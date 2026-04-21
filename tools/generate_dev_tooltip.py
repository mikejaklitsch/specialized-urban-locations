#!/usr/bin/env python3
"""
Generate development tradeoff tooltip GUI, script values, and loc keys
from the base_values and development static modifier definitions.

Reads the modifier values from sul_vanilla_economy_injects.txt and
modifier type definitions from vanilla, then generates:
  1. Script values for current-development display
  2. GUI tooltip rows with correct icons, names, formatting, and colors
  3. Side tooltip content (extraction at 0, production at 100)

Usage: python tools/generate_dev_tooltip.py
"""

import os
import re
import sys

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MOD_ROOT = os.path.dirname(SCRIPT_DIR)
VANILLA_ROOT = "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game"
VANILLA_MODIFIER_DEFS = os.path.join(VANILLA_ROOT, "main_menu", "common", "modifier_type_definitions")
STATIC_MOD_FILE = os.path.join(MOD_ROOT, "main_menu", "common", "static_modifiers", "sul_vanilla_economy_injects.txt")
SCRIPT_VALUES_FILE = os.path.join(MOD_ROOT, "in_game", "common", "script_values", "sul_dev_tooltip_values.txt")

# Icon mappings: modifier name -> icon texture path
ICON_MAP = {
    'local_population_growth': 'gfx/interface/icons/location_icons/new/population_growth.dds',
    'local_disease_resistance': 'gfx/interface/icons/modifier_types/local_disease_resistance.dds',
    'local_migration_attraction': 'gfx/interface/icons/modifier_types/migration_attraction.dds',
    'local_pop_promotion_speed_modifier': 'gfx/interface/icons/location_icons/promotion.dds',
    'local_pop_demotion_speed_modifier': 'gfx/interface/icons/location_icons/promotion.dds',
    'local_pop_assimilation_speed_modifier': 'gfx/interface/icons/modifier_types/global_pop_assimilation_speed.dds',
    'local_pop_conversion_speed_modifier': 'gfx/interface/icons/location_icons/monthly_conversion.dds',
    'local_institution_growth_modifier': 'gfx/interface/icons/modifier_types/study_institutions.dds',
    'local_monthly_literacy': 'gfx/interface/icons/location_icons/literacy.dds',
    'local_construction_speed': 'gfx/interface/icons/modifier_types/free_building_levels.dds',
    'local_peasant_enfranchisment': 'gfx/interface/icons/modifier_types/_default.dds',
    'local_unrest': 'gfx/interface/icons/resources/war_exhaustion.dds',
}

# Goods -> positive icon
GOODS_POSITIVE_ICONS = {
    'wheat': 'wheat_positive', 'rice': 'rice_positive', 'millet': 'millet_positive',
    'maize': 'maize_positive', 'livestock': 'livestock_positive', 'fish': 'fish_positive',
    'iron': 'iron_positive', 'copper': 'copper_positive', 'lumber': 'lumber_positive',
    'wild_game': 'wild_game_positive',
    'cloth': 'cloth_positive', 'fine_cloth': 'fine_cloth_positive',
    'tools': 'tools_positive', 'steel': 'steel_positive',
    'glass': 'glass_positive', 'paper': 'paper_positive',
}


def get_icon(modifier_name):
    """Get the icon path for a modifier."""
    if modifier_name in ICON_MAP:
        return ICON_MAP[modifier_name]
    # Try goods positive icon
    m = re.match(r'local_(\w+)_output_modifier', modifier_name)
    if m:
        good = m.group(1)
        if good in GOODS_POSITIVE_ICONS:
            return f'gfx/interface/icons/modifier_types/{GOODS_POSITIVE_ICONS[good]}.dds'
    return 'gfx/interface/icons/modifier_types/_default.dds'


def parse_modifier_types():
    """Parse vanilla modifier type definitions for percent/color info."""
    defs = {}
    for fn in os.listdir(VANILLA_MODIFIER_DEFS):
        if not fn.endswith('.txt'):
            continue
        with open(os.path.join(VANILLA_MODIFIER_DEFS, fn)) as f:
            content = f.read()
        for m in re.finditer(r'(\w+)\s*=\s*\{([^}]*)\}', content):
            name = m.group(1)
            body = m.group(2)
            info = {'percent': False, 'color': 'good'}
            if 'percent=yes' in body:
                info['percent'] = True
            if 'already_percent=yes' in body:
                info['percent'] = True
                info['already_percent'] = True
            if 'color=bad' in body:
                info['color'] = 'bad'
            defs[name] = info
    return defs


