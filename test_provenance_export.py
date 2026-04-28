"""Tests for provenance_export.py (Phase 4f, CS-17).

Pure-Python tests — no Tk involvement. Construct a real
``ProjectGraph`` with a few hand-built nodes and assert that
``build_provenance_header`` emits the expected ``# ``-prefixed lines.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime

import numpy as np

from graph import ProjectGraph
from nodes import DataNode, NodeState, NodeType, OperationNode, OperationType
from provenance_export import build_provenance_header
from version import __version__ as PTARMIGAN_VERSION


def _data(nid: str, ntype: NodeType, label: str | None = None,
          state: NodeState = NodeState.COMMITTED) -> DataNode:
    return DataNode(
        id=nid, type=ntype, arrays={"x": np.arange(3)},
        metadata={}, label=label or nid, state=state,
    )


def _op(oid: str, otype: OperationType, params: dict,
        inputs: list[str], outputs: list[str],
        engine: str = "internal", engine_version: str = "0.0.0",
        ) -> OperationNode:
    return OperationNode(
        id=oid, type=otype, engine=engine,
        engine_version=engine_version, params=dict(params),
        input_ids=list(inputs), output_ids=list(outputs),
    )


class TestProvenanceExportSingleNode(unittest.TestCase):
    """Header for a graph with only the requested node."""

    def test_single_node_yields_one_ancestor_line(self):
        graph = ProjectGraph()
        graph.add_node(_data("aaaa1111bbbb", NodeType.UVVIS, label="solo"))

        lines = build_provenance_header(graph, "aaaa1111bbbb")

        # Envelope (4) + one ancestor for the node itself.
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], f"# ptarmigan_version={PTARMIGAN_VERSION}")
        self.assertTrue(lines[1].startswith("# exported_at="))
        self.assertEqual(lines[2], "# node_id=aaaa1111bbbb")
        self.assertEqual(lines[3], "# node_label=solo")
        self.assertEqual(
            lines[4],
            "# ancestor[0] type=UVVIS id=aaaa1111 label=solo",
        )

    def test_every_line_is_hash_prefixed_no_newline(self):
        graph = ProjectGraph()
        graph.add_node(_data("nid_xyz_0001", NodeType.UVVIS))

        lines = build_provenance_header(graph, "nid_xyz_0001")

        for line in lines:
            self.assertTrue(line.startswith("# "), repr(line))
            self.assertNotIn("\n", line, repr(line))


class TestProvenanceExportChainOrder(unittest.TestCase):
    """A UVVIS → BASELINE → NORMALISED chain emits five ancestor lines.

    Mirrors the brief: one DataNode line per node + one OperationNode
    line per intervening op, in topological order.
    """

    def setUp(self):
        # uv → op_b → bl → op_n → norm
        self.graph = ProjectGraph()
        self.graph.add_node(_data("uvuvuvuvuv00", NodeType.UVVIS, label="uv"))
        self.graph.add_node(_op(
            "opbopbopbopb", OperationType.BASELINE,
            {"mode": "linear", "anchor_lo_nm": 200.0,
             "anchor_hi_nm": 700.0},
            inputs=["uvuvuvuvuv00"], outputs=["blblblblbl00"],
        ))
        self.graph.add_node(_data(
            "blblblblbl00", NodeType.BASELINE, label="uv (baseline)",
        ))
        self.graph.add_node(_op(
            "opnopnopnopn", OperationType.NORMALISE,
            {"mode": "peak", "peak_lo_nm": 400.0, "peak_hi_nm": 600.0},
            inputs=["blblblblbl00"], outputs=["nrnrnrnrnr00"],
        ))
        self.graph.add_node(_data(
            "nrnrnrnrnr00", NodeType.NORMALISED, label="uv (normalised)",
        ))
        self.graph.add_edge("uvuvuvuvuv00", "opbopbopbopb")
        self.graph.add_edge("opbopbopbopb", "blblblblbl00")
        self.graph.add_edge("blblblblbl00", "opnopnopnopn")
        self.graph.add_edge("opnopnopnopn", "nrnrnrnrnr00")

    def test_chain_has_envelope_plus_five_ancestors(self):
        lines = build_provenance_header(self.graph, "nrnrnrnrnr00")
        # 4 envelope + 5 ancestors.
        self.assertEqual(len(lines), 9)

    def test_ancestor_lines_in_topological_order(self):
        lines = build_provenance_header(self.graph, "nrnrnrnrnr00")
        ancestors = lines[4:]

        self.assertIn("type=UVVIS", ancestors[0])
        self.assertIn("op=BASELINE", ancestors[1])
        self.assertIn("type=BASELINE", ancestors[2])
        self.assertIn("op=NORMALISE", ancestors[3])
        self.assertIn("type=NORMALISED", ancestors[4])

        # And the indices count up.
        for idx, line in enumerate(ancestors):
            self.assertIn(f"ancestor[{idx}]", line)

    def test_data_ancestor_carries_short_id_and_label(self):
        lines = build_provenance_header(self.graph, "nrnrnrnrnr00")
        leaf = lines[-1]
        # Short hex is the first 8 characters of the full id.
        self.assertIn("id=nrnrnrnr", leaf)
        self.assertIn("label=uv (normalised)", leaf)
        # Full hex must NOT appear in the ancestor line (we only show
        # short on ancestor lines; the full id lives on the envelope).
        self.assertNotIn("nrnrnrnrnr00", leaf)

    def test_op_ancestor_params_round_trip_as_json(self):
        lines = build_provenance_header(self.graph, "nrnrnrnrnr00")
        norm_op_line = next(
            line for line in lines if "op=NORMALISE" in line
        )
        # Pull out the `params=` payload; everything after the literal
        # ``params=`` token is one JSON document on a single line.
        _, _, params_json = norm_op_line.partition("params=")
        parsed = json.loads(params_json)
        self.assertEqual(parsed["mode"], "peak")
        self.assertEqual(parsed["peak_lo_nm"], 400.0)
        self.assertEqual(parsed["peak_hi_nm"], 600.0)

    def test_op_ancestor_carries_engine_and_version(self):
        lines = build_provenance_header(self.graph, "nrnrnrnrnr00")
        line = next(line for line in lines if "op=BASELINE" in line)
        self.assertIn("engine=internal", line)
        self.assertIn("engine_version=0.0.0", line)


class TestProvenanceExportEnvelope(unittest.TestCase):
    """Envelope-line invariants."""

    def test_exported_at_is_iso_8601_parseable(self):
        graph = ProjectGraph()
        graph.add_node(_data("idididid0000", NodeType.UVVIS))

        lines = build_provenance_header(graph, "idididid0000")
        ts_line = lines[1]
        _, _, ts_value = ts_line.partition("# exported_at=")
        # ``datetime.fromisoformat`` accepts the timezone-aware shape
        # produced by ``datetime.now(timezone.utc).isoformat()`` from
        # Python 3.11 onwards, including the ``+00:00`` offset.
        parsed = datetime.fromisoformat(ts_value)
        self.assertIsNotNone(parsed.tzinfo,
                             "exported_at must carry timezone info")

    def test_full_node_id_lives_on_envelope_line(self):
        graph = ProjectGraph()
        graph.add_node(_data("123456789abcdef", NodeType.UVVIS, label="x"))

        lines = build_provenance_header(graph, "123456789abcdef")
        # Envelope carries the full hex even when it's longer than 8.
        self.assertEqual(lines[2], "# node_id=123456789abcdef")


class TestProvenanceExportErrors(unittest.TestCase):
    """Error semantics."""

    def test_missing_node_raises_key_error(self):
        graph = ProjectGraph()
        with self.assertRaises(KeyError):
            build_provenance_header(graph, "ghost-id")


if __name__ == "__main__":
    unittest.main(verbosity=2)
