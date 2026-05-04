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


class TestScatteringMode(unittest.TestCase):

    def test_recovers_peak_with_fixed_rayleigh_n(self):
        # Pure Rayleigh background (n=4) + Gaussian peak.
        wl = np.linspace(200.0, 800.0, 601)
        peak = _gaussian(wl, 500.0, 25.5, height=1.0)
        bg = 1e8 * wl ** (-4)
        spectrum = peak + bg
        # Fit window covers a peak-free wing.
        out = ub.compute_scattering(
            wl, spectrum,
            {"n": 4, "fit_lo_nm": 200.0, "fit_hi_nm": 350.0},
        )
        # Background is exactly c·λ^(-4) → residual on wings is ~0.
        self.assertAlmostEqual(float(out.max()), 1.0, places=6)
        self.assertLess(float(np.abs(out[wl < 300]).max()), 1e-6)

    def test_recovers_peak_with_n_fit(self):
        # Same setup, but let the fit recover both c and n simultaneously.
        wl = np.linspace(200.0, 800.0, 601)
        peak = _gaussian(wl, 500.0, 25.5, height=1.0)
        bg = 1e8 * wl ** (-4)
        spectrum = peak + bg
        out = ub.compute_scattering(
            wl, spectrum,
            {"n": "fit", "fit_lo_nm": 200.0, "fit_hi_nm": 350.0},
        )
        self.assertAlmostEqual(float(out.max()), 1.0, places=4)

    def test_n_fit_is_case_insensitive(self):
        wl = np.linspace(200.0, 800.0, 121)
        spectrum = 1e8 * wl ** (-4) + 0.01
        # "FIT" / "Fit" / "fit" all trigger the log-fit branch.
        for label in ("fit", "FIT", "Fit"):
            out = ub.compute_scattering(
                wl, spectrum,
                {"n": label, "fit_lo_nm": 200.0, "fit_hi_nm": 800.0},
            )
            self.assertEqual(out.shape, wl.shape)

    def test_subtracts_pure_power_law_to_zero(self):
        # Pure baseline, no peak — fixed n recovers c exactly.
        wl = np.linspace(200.0, 800.0, 121)
        spectrum = 1e8 * wl ** (-4)
        out = ub.compute_scattering(
            wl, spectrum,
            {"n": 4, "fit_lo_nm": 200.0, "fit_hi_nm": 800.0},
        )
        np.testing.assert_allclose(out, np.zeros_like(out), atol=1e-9)

    def test_n_fit_requires_positive_absorbance(self):
        # Negative absorbance in the fit window breaks the log-fit.
        wl = np.linspace(200.0, 800.0, 121)
        spectrum = 1e8 * wl ** (-4)
        spectrum[10] = -0.01
        with self.assertRaises(ValueError):
            ub.compute_scattering(
                wl, spectrum,
                {"n": "fit", "fit_lo_nm": 200.0, "fit_hi_nm": 400.0},
            )

    def test_fixed_n_tolerates_negative_absorbance(self):
        # With n fixed, the closed-form fit is linear in c — negative
        # absorbance values are not a problem.
        wl = np.linspace(200.0, 800.0, 121)
        spectrum = 1e8 * wl ** (-4)
        spectrum[10] = -0.01  # noise dip in the fit window
        out = ub.compute_scattering(
            wl, spectrum,
            {"n": 4, "fit_lo_nm": 200.0, "fit_hi_nm": 400.0},
        )
        self.assertEqual(out.shape, wl.shape)

    def test_negative_n_rejected(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.ones_like(wl)
        with self.assertRaises(ValueError):
            ub.compute_scattering(
                wl, a,
                {"n": -1.0, "fit_lo_nm": 200.0, "fit_hi_nm": 800.0},
            )

    def test_non_numeric_non_fit_n_rejected(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.ones_like(wl)
        with self.assertRaises(ValueError):
            ub.compute_scattering(
                wl, a,
                {"n": "rayleigh", "fit_lo_nm": 200.0, "fit_hi_nm": 800.0},
            )

    def test_missing_param_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.ones_like(wl)
        with self.assertRaises(KeyError):
            ub.compute_scattering(wl, a, {"n": 4, "fit_lo_nm": 200.0})

    def test_fit_window_endpoints_either_order(self):
        wl = np.linspace(200.0, 800.0, 121)
        spectrum = 1e8 * wl ** (-4) + _gaussian(wl, 500, 25.5)
        a = ub.compute_scattering(
            wl, spectrum,
            {"n": 4, "fit_lo_nm": 200.0, "fit_hi_nm": 350.0},
        )
        b = ub.compute_scattering(
            wl, spectrum,
            {"n": 4, "fit_lo_nm": 350.0, "fit_hi_nm": 200.0},
        )
        np.testing.assert_allclose(a, b, atol=1e-12)

    def test_too_few_points_in_window_raises(self):
        wl = np.linspace(200.0, 800.0, 121)
        a = wl ** (-4)
        # Epsilon-width window grabs at most one point.
        with self.assertRaises(ValueError):
            ub.compute_scattering(
                wl, a,
                {"n": 4, "fit_lo_nm": 199.9, "fit_hi_nm": 200.1},
            )

    def test_non_positive_wavelength_rejected(self):
        # λ ≤ 0 makes λ^(-n) undefined — guard at the input.
        wl = np.linspace(0.0, 600.0, 121)
        a = np.ones_like(wl)
        with self.assertRaises(ValueError):
            ub.compute_scattering(
                wl, a,
                {"n": 4, "fit_lo_nm": 0.0, "fit_hi_nm": 200.0},
            )


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
        # Scattering: pure power-law spectrum collapses to ~zero.
        scatter_spec = 1e8 * wl ** (-4)
        np.testing.assert_allclose(
            ub.compute("scattering", wl, scatter_spec,
                       {"n": 4, "fit_lo_nm": 200.0, "fit_hi_nm": 800.0}),
            np.zeros_like(wl), atol=1e-9,
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


class TestComputeBaselineCurve(unittest.TestCase):
    """Phase 4o (CS-29) — recover the fitted baseline from a BASELINE node.

    The helper walks one hop in the graph
    (baseline_node → BASELINE OperationNode → parent DataNode) and
    returns ``(wavelength_nm, parent_absorbance - baseline_absorbance)``.
    Every failure path returns ``None`` (the helper is silent so the
    caller's render loop can simply skip the entry).
    """

    def setUp(self):
        from graph import ProjectGraph
        from nodes import (DataNode, NodeState, NodeType,
                           OperationNode, OperationType)
        self.ProjectGraph = ProjectGraph
        self.DataNode = DataNode
        self.NodeState = NodeState
        self.NodeType = NodeType
        self.OperationNode = OperationNode
        self.OperationType = OperationType
        self.graph = ProjectGraph()

    def _wire(self, parent_absorb, child_absorb,
              wl=None, parent_type=None):
        """Build parent UVVIS → BASELINE op → BASELINE child + return ids."""
        if wl is None:
            wl = np.linspace(300.0, 600.0, len(parent_absorb))
        parent = self.DataNode(
            id="p1",
            type=parent_type or self.NodeType.UVVIS,
            arrays={"wavelength_nm": np.asarray(wl, dtype=float),
                    "absorbance":    np.asarray(parent_absorb, dtype=float)},
            metadata={}, label="parent",
            state=self.NodeState.COMMITTED,
        )
        op = self.OperationNode(
            id="op1", type=self.OperationType.BASELINE,
            engine="internal", engine_version="test",
            params={"mode": "linear"},
            input_ids=["p1"], output_ids=["c1"],
            status="SUCCESS", state=self.NodeState.PROVISIONAL,
        )
        child = self.DataNode(
            id="c1", type=self.NodeType.BASELINE,
            arrays={"wavelength_nm": np.asarray(wl, dtype=float),
                    "absorbance":    np.asarray(child_absorb, dtype=float)},
            metadata={}, label="parent · baseline (linear)",
            state=self.NodeState.PROVISIONAL,
        )
        self.graph.add_node(parent)
        self.graph.add_node(op)
        self.graph.add_node(child)
        self.graph.add_edge("p1", "op1")
        self.graph.add_edge("op1", "c1")
        return parent, child

    def test_success_returns_parent_minus_child(self):
        # Parent: a sloped line; child: parent with the slope removed.
        # Recovered baseline must equal the slope itself.
        wl = np.linspace(300.0, 600.0, 5)
        parent_abs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        baseline = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
        child_abs = parent_abs - baseline
        _, child = self._wire(parent_abs, child_abs, wl=wl)

        result = ub.compute_baseline_curve(self.graph, child)
        self.assertIsNotNone(result)
        wl_out, curve = result
        np.testing.assert_array_almost_equal(wl_out, wl)
        np.testing.assert_array_almost_equal(curve, baseline)

    def test_chained_baseline_parent_works(self):
        # Parent itself is a BASELINE node — chained corrections.
        # Helper still returns parent_abs - child_abs without caring
        # about the parent's NodeType.
        wl = np.linspace(300.0, 600.0, 4)
        parent_abs = np.array([2.0, 1.5, 1.0, 0.5])
        child_abs = np.array([1.5, 1.0, 0.6, 0.1])
        _, child = self._wire(parent_abs, child_abs, wl=wl,
                              parent_type=self.NodeType.BASELINE)
        result = ub.compute_baseline_curve(self.graph, child)
        self.assertIsNotNone(result)
        _, curve = result
        np.testing.assert_array_almost_equal(curve, parent_abs - child_abs)

    def test_non_baseline_input_returns_none(self):
        # A UVVIS node passed in by mistake — helper silently rejects.
        node = self.DataNode(
            id="u", type=self.NodeType.UVVIS,
            arrays={"wavelength_nm": np.linspace(300, 600, 3),
                    "absorbance":    np.zeros(3)},
            metadata={}, label="u",
            state=self.NodeState.COMMITTED,
        )
        self.graph.add_node(node)
        self.assertIsNone(ub.compute_baseline_curve(self.graph, node))

    def test_missing_arrays_returns_none(self):
        # BASELINE-typed but missing the canonical absorbance key.
        node = self.DataNode(
            id="b", type=self.NodeType.BASELINE,
            arrays={"wavelength_nm": np.linspace(300, 600, 3)},
            metadata={}, label="b",
            state=self.NodeState.COMMITTED,
        )
        self.graph.add_node(node)
        self.assertIsNone(ub.compute_baseline_curve(self.graph, node))

    def test_no_parent_returns_none(self):
        # A BASELINE node with no graph edges — helper returns None
        # rather than walking past the orphan.
        node = self.DataNode(
            id="b", type=self.NodeType.BASELINE,
            arrays={"wavelength_nm": np.linspace(300, 600, 3),
                    "absorbance":    np.zeros(3)},
            metadata={}, label="b",
            state=self.NodeState.COMMITTED,
        )
        self.graph.add_node(node)
        self.assertIsNone(ub.compute_baseline_curve(self.graph, node))

    def test_shape_mismatch_returns_none(self):
        # Parent and child wavelength_nm shapes diverge — helper
        # returns None rather than broadcasting.
        wl_parent = np.linspace(300.0, 600.0, 5)
        wl_child = np.linspace(300.0, 600.0, 4)
        parent = self.DataNode(
            id="p1", type=self.NodeType.UVVIS,
            arrays={"wavelength_nm": wl_parent,
                    "absorbance":    np.ones(5)},
            metadata={}, label="parent",
            state=self.NodeState.COMMITTED,
        )
        op = self.OperationNode(
            id="op1", type=self.OperationType.BASELINE,
            engine="internal", engine_version="test",
            params={"mode": "linear"},
            input_ids=["p1"], output_ids=["c1"],
            status="SUCCESS", state=self.NodeState.PROVISIONAL,
        )
        child = self.DataNode(
            id="c1", type=self.NodeType.BASELINE,
            arrays={"wavelength_nm": wl_child,
                    "absorbance":    np.zeros(4)},
            metadata={}, label="c",
            state=self.NodeState.PROVISIONAL,
        )
        self.graph.add_node(parent)
        self.graph.add_node(op)
        self.graph.add_node(child)
        self.graph.add_edge("p1", "op1")
        self.graph.add_edge("op1", "c1")
        self.assertIsNone(ub.compute_baseline_curve(self.graph, child))


if __name__ == "__main__":
    unittest.main(verbosity=2)
