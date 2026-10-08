"""Join identical sources + clone navigation (whole-unit signatures, conflicts).

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from genesisleaf.core.bookkeeping import (
    date_known, edited_on, is_join_owned, stamp_edited,
)
from genesisleaf.core.constants import JOIN_DELAY_MS
from genesisleaf.core.textfix import oneline
from genesisleaf.ui.fonts import FONT_MONO, FONT_UI
from genesisleaf.ui import theme as _theme


class JoinMixin:
    """Join identical sources + clone navigation (whole-unit signatures, conflicts).

    Mixed into `App`; `self` is the main window.
    """

    # -- "join identical sources" + row copy/paste --------------------------
    def _join_units(self):
        """Every multi-line unit in the pack, in flat order.  A unit is one
        dialogue box (every row the retail pager packs into it) or a lone row
        for the single-string sections.  Built in one pass off the box map -
        `box_rows` is O(len(box_map)) per call, so asking it per entry would be
        quadratic over a 31k-row pack."""
        cached = getattr(self, "_join_unit_cache", None)
        if cached is not None:
            return cached
        boxes = self.box_map()
        by_box = {}
        for i, (b, row) in boxes.items():
            by_box.setdefault(b, []).append((row, i))
        units = [tuple(i for _r, i in sorted(v)) for v in by_box.values()]
        seen = set(boxes)
        units.extend((i,) for i in range(len(self.pack.flat)) if i not in seen)
        units.sort()
        self._join_unit_cache = units
        return units

    def _unit_of(self, idx):
        """The multi-line unit `idx` belongs to, as a tuple of flat indices.

        A tuple, not a list: `_join_groups()` hands back tuples, and callers
        compare a unit against its peers, so the two have to be the same type.
        """
        if 0 <= idx < len(self.pack.flat):
            return tuple(self.box_rows(idx))
        return (idx,)

    def _join_groups(self):
        """unit signature -> [unit, unit, ...], only for units that repeat.

        The signature is the tuple of the unit's row sources *in order*, so a
        dialogue box only ever groups with another box whose every single row
        matches.  Joining row-by-row instead (what the old source-string index
        did) let one line of a box clone into a different box and leave the
        rest of that box's lines behind, which is exactly the case where the
        duplicate is not a duplicate."""
        if getattr(self, "_join_groups_ready", False):
            return self._join
        g = {}
        for u in self._join_units():
            sig = tuple(self.pack.flat[j][1].get("source", "") for j in u)
            if not any(sig):
                continue
            g.setdefault(sig, []).append(u)
        self._join = {sig: us for sig, us in g.items() if len(us) > 1}
        self._join_groups_ready = True
        return self._join

    def _update_join_label(self):
        if not hasattr(self, "l_join"):
            return
        if self._join_job is not None:
            self.l_join.configure(
                text="joining in %.1fs..." % (JOIN_DELAY_MS / 1000.0))
            return
        if not self.join_var.get():
            self.l_join.configure(text="")
            return
        groups = self._join_groups()
        units = sum(len(v) for v in groups.values())
        rows = sum(len(u) for v in groups.values() for u in v)
        both = "both ways" if self.clone_back_var.get() else "forward only"
        self.l_join.configure(
            text="%d identical groups (%d rows) - edits copy %s"
                 % (units, rows, both))

    def _on_join_toggle(self):
        if self.join_var.get():
            self.b_clone_back.state(["!disabled"])
            self._update_join_label()
            if self.current >= 0:
                self._schedule_join(self.current)
        else:
            self._cancel_join()
            self.b_clone_back.state(["disabled"])
            self.l_join.configure(text="")
            self.update_preview()
            self.update_status()

    def _cancel_join(self):
        """Drop a buffered join that has not fired yet."""
        if self._join_job is not None:
            try:
                self.root.after_cancel(self._join_job)
            except Exception:
                pass
            self._join_job = None
        self._join_pending = None

    def _schedule_join(self, idx):
        """Buffer the join so it runs once the user stops typing.

        `on_tr_modified` fires on every keystroke, and one pass rewrites every
        duplicate unit - on a big group that is hundreds of rows plus a possible
        conflict dialog.  Doing it per character froze the window, so the pass
        is debounced: each keystroke pushes the timer out and only the last one
        in a burst does the work."""
        if not self.join_var.get():
            return
        self._join_pending = idx
        if self._join_job is not None:
            try:
                self.root.after_cancel(self._join_job)
            except Exception:
                pass
        self._join_job = self.root.after(JOIN_DELAY_MS, self._run_scheduled_join)
        self._update_join_label()

    def _run_scheduled_join(self):
        self._join_job = None
        idx, self._join_pending = self._join_pending, None
        self._update_join_label()
        if idx is not None:
            self._propagate_join(idx)

    def _join_targets(self, idx):
        """Units a join from `idx` may write: the other units carrying the
        identical whole-unit signature.  Forward only unless "Clone backwards"
        is on, in which case earlier units join in too.  A box is a contiguous
        run of flat rows, so a unit either starts after `idx` or ends before it -
        none can straddle the entry being edited."""
        unit = self._unit_of(idx)
        sig = tuple(self.pack.flat[j][1].get("source", "") for j in unit)
        if not any(sig):
            return unit, []
        peers = self._join_groups().get(sig, [])
        out = [u for u in peers if u[0] > idx]
        if self.clone_back_var.get():
            out.extend(u for u in peers if u[0] < idx)
        out.sort()
        return unit, out

    def _own(self, e):
        """Mark an entry's translation as the user's own rather than a join's,
        so a later join asks before replacing it."""
        e["joined"] = ""
        stamp_edited(e)
        # The stored stamp only has minute resolution, so two edits in the same
        # minute would tie.  A session counter is kept in memory (never
        # serialized) purely to break those ties, which is what lets "Edited"
        # walk back through a burst of work in the order you actually did it.
        self._edit_seq[id(e)] = self._edit_clock
        self._edit_clock += 1
        self._join_skip.discard(e.get("uuid", ""))

    # -- "Next Clone": walk the duplicates of the row you are sitting on ------
    def _clone_group(self, idx):
        """`(unit, peers)` for `idx`: its own unit, and every unit in the pack
        carrying the identical whole-unit signature - the very same set a join
        would write between.  `peers` always includes the unit holding `idx`,
        and is a one-element list when the entry is unique."""
        unit = self._unit_of(idx)
        sig = tuple(self.pack.flat[j][1].get("source", "") for j in unit)
        if not any(sig):
            return unit, []
        return unit, self._join_groups().get(sig, [])

    def _clone_pos(self, start, peers):
        """Where the unit beginning at flat row `start` sits in `peers`.

        Compared on the unit's *first row*, not the row's offset inside its own
        unit - the offset is always 0, which would pin every unit to position 0."""
        for n, u in enumerate(peers):
            if u[0] == start:
                return n
        return -1

    def _update_clone_label(self):
        """Where the current row sits inside its own group: "clone 3 of 447".

        Derived from whatever `self.current` is, so it is recomputed on every
        selection change rather than only when the button is pressed - otherwise
        it would sit there showing the last group you walked through."""
        if self.l_clone is None:
            return
        if not (0 <= self.current < len(self.pack.flat)):
            self.l_clone.configure(text="", foreground=_theme.TH_FG_MUTED)
            return
        unit, peers = self._clone_group(self.current)
        if len(peers) < 2:
            self.l_clone.configure(text="unique", foreground=_theme.TH_FG_MUTED)
            return
        at = self._clone_pos(unit[0], peers)
        if at < 0:
            self.l_clone.configure(text="clone ? of %d" % len(peers),
                                   foreground=_theme.TH_FG_MUTED)
            return
        self.l_clone.configure(
            text="clone %d of %d" % (at + 1, len(peers)),
            foreground=_theme.TH_OK if len(peers) > 2 else _theme.TH_WARN)

    def next_clone(self, d=1):
        """Move the highlight onto the next row that is a clone of this one.

        "Clone" is the whole-unit signature, not just this line: a 3-row dialog
        box only moves to another box whose every row matches, which is the same
        rule the join copies under, so walking the group is walking exactly what
        a join would change.  Wraps round the end so the group can be cycled,
        and works whether or not the join checkbox is on."""
        if not (0 <= self.current < len(self.pack.flat)):
            return "break"
        unit, peers = self._clone_group(self.current)
        if len(peers) < 2:
            self.l_clone.configure(text="unique", foreground=_theme.TH_FG_MUTED)
            return "break"
        at = self._clone_pos(unit[0], peers)
        self.jump_to_flat(peers[(at + d) % len(peers)][0], keep_search=True)
        self._update_clone_label()
        return "break"

    def _join_conflicts(self, idx, targets):
        """(src_row, dst_row) pairs whose destination text would be replaced by
        something the user owns, plus which of them the unknown date is enough
        to ask about.

        The date decides.  A destination stamped `edited` is text a human
        wrote, so a join that would replace it asks.  A destination with no
        stamp is a row nobody has ever touched (or one from a .yaml written
        before the bookkeeping existed), and that splits by direction:

          * forward  - j > i.  The edit is still travelling down the file, so an
            undated row is just a slot waiting to be filled; overwrite it
            silently and stamp it as the join runs.
          * backward - j < i, only reachable with "Clone backwards".  Reaching
            backwards can land on the *published* copy of a line, so an undated
            row is exactly the ambiguous case and gets asked per row.

        A destination the join itself wrote carries `joined` == this source's
        uuid, so re-running never re-asks for it; and a row the user has chosen
        to leave alone is remembered in `_join_skip` for the session so the
        prompt appears once, not once per character."""
        _, e0 = self.pack.flat[idx]
        src_uuid = e0.get("uuid", "")
        mine = self._unit_of(idx)
        pairs = []
        for u in targets:
            for i, j in zip(mine, u):
                if i == j:
                    continue
                _, ej = self.pack.flat[j]
                if ej.get("translation", "") == self.pack.flat[i][1].get(
                        "translation", ""):
                    continue
                if ej.get("uuid", "") in self._join_skip:
                    continue
                if not is_join_owned(ej) and not ej.get("translation", "").strip():
                    continue          # nothing to lose, overwrite silently
                if is_join_owned(ej) and ej.get("joined") == src_uuid:
                    continue          # ours already, refresh silently
                if j > i and not date_known(ej):
                    # forward + undated: the edit is still travelling down the
                    # file, so this row is a slot nobody has ever typed into.
                    # Fill it and stamp it; there is nothing to ask about.
                    continue
                pairs.append((i, j))
        return pairs

    def _join_conflict_split(self, pairs):
        """(batch_pairs, per_row_pairs).

        `batch_pairs` can be answered in one messagebox; `per_row_pairs` needs
        its own question per row because the undated-backwards case may be
        rewriting text the user cannot have knowingly signed off on."""
        batch, per_row = [], []
        for i, j in pairs:
            _, ej = self.pack.flat[j]
            if j < i and not date_known(ej):
                per_row.append((i, j))
            else:
                batch.append((i, j))
        return batch, per_row

    def _join_conflict_rows(self, pairs):
        """(key, edited, current, incoming) tuples, in file order, for the
        confirmation box."""
        out = []
        for i, j in sorted(pairs, key=lambda p: p[1]):
            _, ej = self.pack.flat[j]
            out.append((ej.get("key", ""), edited_on(ej) or "unknown",
                        ej.get("translation", "") or "",
                        self.pack.flat[i][1].get("translation", "") or ""))
        return out

    def _ask_join_conflicts(self, idx, pairs, what="later"):
        """Warn before a join clobbers rows the user edited.  Yes = overwrite
        them, No = leave those rows alone (the rest of the group still syncs).
        Returns the set of destination indices the user agreed to overwrite."""
        batch, per_row = self._join_conflict_split(pairs)
        allowed = set()
        # Only ask the batch question when there is a batch to ask about: a
        # backward join over undated rows produces per_row prompts *only*, and
        # asking anyway put a dialog on screen reading "0 earlier row(s)
        # already hold a translation the join would replace" - a question about
        # nothing, whose answer decided nothing.
        if batch:
            lines = ["  %s  (edited %s)\n      was: %s"
                     % (key, when, oneline(cur) or "(empty)")
                     for key, when, cur, _inc in self._join_conflict_rows(batch)]
            head = ("%d %s row(s) already hold a translation the join would\n"
                    "replace.  Declining keeps them out of the join until you\n"
                    "edit that row again; the other rows still sync.\n\n"
                    % (len(lines), what))
            ok = messagebox.askyesno(
                "Join identical sources", head + "\n".join(lines[:8])
                + ("\n  ... and %d more" % (len(lines) - 8) if len(lines) > 8 else "")
                + "\n\nOverwrite the edited rows?", icon="warning")
            if ok:
                allowed = {j for _i, j in batch}
            else:
                self._join_skip.update(
                    self.pack.flat[j][1].get("uuid", "") for _i, j in batch)
        if per_row:
            allowed |= self._ask_join_conflicts_one(
                what, per_row, self._join_conflict_rows(per_row))
        return allowed

    def _ask_join_conflicts_one(self, what, pairs, rows):
        """One question per row, over a tab-separated listing of the whole
        batch so every candidate can be checked by eye before answering.

        The listing is the point: a single yes/no over twenty keys tells you
        nothing about what you are about to throw away.  Here each line is
        `key <tab> edited <tab> current <tab> incoming`, the current row is
        highlighted, and Yes/No apply to that row alone.  Returns the flat
        indices the user approved."""
        n = len(rows)
        allowed = set()
        dlg = tk.Toplevel(self.root)
        dlg.title("Join identical sources")
        dlg.transient(self.root)
        dlg.geometry("1000x430")
        f = ttk.Frame(dlg, padding=8)
        f.pack(fill="both", expand=True)
        state = {"row": 0}

        ttk.Label(
            f, font=FONT_UI, justify="left", anchor="w",
            text="%d earlier row(s) with no edit date, one at a time.\n"
                 "Cloning backwards can land on a line that is already live, so "
                 "each one is asked on its own." % n).pack(anchor="w")

        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=6)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        txt = tk.Text(body, height=14, font=FONT_MONO, wrap="none",
                      state="disabled")
        txt.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
        vs.grid(row=0, column=1, sticky="ns")
        txt.configure(yscrollcommand=vs.set, tabs=(220, 340, 640))
        txt.tag_configure("cur", background="#ffe9a8", foreground="#000")
        txt.tag_configure("now", background="#cdeccd")

        def fill():
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            for key, when, cur, inc in rows:
                txt.insert("end", "%s\t%s\t%s\t%s\n"
                           % (key, when, oneline(cur), oneline(inc)))
            txt.configure(state="disabled")

        def mark():
            r = state["row"]
            txt.tag_remove("cur", "now", "1.0", "end")
            start = "1.0" if r == 0 else "%d.0" % (r + 1)
            end = "2.0" if r == 0 else txt.index("%d.0 lineend" % (r + 2))
            txt.tag_add("cur", start, end)
            txt.see(start)

        lbl = ttk.Label(f, font=FONT_MONO, justify="left", anchor="w")

        def ask():
            if state["row"] >= n:
                dlg.destroy()
                return
            key, when, cur, inc = rows[state["row"]]
            lbl.configure(
                text="Row %d of %d   %s   (edited: %s)\n"
                     "  replacing:  %s\n  with:       %s"
                     % (state["row"] + 1, n, key, when,
                        oneline(cur) or "(empty)", oneline(inc) or "(empty)"))
            mark()
            dlg.update_idletasks()

        def step(save):
            if save:
                allowed.add(pairs[state["row"]][1])
            state["row"] += 1
            ask()

        b = ttk.Frame(f)
        b.pack(fill="x")
        ttk.Button(b, text="Overwrite this row", width=22,
                   command=lambda: step(True)).pack(side="left")
        ttk.Button(b, text="Leave this row alone", width=22,
                   command=lambda: step(False)).pack(side="left", padx=4)
        ttk.Button(b, text="Stop - leave the rest alone", width=26,
                   command=dlg.destroy).pack(side="left", padx=4)
        lbl.pack(fill="x", pady=(6, 0))
        fill()
        ask()
        dlg.grab_set()
        self.root.wait_window(dlg)
        return allowed

    def _propagate_join(self, idx):
        """Share this unit's translations with every LATER unit that is
        identical row for row, when the join checkbox is on.  Never touches a
        row at or before `idx`, and asks first before replacing a later row
        the user edited."""
        if not self.join_var.get() or not (0 <= idx < len(self.pack.flat)):
            return
        unit, targets = self._join_targets(idx)
        if not targets:
            return
        conflicts = self._join_conflicts(idx, targets)
        back = self.clone_back_var.get()
        # only the rows the user was asked about are subject to the answer;
        # `allowed` is None when there was nothing to ask about, so `denied`
        # stays empty and the whole group syncs
        denied = {j for _i, j in conflicts} - set(
            self._ask_join_conflicts(
                idx, conflicts, "earlier" if back else "later")) \
            if conflicts else set()
        _, e0 = self.pack.flat[idx]
        src_uuid = e0.get("uuid", "")
        wrote = 0
        for u in targets:
            for i, j in zip(unit, u):
                if i == j or j in denied:
                    continue
                _, ei = self.pack.flat[i]
                _, ej = self.pack.flat[j]
                val = ei.get("translation", "")
                if ej.get("translation", "") == val:
                    continue
                ej["translation"] = val
                ej["joined"] = src_uuid
                stamp_edited(ej)
                wrote += 1
                self.dirty = True
                iid = self._iid_of(j)
                if iid is not None:
                    self.update_tree_row(iid, j)
                self._refresh_ed_line(j)
        if wrote:
            self.invalidate_stats()
        self.update_preview()
        self.update_status()
