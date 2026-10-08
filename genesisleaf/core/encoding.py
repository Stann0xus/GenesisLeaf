"""Game-text markup encoding: token grammar, the accented-Latin byte map,
and `parse_text`, the byte-budget measurer every other feature builds on.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import functools
import re

from genesisleaf.core.palette import CF_MAX


# ---------------------------------------------------------------------------
# Encoding rules (measured against the exporter: budget == encoded bytes).
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r"\{([0-9a-fA-F]{1,2})(?::([0-9a-fA-F]{1,2}))?\}")

# ---------------------------------------------------------------------------
# Name-substitution opcodes (the {cN:..} markup family).
#
# The retail expander FUN_80036514 inlines the referenced name behind every
# 0xC1..=0xC5 / 0xC7 token, so each one has to resolve to a real string or the
# preview silently drops it:
#
#   {c1:..} 0xC1  character name    - live party roster slot 0-3
#                                  (arg 0x63/99 = current party leader)
#   {c2:..} 0xC2  item name         - PTR_DAT_8007436C[arg*3]
#   {c3:..} 0xC3  magic name        - PTR_s_Magic_800754D0[arg*3]
#   {c4:..} 0xC4  item name         - same table as 0xC2, second consumer
#   {c5:..} 0xC5  art name          - DAT_80075EC4 keyed (char=arg>>6,
#                                  art=arg&0x3F)
#   {c7:..} 0xC7  actor name        - the fixed 3-entry table in SCUS at
#                                  DAT_80073F24 + arg*8
#
# 0xC0 / 0xC6 have no retail substitution arm - they stay plain 2-byte glyphs.
# ---------------------------------------------------------------------------
SUB_OPS = ("c1", "c2", "c3", "c4", "c5", "c7")
SUB_OPCODES = {"c1": 0xC1, "c2": 0xC2, "c3": 0xC3, "c4": 0xC4,
               "c5": 0xC5, "c7": 0xC7}

# DAT_80073F24 + XX*8: the three 8-byte actor-name strings that share SCUS space
# with the low end of the dialog-font width table (0x80073F24..0x80073F3B).
# Not part of the text pack - it lives in the executable, so {c7:00..02} always
# shows these regardless of what the pack translated.
C7_NAMES = ("Meta", "Terra", "Ozma")

# Characters the importer folds onto ASCII bytes automatically. Most become
# one byte; the ellipsis expands to three periods.
FOLD_CHARS = set(
    "\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f"  # smart single/double quotes
    "\u2013\u2014"        # en/em dash
    "\u2026"              # ellipsis
    "\u00a0"              # NBSP
)

# ---------------------------------------------------------------------------
# Accented-Latin layout - a byte-for-byte port of the LATIN_CELLS table in
# crates/font/src/latin.rs (the one table every consumer reads).
#
#   CP437_MAP    typed character -> dialog-font byte, for the cells the
#                accent font DRAWS (Rust's drawn_byte_for_char).  These are
#                the characters the importer can encode as a single {xx} byte.
#   ACCENT_FOLD  typed character -> plain-ASCII fold, for Latin letters with
#                no drawable byte (Rust's fold_for_char).  The importer folds
#                them; they never encode as a high byte.
# ---------------------------------------------------------------------------
CP437_MAP = {
    # CP437 0x80-0x9F:
    '\u00c7': 0x80,   # Ç  C + cedilla
    '\u00fc': 0x81,   # ü  u + diaeresis
    '\u00e9': 0x82,   # é  e + acute
    '\u00e2': 0x83,   # â  a + circumflex
    '\u00e4': 0x84,   # ä  a + diaeresis
    '\u00e0': 0x85,   # à  a + grave
    '\u00e5': 0x86,   # å  a + ring
    '\u00e7': 0x87,   # ç  c + cedilla
    '\u00ea': 0x88,   # ê  e + circumflex
    '\u00eb': 0x89,   # ë  e + diaeresis
    '\u00e8': 0x8a,   # è  e + grave
    '\u00ef': 0x8b,   # ï  i + diaeresis
    '\u00ee': 0x8c,   # î  i + circumflex
    '\u00ec': 0x8d,   # ì  i + grave
    '\u00c4': 0x8e,   # Ä  A + diaeresis
    '\u00c5': 0x8f,   # Å  A + ring
    '\u00c9': 0x90,   # É  E + acute
    '\u00e6': 0x91,   # æ  ae ligature
    '\u00c6': 0x92,   # Æ  AE ligature
    '\u00f4': 0x93,   # ô  o + circumflex
    '\u00f6': 0x94,   # ö  o + diaeresis
    '\u00f2': 0x95,   # ò  o + grave
    '\u00fb': 0x96,   # û  u + circumflex
    '\u00f9': 0x97,   # ù  u + grave
    '\u00ff': 0x98,   # ÿ  y + diaeresis
    '\u00d6': 0x99,   # Ö  O + diaeresis
    '\u00dc': 0x9a,   # Ü  U + diaeresis
    '\u00e3': 0x9b,   # ã  a + tilde
    '\u0153': 0x9c,   # œ  oe ligature
    '\u0152': 0x9e,   # Œ  OE ligature
    '\u0178': 0x9f,   # Ÿ  Y + diaeresis
    # CP437 0xA0-0xAD (¤¢£¥₧ƒ¬½¼ are not cells in this layout):
    '\u00e1': 0xa0,   # á  a + acute
    '\u00ed': 0xa1,   # í  i + acute
    '\u00f3': 0xa2,   # ó  o + acute
    '\u00fa': 0xa3,   # ú  u + acute
    '\u00f1': 0xa4,   # ñ  n + tilde
    '\u00d1': 0xa5,   # Ñ  N + tilde
    '\u00bf': 0xa8,   # ¿  inverted ?
    '\u00a1': 0xad,   # ¡  inverted !
    # CP850-style capitals the accent font draws (0xB5-0xED):
    '\u00c1': 0xb5,   # Á  A + acute
    '\u00c2': 0xb6,   # Â  A + circumflex
    '\u00c0': 0xb7,   # À  A + grave
    '\u00c3': 0xd0,   # Ã  A + tilde
    '\u00ca': 0xd2,   # Ê  E + circumflex
    '\u00cb': 0xd3,   # Ë  E + diaeresis
    '\u00c8': 0xd4,   # È  E + grave
    '\u00cd': 0xd6,   # Í  I + acute
    '\u00ce': 0xd7,   # Î  I + circumflex
    '\u00cf': 0xd8,   # Ï  I + diaeresis
    '\u00cc': 0xde,   # Ì  I + grave
    '\u00d3': 0xe0,   # Ó  O + acute
    '\u00df': 0xe1,   # ß  drawn sharp s
    '\u00d4': 0xe2,   # Ô  O + circumflex
    '\u00d2': 0xe3,   # Ò  O + grave
    '\u00f5': 0xe4,   # õ  o + tilde
    '\u00d5': 0xe5,   # Õ  O + tilde
    '\u00da': 0xe9,   # Ú  U + acute
    '\u00db': 0xea,   # Û  U + circumflex
    '\u00d9': 0xeb,   # Ù  U + grave
    '\u00dd': 0xed,   # Ý  Y + acute
    '\u00b0': 0xf8,   # °  drawn degree sign
}

# Latin letters that fold to ASCII but never draw (no byte cell): the
# ordinal indicators (ª/º) and latin.rs's FOLD_ONLY list.
ACCENT_FOLD = {
    '\u00aa': 'a',   # ª
    '\u00ba': 'o',   # º
    '\u0105': 'a',   # ą
    '\u0104': 'A',   # Ą
    '\u0107': 'c',   # ć
    '\u0106': 'C',   # Ć
    '\u010d': 'c',   # č
    '\u010c': 'C',   # Č
    '\u010f': 'd',   # ď
    '\u010e': 'D',   # Ď
    '\u0119': 'e',   # ę
    '\u0118': 'E',   # Ę
    '\u011b': 'e',   # ě
    '\u011a': 'E',   # Ě
    '\u011f': 'g',   # ğ
    '\u011e': 'G',   # Ğ
    '\u0131': 'i',   # ı
    '\u0130': 'I',   # İ
    '\u0142': 'l',   # ł
    '\u0141': 'L',   # Ł
    '\u0144': 'n',   # ń
    '\u0143': 'N',   # Ń
    '\u0148': 'n',   # ň
    '\u0147': 'N',   # Ň
    '\u0151': 'o',   # ő
    '\u0150': 'O',   # Ő
    '\u00f8': 'o',   # ø
    '\u00d8': 'O',   # Ø
    '\u0159': 'r',   # ř
    '\u0158': 'R',   # Ř
    '\u015b': 's',   # ś
    '\u015a': 'S',   # Ś
    '\u0161': 's',   # š
    '\u0160': 'S',   # Š
    '\u015f': 's',   # ş
    '\u015e': 'S',   # Ş
    '\u0165': 't',   # ť
    '\u0164': 'T',   # Ť
    '\u016f': 'u',   # ů
    '\u016e': 'U',   # Ů
    '\u0171': 'u',   # ű
    '\u0170': 'U',   # Ű
    '\u00fd': 'y',   # ý
    '\u017a': 'z',   # ź
    '\u0179': 'Z',   # Ź
    '\u017c': 'z',   # ż
    '\u017b': 'Z',   # Ż
    '\u017e': 'z',   # ž
    '\u017d': 'Z',   # Ž
    '\u00f0': 'd',   # ð
    '\u00d0': 'D',   # Ð
    '\u00fe': 'th',  # þ
    '\u00de': 'Th',  # Þ
    '\u00ab': '"',   # «
    '\u00bb': '"',   # »
}

# The editor consumes the span style strings returned by parse_text directly.


def parse_text(s):
    """Return (encoded_byte_len, spans) for a game-text string - see
    `_parse_text`.  Memoised: a pack load and every status refresh parse
    the same strings many times over.  `spans` is a tuple, so a cached
    result cannot be changed by a caller."""
    if not isinstance(s, str):
        return _parse_text(s)
    return _parse_text_cached(s)


def _parse_text(s):
    """Return (encoded_byte_len, spans) for a game-text string.

    spans: list of (start_char, end_char, style); style in
    {'ascii','newline','byte','esc2','sub','ctl','fold','nonascii'}.
    Rules (from the translation guidelines):
      printable ASCII     1 byte
      '|' newline glyph   1 byte
      {xx}  bare byte     1 byte
      {xx:yy} raw escape  2 bytes
      {c1|2|3|4|5|7}:..   2 bytes   (bare {c1} = 1 byte)
      {cf|ce}:..          2 bytes   (bare = 1 byte)
      {7b}/{7d} braces    1 byte
      smart quotes/dash/NBSP -> 1 ASCII byte; ellipsis -> 3 ASCII bytes
      drawn Latin cell (CP437_MAP) -> 1 high byte
      fold-only Latin letter (ACCENT_FOLD) -> folded to ASCII
      any other non-ASCII -> NOT ENCODABLE (still counted 1 byte for display)
    """
    total = 0
    spans = []
    n = len(s)
    i = 0
    while i < n:
        ch = s[i]
        if ch == "{":
            m = TOKEN_RE.match(s, i)
            if m:
                name = m.group(1).lower()
                arg = m.group(2)
                end = m.end()
                if name in ("7b", "7d"):
                    total += 1
                    spans.append((i, end, "byte"))
                elif name in SUB_OPS:
                    total += 2 if arg else 1
                    spans.append((i, end, "sub"))
                elif name in ("ce", "cf"):
                    total += 2 if arg else 1
                    spans.append((i, end, "ctl"))
                else:
                    total += 2 if arg else 1
                    spans.append((i, end, "esc2" if arg else "byte"))
                i = end
                continue
            total += 1
            spans.append((i, i + 1, "ascii"))
            i += 1
            continue
        if ch == "|":
            total += 1
            spans.append((i, i + 1, "newline"))
            i += 1
            continue
        if ord(ch) < 128:
            total += 1
            spans.append((i, i + 1, "ascii"))
            i += 1
            continue
        if ch in CP437_MAP:
            total += 1
            spans.append((i, i + 1, "high_byte"))
            i += 1
            continue
        if ch in FOLD_CHARS:
            total += 3 if ch == "\u2026" else 1
            spans.append((i, i + 1, "fold"))
            i += 1
            continue
        if ch in ACCENT_FOLD:
            total += len(ACCENT_FOLD[ch])
            spans.append((i, i + 1, "fold"))
            i += 1
            continue
        total += 1
        spans.append((i, i + 1, "nonascii"))
        i += 1
    return total, tuple(spans)


@functools.lru_cache(maxsize=1 << 17)
def _parse_text_cached(s):
    return _parse_text(s)


def visible_len(text):
    """How many characters the player actually sees on screen.

    Markup codes ({cf:03}, {c1:00}, {7b}, ...) and the | line break are
    instructions to the game, not glyphs, so they must not count towards
    "does this line overrun the box".  The 0xC7 substitution glyph is one
    character, so it counts as one.  Anything else is counted per character,
    which is the same count the editor already uses for the byte budget.
    """
    return len(TOKEN_RE.sub("", text or "").replace("|", ""))


def bad_cf_codes(text):
    """Return the text fragments of every {cf:..} whose argument is outside
    the valid 0-9 range.  The game only knows ten ink colours; anything else
    is not a real markup code and would break the dialogue, so the editor
    must reject it."""
    out = []
    for s, e, st in parse_text(text)[1]:
        if st != "ctl":
            continue
        m = TOKEN_RE.match(text[s:e])
        if not m or m.group(1).lower() != "cf" or m.group(2) is None:
            continue
        try:
            arg = int(m.group(2), 16)
        except ValueError:
            out.append(text[s:e])
            continue
        if arg > CF_MAX:
            out.append(text[s:e])
    return out
