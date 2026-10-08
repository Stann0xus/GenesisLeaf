"""Fixed application palettes and live preview colours.

GenesisLeaf ships fixed light and dark palettes, also used to tint the game's
graphical menu chrome. Widgets read the live ``TH_*``
roles from this module; :func:`set_theme` updates those roles in one pass.
"""

import colorsys

from genesisleaf.core import palette as _palette
from genesisleaf.core.colors import (
    contrast, darken, hex_to_rgb, mix, norm_color, readable_on, rel_lum, rgb_to_hex,
)
from genesisleaf.ui.fonts import FONT_MONO_B


_THEME_KEYS = (
    "TH_FRAME_BG", "TH_PANEL_BG", "TH_CHROME_BG", "TH_BORDER",
    "TH_FG", "TH_FG_MUTED", "TH_FG_FAINT", "TH_ACCENT",
    "TH_BTN_BG", "TH_BTN_FG", "TH_BTN_HOVER", "TH_SCROLL",
    "TH_OK", "TH_WARN", "TH_BAD", "TH_OVERDRAW_SRC", "TH_OVERDRAW_TR",
    "TH_BAND_A", "TH_BAND_B", "TH_TREE_BG", "TH_HEAD_BG", "TH_HEAD_FG",
    "TH_SEL_BG", "TH_FIELD_BG", "TH_SEL_FG", "BG_EDIT", "FG_MAIN",
    "FG_DIM", "APP_BG",
)

# The primary palette is deliberately calm and high-contrast: cool surfaces,
# one blue action color, and consistent semantic status colors.  Buttons,
# borders and scrollbars each get their own hue (blue / slate / teal).
_DEFAULT = {
    "TH_FRAME_BG": "#eef2f7", "TH_PANEL_BG": "#f9fbfd", "TH_CHROME_BG": "#dce5ef",
    "TH_BORDER": "#c9b27a", "TH_FG": "#17212b", "TH_FG_MUTED": "#536477",
    "TH_FG_FAINT": "#7e8d9d", "TH_ACCENT": "#1769aa",
    "TH_BTN_BG": "#1769aa", "TH_BTN_FG": "#ffffff", "TH_BTN_HOVER": "#0f4d7a",
    "TH_SCROLL": "#c2a15a",
    "TH_OK": "#146c3a", "TH_WARN": "#8a5800", "TH_BAD": "#b42318", "TH_OVERDRAW_SRC": "#a64b08",
    "TH_OVERDRAW_TR": "#8c5a00", "TH_BAND_A": "#ffffff", "TH_BAND_B": "#eaf0f6",
    "TH_TREE_BG": "#ffffff", "TH_HEAD_BG": "#e3d3a8", "TH_HEAD_FG": "#2b1d08",
    "TH_SEL_BG": "#b8d8f2", "TH_FIELD_BG": "#ffffff", "TH_SEL_FG": "#102a43",
    "BG_EDIT": "#101820", "FG_MAIN": "#f2f6fa", "FG_DIM": "#c5d0db", "APP_BG": "#263746",
}

# A dark alternative for dim rooms and users who prefer reduced glare.  It
# remains a complete palette, not a transformed copy, so contrast is explicit.
_DARK = {
    "TH_FRAME_BG": "#101923", "TH_PANEL_BG": "#172432", "TH_CHROME_BG": "#203244",
    "TH_BORDER": "#9c8a52", "TH_FG": "#edf4fa", "TH_FG_MUTED": "#afc1d1",
    "TH_FG_FAINT": "#7890a3", "TH_ACCENT": "#65b5f0",
    "TH_BTN_BG": "#2563eb", "TH_BTN_FG": "#ffffff", "TH_BTN_HOVER": "#1e40af",
    "TH_SCROLL": "#c9a74a",
    "TH_OK": "#75d69b", "TH_WARN": "#f2c35e", "TH_BAD": "#ff8b83", "TH_OVERDRAW_SRC": "#ffad67",
    "TH_OVERDRAW_TR": "#f0c56d", "TH_BAND_A": "#14212d", "TH_BAND_B": "#1b2b3a",
    "TH_TREE_BG": "#14212d", "TH_HEAD_BG": "#4a3a24", "TH_HEAD_FG": "#f5f9fc",
    "TH_SEL_BG": "#315b7a", "TH_FIELD_BG": "#1b2a38", "TH_SEL_FG": "#ffffff",
    "BG_EDIT": "#0b121a", "FG_MAIN": "#eaf3fa", "FG_DIM": "#a9bdcf", "APP_BG": "#0e1721",
}

