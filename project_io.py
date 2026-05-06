"""Persistence Phase A: manifest+sidecar project format (Phase 4v / CS-46).

Locked architecture (BACKLOG persistence-umbrella entry, Phase 4r):

* Content-addressed manifest JSON + sidecar HDF5 files.
* Sidecars carry every raw array (DataNode arrays). Sidecars are
  named after the SHA-256 of the canonical (sorted-by-key) byte
  serialisation of the arrays dict, so two DataNodes with identical
  payloads share a single sidecar.
* Single ``protected: bool`` header flag gates the verification path
  on load. Phase A always writes ``protected: false``.
* Whole-app save: one manifest, one set of sidecars. Top-level
  ``plot_defaults`` mirrors ``plot_settings_dialog._USER_DEFAULTS``;
  per-tab ``tabs[<name>].plot_config`` carries each tab's local
  overrides; per-tab ``tabs[<name>].graph`` carries the full
  ProjectGraph (data nodes + op nodes + edges + active overrides).
* Implementation hash (CS-45) is verified at load: for every
  OperationNode whose ``metadata["implementation_hash"]`` is a real
  hash (not the unregistered sentinel), recompute the registry hash
  and surface a warning per mismatch. The host wraps the warnings in
  a "implementation changed since this project was saved" dialog
  with three actions (Keep cached / Re-run all changed / Show
  details — wired in commit 4 of Phase 4v).

On-disk layout::

    myproject.ptmg/
    +-- manifest.json         # whole-app state
    +-- sidecars/
        +-- <hash>.h5         # one HDF5 per unique arrays bundle
        +-- ...

Phase A explicitly defers:

* The ``.ptmg`` zip-archive form. Directory-only this phase; archive
  support is a small follow-up.
* Phases B-D (subgraph export, signed Merkle manifest, OpenTimestamps
  anchoring).
* Migration of legacy ``.ptproj`` / ``.otproj`` files (per user lock:
  "compatibility with existing project files is NOT a goal").

The TDDFT-only ``.otproj`` save/load via ``project_manager.py`` is
intentionally untouched in Phase A; ``binah.py`` adds new "Save
Workflow" / "Open Workflow" menu items that route here while leaving
the existing TDDFT project gestures alone. Unification is a future
phase.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from graph import ProjectGraph, GraphEvent, GraphEventType
from nodes import (
    DataNode,
    NodeState,
    NodeType,
    OperationNode,
    OperationType,
)
from operation_hash import (
    SENTINEL_PREFIX,
    compute_implementation_hash,
)
from version import __version__ as PTARMIGAN_VERSION


# =====================================================================
# Format constants
# =====================================================================

PTMG_FORMAT = "ptmg"
PTMG_FORMAT_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
SIDECARS_DIRNAME = "sidecars"


# =====================================================================
# Public API
# =====================================================================

def save_project(
    path: Path,
    *,
    name: str,
    plot_defaults: dict[str, Any],
    tabs: dict[str, "TabPayload"],
) -> Path:
    """Write a Ptarmigan workflow to ``path`` (a directory).

    ``path`` is the project root (e.g. ``C:/work/myproject.ptmg``).
    The directory may already exist; its contents are NOT cleared
    automatically. The directory is created if missing.

    Parameters
    ----------
    path : Path
        Project root directory. The ``.ptmg`` suffix is convention,
        not enforced.
    name : str
        Human-readable project name. Persisted in the manifest.
    plot_defaults : dict
        Snapshot of ``plot_settings_dialog._USER_DEFAULTS`` (or any
        equivalent shape).
    tabs : dict[str, TabPayload]
        Per-tab state, keyed by tab name. Tabs whose graphs are empty
        still get a manifest entry so the schema stays uniform.

    Returns the project root.
    """
    path = Path(path)
    sidecars_dir = path / SIDECARS_DIRNAME
    sidecars_dir.mkdir(parents=True, exist_ok=True)

    now_iso = _now_iso()
    existing_meta = _read_existing_meta(path)
    created_at = existing_meta.get("created_at", now_iso)

    manifest: dict[str, Any] = {
        "ptarmigan_format":         PTMG_FORMAT,
        "ptarmigan_format_version": PTMG_FORMAT_VERSION,
        "ptarmigan_version":        PTARMIGAN_VERSION,
        "python_version":           platform.python_version(),
        "name":                     name,
        "created_at":               created_at,
        "modified_at":              now_iso,
        "protected":                False,
        "plot_defaults":            _jsonify(plot_defaults),
        "tabs":                     {},
    }

    for tab_name, payload in tabs.items():
        graph = payload.graph
        manifest["tabs"][tab_name] = {
            "plot_config": _jsonify(payload.plot_config),
            "graph":       _serialise_graph(graph, sidecars_dir),
        }

    manifest_path = path / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_project(path: Path) -> "LoadedProject":
    """Read a Ptarmigan workflow from ``path`` (a directory).

    Returns a ``LoadedProject`` carrying fully reconstructed
    ProjectGraph instances per tab (no subscribers attached), plus
    plot defaults, manifest metadata, and ``implementation_warnings``:
    one entry per OperationNode whose stamped implementation hash no
    longer matches the current registry hash. The host should surface
    the warnings via a dialog with three actions (Keep / Re-run /
    Details).

    Raises
    ------
    FileNotFoundError
        If ``path`` does not contain a ``manifest.json``.
    ValueError
        If the manifest's ``ptarmigan_format`` is not ``"ptmg"`` or
        the format version is unsupported.
    """
    path = Path(path)
    manifest_path = path / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Not a Ptarmigan workflow directory (missing "
            f"{MANIFEST_FILENAME!r}): {path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    fmt = manifest.get("ptarmigan_format")
    if fmt != PTMG_FORMAT:
        raise ValueError(
            f"Unrecognised project format {fmt!r} at {path} "
            f"(expected {PTMG_FORMAT!r})"
        )
    fmt_ver = manifest.get("ptarmigan_format_version")
    if fmt_ver != PTMG_FORMAT_VERSION:
        raise ValueError(
            f"Unsupported manifest version {fmt_ver!r} at {path} "
            f"(this build supports v{PTMG_FORMAT_VERSION})"
        )

    sidecars_dir = path / SIDECARS_DIRNAME
    tabs_out: dict[str, TabPayload] = {}
    impl_warnings: list[str] = []

    for tab_name, tab_blob in (manifest.get("tabs") or {}).items():
        graph, tab_warnings = _deserialise_graph(
            tab_blob.get("graph", {}),
            sidecars_dir=sidecars_dir,
            tab_name=tab_name,
        )
        impl_warnings.extend(tab_warnings)
        tabs_out[tab_name] = TabPayload(
            plot_config=dict(tab_blob.get("plot_config", {})),
            graph=graph,
        )

    return LoadedProject(
        name=manifest.get("name", ""),
        created_at=manifest.get("created_at", ""),
        modified_at=manifest.get("modified_at", ""),
        ptarmigan_version=manifest.get("ptarmigan_version", ""),
        plot_defaults=dict(manifest.get("plot_defaults", {})),
        tabs=tabs_out,
        implementation_warnings=impl_warnings,
    )


def verify_project(path: Path) -> dict[str, list[str]]:
    """Recompute every sidecar's content hash and every op's
    implementation hash; return per-category warning lists.

    Returns ``{"array_warnings": [...], "implementation_warnings": [...]}``.
    Empty lists everywhere ⇒ project is byte-identical to its
    saved-to-disk form (sidecars have not been tampered with) and
    every OperationNode's implementation hash still matches the
    current registry.
    """
    path = Path(path)
    manifest_path = path / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Not a Ptarmigan workflow directory: {path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sidecars_dir = path / SIDECARS_DIRNAME

    array_warnings: list[str] = []
    impl_warnings: list[str] = []
    seen_hashes: set[str] = set()

    for tab_name, tab_blob in (manifest.get("tabs") or {}).items():
        graph_blob = tab_blob.get("graph", {})
        for dn in graph_blob.get("data_nodes", []):
            arrays_hash = dn.get("arrays_hash")
            if arrays_hash is None or arrays_hash in seen_hashes:
                continue
            seen_hashes.add(arrays_hash)
            sidecar_path = sidecars_dir / f"{arrays_hash}.h5"
            if not sidecar_path.exists():
                array_warnings.append(
                    f"sidecar missing: {arrays_hash[:16]}... "
                    f"(referenced by node {dn.get('id', '?')!r} "
                    f"in tab {tab_name!r})"
                )
                continue
            actual = _hash_arrays(_read_arrays_sidecar(sidecar_path))
            if actual != arrays_hash:
                array_warnings.append(
                    f"sidecar hash mismatch: {arrays_hash[:16]}... "
                    f"(actual {actual[:16]}...) referenced by node "
                    f"{dn.get('id', '?')!r} in tab {tab_name!r}"
                )

        for op in graph_blob.get("op_nodes", []):
            stored = (op.get("metadata") or {}).get("implementation_hash")
            if stored is None or stored.startswith(SENTINEL_PREFIX):
                continue
            try:
                op_type = OperationType[op["type"]]
            except (KeyError, ValueError):
                continue
            current = compute_implementation_hash(op_type)
            if current.startswith(SENTINEL_PREFIX):
                impl_warnings.append(
                    f"op {op.get('id', '?')!r} ({op['type']}) was saved "
                    f"with hash {stored[:16]}... but no implementation is "
                    f"registered in this build"
                )
            elif current != stored:
                impl_warnings.append(
                    f"op {op.get('id', '?')!r} ({op['type']}) "
                    f"implementation changed: saved {stored[:16]}... -> "
                    f"now {current[:16]}..."
                )

    return {
        "array_warnings":           array_warnings,
        "implementation_warnings":  impl_warnings,
    }


# =====================================================================
# Payload dataclasses (the public surface for callers)
# =====================================================================

@dataclass
class TabPayload:
    """One tab's serialisable state.

    ``plot_config`` is a free-form dict mirroring the tab's existing
    ``_plot_config`` attribute. ``graph`` is the live ProjectGraph
    instance; project_io reads it on save and reconstructs a fresh
    one on load.
    """
    plot_config: dict[str, Any]
    graph: ProjectGraph


@dataclass
class LoadedProject:
    """Result of ``load_project``.

    Mirrors the manifest's top-level shape with plot_defaults and
    per-tab payloads ready to swap into the running app, plus
    ``implementation_warnings`` for the host's mismatch dialog.
    """
    name: str
    created_at: str
    modified_at: str
    ptarmigan_version: str
    plot_defaults: dict[str, Any]
    tabs: dict[str, TabPayload]
    implementation_warnings: list[str] = field(default_factory=list)


# =====================================================================
# Graph (de)serialisation
# =====================================================================

def _serialise_graph(
    graph: ProjectGraph,
    sidecars_dir: Path,
) -> dict[str, Any]:
    """Serialise a ProjectGraph into a manifest-ready dict, writing
    every unique array bundle to ``sidecars_dir`` as ``<hash>.h5``."""
    data_nodes: list[dict[str, Any]] = []
    op_nodes: list[dict[str, Any]] = []

    written: set[str] = set()

    for node in graph.nodes.values():
        if isinstance(node, DataNode):
            arrays_hash = _hash_arrays(node.arrays)
            sidecar_path = sidecars_dir / f"{arrays_hash}.h5"
            if arrays_hash not in written and not sidecar_path.exists():
                _write_arrays_sidecar(sidecar_path, node.arrays)
            written.add(arrays_hash)
            data_nodes.append(_serialise_data_node(node, arrays_hash))
        elif isinstance(node, OperationNode):
            op_nodes.append(_serialise_op_node(node))
        # Defensive: future NodeType subclasses fall through here;
        # the schema can be extended without breaking older saves.

    edges = [list(edge) for edge in graph.edges]
    active_overrides = dict(graph._active_overrides)

    return {
        "data_nodes":        data_nodes,
        "op_nodes":          op_nodes,
        "edges":             edges,
        "active_overrides":  active_overrides,
    }


def _deserialise_graph(
    blob: dict[str, Any],
    *,
    sidecars_dir: Path,
    tab_name: str,
) -> tuple[ProjectGraph, list[str]]:
    """Reconstruct a ProjectGraph from a manifest blob, returning the
    graph plus a per-op implementation-mismatch warning list."""
    graph = ProjectGraph()
    impl_warnings: list[str] = []

    for dn_blob in blob.get("data_nodes", []):
        arrays_hash = dn_blob.get("arrays_hash")
        if arrays_hash is None:
            arrays: dict[str, np.ndarray] = {}
        else:
            sidecar_path = sidecars_dir / f"{arrays_hash}.h5"
            if not sidecar_path.exists():
                arrays = {}
            else:
                arrays = _read_arrays_sidecar(sidecar_path)
        graph.nodes[dn_blob["id"]] = _deserialise_data_node(dn_blob, arrays)

    for op_blob in blob.get("op_nodes", []):
        op_node = _deserialise_op_node(op_blob)
        graph.nodes[op_node.id] = op_node
        stored = op_node.metadata.get("implementation_hash")
        if stored is None or stored.startswith(SENTINEL_PREFIX):
            continue
        current = compute_implementation_hash(op_node.type)
        if current.startswith(SENTINEL_PREFIX):
            impl_warnings.append(
                f"[{tab_name}] op {op_node.id!r} ({op_node.type.name}) "
                f"was saved with implementation hash {stored[:16]}... but "
                f"the current build has no implementation registered"
            )
        elif current != stored:
            impl_warnings.append(
                f"[{tab_name}] op {op_node.id!r} ({op_node.type.name}) "
                f"implementation changed since save "
                f"({stored[:16]}... -> {current[:16]}...)"
            )

    for edge in blob.get("edges", []):
        graph.edges.append((edge[0], edge[1]))

    graph._active_overrides = dict(blob.get("active_overrides", {}))

    return graph, impl_warnings


def _serialise_data_node(node: DataNode, arrays_hash: str) -> dict[str, Any]:
    return {
        "id":          node.id,
        "type":        node.type.name,
        "label":       node.label,
        "state":       node.state.name,
        "created_at":  node.created_at.isoformat(),
        "active":      node.active,
        "style":       _jsonify(node.style),
        "metadata":    _jsonify(node.metadata),
        "arrays_hash": arrays_hash,
    }


def _deserialise_data_node(
    blob: dict[str, Any],
    arrays: dict[str, np.ndarray],
) -> DataNode:
    return DataNode(
        id=blob["id"],
        type=NodeType[blob["type"]],
        arrays=arrays,
        metadata=dict(blob.get("metadata", {})),
        label=blob.get("label", ""),
        state=NodeState[blob.get("state", "PROVISIONAL")],
        created_at=_parse_iso(blob.get("created_at")),
        active=bool(blob.get("active", True)),
        style=dict(blob.get("style", {})),
    )


def _serialise_op_node(node: OperationNode) -> dict[str, Any]:
    return {
        "id":             node.id,
        "type":           node.type.name,
        "engine":         node.engine,
        "engine_version": node.engine_version,
        "params":         _jsonify(node.params),
        "input_ids":      list(node.input_ids),
        "output_ids":     list(node.output_ids),
        "timestamp":      node.timestamp.isoformat(),
        "duration_ms":    int(node.duration_ms),
        "status":         node.status,
        "log":            node.log,
        "state":          node.state.name,
        "metadata":       _jsonify(node.metadata),
        "deterministic":  bool(node.deterministic),
    }


def _deserialise_op_node(blob: dict[str, Any]) -> OperationNode:
    return OperationNode(
        id=blob["id"],
        type=OperationType[blob["type"]],
        engine=blob.get("engine", "internal"),
        engine_version=blob.get("engine_version", ""),
        params=dict(blob.get("params", {})),
        input_ids=list(blob.get("input_ids", [])),
        output_ids=list(blob.get("output_ids", [])),
        timestamp=_parse_iso(blob.get("timestamp")),
        duration_ms=int(blob.get("duration_ms", 0)),
        status=blob.get("status", "SUCCESS"),
        log=blob.get("log", ""),
        state=NodeState[blob.get("state", "PROVISIONAL")],
        metadata=dict(blob.get("metadata", {})),
        deterministic=bool(blob.get("deterministic", True)),
    )


# =====================================================================
# Sidecar (arrays) HDF5 round-trip + content hashing
# =====================================================================

def _hash_arrays(arrays: dict[str, np.ndarray]) -> str:
    """SHA-256 over a canonical, deterministic encoding of an arrays
    dict.

    Encoding (per array, in sorted-key order)::

        "k:" || key_bytes || "\\n"
        "d:" || dtype.str_bytes || "\\n"
        "s:" || comma-joined shape || "\\n"
        "b:" || array.tobytes() || "\\n"

    Key sorting + per-section length encoding ensure that two arrays
    dicts with the same content always hash identically regardless
    of insertion order.
    """
    h = hashlib.sha256()
    for key in sorted(arrays.keys()):
        arr = np.asarray(arrays[key])
        h.update(b"k:")
        h.update(key.encode("utf-8"))
        h.update(b"\n")
        h.update(b"d:")
        h.update(arr.dtype.str.encode("ascii"))
        h.update(b"\n")
        h.update(b"s:")
        h.update(",".join(str(d) for d in arr.shape).encode("ascii"))
        h.update(b"\n")
        h.update(b"b:")
        h.update(np.ascontiguousarray(arr).tobytes())
        h.update(b"\n")
    return h.hexdigest()


def _write_arrays_sidecar(path: Path, arrays: dict[str, np.ndarray]) -> None:
    """Write an arrays dict to an HDF5 file, one dataset per key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        for key, arr in arrays.items():
            f.create_dataset(
                key,
                data=np.asarray(arr),
                compression="gzip",
                compression_opts=4,
            )


