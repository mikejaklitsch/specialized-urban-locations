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

# Goods -> positive icon (auto-maps good_name to good_name_positive.dds)
# Only override here if the icon name doesn't follow the pattern
GOODS_ICON_OVERRIDES = {
    'goods_gold': 'goods_gold_positive',
    'beeswax': 'beewax_positive',
    'legumes': 'legume_positive',
}


def get_icon(modifier_name):
    """Get the icon path for a modifier."""
    if modifier_name in ICON_MAP:
        return ICON_MAP[modifier_name]
    # Auto-derive goods positive icon from modifier name
    m = re.match(r'local_(\w+)_output_modifier', modifier_name)
    if m:
        good = m.group(1)
        icon_name = GOODS_ICON_OVERRIDES.get(good, f'{good}_positive')
        return f'gfx/interface/icons/modifier_types/{icon_name}.dds'
    return 'gfx/interface/icons/modifier_types/_default.dds'


def parse_modifier_types():
    """Parse vanilla modifier type definitions for percent/color info."""
    defs = {}
    for fn in os.listdir(VANILLA_MODIFIER_DEFS):
        if not fn.endswith('.txt'):
            continue
        with open(os.path.join(VANILLA_MODIFIER_DEFS, fn), encoding='utf-8-sig') as f:
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
    with open(STATIC_MOD_FILE, encoding='utf-8-sig') as f:
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
        # local_trade_center_power: now a tradeoff (-10% base → +10% at dev 100)
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
    extraction_names = {e[0] for e in extraction}
    for mod, dev_val in dev_values.items():
        if mod in skip:
            continue
        if mod in extraction_names:
            continue
        if dev_val > 0:
            production.append((mod, dev_val))
        elif dev_val != 0 and mod not in base_values:
            production.append((mod, dev_val))

    # Sort alphabetically within each category
    extraction.sort(key=lambda x: x[0])
    production.sort(key=lambda x: x[0])

    return extraction, production


def format_value(value, mod_info):
    """Format a static value for display in side tooltips."""
    is_pct = mod_info.get('percent', False)
    is_bad = mod_info.get('color') == 'bad'

    # Color: good modifiers are green when positive, red when negative
    # Bad modifiers (unrest, demotion) are red when positive, green when negative
    if is_bad:
        color = '#color_red' if value >= 0 else '#color_green'
    else:
        color = '#color_green' if value >= 0 else '#color_red'

    sign = '+' if value >= 0 else ''

    if is_pct:
        display = value * 100
        if abs(display - round(display)) < 0.001:
            return f'{color} {sign}{int(round(display))}%#!'
        else:
            return f'{color} {sign}{display:.1f}%#!'
    else:
        if abs(value) < 0.01:
            return f'{color} {sign}{value:.4f}#!'
        elif abs(value) < 0.1:
            return f'{color} {sign}{value:.2f}#!'
        else:
            return f'{color} {sign}{value:.1f}#!'


def script_value_format(mod_info, mod_name=''):
    """Return the GUI format code for a script value display."""
    is_pct = mod_info.get('percent', False)
    already_pct = mod_info.get('already_percent', False)
    if already_pct:
        return '|+=4'
    if is_pct:
        return '|+=2%'
    return '|+=2'


def gui_color(mod_info):
    """Return the default_format color for a modifier."""
    is_bad = mod_info.get('color') == 'bad'
    return '#color_red' if is_bad else '#color_green'


def generate_script_values(extraction, production, mod_types, base_values):
    """Generate script values file for current-development display."""
    lines = ['# AUTO-GENERATED by tools/generate_dev_tooltip.py — do not hand-edit', '']

    def fmt(v):
        """Format float without scientific notation."""
        return f'{v:.10f}'.rstrip('0').rstrip('.')

    # Extraction: base - dev * |offset|
    for mod, base_val, dev_offset in extraction:
        sv_name = f'sul_dev_tt_{mod.replace("local_", "")}'
        lines.append(f'{sv_name} = {{')
        lines.append(f'\tvalue = {fmt(base_val)}')
        if dev_offset != 0:
            lines.append(f'\tsubtract = {{')
            lines.append(f'\t\tvalue = development')
            lines.append(f'\t\tmultiply = {fmt(abs(dev_offset))}')
            lines.append(f'\t}}')
        lines.append('}')
        lines.append('')

    # Production: base + dev * val
    for mod, dev_val in production:
        sv_name = f'sul_dev_tt_{mod.replace("local_", "")}'
        base = base_values.get(mod, 0)
        lines.append(f'{sv_name} = {{')
        lines.append(f'\tvalue = {fmt(base)}')
        lines.append(f'\tadd = {{')
        lines.append(f'\t\tvalue = development')
        lines.append(f'\t\tmultiply = {fmt(dev_val)}')
        lines.append(f'\t}}')
        lines.append('}')
        lines.append('')

    return '\n'.join(lines)


