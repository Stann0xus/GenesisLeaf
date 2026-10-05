"""GenesisLeaf - Legend of Legaia language pack suite.

Package layout (see docs/ARCHITECTURE.md for the full map):

    core/     pure logic, no Tk: encoding, pack I/O, history, config, tables
    render/   pure rasterisers: glyph atlas, measurement, RGBA rendering
    assets/   embedded artwork blob (regenerate with tools/build_asset_blob.py)
    ui/       Tk front-end: theme, fonts, windows, and the App feature mixins
    main.py   entry point (also `python -m genesisleaf`)
"""

from genesisleaf.version import APP_NAME, VERSION

__version__ = VERSION
__all__ = ["APP_NAME", "VERSION", "__version__"]
