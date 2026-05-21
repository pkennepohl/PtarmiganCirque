"""Tests for node_styles_dialog.py (CS-74, Phase 4au).

Mirrors the structure of ``test_style_dialog.py``: construct a real
``tk.Tk`` root and ``ProjectGraph``, drive the dialog, observe widget
+ graph state. Headless environments where ``tk.Tk()`` cannot be
constructed are skipped at module load.

Run with the project venv:

    venv/Scripts/python run_tests.py
"""

from __future__ import annotations

import unittest

import numpy as np

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
          label: str | None = None,
          style: dict | None = None) -> DataNode:
    return DataNode(
        id=nid,
        type=ntype,
        arrays={"x": np.arange(3)},
        metadata={},
        label=label or nid,
        state=NodeState.COMMITTED,
        style=dict(style) if style else {},
    )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogShellPhase4au(unittest.TestCase):
    """Construction, transient/no-grab, registry, destroy cleanup."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog
        cls.open_node_styles_dialog = staticmethod(
            node_styles_dialog.open_node_styles_dialog
        )

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.n_a = _data("a", NodeType.UVVIS, "spec-A",
                         {"color": "#ff0000", "linewidth": 2.0})
        self.n_b = _data("b", NodeType.BASELINE, "base-B",
                         {"color": "#00ff00"})
        self.graph.add_node(self.n_a)
        self.graph.add_node(self.n_b)

    def tearDown(self):
        for dlg in list(self.mod._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_constructs_with_real_graph(self):
        dlg = self.NodeStylesDialog(
            self.host, self.graph, [self.n_a, self.n_b],
        )
        self.assertIsInstance(dlg, tk.Toplevel)
        self.assertEqual(dlg.title(), "Node Styles")

    def test_transient_set_no_grab(self):
        dlg = self.NodeStylesDialog(
            self.host, self.graph, [self.n_a],
        )
        # transient is set (CS-66 pattern: dialog grouped above host)
        self.assertNotEqual(dlg.wm_transient(), "")
        # No grab — modeless
        self.assertFalse(dlg.grab_status())

    def test_no_grab_set_call_in_source(self):
        """Sentinel: source must not call self.grab_set()."""
        import inspect
        src = inspect.getsource(self.NodeStylesDialog.__init__)
        self.assertNotIn("self.grab_set()", src)

    def test_open_factory_returns_same_dialog_on_second_call(self):
        dlg1 = self.open_node_styles_dialog(
            self.host, self.graph, [self.n_a],
        )
        dlg2 = self.open_node_styles_dialog(
            self.host, self.graph, [self.n_a],
        )
        self.assertIs(dlg1, dlg2)

    def test_registry_keyed_by_id_of_parent(self):
        dlg = self.open_node_styles_dialog(
            self.host, self.graph, [self.n_a],
        )
        self.assertIn(id(self.host), self.mod._open_dialogs)
        self.assertIs(self.mod._open_dialogs[id(self.host)], dlg)

    def test_distinct_hosts_get_distinct_dialogs(self):
        host2 = tk.Frame(_root)
        try:
            dlg1 = self.open_node_styles_dialog(
                self.host, self.graph, [self.n_a],
            )
            dlg2 = self.open_node_styles_dialog(
                host2, self.graph, [self.n_a],
            )
            self.assertIsNot(dlg1, dlg2)
            self.assertEqual(len(self.mod._open_dialogs), 2)
        finally:
            host2.destroy()

    def test_destroy_drops_graph_subscription(self):
        dlg = self.NodeStylesDialog(
            self.host, self.graph, [self.n_a],
        )
        self.assertIn(dlg._on_graph_event, self.graph._subscribers)
        dlg.destroy()
        dlg.update()  # Process the destroy event
        self.assertNotIn(dlg._on_graph_event, self.graph._subscribers)

    def test_destroy_pops_registry_entry(self):
        self.open_node_styles_dialog(self.host, self.graph, [self.n_a])
        self.assertIn(id(self.host), self.mod._open_dialogs)
        list(self.mod._open_dialogs.values())[0].destroy()
        _root.update()
        self.assertNotIn(id(self.host), self.mod._open_dialogs)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogComboboxPhase4au(unittest.TestCase):
    """Combobox population + selection switching."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.n_a = _data("a", NodeType.UVVIS, "spec-A",
                         {"color": "#ff0000", "linewidth": 2.0})
        self.n_b = _data("b", NodeType.BASELINE, "base-B",
                         {"color": "#00ff00", "linewidth": 3.5})
        self.n_c = _data("c", NodeType.SECOND_DERIVATIVE, "deriv-C",
                         {"color": "#0000ff"})
        for n in (self.n_a, self.n_b, self.n_c):
            self.graph.add_node(n)
        self.dlg = self.NodeStylesDialog(
            self.host, self.graph, [self.n_a, self.n_b, self.n_c],
        )

    def tearDown(self):
        try:
            self.dlg.destroy()
        except Exception:
            pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_combobox_values_match_nodes(self):
        values = self.dlg._combobox.cget("values")
        # Tk returns a tuple-like; coerce to list of strings
        values = list(values)
        self.assertEqual(len(values), 3)
        # Phase 4av item #1: state glyph prefix (🔒 committed / ⋯ provisional).
        self.assertIn("🔒 spec-A (UVVIS)", values)
        self.assertIn("🔒 base-B (BASELINE)", values)
        self.assertIn("🔒 deriv-C (SECOND_DERIVATIVE)", values)

    def test_initial_selection_is_first_node(self):
        self.assertEqual(self.dlg._node_id, "a")
        self.assertEqual(
            self.dlg._combobox_var.get(),
            "🔒 spec-A (UVVIS)",
        )

    def test_initial_widgets_seeded_from_first_node(self):
        self.assertAlmostEqual(
            float(self.dlg._control_vars["linewidth"].get()),
            2.0, places=5,
        )
        self.assertEqual(
            str(self.dlg._control_vars["color"].get()),
            "#ff0000",
        )

    def test_combobox_select_switches_active_node(self):
        self.dlg._combobox_var.set("🔒 base-B (BASELINE)")
        self.dlg._on_combobox_selected()
        self.assertEqual(self.dlg._node_id, "b")
        self.assertAlmostEqual(
            float(self.dlg._control_vars["linewidth"].get()),
            3.5, places=5,
        )
        self.assertEqual(
            str(self.dlg._control_vars["color"].get()),
            "#00ff00",
        )

    def test_combobox_select_updates_label_entry(self):
        self.dlg._combobox_var.set("🔒 base-B (BASELINE)")
        self.dlg._on_combobox_selected()
        self.assertEqual(
            str(self.dlg._control_vars["label"].get()),
            "base-B",
        )

    def test_combobox_select_same_node_is_noop(self):
        # No-op when display matches current selection
        original_linewidth = float(
            self.dlg._control_vars["linewidth"].get()
        )
        self.dlg._combobox_var.set("🔒 spec-A (UVVIS)")
        self.dlg._on_combobox_selected()
        self.assertEqual(self.dlg._node_id, "a")
        self.assertAlmostEqual(
            float(self.dlg._control_vars["linewidth"].get()),
            original_linewidth, places=5,
        )

    def test_empty_node_list_construction(self):
        host2 = tk.Frame(_root)
        try:
            dlg = self.NodeStylesDialog(host2, self.graph, [])
            self.assertIsNone(dlg._node_id)
            self.assertEqual(list(dlg._combobox.cget("values")), [])
            dlg.destroy()
        finally:
            host2.destroy()


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogRowControlsPhase4au(unittest.TestCase):
    """Each universal-section row writes through graph.set_style /
    graph.set_label with the suspend_writes guard."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.n_a = _data("a", NodeType.UVVIS, "spec-A",
                         {"color": "#ff0000", "linewidth": 2.0,
                          "alpha": 0.8, "fill": False,
                          "fill_alpha": 0.15, "visible": True,
                          "in_legend": True, "linestyle": "-"})
        self.graph.add_node(self.n_a)
        self.dlg = self.NodeStylesDialog(
            self.host, self.graph, [self.n_a],
        )

    def tearDown(self):
        try:
            self.dlg.destroy()
        except Exception:
            pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_linewidth_slider_writes_through_set_style(self):
        self.dlg._control_vars["linewidth"].set(4.2)
        node = self.graph.get_node("a")
        self.assertAlmostEqual(node.style["linewidth"], 4.2, places=5)

    def test_alpha_slider_writes_through_set_style(self):
        self.dlg._control_vars["alpha"].set(0.42)
        node = self.graph.get_node("a")
        self.assertAlmostEqual(node.style["alpha"], 0.42, places=5)

    def test_linestyle_radio_writes_through_set_style(self):
        self.dlg._control_vars["linestyle"].set("dashed")
        node = self.graph.get_node("a")
        self.assertEqual(node.style["linestyle"], "dashed")

    def test_fill_checkbox_writes_through_set_style(self):
        self.dlg._control_vars["fill"].set(True)
        node = self.graph.get_node("a")
        self.assertTrue(node.style["fill"])

    def test_visible_checkbox_writes_through_set_style(self):
        self.dlg._control_vars["visible"].set(False)
        node = self.graph.get_node("a")
        self.assertFalse(node.style["visible"])

    def test_in_legend_checkbox_writes_through_set_style(self):
        self.dlg._control_vars["in_legend"].set(False)
        node = self.graph.get_node("a")
        self.assertFalse(node.style["in_legend"])

    def test_y_axis_combobox_writes_through_set_style(self):
        self.dlg._control_vars["y_axis"].set("secondary")
        # Manually trigger the bound <<ComboboxSelected>> handler
        # since setting the StringVar alone doesn't fire it.
        self.dlg._write_partial({"y_axis": "secondary"})
        node = self.graph.get_node("a")
        self.assertEqual(node.style["y_axis"], "secondary")

    def test_label_entry_writes_through_set_label(self):
        self.dlg._control_vars["label"].set("renamed-A")
        node = self.graph.get_node("a")
        self.assertEqual(node.label, "renamed-A")

    def test_write_partial_engages_suspend_writes(self):
        # Sentinel: tearing into _write_partial flips the flag.
        self.dlg._suspend_writes = False
        # Replace set_style with an introspection hook
        observed: list[bool] = []
        original = self.graph.set_style

        def _capture(node_id, partial):
            observed.append(self.dlg._suspend_writes)
            original(node_id, partial)
        self.graph.set_style = _capture  # type: ignore[assignment]
        try:
            self.dlg._write_partial({"alpha": 0.5})
        finally:
            self.graph.set_style = original  # type: ignore[assignment]
        self.assertEqual(observed, [True])

    def test_write_partial_skipped_when_suspended(self):
        self.dlg._suspend_writes = True
        self.dlg._write_partial({"alpha": 0.42})
        # Suspended: alpha should still be 0.8
        node = self.graph.get_node("a")
        self.assertAlmostEqual(node.style["alpha"], 0.8, places=5)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogApplyToAllPhase4au(unittest.TestCase):
    """Per-row ∀ button delegates via on_apply_to_all."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.n_a = _data("a", NodeType.UVVIS, "spec-A",
                         {"linewidth": 2.0})
        self.graph.add_node(self.n_a)
        self.calls: list[tuple[str, object]] = []

        def _cb(param, value):
            self.calls.append((param, value))
        self.cb = _cb
        self.dlg = self.NodeStylesDialog(
            self.host, self.graph, [self.n_a],
            on_apply_to_all=_cb,
        )

    def tearDown(self):
        try:
            self.dlg.destroy()
        except Exception:
            pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_delegate_calls_callback_with_param_and_value(self):
        self.dlg._delegate_apply_one("linewidth", 3.0)
        self.assertEqual(self.calls, [("linewidth", 3.0)])

    def test_delegate_also_writes_to_source_node(self):
        self.dlg._delegate_apply_one("linewidth", 3.0)
        node = self.graph.get_node("a")
        self.assertAlmostEqual(node.style["linewidth"], 3.0, places=5)

    def test_per_row_button_built_for_every_universal_key(self):
        # 8 broadcast-capable rows: linestyle, linewidth, alpha,
        # color, fill, fill_alpha, visible, in_legend, y_axis = 9
        expected_keys = {
            "linestyle", "linewidth", "alpha", "color",
            "fill", "fill_alpha", "visible", "in_legend", "y_axis",
        }
        self.assertEqual(
            set(self.dlg._apply_one_buttons.keys()), expected_keys,
        )

    def test_label_row_has_no_apply_to_all_button(self):
        # Label fanning would collapse siblings onto one display
        # string — never offered as a ∀ row.
        self.assertNotIn("label", self.dlg._apply_one_buttons)

    def test_buttons_disabled_when_no_callback_wired(self):
        host2 = tk.Frame(_root)
        try:
            dlg = self.NodeStylesDialog(
                host2, self.graph, [self.n_a],
                on_apply_to_all=None,
            )
            for key, btn in dlg._apply_one_buttons.items():
                self.assertEqual(
                    str(btn.cget("state")), "disabled",
                    msg=f"∀ button for {key!r} should be disabled",
                )
            dlg.destroy()
        finally:
            host2.destroy()

    def test_callback_exception_does_not_break_dialog(self):
        def _raising_cb(param, value):
            raise RuntimeError("intentional test exception")
        host2 = tk.Frame(_root)
        try:
            dlg = self.NodeStylesDialog(
                host2, self.graph, [self.n_a],
                on_apply_to_all=_raising_cb,
            )
            # Should not raise — exception is logged inside the
            # delegate.
            dlg._delegate_apply_one("linewidth", 5.0)
            # Source node still got the self-write.
            node = self.graph.get_node("a")
            self.assertAlmostEqual(
                node.style["linewidth"], 5.0, places=5,
            )
            dlg.destroy()
        finally:
            host2.destroy()


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogRefreshNodeListPhase4au(unittest.TestCase):
    """CS-72-pattern refresh_node_list contract."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.n_a = _data("a", NodeType.UVVIS, "spec-A",
                         {"linewidth": 2.0})
        self.n_b = _data("b", NodeType.BASELINE, "base-B",
                         {"linewidth": 3.0})
        self.graph.add_node(self.n_a)
        self.graph.add_node(self.n_b)
        self.dlg = self.NodeStylesDialog(
            self.host, self.graph, [self.n_a, self.n_b],
        )

    def tearDown(self):
        try:
            self.dlg.destroy()
        except Exception:
            pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_refresh_with_grown_list_appends_combobox_value(self):
        n_c = _data("c", NodeType.NORMALISED, "norm-C")
        self.graph.add_node(n_c)
        self.dlg.refresh_node_list([self.n_a, self.n_b, n_c])
        values = list(self.dlg._combobox.cget("values"))
        self.assertIn("🔒 norm-C (NORMALISED)", values)

    def test_refresh_preserves_current_selection_by_id(self):
        # Switch to node B, then refresh — selection should stay B.
        self.dlg._select_node("b")
        n_c = _data("c", NodeType.NORMALISED, "norm-C")
        self.graph.add_node(n_c)
        self.dlg.refresh_node_list([self.n_a, self.n_b, n_c])
        self.assertEqual(self.dlg._node_id, "b")
        self.assertEqual(
            self.dlg._combobox_var.get(), "🔒 base-B (BASELINE)",
        )

    def test_refresh_when_selected_removed_falls_back_to_first(self):
        self.dlg._select_node("b")
        self.dlg.refresh_node_list([self.n_a])
        self.assertEqual(self.dlg._node_id, "a")

    def test_refresh_with_empty_list_clears_selection(self):
        self.dlg.refresh_node_list([])
        self.assertIsNone(self.dlg._node_id)
        self.assertEqual(self.dlg._combobox_var.get(), "")
        self.assertEqual(list(self.dlg._combobox.cget("values")), [])

    def test_refresh_is_widget_state_only_no_graph_mutation(self):
        # Spy on set_style — refresh must not call it.
        original = self.graph.set_style
        calls: list = []

        def _capture(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)
        self.graph.set_style = _capture  # type: ignore[assignment]
        try:
            self.dlg.refresh_node_list([self.n_a, self.n_b])
        finally:
            self.graph.set_style = original  # type: ignore[assignment]
        self.assertEqual(calls, [])


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogGraphEventSyncPhase4au(unittest.TestCase):
    """External NODE_STYLE_CHANGED / NODE_LABEL_CHANGED refresh
    widgets without recursion."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.n_a = _data("a", NodeType.UVVIS, "spec-A",
                         {"linewidth": 2.0, "color": "#ff0000"})
        self.n_b = _data("b", NodeType.BASELINE, "base-B",
                         {"linewidth": 3.0, "color": "#00ff00"})
        self.graph.add_node(self.n_a)
        self.graph.add_node(self.n_b)
        self.dlg = self.NodeStylesDialog(
            self.host, self.graph, [self.n_a, self.n_b],
        )

    def tearDown(self):
        try:
            self.dlg.destroy()
        except Exception:
            pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_external_style_change_on_selected_refreshes_widget(self):
        # Selected node is "a" — external set_style should refresh.
        self.graph.set_style("a", {"linewidth": 4.5})
        self.dlg.update()
        self.assertAlmostEqual(
            float(self.dlg._control_vars["linewidth"].get()),
            4.5, places=5,
        )

    def test_external_style_change_on_other_node_ignored(self):
        # Selected is "a"; mutate "b" — widget shouldn't change.
        self.graph.set_style("b", {"linewidth": 4.5})
        self.dlg.update()
        self.assertAlmostEqual(
            float(self.dlg._control_vars["linewidth"].get()),
            2.0, places=5,
        )

    def test_external_label_change_on_selected_refreshes_entry(self):
        self.graph.set_label("a", "renamed-A")
        self.dlg.update()
        self.assertEqual(
            str(self.dlg._control_vars["label"].get()),
            "renamed-A",
        )

    def test_self_write_does_not_loop_through_refresh(self):
        # Increment a write counter inside refresher to detect a
        # self-triggered loop.
        counters = {"linewidth": 0}
        original_refresher = self.dlg._control_refresh["linewidth"]

        def _wrapped(value):
            counters["linewidth"] += 1
            original_refresher(value)
        self.dlg._control_refresh["linewidth"] = _wrapped
        # User-driven write via the Tk var fires trace → write_partial
        # → graph.set_style → NODE_STYLE_CHANGED. If suspend_writes
        # works the refresher will NOT be called.
        self.dlg._control_vars["linewidth"].set(3.7)
        self.dlg.update()
        # Should not be called (suspend_writes guarded it).
        self.assertEqual(counters["linewidth"], 0)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogConstantsMirrorPhase4au(unittest.TestCase):
    """Sentinel: CS-74 universal-section constants mirror CS-05's."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        import style_dialog
        cls.nsd = node_styles_dialog
        cls.sd = style_dialog

    def test_y_axis_visible_node_types_match(self):
        self.assertEqual(
            self.nsd._Y_AXIS_VISIBLE_NODETYPES,
            self.sd._Y_AXIS_VISIBLE_NODETYPES,
        )

    def test_y_axis_options_match(self):
        self.assertEqual(
            self.nsd._Y_AXIS_OPTIONS, self.sd._Y_AXIS_OPTIONS,
        )

    def test_ls_options_match(self):
        self.assertEqual(self.nsd._LS_OPTIONS, self.sd._LS_OPTIONS)

    def test_y_axis_display_translate_round_trip(self):
        # None ↔ "(default)"
        self.assertIsNone(self.nsd._y_axis_display_to_value("(default)"))
        self.assertEqual(
            self.nsd._y_axis_value_to_display(None), "(default)",
        )
        # Each role string passes through.
        for role in ("primary", "secondary", "tertiary"):
            self.assertEqual(self.nsd._y_axis_display_to_value(role), role)
            self.assertEqual(self.nsd._y_axis_value_to_display(role), role)
        # Defensive: malformed display → None
        self.assertIsNone(self.nsd._y_axis_display_to_value("garbage"))
        # Defensive: malformed value → "(default)"
        self.assertEqual(
            self.nsd._y_axis_value_to_display("garbage"), "(default)",
        )

    def test_universal_keys_order_matches_render_order(self):
        # Sentinel: if a future row is reordered or added, this test
        # catches the drift between _UNIVERSAL_KEYS and the actual
        # render order.
        expected = (
            "linestyle", "linewidth", "alpha",
            "color", "fill", "fill_alpha",
            "visible", "in_legend",
            "y_axis",
        )
        self.assertEqual(self.nsd._UNIVERSAL_KEYS, expected)


# ════════════════════════════════════════════════════════════════════
# Phase 4av polish-bundle sentinels (CS-74 follow-through, no new CS).
# Four Claude-surfaced items from the Phase 4au friction section:
#   #1 Combobox state-badge prefix
#   #2 Palette-picked colour Reset (CS-21 D3 third caller)
#   #3 <Control-Down>/<Control-Up> Combobox stepping
#   #4 Y-axis row NodeType guard (load-bearing on cross-tab adoption)
# ════════════════════════════════════════════════════════════════════


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogStateBadgePhase4av(unittest.TestCase):
    """Item #1: NodeState glyph prefixes the Combobox display string."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.committed = _data("c", NodeType.UVVIS, "shared",
                               {"color": "#ff0000"})
        self.provisional = DataNode(
            id="p", type=NodeType.UVVIS,
            arrays={"x": np.arange(3)}, metadata={},
            label="shared", state=NodeState.PROVISIONAL, style={},
        )
        self.graph.add_node(self.committed)
        self.graph.add_node(self.provisional)
        self.dlg = self.NodeStylesDialog(
            self.host, self.graph,
            [self.committed, self.provisional],
        )

    def tearDown(self):
        try:
            self.dlg.destroy()
        except Exception:
            pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_state_glyph_for_committed_is_lock(self):
        self.assertEqual(
            self.NodeStylesDialog._state_glyph_for(NodeState.COMMITTED),
            "🔒",
        )

    def test_state_glyph_for_provisional_is_ellipsis(self):
        self.assertEqual(
            self.NodeStylesDialog._state_glyph_for(NodeState.PROVISIONAL),
            "⋯",
        )

    def test_committed_node_combobox_label_prefixed_lock(self):
        self.assertEqual(
            self.dlg._combobox_label_for("c"),
            "🔒 shared (UVVIS)",
        )

    def test_provisional_node_combobox_label_prefixed_ellipsis(self):
        self.assertEqual(
            self.dlg._combobox_label_for("p"),
            "⋯ shared (UVVIS)",
        )

    def test_combobox_values_disambiguate_same_label_by_state(self):
        # Both nodes share label "shared" — state glyph is what makes
        # them visually distinguishable in the dropdown.
        values = list(self.dlg._combobox.cget("values"))
        self.assertIn("🔒 shared (UVVIS)", values)
        self.assertIn("⋯ shared (UVVIS)", values)
        self.assertEqual(len(values), 2)

    def test_display_to_node_id_round_trips_through_glyph(self):
        self.assertEqual(
            self.dlg._node_id_for_display("⋯ shared (UVVIS)"), "p",
        )
        self.assertEqual(
            self.dlg._node_id_for_display("🔒 shared (UVVIS)"), "c",
        )

    def test_missing_node_id_still_returns_sentinel(self):
        # Removed node — defensive path returns "<missing>", not
        # a glyph-prefixed string.
        self.assertEqual(
            self.dlg._combobox_label_for("nope"), "<missing>",
        )

    def test_label_format_starts_with_glyph_then_space(self):
        # The leading character must be the glyph and the second must
        # be a space — pins the exact prefix shape for downstream
        # parsing / regex-driven UI tooling.
        for display in self.dlg._combobox.cget("values"):
            self.assertIn(display[0], ("🔒", "⋯"))
            self.assertEqual(display[1], " ")


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogColourResetPalettePhase4av(unittest.TestCase):
    """Item #2: _on_colour_reset delegates to pick_default_color
    (CS-21 D3 third caller)."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        import node_styles
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog
        cls.node_styles = node_styles

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        # Pre-existing nodes consume palette slots — the dialog's
        # Reset must land at a non-zero palette index.
        self.n_a = _data("a", NodeType.UVVIS, "spec-A",
                         {"color": "#abcdef"})
        self.n_b = _data("b", NodeType.BASELINE, "base-B",
                         {"color": "#abcdef"})
        self.graph.add_node(self.n_a)
        self.graph.add_node(self.n_b)
        self.dlg = self.NodeStylesDialog(
            self.host, self.graph, [self.n_a, self.n_b],
        )

    def tearDown(self):
        try:
            self.dlg.destroy()
        except Exception:
            pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_reset_writes_palette_member(self):
        # Reset must write a colour drawn from SPECTRUM_PALETTE,
        # not the constant _UNIVERSAL_DEFAULTS["color"].
        self.dlg._on_colour_reset()
        new_colour = self.graph.get_node("a").style["color"]
        self.assertIn(new_colour, self.node_styles.SPECTRUM_PALETTE)

    def test_reset_picks_via_palette_helper(self):
        # The picked colour must match what
        # node_styles.pick_default_color(graph) returns at reset time.
        expected = self.node_styles.pick_default_color(self.graph)
        self.dlg._on_colour_reset()
        self.assertEqual(
            self.graph.get_node("a").style["color"], expected,
        )

    def test_reset_no_node_selected_is_noop(self):
        # Empty list → no selection → reset must not raise.
        host2 = tk.Frame(_root)
        try:
            dlg = self.NodeStylesDialog(host2, self.graph, [])
            dlg._on_colour_reset()
            dlg.destroy()
        finally:
            host2.destroy()

    def test_reset_advances_when_called_repeatedly(self):
        # pick_default_color counts existing nodes; if Reset is
        # called twice consecutively without intervening graph
        # changes the colour stays at the same palette index (the
        # picker is deterministic over graph state, not call count).
        # This is the correct behaviour — pinning it so a future
        # refactor doesn't silently make Reset random.
        self.dlg._on_colour_reset()
        first = self.graph.get_node("a").style["color"]
        self.dlg._on_colour_reset()
        second = self.graph.get_node("a").style["color"]
        self.assertEqual(first, second)

    def test_reset_falls_back_when_picker_raises(self):
        # Defensive: if pick_default_color blows up, Reset still
        # writes a colour (universal default fallback) rather than
        # leaving the row unwritten.
        original = self.mod.pick_default_color

        def _boom(_g):
            raise RuntimeError("picker exploded")
        self.mod.pick_default_color = _boom  # type: ignore[assignment]
        try:
            self.dlg._on_colour_reset()
        finally:
            self.mod.pick_default_color = original  # type: ignore[assignment]
        self.assertEqual(
            self.graph.get_node("a").style["color"],
            self.mod._UNIVERSAL_DEFAULTS["color"],
        )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogKeyboardNavPhase4av(unittest.TestCase):
    """Item #3: <Control-Down>/<Control-Up> step Combobox without
    mouse; clamp at list ends (no wrap)."""

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.n_a = _data("a", NodeType.UVVIS, "A")
        self.n_b = _data("b", NodeType.BASELINE, "B")
        self.n_c = _data("c", NodeType.NORMALISED, "C")
        for n in (self.n_a, self.n_b, self.n_c):
            self.graph.add_node(n)
        self.dlg = self.NodeStylesDialog(
            self.host, self.graph,
            [self.n_a, self.n_b, self.n_c],
        )

    def tearDown(self):
        try:
            self.dlg.destroy()
        except Exception:
            pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_control_down_steps_forward(self):
        self.assertEqual(self.dlg._node_id, "a")
        self.dlg._step_combobox_selection(+1)
        self.assertEqual(self.dlg._node_id, "b")
        self.dlg._step_combobox_selection(+1)
        self.assertEqual(self.dlg._node_id, "c")

    def test_control_up_steps_backward(self):
        self.dlg._select_node("c")
        self.dlg._step_combobox_selection(-1)
        self.assertEqual(self.dlg._node_id, "b")
        self.dlg._step_combobox_selection(-1)
        self.assertEqual(self.dlg._node_id, "a")

    def test_step_past_end_clamps_no_wrap(self):
        # Step from c (last) forward — must stay at c, not wrap to a.
        self.dlg._select_node("c")
        self.dlg._step_combobox_selection(+1)
        self.assertEqual(self.dlg._node_id, "c")

    def test_step_past_start_clamps_no_wrap(self):
        # At a (first), step backward — must stay at a.
        self.assertEqual(self.dlg._node_id, "a")
        self.dlg._step_combobox_selection(-1)
        self.assertEqual(self.dlg._node_id, "a")

    def test_step_with_empty_list_is_noop(self):
        host2 = tk.Frame(_root)
        try:
            dlg = self.NodeStylesDialog(host2, self.graph, [])
            self.assertIsNone(dlg._node_id)
            dlg._step_combobox_selection(+1)
            self.assertIsNone(dlg._node_id)
            dlg._step_combobox_selection(-1)
            self.assertIsNone(dlg._node_id)
            dlg.destroy()
        finally:
            host2.destroy()

    def test_step_refreshes_universal_section_widgets(self):
        # Stepping must drive the same widget refresh path as a
        # mouse Combobox selection — _select_node is the join point.
        self.graph.set_style("b", {"linewidth": 4.2})
        self.dlg._step_combobox_selection(+1)
        self.assertAlmostEqual(
            float(self.dlg._control_vars["linewidth"].get()),
            4.2, places=5,
        )

    def test_combobox_var_updates_on_step(self):
        self.dlg._step_combobox_selection(+1)
        self.assertEqual(
            self.dlg._combobox_var.get(), "🔒 B (BASELINE)",
        )

    def test_control_arrow_bindings_present_on_toplevel(self):
        # bind(...) returns a Tcl handler string; "" means unbound.
        self.assertNotEqual(self.dlg.bind("<Control-Down>"), "")
        self.assertNotEqual(self.dlg.bind("<Control-Up>"), "")


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNodeStylesDialogYAxisGuardPhase4av(unittest.TestCase):
    """Item #4: Y-axis row state-gated by selected NodeType.

    On UVVisTab today the gate is a no-op (every dropdown NodeType
    is Y-routable); becomes load-bearing on Compare / XANES / EXAFS
    adoption. Tests use NodeType.TDDFT as a stand-in non-Y-routable
    node to exercise the gating before that adoption lands.
    """

    @classmethod
    def setUpClass(cls):
        import node_styles_dialog
        cls.mod = node_styles_dialog
        cls.NodeStylesDialog = node_styles_dialog.NodeStylesDialog

    def setUp(self):
        self.mod._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.graph = ProjectGraph()
        self.n_uvvis = _data("u", NodeType.UVVIS, "uv")
        self.n_tddft = DataNode(
            id="t", type=NodeType.TDDFT,
            arrays={"x": np.arange(3)}, metadata={},
            label="tddft", state=NodeState.COMMITTED, style={},
        )
        self.graph.add_node(self.n_uvvis)
        self.graph.add_node(self.n_tddft)
        self.dlg = self.NodeStylesDialog(
            self.host, self.graph,
            [self.n_uvvis, self.n_tddft],
            on_apply_to_all=lambda _k, _v: None,
        )

    def tearDown(self):
        try:
            self.dlg.destroy()
        except Exception:
            pass
        self.mod._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_y_axis_combobox_reference_stored_on_dialog(self):
        self.assertIsNotNone(self.dlg._y_axis_combobox)

    def test_y_axis_enabled_for_uvvis_selection(self):
        # Initial selection is UVVIS — combobox must be readonly,
        # ∀ button must be NORMAL (callback wired).
        self.assertEqual(
            str(self.dlg._y_axis_combobox.cget("state")), "readonly",
        )
        btn = self.dlg._apply_one_buttons["y_axis"]
        self.assertEqual(str(btn.cget("state")), tk.NORMAL)

    def test_y_axis_disabled_for_tddft_selection(self):
        self.dlg._select_node("t")
        self.assertEqual(
            str(self.dlg._y_axis_combobox.cget("state")),
            str(tk.DISABLED),
        )
        btn = self.dlg._apply_one_buttons["y_axis"]
        self.assertEqual(str(btn.cget("state")), str(tk.DISABLED))

    def test_y_axis_re_enabled_after_switching_back_to_uvvis(self):
        # Switch to TDDFT (disable), then back to UVVIS (enable).
        self.dlg._select_node("t")
        self.dlg._select_node("u")
        self.assertEqual(
            str(self.dlg._y_axis_combobox.cget("state")), "readonly",
        )

    def test_y_axis_combobox_state_is_readonly_not_normal_when_enabled(self):
        # Incidental bug fix: _set_universal_disabled(False) would
        # leave the ttk.Combobox in "normal" (free-text-entry) mode.
        # The guard pins it back to "readonly".
        self.dlg._set_universal_disabled(True)
        self.dlg._set_universal_disabled(False)
        # _set_universal_disabled alone would now show "normal"; the
        # guard must restore "readonly".
        self.dlg._update_y_axis_row_state(NodeType.UVVIS)
        self.assertEqual(
            str(self.dlg._y_axis_combobox.cget("state")), "readonly",
        )

    def test_y_axis_apply_button_disabled_when_no_callback(self):
        host2 = tk.Frame(_root)
        try:
            dlg = self.NodeStylesDialog(
                host2, self.graph, [self.n_uvvis],
                on_apply_to_all=None,
            )
            btn = dlg._apply_one_buttons["y_axis"]
            self.assertEqual(str(btn.cget("state")), str(tk.DISABLED))
            dlg.destroy()
        finally:
            host2.destroy()

    def test_y_axis_disabled_when_node_type_resolution_fails(self):
        # _update_y_axis_row_state called with None must disable.
        self.dlg._update_y_axis_row_state(None)
        self.assertEqual(
            str(self.dlg._y_axis_combobox.cget("state")),
            str(tk.DISABLED),
        )

    def test_node_type_for_helper_resolves_from_local_cache(self):
        self.assertEqual(
            self.dlg._node_type_for("u"), NodeType.UVVIS,
        )
        self.assertEqual(
            self.dlg._node_type_for("t"), NodeType.TDDFT,
        )
        self.assertIsNone(self.dlg._node_type_for("nope"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
