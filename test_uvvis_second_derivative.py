"""Tests for uvvis_second_derivative.py.

Pure compute layer tests run headless (no Tk). Panel tests construct a
real ``tk.Tk`` root and a real ``ProjectGraph``, then drive the
``SecondDerivativePanel`` and observe the resulting graph state.
Headless environments where ``tk.Tk()`` cannot be constructed skip the
panel class via ``unittest.skipUnless``.

Mirrors the structure of test_uvvis_smoothing.py.
"""

from __future__ import annotations

import unittest

import numpy as np

import uvvis_second_derivative as usd

# Try to construct a Tk root once at module import time. If it fails
# (no display, missing tcl/tk), the panel-class tests are skipped but
# the pure compute tests still run.
try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _HAS_DISPLAY = True
except Exception:  # pragma: no cover — only hit on headless CI
    _root = None
    _HAS_DISPLAY = False


from graph import ProjectGraph
from nodes import DataNode, NodeState, NodeType, OperationNode, OperationType


# ---- Helpers -----------------------------------------------------------


def _gaussian(wl, center, sigma, height=1.0):
    return height * np.exp(-((wl - center) / sigma) ** 2)


def _gaussian_d2_analytic(wl, center, sigma, height=1.0):
    """Analytic d²/dλ² of a Gaussian — used as a reference oracle.

    f(λ) = h * exp(-((λ-c)/σ)²)
    f''(λ) = h * (4(λ-c)²/σ⁴ - 2/σ²) * exp(-((λ-c)/σ)²)
    """
    z = (wl - center) / sigma
    return height * (4.0 * z ** 2 / sigma ** 2 - 2.0 / sigma ** 2) * np.exp(-z ** 2)


def _noisy(wl, seed=0, level=0.05):
    rng = np.random.RandomState(seed)
    return _gaussian(wl, 500.0, 25.5, height=1.0) + level * rng.randn(wl.size)


# ---- Pure compute tests ------------------------------------------------


