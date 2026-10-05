"""Credits, statistics, validation, progress window.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import os
import tkinter as tk
from tkinter import messagebox, ttk

from genesisleaf.core.encoding import bad_cf_codes, parse_text
from genesisleaf.core.space import KIND_LABEL, room_kind, row_room, verdict as space_verdict
from genesisleaf.paths import APP_ROOT
from genesisleaf.ui import brand
from genesisleaf.ui.fonts import FONT_UI, FONT_UI_B
from genesisleaf.ui.windows.progress import ProgressWindow
from genesisleaf.version import APP_TITLE, CREDITS


class ReportsMixin:
    """Credits, statistics, validation, progress window.

    Mixed into `App`; `self` is the main window.
    """

    def open_progress_window(self):
        """Open (or raise) the detailed progress window."""
        if not (self.pack and self.pack.flat):
            messagebox.showwarning("Progress Window",
                                   "Open a pack first.")
            return
        if not hasattr(self, "_progress_win") or not self._progress_win.win.winfo_exists():
            self._progress_win = ProgressWindow(self)
        else:
            self._progress_win.refresh()
            self._progress_win.win.deiconify()
            self._progress_win.win.lift()
            self._progress_win.win.focus_set()

    # -- tools -------------------------------------------------------------------------
    def show_credits(self):
        body = [APP_TITLE, ""]
        for name, what in CREDITS:
            body.append("  %s %s" % (name, what))
        body += ["", "This is a fan translation project.",
                 "Legend of Legaia is a trademark of its publisher;",
                 "no affiliation is implied."]
        dlg = tk.Toplevel(self.root)
        dlg.title("Credits")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        f = ttk.Frame(dlg, padding=16)
        f.pack(fill="both", expand=True)
        head = ttk.Frame(f)
        head.grid(row=0, column=0, sticky="w", pady=(0, 10))
        ttk.Label(head, image=brand.icon(self.root, 2)).pack(side="left")
        ttk.Label(head, image=brand.logotype(self.root, 3)).pack(
            side="left", padx=(12, 0))
        for i, line in enumerate(body, 1):
            ftk = FONT_UI_B if i == 0 else FONT_UI
            ttk.Label(f, text=line, font=ftk, justify="left",
                      anchor="w").grid(row=i, column=0, sticky="w")
        ttk.Button(f, text="Close", width=10,
                   command=dlg.destroy).grid(row=len(body) + 2, column=0,
                                             sticky="e", pady=(14, 0))
        dlg.grab_set()
        self.root.wait_window(dlg)

    def show_stats(self):
        s = self.get_stats()
        lines = ["Pack: %s" % (self.pack.path or "-")]
        lines.append("")
        for sec in self.pack.section_names:
            d = s["by_sec"][sec]
            pct = 100.0 * d["filled"] / max(1, d["total"])
            lines.append("%-20s %6d  filled %6d  (%5.1f%%)" % (sec, d["total"], d["filled"], pct))
        lines.append("")
        lines.append("TOTAL                  %6d  filled %6d  (%5.1f%%)" % (
            s["total"], s["filled"], 100.0 * s["filled"] / max(1, s["total"])))
        lines.append("")
        lines.append("Grows into free space:           %d" % s["grows"])
        lines.append("Won't fit:                       %d" % s["over_budget"])
        lines.append("Translations with non-ASCII:     %d" % s["non_ascii"])
        print("\n".join(lines))
        messagebox.showinfo("Pack statistics", "\n".join(lines))

    def validate_pack(self):
        bad = []
        for sec, e in self.pack.flat:
            tr = e.get("translation", "")
            if not tr:
                continue
            b, spans = parse_text(tr)
            if any(st == "nonascii" for _, _, st in spans):
                bad.append((e.get("key", ""), "unencodable char"))
            elif space_verdict(sec, e, b) == "over":
                bad.append((e.get("key", ""), "won't fit: %d B, room %d B (%s)" % (
                    b, row_room(sec, e), KIND_LABEL[room_kind(sec, e.get("key", ""))])))
            for tok in bad_cf_codes(tr):
                bad.append((e.get("key", ""), "colour code %s not in 0-9" % tok))
        print("Validation: %d problem entries" % len(bad))
        for k, why in bad[:200]:
            print("  %s : %s" % (k, why))
        messagebox.showinfo("Validate",
                            "%d problem entries found.\nSee console for list." % len(bad))

    # -- Help menu ------------------------------------------------------------
    SHORTCUTS = (
        ("File", "Ctrl+O", "Open a pack"),
        ("File", "Ctrl+S", "Save (previous file kept as .bak)"),
        ("File", "Ctrl+Shift+S", "Save as a new file (sidecars follow)"),
        ("Compare", "Alt+Down / Alt+Up", "Next / previous difference"),
        ("Compare", "Double-click", "Jump to the MINE entry in the editor"),
        ("Notes", "Hover a ✎ row", "Show the entry's notes"),
        ("Notes", "Alt+Double-click", "Open the row in the Notes dashboard"),
        ("Edit", "Ctrl+Z / Ctrl+Shift+Z, Ctrl+Y", "Undo / redo (all windows)"),
        ("Edit", "Ctrl+E", "Focus the translation box"),
        ("Edit", "Enter", "Insert the | row break"),
        ("Edit", "Ctrl+Enter", "| in a box, real newline in a single row"),
        ("Edit", "Shift+F1..F10", "Wrap selection in colour {cf:00..09}"),
        ("Edit", "F1..F12 (+Ctrl/Alt)", "Your macros (Options)"),
        ("Table", "Click / Shift+Click / arrows", "Select rows"),
        ("Table", "Ctrl+Click", "Pick single cells (again to add/remove)"),
        ("Table", "Ctrl+C / Ctrl+V", "Copy cells or rows / paste translations"),
        ("Table", "Ctrl+Alt+Click", "Copy one cell"),
        ("Table", "Delete", "Clear the selected rows' translations"),
        ("Table", "Ctrl+wheel, Ctrl+= / Ctrl+- / Ctrl+0", "Table text size"),
        ("Move", "Ctrl+N / Ctrl+P", "Next / previous entry"),
        ("Move", "Ctrl+Down / Ctrl+Up", "Next / previous untranslated"),
        ("Move", "Ctrl+Shift+C", "Next clone"),
        ("Move", "Alt+arrows (+Shift)", "Move in the table from anywhere"),
        ("Find", "Ctrl+F", "Focus Find"),
        ("Find", "Ctrl+G / Ctrl+Shift+G", "Next / previous hit"),
        ("View", "Ctrl+B", "Show / hide the navigator"),
        ("View", "Ctrl+Shift+N", "New view of this file"),
    )

    def show_shortcuts(self):
        """Help > Keyboard shortcuts."""
        win = tk.Toplevel(self.root)
        win.title("Keyboard shortcuts")
        win.geometry("640x560")
        win.transient(self.root)
        f = ttk.Frame(win, padding=10)
        f.pack(fill="both", expand=True)
        f.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1)
        tv = ttk.Treeview(f, columns=("area", "keys", "what"),
                          show="headings")
        for col, text, w in (("area", "Area", 70), ("keys", "Keys", 230),
                             ("what", "Does", 300)):
            tv.heading(col, text=text, anchor="w")
            tv.column(col, width=w, anchor="w")
        for row in self.SHORTCUTS:
            tv.insert("", "end", values=row)
        vs = ttk.Scrollbar(f, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        tv.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        ttk.Button(f, text="Close", command=win.destroy).grid(
            row=1, column=0, sticky="e", pady=(8, 0))

    def open_user_guide(self):
        """Help > User guide: the guide (or, in a trimmed install, the README)
        in the system viewer."""
        for name in (os.path.join("docs", "GUIDE.md"), "README.md"):
            path = os.path.join(APP_ROOT, name)
            if os.path.exists(path):
                break
        else:
            messagebox.showinfo("User guide", "The guide was not found next "
                                "to the program.")
            return
        try:
            os.startfile(path)                 # Windows
        except (AttributeError, OSError):
            messagebox.showinfo("User guide", path)

