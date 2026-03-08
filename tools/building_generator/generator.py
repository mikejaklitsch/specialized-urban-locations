#!/usr/bin/env python3
"""
SUL Building Generator - Core Logic

Generates both REPLACE and INJECT building definitions for each specialization.
REPLACE buildings read vanilla base properties directly from game PDX files and
apply minimal SUL overrides from config (specialization triggers, modifier categories).
INJECT buildings add specialization gates and modifier bonuses to existing vanilla buildings.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdx_parser import parse_file
from pdx_writer import write_block

# Type aliases matching pdx_parser/pdx_writer
Value = str | int | float | bool | list
Block = list[tuple[str, Value]]

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
CUSTOM_DIR = Path(__file__).resolve().parent / "custom_buildings"
MOD_DIR = Path(__file__).resolve().parent.parent.parent


def load_config() -> dict:
    """Load the generator configuration."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_goods_catalog(config: dict) -> dict[str, str]:
    """
    Load goods classification from vanilla_buildings.json.

    Returns:
        {good_name: "raw_material" | "produced" | "other"}
    """
    catalog_rel = config.get("goods_catalog_path", "vanilla_buildings.json")
    catalog_path = Path(__file__).resolve().parent / catalog_rel
    if not catalog_path.exists():
        print(f"  WARNING: Goods catalog not found at {catalog_path}")
        return {}
    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        name: info.get("classification", "other")
        for name, info in data.get("goods", {}).items()
    }


def is_raw_material(good: str, goods_catalog: dict[str, str]) -> bool:
    """Check if a good is classified as a raw material."""
    return goods_catalog.get(good) == "raw_material"


def load_vanilla_buildings(base_game_path: str) -> dict[str, Block]:
    """
    Parse all vanilla building .txt files and return a flat dict of building blocks.

    Returns:
        {building_name: Block} for every building in the base game.
    """
    building_dir = Path(base_game_path) / "common" / "building_types"
    buildings: dict[str, Block] = {}

    for filepath in sorted(building_dir.glob("*.txt")):
        try:
            file_block = parse_file(filepath)
        except Exception as e:
            print(f"  WARNING: Failed to parse {filepath.name}: {e}")
            continue

        for key, val in file_block:
            if key.startswith("__"):
                continue
            if isinstance(val, list):
                buildings[key] = val

    return buildings


def load_building_level_penalties(mod_path: Path | None = None) -> dict[str, float]:
    """
    Parse the building_levels static modifier and return per-level penalties.

    Returns a dict of {modifier_name: negative_value} for all negative modifiers
    in REPLACE:building_levels. These represent the per-level penalties that
    SUL building modifiers must counteract.
    """
    if mod_path is None:
        mod_path = MOD_DIR
    filepath = (
        mod_path / "main_menu" / "common" / "static_modifiers" / "sul_location_modifier.txt"
    )
    if not filepath.exists():
        return {}

    file_block = parse_file(filepath)
    for key, val in file_block:
        if key == "REPLACE:building_levels" and isinstance(val, list):
            penalties: dict[str, float] = {}
            for mk, mv in val:
                if mk.startswith("__") or not isinstance(mv, (int, float)):
                    continue
                if mv < 0:
                    penalties[mk] = mv
            return penalties
    return {}


