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

# Try to construct a Tk root once at module import time. If it fails
# (no display, missing tcl/tk), every test in the file is skipped.
try:
    import tkinter as tk
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


def _section_titles(dlg) -> list[str]:
    return [lf.cget("text") for lf in _label_frames(dlg)]


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPlotSettingsDialogShell(unittest.TestCase):
    """Construction, modal contract, registry, snapshot+cancel revert."""

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotSettingsDialog = plot_settings_dialog.PlotSettingsDialog
        cls.open_dialog = staticmethod(plot_settings_dialog.open_plot_settings_dialog)

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
        dlg = self.PlotSettingsDialog(self.host, self.config)
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
        dlg = self.PlotSettingsDialog(self.host, self.config)
        dlg.update_idletasks()
        self.assertEqual(dlg._working["title_font_size"], 22)
        self.assertEqual(dlg._working["grid"], False)
        # Spinbox / checkbox controls reflect the working copy.
        self.assertEqual(dlg._control_vars["title_font_size"].get(), 22)
        self.assertEqual(bool(dlg._control_vars["grid"].get()), False)

    # ----------- modal contract (transient + grab) -----------

    def test_modal_grab_set_on_visible_window(self):
        """grab_set is part of the modal contract per CS-06."""
        dlg = self.PlotSettingsDialog(self.host, self.config)
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
        dlg = self.PlotSettingsDialog(self.host, self.config)
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
        dlg = self.PlotSettingsDialog(
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
        dlg = self.PlotSettingsDialog(self.host, self.config)
        dlg.update_idletasks()
        titles = set(_section_titles(dlg))
        self.assertEqual(titles, {"Appearance"})

    # ----------- working copy: edits do NOT auto-apply -----------

    def test_slider_change_does_not_auto_apply(self):
        """Spinbox/checkbox edits update working copy only, not config."""
        self.config["title_font_size"] = 12
        dlg = self.PlotSettingsDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["title_font_size"].set(20)
        dlg.update_idletasks()

        # Working copy reflects the new value.
        self.assertEqual(dlg._working["title_font_size"], 20)
        # Config dict is untouched until Apply.
        self.assertEqual(self.config["title_font_size"], 12)

    def test_grid_toggle_does_not_auto_apply(self):
        self.config["grid"] = True
        dlg = self.PlotSettingsDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._control_vars["grid"].set(False)
        dlg.update_idletasks()

        self.assertEqual(dlg._working["grid"], False)
        self.assertEqual(self.config["grid"], True)

    def test_apply_does_not_fire_on_construction(self):
        """on_apply must not be invoked merely because the dialog opened."""
        seen: list = []
        self.PlotSettingsDialog(
            self.host, self.config, on_apply=lambda: seen.append(1),
        ).update_idletasks()
        self.assertEqual(seen, [])

    # ----------- Apply commits working copy and fires on_apply -----------

    def test_apply_commits_working_copy_and_calls_on_apply(self):
        self.config["title_font_size"] = 12
        seen: list = []
        dlg = self.PlotSettingsDialog(
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
        dlg = self.PlotSettingsDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._do_apply()
        self.assertTrue(bool(dlg.winfo_exists()))

    # ----------- Cancel reverts and closes -----------

    def test_cancel_reverts_intermediate_apply(self):
        """Cancel reverts to the __init__ snapshot, even after Apply."""
        self.config["title_font_size"] = 12
        seen: list = []
        dlg = self.PlotSettingsDialog(
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
        dlg = self.PlotSettingsDialog(self.host, self.config)
        dlg.update_idletasks()
        dlg._do_cancel()
        # winfo_exists is 0 after destroy in this Tk version.
        self.assertEqual(int(dlg.winfo_exists()), 0)

    def test_window_close_x_is_treated_as_cancel(self):
        self.config["title_font_size"] = 12
        dlg = self.PlotSettingsDialog(self.host, self.config)
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
class TestPlotSettingsDialogDefaults(unittest.TestCase):
    """Save-as-Default / Reset Defaults / Factory Reset semantics."""

    @classmethod
    def setUpClass(cls):
        import plot_settings_dialog
        cls.psd = plot_settings_dialog
        cls.PlotSettingsDialog = plot_settings_dialog.PlotSettingsDialog

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
        dlg = self.PlotSettingsDialog(self.host, self.config)
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
        dlg = self.PlotSettingsDialog(self.host, self.config)
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

        dlg = self.PlotSettingsDialog(self.host, self.config)
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
        dlg = self.PlotSettingsDialog(self.host, self.config)
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

        dlg = self.PlotSettingsDialog(self.host, self.config)
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
        dlg = self.PlotSettingsDialog(self.host, self.config)
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
        dlg = self.PlotSettingsDialog(self.host, self.config)
        dlg.update_idletasks()

        dlg._do_factory_reset()
        dlg._do_apply()

        self.assertEqual(
            self.config["title_font_size"],
            self.psd._FACTORY_DEFAULTS["title_font_size"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