# The game's own pause-menu look: navy marbled windows (the "filigree"), gold-
# bronze frames, tan highlights, warm-white text.  Every colour is sampled from
# the menu sprites (assets/menu_skin.py / window_skin.py): the interior runs
# #10187b..#3142b5, the frame #422908 / #846342 / #cea584.  The surfaces are
# the interior darkened the way the retail windows darken it (their gouraud
# gradient multiplies the tile by 0.5..1.06).  Button text is yellow: the
# plates are blue art, so dark/blue text on them is unreadable.
_LEGAIA = {
    "TH_FRAME_BG": "#0f1766", "TH_PANEL_BG": "#0b1250", "TH_CHROME_BG": "#0b1252",
    "TH_BORDER": "#846342", "TH_FG": "#f6f2e6", "TH_FG_MUTED": "#cfc7b0",
    "TH_FG_FAINT": "#9aa2d8", "TH_ACCENT": "#f2cb6b",
    "TH_BTN_BG": "#2b3aa8", "TH_BTN_FG": "#ffe066", "TH_BTN_HOVER": "#3a52d6",
    "TH_SCROLL": "#a8845a",
    "TH_OK": "#86e69c", "TH_WARN": "#ffd35c", "TH_BAD": "#ff8f86", "TH_OVERDRAW_SRC": "#ffb36e",
    "TH_OVERDRAW_TR": "#f2d46f", "TH_BAND_A": "#0c1458", "TH_BAND_B": "#131d78",
    "TH_TREE_BG": "#0c1458", "TH_HEAD_BG": "#3f397f", "TH_HEAD_FG": "#f6f2e6",
    "TH_SEL_BG": "#3a52d6", "TH_FIELD_BG": "#080d38", "TH_SEL_FG": "#ffffff",
    "BG_EDIT": "#070b2e", "FG_MAIN": "#f6f2e6", "FG_DIM": "#c4bfdc", "APP_BG": "#070b2e",
}


# -- theme construction ------------------------------------------------------
def _hue_shift(color, degrees):
    r, g, b = (v / 255.0 for v in hex_to_rgb(color))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    r, g, b = colorsys.hsv_to_rgb((h + degrees / 360.0) % 1.0, s, v)
    return rgb_to_hex((r * 255, g * 255, b * 255))


def _chroma(color):
    r, g, b = hex_to_rgb(color)
    return max(r, g, b) - min(r, g, b)


def _near(a, b, dist=60):
    return sum((x - y) ** 2 for x, y in zip(hex_to_rgb(a), hex_to_rgb(b))) < dist * dist


def _visible(color, surface, ratio=2.2):
    """Lighten `color` until it stands out from `surface`."""
    for _ in range(6):
        if contrast(color, surface) >= ratio:
            break
        color = mix(color, "#ffffff", 0.25)
    return color


def _dark_theme(surface, accent, button, **over):
    """A complete dark palette in the retail menu's arrangement: `surface` is
    the main UI colour, `button` the plates on it, and the `accent` metal
    (the menu's gold) frames the windows and fills the scrollbars, with darker
    bronze tabs and headings."""
    fg = mix("#ffffff", surface, 0.06)
    border = _visible(mix(accent, surface, 0.4), surface)
    scroll = _visible(mix(accent, surface, 0.1), surface)
    head = mix(darken(accent, 0.55), surface, 0.25)
    sel = mix(surface, accent, 0.45)
    theme = {
        "TH_FRAME_BG": surface,
        "TH_PANEL_BG": mix(surface, "#ffffff", 0.05),
        "TH_CHROME_BG": mix(surface, "#ffffff", 0.10),
        "TH_BORDER": border,
        "TH_FG": fg,
        "TH_FG_MUTED": mix(fg, surface, 0.28),
        "TH_FG_FAINT": mix(fg, surface, 0.52),
        "TH_ACCENT": accent,
        "TH_BTN_BG": button,
        "TH_BTN_FG": "#ffffff" if contrast("#ffffff", button) >= contrast("#101010", button)
        else "#101010",
        "TH_BTN_HOVER": mix(button, "#ffffff", 0.18),
        "TH_SCROLL": scroll,
        "TH_OK": "#75d69b", "TH_WARN": "#f2c35e", "TH_BAD": "#ff8b83",
        "TH_OVERDRAW_SRC": "#ffad67", "TH_OVERDRAW_TR": "#f0c56d",
        "TH_BAND_A": surface, "TH_BAND_B": mix(surface, "#ffffff", 0.05),
        "TH_TREE_BG": surface,
        "TH_HEAD_BG": head, "TH_HEAD_FG": readable_on(fg, head),
        "TH_SEL_BG": sel, "TH_SEL_FG": readable_on("#ffffff", sel),
        "TH_FIELD_BG": darken(surface, 0.22),
        "BG_EDIT": darken(surface, 0.5), "FG_MAIN": fg,
        "FG_DIM": mix(fg, surface, 0.35), "APP_BG": darken(surface, 0.4),
    }
    theme.update(over)
    return theme


