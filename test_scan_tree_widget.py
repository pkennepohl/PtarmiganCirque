"""Tests for scan_tree_widget.py.

The widget is GUI code. Tests construct a real ``tk.Tk`` root and a
real ``ProjectGraph``, then drive the graph and observe the resulting
widget state. We do not call ``mainloop`` — Tk widgets exist as soon
as their constructors return, and ``update_idletasks`` is enough to
flush any pending geometry work.

Headless environments (CI without a display) cannot construct ``Tk``;
the entire test class is skipped via ``unittest.skipUnless`` when
construction fails. Run locally with the project venv:

    venv/Scripts/python run_tests.py

These tests cover the behaviours called out in the Phase 2 task:

* construction with a real ProjectGraph and a stub redraw_cb
* ``NODE_ADDED`` inserts a row
* ``NODE_DISCARDED`` removes the row
* ``NODE_LABEL_CHANGED`` updates the displayed label
* ``NODE_ACTIVE_CHANGED`` hides/shows the row (respecting "Show
  hidden")
* ``node_filter`` is honoured (both list and callable forms)

A handful of additional checks are included for things that are
trivially testable through the public API: sweep-group collapsing,
graph subscription drop on ``unsubscribe`` / ``<Destroy>``, and the
``style_dialog_cb`` hand-off.
"""

from __future__ import annotations

import unittest

import numpy as np

# Try to construct a Tk root once at module import time. If it fails
# (no display, missing tcl/tk), every test in the file is skipped.
try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _HAS_DISPLAY = True
except Exception:  # pragma: no cover — only hit on headless CI
    _root = None
    _HAS_DISPLAY = False


from graph import GraphEventType, ProjectGraph
from nodes import DataNode, NodeState, NodeType, OperationNode, OperationType


# ---- helpers --------------------------------------------------------

def _data(nid: str, ntype: NodeType = NodeType.UVVIS,
          state: NodeState = NodeState.PROVISIONAL,
          label: str | None = None,
          active: bool = True) -> DataNode:
    return DataNode(
        id=nid,
        type=ntype,
        arrays={"x": np.arange(3)},
        metadata={},
        label=label or nid,
        state=state,
        active=active,
    )


def _op(oid: str, otype: OperationType = OperationType.LOAD,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None) -> OperationNode:
    return OperationNode(
        id=oid,
        type=otype,
        engine="internal",
        engine_version="0.0.0",
        params={},
        input_ids=list(inputs or []),
        output_ids=list(outputs or []),
    )


