"""Pure header-builder for single-node export (Phase 4f, CS-17).

Spec
----
The authoritative spec is ``COMPONENTS.md`` (CS-17). This module owns
the textual ``# ``-prefixed provenance header that prefixes every
exported ``.csv`` / ``.txt`` file. The shape mirrors CS-13's project
serialisation contract so a future round-trip / re-import path stays
sane.

Behavioural model
-----------------
``build_provenance_header(graph, node_id)`` walks
``graph.provenance_chain(node_id)`` (topologically sorted, root first,
node last) and emits one line per ancestor. Each line is a single
``# ``-prefixed string with no trailing newline — the writer joins
with the platform's preferred separator.

The top of the header carries four envelope lines describing the
export itself (Ptarmigan version, UTC timestamp, full node id, node
label). Each ancestor is rendered as either:

* ``# ancestor[<idx>] type=<NodeType.name> id=<short_hex>
  label=<label>`` — for ``DataNode``, or
* ``# ancestor[<idx>] op=<OperationType.name> engine=<engine>
  engine_version=<engine_version> params=<json>`` — for
  ``OperationNode``.

Index is 0-based; ``ancestor[0]`` is the root of the provenance chain
and the highest-index ancestor is ``node_id`` itself. The params dict
of an OperationNode is flattened to a single ``json.dumps`` line with
``sort_keys=True`` so two exports of the same operation diff cleanly.

The module is pure: no Tk, no matplotlib, no file I/O, no side
effects. Test coverage in ``test_provenance_export.py``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from graph import ProjectGraph
from nodes import DataNode, OperationNode
from version import __version__ as PTARMIGAN_VERSION


__all__ = ["build_provenance_header"]


_SHORT_HEX_LEN = 8


def _short(node_id: str) -> str:
    """Return the short-hex prefix used in ancestor lines."""
    return node_id[:_SHORT_HEX_LEN]


def _format_ancestor(index: int, ancestor) -> str:
    """Render one ancestor as a ``# ``-prefixed line.

    DataNodes carry ``type``, ``id`` (short), and ``label``;
    OperationNodes carry ``op``, ``engine``, ``engine_version``, and a
    JSON-serialised ``params`` dict. The two prefixes are deliberately
    distinct (``type=`` vs. ``op=``) so a downstream parser can tell
    them apart without re-deriving the chain.
    """
    if isinstance(ancestor, DataNode):
        return (
            f"# ancestor[{index}] type={ancestor.type.name} "
            f"id={_short(ancestor.id)} label={ancestor.label}"
        )
    if isinstance(ancestor, OperationNode):
        # ``default=str`` covers numpy scalars or any non-JSON
        # primitive that slipped into params; keeping the line
        # serialisable is more important than a faithful round-trip
        # at this layer (the provenance chain is the audit-trail
        # source of truth, not the header).
        params_json = json.dumps(
            ancestor.params, sort_keys=True, default=str,
        )
        return (
            f"# ancestor[{index}] op={ancestor.type.name} "
            f"engine={ancestor.engine} "
            f"engine_version={ancestor.engine_version} "
            f"params={params_json}"
        )
    raise TypeError(
        f"Unknown ancestor type: {type(ancestor).__name__}"
    )


def build_provenance_header(
    graph: ProjectGraph, node_id: str,
) -> list[str]:
    """Return the ``# ``-prefixed header lines for an exported node.

    The list is ordered top-down: envelope first (version, timestamp,
    node id, node label), then ancestors in topological order with
    the leaf last. No newlines on any line — the caller joins.

    Raises
    ------
    KeyError
        If ``node_id`` is not in ``graph``. ``provenance_chain``
        raises this for missing ids; we let it propagate so the
        caller can decide how to surface a stale id.
    """
    chain = graph.provenance_chain(node_id)
    leaf = graph.get_node(node_id)

    timestamp = datetime.now(timezone.utc).isoformat()

    leaf_label = leaf.label if isinstance(leaf, DataNode) else node_id

    lines: list[str] = [
        f"# ptarmigan_version={PTARMIGAN_VERSION}",
        f"# exported_at={timestamp}",
        f"# node_id={node_id}",
        f"# node_label={leaf_label}",
    ]
    for index, ancestor in enumerate(chain):
        lines.append(_format_ancestor(index, ancestor))
    return lines
