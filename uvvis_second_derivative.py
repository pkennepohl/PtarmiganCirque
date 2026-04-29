"""UV/Vis second derivative as an explicit operation (Phase 4i, CS-20).

Two pieces live here, mirroring the Phase 4g CS-18 SmoothingPanel
shape (panel co-located with pure compute):

* ``compute`` — pure-Python numpy / scipy routine. Takes
  ``(wavelength_nm, absorbance, params)`` and returns d²A/dλ² as a
  numpy array of the same shape as the input.
* ``SecondDerivativePanel`` — a Tk frame hosting the subject combobox,
  the two parameter spinboxes (window length + polyorder), and the
  Apply button. The panel owns the graph wiring: each Apply gesture
  creates one provisional ``SECOND_DERIVATIVE`` ``OperationNode`` +
  one provisional ``SECOND_DERIVATIVE`` ``DataNode`` wired
  ``parent → op → child``.

Single algorithm — Savitzky-Golay second derivative via
``scipy.signal.savgol_filter(..., deriv=2)``. No mode discriminator,
unlike SMOOTH / NORMALISE / BASELINE / PEAK_PICK: the savgol
derivative is the de facto standard in spectroscopy because it
smooths and differentiates in one pass, so naive ``np.gradient``
(which amplifies noise without bound) would be a footgun mode rather
than a useful alternative. Required ``params`` keys: ``window_length``
(odd int, ``> polyorder``, ``≤ len(absorbance)``), ``polyorder``
(int ``≥ 2`` — second derivative is undefined for polyorder 0 or 1).

Reproducibility (CS-03 params completeness): every key needed to
reproduce the exact derivative array is captured. The wavelength
spacing is implicit in the parent's ``arrays["wavelength_nm"]`` —
recomputed at apply time from ``np.mean(np.diff(wl))`` to give the
caller correctly-scaled physical units (A/nm² rather than A/sample²).
"""

from __future__ import annotations

import uuid
from typing import Callable, List, Mapping, Optional

import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
from scipy.signal import savgol_filter

from graph import GraphEvent, GraphEventType, ProjectGraph
from node_styles import default_spectrum_style
from nodes import (
    DataNode,
    NodeState,
    NodeType,
    OperationNode,
    OperationType,
)
from version import __version__ as PTARMIGAN_VERSION


__all__ = [
    "compute",
    "SecondDerivativePanel",
]


