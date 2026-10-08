"""The {cf:..} ink palette, the retail dialog-window chrome colours, and the
live *preview scheme* every real-font renderer draws with.

`PALETTES` / `PV_*` are the retail values (read off the game's VRAM) and
never change.  What the renderers actually paint comes from `SCHEME`, a dict
the theme fills in place (see ui.theme.apply_preview_scheme): either the
retail look, or colours derived from the active theme.  Because SCHEME is
mutated rather than rebound it is safe to import by name.

`PV_WHITE` is kept for compatibility and is also live: read it as
`_palette.PV_WHITE`, never `from ... import PV_WHITE`.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""


# The in-game {cf:0n} colour controls. Only 0-9 are valid: a cf argument above
# 9 is not a markup code and would break the game, so the editor rejects it.
# Preview only - not layout authority.
#
# A {cf:n} does not carry a colour: it stages CLUT additive index n, and the
# glyph ink is **entry 15** of the 16-colour CLUT the renderer then reads at
# VRAM (16*(6+n), 510) - FUN_80036888 pushes CLUT word `n + 0x7F86` into every
# per-glyph GP0 0x64 packet (docs/formats/dialog-font.md "CLUT",
# docs/subsystems/field-menu.md "Ink CLUT rows").  PALETTES below is that
# entry-15 value per index, read off the retail menu_status_town VRAM:
#
#   0 grey (dim / non-selected)   5 teal     (separators, base values)
#   1 lavender (command labels)   6 gold     (warning tier, headers)
#   2 red (downed, 0 HP)          7 DEFAULT  (normal text - see below)
#   4 green (skill passives)      9 orange   (critical tier)
#
# 7 is NOT a grey/dim ink: retail stages 7 before drawing a normal dialog
# string (shop list, world-map labels, option picker, battle chrome), so
# {cf:07} is the "back to the game's normal text colour" reset that closes
# every coloured span in the source - which is why the pack ends runs with it
# ("{cf:09}{c7:00}{cf:07}: ...").  Its ink is (206,206,206), a touch off pure
# white, and index 8 is the brighter white the editor draws uncoloured text
# with.  3 and 8 are real CLUTs but were not present in the reference capture,
# so those two are the editor's own picks.
CF_MAX = 9

# Ink of a string that carries no {cf:..} at all. Retail stages 7 here.
DEFAULT_PALETTE = 7

PALETTES = {
    0: (132, 132, 132),   # grey - dim / non-selected rows
    1: (107, 107, 231),   # lavender - command labels, arrows
    2: (231, 33, 0),      # red - downed party member, 0 HP
    3: (190, 90, 225),    # violet (not in the reference capture)
    4: (107, 222, 107),   # green - skill passives
    5: (66, 222, 222),    # teal - separators, base stat values
    6: (231, 173, 0),     # gold - warning tier, magic header
    7: (206, 206, 206),   # the game's DEFAULT text ink - the {cf:07} reset
    8: (255, 255, 255),   # brighter white - uncoloured text
    9: (222, 90, 0),      # orange - critical tier, moves header
}

# Previews only: ink 1 is blue on the blue dialog box and unreadable there.
PREVIEW_INK_FIX = {1: (255, 226, 90)}

# window chrome the retail dialog window uses when it draws a box row
PV_RIM = (0xB8, 0xC0, 0xD8)
PV_BG = (0x10, 0x18, 0x48)
PV_PAST = (0x4A, 0x18, 0x22)
PV_LIMIT = (0xFF, 0x60, 0x60)
PV_ESC = (0x70, 0x80, 0xA0)
PV_SHADOW = (0x20, 0x20, 0x20)
PV_WHITE = (0xFF, 0xFF, 0xFF)

# The reading box's fill (FUN_8002C69C): two blend-mode-0 gouraud quads,
# top (0x18,0x18,0x28) -> bottom (0x40,0x40,0xA0), composing to
# 0.25*scene + 0.75*gradient.  The preview has no scene behind the box, so
# it composes over black.
PV_FILL_TOP = (0x12, 0x12, 0x1E)
PV_FILL_BOT = (0x30, 0x30, 0x78)
PV_SCENE = (0, 0, 0)


# -- live preview scheme ------------------------------------------------------
def preview_inks():
    """PALETTES with the readability overrides applied (blue -> yellow)."""
    inks = dict(PALETTES)
    inks.update(PREVIEW_INK_FIX)
    return inks


def retail_scheme(white=PV_WHITE):
    """The game's own dialog window: dark blue box, light rim, retail inks.
    `white` is the ink used for {cf:08} / untinted icons."""
    inks = preview_inks()
    inks[8] = tuple(white)
    return {"rim": PV_RIM, "bg": PV_BG, "past": PV_PAST, "limit": PV_LIMIT,
            "fill_top": PV_FILL_TOP, "fill_bot": PV_FILL_BOT,
            "scene": PV_SCENE, "frame": None,
            "esc": PV_ESC, "shadow": PV_SHADOW, "white": tuple(white),
            "inks": inks, "grid_ink": (198, 216, 248), "grid_bg": (18, 24, 44)}


# What every renderer paints with.  Mutated in place by apply_scheme().
SCHEME = retail_scheme()

# Real-font previews follow the active theme unless the user picked the
# retail colours (Real font options).  Read as `_palette.FOLLOW_THEME`.
FOLLOW_THEME = True


def apply_scheme(scheme):
    """Make `scheme` the live preview scheme (in place, so importers see it)."""
    global PV_WHITE
    SCHEME.clear()
    SCHEME.update(scheme)
    PV_WHITE = tuple(scheme["white"])


def ink(pal):
    """RGB ink of {cf:pal} under the live scheme."""
    return SCHEME["inks"].get(pal & 0xFF, SCHEME["white"])

