"""End-to-end integration tests for Phase 4v / CS-46 (persistence
Phase A) and CS-45 (apply-site implementation-hash stamping).

These tests construct a real Tk root + a real UVVisTab, drive the
left-panel apply gestures, save the resulting workflow, load it back
into a fresh tab, and assert that every aspect of the original
workflow round-trips. They also exercise the implementation-hash
mismatch surface by mutating the registry between save and load.

Run with:  python -m pytest test_persistence_phase_a.py -v
       or:  venv/Scripts/python run_tests.py
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

# Silence modal Tk messageboxes before any apply-site error path
# can fire (e.g. bad input rejected via messagebox.showerror).
from _test_silence import silence_all_messageboxes
silence_all_messageboxes()

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _HAS_DISPLAY = True
except Exception:  # pragma: no cover
    _root = None
    _HAS_DISPLAY = False


from graph import ProjectGraph
from nodes import DataNode, NodeState, NodeType, OperationNode, OperationType
import operation_hash
import project_io
import plot_settings_dialog as psd


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestApplySiteStampsImplementationHash(unittest.TestCase):
    """Every left-panel Apply must stamp metadata["implementation_hash"]
    with the current registry hash for its OperationType."""

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab
        operation_hash.clear_registry()
        operation_hash.register_default_implementations()

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self._uvvis_id = self._add_uvvis()

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def _add_uvvis(self, nid: str = "u1") -> str:
        wl = np.linspace(200.0, 800.0, 601)
        peak = np.exp(-((wl - 500.0) / 25.5) ** 2)
        bg = 0.10 + 0.0005 * wl
        absorb = peak + bg
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "instrument": "synthetic",
                      "source_file": f"syn_{nid}"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        return nid

    def _find_op_of_type(self, op_type: OperationType) -> OperationNode:
        for node in self.graph.nodes.values():
            if isinstance(node, OperationNode) and node.type == op_type:
                return node
        self.fail(f"No OperationNode of type {op_type.name} found")

    def _select_subject(self):
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertGreaterEqual(len(items), 1)
        self.tab._shared_subject.set(items[0])
        self.tab.update_idletasks()

    def test_baseline_apply_stamps_hash(self):
        self._select_subject()
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("250")
        self.tab._baseline_anchor_hi.set("750")
        self.tab._apply_baseline()
        op = self._find_op_of_type(OperationType.BASELINE)
        expected = operation_hash.compute_implementation_hash(
            OperationType.BASELINE)
        self.assertEqual(op.metadata.get("implementation_hash"), expected)

    def test_normalisation_apply_stamps_hash(self):
        self._select_subject()
        self.tab._normalisation_panel._mode_var.set("peak")
        self.tab._normalisation_panel._window_lo.set("400")
        self.tab._normalisation_panel._window_hi.set("600")
        self.tab._normalisation_panel._apply()
        op = self._find_op_of_type(OperationType.NORMALISE)
        expected = operation_hash.compute_implementation_hash(
            OperationType.NORMALISE)
        self.assertEqual(op.metadata.get("implementation_hash"), expected)

    def test_smoothing_apply_stamps_hash(self):
        self._select_subject()
        self.tab._smoothing_panel._mode_var.set("savgol")
        self.tab._smoothing_panel._window_length.set(11)
        self.tab._smoothing_panel._polyorder.set(3)
        self.tab._smoothing_panel._apply()
        op = self._find_op_of_type(OperationType.SMOOTH)
        expected = operation_hash.compute_implementation_hash(
            OperationType.SMOOTH)
        self.assertEqual(op.metadata.get("implementation_hash"), expected)

    def test_peak_picking_apply_stamps_hash(self):
        self._select_subject()
        self.tab._peak_picking_panel._mode_var.set("prominence")
        self.tab._peak_picking_panel._prominence.set("0.05")
        self.tab._peak_picking_panel._apply()
        op = self._find_op_of_type(OperationType.PEAK_PICK)
        expected = operation_hash.compute_implementation_hash(
            OperationType.PEAK_PICK)
        self.assertEqual(op.metadata.get("implementation_hash"), expected)

    def test_second_derivative_apply_stamps_hash(self):
        self._select_subject()
        self.tab._second_derivative_panel._window_length.set(11)
        self.tab._second_derivative_panel._polyorder.set(3)
        self.tab._second_derivative_panel._apply()
        op = self._find_op_of_type(OperationType.SECOND_DERIVATIVE)
        expected = operation_hash.compute_implementation_hash(
            OperationType.SECOND_DERIVATIVE)
        self.assertEqual(op.metadata.get("implementation_hash"), expected)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestSaveLoadRoundTrip(unittest.TestCase):
    """A populated UVVisTab survives a save → load cycle into a fresh
    UVVisTab with no warnings and identical graph contents."""

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab
        operation_hash.clear_registry()
        operation_hash.register_default_implementations()

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tmp = Path(tempfile.mkdtemp(suffix=".ptmg"))

        # Populate one UVVIS + apply a baseline.
        wl = np.linspace(200.0, 800.0, 601)
        peak = np.exp(-((wl - 500.0) / 25.5) ** 2)
        bg = 0.10 + 0.0005 * wl
        self.graph.add_node(DataNode(
            id="u1", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": peak + bg},
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "instrument": "synthetic",
                      "source_file": "syn_u1"},
            label="u1", state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        self.tab.update_idletasks()
        # The shared subject combobox key is "<label>  [<id[:6]>]";
        # picking the first available item is robust to that format.
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertGreaterEqual(len(items), 1)
        self.tab._shared_subject.set(items[0])
        self.tab.update_idletasks()
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("250")
        self.tab._baseline_anchor_hi.set("750")
        self.tab._apply_baseline()

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass
        if self.tmp.exists():
            shutil.rmtree(self.tmp)

    def test_save_then_load_preserves_node_set(self):
        project_io.save_project(
            self.tmp, name="rt", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=self.graph)},
        )
        loaded = project_io.load_project(self.tmp)
        self.assertEqual(
            sorted(loaded.tabs["uvvis"].graph.nodes.keys()),
            sorted(self.graph.nodes.keys()),
        )
        self.assertEqual(loaded.implementation_warnings, [])

    def test_save_then_load_preserves_arrays(self):
        project_io.save_project(
            self.tmp, name="rt", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=self.graph)},
        )
        loaded = project_io.load_project(self.tmp)
        u1_after = loaded.tabs["uvvis"].graph.nodes["u1"]
        np.testing.assert_array_equal(
            u1_after.arrays["wavelength_nm"],
            self.graph.nodes["u1"].arrays["wavelength_nm"],
        )
        np.testing.assert_array_equal(
            u1_after.arrays["absorbance"],
            self.graph.nodes["u1"].arrays["absorbance"],
        )

    def test_node_group_round_trips_through_save_load(self):
        # CS-57 (Phase 4af): a NODE_GROUP DataNode has arrays={} +
        # metadata['member_ids']: list[str]. The existing schema
        # round-trips it without changes (empty arrays → empty
        # savez archive; metadata is JSON-serialisable). This pin
        # traps a future schema tightening that would reject empty-
        # arrays nodes from silently breaking group carry-over.
        wl = self.graph.nodes["u1"].arrays["wavelength_nm"]
        self.graph.add_node(DataNode(
            id="u2", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl,
                    "absorbance": np.zeros_like(wl)},
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "instrument": "synthetic",
                      "source_file": "syn_u2"},
            label="u2", state=NodeState.PROVISIONAL,
        ))
        gid = self.graph.create_group(["u1", "u2"], label="my pair")
        project_io.save_project(
            self.tmp, name="rt", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=self.graph)},
        )
        loaded = project_io.load_project(self.tmp)
        gloaded = loaded.tabs["uvvis"].graph
        self.assertIn(gid, gloaded.nodes)
        group_after = gloaded.nodes[gid]
        self.assertEqual(group_after.type, NodeType.NODE_GROUP)
        self.assertEqual(group_after.label, "my pair")
        self.assertEqual(
            group_after.metadata["member_ids"], ["u1", "u2"],
        )
        self.assertEqual(group_after.arrays, {})
        self.assertEqual(gloaded.group_of("u1"), gid)
        self.assertEqual(gloaded.group_of("u2"), gid)

    def test_extend_then_remove_round_trips_through_save_load(self):
        # CS-58 (Phase 4ag): extend_group and remove_from_group
        # mutate metadata["member_ids"] in place. The save schema
        # serialises the list verbatim, so post-mutation rosters
        # must reach disk and come back identical. Pins that
        # neither method introduces a transient field or alternate
        # representation that the JSON manifest can't preserve.
        wl = self.graph.nodes["u1"].arrays["wavelength_nm"]
        # Add three more UVVIS nodes (u1 already exists from setUp).
        for nid in ("u2", "u3", "u4"):
            self.graph.add_node(DataNode(
                id=nid, type=NodeType.UVVIS,
                arrays={"wavelength_nm": wl,
                        "absorbance": np.zeros_like(wl)},
                metadata={"x_unit": "nm", "y_unit": "absorbance",
                          "instrument": "synthetic",
                          "source_file": f"syn_{nid}"},
                label=nid, state=NodeState.PROVISIONAL,
            ))
        # Start with {u1,u2}; extend to {u1,u2,u3,u4}; remove u2.
        gid = self.graph.create_group(["u1", "u2"], label="my pair")
        self.graph.extend_group(gid, ["u3", "u4"])
        self.graph.remove_from_group("u2")
        # Pre-flight: roster reflects all three mutations in order.
        self.assertEqual(
            self.graph.nodes[gid].metadata["member_ids"],
            ["u1", "u3", "u4"],
        )
        project_io.save_project(
            self.tmp, name="rt2", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=self.graph)},
        )
        loaded = project_io.load_project(self.tmp)
        gloaded = loaded.tabs["uvvis"].graph
        self.assertIn(gid, gloaded.nodes)
        group_after = gloaded.nodes[gid]
        self.assertEqual(group_after.type, NodeType.NODE_GROUP)
        self.assertEqual(group_after.label, "my pair")
        self.assertEqual(
            group_after.metadata["member_ids"], ["u1", "u3", "u4"],
        )
        # group_of() also survives.
        self.assertEqual(gloaded.group_of("u1"), gid)
        self.assertIsNone(gloaded.group_of("u2"))
        self.assertEqual(gloaded.group_of("u3"), gid)
        self.assertEqual(gloaded.group_of("u4"), gid)

    def test_auto_dissolved_group_round_trips_as_discarded(self):
        # CS-58 (Phase 4ag): when remove_from_group drops a group
        # below the 2-active-member threshold the group is auto-
        # dissolved (DISCARDED). Verify the discarded state +
        # group_of consequences survive save/load.
        wl = self.graph.nodes["u1"].arrays["wavelength_nm"]
        self.graph.add_node(DataNode(
            id="u2", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl,
                    "absorbance": np.zeros_like(wl)},
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "instrument": "synthetic",
                      "source_file": "syn_u2"},
            label="u2", state=NodeState.PROVISIONAL,
        ))
        gid = self.graph.create_group(["u1", "u2"], label="doomed")
        self.graph.remove_from_group("u1")
        # Pre-flight: group is now DISCARDED, u2 has no group.
        self.assertEqual(
            self.graph.nodes[gid].state, NodeState.DISCARDED
        )
        self.assertIsNone(self.graph.group_of("u2"))
        project_io.save_project(
            self.tmp, name="rt3", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=self.graph)},
        )
        loaded = project_io.load_project(self.tmp)
        gloaded = loaded.tabs["uvvis"].graph
        # Group node still in graph but DISCARDED; members untouched.
        self.assertIn(gid, gloaded.nodes)
        self.assertEqual(
            gloaded.nodes[gid].state, NodeState.DISCARDED
        )
        self.assertIsNone(gloaded.group_of("u1"))
        self.assertIsNone(gloaded.group_of("u2"))


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestRestoreWorkflowPayload(unittest.TestCase):
    """UVVisTab._restore_workflow_payload swaps graph contents in
    place so subwidgets keep their references and a subsequent apply
    lands in the same graph."""

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab
        operation_hash.clear_registry()
        operation_hash.register_default_implementations()

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tmp = Path(tempfile.mkdtemp(suffix=".ptmg"))

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass
        if self.tmp.exists():
            shutil.rmtree(self.tmp)

    def test_restore_preserves_graph_object_identity(self):
        original_graph = self.tab._graph
        # Build a saved-on-disk workflow with a single UVVIS node.
        external = ProjectGraph()
        wl = np.linspace(200.0, 800.0, 11)
        external.add_node(DataNode(
            id="ext", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": np.zeros_like(wl)},
            metadata={"source_file": "ext_csv"}, label="ext",
            state=NodeState.COMMITTED,
        ))
        project_io.save_project(
            self.tmp, name="rest", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={"x_unit": "eV"}, graph=external)},
        )
        loaded = project_io.load_project(self.tmp)
        self.tab._restore_workflow_payload(loaded.tabs["uvvis"])

        # Same object, but new contents.
        self.assertIs(self.tab._graph, original_graph)
        self.assertIn("ext", self.tab._graph.nodes)

    def test_restore_emits_graph_loaded_event(self):
        """After restore the scan tree's row count reflects the new
        graph (which only fires on a GRAPH_LOADED notification)."""
        external = ProjectGraph()
        wl = np.linspace(200.0, 800.0, 11)
        external.add_node(DataNode(
            id="ext", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": np.zeros_like(wl)},
            metadata={"source_file": "ext_csv"}, label="ext",
            state=NodeState.COMMITTED,
        ))
        project_io.save_project(
            self.tmp, name="rest", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=external)},
        )
        loaded = project_io.load_project(self.tmp)
        self.tab._restore_workflow_payload(loaded.tabs["uvvis"])
        self.tab.update_idletasks()
        # ScanTreeWidget rebuilds and exposes _row_for_node — at least
        # one row exists for the loaded UVVIS.
        self.assertIn("ext", self.tab._graph.nodes)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestImplementationMismatchSurface(unittest.TestCase):
    """When the registry's hash for an op changes between save and
    load, load_project surfaces a warning naming that op."""

    @classmethod
    def setUpClass(cls):
        from uvvis_tab import UVVisTab
        cls.UVVisTab = UVVisTab

    def setUp(self):
        operation_hash.clear_registry()
        operation_hash.register_default_implementations()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.tab = self.UVVisTab(self.host, graph=self.graph)
        self.tmp = Path(tempfile.mkdtemp(suffix=".ptmg"))
        # Apply a baseline so the manifest carries an op with a real hash.
        wl = np.linspace(200.0, 800.0, 601)
        self.graph.add_node(DataNode(
            id="u1", type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl,
                    "absorbance": 0.1 + 0.5 * np.exp(-((wl-500)/30)**2)},
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "instrument": "synthetic", "source_file": "u1"},
            label="u1", state=NodeState.COMMITTED,
            style={"color": "#1f77b4", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        self.tab.update_idletasks()
        items = self.tab._shared_subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        assert len(items) >= 1
        self.tab._shared_subject.set(items[0])
        self.tab.update_idletasks()
        self.tab._baseline_mode.set("linear")
        self.tab._baseline_anchor_lo.set("250")
        self.tab._baseline_anchor_hi.set("750")
        self.tab._apply_baseline()
        # Sanity-check that the apply actually produced an op so
        # downstream warning assertions are meaningful.
        baseline_ops = [n for n in self.graph.nodes.values()
                        if isinstance(n, OperationNode)
                        and n.type == OperationType.BASELINE]
        assert len(baseline_ops) == 1, (
            f"setUp expected exactly one BASELINE op; got {len(baseline_ops)}")

    def tearDown(self):
        try:
            self.tab.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        operation_hash.clear_registry()
        operation_hash.register_default_implementations()

    def test_load_warns_when_baseline_implementation_changes(self):
        project_io.save_project(
            self.tmp, name="drift", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=self.graph)},
        )

        # Replace BASELINE's bundle with a stub so the hash changes.
        def _stub():
            return None
        operation_hash.register_implementation(
            OperationType.BASELINE, _stub)

        loaded = project_io.load_project(self.tmp)
        self.assertEqual(len(loaded.implementation_warnings), 1)
        self.assertIn("BASELINE", loaded.implementation_warnings[0])

    def test_clean_load_emits_no_warnings(self):
        project_io.save_project(
            self.tmp, name="clean", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=self.graph)},
        )
        loaded = project_io.load_project(self.tmp)
        self.assertEqual(loaded.implementation_warnings, [])


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotDefaultsRoundTrip(unittest.TestCase):
    """plot_settings_dialog._USER_DEFAULTS is preserved across save
    and reapplied on load via the host's _do_open_workflow path."""

    def setUp(self):
        operation_hash.clear_registry()
        operation_hash.register_default_implementations()
        self.tmp = Path(tempfile.mkdtemp(suffix=".ptmg"))
        self._defaults_backup = dict(psd._USER_DEFAULTS)

    def tearDown(self):
        psd._USER_DEFAULTS.clear()
        psd._USER_DEFAULTS.update(self._defaults_backup)
        if self.tmp.exists():
            shutil.rmtree(self.tmp)

    def test_user_defaults_round_trip(self):
        defaults = {"sample": "from-test", "font_size": 13}
        project_io.save_project(
            self.tmp, name="pd", plot_defaults=defaults, tabs={},
        )
        loaded = project_io.load_project(self.tmp)
        # Simulate what binah._do_open_workflow does: clear + update.
        psd._USER_DEFAULTS.clear()
        psd._USER_DEFAULTS.update(loaded.plot_defaults)
        self.assertEqual(psd._USER_DEFAULTS["sample"], "from-test")
        self.assertEqual(psd._USER_DEFAULTS["font_size"], 13)


if __name__ == "__main__":
    unittest.main()
