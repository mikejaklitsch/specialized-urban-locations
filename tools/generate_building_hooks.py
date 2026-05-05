#!/usr/bin/env python3
"""
Generate Paradox script files for EPBM (Estates Pay Building Maintenance).

Mod-agnostic generator: parses vanilla building_types and production_methods,
optionally overlays a mod's building_types (handling file replacement, INJECT:,
and REPLACE: directives), then produces the generated script files.

Mod-defined buildings get hooks written directly into their source files.
Vanilla-only buildings get INJECT/REPLACE blocks in generated output files.

Output files (written to --output directory):
  Vanilla-only buildings:
    in_game/common/building_types/epbm_generated_inject.txt
    in_game/common/building_types/epbm_generated_replace.txt
  Always:
    in_game/common/scripted_effects/epbm_generated_init_effects.txt
    in_game/common/international_organizations/epbm_generated_ios.txt
    in_game/common/biases/epbm_generated_biases.txt
    main_menu/localization/english/epbm_ios_l_english.yml

Usage:
  # Vanilla only
  python generate_building_hooks.py --vanilla /path/to/game/in_game --output /path/to/mod

  # With mod overlay (hooks written into mod files, INJECT/REPLACE for vanilla)
  python generate_building_hooks.py --vanilla /path/to/game/in_game --mod /path/to/mod/in_game --output /path/to/output

  # With exclusion list
  python generate_building_hooks.py --vanilla ... --mod ... --output ... --exclude exclusions.txt
"""

import argparse
import re
import sys
from collections import OrderedDict
from pathlib import Path

# Keys in PM definitions that are NOT goods
PM_META_KEYS = {"category", "no_upkeep", "potential", "produced", "output"}

# Configurable prefix for all generated names (set from --prefix arg)
PREFIX = "epbm"

# Files to skip when scanning building_types directories
SKIP_FILES = {"readme.txt", "__readme.txt", "00_unique_buildings_to_make_obsolete.txt"}

PDX_FORMAT_DIR = Path("/mnt/c/Users/Mjaklitsch/Documents/pdx-format")


def _format_files(filepaths):
    """Format files using pdx_format, imported fresh to avoid namespace collisions."""
    paths = [Path(f) for f in filepaths if Path(f).exists()]
    if not paths or not PDX_FORMAT_DIR.exists():
        return
    import importlib
    sys.path.insert(0, str(PDX_FORMAT_DIR))
    try:
        pdx_config = importlib.import_module("pdx_format.config")
        pdx_file_io = importlib.import_module("pdx_format.file_io")
        config = pdx_config.FormatConfig()
        for p in paths:
            pdx_file_io.format_file(p, config)
            pdx_file_io.format_file(p, config)
    except (ImportError, Exception) as e:
        print(f"  WARNING: pdx-format failed: {e}")
    finally:
        sys.path.remove(str(PDX_FORMAT_DIR))


def _p(name):
    """Prefix a name with the configured PREFIX. e.g. _p('buildings') -> 'epbm_buildings'."""
    return f"{PREFIX}_{name}"


# ─────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────

def strip_bom(text):
    return text.lstrip("\ufeff")


def strip_comments(text):
    """Remove # comments (but not inside quotes)."""
    lines = []
    for line in text.split("\n"):
        in_quote = False
        result = []
        for ch in line:
            if ch == '"':
                in_quote = not in_quote
            elif ch == '#' and not in_quote:
                break
            result.append(ch)
        lines.append("".join(result))
    return "\n".join(lines)


def tokenize(text):
    """Simple tokenizer for Paradox script: yields tokens (strings, braces, =, values)."""
    text = strip_bom(text)
    text = strip_comments(text)
    i = 0
    n = len(text)
    while i < n:
        if text[i] in " \t\r\n":
            i += 1
            continue
        if text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == '\\':
                    j += 1
                j += 1
            yield text[i+1:j]
            i = j + 1
            continue
        if text[i] in '{}=':
            yield text[i]
            i += 1
            continue
        j = i
        while j < n and text[j] not in " \t\r\n{}=\"":
            j += 1
        yield text[i:j]
        i = j


def parse_block(tokens, idx):
    """
    Parse a { ... } block starting at tokens[idx] which should be '{'.
    Returns (dict, next_idx).
    """
    assert tokens[idx] == '{', f"Expected '{{' at index {idx}, got '{tokens[idx]}'"
    idx += 1
    result = OrderedDict()
    while idx < len(tokens) and tokens[idx] != '}':
        key = tokens[idx]
        idx += 1
        if idx < len(tokens) and tokens[idx] == '=':
            idx += 1  # skip =
            if idx < len(tokens) and tokens[idx] == '{':
                val, idx = parse_block(tokens, idx)
            else:
                val = tokens[idx]
                idx += 1
        else:
            # Bare value (no =), common in lists like possible_production_methods
            val = True
            if key in result:
                if isinstance(result[key], list):
                    result[key].append(val)
                else:
                    result[key] = [result[key], val]
                continue
            result[key] = val
            continue
        if key in result:
            if isinstance(result[key], list):
                result[key].append(val)
            else:
                result[key] = [result[key], val]
        else:
            result[key] = val
    if idx < len(tokens):
        idx += 1  # skip '}'
    return result, idx


def parse_file(filepath):
    """Parse a Paradox script file into a dict of top-level definitions."""
    text = filepath.read_text(encoding="utf-8-sig")
    toks = list(tokenize(text))
    result = OrderedDict()
    idx = 0
    while idx < len(toks):
        key = toks[idx]
        idx += 1
        if idx < len(toks) and toks[idx] == '=':
            idx += 1
            if idx < len(toks) and toks[idx] == '{':
                val, idx = parse_block(toks, idx)
            else:
                val = toks[idx]
                idx += 1
        else:
            val = True
        if key in result:
            if isinstance(result[key], list):
                result[key].append(val)
            else:
                result[key] = [result[key], val]
        else:
            result[key] = val
    return result


# ─────────────────────────────────────────────
# Exclusion list
# ─────────────────────────────────────────────

def load_exclusions(filepath):
    """Load building exclusion list from a text file. One name per line, # comments."""
    if filepath is None:
        return set()
    path = Path(filepath)
    if not path.exists():
        print(f"  WARNING: Exclusion file not found: {filepath}")
        return set()
    exclusions = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            exclusions.add(line)
    return exclusions


# ─────────────────────────────────────────────
# Parse production methods
# ─────────────────────────────────────────────

def parse_production_methods(vanilla_dir, mod_dir=None):
    """
    Parse unsorted_building_inputs.txt from vanilla (and mod overlay if present).
    Returns dict: pm_name -> { 'goods': OrderedDict, 'no_upkeep': bool, 'has_output': bool, 'has_potential': bool }
    """
    pms = {}

    # Parse vanilla PMs
    vanilla_pm = vanilla_dir / "common" / "production_methods" / "unsorted_building_inputs.txt"
    if vanilla_pm.exists():
        pms.update(_parse_pm_file(vanilla_pm))

    # Overlay mod PMs if present
    if mod_dir:
        mod_pm = mod_dir / "common" / "production_methods" / "unsorted_building_inputs.txt"
        if mod_pm.exists():
            pms.update(_parse_pm_file(mod_pm))

    return pms


def _parse_pm_file(filepath):
    """Parse a single production methods file."""
    data = parse_file(filepath)
    pms = {}
    for name, block in data.items():
        if not isinstance(block, dict):
            continue
        pm = {
            'goods': OrderedDict(),
            'output_goods': OrderedDict(),
            'no_upkeep': 'no_upkeep' in block and block['no_upkeep'] == 'yes',
            'has_output': 'produced' in block or 'output' in block,
            'has_potential': 'potential' in block,
        }
        for k, v in block.items():
            if k not in PM_META_KEYS and isinstance(v, str):
                try:
                    pm['goods'][k] = float(v)
                except ValueError:
                    pass
        # Extract output good: 'produced = <good_name>' + 'output = <quantity>'
        produced = block.get('produced')
        output_qty = block.get('output')
        if isinstance(produced, str) and produced not in ('yes', 'no'):
            qty = 1.0
            if isinstance(output_qty, str):
                try:
                    qty = float(output_qty)
                except ValueError:
                    pass
            pm['output_goods'][produced] = qty
        pms[name] = pm
    return pms


# ─────────────────────────────────────────────
# Parse building types with mod overlay
# ─────────────────────────────────────────────

