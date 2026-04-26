"""Tests for graph.py.

Covers the core ProjectGraph contract:

* add_node, add_edge happy paths and rejections (duplicate id, unknown
  endpoints, self-loop, duplicate edge)
* commit_node and discard_node state-transition rules
* observer pattern: subscribe / unsubscribe / event delivery and order
* cycle detection rejects edges that would close a loop
* provenance_chain returns ancestors in topological order

Run with:  python -m pytest test_graph.py -v
       or:  python test_graph.py
"""

from __future__ import annotations

import unittest

import numpy as np

from graph import (
    GraphEvent,
    GraphEventType,
    ProjectGraph,
)
from nodes import (
    DataNode,
    NodeState,
    NodeType,
    OperationNode,
    OperationType,
)


# ---- helpers --------------------------------------------------------

def _data(node_id: str, ntype: NodeType = NodeType.RAW_FILE,
          state: NodeState = NodeState.PROVISIONAL,
          label: str | None = None) -> DataNode:
    return DataNode(
        id=node_id,
        type=ntype,
        arrays={"x": np.arange(3)},
        metadata={},
        label=label or node_id,
        state=state,
    )


def _op(op_id: str, otype: OperationType = OperationType.LOAD,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        state: NodeState = NodeState.PROVISIONAL) -> OperationNode:
    return OperationNode(
        id=op_id,
        type=otype,
        engine="internal",
        engine_version="0.0.0",
        params={},
        input_ids=list(inputs or []),
        output_ids=list(outputs or []),
        state=state,
    )


# ---- tests ----------------------------------------------------------

