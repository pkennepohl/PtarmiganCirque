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
from tkinter import colorchooser, font as tkfont
from typing import Any, Callable, Iterable, Sequence, Union

from graph import GraphEvent, GraphEventType, ProjectGraph
from nodes import DataNode, NodeState, NodeType, OperationNode
from tooltip import Tooltip

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
# Phase 4w (CS-47): per-cell minimum natural widths. Documented
# vocabulary of every row cell so a sidebar audit has a single source
# of truth. The cumulative sum of always-visible cell mins plus a
# floor for the label cell gives ``_SIDEBAR_MIN_WIDTH_PX``; the
# optional cells contribute to ``_RESPONSIVE_THRESHOLDS_PX`` (whose
# integer values are pinned by the existing test suite at 240 / 280 /
# 320 — see ``test_swatch_revealed_first_at_smallest_threshold`` &
# siblings — and so are constructed by hand below rather than summed
# from this dict). Adding a cell to a row means listing it here too.
_CELL_MIN_PX: dict[str, int] = {
    "state":      18,   # 🔒/⋯ — width=2 char Label
    "swatch":     24,   # colour Button width=2 (optional, P1)
    "vis_cb":     22,   # ☑ Checkbutton, no text
    "row_toggle": 22,   # Phase 4w (CS-48): [~] / placeholder slot
    "label":      56,   # floor: ~8 chars at TkDefaultFont
    "leg":        22,   # ✓/– Button width=2 (optional, P2)
    "ls_canvas":  38,   # 38×16 linestyle canvas (optional, P3)
    "hist":       28,   # ⌥n Button (always visible since CS-26)
    "gear":       22,   # ⚙ Button
    "compare":    22,   # → Button
    "commit":     22,   # 🔒 commit Button (provisional rows only)
    "x":          22,   # ✕ Button
}

_RESPONSIVE_THRESHOLDS_PX: tuple[tuple[str, int], ...] = (
    ("swatch",    240),
    ("leg",       280),
    ("ls_canvas", 320),
)
_RESPONSIVE_COLLAPSE_PX: int = _RESPONSIVE_THRESHOLDS_PX[0][1]

# Phase 4w (CS-47): pinned floor for the right-pane sidebar. Set to
# the same integer as the smallest responsive threshold so the
# PanedWindow's ``minsize`` and the responsive-collapse threshold
# stay in lock-step — narrowing the sash never produces a row that
# can't render at least the always-visible minimum. ``UVVisTab``
# reads this value when configuring ``body.add(sidebar_pane,
# minsize=_SIDEBAR_MIN_WIDTH_PX)``.
_SIDEBAR_MIN_WIDTH_PX: int = _RESPONSIVE_COLLAPSE_PX

# Phase 4q (CS-33): label truncation cap. Long chains of UV/Vis ops
# accumulate suffixes ("NiAqua · baseline (linear) · norm (peak)" etc.)
# and the row's natural width can exceed the canvas, causing
# horizontal overflow even with CS-30's canvas-driven responsive
# helper in place. Truncating the displayed label at a uniform
# character cap keeps every row's column structure consistent (the
# user-flagged invariant from Phase 4p friction #3); the full label
# remains accessible via a hover tooltip and the existing in-place
# rename gesture (double-click, which now reads the full label from
# the graph rather than the widget's truncated text).
#
# Phase 4w (CS-47) makes the cap responsive to the actual sidebar
# width via ``_label_char_capacity``: a wide sidebar shows more of
# the label without truncation, a narrow sidebar shows less. The
# constant below is the static fallback used when canvas width or
# font metrics are unavailable (unrealised geometry, headless
# tests). The CS-33 invariants on ``_truncate_label`` (signature,
# default cap, ``text[:max-1] + "…"`` shape) are preserved.
_LABEL_MAX_CHARS: int = 32

# Phase 4w (CS-47): clamps for the dynamic label cap. The floor keeps
# at least eight characters visible even on the narrowest realised
# sidebar (so a name like "spectrum" is never cut to nothing); the
# ceil prevents a very wide sidebar from disabling truncation
# entirely (a 1500-char "label" is a graph-data bug, not a
# rendering opportunity).
_LABEL_CHAR_FLOOR: int = 8
_LABEL_CHAR_CEIL: int = 64

# Phase 4r (CS-35): visual nesting indent for member rows that render
# below a parent / group leader. Phase 4ac (CS-54) removed the
# automatic sweep-grouping of PROVISIONAL siblings (CS-32) — every
# DataNode now renders as its own standalone row regardless of
# whether siblings share an op_type. The constant + ``indent_px``
# kwarg on ``_build_node_row`` survive Phase 4ac because Phase 4ad's
# user-driven ``NODE_GROUP`` container (deferred register entry) will
# reuse the same pack-arg pass-through to nest its members under the
# group row.
_SWEEP_MEMBER_INDENT_PX: int = 16


