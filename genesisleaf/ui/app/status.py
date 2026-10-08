"""Status bar, byte/status labels, flash messages and cached pack statistics.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk

from genesisleaf.core import space as _space
from genesisleaf.core.encoding import parse_text
from genesisleaf.core.pack import Pack
from genesisleaf.diagnostics import current as current_diagnostics
from genesisleaf.ui.fonts import FONT_UI_SM
from genesisleaf.ui import theme as _theme


class StatusMixin:
    """Status bar, byte/status labels, flash messages and cached pack statistics.

    Mixed into `App`; `self` is the main window.
    """

    # -- status bar ----------------------------------------------------------------
    def _build_statusbar(self):
        """Message on the left; progress and the free-space meter on the
        right, each in its own fixed slot so nothing jumps around."""
        s = ttk.Frame(self.root, padding=(8, 3), style="Chrome.TFrame")
        s.pack(side="bottom", fill="x")
        self.statusbar = s
        self.sb = ttk.Label(s, text="No pack loaded", anchor="w",
                            font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED,
                            style="Chrome.TLabel")
        self.sb.pack(side="left", fill="x", expand=True)
        self.diagnostic_label = None
        if current_diagnostics() is not None:
            self.diagnostic_label = ttk.Label(
                s, text="UI starting", anchor="e", font=FONT_UI_SM,
                foreground=_theme.TH_FG_MUTED, style="Chrome.TLabel")
            self.diagnostic_label.pack(side="right", padx=(10, 0))
        self.sb2 = ttk.Label(s, text="", anchor="e", font=FONT_UI_SM,
                             foreground=_theme.TH_FG_MUTED,
                             style="Chrome.TLabel")
        self.sb2.pack(side="right")
        ttk.Separator(s, orient="vertical").pack(side="right", fill="y",
                                                 padx=8)
        self.space_lab = ttk.Label(s, text="Free space: -", font=FONT_UI_SM,
                                   foreground=_theme.TH_FG_MUTED,
                                   style="Chrome.TLabel", cursor="hand2")
        self.space_lab.pack(side="right")
        self.space_lab.bind("<Button-1>", lambda _e: self.show_space_report())
        ttk.Separator(s, orient="vertical").pack(side="right", fill="y",
                                                 padx=8)
        self.l_dups = ttk.Label(s, text="", font=FONT_UI_SM,
                                foreground=_theme.TH_FG_MUTED,
                                style="Chrome.TLabel")
        self.l_dups.pack(side="right")

    def get_stats(self):
        if self._stats is None:
            self._stats = self.pack.stats()
        return self._stats

    def invalidate_stats(self):
        self._stats_gen = getattr(self, "_stats_gen", 0) + 1
        self._space_stale_key = (id(self.pack),
                                 id(_space.MEASURED["snapshot"]), self._stats_gen)
        self._space_stale_value = True
        if self._stats_job:
            try:
                self.root.after_cancel(self._stats_job)
            except Exception:
                pass
        self._stats_job = self.root.after(600, self._stats_recompute)

    def _stats_recompute(self):
        self._stats_job = None
        previous = getattr(self, "_stats_worker", None)
        if previous is not None and previous.is_alive():
            # An older edit is still being counted. Let it finish before
            # starting the latest snapshot, so typing cannot stack scans.
            self._stats_job = self.root.after(100, self._stats_recompute)
            return
        gen = self._stats_gen
        # Snapshot on Tk's thread, then calculate the expensive per-entry
        # counts in a worker. Edits that arrive meanwhile discard this result.
        rows = [(sec, dict(entry)) for sec, entry in self.pack.flat]
        measured = _space.MEASURED["snapshot"]
        result = {}

        def work():
            try:
                snapshot = Pack()
                snapshot.flat = rows
                result["stats"] = snapshot.stats()
                result["space_est"] = _space.estimate(snapshot)
                if measured:
                    result["space_stale"] = any(
                        measured.get(entry.get("key", "")) != entry.get("translation", "")
                        for _sec, entry in rows)
            except Exception as exc:  # cache refresh is best effort
                result["error"] = exc

        worker = threading.Thread(target=work, daemon=True)
        self._stats_worker = worker
        worker.start()
        self.root.after(50, lambda: self._stats_poll(worker, result, gen))

    def _stats_poll(self, worker, result, gen):
        if not worker.is_alive() and getattr(self, "_stats_worker", None) is worker:
            self._stats_worker = None
        if gen != self._stats_gen:
            return
        if worker.is_alive():
            self.root.after(50, lambda: self._stats_poll(worker, result, gen))
            return
        if "stats" in result and "space_est" in result:
            self._stats = result["stats"]
            self._space_est = result["space_est"]
            if "space_stale" in result:
                self._space_stale_value = result["space_stale"]
            self.update_status()

    # -- status -------------------------------------------------------------------
    def update_status(self):
        self._update_space_lab()
        if not (self.pack and self.pack.flat):
            self.sb.configure(text="No pack loaded")
            if hasattr(self, "l_dups"):
                self.l_dups.configure(text="")
            if hasattr(self, "l_tr_bytes"):
                self.l_tr_bytes.configure(text="")
                self.l_status.configure(text="")
            return
        st = self.get_stats()
        self._refresh_navigator(st)
        # progress for the table, sitting in its own bar rather than mixed in
        # with the filter controls
        if hasattr(self, "l_dups"):
            pct = (100.0 * st["filled"] / st["total"]) if st["total"] else 0.0
            self.l_dups.configure(
                text="%d / %d translated  (%.0f%%)" % (
                    st["filled"], st["total"], pct))
        if self.current < 0:
            self.sb.configure(
                text="Loaded %s | %d entries | %d translated | %d grow into free "
                     "space | %d won't fit | %d non-ASCII" % (
                         os.path.basename(self.pack.path) if self.pack.path else "pack",
                         len(self.pack.flat), st["filled"], st["grows"],
                         st["over_budget"], st["non_ascii"]))
            return
        self._bytes_label()
        self.sb.configure(
            text="%s | section totals: %s | filled overall %d/%d" % (
                (self.pack.flat[self.current][0]),
                self._sec_summary(self.pack.flat[self.current][0]),
                st["filled"], st["total"]))

    def _bytes_label(self):
        if self.current < 0 or not (self.pack and self.pack.flat):
            return
        w = self.tr_txt
        flat = getattr(w, "_ed_flat", [])
        if len(flat) > 1:
            # a box: measure the row under the caret, not just the active one
            try:
                k = int(w.index("insert").split(".")[0]) - 1
            except tk.TclError:
                k = -1
            if 0 <= k < len(flat):
                idx = flat[k]
            else:
                idx = self.current
            tr = w.get("%d.0" % (k + 1), "%d.end" % (k + 1)) \
                if 0 <= k < len(flat) else w.get("1.0", "end-1c")
        else:
            idx = self.current
            tr = w.get("1.0", "end-1c")
        sec, e = self.pack.flat[idx]
        b, spans = parse_text(tr)
        sb, _ = parse_text(e.get("source", ""))
        budget = int(e.get("budget", sb))
        kind = _space.room_kind(sec, e.get("key", ""))
        v = _space.verdict(sec, dict(e, translation=tr), b)
        non = any(st == "nonascii" for _, _, st in spans)
        n_fold = sum(1 for _, _, st in spans if st == "fold")
        n_tok = sum(1 for _, _, st in spans if st in ("sub", "ctl", "byte", "esc2"))
        if non:
            state, col, style = "UNENCODABLE CHARACTERS", _theme.TH_BAD, "BudgetBad"
        elif v == "over":
            state, col, style = "WON'T FIT (%s, room %d B)" % (
                _space.KIND_LABEL[kind], _space.row_room(sec, e)), \
                _theme.TH_BAD, "BudgetBad"
        elif v == "grows":
            names, system, labels, _m = self.space_figures()
            pool = {"name": names, "system": system, "label": labels}.get(kind)
            state = "GROWS +%d B into free space (%s%s)" % (
                b - budget, _space.KIND_LABEL[kind],
                "" if pool is None else ", %s B free" % format(pool, ","))
            col, style = _theme.TH_ACCENT, "BudgetWarn"
        else:
            state, col, style = "OK", _theme.TH_OK, "BudgetOk"
        self.l_tr_bytes.configure(
            text="encoded %d / source %d / budget %d" % (b, sb, budget),
            foreground=col)
        self.l_status.configure(
            text="%s  ·  %d tokens  ·  %d folded" % (state, n_tok, n_fold),
            foreground=col)
        # the meter beside the key: bytes used against the budget
        if hasattr(self, "budget_bar"):
            self.budget_bar.configure(
                value=min(100.0, 100.0 * b / budget) if budget else 100.0,
                style=style + ".Horizontal.TProgressbar")
            self.l_budget.configure(text="%d / %d B" % (b, budget),
                                    foreground=col)

    def flash(self, msg, ms=4000):
        """Show a short-lived confirmation in the editor's own label.

        Used for undo/redo and theme saves, where saying what just happened is
        the point - and where the answer must survive the status refresh that
        the same action triggers immediately afterwards."""
        lab = getattr(self, "l_flash", None)
        if lab is None:
            return
        try:
            lab.configure(text=msg)
            if self._flash_job is not None:
                try:
                    self.root.after_cancel(self._flash_job)
                except (ValueError, tk.TclError, AttributeError):
                    pass
            self._flash_job = self.root.after(
                ms, lambda: lab.configure(text=""))
        except tk.TclError:
            pass
