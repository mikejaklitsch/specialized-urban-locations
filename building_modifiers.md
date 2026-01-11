# Building Modifiers Tracking Document

This document tracks modifier assignments for all buildings in the mod. Edit the assignments in each section, then have Claude implement the changes.

## How to Use
1. Move building names between value tiers to change their modifiers
**!!! Defined values in this file should represent final desired modifier values AFTER adjustment from vanilla values !!!**
**!!! They should NOT account for modifiers from building levels !!!**
2. Only buildings listed under a specific value get that modifier at that value
3. After editing, ask Claude to "implement the changes from building_modifiers.md"

---

# local_monthly_food_modifier

Controls food production bonus/penalty per building level.

## Positive Values

### {0} # Net zero after adjusting from vanilla values
```
cannon_maker
cannon_workshop
cannon_foundry
cannons_factory
hand_cannon_guild
gun_smith
guns_workshop
firearms_manufactory
firearms_factory
tools_guild
tools_workshop
iron_foundry
iron_mill
weapon_guild
weapon_workshop
weapon_manufactory
weapon_factory
steel_mill
jewelry_guild
local_smelters
mercury_patio
stone_quarry
bog_iron_smelter
tar_kiln
lumber_mill
sawmill

dyes_guild
dyes_workshop
dyesworks
dyes_mill
furniture_guild
furniture_workshop
furniture_manufactory
furniture_mill
lacquerware_guild
lacquerware_manufactory

charcoal_maker
improved_charcoal_maker
paper_guild
paper_workshop
paper_manufactory
paper_mill
glass_guild
glass_workshop
glassworks
glass_mill
porcelain_guild
porcelain_manufactory
pottery_guild
pottery_workshop
pottery_manufactory
pottery_mill
apothecary
scriptorium
printing_press_shop
printing_manufactory
printing_mill
cloth_guild
cloth_workshop
cloth_manufactory
textile_mill
fine_cloth_guild
fine_cloth_workshop
fine_cloth_manufactory
fine_cloth_mill
naval_supplies_guild
naval_supplies_workshop
naval_supplies_manufactory
naval_supplies_mill
perfumery
rural_clothmaker
saltpeter_guild
saltpeter_workshop
putrefaction_works
putrefaction_mill
entrepot
trading_hub
customs_house
stock_exchange
clearing_house
market_warehouse
funduq
marketplace
merchants_quarters
grand_marketplace
commerce_center
port_authority
market_village
wharf
dock
dry_dock
shipyard
grand_shipyard
naval_base
sul_inland_wharf
sul_inland_dock
sul_inland_dry_dock
sul_inland_shipyard
sul_inland_grand_shipyard
sul_inland_naval_base

# Non Food Farming
fiber_crops_farm
horse_breeders
sugar_plantation
cotton_plantation
tobacco_plantation
```

### {0.02} - Farming Specialization Buildings (net neutral with building level penalty)
```
# Food Adjacent Goods
elephant_hunting_grounds
tannery
tanning_workshop
tannery_manufactory
tannery_mill
brewery
beer_workshop
brewery_manufactory
brewery_mill
distillers_guild
distillers_workshop
distiller_manufactory
distiller_mill
winery
winery_manufactory

# Food Infrastructure
windmill
granary
```

### {0.05}
```
# Straight up Farming
fruit_orchard
sheep_farms
```

### {0.10}
```
# Force Multipliers
irrigation_systems
fishing_village
farming_village
```

### {0.12}
```
# None currently assigned
```

### {0.15}
```
# None currently assigned
```

### {0.20}
```
# None currently assigned
```

## Negative Values

### {-0.02}
```
# None currently assigned (baseline penalty is applied via script, not here)
```

---

# local_raw_material_output

Controls bonus to raw goods extraction.

## Positive Values

### {0} after adjustment from vanilla
```
# Buildings that should NOT get raw material bonus
entrepot
trading_hub
customs_house
stock_exchange
clearing_house
market_warehouse
funduq
marketplace
merchants_quarters
grand_marketplace
commerce_center
port_authority
market_village
wharf
dock
dry_dock
shipyard
grand_shipyard
naval_base
sul_inland_wharf
sul_inland_dock
sul_inland_dry_dock
sul_inland_shipyard
sul_inland_grand_shipyard
sul_inland_naval_base
cannon_maker
cannon_workshop
cannon_foundry
cannons_factory
hand_cannon_guild
gun_smith
guns_workshop
firearms_manufactory
firearms_factory
weapon_guild
weapon_workshop
weapon_manufactory
weapon_factory
scriptorium
printing_press_shop
printing_manufactory
printing_mill
cloth_guild
cloth_workshop
cloth_manufactory
textile_mill
fine_cloth_guild
fine_cloth_workshop
fine_cloth_manufactory
fine_cloth_mill
naval_supplies_guild
naval_supplies_workshop
naval_supplies_manufactory
naval_supplies_mill
perfumery
rural_clothmaker
mercury_patio
```

