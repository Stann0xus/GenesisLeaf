"""The detachable Float preview window.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from genesisleaf.core.dialog import limit_for
from genesisleaf.ui.canvas_render import reposition_canvas_preview
from genesisleaf.ui.fonts import FONT_UI_SM, JP_FONT_CANDIDATES
from genesisleaf.ui import theme as _theme


class FloatPreviewMixin:
    """The detachable Float preview window.

    Mixed into `App`; `self` is the main window.
    """

    # -- dual view: the floating preview window ---------------------------
    # Two real preview contexts stacked in one window: SOURCE above
    # TRANSLATION.  Both render through the same pipeline as the dock
    # preview (render_text_to_canvas), so every setting - real font, dynamic
    # rows, accent font, scale - applies here live.  Characters the retail
    # atlas cannot draw (Japanese, mainly) fall back per character to a
    # Japanese-capable system font; Latin text keeps the real glyphs.
    def open_float_preview(self):
        if getattr(self, "pv_fwin", None) is None \
                or not self.pv_fwin.winfo_exists():
            self._build_float_preview()
        self.pv_fwin.deiconify()
        self.pv_fwin.lift()
        self.pv_fwin.focus_force()
        self._draw_float_preview()

    def _pv_context(self, win, label):
        """One preview context: a caption and a scrollable canvas."""
        f = ttk.Frame(win)
        ttk.Label(f, text=label, font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(anchor="w", padx=2,
                                               pady=(0, 1))
        host = ttk.Frame(f)
        host.pack(fill="both", expand=True)
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        cv = tk.Canvas(host, highlightthickness=0, bg=_theme.BG_EDIT)
        vs = ttk.Scrollbar(host, orient="vertical", command=cv.yview)
        hs = ttk.Scrollbar(host, orient="horizontal", command=cv.xview)
        cv.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        cv.bind("<Configure>", lambda _e: reposition_canvas_preview(cv))
        cv.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        return f, cv

    def _build_float_preview(self):
        win = tk.Toplevel(self.root)
        win.title("Dual view - source + translation")
        win.geometry("900x760")
        win.transient(self.root)
        win.minsize(420, 320)
        def hide():
            self.preview_queue.cancel(self.pv_fcv_src)
            self.preview_queue.cancel(self.pv_fcv_tr)
            win.withdraw()
        win.protocol("WM_DELETE_WINDOW", hide)
        self.pv_fwin = win
        self.pv_fscale = getattr(self, "pv_fscale", 2)

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=4, pady=(4, 2))
        ttk.Label(bar, text="Scale", font=FONT_UI_SM).pack(side="left")
        ttk.Button(bar, text="-", width=3, takefocus=False,
                   command=lambda: self._pv_fscale_to(-1)).pack(
            side="left", padx=(4, 0))
        self.pv_flab = ttk.Label(bar, text="%dx" % self.pv_fscale, width=5,
                                 font=FONT_UI_SM, anchor="center")
        self.pv_flab.pack(side="left")
        ttk.Button(bar, text="+", width=3, takefocus=False,
                   command=lambda: self._pv_fscale_to(+1)).pack(side="left")

        self.f_show_src = tk.BooleanVar(value=True)
        self.f_show_tr = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Show Source", variable=self.f_show_src,
                        command=self._refresh_float_panes).pack(side="left", padx=(16, 4))
        ttk.Checkbutton(bar, text="Show Translation", variable=self.f_show_tr,
                        command=self._refresh_float_panes).pack(side="left")

        ttk.Label(bar, text="Japanese font (only for characters the game "
                            "atlas cannot draw):",
                  font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED).pack(
            side="right", padx=(0, 6))
        installed = set(tkfont.families())
        fams = [f for f in JP_FONT_CANDIDATES if f in installed]
        cur = getattr(self, "jp_family", None) or "MS Gothic"
        if cur not in fams:
            fams.insert(0, cur)
        self.jp_cb = ttk.Combobox(bar, state="readonly", width=18,
                                  font=FONT_UI_SM, values=fams)
        self.jp_cb.set(cur)
        self.jp_cb.pack(side="right")
        self.jp_cb.bind("<<ComboboxSelected>>", self._on_jp_font)

        self.pv_fpanes = ttk.Panedwindow(win, orient="vertical")
        self.pv_fpanes.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.src_pane, self.pv_fcv_src = self._pv_context(
            self.pv_fpanes, "SOURCE - real preview (CJK falls back to the system font)")
        self.tr_pane, self.pv_fcv_tr = self._pv_context(
            self.pv_fpanes, "TRANSLATION - real preview")
        self._refresh_float_panes()

    def _refresh_float_panes(self):
        try:
            self.pv_fpanes.forget(self.src_pane)
            self.pv_fpanes.forget(self.tr_pane)
        except tk.TclError:
            pass
        if self.f_show_src.get():
            self.pv_fpanes.add(self.src_pane, weight=1)
        if self.f_show_tr.get():
            self.pv_fpanes.add(self.tr_pane, weight=1)

    def _pv_fscale_to(self, delta):
        self.pv_fscale = max(1, min(8, self.pv_fscale + delta))
        self.pv_flab.configure(text="%dx" % self.pv_fscale)
        self._draw_float_preview()

    def _on_jp_font(self, _evt=None):
        fam = self.jp_cb.get()
        if not fam:
            return
        self.jp_family = fam
        self._jp_fonts.clear()
        self.persist_settings()
        self._draw_float_preview()

    def _draw_float_preview(self):
        src = getattr(self, "pv_fcv_src", None)
        tr = getattr(self, "pv_fcv_tr", None)
        if src is None or tr is None:
            return
        if not (src.winfo_exists() and tr.winfo_exists()):
            return
        if self.pv_fwin.state() != "normal":
            return
        if self.pack is None or self.current < 0:
            self.preview_queue.cancel(src)
            self.preview_queue.cancel(tr)
            src.delete("all")
            tr.delete("all")
            return
        sec = self.pack.flat[self.current][0]
        ctx = self._dock_limit_context(sec)
        lim = limit_for(ctx) if ctx else None
        meta = {}
        if lim:
            meta["limit"] = lim["context"]
            meta["glyph_pad"] = lim["glyph_pad"]
        # fixed row positions for box rows, like the dock preview, so an
        # overruning '|' shows the in-game overlap
        row_positions = None
        if self.multi_var.get() and sec in ("scene_dialog", "inline_text"):
            flat = getattr(self.tr_txt, "_ed_flat", [])
            if len(flat) > 1:
                bmap = self.box_map()
                row_positions = [bmap.get(i, (0, 0))[1] for i in flat]
        scale = getattr(self, "pv_fscale", 2)
        jp = self.jp_font(scale)
        accent = self.accent_font_var.get()
        expander = self.markup_expander()
        for cv, rows in ((src, self._editor_source_rows()),
                         (tr, self._editor_preview_rows())):
            pos = row_positions
            if pos is not None and len(pos) != len(rows):
                pos = None
            try:
                self.preview_queue.request(
                    cv, rows, meta, expander=expander, scale=scale,
                    row_positions=pos, accent_font=accent,
                    fallback_font=jp,
                    rf_config=getattr(self, "rf_config", None))
            except Exception:
                pass
