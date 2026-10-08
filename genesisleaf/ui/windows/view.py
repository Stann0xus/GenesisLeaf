"""Secondary view window onto the same pack (Options > New view).

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from time import perf_counter
from tkinter import ttk

from genesisleaf.core.bookkeeping import edited_on
from genesisleaf.core.constants import SEARCH_SCOPES
from genesisleaf.core.encoding import parse_text
from genesisleaf.core.space import KIND_LABEL, room_kind, verdict as space_verdict
from genesisleaf.ui.cellsel import CellSelection
from genesisleaf.ui.widgets import TreeRowTip
from genesisleaf.ui.fonts import FONT_MONO, FONT_UI, FONT_UI_B, FONT_UI_SM
from genesisleaf.ui.keys import _macro_key_ok
from genesisleaf.ui import theme as _theme


class ViewWindow:
    """A second top-level window onto the *same* pack.

    The main window keeps the full toolset.  This is deliberately the smaller
    half of the pair: filter bar, table, translation editor, status line.  What
    it buys is two things the main window cannot give you:

      * two independent cursors.  You can park one on a dialogue box you are
        rewriting and flip to the other to check a term, without losing either
        selection, because `current`/`view` are per-window.
      * the same data.  Both windows read and write one `Pack`, so an edit in
        either shows up in the other on the same keystroke, and Ctrl+C in one
        pastes into the other because the row clipboard lives on the App.

    It is a separate class rather than a second App because the App's ~6k lines
    assume one table; re-entering that code with `self` meaning "the main
    window" would make the live sync implicit and easy to get wrong.  Here every
    write goes through `commit`, which is the only place that touches the pack.
    """

    def __init__(self, app, geometry=None):
        self.app = app
        self.pack = app.pack
        self.win = tk.Toplevel(app.root)
        self.win.title("View - %s" % (app.pack.path or "no file"))
        self.win.geometry(geometry or "1100x700")
        self.win.minsize(700, 420)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        # per-window state; the main window's equivalents are its own
        self.current = -1
        self.view = []
        self.view_iid = {}
        self._iid_by_flat = {}
        self._pos_iids = []
        self._band_of = {}
        self._band_state = {"unit": None, "n": 0}
        self._band_map = {}
        self.filter_section = "All"
        self.filter_status = "All"
        self.filter_text = ""
        self._sort_col = None
        self._sort_rev = False
        self._select_lock = False
        self._loading = False
        self._editing = False          # set while this view made a change
        self._find_hits = None
        self._view_gen = 0
        self._insert_job = None
        self._line_ed_map = {}
        self._line_hdr_map = {}

        self._build()
        app.apply_tree_tags()
        for w in self._line_ed_map.values():
            app.configure_text_tags(w)
        self.rebuild_view()
        self._bind_macros()

    # -- construction -------------------------------------------------------
    def _build(self):
        app = self.app
        top = ttk.Frame(self.win, padding=(8, 6, 8, 4))
        top.pack(side="top", fill="x")

        grp = ttk.Frame(top)
        grp.pack(side="left")
        ttk.Label(grp, text="Section", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left")
        self.sec_cb = ttk.Combobox(grp, state="readonly", width=15,
                                   font=FONT_UI_SM,
                                   values=["All"] + sorted(app.pack.sections))
        self.sec_cb.current(0)
        self.sec_cb.pack(side="left", padx=(4, 8))
        self.sec_cb.bind("<<ComboboxSelected>>", lambda e: self.rebuild_view())

        ttk.Label(grp, text="Status", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left")
        self.st_cb = ttk.Combobox(
            grp, state="readonly", width=17, font=FONT_UI_SM,
            values=["All", "Untranslated", "Translated", "Grows (free space)",
                    "Won't fit",
                    "Overdraw (source)", "Overdraw (translation)",
                    "Has non-ASCII"])
        self.st_cb.current(0)
        self.st_cb.pack(side="left", padx=(4, 8))
        self.st_cb.bind("<<ComboboxSelected>>", lambda e: self.rebuild_view())

        ttk.Label(grp, text="in", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left")
        self.scope_cb = ttk.Combobox(grp, state="readonly", width=17,
                                     font=FONT_UI_SM,
                                     values=list(SEARCH_SCOPES))
        self.scope_cb.set(app.find_scope)
        self.scope_cb.pack(side="left", padx=(4, 8))
        self.scope_cb.bind("<<ComboboxSelected>>", self._on_scope)

        fnd = ttk.Frame(top)
        fnd.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Label(fnd, text="Find", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left")
        self.search_ent = ttk.Entry(fnd, font=FONT_UI_SM)
        self.search_ent.pack(side="left", fill="x", expand=True, padx=4)
        self.search_ent.bind("<Return>", lambda e: self.find_step(1))
        self.search_ent.bind("<Shift-Return>", lambda e: self.find_step(-1))
        self.find_lab = ttk.Label(fnd, text="", font=FONT_UI_SM,
                                  foreground=_theme.TH_FG_MUTED)
        self.find_lab.pack(side="left", padx=(6, 0))

        self.nav_lab = ttk.Label(top, text="", font=FONT_UI_SM)
        self.nav_lab.pack(side="right")

        # -- table -----------------------------------------------------------
        body = ttk.Frame(self.win, padding=(8, 0, 8, 0))
        body.pack(side="top", fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            body,
            columns=("ord", "st", "note", "sec", "key", "context", "source",
                     "tr", "bytes"),
            show="headings", selectmode="extended")
        for col, (txt, w) in (("ord", ("#", 46)), ("st", ("", 28)),
                              ("note", ("✎", 24)),
                              ("sec", ("Section", 86)), ("key", ("Key", 190)),
                              ("context", ("Context", 150)),
                              ("source", ("Source", 200)),
                              ("tr", ("Translation", 200)),
                              ("bytes", ("B/S", 58))):
            self.tree.heading(col, text=txt,
                              command=lambda c=col: self.sort_by(c))
            self.tree.column(col, width=w, anchor="w",
                             stretch=col not in ("ord", "st", "note"))
        self.tree.column("note", anchor="center")
        self.tree.column("bytes", anchor="e")
        self.tree.column("ord", anchor="e")
        vs = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        # entries carrying `notes`: tooltip + Alt+double-click, as in the
        # main table
        TreeRowTip(self.tree, lambda iid: self.app._table_row_tip_for(
            self.view_iid.get(iid)))
        self.tree.bind("<Alt-Double-Button-1>", self._alt_dbl)
        self.tree.bind("<Up>", self.on_rowkey)
        self.tree.bind("<Down>", self.on_rowkey)
        self.tree.bind("<Prior>", self.on_rowkey)
        self.tree.bind("<Next>", self.on_rowkey)
        self.tree.bind("<Control-c>", self.on_copy)
        self.tree.bind("<Control-v>", self.on_paste)
        self.tree.bind("<Control-Shift-C>", lambda e: self.on_copy(e))
        self.tree.bind("<Delete>", lambda e: self.on_delete(e))
        # Ctrl+Click picks cells, plain clicks select rows (ui/cellsel.py)
        self.cellsel = CellSelection(
            self.tree,
            on_pick=lambda rows: (self.tree.selection_set(rows),
                                  self.tree.see(rows[-1])),
            on_copy=self.app._push_clip_history)
        # this window drives the App's one shared history, so undo/redo work
        # from here exactly as they do in the main window
        self.tree.bind("<Control-z>", self.app.do_undo)
        self.tree.bind("<Control-Shift-Z>", self.app.do_redo)
        self.tree.bind("<Control-y>", self.app.do_redo)

        # -- editor dock (perfect clone of main window's dock) -----------------
        # Use a vertical PanedWindow to split table and editor dock
        vp = ttk.Panedwindow(self.win, orient="vertical")
        vp.pack(side="top", fill="both", expand=True, padx=6, pady=6)

        # Table pane (already built above, reparent it)
        # Actually, the tree is already in `body` which is packed. We need to restructure.
        # Let me rebuild the layout properly: table in top pane, editor dock in bottom pane.
        # The current `body` frame contains the tree. We'll move it to the PanedWindow.
        body.pack_forget()
        vp.add(body, weight=3)

        # ---- editor dock (bottom pane) --------------------------------------
        f = ttk.Frame(vp, padding=(6, 4, 6, 4))
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        vp.add(f, weight=1)
        try:
            vp.paneconfigure(body, minsize=160, height=420)
            vp.paneconfigure(f, minsize=190, height=320)
        except tk.TclError:
            pass

        # row 0: section / key / context / bytes (full width)
        r0 = ttk.Frame(f)
        r0.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(r0, text="Section:", font=FONT_UI_SM).pack(side="left")
        self.l_sec = ttk.Label(r0, text="-", font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED)
        self.l_sec.pack(side="left", padx=(2, 10))
        ttk.Label(r0, text="Key:", font=FONT_UI_SM).pack(side="left")
        self.l_key = ttk.Label(r0, text="-", font=FONT_UI)
        self.l_key.pack(side="left", padx=(2, 4))
        self.b_copy_key = ttk.Button(r0, text="Copy key", width=9, command=self.copy_key)
        self.b_copy_key.pack(side="left")
        self.l_selcount = ttk.Label(r0, text="", font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED)
        self.l_selcount.pack(side="left", padx=(4, 0))
        ttk.Separator(r0, orient="vertical").pack(side="left", fill="y", padx=10, pady=2)
        ttk.Label(r0, text="Context:", font=FONT_UI_SM).pack(side="left")
        self.e_context = ttk.Entry(r0, font=FONT_UI, state="readonly")
        self.e_context.pack(side="left", fill="x", expand=True, padx=(2, 0))
        self.b_copy_ctx = ttk.Button(r0, text="Copy", width=6, command=self.copy_context)
        self.b_copy_ctx.pack(side="left", padx=(2, 8))
        self.l_budget = ttk.Label(r0, text="", font=FONT_UI)
        self.l_budget.pack(side="right", padx=(0, 8))
        self.l_src_bytes = ttk.Label(r0, text="", font=FONT_UI)
        self.l_src_bytes.pack(side="right")

        # ---- draggable editor / preview split ---------------------------------
        hp = ttk.Panedwindow(f, orient="horizontal")
        hp.grid(row=1, column=0, sticky="nsew", pady=(4, 0))

        leftp = ttk.Frame(hp, padding=(0, 0, 6, 0))
        leftp.rowconfigure(1, weight=1)
        leftp.rowconfigure(3, weight=2)
        leftp.columnconfigure(0, weight=1)

        rep = ttk.Frame(hp, padding=(6, 0, 0, 0))
        rep.rowconfigure(1, weight=1)
        rep.columnconfigure(0, weight=1)

        hp.add(leftp, weight=3)
        hp.add(rep, weight=2)
        self.dock_split = hp
        try:
            hp.paneconfigure(leftp, minsize=380, width=620)
            hp.paneconfigure(rep, minsize=300, width=420)
        except tk.TclError:
            pass

        ttk.Label(leftp, text="Source", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).grid(row=0, column=0, sticky="w")
        src_wrap = ttk.Frame(leftp)
        src_wrap.grid(row=1, column=0, sticky="nsew")
        src_wrap.columnconfigure(0, weight=1)
        src_wrap.rowconfigure(0, weight=1)
        self.src_txt = tk.Text(src_wrap, height=3, wrap="char", font=FONT_MONO,
                               state="disabled", bg=_theme.TH_PANEL_BG, fg=_theme.TH_FG,
                               padx=3, pady=2, relief="solid", borderwidth=1)
        self.src_txt.grid(row=0, column=0, sticky="nsew")
        src_vs = ttk.Scrollbar(src_wrap, orient="vertical",
                               command=self.src_txt.yview)
        src_vs.grid(row=0, column=1, sticky="ns")
        self.src_txt.configure(yscrollcommand=src_vs.set)

        lab = ttk.Frame(leftp)
        lab.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        ttk.Label(lab, text="Translation", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left")
        self.l_tr_bytes = ttk.Label(lab, text="", font=FONT_UI)
        self.l_tr_bytes.pack(side="left", padx=(10, 0))
        self.l_status = ttk.Label(lab, text="", font=FONT_UI_B)
        self.l_status.pack(side="left", padx=(16, 0))
        self.l_flash = ttk.Label(lab, text="", font=FONT_UI_B, foreground=_theme.TH_ACCENT)
        self.l_flash.pack(side="left", padx=(16, 0))
        self._flash_job = None
        self.multi_cb = ttk.Checkbutton(lab, text="Multi-line rows",
                                        variable=self.app.multi_var,
                                        command=self.on_multi_toggle,
                                        takefocus=False)
        self.multi_cb.pack(side="right")

        tr_inner = ttk.Frame(leftp)
        tr_inner.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
        tr_inner.rowconfigure(1, weight=1)
        tr_inner.columnconfigure(0, weight=1)

        self.l_ed_summary = ttk.Label(tr_inner, text="", font=FONT_UI_SM,
                                      foreground=_theme.TH_FG_MUTED, anchor="w")
        self.l_ed_summary.grid(row=0, column=0, sticky="ew")

        self.tr_single = ttk.Frame(tr_inner)
        self.tr_single.grid(row=1, column=0, sticky="nsew")
        self.tr_single.rowconfigure(0, weight=1)
        self.tr_single.columnconfigure(0, weight=1)
        self.tr_txt = tk.Text(self.tr_single, height=6, wrap="char",
                              font=FONT_MONO, undo=True, padx=3, pady=2,
                              relief="solid", borderwidth=1,
                              highlightthickness=1,
                              insertbackground=_theme.TH_FG)
        self._tr_single_ed = self.tr_txt
        self.tr_txt._flat_idx = None
        self.tr_txt._ed_flat = []
        self.tr_txt._ed_prev = []
        self.tr_txt.grid(row=0, column=0, sticky="nsew")
        tvs = ttk.Scrollbar(self.tr_single, orient="vertical",
                            command=self.tr_txt.yview)
        tvs.grid(row=0, column=1, sticky="ns")
        self.tr_txt.configure(yscrollcommand=tvs.set)
        self.app._bind_editor_keys(self.tr_txt)
        self.tr_txt.bind("<Return>", self.on_tr_return)
        self.tr_txt.bind("<<Modified>>", self.on_tr_modified)
        self.tr_txt.bind("<Control-z>", self.app.do_undo)
        self.tr_txt.bind("<Control-Shift-Z>", self.app.do_redo)
        self.tr_txt.bind("<Control-y>", self.app.do_redo)

        self.tr_multi = ttk.Frame(tr_inner)
        self.tr_multi.grid(row=1, column=0, sticky="nsew")
        self.tr_multi.columnconfigure(0, weight=1)
        self.tr_multi.grid_remove()
        self._line_ed_map = {}
        self._line_hdr_map = {}

        # Insert-token buttons, responsive
        self.tok_row = tok_row = ttk.Frame(leftp)
        tok_row.grid(row=4, column=0, sticky="ew", pady=(2, 0))
        self._tok_label = ttk.Label(tok_row, text="Insert token:",
                                    font=FONT_UI_SM)
        self._tok_label.pack(side="left")
        self._tok_cells = ttk.Frame(tok_row)
        self._tok_cells.pack(side="left")
        self._tok_btns = []
        tokens = ["|", "{01}", "{c1:00}", "{c2:79}", "{c3:0e}",
                  "{c5:02}", "{c7:00}", "{cf:09}", "{ce:10}", "{7b}", "{7d}"]
        for k, t in enumerate(tokens):
            b = ttk.Button(self._tok_cells, text=t, width=7, takefocus=False,
                           command=lambda s=t: self.insert_token(s))
            b.grid(row=0, column=k, padx=1)
            self._tok_btns.append(b)
        self._tok_more = ttk.Button(
            self._tok_cells, text="More \u25be", width=6, takefocus=False,
            command=self._tok_more_menu)
        self._tok_more.grid(row=0, column=len(tokens), padx=2)
        self._tok_more.grid_remove()
        self._tok_menu = tk.Menu(self.win, tearoff=0)
        self._tok_compact = False
        self._tok_job = None
        self._tok_sizes = None
        self._tok_sizes_c = None
        self._tok_hint = ttk.Label(
            tok_row, text="Enter = '|' newline    Ctrl+Enter = '|' (box) / real newline (single)",
            font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED)
        self._tok_hint.pack(side="right")
        tok_row.bind("<Configure>", self._relayout_tokens)
        self.win.after_idle(self._tok_layout_now)

        # ---- right column: preview panel -------------------------------------
        pv_tools = ttk.Frame(rep)
        pv_tools.grid(row=0, column=0, sticky="ew")
        ttk.Label(pv_tools, text="Preview", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left")
        self.b_dyn = ttk.Checkbutton(pv_tools, text="Real font",
                                     variable=self.app.dyn_var,
                                     command=self._toggle_dynamic)
        self.b_dyn.pack(side="left", padx=(8, 0))
        self.b_dyn_size = ttk.Checkbutton(pv_tools, text="Dynamic",
                                          variable=self.app.dyn_size_var,
                                          command=self._toggle_dyn_size)
        self.b_dyn_size.pack(side="left", padx=(2, 0))
        ttk.Button(pv_tools, text="Float preview",
                   command=self.app.open_float_preview,
                   takefocus=False).pack(side="left", padx=(10, 0))
        ttk.Label(pv_tools, text="scale", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="right", padx=(2, 0))
        self.l_pv_scale = ttk.Label(pv_tools, text="2x", width=3,
                                    font=FONT_UI_SM, anchor="center")
        self.l_pv_scale.pack(side="right")
        ttk.Button(pv_tools, text="+", width=3, takefocus=False,
                   command=lambda: self._pv_dock_scale_to(+1)).pack(side="right")
        ttk.Button(pv_tools, text="-", width=3, takefocus=False,
                   command=lambda: self._pv_dock_scale_to(-1)).pack(side="right",
                                                                    padx=(0, 4))
        ttk.Label(pv_tools, text="col guide", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="right", padx=(2, 0))
        self.guide_ent = ttk.Entry(pv_tools, width=5, font=FONT_UI_SM,
                                   justify="center")
        self.guide_ent.insert(0, str(self.app._pv_col_guide))
        self.guide_ent.pack(side="right")
        self.guide_ent.bind("<KeyRelease>", self.on_guide_change)
        self.guide_ent.bind("<Return>", self.on_guide_change)

        pv_host = ttk.Frame(rep, padding=(2, 0))
        pv_host.grid(row=1, column=0, sticky="nsew", pady=(3, 0))
        pv_host.rowconfigure(0, weight=1)
        pv_host.columnconfigure(0, weight=1)
        self.prev_txt = tk.Text(pv_host, wrap="char", font=FONT_MONO,
                                bg=_theme.BG_EDIT, fg=_theme.FG_MAIN, relief="flat",
                                insertbackground="#fff", borderwidth=0,
                                padx=2, pady=2)
        self.prev_txt.grid(row=0, column=0, sticky="nsew")
        pvs = ttk.Scrollbar(pv_host, orient="vertical",
                            command=self.prev_txt.yview)
        pvs.grid(row=0, column=1, sticky="ns")
        self.prev_txt.configure(yscrollcommand=pvs.set)
        self.dyn_cv = tk.Canvas(pv_host, highlightthickness=0, bg=_theme.BG_EDIT)
        self.dyn_cv.grid(row=0, column=0, sticky="nsew")
        self.dyn_vs = ttk.Scrollbar(pv_host, orient="vertical",
                                    command=self.dyn_cv.yview)
        self.dyn_hs = ttk.Scrollbar(pv_host, orient="horizontal",
                                    command=self.dyn_cv.xview)
        self.dyn_cv.configure(yscrollcommand=self.dyn_vs.set,
                              xscrollcommand=self.dyn_hs.set)
        self.dyn_vs.grid(row=0, column=2, sticky="ns")
        self.dyn_hs.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.dyn_vs.grid_remove()
        self.dyn_hs.grid_remove()
        pv_host.rowconfigure(1, weight=0)
        self.pv_guide = tk.Canvas(pv_host, highlightthickness=0, bg=_theme.BG_EDIT)
        self.dyn_cv.grid_remove()
        pv_host.bind("<Configure>", self._refresh_pv_guide)
        self._refresh_pv_guide()

        # Tokens info box and Note field intentionally removed from the UI.
        # l_tokens and note_ent are kept as hidden/detached widgets for compat.
        tok_lab = ttk.LabelFrame(f, text="Tokens", padding=(3, 1))
        self.l_tokens = tk.Text(tok_lab, height=2, wrap="word",
                                font=FONT_UI_SM, background="#f4f6fa",
                                foreground="#3a3f4c", relief="flat",
                                highlightthickness=0, borderwidth=0)
        self.l_tokens.configure(state="disabled")
        self.note_ent = ttk.Entry(f, font=FONT_UI_SM)
        self.note_ent.bind("<KeyRelease>", self.on_note_change)
        # (neither tok_lab nor note_ent is gridded, so they are invisible)

        self.edit_dock = f

    # -- filtering / table --------------------------------------------------
    def _scope_haystack(self, e):
        return self.app._scope_haystack(e, self.scope_cb.get())

    def _passes(self, i):
        sec, e = self.pack.flat[i]
        if self.filter_section != "All" and sec != self.filter_section:
            return False
        tr = e.get("translation", "")
        st = self.filter_status
        if st == "Untranslated" and tr:
            return False
        if st == "Translated" and not tr:
            return False
        if st in ("Won't fit", "Grows (free space)"):
            want = "over" if st == "Won't fit" else "grows"
            b, _ = parse_text(tr)
            if not tr or space_verdict(sec, e, b) != want:
                return False
        if st == "Overdraw (source)" and \
                not self.app.row_overdraw(i, e.get("source", ""))[1]:
            return False
        if st == "Overdraw (translation)" and \
                not (tr and self.app.row_overdraw(i, tr)[1]):
            return False
        if st == "Has non-ASCII" and not any(
                kind == "nonascii" for _, _, kind in parse_text(tr)[1]):
            return False
        if self.filter_text and self.filter_text.lower() not in \
                self._scope_haystack(e).lower():
            return False
        return True

    def _sort_key(self, i):
        sec, e = self.pack.flat[i]
        col = self._sort_col
        if col == "ord":
            return i
        if col == "st":
            return ""
        if col == "note":
            return "0" if e.get("notes") else "1"
        if col == "sec":
            return sec
        if col == "key":
            return e.get("key", "")
        if col == "context":
            return e.get("context", "")
        if col == "source":
            return e.get("source", "")
        if col == "tr":
            return e.get("translation", "")
        if col == "bytes":
            return parse_text(e.get("translation", ""))[0]
        return i

    def sort_by(self, col):
        if self._sort_col != col:
            self._sort_col, self._sort_rev = col, False
        elif not self._sort_rev:
            self._sort_rev = True
        else:
            self._sort_col, self._sort_rev = None, False
        self.rebuild_view()

    def rebuild_view(self):
        self._view_gen += 1
        gen = self._view_gen
        if self._insert_job is not None:
            try:
                self.win.after_cancel(self._insert_job)
            except tk.TclError:
                pass
            self._insert_job = None
        self.filter_section = self.sec_cb.get() or "All"
        self.filter_status = self.st_cb.get() or "All"
        self._find_hits = None
        idxs = [i for i in range(len(self.pack.flat)) if self._passes(i)]
        if self._sort_col:
            idxs = sorted(idxs, key=self._sort_key, reverse=self._sort_rev)
        old_count = len(self._pos_iids)
        self.view = idxs
        self.view_iid = {}
        self._iid_by_flat = {}
        self._pos_iids = []
        self._band_of = {}
        self._band_state = {"unit": None, "n": 0}
        self._band_map = self.app.box_map()
        self.cellsel.clear()
        if max(old_count, len(self.view)) > 2000 and not getattr(
                self, "_bulk_hidden", False):
            self.tree.grid_remove()
            self._bulk_hidden = True
        self.tree.delete(*self.tree.get_children())
        self.nav_lab.configure(text="%d shown" % len(self.view))
        self._insert_rows(0, gen)

    def _insert_rows(self, start, gen):
        """Yield to Tk between short insertion batches in large views."""
        if gen != self._view_gen or not self.win.winfo_exists():
            return
        self._insert_job = None
        deadline = perf_counter() + 0.008
        end = min(start + 256, len(self.view))
        i = start
        while i < end:
            self._insert_row(self.view[i])
            i += 1
            if perf_counter() >= deadline:
                break
        if i < len(self.view):
            self._insert_job = self.win.after(1, self._insert_rows, i, gen)
        else:
            if getattr(self, "_bulk_hidden", False):
                self._bulk_hidden = False
                self.tree.grid()
            if self.current >= 0:
                self.refresh_row(self.current)

    def _band_for(self, i):
        row = self._band_map.get(i)
        unit = row[0] if row is not None else i
        st = self._band_state
        if st["unit"] != unit:
            st["unit"] = unit
            st["n"] += 1
        return "band_a" if st["n"] % 2 else "band_b"

    def _row_tags(self, tag, over, band):
        tags = []
        if tag:
            tags.append(tag)
        if "s" in over:
            tags.append("over_src")
        if "t" in over:
            tags.append("over_tr")
        if band:
            tags.append(band)
        return tuple(tags)

    def _state(self, i):
        return self.app._row_state(i)

    def _alt_dbl(self, evt):
        iid = self.tree.identify_row(evt.y)
        i = self.view_iid.get(iid) if iid else None
        if i is not None:
            self.app.open_notes_dashboard(i)
        return "break"

    def _iid_of(self, i):
        """The row id for flat index `i` in *this* window, or None when the
        current filter hides it.  Same contract as App._iid_of so callers can
        treat the two alike."""
        return self._iid_by_flat.get(i)

    def _insert_row(self, i):
        _sec, e = self.pack.flat[i]
        mark, tag, b, budget, tr, over = self._state(i)
        band = self._band_for(i)
        iid = self.tree.insert("", "end", values=(
            i + 1, mark, "✎" if e.get("notes") else "", _sec,
            e.get("key", ""), e.get("context", ""),
            e.get("source", ""), tr, "%d/%d" % (b, budget)),
            tags=self._row_tags(tag, over, band))
        self._band_of[iid] = band
        self.view_iid[iid] = i
        self._iid_by_flat[i] = iid
        self._pos_iids.append(iid)
        return iid

    def refresh_row(self, i):
        """Repaint one row in this window from the pack."""
        iid = self._iid_by_flat.get(i)
        if iid is None:
            return
        mark, tag, b, budget, tr, over = self._state(i)
        self.tree.item(iid, tags=self._row_tags(tag, over,
                                                self._band_of.get(iid)))
        self.tree.set(iid, "st", mark)
        self.tree.set(iid, "note", "✎" if self.pack.flat[i][1].get(
            "notes") else "")
        self.tree.set(iid, "tr", tr)
        self.tree.set(iid, "bytes", "%d/%d" % (b, budget))
        if i == self.current:
            self._load_editor()

    # -- live sync ----------------------------------------------------------
    def external_row_changed(self, i):
        """Another window changed row `i`.  Never called while this window is
        the one typing, which is what keeps the caret from jumping."""
        if self._editing or self._loading:
            return
        self.refresh_row(i)

    # -- selection ----------------------------------------------------------
    def select(self, i, see=True):
        if not (0 <= i < len(self.pack.flat)):
            return
        self.current = i
        self._load_editor()
        iid = self._iid_by_flat.get(i)
        if iid is None:
            self.filter_section = "All"
            self.filter_status = "All"
            self.sec_cb.current(0)
            self.st_cb.current(0)
            self.filter_text = ""
            self.rebuild_view()
            iid = self._iid_by_flat.get(i)
        if iid is None:
            return
        self._select_lock = True
        try:
            self.tree.selection_set(iid)
            if see:
                self.tree.see(iid)
        finally:
            self._select_lock = False

    def on_select(self, _evt=None):
        if self._select_lock:
            return
        sel = self.tree.selection()
        if not sel:
            return
        i = self.view_iid.get(sel[0])
        if i is not None and i != self.current:
            self.current = i
            self._load_editor()

    def on_rowkey(self, evt):
        if not self.view:
            return
        pos = self._view_pos()
        step = 1
        if evt.keysym == "Down":
            target = pos + step
        elif evt.keysym == "Up":
            target = pos - step
        elif evt.keysym == "Next":
            target = pos + 10
        else:
            target = pos - 10
        if pos < 0:
            target = 0 if target >= 0 else len(self.view) - 1
        target = max(0, min(target, len(self.view) - 1))
        self.select(self.view[target])
        return "break"

    def _view_pos(self):
        iid = self._iid_by_flat.get(self.current)
        if iid is None:
            return -1
        try:
            return self.view.index(self.current)
        except ValueError:
            return -1

    # -- editor -------------------------------------------------------------
    def _load_editor(self):
        if not (0 <= self.current < len(self.pack.flat)):
            return
        self._loading = True
        try:
            sec, e = self.pack.flat[self.current]
            self.l_sec.configure(text=sec)
            self.l_key.configure(text=e.get("key", ""))
            sb, _ = parse_text(e.get("source", ""))
            budget = int(e.get("budget", sb))
            self.l_budget.configure(text="budget %d B (%s)" % (
                budget, KIND_LABEL[room_kind(sec, e.get("key", ""))]))
            self.l_src_bytes.configure(text="src %d B" % sb)
            tr = e.get("translation", "")
            tb, _ = parse_text(tr)
            self.l_tr_bytes.configure(text="tr %d B" % tb)
            self.l_status.configure(text=edited_on(e) or "not edited")
            self.src_txt.configure(state="normal")
            self.src_txt.delete("1.0", "end")
            self.src_txt.insert("1.0", e.get("source", ""))
            self.src_txt.configure(state="disabled")
            self._load_mapped()
        finally:
            self._loading = False
        self._update_status()

    def _load_mapped(self):
        """Unified editor on this window's own box: `app.box_rows` when the
        app's checkbox is on, its own table selection otherwise, one line per
        row.  Rebuilt through the shared `App._load_ed_rows` so the mapping,
        retags and write-back live in one place."""
        self.tr_single.grid()
        self.tr_multi.grid_remove()
        if self._line_ed_map:
            for w_ in list(self._line_ed_map.values()):
                w_.destroy()
            self._line_ed_map = {}
            self._line_hdr_map = {}
        rows = self.app._ed_rows_for(self.current,
                                     self._selected_flat_in_order())
        self.app._load_ed_rows(self.tr_txt, rows, self.current)

    def sync_cells(self, idxs):
        """Rows this window is not editing changed underneath it (an undo or a
        redo in another window, a paste there).  Repaint the table rows and
        any editor showing one of them.

        The mapped box is rebuilt through the shared loader whenever a shown
        row changed; rows this window itself just typed never reach here
        (the change is guarded by `_editing`, which is what keeps the caret)."""
        flat = getattr(self.tr_txt, "_ed_flat", [])
        touched = [i for i in idxs if 0 <= i < len(self.pack.flat)]
        for i in touched:
            iid = self._iid_by_flat.get(i)
            if iid is not None:
                self.refresh_row(i)
        if any(i == self.current or i in flat for i in touched):
            self._load_mapped()
            self._update_status()

    def _set_editor_text(self, w, text):
        """Replace an editor's content without it reporting an edit back."""
        keep = self._editing
        self._editing = True
        try:
            w.delete("1.0", "end")
            w.insert("1.0", text)
            w._tag_content = None
            w.edit_modified(False)
            w.edit_reset()
        finally:
            self._editing = keep

    def on_tr_return(self, evt=None):
        """Enter inserts the game's line break, into whichever editor fired.

        The view cannot use App.on_tr_return, which writes to the main window's
        editor - with two windows open that would put the bar in the wrong
        place."""
        w = getattr(evt, "widget", None) or self.tr_txt
        w.insert("insert", "|")
        return "break"

    def on_tr_modified(self, _evt=None):
        """An editor in this window changed.  Write through to the pack, then
        let the main window (and any other view) repaint."""
        w = self.tr_txt
        if not w.edit_modified():
            return
        w.edit_modified(False)
        if self._loading or self._editing or getattr(w, "_sealing", False):
            return
        self._editing = True
        try:
            self.app._tr_modified_common(w)
            self.app._bytes_label()
            self.app.schedule_preview()
            self._update_status()
        finally:
            self._editing = False

    # -- row clipboard (shared with the main window) ------------------------
    def _selected_flat_in_order(self):
        """Selected flat indices in file order, not click order."""
        sel = set(self.tree.selection())
        return sorted(self.view_iid[iid] for iid in sel if iid in self.view_iid)

    def on_copy(self, _evt=None):
        idxs = self._selected_flat_in_order()
        if not idxs:
            return
        vals = [self.pack.flat[i][1].get("translation", "") for i in idxs]
        # the App owns the buffer, so a copy here pastes in the main window
        self.app._row_clip = vals
        if self.cellsel.active():
            self.cellsel.copy()
            self._update_status()
            return "break"
        self.win.clipboard_clear()
        self.win.clipboard_append("\n".join(vals))
        self._update_status()
        return "break"

    def on_paste(self, _evt=None):
        idxs = self._selected_flat_in_order()
        vals = getattr(self.app, "_row_clip", None)
        if not idxs or not vals:
            return
        self._editing = True
        cells = []
        try:
            for k, i in enumerate(idxs):
                val = vals[k % len(vals)]
                _sec, e = self.pack.flat[i]
                if e.get("translation", "") == val:
                    continue
                cells.append((i, e.get("translation", ""), val))
                e["translation"] = val
                self.app._own(e)
                self.app.dirty = True
            self.app.note_edit("Paste", cells)
            self.app._find_hits = None
            for i in idxs:
                iid = self.app._iid_of(i)
                if iid is not None:
                    self.app.update_tree_row(iid, i)
            self._load_mapped()
            self.app.update_preview()
            self.app.update_status()
            self._update_status()
        finally:
            self._editing = False
        return "break"

    def on_delete(self, _evt=None):
        idxs = self._selected_flat_in_order()
        if not idxs:
            return
        self._editing = True
        cells = []
        try:
            for i in idxs:
                e = self.pack.flat[i][1]
                if not e.get("translation", ""):
                    continue
                cells.append((i, e.get("translation", ""), ""))
                e["translation"] = ""
                self.app._own(e)
                self.app.dirty = True
                iid = self.app._iid_of(i)
                if iid is not None:
                    self.app.update_tree_row(iid, i)
            self.app.note_edit("Clear", cells)
            self.app._find_hits = None
            self._load_editor()
            self.app.update_preview()
            self.app.update_status()
            self._update_status()
        finally:
            self._editing = False
        return "break"

    # -- find ---------------------------------------------------------------
    def _on_scope(self, _evt=None):
        self._find_hits = None
        self.filter_text = self.search_ent.get().strip()
        self.rebuild_view()

    def find_matches(self, q):
        q = q.strip().lower()
        if not q:
            return []
        if self._find_hits is None or self._find_hits[0] != q:
            self._find_hits = (q, [
                i for i, (_s, e) in enumerate(self.pack.flat)
                if q in self._scope_haystack(e).lower()])
        return self._find_hits[1]

    def find_step(self, d=1):
        q = self.search_ent.get().strip()
        if not q:
            self.find_lab.configure(text="")
            return
        hits = self.find_matches(q)
        if not hits:
            self.find_lab.configure(text="no match", foreground=_theme.TH_BAD)
            return
        nxt = None
        for i in hits:
            if (d > 0 and i > self.current) or (d < 0 and i < self.current):
                nxt = i
                break
        if nxt is None:
            nxt = hits[0] if d > 0 else hits[-1]
        self.select(nxt)
        self.find_lab.configure(
            text="%d found - %d of %d" % (len(hits), hits.index(nxt) + 1,
                                          len(hits)),
            foreground=_theme.TH_OK if len(hits) > 1 else _theme.TH_WARN)

    # -- macros -------------------------------------------------------------
    def _bind_macros(self):
        # read the App's map every time, so a macro the user edits later
        # reaches this window too instead of a stale copy taken at open time
        for w in [self.tr_txt] + list(self._line_ed_map.values()):
            for key, tok in (self.app.macros or {}).items():
                if not key.startswith("F") or not tok:
                    continue
                try:
                    w.bind("<%s>" % key,
                           lambda e, t=tok: self._run_macro(t, e.widget, e))
                except tk.TclError:
                    pass

    def _run_macro(self, tok, w, evt=None):
        if not _macro_key_ok(evt):
            return "break"
        try:
            w.insert("insert", tok)
            w.edit_modified(True)
        except tk.TclError:
            return "break"
        return "break"

    # -- misc ---------------------------------------------------------------
    def _update_status(self):
        n = len(self.tree.selection())
        bits = ["%d shown" % len(self.view),
                "no selection" if not n else
                ("1 selected" if n == 1 else "%d selected" % n)]
        if 0 <= self.current < len(self.pack.flat):
            bits.append("row %d/%d" % (self.current + 1, len(self.pack.flat)))
            bits.append("edited %s" % (edited_on(self.pack.flat[self.current][1])
                                       or "-"))
        try:
            self.l_status.configure(text="   ".join(bits))
        except tk.TclError:
            pass

    def set_dirty_label(self):
        self._update_status()

    def apply_theme(self):
        """Re-skin this window after the main window switched themes."""
        self.app.apply_theme()
        self.app.apply_tree_tags()
        for w in [self.src_txt, self.tr_txt] + list(self._line_ed_map.values()):
            self.app.configure_text_tags(w)
        self.rebuild_view()
        if self.current >= 0:
            self._load_editor()

    def close(self):
        self._view_gen += 1
        if self._insert_job is not None:
            try:
                self.win.after_cancel(self._insert_job)
            except tk.TclError:
                pass
            self._insert_job = None
        app = self.app
        try:
            app._views.remove(self)
        except ValueError:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        app._refresh_views_menu()
        app.update_status()

    # -- delegation to app for ViewWindow's editor dock ----------------------
    def copy_key(self):
        return self.app.copy_key()

    def copy_context(self):
        return self.app.copy_context()

    def insert_token(self, tok):
        return self.app.insert_token(tok)

    def _tok_more_menu(self):
        return self.app._tok_more_menu()

    def _relayout_tokens(self, _e=None):
        return self.app._relayout_tokens(_e)

    def _tok_layout_now(self):
        return self.app._tok_layout_now()

    def _rebuild_tok_menu(self, shown):
        return self.app._rebuild_tok_menu(shown)

    def _toggle_dynamic(self):
        return self.app._toggle_dynamic()

    def _toggle_dyn_size(self):
        return self.app._toggle_dyn_size()

    def _pv_dock_scale_to(self, delta):
        return self.app._pv_dock_scale_to(delta)

    def _draw_dyn_preview(self):
        return self.app._draw_dyn_preview()

    def _on_dyn_resize(self, event=None):
        return self.app._on_dyn_resize(event)

    def _run_dyn_resize(self):
        return self.app._run_dyn_resize()

    def _refresh_pv_guide(self, event=None):
        return self.app._refresh_pv_guide(event)

    def on_guide_change(self, _evt=None):
        return self.app.on_guide_change(_evt)

    def on_note_change(self, _evt=None):
        return self.app.on_note_change(_evt)

    def next_empty(self):
        return self.app.next_empty()

    def next_clone(self, d=1):
        return self.app.next_clone(d)

    def copy_source_to_tr(self):
        return self.app.copy_source_to_tr()

    def clear_translation(self):
        return self.app.clear_translation()

    def on_multi_toggle(self):
        return self.app.on_multi_toggle()
