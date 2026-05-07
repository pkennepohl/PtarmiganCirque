"""Per-OperationType implementation hash registry (Phase 4v).

Maps each ``OperationType`` to the concrete Python callable(s) that
implement it. ``compute_implementation_hash(op_type)`` returns a
SHA-256 over the source bytes of every registered callable in the
op's bundle. Apply sites stamp the result into
``OperationNode.metadata["implementation_hash"]``; project load
(persistence Phase A) recomputes the hash and compares — any mismatch
means the algorithmic code path has changed since the project was
saved (whitespace edits to a ``compute_*`` function, a new helper
added, a conditioning strategy swapped out, etc.) and the user
sees a "implementation changed since this project was saved" dialog.

The registry is the SINGLE source of truth for which functions count
as the "implementation" of an op. Helpers shared across compute_*
modes (e.g. ``_floor_zero``, ``_spline_evaluate``, ``_scattering_window``
for BASELINE) are explicitly enumerated in the bundle so any edit
to them invalidates the hash.

Why automatic source-hash (Q1.a) and not manual semver:

* zero developer overhead — no string to bump on every conditioning
  tweak; auto-detects the Phase 4t polynomial conditioning swap that
  motivated the umbrella entry
* manual semver gets forgotten; the failure mode (silent drift) is
  exactly what the entry was raised to prevent
* false positives from whitespace-only edits are the right behaviour
  on the precautionary-principle side: re-run is one click in the
  load-time mismatch dialog, and a stable formatter (e.g. ``black``)
  keeps run-to-run noise out

Unregistered OperationTypes return the sentinel string
``"unregistered:<OperationType.name>"``. The mismatch check at load
time treats sentinel-vs-sentinel as a match (no false positive for
ops the registry has not yet been extended to cover) and
sentinel-vs-real-hash as a structural change worth surfacing.
"""

from __future__ import annotations

import hashlib
import inspect
from typing import Callable

from nodes import OperationType


# =====================================================================
# Registry
# =====================================================================

# OperationType -> tuple of callables whose source bytes constitute the
# implementation of that op. Order does not matter; the hash is
# computed over a deterministic re-ordering by ``__qualname__``.
_HASH_REGISTRY: dict[OperationType, tuple[Callable, ...]] = {}

# Cache of computed hashes. Keyed by OperationType. Invalidated when
# the registry is mutated (callers should not mutate after startup
# anyway). Deliberately small: one entry per OperationType.
_HASH_CACHE: dict[OperationType, str] = {}

# Sentinel prefix returned for OperationTypes that have no registered
# bundle. Includes the op name so a manifest carrying sentinels can
# still be diffed meaningfully.
SENTINEL_PREFIX = "unregistered:"


def register_implementation(
    op_type: OperationType,
    *callables: Callable,
) -> None:
    """Register the implementation bundle for ``op_type``.

    Replaces any prior registration for ``op_type`` and invalidates
    that op's hash cache entry. Tests use this to register stub
    callables; production registers the real compute_* set via
    ``register_default_implementations``.
    """
    _HASH_REGISTRY[op_type] = tuple(callables)
    _HASH_CACHE.pop(op_type, None)


def clear_registry() -> None:
    """Wipe the registry. Test-only helper."""
    _HASH_REGISTRY.clear()
    _HASH_CACHE.clear()


def is_registered(op_type: OperationType) -> bool:
    """Return ``True`` iff ``op_type`` has a registered implementation."""
    return op_type in _HASH_REGISTRY


def registered_op_types() -> tuple[OperationType, ...]:
    """Return the registered OperationTypes (sorted by name)."""
    return tuple(sorted(_HASH_REGISTRY.keys(), key=lambda t: t.name))


# =====================================================================
# Hash computation
# =====================================================================

def compute_implementation_hash(op_type: OperationType) -> str:
    """Return the SHA-256 (hex) of the registered implementation bundle.

    For unregistered ops returns ``"unregistered:<name>"``.

    The hash is computed once per OperationType and cached. The hash
    domain-separates by op name so two different ops registering the
    same set of callables (which would be a registration bug, but is
    technically expressible) get distinct hashes.
    """
    cached = _HASH_CACHE.get(op_type)
    if cached is not None:
        return cached

    bundle = _HASH_REGISTRY.get(op_type)
    if bundle is None:
        sentinel = f"{SENTINEL_PREFIX}{op_type.name}"
        # Do NOT cache sentinels — registration may happen lazily
        # (tests register/unregister between assertions). Real hashes
        # are derived from immutable source bytes so caching them is
        # safe; sentinels can flip when registration occurs.
        return sentinel

    h = hashlib.sha256()
    # Domain-separate by op name so the registry can't accidentally
    # collide hashes between two ops with the same callables.
    h.update(b"op_type:")
    h.update(op_type.name.encode("utf-8"))
    h.update(b"\n")

    # Sort callables by qualname for determinism. Two registrations
    # with the same callables in different order produce the same hash.
    for fn in sorted(bundle, key=_qualname):
        h.update(b"fn:")
        h.update(_qualname(fn).encode("utf-8"))
        h.update(b"\n")
        h.update(_source_bytes(fn))
        h.update(b"\n")

    digest = h.hexdigest()
    _HASH_CACHE[op_type] = digest
    return digest


