"""Undo / redo model: cell-level EditOp and the shared EditHistory stacks.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import time


# ---------------------------------------------------------------------------
# Undo / redo
# ---------------------------------------------------------------------------
UNDO_LIMIT = 400
UNDO_COALESCE_SEC = 0.9


class EditOp:
    """One reversible step: the cells it touched, with both of their values.

    Cell-level (flat index, old, new) rather than a snapshot of the pack,
    because every edit the UI offers *is* "some rows' translation changed" -
    typing, pasting a row onto another, clearing, joining clones.  Keeping the
    old value beside the new one is what makes redo free, and it keeps undo
    exact after the table has been re-sorted, re-filtered or re-rendered.
    """

    __slots__ = ("label", "cells", "when", "mergeable")

    def __init__(self, label, cells, mergeable=False):
        self.label = label
        self.cells = cells            # list of [flat_idx, old, new]
        self.when = time.time()
        self.mergeable = mergeable

    def merged(self, other):
        """Fold a follow-up typing step onto this one.

        Only when both are plain typing, they touch the same single row, and
        they are close together in time - that is one burst of typing.  Making
        the user press Ctrl+Z once per character to get back to where they
        started would be worse than having no undo at all, so a burst collapses
        into a single step.  Pasting and clearing are discrete and never merge.
        """
        if not (self.mergeable and other.mergeable):
            return False
        if len(self.cells) != 1 or len(other.cells) != 1:
            return False
        if self.cells[0][0] != other.cells[0][0]:
            return False
        if other.when - self.when > UNDO_COALESCE_SEC:
            return False
        self.cells[0][2] = other.cells[0][2]
        self.when = other.when
        return True

    def describe(self):
        return "%s (%d line%s)" % (self.label, len(self.cells),
                                   "" if len(self.cells) == 1 else "s")


class EditHistory:
    """The undo/redo stacks.  Owned by the App, so every window shares one
    history: undo in a second window steps the same pack the first window is
    showing, which is what makes it usable as a scratch window."""

    def __init__(self, limit=UNDO_LIMIT):
        self.undo_stack = []
        self.redo_stack = []
        self.limit = limit

    def record(self, op):
        # a burst of typing in one row is one step, not one per keystroke
        if self.undo_stack and self.undo_stack[-1].merged(op):
            return
        # a fresh step invalidates the redo branch: that is what it means to
        # edit something after having undone it
        self.undo_stack.append(op)
        del self.undo_stack[:-self.limit]
        self.redo_stack.clear()

    def undo(self):
        """`(op, forward)` - forward False, so apply the *old* values."""
        if not self.undo_stack:
            return None
        op = self.undo_stack.pop()
        self.redo_stack.append(op)
        return op, False

    def redo(self):
        if not self.redo_stack:
            return None
        op = self.redo_stack.pop()
        self.undo_stack.append(op)
        return op, True

    def clear(self):
        self.undo_stack.clear()
        self.redo_stack.clear()
