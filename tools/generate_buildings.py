#!/usr/bin/env python3
"""
Unified building generator for the SUL 15-rank system.

Pipeline:
  1. Load — vanilla buildings, mod buildings, production methods, rank files, advances
  2. Merge — one MergedBuilding per unique name (INJECT→merged, REPLACE→mod body, etc.)
  3. Classify — single-pass classification (production_gated > spec_locked > universal)
  4. Output — building files, config JSON, diff report, PM localization

Outputs:
  <output>/building_types/sul_rank_flag_injects.txt  — rank INJECTs for vanilla
  <output>/sul_building_types/<mod_file>.txt          — converted mod files
  <output>/building_config.json                       — building catalog for setup generator
  stdout                                              — diff report

Usage:
    python tools/generate_buildings.py --output /tmp/sul_build_test [--report-only]
"""

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field as dc_field
from pathlib import Path

MOD_ROOT = Path(__file__).resolve().parent.parent
VANILLA_BUILDING_DIR = Path(
    "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V"
    "/game/in_game/common/building_types"
)
MOD_BUILDING_DIR = MOD_ROOT / "in_game" / "common" / "building_types"

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SPECS = ["mining", "farming", "gathering", "woodland", "commercial"]
TIERS = ["rural", "town", "city"]
ALL_CUSTOM_RANKS = [f"{s}_{t}" for s in SPECS for t in TIERS]
OLD_RANK_NAMES = {"rural_settlement", "town", "city"}

SPEC_TRIGGER_MAP = {
    "sul_has_mining_specialization": "mining",
    "sul_has_farming_specialization": "farming",
    "sul_has_gathering_specialization": "gathering",
    "sul_has_woodland_specialization": "woodland",
    "sul_has_commercial_specialization": "commercial",
}

GOODS_TO_PRODUCTION_FLAG = {
    "tools": "sul_allows_tools_production",
    "weaponry": "sul_allows_weapons_production",
    "cannons": "sul_allows_cannon_production",
    "firearms": "sul_allows_firearms_production",
    "jewelry": "sul_allows_jewelry_production",
    "steel": "sul_allows_steel_production",
    "beer": "sul_allows_beer_production",
    "wine": "sul_allows_wine_production",
    "liquor": "sul_allows_liquor_production",
    "leather": "sul_allows_leather_production",
    "glass": "sul_allows_glass_production",
    "pottery": "sul_allows_pottery_production",
    "porcelain": "sul_allows_porcelain_production",
    "saltpeter": "sul_allows_saltpeter_production",
    "medicaments": "sul_allows_apothecary_production",
    "furniture": "sul_allows_furniture_production",
    "paper": "sul_allows_paper_production",
    "lacquerware": "sul_allows_lacquerware_production",
    "dyes": "sul_allows_dye_production",
    "charcoal": "sul_allows_charcoal_production",
    "incense": "sul_allows_incense_production",
    "books": "sul_allows_printing_production",
    "cloth": "sul_allows_cloth_production",
    "fine_cloth": "sul_allows_fine_cloth_production",
    "naval_supplies": "sul_allows_naval_supplies_production",
}

PRODUCTION_FLAGS = set(GOODS_TO_PRODUCTION_FLAG.values()) | {
    "sul_allows_commerce_buildings",
}

AGE_ORDER = {
    "age_1_traditions": 1, "age_2_renaissance": 2, "age_3_discovery": 3,
    "age_4_reformation": 4, "age_5_absolutism": 5, "age_6_revolutions": 6,
}

PRODUCED_RE = re.compile(r"\bproduced\s*=\s*([a-z_][a-z0-9_]*)")
PM_NAME_RE = re.compile(r"^([a-z_][a-z0-9_]*)\s*=\s*\{", re.MULTILINE)
DIFF_IGNORE_FIELDS = OLD_RANK_NAMES | set(ALL_CUSTOM_RANKS)

RANK_FILES_DIR = MOD_ROOT / "in_game" / "common" / "location_ranks"
MOD_PM_DIR = MOD_ROOT / "in_game" / "common" / "production_methods"
VANILLA_PM_DIR = Path(
    "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V"
    "/game/in_game/common/production_methods"
)
VANILLA_ADVANCE_DIR = Path(
    "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V"
    "/game/in_game/common/advances"
)


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MergedBuilding:
    name: str
    body: str
    fields: dict
    source: str               # "vanilla", "mod_replace", "mod_inject", "mod_new"
    source_file: str
    vanilla_body: str = None
    vanilla_fields: dict = None
    mod_file: str = None      # which mod file it came from (for file output)


@dataclass
class BuildingClass:
    classification: str       # "production_gated", "spec_locked", "universal"
    specs: list = None        # restricted specs, or None for all
    production_flags: list = dc_field(default_factory=list)
    new_ranks: list = dc_field(default_factory=list)
    has_spec_trigger: bool = False
    tiers: list = dc_field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# PDX Parser
# ─────────────────────────────────────────────────────────────────────────────

BUILDING_HEADER_RE = re.compile(
    r"^(?:(REPLACE|TRY_REPLACE|REPLACE_OR_CREATE|INJECT|TRY_INJECT|INJECT_OR_CREATE):)?"
    r"([a-z_][a-z0-9_]*)\s*=\s*\{",
    re.MULTILINE | re.IGNORECASE,
)


def _find_block_end(text, start):
    depth, i = 1, start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return i


def parse_file_buildings(text):
    buildings = OrderedDict()
    for m in BUILDING_HEADER_RE.finditer(text):
        prefix = m.group(1) or ""
        name = m.group(2)
        end = _find_block_end(text, m.end())
        buildings[name] = {
            "prefix": prefix, "body": text[m.end():end - 1],
            "raw": text[m.start():end], "name": name,
            "block_start": m.start(), "block_end": end,
        }
    return buildings