def _read_arrays_sidecar(path: Path) -> dict[str, np.ndarray]:
    """Read an HDF5 sidecar back into an arrays dict."""
    out: dict[str, np.ndarray] = {}
    with h5py.File(path, "r") as f:
        for key in f.keys():
            out[key] = np.asarray(f[key][...])
    return out


# =====================================================================
# Helpers
# =====================================================================

def _jsonify(value: Any) -> Any:
    """Recursively coerce numpy scalars and tuples into JSON-friendly
    Python natives. ``params`` and ``metadata`` round-trip through
    JSON so any nested numpy or tuple values must be flattened."""
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(s: str | None) -> datetime:
    """Parse an ISO 8601 timestamp; fall back to current UTC if absent
    or malformed (load is best-effort, not a verifier)."""
    if not s:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _read_existing_meta(path: Path) -> dict[str, Any]:
    """Read just the manifest's top-level dict for an in-place save
    (preserves ``created_at`` across re-saves)."""
    target = path / MANIFEST_FILENAME
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# =====================================================================
# Hashing helpers retained for callers (raw file integrity etc.)
# =====================================================================

_HASH_CHUNK = 1 << 20


def hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of the file *contents* at ``path``.

    Retained from the pre-Phase-A project_io for callers that want to
    fingerprint instrument files for the UV/Vis tab's
    ``_has_existing_load`` deduplication logic and for the future
    raw-file sidecar (raw original instrument file persistence is
    deferred to a Phase A follow-up; today only the parsed arrays
    round-trip through the sidecar).
    """
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def copy_project(src: Path, dst: Path) -> Path:
    """Recursively copy a project directory. Used by Save As when the
    user picks a new destination - the old project stays where it was."""
    src = Path(src)
    dst = Path(dst)
    if dst.exists():
        raise FileExistsError(f"Destination already exists: {dst}")
    shutil.copytree(src, dst)
    return dst