def _palette_theme(spec):
    """A dark theme from a game palette (a string of 3-5 hex colours): the
    darkest colour becomes the surface, the most vivid one the buttons, the
    lightest the accent (frames, scrollbars)."""
    pool = []
    for c in spec.split():
        c = norm_color(c)
        if c not in pool:
            pool.append(c)
    dark = min(pool, key=rel_lum)
    surface = darken(dark, 0.45)
    while rel_lum(surface) > 0.035:
        surface = darken(surface, 0.3)
    rest = [c for c in pool if c != dark] or pool
    button = max(rest, key=lambda c: _chroma(c) - abs(rel_lum(c) - 0.3) * 100)
    others = [c for c in rest if c != button]
    accent = max(others, key=rel_lum) if others else mix(button, "#ffffff", 0.4)
    return _dark_theme(surface, accent, button)


def _palette_themes(table):
    return {name: _palette_theme(spec) for name, spec in table.items()}


def _separate_controls(values):
    """Keep interactive chrome visibly distinct from each non-default surface."""
    surface = values["TH_FRAME_BG"]
    border = _visible(values["TH_BORDER"], surface, 2.0)
    scroll = _visible(values["TH_SCROLL"], surface, 2.0)
    button = _visible(values["TH_BTN_BG"], surface, 2.0)
    if _near(scroll, border, 42):
        scroll = _visible(_hue_shift(scroll, 38), surface, 2.0)
        if _near(scroll, border, 42):
            scroll = _visible(mix(scroll, "#ffffff" if rel_lum(surface) < 0.45
                                  else "#000000", 0.35), surface, 2.0)
    if _near(button, border, 42) or _near(button, scroll, 42):
        button = _visible(_hue_shift(button, -38), surface, 2.0)
        if _near(button, border, 42) or _near(button, scroll, 42):
            button = _visible(mix(button, "#ffffff" if rel_lum(surface) < 0.45
                                  else "#000000", 0.35), surface, 2.0)
    values.update(TH_BORDER=border, TH_SCROLL=scroll, TH_BTN_BG=button)
    return values


# -- the sections of the theme menu --------------------------------------------
_CLASSIC = {
    "Default": _DEFAULT,
    "Midnight": _DARK,
    "Forest": _dark_theme("#10251c", "#8ed6a0", "#4f9d63"),
    "Amethyst": _dark_theme("#21172e", "#cca5f5", "#9b59d0"),
    "Ember": _dark_theme("#2b1b17", "#f0b17a", "#d9622b"),
    "Ocean": _dark_theme("#10262c", "#7fd9dc", "#1f8fb8"),
}

