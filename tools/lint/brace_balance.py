#!/usr/bin/env python3
"""Check that every .txt and .gui file has balanced braces."""

from pathlib import Path
from ._util import strip_comment


def run(mod_root: Path, changed: set[Path] | None = None) -> list[str]:
    errors = []
    for ext in ("*.txt", "*.gui"):
        for f in sorted(mod_root.rglob(ext)):
            if ".claude" in f.parts or "__pycache__" in f.parts:
                continue
            if changed is not None and f not in changed:
                continue
            try:
                text = f.read_text(encoding="utf-8-sig")
            except Exception:
                continue
            depth = 0
            for i, line in enumerate(text.splitlines(), 1):
                stripped = strip_comment(line)
                depth += stripped.count("{") - stripped.count("}")
                if depth < 0:
                    errors.append(f"{f.relative_to(mod_root)}:{i}: brace depth went negative ({depth})")
                    break
            else:
                if depth != 0:
                    errors.append(f"{f.relative_to(mod_root)}: unclosed braces (depth {depth} at EOF)")
    return errors
