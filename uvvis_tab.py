"""
uvvis_tab.py — UV/Vis/NIR analysis tab for Ptarmigan
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox

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

# ── Linestyle cycle + Tkinter dash patterns ───────────────────────────────────
_LS_CYCLE = ["solid", "dashed", "dotted", "dashdot"]
_LS_DASH: Dict[str, tuple] = {
    "solid":   (),
    "dashed":  (6, 3),
    "dotted":  (2, 3),
    "dashdot": (6, 3, 2, 3),
}

# ── Default per-scan style ────────────────────────────────────────────────────
def _default_style(colour: str) -> dict:
    return {
        "color":      colour,
        "linestyle":  "solid",
        "linewidth":  1.5,
        "alpha":      0.9,
        "fill":       False,
        "fill_alpha": 0.08,
    }

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


class UVVisTab(tk.Frame):
    """UV/Vis/NIR import, display and analysis panel."""

    def __init__(self, parent, add_scan_fn: Optional[Callable] = None):
        super().__init__(parent)
        self._add_scan_fn: Optional[Callable] = add_scan_fn

        # ── Scan entries: list of dicts ───────────────────────────────────────
        # Each entry: {"scan", "vis", "in_legend", "style"}
        self._entries: List[dict] = []

        # ── Display options ───────────────────────────────────────────────────
        self._x_unit      = tk.StringVar(value="nm")
        self._x_unit_prev = "nm"
        self._y_unit      = tk.StringVar(value="A")
        self._show_nm_axis = tk.BooleanVar(value=True)
        self._norm_mode   = tk.StringVar(value="none")

        # ── Axis limits (empty string = auto) ────────────────────────────────
        self._xlim_lo = tk.StringVar(value="")
        self._xlim_hi = tk.StringVar(value="")
        self._ylim_lo = tk.StringVar(value="")
        self._ylim_hi = tk.StringVar(value="")

        self._build_ui()

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

        left = tk.Frame(body, bd=1, relief=tk.SUNKEN)
        body.add(left, minsize=200)
        self._build_table_panel(left)

        right = tk.Frame(body)
        body.add(right, minsize=400)
        self._build_plot(right)

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
        tk.Label(bar, text="Norm:", font=F9).pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self._norm_mode,
                     values=["none", "peak", "area"],
                     state="readonly", width=6, font=F9,
                     ).pack(side=tk.LEFT, padx=2)
        self._norm_mode.trace_add("write", lambda *_: self._redraw())

        _sep()
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

    # ── Scan table panel ──────────────────────────────────────────────────────

    def _build_table_panel(self, parent):
        tk.Label(parent, text="Loaded Spectra",
                 font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(4, 2))

        # Scrollable canvas
        container = tk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self._tbl_canvas = tk.Canvas(container, bd=0, highlightthickness=0)
        sb = ttk.Scrollbar(container, orient=tk.VERTICAL,
                           command=self._tbl_canvas.yview)
        self._tbl_inner = tk.Frame(self._tbl_canvas)
        self._tbl_inner.bind(
            "<Configure>",
            lambda e: self._tbl_canvas.configure(
                scrollregion=self._tbl_canvas.bbox("all")))
        self._tbl_win = self._tbl_canvas.create_window(
            (0, 0), window=self._tbl_inner, anchor="nw")
        self._tbl_canvas.bind(
            "<Configure>",
            lambda e: self._tbl_canvas.itemconfig(self._tbl_win, width=e.width))
        self._tbl_canvas.configure(yscrollcommand=sb.set)
        self._tbl_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

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
    #  Table rebuild
    # ══════════════════════════════════════════════════════════════════════════

    def _rebuild_table(self):
        for w in self._tbl_inner.winfo_children():
            w.destroy()

        if not self._entries:
            tk.Label(self._tbl_inner,
                     text="No spectra loaded.",
                     fg="gray", font=("", 8)
                     ).grid(row=0, column=0, padx=8, pady=8)
            self._tbl_canvas.update_idletasks()
            self._tbl_canvas.configure(
                scrollregion=self._tbl_canvas.bbox("all"))
            return

        tbl = tk.Frame(self._tbl_inner)
        tbl.pack(fill=tk.X, expand=True, padx=2)

        # Column layout:
        # 0  colour swatch
        # 1  ☐ label  (expands)
        # 2  Lgd toggle
        # 3  Style (linestyle)
        # 4  LW
        # 5  Fill ☐
        # 6  ✕ remove
        tbl.columnconfigure(1, weight=1, minsize=120)
        tbl.columnconfigure(0, minsize=40)
        tbl.columnconfigure(2, minsize=28)
        tbl.columnconfigure(3, minsize=44)   # linestyle canvas
        tbl.columnconfigure(4, minsize=28)
        tbl.columnconfigure(5, minsize=28)
        tbl.columnconfigure(6, minsize=28)

        HDR_BG = "#e8e8e8"
        CPX    = (4, 4)
        SPX    = (4, 2)
        RPX    = (4, 6)
        F8     = ("", 8)
        F9     = ("", 9)
        FHD    = ("", 8, "bold")

        # ── Header ────────────────────────────────────────────────────────────
        for col, txt, anch, px in [
            (0, "",       "center", SPX),
            (1, "Label",  "w",      (6, 4)),
            (2, "Lgd",    "center", CPX),
            (3, "Style",  "center", CPX),
            (4, "LW",     "center", CPX),
            (5, "Fill",   "center", CPX),
            (6, "",       "center", RPX),
        ]:
            tk.Label(tbl, text=txt, font=FHD, bg=HDR_BG, fg="#444444",
                     anchor=anch, padx=3,
                     ).grid(row=0, column=col, sticky="ew", ipady=1, padx=px)

        # ── Helpers ───────────────────────────────────────────────────────────
        def _make_leg_btn(parent, leg_var, r, c):
            b = tk.Button(parent, width=2, font=F9, relief=tk.FLAT)
            def _refresh(_b=b, _v=leg_var):
                _b.config(text="✓" if _v.get() else "–",
                          fg="#006600" if _v.get() else "#999999")
            def _toggle(_b=b, _v=leg_var):
                _v.set(not _v.get()); _refresh(); self._redraw()
            b.config(command=_toggle)
            _refresh()
            b.grid(row=r, column=c, padx=CPX, pady=0, sticky="ew")

        def _make_ls_canvas(parent, style, r, c):
            """Small canvas that draws the line style; click to cycle."""
            W, H = 38, 16
            cv = tk.Canvas(parent, width=W, height=H,
                           bd=1, relief=tk.SUNKEN, bg="white",
                           highlightthickness=0, cursor="hand2")

            def _draw(_cv=cv, _s=style):
                _cv.delete("all")
                ls   = _s.get("linestyle", "solid")
                clr  = _s.get("color", "#333333")
                lw   = max(0.5, float(_s.get("linewidth", 1.5)))
                dash = _LS_DASH.get(ls, ())
                kw   = {"fill": clr, "width": lw, "capstyle": "round"}
                if dash:
                    kw["dash"] = dash
                _cv.create_line(4, H // 2, W - 4, H // 2, **kw)

            def _cycle(_event=None, _cv=cv, _s=style):
                ls  = _s.get("linestyle", "solid")
                idx = _LS_CYCLE.index(ls) if ls in _LS_CYCLE else 0
                _s["linestyle"] = _LS_CYCLE[(idx + 1) % len(_LS_CYCLE)]
                _draw()
                self._redraw()

            cv.bind("<Button-1>", _cycle)
            _draw()
            cv.grid(row=r, column=c, padx=CPX, pady=2, sticky="")

        def _make_lw_entry(parent, lw_var, r, c):
            e = tk.Entry(parent, textvariable=lw_var, width=4,
                         font=("Courier", 8), justify="center")
            e.grid(row=r, column=c, padx=CPX, pady=0, sticky="ew")

        # ── Data rows ─────────────────────────────────────────────────────────
        for i, entry in enumerate(self._entries):
            r      = i + 1
            scan   = entry["scan"]
            vis    = entry["vis"]
            leg    = entry["in_legend"]
            style  = entry["style"]
            colour = style["color"]

            # Col 0: colour swatch — click to change
            def _pick(idx=i):
                old = self._entries[idx]["style"]["color"]
                result = colorchooser.askcolor(color=old,
                                               title="Pick spectrum colour")
                if result and result[1]:
                    self._entries[idx]["style"]["color"] = result[1]
                    self._rebuild_table()
                    self._redraw()
            tk.Button(tbl, bg=colour, relief=tk.RAISED, width=3,
                      text="UV", fg="white", font=("", 7, "bold"),
                      activebackground=colour, cursor="hand2",
                      command=_pick,
                      ).grid(row=r, column=0, padx=SPX, pady=1, sticky="w")

            # Col 1: visibility checkbox + label
            tk.Checkbutton(tbl, text=scan.display_name(), variable=vis,
                           command=self._redraw, anchor="w", font=F9,
                           wraplength=200, justify=tk.LEFT,
                           ).grid(row=r, column=1, sticky="ew",
                                  padx=(6, 4), pady=0)

            # Col 2: legend toggle
            _make_leg_btn(tbl, leg, r, 2)

            # Col 3: linestyle canvas (click to cycle)
            _make_ls_canvas(tbl, style, r, 3)

            # Col 4: linewidth
            lw_var = tk.DoubleVar(value=style.get("linewidth", 1.5))
            def _lw_cb(s=style, v=lw_var, *_):
                try:
                    s["linewidth"] = float(v.get()); self._redraw()
                except Exception:
                    pass
            lw_var.trace_add("write", lambda *a, s=style, v=lw_var: _lw_cb(s, v))
            _make_lw_entry(tbl, lw_var, r, 4)

            # Col 5: fill checkbox
            fill_var = tk.BooleanVar(value=style.get("fill", False))
            def _fill_cb(s=style, v=fill_var, *_):
                s["fill"] = v.get(); self._redraw()
            fill_var.trace_add("write", lambda *a, s=style, v=fill_var: _fill_cb(s, v))
            tk.Checkbutton(tbl, variable=fill_var,
                           ).grid(row=r, column=5, padx=CPX, pady=0,
                                  sticky="ew")

            # Col 6: remove
            tk.Button(tbl, text="✕", font=F8, relief=tk.FLAT,
                      command=lambda idx=i: self._remove_entry(idx),
                      ).grid(row=r, column=6, padx=RPX, pady=0, sticky="e")

        self._tbl_canvas.update_idletasks()
        self._tbl_canvas.configure(
            scrollregion=self._tbl_canvas.bbox("all"))
        # Resize canvas height to content, capped at ~8 rows
        actual_h = self._tbl_inner.winfo_reqheight()
        if actual_h > 0:
            self._tbl_canvas.configure(
                height=min(actual_h, 26 + 8 * 24))

    # ══════════════════════════════════════════════════════════════════════════
    #  File loading / removal
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
                    key = (scan.source_file, scan.label)
                    if any((e["scan"].source_file, e["scan"].label) == key
                           for e in self._entries):
                        continue
                    idx    = len(self._entries)
                    colour = _PALETTE[idx % len(_PALETTE)]
                    self._entries.append({
                        "scan":      scan,
                        "vis":       tk.BooleanVar(value=True),
                        "in_legend": tk.BooleanVar(value=True),
                        "style":     _default_style(colour),
                    })
                    n_loaded += 1
            except Exception as exc:
                messagebox.showerror(
                    "Load error",
                    f"Could not read {os.path.basename(path)}:\n{exc}")

        if n_loaded:
            self._rebuild_table()
            self._redraw()
            self._status_lbl.config(
                text=f"{len(self._entries)} spectrum/spectra loaded.",
                fg="#003300")

    def _remove_entry(self, idx: int):
        if 0 <= idx < len(self._entries):
            self._entries.pop(idx)
            self._rebuild_table()
            self._redraw()

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

    def _x_data(self, scan: UVVisScan) -> np.ndarray:
        unit = self._x_unit.get()
        if unit == "cm-1": return scan.wavenumber_cm1
        if unit == "eV":   return scan.energy_ev
        return scan.wavelength_nm

    def _y_data(self, scan: UVVisScan) -> np.ndarray:
        y = (scan.transmittance_pct if self._y_unit.get() == "%T"
             else scan.absorbance)
        mode = self._norm_mode.get()
        if mode == "peak":
            pk = np.nanmax(np.abs(y))
            if pk > 0: y = y / pk
        elif mode == "area":
            area = np.trapz(np.abs(y), scan.wavelength_nm)
            if area > 0: y = y / area
        return y

    def _redraw(self, *_):
        visible = [e for e in self._entries if e["vis"].get()]

        if not visible:
            self._draw_empty()
            return

        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        ax   = self._ax
        unit = self._x_unit.get()

        for entry in visible:
            scan   = entry["scan"]
            style  = entry["style"]
            colour = style["color"]
            x = self._x_data(scan)
            y = self._y_data(scan)
            order  = np.argsort(x)
            x, y   = x[order], y[order]
            label  = scan.display_name() if entry["in_legend"].get() else None
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

        # ── Axis labels ───────────────────────────────────────────────────────
        ax.set_xlabel({"nm":   "Wavelength (nm)",
                       "cm-1": "Wavenumber (cm⁻¹)",
                       "eV":   "Energy (eV)"}.get(unit, unit),
                      fontsize=10, fontweight="bold")
        ax.set_ylabel({"A": "Absorbance", "%T": "Transmittance (%)"
                       }.get(self._y_unit.get(), ""),
                      fontsize=10, fontweight="bold")

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
            lo_nm = min(e["scan"].wavelength_nm.min() for e in visible)
            hi_nm = max(e["scan"].wavelength_nm.max() for e in visible)
            ax.set_xlim(hi_nm, lo_nm)

        # ── Apply stored x-limits ─────────────────────────────────────────────
        lo_x = self._parse_lim(self._xlim_lo)
        hi_x = self._parse_lim(self._xlim_hi)
        if lo_x is not None or hi_x is not None:
            cur = ax.get_xlim()
            if unit == "nm":
                # nm axis is inverted: lo_x is the right edge, hi_x is the left edge
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

        # ── Legend ────────────────────────────────────────────────────────────
        handles, labels = ax.get_legend_handles_labels()
        if handles:
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

        visible = [e for e in self._entries if e["vis"].get()]
        if not visible:
            messagebox.showinfo("Nothing selected",
                                "Check at least one spectrum in the list first.")
            return

        for entry in visible:
            scan      = entry["scan"]
            energy_ev = scan.energy_ev.copy()
            absorb    = scan.absorbance.copy()
            order     = np.argsort(energy_ev)
            energy_ev = energy_ev[order]
            absorb    = absorb[order]
            mask      = energy_ev > 0
            exp_scan  = ExperimentalScan(
                label=scan.label,
                source_file=scan.source_file,
                energy_ev=energy_ev[mask],
                mu=absorb[mask],
                is_normalized=True,
                scan_type="UV/Vis absorbance",
                metadata=dict(scan.metadata, uvvis_source=scan.source_file),
            )
            self._add_scan_fn(exp_scan)

        self._status_lbl.config(
            text=f"Added {len(visible)} spectrum/spectra to TDDFT overlay.",
            fg="#003d7a")
