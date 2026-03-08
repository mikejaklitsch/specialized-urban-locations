#!/usr/bin/env python3
"""
SUL Building Generator - Main CLI

Generates complete building definition files (both REPLACE and INJECT)
for each specialization type.

Usage:
    python main.py                         # Generate all, write to output/
    python main.py --spec mining           # Generate one specialization
    python main.py --dry-run               # Print output without writing
    python main.py --diff                  # Compare output against current mod files
    python main.py --no-format             # Skip pdx-format on output files
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdx_parser import parse_file
from pdx_writer import write_block, write_file
from generator import (
    load_config,
    load_vanilla_buildings,
    load_building_level_penalties,
    load_goods_catalog,
    generate_spec_buildings,
)

TOOL_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = TOOL_DIR / "output"
CUSTOM_PM_DIR = TOOL_DIR / "custom_buildings" / "production_methods"
MOD_DIR = TOOL_DIR.parent.parent
MOD_BUILDING_DIR = MOD_DIR / "in_game" / "common" / "building_types"
MOD_PM_DIR = MOD_DIR / "in_game" / "common" / "production_methods"

# Type aliases
Block = list[tuple[str, object]]


def generate_spec_file(
    spec_name: str,
    config: dict,
    vanilla_buildings: dict[str, list],
    goods_catalog: dict[str, str] | None = None,
) -> tuple[str, Block]:
    """
    Generate a complete building file for one specialization.

    Returns (output_filename, combined_block).
    """
    output_file = config["specializations"][spec_name].get(
        "output_file", f"sul_{spec_name}.txt"
    )

    combined = generate_spec_buildings(spec_name, config, vanilla_buildings, goods_catalog)

    return output_file, combined


def run_pdx_format(filepath: Path) -> bool:
    """Run pdx-format on a file. Returns True if successful."""
    try:
        result = subprocess.run(
            ["pdx-format", str(filepath)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _is_order_only_diff(existing_block: Block, generated_block: Block) -> bool:
    """Check if two building blocks differ only in property ordering."""
    ex_props = {k: v for k, v in existing_block if not k.startswith("__")}
    gen_props = {k: v for k, v in generated_block if not k.startswith("__")}
    if set(ex_props.keys()) != set(gen_props.keys()):
        return False
    for pk in ex_props:
        ex_val = write_block([(pk, ex_props[pk])])
        gen_val = write_block([(pk, gen_props[pk])])
        if ex_val != gen_val:
            return False
    return True


def _describe_content_diff(key: str, existing_block: Block, generated_block: Block) -> list[str]:
    """Describe the actual content differences between two building blocks."""
    ex_props = {k: v for k, v in existing_block if not k.startswith("__")}
    gen_props = {k: v for k, v in generated_block if not k.startswith("__")}
    details = []
    extra_in_gen = set(gen_props.keys()) - set(ex_props.keys())
    extra_in_mod = set(ex_props.keys()) - set(gen_props.keys())
    if extra_in_gen:
        details.append(f"    + new keys: {sorted(extra_in_gen)}")
    if extra_in_mod:
        details.append(f"    - removed keys: {sorted(extra_in_mod)}")
    for pk in sorted(set(ex_props.keys()) & set(gen_props.keys())):
        ex_val = write_block([(pk, ex_props[pk])])
        gen_val = write_block([(pk, gen_props[pk])])
        if ex_val != gen_val:
            details.append(f"    ~ {pk} changed")
    return details


def diff_with_mod(output_file: str, output_block: Block) -> list[str]:
    """
    Compare generated output against the current mod file.

    Returns list of difference descriptions.
    """
    mod_path = MOD_BUILDING_DIR / output_file
    if not mod_path.exists():
        return [f"Mod file does not exist: {mod_path.name}"]

    existing = parse_file(mod_path)
    existing_dict = {k: v for k, v in existing if not k.startswith("__")}
    generated_dict = {k: v for k, v in output_block if not k.startswith("__")}

    diffs = []
    existing_keys = set(existing_dict.keys())
    generated_keys = set(generated_dict.keys())

    only_in_mod = existing_keys - generated_keys
    only_in_gen = generated_keys - existing_keys

    if only_in_mod:
        diffs.append(f"  Only in mod: {sorted(only_in_mod)}")
    if only_in_gen:
        diffs.append(f"  Only in generated: {sorted(only_in_gen)}")

    # Compare matching buildings
    order_only = 0
    content_diffs = 0
    content_details = []
    for key in sorted(existing_keys & generated_keys):
        ex_text = write_block([(key, existing_dict[key])])
        gen_text = write_block([(key, generated_dict[key])])
        if ex_text != gen_text:
            if _is_order_only_diff(existing_dict[key], generated_dict[key]):
                order_only += 1
            else:
                content_diffs += 1
                content_details.append(f"  CONTENT: {key}")
                content_details.extend(
                    _describe_content_diff(key, existing_dict[key], generated_dict[key])
                )

    total = len(existing_keys & generated_keys)
    exact = total - order_only - content_diffs
    summary = f"  {exact}/{total} exact"
    if order_only:
        summary += f", {order_only} order-only"
    if content_diffs:
        summary += f", {content_diffs} CONTENT DIFF"
    diffs.insert(0, summary)
    diffs.extend(content_details)

    return diffs


def _fmt(val: float) -> str:
    """Format a number compactly: drop trailing zeros, keep sign."""
    if val == 0:
        return "0"
    s = f"{val:.6f}".rstrip("0").rstrip(".")
    return s


def show_penalties(config: dict) -> None:
    """Print the building-level penalty map."""
    penalties = config.get("_building_level_penalties", {})
    if not penalties:
        print("No building-level penalties loaded.\n")
        return

    print("Building-Level Penalties (per level)")
    print("-" * 50)
    # Group by value
    by_value: dict[float, list[str]] = {}
    for k, v in sorted(penalties.items()):
        by_value.setdefault(v, []).append(k)
    for val in sorted(by_value):
        mods = by_value[val]
        print(f"  {_fmt(val):>8}  ({len(mods)} modifiers)")
        for m in mods:
            print(f"             {m}")
    print()


def show_categories(config: dict) -> None:
    """Print modifier categories showing net → script values."""
    categories = config.get("modifier_categories", {})
    penalties = config.get("_building_level_penalties", {})

    print("Modifier Categories (net → script)")
    print("=" * 65)
    for cat_name, cat in categories.items():
        comment = cat.get("comment", cat_name)
        mods = cat.get("modifiers", {})
        print(f"\n  {cat_name}  ({comment})")
        if not mods:
            print("    (no modifiers)")
            continue
        for mk, mv in mods.items():
            penalty = penalties.get(mk, 0)
            script = round(mv - penalty, 6) if penalty else mv
            if penalty:
                print(f"    {mk:<42} {_fmt(mv):>8} → {_fmt(script)}")
            else:
                print(f"    {mk:<42} {_fmt(mv):>8}")
    print()


def show_specializations(config: dict) -> None:
    """Print specialization overview with building counts."""
    specs = config.get("specializations", {})
    replace_buildings = config.get("replace_buildings", {})
    inject_buildings = config.get("inject_buildings", {})

    print("Specializations")
    print("=" * 65)
    for spec_name, spec in sorted(specs.items()):
        trigger = spec["trigger"]
        goods = spec["finished_goods"]
        output = spec.get("output_file", f"sul_{spec_name}.txt")

        replaces = [
            name for name, cfg in replace_buildings.items()
            if cfg.get("specialization") == spec_name
        ]
        inject_cfg = inject_buildings.get(spec_name, {})
        inject_count = sum(
            len(tier.get("buildings", []))
            for tier_name, tier in inject_cfg.items()
            if isinstance(tier, dict) and tier_name != "cross_spec"
        )
        cross = inject_cfg.get("cross_spec", {})
        cross_count = len(cross.get("buildings", []))

        print(f"\n  {spec_name}  →  {output}")
        print(f"    trigger: {trigger}")
        print(f"    goods:   {', '.join(goods)}")
        if spec.get("extra_modifiers"):
            for mk, mv in spec["extra_modifiers"].items():
                print(f"    extra:   {mk} = {_fmt(mv)}")
        print(f"    REPLACE: {len(replaces)}  INJECT: {inject_count}", end="")
        if cross_count:
            print(f"  cross-spec: {cross_count}", end="")
        print()
    print()


def show_buildings(config: dict, spec_filter: str | None = None) -> None:
    """Print building assignments per specialization with category and overrides."""
    specs = config.get("specializations", {})
    categories = config.get("modifier_categories", {})
    replace_buildings = config.get("replace_buildings", {})
    inject_buildings = config.get("inject_buildings", {})
    overrides = config.get("inject_building_overrides", {})
    penalties = config.get("_building_level_penalties", {})

    for spec_name in sorted(specs):
        if spec_filter and spec_name != spec_filter:
            continue

        spec = specs[spec_name]
        print(f"\n{'=' * 65}")
        print(f"  {spec_name.upper()} BUILDINGS")
        print(f"{'=' * 65}")

        # REPLACE buildings grouped by category
        by_cat: dict[str, list[tuple[str, dict]]] = {}
        for bname, bcfg in replace_buildings.items():
            if bcfg.get("specialization") != spec_name:
                continue
            cat = bcfg.get("modifier_category", "_uncategorized")
            by_cat.setdefault(cat, []).append((bname, bcfg))

        if by_cat:
            print("\n  REPLACE buildings:")
            for cat_name, blds in by_cat.items():
                if cat_name == "_uncategorized":
                    label = "uncategorized"
                else:
                    cat_cfg = categories.get(cat_name, {})
                    label = f"{cat_name} ({cat_cfg.get('comment', '')})"
                print(f"    [{label}]")
                for bname, bcfg in blds:
                    extras = []
                    if "max_levels" in bcfg:
                        extras.append(f"max={bcfg['max_levels']}")
                    if "employment_size" in bcfg:
                        extras.append(f"emp={bcfg['employment_size']}")
                    if bcfg.get("replace_location_potential"):
                        extras.append("replace_lp")
                    if bcfg.get("ranks"):
                        ranks = bcfg["ranks"]
                        parts = []
                        for rk in ("rural_settlement", "town", "city"):
                            if rk in ranks:
                                parts.append(f"{rk[0].upper()}={'Y' if ranks[rk] == 'yes' else 'N'}")
                        extras.append(f"ranks={''.join(parts)}")
                    for adj_type in ("override_modifiers", "multiply_modifiers",
                                     "add_modifiers", "set_modifiers"):
                        adj = bcfg.get(adj_type)
                        if adj:
                            items = ", ".join(
                                f"{k}={_fmt(v) if v is not None else 'null'}"
                                for k, v in adj.items()
                            )
                            extras.append(f"{adj_type.split('_')[0]}({items})")
                    suffix = f"  ({', '.join(extras)})" if extras else ""
                    print(f"      {bname}{suffix}")

        # INJECT buildings grouped by tier
        inject_cfg = inject_buildings.get(spec_name, {})
        if inject_cfg:
            print("\n  INJECT buildings:")
            for tier_name, tier in inject_cfg.items():
                if not isinstance(tier, dict):
                    continue
                if tier_name == "cross_spec":
                    blds = tier.get("buildings", [])
                    lp_or = tier.get("location_potential_or", [])
                    print(f"    [cross-spec]  lp_or={lp_or}")
                    for group in tier.get("modifier_groups", []):
                        mod_val = group.get("modifier_value")
                        group_specs = group.get("specs", [])
                        extra = group.get("extra_modifiers", {})
                        parts = []
                        if mod_val is not None:
                            net = _fmt(mod_val)
                            script = _fmt(round(mod_val - next(
                                (v for k, v in penalties.items()
                                 if k.endswith("_output_modifier")), 0
                            ), 6))
                            parts.append(f"spread={net}→{script}")
                        for mk, mv in extra.items():
                            p = penalties.get(mk, 0)
                            if p:
                                parts.append(f"{mk}={_fmt(mv)}→{_fmt(round(mv - p, 6))}")
                            else:
                                parts.append(f"{mk}={_fmt(mv)}")
                        parts.append(f"specs={group_specs}")
                        print(f"      {', '.join(parts)}")
                    for b in blds:
                        bld_ov = overrides.get(b, {})
                        suffix = f"  {bld_ov}" if bld_ov else ""
                        print(f"      {b}{suffix}")
                    continue

                blds = tier.get("buildings", [])
                mod_val = tier.get("modifier_value")
                tier_extra = tier.get("extra_modifiers", {})
                tier_goods = tier.get("finished_goods")

                parts = [tier_name]
                if mod_val is not None:
                    net = _fmt(mod_val)
                    script = _fmt(round(mod_val - next(
                        (v for k, v in penalties.items()
                         if k.endswith("_output_modifier")), 0
                    ), 6))
                    parts.append(f"spread={net}→{script}")
                if tier_extra:
                    for mk, mv in tier_extra.items():
                        p = penalties.get(mk, 0)
                        if p:
                            parts.append(f"{mk}={_fmt(mv)}→{_fmt(round(mv - p, 6))}")
                        else:
                            parts.append(f"{mk}={_fmt(mv)}")
                if tier_goods:
                    parts.append(f"goods={tier_goods}")
                print(f"    [{', '.join(parts)}]")
                for b in blds:
                    bld_ov = overrides.get(b, {})
                    suffix = f"  {bld_ov}" if bld_ov else ""
                    print(f"      {b}{suffix}")
    print()


def show_info(config: dict, spec_filter: str | None = None) -> None:
    """Print full config summary."""
    show_penalties(config)
    show_categories(config)
    show_specializations(config)
    show_buildings(config, spec_filter)


def main():
    parser = argparse.ArgumentParser(
        description="Generate SUL building definition files"
    )
    parser.add_argument("--spec", help="Generate only this specialization")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing")
    parser.add_argument("--diff", action="store_true", help="Compare output against current mod files")
    parser.add_argument("--no-format", action="store_true", help="Skip pdx-format on output files")
    parser.add_argument("--info", nargs="?", const="all",
                        choices=["all", "penalties", "categories", "specs", "buildings"],
                        help="Show config info (default: all)")
    parser.add_argument("--config", help="Path to config.json", default=str(TOOL_DIR / "config.json"))
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    base_game_path = config.get("base_game_path")
    if not base_game_path:
        print("ERROR: base_game_path not set in config.json")
        sys.exit(1)

    print("SUL Building Generator")
    print(f"  Config: {args.config}")
    print(f"  Base game: {base_game_path}")
    print("  Loading vanilla buildings...")
    vanilla_buildings = load_vanilla_buildings(base_game_path)
    print(f"  Loaded {len(vanilla_buildings)} vanilla buildings")

    penalties = load_building_level_penalties(MOD_DIR)
    if penalties:
        config["_building_level_penalties"] = penalties
        print(f"  Loaded {len(penalties)} building-level penalties")

    goods_catalog = load_goods_catalog(config)
    if goods_catalog:
        raw_count = sum(1 for c in goods_catalog.values() if c == "raw_material")
        print(f"  Loaded {len(goods_catalog)} goods ({raw_count} raw materials)")
    print()

    if args.info:
        if args.info == "all":
            show_info(config, args.spec)
        elif args.info == "penalties":
            show_penalties(config)
        elif args.info == "categories":
            show_categories(config)
        elif args.info == "specs":
            show_specializations(config)
        elif args.info == "buildings":
            show_buildings(config, args.spec)
        return

    # Determine which specs to process
    specs = sorted(config["specializations"].keys())
    if args.spec:
        if args.spec not in config["specializations"]:
            print(f"ERROR: Unknown specialization '{args.spec}'")
            print(f"Available: {specs}")
            sys.exit(1)
        specs = [args.spec]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_files = []

    for spec_name in specs:
        output_file, combined_block = generate_spec_file(
            spec_name, config, vanilla_buildings, goods_catalog
        )

        if not combined_block:
            print(f"  {spec_name}: no buildings")
            continue

        replace_count = sum(1 for k, _ in combined_block if k.startswith("REPLACE:"))
        inject_count = sum(1 for k, _ in combined_block if k.startswith("INJECT:"))

        if args.diff:
            print(f"{spec_name} ({output_file}): {replace_count} REPLACE + {inject_count} INJECT")
            diffs = diff_with_mod(output_file, combined_block)
            for d in diffs:
                print(d)
            print()
        elif args.dry_run:
            print(f"\n{'='*60}")
            print(f"  {spec_name} -> {output_file} ({replace_count} REPLACE + {inject_count} INJECT)")
            print(f"{'='*60}")
            print(write_block(combined_block))
        else:
            # Count custom buildings
            custom_count = sum(
                1 for k, _ in combined_block
                if not k.startswith(("REPLACE:", "INJECT:", "__"))
            )

            # Write to output/ (reference copy)
            outpath = OUTPUT_DIR / output_file
            write_file(outpath, combined_block)
            generated_files.append(outpath)

            # Write to in_game/ (live mod)
            mod_path = MOD_BUILDING_DIR / output_file
            write_file(mod_path, combined_block)
            generated_files.append(mod_path)

            parts = f"{replace_count} REPLACE + {inject_count} INJECT"
            if custom_count:
                parts += f" + {custom_count} custom"
            print(f"  {spec_name}: {parts} -> {output_file}")

    # Copy custom production method files to in_game/
    if not args.dry_run and not args.diff and CUSTOM_PM_DIR.exists():
        import shutil
        MOD_PM_DIR.mkdir(parents=True, exist_ok=True)
        pm_files = sorted(CUSTOM_PM_DIR.glob("*.txt"))
        if pm_files:
            for pm_file in pm_files:
                dest = MOD_PM_DIR / f"sul_{pm_file.name}"
                shutil.copy2(pm_file, dest)
                generated_files.append(dest)
            print(f"\n  Copied {len(pm_files)} production method files")

    # Run pdx-format on generated files (default behavior)
    if not args.no_format and generated_files:
        print("\nRunning pdx-format...")
        for fp in generated_files:
            if run_pdx_format(fp):
                print(f"  Formatted: {fp.name}")
            else:
                print(f"  FAILED: {fp.name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
