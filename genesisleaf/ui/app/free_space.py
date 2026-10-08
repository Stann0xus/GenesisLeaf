"""Free space: how much room the pack has left, the way the importer sees it.

The status-bar meter and Tools > Free space report read `core.space`:
a disc-free estimate from the pack alone, or - after *Measure on disc* - the
importer's own dry run (`legaia-patcher translate space --json`) on the
pristine disc configured for Build test ROM, with the same relayout and accent
options the build uses.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import os
import queue as _q
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from genesisleaf.core import space as _space
from genesisleaf.core.briefs import ROOM_BRIEF
from genesisleaf.core.pack import emit_pack
from genesisleaf.ui import theme as _theme
from genesisleaf.ui.fonts import FONT_UI_SM


class FreeSpaceMixin:
    """Status-bar free-space meter, the Free space report, and the measured
    dry run that feeds them.

    Mixed into `App`; `self` is the main window.
    """

    # -- figures --------------------------------------------------------------
    def space_estimate(self):
        """Cached `core.space.estimate` of the open pack."""
        if self.pack is None:
            return None
        if self._space_est is None:
            self._space_est = _space.estimate(self.pack)
        return self._space_est

    def space_figures(self):
        """`(names, system, labels, measured?)` free bytes: the measured run
        while every row it covered is unchanged, else the estimate."""
        est = self.space_estimate()
        meas = _space.measured_summary()
        if meas and not self._space_stale():
            return (meas["names_free"], meas["system_free"],
                    meas["labels_free"], True)
        return est["names_free"], est["system_free"], est["labels_free"], False

    def _space_stale(self):
        """True once any translation differs from what was measured."""
        snap = _space.MEASURED["snapshot"]
        if not snap or self.pack is None:
            return True
        key = (id(self.pack), id(snap), getattr(self, "_stats_gen", 0))
        if getattr(self, "_space_stale_key", None) != key:
            self._space_stale_key = key
            self._space_stale_value = any(
                snap.get(e.get("key", "")) != e.get("translation", "")
                for _s, e in self.pack.flat)
        return self._space_stale_value

    def accent_mode_for_patcher(self):
        """The `--accents` value a build/dry run uses: the patcher config's
        choice, or 'auto' = the pack's own `accents:` header, else `font`
        when the accent-font preview is on."""
        conf = self._load_pat_conf()
        mode = conf.get("accents", "auto")
        if mode in ("strict", "fold", "font"):
            return mode
        hdr = str(self.pack.header.get("accents", "") or "") if self.pack else ""
        if hdr:
            return None             # the pack header already says it
        return "font" if self.accent_font_var.get() else None

    # -- status bar -------------------------------------------------------------
    def _update_space_lab(self):
        lab = getattr(self, "space_lab", None)
        if lab is None:
            return
        if not (self.pack and self.pack.flat):
            lab.configure(text="Free space: -", foreground=_theme.TH_FG_MUTED)
            return
        names, system, labels, measured = self.space_figures()
        txt = "Free: names %s B · labels %s B · system %s B%s" % (
            _fmt(names), _fmt(labels), _fmt(system),
            "" if measured else " (estimate)")
        low = min(v for v in (names, system, labels) if v is not None)
        col = _theme.TH_BAD if low < 0 else (
            _theme.TH_WARN if low < 32 else _theme.TH_FG_MUTED)
        lab.configure(text=txt, foreground=col)

    # -- report window -----------------------------------------------------------
    def show_space_report(self):
        win = tk.Toplevel(self.root)
        win.title("Free space")
        win.geometry("860x680")
        txt = tk.Text(win, wrap="word", font=FONT_UI_SM)
        vs = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vs.set)
        btns = ttk.Frame(win, padding=(6, 6))
        btns.pack(side="bottom", fill="x")
        mb = ttk.Button(btns, text="Measure on disc")
        mb.pack(side="left")
        ttk.Button(btns, text="Refresh",
                   command=lambda: self._space_report_fill(txt)).pack(
                       side="left", padx=6)
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")
        vs.pack(side="left", fill="y", pady=6, padx=(0, 6))
        txt.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        mb.configure(command=lambda: self.measure_space(
            on_done=lambda: self._space_report_fill(txt), button=mb, parent=win))
        self._space_report_fill(txt)

    def _space_report_fill(self, txt):
        if self.pack is None:
            data = "No pack loaded."
        else:
            data = "\n".join(self._space_report_lines())
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("1.0", data)
        txt.configure(state="disabled")

    def _space_report_lines(self):
        est = self.space_estimate()
        meas = _space.measured_summary()
        stale = self._space_stale()
        st = self.get_stats()
        L = ["FREE SPACE", ""]
        if meas:
            L.append("Measured on disc at %s  (%s)%s" % (
                meas["when"], meas["options"] or "no options",
                "  - EDITED SINCE, figures below are from that run"
                if stale else ""))
        else:
            L.append("Estimate from the pack alone.  'Measure on disc' runs the "
                     "importer's own dry run for exact figures.")
        L += ["",
              "Pooled room a longer string can still take:",
              "  %-28s %12s %12s" % ("", "estimate", "measured")]
        rows = (("names (items, spells, ...)", est["names_free"],
                 meas and meas["names_free"]),
                ("system text", est["system_free"], meas and meas["system_free"]),
                ("menu labels", est["labels_free"], meas and meas["labels_free"]))
        for lab, e_, m_ in rows:
            L.append("  %-28s %10s B %10s" % (lab, _fmt(e_),
                                               "-" if not meas else _fmt(m_) + " B"))
        L.append("")
        L.append("  names moved out of their slot: %d   system strings moved: %d"
                 % (est["names_moved"], est["system_moved"]))
        for img, d in sorted(est["labels"].items()):
            if d["moved"] or d["spare"]:
                L.append("  PROT %s labels: %d moved, %d B free (reserved region "
                         "%d B, compaction reserve %d B)" % (
                             img, d["moved"], d["free"], d["spare"],
                             d["compaction"]))
        L += ["",
              "Rows:  %d fit in place,  %d grow into free space,  %d won't fit" % (
                  st["filled"] - st["grows"] - st["over_budget"] - st["non_ascii"],
                  st["grows"], st["over_budget"]),
              "  monster names past %d bytes: %d" % (
                  _space.MONSTER_CAP, len(est["monsters_over"])),
              "  fixed cells / pinned strings over budget: %d%s" % (
                  len(est["fixed_over"]),
                  "  (" + ", ".join(est["fixed_over"][:6]) + ")"
                  if est["fixed_over"] else ""),
              "  dialogue lines longer than their English: %d" % est["dialog_long"]]
        rep = _space.MEASURED["report"]
        if rep:
            L += ["", "Dialogue (measured): every scene must recompress into "
                  "its footprint"]
            tight = [s for s in rep.get("scenes", ())
                     if s.get("rolled_back") or s.get("relayout_sectors")
                     or s.get("relayout_would_add")]
            tight.sort(key=lambda s: -(s.get("full_overflow") or 0))
            if not tight:
                L.append("  every scene fits its footprint")
            for s in tight[:40]:
                L.append("  PROT %4d %-10s %4d lines  footprint %6d B  %s" % (
                    s["prot"], s.get("scene") or "?", s.get("filled") or 0,
                    s["footprint"], _scene_note(s)))
            fails = [e for e in rep.get("entries", ())
                     if e.get("outcome") not in _space.LANDS
                     and e.get("outcome") not in (None, "untranslated")]
            L += ["", "Lines the importer refuses: %d" % len(fails)]
            for e in fails[:60]:
                L.append("  %-26s %s" % (e["key"], e.get("issue") or e["outcome"]))
            regions = sorted(rep.get("name_regions", ()),
                             key=lambda r: r.get("pack_free", 0))
            if regions:
                L += ["", "Tightest name regions (a moved name needs one free "
                      "run big enough):"]
                for r in regions[:8]:
                    L.append("  region %-3d %5d strings  %6d B  free %5d B" % (
                        r["index"], r["strings"], r["total"], r["pack_free"]))
        L += ["", ROOM_BRIEF]
        return L

    # -- measuring ---------------------------------------------------------------
    def measure_space(self, on_done=None, button=None, parent=None):
        """Run `translate space --json` on the configured pristine disc."""
        if not (self.pack and self.pack.flat):
            messagebox.showinfo("No pack", "Open a pack first.", parent=parent)
            return
        conf = self._load_pat_conf()
        exe = conf.get("patcher_exe", "")
        disc = conf.get("retail_disc", "")
        if not (os.path.isfile(exe) and os.path.isfile(disc)):
            messagebox.showinfo(
                "Measure on disc",
                "Set legaia-patcher.exe and the pristine USA disc in "
                "Tools > Build test ROM first.\n\npatcher: %s\ndisc: %s"
                % (exe or "-", disc or "-"), parent=parent)
            return
        fd, tmp = tempfile.mkstemp(suffix=".yaml", prefix="genesisleaf-space-")
        with os.fdopen(fd, "wb") as fh:
            fh.write(emit_pack(self.pack).encode("utf-8"))
        args = ["translate", "space", "--input", disc, "--pack", tmp, "--json"]
        opts = []
        if conf.get("allow_relayout", False):
            args.append("--allow-relayout")
            opts.append("--allow-relayout")
        acc = self.accent_mode_for_patcher()
        if acc:
            args += ["--accents", acc]
            opts.append("--accents " + acc)
        if button is not None:
            button.configure(state="disabled", text="Measuring...")
        q = _q.Queue()

        def work():
            try:
                p = subprocess.run([exe] + args, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
                q.put((p.returncode, p.stdout, p.stderr))
            except Exception as ex:          # noqa: BLE001 - reported below
                q.put((-1, "", str(ex)))
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

        def pump():
            try:
                code, out, err = q.get_nowait()
            except _q.Empty:
                self.root.after(150, pump)
                return
            if button is not None:
                button.configure(state="normal", text="Measure on disc")
            if code != 0:
                messagebox.showerror("Measure on disc",
                                     "legaia-patcher failed (%s):\n%s" % (
                                         code, (err or out)[-1500:]), parent=parent)
                return
            try:
                rep = _space.parse_report(out)
            except ValueError as ex:
                messagebox.showerror("Measure on disc", str(ex), parent=parent)
                return
            _space.load_measured(rep, self.pack, " ".join(opts))
            self.space_changed()
            if on_done:
                on_done()

        threading.Thread(target=work, daemon=True).start()
        pump()

    def space_changed(self):
        """Drop cached figures and repaint everything that reads them."""
        self._stats_gen = getattr(self, "_stats_gen", 0) + 1
        self._space_stale_key = None
        self._space_est = None
        self._stats = None
        self.update_status()
        try:
            self.rebuild_view()
        except Exception:
            pass


def _fmt(v):
    return "-" if v is None else format(v, ",")


def _scene_note(s):
    if s.get("rolled_back"):
        return "%d line(s) ROLLED BACK" % len(s["rolled_back"])
    if s.get("relayout_sectors"):
        return "grows %d sector(s) (relayout)" % s["relayout_sectors"]
    if s.get("relayout_would_add"):
        return "needs +%d sector(s): enable relayout" % s["relayout_would_add"]
    return ""
