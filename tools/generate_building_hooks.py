#!/usr/bin/env python3
"""
Generate Paradox script files for EPBM (Estates Pay Building Maintenance).

Mod-agnostic generator: parses vanilla building_types and production_methods,
optionally overlays a mod's building_types (handling file replacement, INJECT:,
and REPLACE: directives), then produces the generated script files.

Two modes:
  Default mode:  Generates INJECT/REPLACE files to --output directory.
  In-place mode: Writes hooks directly into --mod building files (requires --mod).
                 Idempotent: strips existing EPBM hooks before re-injecting.

Output files (written to --output directory):
  Default mode only:
    in_game/common/building_types/epbm_generated_inject.txt
    in_game/common/building_types/epbm_generated_replace.txt
  Both modes:
    in_game/common/scripted_effects/epbm_generated_init_effects.txt
    in_game/common/international_organizations/epbm_generated_ios.txt
    in_game/common/biases/epbm_generated_biases.txt
    main_menu/localization/english/epbm_ios_l_english.yml

Usage:
  # Default: generate INJECT/REPLACE files
  python generate_building_hooks.py --vanilla /path/to/game/in_game --output /path/to/mod

  # In-place: write hooks directly into mod's building files
  python generate_building_hooks.py --vanilla /path/to/game/in_game --mod /path/to/mod/in_game --output /path/to/output --in-place

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
    if isinstance(upm, dict):
        for pm_name, pm_block in upm.items():
            if isinstance(pm_block, dict):
                goods = OrderedDict()
                for k, v in pm_block.items():
                    if k not in PM_META_KEYS and isinstance(v, str):
                        try:
                            goods[k] = float(v)
                        except ValueError:
                            pass
                b['unique_pms'][pm_name] = {
                    'goods': goods,
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
                    for gk, gv in pm_block.items():
                        if gk not in PM_META_KEYS and isinstance(gv, str):
                            try:
                                goods[gk] = float(gv)
                            except ValueError:
                                pass
                    building['unique_pms'][pm_name] = {
                        'goods': goods,
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
      qualifying: list of (building_name, pm_name, pm_source, is_foreign, estate) tuples
                  where estate is None (split by estate power) or an estate key string
      all_pm_goods: dict pm_name -> OrderedDict(good->amount)
    """
    qualifying = []
    all_pm_goods = OrderedDict()
    excluded_count = 0

    for bname, b in buildings.items():
        if bname in exclusions:
            excluded_count += 1
            continue

        best_pm = None

        # Check external PMs
        for pm_name in b['possible_pms']:
            if pm_name not in pms:
                continue
            pm = pms[pm_name]
            if pm['no_upkeep'] or pm['has_output']:
                continue
            if not pm['goods']:
                continue
            if best_pm is None:
                best_pm = (pm_name, 'external')
                all_pm_goods[pm_name] = pm['goods']

        # Check inline PMs
        for pm_name, pm_data in b['unique_pms'].items():
            if not pm_data.get('is_maintenance', False):
                continue
            if pm_data.get('no_upkeep', False) or pm_data.get('has_output', False):
                continue
            if not pm_data['goods']:
                continue
            if best_pm is None:
                best_pm = (pm_name, 'inline')
                all_pm_goods[pm_name] = pm_data['goods']

        if best_pm:
            estate = b['estate']  # None for unassigned, or estate key string
            qualifying.append((bname, best_pm[0], best_pm[1], b['is_foreign'], estate))

    if excluded_count > 0:
        print(f"  Excluded {excluded_count} building(s) from tracking")

    return qualifying, all_pm_goods


# ─────────────────────────────────────────────
# Read raw building text for REPLACE blocks
# ─────────────────────────────────────────────

def read_raw_building_text(filepath, building_name):
    """
    Extract the raw text of a building definition from a file.
    Returns the text between building_name = { ... } including braces.
    """
    text = filepath.read_text(encoding="utf-8-sig")
    text = strip_bom(text)

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
                return text[start:i+1]
        i += 1
    return None


def inject_on_built_hook(raw_text, building_name):
    """
    For REPLACE buildings: insert our list-management hook into existing on_built,
    and add on_destroyed if it doesn't exist.
    Also renames inline unique_production_methods PM names to avoid duplicates.
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
            return f"{m.group(1)}{_p(name)}{m.group(3)}"
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
    Remove all PREFIX-injected hook code from file text. Idempotent.
    Handles both inline injections (inside existing on_built/on_destroyed)
    and whole-block injections (on_built/on_destroyed added by the generator).
    Uses the current PREFIX to identify injected lines.
    """
    built_marker = _p('on_building_built')
    destroyed_marker = _p('on_building_destroyed')
    list_name = _p('buildings')

    if built_marker not in text and destroyed_marker not in text:
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

        # Skip standalone marker lines
        if stripped == f'{built_marker} = yes' or stripped == f'{destroyed_marker} = yes':
            i += 1
            continue

        result.append(line)
        i += 1

    text = '\n'.join(result)
    text = _remove_empty_hook_blocks(text)

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


