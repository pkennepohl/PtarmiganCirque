"""Tests for style_dialog.py.

Mirrors the structure of ``test_scan_tree_widget.py``: construct a
real ``tk.Tk`` root and a real ``ProjectGraph``, then drive the
dialog and observe the resulting widget and graph state. Headless
environments where ``tk.Tk()`` cannot be constructed are skipped.

Run with the project venv:

    venv/Scripts/python run_tests.py
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
except Exception:  # pragma: no cover — headless CI only
    _root = None
    _HAS_DISPLAY = False


from graph import GraphEventType, ProjectGraph
from nodes import DataNode, NodeState, NodeType


# ---- helpers --------------------------------------------------------

def _data(nid: str, ntype: NodeType = NodeType.UVVIS,
          state: NodeState = NodeState.PROVISIONAL,
          label: str | None = None,
          style: dict | None = None) -> DataNode:
    return DataNode(
        id=nid,
        type=ntype,
        arrays={"x": np.arange(3)},
        metadata={},
        label=label or nid,
        state=state,
        style=dict(style) if style else {},
    )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestStyleDialogShell(unittest.TestCase):
    """Construction, registry/focus, snapshot+cancel, live external sync."""

    @classmethod
    def setUpClass(cls):
        # Lazy import: the module touches tk at module level only via
        # ttk on first widget creation, but importing it before Tk is
        # available is harmless. Mirror the lazy pattern used in
        # test_scan_tree_widget anyway, for symmetry.
        import style_dialog
        cls.style_dialog = style_dialog
        cls.StyleDialog = style_dialog.StyleDialog
        cls.open_style_dialog = staticmethod(style_dialog.open_style_dialog)

    def setUp(self):
        # Per-test registry reset so a leaked entry from one test
        # cannot poison the next.
        self.style_dialog._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()

    def tearDown(self):
        # Destroy any dialogs left open by the test.
        for dlg in list(self.style_dialog._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.style_dialog._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ----------- construction -----------

    def test_constructs_with_real_graph(self):
        self.graph.add_node(_data("a", style={"color": "#ff0000",
                                              "linewidth": 2.0}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        # Title carries the node label (CS-05).
        self.assertIn("Style", dlg.title())
        self.assertIn("a", dlg.title())
        # Universal section vars are populated from the node's style.
        self.assertEqual(dlg._control_vars["color"].get(), "#ff0000")
        self.assertAlmostEqual(dlg._control_vars["linewidth"].get(), 2.0)

    def test_construct_with_unknown_node_id_raises(self):
        with self.assertRaises(KeyError):
            self.StyleDialog(self.host, self.graph, "missing")

    def test_construct_subscribes_to_graph(self):
        self.graph.add_node(_data("a"))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        self.assertIn(dlg._on_graph_event, self.graph._subscribers)

    # ----------- factory: focus existing dialog -----------

    def test_open_twice_returns_same_toplevel(self):
        self.graph.add_node(_data("a"))
        first = self.open_style_dialog(self.host, self.graph, "a")
        second = self.open_style_dialog(self.host, self.graph, "a")
        self.assertIs(first, second)

    def test_open_two_different_nodes_creates_two_dialogs(self):
        self.graph.add_node(_data("a"))
        self.graph.add_node(_data("b"))
        first = self.open_style_dialog(self.host, self.graph, "a")
        second = self.open_style_dialog(self.host, self.graph, "b")
        self.assertIsNot(first, second)

    # ----------- slider change writes via graph.set_style -----------

    def test_slider_change_writes_partial_via_graph(self):
        self.graph.add_node(_data("a", style={"linewidth": 1.5}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        events: list = []
        self.graph.subscribe(events.append)

        # Simulate a slider change.
        dlg._control_vars["linewidth"].set(3.0)
        dlg.update_idletasks()

        # Graph node's style now has the new linewidth and only the
        # linewidth (merge semantics).
        node = self.graph.get_node("a")
        self.assertAlmostEqual(node.style["linewidth"], 3.0)

        # The most-recent NODE_STYLE_CHANGED carries linewidth in its
        # partial.
        style_events = [
            e for e in events
            if e.type == GraphEventType.NODE_STYLE_CHANGED
        ]
        self.assertGreaterEqual(len(style_events), 1)
        last = style_events[-1]
        self.assertIn("linewidth", last.payload["partial"])
        self.assertAlmostEqual(
            float(last.payload["partial"]["linewidth"]), 3.0,
        )

    # ----------- external graph.set_style refreshes widgets -----------

    def test_external_set_style_updates_widget_value(self):
        self.graph.add_node(_data("a", style={"linewidth": 1.5}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        # External writer (sibling dialog, row control, etc.) bumps
        # the value. The dialog's widget must reflect the new value.
        self.graph.set_style("a", {"linewidth": 4.2})
        dlg.update_idletasks()

        self.assertAlmostEqual(
            dlg._control_vars["linewidth"].get(), 4.2,
        )

    def test_external_refresh_does_not_recurse(self):
        """A NODE_STYLE_CHANGED handler must not loop through set_style."""
        self.graph.add_node(_data("a", style={"linewidth": 1.5}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        events: list = []
        self.graph.subscribe(events.append)

        self.graph.set_style("a", {"linewidth": 2.5})
        dlg.update_idletasks()

        # Exactly one NODE_STYLE_CHANGED — no echo from a recursive
        # write-back.
        style_events = [
            e for e in events
            if e.type == GraphEventType.NODE_STYLE_CHANGED
        ]
        self.assertEqual(len(style_events), 1)

    # ----------- snapshot + cancel -----------

    def test_cancel_restores_original_style(self):
        self.graph.add_node(_data("a", style={
            "color": "#ff0000",
            "linewidth": 1.5,
            "alpha": 0.9,
        }))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        # Mutate via the dialog (live update).
        dlg._control_vars["linewidth"].set(4.0)
        dlg.update_idletasks()
        self.assertAlmostEqual(
            self.graph.get_node("a").style["linewidth"], 4.0,
        )

        # Cancel reverts.
        dlg._do_cancel()
        node = self.graph.get_node("a")
        self.assertAlmostEqual(node.style["linewidth"], 1.5)
        self.assertEqual(node.style["color"], "#ff0000")

    # ----------- apply keeps dialog open -----------

    def test_apply_keeps_dialog_open(self):
        self.graph.add_node(_data("a", style={"linewidth": 1.5}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        dlg._control_vars["linewidth"].set(2.5)
        dlg.update_idletasks()

        dlg._do_apply()
        # Dialog still alive.
        self.assertTrue(bool(dlg.winfo_exists()))
        # Node carries the applied value.
        self.assertAlmostEqual(
            self.graph.get_node("a").style["linewidth"], 2.5,
        )

    # ----------- close cleanly drops the subscription -----------

    def test_destroy_drops_graph_subscription(self):
        self.graph.add_node(_data("a"))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        self.assertIn(dlg._on_graph_event, self.graph._subscribers)

        dlg.destroy()
        self.assertNotIn(dlg._on_graph_event, self.graph._subscribers)

    def test_destroy_clears_module_registry_entry(self):
        self.graph.add_node(_data("a"))
        dlg = self.open_style_dialog(self.host, self.graph, "a")
        self.assertIs(self.style_dialog._open_dialogs.get("a"), dlg)
        dlg.destroy()
        self.assertNotIn("a", self.style_dialog._open_dialogs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