def parse_file_buildings_list(text):
    buildings = []
    for m in BUILDING_HEADER_RE.finditer(text):
        prefix = m.group(1) or ""
        name = m.group(2)
        end = _find_block_end(text, m.end())
        buildings.append({
            "prefix": prefix, "body": text[m.end():end - 1],
            "raw": text[m.start():end], "name": name,
            "block_start": m.start(), "block_end": end,
        })
    return buildings


def extract_fields(body):
    fields = {}
    lines = body.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue
        m = re.match(r"([a-z_][a-z0-9_]*)\s*=\s*(.*)", line, re.IGNORECASE)
        if m:
            key, rest = m.group(1), m.group(2).strip()
            if "{" in rest:
                depth = rest.count("{") - rest.count("}")
                block_lines = [rest]
                while depth > 0 and i + 1 < len(lines):
                    i += 1
                    block_lines.append(lines[i].rstrip())
                    depth += lines[i].count("{") - lines[i].count("}")
                value = "\n".join(block_lines)
            else:
                value = rest
            if key in fields:
                if isinstance(fields[key], list):
                    fields[key].append(value)
                else:
                    fields[key] = [fields[key], value]
            else:
                fields[key] = value
        i += 1
    return fields


def normalize_value(v):
    if isinstance(v, list):
        return [normalize_value(x) for x in v]
    return re.sub(r"\s+", " ", str(v)).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Data Loaders
# ─────────────────────────────────────────────────────────────────────────────

def load_production_methods():
    pm_goods = {}
    for d in [VANILLA_PM_DIR, MOD_PM_DIR]:
        if not d.is_dir():
            continue
        for f in d.glob("*.txt"):
            text = f.read_text(encoding="utf-8-sig")
            for m in PM_NAME_RE.finditer(text):
                pm_name = m.group(1)
                end = _find_block_end(text, m.end())
                body = text[m.end():end - 1]
                pm = PRODUCED_RE.search(body)
                if pm:
                    pm_goods[pm_name] = pm.group(1)
    return pm_goods


def load_building_unlocks():
    if not VANILLA_ADVANCE_DIR.is_dir():
        return {}

    advance_data = {}
    for f in sorted(VANILLA_ADVANCE_DIR.glob("*.txt")):
        text = f.read_text(encoding="utf-8-sig")
        for m in re.finditer(r"^([a-z_][a-z0-9_]*)\s*=\s*\{", text, re.MULTILINE):
            name = m.group(1)
            end = _find_block_end(text, m.end())
            body = text[m.end():end - 1]
            age_m = re.search(r"age\s*=\s*([a-z_0-9]+)", body)
            tech_m = re.search(r"starting_technology_level\s*=\s*(\d+)", body)
            req_m = re.search(r"requires\s*=\s*([a-z_][a-z0-9_]*)", body)
            unlocks = re.findall(r"unlock_building\s*=\s*([a-z_][a-z0-9_]*)", body)
            has_ea = bool(re.search(r"sub_continent\s*=\s*sub_continent:east_asia", body))
            advance_data[name] = {
                "age": AGE_ORDER.get(age_m.group(1), 0) if age_m else 0,
                "starting_tech": int(tech_m.group(1)) if tech_m else 0,
                "requires": req_m.group(1) if req_m else None,
                "unlocks": unlocks, "requires_east_asia": has_ea,
            }

    def eff_min_tech(adv_name, visited=None):
        if visited is None:
            visited = set()
        if adv_name not in advance_data or adv_name in visited:
            return 0
        visited.add(adv_name)
        adv = advance_data[adv_name]
        tech = adv["starting_tech"]
        if adv["requires"]:
            tech = max(tech, eff_min_tech(adv["requires"], visited))
        return tech

    result = {}
    for adv_name, adv in advance_data.items():
        for building in adv["unlocks"]:
            result[building] = {
                "age": adv["age"],
                "min_tech": eff_min_tech(adv_name),
                "requires_east_asia": adv["requires_east_asia"],
            }
    return result


def build_flag_to_specs():
    """Read rank definitions and map production flags to the specs that grant them."""
    flag_to_specs = {}
    if not RANK_FILES_DIR.is_dir():
        return flag_to_specs
    rank_name_re = re.compile(r"^([a-z_]+)_(rural|town|city)\s*=\s*\{", re.MULTILINE)
    for f in RANK_FILES_DIR.glob("*.txt"):
        text = f.read_text(encoding="utf-8-sig")
        for m in rank_name_re.finditer(text):
            spec = m.group(1)
            if spec not in SPECS:
                continue
            end = _find_block_end(text, m.end())
            block = text[m.end():end - 1]
            for flag in PRODUCTION_FLAGS:
                if flag in block:
                    flag_to_specs.setdefault(flag, set()).add(spec)
    return flag_to_specs


def get_building_produced_goods(body, pm_goods):
    goods = set()
    for pm in PRODUCED_RE.finditer(body):
        goods.add(pm.group(1))
    ppm_match = re.search(r"possible_production_methods\s*=\s*\{([^}]*)\}", body)
    if ppm_match:
        for ref in re.findall(r"([a-z_][a-z0-9_]*)", ppm_match.group(1)):
            if ref in pm_goods:
                goods.add(pm_goods[ref])
    return goods


def load_vanilla_buildings():
    by_file = OrderedDict()
    for f in sorted(VANILLA_BUILDING_DIR.glob("*.txt")):
        if f.name == "readme.txt":
            continue
        text = f.read_text(encoding="utf-8-sig")
        buildings = parse_file_buildings(text)
        if buildings:
            by_file[f.name] = buildings
    return by_file


def load_mod_buildings():
    mod_buildings = {}
    inject_blocks = defaultdict(list)
    for f in sorted(MOD_BUILDING_DIR.glob("*.txt")):
        if "epbm_generated" in f.name or f.name == "sul_rank_flag_injects.txt":
            continue
        text = f.read_text(encoding="utf-8-sig")
        buildings = parse_file_buildings(text)
        for name, bldg in buildings.items():
            bldg["source_file"] = f.name
            prefix_upper = bldg["prefix"].upper()
            if prefix_upper.startswith("INJECT"):
                inject_blocks[name].append(bldg)
            else:
                mod_buildings[name] = bldg
    return mod_buildings, inject_blocks


