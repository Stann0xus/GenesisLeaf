"""Keyboard helpers shared by the macro layer.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""


def _macro_key_ok(evt):
    """True when a function-key press should trigger a macro.

    Colour-wrap shares the F-keys through bare Shift (Shift+F1..F12),
    so the macro layer declines bare Shift to avoid conflict.
    Other modifier combinations (Control, Alt, Shift+Control, etc.) are allowed."""
    if evt is None:
        return True
    try:
        state = int(evt.state)
    except (AttributeError, TypeError, ValueError):
        return True
    # Allow if no modifiers, or if modifiers include Control/Alt (not bare Shift)
    shift = bool(state & 0x0001)
    control = bool(state & 0x0004)
    alt = bool(state & 0x0008)
    if shift and not (control or alt):
        return False  # bare Shift+F1..F12 reserved for color-wrap
    return True
