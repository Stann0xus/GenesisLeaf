"""Builds the bottom editor dock: identity row, source/translation, tokens, preview panel.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.ui.fonts import FONT_MONO, FONT_UI_B, FONT_UI_SM
from genesisleaf.ui.widgets import ToolTip
from genesisleaf.ui import theme as _theme


class EditorDockMixin:
    """Builds the bottom editor dock: identity row, source/translation, tokens, preview panel.

    Mixed into `App`; `self` is the main window.
    """

    # -- editor dock (always visible at the window bottom) -------------------
    def _build_editor_dock(self, pv):
        """The bottom half: entry identity, the editor, the preview, the note.

        The editor and the preview sit either side of a *draggable* horizontal
        splitter, so their split can be moulded with the mouse instead of being
        fixed at a ratio.  Each side also has a sane default height and a
        minimum, and both expand with the window, so the whole dock stays
        usable from the 800x600 minimum up to a maximised screen."""
        f = ttk.Frame(pv, padding=(6, 4, 6, 4))
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)

        # identity: section chip, key, selection count | byte-budget meter
        r0 = ttk.Frame(f)
        r0.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.l_sec = ttk.Label(r0, text="-", font=FONT_UI_SM, padding=(6, 1),
                               style="Chip.TLabel")
        self.l_sec.pack(side="left")
        self.l_key = ttk.Label(r0, text="no entry selected", font=FONT_UI_B)
        self.l_key.pack(side="left", padx=(8, 4))
        self.b_copy_key = ttk.Button(r0, text="Copy", width=6,
                                     command=self.copy_key, takefocus=False)
        self.b_copy_key.pack(side="left")
        ToolTip(self.b_copy_key, "Copy the key", delay=700)
        self.l_selcount = ttk.Label(r0, text="", font=FONT_UI_SM,
                                    foreground=_theme.TH_FG_MUTED)
        self.l_selcount.pack(side="left", padx=(8, 0))
        # bytes used vs the key's budget, as a bar coloured by state
        self.l_budget = ttk.Label(r0, text="", font=FONT_UI_SM)
        self.l_budget.pack(side="right")
        self.budget_bar = ttk.Progressbar(r0, mode="determinate", maximum=100,
                                          length=150,
                                          style="BudgetOk.Horizontal.TProgressbar")
        self.budget_bar.pack(side="right", padx=(10, 6))
        self.l_src_bytes = ttk.Label(r0, text="", font=FONT_UI_SM,
                                     foreground=_theme.TH_FG_MUTED)
        self.l_src_bytes.pack(side="right")

        r1 = ttk.Frame(f)
        r1.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        ttk.Label(r1, text="Context", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left")
        self.e_context = ttk.Entry(r1, font=FONT_UI_SM, state="readonly")
        self.e_context.pack(side="left", fill="x", expand=True, padx=(6, 2))
        self.b_copy_ctx = ttk.Button(r1, text="Copy", width=6,
                                     command=self.copy_context, takefocus=False)
        self.b_copy_ctx.pack(side="left")
        ToolTip(self.b_copy_ctx, "Copy the context", delay=700)

        # ---- the draggable editor / preview split ---------------------------
        # Left = source + translation + tokens + actions, right = the preview
        # panel (real-font canvas or approx text, plus the token legend).
        hp = ttk.Panedwindow(f, orient="horizontal")
        hp.grid(row=2, column=0, sticky="nsew", pady=(4, 0))

        leftp = ttk.Frame(hp, padding=(0, 0, 6, 0))
        leftp.rowconfigure(1, weight=1)
        leftp.rowconfigure(3, weight=2)
        leftp.columnconfigure(0, weight=1)

        rep = ttk.Frame(hp, padding=(6, 0, 0, 0))
        rep.rowconfigure(2, weight=1)
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
        # the byte counts now live in the meter beside the key; this label is
        # kept (unpacked) because other code still writes to it
        self.l_tr_bytes = ttk.Label(lab, text="", font=FONT_UI_SM)
        self.l_status = ttk.Label(lab, text="", font=FONT_UI_SM)
        self.l_status.pack(side="left", padx=(10, 0))
        # transient confirmations ("Undo: Paste (1 line)") that must not be
        # wiped by the next status refresh, so they get their own label
        self.l_flash = ttk.Label(lab, text="", font=FONT_UI_SM,
                                 foreground=_theme.TH_ACCENT)
        self.l_flash.pack(side="left", padx=(10, 0))
        self._flash_job = None
        self.multi_cb = ttk.Checkbutton(lab, text="Box rows",
                                        variable=self.multi_var,
                                        command=self._on_multi_toggle,
                                        takefocus=False)
        self.multi_cb.pack(side="right")
        self.b_clear_tr = ttk.Button(lab, text="Clear", width=6,
                                     takefocus=False,
                                     command=self.clear_translation)
        self.b_clear_tr.pack(side="right", padx=(0, 8))
        ToolTip(self.b_clear_tr, "Empty the translation of this row / box",
                delay=700)
        self.b_copy_src = ttk.Button(lab, text="Copy source", takefocus=False,
                                     command=self.copy_source_to_tr)
        self.b_copy_src.pack(side="right", padx=(0, 4))
        ToolTip(self.b_copy_src, "Start from the source text", delay=700)

        tr_inner = ttk.Frame(leftp)
        tr_inner.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
        tr_inner.rowconfigure(1, weight=1)
        tr_inner.columnconfigure(0, weight=1)

        # One-line strip above the box summarising each mapped row's key and
        # status; blank while the classic single-row editor is showing.
        self.l_ed_summary = ttk.Label(tr_inner, text="", font=FONT_UI_SM,
                                      foreground=_theme.TH_FG_MUTED, anchor="w")
        self.l_ed_summary.grid(row=0, column=0, sticky="ew")

        # Single translation box.  One line per row when the current entry is
        # a multi-row dialog box (or, unchecked, follows the table selection);
        # a lone row keeps the classic editor.
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
        self._bind_editor_keys(self.tr_txt)

        self.tr_multi = ttk.Frame(tr_inner)
        self.tr_multi.grid(row=1, column=0, sticky="nsew")
        self.tr_multi.columnconfigure(0, weight=1)
        self.tr_multi.grid_remove()
        self._line_ed_map = {}
        self._line_hdr_map = {}

        # Insert-token buttons, responsive: they shrink and then spill into a
        # "More" menu as the window / preview split narrows.  Buttons live in
        # their own frame gridded with one column each, so grid_remove/grid
        # hides and restores them without ever changing the left-to-right
        # order that pack would shuffle when a middle button came back.
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
            b = ttk.Button(self._tok_cells, text=t, width=0, takefocus=False,
                           command=lambda s=t: self.insert_token(s))
            b.grid(row=0, column=k, padx=1)
            ToolTip(b, f"Insert token {t}", delay=2000)
            self._tok_btns.append(b)
        self._tok_more = ttk.Button(
            self._tok_cells, text="More \u25be", width=0, takefocus=False,
            command=self._tok_more_menu)
        self._tok_more.grid(row=0, column=len(tokens), padx=2)
        self._tok_more.grid_remove()
        self._tok_menu = tk.Menu(self.root, tearoff=0)
        self._tok_compact = False
        self._tok_job = None
        self._tok_sizes = None          # per-index reqwidth at width=0
        self._tok_sizes_c = None        # not used, kept for compat
        self._tok_hint = ttk.Label(
            tok_row, text="Enter = '|' newline    Ctrl+Enter = '|' (box) / real newline (single)",
            font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED)
        self._tok_hint.pack(side="right")
        tok_row.bind("<Configure>", self._relayout_tokens)
        self.root.after_idle(self._tok_layout_now)

        # ---- right column: preview panel ------------------------------------
        pv_tools = ttk.Frame(rep)
        pv_tools.grid(row=0, column=0, sticky="ew")
        ttk.Label(pv_tools, text="Preview", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left")
        self.b_dyn = ttk.Checkbutton(pv_tools, text="Real font",
                                     variable=self.dyn_var,
                                     command=self._toggle_dynamic)
        self.b_dyn.pack(side="left", padx=(8, 0))
        self.b_dyn_size = ttk.Checkbutton(pv_tools, text="Dynamic",
                                          variable=self.dyn_size_var,
                                          command=self._toggle_dyn_size)
        self.b_dyn_size.pack(side="left", padx=(2, 0))
        self.b_accent_font = ttk.Checkbutton(pv_tools, text="Accent font",
                                             variable=self.accent_font_var,
                                             command=self._toggle_accent_font)
        self.b_accent_font.pack(side="left", padx=(2, 0))
        ttk.Button(pv_tools, text="Float",
                   command=self.open_float_preview,
                   takefocus=False).pack(side="left", padx=(10, 0))
        # second row: the size/scale tools of whichever preview is showing
        pv_tools2 = ttk.Frame(rep)
        pv_tools2.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.f_real_tools = ttk.Frame(pv_tools2)
        self.f_norm_tools = ttk.Frame(pv_tools2)

        # Normal font tools
        ttk.Label(self.f_norm_tools, text="Size", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left", padx=(4, 2))
        self.pv_size_cb = ttk.Combobox(self.f_norm_tools, state="readonly", width=3,
                                       font=FONT_UI_SM, values=["8", "10", "12", "14", "16", "18", "24", "32"])
        self.pv_size_cb.current(2)  # default 12
        self.pv_size_cb.pack(side="left")
        self.pv_size_cb.bind("<<ComboboxSelected>>", self._on_pv_size_change)

        # Real font tools
        ttk.Label(self.f_real_tools, text="scale", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left", padx=(2, 0))
        self.l_pv_scale = ttk.Label(self.f_real_tools, text="2x", width=3,
                                    font=FONT_UI_SM, anchor="center")
        self.l_pv_scale.pack(side="left")
        ttk.Button(self.f_real_tools, text="-", width=3, takefocus=False,
                   command=lambda: self._pv_dock_scale_to(-1)).pack(side="left")
        ttk.Button(self.f_real_tools, text="+", width=3, takefocus=False,
                   command=lambda: self._pv_dock_scale_to(+1)).pack(side="left", padx=(0, 4))

        ttk.Label(self.f_real_tools, text="col guide", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(side="left", padx=(8, 2))
        self.guide_ent = ttk.Entry(self.f_real_tools, width=5, font=FONT_UI_SM,
                                   justify="center")
        self.guide_ent.insert(0, str(self._pv_col_guide))
        self.guide_ent.pack(side="left")
        self.guide_ent.bind("<KeyRelease>", self.on_guide_change)
        self.guide_ent.bind("<Return>", self.on_guide_change)
        self.guide_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.f_real_tools, text="Guide", variable=self.guide_var,
                        command=self._refresh_pv_guide,
                        takefocus=False).pack(side="left")
                        
        ttk.Button(self.f_real_tools, text="⚙", width=2, takefocus=False,
                   command=self._open_rf_settings).pack(side="left", padx=(4, 0))

        # By default, Real Font is active so we pack real_tools
        self.f_real_tools.pack(side="left")

        pv_host = ttk.Frame(rep, padding=(2, 0))
        pv_host.grid(row=2, column=0, sticky="nsew", pady=(3, 0))
        pv_host.rowconfigure(0, weight=1)
        pv_host.columnconfigure(0, weight=1)
        self.prev_txt = tk.Text(pv_host, wrap="char", font=FONT_MONO,
                                bg=_theme.BG_EDIT, fg=_theme.FG_MAIN, relief="flat",
                                insertbackground="#fff", borderwidth=0,
                                padx=2, pady=2)
        self.prev_txt.grid(row=0, column=0, sticky="nsew")
        # the approx preview can be taller than the pane at a small window
        # height, so it gets its own scrollbar
        pvs = ttk.Scrollbar(pv_host, orient="vertical",
                            command=self.prev_txt.yview)
        pvs.grid(row=0, column=1, sticky="ns")
        self.prev_txt.configure(yscrollcommand=pvs.set)
        self.dyn_cv = tk.Canvas(pv_host, highlightthickness=0, bg=_theme.BG_EDIT)
        self.dyn_cv.grid(row=0, column=0, sticky="nsew")
        # The real-font view can outgrow the pane (multi-row selection, a
        # large scale), so it gets its own scrollbars, like the float preview.
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
        # The real-font view is rendered centred into whatever the canvas
        # currently is, so it has to be re-rendered whenever the pane is
        # resized or the splitter is dragged - otherwise the image stays at
        # the size it had when the row was selected.
        self.dyn_cv.bind("<Configure>", self._on_dyn_resize)
        # Thin guide line at the dialog-box character column (editable
        # "col guide" box, default 24). A 1px-wide canvas over that column so
        # it blends into the background and only the line itself is visible;
        # repositioned on resize. Preview text is not modified.
        self.pv_guide = tk.Canvas(pv_host, highlightthickness=0,
                                  bg=_theme.BG_EDIT)
        self.dyn_cv.grid_remove()
        pv_host.bind("<Configure>", self._refresh_pv_guide)
        self._refresh_pv_guide()

        # Tokens info box and Note field intentionally removed from the UI.
        # l_tokens and note_ent are kept as hidden/detached widgets so the
        # rest of the code that reads/writes them keeps working without changes.
        tok_lab = ttk.LabelFrame(f, text="Tokens", padding=(3, 1))
        self.l_tokens = tk.Text(tok_lab, height=2, wrap="word",
                                font=FONT_UI_SM, background="#f4f6fa",
                                foreground="#3a3f4c", relief="flat",
                                highlightthickness=0, borderwidth=0)
        self.l_tokens.configure(state="disabled")
        self.note_ent = ttk.Entry(f, font=FONT_UI_SM)
        self.note_ent.bind("<KeyRelease>", self.on_note_change)
        # (neither tok_lab nor r5/note_ent is gridded, so they are invisible)

        self.edit_dock = f
        return f