def resolve_tier(value: str | float | None, config: dict) -> float | None:
    """Resolve a tier name to its numeric value, or pass through numbers/None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    tiers = config.get("good_output_tiers", {})
    if value in tiers:
        return tiers[value]
    raise ValueError(f"Unknown good_output_tier: {value!r}")


def make_tier_macros(config: dict) -> Block:
    """Generate @macro definitions for good output tiers."""
    tiers = config.get("good_output_tiers", {})
    if not tiers:
        return []
    result: Block = []
    for name, value in tiers.items():
        result.append((f"@sul_{name}_good_bonus", value))
    return result


def load_custom_buildings(spec_name: str) -> Block:
    """
    Load custom (non-vanilla) building definitions for a specialization.

    Reads from custom_buildings/{spec_name}.txt if it exists.
    Returns a Block of building definitions (with comments preserved).
    """
    filepath = CUSTOM_DIR / f"{spec_name}.txt"
    if not filepath.exists():
        return []
    return parse_file(filepath)


def _apply_penalty_offsets(entries: Block, penalties: dict[str, float]) -> Block:
    """
    Apply building-level penalty offsets to modifier entries.

    Config values represent the intended net effect per level.
    Script values must counteract the building_levels penalty, so:
        script_value = config_value - penalty  (penalty is negative, so this adds)

    Only modifiers with a corresponding penalty are adjusted; others pass through.
    """
    if not penalties:
        return entries
    result: Block = []
    for key, val in entries:
        if key in penalties and isinstance(val, (int, float)):
            result.append((key, round(val - penalties[key], 6)))
        else:
            result.append((key, val))
    return result


# ── Block manipulation helpers ────────────────────────────────────────


def deep_copy_block(block: Block) -> Block:
    """Recursively deep copy a Block."""
    return copy.deepcopy(block)


def get_entry(block: Block, key: str) -> Value | None:
    """Get the first value for a key in a block, or None."""
    for k, v in block:
        if k == key:
            return v
    return None


def set_entry(block: Block, key: str, value: Value) -> None:
    """Set the first occurrence of key to value, or append if not found."""
    for i, (k, v) in enumerate(block):
        if k == key:
            block[i] = (key, value)
            return
    block.append((key, value))


def remove_entry(block: Block, key: str) -> Value | None:
    """Remove and return the first occurrence of key. Returns None if not found."""
    for i, (k, v) in enumerate(block):
        if k == key:
            block.pop(i)
            return v
    return None


# ── REPLACE building generation ───────────────────────────────────────

# Keys that mark the boundary before which rank flags should be inserted
_RANK_BOUNDARY_KEYS = frozenset({
    "location_potential", "country_potential", "allow",
    "build_time", "construction_demand", "forbidden_for_estates",
    "price", "always_add_demands", "modifier",
})

# Keys that mark good insertion points for location_potential
_LP_BOUNDARY_KEYS = frozenset({
    "build_time", "construction_demand", "price", "always_add_demands",
    "forbidden_for_estates", "allow", "modifier",
})


def _strip_debug_max_profit(pm_block: Block) -> Block:
    """Remove debug_max_profit entries from a production method block."""
    return [(k, v) for k, v in pm_block if k != "debug_max_profit"]


def _rename_production_methods(block: Block) -> None:
    """
    Rename unique_production_methods entries with sul_ prefix and strip debug_max_profit.
    Modifies block in place.
    """
    for i, (key, val) in enumerate(block):
        if key == "unique_production_methods" and isinstance(val, list):
            new_upm: Block = []
            for pm_name, pm_block in val:
                if pm_name.startswith("__"):
                    new_upm.append((pm_name, pm_block))
                    continue
                new_name = f"sul_{pm_name}"
                if isinstance(pm_block, list):
                    pm_block = _strip_debug_max_profit(pm_block)
                new_upm.append((new_name, pm_block))
            block[i] = ("unique_production_methods", new_upm)
            return


def _merge_spec_trigger_into_lp(
    block: Block, spec_trigger: str, replace_lp: bool = False
) -> None:
    """
    Add specialization trigger to location_potential.

    If replace_lp is True, replaces the entire LP with just the trigger.
    Otherwise, appends the trigger to the existing LP block.
    If no LP exists, creates one with just the trigger.
    """
    if replace_lp:
        remove_entry(block, "location_potential")
        insert_point = len(block)
        for i, (k, _) in enumerate(block):
            if k in _LP_BOUNDARY_KEYS:
                insert_point = i
                break
        block.insert(insert_point, ("location_potential", [(spec_trigger, "yes")]))
        return

    # Find existing LP and append trigger
    for i, (key, val) in enumerate(block):
        if key == "location_potential" and isinstance(val, list):
            val.append((spec_trigger, "yes"))
            return

    # No LP found - create one
    insert_point = len(block)
    for i, (k, _) in enumerate(block):
        if k in _LP_BOUNDARY_KEYS:
            insert_point = i
            break
    block.insert(insert_point, ("location_potential", [(spec_trigger, "yes")]))


def _remove_modifier_keys(mod_block: Block, keys: set[str]) -> None:
    """Remove all entries matching the given keys from a modifier block."""
    i = 0
    while i < len(mod_block):
        if mod_block[i][0] in keys:
            mod_block.pop(i)
        else:
            i += 1


# Modifiers to strip from vanilla building data (replaced by production_efficiency)
_STRIPPED_VANILLA_MODIFIERS = frozenset({
    "local_raw_material_output",
    "local_monthly_food",
    "local_monthly_food_modifier",
    "local_food_capacity",
    "local_food_capacity_modifier",
})


def _strip_obsolete_modifiers(block: Block) -> None:
    """Remove food and raw_material_output modifiers from a building's modifier block."""
    for i, (key, val) in enumerate(block):
        if key == "modifier" and isinstance(val, list):
            _remove_modifier_keys(val, _STRIPPED_VANILLA_MODIFIERS)
            return


