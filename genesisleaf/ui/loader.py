"""BusyOverlay - the loading animation.

A plain frame laid over the whole main window (no extra Toplevel, so it can
never float above other programs or get lost behind the main window) with a
ring of dots that spins while a pack loads.  It carries no progress numbers:
the parse runs on a worker thread and the overlay only says *that* work is
happening, which is all a load of a few seconds needs.

    overlay = BusyOverlay(root, "Loading", "pack.yaml")
    ...
    overlay.close()            # or overlay.fail("message")

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import math
import tkinter as tk

from genesisleaf.core.colors import mix
from genesisleaf.ui import theme as _theme
from genesisleaf.ui.fonts import FONT_UI_BIG, FONT_UI_SM

DOTS = 12           # dots in the ring
RADIUS = 22         # ring radius (px)
DOT_R = 3.6         # dot radius (px)
FRAME_MS = 70       # animation step


class BusyOverlay:
    """Spinner overlay over `parent` (normally the Tk root)."""

    def __init__(self, parent, title="Loading", detail=""):
        self.parent = parent
        self._head = 0
        self._job = None
        bg = _theme.TH_FRAME_BG
        self.frame = tk.Frame(parent, bg=bg, cursor="watch")
        self.frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.frame.lift()
        # swallow clicks so the half-built table underneath stays untouched
        for seq in ("<Button-1>", "<Button-3>", "<MouseWheel>"):
            self.frame.bind(seq, lambda e: "break")

        card = tk.Frame(self.frame, bg=_theme.TH_PANEL_BG,
                        highlightthickness=1,
                        highlightbackground=_theme.TH_BORDER)
        card.place(relx=0.5, rely=0.45, anchor="center")
        size = (RADIUS + DOT_R) * 2 + 8
        self.cv = tk.Canvas(card, width=size, height=size,
                            bg=_theme.TH_PANEL_BG, highlightthickness=0)
        self.cv.pack(padx=48, pady=(22, 8))
        self.title = tk.Label(card, text=title, font=FONT_UI_BIG,
                              bg=_theme.TH_PANEL_BG, fg=_theme.TH_FG)
        self.title.pack(padx=24)
        self.detail = tk.Label(card, text=detail, font=FONT_UI_SM,
                               bg=_theme.TH_PANEL_BG, fg=_theme.TH_FG_MUTED,
                               wraplength=320)
        self.detail.pack(padx=24, pady=(2, 20))

        c = size / 2.0
        self._dots = []
        for i in range(DOTS):
            a = 2 * math.pi * i / DOTS - math.pi / 2
            x, y = c + RADIUS * math.cos(a), c + RADIUS * math.sin(a)
            self._dots.append(self.cv.create_oval(
                x - DOT_R, y - DOT_R, x + DOT_R, y + DOT_R, outline=""))
        # tail colours: accent at the head fading into the panel colour
        self._ramp = [mix(_theme.TH_ACCENT, _theme.TH_PANEL_BG, t / float(DOTS))
                      for t in range(DOTS)]
        self._paint()
        self._job = self.frame.after(FRAME_MS, self._tick)
        self.pump()

    # -- animation --------------------------------------------------------
    def _paint(self):
        for i, dot in enumerate(self._dots):
            age = (self._head - i) % DOTS
            self.cv.itemconfigure(dot, fill=self._ramp[age])

    def _tick(self):
        self._job = None
        if not self.alive():
            return
        self._head = (self._head + 1) % DOTS
        self._paint()
        self._job = self.frame.after(FRAME_MS, self._tick)

    # -- API --------------------------------------------------------------
    def alive(self):
        try:
            return bool(self.frame.winfo_exists())
        except tk.TclError:
            return False

    def pump(self):
        """Repaint now - call between long synchronous steps on the Tk thread
        so the spinner does not look frozen."""
        if self.alive():
            try:
                self.frame.update_idletasks()
            except tk.TclError:
                pass

    def set_message(self, title=None, detail=None):
        if not self.alive():
            return
        if title is not None:
            self.title.configure(text=title)
        if detail is not None:
            self.detail.configure(text=detail)
        self.pump()

    def fail(self, message, linger_ms=2200):
        """Show the error in place, then go away."""
        if not self.alive():
            return
        self.set_message("Could not load", message)
        self.title.configure(fg=_theme.TH_BAD)
        if self._job is not None:
            self.frame.after_cancel(self._job)
            self._job = None
        self.frame.after(linger_ms, self.close)

    def close(self):
        if self._job is not None:
            try:
                self.frame.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        try:
            self.frame.destroy()
        except tk.TclError:
            pass
