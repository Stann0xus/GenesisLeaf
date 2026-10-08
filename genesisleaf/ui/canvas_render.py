"""Tk canvas front-end for the real-font renderer (PIL composite + emoji fallback).

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import os
from time import perf_counter
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
import tkinter.font as tkfont

from genesisleaf.compat import _PILImage, _PILImageTk
from genesisleaf.diagnostics import current as current_diagnostics
from genesisleaf.core.colors import hex_to_rgb
from genesisleaf.core.fonttables import PREVIEW_MARGIN, ROW_PITCH
from genesisleaf.core.legend import ICON_EMOJI
from genesisleaf.render.icons import (
    _ICON_BAR_HIGH, _ICON_BAR_LOW, _draw_icons_on_image, _load_icon_images,
)
from genesisleaf.render.raster import render_font_rows
from genesisleaf.core import palette as _palette
from genesisleaf.ui import theme as _theme


def render_text_to_canvas(cv, rows, meta=None, expander=None, scale=2,
                          row_positions=None, accent_font=False,
                          emoji_icons=True, fallback_font=None,
                          rf_config=None, _raster=None):
    """Draw `rows` with render_font_rows into `cv` scaled by `scale` and
    centred.

    With `emoji_icons`, every {ce:..} icon escape that has NO PNG in assets/ is
    additionally drawn as a proportional emoji (from ICON_EMOJI) centred inside
    its advance box, on top of the rendered image.  Icons that DO have PNG
    artwork are composited from assets unconditionally.

    Stores the PhotoImage on `cv._pv_image` so it is not collected. Returns
    `(w, h, widest, limit_px)` on success, else None."""
    if _raster is None:
        try:
            _raster = render_font_rows(
                rows, meta or {}, expander=expander, row_positions=row_positions,
                accent_font=accent_font)
        except Exception:
            return None
    w, h, rgba, widest, limit_px, icons, fallbacks = _raster
    # the canvas around the image follows the theme too, so a theme switch
    # re-skins every preview the next time it is drawn
    try:
        cv.configure(background=_theme.BG_EDIT)
    except tk.TclError:
        pass
    s = max(1, int(scale))
    if _PILImage is not None:
        img = _PILImage.frombytes("RGBA", (w, h), rgba)
        img = img.resize((w * s, h * s), _PILImage.NEAREST)
        if icons:
            img = _draw_icons_on_image(img, icons, s)
            
        cw = max(cv.winfo_width(), 40)
        ch = max(cv.winfo_height(), 40)
            
        if rf_config:
            bg_color = rf_config.get("bg_color", "")
            bw = int(rf_config.get("border_width", 0))
            bc = rf_config.get("border_color", "#ffffff")
            bg_img_path = rf_config.get("bg_image", "")
            bg_alpha = float(rf_config.get("bg_alpha", 1.0))
            
            base_w = w * s + bw * 2
            base_h = h * s + bw * 2
            base = _PILImage.new("RGBA", (base_w, base_h), (0,0,0,0))
            
            if bg_img_path and os.path.isfile(bg_img_path):
                try:
                    bg_pic = _PILImage.open(bg_img_path).convert("RGBA")
                    bg_pic = bg_pic.resize((base_w, base_h))
                    if bg_alpha < 1.0:
                        bg_pic.putalpha(bg_pic.getchannel('A').point(lambda i: int(i * bg_alpha)))
                    base.alpha_composite(bg_pic)
                except Exception:
                    pass
                    
            if bg_color:
                try:
                    fill_rgb = hex_to_rgb(bg_color)
                    fill_col = fill_rgb + (int(255 * bg_alpha),)
                    fill_layer = _PILImage.new("RGBA", (base_w, base_h), fill_col)
                    base.alpha_composite(fill_layer)
                except Exception:
                    pass
                    
            if bw > 0:
                from PIL import ImageDraw
                draw = ImageDraw.Draw(base)
                try:
                    outline_col = hex_to_rgb(bc) + (255,)
                except Exception:
                    outline_col = (255,255,255,255)
                draw.rectangle([0, 0, base_w - 1, base_h - 1], outline=outline_col, width=bw)
                
            base.alpha_composite(img, (bw, bw))
            img = base
            w_disp = base_w
            h_disp = base_h
        else:
            w_disp = w * s
            h_disp = h * s
            
        cv._pv_image = _PILImageTk.PhotoImage(img)
        cv.delete("all")
        ox_im = max(4, (cw - w_disp) // 2)
        oy_im = max(4, (ch - h_disp) // 2)
        cv.create_image(ox_im, oy_im, anchor="nw", image=cv._pv_image)
    else:
        cv.delete("all")
        for y in range(h):
            for x in range(w):
                o = (y * w + x) * 4
                if rgba[o + 3] == 0:
                    continue
                cv.create_rectangle(
                    x * s, y * s, x * s + s, y * s + s,
                    fill="#%02x%02x%02x" % (rgba[o], rgba[o + 1], rgba[o + 2]),
                    outline="")
        ox_im = 4
        oy_im = 4
    if emoji_icons and icons:
        _draw_icon_emojis(cv, icons, ox_im, oy_im, s)
    if fallback_font is not None and fallbacks:
        # per-CHARACTER fallback: only the runs with no atlas glyph use the
        # system font; everything around them stays real-glyph preview
        for line, x, seg in fallbacks:
            if not seg:
                continue
            try:
                cv.create_text(
                    ox_im + (PREVIEW_MARGIN + x) * s,
                    oy_im + (PREVIEW_MARGIN + line * ROW_PITCH + 2) * s,
                    text=seg, anchor="nw", font=fallback_font,
                    fill=_theme.FG_MAIN)
            except tk.TclError:
                pass
    cv._pv_origin = (ox_im, oy_im)
    cv._pv_size = (w_disp, h_disp) if _PILImage is not None else (w * s, h * s)
    _set_preview_scrollregion(cv)
    return w, h, widest, limit_px


def _set_preview_scrollregion(cv):
    ox, oy = cv._pv_origin
    width, height = cv._pv_size
    cv.configure(scrollregion=(0, 0,
                               max(cv.winfo_width(), ox + width + 4),
                               max(cv.winfo_height(), oy + height + 4)))


def reposition_canvas_preview(cv):
    """Center an existing preview after a resize without rasterizing it again."""
    if not hasattr(cv, "_pv_size") or not hasattr(cv, "_pv_origin"):
        return False
    width, height = cv._pv_size
    old_x, old_y = cv._pv_origin
    new_x = max(4, (cv.winfo_width() - width) // 2)
    new_y = max(4, (cv.winfo_height() - height) // 2)
    if (new_x, new_y) != (old_x, old_y):
        cv.move("all", new_x - old_x, new_y - old_y)
        cv._pv_origin = (new_x, new_y)
    _set_preview_scrollregion(cv)
    return True


class CanvasRenderQueue:
    """Rasterize previews on workers; create Tk images only on Tk's thread."""

    def __init__(self, root):
        self.root = root
        self.pool = ThreadPoolExecutor(max_workers=2,
                                       thread_name_prefix="genesisleaf-preview")
        self.pending = {}
        self.poll_job = None

    # A one-to-few row preview rasterizes in ~1-2 ms.  Drawing it inline keeps
    # it in the same Tk repaint as the selection that asked for it; handing it
    # to a worker and polling made it land a frame or more later.
    INLINE_ROWS = 6

    def request(self, cv, rows, meta=None, expander=None, scale=2,
                row_positions=None, accent_font=False, fallback_font=None,
                rf_config=None, group=None):
        self.cancel(cv)
        rows = tuple(rows)
        meta = dict(meta or {})
        positions = tuple(row_positions) if row_positions is not None else None
        if len(rows) <= self.INLINE_ROWS:
            try:
                render_text_to_canvas(
                    cv, rows, meta, expander=expander, scale=scale,
                    row_positions=positions, accent_font=accent_font,
                    fallback_font=fallback_font, rf_config=dict(rf_config or {}))
            except tk.TclError:
                pass
            return
        future = self.pool.submit(render_font_rows, rows, meta,
                                  expander=expander, row_positions=positions,
                                  accent_font=accent_font)
        submitted_at = perf_counter()
        self.pending[cv] = (future, rows, meta, expander, scale, positions,
                            accent_font, fallback_font, dict(rf_config or {}),
                            group, False, submitted_at)
        monitor = current_diagnostics()
        if monitor is not None:
            monitor.event("RENDER_REQUEST", canvas=str(cv), rows=len(rows), scale=scale)
        if self.poll_job is None:
            self.poll_job = self.root.after(16, self._poll)

    def request_blank(self, cv, group=None):
        """Clear a canvas in the same frame as its render group."""
        self.cancel(cv)
        try:
            cv.delete("all")
        except tk.TclError:
            pass

    def cancel(self, cv):
        previous = self.pending.pop(cv, None)
        if previous is not None:
            previous[0].cancel()
            monitor = current_diagnostics()
            if monitor is not None:
                monitor.event("RENDER_CANCEL", canvas=str(cv),
                              queued_ms=round((perf_counter() - previous[-1]) * 1000, 3))

    def _poll(self):
        self.poll_job = None
        for cv, task in list(self.pending.items()):
            future = task[0]
            if not future.done():
                continue
            group = task[-3]
            if group is not None and any(
                    other[-3] is group and not other[0].done()
                    for other in self.pending.values()):
                continue
            self.pending.pop(cv, None)
            if future.cancelled():
                continue
            try:
                raster = future.result()
                if cv.winfo_exists():
                    (_, rows, meta, expander, scale, positions, accent, font,
                     config, _group, blank, submitted_at) = task
                    monitor = current_diagnostics()
                    if monitor is not None:
                        monitor.event("RENDER_READY", canvas=str(cv),
                                      queued_ms=round((perf_counter() - submitted_at) * 1000, 3))
                    if blank:
                        cv.delete("all")
                    else:
                        render_text_to_canvas(
                            cv, rows, meta, expander=expander, scale=scale,
                            row_positions=positions, accent_font=accent,
                            fallback_font=font, rf_config=config, _raster=raster)
            except Exception:
                pass
        if self.pending:
            self.poll_job = self.root.after(16, self._poll)

    def close(self):
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        for cv in list(self.pending):
            self.cancel(cv)
        self.pool.shutdown(wait=False, cancel_futures=True)


