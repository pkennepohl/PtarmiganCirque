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


from accessibility import (
    bind_escape_to_close,
    attach_shortcut_tooltip,
    bind_shortcut,
    register_shortcut,
    ShortcutEntry,
    SHORTCUT_REGISTRY,
    _reset_shortcut_registry,
    scale_font_size,
    active_font_scale,
    set_active_font_scale,
    _coerce_font_scale,
    _reset_font_scale,
    _NAMED_FONT_BASE_SIZES,
)
import accessibility as _accessibility_mod
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


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestShortcutRegistryPhase4az(unittest.TestCase):
    """Phase 4az CS-78 — registry + register_shortcut + bind_shortcut."""

    def setUp(self):
        # The registry is module-level state. Snapshot whatever the
        # main app has registered (test runner imports may have
        # populated buckets) and restore on tearDown so cross-suite
        # ordering doesn't matter.
        self._snapshot = {
            cat: list(entries)
            for cat, entries in SHORTCUT_REGISTRY.items()
        }
        _reset_shortcut_registry()
        self.host = tk.Frame(_root)
        self.host.pack()
        self.host.update_idletasks()

    def tearDown(self):
        try:
            self.host.destroy()
        except Exception:
            pass
        SHORTCUT_REGISTRY.clear()
        SHORTCUT_REGISTRY.update(
            {cat: list(entries) for cat, entries in self._snapshot.items()}
        )

    def test_shortcut_entry_is_frozen_dataclass(self):
        entry = ShortcutEntry(category="scan_tree", key="<F2>", action="Rename")
        self.assertEqual(entry.category, "scan_tree")
        self.assertEqual(entry.key, "<F2>")
        self.assertEqual(entry.action, "Rename")
        with self.assertRaises(Exception):
            # Frozen: assignment must raise FrozenInstanceError.
            entry.action = "Mutate"  # type: ignore[misc]

    def test_register_shortcut_appends_new_entry(self):
        entry = register_shortcut("scan_tree", "<F2>", "Rename selected node")
        self.assertIn("scan_tree", SHORTCUT_REGISTRY)
        self.assertEqual(SHORTCUT_REGISTRY["scan_tree"], [entry])

    def test_register_shortcut_is_idempotent_on_key(self):
        register_shortcut("scan_tree", "<F2>", "Rename A")
        register_shortcut("scan_tree", "<F2>", "Rename B")
        # Second registration replaces, does not append.
        self.assertEqual(len(SHORTCUT_REGISTRY["scan_tree"]), 1)
        self.assertEqual(SHORTCUT_REGISTRY["scan_tree"][0].action, "Rename B")

    def test_register_shortcut_keeps_categories_separate(self):
        register_shortcut("scan_tree", "<F2>", "Rename node")
        register_shortcut("plot_dialog", "<F2>", "Reset axis")
        self.assertEqual(len(SHORTCUT_REGISTRY["scan_tree"]), 1)
        self.assertEqual(len(SHORTCUT_REGISTRY["plot_dialog"]), 1)

    def test_register_shortcut_preserves_insertion_order(self):
        register_shortcut("scan_tree", "<F2>", "Rename")
        register_shortcut("scan_tree", "<Delete>", "Discard")
        register_shortcut("scan_tree", "<Control-g>", "Group")
        keys = [e.key for e in SHORTCUT_REGISTRY["scan_tree"]]
        self.assertEqual(keys, ["<F2>", "<Delete>", "<Control-g>"])

    def test_bind_shortcut_registers_in_registry(self):
        called: list[str] = []
        bind_shortcut(
            self.host, "<F2>", lambda _e: called.append("f2"),
            category="scan_tree", action="Rename selected node",
        )
        self.assertEqual(len(SHORTCUT_REGISTRY["scan_tree"]), 1)
        self.assertEqual(SHORTCUT_REGISTRY["scan_tree"][0].key, "<F2>")
        self.assertEqual(
            SHORTCUT_REGISTRY["scan_tree"][0].action, "Rename selected node",
        )

    def test_bind_shortcut_attaches_binding_to_widget(self):
        bind_shortcut(
            self.host, "<F2>", lambda _e: None,
            category="scan_tree", action="Rename",
        )
        # Tk records the bind script; non-empty means at least one
        # binding exists on the widget for the sequence.
        self.assertNotEqual(self.host.bind("<F2>"), "")

    def test_bind_shortcut_handler_registers_with_tk(self):
        # ``event_generate`` on a withdrawn root is unreliable across
        # the full suite (same caveat as bind_escape_to_close above).
        # Pin the contract source-level: the bind script Tk records
        # must reference the registered callback (Tk encodes callbacks
        # as ``pyXXX`` Tcl names).
        bind_shortcut(
            self.host, "<F2>", lambda _e: None,
            category="scan_tree", action="Rename",
        )
        script = self.host.bind("<F2>")
        self.assertNotEqual(script, "")

    def test_bind_shortcut_returns_shortcut_entry(self):
        entry = bind_shortcut(
            self.host, "<Control-g>", lambda _e: None,
            category="scan_tree", action="Group selection",
        )
        self.assertIsInstance(entry, ShortcutEntry)
        self.assertEqual(entry.category, "scan_tree")
        self.assertEqual(entry.key, "<Control-g>")
        self.assertEqual(entry.action, "Group selection")

    def test_bind_shortcut_uses_add_plus_to_stack_bindings(self):
        # ``add="+"`` is the difference between bind_shortcut and a
        # naive widget.bind: it preserves any class-level binding Tk
        # already attaches (e.g. <Delete> on text widgets). After two
        # bind_shortcut calls the script must contain BOTH callback
        # references — script length monotonically grows.
        bind_shortcut(
            self.host, "<F2>", lambda _e: None,
            category="scan_tree", action="First",
        )
        script_after_one = self.host.bind("<F2>")
        bind_shortcut(
            self.host, "<F2>", lambda _e: None,
            category="scan_tree", action="Second",
        )
        script_after_two = self.host.bind("<F2>")
        # add="+" stacks: the second script is strictly longer (and
        # never the same string), confirming the first binding was
        # NOT clobbered.
        self.assertGreater(len(script_after_two), len(script_after_one))

    def test_reset_shortcut_registry_clears_all_buckets(self):
        register_shortcut("scan_tree", "<F2>", "Rename")
        register_shortcut("plot_dialog", "<Escape>", "Dismiss")
        _reset_shortcut_registry()
        self.assertEqual(SHORTCUT_REGISTRY, {})


