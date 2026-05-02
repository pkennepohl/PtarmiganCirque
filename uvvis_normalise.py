"""UV/Vis normalisation as an explicit operation (Phase 4e, CS-16).

Two pieces live here, mirroring the Phase 4c BASELINE shape but with
the panel co-located alongside the pure compute (the brief's call):

* ``compute_peak`` / ``compute_area`` / ``compute`` — pure-Python
  numpy routines. Each takes ``(wavelength_nm, absorbance, params)``
  and returns the normalised absorbance as a numpy array of the same
  shape as the input.
* ``NormalisationPanel`` — a Tk frame hosting the subject combobox,
  mode combobox, conditional parameter rows, and the Apply button.
  The panel owns the graph wiring: each Apply gesture creates one
  provisional ``NORMALISE`` ``OperationNode`` + one provisional
  ``NORMALISED`` ``DataNode`` wired ``parent → op → child``.

Two modes per the Phase 4e brief:

* **peak** — divide the absorbance by the maximum |absorbance| inside
  ``[peak_lo_nm, peak_hi_nm]`` (the peak-search window). Required
  ``params`` keys: ``peak_lo_nm``, ``peak_hi_nm``.
* **area** — divide the absorbance by the integrated |absorbance|
  inside ``[area_lo_nm, area_hi_nm]`` (the integration window),
  computed with ``np.trapezoid``. The divisor is taken in absolute
  value so descending wavelength arrays do not flip the sign.
  Required ``params`` keys: ``area_lo_nm``, ``area_hi_nm``.

There is no ``none`` mode — the absence of normalisation is the
absence of a NORMALISED node. ``compute(...)`` rejects unknown modes
including ``"none"`` so callers cannot accidentally materialise a
no-op operation.

Params completeness (CS-03): each mode lists exactly the keys it
reads from ``params``. Missing keys raise ``KeyError`` (the calling
panel resolves blank fields against the spectrum's full wavelength
range before calling into the compute layer, so the OperationNode's
params dict always contains the resolved bounds).
"""

from __future__ import annotations

import uuid
from typing import Callable, Mapping, Optional

import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox

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
    "compute_peak",
    "compute_area",
    "compute",
    "NORMALISATION_MODES",
    "NormalisationPanel",
]


NORMALISATION_MODES = ("peak", "area")


# ---------------------------------------------------------------------------
# Pure numerical helpers
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


