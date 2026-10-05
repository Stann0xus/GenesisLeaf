"""Tools > Progress window: translation progress by section, context, kind
and status, each row with its counts, a percentage and a bar.

Double-click a section or context row to filter the main table to it.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.core.progress import tally, text_bar
from genesisleaf.ui import theme as _theme
from genesisleaf.ui.fonts import FONT_UI_B, FONT_UI_SM

# notebook tab -> (tally key, name column title)
VIEWS = (
    ("By Section", "section", "Section"),
    ("By Context", "context", "Context"),
    ("By Kind", "kind", "Kind"),
    ("By Status", "status", "Status"),
)


class ProgressWindow:
    """Progress breakdowns; one instance per App (app.open_progress_window)."""

    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("Translation progress")
        self.win.geometry("820x600")
        self.win.transient(app.root)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        main = ttk.Frame(self.win, padding=10)
        main.pack(fill="both", expand=True)
        main.rowconfigure(2, weight=1)
        main.columnconfigure(0, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew")
        self.overall_lab = ttk.Label(header, text="", font=FONT_UI_B,
                                     foreground=_theme.TH_ACCENT)
        self.overall_lab.pack(side="left")
        ttk.Button(header, text="Refresh", command=self.refresh,
                   width=10).pack(side="right")
        self.bar = ttk.Progressbar(main, mode="determinate", maximum=100)
        self.bar.grid(row=1, column=0, sticky="ew", pady=(6, 8))

        self.notebook = ttk.Notebook(main)
        self.notebook.grid(row=2, column=0, sticky="nsew")
        self.trees = {}
        for tab, key, title in VIEWS:
            frame = ttk.Frame(self.notebook, padding=6)
            self.notebook.add(frame, text=tab)
            self.trees[key] = self._build_view(frame, key, title)

        foot = ttk.Frame(main)
        foot.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(foot, font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED,
                  text="Double-click a section or context to show it in "
                       "the main table.").pack(side="left")
        ttk.Button(foot, text="Close", command=self.close).pack(side="right")
        self.refresh()

    def _build_view(self, parent, key, title):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        cols = ("name", "done", "total", "pct", "bar", "issues")
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                            selectmode="browse")
        for col, text, w, anchor, stretch in (
                ("name", title, 240, "w", True),
                ("done", "Done", 70, "e", False),
                ("total", "Total", 70, "e", False),
                ("pct", "%", 60, "e", False),
                ("bar", "", 190, "w", False),
                ("issues", "Issues", 70, "e", False)):
            tree.heading(col, text=text, anchor=anchor)
            tree.column(col, width=w, anchor=anchor, stretch=stretch)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        tree.tag_configure("done", foreground=_theme.TH_OK)
        tree.tag_configure("issues", foreground=_theme.TH_WARN)
        if key in ("section", "context"):
            tree.bind("<Double-Button-1>",
                      lambda e, k=key, t=tree: self._jump(k, t))
        return tree

    def refresh(self):
        """Recount everything from the live pack."""
        pack = self.app.pack
        if not pack or not pack.flat:
            self.overall_lab.configure(text="No pack loaded")
            return
        overall = None
        for _tab, key, _title in VIEWS:
            overall, groups = tally(pack, key)
            tree = self.trees[key]
            tree.delete(*tree.get_children())
            for name, t in groups.items():
                tags = ("done",) if t.pct >= 100 and not t.problems else ()
                if t.problems:
                    tags = ("issues",)
                if key == "status":
                    pct = 100.0 * t.total / max(1, overall.total)
                    vals = (name, t.total, overall.total, "%.1f" % pct,
                            text_bar(pct), "")
                else:
                    vals = (name, t.done, t.total, "%.1f" % t.pct,
                            text_bar(t.pct), t.problems or "")
                tree.insert("", "end", iid=name, values=vals, tags=tags)
        self.overall_lab.configure(
            text="Overall: %d of %d translated  (%.1f%%)   -   %d with issues"
                 % (overall.done, overall.total, overall.pct,
                    overall.problems))
        self.bar.configure(value=overall.pct)

    def _jump(self, key, tree):
        sel = tree.selection()
        if not sel:
            return
        app = self.app
        if key == "section":
            app.set_section_filter(sel[0])
        else:
            app.set_context_filter(sel[0] if sel[0] != "(none)" else "All")
        app.root.lift()

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass

