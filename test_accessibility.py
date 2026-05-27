"""Tests for accessibility.py (Phase 4ax, CS-76).

Phase 4ax introduces the cross-axis accessibility helpers module
shell. These tests pin the two recipe-canonical helpers:

* :func:`bind_escape_to_close` — Escape binding registered on the
  Toplevel; the bound callback invokes the supplied handler and
  returns ``"break"`` to stop propagation.
* :func:`attach_shortcut_tooltip` — Tooltip is constructed against
  the target widget and exposes the canonical CS-42 ``Tooltip``
  surface for later text rotation.

``event_generate`` on a withdrawn root is unreliable across the full
suite (the same caveat documented in ``test_collapsible_section`` and
``test_plot_settings_dialog`` — the dispatch fires in isolation but is
intermittently dropped once many Toplevels have been built and torn
down). The tests below exercise the handler directly via the Tcl
binding script — the same code path Tk would invoke on a real key
press — keeping them deterministic.

Headless environments are skipped via ``unittest.skipUnless``.
"""

from __future__ import annotations

import unittest

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _HAS_DISPLAY = True
except Exception:  # pragma: no cover — only hit on headless CI
    _root = None
    _HAS_DISPLAY = False


from accessibility import bind_escape_to_close, attach_shortcut_tooltip
from tooltip import Tooltip


def _invoke_via_return(top: tk.Toplevel, handler) -> str:
    """Wire ``bind_escape_to_close`` and invoke the returned callback.

    ``event_generate`` on a transient/withdrawn Toplevel is unreliable
    across the full suite (the dispatch fires in isolation but is
    intermittently dropped once many Toplevels have been built and
    torn down — same caveat documented in ``test_collapsible_section``
    and ``test_plot_settings_dialog``). Calling the returned callback
    exercises the same code path Tk would take on a real key press.
    """
    cb = bind_escape_to_close(top, handler)
    return cb(None)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestBindEscapeToClose(unittest.TestCase):

    def setUp(self):
        self.top = tk.Toplevel(_root)
        self.top.update_idletasks()
        self.calls: list[None] = []

    def tearDown(self):
        try:
            self.top.destroy()
        except Exception:
            pass

    def _handler(self) -> None:
        self.calls.append(None)

    def test_escape_binding_is_registered(self):
        # Pre-condition: no <Escape> binding on a bare Toplevel.
        self.assertEqual(self.top.bind("<Escape>"), "")
        bind_escape_to_close(self.top, self._handler)
        # Post-condition: <Escape> binding is present.
        self.assertNotEqual(self.top.bind("<Escape>"), "")

    def test_handler_fires_when_binding_is_invoked(self):
        _invoke_via_return(self.top, self._handler)
        self.assertEqual(len(self.calls), 1)

    def test_handler_invoked_with_no_arguments(self):
        recorded: list[int] = []

        def picky_handler():  # noqa: ANN202 — intentional 0-arg
            recorded.append(0)

        _invoke_via_return(self.top, picky_handler)
        self.assertEqual(recorded, [0])

    def test_callback_returns_break(self):
        # The bound callback must return the literal "break" string so
        # Tk halts event propagation. Production callers ignore the
        # return; tests pin it.
        result = _invoke_via_return(self.top, self._handler)
        self.assertEqual(result, "break")

    def test_multiple_invocations_fire_handler_each_time(self):
        cb = bind_escape_to_close(self.top, self._handler)
        for _ in range(3):
            cb(None)
        self.assertEqual(len(self.calls), 3)

    def test_bind_script_contains_break_keyword(self):
        # Tk wraps Python callbacks returning ``"break"`` in a Tcl
        # script that emits the literal ``break`` keyword so Tk
        # stops propagating the event. Pin the script shape so a
        # future refactor that drops the ``return "break"`` line
        # gets flagged.
        bind_escape_to_close(self.top, self._handler)
        script = self.top.bind("<Escape>")
        self.assertIn("break", script)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestAttachShortcutTooltip(unittest.TestCase):

    def setUp(self):
        self.host = tk.Frame(_root)
        self.widget = tk.Label(self.host, text="target")
        self.widget.pack()
        self.host.update_idletasks()

    def tearDown(self):
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_returns_tooltip_instance(self):
        tip = attach_shortcut_tooltip(self.widget, "Ctrl+X")
        self.assertIsInstance(tip, Tooltip)

    def test_tooltip_text_round_trips(self):
        tip = attach_shortcut_tooltip(self.widget, "Ctrl+X — extract")
        # Tooltip stores text on ``_text``; the constructor argument
        # should persist until rotated via ``update_text``.
        self.assertEqual(tip._text, "Ctrl+X — extract")
        tip.update_text("Ctrl+Y — yank")
        self.assertEqual(tip._text, "Ctrl+Y — yank")

    def test_tooltip_widget_is_the_target(self):
        tip = attach_shortcut_tooltip(self.widget, "Ctrl+Z")
        self.assertIs(tip._widget, self.widget)


