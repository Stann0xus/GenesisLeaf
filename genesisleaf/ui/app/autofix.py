"""Tools > Auto-fix: scoped dry-run/apply of text clean-ups.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.core.encoding import parse_text
from genesisleaf.core.space import row_room, verdict as space_verdict
from genesisleaf.core.textfix import (
    ascii_fold, collapse_spaces, normalize_newlines, truncate_to_budget,
)
from genesisleaf.ui.fonts import FONT_UI, FONT_UI_SM


class AutofixMixin:
    """Tools > Auto-fix: scoped dry-run/apply of text clean-ups.

    Mixed into `App`; `self` is the main window.
    """

    def _build_autofix_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        ttk.Label(f, text="Auto-fix flagged entries: over-budget, non-ASCII, or any translated line.",
                  font=FONT_UI_SM).pack(anchor="w")

        scope = ttk.LabelFrame(f, text="Scope", padding=6)
        scope.pack(fill="x", pady=(4, 0))
        self.afx_scope = tk.StringVar(value="over")
        for val, lab in (("current", "Current entry"),
                         ("over", "Over-budget entries"),
                         ("non", "Entries with non-ASCII"),
                         ("all", "All translated entries")):
            ttk.Radiobutton(scope, text=lab, variable=self.afx_scope,
                            value=val).pack(side="left", padx=8)

        opts = ttk.LabelFrame(f, text="Fixes (applied in this order)", padding=6)
        opts.pack(fill="x", pady=(6, 0))
        self.afx_newlines = tk.BooleanVar(value=True)
        self.afx_fold = tk.BooleanVar(value=True)
        self.afx_space = tk.BooleanVar(value=True)
        self.afx_trim = tk.BooleanVar(value=False)
        self.afx_cut = tk.BooleanVar(value=True)
        for var, lab in (
            (self.afx_newlines, "Convert real newlines to the | glyph"),
            (self.afx_fold, "Fold accents / smart punctuation to ASCII"),
            (self.afx_space, "Collapse repeated spaces"),
            (self.afx_trim, "Trim leading / trailing spaces"),
            (self.afx_cut, "Truncate tail to fit budget (cuts only at words / | rows)")):
            ttk.Checkbutton(opts, text=lab, variable=var).pack(anchor="w")

        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Dry run (count changes)",
                   command=self.autofix_dryrun).pack(side="left", padx=2)
        ttk.Button(btns, text="Apply", command=self.autofix_apply,
                   width=10).pack(side="left", padx=2)
        self.afx_res = ttk.Label(btns, text="", font=FONT_UI)
        self.afx_res.pack(side="left", padx=12)

        log = ttk.LabelFrame(f, text="Log (first 60 changes)", padding=4)
        log.pack(fill="both", expand=True, pady=(6, 0))
        self.afx_log = tk.Text(log, height=9, wrap="word",
                               font=FONT_UI_SM, state="disabled")
        self.afx_log.pack(side="left", fill="both", expand=True)
        vs = ttk.Scrollbar(log, orient="vertical", command=self.afx_log.yview)
        self.afx_log.configure(yscrollcommand=vs.set)
        vs.pack(side="left", fill="y")
        return f

    def _autofix_scope(self):
        v = self.afx_scope.get()
        if v == "current":
            return [self.current] if self.current >= 0 else []
        out = []
        self._afx_secs = {}
        for i, (sec, e) in enumerate(self.pack.flat):
            self._afx_secs[id(e)] = sec
            tr = e.get("translation", "")
            if not tr:
                continue
            b, spans = parse_text(tr)
            non = any(st == "nonascii" for _, _, st in spans)
            if v == "over" and space_verdict(sec, e, b) == "over":
                out.append(i)
            elif v == "non" and non:
                out.append(i)
            elif v == "all":
                out.append(i)
        return out

    def _afx_sec(self, e):
        """Section of entry `e` (the room kind of a `scus:str:` key needs it)."""
        sec = getattr(self, "_afx_secs", {}).get(id(e))
        if sec is None:
            sec = next((s for s, x in self.pack.flat if x is e), "")
        return sec

    def _autofix_one(self, e):
        tr = e.get("translation", "")
        if self.afx_newlines.get():
            tr = normalize_newlines(tr)
        if self.afx_fold.get():
            tr = ascii_fold(tr)
        if self.afx_space.get():
            tr = collapse_spaces(tr)
        if self.afx_trim.get():
            tr = tr.strip()
        if self.afx_cut.get():
            # cut to what the row can really hold: its hard cap, or its
            # in-place span for a pooled row (core.space.row_room)
            tr, _ = truncate_to_budget(tr, row_room(self._afx_sec(e), e))
        return tr

    def _afx_log_clear(self):
        self.afx_log.configure(state="normal")
        self.afx_log.delete("1.0", "end")
        self.afx_log.configure(state="disabled")

    def _afx_log_line(self, s):
        self.afx_log.configure(state="normal")
        self.afx_log.insert("end", s + "\n")
        self.afx_log.configure(state="disabled")

    def _autofix_diff(self):
        idxs = self._autofix_scope()
        changed = []
        for i in idxs:
            sec, e = self.pack.flat[i]
            new = self._autofix_one(e)
            if new != e.get("translation", ""):
                changed.append((i, new))
        return idxs, changed

    def autofix_dryrun(self):
        idxs, changed = self._autofix_diff()
        self.afx_res.configure(text="%d of %d would change"
                                % (len(changed), len(idxs)))
        self._afx_log_clear()
        for i, new in changed[:60]:
            e = self.pack.flat[i][1]
            self._afx_log_line("%s | %s%s%s" % (
                e.get("key", ""), e.get("translation", ""),
                "  ->  " if new else "", new))
        if len(changed) > 60:
            self._afx_log_line("...and %d more" % (len(changed) - 60))

    def autofix_apply(self):
        idxs, changed = self._autofix_diff()
        if not changed:
            self.afx_res.configure(text="Nothing to change (%d in scope)." % len(idxs))
            return
        n = 0
        cells = []
        for i, new in changed:
            _, e = self.pack.flat[i]
            cells.append((i, e.get("translation", ""), new))
            e["translation"] = new
            self._own(e)
            n += 1
        # one step for the whole batch, so a bad auto-fix is one Ctrl+Z away
        self.note_edit("Auto-fix", cells)
        self.dirty = True
        self.invalidate_stats()
        self.view_row_update_all()
        self.update_status()
        if self.current >= 0:
            _, e0 = self.pack.flat[self.current]
            self.tr_txt.delete("1.0", "end")
            self.tr_txt.insert("1.0", e0.get("translation", ""))
            self.tr_txt.edit_modified(False)
            self.retag(self.tr_txt, allow_over=True)
            self.update_preview()
        self.afx_res.configure(text="Applied to %d entries." % n)
        self.autofix_dryrun()