class TestAddNodeAndEdge(unittest.TestCase):

    def test_add_and_get_node(self):
        g = ProjectGraph()
        n = _data("a")
        g.add_node(n)
        self.assertIs(g.get_node("a"), n)

    def test_add_node_rejects_duplicate_id(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        with self.assertRaises(ValueError):
            g.add_node(_data("a"))

    def test_get_node_unknown_id(self):
        g = ProjectGraph()
        with self.assertRaises(KeyError):
            g.get_node("nope")

    def test_add_edge_and_query_neighbours(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        g.add_node(_data("b"))
        g.add_node(_data("c"))
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        self.assertEqual(set(g.children_of("a")), {"b", "c"})
        self.assertEqual(g.parents_of("b"), ["a"])
        self.assertEqual(g.parents_of("c"), ["a"])

    def test_add_edge_rejects_self_loop(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        with self.assertRaises(ValueError):
            g.add_edge("a", "a")

    def test_add_edge_rejects_duplicate(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        g.add_node(_data("b"))
        g.add_edge("a", "b")
        with self.assertRaises(ValueError):
            g.add_edge("a", "b")

    def test_add_edge_rejects_unknown_endpoints(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        with self.assertRaises(KeyError):
            g.add_edge("a", "missing")
        with self.assertRaises(KeyError):
            g.add_edge("missing", "a")


class TestCommitDiscard(unittest.TestCase):

    def test_commit_provisional(self):
        g = ProjectGraph()
        n = _data("a", state=NodeState.PROVISIONAL)
        g.add_node(n)
        g.commit_node("a")
        self.assertEqual(n.state, NodeState.COMMITTED)

    def test_commit_already_committed_raises(self):
        g = ProjectGraph()
        n = _data("a", state=NodeState.COMMITTED)
        g.add_node(n)
        with self.assertRaises(ValueError):
            g.commit_node("a")

    def test_commit_discarded_raises(self):
        g = ProjectGraph()
        n = _data("a", state=NodeState.PROVISIONAL)
        g.add_node(n)
        g.discard_node("a")
        with self.assertRaises(ValueError):
            g.commit_node("a")

    def test_discard_provisional(self):
        g = ProjectGraph()
        n = _data("a", state=NodeState.PROVISIONAL)
        g.add_node(n)
        g.discard_node("a")
        self.assertEqual(n.state, NodeState.DISCARDED)

    def test_discard_committed_raises(self):
        g = ProjectGraph()
        n = _data("a", state=NodeState.COMMITTED)
        g.add_node(n)
        with self.assertRaises(ValueError):
            g.discard_node("a")


class TestObserver(unittest.TestCase):

    def test_node_added_event(self):
        g = ProjectGraph()
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.add_node(_data("a"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, GraphEventType.NODE_ADDED)
        self.assertEqual(events[0].node_id, "a")

    def test_commit_event(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.commit_node("a")
        self.assertEqual([e.type for e in events],
                         [GraphEventType.NODE_COMMITTED])

    def test_discard_event(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.discard_node("a")
        self.assertEqual([e.type for e in events],
                         [GraphEventType.NODE_DISCARDED])

    def test_label_change_event_carries_old_and_new(self):
        g = ProjectGraph()
        g.add_node(_data("a", label="old"))
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.set_label("a", "new")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, GraphEventType.NODE_LABEL_CHANGED)
        self.assertEqual(events[0].payload["old_label"], "old")
        self.assertEqual(events[0].payload["new_label"], "new")

    def test_label_unchanged_emits_nothing(self):
        g = ProjectGraph()
        g.add_node(_data("a", label="same"))
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.set_label("a", "same")
        self.assertEqual(events, [])

    def test_unsubscribe_stops_delivery(self):
        g = ProjectGraph()
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.unsubscribe(events.append)
        g.add_node(_data("a"))
        self.assertEqual(events, [])

    def test_unsubscribe_unknown_callback_is_noop(self):
        g = ProjectGraph()
        g.unsubscribe(lambda e: None)  # should not raise

    def test_multiple_subscribers_all_notified_in_order(self):
        g = ProjectGraph()
        order: list[str] = []
        g.subscribe(lambda e: order.append("A"))
        g.subscribe(lambda e: order.append("B"))
        g.add_node(_data("x"))
        self.assertEqual(order, ["A", "B"])

    def test_edge_added_event(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        g.add_node(_data("b"))
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.add_edge("a", "b")
        self.assertEqual(events[0].type, GraphEventType.EDGE_ADDED)
        self.assertEqual(events[0].payload,
                         {"parent_id": "a", "child_id": "b"})


class TestCycleDetection(unittest.TestCase):

    def test_simple_two_node_cycle_rejected(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        g.add_node(_data("b"))
        g.add_edge("a", "b")
        with self.assertRaises(ValueError):
            g.add_edge("b", "a")

    def test_three_node_cycle_rejected(self):
        g = ProjectGraph()
        for nid in ("a", "b", "c"):
            g.add_node(_data(nid))
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        with self.assertRaises(ValueError):
            g.add_edge("c", "a")

    def test_diamond_is_legal(self):
        # a -> b, a -> c, b -> d, c -> d : this is a DAG, not a cycle.
        g = ProjectGraph()
        for nid in ("a", "b", "c", "d"):
            g.add_node(_data(nid))
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        g.add_edge("b", "d")
        g.add_edge("c", "d")
        # Should reach here without raising.
        self.assertEqual(set(g.children_of("a")), {"b", "c"})
        self.assertEqual(set(g.parents_of("d")), {"b", "c"})


class TestProvenanceChain(unittest.TestCase):

    def test_linear_chain_topological_order(self):
        # raw -> op_norm -> normalised
        g = ProjectGraph()
        raw = _data("ds_raw", NodeType.RAW_FILE, state=NodeState.COMMITTED)
        op = _op("op_norm", OperationType.NORMALISE,
                 inputs=["ds_raw"], outputs=["ds_norm"],
                 state=NodeState.COMMITTED)
        nor = _data("ds_norm", NodeType.NORMALISED, state=NodeState.PROVISIONAL)
        for n in (raw, op, nor):
            g.add_node(n)
        g.add_edge("ds_raw", "op_norm")
        g.add_edge("op_norm", "ds_norm")

        chain = g.provenance_chain("ds_norm")
        ids = [n.id for n in chain]
        self.assertEqual(ids, ["ds_raw", "op_norm", "ds_norm"])

    def test_chain_for_node_with_no_parents_is_just_itself(self):
        g = ProjectGraph()
        g.add_node(_data("solo"))
        self.assertEqual([n.id for n in g.provenance_chain("solo")], ["solo"])

    def test_diamond_chain_each_ancestor_once_and_in_order(self):
        # raw -> op1 -> A
        # raw -> op2 -> B
        # A, B -> op_avg -> avg
        g = ProjectGraph()
        for nid in ("raw", "op1", "op2", "A", "B", "op_avg", "avg"):
            if nid.startswith("op"):
                g.add_node(_op(nid))
            else:
                g.add_node(_data(nid))
        g.add_edge("raw", "op1")
        g.add_edge("raw", "op2")
        g.add_edge("op1", "A")
        g.add_edge("op2", "B")
        g.add_edge("A", "op_avg")
        g.add_edge("B", "op_avg")
        g.add_edge("op_avg", "avg")

        ids = [n.id for n in g.provenance_chain("avg")]

        # Every ancestor appears exactly once, terminating at avg.
        self.assertEqual(sorted(ids),
                         sorted(["raw", "op1", "op2", "A", "B",
                                 "op_avg", "avg"]))
        self.assertEqual(ids[0], "raw")
        self.assertEqual(ids[-1], "avg")
        # Topological correctness: every parent precedes its children.
        for parent, child in [("raw", "op1"), ("raw", "op2"),
                              ("op1", "A"), ("op2", "B"),
                              ("A", "op_avg"), ("B", "op_avg"),
                              ("op_avg", "avg")]:
            self.assertLess(ids.index(parent), ids.index(child),
                            f"{parent} must precede {child}")

    def test_provenance_unknown_node_raises(self):
        g = ProjectGraph()
        with self.assertRaises(KeyError):
            g.provenance_chain("nope")


class TestNodesOfTypeAndActive(unittest.TestCase):

    def test_filter_by_type_and_state(self):
        g = ProjectGraph()
        g.add_node(_data("a", NodeType.UVVIS, state=NodeState.COMMITTED))
        g.add_node(_data("b", NodeType.UVVIS, state=NodeState.PROVISIONAL))
        g.add_node(_data("c", NodeType.XANES, state=NodeState.COMMITTED))
        committed_uv = g.nodes_of_type(NodeType.UVVIS, NodeState.COMMITTED)
        self.assertEqual([n.id for n in committed_uv], ["a"])
        all_uv = g.nodes_of_type(NodeType.UVVIS, state=None)
        self.assertEqual({n.id for n in all_uv}, {"a", "b"})

    def test_active_node_returns_deepest_non_discarded(self):
        # raw (committed) -> op -> norm (committed)
        g = ProjectGraph()
        g.add_node(_data("raw", NodeType.RAW_FILE,
                         state=NodeState.COMMITTED))
        g.add_node(_op("op"))
        g.add_node(_data("norm", NodeType.NORMALISED,
                         state=NodeState.COMMITTED))
        g.add_edge("raw", "op")
        g.add_edge("op", "norm")
        active = g.active_node_for("raw")
        self.assertIsNotNone(active)
        self.assertEqual(active.id, "norm")

    def test_active_node_skips_discarded_branch(self):
        g = ProjectGraph()
        g.add_node(_data("raw", NodeType.RAW_FILE,
                         state=NodeState.COMMITTED))
        g.add_node(_op("op"))
        g.add_node(_data("bad", NodeType.NORMALISED,
                         state=NodeState.PROVISIONAL))
        g.add_edge("raw", "op")
        g.add_edge("op", "bad")
        g.discard_node("bad")
        # Only "raw" remains as a non-discarded data node.
        active = g.active_node_for("raw")
        self.assertEqual(active.id, "raw")


if __name__ == "__main__":
    unittest.main(verbosity=2)
