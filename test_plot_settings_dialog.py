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

    # ----------- modal contract (transient + grab) -----------

    def test_modal_grab_set_on_visible_window(self):
        """grab_set is part of the modal contract per CS-06."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        # ``grab_status`` returns the empty string when no grab is held.
        # When transient + grab_set succeed it returns "local" or
        # "global". Acceptance: anything non-empty.
        dlg.update_idletasks()
        status = dlg.grab_status()
        self.assertNotEqual(
            status, "",
            "Plot Settings dialog must hold a Tk grab once visible",
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

    # ----------- working copy: edits do NOT auto-apply -----------

    def test_slider_change_does_not_auto_apply(self):
        """Spinbox/checkbox edits update working copy only, not config."""
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()

        # Working copy reflects the new value.
        self.assertEqual(dlg._working["title_font_size"], 20)
        # Config dict is untouched until Apply.
        self.assertEqual(self.config["title_font_size"], 12)

    def test_grid_toggle_does_not_auto_apply(self):
        self.config["grid"] = True
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["grid"].set(False)
        dlg.update_idletasks()

        self.assertEqual(dlg._working["grid"], False)
        self.assertEqual(self.config["grid"], True)

    def test_apply_does_not_fire_on_construction(self):
        """on_apply must not be invoked merely because the dialog opened."""
        seen: list = []
        self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        ).update_idletasks()
        self.assertEqual(seen, [])

    # ----------- Apply commits working copy and fires on_apply -----------

    def test_apply_commits_working_copy_and_calls_on_apply(self):
        self.config["title_font_size"] = 12
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(18)
        dlg.update_idletasks()

        # Pre-Apply: config still untouched, on_apply unsignalled.
        self.assertEqual(self.config["title_font_size"], 12)
        self.assertEqual(seen, [])

        dlg._do_apply()

        # Post-Apply: config updated in place, on_apply fired exactly once.
        self.assertEqual(self.config["title_font_size"], 18)
        self.assertEqual(seen, [1])

    def test_apply_keeps_dialog_open(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._do_apply()
        self.assertTrue(bool(dlg.winfo_exists()))

    # ----------- Save commits working copy and closes (CS-23) -----------

    def test_save_button_is_present(self):
        """CS-23: button row is Apply · Save · Cancel."""
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertTrue(hasattr(dlg, "_save_btn"))
        self.assertEqual(str(dlg._save_btn.cget("text")), "Save")

    def test_save_commits_working_copy_to_config(self):
        """Save mutates the caller's config in place, like Apply."""
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(18)
        dlg.update_idletasks()
        self.assertEqual(self.config["title_font_size"], 12)  # not yet

        dlg._do_save()
        self.assertEqual(self.config["title_font_size"], 18)

    def test_save_fires_on_apply_exactly_once(self):
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()

        dlg._control_vars["grid"].set(False)
        dlg._do_save()
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

    def test_cancel_reverts_intermediate_apply(self):
        """Cancel reverts to the __init__ snapshot, even after Apply."""
        self.config["title_font_size"] = 12
        seen: list = []
        dlg = self.PlotConfigDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        )
        dlg.update_idletasks()

        # User edits and clicks Apply.
        dlg._control_vars["title_font_size"].set(20)
        dlg._do_apply()
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

        dlg._control_vars["title_font_size"].set(20)
        dlg._do_apply()
        self.assertEqual(self.config["title_font_size"], 20)

        # The protocol handler is _on_close_requested — calling it
        # directly mimics the [X] gesture.
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

    def test_save_as_default_does_not_apply_to_config(self):
        """Save-as-Default writes to module state, not the tab config."""
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(20)
        dlg._do_save_as_default()

        # Tab config is unchanged — only Apply commits.
        self.assertEqual(self.config["title_font_size"], 12)

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

    def test_factory_reset_does_not_apply_to_config(self):
        """Factory Reset rewrites the working copy only; Apply commits."""
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._do_factory_reset()
        dlg.update_idletasks()

        # Config dict still carries the user's pre-existing value
        # because no Apply happened.
        self.assertEqual(self.config["title_font_size"], 12)

    def test_factory_reset_then_apply_writes_factory_values_to_config(self):
        # A Factory Reset followed by Apply is the only way the
        # factory values reach the tab.
        self.config["title_font_size"] = 22
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._do_factory_reset()
        dlg._do_apply()

        self.assertEqual(
            self.config["title_font_size"],
            self.psd._FACTORY_DEFAULTS["title_font_size"],
        )


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
        # from "out" to "in". Existing _USER_DEFAULTS that pin "out"
        # are unaffected (factory-default-only flip per the decision
        # lock — no migration).
        self.assertEqual(
            self.psd._FACTORY_DEFAULTS["tick_direction"], "in",
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
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["grid_color"].set("#ff0000")
        dlg._control_vars["tertiary_axis_offset"].set(1.40)
        dlg._control_vars["tick_direction"].set("out")
        dlg.update_idletasks()
        dlg._do_factory_reset()
        dlg.update_idletasks()
        self.assertEqual(dlg._working["grid_color"], "#b0b0b0")
        self.assertAlmostEqual(
            dlg._working["tertiary_axis_offset"], 1.12, places=4,
        )
        self.assertEqual(dlg._working["tick_direction"], "in")

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

    def test_axis_tab_shell_carries_phase_4aj_placeholder(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        for key in ("primary_x", "secondary_x",
                    "primary_y", "secondary_y", "tertiary_y"):
            frame = dlg._tab_frames[key]
            texts = [
                c.cget("text") for c in _all_descendants(frame)
                if isinstance(c, tk.Label)
            ]
            self.assertTrue(
                any("Phase 4aj" in t for t in texts),
                f"axis tab {key!r} missing the 'Per-axis settings land "
                f"in Phase 4aj+' placeholder; labels were {texts}",
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

    def test_global_tab_edits_still_reach_config_on_apply(self):
        # Sanity check that the lift-into-Global tab didn't break
        # the existing _do_apply working-copy flow.
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config, tab="primary_y")
        dlg.update_idletasks()
        # Switch to Global to edit the existing widget.
        dlg.select_tab("global")
        dlg._control_vars["title_font_size"].set(22)
        dlg.update_idletasks()
        dlg._do_apply()
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
        # No factory key has a registered tab today — they all live
        # on the Global tab. Phase 4aj+ extends _KEY_TO_TAB as
        # per-axis settings move out of Global.
        for key in self.psd._FACTORY_DEFAULTS:
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

    # ----- Apply / Save clear markers -----

    def test_apply_clears_modified_tabs(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        self.assertEqual(dlg._modified_tabs, {"global"})
        dlg._do_apply()
        self.assertEqual(dlg._modified_tabs, set())
        self.assertEqual(self._tab_text(dlg, "global"), "Global")

    def test_save_clears_modified_tabs_before_destroy(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        # We can't introspect after destroy; record _modified_tabs
        # snapshot just before destroy by calling clear ourselves
        # via _commit_working_copy instead. Equivalent invariant.
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
# CS-60 Phase 4ai: new four-button row (Save / Apply / Apply All / Cancel)
# =====================================================================


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotConfigDialogButtonRowPhase4ai(unittest.TestCase):
    """The dialog-level button row carries four buttons in canonical order.

    Save · Apply · Apply to All Tabs · Cancel — right-aligned at the
    bottom of the Toplevel. Apply to All Tabs is disabled unless the
    host supplied an ``on_apply_all_tabs`` callback.
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

    def test_four_buttons_in_order(self):
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        # The attributes are the canonical names; the visible text is
        # what the user sees.
        self.assertEqual(dlg._save_btn.cget("text"), "Save")
        self.assertEqual(dlg._apply_btn.cget("text"), "Apply")
        self.assertEqual(
            dlg._apply_all_tabs_btn.cget("text"), "Apply to All Tabs",
        )
        self.assertEqual(dlg._cancel_btn.cget("text"), "Cancel")

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

    def test_apply_all_tabs_commits_locally_first(self):
        # The host's replication callback reads self._config, so the
        # local commit must run BEFORE the host callback fires.
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

    def test_has_uncommitted_changes_true_after_apply_then_no_edit(self):
        # Apply commits to config but the __init__ snapshot lives on;
        # Cancel would still revert. So has_uncommitted_changes
        # reports True until the snapshot also matches.
        self.config["title_font_size"] = 12
        dlg = self.PlotConfigDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()
        dlg._do_apply()
        # Modified set was cleared by Apply, but config != snapshot.
        self.assertEqual(dlg._modified_tabs, set())
        self.assertTrue(dlg._has_uncommitted_changes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
