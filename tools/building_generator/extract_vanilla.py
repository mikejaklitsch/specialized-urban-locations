#!/usr/bin/env python3
"""
Extract all vanilla EU5 building definitions and goods into a structured JSON catalog.
Uses the pdx_parser module to parse Clausewitz script files.
"""
import json
import sys
from pathlib import Path

# Add parent to path so we can import pdx_parser
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdx_parser import parse_file, get_value, get_values, get_bare_values, block_keys, get_blocks

import platform
_base = r"C:\SteamLibrary\steamapps\common\Europa Universalis V\game\in_game"
if platform.system() != "Windows":
    _base = "/mnt/c/SteamLibrary/steamapps/common/Europa Universalis V/game/in_game"
BASE_GAME = Path(_base)
BUILDING_DIR = BASE_GAME / "common" / "building_types"
GOODS_DIR = BASE_GAME / "common" / "goods"

# SUL specialization mapping
SPEC_MAP = {
    # Mining raw materials
    "iron": "mining", "copper": "mining", "tin": "mining", "lead": "mining",
    "silver": "mining", "goods_gold": "mining", "stone": "mining", "mercury": "mining",
    "coal": "mining", "gems": "mining", "alum": "mining", "marble": "mining",
    # Mining finished goods
    "tools": "mining", "weaponry": "mining", "cannons": "mining", "firearms": "mining",
    "steel": "mining", "jewelry": "mining",
    # Farming raw materials
    "wheat": "farming", "rice": "farming", "millet": "farming", "fruit": "farming",
    "fiber_crops": "farming", "horses": "farming", "sugar": "farming", "cotton": "farming",
    "tobacco": "farming", "livestock": "farming", "maize": "farming", "legumes": "farming",
    "potato": "farming", "olives": "farming", "beeswax": "farming",
    "silk": "farming", "dyes_raw": "farming", "incense": "farming", "tea": "farming",
    "cocoa": "farming", "coffee": "farming", "saffron": "farming", "pepper": "farming",
    "cloves": "farming", "chili": "farming", "wine": "farming",
    # Farming finished goods
    "beer": "farming", "liquor": "farming", "leather": "farming",
    # Gathering raw materials
    "clay": "gathering", "salt": "gathering", "sand": "gathering", "wool": "gathering",
    "saltpeter": "gathering", "fish": "gathering", "pearls": "gathering",
    "amber": "gathering", "medicaments": "gathering",
    # Gathering finished goods
    "glass": "gathering", "pottery": "gathering", "porcelain": "gathering",
    "lacquerware": "gathering", "masonry": "gathering",
    # Woodland raw materials
    "lumber": "woodland", "elephants": "woodland", "wild_game": "woodland",
    "fur": "woodland", "ivory": "woodland",
    # Woodland finished goods
    "paper": "woodland", "furniture": "woodland", "tar": "woodland",
    "dyes": "woodland",
    # Commercial finished goods
    "cloth": "commercial", "fine_cloth": "commercial", "books": "commercial",
    "naval_supplies": "commercial",
}


def extract_trigger_block(block):
    """Convert a trigger/condition block to a simplified dict representation."""
    if not isinstance(block, list):
        return block
    result = {}
    for key, val in block:
        if key.startswith("__"):
            continue
        if isinstance(val, list):
            val = extract_trigger_block(val)
        if key in result:
            # Handle duplicate keys by converting to list
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(val)
        else:
            result[key] = val
    return result


def extract_production_methods(block):
    """Extract production methods from a building definition block."""
    methods = {}

    # unique_production_methods - inline definitions
    upm_blocks = get_blocks(block, "unique_production_methods")
    for upm_block in upm_blocks:
        for method_name, method_body in upm_block:
            if method_name.startswith("__"):
                continue
            if not isinstance(method_body, list):
                continue
            method = {"inputs": {}, "output": {}}
            for mk, mv in method_body:
                if mk.startswith("__"):
                    continue
                if mk == "produced":
                    method["output"]["good"] = mv
                elif mk == "output":
                    method["output"]["amount"] = mv
                elif mk == "category":
                    method["category"] = mv
                elif mk == "debug_max_profit":
                    method["debug_max_profit"] = mv
                else:
                    # Everything else is an input good
                    method["inputs"][mk] = mv
            methods[method_name] = method

    # possible_production_methods - references to external definitions
    ppm_blocks = get_blocks(block, "possible_production_methods")
    for ppm_block in ppm_blocks:
        for ref_name in get_bare_values(ppm_block):
            if isinstance(ref_name, str):
                methods[ref_name] = {"type": "reference"}

    return methods


