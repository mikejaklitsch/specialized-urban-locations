#!/usr/bin/env python3
"""Check for dot-chains split across quote boundaries.

Formulas that require quotation marks (function calls, variable_map access)
must have the entire dot-chain inside the quotes. A quote character cannot
appear between a scope chain and its formula.

Bad:  scope:foo."function(x|y)"    — chain outside quotes, formula inside
Good: "scope:foo.function(x|y)"    — entire expression quoted
OK:   scope:foo.var:bar            — no quotes needed, no formula
"""

import re
from pathlib import Path
from ._util import strip_comment

# dot-chain ending at a quote boundary: word."
CHAIN_INTO_QUOTE_RE = re.compile(r'\b(\w[\w:]*(?:\.\w[\w:]*)*)\."')

# quote boundary then dot-chain out: ".word
QUOTE_OUT_CHAIN_RE = re.compile(r'"\.([\w:]+(?:\.\w[\w:]*)*)')


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
        rel = f.relative_to(mod_root)
        for i, line in enumerate(text.splitlines(), 1):
            code = strip_comment(line)
            if not code.strip():
                continue
            for m in CHAIN_INTO_QUOTE_RE.finditer(code):
                errors.append(f"{rel}:{i}: dot-chain enters quotes: {m.group(0)}")
            for m in QUOTE_OUT_CHAIN_RE.finditer(code):
                errors.append(f"{rel}:{i}: dot-chain exits quotes: {m.group(0)}")
    return errors