def _truncate_label(text: str, max_chars: int = _LABEL_MAX_CHARS) -> str:
    """Cap a label at ``max_chars`` characters, suffixing ``…`` if cut.

    Pure helper so the unit tests don't need a Tk root. Returns
    ``text`` unchanged when ``len(text) <= max_chars``; otherwise
    returns ``text[:max_chars - 1] + "…"`` so the total displayed
    length is exactly ``max_chars``. ``max_chars`` must be at least
    1; the caller is trusted (this is internal).
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "…"


def _label_char_capacity(
    canvas_width_px: int,
    avg_char_px: int,
    overhead_px: int,
) -> int:
    """Compute the dynamic label-character cap for a given sidebar width.

    Phase 4w (CS-47). The static ``_LABEL_MAX_CHARS = 32`` cap was
    fine for "narrow but readable" sidebars but wastes pixels when
    the user widens the sash to 600 px and is too generous when the
    user narrows it to 240 px. The dynamic cap adapts: more pixels
    means more characters, fewer pixels means fewer.

    Inputs (all in pixels for the canvas dimension; ``avg_char_px`` is
    a font-metric measurement):

    * ``canvas_width_px`` — current sidebar canvas width.
    * ``avg_char_px``     — average character width for the label
      font, e.g. ``font.measure("M")`` or
      ``font.measure("ABCDEFGHIJabcdefghij") // 20``.
    * ``overhead_px``     — sum of always-visible non-label cells
      plus per-row padding, i.e. how much pixel real-estate the row
      consumes before the label cell starts.

    The returned cap is clamped to ``[_LABEL_CHAR_FLOOR,
    _LABEL_CHAR_CEIL]``. When the sidebar is unrealised
    (``canvas_width_px <= 1``), font metrics are unavailable
    (``avg_char_px <= 0``), or overhead exceeds the available width,
    the helper falls back to ``_LABEL_MAX_CHARS`` so the existing
    static-cap behaviour is preserved at construction time and in
    headless test environments where geometry never settles.
    """
    if canvas_width_px <= 1 or avg_char_px <= 0:
        return _LABEL_MAX_CHARS
    available = canvas_width_px - overhead_px
    if available <= 0:
        return _LABEL_MAX_CHARS
    chars = available // avg_char_px
    return max(_LABEL_CHAR_FLOOR, min(_LABEL_CHAR_CEIL, chars))


# Phase 4z (CS-51): the always-visible cell vocabulary, lifted out of
# ``_label_overhead_px`` so the pure helpers below can share it. Order
# is informative only — the sum is order-independent. Listing every
# always-visible cell from the row spec (CS-04 §6.1, CS-26's promotion
# of ``hist`` into the always-visible set, and CS-48's ``row_toggle``).
_ALWAYS_VISIBLE_CELLS: tuple[str, ...] = (
    "state", "vis_cb", "row_toggle",
    "hist", "gear", "compare", "x",
)

# Phase 4z (CS-51): per-row pixel slack added on top of the per-cell
# minimums to cover inter-cell padding (each ``pack(padx=2)`` etc.).
# Lifted from the historical ``_label_overhead_px`` body where it
# lived as the literal ``+ 30``. Pinned by
# ``test_compute_label_overhead_no_optional_cells_matches_phase_4w``
# below so the no-args path stays byte-equivalent to Phase 4w.
_OVERHEAD_SLACK_PX: int = 30


def _compute_label_overhead_px(
    visible_optional_cells: Iterable[str] = (),
) -> int:
    """Pixels consumed by non-label cells at a given visibility set.

    Phase 4z (CS-51). The pure successor to the static
    ``_label_overhead_px`` instance method's body. Returns
    ``sum(_CELL_MIN_PX[c] for c in always_visible_cells +
    visible_optional_cells) + _OVERHEAD_SLACK_PX``.

    Inputs:

    * ``visible_optional_cells`` — names of optional cells that will
      be packed into the row at the width under consideration. Pass
      ``()`` (the default) to get the always-visible-only baseline,
      which matches the Phase 4w behaviour byte-for-byte (186 px).
      Names must come from ``_RESPONSIVE_THRESHOLDS_PX`` ("swatch",
      "leg", "ls_canvas") — the helper does NOT validate, it just
      indexes ``_CELL_MIN_PX``. Unknown names raise ``KeyError`` so
      a typo at the call site fails loudly.

    Pure (no Tk dependencies). Used by ``_label_overhead_px`` to make
    the dynamic label cap aware of which optional cells are about to
    be revealed at the current canvas width — CS-26 reveals an
    optional cell at its threshold (e.g. swatch at 240 px) without
    growing the canvas, so without this widening the label cap stays
    sized for the swatch-absent state and the right-side cells (✕)
    fall off the row's right edge. Phase 4x friction #1 reproduction.
    """
    base = sum(_CELL_MIN_PX[c] for c in _ALWAYS_VISIBLE_CELLS)
    optional = sum(_CELL_MIN_PX[c] for c in visible_optional_cells)
    return base + optional + _OVERHEAD_SLACK_PX


def _visible_optional_cells_for_width(width_px: int) -> tuple[str, ...]:
    """Names of optional cells revealed at ``width_px`` per CS-26.

    Phase 4z (CS-51). Walks ``_RESPONSIVE_THRESHOLDS_PX`` (ascending
    by threshold by construction) and returns the cell names whose
    thresholds are ``<= width_px``. Returned in threshold-ascending
    order. Returns ``()`` when ``width_px < _RESPONSIVE_COLLAPSE_PX``
    (no optional cells visible). Pure helper — does not touch any
    widget state.

    Mirrors ``_apply_responsive_layout``'s reveal logic exactly:
    ``want_<cell> = width >= thresholds[<cell>]``. Centralising the
    rule means ``_label_overhead_px`` and ``_apply_responsive_layout``
    can never disagree about which cells are mapped at a given width.
    """
    return tuple(
        cell for cell, threshold in _RESPONSIVE_THRESHOLDS_PX
        if width_px >= threshold
    )


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
        # CS-57 (Phase 4af): user-driven NODE_GROUP selection model
        # and chevron-expansion state. ``_selected_node_ids`` is the
        # set of row ids the user has clicked to select (toggled on
        # <ButtonRelease-1> rather than <Button-1> so a double-click
        # rename gesture nets out to zero-toggle and leaves selection
        # state unchanged). ``_expanded_groups`` controls whether a
        # NODE_GROUP renders its members inline below the group row;
        # collapsed by default so groups stay one row tall until the
        # user explicitly drills in.
        self._selected_node_ids: set[str] = set()
        self._expanded_groups: set[str] = set()
        # node_id → tk.Frame for the row (top-level, not history sub-frame).
        self._row_frames: dict[str, tk.Frame] = {}
        # node_id → tk.Frame for the history sub-frame (if expanded).
        self._history_frames: dict[str, tk.Frame] = {}
        # Per-row optional controls indexed by node id, used by the
        # responsive layout helper (B-002 + Phase 4n CS-26). Each
        # entry maps a name ("swatch", "leg", "ls_canvas") to the
        # optional widget plus ``vis_cb`` (the swatch's re-pack
        # anchor for ``pack(before=...)``).
        # Phase 4w (CS-47): inner value type relaxed to ``Any`` so
        # the dict can also hold the (optional) Tooltip handle for
        # the row's label widget — needed for dynamic re-truncation
        # in ``_apply_responsive_layout``. Pre-existing entries
        # (swatch, leg, ls_canvas, vis_cb) are still tk.Widget; the
        # ``label_tooltip`` slot is the one ``Tooltip | None`` value.
        self._optional_row_widgets: dict[str, dict[str, Any]] = {}

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

        # Phase 4p (CS-30): the responsive helper now keys on canvas
        # width (the actual sidebar width) rather than row width. Two
        # production failures motivated this: (a) the row's natural
        # width is content-driven (longest visible label wins) so a
        # single-node sidebar stays collapsed at any width because
        # ``row.winfo_width()`` returns a small label-shaped number;
        # (b) narrowing the canvas does not recollapse expanded rows
        # because ``row.winfo_width()`` reflects packed contents, not
        # available space. The canvas-Configure binding here drives
        # reflow on resize; ``_apply_responsive_layout`` reads canvas
        # width as the default ``width`` source. Inner frame width is
        # *not* bound to canvas width — that would cause Tk to auto-
        # unmap overflow widgets in the narrow case, and would also
        # interact badly with the test suite's per-row width stubs.
        def _on_canvas_configure(_event):
            # ``_event.width`` carries Tk's actual reported size, which
            # tests cannot override. Calling the helper without an
            # explicit ``width`` lets it read ``_scroll_canvas
            # .winfo_width()`` — the same source the test suite stubs
            # via ``_force_width`` — so the binding stays inert when
            # tests override the canvas width and active when the
            # user resizes the sidebar in production.
            for nid, frm in list(self._row_frames.items()):
                if nid in self._optional_row_widgets:
                    self._apply_responsive_layout(nid, frm)
        self._scroll_canvas.bind("<Configure>", _on_canvas_configure)

        # Bottom controls.
        self._footer = tk.Frame(self)
        self._footer.pack(side="bottom", fill="x")
        # Phase 4ah: track the Checkbutton as an attribute so _rebuild
        # can flip its state. The toggle is disabled when no hidden
        # rows would be revealed — without the gate the user clicks a
        # responsive-looking control whose only effect is silent. If
        # the toggle is currently ON and the last hidden row is
        # discarded, we leave it ON and disable it (no silent flip to
        # OFF); the disabled state is itself the affordance that the
        # toggle has nothing to act on.
        self._show_hidden_btn = tk.Checkbutton(
            self._footer,
            text="Show hidden",
            variable=self._show_hidden,
            command=self._rebuild,
        )
        self._show_hidden_btn.pack(side="left", padx=4, pady=2)

        # CS-57 (Phase 4af): "Group selected" footer button. Sits on
        # the right of the footer so it's discoverable without
        # competing with the "Show hidden" toggle on the left.
        # Enabled iff ``_selected_node_ids`` has ≥2 entries AND none
        # of them is already in a group AND none of them is itself a
        # NODE_GROUP. The state refresh runs on every selection
        # toggle (via ``_toggle_row_selection``) and after every
        # rebuild (via ``_rebuild``); see ``_refresh_group_button_state``
        # for the predicate. The companion context-menu entry
        # ("Group selected (N)") is enabled by the same predicate.
        self._group_btn = tk.Button(
            self._footer,
            text="Group selected",
            state="disabled",
            command=self._group_selected,
        )
        self._group_btn.pack(side="right", padx=4, pady=2)

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
            GraphEventType.NODE_GROUP_MEMBERS_CHANGED,
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

        CS-57 (Phase 4af): NODE_GROUP rows pass the predicate by a
        side door — the ``node_filter`` predicate is set per-tab
        (e.g. UV/Vis allows only UVVIS-shaped types) and would
        otherwise exclude groups. Groups are always allowed through
        regardless of the predicate so the user's organisational
        layer survives across tabs that share the same widget. Group
        MEMBERS are excluded from the top-level list — they render
        only under their expanded group row (CS-57 visual nesting
        invariant); top-level rendering would double-render the
        member and break the visual containment.
        """
        show_hidden = bool(self._show_hidden.get())

        # CS-57: collect the set of node ids that belong to any
        # active group, so they can be hidden from the flat top-level
        # listing. ``ProjectGraph.group_of`` does this per-node-id
        # but at O(N_groups) per call; building the set once is the
        # rebuild-cost optimisation.
        grouped_member_ids: set[str] = set()
        for node in self._graph.nodes.values():
            if (isinstance(node, DataNode)
                    and node.type == NodeType.NODE_GROUP
                    and node.state != NodeState.DISCARDED):
                grouped_member_ids.update(
                    node.metadata.get("member_ids", ())
                )

        out: list[DataNode] = []
        for node in self._graph.nodes.values():
            if not isinstance(node, DataNode):
                continue
            if node.state == NodeState.DISCARDED:
                continue
            # CS-57: NODE_GROUP always passes the predicate (it's a
            # view-layer aggregation, not a tab-specific data type).
            is_group = node.type == NodeType.NODE_GROUP
            if not is_group and not self._predicate(node):
                continue
            if not node.active and not show_hidden:
                continue
            if node.id in grouped_member_ids:
                # Render only under the expanded group, not at top
                # level — see _rebuild's NODE_GROUP branch.
                continue
            out.append(node)
        return out

    # ------------------------------------------------------------
    # Rebuild
    # ------------------------------------------------------------

    def _rebuild(self) -> None:
        """Tear down and recreate every row from the current graph.

        Cheaper paths exist (insert one row, remove one row) but a
        full rebuild is fast enough for the dataset counts this
        widget is designed for (tens, not thousands).

        CS-57 (Phase 4af): rebuild also prunes stale view state
        (selection ids and expanded-group ids whose nodes are now
        gone or DISCARDED) and refreshes the footer "Group selected"
        button's enabled state. Pruning here means the auto-dissolve
        cascade from ``ProjectGraph.discard_node`` does not leave
        ghost ids in either set after the NODE_DISCARDED event
        rebuilds the widget.
        """
        for child in list(self._rows_frame.winfo_children()):
            child.destroy()
        self._row_frames.clear()
        self._history_frames.clear()
        self._optional_row_widgets.clear()

        # CS-57: prune stale view state. A node is "stale" if it's
        # been removed from the graph entirely or transitioned to
        # DISCARDED. Either way it must not stay in the selection or
        # the expanded-groups set, or a re-add (via undo, recovery,
        # or test reuse of an id) would silently inherit the prior
        # selection.
        for sid in list(self._selected_node_ids):
            if sid not in self._graph.nodes or (
                self._graph.nodes[sid].state == NodeState.DISCARDED
            ):
                self._selected_node_ids.discard(sid)
        for gid in list(self._expanded_groups):
            if gid not in self._graph.nodes or (
                self._graph.nodes[gid].state == NodeState.DISCARDED
            ):
                self._expanded_groups.discard(gid)

        for node in self._candidate_nodes():
            if node.type == NodeType.NODE_GROUP:
                self._build_group_row(node)
                if node.id in self._expanded_groups:
                    # Render each member with the visual nesting
                    # indent so the chevron-expanded group reads as
                    # a containment region rather than four flat
                    # siblings. Members whose ids are no longer
                    # present in the graph (or transitioned to
                    # DISCARDED) are silently skipped — the
                    # ProjectGraph auto-dissolve cascade keeps the
                    # invariant that a NODE_GROUP has ≥2 active
                    # members, but a defensive skip costs nothing.
                    for mid in node.metadata.get("member_ids", ()):
                        if mid not in self._graph.nodes:
                            continue
                        member = self._graph.nodes[mid]
                        if not isinstance(member, DataNode):
                            continue
                        if member.state == NodeState.DISCARDED:
                            continue
                        if not member.active and not bool(
                            self._show_hidden.get()
                        ):
                            continue
                        self._build_node_row(
                            member,
                            indent_px=_SWEEP_MEMBER_INDENT_PX,
                        )
            else:
                self._build_node_row(node)

        self._refresh_group_button_state()
        self._refresh_show_hidden_button_state()

    # ------------------------------------------------------------
    # Per-row construction
    # ------------------------------------------------------------

    def _build_node_row(
        self, node: DataNode, *, indent_px: int = 0,
    ) -> None:
        """Construct the persistent row for a single (non-grouped) node.

        Phase 4r (CS-35): ``indent_px`` shifts the left padding so
        sweep-group members rendered inline below an expanded leader
        (CS-32) sit visually nested under their group. Default ``0``
        keeps every existing call site at the original ``padx=2``;
        only ``_rebuild``'s sweep-expansion branch passes
        ``_SWEEP_MEMBER_INDENT_PX``.
        """
        row = tk.Frame(self._rows_frame)
        row.pack(side="top", fill="x", padx=(2 + indent_px, 2), pady=1)
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

        # Row-toggle slot — Phase 4w (CS-48). A fixed-width column
        # packed on every row regardless of node type so the label
        # cell starts at the same x-coordinate across UVVIS /
        # BASELINE / NORMALISED / SMOOTHED / PEAK_LIST /
        # SECOND_DERIVATIVE rows. This was Phase 4t friction #1: the
        # ``[~]`` baseline-curve toggle existed only on BASELINE
        # rows, so non-BASELINE labels gained ~24 px of leftward
        # space — making column structure visibly different across
        # rows. The slot is a tk.Frame with ``pack_propagate(False)``
        # held at ``_CELL_MIN_PX["row_toggle"]`` width; on BASELINE
        # rows the ``[~]`` Button is parented to it (no change to
        # the toggle's behaviour), on every other type the slot is
        # an empty placeholder that consumes pixels but renders
        # nothing.
        row_toggle = tk.Frame(
            row, width=_CELL_MIN_PX["row_toggle"],
        )
        row_toggle.pack(side="left", padx=(2, 0), fill="y")
        row_toggle.pack_propagate(False)

        # Phase 4r (CS-36): per-node baseline-curve overlay toggle.
        # Only added on BASELINE rows. ``[~]`` when on (default),
        # ``[–]`` when off — parallel to the legend ``✓/–`` glyph
        # vocabulary. The CS-29 global ``Baseline curves`` checkbox
        # is the master switch; this per-row toggle is the
        # downstream filter that lets a user hide individual
        # overlays (e.g. while comparing two of five competing
        # baselines on the same parent). Mutation routes through
        # ``set_style`` so ``GraphEvent.NODE_STYLE_CHANGED`` triggers
        # ``uvvis_tab._redraw`` — same path as the visibility and
        # legend toggles. Phase 4w (CS-48): the button is parented
        # to ``row_toggle`` (the always-packed column slot) rather
        # than to ``row`` directly, so its position aligns with the
        # equivalent placeholder slot on non-BASELINE rows.
        if node.type == NodeType.BASELINE:
            bc_var = tk.BooleanVar(
                value=bool(node.style.get("show_baseline_curve", True))
            )
            bc_btn = tk.Button(row_toggle, width=2, relief=tk.FLAT)

            def _refresh_bc(_b=bc_btn, _v=bc_var):
                _b.config(
                    text="~" if _v.get() else "–",
                    fg="#444444" if _v.get() else "#999999",
                )

            def _toggle_bc(nid=node.id, _b=bc_btn, _v=bc_var):
                new = not _v.get()
                _v.set(new)
                _refresh_bc()
                self._graph.set_style(
                    nid, {"show_baseline_curve": bool(new)},
                )
            bc_btn.config(command=_toggle_bc)
            _refresh_bc()
            bc_btn.pack(fill="both", expand=True)
            # Phase 4t (CS-42) — promoted Tooltip's first cross-module
            # consumer. Phase 4r friction #1 noted the gesture was
            # discoverable only by experimentation; the hover hint
            # paints "Show / hide baseline curve overlay" so a new
            # user reading the row understands the toggle's effect.
            Tooltip(bc_btn, "Show / hide baseline curve overlay")

        # Label (double-click to edit in-place). Phase 4q (CS-33):
        # the displayed text is truncated to keep the row's natural
        # width bounded — long UV/Vis chains accumulate suffixes
        # that would otherwise push the row past the canvas width
        # even with the CS-30 responsive helper. When truncation
        # happens, attach a hover tooltip so the full label remains
        # visible without a rename. The rename Entry reads the full
        # label from the graph (see ``_begin_label_edit``), so
        # editing always starts with the untruncated text regardless
        # of what's painted.
        #
        # Phase 4w (CS-47): the cap is now derived from the actual
        # canvas width via ``_current_label_cap`` instead of the
        # static ``_LABEL_MAX_CHARS = 32``. Falls back to the static
        # cap when geometry / font metrics aren't yet realised, so
        # construction-time behaviour and headless tests are
        # preserved. The same recomputation runs from
        # ``_apply_responsive_layout`` whenever the canvas is
        # resized, so widening the sash visibly grows the label.
        cap = self._current_label_cap()
        display_text = _truncate_label(node.label, max_chars=cap)
        label = tk.Label(row, text=display_text, anchor="w")
        label.pack(side="left", fill="x", expand=True, padx=(2, 4))
        # Always attach a tooltip; its empty-string sentinel makes it
        # silently inert when truncation isn't cutting the text. The
        # canvas-resize re-truncation in ``_apply_responsive_layout``
        # rotates the text via ``update_text`` rather than churning
        # Tooltip handles.
        label_tooltip = Tooltip(
            label,
            node.label if display_text != node.label else "",
        )
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

        # 🔒 — commit gesture on provisional rows (Phase 4q CS-34).
        # Sits between → and ✕ as the commit twin of ✕. Omitted
        # entirely on committed rows: the leftmost-cell 🔒 state
        # indicator already signals the committed state, and a
        # disabled 🔒 button next to ✕ would put two 🔒 glyphs on the
        # same row. The right cluster reads
        # ``[⌥n] [⚙] [→] [🔒] [✕]`` left-to-right when provisional,
        # ``[⌥n] [⚙] [→] [✕]`` when committed.
        if node.state == NodeState.PROVISIONAL:
            commit_btn = tk.Button(
                row, text="🔒", relief=tk.FLAT, cursor="hand2",
                command=lambda nid=node.id: self._safely(
                    self._graph.commit_node, nid),
            )
            commit_btn.pack(side="right", padx=(2, 0))

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
        # CS-57 (Phase 4af): <ButtonRelease-1> on the same widgets
        # toggles selection. ButtonRelease (not Button) so a
        # double-click rename fires Release twice and nets out to
        # zero toggle — see ``_toggle_row_selection`` docstring.
        for w in (row, label, state_lbl):
            w.bind(
                "<Button-3>",
                lambda e, nid=node.id: self._show_context_menu(e, nid),
            )
            w.bind(
                "<ButtonRelease-1>",
                lambda _e, nid=node.id: self._toggle_row_selection(nid),
                add="+",
            )

        # CS-57: paint the selection highlight if this node is
        # currently selected. Reads ``_selected_node_ids`` set by the
        # user's prior click (or empty if this is a fresh rebuild).
        self._apply_row_selection_visual(node.id)

        # Track optional controls so the responsive collapse logic can
        # find them by name (B-002, Phase 4d; thresholds extended in
        # Phase 4n CS-26). ``hist`` is no longer optional — it sits in
        # the always-visible minimum after CS-26 — so it is omitted
        # from this dict. The ``vis_cb`` reference is stored as the
        # swatch's re-pack anchor: without ``before=vis_cb`` a
        # re-packed swatch lands on the wrong side of the label, which
        # has ``fill="x", expand=True``.
        #
        # Phase 4w (CS-47): the ``label`` widget plus its (possibly
        # ``None``) tooltip are tracked here too so
        # ``_apply_responsive_layout`` can re-truncate the painted
        # text on canvas resize without rebuilding the row. The
        # tooltip handle is stored under ``label_tooltip``; a
        # newly-truncated label that previously fitted will get a
        # fresh ``Tooltip`` attached, and a label that previously
        # truncated but now fits will have its tooltip destroyed.
        self._optional_row_widgets[node.id] = {
            "swatch":        swatch,
            "leg":           leg_btn,
            "ls_canvas":     ls_canvas,
            "vis_cb":        vis_cb,
            "label":         label,
            "label_tooltip": label_tooltip,
        }

        # Phase 4p (CS-30): the responsive helper is now driven by
        # canvas-Configure events rather than per-row Configure
        # events. The per-row Configure binding used to read the
        # row's natural (content-driven) width, which (a) misses the
        # available sidebar space when the row is narrower than the
        # canvas, and (b) re-fires on every pack/unpack, racing with
        # explicit helper calls. Initial calibration of newly-built
        # rows happens here: if the canvas is already realised, apply
        # thresholds straight away; otherwise the canvas-Configure
        # event that fires when the canvas first lays out will do
        # the initial pass for every row in one walk.
        self._apply_responsive_layout(node.id, row)

        # Re-attach history sub-frame if currently expanded.
        if node.id in self._expanded_history:
            self._render_history(node.id)

    # ------------------------------------------------------------
    # Group rows (CS-57, Phase 4af)
    # ------------------------------------------------------------

    _SELECTION_BG: str = "#cce4ff"

    def _build_group_row(self, node: DataNode) -> None:
        """Render a NODE_GROUP container row.

        Group rows are a parallel rendering pipeline to
        ``_populate_node_row``: they carry a chevron toggle, the
        group label (renameable via double-click), a member-count
        badge, and an inline ✕ that dissolves the group (members
        return to top-level rendering, the group itself transitions
        to DISCARDED — see ``ProjectGraph.dissolve_group``). Groups
        do NOT participate in the responsive layout helper or the
        per-row style-cell vocabulary; ``_optional_row_widgets`` is
        not populated for group rows so
        ``_apply_responsive_layout`` skips them.

        Selection toggle and right-click context-menu bindings
        mirror the data-row pattern so the gesture vocabulary stays
        coherent ("Group selected" requires the group's own row to
        be selectable for bulk operations like "Ungroup all
        selected", a future polish).
        """
        row = tk.Frame(self._rows_frame)
        row.pack(fill="x", padx=2, pady=1)
        self._row_frames[node.id] = row

        is_expanded = node.id in self._expanded_groups

        # Chevron — ▾ when expanded, ▸ when collapsed.
        chevron_btn = tk.Button(
            row, text=("▾" if is_expanded else "▸"),
            relief=tk.FLAT, cursor="hand2", width=2,
            command=lambda nid=node.id: self._toggle_group_expansion(nid),
        )
        chevron_btn.pack(side="left")
        Tooltip(chevron_btn, "Expand / collapse group")

        # Label — group name + (N members) badge.
        member_count = sum(
            1 for mid in node.metadata.get("member_ids", ())
            if mid in self._graph.nodes
            and self._graph.nodes[mid].state != NodeState.DISCARDED
        )
        suffix = f"  ({member_count} members)"
        cap = self._current_label_cap()
        # Reserve space for the suffix so truncation cuts the user
        # label, not the count badge.
        label_cap = max(_LABEL_CHAR_FLOOR, cap - len(suffix))
        display_text = _truncate_label(node.label, max_chars=label_cap) + suffix
        label = tk.Label(row, text=display_text, anchor="w")
        label.pack(side="left", fill="x", expand=True, padx=(2, 4))
        # Hover tooltip with full label when truncation cuts it.
        Tooltip(
            label,
            node.label if display_text != node.label + suffix else "",
        )
        label.bind(
            "<Double-Button-1>",
            lambda _e, nid=node.id, lbl=label, frm=row:
                self._begin_label_edit(nid, lbl, frm),
        )

        # Inline ✕ — dissolves the group. Tooltip distinguishes it
        # from a member-row ✕ ("Discard"); both glyphs are the same
        # but the semantics differ (members → discard; group →
        # ungroup).
        x_btn = tk.Button(
            row, text="✕", relief=tk.FLAT, cursor="hand2",
            command=lambda nid=node.id: self._safely(
                self._graph.dissolve_group, nid),
        )
        x_btn.pack(side="right", padx=(2, 0))
        Tooltip(x_btn, "Ungroup (dissolve; members are kept)")

        # Selection toggle + right-click context menu — same
        # bindings the data row uses (see _populate_node_row), so
        # group rows feel identical to data rows under the cursor.
        for w in (row, label):
            w.bind(
                "<Button-3>",
                lambda e, nid=node.id: self._show_context_menu(e, nid),
            )
            w.bind(
                "<ButtonRelease-1>",
                lambda _e, nid=node.id: self._toggle_row_selection(nid),
                add="+",
            )

        self._apply_row_selection_visual(node.id)

    def _toggle_group_expansion(self, group_id: str) -> None:
        """Flip a group's expanded state and rebuild.

        The expanded set is small (one entry per drilled-in group)
        so a full rebuild is cheap and avoids subtle invalidations
        from the per-row helpers.
        """
        if group_id in self._expanded_groups:
            self._expanded_groups.discard(group_id)
        else:
            self._expanded_groups.add(group_id)
        self._rebuild()

    # ------------------------------------------------------------
    # Selection & footer-button helpers (CS-57)
    # ------------------------------------------------------------

    def _toggle_row_selection(self, node_id: str) -> None:
        """Flip selection for ``node_id`` and refresh the footer button.

        Bound to ``<ButtonRelease-1>`` rather than ``<Button-1>`` so
        a double-click rename gesture fires Release twice and nets
        out to a zero-toggle (Tk event order: Button-1 →
        ButtonRelease-1 → Double-Button-1 → ButtonRelease-1; the
        two Release events toggle and untoggle, leaving the row in
        its prior selection state). The single-click path runs only
        the first Release and toggles once.
        """
        if node_id in self._selected_node_ids:
            self._selected_node_ids.discard(node_id)
        else:
            self._selected_node_ids.add(node_id)
        self._apply_row_selection_visual(node_id)
        self._refresh_group_button_state()

    def _apply_row_selection_visual(self, node_id: str) -> None:
        """Paint or clear the selection highlight on a row's label.

        Reads ``_selected_node_ids`` to decide. Selected rows get a
        light-blue background on the label widget; unselected rows
        inherit the parent Frame's background (the system default).
        Silently no-ops if the row isn't currently realised (e.g.
        called for a node that was discarded between event firing
        and this method running).
        """
        row = self._row_frames.get(node_id)
        if row is None:
            return
        selected = node_id in self._selected_node_ids
        parent_bg = row.cget("bg")
        new_bg = self._SELECTION_BG if selected else parent_bg
        # Tint every Label child whose 'anchor' is "w" — that's the
        # main label widget by convention (CS-04 §6.1). The state
        # 🔒/⋯ Label uses default anchor and stays system-coloured.
        for child in row.winfo_children():
            if isinstance(child, tk.Label) and child.cget("anchor") == "w":
                child.config(bg=new_bg)

    def _refresh_group_button_state(self) -> None:
        """Update the footer button's text + enable state.

        The button has three operating modes, determined by
        ``_classify_selection``:

        * ``"group"`` — ≥2 ungroupable nodes selected, no groups.
          Button reads ``"Group selected (N)"`` (CS-58, Phase 4ag
          friction #6 polish) and clicking calls ``create_group``.
        * ``"extend"`` — exactly 1 NODE_GROUP + ≥1 ungroupable
          nodes selected. Button reads ``"Add to <group label>"``
          and clicking calls ``extend_group``. The group label is
          truncated so the button doesn't stretch the footer.
        * ``"none"`` / ``"invalid"`` — button reads
          ``"Group selected"`` (the CS-57 baseline label) and is
          disabled.

        CS-57 lock: the button's existence + ``_group_btn``
        attribute name are preserved. The text-mutability is the
        explicit relaxation trigger (Phase 4af friction #6).
        Called from ``_toggle_row_selection`` and at the end of
        ``_rebuild``.
        """
        # Defensive: the button may not exist yet if this is called
        # during ``__init__`` before ``_build_chrome`` finishes.
        btn = getattr(self, "_group_btn", None)
        if btn is None:
            return
        classification = self._classify_selection()
        mode = classification["mode"]
        if mode == "group":
            n = len(classification["members"])
            btn.config(
                state="normal",
                text=f"Group selected ({n})",
            )
        elif mode == "extend":
            target = self._graph.get_node(classification["group_id"])
            # Truncate the group's label so the footer doesn't
            # stretch on long user-renames. Reuses ``_truncate_label``
            # so the cap policy stays consistent with the row labels.
            short_label = _truncate_label(target.label, max_chars=24)
            btn.config(
                state="normal",
                text=f"Add to {short_label}",
            )
        else:
            btn.config(state="disabled", text="Group selected")

    def _has_hidden_rows(self) -> bool:
        """Return True iff ≥1 currently-hidden row exists in the view.

        A row counts as "hidden" iff it is a non-DISCARDED DataNode
        with ``active=False`` that the tab predicate accepts (or it
        is itself a NODE_GROUP, which always passes the predicate
        per CS-57 visual-layer invariant).

        Phase 4ah: includes hidden group members regardless of
        whether their parent group is currently expanded. Rationale:
        if a member is currently hidden, the toggle becomes relevant
        the moment the user expands its group, so we don't want the
        toggle's enabled state to whiplash between disabled and
        enabled as the user expands and collapses groups.
        """
        for node in self._graph.nodes.values():
            if not isinstance(node, DataNode):
                continue
            if node.state == NodeState.DISCARDED:
                continue
            if node.active:
                continue
            if node.type == NodeType.NODE_GROUP:
                return True
            if self._predicate(node):
                return True
        return False

    def _refresh_show_hidden_button_state(self) -> None:
        """Disable the 'Show hidden' toggle when no hidden rows exist.

        Phase 4ah. Without this gate the toggle reads as responsive
        but produces no visible change on a fresh workflow (where no
        nodes are hidden), giving a false-affordance signal.

        Cascade: if the toggle is currently ON and the last hidden
        row is discarded, the toggle stays ON and becomes disabled.
        We never silently flip ``_show_hidden`` to False — the
        disabled state is itself the affordance that the toggle has
        nothing to act on.
        """
        btn = getattr(self, "_show_hidden_btn", None)
        if btn is None:
            return
        btn.config(
            state="normal" if self._has_hidden_rows() else "disabled"
        )

    def _classify_selection(self) -> dict:
        """Classify ``_selected_node_ids`` into a single gesture verdict.

        Returns a small dict so callers (footer button refresh,
        context-menu builders) all read from the same canonical
        analysis. Possible verdicts:

        * ``{"mode": "none"}`` — empty selection.
        * ``{"mode": "group", "members": [ids in graph order]}`` —
          ≥2 ungroupable data nodes, no NODE_GROUPs, none already
          grouped: the create_group gesture is legal.
        * ``{"mode": "extend", "group_id": str,
          "members": [ungrouped ids in graph order]}`` — exactly
          one NODE_GROUP + ≥1 ungrouped data nodes, none already
          grouped: the extend_group gesture is legal.
        * ``{"mode": "invalid"}`` — non-empty selection that doesn't
          fit either gesture (mixed groups, members of another
          group, discarded ids, etc.).

        The ``members`` list is sorted by the graph's node insertion
        order so member_ids stays deterministic across runs (Python
        set iteration is hash-dependent).
        """
        if not self._selected_node_ids:
            return {"mode": "none"}

        groups: list[str] = []
        ungrouped: list[str] = []
        for sid in self._selected_node_ids:
            if sid not in self._graph.nodes:
                return {"mode": "invalid"}
            node = self._graph.nodes[sid]
            if not isinstance(node, DataNode):
                return {"mode": "invalid"}
            if node.state == NodeState.DISCARDED:
                return {"mode": "invalid"}
            if node.type == NodeType.NODE_GROUP:
                if node.state == NodeState.DISCARDED:
                    return {"mode": "invalid"}
                groups.append(sid)
            else:
                if self._graph.group_of(sid) is not None:
                    # Member of some other active group — can't
                    # legally be moved into a new gesture target.
                    return {"mode": "invalid"}
                ungrouped.append(sid)

        # Deterministic order: walk insertion order, keep selected.
        ordered_ungrouped = [
            nid for nid in self._graph.nodes.keys()
            if nid in ungrouped
        ]

        if not groups and len(ordered_ungrouped) >= 2:
            return {"mode": "group", "members": ordered_ungrouped}
        if (len(groups) == 1 and ordered_ungrouped
                and self._graph.nodes[groups[0]].state
                != NodeState.DISCARDED):
            return {
                "mode":     "extend",
                "group_id": groups[0],
                "members":  ordered_ungrouped,
            }
        return {"mode": "invalid"}

    def _can_group_selection(self) -> bool:
        """True iff the current selection is a legal create_group call.

        Preserved verbatim from CS-57 (Phase 4af) — Phase 4ag adds
        ``_classify_selection`` as the richer counterpart but does
        not retire this predicate; callers that only care about
        the create_group gesture (existing footer-button test, the
        data-row context-menu "Group selected (N)" entry) keep
        their narrow check.
        """
        if len(self._selected_node_ids) < 2:
            return False
        for sid in self._selected_node_ids:
            if sid not in self._graph.nodes:
                return False
            node = self._graph.nodes[sid]
            if not isinstance(node, DataNode):
                return False
            if node.state == NodeState.DISCARDED:
                return False
            if node.type == NodeType.NODE_GROUP:
                return False
            if self._graph.group_of(sid) is not None:
                return False
        return True

    def _can_extend_existing_group(self) -> tuple[str, list[str]] | None:
        """Return ``(group_id, ungrouped_ids)`` iff the extend gesture is legal.

        Thin wrapper over ``_classify_selection`` that returns the
        pair callers need or ``None``. Used by both the footer
        button (via _refresh_group_button_state) and the
        context-menu predicates.
        """
        c = self._classify_selection()
        if c["mode"] != "extend":
            return None
        return c["group_id"], c["members"]

    def _group_selected(self) -> None:
        """Footer-button click — dispatch to create_group OR extend_group.

        Re-reads the selection classification so a race between
        button-enable and click (e.g. a graph event that re-shaped
        the selection) gracefully no-ops rather than crashing.
        Clears the selection on success — the user's next gesture
        starts from a clean slate. ``_safely`` swallows benign
        exceptions if the predicate raced a state change.

        CS-58 (Phase 4ag): the click handler used to call
        ``create_group`` unconditionally. It now branches on
        ``_classify_selection`` so the same button surfaces both
        gestures, matching the dynamic label set by
        ``_refresh_group_button_state``.
        """
        classification = self._classify_selection()
        mode = classification["mode"]
        if mode == "group":
            try:
                self._graph.create_group(classification["members"])
            except (KeyError, ValueError, TypeError):
                return
        elif mode == "extend":
            try:
                self._graph.extend_group(
                    classification["group_id"],
                    classification["members"],
                )
            except (KeyError, ValueError, TypeError):
                return
        else:
            return
        self._selected_node_ids.clear()
        # The graph event from create_group/extend_group will trigger
        # a rebuild via _on_graph_event, which also refreshes the
        # button state and re-paints the selection visual.

    def _extend_into_group(self, group_id: str) -> None:
        """Context-menu action — add selection's ungrouped members to ``group_id``.

        Called from the group-row context menu's
        "Add selected to this group" entry and the data-row
        context menu's "Add selected to <group label>" entry.
        Independent of which row was right-clicked — the right-
        click identifies the target group; the *selection*
        identifies what gets added.

        Walks the graph's insertion order to keep member_ids
        deterministic. Clears selection on success. Wraps the
        graph call so a race condition (e.g. group discarded
        between menu-popup and click) silently no-ops.
        """
        ungrouped_ids = [
            sid for sid in self._graph.nodes.keys()
            if sid in self._selected_node_ids
            and isinstance(self._graph.nodes[sid], DataNode)
            and self._graph.nodes[sid].type != NodeType.NODE_GROUP
            and self._graph.nodes[sid].state != NodeState.DISCARDED
            and self._graph.group_of(sid) is None
        ]
        if not ungrouped_ids:
            return
        try:
            self._graph.extend_group(group_id, ungrouped_ids)
        except (KeyError, ValueError, TypeError):
            return
        self._selected_node_ids.clear()

    def _remove_from_group_via_menu(self, node_id: str) -> None:
        """Context-menu action — detach a single node from its group.

        Wraps ``ProjectGraph.remove_from_group`` so the per-row
        gesture (right-click on a grouped member → "Remove from
        group") swallows benign races silently. Does NOT clear
        the selection — the user's selection should survive a
        single-target gesture; only multi-target gestures
        (Group selected / Add selected to <group>) reset it.
        """
        self._safely(self._graph.remove_from_group, node_id)

    # ------------------------------------------------------------
    # Label measurement (Phase 4w CS-47)
    # ------------------------------------------------------------

    def _label_font(self) -> tkfont.Font | None:
        """Return the Tk font used for sidebar row labels.

        Reads the named font ``TkDefaultFont`` since
        ``_populate_node_row`` constructs the label as
        ``tk.Label(row, text=…)`` without an explicit ``font=…``.
        Returns ``None`` if the named font lookup fails (e.g. the
        widget isn't realised yet); callers must handle that.
        """
        try:
            return tkfont.nametofont("TkDefaultFont")
        except (tk.TclError, RuntimeError):
            return None

    def _avg_char_px(self) -> int:
        """Average pixel width of a label character.

        Sampled by measuring a 20-character mixed-case string and
        dividing — more representative than ``measure("M")`` for
        proportional fonts. Returns ``0`` when font metrics are
        unavailable; ``_label_char_capacity`` falls back to the
        static cap in that case.
        """
        font = self._label_font()
        if font is None:
            return 0
        try:
            sample = "ABCDEFGHIJabcdefghij"
            total = font.measure(sample)
            if total <= 0:
                return 0
            return max(1, total // len(sample))
        except tk.TclError:
            return 0

    def _label_overhead_px(self, width: int | None = None) -> int:
        """Pixels consumed by non-label cells at the current row layout.

        Used by ``_current_label_cap`` to estimate the label cell's
        share of the canvas width.

        Phase 4z (CS-51): width-aware. When ``width`` is given, the
        overhead reflects which optional cells will be packed at that
        width per ``_RESPONSIVE_THRESHOLDS_PX``, so the dynamic label
        cap shrinks the moment the swatch (or leg / ls_canvas)
        reappears as the sash widens past its reveal threshold. When
        ``width`` is ``None`` (the no-arg call from
        ``_calibrate_sidebar_width``) the helper returns the
        always-visible-only baseline — byte-equivalent to Phase 4w —
        so the one-shot sash calibration's target is unchanged.

        See ``_compute_label_overhead_px`` /
        ``_visible_optional_cells_for_width`` for the pure helpers
        that do the actual computation; this method just funnels the
        instance's state into them.
        """
        if width is None:
            return _compute_label_overhead_px()
        return _compute_label_overhead_px(
            _visible_optional_cells_for_width(width)
        )

    def _current_label_cap(self) -> int:
        """Compute the dynamic label-character cap for the current canvas.

        Falls back to ``_LABEL_MAX_CHARS`` when the canvas isn't yet
        realised or the named font's metrics aren't available — this
        keeps construction-time and headless-test behaviour
        identical to Phase 4q (CS-33).

        Phase 4z (CS-51): forwards ``canvas_width`` into the
        width-aware ``_label_overhead_px`` so the cap shrinks the
        moment an optional cell (swatch / leg / ls_canvas) reveals
        at its CS-26 threshold. Without this forwarding the static
        overhead stays sized for the swatch-absent state and the
        label widget refuses to shrink, clipping the right-side
        cells (Phase 4x friction #1).
        """
        try:
            canvas_width = self._scroll_canvas.winfo_width()
        except (tk.TclError, AttributeError):
            return _LABEL_MAX_CHARS
        return _label_char_capacity(
            canvas_width_px=canvas_width,
            avg_char_px=self._avg_char_px(),
            overhead_px=self._label_overhead_px(width=canvas_width),
        )

    def widest_label_pixel_width(
        self, font: tkfont.Font | None = None,
    ) -> int:
        """Return the longest candidate node label's pixel width.

        Phase 4w (CS-47). Used by ``UVVisTab._calibrate_sidebar_width``
        to size the sash on first paint so long labels are readable
        without manual sash-dragging. Walks the same candidates that
        ``_rebuild`` would render (filtered, "Show hidden" honoured)
        and returns ``max(font.measure(label))`` over the set.
        Returns ``0`` when the candidate list is empty or font
        metrics fail.
        """
        if font is None:
            font = self._label_font()
        if font is None:
            return 0
        widest = 0
        for node in self._candidate_nodes():
            try:
                w = font.measure(node.label)
            except tk.TclError:
                continue
            if w > widest:
                widest = w
        return widest

    # ------------------------------------------------------------
    # Responsive row collapse (B-002, Phase 4d)
    # ------------------------------------------------------------

    def _apply_responsive_layout(
        self, node_id: str, row: tk.Frame,
        width: int | None = None,
    ) -> None:
        """Hide / re-pack optional controls based on the available width.

        Phase 4n CS-26 graduated reveal: each cell in
        ``_RESPONSIVE_THRESHOLDS_PX`` is mapped iff the available
        width is at least its threshold. Below the smallest threshold
        no optional cells are shown; the always-visible minimum
        (state, ☑, label, ⌥n, ⚙, →, ✕) keeps the row usable.

        Phase 4p (CS-30): ``width`` is the available sidebar width.
        When omitted, the helper reads it from the scrollable
        canvas's ``winfo_width()`` rather than from the row itself —
        the row's natural width is content-driven and does not
        reflect available space, so a single-node sidebar at 800 px
        would otherwise stay collapsed at every threshold. Callers
        that need to drive a specific width (tests; the canvas
        Configure handler) pass it explicitly.

        The helper unconditionally rewrites the optional cells'
        pack state on every call rather than tracking "current"
        state, because:

        * Tk auto-unmaps a packed widget that doesn't fit in a
          narrow parent, so ``winfo_ismapped()`` cannot be trusted
          as the "is this widget in our intended layout?" oracle —
          it disagrees with the pack list under overflow.
        * The right-side optional widgets share a delicate ordering
          invariant: when both ``leg`` and ``ls_canvas`` are mapped
          the canonical visual order is ``leg ls_canvas`` (leg
          leftmost). Re-packing both together preserves that
          regardless of which threshold was just crossed.
        * Repeated <Configure> events with the same width pay only
          a few pack-list updates per row — Tk's pack manager is
          a tcl-level operation, no perceptible flicker.

        ``swatch`` is re-inserted with ``before=vis_cb`` because a
        plain ``side="left"`` would place it after ``label`` (which
        has ``fill="x", expand=True`` and consumes remaining left
        space).
        """
        widgets = self._optional_row_widgets.get(node_id)
        if widgets is None:
            return
        if width is None:
            try:
                width = self._scroll_canvas.winfo_width()
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

        want_swatch = width >= thresholds["swatch"]
        want_leg    = width >= thresholds["leg"]
        want_ls     = width >= thresholds["ls_canvas"]

        # Left side — swatch is independent of right-side ordering.
        # Always pack_forget first so the subsequent pack call (if
        # any) inserts at the correct position via ``before=vis_cb``.
        if swatch is not None:
            try:
                swatch.pack_forget()
            except tk.TclError:
                pass
            if want_swatch and vis_cb is not None:
                try:
                    swatch.pack(side="left", padx=2, before=vis_cb)
                except tk.TclError:
                    pass

        # Right side — reflow ``leg`` and ``ls_canvas`` together so
        # the canonical visual order ``leg · ls_canvas · ⌥n · ⚙ ·
        # → · ✕`` is preserved no matter which threshold was just
        # crossed.
        for w in (leg, ls_canvas):
            if w is None:
                continue
            try:
                w.pack_forget()
            except tk.TclError:
                pass
        # Pack in the order ``ls_canvas`` then ``leg`` so each
        # ``side="right"`` call lands to the left of the previously
        # packed widget.
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

        # Phase 4w (CS-47): re-truncate the label at the cap derived
        # from the current canvas width. The same call cycle that
        # reflows optional cells on resize also adjusts the painted
        # label, so widening the sash visibly shows more characters
        # of long labels and narrowing trims them. The full label
        # stays in the graph; only the painted text changes.
        label_widget = widgets.get("label")
        if label_widget is not None:
            try:
                node = self._graph.get_node(node_id)
            except KeyError:
                return
            if not isinstance(node, DataNode):
                return
            cap = self._current_label_cap()
            new_text = _truncate_label(node.label, max_chars=cap)
            try:
                if label_widget.cget("text") != new_text:
                    label_widget.config(text=new_text)
            except tk.TclError:
                return

            # Tooltip rotation: pass the full label when truncation
            # cuts the text, otherwise the empty-string sentinel
            # which makes Tooltip's ``_show`` bail silently. Single
            # handle for the lifetime of the row — see
            # ``_populate_node_row`` for the always-attach pattern.
            existing_tip = widgets.get("label_tooltip")
            if existing_tip is not None:
                full = node.label if new_text != node.label else ""
                try:
                    existing_tip.update_text(full)
                except (AttributeError, tk.TclError):
                    pass

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
        # Phase 4q (CS-33): read the full label from the graph rather
        # than the widget's painted text, which may have been
        # truncated by ``_truncate_label`` for display. Falling back
        # to the widget text only when the graph lookup fails keeps
        # rename functional on any row even if a teardown race
        # discards the node mid-click.
        try:
            node = self._graph.get_node(node_id)
            current = (node.label
                       if isinstance(node, DataNode)
                       else label_widget.cget("text"))
        except KeyError:
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

        # CS-57 (Phase 4af): NODE_GROUP rows get a simplified menu
        # — Commit / Discard / Send-to-Compare / Export / Hide do
        # not apply to a view-layer aggregation. Rename and Ungroup
        # are the only sensible actions; Expand/Collapse is the
        # chevron's job but a menu entry mirrors the gesture for
        # users who reach for right-click first.
        if node.type == NodeType.NODE_GROUP:
            self._show_group_context_menu(event, node_id)
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
        # CS-57: "Group selected" mirrors the footer button. The
        # menu entry uses the count of selected ids in its label
        # ("Group selected (3)") so the user can confirm at a glance
        # how many rows the action will combine. If the user right-
        # clicked a row that is NOT in the current selection, this
        # entry stays disabled — the menu always acts on the
        # selection, never on the clicked-but-unselected target.
        n_selected = len(self._selected_node_ids)
        group_ok = (
            self._can_group_selection()
            and node_id in self._selected_node_ids
        )
        menu.add_separator()
        menu.add_command(
            label=f"Group selected ({n_selected})",
            state=("normal" if group_ok else "disabled"),
            command=self._group_selected,
        )
        # CS-58 (Phase 4ag): sibling "Add selected to <group>" entry
        # when selection is exactly 1 NODE_GROUP + ≥1 ungrouped.
        # Like "Group selected", it is gated on the right-clicked
        # row being part of the selection — so the gesture always
        # acts on what the user can see is highlighted, never on a
        # clicked-but-unselected target.
        extend_target = self._can_extend_existing_group()
        if extend_target is not None:
            target_gid, target_members = extend_target
            extend_ok = node_id in self._selected_node_ids
            target_label = self._graph.nodes[target_gid].label
            short_label = _truncate_label(target_label, max_chars=20)
            menu.add_command(
                label=f"Add selected to {short_label} "
                      f"({len(target_members)})",
                state=("normal" if extend_ok else "disabled"),
                command=lambda gid=target_gid: self._extend_into_group(gid),
            )
        # CS-58: "Remove from group" — per-row gesture (not
        # selection-based). Visible only when the right-clicked
        # row is itself a member of an active group.
        clicked_group = self._graph.group_of(node_id)
        if clicked_group is not None:
            menu.add_command(
                label="Remove from group",
                command=lambda nid=node_id: self._remove_from_group_via_menu(nid),
            )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_group_context_menu(
        self, event: tk.Event, group_id: str,
    ) -> None:
        """Simplified context menu for NODE_GROUP rows (CS-57).

        Lifecycle and Send-to-Compare actions do not apply to a
        view-layer aggregation, so the menu carries only Rename,
        Expand/Collapse, and Ungroup. Ungroup dispatches to
        ``ProjectGraph.dissolve_group``.

        CS-58 (Phase 4ag): when the current selection contains
        ≥1 ungrouped data node that could legally be added to
        the right-clicked group, the menu grows a fourth entry
        ``"Add selected to this group"``. This entry is
        intentionally insensitive to whether the right-clicked
        group is itself in the selection — the right-click
        identifies the target; the selection identifies the
        payload.
        """
        menu = tk.Menu(self, tearoff=0)
        is_expanded = group_id in self._expanded_groups
        menu.add_command(
            label="Rename",
            command=lambda nid=group_id: self._begin_rename_via_menu(nid),
        )
        menu.add_command(
            label=("Collapse" if is_expanded else "Expand"),
            command=lambda nid=group_id: self._toggle_group_expansion(nid),
        )
        menu.add_separator()
        menu.add_command(
            label="Ungroup",
            command=lambda nid=group_id: self._safely(
                self._graph.dissolve_group, nid),
        )
        # CS-58: "Add selected to this group" — visible only when
        # the selection holds ≥1 ungrouped data node. Disabled
        # otherwise so the affordance remains discoverable.
        addable_count = sum(
            1 for sid in self._selected_node_ids
            if sid in self._graph.nodes
            and isinstance(self._graph.nodes[sid], DataNode)
            and self._graph.nodes[sid].type != NodeType.NODE_GROUP
            and self._graph.nodes[sid].state != NodeState.DISCARDED
            and self._graph.group_of(sid) is None
        )
        add_ok = (
            addable_count > 0
            and group_id in self._graph.nodes
            and self._graph.nodes[group_id].state != NodeState.DISCARDED
        )
        menu.add_separator()
        menu.add_command(
            label=f"Add selected to this group ({addable_count})",
            state=("normal" if add_ok else "disabled"),
            command=lambda gid=group_id: self._extend_into_group(gid),
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
        # CS-57 (Phase 4af): NODE_GROUP rows have a different cell
        # layout (chevron / label / ✕) from data rows, so the
        # ``_populate_node_row`` repaint path would build the wrong
        # chrome. Fall back to a full rebuild for group label
        # changes — group renames are rare and a rebuild keeps the
        # member-count suffix in sync with the current graph state.
        if node.type == NodeType.NODE_GROUP:
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