# ─────────────────────────────────────────────────────────────────────────────
# Merge Phase
# ─────────────────────────────────────────────────────────────────────────────

def merge_inject_fields(vanilla_fields, inject_fields):
    merged = dict(vanilla_fields)
    for key, val in inject_fields.items():
        if key in DIFF_IGNORE_FIELDS:
            continue
        merged[key] = val
    return merged


def build_merged_buildings(vanilla_by_file, mod_buildings, inject_blocks):
    """Create one MergedBuilding per unique building name."""
    vanilla_all = {}
    vanilla_file_map = {}
    for fname, buildings in vanilla_by_file.items():
        for name, bldg in buildings.items():
            vanilla_all[name] = bldg
            vanilla_file_map[name] = fname

    mod_replace = {n for n, b in mod_buildings.items()
                   if b["prefix"].upper().startswith("REPLACE")}
    mod_new = {n for n, b in mod_buildings.items() if not b["prefix"]}

    result = {}

    # 1. Vanilla buildings modified by REPLACE
    for name in sorted(mod_replace):
        bldg = mod_buildings[name]
        v = vanilla_all.get(name)
        result[name] = MergedBuilding(
            name=name,
            body=bldg["body"],
            fields=extract_fields(bldg["body"]),
            source="mod_replace",
            source_file=bldg["source_file"],
            vanilla_body=v["body"] if v else None,
            vanilla_fields=extract_fields(v["body"]) if v else None,
            mod_file=bldg["source_file"],
        )

    # 2. Vanilla buildings modified by INJECT
    for name in sorted(inject_blocks.keys()):
        if name in result:
            continue
        v = vanilla_all.get(name)
        if not v:
            print(f"  WARNING: INJECT target '{name}' not found in vanilla, skipping")
            continue
        v_fields = extract_fields(v["body"])
        combined_inject = {}
        inject_bodies = []
        for inj in inject_blocks[name]:
            combined_inject.update(extract_fields(inj["body"]))
            inject_bodies.append(inj["body"])
        merged_fields = merge_inject_fields(v_fields, combined_inject)
        combined_body = v["body"] + "\n" + "\n".join(inject_bodies)
        sources = sorted(set(inj["source_file"] for inj in inject_blocks[name]))
        result[name] = MergedBuilding(
            name=name,
            body=combined_body,
            fields=merged_fields,
            source="mod_inject",
            source_file=sources[0],
            vanilla_body=v["body"],
            vanilla_fields=v_fields,
            mod_file=sources[0],
        )

    # 3. Vanilla buildings untouched by mod
    for name, bldg in sorted(vanilla_all.items()):
        if name in result:
            continue
        v_fields = extract_fields(bldg["body"])
        result[name] = MergedBuilding(
            name=name,
            body=bldg["body"],
            fields=v_fields,
            source="vanilla",
            source_file=vanilla_file_map[name],
            vanilla_body=bldg["body"],
            vanilla_fields=v_fields,
        )

    # 4. New mod buildings (no vanilla counterpart)
    for name in sorted(mod_new - set(vanilla_all.keys())):
        bldg = mod_buildings[name]
        result[name] = MergedBuilding(
            name=name,
            body=bldg["body"],
            fields=extract_fields(bldg["body"]),
            source="mod_new",
            source_file=bldg["source_file"],
            mod_file=bldg["source_file"],
        )

    return result, vanilla_all, vanilla_file_map


# ─────────────────────────────────────────────────────────────────────────────
# Classification Engine
# ─────────────────────────────────────────────────────────────────────────────

def get_old_rank_flags(fields):
    flags = {}
    for rank_name in OLD_RANK_NAMES:
        if rank_name in fields:
            val = fields[rank_name]
            if isinstance(val, list):
                val = val[-1]
            flags[rank_name] = val.strip().lower() == "yes"
    return flags


def _specs_from_custom_ranks(fields):
    """Derive spec restriction from existing custom rank flags in fields."""
    found_specs = set()
    for rank in ALL_CUSTOM_RANKS:
        if rank in fields:
            val = fields[rank]
            if isinstance(val, list):
                val = val[-1]
            if val.strip().lower() == "yes":
                spec = rank.rsplit("_", 1)[0]
                found_specs.add(spec)
    return sorted(found_specs) if found_specs else None


def _tiers_from_custom_ranks(fields):
    """Derive tier availability from existing custom rank flags."""
    found_tiers = set()
    for rank in ALL_CUSTOM_RANKS:
        if rank in fields:
            val = fields[rank]
            if isinstance(val, list):
                val = val[-1]
            if val.strip().lower() == "yes":
                tier = rank.rsplit("_", 1)[1]
                found_tiers.add(tier)
    return found_tiers


def compute_new_rank_flags(classification, specs, old_flags):
    has_any = bool(old_flags)
    default = not has_any
    allow_rural = old_flags.get("rural_settlement", default)
    allow_town = old_flags.get("town", default)
    allow_city = old_flags.get("city", default)

    target_specs = specs if (classification == "spec_locked" and specs) else SPECS


    ranks = []
    for s in target_specs:
        if allow_rural:
            ranks.append(f"{s}_rural")
        if allow_town:
            ranks.append(f"{s}_town")
        if allow_city:
            ranks.append(f"{s}_city")
    return ranks


