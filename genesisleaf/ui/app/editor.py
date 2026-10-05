"""Translation editor: single/multi-row mapping, write-back, retagging, keys and edits.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.core.encoding import parse_text
from genesisleaf.core.space import verdict as space_verdict
from genesisleaf.ui.fonts import FONT_UI, FONT_UI_SM


class EditorMixin:
    """Translation editor: single/multi-row mapping, write-back, retagging, keys and edits.

    Mixed into `App`; `self` is the main window.
    """

    # -- translation editor ------------------------------------------------
    # A single box owns the translation area.  When the "Multi-line rows"
    # checkbox is on the box shows the current dialog box, one line per row;
    # unchecked it follows the table selection instead (capped by the Options
    # limit).  Either way there is exactly one widget, `_ed_flat` maps widget
    # line -> flat row, and a lone row keeps the classic whole-widget editor.
    def _sync_tr_editors(self, idx=None):
        if not hasattr(self, "tr_single"):
            return
        if idx is None:
            idx = self.current
        if hasattr(self, "tr_multi"):
            self.tr_multi.grid_remove()
            for w in list(self.tr_multi.winfo_children()):
                w.destroy()
        self.tr_single.grid()
        self.tr_txt = self._tr_single_ed
        rows = self._ed_rows_for(idx)
        self._load_ed_rows(self.tr_txt, rows, idx)

    def _ed_rows_for(self, idx, sel_rows=None):
        """Which flat rows the editor should show, in line order.

        `sel_rows` lets a view window pass its own table selection; the main
        window defaults to its own."""
        if sel_rows is None:
            sel_rows = self._selected_flat_in_order()
        if self.multi_var.get():
            if 0 <= idx < len(self.pack.flat):
                rows = [i for i in self.box_rows(idx)
                        if 0 <= i < len(self.pack.flat)]
                return rows or [idx]
        rows = [i for i in sel_rows if 0 <= i < len(self.pack.flat)]
        if idx not in rows:
            rows = [idx]
        cap = int(getattr(self, "max_ed_lines", 10) or 10)
        if len(rows) > cap:
            rows = rows[:cap]
        return rows or [idx]

    def _on_multi_toggle(self):
        if self.current >= 0:
            self.select_entry(self.current)
        self.update_preview()
        self.update_status()
        if hasattr(self, "_cmp_pv_canvases"):
            self._cmp_show_detail()

    def _ed_display_val(self, val, n):
        """Text a mapped editor line should show for value `val`.  Across
        several rows a real newline would shift the line-to-row mapping, so
        it is shown (and later stored) as the game's '|' break; the single
        classic editor keeps raw newlines."""
        return val.replace("\n", "|") if n > 1 else val

    def _load_ed_rows(self, w, rows, active_idx):
        """Repoint the translation widget `w` at `rows` (one line per row)
        without reporting an edit.  `active_idx` names the focused row."""
        n = len(rows)
        vals = []
        for j in rows:
            if 0 <= j < len(self.pack.flat):
                tr = self.pack.flat[j][1].get("translation", "")
            else:
                tr = ""
            vals.append(self._ed_display_val(tr, n))
        w._flat_idx = None
        w._ed_flat = rows
        w._ed_prev = list(vals)
        w.configure(state="normal")
        w.delete("1.0", "end")
        if n:
            w.insert("1.0", "\n".join(vals))
        w.edit_modified(False)
        w.edit_reset()
        self.retag(w, allow_over=True)
        self.update_ed_summary(w)

    def update_ed_summary(self, w=None):
        """The one-line strip above the box: per-row key + status.  Blank in
        the classic single-row editor.  Only the window that owns the widget
        updates it, so a view drawing into the shared box cannot repaint the
        main window's summary."""
        lab = getattr(self, "l_ed_summary", None)
        if lab is None:
            return
        w = w or self.tr_txt
        if w is not self.tr_txt:
            return
        flat = getattr(w, "_ed_flat", [])
        if len(flat) <= 1:
            lab.configure(text="")
            return
        parts = []
        for j in flat:
            if not (0 <= j < len(self.pack.flat)):
                continue
            sec_j, e = self.pack.flat[j]
            b, spans = parse_text(e.get("translation", ""))
            v = space_verdict(sec_j, e, b)
            if any(st == "nonascii" for _, _, st in spans):
                st_ = "NX"
            elif v == "over":
                st_ = "OVER"
            elif v == "grows":
                st_ = "GROWS"
            elif not e.get("translation", "").strip():
                st_ = "-"
            else:
                st_ = "OK"
            budget = int(e.get("budget", parse_text(e.get("source", ""))[0]))
            parts.append("%s %s %dB/%dB" % (e.get("key", ""), st_, b, budget))
        lab.configure(text="   ".join(parts))

    def _refresh_ed_line(self, j):
        """A row changed on the pack side (paste / clear / join / undo);
        repaint its line in the mapped box without reporting an edit."""
        w = self.tr_txt
        flat = getattr(w, "_ed_flat", [])
        if j not in flat or not (0 <= j < len(self.pack.flat)):
            return
        n = len(flat)
        k = flat.index(j)
        prev = w._ed_prev[k] if len(w._ed_prev) == n else None
        val = self._ed_display_val(
            self.pack.flat[j][1].get("translation", ""), n)
        if prev == val:
            return
        w._sealing = True
        try:
            if prev:
                w.delete("%d.0" % (k + 1), "%d.end" % (k + 1))
            if val:
                w.insert("%d.0" % (k + 1), val)
            w.edit_modified(False)
            w.edit_reset()
        finally:
            w._sealing = False
        if len(w._ed_prev) == n:
            w._ed_prev[k] = val
        self.retag(w, allow_over=True)
        self.update_ed_summary(w)

    def _ed_reconcile(self, prev, lines):
        """Fold `lines` (from a paste or Ctrl+Enter that changed the physical
        line count) back onto the rows `prev` described, returning exactly
        len(prev) values.  Unchanged prefix/suffix map 1:1; an inserted
        newline folds the surplus into the affected row (join '|'); a deleted
        newline leaves the merged text in the first affected row and blanks
        the rows it consumed."""
        n = len(prev)
        if len(lines) == n:
            return list(lines)
        if not lines:
            return list(prev)
        a = 0
        hi = min(n, len(lines))
        while a < hi and lines[a] == prev[a]:
            a += 1
        bp, bl = n, len(lines)
        while bp > a and bl > a and lines[bl - 1] == prev[bp - 1]:
            bp -= 1
            bl -= 1
        out = list(prev)
        mp = prev[a:bp]
        ml = lines[a:bl]
        if len(mp) == len(ml):
            for k, v in enumerate(ml):
                out[a + k] = v
        elif len(ml) > len(mp):
            for k, v in enumerate(ml):
                if k < len(mp):
                    out[a + k] = v
                else:
                    out[a + len(mp) - 1] += "|" + v
        else:
            for k, v in enumerate(ml):
                out[a + k] = v
            for k in range(len(ml), len(mp)):
                out[a + k] = ""
        return out

    def _seal_ed(self, w, lines, caret_line):
        """Rewrite the box to exactly one line per mapped row (reconciling a
        paste/newline that shifted the count), keeping the caret on the same
        row."""
        w._sealing = True
        try:
            w.configure(state="normal")
            w.delete("1.0", "end")
            w.insert("1.0", "\n".join(lines))
            w.edit_modified(False)
            w.edit_reset()
            w.mark_set("insert", "%d.0" % min(max(1, caret_line), len(lines)))
        finally:
            w._sealing = False

    def _tr_write_classic(self, w, idx):
        """Single-row write-back (one mapped row, or a legacy widget with no
        map): the whole widget text belongs to `idx`, real newlines and all."""
        if not (0 <= idx < len(self.pack.flat)):
            return
        val = w.get("1.0", "end-1c")
        _, e = self.pack.flat[idx]
        old = e.get("translation", "")
        if old != val:
            e["translation"] = val
            self.note_edit(self._edit_label or "Typing",
                           [(idx, old, val)], mergeable=True)
            self._find_hits = None
            self._own(e)
            self.dirty = True
            self._schedule_join(idx)
            iid = self._iid_of(idx)
            if iid is not None:
                self.update_tree_row(iid, idx)
            self.invalidate_stats()
        self.retag(w, allow_over=True, idx=idx)

    def _tr_modified_common(self, w):
        """Write a translation editor's content back to the pack.  Shared by
        the main window and the view windows so a box maps the same way
        everywhere.  The mapped box owns one line per row; a line-count shift
        (paste, Ctrl+Enter) is reconciled and the box re-sealed."""
        flat = getattr(w, "_ed_flat", [])
        n = len(flat)
        if n <= 1:
            if n:
                idx = flat[0]
            else:
                idx = getattr(w, "_flat_idx", None)
                if idx is None:
                    idx = self.current
            self._tr_write_classic(w, idx)
            return
        content = w.get("1.0", "end-1c")
        raw = content.split("\n")
        prev = list(w._ed_prev) if len(w._ed_prev) == n else [""] * n
        seal = len(raw) != n
        lines = self._ed_reconcile(prev, raw) if seal \
            else list(raw[:n])
        caret_line = 1
        if seal:
            try:
                caret_line = int(w.index("insert").split(".")[0])
            except tk.TclError:
                pass
        changed = []
        for k in range(n):
            j = flat[k]
            if not (0 <= j < len(self.pack.flat)):
                continue
            tr = lines[k].replace("\r", "").replace("\n", "|")
            if tr == prev[k]:
                continue
            _, e = self.pack.flat[j]
            old = e.get("translation", "")
            if old != tr:
                changed.append((j, old, tr))
                e["translation"] = tr
                self._own(e)
                self.dirty = True
                self._schedule_join(j)
            iid = self._iid_of(j)
            if iid is not None:
                self.update_tree_row(iid, j)
        w._ed_prev = [lines[k].replace("\n", "|") for k in range(n)]
        if changed:
            self.note_edit(self._edit_label or "Typing",
                           changed, mergeable=len(changed) == 1)
            self._find_hits = None
            self.invalidate_stats()
        if seal:
            self._seal_ed(w, w._ed_prev, caret_line)
        self.retag(w, allow_over=True)
        self.update_ed_summary(w)

    def retag(self, w, allow_over=False, idx=None):
        content = w.get("1.0", "end-1c")
        for tag in ("nonascii", "fold", "newline", "byte", "esc2", "sub",
                    "ctl", "over"):
            w.tag_remove(tag, "1.0", "end")
        if content:
            _, spans = parse_text(content)
            for s, e_, st in spans:
                if st == "ascii":
                    continue
                w.tag_add(st, "1.0+%dc" % s, "1.0+%dc" % e_)
        if not allow_over:
            return
        flat = getattr(w, "_ed_flat", [])
        if len(flat) > 1:
            # per line: a box can hold a finite budget to a row, so the "over"
            # tint must not leak across rows
            for k, j in enumerate(flat):
                if not (0 <= j < len(self.pack.flat)):
                    continue
                sec_j, e = self.pack.flat[j]
                lt = w.get("%d.0" % (k + 1), "%d.end" % (k + 1))
                b, _ = parse_text(lt)
                if space_verdict(sec_j, e, b) == "over":
                    w.tag_add("over", "%d.0" % (k + 1), "%d.end" % (k + 1))
            return
        i = idx if idx is not None else self.current
        if content and 0 <= i < len(self.pack.flat):
            sec_i, e = self.pack.flat[i]
            b, _ = parse_text(content)
            if space_verdict(sec_i, e, b) == "over":
                w.tag_add("over", "1.0", "end")

    def on_tr_modified(self, _evt=None):
        """Any text change in a translation editor.  `_evt.widget` lets a
        single handler serve the main box and the view windows' boxes; only
        the widget whose text actually changed is written to the pack."""
        w = getattr(_evt, "widget", None) or self.tr_txt
        if not w.edit_modified():
            return
        w.edit_modified(False)
        if self._loading or getattr(w, "_sealing", False):
            return
        if self.current < 0:
            return
        self._tr_modified_common(w)
        self._bytes_label()
        self.invalidate_stats()
        self.update_preview()

    def _bind_editor_keys(self, w):
        """Every binding a translation editor needs, in one place.

        The main box belongs to one window, but after a theme switch the
        same key set is pushed onto every view window's box, so the bindings
        live here and the handlers read `event.widget`, never `self.tr_txt`."""
        w.bind("<<Modified>>", self.on_tr_modified)
        w.bind("<KeyRelease>", self.on_tr_key)
        w.bind("<Return>", self.on_tr_return)
        w.bind("<Control-Return>", self.on_tr_ctrl_return)
        # Shift+F1..F10 wrap the selection in colour codes {cf:00}..{cf:09}.
        # Deliberately not the number row: Shift+1..9 are !@#$%^&*() on a US
        # layout, and binding by keycode made those symbols untypeable.
        for n in range(10):
            w.bind("<Shift-F%d>" % (n + 1),
                   lambda ev, n=n: self._shift_fkey(n, ev.widget))

    def color_wrap(self, n, w=None):
        """Wrap the editor selection in `{cf:0n}...{cf:07}`.

        `{cf:07}` is the game's reset back to the default text colour, so a
        coloured run never bleeds into the rest of the line.  With nothing
        selected the bare `{cf:0n}` is inserted at the caret, which is how you
        start a coloured run before typing it."""
        w = w if w is not None else self.tr_txt
        opener = "{cf:%02x}" % n
        reset = "{cf:07}"
        try:
            sel = w.tag_ranges("sel")
        except tk.TclError:
            sel = ()
        if len(sel) >= 2 and str(sel[0]) != str(sel[1]):
            start, end = sel[0], sel[1]
            # reset first: inserting at `end` leaves `start` valid, whereas
            # inserting at `start` first would push `end` along
            w.insert(end, reset)
            w.insert(start, opener)
            # keep the run selected so the next Shift+digit can recolour it
            end = "%s+%dc" % (end, len(reset) + len(opener))
            w.tag_remove("sel", "1.0", "end")
            w.tag_add("sel", start, end)
        else:
            w.insert("insert", opener)
        try:
            w.edit_modified(True)
        except tk.TclError:
            pass
        self.on_tr_modified()
        return "break"

    def _shift_fkey(self, n, w):
        self.color_wrap(n, w)
        return "break"

    def on_tr_key(self, _evt=None):
        pass

    def on_tr_return(self, _evt=None):
        self.tr_txt.insert("insert", "|")
        return "break"

    def on_tr_ctrl_return(self, _evt=None):
        """Ctrl+Enter.  In a mapped box (several rows) a real newline would
        break the one-line-per-row mapping, so it inserts the game break; the
        classic single-row editor keeps the raw newline."""
        w = getattr(_evt, "widget", None) or self.tr_txt
        if len(getattr(w, "_ed_flat", [])) > 1:
            w.insert("insert", "|")
        else:
            w.insert("insert", "\n")
        return "break"

    def insert_token(self, tok):
        self.tr_txt.insert("insert", tok)

    def open_ed_limit_dialog(self):
        """Small spinbox to cap the selection-driven editor's rows."""
        win = tk.Toplevel(self.root)
        win.title("Editor row limit")
        win.transient(self.root)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=10)
        frm.grid(row=0, column=0)
        ttk.Label(
            frm,
            text="Max rows the editor may show when the checkbox is off "
                 "(selection-driven):",
            font=FONT_UI_SM).grid(row=0, column=0, columnspan=3, sticky="w",
                                  pady=(0, 8))
        ttk.Label(frm, text="Rows:", font=FONT_UI).grid(row=1, column=0,
                                                        sticky="w")
        var = tk.IntVar(value=int(getattr(self, "max_ed_lines", 10) or 10))
        sb = ttk.Spinbox(frm, from_=1, to=200, textvariable=var, width=6)
        sb.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Button(frm, text="OK", command=lambda: self._set_ed_limit(
            win, var)).grid(row=1, column=2, sticky="e")
        win.bind("<Return>", lambda e: self._set_ed_limit(win, var))
        win.bind("<Escape>", lambda e: win.destroy())
        try:
            win.grab_set()
        except tk.TclError:
            pass

    def _set_ed_limit(self, win, var):
        try:
            n = int(var.get())
        except (tk.TclError, ValueError):
            win.destroy()
            return
        self.max_ed_lines = max(1, min(200, n))
        win.destroy()
        if self.current >= 0:
            self.select_entry(self.current)
        self.persist_settings()

    def set_translation(self, s, label=None):
        """Write `s` into the current row's editor.  `label` names the step in
        the undo history; without one it reads as typing, since the widget
        cannot tell a keystroke from a button press.  A mapped box writes just
        the current row's line; the classic editor takes the whole widget."""
        prev = self._edit_label
        self._edit_label = label
        try:
            w = self.tr_txt
            flat = getattr(w, "_ed_flat", [])
            if len(flat) > 1 and self.current in flat:
                self.set_row_translation(self.current, s)
                return
            w.delete("1.0", "end")
            w.insert("1.0", s)
            w.edit_modified(True)
            self.on_tr_modified()
        finally:
            self._edit_label = prev

    def set_row_translation(self, idx, s):
        """Write `s` straight to row `idx` (bypassing the widget event loop)
        and repaint its line in the mapped box."""
        if not (0 <= idx < len(self.pack.flat)):
            return
        _, e = self.pack.flat[idx]
        old = e.get("translation", "")
        if len(getattr(self.tr_txt, "_ed_flat", [])) > 1:
            s = s.replace("\n", "|")
        if old != s:
            e["translation"] = s
            self.note_edit(self._edit_label or "Typing", [(idx, old, s)])
            self._own(e)
            self.dirty = True
            self._schedule_join(idx)
            iid = self._iid_of(idx)
            if iid is not None:
                self.update_tree_row(iid, idx)
            self.invalidate_stats()
        self._refresh_ed_line(idx)
        self._bytes_label()
        self.update_preview()
        self.update_status()

    def clear_translation(self):
        self.set_translation("", "Clear line")

    def copy_source_to_tr(self):
        if self.current < 0:
            return
        s = self.pack.flat[self.current][1].get("source", "")
        self.set_translation(s, "Copy source")

    def copy_key(self):
        self._update_sel_count()
        if self.current >= 0:
            v = self.pack.flat[self.current][1].get("key", "")
            self.root.clipboard_clear()
            self.root.clipboard_append(v)
            self._push_clip_history(v, "key")

    def copy_context(self):
        if self.current >= 0:
            v = self.pack.flat[self.current][1].get("context", "")
            self.root.clipboard_clear()
            self.root.clipboard_append(v)
            self._push_clip_history(v, "context")
