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


class TestSetActive(unittest.TestCase):

    def test_set_active_changes_value_and_emits_event(self):
        g = ProjectGraph()
        n = _data("a")
        n.active = True
        g.add_node(n)
        events: list[GraphEvent] = []
        g.subscribe(events.append)

        g.set_active("a", False)

        self.assertFalse(n.active)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, GraphEventType.NODE_ACTIVE_CHANGED)
        self.assertEqual(events[0].node_id, "a")
        self.assertEqual(events[0].payload,
                         {"new_value": False, "old_value": True})

    def test_set_active_no_event_when_unchanged(self):
        g = ProjectGraph()
        n = _data("a")
        n.active = True
        g.add_node(n)
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.set_active("a", True)
        self.assertEqual(events, [])

    def test_set_active_works_on_committed_node(self):
        # active is a visualization toggle; allowed on any state.
        g = ProjectGraph()
        n = _data("a", state=NodeState.COMMITTED)
        g.add_node(n)
        g.set_active("a", False)
        self.assertFalse(n.active)

    def test_set_active_rejects_operation_node(self):
        g = ProjectGraph()
        g.add_node(_op("op"))
        with self.assertRaises(TypeError):
            g.set_active("op", False)

    def test_set_active_coerces_truthy(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        g.set_active("a", 0)
        self.assertEqual(g.get_node("a").active, False)


class TestSetStyle(unittest.TestCase):

    def test_set_style_merges_into_existing(self):
        g = ProjectGraph()
        n = _data("a")
        n.style = {"color": "red", "linewidth": 1.5}
        g.add_node(n)

        g.set_style("a", {"linewidth": 3.0, "alpha": 0.5})

        # 'color' must be preserved (merge, not replace).
        self.assertEqual(n.style,
                         {"color": "red", "linewidth": 3.0, "alpha": 0.5})

    def test_set_style_emits_event_with_partial_and_merged(self):
        g = ProjectGraph()
        n = _data("a")
        n.style = {"color": "red"}
        g.add_node(n)
        events: list[GraphEvent] = []
        g.subscribe(events.append)

        g.set_style("a", {"linewidth": 2.0})

        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.type, GraphEventType.NODE_STYLE_CHANGED)
        self.assertEqual(ev.node_id, "a")
        self.assertEqual(ev.payload["partial"], {"linewidth": 2.0})
        self.assertEqual(ev.payload["new_style"],
                         {"color": "red", "linewidth": 2.0})

    def test_set_style_empty_is_noop(self):
        g = ProjectGraph()
        g.add_node(_data("a"))
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.set_style("a", {})
        self.assertEqual(events, [])

    def test_set_style_works_on_committed_node(self):
        # Style is display-only; mutable on COMMITTED per CS-02.
        g = ProjectGraph()
        n = _data("a", state=NodeState.COMMITTED)
        g.add_node(n)
        g.set_style("a", {"color": "blue"})
        self.assertEqual(n.style.get("color"), "blue")

    def test_set_style_rejects_operation_node(self):
        g = ProjectGraph()
        g.add_node(_op("op"))
        with self.assertRaises(TypeError):
            g.set_style("op", {"color": "red"})


