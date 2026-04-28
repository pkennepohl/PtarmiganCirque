"""Tests for uvvis_baseline.py.

Pure module — no Tk required. Each mode is exercised against a
synthetic Gaussian-on-background spectrum where the underlying peak
height is known; the recovered peak after baseline subtraction must
match the truth within the tolerance appropriate for that mode.
"""

from __future__ import annotations

import unittest

import numpy as np

import uvvis_baseline as ub


def _gaussian(wl, center, sigma, height=1.0):
    return height * np.exp(-((wl - center) / sigma) ** 2)


class TestLinearMode(unittest.TestCase):

    def test_recovers_peak_on_linear_background(self):
        # Gaussian peak at 500 with FWHM ~60 nm (sigma ~25.5).
        wl = np.linspace(200.0, 800.0, 601)
        peak = _gaussian(wl, 500.0, 25.5, height=1.0)
        bg = 0.10 + 0.0005 * wl
        spectrum = peak + bg
        # Anchors at the spectrum extremes — the Gaussian has decayed
        # to numerically zero there, so the linear baseline equals the
        # underlying linear background almost exactly.
        out = ub.compute_linear(
            wl, spectrum,
            {"anchor_lo_nm": 200.0, "anchor_hi_nm": 800.0},
        )
        # Peak height of the recovered spectrum.
        self.assertAlmostEqual(float(out.max()), 1.0, places=6)
        # Off-peak values are essentially zero (residual baseline).
        self.assertLess(float(np.abs(out[wl < 300]).max()), 1e-6)
        self.assertLess(float(np.abs(out[wl > 700]).max()), 1e-6)

    def test_anchors_in_either_order(self):
        wl = np.linspace(200.0, 800.0, 301)
        spectrum = 0.10 + 0.0005 * wl
        # Identical results regardless of which anchor is "lo".
        a = ub.compute_linear(wl, spectrum,
                              {"anchor_lo_nm": 200.0, "anchor_hi_nm": 800.0})
        b = ub.compute_linear(wl, spectrum,
                              {"anchor_lo_nm": 800.0, "anchor_hi_nm": 200.0})
        np.testing.assert_allclose(a, b, atol=1e-12)

    def test_subtracts_pure_linear_background_to_zero(self):
        wl = np.linspace(200.0, 800.0, 121)
        spectrum = 0.10 + 0.0005 * wl
        out = ub.compute_linear(
            wl, spectrum,
            {"anchor_lo_nm": 200.0, "anchor_hi_nm": 800.0},
        )
        np.testing.assert_allclose(out, np.zeros_like(out), atol=1e-12)

    def test_missing_param_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(KeyError):
            ub.compute_linear(wl, a, {"anchor_lo_nm": 200.0})


