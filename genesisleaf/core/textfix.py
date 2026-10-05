"""Text folding / clean-up helpers used by Auto-fix, the importer rules and
the conflict listings.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import re
import unicodedata

from genesisleaf.core.encoding import ACCENT_FOLD, parse_text


# ---------------------------------------------------------------------------
# Character folding + auto-fix helpers.
# ---------------------------------------------------------------------------

FOLD_CHARS_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201a": ",", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " ",
}

LIGATURE_FOLD = {
    "\u00df": "ss", "\u00c6": "Ae", "\u00e6": "ae",
    "\u0152": "Oe", "\u0153": "oe", "\u00d8": "O", "\u00f8": "o",
    "\u0110": "D", "\u0111": "d", "\u0141": "L", "\u0142": "l",
    "\u00d0": "D", "\u00f0": "d", "\u00de": "Th", "\u00fe": "th",
}


def ascii_fold(s):
    """Best-effort fold of non-ASCII letters to ASCII (safe for the budget)."""
    out = []
    for ch in s:
        if ord(ch) < 0x80:
            out.append(ch)
            continue
        if ch in LIGATURE_FOLD:
            out.append(LIGATURE_FOLD[ch])
            continue
        if ch in ACCENT_FOLD:
            out.append(ACCENT_FOLD[ch])
            continue
        if ch in FOLD_CHARS_MAP:
            out.append(FOLD_CHARS_MAP[ch])
            continue
        d = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in d if not unicodedata.combining(c))
        if base and all(ord(c) < 0x80 for c in base):
            out.append(base)
        else:
            out.append(ch)
    return "".join(out)


def normalize_newlines(s):
    return re.sub(r"\r\n|\r|\n", "|", s)


def collapse_spaces(s):
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def oneline(s, limit=120):
    """One-line, tab-free, length-capped form of a translation, for the
    conflict listing.  A dialog row is a real line (`|`), and a real newline or
    tab inside it would break the tab-separated columns the listing relies on to
    be read one row at a time."""
    s = collapse_spaces(str(s).replace("\r", " ").replace("\n", " ")) \
        .replace("\t", " ")
    return s if len(s) <= limit else s[:limit - 1] + "~"


def truncate_to_budget(text, budget):
    """Shorten text to fit `budget` encoded bytes, cutting only between words
    or at '|' row boundaries so control tokens always survive.  Falls back to
    hard-cutting only when nothing else fits. Returns (new_text, changed)."""
    b, _ = parse_text(text)
    if b <= budget:
        return text, False
    if budget <= 0:
        return "", True
    marks = [i + 1 for i, ch in enumerate(text) if ch in (" ", "|")]
    cur, cb = text, b
    while cb > budget and marks:
        pos = marks.pop()
        if pos >= len(cur):
            continue
        cand = cur[:pos].rstrip()
        if not cand:
            continue
        ncb, _ = parse_text(cand)
        cur, cb = cand, ncb
    if cb > budget:
        while cb > budget and cur:
            cur = cur[:-1]
            cb, _ = parse_text(cur)
    return cur, cur != text


def round_1(x):
    try:
        return ("%.1f" % x)
    except Exception:
        return str(x)
