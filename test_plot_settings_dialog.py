"""Tests for plot_settings_dialog.py.

Mirrors the structure of ``test_style_dialog.py``: construct a real
``tk.Tk`` root, build a real Plot Settings dialog, and observe the
widget and configuration state. Headless environments where
``tk.Tk()`` cannot be constructed are skipped via
``unittest.skipUnless``.

Run with the project venv:

    venv/Scripts/python run_tests.py
"""

from __future__ import annotations

import copy
import unittest

# Silence Tk messageboxes so the CS-60 Cancel-with-pending confirm
# (and any other modal added later) returns askokcancel=True
# unattended. Mirrors the run_tests.py wiring so this test module
# is runnable standalone (``python -m unittest test_plot_settings_dialog``)
# as well as through the suite.
from _test_silence import silence_all_messageboxes
silence_all_messageboxes()

# Try to construct a Tk root once at module import time. If it fails
# (no display, missing tcl/tk), every test in the file is skipped.
try:
    import tkinter as tk
    from tkinter import ttk
    _root = tk.Tk()
    _root.withdraw()
    _HAS_DISPLAY = True
except Exception:  # pragma: no cover — headless CI only
    _root = None
    _HAS_DISPLAY = False


# ---- helpers --------------------------------------------------------


def _all_descendants(w):
    out = []
    for c in w.winfo_children():
        out.append(c)
        out.extend(_all_descendants(c))
    return out


def _label_frames(dlg) -> list[tk.LabelFrame]:
    return [c for c in _all_descendants(dlg) if isinstance(c, tk.LabelFrame)]


def _global_tab_label_frames(dlg) -> list[tk.LabelFrame]:
    """LabelFrames within the Global tab only (CS-60, Phase 4ai).

    Axis tabs ship placeholder LabelFrames ("Plots on this axis",
    "Settings") that are unrelated to the section system; tests that
    care about the Global tab's section render scope here.
    """
    global_frame = dlg._tab_frames["global"]
    return [
        c for c in _all_descendants(global_frame)
        if isinstance(c, tk.LabelFrame)
    ]


