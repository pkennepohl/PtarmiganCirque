"""On-disk persistence for Ptarmigan projects (.ptproj/ directory).

This module is the only place that knows about the project file
format. Everything in ``graph.py`` and ``nodes.py`` is in-memory.

Layout produced and consumed here (CS-13):

    projectname.ptproj/
    +-- project.json           # name, timestamps, version info
    +-- graph/
    |   +-- committed/         # immutable nodes (deferred)
    |   +-- provisional/       # ephemeral nodes (deferred)
    +-- raw/
    |   +-- {id}__{filename}   # original file copies
    |   +-- manifest.json      # {node_id: {original_path, sha256, ...}}
    +-- sessions/              # workspace-window sessions (deferred)
    +-- log.jsonl              # append-only committed-ops audit (deferred)

In this session we implement:

* the directory skeleton (``create_project``)
* ``project.json`` read/write (``read_project_meta`` /
  ``write_project_meta``)
* raw file ingestion: copy + SHA-256 + manifest.json
  (``copy_raw_file``, ``read_raw_manifest``, ``write_raw_manifest``,
  ``hash_file``)

Full graph serialisation (committed/, provisional/), provisional
recovery, and reproducibility report generation are deferred — see
the NotImplementedError stubs at the bottom of the file.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from version import __version__ as PTARMIGAN_VERSION

# Directory and file names within a .ptproj/ project.
PROJECT_JSON       = "project.json"
GRAPH_DIR          = "graph"
COMMITTED_DIR      = "graph/committed"
PROVISIONAL_DIR    = "graph/provisional"
RAW_DIR            = "raw"
RAW_MANIFEST       = "raw/manifest.json"
SESSIONS_DIR       = "sessions"
LOG_FILE           = "log.jsonl"

# Hashing chunk size; large enough to be efficient on small files,
# small enough that big files do not dominate memory.
_HASH_CHUNK = 1 << 20  # 1 MiB


# =====================================================================
# Project skeleton
# =====================================================================

def create_project(path: Path, name: str) -> Path:
    """Create a new empty .ptproj/ directory at ``path``.

    Parameters
    ----------
    path : Path
        Target directory. Must not already exist (refuse to overwrite
        an existing project — that is the caller's responsibility).
    name : str
        Human-readable project name; written into ``project.json``.

    Returns
    -------
    Path
        The created project directory (same as ``path``).
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Path already exists: {path}")

    # Create directory skeleton.
    path.mkdir(parents=True)
    (path / COMMITTED_DIR).mkdir(parents=True)
    (path / PROVISIONAL_DIR).mkdir(parents=True)
    (path / RAW_DIR).mkdir(parents=True)
    (path / SESSIONS_DIR).mkdir(parents=True)

    # Initial metadata.
    now = _now_iso()
    write_project_meta(path, {
        "name":              name,
        "created_at":        now,
        "modified_at":       now,
        "ptarmigan_version": PTARMIGAN_VERSION,
        "python_version":    platform.python_version(),
    })

    # Empty raw manifest and empty log.
    write_raw_manifest(path, {})
    (path / LOG_FILE).touch()

    return path


# =====================================================================
# project.json
# =====================================================================

def write_project_meta(project_path: Path, meta: dict) -> None:
    """Write ``project.json`` for the project at ``project_path``.

    The caller is responsible for the contents of ``meta``; this
    function simply pretty-prints the dict as JSON. ``modified_at``
    is *not* updated automatically here — callers that mutate a
    project should set it explicitly so save semantics stay
    predictable.
    """
    project_path = Path(project_path)
    target = project_path / PROJECT_JSON
    target.write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_project_meta(project_path: Path) -> dict:
    """Read and return ``project.json`` from ``project_path``.

    Raises ``FileNotFoundError`` if the project is missing the file.
    """
    project_path = Path(project_path)
    target = project_path / PROJECT_JSON
    return json.loads(target.read_text(encoding="utf-8"))


# =====================================================================
# Raw files: SHA-256, copy, manifest
# =====================================================================

def hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of the file *contents* at ``path``.

    The hash covers the bytes of the file only — never the filename
    or any filesystem metadata. Reads the file in 1 MiB chunks so
    multi-gigabyte raw beamline files do not need to fit in memory.
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


@dataclass
class RawFileRecord:
    """One entry in ``raw/manifest.json``.

    Attributes
    ----------
    original_path : str
        Absolute path of the source file at the time it was loaded.
        Stored for human reference only — Ptarmigan never reads from
        this path again once the file has been copied into the project.
    sha256 : str
        Hex digest of the file contents.
    copied_to : str
        Path of the copy *relative to the project root* (e.g.
        ``"raw/ds_001__scan1.dat"``).
    copied_at : str
        ISO 8601 UTC timestamp when the copy was made.
    """

    original_path: str
    sha256: str
    copied_to: str
    copied_at: str

    def to_dict(self) -> dict:
        return {
            "original_path": self.original_path,
            "sha256":        self.sha256,
            "copied_to":     self.copied_to,
            "copied_at":     self.copied_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RawFileRecord":
        return cls(
            original_path=d["original_path"],
            sha256=d["sha256"],
            copied_to=d["copied_to"],
            copied_at=d["copied_at"],
        )


def copy_raw_file(
    project_path: Path,
    source_path: Path,
    node_id: str,
) -> RawFileRecord:
    """Copy a raw input file into the project and update the manifest.

    The copy is named ``raw/{node_id}__{original_filename}`` so that
    multiple files with the same basename can coexist without clobbering
    each other. The SHA-256 is computed from the *copy* (which is byte
    identical to the source) and recorded in ``raw/manifest.json``
    keyed by ``node_id``.

    Returns the new ``RawFileRecord``.
    """
    project_path = Path(project_path)
    source_path = Path(source_path).resolve()

    raw_dir = project_path / RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)

    dest_name = f"{node_id}__{source_path.name}"
    dest_path = raw_dir / dest_name

    if dest_path.exists():
        raise FileExistsError(
            f"Raw file already exists for node {node_id!r}: {dest_path}"
        )

    shutil.copy2(source_path, dest_path)
    digest = hash_file(dest_path)

    record = RawFileRecord(
        original_path=str(source_path),
        sha256=digest,
        copied_to=f"{RAW_DIR}/{dest_name}",
        copied_at=_now_iso(),
    )

    manifest = read_raw_manifest(project_path)
    manifest[node_id] = record
    write_raw_manifest(project_path, manifest)

    return record


def read_raw_manifest(project_path: Path) -> dict[str, RawFileRecord]:
    """Read ``raw/manifest.json`` and return ``{node_id: RawFileRecord}``.

    Returns an empty dict if the manifest does not exist yet.
    """
    project_path = Path(project_path)
    target = project_path / RAW_MANIFEST
    if not target.exists():
        return {}
    raw = json.loads(target.read_text(encoding="utf-8"))
    return {nid: RawFileRecord.from_dict(d) for nid, d in raw.items()}


def write_raw_manifest(
    project_path: Path,
    manifest: dict[str, RawFileRecord],
) -> None:
    """Write ``raw/manifest.json``.

    Ensures the parent directory exists.
    """
    project_path = Path(project_path)
    target = project_path / RAW_MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    serialisable = {nid: rec.to_dict() for nid, rec in manifest.items()}
    target.write_text(
        json.dumps(serialisable, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_raw_files(project_path: Path) -> list[str]:
    """Recompute SHA-256 of every copied raw file and report mismatches.

    Returns a list of human-readable warning strings, one per file that
    is missing from disk or whose hash does not match the manifest.
    An empty list means the project's raw/ directory is intact.
    """
    project_path = Path(project_path)
    manifest = read_raw_manifest(project_path)
    warnings: list[str] = []
    for node_id, rec in manifest.items():
        copy_path = project_path / rec.copied_to
        if not copy_path.exists():
            warnings.append(
                f"raw file missing: {rec.copied_to} (node {node_id})"
            )
            continue
        actual = hash_file(copy_path)
        if actual != rec.sha256:
            warnings.append(
                f"raw file hash mismatch: {rec.copied_to} (node {node_id}): "
                f"manifest={rec.sha256[:12]}..., actual={actual[:12]}..."
            )
    return warnings


# =====================================================================
# Deferred: full graph serialisation, recovery, reproducibility report
# =====================================================================

def save_graph(graph, project_path: Path) -> None:
    """Persist a ProjectGraph to ``graph/committed/`` and ``graph/provisional/``.

    TODO (later phase): for each DataNode write ``{id}.json`` (metadata)
    and ``{id}.npz`` (arrays via numpy.savez_compressed); for each
    OperationNode write ``{id}.json``. Committed nodes go to
    graph/committed/, provisional nodes to graph/provisional/.
    Append newly committed operations to log.jsonl. Update
    project.json modified_at.
    """
    raise NotImplementedError(
        "save_graph is implemented in a later phase — node-level "
        "serialisation is intentionally deferred until the in-memory "
        "graph contract is stable."
    )


def load_graph(project_path: Path):
    """Reconstruct a ProjectGraph from a .ptproj/ directory.

    TODO (later phase): read every ``{id}.json`` in graph/committed/,
    rehydrate as DataNode or OperationNode (recover NodeType /
    OperationType / NodeState by name, parse created_at/timestamp,
    load arrays from matching .npz), reconnect edges based on
    operation input/output ids, and emit GRAPH_LOADED. Then offer
    provisional recovery (see recover_provisional below).
    """
    raise NotImplementedError(
        "load_graph is implemented in a later phase."
    )


def recover_provisional(project_path: Path):
    """Detect provisional nodes from a previous session and offer recovery.

    TODO (later phase): inspect graph/provisional/. If non-empty,
    return a summary the UI can present in a "restore or discard"
    dialog (the same gesture as crash recovery in a word processor).
    On restore, load the provisional nodes into the graph as
    PROVISIONAL. On discard, delete graph/provisional/ contents.
    """
    raise NotImplementedError(
        "recover_provisional is implemented in a later phase."
    )


def export_reproducibility_report(
    graph,
    compare_node_ids: list[str],
    output_path: Path,
    fmt: str = "text",
) -> None:
    """Write a human- or machine-readable reproducibility report.

    TODO (later phase): for each id in compare_node_ids, walk the
    full provenance chain via graph.provenance_chain, format every
    OperationNode as a methods-section paragraph (engine, version,
    parameters, inputs), and write to ``output_path`` in either
    ``"text"`` (markdown-ish) or ``"json"`` form. Cross-reference
    raw files by SHA-256 from raw/manifest.json.
    """
    raise NotImplementedError(
        "export_reproducibility_report is implemented in a later phase."
    )


# =====================================================================
# Internals
# =====================================================================

def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.utcnow().isoformat(timespec="seconds")
