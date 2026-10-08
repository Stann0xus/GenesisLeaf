"""Main window body (table + editor dock) and the Tools-menu window host.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.ui import theme as _theme


class LayoutMixin:
    """Main window body (table + editor dock) and the Tools-menu window host.

    Mixed into `App`; `self` is the main window.
    """

    # -- body ----------------------------------------------------------------
    def _build_body(self):
        """Navigator | (find bar + table over the editor dock).

        Both splits are draggable.  The table takes most of the extra
        height when the window grows; the navigator keeps its width and can
        be hidden (View > Navigator, Ctrl+B) to give the table the room."""
        host = ttk.Frame(self.root)
        host.pack(side="top", fill="both", expand=True, padx=6, pady=(4, 2))
        self.nav_toggle = ttk.Button(host, text="◀", width=2,
                                     command=self.toggle_navigator)
        self.nav_toggle.pack(side="left", anchor="n", padx=(0, 3))
        outer = ttk.Panedwindow(host, orient="horizontal")
        outer.pack(side="left", fill="both", expand=True)
        self.body_panes = outer

        self.nav_frame = self._build_navigator(outer)
        outer.add(self.nav_frame, weight=0)

        right = ttk.Panedwindow(outer, orient="vertical")
        outer.add(right, weight=1)
        self.main_panes = right

        top = ttk.Frame(right)
        top.columnconfigure(0, weight=1)
        top.rowconfigure(1, weight=1)
        self._build_findbar(top).grid(row=0, column=0, sticky="ew")
        self.editor_frame = self._build_entries_tab(top)
        self.editor_frame.grid(row=1, column=0, sticky="nsew")
        self._build_editor_dock(right)
        right.add(top, weight=3)
        right.add(self.edit_dock, weight=2)

        # the filters' stand-ins now exist: let the navigator mirror them
        self._nav_choice_changed(self.sec_cb)
        self._nav_choice_changed(self.st_cb)
        self.nav_visible = True
        self._toggle_dynamic()          # show the real-font view (default on)
        # place the splits once the window has its real size (before that
        # every pane is 1px and a sash position would be overridden)
        self._sash_bind = outer.bind("<Configure>", self._first_layout, add="+")
        self._build_tool_windows()

    def _first_layout(self, evt):
        if evt.width < 400:
            return
        try:
            self.body_panes.unbind("<Configure>", self._sash_bind)
        except tk.TclError:
            pass
        self.root.after_idle(self._initial_sashes)

    def _initial_sashes(self):
        """Sensible first split: a 270px navigator, the table ~55% high."""
        try:
            self.root.update_idletasks()
            if self.nav_visible:
                # the game-window frame and hand cursor take a little width
                self.body_panes.sashpos(0, 292 if _theme.MENU_UI else 260)
            h = self.main_panes.winfo_height()
            if h > 200:
                self.main_panes.sashpos(0, int(h * 0.52))
            w = self.dock_split.winfo_width()
            if w > 300:
                self.dock_split.sashpos(0, int(w * 0.56))
        except tk.TclError:
            pass

    def toggle_navigator(self, _evt=None):
        """View > Navigator (Ctrl+B): hide / show the sidebar."""
        try:
            if self.nav_visible:
                self.body_panes.forget(self.nav_frame)
            else:
                self.body_panes.insert(0, self.nav_frame, weight=0)
                self.root.after_idle(
                    lambda: self.body_panes.sashpos(0, 260))
        except tk.TclError:
            return "break"
        self.nav_visible = not self.nav_visible
        self.nav_toggle.configure(text="◀" if self.nav_visible else "▶")
        try:
            self._nav_var.set(self.nav_visible)
        except AttributeError:
            pass
        return "break"

    # -- tool windows (Tools menu / Help menu) -------------------------------
    # The former notebook tabs (Search, Dictionary, Auto-fix, Shared words,
    # Compare, Cheatsheet) are now independent Toplevel windows. They are built
    # eagerly (so the editor can drive their widgets) but stay withdrawn until
    # opened; closing one withdraws it again so its state is preserved.  The
    # Playground is the exception: nothing else drives it and it renders a
    # card per glyph (over a second of startup), so it is built on first open.
    LAZY_TOOLS = ("playground",)

    def _build_tool_windows(self):
        self._tool_wins = {}
        self._tool_lazy = {}
        specs = (
            ("search", self._build_search_tab, "Search", "760x520"),
            ("dictionary", self._build_dictionary_tab, "Dictionary / glossary",
             "820x520"),
            ("autofix", self._build_autofix_tab, "Auto-fix", "720x560"),
            ("cross", self._build_cross_tab, "Shared words / Dups", "980x560"),
            ("compare", self._build_compare_tab, "Compare packs", "1280x780"),
            ("notes", self._build_notes_tab, "Notes dashboard", "940x600"),
            ("cheatsheet", self._build_cheatsheet_tab, "Cheatsheet", "680x640"),
            ("playground", self._build_playground_tab, "Playground",
             "1220x820"),
        )
        for name, builder, title, geo in specs:
            self._build_tool_window(name, title, geo, builder)

    def _build_tool_window(self, name, title, geometry, builder):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry(geometry)
        win.withdraw()
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        if name in self.LAZY_TOOLS:
            self._tool_lazy[name] = builder
        else:
            frame = builder(win)
            frame.pack(fill="both", expand=True)
        setattr(self, name + "_win", win)
        self._tool_wins[name] = win
        return win

    def open_tool(self, name):
        win = self._tool_wins.get(name)
        if win is None:
            return
        builder = self._tool_lazy.pop(name, None)
        if builder is not None:
            builder(win).pack(fill="both", expand=True)
        if name == "compare" and hasattr(self, "l_cmp_left"):
            self._cmp_update_labels()
        win.deiconify()
        win.lift()
        win.focus_force()
