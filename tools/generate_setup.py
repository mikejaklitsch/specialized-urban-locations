#!/usr/bin/env python3
"""
Unified setup generator for the SUL 15-rank system.

Combines template variant generation with per-location RGO placement,
rank assignment, and pop distribution.

Phase 1 — Templates:
  Generate specialization-variant town_setup templates from vanilla templates.
  For each vanilla template × spec × profile, create a variant with spec-compatible
  building substitutions and village building injection.

Phase 2 — Per-location:
  For each owned location, place RGO buildings (raw_material-gated, pop-scaled),
  assign specialization ranks, and shift pops to match RGO pop types.

Reads:
  <vanilla>/in_game/map_data/location_templates.txt
  <vanilla>/in_game/map_data/definitions.txt
  <vanilla>/in_game/common/town_setups/00_default.txt
  <vanilla>/main_menu/setup/start/03_markets.txt
  <vanilla>/main_menu/setup/start/06_pops.txt
  <vanilla>/main_menu/setup/start/07_cities_and_buildings.txt
  <vanilla>/main_menu/setup/start/10_countries.txt
  <mod>/tools/building_config.json
  <mod>/in_game/common/scripted_effects/sul_init_effects.txt
  <mod>/in_game/common/building_types/sul_rgo_buildings.txt

Writes:
  <output>/in_game/common/town_setups/sul_town_setups.txt
  <output>/main_menu/setup/start/07_cities_and_buildings.txt
  <output>/main_menu/setup/start/50_sul_setup.txt
  <output>/main_menu/setup/start/06_pops.txt
  <output>/in_game/common/scripted_effects/sul_rank_setup_generated.txt

Usage:
    python tools/generate_setup.py --output /tmp/sul_setup_test
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from math import floor
from pathlib import Path

MOD_ROOT = Path(__file__).resolve().parent.parent
VANILLA_ROOT = Path(
    "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game"
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SPECS = ["mining", "farming", "gathering", "woodland", "commercial"]
TIERS = ["rural", "town", "city"]
RANK_SUFFIX = {"rural_settlement": "rural", "town": "town", "city": "city"}
POP_TYPE_FALLBACK = {"clergy": "burghers"}
PROFILES = ["default", "east_asia", "tech0", "tech1"]
PROFILE_TECH_LEVEL = {"tech0": 0, "tech1": 1, "default": 3, "east_asia": 3}

GOODS_TO_SPEC = {
    "coal": "mining", "iron": "mining", "copper": "mining", "gold": "mining", "goods_gold": "mining",
    "silver": "mining", "stone": "mining", "tin": "mining", "lead": "mining",
    "alum": "mining", "gems": "mining", "marble": "mining", "mercury": "mining",
    "horses": "farming", "silk": "farming", "tea": "farming", "cocoa": "farming",
    "coffee": "farming", "fiber_crops": "farming", "wine": "farming",
    "saffron": "farming", "pepper": "farming", "cloves": "farming",
    "chili": "farming", "cotton": "farming", "sugar": "farming",
    "tobacco": "farming", "wheat": "farming", "maize": "farming",
    "rice": "farming", "millet": "farming", "legumes": "farming",
    "potato": "farming", "livestock": "farming", "olives": "farming",
    "fruit": "farming",
    "clay": "gathering", "sand": "gathering", "salt": "gathering",
    "saltpeter": "gathering", "medicaments": "gathering", "pearls": "gathering",
    "amber": "gathering", "fish": "gathering", "wool": "gathering",
    "ivory": "gathering",
    "lumber": "woodland", "wild_game": "woodland", "fur": "woodland",
    "incense": "woodland", "elephants": "woodland", "beeswax": "woodland",
    "dyes": "woodland",
}

VILLAGE_BY_SPEC = {
    "farming": "farming_village",
    "gathering": "fishing_village",
    "mining": "sul_mining_village",
    "woodland": "forest_village",
    "commercial": "market_village",
}
VILLAGE_LEVEL_BY_TIER = {"rural": 1, "town": 2, "city": 3}

RGO_POP_PER_LEVEL = 50
LEVEL_CAP = 10
IRON_WORKING_STL = 1
TECH_GATED_RGOS = {"sul_rgo_iron", "sul_rgo_coal"}
EXCLUDED_POP_TYPES = {"slaves", "tribesmen"}

# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────

LOCATION_ENTRY_RE = re.compile(
    r"^\s*([a-z_][a-z0-9_]*)\s*=\s*\{(.*?)\}\s*$", re.IGNORECASE
)
RAW_MATERIAL_RE = re.compile(r"\braw_material\s*=\s*([a-z_][a-z0-9_]*)")
TOPOGRAPHY_RE = re.compile(r"\btopography\s*=\s*([a-z_][a-z0-9_]*)")
VEGETATION_RE = re.compile(r"\bvegetation\s*=\s*([a-z_][a-z0-9_]*)")
CLIMATE_RE = re.compile(r"\bclimate\s*=\s*([a-z_][a-z0-9_]*)")
MARKET_ADD_RE = re.compile(r"\badd_market\s*=\s*([a-z_][a-z0-9_]*)")
SETUP_BUILDING_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*=\s*(\d+)")
RANK_RE = re.compile(r"\brank\s*=\s*(rural_settlement|town|city)")
TOWN_SETUP_RE = re.compile(r"\btown_setup\s*=\s*([a-z_][a-z0-9_]*)")
BM_ENTRY_RE = re.compile(
    r"^\t([a-z_][a-z0-9_]*)\s*=\s*\{[^}]*\blocation\s*=\s*([a-z_][a-z0-9_]*)"
)
RGO_MAP_ENTRY_RE = re.compile(
    r"name\s*=\s*sul_rgo_map\s*key\s*=\s*goods:([a-z_][a-z0-9_]*)"
    r"\s*value\s*=\s*building_type:(sul_rgo_[a-z_][a-z0-9_]*)",
    re.DOTALL,
)
RGO_BUILDING_RE = re.compile(
    r"^(sul_rgo_[a-z_][a-z0-9_]*)\s*=\s*\{(.*?)^\}",
    re.DOTALL | re.MULTILINE,
)
POP_TYPE_RE = re.compile(r"\bpop_type\s*=\s*([a-z_]+)")
DEFINE_POP_BLOCK_RE = re.compile(r"define_pop\s*=\s*\{[^}]*\}", re.DOTALL)
POP_FIELD_RE = re.compile(
    r"\b(type|size|culture|religion)\s*=\s*([A-Za-z_][A-Za-z0-9_]*|[0-9.]+)"
)


def parse_location_templates(path):
    locations = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = LOCATION_ENTRY_RE.match(line)
        if not m:
            continue
        loc, body = m.group(1), m.group(2)
        entry = {}
        for field, regex in [
            ("raw_material", RAW_MATERIAL_RE),
            ("topography", TOPOGRAPHY_RE),
            ("vegetation", VEGETATION_RE),
            ("climate", CLIMATE_RE),
        ]:
            fm = regex.search(body)
            if fm:
                entry[field] = fm.group(1)
        locations[loc] = entry
    return locations


def parse_market_centers(path):
    text = re.sub(r"#[^\n]*", "", path.read_text(encoding="utf-8-sig"))
    return {m.group(1) for m in MARKET_ADD_RE.finditer(text)}


def parse_town_setup_templates(path):
    text = re.sub(r"#[^\n]*", "", path.read_text(encoding="utf-8-sig"))
    templates = {}
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*=\s*\{([^{}]*)\}", text):
        name = m.group(1)
        buildings = {}
        for bm in SETUP_BUILDING_RE.finditer(m.group(2)):
            buildings[bm.group(1)] = int(bm.group(2))
        if buildings:
            templates[name] = buildings
    return templates


def parse_cities_file(path):
    """Parse 07_cities_and_buildings.txt into structured data."""
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    header = []
    loc_entries = []
    bm_lines = []

    in_locations = False
    past_locations = False
    depth = 0

    for line in lines:
        stripped = line.strip()

        if not in_locations and not past_locations:
            if re.match(r"locations\s*=\s*\{", stripped):
                in_locations = True
                depth = 1
                header.append(line)
                continue
            header.append(line)
            continue

        if in_locations:
            open_count = line.count("{")
            close_count = line.count("}")
            depth += open_count - close_count

            if depth <= 0:
                in_locations = False
                past_locations = True
                continue

            cleaned = re.sub(r"#.*", "", stripped).strip()
            if not cleaned:
                comment = stripped if stripped.startswith("#") else ""
                loc_entries.append({
                    "type": "blank_or_comment", "raw": line, "comment": comment,
                })
                continue

            m = re.match(
                r"([a-z_][a-z0-9_]*)\s*=\s*\{([^}]*)\}", cleaned, re.IGNORECASE
            )
            if m:
                loc_name = m.group(1)
                body = m.group(2)
                rank_m = RANK_RE.search(body)
                setup_m = TOWN_SETUP_RE.search(body)
                loc_entries.append({
                    "type": "location",
                    "name": loc_name,
                    "rank": rank_m.group(1) if rank_m else None,
                    "town_setup": setup_m.group(1) if setup_m else None,
                    "raw": line,
                })
            else:
                loc_entries.append({"type": "other", "raw": line})
            continue

        if past_locations:
            bm_lines.append(line)

    return header, loc_entries, bm_lines


def load_building_config(path):
    with open(path) as f:
        entries = json.load(f)
    return {e["name"]: e for e in entries}


def parse_rgo_map(path):
    text = path.read_text(encoding="utf-8-sig")
    compact = re.sub(r"\s+", " ", text)
    return {m.group(1): m.group(2) for m in RGO_MAP_ENTRY_RE.finditer(compact)}


def parse_rgo_pop_types(path):
    text = path.read_text(encoding="utf-8-sig")
    result = {}
    for m in RGO_BUILDING_RE.finditer(text):
        pt = POP_TYPE_RE.search(m.group(2))
        if pt:
            result[m.group(1)] = pt.group(1)
    return result


def parse_pops_structured(path):
    text = path.read_text(encoding="utf-8-sig")
    outer = re.search(r"locations\s*=\s*\{", text)
    if not outer:
        return text, [], ""
    pre_text = text[:outer.end()]
    i = outer.end()
    n = len(text)
    locations = []
    depth = 1
    while i < n and depth > 0:
        c = text[i]
        if c == "{":
            depth += 1
            i += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
            i += 1
        elif depth == 1:
            m = re.match(r"(\s*)([a-z_][a-z0-9_]*)\s*=\s*\{", text[i:], re.IGNORECASE)
            if m:
                leading_ws = m.group(1)
                name = m.group(2)
                header_end = i + m.end()
                inner_depth = 1
                j = header_end
                while j < n and inner_depth > 0:
                    if text[j] == "{":
                        inner_depth += 1
                    elif text[j] == "}":
                        inner_depth -= 1
                    j += 1
                body = text[header_end:j - 1]
                pops = []
                last = 0
                segments = []
                for pm in DEFINE_POP_BLOCK_RE.finditer(body):
                    segments.append(("text", body[last:pm.start()]))
                    fields = {k: v for k, v in POP_FIELD_RE.findall(pm.group(0))}
                    pops.append({
                        "type": fields.get("type", ""),
                        "size": float(fields.get("size", "0")),
                        "culture": fields.get("culture", ""),
                        "religion": fields.get("religion", ""),
                    })
                    segments.append(("pop", len(pops) - 1))
                    last = pm.end()
                segments.append(("text", body[last:]))
                locations.append({
                    "leading_ws": leading_ws,
                    "name": name,
                    "header_suffix": text[i + len(leading_ws) + len(name):header_end],
                    "segments": segments,
                    "pops": pops,
                })
                i = j
            else:
                i += 1
        else:
            i += 1
    post_text = text[i:]
    if post_text and not post_text.startswith(("\n", "\r")):
        post_text = "\n" + post_text
    return pre_text, locations, post_text


# ─────────────────────────────────────────────────────────────────────────────
# Country profiles and east_asia mapping
# ─────────────────────────────────────────────────────────────────────────────


def load_east_asia_locations(vanilla_root):
    defs_file = vanilla_root / "in_game" / "map_data" / "definitions.txt"
    if not defs_file.exists():
        return set()
    text = defs_file.read_text(encoding="utf-8-sig")

    ea_match = re.search(r"\beast_asia\s*=\s*\{", text)
    if not ea_match:
        return set()
    start = ea_match.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    ea_block = text[start:i - 1]

    locations = set()
    for m in re.finditer(r"[a-z_][a-z0-9_]*_province\s*=\s*\{([^}]*)\}", ea_block):
        for loc in re.findall(r"\b([a-z_][a-z0-9_]*)\b", m.group(1)):
            locations.add(loc)
    return locations


def load_country_profiles(vanilla_root):
    countries_file = vanilla_root / "main_menu" / "setup" / "start" / "10_countries.txt"
    templates_dir = vanilla_root / "main_menu" / "setup" / "templates"

    if not countries_file.exists():
        return {}, {}

    template_tech = {}
    if templates_dir.is_dir():
        stl_re = re.compile(r"starting_technology_level\s*=\s*(\d+)")
        for tf in templates_dir.glob("*.txt"):
            ttext = tf.read_text(encoding="utf-8-sig")
            tm = stl_re.search(ttext)
            if tm:
                template_tech[tf.stem] = int(tm.group(1))

    text = re.sub(r"#[^\n]*", "", countries_file.read_text(encoding="utf-8-sig"))

    location_to_owner = {}
    country_profiles = {}

    tag_re = re.compile(r"^\t([A-Z]{3})\s*=\s*\{", re.MULTILINE)
    for tm in tag_re.finditer(text):
        tag = tm.group(1)
        start = tm.end()
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start:i - 1]

        cap_m = re.search(r"\bcapital\s*=\s*([a-z_][a-z0-9_]*)", body)
        capital = cap_m.group(1) if cap_m else None

        tech_m = re.search(r"starting_technology_level\s*=\s*(\d+)", body)
        tech_level = int(tech_m.group(1)) if tech_m else None

        if tech_level is None:
            for inc_m in re.finditer(r'include\s*=\s*"([^"]+)"', body):
                tname = inc_m.group(1)
                if tname in template_tech:
                    tech_level = template_tech[tname]
                    break

        if tech_level is None:
            tech_level = 3

        for loc_key in ["own_control_core", "own_control_integrated",
                        "own_control_conquered", "own_control_colony",
                        "own_core", "own_conquered", "own_integrated",
                        "own_colony", "control_core", "control"]:
            for lm in re.finditer(rf"\b{loc_key}\s*=\s*\{{([^}}]*)\}}", body):
                for loc in re.findall(r"\b([a-z_][a-z0-9_]*)\b", lm.group(1)):
                    if loc != loc_key:
                        location_to_owner[loc] = tag

        country_profiles[tag] = {
            "capital": capital,
            "tech_level": tech_level,
        }

    return location_to_owner, country_profiles


def assign_country_profile_keys(country_profiles, east_asia_locations):
    for tag, prof in country_profiles.items():
        capital = prof.get("capital")
        in_east_asia = capital in east_asia_locations if capital else False
        if prof["tech_level"] < 1:
            prof["profile"] = "tech0"
        elif prof["tech_level"] < 2:
            prof["profile"] = "tech1"
        elif in_east_asia:
            prof["profile"] = "east_asia"
        else:
            prof["profile"] = "default"


# ─────────────────────────────────────────────────────────────────────────────
# Spec and building validity
# ─────────────────────────────────────────────────────────────────────────────


def determine_spec(loc_key, loc_data, market_centers):
    if loc_key in market_centers:
        return "commercial"
    rm = loc_data.get("raw_material")
    if rm and rm in GOODS_TO_SPEC:
        return GOODS_TO_SPEC[rm]
    return "commercial"


def building_spec(config):
    specs = config.get("specs")
    if specs:
        return set(specs)
    return set(SPECS)


def building_valid(config, spec, tier):
    if not config:
        return False
    if tier not in config.get("tiers", []):
        return False
    return spec in building_spec(config)


def building_available_for_profile(cfg, profile):
    if cfg.get("is_foreign") or cfg.get("is_special"):
        return False
    if cfg.get("has_obsolete"):
        return False
    if cfg.get("country_potential"):
        return False
    if cfg.get("estate"):
        return False

    unlock_age = cfg.get("unlock_age")
    if unlock_age is not None and unlock_age > 1:
        return False

    min_tech = cfg.get("unlock_min_tech", 0)
    if min_tech > PROFILE_TECH_LEVEL.get(profile, 3):
        return False

    if profile != "east_asia":
        if cfg.get("unlock_requires_east_asia"):
            return False

    return True


def determine_tier(template_name):
    if "city" in template_name or "capital" in template_name:
        return "city"
    return "town"


# ─────────────────────────────────────────────────────────────────────────────
# Template variant generation
# ─────────────────────────────────────────────────────────────────────────────


REPLACEMENT_CATEGORIES = {
    "basic_industry_category",
    "consumer_goods_category",
    "weapons_industry_category",
    "village_category",
}
REPLACEMENT_NAMES = {
    "marketplace", "merchants_quarters", "grand_marketplace", "commerce_center",
}


def get_replacement_pool(bldg_configs, spec, tier, pop_type, profile="default"):
    pool = []
    for name, cfg in bldg_configs.items():
        if cfg.get("pop_type") != pop_type:
            continue
        cat = cfg.get("category", "")
        if cat not in REPLACEMENT_CATEGORIES and name not in REPLACEMENT_NAMES:
            continue
        if not building_valid(cfg, spec, tier):
            continue
        if not building_available_for_profile(cfg, profile):
            continue
        pool.append(name)
    return sorted(pool)


def _is_production_building(name, cfg):
    cat = cfg.get("category", "")
    return cat in REPLACEMENT_CATEGORIES or name in REPLACEMENT_NAMES


def create_variant(template_buildings, spec, tier, bldg_configs, profile="default"):
    """Create one spec variant of a vanilla template.

    Returns dict {building: level} preserving per-pop-type level totals.
    Production building levels are pooled and redistributed evenly across
    all valid production buildings for the spec. Non-production buildings
    are kept from vanilla if valid, or dropped.
    """
    kept = {}
    production_budget = defaultdict(int)

    for building, level in template_buildings.items():
        config = bldg_configs.get(building)
        if config is None:
            kept[building] = level
            continue

        is_prod = _is_production_building(building, config)

        if is_prod:
            pop = config.get("pop_type", "burghers")
            production_budget[pop] += level
        elif building_valid(config, spec, tier):
            kept[building] = level

    unfilled = {}
    distributed = {}
    for pop_type, total_levels in production_budget.items():
        pool = get_replacement_pool(bldg_configs, spec, tier, pop_type, profile)
        if not pool:
            fallback_pt = POP_TYPE_FALLBACK.get(pop_type)
            if fallback_pt:
                pool = get_replacement_pool(bldg_configs, spec, tier, fallback_pt, profile)
            if not pool:
                unfilled[pop_type] = total_levels
                continue
        base, extra = divmod(total_levels, len(pool))
        for i, bldg in enumerate(pool):
            lvl = base + (1 if i < extra else 0)
            if lvl > 0:
                distributed[bldg] = lvl

    result = dict(kept)
    result.update(distributed)

    village_bldg = VILLAGE_BY_SPEC.get(spec)
    if village_bldg and village_bldg not in result:
        result[village_bldg] = VILLAGE_LEVEL_BY_TIER.get(tier, 1)

    return result, unfilled


# ─────────────────────────────────────────────────────────────────────────────
# Pop shift logic (RGO only)
# ─────────────────────────────────────────────────────────────────────────────


def shift_pops(pops, from_type, to_type, amount):
    if amount <= 0 or from_type == to_type:
        return
    donors = sorted(
        [p for p in pops if p["type"] == from_type],
        key=lambda p: p["size"], reverse=True,
    )
    remaining = amount
    for p in donors:
        if remaining <= 0:
            break
        take = min(remaining, p["size"])
        if take <= 0:
            continue
        p["size"] -= take
        remaining -= take
        target = next(
            (q for q in pops if q["type"] == to_type
             and q["culture"] == p["culture"]
             and q["religion"] == p["religion"]),
            None,
        )
        if target:
            target["size"] += take
        else:
            pops.append({
                "type": to_type, "size": take,
                "culture": p["culture"], "religion": p["religion"],
                "new": True,
            })


# ─────────────────────────────────────────────────────────────────────────────
# Output emitters
# ─────────────────────────────────────────────────────────────────────────────


def emit_town_setups(out_path, variants):
    lines = [
        "# Generated by tools/generate_setup.py — do not hand-edit.",
        "# Specialization variants of vanilla town_setup templates.",
        "",
    ]
    for name, buildings in sorted(variants.items()):
        lines.append(f"{name} = {{")
        for bldg, level in sorted(buildings.items()):
            lines.append(f"\t{bldg} = {level}")
        lines.append("}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def emit_cities_override(out_path, header, loc_entries, bm_lines,
                         all_loc_specs, templates, loc_profiles=None,
                         bldg_configs=None):
    if loc_profiles is None:
        loc_profiles = {}
    emitted = set()
    lines = list(header)

    for entry in loc_entries:
        if entry["type"] != "location":
            lines.append(entry["raw"])
            continue

        loc_name = entry["name"]
        rank = entry["rank"]
        old_setup = entry["town_setup"]
        spec = all_loc_specs.get(loc_name)
        emitted.add(loc_name)

        if spec:
            tier = RANK_SUFFIX.get(rank, "rural") if rank else "rural"
            custom_rank = f"{spec}_{tier}"
            line = entry["raw"]
            if rank:
                line = re.sub(
                    r"rank\s*=\s*[a-z_][a-z0-9_]*",
                    f"rank = {custom_rank}",
                    line,
                )
            else:
                line = re.sub(
                    r"\}",
                    f"rank = {custom_rank} }}",
                    line,
                    count=1,
                )
            if old_setup:
                profile = loc_profiles.get(loc_name, "default")
                prof_name = f"{old_setup}_{spec}_{profile}"
                default_name = f"{old_setup}_{spec}"
                new_setup = prof_name if prof_name in templates else default_name
                if new_setup in templates:
                    line = re.sub(
                        r"town_setup\s*=\s*[a-z_][a-z0-9_]*",
                        f"town_setup = {new_setup}",
                        line,
                    )
            lines.append(line)
            continue

        lines.append(entry["raw"])

    rural_lines = []
    for loc_name, spec in sorted(all_loc_specs.items()):
        if loc_name in emitted:
            continue
        rural_lines.append(f"\t{loc_name} = {{ rank = {spec}_rural }}")

    if rural_lines:
        lines.append("")
        lines.append("\t# Rural locations (rank only, no town_setup)")
        lines.extend(rural_lines)

    lines.append("}")

    for bm_line in bm_lines:
        m = BM_ENTRY_RE.match(bm_line)
        if m:
            bldg_name, loc_name = m.group(1), m.group(2)
            cfg = bldg_configs.get(bldg_name) if bldg_configs else None
            loc_spec = all_loc_specs.get(loc_name)
            if cfg and loc_spec and _is_production_building(bldg_name, cfg):
                if not building_valid(cfg, loc_spec, "city"):
                    continue
        lines.append(bm_line)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def emit_rgo_setup(out_path, bm_entries):
    lines = [
        "# Generated by tools/generate_setup.py — do not hand-edit.",
        "# RGO building placement for all locations.",
        "",
        "building_manager = {",
    ]
    for building, loc, tag, level in bm_entries:
        lines.append(f"\t{building} = {{ location = {loc} tag = {tag} level = {level} }}")
    lines.append("}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def emit_rank_setup(out_path, assignments):
    by_rank = defaultdict(list)
    for loc_key, rank_key in assignments.items():
        by_rank[rank_key].append(loc_key)

    lines = [
        "# Generated by tools/generate_setup.py — do not hand-edit.",
        "# Sets every location's custom specialization rank at game start.",
        "",
        "sul_rank_setup_generated = {",
    ]

    for spec in SPECS:
        for tier in TIERS:
            rank_key = f"{spec}_{tier}"
            locs = sorted(by_rank.get(rank_key, []))
            if not locs:
                continue
            lines.append(f"\t# {rank_key} ({len(locs)} locations)")
            for loc in locs:
                lines.append(
                    f"\tlocation:{loc} = {{ change_location_rank = location_rank:{rank_key} }}"
                )
            lines.append("")

    lines.append("}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def format_pop(pop):
    size = pop["size"]
    size_str = f"{size:g}" if size != int(size) else f"{int(size)}"
    return (
        f"define_pop = {{\ttype = {pop['type']}\tsize = {size_str}"
        f"\tculture = {pop['culture']}\treligion = {pop['religion']} }}"
    )


def write_pops_override(out_path, pre_text, locations, post_text):
    parts = [pre_text]
    for loc in locations:
        parts.append(loc["leading_ws"])
        parts.append(loc["name"])
        parts.append(loc["header_suffix"])
        for kind, payload in loc["segments"]:
            if kind == "text":
                parts.append(payload)
            else:
                pop = loc["pops"][payload]
                if pop.get("new") or pop["size"] <= 0:
                    continue
                parts.append(format_pop(pop))
        new_pops = [p for p in loc["pops"] if p.get("new") and p["size"] > 0]
        for np in new_pops:
            parts.append("\t" + format_pop(np) + "\n")
        parts.append("}")
    parts.append(post_text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(parts), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--vanilla", type=Path, default=VANILLA_ROOT)
    ap.add_argument("--mod", type=Path, default=MOD_ROOT)
    args = ap.parse_args()

    # ── Paths ──
    loc_tpl = args.vanilla / "in_game/map_data/location_templates.txt"
    town_setups_file = args.vanilla / "in_game/common/town_setups/00_default.txt"
    markets_file = args.vanilla / "main_menu/setup/start/03_markets.txt"
    pops_file = args.vanilla / "main_menu/setup/start/06_pops.txt"
    cities_file = args.vanilla / "main_menu/setup/start/07_cities_and_buildings.txt"
    countries_file = args.vanilla / "main_menu/setup/start/10_countries.txt"
    rgo_map_file = args.mod / "in_game/common/scripted_effects/sul_init_effects.txt"
    rgo_bldg_file = args.mod / "in_game/common/building_types/sul_rgo_buildings.txt"
    config_file = args.mod / "tools/building_config.json"

    for f in [loc_tpl, town_setups_file, markets_file, pops_file, cities_file,
              countries_file, rgo_map_file, rgo_bldg_file, config_file]:
        if not f.exists():
            sys.exit(f"missing: {f}")

    # ── Load ──
    print("Loading data...")
    loc_data = parse_location_templates(loc_tpl)
    vanilla_templates = parse_town_setup_templates(town_setups_file)
    market_centers = parse_market_centers(markets_file)
    mod_markets_file = args.mod / "main_menu/setup/start/51_sul_markets.txt"
    if mod_markets_file.exists():
        market_centers |= parse_market_centers(mod_markets_file)
    header, loc_entries, bm_lines = parse_cities_file(cities_file)
    bldg_configs = load_building_config(config_file)
    rgo_map = parse_rgo_map(rgo_map_file)
    rgo_pop_types = parse_rgo_pop_types(rgo_bldg_file)

    print(f"  {len(loc_data)} locations, {len(market_centers)} market centers")
    print(f"  {len(vanilla_templates)} vanilla templates, {len(bldg_configs)} building configs")

    # ── Country profiles ──
    print("Loading country profiles...")
    east_asia_locs = load_east_asia_locations(args.vanilla)
    location_to_owner, country_profiles = load_country_profiles(args.vanilla)
    assign_country_profile_keys(country_profiles, east_asia_locs)

    profile_counts = defaultdict(int)
    for prof in country_profiles.values():
        profile_counts[prof["profile"]] += 1
    print(f"  {len(country_profiles)} countries: " +
          ", ".join(f"{p}={c}" for p, c in sorted(profile_counts.items())))
    print(f"  {len(location_to_owner)} owned locations, {len(east_asia_locs)} east_asia locations")

    # ── Location specs and profiles ──
    loc_specs = {}
    for loc_name in loc_data:
        loc_specs[loc_name] = determine_spec(loc_name, loc_data[loc_name], market_centers)
    for mc in market_centers:
        if mc not in loc_specs:
            loc_specs[mc] = "commercial"
    print(f"  {len(loc_specs)} locations with specializations")

    loc_profiles = {}
    for loc_name in loc_specs:
        owner = location_to_owner.get(loc_name)
        if owner and owner in country_profiles:
            loc_profiles[loc_name] = country_profiles[owner]["profile"]
        else:
            loc_profiles[loc_name] = "default"

    # ── Phase 1: Generate template variants ──
    print("\nPhase 1: Generating template variants...")
    all_variants = {}
    stats = defaultdict(int)
    all_unfilled = defaultdict(lambda: defaultdict(int))

    needed_profiles = {"default"}
    for entry in loc_entries:
        if entry.get("type") == "location":
            p = loc_profiles.get(entry["name"])
            if p:
                needed_profiles.add(p)

    for tpl_name, tpl_buildings in sorted(vanilla_templates.items()):
        tier = determine_tier(tpl_name)

        for spec in SPECS:
            default_variant, default_unfilled = create_variant(
                tpl_buildings, spec, tier, bldg_configs, "default")
            default_name = f"{tpl_name}_{spec}"
            all_variants[default_name] = default_variant
            stats["variants_total"] += 1
            if default_unfilled:
                for pt, lvl in default_unfilled.items():
                    all_unfilled[default_name][pt] = lvl
                stats["variants_with_gaps"] += 1

            for prof_key in sorted(needed_profiles - {"default"}):
                prof_variant, prof_unfilled = create_variant(
                    tpl_buildings, spec, tier, bldg_configs, prof_key)
                if prof_variant != default_variant:
                    prof_name = f"{tpl_name}_{spec}_{prof_key}"
                    all_variants[prof_name] = prof_variant
                    stats["variants_total"] += 1
                    stats["profile_variants"] += 1
                    if prof_unfilled:
                        for pt, lvl in prof_unfilled.items():
                            all_unfilled[prof_name][pt] = lvl
                        stats["variants_with_gaps"] += 1

    print(f"  {stats['variants_total']} variants "
          f"({stats.get('profile_variants', 0)} profile-specific)")
    if stats["variants_with_gaps"]:
        print(f"  {stats['variants_with_gaps']} with unfilled budget:")
        for vname, gaps in sorted(all_unfilled.items()):
            for pt, lvl in gaps.items():
                print(f"    {vname}: {pt} needs {lvl} more levels")

    # ── Phase 2: Per-location RGO placement + ranks ──
    print("\nPhase 2: Per-location RGO and ranks...")
    pre_text, locations_list, post_text = parse_pops_structured(pops_file)
    pops_by_loc = {loc["name"]: loc for loc in locations_list}

    rgo_entries = []
    rank_assignments = {}

    for loc_name, tag in sorted(location_to_owner.items()):
        ld = loc_data.get(loc_name, {})
        rm = ld.get("raw_material")
        if not rm:
            continue

        vanilla_rank_entry = next(
            (e for e in loc_entries if e.get("type") == "location" and e["name"] == loc_name),
            None,
        )
        vanilla_rank = vanilla_rank_entry["rank"] if vanilla_rank_entry else "rural_settlement"
        tier = RANK_SUFFIX.get(vanilla_rank, "rural")
        spec = determine_spec(loc_name, ld, market_centers)
        rank_assignments[loc_name] = f"{spec}_{tier}"

        # RGO placement
        rgo_bldg = rgo_map.get(rm)
        if not rgo_bldg:
            continue

        tag_info = country_profiles.get(tag, {})
        if rgo_bldg in TECH_GATED_RGOS and tag_info.get("tech_level", 0) < IRON_WORKING_STL:
            stats["tech_gated_skipped"] += 1
            continue

        pop_entry = pops_by_loc.get(loc_name)
        eligible_pop = sum(
            p["size"] for p in pop_entry["pops"] if p["type"] not in EXCLUDED_POP_TYPES
        ) if pop_entry else 0

        rgo_level = min(LEVEL_CAP, 1 + floor(eligible_pop / RGO_POP_PER_LEVEL))
        if rgo_level > 0:
            rgo_entries.append((rgo_bldg, loc_name, tag, rgo_level))
            stats["rgo_placed"] += 1

            rgo_pt = rgo_pop_types.get(rgo_bldg)
            if rgo_pt and rgo_pt != "peasants" and pop_entry:
                shift_pops(pop_entry["pops"], "peasants", rgo_pt, rgo_level)

    print(f"  {len(rank_assignments)} rank assignments")
    print(f"  {stats.get('rgo_placed', 0)} RGO placements")
    if stats.get("tech_gated_skipped"):
        print(f"  {stats['tech_gated_skipped']} tech-gated RGO skipped")

    # ── Write outputs ──
    print("\nWriting outputs...")
    setups_out = args.output / "in_game/common/town_setups/sul_town_setups.txt"
    cities_out = args.output / "main_menu/setup/start/07_cities_and_buildings.txt"
    rgo_out = args.output / "main_menu/setup/start/50_sul_setup.txt"
    pops_out = args.output / "main_menu/setup/start/06_pops.txt"
    rank_out = args.output / "in_game/common/scripted_effects/sul_rank_setup_generated.txt"

    emit_town_setups(setups_out, all_variants)
    emit_cities_override(cities_out, header, loc_entries, bm_lines,
                         loc_specs, all_variants, loc_profiles, bldg_configs)
    emit_rgo_setup(rgo_out, rgo_entries)
    write_pops_override(pops_out, pre_text, locations_list, post_text)
    emit_rank_setup(rank_out, rank_assignments)

    print(f"  {setups_out}")
    print(f"  {cities_out}")
    print(f"  {rgo_out} ({len(rgo_entries)} entries)")
    print(f"  {pops_out}")
    print(f"  {rank_out} ({len(rank_assignments)} ranks)")


if __name__ == "__main__":
    main()
