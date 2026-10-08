"""A Treeview that creates native Tk items only for its visible window."""

from tkinter import ttk

from genesisleaf.diagnostics import current as current_diagnostics


class VirtualTreeview(ttk.Treeview):
    WINDOW = 256
    MARGIN = 64

    def __init__(self, master=None, **kw):
        self._all_rows = []
        self._rows = {}
        self._row_positions = {}
        self._window_start = 0
        self._window_rows = []
        self._top = 0
        self._changing_window = False
        self._external_scroll = None
        self._scroll_observers = []
        self._selected = ()
        self._focused = ""
        self._next_iid = 0
        super().__init__(master, **kw)
        self.bind("<MouseWheel>", self._wheel, add="+")

    def configure(self, cnf=None, **kw):
        if "yscrollcommand" in kw:
            self._external_scroll = kw.pop("yscrollcommand")
            kw["yscrollcommand"] = self._native_scrolled
        return super().configure(cnf, **kw)

    config = configure

    def add_scroll_observer(self, callback):
        self._scroll_observers.append(callback)

    def insert(self, parent, index, iid=None, **kw):
        if parent:
            return super().insert(parent, index, iid=iid, **kw)
        if iid is None:
            self._next_iid += 1
            iid = "v%d" % self._next_iid
        if iid in self._rows:
            raise ValueError("Duplicate Treeview item %r" % iid)
        pos = len(self._all_rows)
        self._all_rows.append(iid)
        self._row_positions[iid] = pos
        self._rows[iid] = dict(kw)
        if pos < self.WINDOW:
            super().insert("", "end", iid=iid, **kw)
            self._window_rows.append(iid)
        return iid

    def delete(self, *items):
        if not items:
            return
        if len(items) == len(self._all_rows):
            if self._window_rows:
                super().delete(*self._window_rows)
            self._all_rows.clear()
            self._rows.clear()
            self._row_positions.clear()
            self._window_rows.clear()
            self._window_start = 0
            self._top = 0
            self._selected = ()
            self._focused = ""
            self.refresh_scrollbar()
            return
        gone = set(items)
        visible = [iid for iid in items if iid in self._window_rows]
        if visible:
            super().delete(*visible)
        for iid in gone:
            self._rows.pop(iid, None)
        self._all_rows = [iid for iid in self._all_rows if iid not in gone]
        self._row_positions = {iid: i for i, iid in enumerate(self._all_rows)}
        self._window_rows = [iid for iid in self._window_rows if iid not in gone]
        self._selected = tuple(iid for iid in self._selected if iid not in gone)
        if self._focused in gone:
            self._focused = ""
        self._set_top(self._top)

    def get_children(self, item=None):
        if item is None or item == "":
            return tuple(self._all_rows)
        return super().get_children(item)

    def index(self, item):
        pos = self._row_positions.get(item)
        return pos if pos is not None else super().index(item)

    def exists(self, item):
        return item in self._rows or super().exists(item)

    def item(self, item, option=None, **kw):
        row = self._rows.get(item)
        if row is None:
            return super().item(item, option, **kw)
        if kw:
            row.update(kw)
            if item in self._window_rows:
                super().item(item, **kw)
        if option is not None:
            return row.get(option, () if option in ("values", "tags") else "")
        return dict(row)

    def set(self, item, column=None, value=None):
        row = self._rows.get(item)
        if row is None:
            return super().set(item, column, value)
        columns = tuple(self["columns"])
        values = list(row.get("values", ()))
        if column is None:
            return dict(zip(columns, values))
        col = columns.index(column) if column in columns else int(column.lstrip("#")) - 1
        if value is None:
            return values[col] if col < len(values) else ""
        values.extend([""] * max(0, col + 1 - len(values)))
        values[col] = value
        self.item(item, values=tuple(values))

    @staticmethod
    def _items(args):
        if len(args) == 1 and isinstance(args[0], (tuple, list, set)):
            return tuple(args[0])
        return tuple(args)

    def selection(self):
        native = tuple(super().selection())
        expected = tuple(iid for iid in self._selected if iid in self._window_rows)
        if set(native) != set(expected):
            self._selected = native
        return self._selected

    def _apply_selection(self, changed=False):
        native = tuple(iid for iid in self._selected if iid in self._window_rows)
        if set(super().selection()) != set(native):
            super().selection_set(native)
        elif changed:
            self.event_generate("<<TreeviewSelect>>")

    def selection_set(self, *items):
        wanted = self._items(items)
        changed = set(wanted) != set(self._selected)
        self._selected = wanted
        self._apply_selection(changed)

    def selection_add(self, *items):
        wanted = tuple(dict.fromkeys(self._selected + self._items(items)))
        self.selection_set(wanted)

    def selection_remove(self, *items):
        gone = set(self._items(items))
        self.selection_set(tuple(iid for iid in self._selected if iid not in gone))

    def focus(self, item=None):
        if item is None:
            native = super().focus()
            if native and native != self._focused:
                self._focused = native
            return self._focused
        self._focused = item
        if item in self._window_rows:
            super().focus(item)
        else:
            super().focus("")

    def _visible_rows(self):
        try:
            style = self.cget("style") or "Treeview"
            height = int(ttk.Style(self).lookup(style, "rowheight") or 24)
        except (TypeError, ValueError):
            height = 24
        return max(1, min(96, self.winfo_height() // max(1, height)))

    def _fractions(self):
        total = len(self._all_rows)
        if not total:
            return (0.0, 1.0)
        visible = self._visible_rows()
        return (self._top / total, min(1.0, (self._top + visible) / total))

    def refresh_scrollbar(self):
        if self._external_scroll is not None:
            self._external_scroll(*self._fractions())
        for callback in self._scroll_observers:
            callback()

    def _native_scrolled(self, first, last):
        if self._changing_window:
            return
        if len(self._all_rows) <= self.WINDOW:
            if self._external_scroll is not None:
                self._external_scroll(first, last)
            for callback in self._scroll_observers:
                callback()
            return
        local_top = int(round(float(first) * len(self._window_rows)))
        target = self._window_start + local_top
        if target != self._top:
            self._set_top(target)
        else:
            self.refresh_scrollbar()

    def _set_top(self, top):
        total = len(self._all_rows)
        visible = self._visible_rows()
        top = max(0, min(int(top), max(0, total - visible)))
        old_top = self._top
        if total <= self.WINDOW:
            self._top = top
            if total:
                super().yview_moveto(top / total)
            self.refresh_scrollbar()
            return
        start = self._window_start
        end = start + len(self._window_rows)
        if (not self._window_rows or top < start + self.MARGIN // 2
                or top + visible > end - self.MARGIN // 2):
            start = max(0, min(top - self.MARGIN,
                               max(0, total - self.WINDOW)))
        wanted = self._all_rows[start:start + self.WINDOW]
        self._changing_window = True
        try:
            if wanted != self._window_rows:
                old = set(self._window_rows)
                new = set(wanted)
                leaving = [iid for iid in self._window_rows if iid not in new]
                if leaving:
                    super().delete(*leaving)
                for pos, iid in enumerate(wanted):
                    if iid not in old:
                        super().insert("", pos, iid=iid, **self._rows[iid])
                self._window_rows = list(wanted)
                self._window_start = start
                self._apply_selection()
                if self._focused in new:
                    super().focus(self._focused)
                else:
                    super().focus("")
            self._top = top
            super().yview_moveto((top - start) / max(1, len(wanted)))
        finally:
            self._changing_window = False
        self.refresh_scrollbar()
        if top != old_top:
            monitor = current_diagnostics()
            if monitor is not None:
                monitor.event("TREE_VIEWPORT", tree=str(self), first=top,
                              visible=visible, total=total,
                              attached=len(self._window_rows))

    def yview(self, *args):
        if not args:
            return self._fractions()
        if args[0] == "moveto":
            self._set_top(float(args[1]) * len(self._all_rows))
        elif args[0] == "scroll":
            amount = int(args[1])
            if args[2] == "pages":
                amount *= max(1, self._visible_rows() - 1)
            self._set_top(self._top + amount)

    def yview_moveto(self, fraction):
        self.yview("moveto", fraction)

    def yview_scroll(self, number, what):
        self.yview("scroll", number, what)

    def see(self, item):
        pos = self._row_positions.get(item)
        if pos is None:
            return super().see(item)
        visible = self._visible_rows()
        if pos < self._top:
            self._set_top(pos)
        elif pos >= self._top + visible:
            self._set_top(pos - visible + 1)

    def _wheel(self, event):
        if event.state & 0x5:  # Leave Control zoom and Shift horizontal scroll alone.
            return None
        steps = -int(event.delta / 120)
        if steps:
            self.yview_scroll(steps * 3, "units")
        return "break"