def _parse_building_block(bname, block, source_file):
    """Parse a single building definition block into our internal format."""
    b = {
        'file': source_file,
        'estate': block.get('estate'),
        'is_foreign': block.get('is_foreign') == 'yes',
        'has_on_built': 'on_built' in block,
        'has_on_destroyed': 'on_destroyed' in block,
        'possible_pms': [],
        'unique_pms': OrderedDict(),
        'raw': block,
    }
    ppm = block.get('possible_production_methods')
    if isinstance(ppm, dict):
        b['possible_pms'] = [k for k in ppm.keys()]
    elif isinstance(ppm, list):
        b['possible_pms'] = ppm

    upm = block.get('unique_production_methods')
    if isinstance(upm, list):
        merged = OrderedDict()
        for d in upm:
            if isinstance(d, dict):
                merged.update(d)
        upm = merged
    if isinstance(upm, dict):
        for pm_name, pm_block in upm.items():
            if isinstance(pm_block, dict):
                goods = OrderedDict()
                output_goods = OrderedDict()
                for k, v in pm_block.items():
                    if k not in PM_META_KEYS and isinstance(v, str):
                        try:
                            goods[k] = float(v)
                        except ValueError:
                            pass
                # Extract output good from inline PM
                produced = pm_block.get('produced')
                output_qty = pm_block.get('output')
                if isinstance(produced, str) and produced not in ('yes', 'no'):
                    qty = 1.0
                    if isinstance(output_qty, str):
                        try:
                            qty = float(output_qty)
                        except ValueError:
                            pass
                    output_goods[produced] = qty
                b['unique_pms'][pm_name] = {
                    'goods': goods,
                    'output_goods': output_goods,
                    'has_output': 'produced' in pm_block or 'output' in pm_block,
                    'no_upkeep': pm_block.get('no_upkeep') == 'yes',
                    'is_maintenance': pm_block.get('category') == 'building_maintenance',
                }
    return b


def _scan_building_dir(directory):
    """
    Scan a building_types directory. Returns:
      buildings: dict of building_name -> building_data (for regular definitions)
      injects: list of (building_name, block_dict, source_file)
      replaces: list of (building_name, block_dict, source_file)
      files_present: set of filenames found
    """
    buildings = OrderedDict()
    injects = []
    replaces = []
    files_present = set()

    for f in sorted(directory.iterdir()):
        if f.name.lower() in SKIP_FILES or not f.name.endswith(".txt"):
            continue
        if f.name.startswith(f"{PREFIX}_generated_"):
            continue
        files_present.add(f.name)
        data = parse_file(f)
        for key, block in data.items():
            if not isinstance(block, dict):
                continue

            if key.startswith("INJECT:"):
                bname = key[7:]  # strip "INJECT:" prefix
                injects.append((bname, block, f))
            elif key.startswith("REPLACE:"):
                bname = key[8:]  # strip "REPLACE:" prefix
                replaces.append((bname, block, f))
            else:
                buildings[key] = _parse_building_block(key, block, f)

    return buildings, injects, replaces, files_present


def _apply_inject(building, inject_block):
    """Apply an INJECT block to a building's parsed data (merge properties)."""
    block = inject_block
    raw = building['raw']

    # Merge top-level keys
    for k, v in block.items():
        if k == 'possible_production_methods' and isinstance(v, dict):
            # Merge PM references
            ppm = raw.get('possible_production_methods', OrderedDict())
            if not isinstance(ppm, dict):
                ppm = OrderedDict()
            ppm.update(v)
            raw['possible_production_methods'] = ppm
            building['possible_pms'] = list(ppm.keys())
        elif k == 'unique_production_methods' and isinstance(v, dict):
            upm = raw.get('unique_production_methods', OrderedDict())
            if not isinstance(upm, dict):
                upm = OrderedDict()
            upm.update(v)
            raw['unique_production_methods'] = upm
            # Re-parse unique PMs
            for pm_name, pm_block in v.items():
                if isinstance(pm_block, dict):
                    goods = OrderedDict()
                    output_goods = OrderedDict()
                    for gk, gv in pm_block.items():
                        if gk not in PM_META_KEYS and isinstance(gv, str):
                            try:
                                goods[gk] = float(gv)
                            except ValueError:
                                pass
                    produced = pm_block.get('produced')
                    output_qty = pm_block.get('output')
                    if isinstance(produced, str) and produced not in ('yes', 'no'):
                        qty = 1.0
                        if isinstance(output_qty, str):
                            try:
                                qty = float(output_qty)
                            except ValueError:
                                pass
                        output_goods[produced] = qty
                    building['unique_pms'][pm_name] = {
                        'goods': goods,
                        'output_goods': output_goods,
                        'has_output': 'produced' in pm_block or 'output' in pm_block,
                        'no_upkeep': pm_block.get('no_upkeep') == 'yes',
                        'is_maintenance': pm_block.get('category') == 'building_maintenance',
                    }
        elif k == 'on_built':
            building['has_on_built'] = True
            raw['on_built'] = v
        elif k == 'on_destroyed':
            building['has_on_destroyed'] = True
            raw['on_destroyed'] = v
        elif k == 'estate':
            building['estate'] = v
            raw['estate'] = v
        else:
            raw[k] = v


def parse_all_buildings(vanilla_dir, mod_dir=None):
    """
    Parse all building files from vanilla, optionally overlaying a mod.
    Returns dict: building_name -> building_data
    """
    vanilla_bt_dir = vanilla_dir / "common" / "building_types"
    if not vanilla_bt_dir.exists():
        print(f"ERROR: Vanilla building_types directory not found: {vanilla_bt_dir}")
        sys.exit(1)

    # Step 1: Parse vanilla buildings
    vanilla_buildings, vanilla_injects, vanilla_replaces, vanilla_files = _scan_building_dir(vanilla_bt_dir)
    buildings = vanilla_buildings

    if mod_dir:
        mod_bt_dir = mod_dir / "common" / "building_types"
        if mod_bt_dir.exists():
            mod_buildings, mod_injects, mod_replaces, mod_files = _scan_building_dir(mod_bt_dir)

            # Step 2: For files with the same name, mod replaces vanilla entirely
            replaced_files = vanilla_files & mod_files
            if replaced_files:
                # Remove vanilla buildings from replaced files
                buildings = OrderedDict(
                    (k, v) for k, v in buildings.items()
                    if v['file'].name not in replaced_files
                )
                print(f"  Mod replaces {len(replaced_files)} vanilla file(s): {', '.join(sorted(replaced_files))}")

            # Step 3: Add mod buildings (both from replaced files and new files)
            buildings.update(mod_buildings)

            # Step 4: Apply INJECT directives from mod
            for bname, block, source in mod_injects:
                if bname in buildings:
                    _apply_inject(buildings[bname], block)
                else:
                    print(f"  WARNING: INJECT target '{bname}' not found, skipping")

            # Step 5: Apply REPLACE directives from mod
            for bname, block, source in mod_replaces:
                buildings[bname] = _parse_building_block(bname, block, source)

        else:
            print(f"  No building_types directory in mod, using vanilla only")

    return buildings


# ─────────────────────────────────────────────
# Classify qualifying buildings and PMs
# ─────────────────────────────────────────────

def classify(buildings, pms, exclusions):
    """
    Determine which buildings qualify for maintenance tracking.
    A building qualifies if:
      - Not in the exclusion list
      - Has at least one qualifying PM (category=building_maintenance, has goods, no no_upkeep, no output)

    Returns:
      qualifying: list of (building_name, is_foreign, estate) tuples
                  where estate is None (split by estate power) or an estate key string
      all_pm_goods: dict pm_name -> OrderedDict(good->amount)
    """
    qualifying = []
    all_pm_goods = OrderedDict()
    excluded_count = 0

    # Pass 1: catalog every qualifying maintenance PM
    for pm_name, pm in pms.items():
        if pm['no_upkeep'] or pm['has_output']:
            continue
        if not pm['goods']:
            continue
        all_pm_goods[pm_name] = pm['goods']

    for bname, b in buildings.items():
        for pm_name, pm_data in b['unique_pms'].items():
            if not pm_data.get('is_maintenance', False):
                continue
            if pm_data.get('no_upkeep', False) or pm_data.get('has_output', False):
                continue
            if not pm_data['goods']:
                continue
            all_pm_goods[pm_name] = pm_data['goods']

    # Pass 2: any building that references at least one catalog PM qualifies
    for bname, b in buildings.items():
        if bname in exclusions:
            excluded_count += 1
            continue

        has_tracked = False
        for pm_name in b['possible_pms']:
            if pm_name in all_pm_goods:
                has_tracked = True
                break
        if not has_tracked:
            for pm_name in b['unique_pms']:
                if pm_name in all_pm_goods:
                    has_tracked = True
                    break
        if not has_tracked:
            continue

        estate = b['estate']
        qualifying.append((bname, b['is_foreign'], estate))

    if excluded_count > 0:
        print(f"  Excluded {excluded_count} building(s) from tracking")

    return qualifying, all_pm_goods


# ─────────────────────────────────────────────
# GDP classification: buildings that produce goods
# ─────────────────────────────────────────────

def classify_gdp(buildings, pms):
    """
    Identify all buildings that produce output goods (for GDP tracking).
    No exclusions — every building that produces goods contributes to GDP.

    Returns:
      gdp_buildings: dict of building_name -> set(output_good_names)
      all_output_goods: sorted list of unique output goods across all buildings
    """
    gdp_buildings = {}
    all_goods = set()

    for bname, b in buildings.items():
        bldg_goods = set()

        # Check external PMs for output goods
        for pm_name in b['possible_pms']:
            if pm_name not in pms:
                continue
            pm = pms[pm_name]
            if pm.get('output_goods'):
                bldg_goods.update(pm['output_goods'].keys())

        # Check inline PMs for output goods
        for pm_name, pm_data in b['unique_pms'].items():
            if pm_data.get('output_goods'):
                bldg_goods.update(pm_data['output_goods'].keys())

        if bldg_goods:
            gdp_buildings[bname] = bldg_goods
            all_goods.update(bldg_goods)

    all_output_goods = sorted(all_goods)
    return gdp_buildings, all_output_goods


