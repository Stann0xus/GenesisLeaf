"""The main entry table: build, filtered rebuild, sorting, row state & bands.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from genesisleaf.core.encoding import bad_cf_codes, parse_text
from genesisleaf.core.space import verdict as space_verdict
from genesisleaf.ui.cellsel import CellSelection
from genesisleaf.ui.widgets import TreeRowTip
from genesisleaf.ui.fonts import FONT_UI_B, FONT_UI_SM, font_family, font_size
from genesisleaf.ui import theme as _theme
from genesisleaf.ui.app.notes import NOTE_MARK


class TableMixin:
    """The main entry table: build, filtered rebuild, sorting, row state & bands.

    Mixed into `App`; `self` is the main window.
    """

    # -- entries table (left half, always visible) --------------------------
    def _build_entries_tab(self, parent):
        f = ttk.Frame(parent, padding=(2, 0, 2, 0))
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)

        self.tree = ttk.Treeview(
            f,
            columns=("ord", "st", "note", "sec", "key", "context", "source",
                     "tr", "bytes"),
            show="headings", selectmode="extended", style="Entries.Treeview")
        hdr = {"ord": ("#", 46), "st": ("", 28), "note": (NOTE_MARK, 24),
               "sec": ("Section", 86),
               "key": ("Key", 200), "context": ("Context", 160),
               "source": ("Source", 210), "tr": ("Translation", 210),
               "bytes": ("B/S", 58)}
        self._hdr = hdr
        for col, (txt, w) in hdr.items():
            self.tree.heading(col, text=txt,
                              command=lambda c=col: self.sort_by(c))
            self.tree.column(col, width=w, anchor="w",
                             stretch=(col not in ("ord", "st", "note")))
        self.tree.column("note", anchor="center")
        self.tree.column("bytes", anchor="e")
        self.tree.column("ord", anchor="e")
        vs = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(f, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        vs.grid(row=1, column=1, sticky="ns")
        hs.grid(row=2, column=0, sticky="ew")
        self.apply_tree_tags()
        # Row bands are a separate tag from the status colour above, so a row
        # carries two tags at once: one for "translated / over budget", one for
        # "which band".  The band flips per dialogue UNIT, never per row, so
        # every line of a dialogue box sits on the same background and a box
        # reads as one block.  View-only: no data depends on it.
        self.tree.tag_configure("band_a", background=_theme.TH_BAND_A)
        self.tree.tag_configure("band_b", background=_theme.TH_BAND_B)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Delete>", self.on_tree_delete)
        self.tree.bind("<Up>", self._on_rowkey)
        self.tree.bind("<Down>", self._on_rowkey)
        self.tree.bind("<Prior>", self._on_rowkey)
        self.tree.bind("<Next>", self._on_rowkey)
        self.tree.bind("<Control-c>", self._on_copy_rows)
        self.tree.bind("<Control-v>", self._on_paste_rows)
        # Ctrl+wheel zooms the table text (View > Table zoom)
        self.tree.bind("<Control-MouseWheel>", self._table_wheel_zoom)
        # entries carrying `notes`: tooltip on hover, Alt+double-click opens
        # the Notes dashboard (ui/app/notes.py)
        TreeRowTip(self.tree, self._table_row_tip)
        self.tree.bind("<Alt-Double-Button-1>", self._table_alt_dbl)
        # what the table shows when it has no rows (no pack / no matches)
        self._empty = ttk.Frame(f, padding=24, style="Window.TFrame")
        self._empty_lab = ttk.Label(self._empty, text="", justify="center",
                                    font=FONT_UI_B)
        self._empty_lab.pack()
        self._empty_sub = ttk.Label(self._empty, text="", justify="center",
                                    font=FONT_UI_SM,
                                    foreground=_theme.TH_FG_MUTED)
        self._empty_sub.pack(pady=(4, 10))
        self._empty_btn = ttk.Button(self._empty, text="")
        self._empty_btn.pack()
        # Ctrl+Click picks single cells (spreadsheet style); plain clicks
        # stay row selection - see ui/cellsel.py
        self.cellsel = CellSelection(self.tree, on_pick=self._on_cells_picked,
                                     on_copy=self._push_clip_history)
        return f

    def rebuild_view(self):
        self.filter_section = self.sec_cb.get() or "All"
        self.filter_status = self.st_cb.get() or "All"
        self.filter_context = self.ctx_cb.get() or "All"
        self._ctx_match = (None if self.filter_context == "All"
                           else self._ctx_set_for(self.filter_context))
        self._find_hits = None      # the table just changed under the finder
        # Filter off means the Find text never narrows the table, it only drives
        # the selection; `_search_ignore` covers the one rebuild that has to
        # expose a hit hidden by the section/status filters.
        if self.find_filter_var.get() or self._search_ignore:
            self.filter_text = self.search_ent.get().strip()
        else:
            self.filter_text = ""
        gen = self._view_gen + 1
        self._view_gen = gen
        idxs = [i for i in range(len(self.pack.flat)) if self._filters(i)]
        # Find filter on: widen every hit to its whole dialogue box, so a
        # match on one line shows the complete conversation around it.
        if self.filter_text:
            boxed = set()
            for i in idxs:
                try:
                    boxed.update(self.box_rows(i))
                except Exception:
                    boxed.add(i)
            idxs = sorted(boxed)
        self.view_iid = {}
        self._iid_by_flat = {}
        self._pos_iids = []
        self._band_of = {}
        self._band_state = {"unit": None, "n": 0}
        if self._sort_col:
            idxs = sorted(idxs, key=self._sort_key, reverse=self._sort_rev)
        self.plan = [("r", i) for i in idxs]
        self.view = [i for t, i in self.plan if t == "r"]
        self.cellsel.clear()           # the row iids are about to change
        self.tree.delete(*self.tree.get_children())
        self._refresh_ctx_filter()
        if not self.view:
            self.update_status()
            self.nav_lab.configure(text="0 shown")
            self._update_empty_state()
            return
        self.tree.configure(cursor="watch")
        self._insert_plan(0, gen)
        self.update_status()
        self.nav_lab.configure(text="%d shown" % len(self.view))
        self._update_sel_count()
        self._update_empty_state()

    def _update_empty_state(self):
        """Explain an empty table instead of showing a blank grid."""
        if self.view:
            self._empty.place_forget()
            return
        if not (self.pack and self.pack.flat):
            title = "No pack loaded"
            sub = ("Open a translation pack (.yaml) exported by the "
                   "legend-of-legaia-re toolchain.")
            btn, cmd = "Open pack...  (Ctrl+O)", self.open_pack
        else:
            title = "No rows match"
            sub = "The section, status, context or Find filters hide every row."
            btn, cmd = "Show everything", self.clear_filters
        self._empty_lab.configure(text=title)
        self._empty_sub.configure(text=sub)
        self._empty_btn.configure(text=btn, command=cmd)
        self._empty.place(relx=0.5, rely=0.4, anchor="center")
        self._empty.lift()

    def clear_filters(self):
        """Reset section, status, context and Find in one go."""
        self.sec_cb.set("All")
        self.st_cb.set("All")
        self.ctx_cb.set("All")
        self.filter_field = "Section"
        self.filter_value = "All"
        if hasattr(self, "filter_by_cb"):
            self.filter_by_cb.set("Section")
        self.search_ent.delete(0, "end")
        self._find_hits = None
        self.find_lab.configure(text="")
        self.rebuild_view()

    # -- table zoom ------------------------------------------------------------
    def _table_wheel_zoom(self, evt):
        self.zoom_table(1 if evt.delta > 0 else -1)
        return "break"

    def zoom_table(self, step=0):
        """Grow / shrink the entry tables' text (0 = reset)."""
        self._table_zoom = 0 if step == 0 else max(
            -4, min(12, getattr(self, "_table_zoom", 0) + step))
        self.apply_table_zoom()
        self.flash("table text %+d" % self._table_zoom if self._table_zoom
                   else "table text reset")

    def apply_table_zoom(self):
        """Entries.Treeview font and row height for the current zoom (also
        re-run by apply_theme, which resets the base Treeview style)."""
        size = max(6, font_size() - 2 + getattr(self, "_table_zoom", 0))
        fo = getattr(self, "_table_font", None)
        if fo is None:
            fo = self._table_font = tkfont.Font(self.root, name="lt.table",
                                                family=font_family(),
                                                size=size)
        else:
            fo.configure(family=font_family(), size=size)
        try:
            self.style.configure("Entries.Treeview", font="lt.table",
                                 rowheight=int(fo.metrics("linespace") * 1.35))
        except tk.TclError:
            pass

    # -- column-header sorting ---------------------------------------------------
    def sort_by(self, col):
        if self._sort_col != col:
            self._sort_col = col
            self._sort_rev = False
        elif not self._sort_rev:
            self._sort_rev = True
        else:
            self._sort_col = None
            self._sort_rev = False
        self._mark_sort_heading()
        self.rebuild_view()

    def clear_sort(self):
        if self._sort_col is None:
            return
        self._sort_col = None
        self._sort_rev = False
        self._mark_sort_heading()
        self.rebuild_view()

    def _mark_sort_heading(self):
        for col, (txt, w) in self._hdr.items():
            t = txt
            if self._sort_col == col:
                t = "%s %s" % (txt, "▲" if not self._sort_rev else "▼")
            self.tree.heading(col, text=t)
        if getattr(self, "l_sort", None) is not None:
            if self._sort_col:
                self.l_sort.configure(
                    text="sorted by %s%s" % (
                        self._hdr[self._sort_col][0],
                        " desc" if self._sort_rev else ""))
                if hasattr(self, "b_clear_sort"):
                    self.b_clear_sort.pack(side="left", padx=(4, 8))
            else:
                self.l_sort.configure(text="")
                if hasattr(self, "b_clear_sort"):
                    self.b_clear_sort.pack_forget()

    def _sort_key(self, i):
        col = self._sort_col
        sec, e = self.pack.flat[i]
        if col == "ord":
            return (i,)
        if col == "st":
            tr = e.get("translation", "")
            b, spans = parse_text(tr)
            sb, _ = parse_text(e.get("source", ""))
            if any(st == "nonascii" for _, _, st in spans):
                return (4,)
            v = space_verdict(sec, e, b)
            if v == "over":
                return (3,)
            if v == "grows":
                return (2,)
            return (1,) if tr else (0,)
        if col == "bytes":
            tr = e.get("translation", "")
            b, _ = parse_text(tr)
            sb, _ = parse_text(e.get("source", ""))
            budget = int(e.get("budget", sb))
            return (b, budget)
        if col == "sec":
            return (sec.lower(),)
        if col == "note":
            return (0 if e.get("notes") else 1, i)
        vmap = {"key": "key", "context": "context",
                "source": "source", "tr": "translation"}
        return (e.get(vmap[col], "").lower(),)

    def _band_for(self, i):
        """Which band row `i` goes on, as a Treeview tag.

        Alternates once per dialogue unit rather than once per row, so every
        line of one box shares a background and the box reads as a single
        block.  A lone row (the single-string sections) is its own unit, so
        those alternate row by row.

        The unit is read straight out of the cached box map - `box_rows` would
        rescan the whole map per call, which is quadratic over a 31k pack.
        `self._band_state` carries the flip across the chunked insert calls."""
        row = self.box_map().get(i)
        unit = row[0] if row is not None else i
        st = self._band_state
        if st["unit"] != unit:
            st["unit"] = unit
            st["n"] += 1
        return "band_a" if st["n"] % 2 else "band_b"

    def _insert_plan(self, k, gen):
        CHUNK = 1200
        end = min(k + CHUNK, len(self.plan))
        for t, x in self.plan[k:end]:
            self.tree_insert_row(x)
        self.tree.configure(cursor="")
        if end < len(self.plan):
            self.root.after_idle(lambda: self._finish_insert(end, gen))
        elif gen == self._view_gen:
            # the last chunk is in the tree - if a load is still showing its
            # overlay, this is the moment it may close
            self._finish_loading()

    def _finish_insert(self, end, gen):
        if gen != self._view_gen:
            return
        self._insert_plan(end, gen)

    def _row_state(self, i):
        """`(mark, tag, bytes, budget, translation)` for one flat row.

        The single source of truth for both the first render
        (`tree_insert_row`) and every keystroke afterwards
        (`update_tree_row`).  They used to compute this independently, and when
        they drifted the row's colour and the row's cells could describe two
        different translations until the whole table was rebuilt.
        """
        sec, e = self.pack.flat[i]
        tr = e.get("translation", "")
        b, _ = parse_text(tr)
        sb, _ = parse_text(e.get("source", ""))
        budget = int(e.get("budget", sb))
        non = any(st == "nonascii" for _, _, st in parse_text(tr)[1])
        v = space_verdict(sec, e, b) if tr else "fits"
        badcf = bool(bad_cf_codes(tr))
        if badcf:
            mark, tag = "#", "non"
        elif non:
            mark, tag = "@", "non"
        elif v == "over":
            mark, tag = "!", "warn"
        elif v == "grows":
            # longer than its in-place span, but the importer moves / regrows
            # it into free space (core.space) - not an error
            mark, tag = "+", "grow"
        elif tr:
            mark, tag = "*", "ok"
        else:
            mark, tag = "", "off"
        # Overdraw is orthogonal to the status above: a row can be perfectly
        # valid *and* run off the edge of its box, and losing the "over budget"
        # bang to a width hint would be a downgrade.  So it rides along as its
        # own tag instead of replacing one.  The test is the real font measured
        # against the surface *this* row is drawn on (a party name gets 56px, a
        # dialogue box 244px), and a section with no known surface is left
        # alone rather than judged against a dialogue box's limit.
        over = ""
        _s_px, s_over, s_checked = self.row_overdraw(i, e.get("source", ""))
        _t_px, t_over, t_checked = self.row_overdraw(i, tr)
        if s_checked and s_over:
            over = "s"
        if t_checked and t_over:
            over += "t"
        return mark, tag, b, budget, tr, over

    def tree_insert_row(self, i, parent=None):
        _, e = self.pack.flat[i]
        key = e.get("key", "")
        sec = self.pack.flat[i][0]
        ctx = e.get("context", "")
        src = e.get("source", "")
        mark, tag, b, budget, tr, over = self._row_state(i)
        band = self._band_for(i)
        # values and tags in one Tk call - this runs once per row on load
        iid = self.tree.insert("", "end", values=(
            i + 1, mark, NOTE_MARK if e.get("notes") else "", sec, key, ctx,
            src, tr, "%d/%d" % (b, budget)),
            tags=self._row_tags(tag, over, band))
        self._band_of[iid] = band
        self.view_iid[iid] = i
        self._iid_by_flat[i] = iid
        self._pos_iids.append(iid)
        return iid

    def _row_tags(self, tag, over, band):
        """Assemble a row's tag tuple in draw order.

        Tk applies tags left to right and lets a later tag win, so the order
        is the priority: the overdraw colour has to come after `off`/`ok` (a
        faint untranslated row should still show orange when it is too long)
        but before nothing else - and the band only ever sets a background, so
        its position does not matter."""
        tags = []
        if tag:
            tags.append(tag)
        if "s" in over:
            tags.append("over_src")
        if "t" in over:
            tags.append("over_tr")
        if band:
            tags.append(band)
        return tuple(tags)

    def view_row_update_all(self):
        for iid, i in list(self.view_iid.items()):
            self.update_tree_row(iid, i)

    def update_tree_row(self, iid, i):
        mark, tag, b, budget, tr, over = self._row_state(i)
        # keep the band the row was inserted on: re-deriving it here would
        # flip the stripes, because a single re-render is not a full pass over
        # the units in view order
        band = self._band_of.get(iid)
        self.tree.item(iid, tags=self._row_tags(tag, over, band))
        self.tree.set(iid, "ord", i + 1)
        # the cells too, not just the colour: the mark, the visible
        # translation and the byte counter are the whole point of watching the
        # table while you type
        self.tree.set(iid, "st", mark)
        self.tree.set(iid, "note",
                      NOTE_MARK if self.pack.flat[i][1].get("notes") else "")
        self.tree.set(iid, "tr", tr)
        self.tree.set(iid, "bytes", "%d/%d" % (b, budget))
        # Live sync: every data change in the program passes through here, so
        # this is the one place that has to tell the other view windows.  A
        # view ignores the notification while it is the one that made the
        # change, so this cannot recurse and cannot fight the user's caret.
        self.notify_views(i)

    def notify_views(self, i):
        for v in list(getattr(self, "_views", None) or ()):
            v.external_row_changed(i)
