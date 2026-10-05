"""The GenesisLeaf main window: composes every feature mixin into `App`.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from genesisleaf.core.history import EditHistory
from genesisleaf.core.pack import Pack
from genesisleaf.ui.app.appearance import AppearanceMixin
from genesisleaf.ui.app.autofix import AutofixMixin
from genesisleaf.ui.app.cheatsheet import CheatsheetMixin
from genesisleaf.ui.app.clipboard import ClipboardMixin
from genesisleaf.ui.app.compare import CompareMixin
from genesisleaf.ui.app.duplicates import DuplicatesMixin
from genesisleaf.ui.app.editor import EditorMixin
from genesisleaf.ui.app.editor_dock import EditorDockMixin
from genesisleaf.ui.app.find_filter import FindFilterMixin
from genesisleaf.ui.app.float_preview import FloatPreviewMixin
from genesisleaf.ui.app.free_space import FreeSpaceMixin
from genesisleaf.ui.app.glossary import GlossaryMixin
from genesisleaf.ui.app.join import JoinMixin
from genesisleaf.ui.app.layout import LayoutMixin
from genesisleaf.ui.app.limits import LimitsMixin
from genesisleaf.ui.app.macros import MacroMixin
from genesisleaf.ui.app.menu import MenuMixin
from genesisleaf.ui.app.navigation import NavigationMixin
from genesisleaf.ui.app.navigator import NavigatorMixin
from genesisleaf.ui.app.notes import NotesMixin
from genesisleaf.ui.app.pack_io import PackIOMixin
from genesisleaf.ui.app.preview import PreviewMixin
from genesisleaf.ui.app.references import ReferencesMixin
from genesisleaf.ui.app.reports import ReportsMixin
from genesisleaf.ui.app.rom_builder import RomBuilderMixin
from genesisleaf.ui.app.search_tool import SearchToolMixin
from genesisleaf.ui.app.selection import SelectionMixin
from genesisleaf.ui.app.status import StatusMixin
from genesisleaf.ui.app.table import TableMixin
from genesisleaf.ui.app.token_bar import TokenBarMixin
from genesisleaf.ui.app.toolbar import ToolbarMixin
from genesisleaf.ui.app.undo import UndoMixin
from genesisleaf.ui.app.views import ViewsMixin
from genesisleaf.ui.app.workbench_link import WorkbenchLinkMixin
from genesisleaf.ui.fonts import font_family, init_fonts
from genesisleaf.ui import brand
from genesisleaf.version import APP_TITLE


class App(
        AppearanceMixin,
        MenuMixin,
        NavigatorMixin,
        ToolbarMixin,
        LayoutMixin,
        TableMixin,
        EditorDockMixin,
        StatusMixin,
        PackIOMixin,
        FreeSpaceMixin,
        FindFilterMixin,
        SelectionMixin,
        EditorMixin,
        JoinMixin,
        NavigationMixin,
        ClipboardMixin,
        UndoMixin,
        TokenBarMixin,
        MacroMixin,
        ReferencesMixin,
        PreviewMixin,
        FloatPreviewMixin,
        LimitsMixin,
        NotesMixin,
        SearchToolMixin,
        CheatsheetMixin,
        GlossaryMixin,
        AutofixMixin,
        DuplicatesMixin,
        CompareMixin,
        ReportsMixin,
        RomBuilderMixin,
        WorkbenchLinkMixin,
        ViewsMixin,
):
    """GenesisLeaf main window.

    Every feature lives in its own mixin (genesisleaf/ui/app/*.py); this
    class only owns the shared state set up in __init__ and the close
    handler.  See docs/FEATURE_MAP.md for how the mixins call each other.
    """

    def __init__(self, root):
        self.root = root
        init_fonts(root, font_family())
        self.pack = Pack()
        self.dirty = False
        self.current = -1
        self.view = []                 # flat indices currently listed
        self.view_iid = {}             # iid -> flat index
        self._iid_by_flat = {}         # flat index -> iid (the reverse, so the
                                       # per-keystroke row refresh is O(1)
                                       # rather than a scan of every row)
        self.filter_section = "All"
        self.filter_status = "All"
        self.filter_context = "All"
        self.filter_field = "Section"
        self.filter_value = "All"
        self._ctx_cache = None
        self._ctx_groups = {}
        self.filter_text = ""
        self.glossary = {}
        self.glossary_path = None
        self.notes = {}
        self.notes_path = None
        self._glossary_dirty = 0
        self._load_task = None
        self._search_job = None
        self._notes_job = None
        self._match_idx = {}
        self._loading = False
        self._loader = None              # BusyOverlay while a pack loads
        self._select_lock = False
        self._word_match_rows = None
        self._stats = None
        self._stats_job = None
        self._view_gen = 0
        self._sort_col = None
        self._sort_rev = False
        self._hdr = {}
        self.plan = []
        self._pos_iids = []
        self._cur_pal = 7
        self.ref_items = {}
        self.ref_spells = {}
        self.ref_arts = []
        self.ref_party = []
        self._space_est = None       # cached core.space.estimate()
        self.pat_conf = None         # build-test-ROM sidecar config
        self.relayout_var = tk.BooleanVar(value=False)
        self.dyn_var = tk.BooleanVar(value=True)   # real-glyph dock preview (on by default)
        self.dyn_size_var = tk.BooleanVar(value=False)  # dynamic-size preview: follows the editor's rows
        self.accent_font_var = tk.BooleanVar(value=False)  # accent font preview: draw accents from base + marks
        self.pv_scale = 2                 # pixel scale of the dock real-font preview
        self.jp_family = None             # CJK fallback family (MS Gothic default)
        self._jp_fonts = {}               # (family, scale) -> cached Tk font
        self.multi_var = tk.BooleanVar(value=True)  # split multi-row boxes per line
        self._ed_flat = []          # editor's row lines: one flat index per widget line
        self._ed_prev = []          # prior per-line display values, for write-back
        self.max_ed_lines = 10      # unchecked-mode editor cap (Options)
        self._join = {}             # unit source-signature -> [unit, ...] joined units
        self._join_unit_cache = None  # every multi-line unit, flat order
        self._band_of = {}          # tree iid -> the band tag it was drawn on
        self._band_state = {"unit": None, "n": 0}   # stripe flip, per rebuild
        self._edit_seq = {}         # id(entry) -> session edit order (in memory only)
        self._edit_clock = 0
        self._hist_pos = -1         # how far "Edited" has walked back
        self._views = []            # extra view windows on this pack
        self.macros = dict(self.DEFAULT_MACROS)
        self.find_scope = "All"
        self._join_skip = set()     # uuids the user chose to keep out of a join
        self._join_job = None       # pending debounced join, `after` handle
        self._join_pending = None   # flat index that job will propagate from
        self._find_hits = None      # (query, [flat idx, ...]) for Filter-off find
        self._search_ignore = False  # keep the Find text out of _filters once
        self.l_selcount = None     # "n selected" label beside Copy key
        self.l_clone = None        # "clone 3 of 447" label beside Next Clone
        self._row_clip = None       # list of translations copied from selected rows
        self._clip_hist = []        # clipboard history, newest first [(label, text)]
        self._clip_hist_win = None  # Options ▸ Clipboard history window, when open
        self.history = EditHistory()
        self._replaying = False     # set while undo/redo rewrites cells, so the
                                    # resulting <<Modified>> is not re-recorded
        self._edit_label = None     # names the step the next edit records as
        self._hist_window = None    # the Edit ▸ History window, when open
        self._box_map = None         # flat idx -> (box, row), dialog sections
        self._wb_refs = None         # {cN:arg} -> text, for markup expander
        self._pv_col_guide = 24      # dialog-box "col guide" reference column
        self.other = None            # second pack loaded for comparison
        self.other_path = None
        self.cmp = []
        self.cmp_view = []
        self.cmp_iid = {}
        self.cmp_pos_iid = {}
        self._cmp_plan = []
        self._cmp_gen = 0
        self._jump_data = None
        self._dyn_resize_job = None
        self.wb = None               # Translation workbench window, when open

        root.title(APP_TITLE)
        brand.apply_icon(root)
        root.geometry("1400x860")
        root.minsize(800, 600)
        self.style = ttk.Style(root)
        # "clam" is preferred because it is the one stock theme that honours
        # Treeview tag backgrounds, and the alternating unit bands depend on
        # that.  Fall back through the other available themes.
        for th in ("clam", "vista", "alt", "default"):
            try:
                self.style.theme_use(th)
                break
            except tk.TclError:
                continue
        # Stored preferences (theme, macros, scope) before anything reads them.
        self.restore_settings()
        self.apply_theme()

        self._build_menu()
        self._build_toolbar()
        # status bar before the body: pack gives earlier widgets priority,
        # so a small window squeezes the body, never the status bar
        self._build_statusbar()
        self._build_body()
        self._sync_relayout_var()
        self.apply_theme()          # the editors only exist now: colour them
        self._watch_new_windows()

        self.trans_tag_styles()
        self.bind_macros(self.tr_txt)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        path = sys.argv[1] if len(sys.argv) > 1 else None
        if path and os.path.exists(path):
            self.root.after(200, lambda: self.load_pack(path))
        else:
            self.root.after(200, lambda: self.load_pack(None))

    def on_close(self):
        if self.dirty:
            if not messagebox.askyesno("Unsaved changes",
                                       "The pack has unsaved edits. Close without saving?"):
                return
        if getattr(self, "_glossary_dirty", 0) and self.glossary_path:
            try:
                with open(self.glossary_path, "w", encoding="utf-8") as fh:
                    json.dump(self.glossary, fh, ensure_ascii=False, indent=2)
            except Exception:
                pass
        self._cancel_join()
        self._close_all_views()
        self.root.destroy()
