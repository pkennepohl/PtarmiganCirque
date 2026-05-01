"""UV/Vis peak picking as an explicit operation (Phase 4h, CS-19).

Mirrors the Phase 4g CS-18 SmoothingPanel shape (panel co-located with
pure compute) but materialises a peak-list annotation rather than a
new spectrum:

* ``compute_prominence`` / ``compute_manual`` / ``compute`` — pure
  numpy / scipy routines. Each takes ``(wavelength_nm, absorbance,
  params)`` and returns ``(peak_wavelengths_nm, peak_absorbances,
  peak_prominences)`` — three numpy arrays of equal length. The
  returned ``peak_prominences`` is empty for manual mode (no
  prominence is computed when the user hand-picks wavelengths).
* ``PeakPickingPanel`` — a Tk frame hosting the subject combobox,
  mode combobox, conditional parameter rows, and the Apply button.
  The panel owns the graph wiring: each Apply gesture creates one
  provisional ``PEAK_PICK`` ``OperationNode`` + one provisional
  ``PEAK_LIST`` ``DataNode`` wired ``parent → op → child``.

Two modes per CS-19:

* **prominence** — ``scipy.signal.find_peaks`` with a prominence
  threshold. Required ``params`` keys: ``prominence``
  (float ≥ 0.0). Optional: ``distance`` (int ≥ 1, samples; defaults
  to ``1``). The returned arrays are sorted by wavelength ascending.
* **manual** — user-supplied wavelengths snapped to the nearest
  sample in the parent's wavelength grid. Required ``params`` keys:
  ``wavelengths_nm`` (list[float], length ≥ 1). Each entry resolves
  to the parent's nearest wavelength sample; duplicates collapse so
  the output is deduplicated and sorted ascending.

Single ``OperationType.PEAK_PICK`` with a ``mode``-discriminated
params dict, mirroring CS-15 (BASELINE) / CS-16 (NORMALISE) /
CS-18 (SMOOTH). Reproducibility (CS-03 params completeness): every
key needed to reproduce the exact peak list is captured.
"""

from __future__ import annotations

import uuid
from typing import Callable, Mapping, Optional, Tuple

import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
from scipy.signal import find_peaks

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
    "compute_prominence",
    "compute_manual",
    "compute",
    "PEAK_PICKING_MODES",
    "PeakPickingPanel",
]


PEAK_PICKING_MODES = ("prominence", "manual")


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
    if wl.size == 0:
        raise ValueError("wavelength_nm / absorbance must be non-empty")
    return wl, a


# ---------------------------------------------------------------------------
# Prominence mode
# ---------------------------------------------------------------------------