# ─────────────────────────────────────────────
# GDP code generation
# ─────────────────────────────────────────────

def generate_gdp_effects(gdp_buildings, all_output_goods, buildings):
    """
    Generate sul_gdp_generated_effects.txt containing:
    1. Per-good record_built / record_destroyed effects (location scope)
    2. Dispatch effects for on_built/on_destroyed hooks (building scope)
    3. Init dispatch effect (building scope, game start scan)
    4. Yearly per-location GDP computation (location scope)
    """
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# GDP tracking: per-good production map + yearly output computation.",
        "# sul_local_goods variable map on each location tracks which goods are",
        "# produced there, keyed by goods:<name> with refcount values. The yearly",
        "# computation iterates all known output goods to sum goods_output x price.",
        "",
    ]

    # ── Part 1: Per-good record effects (location scope) ──
    for good in all_output_goods:
        lines.append(f"# Location scope: increment sul_local_goods refcount for {good}")
        lines.append(f"sul_gdp_record_{good}_built = {{")
        lines.append(f"\tif = {{")
        lines.append(f"\t\tlimit = {{")
        lines.append(f"\t\t\thas_variable_map = sul_local_goods")
        lines.append(f"\t\t\tis_key_in_variable_map = {{ name = sul_local_goods target = goods:{good} }}")
        lines.append(f"\t\t}}")
        lines.append(f'\t\tset_local_variable = {{ name = sul_gdp_count value = {{ value = "variable_map(sul_local_goods|goods:{good})" add = 1 }} }}')
        lines.append(f"\t\tadd_to_variable_map = {{ name = sul_local_goods key = goods:{good} value = local_var:sul_gdp_count }}")
        lines.append(f"\t}}")
        lines.append(f"\telse = {{")
        lines.append(f"\t\tadd_to_variable_map = {{ name = sul_local_goods key = goods:{good} value = 1 }}")
        lines.append(f"\t}}")
        lines.append("}")
        lines.append("")

        lines.append(f"# Location scope: decrement sul_local_goods refcount for {good}")
        lines.append(f"sul_gdp_record_{good}_destroyed = {{")
        lines.append(f"\tif = {{")
        lines.append(f"\t\tlimit = {{")
        lines.append(f"\t\t\thas_variable_map = sul_local_goods")
        lines.append(f"\t\t\tis_key_in_variable_map = {{ name = sul_local_goods target = goods:{good} }}")
        lines.append(f"\t\t}}")
        lines.append(f'\t\tset_local_variable = {{ name = sul_gdp_count value = {{ value = "variable_map(sul_local_goods|goods:{good})" subtract = 1 }} }}')
        lines.append(f"\t\tadd_to_variable_map = {{ name = sul_local_goods key = goods:{good} value = local_var:sul_gdp_count }}")
        lines.append(f"\t}}")
        lines.append("}")
        lines.append("")

    # ── Part 2: Dispatch effects (building scope -> location scope) ──
    # Collect all goods that any building can produce, per building
    # The dispatch checks building_produced_goods for each possible output good

    # on_built/on_destroyed and init all run in building scope.
    # Scope into location to reach the sul_local_goods variable map.
    lines.append("# Building scope (on_built): scope into location for map writes")
    lines.append("sul_gdp_on_building_built = {")
    lines.append("\tsave_temporary_scope_as = sul_gdp_bldg")
    lines.append("\tlocation = {")
    for good in all_output_goods:
        lines.append(f"\t\tif = {{")
        lines.append(f"\t\t\tlimit = {{ scope:sul_gdp_bldg = {{ building_produced_goods = goods:{good} }} }}")
        lines.append(f"\t\t\tsul_gdp_record_{good}_built = yes")
        lines.append(f"\t\t}}")
    lines.append("\t}")
    lines.append("}")
    lines.append("")

    lines.append("# Building scope (on_destroyed): scope into location for map writes")
    lines.append("sul_gdp_on_building_destroyed = {")
    lines.append("\tsave_temporary_scope_as = sul_gdp_bldg")
    lines.append("\tlocation = {")
    for good in all_output_goods:
        lines.append(f"\t\tif = {{")
        lines.append(f"\t\t\tlimit = {{ scope:sul_gdp_bldg = {{ building_produced_goods = goods:{good} }} }}")
        lines.append(f"\t\t\tsul_gdp_record_{good}_destroyed = yes")
        lines.append(f"\t\t}}")
    lines.append("\t}")
    lines.append("}")
    lines.append("")

    lines.append("# Building scope (every_buildings_in_location at game start)")
    lines.append("sul_gdp_init_building = {")
    lines.append("\tsave_temporary_scope_as = sul_gdp_bldg")
    lines.append("\tlocation = {")
    for good in all_output_goods:
        lines.append(f"\t\tif = {{")
        lines.append(f"\t\t\tlimit = {{ scope:sul_gdp_bldg = {{ building_produced_goods = goods:{good} }} }}")
        lines.append(f"\t\t\tsul_gdp_record_{good}_built = yes")
        lines.append(f"\t\t}}")
    lines.append("\t}")
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Read raw building text for REPLACE blocks
# ─────────────────────────────────────────────

def read_raw_building_text(filepath, building_name):
    """
    Extract the raw text of a building definition from a file.
    Returns the text between building_name = { ... } including braces.
    Also handles REPLACE:building_name and INJECT:building_name prefixes,
    stripping the directive prefix from the returned text.
    """
    text = filepath.read_text(encoding="utf-8-sig")
    text = strip_bom(text)

    # Try bare name first, then REPLACE:name, then INJECT:name
    for prefix in ('', 'REPLACE:', 'INJECT:'):
        full_name = prefix + building_name
        pattern = re.compile(r'^(' + re.escape(full_name) + r')\s*=\s*\{', re.MULTILINE)
        match = pattern.search(text)
        if match:
            brace_start = text.index('{', match.start())
            depth = 0
            i = brace_start
            while i < len(text):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        raw = text[match.start():i+1]
                        # Strip REPLACE:/INJECT: prefix so callers get bare definition
                        if prefix:
                            raw = raw[len(prefix):]
                        return raw
                i += 1
    return None


def inject_on_built_hook(raw_text, building_name, gdp_tracked=False):
    """
    For REPLACE buildings: insert our list-management hook into existing on_built,
    and add on_destroyed if it doesn't exist.
    Also renames inline unique_production_methods PM names to avoid duplicates.
    If gdp_tracked, also adds GDP dispatch hooks.
    Returns modified building text.
    """
    list_name = _p('buildings')
    add_code = (
        f"\n\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}"
        f"\n\t\t{_p('on_building_built')} = yes"
    )
    remove_code = (
        f"\n\t\tlocation = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}"
        f"\n\t\t{_p('on_building_destroyed')} = yes"
    )
    if gdp_tracked:
        add_code += f"\n\t\tsul_gdp_on_building_built = yes"
        remove_code += f"\n\t\tsul_gdp_on_building_destroyed = yes"

    # Rename inline PM names to avoid duplicate PM name errors
    upm_pattern = re.compile(r'unique_production_methods\s*=\s*\{')
    upm_match = upm_pattern.search(raw_text)
    if upm_match:
        brace_start = upm_match.end() - 1
        depth = 0
        i = brace_start
        while i < len(raw_text):
            if raw_text[i] == '{':
                depth += 1
            elif raw_text[i] == '}':
                depth -= 1
                if depth == 0:
                    upm_end = i + 1
                    break
            i += 1
        else:
            upm_end = len(raw_text)
        upm_block = raw_text[upm_match.start():upm_end]
        pm_def_pattern = re.compile(r'(\t\t)(\w+)(\s*=\s*\{)')
        def rename_pm(m):
            name = m.group(2)
            if name in ('unique_production_methods', 'category', 'potential', 'no_upkeep'):
                return m.group(0)
            # Strip any existing prefix layers to prevent stacking across runs
            stripped = re.sub(r'^(' + re.escape(PREFIX) + r'_)+', '', name)
            return f"{m.group(1)}{_p(stripped)}{m.group(3)}"
        new_upm_block = pm_def_pattern.sub(rename_pm, upm_block)
        raw_text = raw_text[:upm_match.start()] + new_upm_block + raw_text[upm_end:]

    # Find on_built block and inject before its closing brace
    on_built_pattern = re.compile(r'(on_built\s*=\s*\{)')
    match = on_built_pattern.search(raw_text)
    if match:
        brace_start = match.end() - 1
        depth = 0
        i = brace_start
        while i < len(raw_text):
            if raw_text[i] == '{':
                depth += 1
            elif raw_text[i] == '}':
                depth -= 1
                if depth == 0:
                    raw_text = raw_text[:i] + add_code + "\n\t" + raw_text[i:]
                    break
            i += 1

    # Add on_destroyed if not present
    if 'on_destroyed' not in raw_text:
        last_brace = raw_text.rindex('}')
        on_destroyed = f"\n\ton_destroyed = {{{remove_code}\n\t}}"
        raw_text = raw_text[:last_brace] + on_destroyed + "\n" + raw_text[last_brace:]
    else:
        on_destroyed_pattern = re.compile(r'(on_destroyed\s*=\s*\{)')
        match = on_destroyed_pattern.search(raw_text)
        if match:
            brace_start = match.end() - 1
            depth = 0
            i = brace_start
            while i < len(raw_text):
                if raw_text[i] == '{':
                    depth += 1
                elif raw_text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        raw_text = raw_text[:i] + remove_code + "\n\t" + raw_text[i:]
                        break
                i += 1

    return raw_text


