"""
uvvis_tab.py — UV/Vis/NIR analysis tab for Ptarmigan

Phase 4a (loader migration + sidebar swap): the tab reads from a
ProjectGraph rather than a private `_entries` list. File load creates
a COMMITTED RAW_FILE DataNode + LOAD OperationNode + COMMITTED UVVIS
DataNode wired together (CS-13 §"Implementation notes (Phase 4a)").
No analysis runs automatically — parsing the on-disk format into
arrays is bookkeeping, not science.

The right pane is now ``ScanTreeWidget`` (CS-04). Per-row controls,
gestures, and the gear-button hand-off to the unified
``StyleDialog`` (CS-05) all live in that widget. The tab subscribes
to ``GraphEvent`` so dialog- and row-driven mutations drive the plot
without explicit redraw calls.
"""

from __future__ import annotations

import copy
import os
import uuid
from typing import Any, Callable, Iterable, List, Mapping, Optional, Tuple

import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import matplotlib
from matplotlib.ticker import FixedLocator, MultipleLocator
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from uvvis_parser import UVVisScan, parse_uvvis_file
from experimental_parser import ExperimentalScan
from graph import GraphEvent, GraphEventType, ProjectGraph
from nodes import (
    DataNode,
    NodeState,
    NodeType,
    OperationNode,
    OperationType,
)
from operation_hash import compute_implementation_hash
from scan_tree_widget import ScanTreeWidget, _SIDEBAR_MIN_WIDTH_PX
from style_dialog import open_style_dialog
from tooltip import Tooltip
import plot_settings_dialog
import plot_axis_hit_test
import uvvis_baseline
import uvvis_normalise
import uvvis_smoothing
import uvvis_peak_picking
import uvvis_second_derivative
import node_export
from collapsible_section import CollapsibleSection
from node_styles import default_spectrum_style, pick_default_color
from version import __version__ as PTARMIGAN_VERSION

# Colour palette: lifted to node_styles.SPECTRUM_PALETTE in Phase 4j
# (CS-21). Both call sites in this file (the UVVIS loader's default
# colour assignment and _apply_baseline's BASELINE colour assignment)
# go through node_styles.pick_default_color, which walks every
# spectrum-shaped NodeType in one go.

# ── File-type filter ──────────────────────────────────────────────────────────
_FILE_TYPES = [
    ("UV/Vis files",
     "*.csv *.tsv *.txt *.prn *.dpt *.sp *.asc *.dat *.olis *.olisdat"),
    ("CSV / text",  "*.csv *.tsv *.txt *.prn"),
    ("OLIS",        "*.olis *.olisdat *.dat *.asc"),
    ("All files",   "*.*"),
]

# ── Unit conversion ───────────────────────────────────────────────────────────
_NM_TO_CM1 = 1e7
_HC_NM_EV  = 1239.84193

def _nm_to(unit: str, nm_val: float) -> float:
    if nm_val <= 0:
        return nm_val
    if unit == "nm":    return nm_val
    if unit == "cm-1":  return _NM_TO_CM1 / nm_val
    if unit == "eV":    return _HC_NM_EV  / nm_val
    return nm_val

def _to_nm(unit: str, val: float) -> float:
    if val <= 0:
        return val
    if unit == "nm":    return val
    if unit == "cm-1":  return _NM_TO_CM1 / val
    if unit == "eV":    return _HC_NM_EV  / val
    return val

def _convert_xlim(lo: float, hi: float,
                  from_unit: str, to_unit: str) -> Tuple[float, float]:
    a = _nm_to(to_unit, _to_nm(from_unit, lo))
    b = _nm_to(to_unit, _to_nm(from_unit, hi))
    return (min(a, b), max(a, b))


def _wavelength_to_x(wavelength_nm: np.ndarray, unit: str) -> np.ndarray:
    """Derive the displayed x-axis from the canonical wavelength_nm array."""
    if unit == "cm-1":
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(wavelength_nm > 0,
                            _NM_TO_CM1 / wavelength_nm, 0.0)
    if unit == "eV":
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(wavelength_nm > 0,
                            _HC_NM_EV / wavelength_nm, 0.0)
    return wavelength_nm


def _absorbance_to_y(
    absorbance: np.ndarray,
    y_unit: str,
    node_type: NodeType,
) -> np.ndarray:
    """Convert raw values to the renderer y-axis unit, gated on NodeType.

    For absorbance-space NodeTypes (CS-55 ``_ABSORBANCE_SPACE_NODETYPES``
    — UVVIS / BASELINE / NORMALISED / SMOOTHED / PEAK_LIST), the "%T"
    branch applies ``100 · 10^(-A)`` with a defensive clip to [-10, 10].

    For every other NodeType (notably ``SECOND_DERIVATIVE``, whose
    ``arrays["absorbance"]`` field actually holds d²A/dλ² values),
    the helper is a no-op regardless of y-unit. Reason: the %T
    conversion is meaningful for absorbance values but corrupts d²A
    values (which are typically ~0.001 and can be negative, so the
    clip + ``100 · 10^(-A)`` mapping produces nonsense values that
    visually swamp the secondary axis). The secondary y-axis label
    already encodes the unit context post-CS-44/CS-55, so the toggle
    doesn't need to mutate derivative-space values.

    Phase 4ah fix for Phase 4u friction #9 ("`_absorbance_to_y`
    corrupts d²A on %T"). The NodeType-gated branch keeps the three
    ``_redraw`` call sites symmetric — the helper owns the rule.
    """
    if node_type not in _ABSORBANCE_SPACE_NODETYPES:
        return absorbance
    if y_unit == "%T":
        return 100.0 * np.power(10.0, -np.clip(absorbance, -10, 10))
    return absorbance


# Phase 4t (CS-43) — set of baseline modes whose ``compute_*``
# implements the floor-zero constraint. The "Floor at zero" toggle
# is enabled when the current mode is in this set, disabled
# otherwise. Today (Phase 4t) all six modes ship the constrained-
# fit code path, so the disabled state never fires in the default
# build — the constant remains as defensive scaffolding so a future
# new mode added to ``BASELINE_MODES`` without floor-zero coverage
# greys the toggle out automatically. Cross-ref: CS-37 + the BACKLOG
# entry "Floor-zero toggle disabled state for unsupported baseline
# modes (USER-FLAGGED)".
_FLOOR_ZERO_SUPPORTED_MODES: frozenset[str] = frozenset(
    uvvis_baseline.BASELINE_MODES
)

_FLOOR_ZERO_DISABLED_TOOLTIP: str = (
    "Floor-zero is not supported for this baseline mode."
)


# ── Multi-axis plot routing (Phase 4u, CS-44) ────────────────────────────────
# Phase 4t carry-forward friction #2: SECOND_DERIVATIVE values are
# typically 1/100x to 1/1000x the parent absorbance, so plotting them
# on a shared y-axis collapses the parent into a flat line or hides
# the derivative entirely. CS-44 routes each rendered node to one of
# three named axis roles. Today only "primary" and "secondary" are
# populated by the per-NodeType default table; "tertiary" is wired
# through the lazy axis-creation machinery so a future NodeType (or a
# future per-style override) can land as a one-line table edit.
#
# Per-NodeType default mapping. A NodeType absent from the dict
# defaults to "primary". The per-node override hook (Phase 4y, CS-50)
# lives at the front of ``_resolve_y_axis_role`` reading
# ``node.style.get("y_axis")``; per-NodeType remains the fallback when
# the override is None or malformed.
_AXIS_ROLES: tuple[str, ...] = ("primary", "secondary", "tertiary")

_DEFAULT_Y_AXIS_BY_NODETYPE: dict[NodeType, str] = {
    NodeType.UVVIS:             "primary",
    NodeType.BASELINE:          "primary",
    NodeType.NORMALISED:        "primary",
    NodeType.SMOOTHED:          "primary",
    NodeType.PEAK_LIST:         "primary",
    NodeType.SECOND_DERIVATIVE: "secondary",
}

# Phase 4ak (CS-62): mapping from the CS-44 Y-axis role keys
# (``primary`` / ``secondary`` / ``tertiary``) into the Plot Settings
# dialog's per-axis tab keys. Used by the renderer to read
# ``cfg["axes"][<tab_role>]["axis_label_override"]`` for each
# populated Y-axis, and by the plots-by-role enumerator that feeds
# the dialog's "Plots on this axis" lists.
_Y_AXIS_ROLE_TO_TAB: dict[str, str] = {
    "primary":   "primary_y",
    "secondary": "secondary_y",
    "tertiary":  "tertiary_y",
}

# X-unit-aware y-axis label for nodes routed to a non-primary role.
# Keyed by ``(NodeType, x_unit)``; the first node of a given NodeType
# placed on a non-primary role determines that role's label. Unknown
# (NodeType, x_unit) combinations return None and the role goes
# unlabelled.
_NON_PRIMARY_Y_LABEL: dict[tuple[NodeType, str], str] = {
    (NodeType.SECOND_DERIVATIVE, "nm"):   "d²A/dλ²",
    (NodeType.SECOND_DERIVATIVE, "cm-1"): "d²A/d(cm⁻¹)²",
    (NodeType.SECOND_DERIVATIVE, "eV"):   "d²A/dE²",
}

# Fractional x-position of the tertiary axis spine (matplotlib
# ``axes`` coordinate). Tunable later via a Plot Settings field; for
# now it is a module constant so a future settings row can promote
# it without changing the helper signatures. Typical matplotlib
# offset for a 3rd-axis stack is 1.10–1.15.
_TERTIARY_AXIS_OFFSET_FRAC: float = 1.12


def _resolve_y_axis_role(
    node_type: NodeType,
    style: Optional[Mapping[str, Any]] = None,
) -> str:
    """Return the axis role string for a node of ``node_type``.

    Resolution order (Phase 4y, CS-50):
    1. Per-style override: if ``style`` carries a ``"y_axis"`` whose
       value is one of :data:`_AXIS_ROLES`, return it. Any other value
       (``None``, missing key, malformed string) falls through.
    2. Per-NodeType default: looked up in
       :data:`_DEFAULT_Y_AXIS_BY_NODETYPE`; absent NodeTypes default
       to ``"primary"``.

    The ``style`` parameter is optional and defaults to ``None`` so
    every pre-CS-50 caller (overlay-axis resolvers in :meth:`_redraw`
    that operate on a NodeType-constant rather than a per-node style)
    keeps its exact pre-Phase-4y behaviour.
    """
    if style is not None:
        override = style.get("y_axis")
        if isinstance(override, str) and override in _AXIS_ROLES:
            return override
    return _DEFAULT_Y_AXIS_BY_NODETYPE.get(node_type, "primary")


def _resolve_non_primary_y_label(node_type: NodeType, x_unit: str) -> Optional[str]:
    """Return the y-axis label for a non-primary role, or ``None``.

    Looks up :data:`_NON_PRIMARY_Y_LABEL` by ``(node_type, x_unit)``.
    Returns ``None`` for any pair without a registered label so the
    caller can leave the role unlabelled rather than guessing.
    """
    return _NON_PRIMARY_Y_LABEL.get((node_type, x_unit))


def _axis_label_override(cfg: Mapping[str, Any], tab_role: str) -> str:
    """Return the per-axis label override string from ``cfg`` (Phase 4ak).

    ``tab_role`` is one of the Plot Settings dialog's per-axis tab
    keys (``primary_x``, ``secondary_x``, ``primary_y``,
    ``secondary_y``, ``tertiary_y``). Reads
    ``cfg["axes"][tab_role]["axis_label_override"]`` defensively —
    pre-Phase-4ak configs that never round-tripped through the
    dialog do not carry the ``axes`` sub-dict at all, so the
    fallback is the empty string (meaning "no override; let the
    auto/custom resolution downstream handle the label").
    """
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict):
            override = role_dict.get("axis_label_override", "")
            if isinstance(override, str):
                return override
    return ""


def _per_axis_range(
    cfg: Mapping[str, Any], tab_role: str, key: str,
) -> str:
    """Read ``cfg["axes"][tab_role][key]`` for ``range_lo`` / ``range_hi``.

    CS-64 (Phase 4am): both keys are StringVar-backed; an empty
    string means "no bound on this end". Defensive: pre-Phase-4am
    configs that lack the nested key return ``""``.
    """
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict):
            value = role_dict.get(key, "")
            if isinstance(value, str):
                return value
            # Tolerate non-str legacy values by coercing.
            return str(value)
    return ""


def _per_axis_autoscale(cfg: Mapping[str, Any], tab_role: str) -> bool:
    """Read ``cfg["axes"][tab_role]["autoscale"]`` (CS-64, Phase 4am).

    Default-True when missing. ``True`` makes the renderer ignore the
    per-axis range bounds; ``False`` means "clamp where bounds are
    non-empty".
    """
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict) and "autoscale" in role_dict:
            return bool(role_dict["autoscale"])
    return True


def _per_axis_scale(cfg: Mapping[str, Any], tab_role: str) -> str:
    """Read ``cfg["axes"][tab_role]["scale"]`` (CS-64, Phase 4am).

    Returns one of ``{"linear", "log"}``. Defaults to ``"linear"``
    when missing or when the stored value is not in the canonical
    set (defensive fallback for pre-Phase-4am configs).
    """
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict):
            value = role_dict.get("scale")
            if value in ("linear", "log"):
                return value
    return "linear"


def _parse_lim_str(text: str) -> "Optional[float]":
    """Parse a per-axis range Entry value (CS-64).

    Returns ``None`` for empty / whitespace-only / unparseable input —
    callers treat ``None`` as "no bound on this end". Mirrors the
    behaviour of :meth:`UVVisTab._parse_lim` but takes a raw string
    rather than a Tk variable.
    """
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except (TypeError, ValueError):
        return None


def _per_axis_tick_direction(cfg: Mapping[str, Any], tab_role: str) -> str:
    """Resolve the tick_direction for ``tab_role`` with legacy fallback.

    Phase 4ak (CS-62) moved tick_direction into ``cfg["axes"][<role>]``;
    a pre-migration ``_plot_config`` still carries the flat
    ``cfg["tick_direction"]`` key. The renderer reads through this
    helper so both shapes work seamlessly. Falls through to the
    factory default if neither shape registers a value.
    """
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict) and "tick_direction" in role_dict:
            return str(role_dict["tick_direction"])
    legacy = cfg.get("tick_direction")
    if legacy is not None:
        return str(legacy)
    return str(
        plot_settings_dialog._FACTORY_DEFAULTS["axes"][tab_role][
            "tick_direction"
        ]
    )


def _parse_tick_str(text: str) -> "Optional[float]":
    """Parse a per-axis tick-spacing Entry value (CS-65, Phase 4an).

    Returns ``None`` for empty / whitespace-only / unparseable input AND
    for non-positive values — callers treat ``None`` as "let matplotlib
    pick the locator". Negative or zero spacings are silently rejected
    because ``MultipleLocator`` would raise; rejecting in the helper
    keeps the renderer free of try/except cluttering.
    """
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        value = float(stripped)
    except (TypeError, ValueError):
        return None
    if value <= 0.0 or not np.isfinite(value):
        return None
    return value


def _per_axis_tick_major(
    cfg: Mapping[str, Any], tab_role: str,
) -> "Optional[float]":
    """Read ``cfg["axes"][tab_role]["tick_major"]`` (CS-65, Phase 4an).

    Returns the parsed float spacing, or ``None`` for "let matplotlib's
    auto-locator decide". Defensive: pre-Phase-4an configs without the
    nested key return ``None``.
    """
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict):
            value = role_dict.get("tick_major", "")
            if isinstance(value, str):
                return _parse_tick_str(value)
    return None


