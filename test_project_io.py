"""Pure-module tests for project_io manifest+sidecar round-trip
(Phase 4v / CS-46).

Run with:  python -m pytest test_project_io.py -v
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

import project_io
from graph import ProjectGraph
from nodes import (
    DataNode,
    NodeState,
    NodeType,
    OperationNode,
    OperationType,
)
from operation_hash import (
    SENTINEL_PREFIX,
    clear_registry,
    compute_implementation_hash,
    register_default_implementations,
    register_implementation,
)


def _spectrum(n: int = 21) -> dict[str, np.ndarray]:
    """A small UV/Vis-shaped arrays dict."""
    wl = np.linspace(200, 800, n)
    a = 0.1 + 0.5 * np.exp(-((wl - 400) / 50.0) ** 2)
    return {"wavelength_nm": wl, "absorbance": a}


def _make_graph_with_baseline_chain() -> ProjectGraph:
    """A representative two-node provenance chain: UVVIS parent + a
    BASELINE child with one OperationNode wiring them together."""
    register_default_implementations()
    g = ProjectGraph()
    parent = DataNode(
        id="parent", type=NodeType.UVVIS,
        arrays=_spectrum(),
        metadata={"source_file": "fake.csv"},
        label="Parent",
    )
    g.add_node(parent)
    op = OperationNode(
        id="op1", type=OperationType.BASELINE,
        engine="internal", engine_version="0.1",
        params={"mode": "linear", "a_lo": 250.0, "a_hi": 750.0,
                "floor_zero": False},
        input_ids=["parent"], output_ids=["child"],
        metadata={"implementation_hash":
                  compute_implementation_hash(OperationType.BASELINE)},
    )
    g.add_node(op)
    child = DataNode(
        id="child", type=NodeType.BASELINE,
        arrays={"wavelength_nm": _spectrum()["wavelength_nm"],
                "absorbance": _spectrum()["absorbance"] - 0.1},
        metadata={"source_op": "op1"},
        label="Parent baseline",
        state=NodeState.COMMITTED,
    )
    g.add_node(child)
    g.add_edge("parent", "op1")
    g.add_edge("op1", "child")
    return g


class _TmpProjectMixin:
    """Each test runs in its own temp .ptmg directory."""

    def setUp(self):
        clear_registry()
        register_default_implementations()
        self.tmp = Path(tempfile.mkdtemp(suffix=".ptmg"))

    def tearDown(self):
        clear_registry()
        if self.tmp.exists():
            shutil.rmtree(self.tmp)


class TestEmptySaveLoad(_TmpProjectMixin, unittest.TestCase):
    """Saving an empty project produces a valid manifest that loads
    back into an empty workflow."""

    def test_save_empty_creates_manifest_and_sidecars_dir(self):
        project_io.save_project(
            self.tmp, name="empty",
            plot_defaults={}, tabs={},
        )
        self.assertTrue((self.tmp / "manifest.json").exists())
        self.assertTrue((self.tmp / "sidecars").is_dir())

    def test_load_empty_returns_no_tabs(self):
        project_io.save_project(self.tmp, name="empty",
                                plot_defaults={}, tabs={})
        loaded = project_io.load_project(self.tmp)
        self.assertEqual(loaded.name, "empty")
        self.assertEqual(loaded.tabs, {})

    def test_save_then_load_preserves_plot_defaults(self):
        defaults = {"theme": "light", "font_size": 11, "grid": True}
        project_io.save_project(self.tmp, name="p", plot_defaults=defaults,
                                tabs={})
        loaded = project_io.load_project(self.tmp)
        self.assertEqual(loaded.plot_defaults, defaults)


class TestRoundTrip(_TmpProjectMixin, unittest.TestCase):
    """Save then load reproduces every field on every node."""

    def test_data_node_round_trips(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="rt", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={"x_unit": "nm"}, graph=g)},
        )
        loaded = project_io.load_project(self.tmp)
        g2 = loaded.tabs["uvvis"].graph
        for nid in ("parent", "child"):
            orig = g.nodes[nid]
            roundtripped = g2.nodes[nid]
            self.assertEqual(orig.id, roundtripped.id)
            self.assertEqual(orig.type, roundtripped.type)
            self.assertEqual(orig.label, roundtripped.label)
            self.assertEqual(orig.state, roundtripped.state)
            self.assertEqual(orig.metadata, roundtripped.metadata)
            for key in orig.arrays:
                np.testing.assert_array_equal(
                    orig.arrays[key], roundtripped.arrays[key])

    def test_op_node_round_trips_with_implementation_hash(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="rt", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        loaded = project_io.load_project(self.tmp)
        op = loaded.tabs["uvvis"].graph.nodes["op1"]
        self.assertIsInstance(op, OperationNode)
        self.assertEqual(op.params["mode"], "linear")
        self.assertEqual(op.metadata["implementation_hash"],
                         compute_implementation_hash(OperationType.BASELINE))
        self.assertTrue(op.deterministic)

    def test_edges_round_trip(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="rt", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        loaded = project_io.load_project(self.tmp)
        self.assertEqual(
            sorted(loaded.tabs["uvvis"].graph.edges),
            sorted([("parent", "op1"), ("op1", "child")]),
        )

    def test_load_emits_no_warnings_when_implementation_unchanged(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="rt", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        loaded = project_io.load_project(self.tmp)
        self.assertEqual(loaded.implementation_warnings, [])


class TestSidecarDedup(_TmpProjectMixin, unittest.TestCase):
    """Two DataNodes with identical arrays share one sidecar."""

    def test_identical_arrays_share_sidecar(self):
        g = ProjectGraph()
        arrays = _spectrum()
        for nid in ("a", "b"):
            g.add_node(DataNode(
                id=nid, type=NodeType.UVVIS,
                arrays={k: v.copy() for k, v in arrays.items()},
                metadata={}, label=nid,
            ))
        project_io.save_project(
            self.tmp, name="dedup", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        sidecars = list((self.tmp / "sidecars").glob("*.h5"))
        self.assertEqual(len(sidecars), 1,
                         "Two identical arrays should share one sidecar")

    def test_distinct_arrays_get_separate_sidecars(self):
        g = ProjectGraph()
        for nid, scale in (("a", 1.0), ("b", 2.0)):
            arrays = _spectrum()
            arrays["absorbance"] = arrays["absorbance"] * scale
            g.add_node(DataNode(
                id=nid, type=NodeType.UVVIS,
                arrays=arrays, metadata={}, label=nid,
            ))
        project_io.save_project(
            self.tmp, name="distinct", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        sidecars = list((self.tmp / "sidecars").glob("*.h5"))
        self.assertEqual(len(sidecars), 2)


class TestVerifyMismatch(_TmpProjectMixin, unittest.TestCase):
    """verify_project surfaces sidecar tampering and implementation
    drift."""

    def test_no_warnings_on_unmodified_save(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="ok", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        result = project_io.verify_project(self.tmp)
        self.assertEqual(result["array_warnings"], [])
        self.assertEqual(result["implementation_warnings"], [])

    def test_array_warning_on_sidecar_tamper(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="t", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        # Mutate a sidecar so its content hash no longer matches.
        sidecars = list((self.tmp / "sidecars").glob("*.h5"))
        with h5py.File(sidecars[0], "r+") as f:
            arr = f["absorbance"][...]
            arr[0] = arr[0] + 99.0
            del f["absorbance"]
            f.create_dataset("absorbance", data=arr)
        result = project_io.verify_project(self.tmp)
        self.assertEqual(len(result["array_warnings"]), 1)
        self.assertIn("hash mismatch", result["array_warnings"][0])

    def test_array_warning_on_missing_sidecar(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="m", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        for sc in (self.tmp / "sidecars").glob("*.h5"):
            sc.unlink()
        result = project_io.verify_project(self.tmp)
        self.assertTrue(any("missing" in w
                            for w in result["array_warnings"]))

    def test_implementation_warning_on_registry_change(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="i", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )

        # Simulate the implementation drift by re-registering
        # BASELINE with a different (stub) bundle. Whatever new hash
        # is computed will not equal the saved one.
        def _stub_baseline():
            return "different"
        register_implementation(OperationType.BASELINE, _stub_baseline)

        result = project_io.verify_project(self.tmp)
        self.assertEqual(len(result["implementation_warnings"]), 1)
        msg = result["implementation_warnings"][0]
        self.assertIn("BASELINE", msg)
        self.assertIn("changed", msg)

    def test_implementation_warning_on_registry_dropped(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="d", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        clear_registry()  # nothing registered ⇒ sentinel
        result = project_io.verify_project(self.tmp)
        self.assertEqual(len(result["implementation_warnings"]), 1)
        self.assertIn("no implementation is registered",
                      result["implementation_warnings"][0])

    def test_load_implementation_warnings_match_verify(self):
        g = _make_graph_with_baseline_chain()
        project_io.save_project(
            self.tmp, name="match", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )

        def _stub():
            return None
        register_implementation(OperationType.BASELINE, _stub)

        loaded = project_io.load_project(self.tmp)
        verify = project_io.verify_project(self.tmp)
        # Both surfaces flag the same op (different message strings,
        # same root cause). One warning each.
        self.assertEqual(len(loaded.implementation_warnings), 1)
        self.assertEqual(len(verify["implementation_warnings"]), 1)


class TestErrorPaths(_TmpProjectMixin, unittest.TestCase):
    """Malformed / missing inputs raise the expected exceptions."""

    def test_load_missing_dir_raises(self):
        with self.assertRaises(FileNotFoundError):
            project_io.load_project(self.tmp / "nonexistent")

    def test_load_dir_without_manifest_raises(self):
        with self.assertRaises(FileNotFoundError):
            project_io.load_project(self.tmp)

    def test_load_unrecognised_format_raises(self):
        (self.tmp / "manifest.json").write_text(
            json.dumps({"ptarmigan_format": "not-ptmg",
                        "ptarmigan_format_version": 1}),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            project_io.load_project(self.tmp)

    def test_load_unsupported_version_raises(self):
        (self.tmp / "manifest.json").write_text(
            json.dumps({"ptarmigan_format": "ptmg",
                        "ptarmigan_format_version": 999}),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            project_io.load_project(self.tmp)


class TestCreatedAtPersistsAcrossSaves(_TmpProjectMixin, unittest.TestCase):
    """Re-saving in place preserves the original created_at timestamp."""

    def test_created_at_unchanged_on_resave(self):
        project_io.save_project(self.tmp, name="t1",
                                plot_defaults={}, tabs={})
        first = project_io.load_project(self.tmp).created_at
        project_io.save_project(self.tmp, name="t2",
                                plot_defaults={}, tabs={})
        second = project_io.load_project(self.tmp)
        self.assertEqual(second.created_at, first)
        self.assertEqual(second.name, "t2")


class TestJsonifyHelpers(_TmpProjectMixin, unittest.TestCase):
    """numpy values inside params/metadata round-trip through JSON."""

    def test_numpy_scalar_in_params_survives_save(self):
        g = ProjectGraph()
        op = OperationNode(
            id="np", type=OperationType.NORMALISE,
            engine="internal", engine_version="0.1",
            params={"target": np.float64(1.5),
                    "window": (np.int64(200), np.int64(800))},
            input_ids=[], output_ids=[],
        )
        g.add_node(op)
        project_io.save_project(
            self.tmp, name="np", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        loaded = project_io.load_project(self.tmp)
        op2 = loaded.tabs["uvvis"].graph.nodes["np"]
        self.assertEqual(op2.params["target"], 1.5)
        self.assertEqual(op2.params["window"], [200, 800])


class TestUnregisteredOpRoundTrip(_TmpProjectMixin, unittest.TestCase):
    """Unregistered op types round-trip without producing warnings."""

    def test_sentinel_stored_op_does_not_warn(self):
        clear_registry()  # no registrations ⇒ everything is sentinel
        g = ProjectGraph()
        op = OperationNode(
            id="ds", type=OperationType.DEGLITCH,
            engine="internal", engine_version="0.1",
            params={}, input_ids=[], output_ids=[],
            metadata={"implementation_hash":
                      compute_implementation_hash(OperationType.DEGLITCH)},
        )
        g.add_node(op)
        project_io.save_project(
            self.tmp, name="ds", plot_defaults={},
            tabs={"uvvis": project_io.TabPayload(
                plot_config={}, graph=g)},
        )
        loaded = project_io.load_project(self.tmp)
        self.assertEqual(loaded.implementation_warnings, [])
        self.assertTrue(loaded.tabs["uvvis"].graph.nodes["ds"]
                        .metadata["implementation_hash"]
                        .startswith(SENTINEL_PREFIX))


if __name__ == "__main__":
    unittest.main()