# ─────────────────────────────────────────────
# In-place mode: strip and inject hooks into mod files
# ─────────────────────────────────────────────

# Lines injected by EPBM that we need to detect and strip.
# We match the functional lines, not comments.
def _strip_epbm_injected_lines(text):
    """
    Remove all PREFIX-injected hook code and GDP hook code from file text. Idempotent.
    Handles both inline injections (inside existing on_built/on_destroyed)
    and whole-block injections (on_built/on_destroyed added by the generator).
    Uses the current PREFIX to identify injected lines.
    Also strips sul_gdp_on_building_built/destroyed lines.
    """
    built_marker = _p('on_building_built')
    destroyed_marker = _p('on_building_destroyed')
    gdp_built_marker = 'sul_gdp_on_building_built'
    gdp_destroyed_marker = 'sul_gdp_on_building_destroyed'
    list_name = _p('buildings')

    has_epbm = built_marker in text or destroyed_marker in text
    has_gdp = gdp_built_marker in text or gdp_destroyed_marker in text
    if not has_epbm and not has_gdp:
        return text

    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip the add_to_variable_list / remove_list_variable + marker call pairs
        if list_name in stripped and 'add_to_variable_list' in stripped:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and built_marker in lines[j]:
                i = j + 1
                continue

        if list_name in stripped and 'remove_list_variable' in stripped:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and destroyed_marker in lines[j]:
                i = j + 1
                continue

        # Skip standalone marker lines (EPBM and GDP)
        if stripped == f'{built_marker} = yes' or stripped == f'{destroyed_marker} = yes':
            i += 1
            continue
        if stripped == f'{gdp_built_marker} = yes' or stripped == f'{gdp_destroyed_marker} = yes':
            i += 1
            continue

        result.append(line)
        i += 1

    text = '\n'.join(result)
    text = _remove_empty_hook_blocks(text)

    # Collapse runs of 3+ blank lines down to 1
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text


def _remove_empty_hook_blocks(text):
    """Remove on_built = { } and on_destroyed = { } blocks that contain only whitespace."""
    for hook in ('on_built', 'on_destroyed'):
        pattern = re.compile(
            r'\n[ \t]*' + hook + r'\s*=\s*\{[ \t]*\n([ \t]*\n)*[ \t]*\}',
        )
        text = pattern.sub('', text)
    return text