def _per_axis_tick_minor(
    cfg: Mapping[str, Any], tab_role: str,
) -> "Optional[float]":
    """Read ``cfg["axes"][tab_role]["tick_minor"]`` (CS-65, Phase 4an)."""
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict):
            value = role_dict.get("tick_minor", "")
            if isinstance(value, str):
                return _parse_tick_str(value)
    return None


def _per_axis_grid(cfg: Mapping[str, Any], tab_role: str) -> bool:
    """Read ``cfg["axes"][tab_role]["grid_show"]`` (CS-65, Phase 4an).

    Default-True for ``primary_x`` / ``primary_y`` and default-False for
    the three non-primary roles when the key is missing. Renderer
    currently consults this helper only for the two primary roles (twin
    Y axes share the primary's grid); the per-role defaults keep the
    Plot Settings checkbox visually consistent with what the renderer
    actually paints when a config arrives without the key set.
    """
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict) and "grid_show" in role_dict:
            return bool(role_dict["grid_show"])
    return tab_role in ("primary_x", "primary_y")


def _per_axis_color(cfg: Mapping[str, Any], tab_role: str) -> str:
    """Read ``cfg["axes"][tab_role]["axis_color"]`` (CS-65, Phase 4an).

    Returns a hex colour string. Defaults to ``"#000000"`` when missing
    or when the stored value is not a string. Renderer applies the
    colour to the per-role spine + tick params + axis-label colour at
    each axis's per-call-site.
    """
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict):
            value = role_dict.get("axis_color")
            if isinstance(value, str) and value:
                return value
    return "#000000"


# ── CS-69 (Phase 4aq) custom-ticks helpers ───────────────────────────────────
# Per-axis ``custom_ticks`` is a comma-separated list of explicit tick
# positions (e.g. ``"300, 400, 500, 700, 900"``). Non-empty wins outright
# over ``tick_major`` on the role's MAJOR ticks via :class:`FixedLocator`;
# ``tick_minor`` (CS-65) is unaffected. The motivating use case is the
# wavelength↔energy linked secondary X axis (B-005) where
# ``1e7 / x`` / ``_HC_NM_EV / x`` make uniform-spacing
# ``MultipleLocator(value)`` ticks unrepresentative — users want named
# wavelengths in nm. Schema key is uniform across every per-axis role
# (D6b lock); a non-secondary-X axis simply gets the same treatment if
# its ``custom_ticks`` ever parses to a non-empty tuple.
def _parse_custom_ticks_str(text: str) -> "Optional[tuple[float, ...]]":
    """Parse a per-axis ``custom_ticks`` Entry value (CS-69, Phase 4aq).

    Splits on commas, strips whitespace, parses each token as ``float``,
    silently drops empty / non-numeric / non-finite tokens. Returns
    ``None`` for empty / whitespace-only / all-invalid input (callers
    treat ``None`` as "no FixedLocator override; fall through to
    ``tick_major``"). A non-empty tuple of finite floats triggers the
    override. The silent-drop policy mirrors :func:`_parse_tick_str`
    (CS-65) for consistency across the per-axis ladder.
    """
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None
    out: list[float] = []
    for token in stripped.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = float(token)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(value):
            continue
        out.append(value)
    if not out:
        return None
    return tuple(out)


def _per_axis_custom_ticks(
    cfg: Mapping[str, Any], tab_role: str,
) -> str:
    """Read ``cfg["axes"][tab_role]["custom_ticks"]`` (CS-69, Phase 4aq).

    Returns the raw string (caller passes through
    :func:`_parse_custom_ticks_str`). Defensive: pre-Phase-4aq configs
    without the nested key return ``""`` — equivalent to "no override",
    so the renderer falls through to ``tick_major`` automatically. The
    backward-compat path lets a saved .ptmg project load cleanly
    without bumping :data:`project_io.PTMG_FORMAT_VERSION` (CS-46).
    """
    axes = cfg.get("axes")
    if isinstance(axes, dict):
        role_dict = axes.get(tab_role)
        if isinstance(role_dict, dict):
            value = role_dict.get("custom_ticks", "")
            if isinstance(value, str):
                return value
    return ""


def _apply_major_locator(
    axis_obj: Any, cfg: Mapping[str, Any], tab_role: str,
) -> None:
    """Apply the major-tick locator for ``tab_role`` (CS-69, Phase 4aq).

    ``custom_ticks`` wins outright when it parses to a non-empty tuple
    — applied as :class:`~matplotlib.ticker.FixedLocator`. Otherwise
    ``tick_major`` is applied as
    :class:`~matplotlib.ticker.MultipleLocator(value)` when it parses
    to a positive float (CS-65). Empty / all-invalid on both keys
    leaves matplotlib's auto-locator in place — preserving the
    pre-CS-65 default behaviour.

    ``axis_obj`` is one of ``ax.xaxis`` / ``ax.yaxis`` /
    ``twin_ax.yaxis`` / ``sec.xaxis``. The helper is a single point of
    truth for the four per-role call sites in :meth:`UVVisTab._redraw`
    so a future tick-locator key only touches this function.
    """
    custom = _parse_custom_ticks_str(_per_axis_custom_ticks(cfg, tab_role))
    if custom is not None:
        axis_obj.set_major_locator(FixedLocator(list(custom)))
        return
    major = _per_axis_tick_major(cfg, tab_role)
    if major is not None:
        axis_obj.set_major_locator(MultipleLocator(major))


def _enumerate_plots_by_role(
    spectrum_nodes: Iterable[DataNode],
    second_derivative_nodes: Iterable[DataNode],
    peak_list_nodes: Iterable[DataNode],
    *,
    secondary_x_active: bool,
) -> dict[str, tuple[str, ...]]:
    """Group plottable node labels by Plot Settings axis-tab key (Phase 4ak).

    Builds the ``plots_by_role`` mapping the unified Plot Config
    dialog consumes for its per-axis "Plots on this axis" lists.
    Every visible spectrum-shaped node, second-derivative node, and
    peak-list node feeds in:

    * ``primary_x`` lists every visible plot — they all share the
      bottom x-axis regardless of which y-axis they sit on.
    * ``secondary_x`` mirrors ``primary_x`` when the wavelength↔
      energy twin axis is active, empty otherwise.
    * ``primary_y`` / ``secondary_y`` / ``tertiary_y`` route via
      :func:`_resolve_y_axis_role`, which honours each node's
      ``style["y_axis"]`` override (CS-50).

    Invisible (``style.get("visible", True) == False``) or
    discarded nodes are skipped silently — they don't render, so
    they don't appear in the dialog's inventory either.
    """
    primary_x: list[str] = []
    y_buckets: dict[str, list[str]] = {
        "primary": [],
        "secondary": [],
        "tertiary": [],
    }

    def _consume(node: DataNode) -> None:
        style = getattr(node, "style", None) or {}
        if not style.get("visible", True):
            return
        label = node.label or "(unnamed)"
        primary_x.append(label)
        y_role = _resolve_y_axis_role(node.type, style)
        y_buckets.setdefault(y_role, y_buckets["primary"]).append(label)

    for node in spectrum_nodes:
        _consume(node)
    for node in second_derivative_nodes:
        _consume(node)
    for node in peak_list_nodes:
        _consume(node)

    return {
        "primary_x":   tuple(primary_x),
        "secondary_x": tuple(primary_x) if secondary_x_active else (),
        "primary_y":   tuple(y_buckets["primary"]),
        "secondary_y": tuple(y_buckets["secondary"]),
        "tertiary_y":  tuple(y_buckets["tertiary"]),
    }


# Phase 4ad (CS-55): role-agnostic y-axis label resolution.
#
# CS-44 + CS-50 introduced multi-axis routing and a per-style override;
# the resulting bug (Phase 4ac friction #1, USER-FLAGGED) was that the
# renderer hard-coded the primary axis's ylabel from y-unit only, so
# routing Absorbance to "secondary" left the "Absorbance" label on the
# (now empty) primary side, and routing SECOND_DERIVATIVE to "primary"
# kept the "Absorbance" label on a derivative-valued axis. The fix
# below is structural: label dimensionality varies by NodeType class,
# not by axis role. The renderer walks every populated role's first
# node through ``_resolve_y_axis_label`` and labels each axis from the
# returned text (with ylabel_mode = "custom" still winning for primary).
#
# Absorbance-space NodeTypes label from y-unit (A vs %T), independent
# of x-unit and role. Derivative-space NodeTypes label from x-unit via
# the existing CS-44 ``_NON_PRIMARY_Y_LABEL`` table (now consulted for
# both primary and non-primary roles).
_ABSORBANCE_SPACE_NODETYPES: frozenset[NodeType] = frozenset({
    NodeType.UVVIS,
    NodeType.BASELINE,
    NodeType.NORMALISED,
    NodeType.SMOOTHED,
    NodeType.PEAK_LIST,
})

_ABSORBANCE_Y_LABEL: dict[str, str] = {
    "A":  "Absorbance",
    "%T": "Transmittance (%)",
}


def _resolve_y_axis_label(
    node_type: NodeType,
    x_unit: str,
    y_unit: str,
) -> Optional[str]:
    """Return the y-axis label for a node, regardless of axis role.

    Resolution:

    1. If ``node_type`` is in :data:`_ABSORBANCE_SPACE_NODETYPES`,
       return ``_ABSORBANCE_Y_LABEL[y_unit]`` (or ``None`` if the
       y-unit is unknown).
    2. Otherwise look up ``(node_type, x_unit)`` in
       :data:`_NON_PRIMARY_Y_LABEL` (the existing CS-44 table) and
       return its value (or ``None`` for unregistered pairs).

    The helper is consulted for every populated axis role in the
    Phase 4ad renderer pass; the role is intentionally NOT part of the
    key, because label text depends on the NodeType's nature, not on
    which side of the figure it ended up on.
    """
    if node_type in _ABSORBANCE_SPACE_NODETYPES:
        return _ABSORBANCE_Y_LABEL.get(y_unit)
    return _NON_PRIMARY_Y_LABEL.get((node_type, x_unit))


