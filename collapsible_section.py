"""Collapsible left-pane section widget (Phase 4j, CS-21).

A reusable show/hide wrapper for an arbitrary block of widgets. Used
by ``uvvis_tab._build_left_panel`` to wrap the five operation
sections (Baseline / Normalisation / Smoothing / Peak picking /
Second derivative) so users can hide the panels they are not
currently using and reclaim vertical space on the left pane.

Pure widget — no graph, no operation, no plotting knowledge. The
section is two stacked frames:

* a clickable header strip showing ``"▶ Title"`` (collapsed) or
  ``"▼ Title"`` (expanded);
* a body frame, exposed via the :attr:`body` property, into which the
  caller adds the section's content. When the section is collapsed
  the body is ``pack_forget``-en; the body's children stay packed
  inside it so re-expanding restores the previous layout exactly.

Default state is **collapsed** (locked decision at end of Phase 4i).
Per-section state is held in a ``tk.BooleanVar`` owned by the widget
and is **not** persisted to project files this phase — that is a
Phase 8 concern (project save / load).

Usage::

    section = CollapsibleSection(parent, title="Smoothing")
    section.pack(fill=tk.X)
    # add widgets to section.body, not to parent:
    tk.Label(section.body, text="Mode:").pack(anchor="w")
    # to drive from tests:
    section.expand()
    section.collapse()
    section.toggle()
    section.is_expanded()  # -> bool
"""

from __future__ import annotations

from typing import Optional

import tkinter as tk


__all__ = [
    "CollapsibleSection",
]


# Glyphs used in the header label. Tuple form pinned by the test
# module so visual changes here become deliberate.
_GLYPH_COLLAPSED = "▶"
_GLYPH_EXPANDED  = "▼"


class CollapsibleSection(tk.Frame):
    """Header + body composite where the body's visibility toggles."""

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        *,
        expanded: bool = False,
        body_padx: int = 0,
        body_pady: int = 0,
    ) -> None:
        super().__init__(parent)
        self._title = title

        # Per-section state. Owned by the widget; tests can read but
        # callers should drive state via expand / collapse / toggle.
        self._expanded = tk.BooleanVar(value=bool(expanded))

        # Header strip — single full-width clickable Label. Putting
        # the chevron and the title in the same Label means a click
        # anywhere on the strip toggles the section, no double-click
        # required and no separate expand button.
        self._header = tk.Label(
            self,
            text=self._header_text(),
            anchor="w",
            font=("", 9, "bold"),
            cursor="hand2",
            padx=4,
            pady=2,
        )
        self._header.pack(fill=tk.X)
        self._header.bind("<Button-1>", self._on_header_click)

        # Body frame — caller's content goes here. Pack-forgotten when
        # collapsed; re-packed below the header when expanded. Storing
        # the pack arguments so re-expansion restores the exact layout.
        self._body = tk.Frame(self)
        self._body_padx = body_padx
        self._body_pady = body_pady

        # Apply initial visibility now that both halves are built.
        self._refresh_visibility()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def body(self) -> tk.Frame:
        """The frame into which callers should pack their content."""
        return self._body

    @property
    def title(self) -> str:
        return self._title

    def is_expanded(self) -> bool:
        return bool(self._expanded.get())

    def expand(self) -> None:
        if not self._expanded.get():
            self._expanded.set(True)
            self._refresh_visibility()

    def collapse(self) -> None:
        if self._expanded.get():
            self._expanded.set(False)
            self._refresh_visibility()

    def toggle(self) -> None:
        self._expanded.set(not self._expanded.get())
        self._refresh_visibility()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _header_text(self) -> str:
        glyph = _GLYPH_EXPANDED if self._expanded.get() else _GLYPH_COLLAPSED
        return f"{glyph} {self._title}"

    def _refresh_visibility(self) -> None:
        # Chevron always reflects the current state.
        self._header.configure(text=self._header_text())
        if self._expanded.get():
            # Pack the body below the header. ``after=self._header``
            # keeps order deterministic if the parent contains other
            # siblings packed after this section.
            self._body.pack(
                fill=tk.X,
                padx=self._body_padx,
                pady=self._body_pady,
                after=self._header,
            )
        else:
            self._body.pack_forget()

    def _on_header_click(self, _event: Optional[tk.Event] = None) -> None:
        self.toggle()