def _apply_modifier_adjustments(
    block: Block,
    multiply_modifiers: dict[str, float] | None = None,
    add_modifiers: dict[str, float] | None = None,
    set_modifiers: dict[str, float | None] | None = None,
) -> None:
    """
    Apply adjustments to existing vanilla modifier values.

    Order of operations:
        1. multiply_modifiers - scale existing vanilla values
        2. add_modifiers - adjust existing or append new entries
        3. set_modifiers - force exact values; null removes the entry

    set_modifiers is applied last so it acts as the final word.
    """
    if not add_modifiers and not multiply_modifiers and not set_modifiers:
        return

    for i, (key, val) in enumerate(block):
        if key == "modifier" and isinstance(val, list):
            # 1. Multiplicative: scale existing values
            if multiply_modifiers:
                for j, (mk, mv) in enumerate(val):
                    if mk in multiply_modifiers and isinstance(mv, (int, float)):
                        val[j] = (mk, round(mv * multiply_modifiers[mk], 6))

            # 2. Additive: adjust existing or append new
            if add_modifiers:
                remaining = dict(add_modifiers)
                for j, (mk, mv) in enumerate(val):
                    if mk in remaining and isinstance(mv, (int, float)):
                        val[j] = (mk, round(mv + remaining.pop(mk), 6))
                for mk, mv in remaining.items():
                    val.append((mk, mv))

            # 3. Set: force exact values, null = remove
            if set_modifiers:
                to_remove = {k for k, v in set_modifiers.items() if v is None}
                to_set = {k: v for k, v in set_modifiers.items() if v is not None}
                # Remove nullified entries
                if to_remove:
                    _remove_modifier_keys(val, to_remove)
                # Replace or append exact values
                for mk, mv in to_set.items():
                    found = False
                    for j, (ek, _) in enumerate(val):
                        if ek == mk:
                            val[j] = (mk, mv)
                            found = True
                            break
                    if not found:
                        val.append((mk, mv))
            return


def _append_category_modifiers(
    block: Block,
    category_config: dict,
    override_modifiers: dict | None = None,
    penalties: dict[str, float] | None = None,
) -> None:
    """
    Append modifier category values to the building's modifier block.

    Config values represent intended net effects. Building-level penalties are
    added back so the script value counteracts the per-level penalty.

    Removes any existing vanilla entries that match category keys to avoid
    duplicates, then appends the category values.
    Creates a new modifier block if one doesn't exist.
    """
    cat_mods = dict(category_config.get("modifiers", {}))
    comment = category_config.get("comment", "")

    if override_modifiers:
        cat_mods.update(override_modifiers)

    new_entries: Block = []
    if comment:
        new_entries.append(("__comment__", f"# {comment}"))
    for mk, mv in cat_mods.items():
        new_entries.append((mk, mv))

    # Apply building-level penalty offsets (net → script value)
    if penalties:
        new_entries = _apply_penalty_offsets(new_entries, penalties)

    all_keys = set(cat_mods.keys())

    # Find existing modifier block, deduplicate, then append
    for i, (key, val) in enumerate(block):
        if key == "modifier" and isinstance(val, list):
            _remove_modifier_keys(val, all_keys)
            val.extend(new_entries)
            return

    block.append(("modifier", new_entries))


