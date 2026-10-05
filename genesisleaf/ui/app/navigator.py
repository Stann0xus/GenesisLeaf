"""The Navigator: the sidebar on the left of the main window.

    PACK      file name, language, overall progress bar
    FILTER VALUES  section, context, key, or budget values with progress
    STATUS         the status filters with live counts; click to filter
    DISPLAY   preview font, UI text size, pack language

The section/status selection is the single source of truth for the
filters: `self.sec_cb` / `self.st_cb` (ui.widgets.Choice) hold the values
the table filter reads, and they tell the navigator whenever code changes
them, so the highlight always matches what the table shows.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from genesisleaf.core.dialog import _hex_group_label
from genesisleaf.core.encoding import parse_text
from genesisleaf.core.space import verdict as space_verdict

from genesisleaf.ui import skin as _skin
from genesisleaf.ui import theme as _theme
from genesisleaf.ui.app.toolbar import STATUS_FILTERS
from genesisleaf.ui.fonts import (
    FONT_DEFAULT_FAMILY, FONT_DEFAULT_SIZE, FONT_UI_B, FONT_UI_SM,
    font_family, font_size, init_fonts,
)

ACCENT_LANGS = {"pt-br", "pt", "fr", "es", "it", "de", "nl", "pl", "cs", "hu",
                "ro", "sk", "sl", "hr", "sr", "bg", "el", "tr"}
LANGS = ["Auto"] + sorted(["pt-BR", "pt", "fr", "es", "it", "de", "nl", "pl",
                           "cs", "hu", "ro", "sk", "sl", "hr", "sr", "bg", "el",
                           "tr", "en", "ja", "ko", "zh"])
DOT = "●"


class NavigatorMixin:
    """The left sidebar: pack summary, section / status / context filters
    and display settings.

    Mixed into `App`; `self` is the main window.
    """

    def _nav_heading(self, parent, text, row):
        ttk.Label(parent, text=text, font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).grid(
            row=row, column=0, sticky="w", pady=(10, 2))

    def _build_navigator(self, parent):
        # a game window in the menu UI (gold frame), a plain frame otherwise
        f = ttk.Frame(parent, padding=(8, 4, 6, 6), style="Window.TFrame")
        f.columnconfigure(0, weight=1)
        self._nav_syncing = False
        self._nav_stats_seen = None

        # -- pack card -------------------------------------------------------
        card = ttk.Frame(f, padding=(4, 2, 4, 3), style="Window.TFrame")
        card.grid(row=0, column=0, rowspan=4, sticky="ew")
        card.columnconfigure(0, weight=1)
        self.nav_pack_name = ttk.Label(card, text="No pack loaded",
                                       font=FONT_UI_B, anchor="w")
        self.nav_pack_name.grid(row=0, column=0, sticky="ew")
        self.nav_pack_meta = ttk.Label(card, text="File > Open pack  (Ctrl+O)",
                                       font=FONT_UI_SM, anchor="w",
                                       foreground=_theme.TH_FG_MUTED)
        self.nav_pack_meta.grid(row=1, column=0, sticky="ew")
        self.nav_progress = ttk.Progressbar(card, mode="determinate",
                                            maximum=100)
        self.nav_progress.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.nav_progress_lab = ttk.Label(card, text="", font=FONT_UI_SM,
                                          foreground=_theme.TH_FG_MUTED)
        self.nav_progress_lab.grid(row=3, column=0, sticky="w")

        # -- metadata filters -------------------------------------------------
        self._nav_heading(f, "FILTER VALUES", 4)
        self.filter_by_cb = ttk.Combobox(
            f, state="readonly", font=FONT_UI_SM,
            values=("Section", "Context", "Key", "Budget"))
        self.filter_by_cb.set("Section")
        self.filter_by_cb.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        self.filter_by_cb.bind("<<ComboboxSelected>>", self._on_filter_field)
        sec_wrap = ttk.Frame(f)
        sec_wrap.grid(row=6, column=0, sticky="nsew")
        sec_wrap.columnconfigure(0, weight=1)
        sec_wrap.rowconfigure(0, weight=1)
        f.rowconfigure(6, weight=1)
        self.nav_sec = ttk.Treeview(sec_wrap, columns=("n", "pct"),
                                    show="tree", selectmode="browse",
                                    height=6)
        self.nav_sec.column("#0", width=110, minwidth=60, stretch=True)
        self.nav_sec.column("n", width=72, anchor="e", stretch=False)
        self.nav_sec.column("pct", width=40, anchor="e", stretch=False)
        vs = ttk.Scrollbar(sec_wrap, orient="vertical",
                           command=self.nav_sec.yview)
        self.nav_sec.configure(yscrollcommand=vs.set)
        self.nav_sec.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        self.nav_sec.bind("<<TreeviewSelect>>", self._nav_on_section)

        # -- status ----------------------------------------------------------
        self._nav_heading(f, "STATUS", 7)
        self.nav_st = ttk.Treeview(f, columns=("n",), show="tree",
                                   selectmode="browse",
                                   height=len(STATUS_FILTERS))
        self.nav_st.column("#0", width=150, minwidth=80, stretch=True)
        self.nav_st.column("n", width=62, anchor="e", stretch=False)
        self.nav_st.grid(row=8, column=0, sticky="ew")
        for st in STATUS_FILTERS:
            self.nav_st.insert("", "end", iid=st, text="%s  %s" % (DOT, st),
                               values=("",), tags=(self._nav_status_tag(st),))
        self.nav_st.bind("<<TreeviewSelect>>", self._nav_on_status)
        # the menu UI marks the picked row with the game's pointing hand
        self._hand_cursors = [_skin.HandCursor(t, lambda: _theme.MENU_UI)
                              for t in (self.nav_sec, self.nav_st)]
        for hand in self._hand_cursors:
            hand.refresh()

        # -- context ---------------------------------------------------------
        self.ctx_cb = ttk.Combobox(f, state="readonly", font=FONT_UI_SM,
                                   values=["All"])
        self.ctx_cb.current(0)
        self.ctx_cb.grid_remove()
        self.ctx_cb.bind("<<ComboboxSelected>>", self._on_context_combo)

        # -- display ---------------------------------------------------------
        self._nav_heading(f, "DISPLAY", 11)
        disp = ttk.Frame(f)
        disp.grid(row=12, column=0, sticky="ew")
        disp.columnconfigure(1, weight=1)
        ttk.Label(disp, text="Font", font=FONT_UI_SM).grid(
            row=0, column=0, sticky="w", padx=(0, 6))
        fams = sorted(set(tkfont.families()))
        if FONT_DEFAULT_FAMILY in fams:
            fams.remove(FONT_DEFAULT_FAMILY)
        fams.insert(0, FONT_DEFAULT_FAMILY)
        self.font_cb = ttk.Combobox(disp, state="readonly", font=FONT_UI_SM,
                                    values=fams, width=12)
        try:
            self.font_cb.current(fams.index(font_family()))
        except (ValueError, tk.TclError):
            self.font_cb.current(0)
        self.font_cb.grid(row=0, column=1, sticky="ew")
        self.font_cb.bind("<<ComboboxSelected>>", self._on_font_change)

        ttk.Label(disp, text="Size", font=FONT_UI_SM).grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=(3, 0))
        sizes = ["8", "9", "10", "11", "12", "13", "14", "16", "18", "20"]
        self.size_cb = ttk.Combobox(disp, state="readonly", width=4,
                                    font=FONT_UI_SM, values=sizes)
        try:
            self.size_cb.current(sizes.index(str(font_size())))
        except ValueError:
            self.size_cb.current(sizes.index(str(FONT_DEFAULT_SIZE)))
        self.size_cb.grid(row=1, column=1, sticky="w", pady=(3, 0))
        self.size_cb.bind("<<ComboboxSelected>>", self._on_font_size_change)

        ttk.Label(disp, text="Language", font=FONT_UI_SM).grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=(3, 0))
        self.lang_cb = ttk.Combobox(disp, state="readonly", width=8,
                                    font=FONT_UI_SM, values=LANGS)
        self.lang_cb.set("Auto")
        self.lang_cb.grid(row=2, column=1, sticky="w", pady=(3, 0))
        self.lang_cb.bind("<<ComboboxSelected>>", self._on_lang_change)

        self.apply_navigator_tags()
        self.navigator = f
        return f

    # -- colours ---------------------------------------------------------------
    @staticmethod
    def _nav_status_tag(st):
        return {"Untranslated": "st_off", "Translated": "st_ok",
                "Grows (free space)": "st_grow",
                "Won't fit": "st_warn", "Overdraw (source)": "st_odsrc",
                "Overdraw (translation)": "st_odtr",
                "Has non-ASCII": "st_bad"}.get(st, "st_all")

    def apply_navigator_tags(self):
        """Status dots in the theme's status colours (re-run on theme switch)."""
        if not hasattr(self, "nav_st"):
            return
        for tag, col in (("st_all", _theme.TH_FG), ("st_off", _theme.TH_FG_FAINT),
                         ("st_ok", _theme.TH_OK), ("st_warn", _theme.TH_WARN),
                         ("st_grow", _theme.TH_ACCENT),
                         ("st_odsrc", _theme.TH_OVERDRAW_SRC),
                         ("st_odtr", _theme.TH_OVERDRAW_TR),
                         ("st_bad", _theme.TH_BAD)):
            self.nav_st.tag_configure(tag, foreground=col)
        self.nav_sec.tag_configure("done", foreground=_theme.TH_OK)
        self.nav_sec.tag_configure("issues", foreground=_theme.TH_WARN)

    # -- filter <-> navigator --------------------------------------------------
    def _on_filter_field(self, _evt=None):
        self.filter_field = self.filter_by_cb.get() or "Section"
        self.filter_value = "All"
        self.filter_section = "All"
        self.filter_context = "All"
        self.sec_cb.set("All")
        self.ctx_cb.set("All")
        self.rebuild_view()

    def _on_context_combo(self, _evt=None):
        self.set_context_filter(self.ctx_cb.get() or "All")

    def _nav_choice_changed(self, choice):
        """Keep the status choice and metadata value list in sync."""
        if not hasattr(self, "nav_sec"):
            return
        if choice is self.st_cb:
            self._nav_stats_seen = None
            self._refresh_navigator()
        self._sync_filter_value_selection()

    def _sync_filter_value_selection(self):
        if not hasattr(self, "nav_sec"):
            return
        value = getattr(self, "filter_value", "All")
        self._nav_syncing = True
        try:
            if self.nav_sec.exists(value):
                self.nav_sec.selection_set(value)
                self.nav_sec.see(value)
            elif self.nav_sec.exists("All"):
                self.nav_sec.selection_set("All")
        finally:
            self._nav_syncing = False

    def _nav_on_section(self, _evt=None):
        if self._nav_syncing:
            return
        sel = self.nav_sec.selection()
        if not sel:
            return
        value = sel[0]
        # Treeview can emit a queued selection event after the navigator has
        # repopulated itself.  If it names the value already being filtered,
        # rebuilding here would recursively rebuild the table forever.
        if (value == getattr(self, "filter_value", "All") and
                getattr(self, "filter_field", "Section") in
                ("Section", "Context", "Key", "Budget")):
            return
        self.set_metadata_filter(getattr(self, "filter_field", "Section"), value)

    def _nav_on_status(self, _evt=None):
        if self._nav_syncing:
            return
        sel = self.nav_st.selection()
        if sel and sel[0] != self.st_cb.get():
            self.st_cb.set(sel[0])
            self.rebuild_view()

    # -- counts ------------------------------------------------------------------
    def _navigator_value(self, sec, entry):
        field = getattr(self, "filter_field", "Section")
        if field == "Section":
            return sec
        if field == "Context":
            raw = entry.get("context", "")
            label = _hex_group_label(raw)
            names, _groups = self._context_names("All")
            return label if label in names else (raw or "(none)")
        if field == "Key":
            return entry.get("key", "") or "(none)"
        return str(entry.get("budget", 0))

    def _refresh_navigator(self, st=None):
        """Show progress for every value of the active metadata dimension.

        The groups honor status/context/find filters, but deliberately ignore
        the currently selected metadata value so every sibling value keeps a
        useful progress figure while browsing.
        """
        if not hasattr(self, "nav_sec"):
            return
        pack = self.pack
        if not (pack and pack.flat):
            self.nav_pack_name.configure(text="No pack loaded")
            self.nav_pack_meta.configure(text="File > Open pack  (Ctrl+O)")
            self.nav_progress.configure(value=0)
            self.nav_progress_lab.configure(text="")
            return
        field = getattr(self, "filter_field", "Section")
        cache_key = (id(self.get_stats()), field, getattr(self, "filter_value", "All"),
                     self.filter_status, self.filter_context, self.filter_text)
        if cache_key == self._nav_stats_seen:
            self._sync_filter_value_selection()
            return
        self._nav_stats_seen = cache_key
        candidates = [i for i in range(len(pack.flat)) if self._filters(i, ignore_metadata=True)]
        active = [i for i in range(len(pack.flat)) if self._filters(i)]
        groups = {}
        order = []
        overall = {
            "total": len(active),
            "filled": sum(bool(pack.flat[i][1].get("translation", "")) for i in active),
            "issues": 0,
        }
        for i in candidates:
            sec, entry = pack.flat[i]
            name = self._navigator_value(sec, entry)
            if name not in groups:
                groups[name] = {"total": 0, "filled": 0, "issues": 0}
                order.append(name)
            d = groups[name]
            d["total"] += 1
            tr = entry.get("translation", "")
            d["filled"] += bool(tr)
            b, spans = parse_text(tr)
            if (tr and space_verdict(sec, entry, b) == "over") \
                    or any(x[2] == "nonascii" for x in spans):
                d["issues"] += 1
        order.sort(key=(lambda x: pack.section_names.index(x)) if field == "Section" else str.lower)
        self.nav_pack_name.configure(text=os.path.basename(pack.path) if pack.path else "untitled pack")
        self.nav_pack_meta.configure(text="%s  -  %d sections" % (
            pack.header.get("language") or "?", len(pack.section_names)))
        pct = 100.0 * overall["filled"] / overall["total"] if overall["total"] else 0.0
        self.nav_progress.configure(value=pct)
        self.nav_progress_lab.configure(text="%s of %s translated  (%.1f%%)" % (
            format(overall["filled"], ","), format(overall["total"], ","), pct))
        self._nav_syncing = True
        try:
            self.nav_sec.delete(*self.nav_sec.get_children())
            self.nav_sec.insert("", "end", iid="All", text="All values", values=(
                "%d/%d" % (overall["filled"], overall["total"]),
                "%d%%" % int(pct)))
            for name in order:
                d = groups[name]
                p = 100.0 * d["filled"] / d["total"] if d["total"] else 0.0
                tag = "issues" if d["issues"] else ("done" if p >= 100 else "")
                self.nav_sec.insert("", "end", iid=name, text=name, values=(
                    "%d/%d" % (d["filled"], d["total"]), "%d%%" % int(p)),
                    tags=(tag,))
            self._sync_filter_value_selection()
        finally:
            self._nav_syncing = False
        for hand in self._hand_cursors:
            hand.refresh()

    # -- display settings (formerly on the toolbar) -----------------------------
    def _on_font_change(self, _evt=None):
        fam = self.font_cb.get()
        if fam and fam != font_family():
            init_fonts(self.root, fam, font_size())
            self.trans_tag_styles()
            self.apply_theme()
            self.update_preview()
            self.update_status()

    def _on_font_size_change(self, _evt=None):
        try:
            sz = int(self.size_cb.get())
        except (ValueError, tk.TclError):
            return
        if sz and sz != font_size():
            init_fonts(self.root, font_family(), sz)
            self.trans_tag_styles()
            self.apply_theme()

    def _on_lang_change(self, _evt=None):
        """Language picked: switches the accent font on for accented
        languages; a manual pick is also written to the pack header."""
        lang = self.lang_cb.get()
        if lang == "Auto":
            pack_lang = (self.pack.header.get("language") or "").lower()
            self.accent_font_var.set(pack_lang in ACCENT_LANGS)
        else:
            self.accent_font_var.set(lang.lower() in ACCENT_LANGS)
            self.pack.header["language"] = lang
        self._toggle_accent_font()
        self.update_preview()
        self.update_status()
