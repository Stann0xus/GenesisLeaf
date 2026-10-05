"""Optional third-party imports (Pillow) resolved once for the whole package.

Pillow is optional: without it the real-font preview falls back to drawing
pixels as canvas rectangles and the icon artwork is skipped.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

try:
    from PIL import Image as _PILImage
    from PIL import ImageTk as _PILImageTk
except Exception:
    _PILImage = None
    _PILImageTk = None
