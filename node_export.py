"""Single-node export writer (Phase 4f, CS-17).

Spec
----
The authoritative spec is ``COMPONENTS.md`` (CS-17). This module is
the file-writing half of the export feature; the header is built by
``provenance_export.py``. The ``ScanTreeWidget`` ``Export…`` row
gesture and the host's ``filedialog.asksaveasfilename`` flow live
elsewhere — this module owns only the ``(graph, node_id, path)``
→ on-disk file mapping.

Format dispatch
---------------
The output format is keyed off the path extension:

* ``.csv`` — provenance header lines first (``# `` prefixed), then
  one column-header row, then comma-separated numeric rows.
* ``.txt`` — provenance header lines first, then a tab-separated
  column-header row, then tab-separated numeric rows.

Both formats round-trip the canonical ``arrays`` for the node type:

* ``UVVIS`` / ``BASELINE`` / ``NORMALISED`` → ``wavelength_nm`` and
  ``absorbance``.

Other node types raise ``ValueError`` — XANES (``energy``, ``mu``)
and EXAFS (``k``, ``chi``) shapes land in Phase 5 / 6.

Provisional nodes are not exportable; the gesture is hidden /
disabled at the row level (per the Phase 4f lock decision). This
module does not enforce state — the caller can pass a provisional id
and the file will be written. The widget is the gatekeeper.
"""

from __future__ import annotations

import os
from typing import Sequence

import numpy as np

from graph import ProjectGraph
from nodes import DataNode, NodeType
from provenance_export import build_provenance_header


__all__ = ["export_node_to_file", "EXPORTABLE_NODE_TYPES"]


# Node types that today carry a ``wavelength_nm`` + ``absorbance``
# array pair. Phase 5 / 6 will widen this to XANES / EXAFS shapes.
EXPORTABLE_NODE_TYPES: frozenset[NodeType] = frozenset({
    NodeType.UVVIS,
    NodeType.BASELINE,
    NodeType.NORMALISED,
})


def _format_for_path(path: str) -> str:
    """Map a file extension to ``"csv"`` or ``"txt"``.

    Case-insensitive. Anything else raises ``ValueError`` so a typo
    like ``.cvs`` fails loudly rather than producing a broken file.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return "csv"
    if ext == ".txt":
        return "txt"
    raise ValueError(
        f"Unsupported export extension: {ext!r}; "
        f"expected .csv or .txt"
    )


def _resolve_columns(
    node: DataNode,
) -> tuple[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
    """Return ``((col_a, col_b), (data_a, data_b))`` for an exportable node.

    Phase 4f only handles spectrum-shaped nodes (UVVIS / BASELINE /
    NORMALISED). The two columns are always
    ``(wavelength_nm, absorbance)``; this helper fans out so future
    techniques (XANES energy/mu, EXAFS k/chi) extend by branching
    here rather than rewriting the writer.
    """
    if node.type not in EXPORTABLE_NODE_TYPES:
        raise ValueError(
            f"Cannot export node of type {node.type.name}; "
            f"only UVVIS / BASELINE / NORMALISED are supported in "
            f"Phase 4f"
        )
    try:
        wl = np.asarray(node.arrays["wavelength_nm"], dtype=float)
        ab = np.asarray(node.arrays["absorbance"], dtype=float)
    except KeyError as exc:  # pragma: no cover — defensive
        raise ValueError(
            f"Node {node.id!r} of type {node.type.name} is missing "
            f"required array {exc.args[0]!r}"
        ) from None
    return ("wavelength_nm", "absorbance"), (wl, ab)


def _write_rows(
    fh, header_lines: Sequence[str],
    columns: tuple[str, str],
    data: tuple[np.ndarray, np.ndarray], delimiter: str,
) -> None:
    """Write the header + column-header + data block to ``fh``.

    The header lines are written verbatim with a trailing newline; the
    column-header and each data row use ``delimiter``. Numeric values
    are written via ``repr`` so they round-trip without precision loss
    (``str(float)`` truncates on some Python versions).
    """
    for line in header_lines:
        fh.write(line)
        fh.write("\n")
    fh.write(delimiter.join(columns))
    fh.write("\n")
    a, b = data
    if a.shape != b.shape:
        raise ValueError(
            f"Column length mismatch: {a.shape} vs {b.shape}"
        )
    for a_val, b_val in zip(a, b):
        fh.write(f"{repr(float(a_val))}{delimiter}{repr(float(b_val))}")
        fh.write("\n")


def export_node_to_file(
    graph: ProjectGraph, node_id: str, path: str,
) -> None:
    """Write one committed node to ``path`` as ``.csv`` or ``.txt``.

    The file always begins with the ``# ``-prefixed provenance header
    from ``provenance_export.build_provenance_header``; CSV and TXT
    differ only in the data delimiter (``,`` vs ``\\t``). The header
    lines are identical between formats so a downstream parser can
    detect them by the leading ``# `` regardless of extension.

    Raises
    ------
    KeyError
        ``node_id`` is not in ``graph``.
    ValueError
        ``path`` extension is not ``.csv`` / ``.txt``, or the node
        type is not yet exportable.
    """
    fmt = _format_for_path(path)
    node = graph.get_node(node_id)
    if not isinstance(node, DataNode):
        raise ValueError(
            f"Cannot export non-DataNode {node_id!r}"
        )
    columns, data = _resolve_columns(node)
    header_lines = build_provenance_header(graph, node_id)
    delimiter = "," if fmt == "csv" else "\t"

    with open(path, "w", encoding="utf-8", newline="") as fh:
        _write_rows(fh, header_lines, columns, data, delimiter)
