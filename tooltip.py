"""Lightweight hover tooltip for arbitrary Tk widgets.

Originally co-located in ``scan_tree_widget.py`` as the private
``_Tooltip`` (Phase 4q CS-33) where it surfaced full node labels under
``_truncate_label``. Promoted to its own module in Phase 4t (CS-42) on
its first cross-module re-use:

* ``uvvis_tab.UVVisTab`` attaches it to the "Floor at zero"
  Checkbutton; the tooltip text rotates between the empty string
  (when the toggle is enabled — no hint needed) and an explanatory
  hint (when the toggle is disabled because the current baseline
  mode hasn't shipped its constrained-fit code path).
* ``scan_tree_widget`` continues to attach it to truncated labels
  AND to the per-row ``[~]`` baseline-curve toggle introduced in
  CS-36 (Phase 4r friction #1).

Behaviour: ``<Enter>`` schedules a 600 ms ``after`` callback that
opens a borderless ``tk.Toplevel`` containing the tooltip text;
``<Leave>`` and ``<ButtonPress>`` both cancel/destroy. Single-instance
per widget — the binding triple is ``add="+"`` so attaching does not
conflict with widget-owner bindings. ``update_text`` rotates the
tooltip text in place; passing the empty string makes ``_show`` bail
silently so a "tooltip-only-when-relevant" pattern works without
recreating the Tooltip.
"""

from __future__ import annotations

import tkinter as tk


class Tooltip:
    """Lightweight hover tooltip for a Tk widget.

    Construct once per widget. ``text`` may be the empty string at
    construction time and rotated later via :meth:`update_text` — the
    tooltip Toplevel only opens when ``_show`` is reached AND the
    text is truthy, so an empty string is the canonical "do not show"
    sentinel.
    """

    DELAY_MS: int = 600

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>",      self._schedule, add="+")
        widget.bind("<Leave>",      self._hide,     add="+")
        widget.bind("<ButtonPress>", self._hide,    add="+")

    def update_text(self, text: str) -> None:
        self._text = text

    def _schedule(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        try:
            self._after_id = self._widget.after(self.DELAY_MS, self._show)
        except tk.TclError:
            self._after_id = None

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except (tk.TclError, ValueError):
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._tip is not None or not self._text:
            return
        try:
            x = self._widget.winfo_rootx() + 12
            y = (self._widget.winfo_rooty()
                 + self._widget.winfo_height() + 4)
            tip = tk.Toplevel(self._widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tip, text=self._text,
                bg="#FFFFE0", relief=tk.SOLID, bd=1,
                justify="left", padx=4, pady=2,
            ).pack()
            self._tip = tip
        except tk.TclError:
            self._tip = None

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None
