#!/usr/bin/env python3
"""
One-time migration: add rank flags to mod INJECT blocks.

Rules:
  - Rural production buildings (sul_rural_*, rural_clothmaker): locked to
    their specialty's 3 ranks, gated by production modifier
  - Other production buildings: vanilla tier restriction replicated across
    specs that have the gating production flag
  - University: commercial_town + all *_city ranks
  - Everything else (non-production/non-trade): clean convert, vanilla tiers
    across all 5 specs

Reads from:
  - in_game/common/scripted_triggers/sul_triggers.txt (spec → building lists)
  - vanilla building files (tier flags)
  - in_game/common/building_types/sul_*.txt (mod INJECTs to update)

Writes updated mod files to --output (default: /tmp/sul_rank_migration/).
Does NOT modify live files.

Usage:
    python tools/migrate_rank_flags.py
    python tools/migrate_rank_flags.py --output /tmp/test
    python tools/migrate_rank_flags.py --apply   # overwrites live mod files
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

MOD_ROOT = Path(__file__).resolve().parent.parent
VANILLA_BUILDING_DIR = Path(
    "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V"
    "/game/in_game/common/building_types"
)
MOD_BUILDING_DIR = MOD_ROOT / "in_game" / "common" / "building_types"
TRIGGERS_FILE = MOD_ROOT / "in_game" / "common" / "scripted_triggers" / "sul_triggers.txt"

SPECS = ["mining", "farming", "gathering", "woodland", "commercial"]
OLD_RANKS = {"rural_settlement", "town", "city"}

# Production flag → spec mapping (from rank definitions)
RANK_FILE = MOD_ROOT / "in_game" / "common" / "location_ranks" / "00_default.txt"


def parse_spec_buildings(triggers_text):
    """Extract building lists from sul_is_{spec}_building triggers."""
    spec_buildings = {}
    for spec in SPECS:
        pattern = rf"sul_is_{spec}_building\s*=\s*\{{(.*?)\n\}}"
        match = re.search(pattern, triggers_text, re.DOTALL)
        if not match:
            continue
        buildings = re.findall(r"building_type\s*=\s*building_type:(\S+)", match.group(1))
        buildings = [b for b in buildings if not b.startswith("sul_respec_")]
        spec_buildings[spec] = set(buildings)
    return spec_buildings


def build_building_to_specs(spec_buildings):
    """Invert: building → set of specs it belongs to."""
    b2s = defaultdict(set)
    for spec, buildings in spec_buildings.items():
        for b in buildings:
            b2s[b].add(spec)
    return b2s


def get_vanilla_tier_flags(name):
    """Read vanilla tier flags for a building."""
    for f in sorted(VANILLA_BUILDING_DIR.glob("*.txt")):
        text = f.read_text(encoding="utf-8-sig")
        pattern = rf"^{re.escape(name)}\s*=\s*\{{"
        match = re.search(pattern, text, re.MULTILINE)
        if not match:
            continue
        # Find block end
        depth, i = 1, match.end()
        while i < len(text) and depth > 0:
            if text[i] == "{": depth += 1
            elif text[i] == "}": depth -= 1
            i += 1
        body = text[match.end():i-1]
        flags = {}
        for rank in OLD_RANKS:
            m = re.search(rf"\b{rank}\s*=\s*(yes|no)", body)
            if m:
                flags[rank] = m.group(1) == "yes"
        return flags
    return {}


def is_rural_variant(name):
    """Check if building is a rural production variant."""
    return name.startswith("sul_rural_") or name == "rural_clothmaker"


def compute_rank_flags(name, building_specs, vanilla_flags):
    """Compute rank flags based on the rules."""
    # University special case
    if name == "university":
        ranks = ["commercial_town"]
        for s in SPECS:
            ranks.append(f"{s}_city")
        return sorted(ranks)

    # Rural production variants: all tiers of their spec only
    if is_rural_variant(name) and building_specs:
        ranks = []
        for s in sorted(building_specs):
            ranks.extend([f"{s}_rural", f"{s}_town", f"{s}_city"])
        return ranks

    # Determine tier availability from vanilla
    # If any flag is explicitly set, missing flags default to False
    has_any = bool(vanilla_flags)
    default = not has_any
    allow_rural = vanilla_flags.get("rural_settlement", default)
    allow_town = vanilla_flags.get("town", default)
    allow_city = vanilla_flags.get("city", default)

    # Production buildings: only their specs
    if building_specs:
        target_specs = sorted(building_specs)
    else:
        # Non-production: all specs
        target_specs = SPECS

    ranks = []
    for s in target_specs:
        if allow_rural:
            ranks.append(f"{s}_rural")
        if allow_town:
            ranks.append(f"{s}_town")
        if allow_city:
            ranks.append(f"{s}_city")
    return sorted(ranks)


def find_inject_blocks(text):
    """Find all INJECT blocks in a file, return (name, start, end) tuples."""
    pattern = re.compile(
        r"^((?:INJECT|TRY_INJECT|INJECT_OR_CREATE):)([a-z_][a-z0-9_]*)\s*=\s*\{",
        re.MULTILINE | re.IGNORECASE,
    )
    blocks = []
    for m in pattern.finditer(text):
        prefix = m.group(1)
        name = m.group(2)
        depth, i = 1, m.end()
        while i < len(text) and depth > 0:
            if text[i] == "{": depth += 1
            elif text[i] == "}": depth -= 1
            i += 1
        blocks.append((name, prefix, m.start(), i))
    return blocks


def add_rank_flags_to_inject(text, name, prefix, block_start, block_end, rank_flags):
    """Insert rank flags into an INJECT block, replacing any existing rank flags."""
    block_body = text[block_start:block_end]

    # Find the closing brace of the top-level block
    # Remove existing rank flags
    cleaned_lines = []
    body_start = block_body.index("{") + 1
    body_end = block_body.rindex("}")
    inner = block_body[body_start:body_end]

    for line in inner.split("\n"):
        stripped = line.strip()
        # Skip old rank flags
        is_rank_flag = False
        for rank in OLD_RANKS:
            if stripped.startswith(f"{rank} =") or stripped.startswith(f"{rank}="):
                is_rank_flag = True
                break
        for s in SPECS:
            for t in ["rural", "town", "city"]:
                r = f"{s}_{t}"
                if stripped.startswith(f"{r} =") or stripped.startswith(f"{r}="):
                    is_rank_flag = True
                    break
        if not is_rank_flag:
            cleaned_lines.append(line)

    # Remove trailing empty lines before closing brace
    while cleaned_lines and cleaned_lines[-1].strip() == "":
        cleaned_lines.pop()

    # Build rank flag lines
    rank_lines = []
    for rank in OLD_RANKS:
        rank_lines.append(f"\t{rank} = no")
    rank_lines.append("")
    for rank in rank_flags:
        rank_lines.append(f"\t{rank} = yes")

    # Reconstruct
    header = block_body[:body_start]
    new_body = "\n".join(cleaned_lines)
    if new_body.strip():
        new_body += "\n\n"
    else:
        new_body = "\n"
    new_body += "\n".join(rank_lines) + "\n"

    return header + new_body + "}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, default=Path("/tmp/sul_rank_migration"))
    ap.add_argument("--apply", action="store_true",
                    help="Overwrite live mod files (dangerous)")
    args = ap.parse_args()

    # Parse spec → building lists
    triggers_text = TRIGGERS_FILE.read_text(encoding="utf-8-sig")
    spec_buildings = parse_spec_buildings(triggers_text)
    building_to_specs = build_building_to_specs(spec_buildings)
    print(f"Loaded building-to-spec mapping: {sum(len(v) for v in spec_buildings.values())} entries")

    # Process each mod building file
    args.output.mkdir(parents=True, exist_ok=True)
    total_updated = 0

    for mod_file in sorted(MOD_BUILDING_DIR.glob("sul_*.txt")):
        # Skip generated files
        if "epbm_generated" in mod_file.name or mod_file.name == "sul_rank_flag_injects.txt":
            continue
        if mod_file.name == "sul_respec_buildings.txt":
            continue

        text = mod_file.read_text(encoding="utf-8-sig")
        blocks = find_inject_blocks(text)
        if not blocks:
            continue

        updated = 0
        # Process blocks in reverse order to preserve positions
        for name, prefix, start, end in reversed(blocks):
            building_specs = building_to_specs.get(name, set())
            vanilla_flags = get_vanilla_tier_flags(name)
            rank_flags = compute_rank_flags(name, building_specs, vanilla_flags)

            if rank_flags:
                new_block = add_rank_flags_to_inject(text, name, prefix, start, end, rank_flags)
                text = text[:start] + new_block + text[end:]
                updated += 1

        if updated:
            out_path = args.output / mod_file.name
            out_path.write_text(text, encoding="utf-8-sig")
            print(f"  {mod_file.name}: updated {updated} INJECT blocks")
            total_updated += updated

    print(f"\nTotal: {total_updated} blocks updated")
    print(f"Output: {args.output}")

    if args.apply:
        print("\n--apply: copying to live mod files...")
        for f in args.output.glob("*.txt"):
            dest = MOD_BUILDING_DIR / f.name
            dest.write_text(f.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
            print(f"  {f.name} → {dest}")


if __name__ == "__main__":
    main()
