"""Secondary view windows: open, list, close.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import messagebox

from genesisleaf.ui.windows.view import ViewWindow


class ViewsMixin:
    """Secondary view windows: open, list, close.

    Mixed into `App`; `self` is the main window.
    """

    # -- close --------------------------------------------------------------------------
    def open_new_view(self):
        """Open another window onto the pack already loaded.

        Refuses while the file picker is open or when nothing is loaded yet -
        a view of an empty pack is just an empty window, and one opened during
        a load would show half a file."""
        if not getattr(self, "pack", None) or not self.pack.flat:
            messagebox.showinfo("New view",
                                "Open a pack first.")
            return
        v = ViewWindow(self)
        self._views.append(v)
        self._refresh_views_menu()
        self.update_status()
        return v

    def _refresh_views_menu(self):
        """Rebuild the 'Close a view' list in place.

        The menu is the only handle on a secondary window - there is no other
        way back to it once you have switched away - so it has to track the
        live list rather than being built once."""
        m = getattr(self, "views_menu", None)
        if m is None:
            return
        m.delete(0, "end")
        if not self._views:
            m.add_command(label="(none open)", state="disabled")
            return
        for n, v in enumerate(self._views, 1):
            row = v.current + 1 if 0 <= v.current < len(self.pack.flat) else 0
            m.add_command(
                label="View %d%s" % (n, ("  (row %d)" % row) if row else ""),
                command=lambda vv=v: vv.close())

    def _close_all_views(self):
        for v in list(self._views):
            try:
                v.win.destroy()
            except tk.TclError:
                pass
        self._views = []
        self._refresh_views_menu()
