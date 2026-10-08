"""Find box, search scopes, and metadata/status filters.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk

from genesisleaf.core.dialog import _hex_group_label
from genesisleaf.core.encoding import parse_text
from genesisleaf.core.space import verdict as space_verdict
from genesisleaf.ui import theme as _theme


class FindFilterMixin:
    """Find box, search scopes, and metadata/status filters.

    Mixed into `App`; `self` is the main window.
    """

    # -- filtering / tree --------------------------------------------------------
    def clear_search(self):
        self._cancel_search()
        self.search_ent.delete(0, "end")
        self._find_hits = None
        self.find_lab.configure(text="")
        self.rebuild_view()

    def _on_scope_change(self, _evt=None):
        """A new scope changes what counts as a hit, so the cached list, the
        table filter and the tally all have to be redone."""
        self._cancel_search()
        self.find_scope = self.scope_cb.get() or "All"
        self._find_hits = None
        self.rebuild_view()
        q = self.search_ent.get().strip()
        if q:
            self._find_enter()
        self.persist_settings()

    def _on_filter_toggle(self):
        """Filter on = the Find text narrows the table.  Off = the table is left
        exactly as it is and the Find text only steers the selection."""
        self._cancel_search()
        self._find_hits = None
        if self.find_filter_var.get():
            self.rebuild_view()
        else:
            self._find_step(1)

    def _schedule_search(self):
        self._cancel_search()
        self._search_job = self.root.after(2000, self._run_scheduled_search)

    def _cancel_search(self):
        if self._search_job:
            self.root.after_cancel(self._search_job)
            self._search_job = None

    def _run_scheduled_search(self):
        self._search_job = None
        if self.find_filter_var.get():
            self.rebuild_view()
        else:
            self._find_step(1)

    def _find_enter(self):
        self._cancel_search()
        self._run_scheduled_search()

    def _scope_haystack(self, e, scope=None):
        """The text a search should look inside, per the chosen scope.

        "All" is the historical behaviour: key + context + source + translation.
        The narrower scopes exist because a context line is full of asset names
        ("Ponte", "m01_ita") that collide with real dialogue words and drown the
        results, so you can now look only at the text the player reads.
        """
        scope = scope or getattr(self, "find_scope", "All")
        if scope == "Source":
            return e.get("source", "")
        if scope == "Translation":
            return e.get("translation", "")
        if scope == "Source+Translation":
            return e.get("source", "") + " " + e.get("translation", "")
        if scope == "Context":
            return e.get("context", "")
        return (e.get("key", "") + " " + e.get("context", "") + " " +
                e.get("source", "") + " " + e.get("translation", ""))

    def find_matches(self, q, scope=None):
        """Flat indices whose text holds `q`, in file order.  Same haystack the
        table filter uses, so the two modes never disagree about what counts as
        a hit."""
        q = q.strip().lower()
        if not q:
            return []
        out = []
        for i, (_sec, e) in enumerate(self.pack.flat):
            if q in self._scope_haystack(e, scope).lower():
                out.append(i)
        return out

    def _find_hits_for(self, q, scope=None):
        """Cached hit list, recomputed when the query text or scope changes.

        A cached list goes stale as soon as a translation changes - editing the
        row you are standing on can add or remove a match.  Both rebuild_view
        and on_tr_modified drop the cache, so the tally can never disagree with
        the table.  The scope is part of the cache key for the same reason:
        switching from "All" to "Source" must not serve the wider hit list."""
        scope = scope or getattr(self, "find_scope", "All")
        if self._find_hits is None or self._find_hits[:2] != (q, scope):
            self._find_hits = (q, scope, self.find_matches(q, scope))
        return self._find_hits[2]

    def _find_step(self, d=1):
        """Walk the selection onto the next/previous hit without touching the
        table.  Reports the tally beside the Find box."""
        if not hasattr(self, "l_join") and not hasattr(self, "find_lab"):
            return
        q = self.search_ent.get().strip()
        if not q:
            self.find_lab.configure(text="")
            return
        hits = self._find_hits_for(q)
        if not hits:
            self.find_lab.configure(
                text="no match", foreground=_theme.TH_BAD)
            return
        cur = self.current
        nxt = None
        for i in hits:
            if (d > 0 and i > cur) or (d < 0 and i < cur):
                nxt = i
                break
        if nxt is None:                 # wrapped round the end
            nxt = hits[0] if d > 0 else hits[-1]
        self._reveal_flat_keep_find(nxt)
        self.find_lab.configure(
            text="%d found - %d of %d" % (len(hits), hits.index(nxt) + 1,
                                          len(hits)),
            foreground=_theme.TH_OK if len(hits) > 1 else _theme.TH_WARN)

    def _reveal_flat_keep_find(self, i):
        """Select flat row `i` while keeping the Find box intact.

        `jump_to_flat` clears the Find text when the row is not on screen, which
        is right for the word-search tab but wrong here - that box is the cursor
        of this find.  So the section/status filters are dropped instead, and the
        Find text is kept out of `_filters` for the one rebuild that exposes the
        row."""
        if self._iid_of(i) is None:
            self.sec_cb.current(0)
            self.st_cb.current(0)
            self.ctx_cb.current(0)
            self.filter_field = "Section"
            self.filter_value = "All"
            if hasattr(self, "filter_by_cb"):
                self.filter_by_cb.set("Section")
            self._search_ignore = True
            try:
                self.rebuild_view()
            finally:
                self._search_ignore = False
        if self._iid_of(i) is None:
            return
        iid = self._iid_of(i)
        if iid is not None:
            self._select_lock = True
            try:
                self.tree.selection_set(iid)
                self.tree.see(iid)
            finally:
                self._select_lock = False
        self.select_entry(i)

    def _metadata_matches(self, sec, e):
        field = getattr(self, "filter_field", "Section")
        value = getattr(self, "filter_value", "All")
        if value != "All":
            if field == "Section" and sec != value:
                return False
            if field == "Context" and e.get("context", "") not in self._ctx_match:
                return False
            if field == "Key" and e.get("key", "") != value:
                return False
            if field == "Budget":
                try:
                    if int(e.get("budget", 0)) != int(value):
                        return False
                except (TypeError, ValueError):
                    return False
        return True

    def _filters(self, idx, ignore_metadata=False):
        sec, e = self.pack.flat[idx]
        if not ignore_metadata and not self._metadata_matches(sec, e):
            return False
        tr = e.get("translation", "")
        st = self.filter_status
        if st == "Untranslated" and tr:
            return False
        if st == "Translated" and not tr:
            return False
        if st in ("Won't fit", "Grows (free space)"):
            want = "over" if st == "Won't fit" else "grows"
            b, _ = parse_text(tr)
            if not tr or space_verdict(sec, e, b) != want:
                return False
        if st == "Overdraw (source)":
            if not self.row_overdraw(idx, e.get("source", ""))[1]:
                return False
        if st == "Overdraw (translation)":
            if not (tr and self.row_overdraw(idx, tr)[1]):
                return False
        if st == "Has non-ASCII":
            if not any(style == "nonascii" for _, _, style in parse_text(tr)[1]):
                return False
        if self.filter_text:
            t = self.filter_text.lower()
            if t not in self._scope_haystack(e).lower():
                return False
        return True

    def _context_names(self, sec):
        """Sorted, de-duplicated context strings present in the current pack
        for `sec` (or across every section when sec is "All").

        Contexts are grouped when their only distinguishing part is a hex id
        token: "item 0x3c", "item 0x3d". . . collapse to a single "item 0x.."
        entry instead of hundreds of rows.  Two or more DISTINCT raw strings
        must share the shorn label for the group to appear, so a prompt that
        has a lone hex token in it stays an individual entry.
        Returns (names, {label: {raw_context, ...}})."""
        if getattr(self, "_ctx_cache", None) is None:
            self._ctx_cache = {}
        if sec in self._ctx_cache:
            return self._ctx_cache[sec]
        if sec == "All":
            ctxs = {e.get("context", "") for _, e in self.pack.flat}
        else:
            ctxs = {e.get("context", "") for s, e in self.pack.flat
                    if s == sec}
        ctxs.discard("")
        groups = {}
        singles = set()
        for c in ctxs:
            label = _hex_group_label(c)
            if label and label != c:
                groups.setdefault(label, set()).add(c)
            else:
                singles.add(c)
        names = sorted(singles)
        for label in sorted(groups):
            if len(groups[label]) >= 2:
                names.append(label)
        result = (names, groups)
        self._ctx_cache[sec] = result
        return result

    def _refresh_ctx_filter(self):
        """Re-sync the Context dropdown with the current section, keeping the
        selection when it still exists in that section, else back to "All"."""
        try:
            keep = self.ctx_cb.get() or "All"
        except tk.TclError:
            keep = "All"
        names, groups = self._context_names(
            getattr(self, "filter_section", "All"))
        vals = ["All"] + names
        self._ctx_groups = groups
        try:
            self.ctx_cb.configure(values=vals)
            self.ctx_cb.set(keep if keep in vals else "All")
        except tk.TclError:
            pass

    def _ctx_set_for(self, label):
        """Raw context strings that a Context-dropdown `label` selects; the
        identity set for a single prompt, the whole renamed group otherwise."""
        g = getattr(self, "_ctx_groups", None) or {}
        if label in g:
            return g[label]
        if label == "(none)":
            return {""}
        return {label}

    # -- programmatic filters (Progress window, navigator sidebar) ----------
    def _set_metadata_filter(self, field, value):
        """Set one safe, non-editable metadata filter and rebuild the table."""
        if field not in ("Section", "Context", "Key", "Budget"):
            field, value = "Section", "All"
        self.filter_field = field
        self.filter_value = value or "All"
        self.filter_section = self.filter_value if field == "Section" else "All"
        self.filter_context = self.filter_value if field == "Context" else "All"
        self.rebuild_view()

    def set_section_filter(self, sec):
        """Show only section `sec` ("All" for every section)."""
        if sec != "All" and sec not in self.pack.section_names:
            sec = "All"
        self.sec_cb.set(sec)
        self.ctx_cb.set("All")
        self._set_metadata_filter("Section", sec)

    def set_context_filter(self, ctx):
        """Show only rows whose context is `ctx`, across every section.
        A context that the dropdown lists under a hex group ("item 0x..")
        selects that group."""
        self.sec_cb.set("All")
        names, groups = self._context_names("All")
        label = ctx
        if ctx not in names:
            label = next((g for g, raws in groups.items() if ctx in raws
                          and g in names), "All")
        self._ctx_groups = groups
        self.ctx_cb.configure(values=["All"] + names)
        self.ctx_cb.set(label)
        self._set_metadata_filter("Context", label)

    def set_metadata_filter(self, field, value):
        """Public callback used by the navigator for Key and Budget filters."""
        self.sec_cb.set("All")
        self.ctx_cb.set("All")
        if field == "Context":
            names, groups = self._context_names("All")
            self._ctx_groups = groups
            value = value if value in names else "All"
            self.ctx_cb.configure(values=["All"] + names)
            self.ctx_cb.set(value)
        self._set_metadata_filter(field, value)

    def set_status_filter(self, status):
        """One of the Status dropdown values ("All", "Untranslated", ...)."""
        vals = list(self.st_cb["values"])
        self.st_cb.set(status if status in vals else "All")
        self.rebuild_view()
