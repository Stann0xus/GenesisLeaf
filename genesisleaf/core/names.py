"""Game-name reference tables used to resolve {c1..c7:..} substitutions.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import os
import re
import yaml

from genesisleaf.paths import APP_ROOT


# ---------------------------------------------------------------------------
# Game-name reference tables: {c1:..} party names, {c2/c4:..} items, {c3:..}
# spells/magic and {c5:..} arts.  The party and per-character art names are
# the retail dialogue C5 address space (cross-checked against the arts section
# of the original US pack); items/spells are read from that US.yaml when it is
# present so the preview always shows the REAL retail names, and the pack's own
# translated entries still win when a pack provides them.
# ---------------------------------------------------------------------------
NAME_FIELD = 8                # maximum in-game name field, in dialog glyphs

VAHN_ARTS = ("Vahn's Craze", "Burning Flare", "Fire Blow", "Tornado Flame",
             "Cyclone", "Hurricane", "PK Combo", "Spin Combo", "Pyro Pummel",
             "Cross-Kick", "Power Punch", "Slash Kick", "Somersault",
             "Charging Scorch", "Hyper Elbow")
NOA_ARTS = ("Noa's Ark", "Hurricane Kick", None, None, "Vulture Blade",
            "Frost Breath", "Tempest Break", "Rushing Gale", "Tough Love",
            "Swan Driver", "Bird Step", "Dolphin Attack", "Mirage Lancer",
            "Blizzard Bash", "Sonic Javelin", "Acrobatic Blitz", "Lizard Tail")
GALA_ARTS = ("Biron Rage", "Explosive Fist", "Lightning Storm",
             "Thunder Punch", "Bull Horns", "Electro Thrash", "Neo Raising",
             "Black Rain", "Side Kick", "Head-Splitter", "Back Punch",
             "Guillotine", "Ironhead", "Battering Ram")

_ARTS_BY_CHAR = (VAHN_ARTS, NOA_ARTS, GALA_ARTS)

_US_YAML_CANDIDATES = (
    os.path.join(APP_ROOT,
                 "experiments", "US.yaml"),
    os.path.join(APP_ROOT, "US.yaml"),
    os.path.join(os.getcwd(), "experiments", "US.yaml"),
    os.getenv("LEGAIA_US_YAML", ""),
)

_GAME_NAMES = None


def _game_name_db():
    """Reference database for substitution previews.  Items/spells are lifted
    from the bundled original US pack (authoritative retail spellings); the
    party + arts tables are fixed.  Best-effort: any missing US.yaml leaves the
    items/spells dictionaries empty."""
    global _GAME_NAMES
    if _GAME_NAMES is not None:
        return _GAME_NAMES
    db = {"items": {}, "spells": {}, "party": ("Vahn", "Noa", "Gala", "Terra"),
          "arts": _ARTS_BY_CHAR}
    for cand in _US_YAML_CANDIDATES:
        if not cand or not os.path.exists(cand):
            continue
        try:
            with open(cand, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except Exception:
            continue
        secs = data.get("sections") or {} if isinstance(data, dict) else {}
        for e in secs.get("items", ()) or ():
            m = re.match(r"item 0x([0-9a-fA-F]+)",
                         (e.get("context") or "").strip())
            if m and e.get("source"):
                db["items"][int(m.group(1), 16)] = e["source"]
        for e in secs.get("spells", ()) or ():
            m = re.match(r"spell 0x([0-9a-fA-F]+)",
                         (e.get("context") or "").strip())
            if m and e.get("source"):
                db["spells"][int(m.group(1), 16)] = e["source"]
        pn = [(e.get("source") or "").strip()
              for e in (secs.get("party_names", ()) or ())]
        if len(pn) >= 2:
            db["party"] = tuple(pn)
        break
    _GAME_NAMES = db
    return db


def game_name(op, arg):
    """Resolve a substitution escape (op 'c1'..'c7') to the name the retail
    game would splice into that slot, or None if there is no such entry."""
    db = _game_name_db()
    if op in ("c2", "c4"):
        return db["items"].get(arg)
    if op == "c3":
        return db["spells"].get(arg)
    if op == "c1":
        if 0 <= arg <= 3 and arg < len(db["party"]):
            return db["party"][arg]
        return None
    if op == "c5":
        char = (arg >> 6) & 0x3
        art = arg & 0x3F
        if char < len(db["arts"]) and art < len(db["arts"][char]):
            return db["arts"][char][art]
    return None