def classify_building(bldg, pm_goods, flag_to_specs):
    """
    Single-pass classification. Priority:
      1. Produced goods → production flags → production_gated
      2. Body references production flag modifiers → production_gated
      3. Spec triggers in body → spec_locked
      4. Existing custom rank flags (narrow) → spec_locked
      5. Otherwise → universal
    """
    body = bldg.body
    fields = bldg.fields

    # Step 0: RGO buildings are gated by can_build_RGO (raw_material check),
    # never by production flags — classify as universal.
    if "can_build_RGO" in body:
        tier_source = bldg.vanilla_fields if bldg.vanilla_fields else fields
        old_flags = get_old_rank_flags(tier_source)
        if not old_flags:
            custom_tiers = _tiers_from_custom_ranks(fields)
            if custom_tiers:
                old_flags = {
                    "rural_settlement": "rural" in custom_tiers,
                    "town": "town" in custom_tiers,
                    "city": "city" in custom_tiers,
                }
        new_ranks = compute_new_rank_flags("universal", None, old_flags)
        tiers = []
        if any(r.endswith("_rural") for r in new_ranks):
            tiers.append("rural")
        if any(r.endswith("_town") for r in new_ranks):
            tiers.append("town")
        if any(r.endswith("_city") for r in new_ranks):
            tiers.append("city")
        return BuildingClass(
            classification="universal",
            specs=None,
            production_flags=[],
            has_spec_trigger=False,
            new_ranks=new_ranks,
            tiers=tiers,
        )

    # Step 1: Produced goods → production flags
    produced_goods = get_building_produced_goods(body, pm_goods)
    prod_flags = []
    for good in sorted(produced_goods):
        if good in GOODS_TO_PRODUCTION_FLAG:
            flag = GOODS_TO_PRODUCTION_FLAG[good]
            if flag not in prod_flags:
                prod_flags.append(flag)

    # Step 2: Also check body for existing modifier:flag references
    for flag in PRODUCTION_FLAGS:
        if f"modifier:{flag}" in body and flag not in prod_flags:
            prod_flags.append(flag)

    # Step 3: Check for spec triggers
    spec_trigger_specs = []
    for trigger, spec in SPEC_TRIGGER_MAP.items():
        if trigger in body:
            spec_trigger_specs.append(spec)
    has_spec_trigger = bool(spec_trigger_specs)

    # Step 4: Classify with priority
    if prod_flags:
        classification = "production_gated"
        specs_set = set()
        for pf in prod_flags:
            specs_set |= flag_to_specs.get(pf, set())
        specs = sorted(specs_set) if specs_set else None
    elif has_spec_trigger:
        classification = "spec_locked"
        specs = spec_trigger_specs
    else:
        # Fallback: check existing custom rank flags for narrow spec restriction
        rank_specs = _specs_from_custom_ranks(fields)
        if rank_specs and set(rank_specs) != set(SPECS):
            classification = "spec_locked"
            specs = rank_specs
        else:
            classification = "universal"
            specs = None

    # Step 5: Determine tier availability
    # Prefer vanilla fields (stable source), then custom ranks, then default
    tier_source = bldg.vanilla_fields if bldg.vanilla_fields else fields
    old_flags = get_old_rank_flags(tier_source)
    if not old_flags:
        custom_tiers = _tiers_from_custom_ranks(fields)
        if custom_tiers:
            old_flags = {
                "rural_settlement": "rural" in custom_tiers,
                "town": "town" in custom_tiers,
                "city": "city" in custom_tiers,
            }

    # Step 6: Compute rank flags
    new_ranks = compute_new_rank_flags(classification, specs, old_flags)

    tiers = []
    if any(r.endswith("_rural") for r in new_ranks):
        tiers.append("rural")
    if any(r.endswith("_town") for r in new_ranks):
        tiers.append("town")
    if any(r.endswith("_city") for r in new_ranks):
        tiers.append("city")

    return BuildingClass(
        classification=classification,
        specs=specs,
        production_flags=prod_flags,
        new_ranks=new_ranks,
        has_spec_trigger=has_spec_trigger,
        tiers=tiers,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Diff Engine
# ─────────────────────────────────────────────────────────────────────────────

def diff_fields(vanilla_fields, mod_fields):
    all_keys = (set(vanilla_fields.keys()) | set(mod_fields.keys())) - DIFF_IGNORE_FIELDS
    added, modified, removed = [], [], []
    for key in sorted(all_keys):
        v_val = vanilla_fields.get(key)
        m_val = mod_fields.get(key)
        if v_val is None:
            added.append(key)
        elif m_val is None:
            removed.append(key)
        elif normalize_value(v_val) != normalize_value(m_val):
            modified.append(key)
    return added, modified, removed


def compute_signature(added, modified, removed):
    if not added and not modified and not removed:
        return ""
    chars = "~" * len(modified) + "+" * len(added) + "-" * len(removed)
    field_str = ",".join(sorted(modified + added + removed))
    hash_val = hashlib.md5(field_str.encode()).hexdigest()[:4]
    return f"{chars} {hash_val}"


def parse_existing_signature(body):
    m = re.search(r"#\s*@sul-diff:\s*(.+)", body)
    return m.group(1).strip() if m else None


# ─────────────────────────────────────────────────────────────────────────────
# Body Transformer
# ─────────────────────────────────────────────────────────────────────────────

SPEC_TRIGGER_LINE_RE = re.compile(
    r"^\s*sul_has_(?:mining|farming|gathering|woodland|commercial)"
    r"_specialization\s*=\s*yes\s*$"
)
ANY_RANK_FLAG_RE = re.compile(
    r"^\t(?:rural_settlement|town|city|"
    + "|".join(re.escape(r) for r in ALL_CUSTOM_RANKS)
    + r")\s*=\s*(?:yes|no)\s*$"
)


def _strip_spec_triggers(lines):
    """Remove sul_has_X_specialization lines from a list of lines."""
    return [l for l in lines if not SPEC_TRIGGER_LINE_RE.match(l)]


def _collapse_empty_blocks(lines):
    """Collapse empty OR/AND/NOT/etc. wrapper blocks."""
    for _ in range(5):
        new_lines, changed = [], False
        j = 0
        while j < len(lines):
            s = lines[j].strip()
            if re.match(r"(?:OR|AND|NAND|NOR|NOT)\s*=\s*\{", s):
                blk = [lines[j]]
                d = s.count("{") - s.count("}")
                j += 1
                while j < len(lines) and d > 0:
                    blk.append(lines[j])
                    d += lines[j].count("{") - lines[j].count("}")
                    j += 1
                inner = "\n".join(blk[1:]).rstrip()
                if inner.endswith("}"):
                    inner = inner[:-1]
                if not inner.strip():
                    changed = True
                    continue
                new_lines.extend(blk)
            else:
                new_lines.append(lines[j])
                j += 1
        lines = new_lines
        if not changed:
            break
    return lines


def _is_lp_empty(lines):
    """Check if a location_potential block is empty (only braces/whitespace)."""
    content = "\n".join(lines)
    inner = re.sub(r"^\s*location_potential\s*=\s*\{", "", content, count=1).rstrip()
    if inner.endswith("}"):
        inner = inner[:-1]
    return not inner.strip()


def _build_modifier_block(flags):
    """Build an OR block for production flag checks."""
    parts = []
    for flag in flags:
        parts.append(f"\t\t\tmodifier:{flag} = yes")
        parts.append(f"\t\t\thas_variable = {flag}")
    return "\t\tOR = {\n" + "\n".join(parts) + "\n\t\t}"


def transform_location_potential(body, cls):
    """Transform location_potential based on classification.

    production_gated: strip spec triggers, add modifier OR block if not present
    spec_locked: strip spec triggers entirely, remove empty LP
    universal: no changes
    """
    if cls.classification == "universal":
        return body

    lines = body.split("\n")
    result = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if re.match(r"location_potential\s*=\s*\{", stripped):
            # Collect the full location_potential block
            lp_lines = [lines[i]]
            depth = stripped.count("{") - stripped.count("}")
            i += 1
            while i < len(lines) and depth > 0:
                lp_lines.append(lines[i])
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1

            # Strip spec triggers
            cleaned = _strip_spec_triggers(lp_lines)
            cleaned = _collapse_empty_blocks(cleaned)

            if cls.classification == "production_gated":
                # Check if modifier is already present
                lp_text = "\n".join(cleaned)
                needs_modifier = all(
                    f"modifier:{f}" not in lp_text for f in cls.production_flags
                )

                if needs_modifier and cls.production_flags:
                    modifier_block = _build_modifier_block(cls.production_flags)
                    # Insert before closing brace
                    for idx in range(len(cleaned) - 1, -1, -1):
                        if cleaned[idx].strip() == "}":
                            cleaned.insert(idx, modifier_block)
                            break

                # If LP was empty (only had spec triggers), create fresh with modifier
                if _is_lp_empty(_strip_spec_triggers(lp_lines)):
                    if cls.production_flags:
                        modifier_block = _build_modifier_block(cls.production_flags)
                        result.append("\tlocation_potential = {")
                        result.append(modifier_block)
                        result.append("\t}")
                    # else: drop the empty LP entirely
                else:
                    result.extend(cleaned)

            elif cls.classification == "spec_locked":
                if not _is_lp_empty(cleaned):
                    result.extend(cleaned)
                # else: drop the empty LP entirely

            continue
        result.append(lines[i])
        i += 1

    # Only add location_potential if we stripped spec triggers that need replacing
    if (cls.classification == "production_gated" and cls.production_flags
            and cls.has_spec_trigger):
        result_text = "\n".join(result)
        if "location_potential" not in result_text:
            modifier_block = _build_modifier_block(cls.production_flags)
            idx = result_text.rfind("}")
            if idx > 0:
                lp_block = (
                    f"\n\tlocation_potential = {{\n"
                    f"{modifier_block}\n"
                    f"\t}}\n"
                )
                return result_text[:idx] + lp_block + result_text[idx:]

    return "\n".join(result)


def replace_rank_flags(body, new_ranks):
    """Replace all old and custom rank flags with new_ranks."""
    lines = body.split("\n")
    new_lines = []
    inserted = False
    for line in lines:
        if ANY_RANK_FLAG_RE.match(line):
            if not inserted:
                ordered = sorted(
                    new_ranks,
                    key=lambda r: ALL_CUSTOM_RANKS.index(r)
                    if r in ALL_CUSTOM_RANKS else 999,
                )
                for r in ordered:
                    new_lines.append(f"\t{r} = yes")
                inserted = True
        else:
            new_lines.append(line)

    return "\n".join(new_lines)


def transform_body(body, cls, pm_goods):
    """Full body transformation: rank flags + location_potential."""
    result = replace_rank_flags(body, cls.new_ranks)
    result = transform_location_potential(result, cls)
    return result


def rename_inline_pms(body):
    """Rename vanilla PM names in unique_production_methods to sul_ prefix."""
    renames = {}
    pm_header_re = re.compile(r"^(\s*)([a-z_][a-z0-9_]*)\s*=\s*\{", re.MULTILINE)
    upm_re = re.compile(r"unique_production_methods\s*=\s*\{")
    positions = list(upm_re.finditer(body))
    if not positions:
        return body, renames

    result = body
    PM_SKIP = {
        "unique_production_methods", "potential", "allow", "limit",
        "owner", "category", "modifier", "trigger", "effect",
        "location_potential", "country_potential",
        "custom_tooltip", "NOT", "OR", "AND", "if", "else",
    }
    for m in reversed(positions):
        start = m.start()
        depth, i = 0, m.end()
        while i < len(result):
            if result[i] == "{":
                depth += 1
            elif result[i] == "}":
                if depth == 0:
                    break
                depth -= 1
            i += 1
        block = result[start:i + 1]

        def rename_one(pm_match):
            indent, pm_name = pm_match.group(1), pm_match.group(2)
            if pm_name in PM_SKIP or pm_name.startswith("sul_"):
                return pm_match.group(0)
            new_name = f"sul_{pm_name}"
            renames[pm_name] = new_name
            return f"{indent}{new_name} = {{"

        new_block = pm_header_re.sub(rename_one, block)
        result = result[:start] + new_block + result[i + 1:]

    return result, renames


# ─────────────────────────────────────────────────────────────────────────────
# Config Builder
# ─────────────────────────────────────────────────────────────────────────────

def _field_str(fields, key, default=""):
    val = fields.get(key, default)
    if isinstance(val, list):
        val = val[-1]
    return val.strip() if isinstance(val, str) else str(val)


def build_config_entry(bldg, cls, building_unlocks):
    entry = {
        "name": bldg.name,
        "source_file": bldg.source_file,
        "classification": cls.classification,
        "pop_type": _field_str(bldg.fields, "pop_type"),
        "max_levels": _field_str(bldg.fields, "max_levels"),
        "employment_size": _field_str(bldg.fields, "employment_size"),
        "category": _field_str(bldg.fields, "category"),
        "tiers": cls.tiers,
    }

    if cls.specs:
        entry["specs"] = cls.specs

    if _field_str(bldg.fields, "is_special").lower() == "yes":
        entry["is_special"] = True
    if _field_str(bldg.fields, "is_foreign").lower() == "yes":
        entry["is_foreign"] = True
    if "country_potential" in bldg.fields:
        entry["country_potential"] = True

    estate_val = _field_str(bldg.fields, "estate")
    if estate_val:
        entry["estate"] = estate_val

    obsolete_val = _field_str(bldg.fields, "obsolete")
    if obsolete_val:
        entry["has_obsolete"] = True

    if building_unlocks and bldg.name in building_unlocks:
        unlock = building_unlocks[bldg.name]
        entry["unlock_age"] = unlock["age"]
        entry["unlock_min_tech"] = unlock["min_tech"]
        if unlock["requires_east_asia"]:
            entry["unlock_requires_east_asia"] = True

    return entry


# ─────────────────────────────────────────────────────────────────────────────
# Output: Converted Mod Files
# ─────────────────────────────────────────────────────────────────────────────

def fields_to_body(fields, indent="\t"):
    lines = []
    for key, val in fields.items():
        if isinstance(val, list):
            for v in val:
                lines.append(f"{indent}{key} = {v}")
        else:
            lines.append(f"{indent}{key} = {val}")
    return "\n".join(lines)


def rebuild_building_text(name, fields, new_ranks, sig=None, replace_prefix=False):
    lines = []
    if sig:
        lines.append(f"# @sul-diff: {sig}")
    prefix = "REPLACE:" if replace_prefix else ""
    lines.append(f"{prefix}{name} = {{")

    rank_written = False
    for key, val in fields.items():
        if key in OLD_RANK_NAMES:
            if not rank_written:
                ordered = sorted(
                    new_ranks,
                    key=lambda r: ALL_CUSTOM_RANKS.index(r)
                    if r in ALL_CUSTOM_RANKS else 999,
                )
                for r in ordered:
                    lines.append(f"\t{r} = yes")
                rank_written = True
            continue
        if key in set(ALL_CUSTOM_RANKS):
            continue
        if isinstance(val, list):
            for v in val:
                lines.append(f"\t{key} = {v}")
        else:
            lines.append(f"\t{key} = {val}")

    if not rank_written and new_ranks:
        ordered = sorted(
            new_ranks,
            key=lambda r: ALL_CUSTOM_RANKS.index(r)
            if r in ALL_CUSTOM_RANKS else 999,
        )
        for r in ordered:
            lines.append(f"\t{r} = yes")

    lines.append("}")
    return "\n".join(lines)


def generate_mod_files(output_dir, all_buildings, classifications, pm_goods,
                       mod_buildings, inject_blocks, vanilla_all):
    """Generate converted mod building files."""
    sul_out = output_dir / "sul_building_types"
    sul_out.mkdir(parents=True, exist_ok=True)

    all_pm_renames = {}
    files_written = 0

    # Pre-compute conversion data for INJECT and REPLACE buildings
    convert_data = {}
    for name, bldg in all_buildings.items():
        cls = classifications[name]
        if bldg.source == "mod_inject" and bldg.vanilla_fields:
            v_fields = bldg.vanilla_fields
            added, modified, removed = diff_fields(v_fields, bldg.fields)
            sig = compute_signature(added, modified, removed)
            convert_data[name] = {
                "merged_fields": bldg.fields,
                "new_ranks": cls.new_ranks,
                "sig": sig,
                "cls": cls,
            }
        elif bldg.source == "mod_replace" and bldg.vanilla_fields:
            v_fields = bldg.vanilla_fields
            added, modified, removed = diff_fields(v_fields, bldg.fields)
            sig = compute_signature(added, modified, removed)
            convert_data[name] = {
                "merged_fields": bldg.fields,
                "new_ranks": cls.new_ranks,
                "sig": sig,
                "cls": cls,
            }

    for f in sorted(MOD_BUILDING_DIR.glob("*.txt")):
        if "epbm_generated" in f.name or f.name == "sul_rank_flag_injects.txt":
            continue
        text = f.read_text(encoding="utf-8-sig")
        buildings = parse_file_buildings_list(text)
        if not buildings:
            continue

        result = text
        for bldg_block in reversed(buildings):
            name = bldg_block["name"]
            prefix = bldg_block["prefix"]
            prefix_upper = prefix.upper() if prefix else ""

            if name in convert_data:
                cd = convert_data[name]
                cls = cd["cls"]

                if prefix_upper.startswith("INJECT"):
                    continue

                elif prefix_upper.startswith("REPLACE"):
                    body = bldg_block["body"]
                    new_body = transform_body(body, cls, pm_goods)
                    sig_line = f"# @sul-diff: {cd['sig']}\n" if cd["sig"] else ""
                    new_text = f"{sig_line}REPLACE:{name} = {{{new_body}}}"
                    new_text, pm_renames = rename_inline_pms(new_text)
                    all_pm_renames.update(pm_renames)
                else:
                    continue

                result = (result[:bldg_block["block_start"]]
                          + new_text
                          + result[bldg_block["block_end"]:])

            elif not prefix or (prefix_upper.startswith("REPLACE")
                                and name not in vanilla_all):
                if name in classifications:
                    cls = classifications[name]
                    body = bldg_block["body"]
                    old_flags = get_old_rank_flags(extract_fields(body))
                    has_custom = any(r in extract_fields(body) for r in ALL_CUSTOM_RANKS)
                    if old_flags or has_custom:
                        new_body = transform_body(body, cls, pm_goods)
                        out_prefix = "REPLACE:" if prefix_upper.startswith("REPLACE") else ""
                        new_text = f"{out_prefix}{name} = {{{new_body}}}"
                        result = (result[:bldg_block["block_start"]]
                                  + new_text
                                  + result[bldg_block["block_end"]:])

        out_path = sul_out / f.name
        out_path.write_text(result, encoding="utf-8-sig")
        files_written += 1

    print(f"  Wrote {files_written} converted mod files to {sul_out}/")
    if all_pm_renames:
        print(f"  Renamed {len(all_pm_renames)} inline PMs to sul_ prefix")

    # Validate: count INJECTs in output vs source
    src_inject_count = 0
    out_inject_count = 0
    for f in sorted(MOD_BUILDING_DIR.glob("*.txt")):
        if "epbm_generated" in f.name or f.name == "sul_rank_flag_injects.txt":
            continue
        src_inject_count += f.read_text(encoding="utf-8-sig").count("\nINJECT:")
    for f in sul_out.glob("*.txt"):
        out_inject_count += f.read_text(encoding="utf-8-sig").count("\nINJECT:")
    if out_inject_count < src_inject_count:
        print(f"\n  ERROR: Output has {out_inject_count} INJECT blocks but")
        print(f"  source had {src_inject_count}. INJECTs are being destroyed.")
        print(f"  The copy-back will lose mod INJECT blocks.")
        sys.exit(1)

    return all_pm_renames


def generate_vanilla_injects(output_dir, all_buildings, classifications,
                             vanilla_by_file):
    """Generate INJECT file for rank flags on untouched vanilla buildings."""
    bt_out = output_dir / "building_types"
    bt_out.mkdir(parents=True, exist_ok=True)

    inject_lines = [
        "# Generated by tools/generate_buildings.py — do not hand-edit.",
        "# INJECT blocks that set custom rank flags on vanilla buildings.",
        "",
    ]
    count = 0

    for fname, buildings in sorted(vanilla_by_file.items()):
        file_injects = []
        for name in buildings:
            bldg = all_buildings.get(name)
            if not bldg or bldg.source != "vanilla":
                continue
            cls = classifications[name]
            old_flags = get_old_rank_flags(bldg.vanilla_fields or bldg.fields)

            rank_lines = []
            for old_rank in OLD_RANK_NAMES:
                if old_rank in old_flags:
                    rank_lines.append(f"\t{old_rank} = no")
            for rank in sorted(cls.new_ranks):
                rank_lines.append(f"\t{rank} = yes")

            if rank_lines:
                file_injects.append(f"INJECT:{name} = {{")
                file_injects.extend(rank_lines)
                file_injects.append("}")
                file_injects.append("")
                count += 1

        if file_injects:
            inject_lines.append(f"# {fname}")
            inject_lines.extend(file_injects)

    inject_path = bt_out / "sul_rank_flag_injects.txt"
    inject_path.write_text("\n".join(inject_lines), encoding="utf-8-sig")
    print(f"  Vanilla rank INJECTs: {count} buildings → {inject_path}")
    if count == 0:
        print(f"  ERROR: Generated 0 rank flag INJECTs. Vanilla buildings")
        print(f"  will keep old rank flags and won't match custom location ranks.")
        sys.exit(1)


def generate_pm_localization(output_dir, all_pm_renames):
    if not all_pm_renames:
        return
    vanilla_loc = {}
    vanilla_loc_dir = Path(
        "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V"
        "/game/in_game/localization/english"
    )
    if vanilla_loc_dir.is_dir():
        loc_re = re.compile(r"^\s*([a-z_][a-z0-9_]*):\d*\s*\"(.*)\"", re.MULTILINE)
        for lf in vanilla_loc_dir.glob("*.yml"):
            for lm in loc_re.finditer(lf.read_text(encoding="utf-8-sig")):
                vanilla_loc[lm.group(1)] = lm.group(2)

    loc_lines = ["l_english:"]
    for old_name, new_name in sorted(all_pm_renames.items()):
        display = vanilla_loc.get(old_name, old_name.replace("_", " ").title())
        loc_lines.append(f' {new_name}: "{display}"')

    loc_path = output_dir / "sul_pm_l_english.yml"
    loc_path.write_text("\n".join(loc_lines) + "\n", encoding="utf-8")
    print(f"  PM localization: {len(all_pm_renames)} entries → {loc_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Main Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    # ── Phase 0: Load reference data ──
    print("Loading reference data...")
    pm_goods = load_production_methods()
    print(f"  {len(pm_goods)} PMs with produced goods")

    building_unlocks = load_building_unlocks()
    print(f"  {len(building_unlocks)} buildings with advance unlocks")

    flag_to_specs = build_flag_to_specs()
    print(f"  {len(flag_to_specs)} production flags mapped to specs")
    if not flag_to_specs:
        print("\n  ERROR: flag_to_specs is EMPTY — no rank files found or no")
        print("  production flags in rank definitions. Every production-gated")
        print(f"  building will get specs=None (unrestricted).")
        print(f"  Looked in: {RANK_FILES_DIR}")
        print(f"  Directory exists: {RANK_FILES_DIR.is_dir()}")
        if RANK_FILES_DIR.is_dir():
            print(f"  Files: {[f.name for f in RANK_FILES_DIR.glob('*.txt')]}")
        sys.exit(1)
    unmapped_flags = PRODUCTION_FLAGS - set(flag_to_specs.keys())
    if unmapped_flags:
        print(f"  WARNING: {len(unmapped_flags)} production flags not granted by any rank:")
        for f in sorted(unmapped_flags):
            print(f"    {f}")

    print("Loading buildings...")
    vanilla_by_file = load_vanilla_buildings()
    vanilla_count = sum(len(b) for b in vanilla_by_file.values())
    print(f"  {vanilla_count} vanilla buildings across {len(vanilla_by_file)} files")

    mod_buildings, inject_blocks = load_mod_buildings()
    mod_new = {n for n, b in mod_buildings.items() if not b["prefix"]}
    mod_replace = {n for n, b in mod_buildings.items()
                   if b["prefix"].upper().startswith("REPLACE")}
    print(f"  {len(mod_buildings)} mod buildings "
          f"(new={len(mod_new)}, replace={len(mod_replace)})")
    print(f"  {len(inject_blocks)} vanilla buildings INJECT'd")

    # ── Phase 1: Merge ──
    print("\nMerging buildings...")
    all_buildings, vanilla_all, vanilla_file_map = build_merged_buildings(
        vanilla_by_file, mod_buildings, inject_blocks,
    )
    by_source = defaultdict(int)
    for b in all_buildings.values():
        by_source[b.source] += 1
    print(f"  {len(all_buildings)} unique buildings: "
          + ", ".join(f"{k}={v}" for k, v in sorted(by_source.items())))
    if by_source.get("mod_inject", 0) == 0 and len(inject_blocks) > 0:
        print(f"\n  WARNING: {len(inject_blocks)} INJECT blocks found in source")
        print(f"  but 0 merged as mod_inject. INJECTs may not be loading.")
    if by_source.get("vanilla", 0) == 0:
        print(f"\n  ERROR: 0 vanilla-untouched buildings. This means every")
        print(f"  vanilla building was claimed by a mod INJECT or REPLACE.")
        print(f"  Check that sul_rank_flag_injects.txt is excluded from loading.")

    # ── Phase 2: Classify ──
    print("\nClassifying buildings...")
    classifications = {}
    for name, bldg in all_buildings.items():
        classifications[name] = classify_building(bldg, pm_goods, flag_to_specs)

    by_cls = defaultdict(int)
    no_specs = []
    for name, cls in classifications.items():
        by_cls[cls.classification] += 1
        if cls.classification == "production_gated" and not cls.specs:
            no_specs.append(name)
    print(f"  " + ", ".join(f"{k}={v}" for k, v in sorted(by_cls.items())))
    if no_specs:
        print(f"\n  ERROR: {len(no_specs)} production_gated buildings have NO specs")
        print(f"  (they will be placed in ALL specializations):")
        for n in sorted(no_specs)[:10]:
            cls = classifications[n]
            print(f"    {n}: flags={cls.production_flags}")
        if len(no_specs) > 10:
            print(f"    ... and {len(no_specs) - 10} more")
        sys.exit(1)

    # ── Phase 3a: Diff report ──
    print(f"\n{'='*70}")
    print("DIFF REPORT")
    print(f"{'='*70}")

    for name in sorted(all_buildings.keys()):
        bldg = all_buildings[name]
        if bldg.source not in ("mod_replace", "mod_inject"):
            continue
        if not bldg.vanilla_fields:
            continue

        v_fields = bldg.vanilla_fields
        m_fields = bldg.fields
        added, modified, removed = diff_fields(v_fields, m_fields)
        sig = compute_signature(added, modified, removed)
        existing_sig = parse_existing_signature(bldg.body)

        status = "OK"
        if existing_sig and existing_sig != sig:
            status = "DRIFT"
        elif not existing_sig and sig:
            status = "NEW"

        sig_display = sig or "(none)"
        changes = []
        if modified:
            changes.append(f"~{','.join(modified)}")
        if added:
            changes.append(f"+{','.join(added)}")
        if removed:
            changes.append(f"-{','.join(removed)}")
        change_str = " ".join(changes) if changes else "(rank flags only)"
        src_type = "REPLACE" if bldg.source == "mod_replace" else "INJECT"

        print(f"  [{status:7s}] {src_type:7s} {name:40s} "
              f"{sig_display:16s} {change_str}")

    # ── Phase 3b: Build config ──
    config_entries = []
    for name in sorted(all_buildings.keys()):
        config_entries.append(
            build_config_entry(all_buildings[name], classifications[name],
                               building_unlocks)
        )

    specs_counts = defaultdict(int)
    for e in config_entries:
        if e.get("specs"):
            for s in e["specs"]:
                specs_counts[s] += 1
    print(f"\n  Config: {len(config_entries)} entries")
    if specs_counts:
        print(f"  Spec-restricted buildings: "
              + ", ".join(f"{k}={v}" for k, v in sorted(specs_counts.items())))
    else:
        print(f"  WARNING: No buildings have spec restrictions in config")

    if args.report_only:
        return

    # ── Phase 3c: Generate outputs ──
    print(f"\n{'='*70}")
    print("GENERATING outputs")
    print(f"{'='*70}")

    all_pm_renames = generate_mod_files(
        args.output, all_buildings, classifications, pm_goods,
        mod_buildings, inject_blocks, vanilla_all,
    )

    generate_vanilla_injects(
        args.output, all_buildings, classifications, vanilla_by_file,
    )

    config_path = args.output / "building_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_entries, f, indent=2)
    print(f"  Config JSON: {config_path}")

    generate_pm_localization(args.output, all_pm_renames)


if __name__ == "__main__":
    main()