def _window_mask(wl: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Return a boolean mask selecting samples inside ``[lo, hi]``.

    Endpoints are inclusive; ``lo`` and ``hi`` are reordered if the
    caller supplied them in descending order. A window with no samples
    inside it raises ``ValueError`` so the user gets a recognisable
    error rather than a silent NaN.
    """
    if lo > hi:
        lo, hi = hi, lo
    mask = (wl >= lo) & (wl <= hi)
    if not mask.any():
        raise ValueError(
            f"normalisation window [{lo}, {hi}] contains no samples"
        )
    return mask


# ---------------------------------------------------------------------------
# Peak normalisation (divide by max |abs| inside the peak window)
# ---------------------------------------------------------------------------


def compute_peak(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Divide absorbance by its peak |value| inside the search window.

    Required ``params`` keys: ``peak_lo_nm``, ``peak_hi_nm``. The
    divisor is the maximum of ``|absorbance|`` over the samples whose
    wavelength falls inside the window. The whole spectrum (not just
    the window) is then divided by that scalar so the returned array
    has the same shape as the input.
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    lo = float(params["peak_lo_nm"])
    hi = float(params["peak_hi_nm"])
    mask = _window_mask(wl, lo, hi)
    pk = float(np.nanmax(np.abs(a[mask])))
    if not np.isfinite(pk) or pk <= 0.0:
        raise ValueError(
            "peak normalisation: peak |absorbance| is zero or non-finite "
            "in the chosen window"
        )
    return a / pk


# ---------------------------------------------------------------------------
# Area normalisation (divide by integrated |abs| inside the window)
# ---------------------------------------------------------------------------


def compute_area(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Divide absorbance by its integrated |value| inside the window.

    Required ``params`` keys: ``area_lo_nm``, ``area_hi_nm``. The
    divisor is ``|trapezoid(|absorbance|, wavelength_nm)|`` over the
    in-window samples; the absolute value protects against descending
    wavelength arrays that would otherwise yield a negative integral
    (B-003 root cause from Phase 4c).
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    lo = float(params["area_lo_nm"])
    hi = float(params["area_hi_nm"])
    mask = _window_mask(wl, lo, hi)
    # Restrict to in-window samples. The mask is already a 1-D bool
    # array of the same shape as wl/a, so masking preserves order.
    wl_w = wl[mask]
    a_w = a[mask]
    area = float(abs(np.trapezoid(np.abs(a_w), wl_w)))
    if not np.isfinite(area) or area <= 0.0:
        raise ValueError(
            "area normalisation: integrated |absorbance| is zero or "
            "non-finite in the chosen window"
        )
    return a / area


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


_DISPATCH = {
    "peak": compute_peak,
    "area": compute_area,
}


def compute(mode: str, wavelength_nm, absorbance, params: Mapping | None):
    """Dispatch to the appropriate ``compute_*`` by mode name.

    Convenience for callers that hold the mode as a string. Raises
    ``ValueError`` on unknown modes (including ``"none"`` — the
    absence of normalisation is the absence of an operation, not a
    no-op operation).
    """
    if mode not in _DISPATCH:
        raise ValueError(
            f"unknown normalisation mode {mode!r}; expected one of "
            f"{NORMALISATION_MODES}"
        )
    fn = _DISPATCH[mode]
    return fn(wavelength_nm, absorbance, params or {})


# ---------------------------------------------------------------------------
# NormalisationPanel — left-panel UI hosting the Apply gesture
# ---------------------------------------------------------------------------


class NormalisationPanel(tk.Frame):
    """Left-panel widget for UV/Vis normalisation (Phase 4e, CS-16; Phase 4k).

    Materialises a NORMALISED operation chain on the *shared subject*
    selected by the host tab's top-of-pane combobox (Phase 4k, CS-22).

    * **Mode combobox** — ``peak`` / ``area``. On change the parameter
      row frame rebuilds.
    * **Window entries** — ``Window lo / hi`` in nm. Required for both
      modes; blank entries are an error so the OperationNode's params
      dict carries the resolved bounds (CS-03 params completeness).
    * **Apply button** — runs ``_apply()``. Disabled when the host's
      shared subject is missing or its NodeType is not in
      :attr:`ACCEPTED_PARENT_TYPES`.

    The host pushes the shared subject in via :meth:`set_subject`; the
    panel does not own a subject combobox or graph subscription
    (Phase 4k removed those — the tab subscribes once and fans the
    result out to every panel).
    """

    #: NodeTypes the panel accepts as parents for the NORMALISE op.
    #: Normalising a normalised node is allowed (peak-then-area
    #: chains). SMOOTHED is intentionally excluded — normalisation
    #: should run on raw or baseline-corrected curves, before
    #: smoothing, so the smooth window matches the canonical
    #: amplitude scale.
    ACCEPTED_PARENT_TYPES: tuple[NodeType, ...] = (
        NodeType.UVVIS, NodeType.BASELINE, NodeType.NORMALISED,
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
        # combobox (Phase 4k). ``None`` means no subject is selected
        # — the Apply button is disabled in that state.
        self._subject_id: Optional[str] = None

        F9 = ("", 9)
        FC = ("Courier", 9)

        # No inline title label — the CollapsibleSection wrapper (CS-21,
        # Phase 4j) owns the panel header, so a second "Normalisation"
        # label inside the body would duplicate it (Phase 4n, CS-25).

        # Mode.
        mode_frame = tk.Frame(self)
        mode_frame.pack(fill=tk.X, padx=4, pady=(6, 2))
        tk.Label(mode_frame, text="Mode:", font=F9).pack(anchor="w")
        self._mode_var = tk.StringVar(value="peak")
        self._mode_cb = ttk.Combobox(
            mode_frame, textvariable=self._mode_var,
            values=list(NORMALISATION_MODES),
            state="readonly", font=F9, width=24,
        )
        self._mode_cb.pack(fill=tk.X)
        self._mode_var.trace_add(
            "write", lambda *_: self._refresh_param_rows())

        # Per-mode Tk vars (kept on the panel so values survive mode
        # flips). Strings default to empty so the user enters explicit
        # window endpoints — blanks are rejected at Apply per CS-03.
        self._window_lo = tk.StringVar(value="")
        self._window_hi = tk.StringVar(value="")

        # Conditional parameter rows. Rebuilt on every mode change to
        # keep layout straightforward.
        self._params_frame = tk.Frame(self)
        self._params_frame.pack(fill=tk.X, padx=4, pady=2)

        # Apply button.
        apply_frame = tk.Frame(self)
        apply_frame.pack(fill=tk.X, padx=4, pady=(8, 4))
        self._apply_btn = tk.Button(
            apply_frame, text="Apply Normalisation", font=("", 9, "bold"),
            bg="#003d7a", fg="white", activebackground="#0055aa",
            command=self._apply,
        )
        self._apply_btn.pack(fill=tk.X)

        self._refresh_param_rows()
        self._refresh_apply_state()

    # ------------------------------------------------------------------
    # Public subject hand-off (Phase 4k, CS-22)
    # ------------------------------------------------------------------

    def set_subject(self, node_id: Optional[str]) -> None:
        """Adopt the host tab's shared subject selection.

        Called by ``UVVisTab`` whenever the top-of-pane shared
        combobox changes or graph events change the spectrum list.
        Re-evaluates the Apply button state: enabled iff a node id is
        set AND the resolved node's type is in
        :attr:`ACCEPTED_PARENT_TYPES`.
        """
        self._subject_id = node_id
        self._refresh_apply_state()

    def _refresh_apply_state(self) -> None:
        """Disable the Apply button when the shared subject isn't valid."""
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

    def _refresh_param_rows(self) -> None:
        """Rebuild the parameter rows for the currently selected mode."""
        for child in self._params_frame.winfo_children():
            child.destroy()

        F9 = ("", 9)
        FC = ("Courier", 9)
        mode = self._mode_var.get()

        def _row(label_text: str) -> tk.Frame:
            row = tk.Frame(self._params_frame)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=F9, width=15,
                     anchor="w").pack(side=tk.LEFT)
            return row

        # Both modes have the same window-row schema; the row labels
        # change per mode so the user can see whether they are setting
        # a peak-search window or an integration window.
        if mode == "peak":
            tk.Entry(_row("Peak lo (nm):"),
                     textvariable=self._window_lo, width=10,
                     font=FC).pack(side=tk.LEFT)
            tk.Entry(_row("Peak hi (nm):"),
                     textvariable=self._window_hi, width=10,
                     font=FC).pack(side=tk.LEFT)
        elif mode == "area":
            tk.Entry(_row("Area lo (nm):"),
                     textvariable=self._window_lo, width=10,
                     font=FC).pack(side=tk.LEFT)
            tk.Entry(_row("Area hi (nm):"),
                     textvariable=self._window_hi, width=10,
                     font=FC).pack(side=tk.LEFT)

    def _collect_params(self, mode: str) -> dict:
        """Read the panel widgets for ``mode`` into a params dict.

        Raises ``ValueError`` (with a user-readable message) on bad
        input. Per CS-03 the caller writes whatever this returns
        verbatim into the OperationNode's params dict.
        """
        try:
            lo = float(self._window_lo.get())
            hi = float(self._window_hi.get())
        except ValueError:
            raise ValueError("Window endpoints must be numeric (nm).")
        if mode == "peak":
            return {"peak_lo_nm": lo, "peak_hi_nm": hi}
        if mode == "area":
            return {"area_lo_nm": lo, "area_hi_nm": hi}
        raise ValueError(f"Unknown normalisation mode: {mode!r}")

    # ------------------------------------------------------------------
    # Apply — materialise op + node
    # ------------------------------------------------------------------

    def _apply(self) -> Optional[tuple[str, str]]:
        """Materialise a provisional NORMALISE op + NORMALISED node.

        One Apply gesture = one new provisional ``NORMALISE``
        OperationNode + one new provisional ``NORMALISED`` DataNode,
        wired ``parent → op → child``. Returns ``(op_id, child_id)``
        on success or ``None`` if the user input was rejected.

        The shared subject id (Phase 4k, CS-22) is the source of truth
        — set by the host via :meth:`set_subject`. The Apply button is
        disabled when the subject is missing or its NodeType is not in
        :attr:`ACCEPTED_PARENT_TYPES`, but defence-in-depth checks still
        run here in case a programmatic invocation bypasses the gate.
        """
        subject_id = self._subject_id
        if not subject_id:
            messagebox.showinfo(
                "Apply Normalisation",
                "Select a spectrum from the top of the left pane first.",
            )
            return None
        try:
            parent_node = self._graph.get_node(subject_id)
        except KeyError:
            messagebox.showerror(
                "Apply Normalisation",
                "Selected spectrum is no longer in the project graph.",
            )
            return None
        if parent_node.type not in self.ACCEPTED_PARENT_TYPES:
            messagebox.showerror(
                "Apply Normalisation",
                "Selected node is not a valid parent for normalisation.",
            )
            return None

        mode = self._mode_var.get()
        try:
            params = self._collect_params(mode)
        except ValueError as exc:
            messagebox.showerror("Normalisation parameters", str(exc))
            return None

        wl = parent_node.arrays["wavelength_nm"]
        absorb = parent_node.arrays["absorbance"]
        try:
            normalised = compute(mode, wl, absorb, params)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Normalisation computation", str(exc))
            return None

        op_id = uuid.uuid4().hex
        out_id = uuid.uuid4().hex

        # CS-03 params completeness: ``mode`` is the discriminator;
        # the remaining keys are the mode-specific sub-schema (CS-16).
        op_params = {"mode": mode, **params}
        op_node = OperationNode(
            id=op_id,
            type=OperationType.NORMALISE,
            engine="internal",
            engine_version=PTARMIGAN_VERSION,
            params=op_params,
            input_ids=[subject_id],
            output_ids=[out_id],
            status="SUCCESS",
            state=NodeState.PROVISIONAL,
        )

        # Default colour for the new NORMALISED node — pick a fresh
        # palette entry so the normalised curve is visually separable
        # from its parent. CS-21 (Phase 4j) replaced the inline
        # palette-index expression with the shared pick_default_color
        # helper that walks every spectrum-shaped NodeType in one go.
        colour = pick_default_color(self._graph)

        # Carry the parent's metadata forward, plus a normalisation
        # footer (mirrors CS-15's baseline_mode / baseline_parent_id).
        new_meta: dict = {
            **parent_node.metadata,
            "normalisation_mode":      mode,
            "normalisation_parent_id": subject_id,
        }

        data_node = DataNode(
            id=out_id,
            type=NodeType.NORMALISED,
            arrays={
                "wavelength_nm": np.asarray(wl, dtype=float),
                "absorbance":    np.asarray(normalised, dtype=float),
            },
            metadata=new_meta,
            label=f"{parent_node.label} · norm ({mode})",
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
                f"Normalisation ({mode}) applied to {parent_node.label} "
                f"(provisional — commit / discard via the right sidebar)."
            )
        return op_id, out_id
