"""Retail text measurement: substitution expansion (FUN_80036514), the pen
walk (FUN_80036888), markup measurement and overdraw tests.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import functools
import re

from genesisleaf.core.encoding import (
    CP437_MAP, SUB_OPCODES, TOKEN_RE, parse_text, visible_len,
)
from genesisleaf.core.fonttables import (
    FIRST_CHAR, FONT_ESCAPES, FONT_WIDTHS, INTER_GLYPH_PAD, NEWLINE,
    NUMERIC_DIGIT_PX,
)
from genesisleaf.core.palette import DEFAULT_PALETTE
from genesisleaf.core.textfix import ascii_fold
from genesisleaf.render.atlas import _accent_widths


def retail_escape_advance(index):
    """The advance column as the disassembly tabulates it; None past 0x25."""
    if 0 <= index <= 7:
        return ("fixed", 16)
    if 8 <= index <= 10:
        return ("fixed", 12)
    if 11 <= index <= 14:
        return ("numeric", 0)
    if index == 15:
        return ("fixed", 38)
    if 16 <= index <= 19:
        return ("fixed", 12)
    if 20 <= index <= 28:
        return ("fixed", 20)
    if 29 <= index <= 37:
        return ("fixed", 28)
    return None

def font_advance(c, widths=None):
    """Pen advance of one glyph byte, the way FUN_80036888 measures it.
    `widths` defaults to FONT_WIDTHS; pass the table from `_accent_widths()`
    for accent-font glyphs."""
    if c < FIRST_CHAR:
        return 0
    return (FONT_WIDTHS if widths is None else widths)[c] + INTER_GLYPH_PAD

def escape_px(index, numeric_digits):
    """What a 0xCE escape advances the pen (fixed string advance or 8px/digit)."""
    if 0 <= index < len(FONT_ESCAPES):
        sid, adv = FONT_ESCAPES[index]
        if sid == 0:
            return ("numeric", NUMERIC_DIGIT_PX * numeric_digits)
        return ("fixed", adv)
    fallback = retail_escape_advance(index)
    if fallback:
        return fallback
    return ("fixed", 0)

def is_two_byte(b):
    return (b & 0xF0) == 0xC0


def expand_bytes(text, expander=None, unresolved=None):
    """Stage 1: the FUN_80036514 substitution expansion.  Rewrites the author
    aliases (0x5E X -> 0xCE (X - 0x2D), 0xFF -> 0xCF), splices the text behind
    each 0xC1..=0xC7 token via `expander(op, arg)` (returning a byte list or
    None = unknown), and expands a nested 0xC1 inside an expansion once more.
    0xC0/0xC6 have no retail arm and are always unresolved."""
    out = []
    i = 0
    text = list(text)
    while i < len(text):
        b = text[i]
        if b == 0:
            break
        if b == 0x5E:
            b = 0xCE
        elif b == 0xFF:
            b = 0xCF
        if not is_two_byte(b):
            out.append(b)
            i += 1
            continue
        if i + 1 >= len(text):
            break
        raw_arg = text[i + 1]
        arg = (raw_arg - 0x2D) & 0xFF if text[i] == 0x5E else raw_arg
        i += 2
        if 0xC1 <= b <= 0xC5 or b == 0xC7:
            sub = expander(b, arg) if expander else None
            if sub is None:
                if unresolved is not None:
                    unresolved.append((b, arg))
                continue
            j = 0
            while j < len(sub) and sub[j] != 0:
                if sub[j] == 0xC1 and j + 1 < len(sub):
                    inner = sub[j + 1]
                    if expander:
                        name = expander(0xC1, inner)
                        if name is None:
                            if unresolved is not None:
                                unresolved.append((0xC1, inner))
                        else:
                            out.extend(c for c in name if c != 0)
                    j += 2
                else:
                    out.append(sub[j])
                    j += 1
        elif b in (0xC0, 0xC6):
            if unresolved is not None:
                unresolved.append((b, arg))
        else:
            out.append(b)
            out.append(arg)
    return out


def walk_bytes(text, glyph_pad=0, expander=None, numeric_digits=4,
               walk_pal=False, accent_font=False):
    """Port of Font::measure: expand (FUN_80036514) then walk (FUN_80036888).
    `text` is the encoded byte list.  Returns
    (line_widths, max_px, unresolved, pen_items) where pen_items is a list of
    (line, x, kind, byte_or_width) - or (line, x, kind, byte_or_width, pal)
    when walk_pal is True, tracking the {cf:n} colour (default palette
    DEFAULT_PALETTE, the ink retail stages before a normal dialog string)
    per item: kind 'g' for a glyph (byte), 'e' for a 0xCE escape (its width in
    px).  With `accent_font` the accent width table drives the pen."""
    unresolved = []
    expanded = expand_bytes(text, expander, unresolved)
    widths = _accent_widths() if accent_font else FONT_WIDTHS
    line_widths = []
    pen = 0
    items = []
    pal = DEFAULT_PALETTE
    i = 0
    while i < len(expanded):
        c = expanded[i]
        if c < FIRST_CHAR:
            break
        if c == NEWLINE:
            line_widths.append(pen)
            pen = 0
            i += 1
            continue
        if is_two_byte(c):
            arg = expanded[i + 1] if i + 1 < len(expanded) else 0
            if c == 0xCE:
                kind, w = escape_px(arg, numeric_digits)
                if walk_pal:
                    # the 6th field is the escape index, kept so renderers can
                    # place the right icon/emoji inside the advance box
                    items.append((len(line_widths), pen, "e", w, pal, arg))
                else:
                    items.append((len(line_widths), pen, "e", w))
                pen += w
            elif c == 0xCF:
                pal = arg & 0xFF
            i += 2
            continue
        if walk_pal:
            items.append((len(line_widths), pen, "g", c, pal))
        else:
            items.append((len(line_widths), pen, "g", c))
        pen += font_advance(c, widths) + glyph_pad
        i += 1
    line_widths.append(pen)
    max_px = max(line_widths) if line_widths else 0
    return line_widths, max_px, unresolved, items


def measure_markup(text, glyph_pad=0, expander=None, numeric_digits=4,
                   accent_font=False):
    """Measure a pack-format markup string (the editor's normal text form).
    Encodes the markup to MES bytes exactly as the importer would (mirroring
    parse_text's rules), then expands + walks.  Returns
    (encoded_bytes, line_widths, max_px, unresolved, pen_items, bad_characters).
    With `accent_font` the accent width table drives the pen."""
    bs = []
    bad = []
    _, spans = parse_text(text)
    for s, e, st in spans:
        seg = text[s:e]
        if st == "ascii":
            bs.append(ord(seg))
        elif st == "newline":
            bs.append(0x7C)
        elif st == "fold":
            bs.extend(ord(ch) for ch in ascii_fold(seg))
        elif st == "high_byte":
            # Map each CP437 character to its high-byte value
            for ch in seg:
                bs.append(CP437_MAP[ch])
        elif st == "nonascii":
            bad.append(seg)
        elif st == "byte":
            if seg in ("{7b}", "{7d}"):
                bs.append(0x7B if seg == "{7b}" else 0x7D)
            else:
                bs.append(int(seg.strip("{}"), 16))
        elif st == "esc2":
            inner = seg.strip("{}")
            x, y = inner.split(":", 1)
            bs.append(int(x, 16))
            bs.append(int(y, 16))
        elif st == "sub":
            m = TOKEN_RE.match(seg)
            name = m.group(1).lower()
            arg = m.group(2)
            op = SUB_OPCODES.get(name, 0xC7)
            bs.append(op)
            if arg is not None:
                bs.append(int(arg, 16))
        elif st == "ctl":
            m = TOKEN_RE.match(seg)
            name = m.group(1).lower()
            arg = m.group(2)
            op = 0xCE if name == "ce" else 0xCF
            if arg is not None:
                bs += [op, int(arg, 16)]
            else:
                bs += [op]
    line_widths, max_px, unresolved, items = walk_bytes(
        bs, glyph_pad, expander, numeric_digits, accent_font=accent_font)
    return bs, line_widths, max_px, unresolved, items, bad


# ---------------------------------------------------------------------------
# Overdraw: does this line reach the red limit edge the preview draws?
# ---------------------------------------------------------------------------
# The old rule was a flat character count (30), which is wrong in both
# directions.  The game's box is a fixed number of *pixels* wide, and the
# retail font is proportional: 'W' costs 11px, 'i' costs 3px, so 30
# characters can be 330px (badly over) or 150px (comfortably inside).  That is
# also where the familiar "about 30 capitals, about 36 lowercases" rule of
# thumb comes from - it is the *average* case, not a limit.
#
# So the test is the same measurement the preview uses to draw its red limit
# edge: encode the markup, walk it with the real advance table, and compare
# the widest line against the surface that row is actually drawn on.  Mixed
# case then needs no special handling at all - it is just measured.

# widest advance any drawable glyph can cost, used as a cheap "cannot possibly
# overrun" bound so the common short row skips the encode entirely
MAX_GLYPH_ADVANCE = max(FONT_WIDTHS[FIRST_CHAR:]) + INTER_GLYPH_PAD


def text_px(text, lim, expander=None, numeric_digits=4, accent_font=False):
    """Widest rendered line of `text` in pixels on the surface `lim` describes.

    Falls back to a proportional estimate when the markup cannot be encoded
    (a half-typed escape, say) so a row being edited never loses its status.
    Returns (px, exact).
    """
    glyph_pad = (lim or {}).get("glyph_pad", 0)
    # only {c1..c7} substitutions read the expander (live names), so any
    # other text measures the same every time and is cached
    if _SUB_RE.search(text or "") is None:
        return _text_px_plain(text, glyph_pad, numeric_digits,
                              bool(accent_font))
    return _text_px(text, glyph_pad, expander, numeric_digits, accent_font)


_SUB_RE = re.compile(r"\{c[1-7]", re.IGNORECASE)


@functools.lru_cache(maxsize=1 << 16)
def _text_px_plain(text, glyph_pad, numeric_digits, accent_font):
    return _text_px(text, glyph_pad, None, numeric_digits, accent_font)


def _text_px(text, glyph_pad, expander, numeric_digits, accent_font):
    try:
        _bs, _lw, max_px, _un, _items, _bad = measure_markup(
            text, glyph_pad=glyph_pad, expander=expander,
            numeric_digits=numeric_digits, accent_font=accent_font)
        return max_px, True
    except Exception:
        return visible_len(text) * 6, False


def overdraw_px(text, lim, expander=None, numeric_digits=4, accent_font=False):
    """`(px, over, checked)` for one line against one surface.

    `checked` is False when no surface is known for the row, which is the
    signal to stay quiet rather than invent a limit - a name field and a
    dialogue box have nothing in common, and guessing is worse than silent.
    """
    if not lim or not (text or "").strip():
        return 0, False, False
    limit_px = lim["max_px"]
    # cheap bound first: even if every visible character were the widest glyph
    # in the font, a line this short cannot reach the edge
    if visible_len(text) * MAX_GLYPH_ADVANCE <= limit_px:
        return 0, False, True
    px, _exact = text_px(text, lim, expander, numeric_digits,
                         accent_font=accent_font)
    return px, px > limit_px, True
