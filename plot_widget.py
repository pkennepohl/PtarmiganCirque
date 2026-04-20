"""
Interactive TDDFT / XAS plot widget using matplotlib embedded in tkinter.
Supports single-spectrum view, multi-spectrum TDDFT overlay, and experimental
XAS scan overlay on a twin axis with ΔE energy-shift alignment.
"""

import json
import pathlib
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Optional, Tuple

from orca_parser import TDDFTSpectrum
from experimental_parser import ExperimentalScan

# ── Persistent font defaults ──────────────────────────────────────────────────
# Settings are saved to binah_settings.json next to this file.
# These values are the factory fallback used when no settings file exists.
_SETTINGS_FILE = pathlib.Path(__file__).with_name("binah_settings.json")

_FONT_FACTORY_DEFAULTS: dict = {
    "title_size":  11,   "title_bold":  True,
    "xlabel_size": 15,   "xlabel_bold": True,
    "ylabel_size": 15,   "ylabel_bold": True,
    "tick_size":   12,
    "legend_size": 14,
}


def _load_font_defaults() -> dict:
    """Return font defaults from the settings file, falling back to factory."""
    defaults = dict(_FONT_FACTORY_DEFAULTS)
    try:
        if _SETTINGS_FILE.exists():
            data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            for k in defaults:
                if k in data.get("font", {}):
                    defaults[k] = data["font"][k]
    except Exception:
        pass
    return defaults


