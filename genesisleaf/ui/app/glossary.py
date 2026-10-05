"""Tools > Dictionary / glossary: terms, CSV import, suggestions, bulk autofill.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import json
import os
import re
from tkinter import filedialog, messagebox, ttk

from genesisleaf.core.encoding import parse_text
from genesisleaf.core.space import verdict as space_verdict
from genesisleaf.ui.fonts import FONT_UI_SM
from genesisleaf.ui import theme as _theme


class GlossaryMixin:
    """Tools > Dictionary / glossary: terms, CSV import, suggestions, bulk autofill.

    Mixed into `App`; `self` is the main window.
    """

    # -- dictionary tab ----------------------------------------------------------
    def _build_dictionary_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="Glossary file:").pack(side="left")
        self.l_gloss_path = ttk.Label(bar, text="-", foreground=_theme.TH_FG_MUTED)
        self.l_gloss_path.pack(side="left", padx=4)
        ttk.Button(bar, text="Load...", command=self.load_glossary).pack(side="left", padx=2)
        ttk.Button(bar, text="Save", command=self.save_glossary).pack(side="left", padx=2)

        form = ttk.Frame(f)
        form.pack(fill="x", pady=6)
        ttk.Label(form, text="Term (English):").grid(row=0, column=0, sticky="e", padx=2)
        self.dict_term = ttk.Entry(form, width=30)
        self.dict_term.grid(row=0, column=1, sticky="w", padx=2)
        ttk.Label(form, text="Translation:").grid(row=0, column=2, sticky="e", padx=2)
        self.dict_tr = ttk.Entry(form, width=30)
        self.dict_tr.grid(row=0, column=3, sticky="w", padx=2)
        ttk.Button(form, text="Add / update", command=self.dict_add).grid(row=0, column=4, padx=4)
        ttk.Button(form, text="Use current entry", command=self.dict_from_entry).grid(row=0, column=5, padx=2)
        ttk.Button(form, text="Delete", command=self.dict_delete).grid(row=0, column=6, padx=2)
        ttk.Button(form, text="Import from CSV...", command=self.dict_import_csv).grid(row=1, column=5, pady=4, sticky="w")

        cols = ("term", "tr")
        self.dict_tree = ttk.Treeview(f, columns=cols, show="headings", height=10)
        self.dict_tree.heading("term", text="Term")
        self.dict_tree.heading("tr", text="Translation")
        self.dict_tree.column("term", width=260)
        self.dict_tree.column("tr", width=360)
        self.dict_tree.pack(fill="both", expand=True, pady=4)
        self.dict_tree.bind("<<TreeviewSelect>>", self.on_dict_select)

        act = ttk.Frame(f)
        act.pack(fill="x", pady=4)
        ttk.Button(act, text="Suggest translation for current entry",
                   command=self.dict_suggest_current).pack(side="left", padx=2)
        ttk.Button(act, text="Autofill all untranslated (bulk)",
                   command=self.dict_bulk_fill).pack(side="left", padx=2)
        ttk.Label(act, text="Longest match, whole words; skips anything that would exceed budget.",
                  font=FONT_UI_SM).pack(side="left", padx=8)
        return f

    def _refresh_glossary_path(self):
        if not self.pack.path:
            self.l_gloss_path.configure(text="-")
            return
        base = os.path.splitext(self.pack.path)[0]
        self.l_gloss_path.configure(text=base + ".dict.json")

    def load_glossary(self):
        p = filedialog.askopenfilename(
            title="Load glossary",
            filetypes=[("JSON glossary", "*.json"), ("All files", "*.*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as fh:
                g = json.load(fh)
            if not isinstance(g, dict):
                raise ValueError("bad format")
            self.glossary = {str(k): str(v) for k, v in g.items()}
            self.glossary_path = p
            self.refresh_dict_tree()
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def save_glossary(self):
        p = self.glossary_path
        if not p:
            p = filedialog.asksaveasfilename(
                defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not p:
                return
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(self.glossary, fh, ensure_ascii=False, indent=2)
        self.glossary_path = p
        self._glossary_dirty = 0
        self.sb.configure(text="Glossary saved: %s (%d terms)" % (
            os.path.basename(p), len(self.glossary)))

    def dict_add(self):
        term = self.dict_term.get().strip()
        tr = self.dict_tr.get().strip()
        if not term:
            messagebox.showwarning("Glossary", "Term is empty.")
            return
        if not tr:
            messagebox.showwarning("Glossary", "Translation is empty.")
            return
        self.glossary[term] = tr
        self.dict_term.delete(0, "end")
        self.dict_tr.delete(0, "end")
        self._glossary_dirty += 1
        self.refresh_dict_tree()

    def dict_from_entry(self):
        if self.current < 0:
            return
        _, e = self.pack.flat[self.current]
        src, tr = e.get("source", ""), e.get("translation", "")
        self.dict_term.delete(0, "end")
        self.dict_term.insert(0, src)
        self.dict_tr.delete(0, "end")
        self.dict_tr.insert(0, tr)

    def dict_delete(self):
        sel = self.dict_tree.selection()
        if not sel:
            return
        term = self.dict_tree.item(sel[0], "values")[0]
        self.glossary.pop(term, None)
        self._glossary_dirty += 1
        self.refresh_dict_tree()

    def on_dict_select(self, _evt=None):
        sel = self.dict_tree.selection()
        if not sel:
            return
        values = self.dict_tree.item(sel[0], "values")
        self.dict_term.delete(0, "end")
        self.dict_term.insert(0, values[0])
        self.dict_tr.delete(0, "end")
        self.dict_tr.insert(0, values[1])

    def dict_import_csv(self):
        p = filedialog.askopenfilename(
            title="Import glossary from CSV",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not p:
            return
        n = 0
        import csv

        with open(p, "r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and row[0].strip():
                    self.glossary[row[0].strip()] = row[1].strip()
                    n += 1
        self._glossary_dirty += 1
        self.refresh_dict_tree()
        messagebox.showinfo("Import", "Imported %d terms." % n)

    def refresh_dict_tree(self):
        self.dict_tree.delete(*self.dict_tree.get_children())
        for term in sorted(self.glossary):
            self.dict_tree.insert("", "end", values=(term, self.glossary[term]))

    def suggest_for(self, source):
        tokens = []

        def stash(m):
            tokens.append(m.group(0))
            return "\x00%d\x00" % (len(tokens) - 1)

        protected = re.sub(r"\{[0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2})?\}|\|",
                           stash, source)
        out = protected
        for term in sorted(self.glossary, key=len, reverse=True):
            pat = r"(?<![0-9a-zA-Z])" + re.escape(term) + r"(?![0-9a-zA-Z])"
            out = re.sub(pat, lambda m, t=term: self.glossary[t], out, flags=re.I)

        def restore(m):
            return tokens[int(m.group(0)[1:-1])]

        return re.sub(r"\x00\d+\x00", restore, out)

    def dict_suggest_current(self):
        if self.current < 0:
            return
        from_src = not self.pack.flat[self.current][1].get("translation", "")
        target = self.pack.flat[self.current][1]["source"] if from_src else \
            self.pack.flat[self.current][1].get("translation", "")
        s = self.suggest_for(target)
        if s == target:
            messagebox.showinfo("Suggest", "No dictionary term matched.")
            return
        self.set_translation(s)
        self.tr_txt.focus_set()

    def dict_bulk_fill(self):
        if not self.glossary:
            messagebox.showwarning("Glossary", "Glossary is empty.")
            return
        n = 0
        cells = []
        for i, (sec, e) in enumerate(self.pack.flat):
            if e.get("translation", ""):
                continue
            s = self.suggest_for(e.get("source", ""))
            if s == e.get("source", ""):
                continue
            b, _ = parse_text(s)
            if space_verdict(sec, dict(e, translation=s), b) == "over":
                continue
            cells.append((i, "", s))
            e["translation"] = s
            self._own(e)
            n += 1
        self.note_edit("Autofill", cells)
        self.dirty = True
        self.view_row_update_all()
        self.invalidate_stats()
        self.update_status()
        self.refresh_all_rows()
        messagebox.showinfo("Autofill", "Filled %d empty entries from the glossary." % n)
