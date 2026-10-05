"""Compare packs: WinMerge-style two-pane diff, previews, adopt OTHER -> MINE.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import bisect
import difflib
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from genesisleaf.core.colors import mix
from genesisleaf.core.constants import (
    CMP_EV, CMP_LEVEL, CMP_MB, CMP_MBUD, CMP_MI, CMP_MTR,
    CMP_OB, CMP_OBUD, CMP_OI, CMP_OSRC, CMP_OTR, CMP_SEC, CMP_SRC, CMP_ST,
)
from genesisleaf.core.dialog import default_limit_context, limit_for
from genesisleaf.core.encoding import parse_text
from genesisleaf.core.pack import Pack, needs_accent_font
from genesisleaf.core import pairing
from genesisleaf.ui.cellsel import CellSelection, clean
from genesisleaf.ui.canvas_render import render_text_to_canvas
from genesisleaf.ui.fonts import FONT_MONO, FONT_MONO_B, FONT_UI_SM, FONT_UI_SM_B
from genesisleaf.ui.loader import BusyOverlay
from genesisleaf.ui.menubar import Menubar
from genesisleaf.ui.widgets import ToolTip, TreeRowTip
from genesisleaf.ui import theme as _theme

NOTE_MARK = "✎"        # pencil: the row's entry carries `notes`


class CompareMixin:
    """Compare packs: WinMerge-style two-pane diff, previews, adopt OTHER -> MINE.

    Mixed into `App`; `self` is the main window.
    """

    # -- compare window ------------------------------------------------------------
    # MINE (left pane) and a second, read-only pack (right pane) side by side,
    # one pairing per row and both panes scrolling and selecting together, the
    # way WinMerge shows two files: an entry missing on one side leaves a grey
    # gap there, differing pairs are tinted, and the location bar on the left
    # maps every difference in the whole list (click it to scroll there).
    # The diff pane under the table marks exactly which characters differ in
    # the selected pair, and the previews render both sides in the real font.
    # The certainty of each pairing is the "Pair" column; the evidence is in
    # the row's tooltip.
    CMP_FILTERS = ("All", "Differences", "Source differs",
                   "Candidates (review)", "Mine empty, other filled",
                   "Only in mine", "Only in other", "Same")
    CMP_LEFT_COLS = (("st", "", 26), ("lvl", "Pair", 52),
                     ("note", NOTE_MARK, 24), ("key", "Key", 150),
                     ("sec", "Section", 80), ("ctx", "Context", 110),
                     ("source", "Source", 180), ("mine", "Translation", 180),
                     ("bm", "B/S", 62))
    CMP_RIGHT_COLS = (("onote", NOTE_MARK, 24), ("keyo", "Key", 150),
                      ("osec", "Section", 80), ("octx", "Context", 110),
                      ("osrc", "Source", 180), ("other", "Translation", 180),
                      ("bo", "B/S", 62))
    CMP_STRETCH = ("source", "mine", "osrc", "other")
    LOC_W = 18              # location bar width (px)

    def _build_compare_tab(self, parent):
        f = ttk.Frame(parent, padding=(8, 4, 8, 8))
        self._cmp_busy = False
        self._cmp_overlay = None
        self._cmp_detail_job = None
        self._cmp_diff_pos = []
        self._cmp_other_flat = []
        self._build_compare_menu(parent.winfo_toplevel())

        # ---- toolbar: everything the Compare menu does, one click away -----
        bar = ttk.Frame(f)
        bar.pack(fill="x")

        def btn(text, cmd, tip, side="left", padx=(0, 3)):
            # sized to the label: the bar has to fit a 1280px window
            b = ttk.Button(bar, text=text, command=cmd, width=len(text) + 2)
            b.pack(side=side, padx=padx)
            ToolTip(b, tip, delay=500)
            return b

        def sep():
            ttk.Separator(bar, orient="vertical").pack(
                side="left", fill="y", padx=5, pady=2)

        btn("Open 2nd pack...", self.open_compare_pack,
            "Open the pack to compare MINE with (right pane, read-only)")
        btn("Save", lambda: self.save_pack(ask=True),
            "Save MINE  (Ctrl+S)")
        btn("Save As...", self.save_pack_as,
            "Save MINE to a new file  (Ctrl+Shift+S)")
        sep()
        btn("⏮ First", lambda: self.cmp_goto_diff("first"),
            "First difference")
        btn("▲ Prev", lambda: self.cmp_goto_diff(-1),
            "Previous difference  (Alt+Up)")
        btn("▼ Next", lambda: self.cmp_goto_diff(1),
            "Next difference  (Alt+Down)")
        btn("⏭ Last", lambda: self.cmp_goto_diff("last"),
            "Last difference")
        sep()
        btn("Jump", self.jump_from_compare,
            "Jump to the MINE entry in the editor  (double-click)")
        btn("◀ Adopt", self.adopt_other_selected,
            "Adopt OTHER -> MINE for the selected rows")
        btn("◀◀ Adopt all", self.adopt_other_all,
            "Adopt OTHER -> MINE for every shown row the pairing is sure of "
            "(weak candidates are never bulk-adopted)")
        sep()
        btn("Notes", self._cmp_open_notes,
            "Notes dashboard on the selected entry  (Alt+double-click)")
        btn("Close", self.close_compare, "Close the comparison",
            side="right", padx=0)

        mid = ttk.Frame(f)
        mid.pack(fill="x", pady=(6, 0))
        ttk.Label(mid, text="Show:", font=FONT_UI_SM).pack(side="left")
        self.cmp_cb = ttk.Combobox(
            mid, state="readonly", width=24, font=FONT_UI_SM,
            values=list(self.CMP_FILTERS))
        self.cmp_cb.current(0)
        self.cmp_cb.pack(side="left", padx=(2, 8))
        self.cmp_cb.bind("<<ComboboxSelected>>",
                         lambda e: self._cmp_apply_filter())
        self.l_cmp_pos = ttk.Label(mid, text="", font=FONT_UI_SM,
                                   foreground=_theme.TH_FG_MUTED)
        self.l_cmp_pos.pack(side="left", padx=(4, 0))
        self.l_cmp_sum = ttk.Label(mid, text="", foreground=_theme.TH_FG_MUTED,
                                   font=FONT_UI_SM)
        self.l_cmp_sum.pack(side="right")

        # ---- table over the lower section, the split draggable ------------
        vpan = ttk.Panedwindow(f, orient="vertical")
        vpan.pack(fill="both", expand=True, pady=(6, 0))
        self._cmp_vpan = vpan
        self._cmp_sash_set = False
        vpan.bind("<Configure>", self._cmp_first_sash, add="+")

        # ---- the two panes ---------------------------------------------------
        tree_row = ttk.Frame(vpan)
        vpan.add(tree_row, weight=3)
        tree_row.rowconfigure(0, weight=1)
        tree_row.columnconfigure(1, weight=1)
        self.cmp_loc = tk.Canvas(tree_row, width=self.LOC_W,
                                 highlightthickness=1, cursor="hand2",
                                 bg=_theme.TH_TREE_BG,
                                 highlightbackground=_theme.TH_BORDER)
        self.cmp_loc.grid(row=0, column=0, sticky="ns", padx=(0, 4))
        self.cmp_loc.bind("<Configure>", lambda e: self._cmp_draw_location())
        self.cmp_loc.bind("<Button-1>", self._cmp_loc_click)
        self.cmp_loc.bind("<B1-Motion>", self._cmp_loc_click)

        panes = ttk.Panedwindow(tree_row, orient="horizontal")
        panes.grid(row=0, column=1, sticky="nsew")
        self.cmp_tree = self._cmp_make_pane(panes, "left")
        self.cmp_tree_r = self._cmp_make_pane(panes, "right")
        vs = ttk.Scrollbar(tree_row, orient="vertical",
                           command=self._cmp_yview)
        vs.grid(row=0, column=2, sticky="ns")
        self._cmp_vs = vs
        for side, tv in (("left", self.cmp_tree), ("right", self.cmp_tree_r)):
            tv.configure(yscrollcommand=lambda a, b, s=side:
                         self._cmp_on_yscroll(s, a, b))

        # Ctrl+Click picks cells, plain clicks select rows (ui/cellsel.py);
        # created after the scroll callbacks, which it chains onto
        self.cmp_cellsel = CellSelection(
            self.cmp_tree, on_pick=self._cmp_on_cells_picked,
            on_copy=self._push_clip_history)
        self.cmp_cellsel_r = CellSelection(
            self.cmp_tree_r, on_pick=self._cmp_on_cells_picked,
            on_copy=self._push_clip_history)
        self._cmp_apply_tags()

        # ---- lower section: diff pane, preview controls, previews ----------
        lower = ttk.Frame(vpan)
        vpan.add(lower, weight=2)

        # the selected pair, character differences marked - directly under
        # the table, as in WinMerge
        self.cmp_diff = tk.Text(lower, height=4, wrap="none", font=FONT_MONO,
                                relief="flat", padx=6, pady=3,
                                highlightthickness=1, cursor="arrow")
        self.cmp_diff.pack(side="top", fill="x", pady=(6, 0))
        self.cmp_diff.bind("<Key>", self._cmp_diff_key)

        hint = ttk.Label(lower, text="Only MINE (left) is saved.  Weak "
                                     "candidates: adopt row by row.  "
                                     "Alt+Up/Down: next difference.  "
                                     "Alt+double-click: notes.  Drag the "
                                     "split above to resize.",
                         foreground=_theme.TH_FG_FAINT, font=FONT_UI_SM)
        hint.pack(side="bottom", fill="x", pady=(4, 0))

        ctrl_row = ttk.Frame(lower)
        ctrl_row.pack(side="top", fill="x", pady=(6, 2))
        # each side: what to preview (translation / source / both) and with
        # which font; the accent font follows each pack's language
        self.cmp_mine_mode = tk.StringVar(value="translation")
        self.cmp_mine_both = tk.BooleanVar(value=False)
        self.cmp_mine_accent = tk.BooleanVar(value=False)
        self.cmp_other_mode = tk.StringVar(value="translation")
        self.cmp_other_both = tk.BooleanVar(value=False)
        self.cmp_other_accent = tk.BooleanVar(value=False)
        for side, label, mode, both, accent in (
                ("left", "Current pack preview:", self.cmp_mine_mode,
                 self.cmp_mine_both, self.cmp_mine_accent),
                ("right", "Other pack preview:", self.cmp_other_mode,
                 self.cmp_other_both, self.cmp_other_accent)):
            grp = ttk.Frame(ctrl_row)
            grp.pack(side=side)
            ttk.Label(grp, text=label, font=FONT_UI_SM,
                      foreground=_theme.TH_FG_MUTED).pack(side="left")
            ttk.Radiobutton(grp, text="Translation", variable=mode,
                            value="translation",
                            command=self._cmp_rebuild_previews).pack(
                side="left", padx=(6, 2))
            ttk.Radiobutton(grp, text="Source", variable=mode, value="source",
                            command=self._cmp_rebuild_previews).pack(
                side="left", padx=(0, 2))
            ttk.Checkbutton(grp, text="Both", variable=both,
                            command=self._cmp_rebuild_previews).pack(
                side="left", padx=(4, 0))
            ttk.Checkbutton(grp, text="Accent font", variable=accent,
                            command=self._cmp_show_detail).pack(
                side="left", padx=(8, 0))
            if side == "left":
                # the editor's own "Box rows" switch: a dialogue line
                # previews its whole box here too
                ttk.Checkbutton(grp, text="Box rows", variable=self.multi_var,
                                command=self._on_multi_toggle).pack(
                    side="left", padx=(8, 0))

        # Canvas row - dynamically rebuilt by _cmp_rebuild_previews; takes
        # whatever height the split gives the lower section
        self._cmp_drow = ttk.Frame(lower)
        self._cmp_drow.pack(side="top", fill="both", expand=True)
        self._cmp_pv_canvases = {}
        self._cmp_rebuild_previews()

        self._cmp_bind_keys(parent.winfo_toplevel())
        self._cmp_paint_diff_pane()
        return f

    def _cmp_make_pane(self, panes, side):
        """One side of the diff: file header + Treeview + its own h-scroll.
        The vertical scrollbar is shared (see _cmp_yview)."""
        host = ttk.Frame(panes)
        panes.add(host, weight=1)
        host.rowconfigure(1, weight=1)
        host.columnconfigure(0, weight=1)
        head = ttk.Label(host, text="no pack loaded", font=FONT_UI_SM_B,
                         anchor="w", padding=(4, 2))
        head.grid(row=0, column=0, sticky="ew")
        cols = self.CMP_LEFT_COLS if side == "left" else self.CMP_RIGHT_COLS
        tv = ttk.Treeview(host, columns=[c for c, _t, _w in cols],
                          show="headings", height=10)
        for c, t, w in cols:
            tv.heading(c, text=t)
            tv.column(c, width=w, stretch=c in self.CMP_STRETCH,
                      anchor="center" if c in ("st", "lvl", "note", "onote")
                      else "e" if c in ("bm", "bo") else "w")
        hs = ttk.Scrollbar(host, orient="horizontal", command=tv.xview)
        tv.configure(xscrollcommand=hs.set)
        tv.grid(row=1, column=0, sticky="nsew")
        hs.grid(row=2, column=0, sticky="ew")
        if side == "left":
            self.l_cmp_left = head
        else:
            self.l_cmp_right = head
        tv.bind("<Double-Button-1>", lambda e: self.jump_from_compare())
        tv.bind("<Alt-Double-Button-1>",
                lambda e, s=side: self._cmp_alt_dbl(e, s))
        tv.bind("<<TreeviewSelect>>",
                lambda e, s=side: self._cmp_on_select(s))
        tv.bind("<Control-c>", lambda e, s=side: self._cmp_on_copy_cell(e, s))
        # ahead of the Treeview class's own <Up>/<Down>, which would move
        # the selection one row before the jump
        tv.bind("<Alt-Down>", lambda e: self.cmp_goto_diff(1) or "break")
        tv.bind("<Alt-Up>", lambda e: self.cmp_goto_diff(-1) or "break")
        TreeRowTip(tv, lambda iid, s=side: self._cmp_row_tip(iid, s))
        return tv

    def _build_compare_menu(self, win):
        """The compare window's own menu bar (File / Compare)."""
        m = tk.Menu(win)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label="Open 2nd pack...", command=self.open_compare_pack)
        fm.add_command(label="Save pack (mine)", accelerator="Ctrl+S",
                       command=lambda: self.save_pack(ask=True))
        fm.add_command(label="Save pack as...", accelerator="Ctrl+Shift+S",
                       command=self.save_pack_as)
        fm.add_separator()
        fm.add_command(label="Close comparison", command=self.close_compare)
        fm.add_command(label="Close window", command=win.withdraw)
        m.add_cascade(label="File", menu=fm)
        cm = tk.Menu(m, tearoff=0)
        self._fill_compare_menu(cm, in_window=True)
        m.add_cascade(label="Compare", menu=cm)
        self._cmp_menubar = Menubar(win, m)

    def _fill_compare_menu(self, cm, in_window=False):
        """Compare-menu items, shared by the main menu bar and the compare
        window's own."""
        if not in_window:
            cm.add_command(label="Open 2nd pack...",
                           command=self.open_compare_pack)
            cm.add_command(label="Show compare window",
                           command=lambda: self.open_tool("compare"))
            cm.add_separator()
        cm.add_command(label="First difference",
                       command=lambda: self.cmp_goto_diff("first"))
        cm.add_command(label="Previous difference", accelerator="Alt+Up",
                       command=lambda: self.cmp_goto_diff(-1))
        cm.add_command(label="Next difference", accelerator="Alt+Down",
                       command=lambda: self.cmp_goto_diff(1))
        cm.add_command(label="Last difference",
                       command=lambda: self.cmp_goto_diff("last"))
        cm.add_separator()
        cm.add_command(label="Jump to entry (editor)",
                       command=self.jump_from_compare)
        cm.add_command(label="Adopt OTHER -> MINE (selected)",
                       command=self.adopt_other_selected)
        cm.add_command(label="Adopt OTHER -> MINE (all shown, certain only)",
                       command=self.adopt_other_all)
        cm.add_separator()
        cm.add_command(label="Notes of the selected entry...",
                       accelerator="Alt+Double-click",
                       command=self._cmp_open_notes)
        if not in_window:
            cm.add_separator()
            cm.add_command(label="Close comparison",
                           command=self.close_compare)

    def _cmp_bind_keys(self, win):
        # the main window's root bindings do not reach a Toplevel
        win.bind("<Alt-Down>", lambda e: self.cmp_goto_diff(1) or "break")
        win.bind("<Alt-Up>", lambda e: self.cmp_goto_diff(-1) or "break")
        win.bind("<Control-s>", lambda e: self.save_pack(ask=True))
        win.bind("<Control-S>", lambda e: self.save_pack_as())
        win.bind("<Control-Shift-S>", lambda e: self.save_pack_as())

    # -- loading + pairing (worker thread) -----------------------------------
    def open_compare_pack(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
                title="Open second pack to compare",
                filetypes=[("YAML pack", "*.yaml *.yml"), ("All files", "*.*")])
        if not path:
            return
        self.open_tool("compare")
        self._cmp_start(path)

    def refresh_compare(self):
        """Re-pair MINE against the open second pack (no reload)."""
        if self.other is None:
            self._cmp_clear()
            return
        self._cmp_start(None)

    def _cmp_start(self, path):
        """Load `path` (when given) and pair it with MINE on a worker thread.

        The pairing of two unrelated packs (say English against romaji
        Japanese) used to run on the Tk thread and froze the program for
        minutes; now the window shows a spinner and stays responsive, and a
        newer request simply supersedes a running one."""
        self._cmp_gen += 1
        gen = self._cmp_gen
        mine_flat = list(self.pack.flat)
        mine_snap = pairing.snapshot(mine_flat)
        other = self.other
        out = {}
        name = os.path.basename(path or self.other_path or "")
        self._cmp_busy = True
        self._cmp_show_overlay("Loading pack" if path else "Pairing entries",
                               name)

        def work():
            try:
                o = other
                if path is not None:
                    o = Pack()
                    o.load(path)
                    out["other"] = o
                o_flat = list(o.flat)
                res = pairing.match(mine_snap, pairing.snapshot(o_flat),
                                    cancelled=lambda: gen != self._cmp_gen)
                if res is None:
                    return
                pairs, unused = res
                rows = []
                for i, oi, level, ev in pairs:
                    rows.append(self._cmp_pair_row(
                        level, ev, (i,) + mine_flat[i],
                        (oi,) + o_flat[oi] if oi is not None else None))
                for oi in unused:
                    rows.append(self._cmp_pair_row(
                        "none", [], None, (oi,) + o_flat[oi]))
                out["rows"] = rows
                out["oflat"] = o_flat
            except Exception as e:              # noqa: BLE001 - shown to user
                out["err"] = e

        th = threading.Thread(target=work, daemon=True)
        th.start()
        self.root.after(40, lambda: self._cmp_poll(th, gen, path, out))

    def _cmp_poll(self, th, gen, path, out):
        if th.is_alive():
            self.root.after(40, lambda: self._cmp_poll(th, gen, path, out))
            return
        if gen != self._cmp_gen:
            return                   # superseded; the newer run finishes up
        self._cmp_busy = False
        self._cmp_hide_overlay()
        if "err" in out:
            messagebox.showerror("Compare", str(out["err"]),
                                 parent=self.compare_win)
            return
        if "rows" not in out:
            return
        if path is not None:
            self.other = out["other"]
            self.other_path = path
            self.cmp_other_accent.set(needs_accent_font(self.other.header))
        # MINE's side follows the editor's accent switch, which pack loading
        # already sets from MINE's language
        self.cmp_mine_accent.set(bool(self.accent_font_var.get())
                                 or needs_accent_font(self.pack.header))
        self._cmp_other_flat = out["oflat"]
        self.cmp = out["rows"]
        self._cmp_update_labels()
        self._cmp_apply_filter()

    def _cmp_show_overlay(self, title, detail):
        self._cmp_hide_overlay()
        try:
            self._cmp_overlay = BusyOverlay(self.compare_win, title, detail)
        except tk.TclError:
            self._cmp_overlay = None

    def _cmp_hide_overlay(self):
        ov, self._cmp_overlay = getattr(self, "_cmp_overlay", None), None
        if ov is not None:
            ov.close()

    def close_compare(self):
        self._cmp_gen += 1            # drop any pairing still running
        self._cmp_busy = False
        self._cmp_hide_overlay()
        self.other = None
        self.other_path = None
        self._cmp_clear()

    def _cmp_clear(self):
        self._cmp_other_flat = []
        self.cmp = []
        self._cmp_update_labels()
        self._cmp_apply_filter()

    def _cmp_update_labels(self):
        """Pane headers: MINE = the pack loaded as the main table, OTHER =
        the 2nd pack the compare window is pointed at."""
        try:
            left = (os.path.basename(self.pack.path) if getattr(
                self.pack, "path", None) else "no pack loaded")
        except Exception:
            left = "no pack loaded"
        right = (os.path.basename(self.other_path)
                 if self.other_path else "no pack loaded")
        if self.l_cmp_left.winfo_exists():
            self.l_cmp_left.configure(text="MINE  -  " + left)
        if self.l_cmp_right.winfo_exists():
            self.l_cmp_right.configure(text="OTHER (read-only)  -  " + right)

    def _other_flat(self):
        other = self.other
        if other is None:
            return []
        return list(other.flat)

    # -- pairing: certainty levels + evidence ------------------------------
    # DIRECT needs identity beyond question (same uuid / key, or the exact
    # source inside the same section).  A normalised-source match is STRONG
    # in the same section and WEAK across renamed sections; a similar
    # source sharing a context is a WEAK candidate.  Everything uncertain
    # stays a SUGGESTION: adopt-all never merges weak pairs, and the row
    # tooltip shows the evidence so the user verifies before adopting.
    # The engine itself is core/pairing.py (thread-safe, no Tk).

    _cmp_norm = staticmethod(pairing.norm)

    @staticmethod
    def _cmp_bs(tr, entry):
        b, _ = parse_text(tr)
        sb, _ = parse_text(entry.get("source", ""))
        return b, int(entry.get("budget", sb))

    def _cmp_pair_row(self, level, ev, mine, oth):
        """Build one compare row from a (mine, other) pair; either side may
        be None for an only-in-one-pack entry."""
        i = sec = e = None
        if mine is not None:
            i, sec, e = mine
        oi = osec = oe = None
        if oth is not None:
            oi, osec, oe = oth
        if e is not None and oe is not None:
            mtr = e.get("translation", "")
            otr = oe.get("translation", "")
            st = "=" if mtr == otr else "!"
        elif e is not None:
            mtr, otr, st = e.get("translation", ""), "", ">"
        else:
            mtr, otr, st = "", oe.get("translation", ""), "<"
        mb = mbud = ob = obud = 0
        if e is not None:
            mb, mbud = self._cmp_bs(mtr, e)
        if oe is not None:
            ob, obud = self._cmp_bs(otr, oe)
        keym = e.get("key", "") if e is not None else \
            (oe.get("key", "") if oe is not None else "")
        keyo = oe.get("key", "") if oe is not None else ""
        src = e.get("source", "") if e is not None else \
            (oe.get("source", "") if oe is not None else "")
        ctx = e.get("context", "") if e is not None else \
            (oe.get("context", "") if oe is not None else "")
        osrc = oe.get("source", "") if oe is not None else ""
        return [st, level, ev, keym, keyo,
                sec if sec is not None else osec, src, ctx,
                mtr, otr, mb, mbud, ob, obud, i, oi, osrc]

    def _cmp_match_rows(self):
        """Every compare row for MINE against the open second pack, built
        synchronously (the window itself pairs on a worker thread)."""
        mine_flat = list(self.pack.flat)
        o_flat = self._other_flat()
        pairs, unused = pairing.match(pairing.snapshot(mine_flat),
                                      pairing.snapshot(o_flat))
        rows = [self._cmp_pair_row(level, ev, (i,) + mine_flat[i],
                                   (oi,) + o_flat[oi] if oi is not None
                                   else None)
                for i, oi, level, ev in pairs]
        rows += [self._cmp_pair_row("none", [], None, (oi,) + o_flat[oi])
                 for oi in unused]
        return rows

    def _cmp_allowed(self, row, filt):
        st, level = row[CMP_ST], row[CMP_LEVEL]
        mtr, otr = row[CMP_MTR], row[CMP_OTR]
        if filt == "Differences":
            return st == "!"
        if filt == "Source differs":
            return self._cmp_src_differs(row)
        if filt == "Candidates (review)":
            return st == "!" and level in ("strong", "weak")
        if filt == "Mine empty, other filled":
            return st == "!" and not mtr and bool(otr)
        if filt == "Only in mine":
            return st == ">"
        if filt == "Only in other":
            return st == "<"
        if filt == "Same":
            return st == "="
        return True

    # -- row display -------------------------------------------------------
    def _cmp_mine_entry(self, row):
        mi = row[CMP_MI]
        if mi is None or mi >= len(self.pack.flat):
            return None, None
        return self.pack.flat[mi]

    def _cmp_other_entry(self, row):
        oi = row[CMP_OI]
        flat = self._cmp_other_flat
        if oi is None or oi >= len(flat):
            return None, None
        return flat[oi]

    def _cmp_values(self, row):
        """(left pane values, right pane values) for one row; the side an
        entry is missing from shows an empty gap, as in WinMerge."""
        sec, e = self._cmp_mine_entry(row)
        if e is not None:
            left = (row[CMP_ST], row[CMP_LEVEL] if row[CMP_ST] != ">" else "",
                    NOTE_MARK if e.get("notes") else "",
                    e.get("key", ""), sec, e.get("context", ""),
                    e.get("source", ""), row[CMP_MTR],
                    "%d/%d" % (row[CMP_MB], row[CMP_MBUD]))
        else:
            left = (row[CMP_ST], "", "", "", "", "", "", "", "")
        osec, oe = self._cmp_other_entry(row)
        if oe is not None:
            right = (NOTE_MARK if oe.get("notes") else "",
                     oe.get("key", ""), osec, oe.get("context", ""),
                     oe.get("source", ""), row[CMP_OTR],
                     "%d/%d" % (row[CMP_OB], row[CMP_OBUD]))
        else:
            right = ("",) * len(self.CMP_RIGHT_COLS)
        return left, right

    @staticmethod
    def _cmp_src_differs(row):
        """A paired row whose two sources are not byte-identical - what a
        diff of two source exports (empty translations) is about."""
        return (row[CMP_MI] is not None and row[CMP_OI] is not None
                and row[CMP_SRC] != row[CMP_OSRC])

    def _cmp_tag(self, row):
        st, level = row[CMP_ST], row[CMP_LEVEL]
        if st == ">":
            return "mine"
        if st == "<":
            return "other"
        if st == "=":
            return "srcdiff" if self._cmp_src_differs(row) else "same"
        if not row[CMP_MTR] and row[CMP_OTR]:
            return "mineuf"
        if level == "strong":
            return "strong"
        if level == "weak":
            return "weak"
        return "diff"

    def _cmp_side_tags(self, row):
        """Tag for the left and the right pane: a one-sided row is tinted
        where the entry is and greyed where it is missing."""
        t = self._cmp_tag(row)
        if t == "mine":
            return "solo_m", "gap"
        if t == "other":
            return "gap", "solo_o"
        return t, t

    def _cmp_palette(self):
        """Row backgrounds (and location-bar marks) from the live theme, so
        every pair state stays readable in every scheme: tinted amber = a
        certain difference, blue = a strong candidate, red = a weak
        candidate to review, green = something only MINE has / MINE can
        import, grey = the gap where a side has no entry."""
        bg = _theme.TH_TREE_BG
        return {
            "diff": mix(bg, _theme.TH_WARN, 0.20),
            "srcdiff": mix(bg, _theme.TH_OVERDRAW_SRC, 0.11),
            "strong": mix(bg, _theme.TH_ACCENT, 0.18),
            "weak": mix(bg, _theme.TH_BAD, 0.16),
            "mineuf": mix(bg, _theme.TH_OK, 0.20),
            "solo_m": mix(bg, _theme.TH_OK, 0.16),
            "solo_o": mix(bg, _theme.TH_BAD, 0.14),
            "gap": mix(bg, _theme.TH_FG_FAINT, 0.38),
        }

    def _cmp_apply_tags(self):
        pal = self._cmp_palette()
        for t in (self.cmp_tree, getattr(self, "cmp_tree_r", None)):
            if t is None:
                continue
            t.tag_configure("same", foreground=_theme.TH_FG_FAINT)
            for name, bgc in pal.items():
                t.tag_configure(name, background=bgc, foreground=_theme.TH_FG)
            t.tag_configure("mineuf", font=FONT_MONO_B)
        try:
            self.cmp_loc.configure(bg=_theme.TH_TREE_BG,
                                   highlightbackground=_theme.TH_BORDER)
            self._cmp_paint_diff_pane()
            self._cmp_draw_location()
        except (AttributeError, tk.TclError):
            pass

    def _cmp_row_tip(self, iid, side):
        """Row tooltip: the entry's notes (when it has any) and, on the left,
        the pairing evidence."""
        pos = self.cmp_iid.get(iid)
        if pos is None or pos >= len(self.cmp_view):
            return None
        row = self.cmp_view[pos]
        parts = []
        if side == "left":
            _s, e = self._cmp_mine_entry(row)
            if row[CMP_ST] in ("=", "!") and row[CMP_LEVEL] != "none":
                parts.append("Paired %s: %s" % (
                    row[CMP_LEVEL], ", ".join(row[CMP_EV]) or "-"))
        else:
            _s, e = self._cmp_other_entry(row)
        note = (e or {}).get("notes") if e is not None else None
        if note:
            parts.append("Notes:\n%s" % note)
            if side == "left":
                parts.append("(Alt+double-click: open in the Notes dashboard)")
        return "\n\n".join(parts) if parts else None

    # -- filling the panes ---------------------------------------------------
    def _cmp_apply_filter(self):
        """Show the rows the 'Show:' filter allows (no re-pairing)."""
        self.cmp_cellsel.clear()
        self.cmp_cellsel_r.clear()
        for t in (self.cmp_tree, self.cmp_tree_r):
            t.delete(*t.get_children())
        self.cmp_iid = {}
        self.cmp_pos_iid = {}
        filt = self.cmp_cb.get() or "All"
        self.cmp_view = [r for r in self.cmp if self._cmp_allowed(r, filt)]
        self._cmp_plan = self.cmp_view
        self._cmp_diff_pos = self._cmp_find_diffs()
        self._cmp_ins_gen = getattr(self, "_cmp_ins_gen", 0) + 1
        self.update_cmp_summary()
        self._cmp_draw_location()
        self._insert_cmp_rows(0, self._cmp_ins_gen)
        self._cmp_show_detail()

    def _cmp_find_diffs(self):
        """Positions in the view that Next/Prev difference stops at and the
        location bar marks: every row that is not an identical pair (a
        differing source counts, so two source exports diff usefully)."""
        return [p for p, r in enumerate(self.cmp_view)
                if r[CMP_ST] != "=" or self._cmp_src_differs(r)]

    def update_cmp_summary(self):
        if not self.other:
            self.l_cmp_sum.configure(text="")
            self.l_cmp_pos.configure(text="")
            return
        rows = self.cmp
        d = {"=": 0, "!": 0, ">": 0, "<": 0}
        lv = {"direct": 0, "strong": 0, "weak": 0}
        for r in rows:
            d[r[CMP_ST]] += 1
            if r[CMP_ST] == "!" and r[CMP_LEVEL] in lv:
                lv[r[CMP_LEVEL]] += 1
        imp = sum(1 for r in rows
                  if r[CMP_ST] == "!" and not r[CMP_MTR] and r[CMP_OTR])
        sd = sum(1 for r in rows if self._cmp_src_differs(r))
        self.l_cmp_sum.configure(
            text="%d shown | %d rows | same %d differ %d source-differs %d "
                 "mine-only %d other-only %d importable %d | direct %d "
                 "strong %d weak %d"
                 % (len(self.cmp_view), len(rows), d["="], d["!"], sd,
                    d[">"], d["<"], imp, lv["direct"], lv["strong"],
                    lv["weak"]))
        self._cmp_update_pos_label()

    def _insert_cmp_rows(self, k, gen):
        if gen != self._cmp_ins_gen:
            return
        plan = self._cmp_plan
        CHUNK = 900
        end = min(k + CHUNK, len(plan))
        for pos in range(k, end):
            self._cmp_insert_row(pos)
        if end < len(plan):
            self.root.after_idle(lambda: self._insert_cmp_rows(end, gen))
        else:
            self.update_cmp_summary()
            self._cmp_draw_location()

    def _cmp_insert_row(self, pos):
        row = self.cmp_view[pos]
        left, right = self._cmp_values(row)
        lt, rt = self._cmp_side_tags(row)
        iid = "r%d" % pos
        self.cmp_tree.insert("", "end", iid=iid, values=left, tags=(lt,))
        self.cmp_tree_r.insert("", "end", iid=iid, values=right, tags=(rt,))
        self.cmp_iid[iid] = pos
        self.cmp_pos_iid[pos] = iid

    def _cmp_update_cell(self, pos):
        iid = self.cmp_pos_iid.get(pos)
        if iid is None:
            return
        row = self.cmp_view[pos]
        left, right = self._cmp_values(row)
        lt, rt = self._cmp_side_tags(row)
        self.cmp_tree.item(iid, values=left, tags=(lt,))
        self.cmp_tree_r.item(iid, values=right, tags=(rt,))

    def refresh_cmp_cells(self):
        for iid, pos in list(self.cmp_iid.items()):
            self._cmp_update_cell(pos)
        self._cmp_diff_pos = self._cmp_find_diffs()
        self._cmp_draw_location()
        self._cmp_update_pos_label()

    # -- the panes move together -------------------------------------------
    def _cmp_yview(self, *args):
        self.cmp_tree.yview(*args)
        self.cmp_tree_r.yview(*args)

    def _cmp_on_yscroll(self, side, first, last):
        """One pane scrolled (wheel, keys, see()): follow with the other."""
        self._cmp_vs.set(first, last)
        other = self.cmp_tree_r if side == "left" else self.cmp_tree
        try:
            if abs(other.yview()[0] - float(first)) > 1e-9:
                other.yview_moveto(first)
        except tk.TclError:
            pass
        self._cmp_draw_viewport()

    def _cmp_on_select(self, side):
        src = self.cmp_tree if side == "left" else self.cmp_tree_r
        dst = self.cmp_tree_r if side == "left" else self.cmp_tree
        sel = src.selection()
        if tuple(dst.selection()) != tuple(sel):
            dst.selection_set(sel)
        foc = src.focus()
        if foc and dst.focus() != foc:
            dst.focus(foc)
        self._cmp_update_pos_label()
        # both panes report the same change; draw once
        if self._cmp_detail_job is None:
            self._cmp_detail_job = self.root.after_idle(self._cmp_detail_now)

    def _cmp_detail_now(self):
        self._cmp_detail_job = None
        self._cmp_show_detail()

    # -- location bar (WinMerge's location pane) ---------------------------
    def _cmp_loc_marks(self, row):
        """(left colour, right colour) of a row in the location bar, None for
        an identical pair."""
        t = self._cmp_tag(row)
        if t == "same":
            return None
        pal = self._cmp_palette_strong()
        if t == "mine":
            return pal["mine"], pal["gap"]
        if t == "other":
            return pal["gap"], pal["other"]
        return pal[t], pal[t]

    @staticmethod
    def _cmp_palette_strong():
        return {"diff": _theme.TH_WARN, "srcdiff": _theme.TH_OVERDRAW_SRC,
                "strong": _theme.TH_ACCENT,
                "weak": _theme.TH_BAD, "mineuf": _theme.TH_OK,
                "mine": _theme.TH_OK, "other": _theme.TH_BAD,
                "gap": _theme.TH_FG_FAINT}

    _LOC_RANK = {"srcdiff": 1, "diff": 2, "strong": 3, "mineuf": 4,
                 "weak": 5, "mine": 2, "other": 2}

    def _cmp_draw_location(self):
        cv = getattr(self, "cmp_loc", None)
        if cv is None:
            return
        try:
            cv.delete("all")
            h = cv.winfo_height() - 4
            w = cv.winfo_width() - 2
        except tk.TclError:
            return
        n = len(self.cmp_view)
        if n == 0 or h < 4:
            return
        # one cell per pixel row: the most important mark landing on it
        cell = [None] * h
        rank = [0] * h
        for pos in self._cmp_diff_pos:
            if pos >= n:
                continue
            row = self.cmp_view[pos]
            marks = self._cmp_loc_marks(row)
            if marks is None:
                continue
            rk = self._LOC_RANK.get(self._cmp_tag(row), 1)
            y0 = pos * h // n
            y1 = max(y0 + 1, (pos + 1) * h // n)
            for y in range(y0, min(y1, h)):
                if rk >= rank[y]:
                    cell[y], rank[y] = marks, rk
        half = 2 + (w - 2) // 2
        y = 0
        while y < h:
            m = cell[y]
            y2 = y + 1
            while y2 < h and cell[y2] == m:
                y2 += 1
            if m is not None:
                cv.create_rectangle(2, 2 + y, half, 2 + y2, fill=m[0],
                                    outline="")
                cv.create_rectangle(half, 2 + y, w, 2 + y2, fill=m[1],
                                    outline="")
            y = y2
        self._cmp_draw_viewport()

    def _cmp_draw_viewport(self):
        cv = getattr(self, "cmp_loc", None)
        if cv is None:
            return
        try:
            cv.delete("vp")
            if not self.cmp_view:
                return
            first, last = self.cmp_tree.yview()
            h = cv.winfo_height() - 4
            w = cv.winfo_width() - 1
            cv.create_rectangle(1, 2 + first * h, w, 2 + max(last * h,
                                                              first * h + 3),
                                outline=_theme.TH_FG, width=1, tags=("vp",))
        except tk.TclError:
            pass

    def _cmp_loc_click(self, evt):
        if not self.cmp_view:
            return
        h = max(1, self.cmp_loc.winfo_height() - 4)
        frac = min(1.0, max(0.0, (evt.y - 2) / float(h)))
        first, last = self.cmp_tree.yview()
        self.cmp_tree.yview_moveto(max(0.0, frac - (last - first) / 2))

    # -- difference navigation ---------------------------------------------
    def _cmp_cur_pos(self):
        iid = self.cmp_tree.focus() or next(iter(self.cmp_tree.selection()),
                                            None)
        return self.cmp_iid.get(iid) if iid else None

    def cmp_goto_diff(self, where):
        """Select the next (+1) / previous (-1) / "first" / "last" row that
        differs, like WinMerge's Alt+Down / Alt+Up."""
        if not self.other:
            self.open_tool("compare")
            return None
        diffs = self._cmp_diff_pos
        if not diffs:
            self._cmp_update_pos_label("no differences in this view")
            return None
        cur = self._cmp_cur_pos()
        if where == "first":
            target = diffs[0]
        elif where == "last":
            target = diffs[-1]
        elif cur is None:
            target = diffs[0] if where == 1 else diffs[-1]
        elif where == 1:
            k = bisect.bisect_right(diffs, cur)
            target = diffs[k] if k < len(diffs) else None
        else:
            k = bisect.bisect_left(diffs, cur) - 1
            target = diffs[k] if k >= 0 else None
        if target is None:
            self._cmp_update_pos_label("no more differences %s"
                                       % ("below" if where == 1 else "above"))
            return None
        iid = self.cmp_pos_iid.get(target)
        if iid is None:              # still being inserted
            return None
        self.cmp_tree.selection_set(iid)
        self.cmp_tree.focus(iid)
        self.cmp_tree.see(iid)
        self.cmp_tree.focus_set()
        return None

    def _cmp_update_pos_label(self, msg=None):
        lab = getattr(self, "l_cmp_pos", None)
        if lab is None:
            return
        if msg:
            lab.configure(text=msg)
            return
        diffs = self._cmp_diff_pos
        if not self.other:
            lab.configure(text="")
            return
        cur = self._cmp_cur_pos()
        k = bisect.bisect_left(diffs, cur) if cur is not None else -1
        if cur is not None and k < len(diffs) and diffs[k] == cur:
            lab.configure(text="difference %d of %d" % (k + 1, len(diffs)))
        else:
            lab.configure(text="%d difference%s in view" % (
                len(diffs), "" if len(diffs) == 1 else "s"))

    # -- diff pane -----------------------------------------------------------
    def _cmp_paint_diff_pane(self):
        t = getattr(self, "cmp_diff", None)
        if t is None:
            return
        t.configure(bg=_theme.TH_FIELD_BG, fg=_theme.TH_FG,
                    highlightbackground=_theme.TH_BORDER,
                    insertbackground=_theme.TH_FG,
                    selectbackground=_theme.TH_SEL_BG,
                    selectforeground=_theme.TH_SEL_FG)
        t.tag_configure("lab", foreground=_theme.TH_FG_MUTED)
        t.tag_configure("chg", background=mix(_theme.TH_FIELD_BG,
                                              _theme.TH_WARN, 0.38))
        t.tag_configure("gap", foreground=_theme.TH_FG_FAINT)

    @staticmethod
    def _cmp_diff_key(evt):
        # read-only, but selectable / copyable
        if evt.keysym in ("Left", "Right", "Up", "Down", "Home", "End",
                          "Prior", "Next") or (evt.state & 0x4 and
                                               evt.keysym.lower() in ("c", "a")):
            return None
        return "break"

    def _cmp_fill_diff_pane(self, row):
        t = self.cmp_diff
        t.delete("1.0", "end")
        if row is None:
            t.insert("end", "Select a row to see what differs.", "gap")
            return
        has_m = row[CMP_MI] is not None
        has_o = row[CMP_OI] is not None
        lines = (
            ("Mine  translation  ", row[CMP_MTR], row[CMP_OTR], has_m, has_o),
            ("Other translation  ", row[CMP_OTR], row[CMP_MTR], has_o, has_m),
            ("Mine  source       ", row[CMP_SRC] if has_m else "",
             row[CMP_OSRC], has_m, has_o),
            ("Other source       ", row[CMP_OSRC] if has_o else "",
             row[CMP_SRC] if has_m else "", has_o, has_m),
        )
        for n, (lab, a, b, here, there) in enumerate(lines):
            if n:
                t.insert("end", "\n")
            t.insert("end", lab, "lab")
            if not here:
                t.insert("end", "(no entry on this side)", "gap")
                continue
            if not there or a == b:
                t.insert("end", a)
                continue
            sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
            for op, i1, i2, _j1, _j2 in sm.get_opcodes():
                if i1 == i2:
                    continue
                t.insert("end", a[i1:i2], () if op == "equal" else "chg")

    # ---- dynamic preview panel helpers -------------------------------------

    def _make_cmp_canvas(self, parent, label):
        """Create one labelled, scrollable preview canvas inside `parent`."""
        f = ttk.Frame(parent)
        ttk.Label(f, text=label, font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).pack(anchor="w")
        host = ttk.Frame(f)
        host.pack(fill="both", expand=True)
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        # a small requested size: the panels share the row evenly however
        # many there are, and _cmp_show_detail sets the height to the text
        cv = tk.Canvas(host, highlightthickness=0, bg=_theme.BG_EDIT,
                       width=120, height=80)
        vs = ttk.Scrollbar(host, orient="vertical", command=cv.yview)
        hs = ttk.Scrollbar(host, orient="horizontal", command=cv.xview)
        cv.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        cv.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        return f, cv

    def _cmp_rebuild_previews(self, _evt=None):
        """Destroy and recreate the canvas panels based on current checkbox state.

        Left side (current pack, like the left pane) - cmp_mine_mode +
        cmp_mine_both; right side (other pack) - cmp_other_mode +
        cmp_other_both, each:
          • both=OFF, mode=translation  → 1 canvas: other-translation
          • both=OFF, mode=source       → 1 canvas: other-source
          • both=ON                     → 2 canvases: other-source | other-translation

        Total: 2 / 3 / 3 / 4 panels depending on state.
        """
        drow = getattr(self, "_cmp_drow", None)
        if drow is None:
            return
        for w in drow.winfo_children():
            w.destroy()
        self._cmp_pv_canvases = {}

        other_both = getattr(self, "cmp_other_both",
                             tk.BooleanVar(value=False)).get()
        mode = getattr(self, "cmp_other_mode",
                       tk.StringVar(value="translation")).get()
        mine_both = getattr(self, "cmp_mine_both",
                            tk.BooleanVar(value=False)).get()
        mine_mode = getattr(self, "cmp_mine_mode",
                            tk.StringVar(value="translation")).get()

        slots = []   # (key, label), left to right - same sides as the panes
        if mine_both:
            slots.append(("mine_src", "Mine — Source"))
            slots.append(("mine_tr", "Mine — Translation"))
        elif mine_mode == "source":
            slots.append(("mine_src", "Mine — Source"))
        else:
            slots.append(("mine_tr", "Mine — Translation"))
        if other_both:
            slots.append(("other_src", "Other — Source"))
            slots.append(("other_tr", "Other — Translation"))
        elif mode == "source":
            slots.append(("other_src", "Other — Source"))
        else:
            slots.append(("other_tr", "Other — Translation"))

        for key, label in slots:
            fr, cv = self._make_cmp_canvas(drow, label)
            fr.pack(side="left", fill="both", expand=True, padx=(0, 4))
            self._cmp_pv_canvases[key] = cv

        # compat aliases used by old code that holds direct refs
        self.cmp_pv = self._cmp_pv_canvases.get("mine_tr")
        self.cmp_pv_other = self._cmp_pv_canvases.get("other_tr")
        self._cmp_show_detail()

    def _cmp_show_detail(self, _evt=None):
        """Render the selected compare row(s) into the diff pane and every
        active preview canvas.  Never touches the editor's own preview."""
        canvases = getattr(self, "_cmp_pv_canvases", {})
        for cv in canvases.values():
            try:
                cv.delete("all")
            except tk.TclError:
                pass
        rows, positions = self._cmp_preview_rows()
        if getattr(self, "cmp_diff", None) is not None:
            cur = self._cmp_cur_pos()
            focus = (self.cmp_view[cur] if cur is not None
                     and cur < len(self.cmp_view) else None)
            self._cmp_fill_diff_pane(focus or (rows[0] if rows else None))
        if not canvases or not rows:
            return
        row = rows[0]
        ctx = default_limit_context(row[CMP_SEC])
        lim = limit_for(ctx) if ctx else None
        meta = {}
        if lim:
            meta["limit"] = lim["context"]
            meta["glyph_pad"] = lim["glyph_pad"]
        jp = self.jp_font(2)
        # each side in its own pack's font: the accent font where that
        # pack's language needs it (set on load, switchable per side)
        accent = {"mine": self.cmp_mine_accent.get(),
                  "other": self.cmp_other_accent.get()}
        expander = self.markup_expander()
        # Map slot keys to row fields; every previewed row is one box row
        fields = {"other_tr": CMP_OTR, "other_src": CMP_OSRC,
                  "mine_tr": CMP_MTR, "mine_src": CMP_SRC}
        for key, cv in canvases.items():
            f = fields[key]
            texts = [r[f] if len(r) > f else "" for r in rows]
            if not any(texts):
                continue
            try:
                render_text_to_canvas(
                    cv, texts, meta, expander=expander,
                    scale=2, row_positions=positions,
                    accent_font=accent[key.split("_")[0]],
                    fallback_font=jp,
                    rf_config=getattr(self, "rf_config", None))
            except Exception:
                pass
        # the canvases take the height the split gives them; a taller box
        # scrolls

    CMP_PV_MAX_ROWS = 40

    def _cmp_first_sash(self, evt):
        """Once the window has its size: give the lower section ~40%."""
        if self._cmp_sash_set or evt.height < 300:
            return
        self._cmp_sash_set = True
        try:
            self._cmp_vpan.sashpos(0, int(evt.height * 0.58))
        except tk.TclError:
            pass

    def _cmp_preview_rows(self):
        """Compare rows to preview, in table order, plus their dialog-box
        row positions (None stacks them).

        Every selected row is previewed.  With "Box rows" on, a selected
        dialogue line brings in the rest of its box (paired through MINE)
        at the box's own row positions."""
        tree = getattr(self, "cmp_tree", None)
        if tree is None:
            return [], None
        picked = []
        for iid in sorted(tree.selection(), key=tree.index):
            pos = self.cmp_iid.get(iid)
            if pos is not None and pos < len(self.cmp_view):
                picked.append(self.cmp_view[pos])
        if not picked:
            return [], None
        multi = getattr(self, "multi_var", None)
        if multi is None or not multi.get() or self.pack is None:
            return picked[:self.CMP_PV_MAX_ROWS], None
        by_mine = {r[CMP_MI]: r for r in getattr(self, "cmp", [])
                   if r[CMP_MI] is not None}
        bmap = self.box_map()
        out, seen, positions = [], set(), []
        for r in picked:
            mi = r[CMP_MI]
            for j in (self.box_rows(mi) if mi is not None else [None]):
                rr = r if j is None or j == mi else by_mine.get(j)
                if rr is None or id(rr) in seen:
                    continue
                seen.add(id(rr))
                out.append(rr)
                positions.append(bmap[j][1] if j in bmap else None)
        out = out[:self.CMP_PV_MAX_ROWS]
        positions = positions[:len(out)]
        # positions describe ONE box; rows from several boxes (or rows that
        # are not dialogue) stack instead
        boxes = {bmap[r[CMP_MI]][0] for r in out if r[CMP_MI] in bmap}
        if len(boxes) != 1 or None in positions:
            positions = None
        return out, positions

    # ---- comparator cell-column copy helpers --------------------------------

    def _cmp_on_cells_picked(self, rows):
        """Ctrl+Clicked cells select their rows (which shows the active
        pair in the diff pane through <<TreeviewSelect>>)."""
        iid = (self.cmp_cellsel.last_row() or self.cmp_cellsel_r.last_row()
               or rows[-1])
        self.cmp_tree.selection_set(rows)
        self.cmp_tree.focus(iid)
        self.cmp_tree.see(iid)

    def _cmp_on_copy_cell(self, _evt=None, side="left"):
        """Ctrl+C on a pane: its Ctrl+Clicked cells when there are any,
        otherwise that side's translation of every selected row."""
        sel_cells = self.cmp_cellsel if side == "left" else self.cmp_cellsel_r
        tree = self.cmp_tree if side == "left" else self.cmp_tree_r
        col = "mine" if side == "left" else "other"
        if sel_cells.active():
            sel_cells.copy()
            return "break"
        sel = tree.selection()
        if not sel:
            return "break"
        rows = sorted(sel, key=tree.index)
        text = "\n".join(clean(tree.set(iid, col)) for iid in rows)
        if not text:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._push_clip_history(text, "cmp[%s] x%d" % (col, len(rows)))
        return "break"

    # -- notes --------------------------------------------------------------
    def _cmp_alt_dbl(self, evt, side):
        tree = self.cmp_tree if side == "left" else self.cmp_tree_r
        iid = tree.identify_row(evt.y)
        if iid:
            tree.selection_set(iid)
            tree.focus(iid)
        self._cmp_open_notes()
        return "break"

    def _cmp_open_notes(self):
        """Notes dashboard on the selected row's MINE entry."""
        pos = self._cmp_cur_pos()
        if pos is None or pos >= len(self.cmp_view):
            self.open_notes_dashboard()
            return
        mi = self.cmp_view[pos][CMP_MI]
        if mi is None:
            messagebox.showinfo(
                "Notes", "This entry exists only in the other pack; its "
                         "notes show in the row's tooltip.",
                parent=self.compare_win)
            return
        self.open_notes_dashboard(mi)

    # -- actions ------------------------------------------------------------
    def jump_from_compare(self):
        pos = self._cmp_cur_pos()
        if pos is None:
            messagebox.showinfo("Compare", "Select a compare row first.",
                                parent=self.compare_win)
            return
        row = self.cmp_view[pos]
        if row[CMP_MI] is None:
            messagebox.showinfo("Compare",
                                "This entry exists only in the other pack.",
                                parent=self.compare_win)
            return
        self.jump_to_flat(row[CMP_MI])

    def _cmp_adopt_rows(self, rows):
        """Copy OTHER's translation into MINE for each given pair.  Returns
        (cells, skipped, last_index) for the caller's history entry."""
        cells = []
        skipped = 0
        last = None
        for row in rows:
            i = row[CMP_MI]
            otr = row[CMP_OTR]
            if i is None or not otr or row[CMP_MTR] == otr:
                skipped += 1
                continue
            _, e = self.pack.flat[i]
            cells.append((i, e.get("translation", ""), otr))
            e["translation"] = otr
            self._own(e)
            row[CMP_MTR] = otr
            row[CMP_MB], row[CMP_MBUD] = self._cmp_bs(otr, e)
            row[CMP_ST] = "="
            last = i
        return cells, skipped, last

    def adopt_other_selected(self):
        if not self.other:
            messagebox.showinfo("Compare", "Open a second pack first.",
                                parent=self.compare_win)
            return
        sel = self.cmp_tree.selection()
        if not sel:
            messagebox.showinfo("Compare", "Select a compare row first.",
                                parent=self.compare_win)
            return
        rows = []
        for iid in sel:
            pos = self.cmp_iid.get(iid)
            if pos is not None:
                rows.append(self.cmp_view[pos])
        cells, _skipped, last = self._cmp_adopt_rows(rows)
        if not cells:
            messagebox.showinfo(
                "Compare", "The selected rows are already identical or "
                           "carry nothing to adopt.", parent=self.compare_win)
            return
        self.note_edit("Adopt", cells)
        self.dirty = True
        self.refresh_cmp_cells()
        self._cmp_show_detail()
        self.refresh_all_rows()
        self.invalidate_stats()
        self.update_status()
        if last is not None:
            self.jump_to_flat(last)
        messagebox.showinfo(
            "Compare",
            "Copied %d translation%s from the other pack to MINE."
            % (len(cells), "" if len(cells) == 1 else "s"),
            parent=self.compare_win)

    def adopt_other_all(self):
        """Adopt every shown pair the comparator is reasonably sure about.

        Direct and strong pairs merge in bulk; WEAK candidates never do -
        bulk-adopting a similarity would present a guess as a fact, so they
        stay in the 'Candidates (review)' filter for row-by-row adoption."""
        if not self.other:
            messagebox.showinfo("Compare", "Open a second pack first.",
                                parent=self.compare_win)
            return
        rows = [r for r in self.cmp_view
                if not (r[CMP_ST] == "!" and r[CMP_LEVEL] == "weak")]
        cells, _skipped, _last = self._cmp_adopt_rows(rows)
        self.note_edit("Adopt all", cells)
        if cells:
            self.dirty = True
            self.refresh_cmp_cells()
            self._cmp_show_detail()
            self.refresh_all_rows()
            self.invalidate_stats()
            self.update_status()
        messagebox.showinfo(
            "Compare", "Copied %d translation%s from the other pack to MINE."
            % (len(cells), "" if len(cells) == 1 else "s"),
            parent=self.compare_win)
