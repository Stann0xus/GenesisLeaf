"""Named Tk fonts shared by every widget, and the CJK fallback picker.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk
import tkinter.font as tkfont


# ---------------------------------------------------------------------------
# The application
# ---------------------------------------------------------------------------

# Named Tk fonts. Every widget/tag uses one of these NAME strings so that
# reconfiguring the underlying named font (family picker) live-updates the
# whole program. init_fonts(root, family) creates/updates them.
FONT_UI = "lt.ui"            # 10
FONT_UI_SM = "lt.ui_sm"      # 9
FONT_MONO = "lt.mono"        # 11
FONT_MONO_B = "lt.mono_b"    # 11 bold
FONT_UI_B = "lt.ui_b"        # 10 bold
FONT_UI_SM_B = "lt.ui_sm_b"  # 9 bold
FONT_UI_BIG = "lt.ui_big"    # 12 bold

FONT_SPECS = {
    FONT_UI: (10, "normal"),
    FONT_UI_SM: (9, "normal"),
    FONT_MONO: (11, "normal"),
    FONT_MONO_B: (11, "bold"),
    FONT_UI_B: (10, "bold"),
    FONT_UI_SM_B: (9, "bold"),
    FONT_UI_BIG: (12, "bold"),
}
FONT_DEFAULT_FAMILY = "MS Gothic"   # preferred family (JP-capable)
FONT_DEFAULT_SIZE = 11
_FONT_FAMILY = FONT_DEFAULT_FAMILY
_FONT_SIZE = FONT_DEFAULT_SIZE
_FONT_OBJS = {}


def init_fonts(root, family=FONT_DEFAULT_FAMILY, size=None):
    """Create/apply the named fonts and standard Tk fonts for this root.
    `size` is the mono (body) point size; the UI/small/big sizes scale
    proportionally so the whole program grows/shrinks together.

    Font objects must be kept referenced module-wide: tkinter's Font
    __del__ deletes the underlying named font when the object is collected,
    so a dropped reference silently removes the font from the program."""
    global _FONT_FAMILY, _FONT_SIZE
    if size is None:
        size = _FONT_SIZE
    installed = set(tkfont.families())
    if family not in installed:
        family = FONT_DEFAULT_FAMILY if FONT_DEFAULT_FAMILY in installed else \
            next(iter(sorted(installed)))
    _FONT_FAMILY = family
    _FONT_SIZE = size
    scale = size / float(FONT_DEFAULT_SIZE)
    for name, (base, weight) in FONT_SPECS.items():
        sz = max(6, int(round(base * scale)))
        fo = _FONT_OBJS.get(name)
        if fo is not None:
            fo.configure(family=family, size=sz, weight=weight)
        else:
            _FONT_OBJS[name] = tkfont.Font(root, name=name, family=family,
                                           size=sz, weight=weight)
    for tn, base in (("TkDefaultFont", 11), ("TkTextFont", 11),
                     ("TkHeadingFont", 9), ("TkMenuFont", 9)):
        sz = max(7, int(round(base * scale)))
        try:
            tkfont.nametofont(tn).configure(family=family, size=sz)
        except tk.TclError:
            pass

def font_family():
    return _FONT_FAMILY

def font_size():
    return _FONT_SIZE


# Families tried, in order, for the characters the retail atlas cannot draw
# (Japanese/CJK).  MS Gothic is the default; the first installed candidate
# wins.  Latin text never uses these - it keeps the real-glyph preview.
JP_FONT_CANDIDATES = ("MS Gothic", "MS UI Gothic", "MS PGothic", "Meiryo",
                      "Yu Gothic", "Noto Sans CJK JP", "Noto Sans JP",
                      "TakaoGothic", "IPAGothic")


def pick_jp_family(installed):
    for fam in JP_FONT_CANDIDATES:
        if fam in installed:
            return fam
    return None