def _find_building_bounds(text, building_name):
    """
    Find the start and end positions of a building definition in file text.
    Returns (start, end) where text[start:end] is the full building block
    including 'building_name = { ... }'.
    Returns None if not found.
    """
    pattern = re.compile(r'^(' + re.escape(building_name) + r')\s*=\s*\{', re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None

    start = match.start()
    brace_start = text.index('{', match.start())
    depth = 0
    i = brace_start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return (start, i + 1)
        i += 1
    return None


def _inject_hook_into_building_text(building_text, has_on_built, has_on_destroyed, gdp_tracked=False):
    """
    Inject EPBM hooks (and optionally GDP hooks) into a single building's text.
    If the building already has on_built/on_destroyed, inject inside them.
    If not, add new blocks before the building's closing brace.
    Returns modified building text.
    """
    list_name = _p('buildings')
    add_code_lines = (
        f"\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}\n"
        f"\t\t{_p('on_building_built')} = yes\n"
    )
    remove_code_lines = (
        f"\t\tlocation = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}\n"
        f"\t\t{_p('on_building_destroyed')} = yes\n"
    )
    if gdp_tracked:
        add_code_lines += f"\t\tsul_gdp_on_building_built = yes\n"
        remove_code_lines += f"\t\tsul_gdp_on_building_destroyed = yes\n"

    text = building_text

    # Handle on_built
    if has_on_built:
        # Inject before the closing brace of on_built
        on_built_pattern = re.compile(r'on_built\s*=\s*\{')
        match = on_built_pattern.search(text)
        if match:
            brace_start = match.end() - 1
            depth = 0
            i = brace_start
            while i < len(text):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        text = text[:i] + add_code_lines + "\t" + text[i:]
                        break
                i += 1
    else:
        # Add a new on_built block before the building's closing brace
        last_brace = text.rindex('}')
        on_built_block = f"\ton_built = {{\n{add_code_lines}\t}}\n"
        text = text[:last_brace] + on_built_block + text[last_brace:]

    # Handle on_destroyed
    if has_on_destroyed:
        on_destroyed_pattern = re.compile(r'on_destroyed\s*=\s*\{')
        match = on_destroyed_pattern.search(text)
        if match:
            brace_start = match.end() - 1
            depth = 0
            i = brace_start
            while i < len(text):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        text = text[:i] + remove_code_lines + "\t" + text[i:]
                        break
                i += 1
    else:
        last_brace = text.rindex('}')
        on_destroyed_block = f"\ton_destroyed = {{\n{remove_code_lines}\t}}\n"
        text = text[:last_brace] + on_destroyed_block + text[last_brace:]

    return text


def apply_in_place(qualifying, buildings, mod_dir, gdp_buildings=None):
    """
    In-place mode: modify mod building files directly.
    For each qualifying non-foreign building whose source file is in the mod
    directory, inject EPBM hooks. Buildings from vanilla-only files are skipped
    (they go into INJECT/REPLACE output instead).
    If gdp_buildings is provided, also adds GDP hooks for buildings that produce goods.
    Returns (modified_file_count, vanilla_only_buildings) where vanilla_only_buildings
    is a list of (bname, is_foreign, estate) for buildings not in mod files.
    """
    if gdp_buildings is None:
        gdp_buildings = {}
    mod_bt_dir = mod_dir / "common" / "building_types"

    # Group qualifying buildings by source file, separating mod vs vanilla
    mod_buildings_by_file = {}
    vanilla_only = []

    for bname, is_foreign, estate in qualifying:
        if is_foreign:
            continue
        b = buildings[bname]
        filepath = b['file']

        # Check if this file is in the mod directory
        try:
            filepath.relative_to(mod_bt_dir)
            mod_buildings_by_file.setdefault(filepath, []).append((bname, b))
        except ValueError:
            # File is in vanilla, not mod — needs INJECT/REPLACE instead
            vanilla_only.append((bname, is_foreign, estate))

    if vanilla_only:
        print(f"  {len(vanilla_only)} building(s) from vanilla-only files (will generate INJECT/REPLACE)")

    modified_files = 0

    for filepath, bldg_list in sorted(mod_buildings_by_file.items(), key=lambda x: x[0].name):
        text = filepath.read_text(encoding="utf-8-sig")
        original = text

        # Strip all existing EPBM hooks from the file first
        text = _strip_epbm_injected_lines(text)

        # Re-parse to get fresh on_built/on_destroyed state after stripping
        # (a building that had on_built only because of EPBM now won't)
        stripped_toks = list(tokenize(text))
        stripped_blocks = {}
        idx = 0
        while idx < len(stripped_toks):
            key = stripped_toks[idx]
            idx += 1
            if idx < len(stripped_toks) and stripped_toks[idx] == '=':
                idx += 1
                if idx < len(stripped_toks) and stripped_toks[idx] == '{':
                    val, idx = parse_block(stripped_toks, idx)
                else:
                    val = stripped_toks[idx]
                    idx += 1
            else:
                val = True
            if isinstance(val, dict):
                stripped_blocks[key] = val

        # Inject hooks into each qualifying building
        for bname, b in bldg_list:
            bounds = _find_building_bounds(text, bname)
            if bounds is None:
                print(f"  WARNING: Could not find '{bname}' in {filepath.name}, skipping")
                continue

            start, end = bounds
            building_text = text[start:end]

            # Check on_built/on_destroyed state from the stripped parse
            block = stripped_blocks.get(bname, {})
            has_on_built = 'on_built' in block
            has_on_destroyed = 'on_destroyed' in block

            is_gdp = bname in gdp_buildings
            modified = _inject_hook_into_building_text(building_text, has_on_built, has_on_destroyed, gdp_tracked=is_gdp)
            text = text[:start] + modified + text[end:]

        if text != original:
            filepath.write_text(text, encoding="utf-8-sig")
            modified_files += 1
            injected = len(bldg_list)
            print(f"  {filepath.name}: injected hooks into {injected} building(s)")
        else:
            print(f"  {filepath.name}: no changes needed ({len(bldg_list)} building(s) already hooked)")

    return modified_files, vanilla_only


# ─────────────────────────────────────────────
# Code generation (default mode)
# ─────────────────────────────────────────────

def _is_mod_file(building, mod_bt_dir):
    """True if this building is defined in a mod file (skip for INJECT/REPLACE)."""
    if mod_bt_dir is None:
        return False
    try:
        building['file'].relative_to(mod_bt_dir)
        return True
    except ValueError:
        return False


def scan_existing_injects(mod_bt_dir):
    """
    Scan the mod's building_types directory for existing INJECT blocks in
    non-generated files. Returns dict: building_name -> filepath.
    Only records the first occurrence per building (duplicates are a bug).
    """
    existing = {}
    if mod_bt_dir is None or not mod_bt_dir.exists():
        return existing

    for f in sorted(mod_bt_dir.iterdir()):
        if not f.name.endswith(".txt"):
            continue
        if f.name.startswith(f"{PREFIX}_generated_"):
            continue
        text = f.read_text(encoding="utf-8-sig")
        for m in re.finditer(r'^INJECT:(\w+)\s*=\s*\{', text, re.MULTILINE):
            bname = m.group(1)
            if bname not in existing:
                existing[bname] = f
    return existing


def scan_existing_replaces(mod_bt_dir):
    """
    Scan for REPLACE blocks in non-generated mod files.
    Returns set of building names that have REPLACE blocks.
    """
    replaced = set()
    if mod_bt_dir is None or not mod_bt_dir.exists():
        return replaced

    for f in sorted(mod_bt_dir.iterdir()):
        if not f.name.endswith(".txt"):
            continue
        if f.name.startswith(f"{PREFIX}_generated_"):
            continue
        text = f.read_text(encoding="utf-8-sig")
        for m in re.finditer(r'^REPLACE:(\w+)\s*=\s*\{', text, re.MULTILINE):
            replaced.add(m.group(1))
    return replaced


def strip_hooks_from_inject_files(mod_bt_dir):
    """
    Strip previously-merged EPBM/GDP hooks from all non-generated INJECT files
    in the mod's building_types directory. Must be called BEFORE parsing buildings
    so the parser sees the clean state without our hooks.
    """
    if mod_bt_dir is None or not mod_bt_dir.exists():
        return

    for f in sorted(mod_bt_dir.iterdir()):
        if not f.name.endswith(".txt"):
            continue
        if f.name.startswith(f"{PREFIX}_generated_"):
            continue
        text = f.read_text(encoding="utf-8-sig")
        cleaned = _strip_epbm_injected_lines(text)
        if cleaned != text:
            f.write_text(cleaned, encoding="utf-8-sig")


def _build_hook_lines(bname, qualifying, gdp_buildings):
    """
    Build the on_built/on_destroyed lines for a building.
    Returns (on_built_lines, on_destroyed_lines) as lists of strings (no leading tab).
    Returns (None, None) if this building needs no hooks.
    """
    list_name = _p('buildings')
    is_epbm = any(bn == bname and not fg for bn, fg, _ in qualifying)
    is_gdp = bname in gdp_buildings

    if not is_epbm and not is_gdp:
        return None, None

    built = []
    destroyed = []

    if is_epbm:
        built.append(f"location = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}")
        built.append(f"{_p('on_building_built')} = yes")
        destroyed.append(f"location = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}")
        destroyed.append(f"{_p('on_building_destroyed')} = yes")

    if is_gdp:
        built.append("sul_gdp_on_building_built = yes")
        destroyed.append("sul_gdp_on_building_destroyed = yes")

    return built, destroyed


def merge_hooks_into_existing_injects(existing_injects, qualifying, buildings,
                                      gdp_buildings, mod_bt_dir):
    """
    For buildings that already have an INJECT block in another mod file,
    merge on_built/on_destroyed hooks directly into that INJECT block.
    Strips any previously-merged hooks first to be idempotent.
    Returns the set of building names that were merged (so they can be
    skipped in the generated inject file).
    """
    if gdp_buildings is None:
        gdp_buildings = {}

    # Determine which buildings need hooks AND have existing INJECTs
    needs_hooks = set()
    for bname, is_foreign, _ in qualifying:
        if is_foreign:
            continue
        if _is_mod_file(buildings[bname], mod_bt_dir):
            continue
        b = buildings[bname]
        if b['has_on_built'] or b['has_on_destroyed']:
            continue
        needs_hooks.add(bname)

    for bname in gdp_buildings:
        b = buildings.get(bname)
        if b is None or b['is_foreign']:
            continue
        if _is_mod_file(b, mod_bt_dir):
            continue
        if b['has_on_built'] or b['has_on_destroyed']:
            continue
        epbm_handled = any(bn == bname for bn, fg, _ in qualifying if not fg)
        if not epbm_handled:
            needs_hooks.add(bname)

    mergeable = needs_hooks & set(existing_injects.keys())
    if not mergeable:
        return set()

    # Group by file for efficient batch editing
    by_file = {}
    for bname in mergeable:
        fp = existing_injects[bname]
        by_file.setdefault(fp, []).append(bname)

    merged = set()
    for filepath, bnames in sorted(by_file.items(), key=lambda x: x[0].name):
        text = filepath.read_text(encoding="utf-8-sig")
        original = text

        for bname in bnames:
            built_lines, destroyed_lines = _build_hook_lines(bname, qualifying, gdp_buildings)
            if built_lines is None:
                continue

            # Find the INJECT:bname block and its closing brace
            pattern = re.compile(
                r'^(INJECT:' + re.escape(bname) + r')\s*=\s*\{',
                re.MULTILINE
            )
            match = pattern.search(text)
            if not match:
                continue

            brace_start = text.index('{', match.start())
            depth = 0
            i = brace_start
            while i < len(text):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        # Insert on_built + on_destroyed before the closing brace
                        # Strip trailing whitespace before } to avoid blank line accumulation
                        pre = text[:i].rstrip('\n\t ')
                        indent = "\t"
                        hook_text = f"\n{indent}on_built = {{\n"
                        for line in built_lines:
                            hook_text += f"{indent}\t{line}\n"
                        hook_text += f"{indent}}}\n"
                        hook_text += f"{indent}on_destroyed = {{\n"
                        for line in destroyed_lines:
                            hook_text += f"{indent}\t{line}\n"
                        hook_text += f"{indent}}}\n"
                        text = pre + hook_text + text[i:]
                        merged.add(bname)
                        break
                i += 1

        if text != original:
            filepath.write_text(text, encoding="utf-8-sig")
            print(f"  {filepath.name}: merged hooks into {len([b for b in bnames if b in merged])} existing INJECT block(s)")

    return merged


def _remove_injects_for_replaced(existing_injects, replaced_buildings):
    """
    Remove INJECT blocks from source files for buildings that now have
    a REPLACE block (which includes their rank flags). Prevents INJECT+REPLACE
    conflicts on the same building.
    """
    by_file = {}
    for bname in replaced_buildings:
        if bname in existing_injects:
            fp = existing_injects[bname]
            by_file.setdefault(fp, []).append(bname)

    for filepath, bnames in sorted(by_file.items(), key=lambda x: x[0].name):
        text = filepath.read_text(encoding="utf-8-sig")
        original = text

        for bname in bnames:
            # Remove the entire INJECT:bname = { ... } block
            pattern = re.compile(
                r'\n?^INJECT:' + re.escape(bname) + r'\s*=\s*\{',
                re.MULTILINE
            )
            match = pattern.search(text)
            if not match:
                continue

            brace_start = text.index('{', match.start())
            depth = 0
            i = brace_start
            while i < len(text):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        # Remove from match start to end of block (plus trailing newline)
                        end = i + 1
                        if end < len(text) and text[end] == '\n':
                            end += 1
                        start = match.start()
                        if start > 0 and text[start] == '\n':
                            start += 1
                        text = text[:start] + text[end:]
                        break
                i += 1

        if text != original:
            filepath.write_text(text, encoding="utf-8-sig")


def generate_inject(qualifying, buildings, gdp_buildings=None, mod_bt_dir=None,
                    already_merged=None):
    """Generate epbm_generated_inject.txt (INJECT blocks for buildings without on_built)."""
    if gdp_buildings is None:
        gdp_buildings = {}
    if already_merged is None:
        already_merged = set()
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# INJECT blocks: manage location tracking list on build/destroy",
        "",
    ]

    # Track which buildings already got INJECT blocks from EPBM
    injected_buildings = set()

    for bname, is_foreign, _estate in sorted(qualifying, key=lambda x: x[0]):
        b = buildings[bname]
        if is_foreign:
            continue
        if _is_mod_file(b, mod_bt_dir):
            continue
        if b['has_on_built'] or b['has_on_destroyed']:
            continue
        if bname in already_merged:
            continue

        list_name = _p('buildings')
        is_gdp = bname in gdp_buildings
        lines.append(f"# {bname}")
        lines.append(f"INJECT:{bname} = {{")
        lines.append(f"\ton_built = {{")
        lines.append(f"\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}")
        lines.append(f"\t\t{_p('on_building_built')} = yes")
        if is_gdp:
            lines.append(f"\t\tsul_gdp_on_building_built = yes")
        lines.append(f"\t}}")
        lines.append(f"\ton_destroyed = {{")
        lines.append(f"\t\tlocation = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}")
        lines.append(f"\t\t{_p('on_building_destroyed')} = yes")
        if is_gdp:
            lines.append(f"\t\tsul_gdp_on_building_destroyed = yes")
        lines.append(f"\t}}")
        lines.append("}")
        lines.append("")
        injected_buildings.add(bname)

    # GDP-only INJECT blocks: buildings that produce goods but are excluded from
    # EPBM (or have no maintenance PM). They still need on_built/on_destroyed
    # hooks to maintain the sul_local_goods variable map.
    for bname in sorted(gdp_buildings.keys()):
        if bname in injected_buildings:
            continue
        if bname in already_merged:
            continue
        b = buildings.get(bname)
        if b is None or b['is_foreign']:
            continue
        if _is_mod_file(b, mod_bt_dir):
            continue
        if b['has_on_built'] or b['has_on_destroyed']:
            continue
        # Check if already handled by REPLACE (has existing hooks from EPBM)
        epbm_handled = any(bn == bname for bn, fg, _ in qualifying if not fg)
        if epbm_handled:
            continue
        goods_str = ", ".join(sorted(gdp_buildings[bname]))
        lines.append(f"# {bname} produces {goods_str} (GDP-only)")
        lines.append(f"INJECT:{bname} = {{")
        lines.append(f"\ton_built = {{")
        lines.append(f"\t\tsul_gdp_on_building_built = yes")
        lines.append(f"\t}}")
        lines.append(f"\ton_destroyed = {{")
        lines.append(f"\t\tsul_gdp_on_building_destroyed = yes")
        lines.append(f"\t}}")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def _read_inject_content(filepath, building_name):
    """
    Read the raw content of an INJECT:building_name block from a file.
    Returns the content between the braces (excluding on_built/on_destroyed
    which we manage), or None if not found.
    """
    text = filepath.read_text(encoding="utf-8-sig")
    pattern = re.compile(r'^INJECT:' + re.escape(building_name) + r'\s*=\s*\{', re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None

    brace_start = text.index('{', match.start())
    depth = 0
    i = brace_start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                block_content = text[brace_start + 1:i]
                # Strip on_built/on_destroyed blocks (we add our own)
                block_content = re.sub(
                    r'\n?\s*on_built\s*=\s*\{[^}]*\}', '', block_content
                )
                block_content = re.sub(
                    r'\n?\s*on_destroyed\s*=\s*\{[^}]*\}', '', block_content
                )
                return block_content.strip()
        i += 1
    return None


def _merge_inject_into_replace(raw_text, inject_content):
    """
    Merge rank flags (and other INJECT content) into a REPLACE block's text.
    Inserts the content before the closing brace of the building definition.
    Also replaces old rank flags (rural_settlement/town/city = yes) with new ones.
    """
    if not inject_content:
        return raw_text

    # Parse inject content for rank flag replacements
    inject_lines = inject_content.strip().split('\n')
    rank_overrides = {}
    other_lines = []
    for line in inject_lines:
        stripped = line.strip()
        if '=' in stripped:
            parts = stripped.split('=', 1)
            key = parts[0].strip()
            val = parts[1].strip()
            # Rank flags that override vanilla values
            if key in ('rural_settlement', 'town', 'city') or '_' in key:
                rank_overrides[key] = val
            else:
                other_lines.append(line)
        elif stripped:
            other_lines.append(line)

    # Apply rank overrides: replace existing flags and add new ones
    for key, val in rank_overrides.items():
        # Try to replace existing line
        old_pattern = re.compile(r'^(\s*)' + re.escape(key) + r'\s*=\s*\w+', re.MULTILINE)
        if old_pattern.search(raw_text):
            raw_text = old_pattern.sub(f'\\1{key} = {val}', raw_text)
        else:
            # Add before the closing brace
            last_brace = raw_text.rindex('}')
            raw_text = raw_text[:last_brace] + f"\t{key} = {val}\n" + raw_text[last_brace:]

    # Add any other non-rank content before closing brace
    if other_lines:
        last_brace = raw_text.rindex('}')
        extra = "\n".join(other_lines) + "\n"
        raw_text = raw_text[:last_brace] + extra + raw_text[last_brace:]

    return raw_text


def generate_replace(qualifying, buildings, gdp_buildings=None, mod_bt_dir=None,
                     existing_injects=None):
    """Generate epbm_generated_replace.txt (REPLACE blocks for buildings with existing on_built)."""
    if gdp_buildings is None:
        gdp_buildings = {}
    if existing_injects is None:
        existing_injects = {}
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# REPLACE blocks for buildings with existing on_built/on_destroyed hooks",
        "",
    ]

    # Track which buildings already got REPLACE blocks from EPBM
    replaced_buildings = set()

    for bname, is_foreign, _estate in sorted(qualifying, key=lambda x: x[0]):
        b = buildings[bname]
        if is_foreign:
            continue
        if _is_mod_file(b, mod_bt_dir):
            continue
        if not b['has_on_built'] and not b['has_on_destroyed']:
            continue

        raw = read_raw_building_text(b['file'], bname)
        if raw is None:
            lines.append(f"# WARNING: Could not extract raw text for {bname}")
            lines.append("")
            continue

        # Merge rank flags from existing INJECT blocks into the REPLACE
        if bname in existing_injects:
            inject_content = _read_inject_content(existing_injects[bname], bname)
            if inject_content:
                raw = _merge_inject_into_replace(raw, inject_content)

        is_gdp = bname in gdp_buildings
        modified = inject_on_built_hook(raw, bname, gdp_tracked=is_gdp)
        lines.append(f"# {bname} (REPLACE due to existing on_built)")
        lines.append(f"REPLACE:{modified}")
        lines.append("")
        replaced_buildings.add(bname)

    # GDP-only REPLACE blocks: buildings that produce goods and have existing
    # on_built/on_destroyed but are not EPBM-tracked
    for bname in sorted(gdp_buildings.keys()):
        if bname in replaced_buildings:
            continue
        b = buildings.get(bname)
        if b is None or b['is_foreign']:
            continue
        if _is_mod_file(b, mod_bt_dir):
            continue
        if not b['has_on_built'] and not b['has_on_destroyed']:
            continue
        epbm_handled = any(bn == bname for bn, fg, _ in qualifying if not fg)
        if epbm_handled:
            continue

        raw = read_raw_building_text(b['file'], bname)
        if raw is None:
            lines.append(f"# WARNING: Could not extract raw text for {bname}")
            lines.append("")
            continue

        goods_str = ", ".join(sorted(gdp_buildings[bname]))
        # For GDP-only REPLACE, we inject GDP hooks but not EPBM list management
        modified = _inject_gdp_only_replace(raw, bname)
        lines.append(f"# {bname} produces {goods_str} (GDP-only REPLACE)")
        lines.append(f"REPLACE:{modified}")
        lines.append("")

    return "\n".join(lines), replaced_buildings


