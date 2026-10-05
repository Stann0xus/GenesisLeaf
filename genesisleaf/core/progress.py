"""Translation progress: per-row status and grouped tallies.

Pure functions over a Pack; used by the Progress window and the main
window's navigator sidebar.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

from genesisleaf.core.dialog import SECTION_KIND
from genesisleaf.core.encoding import bad_cf_codes, parse_text
from genesisleaf.core.space import verdict

# status key -> label, in display order (most urgent last)
STATUSES = (
    ("untranslated", "Untranslated"),
    ("translated", "Translated"),
    ("grows", "Grows into free space"),
    ("over", "Won't fit"),
    ("nonascii", "Non-ASCII"),
    ("badcf", "Bad colour code"),
)
STATUS_LABEL = dict(STATUSES)


def row_status(e, sec=""):
    """One of the STATUSES keys for a pack entry.  `sec` decides the room
    kind of a `scus:str:` key (a name pools with names, a system string with
    system text) - see `core.space.verdict`."""
    tr = e.get("translation", "")
    if not tr:
        return "untranslated"
    b, spans = parse_text(tr)
    if any(st == "nonascii" for _s, _e, st in spans):
        return "nonascii"
    if bad_cf_codes(tr):
        return "badcf"
    v = verdict(sec, e, b)
    if v == "over":
        return "over"
    if v == "grows":
        return "grows"
    return "translated"


class Tally:
    """Counts for one group: total rows, rows with any translation, and the
    per-status split."""

    __slots__ = ("total", "done", "by_status")

    def __init__(self):
        self.total = 0
        self.done = 0
        self.by_status = {}

    def add(self, status):
        self.total += 1
        if status != "untranslated":
            self.done += 1
        self.by_status[status] = self.by_status.get(status, 0) + 1

    @property
    def pct(self):
        return 100.0 * self.done / self.total if self.total else 0.0

    @property
    def problems(self):
        return sum(n for k, n in self.by_status.items()
                   if k in ("over", "nonascii", "badcf"))


def tally(pack, key):
    """Group every row of `pack` by `key` ('section' | 'context' | 'kind' |
    'status').  Returns (overall Tally, {group: Tally}) with groups in a
    sensible order (file order for sections, size for contexts)."""
    overall = Tally()
    groups = {}
    for sec, e in pack.flat:
        st = row_status(e, sec)
        overall.add(st)
        if key == "section":
            g = sec
        elif key == "context":
            g = e.get("context", "") or "(none)"
        elif key == "kind":
            g = SECTION_KIND.get(sec, "other")
        else:
            g = STATUS_LABEL[st]
        t = groups.get(g)
        if t is None:
            t = groups[g] = Tally()
        t.add(st)
    if key == "section":
        order = [s for s in pack.section_names if s in groups]
    elif key == "status":
        order = [lab for _k, lab in STATUSES if lab in groups]
    else:
        order = sorted(groups, key=lambda g: (-groups[g].total, g))
    return overall, {g: groups[g] for g in order}


def text_bar(pct, width=20):
    """'#######.............' style bar for table cells."""
    n = int(round(width * max(0.0, min(100.0, pct)) / 100.0))
    return "█" * n + "░" * (width - n)