def format_static_value(value, mod_info, mod_name):
    """Format a precomputed value using the same rules as the engine format code."""
    is_pct = mod_info.get('percent', False)
    already_pct = mod_info.get('already_percent', False)
    decimals = 4 if already_pct else 2
    sign = '+' if value >= 0 else ''
    if already_pct:
        return f'{sign}{value:.{decimals}f}%'
    if is_pct:
        return f'{sign}{value * 100:.{decimals}f}%'
    return f'{sign}{value:.{decimals}f}'


def format_script_ref(mod_name, mod_info):
    """Build a script value reference string with engine format code."""
    sv_name = f'sul_dev_tt_{mod_name.replace("local_", "")}'
    fmt = script_value_format(mod_info, mod_name)
    suffix = '%' if mod_info.get('already_percent', False) else ''
    return f"[Location.MakeScope.ScriptValue('{sv_name}'){fmt}]{suffix}"


def compute_color(value, mod_info):
    """Determine display color from value sign and modifier type."""
    is_bad = mod_info.get('color') == 'bad'
    if is_bad:
        return '#color_red' if value >= 0 else '#color_green'
    else:
        return '#color_green' if value >= 0 else '#color_red'


def generate_row(mod, color, value_display, indent, dynamic_color=False):
    """Single unified row generator.

    dynamic_color: emit two overlapping value texts with visibility toggled by sign.
    """
    icon = get_icon(mod)
    if not dynamic_color:
        return (
            f'{indent}TooltipManualTableField = {{\n'
            f'{indent}\ticon = {{ size = {{ 28 28 }} texture = "{icon}" }}\n'
            f'{indent}\ttext_single = {{ fontsize = 15 text = "MODIFIER_TYPE_NAME_{mod}" }}\n'
            f'{indent}\texpand = {{}}\n'
            f'{indent}\ttext_single = {{ fontsize = 15 default_format = "{color}" raw_text = "{value_display}" }}\n'
            f'{indent}}}'
        )
    sv_name = f'sul_dev_tt_{mod.replace("local_", "")}'
    is_bad = color == '#color_red'
    pos_color = '#color_red' if is_bad else '#color_green'
    neg_color = '#color_green' if is_bad else '#color_red'
    ge_zero = f"[Not(LessThan_CFixedPoint(Location.MakeScope.ScriptValue('{sv_name}'), '(CFixedPoint)0'))]"
    lt_zero = f"[LessThan_CFixedPoint(Location.MakeScope.ScriptValue('{sv_name}'), '(CFixedPoint)0')]"
    return (
        f'{indent}TooltipManualTableField = {{\n'
        f'{indent}\ticon = {{ size = {{ 28 28 }} texture = "{icon}" }}\n'
        f'{indent}\ttext_single = {{ fontsize = 15 text = "MODIFIER_TYPE_NAME_{mod}" }}\n'
        f'{indent}\texpand = {{}}\n'
        f'{indent}\ttext_single = {{ visible = "{ge_zero}" fontsize = 15 default_format = "{pos_color}" raw_text = "{value_display}" }}\n'
        f'{indent}\ttext_single = {{ visible = "{lt_zero}" fontsize = 15 default_format = "{neg_color}" raw_text = "{value_display}" }}\n'
        f'{indent}}}'
    )


def generate_rows_block(rows_list):
    """Join a list of row strings with newlines."""
    return '\n'.join(rows_list)


def generate_section_header(title, indent):
    """Generate a section header text within a tooltip scroll area."""
    return (
        f'{indent}text_single = {{\n'
        f'{indent}\traw_text = "#bold {title}#!"\n'
        f'{indent}\tdefault_format = "#color_goldy_yellow"\n'
        f'{indent}\tmargin_top = 5\n'
        f'{indent}}}'
    )


