"""Opens the workbench window and commits its edits back into the pack.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

from tkinter import messagebox

from genesisleaf.ui.windows.workbench import WorkbenchWindow


class WorkbenchLinkMixin:
    """Opens the workbench window and commits its edits back into the pack.

    Mixed into `App`; `self` is the main window.
    """

    # -- translation workbench --------------------------------------------------
    def open_workbench(self):
        """Open (or raise) the dynamic-editor workbench window."""
        if not (self.pack and self.pack.flat):
            messagebox.showwarning("Translation workbench",
                                   "Open a pack first.")
            return
        if self.wb is None or not self.wb.win.winfo_exists():
            self.wb = WorkbenchWindow(self)
        else:
            self.wb.win.deiconify()
            self.wb.win.lift()
            self.wb.focus_set()

    def wb_commit(self, idx, val):
        """Write `val` as entry `idx`'s translation from the workbench window.
        Mirrors on_tr_modified's write-back so both editors agree; if `idx`
        is the main editor's current entry, refresh the main UI too."""
        _, e = self.pack.flat[idx]
        if e.get("translation", "") != val:
            self.note_edit("Workbench", [(idx, e.get("translation", ""), val)],
                           mergeable=True)
            e["translation"] = val
            self._own(e)
            self.dirty = True
            self.invalidate_stats()
        if self.current == idx:
            self._bytes_label()
            self.update_preview()
            self.update_status()
            sel = self.tree.selection()
            if sel:
                iid = sel[0]
                if self.view_iid.get(iid) == idx:
                    self.update_tree_row(iid, idx)
