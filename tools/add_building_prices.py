#!/usr/bin/env python3
"""Add price = X after build_time line for specified buildings."""
import re, sys, os

def add_price_to_buildings(filepath, building_prices):
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    current_building = None
    depth = 0
    changes = 0
    result = []

    for line in lines:
        stripped = line.strip()

        if depth == 0:
            m = re.match(r'^(?:(?:REPLACE|INJECT|TRY_INJECT):)?([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\{', stripped)
            if m:
                name = m.group(1)
                is_inject = stripped.startswith('INJECT:') or stripped.startswith('TRY_INJECT:')
                current_building = name if not is_inject else None
                depth = stripped.count('{') - stripped.count('}')
                result.append(line)
                continue

        if depth > 0:
            depth += stripped.count('{') - stripped.count('}')

        result.append(line)

        if current_building and current_building in building_prices:
            if re.match(r'build_time\s*=', stripped):
                indent = line[:len(line) - len(line.lstrip())]
                result.append(indent + 'price = ' + building_prices[current_building] + '\n')
                changes += 1
                del building_prices[current_building]

        if depth <= 0 and current_building:
            current_building = None

    with open(filepath, 'w', encoding='utf-8-sig') as f:
        f.writelines(result)

    return changes

B = 'sul_basic_building'
E = 'sul_essential_building'
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bt = os.path.join(base, 'in_game', 'common', 'building_types')

tasks = [
    ('sul_crop_buildings.txt', {n: B for n in [
        'fruit_orchard', 'sul_wheat_field', 'sul_rice_paddy', 'sul_maize_field',
        'sul_millet_field', 'sul_potato_field', 'sul_legume_field',
        'sul_pastureland', 'sul_olive_grove', 'sul_fishing_ground']}),
    ('sul_mining.txt', {n: B for n in [
        'sul_iron_mine', 'sul_marble_quarry', 'mercury_patio', 'stone_quarry',
        'bog_iron_smelter', 'local_smelters',
        'sul_rural_blacksmith', 'sul_rural_weaponmaker', 'sul_rural_jeweler']}),
    ('sul_gathering.txt', {n: B for n in [
        'clay_pit', 'salt_collector', 'sand_pit', 'sheep_farms',
        'sul_rural_glassmaker', 'sul_rural_potter', 'sul_rural_herbalist']}),
    ('sul_woodland.txt', {n: B for n in [
        'lumber_mill', 'tar_kiln', 'elephant_hunting_grounds', 'sawmill',
        'sul_rural_carpenter', 'sul_rural_papermaker', 'sul_rural_apiary', 'sul_rural_tanner']}),
    ('sul_village_buildings.txt', {
        **{n: B for n in ['farming_village', 'fishing_village', 'sul_mining_village',
                          'forest_village', 'market_village']},
        'mason': E}),
    ('sul_farming.txt', {
        **{n: B for n in ['fiber_crops_farm', 'horse_breeders', 'granary', 'windmill',
                          'irrigation_systems', 'sul_rural_brewer', 'sul_rural_winemaker',
                          'sul_rural_distiller']},
        'sul_farmers_market': E}),
    ('sul_commercial.txt', {'sul_rural_ropemaker': B}),
]

total = 0
for filename, prices in tasks:
    path = os.path.join(bt, filename)
    c = add_price_to_buildings(path, dict(prices))
    print(f'{filename}: {c} prices added')
    total += c

print(f'\nTotal: {total} prices added')
