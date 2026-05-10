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
            "visible": True,
            "in_legend": True,
            "y_axis": None,
        }))
        seen: list = []
        dlg = self.StyleDialog(
            self.host, self.graph, "a",
            on_apply_to_all=lambda k, v: seen.append((k, v)),
        )
        dlg.update_idletasks()

        # Universal section has nine per-row ∀ buttons after Phase 4y
        # (CS-50) added ``y_axis`` (joining the eight from Phase 4d
        # which added ``visible`` and ``in_legend`` for B-002).
        btns = self._find_apply_one_buttons(dlg)
        self.assertEqual(
            len(btns), 9,
            "expected one ∀ per universal-section row",
        )
        for b in btns:
            b.invoke()

        keys = [k for (k, _) in seen]
        self.assertCountEqual(
            keys,
            ["linestyle", "linewidth", "alpha",
             "color", "fill", "fill_alpha",
             "visible", "in_legend",
             "y_axis"],
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


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestStyleDialogVisibleInLegend(unittest.TestCase):
    """Phase 4d — universal-section ``visible`` and ``in_legend`` rows.

    CS-04 row controls for visibility and legend membership collapse
    when the sidebar narrows (B-002), so the unified StyleDialog
    must carry matching toggles. These tests pin:

    * the rows exist with their initial state read from ``node.style``
    * toggling each writes through ``set_style``
    * the per-row ∀ delegate fans the value out via
      ``on_apply_to_all``
    * an external ``set_style`` updates the dialog widget without
      looping back through ``set_style``
    * the bottom "∀ Apply to All" button does NOT fan out
      ``visible`` / ``in_legend`` (intentional — bulk visibility
      sweeps are a footgun)
    """

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

    # ---- initial state from node.style ----

    def test_visible_initial_state_reads_from_node_style(self):
        self.graph.add_node(_data("a", style={"visible": False}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        var = dlg._control_vars.get("visible")
        self.assertIsNotNone(var)
        self.assertFalse(bool(var.get()))

    def test_in_legend_initial_state_reads_from_node_style(self):
        self.graph.add_node(_data("a", style={"in_legend": False}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        var = dlg._control_vars.get("in_legend")
        self.assertIsNotNone(var)
        self.assertFalse(bool(var.get()))

    def test_visible_default_when_key_absent_from_style(self):
        self.graph.add_node(_data("a"))  # empty style dict
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        # Default per _UNIVERSAL_DEFAULTS is True.
        self.assertTrue(bool(dlg._control_vars["visible"].get()))
        self.assertTrue(bool(dlg._control_vars["in_legend"].get()))

    # ---- toggling writes through set_style ----

    def test_toggling_visible_writes_through_set_style(self):
        self.graph.add_node(_data("a", style={"visible": True}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        dlg._control_vars["visible"].set(False)
        dlg.update_idletasks()
        self.assertEqual(self.graph.get_node("a").style["visible"], False)

    def test_toggling_in_legend_writes_through_set_style(self):
        self.graph.add_node(_data("a", style={"in_legend": True}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        dlg._control_vars["in_legend"].set(False)
        dlg.update_idletasks()
        self.assertEqual(
            self.graph.get_node("a").style["in_legend"], False,
        )

    # ---- external set_style updates the widget ----

    def test_external_set_style_updates_visible_widget(self):
        # An external mutation (e.g., the row's ☑ checkbox) must
        # propagate into the dialog without firing a recursive write.
        self.graph.add_node(_data("a", style={"visible": True}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()

        self.graph.set_style("a", {"visible": False})
        dlg.update_idletasks()
        self.assertFalse(bool(dlg._control_vars["visible"].get()))

    # ---- per-row ∀ delegates fan-out ----

    def test_per_row_apply_one_delegates_visible(self):
        self.graph.add_node(_data("a", style={"visible": True}))
        seen: list = []
        dlg = self.StyleDialog(
            self.host, self.graph, "a",
            on_apply_to_all=lambda k, v: seen.append((k, v)),
        )
        dlg.update_idletasks()

        dlg._delegate_apply_one("visible", False)
        self.assertEqual(seen, [("visible", False)])
        # Self-write also: dialog's local node ends up consistent.
        self.assertEqual(self.graph.get_node("a").style["visible"], False)

    def test_per_row_apply_one_delegates_in_legend(self):
        self.graph.add_node(_data("a", style={"in_legend": True}))
        seen: list = []
        dlg = self.StyleDialog(
            self.host, self.graph, "a",
            on_apply_to_all=lambda k, v: seen.append((k, v)),
        )
        dlg.update_idletasks()

        dlg._delegate_apply_one("in_legend", False)
        self.assertEqual(seen, [("in_legend", False)])
        self.assertEqual(
            self.graph.get_node("a").style["in_legend"], False,
        )

    # ---- bulk ∀ excludes visible / in_legend ----

    def test_bottom_apply_all_excludes_visible_and_in_legend(self):
        # The bottom "∀ Apply to All" button is for bulk-applying
        # *display style*, not visibility or legend membership.
        # Phase 4d documents the exclusion in _BULK_UNIVERSAL_KEYS.
        self.graph.add_node(_data("a", style={
            "linestyle": "solid", "linewidth": 1.5, "alpha": 0.9,
            "color": "#1f77b4", "fill": False, "fill_alpha": 0.08,
            "visible": True, "in_legend": True,
        }))
        seen: list = []
        dlg = self.StyleDialog(
            self.host, self.graph, "a",
            on_apply_to_all=lambda k, v: seen.append((k, v)),
        )
        dlg.update_idletasks()
        dlg._apply_all_btn.invoke()

        keys = [k for (k, _) in seen]
        self.assertNotIn("visible", keys)
        self.assertNotIn("in_legend", keys)
        # And the existing exclusion (colour) still holds.
        self.assertNotIn("color", keys)

    # ---- module-level defaults + bulk key list ----

    def test_universal_defaults_carry_visible_and_in_legend(self):
        # The defaults table is the dialog's fallback when
        # ``node.style`` lacks a key. Adding visible / in_legend to
        # the universal section also requires them in the defaults.
        self.assertIn("visible", self.style_dialog._UNIVERSAL_DEFAULTS)
        self.assertIn("in_legend", self.style_dialog._UNIVERSAL_DEFAULTS)
        self.assertEqual(
            self.style_dialog._UNIVERSAL_DEFAULTS["visible"], True,
        )
        self.assertEqual(
            self.style_dialog._UNIVERSAL_DEFAULTS["in_legend"], True,
        )

    def test_bulk_universal_keys_excludes_visible_and_in_legend(self):
        self.assertNotIn(
            "visible", self.style_dialog._BULK_UNIVERSAL_KEYS,
        )
        self.assertNotIn(
            "in_legend", self.style_dialog._BULK_UNIVERSAL_KEYS,
        )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestStyleDialogYAxisOverride(unittest.TestCase):
    """Phase 4y (CS-50) — universal-section ``y_axis`` Combobox row.

    Carry-forward T from Phase 4u Decision 1 was deferred per the
    user's "Default only for now is okay" lock; CS-49's cross-type
    widening (Phase 4x) made the smoothed-of-derivative misroute
    newly reachable, so T became the next session's intent.

    Coverage:
    * Combobox initial state reads from ``node.style["y_axis"]`` and
      maps ``None`` → "(default)" / role string → role string
    * Selecting a role writes through ``set_style`` with the literal
      role string (or ``None`` for "(default)")
    * Apply / Save round-trip the override via
      ``_read_universal_values``
    * The per-row ∀ delegate fans the chosen value out via
      ``on_apply_to_all``
    * An external ``set_style`` update refreshes the Combobox
      without looping back into ``set_style``
    * The bottom ∀ Apply-to-All button does NOT include ``y_axis``
      (intentional — parallel to Phase 4d's ``visible`` / ``in_legend``
      carve-out; collapsing every derivative onto primary in one
      click is a footgun)
    * The display ↔ value round-trip helpers are total over the
      Combobox's option list and reject malformed input
    """

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

    # ---- initial state from node.style ----

    def test_y_axis_initial_state_default_renders_as_label(self):
        # ``style["y_axis"] = None`` must render as "(default)" so a
        # freshly-created node carries no visible override in the UI.
        self.graph.add_node(_data("a", style={"y_axis": None}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        var = dlg._control_vars.get("y_axis")
        self.assertIsNotNone(var)
        self.assertEqual(var.get(), self.style_dialog._Y_AXIS_DISPLAY_DEFAULT)

    def test_y_axis_initial_state_secondary_renders_literal(self):
        self.graph.add_node(_data("a", style={"y_axis": "secondary"}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        self.assertEqual(dlg._control_vars["y_axis"].get(), "secondary")

    def test_y_axis_missing_key_renders_as_default(self):
        # Pre-CS-50 nodes lack the key entirely; the Combobox falls
        # back to "(default)" via ``_UNIVERSAL_DEFAULTS["y_axis"]``.
        self.graph.add_node(_data("a", style={"linewidth": 2.0}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        self.assertEqual(
            dlg._control_vars["y_axis"].get(),
            self.style_dialog._Y_AXIS_DISPLAY_DEFAULT,
        )

    # ---- write-through via Combobox selection ----

    def test_selecting_secondary_writes_literal_role_to_style(self):
        self.graph.add_node(_data("a", style={"y_axis": None}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        # Simulate user-driven selection: set the StringVar then
        # generate the virtual event the dialog binds to.
        dlg._control_vars["y_axis"].set("secondary")
        # The bind on <<ComboboxSelected>> fires from the widget;
        # tests can call the bound function directly. Find the
        # Combobox via the control map indirectly by invoking the
        # write_partial path through a synthetic event call. The
        # simplest path: invoke the bound callback by generating the
        # virtual event on every ttk.Combobox descendant.
        for widget in dlg.winfo_children():
            self._trigger_combobox_selected(widget)
        self.assertEqual(self.graph.get_node("a").style["y_axis"], "secondary")

    def test_selecting_default_writes_none_to_style(self):
        self.graph.add_node(_data("a", style={"y_axis": "tertiary"}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        dlg._control_vars["y_axis"].set(
            self.style_dialog._Y_AXIS_DISPLAY_DEFAULT,
        )
        for widget in dlg.winfo_children():
            self._trigger_combobox_selected(widget)
        self.assertIsNone(self.graph.get_node("a").style["y_axis"])

    @staticmethod
    def _trigger_combobox_selected(widget):
        # Walk the widget tree, fire <<ComboboxSelected>> on every
        # ttk.Combobox so the write-through callback runs.
        from tkinter import ttk
        if isinstance(widget, ttk.Combobox):
            widget.event_generate("<<ComboboxSelected>>")
        for child in widget.winfo_children():
            TestStyleDialogYAxisOverride._trigger_combobox_selected(child)

    # ---- Apply / Save / Cancel round-trip ----

    def test_apply_button_round_trips_override(self):
        # Apply re-emits the current widget state via _do_apply →
        # _read_universal_values which now includes y_axis.
        self.graph.add_node(_data("a", style={"y_axis": None}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        dlg._control_vars["y_axis"].set("primary")
        dlg._do_apply()
        self.assertEqual(self.graph.get_node("a").style["y_axis"], "primary")

    def test_save_button_round_trips_override(self):
        self.graph.add_node(_data("a", style={"y_axis": None}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        dlg._control_vars["y_axis"].set("tertiary")
        dlg._do_save()
        # Save destroys the dialog; the value stays on the node.
        self.assertEqual(self.graph.get_node("a").style["y_axis"], "tertiary")

    def test_cancel_button_reverts_override_to_snapshot(self):
        # Snapshot is taken in __init__ from the node's style. Cancel
        # re-emits the snapshot via set_style so the override reverts.
        self.graph.add_node(_data("a", style={"y_axis": "secondary"}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        # User mid-session change.
        dlg._control_vars["y_axis"].set("tertiary")
        for widget in dlg.winfo_children():
            self._trigger_combobox_selected(widget)
        self.assertEqual(self.graph.get_node("a").style["y_axis"], "tertiary")
        # Cancel reverts to the snapshot value.
        dlg._do_cancel()
        self.assertEqual(self.graph.get_node("a").style["y_axis"], "secondary")

    # ---- per-row ∀ fan-out ----

    def test_per_row_apply_one_delegates_y_axis(self):
        seen: list = []
        self.graph.add_node(_data("a", style={"y_axis": "secondary"}))
        dlg = self.StyleDialog(
            self.host, self.graph, "a",
            on_apply_to_all=lambda k, v: seen.append((k, v)),
        )
        dlg.update_idletasks()
        dlg._delegate_apply_one("y_axis", "secondary")
        self.assertIn(("y_axis", "secondary"), seen)

    # ---- external sync ----

    def test_external_set_style_refreshes_combobox(self):
        self.graph.add_node(_data("a", style={"y_axis": None}))
        dlg = self.StyleDialog(self.host, self.graph, "a")
        dlg.update_idletasks()
        # An external source (sibling dialog, ScanTreeWidget, ∀ fan-
        # out) writes a new override on the same node.
        self.graph.set_style("a", {"y_axis": "secondary"})
        dlg.update_idletasks()
        self.assertEqual(dlg._control_vars["y_axis"].get(), "secondary")

    # ---- bulk fan-out exclusion ----

    def test_bulk_universal_keys_excludes_y_axis(self):
        # Phase 4y Decision (iii): the bottom ∀ Apply-to-All button
        # does NOT fan out y_axis. Only the per-row ∀ does, parallel
        # to the Phase 4d visible / in_legend carve-out.
        self.assertNotIn("y_axis", self.style_dialog._BULK_UNIVERSAL_KEYS)

    def test_bottom_apply_all_does_not_fan_y_axis(self):
        seen: list = []
        self.graph.add_node(_data("a", style={
            "linestyle": "dashed", "linewidth": 2.0, "alpha": 0.7,
            "color": "#ff0000", "fill": True, "fill_alpha": 0.2,
            "visible": True, "in_legend": True,
            "y_axis": "secondary",
        }))
        dlg = self.StyleDialog(
            self.host, self.graph, "a",
            on_apply_to_all=lambda k, v: seen.append((k, v)),
        )
        dlg.update_idletasks()
        dlg._do_apply_all()
        keys = [k for (k, _) in seen]
        # y_axis stays out of the bulk fan-out.
        self.assertNotIn("y_axis", keys)
        # The other bulk keys still fire.
        self.assertIn("linewidth", keys)

    # ---- module-level defaults + helper round-trip ----

    def test_universal_defaults_carry_y_axis_none(self):
        self.assertIn("y_axis", self.style_dialog._UNIVERSAL_DEFAULTS)
        self.assertIsNone(self.style_dialog._UNIVERSAL_DEFAULTS["y_axis"])

    def test_y_axis_options_match_axis_roles(self):
        # The four Combobox options are "(default)" + the three
        # CS-44 roles. If `_AXIS_ROLES` ever changes shape, this
        # tuple must move in lockstep — pin both for drift.
        from uvvis_tab import _AXIS_ROLES
        self.assertEqual(
            self.style_dialog._Y_AXIS_OPTIONS,
            (self.style_dialog._Y_AXIS_DISPLAY_DEFAULT,) + _AXIS_ROLES,
        )

    def test_display_to_value_round_trip(self):
        sd = self.style_dialog
        self.assertIsNone(
            sd._y_axis_display_to_value(sd._Y_AXIS_DISPLAY_DEFAULT))
        self.assertEqual(sd._y_axis_display_to_value("primary"), "primary")
        self.assertEqual(sd._y_axis_display_to_value("secondary"),
                         "secondary")
        self.assertEqual(sd._y_axis_display_to_value("tertiary"),
                         "tertiary")
        # Defensive: malformed display strings collapse to None so
        # we never write a bogus role into a graph node.
        self.assertIsNone(sd._y_axis_display_to_value("bogus"))
        self.assertIsNone(sd._y_axis_display_to_value(""))

    def test_value_to_display_round_trip(self):
        sd = self.style_dialog
        self.assertEqual(sd._y_axis_value_to_display(None),
                         sd._Y_AXIS_DISPLAY_DEFAULT)
        self.assertEqual(sd._y_axis_value_to_display("primary"), "primary")
        self.assertEqual(sd._y_axis_value_to_display("secondary"),
                         "secondary")
        # Malformed persisted values fall back to "(default)".
        self.assertEqual(sd._y_axis_value_to_display("bogus"),
                         sd._Y_AXIS_DISPLAY_DEFAULT)
        self.assertEqual(sd._y_axis_value_to_display(17),
                         sd._Y_AXIS_DISPLAY_DEFAULT)


class TestStyleDialogPhase4aaConstants(unittest.TestCase):
    """Phase 4aa pure-module drift coverage for the y-axis visibility
    predicate.

    Not Tk-gated — the constant is module-level data, the assertions
    run in any environment that can import the project. The test
    pins ``_Y_AXIS_VISIBLE_NODETYPES`` against
    ``uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE.keys()`` so adding a new
    routed NodeType in the routing table forces the StyleDialog
    Combobox to surface for it (and removing one suppresses it).
    Without the pin, the two could drift and the universal-section
    affordance Phase 4aa was meant to gate would silently re-appear
    on whichever NodeType drifted out of sync.
    """

    @classmethod
    def setUpClass(cls):
        import style_dialog
        import uvvis_tab
        cls.style_dialog = style_dialog
        cls.uvvis_tab = uvvis_tab

    def test_y_axis_visible_node_types_match_routing_table(self):
        # The two sets must be exactly equal — every NodeType the
        # routing table knows about must show the Combobox; no
        # NodeType may show it without an entry in the routing table
        # (otherwise the override would persist on a node whose tab
        # cannot consult it).
        self.assertEqual(
            self.style_dialog._Y_AXIS_VISIBLE_NODETYPES,
            frozenset(self.uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE.keys()),
        )

    def test_y_axis_visible_node_types_is_frozen(self):
        # frozenset is the documented type — pin so a future "convert
        # to set / list / tuple" refactor would force a deliberate
        # decision about mutability rather than silently allowing
        # runtime mutation of the gate predicate.
        self.assertIsInstance(
            self.style_dialog._Y_AXIS_VISIBLE_NODETYPES, frozenset,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
