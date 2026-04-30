"""UV/Vis smoothing as an explicit operation (Phase 4g, CS-18).

Two pieces live here, mirroring the Phase 4e CS-16 NormalisationPanel
shape (panel co-located with pure compute):

* ``compute_savgol`` / ``compute_moving_avg`` / ``compute`` — pure-Python
  numpy / scipy routines. Each takes ``(wavelength_nm, absorbance,
  params)`` and returns the smoothed absorbance as a numpy array of the
  same shape as the input.
* ``SmoothingPanel`` — a Tk frame hosting the subject combobox, mode
  combobox, conditional parameter rows, and the Apply button. The panel
  owns the graph wiring: each Apply gesture creates one provisional
  ``SMOOTH`` ``OperationNode`` + one provisional ``SMOOTHED``
  ``DataNode`` wired ``parent → op → child``.

Two modes per the Phase 4g brief:

* **savgol** — Savitzky-Golay filter (``scipy.signal.savgol_filter``).
  Required ``params`` keys: ``window_length`` (odd int > ``polyorder``,
  ≤ len(absorbance)), ``polyorder`` (int ≥ 0).
* **moving_avg** — uniform moving average over ``window_length``
  samples, reflect-padded at the edges so the output keeps the input
  shape. Required ``params`` keys: ``window_length`` (int ≥ 1,
  ≤ len(absorbance)).

Single ``OperationType.SMOOTH`` with a ``mode``-discriminated params
dict, mirroring CS-15 (BASELINE) / CS-16 (NORMALISE). Reproducibility
(CS-03 params completeness): every key needed to reproduce the exact
smoothed array is captured.
"""

from __future__ import annotations

import uuid
from typing import Callable, List, Mapping, Optional

import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
from scipy.signal import savgol_filter

from graph import GraphEvent, GraphEventType, ProjectGraph
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
    "compute_savgol",
    "compute_moving_avg",
    "compute",
    "SMOOTHING_MODES",
    "SmoothingPanel",
]


SMOOTHING_MODES = ("savgol", "moving_avg")


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


# ---------------------------------------------------------------------------
# Savitzky-Golay
# ---------------------------------------------------------------------------


