"""Shared style defaults for spectrum-producing operations.

This module hosts a single source of truth for the ``DataNode.style``
dict written into a freshly-created spectrum-shaped node (UVVIS,
BASELINE, NORMALISED, SMOOTHED, ...). Each spectrum-producing caller
imports :func:`default_spectrum_style` rather than maintaining its own
copy. Resolves the multi-caller default-style duplication that
Phase 4c friction #5, Phase 4d friction #3, and Phase 4e friction #1
flagged: the four-caller threshold for extraction lands with
Phase 4g (Smoothing — fourth spectrum-producing operation).

The function returns the eight universal style keys (mirrors the
keys that ``scan_tree_widget._DEFAULT_STYLE`` and
``style_dialog._UNIVERSAL_DEFAULTS`` cover, in lockstep). Those two
UI-side maps are intentionally kept adjacent to the widgets that read
them — they are fallbacks consulted when ``node.style`` is missing a
key, not factory dicts for fresh node creation, and the role
difference outweighs the sync risk for those two callers. Should a
fifth or sixth caller appear (e.g. XANES smoothing, deglitch on
UV/Vis), the same import lands in one line.

Phase 4j (CS-21) folds the second long-running duplication into this
module: the ten-colour default palette and the "next colour" picker
that every spectrum-creating call site used to roll by hand. Pre-4j
there were SIX copies of ``_PALETTE`` (uvvis_tab + four operation
modules) and SIX subtly different palette-index expressions (each
``_apply`` walked a slightly different subset of NodeTypes).
:data:`SPECTRUM_PALETTE` is the single source of truth and
:func:`pick_default_color` walks every spectrum-shaped NodeType
(UVVIS, BASELINE, NORMALISED, SMOOTHED, SECOND_DERIVATIVE, PEAK_LIST)
in one go so every caller can collapse to::

    colour = pick_default_color(self._graph)
"""

from __future__ import annotations

from typing import Any

from graph import ProjectGraph
from nodes import NodeType


__all__ = [
    "default_spectrum_style",
    "DEFAULT_SPECTRUM_STYLE_KEYS",
    "SPECTRUM_PALETTE",
    "SPECTRUM_PALETTE_NODE_TYPES",
    "SPECTRUM_PALETTE_NAMES",
    "WONG_2011_PALETTE",
    "active_palette",
    "set_active_palette",
    "pick_default_color",
]


# Keys present in every dict returned by :func:`default_spectrum_style`.
# Tests can use this to assert that callers haven't drifted from the
# shared schema.
#
# Phase 4y (CS-50): ``y_axis`` joins as the per-style override hook for
# CS-44 multi-axis routing. Default ``None`` means "follow my NodeType
# default" (the literal :func:`uvvis_tab._resolve_y_axis_role` fallback);
# a non-None value (one of the CS-44 axis roles) overrides the routing
# per-node. Persistence (CS-46) auto-rides the existing style-dict
# round-trip — no manifest schema change.
DEFAULT_SPECTRUM_STYLE_KEYS: tuple[str, ...] = (
    "color",
    "linestyle",
    "linewidth",
    "alpha",
    "visible",
    "in_legend",
    "fill",
    "fill_alpha",
    "y_axis",
)


def default_spectrum_style(colour: str) -> dict[str, Any]:
    """Return the default ``DataNode.style`` for a fresh spectrum node.

    ``colour`` is the only per-node value: callers pick it from the
    palette so a parent and its derivatives are visually distinct.
    Every other key carries the fixed factory default.
    """
    return {
        "color":      colour,
        "linestyle":  "solid",
        "linewidth":  1.5,
        "alpha":      0.9,
        "visible":    True,
        "in_legend":  True,
        "fill":       False,
        "fill_alpha": 0.08,
        # Phase 4y (CS-50): per-style y-axis override hook. ``None`` =
        # follow the per-NodeType default in
        # ``uvvis_tab._DEFAULT_Y_AXIS_BY_NODETYPE``; a non-None value
        # ("primary" / "secondary" / "tertiary") overrides per-node.
        "y_axis":     None,
    }


# ---------------------------------------------------------------------------
# Palette + next-colour picker (Phase 4j, CS-21)
# ---------------------------------------------------------------------------

# The shared ten-entry default palette. Pre-4j each spectrum-creating
# module carried its own copy of this literal; CS-21 consolidates to
# this single tuple. Tuple (not list) so callers cannot mutate it.
SPECTRUM_PALETTE: tuple[str, ...] = (
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
)


# ---------------------------------------------------------------------------
# Phase 4ay (CS-75 D2 / sub-axis B): colour-blind palette opt-in
# ---------------------------------------------------------------------------
#
# Wong (2011) "Points of view: Color blindness" (Nature Methods 8, 441).
# Eight-colour qualitative palette engineered to remain distinguishable
# under deuteranopia and protanopia (red/green colour-vision deficiencies,
# the two most common types). Tuple (not list) so callers cannot mutate.
# Order matches the Wong figure left-to-right.
WONG_2011_PALETTE: tuple[str, ...] = (
    "#000000",  # black
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#F0E442",  # yellow
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
)