def _apply_rank_overrides(block: Block, ranks: dict) -> None:
    """Override rank flags in the building block."""
    rank_keys = ("rural_settlement", "town", "city")

    if set(ranks.keys()) == set(rank_keys):
        # Full replacement - remove existing, insert in order
        for rk in rank_keys:
            remove_entry(block, rk)

        insert_idx = len(block)
        for i, (k, _) in enumerate(block):
            if k in _RANK_BOUNDARY_KEYS:
                insert_idx = i
                break

        for rk in reversed(rank_keys):
            block.insert(insert_idx, (rk, ranks[rk]))
    else:
        # Partial override - update specific ranks in place
        for rk, rv in ranks.items():
            set_entry(block, rk, rv)


def generate_replace_building(
    name: str,
    bld_config: dict,
    vanilla_block: Block,
    config: dict,
) -> tuple[str, Block]:
    """
    Generate a single REPLACE building by transforming a vanilla building.

    Reads vanilla properties directly and applies minimal SUL modifications:
    - Removes increase_per_level_cost
    - Merges specialization trigger into location_potential
    - Appends modifier category values
    - Applies property overrides (max_levels, employment_size, ranks)
    - Renames production methods with sul_ prefix
    - Strips debug_max_profit from production methods

    Returns:
        ("REPLACE:name", block) tuple.
    """
    block = deep_copy_block(vanilla_block)

    spec_name = bld_config["specialization"]
    spec = config["specializations"][spec_name]

    # 1. Remove increase_per_level_cost
    remove_entry(block, "increase_per_level_cost")

    # 2. Apply property overrides
    if "max_levels" in bld_config:
        set_entry(block, "max_levels", bld_config["max_levels"])

    if "employment_size" in bld_config:
        set_entry(block, "employment_size", bld_config["employment_size"])

    if "ranks" in bld_config:
        _apply_rank_overrides(block, bld_config["ranks"])

    # 3. Merge specialization trigger into location_potential
    replace_lp = bld_config.get("replace_location_potential", False)
    _merge_spec_trigger_into_lp(block, spec["trigger"], replace_lp)

    # 4. Strip obsolete vanilla modifiers (food, raw_material_output)
    _strip_obsolete_modifiers(block)

    # 5. Apply per-building modifier adjustments (multiply, add, set)
    _apply_modifier_adjustments(
        block,
        multiply_modifiers=bld_config.get("multiply_modifiers"),
        add_modifiers=bld_config.get("add_modifiers"),
        set_modifiers=bld_config.get("set_modifiers"),
    )

    # 5. Append modifier category values (replaces any overlapping vanilla keys)
    if "modifier_category" in bld_config:
        cat = config["modifier_categories"][bld_config["modifier_category"]]
        override_mods = bld_config.get("override_modifiers")
        penalties = config.get("_building_level_penalties")
        _append_category_modifiers(block, cat, override_mods, penalties)

    # 5b. Per-good output modifier (e.g. glass_guild → local_glass_output_modifier)
    good_output_val = resolve_tier(bld_config.get("good_output_modifier"), config)
    if good_output_val is not None and "good" in bld_config:
        good = bld_config["good"]
        mod_key = f"local_{good}_output_modifier"
        for i, (key, val) in enumerate(block):
            if key == "modifier" and isinstance(val, list):
                val.append((mod_key, good_output_val))
                break
        else:
            block.append(("modifier", [(mod_key, good_output_val)]))

    # 6. Rename production methods
    _rename_production_methods(block)

    return (f"REPLACE:{name}", block)


# ── INJECT building generation ────────────────────────────────────────


def make_finished_goods_modifiers(
    goods: list[str],
    value: float,
    comment: str | None = None,
) -> Block:
    """Build modifier entries for a set of finished goods."""
    entries: Block = []
    if comment:
        entries.append(("__comment__", f"# {comment}"))
    for good in goods:
        entries.append((f"local_{good}_output_modifier", value))
    return entries