class UVVisTab(tk.Frame):
    """UV/Vis/NIR import, display and analysis panel."""

    def __init__(
        self,
        parent,
        add_scan_fn: Optional[Callable] = None,
        graph: Optional[ProjectGraph] = None,
    ):
        super().__init__(parent)
        self._add_scan_fn: Optional[Callable] = add_scan_fn

        # ProjectGraph: passed in by the host (binah.py once integrated)
        # or constructed locally as a tab-private graph until the host
        # is wired up. The tab routes every mutation through graph
        # methods.
        self._graph: ProjectGraph = graph if graph is not None else ProjectGraph()

        # ── Display options ───────────────────────────────────────────────────
        self._x_unit      = tk.StringVar(value="nm")
        self._x_unit_prev = "nm"
        self._y_unit      = tk.StringVar(value="A")
        self._show_nm_axis = tk.BooleanVar(value=True)
        # Phase 4ao (CS-67) retired the global ``_show_baseline_curves``
        # BooleanVar and its top-bar Checkbutton. Baseline-curve
        # visibility is now per-node via CS-36's
        # ``style["show_baseline_curve"]`` (default True), surfaced as
        # the per-row ``~`` toggle in ScanTreeWidget. The renderer's
        # outer global guard is removed; the per-node filter inside
        # the overlay loop is the single source of truth.

        # ── Axis limits (empty string = auto) ────────────────────────────────
        self._xlim_lo = tk.StringVar(value="")
        self._xlim_hi = tk.StringVar(value="")
        self._ylim_lo = tk.StringVar(value="")
        self._ylim_hi = tk.StringVar(value="")

        # ── Plot Settings configuration (CS-06 / CS-14) ──────────────────────
        # Tab-private dict: fonts, grid, background, legend show/position,
        # tick direction, title/X-label/Y-label text and modes. Initialised
        # from the in-process user defaults if any have been saved this
        # session, falling back to the factory defaults. ``_redraw`` reads
        # from this dict; the ⚙ Plot Settings dialog mutates it in place
        # on Apply. Per Phase 4a friction #4 this is tab-private state, not
        # graph state.
        _src = (
            plot_settings_dialog._USER_DEFAULTS
            or plot_settings_dialog._FACTORY_DEFAULTS
        )
        self._plot_config: dict = copy.deepcopy(dict(_src))

        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    #  Graph helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _uvvis_nodes(self) -> List[DataNode]:
        """Return the UVVIS DataNodes the tab considers "live".

        Live = state != DISCARDED *and* ``active`` is True. The list
        preserves insertion order (Python 3.7+ dict is ordered) so the
        sidebar's row order is deterministic across rebuilds.

        Strictly UVVIS-typed (does not include derived BASELINE nodes);
        callers that want to iterate every spectrum the tab renders
        should use ``_spectrum_nodes`` instead.
        """
        out: List[DataNode] = []
        for node in self._graph.nodes_of_type(NodeType.UVVIS, state=None):
            if node.state == NodeState.DISCARDED:
                continue
            if not node.active:
                continue
            out.append(node)
        return out

    def _spectrum_nodes(self) -> List[DataNode]:
        """Return every spectrum-shaped DataNode the tab considers live.

        Spectrum-shaped today means UVVIS, BASELINE, NORMALISED, or
        SMOOTHED: all four carry ``arrays["wavelength_nm"]`` +
        ``arrays["absorbance"]`` and render through the same
        matplotlib code path. ``_redraw`` and the *shared* subject
        combobox at the top of the left pane (CS-22, Phase 4k)
        iterate this helper. The walk is type-keyed (UVVIS first,
        then BASELINE, then NORMALISED, then SMOOTHED) so a parent
        typically appears above its derivatives in the sidebar /
        subject list when the dict ordering is preserved (Phase 4g
        widening from ``[UVVIS, BASELINE, NORMALISED]`` to include
        SMOOTHED).
        """
        out: List[DataNode] = []
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED, NodeType.SMOOTHED):
            for node in self._graph.nodes_of_type(ntype, state=None):
                if node.state == NodeState.DISCARDED:
                    continue
                if not node.active:
                    continue
                out.append(node)
        return out

    def _peak_list_nodes(self) -> List[DataNode]:
        """Return the PEAK_LIST DataNodes the tab considers live.

        PEAK_LIST nodes are annotation overlays (CS-19, Phase 4h) and
        live in a separate iteration from ``_spectrum_nodes`` because
        their array shape differs (``peak_wavelengths_nm`` /
        ``peak_absorbances`` instead of the curve-shaped
        ``wavelength_nm`` / ``absorbance``) and they are not candidate
        parents for baseline / normalisation / smoothing / further
        peak picking.
        """
        out: List[DataNode] = []
        for node in self._graph.nodes_of_type(NodeType.PEAK_LIST, state=None):
            if node.state == NodeState.DISCARDED:
                continue
            if not node.active:
                continue
            out.append(node)
        return out

    def _second_derivative_nodes(self) -> List[DataNode]:
        """Return the SECOND_DERIVATIVE DataNodes the tab considers live.

        SECOND_DERIVATIVE nodes (CS-20, Phase 4i) carry the curve
        schema (``wavelength_nm`` / ``absorbance`` keys, where the
        latter holds d²A/dλ² values) so the renderer plots them with
        the same code path as UVVIS / BASELINE / NORMALISED /
        SMOOTHED. They live in their own iteration because the
        renderer routes them to the secondary y-axis under CS-44
        (``_DEFAULT_Y_AXIS_BY_NODETYPE[SECOND_DERIVATIVE] ==
        "secondary"``); concatenating them into ``_spectrum_nodes``
        would double-render once the renderer iterates both helpers
        explicitly (see ``_redraw``).

        Phase 4x history note (CS-49): before Phase 4x this helper's
        existence also served the panel-side "shared combobox does
        not surface a derivative" contract — the locked smoothing /
        baseline / normalise / peak-picking panels all rejected
        SECOND_DERIVATIVE, so surfacing one would silently refuse on
        Apply. Phase 4x widened ``SmoothingPanel.ACCEPTED_PARENT_TYPES``
        to include SECOND_DERIVATIVE, and ``_refresh_shared_subjects``
        now unions both helpers so derivative parents do appear in
        the combobox. The renderer-side separation (this helper) is
        unchanged.
        """
        out: List[DataNode] = []
        for node in self._graph.nodes_of_type(NodeType.SECOND_DERIVATIVE,
                                              state=None):
            if node.state == NodeState.DISCARDED:
                continue
            if not node.active:
                continue
            out.append(node)
        return out

    def _has_existing_load(self, source_file: str, label: str) -> bool:
        """Skip duplicates when the user reloads a file already in the graph."""
        for node in self._graph.nodes_of_type(NodeType.UVVIS, state=None):
            md = node.metadata
            if (md.get("source_file") == source_file
                    and node.label == label
                    and node.state != NodeState.DISCARDED):
                return True
        return False

    # ══════════════════════════════════════════════════════════════════════════
    #  Layout
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        top = tk.Frame(self, bd=1, relief=tk.GROOVE, padx=4, pady=3)
        top.pack(side=tk.TOP, fill=tk.X)
        self._build_toolbar(top)

        lim_bar = tk.Frame(self, bd=1, relief=tk.GROOVE, padx=4, pady=2)
        lim_bar.pack(side=tk.TOP, fill=tk.X)
        self._build_limit_bar(lim_bar)

        body = tk.PanedWindow(self, orient=tk.HORIZONTAL,
                              sashwidth=5, sashrelief=tk.RAISED)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ARCHITECTURE.md §3: three-zone layout — left panel (engine /
        # processing controls), centre (matplotlib figure), right
        # (ScanTreeWidget). The left panel landed in Phase 4c (CS-07
        # §"UV/Vis left panel" + CS-15) hosting baseline correction.
        left_pane = tk.Frame(body, bd=1, relief=tk.SUNKEN)
        body.add(left_pane, minsize=220)
        self._build_left_panel(left_pane)

        plot_pane = tk.Frame(body)
        body.add(plot_pane, minsize=400)
        self._build_plot(plot_pane)

        sidebar_pane = tk.Frame(body, bd=1, relief=tk.SUNKEN)
        # Phase 4w (CS-47): pull the sidebar floor from the widget
        # module so the responsive helper's smallest threshold and
        # the PanedWindow's hard minimum stay in lock-step. If the
        # widget bumps its floor in a later phase, this minsize
        # follows automatically.
        body.add(sidebar_pane, minsize=_SIDEBAR_MIN_WIDTH_PX)
        self._build_sidebar(sidebar_pane)
        # Cache the PanedWindow + sidebar pane handles so
        # ``_calibrate_sidebar_width`` can place the sash without
        # reaching back through the widget tree on every call.
        self._body_paned: tk.PanedWindow = body
        self._sidebar_pane: tk.Frame = sidebar_pane
        # Phase 4w (CS-47): one-shot calibration flag. Set to True
        # after the first ``_calibrate_sidebar_width`` runs so the
        # user's manual sash-drags persist across rebuilds.
        self._sidebar_calibrated: bool = False

        # Drive plot redraws off graph events. Dialog and row mutations
        # go through ``graph.set_style`` → ``NODE_STYLE_CHANGED`` which
        # this handler translates into a ``_redraw``. Lifetime is the
        # tab's: unsubscribed automatically on ``<Destroy>``.
        self._graph.subscribe(self._on_graph_event)
        self.bind("<Destroy>", self._on_destroy_unsubscribe, add="+")

        # Phase 4w (CS-47): defer the first sidebar calibration to
        # idle time so the PanedWindow has had a chance to lay out
        # its three panes. Without ``after_idle`` the geometry
        # measurements return zero and the sash placement is a
        # no-op.
        try:
            self.after_idle(self._calibrate_sidebar_width)
        except tk.TclError:
            pass

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self, bar):
        F9 = ("", 9)

        tk.Button(bar, text="📂 Load File…", font=("", 9, "bold"),
                  bg="#003d7a", fg="white", activebackground="#0055aa",
                  command=self._load_files).pack(side=tk.LEFT, padx=(2, 6))

        def _sep():
            ttk.Separator(bar, orient=tk.VERTICAL).pack(
                side=tk.LEFT, fill=tk.Y, padx=6)

        _sep()
        tk.Label(bar, text="X:", font=F9).pack(side=tk.LEFT)
        for lbl, val in [("nm", "nm"), ("cm⁻¹", "cm-1"), ("eV", "eV")]:
            tk.Radiobutton(bar, text=lbl, variable=self._x_unit, value=val,
                           command=self._on_unit_change, font=F9,
                           ).pack(side=tk.LEFT)

        _sep()
        tk.Label(bar, text="Y:", font=F9).pack(side=tk.LEFT)
        for lbl, val in [("Abs", "A"), ("%T", "%T")]:
            tk.Radiobutton(bar, text=lbl, variable=self._y_unit, value=val,
                           command=self._redraw, font=F9,
                           ).pack(side=tk.LEFT)

        _sep()
        self._nm_cb = tk.Checkbutton(bar, text="λ(nm) axis",
                                     variable=self._show_nm_axis,
                                     command=self._redraw, font=F9)
        self._nm_cb.pack(side=tk.LEFT, padx=2)

        # Phase 4ao (CS-67) retired the global "Baseline curves"
        # Checkbutton — CS-36's per-node ``~`` row toggle is now the
        # single source of truth for dashed-overlay visibility.

        # Phase 4n CS-27 retired the top-bar "+ Add to TDDFT Overlay"
        # bulk button. Each ScanTreeWidget row now carries a per-row
        # → icon that calls ``_send_node_to_compare(node_id)`` —
        # disabled on provisional rows and when no Compare host is
        # connected (mirrors the old button's gate).
        _sep()
        # ⚙ Plot Settings (CS-06): opens the unified Plot Settings
        # dialog for this tab.
        self._plot_settings_btn = tk.Button(
            bar, text="⚙ Plot Settings", font=F9,
            command=self._open_plot_settings,
        )
        self._plot_settings_btn.pack(side=tk.LEFT, padx=2)

        self._status_lbl = tk.Label(bar, text="Load a UV/Vis file to begin.",
                                    fg="gray", font=("", 8))
        self._status_lbl.pack(side=tk.LEFT, padx=10)

    # ── Limit bar ─────────────────────────────────────────────────────────────

    def _build_limit_bar(self, bar):
        F9 = ("", 9)
        FC = ("Courier", 9)

        def _entry(var, width=8):
            e = tk.Entry(bar, textvariable=var, width=width, font=FC)
            e.bind("<Return>",   lambda _: self._redraw())
            e.bind("<FocusOut>", lambda _: self._redraw())
            return e

        def _sep():
            ttk.Separator(bar, orient=tk.VERTICAL).pack(
                side=tk.LEFT, fill=tk.Y, padx=8)

        tk.Label(bar, text="X:", font=F9).pack(side=tk.LEFT)
        _entry(self._xlim_lo).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(bar, text="→", font=F9).pack(side=tk.LEFT, padx=1)
        _entry(self._xlim_hi).pack(side=tk.LEFT)
        tk.Button(bar, text="Auto X", font=("", 8),
                  command=self._auto_x).pack(side=tk.LEFT, padx=(4, 0))

        _sep()

        tk.Label(bar, text="Y:", font=F9).pack(side=tk.LEFT)
        _entry(self._ylim_lo).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(bar, text="→", font=F9).pack(side=tk.LEFT, padx=1)
        _entry(self._ylim_hi).pack(side=tk.LEFT)
        tk.Button(bar, text="Auto Y", font=("", 8),
                  command=self._auto_y).pack(side=tk.LEFT, padx=(4, 0))

    # ── Sidebar (right pane: ScanTreeWidget) ──────────────────────────────────

    def _build_sidebar(self, parent):
        """Construct the right-pane sidebar around a ``ScanTreeWidget``.

        The widget filters to ``NodeType.UVVIS``; its row controls
        write through ``graph.set_style`` (CS-04), and the gear button
        delegates to the unified style dialog (CS-05) via
        ``style_dialog_cb``. Phase 4n CS-27 wires
        ``send_to_compare_cb`` to ``_send_node_to_compare`` so the
        per-row → icon pushes a single spectrum into the TDDFT
        overlay (replacing the legacy bulk top-bar button).
        ``export_cb`` is wired to ``_on_export_node`` for the row
        Export… gesture (CS-17, Phase 4f).
        """
        tk.Label(parent, text="Loaded Spectra",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        self._scan_tree = ScanTreeWidget(
            parent,
            self._graph,
            [NodeType.UVVIS, NodeType.BASELINE,
             NodeType.NORMALISED, NodeType.SMOOTHED,
             NodeType.PEAK_LIST, NodeType.SECOND_DERIVATIVE],
            redraw_cb=self._redraw,
            send_to_compare_cb=self._send_node_to_compare,
            style_dialog_cb=self._open_style_dialog_for_node,
            export_cb=self._on_export_node,
        )
        self._scan_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    # ── Sidebar width calibration (Phase 4w CS-47) ─────────────────────────────

    # Cap on the calibrated sidebar width so very long labels can't
    # take half the window on first paint. ~480 px holds roughly 64
    # characters of label plus the always-visible row chrome — past
    # that the user is better served by manual sash-dragging or by
    # editing the labels themselves.
    _SIDEBAR_MAX_CALIBRATED_PX: int = 480

    def _calibrate_sidebar_width(self) -> None:
        """Auto-size the sidebar pane to fit the widest label on first paint.

        Phase 4w (CS-47). Computes a target sidebar width from
        ``ScanTreeWidget.widest_label_pixel_width()`` plus the
        always-visible row overhead (``_label_overhead_px``) and
        moves sash 2 (the rightmost sash, between plot pane and
        sidebar pane) so the sidebar is exactly that wide. Idempotent
        but one-shot: ``_sidebar_calibrated`` flips True after the
        first successful call so subsequent rebuilds preserve any
        manual sash drag the user has applied.

        Bounds: clamped to ``[_SIDEBAR_MIN_WIDTH_PX,
        _SIDEBAR_MAX_CALIBRATED_PX]`` so an empty graph (zero widest
        label) still gets at least the floor and a 600-char label
        doesn't push the plot pane out of the window. If the
        PanedWindow geometry isn't realised yet, the call bails
        silently — the user's drag will still work whenever they
        first try.
        """
        if self._sidebar_calibrated:
            return
        try:
            paned = self._body_paned
            sidebar_pane = self._sidebar_pane
            scan_tree = self._scan_tree
        except AttributeError:
            return
        try:
            paned_width = paned.winfo_width()
        except tk.TclError:
            return
        if paned_width <= 1:
            # Geometry hasn't settled. Try again on the next idle
            # tick — common when the tab is constructed but not yet
            # mapped (the test harness, for instance).
            try:
                self.after(50, self._calibrate_sidebar_width)
            except tk.TclError:
                pass
            return

        widest_label_px = scan_tree.widest_label_pixel_width()
        overhead_px = scan_tree._label_overhead_px()
        target = widest_label_px + overhead_px
        target = max(_SIDEBAR_MIN_WIDTH_PX, target)
        target = min(self._SIDEBAR_MAX_CALIBRATED_PX, target)
        # The sash sits at x = paned_width - target; the sidebar
        # pane occupies the slice from there to the right edge.
        sash_x = max(0, paned_width - target)
        try:
            paned.sash_place(2, sash_x, 0)
        except tk.TclError:
            return
        self._sidebar_calibrated = True

    # ── Left panel (baseline + normalisation + smoothing + peak picking
    #    + second derivative,
    #    CS-07 + CS-15 + CS-16 + CS-18 + CS-19 + CS-20) ──

    def _build_left_panel(self, parent):
        """Construct the left panel with processing controls.

        Per CS-07 §"UV/Vis left panel" the left panel hosts the
        user-initiated UV/Vis operations. Phase 4k (CS-22) introduces
        a shared "Spectrum:" combobox at the top of the pane (above
        every CollapsibleSection); the user picks a subject once and
        every operation panel + the inline baseline section adopts
        it via ``set_subject``. Each panel exposes
        ``ACCEPTED_PARENT_TYPES`` and disables its Apply button when
        the shared selection isn't a valid parent for that op.

        * **Baseline correction** (CS-15, Phase 4c) — inline section
          with a four-mode baseline combobox (linear / polynomial /
          spline / rubberband), conditional parameter rows, and an
          "Apply Baseline" button. Accepts UVVIS / BASELINE parents.
        * **Normalisation** (CS-16, Phase 4e) — ``NormalisationPanel``
          subwidget with a two-mode combobox (peak / area), per-mode
          window entries, and an "Apply Normalisation" button.
          Accepts UVVIS / BASELINE / NORMALISED parents.
        * **Smoothing** (CS-18, Phase 4g) — ``SmoothingPanel`` with
          a two-mode combobox (savgol / moving_avg), per-mode
          parameter rows, and an "Apply Smoothing" button. Accepts
          UVVIS / BASELINE / NORMALISED / SMOOTHED parents.
        * **Peak picking** (CS-19, Phase 4h) — ``PeakPickingPanel``
          with a two-mode combobox (prominence / manual), per-mode
          parameter rows, and an "Apply Peak Picking" button. Each
          Apply gesture creates a provisional ``PEAK_LIST``
          annotation node rendered as scatter on the parent curve.
          Accepts UVVIS / BASELINE / NORMALISED / SMOOTHED parents.
        * **Second derivative** (CS-20, Phase 4i) —
          ``SecondDerivativePanel`` with two parameter spinboxes
          (window length + poly order) and an "Apply Second
          Derivative" button. Single algorithm (Savitzky-Golay with
          deriv=2). Accepts UVVIS / BASELINE / NORMALISED / SMOOTHED
          parents.

        Each Apply gesture creates one provisional OperationNode +
        DataNode pair; the user commits or discards via the
        ``ScanTreeWidget`` on the right.

        Phase 4j (CS-21) wraps every section in a
        :class:`CollapsibleSection` so users can hide the panels they
        are not currently using and reclaim vertical space. All five
        sections start collapsed; clicking the chevron header strip
        toggles. Per-section state is held in each section's own
        ``tk.BooleanVar`` and is not persisted to project files this
        phase (Phase 8 concern).
        """
        F9 = ("", 9)
        FC = ("Courier", 9)

        tk.Label(parent, text="Processing",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        # ── Shared subject combobox (CS-22, Phase 4k) ────────────────────
        # USER-FLAGGED end of Phase 4j: the per-panel "Spectrum:"
        # combobox felt redundant. Lifting it here means the user picks
        # the spectrum once, then expands the section for whichever
        # operation they want to apply. The combobox is always visible,
        # above every CollapsibleSection. Each panel exposes
        # ``set_subject`` + ``ACCEPTED_PARENT_TYPES`` (CS-22) so its
        # Apply button is disabled when the shared selection isn't a
        # valid parent for that op.
        shared_frame = tk.Frame(parent)
        shared_frame.pack(fill=tk.X, padx=4, pady=(0, 2))
        tk.Label(shared_frame, text="Spectrum:",
                 font=F9).pack(anchor="w")
        self._shared_subject = tk.StringVar(value="")
        self._shared_subject_map: dict[str, str] = {}
        self._shared_subject_cb = ttk.Combobox(
            shared_frame, textvariable=self._shared_subject,
            state="readonly", font=F9, width=24,
        )
        self._shared_subject_cb.pack(fill=tk.X)
        # Whenever the user picks a new subject (or _refresh repopulates
        # the values), fan it out to every panel + the inline baseline
        # gate.
        self._shared_subject.trace_add(
            "write", lambda *_: self._on_shared_subject_changed())

        # ── Baseline section (CS-15, Phase 4c) ───────────────────────────
        # Inline section — no panel subwidget. The widgets pack into
        # the CollapsibleSection's body frame; everything else
        # (Tk vars, refresh callbacks) stays on the tab.
        self._baseline_section = CollapsibleSection(
            parent, title="Baseline correction", expanded=False)
        self._baseline_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        bl_body = self._baseline_section.body

        # Phase 4k: the baseline section's inline subject combobox is
        # gone — the shared combobox above the sections is the source
        # of truth. The resolved id lives on the tab as
        # ``self._baseline_subject_id`` (set by
        # ``_on_shared_subject_changed``); ``_apply_baseline_btn`` is
        # disabled when the shared selection isn't a UVVIS / BASELINE
        # parent.
        self._baseline_subject_id: Optional[str] = None
        # Phase 4x widening (CS-49) — SMOOTHED joins the accepted
        # set so users can baseline-correct a smoothed spectrum.
        # Closes the user-flagged Phase 4w friction #1 ("Cannot do
        # baseline correction from a smoothed spectrum"). The math
        # is type-agnostic: every accepted parent carries
        # ``arrays["wavelength_nm"]`` + ``arrays["absorbance"]`` and
        # the baseline solver feeds those arrays in regardless of
        # which op produced them. The dashed-overlay helper
        # (``uvvis_baseline.compute_baseline_curve``) walks
        # parent.absorbance - child.absorbance, which is also
        # type-agnostic.
        #
        # NORMALISED is intentionally NOT added in this phase —
        # baseline-after-normalisation re-shifts the chosen
        # amplitude scale, and the user has not flagged the gap.
        # Audit-time finding documented in BACKLOG (Phase 4x
        # friction). PEAK_LIST stays excluded by array-shape
        # mismatch.
        self._BASELINE_ACCEPTED_PARENT_TYPES: tuple = (
            NodeType.UVVIS, NodeType.BASELINE, NodeType.SMOOTHED,
        )

        # Baseline mode.
        mode_frame = tk.Frame(bl_body)
        mode_frame.pack(fill=tk.X, padx=4, pady=(6, 2))
        tk.Label(mode_frame, text="Baseline mode:", font=F9).pack(anchor="w")
        self._baseline_mode = tk.StringVar(value="linear")
        self._baseline_mode_cb = ttk.Combobox(
            mode_frame, textvariable=self._baseline_mode,
            values=list(uvvis_baseline.BASELINE_MODES),
            state="readonly", font=F9, width=24,
        )
        self._baseline_mode_cb.pack(fill=tk.X)
        self._baseline_mode.trace_add(
            "write", lambda *_: self._refresh_baseline_param_rows())
        # Phase 4t (CS-43) — keep the "Floor at zero" toggle's
        # state in sync with the active mode. Two callbacks fire on
        # the same trace; ordering does not matter (they don't read
        # each other's state).
        self._baseline_mode.trace_add(
            "write", lambda *_: self._refresh_floor_zero_state())

        # Per-mode parameter Tk vars (kept on the tab so values
        # survive mode flips). String entries default to empty so the
        # user is forced to enter window endpoints explicitly.
        self._baseline_anchor_lo = tk.StringVar(value="")
        self._baseline_anchor_hi = tk.StringVar(value="")
        self._baseline_poly_order = tk.IntVar(value=2)
        self._baseline_fit_lo = tk.StringVar(value="")
        self._baseline_fit_hi = tk.StringVar(value="")
        self._baseline_spline_anchors = tk.StringVar(value="")  # comma-sep nm
        # CS-24 (Phase 4m) scattering mode: power-law c · λ^(-n).
        # ``_baseline_scattering_n`` defaults to "4" (Rayleigh); the
        # ``_baseline_scattering_fit_n`` BooleanVar, when checked,
        # makes ``_collect_baseline_params`` emit ``params["n"]="fit"``
        # so the helper recovers n alongside the amplitude.
        self._baseline_scattering_n = tk.StringVar(value="4")
        self._baseline_scattering_fit_n = tk.BooleanVar(value=False)
        self._baseline_scattering_fit_lo = tk.StringVar(value="")
        self._baseline_scattering_fit_hi = tk.StringVar(value="")

        # CS-37 (Phase 4s) — universal "Floor at zero" toggle. Shown for
        # every mode (the param round-trips on every BASELINE
        # OperationNode); the constrained-fit code path is implemented
        # for scattering / scattering+offset / rubberband, and raises
        # a clear ValueError for linear / polynomial / spline (per the
        # per-mode roadmap in BACKLOG).
        self._baseline_floor_zero = tk.BooleanVar(value=False)
        floor_frame = tk.Frame(bl_body)
        floor_frame.pack(fill=tk.X, padx=4, pady=(2, 0))
        self._baseline_floor_zero_cb = tk.Checkbutton(
            floor_frame, text="Floor at zero",
            variable=self._baseline_floor_zero, font=F9,
        )
        self._baseline_floor_zero_cb.pack(anchor="w")
        # Phase 4t (CS-42 + CS-43) — Tooltip on the "Floor at zero"
        # checkbutton. Empty initial text means the hover hint is
        # silent under the supported-mode branch (Tooltip._show
        # bails on empty strings). _refresh_floor_zero_state rotates
        # the text to the explanatory hint when the toggle is
        # disabled. Stored on the tab so the refresh method can
        # reach it.
        self._baseline_floor_zero_tooltip = Tooltip(
            self._baseline_floor_zero_cb, "",
        )
        # Initial calibration — fires before the user touches the
        # mode combobox so the toggle starts in the correct state.
        self._refresh_floor_zero_state()

        # Conditional parameter rows. The frame is rebuilt on every
        # mode change to keep layout straightforward.
        self._baseline_params_frame = tk.Frame(bl_body)
        self._baseline_params_frame.pack(fill=tk.X, padx=4, pady=2)

        # Apply button.
        apply_frame = tk.Frame(bl_body)
        apply_frame.pack(fill=tk.X, padx=4, pady=(8, 4))
        self._apply_baseline_btn = tk.Button(
            apply_frame, text="Apply Baseline", font=("", 9, "bold"),
            bg="#003d7a", fg="white", activebackground="#0055aa",
            command=self._apply_baseline,
        )
        self._apply_baseline_btn.pack(fill=tk.X)

        # ── Normalisation section (CS-16, Phase 4e) ──────────────────────
        self._normalisation_section = CollapsibleSection(
            parent, title="Normalisation", expanded=False)
        self._normalisation_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        self._normalisation_panel = uvvis_normalise.NormalisationPanel(
            self._normalisation_section.body,
            self._graph,
            status_cb=self._set_status_message,
        )
        self._normalisation_panel.pack(fill=tk.X)

        # ── Smoothing section (CS-18, Phase 4g) ──────────────────────────
        self._smoothing_section = CollapsibleSection(
            parent, title="Smoothing", expanded=False)
        self._smoothing_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        self._smoothing_panel = uvvis_smoothing.SmoothingPanel(
            self._smoothing_section.body,
            self._graph,
            status_cb=self._set_status_message,
        )
        self._smoothing_panel.pack(fill=tk.X)

        # ── Peak picking section (CS-19, Phase 4h) ───────────────────────
        # PEAK_LIST nodes are intentionally absent from the shared
        # subject list (chained peak picking is undefined):
        # _spectrum_nodes only walks UVVIS / BASELINE / NORMALISED /
        # SMOOTHED, which is exactly the set the panel accepts as
        # parents.
        self._peak_picking_section = CollapsibleSection(
            parent, title="Peak picking", expanded=False)
        self._peak_picking_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        self._peak_picking_panel = uvvis_peak_picking.PeakPickingPanel(
            self._peak_picking_section.body,
            self._graph,
            status_cb=self._set_status_message,
        )
        self._peak_picking_panel.pack(fill=tk.X)

        # ── Second derivative section (CS-20, Phase 4i) ──────────────────
        # SECOND_DERIVATIVE nodes are NOT candidate parents for further
        # derivatives this phase: _spectrum_nodes excludes
        # SECOND_DERIVATIVE so the shared subject combobox cannot offer
        # one, and the panel's ACCEPTED_PARENT_TYPES rejects it as
        # defence in depth.
        self._second_derivative_section = CollapsibleSection(
            parent, title="Second derivative", expanded=False)
        self._second_derivative_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        self._second_derivative_panel = (
            uvvis_second_derivative.SecondDerivativePanel(
                self._second_derivative_section.body,
                self._graph,
                status_cb=self._set_status_message,
            )
        )
        self._second_derivative_panel.pack(fill=tk.X)

        # Defer non-toolkit init until the chrome is present.
        self._refresh_baseline_param_rows()
        self._refresh_shared_subjects()

    def _set_status_message(self, text: str) -> None:
        """Status-bar callback handed to the NormalisationPanel.

        The tab owns the toolbar status label; subwidgets (the
        baseline section uses ``self._status_lbl.config`` inline,
        the NormalisationPanel uses this callback) update it through
        a single API so the formatting stays consistent.
        """
        if hasattr(self, "_status_lbl"):
            self._status_lbl.config(text=text, fg="#003d7a")

    def _refresh_floor_zero_state(self) -> None:
        """Enable / disable the "Floor at zero" toggle by current mode (CS-43).

        Reads ``self._baseline_mode`` and consults
        ``_FLOOR_ZERO_SUPPORTED_MODES``. Modes outside the supported set
        get the Checkbutton in ``state="disabled"`` plus a hover hint
        explaining the unsupported state; supported modes get the
        Checkbutton enabled and the hint blanked (empty-string sentinel
        makes :meth:`Tooltip._show` bail silently). The BooleanVar's
        value is preserved across enable / disable transitions so the
        persistence-umbrella round-trip carries the user's choice
        forward without auto-clear.
        """
        if not hasattr(self, "_baseline_floor_zero_cb"):
            return
        mode = self._baseline_mode.get()
        if mode in _FLOOR_ZERO_SUPPORTED_MODES:
            self._baseline_floor_zero_cb.config(state="normal")
            self._baseline_floor_zero_tooltip.update_text("")
        else:
            self._baseline_floor_zero_cb.config(state="disabled")
            self._baseline_floor_zero_tooltip.update_text(
                _FLOOR_ZERO_DISABLED_TOOLTIP,
            )

    def _refresh_baseline_param_rows(self) -> None:
        """Rebuild the parameter rows for the currently selected mode."""
        if not hasattr(self, "_baseline_params_frame"):
            return
        for child in self._baseline_params_frame.winfo_children():
            child.destroy()

        F9 = ("", 9)
        FC = ("Courier", 9)
        mode = self._baseline_mode.get()

        def _row(label_text: str) -> tk.Frame:
            row = tk.Frame(self._baseline_params_frame)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=F9, width=15,
                     anchor="w").pack(side=tk.LEFT)
            return row

        if mode == "linear":
            for label, var in [
                ("Anchor lo (nm):", self._baseline_anchor_lo),
                ("Anchor hi (nm):", self._baseline_anchor_hi),
            ]:
                tk.Entry(_row(label), textvariable=var, width=10,
                         font=FC).pack(side=tk.LEFT)
        elif mode == "polynomial":
            tk.Spinbox(_row("Order n:"),
                       textvariable=self._baseline_poly_order,
                       from_=0, to=10, width=8, font=FC,
                       ).pack(side=tk.LEFT)
            for label, var in [
                ("Fit lo (nm):", self._baseline_fit_lo),
                ("Fit hi (nm):", self._baseline_fit_hi),
            ]:
                tk.Entry(_row(label), textvariable=var, width=10,
                         font=FC).pack(side=tk.LEFT)
        elif mode == "spline":
            tk.Label(self._baseline_params_frame,
                     text="Anchors (nm, comma-separated):",
                     font=F9, anchor="w").pack(fill=tk.X)
            tk.Entry(self._baseline_params_frame,
                     textvariable=self._baseline_spline_anchors,
                     font=FC).pack(fill=tk.X, pady=(0, 2))
        elif mode == "rubberband":
            tk.Label(self._baseline_params_frame,
                     text="(parameter-free convex hull)",
                     fg="gray", font=F9).pack(anchor="w", pady=(4, 0))
        elif mode in ("scattering", "scattering+offset"):
            # CS-38 — scattering+offset shares the scattering Tk vars
            # and parameter row layout (the additive constant ``a`` is
            # always fitted, so no extra UI). The mode discriminator
            # picks the right ``compute_*`` at apply time.
            #
            # n entry + "Fit n" checkbox on the same row; checkbox
            # disables the entry so the user sees which way the fit
            # branch is pinned.
            n_row = _row("n:")
            n_entry = tk.Entry(n_row, textvariable=self._baseline_scattering_n,
                               width=8, font=FC)
            n_entry.pack(side=tk.LEFT)

            def _sync_n_entry_state(*_):
                n_entry.configure(
                    state=("disabled"
                           if self._baseline_scattering_fit_n.get()
                           else "normal"))

            tk.Checkbutton(
                n_row, text="Fit n",
                variable=self._baseline_scattering_fit_n,
                font=F9, command=_sync_n_entry_state,
            ).pack(side=tk.LEFT, padx=(8, 0))
            _sync_n_entry_state()
            for label, var in [
                ("Fit lo (nm):", self._baseline_scattering_fit_lo),
                ("Fit hi (nm):", self._baseline_scattering_fit_hi),
            ]:
                tk.Entry(_row(label), textvariable=var, width=10,
                         font=FC).pack(side=tk.LEFT)

    def _refresh_shared_subjects(self) -> None:
        """Repopulate the shared subject combobox from live spectrum nodes.

        Phase 4k (CS-22): a single combobox at the top of the left
        pane drives every operation panel + the inline baseline
        section. The host walks the union of every panel's
        ``ACCEPTED_PARENT_TYPES`` so any candidate parent surfaces
        in the combobox; per-panel gates then disable the per-panel
        Apply button when the selected node is not in their
        accepted set.

        Phase 4x widening (CS-49): SECOND_DERIVATIVE joins the
        union (SmoothingPanel now accepts derivatives — see
        ``SmoothingPanel.ACCEPTED_PARENT_TYPES`` for the rationale).
        We do NOT touch ``_spectrum_nodes`` itself — the renderer
        uses ``_spectrum_nodes()`` and ``_second_derivative_nodes()``
        as separate iterations (the second one's NodeType routes
        to the secondary y-axis under CS-44, and concatenating into
        ``_spectrum_nodes`` would double-render). Order: spectrum
        nodes first (UVVIS → BASELINE → NORMALISED → SMOOTHED),
        then SECOND_DERIVATIVE, so derivative entries cluster at
        the bottom of the combobox.
        """
        if not hasattr(self, "_shared_subject_cb"):
            return
        nodes = self._spectrum_nodes() + self._second_derivative_nodes()
        self._shared_subject_map = {}
        items: List[str] = []
        for n in nodes:
            key = f"{n.label}  [{n.id[:6]}]"
            items.append(key)
            self._shared_subject_map[key] = n.id
        self._shared_subject_cb.configure(values=items)
        # Keep the user's selection if it still exists; otherwise
        # auto-pick the first available. The trace fans the change
        # out to every panel.
        if self._shared_subject.get() not in items:
            self._shared_subject.set(items[0] if items else "")
        else:
            # Selection text unchanged but the underlying node may
            # have moved (label edit, type change). Re-fan so the
            # gates re-evaluate with the up-to-date node.
            self._on_shared_subject_changed()

    def _resolve_shared_subject_id(self) -> Optional[str]:
        """Map the shared combobox display string back to a node id."""
        return self._shared_subject_map.get(self._shared_subject.get())

    def _on_shared_subject_changed(self) -> None:
        """Fan the shared subject change out to every panel + baseline.

        Called by the StringVar trace whenever the user picks a new
        subject (or ``_refresh_shared_subjects`` repopulates the
        list). Each panel's ``set_subject`` re-evaluates its Apply
        button state; the inline baseline section gets the same
        treatment via ``_refresh_baseline_apply_state``.
        """
        node_id = self._resolve_shared_subject_id()
        self._baseline_subject_id = node_id
        if hasattr(self, "_normalisation_panel"):
            self._normalisation_panel.set_subject(node_id)
        if hasattr(self, "_smoothing_panel"):
            self._smoothing_panel.set_subject(node_id)
        if hasattr(self, "_peak_picking_panel"):
            self._peak_picking_panel.set_subject(node_id)
        if hasattr(self, "_second_derivative_panel"):
            self._second_derivative_panel.set_subject(node_id)
        self._refresh_baseline_apply_state()

    def _refresh_baseline_apply_state(self) -> None:
        """Disable the inline baseline Apply button when the subject is invalid."""
        if not hasattr(self, "_apply_baseline_btn"):
            return
        ok = False
        if self._baseline_subject_id is not None:
            try:
                node = self._graph.get_node(self._baseline_subject_id)
            except KeyError:
                node = None
            if node is not None and node.type in self._BASELINE_ACCEPTED_PARENT_TYPES:
                ok = True
        self._apply_baseline_btn.configure(
            state=("normal" if ok else "disabled"))

    def _collect_baseline_params(self, mode: str) -> dict:
        """Read the left-panel widgets for ``mode`` into a params dict.

        Raises ``ValueError`` (with a user-readable message) on bad
        input. Per CS-03 the caller writes whatever this returns
        verbatim into the OperationNode's params dict.

        CS-37 (Phase 4s): every returned dict carries ``floor_zero:
        bool`` so the panel-level toggle round-trips through every
        mode's OperationNode (regardless of whether the constrained-
        fit code path is implemented for that mode yet).
        """
        floor_zero = bool(self._baseline_floor_zero.get())
        if mode == "linear":
            try:
                lo = float(self._baseline_anchor_lo.get())
                hi = float(self._baseline_anchor_hi.get())
            except ValueError:
                raise ValueError("Both anchors must be numeric (nm).")
            return {"anchor_lo_nm": lo, "anchor_hi_nm": hi,
                    "floor_zero": floor_zero}
        if mode == "polynomial":
            try:
                order = int(self._baseline_poly_order.get())
                lo = float(self._baseline_fit_lo.get())
                hi = float(self._baseline_fit_hi.get())
            except (ValueError, tk.TclError):
                raise ValueError(
                    "Order must be int; fit window endpoints must be numeric.")
            return {"order": order, "fit_lo_nm": lo, "fit_hi_nm": hi,
                    "floor_zero": floor_zero}
        if mode == "spline":
            raw = self._baseline_spline_anchors.get().strip()
            if not raw:
                raise ValueError(
                    "Spline anchors required (≥2 wavelengths in nm, comma-separated).")
            try:
                anchors = [float(x.strip()) for x in raw.split(",") if x.strip()]
            except ValueError:
                raise ValueError("Anchors must be comma-separated numbers (nm).")
            if len(anchors) < 2:
                raise ValueError("Spline requires at least 2 anchors.")
            return {"anchors": anchors, "floor_zero": floor_zero}
        if mode == "rubberband":
            return {"floor_zero": floor_zero}
        if mode in ("scattering", "scattering+offset"):
            try:
                lo = float(self._baseline_scattering_fit_lo.get())
                hi = float(self._baseline_scattering_fit_hi.get())
            except ValueError:
                raise ValueError(
                    "Fit window endpoints must be numeric (nm).")
            if self._baseline_scattering_fit_n.get():
                return {"n": "fit", "fit_lo_nm": lo, "fit_hi_nm": hi,
                        "floor_zero": floor_zero}
            try:
                n_val = float(self._baseline_scattering_n.get())
            except ValueError:
                raise ValueError(
                    "n must be numeric (or check 'Fit n' to fit it).")
            return {"n": n_val, "fit_lo_nm": lo, "fit_hi_nm": hi,
                    "floor_zero": floor_zero}
        raise ValueError(f"Unknown baseline mode: {mode!r}")

    def _apply_baseline(self) -> Optional[Tuple[str, str]]:
        """Materialise a provisional BASELINE op + node from the panel state.

        One Apply gesture = one new provisional ``BASELINE``
        OperationNode + one new provisional ``BASELINE`` DataNode,
        wired ``parent → op → child``. Returns ``(op_id, child_id)``
        on success or ``None`` if the user input was rejected.

        Phase 4k (CS-22): the parent is the *shared* subject selected
        by the top-of-pane combobox. ``_apply_baseline_btn`` is
        disabled when the shared selection isn't a UVVIS / BASELINE
        node, but the messagebox-bearing checks below still run as
        defence in depth.
        """
        subject_id = self._baseline_subject_id
        if not subject_id:
            messagebox.showinfo(
                "Apply Baseline",
                "Select a spectrum from the top of the left pane first.",
            )
            return None
        try:
            parent_node = self._graph.get_node(subject_id)
        except KeyError:
            messagebox.showerror(
                "Apply Baseline",
                "Selected spectrum is no longer in the project graph.",
            )
            return None
        if parent_node.type not in self._BASELINE_ACCEPTED_PARENT_TYPES:
            messagebox.showerror(
                "Apply Baseline",
                "Selected node is not a valid parent for baseline correction.",
            )
            return None

        mode = self._baseline_mode.get()
        try:
            params = self._collect_baseline_params(mode)
        except ValueError as exc:
            messagebox.showerror("Baseline parameters", str(exc))
            return None

        # CS-03: capture the full parameter snapshot. ``mode`` is the
        # discriminator; the remaining keys are the mode-specific
        # sub-schema documented in CS-15.
        op_params = {"mode": mode, **params}

        wl = parent_node.arrays["wavelength_nm"]
        absorb = parent_node.arrays["absorbance"]
        try:
            corrected = uvvis_baseline.compute(mode, wl, absorb, params)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Baseline computation", str(exc))
            return None

        # CS-39 (Phase 4s) — persist resolved fit parameters on the
        # OperationNode for the scattering modes. The fit ran inside
        # ``compute()``; the matching ``fit_*`` helper recovers the
        # same values so a downstream consumer (export header,
        # provenance footer, future diagnostic console) can read
        # ``c_fitted`` / ``n_fitted`` / ``a_fitted`` without re-running
        # the operation. Failure here is non-fatal — the corrected
        # spectrum already exists; we simply skip the diagnostic keys.
        if mode == "scattering":
            try:
                info = uvvis_baseline.fit_scattering(wl, absorb, params)
                op_params["c_fitted"] = info["c_fitted"]
                if str(params.get("n", "")).lower() == "fit":
                    op_params["n_fitted"] = info["n_fitted"]
            except (ValueError, KeyError):
                pass
        elif mode == "scattering+offset":
            try:
                info = uvvis_baseline.fit_scattering_offset(wl, absorb, params)
                op_params["a_fitted"] = info["a_fitted"]
                op_params["c_fitted"] = info["c_fitted"]
                if str(params.get("n", "")).lower() == "fit":
                    op_params["n_fitted"] = info["n_fitted"]
            except (ValueError, KeyError):
                pass

        op_id = uuid.uuid4().hex
        out_id = uuid.uuid4().hex
        op_node = OperationNode(
            id=op_id,
            type=OperationType.BASELINE,
            engine="internal",
            engine_version=PTARMIGAN_VERSION,
            params=op_params,
            input_ids=[subject_id],
            output_ids=[out_id],
            status="SUCCESS",
            state=NodeState.PROVISIONAL,
            metadata={"implementation_hash":
                      compute_implementation_hash(OperationType.BASELINE)},
        )

        # Default colour for the new BASELINE node — pick a fresh
        # palette entry so the corrected curve is visually separable
        # from its parent. CS-21 (Phase 4j) replaced the inline
        # palette-index expression with the shared pick_default_color
        # helper.
        colour = pick_default_color(self._graph)

        # Carry the parent's metadata forward, plus a baseline footer.
        new_meta: dict = {
            **parent_node.metadata,
            "baseline_mode":      mode,
            "baseline_parent_id": subject_id,
        }

        data_node = DataNode(
            id=out_id,
            type=NodeType.BASELINE,
            arrays={
                "wavelength_nm": np.asarray(wl, dtype=float),
                "absorbance":    np.asarray(corrected, dtype=float),
            },
            metadata=new_meta,
            label=f"{parent_node.label} · baseline ({mode})",
            state=NodeState.PROVISIONAL,
            style=default_spectrum_style(colour),
        )

        # Insert op + data, then wire parent → op → child.
        self._graph.add_node(op_node)
        self._graph.add_node(data_node)
        self._graph.add_edge(subject_id, op_id)
        self._graph.add_edge(op_id, out_id)

        self._status_lbl.config(
            text=f"Baseline ({mode}) applied to {parent_node.label} "
                 f"(provisional — commit / discard via the right sidebar).",
            fg="#003d7a",
        )
        return op_id, out_id

    # ── Plot panel ────────────────────────────────────────────────────────────

    def _build_plot(self, parent):
        self._fig = Figure(figsize=(7, 4.5), dpi=100)
        self._ax  = self._fig.add_subplot(111)

        # Phase 4u (CS-44): role → matplotlib Axes map. Tracks every
        # populated axis (primary + lazy twin axes for "secondary" /
        # "tertiary") so the legend merge, tick-direction propagation,
        # and tests can introspect them by role. Reseeded on every
        # `_redraw` after `self._fig.clear()`.
        self._axes_by_role: dict[str, "matplotlib.axes.Axes"] = {
            "primary": self._ax,
        }

        self._canvas = FigureCanvasTkAgg(self._fig, master=parent)
        self._canvas.get_tk_widget().pack(
            side=tk.TOP, fill=tk.BOTH, expand=True)

        toolbar_frame = tk.Frame(parent)
        toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self._toolbar = NavigationToolbar2Tk(self._canvas, toolbar_frame)
        self._toolbar.update()

        self._canvas.mpl_connect("button_release_event", self._on_mpl_interact)
        self._canvas.mpl_connect("scroll_event",         self._on_mpl_interact)
        # CS-60 (Phase 4ai): double-clicking on an axis region opens
        # the Plot Config dialog pre-selected to that axis's Notebook
        # tab. Single-clicks and interior clicks fall through silently;
        # the hit-test classifier handles the dblclick filter.
        self._canvas.mpl_connect(
            "button_press_event", self._on_mpl_axis_double_click,
        )

        self._draw_empty()

    # ══════════════════════════════════════════════════════════════════════════
    #  Graph event subscription
    # ══════════════════════════════════════════════════════════════════════════

    def _on_graph_event(self, event: GraphEvent) -> None:
        """Drive plot redraws from graph mutations.

        Per CS-05 the unified style dialog never calls a redraw
        callback; the tab is the single subscriber that owns plot
        updates. ScanTreeWidget rebuilds its own rows; here we just
        repaint the figure. Any UVVIS-touching event re-renders.
        """
        et = event.type
        if et in (
            GraphEventType.NODE_ADDED,
            GraphEventType.NODE_DISCARDED,
            GraphEventType.NODE_ACTIVE_CHANGED,
            GraphEventType.NODE_STYLE_CHANGED,
            GraphEventType.NODE_LABEL_CHANGED,
            GraphEventType.GRAPH_LOADED,
            GraphEventType.GRAPH_CLEARED,
        ):
            self._redraw()
        # The shared subject combobox (CS-22, Phase 4k) tracks which
        # UVVIS / BASELINE / NORMALISED / SMOOTHED nodes exist;
        # refresh on the structural / label / active events that can
        # change that set. The trace on _shared_subject then fans the
        # selection out to every panel + the inline baseline gate.
        if et in (
            GraphEventType.NODE_ADDED,
            GraphEventType.NODE_DISCARDED,
            GraphEventType.NODE_ACTIVE_CHANGED,
            GraphEventType.NODE_LABEL_CHANGED,
            GraphEventType.GRAPH_LOADED,
            GraphEventType.GRAPH_CLEARED,
        ):
            self._refresh_shared_subjects()

    def _on_destroy_unsubscribe(self, _event) -> None:
        try:
            self._graph.unsubscribe(self._on_graph_event)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Workflow restore (Phase 4v / CS-46)
    # ══════════════════════════════════════════════════════════════════════════

    def _restore_workflow_payload(self, payload) -> None:
        """Replace this tab's graph contents and plot config with a
        loaded workflow's payload.

        Mutates ``self._graph`` in place rather than swapping the
        object identity — every subwidget (ScanTreeWidget, the five
        operation panels) holds its own reference to ``self._graph``
        from construction time, and reassigning the attribute would
        leave them pointing at the orphaned old graph. In-place
        replacement preserves identity, every subscriber stays
        subscribed, and one ``GRAPH_LOADED`` event drives a full UI
        rebuild (``_redraw`` + ``_refresh_shared_subjects`` here;
        ScanTreeWidget rebuilds via its own GRAPH_LOADED handler).
        """
        new_graph = payload.graph

        # Suspend notifications while we wipe and refill so the UI
        # does not see the intermediate "empty graph" state.
        saved_subs = list(self._graph._subscribers)
        self._graph._subscribers = []
        try:
            self._graph.nodes.clear()
            self._graph.edges.clear()
            self._graph._active_overrides.clear()
            self._graph.nodes.update(new_graph.nodes)
            self._graph.edges.extend(new_graph.edges)
            self._graph._active_overrides.update(new_graph._active_overrides)
        finally:
            self._graph._subscribers = saved_subs

        if payload.plot_config:
            self._plot_config = copy.deepcopy(dict(payload.plot_config))

        self._graph._notify(GraphEvent(GraphEventType.GRAPH_LOADED, ""))

    # ══════════════════════════════════════════════════════════════════════════
    #  Style dialog hand-off (CS-05)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Export hand-off (CS-17, Phase 4f) ─────────────────────────────────────

    _EXPORT_FILETYPES: tuple = (
        ("CSV (comma-separated)", "*.csv"),
        ("TXT (tab-separated)",   "*.txt"),
    )

    @staticmethod
    def _sanitise_basename(label: str) -> str:
        """Sanitise a node label for use as a default filename basename.

        Strips characters that Windows / macOS / Linux file systems
        reject and collapses runs of whitespace to a single underscore.
        Empty results fall back to ``"export"``.
        """
        bad = '<>:"/\\|?*'
        cleaned = "".join(
            "_" if (ch in bad or ch.isspace()) else ch for ch in label
        )
        cleaned = cleaned.strip("._")
        return cleaned or "export"

    def _on_export_node(self, node_id: str) -> None:
        """Row Export… hand-off: ask for a path then write the file.

        Opens an ``asksaveasfilename`` dialog filtered to ``.csv`` /
        ``.txt``, defaults the basename to the node's sanitised label,
        and delegates to ``node_export.export_node_to_file``. Success
        nudges the status bar; failure surfaces via ``messagebox``.

        The widget gates the gesture on committed state, so this
        method can assume a valid committed-and-exportable id, but
        ``node_export`` raises ``ValueError`` on a stale type and we
        still surface that defensively.
        """
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return

        default_name = self._sanitise_basename(getattr(node, "label", ""))
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export spectrum",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=list(self._EXPORT_FILETYPES),
        )
        if not path:
            return

        try:
            node_export.export_node_to_file(self._graph, node_id, path)
        except (ValueError, KeyError, OSError) as exc:
            messagebox.showerror(
                "Export failed",
                f"Could not export {node_id!r}:\n{exc}",
                parent=self,
            )
            return
        self._set_status_message(f"Exported to {path}")

    def _open_style_dialog_for_node(self, node_id: str) -> None:
        """Gear-button hand-off: open the unified ``StyleDialog`` (CS-05).

        ``open_style_dialog`` enforces one-dialog-per-node. The
        ``on_apply_to_all`` callback fans the value out to every node
        currently rendered in the sidebar — UVVIS and BASELINE alike
        (Phase 4d: B-002 widened the scope so ``visible`` /
        ``in_legend`` toggles propagate across both row types, since
        both share the sidebar and every other row control).
        """
        open_style_dialog(
            self, self._graph, node_id,
            on_apply_to_all=self._on_uvvis_apply_to_all,
        )

    def _on_uvvis_apply_to_all(self, param: str, value) -> None:
        """∀ fan-out: write ``param=value`` onto every visible spectrum node.

        Default scope is ``_spectrum_nodes`` (UVVIS + BASELINE +
        NORMALISED + SMOOTHED), not the UVVIS-only ``_uvvis_nodes``.
        Phase 4d widened this so the new ``visible`` / ``in_legend``
        controls (B-002) cover the whole sidebar — but the widening
        applies to every key, since the user invoking ∀ on, say, a
        linewidth in a sidebar mixing UVVIS and BASELINE rows
        expects every visible row to take the value. ``set_style``
        is a merge per CS-01, so keys other than ``param`` on each
        target node are preserved.

        BASELINE rows lack a baseline-specific style schema today;
        they share the universal style keys with UVVIS, so the merge
        is well-defined. Should a future BASELINE-specific key land
        (e.g., a baseline-fit colour distinct from the spectrum
        colour) the fan-out scope can be revisited.

        Phase 4y (CS-50): the per-row ∀ button next to the StyleDialog
        ``y_axis`` Combobox writes the chosen axis role to **every
        renderable node**, including SECOND_DERIVATIVE and PEAK_LIST.
        ``y_axis`` is the only axis-routing key, so widening the
        fan-out to those types is the user's intended "everyone goes
        on this axis" gesture (per Phase 4y Decision (iii)). Other
        keys keep the spectrum-only scope so a linewidth fan-out
        does not silently rewrite annotation overlays.
        """
        if param == "y_axis":
            targets = (
                self._spectrum_nodes()
                + self._second_derivative_nodes()
                + self._peak_list_nodes()
            )
        else:
            targets = self._spectrum_nodes()
        for node in targets:
            self._graph.set_style(node.id, {param: value})

    # ══════════════════════════════════════════════════════════════════════════
    #  Plot Settings dialog hand-off (CS-06)
    # ══════════════════════════════════════════════════════════════════════════

    def _open_plot_settings(self) -> None:
        """⚙ button hand-off: open the unified Plot Settings dialog.

        The factory enforces one-dialog-per-tab. The dialog mutates
        ``self._plot_config`` in place on Apply, then invokes
        ``on_apply`` so the tab repaints. Phase 4ak (CS-62) threads
        the per-axis plot inventory through ``plots_by_role`` so
        each per-axis Notebook tab can render its "Plots on this
        axis" list. Phase 4al threads ``on_route_plot`` so the
        Move-to picker on each Y-axis tab can write
        ``style["y_axis"]`` directly via ``graph.set_style``.
        """
        plot_settings_dialog.open_plot_config_dialog(
            self, self._plot_config,
            on_apply=self._on_plot_config_changed,
            plots_by_role=self._compute_plots_by_role(),
            on_route_plot=self._on_route_plot_from_dialog,
            secondary_x_linked=self._secondary_x_linked(),
        )

    def _on_plot_config_changed(self) -> None:
        """Apply / Cancel callback from the Plot Settings dialog.

        The dialog has already mutated ``self._plot_config`` in place;
        the tab just needs to repaint. Plot Settings is tab-private
        UI state, so it does not flow through the graph subscription.
        """
        self._redraw()

    def _on_route_plot_from_dialog(
        self,
        source_tab_role: str,
        label: str,
        target_tab_role: Optional[str],
    ) -> None:
        """Phase 4al: Move-to picker callback from the Plot Settings dialog.

        The dialog speaks tab-role-key space (``primary_y`` /
        ``secondary_y`` / ``tertiary_y``); the host translates into
        the CS-50 ``style["y_axis"]`` value via the inverse of
        :data:`_Y_AXIS_ROLE_TO_TAB` and writes it through
        ``graph.set_style``. ``target_tab_role=None`` clears the
        override (restoring per-NodeType default routing).

        Label collisions across axes are resolved by the source role:
        only nodes currently routed to ``source_tab_role`` are
        eligible. The first matching visible node wins — in the
        common case where labels are unique within a graph this is
        deterministic; if a graph carries two visible nodes with
        the same label on the same axis, the user can rename one
        through the per-node Style dialog.

        ``set_style`` fires NODE_STYLE_CHANGED, which the tab's
        subscription consumes and translates into a redraw — no
        explicit ``_redraw`` call needed here.
        """
        tab_to_style = {v: k for k, v in _Y_AXIS_ROLE_TO_TAB.items()}
        source_style = tab_to_style.get(source_tab_role)
        target_style = (
            tab_to_style.get(target_tab_role)
            if target_tab_role is not None else None
        )
        if source_style is None:
            return
        for node in (
            list(self._spectrum_nodes())
            + list(self._second_derivative_nodes())
            + list(self._peak_list_nodes())
        ):
            if not bool(node.style.get("visible", True)):
                continue
            if node.label != label:
                continue
            if _resolve_y_axis_role(node.type, node.style) != source_style:
                continue
            self._graph.set_style(node.id, {"y_axis": target_style})
            return

    def _compute_plots_by_role(self) -> dict[str, tuple[str, ...]]:
        """Build the ``plots_by_role`` mapping the dialog consumes (Phase 4ak).

        Delegates to :func:`_enumerate_plots_by_role` with the three
        live-node helpers and a flag indicating whether the
        wavelength↔energy twin axis is currently visible. Computed
        once at dialog open — the dialog snapshots the result for
        its lifetime, so subsequent graph mutations require a fresh
        open to surface.
        """
        return _enumerate_plots_by_role(
            self._spectrum_nodes(),
            self._second_derivative_nodes(),
            self._peak_list_nodes(),
            secondary_x_active=self._secondary_x_linked(),
        )

    def _secondary_x_linked(self) -> bool:
        """Return True iff the wavelength↔energy linked secondary X axis
        is currently live (CS-69, Phase 4aq).

        The guard is ``self._x_unit.get() in ("cm-1", "eV") and
        bool(self._show_nm_axis.get())``. ``_redraw`` consults it to
        decide whether to build ``sec`` via ``ax.secondary_xaxis(...,
        functions=(_fwd, _fwd))``; ``_compute_plots_by_role`` consults
        it to decide whether the ``secondary_x`` role gets a non-empty
        plots list; the Plot Settings hand-off consults it to thread
        ``secondary_x_linked`` into the dialog so the Secondary X
        tab's inert range / autoscale / scale widgets render greyed
        out (D8 lock; B-005 root cause is matplotlib's set_xlim back-
        propagation through the inverse of ``_fwd``).
        """
        return (
            self._x_unit.get() in ("cm-1", "eV")
            and bool(self._show_nm_axis.get())
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  File loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_files(self):
        paths = filedialog.askopenfilenames(
            title="Open UV/Vis file(s)", filetypes=_FILE_TYPES)
        if not paths:
            return

        n_loaded = 0
        for path in paths:
            try:
                for scan in parse_uvvis_file(path):
                    if self._has_existing_load(scan.source_file, scan.label):
                        continue
                    self._load_uvvis_scan(path, scan)
                    n_loaded += 1
            except Exception as exc:
                messagebox.showerror(
                    "Load error",
                    f"Could not read {os.path.basename(path)}:\n{exc}")

        if n_loaded:
            # Plot redraw fires automatically through the graph
            # subscription on each NODE_ADDED. Status label is a UI
            # detail outside the graph, so update it here directly.
            total = len(self._uvvis_nodes())
            self._status_lbl.config(
                text=f"{total} spectrum/spectra loaded.",
                fg="#003300")

    def _load_uvvis_scan(self, path: str, scan: UVVisScan) -> tuple[str, str, str]:
        """Materialise a parsed UVVisScan as RAW_FILE + LOAD + UVVIS in the graph.

        Implements the §5.3 + CS-13 load-time rule: a file load creates
        a COMMITTED RAW_FILE node (the immutable provenance anchor),
        a COMMITTED LOAD OperationNode, and a COMMITTED UVVIS DataNode
        carrying the parsed arrays. No analysis runs automatically.

        Returns ``(raw_id, op_id, uvvis_id)``.
        """
        raw_id   = uuid.uuid4().hex
        op_id    = uuid.uuid4().hex
        uvvis_id = uuid.uuid4().hex

        ext = os.path.splitext(path)[1].lower().lstrip(".") or "unknown"
        instrument = scan.metadata.get("instrument", "generic")

        # 1. RAW_FILE node — the immutable anchor (CS-02 conventions).
        raw_node = DataNode(
            id=raw_id,
            type=NodeType.RAW_FILE,
            arrays={},
            metadata={
                "original_path": str(path),
                "file_format":   ext,
                # sha256 / copied_to are written when the project is
                # saved into a .ptproj/ via project_io.copy_raw_file.
            },
            label=os.path.basename(path),
            state=NodeState.COMMITTED,
        )

        # 2. LOAD operation — engine="internal", parameters sufficient
        #    to re-run the load (CS-03 params completeness).
        op_node = OperationNode(
            id=op_id,
            type=OperationType.LOAD,
            engine="internal",
            engine_version=PTARMIGAN_VERSION,
            params={
                "file_format": ext,
                "instrument":  instrument,
                "parser":      "uvvis_parser.parse_uvvis_file",
            },
            input_ids=[raw_id],
            output_ids=[uvvis_id],
            status="SUCCESS",
            state=NodeState.COMMITTED,
            metadata={"implementation_hash":
                      compute_implementation_hash(OperationType.LOAD)},
        )

        # 3. UVVIS DataNode — parsed arrays + style with default colour.
        # CS-21 (Phase 4j) routes default-colour selection through
        # node_styles.pick_default_color so the loader walks the same
        # six-NodeType counter as the operation panels.
        colour = pick_default_color(self._graph)

        uvvis_meta = {
            "x_unit":      "nm",
            "y_unit":      "absorbance",
            "instrument":  instrument,
            "source_file": scan.source_file,
        }
        # Carry parser-supplied metadata under a namespaced key so it
        # doesn't collide with CS-02 conventions.
        if scan.metadata:
            uvvis_meta["parser_metadata"] = dict(scan.metadata)

        uvvis_node = DataNode(
            id=uvvis_id,
            type=NodeType.UVVIS,
            arrays={
                "wavelength_nm": np.asarray(scan.wavelength_nm, dtype=float),
                "absorbance":    np.asarray(scan.absorbance, dtype=float),
            },
            metadata=uvvis_meta,
            label=scan.display_name(),
            state=NodeState.COMMITTED,
            style=default_spectrum_style(colour),
        )

        self._graph.add_node(raw_node)
        self._graph.add_node(op_node)
        self._graph.add_node(uvvis_node)
        self._graph.add_edge(raw_id, op_id)
        self._graph.add_edge(op_id, uvvis_id)
        return raw_id, op_id, uvvis_id

    # ══════════════════════════════════════════════════════════════════════════
    #  Axis helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _parse_lim(self, var: tk.StringVar) -> Optional[float]:
        try:
            return float(var.get().strip())
        except ValueError:
            return None

    def _auto_x(self):
        self._xlim_lo.set(""); self._xlim_hi.set(""); self._redraw()

    def _auto_y(self):
        self._ylim_lo.set(""); self._ylim_hi.set(""); self._redraw()

    def _on_mpl_interact(self, event):
        if event.name == "button_release_event" and event.button != 1:
            return
        try:
            x0, x1 = self._ax.get_xlim()
            y0, y1 = self._ax.get_ylim()
            self._xlim_lo.set(f"{min(x0, x1):.4g}")
            self._xlim_hi.set(f"{max(x0, x1):.4g}")
            self._ylim_lo.set(f"{min(y0, y1):.4g}")
            self._ylim_hi.set(f"{max(y0, y1):.4g}")
        except Exception:
            pass

    def _on_mpl_axis_double_click(self, event) -> None:
        """Open the Plot Config dialog on the clicked axis's tab (CS-60).

        Wired to ``button_press_event``; the hit-test classifier
        ignores non-double-clicks. A click in the plot interior
        returns ``None`` from the classifier and is a no-op — the
        existing ⚙ button is still the canonical entry to the Global
        tab. When the classifier matches an axis region, we open via
        :func:`plot_settings_dialog.open_plot_config_dialog` with
        ``tab=<axis-role>``; the factory's "raise existing" path
        switches the active tab if the dialog is already open.

        The dispatch path is intentionally identical to the ⚙
        button's: same ``on_apply`` callback, same modal contract,
        same per-tab registry. Only the entry gesture and the
        pre-selected tab differ.
        """
        hit = plot_axis_hit_test.classify_axis_double_click(
            event,
            self._axes_by_role,
            tertiary_offset_frac=_TERTIARY_AXIS_OFFSET_FRAC,
        )
        if hit is None:
            return
        plot_settings_dialog.open_plot_config_dialog(
            self, self._plot_config,
            on_apply=self._on_plot_config_changed,
            tab=hit.role,
            plots_by_role=self._compute_plots_by_role(),
            on_route_plot=self._on_route_plot_from_dialog,
            secondary_x_linked=self._secondary_x_linked(),
        )

    def _on_unit_change(self):
        new_unit  = self._x_unit.get()
        prev_unit = self._x_unit_prev
        if new_unit != prev_unit:
            lo = self._parse_lim(self._xlim_lo)
            hi = self._parse_lim(self._xlim_hi)
            if lo is not None and hi is not None:
                new_lo, new_hi = _convert_xlim(lo, hi, prev_unit, new_unit)
                self._xlim_lo.set(f"{new_lo:.4g}")
                self._xlim_hi.set(f"{new_hi:.4g}")
            self._x_unit_prev = new_unit
        self._redraw()

    # ══════════════════════════════════════════════════════════════════════════
    #  Plotting (graph-driven)
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_empty(self):
        # Phase 4u (CS-44): clear the whole figure rather than just
        # `self._ax.cla()` so stale twin axes from a prior populated
        # draw (a SECOND_DERIVATIVE node on "secondary", a future
        # NodeType on "tertiary") don't linger as empty floating
        # spines in the empty state. Re-seed the role map.
        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        self._axes_by_role = {"primary": self._ax}
        self._ax.set_facecolor("#f8f8f8")
        self._ax.text(0.5, 0.5, "Load a UV/Vis file to begin",
                      ha="center", va="center",
                      transform=self._ax.transAxes,
                      color="gray", fontsize=11)
        self._ax.set_axis_off()
        self._canvas.draw_idle()

    def _redraw(self, *_args, **_kwargs):
        # Accept ``focus=node_id`` from ScanTreeWidget history-click
        # gestures (CS-04). Phase 4a does not yet implement preview
        # rendering for ancestor nodes, so the kwarg is currently
        # ignored; the call is honoured as a regular full redraw.
        # Walk the ProjectGraph for live UVVIS / BASELINE / NORMALISED
        # nodes whose style has them visible; fall back to the
        # empty-state placeholder when nothing is loaded or every
        # loaded node is hidden. All three render identically — they
        # share the ``arrays["wavelength_nm"]`` /
        # ``arrays["absorbance"]`` convention. Phase 4e retired
        # ``_y_with_norm``: normalisation is now an explicit operation
        # that creates a NORMALISED node with the normalised values
        # baked into ``arrays["absorbance"]``, not a draw-time
        # transform on the displayed y-values.
        live = [n for n in self._spectrum_nodes()
                if bool(n.style.get("visible", True))]
        # SECOND_DERIVATIVE nodes (CS-20, Phase 4i) ride the same
        # curve render path as the spectrum-shaped nodes — they carry
        # the wavelength_nm / absorbance schema, so the loop below
        # treats them identically. They are kept out of
        # ``_spectrum_nodes`` so the locked smoothing / baseline /
        # normalise / peak-picking panels do not surface them as
        # candidate parents (those panels would silently refuse them).
        live.extend(n for n in self._second_derivative_nodes()
                    if bool(n.style.get("visible", True)))

        if not live:
            self._draw_empty()
            return

        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        ax   = self._ax
        unit = self._x_unit.get()
        cfg  = self._plot_config

        # Phase 4u (CS-44): re-seed the role → Axes map for this
        # redraw. Twin axes ("secondary" / "tertiary") are created
        # lazily via ``get_axis(role)`` only when at least one node
        # routes to that role, so a graph without SECOND_DERIVATIVE
        # nodes ends up with exactly one Axes (primary) and behaves
        # identically to the pre-CS-44 single-axis layout.
        self._axes_by_role = {"primary": ax}
        first_node_type_per_role: dict[str, NodeType] = {}

        # Phase 4al: tick_direction reads per axis-role. The schema
        # invention from Phase 4ak (CS-62) stored a tick_direction per
        # role in ``cfg["axes"][<role>]``; this phase wires each
        # tick_params call site to its own role. Primary x/y split via
        # ``axis="x"`` / ``axis="y"`` calls on ``ax``; twin Y-axes
        # read their own role at creation time in ``get_axis``; the
        # secondary_x sibling axis (wavelength↔energy twin) reads
        # from ``secondary_x`` instead of the previous hardcoded
        # ``"in"``. The helper's fallback chain still covers
        # pre-migration ``_plot_config`` shapes via the legacy flat
        # ``cfg["tick_direction"]`` key.
        tick_size = cfg.get("tick_label_font_size", 9)
        tertiary_offset = float(
            cfg.get("tertiary_axis_offset", _TERTIARY_AXIS_OFFSET_FRAC))

        # CS-44 y-axis role keys ("primary"/"secondary"/"tertiary") map
        # to the dialog's tab role keys ("primary_y" etc.) — see
        # :data:`_Y_AXIS_ROLE_TO_TAB`. The twin Y-axis lookup uses
        # this so a future renamed-axis-role lands as a one-line
        # table edit rather than scattered string literals.
        def get_axis(role: str):
            """Return (creating if needed) the Axes for ``role``.

            Primary is always available. Secondary is a plain
            ``twinx()``. Tertiary is a second ``twinx()`` with its
            right spine offset by ``tertiary_offset`` (matplotlib axes
            coordinates) so the three y-axis labels stack visually.
            ``tertiary_offset`` reads through the Plot Settings
            ``tertiary_axis_offset`` key (CS-56 / Phase 4ae) with
            ``_TERTIARY_AXIS_OFFSET_FRAC`` as the fallback. Unknown
            roles fall back to primary so a future per-style override
            with a malformed value cannot crash the renderer.
            """
            if role in self._axes_by_role:
                return self._axes_by_role[role]
            if role == "secondary":
                ax_new = ax.twinx()
            elif role == "tertiary":
                ax_new = ax.twinx()
                ax_new.spines["right"].set_position(
                    ("axes", tertiary_offset))
            else:  # pragma: no cover — defensive fallback
                return ax
            twin_tab_role = _Y_AXIS_ROLE_TO_TAB.get(role)
            twin_tick_dir = _per_axis_tick_direction(cfg, twin_tab_role) \
                if twin_tab_role else _per_axis_tick_direction(cfg, "primary_y")
            ax_new.tick_params(
                axis="y", direction=twin_tick_dir, labelsize=tick_size)
            self._axes_by_role[role] = ax_new
            return ax_new

        # Background colour (Plot Settings → Appearance). Only the
        # primary Axes carries a face colour; twin axes overlay it
        # transparently, so setting it once is correct.
        ax.set_facecolor(cfg.get("background_color", "#ffffff"))

        for node in live:
            # Phase 4o defensive guard: every NodeType in
            # _spectrum_nodes() / _second_derivative_nodes() is *meant*
            # to carry the wavelength_nm + absorbance pair, but a
            # malformed DataNode (test scaffolding, half-loaded
            # project file, future NodeType added to the filter list
            # without renderer support) would otherwise raise
            # KeyError from inside the Tk graph-event handler. Skip
            # silently and let the rest of the live list render.
            if ("wavelength_nm" not in node.arrays
                    or "absorbance" not in node.arrays):
                continue
            # Phase 4y (CS-50): thread ``node.style`` so the per-style
            # ``y_axis`` override short-circuits the per-NodeType
            # default. ``style.get("y_axis") is None`` (the freshly-
            # created default for every spectrum-shaped node) preserves
            # the pre-CS-50 routing exactly; a non-None role string
            # routes the node to that axis regardless of its NodeType.
            role = _resolve_y_axis_role(node.type, node.style)
            target = get_axis(role)
            # Phase 4ad (CS-55): track the first NodeType to land on
            # *every* role, including primary. The label-resolution
            # walk below reads this map to label each populated axis
            # by its first node's NodeType — fixing the Phase 4ac
            # friction #1 bug where the renderer hard-coded primary's
            # ylabel from y-unit only.
            first_node_type_per_role.setdefault(role, node.type)
            style  = node.style
            colour = style.get("color", "#333333")
            wl     = node.arrays["wavelength_nm"]
            absorb = node.arrays["absorbance"]
            x = _wavelength_to_x(wl, unit)
            y = _absorbance_to_y(absorb, self._y_unit.get(), node.type)
            order  = np.argsort(x)
            x, y   = x[order], y[order]
            label  = node.label if style.get("in_legend", True) else None
            target.plot(x, y,
                        color=colour,
                        linestyle=style.get("linestyle", "solid"),
                        linewidth=style.get("linewidth", 1.5),
                        alpha=style.get("alpha", 0.9),
                        label=label)
            if style.get("fill", False):
                target.fill_between(x, 0, y,
                                    color=colour,
                                    alpha=style.get("fill_alpha", 0.08))

        # ── Baseline-curve overlays (CS-36, Phase 4ao / CS-67) ────────
        # For every visible BASELINE node, walk one hop in the graph
        # to recover the fitted baseline function and plot it in the
        # BASELINE node's colour with a dashed linestyle. Drawn after
        # the main spectrum loop so the dashed line sits visually on
        # top of its parent. Helper is silent on every failure path
        # (returns None) so a malformed graph cannot crash this branch.
        # Phase 4u (CS-44): the overlay is routed via
        # ``_resolve_y_axis_role`` for consistency with the main
        # loop. BASELINE → "primary" today by NodeType default, so
        # the dispatch is normally a no-op; the indirection lets a
        # future axis-routing change land as a single table edit.
        # Phase 4y (CS-50): the resolver call moved INSIDE the per-bn
        # loop so a BASELINE node carrying a per-style ``y_axis``
        # override routes its dashed overlay to the SAME axis as
        # the main BASELINE render (otherwise the main curve and
        # its overlay would land on different axes — visually
        # broken).
        # Phase 4ao (CS-67) retired the global ``_show_baseline_curves``
        # outer guard — CS-36's per-node ``style["show_baseline_curve"]``
        # is now the single source of truth (default True per CS-36,
        # so existing graphs that predate the key render their overlays
        # by default; users hide individual overlays via the per-row
        # ``~`` toggle in ScanTreeWidget).
        for bn in self._spectrum_nodes():
            if bn.type != NodeType.BASELINE:
                continue
            if not bool(bn.style.get("visible", True)):
                continue
            if not bool(bn.style.get("show_baseline_curve", True)):
                continue
            pair = uvvis_baseline.compute_baseline_curve(self._graph, bn)
            if pair is None:
                continue
            bwl, bcurve = pair
            bx = _wavelength_to_x(bwl, unit)
            by = _absorbance_to_y(bcurve, self._y_unit.get(), bn.type)
            border = np.argsort(bx)
            bx, by = bx[border], by[border]
            bcolour = bn.style.get("color", "#333333")
            blabel = (f"{bn.label} (baseline)"
                      if bn.style.get("in_legend", True) else None)
            baseline_target = get_axis(
                _resolve_y_axis_role(bn.type, bn.style)
            )
            baseline_target.plot(
                bx, by,
                color=bcolour,
                linestyle="--",
                linewidth=bn.style.get("linewidth", 1.5),
                alpha=0.7,
                label=blabel)

        # ── Peak list overlays (CS-19, Phase 4h) ──────────────────────
        # Render every visible PEAK_LIST node as a scatter on top of
        # the curves above. The peak_list arrays carry samples lifted
        # from the parent's wavelength grid, so the unit / Y-unit
        # conversions are the same ones the curves go through.
        # ``style["linestyle"]`` / ``linewidth`` / ``fill`` are
        # universal style keys but have no scatter analogue; the
        # renderer reads ``color`` / ``alpha`` / ``visible`` /
        # ``in_legend`` and ignores the rest. Marker is fixed at "v"
        # (downward triangle pointing at the peak); a future
        # marker-style schema decision (CS-19 implementation note)
        # could expose this to the user.
        # Phase 4u (CS-44): peak overlays routed via the helper too —
        # PEAK_LIST → "primary" today by NodeType default. Same
        # one-line-edit principle.
        # Phase 4y (CS-50): the resolver call moved INSIDE the
        # per-peak-node loop so a PEAK_LIST node carrying a per-style
        # ``y_axis`` override (e.g. peaks of a derivative routed to
        # the secondary axis) lands on the right axis.
        for peak_node in self._peak_list_nodes():
            pstyle = peak_node.style
            if not pstyle.get("visible", True):
                continue
            pwl = peak_node.arrays["peak_wavelengths_nm"]
            pa = peak_node.arrays["peak_absorbances"]
            if pwl.size == 0:
                continue
            px = _wavelength_to_x(np.asarray(pwl, dtype=float), unit)
            py = _absorbance_to_y(np.asarray(pa, dtype=float),
                                  self._y_unit.get(),
                                  peak_node.type)
            plabel = (peak_node.label
                      if pstyle.get("in_legend", True) else None)
            peak_target = get_axis(
                _resolve_y_axis_role(peak_node.type, pstyle)
            )
            peak_target.scatter(
                px, py,
                color=pstyle.get("color", "#333333"),
                alpha=pstyle.get("alpha", 0.9),
                marker="v", s=40, edgecolor="none",
                label=plabel, zorder=3,
            )

        # ── Axis labels (Plot Settings → Title and labels / Fonts) ───────────
        # ``mode = "auto"`` uses the unit-derived default; ``"custom"``
        # uses the user-supplied text; ``"none"`` (X/Y label rows do not
        # offer None — entry just goes empty if user clears it).
        auto_xlabels = {"nm":   "Wavelength (nm)",
                        "cm-1": "Wavenumber (cm⁻¹)",
                        "eV":   "Energy (eV)"}

        xlabel_mode = cfg.get("xlabel_mode", "auto")
        xlabel_text = (auto_xlabels.get(unit, unit)
                       if xlabel_mode == "auto"
                       else cfg.get("xlabel_text", ""))
        # Phase 4ak (CS-62): a non-empty per-axis override on
        # primary_x wins over the xlabel_mode/xlabel_text path. Empty
        # override (the factory default) defers to the existing auto/
        # custom resolution.
        primary_x_override = _axis_label_override(cfg, "primary_x")
        if primary_x_override:
            xlabel_text = primary_x_override
        ax.set_xlabel(
            xlabel_text,
            fontsize=cfg.get("xlabel_font_size", 10),
            fontweight=("bold" if cfg.get("xlabel_font_bold", True) else "normal"),
        )

        # Phase 4ad (CS-55): the renderer routes the y-axis label
        # through ``_resolve_y_axis_label`` once per populated role.
        # The first NodeType to land on each role drives the label;
        # absorbance-space NodeTypes (UVVIS / BASELINE / NORMALISED /
        # SMOOTHED / PEAK_LIST) label by y-unit, derivatives by
        # x-unit. ``ylabel_mode = "custom"`` is a primary-only
        # affordance — when set, the user's text wins for primary and
        # the loop below skips primary. Non-primary roles always use
        # the auto path. Roles whose first NodeType has no registered
        # label go unlabelled rather than guessing — strictly better
        # than the pre-Phase-4ad behaviour, which hard-coded primary's
        # ylabel from y-unit even when primary held a derivative or
        # was empty entirely.
        ylabel_mode      = cfg.get("ylabel_mode", "auto")
        ylabel_font_size = cfg.get("ylabel_font_size", 10)
        ylabel_bold      = cfg.get("ylabel_font_bold", True)
        ylabel_fontweight = "bold" if ylabel_bold else "normal"
        y_unit = self._y_unit.get()

        # Phase 4ak (CS-62): per-axis label overrides take precedence
        # over both the custom-text mode and the auto y-axis label
        # resolution. The primary Y override slots in here so a user
        # who sets "Custom label" on the primary_y tab gets it on
        # primary regardless of the legacy ylabel_mode/ylabel_text.
        primary_y_override = _axis_label_override(cfg, "primary_y")
        if primary_y_override:
            ax.set_ylabel(
                primary_y_override,
                fontsize=ylabel_font_size,
                fontweight=ylabel_fontweight,
            )
        elif ylabel_mode == "custom":
            ax.set_ylabel(
                cfg.get("ylabel_text", ""),
                fontsize=ylabel_font_size,
                fontweight=ylabel_fontweight,
            )

        for role, first_ntype in first_node_type_per_role.items():
            tab_role = _Y_AXIS_ROLE_TO_TAB.get(role)
            override = (
                _axis_label_override(cfg, tab_role) if tab_role else ""
            )
            if override:
                self._axes_by_role[role].set_ylabel(
                    override,
                    fontsize=ylabel_font_size,
                    fontweight=ylabel_fontweight,
                )
                continue
            if role == "primary" and (primary_y_override or ylabel_mode == "custom"):
                continue
            label_text = _resolve_y_axis_label(first_ntype, unit, y_unit)
            if label_text is None:
                continue
            self._axes_by_role[role].set_ylabel(
                label_text,
                fontsize=ylabel_font_size,
                fontweight=ylabel_fontweight,
            )

        # Title: "auto" has no UV/Vis-derivable default so it falls
        # through as no title; "custom" uses the user-entered text;
        # "none" (default factory value) suppresses the title entirely.
        title_mode = cfg.get("title_mode", "none")
        if title_mode == "custom":
            ax.set_title(
                cfg.get("title_text", ""),
                fontsize=cfg.get("title_font_size", 12),
                fontweight=("bold" if cfg.get("title_font_bold", True) else "normal"),
            )

        # Phase 4al: primary axis tick direction splits per axis-role.
        # Both x and y of the primary Axes inherit ``tick_label_font_size``
        # uniformly (it is a Global key), but the direction (in / out /
        # inout) reads from the per-axis-role slot. Non-primary roles
        # already inherited their per-role direction in ``get_axis`` at
        # creation time.
        ax.tick_params(
            axis="x",
            direction=_per_axis_tick_direction(cfg, "primary_x"),
            labelsize=tick_size,
        )
        ax.tick_params(
            axis="y",
            direction=_per_axis_tick_direction(cfg, "primary_y"),
            labelsize=tick_size,
        )

        # ── Secondary λ(nm) axis ──────────────────────────────────────────────
        # This is an x-axis sibling on the *top* spine of the primary
        # axis (different from the role-keyed y-axis machinery above);
        # it stays anchored to ``ax`` regardless of which roles are
        # populated below.
        #
        # CS-69 (Phase 4aq) B-005 fix: the secondary X axis is a
        # matplotlib LINKED axis via ``ax.secondary_xaxis(...,
        # functions=(_fwd, _fwd))`` — matplotlib derives ``sec``'s data
        # limits from ``ax``'s on every draw via the forward function.
        # The renderer must NEVER call ``sec.set_xlim`` /
        # ``sec.set_xscale``: either the call is a silent no-op or
        # (depending on matplotlib version) it severs the link and
        # leaves the wavelength axis stranded with stale values. The
        # per-axis ``range_lo`` / ``range_hi`` / ``autoscale`` /
        # ``scale`` schema keys for ``secondary_x`` therefore become
        # inert when the link is active — the dialog greys those
        # widgets out so the user can't fight the link (Phase 4aq).
        #
        # CS-69 (Phase 4aq) D8 relaxation: the link extends to both
        # ``unit == "cm-1"`` (via ``1e7 / x``) and ``unit == "eV"``
        # (via ``_HC_NM_EV / x``). Both transforms are self-inverse —
        # ``1e7 / (1e7 / x) == x`` and likewise for the eV constant —
        # which is why the same callable is passed for both slots of
        # ``functions=(...)``. The same ``_show_nm_axis`` Tk var gates
        # both branches; the toggle is a no-op in ``unit == "nm"``
        # (the primary axis is already λ in nm).
        if unit in ("cm-1", "eV") and self._show_nm_axis.get():
            if unit == "cm-1":
                _const = 1e7
            else:
                _const = _HC_NM_EV

            def _fwd(x, _c=_const):
                with np.errstate(divide="ignore", invalid="ignore"):
                    return np.where(np.asarray(x, float) > 0,
                                    _c / np.asarray(x, float), 0.0)
            sec = ax.secondary_xaxis("top", functions=(_fwd, _fwd))
            # Phase 4ak (CS-62): the secondary X label has no
            # historical user-facing control — its override is the
            # only customisation surface, so a non-empty value wins
            # outright. Empty (factory default) keeps the canonical
            # "λ (nm)" string.
            sec_x_override = _axis_label_override(cfg, "secondary_x")
            sec.set_xlabel(sec_x_override or "λ (nm)", fontsize=9)
            # Phase 4al: the previously-hardcoded ``direction="in"`` now
            # reads from the ``secondary_x`` per-axis slot so the user's
            # Plot Settings choice on the Secondary X tab applies. The
            # secondary-x tick label font size stays at 8pt (the
            # original hardcoded value); ``tick_label_font_size``
            # remains a primary-only key.
            sec.tick_params(
                axis="x",
                direction=_per_axis_tick_direction(cfg, "secondary_x"),
                labelsize=8,
            )

        # ── Invert nm axis ────────────────────────────────────────────────────
        if unit == "nm":
            # Mirror the per-node guard above: a malformed live entry
            # without wavelength_nm would crash the min/max computation.
            wl_nodes = [n for n in live if "wavelength_nm" in n.arrays]
            if wl_nodes:
                lo_nm = min(float(np.min(n.arrays["wavelength_nm"]))
                            for n in wl_nodes)
                hi_nm = max(float(np.max(n.arrays["wavelength_nm"]))
                            for n in wl_nodes)
                ax.set_xlim(hi_nm, lo_nm)

        # ── Apply per-axis scale + range (CS-64 Phase 4am) ────────────────────
        # Each axis role reads its own ``cfg["axes"][role]`` slot:
        # * ``scale`` ∈ {"linear", "log"} applied via set_xscale /
        #   set_yscale (linear = no-op effectively, matches default).
        # * ``autoscale=True`` (default) → renderer ignores schema
        #   range bounds; for primary_x / primary_y the legacy
        #   top-bar Tk vars (``_xlim_lo`` / ``_xlim_hi`` /
        #   ``_ylim_lo`` / ``_ylim_hi``) remain the fallback so the
        #   existing top-bar UX keeps working without a sync trace.
        # * ``autoscale=False`` → schema range_lo / range_hi clamp
        #   where non-empty; empty = leave bound as-is.
        # Twin Y-axes (secondary_y, tertiary_y) live in
        # ``self._axes_by_role`` keyed by CS-44 role ("secondary",
        # "tertiary"); their schema slots use the dialog's tab-role
        # keys ("secondary_y", "tertiary_y") — mapped through
        # :data:`_Y_AXIS_ROLE_TO_TAB`. Secondary X (wavelength-nm
        # sibling, ``sec``) is local to this block when active.

        # ---- Primary X ----
        ax.set_xscale(_per_axis_scale(cfg, "primary_x"))
        if _per_axis_autoscale(cfg, "primary_x"):
            # Legacy top-bar Entry fallback.
            lo_x = self._parse_lim(self._xlim_lo)
            hi_x = self._parse_lim(self._xlim_hi)
        else:
            lo_x = _parse_lim_str(_per_axis_range(cfg, "primary_x", "range_lo"))
            hi_x = _parse_lim_str(_per_axis_range(cfg, "primary_x", "range_hi"))
        if lo_x is not None or hi_x is not None:
            cur = ax.get_xlim()
            if unit == "nm":
                ax.set_xlim(hi_x if hi_x is not None else cur[0],
                            lo_x if lo_x is not None else cur[1])
            else:
                ax.set_xlim(lo_x if lo_x is not None else cur[0],
                            hi_x if hi_x is not None else cur[1])

        # ---- Primary Y ----
        ax.set_yscale(_per_axis_scale(cfg, "primary_y"))
        if _per_axis_autoscale(cfg, "primary_y"):
            lo_y = self._parse_lim(self._ylim_lo)
            hi_y = self._parse_lim(self._ylim_hi)
        else:
            lo_y = _parse_lim_str(_per_axis_range(cfg, "primary_y", "range_lo"))
            hi_y = _parse_lim_str(_per_axis_range(cfg, "primary_y", "range_hi"))
        if lo_y is not None or hi_y is not None:
            cur = ax.get_ylim()
            ax.set_ylim(lo_y if lo_y is not None else cur[0],
                        hi_y if hi_y is not None else cur[1])

        # ---- Twin Y-axes (secondary_y, tertiary_y) ----
        for y_role, tab_role in _Y_AXIS_ROLE_TO_TAB.items():
            if y_role == "primary":
                continue
            twin_ax = self._axes_by_role.get(y_role)
            if twin_ax is None:
                continue
            twin_ax.set_yscale(_per_axis_scale(cfg, tab_role))
            if _per_axis_autoscale(cfg, tab_role):
                continue
            lo_t = _parse_lim_str(_per_axis_range(cfg, tab_role, "range_lo"))
            hi_t = _parse_lim_str(_per_axis_range(cfg, tab_role, "range_hi"))
            if lo_t is not None or hi_t is not None:
                cur = twin_ax.get_ylim()
                twin_ax.set_ylim(
                    lo_t if lo_t is not None else cur[0],
                    hi_t if hi_t is not None else cur[1],
                )

        # ---- Secondary X (wavelength-nm sibling) ----
        # CS-69 (Phase 4aq) B-005 fix: the link via
        # ``ax.secondary_xaxis(..., functions=(_fwd, _fwd))`` is the
        # single source of truth for ``sec``'s xlim and xscale.
        # ``sec.set_xlim`` / ``sec.set_xscale`` are intentionally NOT
        # called here. The ``secondary_x`` schema's ``range_lo`` /
        # ``range_hi`` / ``autoscale`` / ``scale`` keys are inert when
        # the link is active; the dialog greys those widgets out so the
        # user can never push values into them while the link is live.
        # Pre-Phase-4aq projects with stale values on those keys simply
        # have them ignored — no migration needed.

        # ── Apply per-axis polish (CS-65 Phase 4an) ──────────────────────────
        # Tick spacing: empty / garbage / non-positive → keep
        # matplotlib's auto-locator (helpers return ``None``).
        # Non-empty positive float → ``MultipleLocator(value)``.
        # Axis colour: hex string applied to the per-role spine,
        # tick params (colour), and axis label colour. Applied AFTER
        # range/scale so the colour change doesn't get reset by a
        # subsequent set_xscale/set_yscale call.
        #
        # Primary X. CS-69: ``_apply_major_locator`` consults
        # ``custom_ticks`` first (FixedLocator wins outright when non-
        # empty) before falling through to ``tick_major``
        # MultipleLocator. Minor ticks unchanged.
        _apply_major_locator(ax.xaxis, cfg, "primary_x")
        minor = _per_axis_tick_minor(cfg, "primary_x")
        if minor is not None:
            ax.xaxis.set_minor_locator(MultipleLocator(minor))
        color_px = _per_axis_color(cfg, "primary_x")
        ax.spines["bottom"].set_color(color_px)
        ax.tick_params(axis="x", colors=color_px)
        ax.xaxis.label.set_color(color_px)

        # Primary Y. CS-69: same custom_ticks → tick_major fallthrough.
        _apply_major_locator(ax.yaxis, cfg, "primary_y")
        minor = _per_axis_tick_minor(cfg, "primary_y")
        if minor is not None:
            ax.yaxis.set_minor_locator(MultipleLocator(minor))
        color_py = _per_axis_color(cfg, "primary_y")
        ax.spines["left"].set_color(color_py)
        ax.tick_params(axis="y", colors=color_py)
        ax.yaxis.label.set_color(color_py)

        # Twin Y-axes (secondary_y, tertiary_y). Each twin has its
        # own right spine; tertiary's spine was already offset in
        # ``get_axis`` (CS-44).
        for y_role, tab_role in _Y_AXIS_ROLE_TO_TAB.items():
            if y_role == "primary":
                continue
            twin_ax = self._axes_by_role.get(y_role)
            if twin_ax is None:
                continue
            # CS-69: custom_ticks → tick_major fallthrough on each twin Y.
            _apply_major_locator(twin_ax.yaxis, cfg, tab_role)
            minor = _per_axis_tick_minor(cfg, tab_role)
            if minor is not None:
                twin_ax.yaxis.set_minor_locator(MultipleLocator(minor))
            color_t = _per_axis_color(cfg, tab_role)
            try:
                twin_ax.spines["right"].set_color(color_t)
            except (KeyError, AttributeError):
                pass
            twin_ax.tick_params(axis="y", colors=color_t)
            twin_ax.yaxis.label.set_color(color_t)

        # Secondary X (wavelength-nm sibling). Only present when the
        # linked-secondary block ran above (cm⁻¹ or eV + toggle ON).
        # CS-69 (Phase 4aq): ``custom_ticks`` is the user's primary
        # affordance for the wavelength axis — ``"300, 400, 500, 700,
        # 900"`` paints those specific nm positions via FixedLocator,
        # whereas ``MultipleLocator`` (fed from ``tick_major``) gives
        # evenly-spaced ticks in wavelength that don't land on
        # round numbers.
        if 'sec' in locals():
            _apply_major_locator(sec.xaxis, cfg, "secondary_x")
            minor = _per_axis_tick_minor(cfg, "secondary_x")
            if minor is not None:
                sec.xaxis.set_minor_locator(MultipleLocator(minor))
            color_sx = _per_axis_color(cfg, "secondary_x")
            sec.tick_params(axis="x", colors=color_sx)
            sec.xaxis.label.set_color(color_sx)

        # ── Legend (Plot Settings → Legend) ──────────────────────────────────
        # Phase 4u (CS-44): merge handles + labels across every
        # populated role so a single legend on the primary axis
        # describes both the absorbance traces and the secondary
        # derivative curve. ``ax.get_legend_handles_labels()`` only
        # picks up artists on its own Axes, so without this merge a
        # SECOND_DERIVATIVE node on the right axis would silently
        # drop out of the legend.
        all_handles: list = []
        all_labels: list = []
        for role_ax in self._axes_by_role.values():
            h, l = role_ax.get_legend_handles_labels()
            all_handles.extend(h)
            all_labels.extend(l)
        if all_handles and cfg.get("legend_show", True):
            ax.legend(
                all_handles, all_labels,
                fontsize=cfg.get("legend_font_size", 8),
                loc=cfg.get("legend_position", "best"),
                framealpha=0.7,
            )

        # ── Grid (Plot Settings → Appearance) ───────────────────────────────
        # Grid is drawn on primary only — gridlines from twin axes
        # would visually compete with the primary's grid. The grid
        # colour reads through the CS-56 ``grid_color`` key with the
        # matplotlib-standard light grey as the fallback. ``zorder=0``
        # is hard-coded (Phase 4ah) so gridlines paint BEHIND data
        # lines — matplotlib's default grid zorder (2.5) is above the
        # line collection's (2.0) and produces visually distracting
        # cross-hatching on dense overlays.
        # CS-65 (Phase 4an): the global ``cfg["grid"]`` master switch
        # still wins (False → no grid anywhere); when True, the per-axis
        # ``grid_show`` keys on ``primary_x`` and ``primary_y`` control
        # the x- and y-grid independently. Twin Y axes share the
        # primary's grid (matplotlib paints gridlines only on the host
        # Axes), so the renderer doesn't consult ``secondary_y`` /
        # ``tertiary_y`` ``grid_show`` even though the schema carries
        # them. CS-28 ``zorder=0`` invariant preserved on every
        # ``visible=True`` call so gridlines paint BEHIND data lines.
        #
        # matplotlib quirk: ``ax.grid(False, axis=..., linestyle=...)``
        # ENABLES the grid because the presence of styling kwargs
        # overrides the explicit ``visible=False``. So the per-axis
        # disable case calls ``ax.grid(False, axis=...)`` with NO
        # styling kwargs.
        if cfg.get("grid", True):
            grid_color = cfg.get("grid_color", "#b0b0b0")
            if _per_axis_grid(cfg, "primary_x"):
                ax.grid(
                    True, axis="x", linestyle=":", alpha=0.4,
                    color=grid_color, zorder=0,
                )
            else:
                ax.grid(False, axis="x")
            if _per_axis_grid(cfg, "primary_y"):
                ax.grid(
                    True, axis="y", linestyle=":", alpha=0.4,
                    color=grid_color, zorder=0,
                )
            else:
                ax.grid(False, axis="y")
        else:
            ax.grid(False)

        self._fig.tight_layout()
        self._canvas.draw_idle()
        self._toolbar.update()

    # ══════════════════════════════════════════════════════════════════════════
    #  Push to TDDFT overlay
    # ══════════════════════════════════════════════════════════════════════════

    def _send_node_to_compare(self, node_id: str) -> None:
        """Push a single node's spectrum into the TDDFT overlay.

        Phase 4n CS-27. Wired as ``send_to_compare_cb`` on the
        ScanTreeWidget so the per-row → icon dispatches to this
        method. The widget's disabled-state already gates on
        ``state == COMMITTED`` and on the callback being wired; this
        handler additionally surfaces the "no Compare host connected"
        case to the user via a messagebox so the affordance still
        feels live when the integration isn't available.
        """
        if self._add_scan_fn is None:
            messagebox.showinfo("Not available",
                                "No TDDFT plot connected to this panel.")
            return
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return
        if not isinstance(node, DataNode) or node.type != NodeType.UVVIS:
            return

        wl     = np.asarray(node.arrays["wavelength_nm"], dtype=float)
        absorb = np.asarray(node.arrays["absorbance"], dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            energy_ev = np.where(wl > 0, _HC_NM_EV / wl, 0.0)
        order     = np.argsort(energy_ev)
        energy_ev = energy_ev[order]
        absorb    = absorb[order]
        mask      = energy_ev > 0
        parser_md = node.metadata.get("parser_metadata", {})
        exp_scan  = ExperimentalScan(
            label=node.label,
            source_file=node.metadata.get("source_file", ""),
            energy_ev=energy_ev[mask],
            mu=absorb[mask],
            is_normalized=True,
            scan_type="UV/Vis absorbance",
            metadata=dict(
                parser_md,
                uvvis_source=node.metadata.get("source_file", ""),
            ),
        )
        self._add_scan_fn(exp_scan)

        self._status_lbl.config(
            text=f"Sent {node.label!r} to TDDFT overlay.",
            fg="#003d7a")
