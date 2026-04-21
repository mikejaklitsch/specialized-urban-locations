#!/usr/bin/env python3
"""
Generate starting development values based on pop-pressure equilibrium.

Reads:
  <vanilla>/main_menu/setup/start/06_pops.txt     (pop distributions)
  <vanilla>/main_menu/setup/start/03_markets.txt   (market center locations)
  <vanilla>/main_menu/setup/start/07_cities_and_buildings.txt (ranks)
  <mod>/main_menu/setup/start/50_sul_setup.txt     (seeded buildings)

Writes:
  <mod>/main_menu/setup/start/14_development.txt   (REPLACE vanilla)

Equilibrium formula:
  eq = 50
       - peasant_share * 30
       - tribesman_share * 30
       - slave_share * 30
       - laborer_share * 15
       + burgher_share * 30
       + (production_buildings - extraction_buildings) * 0.2
       + 5 if market_center
  clamped to [0, 100], rounded to nearest integer.

Building classification:
  Extraction: sul_rgo_*, farming_village, fishing_village, sul_mining_village,
              forest_village
  Production: market_village
  (All seeded buildings in 50_sul_setup.txt)
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Pop pressure coefficients (must match sul_development_pressure.txt)
# ─────────────────────────────────────────────────────────────────────────────

POP_PRESSURE = {
    "peasants":   -0.03,
    "tribesmen":  -0.03,
    "slaves":     -0.03,
    "laborers":   -0.015,
    "burghers":    0.03,
}

# Building classification
EXTRACTION_PREFIXES = ("sul_rgo_",)
EXTRACTION_EXACT = {"farming_village", "fishing_village", "sul_mining_village", "forest_village"}
PRODUCTION_EXACT = {"market_village"}

MARKET_CENTER_BONUS = 5  # dev points

RANK_BONUS = {
    "town": 10,
    "city": 25,
}

# Geography equilibrium shifts (flat_value / 0.001 spring decay)
# Must match in_game/common/script_values/sul_specialization_constants.txt
VEGETATION_SHIFT = {
    "desert":    -12,
    "jungle":    -20,
    "forest":     -8,
    "woods":      -3,
    "farmland":    0,
    "grasslands":  0,
}

TOPOGRAPHY_SHIFT = {
    "mountains": -25,
    "wetlands":  -15,
    "hills":      -2,
    "plateau":    -1,
    "flatland":    0,
    "lakes":       0,
}

CLIMATE_SHIFT = {
    "arctic":     -30,
    "tropical":    -2,
    "continental":  0,
    "temperate":    0,
    "arid":         0,
}

# Base equilibrium (from the spring: +0.05 base, -0.001/dev → eq=50)
BASE_EQ = 50.0

# dev shift per building: ±0.0002 / 0.001 = ±0.2
BUILDING_DEV_SHIFT = 0.2


# ─────────────────────────────────────────────────────────────────────────────
# Regexes
# ─────────────────────────────────────────────────────────────────────────────

LOCATION_BLOCK_RE = re.compile(
    r"^([a-z_][a-z0-9_]*)\s*=\s*\{(.*?)\}\s*$", re.IGNORECASE
)
POP_FIELD_RE = re.compile(
    r"\b(type|size)\s*=\s*([A-Za-z_][A-Za-z0-9_]*|[0-9.]+)"
)
DEFINE_POP_RE = re.compile(r"define_pop\s*=\s*\{([^}]*)\}", re.DOTALL)
MARKET_ADD_RE = re.compile(r"\badd_market\s*=\s*([a-z_][a-z0-9_]*)")
RANK_RE = re.compile(r"\brank\s*=\s*(rural_settlement|town|city)")
BUILDING_LINE_RE = re.compile(
    r"^\s*([a-z_][a-z0-9_]*)\s*=\s*\{\s*location\s*=\s*([a-z_][a-z0-9_]*)",
    re.MULTILINE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────

LOC_OPEN_RE = re.compile(r"^([a-z_][a-z0-9_]*)\s*=\s*\{", re.IGNORECASE)

def parse_pops(path: Path) -> dict:
    """Return {location: {pop_type: total_size}}."""
    result = defaultdict(lambda: defaultdict(float))
    current_loc = None
    depth = 0

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Count braces on this line
        opens = stripped.count("{")
        closes = stripped.count("}")

        # At depth 1 (inside top-level locations={}), look for location blocks
        if depth == 1 and current_loc is None:
            m = LOC_OPEN_RE.match(stripped)
            if m:
                current_loc = m.group(1)

        # Collect pop data inside a location block
        if current_loc and "define_pop" in stripped:
            fields = dict(POP_FIELD_RE.findall(stripped))
            pop_type = fields.get("type")
            size_str = fields.get("size", "0")
            try:
                size = float(size_str)
            except ValueError:
                size = 0
            if pop_type:
                result[current_loc][pop_type] += size

        depth += opens - closes

        # If we dropped back to depth 1, the location block closed
        if depth <= 1:
            current_loc = None

    return dict(result)


def parse_market_centers(path: Path) -> set:
    text = path.read_text(encoding="utf-8-sig")
    return {m.group(1) for m in MARKET_ADD_RE.finditer(text)}


def parse_ranks(path: Path) -> dict:
    """Return {location: rank}."""
    result = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = LOCATION_BLOCK_RE.match(line.strip())
        if m:
            loc_name = m.group(1)
            body = m.group(2)
            rm = RANK_RE.search(body)
            if rm:
                result[loc_name] = rm.group(1)
    return result


def parse_buildings(path: Path) -> dict:
    """Return {location: [(building_type, level), ...]}."""
    result = defaultdict(list)
    text = path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: building_type = { location = X tag = Y level = N }
        m = re.match(
            r"([a-z_][a-z0-9_]*)\s*=\s*\{\s*location\s*=\s*([a-z_][a-z0-9_]*)"
            r".*?level\s*=\s*(\d+)",
            line
        )
        if m:
            btype, loc, level = m.group(1), m.group(2), int(m.group(3))
            result[loc].append((btype, level))
    return dict(result)


TERRAIN_FIELD_RE = re.compile(
    r"\b(topography|vegetation|climate)\s*=\s*([a-z_]+)"
)


def parse_terrain(path: Path) -> dict:
    """Return {location: {topography, vegetation, climate}}."""
    result = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([a-z_][a-z0-9_]*)\s*=\s*\{", line)
        if not m:
            continue
        loc = m.group(1)
        fields = dict(TERRAIN_FIELD_RE.findall(line))
        result[loc] = fields
    return result


def classify_building(name: str) -> str:
    """Return 'extraction', 'production', or 'other'."""
    if name in EXTRACTION_EXACT:
        return "extraction"
    if name in PRODUCTION_EXACT:
        return "production"
    for prefix in EXTRACTION_PREFIXES:
        if name.startswith(prefix):
            return "extraction"
    return "other"


# ─────────────────────────────────────────────────────────────────────────────
# Equilibrium calculator
# ─────────────────────────────────────────────────────────────────────────────

def compute_equilibrium(
    pop_dist: dict,
    buildings: list,
    is_market_center: bool,
    rank: str = "rural_settlement",
    terrain: dict = None,
) -> float:
    """Compute predicted development equilibrium for a location."""
    eq = BASE_EQ

    # Geography shifts
    if terrain:
        eq += VEGETATION_SHIFT.get(terrain.get("vegetation", ""), 0)
        eq += TOPOGRAPHY_SHIFT.get(terrain.get("topography", ""), 0)
        eq += CLIMATE_SHIFT.get(terrain.get("climate", ""), 0)

    # Pop pressure
    total_pop = sum(pop_dist.values())
    if total_pop > 0:
        for pop_type, coeff in POP_PRESSURE.items():
            share = pop_dist.get(pop_type, 0) / total_pop
            # coeff is monthly pressure; shift = coeff / 0.001
            eq += (coeff / 0.001) * share

    # Building pressure
    ext_count = 0
    prod_count = 0
    for btype, level in buildings:
        cls = classify_building(btype)
        if cls == "extraction":
            ext_count += level
        elif cls == "production":
            prod_count += level

    eq += (prod_count - ext_count) * BUILDING_DEV_SHIFT

    # Rank bonus
    eq += RANK_BONUS.get(rank, 0)

    # Market center
    if is_market_center:
        eq += MARKET_CENTER_BONUS

    return max(0.0, min(100.0, eq))


# ─────────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────────

def generate_development_file(
    locations: dict,
    output_path: Path,
):
    """Write the development setup file with per-location values."""
    lines = [
        "# Generated by tools/generate_starting_development.py — do not hand-edit.",
        "# Starting development based on pop-pressure equilibrium.",
        "#",
        "# Equilibrium = 50 + pop_pressure + building_pressure + market_bonus",
        "# Pop pressure: peasants/tribesmen/slaves -30/100%, laborers -15/100%, burghers +30/100%",
        "",
        "development = {",
        "\tbase = 20",
        "",
        "\t# Per-location values are offsets from base",
        "",
    ]

    BASE = 20
    # Sort locations alphabetically for reproducibility
    for loc_name in sorted(locations.keys()):
        delta = locations[loc_name] - BASE
        if delta != 0:
            lines.append(f"\t{loc_name} = {delta}")

    lines.append("}")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate starting development from pop equilibrium"
    )
    parser.add_argument(
        "--vanilla",
        type=Path,
        default=Path("/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game"),
        help="Path to vanilla game directory",
    )
    parser.add_argument(
        "--mod",
        type=Path,
        default=None,
        help="Path to mod dev directory (auto-detected if not given)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats without writing",
    )
    args = parser.parse_args()

    if args.mod is None:
        args.mod = Path(__file__).resolve().parent.parent

    vanilla = args.vanilla
    mod = args.mod

    # Source files — prefer mod overrides, fall back to vanilla
    pops_file = mod / "main_menu/setup/start/06_pops.txt"
    if not pops_file.exists():
        pops_file = vanilla / "main_menu/setup/start/06_pops.txt"

    markets_file = vanilla / "main_menu/setup/start/03_markets.txt"
    ranks_file = vanilla / "main_menu/setup/start/07_cities_and_buildings.txt"
    buildings_file = mod / "main_menu/setup/start/50_sul_setup.txt"
    terrain_file = vanilla / "in_game/map_data/location_templates.txt"
    output_file = mod / "main_menu/setup/start/14_development.txt"

    print(f"Pops:      {pops_file}")
    print(f"Markets:   {markets_file}")
    print(f"Ranks:     {ranks_file}")
    print(f"Terrain:   {terrain_file}")
    print(f"Buildings: {buildings_file}")
    print(f"Output:    {output_file}")
    print()

    # Parse inputs
    pop_data = parse_pops(pops_file)
    market_centers = parse_market_centers(markets_file)
    ranks = parse_ranks(ranks_file)
    terrain_data = parse_terrain(terrain_file) if terrain_file.exists() else {}
    buildings = parse_buildings(buildings_file) if buildings_file.exists() else {}

    print(f"Locations with pops:  {len(pop_data)}")
    print(f"Market centers:       {len(market_centers)}")
    print(f"Locations with rank:  {len(ranks)}")
    print(f"Locations with terrain: {len(terrain_data)}")
    print(f"Locations with bldgs: {len(buildings)}")
    print()

    # Compute equilibrium for every location with pops
    results = {}
    eq_sum = 0
    eq_min = 100
    eq_max = 0
    count_by_bucket = defaultdict(int)

    for loc_name, pops in pop_data.items():
        loc_buildings = buildings.get(loc_name, [])
        is_mc = loc_name in market_centers
        loc_terrain = terrain_data.get(loc_name, {})

        loc_rank = ranks.get(loc_name, "rural_settlement")
        eq = compute_equilibrium(pops, loc_buildings, is_mc, loc_rank, loc_terrain)
        dev = round(eq)

        results[loc_name] = dev
        eq_sum += eq
        eq_min = min(eq_min, eq)
        eq_max = max(eq_max, eq)

        bucket = (dev // 10) * 10
        count_by_bucket[bucket] += 1

    avg_eq = eq_sum / len(results) if results else 0

    print(f"Locations processed:  {len(results)}")
    print(f"Equilibrium range:    {eq_min:.1f} - {eq_max:.1f}")
    print(f"Average equilibrium:  {avg_eq:.1f}")
    print()
    print("Distribution:")
    for bucket in sorted(count_by_bucket.keys()):
        count = count_by_bucket[bucket]
        bar = "#" * (count // 50)
        print(f"  {bucket:3d}-{bucket+9:3d}: {count:5d}  {bar}")

    if not args.dry_run:
        generate_development_file(results, output_file)
        print(f"\nWrote {output_file}")
    else:
        print("\n(dry run — no file written)")


if __name__ == "__main__":
    main()