def _inject_gdp_only_replace(raw_text, building_name):
    """
    For GDP-only REPLACE buildings: insert GDP hooks into existing on_built/on_destroyed.
    If on_built/on_destroyed don't exist, creates new blocks.
    Does NOT add EPBM list management hooks.
    """
    add_code = "\n\t\tsul_gdp_on_building_built = yes"
    remove_code = "\n\t\tsul_gdp_on_building_destroyed = yes"

    # Handle on_built
    on_built_pattern = re.compile(r'(on_built\s*=\s*\{)')
    match = on_built_pattern.search(raw_text)
    if match:
        brace_start = match.end() - 1
        depth = 0
        i = brace_start
        while i < len(raw_text):
            if raw_text[i] == '{':
                depth += 1
            elif raw_text[i] == '}':
                depth -= 1
                if depth == 0:
                    raw_text = raw_text[:i] + add_code + "\n\t" + raw_text[i:]
                    break
            i += 1
    else:
        # No on_built exists — add a new block before the building's closing brace
        last_brace = raw_text.rindex('}')
        on_built = f"\n\ton_built = {{{add_code}\n\t}}"
        raw_text = raw_text[:last_brace] + on_built + "\n" + raw_text[last_brace:]

    # Handle on_destroyed
    if 'on_destroyed' not in raw_text:
        last_brace = raw_text.rindex('}')
        on_destroyed = f"\n\ton_destroyed = {{{remove_code}\n\t}}"
        raw_text = raw_text[:last_brace] + on_destroyed + "\n" + raw_text[last_brace:]
    else:
        on_destroyed_pattern = re.compile(r'(on_destroyed\s*=\s*\{)')
        match = on_destroyed_pattern.search(raw_text)
        if match:
            brace_start = match.end() - 1
            depth = 0
            i = brace_start
            while i < len(raw_text):
                if raw_text[i] == '{':
                    depth += 1
                elif raw_text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        raw_text = raw_text[:i] + remove_code + "\n\t" + raw_text[i:]
                        break
                i += 1

    return raw_text


