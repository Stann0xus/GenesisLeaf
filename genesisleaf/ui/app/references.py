"""Name references and the {cN:..} markup expander, dialog box map.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import re

from genesisleaf.core.encoding import C7_NAMES
from genesisleaf.core.names import NAME_FIELD, game_name
from genesisleaf.core.textfix import ascii_fold


class ReferencesMixin:
    """Name references and the {cN:..} markup expander, dialog box map.

    Mixed into `App`; `self` is the main window.
    """

    # -- live preview ----------------------------------------------------------------
    def build_ref_names(self):
        """Index the pack's name tables for the plain-text preview chips.
        Each reference prefers the entry's translation (the game's string pool
        is rebuilt from the translated pack, so {c2:77} shows "Erva Curativa",
        not the English source) and falls back to the source."""
        self.ref_items = {}
        self.ref_spells = {}
        self.ref_arts = []
        self.ref_party = []
        for sec, e in self.pack.flat:
            ctx = e.get("context", "")
            src = (e.get("translation", "") or "").rstrip() or e.get("source", "")
            m = re.match(r"item 0x([0-9a-fA-F]+)", ctx)
            if sec == "items" and m:
                self.ref_items[int(m.group(1), 16)] = src
            m = re.match(r"spell 0x([0-9a-fA-F]+)", ctx)
            if sec == "spells" and m:
                self.ref_spells[int(m.group(1), 16)] = src
            if sec == "arts":
                self.ref_arts.append(src)
            if sec == "party_names":
                self.ref_party.append(src)

    def box_map(self):
        """flat index -> (box, row) for scene_dialog/inline_text lines, cached
        per loaded pack (keys/budgets don't change while editing)."""
        if self._box_map is None:
            self._box_map = self.pack.dialog_box_map()
        return self._box_map

    def box_rows(self, idx):
        """Flat indices of `idx`'s dialogue box, in box order, or [idx]."""
        row = self.box_map().get(idx)
        if row is None:
            return [idx]
        box_no = row[0]
        return [i for i, (b, _r) in self.box_map().items() if b == box_no]

    def markup_expander(self):
        """Resolve {c1..} substitution tokens to the referenced entry's
        current text (retail uses the runtime string pool). Shared by the
        workbench and the main dock's real-glyph preview."""
        if self._wb_refs is None:
            refs = {}
            for sec, e in self.pack.flat:
                ctx = e.get("context", "")
                txt = e.get("translation", "") or e.get("source", "")
                m = re.match(r"item 0x([0-9a-fA-F]+)", ctx)
                if sec == "items" and m:
                    refs[("c2", int(m.group(1), 16))] = txt
                    refs[("c4", int(m.group(1), 16))] = txt
                m = re.match(r"spell 0x([0-9a-fA-F]+)", ctx)
                if sec == "spells" and m:
                    refs[("c3", int(m.group(1), 16))] = txt
                if sec == "party_names":
                    refs[("c1", len([k for k in refs if k[0] == "c1"]))] = txt
                if sec == "arts":
                    refs[("c5", len([k for k in refs if k[0] == "c5"]))] = txt
            for i, nm in enumerate(C7_NAMES):
                refs[("c7", i)] = nm
            self._wb_refs = refs

        def hook(op, arg):
            if 0xC0 <= op <= 0xC7:
                name = "c%d" % (op - 0xC0)
            else:
                return None
            txt = self._wb_refs.get((name, arg))
            if txt is None:
                txt = game_name(name, arg)
                if txt is None:
                    return None
            bs = []
            for ch in ascii_fold(txt):
                o = ord(ch)
                if o < 0x80:
                    bs.append(o)
            if name == "c1":
                # A {c1:..} name always fills the 8-glyph in-game name field:
                # pad the visible text so the preview shows exactly how much
                # room the retail name splice reserves (the byte budget is
                # unaffected - escapes are 2 bytes no matter what).
                while len(bs) < NAME_FIELD:
                    bs.append(0x5F)      # '_' marks the empty name-field space
            return bs

        return hook
