"""Tests for uvvis_smoothing.py.

Pure compute layer tests run headless (no Tk). Panel tests construct a
real ``tk.Tk`` root and a real ``ProjectGraph``, then drive the
``SmoothingPanel`` and observe the resulting graph state. Headless
environments where ``tk.Tk()`` cannot be constructed skip the panel
class via ``unittest.skipUnless``.

Mirrors the structure of test_uvvis_normalise.py.
"""

from __future__ import annotations

import unittest

import numpy as np

import uvvis_smoothing as us

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


def _noisy(wl, seed=0, level=0.05):
    rng = np.random.RandomState(seed)
    return _gaussian(wl, 500.0, 25.5, height=1.0) + level * rng.randn(wl.size)


class TestSavgolMode(unittest.TestCase):

    def test_smooths_noise_below_input_level(self):
        # The smoothed array's high-frequency content (point-to-point
        # diff) must be smaller than the noisy input's: that is the
        # whole point of smoothing.
        wl = np.linspace(200.0, 800.0, 601)
        noisy = _noisy(wl, seed=1, level=0.10)
        out = us.compute_savgol(
            wl, noisy,
            {"window_length": 11, "polyorder": 2},
        )
        self.assertEqual(out.shape, noisy.shape)
        in_var = float(np.std(np.diff(noisy)))
        out_var = float(np.std(np.diff(out)))
        self.assertLess(out_var, in_var * 0.5)

    def test_preserves_shape_of_smooth_input(self):
        # Savitzky-Golay on a polynomial of order ≤ polyorder is
        # exact — within float tolerance — at all interior points.
        wl = np.linspace(200.0, 800.0, 101)
        clean = 0.10 + 1e-3 * wl + 1e-6 * wl ** 2  # quadratic
        out = us.compute_savgol(
            wl, clean,
            {"window_length": 9, "polyorder": 2},
        )
        np.testing.assert_allclose(out, clean, atol=1e-9)

    def test_window_length_must_be_odd(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl, seed=2)
        with self.assertRaises(ValueError):
            us.compute_savgol(wl, a, {"window_length": 4, "polyorder": 2})

    def test_polyorder_must_be_lt_window_length(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl, seed=3)
        with self.assertRaises(ValueError):
            us.compute_savgol(wl, a, {"window_length": 5, "polyorder": 5})

    def test_window_length_must_not_exceed_signal(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            us.compute_savgol(wl, a, {"window_length": 21, "polyorder": 2})

    def test_window_length_must_be_positive(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl)
        with self.assertRaises(ValueError):
            us.compute_savgol(wl, a, {"window_length": 0, "polyorder": 0})

    def test_polyorder_must_be_nonnegative(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl)
        with self.assertRaises(ValueError):
            us.compute_savgol(wl, a, {"window_length": 5, "polyorder": -1})

    def test_missing_param_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(KeyError):
            us.compute_savgol(wl, a, {"window_length": 5})


class TestMovingAvgMode(unittest.TestCase):

    def test_window_one_is_identity(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl, seed=4)
        out = us.compute_moving_avg(wl, a, {"window_length": 1})
        np.testing.assert_allclose(out, a)

    def test_smooths_noise_below_input_level(self):
        wl = np.linspace(200.0, 800.0, 601)
        noisy = _noisy(wl, seed=5, level=0.10)
        out = us.compute_moving_avg(wl, noisy, {"window_length": 11})
        self.assertEqual(out.shape, noisy.shape)
        in_var = float(np.std(np.diff(noisy)))
        out_var = float(np.std(np.diff(out)))
        self.assertLess(out_var, in_var * 0.5)

    def test_preserves_constant_signal(self):
        # A constant signal must come out exactly constant — no edge
        # bias from the reflect padding.
        wl = np.linspace(200.0, 800.0, 51)
        const = np.full_like(wl, 0.42)
        out = us.compute_moving_avg(wl, const, {"window_length": 5})
        np.testing.assert_allclose(out, const, atol=1e-12)

    def test_kernel_normalised_to_one(self):
        # For a slowly-varying signal the moving average must not
        # change the mean. Mean preservation is a sanity check on the
        # 1/N kernel scaling.
        wl = np.linspace(200.0, 800.0, 101)
        a = _gaussian(wl, 500.0, 60.0, height=1.0)
        out = us.compute_moving_avg(wl, a, {"window_length": 5})
        self.assertAlmostEqual(float(np.mean(out)),
                               float(np.mean(a)),
                               places=4)

    def test_output_keeps_input_shape(self):
        for n_samples in (10, 11, 100, 1001):
            wl = np.linspace(200.0, 800.0, n_samples)
            a = _gaussian(wl, 500.0, 60.0, height=1.0)
            out = us.compute_moving_avg(wl, a, {"window_length": 5})
            self.assertEqual(out.shape, a.shape)

    def test_window_length_must_be_positive(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _gaussian(wl, 500.0, 25.5)
        with self.assertRaises(ValueError):
            us.compute_moving_avg(wl, a, {"window_length": 0})

    def test_window_length_must_not_exceed_signal(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            us.compute_moving_avg(wl, a, {"window_length": 99})

    def test_missing_param_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(KeyError):
            us.compute_moving_avg(wl, a, {})


class TestDispatcher(unittest.TestCase):

    def test_dispatch_routes_each_mode(self):
        wl = np.linspace(200.0, 800.0, 101)
        a = _noisy(wl, seed=6)
        sg = us.compute("savgol", wl, a,
                        {"window_length": 5, "polyorder": 2})
        ma = us.compute("moving_avg", wl, a, {"window_length": 5})
        self.assertEqual(sg.shape, a.shape)
        self.assertEqual(ma.shape, a.shape)
        # The two strategies are different; their results must differ.
        self.assertFalse(np.allclose(sg, ma))

    def test_dispatch_unknown_mode_raises(self):
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            us.compute("nope", wl, a, {})

    def test_dispatch_rejects_none(self):
        # Mirrors CS-16: "none" is not a smoothing mode — it is the
        # absence of a smoothing operation, not a no-op operation.
        wl = np.linspace(200.0, 800.0, 11)
        a = np.zeros_like(wl)
        with self.assertRaises(ValueError):
            us.compute("none", wl, a, {})


class TestInputValidation(unittest.TestCase):

    def test_shape_mismatch_raises(self):
        with self.assertRaises(ValueError):
            us.compute_savgol(
                np.linspace(0, 1, 10), np.zeros(9),
                {"window_length": 5, "polyorder": 2},
            )

    def test_2d_input_raises(self):
        with self.assertRaises(ValueError):
            us.compute_savgol(
                np.zeros((3, 4)), np.zeros((3, 4)),
                {"window_length": 5, "polyorder": 2},
            )


# ---- Panel tests -------------------------------------------------------


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestSmoothingPanel(unittest.TestCase):
    """Drive the SmoothingPanel against a real ProjectGraph."""

    def setUp(self):
        self.host = tk.Frame(_root)
        self.host.pack()
        self.graph = ProjectGraph()
        # Phase 4k: subject is pushed in by the host via set_subject.
        self.panel = us.SmoothingPanel(self.host, self.graph)
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
        # PEAK_LIST is not in SmoothingPanel.ACCEPTED_PARENT_TYPES.
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
            us.SmoothingPanel.ACCEPTED_PARENT_TYPES,
            (NodeType.UVVIS, NodeType.BASELINE,
             NodeType.NORMALISED, NodeType.SMOOTHED),
        )

    def test_no_inline_title_label_inside_panel_body(self):
        # Phase 4n (CS-25): the panel body must not render its own
        # "Smoothing" label — the CollapsibleSection wrapper (CS-21)
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
            if lbl.cget("text") == "Smoothing"
        ]
        self.assertEqual(
            offending, [],
            "panel body must not carry an inline 'Smoothing' label "
            "— the CollapsibleSection header owns the title (CS-21).",
        )

    def test_param_rows_rebuild_on_mode_change(self):
        self._add_uvvis()
        self.panel._mode_var.set("savgol")
        self.panel.update_idletasks()
        savgol_rows = len(self.panel._params_frame.winfo_children())
        self.panel._mode_var.set("moving_avg")
        self.panel.update_idletasks()
        moving_rows = len(self.panel._params_frame.winfo_children())
        # savgol = 2 rows (window_length + polyorder); moving_avg = 1.
        self.assertEqual(savgol_rows, 2)
        self.assertEqual(moving_rows, 1)

    # ---- Apply happy paths ------------------------------------------

    def _select_first_subject(self):
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED, NodeType.SMOOTHED):
            for n in self.graph.nodes_of_type(ntype, state=None):
                if n.state != NodeState.DISCARDED and n.active:
                    self.panel.set_subject(n.id)
                    return
        self.fail("no candidate subject node in graph")

    def test_apply_savgol_creates_provisional_op_and_smoothed_node(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("savgol")
        self.panel._window_length.set(11)
        self.panel._polyorder.set(2)

        n_before = len(self.graph.nodes)
        op_id, out_id = self.panel._apply()
        n_after = len(self.graph.nodes)
        self.assertEqual(n_after - n_before, 2,
                         "Apply must add exactly one op + one data node")

        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertIsInstance(op, OperationNode)
        self.assertEqual(op.type, OperationType.SMOOTH)
        self.assertEqual(op.engine, "internal")
        self.assertEqual(op.state, NodeState.PROVISIONAL)
        # Params completeness — mode + sub-schema for savgol.
        self.assertEqual(op.params["mode"], "savgol")
        self.assertEqual(op.params["window_length"], 11)
        self.assertEqual(op.params["polyorder"], 2)

        self.assertIsInstance(out, DataNode)
        self.assertEqual(out.type, NodeType.SMOOTHED)
        self.assertEqual(out.state, NodeState.PROVISIONAL)
        self.assertIn("wavelength_nm", out.arrays)
        self.assertIn("absorbance", out.arrays)
        # Edges parent → op → out.
        self.assertEqual(self.graph.parents_of(op_id), ["u1"])
        self.assertEqual(self.graph.children_of(op_id), [out_id])
        # Metadata footer carries the mode + parent id.
        self.assertEqual(out.metadata["smoothing_mode"], "savgol")
        self.assertEqual(out.metadata["smoothing_parent_id"], "u1")

    def test_apply_moving_avg_creates_smoothed_node(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("moving_avg")
        self.panel._window_length.set(7)

        op_id, out_id = self.panel._apply()
        op = self.graph.get_node(op_id)
        out = self.graph.get_node(out_id)
        self.assertEqual(op.params["mode"], "moving_avg")
        self.assertEqual(op.params["window_length"], 7)
        # No polyorder key on a moving_avg op (CS-03 params completeness:
        # only the keys the algorithm reads).
        self.assertNotIn("polyorder", op.params)
        self.assertEqual(out.type, NodeType.SMOOTHED)

    # ---- Apply rejection paths --------------------------------------

    def test_apply_invalid_window_length_is_rejected_without_creating_nodes(self):
        # Polyorder >= window_length should be caught at compute time
        # and surfaced via messagebox; no nodes added.
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("savgol")
        self.panel._window_length.set(3)
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

    def test_commit_promotes_smoothed_state(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("savgol")
        self.panel._window_length.set(5)
        self.panel._polyorder.set(2)
        _, out_id = self.panel._apply()
        self.graph.commit_node(out_id)
        self.assertEqual(self.graph.get_node(out_id).state,
                         NodeState.COMMITTED)

    def test_discard_marks_smoothed_discarded(self):
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("savgol")
        self.panel._window_length.set(5)
        self.panel._polyorder.set(2)
        _, out_id = self.panel._apply()
        self.graph.discard_node(out_id)
        self.assertEqual(self.graph.get_node(out_id).state,
                         NodeState.DISCARDED)

    def test_chained_smoothing_accepts_smoothed_subject(self):
        # Chained smoothing is allowed: a SMOOTHED node is itself a
        # valid parent for further smoothing.
        self._add_uvvis("u1")
        self._select_first_subject()
        self.panel._mode_var.set("savgol")
        self.panel._window_length.set(5)
        self.panel._polyorder.set(2)
        _, out_id = self.panel._apply()
        self.panel.set_subject(out_id)
        self.assertEqual(self._apply_btn_state(), "normal")


if __name__ == "__main__":
    unittest.main(verbosity=2)