_SOLARIZED_LIGHT = {
    "TH_FRAME_BG": "#fdf6e3", "TH_PANEL_BG": "#ffffff", "TH_CHROME_BG": "#eee8d5",
    "TH_BORDER": "#cbb675", "TH_FG": "#586e75", "TH_FG_MUTED": "#657b83",
    "TH_FG_FAINT": "#839496", "TH_ACCENT": "#268bd2",
    "TH_BTN_BG": "#268bd2", "TH_BTN_FG": "#ffffff", "TH_BTN_HOVER": "#1f6fa0",
    "TH_SCROLL": "#b58900",
    "TH_OK": "#718200", "TH_WARN": "#966f00", "TH_BAD": "#dc322f", "TH_OVERDRAW_SRC": "#d33682",
    "TH_OVERDRAW_TR": "#cb4b16", "TH_BAND_A": "#ffffff", "TH_BAND_B": "#f7f3e9",
    "TH_TREE_BG": "#ffffff", "TH_HEAD_BG": "#e6d9b0", "TH_HEAD_FG": "#073642",
    "TH_SEL_BG": "#d6eef5", "TH_FIELD_BG": "#ffffff", "TH_SEL_FG": "#073642",
    "BG_EDIT": "#002b36", "FG_MAIN": "#fdf6e3", "FG_DIM": "#93a1a1", "APP_BG": "#073642",
}

_EDITOR = {
    "Solarized Light": _SOLARIZED_LIGHT,
    "Solarized Dark": _dark_theme("#002b36", "#2aa198", "#268bd2",
                                  TH_FG="#93a1a1", TH_FG_MUTED="#839496",
                                  TH_FG_FAINT="#657b83", TH_SEL_FG="#fdf6e3"),
    "Nord": _dark_theme("#2e3440", "#88c0d0", "#5e81ac"),
    "Dracula": _dark_theme("#282a36", "#8be9fd", "#bd93f9"),
    "Gruvbox Dark": _dark_theme("#282828", "#fabd2f", "#d65d0e"),
    "Monokai": _dark_theme("#272822", "#a6e22e", "#f92672"),
    "One Dark": _dark_theme("#282c34", "#61afef", "#c678dd"),
    "Tokyo Night": _dark_theme("#1a1b26", "#7aa2f7", "#bb9af7"),
    "Catppuccin Mocha": _dark_theme("#1e1e2e", "#89b4fa", "#cba6f7"),
    "High Contrast": _dark_theme("#000000", "#ffff00", "#0070d0"),
}

_RA_SERU = _palette_themes({
    "Mist (Seru)": "#4000FF #8020FF #200080 #A080FF #100040",
    "Ra-Seru Fire": "#FF4000 #FF8020 #C02000 #FFD080 #802000",
    "Ra-Seru Wind": "#40FF00 #80FF80 #008000 #C0FFC0 #20A020",
    "Ra-Seru Thunder": "#FFFF00 #FFFF80 #C0C000 #FFFAC0 #808000",
    "Ra-Seru Earth": "#FF8020 #C06000 #804000 #FFB060 #402000",
    "Ra-Seru Water": "#0080FF #40C0FF #004080 #C0E0FF #0060C0",
    "Ra-Seru Holy": "#FFFFFF #FFFFC0 #FFD700 #FFF8DC #C0C0FF",
    "Ra-Seru Dark": "#4000FF #8020FF #200080 #A080FF #100040",
})

_SERU = _palette_themes({
    "Gimard (Fire)": "#FF4000 #FF8020 #C02000 #802000 #FFD080",
    "Sonic (Wind)": "#40FF00 #80FF80 #008000 #C0FFC0 #20A020",
    "Theeder (Thunder)": "#FFFF00 #FFFF80 #C0C000 #808000 #FFFAC0",
    "Vera (Earth)": "#FF8020 #C06000 #804000 #FFB060 #402000",
    "Swordie (Water)": "#0080FF #40C0FF #004080 #C0E0FF #0060C0",
    "Freed (Holy)": "#FFFFFF #FFFFC0 #FFD700 #FFF8DC #C0C0FF",
    "Nova (Dark)": "#4000FF #8020FF #200080 #A080FF #100040",
    "Mushura (Nature)": "#40FF00 #C0FF80 #208000 #E0FFC0 #006000",
    "Gizam (Ice)": "#80FFFF #C0FFFF #0080C0 #E0FFFF #005080",
    "Lapis (Water)": "#0080FF #80C0FF #004080 #C0E0FF #003060",
    "Horn (Earth)": "#FF8020 #FFC080 #804000 #FFE0C0 #603000",
    "Aluru (Wind)": "#40FF00 #A0FF80 #208000 #D0FFB0 #105000",
    "Barra (Fire)": "#FF4000 #FF8040 #A02000 #FFC0A0 #601000",
    "Nighto (Dark)": "#4000FF #6020C0 #200060 #A080E0 #100030",
    "Zenoir (Holy)": "#FFFFFF #FFFAC0 #FFD700 #FFF0D0 #D0C0FF",
    "Kemaro (Thunder)": "#FFFF00 #FFFFA0 #C0C000 #FFFAE0 #808000",
    "Spoon (Earth)": "#FF8020 #E0A060 #804000 #FFD0A0 #503000",
    "Ozma (Dark)": "#4000FF #7020FF #200080 #B090FF #080020",
    "Meta (Fire)": "#FF4000 #FF9060 #A02000 #FFD0B0 #501000",
    "Terra (Nature)": "#40FF00 #90FF60 #208000 #D0FFB0 #104000",
})

