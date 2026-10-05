"""Table selection, keyboard row stepping, box selection and loading an entry.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

from genesisleaf.core.encoding import parse_text


class SelectionMixin:
    """Table selection, keyboard row stepping, box selection and loading an entry.

    Mixed into `App`; `self` is the main window.
    """

    # -- selection ------------------------------------------------------------------
    def _update_sel_count(self):
        """"n selected" beside the Copy key button."""
        if self.l_selcount is None:
            return
        n = len(self.tree.selection())
        self.l_selcount.configure(
            text="no selection" if not n
            else ("1 selected" if n == 1 else "%d selected" % n))

    def _box_iids(self, i):
        """Tree iids of every view row belonging to `i`'s dialog box."""
        rows = self.box_rows(i)
        if len(rows) <= 1:
            return None
        found = []
        for iid, fi in self.view_iid.items():
            if fi in rows:
                found.append(iid)
        return found or None

    def _select_box(self, i):
        """Highlight every tree row of `i`'s box (or just its row).

        `selection_set` fires <<TreeviewSelect>> even when the selection is
        unchanged, which would re-enter select_entry in a loop; only set it
        when it differs from the current selection.
        """
        cur = self.tree.selection()
        if i is None:
            if cur:
                self.tree.selection_remove(*cur)
            self._update_sel_count()
            return
        found = self._box_iids(i)
        if found:
            if tuple(found) != tuple(cur):
                self.tree.selection_set(found)
                self.tree.see(found[0])
            return
        iid = self._iid_of(i)
        if iid and iid not in cur:
            self.tree.selection_set(iid)
            self.tree.see(iid)

    def _iid_of(self, i):
        return self._iid_by_flat.get(i)

    def on_tree_select(self, _evt=None):
        # before the lock guard: the count has to follow programmatic
        # selection changes too, and those arrive with _select_lock set
        self._update_sel_count()
        if self._select_lock:
            return
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        i = self.view_iid.get(iid)
        if i is not None:
            self._reset_edited_walk()
            self.select_entry(i)
            # A shift/ctrl multi-selection (or any selection that is not a
            # plain single row) must be left exactly as the user made it -
            # collapsing it to `sel[0]`'s box would destroy the range.  Only a
            # bare single click expands to the whole box - and only when the
            # checkbox is on: unchecked, a click stays on its one row and the
            # editor follows the user's own selection.
            if len(sel) == 1 and self.multi_var.get():
                self._select_lock = True
                try:
                    self._select_box(i)
                finally:
                    self._select_lock = False

    def _on_rowkey(self, evt):
        sel = self.tree.selection()
        if not sel:
            return
        kids = self.tree.get_children()
        if not kids:
            return
        # step by the box size: a 3-row dialog box advances the whole block when
        # the checkbox is on; unchecked, arrows walk one row at a time
        step = 1
        i = self.view_iid.get(sel[0])
        if i is not None and self.multi_var.get():
            rows = self.box_rows(i)
            if len(rows) > 1:
                step = len(rows)
        pos = self.tree.index(sel[0])
        if evt.keysym == "Down":
            target = pos + step
        elif evt.keysym == "Up":
            target = pos - step
        elif evt.keysym == "Next":
            target = pos + 10
        else:
            target = pos - 10
        target = max(0, min(target, len(kids) - 1))
        iid = kids[target]
        i = self.view_iid.get(iid)
        if i is None:
            return "break"
        # Scroll the destination into view *before* selecting, otherwise a
        # jump from a search hit or an auto-selection to the next row can move
        # the selection off-screen and leave the table looking frozen.
        self.tree.see(iid)
        self.select_entry(i)
        self._select_lock = True
        try:
            if self.multi_var.get():
                self._select_box(i)
            else:
                self.tree.selection_set(iid)
        finally:
            self._select_lock = False
        return "break"

    def _alt_nav(self, evt, keysym, multi=False):
        """Alt+Arrow: navigate the main table from anywhere.

        `multi=False` (Alt+Arrow) – moves the single selection, identical to
        clicking a row.  `multi=True` (Alt+Shift+Arrow) – extends the existing
        selection to include the target row without collapsing rows that were
        already selected, mirroring Shift+Click behaviour.
        """
        kids = self.tree.get_children()
        if not kids:
            return "break"
        sel = self.tree.selection()
        if not sel:
            # nothing selected yet – start from the first visible row
            self.tree.see(kids[0])
            self.select_entry(self.view_iid.get(kids[0], 0))
            self.tree.selection_set(kids[0])
            return "break"
        step = 1
        i = self.view_iid.get(sel[0])
        if i is not None and self.multi_var.get() and not multi:
            rows = self.box_rows(i)
            if len(rows) > 1:
                step = len(rows)
        pos = self.tree.index(sel[0])
        if keysym == "Down":
            target = pos + step
        elif keysym == "Up":
            target = pos - step
        elif keysym == "Next":
            target = pos + 10
        else:
            target = pos - 10
        target = max(0, min(target, len(kids) - 1))
        iid = kids[target]
        ti = self.view_iid.get(iid)
        if ti is None:
            return "break"
        self.tree.see(iid)
        if multi:
            # extend: add everything between anchor and target to selection
            anchor_pos = pos
            lo, hi = min(anchor_pos, target), max(anchor_pos, target)
            span = [kids[p] for p in range(lo, hi + 1)]
            cur = set(self.tree.selection())
            self._select_lock = True
            try:
                self.tree.selection_set(list(cur | set(span)))
            finally:
                self._select_lock = False
        else:
            self.select_entry(ti)
            self._select_lock = True
            try:
                if self.multi_var.get():
                    self._select_box(ti)
                else:
                    self.tree.selection_set(iid)
            finally:
                self._select_lock = False
        return "break"

    def on_tree_delete(self, _evt=None):
        """Delete clears the translation of every selected row, not just the
        highlighted one.

        It used to clear `self.current` alone, so a ctrl/click selection of ten
        rows looked like it had done nothing at all - nine of them kept their
        text.  The bulk write follows `_on_paste_rows`, which already has to
        touch many rows at once and therefore already knows how to keep the
        table, the per-line editors and the ownership/date bookkeeping in step.
        """
        idxs = self._selected_flat_in_order()
        if not idxs:
            # no selection (the key can reach us with the tree unfocused):
            # keep the old single-row behaviour
            if self.current < 0:
                return
            self.clear_translation()
            return "break"
        if len(idxs) == 1 and idxs[0] == self.current:
            self.clear_translation()
            return "break"
        changed = False
        cells = []
        for i in idxs:
            _, e = self.pack.flat[i]
            if not e.get("translation", ""):
                continue
            cells.append((i, e.get("translation", ""), ""))
            e["translation"] = ""
            self._own(e)
            changed = True
            self.dirty = True
            # the single-row path runs through on_tr_modified(), which
            # schedules the debounced join; do the same here so clearing a
            # whole selection refills from duplicates exactly as clearing one
            # row would.  The debounce collapses these into a single pass.
            self._schedule_join(i)
            iid = self._iid_of(i)
            if iid is not None:
                self.update_tree_row(iid, i)
            self._refresh_ed_line(i)
        if not changed:
            return "break"
        self.note_edit("Clear", cells)
        # the highlighted row's own editor has to be reloaded from the pack:
        # set_translation() was not used for it, so nothing has pushed "" into
        # the widget yet
        self._find_hits = None
        if self.current in idxs:
            self._sync_tr_editors(self.current)
        self.invalidate_stats()
        self.update_preview()
        self.update_status()
        return "break"

    def select_entry(self, i, force_update=True):
        if 0 <= i < len(self.pack.flat):
            self.current = i
            self._loading = True
            try:
                self._load_meta(i)
                self._sync_tr_editors(i)
                self._update_words()
            finally:
                self._loading = False
            self.update_preview()
            self.update_status()
        self._update_clone_label()

    def _load_meta(self, i):
        _, e = self.pack.flat[i]
        self.l_sec.configure(text=self.pack.flat[i][0])
        self.l_key.configure(text=e.get("key", ""))
        self.e_context.configure(state="normal")
        self.e_context.delete(0, "end")
        self.e_context.insert(0, e.get("context", ""))
        self.e_context.configure(state="readonly")
        sb, _ = parse_text(e.get("source", ""))
        self.l_src_bytes.configure(text="source %d B" % sb)
        budget = int(e.get("budget", sb))
        self.l_budget.configure(text="- / %d B" % budget)
        self.src_txt.configure(state="normal")
        self.src_txt.delete("1.0", "end")
        rows = self._ed_rows_for(i)
        if len(rows) > 1:
            src_lines = []
            for j in rows:
                _, re_ = self.pack.flat[j]
                src_lines.append(re_.get("source", ""))
            self.src_txt.insert("1.0", "\n".join(src_lines))
            self.src_txt.configure(height=min(4, max(2, len(rows) + 1)))
        else:
            self.src_txt.insert("1.0", e.get("source", ""))
            self.src_txt.configure(height=2)
        self.retag(self.src_txt, allow_over=False)
        self.src_txt.configure(state="disabled")
        self.note_ent.delete(0, "end")
        self.note_ent.insert(0, self.notes.get(e.get("key", ""), ""))

    def _selected_flat_in_order(self):
        """Flat indices of the selected table rows, in row order."""
        out = []
        for iid in self.tree.selection():
            i = self.view_iid.get(iid)
            if i is not None:
                out.append(i)
        return out
