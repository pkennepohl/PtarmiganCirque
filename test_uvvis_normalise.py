"""Tests for uvvis_normalise.py.

Pure compute layer tests run headless (no Tk). Panel tests construct
a real ``tk.Tk`` root and a real ``ProjectGraph``, then drive the
``NormalisationPanel`` and observe the resulting graph state. Headless
environments where ``tk.Tk()`` cannot be constructed skip the panel
class via ``unittest.skipUnless``.

Mirrors the structure of test_uvvis_baseline.py + the
``TestUVVisTabBaseline`` block in test_uvvis_tab.py.
"""

from __future__ import annotations

import unittest

import numpy as np

import uvvis_normalise as un

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


# ---- Pure compute tests ------------------------------------------------


def _gaussian(wl, center, sigma, height=1.0):
    return height * np.exp(-((wl - center) / sigma) ** 2)


class TestPeakMode(unittest.TestCase):

    def test_divides_by_peak_in_window(self):
        wl = np.linspace(200.0, 800.0, 601)
        spectrum = _gaussian(wl, 500.0, 25.5, height=2.5) + 0.1
        out = un.compute_peak(
            wl, spectrum,
            {"peak_lo_nm": 400.0, "peak_hi_nm": 600.0},
        )
        # The Gaussian peak height is 2.5 + 0.1 = 2.6 at 500 nm; max
        # |spectrum| inside [400, 600] is ~2.6, so the normalised peak
        # rounds to ~1.0.
        self.assertAlmostEqual(float(out.max()), 1.0, places=4)

    def test_window_outside_peak_uses_local_max(self):
        # If the user's window doesn't include the peak, the divisor is
        # the local max within the window — meaning the "peak" of the
        # output (which is outside the window) ends up > 1.
        wl = np.linspace(200.0, 800.0, 601)
        spectrum = _gaussian(wl, 500.0, 25.5, height=1.0)
        out = un.compute_peak(
            wl, spectrum,
            {"peak_lo_nm": 200.0, "peak_hi_nm": 350.0},
        )
        # Sanity: the wing-only divisor is much smaller than the actual
        # peak, so the global peak in the output is large.
        self.assertGreater(float(out.max()), 5.0)

    def test_missing_param_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(KeyError):
            un.compute_peak(wl, a, {"peak_lo_nm": 200.0})

    def test_zero_peak_raises(self):
        wl = np.linspace(200.0, 800.0, 601)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            un.compute_peak(
                wl, a,
                {"peak_lo_nm": 200.0, "peak_hi_nm": 800.0},
            )

    def test_window_with_no_samples_raises(self):
        wl = np.linspace(200.0, 800.0, 601)
        spectrum = _gaussian(wl, 500.0, 25.5)
        with self.assertRaises(ValueError):
            un.compute_peak(
                wl, spectrum,
                {"peak_lo_nm": 1000.0, "peak_hi_nm": 1100.0},
            )


class TestAreaMode(unittest.TestCase):

    def test_divides_by_window_integral(self):
        wl = np.linspace(200.0, 800.0, 601)
        spectrum = _gaussian(wl, 500.0, 25.5, height=1.0)
        out = un.compute_area(
            wl, spectrum,
            {"area_lo_nm": 200.0, "area_hi_nm": 800.0},
        )
        # Integrated normalised |spectrum| over the same window ≈ 1.
        mask = (wl >= 200.0) & (wl <= 800.0)
        recovered = float(np.trapezoid(np.abs(out[mask]), wl[mask]))
        self.assertAlmostEqual(recovered, 1.0, places=6)

    def test_window_endpoints_in_either_order(self):
        # The compute layer reorders lo/hi internally so the params
        # dict is allowed to carry them in either order.
        wl = np.linspace(200.0, 800.0, 121)
        spectrum = _gaussian(wl, 500.0, 25.5)
        a = un.compute_area(wl, spectrum,
                            {"area_lo_nm": 200.0, "area_hi_nm": 800.0})
        b = un.compute_area(wl, spectrum,
                            {"area_lo_nm": 800.0, "area_hi_nm": 200.0})
        np.testing.assert_allclose(a, b, atol=1e-12)

    def test_descending_wavelength_does_not_flip_sign(self):
        # B-003 root cause regression — descending nm arrays must yield
        # a positive divisor (the integral's absolute value is taken).
        wl_desc = np.linspace(800.0, 200.0, 601)
        spectrum = _gaussian(wl_desc, 500.0, 25.5, height=1.0) + 0.05
        out = un.compute_area(
            wl_desc, spectrum,
            {"area_lo_nm": 200.0, "area_hi_nm": 800.0},
        )
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertGreater(float(np.max(out)), 0.0,
                           "descending wl must not flip sign of normalised peak")

    def test_missing_param_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(KeyError):
            un.compute_area(wl, a, {"area_lo_nm": 200.0})

    def test_zero_area_raises(self):
        wl = np.linspace(200.0, 800.0, 601)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            un.compute_area(
                wl, a,
                {"area_lo_nm": 200.0, "area_hi_nm": 800.0},
            )


