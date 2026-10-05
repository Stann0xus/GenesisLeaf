"""Per-entry edit bookkeeping (uuid / edited / joined) carried in the pack.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import hashlib
import time


# ---------------------------------------------------------------------------
# Per-entry edit bookkeeping.
#
# Three extra keys ride along on every pack entry and are written back to the
# .yaml next to key/context/source/translation/budget.  The Rust importer
# deserialises `Entry` without `deny_unknown_fields`, so it ignores them - they
# are editor state that happens to live in the same file, not pack schema.
#
#   uuid    8 hex chars, stable for a (section, key) pair.  Derived by md5
#           rather than random so two people opening the same .yaml before
#           either saves it see the same ids - otherwise a shared pack would
#           hand out a fresh identity to every row.
#   edited  "YYYY-MM-DD HH:MM", when this row's translation last changed.
#   joined  uuid of the entry a "join identical sources" pass last copied
#           INTO this row.  Empty = the text here is the user's own, which is
#           what the join uses to decide whether it may overwrite in silence
#           or has to ask first.
# ---------------------------------------------------------------------------
EDITED_FMT = "%Y-%m-%d %H:%M"


def entry_uuid(sec, key):
    """Stable 8-hex id for one entry."""
    h = hashlib.md5(("%s\x00%s" % (sec, key)).encode("utf-8")).hexdigest()
    return h[:8]


def stamp_edited(e):
    e["edited"] = time.strftime(EDITED_FMT)


def is_join_owned(e):
    """True when this row's translation came from a join, not from the user."""
    return bool(e.get("joined"))


def edited_on(e):
    """The row's edit stamp, or "" when the .yaml predates the bookkeeping (or
    the row has never been touched).  An unknown date means "we have no
    evidence the user ever hand-edited this", which is exactly what decides
    whether a join may overwrite the row without asking."""
    return str(e.get("edited", "") or "").strip()


def date_known(e):
    return bool(edited_on(e))
