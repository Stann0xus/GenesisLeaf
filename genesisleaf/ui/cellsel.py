"""CellSelection - spreadsheet-style cell picking on a ttk.Treeview.

Rules (the same on every table that uses it):

  * plain click / Shift+click / arrow keys  -> ordinary ROW selection;
                                               any picked cells are cleared
  * Ctrl+Click on a cell                    -> picks that single cell
  * further Ctrl+Clicks                     -> add / remove cells
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
        self._labels = []
        self._job = None
        tree.bind("<Control-Button-1>", self._ctrl_click)
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

    # -- plumbing -----------------------------------------------------------
    def _wrap_scroll(self, opt):
        """Chain onto the tree's scroll callback so highlights follow the
        rows when the table scrolls by any means (wheel, bar, keys, see())."""
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
        if cell in self.cells and toggle:
            self.cells.remove(cell)
        elif cell not in self.cells:
            self.cells.append(cell)
        self._after_change()
        return True

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
        self.redraw()

    # -- queries ------------------------------------------------------------
    def active(self):
        return bool(self.cells)

    def last_row(self):
        """Row of the most recently picked cell (the 'active' cell)."""
        for iid, _c in reversed(self.cells):
            if self.tree.exists(iid):
                return iid
        return None

    def rows(self):
        """Row iids of the picked cells, in table order, de-duplicated."""
        tv = self.tree
        seen = []
        for iid, _c in self.cells:
            if iid not in seen and tv.exists(iid):
                seen.append(iid)
        return sorted(seen, key=tv.index)

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
        self.redraw()

    def forget_missing(self):
        """Drop cells whose rows left the table (rebuild / filter)."""
        tv = self.tree
        self.cells = [(i, c) for i, c in self.cells if tv.exists(i)]
        self.schedule()

    # -- drawing ------------------------------------------------------------
    def schedule(self):
        """Redraw on the next idle (coalesces bursts of scroll events)."""
        if self._job is None and (self.cells or self._labels):
            self._job = self.tree.after_idle(self.redraw)

    def redraw(self):
        self._job = None
        tv = self.tree
        live = []
        for iid, col in self.cells:
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
            lab.bind("<Button-1>", self._relay_plain)
            self._labels.append(lab)
        for lab in self._labels[len(live):]:
            lab.place_forget()
        for lab, ((x, y, w, h), val) in zip(self._labels, live):
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

    def _relay_plain(self, evt):
        x, y = self._relay(evt)
        self.clear()
        iid = self.tree.identify_row(y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        return "break"