class TestDispatcher(unittest.TestCase):

    def test_dispatch_routes_each_mode(self):
        wl = np.linspace(200.0, 800.0, 51)
        spectrum = _gaussian(wl, 500.0, 25.5, height=1.0) + 0.1

        peak_out = un.compute("peak", wl, spectrum,
                              {"peak_lo_nm": 200.0, "peak_hi_nm": 800.0})
        self.assertAlmostEqual(float(peak_out.max()), 1.0, places=4)

        area_out = un.compute("area", wl, spectrum,
                              {"area_lo_nm": 200.0, "area_hi_nm": 800.0})
        recovered = float(np.trapezoid(np.abs(area_out), wl))
        self.assertAlmostEqual(recovered, 1.0, places=6)

    def test_dispatch_unknown_mode_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            un.compute("nope", wl, a, {})

    def test_dispatch_rejects_none(self):
        # The "none" mode of the legacy _norm_mode combobox is gone;
        # the dispatcher must not silently accept it.
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            un.compute("none", wl, a, {})


class TestInputValidation(unittest.TestCase):

    def test_shape_mismatch_raises(self):
        with self.assertRaises(ValueError):
            un.compute_peak(
                np.linspace(0, 1, 10), np.zeros(9),
                {"peak_lo_nm": 0.0, "peak_hi_nm": 1.0},
            )

    def test_2d_input_raises(self):
        with self.assertRaises(ValueError):
            un.compute_peak(
                np.zeros((3, 4)), np.zeros((3, 4)),
                {"peak_lo_nm": 0.0, "peak_hi_nm": 1.0},
            )


