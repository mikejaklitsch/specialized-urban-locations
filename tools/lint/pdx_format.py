#!/usr/bin/env python3
"""Check that all .txt and .gui files pass pdx-format --check."""

import subprocess
from pathlib import Path

PDX_FORMAT = str(Path.home() / ".local" / "bin" / "pdx-format")


def run(mod_root: Path, changed: set[Path] | None = None) -> list[str]:
    errors = []
    files = []
    for ext in ("*.txt", "*.gui"):
        files.extend(mod_root.rglob(ext))
    files = sorted(
        f for f in files
        if ".claude" not in f.parts and "__pycache__" not in f.parts
        and (changed is None or f in changed)
    )
    if not files:
        return errors
    for f in files:
        result = subprocess.run(
            [PDX_FORMAT, "--check", str(f)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            errors.append(f"needs formatting: {f.relative_to(mod_root)}")
    return errors