def make_inject_building(
    name: str,
    spec_trigger: str,
    finished_goods: list[str],
    modifier_value: float | None,
    comment: str,
    extra_modifiers: dict[str, float] | None = None,
    extra_props: list[list[str]] | None = None,
    location_potential_or: list[str] | None = None,
    override_extra_modifiers: dict[str, float] | None = None,
) -> tuple[str, Block]:
    """Generate a single INJECT building definition."""
    block: Block = []

    if extra_props:
        for prop_key, prop_val in extra_props:
            block.append((prop_key, prop_val))

    # Location potential
    if location_potential_or:
        or_block: Block = []
        for trigger_expr in location_potential_or:
            if " = " in trigger_expr:
                parts = trigger_expr.split(" = ", 1)
                or_block.append((parts[0].strip(), parts[1].strip()))
            else:
                or_block.append((trigger_expr, "yes"))
        block.append(("location_potential", [("OR", or_block)]))
    else:
        block.append(("location_potential", [(spec_trigger, "yes")]))

    # Modifier block
    mod_block: Block = []

    if extra_modifiers:
        if modifier_value is None and comment:
            mod_block.append(("__comment__", f"# {comment}"))
        for mk, mv in extra_modifiers.items():
            mod_block.append((mk, mv))

    if override_extra_modifiers:
        for mk, mv in override_extra_modifiers.items():
            mod_block.append((mk, mv))

    if modifier_value is not None and finished_goods:
        mod_block.extend(
            make_finished_goods_modifiers(finished_goods, modifier_value, comment)
        )

    if mod_block:
        block.append(("modifier", mod_block))

    return (f"INJECT:{name}", block)


def make_cross_spec_building(
    name: str,
    cross_config: dict,
    config: dict,
    trigger: str | None = None,
) -> tuple[str, Block]:
    """Generate a cross-specialization INJECT building."""
    block: Block = []
    specs = config["specializations"]

    if trigger:
        block.append(("location_potential", [(trigger, "yes")]))
    else:
        or_triggers = cross_config.get("location_potential_or", [])
        if or_triggers:
            or_block: Block = [(t, "yes") for t in or_triggers]
            block.append(("location_potential", [("OR", or_block)]))

    mod_block: Block = []
    good_override = cross_config.get("good")
    for group in cross_config.get("modifier_groups", []):
        extra = group.get("extra_modifiers", {})
        for mk, mv in extra.items():
            mod_block.append((mk, mv))

        mod_val = resolve_tier(group.get("modifier_value"), config)
        if mod_val is not None:
            if good_override:
                comment = f"{good_override.replace('_', ' ').title()} output"
                mod_block.extend(
                    make_finished_goods_modifiers([good_override], mod_val, comment)
                )
            else:
                for spec_name in group.get("specs", []):
                    spec = specs[spec_name]
                    goods = spec["finished_goods"]
                    spec_comment = spec["comment"]
                    mod_block.extend(
                        make_finished_goods_modifiers(goods, mod_val, spec_comment)
                    )

    if mod_block:
        block.append(("modifier", mod_block))

    return (f"INJECT:{name}", block)


def _apply_penalties_to_building(block: Block, penalties: dict[str, float]) -> None:
    """Apply building-level penalty offsets to a building's modifier block in place."""
    if not penalties:
        return
    for i, (key, val) in enumerate(block):
        if key == "modifier" and isinstance(val, list):
            block[i] = ("modifier", _apply_penalty_offsets(val, penalties))
            return


