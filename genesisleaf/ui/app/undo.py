"""Undo / redo plumbing on top of core.history and the History window.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk

from genesisleaf.core.history import EditOp
from genesisleaf.ui.windows.history_window import HistoryWindow


class UndoMixin:
    """Undo / redo plumbing on top of core.history and the History window.

    Mixed into `App`; `self` is the main window.
    """

    # -- undo / redo ------------------------------------------------------
    def note_edit(self, label, cells, mergeable=False):
        """Record a change that has just been applied to the pack.

        `cells` is `[(flat_idx, old_text, new_text), ...]`.  Nothing is recorded
        while a replay is running, so undoing never pushes a new step."""
        if self._replaying:
            return
        cells = [list(c) for c in cells if c[1] != c[2]]
        if not cells:
            return
        self.history.record(EditOp(label, cells, mergeable))
        self._sync_history_ui()

    def do_undo(self, _evt=None):
        got = self.history.undo()
        if got is None:
            self.flash("nothing to undo")
            return "break"
        op, forward = got
        self._replay(op, forward)
        return "break"

    def do_redo(self, _evt=None):
        got = self.history.redo()
        if got is None:
            self.flash("nothing to redo")
            return "break"
        op, forward = got
        self._replay(op, forward)
        return "break"

    def _update_history_menu(self):
        """Label the Undo/Redo entries after the step they will step, the way
        every editor does it - "what will Ctrl+Z do" is more useful than a
        greyed-out item."""
        h = self.history
        try:
            if h.undo_stack:
                op = h.undo_stack[-1]
                self._edit_menu.entryconfig(
                    self._undo_idx, label="Undo %s" % op.describe(),
                    state="normal")
            else:
                self._edit_menu.entryconfig(
                    self._undo_idx, label="Undo", state="disabled")
            if h.redo_stack:
                op = h.redo_stack[-1]
                self._edit_menu.entryconfig(
                    self._redo_idx, label="Redo %s" % op.describe(),
                    state="normal")
            else:
                self._edit_menu.entryconfig(
                    self._redo_idx, label="Redo", state="disabled")
        except (AttributeError, tk.TclError):
            pass

    def clear_history(self, _evt=None):
        self.history.clear()
        self._sync_history_ui()
        self.flash("history cleared")

    def open_history(self, _evt=None):
        """The step list, so the history is visible rather than something you
        have to discover by pressing Ctrl+Z."""
        if self._hist_window is not None:
            try:
                self._hist_window.lift()
                self._hist_window.refresh()
                return
            except tk.TclError:
                self._hist_window = None
        self._hist_window = HistoryWindow(self)

    def _replay(self, op, forward):
        """Put an op's cells into their old (undo) or new (redo) state."""
        which = 2 if forward else 1
        idxs = []
        self._replaying = True
        try:
            for c in op.cells:
                i = c[0]
                if not (0 <= i < len(self.pack.flat)):
                    continue
                _sec, e = self.pack.flat[i]
                e["translation"] = c[which]
                self._own(e)
                self.dirty = True
                idxs.append(i)
                iid = self._iid_of(i)
                if iid is not None:
                    self.update_tree_row(iid, i)
        finally:
            self._replaying = False
        if idxs:
            self._find_hits = None
            self.invalidate_stats()
            for v in self._views:
                v.sync_cells(idxs)
            if self.current in idxs:
                self._sync_tr_editors(self.current)
            self._bytes_label()
            self.update_preview()
        self.flash("%s: %s" % ("Redo" if forward else "Undo",
                               op.describe()))
        self._sync_history_ui()

    def _sync_history_ui(self):
        """Keep the Edit menu's Undo/Redo labels and the history window in
        step with the stacks, in every window."""
        for fn in (self._update_history_menu,):
            try:
                fn()
            except (AttributeError, tk.TclError):
                pass
        w = self._hist_window
        if w is not None:
            try:
                w.refresh()
            except (AttributeError, tk.TclError):
                pass
