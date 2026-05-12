"""Tests for plot_axis_hit_test.py (CS-60, Phase 4ai)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import plot_axis_hit_test as pah
from plot_axis_hit_test import AxisHit, classify_axis_double_click


# =====================================================================
# Test fixture helpers
# =====================================================================

class _StubBbox:
    """Stand-in for matplotlib's Bbox — only x0/x1/y0/y1 needed."""

    def __init__(self, x0: float, y0: float, x1: float, y1: float):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


class _StubAxes:
    """Stand-in for matplotlib.axes.Axes with a fixed window extent."""

    def __init__(self, bbox: _StubBbox):
        self._bbox = bbox

    def get_window_extent(self) -> _StubBbox:
        return self._bbox


def _ev(x: float, y: float, dblclick: bool = True) -> SimpleNamespace:
    """Build a MouseEvent-like stub."""
    return SimpleNamespace(x=x, y=y, dblclick=dblclick)


# Default primary axes: pixel rect (100, 100) → (700, 500).
# Plot interior occupies that rectangle; bands extend ±_TOTAL_BAND_PX
# beyond on every side.
_PRIMARY_BBOX = _StubBbox(100, 100, 700, 500)


def _primary_only() -> dict:
    return {"primary": _StubAxes(_PRIMARY_BBOX)}


def _primary_secondary() -> dict:
    return {
        "primary":   _StubAxes(_PRIMARY_BBOX),
        "secondary": _StubAxes(_PRIMARY_BBOX),
    }


def _primary_secondary_tertiary() -> dict:
    return {
        "primary":   _StubAxes(_PRIMARY_BBOX),
        "secondary": _StubAxes(_PRIMARY_BBOX),
        "tertiary":  _StubAxes(_PRIMARY_BBOX),
    }


# =====================================================================
# Sanity / contract
# =====================================================================

class TestAxisHitContract(unittest.TestCase):

    def test_axis_roles_tuple_shape(self):
        # Five roles, in canonical order. The dialog tab order in the
        # next commit relies on this.
        self.assertEqual(
            pah.AXIS_ROLES,
            ("primary_x", "secondary_x", "primary_y",
             "secondary_y", "tertiary_y"),
        )

    def test_hit_kinds_tuple_shape(self):
        self.assertEqual(
            pah.HIT_KINDS,
            ("spine", "tick_labels", "axis_label"),
        )

    def test_axishit_is_frozen_dataclass(self):
        hit = AxisHit("primary_x", "spine")
        with self.assertRaises(Exception):
            hit.role = "primary_y"  # type: ignore[misc]


# =====================================================================
# Reject paths
# =====================================================================

class TestRejectPaths(unittest.TestCase):

    def test_single_click_returns_none(self):
        # Even when the coords land squarely on the bottom-x band, a
        # single-click does not open the dialog.
        result = classify_axis_double_click(
            _ev(400, 90, dblclick=False), _primary_only(),
        )
        self.assertIsNone(result)

    def test_missing_dblclick_attribute_returns_none(self):
        # Bare object with no dblclick attribute: treated as single.
        event = SimpleNamespace(x=400, y=90)
        self.assertIsNone(
            classify_axis_double_click(event, _primary_only()),
        )

    def test_missing_primary_returns_none(self):
        self.assertIsNone(
            classify_axis_double_click(_ev(400, 90), {}),
        )

    def test_no_xy_coords_returns_none(self):
        event = SimpleNamespace(dblclick=True, x=None, y=None)
        self.assertIsNone(
            classify_axis_double_click(event, _primary_only()),
        )

    def test_malformed_xy_returns_none(self):
        event = SimpleNamespace(dblclick=True, x="nope", y="bad")
        self.assertIsNone(
            classify_axis_double_click(event, _primary_only()),
        )

    def test_degenerate_bbox_returns_none(self):
        # bbox with zero width
        ax = _StubAxes(_StubBbox(100, 100, 100, 500))
        self.assertIsNone(
            classify_axis_double_click(_ev(50, 300), {"primary": ax}),
        )

    def test_click_in_plot_interior_returns_none(self):
        # Smack in the middle of the plot bbox: no axis tab.
        self.assertIsNone(
            classify_axis_double_click(_ev(400, 300), _primary_only()),
        )

    def test_click_far_outside_returns_none(self):
        # Well past every envelope.
        self.assertIsNone(
            classify_axis_double_click(_ev(9000, 9000), _primary_only()),
        )

    def test_click_just_outside_bottom_envelope_returns_none(self):
        # y = y0 - _TOTAL_BAND_PX - 1 → outside the bottom band.
        ey = _PRIMARY_BBOX.y0 - pah._TOTAL_BAND_PX - 1
        self.assertIsNone(
            classify_axis_double_click(_ev(400, ey), _primary_only()),
        )


# =====================================================================
# Bottom (primary x)
# =====================================================================

