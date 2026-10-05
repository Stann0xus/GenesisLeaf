"""Per-row screen surface limits and overdraw measurement.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

from genesisleaf.core.dialog import default_limit_context, limit_for
from genesisleaf.render.metrics import overdraw_px


class LimitsMixin:
    """Per-row screen surface limits and overdraw measurement.

    Mixed into `App`; `self` is the main window.
    """

    def _dock_limit_context(self, sec):
        return self._limit_context_at(self.current, sec)

    def _limit_context_at(self, idx, sec=None):
        """The TEXT_LIMITS context for flat row `idx`, or None.

        Lives on the App and takes the row rather than reading `self.current`,
        so a second window measures its own selected row correctly and the
        table's Overdraw column agrees with the preview.

        The one dialogue refinement the pack can justify: a box past its first
        page has the page-advance hand drawn beside it, which eats 16px of the
        same 244px box, so those rows are measured against the narrower limit.
        Picker/option labels get a different surface again, but nothing in the
        pack identifies them - they are ordinary 0x1F segments whose only
        distinguishing feature is the jump table that precedes them in the
        disc script, and the pack does not carry that - so they are left on
        the dialogue-row limit rather than guessed at.
        """
        if sec is None:
            sec = self.pack.flat[idx][0]
        if sec in ("scene_dialog", "inline_text"):
            # `box_rows()` scans the complete box map to collect every row in
            # the dialogue.  This method is called for every source and
            # translation cell while the table is built, so using it here
            # makes a large pack quadratic.  The cached map already stores
            # the row number; the first row is row zero by definition.
            box_row = self.box_map().get(idx)
            first = 0 if box_row is None else box_row[1]
            return "field_dialog_row_beside_page_hand" if first >= 1 \
                else "field_dialog_row"
        return default_limit_context(sec)

    def row_limit(self, idx):
        """`(max_px, max_lines, glyph_pad, context)` for a flat row, or None.

        Cached per pack: the surface a row is drawn on depends only on its
        section and its box number, neither of which editing can change.
        """
        cache = self.pack.row_limits
        if idx in cache:
            return cache[idx]
        ctx = self._limit_context_at(idx)
        lim = limit_for(ctx) if ctx else None
        if lim is not None:
            lim = (lim["max_px"], lim["max_lines"], lim["glyph_pad"],
                   lim["context"])
        cache[idx] = lim
        return lim

    def row_overdraw(self, idx, text):
        """`(px, over, checked)` for one line of row `idx` - see overdraw_px."""
        lim = self.row_limit(idx)
        if lim is None:
            return 0, False, False
        return overdraw_px(text, {"max_px": lim[0], "glyph_pad": lim[2]},
                           self.markup_expander(),
                           accent_font=self.accent_font_var.get())
