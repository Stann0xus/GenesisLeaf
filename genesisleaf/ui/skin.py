"""The game's pause-menu UI as a ttk theme.

Legend of Legaia's menus are navy windows in a gold-bronze 9-slice frame, with
blue command plates, carved brown tab plaques and a pointing-hand cursor (see
legend-of-legaia-re docs/subsystems/field-menu.md).  Those pieces are already
embedded - ``assets/window_skin.py`` (the frame) and ``assets/menu_skin.py``
(the rest; built from ``assets/menu_*.png``) - and this module turns them into a
second ttk theme, ``legaia``, that sits next to the stock ``clam`` one:

    * ``legaia`` inherits ``clam``, so anything it does not restyle keeps
      working; the classic UI is simply ``theme_use("clam")``;
    * every image element is created once, here, so switching is just
      ``theme_use`` plus the palette (``ui.theme.set_menu_ui``).

Text is left alone (fonts and colours come from the palette), only the chrome
changes: frames, plates, plaques, fields, arrows, scrollbars.  Without Pillow
or the sprite modules :func:`install` returns False and the classic UI stays.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import base64
import importlib
import tkinter as tk

from genesisleaf.compat import _PILImage, _PILImageTk
from genesisleaf.core.colors import darken, hex_to_rgb, mix

THEME = "legaia"        # the ttk theme this module builds
CLASSIC = "clam"        # the stock theme the classic UI runs on

_state = {"installed": None, "images": [], "sources": [], "tk": None, "palette": "uninitialized"}


def available():
    """True when the skin can be drawn (Pillow plus the extracted sprites)."""
    if _PILImage is None or _PILImageTk is None:
        return False
    try:
        for name in ("menu_skin", "window_skin"):
            importlib.import_module("genesisleaf.assets." + name)
    except Exception:                       # noqa: BLE001 - optional asset
        return False
    return True


# -- sprite access -----------------------------------------------------------
def _rgba(width, height, data):
    raw = base64.b64decode("".join(data) if not isinstance(data, str) else data)
    return _PILImage.frombytes("RGBA", (width, height), raw)


def _sprite(name):
    from genesisleaf.assets import menu_skin
    w, h, data = menu_skin.SPRITES[name]
    return _rgba(w, h, data)


def _frame_tiles():
    """The eight frame tiles of the dialogue skin (4 corners, 4 edges)."""
    from genesisleaf.assets import window_skin as ws
    block = _rgba(ws.BLOCK_W, ws.BLOCK_H, ws.BLOCK_RGBA)
    names = ("tl", "tr", "bl", "br", "top", "bot", "left", "right")
    return {n: block.crop((u, v, u + w, v + h))
            for n, (u, v, w, h) in zip(names, ws.QUADS)}


# -- image building ----------------------------------------------------------
_FRAME = 4              # the frame art is 4px thick at 1x


def panel(w, h, fill, frame=None):
    """A `w` x `h` window: `fill` colour inside the retail 4px gold frame."""
    img = _PILImage.new("RGBA", (w, h), hex_to_rgb(fill) + (255,))
    t = frame or _frame_tiles()

    def put(tile, x, y, clip_w=None, clip_h=None):
        piece = tile.crop((0, 0, clip_w or tile.width, clip_h or tile.height))
        img.alpha_composite(piece, (x, y))

    x = _FRAME
    while x < w - _FRAME:                       # top / bottom edges, tiled
        run = min(t["top"].width, w - _FRAME - x)
        put(t["top"], x, 0, run)
        put(t["bot"], x, h - _FRAME, run)
        x += run
    y = _FRAME
    while y < h - _FRAME:                       # left / right edges, tiled
        run = min(t["left"].height, h - _FRAME - y)
        put(t["left"], 0, y, None, run)
        put(t["right"], w - _FRAME, y, None, run)
        y += run
    put(t["tl"], 0, 0)
    put(t["tr"], w - _FRAME, 0)
    put(t["bl"], 0, h - _FRAME)
    put(t["br"], w - _FRAME, h - _FRAME)
    return img


def three_slice(prefix):
    """The 32x20 plate / plaque: left cap, body, right cap."""
    img = _PILImage.new("RGBA", (32, 20))
    img.alpha_composite(_sprite(prefix + "_l"), (0, 0))
    img.alpha_composite(_sprite(prefix + "_body"), (8, 0))
    img.alpha_composite(_sprite(prefix + "_r"), (24, 0))
    return img


# ttk draws an image element's 9-slice by tiling the centre/edge slices across
# the widget, one Tk_RedrawImage per tile.  A 24px well leaves a 16px tile, so a
# full-size Treeview needed ~1,000 blits (about 160 ms) on *every* repaint, and
# each column heading another ~40.  The slices are repeated into a larger image
# here - identical pixels, same tile phase - so the same area takes a few blits.
# Callers pin the element's natural size with width/height (see `_natural`).
_TILE_SPAN = 512


def expand_slices(img, border, span=_TILE_SPAN):
    """`img` with its 9-slice centre rows/columns repeated out to ~`span` px."""
    w, h = img.size
    mw, mh = w - 2 * border, h - 2 * border
    if mw <= 0 or mh <= 0:
        return img
    kx, ky = max(1, span // mw), max(1, span // mh)
    wide = _PILImage.new("RGBA", (2 * border + mw * kx, h))
    wide.paste(img.crop((0, 0, border, h)), (0, 0))
    strip = img.crop((border, 0, w - border, h))
    for i in range(kx):
        wide.paste(strip, (border + i * mw, 0))
    wide.paste(img.crop((w - border, 0, w, h)), (border + mw * kx, 0))
    out = _PILImage.new("RGBA", (wide.width, 2 * border + mh * ky))
    out.paste(wide.crop((0, 0, wide.width, border)), (0, 0))
    strip = wide.crop((0, border, wide.width, h - border))
    for i in range(ky):
        out.paste(strip, (0, border + i * mh))
    out.paste(wide.crop((0, h - border, wide.width, h)), (0, border + mh * ky))
    return out


def shade(img, brightness=1.0, saturation=1.0):
    """`img` with its colour scaled; alpha is kept."""
    from PIL import ImageEnhance
    alpha = img.getchannel("A")
    rgb = img.convert("RGB")
    if saturation != 1.0:
        rgb = ImageEnhance.Color(rgb).enhance(saturation)
    if brightness != 1.0:
        rgb = ImageEnhance.Brightness(rgb).enhance(brightness)
    rgb = rgb.convert("RGBA")
    rgb.putalpha(alpha)
    return rgb


def _arrow(direction, size=16):
    """The solid pager triangle (retail sprite) pointing `direction`."""
    left = _sprite("pager_left")
    img = {"left": left, "right": _sprite("pager_right"),
           "up": left.rotate(-90), "down": left.rotate(90)}[direction]
    return img.resize((size, size), _PILImage.NEAREST) if size != 16 else img


def _chip(w, h, fill, frame):
    """A small bevelled button face (arrows, combobox drop)."""
    return panel(w, h, fill, frame)


def _octagon(size, outline, fill, hi, lo, dot=None):
    """A bevelled octagon (the sheet's gem shape), optionally lit."""
    from PIL import ImageDraw
    img = _PILImage.new("RGBA", (size + _GUTTER, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = 3
    pts = [(c, 0), (size - 1 - c, 0), (size - 1, c), (size - 1, size - 1 - c),
           (size - 1 - c, size - 1), (c, size - 1), (0, size - 1 - c), (0, c)]
    d.polygon(pts, fill=outline)
    inner = [(x + (1 if x < size / 2 else -1), y + (1 if y < size / 2 else -1))
             for x, y in pts]
    d.polygon(inner, fill=hi)
    inner2 = [(x + (1 if x < size / 2 else -1), y + (1 if y < size / 2 else -1))
              for x, y in inner]
    d.polygon(inner2, fill=lo)
    inner3 = [(x + (1 if x < size / 2 else -1), y + (1 if y < size / 2 else -1))
              for x, y in inner2]
    d.polygon(inner3, fill=fill)
    if dot:
        m = size // 2
        d.polygon([(m - 2, m), (m, m - 2), (m + 1, m - 2), (m + 3, m),
                   (m + 3, m + 1), (m + 1, m + 3), (m, m + 3), (m - 2, m + 1)],
                  fill=dot)
    return img


_GUTTER = 5             # transparent space between an indicator and its label


def _checkbox(size, fill, outline, hi, lo, tick=None):
    """A bevelled square; `tick` draws the gold check mark."""
    from PIL import ImageDraw
    img = _PILImage.new("RGBA", (size + _GUTTER, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, size - 1, size - 1), fill=outline)
    d.rectangle((1, 1, size - 2, size - 2), fill=hi)
    d.rectangle((2, 2, size - 2, size - 2), fill=lo)
    d.rectangle((2, 2, size - 3, size - 3), fill=fill)
    if tick:
        pts = [(3, size // 2), (size // 2 - 1, size - 5), (size - 4, 3)]
        for dx in (0, 1):
            d.line([(x + dx, y) for x, y in pts], fill=tick, width=2)
    return img


# -- the theme ---------------------------------------------------------------
def _photo(root, img, role="window"):
    """A PhotoImage of `img`; `role` picks which theme colours tint it."""
    from genesisleaf.ui import theme
    source = img.copy()
    if theme.MENU_UI and theme.CLASSIC_THEME != "Default":
        img = tint_image(source, theme.current_values(), role)
    photo = _PILImageTk.PhotoImage(img, master=root)
    _state["images"].append(photo)          # Tk drops images nobody holds
    _state["sources"].append((source, role))
    return photo


def _ramp(base, spread=0.45):
    return darken(base, spread), base, mix(base, "#ffffff", spread)


# (black, mid, white) of the tint per sprite role: frames take the border
# colour, buttons the button colour, headings/tabs the heading colour,
# scrollbar thumbs the scrollbar colour - so no two parts share one tint.
_ROLES = {
    "window": lambda v: (v["TH_FRAME_BG"], v["TH_BORDER"], mix(v["TH_BORDER"], "#ffffff", 0.5)),
    "field": lambda v: (v["TH_FIELD_BG"], v["TH_BORDER"], mix(v["TH_BORDER"], "#ffffff", 0.5)),
    "tree": lambda v: (v["TH_TREE_BG"], v["TH_BORDER"], mix(v["TH_BORDER"], "#ffffff", 0.5)),
    "plate": lambda v: _ramp(v["TH_BTN_BG"]),
    "head": lambda v: _ramp(v["TH_HEAD_BG"], 0.3),
    "scroll": lambda v: _ramp(v["TH_SCROLL"]),
    "accent": lambda v: _ramp(v["TH_ACCENT"], 0.5),
    "check": lambda v: (v["TH_FIELD_BG"], v["TH_BORDER"], mix(v["TH_ACCENT"], "#ffffff", 0.3)),
}


def tint_image(img, values, role="window"):
    """Colour the sprite's luminance ramp, keeping its pixel art and alpha."""
    from PIL import ImageOps
    black, mid, white = _ROLES[role](values)
    tinted = ImageOps.colorize(ImageOps.grayscale(img), black, white,
                               mid=mid).convert("RGBA")
    tinted.putalpha(img.getchannel("A"))
    return tinted


def install(root, style):
    """Build the `legaia` ttk theme once; True when the skin is usable.

    The active theme is left as it was found."""
    if _state["tk"] is not root.tk:
        _state.update(installed=None, images=[], sources=[], tk=root.tk, palette="uninitialized")
    if _state["installed"] is not None:
        return _state["installed"]
    if not available():
        _state["installed"] = False
        return False
    previous = style.theme_use()
    try:
        _build(root, style)
        _state["installed"] = True
    except Exception:                       # noqa: BLE001 - never block start-up
        _state["installed"] = False
    finally:
        style.theme_use(previous)
    return _state["installed"]


def use(style, skinned):
    """Switch the ttk theme; `skinned` False is the classic UI."""
    target = THEME if skinned and _state["installed"] else CLASSIC
    try:
        style.theme_use(target)
        if target == THEME:
            from genesisleaf.ui import theme
            values = theme.current_values() if theme.CLASSIC_THEME != "Default" else None
            signature = tuple(sorted(values.items())) if values else None
            if signature != _state["palette"]:
                for photo, (source, role) in zip(_state["images"], _state["sources"]):
                    photo.paste(tint_image(source, values, role) if values else source)
                _state["palette"] = signature
    except tk.TclError:
        return False
    return target == THEME


def _build(root, style):
    from genesisleaf.ui.theme import THEMES, LEGAIA_THEME
    pal = THEMES[LEGAIA_THEME]
    frame_bg, field_bg = pal["TH_FRAME_BG"], pal["TH_FIELD_BG"]
    chrome_bg = pal["TH_CHROME_BG"]
    tiles = _frame_tiles()

    def ph(img, role="window"):
        return _photo(root, img, role)

    style.theme_create(THEME, parent=CLASSIC)
    style.theme_use(THEME)

    # frames ---------------------------------------------------------------
    def big(img, border, role="window"):
        return ph(expand_slices(img, border), role)

    window = big(panel(24, 24, frame_bg, tiles), 4)
    well = big(panel(24, 24, field_bg, tiles), 4, "field")
    well_focus = big(shade(panel(24, 24, field_bg, tiles), 1.18), 4, "field")
    well_off = big(shade(panel(24, 24, mix(field_bg, frame_bg, 0.5), tiles),
                         0.8, 0.6), 4, "field")
    tree_well = big(panel(24, 24, field_bg, tiles), 4, "tree")
    style.element_create("Legaia.panel", "image", window,
                         border=(4, 4, 4, 4), padding=(4, 4, 4, 4),
                         sticky="nswe", width=24, height=24)
    style.element_create("Legaia.field", "image", well,
                         ("disabled", well_off), ("focus", well_focus),
                         border=(4, 4, 4, 4), padding=(4, 3, 4, 3),
                         sticky="nswe", width=24, height=24)
    style.element_create("Legaia.tree", "image", tree_well,
                         border=(4, 4, 4, 4), padding=(3, 3, 3, 3),
                         sticky="nswe", width=24, height=24)

    # plates (buttons) and plaques (tabs, headings, frame titles) --------------
    blue = three_slice("plate")
    gold = three_slice("tab")
    plate = {
        "n": big(blue, 8, "plate"), "hot": big(shade(blue, 1.3), 8, "plate"),
        "down": big(shade(gold, 1.25), 8, "plate"),
        "off": big(shade(blue, 0.7, 0.35), 8, "plate"),
    }
    head = {
        "n": big(blue, 8, "head"), "hot": big(shade(blue, 1.3), 8, "head"),
        "down": big(shade(gold, 1.25), 8, "head"),
    }
    style.element_create(
        "Legaia.plate", "image", plate["n"],
        ("disabled", plate["off"]), ("pressed", plate["down"]),
        ("active", plate["hot"]), border=(8, 8, 8, 8), padding=(0, 0, 0, 0),
        sticky="nswe", width=32, height=20)
    plaque = {"n": big(gold, 8, "head"), "hot": big(shade(gold, 1.3), 8, "head"),
              "sel": big(shade(gold, 1.45, 1.1), 8, "head"),
              "off": big(shade(blue, 0.65, 0.5), 8, "head")}
    style.element_create(
        "Legaia.plaque", "image", plaque["n"], border=(8, 8, 8, 8),
        sticky="nswe", width=32, height=20)
    style.element_create(
        "Legaia.tab", "image", plaque["off"],
        ("selected", plaque["sel"]), ("active", plaque["hot"]),
        border=(8, 8, 8, 8), sticky="nswe", width=32, height=20)
    style.element_create(          # the menu bar's tab plaques
        "Legaia.menutab", "image", plaque["n"],
        ("pressed", plaque["sel"]), ("active", plaque["hot"]),
        border=(8, 8, 8, 8), sticky="nswe", width=32, height=20)
    style.element_create(
        "Legaia.heading", "image", head["n"],
        ("pressed", head["down"]), ("active", head["hot"]),
        border=(8, 8, 8, 8), padding=(0, 0, 0, 0), sticky="nswe",
        width=32, height=20)

    # combobox drop and spinbox arrows ---------------------------------------
    drop = _chip(18, 22, chrome_bg, tiles)
    drop_arrow = _arrow("down", 12)
    face = drop.copy()
    face.alpha_composite(drop_arrow, (3, 5))
    style.element_create(
        "Legaia.drop", "image", ph(face, "plate"),
        ("pressed", ph(shade(face, 0.75), "plate")),
        ("active", ph(shade(face, 1.3), "plate")),
        border=(4, 4, 4, 4), sticky="ns")
    for d, y in (("up", "Legaia.spin_up"), ("down", "Legaia.spin_down")):
        small = _PILImage.new("RGBA", (14, 10), (0, 0, 0, 0))
        small.alpha_composite(_arrow(d, 10), (2, 0))
        style.element_create(y, "image", ph(small, "accent"),
                             ("active", ph(shade(small, 1.3), "accent")), sticky="")

    # scrollbars -------------------------------------------------------------
    thumb = panel(16, 16, "#846342", tiles)
    style.element_create("Legaia.thumb", "image", ph(thumb, "scroll"),
                         ("active", ph(shade(thumb, 1.25), "scroll")),
                         border=(4, 4, 4, 4), sticky="nswe")

    # check / radio indicators ----------------------------------------------
    outline, tan, bronze = "#422908", "#cea584", "#846342"
    gold_hi = "#f2cb6b"
    box = ph(_checkbox(14, field_bg, outline, tan, bronze), "check")
    box_on = ph(_checkbox(14, field_bg, outline, tan, bronze, tick=gold_hi), "check")
    box_hot = ph(_checkbox(14, "#16227a", outline, tan, bronze), "check")
    box_hot_on = ph(_checkbox(14, "#16227a", outline, tan, bronze, tick=gold_hi), "check")
    box_off = ph(shade(_checkbox(14, field_bg, outline, tan, bronze), 0.6, 0.5), "check")
    box_off_on = ph(shade(_checkbox(14, field_bg, outline, tan, bronze,
                                    tick=gold_hi), 0.6, 0.5), "check")
    style.element_create(
        "Legaia.check", "image", box,
        ("disabled", "selected", box_off_on), ("disabled", box_off),
        ("active", "selected", box_hot_on), ("active", box_hot),
        ("selected", box_on), sticky="")
    gem = ph(_octagon(14, outline, field_bg, tan, bronze), "check")
    gem_on = ph(_octagon(14, outline, field_bg, tan, bronze, dot=gold_hi), "check")
    gem_hot = ph(_octagon(14, outline, "#16227a", tan, bronze), "check")
    gem_hot_on = ph(_octagon(14, outline, "#16227a", tan, bronze, dot=gold_hi), "check")
    style.element_create(
        "Legaia.radio", "image", gem,
        ("active", "selected", gem_hot_on), ("active", gem_hot),
        ("selected", gem_on), sticky="")

    # layouts ----------------------------------------------------------------
    L = style.layout
    L("Window.TFrame", [("Legaia.panel", {"sticky": "nswe"})])
    L("TLabelframe", [("Legaia.panel", {"sticky": "nswe"})])
    L("TLabelframe.Label", [("Legaia.plaque", {"sticky": "nswe", "children": [
        ("Label.text", {"sticky": "nswe"})]})])
    L("TButton", [("Legaia.plate", {"sticky": "nswe", "children": [
        ("Button.focus", {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [
                ("Button.label", {"sticky": "nswe"})]})]})]})])
    L("Menubar.TButton", [("Legaia.menutab", {"sticky": "nswe", "children": [
        ("Button.padding", {"sticky": "nswe", "children": [
            ("Button.label", {"sticky": "nswe"})]})]})])
    L("TMenubutton", [("Legaia.plate", {"sticky": "nswe", "children": [
        ("Menubutton.padding", {"sticky": "nswe", "children": [
            ("Menubutton.label", {"side": "left", "expand": 1})]})]})])
    L("TNotebook", [("Legaia.panel", {"sticky": "nswe"})])
    L("TNotebook.Tab", [("Legaia.tab", {"sticky": "nswe", "children": [
        ("Notebook.padding", {"side": "top", "sticky": "nswe", "children": [
            ("Notebook.focus", {"side": "top", "sticky": "nswe", "children": [
                ("Notebook.label", {"side": "top", "sticky": ""})]})]})]})])
    L("Treeview", [("Legaia.tree", {"sticky": "nswe", "children": [
        ("Treeview.padding", {"sticky": "nswe", "children": [
            ("Treeview.treearea", {"sticky": "nswe"})]})]})])
    L("Treeview.Heading", [("Legaia.heading", {"sticky": "nswe", "children": [
        ("Treeheading.padding", {"sticky": "nswe", "children": [
            ("Treeheading.image", {"side": "right", "sticky": ""}),
            ("Treeheading.text", {"sticky": "we"})]})]})])
    L("TEntry", [("Legaia.field", {"sticky": "nswe", "children": [
        ("Entry.padding", {"sticky": "nswe", "children": [
            ("Entry.textarea", {"sticky": "nswe"})]})]})])
    L("TCombobox", [("Legaia.field", {"sticky": "nswe", "children": [
        ("Legaia.drop", {"side": "right", "sticky": "ns"}),
        ("Combobox.padding", {"sticky": "nswe", "children": [
            ("Combobox.textarea", {"sticky": "nswe"})]})]})])
    L("TSpinbox", [("Legaia.field", {"sticky": "nswe", "children": [
        ("null", {"side": "right", "sticky": "", "children": [
            ("Legaia.spin_up", {"side": "top", "sticky": "e"}),
            ("Legaia.spin_down", {"side": "bottom", "sticky": "e"})]}),
        ("Spinbox.padding", {"sticky": "nswe", "children": [
            ("Spinbox.textarea", {"sticky": "nswe"})]})]})])
    L("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("Legaia.check", {"side": "left", "sticky": ""}),
        ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
            ("Checkbutton.label", {"sticky": "nswe"})]})]})])
    L("TRadiobutton", [("Radiobutton.padding", {"sticky": "nswe", "children": [
        ("Legaia.radio", {"side": "left", "sticky": ""}),
        ("Radiobutton.focus", {"side": "left", "sticky": "", "children": [
            ("Radiobutton.label", {"sticky": "nswe"})]})]})])
    L("Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Legaia.thumb", {"sticky": "nswe"})]})])
    L("Horizontal.TScrollbar", [
        ("Horizontal.Scrollbar.trough", {"sticky": "we", "children": [
            ("Legaia.thumb", {"sticky": "nswe"})]})])
    L("Horizontal.TProgressbar", [("Legaia.field", {"sticky": "nswe", "children": [
        ("Horizontal.Progressbar.pbar", {"side": "left", "sticky": "ns"})]})])

    # geometry the layouts rely on (colours are the palette's, see apply_theme)
    style.configure("TLabelframe", labelmargins=(10, 0, 10, 0),
                    labeloutside=False)
    style.configure("TLabelframe.Label", padding=(2, 1))
    style.configure("TNotebook", tabmargins=(4, 4, 4, 0))
    style.configure("TNotebook.Tab", padding=(6, 3))
    style.configure("TButton", padding=(6, 2), anchor="center")
    style.configure("Treeview.Heading", padding=(2, 2))
    style.configure("Vertical.TScrollbar", width=16)
    style.configure("Horizontal.TScrollbar", width=16)