def extract_modifier(block, key="modifier"):
    """Extract a modifier block as a flat dict."""
    mod_blocks = get_blocks(block, key)
    if not mod_blocks:
        return {}
    result = {}
    for mod_block in mod_blocks:
        for mk, mv in mod_block:
            if mk.startswith("__"):
                continue
            result[mk] = mv
    return result


def extract_building(name, block):
    """Extract all properties from a building definition."""
    building = {"name": name}

    # Simple properties
    simple_props = [
        "is_foreign", "is_special", "max_levels", "pop_type", "category",
        "employment_size", "build_time", "construction_demand", "obsolete",
        "expensive", "rural_settlement", "town", "city", "in_empty",
        "forbidden_for_estates", "is_indestructible", "important_for_UI",
        "important_for_AI", "AI_ignore_available_worker_flag",
        "AI_optimization_flag_coastal", "stronger_power_projection",
        "need_good_relation", "conversion_religion", "always_add_demands",
        "automation_build_allowed", "ai_forbid_shutdown",
    ]
    for prop in simple_props:
        val = get_value(block, prop)
        if val is not None:
            building[prop] = val

    # max_levels can be a block (script value with conditions)
    max_lv = get_value(block, "max_levels")
    if isinstance(max_lv, list):
        building["max_levels"] = extract_trigger_block(max_lv)

    # Rank availability - derive from flags
    ranks = []
    if get_value(block, "rural_settlement") == "yes":
        ranks.append("rural")
    if get_value(block, "town") == "yes":
        ranks.append("town")
    if get_value(block, "city") == "yes":
        ranks.append("city")
    # Default: if no rank flags specified, check if only town/city excluded
    if not ranks:
        rural = get_value(block, "rural_settlement")
        town = get_value(block, "town")
        city = get_value(block, "city")
        if rural == "no" and town == "no" and city != "no":
            ranks = ["city"]
        elif rural == "no" and town != "no" and city != "no":
            ranks = ["town", "city"]
        elif rural is None and town is None and city is None:
            # No rank flags at all - assume town+city as default
            ranks = ["town", "city"]
    building["ranks"] = ranks

    # Trigger blocks
    for trigger_key in ["location_potential", "allow", "country_potential", "remove_if"]:
        trigger_block = get_value(block, trigger_key)
        if isinstance(trigger_block, list):
            building[trigger_key] = extract_trigger_block(trigger_block)

    # Production methods
    methods = extract_production_methods(block)
    if methods:
        building["production_methods"] = methods

    # Modifiers
    for mod_key in ["modifier", "raw_modifier", "capital_modifier", "capital_country_modifier", "market_center_modifier"]:
        mod = extract_modifier(block, mod_key)
        if mod:
            building[mod_key] = mod

    # On built/destroyed effects
    for effect_key in ["on_built", "on_destroyed"]:
        effect_block = get_value(block, effect_key)
        if isinstance(effect_block, list):
            building[effect_key] = extract_trigger_block(effect_block)

    # Custom tags
    ct = get_value(block, "custom_tags")
    if isinstance(ct, list):
        building["custom_tags"] = get_bare_values(ct)

    # Graphical tags
    gt = get_value(block, "graphical_tags")
    if isinstance(gt, list):
        building["graphical_tags"] = get_bare_values(gt)

    # Determine primary produced good and SUL specialization
    produced_good = None
    for method_name, method_data in methods.items():
        if isinstance(method_data, dict) and "output" in method_data:
            good = method_data["output"].get("good")
            if good:
                produced_good = good
                break

    if produced_good:
        building["primary_produced_good"] = produced_good
        sul_spec = SPEC_MAP.get(produced_good)
        if sul_spec:
            building["sul_specialization"] = sul_spec

    # Check location_potential for raw_material requirements
    lp = building.get("location_potential", {})
    raw_materials = []
    _find_raw_materials(lp, raw_materials)
    if raw_materials:
        building["required_raw_materials"] = raw_materials

    return building


