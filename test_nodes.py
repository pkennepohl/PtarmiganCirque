"""Light tests for nodes.py.

These are sanity checks, not a full coverage suite: they verify that
the dataclasses instantiate with sensible defaults, that all enum
variants documented in COMPONENTS.md (CS-02 / CS-03) are present,
and that the style dict on a DataNode is independent per instance.

Run with:  python -m pytest test_nodes.py -v
       or:  python test_nodes.py
"""

from __future__ import annotations

import unittest
from datetime import datetime

import numpy as np

from nodes import (
    DataNode,
    NodeState,
    NodeType,
    OperationNode,
    OperationType,
)


class TestNodeTypeEnum(unittest.TestCase):
    """All NodeType variants from CS-02 are present."""

    EXPECTED = {
        "RAW_FILE", "XANES", "EXAFS", "UVVIS",
        "DEGLITCHED", "NORMALISED", "SMOOTHED", "SHIFTED",
        "BASELINE", "AVERAGED", "DIFFERENCE",
        "TDDFT", "FEFF_PATHS", "BXAS_RESULT",
    }

    def test_all_documented_variants_exist(self):
        actual = {m.name for m in NodeType}
        missing = self.EXPECTED - actual
        self.assertFalse(missing, f"Missing NodeType variants: {missing}")

    def test_variants_are_unique(self):
        values = [m.value for m in NodeType]
        self.assertEqual(len(values), len(set(values)))


class TestNodeStateEnum(unittest.TestCase):

    def test_three_states_exist(self):
        names = {m.name for m in NodeState}
        self.assertEqual(names, {"PROVISIONAL", "COMMITTED", "DISCARDED"})


class TestOperationTypeEnum(unittest.TestCase):
    """All OperationType variants from CS-03 are present."""

    EXPECTED = {
        "LOAD", "DEGLITCH", "NORMALISE", "SMOOTH", "SHIFT_ENERGY",
        "BASELINE", "AVERAGE", "DIFFERENCE", "FEFF_RUN", "BXAS_FIT",
    }

    def test_all_documented_variants_exist(self):
        actual = {m.name for m in OperationType}
        missing = self.EXPECTED - actual
        self.assertFalse(missing, f"Missing OperationType variants: {missing}")


class TestDataNode(unittest.TestCase):

    def _make_minimal(self, **overrides) -> DataNode:
        kwargs = dict(
            id="ds_001",
            type=NodeType.UVVIS,
            arrays={
                "wavelength_nm": np.linspace(200.0, 800.0, 5),
                "absorbance":    np.array([0.1, 0.2, 0.3, 0.2, 0.1]),
            },
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "instrument": "OLIS"},
            label="test scan",
        )
        kwargs.update(overrides)
        return DataNode(**kwargs)

    def test_instantiates_with_defaults(self):
        n = self._make_minimal()
        self.assertEqual(n.id, "ds_001")
        self.assertEqual(n.type, NodeType.UVVIS)
        self.assertEqual(n.state, NodeState.PROVISIONAL)
        self.assertTrue(n.active)
        self.assertEqual(n.style, {})
        self.assertIsInstance(n.created_at, datetime)

    def test_arrays_are_numpy(self):
        n = self._make_minimal()
        self.assertIsInstance(n.arrays["wavelength_nm"], np.ndarray)
        self.assertIsInstance(n.arrays["absorbance"], np.ndarray)

    def test_style_dicts_are_independent(self):
        # field(default_factory=dict) must not be a shared singleton.
        a = self._make_minimal(id="a")
        b = self._make_minimal(id="b")
        a.style["color"] = "red"
        self.assertEqual(b.style, {})

    def test_state_can_be_overridden(self):
        n = self._make_minimal(state=NodeState.COMMITTED)
        self.assertEqual(n.state, NodeState.COMMITTED)


