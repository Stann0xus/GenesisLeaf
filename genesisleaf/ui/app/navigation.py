"""Jumping and stepping: next/prev entry, next untranslated, 'Edited' walk-back.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

from genesisleaf.core.bookkeeping import edited_on


class NavigationMixin:
    """Jumping and stepping: next/prev entry, next untranslated, 'Edited' walk-back.

    Mixed into `App`; `self` is the main window.
    """

    def _edited_history(self):
        """Flat indices of every hand-edited row, newest first.

        Ordered by the stored `edited` stamp, with the in-memory session counter
        as the tiebreak when two rows share a minute, and the file position as
        the last resort for a freshly loaded pack."""
        rows = []
        for i, (_sec, e) in enumerate(self.pack.flat):
            stamp = edited_on(e)
            if not stamp:
                continue
            rows.append((stamp, self._edit_seq.get(id(e), -1), i))
        rows.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
        return [t[2] for t in rows]

    def goto_last_edited(self):
        """Step one row further back through the edit history.

        Repeated presses walk from the most recent edit to the oldest and then
        stay put; moving the selection by hand resets the walk, so the button
        always continues from wherever you actually are."""
        hist = self._edited_history()
        if not hist:
            self.l_edited.configure(text="no history")
            return
        nxt = min(self._hist_pos + 1, len(hist) - 1)
        self._hist_pos = nxt
        i = hist[nxt]
        self._hist_walk = True
        try:
            self.jump_to_flat(i)
        finally:
            self._hist_walk = False
        self.l_edited.configure(
            text="%d/%d back" % (nxt + 1, len(hist)))
        self.b_edited.configure(
            text="Edited" if nxt + 1 < len(hist) else "Edited (oldest)")

    def _reset_edited_walk(self):
        """Called whenever the selection moves on its own.

        Skipped while the button itself is walking the history, because the jump
        selects rows programmatically and would otherwise cancel its own walk on
        the very first press."""
        if getattr(self, "_hist_walk", False):
            return
        if getattr(self, "_hist_pos", -1) != -1:
            self._hist_pos = -1
            if hasattr(self, "l_edited"):
                self.l_edited.configure(text="")
            if hasattr(self, "b_edited"):
                self.b_edited.configure(text="Edited")

    def jump_to_flat(self, i, keep_search=False):
        """Select and scroll to flat row `i`.

        `keep_search` leaves the Find box alone when the row is hidden by a
        filter: the word-search tab wants the box emptied so the row shows, but
        Next Clone and the Filter-off find are *driven* by that text, so it has
        to stay put - the section/status filters are dropped instead, and the
        Find text is held out of `_filters` for that one rebuild."""
        self.select_entry(i)
        if self._iid_of(i) is None:
            self.filter_section = "All"
            self.filter_status = "All"
            self.filter_context = "All"
            self.filter_field = "Section"
            self.filter_value = "All"
            if hasattr(self, "filter_by_cb"):
                self.filter_by_cb.set("Section")
            self.sec_cb.current(0)
            self.st_cb.current(0)
            self.ctx_cb.current(0)
            if keep_search and not self.find_filter_var.get():
                self._search_ignore = True
                try:
                    self.rebuild_view()
                finally:
                    self._search_ignore = False
            else:
                self.filter_text = ""
                self.search_ent.delete(0, "end")
                self.rebuild_view()
        self._jump_data = (i, 100)
        self._reveal_jump()

    def _reveal_jump(self):
        data = self._jump_data
        if not data:
            return
        i, tries = data
        for iid, fi in list(self.view_iid.items()):
            if fi == i:
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self._jump_data = None
                return
        if tries > 0:
            self._jump_data = (i, tries - 1)
            self.root.after(80, self._reveal_jump)
        else:
            self._jump_data = None

    # -- navigation -----------------------------------------------------------------
    def next_entry(self):
        self._nav(1)

    def prev_entry(self):
        self._nav(-1)

    def _nav(self, d):
        if not self.view:
            return
        cur = self._view_pos()
        nxt = cur + d
        if 0 <= nxt < len(self.view):
            self._select_view(nxt)

    def _view_pos(self):
        for pos, i in enumerate(self.view):
            if i == self.current:
                return pos
        return -1

    def _select_view(self, pos):
        if not (0 <= pos < len(self.view)):
            return
        i = self.view[pos]
        # Bring the row on screen: the arrow keys, "next untranslated" and the
        # entry steppers all land here, and a jump that leaves the selection
        # off-screen reads as a frozen table.
        iid = self._iid_of(i)
        if iid is not None:
            self.tree.see(iid)
        self.select_entry(i)
        self._select_lock = True
        try:
            self._select_box(i)
        finally:
            self._select_lock = False

    def next_empty(self):
        self._step(1, empty=True)

    def prev_empty(self):
        self._step(-1, empty=True)

    def _step(self, d, empty):
        if not self.view:
            return
        n = len(self.view)
        pos = self._view_pos()
        if pos < 0:
            pos = 0 if d > 0 else n - 1
        i = pos
        for _ in range(n):
            i = (i + d) % n
            if empty:
                if not self.pack.flat[self.view[i]][1].get("translation", ""):
                    self._select_view(i)
                    return
            else:
                self._select_view(i)
                return
