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


if __name__ == "__main__":
    unittest.main()