### {0.005} - Infrastructure
```
granary
mason
```

### {0.01} - Food/Agricultural Buildings
```
fruit_orchard
fiber_crops_farm
horse_breeders
windmill
irrigation_systems
fishing_village
farming_village
```

### {0.015}
```
# None currently assigned
```

### {0.02}
```
clay_pit
salt_collector
sand_pit
sheep_farms
stone_quarry
bog_iron_smelter
local_smelters
lumber_mill
sawmill
elephant_hunting_grounds
forest_village
sugar_plantation
cotton_plantation
tobacco_plantation
```

### {0.025}
```
# None currently assigned
```

---

# local_max_rgo_size_modifier

Controls bonus to maximum RGO workforce size.

## Positive Values

### {unassigned}
```
# Buildings that should NOT get RGO size bonus
entrepot
trading_hub
customs_house
stock_exchange
clearing_house
market_warehouse
funduq
marketplace
merchants_quarters
grand_marketplace
commerce_center
port_authority
market_village
wharf
dock
dry_dock
shipyard
grand_shipyard
naval_base
sul_inland_wharf
sul_inland_dock
sul_inland_dry_dock
sul_inland_shipyard
sul_inland_grand_shipyard
sul_inland_naval_base
cannon_maker
cannon_workshop
cannon_foundry
cannons_factory
hand_cannon_guild
gun_smith
guns_workshop
firearms_manufactory
firearms_factory
weapon_guild
weapon_workshop
weapon_manufactory
weapon_factory
scriptorium
printing_press_shop
printing_manufactory
printing_mill
cloth_guild
cloth_workshop
cloth_manufactory
textile_mill
fine_cloth_guild
fine_cloth_workshop
fine_cloth_manufactory
fine_cloth_mill
naval_supplies_guild
naval_supplies_workshop
naval_supplies_manufactory
naval_supplies_mill
perfumery
rural_clothmaker
```

### {0.005} - All RGO/Agricultural Buildings
```
clay_pit
salt_collector
sand_pit
sheep_farms
fruit_orchard
fiber_crops_farm
horse_breeders
windmill
irrigation_systems
mercury_patio
stone_quarry
bog_iron_smelter
local_smelters
lumber_mill
sawmill
elephant_hunting_grounds
sugar_plantation
cotton_plantation
tobacco_plantation
granary
mason
```

### {0.01}
```
tools_guild
tools_workshop
iron_foundry
iron_mill
forest_village
fishing_village
farming_village
```

### {0.015}
```
# None currently assigned
```

---

# local_production_efficiency

Controls bonus to industrial/manufacturing output.

## Positive Values

### {0} After adjustment from vanilla
```
# Buildings that should NOT get production efficiency bonus
wharf
dock
dry_dock
shipyard
grand_shipyard
naval_base
sul_inland_wharf
sul_inland_dock
sul_inland_dry_dock
sul_inland_shipyard
sul_inland_grand_shipyard
sul_inland_naval_base
fruit_orchard
fiber_crops_farm
horse_breeders
fishing_village
farming_village
forest_village
clay_pit
salt_collector
sand_pit
sheep_farms
mercury_patio
stone_quarry
bog_iron_smelter
lumber_mill
sawmill
elephant_hunting_grounds
sugar_plantation
cotton_plantation
tobacco_plantation
local_smelters
windmill
```

### {0.005}
```
market_village
granary
```

