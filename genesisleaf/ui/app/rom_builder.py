"""Tools > Build test ROM: drives legaia-patcher.exe on a worker thread.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import json
import os
import queue as _q
import re
import subprocess
import threading
from time import perf_counter
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from genesisleaf.core.config import DEFAULTS_PATCONF, PATCONF_PATH
from genesisleaf.core.pack import save_pack
from genesisleaf.ui.fonts import FONT_UI_SM, FONT_UI_SM_B
from genesisleaf.ui import theme as _theme


class RomBuilderMixin:
    """Tools > Build test ROM: drives legaia-patcher.exe on a worker thread.

    Mixed into `App`; `self` is the main window.
    """

    def _load_pat_conf(self):
        if self.pat_conf is not None:
            return self.pat_conf
        conf = dict(DEFAULTS_PATCONF)
        try:
            if os.path.exists(PATCONF_PATH):
                with open(PATCONF_PATH, "r", encoding="utf-8") as fh:
                    conf.update(json.load(fh))
        except Exception:
            pass
        self.pat_conf = conf
        return conf

    def _sync_relayout_var(self):
        conf = self._load_pat_conf()
        want = bool(conf.get("allow_relayout", False))
        if self.relayout_var.get() != want:
            self.relayout_var.set(want)

    def _on_relayout_toggle(self):
        conf = self._load_pat_conf()
        conf["allow_relayout"] = bool(self.relayout_var.get())
        self._save_pat_conf()

    def _save_pat_conf(self):
        try:
            with open(PATCONF_PATH, "w", encoding="utf-8") as fh:
                json.dump(self.pat_conf, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _open_folder(self, path):
        try:
            os.startfile(path)  # noqa: on Windows
        except Exception:
            try:
                os.startfile(os.path.dirname(os.path.abspath(path)))
            except Exception:
                pass

    def _summary_from_log(self, log):
        txt = log.get("1.0", "end")

        def num(pat, n=1):
            m = re.search(pat, txt)
            return tuple(int(g) for g in m.groups()) if m else (0,) * n
        app = re.search(
            r"applied ([0-9]+) entr\w+,\s*([0-9]+) already applied, "
            r"([0-9]+) untranslated",
            txt)
        app_s = app.groups() if app else ("-", "-", "-")
        skp = re.search(r"([0-9]+) entr\w+ (?:was|were) skipped - fix and re-run", txt)
        skp_s = skp.group(1) if skp else "0"
        secs = re.findall(
            r"\s+([\w:]+)\s+(\d+) of\s+(\d+) applied(?: \((\d+) skipped\))?",
            txt)
        names_n, mons_n = num(r"longer names: (\d+) executable name\(s\) moved[^,]*, "
                              r"(\d+) monster record", 2)
        labels_n, = num(r"longer labels: (\d+)")
        rl_n, rl_s = num(r"disc relayout: grew (\d+) scene MAN entr\w+ by (\d+) sector", 2)
        acc_n, = num(r"accent font: (\d+) accented glyphs")
        lines = [
            "",
            "== SUMMARY ==",
            "applied %s | already %s | untranslated %s | skipped %s" % (
                app_s[0], app_s[1], app_s[2], skp_s),
        ]
        for name, n, tot, sk in secs:
            lines.append("  %-16s %s / %s applied%s" % (
                name, n, tot, " (%s skipped)" % sk if sk else ""))
        lines += [
            "names moved into free table space: %d   monster records grown: %d"
            % (names_n, mons_n),
            "menu / system labels moved (references rewritten): %d" % labels_n,
        ]
        if rl_n:
            lines.append("dialogue relayout: %d scene(s) grew by %d sector(s) - "
                         "the image grew, no PPF" % (rl_n, rl_s))
        if acc_n:
            lines.append("accent font: %d accented glyphs drawn into the font"
                         % acc_n)
        lines += [
            "",
            "Test the image from a COLD BOOT with a CLEAN memory card - never a",
            "save state from the old disc, or the console keeps the old RAM text.",
            "If you ever need --allow-relayout instead, it must be run once on",
            "the PRISTINE disc now, never on this image.",
        ]
        log.insert("end", "\n".join(lines) + "\n", "head")
        log.see("end")

    def build_test_rom(self):
        if not (self.pack and self.pack.path):
            messagebox.showinfo("No pack", "Open a pack first.")
            return
        if self.dirty:
            if not messagebox.askyesno(
                    "Unsaved edits",
                    "The pack has unsaved edits. Save it first so the ROM is "
                    "built from what you see?"):
                return
            try:
                save_pack(self.pack, self.pack.path)
                self.dirty = False
            except Exception as e:
                messagebox.showerror("Save error", str(e))
                return
        self.update_status()

        conf = self._load_pat_conf()
        out_dir = conf.get("output_dir") or DEFAULTS_PATCONF["output_dir"]
        default_out = os.path.join(out_dir, "Legend of Legaia (USA) PT-BR.bin")

        win = tk.Toplevel(self.root)
        win.title("Build test ROM (translate import)")
        win.geometry("880x640")

        body = ttk.Frame(win, padding=8)
        body.pack(side="top", fill="x")
        log_wrap = ttk.Frame(win)
        log_wrap.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 6))

        v = {
            "patcher": tk.StringVar(value=conf.get("patcher_exe", "")),
            "disc": tk.StringVar(value=conf.get("retail_disc", "")),
            "out": tk.StringVar(value=default_out),
            "ppf": tk.StringVar(value=os.path.splitext(default_out)[0] + ".ppf"),
            "dry": tk.BooleanVar(value=conf.get("dry_run_first", True)),
            "write_ppf": tk.BooleanVar(value=True),
            "relayout": tk.BooleanVar(value=conf.get("allow_relayout", False)),
            "accents": tk.StringVar(value=conf.get("accents", "auto")),
        }
        fmt = (("All files", "*.*"),)

        def browse(field, title):
            p = filedialog.askopenfilename(title=title, filetypes=fmt)
            if p:
                v[field].set(p)

        def browse_save(field, title, types=fmt):
            p = filedialog.asksaveasfilename(title=title, filetypes=types)
            if p:
                v[field].set(p)

        row = 0
        ttk.Label(body, text="legaia-patcher.exe:", font=FONT_UI_SM).grid(
            row=row, column=0, sticky="w")
        ttk.Entry(body, textvariable=v["patcher"], width=70,
                  font=FONT_UI_SM).grid(row=row, column=1, sticky="ew", padx=4)
        ttk.Button(body, text="...", width=3,
                   command=lambda: browse("patcher", "Select legaia-patcher.exe")
                   ).grid(row=row, column=2)
        row += 1
        ttk.Label(body, text="Pristine retail disc:", font=FONT_UI_SM).grid(
            row=row, column=0, sticky="w")
        ttk.Entry(body, textvariable=v["disc"], width=70,
                  font=FONT_UI_SM).grid(row=row, column=1, sticky="ew", padx=4)
        ttk.Button(body, text="...", width=3,
                   command=lambda: browse("disc",
                                          "PRISTINE retail disc - never the last output")
                   ).grid(row=row, column=2)
        row += 1
        ttk.Label(body, text="Output image (.bin):", font=FONT_UI_SM).grid(
            row=row, column=0, sticky="w")
        ttk.Entry(body, textvariable=v["out"], width=70,
                  font=FONT_UI_SM).grid(row=row, column=1, sticky="ew", padx=4)
        ttk.Button(body, text="...", width=3,
                   command=lambda: browse_save("out", "Output patched image")
                   ).grid(row=row, column=2)
        row += 1
        ttk.Label(body, text="PPF patch:", font=FONT_UI_SM).grid(
            row=row, column=0, sticky="w")
        ttk.Entry(body, textvariable=v["ppf"], width=70,
                  font=FONT_UI_SM).grid(row=row, column=1, sticky="ew", padx=4)
        ttk.Button(body, text="...", width=3,
                   command=lambda: browse_save(
                       "ppf", "Output PPF 3.0 patch",
                       (("PPF", "*.ppf"), ("All files", "*.*")))
                   ).grid(row=row, column=2)
        row += 1
        ttk.Checkbutton(body, text="Dry run first (translate space - the importer's "
                                   "own verdict for every line, no writes)",
                        variable=v["dry"]).grid(row=row, column=0, columnspan=3,
                                                sticky="w")
        row += 1
        ppf_chk = ttk.Checkbutton(body, text="Also write a PPF 3.0 patch (apply to your "
                                   "retail .bin)",
                                  variable=v["write_ppf"])
        ppf_chk.grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1

        def on_relayout():
            if v["relayout"].get():
                v["write_ppf"].set(False)
                ppf_chk.state(["disabled"])
            else:
                ppf_chk.state(["!disabled"])
            self.relayout_var.set(v["relayout"].get())
            self._on_relayout_toggle()

        ttk.Checkbutton(body, text="Give translated dialog more room "
                                   "(--allow-relayout: a whole-sector disc "
                                   "relayout so full-length dialog fits; "
                                   "disables the PPF patch and grows the image)",
                        variable=v["relayout"],
                        command=on_relayout).grid(row=row, column=0,
                                                  columnspan=3, sticky="w")
        row += 1
        acc_row = ttk.Frame(body)
        acc_row.grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Label(acc_row, text="Accents (--accents):",
                  font=FONT_UI_SM).pack(side="left")
        ttk.Combobox(acc_row, textvariable=v["accents"], state="readonly",
                     width=8, values=("auto", "font", "fold", "strict"),
                     font=FONT_UI_SM).pack(side="left", padx=6)
        ttk.Label(acc_row, text="auto = the pack's accents: header, else font when "
                                "the accent-font preview is on",
                  font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED).pack(side="left")
        row += 1
        body.columnconfigure(1, weight=1)

        log = tk.Text(log_wrap, wrap="word", font=FONT_UI_SM,
                      bg="#111", fg="#d8d8d8", height=18)
        ls = ttk.Scrollbar(log_wrap, orient="vertical", command=log.yview)
        log.configure(yscrollcommand=ls.set)
        ls.pack(side="right", fill="y")
        log.pack(side="left", fill="both", expand=True)
        log.tag_configure("head", foreground="#96d8ff",
                          font=FONT_UI_SM_B)
        log.tag_configure("err", foreground="#ff6b6b")

        btns = ttk.Frame(win, padding=(6, 6))
        btns.pack(side="bottom", fill="x")
        run_btn = ttk.Button(btns, text="Build ROM")
        run_btn.pack(side="left")
        ttk.Button(btns, text="Open output folder",
                   command=lambda: self._open_folder(
                       os.path.dirname(v["out"].get()))).pack(side="left", padx=6)
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")

        q = _q.Queue()

        def commands():
            exe = v["patcher"].get().strip()
            cmds = []
            # the same relayout / accent options for the dry run and the
            # import, so the dry run predicts exactly what the import writes
            opts = []
            if v["relayout"].get():
                opts.append("--allow-relayout")
            acc = self.accent_mode_for_patcher()
            if acc:
                opts += ["--accents", acc]
            if v["dry"].get():
                cmds.append(("[dry run] translate space", [
                    "translate", "space", "--pack", self.pack.path,
                    "--input", v["disc"].get()] + opts))
            imp = ["translate", "import", "--input", v["disc"].get(),
                   "--pack", self.pack.path, "--output", v["out"].get(),
                   "--verbose"] + opts
            if not v["relayout"].get() and v["write_ppf"].get():
                imp += ["--patch", v["ppf"].get()]
            cmds.append(("[import] translate import", imp))
            return exe, cmds

        def worker(exe, cmds, disc, output_dir):
            try:
                if not os.path.isfile(exe):
                    q.put((2, "patcher exe not found:\n%s" % exe))
                elif not os.path.isfile(disc):
                    q.put((2, "retail disc not found:\n%s\n\nUse the PRISTINE "
                              "disc - never an already-patched image." % disc))
                else:
                    os.makedirs(output_dir, exist_ok=True)
                    for label, args in cmds:
                        q.put((0, "== %s ==" % label))
                        q.put((0, "> %s %s" % (os.path.basename(exe),
                                               " ".join(args))))
                        p = subprocess.Popen(
                            [exe] + args, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", bufsize=1)
                        for line in p.stdout:
                            q.put((1, line.rstrip("\n")))
                        p.wait()
                        if p.returncode != 0:
                            q.put((2, "!! '%s' exited with code %d"
                                   % (label, p.returncode)))
                            break
                        q.put((0, ""))
            except Exception as e:
                q.put((2, "!! build failed: %s" % e))
            finally:
                q.put((99, None))

        def pump():
            if not win.winfo_exists():
                return
            deadline = perf_counter() + 0.008
            segments = []
            finished = False
            try:
                while len(segments) < 256 and perf_counter() < deadline:
                    kind, payload = q.get_nowait()
                    if kind == 99:
                        finished = True
                        break
                    tag = "head" if kind == 0 else "err" if kind == 2 else ""
                    if segments and segments[-1][1] == tag:
                        segments[-1][0].append(payload + "\n")
                    else:
                        segments.append(([payload + "\n"], tag))
            except _q.Empty:
                pass
            for lines, tag in segments:
                log.insert("end", "".join(lines), tag)
            if segments:
                log.see("end")
            if finished:
                run_btn.configure(state="normal")
                self._summary_from_log(log)
                return
            win.after(80, pump)

        def start():
            for f in ("patcher", "disc", "out"):
                if not v[f].get().strip():
                    messagebox.showerror("Missing value",
                                         "Fill every path field first.",
                                         parent=win)
                    return
            if v["relayout"].get() and v["write_ppf"].get():
                messagebox.showerror(
                    "--allow-relayout",
                    "The relayout cannot also write a PPF patch (the image "
                    "grows). Untick 'Also write a PPF 3.0 patch' first.",
                    parent=win)
                return
            conf["patcher_exe"] = v["patcher"].get().strip()
            conf["retail_disc"] = v["disc"].get().strip()
            conf["output_dir"] = os.path.dirname(v["out"].get())
            conf["dry_run_first"] = v["dry"].get()
            conf["allow_relayout"] = v["relayout"].get()
            conf["accents"] = v["accents"].get()
            self.pat_conf = conf
            self._save_pat_conf()
            self._sync_relayout_var()
            log.delete("1.0", "end")
            run_btn.configure(state="disabled")
            # Snapshot Tk variables on the UI thread before starting disk work.
            exe, cmds = commands()
            threading.Thread(target=worker, args=(exe, cmds, v["disc"].get().strip(),
                              os.path.dirname(v["out"].get()) or "."), daemon=True).start()
            pump()

        run_btn.configure(command=start)