# Local palette — duplicated from uvvis_tab._PALETTE / uvvis_normalise._PALETTE
# / uvvis_smoothing._PALETTE / uvvis_peak_picking._PALETTE (Phase 4c friction
# #5, Phase 4e friction #2, Phase 4g friction #1, Phase 4h friction #1 each
# flagged the duplication). Carried forward here so a fresh
# SECOND_DERIVATIVE node picks a palette colour distinct from its parent
# without pulling a UI module into this (otherwise compute-only) file's
# import graph. Phase 4i widens the duplication to FIVE callers; the
# `_pick_default_color(graph)` extraction would now touch four locked
# modules, so it stays deferred (BACKLOG friction #1, Phase 4i carry).
_PALETTE = [
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


# ---------------------------------------------------------------------------
# Pure numerical helper
# ---------------------------------------------------------------------------


def _coerce(wavelength_nm, absorbance):
    """Validate inputs and return float64 numpy arrays of equal shape."""
    wl = np.asarray(wavelength_nm, dtype=float)
    a = np.asarray(absorbance, dtype=float)
    if wl.ndim != 1 or a.ndim != 1:
        raise ValueError("wavelength_nm and absorbance must be 1-D arrays")
    if wl.shape != a.shape:
        raise ValueError(
            f"wavelength_nm shape {wl.shape} != absorbance shape {a.shape}"
        )
    return wl, a


def compute(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Compute the Savitzky-Golay second derivative of ``absorbance``.

    Required ``params`` keys: ``window_length`` (odd int, ``> polyorder``
    and ``≤ len(absorbance)``), ``polyorder`` (int ``≥ 2``). Wraps
    ``scipy.signal.savgol_filter`` with ``deriv=2`` and surfaces the
    parameter validation as ``ValueError`` with a user-readable message
    rather than scipy's own assertion text.

    The derivative is scaled by the mean wavelength spacing so the
    output units are A/nm² (physical) rather than A/sample² (which
    would change with the parent's sampling density). For non-uniform
    grids the mean spacing is an approximation; this matches the
    standard analytical-chemistry convention (Owen 1995, Agilent App.
    Note "Derivative spectroscopy") rather than the more rigorous
    re-interpolate-then-differentiate path.
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    window_length = int(params["window_length"])
    polyorder = int(params["polyorder"])

    if window_length < 1:
        raise ValueError("second_derivative: window_length must be >= 1.")
    if window_length % 2 == 0:
        raise ValueError("second_derivative: window_length must be odd.")
    if polyorder < 2:
        raise ValueError(
            "second_derivative: polyorder must be >= 2 "
            "(second derivative is undefined for lower orders)."
        )
    if polyorder >= window_length:
        raise ValueError(
            "second_derivative: polyorder must be < window_length "
            f"(got polyorder={polyorder}, window_length={window_length})."
        )
    if window_length > a.size:
        raise ValueError(
            f"second_derivative: window_length ({window_length}) cannot "
            f"exceed the number of samples ({a.size})."
        )
    if wl.size < 2:
        raise ValueError(
            "second_derivative: need at least two samples to determine "
            "wavelength spacing."
        )

    # Mean wavelength spacing in nm (positive scalar). The savgol kernel
    # assumes uniform spacing — for the typical UV/Vis grid this is true
    # to within < 0.1% so the mean is effectively the exact value.
    delta = float(np.mean(np.abs(np.diff(wl))))
    if delta <= 0:
        raise ValueError(
            "second_derivative: wavelength_nm samples must be strictly "
            "monotonic."
        )

    return np.asarray(
        savgol_filter(
            a,
            window_length=window_length,
            polyorder=polyorder,
            deriv=2,
            delta=delta,
        ),
        dtype=float,
    )


# ---------------------------------------------------------------------------
# SecondDerivativePanel — left-panel UI hosting the Apply gesture
# ---------------------------------------------------------------------------


class SecondDerivativePanel(tk.Frame):
    """Left-panel widget for UV/Vis second derivative (Phase 4i, CS-20).

    Mirrors the Phase 4g ``SmoothingPanel`` shape but materialises a
    ``SECOND_DERIVATIVE`` operation chain instead of a ``SMOOTH`` one:

    * **Subject combobox** — chooses which UVVIS / BASELINE /
      NORMALISED / SMOOTHED node to differentiate. SECOND_DERIVATIVE
      itself is intentionally absent from the candidate set
      (chained second derivatives are physically meaningful only
      rarely, and the locked _spectrum_nodes set already excludes
      this type).
    * **Parameter rows** — single set, no mode discriminator:
      ``window_length`` spinbox (odd, default 11) + ``polyorder``
      spinbox (default 3). Defaults are wider than the smoothing
      panel's because the second derivative is more noise-sensitive
      than the spectrum itself.
    * **Apply button** — runs ``_apply()``.

    The panel owns its graph wiring: pass in the ``ProjectGraph`` and a
    callable returning the live spectrum nodes (the host's
    ``_spectrum_nodes`` helper, which yields UVVIS / BASELINE /
    NORMALISED / SMOOTHED — the same parent set the SmoothingPanel uses).
    """

    def __init__(
        self,
        parent: tk.Misc,
        graph: ProjectGraph,
        spectrum_nodes_fn: Callable[[], List[DataNode]],
        status_cb: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._graph = graph
        self._spectrum_nodes_fn = spectrum_nodes_fn
        self._status_cb = status_cb

        F9 = ("", 9)
        FC = ("Courier", 9)

        tk.Label(self, text="Second derivative",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        # Subject — which spectrum to differentiate.
        subj_frame = tk.Frame(self)
        subj_frame.pack(fill=tk.X, padx=4, pady=2)
        tk.Label(subj_frame, text="Spectrum:", font=F9).pack(anchor="w")
        self._subject_var = tk.StringVar(value="")
        self._subject_map: dict[str, str] = {}
        self._subject_cb = ttk.Combobox(
            subj_frame, textvariable=self._subject_var,
            state="readonly", font=F9, width=24,
        )
        self._subject_cb.pack(fill=tk.X)

        # Parameter Tk vars (kept on the panel so values survive UI
        # rebuilds). Defaults are 11-point Savitzky-Golay window with
        # polyorder 3 — the canonical noise-tolerant starting point for
        # UV/Vis-shaped spectra (narrower windows amplify noise; wider
        # windows blur peaks).
        self._window_length = tk.IntVar(value=11)
        self._polyorder = tk.IntVar(value=3)

        # Parameter rows. Single set (no mode discriminator), so unlike
        # the smoothing / baseline / normalise panels we do not rebuild
        # them on a mode change — they are constructed once and left in
        # place.
        params_frame = tk.Frame(self)
        params_frame.pack(fill=tk.X, padx=4, pady=2)

        def _row(label_text: str) -> tk.Frame:
            row = tk.Frame(params_frame)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=F9, width=15,
                     anchor="w").pack(side=tk.LEFT)
            return row

        # Window length: odd integers from 5 upward. Spinbox with
        # step=2 keeps the value odd as the user clicks the arrows.
        # Lower bound is 5 (not 3 as in smoothing) because the
        # second derivative requires polyorder >= 2 and savgol
        # requires window_length > polyorder; 3 with polyorder 2 is
        # technically legal but degenerate.
        tk.Spinbox(
            _row("Window length:"),
            textvariable=self._window_length,
            from_=5, to=999, increment=2,
            width=8, font=FC,
        ).pack(side=tk.LEFT)
        tk.Spinbox(
            _row("Poly order:"),
            textvariable=self._polyorder,
            from_=2, to=10, increment=1,
            width=8, font=FC,
        ).pack(side=tk.LEFT)

        # Apply button.
        apply_frame = tk.Frame(self)
        apply_frame.pack(fill=tk.X, padx=4, pady=(8, 4))
        self._apply_btn = tk.Button(
            apply_frame, text="Apply Second Derivative",
            font=("", 9, "bold"),
            bg="#003d7a", fg="white", activebackground="#0055aa",
            command=self._apply,
        )
        self._apply_btn.pack(fill=tk.X)

        # Subscribe to graph events so the subject combobox tracks
        # which spectrum nodes exist. Lifetime is the panel's:
        # unsubscribed automatically on ``<Destroy>``.
        self._graph.subscribe(self._on_graph_event)
        self.bind("<Destroy>", self._on_destroy_unsubscribe, add="+")

        self.refresh_subjects()

    # ------------------------------------------------------------------
    # Public refresh API
    # ------------------------------------------------------------------

    def refresh_subjects(self) -> None:
        """Repopulate the subject combobox from the live spectrum nodes."""
        nodes = self._spectrum_nodes_fn()
        self._subject_map = {}
        items: List[str] = []
        for n in nodes:
            key = f"{n.label}  [{n.id[:6]}]"
            items.append(key)
            self._subject_map[key] = n.id
        self._subject_cb.configure(values=items)
        if self._subject_var.get() not in items:
            self._subject_var.set(items[0] if items else "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_params(self) -> dict:
        """Read the panel widgets into a params dict.

        Raises ``ValueError`` (with a user-readable message) on bad
        input. Per CS-03 the caller writes whatever this returns
        verbatim into the OperationNode's params dict.
        """
        try:
            window_length = int(self._window_length.get())
        except (ValueError, tk.TclError):
            raise ValueError("Window length must be an integer.")
        try:
            polyorder = int(self._polyorder.get())
        except (ValueError, tk.TclError):
            raise ValueError("Poly order must be an integer.")
        return {"window_length": window_length, "polyorder": polyorder}

    def _on_graph_event(self, event: GraphEvent) -> None:
        """Refresh the subject list on structural / label / active changes."""
        if event.type in (
            GraphEventType.NODE_ADDED,
            GraphEventType.NODE_DISCARDED,
            GraphEventType.NODE_ACTIVE_CHANGED,
            GraphEventType.NODE_LABEL_CHANGED,
            GraphEventType.GRAPH_LOADED,
            GraphEventType.GRAPH_CLEARED,
        ):
            self.refresh_subjects()

    def _on_destroy_unsubscribe(self, _event) -> None:
        try:
            self._graph.unsubscribe(self._on_graph_event)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Apply — materialise op + node
    # ------------------------------------------------------------------

    def _apply(self) -> Optional[tuple[str, str]]:
        """Materialise a provisional SECOND_DERIVATIVE op + node.

        One Apply gesture = one new provisional ``SECOND_DERIVATIVE``
        OperationNode + one new provisional ``SECOND_DERIVATIVE``
        DataNode, wired ``parent → op → child``. Returns
        ``(op_id, child_id)`` on success or ``None`` if the user input
        was rejected.
        """
        key = self._subject_var.get()
        subject_id = self._subject_map.get(key)
        if not subject_id:
            messagebox.showinfo(
                "Apply Second Derivative",
                "Select a spectrum first (load a file or pick from the list).",
            )
            return None
        try:
            parent_node = self._graph.get_node(subject_id)
        except KeyError:
            messagebox.showerror(
                "Apply Second Derivative",
                "Selected spectrum is no longer in the project graph.",
            )
            return None
        if parent_node.type not in (
            NodeType.UVVIS, NodeType.BASELINE,
            NodeType.NORMALISED, NodeType.SMOOTHED,
        ):
            messagebox.showerror(
                "Apply Second Derivative",
                "Selected node is not a UV/Vis-style spectrum.",
            )
            return None

        try:
            params = self._collect_params()
        except ValueError as exc:
            messagebox.showerror("Second derivative parameters", str(exc))
            return None

        wl = parent_node.arrays["wavelength_nm"]
        absorb = parent_node.arrays["absorbance"]
        try:
            d2 = compute(wl, absorb, params)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Second derivative computation", str(exc))
            return None

        op_id = uuid.uuid4().hex
        out_id = uuid.uuid4().hex

        # CS-03 params completeness: window_length + polyorder fully
        # determine the savgol kernel; wavelength spacing is implicit
        # in the parent's wavelength array so it does not need to be
        # captured separately (the operation is reproducible by
        # re-running compute() against the same parent).
        op_node = OperationNode(
            id=op_id,
            type=OperationType.SECOND_DERIVATIVE,
            engine="internal",
            engine_version=PTARMIGAN_VERSION,
            params=dict(params),
            input_ids=[subject_id],
            output_ids=[out_id],
            status="SUCCESS",
            state=NodeState.PROVISIONAL,
        )

        # Default colour for the new SECOND_DERIVATIVE node — pick a
        # fresh palette entry so the derivative curve is visually
        # separable from its parent. Palette index expression is now
        # five-way duplicated (UVVIS load, BASELINE, NORMALISED,
        # SMOOTHED, SECOND_DERIVATIVE); the `_pick_default_color`
        # extraction would touch four locked modules so it stays
        # deferred (carried forward in BACKLOG friction #1).
        existing_uvvis = len(
            self._graph.nodes_of_type(NodeType.UVVIS, state=None))
        existing_baselines = len(
            self._graph.nodes_of_type(NodeType.BASELINE, state=None))
        existing_normalised = len(
            self._graph.nodes_of_type(NodeType.NORMALISED, state=None))
        existing_smoothed = len(
            self._graph.nodes_of_type(NodeType.SMOOTHED, state=None))
        existing_second_deriv = len(
            self._graph.nodes_of_type(NodeType.SECOND_DERIVATIVE, state=None))
        colour = _PALETTE[
            (existing_uvvis + existing_baselines
             + existing_normalised + existing_smoothed
             + existing_second_deriv)
            % len(_PALETTE)
        ]

        # Carry the parent's metadata forward, plus a derivative footer
        # (mirrors CS-15's baseline_mode / baseline_parent_id, CS-16's
        # normalisation_mode / normalisation_parent_id, CS-18's
        # smoothing_mode / smoothing_parent_id). No "_mode" key here
        # because there is no mode discriminator.
        new_meta: dict = {
            **parent_node.metadata,
            "second_derivative_parent_id": subject_id,
        }

        data_node = DataNode(
            id=out_id,
            type=NodeType.SECOND_DERIVATIVE,
            arrays={
                "wavelength_nm": np.asarray(wl, dtype=float),
                "absorbance":    np.asarray(d2, dtype=float),
            },
            metadata=new_meta,
            label=f"{parent_node.label} · d²A/dλ²",
            state=NodeState.PROVISIONAL,
            style=default_spectrum_style(colour),
        )

        # Insert op + data, then wire parent → op → child.
        self._graph.add_node(op_node)
        self._graph.add_node(data_node)
        self._graph.add_edge(subject_id, op_id)
        self._graph.add_edge(op_id, out_id)

        if self._status_cb is not None:
            self._status_cb(
                f"Second derivative applied to {parent_node.label} "
                f"(provisional — commit / discard via the right sidebar)."
            )
        return op_id, out_id
