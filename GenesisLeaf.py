"""GenesisLeaf 0x5b - Legend of Legaia language pack suite.

Guidelines: https://andrewaltimit.github.io/legend-of-legaia-re/tooling/translation.html

Usage:
    python GenesisLeaf.py [pack.yaml]

Requires: Python 3.8+, PyYAML, tkinter (standard on Windows); Pillow is
optional but strongly recommended (real-font preview, icon artwork).
The tool edits the pack in memory and only writes the .yaml when you Save
(Ctrl+S). A previous copy of the file is kept as <pack>.bak. Glossary and
per-entry notes live in sidecar files next to the pack and are NOT written
into the pack (a working pack must only ever carry the game script locally).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from genesisleaf.main import main  # noqa: E402

if __name__ == "__main__":
    main()
