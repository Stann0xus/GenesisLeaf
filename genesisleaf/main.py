"""Program entry point.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import tkinter as tk

from genesisleaf.ui.app.app import App
from genesisleaf.ui.fonts import (
    FONT_DEFAULT_FAMILY, FONT_MONO, FONT_UI_SM, init_fonts,
)


def main():
    root = tk.Tk()
    init_fonts(root, FONT_DEFAULT_FAMILY)
    # Default font for every widget that does not set one explicitly (labels,
    # buttons, tabs, treeview cells, dialogs) so the whole editor is monospace.
    root.option_add("*font", FONT_MONO)
    root.option_add("*TCombobox*Listbox.font", FONT_UI_SM)
    App(root)
    root.mainloop()
