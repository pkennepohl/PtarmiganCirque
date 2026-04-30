"""Tests for collapsible_section.py (Phase 4j, CS-21).

The widget is GUI code; we construct a real ``tk.Tk`` root and call
``update_idletasks`` between mutations to flush pending geometry
work. Headless environments are skipped via ``unittest.skipUnless``.

Coverage:

* default state is collapsed (header glyph + body unpacked)
* explicit expanded=True at construction renders with body packed
* clicking the header toggles visibility
* expand / collapse / toggle / is_expanded public API
* the body's children are preserved across collapse → expand
* the chevron glyph swaps with state
* the body property exposes a real ``tk.Frame`` instance
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


from collapsible_section import CollapsibleSection


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestDefaultState(unittest.TestCase):

    def setUp(self):
        self.host = tk.Frame(_root)
        self.section = CollapsibleSection(self.host, title="Smoothing")
        self.section.pack(fill=tk.X)
        self.section.update_idletasks()

    def tearDown(self):
        try:
            self.section.destroy()
        except Exception:
            pass
        try:
            self.host.destroy()
        except Exception:
            pass

    def test_default_is_collapsed(self):
        # Locked decision at end of Phase 4i: every section starts
        # collapsed. The body must NOT be on the parent's pack-slave
        # list immediately after construction.
        self.assertFalse(self.section.is_expanded())
        self.assertNotIn(self.section.body, self.section.pack_slaves())

    def test_collapsed_header_uses_right_chevron(self):
        # ▶ for collapsed (head pointing right; "click to open").
        text = self.section._header.cget("text")
        self.assertTrue(text.startswith("▶ "), text)
        self.assertIn("Smoothing", text)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestExpandedAtConstruction(unittest.TestCase):

    def test_expanded_kwarg_renders_with_body_packed(self):
        host = tk.Frame(_root)
        try:
            section = CollapsibleSection(
                host, title="Baseline", expanded=True)
            section.pack(fill=tk.X)
            section.update_idletasks()
            self.assertTrue(section.is_expanded())
            self.assertIn(section.body, section.pack_slaves())
            self.assertTrue(
                section._header.cget("text").startswith("▼ "))
        finally:
            host.destroy()


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestPublicAPI(unittest.TestCase):

    def setUp(self):
        self.host = tk.Frame(_root)
        self.section = CollapsibleSection(self.host, title="Norm")
        self.section.pack(fill=tk.X)
        self.section.update_idletasks()

    def tearDown(self):
        self.host.destroy()

    def test_expand_packs_the_body(self):
        self.section.expand()
        self.section.update_idletasks()
        self.assertTrue(self.section.is_expanded())
        self.assertIn(self.section.body, self.section.pack_slaves())

    def test_collapse_unpacks_the_body(self):
        self.section.expand()
        self.section.update_idletasks()
        self.section.collapse()
        self.section.update_idletasks()
        self.assertFalse(self.section.is_expanded())
        self.assertNotIn(self.section.body, self.section.pack_slaves())

    def test_toggle_flips_state(self):
        self.assertFalse(self.section.is_expanded())
        self.section.toggle()
        self.section.update_idletasks()
        self.assertTrue(self.section.is_expanded())
        self.section.toggle()
        self.section.update_idletasks()
        self.assertFalse(self.section.is_expanded())

    def test_expand_when_already_expanded_is_noop(self):
        self.section.expand()
        self.section.update_idletasks()
        # Calling again does not raise and state stays True.
        self.section.expand()
        self.assertTrue(self.section.is_expanded())

    def test_collapse_when_already_collapsed_is_noop(self):
        self.section.collapse()
        self.assertFalse(self.section.is_expanded())

    def test_chevron_swaps_on_state_change(self):
        self.section.expand()
        self.section.update_idletasks()
        self.assertTrue(
            self.section._header.cget("text").startswith("▼ "))
        self.section.collapse()
        self.section.update_idletasks()
        self.assertTrue(
            self.section._header.cget("text").startswith("▶ "))

    def test_body_property_returns_a_frame(self):
        self.assertIsInstance(self.section.body, tk.Frame)


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestHeaderClickToggles(unittest.TestCase):

    def setUp(self):
        self.host = tk.Frame(_root)
        self.section = CollapsibleSection(self.host, title="Peaks")
        self.section.pack(fill=tk.X)
        self.section.update_idletasks()

    def tearDown(self):
        self.host.destroy()

    def test_button_1_binding_is_registered_on_header(self):
        # The header strip itself must carry a <Button-1> binding —
        # not a sibling, not the body. This pins the contract that a
        # click anywhere on the header toggles the section.
        bindings = self.section._header.bind()
        self.assertIn("<Button-1>", bindings)

    def test_button_1_on_header_toggles_via_handler(self):
        # event_generate on a withdrawn root is unreliable for mouse
        # buttons, so we exercise the handler directly. This is the
        # path the binding ultimately calls.
        self.assertFalse(self.section.is_expanded())
        self.section._on_header_click(None)
        self.section.update_idletasks()
        self.assertTrue(self.section.is_expanded())
        self.section._on_header_click(None)
        self.section.update_idletasks()
        self.assertFalse(self.section.is_expanded())


@unittest.skipUnless(_HAS_DISPLAY, "Tk display not available")
class TestBodyChildPersistence(unittest.TestCase):

    def test_children_survive_a_collapse_expand_cycle(self):
        host = tk.Frame(_root)
        try:
            section = CollapsibleSection(host, title="X")
            section.pack(fill=tk.X)
            # Add three labels into the body. The widget's contract
            # is that the body's pack-slave list stays intact across a
            # collapse → expand round trip; only the body itself is
            # pack_forgotten on the section, the children stay on the
            # body.
            labels = []
            for i, t in enumerate(("a", "b", "c")):
                lbl = tk.Label(section.body, text=t)
                lbl.pack(anchor="w")
                labels.append(lbl)
            section.update_idletasks()

            section.expand()
            section.update_idletasks()
            self.assertEqual(
                section.body.pack_slaves(), labels)

            section.collapse()
            section.update_idletasks()
            # Children are still on the body even though the body is
            # off-screen.
            self.assertEqual(
                section.body.pack_slaves(), labels)

            section.expand()
            section.update_idletasks()
            self.assertEqual(
                section.body.pack_slaves(), labels)
        finally:
            host.destroy()


if __name__ == "__main__":
    unittest.main()
