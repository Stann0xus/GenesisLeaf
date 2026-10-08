"""Menu bar and global keyboard shortcuts.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk

from genesisleaf.ui.theme import SECTION_BREAKS, THEME_SECTIONS
from genesisleaf.ui import theme as _theme
from genesisleaf.ui.menubar import Menubar


class MenuMixin:
    """Menu bar and global keyboard shortcuts.

    Mixed into `App`; `self` is the main window.
    """

    # -- menu ---------------------------------------------------------------
    def _rebuild_menubar(self):
        """Re-present the menu bar after the UI style changed."""
        for bar in (getattr(self, "_menubar", None),
                    getattr(self, "_cmp_menubar", None)):
            if bar is not None:
                bar.sync()

    def _build_menu(self):
        m = tk.Menu(self.root)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label="Open pack...", accelerator="Ctrl+O",
                       command=self.open_pack)
        fm.add_command(label="Save pack", accelerator="Ctrl+S",
                       command=lambda: self.save_pack(ask=True))
        fm.add_command(label="Save pack as...", accelerator="Ctrl+Shift+S",
                       command=self.save_pack_as)
        fm.add_separator()
        fm.add_command(label="Compare with pack...", command=self.open_compare_pack)
        fm.add_command(label="Reload from disk (discard edits)",
                       command=self.reload_from_disk)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.on_close)
        m.add_cascade(label="File", menu=fm)

        nav = tk.Menu(m, tearoff=0)
        nav.add_command(label="Next entry", accelerator="Ctrl+N",
                        command=self.next_entry)
        nav.add_command(label="Previous entry", accelerator="Ctrl+P",
                        command=self.prev_entry)
        nav.add_separator()
        nav.add_command(label="Next untranslated", accelerator="Ctrl+Down",
                        command=self.next_empty)
        nav.add_command(label="Previous untranslated", accelerator="Ctrl+Up",
                        command=self.prev_empty)
        nav.add_command(label="Next clone", accelerator="Ctrl+Shift+C",
                        command=self.next_clone)
        nav.add_command(label="Back through my edits",
                        command=self.goto_last_edited)
        nav.add_separator()
        nav.add_command(label="Find", accelerator="Ctrl+F",
                        command=lambda: self.search_ent.focus_set())
        nav.add_command(label="Clear all filters", command=self.clear_filters)
        nav.add_command(label="Retag view", command=self.rebuild_view)
        m.add_cascade(label="Navigate", menu=nav)

        em = tk.Menu(m, tearoff=0)
        # add_command returns an item *index*, not a widget, so these are
        # relabelled with entryconfig() rather than .configure()
        self._undo_idx = em.add_command(
            label="Undo", accelerator="Ctrl+Z", command=self.do_undo)
        self._redo_idx = em.add_command(
            label="Redo", accelerator="Ctrl+Shift+Z", command=self.do_redo)
        em.add_separator()
        em.add_command(label="Copy row", accelerator="Ctrl+C",
                       command=self._on_copy_rows)
        em.add_command(label="Paste row", accelerator="Ctrl+V",
                       command=self._on_paste_rows)
        em.add_separator()
        em.add_command(label="Edit history...", command=self.open_history)
        em.add_command(label="Clear history", command=self.clear_history)
        m.add_cascade(label="Edit", menu=em)

        vm = tk.Menu(m, tearoff=0)
        self._nav_var = tk.BooleanVar(value=True)
        vm.add_checkbutton(label="Navigator sidebar", accelerator="Ctrl+B",
                           variable=self._nav_var,
                           command=self.toggle_navigator)
        vm.add_checkbutton(label="Real-font preview", variable=self.dyn_var,
                           command=self._toggle_dynamic)
        vm.add_checkbutton(label="Accent font", variable=self.accent_font_var,
                           command=self._toggle_accent_font)
        vm.add_separator()
        vm.add_command(label="Table text bigger", accelerator="Ctrl+=",
                       command=lambda: self.zoom_table(1))
        vm.add_command(label="Table text smaller", accelerator="Ctrl+-",
                       command=lambda: self.zoom_table(-1))
        vm.add_command(label="Table text reset", accelerator="Ctrl+0",
                       command=lambda: self.zoom_table(0))
        vm.add_separator()
        vm.add_command(label="Float preview", command=self.open_float_preview)
        vm.add_command(label="Workbench (measuring editor)",
                       command=self.open_workbench)
        vm.add_command(label="New view of this file",
                       accelerator="Ctrl+Shift+N", command=self.open_new_view)
        m.add_cascade(label="View", menu=vm)
        self._edit_menu = em

        tl = tk.Menu(m, tearoff=0)
        tl.add_command(label="Playground", command=lambda: self.open_tool("playground"))
        tl.add_separator()
        tl.add_command(label="Workbench (measuring editor)",
                       command=self.open_workbench)
        tl.add_separator()
        tl.add_command(label="Notes dashboard...",
                       command=lambda: self.open_notes_dashboard())
        tl.add_separator()
        tl.add_command(label="Pack statistics", command=self.show_stats)
        tl.add_command(label="Validate pack (full)", command=self.validate_pack)
        tl.add_command(label="Free space (budgets, pooled room, scenes)...",
                       command=self.show_space_report)
        tl.add_command(label="Measure free space on disc",
                       command=self.measure_space)
        tl.add_separator()
        tl.add_command(label="Progress window (detailed progress bars)", command=self.open_progress_window)
        tl.add_separator()
        tl.add_command(label="Build test ROM (patch pristine disc)...", command=self.build_test_rom)
        tl.add_separator()
        tl.add_command(label="Reload from disk (discard edits)", command=self.reload_from_disk)
        m.add_cascade(label="Tools", menu=tl)

        cm = tk.Menu(m, tearoff=0)
        self._fill_compare_menu(cm)
        m.add_cascade(label="Compare", menu=cm)

        om = tk.Menu(m, tearoff=0)
        # the game's own menu look is the default; the classic UI (stock ttk
        # chrome in the Default / Midnight palettes) stays one click away
        self._menu_ui_var = tk.BooleanVar(value=_theme.MENU_UI)
        om.add_checkbutton(
            label="Legaia menu UI (game look)", variable=self._menu_ui_var,
            command=lambda: self.set_menu_ui(self._menu_ui_var.get()),
            state="normal" if getattr(self, "_skin_ok", False) else "disabled")
        self.themes_menu = tk.Menu(om, tearoff=0)
        self._theme_var = tk.StringVar(value=_theme.CLASSIC_THEME)

        for section, themes in THEME_SECTIONS.items():
            section_menu = tk.Menu(self.themes_menu, tearoff=0)
            breaks = SECTION_BREAKS.get(section, ())
            for theme_name in themes:
                if theme_name in breaks:
                    section_menu.add_separator()
                section_menu.add_radiobutton(
                    label=theme_name, value=theme_name, variable=self._theme_var,
                    command=lambda n=theme_name: self.set_theme(n))
            self.themes_menu.add_cascade(label=section, menu=section_menu)
        om.add_cascade(label="Colour palette", menu=self.themes_menu)
        om.add_command(label="Edit function-key macros...",
                       command=self.open_macro_editor)
        om.add_command(label="Reset macros to defaults",
                       command=self.reset_macros)
        om.add_separator()
        om.add_command(label="Clipboard history...",
                       command=self.open_clip_history)
        om.add_command(label="Clear clipboard history",
                       command=self.clear_clip_history)
        om.add_separator()
        om.add_command(label="Max editor rows (selection-driven)...",
                       command=self.open_ed_limit_dialog)
        om.add_separator()
        om.add_command(label="New view of this file",
                       accelerator="Ctrl+Shift+N",
                       command=self.open_new_view)
        self.views_menu = tk.Menu(om, tearoff=0)
        om.add_cascade(label="Close a view", menu=self.views_menu)
        om.add_separator()
        om.add_command(label="Save / reset settings",
                       command=self.persist_settings)
        m.add_cascade(label="Options", menu=om)

        hm = tk.Menu(m, tearoff=0)
        hm.add_command(label="User guide", command=self.open_user_guide)
        hm.add_command(label="Keyboard shortcuts", command=self.show_shortcuts)
        hm.add_command(label="Cheatsheet",
                       command=lambda: self.open_tool("cheatsheet"))
        hm.add_separator()
        hm.add_command(label="About / credits", command=self.show_credits)
        m.add_cascade(label="Help", menu=hm)

        # native bar, or the game-style plaque bar while the menu UI is on
        self._menubar = Menubar(self.root, m)
        self.root.bind("<Control-b>", self.toggle_navigator)
        self.root.bind("<Control-equal>", lambda e: self.zoom_table(1))
        self.root.bind("<Control-plus>", lambda e: self.zoom_table(1))
        self.root.bind("<Control-minus>", lambda e: self.zoom_table(-1))
        self.root.bind("<Control-0>", lambda e: self.zoom_table(0))
        self.root.bind("<Control-o>", lambda e: self.open_pack())
        self.root.bind("<Control-s>", lambda e: self.save_pack(ask=True))
        self.root.bind("<Control-S>", lambda e: self.save_pack_as())
        self.root.bind("<Control-Shift-S>", lambda e: self.save_pack_as())
        self.root.bind("<Control-e>", lambda e: self.tr_txt.focus_set())
        self.root.bind("<Control-n>", lambda e: self.next_entry())
        self.root.bind("<Control-p>", lambda e: self.prev_entry())
        self.root.bind("<Control-Down>", lambda e: self.next_empty())
        self.root.bind("<Control-Up>", lambda e: self.prev_empty())
        self.root.bind("<Control-f>", lambda e: self.search_ent.focus_set())
        self.root.bind("<Control-Shift-C>", lambda e: self.next_clone())
        self.root.bind("<Control-Shift-N>", lambda e: self.open_new_view())
        # F1..F12 are the macro layer now (see bind_macros), so find-next moved
        # to Ctrl+G / Ctrl+Shift+G.  Both are still offered in the Find row's
        # own buttons, so nothing is lost.
        self.root.bind("<Control-g>", lambda e: self._find_step(1))
        self.root.bind("<Control-Shift-G>", lambda e: self._find_step(-1))
        # Undo/redo.  Bound on the root, so they work wherever the focus is in
        # this window, and re-bound on every view window's widgets, so a second
        # window drives the same shared history.
        self.root.bind("<Control-z>", self.do_undo)
        self.root.bind("<Control-Shift-Z>", self.do_redo)
        self.root.bind("<Control-y>", self.do_redo)   # the other convention
        # Alt+Arrow: always navigate the main table (single selection)
        # Alt+Shift+Arrow: extend/multi-select in the main table
        for key in ("Up", "Down", "Prior", "Next"):
            self.root.bind("<Alt-%s>" % key,
                           lambda e, k=key: self._alt_nav(e, k, multi=False))
            self.root.bind("<Alt-Shift-%s>" % key,
                           lambda e, k=key: self._alt_nav(e, k, multi=True))
        self._update_history_menu()
