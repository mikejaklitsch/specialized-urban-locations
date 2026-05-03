#!/usr/bin/env python3
"""Check that setup files have no UTF-8 BOM (breaks the engine parser)."""

from pathlib import Path

SETUP_DIR = Path("main_menu") / "setup"


def run(mod_root: Path, changed: set[Path] | None = None) -> list[str]:
    errors = []
    setup_root = mod_root / SETUP_DIR
    if not setup_root.exists():
        return errors
    for f in sorted(setup_root.rglob("*.txt")):
        if changed is not None and f not in changed:
            continue
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        if raw[:3] == b"\xef\xbb\xbf":
            errors.append(f"BOM on setup file: {f.relative_to(mod_root)}")
    return errors
