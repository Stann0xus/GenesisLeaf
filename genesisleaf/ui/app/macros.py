"""Function-key macros: defaults, binding, running and the macro editor.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import re
import tkinter as tk

from genesisleaf.ui.keys import _macro_key_ok
from genesisleaf.ui.windows.macro_editor import MacroEditor


class MacroMixin:
    """Function-key macros: defaults, binding, running and the macro editor.

    Mixed into `App`; `self` is the main window.
    """

    # -- F1..F12 macro layer -------------------------------------------------
    # The name-substitution codes ({c1:00} = "Pontos-Cart" and friends) are
    # fixed per game, so they are the one thing you type over and over while
    # translating.  A macro turns each into a single key press.  The map is
    # user-editable, because the useful set depends on which names the project
    # actually uses, and it is stored in the settings file, not the pack.
    DEFAULT_MACROS = {
        "F1": "{c1:00}", "F2": "{c1:01}", "F3": "{c1:02}",
        "F4": "{c2:00}",
    }

    def bind_macros(self, w=None):
        """(Re)bind the macro keys on the root and on an editor.

        Bound on the root as well as the editors because a macro is just as
        useful while the cursor is in the Find box as while you are typing a
        line, and because the root binding is what makes the key work in a
        second view window.  Keys are Tk event names: "F1", "Control-F1",
        "Alt-F1", "Control-Shift-F1", "Control-Alt-F1".

        Keys bound by an earlier call that no longer hold a macro are
        unbound, so removing a macro really frees its key."""
        bound = getattr(self, "_macro_bound", None)
        if bound is None:
            bound = self._macro_bound = {}       # widget path -> {key}
        live = {k for k, tok in (self.macros or {}).items()
                if tok and re.search(r"F\d{1,2}$", k)}
        for target in filter(None, (self.root, w)):
            path = str(target)
            for key in bound.get(path, set()) - live:
                try:
                    target.unbind("<%s>" % key)
                except tk.TclError:
                    pass
            done = set()
            for key in live:
                cmd = lambda e, t=self.macros[key]: self.run_macro(t, e)
                try:
                    target.bind("<%s>" % key, cmd)
                    done.add(key)
                except tk.TclError:
                    pass
            bound[path] = done

    def set_macros(self, macros):
        """Replace the macro map (the editor's Save), rebind and persist."""
        self.macros = dict(macros)
        self.bind_macros(self.tr_txt)
        for v in list(getattr(self, "_views", ()) or ()):
            try:
                self.bind_macros(v.tr_txt)
            except (AttributeError, tk.TclError):
                pass
        self.persist_settings()
        self.update_status()
        self.flash("macros saved (%d)" % len(self.macros))

    def run_macro(self, tok, evt=None):
        """Insert a macro at the caret of whichever editor has focus."""
        if not _macro_key_ok(evt):
            return "break"
        w = self.root.focus_get()
        if not isinstance(w, (tk.Text, tk.Entry)):
            w = self.tr_txt
        try:
            w.insert("insert", tok)
            w.edit_modified(True)
        except tk.TclError:
            return "break"
        self.on_tr_modified()
        return "break"

    def open_macro_editor(self):
        """Options > Edit function-key macros (ui/windows/macro_editor.py)."""
        return MacroEditor.open(self)

    def reset_macros(self):
        self.set_macros(self.DEFAULT_MACROS)
