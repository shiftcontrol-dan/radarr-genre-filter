#!/usr/bin/env python3
"""Bump the package version and emit the new tag.

Usage:
    python scripts/bump_version.py [major|minor|patch]   # default: patch

Then:
    git commit -am "release vX.Y.Z" && git tag vX.Y.Z && git push --follow-tags
The Release workflow verifies the tag matches pyproject and cuts a GitHub release.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "radarr_janitor" / "__init__.py"


def main() -> int:
    part = sys.argv[1] if len(sys.argv) > 1 else "patch"
    if part not in {"major", "minor", "patch"}:
        print("usage: bump_version.py [major|minor|patch]", file=sys.stderr)
        return 2
    text = PYPROJECT.read_text()
    m = re.search(r'version = "(\d+)\.(\d+)\.(\d+)"', text)
    if not m:
        print("could not find version in pyproject.toml", file=sys.stderr)
        return 1
    major, minor, patch = (int(x) for x in m.groups())
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    new = f"{major}.{minor}.{patch}"
    PYPROJECT.write_text(re.sub(r'version = "\d+\.\d+\.\d+"', f'version = "{new}"', text, count=1))
    INIT.write_text(re.sub(r'__version__ = "\d+\.\d+\.\d+"', f'__version__ = "{new}"', INIT.read_text()))
    print(f"v{new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
