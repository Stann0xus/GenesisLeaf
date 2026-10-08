"""CellSelection - spreadsheet-style cell picking on a ttk.Treeview.

Rules (the same on every table that uses it):

  * plain click / Shift+click / arrow keys  -> ordinary ROW selection;
                                               any picked cells are cleared
  * Ctrl+Click on a cell                    -> picks that single cell
  * further Ctrl+Clicks                     -> add / remove cells
  * Ctrl+Shift+Click                        -> add a column range from the anchor
  * Ctrl+Alt+Click                          -> pick the cell and copy it now
  * Ctrl+C with cells picked                -> copies them as a grid: tab
                                               between cells of one row,
                                               newline between rows
  * Esc                                     -> clears the picked cells

Highlights are opaque labels drawn over the cells with the cell's *current*
text, re-placed after every scroll / resize / repaint, so a highlight can
never show stale text from a previous selection.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import tkinter as tk

from genesisleaf.ui import theme as _theme
from genesisleaf.ui.fonts import FONT_MONO

CTRL = 0x0004


def clean(val):
    """One cell as clipboard text: tabs/newlines escaped so the grid stays
    a grid when pasted into a spreadsheet."""
    return str(val).replace("\t", " ").replace("\r", "").replace("\n", "\\n")


class CellSelection:
    """Ctrl+Click cell picking for `tree`.

    `on_pick(iids)` is called after the picked cells change (with the row
    iids in table order) so the owner can load the active row in its
    editor; `on_copy(text, label)` receives the clipboard text after a copy.
    """

    def __init__(self, tree, on_pick=None, on_copy=None):
        self.tree = tree
        self.on_pick = on_pick
        self.on_copy = on_copy
        self.cells = []            # [(iid, column), ...] in pick order
        self._cell_set = set()
        self._by_row = {}
        self._order = None
        self._anchor = None
        self._last = None
        self._labels = []
        self._label_states = []
        self._job = None
        tree.bind("<Control-Button-1>", self._ctrl_click)
        tree.bind("<Control-Shift-Button-1>", self._ctrl_shift_click)
        tree.bind("<Control-Alt-Button-1>", self._ctrl_alt_click)
        for seq in ("<Button-1>", "<Shift-Button-1>", "<Up>", "<Down>",
                    "<Prior>", "<Next>", "<Home>", "<End>"):
            tree.bind(seq, self._plain, add="+")
        tree.bind("<Escape>", lambda e: self.clear(), add="+")
        for seq in ("<Configure>", "<MouseWheel>", "<ButtonRelease-1>",
                    "<B1-Motion>", "<<TreeviewOpen>>"):
            tree.bind(seq, lambda e: self.schedule(), add="+")
        self._wrap_scroll("yscrollcommand")
        self._wrap_scroll("xscrollcommand")
        tree.bind("<Destroy>", self._destroy, add="+")

    # -- plumbing -----------------------------------------------------------
    def _wrap_scroll(self, opt):
        """Chain onto the tree's scroll callback so highlights follow the
        rows when the table scrolls by any means (wheel, bar, keys, see())."""
        if opt == "yscrollcommand" and hasattr(self.tree, "add_scroll_observer"):
            self.tree.add_scroll_observer(self.schedule)
            return
        try:
            prev = self.tree.cget(opt)
        except tk.TclError:
            return

        def relay(*args):
            if prev:
                self.tree.tk.call(prev, *args) if isinstance(prev, str) \
                    else prev(*args)
            self.schedule()
        self.tree.configure(**{opt: relay})

    def column_at(self, x, y):
        """Column name under (x, y), or None outside the cells.

        Resolved from the cells' own bbox geometry rather than
        identify_column, which disagrees with bbox by a few pixels near
        column edges - the highlight must land exactly where the click was."""
        tv = self.tree
        iid = tv.identify_row(y)
        if not iid or tv.identify_region(x, y) != "cell":
            return None
        disp = tv["displaycolumns"]
        cols = list(tv["columns"]) if disp in ("#all", ("#all",)) else list(disp)
        for col in cols:
            try:
                box = tv.bbox(iid, col)
            except tk.TclError:
                continue
            if box and box[0] <= x < box[0] + box[2]:
                return col
        return None

    # -- events -------------------------------------------------------------
    def _pick_at(self, evt, toggle=True):
        col = self.column_at(evt.x, evt.y)
        iid = self.tree.identify_row(evt.y)
        if not col or not iid:
            return False
        cell = (iid, col)
        if cell in self._cell_set and toggle:
            self.cells.remove(cell)
            self._cell_set.remove(cell)
            self._by_row[iid].remove(col)
            if not self._by_row[iid]:
                del self._by_row[iid]
        else:
            self._add(cell)
        self._anchor = cell
        self._last = iid
        self._after_change()
        return True

    def _add(self, cell):
        if cell not in self._cell_set:
            self.cells.append(cell)
            self._cell_set.add(cell)
            self._by_row.setdefault(cell[0], set()).add(cell[1])

    def _ctrl_shift_click(self, evt):
        col = self.column_at(evt.x, evt.y)
        iid = self.tree.identify_row(evt.y)
        if col and iid:
            anchor = self._anchor
            rows = self.tree.get_children("")
            order = {row: n for n, row in enumerate(rows)}
            if anchor is None or anchor[0] not in order or iid not in order:
                self._pick_at(evt, toggle=False)
            else:
                lo, hi = sorted((order[anchor[0]], order[iid]))
                for row in rows[lo:hi + 1]:
                    self._add((row, col))
                self._order = order
                self._last = iid
                self._after_change()
        self.tree.focus_set()
        return "break"

    def _ctrl_click(self, evt):
        self._pick_at(evt)
        self.tree.focus_set()
        return "break"            # no Treeview ctrl-toggle of rows

    def _ctrl_alt_click(self, evt):
        if self._pick_at(evt, toggle=False):
            self.copy()
        self.tree.focus_set()
        return "break"

    def _plain(self, evt):
        # Control is handled by _ctrl_click; anything else is row mode
        if int(getattr(evt, "state", 0)) & CTRL:
            return None
        if self.cells:
            self.clear()
        return None

    def _after_change(self):
        rows = self.rows()
        if self.on_pick is not None and rows:
            self.on_pick(rows)
        self.schedule()

    # -- queries ------------------------------------------------------------
    def active(self):
        return bool(self.cells)

    def last_row(self):
        """Row of the most recently picked cell (the 'active' cell)."""
        if self._last in self._by_row and self.tree.exists(self._last):
            return self._last
        for iid, _c in reversed(self.cells):
            if self.tree.exists(iid):
                return iid
        return None

    def rows(self):
        """Row iids of the picked cells, in table order, de-duplicated."""
        tv = self.tree
        if self._order is None or any(i not in self._order for i in self._by_row):
            self._order = {iid: n for n, iid in enumerate(tv.get_children(""))}
        return sorted((i for i in self._by_row if i in self._order),
                      key=self._order.__getitem__)

    def text(self):
        """The picked cells as a tab/newline grid."""
        tv = self.tree
        order = list(tv["columns"])
        by_row = {}
        for iid, col in self.cells:
            if tv.exists(iid):
                by_row.setdefault(iid, []).append(col)
        lines = []
        for iid in self.rows():
            cols = sorted(set(by_row[iid]), key=order.index)
            lines.append("\t".join(clean(tv.set(iid, c)) for c in cols))
        return "\n".join(lines)

    # -- actions ------------------------------------------------------------
    def copy(self):
        """Copy the picked cells; returns the text ('' when none)."""
        if not self.cells:
            return ""
        text = self.text()
        tv = self.tree
        tv.clipboard_clear()
        tv.clipboard_append(text)
        if self.on_copy is not None:
            cols = sorted({c for _i, c in self.cells},
                          key=list(tv["columns"]).index)
            self.on_copy(text, "cells [%s] x%d" % (",".join(cols),
                                                    len(self.cells)))
        return text

    def clear(self):
        self.cells = []
        self._cell_set.clear()
        self._by_row.clear()
        self._order = None
        self._anchor = self._last = None
        self._cancel_draw()
        for lab in self._labels:
            lab.place_forget()
        self._label_states = [None] * len(self._labels)

    def _cancel_draw(self):
        if self._job is not None:
            self.tree.after_cancel(self._job)
            self._job = None

    def _destroy(self, evt):
        if evt.widget is self.tree:
            self._cancel_draw()

    def forget_missing(self):
        """Drop cells whose rows left the table (rebuild / filter)."""
        tv = self.tree
        self.cells = [(i, c) for i, c in self.cells if tv.exists(i)]
        self._cell_set = set(self.cells)
        self._by_row = {}
        for i, c in self.cells:
            self._by_row.setdefault(i, set()).add(c)
        self._order = None
        self.schedule()

    # -- drawing ------------------------------------------------------------
    def schedule(self):
        """Coalesce scroll/selection bursts into one pending frame."""
        if self._job is None and (self.cells or self._labels):
            self._job = self.tree.after(16, self.redraw)

    def redraw(self):
        self._cancel_draw()
        tv = self.tree
        live = []
        # Highlights outside the viewport cannot be drawn. Walk visible rows
        # for every selection size so repaint work stays bounded as cells are
        # added, including during a long sequence of Ctrl+clicks.
        visible = []
        seen = set()
        y = 0
        while y < tv.winfo_height():
            iid = tv.identify_row(y)
            box = tv.bbox(iid) if iid else None
            if box:
                if iid not in seen:
                    visible.append(iid)
                    seen.add(iid)
                y = max(y + 1, box[1] + box[3])
            else:
                y += 1
        cells = ((i, c) for i in visible for c in self._by_row.get(i, ()))
        for iid, col in cells:
            if not tv.exists(iid):
                continue
            try:
                box = tv.bbox(iid, col)
            except tk.TclError:
                box = None
            if box:
                live.append((box, tv.set(iid, col)))
        while len(self._labels) < len(live):
            lab = tk.Label(tv, anchor="w", padx=3, font=FONT_MONO,
                           borderwidth=0, highlightthickness=2)
            # clicks on a highlight act like clicks on the cell under it
            lab.bind("<Control-Button-1>", self._relay_ctrl)
            lab.bind("<Control-Shift-Button-1>", self._relay_range)
            lab.bind("<Control-Alt-Button-1>", self._relay_copy)
            lab.bind("<Button-1>", self._relay_plain)
            self._labels.append(lab)
            self._label_states.append(None)
        for n in range(len(live), len(self._labels)):
            if self._label_states[n] is not None:
                self._labels[n].place_forget()
                self._label_states[n] = None
        for n, (lab, ((x, y, w, h), val)) in enumerate(zip(self._labels, live)):
            state = (x, y, w, h, str(val), _theme.TH_SEL_BG,
                     _theme.TH_SEL_FG, _theme.TH_ACCENT)
            if state == self._label_states[n]:
                continue
            self._label_states[n] = state
            lab.configure(text=str(val).replace("\n", " "),
                          bg=_theme.TH_SEL_BG, fg=_theme.TH_SEL_FG,
                          highlightbackground=_theme.TH_ACCENT,
                          highlightcolor=_theme.TH_ACCENT)
            lab.place(x=x, y=y, width=w, height=h)
            lab.lift()

    def _relay(self, evt):
        tv = self.tree
        x = evt.x_root - tv.winfo_rootx()
        y = evt.y_root - tv.winfo_rooty()
        return x, y

    def _relay_ctrl(self, evt):
        x, y = self._relay(evt)
        fake = type("E", (), {"x": x, "y": y, "state": CTRL})()
        return self._ctrl_click(fake)

    def _relay_range(self, evt):
        x, y = self._relay(evt)
        return self._ctrl_shift_click(type("E", (), {"x": x, "y": y})())

    def _relay_copy(self, evt):
        x, y = self._relay(evt)
        return self._ctrl_alt_click(type("E", (), {"x": x, "y": y})())

    def _relay_plain(self, evt):
        x, y = self._relay(evt)
        self.clear()
        iid = self.tree.identify_row(y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        return "break"