def _draw_icon_emojis(cv, icons, ox_im, oy_im, scale):
    """Fallback only: overlay a proportional emoji for icon escapes that have
    no PNG in assets/.  Fitted to the placeholder span (not the tall glyph
    cell) and centred on the anchor bars, so it sits exactly where the icon
    artwork would.  Painted with the row's {cf:..} palette tint."""
    have = _load_icon_images()
    span = _ICON_BAR_HIGH - _ICON_BAR_LOW
    for item in icons:
        x, py, width, idx = item[:4]
        pal = item[4] if len(item) > 4 else None
        if idx in have:
            continue
        em = ICON_EMOJI.get(idx)
        if not em:
            continue
        pixel = max(8.0, min(width, span) * scale * 0.62)
        pt = max(6, int(round(pixel * 72 / 96.0)))
        try:
            fnt = tkfont.Font(family="Segoe UI Emoji", size=pt)
        except tk.TclError:
            continue
        cx = ox_im + (PREVIEW_MARGIN + x + width / 2.0) * scale
        cy = oy_im + (py + _ICON_BAR_LOW + span / 2.0) * scale
        tint = _palette.ink(pal or 8)
        try:
            cv.create_text(cx, cy, text=em, anchor="center", font=fnt,
                           fill="#%02x%02x%02x" % tint)
        except tk.TclError:
            pass
