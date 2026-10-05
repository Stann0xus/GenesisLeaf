"""Small reusable widgets.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk


class ToolTip:
    """A simple delayed tooltip for widgets."""
    def __init__(self, widget, text, delay=2000):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._id = None
        self._tw = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, _evt=None):
        self.schedule()

    def leave(self, _evt=None):
        self.unschedule()
        self.hide()

    def schedule(self):
        self.unschedule()
        self._id = self.widget.after(self.delay, self.show)

    def unschedule(self):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None

    def show(self):
        self.unschedule()
        if self._tw:
            return
        x, y, cx, cy = self.widget.bbox("insert") or (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self._tw = tk.Toplevel(self.widget)
        self._tw.wm_overrideredirect(True)
        self._tw.wm_geometry(f"+{x}+{y}")
        from genesisleaf.ui import theme as _theme
        if _theme.MENU_UI:             # a small game window instead of the
            colours = dict(background=_theme.TH_FRAME_BG,   # yellow note
                           foreground=_theme.TH_FG, padx=6, pady=3,
                           highlightthickness=2,
                           highlightbackground=_theme.TH_BORDER,
                           borderwidth=0, relief="flat")
        else:
            colours = dict(background="#ffffe0", relief="solid", borderwidth=1)
        lbl = tk.Label(self._tw, text=self.text, justify="left",
                       font=("Segoe UI", 9), **colours)
        lbl.pack()

    def hide(self):
        if self._tw:
            self._tw.destroy()
            self._tw = None


class TreeRowTip:
    """Hover tooltip for the rows of a ttk.Treeview.

    `text_for(iid)` returns the text to show for a row, or a false value for
    none.  The tip follows the row under the pointer, waits `delay` ms
    before appearing and goes away on leave / click / scroll."""

    def __init__(self, tree, text_for, delay=450, wrap=460):
        self.tree = tree
        self.text_for = text_for
        self.delay = delay
        self.wrap = wrap
        self._iid = None
        self._job = None
        self._tw = None
        self._xy = (0, 0)
        tree.bind("<Motion>", self._motion, add="+")
        for seq in ("<Leave>", "<ButtonPress>", "<MouseWheel>", "<KeyPress>"):
            tree.bind(seq, self._reset, add="+")

    def _motion(self, evt):
        iid = self.tree.identify_row(evt.y)
        self._xy = (evt.x_root, evt.y_root)
        if iid == self._iid:
            return
        self._reset()
        self._iid = iid
        if iid:
            self._job = self.tree.after(self.delay, self._show)

    def _reset(self, _evt=None):
        if self._job is not None:
            try:
                self.tree.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        self._iid = None
        self.hide()

    def _show(self):
        self._job = None
        iid = self._iid
        if not iid or not self.tree.exists(iid):
            return
        try:
            text = self.text_for(iid)
        except Exception:                 # noqa: BLE001 - a tip never breaks
            text = None
        if not text:
            return
        from genesisleaf.ui import theme as _theme
        x, y = self._xy
        self._tw = tw = tk.Toplevel(self.tree)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x + 16, y + 18))
        tk.Label(tw, text=text, justify="left", anchor="w",
                 wraplength=self.wrap, padx=6, pady=4,
                 background=_theme.TH_PANEL_BG, foreground=_theme.TH_FG,
                 relief="solid", borderwidth=1,
                 font=("Segoe UI", 9)).pack()

    def hide(self):
        if self._tw is not None:
            try:
                self._tw.destroy()
            except tk.TclError:
                pass
            self._tw = None


class Choice:
    """A value + list of allowed values that quacks like a read-only
    ttk.Combobox (get / set / current / ["values"] / configure).

    The main window's section and status filters used to be comboboxes;
    their UI now lives in the navigator sidebar, but a lot of code still
    talks to `app.sec_cb` / `app.st_cb` the combobox way.  `on_change`
    (optional) is told whenever the value or the list changes, so the
    sidebar can mirror it."""

    def __init__(self, values=("All",), on_change=None):
        self._values = list(values)
        self._value = self._values[0] if self._values else ""
        self.on_change = on_change

    def _notify(self):
        if self.on_change is not None:
            self.on_change(self)

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        self._notify()

    def current(self, index=None):
        if index is None:
            try:
                return self._values.index(self._value)
            except ValueError:
                return -1
        self._value = self._values[index]
        self._notify()
        return index

    def __getitem__(self, key):
        if key == "values":
            return tuple(self._values)
        raise KeyError(key)

    def __setitem__(self, key, value):
        if key != "values":
            raise KeyError(key)
        self._values = list(value)
        self._notify()

    def configure(self, **kw):
        if "values" in kw:
            self["values"] = kw["values"]

    config = configure

    def cget(self, key):
        return self[key]

    def bind(self, *_a, **_k):
        """Comboboxes get bound to <<ComboboxSelected>>; nothing to do."""
        return None
