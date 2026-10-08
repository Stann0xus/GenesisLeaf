"""Theme switching, ttk styling, text-tag styles and the theme dialogs.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk

from genesisleaf.core.colors import mix, norm_color, readable_on, rel_lum
from genesisleaf.core.config import load_config, save_config
from genesisleaf.core.constants import SEARCH_SCOPES
from genesisleaf.core import palette as _palette
from genesisleaf.core.palette import CF_MAX
from genesisleaf.ui.fonts import FONT_MONO_B, FONT_UI_B, FONT_UI_SM
from genesisleaf.ui.theme import (
    apply_preview_scheme,
    CLASSIC_THEMES, TAG_STYLES, set_theme,
)
from genesisleaf.ui import skin as _skin
from genesisleaf.ui import theme as _theme

# colour options of plain Tk / ttk widgets that can carry a palette colour
_COLOR_OPTS = ("foreground", "background", "activeforeground",
               "activebackground", "selectbackground", "selectforeground",
               "insertbackground", "highlightbackground", "highlightcolor",
               "disabledforeground", "troughcolor")


class AppearanceMixin:
    """Theme switching, ttk styling, text-tag styles and the theme dialogs.

    Mixed into `App`; `self` is the main window.
    """

    # -- styling ----------------------------------------------------------
    def set_theme(self, name):
        """Choose widget colours and tint the graphical Legaia menu chrome."""
        return self._switch_look(lambda: set_theme(name))

    def set_menu_ui(self, on):
        """Options > Legaia menu UI: the game's menu chrome (the ttk theme in
        ui.skin plus its palette) on, or the classic UI (clam + Default /
        Midnight) off.  Falls back to the classic UI when the sprites or
        Pillow are missing."""
        self._menu_ui_pref = bool(on)       # what the user asked for
        on = bool(on) and getattr(self, "_skin_ok", False)
        result = self._switch_look(lambda: _theme.set_menu_ui(on))
        try:
            self._menu_ui_var.set(on)
        except (AttributeError, tk.TclError):
            pass
        return result

    def _switch_look(self, change):
        """Re-skin the whole program live.

        `change` rebinds the TH_* globals (ui.theme), so everything built from
        here on already uses the new palette; then the ttk theme is selected,
        colours that widgets were created with are carried over to the new
        palette, and `apply_theme` re-pushes the palette into the ttk styles
        and the plain Tk widgets that already exist.  Finally the text tags
        and existing row tags are reconfigured in place."""
        old = _theme.current_values()
        result = change()
        _skin.use(self.style, _theme.MENU_UI)
        try:
            self._theme_var.set(_theme.CLASSIC_THEME)
        except (AttributeError, tk.TclError):
            pass
        self._remap_colors(old, _theme.current_values())
        self.apply_theme()
        self.trans_tag_styles()
        self.configure_text_tags(self.tr_txt)
        for w in self._line_ed_map.values() if hasattr(self, "_line_ed_map") else ():
            self.configure_text_tags(w)
        self.apply_tree_tags()
        if hasattr(self, "cmp_tree_r"):
            self._cmp_apply_tags()
        if hasattr(self, "_notes_paint"):
            self._notes_paint()
        if hasattr(self, "_rebuild_menubar"):
            self._rebuild_menubar()
        # Tag colours are live ttk state: theme switching does not require
        # destroying/reinserting every table row or discarding picked cells.
        self.cellsel.schedule()
        for name in ("cmp_cellsel", "cmp_cellsel_r"):
            picker = getattr(self, name, None)
            if picker is not None:
                picker.schedule()
        for v in list(self._views):
            v.apply_theme()
        for tree in self._all_trees():
            hand = getattr(tree, "_hand_cursor", None)
            if hand is not None:
                hand.refresh()
        for hand in getattr(self, "_hand_cursors", ()):
            hand.refresh()
        self.refresh_previews()
        self.persist_settings()
        return result

    def _remap_colors(self, old, new):
        """Widgets created with a literal palette colour (`foreground=TH_FG_MUTED`
        and the like) keep it across a palette change; carry every such colour
        over to the same role in the new palette."""
        table = {}
        for key in _theme._THEME_KEYS:
            table.setdefault(old[key].lower(), new[key])

        def walk(w):
            for opt in _COLOR_OPTS:
                try:
                    cur = str(w.cget(opt)).lower()
                except (tk.TclError, AttributeError):
                    continue
                to = table.get(cur)
                if to and to.lower() != cur:
                    try:
                        w.configure(**{opt: to})
                        w._gl_fg = None      # re-derived by the contrast pass
                    except tk.TclError:
                        pass
            for child in w.winfo_children():
                walk(child)
        try:
            walk(self.root)
        except tk.TclError:
            pass

    def refresh_previews(self):
        """Redraw every real-font preview that is on screen.

        Called after a theme switch (the preview colours follow the theme,
        see ui.theme.preview_scheme_for) and after the real-font options
        change.  Each step is guarded: a window that is closed or was never
        opened is simply skipped."""
        self._preview_tag_styles(self.prev_txt)
        steps = [self.update_preview]
        if getattr(self, "pv_fwin", None) is not None:
            steps.append(self._draw_float_preview)
        if getattr(self, "_cmp_pv_canvases", None):
            steps.append(self._cmp_show_detail)
        wb = getattr(self, "wb", None)
        if wb is not None:
            steps.append(wb._draw_preview)
        steps.append(self._rebuild_playground)
        for fn in steps:
            try:
                fn()
            except (tk.TclError, AttributeError):
                pass

    def _rebuild_playground(self):
        """The Playground draws its cards once, so rebuild it in place
        (keeping whatever is typed in its Box editor)."""
        win = getattr(self, "playground_win", None)
        if win is None or not win.winfo_exists():
            return
        if "playground" in getattr(self, "_tool_lazy", {}):
            return               # not opened yet: built fresh on first open
        text = None
        for child in win.winfo_children():
            ed = getattr(child, "ed", None)
            if ed is not None:
                text = ed.get("1.0", "end-1c")
            child.destroy()
        tab = self._build_playground_tab(win)
        tab.pack(fill="both", expand=True)
        if text is not None:
            tab.ed.delete("1.0", "end")
            tab.ed.insert("1.0", text)

    def _all_trees(self):
        """Every live row table: the main one plus any extra view windows.

        Row status tags are configured per Treeview, so anything that iterates
        "the trees" has to include the new views or a second window silently
        keeps the old palette."""
        trees = [self.tree]
        for view in getattr(self, "_views", None) or ():
            tree = getattr(view, "tree", None)
            if tree is not None:
                trees.append(tree)
        return trees

    def apply_tree_tags(self):
        """Row status colours live on the Treeview, not in a ttk style, so a
        theme switch has to push them into every tree by hand.  Kept separate
        from the build path so a new view window can reuse it verbatim."""
        for tree in self._all_trees():
            tree.tag_configure("ok", foreground=_theme.TH_OK)
            tree.tag_configure("warn", foreground=_theme.TH_WARN)
            tree.tag_configure("grow", foreground=_theme.TH_ACCENT)
            tree.tag_configure("bad", foreground=_theme.TH_BAD)
            tree.tag_configure("non", foreground=_theme.TH_BAD, font=FONT_MONO_B)
            tree.tag_configure("off", foreground=_theme.TH_FG_FAINT)
            tree.tag_configure("over_src", foreground=_theme.TH_OVERDRAW_SRC)
            tree.tag_configure("over_tr", foreground=_theme.TH_OVERDRAW_TR)
            # the zebra stripes live in tags too, and were only ever set where
            # the tree is built - so after a theme switch every *other* colour
            # moved and the stripes stayed behind, which is what made the table
            # look like it had ignored the theme
            tree.tag_configure("band_a", background=_theme.TH_BAND_A)
            tree.tag_configure("band_b", background=_theme.TH_BAND_B)

    def persist_settings(self):
        data = load_config()
        data["theme"] = _theme.CLASSIC_THEME
        # the choice, not what could be shown: a machine without Pillow must
        # not switch the menu UI off for good
        data["menu_ui"] = bool(getattr(self, "_menu_ui_pref", True))
        data["macros"] = {k: v for k, v in (getattr(self, "macros", None) or {}).items()
                          if v}
        data["search_scope"] = getattr(self, "find_scope", "All")
        data["max_ed_lines"] = int(getattr(self, "max_ed_lines", 10) or 10)
        data["jp_font"] = getattr(self, "jp_family", None) or ""
        data["rf_config"] = getattr(self, "rf_config", {})
        save_config(data)

    def restore_settings(self):
        """Apply the stored theme / macros / scope.  Safe to call before the
        widgets exist: every step is individually guarded."""
        data = load_config()
        self.rf_config = data.get("rf_config", {})
        # previews follow the theme unless the user chose the retail colours
        _palette.FOLLOW_THEME = not bool(self.rf_config.get("retail_colors"))
        apply_preview_scheme()
        # before the theme name is resolved, so a saved custom theme can be
        # the one the config asks for
        want = data.get("theme")
        if want in CLASSIC_THEMES:
            set_theme(want)
        # the game-menu UI is on by default; it needs Pillow + the sprites
        self._skin_ok = _skin.install(self.root, self.style)
        self._menu_ui_pref = bool(data.get("menu_ui", True))
        _theme.set_menu_ui(self._menu_ui_pref and self._skin_ok)
        _skin.use(self.style, _theme.MENU_UI)
        if hasattr(self, "_theme_var"):
            self._theme_var.set(_theme.CLASSIC_THEME)
        scope = data.get("search_scope")
        if scope in SEARCH_SCOPES:
            self.find_scope = scope
        macros = data.get("macros")
        if isinstance(macros, dict):
            clean = {}
            for k, v in macros.items():
                if isinstance(k, str) and k.startswith("F") and isinstance(v, str):
                    clean[k] = v
            self.macros = clean
        mel = data.get("max_ed_lines")
        if isinstance(mel, int) and 1 <= mel <= 200:
            self.max_ed_lines = mel
        jpf = data.get("jp_font")
        if isinstance(jpf, str) and jpf:
            self.jp_family = jpf

    def apply_theme(self):
        """Push THEME_* into the ttk styles and the plain Tk widgets.

        Called once at start-up and again whenever a widget that did not exist
        yet is built later, so nothing keeps a stock colour.  Every lookup is
        guarded: a theme that does not know an option simply keeps its default
        rather than raising."""
        s = self.style
        root = self.root
        def cfg(style, **kw):
            try:
                s.configure(style, **kw)
            except tk.TclError:
                pass
        skinned = _theme.MENU_UI
        btn_bg = _theme.TH_FRAME_BG if skinned else _theme.TH_BTN_BG
        tool_bg = _theme.TH_CHROME_BG if skinned else _theme.TH_BTN_BG
        btn_hot = _theme.TH_FRAME_BG if skinned else _theme.TH_BTN_HOVER
        tool_hot = _theme.TH_CHROME_BG if skinned else _theme.TH_BTN_HOVER
        cfg(".", background=_theme.TH_FRAME_BG, foreground=_theme.TH_FG,
            fieldbackground=_theme.TH_FIELD_BG, bordercolor=_theme.TH_BORDER,
            lightcolor=_theme.TH_FRAME_BG, darkcolor=_theme.TH_BORDER)
        cfg("TFrame", background=_theme.TH_FRAME_BG)
        cfg("TLabel", background=_theme.TH_FRAME_BG, foreground=_theme.TH_FG)
        cfg("TPanedwindow", background=_theme.TH_FRAME_BG)
        cfg("TLabelFrame", background=_theme.TH_FRAME_BG, bordercolor=_theme.TH_BORDER,
            relief="solid", thickness=1)
        cfg("TLabelFrame.Label", background=_theme.TH_FRAME_BG,
            foreground=_theme.TH_FG_MUTED)
        cfg("TButton", background=btn_bg, foreground=_theme.TH_BTN_FG,
            bordercolor=_theme.TH_BORDER, focuscolor=_theme.TH_ACCENT, padding=(8, 3))
        cfg("TEntry", fieldbackground=_theme.TH_FIELD_BG, foreground=_theme.TH_FG,
            bordercolor=_theme.TH_BORDER, insertcolor=_theme.TH_FG, padding=2,
            selectbackground=_theme.TH_SEL_BG, selectforeground=_theme.TH_SEL_FG)
        cfg("TCombobox", fieldbackground=_theme.TH_FIELD_BG, background=_theme.TH_CHROME_BG,
            foreground=_theme.TH_FG, bordercolor=_theme.TH_BORDER, arrowcolor=_theme.TH_FG,
            padding=2, selectbackground=_theme.TH_SEL_BG,
            selectforeground=_theme.TH_SEL_FG)
        cfg("TSpinbox", fieldbackground=_theme.TH_FIELD_BG, foreground=_theme.TH_FG,
            bordercolor=_theme.TH_BORDER, insertcolor=_theme.TH_FG,
            selectbackground=_theme.TH_SEL_BG, selectforeground=_theme.TH_SEL_FG)
        cfg("TCheckbutton", background=_theme.TH_FRAME_BG, foreground=_theme.TH_FG)
        cfg("TRadiobutton", background=_theme.TH_FRAME_BG, foreground=_theme.TH_FG)
        cfg("TNotebook", background=_theme.TH_FRAME_BG, bordercolor=_theme.TH_BORDER)
        cfg("TNotebook.Tab", background=_theme.TH_CHROME_BG, foreground=_theme.TH_FG,
            padding=(10, 4))
        cfg("TSeparator", background=_theme.TH_BORDER)
        cfg("TMenubutton", background=btn_bg, foreground=_theme.TH_BTN_FG)
        cfg("Menubar.TButton", background=_theme.TH_CHROME_BG if skinned
            else _theme.TH_HEAD_BG,
            foreground=_theme.TH_HEAD_FG)
        cfg("Treeview", background=_theme.TH_TREE_BG, fieldbackground=_theme.TH_TREE_BG,
            foreground=_theme.TH_FG, bordercolor=_theme.TH_BORDER, borderwidth=1,
            rowheight=20, relief="solid")
        cfg("Treeview.Heading",
            background=_theme.TH_TREE_BG if skinned else _theme.TH_HEAD_BG,
            foreground=_theme.TH_HEAD_FG,
            bordercolor=_theme.TH_BORDER, relief="flat", padding=(4, 4))
        try:
            s.map("Treeview",
                  background=[("selected", _theme.TH_SEL_BG)],
                  foreground=[("selected", _theme.TH_SEL_FG)])
        except tk.TclError:
            pass
        for name in ("TScrollbar", "Vertical.TScrollbar",
                     "Horizontal.TScrollbar"):
            cfg(name, background=_theme.TH_SCROLL, troughcolor=_theme.TH_FRAME_BG,
                bordercolor=_theme.TH_BORDER, lightcolor=_theme.TH_SCROLL,
                darkcolor=_theme.TH_SCROLL,
                arrowcolor=readable_on(_theme.TH_FG, _theme.TH_SCROLL, 3.0))
            try:
                s.map(name, background=[
                    ("active", mix(_theme.TH_SCROLL, "#ffffff", 0.25))])
            except tk.TclError:
                pass

        # Contrast for the states ttk does not carry by default: focus rings
        # on fields, disabled foregrounds, and the checkbox indicator.
        try:
            s.map("TCheckbutton",
                  background=[("active", _theme.TH_FRAME_BG),
                              ("disabled", _theme.TH_FRAME_BG)],
                  foreground=[("disabled", _theme.TH_FG_FAINT)],
                  indicatorcolor=[("selected", _theme.TH_ACCENT),
                                  ("!selected", _theme.TH_BORDER)])
            s.map("TRadiobutton",
                  foreground=[("disabled", _theme.TH_FG_FAINT)])
            s.map("TCombobox",
                  fieldbackground=[("readonly", _theme.TH_FIELD_BG),
                                   ("disabled", _theme.TH_CHROME_BG)],
                  foreground=[("disabled", _theme.TH_FG_FAINT)],
                  background=[("active", _theme.TH_CHROME_BG)])
            s.map("TEntry",
                  bordercolor=[("focus", _theme.TH_ACCENT)],
                  lightcolor=[("focus", _theme.TH_ACCENT)],
                  foreground=[("disabled", _theme.TH_FG_FAINT)])
            s.map("TSpinbox",
                  bordercolor=[("focus", _theme.TH_ACCENT)],
                  foreground=[("disabled", _theme.TH_FG_FAINT)])
            s.map("TButton",
                  foreground=[("disabled", _theme.TH_FG_FAINT)],
                  background=[("pressed", btn_hot), ("active", btn_hot)])
            s.map("Treeview",
                  background=[("selected", _theme.TH_SEL_BG)],
                  foreground=[("selected", _theme.TH_SEL_FG),
                              ("disabled", _theme.TH_FG_FAINT)])
        except tk.TclError:
            pass
        # -- named styles of the 0x01b main window -------------------------
        cfg("Chrome.TFrame", background=_theme.TH_CHROME_BG)
        cfg("Menubar.TFrame", background=_theme.TH_CHROME_BG)
        cfg("Chrome.TLabel", background=_theme.TH_CHROME_BG,
            foreground=_theme.TH_FG)
        cfg("Chrome.TCheckbutton", background=_theme.TH_CHROME_BG,
            foreground=_theme.TH_FG)
        cfg("Tool.TButton", background=tool_bg,
            foreground=_theme.TH_BTN_FG, bordercolor=_theme.TH_BORDER,
            padding=(6, 1), font=FONT_UI_SM)
        cfg("Chrome.TCheckbutton", font=FONT_UI_SM)
        cfg("Small.TCheckbutton", font=FONT_UI_SM)
        cfg("Chip.TLabel", background=_theme.TH_ACCENT,
            foreground=readable_on(_theme.TH_FRAME_BG, _theme.TH_ACCENT))
        for name, col in (("BudgetOk", _theme.TH_OK),
                          ("BudgetWarn", _theme.TH_WARN),
                          ("BudgetBad", _theme.TH_BAD)):
            cfg(name + ".Horizontal.TProgressbar", background=col,
                troughcolor=_theme.TH_FIELD_BG, bordercolor=_theme.TH_BORDER,
                lightcolor=col, darkcolor=col)
        cfg("Horizontal.TProgressbar", background=_theme.TH_ACCENT,
            troughcolor=_theme.TH_FIELD_BG, bordercolor=_theme.TH_BORDER,
            lightcolor=_theme.TH_ACCENT, darkcolor=_theme.TH_ACCENT)
        try:
            s.map("Tool.TButton",
                  background=[("pressed", tool_hot), ("active", tool_hot)],
                  bordercolor=[("active", _theme.TH_BORDER)])
            s.map("Chrome.TCheckbutton",
                  background=[("active", _theme.TH_CHROME_BG)])
        except tk.TclError:
            pass
        if hasattr(self, "apply_table_zoom"):
            self.apply_table_zoom()
        if hasattr(self, "apply_navigator_tags"):
            self.apply_navigator_tags()
        if hasattr(self, "_nav_stats_seen"):
            self._nav_stats_seen = None          # recolour the section rows

        # The combobox dropdown is a plain Tk listbox that ignores ttk styles
        try:
            root.option_add("*TCombobox*Listbox.background", _theme.TH_FIELD_BG)
            root.option_add("*TCombobox*Listbox.foreground", _theme.TH_FG)
            root.option_add("*TCombobox*Listbox.selectBackground",
                            _theme.TH_SEL_BG)
            root.option_add("*TCombobox*Listbox.selectForeground",
                            _theme.TH_SEL_FG)
            root.option_add("*TCombobox*Listbox.font", FONT_UI_SM)
        except tk.TclError:
            pass

        try:
            root.configure(background=_theme.TH_FRAME_BG)
        except tk.TclError:
            pass
        # plain Tk widgets do not read ttk styles
        for w, bg, fg in ((getattr(self, "src_txt", None), _theme.TH_PANEL_BG, _theme.TH_FG),
                          (getattr(self, "tr_txt", None), _theme.TH_FIELD_BG, _theme.TH_FG),
                          (getattr(self, "l_tokens", None), _theme.TH_PANEL_BG, _theme.TH_FG),
                          (getattr(self, "cheat_txt", None), _theme.TH_PANEL_BG, _theme.TH_FG)):
            if w is None:
                continue
            try:
                w.configure(background=bg, foreground=fg, insertbackground=fg,
                            highlightbackground=_theme.TH_BORDER,
                            highlightcolor=_theme.TH_ACCENT,
                            selectbackground=_theme.TH_SEL_BG,
                            selectforeground=_theme.TH_SEL_FG,
                            selectborderwidth=0, **self._plain_border())
            except tk.TclError:
                pass
        for cv in (getattr(self, "prev_txt", None),
                   getattr(self, "dyn_cv", None),
                   getattr(self, "pv_guide", None)):
            if cv is None:
                continue
            try:
                cv.configure(background=_theme.BG_EDIT, highlightthickness=0,
                             selectbackground=_theme.TH_SEL_BG,
                             selectforeground=_theme.TH_SEL_FG)
            except tk.TclError:
                pass
        self._restyle_plain_widgets()

    @staticmethod
    def _plain_border():
        """Frame of the plain Tk text boxes: the menu UI gives them the game's
        bronze window edge (a 2px highlight ring), the classic UI a hairline."""
        if _theme.MENU_UI:
            return dict(borderwidth=0, relief="flat", highlightthickness=2)
        return dict(borderwidth=1, relief="solid", highlightthickness=1)

    def _watch_new_windows(self):
        """Every window that opens later (views, workbench, dialogs) builds its
        plain Tk widgets with stock colours; restyle each one as it is shown."""
        def on_map(evt):
            w = evt.widget
            try:
                if w.winfo_class() == "Toplevel":
                    self.root.after_idle(lambda: self._restyle_plain_widgets(w))
            except tk.TclError:
                pass
        self.root.bind_all("<Map>", on_map, add="+")

    def _restyle_plain_widgets(self, top=None):
        """Menus, dialogs and list boxes are plain Tk widgets: they ignore ttk
        styles, so push the palette into the live ones and into the option
        database, which the ones created later read."""
        pal = dict(bg=_theme.TH_FRAME_BG, fg=_theme.TH_FG)
        menu = dict(background=_theme.TH_CHROME_BG, foreground=_theme.TH_FG,
                    activebackground=_theme.TH_SEL_BG,
                    activeforeground=_theme.TH_SEL_FG,
                    disabledforeground=_theme.TH_FG_FAINT)
        try:
            self.root.option_add("*Toplevel.background", pal["bg"])
            for key, val in menu.items():
                self.root.option_add("*Menu." + key, val)
        except tk.TclError:
            pass

        def walk(w):
            kind = w.winfo_class()
            try:
                if kind == "Toplevel":
                    w.configure(background=pal["bg"])
                elif kind == "Menu":
                    w.configure(**menu)
                elif kind == "Text":
                    self._restyle_text(w)
                elif kind in ("TLabel", "TCheckbutton", "TRadiobutton"):
                    self._fix_label_contrast(w)
                elif kind == "Listbox":
                    w.configure(background=_theme.TH_PANEL_BG,
                                foreground=_theme.TH_FG,
                                selectbackground=_theme.TH_SEL_BG,
                                selectforeground=_theme.TH_SEL_FG,
                                highlightbackground=_theme.TH_BORDER,
                                highlightcolor=_theme.TH_ACCENT,
                                **self._plain_border())
            except tk.TclError:
                pass
            for child in w.winfo_children():
                walk(child)
        try:
            walk(top or self.root)
        except tk.TclError:
            pass                    # the window closed meanwhile

    @staticmethod
    def _hex(w, name):
        """A Tk colour name as #rrggbb ('' when it is not a colour)."""
        try:
            r, g, b = w.winfo_rgb(name)
        except tk.TclError:
            return ""
        return "#%02x%02x%02x" % (r >> 8, g >> 8, b >> 8)

    def _fix_label_contrast(self, w, minimum=3.5):
        """Labels created with a literal grey/green for the light palette are
        unreadable on a dark one (and vice versa): derive the colour that is
        shown from the one the label was created with.  Reversible, so it
        survives any number of palette switches."""
        try:
            cur = str(w.cget("foreground"))
        except tk.TclError:
            return
        base = getattr(w, "_gl_fg", None)
        if base is None or cur != getattr(w, "_gl_fg_shown", None):
            base = cur                       # new or re-coloured by its owner
        if not base:
            return
        kind = w.winfo_class()
        style = str(w.cget("style")) or kind
        bg = self._hex(w, self.style.lookup(style, "background")
                       or self.style.lookup(kind, "background"))
        fg = self._hex(w, base)
        if not bg or not fg:
            return
        want = readable_on(fg, bg, minimum)
        shown = base if want == norm_color(fg) else want
        w._gl_fg, w._gl_fg_shown = base, shown
        if shown != cur:
            w.configure(foreground=shown)

    def _fix_text_tags(self, w, minimum=3.5):
        """The same, for the foreground colours of a Text widget's tags."""
        text_bg = self._hex(w, str(w.cget("background")))
        if not text_bg:
            return
        seen = getattr(w, "_gl_tags", None)
        if seen is None:
            seen = w._gl_tags = {}
        for tag in w.tag_names():
            if tag == "sel":
                continue
            cur = str(w.tag_cget(tag, "foreground"))
            if not cur:
                continue
            base, shown = seen.get(tag, (None, None))
            if base is None or cur != shown:
                base = cur
            bg = self._hex(w, str(w.tag_cget(tag, "background"))) or text_bg
            fg = self._hex(w, base)
            if not fg:
                continue
            want = readable_on(fg, bg, minimum)
            shown = base if want == norm_color(fg) else want
            seen[tag] = (base, shown)
            if shown != cur:
                w.tag_configure(tag, foreground=shown)

    def _restyle_text(self, w):
        """A plain Text box that was not coloured by name: stock light boxes
        take the field colours on a dark palette; the previews' own dark
        scheme is kept.  Tag colours are made readable on the result."""
        try:
            bg = w.winfo_rgb(str(w.cget("background")))
            if bg == w.winfo_rgb(_theme.BG_EDIT):
                return                       # a real-font preview
            light = rel_lum(self._hex(w, str(w.cget("background")))) > 0.8
            if light and rel_lum(_theme.TH_FIELD_BG) < 0.5                     or bg == w.winfo_rgb("white"):
                w.configure(background=_theme.TH_FIELD_BG,
                            foreground=_theme.TH_FG,
                            insertbackground=_theme.TH_FG)
            w.configure(highlightbackground=_theme.TH_BORDER,
                        highlightcolor=_theme.TH_ACCENT,
                        selectbackground=_theme.TH_SEL_BG,
                        selectforeground=_theme.TH_SEL_FG,
                        **self._plain_border())
            self._fix_text_tags(w)
        except tk.TclError:
            pass

    def trans_tag_styles(self):
        for w in (self.src_txt, self.tr_txt, self.cheat_txt):
            for tag, opts in TAG_STYLES.items():
                try:
                    w.tag_configure(tag, **opts)
                except tk.TclError:
                    pass
            w.tag_configure("placeholder", foreground="#8a8a8a")
        self._preview_tag_styles(self.prev_txt)

    def _preview_tag_styles(self, w):
        w.tag_configure("p_sub", foreground="#96d8ff", font=FONT_UI_B)
        w.tag_configure("p_ctl", foreground="#ffe27a", font=FONT_UI_B)
        w.tag_configure("p_byte", foreground="#c9c9f0", font=FONT_UI_B)
        w.tag_configure("p_non", foreground="#ff6b6b", underline=True)
        w.tag_configure("p_fold", foreground="#d09dff", underline=True)
        for i in range(CF_MAX + 1):
            col = _palette.ink(i)
            w.tag_configure("p_pal%d" % i,
                            foreground="#%02x%02x%02x" % col)

    def configure_text_tags(self, w):
        for tag, opts in TAG_STYLES.items():
            try:
                w.tag_configure(tag, **opts)
            except tk.TclError:
                pass
        w.tag_configure("placeholder", foreground="#8a8a8a")
