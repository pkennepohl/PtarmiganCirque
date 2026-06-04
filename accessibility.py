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

Phase 4ay (sub-axis B) lands the colour-blind palette opt-in. The
``active_palette()`` getter + ``set_active_palette(name)`` setter
live in :mod:`node_styles` (alongside :data:`SPECTRUM_PALETTE`)
rather than here — keeping :mod:`node_styles` as a pure data layer
without a tkinter dependency, while preserving the CS-75 convention
that every accessibility helper has a single recipe-canonical home.

Phase 4az (sub-axis C, CS-78) lands the keyboard-shortcut registry +
binding recipe. Three new pieces:

* :class:`ShortcutEntry` — frozen dataclass capturing one registered
  gesture (``category``, ``key``, ``action``). ``key`` is the Tk
  binding string (``"<F2>"`` / ``"<Control-g>"`` /
  ``"<Control-Shift-G>"`` / …); ``action`` is the short
  user-facing description rendered in the Accessibility tab's
  "Keyboard shortcuts" table and in ``KEYBINDINGS.md``.
* :data:`SHORTCUT_REGISTRY` — module-level dict keyed by category
  (``"scan_tree"`` / ``"plot_dialog"`` / …) holding the list of
  :class:`ShortcutEntry` records. Source of truth for the
  Accessibility-tab table and for the source-level sentinel that
  pins parity with the ``KEYBINDINGS.md`` sister doc.
* :func:`bind_shortcut` — the recipe-canonical binding entry point.
  Calls ``widget.bind(key, handler, add="+")`` AND registers via
  :func:`register_shortcut` so the binding and the discoverability
  table cannot drift. ``add="+"`` makes the binding stack with any
  Tk class-level binding (relevant for ``<Delete>`` / arrow keys
  on text widgets). Returns the :class:`ShortcutEntry`.

Note: :func:`bind_shortcut` does NOT call
:func:`attach_shortcut_tooltip`. The Phase 4az first batch binds on
tree-level container widgets (``ScanTreeWidget`` itself) for which
a hover Tooltip has no natural trigger surface — the canonical
discoverability surface for those gestures is the
Accessibility-tab "Keyboard shortcuts" table fed from
:data:`SHORTCUT_REGISTRY`. Future sub-batches that bind on discrete
shortcut-bearing widgets (buttons, comboboxes — Phase 4ax
``NodeStylesDialog`` Tooltip precedent) should still wire
``attach_shortcut_tooltip`` alongside ``bind_shortcut`` so per-widget
hover discoverability stays intact (CS-75 D6 — additive sub-clause,
not a relaxation: D6 still locks Tooltip-only discoverability for
widgets that DO have a hover surface).

Phase 4ba adds ``scale_font_size(base_pt)`` (sub-axis D) — the
font-scale helper that every dialog font literal eventually routes
through; that one DOES live in this module because the call sites
all already import tkinter. Each helper is the recipe-canonical
entry point; every implementation goes through it rather than
re-deriving the gesture or constant locally.
"""

from __future__ import annotations

from dataclasses import dataclass
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


# ---------------------------------------------------------------------
# Phase 4az (sub-axis C, CS-78) — keyboard-shortcut registry + bind recipe.
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class ShortcutEntry:
    """A single registered keyboard shortcut.

    ``category`` groups entries by surface (``"scan_tree"`` /
    ``"plot_dialog"`` / …) so the Accessibility-tab table and
    ``KEYBINDINGS.md`` can section the listing. ``key`` is the Tk
    binding string (``"<F2>"`` / ``"<Control-g>"`` /
    ``"<Control-Shift-G>"`` / …). ``action`` is the short
    user-facing description.

    Phase 4az CS-78 recipe.
    """
    category: str
    key: str
    action: str


SHORTCUT_REGISTRY: dict[str, list[ShortcutEntry]] = {}
"""Module-level keyboard-shortcut registry (Phase 4az CS-78).

Mapping ``category -> [ShortcutEntry, ...]``. Populated by
:func:`register_shortcut` (typically via :func:`bind_shortcut` at
widget construction time). Read by the PlotConfigDialog
Accessibility-tab "Keyboard shortcuts" LabelFrame and by the
``KEYBINDINGS.md`` source-level parity sentinel.

