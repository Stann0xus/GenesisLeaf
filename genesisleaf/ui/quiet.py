"""Skip `configure()` options that already hold the requested value.

Every Tk configure queues a redisplay (and, for a Text's `height`, a geometry
pass) even when nothing changed.  Selecting a row re-sets a dozen labels and
editor sizes, most to the value they already have, so the repaint that follows
redraws and re-lays-out widgets for no visible reason.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

_installed = False


def _quiet(cls):
    original = cls.configure

    def configure(self, cnf=None, **kw):
        if cnf is None and kw:
            try:
                kw = {key: value for key, value in kw.items()
                      if str(self.cget(key)) != str(value)}
            except tk.TclError:
                pass                    # unknown option: let Tk report it
            if not kw:
                return None
        return original(self, cnf, **kw)

    configure.__doc__ = original.__doc__
    cls.configure = cls.config = configure


def install():
    global _installed
    if _installed:
        return
    _installed = True
    for cls in (ttk.Label, ttk.Progressbar, tk.Label, tk.Text):
        _quiet(cls)
