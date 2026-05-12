"""Plot Settings Dialog — per-tab plot-level config (CS-06).

Spec
----
The authoritative spec is ``COMPONENTS.md`` (CS-06) plus Section 3 of
``ARCHITECTURE.md``. CS-06 places fonts, grid, background colour,
legend position, tick direction, and title/label text in a single
modal dialog accessible from each tab's top bar via the ⚙ button.
This module implements that dialog; the docstrings below cover the
choices made for ambiguities the spec left open.

Behavioural model
-----------------
* **Modal.** A ``tk.Toplevel`` with ``transient(parent)`` and
  ``grab_set()``. Per CS-06 exactly one Plot Settings dialog is open
  at a time per tab; a second open request for the same host raises
  the existing window rather than creating a duplicate.

* **Working copy semantics.** Slider, spinbox, checkbox, and combobox
  edits update an in-memory working copy of the configuration dict.
  Nothing reaches the tab's actual config (or the plot) until the user
  clicks Apply or Save. Apply commits and stays open for further
  iteration; Save commits and closes ("Save & Close"). Cancel and the
  window-close [X] discard the working copy and revert the config to
  the snapshot taken at ``__init__``. The button row matches the CS-05
  StyleDialog vocabulary — ``Apply · Save · Cancel`` — so Cancel-vs-Save
  reads the same across every modal in the app (CS-23, Phase 4l).

* **Save-as-Default / Reset Defaults / Factory Reset.** Three buttons
  inside the Fonts section (per CS-06 layout) modify the working copy
  but do not write to the config until Apply:

  - **Save as Default** copies the working copy into a module-level
    ``_USER_DEFAULTS`` dict whose lifetime is the process. Persistence
    to ``project.json`` is deferred to the project-I/O wiring session
    (CS-13) — flagged in BACKLOG and CS-14.
  - **Reset Defaults** copies ``_USER_DEFAULTS`` into the working copy
    if it is non-empty, otherwise falls back to ``_FACTORY_DEFAULTS``.
  - **Factory Reset** copies ``_FACTORY_DEFAULTS`` into the working
    copy.

* **Settings live in tab-private state, not in the graph.** The
  configuration is a plain Python dict on the tab. ``_redraw`` reads
  from it directly. Per Phase 4a friction #4 the question of a
  graph-side view-state payload is deferred.

Construction
------------

::

    PlotConfigDialog(
        parent,                 # tk.Widget for the Toplevel parent;
                                # also the registry key
        config,                 # dict — tab-private plot config
                                # (mutated in place on Apply)
        on_apply=None,          # callable(); called after Apply
                                # commits the working copy. The tab's
                                # callback is typically just
                                # `self._redraw`.
        sections=None,          # tuple of section names to show.
                                # If None, falls back to
                                # config["_sections"] then to
                                # _DEFAULT_SECTIONS (all four).
    )

Or via the module-level factory which handles the per-host registry:

::

    open_plot_config_dialog(parent, config, on_apply=None,
                              sections=None)
"""

from __future__ import annotations

import copy
import logging
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from typing import Any, Callable

_log = logging.getLogger(__name__)


# =====================================================================
# Module-level state
# =====================================================================

# host widget id → live PlotConfigDialog. CS-06 mandates one dialog
# per tab; the registry key is the host widget so each tab's dialog
# is independent. Entries are cleaned up by ``_on_destroy``. Tests
# clear this at setUp to avoid cross-test contamination.
_open_dialogs: "dict[int, PlotConfigDialog]" = {}


_DEFAULT_SECTIONS: tuple[str, ...] = (
    "fonts", "appearance", "legend", "title_labels",
)


# Human-readable section titles. Used both as the ``tk.LabelFrame``
# text and as the lookup key for tests that walk ``winfo_children()``.
_SECTION_TITLES: dict[str, str] = {
    "fonts":        "Fonts",
    "appearance":   "Appearance",
    "legend":       "Legend",
    "title_labels": "Title and labels",
}


# Combobox values for the legend position. Matches matplotlib's `loc`
# string — passed straight through to ``ax.legend(loc=...)``.
_LEGEND_POSITIONS: tuple[str, ...] = (
    "best",
    "upper right", "upper left", "lower left", "lower right",
    "right", "center left", "center right", "lower center",
    "upper center", "center",
)


# Factory defaults. Used by Factory Reset and as the fallback when a
# config dict is missing keys. Conservative values matching today's
# UV/Vis _redraw output: bold 10pt axis labels, no plot title, a
# light grid, white background, inward ticks, legend visible.
# CS-56 (Phase 4ae) added grid_color + tertiary_axis_offset and flipped
# tick_direction from "out" to "in". tertiary_axis_offset shadows the
# CS-44 _TERTIARY_AXIS_OFFSET_FRAC constant in uvvis_tab; a drift pin
# test asserts the two stay equal.
_FACTORY_DEFAULTS: dict[str, Any] = {
    # Fonts
    "title_font_size":       12,
    "title_font_bold":       True,
    "xlabel_font_size":      10,
    "xlabel_font_bold":      True,
    "ylabel_font_size":      10,
    "ylabel_font_bold":      True,
    "tick_label_font_size":  9,
    "legend_font_size":      8,
    # Appearance
    "grid":                  True,
    "grid_color":            "#b0b0b0",
    "background_color":      "#ffffff",
    "tick_direction":        "in",    # "in" | "out" | "inout"
    "tertiary_axis_offset":  1.12,    # right-spine offset for 3rd y-axis
    # Legend
    "legend_show":           True,
    "legend_position":       "best",
    # Title and labels
    "title_mode":            "none",  # "auto" | "none" | "custom"
    "title_text":            "",
    "xlabel_mode":           "auto",  # "auto" | "custom"
    "xlabel_text":           "",
    "ylabel_mode":           "auto",
    "ylabel_text":           "",
}


