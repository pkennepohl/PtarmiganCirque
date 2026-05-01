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

    PlotSettingsDialog(
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

    open_plot_settings_dialog(parent, config, on_apply=None,
                              sections=None)
"""

from __future__ import annotations

import copy
import logging
import tkinter as tk
from tkinter import colorchooser, ttk
from typing import Any, Callable

_log = logging.getLogger(__name__)


# =====================================================================
# Module-level state
# =====================================================================

# host widget id → live PlotSettingsDialog. CS-06 mandates one dialog
# per tab; the registry key is the host widget so each tab's dialog
# is independent. Entries are cleaned up by ``_on_destroy``. Tests
# clear this at setUp to avoid cross-test contamination.
_open_dialogs: "dict[int, PlotSettingsDialog]" = {}


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
# light grid, white background, outward ticks, legend visible.
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
    "background_color":      "#ffffff",
    "tick_direction":        "out",   # "in" | "out" | "inout"
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


# =====================================================================
# Module-level factory
# =====================================================================

def open_plot_settings_dialog(
    parent: tk.Widget,
    config: dict,
    on_apply: Callable[[], None] | None = None,
    sections: tuple[str, ...] | None = None,
) -> "PlotSettingsDialog":
    """Open the Plot Settings dialog for a tab, or focus the existing one.

    Per CS-06 each tab has at most one open Plot Settings dialog at a
    time. A second request from the same host raises the existing
    Toplevel rather than creating a duplicate.

    Returns the live ``PlotSettingsDialog`` either way.
    """
    key = id(parent)
    existing = _open_dialogs.get(key)
    if existing is not None:
        try:
            if bool(existing.winfo_exists()):
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass
        # Stale registry entry — fall through to construct fresh.
        _open_dialogs.pop(key, None)
    return PlotSettingsDialog(parent, config, on_apply, sections)


# =====================================================================
# Dialog
# =====================================================================

class PlotSettingsDialog(tk.Toplevel):
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
    ) -> None:
        super().__init__(parent)

        self._parent = parent
        self._config = config
        self._on_apply = on_apply

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

        self.bind("<Destroy>", self._on_destroy, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close_requested)

        # Register so a second open_plot_settings_dialog call finds us.
        _open_dialogs[id(parent)] = self

        # Construction complete: writes from now on flow into the
        # working copy.
        self._suspend_writes = False

    # ------------------------------------------------------------
    # Body construction
    # ------------------------------------------------------------

    def _build_body(self) -> None:
        """Build one LabelFrame per section in order, separated by separators."""
        body = tk.Frame(self, padx=12, pady=8)
        body.pack(fill=tk.BOTH, expand=True)
        self._body = body

        for i, name in enumerate(self._sections):
            builder = getattr(self, f"_build_section_{name}", None)
            if builder is None:
                _log.warning(
                    "plot_settings_dialog: no builder for section %r", name,
                )
                continue
            if i > 0:
                ttk.Separator(body, orient=tk.HORIZONTAL).pack(
                    fill=tk.X, pady=(8, 4),
                )
            frame = tk.LabelFrame(
                body, text=_SECTION_TITLES[name], padx=8, pady=4,
            )
            frame.pack(fill=tk.X)
            frame.columnconfigure(1, weight=1)
            builder(frame)

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

        # Background colour swatch (click → colorchooser).
        tk.Label(parent, text="Background:", font=("", 9, "bold")).grid(
            row=1, column=0, sticky="w", pady=2,
        )
        self._make_colour_swatch(parent, 1, 1, "background_color")

        # Tick direction radio.
        tk.Label(parent, text="Tick direction:", font=("", 9, "bold")).grid(
            row=2, column=0, sticky="w", pady=2,
        )
        radio_frame = tk.Frame(parent)
        radio_frame.grid(row=2, column=1, columnspan=2, sticky="w")
        var = tk.StringVar(
            value=str(self._working.get("tick_direction", "out")),
        )
        self._control_vars["tick_direction"] = var
        for display, value in (
            ("In", "in"), ("Out", "out"), ("Both", "inout"),
        ):
            tk.Radiobutton(
                radio_frame, text=display, variable=var, value=value,
            ).pack(side=tk.LEFT, padx=3)
        var.trace_add(
            "write",
            lambda *_, k="tick_direction", v=var:
                self._on_var_write(k, v.get()),
        )

        def _refresh_dir(value, _v=var):
            _v.set(str(value))
        self._control_refresh["tick_direction"] = _refresh_dir

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

    def _on_int_var_write(self, key: str, var: tk.IntVar) -> None:
        if self._suspend_writes:
            return
        try:
            self._working[key] = int(var.get())
        except (tk.TclError, ValueError):
            # Bad spinbox state (mid-edit). Skip until valid.
            pass

    # ------------------------------------------------------------
    # Bottom button row (Apply / Save / Cancel)
    # ------------------------------------------------------------

    def _build_button_row(self) -> None:
        """Apply · Save · Cancel row at the bottom (CS-23).

        Mirrors the CS-05 StyleDialog vocabulary: ``Apply`` commits and
        keeps the dialog open for further iteration; ``Save`` commits
        and closes (the "Save & Close" gesture); ``Cancel`` reverts to
        the snapshot taken at ``__init__`` and closes.
        """
        btn_row = tk.Frame(self)
        btn_row.pack(pady=(4, 10))

        self._apply_btn = tk.Button(
            btn_row, text="Apply", width=10, command=self._do_apply,
        )
        self._apply_btn.pack(side=tk.LEFT, padx=3)

        self._save_btn = tk.Button(
            btn_row, text="Save", width=8, command=self._do_save,
        )
        self._save_btn.pack(side=tk.LEFT, padx=3)

        self._cancel_btn = tk.Button(
            btn_row, text="Cancel", width=8, command=self._do_cancel,
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=3)

    # ------------------------------------------------------------
    # Bottom button actions
    # ------------------------------------------------------------

    def _do_apply(self) -> None:
        """Commit the working copy into the tab's config and notify.

        Mutates the caller's dict in place so the tab's existing
        reference (``self._plot_config``) sees the new values without
        a reassignment. The tab's ``on_apply`` callback (typically
        ``self._redraw``) is invoked once afterwards.
        """
        # Mutate in place: keep the tab's reference valid.
        self._config.clear()
        self._config.update(copy.deepcopy(self._working))
        if self._on_apply is not None:
            try:
                self._on_apply()
            except Exception:
                _log.warning(
                    "plot_settings_dialog: on_apply raised", exc_info=True,
                )

    def _do_save(self) -> None:
        """Commit the working copy and close the dialog (CS-23).

        Equivalent to ``_do_apply`` + ``destroy``. This is the explicit
        "Save & Close" gesture the user expects from a modal dialog;
        before CS-23 the only persist-and-close path required hitting
        Apply then closing via [X], which the protocol handler treated
        as Cancel — silently reverting the just-committed edit.
        """
        self._do_apply()
        self.destroy()

    def _do_cancel(self) -> None:
        """Revert to the snapshot taken at __init__ and close.

        Even if the user clicked Apply intermediate times during this
        session, Cancel reverts everything they did since the dialog
        opened — that matches the modal/snapshot contract the user
        expects from a Cancel gesture.
        """
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