class TestCloneNode(unittest.TestCase):

    def test_clone_assigns_new_id_and_preserves_type(self):
        g = ProjectGraph()
        src = _data("orig", NodeType.UVVIS, state=NodeState.COMMITTED,
                    label="scan1")
        g.add_node(src)
        new_id = g.clone_node("orig")
        self.assertNotEqual(new_id, "orig")
        clone = g.get_node(new_id)
        self.assertIsInstance(clone, DataNode)
        self.assertEqual(clone.type, NodeType.UVVIS)

    def test_clone_starts_provisional_regardless_of_source_state(self):
        g = ProjectGraph()
        g.add_node(_data("orig", state=NodeState.COMMITTED))
        new_id = g.clone_node("orig")
        self.assertEqual(g.get_node(new_id).state, NodeState.PROVISIONAL)

    def test_clone_label_has_copy_suffix(self):
        g = ProjectGraph()
        g.add_node(_data("orig", label="scan1"))
        new_id = g.clone_node("orig")
        self.assertEqual(g.get_node(new_id).label, "scan1 (copy)")

    def test_clone_shares_arrays_reference(self):
        # Numpy arrays are not deep-copied — scientific data is
        # immutable on COMMITTED nodes, so sharing the dict is safe
        # and avoids duplicating large beamline tensors.
        g = ProjectGraph()
        src = _data("orig")
        g.add_node(src)
        new_id = g.clone_node("orig")
        clone = g.get_node(new_id)
        self.assertIs(clone.arrays, src.arrays)

    def test_clone_deep_copies_metadata_and_style(self):
        g = ProjectGraph()
        src = _data("orig")
        src.metadata = {"nested": {"k": 1}}
        src.style    = {"color": "red"}
        g.add_node(src)
        new_id = g.clone_node("orig")
        clone = g.get_node(new_id)

        # Top-level dicts are independent.
        self.assertIsNot(clone.metadata, src.metadata)
        self.assertIsNot(clone.style,    src.style)
        # And nested mutations don't bleed through.
        clone.metadata["nested"]["k"] = 99
        clone.style["color"] = "blue"
        self.assertEqual(src.metadata["nested"]["k"], 1)
        self.assertEqual(src.style["color"], "red")

    def test_clone_does_not_add_edges(self):
        # Caller is responsible for wiring parents to the clone.
        g = ProjectGraph()
        g.add_node(_data("parent"))
        g.add_node(_data("orig"))
        g.add_edge("parent", "orig")
        new_id = g.clone_node("orig")
        self.assertEqual(g.parents_of(new_id), [])
        self.assertEqual(g.children_of(new_id), [])

    def test_clone_emits_node_added(self):
        g = ProjectGraph()
        g.add_node(_data("orig"))
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        new_id = g.clone_node("orig")
        self.assertEqual([e.type for e in events],
                         [GraphEventType.NODE_ADDED])
        self.assertEqual(events[0].node_id, new_id)

    def test_clone_rejects_operation_node(self):
        g = ProjectGraph()
        g.add_node(_op("op"))
        with self.assertRaises(TypeError):
            g.clone_node("op")


class TestNotifyResilience(unittest.TestCase):
    """A raising subscriber must not break sibling subscribers."""

    def test_raising_subscriber_does_not_block_later_ones(self):
        g = ProjectGraph()
        delivered: list[str] = []

        def raiser(_event):
            raise RuntimeError("intentional")

        def good(_event):
            delivered.append("ok")

        g.subscribe(raiser)
        g.subscribe(good)

        # Suppress the WARNING log so the test output stays clean.
        import logging
        logging.getLogger("graph").setLevel(logging.ERROR)
        try:
            g.add_node(_data("a"))
        finally:
            logging.getLogger("graph").setLevel(logging.WARNING)

        self.assertEqual(delivered, ["ok"])

    def test_raising_subscriber_logged_at_warning(self):
        import logging
        g = ProjectGraph()

        def raiser(_event):
            raise RuntimeError("boom")

        g.subscribe(raiser)

        with self.assertLogs("graph", level="WARNING") as cm:
            g.add_node(_data("a"))

        self.assertTrue(any("subscriber" in line and "raised" in line
                            for line in cm.output))


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