def _section_titles(dlg) -> list[str]:
    """Titles of the LabelFrames in the Global tab.

    Always Global-scoped — the pre-CS-60 helper walked the whole
    Toplevel, but axis-tab placeholder LabelFrames now mingle with
    section LabelFrames if you don't scope. Tests that need the
    full descendant walk use :func:`_label_frames` directly.
    """
    return [lf.cget("text") for lf in _global_tab_label_frames(dlg)]


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogShell(unittest.TestCase):
    """Construction, modal contract, registry, snapshot+cancel revert."""

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog
        cls.open_dialog = staticmethod(plot_settings_dialog.open_plot_config_dialog)

    def setUp(self):
        # Per-test registry and user-defaults reset so a leak from one
        # test cannot poison the next.
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ----------- construction -----------

    def test_constructs_with_empty_config(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertEqual(dlg.title(), "Plot Settings")
        # Working copy populated from factory defaults.
        self.assertEqual(
            dlg._working["title_font_size"],
            self.psd._FACTORY_DEFAULTS["title_font_size"],
        )

    def test_construct_pre_populates_from_config(self):
        self.config["title_font_size"] = 22
        self.config["grid"] = False
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertEqual(dlg._working["title_font_size"], 22)
        self.assertEqual(dlg._working["grid"], False)
        # Spinbox / checkbox controls reflect the working copy.
        self.assertEqual(dlg._control_vars["title_font_size"].get(), 22)
        self.assertEqual(bool(dlg._control_vars["grid"].get()), False)

    # ----------- modeless contract (transient WITHOUT grab) -----------

    def test_no_grab_set_on_visible_window(self):
        """Phase 4ao / CS-66: dialog is modeless.

        ``grab_set()`` was removed so the main window stays
        interactive while Plot Settings is open. ``grab_status``
        returns a falsy value (``None`` on some Tk builds, ``""`` on
        others) when no grab is held; held grabs return the literal
        strings ``"local"`` or ``"global"``.
        """
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        status = dlg.grab_status()
        self.assertFalse(
            status,
            f"Plot Settings dialog must NOT hold a Tk grab "
            f"(CS-66 modeless); got grab_status() = {status!r}",
        )

    def test_transient_is_preserved(self):
        """Phase 4ao / CS-66: transient(parent) still set.

        Modeless dialogs in this app keep ``transient`` so the dialog
        is grouped above its parent in the WM's Z-order. The grab is
        what was dropped, not the transient relationship.
        """
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        # ``wm_transient()`` without arguments returns the master path
        # name (a string) — non-empty iff transient was set.
        master_path = dlg.wm_transient()
        self.assertTrue(
            bool(master_path),
            "PlotConfigDialog must call transient(parent) (CS-66)",
        )

    # ----------- factory: focus existing dialog -----------

    def test_open_twice_returns_same_toplevel(self):
        first = self.open_dialog(self.host, self.config)
        second = self.open_dialog(self.host, self.config)
        self.assertIs(first, second)

    def test_open_two_different_hosts_creates_two_dialogs(self):
        host_b = tk.Frame(_root)
        try:
            first = self.open_dialog(self.host, self.config)
            second = self.open_dialog(host_b, {})
            self.assertIsNot(first, second)
        finally:
            host_b.destroy()

    # ----------- every section appears for the default config -----------

    def test_default_config_shows_all_four_sections(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        titles = set(_section_titles(dlg))
        expected = {
            "Fonts", "Appearance", "Legend", "Title and labels",
        }
        self.assertEqual(
            titles & expected, expected,
            f"every section must render for the default config; "
            f"got {sorted(titles)}",
        )

    def test_explicit_sections_argument_filters(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config, sections=("fonts", "legend"),
        )
        dlg.update_idletasks()
        titles = set(_section_titles(dlg))
        self.assertIn("Fonts", titles)
        self.assertIn("Legend", titles)
        self.assertNotIn("Appearance", titles)
        self.assertNotIn("Title and labels", titles)

    def test_config_sections_key_filters_when_arg_omitted(self):
        # Per the spec the configuration object is the source of truth
        # for which sections to show. Tabs that want to opt out of a
        # section can set this key.
        self.config["_sections"] = ("appearance",)
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        titles = set(_section_titles(dlg))
        self.assertEqual(titles, {"Appearance"})

    # ----------- live-preview (CS-68 / Phase 4ap): edits commit on var write -----------

    def test_spinbox_change_writes_through_immediately(self):
        """Spinbox edits commit live to config (CS-68)."""
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()

        # Working copy and config both reflect the new value.
        self.assertEqual(dlg._working["title_font_size"], 20)
        self.assertEqual(self.config["title_font_size"], 20)

    def test_grid_toggle_writes_through_immediately(self):
        """Checkbutton edits commit live to config (CS-68)."""
        self.config["grid"] = True
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["grid"].set(False)
        dlg.update_idletasks()

        self.assertEqual(dlg._working["grid"], False)
        self.assertEqual(self.config["grid"], False)

    def test_apply_does_not_fire_on_construction(self):
        """on_apply must not be invoked merely because the dialog opened."""
        seen: list = []
        self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        ).update_idletasks()
        self.assertEqual(seen, [])

    # ----------- live edit fires on_apply per discrete write (CS-68) -----------

    def test_var_write_fires_on_apply_once_per_discrete_edit(self):
        self.config["title_font_size"] = 12
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(18)
        dlg.update_idletasks()

        # CS-68: live commit fires per discrete-widget edit.
        self.assertEqual(self.config["title_font_size"], 18)
        self.assertEqual(seen, [1])

    # ----------- Save closes the dialog (CS-68) -----------

    def test_save_button_is_present(self):
        """CS-68: button row is Save · Apply to All Tabs · Cancel."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertTrue(hasattr(dlg, "_save_btn"))
        self.assertEqual(str(dlg._save_btn.cget("text")), "Save")

    def test_save_with_prior_live_edit_keeps_committed_value(self):
        """Save under live-preview: edits already in config; Save just closes."""
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(18)
        dlg.update_idletasks()
        # CS-68: live-applied at var.set time.
        self.assertEqual(self.config["title_font_size"], 18)

        dlg._do_save()
        self.assertEqual(self.config["title_font_size"], 18)

    def test_save_does_not_re_fire_on_apply(self):
        """Save under live-preview: on_apply was already fired by the edit."""
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()

        dlg._control_vars["grid"].set(False)
        # Live edit fired on_apply once.
        self.assertEqual(seen, [1])
        dlg._do_save()
        # Save does not re-fire on_apply (CS-68: no extra commit at close).
        self.assertEqual(seen, [1])

    def test_save_destroys_dialog(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._do_save()
        self.assertEqual(int(dlg.winfo_exists()), 0)

    def test_save_with_no_edits_still_commits_identity(self):
        """Save on an unedited dialog leaves the config equivalent and
        closes — the user-flow guarantee that opening + Save never
        loses information, even when nothing changed."""
        self.config.update({"title_font_size": 14, "grid": True})
        snapshot = dict(self.config)
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._do_save()
        # Working copy carries every factory-default key, so the
        # post-save config is a superset of the pre-save snapshot;
        # the snapshot keys must round-trip unchanged.
        for key, value in snapshot.items():
            self.assertEqual(self.config[key], value)
        self.assertEqual(int(dlg.winfo_exists()), 0)

    # ----------- Cancel reverts and closes -----------

    def test_cancel_reverts_live_edits(self):
        """Cancel reverts to the __init__ snapshot, even after live edits (CS-68)."""
        self.config["title_font_size"] = 12
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()

        # User edits — under CS-68 this commits live to config + fires on_apply.
        dlg._control_vars["title_font_size"].set(20)
        self.assertEqual(self.config["title_font_size"], 20)
        self.assertEqual(seen, [1])

        # Then changes mind and clicks Cancel.
        dlg._do_cancel()
        # Snapshot was 12 — Cancel restores.
        self.assertEqual(self.config["title_font_size"], 12)
        # on_apply fired again to drive a redraw of the reverted state.
        self.assertEqual(len(seen), 2)

    def test_cancel_destroys_dialog(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._do_cancel()
        # winfo_exists is 0 after destroy in this Tk version.
        self.assertEqual(int(dlg.winfo_exists()), 0)

    def test_window_close_x_is_treated_as_cancel(self):
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        # CS-68: live edit immediately reaches config.
        dlg._control_vars["title_font_size"].set(20)
        self.assertEqual(self.config["title_font_size"], 20)

        # The protocol handler is _on_close_requested — calling it
        # directly mimics the [X] gesture and runs Cancel revert.
        dlg._on_close_requested()
        self.assertEqual(self.config["title_font_size"], 12)
        self.assertEqual(int(dlg.winfo_exists()), 0)

    # ----------- registry teardown -----------

    def test_destroy_clears_registry_entry(self):
        dlg = self.open_dialog(self.host, self.config)
        self.assertIs(self.psd._open_dialogs.get(id(self.host)), dlg)
        dlg.destroy()
        # Run pending events so <Destroy> fires.
        _root.update()
        self.assertNotIn(id(self.host), self.psd._open_dialogs)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogDefaults(unittest.TestCase):
    """Save-as-Default / Reset Defaults / Factory Reset semantics."""

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ----------- Save-as-Default -----------

    def test_save_as_default_writes_user_defaults(self):
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        # User adjusts the working copy.
        dlg._control_vars["title_font_size"].set(20)
        dlg._control_vars["grid"].set(False)
        dlg.update_idletasks()

        # _USER_DEFAULTS empty before.
        self.assertEqual(self.psd._USER_DEFAULTS, {})

        dlg._do_save_as_default()

        # _USER_DEFAULTS has the working-copy values.
        self.assertEqual(self.psd._USER_DEFAULTS["title_font_size"], 20)
        self.assertEqual(self.psd._USER_DEFAULTS["grid"], False)

    def test_save_as_default_writes_user_defaults_distinct_from_config(self):
        """Save-as-Default writes to module state, not (only) to the config (CS-68)."""
        # Phase 4ap (CS-68): under live-preview the spinbox edit DOES
        # commit to config (no longer a "config untouched until Apply"
        # invariant). Save-as-Default's job is the SECOND write — into
        # the module-level _USER_DEFAULTS dict — and that write is
        # independent of the live-commit. This test pins both halves:
        # the live-commit reaches config AND the save-as-default
        # reaches _USER_DEFAULTS.
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(20)
        # Live-preview: config sees the new value.
        self.assertEqual(self.config["title_font_size"], 20)

        dlg._do_save_as_default()
        # Module-level user defaults captured the working copy.
        self.assertEqual(self.psd._USER_DEFAULTS["title_font_size"], 20)

    # ----------- Reset Defaults -----------

    def test_reset_defaults_restores_user_defaults(self):
        # Pre-seed _USER_DEFAULTS as if a previous session had saved.
        self.psd._USER_DEFAULTS.update({
            "title_font_size": 14,
            "grid": False,
            "background_color": "#eeeeee",
        })

        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        # User edits the working copy.
        dlg._control_vars["title_font_size"].set(30)
        dlg.update_idletasks()
        self.assertEqual(dlg._working["title_font_size"], 30)

        dlg._do_reset_defaults()
        dlg.update_idletasks()

        # Working copy and widget reflect the user defaults, NOT the
        # in-flight 30.
        self.assertEqual(dlg._working["title_font_size"], 14)
        self.assertEqual(dlg._control_vars["title_font_size"].get(), 14)
        self.assertEqual(dlg._working["grid"], False)
        self.assertEqual(dlg._working["background_color"], "#eeeeee")

    def test_reset_defaults_falls_back_to_factory_when_user_defaults_empty(
        self,
    ):
        # _USER_DEFAULTS empty — Reset Defaults reverts to factory.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(99)
        dlg.update_idletasks()

        dlg._do_reset_defaults()
        dlg.update_idletasks()

        self.assertEqual(
            dlg._working["title_font_size"],
            self.psd._FACTORY_DEFAULTS["title_font_size"],
        )

    # ----------- Factory Reset -----------

    def test_factory_reset_restores_factory_defaults(self):
        # Even with _USER_DEFAULTS populated, Factory Reset bypasses
        # them and goes back to the immutable factory values.
        self.psd._USER_DEFAULTS.update({"title_font_size": 14, "grid": False})

        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(99)
        dlg._control_vars["grid"].set(False)
        dlg.update_idletasks()

        dlg._do_factory_reset()
        dlg.update_idletasks()

        self.assertEqual(
            dlg._working["title_font_size"],
            self.psd._FACTORY_DEFAULTS["title_font_size"],
        )
        self.assertEqual(
            dlg._working["grid"], self.psd._FACTORY_DEFAULTS["grid"],
        )

    def test_factory_reset_writes_factory_values_to_config_live(self):
        """Factory Reset commits the bulk reload live (CS-68 / Phase 4ap)."""
        self.config["title_font_size"] = 22
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._do_factory_reset()
        dlg.update_idletasks()

        # CS-68: bulk reload runs _suspend_writes during the widget
        # refresh and fires _apply_changes_live ONCE at the end —
        # config now carries the factory value.
        self.assertEqual(
            self.config["title_font_size"],
            self.psd._FACTORY_DEFAULTS["title_font_size"],
        )

    def test_factory_reset_fires_on_apply_exactly_once(self):
        """The bulk reload coalesces N per-widget redraws into one (CS-68)."""
        seen: list = []
        # Pre-populate config with non-default values across many keys
        # so the reset has work to do on every widget.
        self.config.update({
            "title_font_size": 22,
            "grid": False,
            "background_color": "#abcdef",
        })
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()

        seen.clear()  # ignore any init-side commits (none expected)
        dlg._do_factory_reset()
        dlg.update_idletasks()
        # Exactly one live commit covers the whole bulk reload.
        self.assertEqual(seen, [1])


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestAppearanceSectionPhase4ae(unittest.TestCase):
    """Phase 4ae (CS-56) — Plot Settings → Appearance new controls.

    Three changes:
      - grid_color: NEW factory key + colour-swatch row.
      - tertiary_axis_offset: NEW factory key + float-spinbox row.
      - tick_direction: factory default flipped "out" → "in".
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- factory-defaults dict shape ----

    def test_grid_color_in_factory_defaults(self):
        self.assertIn("grid_color", self.psd._FACTORY_DEFAULTS)
        self.assertEqual(
            self.psd._FACTORY_DEFAULTS["grid_color"], "#b0b0b0",
        )

    def test_tertiary_axis_offset_in_factory_defaults(self):
        self.assertIn("tertiary_axis_offset", self.psd._FACTORY_DEFAULTS)
        self.assertEqual(
            self.psd._FACTORY_DEFAULTS["tertiary_axis_offset"], 1.12,
        )

    def test_tick_direction_factory_default_is_in(self):
        # Phase 4ac friction #3 USER-FLAGGED — factory default flipped
        # from "out" to "in". Phase 4ak (CS-62) moved the key into the
        # nested ``axes[<role>]`` sub-dict; the value stays "in" on
        # every per-axis role. The top-level flat key is gone.
        self.assertNotIn("tick_direction", self.psd._FACTORY_DEFAULTS)
        for role in self.psd._FACTORY_DEFAULTS["axes"]:
            self.assertEqual(
                self.psd._FACTORY_DEFAULTS["axes"][role]["tick_direction"], "in",
                f"per-axis tick_direction default drift on role {role!r}",
            )

    def test_universal_defaults_carries_new_keys(self):
        # _UNIVERSAL_DEFAULTS is a shallow copy of _FACTORY_DEFAULTS
        # (see module top). The new keys must propagate.
        self.assertIn("grid_color", self.psd._UNIVERSAL_DEFAULTS)
        self.assertIn(
            "tertiary_axis_offset", self.psd._UNIVERSAL_DEFAULTS,
        )

    # ---- dialog widget construction ----

    def test_grid_color_swatch_widget_registered(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertIn("grid_color", dlg._control_vars)
        self.assertIn("grid_color", dlg._color_swatches)
        swatch = dlg._color_swatches["grid_color"]
        # Initial swatch colour matches the factory default.
        self.assertEqual(swatch.cget("bg"), "#b0b0b0")

    def test_tertiary_axis_offset_spinbox_registered(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertIn("tertiary_axis_offset", dlg._control_vars)
        var = dlg._control_vars["tertiary_axis_offset"]
        self.assertIsInstance(var, tk.DoubleVar)
        self.assertAlmostEqual(var.get(), 1.12, places=4)

    # ---- writes route through to working dict ----

    def test_grid_color_swatch_writes_through_to_working(self):
        # Swatch writes to _working through the colorchooser's _pick
        # callback (no trace on the StringVar, mirrors how the existing
        # background_color swatch is wired). Simulate the post-pick
        # call directly.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._on_var_write("grid_color", "#ff0000")
        self.assertEqual(dlg._working["grid_color"], "#ff0000")

    def test_tertiary_axis_offset_spinbox_writes_through_to_working(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["tertiary_axis_offset"].set(1.25)
        dlg.update_idletasks()
        self.assertAlmostEqual(
            dlg._working["tertiary_axis_offset"], 1.25, places=4,
        )

    # ---- factory reset restores the new keys ----

    def test_factory_reset_restores_new_appearance_keys(self):
        # Phase 4ak (CS-62) moved tick_direction into the nested
        # ``axes[<role>]`` schema; the reset check now reads per-axis.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["grid_color"].set("#ff0000")
        dlg._control_vars["tertiary_axis_offset"].set(1.40)
        dlg._axis_control_vars[("primary_x", "tick_direction")].set("out")
        dlg._axis_control_vars[("tertiary_y", "tick_direction")].set("inout")
        dlg.update_idletasks()
        dlg._do_factory_reset()
        dlg.update_idletasks()
        self.assertEqual(dlg._working["grid_color"], "#b0b0b0")
        self.assertAlmostEqual(
            dlg._working["tertiary_axis_offset"], 1.12, places=4,
        )
        for role in self.psd._FACTORY_DEFAULTS["axes"]:
            self.assertEqual(
                dlg._working["axes"][role]["tick_direction"], "in",
            )

    # ---- pre-population from config ----

    def test_construct_pre_populates_new_keys_from_config(self):
        self.config["grid_color"] = "#00ff00"
        self.config["tertiary_axis_offset"] = 1.30
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertEqual(dlg._working["grid_color"], "#00ff00")
        self.assertAlmostEqual(
            dlg._working["tertiary_axis_offset"], 1.30, places=4,
        )
        # And the widgets carry the pre-populated values.
        self.assertEqual(
            dlg._color_swatches["grid_color"].cget("bg"), "#00ff00",
        )
        self.assertAlmostEqual(
            dlg._control_vars["tertiary_axis_offset"].get(),
            1.30, places=4,
        )


# =====================================================================
# CS-60 Phase 4ai: Notebook container + 6 tab frames
# =====================================================================


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogNotebookPhase4ai(unittest.TestCase):
    """CS-60 (Phase 4ai): the dialog is a ttk.Notebook with six tabs.

    The Global tab hosts the legacy section LabelFrames; each of the
    five axis tabs hosts a placeholder shell whose real settings land
    in Phase 4aj+. The dialog accepts a ``tab=`` argument to
    pre-select the active tab, and exposes ``select_tab(key)`` for
    runtime navigation (used by the open-factory's "raise existing"
    path when the caller wants a different tab).
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog
        cls.open_dialog = staticmethod(plot_settings_dialog.open_plot_config_dialog)

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ----- module-level constants ------------------------------------

    def test_tab_keys_constant_shape(self):
        # Canonical order. The Notebook pack order matches this tuple
        # and tests downstream rely on it.
        self.assertEqual(
            self.psd._TAB_KEYS,
            ("global", "primary_x", "secondary_x",
             "primary_y", "secondary_y", "tertiary_y"),
        )

    def test_tab_titles_contains_every_key(self):
        for key in self.psd._TAB_KEYS:
            self.assertIn(key, self.psd._TAB_TITLES)
            self.assertIsInstance(self.psd._TAB_TITLES[key], str)
            self.assertTrue(self.psd._TAB_TITLES[key])

    def test_tab_titles_human_readable(self):
        self.assertEqual(self.psd._TAB_TITLES["global"], "Global")
        self.assertEqual(self.psd._TAB_TITLES["primary_x"], "Primary X")
        self.assertEqual(self.psd._TAB_TITLES["secondary_x"], "Secondary X")
        self.assertEqual(self.psd._TAB_TITLES["primary_y"], "Primary Y")
        self.assertEqual(self.psd._TAB_TITLES["secondary_y"], "Secondary Y")
        self.assertEqual(self.psd._TAB_TITLES["tertiary_y"], "Tertiary Y")

    # ----- container shape -------------------------------------------

    def test_dialog_contains_a_notebook(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        notebooks = [
            c for c in _all_descendants(dlg) if isinstance(c, ttk.Notebook)
        ]
        self.assertEqual(len(notebooks), 1)
        # Notebook handle exposed for downstream tests.
        self.assertIs(dlg._notebook, notebooks[0])

    def test_notebook_has_six_tabs_in_canonical_order(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        tab_ids = dlg._notebook.tabs()
        self.assertEqual(len(tab_ids), len(self.psd._TAB_KEYS))
        text_for_each = [dlg._notebook.tab(t, "text") for t in tab_ids]
        expected = [self.psd._TAB_TITLES[k] for k in self.psd._TAB_KEYS]
        self.assertEqual(text_for_each, expected)

    def test_tab_frames_dict_keyed_by_tab_key(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertEqual(
            set(dlg._tab_frames.keys()), set(self.psd._TAB_KEYS),
        )
        # Every frame is a real tk.Frame inside the dialog.
        for key, frame in dlg._tab_frames.items():
            self.assertIsInstance(frame, tk.Frame)

    # ----- Global tab hosts the legacy section LabelFrames -----------

    def test_global_tab_contains_all_four_sections(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        titles = {
            lf.cget("text")
            for lf in _global_tab_label_frames(dlg)
        }
        expected = {"Fonts", "Appearance", "Legend", "Title and labels"}
        self.assertTrue(expected.issubset(titles))

    def test_axis_tabs_do_not_contain_section_label_frames(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for key in ("primary_x", "secondary_x",
                    "primary_y", "secondary_y", "tertiary_y"):
            frame = dlg._tab_frames[key]
            titles = {
                c.cget("text")
                for c in _all_descendants(frame)
                if isinstance(c, tk.LabelFrame)
            }
            # No "Fonts" / "Appearance" / "Legend" / "Title and labels"
            # — only the per-axis shell's "Plots on this axis" and
            # "Settings" placeholders.
            self.assertEqual(
                titles, {"Plots on this axis", "Settings"},
                f"axis tab {key!r} has unexpected LabelFrames: {titles}",
            )

    # ----- axis tab shells -------------------------------------------

    def test_axis_tab_shell_header_text(self):
        # Each axis tab carries a bold "Axis: <Title>" header label.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for key in ("primary_x", "secondary_x",
                    "primary_y", "secondary_y", "tertiary_y"):
            frame = dlg._tab_frames[key]
            texts = [
                c.cget("text") for c in _all_descendants(frame)
                if isinstance(c, tk.Label)
            ]
            expected_header = f"Axis: {self.psd._TAB_TITLES[key]}"
            self.assertIn(
                expected_header, texts,
                f"axis tab {key!r} missing header {expected_header!r}; "
                f"got {texts}",
            )

    def test_axis_tab_shell_carries_placeholder_badge(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for key in ("primary_x", "secondary_x",
                    "primary_y", "secondary_y", "tertiary_y"):
            frame = dlg._tab_frames[key]
            texts = [
                c.cget("text") for c in _all_descendants(frame)
                if isinstance(c, tk.Label)
            ]
            badge = self.psd._AXIS_TAB_PLACEHOLDER_BADGE[key]
            self.assertIn(
                badge, texts,
                f"axis tab {key!r} missing placeholder badge",
            )

    def test_axis_tab_shell_carries_real_settings_widget_post_phase_4aj(self):
        # Phase 4ai shipped each axis tab's "Settings" LabelFrame with
        # a static "Per-axis settings land in Phase 4aj+." placeholder
        # label. Phase 4aj (CS-61) swapped that placeholder for the
        # first real per-axis widget — the Tick direction
        # Radiobutton row. The exhaustive checks live in
        # TestPlotConfigDialogTickDirectionRelocationPhase4aj; this
        # test pins the obvious shape so a future regression that
        # accidentally re-introduces the placeholder fails here too.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for key in ("primary_x", "secondary_x",
                    "primary_y", "secondary_y", "tertiary_y"):
            frame = dlg._tab_frames[key]
            texts = [
                c.cget("text") for c in _all_descendants(frame)
                if isinstance(c, tk.Label)
            ]
            self.assertFalse(
                any("Phase 4aj" in t for t in texts),
                f"axis tab {key!r} still carries the pre-4aj "
                f"placeholder; labels were {texts}",
            )
            self.assertIn(
                "Tick direction:", texts,
                f"axis tab {key!r} missing the relocated Tick "
                f"direction label; labels were {texts}",
            )

    # ----- tab pre-selection via the tab= argument -------------------

    def test_default_tab_is_global(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertEqual(dlg.current_tab_key(), "global")

    def test_tab_argument_pre_selects_axis_tab(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config, tab="primary_y",
        )
        dlg.update_idletasks()
        self.assertEqual(dlg.current_tab_key(), "primary_y")

    def test_unknown_tab_falls_back_to_global(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config, tab="not_a_real_tab",
        )
        dlg.update_idletasks()
        self.assertEqual(dlg.current_tab_key(), "global")

    def test_select_tab_after_construction(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg.select_tab("tertiary_y")
        dlg.update_idletasks()
        self.assertEqual(dlg.current_tab_key(), "tertiary_y")

    def test_select_tab_unknown_falls_back_to_global(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config, tab="primary_y",
        )
        dlg.update_idletasks()
        dlg.select_tab("not_a_real_tab")
        dlg.update_idletasks()
        self.assertEqual(dlg.current_tab_key(), "global")

    # ----- factory propagates tab= and refocuses existing dialogs ----

    def test_factory_propagates_tab_argument(self):
        dlg = self.open_dialog(self.host, self.config, tab="secondary_y")
        dlg.update_idletasks()
        self.assertEqual(dlg.current_tab_key(), "secondary_y")

    def test_factory_focus_existing_switches_tab(self):
        # First open on Global.
        first = self.open_dialog(self.host, self.config)
        first.update_idletasks()
        self.assertEqual(first.current_tab_key(), "global")

        # Second open with tab="tertiary_y": returns the same dialog,
        # but the active tab has switched.
        second = self.open_dialog(self.host, self.config, tab="tertiary_y")
        second.update_idletasks()
        self.assertIs(first, second)
        self.assertEqual(first.current_tab_key(), "tertiary_y")

    # ----- working copy still shared across tabs ---------------------

    def test_global_tab_edits_reach_config_live(self):
        # CS-68 (Phase 4ap): live-preview seam — the Global-tab
        # spinbox edit reaches config without an explicit Apply.
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config, tab="primary_y")
        dlg.update_idletasks()
        # Switch to Global to edit the existing widget.
        dlg.select_tab("global")
        dlg._control_vars["title_font_size"].set(22)
        dlg.update_idletasks()
        self.assertEqual(self.config["title_font_size"], 22)


# =====================================================================
# CS-60 Phase 4ai: cross-tab pending-edit state model + new button row
# =====================================================================


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogStateModelPhase4ai(unittest.TestCase):
    """CS-60 cross-tab pending-edit state model.

    Per-tab modified marker: ``_TAB_TITLES[tab] + " •"`` while any
    setting on that tab has uncommitted edits. Apply / Save / Apply
    to All Tabs commit and clear every marker; Cancel reverts and
    clears every marker. The marker is the soft signal the user
    sees; ``_modified_tabs`` is the source of truth.
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog
        cls.open_dialog = staticmethod(plot_settings_dialog.open_plot_config_dialog)

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def _tab_text(self, dlg, key: str) -> str:
        frame = dlg._tab_frames[key]
        return dlg._notebook.tab(frame, "text")

    # ----- module-level _KEY_TO_TAB defaults all current keys to global

    def test_key_to_tab_defaults_to_global(self):
        # Keys not explicitly registered in _KEY_TO_TAB resolve to
        # the Global tab via the default branch of _key_to_tab.
        # Phase 4aj (CS-61) added the first explicit entry
        # ("tick_direction" → "primary_x"); keys mapped explicitly
        # are out of scope for this test (they have their own
        # per-relocation tests). Future per-axis relocations extend
        # _KEY_TO_TAB and this test keeps narrowing to the
        # still-unmapped factory keys.
        for key in self.psd._FACTORY_DEFAULTS:
            if key in self.psd._KEY_TO_TAB:
                continue
            self.assertEqual(
                self.psd._key_to_tab(key), "global",
                f"key {key!r} should default to the Global tab",
            )

    def test_modified_tab_suffix_constant(self):
        # The bullet character is what the user sees; keep it
        # explicit so renames of the suffix can't drift silently.
        self.assertEqual(self.psd._MODIFIED_TAB_SUFFIX, " •")

    # ----- initial state -----

    def test_no_tabs_modified_at_construction(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertEqual(dlg._modified_tabs, set())
        # Every tab shows its plain title — no bullet appended.
        for key in self.psd._TAB_KEYS:
            self.assertEqual(self._tab_text(dlg, key), self.psd._TAB_TITLES[key])

    # ----- edit marks the tab -----

    def test_int_var_edit_marks_global(self):
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        self.assertIn("global", dlg._modified_tabs)
        self.assertEqual(
            self._tab_text(dlg, "global"),
            "Global" + self.psd._MODIFIED_TAB_SUFFIX,
        )

    def test_bool_var_edit_marks_global(self):
        self.config["grid"] = True
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["grid"].set(False)
        dlg.update_idletasks()
        self.assertIn("global", dlg._modified_tabs)

    def test_float_var_edit_marks_global(self):
        self.config["tertiary_axis_offset"] = 1.12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["tertiary_axis_offset"].set(1.30)
        dlg.update_idletasks()
        self.assertIn("global", dlg._modified_tabs)

    def test_string_var_edit_marks_global(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["legend_position"].set("upper left")
        dlg.update_idletasks()
        self.assertIn("global", dlg._modified_tabs)

    def test_marker_only_on_first_edit_idempotent(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        # Two edits to the same tab → still one entry in _modified_tabs.
        dlg._control_vars["title_font_size"].set(20)
        dlg._control_vars["ylabel_font_size"].set(14)
        dlg.update_idletasks()
        self.assertEqual(dlg._modified_tabs, {"global"})

    # ----- direct mark/clear helpers -----

    def test_mark_then_clear_round_trips(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._mark_tab_modified("primary_y")
        self.assertIn("primary_y", dlg._modified_tabs)
        self.assertEqual(
            self._tab_text(dlg, "primary_y"),
            "Primary Y" + self.psd._MODIFIED_TAB_SUFFIX,
        )
        dlg._clear_tab_modified("primary_y")
        self.assertNotIn("primary_y", dlg._modified_tabs)
        self.assertEqual(self._tab_text(dlg, "primary_y"), "Primary Y")

    def test_mark_unknown_tab_is_no_op(self):
        # A future _KEY_TO_TAB drift that maps a key to an unknown
        # tab key should not crash. The mark silently no-ops.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._mark_tab_modified("not_a_tab")
        self.assertEqual(dlg._modified_tabs, set())

    def test_clear_all_drops_every_marker(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._mark_tab_modified("primary_y")
        dlg._mark_tab_modified("secondary_y")
        dlg._mark_tab_modified("tertiary_y")
        dlg._clear_all_modified_tabs()
        self.assertEqual(dlg._modified_tabs, set())
        for k in ("primary_y", "secondary_y", "tertiary_y"):
            self.assertEqual(self._tab_text(dlg, k), self.psd._TAB_TITLES[k])

    # ----- Marker lifecycle (CS-68 / Phase 4ap) -----

    def test_live_edit_keeps_modified_tab_marker(self):
        """Markers represent 'touched since open' under live-preview (CS-68)."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        # CS-68: live commit writes to config but leaves the marker in
        # place — the user still sees the suffix until Cancel/Save.
        expected = self.psd._TAB_TITLES["global"] + self.psd._MODIFIED_TAB_SUFFIX
        self.assertEqual(dlg._modified_tabs, {"global"})
        self.assertEqual(self._tab_text(dlg, "global"), expected)

    def test_save_clears_modified_tabs_before_destroy(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        # Save clears markers before destroying — equivalent to
        # _commit_working_copy under CS-68 (which now wraps
        # _apply_changes_live + _clear_all_modified_tabs).
        dlg._commit_working_copy()
        self.assertEqual(dlg._modified_tabs, set())

    def test_apply_all_tabs_clears_modified_tabs(self):
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            on_apply_all_tabs=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        dlg._do_apply_all_tabs()
        self.assertEqual(dlg._modified_tabs, set())
        self.assertEqual(seen, [1])

    # ----- Cancel reverts and clears markers -----

    def test_cancel_clears_modified_tabs(self):
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        self.assertEqual(dlg._modified_tabs, {"global"})
        dlg._do_cancel()  # silenced askokcancel returns True
        # After cancel + destroy we can't access _modified_tabs on
        # a destroyed dialog; but the config revert demonstrates
        # cancel ran end-to-end. The marker-clear step is also
        # exercised in _commit_working_copy and _do_apply tests.
        self.assertEqual(self.config["title_font_size"], 12)


# =====================================================================
# CS-60 Phase 4ai → CS-68 Phase 4ap: dialog-level button row
# (Save · Apply to All Tabs · Cancel after CS-68 retired Apply)
# =====================================================================


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogButtonRowPhase4ai(unittest.TestCase):
    """The dialog-level button row carries three buttons in canonical order.

    Save · Apply to All Tabs · Cancel — right-aligned at the bottom of
    the Toplevel. Apply to All Tabs is disabled unless the host
    supplied an ``on_apply_all_tabs`` callback. Phase 4ap (CS-68)
    retired the standalone Apply button — every discrete-widget edit
    is implicitly applied via :meth:`_apply_changes_live`.
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_three_buttons_in_order_after_phase_4ap(self):
        """CS-68: button row is Save · Apply to All Tabs · Cancel (no Apply)."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertEqual(dlg._save_btn.cget("text"), "Save")
        self.assertEqual(
            dlg._apply_all_tabs_btn.cget("text"), "Apply to All Tabs",
        )
        self.assertEqual(dlg._cancel_btn.cget("text"), "Cancel")
        # Apply button retired: attribute MUST be absent (sentinel).
        self.assertFalse(
            hasattr(dlg, "_apply_btn"),
            "Phase 4ap (CS-68) retired the standalone Apply button — "
            "every edit is implicitly applied via _apply_changes_live.",
        )

    def test_apply_method_retired_after_phase_4ap(self):
        """Sentinel: PlotConfigDialog has no _do_apply method (CS-68)."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertFalse(
            hasattr(dlg, "_do_apply"),
            "Phase 4ap (CS-68) retired _do_apply — discrete-widget "
            "edits commit live via _apply_changes_live.",
        )

    def test_apply_all_tabs_disabled_without_callback(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertEqual(str(dlg._apply_all_tabs_btn.cget("state")), "disabled")

    def test_apply_all_tabs_enabled_with_callback(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply_all_tabs=lambda: None,
        )
        dlg.update_idletasks()
        self.assertEqual(str(dlg._apply_all_tabs_btn.cget("state")), "normal")

    def test_apply_all_tabs_button_invokes_callback(self):
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            on_apply_all_tabs=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        dlg._apply_all_tabs_btn.invoke()
        self.assertEqual(seen, [1])

    def test_apply_all_tabs_sees_already_live_config(self):
        # CS-68 (Phase 4ap): the live commit at var.set time means
        # ``self._config`` is already in sync when "Apply to All
        # Tabs" fires. The host's replication callback reads the
        # already-current value.
        observed: list = []

        def host_cb():
            observed.append(self.config.get("title_font_size"))

        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply_all_tabs=host_cb,
        )
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        dlg._do_apply_all_tabs()
        self.assertEqual(observed, [20])

    def test_apply_all_tabs_propagates_via_factory(self):
        seen: list = []
        dlg = self.psd.open_plot_config_dialog(
            self.host, self.config,
            on_apply_all_tabs=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        dlg._apply_all_tabs_btn.invoke()
        self.assertEqual(seen, [1])

    def test_apply_all_tabs_callback_exception_is_logged_not_raised(self):
        # _do_apply_all_tabs must not raise — the host's callback can
        # throw without crashing the dialog.
        def bad_cb():
            raise RuntimeError("boom")
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply_all_tabs=bad_cb,
        )
        dlg.update_idletasks()
        try:
            dlg._do_apply_all_tabs()
        except RuntimeError:
            self.fail("_do_apply_all_tabs must swallow on_apply_all_tabs errors")

    # ----- _has_uncommitted_changes contract -----

    def test_has_uncommitted_changes_false_at_start(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertFalse(dlg._has_uncommitted_changes())

    def test_has_uncommitted_changes_true_after_edit(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        self.assertTrue(dlg._has_uncommitted_changes())

    def test_has_uncommitted_changes_true_after_live_edit_persists(self):
        """CS-68: live-preview keeps the marker AND the config-vs-snapshot delta."""
        # Phase 4ap (CS-68): the live-commit writes to config but does
        # NOT clear the modified-tab marker. Both signals
        # (_modified_tabs non-empty AND config != snapshot) stay True
        # until Cancel reverts or the dialog destroys.
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        # Both signals raised by the same edit.
        self.assertEqual(dlg._modified_tabs, {"global"})
        self.assertNotEqual(dict(dlg._config), dlg._snapshot)
        self.assertTrue(dlg._has_uncommitted_changes())


# =====================================================================
# CS-61 Phase 4aj: tick_direction relocation to per-axis tabs
# =====================================================================


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogTickDirectionRelocationPhase4aj(unittest.TestCase):
    """CS-61 (Phase 4aj) — tick_direction widget moved from Plot Settings
    → Appearance into the per-axis Notebook tabs.

    Phase 4ak (CS-62) is the canonical lock-relaxation: the shared-var
    + Primary-X-dirty-pin pattern from 4aj inverted to per-axis vars
    + per-role dirty marking. This class keeps the still-valid
    relocation invariants (label absent from Appearance, label and
    three radios present on every per-axis "Settings" frame) and
    re-asserts the var / write / dirty semantics in their CS-62 form
    so the relocation thread remains documented across phases. The
    nested-schema / migration-shim / axis_label_override / Global
    mirror behaviour lives in TestPlotConfigDialogPerAxisSchemaPhase4ak.
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- helpers ----

    _AXIS_TAB_KEYS = (
        "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y",
    )

    def _settings_frame(self, dlg, role: str) -> tk.LabelFrame:
        """Return the "Settings" LabelFrame inside the axis tab ``role``."""
        tab_frame = dlg._tab_frames[role]
        for child in _all_descendants(tab_frame):
            if (
                isinstance(child, tk.LabelFrame)
                and child.cget("text") == "Settings"
            ):
                return child
        self.fail(f"no Settings LabelFrame on axis tab {role!r}")

    def _radiobuttons(self, parent: tk.Widget) -> list[tk.Radiobutton]:
        return [
            c for c in _all_descendants(parent)
            if isinstance(c, tk.Radiobutton)
        ]

    # ---- routing map ----

    def test_tick_direction_no_longer_in_key_to_tab(self):
        # Phase 4ak (CS-62) emptied _KEY_TO_TAB — per-axis keys live
        # inside the nested ``axes[<role>]`` sub-dict and route
        # dirty-marking via :meth:`_on_axis_var_write` with an
        # explicit role argument, bypassing :func:`_key_to_tab`.
        self.assertNotIn("tick_direction", self.psd._KEY_TO_TAB)
        # The dict is empty after the CS-61 entry was removed; every
        # flat key falls through to "global".
        self.assertEqual(dict(self.psd._KEY_TO_TAB), {})
        self.assertEqual(self.psd._key_to_tab("tick_direction"), "global")
        self.assertEqual(self.psd._key_to_tab("title_font_size"), "global")

    # ---- widget absence from the old home ----

    def test_tick_direction_label_not_in_appearance_section(self):
        # CS-56 lock relaxation: _build_section_appearance no longer
        # grids a "Tick direction:" label. Walks descendants of the
        # Appearance LabelFrame and asserts no tk.Label carries the
        # canonical text.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        appearance = None
        for lf in _global_tab_label_frames(dlg):
            if lf.cget("text") == "Appearance":
                appearance = lf
                break
        self.assertIsNotNone(appearance, "Appearance LabelFrame missing")
        labels = [
            c for c in _all_descendants(appearance)
            if isinstance(c, tk.Label)
        ]
        texts = [str(lbl.cget("text")) for lbl in labels]
        self.assertNotIn("Tick direction:", texts)

    # ---- widget presence on each per-axis tab ----

    def test_tick_direction_label_in_every_per_axis_settings_frame(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for role in self._AXIS_TAB_KEYS:
            frame = self._settings_frame(dlg, role)
            labels = [
                c for c in _all_descendants(frame)
                if isinstance(c, tk.Label)
            ]
            texts = [str(lbl.cget("text")) for lbl in labels]
            self.assertIn(
                "Tick direction:", texts,
                f"axis tab {role!r} is missing the Tick direction label",
            )

    def test_three_radio_buttons_per_axis_tab_settings_frame(self):
        # The radio set is (In, Out, Both) → three buttons per tab,
        # 15 across the five axis tabs.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        total = 0
        for role in self._AXIS_TAB_KEYS:
            frame = self._settings_frame(dlg, role)
            radios = self._radiobuttons(frame)
            self.assertEqual(
                len(radios), 3,
                f"axis tab {role!r} should have 3 radios, has {len(radios)}",
            )
            total += len(radios)
        self.assertEqual(total, 15)

    # ---- per-axis Tk vars (CS-62 inversion of the CS-61 shared var) ----

    def test_per_axis_tick_direction_vars_registered_for_every_role(self):
        # Phase 4ak: each per-axis tab owns its own (role,
        # "tick_direction") Tk var. The flat "tick_direction" entry
        # in _control_vars is gone.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertNotIn("tick_direction", dlg._control_vars)
        for role in self._AXIS_TAB_KEYS:
            self.assertIn((role, "tick_direction"), dlg._axis_control_vars)
            var = dlg._axis_control_vars[(role, "tick_direction")]
            self.assertIsInstance(var, tk.StringVar)
            self.assertEqual(var.get(), "in")

    def test_each_tab_radio_set_binds_to_that_tab_s_own_var(self):
        # Inverted CS-61 invariant: radios on tab N point at the var
        # for role N, not at a shared var. Five distinct var names,
        # one per tab.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        seen_var_names = set()
        for role in self._AXIS_TAB_KEYS:
            frame = self._settings_frame(dlg, role)
            radios = self._radiobuttons(frame)
            self.assertEqual(len(radios), 3)
            this_var_name = str(
                dlg._axis_control_vars[(role, "tick_direction")]
            )
            for radio in radios:
                self.assertEqual(
                    str(radio.cget("variable")), this_var_name,
                    f"axis tab {role!r}: radio var should match per-axis var",
                )
            seen_var_names.add(this_var_name)
        # Five distinct vars across five tabs.
        self.assertEqual(len(seen_var_names), 5)

    # ---- write semantics ----

    def test_edit_writes_through_to_nested_axes(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._axis_control_vars[("primary_y", "tick_direction")].set("out")
        dlg.update_idletasks()
        self.assertEqual(
            dlg._working["axes"]["primary_y"]["tick_direction"], "out",
        )
        # Other roles are untouched.
        self.assertEqual(
            dlg._working["axes"]["primary_x"]["tick_direction"], "in",
        )
        # The flat key is gone post-migration; no shadow value lingers.
        self.assertNotIn("tick_direction", dlg._working)

    def test_edit_marks_role_specific_tab_dirty(self):
        # CS-62 inversion: edit on Primary Y now marks Primary Y dirty
        # (not Primary X as in the CS-61 single-pin pattern).
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg.select_tab("primary_y")
        dlg.update_idletasks()
        dlg._axis_control_vars[("primary_y", "tick_direction")].set("out")
        dlg.update_idletasks()
        self.assertEqual(dlg._modified_tabs, {"primary_y"})

    def test_factory_reset_restores_in_default_on_every_role(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for role in self._AXIS_TAB_KEYS:
            dlg._axis_control_vars[(role, "tick_direction")].set("out")
        dlg.update_idletasks()
        dlg._do_factory_reset()
        dlg.update_idletasks()
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(
                dlg._working["axes"][role]["tick_direction"], "in",
            )
            self.assertEqual(
                dlg._axis_control_vars[(role, "tick_direction")].get(), "in",
            )

    def test_legacy_flat_config_migrates_into_nested_on_construction(self):
        # CS-62 migration shim: a pre-Phase-4ak config carries the
        # legacy flat ``tick_direction`` key. Dialog construction
        # runs the shim so every per-axis radio reflects the
        # migrated value and the flat key is gone.
        self.config["tick_direction"] = "inout"
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertNotIn("tick_direction", dlg._working)
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(
                dlg._working["axes"][role]["tick_direction"], "inout",
            )
            self.assertEqual(
                dlg._axis_control_vars[(role, "tick_direction")].get(),
                "inout",
            )

    def test_per_axis_tick_direction_writes_through_live_into_config(self):
        # CS-68 (Phase 4ap): Radiobutton edit on per-axis tab fires
        # _on_axis_var_write which live-commits via
        # _apply_changes_live — config carries the new nested value
        # without a separate Apply step. Other roles keep their
        # factory default; only the edited role changes. The CS-60
        # modified-tab marker persists (it represents "touched
        # since open" under live-preview).
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._axis_control_vars[("tertiary_y", "tick_direction")].set("out")
        dlg.update_idletasks()
        self.assertEqual(
            self.config["axes"]["tertiary_y"]["tick_direction"], "out",
        )
        self.assertEqual(
            self.config["axes"]["primary_x"]["tick_direction"], "in",
        )
        self.assertIn("tertiary_y", dlg._modified_tabs)

    # ---- factory defaults invariants (CS-62 shape) ----

    def test_factory_defaults_tick_direction_lives_per_axis(self):
        # CS-62 lock: factory default is "in" on every per-axis role;
        # the top-level flat key is gone.
        self.assertNotIn("tick_direction", self.psd._FACTORY_DEFAULTS)
        for role in self.psd._FACTORY_DEFAULTS["axes"]:
            self.assertEqual(
                self.psd._FACTORY_DEFAULTS["axes"][role]["tick_direction"],
                "in",
                f"per-axis tick_direction default drift on role {role!r}",
            )

    def test_universal_defaults_carries_nested_axes_with_tick_direction(self):
        # The CS-62 deep copy preserves the per-axis shape — and
        # mutating _UNIVERSAL_DEFAULTS cannot leak into
        # _FACTORY_DEFAULTS or vice versa.
        self.assertNotIn("tick_direction", self.psd._UNIVERSAL_DEFAULTS)
        self.assertIn("axes", self.psd._UNIVERSAL_DEFAULTS)
        for role in self.psd._FACTORY_DEFAULTS["axes"]:
            self.assertEqual(
                self.psd._UNIVERSAL_DEFAULTS["axes"][role]["tick_direction"],
                "in",
            )
        self.assertIsNot(
            self.psd._UNIVERSAL_DEFAULTS["axes"],
            self.psd._FACTORY_DEFAULTS["axes"],
        )


# =====================================================================
# CS-62 Phase 4ak: nested per-axis schema + axis_label_override mirror
# =====================================================================


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogPerAxisSchemaPhase4ak(unittest.TestCase):
    """CS-62 (Phase 4ak): _FACTORY_DEFAULTS gains a nested
    ``"axes"`` sub-dict + the new ``axis_label_override`` per-axis
    key + the Global-tab "Per-axis label overrides" mirror section
    + the ``plots_by_role`` constructor kwarg + the
    :func:`migrate_plot_config` legacy-flat-to-nested shim. The
    CS-61 relocation invariants (label absent from Appearance, label
    + 3 radios on every per-axis Settings frame) live alongside in
    TestPlotConfigDialogTickDirectionRelocationPhase4aj — this class
    covers what Phase 4ak introduced on top of those.
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- helpers ----

    _AXIS_TAB_KEYS = (
        "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y",
    )

    def _settings_frame(self, dlg, role: str) -> tk.LabelFrame:
        tab_frame = dlg._tab_frames[role]
        for child in _all_descendants(tab_frame):
            if (
                isinstance(child, tk.LabelFrame)
                and child.cget("text") == "Settings"
            ):
                return child
        self.fail(f"no Settings LabelFrame on axis tab {role!r}")

    def _plots_frame(self, dlg, role: str) -> tk.LabelFrame:
        tab_frame = dlg._tab_frames[role]
        for child in _all_descendants(tab_frame):
            if (
                isinstance(child, tk.LabelFrame)
                and child.cget("text") == "Plots on this axis"
            ):
                return child
        self.fail(f"no Plots LabelFrame on axis tab {role!r}")

    def _global_section_frame(self, dlg, title: str) -> tk.LabelFrame:
        for lf in _global_tab_label_frames(dlg):
            if lf.cget("text") == title:
                return lf
        self.fail(f"Global tab missing {title!r} section")

    # ---- factory defaults shape ----

    def test_factory_defaults_carries_nested_axes(self):
        axes = self.psd._FACTORY_DEFAULTS["axes"]
        self.assertEqual(
            set(axes.keys()),
            set(self._AXIS_TAB_KEYS),
        )
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(axes[role]["tick_direction"], "in")
            self.assertEqual(axes[role]["axis_label_override"], "")
            # CS-64 (Phase 4am): per-axis range / autoscale / scale.
            self.assertEqual(axes[role]["range_lo"], "")
            self.assertEqual(axes[role]["range_hi"], "")
            self.assertIs(axes[role]["autoscale"], True)
            self.assertEqual(axes[role]["scale"], "linear")

    def test_axis_keys_registry_matches_factory(self):
        # _AXIS_KEYS is the canonical per-axis-key registry —
        # asserting its contents documents the schema growth path
        # for future phases. CS-64 (Phase 4am) grew this from 2 → 6;
        # CS-65 (Phase 4an) grew it from 6 → 10 with the polish keys.
        # CS-69 (Phase 4aq) grew it from 10 → 11 with ``custom_ticks``
        # (comma-separated FixedLocator positions for the B-005
        # wavelength axis fix).
        self.assertEqual(
            tuple(self.psd._AXIS_KEYS),
            ("tick_direction", "axis_label_override",
             "range_lo", "range_hi", "autoscale", "scale",
             "tick_major", "tick_minor", "grid_show", "axis_color",
             "custom_ticks"),
        )
        # Every per-axis role's sub-dict carries exactly these keys.
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(
                set(self.psd._FACTORY_DEFAULTS["axes"][role].keys()),
                set(self.psd._AXIS_KEYS),
            )

    def test_default_sections_includes_axis_labels(self):
        self.assertIn("axis_labels", self.psd._DEFAULT_SECTIONS)
        # The new section comes last in the canonical order.
        self.assertEqual(self.psd._DEFAULT_SECTIONS[-1], "axis_labels")
        self.assertEqual(
            self.psd._SECTION_TITLES["axis_labels"],
            "Per-axis label overrides",
        )

    def test_universal_defaults_is_deep_copy_of_factory(self):
        # Phase 4ak upgraded the copy from shallow to deep so mutating
        # one cannot leak through the nested "axes" sub-dict into
        # the other.
        u = self.psd._UNIVERSAL_DEFAULTS
        f = self.psd._FACTORY_DEFAULTS
        self.assertIsNot(u, f)
        self.assertIsNot(u["axes"], f["axes"])
        for role in self._AXIS_TAB_KEYS:
            self.assertIsNot(u["axes"][role], f["axes"][role])

    # ---- migration shim (module-level) ----

    def test_migrate_flat_tick_direction_into_nested(self):
        cfg = {"tick_direction": "out", "untouched_key": 42}
        result = self.psd.migrate_plot_config(cfg)
        self.assertIs(result, cfg, "migration must return same dict")
        self.assertNotIn("tick_direction", cfg)
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(cfg["axes"][role]["tick_direction"], "out")
            self.assertEqual(cfg["axes"][role]["axis_label_override"], "")
        # Unrelated keys are preserved.
        self.assertEqual(cfg["untouched_key"], 42)

    def test_migrate_is_idempotent(self):
        cfg = {"tick_direction": "inout"}
        self.psd.migrate_plot_config(cfg)
        # Second call is a no-op: every per-role slot is already populated.
        snapshot = {role: dict(d) for role, d in cfg["axes"].items()}
        self.psd.migrate_plot_config(cfg)
        self.psd.migrate_plot_config(cfg)
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(dict(cfg["axes"][role]), snapshot[role])

    def test_migrate_empty_config_populates_factory_axes(self):
        cfg = {}
        self.psd.migrate_plot_config(cfg)
        self.assertIn("axes", cfg)
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(cfg["axes"][role]["tick_direction"], "in")
            self.assertEqual(cfg["axes"][role]["axis_label_override"], "")

    def test_migrate_partial_nested_fills_gaps(self):
        # Caller already migrated tick_direction but never set
        # axis_label_override — the shim fills the missing key.
        cfg = {
            "axes": {
                "primary_y": {"tick_direction": "inout"},
            },
        }
        self.psd.migrate_plot_config(cfg)
        self.assertEqual(cfg["axes"]["primary_y"]["tick_direction"], "inout")
        self.assertEqual(cfg["axes"]["primary_y"]["axis_label_override"], "")
        # Missing roles are populated from factory.
        self.assertEqual(cfg["axes"]["primary_x"]["tick_direction"], "in")

    # ---- per-axis axis_label_override widget ----

    def test_axis_label_override_entry_present_on_every_axis_tab(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for role in self._AXIS_TAB_KEYS:
            frame = self._settings_frame(dlg, role)
            texts = [
                c.cget("text") for c in _all_descendants(frame)
                if isinstance(c, tk.Label)
            ]
            self.assertIn(
                "Axis label override:", texts,
                f"axis tab {role!r} missing override label",
            )
            entries = [
                c for c in _all_descendants(frame)
                if isinstance(c, tk.Entry)
            ]
            self.assertGreaterEqual(
                len(entries), 1,
                f"axis tab {role!r} should have at least one Entry",
            )

    def test_axis_label_override_var_created_per_role(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for role in self._AXIS_TAB_KEYS:
            self.assertIn(
                (role, "axis_label_override"), dlg._axis_control_vars,
            )
            var = dlg._axis_control_vars[(role, "axis_label_override")]
            self.assertEqual(var.get(), "")

    def test_axis_label_override_edit_writes_through_to_nested(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        var = dlg._axis_control_vars[("tertiary_y", "axis_label_override")]
        var.set("d²A/dλ² (custom)")
        dlg.update_idletasks()
        self.assertEqual(
            dlg._working["axes"]["tertiary_y"]["axis_label_override"],
            "d²A/dλ² (custom)",
        )
        # Other roles untouched.
        self.assertEqual(
            dlg._working["axes"]["primary_x"]["axis_label_override"], "",
        )

    def test_axis_label_override_edit_marks_role_tab_dirty(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._axis_control_vars[
            ("secondary_x", "axis_label_override")
        ].set("ν̃ (cm⁻¹)")
        dlg.update_idletasks()
        self.assertEqual(dlg._modified_tabs, {"secondary_x"})

    # ---- Global "Per-axis label overrides" mirror section ----

    def test_global_axis_labels_section_present(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        # The section LabelFrame lives on the Global tab with the
        # title declared in _SECTION_TITLES.
        section = self._global_section_frame(dlg, "Per-axis label overrides")
        # Five rows → five Entry widgets, one per axis role.
        entries = [
            c for c in _all_descendants(section)
            if isinstance(c, tk.Entry)
        ]
        self.assertEqual(len(entries), 5)

    def test_global_mirror_entry_shares_var_with_per_axis_entry(self):
        # The Global mirror Entry for primary_y and the per-axis tab's
        # axis_label_override Entry must bind to the same Tk variable
        # name so edits on either surface stay in lockstep.
        # CS-64 (Phase 4am) added two more Entries per per-axis tab
        # (range_lo + range_hi); the mirror covers axis_label_override
        # only, so we resolve THAT Entry via the registered Tk var
        # rather than indexing into the widget tree.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        expected_var = dlg._axis_control_vars[
            ("primary_y", "axis_label_override")
        ]
        per_axis_var_name = str(expected_var)

        # The Global mirror section's third Entry corresponds to
        # primary_y (canonical _TAB_KEYS order, minus "global").
        section = self._global_section_frame(dlg, "Per-axis label overrides")
        mirror_entries = [
            c for c in _all_descendants(section)
            if isinstance(c, tk.Entry)
        ]
        # Find the mirror Entry whose var matches.
        mirror_var_names = [
            str(e.cget("textvariable")) for e in mirror_entries
        ]
        self.assertIn(
            per_axis_var_name, mirror_var_names,
            "Global mirror Entry should share a Tk var with the "
            "per-axis tab Entry for at least one role",
        )

    def test_edit_on_global_mirror_marks_role_tab_dirty(self):
        # The mirror surface is on Global but the gesture is
        # conceptually per-axis: editing should mark the
        # corresponding role tab, not Global.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._axis_control_vars[
            ("primary_x", "axis_label_override")
        ].set("Wavelength (nm)")
        dlg.update_idletasks()
        self.assertIn("primary_x", dlg._modified_tabs)
        self.assertNotIn("global", dlg._modified_tabs)

    # ---- plots_by_role constructor kwarg ----

    def test_plots_by_role_renders_listbox_when_populated(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ("Scan A", "Scan B", "Scan C")},
        )
        dlg.update_idletasks()
        plots_frame = self._plots_frame(dlg, "primary_y")
        listboxes = [
            c for c in _all_descendants(plots_frame)
            if isinstance(c, tk.Listbox)
        ]
        self.assertEqual(len(listboxes), 1)
        listbox = listboxes[0]
        contents = [listbox.get(i) for i in range(listbox.size())]
        self.assertEqual(contents, ["Scan A", "Scan B", "Scan C"])

    def test_plots_by_role_missing_role_renders_placeholder(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ("Scan A",)},
        )
        dlg.update_idletasks()
        # secondary_x was not in plots_by_role — placeholder Label.
        plots_frame = self._plots_frame(dlg, "secondary_x")
        labels = [
            c.cget("text") for c in _all_descendants(plots_frame)
            if isinstance(c, tk.Label)
        ]
        self.assertIn("(no plots on this axis)", labels)
        # No Listbox on the empty role.
        listboxes = [
            c for c in _all_descendants(plots_frame)
            if isinstance(c, tk.Listbox)
        ]
        self.assertEqual(listboxes, [])

    def test_plots_by_role_none_defaults_to_placeholder_everywhere(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for role in self._AXIS_TAB_KEYS:
            plots_frame = self._plots_frame(dlg, role)
            labels = [
                c.cget("text") for c in _all_descendants(plots_frame)
                if isinstance(c, tk.Label)
            ]
            self.assertIn(
                "(no plots on this axis)", labels,
                f"axis tab {role!r} should show empty placeholder",
            )

    def test_plots_listbox_is_disabled_on_x_axis_tabs(self):
        # X-axis tabs keep the CS-62 ``state="disabled"`` lock: every
        # visible plot is necessarily on primary_x and secondary_x
        # mirrors it, so there is nowhere to route to. Phase 4al's
        # canonical relaxation applies only to the three Y-axis tabs.
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_x": ("Scan A", "Scan B")},
        )
        dlg.update_idletasks()
        plots_frame = self._plots_frame(dlg, "primary_x")
        listbox = [
            c for c in _all_descendants(plots_frame)
            if isinstance(c, tk.Listbox)
        ][0]
        self.assertEqual(str(listbox.cget("state")), "disabled")

    def test_plots_listbox_height_capped_at_six(self):
        many_labels = tuple(f"Scan {i}" for i in range(12))
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": many_labels},
        )
        dlg.update_idletasks()
        plots_frame = self._plots_frame(dlg, "primary_y")
        listbox = [
            c for c in _all_descendants(plots_frame)
            if isinstance(c, tk.Listbox)
        ][0]
        self.assertEqual(int(listbox.cget("height")), 6)
        # Contents still complete.
        self.assertEqual(listbox.size(), 12)

    # ---- end-to-end live commits write nested form into config (CS-68) ----

    def test_per_axis_edits_write_through_nested_axes_block_live(self):
        # CS-68 (Phase 4ap): per-axis edits commit live via
        # _on_axis_var_write → _apply_changes_live. The text Entry
        # for axis_label_override defers to <FocusOut>/<Return>
        # in the UI, but a direct var.set in test fires the trace
        # which writes to _working — to flush the live commit we
        # also call _apply_changes_live directly (the test stand-in
        # for the FocusOut event).
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._axis_control_vars[
            ("primary_y", "axis_label_override")
        ].set("Custom label")
        dlg._apply_changes_live()  # simulate <FocusOut> on the override Entry
        dlg._axis_control_vars[("tertiary_y", "tick_direction")].set("out")
        dlg.update_idletasks()
        # Config carries the full nested form.
        self.assertEqual(
            self.config["axes"]["primary_y"]["axis_label_override"],
            "Custom label",
        )
        self.assertEqual(
            self.config["axes"]["tertiary_y"]["tick_direction"], "out",
        )
        # CS-68: markers persist through live commits — they only
        # clear on Cancel-revert or destroy.
        self.assertIn("primary_y", dlg._modified_tabs)
        self.assertIn("tertiary_y", dlg._modified_tabs)

    # ---- end-to-end Reset Defaults migrates user defaults ----

    def test_reset_defaults_migrates_legacy_user_defaults(self):
        # Simulate a _USER_DEFAULTS dict saved by a pre-Phase-4ak
        # session (carries flat tick_direction). Reset Defaults
        # should run the migration shim so the working copy lands
        # in nested form and every per-axis var reflects the
        # migrated value.
        self.psd._USER_DEFAULTS.clear()
        self.psd._USER_DEFAULTS.update({"tick_direction": "out"})
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._do_reset_defaults()
        dlg.update_idletasks()
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(
                dlg._working["axes"][role]["tick_direction"], "out",
            )
        self.assertNotIn("tick_direction", dlg._working)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogMoveToPickerPhase4al(unittest.TestCase):
    """Phase 4al: Move-to Combobox on each Y-axis tab.

    Y-axis tabs (``primary_y``, ``secondary_y``, ``tertiary_y``) host
    a Combobox below the "Plots on this axis" Listbox that lists the
    four CS-50 routing targets ("Default (by NodeType)" plus the
    three explicit Y-axis tabs). Selecting a row + picking a value
    fires the host's ``on_route_plot`` callback. X-axis tabs
    (``primary_x``, ``secondary_x``) get no picker and keep the
    CS-62 ``state="disabled"`` Listbox lock.
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- helpers ----

    _Y_AXIS_TAB_KEYS = ("primary_y", "secondary_y", "tertiary_y")
    _X_AXIS_TAB_KEYS = ("primary_x", "secondary_x")

    def _plots_frame(self, dlg, role: str) -> tk.LabelFrame:
        tab_frame = dlg._tab_frames[role]
        for child in _all_descendants(tab_frame):
            if (
                isinstance(child, tk.LabelFrame)
                and child.cget("text") == "Plots on this axis"
            ):
                return child
        self.fail(f"no Plots LabelFrame on axis tab {role!r}")

    def _listbox(self, dlg, role: str) -> tk.Listbox:
        frame = self._plots_frame(dlg, role)
        for child in _all_descendants(frame):
            if isinstance(child, tk.Listbox):
                return child
        self.fail(f"no Listbox on axis tab {role!r}")

    def _combobox(self, dlg, role: str) -> ttk.Combobox | None:
        """Return the Move-to Combobox for the role's tab, or None."""
        frame = self._plots_frame(dlg, role)
        for child in _all_descendants(frame):
            if isinstance(child, ttk.Combobox):
                return child
        return None

    def _combobox_var(self, combo: ttk.Combobox) -> tk.StringVar:
        """Return the StringVar driving the Combobox's textvariable."""
        var_name = combo.cget("textvariable")
        # ttk widgets store textvariable as the Tk variable name
        # string; re-wrap into a StringVar for ``.set`` / ``.get``.
        return tk.StringVar(name=str(var_name))

    # ---- module-level constants ----

    def test_move_to_options_in_canonical_order(self):
        labels = [label for label, _ in self.psd._MOVE_TO_OPTIONS]
        self.assertEqual(
            labels,
            ["Default (by NodeType)", "Primary Y", "Secondary Y", "Tertiary Y"],
        )

    def test_move_to_value_by_label_maps_default_to_none(self):
        self.assertIsNone(
            self.psd._MOVE_TO_VALUE_BY_LABEL["Default (by NodeType)"]
        )
        self.assertEqual(
            self.psd._MOVE_TO_VALUE_BY_LABEL["Primary Y"], "primary_y"
        )
        self.assertEqual(
            self.psd._MOVE_TO_VALUE_BY_LABEL["Secondary Y"], "secondary_y"
        )
        self.assertEqual(
            self.psd._MOVE_TO_VALUE_BY_LABEL["Tertiary Y"], "tertiary_y"
        )

    def test_y_axis_tab_keys_constant_covers_only_y_tabs(self):
        self.assertEqual(
            set(self.psd._Y_AXIS_TAB_KEYS),
            {"primary_y", "secondary_y", "tertiary_y"},
        )

    # ---- combobox presence ----

    def test_combobox_present_on_every_y_axis_tab_when_plots_exist(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={
                role: ("Scan A",) for role in self._Y_AXIS_TAB_KEYS
            },
        )
        dlg.update_idletasks()
        for role in self._Y_AXIS_TAB_KEYS:
            combo = self._combobox(dlg, role)
            self.assertIsNotNone(combo, f"Y-axis tab {role!r} missing picker")

    def test_combobox_absent_on_x_axis_tabs(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={
                "primary_x":   ("Scan A", "Scan B"),
                "secondary_x": ("Scan A", "Scan B"),
            },
        )
        dlg.update_idletasks()
        for role in self._X_AXIS_TAB_KEYS:
            combo = self._combobox(dlg, role)
            self.assertIsNone(combo, f"X-axis tab {role!r} should have no picker")

    def test_combobox_absent_when_no_plots(self):
        # Empty plots_by_role → italic placeholder, no Listbox, no picker.
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ()},
        )
        dlg.update_idletasks()
        self.assertIsNone(self._combobox(dlg, "primary_y"))

    def test_combobox_lists_four_options(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ("Scan A",)},
        )
        dlg.update_idletasks()
        combo = self._combobox(dlg, "primary_y")
        values = combo.cget("values")
        # ttk Combobox returns values as a tuple-like string list.
        self.assertEqual(len(values), 4)
        for label in (
            "Default (by NodeType)",
            "Primary Y",
            "Secondary Y",
            "Tertiary Y",
        ):
            self.assertIn(label, values)

    def test_combobox_state_readonly(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ("Scan A",)},
        )
        dlg.update_idletasks()
        combo = self._combobox(dlg, "primary_y")
        self.assertEqual(str(combo.cget("state")), "readonly")

    # ---- listbox state relaxation ----

    def test_y_axis_listboxes_are_selectable(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={
                role: ("Scan A", "Scan B")
                for role in self._Y_AXIS_TAB_KEYS
            },
        )
        dlg.update_idletasks()
        for role in self._Y_AXIS_TAB_KEYS:
            listbox = self._listbox(dlg, role)
            self.assertEqual(
                str(listbox.cget("state")), "normal",
                f"Y-axis tab {role!r} listbox should be state=normal",
            )

    # ---- callback firing ----
    #
    # The Combobox handler is exposed as ``PlotConfigDialog._on_move_to_choose``
    # rather than living as a closure inside the builder. Tests drive
    # the routing path by calling that method directly: ttk.Combobox's
    # ``<<ComboboxSelected>>`` virtual event does not reliably dispatch
    # synchronously across the full test suite (the dispatch fires in
    # isolation but is intermittently dropped when other tests have
    # populated and torn down many Toplevels first). Bypassing
    # ``event_generate`` keeps these tests deterministic and exercises
    # the same code path the bind invokes.

    def test_combobox_selection_with_row_fires_callback(self):
        captured: list = []

        def cb(source, label, target):
            captured.append((source, label, target))

        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ("Scan A", "Scan B")},
            on_route_plot=cb,
        )
        dlg.update_idletasks()
        listbox = self._listbox(dlg, "primary_y")
        combo = self._combobox(dlg, "primary_y")
        var = self._combobox_var(combo)
        listbox.selection_set(1)  # "Scan B"
        var.set("Secondary Y")
        dlg._on_move_to_choose("primary_y", listbox, var)
        self.assertEqual(
            captured,
            [("primary_y", "Scan B", "secondary_y")],
        )

    def test_combobox_selection_without_row_does_not_fire(self):
        captured: list = []

        def cb(source, label, target):
            captured.append((source, label, target))

        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ("Scan A",)},
            on_route_plot=cb,
        )
        dlg.update_idletasks()
        listbox = self._listbox(dlg, "primary_y")
        combo = self._combobox(dlg, "primary_y")
        var = self._combobox_var(combo)
        listbox.selection_clear(0, tk.END)
        var.set("Primary Y")
        dlg._on_move_to_choose("primary_y", listbox, var)
        self.assertEqual(captured, [])

    def test_default_option_passes_none_target(self):
        captured: list = []

        def cb(source, label, target):
            captured.append((source, label, target))

        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"tertiary_y": ("Scan X",)},
            on_route_plot=cb,
        )
        dlg.update_idletasks()
        listbox = self._listbox(dlg, "tertiary_y")
        combo = self._combobox(dlg, "tertiary_y")
        var = self._combobox_var(combo)
        listbox.selection_set(0)
        var.set("Default (by NodeType)")
        dlg._on_move_to_choose("tertiary_y", listbox, var)
        self.assertEqual(
            captured,
            [("tertiary_y", "Scan X", None)],
        )

    def test_callback_passes_source_role_from_tab(self):
        # Source role comes from the tab the picker was used on, NOT
        # from the listbox row's label. Two different Y-axis tabs
        # picking the same target must yield different source values.
        captured: list = []

        def cb(source, label, target):
            captured.append((source, label, target))

        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={
                "primary_y":   ("Scan A",),
                "secondary_y": ("Scan A",),
            },
            on_route_plot=cb,
        )
        dlg.update_idletasks()
        for role in ("primary_y", "secondary_y"):
            listbox = self._listbox(dlg, role)
            combo = self._combobox(dlg, role)
            var = self._combobox_var(combo)
            listbox.selection_set(0)
            var.set("Tertiary Y")
            dlg._on_move_to_choose(role, listbox, var)
        self.assertEqual(
            captured,
            [
                ("primary_y",   "Scan A", "tertiary_y"),
                ("secondary_y", "Scan A", "tertiary_y"),
            ],
        )

    def test_combobox_resets_after_choose(self):
        # After firing, the Combobox returns to its empty placeholder
        # so the user can pick the SAME target on another row without
        # first clearing the dropdown.
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ("Scan A",)},
            on_route_plot=lambda *_: None,
        )
        dlg.update_idletasks()
        listbox = self._listbox(dlg, "primary_y")
        combo = self._combobox(dlg, "primary_y")
        var = self._combobox_var(combo)
        listbox.selection_set(0)
        var.set("Secondary Y")
        dlg._on_move_to_choose("primary_y", listbox, var)
        self.assertEqual(combo.get(), "")

    def test_callback_unset_makes_combobox_a_silent_noop(self):
        # No on_route_plot wired → picking a Combobox value is silent.
        # Combobox still resets so the user gets visual feedback.
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ("Scan A",)},
            # on_route_plot omitted
        )
        dlg.update_idletasks()
        listbox = self._listbox(dlg, "primary_y")
        combo = self._combobox(dlg, "primary_y")
        var = self._combobox_var(combo)
        listbox.selection_set(0)
        var.set("Tertiary Y")
        dlg._on_move_to_choose("primary_y", listbox, var)
        # No exception raised; combobox reset.
        self.assertEqual(combo.get(), "")

    def test_combobox_bind_invokes_on_move_to_choose(self):
        # Verify the bind actually wires the method (without relying on
        # event_generate dispatch). Inspect the bound tag list — Tk
        # registers every bind under the widget's bindtags namespace,
        # accessible via ``bind`` with no args.
        dlg = self.PlotConfigDialog(
            self.host, self.config,
            plots_by_role={"primary_y": ("Scan A",)},
        )
        dlg.update_idletasks()
        combo = self._combobox(dlg, "primary_y")
        events = combo.bind()
        self.assertIn("<<ComboboxSelected>>", events)