### {0.01} - Intermediate Goods / Standard Industry
```
entrepot
trading_hub
customs_house
stock_exchange
clearing_house
market_warehouse
funduq
marketplace
merchants_quarters
grand_marketplace
commerce_center
port_authority



tools_guild
tools_workshop
iron_foundry
iron_mill
weapon_guild
weapon_workshop
weapon_manufactory
weapon_factory
steel_mill
tar_kiln
dyes_guild
dyes_workshop
dyesworks
dyes_mill
tannery
tanning_workshop
tannery_manufactory
tannery_mill
charcoal_maker
improved_charcoal_maker

pottery_guild
pottery_workshop
pottery_manufactory
pottery_mill
apothecary
cloth_guild
cloth_workshop
cloth_manufactory
textile_mill

furniture_guild
furniture_workshop
furniture_manufactory
furniture_mill
naval_supplies_guild
naval_supplies_workshop
naval_supplies_manufactory
naval_supplies_mill
rural_clothmaker
brewery
beer_workshop
brewery_manufactory
brewery_mill
winery
winery_manufactory
saltpeter_guild
saltpeter_workshop
putrefaction_works
putrefaction_mill
mason

```

### {0.015} - Advanced Goods / Luxury Industry
```
paper_guild
paper_workshop
paper_manufactory
paper_mill
glass_guild
glass_workshop
glassworks
glass_mill
distillers_guild
distillers_workshop
distiller_manufactory
distiller_mill
fine_cloth_guild
fine_cloth_workshop
fine_cloth_manufactory
fine_cloth_mill
jewelry_guild
lacquerware_guild
lacquerware_manufactory
porcelain_guild
porcelain_manufactory
scriptorium
printing_press_shop
printing_manufactory
printing_mill
perfumery
cannon_maker
cannon_workshop
cannon_foundry
cannons_factory
hand_cannon_guild
gun_smith
guns_workshop
firearms_manufactory
firearms_factory
```

### {0.02}
```
# None currently assigned
```

### {0.025}
```
# None currently assigned
```

---

# Vanilla Building Reference

This section documents what modifiers vanilla buildings have (before this mod modifies them). Use this as reference when deciding what bonuses to add.

## RGO/Extraction Buildings (Vanilla)
| Building | Type | Vanilla Modifiers |
|----------|------|-------------------|
| fishing_village | village | local_monthly_food +1.5, local_fish_output_modifier +0.1 |
| farming_village | village | local_monthly_food +2.0, local_food_capacity +50 |
| forest_village | village | local_monthly_development +0.002 |
| market_village | village | (none) |

## Industrial Buildings (Vanilla)
Most guild/workshop/manufactory buildings have no location modifiers in vanilla - they just have production methods for input/output conversion.

## Trade Buildings (Vanilla)
| Building | Vanilla Modifiers |
|----------|-------------------|
| marketplace | merchant_capacity_from_building +1 |
| merchants_quarters | merchant_capacity_from_building +1.5 |
| grand_marketplace | merchant_capacity_from_building +2.0 |
| commerce_center | merchant_capacity_from_building +4.0 |
| port_authority | merchant_capacity_from_building +0.5 |
| funduq | merchant_capacity_from_building +1.0 |

## Naval Infrastructure (Vanilla)
| Building | Vanilla Modifiers |
|----------|-------------------|
| wharf | local_sailors +0.001 |
| dock | local_sailors +0.008 |
| dry_dock | local_sailors +0.016 |
| shipyard | local_sailors +0.032 |
| grand_shipyard | local_sailors +0.063 |
| naval_base | local_sailors +0.1 |

## Market Center Buildings (Vanilla)
| Building | Vanilla Modifiers |
|----------|-------------------|
| entrepot | merchant_capacity_from_building +10, trade_center_power +0.1 |
| trading_hub | merchant_capacity_from_building +10, trade_center_power +0.1 |
| customs_house | merchant_capacity_from_building +10, trade_center_power +0.1 |
| stock_exchange | merchant_capacity_from_building +10, trade_center_power +0.1 |
| clearing_house | merchant_capacity_from_building +10, trade_center_power +0.1 |
| market_warehouse | merchant_capacity_from_building +1, merchant_power +1, maximum_stockpile_capacity +200 |

---

# Implementation Notes

## Files That Must Be Updated

When changing a building's modifier assignments, ALL of the following locations must be updated:

### 1. Building Type Files (actual modifier values)
These files contain the `modifier = { }` blocks that apply the actual in-game effects:

