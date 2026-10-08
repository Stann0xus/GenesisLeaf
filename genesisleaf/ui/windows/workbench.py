"""Dynamic translation workbench window (mirrors the web translate-workbench).

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.core.colors import readable_on
from genesisleaf.core.dialog import (
    SECTION_KIND, TEXT_LIMITS, default_limit_context, limit_for,
)
from genesisleaf.core.encoding import parse_text
from genesisleaf.core.textfix import truncate_to_budget
from genesisleaf.core.space import KIND_LABEL, room_kind, row_room, verdict as space_verdict
from genesisleaf.render.metrics import font_advance, measure_markup
from genesisleaf.ui.canvas_render import (
    render_text_to_canvas, reposition_canvas_preview,
)
from genesisleaf.ui.fonts import FONT_MONO, FONT_UI_SM
from genesisleaf.ui import theme as _theme


class WorkbenchWindow:
    """Dynamic translation editor (mirrors the web translate-workbench app).

    A separate Toplevel from the main table so you can keep browsing entries
    while this window measures what you type.  Every edit writes straight back
    into the pack (App.wb_commit), keeps the main editor in sync when it is
    showing the same entry, and the READ panel accumulates what the triage
    panel tallies.

    Measurement is the real retail pipeline (font_measure.rs port): encode the
    markup to MES bytes like the importer, expand substitutions, walk the
    width table + escape table, compare against the pinned on-screen budgets
    (TEXT_LIMITS)."""

    def __init__(self, app):
        self.app = app
        self.idx = -1
        self._loading = False
        self._sched = None
        self._filter_sec = "All"
        self._filter_st = "All"
        self._filter_q = ""
        self._manual_limit = None

        win = tk.Toplevel(app.root)
        win.title("Translation workbench")
        win.geometry("1120x680")
        win.configure(bg=_theme.APP_BG)
        self.win = win
        win.protocol("WM_DELETE_WINDOW", self.close)

        self._build_ui()
        self.rebuild()

    # -- ui -----------------------------------------------------------------
    def _build_ui(self):
        win = self.win
        pan = ttk.Panedwindow(win, orient="horizontal")
        pan.pack(fill="both", expand=True, padx=4, pady=4)

        # ---- left: list ----------------------------------------------------
        left = ttk.Frame(pan, padding=2)
        bar = ttk.Frame(left, padding=(0, 0, 0, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Section:", font=FONT_UI_SM).pack(side="left")
        self.sec_cb = ttk.Combobox(bar, state="readonly", width=14,
                                   font=FONT_UI_SM)
        self.sec_cb.pack(side="left", padx=(1, 6))
        self.sec_cb.bind("<<ComboboxSelected>>", self._on_sec)
        ttk.Label(bar, text="St:", font=FONT_UI_SM).pack(side="left")
        self.st_cb = ttk.Combobox(
            bar, state="readonly", width=10, font=FONT_UI_SM,
            values=["All", "Untranslated", "Translated",
                    "Won't fit", "Over width", "Bad chars"])
        self.st_cb.current(0)
        self.st_cb.pack(side="left", padx=(1, 6))
        self.st_cb.bind("<<ComboboxSelected>>", self._on_filter)
        self.q_ent = ttk.Entry(bar, width=16, font=FONT_UI_SM)
        self.q_ent.pack(side="left")
        self.q_ent.bind("<KeyRelease>", self._on_filter)

        cols = ("room", "px", "st", "key", "ctx")
        self.tree = ttk.Treeview(left, columns=cols, show="headings",
                                 selectmode="extended")
        hdrs = {"room": "room", "px": "px", "st": "", "key": "key",
                "ctx": "context"}
        for c in cols:
            w = 40 if c == "st" else (70 if c == "px" else 130)
            self.tree.heading(c, text=hdrs[c])
            self.tree.column(c, width=w, stretch=(c == "ctx"))
        self.tree.tag_configure("over", foreground=_theme.TH_BAD)
        self.tree.tag_configure("ok", foreground=_theme.TH_OK)
        self.tree.pack(fill="both", expand=True)
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        vsb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Up>", self._on_rowkey)
        self.tree.bind("<Down>", self._on_rowkey)
        ttk.Label(left, text="multi-select rows: the preview stacks them; "
                             "Down/Up move by the selection (a whole dialog "
                             "box previews alone)",
                  font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(anchor="w", pady=(2, 0))
        pan.add(left, weight=1)

        # ---- right: editor -------------------------------------------------
        right = ttk.Frame(pan, padding=(6, 2))
        self.l_info = ttk.Label(right, text="No entry selected",
                                font=FONT_UI_SM, foreground=_theme.TH_FG)
        self.l_info.pack(anchor="w")

        row1 = ttk.Frame(right)
        row1.pack(fill="x", pady=(2, 0))
        ttk.Label(row1, text="Surface:", font=FONT_UI_SM).pack(side="left")
        self.limit_cb = ttk.Combobox(
            row1, state="readonly", width=30, font=FONT_UI_SM)
        self.limit_cb.pack(side="left", padx=(2, 8))
        self.limit_cb.bind("<<ComboboxSelected>>", self._on_limit)
        self.l_kind = ttk.Label(row1, text="", font=FONT_UI_SM,
                                foreground=_theme.TH_FG_MUTED)
        self.l_kind.pack(side="left")

        ttk.Label(right, text="Source", font=FONT_UI_SM).pack(anchor="w")
        self.src_txt = tk.Text(right, height=3, wrap="word",
                               state="disabled", font=FONT_MONO,
                               bg=_theme.BG_EDIT, fg=_theme.FG_DIM, relief="flat",
                               selectbackground="#2b4a6e",
                               selectforeground="#ffffff")
        self.src_txt.pack(fill="x", pady=(0, 4))

        ttk.Label(right, text="Translation (measure as you type)",
                  font=FONT_UI_SM).pack(anchor="w")
        self.tr_txt = tk.Text(right, height=8, wrap="word", font=FONT_MONO,
                              bg=_theme.BG_EDIT, fg=_theme.FG_MAIN, relief="flat",
                              undo=True, selectbackground="#2b4a6e",
                              selectforeground="#ffffff")
        self.tr_txt.pack(fill="x", pady=(0, 4))
        self.tr_txt.bind("<<Modified>>", self._on_modified)
        self.tr_txt.bind("<Control-s>", self._save)
        self.tr_txt.bind("<Control-Return>", self._fit_budget)
        self.app.configure_text_tags(self.tr_txt)
        self.app.configure_text_tags(self.src_txt)
        for w in (self.src_txt, self.tr_txt):
            try:
                w.tag_configure("over", background="#5a1e24",
                                foreground="#ffe0e0")
            except tk.TclError:
                pass

        self.l_room = ttk.Label(right, text="", font=FONT_UI_SM)
        self.l_room.pack(anchor="w")
        self.l_px = ttk.Label(right, text="", font=FONT_UI_SM)
        self.l_px.pack(anchor="w")

        btns = ttk.Frame(right)
        btns.pack(fill="x", pady=(4, 2))
        ttk.Button(btns, text="Fit to budget", command=self._fit_budget,
                   width=14).pack(side="left")
        ttk.Button(btns, text="Copy source", command=self._copy_source,
                   width=13).pack(side="left", padx=4)
        ttk.Button(btns, text="Clear", command=self._clear_tr,
                   width=8).pack(side="left")

        # preview: real retail-glyph render (render_font_rows + scale-2 image)
        cwrap = ttk.Frame(right)
        cwrap.pack(fill="both", expand=True, pady=(4, 0))
        cv = tk.Canvas(cwrap, height=150, bg=_theme.APP_BG, highlightthickness=1,
                       highlightbackground="#555")
        cv.pack(fill="both", expand=True)
        self.cv = cv
        self._pv_image = None
        self.cv.bind("<Configure>", lambda e: (
            reposition_canvas_preview(self.cv) or self._draw_preview()))

        # character inspector text (per-token widths)
        ttk.Label(right, text="Characters (byte, advance)",
                  font=FONT_UI_SM).pack(anchor="w", pady=(4, 0))
        self.insp = tk.Text(right, height=5, wrap="none", font=FONT_UI_SM,
                            bg=_theme.BG_EDIT, fg=_theme.FG_DIM, state="disabled",
                            relief="flat", selectbackground="#2b4a6e",
                            selectforeground="#ffffff")
        self.insp.pack(fill="x")
        pan.add(right, weight=2)

        self._populate_sec()

    # -- data ---------------------------------------------------------------
    def _populate_sec(self):
        secs = ["All"] + list(self.app.pack.section_names)
        self.sec_cb.configure(values=secs)
        self.sec_cb.current(0)

    def _row_limit(self, sec):
        eff = self._manual_limit
        if not eff:
            eff = default_limit_context(sec)
        if not eff or eff == "(none)":
            return None
        return limit_for(eff)

    def _kind(self, sec):
        return SECTION_KIND.get(sec, "?")

    def _measure(self, sec, text):
        lim = self._row_limit(sec)
        pad = lim["glyph_pad"] if lim else 0
        bs, lw, maxpx, un, items, bad = measure_markup(
            text, glyph_pad=pad, expander=self._expander())
        return bs, lw, maxpx, un, items, bad, lim

    def _expander(self):
        return self.app.markup_expander()

    def _rebuild_refs(self):
        self.app._wb_refs = None

    def rebuild(self):
        self._rebuild_refs()
        self.tree.delete(*self.tree.get_children())
        app = self.app
        sec = self._filter_sec
        st = self._filter_st
        q = self._filter_q.strip().lower()
        rows = []
        for i, (s, e) in enumerate(app.pack.flat):
            if sec != "All" and s != sec:
                continue
            src = e.get("source", "")
            tr = e.get("translation", "")
            low = (e.get("key", "") + " " + src + " " + tr).lower()
            if q and q not in low:
                continue
            rows.append((i, s, e))
        out = []
        for i, s, e in rows:
            met = self._row_metrics(s, e)
            if st == "Untranslated" and met[3]:
                continue
            if st == "Translated" and not met[3]:
                continue
            if st == "Won't fit" and not met[0]:
                continue
            if st == "Over width" and not met[2]:
                continue
            if st == "Bad chars" and not met[1]:
                continue
            out.append((i, s, e, met))
        for i, s, e, met in out:
            self._insert_row(i, s, e, met)
        self.tree.configure(cursor="")

    def _row_metrics(self, s, e):
        tr = e.get("translation", "")
        b, _ = parse_text(tr)
        _, lw, maxpx, un, items, bad, lim = self._measure(s, tr)
        over_b = bool(tr) and space_verdict(s, e, b) == "over"
        over_w = bool(maxpx and lim and maxpx > lim["max_px"])
        return over_b, bool(bad), over_w, bool(tr)

    def _insert_row(self, i, s, e, met=None):
        src = e.get("source", "")
        tr = e.get("translation", "")
        b, _ = parse_text(tr)
        sb, _ = parse_text(src)
        budget = int(e.get("budget", sb))
        if met is None:
            met = self._row_metrics(s, e)
        _, lw, maxpx, un, items, bad, lim = self._measure(s, tr)
        probes = []
        if met[0]:
            probes.append(("over",))
        if met[1]:
            probes.append(("bad",))
        if tr and not probes:
            probes.append(("ok",))
        tag = "over" if probes else "ok"
        st_mark = "*"
        if met[0]:
            st_mark = "!"
        elif b > budget:
            st_mark = "+"
        if bad:
            st_mark = "@"
        px_s = "%d%s" % (maxpx, ("/%d" % lim["max_px"]) if lim else "")
        self.tree.insert("", "end", iid=str(i), values=(
            "%d/%d" % (b, budget), px_s, st_mark,
            e.get("key", ""), e.get("context", "")), tags=(tag,))

    # -- events ------------------------------------------------------------
    def _on_sec(self, _e=None):
        self._filter_sec = self.sec_cb.get()
        self.rebuild()

    def _on_filter(self, _e=None):
        self._filter_st = self.st_cb.get()
        self._filter_q = self.q_ent.get()
        self.rebuild()

    def _on_limit(self, _e=None):
        v = self.limit_cb.get().strip()
        self._manual_limit = None if v == "(auto)" else (v or None)
        self._commit_delayed()

    def _row_of(self, pos):
        iid = self.tree.get_children()[pos] if self.tree.get_children() else None
        return int(iid) if iid is not None else -1

    def _on_rowkey(self, evt):
        sel = self.tree.selection()
        if not sel:
            return
        kids = self.tree.get_children()
        if not kids:
            return
        step = max(1, len(sel))
        if evt.keysym == "Down":
            target = self.tree.index(sel[0]) + step
        else:
            target = self.tree.index(sel[0]) - step
        target = max(0, min(target, len(kids) - step))
        block = kids[target:target + step]
        if not block:
            return "break"
        self.tree.selection_set(block)
        self.tree.see(block[0])
        self.idx = int(block[0])
        self._load_entry()
        return "break"

    def _on_select(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        self.idx = int(sel[0])
        self._load_entry()

    def _box_texts(self, idx):
        """Rows of `idx`'s dialog box (or the single line): translation if
        non-empty else source, box order. Mirrors web previewRows()."""
        if idx < 0:
            return []
        app = self.app
        rows = app.box_rows(idx)
        out = []
        for i in rows:
            _, e = app.pack.flat[i]
            t = (e.get("translation", "") or "").rstrip()
            out.append(t if t else e.get("source", ""))
        return out

    def _preview_texts(self):
        """Rows for the preview: the explicit multi-selection when >1 rows are
        chosen, else the selected entry's dialog box (or just it)."""
        sel = self.tree.selection()
        if len(sel) > 1:
            idxs = []
            for s in sel:
                try:
                    idxs.append(int(s))
                except (TypeError, ValueError):
                    pass
            idxs.sort()
            out = []
            for i in idxs:
                _, e = self.app.pack.flat[i]
                t = (e.get("translation", "") or "").rstrip()
                out.append(t if t else e.get("source", ""))
            return out
        return self._box_texts(self.idx)

    def _load_entry(self):
        app = self.app
        i = self.idx
        _, e = app.pack.flat[i]
        sec = app.pack.flat[i][0]
        self._loading = True
        try:
            self.l_info.configure(
                text="[%s]  %s  |  %s" % (sec, e.get("key", ""),
                                          e.get("context", "")))
            self.l_kind.configure(text=" - %s" % self._kind(sec))
            self.src_txt.configure(state="normal")
            self.src_txt.delete("1.0", "end")
            self.src_txt.insert("1.0", e.get("source", ""))
            self.src_txt._tag_content = None
            self.app.retag(self.src_txt, idx=i)
            self.src_txt.configure(state="disabled")
            self.tr_txt.delete("1.0", "end")
            self.tr_txt.insert("1.0", e.get("translation", ""))
            self.tr_txt._tag_content = None
            self.tr_txt.edit_modified(False)
            self.app.retag(self.tr_txt, allow_over=True, idx=i)
            self._update_meters()
        finally:
            self._loading = False
        self._draw_preview()
        self._populate_limit_cb(sec)

    def _populate_limit_cb(self, sec):
        self.limit_cb.configure(values=["(auto)"] + sorted(TEXT_LIMITS))
        self.limit_cb.set("(auto)" if self._manual_limit is None
                          else self._manual_limit if self._manual_limit in TEXT_LIMITS
                          else "(none)")

    def _on_modified(self, _e=None):
        if self._loading or self.idx < 0 or not self.tr_txt.edit_modified():
            return
        self.tr_txt.edit_modified(False)
        if self._sched:
            try:
                self.win.after_cancel(self._sched)
            except Exception:
                pass
        self._sched = self.win.after(120, self._commit_delayed)

    def _commit_delayed(self):
        if self.idx < 0:
            return
        self._sched = None
        val = self.tr_txt.get("1.0", "end-1c")
        self.app.wb_commit(self.idx, val)
        self.app.retag(self.tr_txt, allow_over=True, idx=self.idx)
        self._update_meters()
        iid = str(self.idx)
        if self.tree.exists(iid):
            self.tree.delete(iid)
            i, (s, e) = self.idx, self.app.pack.flat[self.idx]
            self._insert_row(i, s, e)
        self._draw_preview()

    def _update_meters(self):
        sec = self.app.pack.flat[self.idx][0]
        e = self.app.pack.flat[self.idx][1]
        tr = e.get("translation", "")
        b, _ = parse_text(tr)
        sb, _ = parse_text(e.get("source", ""))
        budget = int(e.get("budget", sb))
        _, lw, maxpx, un, items, bad, lim = self._measure(sec, tr)
        pad = lim["glyph_pad"] if lim else 0
        room = budget - b
        v = space_verdict(sec, e, b)
        note = ""
        if v == "over":
            note = "   WON'T FIT (room %d B)" % row_room(sec, e)
        elif v == "grows":
            note = "   +%d B from free space (%s)" % (
                b - budget, KIND_LABEL[room_kind(sec, e.get("key", ""))])
        self.l_room.configure(
            text="room %d byte  ->  encoded %d / budget %d%s" % (
                room, b, budget, note),
            foreground=_theme.TH_BAD if b > budget else _theme.TH_OK)
        if lim:
            ml = lim["max_lines"]
            extra = ("  lines %d%s" % (len(lw),
                     ("" if ml is None else " / %d" % ml))
                     if len(lw) > 1 else "")
            self.l_px.configure(
                text="pixels %dpx  vs  %dpx limit (%s)%s%s" % (
                    maxpx, lim["max_px"], lim["context"], extra,
                    "   OVER BY %dpx" % (maxpx - lim["max_px"])
                    if maxpx > lim["max_px"] else ""),
                foreground=_theme.TH_BAD if maxpx > lim["max_px"] else _theme.TH_OK)
        else:
            self.l_px.configure(
                text="pixels %dpx  (no pinned surface limit)" % maxpx)
        self._render_inspector(items, bad, un, pad if lim else 0)

    def _render_inspector(self, items, bad, un, pad):
        self.insp.configure(state="normal")
        self.insp.delete("1.0", "end")
        for line, x, kind, b in items:
            if kind == "e":
                self.insp.insert("end",
                                 "line%d  x%-3d  ESCAPE  %dpx\n" % (line, x, b))
            else:
                w = font_advance(b) + pad
                ch = chr(b) if 0x20 <= b < 0x7F else "\\x%02x" % b
                self.insp.insert("end",
                    "line%d  x%-3d  '%s'  0x%02X  %dpx\n" % (line, x, ch, b, w))
        for t in bad:
            self.insp.insert("end", "BAD: unencodable %r\n" % t, "bad")
        for op, arg in un:
            self.insp.insert("end", "unresolved 0x%02X:%02X\n" % (op, arg), "bad")
        self.insp.tag_configure(
            "bad", foreground=readable_on(_theme.TH_BAD, _theme.BG_EDIT, 3.0))
        self.insp.configure(state="disabled")

    def _draw_preview(self):
        cv = self.cv
        cv.delete("all")
        if self.idx < 0:
            return
        texts = self._preview_texts()
        sec = self.app.pack.flat[self.idx][0]
        lim = self._row_limit(sec)
        meta = {}
        if lim:
            meta["limit"] = lim["context"]
            meta["glyph_pad"] = lim["glyph_pad"]
        pad = lim["glyph_pad"] if lim else 0
        bad = []
        for t in texts:
            _, _, _, _, _, tb = measure_markup(t, glyph_pad=pad,
                                               expander=self._expander())
            bad.extend(tb)
        r = render_text_to_canvas(cv, texts, meta,
                                  expander=self._expander())
        if r is None:
            return
        _, _, _, limit_px = r
        if bad:
            cv.create_text(8, 20, anchor="nw",
                           text="!! unencodable characters present",
                           fill=readable_on(_theme.TH_BAD, _theme.APP_BG, 3.0),
                           font=FONT_UI_SM)
        if limit_px and len(texts) > 1:
            cv.create_text(4, 4, anchor="nw", text="box", fill="#c8a0ff",
                           font=FONT_UI_SM)

    # -- commands -----------------------------------------------------------
    def _save(self, _e=None):
        self.app.save_pack(ask=False)
        return "break"

    def _fit_budget(self, _e=None):
        if self.idx < 0:
            return
        sec, e = self.app.pack.flat[self.idx]
        txt = self.tr_txt.get("1.0", "end-1c")
        new, _ = truncate_to_budget(txt, row_room(sec, e))
        self.tr_txt.delete("1.0", "end")
        self.tr_txt.insert("1.0", new)
        self.tr_txt.edit_modified(True)
        self._on_modified()
        return "break"

    def _copy_source(self):
        if self.idx >= 0:
            self.tr_txt.delete("1.0", "end")
            self.tr_txt.insert("1.0", self.app.pack.flat[self.idx][1].get("source", ""))
            self._on_modified()

    def _clear_tr(self):
        if self.idx >= 0:
            self.tr_txt.delete("1.0", "end")
            self._on_modified()

    def close(self):
        self.app.wb = None
        self.win.destroy()

    def focus_set(self):
        self.win.focus_set()
