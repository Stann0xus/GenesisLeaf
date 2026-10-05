"""The embedded retail glyph atlas and the accent-font cell builder.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import base64 as _b64
import zlib as _zlib

from genesisleaf.assets.font_atlas_blob import FONT_ATLAS_B85
from genesisleaf.core.fonttables import (
    ATLAS_H, ATLAS_W, FONT_WIDTHS, GLYPH_H, GLYPH_W,
)


def atlas_pixels():
    """Decode the embedded 2bpp atlas to a quick bytearray of 0/1/2."""
    raw = _zlib.decompress(_b64.b85decode(FONT_ATLAS_B85))
    out = bytearray(ATLAS_W * ATLAS_H)
    i = 0
    for b in raw:
        out[i] = b & 3
        out[i + 1] = (b >> 2) & 3
        out[i + 2] = (b >> 4) & 3
        out[i + 3] = (b >> 6) & 3
        i += 4
    return out

_FONT_ATLAS = None
_FONT_ATLAS_ACCENT = None
_ACCENT_WIDTHS = None

def _atlas():
    global _FONT_ATLAS
    if _FONT_ATLAS is None:
        _FONT_ATLAS = atlas_pixels()
    return _FONT_ATLAS

def _get_atlas(accent_font=False):
    """The font atlas, optionally rebuilt with the accent font."""
    global _FONT_ATLAS_ACCENT
    if not accent_font:
        return _atlas()
    if _FONT_ATLAS_ACCENT is None:
        _FONT_ATLAS_ACCENT = _build_accent_atlas()
    return _FONT_ATLAS_ACCENT

def _accent_widths():
    """The advance table the accent font would patch in (accent_font.rs):
    a copy of FONT_WIDTHS with every rebuilt recipe cell's advance set (for
    an accent cell, the base letter's own advance; ligatures/drawn, the widest
    ink column + 1)."""
    if _ACCENT_WIDTHS is None:
        _get_atlas(True)
    return _ACCENT_WIDTHS

def _fill_cell_bbox(c):
    """(min_x, max_x, top, bottom) of the fill pixels in a 14x15 cell."""
    hits = [(gx, gy) for gy in range(GLYPH_H) for gx in range(GLYPH_W)
            if c[gy][gx] == 2]
    if not hits:
        return None
    xs = [h[0] for h in hits]
    ys = [h[1] for h in hits]
    return (min(xs), max(xs), min(ys), max(ys))


def _cell_from(atlas, byte):
    """The 14x15 cell of `byte` as rows (0=transparent, 1=shadow, 2=fill)."""
    origin = glyph_origin(byte)
    if origin is None:
        return None
    ox, oy = origin
    return [[atlas[(oy + gy) * ATLAS_W + ox + gx] for gx in range(GLYPH_W)]
            for gy in range(GLYPH_H)]


def _blit_cell(atlas, byte, c):
    origin = glyph_origin(byte)
    if origin is None:
        return
    ox, oy = origin
    for gy in range(GLYPH_H):
        for gx in range(GLYPH_W):
            atlas[(oy + gy) * ATLAS_W + ox + gx] = c[gy][gx]


def _paint(c, pts):
    """Paint `pts` as fill, then drop each a 1px right/down shadow (the page's
    rule) - the shadow only fills cells still transparent (accent_font.rs)."""
    for x, y in pts:
        if 0 <= x < GLYPH_W and 0 <= y < GLYPH_H:
            c[y][x] = 2
    for x, y in pts:
        for dx, dy in ((1, 0), (0, 1), (1, 1)):
            sx, sy = x + dx, y + dy
            if 0 <= sx < GLYPH_W and 0 <= sy < GLYPH_H and c[sy][sx] == 0:
                c[sy][sx] = 1


def _mask_points(rows, x0, y0):
    pts = []
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch == '#':
                pts.append((x0 + dx, y0 + dy))
    return pts


def _shift_down(c, dy):
    return [[0] * GLYPH_W for _ in range(dy)] + c[:GLYPH_H - dy]


def _dotless(c):
    """Drop the dot of an i/j: clear everything above the first fill-free row
    that follows the top fill row (accent_font.rs dotless)."""
    rows = [any(v == 2 for v in row) for row in c]
    tops = [y for y, has in enumerate(rows) if has]
    if not tops:
        return c
    gap = next((y for y in range(min(tops), max(tops) + 1) if not rows[y]),
               None)
    if gap is None:
        return c
    for y in range(gap):
        c[y] = [0] * GLYPH_W
    return c


# Diacritic fill masks (accent_font.rs mark_mask).  1=acute 2=grave 3=circumflex
# 4=tilde 5=diaeresis 6=cedilla 7=ring.
ACCENT_MARKS = {
    1: ['.##', '#..'],
    2: ['##.', '..#'],
    3: ['.#.', '#.#'],
    4: ['.#.#', '#.#.'],
    5: ['#.#'],
    6: ['.#', '##'],
    7: ['###', '#.#', '###'],
}
SHARP_S_MASK = (
    '.##..', '#..#.', '#..#.', '#.#..', '#..#.', '#...#',
    '#...#', '#.##.', '#....',
)
DEGREE_MASK = ('.#.', '#.#', '.#.')

# Drawn-area geometry shared with accent_font.rs.
DESCENDER_ROW = 12          # lowest fill row of a descender
CAP_TOP_ROW = 2             # top fill row of the retail capitals

# byte -> recipe, the recipe cells of the LATIN_CELLS layout:
#   ('accent', base, mark)  base ASCII letter + diacritic (dotless i/j)
#   ('lig', a, b)           2-letter ligature, one column of overlap
#   ('invert', base)        base turned half a turn, dropped to the descender
#   ('drawn', rows)         glyph drawn from a fill mask (sharp s, degree)
ACCENT_RECIPES = {
    0x80: ('accent', 0x43, 6),   # Ç
    0x81: ('accent', 0x75, 5),   # ü
    0x82: ('accent', 0x65, 1),   # é
    0x83: ('accent', 0x61, 3),   # â
    0x84: ('accent', 0x61, 5),   # ä
    0x85: ('accent', 0x61, 2),   # à
    0x86: ('accent', 0x61, 7),   # å
    0x87: ('accent', 0x63, 6),   # ç
    0x88: ('accent', 0x65, 3),   # ê
    0x89: ('accent', 0x65, 5),   # ë
    0x8A: ('accent', 0x65, 2),   # è
    0x8B: ('accent', 0x69, 5),   # ï
    0x8C: ('accent', 0x69, 3),   # î
    0x8D: ('accent', 0x69, 2),   # ì
    0x8E: ('accent', 0x41, 5),   # Ä
    0x8F: ('accent', 0x41, 7),   # Å
    0x90: ('accent', 0x45, 1),   # É
    0x91: ('lig', 0x61, 0x65),   # æ
    0x92: ('lig', 0x41, 0x45),   # Æ
    0x93: ('accent', 0x6F, 3),   # ô
    0x94: ('accent', 0x6F, 5),   # ö
    0x95: ('accent', 0x6F, 2),   # ò
    0x96: ('accent', 0x75, 3),   # û
    0x97: ('accent', 0x75, 2),   # ù
    0x98: ('accent', 0x79, 5),   # ÿ
    0x99: ('accent', 0x4F, 5),   # Ö
    0x9A: ('accent', 0x55, 5),   # Ü
    0x9B: ('accent', 0x61, 4),   # ã
    0x9C: ('lig', 0x6F, 0x65),   # œ
    0x9E: ('lig', 0x4F, 0x45),   # Œ
    0x9F: ('accent', 0x59, 5),   # Ÿ
    0xA0: ('accent', 0x61, 1),   # á
    0xA1: ('accent', 0x69, 1),   # í
    0xA2: ('accent', 0x6F, 1),   # ó
    0xA3: ('accent', 0x75, 1),   # ú
    0xA4: ('accent', 0x6E, 4),   # ñ
    0xA5: ('accent', 0x4E, 4),   # Ñ
    0xA8: ('invert', 0x3F),      # ¿
    0xAD: ('invert', 0x21),      # ¡
    0xB5: ('accent', 0x41, 1),   # Á
    0xB6: ('accent', 0x41, 3),   # Â
    0xB7: ('accent', 0x41, 2),   # À
    0xD0: ('accent', 0x41, 4),   # Ã
    0xD2: ('accent', 0x45, 3),   # Ê
    0xD3: ('accent', 0x45, 5),   # Ë
    0xD4: ('accent', 0x45, 2),   # È
    0xD6: ('accent', 0x49, 1),   # Í
    0xD7: ('accent', 0x49, 3),   # Î
    0xD8: ('accent', 0x49, 5),   # Ï
    0xDE: ('accent', 0x49, 2),   # Ì
    0xE0: ('accent', 0x4F, 1),   # Ó
    0xE1: ('drawn', SHARP_S_MASK),   # ß
    0xE2: ('accent', 0x4F, 3),   # Ô
    0xE3: ('accent', 0x4F, 2),   # Ò
    0xE4: ('accent', 0x6F, 4),   # õ
    0xE5: ('accent', 0x4F, 4),   # Õ
    0xE9: ('accent', 0x55, 1),   # Ú
    0xEA: ('accent', 0x55, 3),   # Û
    0xEB: ('accent', 0x55, 2),   # Ù
    0xED: ('accent', 0x59, 1),   # Ý
    0xF8: ('drawn', DEGREE_MASK),    # °
}


def _build_accent_cell(base_atlas, accent_atlas, byte, recipe):
    """Rebuild one recipe cell into `accent_atlas`; return its new advance,
    or None to leave the cell as the base page has it.  Port of
    accent_font.rs build(): the base letter comes from the page, the mark from
    the fill masks above, fill=2 + shadow=1."""
    kind = recipe[0]
    if kind == "accent":
        _, base, mark = recipe
        c = _cell_from(base_atlas, base)
        if c is None:
            return None
        if base in (ord('i'), ord('j')) and mark != 6:
            c = _dotless(c)
        bb = _fill_cell_bbox(c)
        if bb is None:
            return None
        min_x, max_x, top, bottom = bb
        mask = ACCENT_MARKS[mark]
        mw = max(len(r) for r in mask)
        mh = len(mask)
        bw = max_x - min_x + 1
        x0 = min_x + (bw - mw + 1) // 2
        x0 = max(0, min(x0, GLYPH_W - mw))
        if mark == 6:  # cedilla hangs below the base letter
            _paint(c, _mask_points(mask, x0, bottom + 1))
        else:
            y0 = top - mh - 1
            if y0 < 0:
                c = _shift_down(c, -y0)
            _paint(c, _mask_points(mask, x0, max(y0, 0)))
        _blit_cell(accent_atlas, byte, c)
        return FONT_WIDTHS[base]
    if kind == "lig":
        _, a, b = recipe
        ca = _cell_from(base_atlas, a)
        cb = _cell_from(base_atlas, b)
        if ca is None or cb is None:
            return None
        bba = _fill_cell_bbox(ca)
        bbb = _fill_cell_bbox(cb)
        if bba is None or bbb is None:
            return None
        _, max_a, _, _ = bba
        min_b, _, _, _ = bbb
        shift = max_a - min_b
        if shift < 0:
            return None
        c = [row[:] for row in ca]
        for gy in range(GLYPH_H):
            for gx in range(GLYPH_W):
                p = cb[gy][gx]
                if p == 0:
                    continue
                tx = gx + shift
                if tx >= GLYPH_W:
                    continue
                if p == 2 or c[gy][tx] == 0:
                    c[gy][tx] = p
        bb = _fill_cell_bbox(c)
        if bb is None:
            return None
        _, max_x, _, _ = bb
        if max_x + 1 >= GLYPH_W:
            return None
        _blit_cell(accent_atlas, byte, c)
        return max_x + 1
    if kind == "invert":
        _, base = recipe
        src = _cell_from(base_atlas, base)
        if src is None:
            return None
        bb = _fill_cell_bbox(src)
        if bb is None:
            return None
        min_x, max_x, top, bottom = bb
        h = bottom - top + 1
        dst_top = (DESCENDER_ROW + 1) - h
        if dst_top < 0:
            return None
        pts = []
        for gy in range(top, bottom + 1):
            for gx in range(min_x, max_x + 1):
                if src[gy][gx] == 2:
                    pts.append((min_x + (max_x - gx),
                                dst_top + (bottom - gy)))
        c = [[0] * GLYPH_W for _ in range(GLYPH_H)]
        _paint(c, pts)
        _blit_cell(accent_atlas, byte, c)
        return FONT_WIDTHS[base]
    if kind == "drawn":
        _, rows = recipe
        c = [[0] * GLYPH_W for _ in range(GLYPH_H)]
        _paint(c, _mask_points(rows, 0, CAP_TOP_ROW))
        bb = _fill_cell_bbox(c)
        if bb is None:
            return None
        _, max_x, _, _ = bb
        _blit_cell(accent_atlas, byte, c)
        return max_x + 1
    return None


def _build_accent_atlas():
    """Rebuild every recipe cell of the Latin layout into a copy of the base
    atlas, exactly as accent_font.rs does, and fill the matching advance table
    entries.  Returns the accent atlas as bytes."""
    global _ACCENT_WIDTHS
    base_atlas = _atlas()
    accent_atlas = bytearray(base_atlas)
    widths = list(FONT_WIDTHS)
    for byte, recipe in ACCENT_RECIPES.items():
        adv = _build_accent_cell(base_atlas, accent_atlas, byte, recipe)
        if adv is not None:
            widths[byte] = adv
    _ACCENT_WIDTHS = widths
    return bytes(accent_atlas)

def glyph_origin(c):
    """(ox, oy) into the atlas for character code `c`, else None."""
    if c < 0x20:
        return None
    col = c & 0x0F
    row = (c - 0x20) >> 4
    if row * GLYPH_H + GLYPH_H > ATLAS_H:
        return None
    return col * GLYPH_W, row * GLYPH_H