def _save_font_defaults(d: dict) -> None:
    """Persist font defaults to the settings file (merges with existing data)."""
    try:
        existing: dict = {}
        if _SETTINGS_FILE.exists():
            existing = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        existing["font"] = d
        _SETTINGS_FILE.write_text(
            json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[binah] Could not save font settings: {exc}")


# ── Broadening functions ──────────────────────────────────────────────────────

def gaussian(x, center, fwhm):
    sigma = fwhm / (2 * np.sqrt(2 * np.log(2)))
    return np.exp(-0.5 * ((x - center) / sigma) ** 2)


def lorentzian(x, center, fwhm):
    gamma = fwhm / 2.0
    return gamma**2 / ((x - center)**2 + gamma**2)


# ── Colour cycles ─────────────────────────────────────────────────────────────
OVERLAY_COLOURS = [
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e",
    "#9467bd", "#8c564b", "#e377c2", "#17becf",
]

# Warm red/brown palette for experimental scans — distinct from TDDFT blues
EXP_COLOURS = [
    "#8B0000", "#B22222", "#CC4400", "#884400", "#6A1B9A", "#00695C",
]

# Matplotlib linestyle names → display names and mpl values
LS_OPTIONS = [
    ("Solid",    "solid"),
    ("Dashed",   "dashed"),
    ("Dotted",   "dotted"),
    ("Dash-dot", "dashdot"),
]


# ── Lightweight tooltip for panel widgets ────────────────────────────────────

class _ToolTip:
    """Shows a small tooltip label after a short hover delay."""
    def __init__(self, widget, text: str, delay: int = 600):
        self._widget = widget
        self._text   = text
        self._delay  = delay
        self._id     = None
        self._win    = None
        widget.bind("<Enter>",  self._schedule, add="+")
        widget.bind("<Leave>",  self._cancel,   add="+")
        widget.bind("<Button>", self._cancel,   add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._id = self._widget.after(self._delay, self._show)

    def _cancel(self, _event=None):
        if self._id:
            self._widget.after_cancel(self._id)
            self._id = None
        if self._win:
            self._win.destroy()
            self._win = None

    def _show(self):
        x = self._widget.winfo_rootx() + self._widget.winfo_width() + 4
        y = self._widget.winfo_rooty()
        self._win = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self._text, background="#ffffe0",
                 relief=tk.SOLID, borderwidth=1,
                 font=("", 8)).pack()


# ── Mutable default style stores ─────────────────────────────────────────────
# "Set as Default" writes to disk so preferences survive program restarts.
import json as _json
import os as _os

_STYLE_CONFIG_PATH = _os.path.join(
    _os.path.expanduser("~"), ".binah_config.json")

_EXP_STYLE_FACTORY: dict = {
    "linestyle":  "solid",
    "linewidth":  1.8,
    "fill":       True,
    "fill_alpha": 0.06,
    "color":      "",
}
_TDDFT_STYLE_FACTORY: dict = {
    "env_linewidth":   2.0,
    "env_linestyle":   "solid",
    "env_fill":        True,
    "env_fill_alpha":  0.10,
    "stick_linewidth": 1.2,
    "stick_alpha":     0.75,
    "stick_markersize": 4,
    "stick_markers":   True,
}


def _load_style_config() -> tuple:
    """Load exp + tddft style defaults from the shared config file."""
    exp   = dict(_EXP_STYLE_FACTORY)
    tddft = dict(_TDDFT_STYLE_FACTORY)
    try:
        if _os.path.exists(_STYLE_CONFIG_PATH):
            with open(_STYLE_CONFIG_PATH, "r", encoding="utf-8") as _f:
                _cfg = _json.load(_f)
            for k, v in _cfg.get("exp_style_defaults", {}).items():
                if k in exp:
                    exp[k] = v
            for k, v in _cfg.get("tddft_style_defaults", {}).items():
                if k in tddft:
                    tddft[k] = v
    except Exception:
        pass
    return exp, tddft


def _save_style_config() -> None:
    """Persist current style defaults to the shared config file."""
    try:
        cfg = {}
        if _os.path.exists(_STYLE_CONFIG_PATH):
            with open(_STYLE_CONFIG_PATH, "r", encoding="utf-8") as _f:
                cfg = _json.load(_f)
        cfg["exp_style_defaults"]   = dict(_EXP_STYLE_DEFAULTS)
        cfg["tddft_style_defaults"] = dict(_TDDFT_STYLE_DEFAULTS)
        with open(_STYLE_CONFIG_PATH, "w", encoding="utf-8") as _f:
            _json.dump(cfg, _f, indent=2)
    except Exception:
        pass


# Initialise from disk (falls back to factory values if config absent)
_EXP_STYLE_DEFAULTS, _TDDFT_STYLE_DEFAULTS = _load_style_config()


def _default_exp_style() -> dict:
    """Return a fresh copy of the current experimental-scan defaults."""
    return dict(_EXP_STYLE_DEFAULTS)


def _default_tddft_style() -> dict:
    """Return a fresh copy of the current TDDFT defaults."""
    return dict(_TDDFT_STYLE_DEFAULTS)


# ═════════════════════════════════════════════════════════════════════════════
class PlotWidget(tk.Frame):
    """
    Embeds a matplotlib figure with a controls strip.
    Supports:
      - Single spectrum view + multi-spectrum TDDFT overlay (right y-axis)
      - Experimental XAS scans on left y-axis
      - ΔE shift: nudge all TDDFT positions to align with experimental
      - Per-overlay enable/disable, style control and label editing
      - Global TDDFT style (envelope/stick) and per-scan experimental style
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        # Unified TDDFT spectrum list.
        # Index 0 = "primary" (replaced by load_spectrum); higher indices = overlays.
        # Each entry: {"label": str, "spectrum": TDDFTSpectrum,
        #              "enabled": tk.BooleanVar, "color": str}
        # color == "" → auto-assign from OVERLAY_COLOURS[index] palette.
        self._tddft_spectra: List[dict] = []

        # Experimental scan list: [(label, ExperimentalScan, enabled_BooleanVar, style_dict), ...]
        self._exp_scans: List[Tuple[str, ExperimentalScan, tk.BooleanVar, dict, tk.BooleanVar]] = []
        self._exp_link_counter = 1

        # Global style dictionaries
        self._tddft_style = _default_tddft_style()

        # Controls state
        self._x_unit      = tk.StringVar(value="eV")
        self._prev_x_unit = "eV"   # tracks previous unit for xlim conversion
        self._broadening  = tk.StringVar(value="Gaussian")
        self._fwhm        = tk.DoubleVar(value=1.0)
        self._fwhm_str    = tk.StringVar(value="1.00")
        self._show_sticks = tk.BooleanVar(value=True)
        self._show_env    = tk.BooleanVar(value=True)
        self._show_trans  = tk.BooleanVar(value=False)
        self._normalise   = tk.BooleanVar(value=False)
        self._show_legend           = tk.BooleanVar(value=True)
        self._show_tddft_in_legend  = tk.BooleanVar(value=True)   # TDDFT handles in legend
        self._show_primary_in_legend = tk.BooleanVar(value=True)  # primary TDDFT in legend
        self._custom_title = tk.StringVar(value="")
        self._custom_x_label  = tk.StringVar(value="")   # blank = auto from unit
        self._tick_direction  = tk.StringVar(value="in")  # "in" / "out" / "both"

        # ΔE energy shift (eV) applied to all TDDFT stick positions.
        # _delta_e holds the true (unbounded) value.
        # _de_slider_var is the slider display var, clamped to ±200 for the widget.
        self._delta_e       = tk.DoubleVar(value=0.0)
        self._delta_e_str   = tk.StringVar(value="+0.00")
        self._de_slider_var = tk.DoubleVar(value=0.0)

        # Intensity scale factor multiplied onto all TDDFT y-values.
        # Useful for visually matching TDDFT envelope height to experimental μ(E).
        # Entry accepts any positive float; slider covers 0.01–5× for fine-tuning.
        self._tddft_scale       = tk.DoubleVar(value=1.0)
        self._tddft_scale_str   = tk.StringVar(value="1.000")
        self._scale_slider_var  = tk.DoubleVar(value=1.0)

        # Plot appearance
        self._bg_colour  = "#ffffff"   # axes + figure background colour
        self._show_grid  = tk.BooleanVar(value=False)  # grid off by default

        # Combined-spectrum component toggles (shown/hidden by _update_comb_ui)
        self._comb_total = tk.BooleanVar(value=True)
        self._comb_d2    = tk.BooleanVar(value=False)
        self._comb_m2    = tk.BooleanVar(value=False)
        self._comb_q2    = tk.BooleanVar(value=False)
        self._comb_frame = None   # tk.Frame reference — built in _build_controls

        # Pop-out window refresh callbacks — each entry is a callable()
        # registered by _pop_out_graph and removed when the window closes.
        self._popout_callbacks: list = []

        # Legend drag persistence: (x, y) in figure-fraction coords, or None = "best"
        self._legend_bbox      = None   # (x, y) figure-fraction of upper-left corner
        self._legend_ref       = None
        self._legend_drag_cid  = None   # press
        self._legend_drag_cid2 = None   # motion
        self._legend_drag_cid3 = None   # release
        self._legend_dragging  = False  # True only while mouse is held & moved

        # Master visibility toggles
        self._show_tddft = tk.BooleanVar(value=True)
        self._tddft_on_left = tk.StringVar(value="left")  # "left" or "right"
        self._show_nm_axis   = tk.BooleanVar(value=False)  # secondary nm axis (cm⁻¹ mode only)
        self._nm_axis_cb     = None                        # reference to the checkbox widget
        self._custom_nm_label = tk.StringVar(value="\u03bb (nm)")  # label for the top nm axis
        self._nm_step        = tk.StringVar(value="")      # manual tick step in nm (blank = auto)

        # Manual axis-range overrides (empty string = auto-scale)
        self._xlim_lo = tk.StringVar(value="")
        self._xlim_hi = tk.StringVar(value="")
        self._ylim_lo = tk.StringVar(value="")    # left / TDDFT axis
        self._ylim_hi = tk.StringVar(value="")
        self._ylim_exp_lo = tk.StringVar(value="")  # right / Exp axis
        self._ylim_exp_hi = tk.StringVar(value="")
        # Upstream uses _yleft_lo/_yleft_hi for the same exp-axis limits;
        # alias them so the toolbar entries built from upstream code work.
        self._yleft_lo = self._ylim_exp_lo
        self._yleft_hi = self._ylim_exp_hi

        # Font controls — sizes and bold toggles for each text element
        # Initialised from the user's saved defaults (or factory fallback).
        _fd = _load_font_defaults()
        self._font_title_size   = tk.IntVar(value=_fd["title_size"])
        self._font_title_bold   = tk.BooleanVar(value=_fd["title_bold"])
        self._font_xlabel_size  = tk.IntVar(value=_fd["xlabel_size"])
        self._font_xlabel_bold  = tk.BooleanVar(value=_fd["xlabel_bold"])
        self._font_ylabel_size  = tk.IntVar(value=_fd["ylabel_size"])
        self._font_ylabel_bold  = tk.BooleanVar(value=_fd["ylabel_bold"])
        self._font_tick_size    = tk.IntVar(value=_fd["tick_size"])
        self._font_legend_size  = tk.IntVar(value=_fd["legend_size"])

        # Y-axis label visibility + custom text overrides
        # Empty string = use the auto-computed label; non-empty = use the override.
        self._show_left_ylabel   = tk.BooleanVar(value=True)
        self._show_right_ylabel  = tk.BooleanVar(value=True)
        self._custom_left_ylabel  = tk.StringVar(value="")
        self._custom_right_ylabel = tk.StringVar(value="")

        # Inset (zoomed sub-plot) state
        self._inset_active      = False
        self._inset_xlim        = [None, None]   # data-unit (current x unit)
        self._inset_ylim        = [None, None]   # left-axis units
        self._inset_pos         = [0.54, 0.52, 0.40, 0.34]  # axes-fraction [l,b,w,h]
        self._inset_ax          = None
        self._inset_ax2         = None
        self._inset_drag        = None           # {x0, y0, pos0} while dragging
        self._inset_drag_cids: list = []
        self._inset_plot_data: list = []         # collected each _replot for re-draw
        self._inset_show_labels = tk.BooleanVar(value=True)  # tick labels on/off
        self._inset_indicator   = None   # (rect, connectors) from indicate_inset_zoom

        # Hover state
        self._annot         = None
        self._hover_cid     = None
        self._hover_x       = np.array([])
        self._hover_y       = np.array([])
        self._hover_ev      = np.array([])
        self._hover_cm      = np.array([])
        self._hover_states: list = []    # actual root numbers (sp.states)
        self._hover_labels: list = []    # transition labels (sp.transition_labels)

        self._build_global_controls()
        self._build_figure()        # creates self.ax and self.ax2 once
        self._build_overlay_panel()

    # ══════════════════════════════════════════════════════════════════════════
    #  Scrollable control-bar factory
    # ══════════════════════════════════════════════════════════════════════════
    def _scrollable_bar(self, **kw) -> tk.Frame:
        """Return a Frame packed inside a horizontally-scrollable Canvas.

        Pass the same keyword arguments you would give to tk.Frame (bd, relief,
        padx, pady, bg …).  A thin horizontal scrollbar appears automatically
        whenever the bar content is wider than the window — so controls are
        never cut off on small screens — and hides itself on large screens.
        """
        outer = tk.Frame(self)
        outer.pack(side=tk.TOP, fill=tk.X)

        bg = kw.get("bg", None)
        cnv = tk.Canvas(outer, highlightthickness=0,
                        **({"bg": bg} if bg else {}))
        hbar = ttk.Scrollbar(outer, orient="horizontal", command=cnv.xview)
        cnv.configure(xscrollcommand=hbar.set)
        cnv.pack(side=tk.TOP, fill=tk.X, expand=True)

        inner = tk.Frame(cnv, **kw)
        cnv.create_window((0, 0), window=inner, anchor="nw")

        def _update(_event=None):
            cnv.configure(scrollregion=cnv.bbox("all"))
            req_h = inner.winfo_reqheight()
            if req_h > 1:
                cnv.configure(height=req_h)
            try:
                needed = inner.winfo_reqwidth() > outer.winfo_width() > 1
            except Exception:
                needed = False
            if needed:
                hbar.pack(side=tk.BOTTOM, fill=tk.X, before=cnv)
            else:
                hbar.pack_forget()

        inner.bind("<Configure>", lambda e: outer.after_idle(_update))
        outer.bind("<Configure>", lambda e: outer.after_idle(_update))
        return inner

    def _collapsible_bar(self, title: str, collapsed: bool = False, **kw) -> tk.Frame:
        """Like _scrollable_bar but wrapped in a slim collapsible header.

        Clicking the header row (or the arrow) toggles the content body.
        Returns the inner Frame just like _scrollable_bar so call-sites are
        identical.
        """
        hdr_bg = kw.get("bg") or self.cget("bg")
        # Slightly darken the header relative to the body background
        section = tk.Frame(self)
        section.pack(side=tk.TOP, fill=tk.X)

        _state = {"collapsed": collapsed}

        # ── Slim clickable header ─────────────────────────────────────────────
        hdr = tk.Frame(section, bg=hdr_bg, cursor="hand2")
        hdr.pack(side=tk.TOP, fill=tk.X)

        arrow = tk.Label(hdr, text="▶" if collapsed else "▼",
                         font=("", 7), bg=hdr_bg, fg="#555555",
                         cursor="hand2")
        arrow.pack(side=tk.LEFT, padx=(3, 1), pady=1)
        tk.Label(hdr, text=title, font=("", 8, "bold"),
                 bg=hdr_bg, fg="#333333",
                 cursor="hand2").pack(side=tk.LEFT, pady=1)

        # ── Body — holds the horizontally-scrollable canvas ───────────────────
        body = tk.Frame(section)

        bg = kw.get("bg", None)
        cnv = tk.Canvas(body, highlightthickness=0,
                        **({"bg": bg} if bg else {}))
        hbar = ttk.Scrollbar(body, orient="horizontal", command=cnv.xview)
        cnv.configure(xscrollcommand=hbar.set)
        cnv.pack(side=tk.TOP, fill=tk.X, expand=True)

        inner = tk.Frame(cnv, **kw)
        cnv.create_window((0, 0), window=inner, anchor="nw")

        def _update(_event=None):
            cnv.configure(scrollregion=cnv.bbox("all"))
            req_h = inner.winfo_reqheight()
            if req_h > 1:
                cnv.configure(height=req_h)
            try:
                needed = inner.winfo_reqwidth() > body.winfo_width() > 1
            except Exception:
                needed = False
            if needed:
                hbar.pack(side=tk.BOTTOM, fill=tk.X, before=cnv)
            else:
                hbar.pack_forget()

        inner.bind("<Configure>", lambda e: body.after_idle(_update))
        body.bind("<Configure>", lambda e: body.after_idle(_update))

        # ── Toggle logic ──────────────────────────────────────────────────────
        def _toggle(_event=None):
            if _state["collapsed"]:
                _state["collapsed"] = False
                arrow.config(text="▼")
                body.pack(side=tk.TOP, fill=tk.X)
            else:
                _state["collapsed"] = True
                arrow.config(text="▶")
                body.pack_forget()

        hdr.bind("<Button-1>", _toggle)
        arrow.bind("<Button-1>", _toggle)
        for child in hdr.winfo_children():
            child.bind("<Button-1>", _toggle)

        # Initial state
        if not collapsed:
            body.pack(side=tk.TOP, fill=tk.X)

        return inner

    # ══════════════════════════════════════════════════════════════════════════
    #  Global controls — single always-visible compact panel (replaces 6 bars)
    # ══════════════════════════════════════════════════════════════════════════
    def _build_global_controls(self):
        """Single always-visible compact control panel (replaces 6 collapsible bars)."""
        F9 = ("", 9)
        F10 = ("", 10)

        def _vsep(bar):
            tk.Frame(bar, width=1, bg="#aaaaaa").pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=2)

        outer = tk.Frame(self, bd=1, relief=tk.RIDGE)
        outer.pack(side=tk.TOP, fill=tk.X, padx=2, pady=(2, 1))

        # ── Row 0: Display & Quick Actions ───────────────────────────────────────
        r0 = tk.Frame(outer, padx=4, pady=3)
        r0.pack(side=tk.TOP, fill=tk.X)

        tk.Label(r0, text="X axis:", font=F9).pack(side=tk.LEFT)
        for unit, label in (("eV", "eV"), ("Ha", "Ha"), ("cm\u207b\u00b9", "cm\u207b\u00b9")):
            tk.Radiobutton(r0, text=label, variable=self._x_unit,
                           value=unit, command=self._on_unit_change,
                           font=F9).pack(side=tk.LEFT, padx=1)
        self._nm_axis_cb = tk.Checkbutton(
            r0, text="\u03bb(nm)", variable=self._show_nm_axis,
            command=self._replot, font=F9, state=tk.DISABLED)
        self._nm_axis_cb.pack(side=tk.LEFT, padx=(1, 1))
        tk.Label(r0, text="step:", font=F9).pack(side=tk.LEFT)
        _nm_step_e = tk.Entry(r0, textvariable=self._nm_step, width=6,
                              font=("Courier", 9))
        _nm_step_e.pack(side=tk.LEFT, padx=(1, 3))
        _nm_step_e.bind("<Return>",   lambda _: self._replot())
        _nm_step_e.bind("<FocusOut>", lambda _: self._replot())
        _ToolTip(_nm_step_e, "nm tick step for \u03bb axis.\nLeave blank for auto.")

        _vsep(r0)
        tk.Checkbutton(r0, text="Normalise", variable=self._normalise,
                       command=self._replot, font=F9).pack(side=tk.LEFT, padx=2)
        _vsep(r0)
        tk.Checkbutton(r0, text="Grid", variable=self._show_grid,
                       command=self._replot, font=F9).pack(side=tk.LEFT, padx=2)
        _vsep(r0)
        self._bg_btn = tk.Button(r0, text="Plot BG\u2026", font=F9,
                                 bg=self._bg_colour, relief=tk.RAISED,
                                 command=self._choose_bg_colour)
        self._bg_btn.pack(side=tk.LEFT, padx=2)
        tk.Button(r0, text="Fonts\u2026", command=self._open_font_dialog,
                  font=F9).pack(side=tk.LEFT, padx=2)

        # Right side of row 0 — export/pop-out
        tk.Button(r0, text="\u29c9 Pop Out", command=self._pop_out_graph,
                  font=(F9[0], F9[1], "bold"), fg="#003399",
                  relief=tk.RAISED).pack(side=tk.RIGHT, padx=(2, 4))
        tk.Button(r0, text="Export CSV", command=self._export_csv,
                  font=F9).pack(side=tk.RIGHT, padx=2)
        tk.Button(r0, text="Save Fig", command=self._save_figure,
                  font=F9).pack(side=tk.RIGHT, padx=2)

        # ── Row 1: Axis ranges + Y-swap + ticks ──────────────────────────────────
        r1 = tk.Frame(outer, padx=4, pady=2)
        r1.pack(side=tk.TOP, fill=tk.X)

        tk.Label(r1, text="X:", font=F9).pack(side=tk.LEFT)
        _exlo = tk.Entry(r1, textvariable=self._xlim_lo, width=8, font=("Courier", 9))
        _exlo.pack(side=tk.LEFT, padx=(2, 0))
        _exlo.bind("<Return>",   lambda e: self._replot())
        _exlo.bind("<FocusOut>", lambda e: self._replot())
        tk.Label(r1, text="\u2192", font=F9).pack(side=tk.LEFT, padx=1)
        _exhi = tk.Entry(r1, textvariable=self._xlim_hi, width=8, font=("Courier", 9))
        _exhi.pack(side=tk.LEFT)
        _exhi.bind("<Return>",   lambda e: self._replot())
        _exhi.bind("<FocusOut>", lambda e: self._replot())
        tk.Button(r1, text="Auto X", font=F9, command=self._auto_x).pack(side=tk.LEFT, padx=(3, 0))

        _vsep(r1)

        tk.Label(r1, text="Y (TDDFT):", font=F9).pack(side=tk.LEFT)
        _eylo = tk.Entry(r1, textvariable=self._ylim_lo, width=7, font=("Courier", 9))
        _eylo.pack(side=tk.LEFT, padx=(2, 0))
        _eylo.bind("<Return>",   lambda e: self._replot())
        _eylo.bind("<FocusOut>", lambda e: self._replot())
        tk.Label(r1, text="\u2192", font=F9).pack(side=tk.LEFT, padx=1)
        _eyhi = tk.Entry(r1, textvariable=self._ylim_hi, width=7, font=("Courier", 9))
        _eyhi.pack(side=tk.LEFT)
        _eyhi.bind("<Return>",   lambda e: self._replot())
        _eyhi.bind("<FocusOut>", lambda e: self._replot())
        tk.Button(r1, text="Auto", font=F9, command=self._auto_y).pack(side=tk.LEFT, padx=(3, 0))

        _vsep(r1)

        tk.Label(r1, text="Y (Exp):", font=F9).pack(side=tk.LEFT)
        _eeylo = tk.Entry(r1, textvariable=self._ylim_exp_lo, width=7, font=("Courier", 9))
        _eeylo.pack(side=tk.LEFT, padx=(2, 0))
        _eeylo.bind("<Return>",   lambda e: self._replot())
        _eeylo.bind("<FocusOut>", lambda e: self._replot())
        tk.Label(r1, text="\u2192", font=F9).pack(side=tk.LEFT, padx=1)
        _eeyhi = tk.Entry(r1, textvariable=self._ylim_exp_hi, width=7, font=("Courier", 9))
        _eeyhi.pack(side=tk.LEFT)
        _eeyhi.bind("<Return>",   lambda e: self._replot())
        _eeyhi.bind("<FocusOut>", lambda e: self._replot())
        tk.Button(r1, text="Auto", font=F9,
                  command=lambda: (self._ylim_exp_lo.set(""), self._ylim_exp_hi.set(""), self._replot())
                  ).pack(side=tk.LEFT, padx=(3, 0))

        _vsep(r1)

        tk.Label(r1, text="TDDFT axis:", font=F9).pack(side=tk.LEFT)
        tk.Radiobutton(r1, text="Left", variable=self._tddft_on_left,
                       value="left",  command=self._replot, font=F9).pack(side=tk.LEFT, padx=1)
        tk.Radiobutton(r1, text="Right", variable=self._tddft_on_left,
                       value="right", command=self._replot, font=F9).pack(side=tk.LEFT, padx=1)

        _vsep(r1)

        tk.Label(r1, text="Ticks:", font=F9).pack(side=tk.LEFT)
        for val, lbl in (("in", "In"), ("out", "Out"), ("both", "Both")):
            tk.Radiobutton(r1, text=lbl, variable=self._tick_direction,
                           value=val, command=self._replot, font=F9).pack(side=tk.LEFT, padx=1)

        # ── Row 2: Axis labels ────────────────────────────────────────────────────
        r2 = tk.Frame(outer, padx=4, pady=2)
        r2.pack(side=tk.TOP, fill=tk.X)

        tk.Label(r2, text="Title:", font=F9).pack(side=tk.LEFT)
        _tle = tk.Entry(r2, textvariable=self._custom_title, font=("", 9),
                        relief=tk.SUNKEN, width=18, bg="#f8f8ff")
        _tle.pack(side=tk.LEFT, padx=(2, 0))
        _tle.bind("<Return>",   lambda _: self._replot())
        _tle.bind("<FocusOut>", lambda _: self._replot())
        tk.Button(r2, text="Auto", font=F9,
                  command=lambda: (self._custom_title.set(""), self._replot())
                  ).pack(side=tk.LEFT, padx=(2, 2))
        tk.Button(r2, text="None", font=F9,
                  command=lambda: (self._custom_title.set("\x00"), self._replot())
                  ).pack(side=tk.LEFT, padx=(0, 4))

        _vsep(r2)

        tk.Label(r2, text="X label:", font=F9).pack(side=tk.LEFT)
        _xle = tk.Entry(r2, textvariable=self._custom_x_label, font=("", 9),
                        relief=tk.SUNKEN, width=18, bg="#f8f8ff")
        _xle.pack(side=tk.LEFT, padx=(2, 0))
        _xle.bind("<Return>",   lambda _: self._replot())
        _xle.bind("<FocusOut>", lambda _: self._replot())
        tk.Button(r2, text="Auto", font=F9,
                  command=lambda: (self._custom_x_label.set(""), self._replot())
                  ).pack(side=tk.LEFT, padx=(2, 4))

        _vsep(r2)

        tk.Checkbutton(r2, text="TDDFT Y:", variable=self._show_left_ylabel,
                       command=self._replot, font=F9).pack(side=tk.LEFT)
        self._left_ylabel_entry = tk.Entry(r2, textvariable=self._custom_left_ylabel,
                                           width=16, font=("", 9), relief=tk.SUNKEN, bg="#f8f8ff")
        self._left_ylabel_entry.pack(side=tk.LEFT, padx=(2, 4))
        self._left_ylabel_entry.bind("<Return>",   lambda _: self._replot())
        self._left_ylabel_entry.bind("<FocusOut>", lambda _: self._replot())

        _vsep(r2)

        tk.Checkbutton(r2, text="Exp Y:", variable=self._show_right_ylabel,
                       command=self._replot, font=F9).pack(side=tk.LEFT)
        self._right_ylabel_entry = tk.Entry(r2, textvariable=self._custom_right_ylabel,
                                            width=16, font=("", 9), relief=tk.SUNKEN, bg="#f8f8ff")
        self._right_ylabel_entry.pack(side=tk.LEFT, padx=(2, 4))
        self._right_ylabel_entry.bind("<Return>",   lambda _: self._replot())
        self._right_ylabel_entry.bind("<FocusOut>", lambda _: self._replot())

        _vsep(r2)

        tk.Label(r2, text="\u03bb axis:", font=F9).pack(side=tk.LEFT)
        _nme = tk.Entry(r2, textvariable=self._custom_nm_label, font=("", 9),
                        relief=tk.SUNKEN, width=10, bg="#f8f8ff")
        _nme.pack(side=tk.LEFT, padx=(2, 0))
        _nme.bind("<Return>",   lambda _: self._replot())
        _nme.bind("<FocusOut>", lambda _: self._replot())

        # ── Row 3: Legend + Inset + Clear buttons ─────────────────────────────
        r3 = tk.Frame(outer, padx=4, pady=2)
        r3.pack(side=tk.TOP, fill=tk.X)

        tk.Checkbutton(r3, text="Legend", variable=self._show_legend,
                       command=self._toggle_legend, font=F9).pack(side=tk.LEFT)
        tk.Button(r3, text="Edit Labels\u2026", command=self._open_legend_editor,
                  font=F9).pack(side=tk.LEFT, padx=(4, 2))

        _vsep(r3)

        self._inset_btn = tk.Button(r3, text="+ Add Inset\u2026",
                                    font=(F9[0], F9[1], "bold"),
                                    fg="darkgreen", command=self._open_inset_dialog)
        self._inset_btn.pack(side=tk.LEFT, padx=2)
        tk.Checkbutton(r3, text="Inset labels", variable=self._inset_show_labels,
                       command=self._on_inset_labels_toggle,
                       font=F9).pack(side=tk.LEFT, padx=(2, 0))

        # Clear buttons — right-justified to mirror Save/Export on row 0
        tk.Button(r3, text="Clear Exp.", command=self._clear_exp_scans,
                  font=F9).pack(side=tk.RIGHT, padx=(2, 4))
        tk.Button(r3, text="Clear TDDFT", command=self._clear_overlays,
                  font=F9).pack(side=tk.RIGHT, padx=2)

        # ── Hidden widgets — never packed but referenced by other code paths ───────
        self._fwhm_unit_label = tk.Label(self, text="eV", width=5, anchor="w")
        self._fwhm_slider = tk.Scale(
            self, from_=0.05, to=20.0, resolution=0.05,
            orient=tk.HORIZONTAL, length=140,
            variable=self._fwhm, showvalue=False,
            command=self._on_fwhm_slider_change
        )
        self._comb_frame = None

    # ══════════════════════════════════════════════════════════════════════════
    #  Spectrum controls (row 1) — X unit + Normalise
    #  (Broadening / FWHM / ΔE / Scale / Sticks / Env / Trans are now
    #   per-spectrum settings accessed via each row's "Style…" button.)
    # ══════════════════════════════════════════════════════════════════════════
    def _build_spectrum_controls(self):
        ctrl = self._collapsible_bar("Spectrum", bd=1, relief=tk.SUNKEN, padx=4, pady=3)

        # X-axis unit
        tk.Label(ctrl, text="X axis:").pack(side=tk.LEFT)
        for unit, label in (("eV", "eV"), ("Ha", "Ha"), ("cm\u207b\u00b9", "cm\u207b\u00b9"), ("nm", "nm")):
            tk.Radiobutton(ctrl, text=label, variable=self._x_unit,
                           value=unit, command=self._on_unit_change).pack(side=tk.LEFT, padx=1)

        _sep(ctrl)

        tk.Checkbutton(ctrl, text="Normalise", variable=self._normalise,
                       command=self._replot).pack(side=tk.LEFT)

        # Hidden widgets kept so existing code paths (_on_unit_change, load_spectrum,
        # project_manager) can still call .config() / .set() without crashing.
        # They are never packed so they never appear on screen.
        self._fwhm_unit_label = tk.Label(self, text="eV", width=5, anchor="w")
        self._fwhm_slider = tk.Scale(
            self, from_=0.05, to=20.0, resolution=0.05,
            orient=tk.HORIZONTAL, length=140,
            variable=self._fwhm, showvalue=False,
            command=self._on_fwhm_slider_change
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  Alignment controls (row 2) — ΔE shift, entry unbounded, slider ±200
    # ══════════════════════════════════════════════════════════════════════════
    def _build_alignment_controls(self):
        bar = self._collapsible_bar("Alignment", bd=1, relief=tk.FLAT, padx=4, pady=2, bg="#f0f0e8")

        tk.Label(bar, text="TDDFT \u0394E shift:", font=("", 9),
                 bg="#f0f0e8").pack(side=tk.LEFT)

        self._de_entry = tk.Entry(bar, textvariable=self._delta_e_str, width=9,
                                  font=("Courier", 9))
        self._de_entry.pack(side=tk.LEFT, padx=(2, 0))
        self._de_entry.bind("<Return>",   self._on_de_entry_commit)
        self._de_entry.bind("<FocusOut>", self._on_de_entry_commit)

        tk.Label(bar, text="eV", font=("", 9), bg="#f0f0e8").pack(side=tk.LEFT, padx=(2, 4))

        self._de_slider = tk.Scale(
            bar, from_=-200.0, to=200.0, resolution=0.1,
            orient=tk.HORIZONTAL, length=200,
            variable=self._de_slider_var, showvalue=False,
            bg="#f0f0e8",
            command=self._on_de_slider_change
        )
        self._de_slider.pack(side=tk.LEFT, padx=2)

        tk.Button(bar, text="Reset \u0394E", font=("", 8), bg="#f0f0e8",
                  command=self._reset_delta_e).pack(side=tk.LEFT, padx=(4, 12))

        # ── TDDFT intensity scale ─────────────────────────────────────────────
        tk.Label(bar, text="Intensity scale:", font=("", 9),
                 bg="#f0f0e8").pack(side=tk.LEFT)

        self._scale_entry = tk.Entry(bar, textvariable=self._tddft_scale_str, width=8,
                                     font=("Courier", 9))
        self._scale_entry.pack(side=tk.LEFT, padx=(2, 0))
        self._scale_entry.bind("<Return>",   self._on_scale_entry_commit)
        self._scale_entry.bind("<FocusOut>", self._on_scale_entry_commit)

        tk.Label(bar, text="\u00d7", font=("", 10), bg="#f0f0e8").pack(
            side=tk.LEFT, padx=(2, 4))

        self._scale_slider = tk.Scale(
            bar, from_=0.01, to=5.0, resolution=0.01,
            orient=tk.HORIZONTAL, length=160,
            variable=self._scale_slider_var, showvalue=False,
            bg="#f0f0e8",
            command=self._on_scale_slider_change
        )
        self._scale_slider.pack(side=tk.LEFT, padx=2)

        tk.Button(bar, text="Reset \u00d7", font=("", 8), bg="#f0f0e8",
                  command=self._reset_scale).pack(side=tk.LEFT, padx=4)

        tk.Label(bar, text="(slider 0.01\u20135\u00d7  |  type any value for larger scale)",
                 font=("", 8), fg="gray", bg="#f0f0e8").pack(side=tk.LEFT, padx=4)

    # ══════════════════════════════════════════════════════════════════════════
    #  View-controls bar (row 3) — visibility, axis ranges, inset
    # ══════════════════════════════════════════════════════════════════════════
    def _build_view_controls(self):
        bar = self._collapsible_bar("View", collapsed=True, bd=1, relief=tk.FLAT, padx=4, pady=2, bg="#e8f0e8")

        # ── Master visibility ──────────────────────────────────────────────
        tk.Checkbutton(bar, text="Show TDDFT", variable=self._show_tddft,
                       command=self._replot, bg="#e8f0e8",
                       font=("", 9, "bold"), fg="navy").pack(side=tk.LEFT, padx=(0, 4))

        def _sep2(): tk.Frame(bar, width=1, bg="#aabbaa").pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=2)

        _sep2()

        # ── X axis range ──────────────────────────────────────────────────
        tk.Label(bar, text="X:", font=("", 9), bg="#e8f0e8").pack(side=tk.LEFT)
        ex_lo = tk.Entry(bar, textvariable=self._xlim_lo, width=8, font=("Courier", 9))
        ex_lo.pack(side=tk.LEFT, padx=(2, 0))
        ex_lo.bind("<Return>",   lambda e: self._replot())
        ex_lo.bind("<FocusOut>", lambda e: self._replot())
        tk.Label(bar, text="→", bg="#e8f0e8").pack(side=tk.LEFT, padx=1)
        ex_hi = tk.Entry(bar, textvariable=self._xlim_hi, width=8, font=("Courier", 9))
        ex_hi.pack(side=tk.LEFT)
        ex_hi.bind("<Return>",   lambda e: self._replot())
        ex_hi.bind("<FocusOut>", lambda e: self._replot())
        tk.Button(bar, text="Auto X", font=("", 8), bg="#e8f0e8",
                  command=self._auto_x).pack(side=tk.LEFT, padx=(2, 0))

        _sep2()

        # ── Y axis range (right / TDDFT) ──────────────────────────────────
        tk.Label(bar, text="Y right (TDDFT):", font=("", 9), bg="#e8f0e8").pack(side=tk.LEFT)
        ey_lo = tk.Entry(bar, textvariable=self._ylim_lo, width=7, font=("Courier", 9))
        ey_lo.pack(side=tk.LEFT, padx=(2, 0))
        ey_lo.bind("<Return>",   lambda e: self._replot())
        ey_lo.bind("<FocusOut>", lambda e: self._replot())
        tk.Label(bar, text="→", bg="#e8f0e8").pack(side=tk.LEFT, padx=1)
        ey_hi = tk.Entry(bar, textvariable=self._ylim_hi, width=7, font=("Courier", 9))
        ey_hi.pack(side=tk.LEFT)
        ey_hi.bind("<Return>",   lambda e: self._replot())
        ey_hi.bind("<FocusOut>", lambda e: self._replot())
        tk.Button(bar, text="Auto Y right", font=("", 8), bg="#e8f0e8",
                  command=self._auto_y).pack(side=tk.LEFT, padx=(2, 0))

        _sep2()

        # ── Inset ─────────────────────────────────────────────────────────
        tk.Label(bar, text="Y left (Exp):", font=("", 9), bg="#e8f0e8").pack(side=tk.LEFT)
        ey2_lo = tk.Entry(bar, textvariable=self._yleft_lo, width=7, font=("Courier", 9))
        ey2_lo.pack(side=tk.LEFT, padx=(2, 0))
        ey2_lo.bind("<Return>",   lambda e: self._replot())
        ey2_lo.bind("<FocusOut>", lambda e: self._replot())
        tk.Label(bar, text="→", bg="#e8f0e8").pack(side=tk.LEFT, padx=1)
        ey2_hi = tk.Entry(bar, textvariable=self._yleft_hi, width=7, font=("Courier", 9))
        ey2_hi.pack(side=tk.LEFT)
        ey2_hi.bind("<Return>",   lambda e: self._replot())
        ey2_hi.bind("<FocusOut>", lambda e: self._replot())
        tk.Button(bar, text="Auto Y left", font=("", 8), bg="#e8f0e8",
                  command=self._auto_y_left).pack(side=tk.LEFT, padx=(2, 0))

        _sep2()

        self._inset_btn = tk.Button(
            bar, text="+ Add Inset\u2026", font=("", 8, "bold"), bg="#e8f0e8",
            fg="darkgreen", command=self._open_inset_dialog)
        self._inset_btn.pack(side=tk.LEFT, padx=2)
        tk.Checkbutton(bar, text="Axis labels", variable=self._inset_show_labels,
                       command=self._on_inset_labels_toggle,
                       bg="#e8f0e8", font=("", 8)).pack(side=tk.LEFT, padx=(2, 0))


    def _auto_x(self):
        self._xlim_lo.set("")
        self._xlim_hi.set("")
        self._replot()

    def _auto_y(self):
        self._ylim_lo.set("")
        self._ylim_hi.set("")
        self._replot()

    def _auto_y_left(self):
        self._yleft_lo.set("")
        self._yleft_hi.set("")
        self._replot()

    def _on_inset_labels_toggle(self):
        if self._inset_active and self._inset_ax is not None:
            self._quick_move_inset()
        # No-op if inset not yet shown

    # ── ΔE handlers ──────────────────────────────────────────────────────────

    def _on_de_slider_change(self, val):
        """Slider moved → update actual delta_e and entry display."""
        v = float(val)
        self._delta_e.set(v)
        self._delta_e_str.set(f"{v:+.2f}")
        self._replot()

    def _on_de_entry_commit(self, event=None):
        """Entry committed → update delta_e (unbounded) and nudge slider."""
        raw = self._delta_e_str.get().strip()
        try:
            val = float(raw)
        except ValueError:
            self._delta_e_str.set(f"{self._delta_e.get():+.2f}")
            return
        # Store actual (unbounded) value
        self._delta_e.set(val)
        self._delta_e_str.set(f"{val:+.2f}")
        # Move slider to clamped representation for visual feedback
        self._de_slider_var.set(max(-200.0, min(200.0, val)))
        self._replot()

    def _reset_delta_e(self):
        self._delta_e.set(0.0)
        self._delta_e_str.set("+0.00")
        self._de_slider_var.set(0.0)
        self._replot()

    # ── Intensity scale handlers ──────────────────────────────────────────────

    def _on_scale_slider_change(self, val):
        v = float(val)
        self._tddft_scale.set(v)
        self._tddft_scale_str.set(f"{v:.3f}")
        self._replot()

    def _on_scale_entry_commit(self, event=None):
        raw = self._tddft_scale_str.get().strip()
        try:
            val = float(raw)
            if val <= 0:
                raise ValueError
        except ValueError:
            self._tddft_scale_str.set(f"{self._tddft_scale.get():.3f}")
            return
        self._tddft_scale.set(val)
        self._tddft_scale_str.set(f"{val:.3f}")
        # Move slider to clamped position for visual feedback
        self._scale_slider_var.set(max(0.01, min(5.0, val)))
        self._replot()

    def _reset_scale(self):
        self._tddft_scale.set(1.0)
        self._tddft_scale_str.set("1.000")
        self._scale_slider_var.set(1.0)
        self._replot()

    # ── Background colour ─────────────────────────────────────────────────────

    def _choose_bg_colour(self):
        from tkinter import colorchooser
        result = colorchooser.askcolor(color=self._bg_colour,
                                       title="Choose plot background colour")
        if result and result[1]:
            self._bg_colour = result[1]
            # Keep button face in sync so it acts as a swatch
            try:
                self._bg_btn.config(bg=self._bg_colour)
            except Exception:
                pass
            self._replot()

    # ══════════════════════════════════════════════════════════════════════════
    #  Axes & Labels (title, X/Y labels, tick direction)
    # ══════════════════════════════════════════════════════════════════════════
    def _build_axes_controls(self):
        bg = "#e8e8f8"
        bar = self._collapsible_bar("Axes & Labels", collapsed=True, padx=4, pady=2, bg=bg)

        def _sep3(): tk.Frame(bar, width=1, bg="#9999bb").pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=2)

        # ── Plot title ────────────────────────────────────────────────────
        tk.Label(bar, text="Title:", font=("", 9), bg=bg).pack(side=tk.LEFT)
        title_entry = tk.Entry(bar, textvariable=self._custom_title,
                               font=("", 9), relief=tk.SUNKEN, width=22, bg="#f8f8ff")
        title_entry.pack(side=tk.LEFT, padx=(2, 0))
        title_entry.bind("<Return>",   lambda _: self._replot())
        title_entry.bind("<FocusOut>", lambda _: self._replot())
        tk.Button(bar, text="Auto", font=("", 8), bg=bg,
                  command=self._reset_title).pack(side=tk.LEFT, padx=(2, 0))
        _ToolTip(title_entry, "Custom plot title.\nLeave blank for auto title.")

        _sep3()

        # ── X axis label ─────────────────────────────────────────────────
        tk.Label(bar, text="X label:", font=("", 9), bg=bg).pack(side=tk.LEFT)
        xl_entry = tk.Entry(bar, textvariable=self._custom_x_label,
                            font=("", 9), relief=tk.SUNKEN, width=18, bg="#f8f8ff")
        xl_entry.pack(side=tk.LEFT, padx=(2, 0))
        xl_entry.bind("<Return>",   lambda _: self._replot())
        xl_entry.bind("<FocusOut>", lambda _: self._replot())
        tk.Button(bar, text="Auto", font=("", 8), bg=bg,
                  command=lambda: (self._custom_x_label.set(""), self._replot())
                  ).pack(side=tk.LEFT, padx=(2, 0))
        _ToolTip(xl_entry, "Custom X-axis label.\nLeave blank to use the auto label from the unit selection.")

        _sep3()

        # ── Left Y label ─────────────────────────────────────────────────
        tk.Checkbutton(bar, text="TDDFT Y:", variable=self._show_left_ylabel,
                       command=self._replot, bg=bg, font=("", 9)).pack(side=tk.LEFT)
        self._left_ylabel_entry = tk.Entry(
            bar, textvariable=self._custom_left_ylabel,
            width=16, font=("", 8), relief=tk.SUNKEN, bg="#f8f8ff")
        self._left_ylabel_entry.pack(side=tk.LEFT, padx=(2, 4))
        self._left_ylabel_entry.bind("<Return>",   lambda _: self._replot())
        self._left_ylabel_entry.bind("<FocusOut>", lambda _: self._replot())
        _ToolTip(self._left_ylabel_entry,
                 "Custom TDDFT (left) Y-axis label.\nLeave blank to use the auto label.")

        # ── Right Y label ────────────────────────────────────────────────
        tk.Checkbutton(bar, text="Exp. Y:", variable=self._show_right_ylabel,
                       command=self._replot, bg=bg, font=("", 9)).pack(side=tk.LEFT)
        self._right_ylabel_entry = tk.Entry(
            bar, textvariable=self._custom_right_ylabel,
            width=16, font=("", 8), relief=tk.SUNKEN, bg="#f8f8ff")
        self._right_ylabel_entry.pack(side=tk.LEFT, padx=(2, 0))
        self._right_ylabel_entry.bind("<Return>",   lambda _: self._replot())
        self._right_ylabel_entry.bind("<FocusOut>", lambda _: self._replot())
        _ToolTip(self._right_ylabel_entry,
                 "Custom Exp. (right) Y-axis label.\nLeave blank to use the auto label.")

        _sep3()

        # ── Tick direction ────────────────────────────────────────────────
        tk.Label(bar, text="Ticks:", font=("", 9), bg=bg).pack(side=tk.LEFT)
        for val, lbl in (("out", "Out"), ("in", "In"), ("both", "Both")):
            tk.Radiobutton(bar, text=lbl, variable=self._tick_direction,
                           value=val, command=self._replot,
                           bg=bg, font=("", 9)).pack(side=tk.LEFT, padx=1)

    # ══════════════════════════════════════════════════════════════════════════
    #  Style (grid, background, TDDFT style, fonts)
    # ══════════════════════════════════════════════════════════════════════════
    def _build_style_controls(self):
        bar = self._collapsible_bar("Style", collapsed=True, padx=4, pady=3)

        tk.Checkbutton(bar, text="Grid", variable=self._show_grid,
                       command=self._replot).pack(side=tk.LEFT)

        self._bg_btn = tk.Button(
            bar, text="Plot BG\u2026", font=("", 8),
            bg=self._bg_colour, relief=tk.RAISED,
            command=self._choose_bg_colour
        )
        self._bg_btn.pack(side=tk.LEFT, padx=(4, 0))

        _sep(bar)

        tk.Button(bar, text="TDDFT Style\u2026", command=self._open_tddft_style_dialog,
                  font=("", 8)).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="Fonts\u2026", command=self._open_font_dialog,
                  font=("", 8)).pack(side=tk.LEFT, padx=2)

    # ══════════════════════════════════════════════════════════════════════════
    #  Legend & Export
    # ══════════════════════════════════════════════════════════════════════════
    def _build_legend_export_controls(self):
        bar = self._collapsible_bar("Legend & Export", collapsed=True, padx=4, pady=3)

        tk.Checkbutton(bar, text="Legend", variable=self._show_legend,
                       command=self._toggle_legend).pack(side=tk.LEFT)
        tk.Checkbutton(bar, text="TDDFT", variable=self._show_tddft_in_legend,
                       command=self._replot,
                       font=("", 8), fg="navy").pack(side=tk.LEFT, padx=(0, 2))
        tk.Button(bar, text="Edit Labels\u2026", command=self._open_legend_editor,
                  font=("", 8)).pack(side=tk.LEFT, padx=(2, 0))

        _sep(bar)

        tk.Button(bar, text="Save Fig",   command=self._save_figure,
                  font=("", 8)).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="Export CSV", command=self._export_csv,
                  font=("", 8)).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="\u29c9 Pop Out", command=self._pop_out_graph,
                  font=("", 8, "bold"), fg="#003399",
                  relief=tk.RAISED).pack(side=tk.LEFT, padx=(2, 4))

    # ══════════════════════════════════════════════════════════════════════════
    #  Overlay controls (overlay mode + combined-spectrum components)
    # ══════════════════════════════════════════════════════════════════════════
    def _build_overlay_controls(self):
        bg = "#e8f0f8"
        bar = self._collapsible_bar("Overlay", collapsed=True, padx=4, pady=3, bg=bg)

        # Component toggles moved to per-spectrum detail panel — nothing here now.
        self._comb_frame = None

    def _reset_title(self):
        self._custom_title.set("")
        self._replot()

    def _auto_title(self) -> str:
        n_tddft = sum(1 for e in self._tddft_spectra if e["enabled"].get())
        n_exp   = sum(1 for _, _, v, _, _ in self._exp_scans if v.get())
        if n_tddft > 1:
            parts = [f"{n_tddft} TDDFT"]
            if n_exp:
                parts.append(f"{n_exp} Exp.")
            return "Overlay: " + ", ".join(parts)
        elif n_tddft == 1:
            entry = next(e for e in self._tddft_spectra if e["enabled"].get())
            sp    = entry["spectrum"]
            base  = getattr(sp, "_custom_label", None) or sp.display_name()
            return (f"{base} + {n_exp} Exp. scan{'s' if n_exp > 1 else ''}"
                    if n_exp else base)
        elif n_exp:
            return f"Experimental scan{'s' if n_exp > 1 else ''}"
        return ""

    # ── FWHM two-way binding ──────────────────────────────────────────────────

    def _on_fwhm_slider_change(self, val):
        fwhm = float(val)
        unit = self._x_unit.get()
        if unit == "cm\u207b\u00b9":
            self._fwhm_str.set(f"{fwhm:.0f}")
        elif unit == "Ha":
            self._fwhm_str.set(f"{fwhm:.4f}")
        else:
            self._fwhm_str.set(f"{fwhm:.2f}")
        self._replot()

    def _on_fwhm_entry_commit(self, event=None):
        raw = self._fwhm_str.get().strip()
        try:
            val = float(raw)
        except ValueError:
            self._sync_fwhm_entry()
            return
        lo = self._fwhm_slider.cget("from")
        hi = self._fwhm_slider.cget("to")
        val = max(lo, min(hi, val))
        self._fwhm.set(val)
        self._sync_fwhm_entry()
        self._replot()

    def _sync_fwhm_entry(self):
        fwhm = self._fwhm.get()
        unit = self._x_unit.get()
        if unit == "cm\u207b\u00b9":
            self._fwhm_str.set(f"{fwhm:.0f}")
        elif unit == "Ha":
            self._fwhm_str.set(f"{fwhm:.4f}")
        else:
            self._fwhm_str.set(f"{fwhm:.2f}")

    # ------------------------------------------------------------------
    #  X-limit conversion when the energy unit is switched
    # ------------------------------------------------------------------
    def _convert_xlims(self, old_unit: str, new_unit: str):
        """Convert stored x-axis limit strings from old_unit to new_unit.

        Empty strings (auto) are left untouched.  nm is special because the
        axis is inverted (higher energy = lower nm), so lo↔hi are swapped.
        """
        def _to_ev(val: float, unit: str) -> float:
            if unit == "eV":
                return val
            if unit == "Ha":
                return val * self._HA_TO_EV
            if unit == "cm\u207b\u00b9":
                return val / self._EV_TO_CM
            if unit == "nm":
                return 1239.84 / val   # photon energy in eV
            return val

        def _from_ev(val_ev: float, unit: str) -> float:
            if unit == "eV":
                return val_ev
            if unit == "Ha":
                return val_ev / self._HA_TO_EV
            if unit == "cm\u207b\u00b9":
                return val_ev * self._EV_TO_CM
            if unit == "nm":
                return 1239.84 / val_ev
            return val_ev

        lo_str = self._xlim_lo.get().strip()
        hi_str = self._xlim_hi.get().strip()

        if not lo_str and not hi_str:
            return   # both auto — nothing to do

        try:
            lo_ev = _to_ev(float(lo_str), old_unit) if lo_str else None
            hi_ev = _to_ev(float(hi_str), old_unit) if hi_str else None
        except ValueError:
            return   # unparseable — leave as-is

        def _fmt(v, unit):
            if unit == "cm\u207b\u00b9":
                return f"{v:.0f}"
            if unit == "Ha":
                return f"{v:.6f}"
            if unit == "nm":
                return f"{v:.1f}"
            return f"{v:.4f}"

        if new_unit == "nm":
            # nm axis is inverted: small eV → large nm.
            # What was the "low" energy bound becomes the "high" nm bound.
            new_lo = _from_ev(hi_ev, "nm") if hi_ev is not None else ""
            new_hi = _from_ev(lo_ev, "nm") if lo_ev is not None else ""
        elif old_unit == "nm":
            # Coming from nm: invert the swap.
            # lo_nm corresponds to high energy; hi_nm to low energy.
            new_lo = _from_ev(hi_ev, new_unit) if hi_ev is not None else ""
            new_hi = _from_ev(lo_ev, new_unit) if lo_ev is not None else ""
        else:
            new_lo = _from_ev(lo_ev, new_unit) if lo_ev is not None else ""
            new_hi = _from_ev(hi_ev, new_unit) if hi_ev is not None else ""

        self._xlim_lo.set(_fmt(new_lo, new_unit) if new_lo != "" else "")
        self._xlim_hi.set(_fmt(new_hi, new_unit) if new_hi != "" else "")

    def _on_unit_change(self):
        unit     = self._x_unit.get()
        old_unit = self._prev_x_unit

        # Convert any stored x-axis limits from the previous unit to the new one
        self._convert_xlims(old_unit, unit)

        # ── Convert all stored FWHM values from old unit to new unit ──────────
        # Global FWHM
        new_global_fwhm = self._convert_fwhm_value(self._fwhm.get(), old_unit, unit)

        # Per-spectrum FWHM values
        for e in self._tddft_spectra:
            converted = self._convert_fwhm_value(e["fwhm"].get(), old_unit, unit)
            e["fwhm"].set(round(converted, 6))

        # ── Update global FWHM slider bounds for the new unit ─────────────────
        lo, hi, res = self._fwhm_slider_range(unit)
        fwhm_unit_label = (
            "cm\u207b\u00b9" if unit in ("cm\u207b\u00b9", "nm") else
            "Ha"              if unit == "Ha" else
            "eV"
        )
        self._fwhm_unit_label.config(text=fwhm_unit_label)
        self._fwhm_slider.config(from_=lo, to=hi, resolution=res)

        # Clamp converted value to the new slider range and apply
        self._fwhm.set(max(lo, min(hi, new_global_fwhm)))
        self._sync_fwhm_entry()
        self._prev_x_unit = unit
        self._update_nm_axis_btn_state()
        self._replot()

    # ──────────────────────────────────────────────────────────────────────────
    #  Secondary nm-axis helpers
    # ──────────────────────────────────────────────────────────────────────────
    def _update_nm_axis_btn_state(self):
        """Enable the λ(nm) checkbox only when the X-axis is in cm⁻¹."""
        if self._nm_axis_cb is None:
            return
        is_cm = self._x_unit.get() == "cm\u207b\u00b9"
        self._nm_axis_cb.config(state=tk.NORMAL if is_cm else tk.DISABLED)
        if not is_cm:
            self._show_nm_axis.set(False)

    def _draw_secondary_nm_axis(self, ax) -> None:
        """Add a secondary x-axis on top showing wavelength in nm (cm⁻¹ mode only)."""
        import math

        def _cm_to_nm(x):
            arr = np.asarray(x, dtype=float)
            with np.errstate(divide="ignore", invalid="ignore"):
                # Clamp to ≥ 0.1 cm⁻¹ so the transform never returns NaN.
                # At secondary-axis creation time matplotlib calls this with
                # its default xlim (0, 1) — a NaN result there breaks minor-
                # tick computation and silently kills the axis render.
                return 1e7 / np.maximum(arr, 0.1)

        cm_lo_raw, cm_hi_raw = ax.get_xlim()
        cm_lo = min(cm_lo_raw, cm_hi_raw)
        cm_hi = max(cm_lo_raw, cm_hi_raw)
        if cm_hi <= 0:
            return  # entire visible range is non-physical

        # Create secondary axis — same function both ways (self-inverse transform)
        ax_top = ax.secondary_xaxis("top", functions=(_cm_to_nm, _cm_to_nm))

        # Determine nm range for tick selection.
        # Use actual positive xlim values; if cm_lo ≤ 0 (autoscale margin),
        # clamp to a fraction of cm_hi so we don't compute absurdly large nm.
        cm_lo_pos = max(cm_lo, cm_hi * 0.01)
        nm_hi = 1e7 / cm_lo_pos
        nm_lo = 1e7 / cm_hi
        if nm_hi <= nm_lo:
            return

        # Manual step overrides auto-select
        _manual = None
        try:
            _v = float(self._nm_step.get().strip())
            if _v > 0:
                _manual = _v
        except (ValueError, AttributeError):
            pass

        if _manual is not None:
            chosen_step = _manual
        else:
            # Geometric candidate list — works across UV, Vis, near-IR ranges
            candidates = [
                5, 10, 20, 25, 50, 100, 200, 250, 500,
                1000, 2000, 2500, 5000, 10000, 25000, 50000
            ]
            chosen_step = candidates[-1]
            for step in candidates:
                first = math.ceil(nm_lo / step) * step
                last  = math.floor(nm_hi / step) * step
                count = (int(round((last - first) / step)) + 1
                         if last >= first else 0)
                if 4 <= count <= 12:
                    chosen_step = step
                    break

        first_tick = math.ceil(nm_lo / chosen_step) * chosen_step
        last_tick  = math.floor(nm_hi / chosen_step) * chosen_step
        if first_tick > last_tick:
            return

        tick_nm = np.arange(first_tick, last_tick + 0.5 * chosen_step, chosen_step)
        tick_nm = tick_nm[(tick_nm >= nm_lo) & (tick_nm <= nm_hi)]
        if len(tick_nm) == 0:
            return

        # Set ticks in nm space — secondary_xaxis applies the inverse to place them
        ax_top.set_xticks(tick_nm)
        ax_top.set_xticklabels([str(int(t)) for t in tick_nm])

        _nm_lbl = self._custom_nm_label.get().strip()
        if _nm_lbl:
            ax_top.set_xlabel(
                _nm_lbl,
                fontsize=self._font_xlabel_size.get(),
                fontweight="bold" if self._font_xlabel_bold.get() else "normal",
            )
        else:
            ax_top.set_xlabel("")

        ax_top.tick_params(
            axis="x", which="both",
            direction=self._tick_direction.get(),
            labelsize=self._font_tick_size.get(),
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  Figure — ax and ax2 created ONCE; never destroyed (fixes toolbar zoom)
    # ══════════════════════════════════════════════════════════════════════════
    def _build_figure(self):
        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.ax  = self.fig.add_subplot(111)
        self.ax2 = None   # created on demand in _replot; never persistent

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        tb_frame = tk.Frame(self)
        tb_frame.pack(side=tk.TOP, fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, tb_frame)
        self.toolbar.update()

    # ax2 is created fresh in _replot when experimental scans are present,
    # and set to None otherwise. No hide/show helpers are needed.

    # ══════════════════════════════════════════════════════════════════════════
    #  Overlay panel
    # ══════════════════════════════════════════════════════════════════════════
    def _build_overlay_panel(self):
        self._overlay_panel = tk.Frame(self, bd=1, relief=tk.RIDGE, padx=4, pady=2)
        # Not packed yet — _update_overlay_panel_visibility() handles show/hide

        container = tk.Frame(self._overlay_panel)
        container.pack(fill=tk.BOTH, expand=True)

        self._ov_canvas = tk.Canvas(container, height=26, bd=0, highlightthickness=0)
        ov_scroll = ttk.Scrollbar(container, orient=tk.VERTICAL,
                                  command=self._ov_canvas.yview)
        self._ov_inner = tk.Frame(self._ov_canvas)
        self._ov_inner.bind(
            "<Configure>",
            lambda e: self._ov_canvas.configure(
                scrollregion=self._ov_canvas.bbox("all"))
        )
        self._ov_win_id = self._ov_canvas.create_window(
            (0, 0), window=self._ov_inner, anchor="nw")
        # Stretch inner frame to fill canvas width whenever the panel resizes
        self._ov_canvas.bind(
            "<Configure>",
            lambda e: self._ov_canvas.itemconfig(self._ov_win_id, width=e.width))
        self._ov_canvas.configure(yscrollcommand=ov_scroll.set)
        self._ov_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ov_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _make_panel_row(self, parent, label, var, colour, remove_cmd,
                        style_cmd=None, color_cmd=None, type_label=None,
                        legend_var=None):
        """Create a single checkbox row in the Data panel.

        legend_var: if provided, a BooleanVar that controls whether this
        spectrum appears in the plot legend.  Shown as a small ✓/– toggle.
        """
        row = tk.Frame(parent)
        row.pack(fill=tk.X, anchor="w")

        _tag = type_label or ""
        if color_cmd:
            swatch = tk.Button(row, bg=colour, relief=tk.RAISED,
                               cursor="hand2", command=color_cmd,
                               activebackground=colour,
                               text=_tag, fg="white", font=("", 7, "bold"),
                               width=5, pady=0)
            swatch.pack(side=tk.LEFT, padx=(2, 0))
            _ToolTip(swatch, "Click to change colour")
        else:
            tk.Label(row, bg=colour, relief=tk.RAISED,
                     text=_tag, fg="white", font=("", 7, "bold"),
                     width=5).pack(side=tk.LEFT, padx=(2, 0))

        tk.Checkbutton(
            row, text=label, variable=var, command=self._replot,
            anchor="w", font=("", 8), wraplength=200, justify=tk.LEFT
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Legend toggle — small button, toggles BooleanVar on click
        if legend_var is not None:
            def _toggle_legend(_v=legend_var, _r=row):
                _v.set(not _v.get())
                _update_legend_btn()
                self._replot()

            _leg_btn = tk.Button(row, width=2, font=("", 8), relief=tk.FLAT,
                                 command=_toggle_legend)

            def _update_legend_btn(_v=legend_var, _b=_leg_btn):
                _b.config(text="\u2713" if _v.get() else "\u2013",
                          fg="#006600" if _v.get() else "#999999")

            _update_legend_btn()
            _leg_btn.pack(side=tk.RIGHT, padx=(1, 0))
            _ToolTip(_leg_btn, "Toggle legend entry")

        if style_cmd:
            tk.Button(row, text="Style\u2026", width=5, font=("", 7),
                      relief=tk.FLAT, command=style_cmd).pack(side=tk.RIGHT, padx=1)
        tk.Button(row, text="\u2715", width=2, font=("", 7), relief=tk.FLAT,
                  command=remove_cmd).pack(side=tk.RIGHT, padx=2)


    def _refresh_panel_content(self):
        """Rebuild the data panel as a unified grid table — TDDFT and EXP share columns."""
        for w in self._ov_inner.winfo_children():
            w.destroy()

        have_rows = bool(self._tddft_spectra) or bool(self._exp_scans)
        if not have_rows:
            self._ov_canvas.configure(height=26)
            self._update_overlay_panel_visibility()
            return

        # ── Unified column layout ─────────────────────────────────────────────
        # 0  : color swatch (T/E indicator)
        # 1  : ☐ Label  (expands)
        # 2  : Lgd toggle
        # 3  : Line/Env style  OptionMenu   — envelope linestyle (TDDFT) / linestyle (EXP)
        # 4  : LW entry                     — envelope linewidth (TDDFT) / linewidth (EXP)
        # 5  : ☐ Env  (TDDFT only; blank for EXP)
        # 6  : ☐ Stk  (TDDFT only; blank for EXP)
        # 7  : ☐ Trans (TDDFT only; blank for EXP)
        # 8  : Style… button
        # 9  : ✕ remove

        tbl = tk.Frame(self._ov_inner)
        tbl.pack(fill=tk.X, expand=True, padx=2)
        # Label column expands; give the fixed columns a consistent minimum width
        tbl.columnconfigure(1, weight=1, minsize=280)
        tbl.columnconfigure(0, minsize=46)
        for _c in (2, 3, 4, 5, 6, 7, 8, 9):
            tbl.columnconfigure(_c, minsize=30)

        HDR_BG = "#e8e8e8"
        # Inter-column padding — horizontal only; rows stay tight (pady=0)
        CPX = (5, 5)   # standard cell padx
        SPX = (4, 2)   # swatch (col 0)
        RPX = (4, 6)   # remove button (col 9)

        F8  = ("", 8)
        F9  = ("", 9)
        FHD = ("", 8, "bold")

        # ── Header row ────────────────────────────────────────────────────────
        hdr_specs = [
            (0, "",       "center", SPX),
            (1, "Label",  "w",      (6, 4)),
            (2, "Lgd",    "center", CPX),
            (3, "Style",  "center", CPX),
            (4, "LW",     "center", CPX),
            (5, "Env",    "center", CPX),
            (6, "Stk",    "center", CPX),
            (7, "Trans",  "center", CPX),
            (8, "",       "center", CPX),
            (9, "",       "center", RPX),
        ]
        for col, txt, anch, px in hdr_specs:
            tk.Label(tbl, text=txt, font=FHD, bg=HDR_BG, fg="#444444",
                     anchor=anch, padx=4
                     ).grid(row=0, column=col, sticky="ew", ipady=1, padx=px)

        # ── Helper: legend toggle button ──────────────────────────────────────
        def _make_leg_btn(parent, legend_var, grid_row, grid_col):
            b = tk.Button(parent, width=2, font=F9, relief=tk.FLAT)
            def _refresh_btn(_b=b, _v=legend_var):
                _b.config(text="\u2713" if _v.get() else "\u2013",
                          fg="#006600" if _v.get() else "#999999")
            def _toggle(_b=b, _v=legend_var):
                _v.set(not _v.get())
                _refresh_btn()
                self._replot()
            b.config(command=_toggle)
            _refresh_btn()
            b.grid(row=grid_row, column=grid_col, padx=CPX, pady=0, sticky="ew")
            return b

        # ── Helper: linestyle OptionMenu ──────────────────────────────────────
        def _make_ls_menu(parent, ls_var, grid_row, grid_col):
            om = tk.OptionMenu(parent, ls_var, "solid", "dashed", "dotted", "dashdot")
            om.config(font=F8, width=7, pady=0, highlightthickness=0)
            om["menu"].config(font=F8)
            om.grid(row=grid_row, column=grid_col, padx=CPX, pady=0, sticky="ew")
            return om

        # ── Helper: linewidth entry ────────────────────────────────────────────
        def _make_lw_entry(parent, lw_var, grid_row, grid_col):
            e = tk.Entry(parent, textvariable=lw_var, width=4,
                         font=("Courier", 8), justify="center")
            e.grid(row=grid_row, column=grid_col, padx=CPX, pady=0, sticky="ew")
            return e

        # ── TDDFT rows ────────────────────────────────────────────────────────
        for i, entry in enumerate(self._tddft_spectra):
            colour = entry["color"] or OVERLAY_COLOURS[i % len(OVERLAY_COLOURS)]
            r = i + 1   # row 0 = header

            # Col 0: swatch
            tk.Button(tbl, bg=colour, relief=tk.RAISED, width=4,
                      text="TDD", fg="white", font=("", 7, "bold"),
                      activebackground=colour, cursor="hand2",
                      command=lambda idx=i: self._pick_tddft_colour(idx)
                      ).grid(row=r, column=0, padx=SPX, pady=0, sticky="w")

            # Col 1: enable + label
            tk.Checkbutton(tbl, text=entry["label"], variable=entry["enabled"],
                           command=self._replot, anchor="w", font=F9,
                           wraplength=300, justify=tk.LEFT
                           ).grid(row=r, column=1, sticky="ew", padx=(6, 4), pady=0)

            # Col 2: legend toggle
            _make_leg_btn(tbl, entry["in_legend"], r, 2)

            # Col 3: envelope linestyle
            _st = entry["style"]
            _ls_v = tk.StringVar(value=_st.get("env_linestyle", "solid"))
            def _tddft_ls_cb(s, v, *_):
                s["env_linestyle"] = v.get()
                self._replot()
            _ls_v.trace_add("write", lambda *_, s=_st, v=_ls_v: _tddft_ls_cb(s, v))
            _make_ls_menu(tbl, _ls_v, r, 3)

            # Col 4: envelope linewidth
            _lw_v = tk.DoubleVar(value=_st.get("env_linewidth", 2.0))
            def _tddft_lw_cb(s, v, *_):
                try:
                    s["env_linewidth"] = float(v.get())
                    self._replot()
                except Exception:
                    pass
            _lw_v.trace_add("write", lambda *_, s=_st, v=_lw_v: _tddft_lw_cb(s, v))
            _make_lw_entry(tbl, _lw_v, r, 4)

            # Col 5: Env toggle
            tk.Checkbutton(tbl, text="", variable=entry["show_env"],
                           command=self._replot
                           ).grid(row=r, column=5, padx=CPX, pady=0, sticky="ew")

            # Col 6: Stk toggle
            tk.Checkbutton(tbl, text="", variable=entry["show_sticks"],
                           command=self._replot
                           ).grid(row=r, column=6, padx=CPX, pady=0, sticky="ew")

            # Col 7: Trans toggle
            tk.Checkbutton(tbl, text="", variable=entry["show_trans"],
                           command=self._replot
                           ).grid(row=r, column=7, padx=CPX, pady=0, sticky="ew")

            # Col 8: Style…
            tk.Button(tbl, text="Style\u2026", font=F8, relief=tk.FLAT,
                      command=lambda idx=i: self._open_tddft_spectrum_style_dialog(idx)
                      ).grid(row=r, column=8, padx=CPX, pady=0, sticky="ew")

            # Col 9: ✕
            tk.Button(tbl, text="\u2715", font=F8, relief=tk.FLAT,
                      command=lambda idx=i: self._remove_tddft_idx(idx)
                      ).grid(row=r, column=9, padx=RPX, pady=0, sticky="e")

        # ── EXP rows ─────────────────────────────────────────────────────────
        offset = len(self._tddft_spectra) + 1   # +1 for header row
        for i, (label, scan, var, style, in_legend) in enumerate(self._exp_scans):
            colour = style.get("color") or EXP_COLOURS[i % len(EXP_COLOURS)]
            r = offset + i

            # Col 0: swatch
            tk.Button(tbl, bg=colour, relief=tk.RAISED, width=4,
                      text="EXP", fg="white", font=("", 7, "bold"),
                      activebackground=colour, cursor="hand2",
                      command=lambda idx=i: self._pick_exp_colour(idx)
                      ).grid(row=r, column=0, padx=SPX, pady=0, sticky="w")

            # Col 1: enable + label
            tk.Checkbutton(tbl, text=label, variable=var,
                           command=self._replot, anchor="w", font=F9,
                           wraplength=300, justify=tk.LEFT
                           ).grid(row=r, column=1, sticky="ew", padx=(6, 4), pady=0)

            # Col 2: legend toggle
            _make_leg_btn(tbl, in_legend, r, 2)

            # Col 3: linestyle
            _ls_v = tk.StringVar(value=style.get("linestyle", "solid"))
            def _exp_ls_cb(s, v, *_):
                s["linestyle"] = v.get()
                self._replot()
            _ls_v.trace_add("write", lambda *_, s=style, v=_ls_v: _exp_ls_cb(s, v))
            _make_ls_menu(tbl, _ls_v, r, 3)

            # Col 4: linewidth
            _lw_v = tk.DoubleVar(value=style.get("linewidth", 1.8))
            def _exp_lw_cb(s, v, *_):
                try:
                    s["linewidth"] = float(v.get())
                    self._replot()
                except Exception:
                    pass
            _lw_v.trace_add("write", lambda *_, s=style, v=_lw_v: _exp_lw_cb(s, v))
            _make_lw_entry(tbl, _lw_v, r, 4)

            # Cols 5-7: blank (TDDFT-only toggles)
            for _bc in (5, 6, 7):
                tk.Label(tbl, text="").grid(row=r, column=_bc, padx=CPX, pady=0)

            # Col 8: Style…
            tk.Button(tbl, text="Style\u2026", font=F8, relief=tk.FLAT,
                      command=lambda idx=i: self._open_exp_style_dialog(idx)
                      ).grid(row=r, column=8, padx=CPX, pady=0, sticky="ew")

            # Col 9: ✕
            tk.Button(tbl, text="\u2715", font=F8, relief=tk.FLAT,
                      command=lambda idx=i: self._remove_exp_scan_idx(idx)
                      ).grid(row=r, column=9, padx=RPX, pady=0, sticky="e")

        self._ov_inner.update_idletasks()
        self._ov_canvas.configure(scrollregion=self._ov_canvas.bbox("all"))
        # ── Dynamic canvas height ──────────────────────────────────────────────
        # Measure actual required height after layout, then clamp to ~6 rows max.
        # This makes the panel collapse when few items are loaded and grow as
        # more are added, without ever exceeding the 6-row threshold.
        actual_h = self._ov_inner.winfo_reqheight()
        _MAX_H   = 155   # ≈ header (26 px) + 6 data rows (~21 px each)
        _MIN_H   = 26    # at least one row visible
        self._ov_canvas.configure(height=max(_MIN_H, min(actual_h, _MAX_H)))
        self._update_overlay_panel_visibility()

    # Alias kept for external callers
    def _refresh_overlay_panel(self):
        self._refresh_panel_content()

    def _ensure_exp_scan_original_backup(self, scan: ExperimentalScan):
        """Persist the originally loaded curve so later processing stays reversible."""
        meta = getattr(scan, "metadata", None)
        if meta is None:
            scan.metadata = {}
            meta = scan.metadata
        if "_binah_original_energy" not in meta:
            meta["_binah_original_energy"] = np.array(scan.energy_ev, dtype=float).copy()
            meta["_binah_original_mu"] = np.array(scan.mu, dtype=float).copy()
            meta["_binah_original_e0"] = float(scan.e0)
            meta["_binah_original_norm"] = bool(scan.is_normalized)
            meta["_binah_original_scan_type"] = str(getattr(scan, "scan_type", ""))

    def _exp_link_meta(self, scan: ExperimentalScan) -> tuple:
        meta = getattr(scan, "metadata", {}) or {}
        return meta.get("_binah_link_group", ""), meta.get("_binah_link_role", "")

    def _selected_exp_entries(self):
        return [
            (i, label, scan, var, style)
            for i, (label, scan, var, style, _il) in enumerate(self._exp_scans)
            if var.get()
        ]

    def _new_exp_link_group_id(self) -> str:
        existing = set()
        for _label, scan, _var, _style, _il in self._exp_scans:
            meta = getattr(scan, "metadata", {}) or {}
            gid = meta.get("_binah_link_group")
            if gid:
                existing.add(str(gid))
        while True:
            gid = f"exp-link-{self._exp_link_counter}"
            self._exp_link_counter += 1
            if gid not in existing:
                return gid

    def _cleanup_exp_link_groups(self):
        groups = {}
        for _label, scan, _var, _style, _il in self._exp_scans:
            meta = getattr(scan, "metadata", None) or {}
            gid = meta.get("_binah_link_group")
            if gid:
                groups.setdefault(gid, []).append(scan)

        for gid, scans in groups.items():
            if len(scans) < 2:
                for scan in scans:
                    meta = getattr(scan, "metadata", None) or {}
                    meta.pop("_binah_link_group", None)
                    meta.pop("_binah_link_role", None)
                continue

            ref_found = False
            for scan in scans:
                meta = getattr(scan, "metadata", None) or {}
                role = meta.get("_binah_link_role")
                if role == "reference" and not ref_found:
                    ref_found = True
                else:
                    meta["_binah_link_role"] = "linked"

            if not ref_found and scans:
                scans[0].metadata["_binah_link_role"] = "reference"

    def _link_display_label(self, label: str, scan: ExperimentalScan) -> str:
        _gid, role = self._exp_link_meta(scan)
        if role == "reference":
            return f"[Ref] {label}"
        if role == "linked":
            return f"[Linked] {label}"
        return label

    def _link_selected_exp_scans(self):
        selected = self._selected_exp_entries()
        if len(selected) < 2:
            messagebox.showinfo(
                "Attach Reference / Raw",
                "Enable at least two experimental scans first.\n\n"
                "The first enabled scan becomes the reference, and the others follow its energy calibration."
            )
            return

        gid = self._new_exp_link_group_id()

        for idx, (_row_idx, _label, scan, _var, _style) in enumerate(selected):
            self._ensure_exp_scan_original_backup(scan)
            meta = getattr(scan, "metadata", None)
            if meta is None:
                scan.metadata = {}
                meta = scan.metadata
            meta["_binah_link_group"] = gid
            meta["_binah_link_role"] = "reference" if idx == 0 else "linked"

        self._cleanup_exp_link_groups()
        ref_label = selected[0][1]
        n_linked = max(0, len(selected) - 1)
        self._refresh_panel_content()
        self._replot()
        messagebox.showinfo(
            "Attach Reference / Raw",
            f"Attached {len(selected)} scans into one calibration group.\n\n"
            f"Reference: {ref_label}\n"
            f"Followers: {n_linked}\n\n"
            f"Now when you shift the reference energy in XAS Analysis, the linked raw scans will move with it."
        )

    def _unlink_selected_exp_scans(self):
        selected = self._selected_exp_entries()
        if not selected:
            messagebox.showinfo(
                "Detach Linked Scans",
                "Enable one or more linked experimental scans to detach."
            )
            return

        changed = 0
        for _row_idx, _label, scan, _var, _style in selected:
            meta = getattr(scan, "metadata", None) or {}
            if "_binah_link_group" in meta or "_binah_link_role" in meta:
                meta.pop("_binah_link_group", None)
                meta.pop("_binah_link_role", None)
                changed += 1

        self._cleanup_exp_link_groups()
        self._refresh_panel_content()
        self._replot()
        if changed:
            messagebox.showinfo(
                "Detach Linked Scans",
                f"Detached {changed} scan(s) from calibration groups."
            )
        else:
            messagebox.showinfo(
                "Detach Linked Scans",
                "None of the enabled scans were linked."
            )

    def _update_overlay_panel_visibility(self):
        should_show = bool(self._tddft_spectra) or bool(self._exp_scans)
        if should_show:
            self._overlay_panel.pack(side=tk.TOP, fill=tk.X,
                                     before=self.canvas.get_tk_widget())
        else:
            self._overlay_panel.pack_forget()

    def _on_overlay_toggle(self):
        """Legacy stub — overlay mode is now implicit from list length."""
        self._refresh_panel_content()
        self._replot()

    # ══════════════════════════════════════════════════════════════════════════
    #  Font settings dialog
    # ══════════════════════════════════════════════════════════════════════════
    def _open_font_dialog(self):
        """Non-modal dialog for controlling font sizes and bold on all text elements."""
        win = tk.Toplevel(self)
        win.title("Font Settings")
        win.resizable(False, False)

        frm = tk.Frame(win, padx=18, pady=14)
        frm.pack(fill=tk.BOTH)

        # Header row
        tk.Label(frm, text="Element", font=("", 9, "bold"),
                 width=16, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(frm, text="Size", font=("", 9, "bold")).grid(
            row=0, column=1, columnspan=2, sticky="w", padx=(12, 0))
        tk.Label(frm, text="Bold", font=("", 9, "bold")).grid(
            row=0, column=3, sticky="w", padx=(16, 0))

        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(2, 8))

        def _row(r, label, size_var, bold_var=None):
            tk.Label(frm, text=label, font=("", 9),
                     width=16, anchor="w").grid(row=r, column=0, sticky="w", pady=3)
            tk.Label(frm, text="Size:", font=("", 8),
                     fg="gray").grid(row=r, column=1, sticky="e", padx=(12, 2))
            sb = tk.Spinbox(
                frm, from_=5, to=36, increment=1, width=5,
                textvariable=size_var, font=("Courier", 9),
                command=self._replot,
            )
            sb.grid(row=r, column=2, sticky="w")
            sb.bind("<Return>",   lambda _e: self._replot())
            sb.bind("<FocusOut>", lambda _e: self._replot())
            if bold_var is not None:
                tk.Checkbutton(frm, text="Bold", variable=bold_var,
                               command=self._replot,
                               font=("", 9)).grid(row=r, column=3, sticky="w",
                                                   padx=(16, 0))
            else:
                tk.Label(frm, text="—", fg="gray",
                         font=("", 9)).grid(row=r, column=3, sticky="w", padx=(16, 0))

        _row(2, "Plot title",    self._font_title_size,  self._font_title_bold)
        _row(3, "X-axis label",  self._font_xlabel_size, self._font_xlabel_bold)
        _row(4, "Y-axis labels", self._font_ylabel_size, self._font_ylabel_bold)
        _row(5, "Tick labels",   self._font_tick_size)
        _row(6, "Legend",        self._font_legend_size)

        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(
            row=7, column=0, columnspan=4, sticky="ew", pady=(10, 6))

        status_var = tk.StringVar(value="Changes apply live.  Size range 5 – 36 pt.")

        def _reset_all():
            """Reset to the user's saved defaults (or factory if none saved)."""
            fd = _load_font_defaults()
            self._font_title_size.set(fd["title_size"])
            self._font_title_bold.set(fd["title_bold"])
            self._font_xlabel_size.set(fd["xlabel_size"])
            self._font_xlabel_bold.set(fd["xlabel_bold"])
            self._font_ylabel_size.set(fd["ylabel_size"])
            self._font_ylabel_bold.set(fd["ylabel_bold"])
            self._font_tick_size.set(fd["tick_size"])
            self._font_legend_size.set(fd["legend_size"])
            self._replot()
            status_var.set("Reset to saved defaults.")

        def _save_as_default():
            """Persist current settings as the new program default."""
            d = {
                "title_size":  self._font_title_size.get(),
                "title_bold":  self._font_title_bold.get(),
                "xlabel_size": self._font_xlabel_size.get(),
                "xlabel_bold": self._font_xlabel_bold.get(),
                "ylabel_size": self._font_ylabel_size.get(),
                "ylabel_bold": self._font_ylabel_bold.get(),
                "tick_size":   self._font_tick_size.get(),
                "legend_size": self._font_legend_size.get(),
            }
            _save_font_defaults(d)
            status_var.set("✔ Saved as program default.")

        def _factory_reset():
            """Reset to the original factory defaults (ignores saved file)."""
            fd = _FONT_FACTORY_DEFAULTS
            self._font_title_size.set(fd["title_size"])
            self._font_title_bold.set(fd["title_bold"])
            self._font_xlabel_size.set(fd["xlabel_size"])
            self._font_xlabel_bold.set(fd["xlabel_bold"])
            self._font_ylabel_size.set(fd["ylabel_size"])
            self._font_ylabel_bold.set(fd["ylabel_bold"])
            self._font_tick_size.set(fd["tick_size"])
            self._font_legend_size.set(fd["legend_size"])
            self._replot()
            status_var.set("Reset to factory defaults.")

        btn_row = tk.Frame(frm)
        btn_row.grid(row=8, column=0, columnspan=4, pady=(0, 2))
        tk.Button(btn_row, text="Save as Default", command=_save_as_default,
                  font=("", 8, "bold"), bg="#d0e8d0", fg="darkgreen",
                  relief="raised").pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Reset Defaults", command=_reset_all,
                  font=("", 8)).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Factory Reset", command=_factory_reset,
                  font=("", 8), fg="gray").pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Close", command=win.destroy,
                  font=("", 9)).pack(side=tk.LEFT, padx=4)

        tk.Label(frm, textvariable=status_var,
                 font=("", 8), fg="gray").grid(
            row=9, column=0, columnspan=4, pady=(4, 0))

        _centre_window(win, self)

    # ══════════════════════════════════════════════════════════════════════════
    #  Style dialogs
    # ══════════════════════════════════════════════════════════════════════════

    def _open_tddft_spectrum_style_dialog(self, idx: int):
        """Per-spectrum TDDFT style: display toggles, broadening, scale, components, plot style."""
        entry = self._tddft_spectra[idx]
        sp    = entry["spectrum"]
        st    = entry["style"]

        win = tk.Toplevel(self)
        win.title("TDDFT Spectrum Style")
        win.resizable(False, False)
        win.grab_set()

        # ── Header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg="#003366", padx=10, pady=6)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="TDDFT Spectrum Style",
                 bg="#003366", fg="white", font=("", 10, "bold")).pack(anchor="w")
        lbl_text = entry["label"][:60] + ("\u2026" if len(entry["label"]) > 60 else "")
        tk.Label(hdr, text=lbl_text, bg="#003366", fg="#aaccff",
                 font=("", 8)).pack(anchor="w")

        body = tk.Frame(win, padx=12, pady=8)
        body.pack(fill=tk.BOTH)

        # ── Display toggles ─────────────────────────────────────────────────
        disp_frame = tk.LabelFrame(body, text="Display", padx=8, pady=4)
        disp_frame.pack(fill=tk.X, pady=(0, 6))

        show_sticks = tk.BooleanVar(value=entry["show_sticks"].get())
        show_env    = tk.BooleanVar(value=entry["show_env"].get())
        show_trans  = tk.BooleanVar(value=entry["show_trans"].get())

        tk.Checkbutton(disp_frame, text="Sticks",      variable=show_sticks).pack(side=tk.LEFT, padx=4)
        tk.Checkbutton(disp_frame, text="Envelope",    variable=show_env).pack(side=tk.LEFT, padx=4)
        tk.Checkbutton(disp_frame, text="Transitions", variable=show_trans).pack(side=tk.LEFT, padx=4)

        # ── Broadening & scale ───────────────────────────────────────────────
        brd_frame = tk.LabelFrame(body, text="Broadening & Scale", padx=8, pady=4)
        brd_frame.pack(fill=tk.X, pady=(0, 6))

        # Broadening type
        br_row = tk.Frame(brd_frame)
        br_row.grid(row=0, column=0, columnspan=4, sticky="w")
        tk.Label(br_row, text="Broadening:").pack(side=tk.LEFT)
        broadening = tk.StringVar(value=entry["broadening"].get())
        for b in ("Gaussian", "Lorentzian"):
            tk.Radiobutton(br_row, text=b, variable=broadening,
                           value=b).pack(side=tk.LEFT, padx=3)

        # FWHM — unit and slider range match the current X axis
        _xu = self._x_unit.get()
        _fwhm_unit = "cm\u207b\u00b9" if _xu in ("cm\u207b\u00b9", "nm") else ("Ha" if _xu == "Ha" else "eV")
        _fwhm_lo, _fwhm_hi, _fwhm_res = self._fwhm_slider_range(_xu)
        fwhm_v = tk.DoubleVar(value=entry["fwhm"].get())
        _slider_row(brd_frame, "FWHM:", fwhm_v, _fwhm_lo, _fwhm_hi, _fwhm_res, row=1, unit=_fwhm_unit)

        # ΔE shift
        de_v = tk.DoubleVar(value=entry["delta_e"].get())
        _slider_row(brd_frame, "\u0394E:", de_v, -200.0, 200.0, 0.1, row=2, unit="eV")

        # Scale
        scale_v = tk.DoubleVar(value=entry["scale"].get())
        _slider_row(brd_frame, "Scale:", scale_v, 0.01, 5.0, 0.01, row=3, unit="\u00d7")

        # ── Components (combined spectra only) ──────────────────────────────
        if sp.is_combined():
            comb_frame = tk.LabelFrame(body, text="Components", padx=8, pady=4)
            comb_frame.pack(fill=tk.X, pady=(0, 6))

            comb_total = tk.BooleanVar(value=entry["comb_total"].get())
            tk.Checkbutton(comb_frame, text="Total", variable=comb_total,
                           fg="#333333").pack(side=tk.LEFT, padx=4)
            comb_d2 = tk.BooleanVar(value=entry["comb_d2"].get())
            if sp.fosc_d2:
                tk.Checkbutton(comb_frame, text="Elec. Dipole (D\u00b2)",
                               variable=comb_d2, fg="#1f77b4").pack(side=tk.LEFT, padx=4)
            comb_m2 = tk.BooleanVar(value=entry["comb_m2"].get())
            if sp.fosc_m2:
                tk.Checkbutton(comb_frame, text="Mag. Dipole (m\u00b2)",
                               variable=comb_m2, fg="#2ca02c").pack(side=tk.LEFT, padx=4)
            comb_q2 = tk.BooleanVar(value=entry["comb_q2"].get())
            if sp.fosc_q2:
                tk.Checkbutton(comb_frame, text="Elec. Quad. (Q\u00b2)",
                               variable=comb_q2, fg="#d62728").pack(side=tk.LEFT, padx=4)
        else:
            comb_total = comb_d2 = comb_m2 = comb_q2 = None

        # ── Envelope style ───────────────────────────────────────────────────
        env_frame = tk.LabelFrame(body, text="Envelope", padx=8, pady=4)
        env_frame.pack(fill=tk.X, pady=(0, 6))

        env_lw  = tk.DoubleVar(value=st.get("env_linewidth",  2.0))
        env_fill = tk.BooleanVar(value=st.get("env_fill",     True))
        env_fa  = tk.DoubleVar(value=st.get("env_fill_alpha", 0.10))

        _slider_row(env_frame, "Line width:", env_lw, 0.5, 5.0, 0.1, row=0, unit="pt")
        fill_row = tk.Frame(env_frame)
        fill_row.grid(row=1, column=0, columnspan=4, sticky="w", pady=2)
        tk.Checkbutton(fill_row, text="Fill area under curve",
                       variable=env_fill).pack(side=tk.LEFT)
        _slider_row(env_frame, "Fill opacity:", env_fa, 0.0, 0.50, 0.01, row=2)

        # ── Sticks style ─────────────────────────────────────────────────────
        stk_frame = tk.LabelFrame(body, text="Sticks (stems)", padx=8, pady=4)
        stk_frame.pack(fill=tk.X, pady=(0, 6))

        stk_lw   = tk.DoubleVar(value=st.get("stick_linewidth",  1.2))
        stk_alph = tk.DoubleVar(value=st.get("stick_alpha",      0.75))
        stk_ms   = tk.DoubleVar(value=st.get("stick_markersize", 4))
        stk_mkr  = tk.BooleanVar(value=st.get("stick_markers",   True))

        _slider_row(stk_frame, "Line width:", stk_lw,   0.5, 4.0, 0.1,  row=0, unit="pt")
        _slider_row(stk_frame, "Opacity:",    stk_alph, 0.1, 1.0, 0.05, row=1)
        mkr_row = tk.Frame(stk_frame)
        mkr_row.grid(row=2, column=0, columnspan=4, sticky="w", pady=2)
        tk.Checkbutton(mkr_row, text="Show tip markers (dots)",
                       variable=stk_mkr).pack(side=tk.LEFT)
        _slider_row(stk_frame, "Marker size:", stk_ms, 1, 12, 1, row=3, unit="px")

        # ── Snapshot original state for Cancel revert ────────────────────────
        _orig = {
            "show_sticks": entry["show_sticks"].get(),
            "show_env":    entry["show_env"].get(),
            "show_trans":  entry["show_trans"].get(),
            "broadening":  entry["broadening"].get(),
            "fwhm":        entry["fwhm"].get(),
            "delta_e":     entry["delta_e"].get(),
            "scale":       entry["scale"].get(),
            "comb_total":  entry["comb_total"].get() if "comb_total" in entry else True,
            "comb_d2":     entry["comb_d2"].get()    if "comb_d2"    in entry else False,
            "comb_m2":     entry["comb_m2"].get()    if "comb_m2"    in entry else False,
            "comb_q2":     entry["comb_q2"].get()    if "comb_q2"    in entry else False,
            "style":       dict(entry["style"]),
        }

        # ── Buttons ─────────────────────────────────────────────────────────
        def _read_dialog():
            return {
                "show_sticks": show_sticks.get(),
                "show_env":    show_env.get(),
                "show_trans":  show_trans.get(),
                "broadening":  broadening.get(),
                "fwhm":        fwhm_v.get(),
                "delta_e":     de_v.get(),
                "scale":       scale_v.get(),
                "comb_total":  comb_total.get() if comb_total else True,
                "comb_d2":     comb_d2.get()    if comb_d2    else False,
                "comb_m2":     comb_m2.get()    if comb_m2    else False,
                "comb_q2":     comb_q2.get()    if comb_q2    else False,
                "style": {
                    "env_linewidth":    env_lw.get(),
                    "env_fill":         env_fill.get(),
                    "env_fill_alpha":   env_fa.get(),
                    "stick_linewidth":  stk_lw.get(),
                    "stick_alpha":      stk_alph.get(),
                    "stick_markersize": int(stk_ms.get()),
                    "stick_markers":    stk_mkr.get(),
                },
            }

        def _apply_vals(vals, target_entry):
            target_entry["show_sticks"].set(vals["show_sticks"])
            target_entry["show_env"].set(vals["show_env"])
            target_entry["show_trans"].set(vals["show_trans"])
            target_entry["broadening"].set(vals["broadening"])
            target_entry["fwhm"].set(vals["fwhm"])
            target_entry["delta_e"].set(vals["delta_e"])
            target_entry["scale"].set(vals["scale"])
            if "comb_total" in target_entry:
                target_entry["comb_total"].set(vals["comb_total"])
                target_entry["comb_d2"].set(vals["comb_d2"])
                target_entry["comb_m2"].set(vals["comb_m2"])
                target_entry["comb_q2"].set(vals["comb_q2"])
            target_entry["style"].update(vals["style"])

        def _do_apply():
            """Apply current dialog values to this spectrum (no close)."""
            _apply_vals(_read_dialog(), entry)
            self._replot()

        def _do_apply_all():
            """Apply current dialog values to every TDDFT spectrum (no close)."""
            vals = _read_dialog()
            for e in self._tddft_spectra:
                _apply_vals(vals, e)
            self._replot()

        def _do_save():
            """Apply and close."""
            _do_apply()
            win.destroy()

        def _do_cancel():
            """Revert to state at dialog-open time, then close."""
            _apply_vals(_orig, entry)
            self._replot()
            win.destroy()

        def _do_set_default():
            vals = _read_dialog()
            _TDDFT_STYLE_DEFAULTS.update(vals["style"])
            _apply_vals(vals, entry)
            _save_style_config()
            self._replot()
            messagebox.showinfo("Default saved",
                "Style saved as default for new TDDFT spectra.",
                parent=win)

        btn = tk.Frame(win)
        btn.pack(pady=(4, 10))
        tk.Button(btn, text="Apply",               width=12,
                  command=_do_apply).pack(side=tk.LEFT, padx=3)
        tk.Button(btn, text="Apply to ALL TDDFT",  width=18,
                  bg="#004400", fg="white",
                  command=_do_apply_all).pack(side=tk.LEFT, padx=3)
        tk.Button(btn, text="Set as Default",      width=14,
                  bg="#003366", fg="white",
                  command=_do_set_default).pack(side=tk.LEFT, padx=3)
        tk.Button(btn, text="Save",                width=8,
                  command=_do_save).pack(side=tk.LEFT, padx=3)
        tk.Button(btn, text="Cancel",              width=8,
                  command=_do_cancel).pack(side=tk.LEFT, padx=3)

        win.protocol("WM_DELETE_WINDOW", _do_cancel)   # X button reverts too
        _centre_window(win, self)

    def _open_tddft_style_dialog(self):
        """Global TDDFT plot style: envelope and sticks."""
        win = tk.Toplevel(self)
        win.title("TDDFT Plot Style")
        win.resizable(False, False)
        win.grab_set()

        st = self._tddft_style

        # ── Envelope ────────────────────────────────────────────────────────
        env_frame = tk.LabelFrame(win, text="Envelope", padx=10, pady=6)
        env_frame.pack(fill=tk.X, padx=12, pady=(10, 4))

        env_lw  = tk.DoubleVar(value=st["env_linewidth"])
        env_fill = tk.BooleanVar(value=st["env_fill"])
        env_fa  = tk.DoubleVar(value=st["env_fill_alpha"])

        _slider_row(env_frame, "Line width:", env_lw, 0.5, 5.0, 0.1, row=0, unit="pt")

        fill_row = tk.Frame(env_frame)
        fill_row.grid(row=1, column=0, columnspan=4, sticky="w", pady=2)
        tk.Checkbutton(fill_row, text="Fill area under curve",
                       variable=env_fill).pack(side=tk.LEFT)
        _slider_row(env_frame, "Fill opacity:", env_fa, 0.0, 0.50, 0.01, row=2)

        # ── Sticks ──────────────────────────────────────────────────────────
        stk_frame = tk.LabelFrame(win, text="Sticks (stems)", padx=10, pady=6)
        stk_frame.pack(fill=tk.X, padx=12, pady=(4, 10))

        stk_lw   = tk.DoubleVar(value=st["stick_linewidth"])
        stk_alph = tk.DoubleVar(value=st["stick_alpha"])
        stk_ms   = tk.DoubleVar(value=st["stick_markersize"])
        stk_mkr  = tk.BooleanVar(value=st.get("stick_markers", True))

        _slider_row(stk_frame, "Line width:",   stk_lw,   0.5, 4.0, 0.1,  row=0, unit="pt")
        _slider_row(stk_frame, "Opacity:",      stk_alph, 0.1, 1.0, 0.05, row=1)

        mkr_row = tk.Frame(stk_frame)
        mkr_row.grid(row=2, column=0, columnspan=4, sticky="w", pady=2)
        tk.Checkbutton(mkr_row, text="Show tip markers (dots)",
                       variable=stk_mkr).pack(side=tk.LEFT)

        _slider_row(stk_frame, "Marker size:",  stk_ms,   1,   12,  1,    row=3, unit="px")

        # ── Snapshot for Cancel revert ───────────────────────────────────────
        _orig_st = dict(st)

        # ── Buttons ─────────────────────────────────────────────────────────
        def _read_dialog():
            return {
                "env_linewidth":    env_lw.get(),
                "env_fill":         env_fill.get(),
                "env_fill_alpha":   env_fa.get(),
                "stick_linewidth":  stk_lw.get(),
                "stick_alpha":      stk_alph.get(),
                "stick_markersize": int(stk_ms.get()),
                "stick_markers":    stk_mkr.get(),
            }

        def _do_apply():
            st.update(_read_dialog())
            self._replot()

        def _do_save():
            _do_apply()
            win.destroy()

        def _do_cancel():
            st.update(_orig_st)
            self._replot()
            win.destroy()

        def _do_set_default():
            vals = _read_dialog()
            _TDDFT_STYLE_DEFAULTS.update(vals)
            st.update(vals)
            _save_style_config()
            self._replot()
            messagebox.showinfo("Default saved",
                "TDDFT style saved as default.\n"
                "All new computational spectra will use these settings.",
                parent=win)

        btn = tk.Frame(win)
        btn.pack(pady=(4, 10))
        tk.Button(btn, text="Apply",          width=12,
                  command=_do_apply).pack(side=tk.LEFT, padx=4)
        tk.Button(btn, text="Set as Default", width=14, bg="#003366", fg="white",
                  command=_do_set_default).pack(side=tk.LEFT, padx=4)
        tk.Button(btn, text="Save",           width=8,
                  command=_do_save).pack(side=tk.LEFT, padx=4)
        tk.Button(btn, text="Cancel",         width=8,
                  command=_do_cancel).pack(side=tk.LEFT, padx=4)

        win.protocol("WM_DELETE_WINDOW", _do_cancel)
        _centre_window(win, self)

    def _pick_exp_colour(self, idx: int):
        """Open the system colour-wheel directly from the panel swatch."""
        from tkinter import colorchooser
        label, scan, var, style, in_legend = self._exp_scans[idx]
        auto_col  = EXP_COLOURS[idx % len(EXP_COLOURS)]
        init_col  = style.get("color") or auto_col
        result    = colorchooser.askcolor(
            color=init_col,
            title=f"Colour — {label[:40]}",
            parent=self,
        )
        if result and result[1]:                    # user confirmed a colour
            style["color"] = result[1]
            self._refresh_panel_content()
            self._replot()

    def _pick_tddft_colour(self, idx: int):
        """Open the system colour-wheel for a TDDFT spectrum swatch."""
        from tkinter import colorchooser
        entry = self._tddft_spectra[idx]
        default_col = OVERLAY_COLOURS[idx % len(OVERLAY_COLOURS)]
        init_col    = entry["color"] or default_col
        result = colorchooser.askcolor(
            color=init_col,
            title=f"Colour — {entry['label'][:40]}",
            parent=self,
        )
        if result and result[1]:
            self._tddft_spectra[idx]["color"] = result[1]
            self._refresh_panel_content()
            self._replot()

    # Legacy alias kept so any external calls still work
    def _pick_overlay_colour(self, idx: int):
        self._pick_tddft_colour(idx + 1)   # old idx was 0-based within overlay_spectra

    def _open_exp_style_dialog(self, idx: int):
        """Per-scan experimental plot style."""
        label, scan, var, style, in_legend = self._exp_scans[idx]

        win = tk.Toplevel(self)
        win.title(f"Exp. Scan Style")
        win.resizable(False, False)
        win.grab_set()

        # Header
        hdr = tk.Frame(win, bg="#6B0000", padx=10, pady=6)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Experimental Scan Style",
                 bg="#6B0000", fg="white", font=("", 10, "bold")).pack(anchor="w")
        tk.Label(hdr, text=label[:60] + ("…" if len(label) > 60 else ""),
                 bg="#6B0000", fg="#ffaaaa", font=("", 8)).pack(anchor="w")

        body = tk.Frame(win, padx=12, pady=8)
        body.pack(fill=tk.BOTH)

        # ── Line style ──────────────────────────────────────────────────────
        tk.Label(body, text="Line style:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        ls_var = tk.StringVar(value=style["linestyle"])
        ls_frame = tk.Frame(body)
        ls_frame.grid(row=0, column=1, columnspan=4, sticky="w")
        for display, value in LS_OPTIONS:
            tk.Radiobutton(ls_frame, text=display, variable=ls_var,
                           value=value).pack(side=tk.LEFT, padx=4)

        # ── Line width ──────────────────────────────────────────────────────
        lw_var = tk.DoubleVar(value=style["linewidth"])
        _slider_row(body, "Line width:", lw_var, 0.5, 5.0, 0.1, row=1, unit="pt")

        # ── Color ───────────────────────────────────────────────────────────
        auto_col = EXP_COLOURS[idx % len(EXP_COLOURS)]
        tk.Label(body, text="Color:", font=("", 9, "bold")).grid(
            row=2, column=0, sticky="w", pady=4)
        col_var = tk.StringVar(value=style.get("color", ""))

        # Swatch button — shows current colour; click opens colour-wheel
        _swatch_init = col_var.get() or auto_col
        col_swatch = tk.Button(body, bg=_swatch_init, width=4, relief=tk.RAISED,
                               cursor="hand2")
        col_swatch.grid(row=2, column=1, sticky="w", padx=(4, 4))

        def _pick_color_dialog():
            from tkinter import colorchooser
            init = col_var.get().strip() or auto_col
            result = colorchooser.askcolor(color=init,
                                           title="Choose scan colour",
                                           parent=win)
            if result and result[1]:
                col_var.set(result[1])
                col_swatch.config(bg=result[1], activebackground=result[1])

        col_swatch.config(command=_pick_color_dialog)

        def _reset_to_auto():
            col_var.set("")
            col_swatch.config(bg=auto_col, activebackground=auto_col)

        tk.Label(body, text=f"(auto: {auto_col})",
                 fg="gray", font=("", 8)).grid(row=2, column=2, sticky="w")
        tk.Button(body, text="Reset to auto", font=("", 8),
                  command=_reset_to_auto).grid(row=2, column=3, sticky="w")

        # ── Fill ────────────────────────────────────────────────────────────
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(
            row=3, column=0, columnspan=4, sticky="ew", pady=6)
        tk.Label(body, text="Fill area under curve:",
                 font=("", 9, "bold")).grid(row=4, column=0, sticky="w")
        fill_var  = tk.BooleanVar(value=style["fill"])
        alpha_var = tk.DoubleVar(value=style["fill_alpha"])

        fill_frame = tk.Frame(body)
        fill_frame.grid(row=4, column=1, columnspan=4, sticky="w")
        tk.Checkbutton(fill_frame, text="Show fill", variable=fill_var).pack(side=tk.LEFT)

        _slider_row(body, "Fill opacity:", alpha_var, 0.0, 0.5, 0.01, row=5)

        # ── Snapshot original state for Cancel revert ────────────────────────
        _orig_style = dict(style)

        # ── Buttons ─────────────────────────────────────────────────────────
        def _read_dialog():
            return {
                "linestyle":  ls_var.get(),
                "linewidth":  lw_var.get(),
                "color":      col_var.get().strip(),
                "fill":       fill_var.get(),
                "fill_alpha": alpha_var.get(),
            }

        def _do_apply():
            """Apply to this scan without closing."""
            style.update(_read_dialog())
            self._refresh_panel_content()
            self._replot()

        def _do_apply_all():
            """Push line/fill style to every exp scan — NEVER changes colours."""
            vals = _read_dialog()
            for _lbl, _sc, _var, _st, _il in self._exp_scans:
                _st["linestyle"]  = vals["linestyle"]
                _st["linewidth"]  = vals["linewidth"]
                _st["fill"]       = vals["fill"]
                _st["fill_alpha"] = vals["fill_alpha"]
            self._refresh_panel_content()
            self._replot()

        def _do_save():
            _do_apply()
            win.destroy()

        def _do_cancel():
            style.update(_orig_style)
            self._refresh_panel_content()
            self._replot()
            win.destroy()

        def _do_set_default():
            vals = _read_dialog()
            saved = dict(vals)
            saved["color"] = ""   # don't save per-scan colour as the global default
            _EXP_STYLE_DEFAULTS.update(saved)
            style.update(vals)
            _save_style_config()
            self._refresh_panel_content()
            self._replot()
            messagebox.showinfo("Default saved",
                "Experimental style saved as default.\n"
                "All new scans loaded from now on will use these settings.",
                parent=win)

        btn = tk.Frame(win)
        btn.pack(pady=(4, 10))
        tk.Button(btn, text="Apply",             width=12,
                  command=_do_apply).pack(side=tk.LEFT, padx=3)
        tk.Button(btn, text="Apply to ALL Exp.", width=16,
                  bg="#004400", fg="white",
                  command=_do_apply_all).pack(side=tk.LEFT, padx=3)
        tk.Button(btn, text="Set as Default",    width=14,
                  bg="#003366", fg="white",
                  command=_do_set_default).pack(side=tk.LEFT, padx=3)
        tk.Button(btn, text="Save",              width=8,
                  command=_do_save).pack(side=tk.LEFT, padx=3)
        tk.Button(btn, text="Cancel",            width=8,
                  command=_do_cancel).pack(side=tk.LEFT, padx=3)

        win.protocol("WM_DELETE_WINDOW", _do_cancel)
        _centre_window(win, self)

    # ══════════════════════════════════════════════════════════════════════════
    #  Legend editor dialog
    # ══════════════════════════════════════════════════════════════════════════
    def _open_legend_editor(self):
        win = tk.Toplevel(self)
        win.title("Edit Legend")
        win.resizable(True, False)
        win.grab_set()

        tk.Label(win, text="Edit legend labels below. Leave blank to hide that entry.",
                 font=("", 9), fg="gray").pack(anchor="w", padx=10, pady=(8, 2))

        # ── Plot title ────────────────────────────────────────────────────────
        title_frame = tk.Frame(win, padx=10)
        title_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(title_frame, text="Plot title:", font=("", 9, "bold"),
                 width=12, anchor="e").pack(side=tk.LEFT)
        _title_entry = tk.Entry(title_frame, font=("", 9), width=50, bg="#f8f8ff",
                                relief=tk.SUNKEN)
        _title_entry.insert(0, self._custom_title.get())
        _title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        tk.Button(title_frame, text="Auto", font=("", 8),
                  command=lambda: (_title_entry.delete(0, tk.END),)
                  ).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Separator(win, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=(4, 2))

        entries = []

        # TDDFT spectra (unified list: index 0 = primary, 1+ = overlays)
        _local_show_primary = tk.BooleanVar(value=self._show_primary_in_legend.get())
        if self._tddft_spectra:
            tk.Label(win, text="TDDFT Spectra:", font=("", 8, "bold")).pack(anchor="w", padx=10)
            for i, entry in enumerate(self._tddft_spectra):
                col = entry["color"] or OVERLAY_COLOURS[i % len(OVERLAY_COLOURS)]
                sp  = entry["spectrum"]
                tf  = tk.Frame(win, padx=8)
                tf.pack(fill=tk.X, pady=1)
                tk.Label(tf, bg=col, width=2, relief=tk.RAISED).pack(side=tk.LEFT)
                prefix = "Primary" if i == 0 else f"  #{i}"
                tk.Label(tf, text=prefix, width=8, anchor="e",
                         font=("", 8, "bold" if i == 0 else "normal")).pack(side=tk.LEFT)
                te = tk.Entry(tf, width=46, font=("", 9))
                te.insert(0, getattr(sp, "_custom_label", None) or entry["label"])
                te.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
                if i == 0:
                    tk.Checkbutton(tf, text="Show in legend",
                                   variable=_local_show_primary,
                                   font=("", 8)).pack(side=tk.LEFT, padx=(6, 0))
                entries.append(("tddft", i, te))

        # Experimental scans
        if self._exp_scans:
            ttk.Separator(win, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=4)
            tk.Label(win, text="Experimental Scans:", font=("", 8, "bold"),
                     fg="darkred").pack(anchor="w", padx=10)
            for i, (label, scan, var, style, il) in enumerate(self._exp_scans):
                col = style.get("color") or EXP_COLOURS[i % len(EXP_COLOURS)]
                ef = tk.Frame(win, padx=8)
                ef.pack(fill=tk.X, pady=1)
                tk.Label(ef, bg=col, width=2, relief=tk.RAISED).pack(side=tk.LEFT)
                tk.Label(ef, text=f"  E{i+1}", width=4, anchor="e",
                         font=("", 8)).pack(side=tk.LEFT)
                ee = tk.Entry(ef, width=55, font=("", 9))
                ee.insert(0, label)
                ee.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
                entries.append(("exp", i, ee))

        ttk.Separator(win, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=6)

        # Use a LOCAL copy of _show_legend so the checkbox in this dialog
        # cannot accidentally flip the live state while the user is typing.
        # The value is only written back to self._show_legend on Apply.
        _local_show_legend = tk.BooleanVar(value=self._show_legend.get())
        vis_frame = tk.Frame(win, padx=10)
        vis_frame.pack(fill=tk.X)
        tk.Checkbutton(vis_frame, text="Show legend on plot",
                       variable=_local_show_legend).pack(side=tk.LEFT)

        def apply():
            for entry_info in entries:
                kind = entry_info[0]
                if kind == "tddft":
                    _, idx, e = entry_info
                    new = e.get().strip()
                    old_lbl = self._tddft_spectra[idx]["label"]
                    self._tddft_spectra[idx]["label"] = new if new else old_lbl
                    self._tddft_spectra[idx]["spectrum"]._custom_label = new if new else None
                elif kind == "exp":
                    _, idx, e = entry_info
                    new = e.get().strip()
                    lbl, scan, var, style, il = self._exp_scans[idx]
                    self._exp_scans[idx] = (new if new else lbl, scan, var, style, il)
            # Push legend-visibility + title choices back to the real variables
            self._show_legend.set(_local_show_legend.get())
            self._show_primary_in_legend.set(_local_show_primary.get())
            self._custom_title.set(_title_entry.get().strip())
            # Destroy dialog BEFORE replot so the modal grab is released first
            win.destroy()
            self._refresh_panel_content()
            self._replot()

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=8)
        tk.Button(btn_frame, text="Apply",  command=apply,      width=10).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Cancel", command=win.destroy, width=10).pack(side=tk.LEFT, padx=4)
        _centre_window(win, self)

    # ══════════════════════════════════════════════════════════════════════════
    #  Public API
    # ══════════════════════════════════════════════════════════════════════════
    def load_spectrum(self, spectrum: TDDFTSpectrum):
        if not self._custom_title.get().strip():
            self._custom_title.set(spectrum.display_name())
        # Never override the user's chosen x-unit or axis limits — just ensure
        # the FWHM slider range matches whatever unit is currently active.
        cur = self._x_unit.get()
        lo, hi, res = self._fwhm_slider_range(cur)
        self._fwhm_slider.config(from_=lo, to=hi, resolution=res)
        fwhm_lbl = (
            "cm\u207b\u00b9" if cur in ("cm\u207b\u00b9", "nm") else
            "Ha"              if cur == "Ha" else
            "eV"
        )
        self._fwhm_unit_label.config(text=fwhm_lbl)
        self._sync_fwhm_entry()

        label = getattr(spectrum, "_custom_label", None) or spectrum.display_name()
        # Carry forward per-spectrum params from the existing slot-0 entry so
        # that switching spectra doesn't reset broadening, scale, etc.
        _prev = self._tddft_spectra[0] if self._tddft_spectra else None
        entry = {
            "label":      label,
            "spectrum":   spectrum,
            "enabled":    tk.BooleanVar(value=True),
            "color":      "",
            # Preserve current values if an entry already exists; fall back to globals
            "fwhm":       tk.DoubleVar(value=_prev["fwhm"].get() if _prev else self._fwhm.get()),
            "broadening": tk.StringVar(value=_prev["broadening"].get() if _prev else self._broadening.get()),
            "delta_e":    tk.DoubleVar(value=_prev["delta_e"].get() if _prev else self._delta_e.get()),
            "scale":      tk.DoubleVar(value=_prev["scale"].get() if _prev else self._tddft_scale.get()),
            # Per-spectrum component toggles (for combined spectra)
            "comb_total": tk.BooleanVar(value=True),
            "comb_d2":    tk.BooleanVar(value=False),
            "comb_m2":    tk.BooleanVar(value=False),
            "comb_q2":    tk.BooleanVar(value=False),
            # Per-spectrum display toggles — preserve if replacing
            "show_sticks": tk.BooleanVar(value=_prev["show_sticks"].get() if _prev else self._show_sticks.get()),
            "show_env":    tk.BooleanVar(value=_prev["show_env"].get()    if _prev else self._show_env.get()),
            "show_trans":  tk.BooleanVar(value=_prev["show_trans"].get()  if _prev else self._show_trans.get()),
            # Per-spectrum style — preserve if replacing
            "style":       dict(_prev["style"]) if _prev else _default_tddft_style(),
            # Legend inclusion
            "in_legend":   tk.BooleanVar(value=_prev["in_legend"].get() if _prev else True),
        }
        if self._tddft_spectra:
            # Replace the primary (index 0) — keep any overlays intact
            self._tddft_spectra[0] = entry
        else:
            self._tddft_spectra.append(entry)
        self._refresh_panel_content()
        self._replot()

    def add_overlay(self, label: str, spectrum: TDDFTSpectrum):
        entry = {
            "label":      label,
            "spectrum":   spectrum,
            "enabled":    tk.BooleanVar(value=True),
            "color":      "",
            # Per-spectrum parameters (initialised from current global defaults)
            "fwhm":       tk.DoubleVar(value=self._fwhm.get()),
            "broadening": tk.StringVar(value=self._broadening.get()),
            "delta_e":    tk.DoubleVar(value=self._delta_e.get()),
            "scale":      tk.DoubleVar(value=self._tddft_scale.get()),
            # Per-spectrum component toggles (for combined spectra)
            "comb_total": tk.BooleanVar(value=True),
            "comb_d2":    tk.BooleanVar(value=False),
            "comb_m2":    tk.BooleanVar(value=False),
            "comb_q2":    tk.BooleanVar(value=False),
            # Per-spectrum display toggles
            "show_sticks": tk.BooleanVar(value=self._show_sticks.get()),
            "show_env":    tk.BooleanVar(value=self._show_env.get()),
            "show_trans":  tk.BooleanVar(value=self._show_trans.get()),
            # Per-spectrum style (independent copy of global defaults)
            "style":       _default_tddft_style(),
            # Legend inclusion
            "in_legend":   tk.BooleanVar(value=True),
        }
        self._tddft_spectra.append(entry)
        self._refresh_panel_content()
        self._replot()

    def add_exp_scan(self, label: str, scan: ExperimentalScan):
        self._ensure_exp_scan_original_backup(scan)
        var       = tk.BooleanVar(value=True)
        style     = _default_exp_style()
        in_legend = tk.BooleanVar(value=True)
        self._exp_scans.append((label, scan, var, style, in_legend))
        self._refresh_panel_content()
        self._replot()

    def _next_exp_merge_label(self, base: str) -> str:
        existing = {lbl for lbl, *_ in self._exp_scans}
        if base not in existing:
            return base
        idx = 2
        while f"{base} #{idx}" in existing:
            idx += 1
        return f"{base} #{idx}"

    def _exp_merge_source_arrays(self, scan: ExperimentalScan, use_original: bool):
        meta = getattr(scan, "metadata", {}) or {}
        if use_original and "_binah_original_energy" in meta and "_binah_original_mu" in meta:
            energy = np.array(meta["_binah_original_energy"], dtype=float).copy()
            mu = np.array(meta["_binah_original_mu"], dtype=float).copy()
            is_norm = bool(meta.get("_binah_original_norm", scan.is_normalized))
            e0 = float(meta.get("_binah_original_e0", scan.e0))
            scan_type = str(meta.get("_binah_original_scan_type", getattr(scan, "scan_type", "")))
        else:
            energy = np.array(scan.energy_ev, dtype=float).copy()
            mu = np.array(scan.mu, dtype=float).copy()
            is_norm = bool(scan.is_normalized)
            e0 = float(scan.e0)
            scan_type = str(getattr(scan, "scan_type", ""))

        order = np.argsort(energy)
        energy = energy[order]
        mu = mu[order]
        energy, unique_idx = np.unique(energy, return_index=True)
        mu = mu[unique_idx]
        return energy, mu, is_norm, e0, scan_type

    def _merge_exp_scans(self, use_original: bool = False):
        selected = [(lbl, scan) for lbl, scan, var, _style, _il in self._exp_scans if var.get()]
        if len(selected) < 2:
            messagebox.showinfo(
                "Merge Experimental Scans",
                "Enable at least two experimental scans to merge."
            )
            return

        series = []
        norm_flags = []
        for lbl, scan in selected:
            self._ensure_exp_scan_original_backup(scan)
            energy, mu, is_norm, e0, scan_type = self._exp_merge_source_arrays(
                scan, use_original=use_original)
            if len(energy) < 2:
                continue
            series.append((lbl, energy, mu, e0, scan_type))
            norm_flags.append(is_norm)

        if len(series) < 2:
            messagebox.showerror(
                "Merge Experimental Scans",
                "At least two scans need usable energy data to merge."
            )
            return

        if any(flag != norm_flags[0] for flag in norm_flags):
            source_txt = "original loaded" if use_original else "current"
            messagebox.showerror(
                "Merge Experimental Scans",
                "Cannot merge a mixture of raw and normalized scans from the same source.\n\n"
                f"Choose scans with the same normalization state, or switch to the other merge mode.\n"
                f"Current mode: {source_txt} data."
            )
            return

        overlap_lo = max(float(en.min()) for _, en, *_ in series)
        overlap_hi = min(float(en.max()) for _, en, *_ in series)
        if overlap_hi <= overlap_lo:
            messagebox.showerror(
                "Merge Experimental Scans",
                "The selected scans do not share an overlapping energy range."
            )
            return

        ref_idx = max(
            range(len(series)),
            key=lambda i: int(np.count_nonzero(
                (series[i][1] >= overlap_lo) & (series[i][1] <= overlap_hi)))
        )
        ref_energy = series[ref_idx][1]
        grid = ref_energy[(ref_energy >= overlap_lo) & (ref_energy <= overlap_hi)]
        if len(grid) < 2:
            grid = np.linspace(overlap_lo, overlap_hi, 400)

        merged_rows = []
        for _lbl, energy, mu, _e0, _stype in series:
            merged_rows.append(np.interp(grid, energy, mu))
        merged_arr = np.vstack(merged_rows)
        merged_mu = np.mean(merged_arr, axis=0)

        valid_e0 = [e0 for _, _, _, e0, _ in series if e0 > 0]
        merged_e0 = float(np.mean(valid_e0)) if valid_e0 else 0.0
        merged_is_norm = bool(norm_flags[0])
        merge_kind = "normalized" if merged_is_norm else "raw"
        label = self._next_exp_merge_label(
            f"Merged {merge_kind} ({len(series)} scans, {'original' if use_original else 'current'})")

        merged_scan = ExperimentalScan(
            label=label,
            source_file="merged://experimental",
            energy_ev=grid,
            mu=merged_mu,
            e0=merged_e0,
            is_normalized=merged_is_norm,
            scan_type=f"merged {merge_kind}",
            metadata={
                "merged_from_labels": [lbl for lbl, *_ in series],
                "merge_source": "original" if use_original else "current",
                "merge_count": len(series),
                "merge_overlap_ev": [overlap_lo, overlap_hi],
            },
        )
        self.add_exp_scan(label, merged_scan)
        source_txt = "original loaded" if use_original else "current"
        messagebox.showinfo(
            "Merge Experimental Scans",
            f"Created merged scan:\n{label}\n\n"
            f"Source: {source_txt}\n"
            f"Scans merged: {len(series)}\n"
            f"Overlap: {overlap_lo:.2f} to {overlap_hi:.2f} eV"
        )

    def _remove_overlay_idx(self, idx: int):
        """Legacy alias — old callers used 0-based overlay index (skipping primary)."""
        self._remove_tddft_idx(idx + 1)

    def _remove_exp_scan_idx(self, idx: int):
        if 0 <= idx < len(self._exp_scans):
            self._exp_scans.pop(idx)
            self._refresh_panel_content()
            self._replot()

    def _clear_overlays(self):
        """Remove all overlay spectra (indices 1+), keeping the primary (index 0)."""
        if len(self._tddft_spectra) > 1:
            del self._tddft_spectra[1:]
        self._refresh_panel_content()
        self._replot()

    def clear_tddft(self):
        """Remove ALL TDDFT spectra including the primary."""
        self._tddft_spectra.clear()
        self._refresh_panel_content()
        self._replot()

    def _clear_exp_scans(self):
        self._exp_scans.clear()
        self._refresh_panel_content()
        self._replot()

    # ══════════════════════════════════════════════════════════════════════════
    #  Unit helpers
    # ══════════════════════════════════════════════════════════════════════════
    # Conversion constants
    _HA_TO_EV  = 27.21138602   # 1 Hartree in eV
    _EV_TO_CM  = 8065.54       # 1 eV in cm⁻¹

    def _ev_to_unit(self, ev_arr):
        unit = self._x_unit.get()
        if unit == "nm":
            with np.errstate(divide="ignore"):
                return np.where(ev_arr > 0, 1239.84 / ev_arr, 0.0)
        elif unit == "Ha":
            return ev_arr / self._HA_TO_EV
        elif unit == "cm\u207b\u00b9":
            return ev_arr * self._EV_TO_CM
        return ev_arr   # eV

    # ── FWHM unit helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _fwhm_slider_range(unit: str):
        """Return (lo, hi, resolution) for the FWHM slider in *unit* space.
        Ranges correspond to ≈0.05 eV – 20 eV broadening in each unit."""
        if unit in ("cm\u207b\u00b9", "nm"):
            return 400, 160000, 400
        if unit == "Ha":
            return 0.002, 0.74, 0.001
        return 0.05, 20.0, 0.05   # eV (default)

    def _convert_fwhm_value(self, value: float, from_unit: str, to_unit: str) -> float:
        """Convert a FWHM value from one display-unit space to another."""
        if from_unit == to_unit:
            return value
        # Step 1 — convert to eV
        if from_unit == "Ha":
            ev = value * self._HA_TO_EV
        elif from_unit in ("cm\u207b\u00b9", "nm"):
            ev = value / self._EV_TO_CM
        else:
            ev = value   # already eV
        # Step 2 — convert from eV to target unit
        if to_unit == "Ha":
            return ev / self._HA_TO_EV
        if to_unit in ("cm\u207b\u00b9", "nm"):
            return ev * self._EV_TO_CM
        return ev   # eV

    def _fwhm_in_ev(self, fwhm_override: float = None) -> float:
        """Return the FWHM value converted to eV for broadening.
        If fwhm_override is given, use that instead of self._fwhm.get()."""
        unit = self._x_unit.get()
        fwhm = fwhm_override if fwhm_override is not None else self._fwhm.get()
        if unit == "Ha":
            return fwhm * self._HA_TO_EV
        if unit in ("cm\u207b\u00b9", "nm"):
            return fwhm / self._EV_TO_CM
        return fwhm   # already eV

    def _xlabel(self) -> str:
        unit = self._x_unit.get()
        if unit == "nm":  return "Wavelength (nm)"
        if unit == "eV":  return "Energy (eV)"
        if unit == "Ha":  return "Energy (Ha)"
        return "Wavenumber (cm\u207b\u00b9)"

    # ══════════════════════════════════════════════════════════════════════════
    #  Main plot routine — uses cla() so axes objects are never destroyed
    # ══════════════════════════════════════════════════════════════════════════
    def _replot(self, *_):
        # ── Determine what to draw ────────────────────────────────────────────
        tddft_to_draw: List[Tuple[str, TDDFTSpectrum, str, dict]] = []
        for k, entry in enumerate(self._tddft_spectra):
            if entry["enabled"].get():
                col = entry["color"] or OVERLAY_COLOURS[k % len(OVERLAY_COLOURS)]
                lbl = entry["label"]
                params = {
                    "fwhm":       entry["fwhm"].get() if "fwhm" in entry else self._fwhm.get(),
                    "broadening": entry["broadening"].get() if "broadening" in entry else self._broadening.get(),
                    "delta_e":    entry["delta_e"].get() if "delta_e" in entry else self._delta_e.get(),
                    "scale":      entry["scale"].get() if "scale" in entry else self._tddft_scale.get(),
                    "comb_total": entry.get("comb_total") or self._comb_total,
                    "comb_d2":    entry.get("comb_d2")    or self._comb_d2,
                    "comb_m2":    entry.get("comb_m2")    or self._comb_m2,
                    "comb_q2":    entry.get("comb_q2")    or self._comb_q2,
                    # Per-spectrum display toggles (fall back to global if absent)
                    "show_sticks": entry.get("show_sticks") or self._show_sticks,
                    "show_env":    entry.get("show_env")    or self._show_env,
                    "show_trans":  entry.get("show_trans")  or self._show_trans,
                    # Per-spectrum style (fall back to global style dict if absent)
                    "style":       entry.get("style")       or self._tddft_style,
                    # Legend inclusion
                    "in_legend":   entry.get("in_legend")   or tk.BooleanVar(value=True),
                }
                tddft_to_draw.append((lbl, entry["spectrum"], col, params))

        active_exp = [
            (lbl, sc, style.get("color") or EXP_COLOURS[i % len(EXP_COLOURS)], style, in_legend)
            for i, (lbl, sc, var, style, in_legend) in enumerate(self._exp_scans)
            if var.get()
        ]

        # ── Rebuild axes from scratch every redraw ────────────────────────────
        # fig.clear() + add_subplot() is the standard embedded-matplotlib pattern.
        # toolbar.update() (called at the end) re-registers the fresh axes so that
        # zoom, pan, home, back, forward all work correctly after every redraw.
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)

        # Create twin axis only when experimental scans are active
        _tddft_left = self._tddft_on_left.get() == "left"
        if active_exp:
            self.ax2 = self.ax.twinx()
            self.ax2.set_navigate(False)
            if _tddft_left:
                ax_t = self.ax   # TDDFT on left
                ax_e = self.ax2  # EXP on right
                self.ax.set_zorder(self.ax2.get_zorder() + 1)
                self.ax.patch.set_visible(False)
            else:
                ax_t = self.ax2  # TDDFT on right
                ax_e = self.ax   # EXP on left
                self.ax2.set_zorder(self.ax.get_zorder() + 1)
                self.ax2.patch.set_visible(False)
                self.ax.patch.set_visible(True)
        else:
            self.ax2 = None
            self.ax.patch.set_visible(True)
            _tddft_left = True
            ax_t = self.ax
            ax_e = None

        if not tddft_to_draw and not active_exp:
            self.toolbar.update()
            self.canvas.draw_idle()
            self._notify_popouts()
            return

        multi_tddft = len(tddft_to_draw) > 1
        first_hover_set = False
        ylabel = "Oscillator Strength (f)"

        # ── Collect fresh inset data each replot ─────────────────────────────
        self._inset_plot_data = []
        self._inset_indicator = None   # fig.clear() already destroyed old indicator

        # TDDFT always plots in true oscillator-strength units on its own axis
        # (ax).  Experimental scans plot on a separate twin axis (ax2) and
        # autoscale independently, so no cross-normalisation is needed.
        show_tddft = self._show_tddft.get() and bool(tddft_to_draw)

        # ── Draw TDDFT spectra (left axis) ────────────────────────────────────
        for name, sp, colour, sp_params in (tddft_to_draw if show_tddft else []):
            # Resolve per-spectrum style + display toggles
            _st         = sp_params["style"]
            _show_sticks = sp_params["show_sticks"]
            _show_env    = sp_params["show_env"]
            _show_trans  = sp_params["show_trans"]
            _in_legend   = sp_params["in_legend"]

            delta_e = sp_params["delta_e"]
            scale   = sp_params["scale"]
            ev_arr = np.array(sp.energies_ev) + delta_e
            is_cd  = sp.is_cd()
            is_comb = sp.is_combined()
            if len(ev_arr) == 0:
                continue
            x_arr = self._ev_to_unit(ev_arr)

            import matplotlib.pyplot as _plt

            if is_comb:
                # ── Combined spectrum: draw each enabled component separately ──────
                # Colours fixed so D2/m2/Q2 are always the same colour regardless of
                # which overlay slot this spectrum occupies.
                COMB_COLS = {
                    "total": colour,         # uses normal spectrum colour
                    "d2":    "#1f77b4",      # blue
                    "m2":    "#2ca02c",      # green
                    "q2":    "#d62728",      # red
                }
                comp_defs = []
                if sp_params["comb_total"].get():
                    comp_defs.append(("total", np.array(sp.fosc),    COMB_COLS["total"], "Total"))
                if sp_params["comb_d2"].get() and sp.fosc_d2:
                    comp_defs.append(("d2",    np.array(sp.fosc_d2), COMB_COLS["d2"],   "D\u00b2 (elec. dip.)"))
                if sp_params["comb_m2"].get() and sp.fosc_m2:
                    comp_defs.append(("m2",    np.array(sp.fosc_m2), COMB_COLS["m2"],   "m\u00b2 (mag. dip.)"))
                if sp_params["comb_q2"].get() and sp.fosc_q2:
                    comp_defs.append(("q2",    np.array(sp.fosc_q2), COMB_COLS["q2"],   "Q\u00b2 (elec. quad.)"))

                if not comp_defs:
                    continue   # nothing selected — skip this spectrum silently

                for k, (key, y_c, col_c, comp_lbl) in enumerate(comp_defs):
                    if self._normalise.get() and np.abs(y_c).max() != 0:
                        yp = (y_c / np.abs(y_c).max()) * scale
                        ylabel = "Normalised Intensity"
                    else:
                        yp = y_c * scale
                        ylabel = "Oscillator Strength (f)"

                    if _show_sticks.get():
                        ml, sl, bl = ax_t.stem(
                            x_arr, yp, linefmt=col_c, markerfmt="o", basefmt=" ",
                            label="_nolegend_"
                        )
                        ml.set_markersize(_st["stick_markersize"] if _st.get("stick_markers", True) else 0)
                        ml.set_color(col_c)
                        _plt.setp(sl, linewidth=_st["stick_linewidth"],
                                  alpha=_st["stick_alpha"], color=col_c)
                        self._inset_plot_data.append(
                            ("sticks", x_arr.copy(), yp.copy(), col_c,
                             _st["stick_linewidth"], _st["stick_alpha"]))

                    if _show_env.get():
                        x_env, y_env = self._draw_envelope(ev_arr, yp, col_c, True, comp_lbl,
                                                            fwhm_override=sp_params["fwhm"],
                                                            broadening_override=sp_params["broadening"],
                                                            style=_st, ax=ax_t)
                        if x_env is not None:
                            self._inset_plot_data.append(
                                ("line", x_env, y_env, col_c,
                                 _st["env_linewidth"], "solid", 0.9))
                            if _st["env_fill"]:
                                self._inset_plot_data.append(
                                    ("fill", x_env, y_env, col_c, _st["env_fill_alpha"]))

                    if _show_trans.get() and sp.excited_states and k == 0:
                        self._draw_transition_labels(x_arr, yp, sp)

                    # Hover data from the first/primary component
                    if k == 0 and not first_hover_set:
                        self._hover_x      = x_arr
                        self._hover_y      = yp
                        self._hover_ev     = ev_arr
                        self._hover_cm     = np.array(sp.energies_cm)
                        self._hover_states = list(sp.states)
                        self._hover_labels = list(sp.transition_labels)
                        first_hover_set = True

            else:
                # ── Normal (non-combined) spectrum ────────────────────────────────
                y_arr = np.array(sp.rotatory_strength if is_cd else sp.fosc)

                if self._normalise.get() and np.abs(y_arr).max() != 0:
                    y_plot = (y_arr / np.abs(y_arr).max()) * scale
                    ylabel = ("Normalised \u00d7 scale" if abs(scale - 1) > 1e-6
                              else "Normalised Intensity")
                else:
                    y_plot = y_arr * scale
                    ylabel = "Rotatory Strength" if is_cd else "Oscillator Strength (f)"

                if _show_sticks.get():
                    ml, sl, bl = ax_t.stem(
                        x_arr, y_plot, linefmt=colour, markerfmt="o", basefmt=" ",
                        label="_nolegend_"
                    )
                    ml.set_markersize(_st["stick_markersize"] if _st.get("stick_markers", True) else 0)
                    ml.set_color(colour)
                    _plt.setp(sl, linewidth=_st["stick_linewidth"],
                              alpha=_st["stick_alpha"], color=colour)
                    self._inset_plot_data.append(
                        ("sticks", x_arr.copy(), y_plot.copy(), colour,
                         _st["stick_linewidth"], _st["stick_alpha"]))

                if _show_env.get():
                    x_env, y_env = self._draw_envelope(ev_arr, y_plot, colour,
                                                        _in_legend.get(), name,
                                                        fwhm_override=sp_params["fwhm"],
                                                        broadening_override=sp_params["broadening"],
                                                        style=_st, ax=ax_t)
                    if x_env is not None:
                        self._inset_plot_data.append(
                            ("line", x_env, y_env, colour,
                             _st["env_linewidth"], "solid", 0.9))
                        if _st["env_fill"]:
                            self._inset_plot_data.append(
                                ("fill", x_env, y_env, colour, _st["env_fill_alpha"]))

                if _show_trans.get() and sp.excited_states and not multi_tddft:
                    self._draw_transition_labels(x_arr, y_plot, sp)

                if not first_hover_set:
                    self._hover_x      = x_arr
                    self._hover_y      = y_plot
                    self._hover_ev     = ev_arr
                    self._hover_cm     = np.array(sp.energies_cm)
                    self._hover_states = list(sp.states)
                    self._hover_labels = list(sp.transition_labels)
                    first_hover_set = True

        # ── Draw experimental scans (twin axis) ─────────────────────────
        if active_exp and ax_e is not None:
            for lbl, scan, colour, style, in_legend in active_exp:
                ev_exp = scan.energy_ev
                mu_exp = scan.mu
                if len(ev_exp) == 0:
                    continue
                x_exp = self._ev_to_unit(ev_exp)
                ls    = style.get("linestyle", "solid")
                lw    = style.get("linewidth", 1.8)
                ax_e.plot(x_exp, mu_exp, color=colour, linewidth=lw,
                          linestyle=ls, alpha=0.9,
                          label=lbl if in_legend.get() else None)
                if style.get("fill", True):
                    fa = style.get("fill_alpha", 0.06)
                    ax_e.fill_between(x_exp, 0, mu_exp, alpha=fa, color=colour)
                self._inset_plot_data.append(
                    ("exp", x_exp.copy(), mu_exp.copy(), colour, lw, ls, 0.9,
                     style.get("fill", True), style.get("fill_alpha", 0.06)))

            _right_lbl = (self._custom_right_ylabel.get().strip()
                          or "\u03bc(E) \u2014 normalized XAS")
            _show_right = self._show_right_ylabel.get()
            ax_e.set_ylabel(
                _right_lbl if _show_right else "",
                fontsize=self._font_ylabel_size.get(),
                fontweight="bold" if self._font_ylabel_bold.get() else "normal",
                color="darkred")
            _show_left_exp = self._show_left_ylabel.get()
            ax_e.tick_params(
                axis="y",
                labelcolor="darkred" if _show_left_exp else "none",
                labelleft=_show_left_exp,
                labelright=False,
            )
            ax_e.axhline(0, color="darkred", linewidth=0.4, alpha=0.3)

        # ── Align y=0 of both axes when experimental overlay is active ───────
        # Ensure both axes share the same zero position regardless of scale,
        # so TDDFT sticks and XAS curve both start from the same baseline.
        if active_exp and ax_e is not None:
            # Get the natural top of each axis after plotting
            _ax1_bot, _ax1_top = ax_t.get_ylim()
            _ax2_bot, _ax2_top = ax_e.get_ylim()
            # Force bottom to 0 on both (sticks and XAS data never go below 0)
            _ax1_top = max(_ax1_top, 1e-6)
            _ax2_top = max(_ax2_top, 1e-6)
            ax_t.set_ylim(bottom=0, top=_ax1_top)
            ax_e.set_ylim(bottom=0, top=_ax2_top)

        # ── Axes decoration ───────────────────────────────────────────────────
        self.ax.set_xlabel(
            self._custom_x_label.get().strip() or self._xlabel(),
            fontsize=self._font_xlabel_size.get(),
            fontweight="bold" if self._font_xlabel_bold.get() else "normal")
        _left_lbl = self._custom_left_ylabel.get().strip() or ylabel
        ax_t.set_ylabel(
            _left_lbl if self._show_left_ylabel.get() else "",
            fontsize=self._font_ylabel_size.get(),
            fontweight="bold" if self._font_ylabel_bold.get() else "normal")

        _raw_title = self._custom_title.get()
        if _raw_title == "\x00":          # "None" button pressed — suppress title
            self.ax.set_title("")
        else:
            title = _raw_title.strip() or self._auto_title()
            self.ax.set_title(
                title,
                fontsize=self._font_title_size.get(),
                fontweight="bold" if self._font_title_bold.get() else "normal")

        # Tick label size + direction (both axes)
        self.ax.tick_params(axis="both", labelsize=self._font_tick_size.get(),
                            direction=self._tick_direction.get())
        if self.ax2 is not None:
            _show_left = self._show_left_ylabel.get()
            self.ax2.tick_params(
                axis="y",
                labelsize=self._font_tick_size.get(),
                labelcolor="darkred" if _show_right else "none",
                labelright=_show_right,
                direction=self._tick_direction.get(),
            )

        self.ax.set_facecolor(self._bg_colour)
        self.fig.patch.set_facecolor(self._bg_colour)
        self.ax.axhline(0, color="gray", linewidth=0.5, linestyle="--", alpha=0.5)
        if self._show_grid.get():
            self.ax.grid(True, alpha=0.25, linestyle=":", color="gray")
        else:
            self.ax.grid(False)

        if self._x_unit.get() == "nm" and len(self._hover_x):
            lo, hi = self._hover_x.min(), self._hover_x.max()
            if lo < hi:
                self.ax.set_xlim(hi * 1.02, lo * 0.98)

        # ── Apply manual axis-range overrides ─────────────────────────────────
        def _parse_float(s):
            try: return float(s.get().strip())
            except (ValueError, AttributeError): return None
        x_lo = _parse_float(self._xlim_lo)
        x_hi = _parse_float(self._xlim_hi)
        y_lo = _parse_float(self._ylim_lo)
        y_hi = _parse_float(self._ylim_hi)
        if x_lo is not None or x_hi is not None:
            cur = self.ax.get_xlim()
            self.ax.set_xlim(x_lo if x_lo is not None else cur[0],
                             x_hi if x_hi is not None else cur[1])
        if y_lo is not None or y_hi is not None:
            cur = ax_t.get_ylim()
            ax_t.set_ylim(y_lo if y_lo is not None else cur[0],
                          y_hi if y_hi is not None else cur[1])
        ey_lo = _parse_float(self._ylim_exp_lo)
        ey_hi = _parse_float(self._ylim_exp_hi)
        if (ey_lo is not None or ey_hi is not None) and ax_e is not None:
            cur = ax_e.get_ylim()
            ax_e.set_ylim(ey_lo if ey_lo is not None else cur[0],
                          ey_hi if ey_hi is not None else cur[1])

        # ── Secondary nm axis (cm⁻¹ mode only) ──────────────────────────────────
        _nm_axis_active = (
            self._x_unit.get() == "cm\u207b\u00b9"
            and self._show_nm_axis.get()
        )
        if _nm_axis_active:
            self._draw_secondary_nm_axis(self.ax)

        # ── Layout first so legend bbox coords are stable ─────────────────────
        self.fig.tight_layout(pad=3.0 if _nm_axis_active else 2.5)

        # ── Legend (after tight_layout so position is correct) ────────────────
        # Disconnect all stale drag callbacks from previous draw
        for _attr in ("_legend_drag_cid", "_legend_drag_cid2", "_legend_drag_cid3"):
            _cid = getattr(self, _attr, None)
            if _cid is not None:
                try:
                    self.canvas.mpl_disconnect(_cid)
                except Exception:
                    pass
                setattr(self, _attr, None)
        self._legend_ref      = None
        self._legend_dragging = False

        if self._show_legend.get():
            # h1/l1 = TDDFT handles (left axis); h2/l2 = exp handles (right axis)
            # Per-entry legend inclusion is already handled at draw time via in_legend
            # vars — entries with in_legend=False were drawn with label=None so they
            # don't appear in get_legend_handles_labels() at all.
            h1, l1 = ax_t.get_legend_handles_labels()
            h2, l2 = (ax_e.get_legend_handles_labels()
                      if active_exp and ax_e is not None else ([], []))
            # Per-spectrum in_legend vars control inclusion; combine both axes
            all_h, all_l = h1 + h2, l1 + l2
            if all_h:
                _leg_fs = self._font_legend_size.get()
                if self._legend_bbox is not None:
                    # Restore using figure-fraction coordinates so the position
                    # is stable across tight_layout / axes size changes.
                    leg = self.ax.legend(all_h, all_l, fontsize=_leg_fs,
                                         loc="upper left",
                                         bbox_to_anchor=self._legend_bbox,
                                         bbox_transform=self.fig.transFigure)
                else:
                    leg = self.ax.legend(all_h, all_l, fontsize=_leg_fs, loc="best")
                leg.set_draggable(True, update="bbox")
                self._legend_ref = leg
                # Connect drag-end callback once per draw.
                # We use motion_notify_event + button_release to detect a real
                # drag (as opposed to a plain click which must not move the saved pos).
                self._legend_dragging = False
                self._legend_drag_cid = self.canvas.mpl_connect(
                    "button_press_event",   self._on_legend_press)
                self._legend_drag_cid2 = self.canvas.mpl_connect(
                    "motion_notify_event",  self._on_legend_motion)
                self._legend_drag_cid3 = self.canvas.mpl_connect(
                    "button_release_event", self._on_legend_release)

        # ── Inset zoomed sub-plot ─────────────────────────────────────────────
        if self._inset_active and None not in self._inset_xlim:
            self._draw_inset()

        # Re-register axes with toolbar so zoom/pan/home work after every redraw
        self.toolbar.update()
        self.canvas.draw_idle()
        self._setup_inset_drag()
        self._setup_hover()
        self._update_comb_ui()
        self._notify_popouts()

    # ─────────────────────────────────────────────────────────────────────────
    def _draw_envelope(self, ev_arr, y_arr, colour, multi, name,
                       fwhm_override=None, broadening_override=None, style=None, ax=None):
        """Draw broadened envelope on ax (default self.ax); returns (x_grid, env) for inset re-use."""
        ax = ax if ax is not None else self.ax
        fwhm_ev = self._fwhm_in_ev(fwhm_override)
        if fwhm_ev <= 0:
            return None, None
        ev_min  = max(1e-3, ev_arr.min() - 4 * fwhm_ev)
        ev_max  = ev_arr.max() + 4 * fwhm_ev
        ev_grid = np.linspace(ev_min, ev_max, 2000)
        broadening = broadening_override if broadening_override is not None else self._broadening.get()
        fn      = gaussian if broadening == "Gaussian" else lorentzian
        env     = sum(y * fn(ev_grid, c, fwhm_ev) for c, y in zip(ev_arr, y_arr))
        x_grid  = self._ev_to_unit(ev_grid)
        label   = name if multi else "Envelope"
        st      = style if style is not None else self._tddft_style

        ax.plot(x_grid, env, color=colour, linewidth=st["env_linewidth"],
                linestyle=st.get("env_linestyle", "solid"),
                alpha=0.9, label=label if multi else None)
        if st["env_fill"]:
            ax.fill_between(x_grid, 0, env,
                            alpha=st["env_fill_alpha"], color=colour)
        return x_grid, env

    # ══════════════════════════════════════════════════════════════════════════
    #  Inset zoomed sub-plot
    # ══════════════════════════════════════════════════════════════════════════

    def _open_inset_dialog(self):
        """Dialog to configure (or remove) the inset zoomed sub-plot."""
        win = tk.Toplevel(self)
        win.title("Inset zoom settings")
        win.resizable(False, False)
        win.grab_set()

        unit = self._x_unit.get()

        frm = tk.Frame(win, padx=14, pady=10)
        frm.pack(fill=tk.BOTH)

        tk.Label(frm, text="Zoom region — X axis", font=("", 9, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))

        def _lbl(r, c, txt): tk.Label(frm, text=txt).grid(row=r, column=c, sticky="e", padx=4)

        _lbl(1, 0, f"X min ({unit}):")
        xlo_v = tk.StringVar(value="" if self._inset_xlim[0] is None else str(self._inset_xlim[0]))
        tk.Entry(frm, textvariable=xlo_v, width=12).grid(row=1, column=1, sticky="w")
        _lbl(1, 2, f"X max ({unit}):")
        xhi_v = tk.StringVar(value="" if self._inset_xlim[1] is None else str(self._inset_xlim[1]))
        tk.Entry(frm, textvariable=xhi_v, width=12).grid(row=1, column=3, sticky="w")

        tk.Label(frm, text="Zoom region — Y axis  (leave blank to auto-scale)",
                 font=("", 9, "bold")).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(8, 4))
        _lbl(3, 0, "Y min:")
        ylo_v = tk.StringVar(value="" if self._inset_ylim[0] is None else str(self._inset_ylim[0]))
        tk.Entry(frm, textvariable=ylo_v, width=12).grid(row=3, column=1, sticky="w")
        _lbl(3, 2, "Y max:")
        yhi_v = tk.StringVar(value="" if self._inset_ylim[1] is None else str(self._inset_ylim[1]))
        tk.Entry(frm, textvariable=yhi_v, width=12).grid(row=3, column=3, sticky="w")

        tk.Label(frm, text="Inset size (% of plot area  —  1 % … 100 %)",
                 font=("", 9, "bold")).grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(8, 4))

        # Width — slider + live numeric entry
        _lbl(5, 0, "Width %:")
        wv = tk.DoubleVar(value=round(self._inset_pos[2] * 100))
        w_entry_var = tk.StringVar(value=str(int(wv.get())))

        def _w_slider_moved(*_):
            w_entry_var.set(str(int(wv.get())))

        def _w_entry_committed(*_):
            try:
                v = float(w_entry_var.get())
                v = max(1.0, min(100.0, v))
                wv.set(v)
                w_entry_var.set(str(int(v)))
            except ValueError:
                w_entry_var.set(str(int(wv.get())))

        w_frame = tk.Frame(frm)
        w_frame.grid(row=5, column=1, sticky="w")
        tk.Scale(w_frame, variable=wv, from_=1, to=100, resolution=1,
                 orient=tk.HORIZONTAL, length=160,
                 command=_w_slider_moved).pack(side=tk.LEFT)
        we = tk.Entry(w_frame, textvariable=w_entry_var, width=5,
                      font=("Courier", 9))
        we.pack(side=tk.LEFT, padx=(4, 0))
        we.bind("<Return>",   _w_entry_committed)
        we.bind("<FocusOut>", _w_entry_committed)

        # Height — slider + live numeric entry
        _lbl(5, 2, "Height %:")
        hv = tk.DoubleVar(value=round(self._inset_pos[3] * 100))
        h_entry_var = tk.StringVar(value=str(int(hv.get())))

        def _h_slider_moved(*_):
            h_entry_var.set(str(int(hv.get())))

        def _h_entry_committed(*_):
            try:
                v = float(h_entry_var.get())
                v = max(1.0, min(100.0, v))
                hv.set(v)
                h_entry_var.set(str(int(v)))
            except ValueError:
                h_entry_var.set(str(int(hv.get())))

        h_frame = tk.Frame(frm)
        h_frame.grid(row=5, column=3, sticky="w")
        tk.Scale(h_frame, variable=hv, from_=1, to=100, resolution=1,
                 orient=tk.HORIZONTAL, length=160,
                 command=_h_slider_moved).pack(side=tk.LEFT)
        he = tk.Entry(h_frame, textvariable=h_entry_var, width=5,
                      font=("Courier", 9))
        he.pack(side=tk.LEFT, padx=(4, 0))
        he.bind("<Return>",   _h_entry_committed)
        he.bind("<FocusOut>", _h_entry_committed)

        def _parse(sv):
            try: return float(sv.get().strip())
            except ValueError: return None

        def apply():
            xl, xh = _parse(xlo_v), _parse(xhi_v)
            if xl is None or xh is None:
                messagebox.showerror("Inset", "Please fill in both X range fields.",
                                     parent=win)
                return
            # Y range is optional — leave blank for auto-scale
            yl, yh = _parse(ylo_v), _parse(yhi_v)
            self._inset_xlim = [xl, xh]
            self._inset_ylim = [yl, yh]   # None = auto
            self._inset_pos[2] = wv.get() / 100.0
            self._inset_pos[3] = hv.get() / 100.0
            # Clamp position so inset stays within the axes (handles 1-100 %)
            self._inset_pos[0] = float(np.clip(
                self._inset_pos[0], 0.0, max(0.0, 1.0 - self._inset_pos[2])))
            self._inset_pos[1] = float(np.clip(
                self._inset_pos[1], 0.0, max(0.0, 1.0 - self._inset_pos[3])))
            self._inset_active = True
            self._inset_btn.config(text="✎ Inset\u2026", fg="darkgreen")
            win.destroy()
            self._replot()

        def remove():
            self._inset_active = False
            self._inset_xlim = [None, None]
            self._inset_ylim = [None, None]
            self._inset_ax   = None
            self._inset_ax2  = None
            self._inset_btn.config(text="+ Add Inset\u2026", fg="darkgreen")
            win.destroy()
            self._replot()

        btn_row = tk.Frame(win, pady=8)
        btn_row.pack()
        tk.Button(btn_row, text="Apply",        width=10, command=apply).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Remove Inset", width=12, command=remove).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Cancel",       width=10, command=win.destroy).pack(side=tk.LEFT, padx=4)

        _centre_window(win, self)

    def _draw_inset(self):
        """Create the inset axes, re-draw plot data at zoom limits, add indicator."""
        xl, xh = self._inset_xlim
        yl, yh = self._inset_ylim   # either floats or None (auto)

        inset_ax = self.ax.inset_axes(self._inset_pos)
        self._inset_ax  = inset_ax
        self._inset_ax2 = None

        has_tddft = any(d[0] in ("sticks", "line", "fill")
                        for d in self._inset_plot_data)
        has_exp   = any(d[0] == "exp" for d in self._inset_plot_data)

        if has_exp:
            inset_ax2 = inset_ax.twinx()
            inset_ax2.set_navigate(False)
            self._inset_ax2 = inset_ax2
            inset_ax2.yaxis.set_label_position("left")
            inset_ax2.yaxis.tick_left()
            inset_ax2.spines["left"].set_visible(True)
            inset_ax2.spines["right"].set_visible(False)

        inset_ax.yaxis.set_label_position("right")
        inset_ax.yaxis.tick_right()
        inset_ax.spines["right"].set_visible(True)
        inset_ax.spines["left"].set_visible(False)

        # ── Plot data ────────────────────────────────────────────────────────
        for d in self._inset_plot_data:
            kind = d[0]
            if kind == "sticks":
                _, x, y, col, lw, alpha = d
                inset_ax.vlines(x, 0, y, colors=col, linewidth=lw, alpha=alpha)
            elif kind == "line":
                _, x, y, col, lw, ls, alpha = d
                inset_ax.plot(x, y, color=col, linewidth=lw, linestyle=ls, alpha=alpha)
            elif kind == "fill":
                _, x, y, col, alpha = d
                inset_ax.fill_between(x, 0, y, color=col, alpha=alpha)
            elif kind == "exp" and self._inset_ax2 is not None:
                _, x, y, col, lw, ls, alpha, do_fill, fa = d
                self._inset_ax2.plot(x, y, color=col, linewidth=lw,
                                     linestyle=ls, alpha=alpha)
                if do_fill:
                    self._inset_ax2.fill_between(x, 0, y, color=col, alpha=fa)

        # ── Compute auto y-range from experimental data inside the x-zoom ────
        # Needed when TDDFT is absent so indicate_inset_zoom uses the right scale.
        if has_exp and not has_tddft:
            exp_ys = []
            for d in self._inset_plot_data:
                if d[0] == "exp":
                    x, y = d[1], d[2]
                    mask = (x >= xl) & (x <= xh)
                    if mask.sum():
                        exp_ys.extend(y[mask].tolist())
            if exp_ys:
                auto_ylo = min(0.0, float(np.min(exp_ys)))
                auto_yhi = float(np.max(exp_ys)) * 1.08
            else:
                auto_ylo, auto_yhi = 0.0, 1.1
            # Only fall back to auto range when user hasn't set explicit limits
            if yl is None:
                yl = auto_ylo
            if yh is None:
                yh = auto_yhi

        # ── Apply zoom limits ────────────────────────────────────────────────
        inset_ax.set_xlim(xl, xh)
        if yl is not None and yh is not None:
            inset_ax.set_ylim(yl, yh)
        # else: leave inset_ax y auto-scaled to whatever TDDFT data is there

        if self._inset_ax2 is not None:
            self._inset_ax2.set_xlim(xl, xh)
            if not has_tddft and yl is not None:
                # No TDDFT: sync right axis to the same exp scale
                self._inset_ax2.set_ylim(yl, yh)
            elif has_tddft:
                # ── Zero-alignment across twin axes ──────────────────────────
                # After the TDDFT ylim is settled, compute where y=0 sits as a
                # fraction of the left axis height, then force the right (exp)
                # axis to the same fraction so both zeros land on the same pixel.
                tddft_yl, tddft_yh = inset_ax.get_ylim()
                tddft_span = tddft_yh - tddft_yl
                # Fraction from bottom at which zero sits on the left axis
                zero_frac = ((-tddft_yl) / tddft_span) if tddft_span > 0 else 0.0
                zero_frac = float(np.clip(zero_frac, 0.0, 1.0))

                # Determine the natural top of the exp data in the x-window
                exp_ys_in = []
                for _d in self._inset_plot_data:
                    if _d[0] == "exp":
                        _x, _y = _d[1], _d[2]
                        _m = (_x >= xl) & (_x <= xh)
                        if _m.sum():
                            exp_ys_in.extend(_y[_m].tolist())

                if exp_ys_in:
                    exp_top = float(np.max(exp_ys_in)) * 1.08
                    exp_top = max(exp_top, 0.1)   # guard against flat-zero data
                else:
                    exp_top = 1.1

                # Solve: (0 - exp_bot) / (exp_top - exp_bot) = zero_frac
                #   => exp_bot = zero_frac * exp_top / (zero_frac - 1)
                if zero_frac < 1.0:
                    exp_bot = zero_frac * exp_top / (zero_frac - 1.0)
                else:
                    exp_bot = -exp_top  # degenerate: zero at very top
                self._inset_ax2.set_ylim(exp_bot, exp_top)

        # ── Label / tick visibility ──────────────────────────────────────────
        show_lbl = self._inset_show_labels.get()
        # Left axis: hide entirely when there's no TDDFT data on it
        if not has_tddft:
            inset_ax.yaxis.set_visible(False)
        else:
            inset_ax.tick_params(labelsize=7, labelleft=False, labelright=show_lbl)
        inset_ax.tick_params(labelsize=7, labelbottom=show_lbl)

        if self._inset_ax2 is not None:
            self._inset_ax2.tick_params(
                axis="y", labelsize=6, labelcolor="darkred",
                labelleft=show_lbl, labelright=False)

        inset_ax.set_facecolor(self._bg_colour)

        # ── Indicator rectangle on the main axes ─────────────────────────────
        # We draw this manually rather than using indicate_inset_zoom() because
        # that function only understands a single axis coordinate system.  When
        # exp data lives on ax2 (right axis) but TDDFT lives on ax (left axis),
        # indicate_inset_zoom(inset_ax) draws the box in LEFT-axis (oscillator-
        # strength) coordinates — so the box appears at totally the wrong y
        # position (e.g. a 0–0.04 sliver at the bottom instead of the
        # 0.4–1.1 XAS range).
        #
        # Rule:
        #   • exp data present  → draw on self.ax2 using the XAS y-range of the
        #                          zoom window so the box overlaps the actual curves
        #   • TDDFT only        → draw on self.ax using the TDDFT y-range
        from matplotlib.patches import Rectangle as _Rect, ConnectionPatch as _ConPatch

        if has_exp and self.ax2 is not None:
            _ref_ax = self.ax2
            # Y-range: actual exp values inside [xl, xh] on the main plot ax2
            _ind_ys = []
            for _d in self._inset_plot_data:
                if _d[0] == "exp":
                    _dx, _dy = _d[1], _d[2]
                    _m = (_dx >= xl) & (_dx <= xh)
                    if _m.sum():
                        _ind_ys.extend(_dy[_m].tolist())
            if _ind_ys:
                _rect_yl = min(0.0, float(np.min(_ind_ys)))
                _rect_yh = float(np.max(_ind_ys)) * 1.08
                _rect_yh = max(_rect_yh, _rect_yl + 0.05)
            else:
                _rect_yl, _rect_yh = 0.0, 1.1
        else:
            _ref_ax  = self.ax
            _rect_yl = yl  if yl is not None else self.ax.get_ylim()[0]
            _rect_yh = yh  if yh is not None else self.ax.get_ylim()[1]

        _rect = _Rect(
            (xl, _rect_yl), xh - xl, _rect_yh - _rect_yl,
            linewidth=1.2, edgecolor="black", facecolor="none",
            linestyle="--", alpha=0.8, transform=_ref_ax.transData, zorder=5,
        )
        _ref_ax.add_patch(_rect)

        # Connector lines: two ConnectionPatch objects linking facing corners of
        # the indicator rectangle (in _ref_ax data coords) to the inset axes
        # corners (in inset_ax axes-fraction coords).
        #
        # ConnectionPatch stores coordinates in axis-relative terms and
        # recomputes screen positions on every render — so it works correctly
        # after figure resize AND after pickle-copy to the pop-out window.
        _connectors = []
        try:
            # Determine whether the inset is to the left or right of the
            # indicator rectangle by comparing their centres in axes-fraction.
            _xl_lim, _xr_lim = _ref_ax.get_xlim()
            _x_span = (_xr_lim - _xl_lim) if _xr_lim != _xl_lim else 1.0
            _rect_cx_frac = ((xl + xh) / 2.0 - _xl_lim) / _x_span
            _ins_cx_frac  = self._inset_pos[0] + self._inset_pos[2] / 2.0

            if _ins_cx_frac >= _rect_cx_frac:
                # Inset to the RIGHT → connect right edge of rect to left edge of inset
                _pairs = [
                    ((xh, _rect_yh), (0.0, 1.0)),   # rect top-right    → inset top-left
                    ((xh, _rect_yl), (0.0, 0.0)),   # rect bottom-right → inset bottom-left
                ]
            else:
                # Inset to the LEFT → connect left edge of rect to right edge of inset
                _pairs = [
                    ((xl, _rect_yh), (1.0, 1.0)),   # rect top-left    → inset top-right
                    ((xl, _rect_yl), (1.0, 0.0)),   # rect bottom-left → inset bottom-right
                ]

            for _xyA, _xyB in _pairs:
                _con = _ConPatch(
                    xyA=_xyA, coordsA="data",           axesA=_ref_ax,
                    xyB=_xyB, coordsB="axes fraction",  axesB=inset_ax,
                    color="black", linewidth=0.8,
                    alpha=0.6, linestyle="--",
                    arrowstyle="-",
                )
                self.fig.add_artist(_con)
                _connectors.append(_con)
        except Exception:
            pass   # connectors are cosmetic — skip if anything goes wrong

        self._inset_indicator = (_rect, _connectors)

    # ── Inset drag support ────────────────────────────────────────────────────

    def _setup_inset_drag(self):
        """Connect mouse events for dragging the inset."""
        for cid in self._inset_drag_cids:
            try: self.canvas.mpl_disconnect(cid)
            except Exception: pass
        self._inset_drag_cids = []
        if not self._inset_active:
            return
        self._inset_drag_cids = [
            self.canvas.mpl_connect("button_press_event",   self._inset_on_press),
            self.canvas.mpl_connect("motion_notify_event",  self._inset_on_motion),
            self.canvas.mpl_connect("button_release_event", self._inset_on_release),
        ]

    def _inset_on_press(self, event):
        # Use pixel bbox hit-testing — event.inaxes is unreliable for inset axes
        # in the TkAgg backend because the axes locator isn't registered the same way.
        if self._inset_ax is None or event.x is None or event.y is None:
            return
        try:
            bbox = self._inset_ax.get_window_extent()
        except Exception:
            return
        if not bbox.contains(event.x, event.y):
            return
        self._inset_drag = {
            "x0":   event.x,
            "y0":   event.y,
            "pos0": list(self._inset_pos),
        }

    def _inset_on_motion(self, event):
        if self._inset_drag is None or event.x is None:
            return
        # Skip if toolbar is active (zoom/pan mode)
        if self.toolbar.mode != "":
            return
        ax_bb = self.ax.get_window_extent()
        if ax_bb.width == 0 or ax_bb.height == 0:
            return
        dx = (event.x - self._inset_drag["x0"]) / ax_bb.width
        dy = (event.y - self._inset_drag["y0"]) / ax_bb.height
        p0 = self._inset_drag["pos0"]
        new_l = float(np.clip(p0[0] + dx, 0.0, 1.0 - p0[2]))
        new_b = float(np.clip(p0[1] + dy, 0.0, 1.0 - p0[3]))
        # Only redraw if position changed by at least 0.5% to avoid thrashing
        if (abs(new_l - self._inset_pos[0]) > 0.005 or
                abs(new_b - self._inset_pos[1]) > 0.005):
            self._inset_pos[0] = new_l
            self._inset_pos[1] = new_b
            self._quick_move_inset()

    def _inset_on_release(self, event):
        self._inset_drag = None   # position already saved; full replot not needed

    def _quick_move_inset(self):
        """Remove old inset artists and re-draw at updated _inset_pos (no full replot)."""
        # Remove old inset axes
        for ax in [self._inset_ax, self._inset_ax2]:
            if ax is not None:
                try: ax.remove()
                except Exception: pass
        self._inset_ax  = None
        self._inset_ax2 = None
        # Remove the stored indicator (rectangle + connector arrows) by direct reference.
        # This is the only reliable way — attribute-scanning misses FancyArrowPatch objects.
        if self._inset_indicator is not None:
            rect, connectors = self._inset_indicator
            try: rect.remove()
            except Exception: pass
            for c in (connectors or []):
                try: c.remove()
                except Exception: pass
            self._inset_indicator = None
        self._draw_inset()
        self.canvas.draw_idle()

    def _draw_transition_labels(self, x_arr, y_arr, sp: TDDFTSpectrum):
        for i, state in enumerate(sp.excited_states):
            if i >= len(x_arr):
                break
            if not state.transitions:
                continue
            dom = max(state.transitions, key=lambda t: t[2])
            self.ax.annotate(
                f"{dom[0]}\u2192{dom[1]} ({dom[2]:.2f})",
                xy=(x_arr[i], y_arr[i]),
                xytext=(0, 8), textcoords="offset points",
                fontsize=6, ha="center", color="gray", rotation=70
            )

    # ══════════════════════════════════════════════════════════════════════════
    #  Hover tooltip
    # ══════════════════════════════════════════════════════════════════════════
    def _setup_hover(self):
        if self._hover_cid is not None:
            try:
                self.canvas.mpl_disconnect(self._hover_cid)
            except Exception:
                pass
        if self._annot is not None:
            try:
                self._annot.remove()
            except Exception:
                pass
        self._annot = self.ax.annotate(
            "", xy=(0, 0), xytext=(18, 60), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc="lightyellow", ec="gray", alpha=0.92),
            arrowprops=dict(arrowstyle="->", color="dimgray", lw=1.2,
                            connectionstyle="arc3,rad=0.15"),
            fontsize=8, visible=False
        )
        self._hover_cid = self.canvas.mpl_connect("motion_notify_event", self._on_hover)

    def _on_hover(self, event):
        # Never interfere while the toolbar is in zoom-rect or pan mode.
        # Our draw_idle() call corrupts the rubber-band overlay if we fire during a drag.
        if self.toolbar.mode != "":
            return
        valid = {self.ax} | ({self.ax2} if self.ax2 is not None else set())
        if event.inaxes not in valid or len(self._hover_x) == 0:
            if self._annot and self._annot.get_visible():
                self._annot.set_visible(False)
                self.canvas.draw_idle()
            return

        dists = np.abs(self._hover_x - event.xdata)
        idx   = int(np.argmin(dists))
        rng   = (self._hover_x.max() - self._hover_x.min()) if len(self._hover_x) > 1 else 1
        if rng > 0 and dists[idx] > rng * 0.05:
            self._annot.set_visible(False)
            self.canvas.draw_idle()
            return

        ev  = self._hover_ev[idx]
        cm  = self._hover_cm[idx] if idx < len(self._hover_cm) else ev * 8065.54
        nm  = 1239.84 / ev if ev > 0 else 0
        fy  = self._hover_y[idx]
        _sp0 = self._tddft_spectra[0]["spectrum"] if self._tddft_spectra else None
        lbl = "R" if (_sp0 and _sp0.is_cd()) else "f"

        delta_e = self._delta_e.get()

        # State identifier: use actual root number + transition label if available
        if self._hover_states and idx < len(self._hover_states):
            root = self._hover_states[idx]
            if self._hover_labels and idx < len(self._hover_labels):
                tip = [f"State {root}  \u2014  {self._hover_labels[idx]}"]
            else:
                tip = [f"State {root}"]
        else:
            tip = [f"State {idx + 1}"]

        if abs(delta_e) > 1e-4:
            tip.append(f"Shifted: {ev:.4f} eV  (orig. {ev - delta_e:.4f} eV)")
        else:
            tip.append(f"{ev:.4f} eV  |  {nm:.2f} nm  |  {cm:.0f} cm\u207b\u00b9")
        tip.append(f"{lbl} = {fy:.6f}")

        if (_sp0 and _sp0.excited_states and
                idx < len(_sp0.excited_states)):
            es = _sp0.excited_states[idx]
            if not es.transitions:
                tip.append("\u2500" * 28)
                tip.append("(no CI vectors in output file)")
            if es.transitions:
                # Sort all contributions by weight (c²) descending.
                # Show every transition ≥ 1%, or at minimum the top 1.
                # c² is stored directly in the tuple (captured before "(c=" in the regex).
                sorted_t = sorted(es.transitions, key=lambda t: t[2], reverse=True)
                threshold = 0.01   # 1 %
                shown = [t for t in sorted_t if t[2] >= threshold]
                if not shown:
                    shown = sorted_t[:1]   # always show at least the dominant one
                shown = shown[:8]          # cap at 8 lines to keep tooltip readable
                tip.append("\u2500" * 28)
                tip.append("Acceptor orbitals (MO\u1d47 \u2192 MO\u1d43):")
                for fr, to, w2 in shown:
                    bar = "\u2588" * int(w2 * 20 + 0.5)   # mini bar up to 20 chars
                    # ORCA outputs 0-based MO indices directly — display as-is
                    tip.append(f"  {fr:3d} \u2192 {to:3d}   {w2*100:5.1f}%  {bar}")
                if len(sorted_t) > len(shown):
                    rest_w = sum(t[2] for t in sorted_t[len(shown):])
                    tip.append(f"  ... {len(sorted_t)-len(shown)} more  ({rest_w*100:.1f}% total)")

        self._annot.set_text("\n".join(tip))
        self._annot.xy = (self._hover_x[idx], self._hover_y[idx])
        self._annot.set_visible(True)
        self.canvas.draw_idle()

    def _toggle_legend(self):
        """Called when the Legend checkbox is clicked.
        Resets the saved position so the legend returns to 'best' on next show."""
        self._legend_bbox = None
        self._replot()

    def _on_legend_press(self, event):
        """Record that a mouse button was pressed (drag detection start)."""
        self._legend_dragging = False   # reset; motion will set to True

    def _on_legend_motion(self, event):
        """Mark that a drag is in progress (mouse moved while button held)."""
        if event.button is not None:
            self._legend_dragging = True

    def _on_legend_release(self, event):
        """Save the legend's upper-left corner in figure-fraction coordinates
        — but ONLY if a real drag happened (not a plain click)."""
        if not self._legend_dragging:
            return
        self._legend_dragging = False
        if self._legend_ref is None:
            return
        try:
            # get_window_extent() → display-pixel Bbox of the legend frame
            bb  = self._legend_ref.get_window_extent()
            # Convert the UPPER-LEFT corner to figure-fraction.
            # We consistently restore with loc="upper left" so we always
            # anchor the top-left — no drift across successive drags.
            inv       = self.fig.transFigure.inverted()
            x_fig, y_fig = inv.transform((bb.x0, bb.y1))
            self._legend_bbox = (x_fig, y_fig)
        except Exception:
            pass   # silently ignore if legend was removed mid-drag

    def _update_comb_ui(self):
        """No-op — component toggles now live in each spectrum's detail panel."""
        pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Export
    # ══════════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════════
    #  Pop-out graph window
    # ══════════════════════════════════════════════════════════════════════════
    def _notify_popouts(self):
        """Call every registered pop-out refresh callback (skip dead windows)."""
        if not self._popout_callbacks:
            return
        alive = []
        for cb in self._popout_callbacks:
            try:
                cb()
                alive.append(cb)
            except Exception:
                pass  # window was already destroyed — silently drop
        self._popout_callbacks = alive

    def _pop_out_graph(self):
        """Open the current graph in a standalone, resizable window.

        The pop-out is a deep copy of the live figure, so it is independent of
        the embedded panel — you can zoom/pan/save it without affecting the
        main view.  The figure auto-resizes as you drag the window border.
        """
        import pickle
        import io as _io

        # Make sure the figure is fully up to date before copying
        self._replot()

        # ── Helper: deep-copy the current live figure ─────────────────────────
        def _copy_fig():
            buf = _io.BytesIO()
            pickle.dump(self.fig, buf)
            buf.seek(0)
            f = pickle.load(buf)
            f.set_size_inches(12, 7)
            try:
                f.set_layout_engine("tight")
            except AttributeError:
                f.tight_layout()
            return f

        try:
            fig_copy = _copy_fig()
        except Exception as exc:
            messagebox.showerror(
                "Pop Out — Error",
                f"Could not copy the figure:\n{exc}\n\n"
                "Try saving to SVG/PDF as a workaround.",
            )
            return

        # Mutable reference so save always uses the latest figure object
        fig_ref = [fig_copy]

        # ── Build the Toplevel ────────────────────────────────────────────────
        win = tk.Toplevel(self)
        win.title("Graph — Pop Out  (resize freely)")
        win.geometry("1200x760")
        win.resizable(True, True)
        win.minsize(600, 400)

        # ── Top status / control bar ──────────────────────────────────────────
        top_bar = tk.Frame(win, bd=1, relief=tk.SUNKEN,
                           padx=6, pady=3, bg="#e8eef8")
        top_bar.pack(side=tk.TOP, fill=tk.X)

        auto_update_var = tk.BooleanVar(value=True)

        tk.Label(top_bar, text="Pop-Out Controls:", font=("", 9, "bold"),
                 bg="#e8eef8").pack(side=tk.LEFT, padx=(0, 8))

        tk.Checkbutton(
            top_bar, text="Auto Update  (syncs with main panel on every replot)",
            variable=auto_update_var, bg="#e8eef8", font=("", 9),
            fg="#003399",
        ).pack(side=tk.LEFT, padx=4)

        def _do_refresh():
            """Re-copy the live figure into this pop-out canvas."""
            try:
                new_fig = _copy_fig()
                canvas_po.figure = new_fig
                fig_ref[0] = new_fig
                toolbar_po.update()
                canvas_po.draw_idle()
            except Exception as exc:
                messagebox.showerror("Refresh Error", str(exc), parent=win)

        tk.Button(top_bar, text="\u21ba Refresh Now", command=_do_refresh,
                  font=("", 9, "bold"), bg="#cce0ff",
                  relief=tk.RAISED).pack(side=tk.LEFT, padx=8)

        tk.Label(top_bar,
                 text="Toolbar below: zoom \u00b7 pan \u00b7 home \u00b7 save",
                 font=("", 8), fg="gray", bg="#e8eef8").pack(side=tk.RIGHT, padx=6)

        # Embed the copied figure
        canvas_po = FigureCanvasTkAgg(fig_copy, master=win)
        canvas_po.draw()
        cw = canvas_po.get_tk_widget()
        cw.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Matplotlib navigation toolbar (zoom, pan, home, back/forward, save)
        tb_frame = tk.Frame(win, bd=1, relief=tk.FLAT)
        tb_frame.pack(side=tk.TOP, fill=tk.X)
        toolbar_po = NavigationToolbar2Tk(canvas_po, tb_frame)
        toolbar_po.update()

        # ── Bottom button row ─────────────────────────────────────────────────
        btn_row = tk.Frame(win, bd=1, relief=tk.SUNKEN, padx=6, pady=4)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X)

        def _save_popout():
            path = filedialog.asksaveasfilename(
                defaultextension=".svg",
                filetypes=[
                    ("SVG — vector, best for Word/Illustrator", "*.svg"),
                    ("PDF — vector, best for LaTeX / Acrobat",  "*.pdf"),
                    ("EPS — vector, journals / Illustrator",    "*.eps"),
                    ("PNG — raster 600 dpi, for presentations", "*.png"),
                    ("All files", "*.*"),
                ],
                title="Save Pop-Out Figure",
                parent=win,
            )
            if not path:
                return
            ext  = _os.path.splitext(path)[1].lower()
            fig_cur = fig_ref[0]
            skw  = dict(bbox_inches="tight", facecolor=fig_cur.get_facecolor())
            if ext == ".png":
                skw["dpi"] = 600
            elif ext in (".pdf", ".eps"):
                skw["backend"] = "pdf" if ext == ".pdf" else "ps"
            try:
                fig_cur.savefig(path, **skw)
                messagebox.showinfo(
                    "Saved", f"Figure saved to:\n{path}", parent=win)
            except Exception as exc:
                messagebox.showerror(
                    "Save Error", f"Could not save:\n{exc}", parent=win)

        tk.Button(btn_row, text="Save Figure\u2026", command=_save_popout,
                  font=("", 9), relief=tk.RAISED).pack(side=tk.LEFT, padx=4)

        tk.Button(btn_row, text="Close", command=lambda: _on_close(),
                  font=("", 9)).pack(side=tk.RIGHT, padx=4)

        # ── Auto-update callback registered with the main widget ──────────────
        def _auto_refresh():
            """Called by _notify_popouts() after every main _replot()."""
            if auto_update_var.get():
                _do_refresh()

        self._popout_callbacks.append(_auto_refresh)

        def _on_close():
            try:
                self._popout_callbacks.remove(_auto_refresh)
            except ValueError:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)

        # ── Auto-tight on window resize ───────────────────────────────────────
        def _on_win_resize(event):
            if event.widget is win:
                try:
                    fig_ref[0].tight_layout()
                    canvas_po.draw_idle()
                except Exception:
                    pass

        win.bind("<Configure>", _on_win_resize)

        # Focus the new window so it's on top
        win.focus_force()

    def _save_figure(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".svg",
            filetypes=[
                ("SVG — vector, best for Word/Illustrator", "*.svg"),
                ("PDF — vector, best for LaTeX / Acrobat",  "*.pdf"),
                ("EPS — vector, journals / Illustrator",    "*.eps"),
                ("PNG — raster 600 dpi, for presentations", "*.png"),
                ("All files", "*.*"),
            ],
            title="Save Figure  (SVG / PDF / EPS = vector; PNG = high-res raster)",
        )
        if not path:
            return

        ext = _os.path.splitext(path)[1].lower()

        # Vector formats: no dpi needed — matplotlib writes true vector paths.
        # PNG: use 600 dpi so it's still sharp when resized in a document.
        save_kw = dict(bbox_inches="tight", facecolor=self.fig.get_facecolor())
        if ext == ".png":
            save_kw["dpi"] = 600
        elif ext in (".pdf", ".eps"):
            # Embed fonts so the file is self-contained
            save_kw["backend"] = "pdf" if ext == ".pdf" else "ps"

        try:
            self.fig.savefig(path, **save_kw)
        except Exception as exc:
            messagebox.showerror("Save Error", f"Could not save figure:\n{exc}")
            return

        fmt_hint = {
            ".svg": "SVG vector — insert into Word via Insert → Pictures → SVG.",
            ".pdf": "PDF vector — drag into Illustrator / LaTeX \\includegraphics.",
            ".eps": "EPS vector — use with Illustrator or LaTeX.",
            ".png": "PNG 600 dpi — paste directly into Word or PowerPoint.",
        }.get(ext, "")
        messagebox.showinfo("Figure Saved",
                            f"Saved to:\n{path}\n\n{fmt_hint}")

    def _export_csv(self):
        sp = self._tddft_spectra[0]["spectrum"] if self._tddft_spectra else None
        if not sp:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV","*.csv"),("All","*.*")],
            title="Export CSV"
        )
        if not path:
            return
        is_cd   = sp.is_cd()
        is_comb = bool(sp.fosc_d2)
        delta_e = self._delta_e.get()
        with open(path, "w") as f:
            if is_cd:
                hdr = "State,Label,Energy_eV,Energy_eV_shifted,Energy_cm,Wavelength_nm,RotatoryStrength"
            elif is_comb:
                hdr = "State,Label,Energy_eV,Energy_eV_shifted,Energy_cm,Wavelength_nm,Fosc_Total,Fosc_D2,Fosc_m2,Fosc_Q2"
            else:
                hdr = "State,Label,Energy_eV,Energy_eV_shifted,Energy_cm,Wavelength_nm,Fosc"
            f.write(hdr + "\n")
            n = len(sp.states)
            for i in range(n):
                lbl  = sp.transition_labels[i] if i < len(sp.transition_labels) else str(sp.states[i])
                ev   = sp.energies_ev[i]    if i < len(sp.energies_ev)    else 0
                cm   = sp.energies_cm[i]    if i < len(sp.energies_cm)    else 0
                nm   = sp.wavelengths_nm[i] if i < len(sp.wavelengths_nm) else 0
                ev_s = ev + delta_e
                if is_cd:
                    val = sp.rotatory_strength[i] if i < len(sp.rotatory_strength) else 0
                    row = f"{sp.states[i]},{lbl},{ev:.6f},{ev_s:.6f},{cm:.2f},{nm:.4f},{val:.8f}"
                elif is_comb:
                    ft  = sp.fosc[i]    if i < len(sp.fosc)    else 0
                    fd2 = sp.fosc_d2[i] if i < len(sp.fosc_d2) else 0
                    fm2 = sp.fosc_m2[i] if i < len(sp.fosc_m2) else 0
                    fq2 = sp.fosc_q2[i] if i < len(sp.fosc_q2) else 0
                    row = f"{sp.states[i]},{lbl},{ev:.6f},{ev_s:.6f},{cm:.2f},{nm:.4f},{ft:.8f},{fd2:.8f},{fm2:.8e},{fq2:.8e}"
                else:
                    val = sp.fosc[i] if i < len(sp.fosc) else 0
                    row = f"{sp.states[i]},{lbl},{ev:.6f},{ev_s:.6f},{cm:.2f},{nm:.4f},{val:.8f}"
                f.write(row + "\n")
        messagebox.showinfo("Exported", f"Data saved to:\n{path}")


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sep(parent):
    ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)