class TestNormalisedNodeLifecycle(unittest.TestCase):
    """Phase 4e — pin the NORMALISED commit / discard / clone contract.

    NORMALISED is the third user-derived UV/Vis node type after UVVIS
    and BASELINE; CS-01's lifecycle rules apply uniformly across node
    types but it's worth a focused test that exercises the new node
    against the same surface (commit, discard, clone, set_style,
    parent → op → child wiring).
    """

    def _wire_uvvis_normalise_chain(self, g: ProjectGraph) -> tuple[str, str, str]:
        parent = _data("parent", NodeType.UVVIS, state=NodeState.COMMITTED)
        op = _op("op_n", OperationType.NORMALISE,
                 inputs=["parent"], outputs=["norm"],
                 state=NodeState.PROVISIONAL)
        op.params = {"mode": "peak", "peak_lo_nm": 200.0, "peak_hi_nm": 800.0}
        nor = _data("norm", NodeType.NORMALISED,
                    state=NodeState.PROVISIONAL)
        for n in (parent, op, nor):
            g.add_node(n)
        g.add_edge("parent", "op_n")
        g.add_edge("op_n", "norm")
        return "parent", "op_n", "norm"

    def test_commit_promotes_normalised(self):
        g = ProjectGraph()
        _, _, nor_id = self._wire_uvvis_normalise_chain(g)
        g.commit_node(nor_id)
        self.assertEqual(g.get_node(nor_id).state, NodeState.COMMITTED)

    def test_discard_marks_normalised(self):
        g = ProjectGraph()
        _, _, nor_id = self._wire_uvvis_normalise_chain(g)
        g.discard_node(nor_id)
        self.assertEqual(g.get_node(nor_id).state, NodeState.DISCARDED)

    def test_clone_normalised_yields_provisional_copy(self):
        g = ProjectGraph()
        _, _, nor_id = self._wire_uvvis_normalise_chain(g)
        # Set style and metadata on the source so the clone independence
        # rules (style deep-copied, metadata deep-copied, arrays shared
        # reference) can be checked.
        g.set_style(nor_id, {"color": "#abcdef"})
        g.get_node(nor_id).metadata["normalisation_mode"] = "peak"
        g.commit_node(nor_id)
        clone_id = g.clone_node(nor_id)
        clone = g.get_node(clone_id)
        self.assertEqual(clone.type, NodeType.NORMALISED)
        self.assertEqual(clone.state, NodeState.PROVISIONAL)
        self.assertIs(clone.arrays, g.get_node(nor_id).arrays)
        # Mutating the clone's style / metadata must not leak back.
        clone.style["color"] = "#000000"
        clone.metadata["normalisation_mode"] = "area"
        self.assertEqual(g.get_node(nor_id).style["color"], "#abcdef")
        self.assertEqual(
            g.get_node(nor_id).metadata["normalisation_mode"], "peak")

    def test_normalise_op_recognised_by_nodes_of_type_passthrough(self):
        # OperationType.NORMALISE is not visible via nodes_of_type
        # (it's an op, not a data node), but the OUTPUT NORMALISED
        # DataNode is — confirm the type filter picks it out.
        g = ProjectGraph()
        self._wire_uvvis_normalise_chain(g)
        norms = g.nodes_of_type(NodeType.NORMALISED, state=None)
        self.assertEqual(len(norms), 1)
        self.assertEqual(norms[0].id, "norm")


class TestFindProvisionalOpWithParamsRemoved(unittest.TestCase):
    """Phase 4ac (CS-54) — CS-31's dedup helper is gone.

    The Phase 4p / CS-31 ``find_provisional_op_with_params`` helper
    was the data-shape of the "no duplicate apply" gate. Phase 4ac
    drops the gate at every apply site (USER-FLAGGED Phase 4v
    friction #1), so the helper has no consumers and is removed.

    This pin traps a future regression that would re-introduce the
    helper — if the user's workflow problem (re-applying a process
    you tweaked once is blocked) recurs, it should fail in a way
    that lights this test up rather than silently re-blocking
    legitimate re-applies.
    """

    def test_helper_no_longer_exists_on_project_graph(self):
        g = ProjectGraph()
        self.assertFalse(
            hasattr(g, "find_provisional_op_with_params"),
            "Phase 4ac dropped CS-31's duplicate-apply gate — the "
            "helper must not be re-introduced without re-opening "
            "the user-flagged Phase 4v friction #1 register entry."
        )


