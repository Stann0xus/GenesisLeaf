"""How much room a translation really has, the way `legaia-patcher translate
import` decides it.

A row's `budget` is only its *in-place* span. Whether a longer translation
still lands depends on what kind of string it is:

  name    item / item-type / spell / art / accessory-passive strings
          (`scus:str:` in the name sections).  The name pools are compacted
          and a longer name moves into the bytes shorter names give up, so
          the limit is the pooled free space, not the row.
  system  `system_text` strings.  A longer one moves into the free runs the
          name pools leave once the names are placed.
  label   `ui_menu` overlay labels.  A longer one moves, with every code
          reference rewritten, into its image's compaction room and (menu
          overlay PROT 0899) the reserved translation region.
  monster `mon:` names.  The record grows, up to 15 bytes.
  place   `scus:cell:` quick-travel cells - fixed, the budget is the law.
  party   `scus:party:` roster names - fixed 10-byte field.
  dialog  `man:` / `raw:` lines.  The scene is rewritten as a whole and must
          recompress into its footprint; with relayout the scene grows by
          whole sectors instead.

A few strings never move (the arts-menu descriptions, strings sharing their
tail, labels reached as an offset from another): `US_PINNED` lists them for
the USA disc - disc coordinates measured with `translate space`, no game
text.

Two sources of truth, best first:
  * a **measured** dry run - `legaia-patcher translate space --json` on the
    user's own disc (`load_measured`): the importer's own verdict per key;
  * a **disc-free estimate** (`estimate`) from the pack alone, calibrated
    against the measured run on the retail USA disc.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import json
import time

from genesisleaf.core.encoding import parse_text

NAME_SECTIONS = ("items", "item_types", "spells", "arts", "accessory_passives")

# Longest monster name the battle loader's name buffer takes (retail longest).
MONSTER_CAP = 15

# Menu overlay (PROT 0899) zero fill reserved for relocated labels:
# 0x801ED340..0x801EE120 (legaia_patcher::space_ledger, owner "translation").
LABEL_SPARE = {"899": 0xDE0}

# Strings that never move on the USA disc (arts-menu descriptions, shared
# tails, labels with no movable reference).  Over budget = will not fit.
US_PINNED = frozenset("""
scus:str:0x800135e0 scus:str:0x8001362c scus:str:0x80013670 scus:str:0x800136a8
scus:str:0x800136e8 scus:str:0x80013734 scus:str:0x80013780 scus:str:0x800137cc
scus:str:0x80013818 scus:str:0x80013860 scus:str:0x800138b0 scus:str:0x80013904
scus:str:0x8001394c scus:str:0x80013998 scus:str:0x800139f0 scus:str:0x80013a50
scus:str:0x80013a9c scus:str:0x80013adc scus:str:0x80013b30 scus:str:0x80013b78
scus:str:0x80013bc4 scus:str:0x80013c08 scus:str:0x80013c44 scus:str:0x80013c8c
scus:str:0x80013cd8 scus:str:0x80013d2c scus:str:0x80013d78 scus:str:0x80013dcc
scus:str:0x80013e20 scus:str:0x80013e6c scus:str:0x80013eb8 scus:str:0x80013efc
scus:str:0x80013f20 scus:str:0x80013f2c scus:str:0x80013f68 scus:str:0x80013fb0
scus:str:0x80013ff0 scus:str:0x80013ffc scus:str:0x80014040 scus:str:0x8001408c
scus:str:0x800140dc scus:str:0x80014120 scus:str:0x80014158 scus:str:0x80014198
scus:str:0x800141a4 scus:str:0x800141ec scus:str:0x80014240
ui:898:0x801ce818 ui:898:0x801cf714 ui:898:0x801f4b98 ui:898:0x801f4ba0
ui:898:0x801f4ba8 ui:898:0x801f4bb2 ui:898:0x801f4bbc ui:899:0x801ce8e6
ui:899:0x801ce8f0 ui:899:0x801cec0b ui:899:0x801cec18 ui:954:0x801f8f30
ui:954:0x801f8f58 ui:954:0x801f8f80 ui:954:0x801f8fa8 ui:967:0x801f7684
ui:967:0x801f76b8 ui:967:0x801f7718 ui:967:0x801f774c ui:967:0x801f7820
ui:967:0x801f784c ui:967:0x801f78c0 ui:967:0x801f7a5c ui:967:0x801f7a8c
ui:967:0x801f7ad4 ui:967:0x801f7b44 ui:967:0x801f7bc4 ui:967:0x801f7c28
ui:967:0x801f7c64 ui:967:0x801f7c80
""".split())

# Importer outcomes (`translate space` entry rows).  Anything not listed as
# landing is a refusal.
LANDS = frozenset(("in_place", "moved", "grown", "relocated", "relayout",
                   "already_applied"))

KIND_LABEL = {
    "name": "names (pooled)",
    "system": "system text (pooled)",
    "label": "menu labels (pooled)",
    "monster": "monster names (grow to 15)",
    "place": "place names (fixed)",
    "party": "party names (fixed)",
    "dialog": "dialogue (scene footprint)",
    "pinned": "pinned (fixed)",
}


def room_kind(sec, key):
    """The room class of one pack row (see the module docstring)."""
    if key in US_PINNED:
        return "pinned"
    if key.startswith("mon:"):
        return "monster"
    if key.startswith("scus:cell:"):
        return "place"
    if key.startswith("scus:party:"):
        return "party"
    if key.startswith("ui:"):
        return "label"
    if key.startswith(("man:", "raw:")):
        return "dialog"
    if key.startswith("scus:str:"):
        return "system" if sec == "system_text" else "name"
    return "pinned"


def is_growable(kind):
    return kind in ("name", "system", "label", "monster", "dialog")


def hard_cap(kind, budget):
    """Absolute byte ceiling of one row, or None when only a pool bounds it."""
    if kind == "monster":
        return max(MONSTER_CAP, budget)
    if kind in ("place", "party", "pinned"):
        return budget
    return None


def _align4(n):
    return (n + 3) & ~3


# -- measured run --------------------------------------------------------------
# Set by the UI after a `translate space --json` run: the report plus the
# translation of every key at the moment it was measured, so a row edited
# since falls back to the estimate instead of trusting a stale verdict.
MEASURED = {"report": None, "entries": {}, "snapshot": {}, "when": None,
            "options": ""}


def load_measured(report, pack, options=""):
    """Install a parsed `legaia-space-v1` report measured for `pack`."""
    MEASURED["report"] = report
    MEASURED["entries"] = {e["key"]: e for e in report.get("entries", ())}
    MEASURED["snapshot"] = {e.get("key", ""): e.get("translation", "")
                            for _s, e in pack.flat}
    MEASURED["when"] = time.strftime("%H:%M")
    MEASURED["options"] = options


def clear_measured():
    MEASURED.update(report=None, entries={}, snapshot={}, when=None,
                    options="")


def parse_report(text):
    """Parse `translate space --json` output; raises ValueError."""
    rep = json.loads(text)
    if rep.get("schema") != "legaia-space-v1":
        raise ValueError("unexpected report schema %r" % rep.get("schema"))
    return rep


def measured_row(e):
    """The importer's own row for `e`, if a measured run covers its current
    translation; else None."""
    key = e.get("key", "")
    row = MEASURED["entries"].get(key)
    if row is None:
        return None
    if MEASURED["snapshot"].get(key) != e.get("translation", ""):
        return None
    return row


# -- the per-row verdict ---------------------------------------------------------
def verdict(sec, e, b=None):
    """`'fits'`, `'grows'` or `'over'` for row `e` at `b` encoded bytes.

    fits  - inside the row's in-place budget;
    grows - longer than that, but its kind can grow (the importer moves or
            regrows it) and nothing says it will not land;
    over  - past a hard cap, a pinned or fixed string, or refused by the
            measured run.
    """
    tr = e.get("translation", "")
    if b is None:
        b = parse_text(tr)[0]
    budget = int(e.get("budget", parse_text(e.get("source", ""))[0]))
    row = measured_row(e) if tr else None
    if row is not None and row.get("outcome") not in (None, "untranslated"):
        if row["outcome"] not in LANDS:
            return "over"
        return "fits" if b <= budget else "grows"
    if b <= budget:
        return "fits"
    kind = room_kind(sec, e.get("key", ""))
    cap = hard_cap(kind, budget)
    if cap is not None and b > cap:
        return "over"
    return "grows" if is_growable(kind) else "over"


def row_room(sec, e):
    """Bytes this row may reach without a pool: its hard cap, or the in-place
    budget for a pooled row."""
    budget = int(e.get("budget", parse_text(e.get("source", ""))[0]))
    cap = hard_cap(room_kind(sec, e.get("key", "")), budget)
    return budget if cap is None else cap


# -- disc-free estimate ----------------------------------------------------------
def estimate(pack):
    """Pooled free space from the pack alone.

    Names: each movable name occupies `budget + 1` bytes of pool (its span,
    terminator and alignment padding) and needs `align4(len + 1)` once the
    pools are compacted; the difference summed over the pools is what a
    longer name can still take.  System text draws on what the names leave,
    labels on their own image's compaction plus the menu overlay's reserved
    region.  Calibrated against `translate space` on the retail USA disc
    (names within a few bytes).  Dialogue has no disc-free figure: its room
    is each scene's compressed footprint.
    """
    names_free = 0
    names_need = names_n = 0
    system_need = system_n = 0
    labels = {}
    monsters_over = []
    fixed_over = []
    dialog_long = 0
    for sec, e in pack.flat:
        key = e.get("key", "")
        kind = room_kind(sec, key)
        tr = e.get("translation", "")
        src_b = parse_text(e.get("source", ""))[0]
        use = parse_text(tr)[0] if tr else src_b
        budget = int(e.get("budget", src_b))
        if kind == "name":
            names_free += budget + 1 - _align4(use + 1)
            if use > budget:
                names_n += 1
                names_need += _align4(use + 1)
        elif kind == "system":
            if use > budget:
                system_n += 1
                system_need += _align4(use + 1)
        elif kind == "label":
            img = key.split(":")[1]
            d = labels.setdefault(img, {"compaction": 0, "need": 0, "moved": 0})
            d["compaction"] += budget + 1 - _align4(use + 1)
            if use > budget:
                d["need"] += _align4(use + 1)
                d["moved"] += 1
        elif kind == "monster":
            if use > MONSTER_CAP:
                monsters_over.append(key)
        elif kind in ("place", "party", "pinned"):
            if use > budget:
                fixed_over.append(key)
        elif kind == "dialog" and tr and use > budget:
            dialog_long += 1
    system_free = names_free - system_need
    label_free = {}
    for img, d in labels.items():
        spare = LABEL_SPARE.get(img, 0)
        # Growing labels go to the spare region first; the pools are
        # compacted only when that is not enough.
        free = spare - d["need"] if d["need"] <= spare \
            else spare + max(0, d["compaction"]) - d["need"]
        label_free[img] = {"free": free, "moved": d["moved"],
                           "spare": spare, "compaction": d["compaction"]}
    return {
        "names_free": names_free,
        "names_moved": names_n,
        "system_free": system_free,
        "system_moved": system_n,
        "labels": label_free,
        "labels_free": sum(v["free"] for v in label_free.values()),
        "monsters_over": monsters_over,
        "fixed_over": fixed_over,
        "dialog_long": dialog_long,
    }


def measured_summary():
    """The measured run's pooled free bytes per category, or None."""
    rep = MEASURED["report"]
    if not rep:
        return None
    cats = {c["category"]: c for c in rep.get("categories", ())}

    def free(name):
        c = cats.get(name)
        return None if c is None else c.get("free_pack", c.get("free_english"))

    scenes = rep.get("scenes", ())
    return {
        "names_free": free("items"),
        "system_free": free("system_text"),
        "labels_free": free("ui_menu"),
        "monsters_free": free("monster_names"),
        "outcomes": rep.get("summary", {}).get("outcomes", {}),
        "rolled_back": sum(len(s.get("rolled_back") or ()) for s in scenes),
        "relayout_sectors": sum(s.get("relayout_sectors") or 0 for s in scenes),
        "would_add": sum(s.get("relayout_would_add") or 0 for s in scenes),
        "when": MEASURED["when"],
        "options": MEASURED["options"],
    }
