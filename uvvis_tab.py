"""
uvvis_tab.py — UV/Vis/NIR analysis tab for Ptarmigan

Phase 4a (loader migration): the tab now reads from a ProjectGraph
rather than a private `_entries` list. File load creates a COMMITTED
RAW_FILE DataNode + LOAD OperationNode + COMMITTED UVVIS DataNode
wired together (CS-13 §"Implementation notes (Phase 4a)"). No
analysis runs automatically — parsing the on-disk format into arrays
is bookkeeping, not science.
"""

from __future__ import annotations

import os
import uuid
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
from graph import ProjectGraph
from nodes import (
    DataNode,
    NodeState,
    NodeType,
    OperationNode,
    OperationType,
)
from version import __version__ as PTARMIGAN_VERSION

# ── Colour palette (loader-side default colour assignment) ────────────────────
# Phase 2 friction #3: the UVVIS DataNode receives ``style["color"]`` at
# creation so the StyleDialog opens with a non-empty starting colour.
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
def _default_uvvis_style(colour: str) -> dict:
    """Default ``DataNode.style`` for a freshly-loaded UVVIS node.

    Mirrors ``scan_tree_widget._DEFAULT_STYLE`` so that row controls
    and the unified style dialog read/write the same dict. ``visible``
    and ``in_legend`` move into the style dict (Phase 2 friction #2).
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

# ── Linestyle radio options (display name → mpl value) ───────────────────────
_LS_OPTIONS = [
    ("Solid",    "solid"),
    ("Dashed",   "dashed"),
    ("Dotted",   "dotted"),
    ("Dash-dot", "dashdot"),
]

# ── Lightweight hover tooltip ─────────────────────────────────────────────────
class _ToolTip:
    def __init__(self, widget, text: str, delay: int = 500):
        self._w, self._text, self._delay = widget, text, delay
        self._id = self._win = None
        widget.bind("<Enter>",  self._schedule, add="+")
        widget.bind("<Leave>",  self._cancel,   add="+")
        widget.bind("<Button>", self._cancel,   add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._id = self._w.after(self._delay, self._show)

    def _cancel(self, _=None):
        if self._id:
            self._w.after_cancel(self._id); self._id = None
        if self._win:
            self._win.destroy(); self._win = None

    def _show(self):
        x = self._w.winfo_rootx() + self._w.winfo_width() + 4
        y = self._w.winfo_rooty()
        self._win = tw = tk.Toplevel(self._w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self._text, background="#ffffe0",
                 relief=tk.SOLID, borderwidth=1, font=("", 8)).pack()

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
        self._norm_mode   = tk.StringVar(value="none")

        # ── Axis limits (empty string = auto) ────────────────────────────────
        self._xlim_lo = tk.StringVar(value="")
        self._xlim_hi = tk.StringVar(value="")
        self._ylim_lo = tk.StringVar(value="")
        self._ylim_hi = tk.StringVar(value="")

        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    #  Graph helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _uvvis_nodes(self) -> List[DataNode]:
        """Return the UVVIS DataNodes the tab considers "live".

        Live = state != DISCARDED *and* ``active`` is True. The list
        preserves insertion order (Python 3.7+ dict is ordered) so the
        sidebar's row order is deterministic across rebuilds.
        """
        out: List[DataNode] = []
        for node in self._graph.nodes_of_type(NodeType.UVVIS, state=None):
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
    #  Table rebuild  (Part B will replace this with ScanTreeWidget)
    # ══════════════════════════════════════════════════════════════════════════

    def _rebuild_table(self):
        for w in self._tbl_inner.winfo_children():
            w.destroy()

        nodes = self._uvvis_nodes()
        if not nodes:
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

        tbl.columnconfigure(1, weight=1, minsize=120)
        tbl.columnconfigure(0, minsize=40)
        tbl.columnconfigure(2, minsize=28)
        tbl.columnconfigure(3, minsize=44)
        tbl.columnconfigure(4, minsize=28)
        tbl.columnconfigure(5, minsize=28)
        tbl.columnconfigure(6, minsize=24)
        tbl.columnconfigure(7, minsize=28)

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
            (3, "LS",     "center", CPX),
            (4, "LW",     "center", CPX),
            (5, "Fill",   "center", CPX),
            (6, "",       "center", CPX),
            (7, "",       "center", RPX),
        ]:
            tk.Label(tbl, text=txt, font=FHD, bg=HDR_BG, fg="#444444",
                     anchor=anch, padx=3,
                     ).grid(row=0, column=col, sticky="ew", ipady=1, padx=px)

        # ── Helpers ───────────────────────────────────────────────────────────
        def _make_leg_btn(parent, node, r, c):
            v = tk.BooleanVar(value=bool(node.style.get("in_legend", True)))
            b = tk.Button(parent, width=2, font=F9, relief=tk.FLAT)
            def _refresh(_b=b, _v=v):
                _b.config(text="✓" if _v.get() else "–",
                          fg="#006600" if _v.get() else "#999999")
            def _toggle(nid=node.id, _b=b, _v=v):
                _v.set(not _v.get()); _refresh()
                self._graph.set_style(nid, {"in_legend": bool(_v.get())})
                self._redraw()
            b.config(command=_toggle)
            _refresh()
            b.grid(row=r, column=c, padx=CPX, pady=0, sticky="ew")

        def _make_ls_canvas(parent, node, r, c):
            W, H = 38, 16
            cv = tk.Canvas(parent, width=W, height=H,
                           bd=1, relief=tk.SUNKEN, bg="white",
                           highlightthickness=0, cursor="hand2")

            def _draw(_cv=cv, _node=node):
                _cv.delete("all")
                style = _node.style
                ls   = style.get("linestyle", "solid")
                clr  = style.get("color", "#333333")
                lw   = max(0.5, float(style.get("linewidth", 1.5)))
                dash = _LS_DASH.get(ls, ())
                kw   = {"fill": clr, "width": lw, "capstyle": "round"}
                if dash:
                    kw["dash"] = dash
                _cv.create_line(4, H // 2, W - 4, H // 2, **kw)

            def _cycle(_event=None, _node=node):
                ls  = _node.style.get("linestyle", "solid")
                idx = _LS_CYCLE.index(ls) if ls in _LS_CYCLE else 0
                new = _LS_CYCLE[(idx + 1) % len(_LS_CYCLE)]
                self._graph.set_style(_node.id, {"linestyle": new})
                _draw()
                self._redraw()

            cv.bind("<Button-1>", _cycle)
            _draw()
            cv.grid(row=r, column=c, padx=CPX, pady=2, sticky="")

        def _make_lw_entry(parent, node, r, c):
            v = tk.DoubleVar(value=float(node.style.get("linewidth", 1.5)))
            def _cb(*_, nid=node.id, _v=v):
                try:
                    val = float(_v.get())
                except Exception:
                    return
                self._graph.set_style(nid, {"linewidth": val})
                self._redraw()
            v.trace_add("write", _cb)
            e = tk.Entry(parent, textvariable=v, width=4,
                         font=("Courier", 8), justify="center")
            e.grid(row=r, column=c, padx=CPX, pady=0, sticky="ew")

        # ── Data rows ─────────────────────────────────────────────────────────
        for i, node in enumerate(nodes):
            r      = i + 1
            colour = node.style.get("color", "#333333")

            # Col 0: colour swatch — click to change
            def _pick(nid=node.id):
                old = self._graph.get_node(nid).style.get("color", "#1f77b4")
                result = colorchooser.askcolor(color=old,
                                               title="Pick spectrum colour")
                if result and result[1]:
                    self._graph.set_style(nid, {"color": result[1]})
                    self._rebuild_table()
                    self._redraw()
            tk.Button(tbl, bg=colour, relief=tk.RAISED, width=3,
                      text="UV", fg="white", font=("", 7, "bold"),
                      activebackground=colour, cursor="hand2",
                      command=_pick,
                      ).grid(row=r, column=0, padx=SPX, pady=1, sticky="w")

            # Col 1: visibility checkbox + label
            vis_var = tk.BooleanVar(value=bool(node.style.get("visible", True)))
            def _vis_cb(*_, nid=node.id, v=vis_var):
                self._graph.set_style(nid, {"visible": bool(v.get())})
                self._redraw()
            vis_var.trace_add("write", _vis_cb)
            tk.Checkbutton(tbl, text=node.label, variable=vis_var,
                           anchor="w", font=F9,
                           wraplength=200, justify=tk.LEFT,
                           ).grid(row=r, column=1, sticky="ew",
                                  padx=(6, 4), pady=0)

            # Col 2: legend toggle
            _make_leg_btn(tbl, node, r, 2)

            # Col 3: linestyle canvas (click to cycle)
            _make_ls_canvas(tbl, node, r, 3)

            # Col 4: linewidth
            _make_lw_entry(tbl, node, r, 4)

            # Col 5: fill checkbox
            fill_var = tk.BooleanVar(value=bool(node.style.get("fill", False)))
            def _fill_cb(*_, nid=node.id, v=fill_var):
                self._graph.set_style(nid, {"fill": bool(v.get())})
                self._redraw()
            fill_var.trace_add("write", _fill_cb)
            tk.Checkbutton(tbl, variable=fill_var,
                           ).grid(row=r, column=5, padx=CPX, pady=0,
                                  sticky="ew")

            # Col 6: style dialog
            _gear = tk.Button(tbl, text="⚙", font=F8, relief=tk.FLAT,
                              cursor="hand2",
                              command=lambda nid=node.id: self._open_style_dialog(nid))
            _gear.grid(row=r, column=6, padx=CPX, pady=0, sticky="ew")
            _ToolTip(_gear, "Edit full style…")

            # Col 7: remove
            tk.Button(tbl, text="✕", font=F8, relief=tk.FLAT,
                      command=lambda nid=node.id: self._remove_entry(nid),
                      ).grid(row=r, column=7, padx=RPX, pady=0, sticky="e")

        self._tbl_canvas.update_idletasks()
        self._tbl_canvas.configure(
            scrollregion=self._tbl_canvas.bbox("all"))
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
                    if self._has_existing_load(scan.source_file, scan.label):
                        continue
                    self._load_uvvis_scan(path, scan)
                    n_loaded += 1
            except Exception as exc:
                messagebox.showerror(
                    "Load error",
                    f"Could not read {os.path.basename(path)}:\n{exc}")

        if n_loaded:
            self._rebuild_table()
            self._redraw()
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
        existing_count = len(self._graph.nodes_of_type(NodeType.UVVIS, state=None))
        colour = _PALETTE[existing_count % len(_PALETTE)]

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
            style=_default_uvvis_style(colour),
        )

        self._graph.add_node(raw_node)
        self._graph.add_node(op_node)
        self._graph.add_node(uvvis_node)
        self._graph.add_edge(raw_id, op_id)
        self._graph.add_edge(op_id, uvvis_id)
        return raw_id, op_id, uvvis_id

    def _remove_entry(self, node_id: str):
        """✕ button: discard provisional, soft-hide committed.

        Mirrors ScanTreeWidget._on_x_clicked semantics (CS-04 §6.1) so
        Part B's swap to ScanTreeWidget is a no-op for the user.
        """
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return
        if not isinstance(node, DataNode):
            return
        if node.state == NodeState.PROVISIONAL:
            self._graph.discard_node(node_id)
        elif node.state == NodeState.COMMITTED:
            self._graph.set_active(node_id, False)
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

    def _y_with_norm(self, absorbance: np.ndarray,
                     wavelength_nm: np.ndarray) -> np.ndarray:
        y = _absorbance_to_y(absorbance, self._y_unit.get())
        mode = self._norm_mode.get()
        if mode == "peak":
            pk = np.nanmax(np.abs(y))
            if pk > 0: y = y / pk
        elif mode == "area":
            area = np.trapz(np.abs(y), wavelength_nm)
            if area > 0: y = y / area
        return y

    def _redraw(self, *_):
        # Walk the ProjectGraph for live UVVIS nodes whose style has
        # them visible; fall back to the empty-state placeholder when
        # nothing is loaded or every loaded node is hidden.
        live = [n for n in self._uvvis_nodes()
                if bool(n.style.get("visible", True))]

        if not live:
            self._draw_empty()
            return

        self._fig.clear()
        self._ax = self._fig.add_subplot(111)
        ax   = self._ax
        unit = self._x_unit.get()

        for node in live:
            style  = node.style
            colour = style.get("color", "#333333")
            wl     = node.arrays["wavelength_nm"]
            absorb = node.arrays["absorbance"]
            x = _wavelength_to_x(wl, unit)
            y = self._y_with_norm(absorb, wl)
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

        # ── Legend ────────────────────────────────────────────────────────────
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=8, loc="best", framealpha=0.7)

        ax.grid(True, linestyle=":", alpha=0.4)
        self._fig.tight_layout()
        self._canvas.draw_idle()
        self._toolbar.update()

    # ══════════════════════════════════════════════════════════════════════════
    #  Per-scan style dialog (legacy — Part C will delete this)
    # ══════════════════════════════════════════════════════════════════════════

    def _open_style_dialog(self, node_id: str):
        try:
            node = self._graph.get_node(node_id)
        except KeyError:
            return
        if not isinstance(node, DataNode):
            return
        style = node.style

        win = tk.Toplevel(self)
        win.title("Spectrum Style")
        win.resizable(False, False)
        win.grab_set()

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg="#003d7a", padx=10, pady=6)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="UV/Vis Spectrum Style",
                 bg="#003d7a", fg="white",
                 font=("", 10, "bold")).pack(anchor="w")
        name = node.label
        tk.Label(hdr, text=(name[:60] + "…") if len(name) > 60 else name,
                 bg="#003d7a", fg="#aaccff", font=("", 8)).pack(anchor="w")

        body = tk.Frame(win, padx=12, pady=8)
        body.pack(fill=tk.BOTH)
        body.columnconfigure(1, weight=1)

        # ── Helpers ───────────────────────────────────────────────────────────

        def _push_to_all(key, get_fn):
            def _do():
                val = get_fn()
                for other in self._uvvis_nodes():
                    self._graph.set_style(other.id, {key: val})
                self._rebuild_table()
                self._redraw()
            return _do

        def _all_btn(row, col, fn, tip="Apply to all spectra"):
            b = tk.Button(body, text="∀", font=("", 8), relief=tk.FLAT,
                          cursor="hand2", fg="#004400", activeforeground="#006600",
                          command=fn)
            b.grid(row=row, column=col, padx=(2, 0), sticky="w")
            _ToolTip(b, tip)

        def _slider_row(label, var, lo, hi, res, row, unit="", apply_fn=None):
            tk.Label(body, text=label, font=("", 9, "bold")).grid(
                row=row, column=0, sticky="w", pady=3)
            val_lbl = tk.Label(body, font=("Courier", 8), width=7)
            def _fmt(*_):
                try:
                    val_lbl.config(
                        text=f"{var.get():.3g}{' ' + unit if unit else ''}")
                except Exception:
                    pass
            sc = tk.Scale(body, variable=var, from_=lo, to=hi, resolution=res,
                          orient=tk.HORIZONTAL, length=160, showvalue=False,
                          command=lambda _: _fmt())
            sc.grid(row=row, column=1, sticky="ew", padx=4)
            val_lbl.grid(row=row, column=2, sticky="w")
            _fmt()
            if apply_fn:
                _all_btn(row, 3, apply_fn)

        row = 0

        # ── Linestyle ─────────────────────────────────────────────────────────
        tk.Label(body, text="Line style:", font=("", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=(0, 4))
        ls_var = tk.StringVar(value=style.get("linestyle", "solid"))
        ls_frame = tk.Frame(body)
        ls_frame.grid(row=row, column=1, columnspan=2, sticky="w")
        for display, value in _LS_OPTIONS:
            tk.Radiobutton(ls_frame, text=display, variable=ls_var,
                           value=value).pack(side=tk.LEFT, padx=3)
        _all_btn(row, 3, _push_to_all("linestyle", ls_var.get))
        row += 1

        # ── Linewidth ─────────────────────────────────────────────────────────
        lw_var = tk.DoubleVar(value=style.get("linewidth", 1.5))
        _slider_row("Line width:", lw_var, 0.5, 5.0, 0.1, row, unit="pt",
                    apply_fn=_push_to_all("linewidth", lw_var.get))
        row += 1

        # ── Line opacity ──────────────────────────────────────────────────────
        alpha_var = tk.DoubleVar(value=style.get("alpha", 0.9))
        _slider_row("Line opacity:", alpha_var, 0.0, 1.0, 0.05, row,
                    apply_fn=_push_to_all("alpha", alpha_var.get))
        row += 1

        # ── Color ─────────────────────────────────────────────────────────────
        tk.Label(body, text="Color:", font=("", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=4)
        snapshot_col = style.get("color", "#1f77b4")
        col_var      = tk.StringVar(value=snapshot_col)
        col_swatch   = tk.Button(body, bg=col_var.get() or snapshot_col,
                                 width=4, relief=tk.RAISED, cursor="hand2")
        col_swatch.grid(row=row, column=1, sticky="w", padx=(4, 0))

        def _pick_color():
            init   = col_var.get().strip() or snapshot_col
            result = colorchooser.askcolor(color=init,
                                           title="Choose colour", parent=win)
            if result and result[1]:
                col_var.set(result[1])
                col_swatch.config(bg=result[1], activebackground=result[1])
        col_swatch.config(command=_pick_color)

        def _reset_color():
            col_var.set(snapshot_col)
            col_swatch.config(bg=snapshot_col, activebackground=snapshot_col)

        reset_row = tk.Frame(body)
        reset_row.grid(row=row, column=2, sticky="w", padx=4)
        tk.Button(reset_row, text="Reset", font=("", 8),
                  command=_reset_color).pack(side=tk.LEFT)

        _all_btn(row, 3,
                 _push_to_all("color", lambda: col_var.get().strip() or snapshot_col),
                 tip="Apply this colour to all spectra")
        row += 1

        # ── Fill ──────────────────────────────────────────────────────────────
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=4, sticky="ew", pady=6)
        row += 1

        tk.Label(body, text="Fill area:", font=("", 9, "bold")).grid(
            row=row, column=0, sticky="w")
        fill_var = tk.BooleanVar(value=style.get("fill", False))
        tk.Checkbutton(body, text="Show fill under curve",
                       variable=fill_var).grid(row=row, column=1,
                                               columnspan=2, sticky="w")
        _all_btn(row, 3, _push_to_all("fill", fill_var.get))
        row += 1

        fill_alpha_var = tk.DoubleVar(value=style.get("fill_alpha", 0.08))
        _slider_row("Fill opacity:", fill_alpha_var, 0.0, 0.5, 0.01, row,
                    apply_fn=_push_to_all("fill_alpha", fill_alpha_var.get))
        row += 1

        # ── Snapshot for cancel revert ────────────────────────────────────────
        _orig = dict(style)

        # ── Read all controls ─────────────────────────────────────────────────
        def _read():
            return {
                "linestyle":  ls_var.get(),
                "linewidth":  lw_var.get(),
                "alpha":      alpha_var.get(),
                "color":      col_var.get().strip() or snapshot_col,
                "fill":       fill_var.get(),
                "fill_alpha": fill_alpha_var.get(),
            }

        def _do_apply():
            self._graph.set_style(node_id, _read())
            self._rebuild_table()
            self._redraw()

        def _do_apply_all():
            vals = _read()
            partial = {k: v for k, v in vals.items() if k != "color"}
            for other in self._uvvis_nodes():
                self._graph.set_style(other.id, dict(partial))
            self._rebuild_table()
            self._redraw()

        def _do_save():
            _do_apply(); win.destroy()

        def _do_cancel():
            self._graph.set_style(node_id, dict(_orig))
            self._rebuild_table()
            self._redraw()
            win.destroy()

        btn_row = tk.Frame(win)
        btn_row.pack(pady=(4, 10))
        tk.Button(btn_row, text="Apply",              width=10,
                  command=_do_apply).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_row, text="∀  Apply to All",    width=14,
                  bg="#004400", fg="white", activeforeground="white",
                  command=_do_apply_all).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_row, text="Save",               width=8,
                  command=_do_save).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_row, text="Cancel",             width=8,
                  command=_do_cancel).pack(side=tk.LEFT, padx=3)

    # ══════════════════════════════════════════════════════════════════════════
    #  Push to TDDFT overlay
    # ══════════════════════════════════════════════════════════════════════════

    def _add_selected_to_overlay(self):
        if self._add_scan_fn is None:
            messagebox.showinfo("Not available",
                                "No TDDFT plot connected to this panel.")
            return

        live = [n for n in self._uvvis_nodes()
                if bool(n.style.get("visible", True))]
        if not live:
            messagebox.showinfo("Nothing selected",
                                "Check at least one spectrum in the list first.")
            return

        for node in live:
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
            text=f"Added {len(live)} spectrum/spectra to TDDFT overlay.",
            fg="#003d7a")
