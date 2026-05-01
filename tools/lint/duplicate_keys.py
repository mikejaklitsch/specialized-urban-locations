#!/usr/bin/env python3
"""Check for duplicate top-level block names and @macro definitions per file.

For .gui files, only @macros are checked — GUI uses generic block names
(widget, container, window) that repeat by design.
"""

import re
from pathlib import Path
from ._util import strip_comment

MACRO_RE = re.compile(r"^(@\w+)\s*=")
BLOCK_RE = re.compile(r"^(\w[\w:]*)\s*=\s*\{")
INJECT_RE = re.compile(r"^((?:TRY_)?(?:INJECT|REPLACE)(?:_OR_CREATE)?:\w+)\s*=\s*\{")


def run(mod_root: Path, changed: set[Path] | None = None) -> list[str]:
    errors = []
    for ext in ("*.txt", "*.gui"):
        check_blocks = ext == "*.txt"
        for f in sorted(mod_root.rglob(ext)):
            if ".claude" in f.parts or "__pycache__" in f.parts:
                continue
            if changed is not None and f not in changed:
                continue
            try:
                text = f.read_text(encoding="utf-8-sig")
            except Exception:
                continue
            macros: dict[str, list[int]] = {}
            blocks: dict[str, list[int]] = {}
            depth = 0
            for i, line in enumerate(text.splitlines(), 1):
                stripped = strip_comment(line)
                m = MACRO_RE.match(stripped.strip())
                if m:
                    macros.setdefault(m.group(1), []).append(i)
                if check_blocks and depth == 0:
                    m = INJECT_RE.match(stripped.strip()) or BLOCK_RE.match(stripped.strip())
                    if m:
                        blocks.setdefault(m.group(1), []).append(i)
                depth += stripped.count("{") - stripped.count("}")

            rel = f.relative_to(mod_root)
            for name, lines in macros.items():
                if len(lines) > 1:
                    errors.append(f"{rel}: duplicate @macro '{name}' on lines {', '.join(map(str, lines))}")
            for name, lines in blocks.items():
                if len(lines) > 1:
                    errors.append(f"{rel}: duplicate block '{name}' on lines {', '.join(map(str, lines))}")
    return errors
