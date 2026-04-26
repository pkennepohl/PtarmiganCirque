"""Core node dataclasses for the Ptarmigan provenance DAG.

This module defines the immutable building blocks of the project graph:
``DataNode`` (a dataset at one point in its processing history) and
``OperationNode`` (the processing step that produced one or more
DataNodes from one or more parents). Together with ``ProjectGraph``
(see ``graph.py``) these replace all ad-hoc tuple/dict structures
that previous versions of Ptarmigan used to track scans and overlays.

The module is pure Python; it has no UI or Tkinter dependencies and
no knowledge of the on-disk project format. See ``project_io.py``
for serialisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


# =====================================================================
# Enums
# =====================================================================

class NodeType(Enum):
    """The kind of dataset a ``DataNode`` represents.

    Variants are deliberately coarse — they describe the scientific role
    of the data, not the engine or operation that produced it. The list
    is extensible: new variants can be appended as new operations are
    implemented. Persistence uses the variant *name* (a string) so
    appending new members at the end never breaks existing project files,
    but renaming or removing existing members will.
    """

    RAW_FILE    = auto()  # original loaded file; never derived from another node
    XANES       = auto()  # processed XANES (normalised mu(E))
    EXAFS       = auto()  # processed EXAFS (chi(k), |chi(R)|)
    UVVIS       = auto()  # UV/Vis/NIR spectrum
    DEGLITCHED  = auto()  # scan with spikes removed
    NORMALISED  = auto()  # normalised result (XANES or UV/Vis)
    SMOOTHED    = auto()  # smoothed result
    SHIFTED     = auto()  # energy-shifted result
    BASELINE    = auto()  # baseline-corrected UV/Vis
    AVERAGED    = auto()  # average of multiple input nodes
    DIFFERENCE  = auto()  # difference of two input nodes
    TDDFT       = auto()  # TD-DFT calculated spectrum (from ORCA)
    FEFF_PATHS  = auto()  # FEFF simulation result
    BXAS_RESULT = auto()  # bXAS unified fit result
    # Add further types as new operations are implemented.


class NodeState(Enum):
    """Lifecycle state of any node in the graph.

    Every node enters the graph as ``PROVISIONAL``. The user explicitly
    promotes it to ``COMMITTED`` (locked into the scientific record,
    written to ``log.jsonl``) or ``DISCARDED`` (abandoned, hidden from
    default views). State transitions are one-way: a committed node
    can never become provisional again, and a discarded node is never
    revived.
    """

    PROVISIONAL = auto()  # being explored; not yet locked
    COMMITTED   = auto()  # permanent; part of the scientific record
    DISCARDED   = auto()  # explicitly abandoned


class OperationType(Enum):
    """The kind of processing step an ``OperationNode`` represents.

    As with ``NodeType``, this enum is extensible: append new variants
    as new operations are implemented. Persistence uses the variant
    name as a string.
    """

    LOAD         = auto()  # raw file load (always produces COMMITTED RAW_FILE node)
    DEGLITCH     = auto()  # spike removal
    NORMALISE    = auto()  # XANES or UV/Vis normalisation
    SMOOTH       = auto()  # Savitzky-Golay or moving average
    SHIFT_ENERGY = auto()  # energy axis offset
    BASELINE     = auto()  # baseline subtraction (UV/Vis)
    AVERAGE      = auto()  # multi-input average
    DIFFERENCE   = auto()  # two-input difference
    FEFF_RUN     = auto()  # FEFF simulation execution
    BXAS_FIT     = auto()  # bXAS unified background + spectral fit
    # Add further types as new operations are implemented.


# =====================================================================
# DataNode
# =====================================================================

@dataclass
class DataNode:
    """A dataset at one point in its processing history.

    A ``DataNode`` stores results, not procedures: the outcome of an
    operation, frozen as numpy arrays and a metadata dict. The graph
    edges (managed by ``ProjectGraph``) describe how a node was
    derived from its parents; this object does not know about its
    own parents or children.

    Once a node has state ``COMMITTED`` its ``arrays`` and
    ``metadata`` must never be mutated. This rule has no exceptions
    and is the foundation of the provenance guarantee.

    Attributes
    ----------
    id : str
        Unique, permanent identifier (typically a uuid4 hex string).
        Never reused — even discarded nodes keep their id.
    type : NodeType
        Coarse scientific role of the data; see ``NodeType``.
    arrays : dict[str, Any]
        Numerical payload. Keys are short strings (e.g. ``"energy"``,
        ``"mu"``, ``"wavelength_nm"``, ``"absorbance"``); values are
        ``numpy.ndarray`` instances. Conventions per node type are
        documented in ``COMPONENTS.md`` (CS-02).
    metadata : dict[str, Any]
        Technique-specific parameters and provenance information
        (E0, edge step, fit quality, source filename, etc.). Must be
        JSON-serialisable.
    label : str
        User-editable display name. Free-form. Changes do not affect
        scientific data.
    state : NodeState
        Lifecycle state. New nodes default to ``PROVISIONAL``.
    created_at : datetime
        UTC timestamp at object construction.
    active : bool
        ``False`` hides the node from default views (sidebar, plots).
        Used to "soft-hide" committed nodes without discarding them;
        committed nodes are never deleted from the graph.
    style : dict
        Display-only properties (colour, line width, marker shape,
        legend visibility, ...). The style dict NEVER influences
        scientific values: any code that reads ``arrays`` or
        ``metadata`` must ignore ``style`` entirely. Style is
        controlled by the unified style dialog (CS-05) and is the
        only mutable field on a committed node.

    Notes
    -----
    Persistence (see ``project_io.py``):

    * ``arrays`` is written as a single ``{id}.npz`` file using
      ``numpy.savez_compressed``. Array dtypes and shapes are preserved.
    * Everything else (id, type, metadata, label, state, created_at,
      active, style) is written as ``{id}.json``. Enum values are
      stored as their ``.name``; ``created_at`` is stored as ISO 8601.
    * Committed nodes live in ``graph/committed/``; provisional nodes
      live in ``graph/provisional/`` and are offered for recovery on
      next project open.
    """

    id: str
    type: NodeType
    arrays: dict[str, Any]
    metadata: dict[str, Any]
    label: str
    state: NodeState = NodeState.PROVISIONAL
    created_at: datetime = field(default_factory=datetime.utcnow)
    active: bool = True
    style: dict = field(default_factory=dict)


# =====================================================================
# OperationNode
# =====================================================================

@dataclass
class OperationNode:
    """A processing step that produced one or more DataNodes.

    An ``OperationNode`` is the audit-trail counterpart of a
    ``DataNode``: it records what was done, by which engine, with
    which parameters, and which input nodes were consumed. Together
    with the input/output edges in the graph, an ``OperationNode``
    is sufficient to reproduce the operation exactly.

    Attributes
    ----------
    id : str
        Unique, permanent identifier (typically a uuid4 hex string).
    type : OperationType
        The kind of operation; see ``OperationType``.
    engine : str
        Which engine executed the operation. Conventional values:
        ``"internal"`` (pure-Python in-process), ``"larch"``,
        ``"feff"``, ``"bxas"``.
    engine_version : str
        Exact version string of the engine (e.g. ``"0.9.80"`` for
        Larch). Required for reproducibility.
    params : dict
        Complete snapshot of every parameter the engine consumed.
        Must be sufficient to re-run the operation on the same inputs
        and obtain identical outputs (modulo non-determinism inherent
        to the engine itself). Must be JSON-serialisable.
    input_ids : list[str]
        ``DataNode`` ids consumed by this operation, in the order the
        operation expects them. Order matters for asymmetric ops
        (e.g. DIFFERENCE: input_ids[0] - input_ids[1]).
    output_ids : list[str]
        ``DataNode`` ids produced by this operation.
    timestamp : datetime
        UTC timestamp at the moment the operation completed.
    duration_ms : int
        Wall-clock duration in milliseconds. Useful for performance
        diagnostics and the methods-section reproducibility report.
    status : str
        One of ``"SUCCESS"``, ``"FAILED"``, ``"PARTIAL"``. A failed
        operation can still be recorded so that the user can see
        what was attempted.
    log : str
        Captured engine stdout/stderr. May be empty.
    state : NodeState
        Lifecycle state. New operations default to ``PROVISIONAL``;
        only ``COMMITTED`` operations appear in ``log.jsonl``.
    """

    id: str
    type: OperationType
    engine: str
    engine_version: str
    params: dict
    input_ids: list[str]
    output_ids: list[str]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: int = 0
    status: str = "SUCCESS"
    log: str = ""
    state: NodeState = NodeState.PROVISIONAL
