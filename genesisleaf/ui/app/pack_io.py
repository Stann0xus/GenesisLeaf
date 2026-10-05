"""Open / async load / reload / save of packs, and the glossary/notes sidecars.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import json
import os
import threading
from tkinter import filedialog, messagebox

from genesisleaf.core.pack import Pack, needs_accent_font, save_pack
from genesisleaf.core.textfix import round_1
from genesisleaf.core import space as _space
from genesisleaf.ui.loader import BusyOverlay
from genesisleaf.version import APP_REVISION, APP_TITLE


class PackIOMixin:
    """Open / async load / reload / save of packs, and the glossary/notes sidecars.

    Mixed into `App`; `self` is the main window.
    """

    # ---------------------------------------------------------------------------
    # IO
    # ---------------------------------------------------------------------------
    def load_pack(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
                title="Open translation pack",
                filetypes=[("YAML pack", "*.yaml *.yml"), ("All files", "*.*")])
            if not path:
                return
        self._load_pack_async(path)

    def _load_pack_async(self, path):
        """Parse `path` on a worker thread behind the spinner overlay.

        The worker builds a *fresh* Pack and never touches a widget or the
        live pack; `_load_poll` swaps it in on the Tk thread once it is done.
        The overlay stays up through the table build and is closed by
        `_finish_loading` when the last chunk of rows is in the tree."""
        if getattr(self, "_loading", False):
            self.flash("still loading the previous file")
            return
        self._finish_loading()               # drop any stale overlay
        self._loader = BusyOverlay(self.root, "Loading pack",
                                   os.path.basename(path))
        self._loading = True
        self.root.config(cursor="watch")
        outcome = {}

        def work():
            try:
                fresh = Pack()
                fresh.load(path)
                outcome["pack"] = fresh
            except Exception as e:                  # noqa: BLE001 - shown to user
                outcome["err"] = e

        th = threading.Thread(target=work, daemon=True)
        th.start()
        self.root.after(50, lambda: self._load_poll(th, outcome, path))

    def _load_poll(self, th, outcome, path):
        """Tk-side heartbeat: keep the window responsive until the worker
        is out, then hand over to `_after_pack_loaded`."""
        if th.is_alive():
            self.root.after(40, lambda: self._load_poll(th, outcome, path))
            return
        self._loading = False
        self.root.config(cursor="")
        if "err" in outcome:
            self._finish_loading()
            messagebox.showerror("Load error", str(outcome["err"]))
            return
        self.pack = outcome["pack"]
        if self._loader is not None:
            self._loader.set_message("Building table",
                                     os.path.basename(path))
        self._after_pack_loaded(path)

    def _after_pack_loaded(self, path):
        self.dirty = False
        self.current = -1
        self._stats = None
        self._space_est = None
        _space.clear_measured()      # measured for the previous pack
        self._box_map = None
        self.history.clear()          # steps belong to the pack they edited
        self._wb_refs = None
        self._join.clear()
        self._join_unit_cache = None
        self._join_skip.clear()
        self._cancel_join()          # a buffered pass would fire into the new pack
        self._find_hits = None
        self._update_join_label()
        self._load_sidecar()
        self.build_ref_names()
        self.sec_cb["values"] = ["All"] + list(self.pack.section_names)
        self.sec_cb.current(0)
        self.filter_field = "Section"
        self.filter_value = "All"
        if hasattr(self, "filter_by_cb"):
            self.filter_by_cb.set("Section")
        self._ctx_cache = None
        self._cmp_update_labels()
        if self.other is not None:
            # the open comparison pairs flat indices of the previous pack
            self.refresh_compare()
        self.refresh_notes_dashboard()
        self._refresh_glossary_path()
        self.rebuild_view()
        self._pump_loader()
        self.refresh_dups()
        self.update_status()
        self._pump_loader()
        # a fresh pack invalidates every secondary view: re-point them at the
        # new data and rebuild their tables, or they would keep showing the
        # previous file's rows
        for v in list(self._views):
            v.pack = self.pack
            v.win.title("View - %s" % (self.pack.path or "no file"))
            v.sec_cb["values"] = ["All"] + list(self.pack.section_names)
            v.sec_cb.current(0)
            v.current = -1
            v.rebuild_view()
            self._pump_loader()
        if self.view:
            self.root.after(50, lambda: self._select_view(0))
        self.sb2.configure(text="glossary: %d terms" % len(self.glossary))
        self.root.title("%s  -  %s  (%s)"
                        % (APP_TITLE, os.path.basename(path), APP_REVISION))
        # Auto-enable accent font for languages that need accents (Portuguese, French, Spanish, etc.)
        pack_lang = (self.pack.header.get("language") or "").lower()
        if needs_accent_font(self.pack.header):
            self.accent_font_var.set(True)
            self._toggle_accent_font()
        # Set language combo box
        if hasattr(self, "lang_cb"):
            if pack_lang:
                self.lang_cb.set(pack_lang.upper() if pack_lang != "pt-br" else "pt-BR")
            else:
                self.lang_cb.set("Auto")
        # `rebuild_view` above only fills the first insert chunk; the rest is
        # pumped through `after_idle` by `_insert_plan`, whose last chunk
        # calls `_finish_loading`.  An empty view never reaches that chunk,
        # so close the overlay right away.
        if not self.view:
            self._finish_loading()

    def _pump_loader(self):
        if getattr(self, "_loader", None) is not None:
            self._loader.pump()

    def _finish_loading(self):
        """Close the loading overlay (no-op when none is showing)."""
        loader = getattr(self, "_loader", None)
        self._loader = None
        if loader is not None:
            loader.close()

    def reload_from_disk(self):
        if not self.pack.path:
            return
        if self.dirty and not messagebox.askyesno(
                "Discard edits", "Reload from disk and discard unsaved edits?"):
            return
        self.load_pack(self.pack.path)

    def open_pack(self):
        if self.dirty and not messagebox.askyesno(
                "Unsaved edits", "Open another pack and lose unsaved edits?"):
            return
        self.load_pack(None)

    def save_pack(self, ask=False):
        if not self.pack.path:
            if not ask:
                return
            p = filedialog.asksaveasfilename(
                defaultextension=".yaml",
                filetypes=[("YAML pack", "*.yaml *.yml")])
            if not p:
                return
            self.pack.path = p
        try:
            n = save_pack(self.pack, self.pack.path)
            self.dirty = False
            self.update_status()
            st = self.get_stats()
            self.sb.configure(text="Saved %s  (%d bytes, %d entries, %s%%)" % (
                os.path.basename(self.pack.path), n, len(self.pack.flat),
                round_1(100.0 * st["filled"] / max(1, len(self.pack.flat)))))
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    def save_pack_as(self):
        """File > Save pack as... (Ctrl+Shift+S): write MINE to a new file and
        keep working on that one.  The notes / glossary sidecars follow it,
        so they are not left behind next to the old file."""
        if not (self.pack and self.pack.flat):
            messagebox.showinfo("Save as", "No pack is loaded.")
            return "break"
        cur = self.pack.path or ""
        p = filedialog.asksaveasfilename(
            title="Save pack as",
            initialdir=os.path.dirname(cur) or None,
            initialfile=os.path.basename(cur) or "pack.yaml",
            defaultextension=".yaml",
            filetypes=[("YAML pack", "*.yaml *.yml"), ("All files", "*.*")])
        if not p:
            return "break"
        old = self.pack.path
        self.pack.path = p
        try:
            n = save_pack(self.pack, p)
        except Exception as e:                      # noqa: BLE001
            self.pack.path = old
            messagebox.showerror("Save error", str(e))
            return "break"
        self.dirty = False
        if self.notes:
            self._flush_notes()
        if self.glossary and self.glossary_path:
            gp = os.path.splitext(p)[0] + ".dict.json"
            try:
                with open(gp, "w", encoding="utf-8") as fh:
                    json.dump(self.glossary, fh, ensure_ascii=False, indent=2)
                self.glossary_path = gp
            except OSError:
                pass
        self._refresh_glossary_path()
        self._cmp_update_labels()
        self.root.title("%s  -  %s  (%s)"
                        % (APP_TITLE, os.path.basename(p), APP_REVISION))
        self.update_status()
        self.sb.configure(text="Saved as %s  (%d bytes, %d entries)" % (
            os.path.basename(p), n, len(self.pack.flat)))
        return "break"

    # -- sidecars -------------------------------------------------------------
    def _sidecar(self, suffix, default):
        if not self.pack.path:
            return None
        base = os.path.splitext(self.pack.path)[0]
        p = base + suffix
        if not os.path.exists(p) and os.path.exists(default):
            p = default
        return p

    def _load_sidecar(self):
        gp = self._sidecar(".dict.json", "legaia_dict.json")
        if gp and os.path.exists(gp):
            try:
                with open(gp, "r", encoding="utf-8") as fh:
                    self.glossary = json.load(fh)
                self.glossary_path = gp
            except Exception:
                self.glossary = {}
        else:
            self.glossary = {}
            self.glossary_path = None
        np_ = self._sidecar(".notes.json", "legaia_notes.json")
        if np_ and os.path.exists(np_):
            try:
                with open(np_, "r", encoding="utf-8") as fh:
                    self.notes = json.load(fh)
                self.notes_path = np_
            except Exception:
                self.notes = {}
        else:
            self.notes = {}
            self.notes_path = None
        self.refresh_dict_tree()
