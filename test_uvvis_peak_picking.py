"""Tests for uvvis_peak_picking.py.

Pure compute layer tests run headless (no Tk). Panel tests construct a
real ``tk.Tk`` root and a real ``ProjectGraph``, then drive the
``PeakPickingPanel`` and observe the resulting graph state. Headless
environments where ``tk.Tk()`` cannot be constructed skip the panel
class via ``unittest.skipUnless``.

Mirrors the structure of test_uvvis_smoothing.py.
"""

from __future__ import annotations

import unittest

import numpy as np

import uvvis_peak_picking as pp

# Try to construct a Tk root once at module import time.
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


# ---- Fixtures ----------------------------------------------------------


def _gaussian(wl, center, sigma, height=1.0):
    return height * np.exp(-((wl - center) / sigma) ** 2)


def _two_peak_spectrum(n_samples=601, lo=200.0, hi=800.0):
    """Synthetic absorbance: two well-separated Gaussian peaks + DC."""
    wl = np.linspace(lo, hi, n_samples)
    a = (
        _gaussian(wl, 350.0, 30.0, height=1.0)
        + _gaussian(wl, 600.0, 25.0, height=0.5)
        + 0.05
    )
    return wl, a


# ---- Pure compute tests ------------------------------------------------


class TestProminenceMode(unittest.TestCase):

    def test_finds_two_peaks_in_synthetic_two_peak_spectrum(self):
        wl, a = _two_peak_spectrum()
        peak_wl, peak_a, peak_prom = pp.compute_prominence(
            wl, a, {"prominence": 0.1},
        )
        # Two peaks at ~350 and ~600 nm.
        self.assertEqual(peak_wl.size, 2)
        self.assertAlmostEqual(float(peak_wl[0]), 350.0, delta=1.0)
        self.assertAlmostEqual(float(peak_wl[1]), 600.0, delta=1.0)
        # Prominences: tallest peak first sample-wise — 350 nm at ~1.05.
        self.assertEqual(peak_prom.size, 2)
        self.assertGreater(float(peak_prom[0]), 0.5)
        # Output absorbance equals the input at the picked indices.
        for w, val in zip(peak_wl, peak_a):
            idx = int(np.argmin(np.abs(wl - w)))
            self.assertAlmostEqual(float(val), float(a[idx]), places=10)

    def test_high_threshold_returns_no_peaks(self):
        wl, a = _two_peak_spectrum()
        peak_wl, peak_a, peak_prom = pp.compute_prominence(
            wl, a, {"prominence": 100.0},
        )
        # No peaks meet the threshold → empty arrays (not an error).
        self.assertEqual(peak_wl.size, 0)
        self.assertEqual(peak_a.size, 0)
        self.assertEqual(peak_prom.size, 0)

    def test_distance_filters_close_peaks(self):
        # Construct three peaks at 350 / 360 / 600. With a large
        # min-distance the 360 peak gets suppressed.
        wl = np.linspace(200.0, 800.0, 601)
        a = (
            _gaussian(wl, 350.0, 5.0, height=1.0)
            + _gaussian(wl, 360.0, 5.0, height=0.95)
            + _gaussian(wl, 600.0, 25.0, height=0.5)
        )
        relaxed_wl, _, _ = pp.compute_prominence(
            wl, a, {"prominence": 0.05, "distance": 1},
        )
        strict_wl, _, _ = pp.compute_prominence(
            wl, a, {"prominence": 0.05, "distance": 50},
        )
        self.assertEqual(relaxed_wl.size, 3)
        self.assertEqual(strict_wl.size, 2)

    def test_negative_prominence_raises(self):
        wl, a = _two_peak_spectrum()
        with self.assertRaises(ValueError):
            pp.compute_prominence(wl, a, {"prominence": -0.1})

    def test_zero_distance_raises(self):
        wl, a = _two_peak_spectrum()
        with self.assertRaises(ValueError):
            pp.compute_prominence(wl, a, {"prominence": 0.1, "distance": 0})

    def test_missing_prominence_raises(self):
        wl, a = _two_peak_spectrum()
        with self.assertRaises(KeyError):
            pp.compute_prominence(wl, a, {})

    def test_descending_wavelength_input_yields_sorted_output(self):
        # The compute_prominence helper sorts ascending before searching;
        # the output must come back ascending in wavelength regardless
        # of the input order.
        wl, a = _two_peak_spectrum()
        peak_wl, _, _ = pp.compute_prominence(
            wl[::-1], a[::-1], {"prominence": 0.1},
        )
        self.assertEqual(peak_wl.size, 2)
        self.assertTrue(np.all(np.diff(peak_wl) > 0),
                        "peaks must be sorted ascending by wavelength")