def _inject_hook_into_building_text(building_text, has_on_built, has_on_destroyed):
    """
    Inject EPBM hooks into a single building's text.
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


def apply_in_place(qualifying, buildings, mod_dir):
    """
    In-place mode: modify mod building files directly.
    For each qualifying non-foreign building whose source file is in the mod
    directory, inject EPBM hooks. Buildings from vanilla-only files are skipped
    (they go into INJECT/REPLACE output instead).
    Returns (modified_file_count, vanilla_only_buildings) where vanilla_only_buildings
    is a list of (bname, pm_name, pm_source, is_foreign, estate) for buildings not in mod files.
    """
    mod_bt_dir = mod_dir / "common" / "building_types"

    # Group qualifying buildings by source file, separating mod vs vanilla
    mod_buildings_by_file = {}
    vanilla_only = []

    for bname, pm_name, pm_source, is_foreign, estate in qualifying:
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
            vanilla_only.append((bname, pm_name, pm_source, is_foreign, estate))

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

            modified = _inject_hook_into_building_text(building_text, has_on_built, has_on_destroyed)
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

def generate_inject(qualifying, buildings):
    """Generate epbm_generated_inject.txt (INJECT blocks for buildings without on_built)."""
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# INJECT blocks: manage location tracking list on build/destroy",
        "",
    ]

    for bname, pm_name, _, is_foreign, _estate in sorted(qualifying, key=lambda x: x[0]):
        b = buildings[bname]
        if is_foreign:
            continue
        if b['has_on_built'] or b['has_on_destroyed']:
            continue

        list_name = _p('buildings')
        lines.append(f"# {bname} uses {pm_name}")
        lines.append(f"INJECT:{bname} = {{")
        lines.append(f"\ton_built = {{")
        lines.append(f"\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = prev }} }}")
        lines.append(f"\t\t{_p('on_building_built')} = yes")
        lines.append(f"\t}}")
        lines.append(f"\ton_destroyed = {{")
        lines.append(f"\t\tlocation = {{ remove_list_variable = {{ name = {list_name} target = prev }} }}")
        lines.append(f"\t\t{_p('on_building_destroyed')} = yes")
        lines.append(f"\t}}")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_replace(qualifying, buildings):
    """Generate epbm_generated_replace.txt (REPLACE blocks for buildings with existing on_built)."""
    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# REPLACE blocks for buildings with existing on_built/on_destroyed hooks",
        "",
    ]

    for bname, pm_name, _, is_foreign, _estate in sorted(qualifying, key=lambda x: x[0]):
        b = buildings[bname]
        if is_foreign:
            continue
        if not b['has_on_built'] and not b['has_on_destroyed']:
            continue

        raw = read_raw_building_text(b['file'], bname)
        if raw is None:
            lines.append(f"# WARNING: Could not extract raw text for {bname}")
            lines.append("")
            continue

        modified = inject_on_built_hook(raw, bname)
        lines.append(f"# {bname} uses {pm_name} (REPLACE due to existing on_built)")
        lines.append(f"REPLACE:{modified}")
        lines.append("")

    return "\n".join(lines)


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
    1. {prefix}_stamp_globals: creates PM IOs + stamps global building_type->IO map
    2. {prefix}_init_building: dispatch that adds building to list (game start)
    """
    pm_prefix = _p('pm')
    list_name = _p('buildings')
    all_ios = _p('all_ios')
    profiles = _p('profiles')
    estate_map = _p('estate_map')
    goods = _p('goods')
    bldg = _p('bldg')

    lines = [
        "# Auto-generated by tools/generate_building_hooks.py",
        "# IO creation + global profile lookup + init dispatch",
        "",
    ]

    # ── Part 1: Create IOs and stamp global profile map ──
    lines.append("# Create PM international organizations and populate their goods maps,")
    lines.append(f"# then stamp global map {profiles} (building_type -> IO scope).")
    lines.append("# Called once at game start.")
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
    lines.append("\t# Create all PM IOs and populate goods maps inside creation scope")
    lines.append("\trandom_country = {")
    lines.append("\t\tlimit = { is_real_country = yes }")

    for pm_name in sorted(all_pm_goods.keys()):
        pm_goods = all_pm_goods[pm_name]
        io_type = f"international_organization_type:{pm_prefix}_{pm_name}"
        goods_str = ", ".join(f"{g} {a}" for g, a in pm_goods.items())
        lines.append(f"\t\t# PM: {pm_name} ({goods_str})")
        lines.append(f"\t\tcreate_international_organization = {{")
        lines.append(f"\t\t\ttype = {io_type}")
        for good, amount in pm_goods.items():
            lines.append(f"\t\t\tadd_to_variable_map = {{ name = {goods} key = goods:{good} value = {amount} }}")
        lines.append("\t\t}")

    lines.append("\t}")
    lines.append("")
    lines.append("\t# Global map: building_type -> IO scope")

    for bname, pm_name, _, is_foreign, estate in sorted(qualifying, key=lambda x: x[0]):
        bt_ref = f"building_type:{bname}"
        io_ref = f"international_organization:{pm_prefix}_{pm_name}"
        tags = []
        if is_foreign:
            tags.append('foreign')
        if estate:
            tags.append(f'estate:{estate}')
        tag = f'  # ({", ".join(tags)})' if tags else ''
        lines.append(f"\tadd_to_global_variable_map = {{ name = {profiles} key = {bt_ref} value = {io_ref} }}{tag}")

    # Estate map: building_type -> estate_type (only for estate-assigned buildings)
    estate_buildings = [(b, e) for b, _, _, _, e in qualifying if e is not None]
    if estate_buildings:
        lines.append("")
        lines.append(f"\t# Estate map: building_type -> estate_type (charged entirely to assigned estate)")
        lines.append(f"\tclear_global_variable_map = {estate_map}")
        for bname, estate in sorted(estate_buildings):
            bt_ref = f"building_type:{bname}"
            lines.append(f"\tadd_to_global_variable_map = {{ name = {estate_map} key = {bt_ref} value = estate_type:{estate} }}")

    lines.append("")
    lines.append("\t# Global list of all PM IOs (for monthly cache clearing)")
    for pm_name in sorted(all_pm_goods.keys()):
        io_ref = f"international_organization:{pm_prefix}_{pm_name}"
        lines.append(f"\tadd_to_global_variable_list = {{ name = {all_ios} target = {io_ref} }}")

    lines.append("}")
    lines.append("")

    # ── Part 2: Init dispatch for pre-existing buildings ──
    lines.append(f"# Init dispatch: add building instance to {list_name} list for pre-existing buildings")
    lines.append("# Scope: building (called via every_buildings_in_location)")
    lines.append(f"# All non-foreign buildings go to {list_name}. Foreign buildings are skipped.")
    lines.append(f"{_p('init_building')} = {{")
    lines.append(f"\tsave_temporary_scope_as = {bldg}")

    first = True
    for bname, pm_name, _, is_foreign, _estate in sorted(qualifying, key=lambda x: x[0]):
        if is_foreign:
            continue
        keyword = "if" if first else "else_if"
        first = False
        bt_ref = f"building_type:{bname}"
        lines.append(f"\t{keyword} = {{")
        lines.append(f"\t\tlimit = {{ building_type = {bt_ref} }}")
        lines.append(f"\t\tlocation = {{ add_to_variable_list = {{ name = {list_name} target = scope:{bldg} }} }}")
        lines.append("\t}")

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
  # Vanilla only (default mode — generates INJECT/REPLACE files)
  %(prog)s --vanilla /path/to/game/in_game --output /path/to/mod

  # With mod overlay
  %(prog)s --vanilla /path/to/game/in_game --mod /path/to/mnt/in_game --output /path/to/mod

  # In-place mode — writes hooks directly into mod building files
  %(prog)s --vanilla /path/to/game/in_game --mod /path/to/mnt/in_game --output /path/to/output --in-place

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
    parser.add_argument("--in-place", action="store_true", dest="in_place",
                        help="Write hooks directly into --mod building files instead of "
                             "generating INJECT/REPLACE output (requires --mod)")
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
    in_place = args.in_place

    if not vanilla_dir.exists():
        print(f"ERROR: Vanilla directory not found: {vanilla_dir}")
        return 1
    if mod_dir and not mod_dir.exists():
        print(f"ERROR: Mod directory not found: {mod_dir}")
        return 1
    if in_place and not mod_dir:
        print("ERROR: --in-place requires --mod")
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

    # Parse building types
    print("\nParsing building types...")
    buildings = parse_all_buildings(vanilla_dir, mod_dir)
    print(f"  Found {len(buildings)} buildings")

    # Classify
    print("\nClassifying qualifying buildings...")
    qualifying, all_pm_goods = classify(buildings, pms, exclusions)
    print(f"  Qualifying buildings: {len(qualifying)}")
    print(f"  Unique PM goods profiles: {len(all_pm_goods)}")

    pm_to_buildings = {}
    for bname, pm_name, _, _, _ in qualifying:
        pm_to_buildings.setdefault(pm_name, []).append(bname)

    non_foreign = [q for q in qualifying if not q[3]]
    foreign_count = sum(1 for q in qualifying if q[3])
    estate_count = sum(1 for q in qualifying if q[4] is not None)
    inject_count = sum(1 for b, _, _, _, _ in non_foreign
                       if not buildings[b]['has_on_built'] and not buildings[b]['has_on_destroyed'])
    replace_count = sum(1 for b, _, _, _, _ in non_foreign
                        if buildings[b]['has_on_built'] or buildings[b]['has_on_destroyed'])
    print(f"  INJECT buildings: {inject_count}")
    print(f"  REPLACE buildings: {replace_count}")
    print(f"  Foreign buildings: {foreign_count}")

    if replace_count > 0:
        replace_buildings = [b for b, _, _, fg, _ in qualifying
                            if not fg and (buildings[b]['has_on_built'] or buildings[b]['has_on_destroyed'])]
        print(f"  REPLACE candidates: {', '.join(replace_buildings)}")

    # Output directories
    out_effects = output_dir / "in_game" / "common" / "scripted_effects"
    out_ios = output_dir / "in_game" / "common" / "international_organizations"
    out_biases = output_dir / "in_game" / "common" / "biases"
    out_loc = output_dir / "main_menu" / "localization" / "english"

    # Generate building hooks
    if in_place:
        print(f"\nIn-place mode: modifying mod building files...")
        modified, vanilla_only = apply_in_place(qualifying, buildings, mod_dir)
        print(f"  Modified {modified} file(s)")

        # Generate INJECT/REPLACE for buildings from vanilla-only files
        if vanilla_only:
            out_buildings = output_dir / "in_game" / "common" / "building_types"
            out_buildings.mkdir(parents=True, exist_ok=True)

            print(f"\nGenerating INJECT/REPLACE for {len(vanilla_only)} vanilla-only building(s)...")
            inject_code = generate_inject(vanilla_only, buildings)
            out_path = out_buildings / f"{PREFIX}_generated_inject.txt"
            out_path.write_text(inject_code, encoding="utf-8-sig")
            print(f"  Wrote {out_path.relative_to(output_dir)}")

            replace_code = generate_replace(vanilla_only, buildings)
            out_path = out_buildings / f"{PREFIX}_generated_replace.txt"
            out_path.write_text(replace_code, encoding="utf-8-sig")
            print(f"  Wrote {out_path.relative_to(output_dir)}")
    else:
        out_buildings = output_dir / "in_game" / "common" / "building_types"
        print(f"\nGenerating INJECT/REPLACE files to {output_dir}...")

        out_buildings.mkdir(parents=True, exist_ok=True)
        inject_code = generate_inject(qualifying, buildings)
        out_path = out_buildings / f"{PREFIX}_generated_inject.txt"
        out_path.write_text(inject_code, encoding="utf-8-sig")
        print(f"  Wrote {out_path.relative_to(output_dir)}")

        replace_code = generate_replace(qualifying, buildings)
        out_path = out_buildings / f"{PREFIX}_generated_replace.txt"
        out_path.write_text(replace_code, encoding="utf-8-sig")
        print(f"  Wrote {out_path.relative_to(output_dir)}")

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

    # Summary
    print("\n=== Summary ===")
    print(f"Mode: {'in-place' if in_place else 'default (INJECT/REPLACE)'}")
    print(f"Total qualifying buildings: {len(qualifying)}")
    print(f"  Location-tracked buildings: {len(non_foreign)}")
    print(f"  Foreign buildings (no list): {foreign_count}")
    print(f"  Estate-assigned buildings: {estate_count}")
    print(f"Unique PM goods profiles: {len(all_pm_goods)}")
    if not in_place:
        print(f"INJECT blocks: {inject_count}")
        print(f"REPLACE blocks: {replace_count}")
    if exclusions:
        print(f"Excluded buildings: {len(exclusions)}")

    all_goods = set()
    for goods in all_pm_goods.values():
        all_goods.update(goods.keys())
    print(f"Distinct maintenance goods: {len(all_goods)} ({', '.join(sorted(all_goods))})")

    print("\n=== PM to Buildings Mapping ===")
    for pm_name in sorted(all_pm_goods.keys()):
        blist = pm_to_buildings.get(pm_name, [])
        goods = all_pm_goods[pm_name]
        goods_str = ", ".join(f"{g}={a}" for g, a in goods.items())
        print(f"  {pm_name} ({len(blist)} buildings): [{goods_str}]")
        for b in sorted(blist):
            src = "inline" if any(bn == b and s == 'inline' for bn, _, s, _, _ in qualifying) else "external"
            tag = " (foreign)" if buildings[b]['is_foreign'] else ""
            print(f"    - {b} ({src}){tag}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
