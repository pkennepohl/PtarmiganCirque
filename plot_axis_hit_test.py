"""Hit-test classifier for matplotlib axis-region double-clicks (CS-60, Phase 4ai).

Spec
----
Part of the CS-60 unified Plot Config dialog initiative. When the user
double-clicks anywhere in the UV/Vis plot, this module decides whether
the click landed in an *axis region* (a spine, its tick labels, or its
axis label) and, if so, which of the five axis roles (primary_x,
secondary_x, primary_y, secondary_y, tertiary_y) the gesture targets.
A click in the interior plot area, or anywhere outside an axis region,
returns ``None`` and the caller leaves the dialog closed.

Decisions taken here
--------------------
* **Bbox-relative hit-test, not ``event.inaxes``.** When axes share a
  bbox via ``twinx`` the topmost axes wins ``event.inaxes`` regardless
  of which spine the user aimed at, so we can't distinguish primary
  vs secondary y from that. Instead we compute display-pixel zones
  relative to the primary axes' ``get_window_extent()``: each axis
  role owns one rectangular band of figure pixels (left of bbox,
  right of bbox, below bbox, above bbox, near the tertiary offset
  spine), and the click is classified by which band contains it.

* **Tertiary spine band priority.** When a tertiary axis exists, its
  spine sits at axes-x = ``tertiary_offset_frac`` (default 1.12,
  matching CS-44 ``_TERTIARY_AXIS_OFFSET_FRAC``). We test that band
  first so the secondary-y band gets clipped at the tertiary spine
  rather than swallowing it.

* **Hit kind = spine | tick_labels | axis_label.** Three bands per
  side, picked by perpendicular distance from the spine: the first
  ``_SPINE_BAND_PX`` pixels are the spine, the next
  ``_TICK_BAND_PX`` are tick-label territory, and the rest of the
  ``_TOTAL_BAND_PX`` envelope is axis-label territory. ``hit_kind``
  is a soft hint — every double-click on the same axis opens the same
  tab in the dialog regardless of which sub-band landed.

* **Secondary x is reserved.** The figure today has only a primary x
  axis (CS-44). Clicks in the top-of-bbox band still classify as
  ``secondary_x`` so the dialog can open the secondary-X tab —
  greyed-out today, populated when the wavelength↔energy twin-x
  lands in a future phase.

* **No matplotlib import at module top.** ``Bbox``-style access only;
  the function reads ``event.x / event.y / event.dblclick`` and the
  primary axes' ``get_window_extent`` duck-typed. This keeps the
  module test-friendly without standing up a Figure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


# =====================================================================
# Constants
# =====================================================================

# Pixel envelope around each axis side that we consider "axis region".
# Outside this envelope a double-click is treated as plot-interior and
# returns None. 40px ≈ the visual height of a typical tick-label band
# plus axis-label band together.
_TOTAL_BAND_PX: int = 40

# Inner sub-band: clicks within this many pixels of the spine line are
# classified as ``hit_kind = "spine"``.
_SPINE_BAND_PX: int = 6

# Middle sub-band: clicks beyond the spine band but within this much
# of the spine are ``hit_kind = "tick_labels"``.
_TICK_BAND_PX: int = 18

# Tertiary spine envelope. The tertiary axis lives at axes-x =
# ``tertiary_offset_frac`` — a vertical band of this many pixels each
# side of the spine catches the spine + ticks + label region.
_TERTIARY_BAND_PX: int = 24


# =====================================================================
# Public types
# =====================================================================

# Five named axis roles. The X-secondary slot is currently reserved
# (no figure data routes there today, but the dialog has a tab for
# it). Y roles match CS-44's ``_AXIS_ROLES`` but spelled out as
# ``primary_y`` etc. so the X / Y split is unambiguous at call sites.
AXIS_ROLES: tuple[str, ...] = (
    "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y",
)

HIT_KINDS: tuple[str, ...] = ("spine", "tick_labels", "axis_label")


@dataclass(frozen=True)
class AxisHit:
    """Result of an axis-region double-click classification.

    ``role`` is one of :data:`AXIS_ROLES`. ``hit_kind`` is one of
    :data:`HIT_KINDS` and is a soft hint (the dialog opens the same
    tab for any of the three). ``hit_kind`` is preserved so future
    telemetry / refined behaviour can branch on it without changing
    the signature.
    """
    role: str
    hit_kind: str


# =====================================================================
# Classifier
# =====================================================================

def classify_axis_double_click(
    event: Any,
    axes_by_role: Mapping[str, Any],
    tertiary_offset_frac: float = 1.12,
) -> Optional[AxisHit]:
    """Decide whether a matplotlib ``button_press_event`` hit an axis region.

    Parameters
    ----------
    event
        A matplotlib ``MouseEvent``-like object. Must expose
        ``.dblclick`` (bool), ``.x`` and ``.y`` (figure pixel coords,
        bottom-left origin). Single-clicks return ``None``.
    axes_by_role
        Mapping ``role → matplotlib.axes.Axes``. CS-44 keys
        (``"primary"``, ``"secondary"``, ``"tertiary"``). Only
        ``"primary"`` is required; the others are optional and
        merely affect the right-side classification. The primary
        axes' ``get_window_extent()`` defines every band.
    tertiary_offset_frac
        Where the tertiary spine lives in axes-coords (matches the
        CS-44 module constant). Default 1.12.

    Returns
    -------
    AxisHit or None
        ``AxisHit(role, hit_kind)`` if the click landed in an axis
        region, otherwise ``None`` (single-click, no primary axes,
        click in plot interior, click outside the figure, malformed
        event).
    """
    # Reject single-clicks. Matplotlib events fire both press
    # callbacks for the second click in a double-click sequence; the
    # second one carries ``dblclick=True``.
    if not getattr(event, "dblclick", False):
        return None

    primary = axes_by_role.get("primary")
    if primary is None:
        return None

    # Pull the primary bbox in display pixels. If get_window_extent
    # isn't callable (test stub) or returns malformed data, bail.
    try:
        bbox = primary.get_window_extent()
        x0, x1 = float(bbox.x0), float(bbox.x1)
        y0, y1 = float(bbox.y0), float(bbox.y1)
    except (AttributeError, TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None

    # Event pixel coords. Both ``.x`` and ``.y`` are floats in
    # matplotlib's bottom-left origin convention. None means
    # "outside the canvas".
    ex = getattr(event, "x", None)
    ey = getattr(event, "y", None)
    if ex is None or ey is None:
        return None
    try:
        ex = float(ex)
        ey = float(ey)
    except (TypeError, ValueError):
        return None

    width = x1 - x0

    # ── Tertiary y band ───────────────────────────────────────────
    # Test FIRST so the secondary-y band gets clipped at the
    # tertiary spine. The tertiary spine sits at
    # x = x0 + tertiary_offset_frac * width; a band of
    # ±_TERTIARY_BAND_PX around it counts as a tertiary hit.
    tertiary = axes_by_role.get("tertiary")
    if tertiary is not None:
        tertiary_spine_x = x0 + tertiary_offset_frac * width
        in_y_range = y0 <= ey <= y1
        if in_y_range:
            dist_to_tertiary = ex - tertiary_spine_x
            if -_TERTIARY_BAND_PX <= dist_to_tertiary <= _TERTIARY_BAND_PX:
                if abs(dist_to_tertiary) <= _SPINE_BAND_PX:
                    return AxisHit("tertiary_y", "spine")
                if abs(dist_to_tertiary) <= _TICK_BAND_PX:
                    return AxisHit("tertiary_y", "tick_labels")
                return AxisHit("tertiary_y", "axis_label")

    # ── Bottom (primary x) ────────────────────────────────────────
    # Below the bbox baseline, within the x-range. First band is
    # spine, next is tick labels, beyond is axis label.
    if x0 <= ex <= x1 and y0 - _TOTAL_BAND_PX <= ey <= y0:
        d = y0 - ey
        if d <= _SPINE_BAND_PX:
            return AxisHit("primary_x", "spine")
        if d <= _TICK_BAND_PX:
            return AxisHit("primary_x", "tick_labels")
        return AxisHit("primary_x", "axis_label")

    # ── Top (secondary x — reserved) ──────────────────────────────
    if x0 <= ex <= x1 and y1 <= ey <= y1 + _TOTAL_BAND_PX:
        d = ey - y1
        if d <= _SPINE_BAND_PX:
            return AxisHit("secondary_x", "spine")
        if d <= _TICK_BAND_PX:
            return AxisHit("secondary_x", "tick_labels")
        return AxisHit("secondary_x", "axis_label")

    # ── Left (primary y) ──────────────────────────────────────────
    if y0 <= ey <= y1 and x0 - _TOTAL_BAND_PX <= ex <= x0:
        d = x0 - ex
        if d <= _SPINE_BAND_PX:
            return AxisHit("primary_y", "spine")
        if d <= _TICK_BAND_PX:
            return AxisHit("primary_y", "tick_labels")
        return AxisHit("primary_y", "axis_label")

    # ── Right side (secondary y, or primary y's right spine) ─────
    # If a tertiary axis exists, the secondary band stops just left
    # of the tertiary spine; otherwise it extends the full envelope.
    if y0 <= ey <= y1 and x1 <= ex:
        right_limit = x1 + _TOTAL_BAND_PX
        if tertiary is not None:
            tertiary_spine_x = x0 + tertiary_offset_frac * width
            right_limit = min(right_limit, tertiary_spine_x - _TERTIARY_BAND_PX)
        if ex <= right_limit:
            secondary = axes_by_role.get("secondary")
            target_role = "secondary_y" if secondary is not None else "primary_y"
            d = ex - x1
            if d <= _SPINE_BAND_PX:
                return AxisHit(target_role, "spine")
            if d <= _TICK_BAND_PX:
                return AxisHit(target_role, "tick_labels")
            return AxisHit(target_role, "axis_label")

    # Interior plot area, or beyond every envelope. No tab opens.
    return None
