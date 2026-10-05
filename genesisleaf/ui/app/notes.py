"""Entry notes: the pack's per-entry `notes` field (Notes dashboard, row
tooltips) and the older per-key notes sidecar.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import json
import tkinter as tk
from tkinter import messagebox, ttk

from genesisleaf.core.constants import CMP_MI
from genesisleaf.ui.fonts import FONT_MONO, FONT_UI_SM, FONT_UI_SM_B
from genesisleaf.ui import theme as _theme

NOTE_MARK = "✎"


class NotesMixin:
    """Entry notes: the pack's per-entry `notes` field (Notes dashboard, row
    tooltips) and the older per-key notes sidecar.

    Mixed into `App`; `self` is the main window.
    """

    # -- notes dashboard ------------------------------------------------------
    # Every entry whose `notes:` field is set, in pack order, with a filter
    # and an editor for the selected note.  A row of the main table or the
    # comparator that has notes shows a pencil mark and its notes as a
    # tooltip; Alt+double-click brings it here (an entry without notes opens
    # here too, ready for its first one).  Notes are saved with the pack.
    def _build_notes_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        self._notes_target = None
        self._notes_rows = []                  # flat indices listed

        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Filter:", font=FONT_UI_SM).pack(side="left")
        self.notes_filter = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.notes_filter, width=32)
        ent.pack(side="left", padx=(4, 8))
        self.notes_filter.trace_add(
            "write", lambda *_a: self.refresh_notes_dashboard())
        ttk.Button(top, text="Jump to entry",
                   command=self._notes_jump).pack(side="left", padx=2)
        ttk.Button(top, text="Note on current entry",
                   command=lambda: self.open_notes_dashboard(
                       self.current if self.current >= 0 else None)
                   ).pack(side="left", padx=2)
        self.l_notes_count = ttk.Label(top, text="", font=FONT_UI_SM,
                                       foreground=_theme.TH_FG_MUTED)
        self.l_notes_count.pack(side="right")

        panes = ttk.Panedwindow(f, orient="vertical")
        panes.pack(fill="both", expand=True, pady=(6, 0))

        lst = ttk.Frame(panes)
        lst.rowconfigure(0, weight=1)
        lst.columnconfigure(0, weight=1)
        cols = (("ord", "#", 54), ("sec", "Section", 100),
                ("key", "Key", 170), ("source", "Source", 220),
                ("note", "Notes", 320))
        tv = ttk.Treeview(lst, columns=[c for c, _t, _w in cols],
                          show="headings", selectmode="browse", height=10)
        for c, t, w in cols:
            tv.heading(c, text=t, anchor="w")
            tv.column(c, width=w, anchor="e" if c == "ord" else "w",
                      stretch=c in ("source", "note"))
        vs = ttk.Scrollbar(lst, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        tv.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        tv.bind("<<TreeviewSelect>>", lambda e: self._notes_on_select())
        tv.bind("<Double-Button-1>", lambda e: self._notes_jump())
        self.notes_tree = tv
        panes.add(lst, weight=3)

        ed = ttk.Frame(panes)
        self.l_notes_head = ttk.Label(ed, text="", font=FONT_UI_SM_B,
                                      anchor="w")
        self.l_notes_head.pack(fill="x")
        self.l_notes_src = ttk.Label(ed, text="", font=FONT_UI_SM,
                                     foreground=_theme.TH_FG_MUTED,
                                     anchor="w")
        self.l_notes_src.pack(fill="x")
        self.notes_txt = tk.Text(ed, height=6, wrap="word", font=FONT_MONO,
                                 undo=True, padx=6, pady=4,
                                 highlightthickness=1)
        self.notes_txt.pack(fill="both", expand=True, pady=(4, 0))
        self.notes_txt.bind("<Control-Return>",
                            lambda e: self._notes_apply() or "break")
        self._notes_paint()
        btns = ttk.Frame(ed)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Apply  (Ctrl+Enter)",
                   command=self._notes_apply).pack(side="left", padx=2)
        ttk.Button(btns, text="Revert",
                   command=self._notes_load_target).pack(side="left", padx=2)
        ttk.Button(btns, text="Delete note",
                   command=self._notes_delete).pack(side="left", padx=2)
        ttk.Label(btns, text="Notes are part of the pack: Ctrl+S saves them.",
                  font=FONT_UI_SM, foreground=_theme.TH_FG_FAINT).pack(
            side="left", padx=8)
        panes.add(ed, weight=2)
        return f

    def _notes_paint(self):
        t = getattr(self, "notes_txt", None)
        if t is None:
            return
        t.configure(bg=_theme.TH_FIELD_BG, fg=_theme.TH_FG,
                    insertbackground=_theme.TH_FG,
                    highlightbackground=_theme.TH_BORDER,
                    selectbackground=_theme.TH_SEL_BG,
                    selectforeground=_theme.TH_SEL_FG)

    def open_notes_dashboard(self, flat_index=None):
        """Show the dashboard; with `flat_index`, on that entry (an entry
        without notes is put in the editor, ready for its first note)."""
        self.open_tool("notes")
        self.refresh_notes_dashboard()
        if flat_index is None or not (0 <= flat_index < len(self.pack.flat)):
            return
        iid = "n%d" % flat_index
        if not self.notes_tree.exists(iid) and self.notes_filter.get():
            self.notes_filter.set("")           # the filter hid it
        if self.notes_tree.exists(iid):
            self.notes_tree.selection_set(iid)
            self.notes_tree.focus(iid)
            self.notes_tree.see(iid)
        else:
            self._notes_commit_pending()
            self.notes_tree.selection_set(())
            self._notes_target = flat_index
            self._notes_load_target()
        self.notes_txt.focus_set()

    def refresh_notes_dashboard(self):
        tv = getattr(self, "notes_tree", None)
        if tv is None:
            return
        q = self.notes_filter.get().strip().lower()
        keep = tv.selection()
        tv.delete(*tv.get_children())
        rows = []
        total = 0
        for i, (sec, e) in enumerate(self.pack.flat):
            note = e.get("notes")
            if not note:
                continue
            total += 1
            note = str(note)
            if q and q not in note.lower() and q not in e.get(
                    "key", "").lower() and q not in e.get(
                    "source", "").lower() and q not in sec.lower():
                continue
            rows.append(i)
            tv.insert("", "end", iid="n%d" % i, values=(
                i + 1, sec, e.get("key", ""), e.get("source", ""),
                note.replace("\n", "  ↵ ")))
        self._notes_rows = rows
        self.l_notes_count.configure(
            text="%d entr%s with notes%s" % (
                total, "y" if total == 1 else "ies",
                "" if not q else ", %d shown" % len(rows)))
        keep = [k for k in keep if tv.exists(k)]
        if keep:
            tv.selection_set(keep)
        elif self._notes_target is not None and \
                self._notes_target >= len(self.pack.flat):
            self._notes_target = None
            self._notes_load_target()

    def _notes_on_select(self):
        sel = self.notes_tree.selection()
        if not sel:
            return
        i = int(sel[0][1:])
        if i == self._notes_target:
            return
        self._notes_commit_pending()
        self._notes_target = i
        self._notes_load_target()

    def _notes_commit_pending(self):
        """Keep an edit that was never Applied when the editor moves on to
        another entry."""
        i = self._notes_target
        if i is None or i >= len(self.pack.flat) or \
                not self.notes_txt.edit_modified():
            return
        if self._notes_store(i, self.notes_txt.get("1.0", "end-1c")):
            iid = "n%d" % i
            if self.notes_tree.exists(iid):
                self.notes_tree.set(iid, "note", self.entry_note(i)
                                    .replace("\n", "  ↵ "))

    def _notes_load_target(self):
        t = self.notes_txt
        t.delete("1.0", "end")
        i = self._notes_target
        if i is None or i >= len(self.pack.flat):
            self.l_notes_head.configure(text="Select an entry")
            self.l_notes_src.configure(text="")
            return
        sec, e = self.pack.flat[i]
        note = e.get("notes") or ""
        self.l_notes_head.configure(text="#%d   %s   %s%s" % (
            i + 1, sec, e.get("key", ""),
            "" if note else "   (no notes yet - type and Apply)"))
        src = e.get("source", "")
        self.l_notes_src.configure(text="source: %s" % (
            src if len(src) < 160 else src[:157] + "..."))
        t.insert("1.0", str(note))
        t.edit_reset()
        t.edit_modified(False)

    def _notes_apply(self):
        i = self._notes_target
        if i is None or i >= len(self.pack.flat):
            return
        if self._notes_store(i, self.notes_txt.get("1.0", "end-1c")):
            self._notes_changed(i)

    def _notes_store(self, i, text):
        """Write `text` as entry `i`'s notes ('' removes them) and repaint
        the rows that show the mark.  Returns whether anything changed."""
        _sec, e = self.pack.flat[i]
        text = text.rstrip()
        if text == str(e.get("notes") or ""):
            return False
        if text:
            e["notes"] = text
        else:
            e.pop("notes", None)
        self.dirty = True
        iid = self._iid_of(i)
        if iid is not None:
            self.update_tree_row(iid, i)
        if getattr(self, "other", None) is not None:
            for pos, row in enumerate(self.cmp_view):
                if row[CMP_MI] == i:
                    self._cmp_update_cell(pos)
        self.update_status()
        return True

    def _notes_delete(self):
        i = self._notes_target
        if i is None or i >= len(self.pack.flat):
            return
        _sec, e = self.pack.flat[i]
        if not e.get("notes"):
            return
        if not messagebox.askyesno("Notes", "Delete the notes of entry #%d?"
                                   % (i + 1), parent=self.notes_win):
            return
        self._notes_store(i, "")
        self._notes_changed(i)

    def _notes_changed(self, i):
        """After a stored change: relist, keeping entry `i` in the editor."""
        self.refresh_notes_dashboard()
        iid = "n%d" % i
        if self.notes_tree.exists(iid):
            self.notes_tree.selection_set(iid)
            self.notes_tree.see(iid)
        self._notes_load_target()

    def _notes_jump(self):
        i = self._notes_target
        if i is not None and i < len(self.pack.flat):
            self.jump_to_flat(i)
            self.root.lift()

    # -- notes on table rows -------------------------------------------------
    def entry_note(self, i):
        """The `notes` of flat entry `i` ('' when none)."""
        if i is None or not (0 <= i < len(self.pack.flat)):
            return ""
        return str(self.pack.flat[i][1].get("notes") or "")

    def _table_row_tip(self, iid):
        return self._table_row_tip_for(self.view_iid.get(iid))

    def _table_row_tip_for(self, i):
        note = self.entry_note(i)
        if not note:
            return None
        return ("Notes:\n%s\n\n(Alt+double-click: open in the Notes "
                "dashboard)" % note)

    def _table_alt_dbl(self, evt):
        iid = self.tree.identify_row(evt.y)
        i = self.view_iid.get(iid) if iid else None
        if i is not None:
            self.open_notes_dashboard(i)
        return "break"

    # -- notes sidecar (per key, legacy) ---------------------------------------
    def on_note_change(self, _evt=None):
        if self.current < 0:
            return
        k = self.pack.flat[self.current][1].get("key", "")
        v = self.note_ent.get()
        self.notes[k] = v
        if self._notes_job:
            try:
                self.root.after_cancel(self._notes_job)
            except Exception:
                pass
        self._notes_job = self.root.after(400, self._flush_notes)

    def _flush_notes(self):
        np_ = self._sidecar(".notes.json", "legaia_notes.json")
        if not np_:
            return
        try:
            with open(np_, "w", encoding="utf-8") as fh:
                json.dump(self.notes, fh, ensure_ascii=False, indent=1)
            self.notes_path = np_
        except Exception:
            pass