class TestNodeGroupOps(unittest.TestCase):
    """CS-57 (Phase 4af) — user-driven NODE_GROUP container.

    Pins the create_group / dissolve_group / group_of API + the
    auto-dissolve cascade inside discard_node. The invariants
    locked here are the lock-list anchors for every downstream
    consumer (ScanTreeWidget's group row rendering, project_io's
    round-trip path, future bulk operations on grouped nodes).
    """

    def _three_uvvis(self) -> ProjectGraph:
        g = ProjectGraph()
        for nid in ("a", "b", "c"):
            g.add_node(_data(nid, ntype=NodeType.UVVIS))
        return g

    # ---- create_group --------------------------------------------

    def test_create_group_happy_path_returns_new_id(self):
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        self.assertIn(gid, g.nodes)
        group = g.get_node(gid)
        self.assertIsInstance(group, DataNode)
        self.assertEqual(group.type, NodeType.NODE_GROUP)
        self.assertEqual(group.state, NodeState.PROVISIONAL)
        self.assertEqual(group.metadata["member_ids"], ["a", "b"])
        self.assertEqual(group.arrays, {})

    def test_create_group_auto_labels_when_label_omitted(self):
        g = self._three_uvvis()
        gid1 = g.create_group(["a", "b"])
        # Add two more nodes so we can form a second group.
        g.add_node(_data("d", ntype=NodeType.UVVIS))
        g.add_node(_data("e", ntype=NodeType.UVVIS))
        gid2 = g.create_group(["d", "e"])
        self.assertEqual(g.get_node(gid1).label, "Group 1")
        self.assertEqual(g.get_node(gid2).label, "Group 2")

    def test_create_group_respects_user_label(self):
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"], label="my Ni²⁺ aquo series")
        self.assertEqual(g.get_node(gid).label, "my Ni²⁺ aquo series")

    def test_create_group_emits_node_added_event(self):
        g = self._three_uvvis()
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        gid = g.create_group(["a", "b"])
        # NODE_ADDED is the only event from create_group itself.
        added = [e for e in events if e.type == GraphEventType.NODE_ADDED]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].node_id, gid)

    def test_create_group_rejects_fewer_than_two_members(self):
        g = self._three_uvvis()
        with self.assertRaises(ValueError):
            g.create_group(["a"])
        with self.assertRaises(ValueError):
            g.create_group([])

    def test_create_group_rejects_duplicate_member_ids(self):
        g = self._three_uvvis()
        with self.assertRaises(ValueError):
            g.create_group(["a", "a"])

    def test_create_group_rejects_unknown_member_id(self):
        g = self._three_uvvis()
        with self.assertRaises(KeyError):
            g.create_group(["a", "z"])

    def test_create_group_rejects_operationnode_member(self):
        g = self._three_uvvis()
        g.add_node(_op("op_x", otype=OperationType.NORMALISE))
        with self.assertRaises(TypeError):
            g.create_group(["a", "op_x"])

    def test_create_group_rejects_node_group_member_flat_only(self):
        # Flat-only invariant: NODE_GROUP cannot be a member of
        # another NODE_GROUP.
        g = self._three_uvvis()
        inner_gid = g.create_group(["a", "b"])
        g.add_node(_data("d", ntype=NodeType.UVVIS))
        g.add_node(_data("e", ntype=NodeType.UVVIS))
        with self.assertRaises(ValueError):
            g.create_group([inner_gid, "d"])
        # And rejecting the nested group should not have mutated
        # the graph or left a partial group.
        groups = [n for n in g.nodes.values()
                  if isinstance(n, DataNode)
                  and n.type == NodeType.NODE_GROUP]
        self.assertEqual(len(groups), 1)

    def test_create_group_rejects_discarded_member(self):
        g = self._three_uvvis()
        g.discard_node("a")
        with self.assertRaises(ValueError):
            g.create_group(["a", "b"])

    def test_create_group_rejects_already_grouped_member(self):
        # Single-membership invariant.
        g = self._three_uvvis()
        g.add_node(_data("d", ntype=NodeType.UVVIS))
        g.create_group(["a", "b"])
        with self.assertRaises(ValueError):
            g.create_group(["b", "d"])

    # ---- group_of -----------------------------------------------

    def test_group_of_returns_active_group_id(self):
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        self.assertEqual(g.group_of("a"), gid)
        self.assertEqual(g.group_of("b"), gid)

    def test_group_of_returns_none_for_ungrouped_node(self):
        g = self._three_uvvis()
        g.create_group(["a", "b"])
        self.assertIsNone(g.group_of("c"))

    def test_group_of_returns_none_for_unknown_id(self):
        g = self._three_uvvis()
        self.assertIsNone(g.group_of("nope"))

    def test_group_of_ignores_discarded_groups(self):
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        g.dissolve_group(gid)
        # 'a' was a member of a now-discarded group → no active
        # group claims it.
        self.assertIsNone(g.group_of("a"))

    # ---- dissolve_group ------------------------------------------

    def test_dissolve_group_marks_group_discarded(self):
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        g.dissolve_group(gid)
        self.assertEqual(g.get_node(gid).state, NodeState.DISCARDED)

    def test_dissolve_group_leaves_members_intact(self):
        # Dissolving the group must NOT discard the members.
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        g.dissolve_group(gid)
        self.assertEqual(g.get_node("a").state, NodeState.PROVISIONAL)
        self.assertEqual(g.get_node("b").state, NodeState.PROVISIONAL)
        self.assertTrue(g.get_node("a").active)
        self.assertTrue(g.get_node("b").active)

    def test_dissolve_group_emits_node_discarded_for_group_only(self):
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.dissolve_group(gid)
        discarded = [e for e in events
                     if e.type == GraphEventType.NODE_DISCARDED]
        self.assertEqual(len(discarded), 1)
        self.assertEqual(discarded[0].node_id, gid)

    def test_dissolve_group_rejects_non_group(self):
        g = self._three_uvvis()
        with self.assertRaises(TypeError):
            g.dissolve_group("a")  # UVVIS, not NODE_GROUP

    def test_dissolve_group_rejects_operationnode(self):
        g = self._three_uvvis()
        g.add_node(_op("op_x", otype=OperationType.NORMALISE))
        with self.assertRaises(TypeError):
            g.dissolve_group("op_x")

    def test_dissolve_group_rejects_unknown_id(self):
        g = self._three_uvvis()
        with self.assertRaises(KeyError):
            g.dissolve_group("nope")

    def test_dissolve_group_rejects_already_discarded_group(self):
        # Already-DISCARDED → ValueError via discard_node.
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        g.dissolve_group(gid)
        with self.assertRaises(ValueError):
            g.dissolve_group(gid)

    # ---- auto-dissolve cascade ----------------------------------

    def test_auto_dissolve_when_group_falls_below_two_active_members(self):
        # 2-member group: discarding one member triggers cascade.
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        g.discard_node("a")
        self.assertEqual(g.get_node(gid).state, NodeState.DISCARDED)
        # 'b' is still active (cascade discards the group, not the
        # remaining member).
        self.assertEqual(g.get_node("b").state, NodeState.PROVISIONAL)

    def test_auto_dissolve_does_not_fire_above_two_active_members(self):
        # 3-member group: discarding one leaves 2 active members,
        # group survives.
        g = self._three_uvvis()
        gid = g.create_group(["a", "b", "c"])
        g.discard_node("a")
        self.assertEqual(g.get_node(gid).state, NodeState.PROVISIONAL)
        self.assertEqual(g.group_of("b"), gid)
        self.assertEqual(g.group_of("c"), gid)

    def test_auto_dissolve_fires_on_second_discard_of_3_member_group(self):
        # Sequential discards walk the group down past the
        # threshold.
        g = self._three_uvvis()
        gid = g.create_group(["a", "b", "c"])
        g.discard_node("a")
        self.assertEqual(g.get_node(gid).state, NodeState.PROVISIONAL)
        g.discard_node("b")
        self.assertEqual(g.get_node(gid).state, NodeState.DISCARDED)
        self.assertEqual(g.get_node("c").state, NodeState.PROVISIONAL)

    def test_auto_dissolve_emits_two_node_discarded_events(self):
        # Member-discard event fires first, then the cascade-
        # discard event for the group. Subscribers see both in
        # order.
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.discard_node("a")
        discarded = [e for e in events
                     if e.type == GraphEventType.NODE_DISCARDED]
        self.assertEqual(len(discarded), 2)
        self.assertEqual(discarded[0].node_id, "a")
        self.assertEqual(discarded[1].node_id, gid)

    def test_auto_dissolve_cascade_bounded_at_one_level(self):
        # Discarding a group itself does not trigger another
        # cascade (flat-only invariant: groups never nest).
        g = self._three_uvvis()
        gid = g.create_group(["a", "b"])
        events: list[GraphEvent] = []
        g.subscribe(events.append)
        g.dissolve_group(gid)
        discarded = [e for e in events
                     if e.type == GraphEventType.NODE_DISCARDED]
        # Exactly one event: the group's own.
        self.assertEqual(len(discarded), 1)
        self.assertEqual(discarded[0].node_id, gid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
