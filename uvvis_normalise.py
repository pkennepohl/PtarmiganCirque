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
from typing import Callable, List, Mapping, Optional

import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox

from graph import GraphEvent, GraphEventType, ProjectGraph
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


# Local palette — duplicated from uvvis_tab._PALETTE (Phase 4c friction
# point #5 flagged the duplication; Phase 4e's brief explicitly carries
# it forward instead of extracting a helper). The values must stay in
# sync with the loader-side palette so a consistent visual ordering is
# preserved across UVVIS / BASELINE / NORMALISED nodes.
_PALETTE = [
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


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
# Default style for a freshly-created NORMALISED node
# ---------------------------------------------------------------------------


def _default_normalised_style(colour: str) -> dict:
    """Default ``DataNode.style`` for a new NORMALISED node.

    Mirrors ``uvvis_tab._default_uvvis_style`` and
    ``scan_tree_widget._DEFAULT_STYLE``; Phase 4d friction point #3
    already flagged the duplication. We carry it forward here per the
    Phase 4e brief rather than extract a shared module — the third
    copy makes the smell visible without requiring the cross-module
    refactor that would belong in its own session.
    """
    return {
        "color":      colour,
        "linestyle":  "solid",
        "linewidth":  1.5,
        "alpha":      0.9,
        "visible":    True,
        "in_legend":  True,
        "fill":       False,
        "fill_alpha": 0.08,
    }


# ---------------------------------------------------------------------------
# NormalisationPanel — left-panel UI hosting the Apply gesture
# ---------------------------------------------------------------------------


class NormalisationPanel(tk.Frame):
    """Left-panel widget for UV/Vis normalisation (Phase 4e, CS-16).

    Mirrors the Phase 4c baseline panel's shape but materialises a
    NORMALISED operation chain instead of a BASELINE one:

    * **Subject combobox** — chooses which UVVIS / BASELINE /
      NORMALISED node to normalise. Normalising a normalised node is
      allowed (the user might first normalise to peak then to area).
    * **Mode combobox** — ``peak`` / ``area``. On change the parameter
      row frame rebuilds.
    * **Window entries** — ``Window lo / hi`` in nm. Required for both
      modes; blank entries are an error so the OperationNode's params
      dict carries the resolved bounds (CS-03 params completeness).
    * **Apply button** — runs ``_apply()``.

    The panel owns its graph wiring: pass in the ``ProjectGraph`` and
    a callable returning the live spectrum nodes (the host's
    ``_spectrum_nodes`` helper, which already returns UVVIS +
    BASELINE; the host extends it to include NORMALISED in Phase 4e
    Part E so the subject list covers every spectrum the tab plots).
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

        tk.Label(self, text="Normalisation",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        # Subject — which spectrum to normalise.
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

        # Subscribe to graph events so the subject combobox tracks
        # which UVVIS / BASELINE / NORMALISED nodes exist. Lifetime is
        # the panel's: unsubscribed automatically on ``<Destroy>``.
        self._graph.subscribe(self._on_graph_event)
        self.bind("<Destroy>", self._on_destroy_unsubscribe, add="+")

        self._refresh_param_rows()
        self.refresh_subjects()

    # ------------------------------------------------------------------
    # Public refresh API
    # ------------------------------------------------------------------

    def refresh_subjects(self) -> None:
        """Repopulate the subject combobox from the live spectrum nodes.

        The host's ``_spectrum_nodes`` callable is the source of
        truth; this method only translates the list into combobox
        items and preserves the user's selection if it still exists.
        """
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
        """Materialise a provisional NORMALISE op + NORMALISED node.

        One Apply gesture = one new provisional ``NORMALISE``
        OperationNode + one new provisional ``NORMALISED`` DataNode,
        wired ``parent → op → child``. Returns ``(op_id, child_id)``
        on success or ``None`` if the user input was rejected.
        """
        key = self._subject_var.get()
        subject_id = self._subject_map.get(key)
        if not subject_id:
            messagebox.showinfo(
                "Apply Normalisation",
                "Select a spectrum first (load a file or pick from the list).",
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
        if parent_node.type not in (
            NodeType.UVVIS, NodeType.BASELINE, NodeType.NORMALISED,
        ):
            messagebox.showerror(
                "Apply Normalisation",
                "Selected node is not a UV/Vis-style spectrum.",
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
        # from its parent. Phase 4c friction #5 flagged this duplication
        # explicitly; carried forward per the Phase 4e brief.
        existing_uvvis = len(
            self._graph.nodes_of_type(NodeType.UVVIS, state=None))
        existing_baselines = len(
            self._graph.nodes_of_type(NodeType.BASELINE, state=None))
        existing_normalised = len(
            self._graph.nodes_of_type(NodeType.NORMALISED, state=None))
        colour = _PALETTE[
            (existing_uvvis + existing_baselines + existing_normalised)
            % len(_PALETTE)
        ]

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
            style=_default_normalised_style(colour),
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