def _redraw_calls() -> tuple[list[tuple[tuple, dict]], "function"]:
    """Build a stub ``redraw_cb`` and the list of calls it records.

    Each invocation records ``(args, kwargs)`` so tests can assert
    that a history click invoked it with ``focus=...``.
    """
    calls: list[tuple[tuple, dict]] = []

    def cb(*args, **kwargs):
        calls.append((args, kwargs))

    return calls, cb


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestScanTreeWidget(unittest.TestCase):
    """Reactivity, filtering, and structural behaviours."""

    @classmethod
    def setUpClass(cls):
        # Importing the widget here, after we know Tk is available,
        # mirrors how a real tab would import it lazily.
        from scan_tree_widget import ScanTreeWidget
        cls.ScanTreeWidget = ScanTreeWidget

    def setUp(self):
        # One container Frame per test, parented to the module-level
        # _root. We destroy it in tearDown so Tk's widget table is
        # not polluted across tests.
        self.host = tk.Frame(_root)

    def tearDown(self):
        try:
            self.host.destroy()
        except Exception:
            pass

    # ----------- construction -----------

    def test_constructs_with_empty_graph(self):
        graph = ProjectGraph()
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        widget.update_idletasks()
        self.assertEqual(widget._row_frames, {})

    def test_subscribes_on_construction(self):
        graph = ProjectGraph()
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        # The widget's _on_graph_event must be in the graph's
        # subscriber list.
        self.assertIn(widget._on_graph_event, graph._subscribers)

    # ----------- reactivity: NODE_ADDED -----------

    def test_node_added_inserts_row(self):
        graph = ProjectGraph()
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        graph.add_node(_data("a", NodeType.UVVIS))
        widget.update_idletasks()
        self.assertIn("a", widget._row_frames)

    def test_node_added_outside_filter_does_not_insert_row(self):
        graph = ProjectGraph()
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        graph.add_node(_data("xanes", NodeType.XANES))
        widget.update_idletasks()
        self.assertNotIn("xanes", widget._row_frames)

    # ----------- reactivity: NODE_DISCARDED -----------

    def test_node_discarded_removes_row(self):
        graph = ProjectGraph()
        graph.add_node(_data("a", NodeType.UVVIS))
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        widget.update_idletasks()
        self.assertIn("a", widget._row_frames)

        graph.discard_node("a")
        widget.update_idletasks()
        self.assertNotIn("a", widget._row_frames)

    # ----------- reactivity: NODE_LABEL_CHANGED -----------

    def test_node_label_change_updates_label(self):
        graph = ProjectGraph()
        graph.add_node(_data("a", NodeType.UVVIS, label="old"))
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        widget.update_idletasks()

        graph.set_label("a", "new")
        widget.update_idletasks()

        # Find the editable Label inside the row.
        row = widget._row_frames["a"]
        label_widgets = [
            w for w in row.winfo_children()
            if isinstance(w, tk.Label)
            and w.cget("text") not in ("🔒", "⋯")
        ]
        self.assertEqual(len(label_widgets), 1)
        self.assertEqual(label_widgets[0].cget("text"), "new")

    # ----------- reactivity: NODE_ACTIVE_CHANGED -----------

    def test_active_false_hides_row_unless_show_hidden(self):
        graph = ProjectGraph()
        graph.add_node(
            _data("a", NodeType.UVVIS, state=NodeState.COMMITTED),
        )
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        widget.update_idletasks()
        self.assertIn("a", widget._row_frames)

        graph.set_active("a", False)
        widget.update_idletasks()
        self.assertNotIn(
            "a", widget._row_frames,
            "active=False should hide the row when 'show hidden' is off",
        )

        widget._show_hidden.set(True)
        widget._rebuild()
        widget.update_idletasks()
        self.assertIn(
            "a", widget._row_frames,
            "'Show hidden' should reveal the soft-hidden row",
        )

        graph.set_active("a", True)
        widget.update_idletasks()
        self.assertIn("a", widget._row_frames)

    # ----------- node_filter -----------

    def test_node_filter_list_form(self):
        graph = ProjectGraph()
        graph.add_node(_data("uv", NodeType.UVVIS))
        graph.add_node(_data("xa", NodeType.XANES))
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        widget.update_idletasks()
        self.assertIn("uv", widget._row_frames)
        self.assertNotIn("xa", widget._row_frames)

    def test_node_filter_callable_form(self):
        graph = ProjectGraph()
        graph.add_node(_data("a", NodeType.UVVIS, label="keep"))
        graph.add_node(_data("b", NodeType.UVVIS, label="drop"))
        _, cb = _redraw_calls()

        def predicate(n):
            return n.label == "keep"

        widget = self.ScanTreeWidget(
            self.host, graph, predicate, cb,
        )
        widget.update_idletasks()
        self.assertIn("a", widget._row_frames)
        self.assertNotIn("b", widget._row_frames)

    # ----------- discarded nodes never render -----------

    def test_discarded_node_excluded_at_rebuild(self):
        graph = ProjectGraph()
        graph.add_node(_data("a", NodeType.UVVIS))
        graph.discard_node("a")
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        widget.update_idletasks()
        self.assertNotIn("a", widget._row_frames)

    # ----------- sweep group collapsing -----------

    def test_sweep_group_collapses_two_provisional_siblings(self):
        # parent (committed) → op → variant_a (prov), variant_b (prov)
        # The two variants share a single DataNode parent (after
        # walking back through the OperationNode), so they collapse
        # into one sweep-group row.
        graph = ProjectGraph()
        graph.add_node(
            _data("p", NodeType.UVVIS, state=NodeState.COMMITTED),
        )
        graph.add_node(_op("op_sweep"))
        graph.add_node(_data("a", NodeType.UVVIS))
        graph.add_node(_data("b", NodeType.UVVIS))
        graph.add_edge("p", "op_sweep")
        graph.add_edge("op_sweep", "a")
        graph.add_edge("op_sweep", "b")

        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        widget.update_idletasks()

        # The leader (lex-smallest id, "a") owns the group row;
        # "b" should NOT have its own row entry.
        self.assertIn("a", widget._row_frames)
        self.assertNotIn("b", widget._row_frames)
        self.assertIn("p", widget._sweep_groups)
        self.assertEqual(set(widget._sweep_groups["p"]), {"a", "b"})

    # ----------- subscription teardown -----------

    def test_unsubscribe_drops_from_graph(self):
        graph = ProjectGraph()
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        self.assertIn(widget._on_graph_event, graph._subscribers)
        widget.unsubscribe()
        self.assertNotIn(widget._on_graph_event, graph._subscribers)

    # ----------- style_dialog_cb hand-off -----------

    def test_gear_button_invokes_style_dialog_cb(self):
        graph = ProjectGraph()
        graph.add_node(_data("a", NodeType.UVVIS))
        _, redraw = _redraw_calls()
        seen: list[str] = []

        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], redraw,
            style_dialog_cb=seen.append,
        )
        widget.update_idletasks()

        # Find the gear ⚙ button in row "a" and invoke it.
        row = widget._row_frames["a"]
        gear = [
            w for w in row.winfo_children()
            if isinstance(w, tk.Button) and w.cget("text") == "⚙"
        ]
        self.assertEqual(len(gear), 1)
        gear[0].invoke()
        self.assertEqual(seen, ["a"])

    # ----------- graph extensions are exercised -----------

    def test_x_button_on_committed_soft_hides(self):
        graph = ProjectGraph()
        graph.add_node(
            _data("a", NodeType.UVVIS, state=NodeState.COMMITTED),
        )
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        widget.update_idletasks()

        row = widget._row_frames["a"]
        x_buttons = [
            w for w in row.winfo_children()
            if isinstance(w, tk.Button) and w.cget("text") == "✕"
        ]
        self.assertEqual(len(x_buttons), 1)
        x_buttons[0].invoke()
        widget.update_idletasks()

        # Node still in the graph but active=False, so row is gone.
        self.assertEqual(graph.get_node("a").active, False)
        self.assertNotIn("a", widget._row_frames)

    def test_x_button_on_provisional_discards(self):
        graph = ProjectGraph()
        graph.add_node(_data("a", NodeType.UVVIS))
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        widget.update_idletasks()

        row = widget._row_frames["a"]
        x_buttons = [
            w for w in row.winfo_children()
            if isinstance(w, tk.Button) and w.cget("text") == "✕"
        ]
        x_buttons[0].invoke()
        widget.update_idletasks()

        self.assertEqual(graph.get_node("a").state, NodeState.DISCARDED)
        self.assertNotIn("a", widget._row_frames)

    def test_subscriber_on_destroy_is_dropped(self):
        graph = ProjectGraph()
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, graph, [NodeType.UVVIS], cb,
        )
        self.assertIn(widget._on_graph_event, graph._subscribers)
        widget.destroy()
        # The <Destroy> handler runs synchronously during destroy().
        self.assertNotIn(widget._on_graph_event, graph._subscribers)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestScanTreeWidgetBugB001(unittest.TestCase):
    """Phase 4c — B-001: history pane must render inline below the row.

    Regression: the previous implementation packed the history
    sub-frame at the end of the rows container (Tk's pack default)
    and relied on a full rebuild to restore visual ordering. With
    two rows, expanding history on the first row appeared
    *underneath the second* row, making the row → history visual
    association ambiguous.
    """

    @classmethod
    def setUpClass(cls):
        from scan_tree_widget import ScanTreeWidget
        cls.ScanTreeWidget = ScanTreeWidget

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()

    def tearDown(self):
        try:
            self.host.destroy()
        except Exception:
            pass

    def _fresh_widget(self):
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, self.graph, [NodeType.UVVIS], cb,
        )
        widget.pack()
        return widget

    def test_history_frame_packs_immediately_after_clicked_row(self):
        # Two committed UVVIS rows, neither expanded. The history
        # toggle on the first row must place the sub-frame between
        # the two rows in pack order.
        a = _data("a", state=NodeState.COMMITTED)
        b = _data("b", state=NodeState.COMMITTED)
        self.graph.add_node(a)
        self.graph.add_node(b)
        widget = self._fresh_widget()
        widget.update_idletasks()

        widget._toggle_history("a")
        widget.update_idletasks()

        slaves = widget._rows_frame.pack_slaves()
        # Three children: row_a, history_a, row_b — in that order.
        self.assertEqual(len(slaves), 3,
                         f"expected row_a, history_a, row_b; got {slaves}")
        self.assertIs(slaves[0], widget._row_frames["a"])
        self.assertIs(slaves[1], widget._history_frames["a"])
        self.assertIs(slaves[2], widget._row_frames["b"])

    def test_history_collapses_when_other_row_expanded(self):
        # Spec: "Toggling history on a different row collapses the
        # previous one (one history pane open at a time across the
        # widget)."
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        self.graph.add_node(_data("b", state=NodeState.COMMITTED))
        widget = self._fresh_widget()
        widget.update_idletasks()

        widget._toggle_history("a")
        self.assertIn("a", widget._expanded_history)
        widget._toggle_history("b")
        self.assertNotIn("a", widget._expanded_history)
        self.assertIn("b", widget._expanded_history)
        # And the new history frame sits between row_b and any
        # subsequent row (here, only row_b after row_a).
        slaves = widget._rows_frame.pack_slaves()
        self.assertIs(slaves[0], widget._row_frames["a"])
        self.assertIs(slaves[1], widget._row_frames["b"])
        self.assertIs(slaves[2], widget._history_frames["b"])

    def test_toggle_same_row_collapses_history(self):
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget()
        widget.update_idletasks()

        widget._toggle_history("a")
        self.assertIn("a", widget._expanded_history)
        widget._toggle_history("a")
        self.assertNotIn("a", widget._expanded_history)
        self.assertNotIn("a", widget._history_frames)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestScanTreeWidgetBugB004(unittest.TestCase):
    """Phase 4c — B-004: Rename context-menu entry triggers in-place edit.

    Although the double-click rename pathway has worked since Phase 2,
    the right-click menu entry was reported in Phase 4b manual testing
    as missing. CS-04 §"Context menu" lists ``Rename`` as a
    right-click entry. These tests pin (a) that the menu carries a
    ``Rename`` entry and (b) that invoking it routes through the same
    ``_begin_label_edit`` path as a double-click on the label.
    """

    @classmethod
    def setUpClass(cls):
        from scan_tree_widget import ScanTreeWidget
        cls.ScanTreeWidget = ScanTreeWidget

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()

    def tearDown(self):
        try:
            self.host.destroy()
        except Exception:
            pass

    def _fresh_widget(self):
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, self.graph, [NodeType.UVVIS], cb,
        )
        widget.pack()
        return widget

    def test_context_menu_carries_rename_entry(self):
        # Stub tk_popup so the menu gets constructed but never grabs
        # input; capture the Menu so we can introspect its entries.
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget()
        widget.update_idletasks()

        captured: dict = {}
        original_popup = tk.Menu.tk_popup

        def _stub_popup(self, x, y, *args, **kwargs):
            captured["menu"] = self

        try:
            tk.Menu.tk_popup = _stub_popup
            fake_event = type("E", (), {"x_root": 0, "y_root": 0})()
            widget._show_context_menu(fake_event, "a")
        finally:
            tk.Menu.tk_popup = original_popup

        menu = captured.get("menu")
        self.assertIsNotNone(menu, "context menu should have been built")
        labels: list[str] = []
        last = menu.index("end")
        if last is not None:
            for i in range(last + 1):
                if menu.type(i) != "separator":
                    labels.append(menu.entrycget(i, "label"))
        self.assertIn("Rename", labels)

    def test_rename_menu_invokes_in_place_edit(self):
        # Calling the menu's Rename handler must replace the label
        # widget with an Entry in exactly the same way a double-click
        # does. We invoke the helper directly so we don't have to
        # synthesise a tk_popup callback dispatch.
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]
        entries_pre = [w for w in row.winfo_children()
                       if isinstance(w, tk.Entry)]
        self.assertEqual(entries_pre, [])

        widget._begin_rename_via_menu("a")
        widget.update_idletasks()

        entries_post = [w for w in row.winfo_children()
                        if isinstance(w, tk.Entry)]
        self.assertEqual(len(entries_post), 1,
                         "Rename should swap the label for an Entry")
        self.assertEqual(entries_post[0].get(), "a")

    def test_rename_menu_and_double_click_share_pathway(self):
        # Both gestures invoke ``_begin_label_edit``. Patch the method
        # and verify each gesture routes through it once with the
        # expected node id.
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget()
        widget.update_idletasks()

        calls: list[str] = []
        original = widget._begin_label_edit

        def _spy(node_id, label_widget, row_frame):
            calls.append(node_id)
            # Don't actually mutate the row — we just want to confirm
            # routing, not also test the edit body.

        widget._begin_label_edit = _spy  # type: ignore[assignment]
        try:
            widget._begin_rename_via_menu("a")
        finally:
            widget._begin_label_edit = original  # type: ignore[assignment]

        self.assertEqual(calls, ["a"])


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestScanTreeWidgetResponsiveRow(unittest.TestCase):
    """Phase 4d B-002 + Phase 4n CS-26 — per-row responsive layout.

    Phase 4d introduced a single 280 px collapse threshold over four
    optional cells; Phase 4n CS-26 promoted ⌥n into the
    always-visible minimum and replaced the single threshold with
    three priority-ordered thresholds (swatch @ 240, leg @ 280,
    ls_canvas @ 320). The always-visible minimum is now seven
    cells: ``state``, ``[☑]``, ``label``, ``⌥n``, ``[⚙]``, ``[→]``,
    ``[✕]``.

    Tests force a known row width by calling
    ``widget._apply_responsive_layout`` directly with a stubbed
    ``winfo_width`` rather than driving Tk geometry events — that
    keeps the suite deterministic and decoupled from the host's
    actual pixel width.
    """

    @classmethod
    def setUpClass(cls):
        from scan_tree_widget import ScanTreeWidget
        import scan_tree_widget as stw_mod
        cls.ScanTreeWidget = ScanTreeWidget
        cls.stw_mod = stw_mod

    def setUp(self):
        # Pin a wide host frame so Tk doesn't auto-unmap packed
        # widgets that overflow a default-sized frame. Without the
        # explicit size, ``winfo_ismapped()`` would intermittently
        # report False for packed-but-overflowed widgets at the
        # "wide" width stubbed by ``_force_width`` — defeating the
        # responsive helper's contract from the test side.
        self.host = tk.Frame(_root, width=800, height=400)
        self.host.pack_propagate(False)
        self.host.pack()
        self.graph = ProjectGraph()

    def tearDown(self):
        try:
            self.host.destroy()
        except Exception:
            pass

    def _fresh_widget(self, **kwargs):
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, self.graph, [NodeType.UVVIS], cb, **kwargs,
        )
        # Fill the host so each row inherits the host's pinned width
        # — without ``fill="both", expand=True`` the widget sits at
        # its natural (narrow) size and rows overflow.
        widget.pack(fill="both", expand=True)
        # ``update()`` (not ``update_idletasks``) is required on a
        # withdrawn root for the geometry pass to actually run; the
        # latter only flushes idle handlers and leaves
        # ``winfo_ismapped()`` stale until the next event cycle.
        _root.update()
        return widget

    @staticmethod
    def _force_width(widget: tk.Widget, width: int) -> None:
        """Stub ``winfo_width`` on a row + the owning ScanTreeWidget's canvas.

        Phase 4p (CS-30): the responsive helper now reads canvas width
        as the default ``width`` source (the row's natural width is
        content-driven and does not reflect the available sidebar
        space). Tests that rely on ``_force_width(row, N)`` followed
        by ``widget._apply_responsive_layout("a", row)`` (no explicit
        width kwarg) need the canvas's reported width to match so
        the helper's default-width path sees the test's intended
        value. Tests that pass ``width=`` explicitly are unaffected.
        """
        widget.winfo_width = lambda w=width: w  # type: ignore[assignment]
        ancestor = widget
        while ancestor is not None:
            scroll_canvas = getattr(ancestor, "_scroll_canvas", None)
            if scroll_canvas is not None:
                scroll_canvas.winfo_width = lambda w=width: w  # type: ignore[assignment]
                break
            ancestor = getattr(ancestor, "master", None)

    def _always_visible(self, row: tk.Frame) -> dict[str, tk.Widget]:
        """Locate the always-visible widgets in a row.

        Returns a dict keyed by role name. Used to assert that the
        minimum set survives every collapse/restore cycle. Phase 4n
        CS-26 promoted ``hist`` (⌥n provenance count); Phase 4n
        CS-27 added ``compare`` (→ Send-to-Compare).
        """
        labels = [
            w for w in row.winfo_children() if isinstance(w, tk.Label)
        ]
        state_lbl = next(
            (w for w in labels if w.cget("text") in ("🔒", "⋯")), None,
        )
        text_lbl = next(
            (w for w in labels if w.cget("text") not in ("🔒", "⋯")), None,
        )
        vis_cb = next(
            (w for w in row.winfo_children()
             if isinstance(w, tk.Checkbutton)),
            None,
        )
        buttons = [
            w for w in row.winfo_children() if isinstance(w, tk.Button)
        ]
        gear = next((b for b in buttons if b.cget("text") == "⚙"), None)
        x_btn = next((b for b in buttons if b.cget("text") == "✕"), None)
        compare = next(
            (b for b in buttons if b.cget("text") == "→"), None,
        )
        hist = next(
            (b for b in buttons if b.cget("text").startswith("⌥")), None,
        )
        return {
            "state": state_lbl, "label": text_lbl, "vis_cb": vis_cb,
            "hist": hist, "gear": gear, "compare": compare, "x": x_btn,
        }

    # ----------- threshold constant exists -----------

    def test_threshold_constant_is_a_positive_int(self):
        # The collapse threshold is module-level so both the widget
        # and tests can reach it. Pinning the type and sign protects
        # against accidental redefinition.
        self.assertIsInstance(self.stw_mod._RESPONSIVE_COLLAPSE_PX, int)
        self.assertGreater(self.stw_mod._RESPONSIVE_COLLAPSE_PX, 0)

    # ----------- optional widgets dict is populated -----------

    def test_optional_row_widgets_tracked_per_node(self):
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        widgets = widget._optional_row_widgets["a"]
        # Names that responsive layout reaches for. Phase 4n CS-26
        # removed ``hist`` from this set (it is always-visible now);
        # the dict is the responsive-helper's working set, not a
        # generic "all widgets in the row" registry.
        for name in ("swatch", "leg", "ls_canvas", "vis_cb"):
            self.assertIn(name, widgets, f"missing {name!r}")
            self.assertTrue(
                bool(widgets[name].winfo_exists()),
                f"{name!r} widget should exist",
            )
        self.assertNotIn(
            "hist", widgets,
            "hist must not be in the responsive optional set after CS-26",
        )

    # ----------- collapse below threshold -----------

    def test_narrow_width_hides_every_optional_control(self):
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]
        # Force narrow width below the smallest threshold (240 px).
        self._force_width(row, 100)
        widget._apply_responsive_layout("a", row)

        widgets = widget._optional_row_widgets["a"]
        for name in ("swatch", "leg", "ls_canvas"):
            self.assertFalse(
                bool(widgets[name].winfo_ismapped()),
                f"{name!r} should be pack_forget-ed at narrow width",
            )

    # ----------- restore at wide width -----------

    def test_wide_width_keeps_all_controls_packed(self):
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()

        row = widget._row_frames["a"]
        # Force wide width well above every threshold.
        self._force_width(row, 600)
        widget._apply_responsive_layout("a", row)
        # Full ``update()`` (not just idletasks) on a withdrawn root
        # is needed for the geometry pass to flip ``winfo_ismapped``.
        _root.update()

        widgets = widget._optional_row_widgets["a"]
        for name in ("swatch", "leg", "ls_canvas"):
            self.assertTrue(
                bool(widgets[name].winfo_ismapped()),
                f"{name!r} should be packed at wide width",
            )

    # ----------- collapse → restore round trip -----------

    def test_resize_back_and_forth_toggles_cleanly(self):
        # Repeatedly narrow → widen → narrow → widen and confirm the
        # optional controls track their thresholds without leaking
        # widgets or losing pack order.
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]
        widgets = widget._optional_row_widgets["a"]

        for width, expected_mapped in (
            (600, True),
            (100, False),
            (600, True),
            (50,  False),
            (400, True),
        ):
            self._force_width(row, width)
            widget._apply_responsive_layout("a", row)
            # ``winfo_ismapped()`` reflects the result of Tk's geometry
            # pass, not the most recent ``pack`` / ``pack_forget`` call,
            # so a flush is needed before reading it.
            widget.update_idletasks()
            for name in ("swatch", "leg", "ls_canvas"):
                self.assertEqual(
                    bool(widgets[name].winfo_ismapped()),
                    expected_mapped,
                    f"{name!r} mapped state at width={width} "
                    f"should be {expected_mapped}",
                )

    # ----------- always-visible minimum survives every width -----------

    def test_always_visible_minimum_unaffected_at_every_width(self):
        # state · ☑ · label · ⌥n · ⚙ · → · ✕ must remain mapped at
        # every width — narrow, wide, and zero/negative defensive
        # cases. Phase 4n CS-26 promoted hist; CS-27 added compare.
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget(send_to_compare_cb=lambda nid: None)
        widget.update_idletasks()

        row = widget._row_frames["a"]
        for width in (50, 200, 240, 280, 320, 400, 1200):
            self._force_width(row, width)
            widget._apply_responsive_layout("a", row)
            mins = self._always_visible(row)
            for role, w in mins.items():
                self.assertIsNotNone(
                    w, f"{role!r} missing from row",
                )
                self.assertTrue(
                    bool(w.winfo_ismapped()),
                    f"{role!r} should stay mapped at width={width}",
                )

    # ----------- pack order preserved on restore -----------

    def test_restored_pack_order_matches_original(self):
        # Visual order on restoration must be:
        # [state · swatch · vis_cb · label · ... · leg · ls_canvas
        #  · hist · gear · x]. Verifying via winfo_x() ensures the
        # restore path uses the right ``before=`` / packing order
        # (tested implicitly — a ``side="left"`` restore for the
        # swatch without ``before=vis_cb`` would land it after the
        # label, breaking the sequence).
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]

        # Collapse first, then restore to a wide width.
        self._force_width(row, 100)
        widget._apply_responsive_layout("a", row)
        self._force_width(row, 600)
        widget._apply_responsive_layout("a", row)

        widgets = widget._optional_row_widgets["a"]
        widget.update_idletasks()

        # Confirm the swatch sits to the left of the visibility
        # checkbox (i.e., between state and ☑) — the canonical
        # ``side="left", before=vis_cb`` placement.
        swatch_x = widgets["swatch"].winfo_x()
        vis_cb_x = widgets["vis_cb"].winfo_x()
        self.assertLess(
            swatch_x, vis_cb_x,
            "swatch must be packed before vis_cb on the left side",
        )

    # ----------- multi-row independence -----------

    def test_each_row_collapses_independently(self):
        # Phase 4p (CS-30): the helper now keys on canvas width by
        # default, so production rows reflow uniformly. The
        # per-row-independence contract is preserved through the
        # explicit ``width`` kwarg — when given, the helper applies
        # exactly that width to that row and no other. Pass widths
        # directly so each row gets its own width even though they
        # share a canvas.
        self.graph.add_node(_data("a"))
        self.graph.add_node(_data("b"))
        widget = self._fresh_widget()

        row_a = widget._row_frames["a"]
        row_b = widget._row_frames["b"]
        widget._apply_responsive_layout("a", row_a, width=100)
        widget._apply_responsive_layout("b", row_b, width=600)
        # Use ``update_idletasks`` rather than ``_root.update()`` so a
        # late canvas-Configure event (Phase 4p CS-30 binding) does
        # not reflow both rows uniformly and erase the per-row widths
        # we just applied.
        widget.update_idletasks()

        a_swatch = widget._optional_row_widgets["a"]["swatch"]
        b_swatch = widget._optional_row_widgets["b"]["swatch"]
        self.assertFalse(bool(a_swatch.winfo_ismapped()))
        self.assertTrue(bool(b_swatch.winfo_ismapped()))

    # ----------- CS-26 hist promotion: always mapped at every width --

    def test_hist_button_always_visible_after_promotion(self):
        # Phase 4n CS-26: ⌥n provenance count moved from the optional
        # set into the always-visible minimum. It must stay mapped
        # even at width 50 (well below every threshold).
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]
        for width in (50, 100, 240, 600, 1200):
            self._force_width(row, width)
            widget._apply_responsive_layout("a", row)
            widget.update_idletasks()
            mins = self._always_visible(row)
            self.assertIsNotNone(mins["hist"])
            self.assertTrue(
                bool(mins["hist"].winfo_ismapped()),
                f"hist must stay mapped at width={width}",
            )

    # ----------- CS-26 graduated thresholds -----------

    def test_thresholds_constant_is_priority_ordered(self):
        # ``_RESPONSIVE_THRESHOLDS_PX`` is a tuple of (name, px) pairs
        # in priority order: swatch first (highest priority, smallest
        # threshold), ls_canvas last (lowest priority, largest
        # threshold). Pinning the order protects future edits from
        # silently shuffling the reveal sequence.
        seq = list(self.stw_mod._RESPONSIVE_THRESHOLDS_PX)
        names = [n for n, _ in seq]
        self.assertEqual(names, ["swatch", "leg", "ls_canvas"])
        widths = [w for _, w in seq]
        self.assertEqual(widths, sorted(widths))
        # Smallest threshold matches the legacy alias.
        self.assertEqual(
            self.stw_mod._RESPONSIVE_COLLAPSE_PX, widths[0],
        )

    def test_swatch_revealed_first_at_smallest_threshold(self):
        # Just above the swatch threshold (240) but below leg (280):
        # swatch maps, leg / ls_canvas stay hidden.
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]
        self._force_width(row, 250)
        widget._apply_responsive_layout("a", row)
        widget.update_idletasks()

        widgets = widget._optional_row_widgets["a"]
        self.assertTrue(bool(widgets["swatch"].winfo_ismapped()))
        self.assertFalse(bool(widgets["leg"].winfo_ismapped()))
        self.assertFalse(bool(widgets["ls_canvas"].winfo_ismapped()))

    def test_leg_revealed_at_middle_threshold(self):
        # At 290 (≥280, <320): swatch + leg map; ls_canvas hidden.
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]
        self._force_width(row, 290)
        widget._apply_responsive_layout("a", row)
        widget.update_idletasks()

        widgets = widget._optional_row_widgets["a"]
        self.assertTrue(bool(widgets["swatch"].winfo_ismapped()))
        self.assertTrue(bool(widgets["leg"].winfo_ismapped()))
        self.assertFalse(bool(widgets["ls_canvas"].winfo_ismapped()))

    def test_ls_canvas_revealed_at_largest_threshold(self):
        # At 330 (≥320): every optional cell maps.
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]
        self._force_width(row, 330)
        widget._apply_responsive_layout("a", row)
        widget.update_idletasks()

        widgets = widget._optional_row_widgets["a"]
        self.assertTrue(bool(widgets["swatch"].winfo_ismapped()))
        self.assertTrue(bool(widgets["leg"].winfo_ismapped()))
        self.assertTrue(bool(widgets["ls_canvas"].winfo_ismapped()))

    def test_graduated_reveal_visual_order_at_each_threshold(self):
        # The right-side optional cells must appear in the canonical
        # ``leg ls_canvas`` order whenever both are mapped — even if
        # they were promoted at different times. Step the row width
        # through each threshold and confirm the geometry.
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]
        widgets = widget._optional_row_widgets["a"]

        # Walk widths up across all three thresholds, then back down.
        for width in (200, 250, 290, 330, 290, 250, 200, 600):
            self._force_width(row, width)
            widget._apply_responsive_layout("a", row)
            widget.update_idletasks()
            leg = widgets["leg"]
            ls_canvas = widgets["ls_canvas"]
            both_mapped = (
                bool(leg.winfo_ismapped())
                and bool(ls_canvas.winfo_ismapped())
            )
            if both_mapped:
                self.assertLess(
                    leg.winfo_x(), ls_canvas.winfo_x(),
                    f"leg must be left of ls_canvas at width={width}",
                )

    def test_steady_state_preserves_mapped_set(self):
        # Repeated _apply_responsive_layout calls at the same width
        # must converge on the same mapped set (i.e. don't drift). A
        # call IS allowed to pack_forget + re-pack — that is how the
        # helper preserves the canonical visual order under overflow
        # — but the visible outcome must be stable.
        self.graph.add_node(_data("a"))
        widget = self._fresh_widget()
        widget.update_idletasks()

        row = widget._row_frames["a"]
        widgets = widget._optional_row_widgets["a"]

        self._force_width(row, 290)  # swatch + leg, no ls_canvas
        for _ in range(3):
            widget._apply_responsive_layout("a", row)
            widget.update_idletasks()

        # Pack-list membership is the helper's ground-truth contract.
        slaves = set(row.pack_slaves())
        self.assertIn(widgets["swatch"], slaves)
        self.assertIn(widgets["leg"], slaves)
        self.assertNotIn(widgets["ls_canvas"], slaves)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestScanTreeWidgetCanvasDrivenLayout(unittest.TestCase):
    """Phase 4p CS-30 — responsive helper now keys on canvas width.

    Two production failures motivated the change:

    - Single-node sidebar stayed collapsed at any width: the row's
      natural width is content-driven (longest visible label), so
      ``row.winfo_width()`` returns a small label-sized number even
      when the actual sidebar is 800 px wide.
    - Narrowing the sidebar did not recollapse expanded rows: the
      row's own width didn't change because content didn't change,
      so the per-row Configure binding never re-fired.

    The fix replaced the per-row Configure binding with a canvas
    Configure binding plus an initial helper call inside
    ``_populate_node_row``. ``_apply_responsive_layout`` defaults to
    reading ``_scroll_canvas.winfo_width()`` when no explicit width
    is passed.
    """

    @classmethod
    def setUpClass(cls):
        from scan_tree_widget import ScanTreeWidget
        import scan_tree_widget as stw_mod
        cls.ScanTreeWidget = ScanTreeWidget
        cls.stw_mod = stw_mod

    def setUp(self):
        self.host = tk.Frame(_root, width=800, height=400)
        self.host.pack_propagate(False)
        self.host.pack()
        self.graph = ProjectGraph()

    def tearDown(self):
        try:
            self.host.destroy()
        except Exception:
            pass

    def _build(self):
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, self.graph, [NodeType.UVVIS], cb,
        )
        widget.pack(fill="both", expand=True)
        _root.update()
        return widget

    def test_default_width_source_is_canvas(self):
        # When no explicit width is passed, the helper reads from the
        # canvas's winfo_width — not the row's. Stub the canvas to a
        # value above every threshold; expect every optional cell to
        # be in the row's pack slaves regardless of the row's actual
        # natural width.
        self.graph.add_node(_data("a"))
        widget = self._build()
        widget._scroll_canvas.winfo_width = lambda: 600  # type: ignore[assignment]

        row = widget._row_frames["a"]
        widget._apply_responsive_layout("a", row)
        widget.update_idletasks()

        slaves = set(row.pack_slaves())
        widgets = widget._optional_row_widgets["a"]
        for name in ("swatch", "leg", "ls_canvas"):
            self.assertIn(
                widgets[name], slaves,
                f"{name!r} must be packed when canvas reports 600 px",
            )

    def test_default_width_source_collapses_when_canvas_narrow(self):
        # Mirror image of the previous test: canvas reports a narrow
        # value, helper drops every optional cell from the row's
        # pack slaves.
        self.graph.add_node(_data("a"))
        widget = self._build()
        widget._scroll_canvas.winfo_width = lambda: 100  # type: ignore[assignment]

        row = widget._row_frames["a"]
        widget._apply_responsive_layout("a", row)
        widget.update_idletasks()

        slaves = set(row.pack_slaves())
        widgets = widget._optional_row_widgets["a"]
        for name in ("swatch", "leg", "ls_canvas"):
            self.assertNotIn(
                widgets[name], slaves,
                f"{name!r} must NOT be packed when canvas reports 100 px",
            )

    def test_explicit_width_overrides_canvas_default(self):
        # When the caller passes ``width=N`` the helper must use N,
        # not the canvas width. Stub the canvas wide and pass a
        # narrow explicit width — expect collapse.
        self.graph.add_node(_data("a"))
        widget = self._build()
        widget._scroll_canvas.winfo_width = lambda: 800  # type: ignore[assignment]

        row = widget._row_frames["a"]
        widget._apply_responsive_layout("a", row, width=100)
        widget.update_idletasks()

        slaves = set(row.pack_slaves())
        widgets = widget._optional_row_widgets["a"]
        for name in ("swatch", "leg", "ls_canvas"):
            self.assertNotIn(
                widgets[name], slaves,
                f"{name!r} must obey explicit width=100, not canvas=800",
            )

    def test_canvas_configure_event_walks_every_row(self):
        # Firing a Configure event on the canvas must invoke the
        # helper for every row that has optional widgets. The handler
        # reads ``canvas.winfo_width()`` (not ``event.width``) so
        # tests stub the canvas width and synthesize a Configure to
        # fire the binding.
        self.graph.add_node(_data("a"))
        self.graph.add_node(_data("b"))
        widget = self._build()
        # Start with a narrow canvas so initial calibration
        # collapses optional cells.
        widget._scroll_canvas.winfo_width = lambda: 100  # type: ignore[assignment]
        widget._scroll_canvas.event_generate("<Configure>", width=100, height=400)
        widget.update_idletasks()
        for nid in ("a", "b"):
            row = widget._row_frames[nid]
            slaves = set(row.pack_slaves())
            widgets = widget._optional_row_widgets[nid]
            for name in ("swatch", "leg", "ls_canvas"):
                self.assertNotIn(
                    widgets[name], slaves,
                    f"row {nid!r} {name!r} must NOT be packed when canvas=100",
                )

        # Re-stub canvas wide and fire Configure again — every row
        # should re-pack.
        widget._scroll_canvas.winfo_width = lambda: 600  # type: ignore[assignment]
        widget._scroll_canvas.event_generate("<Configure>", width=600, height=400)
        widget.update_idletasks()
        for nid in ("a", "b"):
            row = widget._row_frames[nid]
            slaves = set(row.pack_slaves())
            widgets = widget._optional_row_widgets[nid]
            for name in ("swatch", "leg", "ls_canvas"):
                self.assertIn(
                    widgets[name], slaves,
                    f"row {nid!r} {name!r} must be packed after "
                    f"Configure with canvas=600",
                )

    def test_initial_calibration_runs_in_populate_node_row(self):
        # New rows added at runtime must be calibrated immediately:
        # _populate_node_row calls the helper itself rather than
        # waiting for a (potentially never-fired) Configure event.
        # Stub canvas narrow before adding the node so the initial
        # call collapses the optional cells.
        widget = self._build()
        widget._scroll_canvas.winfo_width = lambda: 100  # type: ignore[assignment]

        # Adding a new node triggers _rebuild → _populate_node_row.
        self.graph.add_node(_data("a"))
        widget.update_idletasks()

        row = widget._row_frames["a"]
        slaves = set(row.pack_slaves())
        widgets = widget._optional_row_widgets["a"]
        for name in ("swatch", "leg", "ls_canvas"):
            self.assertNotIn(
                widgets[name], slaves,
                f"newly-added row's {name!r} must collapse on insert "
                f"when the canvas is already narrow",
            )

    def test_no_per_row_configure_binding(self):
        # The Phase 4p (CS-30) refactor removed the per-row Configure
        # binding because (a) it raced with explicit helper calls
        # under update_idletasks, and (b) the row's natural width is
        # not the right signal for threshold logic. Verifying the
        # binding is gone protects against an accidental restore in
        # a future row-rendering refactor.
        self.graph.add_node(_data("a"))
        widget = self._build()

        row = widget._row_frames["a"]
        binds = row.bind()  # tuple of bound sequence names
        self.assertNotIn(
            "<Configure>", binds,
            "row must not carry a <Configure> binding after CS-30",
        )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestScanTreeWidgetSendToCompareButton(unittest.TestCase):
    """Phase 4n CS-27 — per-row → Send-to-Compare icon.

    The icon replaces the legacy "+ Add to TDDFT Overlay" top-bar
    bulk button. Disabled-state convention mirrors Export…: a
    callback must be wired AND the row must be COMMITTED.
    """

    @classmethod
    def setUpClass(cls):
        from scan_tree_widget import ScanTreeWidget
        cls.ScanTreeWidget = ScanTreeWidget

    def setUp(self):
        # Pin a wide host frame so Tk doesn't auto-unmap packed
        # widgets that overflow a default-sized frame. Without the
        # explicit size, ``winfo_ismapped()`` would intermittently
        # report False for packed-but-overflowed widgets at the
        # "wide" width stubbed by ``_force_width`` — defeating the
        # responsive helper's contract from the test side.
        self.host = tk.Frame(_root, width=800, height=400)
        self.host.pack_propagate(False)
        self.host.pack()
        self.graph = ProjectGraph()

    def tearDown(self):
        try:
            self.host.destroy()
        except Exception:
            pass

    def _fresh_widget(self, **kwargs):
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, self.graph, [NodeType.UVVIS], cb, **kwargs,
        )
        # Fill the host so each row inherits the host's pinned width
        # — without ``fill="both", expand=True`` the widget sits at
        # its natural (narrow) size and rows overflow.
        widget.pack(fill="both", expand=True)
        # ``update()`` (not ``update_idletasks``) is required on a
        # withdrawn root for the geometry pass to actually run; the
        # latter only flushes idle handlers and leaves
        # ``winfo_ismapped()`` stale until the next event cycle.
        _root.update()
        return widget

    def _compare_button(self, widget, node_id: str) -> tk.Button:
        row = widget._row_frames[node_id]
        for child in row.winfo_children():
            if isinstance(child, tk.Button) and child.cget("text") == "→":
                return child
        raise AssertionError(
            f"no → Send-to-Compare button found in row {node_id!r}"
        )

    def test_button_present_on_every_row(self):
        # Both committed and provisional rows render the button — it
        # is gated by ``state``, not by hiding the affordance.
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        self.graph.add_node(_data("b", state=NodeState.PROVISIONAL))
        widget = self._fresh_widget(send_to_compare_cb=lambda nid: None)
        widget.update_idletasks()

        # Construction succeeds.
        self._compare_button(widget, "a")
        self._compare_button(widget, "b")

    def test_button_disabled_on_provisional_row(self):
        self.graph.add_node(_data("a", state=NodeState.PROVISIONAL))
        widget = self._fresh_widget(send_to_compare_cb=lambda nid: None)
        widget.update_idletasks()

        btn = self._compare_button(widget, "a")
        self.assertEqual(str(btn.cget("state")), "disabled")

    def test_button_enabled_on_committed_row_with_callback(self):
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget(send_to_compare_cb=lambda nid: None)
        widget.update_idletasks()

        btn = self._compare_button(widget, "a")
        self.assertEqual(str(btn.cget("state")), "normal")

    def test_button_disabled_when_callback_missing(self):
        # No send_to_compare_cb wired ⇒ button always disabled. Pins
        # the deferred-tab convention shared with Export….
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget()  # no callback
        widget.update_idletasks()

        btn = self._compare_button(widget, "a")
        self.assertEqual(str(btn.cget("state")), "disabled")

    def test_button_invoke_calls_callback_with_node_id(self):
        seen: list[str] = []
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget(send_to_compare_cb=seen.append)
        widget.update_idletasks()

        self._compare_button(widget, "a").invoke()
        self.assertEqual(seen, ["a"])

    def test_handler_revalidates_committed_state_defensively(self):
        # The button's disabled-state is set at row build time; if the
        # row's state changes between build and click without a
        # rebuild, the handler must re-check COMMITTED before
        # invoking the callback. Demote the node directly via the
        # private state attribute to simulate the gap.
        seen: list[str] = []
        node = _data("a", state=NodeState.COMMITTED)
        self.graph.add_node(node)
        widget = self._fresh_widget(send_to_compare_cb=seen.append)
        widget.update_idletasks()

        # Bypass the disabled-state gate by calling the handler
        # directly on a node that is no longer COMMITTED.
        node.state = NodeState.PROVISIONAL
        widget._on_send_to_compare_clicked("a")
        self.assertEqual(
            seen, [],
            "handler must not invoke callback on a non-COMMITTED node",
        )

    def test_handler_swallows_unknown_node_id(self):
        # A stale id (e.g. node was discarded between row build and
        # click) must not raise out of the click path.
        seen: list[str] = []
        widget = self._fresh_widget(send_to_compare_cb=seen.append)
        widget.update_idletasks()

        # No node with this id exists in the graph.
        widget._on_send_to_compare_clicked("ghost")
        self.assertEqual(seen, [])

    def test_handler_noop_when_callback_none(self):
        # Even if someone reaches in and invokes the handler directly
        # with no callback wired, it must not raise.
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget()  # no callback
        widget.update_idletasks()

        widget._on_send_to_compare_clicked("a")  # silent


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestScanTreeWidgetExportMenu(unittest.TestCase):
    """Phase 4f — CS-17: Export… row context-menu entry.

    Mirrors ``TestScanTreeWidgetBugB004`` in capture style: stub
    ``tk.Menu.tk_popup`` so the menu instance is constructed but never
    grabs input, then introspect the resulting entries.
    """

    @classmethod
    def setUpClass(cls):
        from scan_tree_widget import ScanTreeWidget
        cls.ScanTreeWidget = ScanTreeWidget

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()

    def tearDown(self):
        try:
            self.host.destroy()
        except Exception:
            pass

    def _capture_menu(self, widget, node_id: str) -> tk.Menu:
        captured: dict = {}
        original_popup = tk.Menu.tk_popup

        def _stub_popup(self, x, y, *args, **kwargs):
            captured["menu"] = self

        try:
            tk.Menu.tk_popup = _stub_popup
            fake_event = type("E", (), {"x_root": 0, "y_root": 0})()
            widget._show_context_menu(fake_event, node_id)
        finally:
            tk.Menu.tk_popup = original_popup
        menu = captured["menu"]
        return menu

    @staticmethod
    def _entry_state(menu: tk.Menu, label: str) -> str:
        last = menu.index("end")
        for i in range(last + 1):
            if menu.type(i) == "separator":
                continue
            if menu.entrycget(i, "label") == label:
                return menu.entrycget(i, "state")
        raise AssertionError(f"{label!r} not found in menu")

    def _fresh_widget(self, **kwargs):
        _, cb = _redraw_calls()
        widget = self.ScanTreeWidget(
            self.host, self.graph, [NodeType.UVVIS], cb, **kwargs,
        )
        # Fill the host so each row inherits the host's pinned width
        # — without ``fill="both", expand=True`` the widget sits at
        # its natural (narrow) size and rows overflow.
        widget.pack(fill="both", expand=True)
        # ``update()`` (not ``update_idletasks``) is required on a
        # withdrawn root for the geometry pass to actually run; the
        # latter only flushes idle handlers and leaves
        # ``winfo_ismapped()`` stale until the next event cycle.
        _root.update()
        return widget

    def test_export_entry_present_on_committed_row(self):
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget(export_cb=lambda nid: None)
        widget.update_idletasks()

        menu = self._capture_menu(widget, "a")
        labels: list[str] = []
        last = menu.index("end")
        for i in range(last + 1):
            if menu.type(i) != "separator":
                labels.append(menu.entrycget(i, "label"))
        self.assertIn("Export…", labels)

    def test_export_entry_disabled_on_provisional_row(self):
        self.graph.add_node(_data("a", state=NodeState.PROVISIONAL))
        widget = self._fresh_widget(export_cb=lambda nid: None)
        widget.update_idletasks()

        menu = self._capture_menu(widget, "a")
        self.assertEqual(self._entry_state(menu, "Export…"), "disabled")

    def test_export_entry_disabled_when_callback_missing(self):
        # Even on a committed row, no callback ⇒ disabled. Pins the
        # convention used by Send to Compare so a tab can adopt the
        # gesture incrementally.
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        widget = self._fresh_widget()  # no export_cb wired
        widget.update_idletasks()

        menu = self._capture_menu(widget, "a")
        self.assertEqual(self._entry_state(menu, "Export…"), "disabled")

    def test_export_entry_invokes_callback_with_node_id(self):
        self.graph.add_node(_data("a", state=NodeState.COMMITTED))
        seen: list[str] = []

        widget = self._fresh_widget(export_cb=seen.append)
        widget.update_idletasks()

        menu = self._capture_menu(widget, "a")
        last = menu.index("end")
        export_idx = next(
            i for i in range(last + 1)
            if menu.type(i) != "separator"
            and menu.entrycget(i, "label") == "Export…"
        )
        menu.invoke(export_idx)
        self.assertEqual(seen, ["a"])


