"""Options > Function-key macros: the macro editor window.

Left: every assigned key and what it types.  Right: the editor for the
selected (or a new) macro - pick the key with modifier buttons + an F-key
list or by pressing it, type the text (quick-insert buttons for the common
tokens), and see what it means and how it renders in the real font.

Nothing touches the live bindings until Save; Cancel throws the session away.

Key strings are Tk event names: "F3", "Control-F3", "Alt-F3",
"Control-Shift-F3", "Control-Alt-F3".  Bare Shift+F1..F10 belong to colour
wrap and are refused (ui.keys._macro_key_ok drops them at run time too).

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import re
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from genesisleaf.core.encoding import TOKEN_RE, parse_text
from genesisleaf.core.legend import TOKEN_DOCS
from genesisleaf.ui import theme as _theme
from genesisleaf.ui.canvas_render import render_text_to_canvas
from genesisleaf.ui.fonts import FONT_MONO, FONT_UI, FONT_UI_B, FONT_UI_SM

# (Tk prefix, label) - the combinations a macro may use
MODIFIERS = (
    ("", "F-key"),
    ("Control-", "Ctrl"),
    ("Alt-", "Alt"),
    ("Control-Shift-", "Ctrl+Shift"),
    ("Control-Alt-", "Ctrl+Alt"),
)
QUICK_TOKENS = ("{c1:00}", "{c2:00}", "{c3:00}", "{c5:00}", "{c7:00}",
                "{cf:02}", "{cf:07}", "{ce:00}", "|", "{7b}", "{7d}")
KEY_RE = re.compile(r"^((?:Control-|Alt-|Shift-)*)F(\d{1,2})$")


def key_label(key):
    """'Control-Alt-F3' -> 'Ctrl+Alt+F3'."""
    return (key.replace("Control-", "Ctrl+").replace("Alt-", "Alt+")
               .replace("Shift-", "Shift+"))


def key_sort(key):
    m = KEY_RE.match(key)
    if not m:
        return (99, 99, key)
    order = [p for p, _l in MODIFIERS]
    mod = m.group(1)
    return (order.index(mod) if mod in order else 50, int(m.group(2)), key)


def key_problem(key):
    """Why `key` cannot hold a macro, or None."""
    m = KEY_RE.match(key)
    if not m or not 1 <= int(m.group(2)) <= 12:
        return "not a function key"
    if m.group(1) == "Shift-":
        return "bare Shift+F-keys are colour wrap ({cf:0n}...{cf:07})"
    if m.group(1) not in [p for p, _l in MODIFIERS]:
        return "use F-key, Ctrl, Alt, Ctrl+Shift or Ctrl+Alt"
    return None


class MacroEditor:
    """The macro editor window.  One instance at a time (see open())."""

    _open = None

    @classmethod
    def open(cls, app):
        cur = cls._open
        if cur is not None and cur.win.winfo_exists():
            cur.win.deiconify()
            cur.win.lift()
            cur.win.focus_force()
            return cur
        cls._open = cls(app)
        return cls._open

    def __init__(self, app):
        self.app = app
        self.macros = dict(app.macros or {})      # working copy
        self.editing = None                       # key being edited, or None
        win = self.win = tk.Toplevel(app.root)
        win.title("Function-key macros")
        win.transient(app.root)
        win.geometry("900x520")
        win.minsize(760, 440)
        win.configure(background=_theme.TH_FRAME_BG)
        win.protocol("WM_DELETE_WINDOW", self.cancel)

        head = ttk.Frame(win, padding=(12, 10, 12, 4))
        head.pack(fill="x")
        ttk.Label(head, text="Function-key macros", font=FONT_UI_B).pack(
            anchor="w")
        ttk.Label(head, font=FONT_UI_SM, foreground=_theme.TH_FG_MUTED,
                  text="A macro types its text at the caret of whichever box "
                       "has focus.  Shift+F1..F10 stay reserved for colour "
                       "wrap.").pack(anchor="w")

        body = ttk.Panedwindow(win, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=6)
        body.add(self._build_list(body), weight=2)
        body.add(self._build_editor(body), weight=3)

        foot = ttk.Frame(win, padding=(12, 4, 12, 10))
        foot.pack(fill="x")
        ttk.Button(foot, text="Reset to defaults",
                   command=self.reset_defaults).pack(side="left")
        ttk.Button(foot, text="Cancel", command=self.cancel).pack(side="right")
        ttk.Button(foot, text="Save", command=self.save).pack(
            side="right", padx=(0, 6))
        self.l_dirty = ttk.Label(foot, text="", font=FONT_UI_SM,
                                 foreground=_theme.TH_WARN)
        self.l_dirty.pack(side="right", padx=10)

        self.refresh_list()
        self.new_macro()

    # -- left: assigned keys --------------------------------------------------
    def _build_list(self, parent):
        f = ttk.Frame(parent, padding=(0, 0, 8, 0))
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)
        ttk.Label(f, text="Assigned keys", font=FONT_UI_SM,
                  foreground=_theme.TH_FG_MUTED).grid(row=0, column=0,
                                                      sticky="w")
        self.tree = ttk.Treeview(f, columns=("key", "text"), show="headings",
                                 selectmode="browse")
        self.tree.heading("key", text="Key")
        self.tree.heading("text", text="Types")
        self.tree.column("key", width=110, stretch=False)
        self.tree.column("text", width=220)
        vs = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        vs.grid(row=1, column=1, sticky="ns")
        self.tree.tag_configure("bad", foreground=_theme.TH_BAD)
        self.tree.bind("<<TreeviewSelect>>", self._on_pick)
        self.tree.bind("<Delete>", lambda e: self.remove())
        btns = ttk.Frame(f)
        btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="New", command=self.new_macro).pack(side="left")
        ttk.Button(btns, text="Remove", command=self.remove).pack(
            side="left", padx=4)
        self.l_count = ttk.Label(btns, text="", font=FONT_UI_SM,
                                 foreground=_theme.TH_FG_MUTED)
        self.l_count.pack(side="right")
        return f

    def refresh_list(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for key in sorted(self.macros, key=key_sort):
            bad = key_problem(key)
            self.tree.insert("", "end", iid=key,
                             values=(key_label(key), self.macros[key]),
                             tags=("bad",) if bad else ())
        n = len(self.macros)
        self.l_count.configure(text="%d macro%s" % (n, "" if n == 1 else "s"))
        if select and self.tree.exists(select):
            self.tree.selection_set(select)
            self.tree.see(select)

    def _on_pick(self, _evt=None):
        sel = self.tree.selection()
        if sel:
            self.load(sel[0])

    # -- right: editor -------------------------------------------------------
    def _build_editor(self, parent):
        f = ttk.Frame(parent, padding=(8, 0, 0, 0))
        f.columnconfigure(1, weight=1)
        self.l_mode = ttk.Label(f, text="", font=FONT_UI_B)
        self.l_mode.grid(row=0, column=0, columnspan=3, sticky="w",
                         pady=(0, 6))

        ttk.Label(f, text="Key", font=FONT_UI).grid(row=1, column=0,
                                                    sticky="nw", pady=4)
        keyrow = ttk.Frame(f)
        keyrow.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)
        self.mod_var = tk.StringVar(value="")
        for prefix, label in MODIFIERS:
            ttk.Radiobutton(keyrow, text=label, value=prefix,
                            variable=self.mod_var,
                            command=self._key_changed).pack(side="left",
                                                            padx=(0, 6))
        keyrow2 = ttk.Frame(f)
        keyrow2.grid(row=2, column=1, columnspan=2, sticky="w")
        self.fkey = ttk.Combobox(keyrow2, state="readonly", width=5,
                                 values=["F%d" % n for n in range(1, 13)])
        self.fkey.pack(side="left")
        self.fkey.bind("<<ComboboxSelected>>", lambda e: self._key_changed())
        self.b_capture = ttk.Button(keyrow2, text="Press a key...",
                                    command=self.capture)
        self.b_capture.pack(side="left", padx=8)
        self.l_key = ttk.Label(keyrow2, text="", font=FONT_UI_SM)
        self.l_key.pack(side="left")

        ttk.Label(f, text="Types", font=FONT_UI).grid(row=3, column=0,
                                                      sticky="nw",
                                                      pady=(12, 4))
        self.text_var = tk.StringVar()
        self.ent = ttk.Entry(f, textvariable=self.text_var, font=FONT_MONO)
        self.ent.grid(row=3, column=1, columnspan=2, sticky="ew",
                      pady=(12, 4))
        self.text_var.trace_add("write", lambda *a: self._text_changed())

        quick = ttk.Frame(f)
        quick.grid(row=4, column=1, columnspan=2, sticky="w")
        for tok in QUICK_TOKENS:
            ttk.Button(quick, text=tok, width=0, takefocus=False,
                       command=lambda t=tok: self._insert(t)).pack(
                side="left", padx=(0, 2))

        ttk.Label(f, text="Means", font=FONT_UI).grid(row=5, column=0,
                                                      sticky="nw",
                                                      pady=(10, 0))
        self.l_means = ttk.Label(f, text="", font=FONT_UI_SM, justify="left",
                                 foreground=_theme.TH_FG_MUTED,
                                 wraplength=440)
        self.l_means.grid(row=5, column=1, columnspan=2, sticky="nw",
                          pady=(10, 0))

        ttk.Label(f, text="Preview", font=FONT_UI).grid(row=6, column=0,
                                                        sticky="nw",
                                                        pady=(10, 0))
        self.cv = tk.Canvas(f, height=70, highlightthickness=0,
                            background=_theme.BG_EDIT)
        self.cv.grid(row=6, column=1, columnspan=2, sticky="ew", pady=(10, 0))
        self.cv.bind("<Configure>", lambda e: self._draw())

        act = ttk.Frame(f)
        act.grid(row=7, column=1, columnspan=2, sticky="w", pady=(12, 0))
        self.b_apply = ttk.Button(act, text="Assign", command=self.assign)
        self.b_apply.pack(side="left")
        self.l_warn = ttk.Label(act, text="", font=FONT_UI_SM,
                                foreground=_theme.TH_WARN, wraplength=360)
        self.l_warn.pack(side="left", padx=10)
        self.ent.bind("<Return>", lambda e: self.assign())
        return f

    # -- editor state ----------------------------------------------------------
    def current_key(self):
        fk = self.fkey.get()
        return (self.mod_var.get() + fk) if fk else ""

    def new_macro(self):
        self.editing = None
        self.tree.selection_remove(*self.tree.selection())
        free = next((p + "F%d" % n for p, _l in MODIFIERS
                     for n in range(1, 13)
                     if p + "F%d" % n not in self.macros
                     and not key_problem(p + "F%d" % n)), "F1")
        m = KEY_RE.match(free)
        self.mod_var.set(m.group(1))
        self.fkey.set("F" + m.group(2))
        self.text_var.set("")
        self.l_mode.configure(text="New macro")
        self.b_apply.configure(text="Assign")
        self._key_changed()
        self.ent.focus_set()

    def load(self, key):
        m = KEY_RE.match(key)
        self.editing = key
        if m:
            self.mod_var.set(m.group(1))
            self.fkey.set("F" + m.group(2))
        self.text_var.set(self.macros.get(key, ""))
        self.l_mode.configure(text="Edit %s" % key_label(key))
        self.b_apply.configure(text="Update")
        self._key_changed()

    def _insert(self, tok):
        self.ent.insert("insert", tok)
        self.ent.focus_set()

    def _key_changed(self):
        key = self.current_key()
        self.l_key.configure(text=key_label(key) if key else "")
        prob = key_problem(key) if key else "pick a key"
        if prob:
            self.l_warn.configure(text="Not allowed: " + prob,
                                  foreground=_theme.TH_BAD)
        elif key in self.macros and key != self.editing:
            self.l_warn.configure(
                text="%s already types %r - it will be replaced."
                     % (key_label(key), self.macros[key]),
                foreground=_theme.TH_WARN)
        else:
            self.l_warn.configure(text="")

    def _text_changed(self):
        text = self.text_var.get()
        self.l_means.configure(text=self.describe(text))
        self._draw()

    def describe(self, text):
        """One line per distinct token: what it is (and the name it
        splices, when the loaded pack can resolve it)."""
        if not text:
            return "-"
        lines = []
        seen = set()
        for s, e, st in parse_text(text)[1]:
            seg = text[s:e]
            if st in ("sub", "ctl"):
                m = TOKEN_RE.match(seg)
                name, arg = m.group(1).lower(), m.group(2)
                if seg in seen:
                    continue
                seen.add(seg)
                doc = TOKEN_DOCS.get(name, seg)
                extra = ""
                if st == "sub" and arg is not None:
                    try:
                        res = self.app._resolve_sub(name, arg)
                    except Exception:
                        res = None
                    if res:
                        extra = "  ->  %s" % res
                lines.append("%s  %s%s" % (seg, doc.split("  ", 1)[-1], extra))
            elif st == "newline" and "|" not in seen:
                seen.add("|")
                lines.append(TOKEN_DOCS["|"])
            elif st == "nonascii" and "nonascii" not in seen:
                seen.add("nonascii")
                lines.append(TOKEN_DOCS["nonascii"])
        n = parse_text(text)[0]
        lines.append("%d byte%s when inserted" % (n, "" if n == 1 else "s"))
        return "\n".join(lines)

    def _draw(self):
        text = self.text_var.get()
        self.cv.delete("all")
        if not text:
            return
        try:
            render_text_to_canvas(
                self.cv, [text], {"glyph_pad": 1},
                expander=self.app.markup_expander(), scale=2,
                accent_font=bool(self.app.accent_font_var.get()))
        except Exception:
            pass

    # -- capture a key press ----------------------------------------------------
    def capture(self):
        self.b_capture.configure(text="Press F1..F12 (Esc cancels)")
        self.win.focus_force()
        self.win.bind("<KeyPress>", self._captured)

    def _captured(self, evt):
        sym = evt.keysym
        if sym in ("Shift_L", "Shift_R", "Control_L", "Control_R",
                   "Alt_L", "Alt_R"):
            return "break"
        self.win.unbind("<KeyPress>")
        self.b_capture.configure(text="Press a key...")
        if sym == "Escape" or not re.match(r"^F\d{1,2}$", sym):
            return "break"
        st = int(evt.state)
        # Alt is bit 0x20000 on Windows (0x0008 there is NumLock)
        alt = st & (0x20000 if sys.platform == "win32" else 0x0008)
        mod = (("Control-" if st & 0x0004 else "")
               + ("Alt-" if alt else "")
               + ("Shift-" if st & 0x0001 else ""))
        self.mod_var.set(mod)
        self.fkey.set(sym)
        self._key_changed()
        self.ent.focus_set()
        return "break"

    # -- actions ------------------------------------------------------------------
    def _mark_dirty(self):
        self.l_dirty.configure(text="unsaved changes")

    def assign(self):
        key = self.current_key()
        text = self.text_var.get()
        prob = key_problem(key) if key else "pick a key"
        if prob:
            messagebox.showwarning("Macro", "%s: %s" % (key_label(key) or "Key",
                                                        prob), parent=self.win)
            return
        if not text:
            messagebox.showwarning("Macro", "Type the text this key inserts.",
                                   parent=self.win)
            return
        if self.editing and self.editing != key:
            self.macros.pop(self.editing, None)     # the macro moved keys
        self.macros[key] = text
        self.editing = key
        self._mark_dirty()
        self.refresh_list(select=key)
        self.l_mode.configure(text="Edit %s" % key_label(key))
        self.b_apply.configure(text="Update")
        self._key_changed()

    def remove(self):
        sel = self.tree.selection()
        key = sel[0] if sel else self.editing
        if not key or key not in self.macros:
            return
        del self.macros[key]
        self._mark_dirty()
        self.refresh_list()
        self.new_macro()

    def reset_defaults(self):
        if not messagebox.askyesno(
                "Macros", "Replace every macro with the defaults?",
                parent=self.win):
            return
        self.macros = dict(self.app.DEFAULT_MACROS)
        self._mark_dirty()
        self.refresh_list()
        self.new_macro()

    def save(self):
        self.app.set_macros(self.macros)
        self.close()

    def cancel(self):
        if self.l_dirty.cget("text") and not messagebox.askyesno(
                "Macros", "Discard the unsaved macro changes?",
                parent=self.win):
            return
        self.close()

    def close(self):
        MacroEditor._open = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass
