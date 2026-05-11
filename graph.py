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

    NODE_ADDED                  = auto()
    NODE_COMMITTED              = auto()
    NODE_DISCARDED              = auto()
    NODE_LABEL_CHANGED          = auto()
    NODE_ACTIVE_CHANGED         = auto()
    NODE_STYLE_CHANGED          = auto()
    NODE_GROUP_MEMBERS_CHANGED  = auto()
    EDGE_ADDED                  = auto()
    GRAPH_LOADED                = auto()
    GRAPH_CLEARED               = auto()


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
        * ``NODE_GROUP_MEMBERS_CHANGED``: ``{"group_id": str,
          "added": list[str], "removed": list[str]}``. Emitted when
          ``extend_group`` or ``remove_from_group`` mutates a
          NODE_GROUP's ``metadata["member_ids"]`` while the group
          itself survives. When ``remove_from_group`` triggers the
          auto-dissolve cascade (active member count < 2), the event
          is *not* emitted — the cascading ``NODE_DISCARDED`` is the
          authoritative signal in that case. ``node_id`` is the
          group id (same as ``group_id`` in payload, repeated there
          so subscribers walking the payload don't need to consult
          the envelope).
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

        CS-57 (Phase 4af): when the discarded node was a member of an
        active NODE_GROUP and the group now has fewer than two active
        (i.e. non-DISCARDED) members, the group is auto-dissolved by
        a recursive ``discard_node`` call. This cascades at most one
        level because the flat-only invariant (``create_group``
        rejects nested groups) means a NODE_GROUP is never itself a
        member of another NODE_GROUP. The cascade emits a second
        NODE_DISCARDED event for the group; subscribers see both
        events in order (member first, then group).
        """
        node = self.get_node(node_id)
        if node.state != NodeState.PROVISIONAL:
            raise ValueError(
                f"Cannot discard node {node_id!r}: state is "
                f"{node.state.name}, expected PROVISIONAL"
            )
        node.state = NodeState.DISCARDED
        self._notify(GraphEvent(GraphEventType.NODE_DISCARDED, node_id))

        # CS-57: auto-dissolve cascade. Skip when the just-discarded
        # node is itself a NODE_GROUP — by the flat-only invariant a
        # group is never a member of another group, so this would be
        # a wasted ``group_of`` walk.
        if not (isinstance(node, DataNode)
                and node.type == NodeType.NODE_GROUP):
            group_id = self.group_of(node_id)
            if group_id is not None:
                group = self.nodes[group_id]
                assert isinstance(group, DataNode)
                member_ids = group.metadata.get("member_ids", ())
                active_count = sum(
                    1 for mid in member_ids
                    if mid in self.nodes
                    and isinstance(self.nodes[mid], DataNode)
                    and self.nodes[mid].state != NodeState.DISCARDED
                )
                if active_count < 2:
                    self.discard_node(group_id)

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
    # Node groups (CS-57, Phase 4af)
    # ------------------------------------------------------------

    def create_group(
        self,
        member_ids: list[str],
        label: str | None = None,
    ) -> str:
        """Create a NODE_GROUP DataNode aggregating ``member_ids``.

        CS-57 (Phase 4af) part (c) of the Phase 4v friction #1
        architecture. A NODE_GROUP is a view-layer aggregation: it
        carries no scientific arrays and does not reparent its
        members. ``ScanTreeWidget`` reads ``metadata["member_ids"]``
        to render member rows under a chevron-toggleable group row.

        Validation rules (all raise on violation, no node is created):

        * ``member_ids`` must contain at least two ids.
        * Ids must be unique (no duplicate within ``member_ids``).
        * Every id must exist in the graph (``KeyError`` otherwise).
        * Every member must be a DataNode (``TypeError`` if an
          OperationNode id is passed).
        * No member may itself be a NODE_GROUP — the flat-only
          invariant (``ValueError``). Relaxing this would require
          updating ``group_of`` and the scan tree to walk a tree.
        * No member may be DISCARDED — would render under the group
          but immediately be invisible (``ValueError``).
        * No member may already belong to another active NODE_GROUP
          (``ValueError`` — the single-membership invariant).

        ``label`` defaults to ``f"Group {N}"`` where N is one past the
        count of existing NODE_GROUPs (active or discarded). The
        caller may pass a user-chosen label.

        Returns the new group's id. Emits ``NODE_ADDED`` via
        ``add_node``. The group is created in state ``PROVISIONAL``;
        groups have no scientific value to commit and dissolve via
        ``dissolve_group`` (which routes through ``discard_node``).
        """
        if len(member_ids) < 2:
            raise ValueError(
                f"NODE_GROUP requires at least 2 members, got "
                f"{len(member_ids)}"
            )
        if len(set(member_ids)) != len(member_ids):
            raise ValueError(
                f"NODE_GROUP member_ids must be unique: {member_ids!r}"
            )
        for mid in member_ids:
            if mid not in self.nodes:
                raise KeyError(f"Unknown member id: {mid!r}")
            member = self.nodes[mid]
            if not isinstance(member, DataNode):
                raise TypeError(
                    f"NODE_GROUP members must be DataNode, {mid!r} is "
                    f"{type(member).__name__}"
                )
            if member.type == NodeType.NODE_GROUP:
                raise ValueError(
                    f"Nested NODE_GROUPs are not supported: {mid!r} "
                    f"is itself a NODE_GROUP"
                )
            if member.state == NodeState.DISCARDED:
                raise ValueError(
                    f"NODE_GROUP members must not be DISCARDED: {mid!r}"
                )
            existing_group = self.group_of(mid)
            if existing_group is not None:
                raise ValueError(
                    f"Node {mid!r} already belongs to group "
                    f"{existing_group!r}"
                )

        if label is None:
            existing_total = sum(
                1 for n in self.nodes.values()
                if isinstance(n, DataNode) and n.type == NodeType.NODE_GROUP
            )
            label = f"Group {existing_total + 1}"

        new_id = uuid.uuid4().hex
        group = DataNode(
            id=new_id,
            type=NodeType.NODE_GROUP,
            arrays={},
            metadata={"member_ids": list(member_ids)},
            label=label,
            state=NodeState.PROVISIONAL,
            active=True,
            style={},
        )
        self.add_node(group)
        return new_id

    def dissolve_group(self, group_id: str) -> None:
        """Discard a NODE_GROUP, unbundling its members.

        Dissolving a group does NOT discard its members — members
        return to top-level scan-tree rendering with their state and
        edges untouched. The group itself transitions to DISCARDED
        via ``discard_node``, emitting NODE_DISCARDED.

        Raises ``KeyError`` if the id is unknown, ``TypeError`` if the
        id refers to a non-NODE_GROUP node, and ``ValueError`` (via
        ``discard_node``) if the group is not PROVISIONAL.
        """
        node = self.get_node(group_id)
        if not isinstance(node, DataNode) or node.type != NodeType.NODE_GROUP:
            raise TypeError(
                f"dissolve_group expects a NODE_GROUP DataNode, got "
                f"{type(node).__name__}"
                + (f" (type={node.type.name})" if isinstance(node, DataNode)
                   else "")
            )
        self.discard_node(group_id)

    def group_of(self, node_id: str) -> str | None:
        """Return the id of the active NODE_GROUP containing ``node_id``.

        Walks the graph looking for an active (non-DISCARDED)
        NODE_GROUP whose ``metadata["member_ids"]`` includes the
        given id. Returns ``None`` if no such group exists. Used by
        ``create_group`` to enforce single-membership, by
        ``discard_node`` to drive the auto-dissolve cascade, and by
        ``ScanTreeWidget._candidate_nodes`` to exclude grouped
        members from top-level rendering.

        Returns ``None`` for unknown ids; never raises. By the
        single-membership invariant a node belongs to at most one
        active group, so the first match is canonical.
        """
        if node_id not in self.nodes:
            return None
        for node in self.nodes.values():
            if not isinstance(node, DataNode):
                continue
            if node.type != NodeType.NODE_GROUP:
                continue
            if node.state == NodeState.DISCARDED:
                continue
            if node_id in node.metadata.get("member_ids", ()):
                return node.id
        return None

    def extend_group(
        self,
        group_id: str,
        member_ids: list[str],
    ) -> None:
        """Append ``member_ids`` to an existing NODE_GROUP's roster.

        CS-58 (Phase 4ag). The natural follow-up to CS-57's
        ``create_group``: once a group exists, the user can keep
        adding nodes to it without dissolving and re-creating. The
        method mutates the group's ``metadata["member_ids"]`` list
        in place (per the CS-57 lock relaxation: the list *shape*
        stays canonical, only mutability grows).

        Validation mirrors ``create_group`` so the gesture has the
        same invariants regardless of which entry point the user
        reached:

        * ``group_id`` must exist and refer to an active (non-DISCARDED)
          NODE_GROUP DataNode.
        * ``member_ids`` must contain at least one id.
        * Ids must be unique within the call.
        * None of the ids may already be in the group's roster (no
          accidental duplicates from a re-issued gesture).
        * Every id must exist in the graph.
        * Every member must be a DataNode (not OperationNode).
        * No member may itself be a NODE_GROUP — flat-only invariant.
        * No member may be DISCARDED.
        * No member may already belong to another active NODE_GROUP
          (single-membership invariant).

        Emits ``NODE_GROUP_MEMBERS_CHANGED`` with payload carrying
        the group id and the list of added ids. Does NOT emit
        ``NODE_LABEL_CHANGED``: the group's *backing* label is
        unchanged; the displayed "(N members)" suffix is a view-layer
        concern that the scan tree re-derives on rebuild.
        """
        group = self.get_node(group_id)
        if (not isinstance(group, DataNode)
                or group.type != NodeType.NODE_GROUP):
            raise TypeError(
                f"extend_group expects a NODE_GROUP DataNode, got "
                f"{type(group).__name__}"
                + (f" (type={group.type.name})" if isinstance(group, DataNode)
                   else "")
            )
        if group.state == NodeState.DISCARDED:
            raise ValueError(
                f"Cannot extend a DISCARDED group: {group_id!r}"
            )
        if len(member_ids) < 1:
            raise ValueError(
                f"extend_group requires at least 1 new member, got 0"
            )
        if len(set(member_ids)) != len(member_ids):
            raise ValueError(
                f"extend_group member_ids must be unique: {member_ids!r}"
            )
        existing_roster = group.metadata.get("member_ids", [])
        for mid in member_ids:
            if mid in existing_roster:
                raise ValueError(
                    f"Node {mid!r} is already a member of group "
                    f"{group_id!r}"
                )
            if mid not in self.nodes:
                raise KeyError(f"Unknown member id: {mid!r}")
            member = self.nodes[mid]
            if not isinstance(member, DataNode):
                raise TypeError(
                    f"NODE_GROUP members must be DataNode, {mid!r} is "
                    f"{type(member).__name__}"
                )
            if member.type == NodeType.NODE_GROUP:
                raise ValueError(
                    f"Nested NODE_GROUPs are not supported: {mid!r} "
                    f"is itself a NODE_GROUP"
                )
            if member.state == NodeState.DISCARDED:
                raise ValueError(
                    f"NODE_GROUP members must not be DISCARDED: {mid!r}"
                )
            existing_group = self.group_of(mid)
            if existing_group is not None:
                raise ValueError(
                    f"Node {mid!r} already belongs to group "
                    f"{existing_group!r}"
                )

        existing_roster.extend(member_ids)
        self._notify(GraphEvent(
            GraphEventType.NODE_GROUP_MEMBERS_CHANGED,
            group_id,
            payload={
                "group_id": group_id,
                "added":    list(member_ids),
                "removed":  [],
            },
        ))

    def remove_from_group(self, node_id: str) -> None:
        """Detach ``node_id`` from whichever NODE_GROUP currently owns it.

        CS-58 (Phase 4ag). The per-row counterpart to ``extend_group``:
        the user can pull a single node out of its group without
        dissolving the whole group. The removed node returns to
        top-level scan-tree rendering with its state, edges, label,
        and style untouched.

        Raises ``ValueError`` if ``node_id`` is not in any active group.

        Auto-dissolve: if removing the node leaves the group with
        fewer than two active (non-DISCARDED) members, the group is
        dissolved by routing through ``discard_node`` — same
        threshold as CS-57's discard cascade. In that branch the
        event stream is ``NODE_DISCARDED`` (on the group) only —
        ``NODE_GROUP_MEMBERS_CHANGED`` is suppressed because the
        group is gone by the time subscribers run.

        When the group survives, emits
        ``NODE_GROUP_MEMBERS_CHANGED`` with the removed id in the
        payload's ``removed`` list.
        """
        group_id = self.group_of(node_id)
        if group_id is None:
            raise ValueError(
                f"Node {node_id!r} is not in any active group"
            )
        group = self.nodes[group_id]
        assert isinstance(group, DataNode)
        member_ids = group.metadata.get("member_ids", [])
        member_ids.remove(node_id)
        active_count = sum(
            1 for mid in member_ids
            if mid in self.nodes
            and isinstance(self.nodes[mid], DataNode)
            and self.nodes[mid].state != NodeState.DISCARDED
        )
        if active_count < 2:
            # Auto-dissolve. discard_node emits NODE_DISCARDED on the
            # group; we suppress NODE_GROUP_MEMBERS_CHANGED because
            # the group no longer exists for subscribers to refresh.
            self.discard_node(group_id)
            return
        self._notify(GraphEvent(
            GraphEventType.NODE_GROUP_MEMBERS_CHANGED,
            group_id,
            payload={
                "group_id": group_id,
                "added":    [],
                "removed":  [node_id],
            },
        ))

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
