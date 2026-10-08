"""Row/cell copy & paste, cell overlay and the clipboard history window.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.ui.cellsel import clean
from genesisleaf.ui.fonts import FONT_MONO, FONT_UI_SM
from genesisleaf.ui import theme as _theme


class ClipboardMixin:
    """Row/cell copy & paste, cell overlay and the clipboard history window.

    Mixed into `App`; `self` is the main window.
    """

    # ---- main table cell-column tracking ----------------------------------

    def _on_cells_picked(self, rows):
        """Ctrl+Click picked cells: select their rows (without the box
        expansion a plain click does) and load the active cell's row."""
        iid = self.cellsel.last_row() or rows[-1]
        self._select_lock = True
        try:
            if tuple(self.tree.selection()) != tuple(rows):
                self.tree.selection_set(rows)
            self.tree.focus(iid)
            self.tree.see(iid)
        finally:
            self._select_lock = False
        i = self.view_iid.get(iid)
        if i is not None and i != self.current:
            self._reset_edited_walk()
            self.select_entry(i)
        self._update_sel_count()

    def _on_copy_rows(self, _evt=None):
        """Ctrl+C on the table.

        With Ctrl+Clicked cells: copy exactly those cells as a tab/newline
        grid (CellSelection.copy).  Otherwise copy the TRANSLATION of every
        selected row, one per line - the rows Ctrl+V pastes back.  The
        internal row clip always holds translations, so Ctrl+V after either
        kind of copy writes translations only and can never overwrite a
        key, context or source."""
        idxs = self._selected_flat_in_order()
        if not idxs:
            return "break"
        self._row_clip = [self.pack.flat[i][1].get("translation", "")
                          for i in idxs]
        if self.cellsel.active():
            self.cellsel.copy()
            self.update_status()
            return "break"
        text = "\n".join(clean(v) for v in self._row_clip)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._push_clip_history(
            text,
            "[tr] rows %d-%d" % (idxs[0], idxs[-1]) if len(idxs) > 1
            else "[tr] row %d" % idxs[0])
        self.update_status()
        return "break"

    def _push_clip_history(self, text, label):
        """Keep a short, deduped record of what was copied, newest first."""
        if not text:
            return
        text = text.strip("\n")
        if not text:
            return
        if self._clip_hist and self._clip_hist[0][1] == text:
            return
        self._clip_hist.insert(0, (label, text))
        del self._clip_hist[40:]
        w = getattr(self, "_clip_hist_win", None)
        if w is not None and w.winfo_exists():
            self._refresh_clip_hist_win(w)

    # -- clipboard history --------------------------------------------------
    def open_clip_history(self, _evt=None):
        """Options ▸ Clipboard history: the text copied so far, with buttons
        to put any entry back on the clipboard or straight into the editor."""
        win = self._clip_hist_win
        if win is not None:
            try:
                win.lift()
                self._refresh_clip_hist_win(win)
                return
            except tk.TclError:
                self._clip_hist_win = None
        win = tk.Toplevel(self.root)
        win.title("Clipboard history")
        win.geometry("560x360")
        win.transient(self.root)
        self._clip_hist_win = win
        frm = ttk.Frame(win, padding=8)
        frm.pack(fill="both", expand=True)
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        lb = tk.Listbox(frm, font=FONT_MONO, bg=_theme.TH_PANEL_BG, fg=_theme.TH_FG,
                        selectbackground=_theme.TH_SEL_BG,
                        selectforeground=_theme.TH_SEL_FG, relief="flat",
                        highlightthickness=0)
        lb.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(frm, orient="vertical", command=lb.yview)
        vs.grid(row=0, column=1, sticky="ns")
        lb.configure(yscrollcommand=vs.set)
        lb.bind("<Double-Button-1>", lambda e: self._clip_hist_insert())
        lb.bind("<Return>", lambda e: self._clip_hist_insert())
        win.lb = lb
        btns = ttk.Frame(frm)
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="Copy to clipboard",
                   command=self._clip_hist_copy).pack(side="left")
        ttk.Button(btns, text="Insert into editor",
                   command=self._clip_hist_insert).pack(side="left", padx=(4, 0))
        ttk.Label(btns, text="double-click pastes a row into the editor",
                  font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED).pack(side="left",
                                                                padx=(10, 0))
        ttk.Button(btns, text="Close",
                   command=win.destroy).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._refresh_clip_hist_win(win)

    def _refresh_clip_hist_win(self, win):
        lb = getattr(win, "lb", None)
        if lb is None:
            return
        lb.delete(0, "end")
        for label, text in self._clip_hist:
            one = text.replace("\n", " | ")
            if len(one) > 78:
                one = one[:75] + "..."
            lb.insert("end", "[%s]  %s" % (label, one))

    def _clip_hist_selected(self):
        win = getattr(self, "_clip_hist_win", None)
        lb = getattr(win, "lb", None) if win is not None else None
        if lb is None:
            return None
        try:
            i = int(lb.curselection()[0])
        except (IndexError, tk.TclError, ValueError):
            return None
        if 0 <= i < len(self._clip_hist):
            return self._clip_hist[i][1]
        return None

    def _clip_hist_copy(self):
        v = self._clip_hist_selected()
        if v is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(v)
        self.flash("Clipboard history: copied to clipboard")

    def _clip_hist_insert(self):
        v = self._clip_hist_selected()
        if v is None:
            return
        try:
            self.tr_txt.insert("insert", v.replace("\n", "|"))
        except tk.TclError:
            pass

    def clear_clip_history(self):
        self._clip_hist = []
        win = getattr(self, "_clip_hist_win", None)
        if win is not None:
            try:
                self._refresh_clip_hist_win(win)
            except tk.TclError:
                self._clip_hist_win = None

    def _on_paste_rows(self, _evt=None):
        idxs = self._selected_flat_in_order()
        if not idxs:
            return
            
        try:
            clip_text = self.root.clipboard_get()
        except tk.TclError:
            clip_text = ""
            
        if not clip_text and not getattr(self, "_row_clip", None):
            return
            
        if clip_text:
            # Parse Excel TSV/newline structure
            vals = [v.replace("\\n", "\n") for v in clip_text.strip("\r\n").split("\n")]
        else:
            vals = self._row_clip
            
        changed = False
        cells = []
        for k, i in enumerate(idxs):
            val = vals[k % len(vals)].strip("\r")
            _, e = self.pack.flat[i]
            if e.get("translation", "") == val:
                continue
            # the whole paste is one step: pasting a row onto the wrong row by
            # accident is exactly the mistake Ctrl+Z has to be able to take
            # back, and it should take one press, not one press per row
            cells.append((i, e.get("translation", ""), val))
            e["translation"] = val
            self._own(e)
            changed = True
            self.dirty = True
            iid = self._iid_of(i)
            if iid is not None:
                self.update_tree_row(iid, i)
            self._refresh_ed_line(i)
        if changed:
            self.note_edit("Paste", cells)
            self._find_hits = None    # translations just changed under the finder
            self.update_preview()
            self.update_status()
        return "break"
