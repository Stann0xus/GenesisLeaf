"""Table selection, keyboard row stepping, box selection and loading an entry.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

from contextlib import nullcontext

from genesisleaf.core.encoding import parse_text
from genesisleaf.diagnostics import current as current_diagnostics


class SelectionMixin:
    """Table selection, keyboard row stepping, box selection and loading an entry.

    Mixed into `App`; `self` is the main window.
    """

    # -- selection ------------------------------------------------------------------
    def _see_if_needed(self, iid):
        """Avoid Treeview.see's layout work for an already visible row."""
        monitor = current_diagnostics()
        pos = self._pos_by_iid.get(iid)
        if pos is not None and self._pos_iids:
            y_range = getattr(self, "_tree_y_range", None)
            first, last = y_range if y_range is not None else self.tree.yview()
            count = len(self._pos_iids)
            if first * count <= pos and pos + 1 <= last * count:
                if monitor is not None:
                    monitor.event("ROW_VISIBILITY", row=pos, visible=True,
                                  first=round(first, 5), last=round(last, 5))
                return
        if monitor is not None:
            monitor.event("ROW_VISIBILITY", row=pos, visible=False)
        self.tree.see(iid)

    def _set_tree_selection(self, wanted, current=None):
        """Apply a selection once and ignore its queued synthetic event."""
        cur = self.tree.selection() if current is None else current
        old, new = set(cur), set(wanted)
        removed = [iid for iid in cur if iid not in new]
        added = [iid for iid in wanted if iid not in old]
        if not removed and not added:
            return
        monitor = current_diagnostics()
        if monitor is not None:
            monitor.event("TREE_SELECTION_DELTA", remove=len(removed),
                          add=len(added), existing=len(cur))
        self._tree_auto_selection = frozenset(new)
        if removed and added:
            self.tree.selection_set(wanted)
        elif removed:
            self.tree.selection_remove(*removed)
        else:
            self.tree.selection_add(*added)

    def _update_sel_count(self, selection=None):
        """"n selected" beside the Copy key button."""
        if self.l_selcount is None:
            return
        n = len(self.tree.selection() if selection is None else selection)
        label = ("no selection" if not n else
                 "1 selected" if n == 1 else "%d selected" % n)
        if getattr(self, "_sel_count_label", None) != label:
            self._sel_count_label = label
            self.l_selcount.configure(text=label)

    def _box_iids(self, i):
        """Tree iids of every view row belonging to `i`'s dialog box."""
        rows = self.box_rows(i)
        if len(rows) <= 1:
            return None
        # The reverse index is maintained as table chunks are inserted. A
        # full view scan here made every click cost O(pack size).
        found = [iid for row in rows
                 if (iid := self._iid_by_flat.get(row)) is not None]
        return found or None

    def _select_box(self, i, current_selection=None):
        """Highlight every tree row of `i`'s box (or just its row).

        `selection_set` fires <<TreeviewSelect>> even when the selection is
        unchanged, which would re-enter select_entry in a loop; only set it
        when it differs from the current selection.
        """
        cur = self.tree.selection() if current_selection is None else current_selection
        if i is None:
            if cur:
                self.tree.selection_remove(*cur)
            self._update_sel_count()
            return
        found = self._box_iids(i)
        if found:
            if set(found) != set(cur):
                self._set_tree_selection(found, current=cur)
                self._see_if_needed(found[0])
            return
        iid = self._iid_of(i)
        if iid and iid not in cur:
            self._set_tree_selection((iid,), current=cur)
            self._see_if_needed(iid)

    def _iid_of(self, i):
        return self._iid_by_flat.get(i)

    def on_tree_select(self, _evt=None):
        # before the lock guard: the count has to follow programmatic
        # selection changes too, and those arrive with _select_lock set
        sel = self.tree.selection()
        self._update_sel_count(sel)
        if self._select_lock:
            return
        auto = getattr(self, "_tree_auto_selection", None)
        if auto is not None:
            if frozenset(sel) == auto:
                return
            self._tree_auto_selection = None
        if not sel:
            return
        if self.cellsel.active():
            # Tk delivers programmatic selection events after the lock clears.
            # The cell-pick callback already loaded the active (last) row.
            return
        focused = self.tree.focus()
        iid = focused if focused in sel else sel[0]
        i = self.view_iid.get(iid)
        if i is not None:
            self._reset_edited_walk()
            if i != self.current:
                self.select_entry(i)
            else:
                self._sync_tr_editors(i)
                self.update_preview()
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
        monitor = current_diagnostics()
        with (monitor.span("rowkey.read_selection") if monitor else nullcontext()):
            sel = self.tree.selection()
        if not sel:
            return
        kids = self._pos_iids
        if not kids:
            return
        # step by the box size: a 3-row dialog box advances the whole block when
        # the checkbox is on; unchecked, arrows walk one row at a time
        step = 1
        i = self.view_iid.get(sel[0])
        if i is not None and self.multi_var.get():
            with (monitor.span("rowkey.box_lookup") if monitor else nullcontext()):
                rows = self.box_rows(i)
            if len(rows) > 1:
                step = len(rows)
        pos = self._pos_by_iid.get(sel[0])
        if pos is None:
            return "break"
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
        with (monitor.span("rowkey.scroll") if monitor else nullcontext()):
            self._see_if_needed(iid)
        with (monitor.span("rowkey.load_editor") if monitor else nullcontext()):
            self.select_entry(i)
        self._select_lock = True
        try:
            with (monitor.span("rowkey.select_tree") if monitor else nullcontext()):
                if self.multi_var.get():
                    self._select_box(i, current_selection=sel)
                else:
                    self._set_tree_selection((iid,), current=sel)
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
        kids = self._pos_iids
        if not kids:
            return "break"
        sel = self.tree.selection()
        if not sel:
            # nothing selected yet – start from the first visible row
            self._see_if_needed(kids[0])
            self.select_entry(self.view_iid.get(kids[0], 0))
            self._set_tree_selection((kids[0],), current=sel)
            return "break"
        step = 1
        i = self.view_iid.get(sel[0])
        if i is not None and self.multi_var.get() and not multi:
            rows = self.box_rows(i)
            if len(rows) > 1:
                step = len(rows)
        pos = self._pos_by_iid.get(sel[0])
        if pos is None:
            return "break"
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
        self._see_if_needed(iid)
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
                    self._set_tree_selection((iid,), current=sel)
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
            # immediate, not debounced: the preview must repaint together
            # with the table row and editors (see CanvasRenderQueue.request)
            self.update_preview()
            self.update_status()
            self._cmp_follow_main(i)
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
        self.src_txt._tag_content = None
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
