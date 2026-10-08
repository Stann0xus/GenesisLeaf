"""Pure RGBA rasterisers: dialog rows, the literal text wall and the font grid.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import re

from genesisleaf.core.dialog import limit_for
from genesisleaf.core.encoding import CP437_MAP, parse_text, visible_len
from genesisleaf.core.fonttables import (
    ATLAS_W, FONT_WIDTHS, GLYPH_H, GLYPH_W, PREVIEW_MARGIN, ROW_PITCH,
)
from genesisleaf.core.palette import SCHEME
from genesisleaf.core.textfix import ascii_fold
from genesisleaf.render.atlas import (
    _accent_widths, _atlas, _get_atlas, glyph_origin,
)
from genesisleaf.render.metrics import font_advance, measure_markup, walk_bytes
from genesisleaf.render.window import FILL_INSET, paint_window
from genesisleaf.core import palette as _palette


# A Japanese-retail name starts with a length byte ({04}.. = that many
# characters follow).  The US walker reads any byte below 0x20 as the end of
# the string, so a JP row like '{06}鈍重no首飾ri|Slowness Chain' previewed as
# nothing at all; the preview drops that leading prefix instead.
_LEN_PREFIX_RE = re.compile(r"^(?:\{[01][0-9a-fA-F]\})+")
# room the atlas pen keeps for one character it cannot draw (Japanese/CJK):
# the system-font fallback draws it 13 px wide at 1x (ui.app.preview.jp_font),
# and 3 spaces are 15 px, so neighbouring glyphs never overlap it
FALLBACK_CHAR = "   "


def _preview_markup(row):
    """`row` as the preview lays it out: the leading JP length prefix
    dropped, and every character the atlas cannot draw replaced by blank
    room.  Returns (markup, [(index_in_markup, char), ...]) - the places
    where the fallback font draws those characters."""
    row = _LEN_PREFIX_RE.sub("", row)
    _, spans = parse_text(row)
    out = []
    holes = []
    pos = 0
    n = 0
    for s, e, st in spans:
        if s > pos:
            out.append(row[pos:s])
            n += s - pos
        if st == "nonascii":
            for ch in row[s:e]:
                holes.append((n, ch))
                out.append(FALLBACK_CHAR)
                n += len(FALLBACK_CHAR)
        else:
            out.append(row[s:e])
            n += e - s
        pos = e
    out.append(row[pos:])
    return "".join(out), holes


def _hole_positions(markup, holes, glyph_pad, expander, numeric_digits,
                    accent_font=False):
    """(line, x, char) for each fallback character of a `_preview_markup`
    row, at the pen position the walk reaches there."""
    if (holes and type(glyph_pad) is int
            and all(0x20 <= ord(ch) < 0x7f and ch not in "{^" for ch in markup)
            and all(0 <= at <= len(markup) for at, _ch in holes)):
        # Plain fallback rows contain spaces where CJK glyphs will be drawn.
        # No escape/substitution can affect this pen, so walk it once instead
        # of encoding every progressively longer prefix. Rich markup keeps
        # the full walker below, including its callback/error semantics.
        widths = _accent_widths() if accent_font else FONT_WIDTHS
        wanted = {at for at, _ch in holes}
        positions = {}
        line = x = 0
        for at, ch in enumerate(markup):
            if at in wanted:
                positions[at] = (line, x)
            if ch == "|":
                line += 1
                x = 0
            else:
                x += font_advance(ord(ch), widths) + glyph_pad
        positions[len(markup)] = (line, x)
        return [(positions[at][0], positions[at][1], ch) for at, ch in holes]
    out = []
    for at, ch in holes:
        head = markup[:at]
        line = 0
        _, spans = parse_text(head)
        start = 0
        for s, e, st in spans:
            if st == "newline":
                line += 1
                start = e
        try:
            _b, lw, _m, _u, _it, _bad = measure_markup(
                head[start:], glyph_pad=glyph_pad, expander=expander,
                numeric_digits=numeric_digits, accent_font=accent_font)
            x = lw[-1] if lw else 0
        except Exception:
            x = visible_len(head[start:]) * 6
        out.append((line, x, ch))
    return out


def render_font_rows(rows, key_meta=None, expander=None, row_positions=None,
                     accent_font=False):
    """Port of translate_workbench.rs::render(): lays `rows` (list of strings;
    each string is the packed markup of one in-game row) into a preview surface
    drawn with the REAL retail glyphs.

    Returns (w, h, rgba, widest_px, limit_px, icons) where rgba is a bytes
    buffer of w*h RGBA pixels: dark window with light rim, the limit edge in
    red, rows of glyph ink from the embedded atlas, escape bars in dim blue,
    and `icons` a list of (x, py, width, index) for every {ce:..} escape that
    was placed (so a renderer can overlay the right icon/emoji in proportion).

    If `row_positions` is provided (list of ints, one per row), each row
    starts at its box position (so a box with a missing row keeps its gap),
    but never above the line after the previous row's last '|' line - a
    multi-line row pushes the rows below it down instead of being drawn
    over, so every line stays readable.  Otherwise rows are stacked
    sequentially.

    If `accent_font` is True, accented characters are rendered by combining
    base letters with diacritical marks (accent font preview)."""
    meta = key_meta or {}
    if meta.get("limit") and isinstance(meta["limit"], dict):
        limit = meta["limit"]
    else:
        limit = (limit_for(meta["limit"]) if meta.get("limit") else None)
    glyph_pad = meta.get("glyph_pad", 0)
    numeric_digits = meta.get("numeric_digits", 4)
    if limit:
        glyph_pad = limit["glyph_pad"]

    # Get the atlas (regular or accent font)
    atlas = _get_atlas(accent_font)

    placed = []          # (base_line, line, x, kind, byte_or_px, palette[, icon])
    fallbacks = []       # (line, x, text): runs the atlas cannot draw
    widest = 0
    max_line = 0
    base_line = 0
    next_free = 0
    for idx, row in enumerate(rows):
        row, holes = _preview_markup(row)
        bs, lw, maxpx, _, _, _ = measure_markup(
            row, glyph_pad=glyph_pad, expander=expander,
            numeric_digits=numeric_digits, accent_font=accent_font)
        widest = max(widest, maxpx)
        _, _, _, items = walk_bytes(bs, glyph_pad, expander, numeric_digits,
                                    walk_pal=True, accent_font=accent_font)
        if row_positions is not None and idx < len(row_positions):
            base_line = max(row_positions[idx], next_free)
        for line, x, ch in _hole_positions(
                row, holes, glyph_pad, expander, numeric_digits,
                accent_font=accent_font):
            fallbacks.append((base_line + line, x, ch))
        for item in items:
            line, x, kind, b = item[0], item[1], item[2], item[3]
            pal = item[4] if len(item) > 4 else 8
            earg = item[5] if len(item) > 5 else None
            placed.append((base_line + line, x, kind, b, pal, earg))
            max_line = max(max_line, base_line + line)
        next_free = base_line + max(1, len(lw))
        if row_positions is None:
            base_line += len(lw)

    lines = max(max_line + 1, next_free) if row_positions is not None         else base_line
    limit_px = limit["max_px"] if limit else 0
    margin = PREVIEW_MARGIN
    w = (max(widest, limit_px) + 2 * margin + 4)
    if w > 1024:
        w = 1024
    h = max(lines, 1) * ROW_PITCH + 2 * margin
    rgba = bytearray(w * h * 4)
    sch = SCHEME               # live preview colours (core.palette)

    def put(x, y, c):
        if 0 <= x < w and 0 <= y < h:
            o = (y * w + x) * 4
            rgba[o] = c[0]
            rgba[o + 1] = c[1]
            rgba[o + 2] = c[2]
            rgba[o + 3] = 255

    # the game's dialog window: gradient fill, the red past-the-limit band,
    # the gold 9-slice frame (render.window)
    paint_window(rgba, w, h, sch,
                 limit_x=margin + limit_px if limit_px > 0 else 0)

    if limit_px > 0:
        # inside the fill only: the frame stays whole
        for y in range(FILL_INSET, h - FILL_INSET):
            if y % 4 < 2:
                put(margin + limit_px, y, sch["limit"])

    icons = []
    for line, x, kind, data, pal, earg in placed:
        py = margin + line * ROW_PITCH
        if kind == "e":
            if earg is not None:
                icons.append((x, py, data, earg, pal))
            for gx in range(max(0, data - 1)):
                put(margin + x + gx, py + 2, sch["esc"])
                put(margin + x + gx, py + 12, sch["esc"])
            continue
        if data < 0x20:
            continue
        o = glyph_origin(data)
        if o is None:
            continue
        ink = _palette.ink(pal)
        ox, oy = o
        # Accent-rebuilt cells are drawn from the base letter's own seat in
        # the atlas, exactly as accent_font.rs builds them - so NO baseline
        # nudge here: an accent letter lines up with the plain letters
        # beside it, and toggling the accent font never makes text jump.
        for gy in range(GLYPH_H):
            for gx in range(GLYPH_W):
                v = atlas[(oy + gy) * ATLAS_W + ox + gx]
                if v == 0:
                    continue
                put(margin + x + gx, py + gy,
                    sch["shadow"] if v == 1 else ink)

    return w, h, bytes(rgba), widest, limit_px, icons, fallbacks


# ---------------- Playground ----------------
# A scratch space for trying box/dialogue markup before touching a real pack:
#   * Box   - define the box (lines + red-line budget) and type markup in a
#             side editor; the real-font box renders live;
#   * Cheat - one objective line + a real-font example box per token;
#   * Wall  - the whole font tiled 1:1, and literal text with EVERY effect
#             disabled (a pipe prints as the pipe glyph, {7c} prints braces);
#   * Icons - the {ce:00}..{ce:23} splices drawn as proportional emoji.


def _glyph_bytes_list(text, accent_font=False):
    """Map a LITERAL string to glyph bytes with no effect handling: '|' stays
    the pipe glyph, '{..}' braces would stay literal braces and nothing ever
    jumps rows.  Used by the Text Wall to prove a string can be drawn as-is."""
    out = []
    for ch in text:
        o = ord(ch)
        if o < 0x80:
            out.append(o)
            continue
        if ch in CP437_MAP:
            out.append(CP437_MAP[ch])
            continue
        out.extend(ord(c) for c in ascii_fold(ch) if ord(c) < 0x80)
    return out


def render_wall_text(texts, accent_font=False):
    """Render `texts` (literal strings, effects DISABLED) as rows of real font
    glyphs.  Returns (w, h, rgba, max_px)."""
    widths = _accent_widths() if accent_font else FONT_WIDTHS
    lines = [_glyph_bytes_list(t, accent_font) for t in texts]
    row_px = [sum(font_advance(b, widths) for b in line) for line in lines]
    max_w = max(row_px) if row_px else 0
    margin = PREVIEW_MARGIN
    w = min(4096, max_w + 2 * margin + 4)
    h = max(len(lines), 1) * ROW_PITCH + 2 * margin
    rgba = bytearray(w * h * 4)
    sch = SCHEME               # live preview colours (core.palette)
    atlas = _get_atlas(accent_font)

    def put(x, y, c):
        if 0 <= x < w and 0 <= y < h:
            o = (y * w + x) * 4
            rgba[o], rgba[o + 1], rgba[o + 2], rgba[o + 3] = c[0], c[1], c[2], 255

    for y in range(h):
        for x in range(w):
            rim = x == 0 or y == 0 or x == w - 1 or y == h - 1
            put(x, y, sch["rim"] if rim else sch["bg"])

    for li, line in enumerate(lines):
        px = 0
        for b in line:
            if b >= 0x20:
                o = glyph_origin(b)
                if o:
                    ox, oy = o
                    for gy in range(GLYPH_H):
                        for gx in range(GLYPH_W):
                            v = atlas[(oy + gy) * ATLAS_W + ox + gx]
                            if v == 0:
                                continue
                            put(margin + px + gx,
                                margin + li * ROW_PITCH + gy,
                                sch["shadow"] if v == 1 else sch["white"])
            px += font_advance(b, widths)
    return w, h, bytes(rgba), max_w


def build_font_grid_rgba():
    """Tile every drawable glyph (0x21..0xFF) 1:1 with a 3px gutter.  Returns
    (w, h, rgba, slots) where slots = [(byte, x, y)] cell origins in the image
    so a caller can draw a hex label under each cell (the empty cells are the
    control / two-byte-opcode bytes 0xC0-0xCF, which are never glyphs)."""
    atlas = _atlas()
    glyphs = list(range(0x21, 0x100))
    cols = 16
    rows = (len(glyphs) + cols - 1) // cols
    cell_w, cell_h = GLYPH_W + 3, GLYPH_H + 5
    w = cols * cell_w + 4
    h = rows * cell_h + 6
    rgba = bytearray(w * h * 4)

    def put(x, y, c):
        o = (y * w + x) * 4
        rgba[o], rgba[o + 1], rgba[o + 2], rgba[o + 3] = c[0], c[1], c[2], 255

    sch = SCHEME
    bg = sch["grid_bg"]
    for y in range(h):
        for x in range(w):
            put(x, y, bg)

    slots = []
    for gi, b in enumerate(glyphs):
        r, c = divmod(gi, cols)
        ox0 = 4 + c * cell_w
        oy0 = 6 + r * cell_h
        o = glyph_origin(b)
        if o:
            ox, oy = o
            for gy in range(GLYPH_H):
                for gx in range(GLYPH_W):
                    v = atlas[(oy + gy) * ATLAS_W + ox + gx]
                    if v == 0:
                        continue
                    put(ox0 + gx, oy0 + gy,
                        sch["shadow"] if v == 1 else sch["grid_ink"])
        slots.append((b, ox0, oy0))
    return w, h, bytes(rgba), slots