class TestManualMode(unittest.TestCase):

    def test_snaps_each_request_to_nearest_sample(self):
        wl, a = _two_peak_spectrum()
        # Request 351.7 — nearest sample is 1 nm step from 351.0/352.0
        # depending on the linspace grid.
        requested = [351.7, 600.4]
        peak_wl, peak_a, peak_prom = pp.compute_manual(
            wl, a, {"wavelengths_nm": requested},
        )
        self.assertEqual(peak_wl.size, 2)
        self.assertEqual(peak_prom.size, 0,
                         "manual mode does not compute prominence")
        # Each output wavelength is the nearest-sample to the request.
        for target, snapped in zip(sorted(requested), peak_wl):
            idx = int(np.argmin(np.abs(wl - target)))
            self.assertAlmostEqual(float(snapped), float(wl[idx]), places=10)

    def test_duplicates_are_deduplicated(self):
        wl, a = _two_peak_spectrum()
        # Two requests round to the same sample → output has one entry.
        peak_wl, _, _ = pp.compute_manual(
            wl, a, {"wavelengths_nm": [350.0, 350.5]},
        )
        self.assertEqual(peak_wl.size, 1)

    def test_output_sorted_ascending(self):
        wl, a = _two_peak_spectrum()
        peak_wl, _, _ = pp.compute_manual(
            wl, a, {"wavelengths_nm": [600.0, 350.0, 500.0]},
        )
        self.assertEqual(peak_wl.size, 3)
        self.assertTrue(np.all(np.diff(peak_wl) > 0))

    def test_empty_request_raises(self):
        wl, a = _two_peak_spectrum()
        with self.assertRaises(ValueError):
            pp.compute_manual(wl, a, {"wavelengths_nm": []})

    def test_non_finite_request_raises(self):
        wl, a = _two_peak_spectrum()
        with self.assertRaises(ValueError):
            pp.compute_manual(wl, a, {"wavelengths_nm": [350.0, float("nan")]})

    def test_missing_param_raises(self):
        wl, a = _two_peak_spectrum()
        with self.assertRaises(KeyError):
            pp.compute_manual(wl, a, {})


class TestDispatcher(unittest.TestCase):

    def test_dispatch_routes_each_mode(self):
        wl, a = _two_peak_spectrum()
        prom_wl, _, _ = pp.compute("prominence", wl, a, {"prominence": 0.1})
        manual_wl, _, _ = pp.compute(
            "manual", wl, a, {"wavelengths_nm": [350.0, 600.0]},
        )
        self.assertEqual(prom_wl.size, 2)
        self.assertEqual(manual_wl.size, 2)

    def test_dispatch_unknown_mode_raises(self):
        wl, a = _two_peak_spectrum()
        with self.assertRaises(ValueError):
            pp.compute("nope", wl, a, {})

    def test_dispatch_rejects_none(self):
        # Mirrors CS-16 / CS-18: "none" is not a peak-picking mode — it is
        # the absence of a peak-picking operation.
        wl, a = _two_peak_spectrum()
        with self.assertRaises(ValueError):
            pp.compute("none", wl, a, {})


class TestInputValidation(unittest.TestCase):

    def test_shape_mismatch_raises(self):
        with self.assertRaises(ValueError):
            pp.compute_prominence(
                np.linspace(0, 1, 10), np.zeros(9),
                {"prominence": 0.1},
            )

    def test_2d_input_raises(self):
        with self.assertRaises(ValueError):
            pp.compute_prominence(
                np.zeros((3, 4)), np.zeros((3, 4)),
                {"prominence": 0.1},
            )

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            pp.compute_prominence(
                np.array([]), np.array([]), {"prominence": 0.1},
            )


