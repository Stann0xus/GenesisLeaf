"""The retail dialog-window chrome for the real-font previews.

The game draws its reading box with FUN_8002C69C (legend-of-legaia-re
docs/formats/mes.md "Box render"):

  * **fill** - two semi-transparent gouraud quads, top RGB (0x18,0x18,0x28),
    bottom RGB (0x40,0x40,0xA0), which compose to 0.25*scene + 0.75*gradient,
    over the centre rect inflated by 4;
  * **frame** - the gold 9-slice of the system-UI sheet (4 corners + edges
    tiled at their own size, the last tile clipped), over the centre rect
    inflated by 8 - the skin's seat bias.

The frame texels come from genesisleaf/assets/window_skin.py, which
tools/build_art_blob.py builds from assets/window_frame.png; without it the box
falls back to a plain one-pixel rim.  The live colours (retail, or derived
from the theme) come from core.palette.SCHEME.

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import base64

_SKIN = None            # (quads, block_w, [(r, g, b, a)]) or False


def skin():
    """The embedded frame skin, or None when it was never extracted."""
    global _SKIN
    if _SKIN is None:
        try:
            from genesisleaf.assets import window_skin as ws
            px = base64.b64decode("".join(ws.BLOCK_RGBA))
            texels = [tuple(px[i:i + 4]) for i in range(0, len(px), 4)]
            _SKIN = (list(ws.QUADS), ws.BLOCK_W, texels)
        except Exception:                 # noqa: BLE001 - optional asset
            _SKIN = False
    return _SKIN or None


FRAME = 8        # frame footprint: centre rect inflated by this much
FILL_INSET = 4   # the gradient fill: centre rect inflated by 4


def _recolour(sch):
    """Texel -> colour mapping for the frame under the live scheme: the
    retail art as-is, or (themed previews) its brightness re-mapped onto
    the scheme's `frame` ramp (dark, light)."""
    ramp = sch.get("frame")
    if not ramp:
        return lambda c: c
    dark, light = ramp

    def f(c):
        t = (0.30 * c[0] + 0.59 * c[1] + 0.11 * c[2]) / 255.0
        t = min(1.0, max(0.0, (t - 0.08) / 0.62))
        return tuple(int(dark[k] + (light[k] - dark[k]) * t) for k in range(3))
    return f


def paint_window(rgba, w, h, sch, limit_x=0):
    """Paint the dialog window into the `w` x `h` RGBA buffer `rgba` (a
    bytearray): the gradient fill, the red "past the limit" region from
    `limit_x` on (0 = none), then the frame on top - glyphs go over all of it.

    The whole buffer is the frame footprint, so the text's centre rect
    starts FRAME px in, which is where the renderers already put the pen."""
    top = sch.get("fill_top", sch["bg"])
    bot = sch.get("fill_bot", sch["bg"])
    past = sch["past"]
    scene = sch.get("scene", (0, 0, 0))
    sk = skin()
    inset = FILL_INSET if sk else 1
    y0, y1 = inset, h - inset
    span = max(1, y1 - y0 - 1)
    for y in range(h):
        o = y * w * 4
        if y < y0 or y >= y1:
            row_c = scene
        else:
            t = (y - y0) / float(span)
            row_c = tuple(int(top[k] + (bot[k] - top[k]) * t) for k in range(3))
        line = bytearray()
        for x in range(w):
            if y < y0 or y >= y1 or x < inset or x >= w - inset:
                c = scene
            elif limit_x and x >= limit_x:
                c = past
            else:
                c = row_c
            line += bytes((c[0], c[1], c[2], 255))
        rgba[o:o + w * 4] = line
    if sk:
        _paint_frame(rgba, w, h, sk, _recolour(sch))
    else:
        rim = sch["rim"]
        for x in range(w):
            for y in (0, h - 1):
                _put(rgba, w, h, x, y, rim)
        for y in range(h):
            for x in (0, w - 1):
                _put(rgba, w, h, x, y, rim)


def _put(rgba, w, h, x, y, c, a=255):
    if not (0 <= x < w and 0 <= y < h):
        return
    o = (y * w + x) * 4
    if a >= 255:
        rgba[o], rgba[o + 1], rgba[o + 2] = c[0], c[1], c[2]
    else:                       # PSX blend mode 0: B/2 + F/2
        rgba[o] = (rgba[o] + c[0]) // 2
        rgba[o + 1] = (rgba[o + 1] + c[1]) // 2
        rgba[o + 2] = (rgba[o + 2] + c[2]) // 2
    rgba[o + 3] = 255


def _blit(rgba, w, h, sk, recol, quad, dx, dy, dw, dh):
    """Tile `quad` over (dx, dy, dw, dh), clipping the last tile."""
    _quads, bw, texels = sk
    qu, qv, qw, qh = quad
    for y in range(dh):
        sv = qv + (y % qh)
        for x in range(dw):
            t = texels[sv * bw + qu + (x % qw)]
            if t[3] == 0:
                continue
            _put(rgba, w, h, dx + x, dy + y, recol(t), t[3])


def _paint_frame(rgba, w, h, sk, recol):
    quads = sk[0]
    tl, tr, bl, br, top, bot, left, right = quads
    cw, ch = tl[2], tl[3]
    _blit(rgba, w, h, sk, recol, top, cw, 0, w - 2 * cw, top[3])
    _blit(rgba, w, h, sk, recol, bot, cw, h - bot[3], w - 2 * cw, bot[3])
    _blit(rgba, w, h, sk, recol, left, 0, ch, left[2], h - 2 * ch)
    _blit(rgba, w, h, sk, recol, right, w - right[2], ch, right[2], h - 2 * ch)
    _blit(rgba, w, h, sk, recol, tl, 0, 0, cw, ch)
    _blit(rgba, w, h, sk, recol, tr, w - tr[2], 0, tr[2], tr[3])
    _blit(rgba, w, h, sk, recol, bl, 0, h - bl[3], bl[2], bl[3])
    _blit(rgba, w, h, sk, recol, br, w - br[2], h - br[3], br[2], br[3])