def compute_prominence(
    wavelength_nm, absorbance, params: Mapping,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Find peaks above a prominence threshold via ``scipy.signal.find_peaks``.

    Required ``params`` keys: ``prominence`` (float ≥ 0.0). Optional:
    ``distance`` (int ≥ 1; minimum sample-spacing between peaks).
    The wavelength grid is sorted ascending before the search so a
    descending input does not invert the prominence semantics; the
    returned arrays are likewise sorted by wavelength ascending.

    Returns ``(peak_wavelengths_nm, peak_absorbances, peak_prominences)``.
    Empty arrays are returned (length 0) when no peaks meet the
    threshold — this is not an error.
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    prominence = float(params["prominence"])
    if not np.isfinite(prominence) or prominence < 0.0:
        raise ValueError(
            "prominence: prominence must be a finite, non-negative float."
        )
    distance = params.get("distance", 1)
    try:
        distance = int(distance)
    except (TypeError, ValueError):
        raise ValueError("prominence: distance must be a positive integer.")
    if distance < 1:
        raise ValueError("prominence: distance must be >= 1.")

    # Sort ascending so find_peaks operates on a monotonically-rising
    # x-axis. Prominence is computed on the y-array; the order matters
    # only if we report indices, so we re-sort the outputs by wavelength
    # afterwards (already ascending here, but kept explicit for clarity).
    order = np.argsort(wl)
    wl_s = wl[order]
    a_s = a[order]

    indices, props = find_peaks(
        a_s, prominence=prominence, distance=distance,
    )
    peak_wl = wl_s[indices]
    peak_a = a_s[indices]
    peak_prom = np.asarray(props.get("prominences", []), dtype=float)
    return (
        np.asarray(peak_wl, dtype=float),
        np.asarray(peak_a, dtype=float),
        peak_prom,
    )


# ---------------------------------------------------------------------------
# Manual mode
# ---------------------------------------------------------------------------


def compute_manual(
    wavelength_nm, absorbance, params: Mapping,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Snap user-supplied wavelengths to the nearest sample in the parent.

    Required ``params`` keys: ``wavelengths_nm`` (sequence of floats,
    length ≥ 1). Each entry resolves to the index of the parent's
    nearest wavelength sample; duplicates are collapsed and the output
    is sorted ascending by wavelength. ``peak_prominences`` is returned
    as an empty array (no prominence is computed for hand-picked peaks).
    """
    wl, a = _coerce(wavelength_nm, absorbance)
    requested = params["wavelengths_nm"]
    requested_arr = np.asarray(list(requested), dtype=float)
    if requested_arr.size == 0:
        raise ValueError(
            "manual: at least one wavelength is required."
        )
    if not np.all(np.isfinite(requested_arr)):
        raise ValueError(
            "manual: every wavelength must be a finite number."
        )
    # Nearest-sample snap. argmin over |wl - target| is O(N·M) for N
    # samples and M requested wavelengths — fine for typical UV/Vis
    # spectra (N ≈ 1000, M ≤ tens).
    snapped_indices = [
        int(np.argmin(np.abs(wl - target))) for target in requested_arr
    ]
    unique_indices = sorted(set(snapped_indices), key=lambda i: float(wl[i]))
    peak_wl = wl[unique_indices]
    peak_a = a[unique_indices]
    return (
        np.asarray(peak_wl, dtype=float),
        np.asarray(peak_a, dtype=float),
        np.asarray([], dtype=float),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


_DISPATCH = {
    "prominence": compute_prominence,
    "manual":     compute_manual,
}


def compute(mode: str, wavelength_nm, absorbance, params: Mapping | None):
    """Dispatch to the appropriate ``compute_*`` by mode name.

    Raises ``ValueError`` on unknown modes (mirrors CS-15 / CS-16 /
    CS-18: the absence of peak picking is the absence of a PEAK_LIST
    node, not a no-op operation).
    """
    if mode not in _DISPATCH:
        raise ValueError(
            f"unknown peak-picking mode {mode!r}; expected one of "
            f"{PEAK_PICKING_MODES}"
        )
    fn = _DISPATCH[mode]
    return fn(wavelength_nm, absorbance, params or {})


# ---------------------------------------------------------------------------
# PeakPickingPanel — left-panel UI hosting the Apply gesture
# ---------------------------------------------------------------------------


class PeakPickingPanel(tk.Frame):
    """Left-panel widget for UV/Vis peak picking (Phase 4h, CS-19; Phase 4k).

    Materialises a ``PEAK_PICK`` operation chain that emits a
    ``PEAK_LIST`` annotation node, on the *shared subject* selected
    by the host tab's top-of-pane combobox (Phase 4k, CS-22):

    * **Mode combobox** — ``prominence`` / ``manual``. On change the
      parameter row frame rebuilds.
    * **Per-mode parameter rows** —
      * prominence: ``Prominence`` entry (float, default 0.05) +
        ``Min distance`` spinbox (samples, default 1).
      * manual: ``Wavelengths (nm, comma-separated)`` text entry.
    * **Apply button** — runs ``_apply()``. Disabled when the host's
      shared subject is missing or its NodeType is not in
      :attr:`ACCEPTED_PARENT_TYPES`.

    PEAK_LIST and SECOND_DERIVATIVE nodes are intentionally absent
    from :attr:`ACCEPTED_PARENT_TYPES` (chained peak picking on a
    peak-list / derivative is undefined).
    """

    #: NodeTypes the panel accepts as parents for the PEAK_PICK op.
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

        tk.Label(self, text="Peak picking",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        # Mode.
        mode_frame = tk.Frame(self)
        mode_frame.pack(fill=tk.X, padx=4, pady=(6, 2))
        tk.Label(mode_frame, text="Mode:", font=F9).pack(anchor="w")
        self._mode_var = tk.StringVar(value="prominence")
        self._mode_cb = ttk.Combobox(
            mode_frame, textvariable=self._mode_var,
            values=list(PEAK_PICKING_MODES),
            state="readonly", font=F9, width=24,
        )
        self._mode_cb.pack(fill=tk.X)
        self._mode_var.trace_add(
            "write", lambda *_: self._refresh_param_rows())

        # Per-mode Tk vars (kept on the panel so values survive mode
        # flips). Default prominence threshold (0.05) is a reasonable
        # starting point for UV/Vis absorbance spectra (peaks above
        # ~5% of full-scale amplitude); the user adjusts up or down.
        self._prominence = tk.StringVar(value="0.05")
        self._distance = tk.IntVar(value=1)
        self._manual_wavelengths = tk.StringVar(value="")

        # Conditional parameter rows. Rebuilt on every mode change.
        self._params_frame = tk.Frame(self)
        self._params_frame.pack(fill=tk.X, padx=4, pady=2)

        # Apply button.
        apply_frame = tk.Frame(self)
        apply_frame.pack(fill=tk.X, padx=4, pady=(8, 4))
        self._apply_btn = tk.Button(
            apply_frame, text="Apply Peak Picking", font=("", 9, "bold"),
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

        if mode == "prominence":
            tk.Entry(
                _row("Prominence:"),
                textvariable=self._prominence,
                width=10, font=FC,
            ).pack(side=tk.LEFT)
            tk.Spinbox(
                _row("Min distance:"),
                textvariable=self._distance,
                from_=1, to=999, increment=1,
                width=8, font=FC,
            ).pack(side=tk.LEFT)
        elif mode == "manual":
            # Wavelengths entry spans the row so the user can list a
            # handful of comma-separated values without horizontal
            # scrolling. The label sits above the entry.
            tk.Label(self._params_frame,
                     text="Wavelengths (nm, comma-separated):",
                     font=F9, anchor="w").pack(fill=tk.X)
            tk.Entry(self._params_frame,
                     textvariable=self._manual_wavelengths,
                     font=FC).pack(fill=tk.X, pady=(0, 2))

    def _collect_params(self, mode: str) -> dict:
        """Read the panel widgets for ``mode`` into a params dict.

        Raises ``ValueError`` (with a user-readable message) on bad
        input. Per CS-03 the caller writes whatever this returns
        verbatim into the OperationNode's params dict.
        """
        if mode == "prominence":
            try:
                prominence = float(self._prominence.get())
            except ValueError:
                raise ValueError("Prominence must be a numeric value.")
            try:
                distance = int(self._distance.get())
            except (ValueError, tk.TclError):
                raise ValueError("Min distance must be an integer.")
            return {"prominence": prominence, "distance": distance}
        if mode == "manual":
            raw = self._manual_wavelengths.get().strip()
            if not raw:
                raise ValueError(
                    "Wavelengths required (≥1 nm value, comma-separated).")
            try:
                wavelengths = [
                    float(x.strip()) for x in raw.split(",") if x.strip()
                ]
            except ValueError:
                raise ValueError(
                    "Wavelengths must be comma-separated numbers (nm).")
            if not wavelengths:
                raise ValueError("Wavelengths required (≥1 nm value).")
            return {"wavelengths_nm": wavelengths}
        raise ValueError(f"Unknown peak-picking mode: {mode!r}")

    # ------------------------------------------------------------------
    # Apply — materialise op + node
    # ------------------------------------------------------------------

    def _apply(self) -> Optional[tuple[str, str]]:
        """Materialise a provisional PEAK_PICK op + PEAK_LIST node.

        One Apply gesture = one new provisional ``PEAK_PICK``
        OperationNode + one new provisional ``PEAK_LIST`` DataNode,
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
                "Apply Peak Picking",
                "Select a spectrum from the top of the left pane first.",
            )
            return None
        try:
            parent_node = self._graph.get_node(subject_id)
        except KeyError:
            messagebox.showerror(
                "Apply Peak Picking",
                "Selected spectrum is no longer in the project graph.",
            )
            return None
        if parent_node.type not in self.ACCEPTED_PARENT_TYPES:
            messagebox.showerror(
                "Apply Peak Picking",
                "Selected node is not a valid parent for peak picking.",
            )
            return None

        mode = self._mode_var.get()
        try:
            params = self._collect_params(mode)
        except ValueError as exc:
            messagebox.showerror("Peak picking parameters", str(exc))
            return None

        wl = parent_node.arrays["wavelength_nm"]
        absorb = parent_node.arrays["absorbance"]
        try:
            peak_wl, peak_a, peak_prom = compute(mode, wl, absorb, params)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Peak picking computation", str(exc))
            return None

        op_id = uuid.uuid4().hex
        out_id = uuid.uuid4().hex

        # CS-03 params completeness: ``mode`` is the discriminator;
        # the remaining keys are the mode-specific sub-schema (CS-19).
        op_params = {"mode": mode, **params}
        op_node = OperationNode(
            id=op_id,
            type=OperationType.PEAK_PICK,
            engine="internal",
            engine_version=PTARMIGAN_VERSION,
            params=op_params,
            input_ids=[subject_id],
            output_ids=[out_id],
            status="SUCCESS",
            state=NodeState.PROVISIONAL,
        )

        # Default colour for the new PEAK_LIST node — pick a fresh
        # palette entry so the markers are visually separable from the
        # parent curve. CS-21 (Phase 4j) replaced the inline
        # palette-index expression with the shared pick_default_color
        # helper that walks every spectrum-shaped NodeType (PEAK_LIST
        # included) in one go.
        colour = pick_default_color(self._graph)

        # Carry the parent's metadata forward, plus a peak-picking
        # footer (mirrors CS-15's baseline_mode / baseline_parent_id,
        # CS-16's normalisation_mode / normalisation_parent_id, CS-18's
        # smoothing_mode / smoothing_parent_id).
        new_meta: dict = {
            **parent_node.metadata,
            "peak_picking_mode":      mode,
            "peak_picking_parent_id": subject_id,
            "peak_count":             int(peak_wl.size),
        }

        arrays: dict = {
            "peak_wavelengths_nm": np.asarray(peak_wl, dtype=float),
            "peak_absorbances":    np.asarray(peak_a, dtype=float),
        }
        # Prominence is mode-specific; only emit the key when the
        # algorithm actually computed it (manual mode returns []).
        if peak_prom.size:
            arrays["peak_prominences"] = np.asarray(peak_prom, dtype=float)

        data_node = DataNode(
            id=out_id,
            type=NodeType.PEAK_LIST,
            arrays=arrays,
            metadata=new_meta,
            label=f"{parent_node.label} · peaks ({mode})",
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
                f"Peak picking ({mode}) found {int(peak_wl.size)} peak(s) "
                f"in {parent_node.label} (provisional — commit / discard "
                f"via the right sidebar)."
            )
        return op_id, out_id
