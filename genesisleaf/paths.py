"""Filesystem anchors.

APP_ROOT is the folder that holds the launcher (GenesisLeaf.py) - the same
place the single-file GenesisText kept its settings and patcher sidecars, so
existing GenesisText.json / legaia_patcher_config.json files keep working.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import os
import sys

PKG_DIR = os.path.dirname(os.path.abspath(__file__))

if getattr(sys, "frozen", False):          # PyInstaller & co.
    APP_ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_ROOT = os.path.dirname(PKG_DIR)
