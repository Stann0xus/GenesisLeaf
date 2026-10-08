"""Dock preview: approx chip preview, real-font canvas, guide, real-font options.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk

from genesisleaf.core.dialog import limit_for
from genesisleaf.core.encoding import C7_NAMES, TOKEN_RE, parse_text
from genesisleaf.core.legend import TOKEN_DOCS
from genesisleaf.core import palette as _palette
from genesisleaf.core.palette import CF_MAX
from genesisleaf.ui.canvas_render import (
    reposition_canvas_preview,
)
from genesisleaf.ui.fonts import FONT_MONO, pick_jp_family
from genesisleaf.ui.theme import apply_preview_scheme


class PreviewMixin:
    """Dock preview: approx chip preview, real-font canvas, guide, real-font options.

    Mixed into `App`; `self` is the main window.
    """

    def dock_box_rows(self):
        """Rows to show in the main dock's real-glyph preview: the current
        box when on a dialog line (translation if non-empty else source per
        row, box order), else the single line - mirroring the web workbench's
        previewRows()."""
        i = self.current
        if i < 0:
            return []
        rows = []
        for j in self.box_rows(i):
            _, e = self.pack.flat[j]
            t = (e.get("translation", "") or "").rstrip()
            rows.append(t if t else e.get("source", ""))
        return rows

    def _editor_preview_rows(self):
        """Rows the translation editor is showing right now, one per `_ed_flat`
        line (translation if non-empty else source per row).

        This is the same source the approx preview reads, so the real-font
        view can draw exactly what the editor maps: the current box when the
        multi-line checkbox is on, or the table selection (any number of rows)
        when it is off.  A row's own `|` breaks stay inside that row - the
        folded-in line is part of the row, never an extra row."""
        flat = getattr(self.tr_txt, "_ed_flat", [])
        if len(flat) > 1:
            rows = []
            for j in flat:
                if not (0 <= j < len(self.pack.flat)):
                    continue
                _, e = self.pack.flat[j]
                t = (e.get("translation", "") or "").rstrip()
                rows.append(t if t else e.get("source", ""))
            return rows
        return [self.tr_txt.get("1.0", "end-1c")]

    def jp_font(self, scale=1):
        """The fallback Tk font for characters the retail atlas cannot draw
        (Japanese/CJK).  MS Gothic Bold by default, the first installed
        alternative otherwise, and the user's pick from the dual-view
        combobox wins.  Size is set to 13 px * scale so CJK characters 
        match the perceptual size of the atlas glyphs.
        Bold weight matches the fill intensity of the retail glyph ink.
        Latin text never uses this - it keeps the real-glyph preview."""
        fam = getattr(self, "jp_family", None)
        if not fam:
            fam = pick_jp_family(set(tkfont.families())) or "MS Gothic"
            self.jp_family = fam
        key = (fam, max(1, int(scale)))
        fo = self._jp_fonts.get(key)
        if fo is None:
            fo = tkfont.Font(root=self.root, family=fam, weight="bold",
                             size=-max(9, int(13 * key[1])))
            self._jp_fonts[key] = fo
        return fo

    def _editor_source_rows(self):
        """The source of whatever the translation editor is mapping right
        now - the same rows `_editor_preview_rows` shows the translations
        of, so the dual view's two contexts line up line for line."""
        flat = getattr(self.tr_txt, "_ed_flat", [])
        if len(flat) > 1:
            rows = []
            for j in flat:
                if 0 <= j < len(self.pack.flat):
                    rows.append(self.pack.flat[j][1].get("source", ""))
            return rows
        if 0 <= self.current < len(self.pack.flat):
            return [self.pack.flat[self.current][1].get("source", "")]
        return []

    def _toggle_dynamic(self):
        on = self.dyn_var.get()
        if on:
            self.prev_txt.grid_remove()
            self.pv_guide.place_forget()
            self.dyn_cv.grid()
            self.dyn_vs.grid()
            self.dyn_hs.grid()
            self.f_norm_tools.pack_forget()
            self.f_real_tools.pack(side="left")
            self._draw_dyn_preview()
        else:
            self.dyn_vs.grid_remove()
            self.dyn_hs.grid_remove()
            self.dyn_cv.grid_remove()
            self.prev_txt.grid()
            self.f_real_tools.pack_forget()
            self.f_norm_tools.pack(side="left")
            self._refresh_pv_guide()
            self.update_preview()

    def _on_pv_size_change(self, _evt=None):
        try:
            sz = int(self.pv_size_cb.get())
            # Copy standard font but override size
            fo = tkfont.Font(font=self.prev_txt.cget("font"))
            fo.configure(size=sz)
            self.prev_txt.configure(font=fo)
            self._refresh_pv_guide()
        except Exception:
            pass

    def _pv_dock_scale_to(self, delta):
        """Dock real-font preview pixel scale (1..8), like the float one."""
        self.pv_scale = max(1, min(8, self.pv_scale + delta))
        self.l_pv_scale.configure(text="%dx" % self.pv_scale)
        if getattr(self, "dyn_var", None) and self.dyn_var.get():
            self._draw_dyn_preview()

    def _toggle_dyn_size(self):
        """The "Dynamic" box: the real-font view picks up the editor's rows
        (a multi-row table selection included) instead of just the current
        dialog box.  No-op next to the approx text - that one already follows
        the editor."""
        self.update_preview()

    def _toggle_accent_font(self):
        """The "Accent font" box: the real-font view renders accented characters
        by combining base letters with diacritical marks (accent font)."""
        self.update_preview()

    def _on_dyn_resize(self, event=None):
        """Re-render the real-font view after the pane is resized.

        Dragging the splitter fires a stream of <Configure> events, so the
        actual redraw is deferred by one idle pass and only runs once, after
        the drag settles.  No-op while the approx view is showing."""
        if not getattr(self, "dyn_var", None) or not self.dyn_var.get():
            return
        if getattr(self, "_dyn_resize_job", None) is not None:
            try:
                self.root.after_cancel(self._dyn_resize_job)
            except (tk.TclError, ValueError):
                pass
            self._dyn_resize_job = None
        self._dyn_resize_job = self.root.after(16, self._run_dyn_resize)

    def _run_dyn_resize(self):
        self._dyn_resize_job = None
        if getattr(self, "dyn_var", None) and self.dyn_var.get():
            if not reposition_canvas_preview(self.dyn_cv):
                self._draw_dyn_preview()
            self._refresh_pv_guide()

    def _draw_dyn_preview(self):
        cv = self.dyn_cv
        if self.current < 0:
            self.preview_queue.cancel(cv)
            cv.delete("all")
            return
        sec = self.pack.flat[self.current][0]
        ctx = self._dock_limit_context(sec)
        lim = limit_for(ctx) if ctx else None
        meta = {}
        if lim:
            meta["limit"] = lim["context"]
            meta["glyph_pad"] = lim["glyph_pad"]
        # The rows the editor maps: the dialog box when "Box rows" is on,
        # else every selected table row.  Without "Dynamic" a lone dialogue
        # line still previews its whole box.
        flat = [j for j in getattr(self.tr_txt, "_ed_flat", [])
                if 0 <= j < len(self.pack.flat)]
        if self.dyn_size_var.get() or len(flat) > 1:
            rows = self._editor_preview_rows()
            idxs = flat if len(flat) > 1 else [self.current]
        else:
            rows = self.dock_box_rows()
            idxs = self.box_rows(self.current)

        # Rows that form one dialog box keep their box positions (a missing
        # row leaves its gap); anything else stacks.  Either way the renderer
        # never draws a row over the '|' lines of the row above it.
        row_positions = None
        if sec in ("scene_dialog", "inline_text") and len(idxs) == len(rows) \
                and set(idxs) <= set(self.box_rows(self.current)):
            bmap = self.box_map()
            row_positions = [bmap.get(i, (0, 0))[1] for i in idxs]

        try:
            self.preview_queue.request(cv, rows, meta,
                                       expander=self.markup_expander(),
                                       scale=getattr(self, "pv_scale", 2),
                                       row_positions=row_positions,
                                       accent_font=self.accent_font_var.get(),
                                       fallback_font=self.jp_font(
                                           getattr(self, "pv_scale", 2)),
                                       rf_config=getattr(self, "rf_config", None))
        except Exception:
            pass

    def schedule_preview(self, delay=80):
        """Keep typing responsive; render the latest editor state once per burst."""
        pending = getattr(self, "_preview_job", None)
        if pending is not None:
            self.root.after_cancel(pending)
        self._preview_job = self.root.after(delay, self.update_preview)

    def update_preview(self):
        pending = getattr(self, "_preview_job", None)
        if pending is not None:
            self.root.after_cancel(pending)
            self._preview_job = None
        if not hasattr(self, "prev_txt"):
            return
        self._draw_float_preview()
        if self.dyn_var.get():
            self._draw_dyn_preview()
            return
        txt = "\n".join(self._editor_preview_rows())
        self.prev_txt.configure(state="normal")
        self.prev_txt.delete("1.0", "end")
        self._cur_pal = 7
        self._preview_render(txt)
        self.prev_txt.configure(state="disabled")
        self._set_token_info(txt)

    def on_guide_change(self, _evt=None):
        try:
            self._pv_col_guide = max(1, int(self.guide_ent.get().strip()))
        except ValueError:
            return
        self.guide_ent.delete(0, "end")
        self.guide_ent.insert(0, str(self._pv_col_guide))
        self._refresh_pv_guide()

    def _refresh_pv_guide(self, event=None):
        """Draw a thin vertical line at the "col guide" character column (the
        dialog-box width reference, default 24, editable). A 1px-wide canvas
        sits exactly over that column - its solid background matches the
        preview bg, so the text beside it is untouched and only the line
        shows. Re-placed on every resize to stay aligned."""
        if not hasattr(self, "prev_txt"):
            return
        if not getattr(self, "guide_var", None) or not self.guide_var.get():
            # Column Guide OFF: no line, no overlay, nothing in the preview.
            try:
                self.pv_guide.place_forget()
            except tk.TclError:
                pass
            return
        tw = self.prev_txt.winfo_width()
        th = self.prev_txt.winfo_height()
        if tw < 2 or th < 2:
            return
        font = tkfont.Font(font=FONT_MONO)
        pad = 2  # Text widget default padx
        x = pad + font.measure("0") * self._pv_col_guide
        x = min(x, tw - 1)
        self.pv_guide.place(x=x, y=0, width=1, height=th)
        self.pv_guide.delete("all")
        self.pv_guide.create_line(0, 0, 0, th, fill="#8a5a3c",
                                  width=1, dash=(3, 3))

    def _prv(self, w, chunk, extra=()):
        tags = list(extra)
        tags.append("p_pal%d" % self._cur_pal)
        w.insert("end", chunk, tuple(tags))

    def _preview_render(self, text):
        w = self.prev_txt
        _, spans = parse_text(text)
        for s, e, st in spans:
            seg = text[s:e]
            if st == "ascii":
                self._prv(w, seg)
            elif st == "newline":
                w.insert("end", "\n")
            elif st == "fold":
                self._prv(w, seg, ("p_fold",))
            elif st == "nonascii":
                self._prv(w, seg, ("p_non",))
            else:
                self._prv_chip(w, seg, st)

    def _resolve_sub(self, name, arg):
        try:
            idx = int(arg, 16) if arg is not None else 0
        except ValueError:
            idx = 0
        if name == "c1":
            if self.ref_party and idx < len(self.ref_party):
                return self.ref_party[idx]
            return "[character %d]" % idx
        if name in ("c2", "c4"):
            return self.ref_items.get(idx) or "[item 0x%x]" % idx
        if name == "c3":
            return self.ref_spells.get(idx) or "[spell 0x%x]" % idx
        if name == "c5":
            if self.ref_arts and idx < len(self.ref_arts):
                return self.ref_arts[idx]
            return "[art 0x%x]" % idx
        if name == "c7":
            if idx < len(C7_NAMES):
                return C7_NAMES[idx]
            return "[actor 0x%x]" % idx
        return "[%s]" % name.upper()

    def _prv_chip(self, w, seg, st):
        m = TOKEN_RE.match(seg)
        if st == "sub":
            self._prv(w, self._resolve_sub(m.group(1).lower(), m.group(2)),
                      ("p_sub",))
            return
        if st == "ctl":
            name = m.group(1).lower()
            arg = m.group(2)
            if name == "cf" and arg is not None:
                try:
                    pal = int(arg, 16)
                except ValueError:
                    pal = CF_MAX + 1
                if pal <= CF_MAX:
                    self._cur_pal = pal
                    self._prv(w, "\u25cf ", ("p_ctl",))
                else:
                    self._prv(w, "BAD {cf:%s} (0-9)" % arg.upper(), ("p_non",))
            else:
                self._prv(w, "[icon %s]" % (arg or "??"), ("p_ctl",))
            return
        if st == "byte":
            if seg in ("{7b}", "{7d}"):
                self._prv(w, "{" if seg == "{7b}" else "}", ("p_byte",))
            else:
                self._prv(w, "[%s]" % seg.strip("{}").upper(), ("p_byte",))
            return
        if st == "esc2":
            inner = seg.strip("{}")
            if ":" in inner:
                x, y = inner.split(":", 1)
                self._prv(w, "[%s:%s]" % (x.upper(), y.upper()), ("p_byte",))
            else:
                self._prv(w, "[%s]" % inner.upper(), ("p_byte",))

    def _set_token_info(self, text):
        if not hasattr(self, "l_tokens"):
            return
        kinds = []
        for s, e, st in parse_text(text)[1]:
            seg = text[s:e]
            if st == "newline":
                kinds.append("|")
            elif st in ("sub", "ctl"):
                kinds.append(TOKEN_RE.match(seg).group(1).lower())
            elif st == "byte":
                kinds.append("7b" if seg in ("{7b}", "{7d}") else "byte")
            elif st == "esc2":
                kinds.append("esc2")
            elif st == "fold":
                kinds.append("fold")
            elif st == "nonascii":
                kinds.append("nonascii")
        if not kinds:
            self._tokens_set("No control tokens - plain ASCII line.")
            return
        seen = []
        for k in kinds:
            if k not in seen:
                seen.append(k)
        docs = [TOKEN_DOCS[k] for k in seen if k in TOKEN_DOCS]
        self._tokens_set("\n".join(docs) if docs else " / ".join(seen))

    def _tokens_set(self, text):
        """Write the token legend into the fixed-height Text box. The box only
        grows for the widget's height=2 lines; anything longer is scrollable,
        so an entry full of escape codes can never push the preview off the
        window."""
        if not hasattr(self, "l_tokens"):
            return
        self.l_tokens.configure(state="normal")
        self.l_tokens.delete("1.0", "end")
        self.l_tokens.insert("1.0", text)
        self.l_tokens.configure(state="disabled")

    def _open_rf_settings(self):
        if getattr(self, "_rf_settings_win", None) and self._rf_settings_win.winfo_exists():
            self._rf_settings_win.lift()
            self._rf_settings_win.focus_force()
            return
            
        win = tk.Toplevel(self.root)
        win.title("Real Font Options")
        win.geometry("400x320")
        win.transient(self.root)
        
        cfg = getattr(self, "rf_config", {})
        
        f = ttk.Frame(win, padding=12)
        f.pack(fill="both", expand=True)
        
        # BG Color
        ttk.Label(f, text="Background Color (Hex):").grid(row=0, column=0, sticky="w", pady=4)
        bg_col_var = tk.StringVar(value=cfg.get("bg_color", ""))
        ttk.Entry(f, textvariable=bg_col_var).grid(row=0, column=1, sticky="ew", pady=4)
        
        # Border Color
        ttk.Label(f, text="Border Color (Hex):").grid(row=1, column=0, sticky="w", pady=4)
        border_col_var = tk.StringVar(value=cfg.get("border_color", "#ffffff"))
        ttk.Entry(f, textvariable=border_col_var).grid(row=1, column=1, sticky="ew", pady=4)
        
        # Border Width
        ttk.Label(f, text="Border Width (px):").grid(row=2, column=0, sticky="w", pady=4)
        border_w_var = tk.IntVar(value=cfg.get("border_width", 0))
        ttk.Spinbox(f, from_=0, to=20, textvariable=border_w_var, width=5).grid(row=2, column=1, sticky="w", pady=4)
        
        # BG Image
        ttk.Label(f, text="Background Image:").grid(row=3, column=0, sticky="w", pady=4)
        img_f = ttk.Frame(f)
        img_f.grid(row=3, column=1, sticky="ew", pady=4)
        img_var = tk.StringVar(value=cfg.get("bg_image", ""))
        ttk.Entry(img_f, textvariable=img_var).pack(side="left", fill="x", expand=True)
        def browse_img():
            p = filedialog.askopenfilename(title="Select BG Image", filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All", "*.*")])
            if p: img_var.set(p)
        ttk.Button(img_f, text="...", width=3, command=browse_img).pack(side="right", padx=(4,0))
        
        # Alpha
        ttk.Label(f, text="BG Opacity (0.0 - 1.0):").grid(row=4, column=0, sticky="w", pady=4)
        alpha_var = tk.DoubleVar(value=cfg.get("bg_alpha", 1.0))
        ttk.Scale(f, from_=0.0, to=1.0, variable=alpha_var, orient="horizontal").grid(row=4, column=1, sticky="ew", pady=4)
        
        # Retail colours: the game's own dark-blue window and inks instead of
        # the colours derived from the active theme.
        retail_var = tk.BooleanVar(value=bool(cfg.get("retail_colors", False)))
        ttk.Checkbutton(f, text="Retail window colours (ignore the theme)",
                        variable=retail_var).grid(row=5, column=0, columnspan=2,
                                                  sticky="w", pady=(8, 0))

        f.columnconfigure(1, weight=1)

        def save_and_close():
            self.rf_config = {
                "bg_color": bg_col_var.get().strip(),
                "border_color": border_col_var.get().strip() or "#ffffff",
                "border_width": border_w_var.get(),
                "bg_image": img_var.get().strip(),
                "bg_alpha": alpha_var.get(),
                "retail_colors": bool(retail_var.get()),
            }
            _palette.FOLLOW_THEME = not self.rf_config["retail_colors"]
            apply_preview_scheme()
            self.persist_settings()
            self.refresh_previews()
            win.destroy()

        ttk.Button(f, text="Apply", command=save_and_close).grid(row=6, column=0, columnspan=2, pady=16)
        
        self._rf_settings_win = win
