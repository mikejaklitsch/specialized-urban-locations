#!/usr/bin/env python3
"""Check that generated files are up-to-date with their source inputs.

Compares mtimes of known generated files against their input dependencies.
If any input is newer than the output, the generated content is stale.

Always runs regardless of changed files — it's cheap (just stat calls).
"""

from pathlib import Path

GENERATORS = [
    {
        "name": "EPBM hooks",
        "script": "tools/generate_epbm_hooks.sh",
        "outputs": [
            "in_game/common/building_types/sul_epbm_generated_inject.txt",
            "in_game/common/building_types/sul_epbm_generated_replace.txt",
            "in_game/common/scripted_effects/sul_epbm_generated_init_effects.txt",
            "in_game/common/international_organizations/sul_epbm_generated_ios.txt",
            "in_game/common/biases/sul_epbm_generated_biases.txt",
            "main_menu/localization/english/sul_epbm_ios_l_english.yml",
        ],
        "inputs": [
            "in_game/common/building_types/*.txt",
            "tools/generate_building_hooks.py",
            "tools/exclusions.txt",
        ],
        "exclude_inputs": ["sul_epbm_generated_*.txt"],
    },
    {
        "name": "GDP building effects",
        "script": "tools/generate_buildings.py",
        "outputs": [
            "in_game/common/scripted_effects/sul_gdp_generated_effects.txt",
        ],
        "inputs": [
            "tools/generate_buildings.py",
            "tools/building_config.json",
        ],
    },
]


def _newest_mtime(mod_root: Path, globs: list[str], exclude: list[str] | None = None) -> float:
    newest = 0.0
    exclude = exclude or []
    for g in globs:
        for f in mod_root.glob(g):
            if any(f.match(ex) for ex in exclude):
                continue
            if f.is_file():
                newest = max(newest, f.stat().st_mtime)
    return newest


def _oldest_mtime(mod_root: Path, paths: list[str]) -> float | None:
    oldest = None
    for p in paths:
        f = mod_root / p
        if not f.exists():
            return None
        t = f.stat().st_mtime
        if oldest is None or t < oldest:
            oldest = t
    return oldest


def run(mod_root: Path, changed: set[Path] | None = None) -> list[str]:
    errors = []
    for gen in GENERATORS:
        out_mtime = _oldest_mtime(mod_root, gen["outputs"])
        if out_mtime is None:
            missing = [p for p in gen["outputs"] if not (mod_root / p).exists()]
            errors.append(f"{gen['name']}: missing output(s): {', '.join(missing)}")
            continue
        in_mtime = _newest_mtime(mod_root, gen["inputs"], gen.get("exclude_inputs"))
        if in_mtime > out_mtime:
            errors.append(f"{gen['name']}: generated files are stale (run {gen['script']})")
    return errors