# Universal defaults: alias for the factory defaults today, kept as a
# distinct name so a future design session can split "what every
# config inherits" from "what Factory Reset writes" without a global
# rename. The two dicts share keys but are independent shallow
# copies — mutating one never affects the other.
_UNIVERSAL_DEFAULTS: dict[str, Any] = dict(_FACTORY_DEFAULTS)


# In-process user defaults written by Save-as-Default. Cleared by
# tests; persistence to project.json is deferred (CS-13 / CS-14).
_USER_DEFAULTS: dict[str, Any] = {}


# Notebook tab keys (CS-60, Phase 4ai). Canonical order — the Notebook
# pack order matches this tuple. The first entry is the default tab.
_TAB_KEYS: tuple[str, ...] = (
    "global",
    "primary_x", "secondary_x",
    "primary_y", "secondary_y", "tertiary_y",
)

# Human-readable Notebook tab labels. Used as the tab text and as the
# lookup key for tests that walk `notebook.tabs()`. Modified-edit
# marker (`" •"`) is appended at runtime by commit 4's state model.
_TAB_TITLES: dict[str, str] = {
    "global":      "Global",
    "primary_x":   "Primary X",
    "secondary_x": "Secondary X",
    "primary_y":   "Primary Y",
    "secondary_y": "Secondary Y",
    "tertiary_y":  "Tertiary Y",
}

# Per-axis-tab subtitle. The dialog can't introspect the figure today
# (no figure handle in scope), so Phase 4ai shipped these as static
# placeholders; Phase 4ak will populate live "(used by N nodes)" /
# "(unused)" / "(derived)" badges from the host tab's
# ``_axes_by_role`` plus the graph's nodes.
_AXIS_TAB_PLACEHOLDER_BADGE: dict[str, str] = {
    "primary_x":   "(spectral x-axis)",
    "secondary_x": "(derived, e.g. wavelength↔energy)",
    "primary_y":   "(plots routed here by default)",
    "secondary_y": "(plots routed via y_axis style)",
    "tertiary_y":  "(plots routed via y_axis style)",
}


# CS-60 (Phase 4ai): per-setting tab attribution for the modified-tab
# marker. Every working-copy key resolves to a Notebook tab; the
# writer helpers tag that tab dirty when the user edits it. Phase 4aj
# (CS-61) added the first entry: ``tick_direction`` pins to
# ``primary_x`` because tick direction is most visually associated
# with the bottom X-axis ticks in a UV/Vis plot. The widget itself
# is mirrored across all five per-axis tabs sharing one Tk var;
# editing on any tab marks only Primary X dirty so the user is not
# flooded with five bullets per single-setting edit (the dishonest
# UX is acknowledged friction for 4aj, resolved in 4ak when each
# axis owns its own ``tick_direction`` slot via the per-axis
# schema). Phase 4ak+ populates this map with additional per-axis
# role keys as per-axis settings land.
_KEY_TO_TAB: dict[str, str] = {
    "tick_direction": "primary_x",
}


# Suffix appended to a tab's title when it carries uncommitted edits.
# IntelliJ-style bullet so the visual change is unmissable across
# tab themes.
_MODIFIED_TAB_SUFFIX: str = " •"


def _key_to_tab(key: str) -> str:
    """Resolve a working-copy key to its owning Notebook tab key.

    Phase 4ai ships every existing setting on the Global tab — the
    map is empty and the default branch returns ``"global"`` for
    every key. Phase 4aj+ adds per-axis-role entries as per-axis
    settings move out of the Global tab.
    """
    return _KEY_TO_TAB.get(key, "global")


# =====================================================================
# Module-level factory
# =====================================================================

def open_plot_config_dialog(
    parent: tk.Widget,
    config: dict,
    on_apply: Callable[[], None] | None = None,
    sections: tuple[str, ...] | None = None,
    tab: str = "global",
    on_apply_all_tabs: Callable[[], None] | None = None,
) -> "PlotConfigDialog":
    """Open the Plot Config dialog for a host, or focus the existing one.

    Per CS-06 (and CS-60 from Phase 4ai onward) each host has at most
    one open Plot Config dialog at a time. A second request from the
    same host raises the existing Toplevel rather than creating a
    duplicate; the existing dialog's active Notebook tab is updated
    to ``tab`` when the caller asks for a specific one.

    ``tab`` is one of :data:`_TAB_KEYS`; values outside the set fall
    back to ``"global"``. Used by the Phase 4ai double-click hit-test
    (CS-60) to pre-select the clicked axis's tab.

    ``on_apply_all_tabs`` is the optional "Apply to All Tabs"
    callback. When omitted (or None) the button shows disabled —
    the dialog still functions as a per-tab editor. The callback
    runs in addition to ``on_apply``: cross-UV/Vis-tab replication
    semantics belong to the host (typically Binah) and remain
    out-of-scope for the dialog itself.

    Returns the live ``PlotConfigDialog`` either way.
    """
    key = id(parent)
    existing = _open_dialogs.get(key)
    if existing is not None:
        try:
            if bool(existing.winfo_exists()):
                existing.select_tab(tab)
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass
        # Stale registry entry — fall through to construct fresh.
        _open_dialogs.pop(key, None)
    return PlotConfigDialog(
        parent, config, on_apply, sections,
        tab=tab, on_apply_all_tabs=on_apply_all_tabs,
    )


# =====================================================================
# Dialog
# =====================================================================