class TestPrimaryX(unittest.TestCase):

    def test_spine_band(self):
        # ey just below y0 → spine band.
        ey = _PRIMARY_BBOX.y0 - 2
        hit = classify_axis_double_click(_ev(400, ey), _primary_only())
        self.assertEqual(hit, AxisHit("primary_x", "spine"))

    def test_tick_labels_band(self):
        ey = _PRIMARY_BBOX.y0 - (pah._SPINE_BAND_PX + 5)
        hit = classify_axis_double_click(_ev(400, ey), _primary_only())
        self.assertEqual(hit, AxisHit("primary_x", "tick_labels"))

    def test_axis_label_band(self):
        ey = _PRIMARY_BBOX.y0 - (pah._TICK_BAND_PX + 5)
        hit = classify_axis_double_click(_ev(400, ey), _primary_only())
        self.assertEqual(hit, AxisHit("primary_x", "axis_label"))

    def test_outside_x_range_returns_none(self):
        # Below the bbox vertically, but to the left of x0.
        ey = _PRIMARY_BBOX.y0 - 5
        self.assertIsNone(
            classify_axis_double_click(_ev(50, ey), _primary_only()),
        )


# =====================================================================
# Top (secondary x — reserved)
# =====================================================================

class TestSecondaryX(unittest.TestCase):

    def test_spine_band(self):
        ey = _PRIMARY_BBOX.y1 + 2
        hit = classify_axis_double_click(_ev(400, ey), _primary_only())
        self.assertEqual(hit, AxisHit("secondary_x", "spine"))

    def test_tick_labels_band(self):
        ey = _PRIMARY_BBOX.y1 + (pah._SPINE_BAND_PX + 5)
        hit = classify_axis_double_click(_ev(400, ey), _primary_only())
        self.assertEqual(hit, AxisHit("secondary_x", "tick_labels"))

    def test_axis_label_band(self):
        ey = _PRIMARY_BBOX.y1 + (pah._TICK_BAND_PX + 5)
        hit = classify_axis_double_click(_ev(400, ey), _primary_only())
        self.assertEqual(hit, AxisHit("secondary_x", "axis_label"))


# =====================================================================
# Left (primary y)
# =====================================================================

class TestPrimaryY(unittest.TestCase):

    def test_spine_band(self):
        ex = _PRIMARY_BBOX.x0 - 2
        hit = classify_axis_double_click(_ev(ex, 300), _primary_only())
        self.assertEqual(hit, AxisHit("primary_y", "spine"))

    def test_tick_labels_band(self):
        ex = _PRIMARY_BBOX.x0 - (pah._SPINE_BAND_PX + 5)
        hit = classify_axis_double_click(_ev(ex, 300), _primary_only())
        self.assertEqual(hit, AxisHit("primary_y", "tick_labels"))

    def test_axis_label_band(self):
        ex = _PRIMARY_BBOX.x0 - (pah._TICK_BAND_PX + 5)
        hit = classify_axis_double_click(_ev(ex, 300), _primary_only())
        self.assertEqual(hit, AxisHit("primary_y", "axis_label"))

    def test_outside_y_range_returns_none(self):
        # Left of bbox but below y0 → not a primary-y hit (and not in
        # the bottom band either since ex < x0).
        ex = _PRIMARY_BBOX.x0 - 5
        ey = _PRIMARY_BBOX.y0 - 5
        self.assertIsNone(
            classify_axis_double_click(_ev(ex, ey), _primary_only()),
        )


# =====================================================================
# Right side — no twinx (= primary y's right spine)
# =====================================================================

class TestPrimaryYRightSpine(unittest.TestCase):
    """When no secondary is present, clicks on the right side hit primary_y."""

    def test_right_spine_with_no_twinx_maps_to_primary_y(self):
        ex = _PRIMARY_BBOX.x1 + 2
        hit = classify_axis_double_click(_ev(ex, 300), _primary_only())
        self.assertEqual(hit, AxisHit("primary_y", "spine"))

    def test_right_tick_labels_with_no_twinx_maps_to_primary_y(self):
        ex = _PRIMARY_BBOX.x1 + (pah._SPINE_BAND_PX + 5)
        hit = classify_axis_double_click(_ev(ex, 300), _primary_only())
        self.assertEqual(hit, AxisHit("primary_y", "tick_labels"))

    def test_right_axis_label_with_no_twinx_maps_to_primary_y(self):
        ex = _PRIMARY_BBOX.x1 + (pah._TICK_BAND_PX + 5)
        hit = classify_axis_double_click(_ev(ex, 300), _primary_only())
        self.assertEqual(hit, AxisHit("primary_y", "axis_label"))


# =====================================================================
# Right side — with secondary y (twinx present)
# =====================================================================