def parse_static_modifiers():
    """Parse our static modifier file for base_values and development tradeoff modifiers."""
    with open(STATIC_MOD_FILE) as f:
        content = f.read()

    base_values = {}
    dev_values = {}

    def parse_block(content, block_name):
        """Parse a modifier block, handling nested game_data blocks."""
        values = {}
        pattern = rf'(?:REPLACE|TRY_INJECT):{block_name}\s*=\s*\{{'
        m = re.search(pattern, content)
        if not m:
            return values
        # Find matching closing brace
        start = m.end()
        depth = 1
        pos = start
        while pos < len(content) and depth > 0:
            if content[pos] == '{':
                depth += 1
            elif content[pos] == '}':
                depth -= 1
            pos += 1
        block_text = content[start:pos-1]
        # Remove nested blocks (game_data = { ... })
        block_text = re.sub(r'\w+\s*=\s*\{[^}]*\}', '', block_text)
        for line in block_text.split('\n'):
            line = line.split('#')[0].strip()
            parts = line.split('=')
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip()
                try:
                    values[key] = float(val)
                except ValueError:
                    pass
        return values

    base_values = parse_block(content, 'location_base_values')
    dev_values = parse_block(content, 'development')

    return base_values, dev_values


def classify_modifiers(base_values, dev_values):
    """Classify modifiers into extraction (in base, offset in dev) and production (only in dev)."""
    # Non-tradeoff modifiers (vanilla preserved values, equilibrium spring, RGO nulls)
    skip = {
        'local_food_capacity', 'local_max_rgo_size', 'local_monthly_development',
        'local_monthly_food_modifier',
        # Vanilla base_values preserved
        'local_devastation_recovery', 'local_monthly_control',
        'max_regiments_trained_at_same_time', 'max_constructions_at_same_time',
        'local_pop_promotion_speed', 'local_pop_demotion_speed',
        'local_frontage_allowed', 'local_garrison_growth',
        'max_attrition', 'supply_limit', 'hostile_disembark_time_modifier',
        'local_monthly_prosperity', 'local_trade_embark_disembark_cost_modifier',
        'local_clergy_desired_pop_scaled', 'local_nobles_desired_pop_scaled',
        # local_migration_attraction: vanilla base has 0.1, our dev adds 0.001/pt (production bonus)
        # Vanilla development preserved
        'local_population_capacity_modifier', 'local_distance_from_capital_speed_propagation',
        'local_supply_limit_modifier', 'blockade_force_required',
        'local_trade_center_power', 'free_building_levels',
        'local_life_expectancy', 'occupation_time',
        'local_build_buildings_cost', 'maximum_stockpile_capacity',
    }

    extraction = []  # In base_values WITH negative offset in dev (tradeoff pair)
    production = []  # Only in dev with positive values (production bonuses + costs)

    # Extraction: modifiers present in BOTH base_values and dev with opposite signs
    for mod, base_val in base_values.items():
        if mod in skip:
            continue
        if mod in dev_values and dev_values[mod] < 0 and base_val > 0:
            extraction.append((mod, base_val, dev_values[mod]))

    # Production: modifiers in dev with positive values that aren't extraction offsets
    for mod, dev_val in dev_values.items():
        if mod in skip:
            continue
        if dev_val > 0 and mod not in [e[0] for e in extraction]:
            production.append((mod, dev_val))
        elif dev_val != 0 and mod not in base_values and mod not in [e[0] for e in extraction]:
            production.append((mod, dev_val))

    return extraction, production


def format_value(value, mod_info):
    """Format a static value for display in side tooltips."""
    is_pct = mod_info.get('percent', False)
    is_bad = mod_info.get('color') == 'bad'
    color = '#color_red' if is_bad else '#color_green'

    if is_pct:
        display = value * 100
        if abs(display - round(display)) < 0.001:
            return f'{color} +{int(round(display))}%#!'
        else:
            return f'{color} +{display:.1f}%#!'
    else:
        if abs(value) < 0.01:
            return f'{color} +{value:.4f}#!'
        elif abs(value) < 0.1:
            return f'{color} +{value:.2f}#!'
        else:
            return f'{color} +{value:.1f}#!'


def script_value_format(mod_info):
    """Return the GUI format code for a script value display."""
    is_pct = mod_info.get('percent', False)
    if is_pct:
        return '|+0%'
    else:
        return '|+2'


def gui_color(mod_info):
    """Return the default_format color for a modifier."""
    is_bad = mod_info.get('color') == 'bad'
    return '#color_red' if is_bad else '#color_green'


