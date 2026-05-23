"""Accessibility helpers shared across the dialog modules (Phase 4ax, CS-76).

Created in Phase 4ax as the first sub-batch of the CS-75 accessibility
umbrella scope. Hosts cross-axis helpers that every dialog calls
through so the recipe is captured in exactly one place:

* :func:`bind_escape_to_close` — CS-75 D3 Escape-dismiss audit recipe.
  Binds ``<Escape>`` on a ``tk.Toplevel`` to its canonical
  close/cancel handler and returns ``"break"`` to prevent default Tk
  propagation. Sub-batch 4ax wires this onto the three CS-75 D3
  scope dialogs (``NodeStylesDialog`` / ``PlotConfigDialog`` /
  ``StyleDialog``); further Toplevels remain inventoried as
  carry-forward.
* :func:`attach_shortcut_tooltip` — CS-75 D6 Tooltip-only
  discoverability convention. Thin delegate over
  :class:`tooltip.Tooltip` (CS-42) so call-sites read intent
  (a shortcut hint) rather than the generic Tooltip constructor.

Phase 4ay adds ``active_palette()`` (sub-axis B) — palette-aware
getter that ``pick_default_color`` will consult internally. Phase
4ba adds ``scale_font_size(base_pt)`` (sub-axis D) — the font-scale
helper that every dialog font literal eventually routes through.
Each helper is the recipe-canonical entry point; every
implementation goes through it rather than re-deriving the gesture
or constant locally.
"""

from __future__ import annotations

from typing import Callable

import tkinter as tk

from tooltip import Tooltip


def bind_escape_to_close(
    toplevel: tk.Toplevel,
    handler: Callable[[], object],
) -> Callable[[tk.Event | None], str]:
    """Bind ``<Escape>`` on ``toplevel`` to ``handler``.

    The bound callback invokes ``handler()`` and returns ``"break"``
    so Tk does not propagate the event further. ``handler`` typically
    is the dialog's ``_on_close_requested`` method (the same callable
    that ``WM_DELETE_WINDOW`` routes through); the result of
    ``handler()`` is ignored.

    Returns the bound callback so tests can invoke it deterministically
    — ``event_generate`` on transient/withdrawn Toplevels is
    unreliable across the full test suite (the same caveat documented
    in ``test_plot_settings_dialog`` and ``test_collapsible_section``).
    Production callers ignore the return value.

    Phase 4ax CS-75 D3 recipe.
    """
    def _on_escape(_event: tk.Event | None = None) -> str:
        handler()
        return "break"

    toplevel.bind("<Escape>", _on_escape)
    return _on_escape


def attach_shortcut_tooltip(widget: tk.Widget, text: str) -> Tooltip:
    """Attach a CS-42 :class:`Tooltip` to ``widget`` describing a
    keyboard shortcut.

    Thin delegate over :class:`tooltip.Tooltip` so the call-site reads
    as discoverability intent (CS-75 D6 — Tooltip-only convention).
    Returns the constructed Tooltip so callers can rotate the text
    later via ``Tooltip.update_text``.

    Phase 4ax CS-75 D6 recipe.
    """
    return Tooltip(widget, text)