class TestPolynomialMode(unittest.TestCase):

    def test_recovers_peak_on_linear_background_order_1(self):
        wl = np.linspace(200.0, 800.0, 601)
        peak = _gaussian(wl, 500.0, 25.5, height=1.0)
        bg = 0.10 + 0.0005 * wl
        spectrum = peak + bg
        # Fit window covers both peak-free wings (the peak is near
        # zero outside ~[420, 580]).
        out = ub.compute_polynomial(
            wl, spectrum,
            {"order": 1, "fit_lo_nm": 200.0, "fit_hi_nm": 380.0},
        )
        # Background is exactly degree-1 → residual on wings is ~0.
        self.assertAlmostEqual(float(out.max()), 1.0, places=6)
        self.assertLess(float(np.abs(out[wl < 300]).max()), 1e-6)

    def test_recovers_peak_on_quadratic_background_order_2(self):
        wl = np.linspace(200.0, 800.0, 601)
        peak = _gaussian(wl, 500.0, 25.5, height=1.0)
        bg = 0.05 + 1e-4 * (wl - 200.0) + 1e-7 * (wl - 200.0) ** 2
        spectrum = peak + bg
        # Fit window: union via two halves cannot be expressed in a
        # single nm window, so use a generous left-side window
        # comfortably outside the peak. Order 2 polynomial recovers
        # the quadratic background exactly within the fit window;
        # extrapolation across the peak is only as good as a quadratic
        # extrapolation can be — but for this background it's exact.
        out = ub.compute_polynomial(
            wl, spectrum,
            {"order": 2, "fit_lo_nm": 200.0, "fit_hi_nm": 380.0},
        )
        self.assertAlmostEqual(float(out.max()), 1.0, places=4)

    def test_too_few_points_for_order_raises(self):
        wl = np.linspace(200.0, 800.0, 601)
        a = np.zeros_like(wl)
        # Window with only one point — can't fit even a constant via polyfit.
        with self.assertRaises(ValueError):
            ub.compute_polynomial(
                wl, a,
                # Use a tiny epsilon-width window to grab one sample.
                {"order": 5, "fit_lo_nm": 199.9, "fit_hi_nm": 200.1},
            )

    def test_negative_order_rejected(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            ub.compute_polynomial(
                wl, a,
                {"order": -1, "fit_lo_nm": 200.0, "fit_hi_nm": 800.0},
            )


class TestSplineMode(unittest.TestCase):

    def test_recovers_peak_with_anchors_outside_peak(self):
        wl = np.linspace(200.0, 800.0, 601)
        peak = _gaussian(wl, 500.0, 25.5, height=1.0)
        # Smoothly varying non-linear background (sin component).
        bg = 0.10 + 0.0005 * wl + 0.05 * np.sin(wl / 100.0)
        spectrum = peak + bg
        # Anchors live in the peak-free wings; the cubic spline between
        # them tracks the smooth background through the peak region.
        anchors = [200.0, 250.0, 300.0, 350.0, 380.0,
                   620.0, 660.0, 700.0, 750.0, 800.0]
        out = ub.compute_spline(wl, spectrum, {"anchors": anchors})
        # Peak recovery is approximate (the spline through anchors is
        # not the true sinusoid), but the height is well within 5%.
        self.assertAlmostEqual(float(out.max()), 1.0, delta=0.05)

    def test_two_anchors_act_as_linear(self):
        wl = np.linspace(200.0, 800.0, 121)
        spectrum = 0.10 + 0.0005 * wl
        out = ub.compute_spline(
            wl, spectrum, {"anchors": [200.0, 800.0]},
        )
        np.testing.assert_allclose(out, np.zeros_like(out), atol=1e-12)

    def test_too_few_anchors_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            ub.compute_spline(wl, a, {"anchors": [400.0]})

    def test_three_anchors_use_quadratic(self):
        wl = np.linspace(200.0, 800.0, 121)
        # Pure quadratic spectrum; three anchors at the same wavelengths
        # the polynomial passes through → recovered residual is zero.
        spectrum = 1e-6 * (wl - 500.0) ** 2 + 0.2
        out = ub.compute_spline(
            wl, spectrum, {"anchors": [200.0, 500.0, 800.0]},
        )
        np.testing.assert_allclose(out, np.zeros_like(out), atol=1e-9)


class TestRubberbandMode(unittest.TestCase):

    def test_recovers_peak_on_linear_background(self):
        wl = np.linspace(200.0, 800.0, 601)
        peak = _gaussian(wl, 500.0, 25.5, height=1.0)
        bg = 0.10 + 0.0005 * wl
        spectrum = peak + bg
        out = ub.compute_rubberband(wl, spectrum, {})
        # The Gaussian has decayed to numerical zero at the wings, so
        # the lower hull tracks the linear background almost exactly.
        self.assertAlmostEqual(float(out.max()), 1.0, places=4)

    def test_no_params_arg_works(self):
        wl = np.linspace(200.0, 800.0, 121)
        spectrum = 0.10 + 0.0005 * wl + _gaussian(wl, 500, 25.5)
        # ``params`` is allowed to be None for the parameter-free mode.
        out = ub.compute_rubberband(wl, spectrum, None)
        self.assertAlmostEqual(float(out.max()), 1.0, places=4)

    def test_baseline_never_above_data(self):
        # The rubberband baseline is a *lower* envelope, so the
        # corrected absorbance must be non-negative everywhere.
        rng = np.random.default_rng(seed=42)
        wl = np.linspace(200.0, 800.0, 401)
        bg = 0.05 + 0.001 * wl
        spectrum = bg + 0.3 * _gaussian(wl, 350, 30)
        spectrum += 0.7 * _gaussian(wl, 600, 40)
        spectrum += 0.005 * rng.standard_normal(wl.size)
        out = ub.compute_rubberband(wl, spectrum, None)
        # Allow a tiny numerical slack from the linear interp.
        self.assertGreaterEqual(float(out.min()), -1e-9)


class TestDispatcher(unittest.TestCase):

    def test_dispatch_routes_each_mode(self):
        wl = np.linspace(200.0, 800.0, 51)
        spectrum = 0.10 + 0.0005 * wl
        zero = np.zeros_like(wl)

        np.testing.assert_allclose(
            ub.compute("linear", wl, spectrum,
                       {"anchor_lo_nm": 200.0, "anchor_hi_nm": 800.0}),
            zero, atol=1e-12,
        )
        np.testing.assert_allclose(
            ub.compute("polynomial", wl, spectrum,
                       {"order": 1, "fit_lo_nm": 200.0, "fit_hi_nm": 800.0}),
            zero, atol=1e-12,
        )
        np.testing.assert_allclose(
            ub.compute("spline", wl, spectrum,
                       {"anchors": [200.0, 800.0]}),
            zero, atol=1e-12,
        )
        np.testing.assert_allclose(
            ub.compute("rubberband", wl, spectrum, None),
            zero, atol=1e-9,
        )

    def test_dispatch_unknown_mode_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            ub.compute("nope", wl, a, {})


class TestInputValidation(unittest.TestCase):

    def test_shape_mismatch_raises(self):
        with self.assertRaises(ValueError):
            ub.compute_linear(
                np.linspace(0, 1, 10), np.zeros(9),
                {"anchor_lo_nm": 0.0, "anchor_hi_nm": 1.0},
            )

    def test_2d_input_raises(self):
        with self.assertRaises(ValueError):
            ub.compute_linear(
                np.zeros((3, 4)), np.zeros((3, 4)),
                {"anchor_lo_nm": 0.0, "anchor_hi_nm": 1.0},
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
