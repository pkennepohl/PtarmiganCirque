"""Unified Style Dialog — per-node style editing for any tab (CS-05).

Spec
----
The authoritative spec is ``COMPONENTS.md`` (CS-05) plus Section 7 of
``ARCHITECTURE.md``. This module implements that spec; the docstrings
cover only what the spec leaves open and the implementation decisions
made along the way.

Behavioural model
-----------------
* **Modeless.** A ``tk.Toplevel`` with no ``transient`` and no
  ``grab_set``: the main window stays interactive while the dialog
  is open. Multiple dialogs (one per node) coexist; opening the gear
  on a node that already has an open dialog focuses the existing
  dialog rather than creating a duplicate.

* **Edit through the graph.** Every style mutation routes through
  ``graph.set_style`` (which merges per CS-01). The dialog never
  assigns to ``node.style`` directly. ``set_style`` fires
  ``NODE_STYLE_CHANGED``, so the plot redraws via the tab's existing
  graph subscription — the dialog never triggers a redraw itself.

* **Live external sync.** The dialog subscribes to
  ``NODE_STYLE_CHANGED`` for its own node. When another source (a
  sibling dialog, a ScanTreeWidget row control, the bottom ∀ button)
  writes to the same node's style, the dialog's widget values refresh
  in place. A re-entrancy guard (``_suspend_writes``) prevents the
  refresh from firing recursive ``set_style`` calls.

* **Cancel revert.** ``__init__`` snapshots the current style. Cancel
  re-emits the snapshot via ``set_style`` so the original values
  are restored. Note: ``set_style`` merges (CS-01), so style keys
  added during the session that were absent from the snapshot remain
  on the node — see "Implementation notes" in CS-05 for the
  rationale.

Construction
------------

::

    StyleDialog(
        parent,                 # tk.Widget for the Toplevel parent
        graph,                  # ProjectGraph
        node_id,                # the DataNode being edited
        on_apply_to_all=None,   # callable(param_name, value) for ∀
                                # gestures. The dialog only delegates;
                                # the tab decides which other nodes to
                                # apply the value to.
    )

Or, more commonly, via the module-level factory which handles the
"focus existing dialog" rule:

::

    open_style_dialog(parent, graph, node_id, on_apply_to_all=None)
"""

from __future__ import annotations

import copy
import logging
import tkinter as tk
from tkinter import colorchooser, ttk
from typing import Any, Callable

from graph import GraphEvent, GraphEventType, ProjectGraph
from nodes import DataNode, NodeType

_log = logging.getLogger(__name__)


# =====================================================================
# Module-level state
# =====================================================================

# node_id → live StyleDialog instance. Used by ``open_style_dialog``
# to deduplicate: a second open request for the same node focuses the
# existing window rather than creating another. Entries are cleaned
# up by ``StyleDialog._on_destroy``.
_open_dialogs: "dict[str, StyleDialog]" = {}


_LS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Solid",    "solid"),
    ("Dashed",   "dashed"),
    ("Dotted",   "dotted"),
    ("Dash-dot", "dashdot"),
)


# Module-level defaults used when the node's style dict is missing a
# key the universal section needs to render. Kept in sync with the
# defaults the ScanTreeWidget uses (``scan_tree_widget._DEFAULT_STYLE``).
_UNIVERSAL_DEFAULTS: dict[str, Any] = {
    "color":       "#1f77b4",
    "linestyle":   "solid",
    "linewidth":   1.5,
    "alpha":       0.9,
    "fill":        False,
    "fill_alpha":  0.08,
}


# Style keys the bottom "∀ Apply to All" button fans out (per CS-05:
# "all style settings except colour"). The dialog reads each key's
# current value from its own widget and delegates via ``on_apply_to_all``
# — the tab decides which sibling nodes receive the value.
_BULK_UNIVERSAL_KEYS: tuple[str, ...] = (
    "linestyle", "linewidth", "alpha", "fill", "fill_alpha",
)


# Conditional sections per node type. Keys map to the section-builder
# methods on ``StyleDialog`` (named ``_build_section_<name>``). A node
# type absent from the table has only the universal section.
#
# Populated in Part B; Part A ships with the universal section only.
_SECTIONS_BY_TYPE: dict[NodeType, tuple[str, ...]] = {}