def generate_script_values(extraction, production, mod_types):
    """Generate script values file for current-development display."""
    lines = ['# AUTO-GENERATED by tools/generate_dev_tooltip.py — do not hand-edit', '']

    # Extraction: base - dev * |offset|
    for mod, base_val, dev_offset in extraction:
        sv_name = f'sul_dev_tt_{mod.replace("local_", "")}'
        lines.append(f'{sv_name} = {{')
        lines.append(f'\tvalue = {base_val}')
        if dev_offset != 0:
            lines.append(f'\tsubtract = {{')
            lines.append(f'\t\tvalue = development')
            lines.append(f'\t\tmultiply = {abs(dev_offset)}')
            lines.append(f'\t}}')
        lines.append('}')
        lines.append('')

    # Production: dev * val
    for mod, dev_val in production:
        sv_name = f'sul_dev_tt_{mod.replace("local_", "")}'
        lines.append(f'{sv_name} = {{')
        lines.append(f'\tvalue = development')
        lines.append(f'\tmultiply = {dev_val}')
        lines.append('}')
        lines.append('')

    return '\n'.join(lines)


def generate_tooltip_row(mod, sv_name, mod_info, indent='\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t'):
    """Generate a single TooltipManualTableField for a modifier."""
    icon = get_icon(mod)
    fmt = script_value_format(mod_info)
    color = gui_color(mod_info)

    return (
        f'{indent}TooltipManualTableField = {{\n'
        f'{indent}\ticon = {{ size = {{ 28 28 }} texture = "{icon}" }}\n'
        f'{indent}\ttext_single = {{ fontsize = 15 text = "MODIFIER_TYPE_NAME_{mod}" }}\n'
        f'{indent}\texpand = {{}}\n'
        f'{indent}\ttext_single = {{ fontsize = 15 default_format = "{color}" '
        f'raw_text = "[Location.MakeScope.ScriptValue(\'{sv_name}\'){fmt}]" }}\n'
        f'{indent}}}'
    )


def generate_side_tooltip_row(mod, value, mod_info, indent='\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t'):
    """Generate a TooltipManualTableField for a side (extraction/production) tooltip."""
    icon = get_icon(mod)
    formatted = format_value(value, mod_info)

    return (
        f'{indent}TooltipManualTableField = {{\n'
        f'{indent}\ticon = {{ size = {{ 28 28 }} texture = "{icon}" }}\n'
        f'{indent}\ttext_single = {{ fontsize = 15 text = "MODIFIER_TYPE_NAME_{mod}" }}\n'
        f'{indent}\texpand = {{}}\n'
        f'{indent}\ttext_single = {{ fontsize = 15 raw_text = "{formatted}" }}\n'
        f'{indent}}}'
    )


def main():
    mod_types = parse_modifier_types()
    base_values, dev_values = parse_static_modifiers()
    extraction, production = classify_modifiers(base_values, dev_values)

    # Generate script values
    sv_content = generate_script_values(extraction, production, mod_types)
    with open(SCRIPT_VALUES_FILE, 'w') as f:
        f.write(sv_content)
    print(f"Wrote script values to {SCRIPT_VALUES_FILE}")

    # Print GUI snippets for copy-paste
    print("\n" + "=" * 60)
    print("EXTRACTION TOOLTIP ROWS (at dev 0, base values only):")
    print("=" * 60)
    indent = '\t\t\t\t\t\t\t\t\t\t'
    for mod, base_val, dev_offset in extraction:
        info = mod_types.get(mod, {'percent': False, 'color': 'good'})
        print(generate_side_tooltip_row(mod, base_val, info, indent))

    print("\n" + "=" * 60)
    print("PRODUCTION TOOLTIP ROWS (at dev 100, full value):")
    print("=" * 60)
    for mod, dev_val in production:
        info = mod_types.get(mod, {'percent': False, 'color': 'good'})
        val_at_100 = dev_val * 100
        print(generate_side_tooltip_row(mod, val_at_100, info, indent))

    print("\n" + "=" * 60)
    print("CURRENT EFFECTS TOOLTIP ROWS (dynamic script values):")
    print("=" * 60)
    indent = '\t\t\t\t\t\t\t\t'
    for mod, base_val, dev_offset in extraction:
        info = mod_types.get(mod, {'percent': False, 'color': 'good'})
        sv_name = f'sul_dev_tt_{mod.replace("local_", "")}'
        print(generate_tooltip_row(mod, sv_name, info, indent))

    for mod, dev_val in production:
        info = mod_types.get(mod, {'percent': False, 'color': 'good'})
        sv_name = f'sul_dev_tt_{mod.replace("local_", "")}'
        print(generate_tooltip_row(mod, sv_name, info, indent))

    print("\nDone.")


if __name__ == '__main__':
    main()