class PlotConfigDialog(tk.Toplevel):
    """Modal per-tab plot-settings editor (CS-06).

    See module docstring for the design model. The class is a
    ``Toplevel`` configured ``transient`` + ``grab_set`` so the main
    window is non-interactive while the dialog is open. Each tab gets
    its own Toplevel via the per-host registry above.
    """

    # ------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------

    def __init__(
        self,
        parent: tk.Widget,
        config: dict,
        on_apply: Callable[[], None] | None = None,
        sections: tuple[str, ...] | None = None,
        tab: str = "global",
        on_apply_all_tabs: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._parent = parent
        self._config = config
        self._on_apply = on_apply
        # CS-60: optional cross-tab application callback. None means
        # "the host hasn't wired the multi-tab apply path", so the
        # "Apply to All Tabs" button shows disabled.
        self._on_apply_all_tabs = on_apply_all_tabs

        # Resolve the section set: explicit argument > config["_sections"]
        # > module default. Filtering to known names keeps a stray
        # entry from breaking the build silently.
        if sections is None:
            sections = config.get("_sections", _DEFAULT_SECTIONS)
        self._sections: tuple[str, ...] = tuple(
            s for s in sections if s in _SECTION_TITLES
        )

        # Snapshot for Cancel revert. Deep copy so that nested values
        # (none today, but future-proof) cannot leak through.
        self._snapshot: dict[str, Any] = copy.deepcopy(dict(config))

        # Working copy: starts from the current config, falls back to
        # _FACTORY_DEFAULTS for any key the config is missing. This
        # gives every widget a defined value at construction time
        # regardless of how sparse the caller's config is.
        self._working: dict[str, Any] = dict(_FACTORY_DEFAULTS)
        self._working.update(copy.deepcopy(dict(config)))

        # Re-entrancy guard. Set during widget refreshes (Reset
        # Defaults, Factory Reset, _refresh_widgets_from_working) so
        # the variable trace callbacks do not fire write-backs.
        self._suspend_writes: bool = True

        # Per-key Tk variables. Populated by section builders.
        self._control_vars: dict[str, tk.Variable] = {}
        # Per-key writer closures the refresh path uses to push a
        # working-copy value back into the widget without firing a
        # write-back. Populated by row builders.
        self._control_refresh: dict[str, Callable[[Any], None]] = {}
        # Colour swatch buttons. ``set_facecolor``-style controls
        # are not bound to a Tk var so they need their own refresh.
        self._color_swatches: dict[str, tk.Button] = {}

        # CS-60: Notebook tab frames keyed by :data:`_TAB_KEYS`. The
        # Global tab hosts the existing section LabelFrames; each
        # axis tab hosts the per-axis shell built in
        # :meth:`_build_axis_tab_shell`.
        self._notebook: ttk.Notebook | None = None
        self._tab_frames: dict[str, tk.Frame] = {}

        # CS-60 (Phase 4ai): per-tab pending-edit tracking. Each tab
        # key in this set carries an uncommitted edit; the tab's
        # Notebook title gets the :data:`_MODIFIED_TAB_SUFFIX` bullet
        # appended until Apply / Save clears it (or Cancel reverts
        # everything). Tabs persist their pending state across tab
        # switches — switching tabs is a navigation gesture, not a
        # commit boundary, so edits made on one tab survive a hop
        # to another and back.
        self._modified_tabs: set[str] = set()

        self.title("Plot Settings")
        # Modal: transient + grab_set per CS-06. ``transient`` keeps
        # the dialog above the main window; ``grab_set`` blocks input
        # to the rest of the app while open.
        try:
            self.transient(parent.winfo_toplevel())
        except (AttributeError, tk.TclError):
            pass
        self.grab_set()

        self._build_body()
        self._build_button_row()

        # Pre-select the requested tab. Falls back to "global" for any
        # unknown key — the double-click hit-test occasionally passes
        # roles whose tab is reserved (e.g. ``secondary_x`` today).
        self.select_tab(tab)

        self.bind("<Destroy>", self._on_destroy, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close_requested)

        # Register so a second open_plot_config_dialog call finds us.
        _open_dialogs[id(parent)] = self

        # Construction complete: writes from now on flow into the
        # working copy.
        self._suspend_writes = False

    # ------------------------------------------------------------
    # Body construction — Notebook + per-tab frames (CS-60)
    # ------------------------------------------------------------

    def _build_body(self) -> None:
        """Build the Notebook and the six per-tab frames (CS-60).

        The Notebook holds one tab per :data:`_TAB_KEYS` entry. The
        Global tab hosts the pre-existing section LabelFrames
        (delegated to :meth:`_build_global_tab`); each axis tab holds
        a placeholder shell (:meth:`_build_axis_tab_shell`) until
        per-axis settings land in Phase 4aj+.
        """
        body = tk.Frame(self, padx=8, pady=8)
        body.pack(fill=tk.BOTH, expand=True)
        self._body = body

        nb = ttk.Notebook(body)
        nb.pack(fill=tk.BOTH, expand=True)
        self._notebook = nb

        for key in _TAB_KEYS:
            frame = tk.Frame(nb, padx=8, pady=8)
            nb.add(frame, text=_TAB_TITLES[key])
            self._tab_frames[key] = frame

            if key == "global":
                self._build_global_tab(frame)
            else:
                self._build_axis_tab_shell(frame, key)

    def _build_global_tab(self, parent: tk.Widget) -> None:
        """Build the Global tab's LabelFrame stack.

        Pre-CS-60 this was the entire dialog body. Lifted into the
        Global Notebook tab unchanged so the existing section
        widgets (fonts, appearance, legend, title/labels) keep
        identical behaviour. Phase 4aj (CS-61) removed the Tick
        direction row from the Appearance section and relocated it
        to the per-axis tabs; the Appearance section now hosts the
        Grid checkbox, Grid colour swatch, Background swatch, and
        Tertiary axis offset spinbox (rows 0–3). Phase 4ak's
        axis-labels mirror lands at the top of this tab.
        """
        for i, name in enumerate(self._sections):
            builder = getattr(self, f"_build_section_{name}", None)
            if builder is None:
                _log.warning(
                    "plot_settings_dialog: no builder for section %r", name,
                )
                continue
            if i > 0:
                ttk.Separator(parent, orient=tk.HORIZONTAL).pack(
                    fill=tk.X, pady=(8, 4),
                )
            frame = tk.LabelFrame(
                parent, text=_SECTION_TITLES[name], padx=8, pady=4,
            )
            frame.pack(fill=tk.X)
            frame.columnconfigure(1, weight=1)
            builder(frame)

    def _build_axis_tab_shell(self, parent: tk.Widget, role: str) -> None:
        """Build the per-axis Notebook tab shell (CS-60, Phase 4ai).

        Phase 4ai shipped the layout; Phase 4aj (CS-61) populated the
        "Settings" LabelFrame with the first real per-axis widget
        (tick direction). Structure:

        * Header row: bold ``"Axis: <Tab Title>"`` on the left,
          italic state badge (placeholder text from
          :data:`_AXIS_TAB_PLACEHOLDER_BADGE`) on the right.
        * Separator.
        * "Plots on this axis" LabelFrame containing an empty
          scrollable list placeholder. Phase 4ak populates this from
          the host tab's graph + ``y_axis`` style key (CS-50).
        * Separator.
        * "Settings" LabelFrame populated via
          :meth:`_build_axis_tab_settings`. Phase 4aj ships the
          Tick direction Radiobutton row mirrored across all five
          axis tabs (shared Tk var, flat schema, Primary X dirty
          pin — CS-61). Each subsequent phase adds widgets here.
        """
        header = tk.Frame(parent)
        header.pack(fill=tk.X)
        tk.Label(
            header, text=f"Axis: {_TAB_TITLES[role]}",
            font=("", 10, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            header, text=_AXIS_TAB_PLACEHOLDER_BADGE.get(role, ""),
            font=("", 9, "italic"), fg="#666666",
        ).pack(side=tk.RIGHT)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=(6, 4),
        )

        plots_frame = tk.LabelFrame(
            parent, text="Plots on this axis", padx=8, pady=6,
        )
        plots_frame.pack(fill=tk.X)
        tk.Label(
            plots_frame,
            text="(populated in Phase 4ak)",
            font=("", 9), fg="#888888",
        ).pack(anchor="w")

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=(8, 4),
        )

        settings_frame = tk.LabelFrame(
            parent, text="Settings", padx=8, pady=6,
        )
        settings_frame.pack(fill=tk.X)
        self._build_axis_tab_settings(settings_frame, role)

    # ------------------------------------------------------------
    # Tab navigation (CS-60)
    # ------------------------------------------------------------

    def select_tab(self, key: str) -> None:
        """Switch the Notebook to the tab named ``key``.

        ``key`` must be one of :data:`_TAB_KEYS`; an unknown key (or
        a key whose tab is reserved-but-not-built — none today)
        falls back silently to ``"global"`` so the double-click
        hit-test's reserved roles don't crash the dialog.
        """
        if self._notebook is None:
            return
        if key not in self._tab_frames:
            key = "global"
        frame = self._tab_frames[key]
        try:
            self._notebook.select(frame)
        except tk.TclError:
            # Tab not yet added to the notebook (shouldn't happen
            # given _build_body); swallow rather than crash.
            pass

    def current_tab_key(self) -> str:
        """Return the currently selected tab key (CS-60).

        Useful for tests and for the commit-4 button row that needs
        to know which tab the user is on when they Apply. Returns
        ``"global"`` if the Notebook isn't yet wired.
        """
        if self._notebook is None:
            return "global"
        try:
            selected = self._notebook.select()
            for key, frame in self._tab_frames.items():
                if str(frame) == selected:
                    return key
        except tk.TclError:
            pass
        return "global"

    # ============================================================
    # Section: Fonts
    # ============================================================

    def _build_section_fonts(self, parent: tk.Widget) -> None:
        """Per-element font-size spinbox + bold checkbox.

        Per CS-06 the Save-as-Default / Reset Defaults / Factory Reset
        button row sits at the bottom of this section even though the
        actions affect every section. The placement is the spec's; the
        scope is the dialog's full working copy.
        """
        rows: tuple[tuple[str, str, bool, str], ...] = (
            # (label,         size_key,                bold?,  bold_key)
            ("Plot title:",   "title_font_size",       True,   "title_font_bold"),
            ("X-axis label:", "xlabel_font_size",      True,   "xlabel_font_bold"),
            ("Y-axis label:", "ylabel_font_size",      True,   "ylabel_font_bold"),
            ("Tick labels:",  "tick_label_font_size",  False,  ""),
            ("Legend:",       "legend_font_size",      False,  ""),
        )
        for r, (label, size_key, has_bold, bold_key) in enumerate(rows):
            tk.Label(parent, text=label, font=("", 9, "bold")).grid(
                row=r, column=0, sticky="w", pady=2,
            )
            tk.Label(parent, text="Size", font=("", 9)).grid(
                row=r, column=1, sticky="w", padx=(8, 2),
            )
            self._make_int_spinbox(parent, r, 2, size_key, lo=4, hi=36)
            if has_bold:
                self._make_bool_checkbox(
                    parent, r, 3, bold_key, label_text="Bold",
                )

        # Bottom row of the Fonts section: Save-as-Default, Reset
        # Defaults, Factory Reset. Spans full width.
        btns_row = len(rows)
        btns = tk.Frame(parent)
        btns.grid(
            row=btns_row, column=0, columnspan=4,
            sticky="ew", pady=(8, 2),
        )
        tk.Button(
            btns, text="Save as Default", font=("", 8),
            command=self._do_save_as_default,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btns, text="Reset Defaults", font=("", 8),
            command=self._do_reset_defaults,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btns, text="Factory Reset", font=("", 8),
            command=self._do_factory_reset,
        ).pack(side=tk.LEFT, padx=2)

    # ============================================================
    # Section: Appearance
    # ============================================================

    def _build_section_appearance(self, parent: tk.Widget) -> None:
        # Grid checkbox.
        tk.Label(parent, text="Grid:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=2,
        )
        self._make_bool_checkbox(
            parent, 0, 1, "grid", label_text="Show grid",
        )

        # Grid colour swatch (CS-56). Click → colorchooser. Plot-wide;
        # the StyleDialog per-style override stays carry-forward.
        tk.Label(parent, text="Grid colour:", font=("", 9, "bold")).grid(
            row=1, column=0, sticky="w", pady=2,
        )
        self._make_colour_swatch(parent, 1, 1, "grid_color")

        # Background colour swatch (click → colorchooser).
        tk.Label(parent, text="Background:", font=("", 9, "bold")).grid(
            row=2, column=0, sticky="w", pady=2,
        )
        self._make_colour_swatch(parent, 2, 1, "background_color")

        # CS-61 (Phase 4aj): the "Tick direction" row used to live here
        # at row 3; it now lives on each per-axis tab (built by
        # ``_build_axis_tab_settings``). The factory default key and
        # working-copy storage stay in this module unchanged; only the
        # widget moved. Tertiary axis offset slides up from row 4 to
        # row 3 to keep the section dense.

        # Tertiary y-axis offset (CS-56 + CS-44 follow-up). Promotes the
        # uvvis_tab._TERTIARY_AXIS_OFFSET_FRAC module-level constant to
        # a tunable Plot Settings key; 1.00 = right spine flush against
        # the figure edge, 1.50 = offset half a figure-width outward.
        # 0.01 step is fine enough for visual tuning; bounds picked from
        # practical use rather than matplotlib's full numerical range.
        tk.Label(
            parent, text="Tertiary axis offset:", font=("", 9, "bold"),
        ).grid(row=3, column=0, sticky="w", pady=2)
        off_var = tk.DoubleVar(
            value=float(self._working.get(
                "tertiary_axis_offset",
                _FACTORY_DEFAULTS["tertiary_axis_offset"],
            )),
        )
        self._control_vars["tertiary_axis_offset"] = off_var
        off_spin = tk.Spinbox(
            parent, from_=1.00, to=1.50, increment=0.01,
            textvariable=off_var, width=6, format="%.2f",
        )
        off_spin.grid(row=3, column=1, sticky="w", padx=2)
        off_var.trace_add(
            "write",
            lambda *_, k="tertiary_axis_offset", v=off_var:
                self._on_float_var_write(k, v),
        )

        def _refresh_off(value, _v=off_var):
            try:
                _v.set(float(value))
            except (tk.TclError, ValueError):
                pass
        self._control_refresh["tertiary_axis_offset"] = _refresh_off

    # ============================================================
    # Per-axis tab body — CS-61 (Phase 4aj) tick_direction relocation
    # ============================================================

    def _build_axis_tab_settings(self, parent: tk.Widget, role: str) -> None:
        """Populate the per-axis tab's "Settings" LabelFrame (CS-61).

        Phase 4aj ships the first real per-axis widget: a Tick direction
        Radiobutton row that mirrors across all five axis tabs. Every
        tab's radio is bound to the SAME ``self._control_vars["tick_direction"]``
        Tk var, so editing on one tab visually reflects on the other
        four. The single working-copy key ``tick_direction`` keeps the
        schema flat (no nested ``_USER_DEFAULTS["axes"][role]`` yet —
        that schema invention lands in Phase 4ak). The dirty marker
        pins to Primary X via ``_KEY_TO_TAB["tick_direction"]``, so
        editing the radio on any axis tab marks ONLY Primary X dirty
        (not all five). The acknowledged friction — "I edited on Y but
        X shows the bullet" — clears in 4ak.

        ``parent`` is the inner ``"Settings"`` LabelFrame built by
        ``_build_axis_tab_shell``. ``role`` is the axis-role tab key
        (one of ``primary_x``, ``secondary_x``, ``primary_y``,
        ``secondary_y``, ``tertiary_y``).
        """
        row = tk.Frame(parent)
        row.pack(fill=tk.X, anchor="w", pady=2)
        tk.Label(
            row, text="Tick direction:", font=("", 9, "bold"),
        ).pack(side=tk.LEFT)

        # The first axis tab built (canonical pack order: primary_x)
        # registers the shared Tk var, trace callback, and refresh
        # closure. Subsequent tabs reuse the var so all five radios
        # display the same selection.
        var = self._control_vars.get("tick_direction")
        if var is None:
            var = tk.StringVar(
                value=str(self._working.get("tick_direction", "in")),
            )
            self._control_vars["tick_direction"] = var
            var.trace_add(
                "write",
                lambda *_, k="tick_direction", v=var:
                    self._on_var_write(k, v.get()),
            )

            def _refresh_dir(value, _v=var):
                _v.set(str(value))
            self._control_refresh["tick_direction"] = _refresh_dir

        radio_frame = tk.Frame(row)
        radio_frame.pack(side=tk.LEFT, padx=(8, 0))
        for display, value in (
            ("In", "in"), ("Out", "out"), ("Both", "inout"),
        ):
            tk.Radiobutton(
                radio_frame, text=display, variable=var, value=value,
            ).pack(side=tk.LEFT, padx=3)

    # ============================================================
    # Section: Legend
    # ============================================================

    def _build_section_legend(self, parent: tk.Widget) -> None:
        # Show legend checkbox.
        tk.Label(parent, text="Show legend:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=2,
        )
        self._make_bool_checkbox(
            parent, 0, 1, "legend_show", label_text="Visible",
        )

        # Position combobox.
        tk.Label(parent, text="Position:", font=("", 9, "bold")).grid(
            row=1, column=0, sticky="w", pady=2,
        )
        var = tk.StringVar(
            value=str(self._working.get("legend_position", "best")),
        )
        self._control_vars["legend_position"] = var
        cb = ttk.Combobox(
            parent, textvariable=var, values=list(_LEGEND_POSITIONS),
            state="readonly", width=14, font=("", 9),
        )
        cb.grid(row=1, column=1, sticky="w", padx=4)
        var.trace_add(
            "write",
            lambda *_, k="legend_position", v=var:
                self._on_var_write(k, v.get()),
        )

        def _refresh_pos(value, _v=var):
            _v.set(str(value))
        self._control_refresh["legend_position"] = _refresh_pos

    # ============================================================
    # Section: Title and labels
    # ============================================================

    def _build_section_title_labels(self, parent: tk.Widget) -> None:
        # The dialog cannot compute the auto-derived label text — that
        # is tab-specific (e.g. "Wavelength (nm)" depending on x_unit).
        # So Auto/None are mode flags; the entry is what the user
        # typed. _redraw on the tab side picks a value from
        # title_text/xlabel_text/ylabel_text only when the matching
        # mode is "custom".
        rows: tuple[tuple[str, str, str, bool], ...] = (
            # (label,   text_key,       mode_key,       offer_none)
            ("Title:",  "title_text",   "title_mode",   True),
            ("X label:", "xlabel_text", "xlabel_mode",  False),
            ("Y label:", "ylabel_text", "ylabel_mode",  False),
        )
        for r, (label, text_key, mode_key, offer_none) in enumerate(rows):
            tk.Label(parent, text=label, font=("", 9, "bold")).grid(
                row=r, column=0, sticky="w", pady=2,
            )
            self._make_label_row(
                parent, r, text_key, mode_key, offer_none,
            )

    def _make_label_row(
        self,
        parent: tk.Widget,
        row: int,
        text_key: str,
        mode_key: str,
        offer_none: bool,
    ) -> None:
        text_var = tk.StringVar(value=str(self._working.get(text_key, "")))
        mode_var = tk.StringVar(value=str(self._working.get(mode_key, "auto")))
        self._control_vars[text_key] = text_var
        self._control_vars[mode_key] = mode_var

        entry = tk.Entry(parent, textvariable=text_var, width=20)
        entry.grid(row=row, column=1, sticky="ew", padx=4)

        # Editing the entry implicitly switches mode to "custom".
        def _on_entry_write(*_, k=text_key, v=text_var, mk=mode_key,
                            mv=mode_var):
            self._on_var_write(k, v.get())
            # If the user typed something, mode → custom. The trace on
            # mode_var fires as a result and writes through.
            if mv.get() != "custom":
                mv.set("custom")
        text_var.trace_add("write", _on_entry_write)

        # The mode_var writes through on its own.
        mode_var.trace_add(
            "write",
            lambda *_, k=mode_key, v=mode_var:
                self._on_var_write(k, v.get()),
        )

        # [Auto] button: set mode to "auto".
        def _set_auto(_mv=mode_var):
            _mv.set("auto")
        tk.Button(
            parent, text="Auto", font=("", 8), command=_set_auto,
        ).grid(row=row, column=2, sticky="w", padx=2)

        if offer_none:
            def _set_none(_mv=mode_var):
                _mv.set("none")
            tk.Button(
                parent, text="None", font=("", 8), command=_set_none,
            ).grid(row=row, column=3, sticky="w", padx=2)

        # Mode indicator label (small, follows the mode_var).
        mode_lbl = tk.Label(
            parent, text=f"({mode_var.get()})",
            fg="#666666", font=("", 8),
        )
        col = 4 if offer_none else 3
        mode_lbl.grid(row=row, column=col, sticky="w", padx=4)

        def _refresh_mode_label(*_, _l=mode_lbl, _v=mode_var):
            _l.config(text=f"({_v.get()})")
        mode_var.trace_add("write", _refresh_mode_label)

        # Refreshers used by Reset / Factory Reset.
        def _refresh_text(value, _v=text_var):
            _v.set(str(value))
        self._control_refresh[text_key] = _refresh_text

        def _refresh_mode(value, _v=mode_var, _l=mode_lbl):
            _v.set(str(value))
            _l.config(text=f"({value})")
        self._control_refresh[mode_key] = _refresh_mode

    # ------------------------------------------------------------
    # Widget factories
    # ------------------------------------------------------------

    def _make_int_spinbox(
        self,
        parent: tk.Widget,
        row: int,
        column: int,
        key: str,
        lo: int = 1,
        hi: int = 99,
    ) -> tk.Spinbox:
        var = tk.IntVar(value=int(self._working.get(key, _FACTORY_DEFAULTS[key])))
        self._control_vars[key] = var
        spin = tk.Spinbox(
            parent, from_=lo, to=hi, increment=1, textvariable=var,
            width=4,
        )
        spin.grid(row=row, column=column, sticky="w", padx=2)
        var.trace_add(
            "write",
            lambda *_, k=key, v=var: self._on_int_var_write(k, v),
        )

        def _refresh(value, _v=var):
            try:
                _v.set(int(value))
            except (tk.TclError, ValueError):
                pass
        self._control_refresh[key] = _refresh
        return spin

    def _make_bool_checkbox(
        self,
        parent: tk.Widget,
        row: int,
        column: int,
        key: str,
        label_text: str = "",
    ) -> tk.Checkbutton:
        var = tk.BooleanVar(value=bool(self._working.get(key, _FACTORY_DEFAULTS[key])))
        self._control_vars[key] = var
        cb = tk.Checkbutton(parent, text=label_text, variable=var)
        cb.grid(row=row, column=column, sticky="w", padx=2)
        var.trace_add(
            "write",
            lambda *_, k=key, v=var:
                self._on_var_write(k, bool(v.get())),
        )

        def _refresh(value, _v=var):
            _v.set(bool(value))
        self._control_refresh[key] = _refresh
        return cb

    def _make_colour_swatch(
        self,
        parent: tk.Widget,
        row: int,
        column: int,
        key: str,
    ) -> tk.Button:
        current = str(self._working.get(key, _FACTORY_DEFAULTS[key]))
        var = tk.StringVar(value=current)
        self._control_vars[key] = var

        swatch = tk.Button(
            parent, bg=current, width=4, relief=tk.RAISED,
            cursor="hand2",
        )
        swatch.grid(row=row, column=column, sticky="w", padx=4)
        self._color_swatches[key] = swatch

        def _set_swatch(value: str) -> None:
            try:
                swatch.config(bg=value, activebackground=value)
            except tk.TclError:
                pass

        def _pick():
            initial = var.get().strip() or _FACTORY_DEFAULTS[key]
            result = colorchooser.askcolor(
                color=initial, title="Choose colour", parent=self,
            )
            if result and result[1]:
                var.set(result[1])
                _set_swatch(result[1])
                self._on_var_write(key, result[1])

        swatch.config(command=_pick)

        def _refresh(value, _v=var, _set=_set_swatch):
            _v.set(str(value))
            _set(str(value))
        self._control_refresh[key] = _refresh
        return swatch

    # ------------------------------------------------------------
    # Working-copy write helpers (with re-entrancy guard)
    # ------------------------------------------------------------

    def _on_var_write(self, key: str, value: Any) -> None:
        """Update the working copy when a Tk variable changes.

        ``_suspend_writes`` is set during widget refreshes (Reset
        Defaults, Factory Reset, Cancel revert) so the trace callbacks
        triggered by ``var.set`` don't loop back into this handler.
        """
        if self._suspend_writes:
            return
        self._working[key] = value
        self._mark_tab_modified(_key_to_tab(key))

    def _on_int_var_write(self, key: str, var: tk.IntVar) -> None:
        if self._suspend_writes:
            return
        try:
            self._working[key] = int(var.get())
        except (tk.TclError, ValueError):
            # Bad spinbox state (mid-edit). Skip until valid.
            return
        self._mark_tab_modified(_key_to_tab(key))

    def _on_float_var_write(self, key: str, var: tk.DoubleVar) -> None:
        # CS-56 (Phase 4ae): float-spinbox analogue of _on_int_var_write.
        # Skips the write on mid-edit garbage rather than crashing the
        # trace; the working dict keeps its last good value until the
        # spinbox re-stabilises.
        if self._suspend_writes:
            return
        try:
            self._working[key] = float(var.get())
        except (tk.TclError, ValueError):
            return
        self._mark_tab_modified(_key_to_tab(key))

    # ------------------------------------------------------------
    # Per-tab modified-edit tracking (CS-60, Phase 4ai)
    # ------------------------------------------------------------

    def _mark_tab_modified(self, tab_key: str) -> None:
        """Flag ``tab_key`` as carrying uncommitted edits.

        Adds the :data:`_MODIFIED_TAB_SUFFIX` bullet to the
        Notebook tab title and records the tab in
        :attr:`_modified_tabs`. Idempotent — a second edit on the
        same tab is a no-op.
        """
        if tab_key not in self._tab_frames:
            return
        if tab_key in self._modified_tabs:
            return
        self._modified_tabs.add(tab_key)
        self._refresh_tab_title(tab_key)

    def _clear_tab_modified(self, tab_key: str) -> None:
        """Clear the uncommitted-edit marker for ``tab_key``."""
        if tab_key not in self._modified_tabs:
            return
        self._modified_tabs.discard(tab_key)
        self._refresh_tab_title(tab_key)

    def _clear_all_modified_tabs(self) -> None:
        """Drop the modified marker from every tab.

        Called by Apply / Save / "Apply to All Tabs" after the
        working copy commits, and by Cancel after the snapshot
        revert. Walks a snapshot of :attr:`_modified_tabs` so
        :meth:`_clear_tab_modified` can mutate the set during the
        loop.
        """
        for tab_key in list(self._modified_tabs):
            self._clear_tab_modified(tab_key)

    def _refresh_tab_title(self, tab_key: str) -> None:
        """Push the current modified-state suffix into the Notebook tab.

        Idempotent. ``_TAB_TITLES[tab_key]`` is the canonical
        base text; the suffix is appended iff ``tab_key`` is in
        :attr:`_modified_tabs`.
        """
        if self._notebook is None:
            return
        frame = self._tab_frames.get(tab_key)
        if frame is None:
            return
        title = _TAB_TITLES[tab_key]
        if tab_key in self._modified_tabs:
            title += _MODIFIED_TAB_SUFFIX
        try:
            self._notebook.tab(frame, text=title)
        except tk.TclError:
            pass

    def _has_uncommitted_changes(self) -> bool:
        """True iff Cancel would discard something the user could miss.

        Two ways to be "dirty": uncommitted edits in the working
        copy (``_modified_tabs`` non-empty), or intermediate-Applied
        edits that Cancel would still revert (config != snapshot).
        """
        if self._modified_tabs:
            return True
        return dict(self._config) != self._snapshot

    # ------------------------------------------------------------
    # Bottom button row — CS-60: Save · Apply · Apply to All Tabs · Cancel
    # ------------------------------------------------------------

    def _build_button_row(self) -> None:
        """Build the right-aligned dialog-level button row (CS-60).

        Layout, left → right:
        ``Save``, ``Apply``, ``Apply to All Tabs``, ``Cancel``.

        * **Save** commits every pending edit across every tab and
          closes the dialog. Same wording as CS-23; cross-tab scope
          is new in CS-60.
        * **Apply** commits every pending edit across every tab and
          keeps the dialog open. The user iterates: edit → Apply →
          inspect the plot → edit more.
        * **Apply to All Tabs** commits and replicates the result to
          the host's sibling UV/Vis notebook tabs. Disabled when the
          host hasn't supplied ``on_apply_all_tabs``.
        * **Cancel** reverts every pending edit across every tab
          AND any intermediate-Applied edit, then closes. When the
          dialog has uncommitted state it shows an
          ``askokcancel("Discard changes?")`` confirm first; the
          conservative tk-silenced answer (True) preserves the
          existing CS-23 always-close-on-Cancel test contract.

        The button row sits at the bottom of the Toplevel, not
        inside the Notebook, so it applies dialog-wide. CS-23's
        per-section "Save as Default / Reset Defaults / Factory
        Reset" row inside Fonts stays — those affect the working
        copy only and are independent of the dialog-level buttons.
        """
        btn_row = tk.Frame(self)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 10))

        # Right-aligned: pack into a sub-frame anchored east.
        right = tk.Frame(btn_row)
        right.pack(side=tk.RIGHT)

        self._save_btn = tk.Button(
            right, text="Save", width=8, command=self._do_save,
        )
        self._save_btn.pack(side=tk.LEFT, padx=3)

        self._apply_btn = tk.Button(
            right, text="Apply", width=10, command=self._do_apply,
        )
        self._apply_btn.pack(side=tk.LEFT, padx=3)

        self._apply_all_tabs_btn = tk.Button(
            right, text="Apply to All Tabs", width=18,
            command=self._do_apply_all_tabs,
            state=(tk.NORMAL if self._on_apply_all_tabs else tk.DISABLED),
        )
        self._apply_all_tabs_btn.pack(side=tk.LEFT, padx=3)

        self._cancel_btn = tk.Button(
            right, text="Cancel", width=8, command=self._do_cancel,
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=3)

    # ------------------------------------------------------------
    # Bottom button actions
    # ------------------------------------------------------------

    def _commit_working_copy(self) -> None:
        """Mutate ``self._config`` in place from ``self._working``.

        Shared by every "commit" path (Apply / Save / Apply All).
        After commit fires ``on_apply`` if wired, then clears every
        modified-tab marker — the working state is the new live
        state and no tab is dirty.
        """
        self._config.clear()
        self._config.update(copy.deepcopy(self._working))
        if self._on_apply is not None:
            try:
                self._on_apply()
            except Exception:
                _log.warning(
                    "plot_settings_dialog: on_apply raised", exc_info=True,
                )
        self._clear_all_modified_tabs()

    def _do_apply(self) -> None:
        """Commit working copy + on_apply + clear markers; stay open."""
        self._commit_working_copy()

    def _do_save(self) -> None:
        """Commit working copy + on_apply + clear markers; close."""
        self._commit_working_copy()
        self.destroy()

    def _do_apply_all_tabs(self) -> None:
        """Commit working copy locally, then replicate via the host callback.

        The local commit runs first so the host's replication logic
        sees the new value when it reads ``self._config``.
        Disabled-button guard is enforced at construction; if the
        callback is None we still no-op safely.
        """
        self._commit_working_copy()
        if self._on_apply_all_tabs is None:
            return
        try:
            self._on_apply_all_tabs()
        except Exception:
            _log.warning(
                "plot_settings_dialog: on_apply_all_tabs raised",
                exc_info=True,
            )

    def _do_cancel(self) -> None:
        """Revert to the __init__ snapshot and close — with confirm.

        Cancel reverts everything done since the dialog opened, even
        edits that were intermediate-Applied (CS-23 semantic kept).
        Shows ``askokcancel("Discard changes?")`` first when there is
        anything to discard. When the answer is False, stay open;
        otherwise revert and destroy.
        """
        if self._has_uncommitted_changes():
            proceed = messagebox.askokcancel(
                "Discard changes?",
                "There are unsaved changes in this dialog. "
                "Discard them and close?",
                parent=self,
            )
            if not proceed:
                return
        if dict(self._config) != self._snapshot:
            self._config.clear()
            self._config.update(copy.deepcopy(self._snapshot))
            if self._on_apply is not None:
                try:
                    self._on_apply()
                except Exception:
                    _log.warning(
                        "plot_settings_dialog: on_apply raised on cancel",
                        exc_info=True,
                    )
        self._clear_all_modified_tabs()
        self.destroy()

    def _on_close_requested(self) -> None:
        """Window-close [X] is treated as Cancel (matches StyleDialog)."""
        self._do_cancel()

    # ------------------------------------------------------------
    # Defaults actions (in-section buttons)
    # ------------------------------------------------------------

    def _do_save_as_default(self) -> None:
        """Copy the working copy into the in-process _USER_DEFAULTS dict.

        Per the brief, persistence to project.json is deferred to the
        project-I/O wiring session. Lifetime is the process — newly
        opened dialogs in the same session pick up these values via
        Reset Defaults; they are lost on app restart.
        """
        global _USER_DEFAULTS
        _USER_DEFAULTS = copy.deepcopy(self._working)

    def _do_reset_defaults(self) -> None:
        """Load _USER_DEFAULTS into the working copy (refresh widgets only).

        Falls back to _FACTORY_DEFAULTS when the user has never clicked
        Save-as-Default. Does not modify the tab's config or trigger a
        redraw — the user must click Apply to commit.
        """
        source = _USER_DEFAULTS if _USER_DEFAULTS else _FACTORY_DEFAULTS
        self._load_into_working(source)

    def _do_factory_reset(self) -> None:
        """Load _FACTORY_DEFAULTS into the working copy (refresh widgets only).

        Does not modify the tab's config or trigger a redraw — the
        user must click Apply to commit.
        """
        self._load_into_working(_FACTORY_DEFAULTS)

    def _load_into_working(self, source: dict[str, Any]) -> None:
        """Replace the working copy with a deep copy of ``source``.

        Refreshes every widget through its registered ``_control_refresh``
        closure under ``_suspend_writes`` so the trace callbacks don't
        write back into the working copy mid-refresh.
        """
        self._working = copy.deepcopy(dict(source))
        # Make sure every key the dialog might touch has a value.
        for k, v in _FACTORY_DEFAULTS.items():
            self._working.setdefault(k, v)
        self._refresh_widgets_from_working()

    def _refresh_widgets_from_working(self) -> None:
        """Push every working-copy value back into its widget.

        Used by Reset Defaults and Factory Reset. ``_suspend_writes``
        keeps the variable trace callbacks from looping back into
        ``_on_var_write`` while widgets settle.
        """
        self._suspend_writes = True
        try:
            for key, refresh in self._control_refresh.items():
                if key not in self._working:
                    continue
                try:
                    refresh(self._working[key])
                except Exception:
                    _log.warning(
                        "plot_settings_dialog: refresh failed for %r",
                        key, exc_info=True,
                    )
        finally:
            self._suspend_writes = False

    # ------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------

    def _on_destroy(self, _event: tk.Event) -> None:
        """Drop the registry entry when the Toplevel is destroyed.

        Idempotent — both Tk's <Destroy> event and the WM close hook
        can fire, but a missing key is harmless.
        """
        key = id(self._parent)
        if _open_dialogs.get(key) is self:
            _open_dialogs.pop(key, None)