# ---- Panel tests -------------------------------------------------------


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPeakPickingPanel(unittest.TestCase):
    """Drive the PeakPickingPanel against a real ProjectGraph."""

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        # Phase 4k: subject is pushed in by the host via set_subject.
        self.panel = pp.PeakPickingPanel(self.host, self.graph)
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

    def _add_uvvis(self, nid: str = "u1") -> None:
        wl, a = _two_peak_spectrum()
        self.graph.add_node(DataNode(
            id=nid, type=NodeType.UVVIS,
            arrays={"wavelength_nm": wl, "absorbance": a},
            metadata={"source_file": "syn"},
            label=nid, state=NodeState.COMMITTED,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))

    # ---- shared-subject hand-off (Phase 4k, CS-22) ------------------

    def _apply_btn_state(self) -> str:
        return str(self.panel._apply_btn.cget("state"))

    def test_apply_disabled_when_no_subject(self):
        self.assertEqual(self._apply_btn_state(), "disabled")

    def test_set_subject_with_uvvis_enables_apply(self):
        self._add_uvvis("u1")
        self.panel.set_subject("u1")
        self.assertEqual(self._apply_btn_state(), "normal")

    def test_set_subject_none_disables_apply(self):
        self._add_uvvis("u1")
        self.panel.set_subject("u1")
        self.assertEqual(self._apply_btn_state(), "normal")
        self.panel.set_subject(None)
        self.assertEqual(self._apply_btn_state(), "disabled")

    def test_set_subject_unknown_id_disables_apply(self):
        self.panel.set_subject("does-not-exist")
        self.assertEqual(self._apply_btn_state(), "disabled")

    def test_set_subject_peak_list_disables_apply(self):
        # PEAK_LIST is not in PeakPickingPanel.ACCEPTED_PARENT_TYPES
        # (chained peak picking is undefined; CS-19).
        wl = np.linspace(200.0, 800.0, 11)
        self.graph.add_node(DataNode(
            id="p1", type=NodeType.PEAK_LIST,
            arrays={"wavelength_nm": wl, "absorbance": np.zeros_like(wl)},
            metadata={}, label="p1", state=NodeState.PROVISIONAL,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        self.panel.set_subject("p1")
        self.assertEqual(self._apply_btn_state(), "disabled")

    def test_accepted_parent_types_constant(self):
        self.assertEqual(
            pp.PeakPickingPanel.ACCEPTED_PARENT_TYPES,
            (NodeType.UVVIS, NodeType.BASELINE,
             NodeType.NORMALISED, NodeType.SMOOTHED),
        )

    def test_param_rows_rebuild_on_mode_change(self):
        self._add_uvvis()
        self.panel._mode_var.set("prominence")
        self.panel.update_idletasks()
        prom_rows = len(self.panel._params_frame.winfo_children())
        self.panel._mode_var.set("manual")
        self.panel.update_idletasks()
        manual_rows = len(self.panel._params_frame.winfo_children())
        # prominence has 2 rows (Prominence + Min distance);
        # manual has 1 label + 1 entry directly in the frame = 2 children.
        self.assertEqual(prom_rows, 2)
        self.assertEqual(manual_rows, 2)

    # ---- Apply happy paths ------------------------------------------

    def _select_first_subject(self):
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED, NodeType.SMOOTHED):
            for n in self.graph.nodes_of_type(ntype, state=None):
                if n.state != NodeState.DISCARDED and n.active:
                    self.panel.set_subject(n.id)
                    return
        self.fail("no candidate subject node in graph")

    def test_apply_prominence_creates_provisional_op_and_peak_list(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("prominence")
        self.panel._prominence.set("0.1")
        self.panel._distance.set(1)

        n_before = len(self.graph.nodes)
        op_id, out_id = self.panel._apply()
        n_after = len(self.graph.nodes)
        self.assertEqual(n_after - n_before, 2,
                         "Apply must add exactly one op + one data node")

        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertIsInstance(op, OperationNode)
        self.assertEqual(op.type, OperationType.PEAK_PICK)
        self.assertEqual(op.engine, "internal")
        self.assertEqual(op.state, NodeState.PROVISIONAL)
        # Params completeness — mode + sub-schema for prominence.
        self.assertEqual(op.params["mode"], "prominence")
        self.assertAlmostEqual(op.params["prominence"], 0.1)
        self.assertEqual(op.params["distance"], 1)

        self.assertIsInstance(out, DataNode)
        self.assertEqual(out.type, NodeType.PEAK_LIST)
        self.assertEqual(out.state, NodeState.PROVISIONAL)
        self.assertIn("peak_wavelengths_nm", out.arrays)
        self.assertIn("peak_absorbances", out.arrays)
        # Prominence array present (because prominence mode emits it).
        self.assertIn("peak_prominences", out.arrays)
        # Edges parent → op → out.
        self.assertEqual(self.graph.parents_of(op_id), ["u1"])
        self.assertEqual(self.graph.children_of(op_id), [out_id])
        # Metadata footer carries mode + parent id + count.
        self.assertEqual(out.metadata["peak_picking_mode"], "prominence")
        self.assertEqual(out.metadata["peak_picking_parent_id"], "u1")
        self.assertEqual(out.metadata["peak_count"],
                         int(out.arrays["peak_wavelengths_nm"].size))

    def test_apply_manual_creates_peak_list_without_prominences_array(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("manual")
        self.panel._manual_wavelengths.set("350, 600")

        op_id, out_id = self.panel._apply()
        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertEqual(op.params["mode"], "manual")
        self.assertEqual(list(op.params["wavelengths_nm"]), [350.0, 600.0])
        self.assertEqual(out.type, NodeType.PEAK_LIST)
        # Manual mode does not emit a prominences array (CS-03 params
        # completeness: only the keys the algorithm computes).
        self.assertNotIn("peak_prominences", out.arrays)
        self.assertEqual(int(out.arrays["peak_wavelengths_nm"].size), 2)

    # ---- Apply rejection paths --------------------------------------

    def test_apply_invalid_prominence_is_rejected_without_creating_nodes(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("prominence")
        self.panel._prominence.set("not-a-number")

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

    def test_apply_empty_manual_wavelengths_is_rejected(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("manual")
        self.panel._manual_wavelengths.set("")

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

    def test_apply_high_prominence_returns_empty_peak_list_without_error(self):
        # Empty result is a valid outcome (the threshold filtered every
        # peak). The op/data nodes still get created so the user can
        # see that the operation ran.
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("prominence")
        self.panel._prominence.set("100.0")

        op_id, out_id = self.panel._apply()
        out = self.graph.get_node(out_id)
        self.assertEqual(int(out.arrays["peak_wavelengths_nm"].size), 0)
        self.assertEqual(out.metadata["peak_count"], 0)

    # ---- Provisional → commit / discard -----------------------------

    def test_commit_promotes_peak_list_state(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("prominence")
        self.panel._prominence.set("0.1")
        _, out_id = self.panel._apply()
        self.graph.commit_node(out_id)
        self.assertEqual(self.graph.get_node(out_id).state,
                         NodeState.COMMITTED)

    def test_discard_marks_peak_list_discarded(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("prominence")
        self.panel._prominence.set("0.1")
        _, out_id = self.panel._apply()
        self.graph.discard_node(out_id)
        self.assertEqual(self.graph.get_node(out_id).state,
                         NodeState.DISCARDED)

    def test_peak_list_subject_is_rejected_by_apply_gate(self):
        # PEAK_LIST is NOT a valid parent for further peak picking
        # (CS-19). The host's shared subject combobox excludes
        # PEAK_LIST from its list (via _spectrum_nodes); even if a
        # caller pushes one in via set_subject, the panel's gate
        # disables Apply.
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("prominence")
        self.panel._prominence.set("0.1")
        _, out_id = self.panel._apply()  # creates a PEAK_LIST
        self.panel.set_subject(out_id)
        self.assertEqual(self._apply_btn_state(), "disabled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
