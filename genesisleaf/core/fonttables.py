"""Retail dialog-font geometry and advance tables (pure data).

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""


# ---------------------------------------------------------------------------
# Retail dialog font, embedded as a verified 224x210 glyph atlas.
#
# The TIM at PROT.DAT file offset 0x7F40 (FONT_TIM_PROT_DAT_OFFSET) is 4bpp,
# 64x256 halfwords = 256x256 pixels, CLUT 16 entries (index 0 transparent,
# 14 drop shadow, 15 glyph fill).  glyph_origin maps a character to a 14x15
# cell (col = c & 0x0F, row = (c - 0x20) >> 4) of a 16x14 grid.  The atlas
# below is 2bpp/indexed: 0 = transparent, 1 = shadow, 2 = fill white, so the
# workbench can draw the REAL glyphs the way the web translate-workbench
# render() does.  It was generated from this disc and byte-verified against
# translate_workbench.rs::render outputs.
# ---------------------------------------------------------------------------
FONT_VRAM_X16 = 896          # fb x of the font page on the retail VRAM
ATLAS_W = 224
ATLAS_H = 210
GLYPH_W = 14
GLYPH_H = 15
ROW_PITCH = 15               # web workbench's on-screen row step (px)
ROWS_PER_BOX = 3             # field dialog pager rows per box (_DAT_801F2740)
PREVIEW_MARGIN = 8           # dark-window margin around/between text

FONT_WIDTHS = (
    255, 0, 0, 0, 16, 0, 0, 0, 77, 101, 116, 97, 0, 0, 0, 0,
    84, 101, 114, 114, 97, 0, 0, 0, 79, 122, 109, 97, 0, 0, 0, 0,
    4, 4, 5, 7, 9, 8, 7, 3, 5, 5, 7, 6, 3, 5, 3, 6,
    6, 4, 6, 6, 6, 6, 6, 6, 6, 6, 4, 4, 4, 5, 4, 6,
    0, 7, 6, 6, 6, 6, 6, 6, 6, 3, 6, 6, 6, 8, 6, 6,
    6, 6, 6, 6, 7, 6, 7, 9, 7, 7, 6, 5, 6, 5, 5, 6,
    3, 6, 5, 5, 5, 5, 5, 5, 5, 3, 4, 5, 3, 8, 5, 5,
    5, 5, 4, 5, 4, 5, 5, 7, 5, 5, 5, 5, 3, 5, 9, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 0, 13, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 10, 0, 0, 8,
    0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 4, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6,
    8, 8, 8, 8, 8, 8, 13, 7, 7, 7, 7, 7, 4, 4, 4, 4,
    8, 7, 7, 7, 7, 7, 7, 6, 10, 7, 7, 7, 7, 8, 8, 8,
    7, 7, 7, 7, 7, 7, 10, 6, 6, 6, 6, 6, 4, 4, 4, 4,
    6, 6, 6, 6, 6, 6, 6, 6, 8, 6, 6, 6, 6, 6, 6, 6,
)

FONT_ESCAPES = (
    (55, 16),
    (56, 16),
    (57, 16),
    (58, 16),
    (59, 16),
    (60, 16),
    (61, 16),
    (62, 16),
    (98, 12),
    (132, 12),
    (133, 12),
    (0, 32),
    (0, 32),
    (0, 32),
    (0, 32),
    (137, 38),
    (36, 12),
    (34, 12),
    (35, 12),
    (37, 12),
    (139, 20),
    (140, 20),
    (141, 20),
    (142, 20),
    (143, 20),
    (144, 20),
    (145, 20),
    (146, 20),
    (147, 20),
    (148, 28),
    (149, 28),
    (150, 28),
    (151, 28),
    (152, 28),
    (153, 28),
    (154, 28),
    (155, 28),
    (156, 28),
)

INTER_GLYPH_PAD = 1
FIRST_CHAR = 32
NEWLINE = 124
DIALOG_GLYPH_PAD = 1
NUMERIC_DIGIT_PX = 8