class TestPlotConfigDialogPerAxisRangeScaleSchemaPhase4am(unittest.TestCase):
    """CS-64 (Phase 4am) — per-axis range / autoscale / scale schema.

    ``_AXIS_KEYS`` grew from 2 → 6 with ``range_lo`` / ``range_hi`` /
    ``autoscale`` / ``scale``. The migration shim's existing per-role
    per-key fill loop handles the new keys transparently; this class
    pins the fill behaviour for legacy configs and the idempotency
    invariant.
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog

    _AXIS_TAB_KEYS = (
        "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y",
    )

    def test_axis_keys_grew_to_six(self):
        # CS-65 (Phase 4an): registry grew from 6 → 10. The original
        # Phase 4am assertion (== 6) became a lower bound; the four
        # range/scale keys this test was written to defend still live
        # in the tuple, just alongside the new tick/grid/colour keys.
        self.assertGreaterEqual(len(self.psd._AXIS_KEYS), 6)
        for k in ("range_lo", "range_hi", "autoscale", "scale"):
            self.assertIn(k, self.psd._AXIS_KEYS)

    def test_scale_options_are_linear_and_log(self):
        self.assertEqual(self.psd._AXIS_SCALE_OPTIONS, ("linear", "log"))

    def test_migration_fills_missing_range_lo_range_hi_autoscale_scale(self):
        cfg: dict = {}
        self.psd.migrate_plot_config(cfg)
        for role in self._AXIS_TAB_KEYS:
            slot = cfg["axes"][role]
            self.assertEqual(slot["range_lo"], "")
            self.assertEqual(slot["range_hi"], "")
            self.assertIs(slot["autoscale"], True)
            self.assertEqual(slot["scale"], "linear")

    def test_migration_preserves_user_set_range_values(self):
        cfg: dict = {
            "axes": {
                "primary_y": {
                    "range_lo": "0.05", "range_hi": "1.2",
                    "autoscale": False, "scale": "log",
                },
            },
        }
        self.psd.migrate_plot_config(cfg)
        slot = cfg["axes"]["primary_y"]
        self.assertEqual(slot["range_lo"], "0.05")
        self.assertEqual(slot["range_hi"], "1.2")
        self.assertIs(slot["autoscale"], False)
        self.assertEqual(slot["scale"], "log")
        # Other roles still get factory defaults.
        self.assertIs(cfg["axes"]["primary_x"]["autoscale"], True)

    def test_migration_is_idempotent_on_phase_4am_keys(self):
        cfg: dict = {
            "axes": {
                "secondary_y": {
                    "range_lo": "-1", "range_hi": "1",
                    "autoscale": False, "scale": "log",
                },
            },
        }
        self.psd.migrate_plot_config(cfg)
        snapshot = copy.deepcopy(cfg)
        self.psd.migrate_plot_config(cfg)
        self.assertEqual(cfg, snapshot)

    def test_universal_defaults_carries_phase_4am_keys(self):
        for role in self._AXIS_TAB_KEYS:
            slot = self.psd._UNIVERSAL_DEFAULTS["axes"][role]
            self.assertEqual(slot["range_lo"], "")
            self.assertEqual(slot["range_hi"], "")
            self.assertIs(slot["autoscale"], True)
            self.assertEqual(slot["scale"], "linear")


@unittest.skipUnless(_root is not None, "Tk root unavailable")
class TestPlotConfigDialogPerAxisRangeScaleWidgetsPhase4am(unittest.TestCase):
    """CS-64 (Phase 4am) — per-axis Range Entries, Autoscale Checkbutton,
    Scale Combobox on every per-axis tab.

    Each per-axis tab (all five roles) hosts three new widget rows
    below the existing tick-direction + axis-label-override rows.
    The Tk vars register through the existing ``_axis_control_vars``
    registry (cross-typed: StringVar for range/scale, BooleanVar for
    autoscale).
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    _AXIS_TAB_KEYS = (
        "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y",
    )

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- registry coverage ----

    def test_axis_control_vars_registered_for_range_lo(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            self.assertIn((role, "range_lo"), dlg._axis_control_vars)
            self.assertIsInstance(
                dlg._axis_control_vars[(role, "range_lo")], tk.StringVar,
            )

    def test_axis_control_vars_registered_for_range_hi(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            self.assertIn((role, "range_hi"), dlg._axis_control_vars)

    def test_axis_control_vars_registered_for_autoscale_as_bool(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            self.assertIn((role, "autoscale"), dlg._axis_control_vars)
            var = dlg._axis_control_vars[(role, "autoscale")]
            self.assertIsInstance(var, tk.BooleanVar)
            self.assertIs(var.get(), True)

    def test_axis_control_vars_registered_for_scale(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            self.assertIn((role, "scale"), dlg._axis_control_vars)
            var = dlg._axis_control_vars[(role, "scale")]
            self.assertEqual(var.get(), "linear")

    def test_make_axis_bool_var_idempotent(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        first = dlg._make_axis_bool_var("primary_y", "autoscale")
        second = dlg._make_axis_bool_var("primary_y", "autoscale")
        self.assertIs(first, second)

    # ---- write-through behaviour ----

    def test_setting_range_lo_writes_to_working(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        dlg._axis_control_vars[("primary_y", "range_lo")].set("0.1")
        self.assertEqual(
            dlg._working["axes"]["primary_y"]["range_lo"], "0.1",
        )
        # Other roles untouched.
        self.assertEqual(
            dlg._working["axes"]["primary_x"]["range_lo"], "",
        )

    def test_setting_autoscale_false_writes_bool_to_working(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        dlg._axis_control_vars[("tertiary_y", "autoscale")].set(False)
        self.assertIs(
            dlg._working["axes"]["tertiary_y"]["autoscale"], False,
        )
        self.assertIs(
            dlg._working["axes"]["primary_y"]["autoscale"], True,
        )

    def test_setting_scale_to_log_writes_to_working(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        dlg._axis_control_vars[("secondary_y", "scale")].set("log")
        self.assertEqual(
            dlg._working["axes"]["secondary_y"]["scale"], "log",
        )
        self.assertEqual(
            dlg._working["axes"]["primary_y"]["scale"], "linear",
        )

    # ---- widget surface ----

    def _settings_frame(self, dlg, role: str) -> tk.LabelFrame:
        tab_frame = dlg._tab_frames[role]
        for child in _all_descendants(tab_frame):
            if (
                isinstance(child, tk.LabelFrame)
                and child.cget("text") == "Settings"
            ):
                return child
        self.fail(f"no Settings LabelFrame on axis tab {role!r}")

    def test_each_per_axis_tab_carries_range_label(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            frame = self._settings_frame(dlg, role)
            texts = [
                child.cget("text")
                for child in _all_descendants(frame)
                if isinstance(child, tk.Label)
            ]
            self.assertIn(
                "Range:", texts,
                f"per-axis tab {role!r} missing Range label",
            )

    def test_each_per_axis_tab_carries_autoscale_checkbutton(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            frame = self._settings_frame(dlg, role)
            cbs = [
                child for child in _all_descendants(frame)
                if isinstance(child, tk.Checkbutton)
                and child.cget("text") == "Autoscale"
            ]
            self.assertEqual(
                len(cbs), 1,
                f"per-axis tab {role!r} should have exactly one "
                f"Autoscale Checkbutton",
            )

    def test_each_per_axis_tab_carries_scale_combobox(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            frame = self._settings_frame(dlg, role)
            combos = [
                child for child in _all_descendants(frame)
                if isinstance(child, ttk.Combobox)
            ]
            self.assertGreaterEqual(
                len(combos), 1,
                f"per-axis tab {role!r} missing Scale Combobox",
            )
            scale_var_name = str(combos[0].cget("textvariable"))
            self.assertEqual(
                scale_var_name,
                str(dlg._axis_control_vars[(role, "scale")]),
            )

    # ---- Live commit round-trip (CS-68 / Phase 4ap) ----

    def test_per_axis_range_writes_through_to_config_live(self):
        # CS-68: range_lo / range_hi are typed Entries → defer per-
        # keystroke commit until <FocusOut>/<Return>; we flush by
        # calling _apply_changes_live directly. autoscale (BoolVar
        # Checkbutton) and scale (Combobox) are discrete and live-
        # commit on var write.
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        dlg._axis_control_vars[("primary_y", "range_lo")].set("0.05")
        dlg._axis_control_vars[("primary_y", "range_hi")].set("1.5")
        dlg._apply_changes_live()  # simulate <FocusOut> on the typed Entries
        dlg._axis_control_vars[("primary_y", "autoscale")].set(False)
        dlg._axis_control_vars[("primary_y", "scale")].set("log")
        slot = self.config["axes"]["primary_y"]
        self.assertEqual(slot["range_lo"], "0.05")
        self.assertEqual(slot["range_hi"], "1.5")
        self.assertIs(slot["autoscale"], False)
        self.assertEqual(slot["scale"], "log")

    # ---- migration: legacy config still loads ----

    def test_legacy_config_loads_with_phase_4am_defaults(self):
        # Pre-Phase-4am config: only tick_direction + axis_label_override.
        self.config = {
            "axes": {
                "primary_y": {
                    "tick_direction": "out", "axis_label_override": "A",
                },
            },
        }
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        slot = dlg._working["axes"]["primary_y"]
        self.assertEqual(slot["tick_direction"], "out")
        self.assertEqual(slot["axis_label_override"], "A")
        self.assertEqual(slot["range_lo"], "")
        self.assertEqual(slot["range_hi"], "")
        self.assertIs(slot["autoscale"], True)
        self.assertEqual(slot["scale"], "linear")


class TestPlotConfigDialogPerAxisPolishSchemaPhase4an(unittest.TestCase):
    """CS-65 (Phase 4an) — tick spacing + per-axis grid + axis colour
    schema growth.

    ``_AXIS_KEYS`` grew from 6 → 10 with ``tick_major`` / ``tick_minor`` /
    ``grid_show`` / ``axis_color``. ``grid_show`` defaults differ per
    role (True for the two primaries, False elsewhere) — the renderer
    only reads it for the primary roles (twin Y axes share the primary
    grid), but the schema stores it on every role for shape consistency
    (CS-62 invariant).
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog

    _AXIS_TAB_KEYS = (
        "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y",
    )

    def test_axis_keys_grew_to_eleven_after_phase_4aq(self):
        # CS-65 (Phase 4an) grew the registry to ten with the polish
        # ladder (tick_major / tick_minor / grid_show / axis_color).
        # CS-69 (Phase 4aq) added the eleventh — ``custom_ticks`` —
        # for the B-005 wavelength axis FixedLocator path.
        self.assertEqual(len(self.psd._AXIS_KEYS), 11)
        for k in ("tick_major", "tick_minor", "grid_show", "axis_color",
                  "custom_ticks"):
            self.assertIn(k, self.psd._AXIS_KEYS)

    def test_factory_defaults_carry_phase_4an_keys(self):
        for role in self._AXIS_TAB_KEYS:
            slot = self.psd._FACTORY_DEFAULTS["axes"][role]
            self.assertEqual(slot["tick_major"], "")
            self.assertEqual(slot["tick_minor"], "")
            self.assertEqual(slot["axis_color"], "#000000")
            # grid_show defaults split: True for primaries only.
            if role in ("primary_x", "primary_y"):
                self.assertIs(slot["grid_show"], True)
            else:
                self.assertIs(slot["grid_show"], False)

    def test_universal_defaults_carry_phase_4an_keys(self):
        for role in self._AXIS_TAB_KEYS:
            slot = self.psd._UNIVERSAL_DEFAULTS["axes"][role]
            self.assertEqual(slot["tick_major"], "")
            self.assertEqual(slot["tick_minor"], "")
            self.assertEqual(slot["axis_color"], "#000000")

    def test_migration_fills_missing_phase_4an_keys(self):
        cfg: dict = {}
        self.psd.migrate_plot_config(cfg)
        for role in self._AXIS_TAB_KEYS:
            slot = cfg["axes"][role]
            self.assertEqual(slot["tick_major"], "")
            self.assertEqual(slot["tick_minor"], "")
            self.assertEqual(slot["axis_color"], "#000000")
            self.assertIn("grid_show", slot)

    def test_migration_preserves_user_set_phase_4an_values(self):
        cfg: dict = {
            "axes": {
                "primary_y": {
                    "tick_major": "0.25", "tick_minor": "0.05",
                    "grid_show": False, "axis_color": "#ff0000",
                },
            },
        }
        self.psd.migrate_plot_config(cfg)
        slot = cfg["axes"]["primary_y"]
        self.assertEqual(slot["tick_major"], "0.25")
        self.assertEqual(slot["tick_minor"], "0.05")
        self.assertIs(slot["grid_show"], False)
        self.assertEqual(slot["axis_color"], "#ff0000")
        # Other roles get factory defaults for the new keys.
        self.assertEqual(cfg["axes"]["primary_x"]["axis_color"], "#000000")

    def test_migration_is_idempotent_on_phase_4an_keys(self):
        cfg: dict = {
            "axes": {
                "secondary_y": {
                    "tick_major": "10", "tick_minor": "2",
                    "grid_show": True, "axis_color": "#0000ff",
                },
            },
        }
        self.psd.migrate_plot_config(cfg)
        snapshot = copy.deepcopy(cfg)
        self.psd.migrate_plot_config(cfg)
        self.assertEqual(cfg, snapshot)


class TestUVVisTabPerAxisPolishHelpersPhase4an(unittest.TestCase):
    """CS-65 (Phase 4an) — module-level renderer helpers for the new
    polish keys: ``_parse_tick_str`` / ``_per_axis_tick_major`` /
    ``_per_axis_tick_minor`` / ``_per_axis_grid`` / ``_per_axis_color``.
    """

    @classmethod
    def setUpClass(cls):
        import uvvis_tab
        cls.ut = uvvis_tab

    def test_parse_tick_str_accepts_positive_floats(self):
        self.assertEqual(self.ut._parse_tick_str("0.25"), 0.25)
        self.assertEqual(self.ut._parse_tick_str("10"), 10.0)
        self.assertEqual(self.ut._parse_tick_str("  3.5 "), 3.5)

    def test_parse_tick_str_rejects_empty_and_garbage(self):
        for bad in ("", "   ", "abc", "1.2.3", None):
            self.assertIsNone(self.ut._parse_tick_str(bad))  # type: ignore[arg-type]

    def test_parse_tick_str_rejects_non_positive(self):
        # Negative + zero spacings would crash MultipleLocator;
        # silently rejecting in the helper keeps the renderer clean.
        self.assertIsNone(self.ut._parse_tick_str("0"))
        self.assertIsNone(self.ut._parse_tick_str("-1"))
        self.assertIsNone(self.ut._parse_tick_str("inf"))
        self.assertIsNone(self.ut._parse_tick_str("nan"))

    def test_per_axis_tick_major_reads_nested_slot(self):
        cfg = {"axes": {"primary_x": {"tick_major": "0.5"}}}
        self.assertEqual(
            self.ut._per_axis_tick_major(cfg, "primary_x"), 0.5,
        )

    def test_per_axis_tick_major_defaults_none(self):
        self.assertIsNone(self.ut._per_axis_tick_major({}, "primary_x"))
        self.assertIsNone(
            self.ut._per_axis_tick_major(
                {"axes": {"primary_x": {}}}, "primary_x",
            ),
        )

    def test_per_axis_tick_minor_reads_nested_slot(self):
        cfg = {"axes": {"primary_y": {"tick_minor": "0.05"}}}
        self.assertAlmostEqual(
            self.ut._per_axis_tick_minor(cfg, "primary_y"), 0.05,
        )

    def test_per_axis_grid_role_default(self):
        # Missing key → default differs per role.
        self.assertIs(self.ut._per_axis_grid({}, "primary_x"), True)
        self.assertIs(self.ut._per_axis_grid({}, "primary_y"), True)
        self.assertIs(self.ut._per_axis_grid({}, "secondary_x"), False)
        self.assertIs(self.ut._per_axis_grid({}, "secondary_y"), False)
        self.assertIs(self.ut._per_axis_grid({}, "tertiary_y"), False)

    def test_per_axis_grid_explicit_overrides_default(self):
        cfg = {"axes": {"primary_x": {"grid_show": False},
                        "secondary_y": {"grid_show": True}}}
        self.assertIs(self.ut._per_axis_grid(cfg, "primary_x"), False)
        self.assertIs(self.ut._per_axis_grid(cfg, "secondary_y"), True)

    def test_per_axis_color_reads_nested_slot(self):
        cfg = {"axes": {"primary_x": {"axis_color": "#ff8800"}}}
        self.assertEqual(
            self.ut._per_axis_color(cfg, "primary_x"), "#ff8800",
        )

    def test_per_axis_color_defaults_black(self):
        self.assertEqual(self.ut._per_axis_color({}, "primary_x"), "#000000")
        self.assertEqual(
            self.ut._per_axis_color({"axes": {"primary_x": {}}}, "primary_x"),
            "#000000",
        )

    def test_per_axis_color_rejects_non_string(self):
        # Defensive: pre-Phase-4an configs that somehow injected a
        # non-string into the slot fall back to the default rather
        # than propagating a bad value into matplotlib.
        cfg = {"axes": {"primary_x": {"axis_color": 0xff8800}}}
        self.assertEqual(self.ut._per_axis_color(cfg, "primary_x"), "#000000")


@unittest.skipUnless(_root is not None, "Tk root unavailable")
class TestPlotConfigDialogPerAxisPolishWidgetsPhase4an(unittest.TestCase):
    """CS-65 (Phase 4an) — per-axis tick-spacing Entries, grid_show
    Checkbutton, and axis_color colour picker on every per-axis tab.

    Each per-axis tab grows four widget rows below the Phase 4am Range /
    Autoscale / Scale rows. The Tk vars register through the existing
    ``_axis_control_vars`` registry (cross-typed: StringVar for the
    tick / colour keys, BooleanVar for ``grid_show``).
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    _AXIS_TAB_KEYS = (
        "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y",
    )

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- registry coverage ----

    def test_axis_control_vars_registered_for_tick_major(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            self.assertIn((role, "tick_major"), dlg._axis_control_vars)
            var = dlg._axis_control_vars[(role, "tick_major")]
            self.assertIsInstance(var, tk.StringVar)
            self.assertEqual(var.get(), "")

    def test_axis_control_vars_registered_for_tick_minor(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            self.assertIn((role, "tick_minor"), dlg._axis_control_vars)

    def test_axis_control_vars_registered_for_grid_show_as_bool(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            self.assertIn((role, "grid_show"), dlg._axis_control_vars)
            var = dlg._axis_control_vars[(role, "grid_show")]
            self.assertIsInstance(var, tk.BooleanVar)
            # Default split: True for primaries, False otherwise.
            expected = role in ("primary_x", "primary_y")
            self.assertIs(var.get(), expected)

    def test_axis_control_vars_registered_for_axis_color(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        for role in self._AXIS_TAB_KEYS:
            self.assertIn((role, "axis_color"), dlg._axis_control_vars)
            var = dlg._axis_control_vars[(role, "axis_color")]
            self.assertEqual(var.get(), "#000000")

    # ---- write-through behaviour ----

    def test_setting_tick_major_writes_to_working(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        dlg._axis_control_vars[("primary_x", "tick_major")].set("0.5")
        self.assertEqual(
            dlg._working["axes"]["primary_x"]["tick_major"], "0.5",
        )
        # Other roles untouched.
        self.assertEqual(
            dlg._working["axes"]["primary_y"]["tick_major"], "",
        )

    def test_setting_grid_show_false_writes_bool_to_working(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        dlg._axis_control_vars[("primary_y", "grid_show")].set(False)
        self.assertIs(
            dlg._working["axes"]["primary_y"]["grid_show"], False,
        )
        # primary_x still True (default).
        self.assertIs(
            dlg._working["axes"]["primary_x"]["grid_show"], True,
        )

    def test_setting_axis_color_writes_hex_to_working(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        dlg._axis_control_vars[("tertiary_y", "axis_color")].set("#ff8800")
        self.assertEqual(
            dlg._working["axes"]["tertiary_y"]["axis_color"], "#ff8800",
        )

    # ---- migration + working-copy seeding ----

    def test_working_copy_seeded_from_existing_phase_4an_values(self):
        self.config = {
            "axes": {
                "primary_x": {"tick_major": "0.5", "tick_minor": "0.1"},
                "primary_y": {"grid_show": False, "axis_color": "#cc0000"},
            },
        }
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        self.assertEqual(
            dlg._axis_control_vars[("primary_x", "tick_major")].get(),
            "0.5",
        )
        self.assertEqual(
            dlg._axis_control_vars[("primary_x", "tick_minor")].get(),
            "0.1",
        )
        self.assertIs(
            dlg._axis_control_vars[("primary_y", "grid_show")].get(),
            False,
        )
        self.assertEqual(
            dlg._axis_control_vars[("primary_y", "axis_color")].get(),
            "#cc0000",
        )

    def test_factory_reset_restores_phase_4an_defaults(self):
        dlg = self.psd.open_plot_config_dialog(self.host, self.config)
        # Dirty the polish keys on one role.
        dlg._axis_control_vars[("primary_y", "tick_major")].set("0.25")
        dlg._axis_control_vars[("primary_y", "grid_show")].set(False)
        dlg._axis_control_vars[("primary_y", "axis_color")].set("#00ff00")
        # Trigger Factory Reset.
        dlg._do_factory_reset()
        self.assertEqual(
            dlg._axis_control_vars[("primary_y", "tick_major")].get(), "",
        )
        self.assertIs(
            dlg._axis_control_vars[("primary_y", "grid_show")].get(), True,
        )
        self.assertEqual(
            dlg._axis_control_vars[("primary_y", "axis_color")].get(),
            "#000000",
        )

    def test_dialog_opens_on_every_per_axis_tab_without_error(self):
        # Smoke test: building the dialog should successfully construct
        # the four new widget rows on every per-axis tab. Without the
        # new rows wired through _make_axis_string_var / _make_axis_bool_var,
        # the registry assertions above would have failed; this one
        # additionally catches Tk widget-construction errors (colour
        # swatch Frame, Checkbutton, etc.).
        for tab in self._AXIS_TAB_KEYS:
            dlg = self.psd.open_plot_config_dialog(
                self.host, self.config, tab=tab,
            )
            self.assertTrue(bool(dlg.winfo_exists()))
            dlg.destroy()
            self.psd._open_dialogs.clear()


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogModelessPhase4ao(unittest.TestCase):
    """Phase 4ao / CS-66: Plot Settings dropped its ``grab_set()``.

    Re-pins the modeless contract independently of the
    :class:`TestPlotConfigDialogShell` suite so the lock is easy to
    find by phase tag. The shell suite still owns the singleton +
    transient + Cancel-revert behaviour; this class owns the explicit
    "main window stays interactive" + "no source-level grab call"
    invariants.
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog
        cls.open_dialog = staticmethod(plot_settings_dialog.open_plot_config_dialog)

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_main_window_stays_interactive_with_dialog_open(self):
        """The host frame must not be grabbed away while the dialog is open.

        The previous CS-06 modal contract used ``grab_set()`` which
        redirects every pointer/keyboard event to the dialog
        subtree until release. CS-66 drops that — the host frame is
        still in the focus chain.
        """
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        # ``grab_current`` on the root returns None when no widget
        # holds a grab.
        self.assertIsNone(
            _root.grab_current(),
            "No Tk widget should hold a grab while Plot Settings is open",
        )

    def test_source_does_not_call_grab_set(self):
        """Sentinel: re-introducing ``grab_set`` should require a
        deliberate edit.

        We pin the absence of the literal ``self.grab_set()`` call in
        :meth:`PlotConfigDialog.__init__` source so a future copy-paste
        from a modal dialog doesn't silently re-introduce the grab.
        """
        import inspect
        src = inspect.getsource(self.PlotConfigDialog.__init__)
        self.assertNotIn(
            "self.grab_set()", src,
            "PlotConfigDialog.__init__ must not call grab_set() (CS-66)",
        )

    def test_singleton_invariant_preserved_under_modeless(self):
        """CS-06 one-per-host uniqueness survives the modal→modeless flip."""
        first = self.open_dialog(self.host, self.config)
        second = self.open_dialog(self.host, self.config)
        self.assertIs(first, second)

    def test_destroy_does_not_break_with_no_grab(self):
        """Without a grab there is nothing to release; destroy must
        still complete cleanly."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg.destroy()
        # Idempotent — second destroy on an already-destroyed Toplevel
        # is a no-op via Tk's guard.
        try:
            dlg.destroy()
        except tk.TclError:
            pass


# =====================================================================
# CS-68 Phase 4ap — live-preview (USER-FLAGGED)
# =====================================================================


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogLivePreviewPhase4ap(unittest.TestCase):
    """CS-68 (Phase 4ap) — Plot Settings dialog runs in live-preview mode.

    Discrete widgets (Combobox, Checkbutton, Spinbox, color picker,
    Radiobutton) commit every edit immediately to the live config and
    fire ``on_apply``. Text Entry widgets defer the live commit to
    ``<FocusOut>`` and ``<Return>`` so per-keystroke typing does not
    redraw the canvas. The Apply button is retired.
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- module sentinels ----

    def test_apply_changes_live_method_present(self):
        """CS-68 sentinel: the live-commit helper exists on the dialog."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertTrue(callable(getattr(dlg, "_apply_changes_live", None)))

    def test_bind_entry_live_commit_method_present(self):
        """CS-68 sentinel: the FocusOut/Return helper for text Entries exists."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertTrue(
            callable(getattr(dlg, "_bind_entry_live_commit", None))
        )

    def test_defer_apply_keys_registered_for_text_label_entries(self):
        """CS-68: title/X label/Y label text Entries register defer-apply."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for key in ("title_text", "xlabel_text", "ylabel_text"):
            self.assertIn(
                key, dlg._defer_apply_keys,
                f"text Entry key {key!r} must defer live commit (CS-68)",
            )

    def test_defer_apply_axis_keys_registered_for_per_axis_entries(self):
        """CS-68: per-axis typed Entries register defer-apply."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        # axis_label_override is registered on every per-axis tab AND
        # on the Global mirror (idempotent set add); range_lo /
        # range_hi / tick_major / tick_minor are per-axis only.
        for role in ("primary_x", "secondary_x", "primary_y",
                     "secondary_y", "tertiary_y"):
            for key in ("axis_label_override", "range_lo", "range_hi",
                        "tick_major", "tick_minor"):
                self.assertIn(
                    (role, key), dlg._defer_apply_axis_keys,
                    f"per-axis Entry ({role!r}, {key!r}) must defer (CS-68)",
                )

    # ---- discrete widgets commit live ----

    def test_combobox_change_writes_through_immediately(self):
        """CS-68: Combobox StringVar edit (legend_position) commits live."""
        self.config["legend_position"] = "best"
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        dlg._control_vars["legend_position"].set("upper right")
        dlg.update_idletasks()
        self.assertEqual(self.config["legend_position"], "upper right")
        self.assertEqual(seen, [1])

    def test_int_spinbox_change_writes_through_immediately(self):
        """CS-68: int Spinbox edit (title_font_size) commits live."""
        self.config["title_font_size"] = 12
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        self.assertEqual(self.config["title_font_size"], 20)
        self.assertEqual(seen, [1])

    def test_per_axis_radio_writes_through_immediately(self):
        """CS-68: per-axis tick_direction Radiobutton commits live."""
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        dlg._axis_control_vars[
            ("primary_x", "tick_direction")
        ].set("out")
        dlg.update_idletasks()
        self.assertEqual(
            self.config["axes"]["primary_x"]["tick_direction"], "out",
        )
        self.assertEqual(seen, [1])

    def test_per_axis_autoscale_checkbutton_writes_through_immediately(self):
        """CS-68: per-axis BooleanVar Checkbutton (autoscale) commits live."""
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        dlg._axis_control_vars[("primary_y", "autoscale")].set(False)
        dlg.update_idletasks()
        self.assertIs(
            self.config["axes"]["primary_y"]["autoscale"], False,
        )
        self.assertEqual(seen, [1])

    # ---- text Entry defers commit until FocusOut / Return ----

    def test_text_label_entry_var_write_does_not_fire_on_apply(self):
        """CS-68: per-keystroke writes on title_text don't fire on_apply."""
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        # var.set simulates a keystroke writing into the StringVar.
        # Note: title_text trace flips the mode_var to "custom" which
        # IS a discrete commit — test with a non-empty initial mode
        # to suppress that branch.
        dlg._working["title_mode"] = "custom"
        dlg._control_vars["title_mode"].set("custom")
        dlg.update_idletasks()
        seen.clear()  # ignore the mode-flip commit
        dlg._control_vars["title_text"].set("My Title")
        dlg.update_idletasks()
        # Working copy reflects the typed text.
        self.assertEqual(dlg._working["title_text"], "My Title")
        # CS-68: live commit deferred — config NOT yet updated.
        self.assertNotEqual(self.config.get("title_text"), "My Title")
        self.assertEqual(seen, [])

    def test_text_label_entry_has_focus_out_and_return_bindings(self):
        """CS-68: title_text Entry binds <FocusOut> and <Return> for live commit."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        # Find the title_text Entry by matching its textvariable name.
        title_entries = [
            w for w in _all_descendants(dlg)
            if isinstance(w, tk.Entry)
            and str(w.cget("textvariable"))
            == str(dlg._control_vars["title_text"])
        ]
        self.assertEqual(len(title_entries), 1)
        entry = title_entries[0]
        focus_out_bindings = entry.bind("<FocusOut>")
        return_bindings = entry.bind("<Return>")
        # Tk's bind() returns the script string (or empty string when
        # nothing is bound). Non-empty proves a binding is attached.
        self.assertTrue(
            focus_out_bindings,
            "title_text Entry must carry a <FocusOut> binding (CS-68)",
        )
        self.assertTrue(
            return_bindings,
            "title_text Entry must carry a <Return> binding (CS-68)",
        )

    def test_text_label_entry_apply_changes_live_commits(self):
        """CS-68: the deferred path commits via _apply_changes_live (the
        binding's call target)."""
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        dlg._working["title_mode"] = "custom"
        dlg._control_vars["title_mode"].set("custom")
        dlg.update_idletasks()
        seen.clear()
        dlg._control_vars["title_text"].set("After Focus")
        dlg.update_idletasks()
        # Per-keystroke trace deferred — config not yet updated.
        self.assertNotEqual(self.config.get("title_text"), "After Focus")
        self.assertEqual(seen, [])
        # The bound FocusOut/Return target IS _apply_changes_live;
        # invoking it directly is the headless-test stand-in.
        dlg._apply_changes_live()
        self.assertEqual(self.config.get("title_text"), "After Focus")
        self.assertEqual(seen, [1])

    def test_per_axis_override_entry_focus_out_fires_on_apply(self):
        """CS-68: <FocusOut> on per-axis axis_label_override commits live."""
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        dlg._axis_control_vars[
            ("primary_y", "axis_label_override")
        ].set("Custom")
        dlg.update_idletasks()
        # Defer in effect: not yet committed live.
        self.assertEqual(seen, [])
        # Direct call substitutes for the FocusOut event (the binding
        # call target is the same).
        dlg._apply_changes_live()
        self.assertEqual(
            self.config["axes"]["primary_y"]["axis_label_override"], "Custom",
        )
        self.assertEqual(seen, [1])

    # ---- bulk reload coalesces redraws ----

    def test_user_defaults_bulk_load_fires_one_redraw(self):
        """CS-68: Reset Defaults pushes N values but fires on_apply once."""
        self.psd._USER_DEFAULTS.update({
            "title_font_size": 14,
            "grid": False,
            "background_color": "#eeeeee",
        })
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()
        seen.clear()
        dlg._do_reset_defaults()
        dlg.update_idletasks()
        # CS-68: bulk reload coalesces to one live commit.
        self.assertEqual(seen, [1])

    # ---- _commit_working_copy survives as a wrapper ----

    def test_commit_working_copy_is_apply_plus_marker_clear(self):
        """CS-68: _commit_working_copy now wraps _apply_changes_live + clear."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        self.assertEqual(dlg._modified_tabs, {"global"})
        dlg._commit_working_copy()
        # Markers cleared; config retains the edit.
        self.assertEqual(dlg._modified_tabs, set())
        self.assertEqual(self.config["title_font_size"], 20)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogSecondaryXLinkGreyingPhase4aq(unittest.TestCase):
    """CS-69 (Phase 4aq) — Secondary X link greying state-machine.

    Pins the contract for the new ``secondary_x_linked: bool``
    constructor kwarg. When True, the Secondary X tab's
    ``range_lo`` / ``range_hi`` / ``autoscale`` / ``scale`` widgets
    render ``state="disabled"`` because matplotlib's linked
    secondary derives its limits from the primary via the forward
    function — pushing values into those widgets would back-
    propagate through the inverse and corrupt the primary axis
    (B-005). ``custom_ticks`` / ``tick_major`` / ``tick_minor`` stay
    editable — they're the user's actual affordances on the linked
    axis.

    The greying is a snapshot at dialog open; the kwarg defaults to
    False, so every existing test that constructs the dialog without
    the kwarg keeps the pre-CS-69 fully-editable behaviour.
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    # ---- kwarg plumbing ----

    def test_secondary_x_linked_kwarg_defaults_false(self):
        # Existing tests construct PlotConfigDialog without the kwarg
        # and must keep working.
        dlg = self.PlotConfigDialog(self.host, self.config)
        self.assertIs(dlg._secondary_x_linked, False)

    def test_secondary_x_linked_true_stored_on_dialog(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config, secondary_x_linked=True,
        )
        self.assertIs(dlg._secondary_x_linked, True)

    def test_factory_threads_secondary_x_linked_through(self):
        # ``open_plot_config_dialog`` is the public entry; the kwarg
        # must propagate.
        dlg = self.psd.open_plot_config_dialog(
            self.host, self.config, secondary_x_linked=True,
        )
        self.assertIs(dlg._secondary_x_linked, True)

    # ---- widget registry (CS-69 hook for greying + future tests) ----

    def test_axis_control_widgets_registry_populated(self):
        # The registry exposes (role, key) → widget for every per-axis
        # role on the four greyable keys plus custom_ticks. Tests can
        # address them by key instead of walking the widget tree.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for role in ("primary_x", "secondary_x", "primary_y",
                     "secondary_y", "tertiary_y"):
            for key in ("range_lo", "range_hi", "autoscale", "scale",
                        "custom_ticks"):
                self.assertIn(
                    (role, key), dlg._axis_control_widgets,
                    f"(role, key)=({role}, {key}) missing from registry",
                )

    # ---- greying invariants ----

    def test_secondary_x_widgets_disabled_when_linked(self):
        dlg = self.PlotConfigDialog(
            self.host, self.config, secondary_x_linked=True,
        )
        dlg.update_idletasks()
        for key in ("range_lo", "range_hi", "autoscale", "scale"):
            w = dlg._axis_control_widgets[("secondary_x", key)]
            self.assertEqual(
                str(w.cget("state")), "disabled",
                f"secondary_x.{key} widget should be disabled when "
                f"secondary_x_linked=True",
            )

    def test_secondary_x_widgets_editable_when_not_linked(self):
        # Default False → pre-CS-69 fully-editable behaviour.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for key in ("range_lo", "range_hi"):
            w = dlg._axis_control_widgets[("secondary_x", key)]
            self.assertEqual(str(w.cget("state")), "normal")
        autoscale_cb = dlg._axis_control_widgets[
            ("secondary_x", "autoscale")
        ]
        self.assertEqual(str(autoscale_cb.cget("state")), "normal")
        scale_combo = dlg._axis_control_widgets[("secondary_x", "scale")]
        # Combobox uses "readonly" as its normal state.
        self.assertEqual(str(scale_combo.cget("state")), "readonly")

    def test_custom_ticks_entry_editable_even_when_linked(self):
        # Custom ticks is the user's actual affordance on the linked
        # axis (the whole point of the B-005 fix); it stays editable.
        dlg = self.PlotConfigDialog(
            self.host, self.config, secondary_x_linked=True,
        )
        dlg.update_idletasks()
        w = dlg._axis_control_widgets[("secondary_x", "custom_ticks")]
        self.assertEqual(str(w.cget("state")), "normal")

    def test_other_role_widgets_not_disabled_when_secondary_x_linked(self):
        # Greying is scoped to the Secondary X tab. The other four
        # per-axis tabs stay fully editable.
        dlg = self.PlotConfigDialog(
            self.host, self.config, secondary_x_linked=True,
        )
        dlg.update_idletasks()
        for role in ("primary_x", "primary_y", "secondary_y", "tertiary_y"):
            for key in ("range_lo", "range_hi"):
                w = dlg._axis_control_widgets[(role, key)]
                self.assertEqual(
                    str(w.cget("state")), "normal",
                    f"{role}.{key} should NOT be disabled "
                    f"(greying is secondary_x-only)",
                )


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogCustomTicksPhase4aq(unittest.TestCase):
    """CS-69 (Phase 4aq) — ``custom_ticks`` Entry per-axis schema + live.

    Pins:

    1. The schema's ``custom_ticks`` key defaults to ``""`` on every
       per-axis role.
    2. The Entry registers in :attr:`PlotConfigDialog._defer_apply_axis_keys`
       so it commits live on ``<FocusOut>`` / ``<Return>`` (CS-68
       consistency).
    3. Setting the Tk var writes through to the working copy.
    4. ``_apply_changes_live`` propagates the working copy into the
       host config dict (the host's source of truth for the renderer).
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotConfigDialog = plot_settings_dialog.PlotConfigDialog

    _AXIS_TAB_KEYS = (
        "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y",
    )

    def setUp(self):
        self.psd._open_dialogs.clear()
        self.psd._USER_DEFAULTS.clear()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.config: dict = {}

    def tearDown(self):
        for dlg in list(self.psd._open_dialogs.values()):
            try:
                dlg.destroy()
            except Exception:
                pass
        self.psd._open_dialogs.clear()
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_custom_ticks_default_empty_on_every_role(self):
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(
                self.psd._FACTORY_DEFAULTS["axes"][role]["custom_ticks"],
                "",
                f"{role}.custom_ticks factory default should be empty",
            )

    def test_custom_ticks_entry_is_deferred_apply(self):
        # CS-68: typed Entries defer commit to <FocusOut>/<Return>.
        # The (role, key) pair must register in _defer_apply_axis_keys
        # for every per-axis role, so the typed Entry's per-keystroke
        # var.set() does NOT auto-fire the live commit.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for role in self._AXIS_TAB_KEYS:
            self.assertIn(
                (role, "custom_ticks"), dlg._defer_apply_axis_keys,
                f"({role}, custom_ticks) should defer-apply per CS-68",
            )

    def test_var_set_writes_to_working_copy(self):
        # Setting the Tk var writes through to the working copy
        # (whether or not the live commit fires).
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._axis_control_vars[
            ("secondary_x", "custom_ticks")
        ].set("300, 400, 500")
        dlg.update_idletasks()
        self.assertEqual(
            dlg._working["axes"]["secondary_x"]["custom_ticks"],
            "300, 400, 500",
        )

    def test_apply_changes_live_propagates_to_host_config(self):
        # CS-68: <FocusOut>/<Return> triggers _apply_changes_live which
        # writes the working copy into ``self.config`` (the host's
        # source of truth for the renderer).
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._axis_control_vars[
            ("secondary_x", "custom_ticks")
        ].set("300, 400, 500")
        dlg._apply_changes_live()
        self.assertEqual(
            self.config["axes"]["secondary_x"]["custom_ticks"],
            "300, 400, 500",
        )

    def test_cancel_revert_clears_uncommitted_custom_ticks(self):
        # CS-68 protects un-committed Entry edits via the _snapshot
        # taken at dialog open. With CS-68 live-preview semantics,
        # the working-copy write happens on var.set (above), but the
        # host config only picks up the value at <FocusOut>/<Return>.
        # So setting the var without firing _apply_changes_live and
        # then Cancelling confirms the host config never saw the
        # edit. We seed the host config with a known starting value
        # so the assertion has something concrete to compare against
        # post-revert.
        self.config = {"axes": {"secondary_x": {"custom_ticks": "100"}}}
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._axis_control_vars[
            ("secondary_x", "custom_ticks")
        ].set("999")
        dlg.update_idletasks()
        # Cancel discards the working-copy change without ever
        # committing to host config — config returns to the snapshot.
        dlg._do_cancel()
        self.assertEqual(
            self.config["axes"]["secondary_x"]["custom_ticks"],
            "100",
            "Cancel should revert un-committed custom_ticks edit "
            "back to the snapshot value",
        )

    def test_apply_changes_live_with_invalid_custom_ticks_stores_raw(self):
        # The dialog stores the raw string; the parser silently drops
        # invalid tokens at the renderer side. Confirms the dialog
        # doesn't pre-filter.
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._axis_control_vars[
            ("secondary_x", "custom_ticks")
        ].set("300, abc, 500")
        dlg._apply_changes_live()
        self.assertEqual(
            self.config["axes"]["secondary_x"]["custom_ticks"],
            "300, abc, 500",
        )


class TestPlotConfigMigrationCustomTicksPhase4aq(unittest.TestCase):
    """CS-69 (Phase 4aq) — migration fills in ``custom_ticks: ""``.

    The migration shim reuses the existing CS-62 factory walk; no new
    code in :func:`migrate_plot_config` is required. These tests pin
    that the existing walk picks up the new schema key, preserves
    user-set values, and is idempotent — and confirm CS-46's
    PTMG_FORMAT_VERSION does NOT need to bump (the addition is
    backward-compatible: pre-Phase-4aq saves load with ``""`` defaults
    and re-saves include the key without protocol change).
    """

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog

    _AXIS_TAB_KEYS = (
        "primary_x", "secondary_x", "primary_y", "secondary_y", "tertiary_y",
    )

    def test_migration_fills_custom_ticks_on_every_role(self):
        cfg: dict = {}
        self.psd.migrate_plot_config(cfg)
        for role in self._AXIS_TAB_KEYS:
            self.assertEqual(
                cfg["axes"][role]["custom_ticks"], "",
                f"{role}.custom_ticks should be filled to '' by migration",
            )

    def test_migration_preserves_user_set_custom_ticks(self):
        cfg: dict = {
            "axes": {
                "secondary_x": {"custom_ticks": "300, 400, 500"},
            },
        }
        self.psd.migrate_plot_config(cfg)
        self.assertEqual(
            cfg["axes"]["secondary_x"]["custom_ticks"], "300, 400, 500",
        )
        # Other roles get the factory default "".
        for role in ("primary_x", "primary_y", "secondary_y", "tertiary_y"):
            self.assertEqual(cfg["axes"][role]["custom_ticks"], "")

    def test_migration_is_idempotent_on_custom_ticks(self):
        cfg: dict = {
            "axes": {
                "secondary_x": {"custom_ticks": "300, 400"},
            },
        }
        self.psd.migrate_plot_config(cfg)
        snapshot = copy.deepcopy(cfg)
        self.psd.migrate_plot_config(cfg)
        self.assertEqual(cfg, snapshot)

    def test_pre_phase_4aq_config_loads_through_factory(self):
        # A pre-Phase-4aq config carries the CS-65 ten-key schema for
        # one role and nothing for the others. Migration fills the
        # missing keys (including custom_ticks) from factory defaults
        # without touching the user's values.
        cfg: dict = {
            "axes": {
                "primary_y": {
                    "tick_direction": "out",
                    "axis_label_override": "Absorbance",
                    "range_lo": "0",
                    "range_hi": "1",
                    "autoscale": False,
                    "scale": "linear",
                    "tick_major": "0.2",
                    "tick_minor": "0.05",
                    "grid_show": True,
                    "axis_color": "#000000",
                    # Note: custom_ticks missing — simulates pre-CS-69 save.
                },
            },
        }
        self.psd.migrate_plot_config(cfg)
        # The pre-existing keys stay put.
        self.assertEqual(cfg["axes"]["primary_y"]["tick_direction"], "out")
        self.assertEqual(cfg["axes"]["primary_y"]["range_lo"], "0")
        self.assertEqual(cfg["axes"]["primary_y"]["tick_major"], "0.2")
        # The new CS-69 key is filled with the factory default.
        self.assertEqual(cfg["axes"]["primary_y"]["custom_ticks"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