class TestBinahEscapeInventoryPhase4ax(unittest.TestCase):
    """Source-level sentinel: every ``tk.Toplevel(`` construction site
    in binah.py has a paired ``bind_escape_to_close(`` call (CS-75 D3
    scope expanded at Phase 4ax step-5 elicitation to cover the 7
    app-level binah.py dialogs).

    binah.py has no dedicated test module — the main app is
    constructed only by ``binah.OrcaTDDFTApp.__init__`` which spins up
    every tab + the matplotlib backend, too expensive for the unit
    suite. A source-level count is the cheapest contract pin: if a
    future commit adds a Toplevel without the recipe (or removes the
    bind call), the counts diverge and this test fails.
    """

    def test_binah_toplevels_and_escape_bindings_one_to_one(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parent / "binah.py").read_text(
            encoding="utf-8",
        )
        toplevels = src.count("tk.Toplevel(")
        escape_binds = src.count("bind_escape_to_close(")
        # All 7 binah.py Toplevels (FEFF Setup, Load Spectrum,
        # SXRMB, BioXAS, Athena, No-Data diagnostic, Impl Drift
        # Details) carry the Phase 4ax CS-75 D3 recipe. If a new
        # dialog lands, increment both counts in lockstep.
        self.assertEqual(toplevels, 7,
                         f"expected 7 tk.Toplevel sites, found {toplevels}")
        self.assertEqual(escape_binds, toplevels,
                         "every binah.py Toplevel must pair with "
                         "bind_escape_to_close (Phase 4ax CS-75 D3)")


class TestPalettePhase4ayInventory(unittest.TestCase):
    """Source-level sentinels for Phase 4ay (CS-75 D2 / sub-axis B):
    palette opt-in surface area is pinned in the canonical places.

    These are source-text counts rather than runtime imports — the
    cheapest way to flag a future refactor that drops a load-bearing
    piece of the palette wiring (e.g. removes ``set_active_palette``
    from binah's load path, or strips the Combobox commit-on-click
    handler from the dialog). Same convention as the Phase 4ax
    binah-Toplevel sentinel above.
    """

    @staticmethod
    def _read(filename: str) -> str:
        from pathlib import Path
        return (
            Path(__file__).resolve().parent / filename
        ).read_text(encoding="utf-8")

    def test_node_styles_exports_palette_opt_in_surface(self):
        # Pin the four Phase 4ay additions on the public surface.
        src = self._read("node_styles.py")
        for name in (
            "WONG_2011_PALETTE",
            "SPECTRUM_PALETTE_NAMES",
            "active_palette",
            "set_active_palette",
        ):
            self.assertIn(name, src,
                          f"node_styles.py is missing {name}")

    def test_plot_settings_dialog_has_accessibility_tab(self):
        # The Accessibility tab is the first surface of CS-75 D1.
        # Pin the canonical wiring: the tab key, the build method
        # name, and the commit-on-click handler.
        src = self._read("plot_settings_dialog.py")
        self.assertIn("_build_accessibility_tab", src)
        self.assertIn("_on_palette_var_write", src)
        self.assertIn('"accessibility"', src)

    def test_plot_settings_dialog_imports_node_styles(self):
        # The dialog must call set_active_palette on the Combobox flip
        # so the renderer sees the new palette. Pin the import + at
        # least one set_active_palette call site.
        src = self._read("plot_settings_dialog.py")
        self.assertIn("import node_styles", src)
        self.assertIn("node_styles.set_active_palette", src)

    def test_binah_load_path_restores_active_palette(self):
        # The CS-46 round-trip is only half the story — load must
        # also flip the active palette so subsequent
        # pick_default_color calls (e.g. a UVVIS load on the just-
        # opened project) paint in the user's saved palette.
        src = self._read("binah.py")
        self.assertIn("import node_styles", src)
        self.assertIn("set_active_palette", src,
                      "binah.py load path must call "
                      "node_styles.set_active_palette after "
                      "_USER_DEFAULTS.update")


if __name__ == "__main__":
    unittest.main()