# Spells, grouped by element; SECTION_BREAKS puts a separator before the
# first spell of each group in the menu.
_SPELL_GROUPS = (
    {"Fire Blow": "#FF4000 #FF8020 #C02000", "Burning Attack": "#FF4000 #FF6000 #802000",
     "Fire Breath": "#FF4000 #FFA040 #A02000", "Explosion": "#FF4000 #FFFF00 #C02000",
     "Flame": "#FF4000 #FFB060 #801000"},
    {"Wind Blade": "#40FF00 #A0FF80 #208000", "Healing Wind": "#40FF00 #C0FFC0 #008000",
     "Sonic Wave": "#40FF00 #80FF80 #106000", "Storm": "#40FF00 #80FFFF #208000"},
    {"Thunder Storm": "#FFFF00 #FFFFC0 #C0C000", "Lightning": "#FFFF00 #FFFFFF #808000",
     "Thunderbolt": "#FFFF00 #FFFF80 #A0A000", "Shock": "#FFFF00 #FFFAC0 #C0C000"},
    {"Earthquake": "#FF8020 #C06000 #804000", "Rock Slide": "#FF8020 #A05000 #603000",
     "Quake": "#FF8020 #E09040 #804000", "Stone Crush": "#FF8020 #FFB080 #503000"},
    {"Ice Needle": "#80FFFF #C0FFFF #0080C0", "Frost": "#80FFFF #FFFFFF #005080",
     "Ice Wall": "#80FFFF #E0FFFF #0080A0", "Blizzard": "#80FFFF #A0E0FF #004080"},
    {"Water Fall": "#0080FF #80C0FF #004080", "Aqua": "#0080FF #40C0FF #003060",
     "Heal": "#0080FF #C0E0FF #0060C0", "Purify": "#0080FF #FFFFFF #004080"},
    {"Holy Light": "#FFFFFF #FFFFC0 #FFD700", "Resurrect": "#FFFFFF #FFFAC0 #FFD700",
     "Blessing": "#FFFFFF #FFF8DC #C0C0FF", "Divine": "#FFFFFF #FFFFE0 #FFD700"},
    {"Dark Wave": "#4000FF #8020FF #200080", "Curse": "#4000FF #6020C0 #100040",
     "Drain": "#4000FF #A080FF #200060", "Nightmare": "#4000FF #5020C0 #080020"},
)
_SEED_SPELLS = {name: spec for group in _SPELL_GROUPS for name, spec in group.items()}

_LOCATIONS = _palette_themes({
    "Meta": "#FF4000 #FF8020 #C02000 #802000 #FFD080",
    "Ozma": "#4000FF #8020FF #200080 #A080FF #100040",
    "Terra": "#40FF00 #80FF80 #008000 #C0FFC0 #20A020",
    "Voz Forest": "#40FF00 #208000 #C0FF80 #006000 #E0FFC0",
    "Noaru Valley": "#0080FF #40C0FF #004080 #C0E0FF #003060",
    "Drake Castle": "#808080 #C0C0C0 #404040 #E0E0E0 #202020",
    "Byron Temple": "#FF8020 #C06000 #804000 #FFB060 #402000",
    "Biron Temple": "#FF8020 #FFC080 #804000 #FFE0C0 #603000",
    "Sol Tower": "#FFFF00 #FFFFC0 #C0C000 #FFFAE0 #808000",
    "Ratayu": "#FF4000 #FFA040 #A02000 #FFD0B0 #501000",
    "Rim Elm": "#40FF00 #C0FF80 #208000 #E0FFC0 #006000",
    "Karisto": "#80FFFF #C0FFFF #0080C0 #E0FFFF #005080",
    "Uru Mais": "#FF8020 #E0A060 #804000 #FFD0A0 #503000",
    "Zeto": "#4000FF #7020FF #200080 #B090FF #080020",
    "Cort": "#808080 #A0A0A0 #404040 #C0C0C0 #202020",
    "Jette": "#0080FF #80C0FF #004080 #C0E0FF #003060",
    "Octam": "#FF8020 #C06000 #804000 #FFB060 #402000",
    "Balg": "#40FF00 #A0FF80 #208000 #D0FFB0 #105000",
    "Conkram": "#FF4000 #FF6000 #802000 #FFC0A0 #601000",
    "Nivora": "#80FFFF #FFFFFF #005080 #E0FFFF #004080",
})

