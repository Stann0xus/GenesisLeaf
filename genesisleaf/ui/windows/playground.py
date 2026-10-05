"""Playground tool window: Box editor, Cheatsheet cards, Text Wall, Icons.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from genesisleaf.compat import _PILImage, _PILImageTk
from genesisleaf.core.fonttables import GLYPH_W
from genesisleaf.core.legend import ICON_EMOJI, ICON_LEGEND
from genesisleaf.render.icons import (
    _ICON_BAR_HIGH, _ICON_BAR_LOW, _draw_icons_on_image, _load_icon_images,
)
from genesisleaf.render.metrics import escape_px
from genesisleaf.render.raster import (
    build_font_grid_rgba, render_font_rows, render_wall_text,
)
from genesisleaf.ui.canvas_render import render_text_to_canvas
from genesisleaf.ui.fonts import FONT_UI_B, FONT_UI_SM
from genesisleaf.core import palette as _palette
from genesisleaf.ui import theme as _theme


WALL_SAMPLES = (
    "|  -  the pipe is a glyph here:  {7c}  {ce:14}  {cf:02}  print literally",
    "no | break | ever | happens | in | this | wall",
    "A ROCK {7b}1{7d}  |  VIPER-X  |  099  |  LOARA",
    "0 1 2 3 4 5 6 7 8 9 ? ! . , : ; ( ) [ ] @ # & % + - = / * < >",
    "every colour tag prints as text:  {cf:00} {cf:01} {cf:02} {cf:03} {cf:04} "
    "{cf:05} {cf:06} {cf:07} {cf:08} {cf:09}",
)

WALL_THEMES = (
    "Scene dialog (244px / 3 rows):",
    "A beach! We should be safe here.|Now, the mist.{ce:1d}|My Seru... {c3:11}?",
    "Option box (228px / 4 rows):",
    "Use the Flame Seru?|Specter?|Wait, let me think.|Cancel",
    "Item name (104px / 1 row):",
    "Flash Swrd {c1:00}",
    "Battle message (288px / free rows):",
    "TOTAL DAMAGE: {ce:0b} {cf:05}652!",
)


def build_cheatsheet_cards(parent, pg):
    """Short, objective rule + real-font example box per token.  `pg` is the
    PlaygroundTab that owns the accent toggle and markup expander."""
    outer = ttk.Frame(parent)
    cvs = tk.Canvas(outer, highlightthickness=0, bg=_theme.TH_PANEL_BG)
    vsb = ttk.Scrollbar(outer, orient="vertical", command=cvs.yview)
    inner = ttk.Frame(cvs)
    inner.bind("<Configure>", lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
    cvs.create_window((0, 0), window=inner, anchor="nw")
    cvs.configure(yscrollcommand=vsb.set)
    cvs.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    ttk.Label(inner,
              text="Every {xx:yy} token in one line.  The pipe | ends the row. "
                   "{cf:00}-{cf:09} recolor what follows.  Boxes render with the "
                   "REAL font (accent font when its toggle is on).",
              font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED,
              wraplength=940).pack(anchor="w", padx=12, pady=(10, 2))

    def card(title, rule, markup, lim=None, accent=False, emoji=False):
        box = ttk.LabelFrame(inner, text=title, padding=6)
        box.pack(fill="x", padx=8, pady=6)
        ttk.Label(box, text=rule, wraplength=940, justify="left",
                  font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED).pack(anchor="w")
        ttk.Label(box, text=markup, font=("Consolas", 9), padding=4,
                  background=_theme.BG_EDIT, foreground=_theme.FG_MAIN).pack(anchor="w",
                                                               pady=(4, 2))
        rc = tk.Canvas(box, height=56, background=_theme.BG_EDIT,
                       highlightthickness=0)
        rc.pack(fill="x")
        meta = {"glyph_pad": 1}
        if lim:
            meta["limit"] = lim
            meta["glyph_pad"] = lim.get("glyph_pad", 1)
        def draw(with_accent):
            try:
                render_text_to_canvas(rc, [markup], meta,
                                      expander=pg.app.markup_expander(),
                                      scale=1, accent_font=with_accent,
                                      emoji_icons=emoji)
            except Exception:
                pass
        draw(True if accent else bool(pg.accent_var.get()))
        if accent:
            pg._cheat_accent_cards.append((rc, markup, meta, draw))

    acc = pg.app.markup_expander  # bound for readability
    _ = acc

    card("Newline",
         "A pipe | ends the row; the next glyph starts on the row below.",
         "Line one|Line two")
    card("Colours",
         "{cf:NN} recolours everything after it.  01-06 are the dialogue "
         "palette, 07-09 the info-board lights; 00 = dark purple.",
         "{cf:00}x{cf:02}x{cf:04}x{cf:06}x{cf:08}x{cf:09}x")
    card("Literal braces",
         "A { starts a token, so write {7b} and {7d} to print a literal brace.",
         "Box {7b}1{7d} of 2")
    card("Literal pipe",
         "{7c} prints the pipe glyph itself and does NOT break the row.",
         "x{7c}y")
    card("Accents",
         "Accented latin-1 (a accent, c cedilla...) renders when the accent "
         "font is on; toggle it in the Box tab.",
         "Voce nao e tao bom! -> Voc\u00ea n\u00e3o \u00e9 t\u00e3o bom.",
         accent=True)
    card("Fold to ASCII",
         "Letters outside the font fold to their ASCII base (A -> A, 6 -> 6 "
         "stay when they are already there).",
         "S\u00e3o Francisco")
    card("Character name",
         "{c1:NN} splices a party member's name (party_names table; shows the "
         "real name when a pack is loaded).",
         "Vahn:{c1:00}")
    card("Item name",
         "{c2:NN} and {c4:NN} splice an item's name (items table).",
         "Got {c2:1a}.")
    card("Spell name",
         "{c3:NN} splices a spell's name (spells table).",
         "{c3:0e}!")
    card("Art name",
         "{c5:NN} splices an Art's name (arts table).",
         "{c5:1e}!!")
    card("Actor / speaker",
         "{c7:NN} splices the current speaker (Meta, Algernon...).",
         "{c7:00}: I see.")
    card("Undefined C0/C6",
         "{c0:NN} and {c6:NN} have no retail substitution arm - they stay "
         "2-byte glyphs (undefined; draw nothing).",
         "raw {c0:00}")
    card("Icon / escape",
         "{ce:NN} reserves a fixed box for a button / armour / element icon; "
         "all boxes are listed in the Icons tab.",
         "DMG {ce:14} 90", emoji=True)
    card("Digital form",
         "{ff:NN} and {5e:NN} are the raw aliases of {cf:NN} and {ce:NN} "
         "(0xFF -> 0xCF, 0x5E -> 0xCE).",
         "{ff:02}hi")
    return outer


class PlaygroundTab(ttk.Frame):
    """Body of the Playground tool window: the Box editor, the cheatsheet, the
    Text Wall and the Icons legend.  See the module docstring above."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=4)
        self.app = app
        self.accent_var = tk.BooleanVar(value=False)
        self.lines_var = tk.IntVar(value=3)
        self.maxpx_var = tk.IntVar(value=244)
        self.chars_var = tk.IntVar(value=40)
        self.scale_var = tk.IntVar(value=2)
        self._syncing = False
        self._cheat_accent_cards = []
        self._keep = []

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        nb.add(self._build_box_tab(nb), text=" Box ")
        nb.add(self._build_cheat_tab(nb), text=" Cheatsheet ")
        nb.add(self._build_wall_tab(nb), text=" Text Wall ")
        nb.add(self._build_icons_tab(nb), text=" Icons ")

        self.lines_var.trace_add("write", self._on_box_changed)
        self.maxpx_var.trace_add("write", self._on_maxpx_changed)
        self.chars_var.trace_add("write", self._on_chars_changed)
        self.scale_var.trace_add("write", self._on_box_changed)
        self.accent_var.trace_add("write", self._on_accent_changed)
        self._refresh_box()

    # -- helpers --------------------------------------------------------------
    def _expand_markup(self):
        try:
            return self.app.markup_expander()
        except Exception:
            return None

    # -- Box --------------------------------------------------------------
    def _build_box_tab(self, parent):
        t = ttk.Frame(parent)
        bar = ttk.Frame(t)
        bar.pack(side="top", fill="x", padx=4, pady=(4, 0))
        ttk.Label(bar, text="Lines", font=FONT_UI_SM).pack(side="left")
        ttk.Spinbox(bar, from_=1, to=8, textvariable=self.lines_var, width=3,
                    font=FONT_UI_SM).pack(side="left", padx=(2, 10))
        ttk.Label(bar, text="Max chars / line", font=FONT_UI_SM).pack(side="left")
        ttk.Spinbox(bar, from_=1, to=99, textvariable=self.chars_var, width=3,
                    font=FONT_UI_SM).pack(side="left", padx=(2, 10))
        ttk.Label(bar, text="Red line (px)", font=FONT_UI_SM).pack(side="left")
        ttk.Spinbox(bar, from_=40, to=1200, increment=1,
                    textvariable=self.maxpx_var, width=5,
                    font=FONT_UI_SM).pack(side="left", padx=(2, 10))
        ttk.Checkbutton(bar, text="Accent font", variable=self.accent_var,
                        onvalue=True, offvalue=False).pack(side="left",
                                                           padx=(0, 10))
        ttk.Label(bar, text="Scale", font=FONT_UI_SM).pack(side="left")
        ttk.Spinbox(bar, from_=1, to=4, textvariable=self.scale_var, width=3,
                    font=FONT_UI_SM).pack(side="left", padx=(2, 10))
        self.box_note = ttk.Label(t, text="", font=FONT_UI_SM,
                                  foreground=_theme.TH_FG_MUTED)
        self.box_note.pack(side="top", anchor="w", padx=8, pady=(2, 0))

        pane = ttk.Panedwindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=4, pady=4)
        left = ttk.LabelFrame(pane, text=" Box markup (custom editor) ",
                              padding=4)
        self.ed = tk.Text(left, wrap="word", undo=True, height=8,
                          background=_theme.BG_EDIT, foreground=_theme.FG_MAIN,
                          insertbackground=_theme.FG_MAIN, relief="flat",
                          font=("Consolas", 10))
        ed_sb = ttk.Scrollbar(left, orient="vertical", command=self.ed.yview)
        self.ed.configure(yscrollcommand=ed_sb.set)
        self.ed.pack(side="left", fill="both", expand=True)
        ed_sb.pack(side="right", fill="y")
        self.ed.insert("1.0", "Hello, {c1:00}!|Welcome to Sol.|{cf:02}Press "
                              "{ce:14} to save.")
        self.ed.bind("<<Modified>>", self._on_edit)

        right = ttk.LabelFrame(pane, text=" Real font box (red line = budget) ",
                               padding=4)
        self.box_cv = tk.Canvas(right, background=_theme.BG_EDIT,
                                highlightthickness=0)
        hsb = ttk.Scrollbar(right, orient="horizontal",
                            command=self.box_cv.xview)
        vsb = ttk.Scrollbar(right, orient="vertical",
                            command=self.box_cv.yview)
        self.box_cv.configure(xscrollcommand=hsb.set, yscrollcommand=vsb.set)
        self.box_cv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        pane.add(left, weight=1)
        pane.add(right, weight=3)
        return t

    def _on_edit(self, _evt=None):
        if self.ed.edit_modified():
            self._refresh_box()
        self.ed.edit_modified(False)

    def _on_box_changed(self, *_):
        self._refresh_box()

    def _on_maxpx_changed(self, *_):
        if self._syncing:
            return
        try:
            self.chars_var.set(max(1, round(int(self.maxpx_var.get()) / 6)))
        except (ValueError, tk.TclError):
            return

    def _on_chars_changed(self, *_):
        if self._syncing:
            return
        try:
            ch = max(1, int(self.chars_var.get()))
        except (ValueError, tk.TclError):
            ch = self.chars_var.get()
        self.maxpx_var.set(ch * 6)   # ~6px per character in the real font

    def _on_accent_changed(self, *_):
        self._refresh_box()
        for cv, markup, meta, draw in self._cheat_accent_cards:
            draw(bool(self.accent_var.get()))

    def _refresh_box(self, *_):
        try:
            text = self.ed.get("1.0", "end-1c")
        except tk.TclError:
            return
        lines = max(1, int(self.lines_var.get()))
        rows = (text.split("\n") or [""])[:lines]
        try:
            maxpx = int(self.maxpx_var.get())
        except (ValueError, tk.TclError):
            maxpx = 244
        meta = {"limit": {"context": "playground", "max_px": maxpx,
                          "max_lines": lines, "glyph_pad": 1}}
        try:
            res = render_text_to_canvas(
                self.box_cv, rows, meta, expander=self._expand_markup(),
                scale=max(1, int(self.scale_var.get())),
                accent_font=bool(self.accent_var.get()), emoji_icons=True)
        except Exception as exc:
            self.box_note.configure(
                text="render error: %r" % (exc,))
            return
        if not res:
            self.box_note.configure(text="(empty)")
            return
        _, _, widest, limit_px = res
        extra = len(text.split("\n")) - lines
        note = "widest row %d px | red line %d px | %s | %s" % (
            widest, limit_px,
            ("%d px over!" % (widest - limit_px)) if widest > limit_px
            else ("%d px to spare" % (limit_px - widest)),
            ("%d more box line(s) hidden" % extra) if extra > 0 else "box fits")
        self.box_note.configure(text=note)

    # -- Cheatsheet -----------------------------------------------------------
    def _build_cheat_tab(self, parent):
        return build_cheatsheet_cards(parent, self)

    # -- Text Wall -------------------------------------------------------------
    def _build_wall_tab(self, parent):
        t = ttk.Frame(parent)
        cvs = tk.Canvas(t, background=_theme.BG_EDIT, highlightthickness=0)
        hsb = ttk.Scrollbar(t, orient="horizontal", command=cvs.xview)
        vsb = ttk.Scrollbar(t, orient="vertical", command=cvs.yview)
        cvs.configure(xscrollcommand=hsb.set, yscrollcommand=vsb.set)
        cvs.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        t.rowconfigure(0, weight=1)
        t.columnconfigure(0, weight=1)

        self._keep = []
        y = 0
        cvs.create_text(8, y, anchor="nw", text="FULL FONT  0x21 .. 0xFF",
                        fill="#9fc8f8", font=FONT_UI_B)
        y += 26
        if _PILImage is None:
            cvs.create_text(8, y, anchor="nw",
                            text="(Image rendering needs Pill - install it "
                                 "to see the full font.)",
                            fill="#7fa7d8", font=FONT_UI_SM)
            y += 26

        w, h, rgba, slots = build_font_grid_rgba()
        img = _PILImage.frombytes("RGBA", (w, h), rgba)
        img = img.resize((w * 2, h * 2), _PILImage.NEAREST)
        ph = _PILImageTk.PhotoImage(img)
        self._keep.append(ph)
        cvs.create_image(4, y, anchor="nw", image=ph)
        for b, x0, y0 in slots:
            cvs.create_text(4 + x0 * 2 + GLYPH_W, y + y0 * 2 - 4,
                            text="%02X" % b, anchor="n",
                            fill="#4f8fd0", font=("Consolas", 6))
        y += h * 2 + 24

        cvs.create_text(8, y, anchor="nw",
                        text="LITERAL  -  NO effects:  |  {7c}  {ce:14}  {cf:02} "
                             "are glyphs here, nothing ever jumps rows",
                        fill="#9fc8f8", font=FONT_UI_B)
        y += 26
        w2, h2, rgba2, _ = render_wall_text(WALL_SAMPLES)
        img2 = _PILImage.frombytes("RGBA", (w2, h2), rgba2)
        img2 = img2.resize((w2 * 2, h2 * 2), _PILImage.NEAREST)
        ph2 = _PILImageTk.PhotoImage(img2)
        self._keep.append(ph2)
        cvs.create_image(4, y, anchor="nw", image=ph2)
        y += h2 * 2 + 26

        cvs.create_text(8, y, anchor="nw",
                        text="REAL  windowed examples  (effects on, like the "
                             "finished game)",
                        fill="#9fc8f8", font=FONT_UI_B)
        y += 26
        for head, markup in ((WALL_THEMES[0], WALL_THEMES[1]),
                             (WALL_THEMES[2], WALL_THEMES[3]),
                             (WALL_THEMES[4], WALL_THEMES[5]),
                             (WALL_THEMES[6], WALL_THEMES[7])):
            cvs.create_text(8, y, anchor="nw", text=head, fill="#7fa7d8",
                            font=FONT_UI_SM)
            y += 20
            hh = self._render_example_into(cvs, markup, y)
            y += hh + 8

        cvs.configure(scrollregion=(0, 0, 4096, y + 20))
        return t

    def _render_example_into(self, cvs, markup, y_top):
        """Render a real windowed example right on the wall canvas; returns the
        drawn height.  `markup` holds the literal source (pipes split rows)."""
        h2 = 0
        try:
            from_bytes = _PILImage.frombytes
            w, h, rgba, _, _, icons, _fb = render_font_rows(
                [markup], {"glyph_pad": 1}, expander=self._expand_markup(),
                accent_font=bool(self.accent_var.get()))
            img = from_bytes("RGBA", (w, h), rgba)
            img = img.resize((w * 2, h * 2), _PILImage.NEAREST)
            img = _draw_icons_on_image(img, icons, 2)
            ph = _PILImageTk.PhotoImage(img)
            self._keep.append(ph)
            cvs.create_image(8, y_top, anchor="nw", image=ph)
            h2 = h * 2
            have = _load_icon_images()
            span = _ICON_BAR_HIGH - _ICON_BAR_LOW
            for x, py, width, idx in icons:
                if idx in have:
                    continue
                em = ICON_EMOJI.get(idx)
                if not em:
                    continue
                pixel = max(8.0, min(width, span) * 2 * 0.62)
                pt = max(6, int(round(pixel * 72 / 96.0)))
                try:
                    fnt = tkfont.Font(family="Segoe UI Emoji", size=pt)
                except tk.TclError:
                    continue
                cvs.create_text(8 + (x + width / 2.0) * 2,
                                y_top + (py + _ICON_BAR_LOW + span / 2.0) * 2,
                                text=em, anchor="center", font=fnt,
                                fill="#%02x%02x%02x" % _palette.PV_WHITE)
        except Exception:
            pass
        return h2

    # -- Icons -----------------------------------------------------------------
    def _build_icons_tab(self, parent):
        t = ttk.Frame(parent)
        cvs = tk.Canvas(t, background=_theme.TH_PANEL_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(t, orient="vertical", command=cvs.yview)
        inner = ttk.Frame(cvs)
        inner.bind("<Configure>",
                   lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.create_window((0, 0), window=inner, anchor="nw")
        cvs.configure(yscrollcommand=vsb.set)
        cvs.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        ttk.Label(inner,
                  text="Every {ce:..} splice with its REAL advance box.  The "
                       "bars are exactly what the retail font reserves; the "
                       "artwork is the embedded icon data scaled to that "
                       "slot (emoji is only a fallback when an icon is "
                       "missing).",
                  font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED,
                  wraplength=1000).pack(anchor="w", padx=10, pady=(8, 4))
        for idx in range(0x24):
            self._icon_card(inner, idx)
        return t

    def _icon_card(self, inner, idx):
        box = ttk.LabelFrame(inner, text="  {ce:%02X}  " % idx, padding=4)
        box.pack(fill="x", padx=8, pady=3)
        kind, adv = escape_px(idx, 4)
        em = ICON_EMOJI.get(idx)
        desc = ICON_LEGEND[idx]
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text=desc, font=FONT_UI_SM).pack(side="left",
                                                        padx=(4, 12))
        ttk.Label(row, text="%s  %d px advance" % (kind, adv),
                  font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED).pack(side="left")
        if em:
            ttk.Label(row, text="emoji %r" % em,
                      font=FONT_UI_SM, foreground=_theme.TH_FG_FAINT).pack(
                side="right", padx=8)
        cv = tk.Canvas(box, height=44, background=_theme.BG_EDIT,
                       highlightthickness=0)
        cv.pack(fill="x", pady=(2, 0))
        try:
            render_text_to_canvas(cv, ["{ce:%02X}" % idx], {"glyph_pad": 1},
                                  expander=self._expand_markup(), scale=2,
                                  emoji_icons=bool(em))
        except Exception:
            pass
