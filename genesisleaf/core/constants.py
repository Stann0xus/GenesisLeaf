"""Small shared constants: search scopes, compare-row field indices, join delay.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""


# What a search is allowed to look inside.  "All" is the historical haystack
# (key + context + source + translation); the rest exist to stop context asset
# names from swamping a real dialogue-word search.
SEARCH_SCOPES = ("All", "Source", "Translation", "Source+Translation", "Context")

# Compare-row layout: App._cmp_pair_row builds them, everything else reads.
CMP_ST, CMP_LEVEL, CMP_EV, CMP_KEYM, CMP_KEYO, CMP_SEC, CMP_SRC, CMP_CTX, \
    CMP_MTR, CMP_OTR, CMP_MB, CMP_MBUD, CMP_OB, CMP_OBUD, CMP_MI, CMP_OI, \
    CMP_OSRC = range(17)

# How long the editor waits after the last keystroke before it pushes a
# translation into the joined duplicates.  A join can rewrite hundreds of rows
# and raise a conflict prompt, and doing that once per character makes the
# whole window crawl; this batches a word (or a paste) into a single pass.
JOIN_DELAY_MS = 1500