# ---- Panel tests -------------------------------------------------------


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestNormalisationPanel(unittest.TestCase):
    """Drive the NormalisationPanel against a real ProjectGraph."""

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        # Phase 4k: the panel no longer owns a subject combobox or a
        # graph subscription; the host pushes the shared subject in
        # via ``set_subject``.
        self.panel = un.NormalisationPanel(self.host, self.graph)
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

    def test_set_subject_unaccepted_type_disables_apply(self):
        # SMOOTHED is not in NormalisationPanel.ACCEPTED_PARENT_TYPES
        # (peak/area normalise should run before smoothing).
        wl = np.linspace(200.0, 800.0, 601)
        absorb = _gaussian(wl, 500.0, 25.5, height=1.0) + 0.05
        self.graph.add_node(DataNode(
            id="s1", type=NodeType.SMOOTHED,
            arrays={"wavelength_nm": wl, "absorbance": absorb},
            metadata={}, label="s1", state=NodeState.PROVISIONAL,
            style={"color": "#111", "linestyle": "solid",
                   "linewidth": 1.5, "alpha": 0.9, "visible": True,
                   "in_legend": True, "fill": False, "fill_alpha": 0.08},
        ))
        self.panel.set_subject("s1")
        self.assertEqual(self._apply_btn_state(), "disabled")

    def test_accepted_parent_types_constant(self):
        self.assertEqual(
            un.NormalisationPanel.ACCEPTED_PARENT_TYPES,
            (NodeType.UVVIS, NodeType.BASELINE, NodeType.NORMALISED),
        )

    def test_no_inline_title_label_inside_panel_body(self):
        # Phase 4n (CS-25): the panel body must not render its own
        # "Normalisation" label — the CollapsibleSection wrapper (CS-21)
        # owns the section header. A second inline title would
        # duplicate it on screen, which was the user-flagged bug
        # (Phase 4l friction #6) this phase fixes. Recursive walk so a
        # future refactor that nests the label inside a sub-frame is
        # also caught.
        def _walk_labels(widget):
            out = []
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    out.append(child)
                out.extend(_walk_labels(child))
            return out
        offending = [
            lbl for lbl in _walk_labels(self.panel)
            if lbl.cget("text") == "Normalisation"
        ]
        self.assertEqual(
            offending, [],
            "panel body must not carry an inline 'Normalisation' label "
            "— the CollapsibleSection header owns the title (CS-21).",
        )

    def test_param_rows_rebuild_on_mode_change(self):
        self._add_uvvis()
        self.panel._mode_var.set("peak")
        self.panel.update_idletasks()
        peak_count = len(self.panel._params_frame.winfo_children())
        self.panel._mode_var.set("area")
        self.panel.update_idletasks()
        area_count = len(self.panel._params_frame.winfo_children())
        # Both modes have two rows (lo + hi); the row labels differ.
        self.assertEqual(peak_count, 2)
        self.assertEqual(area_count, 2)

    # ---- Apply happy paths ------------------------------------------

    def _select_first_subject(self):
        # Phase 4k: subject is pushed in by the host. Pick the first
        # non-discarded node from the graph and adopt it.
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED):
            for n in self.graph.nodes_of_type(ntype, state=None):
                if n.state != NodeState.DISCARDED and n.active:
                    self.panel.set_subject(n.id)
                    return
        self.fail("no candidate subject node in graph")

    def test_apply_peak_creates_provisional_op_and_normalised_node(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("peak")
        self.panel._window_lo.set("400")
        self.panel._window_hi.set("600")

        n_before = len(self.graph.nodes)
        op_id, out_id = self.panel._apply()
        n_after = len(self.graph.nodes)
        self.assertEqual(n_after - n_before, 2,
                         "Apply must add exactly one op + one data node")

        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertIsInstance(op, OperationNode)
        self.assertEqual(op.type, OperationType.NORMALISE)
        self.assertEqual(op.engine, "internal")
        self.assertEqual(op.state, NodeState.PROVISIONAL)
        # Params completeness — mode + sub-schema for peak.
        self.assertEqual(op.params["mode"], "peak")
        self.assertAlmostEqual(op.params["peak_lo_nm"], 400.0)
        self.assertAlmostEqual(op.params["peak_hi_nm"], 600.0)

        self.assertIsInstance(out, DataNode)
        self.assertEqual(out.type, NodeType.NORMALISED)
        self.assertEqual(out.state, NodeState.PROVISIONAL)
        self.assertIn("wavelength_nm", out.arrays)
        self.assertIn("absorbance", out.arrays)
        # Recovered peak ≈ 1.0 inside the window.
        self.assertAlmostEqual(float(out.arrays["absorbance"].max()),
                               1.0, places=4)
        # Edges parent → op → out.
        self.assertEqual(self.graph.parents_of(op_id), ["u1"])
        self.assertEqual(self.graph.children_of(op_id), [out_id])
        # Metadata footer carries the mode + parent id.
        self.assertEqual(out.metadata["normalisation_mode"], "peak")
        self.assertEqual(out.metadata["normalisation_parent_id"], "u1")

    def test_apply_area_creates_normalised_node_with_unit_integral(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("area")
        self.panel._window_lo.set("200")
        self.panel._window_hi.set("800")

        _, out_id = self.panel._apply()
        out = self.graph.get_node(out_id)
        self.assertEqual(out.type, NodeType.NORMALISED)
        self.assertEqual(
            self.graph.get_node(self.graph.parents_of(out_id)[0]).params["mode"],
            "area",
        )
        wl = out.arrays["wavelength_nm"]
        absorb = out.arrays["absorbance"]
        recovered = float(np.trapezoid(np.abs(absorb), wl))
        self.assertAlmostEqual(recovered, 1.0, places=6)

    # ---- Apply rejection paths --------------------------------------

    def test_apply_blank_window_is_rejected_without_creating_nodes(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("peak")
        # Both window entries left blank.
        self.panel._window_lo.set("")
        self.panel._window_hi.set("")

        n_before = len(self.graph.nodes)
        # The error path uses messagebox which would be modal — patch
        # it out so the test runs headlessly.
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
        # Empty subject combobox + Apply → no nodes added.
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

    def test_commit_promotes_normalised_state(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("peak")
        self.panel._window_lo.set("200")
        self.panel._window_hi.set("800")
        _, out_id = self.panel._apply()
        self.graph.commit_node(out_id)
        self.assertEqual(self.graph.get_node(out_id).state,
                         NodeState.COMMITTED)

    def test_discard_marks_normalised_discarded(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("peak")
        self.panel._window_lo.set("200")
        self.panel._window_hi.set("800")
        _, out_id = self.panel._apply()
        self.graph.discard_node(out_id)
        self.assertEqual(self.graph.get_node(out_id).state,
                         NodeState.DISCARDED)

    def test_chained_normalisation_accepts_normalised_subject(self):
        # Chained normalisation is allowed: a NORMALISED node is itself
        # a valid parent for further normalisation. The shared
        # subject combobox lives on the tab now (Phase 4k); here we
        # check the panel-side gate accepts a NORMALISED parent.
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("peak")
        self.panel._window_lo.set("200")
        self.panel._window_hi.set("800")
        _, out_id = self.panel._apply()
        self.panel.set_subject(out_id)
        self.assertEqual(self._apply_btn_state(), "normal")


if __name__ == "__main__":
    unittest.main(verbosity=2)
