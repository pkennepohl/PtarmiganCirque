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


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestStyleDialogConditionalSections(unittest.TestCase):
    """Sections shown/hidden depending on the node's NodeType (CS-05)."""

    @classmethod
    def setUpClass(cls):
        import style_dialog
        cls.style_dialog = style_dialog
        cls.StyleDialog = style_dialog.StyleDialog

    def setUp(self):
        self.style_dialog._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()

    def tearDown(self):
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

    @staticmethod
    def _section_titles(dlg) -> list[str]:
        titles: list[str] = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.LabelFrame):
                    titles.append(c.cget("text"))
                walk(c)
        walk(dlg)
        return titles

    # All possible section titles — used to assert "no other sections."
    _ALL_SECTIONS = {
        "Markers", "Broadening", "Energy shift and scale",
        "Envelope", "Sticks", "Component visibility",
        "Uncertainty band", "Compound result components",
    }

    def _open(self, ntype: NodeType):
        self.graph.add_node(_data("a", ntype))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        return dlg

    def _assert_only(self, dlg, expected: set[str]):
        titles = set(self._section_titles(dlg))
        self.assertEqual(
            titles & self._ALL_SECTIONS, expected,
            f"section set mismatch: got {sorted(titles)}, "
            f"expected {sorted(expected)}",
        )

    # ---- types with no conditional section ----

    def test_uvvis_has_no_conditional_sections(self):
        dlg = self._open(NodeType.UVVIS)
        self._assert_only(dlg, set())

    def test_raw_file_has_no_conditional_sections(self):
        dlg = self._open(NodeType.RAW_FILE)
        self._assert_only(dlg, set())

    # ---- types in the markers group ----

    def test_xanes_has_markers_only(self):
        dlg = self._open(NodeType.XANES)
        self._assert_only(dlg, {"Markers"})

    def test_exafs_has_markers_only(self):
        dlg = self._open(NodeType.EXAFS)
        self._assert_only(dlg, {"Markers"})

    def test_deglitched_has_markers_only(self):
        dlg = self._open(NodeType.DEGLITCHED)
        self._assert_only(dlg, {"Markers"})

    def test_averaged_has_markers_only(self):
        dlg = self._open(NodeType.AVERAGED)
        self._assert_only(dlg, {"Markers"})

    # ---- TDDFT (the heavyweight) ----

    def test_tddft_has_full_calculated_set(self):
        dlg = self._open(NodeType.TDDFT)
        self._assert_only(dlg, {
            "Broadening", "Energy shift and scale",
            "Envelope", "Sticks", "Component visibility",
        })

    # ---- BXAS_RESULT (with both stubs) ----

    def test_bxas_result_includes_stubs(self):
        dlg = self._open(NodeType.BXAS_RESULT)
        self._assert_only(dlg, {
            "Broadening", "Energy shift and scale", "Envelope",
            "Uncertainty band", "Compound result components",
        })

    def test_bxas_uncertainty_section_is_oq002_stub(self):
        """The uncertainty section must NOT silently be empty.

        OQ-002 (uncertainty band schema) blocks the real controls; the
        section header is present and contains a Label that flags the
        gap so it's visible rather than silent.
        """
        dlg = self._open(NodeType.BXAS_RESULT)
        # Find the LabelFrame and assert it contains a Label
        # mentioning "OQ-002".
        found = False
        for child in self._all_descendants(dlg):
            if (isinstance(child, tk.LabelFrame)
                    and child.cget("text") == "Uncertainty band"):
                for sub in child.winfo_children():
                    if isinstance(sub, tk.Label) and "OQ-002" in sub.cget(
                        "text"
                    ):
                        found = True
                        break
                break
        self.assertTrue(
            found,
            "Uncertainty band stub must contain an OQ-002 reference",
        )

    # ---- FEFF_PATHS (energy shift / scale only) ----

    def test_feff_paths_has_energy_shift_only(self):
        dlg = self._open(NodeType.FEFF_PATHS)
        self._assert_only(dlg, {"Energy shift and scale"})

    # ---- conditional section writes through the graph ----

    def test_marker_size_change_writes_via_graph(self):
        """Conditional section controls also route through set_style."""
        self.graph.add_node(_data("a", NodeType.XANES,
                                  style={"marker_size": 4}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        dlg._control_vars["marker_size"].set(8)
        dlg.update_idletasks()

        self.assertEqual(self.graph.get_node("a").style["marker_size"], 8)

    @staticmethod
    def _all_descendants(w):
        out = []
        for c in w.winfo_children():
            out.append(c)
            out.extend(
                TestStyleDialogConditionalSections._all_descendants(c)
            )
        return out


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestStyleDialogApplyToAll(unittest.TestCase):
    """Per-parameter ∀ and bottom ∀ Apply to All wiring (CS-05)."""

    @classmethod
    def setUpClass(cls):
        import style_dialog
        cls.style_dialog = style_dialog
        cls.StyleDialog = style_dialog.StyleDialog

    def setUp(self):
        self.style_dialog._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()

    def tearDown(self):
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

    @staticmethod
    def _find_apply_one_buttons(parent) -> list:
        """Walk the widget tree for per-row ∀ buttons.

        The bottom Apply-to-All button has text "∀  Apply to All" with
        a different label so it does not match.
        """
        out = []
        for c in parent.winfo_children():
            if isinstance(c, tk.Button) and c.cget("text") == "∀":
                out.append(c)
            out.extend(
                TestStyleDialogApplyToAll._find_apply_one_buttons(c)
            )
        return out

    # ---- per-parameter ∀ ----

    def test_delegate_apply_one_calls_callback(self):
        """The dialog forwards (key, value) to on_apply_to_all."""
        self.graph.add_node(_data("a", style={"linewidth": 2.5}))
        seen: list = []
        dlg = self.StyleDialog(
            self.host, self.graph, "a",
            on_apply_to_all=lambda k, v: seen.append((k, v)),
        )
        dlg._delegate_apply_one("linewidth", 3.5)
        self.assertEqual(seen, [("linewidth", 3.5)])
        # Self-write too: the local node ends up with the value so the
        # dialog's widgets stay in sync with the graph.
        self.assertAlmostEqual(
            self.graph.get_node("a").style["linewidth"], 3.5,
        )

    def test_per_row_buttons_emit_one_call_per_universal_key(self):
        """Invoking every per-row ∀ records the universal-section keys."""
        self.graph.add_node(_data("a", style={
            "linestyle": "dashed",
            "linewidth": 2.5,
            "alpha": 0.7,
            "color": "#ff0000",
            "fill": True,
            "fill_alpha": 0.2,
        }))
        seen: list = []
        dlg = self.StyleDialog(
            self.host, self.graph, "a",
            on_apply_to_all=lambda k, v: seen.append((k, v)),
        )
        dlg.update_idletasks()

        # Universal section has six per-row ∀ buttons.
        btns = self._find_apply_one_buttons(dlg)
        self.assertEqual(
            len(btns), 6,
            "expected one ∀ per universal-section row",
        )
        for b in btns:
            b.invoke()

        keys = [k for (k, _) in seen]
        self.assertCountEqual(
            keys,
            ["linestyle", "linewidth", "alpha",
             "color", "fill", "fill_alpha"],
        )

    # ---- bottom ∀ Apply to All ----

    def test_bottom_apply_all_fans_out_all_except_colour(self):
        """Bottom ∀ button delegates every universal key except colour."""
        self.graph.add_node(_data("a", style={
            "linestyle": "dashed",
            "linewidth": 2.5,
            "alpha": 0.7,
            "color": "#ff0000",
            "fill": True,
            "fill_alpha": 0.2,
        }))
        seen: list = []
        dlg = self.StyleDialog(
            self.host, self.graph, "a",
            on_apply_to_all=lambda k, v: seen.append((k, v)),
        )
        dlg.update_idletasks()

        dlg._apply_all_btn.invoke()

        keys = [k for (k, _) in seen]
        self.assertNotIn("color", keys)
        self.assertCountEqual(
            keys,
            ["linestyle", "linewidth", "alpha", "fill", "fill_alpha"],
        )
        # Values match the graph state.
        as_dict = dict(seen)
        self.assertEqual(as_dict["linestyle"], "dashed")
        self.assertAlmostEqual(as_dict["linewidth"], 2.5)
        self.assertAlmostEqual(as_dict["alpha"], 0.7)
        self.assertEqual(as_dict["fill"], True)
        self.assertAlmostEqual(as_dict["fill_alpha"], 0.2)

    # ---- callback absent → buttons disabled ----

    def test_apply_buttons_disabled_when_no_callback(self):
        self.graph.add_node(_data("a"))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        for b in self._find_apply_one_buttons(dlg):
            self.assertEqual(str(b.cget("state")), "disabled")
        self.assertEqual(
            str(dlg._apply_all_btn.cget("state")), "disabled",
        )

    def test_callback_exception_does_not_break_dialog(self):
        """A raising on_apply_to_all is logged, not propagated."""
        self.graph.add_node(_data("a", style={"linewidth": 2.0}))

        def raiser(_k, _v):
            raise RuntimeError("intentional")

        dlg = self.StyleDialog(
            self.host, self.graph, "a", on_apply_to_all=raiser,
        )
        dlg.update_idletasks()

        # Suppress the WARNING noise so test output stays clean.
        import logging
        logging.getLogger("style_dialog").setLevel(logging.ERROR)
        try:
            # No exception escapes.
            dlg._delegate_apply_one("linewidth", 3.0)
        finally:
            logging.getLogger("style_dialog").setLevel(logging.WARNING)
        # The dialog still wrote to its own node.
        self.assertAlmostEqual(
            self.graph.get_node("a").style["linewidth"], 3.0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