def generate_spec_buildings(
    spec_name: str,
    config: dict,
    vanilla_buildings: dict[str, Block],
    goods_catalog: dict[str, str] | None = None,
) -> Block:
    """
    Generate all buildings (REPLACE + INJECT) for a specialization.

    Buildings are grouped into sections by header comment.  Sections with the
    same header are merged, with REPLACE entries appearing before INJECT
    entries within each section.

    Returns:
        A single Block containing all building definitions with section headers.
    """
    # Ordered dict: header -> list of (key, block) tuples
    sections: dict[str, list[tuple[str, Block]]] = {}
    penalties = config.get("_building_level_penalties", {})

    def add_to_section(header: str, key: str, block: Block) -> None:
        sections.setdefault(header, []).append((key, block))

    categories = config.get("modifier_categories", {})

    # ── REPLACE buildings ────────────────────────────────────────

    for bld_name, bld_config in config.get("replace_buildings", {}).items():
        if bld_config.get("specialization") != spec_name:
            continue
        if bld_name not in vanilla_buildings:
            print(f"  WARNING: Vanilla building '{bld_name}' not found, skipping")
            continue

        key, block = generate_replace_building(
            bld_name, bld_config, vanilla_buildings[bld_name], config
        )
        cat = bld_config.get("modifier_category", "_uncategorized")
        cat_comment = categories.get(cat, {}).get("comment", "") if cat != "_uncategorized" else ""
        header = cat_comment or "Uncategorized"
        add_to_section(header, key, block)

    # ── INJECT buildings ─────────────────────────────────────────

    spec = config["specializations"][spec_name]
    inject_config = config["inject_buildings"].get(spec_name, {})
    overrides = config.get("inject_building_overrides", {})

    trigger = spec["trigger"]
    goods = spec["finished_goods"]
    comment = spec["comment"]
    spec_extra_mods = spec.get("extra_modifiers")

    # Build building→chain trigger map
    chain_trigger_map: dict[str, str] = {}
    for chain_trigger, chain_buildings in config.get("building_chains", {}).items():
        for bld in chain_buildings:
            chain_trigger_map[bld] = chain_trigger

    for tier_name, tier_config in inject_config.items():
        if tier_name == "cross_spec" or tier_name.startswith("_"):
            continue

        mod_value = resolve_tier(tier_config.get("modifier_value"), config)
        tier_extra = tier_config.get("extra_modifiers")
        tier_comment = tier_config.get("comment")
        tier_buildings = tier_config.get("buildings", [])
        tier_good = tier_config.get("good")
        if tier_good:
            tier_goods = [tier_good]
        else:
            tier_goods = tier_config.get("finished_goods", goods)

        if not tier_buildings:
            continue

        label = tier_comment or comment
        header = f"{label} ({tier_name})"

        for building_name in tier_buildings:
            bld_override = overrides.get(building_name, {})
            loc_or = bld_override.get("location_potential_or")
            extra_props = bld_override.get("extra_props")

            # Use chain-specific trigger if available, else spec trigger
            bld_trigger = chain_trigger_map.get(building_name, trigger)

            merged_extra = {}
            if spec_extra_mods:
                merged_extra.update(spec_extra_mods)
            if tier_extra:
                merged_extra.update(tier_extra)

            # Auto-derive: add local_max_rgo_size_modifier for raw material goods
            if goods_catalog and tier_good and is_raw_material(tier_good, goods_catalog):
                if "local_max_rgo_size_modifier" not in merged_extra:
                    merged_extra["local_max_rgo_size_modifier"] = 0.015

            override_extra = bld_override.get("extra_modifiers")

            key, block = make_inject_building(
                name=building_name,
                spec_trigger=bld_trigger,
                finished_goods=tier_goods,
                modifier_value=mod_value,
                comment=tier_comment or comment,
                extra_modifiers=merged_extra or None,
                extra_props=extra_props,
                location_potential_or=loc_or,
                override_extra_modifiers=override_extra,
            )
            _apply_penalties_to_building(block, penalties)
            add_to_section(header, key, block)

    # Cross-spec
    cross = inject_config.get("cross_spec")
    if cross:
        for building_name in cross.get("buildings", []):
            bld_trigger = chain_trigger_map.get(building_name)
            key, block = make_cross_spec_building(
                building_name, cross, config, trigger=bld_trigger
            )
            _apply_penalties_to_building(block, penalties)
            add_to_section("Cross-specialization", key, block)

    # ── Assemble output ──────────────────────────────────────────

    result: Block = []

    # Prepend @macro definitions for good output tiers
    macros = make_tier_macros(config)
    if macros:
        result.extend(macros)

    for header, buildings in sections.items():
        result.append(("__comment__", f"# {header}"))
        result.extend(buildings)

    # ── Custom buildings ────────────────────────────────────────

    custom = load_custom_buildings(spec_name)
    if custom:
        result.append(("__comment__", "# Custom buildings"))
        result.extend(custom)

    return result
