"""Modeless cross-node style dropdown (CS-74, Phase 4au).

Sibling surface to :mod:`style_dialog` (CS-05) that lets the user
walk every renderable DataNode on the host tab from one dialog
instead of opening N per-node ``StyleDialog``s. The user-facing
request (Phase 4ap step-5 elicitation):

    "just like plot settings, I'd like a way of having access to all
     node plot settings from the pop up window. dropdown menu with
     all of the loaded nodes?"

CS-74 lock decisions (Phase 4au):

* **D1 — Container.** New sibling modeless ``Toplevel`` in its own
  module rather than a 7th tab on :class:`plot_settings_dialog.PlotConfigDialog`.
  PlotConfigDialog carries a CS-23 working-copy + Apply/Save/Cancel
  contract for tab-private UI state; node styles are graph-resident
  via :meth:`ProjectGraph.set_style`. Mixing the two semantics inside
  one dialog would force either a Cancel that reverts graph mutations
  (which the graph contract doesn't support) OR a Cancel that silently
  excludes the new tab (an asymmetric contract on a unified surface).
  A sibling dialog inherits :mod:`style_dialog`'s live-write contract
  directly and reuses CS-66's ``_open_dialogs`` per-host singleton
  pattern.
* **D2 — Dropdown scope.** Every renderable DataNode the host tab
  shows: the union of :meth:`UVVisTab._spectrum_nodes` (UVVIS /
  BASELINE / NORMALISED / SMOOTHED), :meth:`_second_derivative_nodes`
  (SECOND_DERIVATIVE), and :meth:`_peak_list_nodes` (PEAK_LIST). The
  host owns the enumeration; the dialog receives the precomputed list
  via the constructor and via :meth:`refresh_node_list`.
* **D3 — Refresh recipe.** CS-72 playbook reused exactly:
  ``refresh_node_list(nodes)`` public method on the dialog (widget-
  state only — no graph mutation, no working-copy touch) plus
  ``_notify_node_list_change()`` helper on the host that looks up the
  dialog via ``_open_dialogs.get(id(parent))`` and fires the refresh.
  Host dispatch fires from ``_on_graph_event`` for NODE_ADDED,
  NODE_DISCARDED, NODE_LABEL_CHANGED, NODE_GROUP_MEMBERS_CHANGED,
  GRAPH_LOADED, GRAPH_CLEARED. Explicitly omits NODE_STYLE_CHANGED
  (would rebuild widgets the user is mid-edit) and NODE_ACTIVE_CHANGED
  (visibility, not list membership).
* **D4 — CS-05 coexistence.** The per-row ``⚙`` gear button on
  :class:`ScanTreeWidget` rows still opens an independent
  :class:`style_dialog.StyleDialog` (CS-05). Both surfaces write
  through :meth:`ProjectGraph.set_style`; the resulting
  ``NODE_STYLE_CHANGED`` event drives both dialogs' refresh paths so
  they stay in sync. CS-05 has no retirement.
* **D5 — Per-row ∀ broadcast.** Each universal-section row carries a
  ``∀`` button matching the CS-05 visual ( ``text="∀"``,
  ``font=("", 8)``, ``relief=tk.FLAT``). The button delegates via
  ``on_apply_to_all(param_name, value)`` — the host wires
  :meth:`UVVisTab._on_uvvis_apply_to_all` which already carries the
  CS-50 key-conditional widening for ``y_axis`` (fans across
  ``_spectrum_nodes + _second_derivative_nodes + _peak_list_nodes``).
* **D6 — Close-only button row.** Live writes via ``graph.set_style``
  ARE the save; there is no working-copy, no per-session snapshot, no
  Cancel/Save dichotomy. The user closes the dialog when done; edits
  remain. A multi-node Cancel would have ambiguous blast radius (which
  session of edits does it revert?); a per-current-node Cancel would
  fire surprisingly on window-close after the user had switched away
  from the most-recently-edited node. CS-05's per-node snapshot remains
  available via the gear button — this dialog is the "browse N nodes
  quickly" surface, complementary not redundant.
* **D7 — Component number.** CS-74.

Phase 4av polish-bundle additions (still CS-74; not a new lock set):

* **Item #1 — Combobox state-badge prefix.** Display string becomes
  ``f"{glyph} {label} ({TYPE})"`` where glyph is ``🔒`` for COMMITTED
  and ``⋯`` for PROVISIONAL (matches the
  :mod:`scan_tree_widget` convention exactly). Disambiguates two
  same-labelled siblings differing only in NodeState.
* **Item #2 — Palette-picked colour Reset.** ``_on_colour_reset``
  delegates to :func:`node_styles.pick_default_color`. CS-21 D3
  (palette-helper invocation site) grows from two callers to three;
  the helper is unchanged.
* **Item #3 — Keyboard Combobox navigation.** ``<Control-Down>`` /
  ``<Control-Up>`` step through the Combobox without touching the
  mouse. Bound on the Toplevel (not on the Combobox itself) so the
  bindings fire regardless of focus inside the dialog. ``Control``
  modifier avoids conflicting with Combobox-internal arrow nav.
  Clamps at list ends (no wrap).
* **Item #4 — Y-axis NodeType guard.** Row is built once
  unconditionally, then dynamically state-gated by
  :meth:`_update_y_axis_row_state` whenever the selected node's
  NodeType falls outside :data:`_Y_AXIS_VISIBLE_NODETYPES`. No-op on
  UVVisTab today (every dropdown NodeType passes the filter); becomes
  load-bearing when Compare / XANES / EXAFS adopt the dialog and the
  Combobox starts listing non-Y-routable types.

Re-entrancy guard ``_suspend_writes`` mirrors CS-05's pattern: set
during every ``set_style`` / ``set_label`` write so the resulting
graph event is recognized as "ours" and the widget-refresh callback
skips re-entry; set during external-event widget refreshes so the
``trace_add('write')`` callbacks don't loop back into ``set_style``.

CS-74 carries no PTMG schema impact — every key it writes already
exists on :data:`scan_tree_widget._DEFAULT_STYLE` and round-trips via
CS-46.
"""

