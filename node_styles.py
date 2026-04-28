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
"""

from __future__ import annotations

from typing import Any


__all__ = [
    "default_spectrum_style",
    "DEFAULT_SPECTRUM_STYLE_KEYS",
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
