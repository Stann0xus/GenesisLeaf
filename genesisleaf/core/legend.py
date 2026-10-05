"""Human-readable legends for markup tokens and {ce:..} icon escapes.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""


TOKEN_DOCS = {
    '|': '|  new-line: cursor drops one row, X resets to line start.',
    'c1': '{c1:..}  character-name substitution (active roster slot 0-3).',
    'c2': '{c2:..}  item-name substitution (item table name).',
    'c3': '{c3:..}  magic / spell-name substitution (spell table).',
    'c4': '{c4:..}  item-name substitution (same table as {c2:..}).',
    'c5': '{c5:..}  art-name substitution (art table).',
    'c7': '{c7:..}  actor-name substitution (fixed SCUS table: 00 Meta, 01 Terra, 02 Ozma).',
    'ce': '{ce:..}  escape: icons 00-07 (button/currency), numbers 0b-0e (HP/MP/Gold/Exp), actor name 10-13.',
    'cf': '{cf:..}  colour change: 0-9 only (dark grey, blue, red, purple, green, cyan, orange, greyed, white, red).  Above 9 is invalid - it breaks the game.',
    '7b': '{7b}/{7d}  literal { and } text, not a control.',
    'byte': '{xx}  bare byte (0x01 icon prefix, 0x7c newline, 0xce escape, 0xcf colour...).',
    'esc2': '{xx:yy}  raw two-byte escape.',
    'fold': 'purple  smart quote/dash/NBSP/ellipsis (importer folds it to 1 byte).',
    'nonascii': 'RED  character not in the retail font - never encodable.',
}

# {ce:..} legend (escape indices 0x00-0x23).  ICON_LEGEND: index -> one-line
# description.  ICON_EMOJI: index -> the emoji the Playground draws inside the
# escape's advance box (in proportion), None for NULLs / numeric escapes (0x0B
# - 0x0E draw no icon - they are the {cf}ting / coin / HP-MP-Gold-Exp splices).
ICON_LEGEND = {
    0x00: "X Button",
    0x01: "Circle Button",
    0x02: "Square Button",
    0x03: "Triangle Button",
    0x04: "R1 Button",
    0x05: "R2 Button",
    0x06: "L1 Button",
    0x07: "L2 Button",
    0x08: "G(old) Icon",
    0x09: "I(ndividual) Icon",
    0x0A: "A(ll) Icon",
    0x0B: "NULL",
    0x0C: "NULL",
    0x0D: "NULL",
    0x0E: "NULL",
    0x0F: "(Ra-Seru) Text",
    0x10: "Hand (Arms.) Icon",
    0x11: "Helmet (Head) Icon",
    0x12: "Armor (Body) Icon",
    0x13: "Boot (Legs) Icon",
    0x14: "Fire Icon",
    0x15: "Thunder Icon",
    0x16: "Wind Icon",
    0x17: "Water Icon",
    0x18: "Earth Icon",
    0x19: "Light Icon",
    0x1A: "Dark Icon",
    0x1B: "Monster (Juggernault) Icon",
    0x1C: "NULL (Broken Fire Icon)",
    0x1D: "Fire Icon 2 (Ult.)",
    0x1E: "Thunder Icon 2",
    0x1F: "Wind Icon 2",
    0x20: "Water Icon 2",
    0x21: "Earth Icon 2",
    0x22: "Light Icon 2",
    0x23: "Dark Icon 2",
}

ICON_EMOJI = {
    0x00: "\u2715",   # ✕
    0x01: "\u25CB",   # ○
    0x02: "\u25A1",   # □
    0x03: "\u25B3",   # △
    0x04: "\u25B6",   # ▶ R1
    0x05: "\u23ED",   # ⏭ R2
    0x06: "\u25C0",   # ◀ L1
    0x07: "\u23EE",   # ⏮ L2
    0x08: "\U0001F4B0",   # 💰
    0x09: "\U0001F464",   # 👤
    0x0A: "\U0001F465",   # 👥
    0x0B: None,
    0x0C: None,
    0x0D: None,
    0x0E: None,
    0x0F: "\U0001F4DC",   # 📜
    0x10: "\U0001F590",   # 🖐
    0x11: "\U0001FA96",   # 🪖
    0x12: "\U0001F9BA",   # 🦺
    0x13: "\U0001F462",   # 👢
    0x14: "\U0001F525",   # 🔥
    0x15: "\u26A1",       # ⚡
    0x16: "\U0001F4A8",   # 💨
    0x17: "\U0001F4A7",   # 💧
    0x18: "\U0001FAA8",   # 🪨
    0x19: "\u2728",       # ✨
    0x1A: "\U0001F311",   # 🌑
    0x1B: "\U0001F479",   # 👹
    0x1C: None,
    0x1D: "\U0001F525",   # 🔥
    0x1E: "\u26A1",       # ⚡
    0x1F: "\U0001F4A8",   # 💨
    0x20: "\U0001F4A7",   # 💧
    0x21: "\U0001FAA8",   # 🪨
    0x22: "\u2728",       # ✨
    0x23: "\U0001F311",   # 🌑
}
