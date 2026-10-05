"""One window's menu bar, native or in the game's tab-plaque look.

Windows draws a native menu bar that no palette or image can touch, so in the
menu UI the bar is a row of carved-brown plaques (the game's own tab banner)
that drop the very same ``tk.Menu`` cascades.  With the menu UI off the native
bar comes back.  The menus themselves are built once by their owner; this
class only decides how they are presented.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

from tkinter import ttk

from genesisleaf.ui import theme as _theme


class Menubar:
    def __init__(self, win, menu):
        self.win = win
        self.menu = menu            # the tk.Menu whose cascades are the bar
        self.bar = None
        self.sync()

    def _cascades(self):
        last = self.menu.index("end")
        if last is None:
            return
        for i in range(last + 1):
            if self.menu.type(i) == "cascade":
                label = self.menu.entrycget(i, "label")
                yield label, self.win.nametowidget(self.menu.entrycget(i, "menu"))

    def _drop(self, button, sub):
        # post the menu under its plaque; Tk grabs input until it closes
        x = button.winfo_rootx()
        y = button.winfo_rooty() + button.winfo_height()
        try:
            sub.tk_popup(x, y)
        finally:
            sub.grab_release()

    def sync(self):
        """Show the bar that matches the current UI style."""
        if _theme.MENU_UI:
            self.win.configure(menu="")
            if self.bar is None:
                self.bar = ttk.Frame(self.win, style="Menubar.TFrame",
                                     padding=(6, 4, 6, 0))
                for label, sub in self._cascades():
                    b = ttk.Button(self.bar, text=label, takefocus=False,
                                   style="Menubar.TButton")
                    b.configure(command=lambda b=b, s=sub: self._drop(b, s))
                    b.pack(side="left", padx=(0, 4))
            if not self.bar.winfo_ismapped():
                slaves = [w for w in self.win.pack_slaves() if w is not self.bar]
                if slaves:
                    self.bar.pack(side="top", fill="x", before=slaves[0])
                else:
                    self.bar.pack(side="top", fill="x")
        else:
            if self.bar is not None:
                self.bar.destroy()
                self.bar = None
            self.win.configure(menu=self.menu)
