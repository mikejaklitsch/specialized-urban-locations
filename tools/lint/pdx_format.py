#!/usr/bin/env python3
"""Check that all .txt and .gui files pass pdx-format --check."""

import subprocess
from pathlib import Path

PDX_FORMAT = str(Path.home() / ".local" / "bin" / "pdx-format")

NO_BOM_DIRS = {"setup"}


def _needs_no_bom(f: Path) -> bool:
    return any(d in f.parts for d in NO_BOM_DIRS)


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
        cmd = [PDX_FORMAT, "--check"]
        if _needs_no_bom(f):
            cmd.append("--no-bom")
        cmd.append(str(f))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            errors.append(f"needs formatting: {f.relative_to(mod_root)}")
    return errors
