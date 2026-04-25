#!/usr/bin/env python3
"""
Master rebuilder — runs all generators in dependency order.

Generates all auto-generated content for the SUL mod in one command.
Each step outputs to a tmp staging directory first, then copies to the mod
on success. Retired generators (generate_rank_setup.py, generate_rgo_town_setups.py)
are skipped.

Steps (in order):
  1. generate_rank_overrides.py  — rank modifier definitions (15 custom ranks)
  2. generate_buildings.py       — vanilla overrides, building config, @sul-diff, EPBM hooks
  3. generate_town_setups.py     — specialization-variant town setup templates
  4. generate_setup.py           — rank assignments, building placements, pops
  5. generate_starting_development.py — starting development values
  6. demand_calculator.py        — demand values, goods overrides, demand GUI
  7. generate_dev_tooltip.py     — development tooltip GUI

Usage:
    python tools/rebuild.py                  # run all steps
    python tools/rebuild.py --steps 1,2,3    # run specific steps
    python tools/rebuild.py --dry-run        # show what would run
    python tools/rebuild.py --list           # list steps
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MOD_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = MOD_ROOT / "tools"
VANILLA_ROOT = Path("/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game")


def step_rank_overrides(staging, dry_run):
    """Generate rank modifier definitions."""
    out = staging / "rank_overrides"
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(TOOLS_DIR / "generate_rank_overrides.py"),
        "--vanilla", str(VANILLA_ROOT),
        "--output", str(out),
    ]
    if dry_run:
        return cmd, []
    subprocess.check_call(cmd)
    return cmd, _find_outputs(out)


def step_buildings(staging, dry_run):
    """Generate vanilla building overrides, building config, and EPBM hooks."""
    out = staging / "buildings"
    cmd_buildings = [
        sys.executable, str(TOOLS_DIR / "generate_buildings.py"),
        "--output", str(out),
    ]
    cmd_epbm = ["bash", str(TOOLS_DIR / "generate_epbm_hooks.sh")]
    if dry_run:
        return cmd_buildings, []
    subprocess.check_call(cmd_buildings)
    print("  Running EPBM hooks generator...")
    subprocess.check_call(cmd_epbm)
    _format_mod_files([
        MOD_ROOT / "in_game/common/building_types/sul_epbm_generated_inject.txt",
        MOD_ROOT / "in_game/common/building_types/sul_epbm_generated_replace.txt",
        MOD_ROOT / "in_game/common/scripted_effects/sul_epbm_generated_init_effects.txt",
        MOD_ROOT / "in_game/common/international_organizations/sul_epbm_generated_ios.txt",
        MOD_ROOT / "in_game/common/biases/sul_epbm_generated_biases.txt",
    ])
    return cmd_buildings, _find_outputs(out) + ["(EPBM writes directly to mod)"]


def step_town_setups(staging, dry_run):
    """Generate specialization-variant town setup templates."""
    out = staging / "town_setups"
    cmd = [
        sys.executable, str(TOOLS_DIR / "generate_town_setups.py"),
        "--output", str(out),
    ]
    if dry_run:
        return cmd, []
    subprocess.check_call(cmd)
    return cmd, _find_outputs(out)


def step_setup(staging, dry_run):
    """Generate rank assignments, building placements, pops."""
    out = staging / "setup"
    cmd = [
        sys.executable, str(TOOLS_DIR / "generate_setup.py"),
        "--output", str(out),
    ]
    if dry_run:
        return cmd, []
    subprocess.check_call(cmd)
    return cmd, _find_outputs(out)



def step_starting_development(staging, dry_run):
    """Generate starting development values."""
    cmd = [
        sys.executable, str(TOOLS_DIR / "generate_starting_development.py"),
        "--vanilla", str(VANILLA_ROOT),
        "--mod", str(MOD_ROOT),
    ]
    if dry_run:
        return cmd, []
    subprocess.check_call(cmd)
    return cmd, ["(writes directly to mod)"]


def step_demand_calculator(staging, dry_run):
    """Generate demand values, goods overrides, demand init, GUI tooltip."""
    cmd = [
        sys.executable, str(TOOLS_DIR / "demand_calculator.py"),
        "--write", "--cache", "--gui",
    ]
    if dry_run:
        return cmd, []
    subprocess.check_call(cmd)
    _format_mod_files([
        MOD_ROOT / "in_game/common/goods/sul_goods.txt",
    ])
    return cmd, ["(writes directly to mod)"]


def step_dev_tooltip(staging, dry_run):
    """Generate development tooltip GUI."""
    cmd = [sys.executable, str(TOOLS_DIR / "generate_dev_tooltip.py")]
    if dry_run:
        return cmd, []
    subprocess.check_call(cmd)
    _format_mod_files([
        MOD_ROOT / "in_game/common/script_values/sul_dev_tooltip_values.txt",
        MOD_ROOT / "in_game/gui/shared/aaa_sul_location_tooltips.gui",
    ])
    return cmd, ["(writes directly to mod)"]


STEPS = [
    (1, "rank_overrides", "Rank modifier definitions", step_rank_overrides),
    (2, "buildings", "Building overrides + config + EPBM hooks", step_buildings),
    (3, "town_setups", "Specialization-variant town setup templates", step_town_setups),
    (4, "setup", "Rank assignments + building placements + pops", step_setup),
    (5, "starting_dev", "Starting development values", step_starting_development),
    (6, "demand", "Demand values + goods overrides + GUI", step_demand_calculator),
    (7, "dev_tooltip", "Development tooltip GUI", step_dev_tooltip),
]


PDX_FORMAT = Path.home() / ".local" / "bin" / "pdx-format"

SKIP_FORMAT = {
    "06_pops.txt", "14_development.txt", "building_config.json",
    "07_cities_and_buildings.txt", "50_sul_setup.txt", "51_sul_markets.txt",
}

NO_BOM_FILES = {
    "06_pops.txt", "14_development.txt",
    "07_cities_and_buildings.txt", "50_sul_setup.txt", "51_sul_markets.txt",
}


def _find_outputs(root):
    """Recursively find all files under a directory."""
    return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]


def _pdx_format(filepath):
    """Run pdx-format on a file. Setup files get --no-bom, others get default BOM."""
    if not PDX_FORMAT.exists():
        return False
    cmd = [str(PDX_FORMAT)]
    if filepath.name in NO_BOM_FILES:
        cmd.append("--no-bom")
    cmd.append(str(filepath))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _format_mod_files(paths):
    """Run pdx-format on specific mod files written directly (not staged)."""
    for p in paths:
        if not p.exists() or p.name in SKIP_FORMAT:
            continue
        _pdx_format(p)


def _format_staged_files(staging_subdir):
    """Run pdx-format on all .txt files in staging before copying to mod."""
    if not PDX_FORMAT.exists():
        print("  pdx-format not found, skipping formatting")
        return 0
    formatted = 0
    for f in staging_subdir.rglob("*.txt"):
        if f.name in SKIP_FORMAT:
            continue
        if _pdx_format(f):
            formatted += 1
    return formatted


def _copy_staging_to_mod(staging_subdir, step_name):
    """Copy staged outputs to the mod directory, preserving structure."""
    if not staging_subdir.exists():
        return 0
    copied = 0

    # buildings step has special structure
    if step_name == "buildings":
        # building_types/ → mod building_types/
        bt_dir = staging_subdir / "building_types"
        if bt_dir.exists():
            dest = MOD_ROOT / "in_game" / "common" / "building_types"
            for f in bt_dir.glob("*.txt"):
                shutil.copy2(f, dest / f.name)
                copied += 1
        # sul_building_types/ → mod building_types/
        sul_bt = staging_subdir / "sul_building_types"
        if sul_bt.exists():
            dest = MOD_ROOT / "in_game" / "common" / "building_types"
            for f in sul_bt.glob("*.txt"):
                shutil.copy2(f, dest / f.name)
                copied += 1
        # building_config.json → tools/
        cfg = staging_subdir / "building_config.json"
        if cfg.exists():
            shutil.copy2(cfg, TOOLS_DIR / "building_config.json")
            copied += 1
        # PM localization → in_game/localization/english/
        pm_loc = staging_subdir / "sul_pm_l_english.yml"
        if pm_loc.exists():
            dest = MOD_ROOT / "in_game" / "localization" / "english"
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pm_loc, dest / pm_loc.name)
            copied += 1
    elif step_name in ("setup", "town_setups"):
        for f in staging_subdir.rglob("*.txt"):
            rel = f.relative_to(staging_subdir)
            dest = MOD_ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied += 1
    elif step_name == "rank_overrides":
        for f in staging_subdir.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(staging_subdir)
            dest = MOD_ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied += 1

    return copied


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--steps", type=str, default=None,
                    help="Comma-separated step numbers to run (default: all)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show commands without executing")
    ap.add_argument("--list", action="store_true",
                    help="List available steps")
    args = ap.parse_args()

    if args.list:
        print("Available steps:")
        for num, name, desc, _ in STEPS:
            print(f"  {num}. {name:20s} — {desc}")
        return

    selected = None
    if args.steps:
        selected = {int(s.strip()) for s in args.steps.split(",")}

    staging = Path(tempfile.mkdtemp(prefix="sul_rebuild_"))
    print(f"Staging directory: {staging}")
    print(f"Mod root: {MOD_ROOT}\n")

    failed = []
    succeeded = []

    for num, name, desc, func in STEPS:
        if selected and num not in selected:
            continue

        print(f"{'='*60}")
        print(f"Step {num}: {desc}")
        print(f"{'='*60}")

        if args.dry_run:
            cmd, _ = func(staging, dry_run=True)
            print(f"  Would run: {' '.join(str(c) for c in cmd)}")
            succeeded.append(num)
            continue

        try:
            cmd, outputs = func(staging, dry_run=False)

            # Format + copy staged outputs to mod (for steps that use staging)
            step_staging = staging / name
            if step_staging.exists():
                fmt_count = _format_staged_files(step_staging)
                if fmt_count:
                    print(f"  Formatted {fmt_count} files")
                copied = _copy_staging_to_mod(step_staging, name)
                if copied:
                    print(f"  Copied {copied} files to mod")

            succeeded.append(num)
            print(f"  Step {num} OK\n")

        except subprocess.CalledProcessError as e:
            print(f"  FAILED (exit code {e.returncode})\n", file=sys.stderr)
            failed.append(num)
        except Exception as e:
            print(f"  FAILED: {e}\n", file=sys.stderr)
            failed.append(num)

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Succeeded: {succeeded}")
    if failed:
        print(f"  FAILED: {failed}")
        sys.exit(1)
    else:
        print(f"  All steps completed successfully")

    # Clean up staging
    shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
