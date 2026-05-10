"""ProjectGraph — the single source of truth for all data in Ptarmigan.

The graph is a DAG of ``DataNode`` and ``OperationNode`` objects (see
``nodes.py``). Every tab, sidebar, and dialog reads from and writes to
the graph; no tab keeps its own list of scans or spectra.

Reactivity is provided by a simple observer pattern: components
``subscribe`` a callback and receive ``GraphEvent`` objects whenever
the graph changes. This eliminates the need for "Refresh" buttons
anywhere in the UI.

This module has no Tkinter or matplotlib imports. Persistence
(``save`` and ``load``) is delegated to ``project_io.py``; the
signatures live here for API completeness but currently raise
``NotImplementedError`` until the graph contract has stabilised.
"""

from __future__ import annotations

import copy
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Iterable, Union

from nodes import (
    DataNode,
    NodeState,
    NodeType,
    OperationNode,
    OperationType,
)

_log = logging.getLogger(__name__)


# =====================================================================
# Events
# =====================================================================

class GraphEventType(Enum):
    """Categories of events the graph can emit to its subscribers."""

    NODE_ADDED           = auto()
    NODE_COMMITTED       = auto()
    NODE_DISCARDED       = auto()
    NODE_LABEL_CHANGED   = auto()
    NODE_ACTIVE_CHANGED  = auto()
    NODE_STYLE_CHANGED   = auto()
    EDGE_ADDED           = auto()
    GRAPH_LOADED         = auto()
    GRAPH_CLEARED        = auto()


@dataclass(frozen=True)
class GraphEvent:
    """A single notification emitted by the graph.

    Attributes
    ----------
    type : GraphEventType
        Which event occurred.
    node_id : str | None
        Affected node id, if applicable. ``None`` for graph-level
        events (``GRAPH_LOADED``, ``GRAPH_CLEARED``).
    payload : dict
        Additional event-specific data. Conventions:

        * ``NODE_LABEL_CHANGED``: ``{"new_label": str, "old_label": str}``
        * ``NODE_ACTIVE_CHANGED``: ``{"new_value": bool, "old_value": bool}``
        * ``NODE_STYLE_CHANGED``: ``{"partial": dict, "new_style": dict}``
          where ``partial`` is the user-supplied delta and
          ``new_style`` is the full merged style dict after the update.
        * ``EDGE_ADDED``: ``{"parent_id": str, "child_id": str}``
        * other event types may carry an empty dict.
    """

    type: GraphEventType
    node_id: str | None = None
    payload: dict = field(default_factory=dict)


GraphSubscriber = Callable[[GraphEvent], None]
NodeUnion = Union[DataNode, OperationNode]


# =====================================================================
# ProjectGraph
# =====================================================================