def _qualname(fn: Callable) -> str:
    """Module + qualname pair so two same-named callables in different
    modules don't collide."""
    module = getattr(fn, "__module__", "")
    qual = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
    return f"{module}:{qual}"


def _source_bytes(fn: Callable) -> bytes:
    """Return the source bytes of ``fn``.

    Wraps ``inspect.getsource`` so the failure mode for a callable
    whose source cannot be located (built-ins, dynamically created
    callables, REPL definitions) is a deterministic-but-noisy
    placeholder rather than an exception. Such callables should not
    appear in the production registry; the placeholder makes the
    test failure obvious.
    """
    try:
        return inspect.getsource(fn).encode("utf-8")
    except (OSError, TypeError):
        return f"<source-unavailable:{_qualname(fn)}>".encode("utf-8")


# =====================================================================
# Default registration (production code)
# =====================================================================

def register_default_implementations() -> None:
    """Register the compute_* bundles for every shipped OperationType.

    Idempotent: re-calling has no observable effect beyond clearing
    the hash cache for the registered ops. Imports are local so that
    the operation_hash module itself stays import-cheap; production
    callers (project_io, the apply sites) trigger this once at app
    startup.

    Coverage today (Phase 4v):

    * ``BASELINE`` — every ``compute_*`` for the six modes plus the
      shared validators (``_floor_zero``, ``_resolve_n_bounds``) and
      the per-mode helpers (``_spline_evaluate`` /
      ``_spline_floor_zero_fit`` for spline, ``_scattering_window`` /
      ``_scattering_fit`` / ``_scattering_offset_fit`` for the
      scattering pair).
    * ``NORMALISE`` — both modes (``compute_peak`` / ``compute_area``)
      plus shared validators.
    * ``SMOOTH`` — both modes (``compute_savgol`` /
      ``compute_moving_avg``) plus the shared validator.
    * ``PEAK_PICK`` — both modes (``compute_prominence`` /
      ``compute_manual``) plus the shared validator.
    * ``SECOND_DERIVATIVE`` — single ``compute`` plus the shared
      validator.
    * ``LOAD`` — the parser entry point. Future OLIS / .ols / .asc
      readers extend the bundle.

    OperationTypes not used by the redesign UV/Vis flow today
    (DEGLITCH, SHIFT_ENERGY, AVERAGE, DIFFERENCE, FEFF_RUN, BXAS_FIT)
    are intentionally NOT registered; they get the unregistered
    sentinel hash. Register them when their compute_* lands.
    """
    # Local imports keep module load cheap when only the registry
    # primitives (register_implementation / compute_implementation_hash)
    # are needed (tests; tooling).
    from uvvis_baseline import (
        compute_linear,
        compute_polynomial,
        compute_spline,
        compute_rubberband,
        compute_scattering,
        compute_scattering_offset,
        _floor_zero,
        _resolve_n_bounds,
        _spline_evaluate,
        _spline_floor_zero_fit,
        _scattering_window,
        _scattering_fit,
        _scattering_offset_fit,
    )
    from uvvis_normalise import (
        compute_peak,
        compute_area,
        _coerce as _normalise_coerce,
        _window_mask,
    )
    from uvvis_smoothing import (
        compute_savgol,
        compute_moving_avg,
        _coerce as _smoothing_coerce,
    )
    from uvvis_peak_picking import (
        compute_prominence,
        compute_manual,
        _coerce as _peak_picking_coerce,
    )
    from uvvis_second_derivative import (
        compute as compute_second_derivative,
        _coerce as _second_derivative_coerce,
    )
    from uvvis_parser import parse_uvvis_file

    register_implementation(
        OperationType.BASELINE,
        compute_linear,
        compute_polynomial,
        compute_spline,
        compute_rubberband,
        compute_scattering,
        compute_scattering_offset,
        _floor_zero,
        _resolve_n_bounds,
        _spline_evaluate,
        _spline_floor_zero_fit,
        _scattering_window,
        _scattering_fit,
        _scattering_offset_fit,
    )
    register_implementation(
        OperationType.NORMALISE,
        compute_peak,
        compute_area,
        _normalise_coerce,
        _window_mask,
    )
    register_implementation(
        OperationType.SMOOTH,
        compute_savgol,
        compute_moving_avg,
        _smoothing_coerce,
    )
    register_implementation(
        OperationType.PEAK_PICK,
        compute_prominence,
        compute_manual,
        _peak_picking_coerce,
    )
    register_implementation(
        OperationType.SECOND_DERIVATIVE,
        compute_second_derivative,
        _second_derivative_coerce,
    )
    register_implementation(
        OperationType.LOAD,
        parse_uvvis_file,
    )