from __future__ import annotations

import copy
import logging
import tkinter as tk
import tkinter.colorchooser
from tkinter import ttk
from typing import Any, Callable, Iterable, Optional

from nodes import DataNode, NodeState, NodeType
from graph import GraphEvent, GraphEventType, ProjectGraph
from node_styles import pick_default_color

_log = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────
# Constants — mirrored from style_dialog.py for the universal section.
# A sentinel test pins these against the canonical sources to catch
# drift (see TestNodeStylesDialogConstantsMirror).
# ───────────────────────────────────────────────────────────────────

_LS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Solid",     "solid"),
    ("Dashed",    "dashed"),
    ("Dotted",    "dotted"),
    ("Dash-dot",  "dashdot"),
)

_Y_AXIS_DISPLAY_DEFAULT: str = "(default)"
_Y_AXIS_OPTIONS: tuple[str, ...] = (
    _Y_AXIS_DISPLAY_DEFAULT, "primary", "secondary", "tertiary",
)

# Mirrors style_dialog._Y_AXIS_VISIBLE_NODETYPES exactly. The Combobox
# row is built only when the selected node's type is in the set; for
# other types the row is suppressed entirely so the misleading-
# affordance footgun documented in CS-50 / CS-52 cannot occur.
_Y_AXIS_VISIBLE_NODETYPES: frozenset[NodeType] = frozenset({
    NodeType.UVVIS,
    NodeType.BASELINE,
    NodeType.NORMALISED,
    NodeType.SMOOTHED,
    NodeType.PEAK_LIST,
    NodeType.SECOND_DERIVATIVE,
})

# Universal-section style keys in the order they render in the dialog.
# Used by :meth:`NodeStylesDialog._refresh_widgets` to walk every
# registered refresher when a NODE_STYLE_CHANGED event lands on the
# selected node.
_UNIVERSAL_KEYS: tuple[str, ...] = (
    "linestyle", "linewidth", "alpha",
    "color", "fill", "fill_alpha",
    "visible", "in_legend",
    "y_axis",
)

# Fallback values consulted when a node's ``style`` dict lacks a key.
# Mirrors scan_tree_widget._DEFAULT_STYLE plus the universal-section
# additions Phase 4d (visible / in_legend) and Phase 4y (y_axis).
_UNIVERSAL_DEFAULTS: dict[str, Any] = {
    "linestyle":  "solid",
    "linewidth":  1.5,
    "alpha":      1.0,
    "color":      "#1f77b4",
    "fill":       False,
    "fill_alpha": 0.15,
    "visible":    True,
    "in_legend":  True,
    "y_axis":     None,
}


# ───────────────────────────────────────────────────────────────────
# Y-axis display ⇄ value helpers — mirror style_dialog's translation
# pair so the persisted ``style["y_axis"]`` value matches whichever
# surface the user edited from.
# ───────────────────────────────────────────────────────────────────

def _y_axis_display_to_value(display: str) -> Optional[str]:
    if display == _Y_AXIS_DISPLAY_DEFAULT:
        return None
    if display in ("primary", "secondary", "tertiary"):
        return display
    return None


def _y_axis_value_to_display(value: Any) -> str:
    if value is None:
        return _Y_AXIS_DISPLAY_DEFAULT
    if isinstance(value, str) and value in ("primary", "secondary", "tertiary"):
        return value
    return _Y_AXIS_DISPLAY_DEFAULT


# ───────────────────────────────────────────────────────────────────
# Per-host singleton registry (CS-66 pattern, mirrors PlotConfigDialog
# and style_dialog's per-target registries).
# ───────────────────────────────────────────────────────────────────

_open_dialogs: "dict[int, NodeStylesDialog]" = {}


def open_node_styles_dialog(
    parent: tk.Widget,
    graph: ProjectGraph,
    nodes: Iterable[DataNode],
    on_apply_to_all: Callable[[str, Any], None] | None = None,
) -> "NodeStylesDialog":
    """Open the Cross-node Styles dialog for a host, or focus existing.

    CS-74 (Phase 4au): per-host singleton like :class:`PlotConfigDialog`
    (one Node Styles dialog per host tab). A second open request from
    the same ``parent`` raises the existing ``Toplevel`` rather than
    creating a duplicate. Distinct from the per-node CS-05
    :class:`style_dialog.StyleDialog` registry — both can coexist
    (e.g. one Node Styles dialog plus N independent StyleDialogs).

    ``nodes`` is the host's renderable-node enumeration (typically
    ``_spectrum_nodes() + _second_derivative_nodes() + _peak_list_nodes()``);
    the order is preserved as Combobox order so type-grouped sidebar
    ordering carries through.

    ``on_apply_to_all(param_name, value)`` is the per-row ∀ fan-out
    delegate. ``None`` renders the ∀ buttons disabled.
    """
    key = id(parent)
    existing = _open_dialogs.get(key)
    if existing is not None:
        try:
            if bool(existing.winfo_exists()):
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass
        _open_dialogs.pop(key, None)
    return NodeStylesDialog(parent, graph, nodes, on_apply_to_all)


# ───────────────────────────────────────────────────────────────────
# Dialog
# ───────────────────────────────────────────────────────────────────

