"""Long explanatory texts shown by the report windows.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""


ROOM_BRIEF = """HOW THE DISC'S SPACE WORKS  (what `legaia-patcher translate import` does)

A row's `budget` is its IN-PLACE span: the bytes the English string occupies
(plus its 0..3 bytes of alignment padding).  Shorter always fits.  Longer
depends on what kind of string it is:

* Names - items, item types, spells, arts, accessory passives.  The name
  pools are compacted: every movable name is re-laid end to end, the bytes
  shorter translations give up collect into free runs, and a longer name
  MOVES into one, with its table slot repointed.  So room IS shared: a name
  that saves 10 bytes pays for another that needs 10 more.  Limit: the
  pooled free space ("names" above).  Exceptions that never move: the
  arts-menu descriptions and a few shared strings (shown as pinned).

* System text - a longer string moves into the free runs the names leave.

* Menu labels (ui_menu) - a longer label moves and every instruction that
  loads its address is rewritten.  The menu overlay also reserves a region
  for moved labels.  A label reached only as an offset from another stays
  pinned.

* Monster names - the record grows, up to 15 bytes.

* Place names and party names - fixed cells; the budget is the law.

* Dialogue (scene_dialog / inline_text) - a scene is rewritten as a whole and
  must recompress into its compressed footprint.  Retail scenes have zero
  slack, and translated text compresses worse than English, so a scene can
  overflow even when every line is shorter.  Without relayout the importer
  rolls back lines until it fits; with "Give translated dialog more room"
  (--allow-relayout) the scene grows by whole 2048-byte sectors instead.
  Relayout grows the image, so it writes a .bin, not a PPF.

* Accents - with --accents font the accented letters are drawn into the
  dialog font and cost one byte each, like any letter.

The estimate here is computed from the pack alone and tracks the importer
closely for names, system text and labels.  Dialogue has no disc-free figure:
use "Measure on disc", which runs the importer's own dry run
(`translate space`) with your build options and reports every line it would
refuse.
"""
