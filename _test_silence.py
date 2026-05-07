"""Silence Tk messageboxes during test runs (Phase 4v).

Modal Tk dialogs (``messagebox.showinfo``, ``showerror``, ``askyesno``,
etc.) block the event loop until a user clicks. When tests exercise
apply-gesture error paths or the load-time mismatch dialog the
modals pop up and stall the run — particularly painful on CI or
when running locally and the developer has to manually click each
one.

Importing this module and calling ``silence_all_messageboxes()``
replaces every modal entry point on ``tkinter.messagebox`` with a
no-op (or a deterministic non-interactive return value). The
replacement is idempotent and persists for the lifetime of the
Python process — call once at test-module load time.

Per-test ``mock.patch`` (used in some legacy tests) still works on
top of this; the patch's ``__exit__`` restores the silenced no-op
which is functionally identical to the real modal absent any
clicks.
"""

from __future__ import annotations

import tkinter.messagebox as _mb


_SILENCED = False


def silence_all_messageboxes() -> None:
    """Replace every Tk messagebox primitive with a no-op.

    * ``showinfo`` / ``showwarning`` / ``showerror`` -> return None
    * ``askyesno`` / ``askretrycancel`` / ``askyesnocancel`` -> False
      (the conservative "do nothing destructive" answer)
    * ``askokcancel`` -> True (treats as confirmation accepted)
    * ``askquestion`` -> "no"
    """
    global _SILENCED
    if _SILENCED:
        return
    _mb.showinfo       = lambda *a, **kw: None
    _mb.showwarning    = lambda *a, **kw: None
    _mb.showerror      = lambda *a, **kw: None
    _mb.askyesno       = lambda *a, **kw: False
    _mb.askretrycancel = lambda *a, **kw: False
    _mb.askyesnocancel = lambda *a, **kw: False
    _mb.askokcancel    = lambda *a, **kw: True
    _mb.askquestion    = lambda *a, **kw: "no"
    _SILENCED = True
