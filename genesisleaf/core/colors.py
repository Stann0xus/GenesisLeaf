"""Colour maths (hex parsing, WCAG luminance/contrast, mixing).

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import re


_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def norm_color(c, fallback="#888888"):
    """Accept `#rgb`, `#rrggbb` or a bare hex triplet; return `#rrggbb`."""
    c = (c or "").strip()
    if not c.startswith("#"):
        c = "#" + c
    if not _HEX_RE.match(c):
        return fallback
    if len(c) == 4:
        c = "#" + "".join(ch * 2 for ch in c[1:])
    return c.lower()


# -- colour maths ----------------------------------------------------------
# Everything below supports palette contrast and readable color-role construction from
# one hex value, and so a selection pair is never unreadable.

def hex_to_rgb(c):
    """`#rrggbb` -> (r, g, b), 0-255 each."""
    c = norm_color(c, "#000000")
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def rgb_to_hex(rgb):
    r, g, b = (max(0, min(255, int(round(v)))) for v in rgb)
    return "#%02x%02x%02x" % (r, g, b)


def _channel_luminance(v):
    """sRGB -> linear light for one 0-255 channel (WCAG relative luminance)."""
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rel_lum(c):
    """WCAG relative luminance of a colour, 0.0 (black) to 1.0 (white)."""
    r, g, b = hex_to_rgb(c)
    return (0.2126 * _channel_luminance(r) +
            0.7152 * _channel_luminance(g) +
            0.0722 * _channel_luminance(b))


def contrast(fg, bg):
    """WCAG contrast ratio between two colours, 1.0 to 21.0."""
    a, b = rel_lum(fg), rel_lum(bg)
    lo, hi = (a, b) if a <= b else (b, a)
    return (hi + 0.05) / (lo + 0.05)


def mix(c, target, t):
    """Blend `c` toward `target` by `t` (0.0 = c, 1.0 = target)."""
    a, b = hex_to_rgb(c), hex_to_rgb(target)
    return rgb_to_hex([a[i] + (b[i] - a[i]) * t for i in range(3)])


def darken(c, t):
    return mix(c, "#000000", t)


def readable_on(fg, bg, minimum=4.5):
    """Return `fg`, or the nearest black/white that clears `minimum` contrast.

    A generated theme can land on an unreadable pair (a mid-grey accent on a
    mid-grey panel, say).  Rather than reject the colour, nudge the foreground
    the shortest distance that makes the text legible, so the picker still
    gives you the hue you asked for."""
    fg = norm_color(fg, "#000000")
    bg = norm_color(bg, "#ffffff")
    if contrast(fg, bg) >= minimum:
        return fg
    pole = "#000000" if rel_lum(bg) > 0.5 else "#ffffff"
    for step in range(1, 21):
        cand = mix(fg, pole, step / 20.0)
        if contrast(cand, bg) >= minimum:
            return cand
    return pole