class TestComputeBasic(unittest.TestCase):

    def test_output_shape_matches_input(self):
        wl = np.linspace(200.0, 800.0, 601)
        a = _gaussian(wl, 500.0, 25.5, height=1.0)
        out = usd.compute(wl, a, {"window_length": 11, "polyorder": 3})
        self.assertEqual(out.shape, a.shape)

    def test_output_dtype_is_float(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _gaussian(wl, 500.0, 25.5)
        out = usd.compute(wl, a, {"window_length": 9, "polyorder": 3})
        self.assertEqual(out.dtype, np.float64)

    def test_constant_signal_yields_near_zero_derivative(self):
        wl = np.linspace(200.0, 800.0, 101)
        const = np.full_like(wl, 0.42)
        out = usd.compute(wl, const, {"window_length": 9, "polyorder": 3})
        np.testing.assert_allclose(out, np.zeros_like(out), atol=1e-12)

    def test_linear_signal_yields_near_zero_derivative(self):
        # The second derivative of a line is zero everywhere — this is
        # what savgol with polyorder ≥ 2 reproduces exactly at every
        # interior point.
        wl = np.linspace(200.0, 800.0, 101)
        line = 0.10 + 0.001 * wl
        out = usd.compute(wl, line, {"window_length": 9, "polyorder": 3})
        np.testing.assert_allclose(out, np.zeros_like(out), atol=1e-9)

    def test_quadratic_recovers_exact_curvature(self):
        # f(λ) = a*λ² → f''(λ) = 2a, exactly — at every interior point.
        # Tests the delta scaling: if the savgol routine returned
        # A/sample² instead of A/nm², this would fail.
        wl = np.linspace(200.0, 800.0, 101)
        a_coeff = 1e-4
        quad = a_coeff * wl ** 2
        out = usd.compute(wl, quad, {"window_length": 9, "polyorder": 3})
        # Expected curvature is 2*a everywhere; trim the edges where
        # savgol's polynomial fit interacts with the boundary.
        np.testing.assert_allclose(
            out[20:-20],
            np.full(out.size - 40, 2.0 * a_coeff),
            atol=1e-9,
        )


class TestComputeOnGaussianMatchesAnalytic(unittest.TestCase):

    def test_gaussian_d2_matches_analytic_at_peak(self):
        # The analytic d² of a Gaussian at the peak is -2h/σ². If the
        # delta scaling is correct, the savgol output near the peak
        # must be close to this value.
        wl = np.linspace(200.0, 800.0, 1201)
        sigma = 25.5
        a = _gaussian(wl, 500.0, sigma, height=1.0)
        out = usd.compute(wl, a, {"window_length": 21, "polyorder": 3})
        peak_idx = int(np.argmin(np.abs(wl - 500.0)))
        expected = -2.0 / sigma ** 2  # height = 1
        # Tolerance is ~2% relative because savgol with a 21-point
        # window blurs the peak slightly. The whole point of this
        # assertion is to lock in the delta scaling: an unscaled
        # output (A/sample² rather than A/nm²) would differ by a
        # factor of (Δλ)² ≈ 0.25, way outside this tolerance.
        self.assertAlmostEqual(float(out[peak_idx]), expected, delta=1e-4)

    def test_gaussian_d2_zero_crossings_at_inflection_points(self):
        # The second derivative of a Gaussian crosses zero at λ = c ± σ.
        # The savgol output must have the same sign pattern.
        wl = np.linspace(200.0, 800.0, 1201)
        sigma = 25.5
        a = _gaussian(wl, 500.0, sigma, height=1.0)
        out = usd.compute(wl, a, {"window_length": 21, "polyorder": 3})
        # At the inflection points the curvature is zero; just inside,
        # negative; just outside, positive.
        idx_inside_lo = int(np.argmin(np.abs(wl - (500.0 - sigma * 0.5))))
        idx_inside_hi = int(np.argmin(np.abs(wl - (500.0 + sigma * 0.5))))
        idx_outside_lo = int(np.argmin(np.abs(wl - (500.0 - sigma * 1.5))))
        idx_outside_hi = int(np.argmin(np.abs(wl - (500.0 + sigma * 1.5))))
        self.assertLess(out[idx_inside_lo], 0.0)
        self.assertLess(out[idx_inside_hi], 0.0)
        self.assertGreater(out[idx_outside_lo], 0.0)
        self.assertGreater(out[idx_outside_hi], 0.0)


class TestComputeValidation(unittest.TestCase):

    def test_window_length_must_be_odd(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl, seed=1)
        with self.assertRaises(ValueError):
            usd.compute(wl, a, {"window_length": 10, "polyorder": 3})

    def test_window_length_must_be_positive(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl)
        with self.assertRaises(ValueError):
            usd.compute(wl, a, {"window_length": 0, "polyorder": 3})

    def test_polyorder_must_be_at_least_two(self):
        # Second derivative is undefined for polyorder < 2 — this is
        # the key difference from smoothing's polyorder >= 0 rule.
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl)
        with self.assertRaises(ValueError):
            usd.compute(wl, a, {"window_length": 9, "polyorder": 1})
        with self.assertRaises(ValueError):
            usd.compute(wl, a, {"window_length": 9, "polyorder": 0})

    def test_polyorder_must_be_lt_window_length(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl)
        with self.assertRaises(ValueError):
            usd.compute(wl, a, {"window_length": 5, "polyorder": 5})

    def test_window_length_must_not_exceed_signal(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            usd.compute(wl, a, {"window_length": 21, "polyorder": 3})

    def test_missing_window_length_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(KeyError):
            usd.compute(wl, a, {"polyorder": 3})

    def test_missing_polyorder_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(KeyError):
            usd.compute(wl, a, {"window_length": 5})

    def test_shape_mismatch_raises(self):
        with self.assertRaises(ValueError):
            usd.compute(
                np.linspace(0, 1, 10), np.zeros(9),
                {"window_length": 5, "polyorder": 2},
            )

    def test_2d_input_raises(self):
        with self.assertRaises(ValueError):
            usd.compute(
                np.zeros((3, 4)), np.zeros((3, 4)),
                {"window_length": 5, "polyorder": 2},
            )

    def test_too_few_samples_raises(self):
        # A single sample has no spacing → cannot compute delta.
        with self.assertRaises(ValueError):
            usd.compute(
                np.array([500.0]), np.array([1.0]),
                {"window_length": 5, "polyorder": 2},
            )


# ---- Panel tests -------------------------------------------------------


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestSecondDerivativePanel(unittest.TestCase):
    """Drive the SecondDerivativePanel against a real ProjectGraph."""

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        self.panel = usd.SecondDerivativePanel(
            self.host, self.graph,
            spectrum_nodes_fn=self._spectrum_nodes,
        )
        self.panel.pack()

    def tearDown(self):
        try:
            self.panel.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- helpers -----------------------------------------------------

    def _spectrum_nodes(self):
        # Mirrors the host's _spectrum_nodes — UVVIS / BASELINE /
        # NORMALISED / SMOOTHED, *not* SECOND_DERIVATIVE itself.
        out = []
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED, NodeType.SMOOTHED):
            for n in self.graph.nodes_of_type(ntype, state=None):
                if n.state == NodeState.DISCARDED:
                    continue
                if not n.active:
                    continue
                out.append(n)
        return out

    def _add_uvvis(self, nid: str = "u1") -> None:
        wl = np.linspace(200.0, 800.0, 601)
        absorb = _gaussian(wl, 500.0, 25.5, height=1.0) + 0.05
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    # ---- subject combobox -------------------------------------------

    def test_subject_combobox_tracks_added_uvvis_node(self):
        items_before = self.panel._subject_cb.cget("values")
        if isinstance(items_before, str):
            items_before = tuple(items_before.split())
        self.assertEqual(len(items_before), 0)
        self._add_uvvis("u1")
        self.panel.update_idletasks()
        items_after = self.panel._subject_cb.cget("values")
        if isinstance(items_after, str):
            items_after = tuple(items_after.split())
        self.assertEqual(len(items_after), 1)

    # ---- Apply happy paths ------------------------------------------

    def _select_first_subject(self):
        items = self.panel._subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertGreaterEqual(len(items), 1)
        self.panel._subject_var.set(items[0])

    def test_apply_creates_provisional_op_and_second_derivative_node(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._window_length.set(11)
        self.panel._polyorder.set(3)

        n_before = len(self.graph.nodes)
        op_id, out_id = self.panel._apply()
        n_after = len(self.graph.nodes)
        self.assertEqual(n_after - n_before, 2,
                         "Apply must add exactly one op + one data node")

        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertIsInstance(op, OperationNode)
        self.assertEqual(op.type, OperationType.SECOND_DERIVATIVE)
        self.assertEqual(op.engine, "internal")
        self.assertEqual(op.state, NodeState.PROVISIONAL)
        # Params completeness: window_length + polyorder, no mode key
        # (single algorithm).
        self.assertEqual(op.params["window_length"], 11)
        self.assertEqual(op.params["polyorder"], 3)
        self.assertNotIn("mode", op.params)

        self.assertIsInstance(out, DataNode)
        self.assertEqual(out.type, NodeType.SECOND_DERIVATIVE)
        self.assertEqual(out.state, NodeState.PROVISIONAL)
        self.assertIn("wavelength_nm", out.arrays)
        self.assertIn("absorbance", out.arrays)
        # Edges parent → op → out.
        self.assertEqual(self.graph.parents_of(op_id), ["u1"])
        self.assertEqual(self.graph.children_of(op_id), [out_id])
        # Metadata footer carries the parent id (no mode key).
        self.assertEqual(out.metadata["second_derivative_parent_id"], "u1")
        self.assertNotIn("second_derivative_mode", out.metadata)

    def test_default_label_includes_d2_suffix(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        _, out_id = self.panel._apply()
        out = self.graph.get_node(out_id)
        self.assertIn("d²A/dλ²", out.label)

    def test_default_style_picks_palette_colour(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        _, out_id = self.panel._apply()
        out = self.graph.get_node(out_id)
        # default_spectrum_style schema: eight universal keys present.
        for key in ("color", "linestyle", "linewidth", "alpha",
                    "visible", "in_legend", "fill", "fill_alpha"):
            self.assertIn(key, out.style)
        # Colour is one of the palette entries (not the parent's).
        self.assertIn(out.style["color"], usd._PALETTE)
        self.assertNotEqual(out.style["color"], "#111")

    # ---- Apply rejection paths --------------------------------------

    def test_apply_invalid_polyorder_is_rejected_without_creating_nodes(self):
        # polyorder < 2 is the second-derivative-specific rule.
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._window_length.set(9)
        self.panel._polyorder.set(1)

        n_before = len(self.graph.nodes)
        from tkinter import messagebox as mb
        original = mb.showerror
        mb.showerror = lambda *a, **k: None
        try:
            result = self.panel._apply()
        finally:
            mb.showerror = original
        n_after = len(self.graph.nodes)
        self.assertIsNone(result)
        self.assertEqual(n_after, n_before)

    def test_apply_window_smaller_than_polyorder_is_rejected(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._window_length.set(5)
        self.panel._polyorder.set(5)

        n_before = len(self.graph.nodes)
        from tkinter import messagebox as mb
        original = mb.showerror
        mb.showerror = lambda *a, **k: None
        try:
            result = self.panel._apply()
        finally:
            mb.showerror = original
        n_after = len(self.graph.nodes)
        self.assertIsNone(result)
        self.assertEqual(n_after, n_before)

    def test_apply_no_subject_is_rejected(self):
        n_before = len(self.graph.nodes)
        from tkinter import messagebox as mb
        original = mb.showinfo
        mb.showinfo = lambda *a, **k: None
        try:
            result = self.panel._apply()
        finally:
            mb.showinfo = original
        n_after = len(self.graph.nodes)
        self.assertIsNone(result)
        self.assertEqual(n_after, n_before)

    # ---- Provisional → commit / discard -----------------------------

    def test_commit_promotes_second_derivative_state(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        _, out_id = self.panel._apply()
        self.graph.commit_node(out_id)
        self.assertEqual(self.graph.get_node(out_id).state,
                         NodeState.COMMITTED)

    def test_discard_marks_second_derivative_discarded(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        _, out_id = self.panel._apply()
        self.graph.discard_node(out_id)
        self.assertEqual(self.graph.get_node(out_id).state,
                         NodeState.DISCARDED)

    def test_subject_combobox_excludes_second_derivative_after_apply(self):
        # Chained second derivatives are intentionally excluded — the
        # subject helper does not return SECOND_DERIVATIVE nodes, so
        # applying a second derivative does NOT add a new candidate
        # subject. Mirrors the locked SmoothingPanel parent type set.
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._apply()
        self.panel.update_idletasks()
        items = self.panel._subject_cb.cget("values")
        if isinstance(items, str):
            items = tuple(items.split())
        self.assertEqual(len(items), 1,
                         "subject list should NOT include the new "
                         "SECOND_DERIVATIVE node (chained derivatives "
                         "out of scope)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