# =====================================================================
# Module-level factory
# =====================================================================

def open_style_dialog(
    parent: tk.Widget,
    graph: ProjectGraph,
    node_id: str,
    on_apply_to_all: Callable[[str, Any], None] | None = None,
) -> "StyleDialog":
    """Open the style dialog for a node, or focus the existing one.

    Per CS-05 each node has at most one open style dialog at a time.
    A second request for the same ``node_id`` raises the existing
    Toplevel rather than creating a duplicate.

    Returns the live ``StyleDialog`` either way.
    """
    existing = _open_dialogs.get(node_id)
    if existing is not None:
        try:
            if bool(existing.winfo_exists()):
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass
        # Stale registry entry — fall through to construct fresh.
        _open_dialogs.pop(node_id, None)
    return StyleDialog(parent, graph, node_id, on_apply_to_all)


# =====================================================================
# Dialog
# =====================================================================

class StyleDialog(tk.Toplevel):
    """Modeless per-node style editor (CS-05).

    See module docstring for the design model. The class is a
    ``Toplevel`` so each node gets its own independent window.
    """

    # ------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------

    def __init__(
        self,
        parent: tk.Widget,
        graph: ProjectGraph,
        node_id: str,
        on_apply_to_all: Callable[[str, Any], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._graph = graph
        self._node_id = node_id
        self._on_apply_to_all = on_apply_to_all

        node = graph.get_node(node_id)
        if not isinstance(node, DataNode):
            raise TypeError(
                f"StyleDialog only edits DataNode, got "
                f"{type(node).__name__}"
            )
        self._node_type = node.type

        # Snapshot for Cancel revert.
        self._snapshot: dict[str, Any] = copy.deepcopy(node.style)

        # Re-entrancy guard. Set to True while we are in the middle
        # of writing through ``set_style`` (so the resulting
        # ``NODE_STYLE_CHANGED`` event is ignored), and while we are
        # refreshing widgets in response to an external event (so the
        # widget callbacks don't loop back into ``set_style``).
        self._suspend_writes: bool = True

        # Per-key Tk variables. Populated by section builders.
        # ``_control_vars[key]`` is the variable the user sees;
        # ``_value_labels[key]`` is the optional ``[value]`` label
        # next to a slider, refreshed when the value changes.
        self._control_vars: dict[str, tk.Variable] = {}
        self._value_labels: dict[str, tk.Label] = {}
        # Per-key "writer" closures the refresh path uses to push a
        # graph-side value back into the widget without firing a
        # write-back. Populated by the row builders.
        self._control_refresh: dict[str, Callable[[Any], None]] = {}

        self.title(f"Style — {node.label}")
        # Modeless: no transient / no grab_set (per CS-05).

        self._build_body(node)
        self._build_button_row()

        # Subscribe AFTER widgets exist so the first inbound event
        # finds a populated control map.
        self._graph.subscribe(self._on_graph_event)

        self.bind("<Destroy>", self._on_destroy, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close_requested)

        # Register so a second open_style_dialog call finds us.
        _open_dialogs[node_id] = self

        # Construction complete: live writes from now on.
        self._suspend_writes = False

    # ------------------------------------------------------------
    # Body construction
    # ------------------------------------------------------------

    def _build_body(self, node: DataNode) -> None:
        """Build the universal section followed by any conditional sections.

        Conditional sections are looked up in ``_SECTIONS_BY_TYPE`` and
        added via ``_build_section_<name>`` methods. Hidden sections
        consume no vertical space — they simply aren't created.
        """
        body = tk.Frame(self, padx=12, pady=8)
        body.pack(fill=tk.BOTH, expand=True)
        self._body = body

        # Universal section (no LabelFrame; renders flush at the top).
        self._build_universal_section(body, node)

        # Conditional sections: one tk.LabelFrame per section, each
        # preceded by a horizontal separator. Hidden sections (those
        # not in _SECTIONS_BY_TYPE for this node type) are simply not
        # created — they consume no vertical space.
        section_names = _SECTIONS_BY_TYPE.get(node.type, ())
        for name in section_names:
            ttk.Separator(body, orient=tk.HORIZONTAL).pack(
                fill=tk.X, pady=(8, 4),
            )
            builder = getattr(self, f"_build_section_{name}", None)
            if builder is None:
                _log.warning(
                    "style_dialog: no builder for section %r (node %r)",
                    name, self._node_id,
                )
                continue
            builder(body, node)

    def _build_universal_section(
        self, parent: tk.Widget, node: DataNode,
    ) -> None:
        """Universal section: line style / width / opacity / colour / fill.

        Layout uses a 4-column grid (label · control · value · ∀).
        """
        sec = tk.Frame(parent)
        sec.pack(fill=tk.X)
        sec.columnconfigure(1, weight=1)

        row = 0

        # ── Line style ────────────────────────────────────────────
        ls_var = tk.StringVar(value=self._style_get("linestyle"))
        self._control_vars["linestyle"] = ls_var

        tk.Label(sec, text="Line style:", font=("", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=(0, 4),
        )
        ls_frame = tk.Frame(sec)
        ls_frame.grid(row=row, column=1, columnspan=2, sticky="w")
        for display, value in _LS_OPTIONS:
            tk.Radiobutton(
                ls_frame, text=display, variable=ls_var, value=value,
            ).pack(side=tk.LEFT, padx=3)
        ls_var.trace_add(
            "write",
            lambda *_, k="linestyle", v=ls_var:
                self._write_partial({k: v.get()}),
        )
        self._add_apply_one_button(sec, row, 3, "linestyle", ls_var.get)

        def _refresh_ls(value, _v=ls_var):
            _v.set(str(value))
        self._control_refresh["linestyle"] = _refresh_ls
        row += 1

        # ── Line width ────────────────────────────────────────────
        lw_var = tk.DoubleVar(value=float(self._style_get("linewidth")))
        self._control_vars["linewidth"] = lw_var
        self._build_slider_row(
            sec, row, "Line width:", lw_var,
            lo=0.5, hi=5.0, res=0.1, key="linewidth", unit="pt",
        )
        row += 1

        # ── Line opacity ──────────────────────────────────────────
        alpha_var = tk.DoubleVar(value=float(self._style_get("alpha")))
        self._control_vars["alpha"] = alpha_var
        self._build_slider_row(
            sec, row, "Line opacity:", alpha_var,
            lo=0.0, hi=1.0, res=0.05, key="alpha",
        )
        row += 1

        # ── Colour ────────────────────────────────────────────────
        col_var = tk.StringVar(value=str(self._style_get("color")))
        self._control_vars["color"] = col_var
        self._build_colour_row(sec, row, col_var)
        row += 1

        # ── Fill area (checkbutton) ───────────────────────────────
        fill_var = tk.BooleanVar(value=bool(self._style_get("fill")))
        self._control_vars["fill"] = fill_var
        tk.Label(sec, text="Fill area:", font=("", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=3,
        )
        tk.Checkbutton(
            sec, text="Show fill under curve", variable=fill_var,
        ).grid(row=row, column=1, columnspan=2, sticky="w")
        fill_var.trace_add(
            "write",
            lambda *_, k="fill", v=fill_var:
                self._write_partial({k: bool(v.get())}),
        )
        self._add_apply_one_button(
            sec, row, 3, "fill", lambda v=fill_var: bool(v.get()),
        )

        def _refresh_fill(value, _v=fill_var):
            _v.set(bool(value))
        self._control_refresh["fill"] = _refresh_fill
        row += 1

        # ── Fill opacity ──────────────────────────────────────────
        fill_alpha_var = tk.DoubleVar(
            value=float(self._style_get("fill_alpha")),
        )
        self._control_vars["fill_alpha"] = fill_alpha_var
        self._build_slider_row(
            sec, row, "Fill opacity:", fill_alpha_var,
            lo=0.0, hi=0.5, res=0.01, key="fill_alpha",
        )
        row += 1

    # ------------------------------------------------------------
    # Slider helper (used by universal and several conditional sections)
    # ------------------------------------------------------------

    def _build_slider_row(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        var: tk.DoubleVar,
        lo: float,
        hi: float,
        res: float,
        key: str,
        unit: str = "",
    ) -> None:
        """Build a labelled Scale + value-label + ∀-button row.

        Variable changes (slider drag, ``var.set``, ``scale.set``) all
        fire a ``trace_add("write")`` callback that updates the value
        label and writes to the graph via ``_write_partial``. Using
        a variable trace rather than the Scale's ``command`` is more
        robust: ``command`` is not fired by all sources of change in
        every Tk version, but a ``write`` trace is.
        """
        tk.Label(parent, text=label, font=("", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=3,
        )
        val_lbl = tk.Label(parent, font=("Courier", 8), width=8)

        def _fmt(*_):
            try:
                val_lbl.config(
                    text=f"{var.get():.3g}{(' ' + unit) if unit else ''}",
                )
            except Exception:
                pass

        sc = tk.Scale(
            parent, variable=var, from_=lo, to=hi, resolution=res,
            orient=tk.HORIZONTAL, length=160, showvalue=False,
        )
        sc.grid(row=row, column=1, sticky="ew", padx=4)
        val_lbl.grid(row=row, column=2, sticky="w")
        _fmt()
        self._value_labels[key] = val_lbl
        self._add_apply_one_button(parent, row, 3, key, var.get)

        def _on_var_write(*_, k=key, v=var, f=_fmt):
            f()
            self._write_partial({k: float(v.get())})
        var.trace_add("write", _on_var_write)

        def _refresh(value, _v=var, _f=_fmt):
            _v.set(float(value))
            _f()
        self._control_refresh[key] = _refresh

    # ------------------------------------------------------------
    # Colour row (swatch + reset, with ∀)
    # ------------------------------------------------------------

    def _build_colour_row(
        self, parent: tk.Widget, row: int, col_var: tk.StringVar,
    ) -> None:
        tk.Label(parent, text="Colour:", font=("", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=4,
        )

        # Swatch button (click → colorchooser).
        col_swatch = tk.Button(
            parent, bg=col_var.get(), width=4, relief=tk.RAISED,
            cursor="hand2",
        )
        col_swatch.grid(row=row, column=1, sticky="w", padx=(4, 0))

        def _set_swatch(value: str) -> None:
            try:
                col_swatch.config(bg=value, activebackground=value)
            except tk.TclError:
                pass

        def _pick():
            initial = col_var.get().strip() or _UNIVERSAL_DEFAULTS["color"]
            result = colorchooser.askcolor(
                color=initial, title="Choose colour", parent=self,
            )
            if result and result[1]:
                col_var.set(result[1])
                _set_swatch(result[1])
                self._write_partial({"color": result[1]})

        col_swatch.config(command=_pick)

        # Reset button — restores the snapshot colour at dialog open
        # (so Reset is undo to whatever was there when the dialog
        # appeared, not to a global palette default — the dialog has
        # no palette knowledge).
        snapshot_color = (
            self._snapshot.get("color")
            or _UNIVERSAL_DEFAULTS["color"]
        )

        def _reset():
            col_var.set(snapshot_color)
            _set_swatch(snapshot_color)
            self._write_partial({"color": snapshot_color})

        reset_row = tk.Frame(parent)
        reset_row.grid(row=row, column=2, sticky="w", padx=4)
        tk.Button(
            reset_row, text="Reset", font=("", 8), command=_reset,
        ).pack(side=tk.LEFT)

        self._add_apply_one_button(
            parent, row, 3, "color",
            lambda v=col_var: v.get().strip() or _UNIVERSAL_DEFAULTS["color"],
        )

        def _refresh_color(value, _v=col_var):
            _v.set(str(value))
            _set_swatch(str(value))
        self._control_refresh["color"] = _refresh_color

    # ------------------------------------------------------------
    # ∀ button factory
    # ------------------------------------------------------------

    def _add_apply_one_button(
        self,
        parent: tk.Widget,
        row: int,
        column: int,
        key: str,
        get_fn: Callable[[], Any],
    ) -> tk.Button:
        """Place a per-parameter ∀ button at (row, column).

        Clicking it calls ``self._on_apply_to_all(key, get_fn())`` —
        the dialog only delegates; the tab decides which sibling
        nodes receive the value (CS-05).

        When ``on_apply_to_all`` is None (i.e., no tab has wired it),
        the button is rendered disabled so the user sees the affordance
        but can't trigger a no-op.
        """
        b = tk.Button(
            parent, text="∀", font=("", 8), relief=tk.FLAT,
            cursor="hand2", fg="#004400",
            activeforeground="#006600",
            command=lambda k=key, g=get_fn: self._delegate_apply_one(k, g()),
        )
        b.grid(row=row, column=column, padx=(2, 0), sticky="w")
        if self._on_apply_to_all is None:
            b.config(state=tk.DISABLED)
        return b

    def _delegate_apply_one(self, key: str, value: Any) -> None:
        """Invoke the tab's apply-to-all callback for one parameter.

        The dialog also writes the value to its own node so the local
        widgets stay in sync with the graph (the tab's fan-out is free
        to skip its own node or include it; either way the dialog's
        node ends up with the value).
        """
        # Self-write first so the local node reflects the gesture even
        # if the tab's fan-out callback is a no-op for the dialog's own
        # node id.
        self._write_partial({key: value})
        if self._on_apply_to_all is not None:
            try:
                self._on_apply_to_all(key, value)
            except Exception:
                _log.warning(
                    "style_dialog: on_apply_to_all raised for "
                    "%r=%r (node %r)",
                    key, value, self._node_id, exc_info=True,
                )

    # ------------------------------------------------------------
    # Bottom button row
    # ------------------------------------------------------------

    def _build_button_row(self) -> None:
        """Apply · ∀ Apply to All · Save · Cancel row at the bottom."""
        btn_row = tk.Frame(self)
        btn_row.pack(pady=(4, 10))

        self._apply_btn = tk.Button(
            btn_row, text="Apply", width=10, command=self._do_apply,
        )
        self._apply_btn.pack(side=tk.LEFT, padx=3)

        self._apply_all_btn = tk.Button(
            btn_row, text="∀  Apply to All", width=14,
            bg="#004400", fg="white", activeforeground="white",
            command=self._do_apply_all,
        )
        self._apply_all_btn.pack(side=tk.LEFT, padx=3)
        if self._on_apply_to_all is None:
            self._apply_all_btn.config(state=tk.DISABLED)

        self._save_btn = tk.Button(
            btn_row, text="Save", width=8, command=self._do_save,
        )
        self._save_btn.pack(side=tk.LEFT, padx=3)

        self._cancel_btn = tk.Button(
            btn_row, text="Cancel", width=8, command=self._do_cancel,
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=3)

    # ------------------------------------------------------------
    # Bottom button actions
    # ------------------------------------------------------------

    def _read_universal_values(self) -> dict[str, Any]:
        """Snapshot every universal-section widget into a partial dict."""
        out: dict[str, Any] = {}
        for key in (
            "linestyle", "linewidth", "alpha",
            "color", "fill", "fill_alpha",
        ):
            var = self._control_vars.get(key)
            if var is None:
                continue
            try:
                value = var.get()
            except tk.TclError:
                continue
            # Coerce types so set_style payloads are clean.
            if key in ("linewidth", "alpha", "fill_alpha"):
                value = float(value)
            elif key == "fill":
                value = bool(value)
            elif key in ("linestyle", "color"):
                value = str(value)
            out[key] = value
        return out

    def _do_apply(self) -> None:
        """Re-emit current widget state (idempotent if already live)."""
        partial = self._read_universal_values()
        self._write_partial(partial)

    def _do_save(self) -> None:
        self._do_apply()
        self.destroy()

    def _do_cancel(self) -> None:
        """Restore the snapshot and close.

        ``set_style`` merges, so any keys added during the session
        that were absent from the snapshot remain on the node. This
        matches the existing UV/Vis dialog and is documented in CS-05
        Implementation notes.
        """
        if self._snapshot:
            self._write_partial(dict(self._snapshot))
        self.destroy()

    def _do_apply_all(self) -> None:
        """Bottom ∀: fan out every universal-section param except colour."""
        if self._on_apply_to_all is None:
            return
        values = self._read_universal_values()
        for key in _BULK_UNIVERSAL_KEYS:
            if key not in values:
                continue
            self._delegate_apply_one(key, values[key])

    def _on_close_requested(self) -> None:
        """Window-close [X] is treated as Cancel (revert + close).

        With live updates, leaving changes on the node when the user
        hits the close box would feel like a bug — they expect the
        same revert behaviour as Cancel.
        """
        self._do_cancel()

    # ------------------------------------------------------------
    # Style read helper
    # ------------------------------------------------------------

    def _style_get(self, key: str) -> Any:
        """Fetch a style value with the universal-default fallback."""
        try:
            node = self._graph.get_node(self._node_id)
        except KeyError:
            return _UNIVERSAL_DEFAULTS.get(key)
        if not isinstance(node, DataNode):
            return _UNIVERSAL_DEFAULTS.get(key)
        return node.style.get(key, _UNIVERSAL_DEFAULTS.get(key))

    # ------------------------------------------------------------
    # Graph write (with re-entrancy guard)
    # ------------------------------------------------------------

    def _write_partial(self, partial: dict[str, Any]) -> None:
        """Send a partial through ``graph.set_style`` once, with guard.

        While the write is in flight we mark ``_suspend_writes`` so the
        resulting ``NODE_STYLE_CHANGED`` event is treated as our own
        (no widget refresh) and any widget-callback re-entries from
        side effects are suppressed.
        """
        if self._suspend_writes:
            return
        if not partial:
            return
        self._suspend_writes = True
        try:
            self._graph.set_style(self._node_id, partial)
        except (KeyError, TypeError, ValueError):
            # Stale node id or wrong node type: dialog is in a bad
            # state, but we don't want to crash the UI here.
            _log.warning(
                "style_dialog: set_style failed for node %r partial %r",
                self._node_id, partial, exc_info=True,
            )
        finally:
            self._suspend_writes = False

    # ------------------------------------------------------------
    # Graph event subscriber
    # ------------------------------------------------------------

    def _on_graph_event(self, event: GraphEvent) -> None:
        """Refresh widgets when an external source mutates this node's style.

        Ignores events for other nodes and events the dialog itself
        triggered (``_suspend_writes`` is True throughout the
        ``_write_partial`` body, including the synchronous notify
        dispatch).
        """
        if event.node_id != self._node_id:
            return
        if event.type != GraphEventType.NODE_STYLE_CHANGED:
            return
        if self._suspend_writes:
            return
        new_style = event.payload.get("new_style") or {}
        self._refresh_widgets(new_style)

    def _refresh_widgets(self, new_style: dict[str, Any]) -> None:
        """Push graph-side values into widgets without firing write-backs."""
        self._suspend_writes = True
        try:
            for key, refresher in self._control_refresh.items():
                if key not in new_style:
                    continue
                try:
                    refresher(new_style[key])
                except Exception:
                    _log.warning(
                        "style_dialog: refresher for %r raised "
                        "(node %r)", key, self._node_id, exc_info=True,
                    )
        finally:
            self._suspend_writes = False

    # ------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------

    def _on_destroy(self, _event: tk.Event) -> None:
        """Drop the graph subscription and registry entry on close.

        Idempotent — both Tk's <Destroy> event and the WM close hook
        can fire, but the underlying ops are safe to run twice.
        """
        try:
            self._graph.unsubscribe(self._on_graph_event)
        except Exception:
            pass
        if _open_dialogs.get(self._node_id) is self:
            _open_dialogs.pop(self._node_id, None)

    # ------------------------------------------------------------
    # Conditional section builders (Phase 3 Part B fills these in)
    # ------------------------------------------------------------

    # Each section builder takes (parent, node) and builds inside
    # ``parent`` (typically the body Frame). They are looked up by
    # name via ``_SECTIONS_BY_TYPE``. Hidden sections are never
    # constructed and so consume no vertical space (per the task
    # spec "Hidden sections must NOT consume vertical space").
    #
    # Filled in by Part B.