def generate_io_definitions(all_pm_goods):
    """Generate epbm_generated_ios.txt: hidden IOs as variable map containers."""
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# Hidden international organizations used as variable map containers.",
        f"# Each IO hosts a {_p('goods')} variable map for one PM profile.",
        "",
    ]

    for pm_name in sorted(all_pm_goods.keys()):
        io_name = f"{_p('pm')}_{pm_name}"
        lines.append(f"{io_name} = {{")
        lines.append("\tunique = yes")
        lines.append("\thas_target = no")
        lines.append("\tshow_on_diplomatic_map = no")
        lines.append("\tcreate_visible_trigger = { always = no }")
        lines.append("\tauto_disband_trigger = { always = no }")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_io_biases(all_pm_goods):
    """Generate epbm_generated_biases.txt: opinion biases for each IO (value = 0)."""
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# Opinion biases for hidden PM IOs (required by engine, value 0).",
        "",
    ]

    for pm_name in sorted(all_pm_goods.keys()):
        lines.append(f"io_opinion_{_p('pm')}_{pm_name} = {{")
        lines.append("\tvalue = 0")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_io_localization(all_pm_goods):
    """Generate epbm_ios_l_english.yml: localization entries for each IO."""
    lines = ["\ufeffl_english:"]

    for pm_name in sorted(all_pm_goods.keys()):
        io = f"{_p('pm')}_{pm_name}"
        lines.append(f' {io}: ""')
        lines.append(f' {io}_desc: ""')
        lines.append(f' diplomatic_status_{io}_name: ""')
        lines.append(f' diplomatic_status_{io}_tooltip: ""')
        lines.append(f' {io}_list_who_tt: ""')
        lines.append(f' io_opinion_{io}: ""')

    return "\n".join(lines)


def generate_init_effects(qualifying, all_pm_goods):
    """
    Generate init effects file:
    1. {prefix}_stamp_globals: creates PM IOs + stamps global production_method->IO map
    2. {prefix}_register_pm: helper to register one PM's IO (nested metascripting)
    3. {prefix}_good: helper to add one good entry to an IO during creation
    """
    pm_prefix = _p('pm')
    all_ios = _p('all_ios')
    profiles = _p('profiles')
    estate_map = _p('estate_map')
    goods = _p('goods')

    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# IO creation + global profile map (production_method -> IO scope)",
        "",
    ]

    # ── Helper: add one good entry to the IO being created ──
    lines.append(f"{_p('good')} = {{")
    lines.append(f"\tadd_to_variable_map = {{")
    lines.append(f"\t\tname = {goods}")
    lines.append(f"\t\tkey = goods:$good$")
    lines.append(f"\t\tvalue = $amount$")
    lines.append(f"\t}}")
    lines.append("}")
    lines.append("")

    # ── Helper: register one PM's IO via nested metascripting ──
    lines.append(f"{_p('register_pm')} = {{")
    lines.append(f"\tcreate_international_organization = {{")
    lines.append(f"\t\ttype = international_organization_type:{pm_prefix}_$pm$")
    lines.append(f"\t\t$goods_block$")
    lines.append(f"\t}}")
    lines.append(f"\tadd_to_global_variable_map = {{")
    lines.append(f"\t\tname = {profiles}")
    lines.append(f"\t\tkey = production_method:$pm$")
    lines.append(f"\t\tvalue = international_organization:{pm_prefix}_$pm$")
    lines.append(f"\t}}")
    lines.append(f"\tadd_to_global_variable_list = {{")
    lines.append(f"\t\tname = {all_ios}")
    lines.append(f"\t\ttarget = international_organization:{pm_prefix}_$pm$")
    lines.append(f"\t}}")
    lines.append("}")
    lines.append("")

    # ── stamp_globals: destroy stale IOs, clear globals, register all PMs ──
    lines.append("# Called once at game start: destroy stale IOs, clear globals, then")
    lines.append(f"# register one IO per maintenance PM via {_p('register_pm')}.")
    lines.append(f"{_p('stamp_globals')} = {{")
    lines.append("\t# destroy_international_organization requires country scope")
    lines.append("\trandom_country = {")
    lines.append("\t\tlimit = { is_real_country = yes }")
    lines.append("\t\tevery_in_global_list = {")
    lines.append(f"\t\t\tvariable = {all_ios}")
    lines.append("\t\t\tsave_temporary_scope_as = io_to_destroy")
    lines.append("\t\t\tprev = {")
    lines.append("\t\t\t\tdestroy_international_organization = { target = scope:io_to_destroy }")
    lines.append("\t\t\t}")
    lines.append("\t\t}")
    lines.append("\t}")
    lines.append(f"\tclear_global_variable_list = {all_ios}")
    lines.append(f"\tclear_global_variable_map = {profiles}")
    lines.append(f"\tclear_global_variable_map = {estate_map}")
    lines.append("")
    lines.append("\trandom_country = {")
    lines.append("\t\tlimit = { is_real_country = yes }")

    for pm_name in sorted(all_pm_goods.keys()):
        pm_goods = all_pm_goods[pm_name]
        lines.append(f"\t\t{_p('register_pm')} = {{")
        lines.append(f"\t\t\tpm = {pm_name}")
        lines.append(f"\t\t\tgoods_block = \"")
        for good, amount in pm_goods.items():
            lines.append(f"\t\t\t\t{_p('good')} = {{ good = {good} amount = {amount} }}")
        lines.append("\t\t\t\"")
        lines.append("\t\t}")

    lines.append("\t}")

    # Estate-assignment map: building_type → estate_type
    estate_buildings = [(b, e) for b, _, e in qualifying if e is not None]
    if estate_buildings:
        lines.append("")
        lines.append(f"\t# Estate-assigned buildings: charge full cost to the named estate")
        for bname, estate in sorted(estate_buildings):
            bt_ref = f"building_type:{bname}"
            lines.append(f"\tadd_to_global_variable_map = {{ name = {estate_map} key = {bt_ref} value = estate_type:{estate} }}")

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def strip_mode(directories):
    """
    Strip all EPBM hooks from building files in the given directories.
    Handles:
      - Buildings where EPBM added on_built/on_destroyed blocks (removes the whole block)
      - Buildings with their own on_built/on_destroyed logic alongside EPBM (removes only EPBM lines)
      - EPBM-generated INJECT/REPLACE files (deletes them entirely)
    """
    total_cleaned = 0
    total_deleted = 0

    for dir_path in directories:
        d = Path(dir_path)
        if not d.exists():
            print(f"WARNING: Directory not found: {d}")
            continue

        print(f"Stripping EPBM hooks from {d}...")

        for f in sorted(d.glob("*.txt")):
            # Generated INJECT/REPLACE files — delete entirely
            if f.name in (f"{PREFIX}_generated_inject.txt", f"{PREFIX}_generated_replace.txt"):
                f.unlink()
                total_deleted += 1
                print(f"  Deleted {f.name}")
                continue

            text = f.read_text(encoding="utf-8-sig")
            built_marker = _p('on_building_built')
            destroyed_marker = _p('on_building_destroyed')
            if built_marker not in text and destroyed_marker not in text:
                continue

            cleaned = _strip_epbm_injected_lines(text)
            if cleaned != text:
                f.write_text(cleaned, encoding="utf-8-sig")
                total_cleaned += 1
                print(f"  Cleaned {f.name}")

    if total_cleaned == 0 and total_deleted == 0:
        print("No EPBM hooks found.")
    else:
        print(f"\nDone: cleaned {total_cleaned} file(s), deleted {total_deleted} generated file(s)")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Generate EPBM building maintenance hooks for EU5 mods.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Vanilla only
  %(prog)s --vanilla /path/to/game/in_game --output /path/to/mod

  # With mod overlay (hooks written into mod files, INJECT/REPLACE for vanilla)
  %(prog)s --vanilla /path/to/game/in_game --mod /path/to/mnt/in_game --output /path/to/mod

  # Strip mode — remove all EPBM hooks from building files
  %(prog)s --strip /path/to/mod/in_game/common/building_types
  %(prog)s --strip /path/to/mod/in_game/common/building_types --strip /path/to/epbm/in_game/common/building_types

  # Custom exclusion list
  %(prog)s --vanilla ... --output ... --exclude my_exclusions.txt

  # No exclusions (track all buildings)
  %(prog)s --vanilla ... --output ... --exclude /dev/null
