#!/usr/bin/env python3
"""
Generate starting development values based on pop-pressure equilibrium.

Reads:
  <vanilla>/main_menu/setup/start/06_pops.txt     (pop distributions)
  <vanilla>/main_menu/setup/start/03_markets.txt   (market center locations)
  <vanilla>/main_menu/setup/start/07_cities_and_buildings.txt (ranks)
  <mod>/main_menu/setup/start/50_sul_setup.txt     (seeded buildings)
  <mod>/in_game/common/building_types/*.txt        (building local_monthly_development)

Writes:
  <mod>/main_menu/setup/start/14_development.txt   (REPLACE vanilla)

Equilibrium formula (1 dev per 0.01 monthly_development):
  eq = 50
       + sum(building_flat_dev / 0.01)  per building level
       - peasant_share * 30
       - tribesman_share * 30
       - slave_share * 30
       - laborer_share * 15
       + burgher_share * 30
       + 5 if market_center
  clamped to [0, 100], rounded to nearest integer.

Building dev contribution is parsed from actual building definitions
(local_monthly_development per level in each building's modifier block).
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
    "peasants":   -0.3,
    "tribesmen":  -0.3,
    "slaves":     -0.3,
    "laborers":   -0.15,
    "burghers":    0.3,
}

MARKET_CENTER_BONUS = 25  # dev points

RANK_BONUS = {
    "town": 10,    # +0.10 monthly dev / 0.01 decay
    "city": 25,    # +0.25 monthly dev / 0.01 decay
}

# Government type global_monthly_development (must match sul_gov_type_adjustments.txt)
GOV_TYPE_DEV = {
    "republic": 0.1,
    "steppe_horde": -0.1,
}

# Reform bonuses (stacks with gov type)
REFORM_DEV = {
    "merchant_republic": 0.15,
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

# Base equilibrium (from the spring: +0.50 base, -0.01/dev → eq=50)
BASE_EQ = 50.0

# Spring decay rate (equilibrium = flat_monthly_dev / DECAY)
SPRING_DECAY = 0.01


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
OWNABLE_RE = re.compile(r"\b(religion|culture)\s*=\s*[a-z_]")


def parse_terrain(path: Path) -> tuple:
    """Return ({location: {topography, vegetation, climate}}, {ownable locations})."""
    result = {}
    ownable = set()
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
        if OWNABLE_RE.search(line):
            ownable.add(loc)
    return result, ownable


TAG_RE = re.compile(r"^([A-Z]{3})\s*=\s*\{")
GOV_TYPE_RE = re.compile(r"\btype\s*=\s*([a-z_]+)")
REFORM_RE = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*$")
OWN_BLOCK_RE = re.compile(r"\b(own_control_core|own_control_integrated|own_control_conquered|own_control_colony|own_core|own_conquered|own_integrated|own_colony)\s*=\s*\{")
LOC_NAME_RE = re.compile(r"[a-z_][a-z0-9_]*")


def parse_countries(path: Path) -> tuple:
    """Parse 10_countries.txt. Return (location→tag, tag→gov_dev_bonus)."""
    text = path.read_text(encoding="utf-8-sig")
    loc_owner = {}
    tag_bonus = {}

    current_tag = None
    gov_type = None
    reforms = set()
    owned_locs = []
    in_own_block = False
    in_gov_block = False
    in_reforms_block = False
    depth = 0
    tag_depth = 0
    own_depth = 0
    gov_depth = 0
    reforms_depth = 0

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        opens = stripped.count("{")
        closes = stripped.count("}")

        # Detect new country tag at depth 2 (inside countries = { countries = { )
        if depth == 2 and not current_tag:
            m = TAG_RE.match(stripped)
            if m:
                current_tag = m.group(1)
                tag_depth = depth + opens
                gov_type = None
                reforms = set()
                owned_locs = []

        if current_tag:
            # Detect ownership blocks
            if not in_own_block and OWN_BLOCK_RE.search(stripped):
                in_own_block = True
                own_depth = depth + opens

            # Detect government block
            if not in_gov_block and "government" in stripped and "{" in stripped and "type" not in stripped:
                in_gov_block = True
                gov_depth = depth + opens

            # Inside ownership block: collect location names
            if in_own_block:
                for word in LOC_NAME_RE.findall(stripped):
                    if word not in ("own_control_core", "own_control_integrated",
                                    "own_control_conquered", "own_control_colony",
                                    "own_core", "own_conquered", "own_integrated",
                                    "own_colony"):
                        owned_locs.append(word)

            # Inside government block
            if in_gov_block:
                gm = GOV_TYPE_RE.search(stripped)
                if gm:
                    gov_type = gm.group(1)

                if "reforms" in stripped and "{" in stripped:
                    in_reforms_block = True
                    reforms_depth = depth + opens

                if in_reforms_block:
                    for rm in REFORM_RE.finditer(stripped):
                        name = rm.group(1)
                        if name != "reforms":
                            reforms.add(name)

        new_depth = depth + opens - closes

        # Check for block closures
        if in_reforms_block and new_depth <= reforms_depth:
            in_reforms_block = False
        if in_gov_block and new_depth < gov_depth:
            in_gov_block = False
        if in_own_block and new_depth < own_depth:
            in_own_block = False
        if current_tag and new_depth < tag_depth:
            # Country block closed — commit
            bonus = GOV_TYPE_DEV.get(gov_type, 0)
            for r in reforms:
                bonus += REFORM_DEV.get(r, 0)
            tag_bonus[current_tag] = bonus
            for loc in owned_locs:
                loc_owner[loc] = current_tag
            current_tag = None

        depth = new_depth

    return loc_owner, tag_bonus


BUILDING_DEV_RE = re.compile(r"local_monthly_development\s*=\s*(-?[0-9.]+)")


def parse_building_dev(building_types_dir: Path) -> dict:
    """Parse local_monthly_development per level from building definition files.

    Returns {building_type: flat_dev_per_level}.
    Buildings without local_monthly_development are omitted (contribute 0).
    """
    result = {}
    for txt_file in sorted(building_types_dir.glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8-sig")
        current_building = None
        in_modifier = False
        depth = 0
        modifier_depth = 0

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            opens = stripped.count("{")
            closes = stripped.count("}")

            # Top-level or REPLACE/new building definition
            if depth == 0:
                m = re.match(
                    r"(?:(?:REPLACE|INJECT):)?([a-z_][a-z0-9_]*)\s*=\s*\{",
                    stripped,
                )
                if m:
                    current_building = m.group(1)
                    in_modifier = False

            # Detect modifier block inside building
            if current_building and not in_modifier:
                if re.search(r"\bmodifier\s*=\s*\{", stripped):
                    in_modifier = True
                    modifier_depth = depth + opens

            # Inside modifier: look for local_monthly_development (not _modifier)
            if in_modifier and "local_monthly_development" in stripped:
                if "local_monthly_development_modifier" not in stripped:
                    dm = BUILDING_DEV_RE.search(stripped)
                    if dm and current_building:
                        result[current_building] = float(dm.group(1))

            new_depth = depth + opens - closes

            if in_modifier and new_depth < modifier_depth:
                in_modifier = False
            if current_building and new_depth <= 0:
                current_building = None

            depth = new_depth

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Equilibrium calculator
# ─────────────────────────────────────────────────────────────────────────────

def compute_equilibrium(
    pop_dist: dict,
    buildings: list,
    is_market_center: bool,
    rank: str = "rural_settlement",
    terrain: dict = None,
    gov_bonus: float = 0.0,
    building_dev_map: dict = None,
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
            eq += (coeff / SPRING_DECAY) * share

    # Building pressure: actual flat local_monthly_development per building level
    if building_dev_map:
        for btype, level in buildings:
            flat_dev = building_dev_map.get(btype, 0)
            eq += (flat_dev / SPRING_DECAY) * level

    # Rank bonus
    eq += RANK_BONUS.get(rank, 0)

    # Market center
    if is_market_center:
        eq += MARKET_CENTER_BONUS

    # Government type / reform bonus
    eq += gov_bonus / SPRING_DECAY

    return max(0.0, min(100.0, eq))


# ─────────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────────

def generate_development_file(
    locations: dict,
    output_path: Path,
):
    """Write the development setup file with per-location absolute values."""
    lines = [
        "# Generated by tools/generate_starting_development.py — do not hand-edit.",
        "# Starting development based on pop-pressure equilibrium.",
        "#",
        "# Equilibrium = 50 + pop_pressure + building_dev/0.01 + terrain + market + rank + gov",
        "# Pop pressure: peasants/tribesmen/slaves -30/100%, laborers -15/100%, burghers +30/100%",
        "# Building dev: actual local_monthly_development per level from building definitions",
        "",
        "development = {",
        "\tbase = 0",
        "",
    ]

    for loc_name in sorted(locations.keys()):
        dev = locations[loc_name]
        if dev != 0:
            lines.append(f"\t{loc_name} = {dev}")

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

    vanilla_markets_file = vanilla / "main_menu/setup/start/03_markets.txt"
    mod_markets_file = mod / "main_menu/setup/start/51_sul_markets.txt"
    ranks_file = vanilla / "main_menu/setup/start/07_cities_and_buildings.txt"
    buildings_file = mod / "main_menu/setup/start/50_sul_setup.txt"
    terrain_file = vanilla / "in_game/map_data/location_templates.txt"
    countries_file = vanilla / "main_menu/setup/start/10_countries.txt"
    building_types_dir = mod / "in_game/common/building_types"
    output_file = mod / "main_menu/setup/start/14_development.txt"

    print(f"Pops:       {pops_file}")
    print(f"Markets:    {vanilla_markets_file}")
    print(f"Mod mkts:   {mod_markets_file}")
    print(f"Ranks:      {ranks_file}")
    print(f"Terrain:    {terrain_file}")
    print(f"Countries:  {countries_file}")
    print(f"Buildings:  {buildings_file}")
    print(f"Bldg defs:  {building_types_dir}")
    print(f"Output:     {output_file}")
    print()

    # Parse inputs
    pop_data = parse_pops(pops_file)
    market_centers = parse_market_centers(vanilla_markets_file)
    if mod_markets_file.exists():
        market_centers |= parse_market_centers(mod_markets_file)
    ranks = parse_ranks(ranks_file)
    terrain_data, ownable_locations = parse_terrain(terrain_file) if terrain_file.exists() else ({}, set())
    buildings = parse_buildings(buildings_file) if buildings_file.exists() else {}
    loc_owner, tag_bonus = parse_countries(countries_file) if countries_file.exists() else ({}, {})
    building_dev_map = parse_building_dev(building_types_dir) if building_types_dir.exists() else {}

    # All ownable locations: those with pops + those with terrain flagged ownable
    all_locations = set(pop_data.keys()) | ownable_locations

    # Gov type stats
    gov_counts = defaultdict(int)
    for tag, bonus in tag_bonus.items():
        if bonus != 0:
            gov_counts[bonus] += 1

    print(f"Locations with pops:    {len(pop_data)}")
    print(f"Market centers:         {len(market_centers)}")
    print(f"Locations with rank:    {len(ranks)}")
    print(f"Ownable locations:      {len(ownable_locations)}")
    print(f"Total locations:        {len(all_locations)}")
    print(f"Locations with bldgs:   {len(buildings)}")
    print(f"Building types w/ dev:  {len(building_dev_map)}")
    print(f"Countries parsed:       {len(tag_bonus)}")
    print(f"Owned locations:        {len(loc_owner)}")
    for bonus, count in sorted(gov_counts.items()):
        shift = bonus / SPRING_DECAY
        print(f"  gov bonus {bonus:+.2f} ({shift:+.0f} eq): {count} countries")
    for btype in sorted(building_dev_map):
        flat = building_dev_map[btype]
        shift = flat / SPRING_DECAY
        print(f"  {btype}: {flat:+.3f} flat ({shift:+.1f} eq/level)")
    print()

    # Compute equilibrium for every ownable location
    results = {}
    eq_sum = 0
    eq_min = 100
    eq_max = 0
    count_by_bucket = defaultdict(int)

    for loc_name in all_locations:
        pops = pop_data.get(loc_name, {})
        loc_buildings = buildings.get(loc_name, [])
        is_mc = loc_name in market_centers
        loc_terrain = terrain_data.get(loc_name, {})

        loc_rank = ranks.get(loc_name, "rural_settlement")
        owner_tag = loc_owner.get(loc_name)
        gov_bonus = tag_bonus.get(owner_tag, 0) if owner_tag else 0
        eq = compute_equilibrium(pops, loc_buildings, is_mc, loc_rank, loc_terrain, gov_bonus, building_dev_map)
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