def compute_savgol(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Apply a Savitzky-Golay filter to ``absorbance``.

    Required ``params`` keys: ``window_length`` (odd int, ``>polyorder``
    and ``≤ len(absorbance)``), ``polyorder`` (int ``≥ 0``). Wraps
    ``scipy.signal.savgol_filter`` and surfaces the parameter validation
    as ``ValueError`` with a user-readable message rather than scipy's
    own assertion text.
    """
    _, a = _coerce(wavelength_nm, absorbance)
    window_length = int(params["window_length"])
    polyorder = int(params["polyorder"])

    if window_length < 1:
        raise ValueError("savgol: window_length must be >= 1.")
    if window_length % 2 == 0:
        raise ValueError("savgol: window_length must be odd.")
    if polyorder < 0:
        raise ValueError("savgol: polyorder must be >= 0.")
    if polyorder >= window_length:
        raise ValueError(
            "savgol: polyorder must be < window_length "
            f"(got polyorder={polyorder}, window_length={window_length})."
        )
    if window_length > a.size:
        raise ValueError(
            f"savgol: window_length ({window_length}) cannot exceed the "
            f"number of samples ({a.size})."
        )

    return np.asarray(
        savgol_filter(a, window_length=window_length, polyorder=polyorder),
        dtype=float,
    )


# ---------------------------------------------------------------------------
# Moving average
# ---------------------------------------------------------------------------


def compute_moving_avg(
    wavelength_nm, absorbance, params: Mapping,
) -> np.ndarray:
    """Apply a uniform moving average (length ``window_length``).

    Required ``params`` keys: ``window_length`` (int ``≥ 1``,
    ``≤ len(absorbance)``). The signal is reflect-padded so the output
    keeps the input shape; an odd ``window_length`` keeps the kernel
    centred at every sample (an even ``window_length`` is allowed but
    introduces a half-sample shift, so the panel offers odd values
    only).
    """
    _, a = _coerce(wavelength_nm, absorbance)
    window_length = int(params["window_length"])

    if window_length < 1:
        raise ValueError("moving_avg: window_length must be >= 1.")
    if window_length > a.size:
        raise ValueError(
            f"moving_avg: window_length ({window_length}) cannot exceed "
            f"the number of samples ({a.size})."
        )
    if window_length == 1:
        return a.copy()

    # Reflect-pad so edges keep their amplitude (boxcar convolution
    # would otherwise pull edge samples toward zero / NaN). The
    # ``reflect`` mode mirrors without repeating the edge sample.
    half = window_length // 2
    pad_lo = half
    pad_hi = window_length - 1 - half
    padded = np.pad(a, (pad_lo, pad_hi), mode="reflect")
    kernel = np.full(window_length, 1.0 / window_length, dtype=float)
    return np.convolve(padded, kernel, mode="valid")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


_DISPATCH = {
    "savgol":     compute_savgol,
    "moving_avg": compute_moving_avg,
}


def compute(mode: str, wavelength_nm, absorbance, params: Mapping | None):
    """Dispatch to the appropriate ``compute_*`` by mode name.

    Convenience for callers that hold the mode as a string. Raises
    ``ValueError`` on unknown modes (mirrors CS-15 / CS-16: the absence
    of smoothing is the absence of a SMOOTHED node, not a no-op
    operation).
    """
    if mode not in _DISPATCH:
        raise ValueError(
            f"unknown smoothing mode {mode!r}; expected one of "
            f"{SMOOTHING_MODES}"
        )
    fn = _DISPATCH[mode]
    return fn(wavelength_nm, absorbance, params or {})


# ---------------------------------------------------------------------------
# SmoothingPanel — left-panel UI hosting the Apply gesture
# ---------------------------------------------------------------------------


class SmoothingPanel(tk.Frame):
    """Left-panel widget for UV/Vis smoothing (Phase 4g, CS-18).

    Mirrors the Phase 4e ``NormalisationPanel`` shape but materialises
    a ``SMOOTH`` operation chain instead of a ``NORMALISE`` one:

    * **Subject combobox** — chooses which UVVIS / BASELINE /
      NORMALISED / SMOOTHED node to smooth. Smoothing a smoothed node
      is allowed (the user might iterate Savitzky-Golay then a final
      moving-average pass).
    * **Mode combobox** — ``savgol`` / ``moving_avg``. On change the
      parameter row frame rebuilds.
    * **Per-mode parameter rows** —
      * savgol: ``window_length`` spinbox (odd, default 5) +
        ``polyorder`` spinbox (default 2).
      * moving_avg: ``window_length`` spinbox (odd, default 5).
    * **Apply button** — runs ``_apply()``.

    The panel owns its graph wiring: pass in the ``ProjectGraph`` and a
    callable returning the live spectrum nodes (the host's
    ``_spectrum_nodes`` helper, which Phase 4g widens to include
    SMOOTHED so the subject list covers every spectrum the tab plots).
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

        tk.Label(self, text="Smoothing",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        # Subject — which spectrum to smooth.
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

        # Mode.
        mode_frame = tk.Frame(self)
        mode_frame.pack(fill=tk.X, padx=4, pady=(6, 2))
        tk.Label(mode_frame, text="Mode:", font=F9).pack(anchor="w")
        self._mode_var = tk.StringVar(value="savgol")
        self._mode_cb = ttk.Combobox(
            mode_frame, textvariable=self._mode_var,
            values=list(SMOOTHING_MODES),
            state="readonly", font=F9, width=24,
        )
        self._mode_cb.pack(fill=tk.X)
        self._mode_var.trace_add(
            "write", lambda *_: self._refresh_param_rows())

        # Per-mode Tk vars (kept on the panel so values survive mode
        # flips). Defaults are the canonical Savitzky-Golay starting
        # parameters for UV/Vis-shaped spectra (5-point window, quadratic).
        self._window_length = tk.IntVar(value=5)
        self._polyorder = tk.IntVar(value=2)

        # Conditional parameter rows. Rebuilt on every mode change to
        # keep layout straightforward (mirrors the baseline / normalise
        # panels).
        self._params_frame = tk.Frame(self)
        self._params_frame.pack(fill=tk.X, padx=4, pady=2)

        # Apply button.
        apply_frame = tk.Frame(self)
        apply_frame.pack(fill=tk.X, padx=4, pady=(8, 4))
        self._apply_btn = tk.Button(
            apply_frame, text="Apply Smoothing", font=("", 9, "bold"),
            bg="#003d7a", fg="white", activebackground="#0055aa",
            command=self._apply,
        )
        self._apply_btn.pack(fill=tk.X)

        # Subscribe to graph events so the subject combobox tracks
        # which spectrum nodes exist. Lifetime is the panel's:
        # unsubscribed automatically on ``<Destroy>``.
        self._graph.subscribe(self._on_graph_event)
        self.bind("<Destroy>", self._on_destroy_unsubscribe, add="+")

        self._refresh_param_rows()
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

        if mode == "savgol":
            # Window length: odd integers from 3 upward. Spinbox with
            # step=2 keeps the value odd as the user clicks the arrows.
            tk.Spinbox(
                _row("Window length:"),
                textvariable=self._window_length,
                from_=3, to=999, increment=2,
                width=8, font=FC,
            ).pack(side=tk.LEFT)
            tk.Spinbox(
                _row("Poly order:"),
                textvariable=self._polyorder,
                from_=0, to=10, increment=1,
                width=8, font=FC,
            ).pack(side=tk.LEFT)
        elif mode == "moving_avg":
            # Same odd-valued spinbox as savgol; polyorder N/A.
            tk.Spinbox(
                _row("Window length:"),
                textvariable=self._window_length,
                from_=1, to=999, increment=2,
                width=8, font=FC,
            ).pack(side=tk.LEFT)

    def _collect_params(self, mode: str) -> dict:
        """Read the panel widgets for ``mode`` into a params dict.

        Raises ``ValueError`` (with a user-readable message) on bad
        input. Per CS-03 the caller writes whatever this returns
        verbatim into the OperationNode's params dict.
        """
        try:
            window_length = int(self._window_length.get())
        except (ValueError, tk.TclError):
            raise ValueError("Window length must be an integer.")
        if mode == "savgol":
            try:
                polyorder = int(self._polyorder.get())
            except (ValueError, tk.TclError):
                raise ValueError("Poly order must be an integer.")
            return {"window_length": window_length, "polyorder": polyorder}
        if mode == "moving_avg":
            return {"window_length": window_length}
        raise ValueError(f"Unknown smoothing mode: {mode!r}")

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
        """Materialise a provisional SMOOTH op + SMOOTHED node.

        One Apply gesture = one new provisional ``SMOOTH``
        OperationNode + one new provisional ``SMOOTHED`` DataNode,
        wired ``parent → op → child``. Returns ``(op_id, child_id)``
        on success or ``None`` if the user input was rejected.
        """
        key = self._subject_var.get()
        subject_id = self._subject_map.get(key)
        if not subject_id:
            messagebox.showinfo(
                "Apply Smoothing",
                "Select a spectrum first (load a file or pick from the list).",
            )
            return None
        try:
            parent_node = self._graph.get_node(subject_id)
        except KeyError:
            messagebox.showerror(
                "Apply Smoothing",
                "Selected spectrum is no longer in the project graph.",
            )
            return None
        if parent_node.type not in (
            NodeType.UVVIS, NodeType.BASELINE,
            NodeType.NORMALISED, NodeType.SMOOTHED,
        ):
            messagebox.showerror(
                "Apply Smoothing",
                "Selected node is not a UV/Vis-style spectrum.",
            )
            return None

        mode = self._mode_var.get()
        try:
            params = self._collect_params(mode)
        except ValueError as exc:
            messagebox.showerror("Smoothing parameters", str(exc))
            return None

        wl = parent_node.arrays["wavelength_nm"]
        absorb = parent_node.arrays["absorbance"]
        try:
            smoothed = compute(mode, wl, absorb, params)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Smoothing computation", str(exc))
            return None

        op_id = uuid.uuid4().hex
        out_id = uuid.uuid4().hex

        # CS-03 params completeness: ``mode`` is the discriminator;
        # the remaining keys are the mode-specific sub-schema (CS-18).
        op_params = {"mode": mode, **params}
        op_node = OperationNode(
            id=op_id,
            type=OperationType.SMOOTH,
            engine="internal",
            engine_version=PTARMIGAN_VERSION,
            params=op_params,
            input_ids=[subject_id],
            output_ids=[out_id],
            status="SUCCESS",
            state=NodeState.PROVISIONAL,
        )

        # Default colour for the new SMOOTHED node — pick a fresh
        # palette entry so the smoothed curve is visually separable
        # from its parent. CS-21 (Phase 4j) replaced the inline
        # palette-index expression with the shared pick_default_color
        # helper that walks every spectrum-shaped NodeType in one go.
        colour = pick_default_color(self._graph)

        # Carry the parent's metadata forward, plus a smoothing footer
        # (mirrors CS-15's baseline_mode / baseline_parent_id and
        # CS-16's normalisation_mode / normalisation_parent_id).
        new_meta: dict = {
            **parent_node.metadata,
            "smoothing_mode":      mode,
            "smoothing_parent_id": subject_id,
        }

        data_node = DataNode(
            id=out_id,
            type=NodeType.SMOOTHED,
            arrays={
                "wavelength_nm": np.asarray(wl, dtype=float),
                "absorbance":    np.asarray(smoothed, dtype=float),
            },
            metadata=new_meta,
            label=f"{parent_node.label} · smooth ({mode})",
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
                f"Smoothing ({mode}) applied to {parent_node.label} "
                f"(provisional — commit / discard via the right sidebar)."
            )
        return op_id, out_id
