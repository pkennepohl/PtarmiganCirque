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
    "pick_default_color",
]


# Keys present in every dict returned by :func:`default_spectrum_style`.
# Tests can use this to assert that callers haven't drifted from the
# shared schema.
DEFAULT_SPECTRUM_STYLE_KEYS: tuple[str, ...] = (
    "color",
    "linestyle",
    "linewidth",
    "alpha",
    "visible",
    "in_legend",
    "fill",
    "fill_alpha",
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
    """
    total = 0
    for node_type in SPECTRUM_PALETTE_NODE_TYPES:
        total += len(graph.nodes_of_type(node_type, state=None))
    return SPECTRUM_PALETTE[total % len(SPECTRUM_PALETTE)]
