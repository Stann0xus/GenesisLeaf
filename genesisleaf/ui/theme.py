"""Fixed application palettes and live preview colours.

GenesisLeaf intentionally ships two coherent palettes instead of a theme editor
or a collection of near-duplicate schemes.  Widgets read the live ``TH_*``
roles from this module; :func:`set_theme` updates those roles in one pass.
"""

from genesisleaf.core import palette as _palette
from genesisleaf.core.colors import (
    darken, hex_to_rgb, mix, norm_color, readable_on, rel_lum, rgb_to_hex,
)
from genesisleaf.core.palette import PALETTES
from genesisleaf.ui.fonts import FONT_MONO_B


_THEME_KEYS = (
    "TH_FRAME_BG", "TH_PANEL_BG", "TH_CHROME_BG", "TH_BORDER",
    "TH_FG", "TH_FG_MUTED", "TH_FG_FAINT", "TH_ACCENT",
    "TH_OK", "TH_WARN", "TH_BAD", "TH_OVERDRAW_SRC", "TH_OVERDRAW_TR",
    "TH_BAND_A", "TH_BAND_B", "TH_TREE_BG", "TH_HEAD_BG", "TH_HEAD_FG",
    "TH_SEL_BG", "TH_FIELD_BG", "TH_SEL_FG", "BG_EDIT", "FG_MAIN",
    "FG_DIM", "APP_BG",
)

# The primary palette is deliberately calm and high-contrast: cool surfaces,
# one blue action color, and consistent semantic status colors.
_DEFAULT = {
    "TH_FRAME_BG": "#eef2f7", "TH_PANEL_BG": "#f9fbfd", "TH_CHROME_BG": "#dce5ef",
    "TH_BORDER": "#b8c5d4", "TH_FG": "#17212b", "TH_FG_MUTED": "#536477",
    "TH_FG_FAINT": "#7e8d9d", "TH_ACCENT": "#1769aa", "TH_OK": "#146c3a",
    "TH_WARN": "#8a5800", "TH_BAD": "#b42318", "TH_OVERDRAW_SRC": "#a64b08",
    "TH_OVERDRAW_TR": "#8c5a00", "TH_BAND_A": "#ffffff", "TH_BAND_B": "#eaf0f6",
    "TH_TREE_BG": "#ffffff", "TH_HEAD_BG": "#d3deea", "TH_HEAD_FG": "#17212b",
    "TH_SEL_BG": "#b8d8f2", "TH_FIELD_BG": "#ffffff", "TH_SEL_FG": "#102a43",
    "BG_EDIT": "#101820", "FG_MAIN": "#f2f6fa", "FG_DIM": "#c5d0db", "APP_BG": "#263746",
}

# A dark alternative for dim rooms and users who prefer reduced glare.  It
# remains a complete palette, not a transformed copy, so contrast is explicit.
_DARK = {
    "TH_FRAME_BG": "#101923", "TH_PANEL_BG": "#172432", "TH_CHROME_BG": "#203244",
    "TH_BORDER": "#385064", "TH_FG": "#edf4fa", "TH_FG_MUTED": "#afc1d1",
    "TH_FG_FAINT": "#7890a3", "TH_ACCENT": "#65b5f0", "TH_OK": "#75d69b",
    "TH_WARN": "#f2c35e", "TH_BAD": "#ff8b83", "TH_OVERDRAW_SRC": "#ffad67",
    "TH_OVERDRAW_TR": "#f0c56d", "TH_BAND_A": "#14212d", "TH_BAND_B": "#1b2b3a",
    "TH_TREE_BG": "#14212d", "TH_HEAD_BG": "#2d465c", "TH_HEAD_FG": "#f5f9fc",
    "TH_SEL_BG": "#315b7a", "TH_FIELD_BG": "#1b2a38", "TH_SEL_FG": "#ffffff",
    "BG_EDIT": "#0b121a", "FG_MAIN": "#eaf3fa", "FG_DIM": "#a9bdcf", "APP_BG": "#0e1721",
}

# The game's own pause-menu look: navy marbled windows (the "filigree"), gold-
# bronze frames, tan highlights, warm-white text.  Every colour is sampled from
# the menu sprites (assets/menu_skin.py / window_skin.py): the interior runs
# #10187b..#3142b5, the frame #422908 / #846342 / #cea584.  The surfaces are
# the interior darkened the way the retail windows darken it (their gouraud
# gradient multiplies the tile by 0.5..1.06).
_LEGAIA = {
    "TH_FRAME_BG": "#0f1766", "TH_PANEL_BG": "#0b1250", "TH_CHROME_BG": "#0b1252",
    "TH_BORDER": "#846342", "TH_FG": "#f6f2e6", "TH_FG_MUTED": "#cfc7b0",
    "TH_FG_FAINT": "#9aa2d8", "TH_ACCENT": "#f2cb6b", "TH_OK": "#86e69c",
    "TH_WARN": "#ffd35c", "TH_BAD": "#ff8f86", "TH_OVERDRAW_SRC": "#ffb36e",
    "TH_OVERDRAW_TR": "#f2d46f", "TH_BAND_A": "#0c1458", "TH_BAND_B": "#131d78",
    "TH_TREE_BG": "#0c1458", "TH_HEAD_BG": "#3f397f", "TH_HEAD_FG": "#f6f2e6",
    "TH_SEL_BG": "#3a52d6", "TH_FIELD_BG": "#080d38", "TH_SEL_FG": "#ffffff",
    "BG_EDIT": "#070b2e", "FG_MAIN": "#f6f2e6", "FG_DIM": "#c4bfdc", "APP_BG": "#070b2e",
}

# The two classic palettes; they are the fallback UI (Options > Legaia menu UI).
CLASSIC_THEMES = {"Default": _DEFAULT, "Midnight": _DARK}
LEGAIA_THEME = "Legaia"
THEMES = dict(CLASSIC_THEMES)
THEMES[LEGAIA_THEME] = _LEGAIA

CLASSIC_THEME = "Default"      # the classic palette used while the menu UI is off
MENU_UI = False                # draw the game's menu UI (needs the skin assets)
CURRENT_THEME = "Default"      # the palette that is live: LEGAIA_THEME or classic


def current_values():
    """The live palette as a complete {TH_*: colour} dict."""
    return _complete(THEMES[CURRENT_THEME])


def _complete(values):
    """Return a complete palette without exposing mutable theme definitions."""
    result = dict(_DEFAULT)
    result.update(values or {})
    return result


def _activate(name):
    global CURRENT_THEME
    values = _complete(THEMES[name])
    globals().update({key: values[key] for key in _THEME_KEYS})
    CURRENT_THEME = name
    apply_preview_scheme(values)
    refresh_tag_styles(values)


def set_theme(name):
    """Choose the classic palette (``Default`` / ``Midnight``) and return its
    name.  It goes live at once unless the menu UI is on, which keeps its own
    palette until it is switched off."""
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
        for number, rgb in PALETTES.items()
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
    values = _complete(THEMES.get(CURRENT_THEME)) if values is None else values
    if _palette.FOLLOW_THEME and CURRENT_THEME not in RETAIL_PREVIEW_THEMES:
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
    "sub": {"foreground": "#1450c8", "font": FONT_MONO_B},
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
