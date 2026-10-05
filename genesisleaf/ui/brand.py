"""The window icon (a leaf and a pen) and the "Genesis Leaf" logotype.

Both are embedded PNGs (assets/brand_blob.py).  Tk reads PNG itself, so no
Pillow is needed; the pixel art is enlarged with `zoom` (nearest neighbour).

Part of GenesisLeaf - see docs/ARCHITECTURE.md.
"""

import tkinter as tk

from genesisleaf.assets.brand_blob import BRAND

_cache = {}


def _image(root, key, zoom=1):
    """A PhotoImage of the brand art `key`, enlarged `zoom` times."""
    token = (key, zoom)
    if token not in _cache:
        img = tk.PhotoImage(master=root, data="".join(BRAND[key]))
        _cache[token] = img.zoom(zoom) if zoom > 1 else img
    return _cache[token]


def logotype(root, zoom=2):
    """The "Genesis Leaf" wordmark (80x14 at zoom 1)."""
    return _image(root, "logotype", zoom)


def icon(root, zoom=1):
    """The leaf-and-pen icon (32x32 at zoom 1)."""
    return _image(root, "icon", zoom)


def apply_icon(root):
    """Use the leaf-and-pen icon on every window instead of Tk's feather."""
    try:
        big = icon(root)
        small = big.subsample(2)           # crisp 16px for the title bar
        root.iconphoto(True, big, small)
    except tk.TclError:
        pass
