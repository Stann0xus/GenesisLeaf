"""Responsive Insert-token button strip with the 'More' overflow menu.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk


class TokenBarMixin:
    """Responsive Insert-token button strip with the 'More' overflow menu.

    Mixed into `App`; `self` is the main window.
    """

    # -- responsive insert-token strip ---------------------------------------
    def _relayout_tokens(self, _e=None):
        if self._tok_job is not None:
            try:
                self.root.after_cancel(self._tok_job)
            except (tk.TclError, ValueError):
                pass
        self._tok_job = self.root.after(40, self._tok_layout_now)

    def _rebuild_tok_menu(self, shown):
        self._tok_menu.delete(0, "end")
        for b in self._tok_btns[shown:]:
            tok = b.cget("text")
            self._tok_menu.add_command(label=tok,
                                       command=lambda s=tok:
                                       self.insert_token(s))

    def _tok_more_menu(self):
        if self._tok_menu.index("end") is None:
            return
        try:
            self._tok_menu.tk_popup(self._tok_more.winfo_rootx(),
                                    self._tok_more.winfo_rooty()
                                    + self._tok_more.winfo_height())
        finally:
            self._tok_menu.grab_release()

    def _tok_cache_sizes(self):
        """Record each token button's pixel width at the current size, once we
        actually have it laid out, so the layout decision never depends on
        measuring through a stale configuration."""
        if self._tok_sizes is None:
            if all(b.winfo_ismapped() for b in self._tok_btns):
                self._tok_sizes = {k: b.winfo_reqwidth()
                                   for k, b in enumerate(self._tok_btns)}
        if self._tok_sizes_c is None:
            if self._tok_compact and \
                    all(b.winfo_ismapped() for b in self._tok_btns):
                self._tok_sizes_c = {k: b.winfo_reqwidth()
                                     for k, b in enumerate(self._tok_btns)}

    def _tok_width_at(self, sizes, more):
        if sizes is None:
            return None
        return sum(v + 2 for v in sizes.values()) + \
            (more + 2 if more else 0)

    def _tok_layout_now(self):
        self._tok_job = None
        self._tok_cache_sizes()
        row = self.tok_row
        w = row.winfo_width()
        n = len(self._tok_btns)
        if w < 40:
            return
        base = self._tok_label.winfo_reqwidth() + 8
        hint_w = self._tok_hint.winfo_reqwidth() + 12
        full = self._tok_width_at(self._tok_sizes, 0)
        # phase A: pick the mode; shrinking the buttons triggers a remeasure,
        # so the first "cramp" pass only re-sizes and defers to the next one
        if full is not None and w - base - hint_w >= full:
            want_compact, hint = False, True
        else:
            want_compact, hint = True, False
        if want_compact != self._tok_compact:
            # phase A needs a remeasure: applied a not-yet-measured size
            if want_compact:
                for b in self._tok_btns:
                    b.configure(width=4)
                self._tok_more.configure(width=5)
            else:
                for b in self._tok_btns:
                    b.configure(width=7)
                self._tok_more.configure(width=6)
            self._tok_compact = want_compact
            self.root.after_idle(self._tok_layout_now)
            return
        # phase B: with measured sizes in hand, count what fits
        hint_on = hint
        if not want_compact:
            shown = n
        else:
            shown = 0
            if self._tok_sizes_c is not None:
                acc = 0
                more_req = self._tok_more.winfo_reqwidth() + 2
                for v in self._tok_sizes_c.values():
                    need = v + 2
                    if acc + need + more_req > w - base:
                        break
                    acc += need
                    shown += 1
            else:
                shown = n
        # apply the decision
        if hint_on and not self._tok_hint.winfo_ismapped():
            self._tok_hint.pack(side="right")
        elif not hint_on and self._tok_hint.winfo_ismapped():
            self._tok_hint.pack_forget()
        for k, b in enumerate(self._tok_btns):
            if k < shown:
                if not b.winfo_ismapped():
                    b.grid()
            elif b.winfo_ismapped():
                b.grid_remove()
        if n - shown > 0:
            if not self._tok_more.winfo_ismapped():
                self._tok_more.grid()
        elif self._tok_more.winfo_ismapped():
            self._tok_more.grid_remove()
        if getattr(self, "_tok_shown", None) != shown:
            self._rebuild_tok_menu(shown)
            self._tok_shown = shown
        self._tok_compact = want_compact
