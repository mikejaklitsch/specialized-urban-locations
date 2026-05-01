#!/usr/bin/env python3
"""Check for complex value blocks in add_to_variable_map assignments.

The engine silently ignores computed values (blocks with {}) in
add_to_variable_map value fields — only literals and variable refs work.
"""

import re
from pathlib import Path
from ._util import strip_comment

ADD_MAP_RE = re.compile(r"\badd_to_variable_map\b")


def run(mod_root: Path, changed: set[Path] | None = None) -> list[str]:
    errors = []
    for f in sorted(mod_root.rglob("*.txt")):
        if ".claude" in f.parts or "__pycache__" in f.parts:
            continue
        if changed is not None and f not in changed:
            continue
        try:
            text = f.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        lines = text.splitlines()
        rel = f.relative_to(mod_root)
        i = 0
        while i < len(lines):
            stripped = strip_comment(lines[i])
            if ADD_MAP_RE.search(stripped):
                block_start = i
                depth = stripped.count("{") - stripped.count("}")
                in_value = False
                j = i + 1
                while j < len(lines) and depth > 0:
                    s = strip_comment(lines[j])
                    if not in_value and re.search(r"\bvalue\s*=\s*\{", s):
                        in_value = True
                        errors.append(
                            f"{rel}:{j + 1}: add_to_variable_map has complex value block "
                            f"(started at line {block_start + 1})"
                        )
                    depth += s.count("{") - s.count("}")
                    j += 1
                i = j
            else:
                i += 1
    return errors
