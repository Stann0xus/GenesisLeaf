"""Icon artwork (embedded PNG blob) decoding and compositing into previews.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import base64 as _b64
import io

from genesisleaf.assets.icons_blob import ASSETS
from genesisleaf.compat import _PILImage
from genesisleaf.core.fonttables import PREVIEW_MARGIN
from genesisleaf.core import palette as _palette


# The real retail icon artwork, embedded as base64 PNGs in ASSETS.  When an
# icon exists it is composited into the preview at the escape's advance-box
# size; without one the mono-bars placeholder stays bare or the proportional
# emoji (ICON_EMOJI) is drawn instead.
_ICON_IMAGES = None
_ICON_BAR_LOW = 2             # the two placeholder bars sit at py+2 / py+12
_ICON_BAR_HIGH = 12


def _load_icon_images():
    """Decode ASSETS ("icon_XX.png" -> base64 PNG, XX = the HEX escape index)
    -> {index: PIL Image}, cached in `_ICON_IMAGES`."""
    global _ICON_IMAGES
    if _ICON_IMAGES is not None:
        return _ICON_IMAGES
    _ICON_IMAGES = {}
    if _PILImage is None:
        return _ICON_IMAGES
    for name, data in ASSETS.items():
        try:
            idx = int(name.split("_")[1].split(".")[0], 16)
            im = _PILImage.open(io.BytesIO(_b64.b64decode(data)))
            im.load()
            _ICON_IMAGES[idx] = im
        except Exception:
            pass
    return _ICON_IMAGES


def _draw_icons_on_image(img, icons, scale):
    """Composite the real icon PNGs into the (already scaled) preview image.
    Every icon keeps its OWN resolution (16x16, 12x12, 32x16 ... exactly as
    shipped) scaled by the view: it is centred inside its escape's advance
    box and centred vertically on the placeholder bars (py+2..py+12) - the
    artwork is never stretched to fill the slot.  When the {cf:..} palette has
    retinted the row, the icon RGB is tinted the same way (an informative
    approximation, not a real palette remap)."""
    imgs = _load_icon_images()
    if not imgs or _PILImage is None:
        return img
    mid = (_ICON_BAR_LOW + _ICON_BAR_HIGH) / 2.0
    for item in icons:
        x, py, width, idx = item[:4]
        pal = item[4] if len(item) > 4 else None
        src = imgs.get(idx)
        if src is None:
            continue
        try:
            icon = src.convert("RGBA")
        except Exception:
            continue
        tw = max(1, int(round(icon.width * scale)))
        th = max(1, int(round(icon.height * scale)))
        if tw != icon.width or th != icon.height:
            try:
                icon = icon.resize(
                    (tw, th), getattr(_PILImage, "LANCZOS") or
                    getattr(_PILImage, "NEAREST"))
            except Exception:
                continue
        try:
            tint = _palette.ink(pal or 8)
            if tint != _palette.SCHEME["white"]:
                r, g, b, a = icon.split()
                tr, tg, tb = tint
                r = r.point(lambda v, t=tr: v * t // 255)
                g = g.point(lambda v, t=tg: v * t // 255)
                b = b.point(lambda v, t=tb: v * t // 255)
                icon = _PILImage.merge("RGBA", (r, g, b, a))
        except Exception:
            pass
        left = int(round((PREVIEW_MARGIN + x + width / 2.0) * scale
                         - tw / 2.0))
        top = int(round((py + mid) * scale - th / 2.0))
        try:
            img.paste(icon, (left, top), icon)
        except Exception:
            continue
    return img