class ProjectGraph:
    """A directed acyclic graph of DataNode and OperationNode objects.

    The graph stores nodes in a single ``{id: node}`` map, regardless
    of node kind, and a flat list of ``(parent_id, child_id)`` edges.
    Lookup helpers (parents, children, provenance chain, type-filtered
    listing) are built on top of these primitives.

    Reactivity uses a lightweight observer list: ``subscribe`` adds a
    callback, ``unsubscribe`` removes it, and any mutation method
    emits a ``GraphEvent`` to all current subscribers via
    ``_notify``. Subscribers must not mutate the graph from inside
    their callback (that re-entrancy is not supported in this design).

    Persistence (``save`` / ``load``) is delegated to ``project_io.py``
    and currently raises ``NotImplementedError``.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, NodeUnion] = {}
        self.edges: list[tuple[str, str]] = []
        self._subscribers: list[GraphSubscriber] = []
        # Index of which DataNode is "active" for a given dataset
        # lineage. Populated lazily by active_node_for; users may
        # override via set_active_node when explicit control is needed.
        self._active_overrides: dict[str, str] = {}

    # ------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------

    def add_node(self, node: NodeUnion) -> None:
        """Add a node to the graph.

        Raises ``ValueError`` if a node with the same id already exists.
        Emits ``NODE_ADDED``.
        """
        if node.id in self.nodes:
            raise ValueError(f"Node id already in graph: {node.id!r}")
        self.nodes[node.id] = node
        self._notify(GraphEvent(GraphEventType.NODE_ADDED, node.id))

    def get_node(self, node_id: str) -> NodeUnion:
        """Return the node with the given id.

        Raises ``KeyError`` if the id is unknown.
        """
        try:
            return self.nodes[node_id]
        except KeyError:
            raise KeyError(f"Unknown node id: {node_id!r}") from None

    def commit_node(self, node_id: str) -> None:
        """Promote a PROVISIONAL node to COMMITTED.

        Only PROVISIONAL nodes can be committed. Attempting to commit
        a node already in the COMMITTED or DISCARDED state raises
        ``ValueError``. Emits ``NODE_COMMITTED``.
        """
        node = self.get_node(node_id)
        if node.state != NodeState.PROVISIONAL:
            raise ValueError(
                f"Cannot commit node {node_id!r}: state is "
                f"{node.state.name}, expected PROVISIONAL"
            )
        node.state = NodeState.COMMITTED
        self._notify(GraphEvent(GraphEventType.NODE_COMMITTED, node_id))

    def discard_node(self, node_id: str) -> None:
        """Promote a PROVISIONAL node to DISCARDED.

        Only PROVISIONAL nodes can be discarded. Attempting to discard
        a node already in the COMMITTED or DISCARDED state raises
        ``ValueError`` (committed nodes are hidden via ``active=False``,
        not discarded). Emits ``NODE_DISCARDED``.
        """
        node = self.get_node(node_id)
        if node.state != NodeState.PROVISIONAL:
            raise ValueError(
                f"Cannot discard node {node_id!r}: state is "
                f"{node.state.name}, expected PROVISIONAL"
            )
        node.state = NodeState.DISCARDED
        self._notify(GraphEvent(GraphEventType.NODE_DISCARDED, node_id))

    def set_label(self, node_id: str, new_label: str) -> None:
        """Update the display label of a DataNode.

        Labels are user-editable on any state (provisional, committed,
        or discarded) — they are display-only and do not affect
        scientific data. Emits ``NODE_LABEL_CHANGED``.
        """
        node = self.get_node(node_id)
        if not isinstance(node, DataNode):
            raise TypeError(
                f"set_label only applies to DataNode, got "
                f"{type(node).__name__}"
            )
        old_label = node.label
        if old_label == new_label:
            return
        node.label = new_label
        self._notify(GraphEvent(
            GraphEventType.NODE_LABEL_CHANGED,
            node_id,
            payload={"new_label": new_label, "old_label": old_label},
        ))

    def set_active(self, node_id: str, value: bool) -> None:
        """Toggle a DataNode's ``active`` flag (visibility hint).

        ``active`` is a display-only property: it is the canonical
        signal the ScanTreeWidget uses to hide a row from the default
        view, and ``DISCARDED`` is the only state where ``active`` is
        forced. Allowed on any state — committed nodes can be hidden
        without being deleted. Emits ``NODE_ACTIVE_CHANGED``; if the
        new value equals the existing value, no event is emitted.
        """
        node = self.get_node(node_id)
        if not isinstance(node, DataNode):
            raise TypeError(
                f"set_active only applies to DataNode, got "
                f"{type(node).__name__}"
            )
        new_value = bool(value)
        old_value = node.active
        if old_value == new_value:
            return
        node.active = new_value
        self._notify(GraphEvent(
            GraphEventType.NODE_ACTIVE_CHANGED,
            node_id,
            payload={"new_value": new_value, "old_value": old_value},
        ))

    def set_style(self, node_id: str, partial: dict) -> None:
        """Merge ``partial`` into a DataNode's style dict.

        This is a *merge*, not a replacement: keys present in
        ``partial`` overwrite the existing style values; keys absent
        from ``partial`` are preserved. Style is display-only (CS-02)
        and may be edited on any state, including COMMITTED. Emits
        ``NODE_STYLE_CHANGED`` whose payload carries both the
        user-supplied ``partial`` and the resulting merged
        ``new_style`` (a shallow copy, safe for subscribers to
        retain).

        Passing an empty dict is a no-op; no event is emitted.
        """
        node = self.get_node(node_id)
        if not isinstance(node, DataNode):
            raise TypeError(
                f"set_style only applies to DataNode, got "
                f"{type(node).__name__}"
            )
        if not partial:
            return
        node.style.update(partial)
        self._notify(GraphEvent(
            GraphEventType.NODE_STYLE_CHANGED,
            node_id,
            payload={
                "partial":   dict(partial),
                "new_style": dict(node.style),
            },
        ))

    def clone_node(self, node_id: str) -> str:
        """Duplicate a DataNode, returning the new node's id.

        The clone is a fresh PROVISIONAL DataNode with a new uuid4
        id. Field handling:

        * ``type`` — same enum value as the source.
        * ``arrays`` — **shared reference** to the source dict (numpy
          arrays are not deep-copied, by design: scientific data is
          immutable on COMMITTED nodes, so sharing the array dict is
          safe and avoids needlessly duplicating large beamline
          tensors).
        * ``metadata`` — deep-copied so callers can mutate the clone's
          metadata without affecting the source.
        * ``label`` — source label with the suffix ``" (copy)"``.
        * ``style`` — deep-copied so the clone has independent visual
          state (colour swatch edits on the clone do not affect the
          source).
        * ``state`` — always ``PROVISIONAL``, regardless of the
          source's state. The caller commits or discards explicitly.
        * ``active`` — defaults to ``True``.

        No edges are wired up: the caller is responsible for calling
        ``add_edge`` for every parent that should also point at the
        clone. Emits ``NODE_ADDED`` (via ``add_node``).

        Raises ``TypeError`` if the source id refers to an
        ``OperationNode`` rather than a DataNode.
        """
        source = self.get_node(node_id)
        if not isinstance(source, DataNode):
            raise TypeError(
                f"clone_node only applies to DataNode, got "
                f"{type(source).__name__}"
            )
        new_id = uuid.uuid4().hex
        clone = DataNode(
            id=new_id,
            type=source.type,
            arrays=source.arrays,                  # shared reference
            metadata=copy.deepcopy(source.metadata),
            label=f"{source.label} (copy)",
            state=NodeState.PROVISIONAL,
            active=True,
            style=copy.deepcopy(source.style),
        )
        self.add_node(clone)
        return new_id

    # ------------------------------------------------------------
    # Edge management
    # ------------------------------------------------------------

    def add_edge(self, parent_id: str, child_id: str) -> None:
        """Add a directed edge from parent to child.

        Both nodes must already be in the graph. Raises ``ValueError``
        if the edge would create a cycle, if it duplicates an existing
        edge, or if either node is missing. Emits ``EDGE_ADDED``.
        """
        if parent_id not in self.nodes:
            raise KeyError(f"Unknown parent id: {parent_id!r}")
        if child_id not in self.nodes:
            raise KeyError(f"Unknown child id: {child_id!r}")
        if parent_id == child_id:
            raise ValueError(
                f"Self-loops are not allowed: {parent_id!r} → itself"
            )
        edge = (parent_id, child_id)
        if edge in self.edges:
            raise ValueError(
                f"Edge already present: {parent_id!r} → {child_id!r}"
            )
        # Cycle check: a cycle would exist iff parent is reachable
        # from child along existing edges.
        if self._reachable(child_id, parent_id):
            raise ValueError(
                f"Adding edge {parent_id!r} → {child_id!r} would "
                f"create a cycle"
            )
        self.edges.append(edge)
        self._notify(GraphEvent(
            GraphEventType.EDGE_ADDED,
            payload={"parent_id": parent_id, "child_id": child_id},
        ))

    def parents_of(self, node_id: str) -> list[str]:
        """Return ids of all direct parents of the given node."""
        if node_id not in self.nodes:
            raise KeyError(f"Unknown node id: {node_id!r}")
        return [p for (p, c) in self.edges if c == node_id]

    def children_of(self, node_id: str) -> list[str]:
        """Return ids of all direct children of the given node."""
        if node_id not in self.nodes:
            raise KeyError(f"Unknown node id: {node_id!r}")
        return [c for (p, c) in self.edges if p == node_id]

    # ------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------

    def nodes_of_type(
        self,
        node_type: NodeType,
        state: NodeState | None = NodeState.COMMITTED,
    ) -> list[DataNode]:
        """Return all DataNodes of a given type.

        Parameters
        ----------
        node_type : NodeType
            Filter to this node type.
        state : NodeState | None
            If set (default ``COMMITTED``), only nodes in that state
            are returned. Pass ``None`` to return all nodes regardless
            of state.
        """
        result: list[DataNode] = []
        for node in self.nodes.values():
            if not isinstance(node, DataNode):
                continue
            if node.type != node_type:
                continue
            if state is not None and node.state != state:
                continue
            result.append(node)
        return result

    def active_node_for(self, dataset_id: str) -> DataNode | None:
        """Return the currently "active" DataNode for a dataset lineage.

        A "dataset" here means the chain of DataNodes derived from a
        single original RAW_FILE node. ``dataset_id`` is the id of any
        node in that chain (typically the RAW_FILE id, but any node
        works); this method walks the descendants and returns the
        latest non-discarded node. If a manual override has been set
        via ``set_active_node`` it is honoured.

        Returns ``None`` if the dataset_id is unknown or every node
        in its lineage is discarded.
        """
        if dataset_id not in self.nodes:
            return None

        # Identify the root of the lineage: walk parents until none.
        root = self._lineage_root(dataset_id)

        # Manual override wins, if it points to a node still in the
        # lineage and not discarded.
        override_id = self._active_overrides.get(root)
        if override_id and override_id in self.nodes:
            override = self.nodes[override_id]
            if (isinstance(override, DataNode)
                    and override.state != NodeState.DISCARDED):
                return override

        # Otherwise: BFS from root, prefer the deepest (most-derived)
        # non-discarded DataNode.
        best: DataNode | None = None
        best_depth = -1
        queue: deque[tuple[str, int]] = deque([(root, 0)])
        seen: set[str] = set()
        while queue:
            nid, depth = queue.popleft()
            if nid in seen:
                continue
            seen.add(nid)
            node = self.nodes.get(nid)
            if isinstance(node, DataNode) and node.state != NodeState.DISCARDED:
                if depth > best_depth:
                    best = node
                    best_depth = depth
            for child in self.children_of(nid):
                queue.append((child, depth + 1))
        return best

    def set_active_node(self, dataset_id: str, node_id: str) -> None:
        """Override the active node for a dataset lineage.

        ``dataset_id`` may be any node in the lineage; the override is
        stored against the lineage root.
        """
        if dataset_id not in self.nodes:
            raise KeyError(f"Unknown dataset id: {dataset_id!r}")
        if node_id not in self.nodes:
            raise KeyError(f"Unknown node id: {node_id!r}")
        root = self._lineage_root(dataset_id)
        self._active_overrides[root] = node_id

    def provenance_chain(self, node_id: str) -> list[NodeUnion]:
        """Return the full provenance chain ending at ``node_id``.

        The chain is ordered from the root (RAW_FILE or earliest
        ancestor) through each intermediate operation/data node down
        to ``node_id`` itself. Order is a topological sort restricted
        to ancestors of ``node_id``: every parent appears before its
        child in the list.

        For a tree with a single root the result is the unique path
        from root to node. For DAGs with multiple ancestral paths
        (e.g. an AVERAGE that consumes two scans), every ancestor
        appears exactly once and the order is consistent with all
        edges.
        """
        if node_id not in self.nodes:
            raise KeyError(f"Unknown node id: {node_id!r}")

        # Collect all ancestors (BFS upwards).
        ancestors: set[str] = {node_id}
        queue: deque[str] = deque([node_id])
        while queue:
            nid = queue.popleft()
            for parent in self.parents_of(nid):
                if parent not in ancestors:
                    ancestors.add(parent)
                    queue.append(parent)

        # Topological sort, restricted to the ancestor set.
        # Kahn's algorithm: repeatedly emit nodes whose remaining
        # in-degree (from within the ancestor set) is zero.
        in_degree: dict[str, int] = {a: 0 for a in ancestors}
        for parent, child in self.edges:
            if parent in ancestors and child in ancestors:
                in_degree[child] += 1
        ready: deque[str] = deque(
            sorted(a for a, d in in_degree.items() if d == 0)
        )
        order: list[str] = []
        while ready:
            nid = ready.popleft()
            order.append(nid)
            for child in sorted(self.children_of(nid)):
                if child in ancestors:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        ready.append(child)

        return [self.nodes[nid] for nid in order]

    # ------------------------------------------------------------
    # Persistence (delegated to project_io.py)
    # ------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Write the graph to a ``.ptproj/`` directory.

        Full implementation lives in ``project_io.py`` — this method
        will become a thin pass-through once that is wired up. Until
        then it raises ``NotImplementedError``.
        """
        raise NotImplementedError(
            "ProjectGraph.save is implemented in a later phase; "
            "use project_io functions directly for now."
        )

    def load(self, path: Path) -> None:
        """Replace the graph with one read from a ``.ptproj/`` directory.

        Full implementation lives in ``project_io.py`` — this method
        will become a thin pass-through once that is wired up. Until
        then it raises ``NotImplementedError``. On success it must
        emit ``GRAPH_LOADED``.
        """
        raise NotImplementedError(
            "ProjectGraph.load is implemented in a later phase; "
            "use project_io functions directly for now."
        )

    def export_log(self, path: Path) -> None:
        """Write the committed-operations audit trail to ``log.jsonl``.

        Full implementation lives in ``project_io.py``.
        """
        raise NotImplementedError(
            "ProjectGraph.export_log is implemented in a later phase."
        )

    # ------------------------------------------------------------
    # Observer pattern
    # ------------------------------------------------------------

    def subscribe(self, callback: GraphSubscriber) -> None:
        """Register a callback to receive ``GraphEvent`` notifications.

        Duplicate subscriptions are silently ignored.
        """
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: GraphSubscriber) -> None:
        """Remove a previously-registered callback.

        Unsubscribing a callback that was never registered is a no-op.
        """
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    def _notify(self, event: GraphEvent) -> None:
        """Emit an event to all current subscribers.

        Subscribers are notified in registration order. A subscriber
        that raises does NOT prevent later subscribers from receiving
        the event: the exception is logged at WARNING level via the
        standard ``logging`` module and dispatch continues. This
        isolates UI components from each other — a buggy sidebar
        cannot break the log panel by raising on a NODE_ADDED.
        """
        for cb in list(self._subscribers):
            try:
                cb(event)
            except Exception:
                _log.warning(
                    "graph subscriber %r raised on event %s "
                    "(node_id=%r); continuing dispatch",
                    cb, event.type.name, event.node_id,
                    exc_info=True,
                )

    # ------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------

    def _reachable(self, src: str, dst: str) -> bool:
        """Return True if ``dst`` is reachable from ``src`` along edges."""
        if src == dst:
            return True
        seen: set[str] = {src}
        stack: list[str] = [src]
        while stack:
            cur = stack.pop()
            for child in self.children_of(cur):
                if child == dst:
                    return True
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return False

    def _lineage_root(self, node_id: str) -> str:
        """Walk parents until reaching a node with no parents.

        For DAGs with multiple roots reachable from ``node_id`` (e.g.
        an AVERAGE node), this returns one of them deterministically
        (the lexicographically smallest id), so that lookups against
        ``_active_overrides`` are stable.
        """
        cur = node_id
        while True:
            parents = self.parents_of(cur)
            if not parents:
                return cur
            cur = sorted(parents)[0]
