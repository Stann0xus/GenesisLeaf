"""The main toolbar (one strip of actions) and the Find bar over the table.

Layout of the revamped main window (see layout.py):

    menu bar
    toolbar      file | undo | entry navigation | join & clones
    +-- navigator --+-- find bar ------------------------------------+
    |  pack card    |  table                                         |
    |  sections     |                                                |
    |  status       +================ sash =========================+
    |  context      |  editor dock (identity, editor, preview)       |
    |  display      |                                                |
    +---------------+------------------------------------------------+
    status bar

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.core.constants import SEARCH_SCOPES
from genesisleaf.ui import brand
from genesisleaf.ui import theme as _theme
from genesisleaf.ui.fonts import FONT_UI_SM
from genesisleaf.ui.widgets import Choice, ToolTip

# Status filter values, in the order the navigator lists them.
STATUS_FILTERS = ("All", "Untranslated", "Translated", "Grows (free space)",
                  "Won't fit",
                  "Overdraw (source)", "Overdraw (translation)",
                  "Has non-ASCII")


class ToolbarMixin:
    """The main toolbar and the Find bar.

    Mixed into `App`; `self` is the main window.
    """

    def _tool(self, parent, text, command, tip=None, width=None):
        b = ttk.Button(parent, text=text, command=command, takefocus=False,
                       style="Tool.TButton")
        if width:
            b.configure(width=width)
        b.pack(side="left", padx=(0, 2))
        if tip:
            ToolTip(b, tip, delay=700)
        return b

    @staticmethod
    def _sep(parent):
        ttk.Separator(parent, orient="vertical").pack(side="left", fill="y",
                                                      padx=8, pady=2)

    # -- toolbar -------------------------------------------------------------
    def _build_toolbar(self):
        """One strip of actions, grouped left to right by what you do most:
        file, undo, moving between entries, joins/clones, extra windows."""
        bar = ttk.Frame(self.root, padding=(8, 3, 8, 3), style="Chrome.TFrame")
        bar.pack(side="top", fill="x")
        self.toolbar = bar

        # the wordmark sits at the far end of the strip
        self._logo = brand.logotype(self.root, 2)
        ttk.Label(bar, image=self._logo, style="Chrome.TLabel").pack(
            side="right", padx=(8, 2))

        self._tool(bar, "Open", self.open_pack, "Open a pack (Ctrl+O)")
        self._tool(bar, "Save", lambda: self.save_pack(ask=True),
                   "Save the pack (Ctrl+S); the previous file is kept as .bak")
        self._sep(bar)
        self._tool(bar, "↶", self.do_undo, "Undo (Ctrl+Z)", width=3)
        self._tool(bar, "↷", self.do_redo, "Redo (Ctrl+Shift+Z / Ctrl+Y)",
                   width=3)
        self._sep(bar)
        self._tool(bar, "▲", self.prev_entry, "Previous entry (Ctrl+P)",
                   width=3)
        self._tool(bar, "▼", self.next_entry, "Next entry (Ctrl+N)",
                   width=3)
        self.b_next_empty = self._tool(
            bar, "Next untranslated", self.next_empty,
            "Jump to the next row with no translation (Ctrl+Down)")
        # "Where was I?" - walk backwards through the rows you have edited.
        self.b_edited = self._tool(
            bar, "↺ Edited", self.goto_last_edited,
            "Step back through the rows you edited, newest first")
        self.l_edited = ttk.Label(bar, text="", width=9, font=FONT_UI_SM,
                                  foreground=_theme.TH_FG_MUTED,
                                  style="Chrome.TLabel")
        self.l_edited.pack(side="left")
        self._sep(bar)

        self.join_var = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(bar, text="Join identical", variable=self.join_var,
                             command=self._on_join_toggle, takefocus=False,
                             style="Chrome.TCheckbutton")
        cb.pack(side="left")
        ToolTip(cb, "Typing in a dialogue box also fills every identical "
                    "box (asks before overwriting text you wrote)", delay=700)
        self.clone_back_var = tk.BooleanVar(value=False)
        self.b_clone_back = ttk.Checkbutton(
            bar, text="Backwards", variable=self.clone_back_var,
            command=self._on_join_toggle, takefocus=False,
            style="Chrome.TCheckbutton")
        self.b_clone_back.pack(side="left", padx=(6, 6))
        ToolTip(self.b_clone_back, "Let the join also write identical boxes "
                                   "EARLIER in the file", delay=700)
        self.b_prev_clone = self._tool(bar, "◂ Clone",
                                       lambda: self.next_clone(-1),
                                       "Previous identical box")
        self.b_next_clone = self._tool(bar, "Clone ▸", self.next_clone,
                                       "Next identical box (Ctrl+Shift+C)")
        self.l_clone = ttk.Label(bar, text="", anchor="w",
                                 font=FONT_UI_SM, foreground=_theme.TH_OK,
                                 style="Chrome.TLabel")
        self.l_clone.pack(side="left", padx=(4, 0))
        self.l_join = ttk.Label(bar, text="", font=FONT_UI_SM,
                                foreground=_theme.TH_FG_MUTED,
                                style="Chrome.TLabel")
        self.l_join.pack(side="left", padx=(4, 0))

    # -- find bar --------------------------------------------------------------
    def _build_findbar(self, parent):
        """Find box over the table.  Filter on: the text narrows the table.
        Filter off: the table stays put and Prev/Next walk the hits."""
        # The section and status filters live in the navigator; these
        # stand-ins keep the combobox interface the rest of the code uses.
        self.sec_cb = Choice(["All"], on_change=self._nav_choice_changed)
        self.st_cb = Choice(STATUS_FILTERS, on_change=self._nav_choice_changed)

        fnd = ttk.Frame(parent, padding=(2, 0, 2, 4))
        fnd.columnconfigure(1, weight=1)

        ttk.Label(fnd, text="Find", font=FONT_UI_SM).grid(
            row=0, column=0, padx=(0, 4))
        self.search_ent = ttk.Entry(fnd, font=FONT_UI_SM, width=24)
        self.search_ent.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.search_ent.bind("<KeyRelease>", lambda e: self._schedule_search())
        self.search_ent.bind("<Return>", lambda e: self._find_enter())
        self.search_ent.bind("<Shift-Return>", lambda e: self._find_step(-1))
        self.search_ent.bind(
            "<Escape>",
            lambda e: (self.search_ent.delete(0, "end"),
                       self.find_lab.configure(text=""),
                       self.rebuild_view()))
        ToolTip(self.search_ent, "Find (Ctrl+F).  Enter / Ctrl+G = next, "
                                 "Shift+Enter / Ctrl+Shift+G = previous, "
                                 "Esc clears", delay=900)

        self.scope_cb = ttk.Combobox(fnd, state="readonly", width=13,
                                     font=FONT_UI_SM, values=list(SEARCH_SCOPES))
        self.find_scope = getattr(self, "find_scope", "All")
        self.scope_cb.set(self.find_scope)
        self.scope_cb.grid(row=0, column=2, padx=(0, 6))
        self.scope_cb.bind("<<ComboboxSelected>>", self._on_scope_change)
        ToolTip(self.scope_cb, "Where to look: All = key + context + source + "
                               "translation", delay=900)

        self.find_filter_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(fnd, text="Filter", variable=self.find_filter_var,
                        command=self._on_filter_toggle, takefocus=False,
                        style="Small.TCheckbutton").grid(row=0, column=3,
                                                         padx=(0, 4))
        self.b_find_prev = ttk.Button(fnd, text="◀", width=2,
                                      takefocus=False, style="Tool.TButton",
                                      command=lambda: self._find_step(-1))
        self.b_find_prev.grid(row=0, column=4)
        self.b_find_next = ttk.Button(fnd, text="▶", width=2,
                                      takefocus=False, style="Tool.TButton",
                                      command=lambda: self._find_step(1))
        self.b_find_next.grid(row=0, column=5, padx=(2, 2))
        ttk.Button(fnd, text="✕", width=2, takefocus=False,
                   style="Tool.TButton",
                   command=self.clear_search).grid(row=0, column=6)
        self.find_lab = ttk.Label(fnd, text="", width=16, anchor="w",
                                  font=FONT_UI_SM, foreground=_theme.TH_OK)
        self.find_lab.grid(row=0, column=7, sticky="w", padx=(8, 0))

        right = ttk.Frame(fnd)
        right.grid(row=0, column=8, sticky="e", padx=(8, 0))
        self.l_sort = ttk.Label(right, text="", font=FONT_UI_SM,
                                foreground=_theme.TH_FG_MUTED)
        self.l_sort.pack(side="left")
        # only shown while a column sort is active (see _mark_sort_heading)
        self.b_clear_sort = ttk.Button(right, text="✕ sort",
                                       takefocus=False, style="Tool.TButton",
                                       command=self.clear_sort)
        self.nav_lab = ttk.Label(right, text="", font=FONT_UI_SM,
                                 foreground=_theme.TH_FG_MUTED)
        self.nav_lab.pack(side="left")
        return fnd