# Section name -> {theme name: palette}, in menu order.
THEME_SECTIONS = {
    "Classic": _CLASSIC,
    "Editor styles": _EDITOR,
    "Ra-Seru": _RA_SERU,
    "Seru": _SERU,
    "Seru magic": _palette_themes(_SEED_SPELLS),
    "Locations": _LOCATIONS,
}
SECTION_BREAKS = {"Seru magic": {next(iter(g)) for g in _SPELL_GROUPS[1:]}}

# Every selectable palette (these also colour the graphical menu; Default
# keeps the retail art).
CLASSIC_THEMES = {name: values for section in THEME_SECTIONS.values()
                  for name, values in section.items()}
LEGAIA_THEME = "Legaia"
THEMES = dict(CLASSIC_THEMES)
THEMES[LEGAIA_THEME] = _LEGAIA

CLASSIC_THEME = "Default"      # the classic palette used while the menu UI is off
MENU_UI = False                # draw the game's menu UI (needs the skin assets)
CURRENT_THEME = "Default"      # the palette that is live: LEGAIA_THEME or classic


def current_values():
    """The live palette as a complete {TH_*: colour} dict."""
    return {key: globals()[key] for key in _THEME_KEYS}


def _complete(values):
    """Return a complete palette without exposing mutable theme definitions."""
    result = dict(_DEFAULT)
    result.update(values or {})
    return result


def _activate(name):
    global CURRENT_THEME
    values = _complete(THEMES[name])
    if MENU_UI and CLASSIC_THEME != "Default":
        values = _complete(CLASSIC_THEMES[CLASSIC_THEME])
    # The original Default palette is intentionally preserved byte-for-byte.
    # Other palettes get separated border, scrollbar and button colours.
    if CLASSIC_THEME != "Default":
        values = _separate_controls(values)
    # the plate sprite's face is darker than the button colour itself
    face = darken(values["TH_BTN_BG"], 0.25) if MENU_UI else values["TH_BTN_BG"]
    if not (MENU_UI and CLASSIC_THEME == "Default"):
        values["TH_BTN_FG"] = max(("#ffffff", "#000000"),
                                  key=lambda c: contrast(c, face))
    globals().update({key: values[key] for key in _THEME_KEYS})
    CURRENT_THEME = name
    apply_preview_scheme(values)
    refresh_tag_styles(values)


def set_theme(name):
    """Choose a palette for widgets and graphical menu chrome. Default uses
    the original game colours while the menu UI is enabled."""
    global CLASSIC_THEME
    CLASSIC_THEME = name if name in CLASSIC_THEMES else "Default"
    _activate(LEGAIA_THEME if MENU_UI else CLASSIC_THEME)
    return CLASSIC_THEME


def set_menu_ui(on):
    """Turn the game-menu UI on or off and return whether it is on.  Off
    restores the classic palette that was chosen last."""
    global MENU_UI
    MENU_UI = bool(on)
    _activate(LEGAIA_THEME if MENU_UI else CLASSIC_THEME)
    return MENU_UI