# Canonical palette name → palette tuple. Adding a new palette is a
# single insert here plus an entry in :data:`SPECTRUM_PALETTE_NAMES`.
# ``"default"`` aliases :data:`SPECTRUM_PALETTE` so the pre-Phase-4ay
# behaviour is the unchanged factory default and CS-21 D3's
# additive-relaxation contract holds: SPECTRUM_PALETTE is still the
# 10-entry tuple every external reader has always seen.
_PALETTES: dict[str, tuple[str, ...]] = {
    "default":   SPECTRUM_PALETTE,
    "wong_2011": WONG_2011_PALETTE,
}


# Valid palette names. Surfaced as the Combobox values on the new
# Accessibility tab in :class:`plot_settings_dialog.PlotConfigDialog`.
SPECTRUM_PALETTE_NAMES: tuple[str, ...] = ("default", "wong_2011")


# Active palette name. Process-lifetime mutable; updated by
# :func:`set_active_palette` from the dialog's commit-on-click path
# and from binah.py's project-load path (after the manifest's
# ``plot_defaults["accessibility"]["palette"]`` slot restores the
# user's choice into ``plot_settings_dialog._USER_DEFAULTS``).
_active_palette_name: str = "default"


def active_palette() -> tuple[str, ...]:
    """Return the palette tuple currently selected by the user.

    :func:`pick_default_color` consults this getter on every call so
    the three pre-existing call sites (uvvis_tab, uvvis_peak_picking,
    uvvis_second_derivative) become palette-aware "for free" without
    any per-call-site edit. Defaults to :data:`SPECTRUM_PALETTE` when
    no palette opt-in is active.

    Phase 4ay CS-75 D2 recipe.
    """
    return _PALETTES[_active_palette_name]


def set_active_palette(name: str) -> None:
    """Switch the active palette by name.

    ``name`` must be one of :data:`SPECTRUM_PALETTE_NAMES`. Unknown
    names fall back to ``"default"`` silently — a defensive choice
    because the load path may surface a value written by a future
    version of the app, and the renderer should keep painting with
    the legacy palette rather than crash on an unknown key.

    Phase 4ay CS-75 D2 recipe.
    """
    global _active_palette_name
    if name in _PALETTES:
        _active_palette_name = name
    else:
        _active_palette_name = "default"


# NodeTypes whose existence consumes a palette slot. Every spectrum-
# shaped node creation site (UVVIS load, BASELINE / NORMALISED /
# SMOOTHED / SECOND_DERIVATIVE _apply) plus the PEAK_LIST creation site
# in uvvis_peak_picking goes through :func:`pick_default_color`, so all
# six NodeTypes share a single deterministic counter. The counter walks
# every state (provisional + committed + discarded) so a discarded node
# does not free up its palette slot — colours stay sticky across an
# undo/redo round trip and across project save/load.
SPECTRUM_PALETTE_NODE_TYPES: tuple[NodeType, ...] = (
    NodeType.UVVIS,
    NodeType.BASELINE,
    NodeType.NORMALISED,
    NodeType.SMOOTHED,
    NodeType.SECOND_DERIVATIVE,
    NodeType.PEAK_LIST,
)


def pick_default_color(graph: ProjectGraph) -> str:
    """Return the next default palette colour for a fresh spectrum node.

    The rule is simple and deterministic: count every existing node
    of any type in :data:`SPECTRUM_PALETTE_NODE_TYPES` (across all
    states), modulo into :data:`SPECTRUM_PALETTE`, and return the
    resulting hex string. Callers pass the returned colour to
    :func:`default_spectrum_style` (or, for PEAK_LIST, into the
    annotation-style factory) so the new node lands with a colour
    visually distinct from the chain of nodes already in the graph.

    Pre-4j, each spectrum-creating module rolled its own version of
    this expression with a slightly different subset of NodeTypes
    (uvvis_tab counted UVVIS only; uvvis_peak_picking counted UVVIS +
    BASELINE + NORMALISED + SMOOTHED + PEAK_LIST; uvvis_second_derivative
    counted UVVIS + BASELINE + NORMALISED + SMOOTHED + SECOND_DERIVATIVE
    — the latter two never aware of each other). CS-21 unifies on the
    full six-NodeType walk so every caller picks against the same
    counter and the next-colour rule is order-independent.

    Empty graph → first palette entry. Walks past the palette length
    wrap with modulo.

    Phase 4ay (CS-75 D2 / sub-axis B): internals consult
    :func:`active_palette` so the three call sites become palette-aware
    without per-site edits. External return type unchanged — still a
    hex string. CS-21 D3 additive relaxation: SPECTRUM_PALETTE itself
    is unchanged; this function now picks against whichever palette
    the user has opted into.
    """
    palette = active_palette()
    total = 0
    for node_type in SPECTRUM_PALETTE_NODE_TYPES:
        total += len(graph.nodes_of_type(node_type, state=None))
    return palette[total % len(palette)]