class NodeStylesDialog(tk.Toplevel):
    """Cross-node modeless style dropdown (CS-74, Phase 4au).

    Top-of-body Combobox lists every renderable DataNode on the host
    tab; selecting a row swaps the dialog's editing focus without
    tearing down the dialog. The body below the Combobox carries the
    CS-05 universal-section rows (linestyle / linewidth / alpha /
    colour / fill / fill_alpha / visible / in_legend / y_axis) plus
    the Phase 4aa label-rename Entry; each row carries a per-row ∀
    button that delegates to the host's ``on_apply_to_all``.

    Live writes via :meth:`ProjectGraph.set_style` and
    :meth:`ProjectGraph.set_label`; no Cancel / Save dichotomy. The
    bottom button row is a single "Close" button. See module
    docstring D6 for the rationale.
    """

    def __init__(
        self,
        parent: tk.Widget,
        graph: ProjectGraph,
        nodes: Iterable[DataNode],
        on_apply_to_all: Callable[[str, Any], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._parent = parent
        self._graph = graph
        self._on_apply_to_all = on_apply_to_all

        # Pre-build state. Populated as widgets are constructed.
        self._nodes: list[DataNode] = list(nodes)
        self._node_id: Optional[str] = (
            self._nodes[0].id if self._nodes else None
        )
        # Re-entrancy guard. True throughout construction so the
        # trace callbacks created by the row builders don't fire
        # write-backs against an in-flight init. Flipped False at
        # the end of __init__.
        self._suspend_writes: bool = True

        # Per-key Tk variables (universal section). Identical shape
        # to StyleDialog._control_vars — populated by the row builders.
        self._control_vars: dict[str, tk.Variable] = {}
        # Per-key writer closures. The refresh path calls these to
        # push a graph-side value back into the widget without
        # triggering a write-back trace.
        self._control_refresh: dict[str, Callable[[Any], None]] = {}
        # ∀ buttons keyed by parameter name. Used by the
        # "no_apply_to_all" path to render them all disabled when the
        # host did not wire a fan-out callback (parity with CS-05).
        self._apply_one_buttons: dict[str, tk.Button] = {}
        # Combobox + StringVar handle, populated by _build_combobox.
        # Stored on self so refresh_node_list can re-set the values
        # list without rebuilding the widget.
        self._combobox: ttk.Combobox | None = None
        self._combobox_var: tk.StringVar | None = None
        # Colour swatch reference (for refresh).
        self._color_swatch: tk.Button | None = None
        # Y-axis Combobox reference (Phase 4av item #4). Stored so
        # :meth:`_update_y_axis_row_state` can flip its state without
        # walking the widget tree.
        self._y_axis_combobox: ttk.Combobox | None = None

        # CS-66 (Phase 4ao): transient binds the dialog above the
        # parent in the WM Z-order without grabbing input. Distinct
        # from CS-05's no-transient choice — CS-05 dialogs are
        # per-node-coexisting (multiple can stack), Node Styles is
        # per-host-singleton like PlotConfigDialog.
        try:
            self.transient(parent.winfo_toplevel())
        except (AttributeError, tk.TclError):
            pass

        self.title("Node Styles")

        self._build_body()
        self._build_button_row()

        # Subscribe AFTER widgets exist so the first inbound event
        # finds a populated control map.
        self._graph.subscribe(self._on_graph_event)

        self.bind("<Destroy>", self._on_destroy, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close_requested)

        # Phase 4av item #3: keyboard Combobox stepping. Ctrl modifier
        # so the bindings don't shadow Tk's built-in Combobox arrow
        # behaviour when the Combobox itself holds focus. Bound on the
        # Toplevel so they fire regardless of which descendant has
        # focus.
        self.bind("<Control-Down>", self._on_keyboard_step_next, add="+")
        self.bind("<Control-Up>", self._on_keyboard_step_prev, add="+")

        _open_dialogs[id(parent)] = self

        # Construction complete; live writes from now on.
        self._suspend_writes = False

    # ------------------------------------------------------------
    # Body construction
    # ------------------------------------------------------------

    def _build_body(self) -> None:
        """Build the Combobox header + universal section."""
        body = tk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))

        self._build_combobox(body)

        ttk.Separator(body, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=(4, 6),
        )

        self._universal_frame = tk.Frame(body)
        self._universal_frame.pack(fill=tk.BOTH, expand=True)
        self._universal_frame.columnconfigure(1, weight=1)

        self._build_universal_section()

    def _build_combobox(self, parent: tk.Widget) -> None:
        """Build the node-selector Combobox at the top of the dialog.

        Display strings come from :meth:`_combobox_label_for`; the
        underlying value is the node id, but the Combobox surface
        speaks display strings so the user reads labels. A
        ``<<ComboboxSelected>>`` binding routes user-driven selection
        through :meth:`_on_combobox_selected`.
        """
        header = tk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            header, text="Node:", font=("", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 4))

        self._combobox_var = tk.StringVar(master=self, value="")
        self._combobox = ttk.Combobox(
            header,
            textvariable=self._combobox_var,
            state="readonly",
            values=self._combobox_values(),
            width=40,
        )
        self._combobox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._combobox.bind(
            "<<ComboboxSelected>>", self._on_combobox_selected,
        )

        # Initial selection: the first node, if any.
        if self._node_id is not None:
            self._combobox_var.set(self._combobox_label_for(self._node_id))

    def _build_universal_section(self) -> None:
        """Build the nine universal-section rows + label Entry.

        Layout mirrors :meth:`style_dialog.StyleDialog._build_universal_section`
        — a 4-column grid (label · control · value · ∀). Builders
        register each row's Tk var in ``_control_vars`` and its
        refresher in ``_control_refresh``; the per-row ∀ button
        registers in ``_apply_one_buttons``.
        """
        sec = self._universal_frame
        row = 0

        # ── Label rename Entry (Phase 4aa pattern, no ∀) ──────────
        self._build_label_row(sec, row)
        row += 1

        # ── Line style (radio) ────────────────────────────────────
        self._build_linestyle_row(sec, row)
        row += 1

        # ── Line width (slider) ───────────────────────────────────
        self._build_slider_row(
            sec, row, "Line width:",
            key="linewidth", lo=0.5, hi=5.0, res=0.1, unit="pt",
        )
        row += 1

        # ── Line opacity (slider) ─────────────────────────────────
        self._build_slider_row(
            sec, row, "Line opacity:",
            key="alpha", lo=0.0, hi=1.0, res=0.05,
        )
        row += 1

        # ── Colour (swatch + reset) ───────────────────────────────
        self._build_colour_row(sec, row)
        row += 1

        # ── Fill area (checkbutton) ───────────────────────────────
        self._build_checkbox_row(
            sec, row,
            label="Fill area:", check_text="Show fill under curve",
            key="fill",
        )
        row += 1

        # ── Fill opacity (slider) ─────────────────────────────────
        self._build_slider_row(
            sec, row, "Fill opacity:",
            key="fill_alpha", lo=0.0, hi=0.5, res=0.01,
        )
        row += 1

        # ── Visible (checkbutton) ─────────────────────────────────
        self._build_checkbox_row(
            sec, row,
            label="Visible:", check_text="Show on plot",
            key="visible",
        )
        row += 1

        # ── In legend (checkbutton) ───────────────────────────────
        self._build_checkbox_row(
            sec, row,
            label="In legend:", check_text="Include in legend",
            key="in_legend",
        )
        row += 1

        # ── Y axis (Combobox) ─────────────────────────────────────
        # Every NodeType the dropdown lists (UVVIS / BASELINE /
        # NORMALISED / SMOOTHED / PEAK_LIST / SECOND_DERIVATIVE) is
        # in _Y_AXIS_VISIBLE_NODETYPES — so the row is always
        # meaningful for the cross-node dialog's UVVisTab-scoped
        # node list. Per-row ∀ on this row triggers the CS-50
        # widened fan-out (host's _on_uvvis_apply_to_all extends
        # the scope for y_axis to include second-deriv + peak-list
        # too).
        self._build_y_axis_row(sec, row)
        row += 1

        # Seed widgets with the initial selection's style values.
        if self._node_id is not None:
            self._refresh_widgets_from_node(self._node_id)
        else:
            self._set_universal_disabled(True)

    # ------------------------------------------------------------
    # Row builders
    # ------------------------------------------------------------

    def _build_label_row(self, parent: tk.Widget, row: int) -> None:
        """Entry row for renaming the currently-selected node.

        Mirrors the Phase 4aa StyleDialog label row exactly — live
        write via :meth:`_write_label_partial` on every keystroke,
        no ∀ button (fanning one label across siblings would collapse
        them onto a single display name).
        """
        current = self._current_label()
        var = tk.StringVar(master=self, value=current)
        self._control_vars["label"] = var

        tk.Label(
            parent, text="Label:", font=("", 9, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=(0, 4))

        entry = tk.Entry(parent, textvariable=var)
        entry.grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=(4, 0),
        )

        def _on_var_write(*_, v=var):
            self._write_label_partial(str(v.get()))
        var.trace_add("write", _on_var_write)

        def _refresh(value, _v=var):
            _v.set(str(value))
        self._control_refresh["label"] = _refresh

    def _build_linestyle_row(self, parent: tk.Widget, row: int) -> None:
        ls_var = tk.StringVar(
            master=self,
            value=str(_UNIVERSAL_DEFAULTS["linestyle"]),
        )
        self._control_vars["linestyle"] = ls_var

        tk.Label(
            parent, text="Line style:", font=("", 9, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=(0, 4))

        ls_frame = tk.Frame(parent)
        ls_frame.grid(row=row, column=1, columnspan=2, sticky="w")
        for display, value in _LS_OPTIONS:
            tk.Radiobutton(
                ls_frame, text=display, variable=ls_var, value=value,
            ).pack(side=tk.LEFT, padx=3)

        ls_var.trace_add(
            "write",
            lambda *_, k="linestyle", v=ls_var:
                self._write_partial({k: str(v.get())}),
        )

        self._add_apply_one_button(parent, row, 3, "linestyle", ls_var.get)

        def _refresh(value, _v=ls_var):
            _v.set(str(value))
        self._control_refresh["linestyle"] = _refresh

    def _build_slider_row(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        key: str,
        lo: float,
        hi: float,
        res: float,
        unit: str = "",
    ) -> None:
        var = tk.DoubleVar(
            master=self,
            value=float(_UNIVERSAL_DEFAULTS[key]),
        )
        self._control_vars[key] = var

        tk.Label(
            parent, text=label, font=("", 9, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=3)

        scale = tk.Scale(
            parent, from_=lo, to=hi, resolution=res,
            orient=tk.HORIZONTAL, variable=var,
            length=180, showvalue=False,
        )
        scale.grid(row=row, column=1, sticky="ew", padx=4)

        value_lbl = tk.Label(
            parent,
            text=self._format_slider_value(var.get(), unit),
            font=("Courier", 9), width=8, anchor="w",
        )
        value_lbl.grid(row=row, column=2, sticky="w")

        def _on_var_write(*_, k=key, v=var, lbl=value_lbl, u=unit):
            try:
                value = float(v.get())
            except (tk.TclError, ValueError):
                return
            lbl.config(text=self._format_slider_value(value, u))
            self._write_partial({k: value})
        var.trace_add("write", _on_var_write)

        self._add_apply_one_button(
            parent, row, 3, key, lambda v=var: float(v.get()),
        )

        def _refresh(value, _v=var, _lbl=value_lbl, _u=unit):
            try:
                f = float(value)
            except (TypeError, ValueError):
                return
            _v.set(f)
            _lbl.config(text=self._format_slider_value(f, _u))
        self._control_refresh[key] = _refresh

    def _build_colour_row(self, parent: tk.Widget, row: int) -> None:
        col_var = tk.StringVar(
            master=self,
            value=str(_UNIVERSAL_DEFAULTS["color"]),
        )
        self._control_vars["color"] = col_var

        tk.Label(
            parent, text="Colour:", font=("", 9, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=3)

        swatch_frame = tk.Frame(parent)
        swatch_frame.grid(row=row, column=1, columnspan=2, sticky="w", padx=4)

        swatch = tk.Button(
            swatch_frame,
            width=4,
            bg=col_var.get(),
            relief=tk.RAISED,
            command=self._on_colour_swatch_click,
        )
        swatch.pack(side=tk.LEFT)
        self._color_swatch = swatch

        reset_btn = tk.Button(
            swatch_frame, text="Reset", font=("", 8),
            command=self._on_colour_reset,
        )
        reset_btn.pack(side=tk.LEFT, padx=(4, 0))

        # No trace on col_var — colour writes come from the colorchooser
        # / reset paths exclusively, and each path calls _write_partial
        # directly. (A trace would double-fire on programmatic refresh.)

        self._add_apply_one_button(
            parent, row, 3, "color", lambda v=col_var: str(v.get()),
        )

        def _refresh(value, _v=col_var, _sw=swatch):
            new_colour = str(value)
            _v.set(new_colour)
            try:
                _sw.config(bg=new_colour)
            except tk.TclError:
                # Malformed colour string — leave swatch as-is and
                # log; the persisted value is the source of truth,
                # the visual is only a status indicator.
                _log.warning(
                    "node_styles_dialog: bad colour %r — swatch unchanged",
                    new_colour,
                )
        self._control_refresh["color"] = _refresh

    def _build_checkbox_row(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        check_text: str,
        key: str,
    ) -> None:
        var = tk.BooleanVar(
            master=self,
            value=bool(_UNIVERSAL_DEFAULTS[key]),
        )
        self._control_vars[key] = var

        tk.Label(
            parent, text=label, font=("", 9, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=3)

        tk.Checkbutton(
            parent, text=check_text, variable=var,
        ).grid(row=row, column=1, columnspan=2, sticky="w")

        var.trace_add(
            "write",
            lambda *_, k=key, v=var:
                self._write_partial({k: bool(v.get())}),
        )

        self._add_apply_one_button(
            parent, row, 3, key, lambda v=var: bool(v.get()),
        )

        def _refresh(value, _v=var):
            _v.set(bool(value))
        self._control_refresh[key] = _refresh

    def _build_y_axis_row(self, parent: tk.Widget, row: int) -> None:
        """Build the Y-axis override Combobox row (CS-50 mirror).

        Round-trip through ``_y_axis_display_to_value`` /
        ``_y_axis_value_to_display`` so the persisted value matches
        CS-05's :data:`style_dialog._Y_AXIS_OPTIONS` translation. The
        per-row ∀ on this row triggers the host's CS-50 widened
        fan-out (writes y_axis across every renderable node, not just
        ``_spectrum_nodes``).
        """
        var = tk.StringVar(
            master=self,
            value=_y_axis_value_to_display(_UNIVERSAL_DEFAULTS["y_axis"]),
        )
        self._control_vars["y_axis"] = var

        tk.Label(
            parent, text="Y axis:", font=("", 9, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=3)

        cb = ttk.Combobox(
            parent, textvariable=var, state="readonly",
            values=list(_Y_AXIS_OPTIONS), width=12,
        )
        cb.grid(row=row, column=1, columnspan=2, sticky="w", padx=4)
        self._y_axis_combobox = cb

        def _on_selected(_event=None, _v=var):
            self._write_partial(
                {"y_axis": _y_axis_display_to_value(str(_v.get()))}
            )
        cb.bind("<<ComboboxSelected>>", _on_selected)

        self._add_apply_one_button(
            parent, row, 3, "y_axis",
            lambda v=var: _y_axis_display_to_value(str(v.get())),
        )

        def _refresh(value, _v=var):
            _v.set(_y_axis_value_to_display(value))
        self._control_refresh["y_axis"] = _refresh

    # ------------------------------------------------------------
    # ∀ button factory + delegator
    # ------------------------------------------------------------

    def _add_apply_one_button(
        self,
        parent: tk.Widget,
        row: int,
        column: int,
        key: str,
        get_fn: Callable[[], Any],
    ) -> tk.Button:
        """Place a per-row ∀ button at ``(row, column)``.

        Click calls :meth:`_delegate_apply_one` which writes the value
        to the dialog's own node first (so the row reflects the
        gesture even if the host's fan-out skips the source node) and
        then invokes ``self._on_apply_to_all(key, value)``.

        Visual matches the CS-05 convention (text="∀", flat relief,
        8-pt font) so the cross-surface ∀ language stays unified.
        """
        b = tk.Button(
            parent, text="∀", font=("", 8), relief=tk.FLAT,
            cursor="hand2", fg="#004400",
            activeforeground="#006600",
            command=lambda k=key, g=get_fn:
                self._delegate_apply_one(k, g()),
        )
        b.grid(row=row, column=column, padx=(2, 0), sticky="w")
        if self._on_apply_to_all is None:
            b.config(state=tk.DISABLED)
        self._apply_one_buttons[key] = b
        return b

    def _delegate_apply_one(self, key: str, value: Any) -> None:
        """Write value to current node then delegate the fan-out.

        Mirrors :meth:`style_dialog.StyleDialog._delegate_apply_one`
        exactly — the dialog never enumerates other nodes itself; the
        host's ``on_apply_to_all`` callback owns the sibling scope.
        Writing to the current node first ensures the row stays in
        sync if the host's fan-out skips the source.
        """
        self._write_partial({key: value})
        if self._on_apply_to_all is not None:
            try:
                self._on_apply_to_all(key, value)
            except Exception:
                _log.warning(
                    "node_styles_dialog: on_apply_to_all raised for "
                    "%r=%r (node %r)",
                    key, value, self._node_id, exc_info=True,
                )

    # ------------------------------------------------------------
    # Colour swatch handlers
    # ------------------------------------------------------------

    def _on_colour_swatch_click(self) -> None:
        if self._node_id is None:
            return
        current = self._current_style_value("color")
        result = tkinter.colorchooser.askcolor(
            color=str(current), parent=self, title="Choose colour",
        )
        if result is None or result[1] is None:
            return
        self._write_partial({"color": result[1]})

    def _on_colour_reset(self) -> None:
        """Reset colour to a freshly-picked palette default.

        Distinct from CS-05's "snapshot" reset semantics — we have no
        snapshot. Phase 4av item #2: delegates to
        :func:`node_styles.pick_default_color` (CS-21 D3 — third
        caller) so the colour the user lands on rotates through
        :data:`node_styles.SPECTRUM_PALETTE` based on the current
        renderable scope. Previously this wrote the constant
        ``_UNIVERSAL_DEFAULTS["color"]`` (``"#1f77b4"``), which
        flattened every node to palette index 0.
        """
        if self._node_id is None:
            return
        try:
            new_colour = pick_default_color(self._graph)
        except Exception:
            _log.warning(
                "node_styles_dialog: pick_default_color raised "
                "(node %r) — falling back to universal default",
                self._node_id, exc_info=True,
            )
            new_colour = str(_UNIVERSAL_DEFAULTS["color"])
        self._write_partial({"color": new_colour})

    # ------------------------------------------------------------
    # Combobox selection handling
    # ------------------------------------------------------------

    def _on_combobox_selected(self, _event: tk.Event | None = None) -> None:
        """User picked a new node from the Combobox.

        Routes through :meth:`_select_node` to refresh widgets.
        """
        if self._combobox_var is None:
            return
        display = str(self._combobox_var.get())
        new_id = self._node_id_for_display(display)
        if new_id is None or new_id == self._node_id:
            return
        self._select_node(new_id)

    def _select_node(self, node_id: str) -> None:
        """Switch the dialog's editing focus to ``node_id``.

        Refreshes every universal-section widget from the new node's
        style + label. The Combobox display is updated to match.
        Phase 4av item #4: after the universal section re-enables,
        the Y-axis row's state is gated by the new selection's
        NodeType.
        """
        self._node_id = node_id
        if self._combobox_var is not None:
            self._combobox_var.set(self._combobox_label_for(node_id))
        self._refresh_widgets_from_node(node_id)
        self._set_universal_disabled(False)
        self._update_y_axis_row_state(self._node_type_for(node_id))

    # ------------------------------------------------------------
    # Keyboard Combobox stepping (Phase 4av item #3)
    # ------------------------------------------------------------

    def _on_keyboard_step_next(self, _event: tk.Event | None = None) -> str:
        """Bound to ``<Control-Down>`` — step Combobox forward by one."""
        self._step_combobox_selection(+1)
        return "break"

    def _on_keyboard_step_prev(self, _event: tk.Event | None = None) -> str:
        """Bound to ``<Control-Up>`` — step Combobox backward by one."""
        self._step_combobox_selection(-1)
        return "break"

    def _step_combobox_selection(self, delta: int) -> None:
        """Move the Combobox selection by ``delta`` rows.

        Clamps at list ends (no wrap). No-op when the list is empty
        or when stepping past either boundary. Calls
        :meth:`_select_node` so the universal section refreshes
        identically to a mouse-driven Combobox selection — the only
        difference is the input gesture.
        """
        if not self._nodes:
            return
        if self._node_id is None:
            target = self._nodes[0]
        else:
            try:
                idx = next(
                    i for i, n in enumerate(self._nodes)
                    if n.id == self._node_id
                )
            except StopIteration:
                target = self._nodes[0]
            else:
                new_idx = idx + delta
                if new_idx < 0 or new_idx >= len(self._nodes):
                    return
                target = self._nodes[new_idx]
        if target.id == self._node_id:
            return
        self._select_node(target.id)

    # ------------------------------------------------------------
    # Refresh — both internally-driven (Combobox switch) and
    # externally-driven (graph events).
    # ------------------------------------------------------------

    def _refresh_widgets_from_node(self, node_id: str) -> None:
        """Push the named node's style + label into every widget."""
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            _log.warning(
                "node_styles_dialog: refresh requested for missing "
                "node %r", node_id,
            )
            return
        if not isinstance(node, DataNode):
            _log.warning(
                "node_styles_dialog: refresh requested for non-DataNode "
                "node %r (%s)", node_id, type(node).__name__,
            )
            return

        self._suspend_writes = True
        try:
            # Label first so the Entry reflects the new selection.
            label_refresher = self._control_refresh.get("label")
            if label_refresher is not None:
                label_refresher(node.label)

            # Universal style keys: read from node.style with
            # _UNIVERSAL_DEFAULTS fallback so a node missing a key
            # still renders something sensible.
            for key in _UNIVERSAL_KEYS:
                refresher = self._control_refresh.get(key)
                if refresher is None:
                    continue
                value = node.style.get(key, _UNIVERSAL_DEFAULTS[key])
                try:
                    refresher(value)
                except Exception:
                    _log.warning(
                        "node_styles_dialog: refresher for %r raised "
                        "(node %r)", key, node_id, exc_info=True,
                    )
        finally:
            self._suspend_writes = False

    def _refresh_widgets_from_style(
        self, new_style: dict[str, Any],
    ) -> None:
        """Push a partial style dict into the registered refreshers.

        Used by the graph-event subscriber when an external surface
        (CS-05 StyleDialog on the same node, sidebar row controls, a
        ∀ broadcast from elsewhere) writes to the currently-selected
        node's style. The label refresher is NOT walked here — label
        changes route through :meth:`_refresh_label_from_event`.
        """
        self._suspend_writes = True
        try:
            for key, refresher in self._control_refresh.items():
                if key == "label":
                    continue
                if key not in new_style:
                    continue
                try:
                    refresher(new_style[key])
                except Exception:
                    _log.warning(
                        "node_styles_dialog: refresher for %r raised "
                        "(node %r)", key, self._node_id, exc_info=True,
                    )
        finally:
            self._suspend_writes = False

    def _refresh_label_from_event(self, new_label: str) -> None:
        """Push an external label change into the Entry + Combobox."""
        self._suspend_writes = True
        try:
            refresher = self._control_refresh.get("label")
            if refresher is not None:
                try:
                    refresher(new_label)
                except Exception:
                    _log.warning(
                        "node_styles_dialog: label refresher raised "
                        "(node %r)", self._node_id, exc_info=True,
                    )
            # Combobox display string contains the label, so re-paint
            # the values list and the selection display.
            if self._combobox is not None and self._combobox_var is not None:
                self._combobox.config(values=self._combobox_values())
                if self._node_id is not None:
                    self._combobox_var.set(
                        self._combobox_label_for(self._node_id)
                    )
        finally:
            self._suspend_writes = False

    def refresh_node_list(self, nodes: Iterable[DataNode]) -> None:
        """Replace the Combobox's node list (CS-72 pattern).

        Public host hook. Widget-state only — no graph mutation, no
        ``_apply_changes_live`` analog. Selection preservation by
        node id: if the previously-selected node is in the new list,
        keep selection; if not, fall back to the first available node
        (or empty if the list is empty).

        Mirrors CS-72's selection-preservation contract but uses node
        id rather than label match — labels mutate (NODE_LABEL_CHANGED
        fires this refresh), so id is the stable identifier.
        """
        new_nodes = list(nodes)
        previous_id = self._node_id

        self._nodes = new_nodes

        if self._combobox is None or self._combobox_var is None:
            return

        # Rebuild the Combobox values list.
        self._combobox.config(values=self._combobox_values())

        if not new_nodes:
            # No nodes left — clear selection, disable all rows.
            self._node_id = None
            self._combobox_var.set("")
            self._set_universal_disabled(True)
            return

        # Try to preserve selection by id.
        new_ids = {n.id for n in new_nodes}
        if previous_id is not None and previous_id in new_ids:
            target_id = previous_id
        else:
            target_id = new_nodes[0].id

        self._select_node(target_id)

    # ------------------------------------------------------------
    # Live writes — graph.set_style / graph.set_label
    # ------------------------------------------------------------

    def _write_partial(self, partial: dict[str, Any]) -> None:
        """Send a partial through graph.set_style.

        Mirrors :meth:`style_dialog.StyleDialog._write_partial`. The
        ``_suspend_writes`` guard is set during the write so the
        resulting NODE_STYLE_CHANGED event is treated as "ours" and
        the widget-refresh callback skips re-entry.
        """
        if self._suspend_writes:
            return
        if not partial:
            return
        if self._node_id is None:
            return
        self._suspend_writes = True
        try:
            self._graph.set_style(self._node_id, partial)
        except (KeyError, TypeError, ValueError):
            _log.warning(
                "node_styles_dialog: set_style failed for node %r "
                "partial %r", self._node_id, partial, exc_info=True,
            )
        finally:
            self._suspend_writes = False

    def _write_label_partial(self, new_label: str) -> None:
        """Send a label rename through graph.set_label."""
        if self._suspend_writes:
            return
        if self._node_id is None:
            return
        self._suspend_writes = True
        try:
            self._graph.set_label(self._node_id, new_label)
        except (KeyError, TypeError, ValueError):
            _log.warning(
                "node_styles_dialog: set_label failed for node %r "
                "label %r", self._node_id, new_label, exc_info=True,
            )
        finally:
            self._suspend_writes = False

    # ------------------------------------------------------------
    # Graph event subscriber
    # ------------------------------------------------------------

    def _on_graph_event(self, event: GraphEvent) -> None:
        """Refresh widgets when an external source mutates this node.

        Skips self-triggered events via the ``_suspend_writes`` guard
        (set throughout ``_write_partial`` / ``_write_label_partial``).
        Only NODE_STYLE_CHANGED + NODE_LABEL_CHANGED on the currently-
        selected node drive a widget refresh from here — every other
        event class (list-membership changes, group changes,
        graph-load) goes through the host-driven
        :meth:`refresh_node_list` path instead, so the dialog has one
        owner for "widget rebuild" vs "selection rebuild".
        """
        if self._suspend_writes:
            return
        if event.node_id != self._node_id:
            return
        if event.type == GraphEventType.NODE_STYLE_CHANGED:
            new_style = event.payload.get("new_style") or {}
            self._refresh_widgets_from_style(new_style)
            return
        if event.type == GraphEventType.NODE_LABEL_CHANGED:
            new_label = str(event.payload.get("new_label", ""))
            self._refresh_label_from_event(new_label)
            return

    # ------------------------------------------------------------
    # Bottom button row + close handlers
    # ------------------------------------------------------------

    def _build_button_row(self) -> None:
        """Single Close button (D6 — see module docstring)."""
        btn_row = tk.Frame(self)
        btn_row.pack(pady=(4, 10))

        self._close_btn = tk.Button(
            btn_row, text="Close", width=10,
            command=self._on_close_requested,
        )
        self._close_btn.pack(side=tk.LEFT, padx=3)

    def _on_close_requested(self) -> None:
        """Close gesture — destroy the dialog. No revert; live writes
        are already committed to the graph."""
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _on_destroy(self, event: tk.Event) -> None:
        """Drop the graph subscription + pop the registry on destroy.

        CS-72 D17 filter: only fire on the Toplevel's own destruction,
        not descendants'. Pre-CS-72 the dialog used to pop the registry
        for any descendant destroy, which would silently break the
        per-host singleton if a refresh path destroyed widgets. The
        Node Styles dialog doesn't destroy descendants (Combobox-
        switch updates values in place rather than rebuilding), but
        the filter is the canonical pattern and the cost is one
        identity check.
        """
        if event.widget is not self:
            return
        try:
            self._graph.unsubscribe(self._on_graph_event)
        except Exception:
            pass
        _open_dialogs.pop(id(self._parent), None)

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _combobox_values(self) -> list[str]:
        return [self._combobox_label_for(n.id) for n in self._nodes]

    def _combobox_label_for(self, node_id: str) -> str:
        """Format a node's Combobox display string.

        Bracketed type name disambiguates similarly-labelled nodes
        across types (e.g. a UVVIS and a BASELINE both labelled
        "Sample A"). Phase 4av item #1: a leading state glyph
        (``🔒`` committed / ``⋯`` provisional, matching
        :mod:`scan_tree_widget`'s convention) further disambiguates
        siblings differing only in NodeState. Falls back to
        ``"<missing>"`` if the id is no longer in the graph —
        defensive against a race between refresh_node_list and a
        NODE_DISCARDED event.
        """
        for n in self._nodes:
            if n.id == node_id:
                glyph = self._state_glyph_for(n.state)
                return f"{glyph} {n.label} ({n.type.name})"
        # Out-of-list id — defer to the graph as a fallback.
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return "<missing>"
        if isinstance(node, DataNode):
            glyph = self._state_glyph_for(node.state)
            return f"{glyph} {node.label} ({node.type.name})"
        return "<missing>"

    @staticmethod
    def _state_glyph_for(state: NodeState) -> str:
        """Return the leading NodeState glyph for a Combobox row.

        Mirrors :mod:`scan_tree_widget`'s
        ``"🔒" if node.state == NodeState.COMMITTED else "⋯"``
        binary check exactly — non-COMMITTED renders as provisional.
        Discarded nodes shouldn't appear in the dialog's node list,
        but if they did, they'd surface as ``⋯``.
        """
        if state == NodeState.COMMITTED:
            return "🔒"
        return "⋯"

    def _node_type_for(self, node_id: str) -> Optional[NodeType]:
        """Return the NodeType for ``node_id`` (helper for Y-axis guard).

        Prefers the local ``self._nodes`` cache, falls back to the
        graph. Returns ``None`` if the id resolves to no DataNode.
        """
        for n in self._nodes:
            if n.id == node_id:
                return n.type
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return None
        if isinstance(node, DataNode):
            return node.type
        return None

    def _update_y_axis_row_state(
        self, node_type: Optional[NodeType],
    ) -> None:
        """Enable / disable the Y-axis row based on NodeType.

        Phase 4av item #4: when the selected node's NodeType is not in
        :data:`_Y_AXIS_VISIBLE_NODETYPES` the Y-axis Combobox and its
        ∀ button render disabled. On UVVisTab today every dropdown
        NodeType passes the filter so this is a visual no-op; the gate
        becomes load-bearing when Compare / XANES / EXAFS adopt the
        dialog and feed in non-Y-routable NodeTypes.

        Also explicitly re-sets the Combobox state to ``"readonly"``
        on re-enable so the pre-existing
        :meth:`_set_universal_disabled` walk (which sets
        ``state=tk.NORMAL`` indiscriminately) does not leave the
        Combobox in a free-text-entry mode.
        """
        if self._y_axis_combobox is None:
            return
        in_scope = (
            node_type is not None
            and node_type in _Y_AXIS_VISIBLE_NODETYPES
        )
        cb_state = "readonly" if in_scope else tk.DISABLED
        btn = self._apply_one_buttons.get("y_axis")
        if in_scope:
            btn_state = (
                tk.NORMAL if self._on_apply_to_all is not None
                else tk.DISABLED
            )
        else:
            btn_state = tk.DISABLED
        try:
            self._y_axis_combobox.config(state=cb_state)
        except tk.TclError:
            pass
        if btn is not None:
            try:
                btn.config(state=btn_state)
            except tk.TclError:
                pass

    def _node_id_for_display(self, display: str) -> Optional[str]:
        for n in self._nodes:
            if self._combobox_label_for(n.id) == display:
                return n.id
        return None

    def _current_label(self) -> str:
        if self._node_id is None:
            return ""
        try:
            node = self._graph.get_node(self._node_id)
        except KeyError:
            return ""
        if isinstance(node, DataNode):
            return node.label
        return ""

    def _current_style_value(self, key: str) -> Any:
        if self._node_id is None:
            return _UNIVERSAL_DEFAULTS.get(key)
        try:
            node = self._graph.get_node(self._node_id)
        except KeyError:
            return _UNIVERSAL_DEFAULTS.get(key)
        if isinstance(node, DataNode):
            return node.style.get(key, _UNIVERSAL_DEFAULTS.get(key))
        return _UNIVERSAL_DEFAULTS.get(key)

    def _set_universal_disabled(self, disabled: bool) -> None:
        """Disable / enable the universal section.

        Disabled state for the "no node selected" path (empty list).
        Re-enabled when refresh_node_list lands a non-empty list and
        a node is selected.
        """
        state = tk.DISABLED if disabled else tk.NORMAL
        # Walk the universal-frame's children recursively and set their
        # state where supported. tk.Label widgets don't have a state
        # option — wrap in try/except to silently skip them.
        for child in self._iter_widgets(self._universal_frame):
            try:
                child.config(state=state)
            except tk.TclError:
                continue
        # ∀ buttons get an additional override — if the host did not
        # wire on_apply_to_all, they stay DISABLED even when the rest
        # of the section is enabled. Same convention as CS-05.
        if not disabled and self._on_apply_to_all is None:
            for b in self._apply_one_buttons.values():
                try:
                    b.config(state=tk.DISABLED)
                except tk.TclError:
                    continue

    @staticmethod
    def _iter_widgets(parent: tk.Widget) -> Iterable[tk.Widget]:
        """Walk the widget tree under ``parent``, depth-first."""
        for child in parent.winfo_children():
            yield child
            yield from NodeStylesDialog._iter_widgets(child)

    @staticmethod
    def _format_slider_value(value: float, unit: str) -> str:
        if unit:
            return f"{value:.2f} {unit}"
        return f"{value:.2f}"
