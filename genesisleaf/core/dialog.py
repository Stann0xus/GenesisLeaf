"""Screen surfaces, text limits, section kinds and the retail dialog-box pager.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import re

from genesisleaf.core.fonttables import ROWS_PER_BOX


# Every pinned screen budget (docs/formats/dialog-font.md "Line width and
# wrapping", docs/subsystems/field-menu.md).  context -> (max_px, max_lines,
# glyph_pad).  max_lines None = no fixed row count.  No retail surface wraps.
TEXT_LIMITS = {
    "field_dialog_row": (244, 3, 1),
    "field_dialog_row_beside_page_hand": (228, 2, 1),
    "field_dialog_option": (228, 4, 1),
    "party_name": (56, 1, 0),
    "item_list_name": (104, 1, 0),
    "shop_buy_name": (104, 1, 0),
    "item_info_name": (124, 1, 0),
    "status_magic_name": (104, 1, 0),
    "status_moves_name": (114, 1, 0),
    "battle_message_line": (288, None, 0),
    "battle_intro_enemy_label": (308, 1, 0),
}


def limit_for(context):
    if context in TEXT_LIMITS:
        max_px, max_lines, glyph_pad = TEXT_LIMITS[context]
        return {"context": context, "max_px": max_px,
                "max_lines": max_lines, "glyph_pad": glyph_pad}
    return None


_HEXID_RE = re.compile(r"0x[0-9a-fA-F]+")


def _hex_group_label(ctx):
    """Shorn label for a context whose only distinguishing part is a hex id,
    e.g. 'item 0x3c' -> 'item 0x..'.  None when there is no hex token or the
    token is the whole string."""
    m = _HEXID_RE.search(ctx)
    if not m:
        return None
    head = ctx[:m.start()].rstrip(" ([:,-")
    return head + " 0x.." if head else None


# How each pack section is drawn in the finished game - the workbench shows
# this classification so a line's budget is compared to the right surface.
SECTION_KIND = {
    "scene_dialog": "dialogue",
    "inline_text": "dialogue",
    "ui_menu": "system / UI label",
    "system_text": "system string",
    "party_names": "name (C string)",
    "items": "name (C string)",
    "item_types": "name (C string)",
    "accessory_passives": "name (C string)",
    "spells": "name (C string)",
    "arts": "name (C string)",
    "place_names": "name (C string)",
    "monster_names": "battle name",
}


def default_limit_context(sec):
    """The pinned surface a section's lines are drawn on, when one applies."""
    if sec in ("scene_dialog", "inline_text"):
        return "field_dialog_row"
    if sec == "party_names":
        return "party_name"
    if sec in ("items", "item_types"):
        return "item_list_name"
    if sec == "spells":
        return "status_magic_name"
    if sec == "arts":
        return "status_moves_name"
    if sec == "monster_names":
        return "battle_intro_enemy_label"
    if sec == "accessory_passives":
        return "item_info_name"
    return None


def dialog_coord(key):
    """`(kind, prot, offset)` of a `man:` / `raw:` dialog key, else None."""
    m = re.match(r"^(man|raw):(\d+):0x([0-9a-fA-F]+)$", key)
    if not m:
        return None
    return (m.group(1), int(m.group(2)), int(m.group(3), 16))


def dialog_boxes(lines, first_box=0):
    """Port of translate_workbench.rs::dialog_boxes(): box/row numbers for a
    run of dialog lines, in the order given.

    The retail pager packs *consecutive* lines into one box: the byte after a
    line's `0x00` terminator being another `0x1F` lead means "same box, next
    row", up to ROWS_PER_BOX rows. A line is `0x1F <text> 0x00`, so the next
    line of the same box starts its text `len + 2` bytes after this one's.
    `lines` are `(key, English text length)`; box numbers count up from
    `first_box`. Returns `[(box, row), ...]`.
    """
    out = []
    bx = first_box
    prev = None
    for (key, length) in lines:
        coord = dialog_coord(key)
        prow = 0
        if prev is not None and coord is not None:
            (pk, pprot), pend, prow = prev
            k, p, off = coord
            if pk == k and pprot == p and off == pend and prow + 1 < ROWS_PER_BOX:
                prow += 1
                row = prow
            else:
                if out:
                    bx += 1
                row = 0
        else:
            if out:
                bx += 1
            row = 0
        out.append((bx, row))
        prev = None
        if coord is not None:
            prev = ((coord[0], coord[1]), coord[2] + length + 2, row)
    return out