class TestSecondaryY(unittest.TestCase):

    def test_spine_band_with_secondary(self):
        ex = _PRIMARY_BBOX.x1 + 2
        hit = classify_axis_double_click(_ev(ex, 300), _primary_secondary())
        self.assertEqual(hit, AxisHit("secondary_y", "spine"))

    def test_tick_labels_band_with_secondary(self):
        ex = _PRIMARY_BBOX.x1 + (pah._SPINE_BAND_PX + 5)
        hit = classify_axis_double_click(_ev(ex, 300), _primary_secondary())
        self.assertEqual(hit, AxisHit("secondary_y", "tick_labels"))


# =====================================================================
# Tertiary y (offset spine at axes-x = 1.12)
# =====================================================================

class TestTertiaryY(unittest.TestCase):

    def test_spine_band_at_offset(self):
        width = _PRIMARY_BBOX.x1 - _PRIMARY_BBOX.x0
        tertiary_spine = _PRIMARY_BBOX.x0 + 1.12 * width
        hit = classify_axis_double_click(
            _ev(tertiary_spine, 300), _primary_secondary_tertiary(),
        )
        self.assertEqual(hit, AxisHit("tertiary_y", "spine"))

    def test_tick_labels_band_at_offset(self):
        width = _PRIMARY_BBOX.x1 - _PRIMARY_BBOX.x0
        tertiary_spine = _PRIMARY_BBOX.x0 + 1.12 * width
        ex = tertiary_spine + (pah._SPINE_BAND_PX + 2)
        hit = classify_axis_double_click(
            _ev(ex, 300), _primary_secondary_tertiary(),
        )
        self.assertEqual(hit, AxisHit("tertiary_y", "tick_labels"))

    def test_axis_label_band_at_offset(self):
        width = _PRIMARY_BBOX.x1 - _PRIMARY_BBOX.x0
        tertiary_spine = _PRIMARY_BBOX.x0 + 1.12 * width
        ex = tertiary_spine + (pah._TICK_BAND_PX + 2)
        hit = classify_axis_double_click(
            _ev(ex, 300), _primary_secondary_tertiary(),
        )
        self.assertEqual(hit, AxisHit("tertiary_y", "axis_label"))

    def test_tertiary_offset_frac_argument_overrides_default(self):
        # Move the tertiary spine to axes-x = 1.30 instead of 1.12.
        width = _PRIMARY_BBOX.x1 - _PRIMARY_BBOX.x0
        tertiary_spine = _PRIMARY_BBOX.x0 + 1.30 * width
        hit = classify_axis_double_click(
            _ev(tertiary_spine, 300),
            _primary_secondary_tertiary(),
            tertiary_offset_frac=1.30,
        )
        self.assertEqual(hit, AxisHit("tertiary_y", "spine"))


# =====================================================================
# Tertiary precedence — secondary band clipped at tertiary spine
# =====================================================================

class TestSecondaryClippedByTertiary(unittest.TestCase):
    """When both secondary and tertiary exist, clicks near the tertiary
    spine must classify as tertiary, not as secondary."""

    def test_click_near_tertiary_classifies_as_tertiary(self):
        width = _PRIMARY_BBOX.x1 - _PRIMARY_BBOX.x0
        tertiary_spine = _PRIMARY_BBOX.x0 + 1.12 * width
        # Slightly left of tertiary spine (still in tertiary band).
        ex = tertiary_spine - 3
        hit = classify_axis_double_click(
            _ev(ex, 300), _primary_secondary_tertiary(),
        )
        self.assertEqual(hit.role, "tertiary_y")

    def test_click_in_secondary_band_well_left_of_tertiary(self):
        # 3px outside primary bbox right edge — well left of tertiary.
        ex = _PRIMARY_BBOX.x1 + 3
        hit = classify_axis_double_click(
            _ev(ex, 300), _primary_secondary_tertiary(),
        )
        self.assertEqual(hit.role, "secondary_y")


# =====================================================================
# Edge case — bbox exactly at envelope boundary
# =====================================================================

class TestBoundaryConditions(unittest.TestCase):

    def test_ey_exactly_y0_is_primary_x_spine(self):
        # On the spine line itself.
        hit = classify_axis_double_click(
            _ev(400, _PRIMARY_BBOX.y0), _primary_only(),
        )
        self.assertEqual(hit, AxisHit("primary_x", "spine"))

    def test_ex_exactly_x0_is_primary_y_spine(self):
        hit = classify_axis_double_click(
            _ev(_PRIMARY_BBOX.x0, 300), _primary_only(),
        )
        self.assertEqual(hit, AxisHit("primary_y", "spine"))

    def test_corner_belongs_to_bottom_first(self):
        # Pixel directly at (x0, y0): the bottom band is tested before
        # the left band, so this classifies as primary_x.
        hit = classify_axis_double_click(
            _ev(_PRIMARY_BBOX.x0, _PRIMARY_BBOX.y0), _primary_only(),
        )
        self.assertEqual(hit.role, "primary_x")


if __name__ == "__main__":
    unittest.main()
