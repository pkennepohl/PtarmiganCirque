"""ScanTreeWidget — the right-sidebar component shared by every tab.

Spec
----
The authoritative spec is ``COMPONENTS.md`` (CS-04). This module
implements that spec; the docstrings cover only what CS-04 leaves
open and any pragmatic decisions made along the way.

Behavioural model
-----------------
The widget is a stateless view of ``ProjectGraph``. It owns no node
data: every redraw is recomputed from the graph plus a small amount
of local view state (``_show_hidden``, ``_expanded_history``). All
mutations go through graph methods (``set_label``, ``set_active``,
``set_style``, ``commit_node``, ``discard_node``, ``clone_node``,
``add_edge``); the widget never touches a node directly.

It subscribes to ``GraphEvent`` notifications and rebuilds the
affected rows. There is no manual refresh.

Layout (per row, left to right; matches CS-04 §6.1)
---------------------------------------------------

::

    [state] [swatch] [☑] [label] [✓/–] [~~~~] [⌥n] [⚙] [→] [✕]

* ``state``  — ``🔒`` committed, ``⋯`` provisional.
* ``swatch`` — colour button; click opens ``tk.colorchooser``.
* ``☑``      — visibility checkbox; bound to ``style["visible"]``
  (default ``True``).
* ``label``  — double-click opens an in-place ``Entry``.
* ``✓/–``    — legend toggle; bound to ``style["in_legend"]``.
* ``~~~~``   — linestyle canvas; click cycles
  solid → dashed → dotted → dashdot.
* ``⌥n``     — provenance count; click toggles the inline history
  expansion below the row.
* ``⚙``      — invokes ``style_dialog_cb(node_id)``; the widget
  never imports the dialog module (Phase 3).
* ``→``      — invokes ``send_to_compare_cb(node_id)``; disabled
  when no callback is wired (the deferred-tab convention) or the
  row is provisional. Per-row Phase 4n CS-27 replacement for the
  legacy "+ Add to TDDFT Overlay" top-bar bulk button.
* ``✕``      — provisional → ``discard_node``; committed →
  ``set_active(False)`` (soft-hide, not delete; CS-04 §6.1).

Phase 4n CS-26 promoted ``⌥n`` from the optional set into the
always-visible minimum (so the provenance affordance survives a
narrow sidebar) and replaced the single 280 px collapse threshold
with three priority-ordered thresholds — see
``_RESPONSIVE_THRESHOLDS_PX``.

A "Show hidden" checkbutton at the bottom (off by default) reveals
committed nodes that have been soft-hidden (``active=False``).

Sweep groups
------------
A *sweep group* (per the Phase 1 rule) is two or more PROVISIONAL
DataNodes that share the same DataNode parent. Such siblings collapse
into a single row whose label summarises the count, with an
"expand" affordance for inspecting variants individually.

Construction
------------

::

    ScanTreeWidget(
        parent,            # tk.Widget host frame
        graph,             # ProjectGraph
        node_filter,       # list[NodeType] or Callable[[DataNode], bool]
        redraw_cb,         # callable: redraw_cb() = full redraw,
                           # redraw_cb(focus=id) = preview a node
        send_to_compare_cb=None,  # called with node_id; widget
                                  # knows nothing about the Compare tab
        style_dialog_cb=None,     # called with node_id; widget
                                  # knows nothing about the dialog
        export_cb=None,           # called with node_id; host opens
                                  # the file dialog and writes the
                                  # file (CS-17, Phase 4f)
    )

Call ``unsubscribe()`` before destroying the widget if you want to
cleanly drop the observer link (the widget also unsubscribes on
``<Destroy>``).
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import colorchooser
from typing import Any, Callable, Iterable, Sequence, Union

from graph import GraphEvent, GraphEventType, ProjectGraph
from nodes import DataNode, NodeState, NodeType, OperationNode

_log = logging.getLogger(__name__)


# =====================================================================
# Style helpers (mirrors uvvis_tab._LS_CYCLE / _LS_DASH for consistency)
# =====================================================================

_LS_CYCLE: tuple[str, ...] = ("solid", "dashed", "dotted", "dashdot")
_LS_DASH: dict[str, tuple] = {
    "solid":   (),
    "dashed":  (6, 3),
    "dotted":  (2, 3),
    "dashdot": (6, 3, 2, 3),
}

_DEFAULT_STYLE: dict[str, Any] = {
    "color":      "#1f77b4",
    "linestyle":  "solid",
    "linewidth":  1.5,
    "alpha":      0.9,
    "visible":    True,
    "in_legend":  True,
    "fill":       False,
    "fill_alpha": 0.08,
}


# Responsive row collapse — Phase 4d B-002 (single 280 px threshold)
# extended in Phase 4n CS-26 to three priority-ordered thresholds.
#
# The always-visible minimum is now ``state · ☑ · label · ⌥n · ⚙ ·
# → · ✕`` (seven cells). Optional cells reveal in priority order as
# the row widens past each threshold:
#
#   1. ``swatch``    — ``style.color`` colour button (priority 1)
#   2. ``leg``       — ``✓/–`` legend toggle      (priority 2)
#   3. ``ls_canvas`` — linestyle preview canvas   (priority 3)
#
# Below the smallest threshold, no optional cells are shown; the
# always-visible minimum keeps the row usable. The full set of
# hidden controls remains reachable through the unified StyleDialog
# (CS-05).
#
# ``_RESPONSIVE_COLLAPSE_PX`` is the smallest threshold (i.e. the
# width at or above which any optional cell is shown). Kept as a
# module-level alias so callers / tests have a single "is the row
# narrow?" sentinel.
_RESPONSIVE_THRESHOLDS_PX: tuple[tuple[str, int], ...] = (
    ("swatch",    240),
    ("leg",       280),
    ("ls_canvas", 320),
)
_RESPONSIVE_COLLAPSE_PX: int = _RESPONSIVE_THRESHOLDS_PX[0][1]


def _style_get(node: DataNode, key: str) -> Any:
    """Read a style value with the module default as a fallback."""
    return node.style.get(key, _DEFAULT_STYLE[key])


# =====================================================================
# Node filter normalisation
# =====================================================================

NodeFilter = Union[Sequence[NodeType], Callable[[DataNode], bool]]


def _make_predicate(node_filter: NodeFilter) -> Callable[[DataNode], bool]:
    """Turn ``node_filter`` (list[NodeType] | callable) into a predicate.

    The widget accepts either a list of allowed ``NodeType`` values or
    a free-form callable. A list is the common case (a tab restricts
    its sidebar to its own scan type); the callable form is for the
    Compare tab, which mixes types and groups them by category.
    """
    if callable(node_filter):
        return node_filter  # type: ignore[return-value]
    allowed = set(node_filter)

    def _pred(n: DataNode) -> bool:
        return n.type in allowed
    return _pred


# =====================================================================
# Sweep group detection
# =====================================================================

def _datanode_parents(
    graph: ProjectGraph, node_id: str,
) -> list[str]:
    """Return DataNode ancestor ids reachable through any OperationNode hops.

    A DataNode's *graph* parents are the OperationNodes that produced
    it. Walk one hop further up to reach the input DataNodes. For
    sweep grouping we care about which input DataNodes a candidate
    derived from, not which operation produced it.
    """
    direct_parents = graph.parents_of(node_id)
    out: list[str] = []
    for pid in direct_parents:
        node = graph.get_node(pid)
        if isinstance(node, DataNode):
            out.append(pid)
        elif isinstance(node, OperationNode):
            for grandparent in graph.parents_of(pid):
                gp_node = graph.get_node(grandparent)
                if isinstance(gp_node, DataNode):
                    out.append(grandparent)
    return out


# =====================================================================
# Widget
# =====================================================================

class ScanTreeWidget(tk.Frame):
    """The right-sidebar component (CS-04).

    See module docstring for the design model. The widget is a Frame
    so it can be packed/gridded directly into a tab's right-pane
    container.
    """

    # ------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------

    def __init__(
        self,
        parent: tk.Widget,
        graph: ProjectGraph,
        node_filter: NodeFilter,
        redraw_cb: Callable[..., None],
        send_to_compare_cb: Callable[[str], None] | None = None,
        style_dialog_cb: Callable[[str], None] | None = None,
        export_cb: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._graph: ProjectGraph = graph
        self._predicate: Callable[[DataNode], bool] = _make_predicate(
            node_filter
        )
        self._redraw_cb = redraw_cb
        self._send_to_compare_cb = send_to_compare_cb
        self._style_dialog_cb = style_dialog_cb
        self._export_cb = export_cb

        # View state.
        self._show_hidden = tk.BooleanVar(value=False)
        self._expanded_history: set[str] = set()
        # node_id → tk.Frame for the row (top-level, not history sub-frame).
        self._row_frames: dict[str, tk.Frame] = {}
        # node_id → tk.Frame for the history sub-frame (if expanded).
        self._history_frames: dict[str, tk.Frame] = {}
        # Sweep group key (parent DataNode id) → list of member ids.
        # Recomputed every full rebuild.
        self._sweep_groups: dict[str, list[str]] = {}
        # Set of node ids currently rendered as the *leader* of a sweep
        # group (to avoid creating a separate row for the same node).
        self._sweep_leaders: set[str] = set()
        # Per-row optional controls indexed by node id, used by the
        # responsive collapse logic (B-002). Each entry maps a name
        # ("swatch", "leg", "ls_canvas", "hist") to the widget that
        # should hide when the row narrows below ``_RESPONSIVE_COLLAPSE_PX``
        # — and to the anchor widget (``vis_cb``) the swatch needs for
        # correct re-insertion via ``pack(before=...)``.
        self._optional_row_widgets: dict[str, dict[str, tk.Widget]] = {}

        self._build_chrome()

        self._graph.subscribe(self._on_graph_event)
        self.bind("<Destroy>", self._on_destroy, add="+")

        self._rebuild()

    def _build_chrome(self) -> None:
        """Construct the widget's persistent UI scaffolding.

        The middle area is a vertically scrollable canvas of rows; the
        bottom area holds the "Show hidden" toggle. Both survive
        rebuilds (only the rows inside the canvas are torn down and
        recreated).
        """
        # Scrollable rows container.
        self._scroll_canvas = tk.Canvas(
            self, highlightthickness=0, borderwidth=0,
        )
        self._scroll_canvas.pack(side="top", fill="both", expand=True)

        self._rows_frame = tk.Frame(self._scroll_canvas)
        self._rows_window = self._scroll_canvas.create_window(
            (0, 0), window=self._rows_frame, anchor="nw",
        )

        def _on_inner_configure(_event=None):
            self._scroll_canvas.configure(
                scrollregion=self._scroll_canvas.bbox("all"),
            )
        self._rows_frame.bind("<Configure>", _on_inner_configure)

        # Bottom controls.
        self._footer = tk.Frame(self)
        self._footer.pack(side="bottom", fill="x")
        tk.Checkbutton(
            self._footer,
            text="Show hidden",
            variable=self._show_hidden,
            command=self._rebuild,
        ).pack(side="left", padx=4, pady=2)

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def unsubscribe(self) -> None:
        """Drop the graph subscription.

        Idempotent. Called automatically on widget ``<Destroy>``;
        provided publicly for tabs that want to detach the widget
        without destroying it.
        """
        self._graph.unsubscribe(self._on_graph_event)

    # ------------------------------------------------------------
    # Reactive event handler
    # ------------------------------------------------------------

    def _on_graph_event(self, event: GraphEvent) -> None:
        """Translate a graph event into the minimal UI update.

        For most events we do a targeted redraw of the affected row
        (cheap, avoids flicker). For structural changes — adds,
        commits/discards, edges — we rebuild the whole list because
        sweep grouping may need to be recomputed.
        """
        et = event.type
        # Structural events: rebuild everything.
        if et in (
            GraphEventType.NODE_ADDED,
            GraphEventType.NODE_COMMITTED,
            GraphEventType.NODE_DISCARDED,
            GraphEventType.EDGE_ADDED,
            GraphEventType.GRAPH_LOADED,
            GraphEventType.GRAPH_CLEARED,
        ):
            self._rebuild()
            return

        # Targeted updates.
        if et == GraphEventType.NODE_LABEL_CHANGED:
            self._refresh_row(event.node_id)
        elif et == GraphEventType.NODE_ACTIVE_CHANGED:
            # Hidden ↔ visible flip: a full rebuild keeps the row
            # ordering consistent (and respects "Show hidden").
            self._rebuild()
        elif et == GraphEventType.NODE_STYLE_CHANGED:
            self._refresh_row(event.node_id)

    # ------------------------------------------------------------
    # Listing & filtering
    # ------------------------------------------------------------

    def _candidate_nodes(self) -> list[DataNode]:
        """Return DataNodes that should be considered for display.

        Filters out OperationNodes and DISCARDED nodes; applies the
        ``node_filter`` predicate; respects ``active`` unless
        "Show hidden" is on. Returns insertion order — the dict is
        stable in 3.7+ so this gives deterministic ordering.
        """
        show_hidden = bool(self._show_hidden.get())
        out: list[DataNode] = []
        for node in self._graph.nodes.values():
            if not isinstance(node, DataNode):
                continue
            if node.state == NodeState.DISCARDED:
                continue
            if not self._predicate(node):
                continue
            if not node.active and not show_hidden:
                continue
            out.append(node)
        return out

    def _compute_sweep_groups(
        self, candidates: Sequence[DataNode],
    ) -> tuple[dict[str, list[str]], set[str]]:
        """Identify sweep groups among the visible candidates.

        A sweep group is 2+ PROVISIONAL DataNodes that share a single
        DataNode parent. Returns ``({parent_id: [member_ids]},
        {ids that are members of any group})``. The member set is
        used to suppress per-row entries for grouped nodes; the
        leader (lexicographically smallest id, for determinism)
        renders the group row.
        """
        cand_ids = {n.id for n in candidates}
        # Map each candidate's "data parent" to that candidate.
        by_parent: dict[str, list[str]] = {}
        for n in candidates:
            if n.state != NodeState.PROVISIONAL:
                continue
            parents = _datanode_parents(self._graph, n.id)
            for pid in parents:
                by_parent.setdefault(pid, []).append(n.id)

        groups: dict[str, list[str]] = {}
        members: set[str] = set()
        for pid, kids in by_parent.items():
            kids_visible = [k for k in kids if k in cand_ids]
            if len(kids_visible) >= 2:
                groups[pid] = sorted(kids_visible)
                members.update(kids_visible)
        return groups, members

    # ------------------------------------------------------------
    # Rebuild
    # ------------------------------------------------------------

    def _rebuild(self) -> None:
        """Tear down and recreate every row from the current graph.

        Cheaper paths exist (insert one row, remove one row) but a
        full rebuild keeps sweep grouping coherent and is fast enough
        for the dataset counts this widget is designed for (tens, not
        thousands).
        """
        for child in list(self._rows_frame.winfo_children()):
            child.destroy()
        self._row_frames.clear()
        self._history_frames.clear()
        self._optional_row_widgets.clear()

        candidates = self._candidate_nodes()
        self._sweep_groups, self._sweep_leaders = (
            self._compute_sweep_groups(candidates)
        )

        rendered_for_group: set[str] = set()
        for node in candidates:
            if node.id in self._sweep_leaders:
                # Each group renders exactly once, on its first member.
                # Identify the group this id belongs to.
                group_key = self._group_key_of(node.id)
                if group_key in rendered_for_group:
                    continue
                rendered_for_group.add(group_key)
                self._build_sweep_row(group_key)
            else:
                self._build_node_row(node)

    def _group_key_of(self, node_id: str) -> str:
        """Return the parent DataNode id that defines this node's group."""
        for parent_id, members in self._sweep_groups.items():
            if node_id in members:
                return parent_id
        # Defensive default — shouldn't reach here when called via _rebuild.
        return node_id

    # ------------------------------------------------------------
    # Per-row construction
    # ------------------------------------------------------------

    def _build_node_row(self, node: DataNode) -> None:
        """Construct the persistent row for a single (non-grouped) node."""
        row = tk.Frame(self._rows_frame)
        row.pack(side="top", fill="x", padx=2, pady=1)
        self._row_frames[node.id] = row
        self._populate_node_row(row, node)

    def _populate_node_row(self, row: tk.Frame, node: DataNode) -> None:
        """Fill a row frame with the per-node controls.

        The row layout follows CS-04 §6.1 as extended by Phase 4n.
        Always-visible minimum: ``state``, ``☑`` visibility, ``label``,
        ``⌥n`` provenance count (Phase 4n CS-26 promotion),
        ``⚙`` gear, ``→`` Send-to-Compare (Phase 4n CS-27), ``✕``.
        Optional set: ``swatch``, ``leg``, ``ls_canvas``, tracked in
        ``self._optional_row_widgets[node.id]`` so the responsive
        layout helper can show / hide each one independently as the
        row crosses its threshold (CS-26 graduated reveal — see
        ``_RESPONSIVE_THRESHOLDS_PX``).
        """
        for child in row.winfo_children():
            child.destroy()
        # Drop any per-row tracking for this id; we'll repopulate as we
        # rebuild the controls. Without this, a refresh after
        # node-style change would leak stale widget references.
        self._optional_row_widgets.pop(node.id, None)

        # State indicator (always visible).
        state_text = "🔒" if node.state == NodeState.COMMITTED else "⋯"
        state_lbl = tk.Label(row, text=state_text, width=2)
        state_lbl.pack(side="left")

        # Colour swatch (optional — collapses on narrow rows).
        swatch_color = _style_get(node, "color")
        swatch = tk.Button(
            row, bg=swatch_color, width=2, relief=tk.RAISED,
            cursor="hand2",
            command=lambda nid=node.id: self._on_pick_color(nid),
        )
        swatch.pack(side="left", padx=2)

        # Visibility checkbox (always visible) — style.visible.
        vis_var = tk.BooleanVar(value=bool(_style_get(node, "visible")))
        vis_cb = tk.Checkbutton(
            row, variable=vis_var,
            command=lambda nid=node.id, v=vis_var: self._graph.set_style(
                nid, {"visible": bool(v.get())},
            ),
        )
        vis_cb.pack(side="left")

        # Label (double-click to edit in-place).
        label = tk.Label(row, text=node.label, anchor="w")
        label.pack(side="left", fill="x", expand=True, padx=(2, 4))
        label.bind(
            "<Double-Button-1>",
            lambda _e, nid=node.id, lbl=label, frm=row:
                self._begin_label_edit(nid, lbl, frm),
        )

        # ✕ — discard provisional / soft-hide committed.
        x_btn = tk.Button(
            row, text="✕", relief=tk.FLAT, cursor="hand2",
            command=lambda nid=node.id: self._on_x_clicked(nid),
        )
        x_btn.pack(side="right", padx=(2, 0))

        # → — Send-to-Compare (Phase 4n CS-27). Disabled when no
        # callback is wired (deferred-tab convention shared with
        # Export…) or when the row is provisional (commit-or-discard
        # discipline before a spectrum can leak into a downstream
        # tab). Sits between ⚙ and ✕ so the right cluster reads
        # ``[⌥n] [⚙] [→] [✕]`` left-to-right.
        compare_state = ("normal" if (
            self._send_to_compare_cb is not None
            and node.state == NodeState.COMMITTED
        ) else "disabled")
        compare_btn = tk.Button(
            row, text="→", relief=tk.FLAT, cursor="hand2",
            state=compare_state,
            command=lambda nid=node.id: self._on_send_to_compare_clicked(nid),
        )
        compare_btn.pack(side="right", padx=(2, 0))

        # ⚙ — style dialog hand-off.
        gear_btn = tk.Button(
            row, text="⚙", relief=tk.FLAT, cursor="hand2",
            command=lambda nid=node.id: self._on_gear_clicked(nid),
        )
        gear_btn.pack(side="right", padx=(2, 0))

        # ⌥n — history expand toggle. Always visible after CS-26 so
        # the provenance affordance doesn't disappear on a narrow
        # sidebar; no longer in the responsive optional set.
        chain_len = self._provenance_op_count(node.id)
        hist_btn = tk.Button(
            row, text=f"⌥{chain_len}", relief=tk.FLAT, cursor="hand2",
            command=lambda nid=node.id: self._toggle_history(nid),
        )
        hist_btn.pack(side="right", padx=(2, 0))

        # Linestyle canvas.
        ls_canvas = self._build_linestyle_canvas(row, node)
        ls_canvas.pack(side="right", padx=(2, 0))

        # Legend toggle (✓/–).
        leg_var = tk.BooleanVar(value=bool(_style_get(node, "in_legend")))
        leg_btn = tk.Button(row, width=2, relief=tk.FLAT)

        def _refresh_leg(_b=leg_btn, _v=leg_var):
            _b.config(
                text="✓" if _v.get() else "–",
                fg="#006600" if _v.get() else "#999999",
            )

        def _toggle_leg(nid=node.id, _b=leg_btn, _v=leg_var):
            new = not _v.get()
            _v.set(new)
            _refresh_leg()
            self._graph.set_style(nid, {"in_legend": bool(new)})
        leg_btn.config(command=_toggle_leg)
        _refresh_leg()
        leg_btn.pack(side="right", padx=(2, 0))

        # Right-click context menu (any row, including label area).
        for w in (row, label, state_lbl):
            w.bind(
                "<Button-3>",
                lambda e, nid=node.id: self._show_context_menu(e, nid),
            )

        # Track optional controls so the responsive collapse logic can
        # find them by name (B-002, Phase 4d; thresholds extended in
        # Phase 4n CS-26). ``hist`` is no longer optional — it sits in
        # the always-visible minimum after CS-26 — so it is omitted
        # from this dict. The ``vis_cb`` reference is stored as the
        # swatch's re-pack anchor: without ``before=vis_cb`` a
        # re-packed swatch lands on the wrong side of the label, which
        # has ``fill="x", expand=True``.
        self._optional_row_widgets[node.id] = {
            "swatch":     swatch,
            "leg":        leg_btn,
            "ls_canvas":  ls_canvas,
            "vis_cb":     vis_cb,
        }

        # Bind row width changes to the responsive layout helper. The
        # bind is per row frame so the helper knows which row to
        # apply the rule to. Configure also fires on the very first
        # geometry pass, so this doubles as the initial calibration.
        row.bind(
            "<Configure>",
            lambda _e, nid=node.id, frm=row:
                self._apply_responsive_layout(nid, frm),
            add="+",
        )

        # Re-attach history sub-frame if currently expanded.
        if node.id in self._expanded_history:
            self._render_history(node.id)

    # ------------------------------------------------------------
    # Responsive row collapse (B-002, Phase 4d)
    # ------------------------------------------------------------

    def _apply_responsive_layout(
        self, node_id: str, row: tk.Frame,
    ) -> None:
        """Hide / re-pack optional controls based on row width.

        Phase 4n CS-26 graduated reveal: each cell in
        ``_RESPONSIVE_THRESHOLDS_PX`` is mapped iff the row is at
        least its threshold wide. Below the smallest threshold no
        optional cells are shown; the always-visible minimum
        (state, ☑, label, ⌥n, ⚙, →, ✕) keeps the row usable.

        The right-side optional widgets share a delicate ordering
        invariant: when both ``leg`` and ``ls_canvas`` are mapped the
        canonical visual order is ``leg ls_canvas`` (i.e. ``leg`` is
        leftmost). Naively packing one when the other is already
        mapped would land the new one on the wrong side, so the
        helper reflows BOTH right-side optional cells whenever the
        right-side mapped set is about to change. This is idempotent
        at steady state: when the desired mapped set already matches
        the actual mapped set, no pack / pack_forget calls fire.

        ``swatch`` is re-inserted with ``before=vis_cb`` because a
        plain ``side="left"`` would place it after ``label`` (which
        has ``fill="x", expand=True`` and consumes remaining left
        space).
        """
        widgets = self._optional_row_widgets.get(node_id)
        if widgets is None:
            return
        try:
            width = row.winfo_width()
        except tk.TclError:
            return
        # Tk reports width=1 before the widget is realised in
        # geometry; ignore those Configure events so we don't
        # spuriously collapse a row that hasn't been laid out yet.
        if width <= 1:
            return

        thresholds = dict(_RESPONSIVE_THRESHOLDS_PX)
        swatch    = widgets.get("swatch")
        vis_cb    = widgets.get("vis_cb")
        leg       = widgets.get("leg")
        ls_canvas = widgets.get("ls_canvas")

        def _is_mapped(w: tk.Widget | None) -> bool:
            if w is None:
                return False
            try:
                return bool(w.winfo_ismapped())
            except tk.TclError:
                return False

        want_swatch = width >= thresholds["swatch"]
        want_leg    = width >= thresholds["leg"]
        want_ls     = width >= thresholds["ls_canvas"]

        have_swatch = _is_mapped(swatch)
        have_leg    = _is_mapped(leg)
        have_ls     = _is_mapped(ls_canvas)

        # Left side — swatch is independent of right-side ordering.
        if have_swatch and not want_swatch and swatch is not None:
            try:
                swatch.pack_forget()
            except tk.TclError:
                pass
        elif (want_swatch and not have_swatch
                and swatch is not None and vis_cb is not None):
            try:
                swatch.pack(side="left", padx=2, before=vis_cb)
            except tk.TclError:
                pass

        # Right side — reflow ``leg`` and ``ls_canvas`` together when
        # the desired set differs from the actual set, otherwise skip
        # entirely (idempotent at steady state).
        right_changed = (want_leg, want_ls) != (have_leg, have_ls)
        if right_changed:
            for w in (leg, ls_canvas):
                if w is None:
                    continue
                try:
                    if w.winfo_ismapped():
                        w.pack_forget()
                except tk.TclError:
                    pass
            # Pack in the order ``ls_canvas`` then ``leg`` so each
            # ``side="right"`` call lands to the left of the
            # previously packed widget — matching the canonical
            # visual order ``leg · ls_canvas · ⌥n · ⚙ · → · ✕``.
            if want_ls and ls_canvas is not None:
                try:
                    ls_canvas.pack(side="right", padx=(2, 0))
                except tk.TclError:
                    pass
            if want_leg and leg is not None:
                try:
                    leg.pack(side="right", padx=(2, 0))
                except tk.TclError:
                    pass

    # ------------------------------------------------------------
    # Sweep group row
    # ------------------------------------------------------------

    def _build_sweep_row(self, parent_id: str) -> None:
        """Build a single collapsed row for a sweep group.

        The row currently shows the count of variants and offers a
        "✕all" gesture (discard all members). Expanding into individual
        variant editing is covered by a future refinement; for now the
        user can hold Shift+Click on the count to expand into per-row
        rendering by toggling "Show hidden" + node selection in the
        graph (Phase 4 will design the variant editor in full).
        """
        members = self._sweep_groups.get(parent_id, [])
        if not members:
            return

        row = tk.Frame(self._rows_frame)
        row.pack(side="top", fill="x", padx=2, pady=1)
        # Reuse the leader's row frame for refresh dispatch.
        leader_id = members[0]
        self._row_frames[leader_id] = row

        try:
            parent_node = self._graph.get_node(parent_id)
            parent_label = (parent_node.label
                            if isinstance(parent_node, DataNode)
                            else parent_id)
        except KeyError:
            parent_label = parent_id

        tk.Label(row, text="⋯", width=2).pack(side="left")
        tk.Label(
            row,
            text=f"{parent_label} · sweep ({len(members)} variants)",
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(2, 4))

        tk.Button(
            row, text="✕all", relief=tk.FLAT, cursor="hand2",
            command=lambda ids=tuple(members): self._discard_many(ids),
        ).pack(side="right", padx=(2, 0))

    def _discard_many(self, node_ids: Iterable[str]) -> None:
        for nid in node_ids:
            try:
                self._graph.discard_node(nid)
            except (KeyError, ValueError):
                # Sibling already discarded or removed: ignore.
                continue

    # ------------------------------------------------------------
    # Linestyle canvas
    # ------------------------------------------------------------

    def _build_linestyle_canvas(
        self, parent: tk.Widget, node: DataNode,
    ) -> tk.Canvas:
        W, H = 38, 16
        cv = tk.Canvas(
            parent, width=W, height=H,
            bd=1, relief=tk.SUNKEN, bg="white",
            highlightthickness=0, cursor="hand2",
        )

        def _draw():
            cv.delete("all")
            ls   = _style_get(node, "linestyle")
            clr  = _style_get(node, "color")
            lw   = max(0.5, float(_style_get(node, "linewidth")))
            dash = _LS_DASH.get(ls, ())
            kwargs: dict[str, Any] = {
                "fill": clr, "width": lw, "capstyle": "round",
            }
            if dash:
                kwargs["dash"] = dash
            cv.create_line(4, H // 2, W - 4, H // 2, **kwargs)

        def _cycle(_event=None):
            cur = _style_get(node, "linestyle")
            idx = _LS_CYCLE.index(cur) if cur in _LS_CYCLE else 0
            nxt = _LS_CYCLE[(idx + 1) % len(_LS_CYCLE)]
            self._graph.set_style(node.id, {"linestyle": nxt})
            # The graph event will trigger a row refresh which redraws
            # this canvas, so no explicit _draw() needed here.

        cv.bind("<Button-1>", _cycle)
        _draw()
        return cv

    # ------------------------------------------------------------
    # Per-row mutations
    # ------------------------------------------------------------

    def _on_pick_color(self, node_id: str) -> None:
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return
        if not isinstance(node, DataNode):
            return
        current = _style_get(node, "color")
        result = colorchooser.askcolor(
            color=current, title="Pick colour", parent=self,
        )
        if result and result[1]:
            self._graph.set_style(node_id, {"color": result[1]})

    def _on_x_clicked(self, node_id: str) -> None:
        """Discard if provisional, soft-hide if committed.

        Per CS-04 §6.1: ✕ on a committed node sets ``active=False``;
        it does not delete the node. The "Show hidden" toggle reveals
        such nodes again.
        """
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return
        if not isinstance(node, DataNode):
            return
        if node.state == NodeState.PROVISIONAL:
            self._graph.discard_node(node_id)
        elif node.state == NodeState.COMMITTED:
            self._graph.set_active(node_id, False)
        # DISCARDED rows aren't rendered; this branch is unreachable.

    def _on_gear_clicked(self, node_id: str) -> None:
        if self._style_dialog_cb is None:
            _log.info(
                "ScanTreeWidget: gear clicked on %s but no "
                "style_dialog_cb wired (phase 3 work)",
                node_id,
            )
            return
        self._style_dialog_cb(node_id)

    def _on_send_to_compare_clicked(self, node_id: str) -> None:
        """Handle a click on the per-row → Send-to-Compare button.

        Phase 4n CS-27. Disabled-button protection means a callback
        is wired and the row is COMMITTED — but we re-check anyway
        because the row state could change between row build and
        click without a rebuild firing (defensive).
        """
        if self._send_to_compare_cb is None:
            return
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return
        if not isinstance(node, DataNode):
            return
        if node.state != NodeState.COMMITTED:
            return
        self._send_to_compare_cb(node_id)

    # ------------------------------------------------------------
    # In-place label editing
    # ------------------------------------------------------------

    def _begin_label_edit(
        self, node_id: str, label_widget: tk.Label, row_frame: tk.Frame,
    ) -> None:
        """Replace the label widget with an Entry for in-place editing.

        Enter or focus loss commits via ``graph.set_label``. Escape
        cancels without writing back. The widget stops doing anything
        special once the row rebuilds in response to the resulting
        ``NODE_LABEL_CHANGED`` event.
        """
        current = label_widget.cget("text")
        # Phase 4j friction #1: pass ``master=row_frame`` explicitly so
        # the StringVar binds to the same Tk interpreter as the Entry.
        # Without it, ``tk.StringVar(value=...)`` falls back to
        # ``tkinter._default_root``, which can be a different root when
        # multiple test modules each call ``tk.Tk()`` at module-import
        # time. The mismatch makes the textvariable binding silently
        # no-op so the rename Entry renders empty even though
        # ``value=current`` was supplied. Defence-in-depth fix; users
        # never hit it in single-Tk production paths but it would
        # break any future plugin tab that spawns its own Tk root.
        entry_var = tk.StringVar(master=row_frame, value=current)
        entry = tk.Entry(row_frame, textvariable=entry_var)

        # Replace the label inline. B-004 (Phase 4c) followup: passing
        # ``before=label_widget`` to ``entry.pack`` after the label has
        # already been ``pack_forget``-ed raises
        # ``TclError: ... isn't packed``, which is why rename has been
        # silently broken since Phase 2 from both gestures (double
        # click and the Rename context menu entry). Pack with
        # ``side="left"`` only — the row's layout puts vis_cb to our
        # left and the right-side controls all use ``side="right"``,
        # so the entry naturally fills the slot the label vacated.
        label_widget.pack_forget()
        entry.pack(side="left", fill="x", expand=True)
        entry.focus_set()
        entry.select_range(0, "end")

        committed = {"done": False}

        def _commit(_event=None):
            if committed["done"]:
                return
            committed["done"] = True
            new_label = entry_var.get()
            try:
                self._graph.set_label(node_id, new_label)
            except (KeyError, TypeError, ValueError):
                # Defensive: stale row, or node went away. Just
                # rebuild — the label handler is best-effort.
                pass
            self._rebuild()

        def _cancel(_event=None):
            if committed["done"]:
                return
            committed["done"] = True
            self._rebuild()

        entry.bind("<Return>",   _commit)
        entry.bind("<FocusOut>", _commit)
        entry.bind("<Escape>",   _cancel)

    # ------------------------------------------------------------
    # History expansion
    # ------------------------------------------------------------

    def _provenance_op_count(self, node_id: str) -> int:
        """Number of OperationNodes in the provenance chain of a node."""
        try:
            chain = self._graph.provenance_chain(node_id)
        except KeyError:
            return 0
        return sum(1 for n in chain if isinstance(n, OperationNode))

    def _toggle_history(self, node_id: str) -> None:
        # B-001 (Phase 4c): only one history pane is open at a time
        # across the widget. Toggling on a row that is already
        # expanded collapses it; toggling on any other row collapses
        # the previously expanded pane before opening the new one.
        if node_id in self._expanded_history:
            self._expanded_history.discard(node_id)
            frame = self._history_frames.pop(node_id, None)
            if frame is not None:
                frame.destroy()
            return

        for other_id in list(self._expanded_history):
            self._expanded_history.discard(other_id)
            other_frame = self._history_frames.pop(other_id, None)
            if other_frame is not None:
                other_frame.destroy()

        self._expanded_history.add(node_id)
        self._render_history(node_id)

    def _render_history(self, node_id: str) -> None:
        """Render the inline provenance chain below the row.

        B-001 (Phase 4c): the sub-frame is packed with ``after=row`` so
        it appears immediately below the clicked row, not at the end
        of the scroll area. Tk's pack manager does support
        ``after=`` — the previous implementation that relied on the
        next full rebuild to restore ordering was wrong.
        """
        row = self._row_frames.get(node_id)
        if row is None:
            return
        try:
            chain = self._graph.provenance_chain(node_id)
        except KeyError:
            return

        # Replace any previous sub-frame for this node so the
        # ``_refresh_row → _populate_node_row → _render_history``
        # chain doesn't leak orphan history frames after a label or
        # style update.
        old = self._history_frames.pop(node_id, None)
        if old is not None:
            old.destroy()

        sub = tk.Frame(self._rows_frame)
        sub.pack(after=row, side="top", fill="x", padx=(20, 4), pady=(0, 2))
        self._history_frames[node_id] = sub

        for ancestor in chain:
            text = self._format_history_entry(ancestor)
            lbl = tk.Label(
                sub, text=text, anchor="w", fg="#444444",
                cursor="hand2",
            )
            lbl.pack(side="top", fill="x")
            lbl.bind(
                "<Button-1>",
                lambda _e, nid=ancestor.id: self._on_history_click(nid),
            )

    def _format_history_entry(
        self, ancestor: Union[DataNode, OperationNode],
    ) -> str:
        if isinstance(ancestor, OperationNode):
            return (
                f"  ↳ {ancestor.type.name.lower()} "
                f"[{ancestor.engine} {ancestor.engine_version}]"
            )
        # DataNode
        return f"  ↳ {ancestor.label}"

    def _on_history_click(self, ancestor_id: str) -> None:
        """Preview an ancestor on the plot via redraw_cb(focus=...)."""
        try:
            self._redraw_cb(focus=ancestor_id)
        except TypeError:
            # redraw_cb may not accept focus= in early integrations;
            # degrade to a regular redraw rather than swallow silently.
            self._redraw_cb()

    # ------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------

    def _show_context_menu(self, event: tk.Event, node_id: str) -> None:
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return
        if not isinstance(node, DataNode):
            return

        menu = tk.Menu(self, tearoff=0)
        is_prov = node.state == NodeState.PROVISIONAL
        is_committed = node.state == NodeState.COMMITTED

        menu.add_command(
            label="Commit",
            state=("normal" if is_prov else "disabled"),
            command=lambda nid=node_id: self._safely(
                self._graph.commit_node, nid),
        )
        menu.add_command(
            label="Discard",
            state=("normal" if is_prov else "disabled"),
            command=lambda nid=node_id: self._safely(
                self._graph.discard_node, nid),
        )
        menu.add_separator()
        menu.add_command(
            label="Send to Compare",
            state=("normal" if (is_committed
                                 and self._send_to_compare_cb is not None)
                   else "disabled"),
            command=lambda nid=node_id: (
                self._send_to_compare_cb(nid)
                if self._send_to_compare_cb else None
            ),
        )
        menu.add_command(
            label="Rename",
            command=lambda nid=node_id: self._begin_rename_via_menu(nid),
        )
        # Export… (CS-17, Phase 4f). Available only on committed nodes
        # — provisional rows force commit-or-discard discipline before
        # the spectrum can leak into a downstream file. Disabled (not
        # hidden) so the user can see the affordance and learn the
        # rule, mirroring the Discard / Commit entries above.
        menu.add_command(
            label="Export…",
            state=("normal" if (is_committed
                                 and self._export_cb is not None)
                   else "disabled"),
            command=lambda nid=node_id: (
                self._export_cb(nid) if self._export_cb else None
            ),
        )
        menu.add_command(
            label="Show history",
            command=lambda nid=node_id: self._toggle_history(nid),
        )
        if node.active:
            menu.add_command(
                label="Hide",
                command=lambda nid=node_id: self._graph.set_active(nid, False),
            )
        else:
            menu.add_command(
                label="Show",
                command=lambda nid=node_id: self._graph.set_active(nid, True),
            )
        menu.add_separator()
        menu.add_command(
            label="Duplicate",
            command=lambda nid=node_id: self._duplicate_node(nid),
        )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _safely(self, fn: Callable[..., Any], *args: Any) -> None:
        """Call a graph method, swallowing benign errors on stale ids."""
        try:
            fn(*args)
        except (KeyError, ValueError, TypeError):
            pass

    def _begin_rename_via_menu(self, node_id: str) -> None:
        """Trigger the in-place rename Entry from the context-menu Rename.

        Per CS-04 §"Context menu". B-004 (Phase 4c) regression-tests
        this routing — both this method and the label's
        ``<Double-Button-1>`` binding must end up at
        ``_begin_label_edit`` so the user sees identical behaviour
        from either gesture.
        """
        row = self._row_frames.get(node_id)
        if row is None:
            return
        # Find the label child (only one Label in our row layout that
        # contains the node label — the "anchor=w" one). Walk children.
        for child in row.winfo_children():
            if (isinstance(child, tk.Label)
                    and child.cget("text") not in ("🔒", "⋯")):
                self._begin_label_edit(node_id, child, row)
                return

    def _duplicate_node(self, node_id: str) -> None:
        """Clone a node and re-wire its parents to the clone.

        Per the Phase 1 design decision, ``graph.clone_node`` does
        NOT add edges; the caller is responsible. We replicate every
        direct parent edge of the source so the clone sits in the
        same lineage and is discoverable via ``provenance_chain``.
        """
        try:
            new_id = self._graph.clone_node(node_id)
        except (KeyError, TypeError):
            return
        for parent_id in self._graph.parents_of(node_id):
            try:
                self._graph.add_edge(parent_id, new_id)
            except (KeyError, ValueError):
                continue

    # ------------------------------------------------------------
    # Targeted refresh
    # ------------------------------------------------------------

    def _refresh_row(self, node_id: str | None) -> None:
        """Repaint a single row in place, without disturbing siblings.

        Used for label and style updates — events that don't change
        which rows exist or how they group, just the contents of one
        row. Falls back to a full rebuild if the row isn't present
        (e.g. the node became visible after a hidden→shown flip).
        """
        if node_id is None:
            return
        row = self._row_frames.get(node_id)
        if row is None:
            self._rebuild()
            return
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            self._rebuild()
            return
        if not isinstance(node, DataNode):
            return
        # If this id is part of a sweep group leader row, the row
        # holds aggregate content, not per-node — easier to rebuild.
        if any(node_id in members
               for members in self._sweep_groups.values()):
            self._rebuild()
            return
        self._populate_node_row(row, node)

    # ------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------

    def _on_destroy(self, _event: tk.Event) -> None:
        # The widget itself is being destroyed; drop the subscription
        # so the graph doesn't hold a callback to a dead Tk frame.
        self.unsubscribe()
