"""
uvvis_tab.py — UV/Vis/NIR analysis tab for Ptarmigan
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from uvvis_parser import UVVisScan, parse_uvvis_file
from experimental_parser import ExperimentalScan

# ── Colour palette ────────────────────────────────────────────────────────────
_PALETTE = [
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

# ── File-type filter for open dialog ─────────────────────────────────────────
_FILE_TYPES = [
    ("UV/Vis files",
     "*.csv *.tsv *.txt *.prn *.dpt *.sp *.asc *.dat *.olis *.olisdat"),
    ("CSV / text",  "*.csv *.tsv *.txt *.prn"),
    ("OLIS",        "*.olis *.olisdat *.dat *.asc"),
    ("All files",   "*.*"),
]

# ── Unit conversion helpers ───────────────────────────────────────────────────
_NM_TO_CM1  = 1e7          # ν(cm⁻¹) = 1e7 / λ(nm)  (self-inverse)
_HC_NM_EV   = 1239.84193   # E(eV) = 1239.84 / λ(nm)

def _nm_to(unit: str, nm_val: float) -> float:
    """Convert a wavelength value in nm to the target unit."""
    if nm_val <= 0:
        return nm_val
    if unit == "nm":
        return nm_val
    if unit == "cm-1":
        return _NM_TO_CM1 / nm_val
    if unit == "eV":
        return _HC_NM_EV / nm_val
    return nm_val

def _to_nm(unit: str, val: float) -> float:
    """Convert a value in `unit` back to nm."""
    if val <= 0:
        return val
    if unit == "nm":
        return val
    if unit == "cm-1":
        return _NM_TO_CM1 / val
    if unit == "eV":
        return _HC_NM_EV / val
    return val

def _convert_xlim(lo: float, hi: float,
                  from_unit: str, to_unit: str) -> Tuple[float, float]:
    """Convert an x-axis limit pair between units.

    Because nm↔cm⁻¹ is order-reversing (larger nm = smaller cm⁻¹),
    the lo/hi are swapped and re-sorted so the result is always (min, max).
    """
    a = _nm_to(to_unit, _to_nm(from_unit, lo))
    b = _nm_to(to_unit, _to_nm(from_unit, hi))
    return (min(a, b), max(a, b))


class UVVisTab(tk.Frame):
    """UV/Vis/NIR import, display and analysis panel.

    Parameters
    ----------
    parent       : Tk parent widget
    add_scan_fn  : optional callable(ExperimentalScan) — called when the user
                   clicks '+ Add to TDDFT Overlay'.  The scan is converted to
                   energy (eV) so it fits naturally on the main TDDFT plot.
    """

    def __init__(self, parent, add_scan_fn: Optional[Callable] = None):
        super().__init__(parent)
        self._add_scan_fn: Optional[Callable] = add_scan_fn

        # ── Scan state ────────────────────────────────────────────────────────
        self._scans:    List[UVVisScan] = []
        self._vis_vars: Dict[str, tk.BooleanVar] = {}   # label → visible
        self._colours:  Dict[str, str]            = {}   # label → hex

        # ── Display options ───────────────────────────────────────────────────
        self._x_unit       = tk.StringVar(value="nm")    # "nm"|"cm-1"|"eV"
        self._x_unit_prev  = "nm"                        # for limit conversion
        self._y_unit       = tk.StringVar(value="A")     # "A"|"%T"
        self._show_nm_axis = tk.BooleanVar(value=True)   # secondary λ axis
        self._norm_mode    = tk.StringVar(value="none")  # "none"|"peak"|"area"

        # ── Axis limits — None means auto-scale ───────────────────────────────
        # Stored in whatever unit is currently selected.
        # StringVars drive the entry widgets; None sentinel → auto.
        self._xlim_lo = tk.StringVar(value="")
        self._xlim_hi = tk.StringVar(value="")
        self._ylim_lo = tk.StringVar(value="")
        self._ylim_hi = tk.StringVar(value="")

        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    #  Layout
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Top toolbar ───────────────────────────────────────────────────────
        top = tk.Frame(self, bd=1, relief=tk.GROOVE, padx=4, pady=3)
        top.pack(side=tk.TOP, fill=tk.X)
        self._build_toolbar(top)

        # ── Axis-limit bar ────────────────────────────────────────────────────
        lim_bar = tk.Frame(self, bd=1, relief=tk.GROOVE, padx=4, pady=2)
        lim_bar.pack(side=tk.TOP, fill=tk.X)
        self._build_limit_bar(lim_bar)

        # ── Body: scan list (left) + plot (right) ─────────────────────────────
        body = tk.PanedWindow(self, orient=tk.HORIZONTAL,
                              sashwidth=5, sashrelief=tk.RAISED)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left = tk.Frame(body, width=220, bd=1, relief=tk.SUNKEN)
        body.add(left, minsize=180)
        self._build_scan_list(left)

        right = tk.Frame(body)
        body.add(right, minsize=400)
        self._build_plot(right)

    def _build_toolbar(self, bar):
        F9 = ("", 9)

        tk.Button(bar, text="📂 Load File…", font=("", 9, "bold"),
                  bg="#003d7a", fg="white", activebackground="#0055aa",
                  command=self._load_files).pack(side=tk.LEFT, padx=(2, 6))

        def _sep():
            ttk.Separator(bar, orient=tk.VERTICAL).pack(
                side=tk.LEFT, fill=tk.Y, padx=6)

        _sep()

        # X-axis unit — triggers limit conversion
        tk.Label(bar, text="X:", font=F9).pack(side=tk.LEFT)
        for label, val in [("nm", "nm"), ("cm⁻¹", "cm-1"), ("eV", "eV")]:
            tk.Radiobutton(bar, text=label, variable=self._x_unit, value=val,
                           command=self._on_unit_change, font=F9,
                           ).pack(side=tk.LEFT)

        _sep()

        # Y-axis unit
        tk.Label(bar, text="Y:", font=F9).pack(side=tk.LEFT)
        for label, val in [("Absorbance", "A"), ("%T", "%T")]:
            tk.Radiobutton(bar, text=label, variable=self._y_unit, value=val,
                           command=self._redraw, font=F9,
                           ).pack(side=tk.LEFT)

        _sep()

        # Normalisation
        tk.Label(bar, text="Norm:", font=F9).pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self._norm_mode,
                     values=["none", "peak", "area"],
                     state="readonly", width=6, font=F9,
                     ).pack(side=tk.LEFT, padx=2)
        self._norm_mode.trace_add("write", lambda *_: self._redraw())

        _sep()

        # Secondary nm axis (shown only in cm⁻¹ mode)
        self._nm_cb = tk.Checkbutton(bar, text="λ(nm) axis",
                                     variable=self._show_nm_axis,
                                     command=self._redraw, font=F9)
        self._nm_cb.pack(side=tk.LEFT, padx=2)

        _sep()

        tk.Button(bar, text="+ Add to TDDFT Overlay",
                  font=("", 9, "bold"), bg="#4a0070", fg="white",
                  activebackground="#6a0090",
                  command=self._add_selected_to_overlay,
                  ).pack(side=tk.LEFT, padx=2)

        self._status_lbl = tk.Label(bar, text="Load a UV/Vis file to begin.",
                                    fg="gray", font=("", 8))
        self._status_lbl.pack(side=tk.LEFT, padx=10)

    def _build_limit_bar(self, bar):
        F9 = ("", 9)
        FC = ("Courier", 9)

        def _entry(var, width=8):
            e = tk.Entry(bar, textvariable=var, width=width, font=FC)
            e.bind("<Return>",   lambda _e: self._redraw())
            e.bind("<FocusOut>", lambda _e: self._redraw())
            return e

        def _sep():
            ttk.Separator(bar, orient=tk.VERTICAL).pack(
                side=tk.LEFT, fill=tk.Y, padx=8)

        # X limits
        tk.Label(bar, text="X:", font=F9).pack(side=tk.LEFT)
        _entry(self._xlim_lo).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(bar, text="→", font=F9).pack(side=tk.LEFT, padx=1)
        _entry(self._xlim_hi).pack(side=tk.LEFT)
        tk.Button(bar, text="Auto X", font=("", 8),
                  command=self._auto_x).pack(side=tk.LEFT, padx=(4, 0))

        _sep()

        # Y limits
        tk.Label(bar, text="Y:", font=F9).pack(side=tk.LEFT)
        _entry(self._ylim_lo).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(bar, text="→", font=F9).pack(side=tk.LEFT, padx=1)
        _entry(self._ylim_hi).pack(side=tk.LEFT)
        tk.Button(bar, text="Auto Y", font=("", 8),
                  command=self._auto_y).pack(side=tk.LEFT, padx=(4, 0))

    def _build_scan_list(self, parent):
        tk.Label(parent, text="Loaded Spectra",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        btn_row = tk.Frame(parent)
        btn_row.pack(fill=tk.X, padx=4, pady=(0, 4))
        tk.Button(btn_row, text="All",  font=("", 8),
                  command=lambda: self._set_all_vis(True)
                  ).pack(side=tk.LEFT, padx=(0, 2))
        tk.Button(btn_row, text="None", font=("", 8),
                  command=lambda: self._set_all_vis(False)
                  ).pack(side=tk.LEFT)

        cnv_frame = tk.Frame(parent)
        cnv_frame.pack(fill=tk.BOTH, expand=True, padx=2)

        self._list_canvas = tk.Canvas(cnv_frame, bd=0, highlightthickness=0)
        sb = ttk.Scrollbar(cnv_frame, orient=tk.VERTICAL,
                           command=self._list_canvas.yview)
        self._list_inner = tk.Frame(self._list_canvas)
        self._list_inner.bind(
            "<Configure>",
            lambda e: self._list_canvas.configure(
                scrollregion=self._list_canvas.bbox("all")))
        self._list_win = self._list_canvas.create_window(
            (0, 0), window=self._list_inner, anchor="nw")
        self._list_canvas.bind(
            "<Configure>",
            lambda e: self._list_canvas.itemconfig(self._list_win, width=e.width))
        self._list_canvas.configure(yscrollcommand=sb.set)
        self._list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

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

        # Capture manual pan/zoom from the matplotlib toolbar so we honour it
        self._canvas.mpl_connect("button_release_event", self._on_mpl_interact)
        self._canvas.mpl_connect("scroll_event",         self._on_mpl_interact)

        self._draw_empty()

    # ══════════════════════════════════════════════════════════════════════════
    #  Axis limit helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _parse_lim(self, var: tk.StringVar) -> Optional[float]:
        try:
            return float(var.get().strip())
        except ValueError:
            return None

    def _auto_x(self):
        self._xlim_lo.set("")
        self._xlim_hi.set("")
        self._redraw()

    def _auto_y(self):
        self._ylim_lo.set("")
        self._ylim_hi.set("")
        self._redraw()

    def _on_mpl_interact(self, event):
        """After a matplotlib pan/zoom, capture the new axis limits into
        the entry widgets so they become 'sticky'."""
        if event.name == "button_release_event" and event.button != 1:
            return
        try:
            x0, x1 = self._ax.get_xlim()
            y0, y1 = self._ax.get_ylim()
            # Normalise so lo < hi in the entry fields
            self._xlim_lo.set(f"{min(x0, x1):.4g}")
            self._xlim_hi.set(f"{max(x0, x1):.4g}")
            self._ylim_lo.set(f"{min(y0, y1):.4g}")
            self._ylim_hi.set(f"{max(y0, y1):.4g}")
        except Exception:
            pass

    def _on_unit_change(self):
        """Convert the stored x-limits to the new unit before redrawing."""
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
    #  File loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_files(self):
        paths = filedialog.askopenfilenames(
            title="Open UV/Vis file(s)", filetypes=_FILE_TYPES)
        if not paths:
            return

        n_loaded, n_failed = 0, 0
        for path in paths:
            try:
                new_scans = parse_uvvis_file(path)
                for scan in new_scans:
                    key = (scan.source_file, scan.label)
                    if any((s.source_file, s.label) == key
                           for s in self._scans):
                        continue
                    self._scans.append(scan)
                    idx = len(self._scans) - 1
                    self._colours[scan.label] = _PALETTE[idx % len(_PALETTE)]
                    self._vis_vars[scan.label] = tk.BooleanVar(value=True)
                    n_loaded += 1
            except Exception as exc:
                n_failed += 1
                messagebox.showerror(
                    "Load error",
                    f"Could not read {os.path.basename(path)}:\n{exc}")

        if n_loaded:
            self._rebuild_list()
            self._redraw()
            self._status_lbl.config(
                text=f"{len(self._scans)} spectrum/spectra loaded.",
                fg="#003300")

    def _remove_scan(self, label: str):
        self._scans = [s for s in self._scans if s.label != label]
        self._vis_vars.pop(label, None)
        self._colours.pop(label, None)
        self._rebuild_list()
        self._redraw()

    # ══════════════════════════════════════════════════════════════════════════
    #  Scan list UI
    # ══════════════════════════════════════════════════════════════════════════

    def _rebuild_list(self):
        for w in self._list_inner.winfo_children():
            w.destroy()

        for i, scan in enumerate(self._scans):
            colour = self._colours.get(scan.label, _PALETTE[i % len(_PALETTE)])
            var    = self._vis_vars.get(scan.label)
            if var is None:
                var = tk.BooleanVar(value=True)
                self._vis_vars[scan.label] = var

            row = tk.Frame(self._list_inner)
            row.pack(fill=tk.X, pady=1, padx=2)

            tk.Label(row, bg=colour, width=3, relief=tk.RAISED
                     ).pack(side=tk.LEFT, padx=(0, 3))

            tk.Checkbutton(row, text=scan.display_name(), variable=var,
                           command=self._redraw, anchor="w", font=("", 8),
                           wraplength=150, justify=tk.LEFT,
                           ).pack(side=tk.LEFT, fill=tk.X, expand=True)

            tk.Button(row, text="✕", font=("", 7), relief=tk.FLAT,
                      command=lambda lbl=scan.label: self._remove_scan(lbl)
                      ).pack(side=tk.RIGHT)

        self._list_canvas.update_idletasks()
        self._list_canvas.configure(
            scrollregion=self._list_canvas.bbox("all"))

    def _set_all_vis(self, state: bool):
        for var in self._vis_vars.values():
            var.set(state)
        self._redraw()

    # ══════════════════════════════════════════════════════════════════════════
    #  Data extraction helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _x_data(self, scan: UVVisScan) -> np.ndarray:
        unit = self._x_unit.get()
        if unit == "cm-1":
            return scan.wavenumber_cm1
        if unit == "eV":
            return scan.energy_ev
        return scan.wavelength_nm

    def _y_data(self, scan: UVVisScan) -> np.ndarray:
        y = (scan.transmittance_pct if self._y_unit.get() == "%T"
             else scan.absorbance)
        mode = self._norm_mode.get()
        if mode == "peak":
            pk = np.nanmax(np.abs(y))
            if pk > 0:
                y = y / pk
        elif mode == "area":
            area = np.trapz(np.abs(y), scan.wavelength_nm)
            if area > 0:
                y = y / area
        return y

    # ══════════════════════════════════════════════════════════════════════════
    #  Plotting
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

    def _redraw(self, *_):
        visible = [
            (s, self._colours.get(s.label, _PALETTE[0]))
            for s in self._scans
            if self._vis_vars.get(s.label, tk.BooleanVar(value=True)).get()
        ]

        if not visible:
            self._draw_empty()
            return

        # ── Capture current limits BEFORE clearing ────────────────────────────
        # This preserves any pan/zoom the user applied via the mpl toolbar,
        # in addition to anything typed into the limit entry fields.
        try:
            cur_xlim = self._ax.get_xlim()
            cur_ylim = self._ax.get_ylim()
            had_data = True
        except Exception:
            cur_xlim = cur_ylim = None
            had_data = False

        # ── Rebuild axes ──────────────────────────────────────────────────────
        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        ax = self._ax

        unit = self._x_unit.get()

        for scan, colour in visible:
            x = self._x_data(scan)
            y = self._y_data(scan)
            order = np.argsort(x)
            ax.plot(x[order], y[order], color=colour,
                    linewidth=1.5, label=scan.display_name())

        # ── Axis labels ───────────────────────────────────────────────────────
        xlabels = {"nm":   "Wavelength (nm)",
                   "cm-1": "Wavenumber (cm⁻¹)",
                   "eV":   "Energy (eV)"}
        ylabels = {"A":  "Absorbance",
                   "%T": "Transmittance (%)"}
        ax.set_xlabel(xlabels.get(unit, unit), fontsize=10, fontweight="bold")
        ax.set_ylabel(ylabels.get(self._y_unit.get(), ""),
                      fontsize=10, fontweight="bold")

        # ── Secondary λ(nm) axis on top when x = cm⁻¹ ───────────────────────
        if unit == "cm-1" and self._show_nm_axis.get():
            def _fwd(x):
                with np.errstate(divide="ignore", invalid="ignore"):
                    return np.where(np.asarray(x, float) > 0,
                                    1e7 / np.asarray(x, float), 0.0)
            sec = ax.secondary_xaxis("top", functions=(_fwd, _fwd))
            sec.set_xlabel("λ (nm)", fontsize=9)
            sec.tick_params(axis="x", direction="in", labelsize=8)

        # ── Invert nm axis (instruments scan high→low wavelength) ─────────────
        if unit == "nm":
            lo_nm = min(s.wavelength_nm.min() for s, _ in visible)
            hi_nm = max(s.wavelength_nm.max() for s, _ in visible)
            # Invert so that short wavelength (high energy) is on the right
            ax.set_xlim(hi_nm, lo_nm)

        # ── Apply stored / entry x-limits (override auto above) ──────────────
        lo_x = self._parse_lim(self._xlim_lo)
        hi_x = self._parse_lim(self._xlim_hi)
        if lo_x is not None or hi_x is not None:
            cur = ax.get_xlim()
            ax.set_xlim(lo_x if lo_x is not None else cur[0],
                        hi_x if hi_x is not None else cur[1])

        # ── Apply stored / entry y-limits ─────────────────────────────────────
        lo_y = self._parse_lim(self._ylim_lo)
        hi_y = self._parse_lim(self._ylim_hi)
        if lo_y is not None or hi_y is not None:
            cur = ax.get_ylim()
            ax.set_ylim(lo_y if lo_y is not None else cur[0],
                        hi_y if hi_y is not None else cur[1])

        # ── Legend ────────────────────────────────────────────────────────────
        if len(visible) > 1:
            ax.legend(fontsize=8, loc="best", framealpha=0.7)

        ax.grid(True, linestyle=":", alpha=0.4)
        self._fig.tight_layout()
        self._canvas.draw_idle()
        self._toolbar.update()

    # ══════════════════════════════════════════════════════════════════════════
    #  Push to TDDFT overlay
    # ══════════════════════════════════════════════════════════════════════════

    def _add_selected_to_overlay(self):
        if self._add_scan_fn is None:
            messagebox.showinfo("Not available",
                                "No TDDFT plot connected to this panel.")
            return

        visible = [s for s in self._scans
                   if self._vis_vars.get(s.label, tk.BooleanVar()).get()]
        if not visible:
            messagebox.showinfo("Nothing selected",
                                "Check at least one spectrum in the list first.")
            return

        for scan in visible:
            energy_ev  = scan.energy_ev.copy()
            absorbance = scan.absorbance.copy()

            order      = np.argsort(energy_ev)
            energy_ev  = energy_ev[order]
            absorbance = absorbance[order]

            mask       = energy_ev > 0
            energy_ev  = energy_ev[mask]
            absorbance = absorbance[mask]

            exp_scan = ExperimentalScan(
                label=scan.label,
                source_file=scan.source_file,
                energy_ev=energy_ev,
                mu=absorbance,
                is_normalized=True,
                scan_type="UV/Vis absorbance",
                metadata=dict(scan.metadata, uvvis_source=scan.source_file),
            )
            self._add_scan_fn(exp_scan)

        self._status_lbl.config(
            text=f"Added {len(visible)} spectrum/spectra to TDDFT overlay.",
            fg="#003d7a")
