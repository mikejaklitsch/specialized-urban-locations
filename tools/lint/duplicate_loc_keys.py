#!/usr/bin/env python3
"""Check for duplicate localization keys within each language directory.

Cross-language duplicates are expected (translations). Only flags duplicates
within the same language folder (e.g. two english files defining the same key).

Always scans all files — a changed file could duplicate a key in an unchanged file.
"""

import re
from collections import defaultdict
from pathlib import Path

LOC_KEY_RE = re.compile(r"^\s+([\w.]+):\d*\s")

LANGUAGES = {
    "english", "french", "german", "spanish", "russian",
    "polish", "braz_por", "japanese", "korean", "simp_chinese", "turkish",
}


def _lang_dir(f: Path) -> str:
    for part in f.parts:
        if part in LANGUAGES:
            return part
    return "unknown"


def run(mod_root: Path, changed: set[Path] | None = None) -> list[str]:
    if changed is not None and not any(f.suffix == ".yml" for f in changed):
        return []
    errors = []
    by_lang: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for f in sorted(mod_root.rglob("*.yml")):
        if ".claude" in f.parts or "__pycache__" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        lang = _lang_dir(f)
        rel = str(f.relative_to(mod_root))
        for i, line in enumerate(text.splitlines(), 1):
            m = LOC_KEY_RE.match(line)
            if m:
                by_lang[lang][m.group(1)].append(f"{rel}:{i}")
    for lang in sorted(by_lang):
        for key, locations in sorted(by_lang[lang].items()):
            if len(locations) > 1:
                errors.append(f"[{lang}] duplicate loc key '{key}': {', '.join(locations)}")
    return errors
