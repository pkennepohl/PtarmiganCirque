"""
uvvis_tab.py — UV/Vis/NIR analysis tab for Ptarmigan

Phase 4a (loader migration + sidebar swap): the tab reads from a
ProjectGraph rather than a private `_entries` list. File load creates
a COMMITTED RAW_FILE DataNode + LOAD OperationNode + COMMITTED UVVIS
DataNode wired together (CS-13 §"Implementation notes (Phase 4a)").
No analysis runs automatically — parsing the on-disk format into
arrays is bookkeeping, not science.

The right pane is now ``ScanTreeWidget`` (CS-04). Per-row controls,
gestures, and the gear-button hand-off to the unified
``StyleDialog`` (CS-05) all live in that widget. The tab subscribes
to ``GraphEvent`` so dialog- and row-driven mutations drive the plot
without explicit redraw calls.
"""

from __future__ import annotations

import copy
import os
import uuid
from typing import Callable, List, Optional, Tuple

import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from uvvis_parser import UVVisScan, parse_uvvis_file
from experimental_parser import ExperimentalScan
from graph import GraphEvent, GraphEventType, ProjectGraph
from nodes import (
    DataNode,
    NodeState,
    NodeType,
    OperationNode,
    OperationType,
)
from scan_tree_widget import ScanTreeWidget
from style_dialog import open_style_dialog
import plot_settings_dialog
import uvvis_baseline
import uvvis_normalise
import uvvis_smoothing
import uvvis_peak_picking
import uvvis_second_derivative
import node_export
from collapsible_section import CollapsibleSection
from node_styles import default_spectrum_style, pick_default_color
from version import __version__ as PTARMIGAN_VERSION

# Colour palette: lifted to node_styles.SPECTRUM_PALETTE in Phase 4j
# (CS-21). Both call sites in this file (the UVVIS loader's default
# colour assignment and _apply_baseline's BASELINE colour assignment)
# go through node_styles.pick_default_color, which walks every
# spectrum-shaped NodeType in one go.

# ── File-type filter ──────────────────────────────────────────────────────────
_FILE_TYPES = [
    ("UV/Vis files",
     "*.csv *.tsv *.txt *.prn *.dpt *.sp *.asc *.dat *.olis *.olisdat"),
    ("CSV / text",  "*.csv *.tsv *.txt *.prn"),
    ("OLIS",        "*.olis *.olisdat *.dat *.asc"),
    ("All files",   "*.*"),
]

# ── Unit conversion ───────────────────────────────────────────────────────────
_NM_TO_CM1 = 1e7
_HC_NM_EV  = 1239.84193

def _nm_to(unit: str, nm_val: float) -> float:
    if nm_val <= 0:
        return nm_val
    if unit == "nm":    return nm_val
    if unit == "cm-1":  return _NM_TO_CM1 / nm_val
    if unit == "eV":    return _HC_NM_EV  / nm_val
    return nm_val

def _to_nm(unit: str, val: float) -> float:
    if val <= 0:
        return val
    if unit == "nm":    return val
    if unit == "cm-1":  return _NM_TO_CM1 / val
    if unit == "eV":    return _HC_NM_EV  / val
    return val

def _convert_xlim(lo: float, hi: float,
                  from_unit: str, to_unit: str) -> Tuple[float, float]:
    a = _nm_to(to_unit, _to_nm(from_unit, lo))
    b = _nm_to(to_unit, _to_nm(from_unit, hi))
    return (min(a, b), max(a, b))


def _wavelength_to_x(wavelength_nm: np.ndarray, unit: str) -> np.ndarray:
    """Derive the displayed x-axis from the canonical wavelength_nm array."""
    if unit == "cm-1":
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(wavelength_nm > 0,
                            _NM_TO_CM1 / wavelength_nm, 0.0)
    if unit == "eV":
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(wavelength_nm > 0,
                            _HC_NM_EV / wavelength_nm, 0.0)
    return wavelength_nm


def _absorbance_to_y(absorbance: np.ndarray, y_unit: str) -> np.ndarray:
    if y_unit == "%T":
        return 100.0 * np.power(10.0, -np.clip(absorbance, -10, 10))
    return absorbance