"""
    )
    parser.add_argument("--vanilla",
                        help="Path to vanilla game's in_game/ directory")
    parser.add_argument("--mod",
                        help="Path to source mod's in_game/ directory (optional)")
    parser.add_argument("--output",
                        help="Output directory for generated files (mod root)")
    parser.add_argument("--exclude",
                        help="Path to building exclusion list file (one name per line)")
    parser.add_argument("--prefix", default="epbm",
                        help="Prefix for all generated names (default: epbm). "
                             "Affects IO names, effect names, variable names, and filenames.")
    parser.add_argument("--strip", action="append", metavar="DIR",
                        help="Remove all hooks with the current --prefix from building files "
                             "in DIR. Can be specified multiple times. Standalone — ignores "
                             "other flags except --prefix.")

    args = parser.parse_args()

    # Set global prefix
    global PREFIX
    PREFIX = args.prefix

    # ── Strip mode: standalone, doesn't need vanilla/output ──
    if args.strip:
        return strip_mode(args.strip)

    # ── Generate modes need --vanilla and --output ──
    if not args.vanilla:
        parser.error("--vanilla is required (unless using --strip)")
    if not args.output:
        parser.error("--output is required (unless using --strip)")

    vanilla_dir = Path(args.vanilla)
    mod_dir = Path(args.mod) if args.mod else None
    output_dir = Path(args.output)

    if not vanilla_dir.exists():
        print(f"ERROR: Vanilla directory not found: {vanilla_dir}")
        return 1
    if mod_dir and not mod_dir.exists():
        print(f"ERROR: Mod directory not found: {mod_dir}")
        return 1

    # Load exclusions
    exclusions = load_exclusions(args.exclude)
    if exclusions:
        print(f"Loaded {len(exclusions)} building exclusion(s)")

    # Parse production methods
    print("Parsing production methods...")
    pms = parse_production_methods(vanilla_dir, mod_dir)
    print(f"  Found {len(pms)} production methods")
    qualifying_pms = {k: v for k, v in pms.items()
                      if not v['no_upkeep'] and not v['has_output'] and v['goods']}
    print(f"  Qualifying PMs (has goods, no no_upkeep, no output): {len(qualifying_pms)}")

    # Strip previously-merged hooks before parsing so the parser sees clean state
    if mod_dir:
        mod_bt_dir = mod_dir / "common" / "building_types"
        strip_hooks_from_inject_files(mod_bt_dir)

    # Parse building types
    print("\nParsing building types...")
    buildings = parse_all_buildings(vanilla_dir, mod_dir)
    print(f"  Found {len(buildings)} buildings")

    # Classify EPBM
    print("\nClassifying qualifying buildings (EPBM)...")
    qualifying, all_pm_goods = classify(buildings, pms, exclusions)
    print(f"  Qualifying buildings: {len(qualifying)}")
    print(f"  Unique PM goods profiles: {len(all_pm_goods)}")

    # Classify GDP (all buildings with output goods, no exclusions)
    print("\nClassifying GDP-tracked buildings...")
    gdp_buildings, all_output_goods = classify_gdp(buildings, pms)
    print(f"  GDP-tracked buildings: {len(gdp_buildings)}")
    print(f"  Unique output goods: {len(all_output_goods)} ({', '.join(all_output_goods)})")

    non_foreign = [q for q in qualifying if not q[1]]
    foreign_count = sum(1 for q in qualifying if q[1])
    estate_count = sum(1 for q in qualifying if q[2] is not None)

    # Output directories
    out_effects = output_dir / "in_game" / "common" / "scripted_effects"
    out_ios = output_dir / "in_game" / "common" / "international_organizations"
    out_biases = output_dir / "in_game" / "common" / "biases"
    out_loc = output_dir / "main_menu" / "localization" / "english"

    # Generate building hooks (mod-defined buildings filtered out by mod_bt_dir)
    mod_bt_dir = (mod_dir / "common" / "building_types") if mod_dir else None
    out_buildings = output_dir / "in_game" / "common" / "building_types"
    out_buildings.mkdir(parents=True, exist_ok=True)

    # Merge hooks into existing INJECT blocks from other mod files
    print(f"\nMerging hooks into existing INJECT blocks...")
    existing_injects = scan_existing_injects(mod_bt_dir)
    already_merged = merge_hooks_into_existing_injects(
        existing_injects, qualifying, buildings, gdp_buildings, mod_bt_dir
    )
    if already_merged:
        print(f"  Merged {len(already_merged)} building(s) into existing INJECT blocks")
    else:
        print(f"  No existing INJECT blocks to merge into")

    print(f"\nGenerating INJECT/REPLACE files...")
    inject_code = generate_inject(qualifying, buildings, gdp_buildings=gdp_buildings,
                                  mod_bt_dir=mod_bt_dir, already_merged=already_merged)
    out_path = out_buildings / f"{PREFIX}_generated_inject.txt"
    out_path.write_text(inject_code, encoding="utf-8-sig")
    print(f"  Wrote {out_path.relative_to(output_dir)}")

    replace_code, replaced_buildings = generate_replace(
        qualifying, buildings, gdp_buildings=gdp_buildings,
        mod_bt_dir=mod_bt_dir, existing_injects=existing_injects)
    out_path = out_buildings / f"{PREFIX}_generated_replace.txt"
    out_path.write_text(replace_code, encoding="utf-8-sig")
    print(f"  Wrote {out_path.relative_to(output_dir)}")

    # Remove INJECT blocks for buildings we REPLACE'd (their flags are now in the REPLACE)
    conflicting_replaces = replaced_buildings & set(existing_injects.keys())
    if conflicting_replaces:
        _remove_injects_for_replaced(existing_injects, conflicting_replaces)
        print(f"  Removed {len(conflicting_replaces)} INJECT block(s) absorbed into REPLACE")

    # Also remove INJECT blocks that conflict with REPLACE blocks in other mod files
    # (e.g., rank flag INJECTs for buildings that have hand-written REPLACE elsewhere)
    other_replaces = scan_existing_replaces(mod_bt_dir)
    stale_injects = set(existing_injects.keys()) & other_replaces
    if stale_injects:
        _remove_injects_for_replaced(existing_injects, stale_injects)
        print(f"  Removed {len(stale_injects)} stale INJECT block(s) conflicting with REPLACE in other files")

    # Generate shared files (both modes)

    out_ios.mkdir(parents=True, exist_ok=True)
    io_defs = generate_io_definitions(all_pm_goods)
    out_path = out_ios / f"{PREFIX}_generated_ios.txt"
    out_path.write_text(io_defs, encoding="utf-8-sig")
    print(f"  Wrote {out_path.relative_to(output_dir)}")

    out_effects.mkdir(parents=True, exist_ok=True)
    init_effects = generate_init_effects(qualifying, all_pm_goods)
    out_path = out_effects / f"{PREFIX}_generated_init_effects.txt"
    out_path.write_text(init_effects, encoding="utf-8-sig")
    print(f"  Wrote {out_path.relative_to(output_dir)}")

    out_biases.mkdir(parents=True, exist_ok=True)
    biases = generate_io_biases(all_pm_goods)
    out_path = out_biases / f"{PREFIX}_generated_biases.txt"
    out_path.write_text(biases, encoding="utf-8-sig")
    print(f"  Wrote {out_path.relative_to(output_dir)}")

    out_loc.mkdir(parents=True, exist_ok=True)
    loc = generate_io_localization(all_pm_goods)
    out_path = out_loc / f"{PREFIX}_ios_l_english.yml"
    out_path.write_text(loc, encoding="utf-8")
    print(f"  Wrote {out_path.relative_to(output_dir)}")

    # Generate GDP effects
    if all_output_goods:
        print(f"\nGenerating GDP effects ({len(all_output_goods)} output goods)...")
        gdp_code = generate_gdp_effects(gdp_buildings, all_output_goods, buildings)
        out_path = out_effects / "sul_gdp_generated_effects.txt"
        out_path.write_text(gdp_code, encoding="utf-8-sig")
        print(f"  Wrote {out_path.relative_to(output_dir)}")

    # Format all generated and modified files
    print(f"\nFormatting files...")
    format_targets = []
    if mod_bt_dir:
        for f in sorted(mod_bt_dir.iterdir()):
            if f.name.endswith(".txt"):
                format_targets.append(f)
    format_targets.append(out_effects / f"{PREFIX}_generated_init_effects.txt")
    format_targets.append(out_effects / "sul_gdp_generated_effects.txt")
    _format_files(format_targets)

    # Ensure all output mtimes are newer than inputs (for stale detection)
    import time
    time.sleep(0.1)
    for f in out_buildings.glob(f"{PREFIX}_generated_*.txt"):
        f.touch()
    for d in (out_effects, out_ios, out_biases, out_loc):
        if d.exists():
            for f in d.iterdir():
                if PREFIX in f.name:
                    f.touch()

    # Summary
    print("\n=== Summary ===")
    print(f"Total qualifying buildings: {len(qualifying)}")
    print(f"  Location-tracked buildings: {len(non_foreign)}")
    print(f"  Foreign buildings (no list): {foreign_count}")
    print(f"  Estate-assigned buildings: {estate_count}")
    print(f"Unique PM goods profiles: {len(all_pm_goods)}")
    if exclusions:
        print(f"Excluded buildings: {len(exclusions)}")

    all_goods = set()
    for goods in all_pm_goods.values():
        all_goods.update(goods.keys())
    print(f"Distinct maintenance goods: {len(all_goods)} ({', '.join(sorted(all_goods))})")

    gdp_only_count = sum(1 for b in gdp_buildings if b not in {q[0] for q in qualifying})
    print(f"GDP-tracked buildings: {len(gdp_buildings)} ({gdp_only_count} GDP-only)")
    print(f"Unique output goods: {len(all_output_goods)} ({', '.join(all_output_goods)})")

    print("\n=== PM Goods Profiles ===")
    for pm_name in sorted(all_pm_goods.keys()):
        goods = all_pm_goods[pm_name]
        goods_str = ", ".join(f"{g}={a}" for g, a in goods.items())
        print(f"  {pm_name}: [{goods_str}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