def _find_raw_materials(obj, results):
    """Recursively find raw_material = goods:X in a trigger structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "raw_material":
                if isinstance(v, str) and v.startswith("goods:"):
                    results.append(v.replace("goods:", ""))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and item.startswith("goods:"):
                            results.append(item.replace("goods:", ""))
            else:
                _find_raw_materials(v, results)
    elif isinstance(obj, list):
        for item in obj:
            _find_raw_materials(item, results)


def extract_good(name, block):
    """Extract properties from a good definition."""
    good = {"name": name}

    simple_props = [
        "category", "method", "food", "price", "obsolete",
        "base_demand", "demand_slope", "base_supply", "supply_slope",
    ]
    for prop in simple_props:
        val = get_value(block, prop)
        if val is not None:
            good[prop] = val

    # Determine classification
    method = get_value(block, "method")
    category = get_value(block, "category")

    if method:
        good["classification"] = "raw_material"
        good["extraction_method"] = method
    elif category == "produced":
        good["classification"] = "produced"
    else:
        good["classification"] = "other"

    # SUL specialization
    sul_spec = SPEC_MAP.get(name)
    if sul_spec:
        good["sul_specialization"] = sul_spec

    return good


def main():
    print("Extracting vanilla EU5 buildings and goods...")

    # ── Parse all goods files ──
    goods_catalog = {}
    goods_files = sorted(GOODS_DIR.glob("*.txt"))
    print(f"\nParsing {len(goods_files)} goods files...")
    for gf in goods_files:
        print(f"  {gf.name}")
        try:
            parsed = parse_file(gf)
        except Exception as e:
            print(f"    ERROR: {e}")
            continue
        for key, val in parsed:
            if key.startswith("__"):
                continue
            if isinstance(val, list):
                goods_catalog[key] = extract_good(key, val)

    print(f"  Total goods: {len(goods_catalog)}")

    # ── Parse all building files ──
    buildings_catalog = {}
    source_files = {}
    building_files = sorted(BUILDING_DIR.glob("*.txt"))
    # Skip readme
    building_files = [f for f in building_files if f.name != "readme.txt"]
    print(f"\nParsing {len(building_files)} building files...")
    for bf in building_files:
        print(f"  {bf.name}")
        try:
            parsed = parse_file(bf)
        except Exception as e:
            print(f"    ERROR parsing {bf.name}: {e}")
            continue
        for key, val in parsed:
            if key.startswith("__"):
                continue
            if isinstance(val, list):
                building = extract_building(key, val)
                building["source_file"] = bf.name
                buildings_catalog[key] = building
                source_files.setdefault(bf.name, []).append(key)

    print(f"  Total buildings: {len(buildings_catalog)}")

    # ── Build upgrade chains ──
    chains = {}
    for bname, bdata in buildings_catalog.items():
        obs = bdata.get("obsolete")
        if obs and isinstance(obs, str):
            chains[obs] = bname  # obs is replaced by bname

    # Walk chains to build full sequences
    upgrade_chains = {}
    for bname in buildings_catalog:
        if bname not in [v for v in chains.values()]:
            # This is a chain start (not obsoleted by anything)
            if bname in chains:
                chain = [bname]
                current = bname
                while current in chains:
                    current = chains[current]
                    chain.append(current)
                if len(chain) > 1:
                    upgrade_chains[chain[0]] = chain

    # ── Build category index ──
    categories = {}
    for bname, bdata in buildings_catalog.items():
        cat = bdata.get("category", "uncategorized")
        categories.setdefault(cat, []).append(bname)

    # ── Build specialization index ──
    spec_index = {}
    for bname, bdata in buildings_catalog.items():
        spec = bdata.get("sul_specialization")
        if spec:
            spec_index.setdefault(spec, []).append(bname)

    # ── Assemble final catalog ──
    catalog = {
        "_metadata": {
            "description": "Vanilla EU5 building and goods catalog for SUL building generator",
            "base_game_path": str(BASE_GAME),
            "total_buildings": len(buildings_catalog),
            "total_goods": len(goods_catalog),
        },
        "goods": goods_catalog,
        "buildings": buildings_catalog,
        "upgrade_chains": upgrade_chains,
        "categories": categories,
        "sul_specialization_index": spec_index,
        "source_files": source_files,
    }

    # Write output
    output_path = Path(__file__).resolve().parent / "vanilla_buildings.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nWrote catalog to {output_path}")
    print(f"  Buildings: {len(buildings_catalog)}")
    print(f"  Goods: {len(goods_catalog)}")
    print(f"  Upgrade chains: {len(upgrade_chains)}")
    print(f"  Categories: {len(categories)}")
    print(f"  SUL specializations: {list(spec_index.keys())}")

    return catalog


if __name__ == "__main__":
    main()