# -- the hand cursor ----------------------------------------------------------
class HandCursor:
    """Marks the selected row of a Treeview with the retail pointing finger.

    Every row carries an image (the hand, or a blank of the same size) so the
    text never shifts.  A no-op - and no images at all - while the skin is not
    active, so the classic UI is untouched."""

    def __init__(self, tree, is_active):
        self.tree = tree
        self.is_active = is_active
        self._hand = self._blank = None
        self._selected = set()
        self._active = None
        tree.bind("<<TreeviewSelect>>", self.refresh, add="+")

    def _images(self):
        if self._hand is None:
            img = _sprite("hand")
            self._hand = _photo(self.tree, img, "accent")
            self._blank = _photo(self.tree, _PILImage.new("RGBA", img.size), "accent")
        return self._hand, self._blank

    def refresh(self, _evt=None):
        try:
            tree = self.tree
            active = self.is_active()
            hand, blank = self._images() if active else ("", "")
            sel = set(tree.selection())
            rows = (tree.get_children("") if _evt is None or active != self._active
                    else self._selected ^ sel)
            for iid in rows:
                if not tree.exists(iid):
                    continue
                want = (hand if iid in sel else blank) if active else ""
                if str(tree.item(iid, "image") or "") != str(want or ""):
                    tree.item(iid, image=want)
            self._selected = sel
            self._active = active
        except tk.TclError:
            pass