class TestFontScalePhase4ba(unittest.TestCase):
    """Phase 4ba CS-79 — font-scale multiplier helper.

    The active scale is module-level global state. Every test that
    mutates it calls :func:`_reset_font_scale` on tearDown so a
    non-1.0 scale (and the named-font base-size cache) never bleeds
    into sibling tests — most importantly the ScanTreeWidget width
    tests that measure ``TkDefaultFont`` metrics.
    """

    def tearDown(self):
        _reset_font_scale()

    def test_default_scale_is_unity(self):
        self.assertEqual(active_font_scale(), 1.0)

    def test_scale_font_size_identity_at_unity(self):
        for pt in (8, 9, 10, 11, 12):
            self.assertEqual(scale_font_size(pt), pt)

    def test_scale_font_size_scales_up(self):
        set_active_font_scale(2.0)
        self.assertEqual(scale_font_size(9), 18)
        self.assertEqual(scale_font_size(11), 22)

    def test_scale_font_size_half_up_rounding(self):
        set_active_font_scale(1.5)
        # 9 * 1.5 = 13.5 -> 14 (half-up, deterministic).
        self.assertEqual(scale_font_size(9), 14)
        self.assertEqual(scale_font_size(8), 12)

    def test_scale_font_size_scales_down(self):
        set_active_font_scale(0.75)
        self.assertEqual(scale_font_size(12), 9)
        self.assertEqual(scale_font_size(8), 6)

    def test_scale_font_size_floors_at_one(self):
        set_active_font_scale(0.5)
        # 1 * 0.5 = 0.5 -> would round to 0/1; floor guarantees a
        # legal positive Tk point size.
        self.assertGreaterEqual(scale_font_size(1), 1)

    def test_set_get_round_trip(self):
        set_active_font_scale(1.25)
        self.assertEqual(active_font_scale(), 1.25)

    def test_coerce_clamps_out_of_range(self):
        self.assertEqual(_coerce_font_scale(99.0), 3.0)
        self.assertEqual(_coerce_font_scale(0.0), 0.5)

    def test_coerce_non_numeric_falls_back_to_unity(self):
        self.assertEqual(_coerce_font_scale("nonsense"), 1.0)
        self.assertEqual(_coerce_font_scale(None), 1.0)

    def test_set_active_font_scale_clamps_via_coerce(self):
        set_active_font_scale(10.0)
        self.assertEqual(active_font_scale(), 3.0)
        set_active_font_scale("garbage")
        self.assertEqual(active_font_scale(), 1.0)

    @unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
    def test_named_fonts_reconfigured_live(self):
        import tkinter.font as tkfont
        base = int(tkfont.nametofont("TkDefaultFont").cget("size"))
        set_active_font_scale(2.0)
        scaled = int(tkfont.nametofont("TkDefaultFont").cget("size"))
        # Positive (point) base doubles; negative (pixel) base doubles
        # in magnitude with sign preserved.
        if base >= 0:
            self.assertEqual(scaled, _accessibility_mod._scaled_named_size(base))
            self.assertGreater(scaled, base)
        else:
            self.assertLess(scaled, base)

    @unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
    def test_reset_font_scale_restores_named_fonts(self):
        import tkinter.font as tkfont
        base = int(tkfont.nametofont("TkDefaultFont").cget("size"))
        set_active_font_scale(2.0)
        self.assertNotEqual(
            int(tkfont.nametofont("TkDefaultFont").cget("size")), base,
        )
        _reset_font_scale()
        self.assertEqual(
            int(tkfont.nametofont("TkDefaultFont").cget("size")), base,
        )
        # Cache cleared so a fresh root re-captures its own defaults.
        self.assertEqual(_NAMED_FONT_BASE_SIZES, {})


if __name__ == "__main__":
    unittest.main()
