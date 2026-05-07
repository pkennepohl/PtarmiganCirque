"""Pure-module tests for the OperationNode metadata + deterministic
fields added in Phase 4v (CS-45).

Run with:  python -m pytest test_nodes_metadata_field.py -v
"""

from __future__ import annotations

import copy
import unittest

from nodes import OperationNode, OperationType, NodeState


def _make_op(**overrides) -> OperationNode:
    base = dict(
        id="op",
        type=OperationType.LOAD,
        engine="internal",
        engine_version="0.1",
        params={},
        input_ids=[],
        output_ids=[],
    )
    base.update(overrides)
    return OperationNode(**base)


class TestOperationNodeMetadataDefault(unittest.TestCase):
    """metadata defaults to a fresh empty dict per instance."""

    def test_default_is_empty_dict(self):
        op = _make_op()
        self.assertEqual(op.metadata, {})

    def test_default_dict_is_per_instance(self):
        op1 = _make_op(id="op1")
        op2 = _make_op(id="op2")
        op1.metadata["implementation_hash"] = "abc"
        self.assertNotIn("implementation_hash", op2.metadata)

    def test_metadata_accepts_arbitrary_json_compatible_payload(self):
        op = _make_op(metadata={"implementation_hash": "deadbeef",
                                "duration_breakdown": {"fit_ms": 12,
                                                       "validate_ms": 1}})
        self.assertEqual(op.metadata["implementation_hash"], "deadbeef")
        self.assertEqual(op.metadata["duration_breakdown"]["fit_ms"], 12)


class TestOperationNodeDeterministicDefault(unittest.TestCase):
    """deterministic defaults to True (every op shipped today is)."""

    def test_default_is_true(self):
        op = _make_op()
        self.assertTrue(op.deterministic)

    def test_explicit_false_round_trips(self):
        op = _make_op(deterministic=False)
        self.assertFalse(op.deterministic)


class TestOperationNodeShape(unittest.TestCase):
    """The new fields do not break the existing positional contract."""

    def test_field_count(self):
        # 12 original + metadata + deterministic = 14
        self.assertEqual(len(OperationNode.__dataclass_fields__), 14)

    def test_deepcopy_preserves_independence(self):
        op = _make_op(metadata={"implementation_hash": "x"})
        clone = copy.deepcopy(op)
        clone.metadata["implementation_hash"] = "y"
        self.assertEqual(op.metadata["implementation_hash"], "x")

    def test_state_default_unchanged(self):
        op = _make_op()
        self.assertEqual(op.state, NodeState.PROVISIONAL)


if __name__ == "__main__":
    unittest.main()
