"""GenesisLeaf version identity and the version-string scheme.

Scheme:  <Major>x<Minor><Patch>

    Major   one hex digit     0-F
    Minor   two hex digits    00-FF
    Patch   one letter        a-z, then A-Z   (a < b < ... < z < A < ... < Z)

    "0x5b"   ->  major 0, minor 0x05, patch 'b' (compact release label)

Bumping the minor resets the patch to 'a'; bumping the major resets both.
`version_key()` gives a sortable tuple so two version strings can be compared.

Part of GenesisLeaf 0x5b - see docs/ARCHITECTURE.md.
"""

import re

APP_NAME = "GenesisLeaf"

PATCH_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_VERSION_RE = re.compile(r"^([0-9A-Fa-f])x([0-9A-Fa-f]{1,2})([a-zA-Z])$")


def format_version(major, minor, patch):
    """(0, 1, 'a') -> '0x01a'.  Raises ValueError outside the scheme."""
    if not 0 <= int(major) <= 0xF:
        raise ValueError("major must be 0-F, got %r" % (major,))
    if not 0 <= int(minor) <= 0xFF:
        raise ValueError("minor must be 00-FF, got %r" % (minor,))
    if patch not in PATCH_LETTERS or len(patch) != 1:
        raise ValueError("patch must be one letter a-z / A-Z, got %r" % (patch,))
    return "%Xx%02X%s" % (int(major), int(minor), patch)


def parse_version(text):
    """Parse padded or compact labels such as '0x01a' and '0x5b'."""
    m = _VERSION_RE.match((text or "").strip())
    if not m:
        raise ValueError("not a GenesisLeaf version: %r" % (text,))
    return int(m.group(1), 16), int(m.group(2), 16), m.group(3)


def version_key(text):
    """Sortable key: (major, minor, patch ordinal)."""
    major, minor, patch = parse_version(text)
    return major, minor, PATCH_LETTERS.index(patch)


def next_version(text, part="patch"):
    """The version after `text`, bumping `part` ('patch' | 'minor' | 'major')."""
    major, minor, patch = parse_version(text)
    if part == "patch":
        i = PATCH_LETTERS.index(patch) + 1
        if i >= len(PATCH_LETTERS):
            raise ValueError("patch letters exhausted - bump the minor instead")
        return format_version(major, minor, PATCH_LETTERS[i])
    if part == "minor":
        return format_version(major, minor + 1, "a")
    if part == "major":
        return format_version(major + 1, 0, "a")
    raise ValueError("part must be 'patch', 'minor' or 'major'")


VERSION_MAJOR = 0x1
VERSION_MINOR = 0x02
VERSION_PATCH = "b"
VERSION = "1x02b"
RELEASE_NAME = "Public Beta"

# Title-bar / About strings.
APP_TITLE = "%s %s %s  -  Legend of Legaia Language Pack Suite" % (
    APP_NAME, RELEASE_NAME, VERSION)
APP_REVISION = "Stann0x Studio  @  2026"
CREDITS = (
    ("Stann0x Studio", "@ 2026"),
)
