"""User settings (GenesisLeaf.json) and the Build-test-ROM patcher sidecar.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import json
import os

from genesisleaf.paths import APP_ROOT


# Build-test-ROM settings, edited inside the "Build test ROM" dialog and kept
# in a sidecar JSON next to this script.
PATCONF_PATH = os.path.join(
    APP_ROOT, "legaia_patcher_config.json")
def _first_existing(*paths):
    """The first path that exists, else the first one (a visible default)."""
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]


_SIBLINGS = os.path.dirname(APP_ROOT)      # the folder GenesisLeaf sits in

DEFAULTS_PATCONF = {
    # a legend-of-legaia-re checkout and a _STAGING disc folder next to
    # GenesisLeaf are found without any setup
    "patcher_exe": _first_existing(
        os.path.join(_SIBLINGS, "legend-of-legaia-re", "target", "release",
                     "legaia-patcher.exe"),
        r"A:\Workspace\Development\Indev\LegaiaTranslatorTool"
        r"\legend-of-legaia-re\target\release\legaia-patcher.exe"),
    "retail_disc": _first_existing(
        os.path.join(_SIBLINGS, "_STAGING", "LEGEND-OF-LEGAIA.BIN"),
        r"A:\Programming\Legend of Legaia\ROMS\Legend of Legaia (USA).bin"),
    "output_dir": os.path.join(
        APP_ROOT, "output"),
    "dry_run_first": True,
    "allow_relayout": False,
    "accents": "auto",       # --accents: auto | font | fold | strict
}

# -- user config -------------------------------------------------------------
# Theme, macros and search scope are choices the user makes, not document data,
# so they live in a small JSON file next to the program rather than in the pack.
# A missing or corrupt file is never fatal: defaults win and we rewrite on save.
CONFIG_NAME = "GenesisLeaf.json"
LEGACY_CONFIG_NAME = "GenesisText.json"   # pre-0x01a settings, read-only


def _config_path(name=CONFIG_NAME):
    """`GenesisLeaf.json` beside the program, or in the home directory if the
    install directory is not writable."""
    prog_dir = APP_ROOT
    here = os.path.join(prog_dir, name)
    if os.access(prog_dir, os.W_OK):
        return here
    return os.path.join(os.path.expanduser("~"), "." + name)


def _read_config_candidates():
    """The settings file, then (only while it does not exist yet) the legacy
    GenesisText.json so an upgrade keeps the user's theme, macros and
    real-font options.  The next save writes GenesisLeaf.json."""
    cur = _config_path()
    if os.path.exists(cur):
        return [cur]
    return [cur, _config_path(LEGACY_CONFIG_NAME)]


def load_config():
    for path in _read_config_candidates():
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    return {}


def save_config(data):
    """Best-effort write.  A read-only install must not break editing."""
    try:
        with open(_config_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        return True
    except OSError:
        return False
