"""Isolated parser for large YAML cache misses; invoked by Pack.load."""

import os
import sys

from genesisleaf.core.pack import _parse_cache_file, _parse_yaml_and_cache


def main():
    path = sys.argv[1]
    data = _parse_yaml_and_cache(path)
    if not isinstance(data, dict) or not isinstance(data.get("sections"), dict):
        return 1
    return 0 if os.path.isfile(_parse_cache_file(path, os.stat(path))) else 1


if __name__ == "__main__":
    raise SystemExit(main())