def is_goods_modifier(name):
    return '_output_modifier' in name


def split_by_type(modifiers):
    """Split a list of (mod, ...) tuples into (location_mods, goods_mods)."""
    location = []
    goods = []
    for item in modifiers:
        mod = item[0]
        if is_goods_modifier(mod):
            goods.append(item)
        else:
            location.append(item)
    return location, goods


def inject_into_gui(gui_path, extraction, production, mod_types, base_values):
    """Replace marked sections in the GUI file with generated content.

    Marker format in .gui file:
        # BEGIN_GENERATED: <section_name>
        ... (replaced content) ...
        # END_GENERATED: <section_name>

    Sections: EXTRACTION_ROWS, PRODUCTION_ROWS, CURRENT_EFFECTS_ROWS
    """
    with open(gui_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()

    sections = {}

    # Split extraction and production into location vs goods
    ext_location, ext_goods = split_by_type(extraction)
    prod_location, prod_goods = split_by_type(production)

    def make_row(mod, info, dev_level, base_val, dev_per_point, indent):
        """Build a single row for any dev level. Returns None if value is zero (static only)."""
        if dev_level == 'current':
            value_display = format_script_ref(mod, info)
            color = gui_color(info)
            return generate_row(mod, color, value_display, indent, dynamic_color=True)
        else:
            value = base_val + dev_level * dev_per_point
            if abs(value) < 0.00001:
                return None
            value_display = format_static_value(value, info, mod)
            color = compute_color(value, info)
            return generate_row(mod, color, value_display, indent)

    def generate_grouped_rows(dev_level, indent):
        """Generate location/extraction/production row groups for a dev level."""
        result = {}

        rows = []
        for mod, base_val, dev_offset in ext_location:
            info = mod_types.get(mod, {'percent': False, 'color': 'good'})
            row = make_row(mod, info, dev_level, base_val, dev_offset, indent)
            if row:
                rows.append(row)
        for item in prod_location:
            mod = item[0]
            dev_val = item[1]
            base = base_values.get(mod, 0)
            info = mod_types.get(mod, {'percent': False, 'color': 'good'})
            row = make_row(mod, info, dev_level, base, dev_val, indent)
            if row:
                rows.append(row)
        result['LOCATION'] = rows

        rows = []
        for mod, base_val, dev_offset in ext_goods:
            info = mod_types.get(mod, {'percent': False, 'color': 'good'})
            row = make_row(mod, info, dev_level, base_val, dev_offset, indent)
            if row:
                rows.append(row)
        result['EXTRACTION'] = rows

        rows = []
        for item in prod_goods:
            mod = item[0]
            dev_val = item[1]
            base = base_values.get(mod, 0)
            info = mod_types.get(mod, {'percent': False, 'color': 'good'})
            row = make_row(mod, info, dev_level, base, dev_val, indent)
            if row:
                rows.append(row)
        result['PRODUCTION'] = rows

        return result

    # All three tooltips use the same three-list structure
    for dev_level, prefix in [(0, 'DEV0'), (100, 'DEV100'), ('current', 'CURRENT')]:
        indent = '\t\t\t\t\t\t\t\t\t\t' if dev_level != 'current' else '\t\t\t\t\t\t\t\t'
        groups = generate_grouped_rows(dev_level, indent)
        sections[f'{prefix}_LOCATION_ROWS'] = generate_rows_block(groups['LOCATION'])
        sections[f'{prefix}_EXTRACTION_ROWS'] = generate_rows_block(groups['EXTRACTION'])
        sections[f'{prefix}_PRODUCTION_ROWS'] = generate_rows_block(groups['PRODUCTION'])

    replaced = 0
    for section_name, new_content in sections.items():
        begin = f'# BEGIN_GENERATED: {section_name}'
        end = f'# END_GENERATED: {section_name}'
        pattern = re.compile(
            rf'({re.escape(begin)}\n)(.*?)(\s*{re.escape(end)})',
            re.DOTALL
        )
        m = pattern.search(content)
        if m:
            content = content[:m.start(2)] + new_content + content[m.start(3):]
            replaced += 1
            print(f"  Replaced section: {section_name}")
        else:
            print(f"  WARNING: Marker not found for {section_name}")

    if replaced > 0:
        with open(gui_path, 'w', encoding='utf-8-sig') as f:
            f.write(content)

    return replaced


def generate_template_skeleton():
    """Generate the full location_development_tooltip template skeleton.

    The tooltip is on the parent widget so it covers both the monthly badge
    and the progress bar. Generated rows are inserted at the markers.
    """
    def side_tooltip(title_key, title_icon, desc_key, loc_marker, ext_marker, prod_marker):
        return f"""
					tooltipwidget = {{
						ContextualTooltipType = {{
							blockoverride "title_text" {{ text = "{title_key}" }}
							blockoverride "title_icon" {{
								ContextualTooltipDefaultIcon = {{
									blockoverride "title_icon_texture" {{ texture = "{title_icon}" }}
								}}
							}}
							blockoverride "tooltip_content" {{
								TooltipTextBlock = {{
									blockoverride "text" {{ text = "{desc_key}" }}
								}}
								TooltipListBase = {{
									blockoverride "block_title" {{ text = "SUL_DEV_CURRENT_LOCATION_TITLE" }}
									TooltipListScrollArea = {{
										blockoverride "block_scrollarea" {{
											maximumsize = {{ -1 150 }}
											minimumsize = {{ -1 30 }}
										}}
										blockoverride "scrollarea_content" {{
											vbox = {{
												set_parent_dimension_to_minimum = height
												layoutpolicy_horizontal = expanding
												# BEGIN_GENERATED: {loc_marker}
												# END_GENERATED: {loc_marker}
											}}
										}}
									}}
								}}
								TooltipListBase = {{
									blockoverride "block_title" {{ text = "SUL_DEV_CURRENT_EXTRACTION_TITLE" }}
									TooltipListScrollArea = {{
										blockoverride "block_scrollarea" {{
											maximumsize = {{ -1 150 }}
											minimumsize = {{ -1 30 }}
										}}
										blockoverride "scrollarea_content" {{
											vbox = {{
												set_parent_dimension_to_minimum = height
												layoutpolicy_horizontal = expanding
												# BEGIN_GENERATED: {ext_marker}
												# END_GENERATED: {ext_marker}
											}}
										}}
									}}
								}}
								TooltipListBase = {{
									blockoverride "block_title" {{ text = "SUL_DEV_CURRENT_PRODUCTION_TITLE" }}
									TooltipListScrollArea = {{
										blockoverride "block_scrollarea" {{
											maximumsize = {{ -1 150 }}
											minimumsize = {{ -1 30 }}
										}}
										blockoverride "scrollarea_content" {{
											vbox = {{
												set_parent_dimension_to_minimum = height
												layoutpolicy_horizontal = expanding
												# BEGIN_GENERATED: {prod_marker}
												# END_GENERATED: {prod_marker}
											}}
										}}
									}}
								}}
							}}
						}}
					}}"""

    # Current effects tooltip uses shallower indent (8 tabs vs 10)
    current_tooltip = f"""
				TooltipListBase = {{
					blockoverride "block_title" {{ text = "SUL_DEV_CURRENT_EFFECTS_TITLE" }}
					TooltipListScrollArea = {{
						blockoverride "block_scrollarea" {{
							maximumsize = {{ -1 225 }}
							minimumsize = {{ -1 30 }}
						}}
						blockoverride "scrollarea_content" {{
							vbox = {{
								set_parent_dimension_to_minimum = height
								layoutpolicy_horizontal = expanding
								# BEGIN_GENERATED: CURRENT_LOCATION_ROWS
								# END_GENERATED: CURRENT_LOCATION_ROWS
							}}
						}}
					}}
				}}
				TooltipListBase = {{
					blockoverride "block_title" {{ text = "SUL_DEV_CURRENT_EXTRACTION_TITLE" }}
					TooltipListScrollArea = {{
						blockoverride "block_scrollarea" {{
							maximumsize = {{ -1 225 }}
							minimumsize = {{ -1 30 }}
						}}
						blockoverride "scrollarea_content" {{
							vbox = {{
								set_parent_dimension_to_minimum = height
								layoutpolicy_horizontal = expanding
								# BEGIN_GENERATED: CURRENT_EXTRACTION_ROWS
								# END_GENERATED: CURRENT_EXTRACTION_ROWS
							}}
						}}
					}}
				}}
				TooltipListBase = {{
					blockoverride "block_title" {{ text = "SUL_DEV_CURRENT_PRODUCTION_TITLE" }}
					TooltipListScrollArea = {{
						blockoverride "block_scrollarea" {{
							maximumsize = {{ -1 225 }}
							minimumsize = {{ -1 30 }}
						}}
						blockoverride "scrollarea_content" {{
							vbox = {{
								set_parent_dimension_to_minimum = height
								layoutpolicy_horizontal = expanding
								# BEGIN_GENERATED: CURRENT_PRODUCTION_ROWS
								# END_GENERATED: CURRENT_PRODUCTION_ROWS
							}}
						}}
					}}
				}}"""

    extraction_side = side_tooltip(
        'SUL_DEV_EXTRACTION_TITLE',
        'gfx/interface/icons/modifier_types/global_raw_material_output.dds',
        'SUL_DEV_EXTRACTION_DESC',
        'DEV0_LOCATION_ROWS', 'DEV0_EXTRACTION_ROWS', 'DEV0_PRODUCTION_ROWS')

    production_side = side_tooltip(
        'SUL_DEV_PRODUCTION_TITLE',
        'gfx/interface/icons/modifier_types/global_production_efficiency.dds',
        'SUL_DEV_PRODUCTION_DESC',
        'DEV100_LOCATION_ROWS', 'DEV100_EXTRACTION_ROWS', 'DEV100_PRODUCTION_ROWS')

    return f"""
template location_development_tooltip {{
	ContextualTooltipType = {{

		blockoverride "title_icon" {{
			icon = {{
				using = tooltip_title_icon_size
				texture = "gfx/interface/icons/location_icons/development.dds"
			}}
		}}

		blockoverride "title_text" {{
			text = "DEVELOPMENT_IN_LOC"
		}}

		blockoverride "concept_link" {{
			text = [development|e]
		}}

		blockoverride "tooltip_content" {{
			widget = {{
				size = {{ 400 62 }}

				tooltipwidget = {{
					ContextualTooltipType = {{
						blockoverride "title_text" {{ text = "SUL_DEV_EQUILIBRIUM_HEADER" }}
						blockoverride "title_icon" {{
							ContextualTooltipDefaultIcon = {{
								blockoverride "title_icon_texture" {{ texture = "gfx/interface/icons/location_icons/development.dds" }}
							}}
						}}
						blockoverride "tooltip_content" {{
							TooltipTextBlock = {{
								blockoverride "text" {{ text = "SUL_DEV_EQUILIBRIUM_DESC" }}
							}}
							TooltipListBase = {{
								blockoverride "block_title" {{}}
								TooltipListRowContent = {{
									TooltipManualTableField = {{
										text_single = {{ fontsize = 15 text = "SUL_DEV_CURRENT_LABEL" }}
										expand = {{}}
										text_single = {{ fontsize = 15 raw_text = "[Location.GetDevelopment|2]" }}
									}}
								}}
								TooltipListRowContent = {{
									TooltipManualTableField = {{
										text_single = {{ fontsize = 15 text = "SUL_DEV_TOTAL_LABEL" }}
										expand = {{}}
										text_single = {{ fontsize = 15 raw_text = "[Location.MakeScope.ScriptValue('sul_total_monthly_development')|+4]" }}
									}}
								}}
								TooltipListRowContent = {{
									TooltipManualTableField = {{
										text_single = {{ fontsize = 15 text = "SUL_DEV_EQUILIBRIUM_LABEL" }}
										expand = {{}}
										text_single = {{ fontsize = 15 raw_text = "[Location.MakeScope.ScriptValue('sul_development_equilibrium')|2]" }}
									}}
								}}
							}}
							TooltipStringPairList = {{
								blockoverride "block_title" {{
									datacontext = "[Location]"
									text = "SUL_DEV_TOTAL_LABEL"
								}}
								textcontext = "[Location.GetDescriptionValueAndPercentWithCountryFor('local_monthly_development','local_monthly_development_modifier','global_monthly_development')]"
							}}
						}}
					}}
				}}

				# Monthly change badge (centered on bar, renders behind)
				widget = {{
					position = {{ 100 7 }}
					size = {{ 200 24 }}

					icon = {{
						position = {{ -5 0 }}
						size = {{ 50 24 }}
						using = left_decoration_icon
					}}

					icon = {{
						position = {{ 155 0 }}
						size = {{ 50 24 }}
						using = right_decoration_icon
					}}

					using = bg_mapmenu_tab

					text_single = {{
						parentanchor = center
						fontsize = 13
						align = center|nobaseline
						text = "SUL_DEV_MONTHLY_VALUE"
					}}
				}}

				# Bordered bar area
				widget = {{
					position = {{ 14 28 }}
					size = {{ 372 34 }}

					using = bg_paper_card
					using = bg_cabinet_card_frame

					progressbar = {{
						position = {{ 18 8 }}
						size = {{ 336 16 }}
						using = progress_bar_green_red_alt
						min = 0
						max = 1
						value = "[Divide_float(FixedPointToFloat(Location.GetDevelopment), '(float)100.0')]"
						direction = horizontal
					}}

					progressbar = {{
						position = {{ 18 24 }}
						size = {{ 336 4 }}
						using = progress_bar_blue_alt
						min = 0
						max = 1
						value = "[Divide_float(FixedPointToFloat(Location.MakeScope.ScriptValue('sul_development_equilibrium')), '(float)100.0')]"
						direction = horizontal
					}}

					icon = {{
						position = {{ 102 8 }}
						size = {{ 2 20 }}
						texture = "gfx/interface/progressbars/progress_black.dds"
						spriteType = Corneredstretched
						spriteborder = {{ 1 1 }}
						alpha = 0.3
					}}

					icon = {{
						position = {{ 186 8 }}
						size = {{ 2 20 }}
						texture = "gfx/interface/progressbars/progress_black.dds"
						spriteType = Corneredstretched
						spriteborder = {{ 1 1 }}
						alpha = 0.9
					}}

					icon = {{
						position = {{ 270 8 }}
						size = {{ 2 20 }}
						texture = "gfx/interface/progressbars/progress_black.dds"
						spriteType = Corneredstretched
						spriteborder = {{ 1 1 }}
						alpha = 0.3
					}}
				}}

				# Extraction icon (left)
				widget = {{
					position = {{ 0 31 }}
					size = {{ 29 29 }}
					using = bg_circle
					using = bg_circle_piechart
{extraction_side}

					icon = {{
						size = {{ 60% 60% }}
						parentanchor = center
						texture = "gfx/interface/icons/modifier_types/global_raw_material_output.dds"
					}}
				}}

				# Production icon (right)
				widget = {{
					position = {{ 371 31 }}
					size = {{ 29 29 }}
					using = bg_circle
					using = bg_circle_piechart
{production_side}

					icon = {{
						size = {{ 60% 60% }}
						parentanchor = center
						texture = "gfx/interface/icons/modifier_types/global_production_efficiency.dds"
					}}
				}}
			}}

			# Current effects at this development level
{current_tooltip}
		}}
	}}
}}
"""


def main():
    mod_types = parse_modifier_types()
    base_values, dev_values = parse_static_modifiers()
    extraction, production = classify_modifiers(base_values, dev_values)

    # Generate script values
    sv_content = generate_script_values(extraction, production, mod_types, base_values)
    with open(SCRIPT_VALUES_FILE, 'w', encoding='utf-8-sig') as f:
        f.write(sv_content)
    print(f"Wrote script values to {SCRIPT_VALUES_FILE}")

    # Write the full GUI file (this file is entirely generator-owned)
    gui_path = os.path.join(MOD_ROOT, "in_game", "gui", "shared", "aaa_sul_development_tooltip.gui")
    skeleton = generate_template_skeleton()
    with open(gui_path, 'w', encoding='utf-8-sig') as f:
        f.write(skeleton)
    print(f"Wrote template to {gui_path}")

    # Inject generated rows into markers
    count = inject_into_gui(gui_path, extraction, production, mod_types, base_values)
    if count == 0:
        print("  ERROR: No markers found after template generation")

    print("\nDone.")


if __name__ == '__main__':
    main()