class TestOperationNode(unittest.TestCase):

    def test_instantiates_with_defaults(self):
        op = OperationNode(
            id="op_001",
            type=OperationType.NORMALISE,
            engine="larch",
            engine_version="0.9.80",
            params={"e0": 2470.3, "pre1": -150.0, "pre2": -30.0,
                    "nor1": 19.0, "nor2": 119.3, "nnorm": 2},
            input_ids=["ds_001"],
            output_ids=["ds_002"],
        )
        self.assertEqual(op.id, "op_001")
        self.assertEqual(op.engine, "larch")
        self.assertEqual(op.engine_version, "0.9.80")
        self.assertEqual(op.status, "SUCCESS")
        self.assertEqual(op.duration_ms, 0)
        self.assertEqual(op.log, "")
        self.assertEqual(op.state, NodeState.PROVISIONAL)
        self.assertIsInstance(op.timestamp, datetime)

    def test_input_output_lists_independent(self):
        a = OperationNode(
            id="op_a", type=OperationType.LOAD, engine="internal",
            engine_version="1.0", params={}, input_ids=[], output_ids=[],
        )
        b = OperationNode(
            id="op_b", type=OperationType.LOAD, engine="internal",
            engine_version="1.0", params={}, input_ids=[], output_ids=[],
        )
        a.input_ids.append("x")
        a.output_ids.append("y")
        self.assertEqual(b.input_ids, [])
        self.assertEqual(b.output_ids, [])


class TestNormalisedNodeAndOperation(unittest.TestCase):
    """Phase 4e — pin the NORMALISED / NORMALISE contract.

    The enum members existed before Phase 4e; the specific contract
    locked here is the mode-discriminated ``params`` dict for the
    UV/Vis NORMALISE operation (mirrors Phase 4c BASELINE per
    CS-15 / CS-16). These tests are intentionally focused on the
    new operation's shape, not on the rest of the enum surface
    (which ``TestNodeTypeEnum`` and ``TestOperationTypeEnum``
    already cover).
    """

    def test_normalised_data_node_constructs(self):
        wl = np.linspace(200.0, 800.0, 5)
        absorb = np.array([0.10, 0.45, 1.00, 0.30, 0.05])
        n = DataNode(
            id="norm1",
            type=NodeType.NORMALISED,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"x_unit": "nm", "y_unit": "absorbance",
                      "normalisation_mode": "peak",
                      "normalisation_parent_id": "uvvis_a"},
            label="syn · norm (peak)",
        )
        self.assertEqual(n.type, NodeType.NORMALISED)
        self.assertEqual(n.state, NodeState.PROVISIONAL)
        self.assertIn("wavelength_nm", n.arrays)
        self.assertIn("absorbance", n.arrays)
        self.assertEqual(n.metadata["normalisation_mode"], "peak")
        self.assertEqual(n.metadata["normalisation_parent_id"], "uvvis_a")

    def test_normalise_op_with_peak_params(self):
        # CS-03 params completeness: every key needed to reproduce the
        # operation must live in ``params``. Peak mode requires the
        # mode discriminator + the resolved peak window in nm.
        op = OperationNode(
            id="op_n_peak",
            type=OperationType.NORMALISE,
            engine="internal",
            engine_version="0.0",
            params={"mode": "peak",
                    "peak_lo_nm": 400.0, "peak_hi_nm": 600.0},
            input_ids=["uvvis_a"],
            output_ids=["norm_a"],
        )
        self.assertEqual(op.type, OperationType.NORMALISE)
        self.assertEqual(op.params["mode"], "peak")
        self.assertEqual(op.params["peak_lo_nm"], 400.0)
        self.assertEqual(op.params["peak_hi_nm"], 600.0)
        self.assertEqual(op.state, NodeState.PROVISIONAL)
        self.assertEqual(op.engine, "internal")

    def test_normalise_op_with_area_params(self):
        # Area mode: integration window endpoints in nm.
        op = OperationNode(
            id="op_n_area",
            type=OperationType.NORMALISE,
            engine="internal",
            engine_version="0.0",
            params={"mode": "area",
                    "area_lo_nm": 200.0, "area_hi_nm": 800.0},
            input_ids=["uvvis_a"],
            output_ids=["norm_a"],
        )
        self.assertEqual(op.params["mode"], "area")
        self.assertEqual(op.params["area_lo_nm"], 200.0)
        self.assertEqual(op.params["area_hi_nm"], 800.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
