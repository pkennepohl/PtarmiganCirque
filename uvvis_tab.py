"""
uvvis_tab.py — UV/Vis/NIR analysis tab for Ptarmigan
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional

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


class UVVisTab(tk.Frame):
    """UV/Vis/NIR import, display and analysis panel.

    Parameters
    ----------
    parent       : Tk parent widget
    add_scan_fn  : optional callable(ExperimentalScan) — called when the user
                   clicks '+ Add to TDDFT Overlay'.  The scan is converted to
                   energy (eV) so it fits naturally on the main TDDFT plot.
    """

    def __init__(self, parent,
                 add_scan_fn: Optional[Callable] = None):
        super().__init__(parent)
        self._add_scan_fn: Optional[Callable] = add_scan_fn

        # ── State ─────────────────────────────────────────────────────────────
        self._scans:     List[UVVisScan] = []
        self._vis_vars:  Dict[str, tk.BooleanVar] = {}   # label → checked
        self._colours:   Dict[str, str]            = {}   # label → hex colour

        # Display options
        self._x_unit   = tk.StringVar(value="nm")        # "nm" | "cm-1" | "eV"
        self._y_unit   = tk.StringVar(value="A")         # "A"  | "%T"
        self._show_nm_axis = tk.BooleanVar(value=True)   # secondary nm axis when x=cm-1
        self._norm_mode    = tk.StringVar(value="none")  # "none"|"area"|"peak"

        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    #  Layout
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Top toolbar ───────────────────────────────────────────────────────
        top = tk.Frame(self, bd=1, relief=tk.GROOVE, padx=4, pady=3)
        top.pack(side=tk.TOP, fill=tk.X)
        self._build_toolbar(top)

        # ── Body: scan list (left) + plot (right) ─────────────────────────────
        body = tk.PanedWindow(self, orient=tk.HORIZONTAL,
                              sashwidth=5, sashrelief=tk.RAISED)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left panel
        left = tk.Frame(body, width=220, bd=1, relief=tk.SUNKEN)
        body.add(left, minsize=180)
        self._build_scan_list(left)

        # Right panel — plot
        right = tk.Frame(body)
        body.add(right, minsize=400)
        self._build_plot(right)

    def _build_toolbar(self, bar):
        tk.Button(bar, text="📂 Load File…",
                  font=("", 9, "bold"), bg="#003d7a", fg="white",
                  activebackground="#0055aa",
                  command=self._load_files).pack(side=tk.LEFT, padx=(2, 6))

        ttk.Separator(bar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        # X-axis unit
        tk.Label(bar, text="X:", font=("", 9)).pack(side=tk.LEFT)
        for label, val in [("nm", "nm"), ("cm⁻¹", "cm-1"), ("eV", "eV")]:
            tk.Radiobutton(bar, text=label, variable=self._x_unit, value=val,
                           command=self._redraw, font=("", 9)
                           ).pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        # Y-axis unit
        tk.Label(bar, text="Y:", font=("", 9)).pack(side=tk.LEFT)
        for label, val in [("Absorbance", "A"), ("%T", "%T")]:
            tk.Radiobutton(bar, text=label, variable=self._y_unit, value=val,
                           command=self._redraw, font=("", 9)
                           ).pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        # Normalisation
        tk.Label(bar, text="Norm:", font=("", 9)).pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self._norm_mode,
                     values=["none", "peak", "area"],
                     state="readonly", width=6,
                     font=("", 9)).pack(side=tk.LEFT, padx=2)
        self._norm_mode.trace_add("write", lambda *_: self._redraw())

        ttk.Separator(bar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        # Secondary nm axis toggle (only visible in cm⁻¹ mode)
        self._nm_cb = tk.Checkbutton(bar, text="λ(nm) axis",
                                     variable=self._show_nm_axis,
                                     command=self._redraw, font=("", 9))
        self._nm_cb.pack(side=tk.LEFT, padx=2)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        tk.Button(bar, text="+ Add to TDDFT Overlay",
                  font=("", 9, "bold"), bg="#4a0070", fg="white",
                  activebackground="#6a0090",
                  command=self._add_selected_to_overlay
                  ).pack(side=tk.LEFT, padx=2)

        self._status_lbl = tk.Label(bar, text="Load a UV/Vis file to begin.",
                                    fg="gray", font=("", 8))
        self._status_lbl.pack(side=tk.LEFT, padx=10)

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

        # Scrollable list area
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
        self._canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        toolbar_frame = tk.Frame(parent)
        toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self._toolbar = NavigationToolbar2Tk(self._canvas, toolbar_frame)
        self._toolbar.update()

        self._draw_empty()

    # ══════════════════════════════════════════════════════════════════════════
    #  File loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_files(self):
        paths = filedialog.askopenfilenames(
            title="Open UV/Vis file(s)",
            filetypes=_FILE_TYPES)
        if not paths:
            return
        n_loaded, n_failed = 0, 0
        for path in paths:
            try:
                new_scans = parse_uvvis_file(path)
                for scan in new_scans:
                    # Deduplicate by (source_file, label)
                    key = (scan.source_file, scan.label)
                    if any((s.source_file, s.label) == key
                           for s in self._scans):
                        continue
                    self._scans.append(scan)
                    idx = len(self._scans) - 1
                    colour = _PALETTE[idx % len(_PALETTE)]
                    self._colours[scan.label] = colour
                    var = tk.BooleanVar(value=True)
                    self._vis_vars[scan.label] = var
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

            # Colour swatch
            tk.Label(row, bg=colour, width=3, relief=tk.RAISED
                     ).pack(side=tk.LEFT, padx=(0, 3))

            # Visibility checkbox + label
            tk.Checkbutton(row, text=scan.display_name(), variable=var,
                           command=self._redraw, anchor="w",
                           font=("", 8), wraplength=150, justify=tk.LEFT
                           ).pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Remove button
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

    def _y_data(self, scan: UVVisScan) -> np.ndarray:
        """Return the y-array for the current display unit + normalisation."""
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

    def _x_data(self, scan: UVVisScan):
        unit = self._x_unit.get()
        if unit == "cm-1":
            return scan.wavenumber_cm1
        if unit == "eV":
            return scan.energy_ev
        return scan.wavelength_nm

    def _redraw(self):
        visible = [(s, self._colours.get(s.label, "#333333"))
                   for s in self._scans
                   if self._vis_vars.get(s.label, tk.BooleanVar(value=True)).get()]

        if not visible:
            self._draw_empty()
            return

        self._fig.clear()

        unit = self._x_unit.get()
        show_nm_top = (unit == "cm-1" and self._show_nm_axis.get())

        if show_nm_top:
            from mpl_toolkits.axes_grid1 import host_subplot
            # Use secondary_xaxis for the nm axis on top
            self._ax = self._fig.add_subplot(111)
        else:
            self._ax = self._fig.add_subplot(111)

        ax = self._ax

        for scan, colour in visible:
            x = self._x_data(scan)
            y = self._y_data(scan)
            # Sort by x (ascending) — cm⁻¹ is ascending for increasing energy
            order = np.argsort(x)
            ax.plot(x[order], y[order], color=colour,
                    linewidth=1.5, label=scan.display_name())

        # ── Axes labels ───────────────────────────────────────────────────────
        xlabels = {"nm": "Wavelength (nm)",
                   "cm-1": "Wavenumber (cm⁻¹)",
                   "eV": "Energy (eV)"}
        ylabels = {"A": "Absorbance",
                   "%T": "Transmittance (%)"}
        ax.set_xlabel(xlabels.get(unit, unit), fontsize=10, fontweight="bold")
        ax.set_ylabel(ylabels.get(self._y_unit.get(), ""), fontsize=10,
                      fontweight="bold")

        # ── Secondary nm axis on top when x = cm⁻¹ ───────────────────────────
        if show_nm_top:
            def _cm1_to_nm(x):
                with np.errstate(divide="ignore", invalid="ignore"):
                    return np.where(np.asarray(x) > 0, 1e7 / np.asarray(x), 0)

            sec = ax.secondary_xaxis("top", functions=(_cm1_to_nm, _cm1_to_nm))
            sec.set_xlabel("λ (nm)", fontsize=9)
            sec.tick_params(axis="x", direction="in", labelsize=8)

        # ── Invert x-axis for nm (instruments scan high→low) ─────────────────
        if unit == "nm":
            xlims = ax.get_xlim()
            if xlims[0] < xlims[1]:   # not already inverted
                ax.invert_xaxis()

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
                   if self._vis_vars.get(s.label,
                                         tk.BooleanVar()).get()]
        if not visible:
            messagebox.showinfo("Nothing selected",
                                "Check at least one spectrum in the list first.")
            return

        for scan in visible:
            # Convert to ExperimentalScan (energy in eV, absorbance as μ)
            energy_ev = scan.energy_ev
            absorbance = scan.absorbance

            # Sort ascending by energy
            order     = np.argsort(energy_ev)
            energy_ev = energy_ev[order]
            absorbance = absorbance[order]

            # Remove any zero-energy points that arise from λ=0 artefacts
            mask = energy_ev > 0
            energy_ev  = energy_ev[mask]
            absorbance = absorbance[mask]

            exp_scan = ExperimentalScan(
                label=scan.label,
                source_file=scan.source_file,
                energy_ev=energy_ev,
                mu=absorbance,
                is_normalized=True,
                scan_type="UV/Vis absorbance",
                metadata=dict(scan.metadata,
                              uvvis_source=scan.source_file),
            )
            self._add_scan_fn(exp_scan)

        self._status_lbl.config(
            text=f"Added {len(visible)} spectrum/spectra to TDDFT overlay.",
            fg="#003d7a")