class UVVisTab(tk.Frame):
    """UV/Vis/NIR import, display and analysis panel."""

    def __init__(
        self,
        parent,
        add_scan_fn: Optional[Callable] = None,
        graph: Optional[ProjectGraph] = None,
    ):
        super().__init__(parent)
        self._add_scan_fn: Optional[Callable] = add_scan_fn

        # ProjectGraph: passed in by the host (binah.py once integrated)
        # or constructed locally as a tab-private graph until the host
        # is wired up. The tab routes every mutation through graph
        # methods.
        self._graph: ProjectGraph = graph if graph is not None else ProjectGraph()

        # ── Display options ───────────────────────────────────────────────────
        self._x_unit      = tk.StringVar(value="nm")
        self._x_unit_prev = "nm"
        self._y_unit      = tk.StringVar(value="A")
        self._show_nm_axis = tk.BooleanVar(value=True)

        # ── Axis limits (empty string = auto) ────────────────────────────────
        self._xlim_lo = tk.StringVar(value="")
        self._xlim_hi = tk.StringVar(value="")
        self._ylim_lo = tk.StringVar(value="")
        self._ylim_hi = tk.StringVar(value="")

        # ── Plot Settings configuration (CS-06 / CS-14) ──────────────────────
        # Tab-private dict: fonts, grid, background, legend show/position,
        # tick direction, title/X-label/Y-label text and modes. Initialised
        # from the in-process user defaults if any have been saved this
        # session, falling back to the factory defaults. ``_redraw`` reads
        # from this dict; the ⚙ Plot Settings dialog mutates it in place
        # on Apply. Per Phase 4a friction #4 this is tab-private state, not
        # graph state.
        _src = (
            plot_settings_dialog._USER_DEFAULTS
            or plot_settings_dialog._FACTORY_DEFAULTS
        )
        self._plot_config: dict = copy.deepcopy(dict(_src))

        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    #  Graph helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _uvvis_nodes(self) -> List[DataNode]:
        """Return the UVVIS DataNodes the tab considers "live".

        Live = state != DISCARDED *and* ``active`` is True. The list
        preserves insertion order (Python 3.7+ dict is ordered) so the
        sidebar's row order is deterministic across rebuilds.

        Strictly UVVIS-typed (does not include derived BASELINE nodes);
        callers that want to iterate every spectrum the tab renders
        should use ``_spectrum_nodes`` instead.
        """
        out: List[DataNode] = []
        for node in self._graph.nodes_of_type(NodeType.UVVIS, state=None):
            if node.state == NodeState.DISCARDED:
                continue
            if not node.active:
                continue
            out.append(node)
        return out

    def _spectrum_nodes(self) -> List[DataNode]:
        """Return every spectrum-shaped DataNode the tab considers live.

        Spectrum-shaped today means UVVIS, BASELINE, NORMALISED, or
        SMOOTHED: all four carry ``arrays["wavelength_nm"]`` +
        ``arrays["absorbance"]`` and render through the same
        matplotlib code path. ``_redraw`` and the *shared* subject
        combobox at the top of the left pane (CS-22, Phase 4k)
        iterate this helper. The walk is type-keyed (UVVIS first,
        then BASELINE, then NORMALISED, then SMOOTHED) so a parent
        typically appears above its derivatives in the sidebar /
        subject list when the dict ordering is preserved (Phase 4g
        widening from ``[UVVIS, BASELINE, NORMALISED]`` to include
        SMOOTHED).
        """
        out: List[DataNode] = []
        for ntype in (NodeType.UVVIS, NodeType.BASELINE,
                      NodeType.NORMALISED, NodeType.SMOOTHED):
            for node in self._graph.nodes_of_type(ntype, state=None):
                if node.state == NodeState.DISCARDED:
                    continue
                if not node.active:
                    continue
                out.append(node)
        return out

    def _peak_list_nodes(self) -> List[DataNode]:
        """Return the PEAK_LIST DataNodes the tab considers live.

        PEAK_LIST nodes are annotation overlays (CS-19, Phase 4h) and
        live in a separate iteration from ``_spectrum_nodes`` because
        their array shape differs (``peak_wavelengths_nm`` /
        ``peak_absorbances`` instead of the curve-shaped
        ``wavelength_nm`` / ``absorbance``) and they are not candidate
        parents for baseline / normalisation / smoothing / further
        peak picking.
        """
        out: List[DataNode] = []
        for node in self._graph.nodes_of_type(NodeType.PEAK_LIST, state=None):
            if node.state == NodeState.DISCARDED:
                continue
            if not node.active:
                continue
            out.append(node)
        return out

    def _second_derivative_nodes(self) -> List[DataNode]:
        """Return the SECOND_DERIVATIVE DataNodes the tab considers live.

        SECOND_DERIVATIVE nodes (CS-20, Phase 4i) carry the curve
        schema (``wavelength_nm`` / ``absorbance`` keys, where the
        latter holds d²A/dλ² values) so the renderer plots them with
        the same code path as UVVIS / BASELINE / NORMALISED /
        SMOOTHED. They live in their own iteration because they are
        intentionally absent from ``_spectrum_nodes`` — the locked
        smoothing / baseline / normalise / peak-picking panels'
        parent type checks reject SECOND_DERIVATIVE, so including it
        in ``_spectrum_nodes`` would surface a node in those subject
        comboboxes that those panels would silently refuse on Apply.
        Chained second derivatives are out of scope this phase.
        """
        out: List[DataNode] = []
        for node in self._graph.nodes_of_type(NodeType.SECOND_DERIVATIVE,
                                              state=None):
            if node.state == NodeState.DISCARDED:
                continue
            if not node.active:
                continue
            out.append(node)
        return out

    def _has_existing_load(self, source_file: str, label: str) -> bool:
        """Skip duplicates when the user reloads a file already in the graph."""
        for node in self._graph.nodes_of_type(NodeType.UVVIS, state=None):
            md = node.metadata
            if (md.get("source_file") == source_file
                    and node.label == label
                    and node.state != NodeState.DISCARDED):
                return True
        return False

    # ══════════════════════════════════════════════════════════════════════════
    #  Layout
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        top = tk.Frame(self, bd=1, relief=tk.GROOVE, padx=4, pady=3)
        top.pack(side=tk.TOP, fill=tk.X)
        self._build_toolbar(top)

        lim_bar = tk.Frame(self, bd=1, relief=tk.GROOVE, padx=4, pady=2)
        lim_bar.pack(side=tk.TOP, fill=tk.X)
        self._build_limit_bar(lim_bar)

        body = tk.PanedWindow(self, orient=tk.HORIZONTAL,
                              sashwidth=5, sashrelief=tk.RAISED)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ARCHITECTURE.md §3: three-zone layout — left panel (engine /
        # processing controls), centre (matplotlib figure), right
        # (ScanTreeWidget). The left panel landed in Phase 4c (CS-07
        # §"UV/Vis left panel" + CS-15) hosting baseline correction.
        left_pane = tk.Frame(body, bd=1, relief=tk.SUNKEN)
        body.add(left_pane, minsize=220)
        self._build_left_panel(left_pane)

        plot_pane = tk.Frame(body)
        body.add(plot_pane, minsize=400)
        self._build_plot(plot_pane)

        sidebar_pane = tk.Frame(body, bd=1, relief=tk.SUNKEN)
        body.add(sidebar_pane, minsize=240)
        self._build_sidebar(sidebar_pane)

        # Drive plot redraws off graph events. Dialog and row mutations
        # go through ``graph.set_style`` → ``NODE_STYLE_CHANGED`` which
        # this handler translates into a ``_redraw``. Lifetime is the
        # tab's: unsubscribed automatically on ``<Destroy>``.
        self._graph.subscribe(self._on_graph_event)
        self.bind("<Destroy>", self._on_destroy_unsubscribe, add="+")

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self, bar):
        F9 = ("", 9)

        tk.Button(bar, text="📂 Load File…", font=("", 9, "bold"),
                  bg="#003d7a", fg="white", activebackground="#0055aa",
                  command=self._load_files).pack(side=tk.LEFT, padx=(2, 6))

        def _sep():
            ttk.Separator(bar, orient=tk.VERTICAL).pack(
                side=tk.LEFT, fill=tk.Y, padx=6)

        _sep()
        tk.Label(bar, text="X:", font=F9).pack(side=tk.LEFT)
        for lbl, val in [("nm", "nm"), ("cm⁻¹", "cm-1"), ("eV", "eV")]:
            tk.Radiobutton(bar, text=lbl, variable=self._x_unit, value=val,
                           command=self._on_unit_change, font=F9,
                           ).pack(side=tk.LEFT)

        _sep()
        tk.Label(bar, text="Y:", font=F9).pack(side=tk.LEFT)
        for lbl, val in [("Abs", "A"), ("%T", "%T")]:
            tk.Radiobutton(bar, text=lbl, variable=self._y_unit, value=val,
                           command=self._redraw, font=F9,
                           ).pack(side=tk.LEFT)

        _sep()
        self._nm_cb = tk.Checkbutton(bar, text="λ(nm) axis",
                                     variable=self._show_nm_axis,
                                     command=self._redraw, font=F9)
        self._nm_cb.pack(side=tk.LEFT, padx=2)

        # Phase 4n CS-27 retired the top-bar "+ Add to TDDFT Overlay"
        # bulk button. Each ScanTreeWidget row now carries a per-row
        # → icon that calls ``_send_node_to_compare(node_id)`` —
        # disabled on provisional rows and when no Compare host is
        # connected (mirrors the old button's gate).
        _sep()
        # ⚙ Plot Settings (CS-06): opens the unified Plot Settings
        # dialog for this tab.
        self._plot_settings_btn = tk.Button(
            bar, text="⚙ Plot Settings", font=F9,
            command=self._open_plot_settings,
        )
        self._plot_settings_btn.pack(side=tk.LEFT, padx=2)

        self._status_lbl = tk.Label(bar, text="Load a UV/Vis file to begin.",
                                    fg="gray", font=("", 8))
        self._status_lbl.pack(side=tk.LEFT, padx=10)

    # ── Limit bar ─────────────────────────────────────────────────────────────

    def _build_limit_bar(self, bar):
        F9 = ("", 9)
        FC = ("Courier", 9)

        def _entry(var, width=8):
            e = tk.Entry(bar, textvariable=var, width=width, font=FC)
            e.bind("<Return>",   lambda _: self._redraw())
            e.bind("<FocusOut>", lambda _: self._redraw())
            return e

        def _sep():
            ttk.Separator(bar, orient=tk.VERTICAL).pack(
                side=tk.LEFT, fill=tk.Y, padx=8)

        tk.Label(bar, text="X:", font=F9).pack(side=tk.LEFT)
        _entry(self._xlim_lo).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(bar, text="→", font=F9).pack(side=tk.LEFT, padx=1)
        _entry(self._xlim_hi).pack(side=tk.LEFT)
        tk.Button(bar, text="Auto X", font=("", 8),
                  command=self._auto_x).pack(side=tk.LEFT, padx=(4, 0))

        _sep()

        tk.Label(bar, text="Y:", font=F9).pack(side=tk.LEFT)
        _entry(self._ylim_lo).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(bar, text="→", font=F9).pack(side=tk.LEFT, padx=1)
        _entry(self._ylim_hi).pack(side=tk.LEFT)
        tk.Button(bar, text="Auto Y", font=("", 8),
                  command=self._auto_y).pack(side=tk.LEFT, padx=(4, 0))

    # ── Sidebar (right pane: ScanTreeWidget) ──────────────────────────────────

    def _build_sidebar(self, parent):
        """Construct the right-pane sidebar around a ``ScanTreeWidget``.

        The widget filters to ``NodeType.UVVIS``; its row controls
        write through ``graph.set_style`` (CS-04), and the gear button
        delegates to the unified style dialog (CS-05) via
        ``style_dialog_cb``. Phase 4n CS-27 wires
        ``send_to_compare_cb`` to ``_send_node_to_compare`` so the
        per-row → icon pushes a single spectrum into the TDDFT
        overlay (replacing the legacy bulk top-bar button).
        ``export_cb`` is wired to ``_on_export_node`` for the row
        Export… gesture (CS-17, Phase 4f).
        """
        tk.Label(parent, text="Loaded Spectra",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        self._scan_tree = ScanTreeWidget(
            parent,
            self._graph,
            [NodeType.UVVIS, NodeType.BASELINE,
             NodeType.NORMALISED, NodeType.SMOOTHED,
             NodeType.PEAK_LIST, NodeType.SECOND_DERIVATIVE],
            redraw_cb=self._redraw,
            send_to_compare_cb=self._send_node_to_compare,
            style_dialog_cb=self._open_style_dialog_for_node,
            export_cb=self._on_export_node,
        )
        self._scan_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    # ── Left panel (baseline + normalisation + smoothing + peak picking
    #    + second derivative,
    #    CS-07 + CS-15 + CS-16 + CS-18 + CS-19 + CS-20) ──

    def _build_left_panel(self, parent):
        """Construct the left panel with processing controls.

        Per CS-07 §"UV/Vis left panel" the left panel hosts the
        user-initiated UV/Vis operations. Phase 4k (CS-22) introduces
        a shared "Spectrum:" combobox at the top of the pane (above
        every CollapsibleSection); the user picks a subject once and
        every operation panel + the inline baseline section adopts
        it via ``set_subject``. Each panel exposes
        ``ACCEPTED_PARENT_TYPES`` and disables its Apply button when
        the shared selection isn't a valid parent for that op.

        * **Baseline correction** (CS-15, Phase 4c) — inline section
          with a four-mode baseline combobox (linear / polynomial /
          spline / rubberband), conditional parameter rows, and an
          "Apply Baseline" button. Accepts UVVIS / BASELINE parents.
        * **Normalisation** (CS-16, Phase 4e) — ``NormalisationPanel``
          subwidget with a two-mode combobox (peak / area), per-mode
          window entries, and an "Apply Normalisation" button.
          Accepts UVVIS / BASELINE / NORMALISED parents.
        * **Smoothing** (CS-18, Phase 4g) — ``SmoothingPanel`` with
          a two-mode combobox (savgol / moving_avg), per-mode
          parameter rows, and an "Apply Smoothing" button. Accepts
          UVVIS / BASELINE / NORMALISED / SMOOTHED parents.
        * **Peak picking** (CS-19, Phase 4h) — ``PeakPickingPanel``
          with a two-mode combobox (prominence / manual), per-mode
          parameter rows, and an "Apply Peak Picking" button. Each
          Apply gesture creates a provisional ``PEAK_LIST``
          annotation node rendered as scatter on the parent curve.
          Accepts UVVIS / BASELINE / NORMALISED / SMOOTHED parents.
        * **Second derivative** (CS-20, Phase 4i) —
          ``SecondDerivativePanel`` with two parameter spinboxes
          (window length + poly order) and an "Apply Second
          Derivative" button. Single algorithm (Savitzky-Golay with
          deriv=2). Accepts UVVIS / BASELINE / NORMALISED / SMOOTHED
          parents.

        Each Apply gesture creates one provisional OperationNode +
        DataNode pair; the user commits or discards via the
        ``ScanTreeWidget`` on the right.

        Phase 4j (CS-21) wraps every section in a
        :class:`CollapsibleSection` so users can hide the panels they
        are not currently using and reclaim vertical space. All five
        sections start collapsed; clicking the chevron header strip
        toggles. Per-section state is held in each section's own
        ``tk.BooleanVar`` and is not persisted to project files this
        phase (Phase 8 concern).
        """
        F9 = ("", 9)
        FC = ("Courier", 9)

        tk.Label(parent, text="Processing",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        # ── Shared subject combobox (CS-22, Phase 4k) ────────────────────
        # USER-FLAGGED end of Phase 4j: the per-panel "Spectrum:"
        # combobox felt redundant. Lifting it here means the user picks
        # the spectrum once, then expands the section for whichever
        # operation they want to apply. The combobox is always visible,
        # above every CollapsibleSection. Each panel exposes
        # ``set_subject`` + ``ACCEPTED_PARENT_TYPES`` (CS-22) so its
        # Apply button is disabled when the shared selection isn't a
        # valid parent for that op.
        shared_frame = tk.Frame(parent)
        shared_frame.pack(fill=tk.X, padx=4, pady=(0, 2))
        tk.Label(shared_frame, text="Spectrum:",
                 font=F9).pack(anchor="w")
        self._shared_subject = tk.StringVar(value="")
        self._shared_subject_map: dict[str, str] = {}
        self._shared_subject_cb = ttk.Combobox(
            shared_frame, textvariable=self._shared_subject,
            state="readonly", font=F9, width=24,
        )
        self._shared_subject_cb.pack(fill=tk.X)
        # Whenever the user picks a new subject (or _refresh repopulates
        # the values), fan it out to every panel + the inline baseline
        # gate.
        self._shared_subject.trace_add(
            "write", lambda *_: self._on_shared_subject_changed())

        # ── Baseline section (CS-15, Phase 4c) ───────────────────────────
        # Inline section — no panel subwidget. The widgets pack into
        # the CollapsibleSection's body frame; everything else
        # (Tk vars, refresh callbacks) stays on the tab.
        self._baseline_section = CollapsibleSection(
            parent, title="Baseline correction", expanded=False)
        self._baseline_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        bl_body = self._baseline_section.body

        # Phase 4k: the baseline section's inline subject combobox is
        # gone — the shared combobox above the sections is the source
        # of truth. The resolved id lives on the tab as
        # ``self._baseline_subject_id`` (set by
        # ``_on_shared_subject_changed``); ``_apply_baseline_btn`` is
        # disabled when the shared selection isn't a UVVIS / BASELINE
        # parent.
        self._baseline_subject_id: Optional[str] = None
        self._BASELINE_ACCEPTED_PARENT_TYPES: tuple = (
            NodeType.UVVIS, NodeType.BASELINE,
        )

        # Baseline mode.
        mode_frame = tk.Frame(bl_body)
        mode_frame.pack(fill=tk.X, padx=4, pady=(6, 2))
        tk.Label(mode_frame, text="Baseline mode:", font=F9).pack(anchor="w")
        self._baseline_mode = tk.StringVar(value="linear")
        self._baseline_mode_cb = ttk.Combobox(
            mode_frame, textvariable=self._baseline_mode,
            values=list(uvvis_baseline.BASELINE_MODES),
            state="readonly", font=F9, width=24,
        )
        self._baseline_mode_cb.pack(fill=tk.X)
        self._baseline_mode.trace_add(
            "write", lambda *_: self._refresh_baseline_param_rows())

        # Per-mode parameter Tk vars (kept on the tab so values
        # survive mode flips). String entries default to empty so the
        # user is forced to enter window endpoints explicitly.
        self._baseline_anchor_lo = tk.StringVar(value="")
        self._baseline_anchor_hi = tk.StringVar(value="")
        self._baseline_poly_order = tk.IntVar(value=2)
        self._baseline_fit_lo = tk.StringVar(value="")
        self._baseline_fit_hi = tk.StringVar(value="")
        self._baseline_spline_anchors = tk.StringVar(value="")  # comma-sep nm
        # CS-24 (Phase 4m) scattering mode: power-law c · λ^(-n).
        # ``_baseline_scattering_n`` defaults to "4" (Rayleigh); the
        # ``_baseline_scattering_fit_n`` BooleanVar, when checked,
        # makes ``_collect_baseline_params`` emit ``params["n"]="fit"``
        # so the helper recovers n alongside the amplitude.
        self._baseline_scattering_n = tk.StringVar(value="4")
        self._baseline_scattering_fit_n = tk.BooleanVar(value=False)
        self._baseline_scattering_fit_lo = tk.StringVar(value="")
        self._baseline_scattering_fit_hi = tk.StringVar(value="")

        # Conditional parameter rows. The frame is rebuilt on every
        # mode change to keep layout straightforward.
        self._baseline_params_frame = tk.Frame(bl_body)
        self._baseline_params_frame.pack(fill=tk.X, padx=4, pady=2)

        # Apply button.
        apply_frame = tk.Frame(bl_body)
        apply_frame.pack(fill=tk.X, padx=4, pady=(8, 4))
        self._apply_baseline_btn = tk.Button(
            apply_frame, text="Apply Baseline", font=("", 9, "bold"),
            bg="#003d7a", fg="white", activebackground="#0055aa",
            command=self._apply_baseline,
        )
        self._apply_baseline_btn.pack(fill=tk.X)

        # ── Normalisation section (CS-16, Phase 4e) ──────────────────────
        self._normalisation_section = CollapsibleSection(
            parent, title="Normalisation", expanded=False)
        self._normalisation_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        self._normalisation_panel = uvvis_normalise.NormalisationPanel(
            self._normalisation_section.body,
            self._graph,
            status_cb=self._set_status_message,
        )
        self._normalisation_panel.pack(fill=tk.X)

        # ── Smoothing section (CS-18, Phase 4g) ──────────────────────────
        self._smoothing_section = CollapsibleSection(
            parent, title="Smoothing", expanded=False)
        self._smoothing_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        self._smoothing_panel = uvvis_smoothing.SmoothingPanel(
            self._smoothing_section.body,
            self._graph,
            status_cb=self._set_status_message,
        )
        self._smoothing_panel.pack(fill=tk.X)

        # ── Peak picking section (CS-19, Phase 4h) ───────────────────────
        # PEAK_LIST nodes are intentionally absent from the shared
        # subject list (chained peak picking is undefined):
        # _spectrum_nodes only walks UVVIS / BASELINE / NORMALISED /
        # SMOOTHED, which is exactly the set the panel accepts as
        # parents.
        self._peak_picking_section = CollapsibleSection(
            parent, title="Peak picking", expanded=False)
        self._peak_picking_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        self._peak_picking_panel = uvvis_peak_picking.PeakPickingPanel(
            self._peak_picking_section.body,
            self._graph,
            status_cb=self._set_status_message,
        )
        self._peak_picking_panel.pack(fill=tk.X)

        # ── Second derivative section (CS-20, Phase 4i) ──────────────────
        # SECOND_DERIVATIVE nodes are NOT candidate parents for further
        # derivatives this phase: _spectrum_nodes excludes
        # SECOND_DERIVATIVE so the shared subject combobox cannot offer
        # one, and the panel's ACCEPTED_PARENT_TYPES rejects it as
        # defence in depth.
        self._second_derivative_section = CollapsibleSection(
            parent, title="Second derivative", expanded=False)
        self._second_derivative_section.pack(fill=tk.X, padx=0, pady=(2, 0))
        self._second_derivative_panel = (
            uvvis_second_derivative.SecondDerivativePanel(
                self._second_derivative_section.body,
                self._graph,
                status_cb=self._set_status_message,
            )
        )
        self._second_derivative_panel.pack(fill=tk.X)

        # Defer non-toolkit init until the chrome is present.
        self._refresh_baseline_param_rows()
        self._refresh_shared_subjects()

    def _set_status_message(self, text: str) -> None:
        """Status-bar callback handed to the NormalisationPanel.

        The tab owns the toolbar status label; subwidgets (the
        baseline section uses ``self._status_lbl.config`` inline,
        the NormalisationPanel uses this callback) update it through
        a single API so the formatting stays consistent.
        """
        if hasattr(self, "_status_lbl"):
            self._status_lbl.config(text=text, fg="#003d7a")

    def _refresh_baseline_param_rows(self) -> None:
        """Rebuild the parameter rows for the currently selected mode."""
        if not hasattr(self, "_baseline_params_frame"):
            return
        for child in self._baseline_params_frame.winfo_children():
            child.destroy()

        F9 = ("", 9)
        FC = ("Courier", 9)
        mode = self._baseline_mode.get()

        def _row(label_text: str) -> tk.Frame:
            row = tk.Frame(self._baseline_params_frame)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label_text, font=F9, width=15,
                     anchor="w").pack(side=tk.LEFT)
            return row

        if mode == "linear":
            for label, var in [
                ("Anchor lo (nm):", self._baseline_anchor_lo),
                ("Anchor hi (nm):", self._baseline_anchor_hi),
            ]:
                tk.Entry(_row(label), textvariable=var, width=10,
                         font=FC).pack(side=tk.LEFT)
        elif mode == "polynomial":
            tk.Spinbox(_row("Order n:"),
                       textvariable=self._baseline_poly_order,
                       from_=0, to=10, width=8, font=FC,
                       ).pack(side=tk.LEFT)
            for label, var in [
                ("Fit lo (nm):", self._baseline_fit_lo),
                ("Fit hi (nm):", self._baseline_fit_hi),
            ]:
                tk.Entry(_row(label), textvariable=var, width=10,
                         font=FC).pack(side=tk.LEFT)
        elif mode == "spline":
            tk.Label(self._baseline_params_frame,
                     text="Anchors (nm, comma-separated):",
                     font=F9, anchor="w").pack(fill=tk.X)
            tk.Entry(self._baseline_params_frame,
                     textvariable=self._baseline_spline_anchors,
                     font=FC).pack(fill=tk.X, pady=(0, 2))
        elif mode == "rubberband":
            tk.Label(self._baseline_params_frame,
                     text="(parameter-free convex hull)",
                     fg="gray", font=F9).pack(anchor="w", pady=(4, 0))
        elif mode == "scattering":
            # n entry + "Fit n" checkbox on the same row; checkbox
            # disables the entry so the user sees which way the fit
            # branch is pinned.
            n_row = _row("n:")
            n_entry = tk.Entry(n_row, textvariable=self._baseline_scattering_n,
                               width=8, font=FC)
            n_entry.pack(side=tk.LEFT)

            def _sync_n_entry_state(*_):
                n_entry.configure(
                    state=("disabled"
                           if self._baseline_scattering_fit_n.get()
                           else "normal"))

            tk.Checkbutton(
                n_row, text="Fit n",
                variable=self._baseline_scattering_fit_n,
                font=F9, command=_sync_n_entry_state,
            ).pack(side=tk.LEFT, padx=(8, 0))
            _sync_n_entry_state()
            for label, var in [
                ("Fit lo (nm):", self._baseline_scattering_fit_lo),
                ("Fit hi (nm):", self._baseline_scattering_fit_hi),
            ]:
                tk.Entry(_row(label), textvariable=var, width=10,
                         font=FC).pack(side=tk.LEFT)

    def _refresh_shared_subjects(self) -> None:
        """Repopulate the shared subject combobox from live spectrum nodes.

        Phase 4k (CS-22): a single combobox at the top of the left
        pane drives every operation panel + the inline baseline
        section. The host walks ``_spectrum_nodes`` (UVVIS / BASELINE
        / NORMALISED / SMOOTHED) — the same union-of-all-accepted-
        parents the per-panel comboboxes used to walk individually.
        Per-panel ``ACCEPTED_PARENT_TYPES`` then narrows the
        candidate set inside each Apply gate.
        """
        if not hasattr(self, "_shared_subject_cb"):
            return
        nodes = self._spectrum_nodes()
        self._shared_subject_map = {}
        items: List[str] = []
        for n in nodes:
            key = f"{n.label}  [{n.id[:6]}]"
            items.append(key)
            self._shared_subject_map[key] = n.id
        self._shared_subject_cb.configure(values=items)
        # Keep the user's selection if it still exists; otherwise
        # auto-pick the first available. The trace fans the change
        # out to every panel.
        if self._shared_subject.get() not in items:
            self._shared_subject.set(items[0] if items else "")
        else:
            # Selection text unchanged but the underlying node may
            # have moved (label edit, type change). Re-fan so the
            # gates re-evaluate with the up-to-date node.
            self._on_shared_subject_changed()

    def _resolve_shared_subject_id(self) -> Optional[str]:
        """Map the shared combobox display string back to a node id."""
        return self._shared_subject_map.get(self._shared_subject.get())

    def _on_shared_subject_changed(self) -> None:
        """Fan the shared subject change out to every panel + baseline.

        Called by the StringVar trace whenever the user picks a new
        subject (or ``_refresh_shared_subjects`` repopulates the
        list). Each panel's ``set_subject`` re-evaluates its Apply
        button state; the inline baseline section gets the same
        treatment via ``_refresh_baseline_apply_state``.
        """
        node_id = self._resolve_shared_subject_id()
        self._baseline_subject_id = node_id
        if hasattr(self, "_normalisation_panel"):
            self._normalisation_panel.set_subject(node_id)
        if hasattr(self, "_smoothing_panel"):
            self._smoothing_panel.set_subject(node_id)
        if hasattr(self, "_peak_picking_panel"):
            self._peak_picking_panel.set_subject(node_id)
        if hasattr(self, "_second_derivative_panel"):
            self._second_derivative_panel.set_subject(node_id)
        self._refresh_baseline_apply_state()

    def _refresh_baseline_apply_state(self) -> None:
        """Disable the inline baseline Apply button when the subject is invalid."""
        if not hasattr(self, "_apply_baseline_btn"):
            return
        ok = False
        if self._baseline_subject_id is not None:
            try:
                node = self._graph.get_node(self._baseline_subject_id)
            except KeyError:
                node = None
            if node is not None and node.type in self._BASELINE_ACCEPTED_PARENT_TYPES:
                ok = True
        self._apply_baseline_btn.configure(
            state=("normal" if ok else "disabled"))

    def _collect_baseline_params(self, mode: str) -> dict:
        """Read the left-panel widgets for ``mode`` into a params dict.

        Raises ``ValueError`` (with a user-readable message) on bad
        input. Per CS-03 the caller writes whatever this returns
        verbatim into the OperationNode's params dict.
        """
        if mode == "linear":
            try:
                lo = float(self._baseline_anchor_lo.get())
                hi = float(self._baseline_anchor_hi.get())
            except ValueError:
                raise ValueError("Both anchors must be numeric (nm).")
            return {"anchor_lo_nm": lo, "anchor_hi_nm": hi}
        if mode == "polynomial":
            try:
                order = int(self._baseline_poly_order.get())
                lo = float(self._baseline_fit_lo.get())
                hi = float(self._baseline_fit_hi.get())
            except (ValueError, tk.TclError):
                raise ValueError(
                    "Order must be int; fit window endpoints must be numeric.")
            return {"order": order, "fit_lo_nm": lo, "fit_hi_nm": hi}
        if mode == "spline":
            raw = self._baseline_spline_anchors.get().strip()
            if not raw:
                raise ValueError(
                    "Spline anchors required (≥2 wavelengths in nm, comma-separated).")
            try:
                anchors = [float(x.strip()) for x in raw.split(",") if x.strip()]
            except ValueError:
                raise ValueError("Anchors must be comma-separated numbers (nm).")
            if len(anchors) < 2:
                raise ValueError("Spline requires at least 2 anchors.")
            return {"anchors": anchors}
        if mode == "rubberband":
            return {}
        if mode == "scattering":
            try:
                lo = float(self._baseline_scattering_fit_lo.get())
                hi = float(self._baseline_scattering_fit_hi.get())
            except ValueError:
                raise ValueError(
                    "Fit window endpoints must be numeric (nm).")
            if self._baseline_scattering_fit_n.get():
                return {"n": "fit", "fit_lo_nm": lo, "fit_hi_nm": hi}
            try:
                n_val = float(self._baseline_scattering_n.get())
            except ValueError:
                raise ValueError(
                    "n must be numeric (or check 'Fit n' to fit it).")
            return {"n": n_val, "fit_lo_nm": lo, "fit_hi_nm": hi}
        raise ValueError(f"Unknown baseline mode: {mode!r}")

    def _apply_baseline(self) -> Optional[Tuple[str, str]]:
        """Materialise a provisional BASELINE op + node from the panel state.

        One Apply gesture = one new provisional ``BASELINE``
        OperationNode + one new provisional ``BASELINE`` DataNode,
        wired ``parent → op → child``. Returns ``(op_id, child_id)``
        on success or ``None`` if the user input was rejected.

        Phase 4k (CS-22): the parent is the *shared* subject selected
        by the top-of-pane combobox. ``_apply_baseline_btn`` is
        disabled when the shared selection isn't a UVVIS / BASELINE
        node, but the messagebox-bearing checks below still run as
        defence in depth.
        """
        subject_id = self._baseline_subject_id
        if not subject_id:
            messagebox.showinfo(
                "Apply Baseline",
                "Select a spectrum from the top of the left pane first.",
            )
            return None
        try:
            parent_node = self._graph.get_node(subject_id)
        except KeyError:
            messagebox.showerror(
                "Apply Baseline",
                "Selected spectrum is no longer in the project graph.",
            )
            return None
        if parent_node.type not in self._BASELINE_ACCEPTED_PARENT_TYPES:
            messagebox.showerror(
                "Apply Baseline",
                "Selected node is not a valid parent for baseline correction.",
            )
            return None

        mode = self._baseline_mode.get()
        try:
            params = self._collect_baseline_params(mode)
        except ValueError as exc:
            messagebox.showerror("Baseline parameters", str(exc))
            return None

        wl = parent_node.arrays["wavelength_nm"]
        absorb = parent_node.arrays["absorbance"]
        try:
            corrected = uvvis_baseline.compute(mode, wl, absorb, params)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Baseline computation", str(exc))
            return None

        op_id = uuid.uuid4().hex
        out_id = uuid.uuid4().hex

        # CS-03: capture the full parameter snapshot. ``mode`` is the
        # discriminator; the remaining keys are the mode-specific
        # sub-schema documented in CS-15.
        op_params = {"mode": mode, **params}
        op_node = OperationNode(
            id=op_id,
            type=OperationType.BASELINE,
            engine="internal",
            engine_version=PTARMIGAN_VERSION,
            params=op_params,
            input_ids=[subject_id],
            output_ids=[out_id],
            status="SUCCESS",
            state=NodeState.PROVISIONAL,
        )

        # Default colour for the new BASELINE node — pick a fresh
        # palette entry so the corrected curve is visually separable
        # from its parent. CS-21 (Phase 4j) replaced the inline
        # palette-index expression with the shared pick_default_color
        # helper.
        colour = pick_default_color(self._graph)

        # Carry the parent's metadata forward, plus a baseline footer.
        new_meta: dict = {
            **parent_node.metadata,
            "baseline_mode":      mode,
            "baseline_parent_id": subject_id,
        }

        data_node = DataNode(
            id=out_id,
            type=NodeType.BASELINE,
            arrays={
                "wavelength_nm": np.asarray(wl, dtype=float),
                "absorbance":    np.asarray(corrected, dtype=float),
            },
            metadata=new_meta,
            label=f"{parent_node.label} · baseline ({mode})",
            state=NodeState.PROVISIONAL,
            style=default_spectrum_style(colour),
        )

        # Insert op + data, then wire parent → op → child.
        self._graph.add_node(op_node)
        self._graph.add_node(data_node)
        self._graph.add_edge(subject_id, op_id)
        self._graph.add_edge(op_id, out_id)

        self._status_lbl.config(
            text=f"Baseline ({mode}) applied to {parent_node.label} "
                 f"(provisional — commit / discard via the right sidebar).",
            fg="#003d7a",
        )
        return op_id, out_id

    # ── Plot panel ────────────────────────────────────────────────────────────

    def _build_plot(self, parent):
        self._fig = Figure(figsize=(7, 4.5), dpi=100)
        self._ax  = self._fig.add_subplot(111)

        self._canvas = FigureCanvasTkAgg(self._fig, master=parent)
        self._canvas.get_tk_widget().pack(
            side=tk.TOP, fill=tk.BOTH, expand=True)

        toolbar_frame = tk.Frame(parent)
        toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self._toolbar = NavigationToolbar2Tk(self._canvas, toolbar_frame)
        self._toolbar.update()

        self._canvas.mpl_connect("button_release_event", self._on_mpl_interact)
        self._canvas.mpl_connect("scroll_event",         self._on_mpl_interact)

        self._draw_empty()

    # ══════════════════════════════════════════════════════════════════════════
    #  Graph event subscription
    # ══════════════════════════════════════════════════════════════════════════

    def _on_graph_event(self, event: GraphEvent) -> None:
        """Drive plot redraws from graph mutations.

        Per CS-05 the unified style dialog never calls a redraw
        callback; the tab is the single subscriber that owns plot
        updates. ScanTreeWidget rebuilds its own rows; here we just
        repaint the figure. Any UVVIS-touching event re-renders.
        """
        et = event.type
        if et in (
            GraphEventType.NODE_ADDED,
            GraphEventType.NODE_DISCARDED,
            GraphEventType.NODE_ACTIVE_CHANGED,
            GraphEventType.NODE_STYLE_CHANGED,
            GraphEventType.NODE_LABEL_CHANGED,
            GraphEventType.GRAPH_LOADED,
            GraphEventType.GRAPH_CLEARED,
        ):
            self._redraw()
        # The shared subject combobox (CS-22, Phase 4k) tracks which
        # UVVIS / BASELINE / NORMALISED / SMOOTHED nodes exist;
        # refresh on the structural / label / active events that can
        # change that set. The trace on _shared_subject then fans the
        # selection out to every panel + the inline baseline gate.
        if et in (
            GraphEventType.NODE_ADDED,
            GraphEventType.NODE_DISCARDED,
            GraphEventType.NODE_ACTIVE_CHANGED,
            GraphEventType.NODE_LABEL_CHANGED,
            GraphEventType.GRAPH_LOADED,
            GraphEventType.GRAPH_CLEARED,
        ):
            self._refresh_shared_subjects()

    def _on_destroy_unsubscribe(self, _event) -> None:
        try:
            self._graph.unsubscribe(self._on_graph_event)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Style dialog hand-off (CS-05)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Export hand-off (CS-17, Phase 4f) ─────────────────────────────────────

    _EXPORT_FILETYPES: tuple = (
        ("CSV (comma-separated)", "*.csv"),
        ("TXT (tab-separated)",   "*.txt"),
    )

    @staticmethod
    def _sanitise_basename(label: str) -> str:
        """Sanitise a node label for use as a default filename basename.

        Strips characters that Windows / macOS / Linux file systems
        reject and collapses runs of whitespace to a single underscore.
        Empty results fall back to ``"export"``.
        """
        bad = '<>:"/\\|?*'
        cleaned = "".join(
            "_" if (ch in bad or ch.isspace()) else ch for ch in label
        )
        cleaned = cleaned.strip("._")
        return cleaned or "export"

    def _on_export_node(self, node_id: str) -> None:
        """Row Export… hand-off: ask for a path then write the file.

        Opens an ``asksaveasfilename`` dialog filtered to ``.csv`` /
        ``.txt``, defaults the basename to the node's sanitised label,
        and delegates to ``node_export.export_node_to_file``. Success
        nudges the status bar; failure surfaces via ``messagebox``.

        The widget gates the gesture on committed state, so this
        method can assume a valid committed-and-exportable id, but
        ``node_export`` raises ``ValueError`` on a stale type and we
        still surface that defensively.
        """
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return

        default_name = self._sanitise_basename(getattr(node, "label", ""))
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export spectrum",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=list(self._EXPORT_FILETYPES),
        )
        if not path:
            return

        try:
            node_export.export_node_to_file(self._graph, node_id, path)
        except (ValueError, KeyError, OSError) as exc:
            messagebox.showerror(
                "Export failed",
                f"Could not export {node_id!r}:\n{exc}",
                parent=self,
            )
            return
        self._set_status_message(f"Exported to {path}")

    def _open_style_dialog_for_node(self, node_id: str) -> None:
        """Gear-button hand-off: open the unified ``StyleDialog`` (CS-05).

        ``open_style_dialog`` enforces one-dialog-per-node. The
        ``on_apply_to_all`` callback fans the value out to every node
        currently rendered in the sidebar — UVVIS and BASELINE alike
        (Phase 4d: B-002 widened the scope so ``visible`` /
        ``in_legend`` toggles propagate across both row types, since
        both share the sidebar and every other row control).
        """
        open_style_dialog(
            self, self._graph, node_id,
            on_apply_to_all=self._on_uvvis_apply_to_all,
        )

    def _on_uvvis_apply_to_all(self, param: str, value) -> None:
        """∀ fan-out: write ``param=value`` onto every visible spectrum node.

        Scope is ``_spectrum_nodes`` (UVVIS + BASELINE), not the
        UVVIS-only ``_uvvis_nodes``. Phase 4d widened this so the
        new ``visible`` / ``in_legend`` controls (B-002) cover the
        whole sidebar — but the widening applies to every key, since
        the user invoking ∀ on, say, a linewidth in a sidebar mixing
        UVVIS and BASELINE rows expects every visible row to take
        the value. ``set_style`` is a merge per CS-01, so keys other
        than ``param`` on each target node are preserved.

        BASELINE rows lack a baseline-specific style schema today;
        they share the universal style keys with UVVIS, so the merge
        is well-defined. Should a future BASELINE-specific key land
        (e.g., a baseline-fit colour distinct from the spectrum
        colour) the fan-out scope can be revisited.
        """
        for node in self._spectrum_nodes():
            self._graph.set_style(node.id, {param: value})

    # ══════════════════════════════════════════════════════════════════════════
    #  Plot Settings dialog hand-off (CS-06)
    # ══════════════════════════════════════════════════════════════════════════

    def _open_plot_settings(self) -> None:
        """⚙ button hand-off: open the unified Plot Settings dialog.

        The factory enforces one-dialog-per-tab. The dialog mutates
        ``self._plot_config`` in place on Apply, then invokes
        ``on_apply`` so the tab repaints.
        """
        plot_settings_dialog.open_plot_settings_dialog(
            self, self._plot_config,
            on_apply=self._on_plot_config_changed,
        )

    def _on_plot_config_changed(self) -> None:
        """Apply / Cancel callback from the Plot Settings dialog.

        The dialog has already mutated ``self._plot_config`` in place;
        the tab just needs to repaint. Plot Settings is tab-private
        UI state, so it does not flow through the graph subscription.
        """
        self._redraw()

    # ══════════════════════════════════════════════════════════════════════════
    #  File loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_files(self):
        paths = filedialog.askopenfilenames(
            title="Open UV/Vis file(s)", filetypes=_FILE_TYPES)
        if not paths:
            return

        n_loaded = 0
        for path in paths:
            try:
                for scan in parse_uvvis_file(path):
                    if self._has_existing_load(scan.source_file, scan.label):
                        continue
                    self._load_uvvis_scan(path, scan)
                    n_loaded += 1
            except Exception as exc:
                messagebox.showerror(
                    "Load error",
                    f"Could not read {os.path.basename(path)}:\n{exc}")

        if n_loaded:
            # Plot redraw fires automatically through the graph
            # subscription on each NODE_ADDED. Status label is a UI
            # detail outside the graph, so update it here directly.
            total = len(self._uvvis_nodes())
            self._status_lbl.config(
                text=f"{total} spectrum/spectra loaded.",
                fg="#003300")

    def _load_uvvis_scan(self, path: str, scan: UVVisScan) -> tuple[str, str, str]:
        """Materialise a parsed UVVisScan as RAW_FILE + LOAD + UVVIS in the graph.

        Implements the §5.3 + CS-13 load-time rule: a file load creates
        a COMMITTED RAW_FILE node (the immutable provenance anchor),
        a COMMITTED LOAD OperationNode, and a COMMITTED UVVIS DataNode
        carrying the parsed arrays. No analysis runs automatically.

        Returns ``(raw_id, op_id, uvvis_id)``.
        """
        raw_id   = uuid.uuid4().hex
        op_id    = uuid.uuid4().hex
        uvvis_id = uuid.uuid4().hex

        ext = os.path.splitext(path)[1].lower().lstrip(".") or "unknown"
        instrument = scan.metadata.get("instrument", "generic")

        # 1. RAW_FILE node — the immutable anchor (CS-02 conventions).
        raw_node = DataNode(
            id=raw_id,
            type=NodeType.RAW_FILE,
            arrays={},
            metadata={
                "original_path": str(path),
                "file_format":   ext,
                # sha256 / copied_to are written when the project is
                # saved into a .ptproj/ via project_io.copy_raw_file.
            },
            label=os.path.basename(path),
            state=NodeState.COMMITTED,
        )

        # 2. LOAD operation — engine="internal", parameters sufficient
        #    to re-run the load (CS-03 params completeness).
        op_node = OperationNode(
            id=op_id,
            type=OperationType.LOAD,
            engine="internal",
            engine_version=PTARMIGAN_VERSION,
            params={
                "file_format": ext,
                "instrument":  instrument,
                "parser":      "uvvis_parser.parse_uvvis_file",
            },
            input_ids=[raw_id],
            output_ids=[uvvis_id],
            status="SUCCESS",
            state=NodeState.COMMITTED,
        )

        # 3. UVVIS DataNode — parsed arrays + style with default colour.
        # CS-21 (Phase 4j) routes default-colour selection through
        # node_styles.pick_default_color so the loader walks the same
        # six-NodeType counter as the operation panels.
        colour = pick_default_color(self._graph)

        uvvis_meta = {
            "x_unit":      "nm",
            "y_unit":      "absorbance",
            "instrument":  instrument,
            "source_file": scan.source_file,
        }
        # Carry parser-supplied metadata under a namespaced key so it
        # doesn't collide with CS-02 conventions.
        if scan.metadata:
            uvvis_meta["parser_metadata"] = dict(scan.metadata)

        uvvis_node = DataNode(
            id=uvvis_id,
            type=NodeType.UVVIS,
            arrays={
                "wavelength_nm": np.asarray(scan.wavelength_nm, dtype=float),
                "absorbance":    np.asarray(scan.absorbance, dtype=float),
            },
            metadata=uvvis_meta,
            label=scan.display_name(),
            state=NodeState.COMMITTED,
            style=default_spectrum_style(colour),
        )

        self._graph.add_node(raw_node)
        self._graph.add_node(op_node)
        self._graph.add_node(uvvis_node)
        self._graph.add_edge(raw_id, op_id)
        self._graph.add_edge(op_id, uvvis_id)
        return raw_id, op_id, uvvis_id

    # ══════════════════════════════════════════════════════════════════════════
    #  Axis helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _parse_lim(self, var: tk.StringVar) -> Optional[float]:
        try:
            return float(var.get().strip())
        except ValueError:
            return None

    def _auto_x(self):
        self._xlim_lo.set(""); self._xlim_hi.set(""); self._redraw()

    def _auto_y(self):
        self._ylim_lo.set(""); self._ylim_hi.set(""); self._redraw()

    def _on_mpl_interact(self, event):
        if event.name == "button_release_event" and event.button != 1:
            return
        try:
            x0, x1 = self._ax.get_xlim()
            y0, y1 = self._ax.get_ylim()
            self._xlim_lo.set(f"{min(x0, x1):.4g}")
            self._xlim_hi.set(f"{max(x0, x1):.4g}")
            self._ylim_lo.set(f"{min(y0, y1):.4g}")
            self._ylim_hi.set(f"{max(y0, y1):.4g}")
        except Exception:
            pass

    def _on_unit_change(self):
        new_unit  = self._x_unit.get()
        prev_unit = self._x_unit_prev
        if new_unit != prev_unit:
            lo = self._parse_lim(self._xlim_lo)
            hi = self._parse_lim(self._xlim_hi)
            if lo is not None and hi is not None:
                new_lo, new_hi = _convert_xlim(lo, hi, prev_unit, new_unit)
                self._xlim_lo.set(f"{new_lo:.4g}")
                self._xlim_hi.set(f"{new_hi:.4g}")
            self._x_unit_prev = new_unit
        self._redraw()

    # ══════════════════════════════════════════════════════════════════════════
    #  Plotting (graph-driven)
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_empty(self):
        self._ax.cla()
        self._ax.set_facecolor("#f8f8f8")
        self._ax.text(0.5, 0.5, "Load a UV/Vis file to begin",
                      ha="center", va="center",
                      transform=self._ax.transAxes,
                      color="gray", fontsize=11)
        self._ax.set_axis_off()
        self._canvas.draw_idle()

    def _redraw(self, *_args, **_kwargs):
        # Accept ``focus=node_id`` from ScanTreeWidget history-click
        # gestures (CS-04). Phase 4a does not yet implement preview
        # rendering for ancestor nodes, so the kwarg is currently
        # ignored; the call is honoured as a regular full redraw.
        # Walk the ProjectGraph for live UVVIS / BASELINE / NORMALISED
        # nodes whose style has them visible; fall back to the
        # empty-state placeholder when nothing is loaded or every
        # loaded node is hidden. All three render identically — they
        # share the ``arrays["wavelength_nm"]`` /
        # ``arrays["absorbance"]`` convention. Phase 4e retired
        # ``_y_with_norm``: normalisation is now an explicit operation
        # that creates a NORMALISED node with the normalised values
        # baked into ``arrays["absorbance"]``, not a draw-time
        # transform on the displayed y-values.
        live = [n for n in self._spectrum_nodes()
                if bool(n.style.get("visible", True))]
        # SECOND_DERIVATIVE nodes (CS-20, Phase 4i) ride the same
        # curve render path as the spectrum-shaped nodes — they carry
        # the wavelength_nm / absorbance schema, so the loop below
        # treats them identically. They are kept out of
        # ``_spectrum_nodes`` so the locked smoothing / baseline /
        # normalise / peak-picking panels do not surface them as
        # candidate parents (those panels would silently refuse them).
        live.extend(n for n in self._second_derivative_nodes()
                    if bool(n.style.get("visible", True)))

        if not live:
            self._draw_empty()
            return

        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        ax   = self._ax
        unit = self._x_unit.get()
        cfg  = self._plot_config

        # Background colour (Plot Settings → Appearance).
        ax.set_facecolor(cfg.get("background_color", "#ffffff"))

        for node in live:
            style  = node.style
            colour = style.get("color", "#333333")
            wl     = node.arrays["wavelength_nm"]
            absorb = node.arrays["absorbance"]
            x = _wavelength_to_x(wl, unit)
            y = _absorbance_to_y(absorb, self._y_unit.get())
            order  = np.argsort(x)
            x, y   = x[order], y[order]
            label  = node.label if style.get("in_legend", True) else None
            ax.plot(x, y,
                    color=colour,
                    linestyle=style.get("linestyle", "solid"),
                    linewidth=style.get("linewidth", 1.5),
                    alpha=style.get("alpha", 0.9),
                    label=label)
            if style.get("fill", False):
                ax.fill_between(x, 0, y,
                                color=colour,
                                alpha=style.get("fill_alpha", 0.08))

        # ── Peak list overlays (CS-19, Phase 4h) ──────────────────────
        # Render every visible PEAK_LIST node as a scatter on top of
        # the curves above. The peak_list arrays carry samples lifted
        # from the parent's wavelength grid, so the unit / Y-unit
        # conversions are the same ones the curves go through.
        # ``style["linestyle"]`` / ``linewidth`` / ``fill`` are
        # universal style keys but have no scatter analogue; the
        # renderer reads ``color`` / ``alpha`` / ``visible`` /
        # ``in_legend`` and ignores the rest. Marker is fixed at "v"
        # (downward triangle pointing at the peak); a future
        # marker-style schema decision (CS-19 implementation note)
        # could expose this to the user.
        for peak_node in self._peak_list_nodes():
            pstyle = peak_node.style
            if not pstyle.get("visible", True):
                continue
            pwl = peak_node.arrays["peak_wavelengths_nm"]
            pa = peak_node.arrays["peak_absorbances"]
            if pwl.size == 0:
                continue
            px = _wavelength_to_x(np.asarray(pwl, dtype=float), unit)
            py = _absorbance_to_y(np.asarray(pa, dtype=float),
                                  self._y_unit.get())
            plabel = (peak_node.label
                      if pstyle.get("in_legend", True) else None)
            ax.scatter(
                px, py,
                color=pstyle.get("color", "#333333"),
                alpha=pstyle.get("alpha", 0.9),
                marker="v", s=40, edgecolor="none",
                label=plabel, zorder=3,
            )

        # ── Axis labels (Plot Settings → Title and labels / Fonts) ───────────
        # ``mode = "auto"`` uses the unit-derived default; ``"custom"``
        # uses the user-supplied text; ``"none"`` (X/Y label rows do not
        # offer None — entry just goes empty if user clears it).
        auto_xlabels = {"nm":   "Wavelength (nm)",
                        "cm-1": "Wavenumber (cm⁻¹)",
                        "eV":   "Energy (eV)"}
        auto_ylabels = {"A": "Absorbance", "%T": "Transmittance (%)"}

        xlabel_mode = cfg.get("xlabel_mode", "auto")
        xlabel_text = (auto_xlabels.get(unit, unit)
                       if xlabel_mode == "auto"
                       else cfg.get("xlabel_text", ""))
        ax.set_xlabel(
            xlabel_text,
            fontsize=cfg.get("xlabel_font_size", 10),
            fontweight=("bold" if cfg.get("xlabel_font_bold", True) else "normal"),
        )

        ylabel_mode = cfg.get("ylabel_mode", "auto")
        ylabel_text = (auto_ylabels.get(self._y_unit.get(), "")
                       if ylabel_mode == "auto"
                       else cfg.get("ylabel_text", ""))
        ax.set_ylabel(
            ylabel_text,
            fontsize=cfg.get("ylabel_font_size", 10),
            fontweight=("bold" if cfg.get("ylabel_font_bold", True) else "normal"),
        )

        # Title: "auto" has no UV/Vis-derivable default so it falls
        # through as no title; "custom" uses the user-entered text;
        # "none" (default factory value) suppresses the title entirely.
        title_mode = cfg.get("title_mode", "none")
        if title_mode == "custom":
            ax.set_title(
                cfg.get("title_text", ""),
                fontsize=cfg.get("title_font_size", 12),
                fontweight=("bold" if cfg.get("title_font_bold", True) else "normal"),
            )

        # Tick direction + tick label size.
        ax.tick_params(
            direction=cfg.get("tick_direction", "out"),
            labelsize=cfg.get("tick_label_font_size", 9),
        )

        # ── Secondary λ(nm) axis ──────────────────────────────────────────────
        if unit == "cm-1" and self._show_nm_axis.get():
            def _fwd(x):
                with np.errstate(divide="ignore", invalid="ignore"):
                    return np.where(np.asarray(x, float) > 0,
                                    1e7 / np.asarray(x, float), 0.0)
            sec = ax.secondary_xaxis("top", functions=(_fwd, _fwd))
            sec.set_xlabel("λ (nm)", fontsize=9)
            sec.tick_params(axis="x", direction="in", labelsize=8)

        # ── Invert nm axis ────────────────────────────────────────────────────
        if unit == "nm":
            lo_nm = min(float(np.min(n.arrays["wavelength_nm"])) for n in live)
            hi_nm = max(float(np.max(n.arrays["wavelength_nm"])) for n in live)
            ax.set_xlim(hi_nm, lo_nm)

        # ── Apply stored x-limits ─────────────────────────────────────────────
        lo_x = self._parse_lim(self._xlim_lo)
        hi_x = self._parse_lim(self._xlim_hi)
        if lo_x is not None or hi_x is not None:
            cur = ax.get_xlim()
            if unit == "nm":
                ax.set_xlim(hi_x if hi_x is not None else cur[0],
                            lo_x if lo_x is not None else cur[1])
            else:
                ax.set_xlim(lo_x if lo_x is not None else cur[0],
                            hi_x if hi_x is not None else cur[1])

        # ── Apply stored y-limits ─────────────────────────────────────────────
        lo_y = self._parse_lim(self._ylim_lo)
        hi_y = self._parse_lim(self._ylim_hi)
        if lo_y is not None or hi_y is not None:
            cur = ax.get_ylim()
            ax.set_ylim(lo_y if lo_y is not None else cur[0],
                        hi_y if hi_y is not None else cur[1])

        # ── Legend (Plot Settings → Legend) ──────────────────────────────────
        handles, labels = ax.get_legend_handles_labels()
        if handles and cfg.get("legend_show", True):
            ax.legend(
                fontsize=cfg.get("legend_font_size", 8),
                loc=cfg.get("legend_position", "best"),
                framealpha=0.7,
            )

        # ── Grid (Plot Settings → Appearance) ───────────────────────────────
        if cfg.get("grid", True):
            ax.grid(True, linestyle=":", alpha=0.4)
        else:
            ax.grid(False)

        self._fig.tight_layout()
        self._canvas.draw_idle()
        self._toolbar.update()

    # ══════════════════════════════════════════════════════════════════════════
    #  Push to TDDFT overlay
    # ══════════════════════════════════════════════════════════════════════════

    def _send_node_to_compare(self, node_id: str) -> None:
        """Push a single node's spectrum into the TDDFT overlay.

        Phase 4n CS-27. Wired as ``send_to_compare_cb`` on the
        ScanTreeWidget so the per-row → icon dispatches to this
        method. The widget's disabled-state already gates on
        ``state == COMMITTED`` and on the callback being wired; this
        handler additionally surfaces the "no Compare host connected"
        case to the user via a messagebox so the affordance still
        feels live when the integration isn't available.
        """
        if self._add_scan_fn is None:
            messagebox.showinfo("Not available",
                                "No TDDFT plot connected to this panel.")
            return
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return
        if not isinstance(node, DataNode) or node.type != NodeType.UVVIS:
            return

        wl     = np.asarray(node.arrays["wavelength_nm"], dtype=float)
        absorb = np.asarray(node.arrays["absorbance"], dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            energy_ev = np.where(wl > 0, _HC_NM_EV / wl, 0.0)
        order     = np.argsort(energy_ev)
        energy_ev = energy_ev[order]
        absorb    = absorb[order]
        mask      = energy_ev > 0
        parser_md = node.metadata.get("parser_metadata", {})
        exp_scan  = ExperimentalScan(
            label=node.label,
            source_file=node.metadata.get("source_file", ""),
            energy_ev=energy_ev[mask],
            mu=absorb[mask],
            is_normalized=True,
            scan_type="UV/Vis absorbance",
            metadata=dict(
                parser_md,
                uvvis_source=node.metadata.get("source_file", ""),
            ),
        )
        self._add_scan_fn(exp_scan)

        self._status_lbl.config(
            text=f"Sent {node.label!r} to TDDFT overlay.",
            fg="#003d7a")
