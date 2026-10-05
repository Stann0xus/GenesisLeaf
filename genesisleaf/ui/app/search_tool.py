"""Tools > Search window (word search across the pack).

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.core.constants import SEARCH_SCOPES
from genesisleaf.ui.fonts import FONT_UI_SM
from genesisleaf.ui import theme as _theme


class SearchToolMixin:
    """Tools > Search window (word search across the pack).

    Mixed into `App`; `self` is the main window.
    """

    # -- search tab ----------------------------------------------------------
    def _build_search_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        r = ttk.Frame(f)
        r.pack(fill="x")
        ttk.Label(r, text="Search every source / context / key:",
                  font=FONT_UI_SM).pack(side="left")
        self.word_search = ttk.Entry(r, font=FONT_UI_SM)
        self.word_search.pack(side="left", fill="x", expand=True, padx=(4, 2))
        self.word_search.bind("<Return>", lambda e: self.word_search_run())
        self.search_untrans = tk.BooleanVar(value=False)
        ttk.Checkbutton(r, text="Untranslated only", variable=self.search_untrans,
                        command=self.word_search_run).pack(side="left", padx=(4, 2))
        ttk.Button(r, text="Search", command=self.word_search_run,
                   width=9).pack(side="left", padx=2)
        ttk.Button(r, text="Jump to entry", command=self.jump_word_result,
                   width=12).pack(side="left", padx=2)

        # Scope selector, so a word that only appears in a context asset name
        # does not flood this list.  Shares SEARCH_SCOPES with the main Find
        # box and starts on the same setting.
        srow = ttk.Frame(f)
        srow.pack(fill="x", pady=(5, 0))
        ttk.Label(srow, text="Search in:", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left")
        self.word_scope = ttk.Combobox(
            srow, state="readonly", width=19, font=FONT_UI_SM,
            values=list(SEARCH_SCOPES))
        self.word_scope.set(getattr(self, "find_scope", "All"))
        self.word_scope.pack(side="left", padx=(4, 8))
        self.word_scope.bind("<<ComboboxSelected>>",
                             lambda e: self.word_search_run())
        ttk.Label(srow, font=FONT_UI_SM, foreground=_theme.TH_FG_FAINT,
                  text="Source/Translation ignore key and context, so a word "
                       "shared with an asset name no longer matches."
                  ).pack(side="left")

        tr = ttk.Frame(f)
        tr.pack(fill="both", expand=True, pady=(4, 0))
        tr.rowconfigure(0, weight=1)
        tr.columnconfigure(0, weight=1)
        self.word_results = ttk.Treeview(
            tr, columns=("st", "key", "sec", "ctx", "src", "tr"),
            show="headings")
        for c, t, w in (("st", " ", 30), ("key", "Key", 190),
                        ("sec", "Section", 80), ("ctx", "Context", 150),
                        ("src", "Source", 280), ("tr", "Translation", 260)):
            self.word_results.heading(c, text=t)
            self.word_results.column(c, width=w, anchor="w" if c != "st" else "center")
        self.word_results.grid(row=0, column=0, sticky="nsew")
        via = ttk.Scrollbar(tr, orient="vertical", command=self.word_results.yview)
        via.grid(row=0, column=1, sticky="ns")
        hor = ttk.Scrollbar(tr, orient="horizontal", command=self.word_results.xview)
        hor.grid(row=1, column=0, sticky="ew")
        self.word_results.configure(yscrollcommand=via.set, xscrollcommand=hor.set)
        self.word_results.bind("<Double-Button-1>", lambda e: self.jump_word_result())
        self._word_src = ""
        return f

    # -- word search in search tab ----------------------------------------------------
    def word_search_run(self):
        self._word_src = self.word_search.get().strip()
        self.word_results.delete(*self.word_results.get_children())
        if not self._word_src:
            return
        q = self._word_src.lower()
        untr = self.search_untrans.get()
        # Same scope options as the main Find box, and the same haystack
        # helper, so the two searches can never disagree about a hit.
        scope = self.word_scope.get()
        seen = set()
        rows = []
        for i, (sec, e) in enumerate(self.pack.flat):
            if q in self._scope_haystack(e, scope).lower():
                tr = e.get("translation", "") or ""
                if untr and tr:
                    continue
                # Show the ENTIRE dialogue box the hit belongs to, not just
                # the line that matched (matches the main Find filter).
                for gi in self.box_rows(i):
                    if gi in seen:
                        continue
                    seen.add(gi)
                    gsec, ge = self.pack.flat[gi]
                    gtr = ge.get("translation", "") or ""
                    mark = "*" if gtr else ""
                    rows.append((gi, mark, ge.get("key", ""), gsec,
                                 ge.get("context", ""), ge.get("source", ""),
                                 gtr))
        for vals in rows:
            self.word_results.insert("", "end", iid=str(vals[0]),
                                     values=vals[1:])

    def jump_word_result(self):
        sel = self.word_results.selection()
        if not sel:
            return
        i = int(sel[0])
        self.jump_to_flat(i)
