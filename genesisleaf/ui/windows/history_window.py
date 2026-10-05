"""Edit > History window (read-only view of the undo stack).

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import time
import tkinter as tk
from tkinter import ttk

from genesisleaf.ui.fonts import FONT_UI_SM
from genesisleaf.ui import theme as _theme


class HistoryWindow:
    """Edit ▸ History: the undo stack, newest first, with the redo branch shown
    greyed below it.  Read-only on purpose - a history you can click is a
    history that can desync, and Ctrl+Z / Ctrl+Shift+Z already do the job."""

    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("Edit history")
        self.win.geometry("460x420")
        self.lab = tk.Label(self.win, text="", anchor="w",
                            font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED)
        self.lab.pack(side="top", fill="x", padx=8, pady=(8, 4))
        wrap = ttk.Frame(self.win)
        wrap.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 8))
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(wrap, columns=("n", "when", "what"),
                                 show="headings", selectmode="browse")
        for col, txt, w in (("n", "#", 46), ("when", "Time", 80),
                            ("what", "Step", 280)):
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="w",
                             stretch=(col == "what"))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        btns = ttk.Frame(self.win, padding=(8, 0, 8, 8))
        btns.pack(side="bottom", fill="x")
        ttk.Button(btns, text="Undo", command=app.do_undo).pack(side="left")
        ttk.Button(btns, text="Redo", command=app.do_redo).pack(
            side="left", padx=6)
        ttk.Button(btns, text="Close", command=self.close).pack(side="right")
        self.refresh()

    def refresh(self):
        h = self.app.history
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        # newest first, and the step Ctrl+Z would take is at the top
        n = 0
        for op in reversed(h.undo_stack):
            n += 1
            self.tree.insert("", "end", values=(
                n, time.strftime("%H:%M:%S", time.localtime(op.when)),
                op.describe()))
        for op in reversed(h.redo_stack):
            self.tree.insert("", "end", values=(
                "", time.strftime("%H:%M:%S", time.localtime(op.when)),
                "redo: " + op.describe()), tags=("redo",))
        self.tree.tag_configure("redo", foreground=_theme.TH_FG_FAINT)
        self.lab.configure(text="%d step%s recorded, %d redoable"
                           % (len(h.undo_stack),
                              "" if len(h.undo_stack) == 1 else "s",
                              len(h.redo_stack)))

    def close(self):
        self.app._hist_window = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass
