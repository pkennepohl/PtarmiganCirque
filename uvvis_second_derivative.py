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
from typing import Callable, Mapping, Optional

import numpy as np
import tkinter as tk
from tkinter import messagebox
from scipy.signal import savgol_filter

from graph import ProjectGraph
from node_styles import default_spectrum_style, pick_default_color
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
    """Left-panel widget for UV/Vis second derivative (Phase 4i, CS-20; Phase 4k).

    Materialises a ``SECOND_DERIVATIVE`` operation chain on the
    *shared subject* selected by the host tab's top-of-pane combobox
    (Phase 4k, CS-22):

    * **Parameter rows** — single set, no mode discriminator:
      ``window_length`` spinbox (odd, default 11) + ``polyorder``
      spinbox (default 3). Defaults are wider than the smoothing
      panel's because the second derivative is more noise-sensitive
      than the spectrum itself.
    * **Apply button** — runs ``_apply()``. Disabled when the host's
      shared subject is missing or its NodeType is not in
      :attr:`ACCEPTED_PARENT_TYPES`.

    SECOND_DERIVATIVE itself is intentionally absent from
    :attr:`ACCEPTED_PARENT_TYPES` (chained second derivatives are
    physically meaningful only rarely, and the locked
    ``_spectrum_nodes`` set already excludes this type so the shared
    subject combobox cannot offer one).
    """

    #: NodeTypes the panel accepts as parents for the SECOND_DERIVATIVE op.
    ACCEPTED_PARENT_TYPES: tuple[NodeType, ...] = (
        NodeType.UVVIS, NodeType.BASELINE,
        NodeType.NORMALISED, NodeType.SMOOTHED,
    )

    def __init__(
        self,
        parent: tk.Misc,
        graph: ProjectGraph,
        status_cb: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._graph = graph
        self._status_cb = status_cb

        # Shared-subject id pushed in by the host's top-of-pane
        # combobox (Phase 4k). ``None`` means no subject — Apply is
        # disabled.
        self._subject_id: Optional[str] = None

        F9 = ("", 9)
        FC = ("Courier", 9)

        # No inline title label — the CollapsibleSection wrapper (CS-21,
        # Phase 4j) owns the panel header, so a second "Second derivative"
        # label inside the body would duplicate it (Phase 4n, CS-25).

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

        self._refresh_apply_state()

    # ------------------------------------------------------------------
    # Public subject hand-off (Phase 4k, CS-22)
    # ------------------------------------------------------------------

    def set_subject(self, node_id: Optional[str]) -> None:
        """Adopt the host tab's shared subject selection.

        Re-evaluates the Apply button state: enabled iff a node id is
        set AND the resolved node's type is in
        :attr:`ACCEPTED_PARENT_TYPES`.
        """
        self._subject_id = node_id
        self._refresh_apply_state()

    def _refresh_apply_state(self) -> None:
        """Disable Apply when the shared subject isn't a valid parent."""
        ok = False
        if self._subject_id is not None:
            try:
                node = self._graph.get_node(self._subject_id)
            except KeyError:
                node = None
            if node is not None and node.type in self.ACCEPTED_PARENT_TYPES:
                ok = True
        self._apply_btn.configure(state=("normal" if ok else "disabled"))

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

        The shared subject id (Phase 4k, CS-22) is the source of truth
        — set by the host via :meth:`set_subject`. The Apply button is
        disabled when the subject is missing or its NodeType is not in
        :attr:`ACCEPTED_PARENT_TYPES`, but defence-in-depth checks still
        run here in case a programmatic invocation bypasses the gate.
        """
        subject_id = self._subject_id
        if not subject_id:
            messagebox.showinfo(
                "Apply Second Derivative",
                "Select a spectrum from the top of the left pane first.",
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
        if parent_node.type not in self.ACCEPTED_PARENT_TYPES:
            messagebox.showerror(
                "Apply Second Derivative",
                "Selected node is not a valid parent for second derivative.",
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
        # separable from its parent. CS-21 (Phase 4j) replaced the
        # inline palette-index expression with the shared
        # pick_default_color helper that walks every spectrum-shaped
        # NodeType in one go.
        colour = pick_default_color(self._graph)

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
