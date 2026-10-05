"""Tools > Cheatsheet window and the Playground window host.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import ttk

from genesisleaf.ui.fonts import FONT_UI_BIG, FONT_UI_SM
from genesisleaf.ui.windows.playground import PlaygroundTab


class CheatsheetMixin:
    """Tools > Cheatsheet window and the Playground window host.

    Mixed into `App`; `self` is the main window.
    """

    # -- cheatsheet tab ---------------------------------------------------------
    def _build_cheatsheet_tab(self, parent):
        f = ttk.Frame(parent)
        self.cheat_txt = tk.Text(f, wrap="word", font=FONT_UI_SM,
                                 bg="#fbfbfb", padx=10, pady=8)
        vs = ttk.Scrollbar(f, orient="vertical", command=self.cheat_txt.yview)
        self.cheat_txt.configure(yscrollcommand=vs.set)
        self.cheat_txt.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.cheat_txt.configure(state="normal")
        self._fill_cheatsheet()
        self.cheat_txt.configure(state="disabled")
        return f

    def _fill_cheatsheet(self):
        t = self.cheat_txt
        self.configure_text_tags(t)
        ins = t.insert
        ins("end", "\nMARKUP CODES   (guidelines: legend-of-legaia-re/tooling/translation)\n")
        t.tag_add("h", "end-1c")
        t.tag_configure("h", font=FONT_UI_BIG, foreground="#1450c8")

        for txt, tg in (
            ("{01}", "byte"), ("{c1:00}", "sub"), ("{c2:79}", "sub"),
            ("{c3:0e}", "sub"), ("{c5:02}", "sub"), ("{c7:00}", "sub"),
            ("{cf:09}", "ctl"), ("{ce:10}", "ctl"), ("{7b}", "byte")):
            end = t.index("end-1c")
            ins("end", "  " + txt)
            t.tag_add(tg, end, "end-1c")

        ins("end", "\n")
        ins("end", "  {c1:..} character-name substitution     2 bytes\n")
        ins("end", "  {c2:..} item-name substitution          2 bytes\n")
        ins("end", "  {c3:..} magic-name substitution         2 bytes\n")
        ins("end", "  {c5:..} art-name substitution           2 bytes\n")
        ins("end", "  {c7:..} actor-name substitution (00 Meta, 01 Terra, 02 Ozma)\n")
        ins("end", "  {cf:0n} palette / colour change (n = 0-9)    2 bytes\n")
        ins("end", "  {ce:..} spacing / icon escape           2 bytes\n")
        ins("end", "  {xx}    bare byte (e.g. {01} icon prefix)   1 byte\n")
        ins("end", "  {xx:yy} raw two-byte escape             2 bytes\n")
        ins("end", "  {7b} = literal {    {7d} = literal }     1 byte each\n")

        ins("end", "\nBUDGETS - the same-size rule\n")
        ins("end", "  The `budget:` value on each key is the max encoded bytes (it is measured\n")
        ins("end", "  to the disc span, including alignment padding - NOT the source length).\n")
        ins("end", "  The importer rejects anything over it. Colour guide in the editor:\n")
        ins("end", "    GREEN   fits within the budget\n")
        ins("end", "    YELLOW  encoded bytes exceed the budget - will not fit\n")
        ins("end", "    RED     unencodable characters (shown per-character)\n")
        ins("end", "  Dialogue rows are line-granular and pack 3 segments/box: translate\n")
        ins("end", "  consecutive rows as a group, each inside its own budget.\n")

        ins("end", "\nCHARACTERS\n")
        ins("end", "  Only printable ASCII 0x20-0x7E is encodable (retail font).\n")
        ins("end", "  RED underlined  -> accent/Cyrillic/CJK etc. NOT encodable. Fold:\n")
        ins("end", "      Epee not \u00c9p\u00e9e, Nao not N\u00e3o, Acao not A\u00e7\u00e3o, ss not \u00df\n")
        end = t.index("end-1c")
        ins("end", "  PURPLE underlined -> smart quote / dash / ellipsis / NBSP: auto-folded\n")
        t.tag_add("fold_ex", end + " lineend")
        t.tag_configure("fold_ex", foreground="#7a5cd6", underline=True)
        ins("end", "\n      to ASCII by the importer, but type plain ASCII anyway.\n")

        ins("end", "\nRULES OF THUMB\n")
        ins("end", "  - Keep every control token exactly where the source has it.\n")
        ins("end", "  - Do not touch the {..} braces or the '|' newline.\n")
        ins("end", "  - One line per {..}? no: one entry = one row; | splits rows.\n")
        ins("end", "  - Names (items, spells, arts) > labels (menus) > dialogue stay short:\n")
        ins("end", "    shorter always fits; longer never grows the disc.\n")
        ins("end", "  - Lines EITHER stay English if too long - never invent padding.\n")
        ins("end", "  - A partially filled pack is always playable.\n")
        ins("end", "\nWORKFLOW\n")
        ins("end", "  export -> fill translation: (this tool) -> stats -> strip (removes\n")
        ins("end", "  source+context) -> import into your disc. Never commit working packs;\n")
        ins("end", "  they carry the game script. Share only stripped packs.\n")
        ins("end", "  Save (Ctrl+S) writes a byte-perfect pack; a <pack>.bak is kept.\n")

        ins("end", "\nLIST MARKERS (Status column in the entry list)\n")
        ins("end", "  (blank)  untranslated      *  translated\n")
        ins("end", "  !        encoded bytes over the key's budget\n")
        ins("end", "  @        translation has non-ASCII characters\n")
        ins("end", "  #        translation has an invalid {cf:..} colour code (must be 0-9)\n")

        ins("end", "\nNAVIGATOR (left sidebar, Ctrl+B hides it)\n")
        ins("end", "  SECTIONS  click a section to show only it (done/total and % each)\n")
        ins("end", "  STATUS    click a status to filter; counts update as you work\n")
        ins("end", "  CONTEXT   context filter - hex ids collapse into one group\n")
        ins("end", "            ('item 0x..' covers every 'item 0xNN')\n")
        ins("end", "  Click any column header (# / Key / Context / Source / Translation /\n")
        ins("end", "  Section / B-S / marker) to sort ascending, again for descending, a\n")
        ins("end", "  third time (or 'x sort') to drop the ordering.  # is the entry's\n")
        ins("end", "  position in the YAML as shipped.  B-S sorts by encoded bytes; the\n")
        ins("end", "  marker sorts blank -> translated -> over-budget -> non-ASCII.\n")
        ins("end", "  Click / Shift+Click select rows; Ctrl+Click picks single cells and\n")
        ins("end", "  Ctrl+C then copies them as a grid.  Ctrl+wheel zooms the table.\n")

        ins("end", "\nPREVIEW PANE (bottom editor dock - always visible)\n")
        ins("end", "  Render of the current translation, approx game-style.\n")
        ins("end", "  BLUE names    {c1/c2/c3/c5:..} resolve to the real party / item /\n")
        ins("end", "                spell / art names where the pack has them.\n")
        ins("end", "  GOLD circles  {cf:..} palette switch (text after it recolours;\n")
        ins("end", "                0 dark grey, 1 blue, 2 red, 3 purple, 4 green, 5 cyan,\n")
        ins("end", "                6 orange, 7 greyed, 8 white, 9 red - 0-9 only, anything\n")
        ins("end", "                above 9 is invalid and breaks the game).\n")
        ins("end", "  GOLD [icon]  {ce:..} escape (icon/button/currency/number splice).\n")
        ins("end", "  VIOLET [..]  bare bytes {01}, raw {xx:yy}, and literal braces.\n")
        ins("end", "  RED           unencodable characters.\n")
        ins("end", "  |   new line in the preview; the line under it lists every control\n")
        ins("end", "      token used and what it means, from the RE documentation.\n")

        ins("end", "\nAUTO-FIX tab\n")
        ins("end", "  Dry run then apply: scope = current / over-budget / non-ASCII / all.\n")
        ins("end", "  Fixes: real newlines -> |, fold accents/smart punctuation to ASCII,\n")
        ins("end", "  collapse repeated spaces, trim, truncate to budget (cuts only at\n")
        ins("end", "  word / row boundaries so control tokens always survive).\n")
        ins("end", "\nCOMPARE tab\n")
        ins("end", "  Open a second pack (File > Compare with pack...) to review it key-by-key\n")
        ins("end", "  against MINE: same / differ / only-in-one. Double-click a row (or use\n")
        ins("end", "  Jump) to open it in the editor. 'Adopt OTHER -> MINE' copies that text\n")
        ins("end", "  into MINE; only MINE is saved with Ctrl+S. Filter 'Mine empty, other\n")
        ins("end", "  filled' lists what you can import in one pass.\n")

        ins("end", "\nLAYOUT\n")
        ins("end", "  Toolbar, navigator on the left, Find bar + table, and the editor\n")
        ins("end", "  dock under the table (drag either sash).  Clicking a row in any\n")
        ins("end", "  table (Entries, Search, Shared words/Dups, Compare) loads it into\n")
        ins("end", "  the dock.  The byte meter beside the key turns amber over budget\n")
        ins("end", "  and red for unencodable text.  Tools and extra windows live in the\n")
        ins("end", "  Tools and View menus; Help lists every shortcut.\n")

        ins("end", "\nKEYBOARD\n")
        ins("end", "  Ctrl+S save    Ctrl+O open    Ctrl+F search    Ctrl+E edit\n")
        ins("end", "  Ctrl+N/P next/prev entry, Ctrl+Down/Up next/prev untranslated\n")
        ins("end", "  Enter inserts '|' in the translation box (Ctrl+Enter = newline)\n")

    def _build_playground_tab(self, win):
        return PlaygroundTab(win, self)