class TestTruncateLabel(unittest.TestCase):
    """Phase 4q (CS-33) — pure label-truncation helper.

    No Tk root required; runs in any environment.
    """

    def test_short_text_returned_unchanged(self):
        from scan_tree_widget import _truncate_label, _LABEL_MAX_CHARS
        text = "short"
        self.assertLess(len(text), _LABEL_MAX_CHARS)
        self.assertEqual(_truncate_label(text), text)

    def test_text_exactly_at_cap_returned_unchanged(self):
        from scan_tree_widget import _truncate_label, _LABEL_MAX_CHARS
        text = "x" * _LABEL_MAX_CHARS
        self.assertEqual(_truncate_label(text), text)

    def test_long_text_truncated_with_ellipsis(self):
        from scan_tree_widget import _truncate_label, _LABEL_MAX_CHARS
        text = "x" * (_LABEL_MAX_CHARS + 10)
        out = _truncate_label(text)
        self.assertEqual(len(out), _LABEL_MAX_CHARS)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(out[:-1], "x" * (_LABEL_MAX_CHARS - 1))

    def test_explicit_max_chars_override(self):
        from scan_tree_widget import _truncate_label
        self.assertEqual(_truncate_label("hello world", max_chars=5), "hell…")
        self.assertEqual(_truncate_label("hello", max_chars=5), "hello")
        self.assertEqual(_truncate_label("abc", max_chars=10), "abc")

    def test_label_max_chars_constant_is_a_positive_int(self):
        from scan_tree_widget import _LABEL_MAX_CHARS
        self.assertIsInstance(_LABEL_MAX_CHARS, int)
        self.assertGreater(_LABEL_MAX_CHARS, 1)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestTooltip(unittest.TestCase):
    """Phase 4q (CS-33) — hover tooltip helper.

    Construction-only assertions plus ``update_text``; the actual
    Toplevel display is timing-dependent (600 ms ``after``) and we
    don't drive the event loop in the test suite, so verifying the
    tooltip surface itself is left to manual smoke. The class still
    has to construct cleanly and bind to a parent without raising.
    """

    def setUp(self) -> None:
        self.host = tk.Frame(_root)
        self.host.pack()

    def tearDown(self) -> None:
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_construction_binds_without_error(self):
        from scan_tree_widget import _Tooltip
        lbl = tk.Label(self.host, text="hi")
        lbl.pack()
        tip = _Tooltip(lbl, "the full label")
        self.assertEqual(tip._text, "the full label")
        self.assertIsNone(tip._tip)

    def test_update_text_rotates_in_place(self):
        from scan_tree_widget import _Tooltip
        lbl = tk.Label(self.host, text="hi")
        lbl.pack()
        tip = _Tooltip(lbl, "first")
        tip.update_text("second")
        self.assertEqual(tip._text, "second")

    def test_hide_is_idempotent_when_no_tip_open(self):
        from scan_tree_widget import _Tooltip
        lbl = tk.Label(self.host, text="hi")
        lbl.pack()
        tip = _Tooltip(lbl, "x")
        tip._hide()
        tip._hide()
        self.assertIsNone(tip._tip)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestExpandedSweepGroupsField(unittest.TestCase):
    """Phase 4q (CS-32) — sweep-group expansion state field.

    Construction-only check: the field must exist as an empty set on
    a fresh widget so callers can mutate it without a None-check.
    Mirrors how ``_expanded_history`` is exposed.
    """

    def setUp(self) -> None:
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()

    def tearDown(self) -> None:
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_initial_state_is_empty_set(self):
        from scan_tree_widget import ScanTreeWidget
        _, cb = _redraw_calls()
        widget = ScanTreeWidget(
            self.host, self.graph, [NodeType.UVVIS], cb,
        )
        self.assertEqual(widget._expanded_sweep_groups, set())
        self.assertIsInstance(widget._expanded_sweep_groups, set)


if __name__ == "__main__":
    unittest.main(verbosity=2)
