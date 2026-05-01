#!/usr/bin/env python3
"""Check that all .yml localization files have UTF-8 BOM."""

from pathlib import Path

BOM = b"\xef\xbb\xbf"


def run(mod_root: Path, changed: set[Path] | None = None) -> list[str]:
    errors = []
    for f in sorted(mod_root.rglob("*.yml")):
        if ".claude" in f.parts or "__pycache__" in f.parts:
            continue
        if changed is not None and f not in changed:
            continue
        try:
            head = f.read_bytes()[:3]
        except Exception:
            continue
        if head != BOM:
            errors.append(f"{f.relative_to(mod_root)}: missing UTF-8 BOM")
    return errors
