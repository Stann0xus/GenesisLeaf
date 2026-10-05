"""Tools > Shared words / Dups: duplicate sources, propagation, shared words.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from genesisleaf.ui.fonts import FONT_UI_SM


class DuplicatesMixin:
    """Tools > Shared words / Dups: duplicate sources, propagation, shared words.

    Mixed into `App`; `self` is the main window.
    """

    def _build_cross_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        f.rowconfigure(1, weight=2)
        f.rowconfigure(3, weight=1)
        f.columnconfigure(0, weight=1)

        top = ttk.Frame(f)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Duplicate sources:", font=FONT_UI_SM).grid(
            row=0, column=0, sticky="w")
        self.dup_filter = ttk.Combobox(
            top, state="readonly", width=20, font=FONT_UI_SM,
            values=["All", "Untranslated only"])
        self.dup_filter.current(0)
        self.dup_filter.grid(row=0, column=1, padx=(8, 0), sticky="w")
        self.dup_filter.bind("<<ComboboxSelected>>", lambda e: self.on_dup_select())
        ttk.Button(top, text="List all duplicate sources",
                   command=self.refresh_dups).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(top, text="Jump to copy",
                   command=self.jump_dup_key).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(top, text="Propagate editor translation to ALL copies",
                   command=self.propagate_translation).grid(row=0, column=4, padx=(8, 0))
        top.columnconfigure(5, weight=1)

        dp = ttk.Panedwindow(f, orient="horizontal")
        dp.grid(row=1, column=0, sticky="nsew", pady=(4, 0))

        l1 = ttk.Frame(dp)
        self.dup_tree = ttk.Treeview(l1, columns=("src", "n"), show="headings")
        self.dup_tree.heading("src", text="Source (lowercased)")
        self.dup_tree.heading("n", text="#")
        self.dup_tree.column("src", width=420)
        self.dup_tree.column("n", width=50, anchor="e")
        self.dup_tree.pack(side="left", fill="both", expand=True)
        dsc = ttk.Scrollbar(l1, orient="vertical", command=self.dup_tree.yview)
        dsc.pack(side="left", fill="y")
        self.dup_tree.configure(yscrollcommand=dsc.set)
        self.dup_tree.bind("<<TreeviewSelect>>", self.on_dup_select)
        dp.add(l1, weight=1)

        l2 = ttk.Frame(dp)
        self.dup_keys = ttk.Treeview(
            l2, columns=("st", "key", "ctx", "src", "tr"), show="headings")
        for c, t, w in (("st", " ", 30), ("key", "Key", 190),
                        ("ctx", "Context", 150), ("src", "Source", 220),
                        ("tr", "Translation", 220)):
            self.dup_keys.heading(c, text=t)
            self.dup_keys.column(c, width=w, anchor="w" if c != "st" else "center")
        self.dup_keys.pack(side="left", fill="both", expand=True)
        dk = ttk.Scrollbar(l2, orient="vertical", command=self.dup_keys.yview)
        dk.pack(side="left", fill="y")
        self.dup_keys.configure(yscrollcommand=dk.set)
        self.dup_keys.bind("<<TreeviewSelect>>", self.on_dup_key_select)
        self.dup_keys.bind("<Double-Button-1>", lambda e: self.jump_dup_key())
        dp.add(l2, weight=1)

        sp = ttk.LabelFrame(
            f, text="Shared words in the current line  (pick a word to see every "
                    "other line that uses it; double-click a match to open it)",
            padding=4)
        sp.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        sp.rowconfigure(1, weight=1)
        sp.columnconfigure(0, weight=1)
        sp.columnconfigure(2, weight=1)

        self.word_list = tk.Listbox(sp, font=FONT_UI_SM)
        self.word_list.grid(row=1, column=0, sticky="nsew")
        wsc = ttk.Scrollbar(sp, orient="vertical", command=self.word_list.yview)
        wsc.grid(row=1, column=1, sticky="ns")
        self.word_list.configure(yscrollcommand=wsc.set)
        self.word_list.bind("<<ListboxSelect>>", self.on_word_select)

        self.match_list = tk.Listbox(sp, font=FONT_UI_SM)
        self.match_list.grid(row=1, column=2, sticky="nsew")
        msc = ttk.Scrollbar(sp, orient="vertical", command=self.match_list.yview)
        msc.grid(row=1, column=3, sticky="ns")
        self.match_list.configure(yscrollcommand=msc.set)
        self.match_list.bind("<Double-Button-1>", self.on_match_jump)
        self._match_idx = {}

        mbtns = ttk.Frame(sp)
        mbtns.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 2))
        ttk.Button(mbtns, text="Jump to match",
                   command=self.jump_selected_match, width=16).pack(side="right")
        return f

    # -- shared words panel -----------------------------------------------------------
    def _update_words(self):
        self._match_idx = {}
        self.word_list.delete(0, "end")
        self.match_list.delete(0, "end")
        if self.current < 0:
            return
        ws = self.pack.words_of(self.current)
        for w in ws:
            self.word_list.insert("end", w)
        self._word_match_rows = {}

    def on_word_select(self, _evt=None):
        sel = self.word_list.curselection()
        self.match_list.delete(0, "end")
        self._match_idx = {}
        if not sel:
            return
        word = self.word_list.get(sel[0])
        idxs = self.pack.word_index.get(word, [])
        shown = 0
        for i in idxs:
            if i == self.current:
                continue
            sec, e = self.pack.flat[i]
            prev = e.get("source", "").split("|")[0]
            label = "%s  |  %s" % (e.get("key", ""), prev[:46])
            self.match_list.insert("end", label)
            self._match_idx[label] = i
            shown += 1
        self.match_list.configure(
            height=max(4, min(10, len(self.match_list.get(0, "end")))))

    def on_match_jump(self, _evt=None):
        self.jump_selected_match()

    def jump_selected_match(self):
        sel = self.match_list.curselection()
        if not sel:
            return
        label = self.match_list.get(sel[0])
        i = self._match_idx.get(label)
        if i is not None:
            self.jump_to_flat(i)

    def _sec_summary(self, sec):
        d = self.get_stats()["by_sec"].get(sec, {"total": 0, "filled": 0})
        return "%d filled / %d" % (d["filled"], d["total"])

    # -- cross tab -----------------------------------------------------------------------
    def refresh_dups(self):
        self.dup_tree.delete(*self.dup_tree.get_children())
        self.dup_keys.delete(*self.dup_keys.get_children())
        if not len(self.pack.flat):
            return
        rows = []
        for src_l, idxs in self.pack.same_source.items():
            if len(idxs) > 1:
                rows.append((src_l, len(idxs)))
        rows.sort(key=lambda r: -r[1])
        for src_l, n in rows:
            self.dup_tree.insert("", "end", values=(src_l, n))
        self.update_status()

    def _sel_src_l(self):
        sel = self.dup_tree.selection()
        if not sel:
            return None
        return self.dup_tree.item(sel[0], "values")[0]

    def on_dup_select(self, _evt=None):
        self.dup_keys.delete(*self.dup_keys.get_children())
        src_l = self._sel_src_l()
        if src_l is None:
            return
        untr = (self.dup_filter.get() or "All") == "Untranslated only"
        for i in self.pack.same_source.get(src_l, []):
            sec, e = self.pack.flat[i]
            tr = e.get("translation", "") or ""
            if untr and tr:
                continue
            mark = "*" if tr else ""
            self.dup_keys.insert("", "end", iid=str(i),
                                 values=(mark, e.get("key", ""), e.get("context", ""),
                                         e.get("source", ""), tr))

    def on_dup_key_select(self, _evt=None):
        pass

    def jump_dup_key(self):
        sel = self.dup_keys.selection()
        if not sel:
            return
        i = int(sel[0])
        self.jump_to_flat(i)

    def propagate_translation(self):
        if self.current < 0:
            messagebox.showinfo("Propagate", "Open an entry and give it a translation first.")
            return
        src_l = self._sel_src_l()
        if src_l is None:
            messagebox.showinfo("Propagate", "Select an exact-duplicate source on the left.")
            return
        tr = self.pack.flat[self.current][1].get("translation", "")
        if not tr:
            messagebox.showinfo("Propagate", "Current entry has an empty translation.")
            return
        idxs = self.pack.same_source.get(src_l, [])
        cells = []
        for i in idxs:
            _, e = self.pack.flat[i]
            cells.append((i, e.get("translation", ""), tr))
            e["translation"] = tr
            self._own(e)
        self.note_edit("Propagate", cells)
        self.dirty = True
        self.invalidate_stats()
        self.refresh_all_rows()
        self.update_status()
        messagebox.showinfo("Propagate", "Applied the current translation to %d copies." % len(idxs))

    def refresh_all_rows(self):
        for iid, i in list(self.view_iid.items()):
            self.update_tree_row(iid, i)