| File | Buildings Defined |
|------|-------------------|
| `in_game/common/building_types/sul_mining.txt` | mercury_patio, stone_quarry, bog_iron_smelter, local_smelters, cannon_*, gun_*, firearms_*, tools_*, iron_*, weapon_*, steel_mill, jewelry_guild |
| `in_game/common/building_types/sul_farming.txt` | fruit_orchard, fiber_crops_farm, horse_breeders, windmill, irrigation_systems, sugar_plantation, cotton_plantation, tobacco_plantation, saltpeter_guild, brewery*, distiller*, winery*, saltpeter_workshop, putrefaction_* |
| `in_game/common/building_types/sul_gathering.txt` | clay_pit, salt_collector, sand_pit, sheep_farms, glass_*, porcelain_*, pottery_*, apothecary |
| `in_game/common/building_types/sul_woodland.txt` | lumber_mill, tar_kiln, sawmill, elephant_hunting_grounds, dyes_*, furniture_*, lacquerware_*, tannery*, charcoal_maker, improved_charcoal_maker, paper_* |
| `in_game/common/building_types/sul_commercial.txt` | entrepot, trading_hub, customs_house, stock_exchange, clearing_house, market_warehouse, funduq, scriptorium, printing_*, cloth_*, fine_cloth_*, naval_supplies_*, perfumery, marketplace, merchants_quarters, grand_marketplace, commerce_center, port_authority, rural_clothmaker |
| `in_game/common/building_types/sul_village_buildings.txt` | market_village, fishing_village, farming_village, forest_village, granary, mason |
| `in_game/common/building_types/sul_naval_infra_trade.txt` | wharf, dock, dry_dock, shipyard, grand_shipyard, naval_base, sul_inland_* |

### 2. Script Values File (tooltip calculations)
This file calculates the modifier values shown in GUI tooltips:

**File:** `in_game/common/script_values/sul_building_externalities.txt`

Script values to update for each modifier type:
- `sul_building_food_modifier` - calculates food bonus per building
- `sul_building_raw_modifier` - calculates raw material output bonus
- `sul_building_rgo_modifier` - calculates RGO size bonus
- `sul_building_efficiency_modifier` - calculates production efficiency bonus

Each script value contains a series of `if/else_if` blocks checking building types. When adding/removing a building from a modifier tier, update the corresponding block.

### 3. GUI Template File (tooltip display)
This file defines what buildings are listed in each tooltip section:

**File:** `in_game/gui/aaa_sul_templates.gui`

Templates to update:
- `sul_food_breakdown_tooltip` - lists buildings that affect food production
- `sul_raw_breakdown_tooltip` - lists buildings that affect raw material output
- `sul_rgo_breakdown_tooltip` - lists buildings that affect RGO size
- `sul_efficiency_breakdown_tooltip` - lists buildings that affect production efficiency

Each template has `TooltipManualTableField` entries for buildings. Add/remove entries when changing which buildings get which modifiers.

## Implementation Checklist CRITICAL

When changing a building's modifier:

- [ ] **Building file**: Update `modifier = { }` block with new values
- [ ] **Script values**: Update `sul_building_*_modifier` calculation
- [ ] **GUI tooltips**: Update breakdown tooltip template entries
- [ ] **This document**: Move building name to correct tier section

## Quick Reference: INJECT vs REPLACE

- **INJECT**: Adds to/modifies vanilla buildings. Only include the modifier block you're adding.
- **REPLACE**: Completely replaces vanilla buildings. Must include ALL building properties including production methods inline.

## Current Design Philosophy

### Baseline Penalty (applied via script to ALL buildings)
- local_monthly_food_modifier: -0.02
- local_raw_material_output: -0.005
- local_max_rgo_size_modifier: -0.005
- local_production_efficiency: -0.005

### Building Categories

**Raw Extraction (RGO buildings)**
- +0.015 raw_material_output, +0.005 rgo_size
- No food modifier (net -0.02 food)
- Examples: mines, quarries, lumber mills, clay pits

**Food/Agricultural (farming buildings)**
- +0.02 food (net 0 with baseline)
- +0.01 raw_material_output, +0.005 rgo_size
- Examples: orchards, plantations, windmills

**Intermediate Industry (processing goods)**
- +0.01 production_efficiency
- No raw/rgo bonuses
- No food modifier (net -0.02 food)
- Examples: tool shops, tanneries, cloth workshops

**Advanced Industry (luxury goods)**
- +0.015 production_efficiency
- No raw/rgo bonuses
- No food modifier (net -0.02 food)
- Examples: jewelry, furniture, porcelain, printing

**Trade/Commercial (merchant buildings)**
- No positive bonuses (baseline penalty only)
- Examples: markets, trade centers, ports

**Village Buildings**
- +1 free_building_levels (makes them effectively free)
- +0.12 food for farming/fishing villages
- +0.015 raw/+0.005 rgo for woodland villages