The registry is idempotent on the ``(category, key)`` pair —
re-registering the same key in the same category replaces the
existing entry rather than appending, so multiple instances of the
same widget (e.g. across the test suite) do not bloat the list.
Tests that need a clean baseline call
:func:`_reset_shortcut_registry`.
"""


def register_shortcut(
    category: str, key: str, action: str,
) -> ShortcutEntry:
    """Register (or replace) a keyboard shortcut in :data:`SHORTCUT_REGISTRY`.

    Idempotent on ``(category, key)``: re-registering replaces the
    existing entry rather than appending. Returns the
    :class:`ShortcutEntry` actually stored.

    Phase 4az CS-78 recipe.
    """
    entry = ShortcutEntry(category=category, key=key, action=action)
    bucket = SHORTCUT_REGISTRY.setdefault(category, [])
    for i, existing in enumerate(bucket):
        if existing.key == key:
            bucket[i] = entry
            return entry
    bucket.append(entry)
    return entry


def bind_shortcut(
    widget: tk.Widget,
    key: str,
    handler: Callable[[tk.Event], object],
    *,
    category: str,
    action: str,
) -> ShortcutEntry:
    """Bind ``key`` on ``widget`` to ``handler`` AND register it.

    Recipe-canonical entry point for Phase 4az CS-78 keyboard
    shortcuts. Combines two steps so the binding and the
    discoverability registry cannot drift:

    1. ``widget.bind(key, handler, add="+")`` — ``add="+"``
       guarantees the binding stacks with anything Tk's class
       bindings already attach to the key (mostly relevant for
       ``<Delete>`` / arrow keys on text widgets).
    2. :func:`register_shortcut` — append (or replace) the
       :class:`ShortcutEntry` in :data:`SHORTCUT_REGISTRY` so the
       Accessibility-tab table picks it up.

    ``handler`` receives the Tk event as its single argument
    (standard ``widget.bind`` signature). Returning ``"break"``
    from ``handler`` halts propagation; this helper does NOT wrap
    the return — that's the caller's responsibility per gesture.

    Phase 4az CS-78 recipe.
    """
    widget.bind(key, handler, add="+")
    return register_shortcut(category, key, action)


def _reset_shortcut_registry() -> None:
    """Clear :data:`SHORTCUT_REGISTRY` — test-only.

    Production code never calls this; the registry accretes for the
    process lifetime and idempotent :func:`register_shortcut` keeps
    it bounded. Tests that need a clean baseline call this before
    their setUp.

    Phase 4az CS-78 recipe.
    """
    SHORTCUT_REGISTRY.clear()


# ---------------------------------------------------------------------
# Phase 4ba (sub-axis D, CS-79) — font-scale multiplier.
# ---------------------------------------------------------------------
#
# Two complementary mechanisms make one Accessibility-tab control
# rescale the whole UI:
#
# 1. :func:`scale_font_size` — every explicit ``font=("", N, ...)``
#    literal across the dialog modules routes its size ``N`` through
#    this helper. Those widgets pick up the new scale on their NEXT
#    construction (e.g. when a dialog is reopened), because a Tk font
#    tuple is evaluated once at widget-creation time.
# 2. :func:`set_active_font_scale` ALSO reconfigures the standard Tk
#    named fonts (``TkDefaultFont`` et al). Widgets that render with
#    the platform default font — i.e. those WITHOUT an explicit
#    ``font=`` literal, notably the :class:`scan_tree_widget.ScanTreeWidget`
#    sidebar rows, which read ``TkDefaultFont`` via
#    ``tkfont.nametofont`` — rescale INSTANTLY when the control moves.
#
# The split is deliberate: a full live re-render of already-built
# explicit-font widgets would require tearing down and rebuilding
# every open dialog, which is out of scope here. 1.0 is the factory
# default and a visual no-op, so the literal-routing bulk pass is safe.

# Standard Tk named fonts reconfigured live by
# :func:`set_active_font_scale`.
_NAMED_FONTS: tuple[str, ...] = (
    "TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont",
    "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont",
    "TkIconFont", "TkTooltipFont",
)

# Base (scale-1.0) sizes captured lazily the first time a named font is
# reconfigured. Keyed by font name. Cleared by :func:`_reset_font_scale`
# (test-only) so a fresh Tk root re-captures its own defaults rather
# than inheriting a stale base from a destroyed root.
_NAMED_FONT_BASE_SIZES: dict[str, int] = {}

# Active font-scale multiplier. Process-lifetime mutable; updated by
# :func:`set_active_font_scale` from the dialog's commit-on-change path
# and from binah.py's project-load path. 1.0 is the factory default and
# a visual no-op.
_active_font_scale: float = 1.0

# Defensive bounds. The Accessibility-tab control offers 0.75–2.0; the
# wider clamp tolerates a value written by a future app version without
# letting a pathological multiplier wreck the UI.
_FONT_SCALE_MIN: float = 0.5
_FONT_SCALE_MAX: float = 3.0


def _coerce_font_scale(value: object) -> float:
    """Clamp ``value`` into the valid font-scale band; fall back to 1.0.

    Non-numeric input falls back to ``1.0`` silently — mirrors
    :func:`node_styles.set_active_palette`'s defensive fallback, since
    the load path may surface a value written by a future app version
    and the UI should keep rendering rather than crash.

    Phase 4ba CS-79 recipe.
    """
    try:
        scale = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0
    if scale < _FONT_SCALE_MIN:
        return _FONT_SCALE_MIN
    if scale > _FONT_SCALE_MAX:
        return _FONT_SCALE_MAX
    return scale


def active_font_scale() -> float:
    """Return the active font-scale multiplier (default ``1.0``).

    Phase 4ba CS-79 recipe.
    """
    return _active_font_scale


def scale_font_size(base_pt: int) -> int:
    """Scale a point size by the active multiplier (Phase 4ba CS-79).

    The recipe-canonical entry point every explicit ``font=("", N, ...)``
    literal routes its size ``N`` through, so one Accessibility-tab
    control rescales the dialog chrome. Identity when the scale is
    ``1.0`` (the factory default), which is why the bulk routing pass
    is a visual no-op until the user opts in. Half-up rounding keeps
    the result deterministic; the floor of ``1`` guarantees a legal
    (positive) Tk point size even for a small base at a small
    multiplier.
    """
    scaled = int(base_pt * _active_font_scale + 0.5)
    return scaled if scaled >= 1 else 1


def _scaled_named_size(base: int) -> int:
    """Scale a *named-font* base size, preserving Tk's sign convention.

    Tk font sizes are points when positive and pixels when negative.
    The multiplier preserves the sign so a pixel-specified named font
    stays pixel-specified; magnitude is floored at 1.
    """
    if base < 0:
        scaled = -int(-base * _active_font_scale + 0.5)
        return scaled if scaled <= -1 else -1
    scaled = int(base * _active_font_scale + 0.5)
    return scaled if scaled >= 1 else 1


def _apply_scale_to_named_fonts() -> None:
    """Reconfigure the standard Tk named fonts to the active scale.

    Captures each font's scale-1.0 base size on first contact. Silently
    no-ops when no Tk root exists yet (e.g. called at import time or in
    a headless context); the next call after a root is created applies
    the scale.
    """
    try:
        import tkinter.font as tkfont
    except Exception:
        return
    for name in _NAMED_FONTS:
        try:
            font = tkfont.nametofont(name)
        except Exception:
            # No Tk root yet, or this platform lacks the named font.
            continue
        base = _NAMED_FONT_BASE_SIZES.get(name)
        if base is None:
            try:
                base = int(font.cget("size"))
            except Exception:
                continue
            _NAMED_FONT_BASE_SIZES[name] = base
        try:
            font.configure(size=_scaled_named_size(base))
        except Exception:
            continue


def set_active_font_scale(value: object) -> None:
    """Set the active font-scale multiplier and live-reconfigure named fonts.

    ``value`` is coerced/clamped by :func:`_coerce_font_scale`. After
    storing it, the standard Tk named fonts are reconfigured so every
    widget using the platform default font (no explicit ``font=``
    literal — notably ScanTreeWidget sidebar rows) rescales instantly.
    Widgets built with explicit ``font=("", N, ...)`` literals rescale
    on their next construction via :func:`scale_font_size`.

    Phase 4ba CS-79 recipe.
    """
    global _active_font_scale
    _active_font_scale = _coerce_font_scale(value)
    _apply_scale_to_named_fonts()


def _reset_font_scale() -> None:
    """Reset scale to 1.0, restore named fonts, drop the base cache — test-only.

    Production code never calls this. Tests that exercise a non-1.0
    scale call it in tearDown so global Tk named-font state (and the
    base-size cache, which is tied to a specific Tk root) does not
    bleed into sibling tests — particularly the ScanTreeWidget width
    tests that measure ``TkDefaultFont`` metrics.

    Phase 4ba CS-79 recipe.
    """
    global _active_font_scale
    _active_font_scale = 1.0
    _apply_scale_to_named_fonts()  # restores fonts to captured base sizes
    _NAMED_FONT_BASE_SIZES.clear()