def _slider_row(parent, label: str, var: tk.DoubleVar,
                lo: float, hi: float, res: float, row: int, unit: str = ""):
    """Label | editable numeric entry [unit] | slider — all in a 4-column grid.

    Columns: 0 = label, 1 = entry, 2 = unit label, 3 = slider.
    The entry is editable: type a value and press Enter (or click away) to commit.
    """
    fmt = (lambda v: f"{v:.2f}") if res < 1 else (lambda v: f"{int(v)}")

    tk.Label(parent, text=label, font=("", 9)).grid(
        row=row, column=0, sticky="e", padx=(0, 4), pady=2)

    # ── Editable numeric entry ───────────────────────────────────────────────
    _busy = [False]   # guard against circular update
    entry_var = tk.StringVar(value=fmt(var.get()))

    entry = tk.Entry(parent, textvariable=entry_var, width=7,
                     font=("Courier", 9), justify="right")
    entry.grid(row=row, column=1, sticky="ew", padx=(0, 2))

    # Unit label (column 2)
    tk.Label(parent, text=unit, font=("", 8), fg="gray",
             anchor="w", width=4).grid(row=row, column=2, sticky="w")

    # ── Slider (column 3) ────────────────────────────────────────────────────
    sl = tk.Scale(parent, from_=lo, to=hi, resolution=res,
                  orient=tk.HORIZONTAL, length=160,
                  variable=var, showvalue=False)
    sl.grid(row=row, column=3, sticky="w")

    # Keep entry in sync when slider moves
    def _var_to_entry(*_):
        if not _busy[0]:
            entry_var.set(fmt(var.get()))

    var.trace_add("write", _var_to_entry)

    # Commit typed value → var + slider
    def _entry_to_var(*_):
        try:
            v = float(entry_var.get().replace(",", "."))
            v = max(lo, min(hi, v))
            _busy[0] = True
            var.set(v)
            entry_var.set(fmt(v))
            _busy[0] = False
        except ValueError:
            entry_var.set(fmt(var.get()))   # revert to last good value

    entry.bind("<Return>",   _entry_to_var)
    entry.bind("<FocusOut>", _entry_to_var)
    _var_to_entry()   # initialise display


def _centre_window(win: tk.Toplevel, parent: tk.Widget):
    win.update_idletasks()
    px = parent.winfo_rootx() + (parent.winfo_width()  - win.winfo_width())  // 2
    py = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{px}+{py}")