def preview_scheme_for(values):
    """Derive readable real-font preview colours from a UI palette."""
    bg = norm_color(values.get("BG_EDIT"), "#10183a")
    fg = readable_on(values.get("FG_MAIN") or "#ffffff", bg)
    dark = rel_lum(bg) < 0.4
    inks = {
        number: hex_to_rgb(readable_on(rgb_to_hex(rgb), bg, 3.0))
        for number, rgb in _palette.preview_inks().items()
    }
    inks[7] = hex_to_rgb(readable_on(mix(fg, bg, 0.12), bg, 4.5))
    inks[8] = hex_to_rgb(fg)
    accent = values.get("TH_ACCENT") or fg
    return {
        "bg": hex_to_rgb(bg), "rim": hex_to_rgb(mix(bg, fg, 0.55)),
        # the retail window's shape in the theme's colours: a gradient of
        # the theme's preview background and the gold frame's light/dark
        # re-mapped onto the theme (render.window)
        "fill_top": hex_to_rgb(darken(bg, 0.35) if dark else mix(bg, fg, 0.06)),
        "fill_bot": hex_to_rgb(mix(bg, accent, 0.28)),
        "scene": hex_to_rgb(darken(bg, 0.55) if dark else mix(bg, fg, 0.25)),
        "frame": (hex_to_rgb(darken(mix(bg, fg, 0.35), 0.55)),
                  hex_to_rgb(mix(accent, fg, 0.55))),
        "past": hex_to_rgb(mix(bg, values.get("TH_BAD") or "#c03030", 0.22)),
        "limit": hex_to_rgb(readable_on(values.get("TH_BAD") or "#ff6060", bg, 2.5)),
        "esc": hex_to_rgb(mix(bg, values.get("TH_ACCENT") or fg, 0.6)),
        "shadow": hex_to_rgb(darken(bg, 0.6) if dark else mix(bg, fg, 0.22)),
        "white": hex_to_rgb(fg), "inks": inks, "grid_ink": hex_to_rgb(fg),
        "grid_bg": hex_to_rgb(bg),
    }


# The theme whose previews keep the game's own look (dark-blue gradient box,
# gold frame, retail inks); the other palettes re-colour the previews.
RETAIL_PREVIEW_THEMES = ("Default", LEGAIA_THEME)


def apply_preview_scheme(values=None):
    """Push themed or retail preview colours into the shared palette."""
    values = current_values() if values is None else values
    if _palette.FOLLOW_THEME and (CURRENT_THEME not in RETAIL_PREVIEW_THEMES
                                 or MENU_UI and CLASSIC_THEME != "Default"):
        _palette.apply_scheme(preview_scheme_for(values))
    else:
        fg = hex_to_rgb(norm_color(values.get("FG_MAIN"), "#ffffff"))
        _palette.apply_scheme(_palette.retail_scheme(fg))


# Text-tag looks for the editors.  The colours are the light-theme originals;
# refresh_tag_styles() re-derives them for the live editor background so they
# stay readable on the dark palettes too.
_TAG_BASE = {
    "nonascii": {"foreground": "#d40000", "underline": True},
    "fold": {"foreground": "#7a5cd6", "underline": True},
    "newline": {"foreground": "#b06000", "font": FONT_MONO_B},
    "byte": {"foreground": "#0a7a0a", "font": FONT_MONO_B},
    "esc2": {"foreground": "#8b4513", "font": FONT_MONO_B},
    "sub": {"foreground": "#c9a000", "font": FONT_MONO_B},
    "ctl": {"foreground": "#a000a0", "font": FONT_MONO_B},
    "over": {"background": "#fff4bf"},
}
TAG_STYLES = {k: dict(v) for k, v in _TAG_BASE.items()}


def refresh_tag_styles(values):
    """Rewrite TAG_STYLES in place (importers hold the dict) for the editors'
    background: foregrounds are pushed to 4.5:1 contrast, the overdraw wash is
    tinted from the palette's warning colour."""
    bg = norm_color(values.get("TH_FIELD_BG"), "#ffffff")
    dark = rel_lum(bg) < 0.4
    for name, base in _TAG_BASE.items():
        style = dict(base)
        if "foreground" in style:
            style["foreground"] = readable_on(style["foreground"], bg, 4.5)
        if name == "over" and dark:
            style["background"] = mix(bg, values.get("TH_WARN") or "#ffd35c", 0.3)
        TAG_STYLES[name].clear()
        TAG_STYLES[name].update(style)


_activate(CURRENT_THEME)
