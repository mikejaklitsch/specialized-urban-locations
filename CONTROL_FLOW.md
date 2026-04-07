# SUL Mod — Variable & Data Flow Reference

Authoritative map of every persistent variable, variable map, modifier, and global flag.
Organized by subsystem. **Update this document when adding, removing, or renaming any variable.**

---

## Execution Order (sul_hardcoded.txt)

### Game Start
1. `sul_rgo_init` — populate `sul_rgo_map` (goods → building_type)
2. `sul_rgo_removal_start` — remove vanilla RGO buildings
3. `sul_initialize_all` — full specialization rebuild, stamp version on Bouvet Island
4. `sul_initialize_economy` — seed spending rates + budget pressure, run first economy update
5. `sul_war_on_game_start` — initialize war momentum for countries already at war

### Monthly Country Pulse
1. `sul_version_check` — detect mod update, trigger rebuild if needed
2. `sul_clear_market_cache` / `sul_refresh_market_cache` — invalidate + repopulate market cache
3. `sul_update_spending_rates` — recalculate 4 spending vars per country
4. `sul_player_wage_update` — accumulate + pay wages (player only)
6. `sul_ai_monthly_wage_payment` — pay previously accumulated wages (AI only)
7. `sul_war_init_pulse` — war system version check
8. `sul_war_monthly_pulse` — war momentum update (countries at war only)

### Yearly Country Pulse
- `sul_ai_yearly_wage_accumulate` — accumulate wages (AI only, paid next month)
- `sul_cleanup_dead_units` — remove dead unit references
- `sul_yearly_rgo_trim` — cap RGO levels

### Weather Monthly Pulse (every month, scopeless)
- `sul_batch_location_update` — WPP refresh for up to 333 stale AI locations

### On-Action Hooks
| Hook | Handler | Purpose |
|------|---------|---------|
| on_location_changed_rank | `sul_on_rank_changed` | Rebuild spec + trim RGO |
| on_raw_material_changed | `sul_on_raw_material_changed` | Swap RGO + validate spec |
| on_location_changed_owner | `sul_on_location_changed_owner` | Seed RGO for new colonies |
| on_location_changed_owner | `sul_war_on_auto_conquest` | Tag auto-conquered locations |
| on_annex | `sul_war_on_annex` | Clean capital modifier + tags |
| on_capital_moved | `sul_war_on_capital_moved` | Strip old capital modifier |
| on_ending_war | `sul_war_on_war_end_cleanup` | Clean auto-conquest tags |
| in_battle | `sul_war_in_battle_action` | Frontage penalty per tick |
| on_battle_won/lost_character | `sul_war_battle_cleanup_action` | Clear cached battle vars |

---

## 1. Specialization Core

### Location Variables
| Variable | Set By | Updated | Read By | Purpose |
|----------|--------|---------|---------|---------|
| `sul_spec_type` | `sul_assign_specialization_by_resources` | on_raw_material_changed, rank change | triggers, effects, GUI | Type: 1=mining, 2=farming, 3=gathering, 4=woodland, 5=commercial |
| `sul_designation` | `sul_update_designation` | after spec change | GUI | Combined type+rank encoding for tooltip display |
| `sul_can_mine` | `sul_calculate_specialization_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |
| `sul_can_farm` | `sul_calculate_specialization_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |
| `sul_can_gather` | `sul_calculate_specialization_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |
| `sul_can_woodland` | `sul_calculate_specialization_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |

### Country Variables
| Variable | Set By | Updated | Read By | Purpose |
|----------|--------|---------|---------|---------|
| `sul_mining_count` | `sul_initialize_specialization_counts` | on spec change | diversity pressure | Per-spec location count |
| `sul_farming_count` | (same) | (same) | (same) | (same) |
| `sul_woodland_count` | (same) | (same) | (same) | (same) |
| `sul_gathering_count` | (same) | (same) | (same) | (same) |
| `sul_commercial_count` | (same) | (same) | (same) | (same) |
| `sul_total_weighted` | (same) | (same) | (same) | Weighted count (farming=2x) |

### Location Modifiers (15 total: 5 specs x 3 ranks)
Pattern: `sul_{spec}_{rank}_specialization` where spec = mining/farming/gathering/woodland/commercial, rank = rural/town/city.
Applied by `sul_apply_specialization_modifier`, removed by `sul_clear_all_specialization_modifiers`.

| Modifier | Scope | Purpose |
|----------|-------|---------|
| `sul_recently_respecialized` | location | 5-year cooldown after spec change. Applied by generic_actions + missions. Removed on raw material change. |

### Init-Only Variables (location scope, 1-day expiry)
Set by `sul_set_init_production_variables` during game start. Gate building validation before modifiers load. All auto-expire.

**Mining:** `sul_allows_tools_production`, `sul_allows_weapons_production`, `sul_allows_cannon_production`, `sul_allows_firearms_production`, `sul_allows_jewelry_production`, `sul_allows_steel_production`

**Farming:** `sul_allows_beer_production`, `sul_allows_wine_production`, `sul_allows_liquor_production`, `sul_allows_leather_production`

**Gathering:** `sul_allows_glass_production`, `sul_allows_pottery_production`, `sul_allows_porcelain_production`, `sul_allows_saltpeter_production`, `sul_allows_apothecary_production`

**Woodland:** `sul_allows_furniture_production`, `sul_allows_paper_production`, `sul_allows_lacquerware_production`, `sul_allows_dye_production`, `sul_allows_charcoal_production`, `sul_allows_leather_production` (shared with farming), `sul_allows_incense_production`

**Commercial:** `sul_allows_printing_production`, `sul_allows_cloth_production`, `sul_allows_fine_cloth_production`, `sul_allows_naval_supplies_production`, `sul_allows_commerce_buildings`

---

## 2. Market Cache

### Global Variable Maps (keyed by market)
| Map | Set By | Updated | Read By | Purpose |
|-----|--------|---------|---------|---------|
| `sul_iron_pressure` | `sul_update_market_cache` | monthly cache refresh | spec eligibility | Iron market pressure |
| `sul_mining_finished_composite` | (same) | (same) | spec eligibility | Mining output demand/supply ratio |
| `sul_farming_finished_composite` | (same) | (same) | spec eligibility | Farming output demand/supply ratio |
| `sul_woodland_finished_composite` | (same) | (same) | spec eligibility | Woodland output demand/supply ratio |
| `sul_gathering_finished_composite` | (same) | (same) | spec eligibility | Gathering output demand/supply ratio |
| `sul_commercial_finished_composite` | (same) | (same) | spec eligibility | Commercial output demand/supply ratio |
| `sul_trade_spread` | `sul_do_refresh_market_cache` | monthly cache refresh | commercial spec gating | Price deviation across all goods in market |

### Global Flags
| Variable | Set By | Cleared By | Purpose |
|----------|--------|------------|---------|
| `sul_market_demand_cached` | `sul_do_refresh_market_cache` | `sul_clear_market_cache` (monthly) | Cache validity flag |
| `sul_cache_month` | `sul_clear_market_cache` | (overwritten monthly) | Current month for expiry detection |

---

## 3. RGO System

### Global Variable Maps
| Map | Set By | Read By | Purpose |
|-----|--------|---------|---------|
| `sul_rgo_map` | `sul_init_rgo_map` (game start) | RGO construction/destruction, on_raw_material_changed | goods → building_type mapping |
| `sul_goods_to_spec_type` | `sul_setup_goods_spec_map` (game start) | spec assignment | goods → spec type (1-5) |

### Location Variables
| Variable | Set By | Updated | Read By | Purpose |
|----------|--------|---------|---------|---------|
| `sul_rgo_building_type` | `sul_on_location_changed_owner`, RGO init | on_raw_material_changed | building construction/destruction | Cached building_type for this location's RGO |
| `sul_rgo_constructing` | RGO construction callbacks | on_construction_ended (-1) | construction tracking | Levels under construction |
| `sul_prior_building_levels` | `sul_save_building_levels` | on spec change | building redistribution | Saved levels before destruction |

### Distribution Counters (location scope, temporary during `sul_distribute_*_buildings`)
| Variable | Purpose |
|----------|---------|
| `sul_dist_budget` | Remaining building levels to distribute |
| `sul_dist_cap` | Per-building level cap (from rural_building_cap) |
| `sul_guild_cap` | Guild building max level cap |
| `sul_c0`..`sul_c4` | Per-building counters during mining distribution (stone, bog_iron, smelters, iron_mine, marble) |
| `sul_g0`..`sul_g3` | Per-guild counters during guild building distribution |

Set and consumed within a single `sul_distribute_*_buildings` call. Not persistent.

---

## 4. Economy / GDP / Wages

### Location Variables (refreshed by `sul_update_location_wpp`)
| Variable | Updated | Read By | Purpose |
|----------|---------|---------|---------|
| `sul_local_wages` | weather_monthly_pulse (AI batch) | wage accumulation, tooltips | Population x wage rates x market_access |
| `sul_total_weighted` | (same) | WPP denominator | Weighted estate power sum |
| `sul_local_gdp` | (same) | WPP base, tooltips | tax_base/control + wages |
| `sul_enfranchisement` | (same) | noble/commoner WPP split | Peasant enfranchisement (0.1-1.0) |
| `sul_wealth_per_pop` | (same) | `sul_read_wpp`, pop_demands | Variable map: pop_type → WPP |
| `sul_last_update` | (same) | batch scheduling | Year of last WPP update |

### Country Variables — Spending Rates (monthly refresh)
| Variable | Init | Updated By | Read By | Formula |
|----------|------|------------|---------|---------|
| `sul_spending_nobles` | `sul_initialize_economy` | `sul_update_spending_rates` | WPP, wage payment | 1 - enrichment - 0.30, clamped 0-1 |
| `sul_spending_clergy` | (same) | (same) | (same) | 1 - enrichment - 0.25 |
| `sul_spending_burghers` | (same) | (same) | (same) | 1 - enrichment - 0.20 |
| `sul_spending_commoners` | (same) | (same) | (same) | 1 - enrichment - 0.10 |

All 4 are always set together. Guard: `has_variable = sul_spending_nobles`

### Country Variables — Budget Pressure (monthly, post-WPP)
| Variable | Init | Updated By | Read By | Formula |
|----------|------|------------|---------|---------|
| `sul_budget_pressure_nobles` | seeded to 1 | `sul_compute_budget_pressure` | `sul_demand_*` script values | max(1, 1 + (estate_gold - 1000) x 0.00025) |
| `sul_budget_pressure_clergy` | (same) | (same) | (same) | (same) |
| `sul_budget_pressure_burghers` | (same) | (same) | (same) | (same) |
| `sul_budget_pressure_peasants` | (same) | (same) | (same) | (same) |

### Country Variables — Accumulated Wages (monthly player / yearly AI)
| Variable | Set By | Read By | Purpose |
|----------|--------|---------|---------|
| `sul_monthly_wages_nobles` | `sul_accumulate_wages` / `sul_update_country_economy` | `sul_pay_estate_wages` | Noble estate payment |
| `sul_monthly_wages_clergy` | (same) | (same) | Clergy estate payment |
| `sul_monthly_wages_burghers` | (same) | (same) | Burgher estate payment |
| `sul_monthly_wages_peasants` | (same) | (same) | Peasant estate payment |
| `sul_monthly_wages_dhimmi` | (same, always 0) | (same) | Placeholder |
| `sul_monthly_wages_cossacks` | (same, always 0) | (same) | Placeholder |
| `sul_monthly_wages_tribes` | (same, always 0) | (same) | Placeholder |

### Economy Data Flow
```
pop counts + wage rates → sul_local_wages (per location)
                        → sul_total_weighted
tax_base + wages        → sul_local_gdp
gdp / weighted          → WPP base → per-estate WPP → sul_wealth_per_pop map
                                                     → sul_demand_* script values → pop_demands
estate gold             → sul_budget_pressure_* → demand multiplier
location wages          → sul_accumulate_wages → sul_monthly_wages_* → sul_pay_estate_wages → estate gold
```

---

## 5. Version / Init

| Variable | Scope | Set By | Purpose |
|----------|-------|--------|---------|
| `sul_version` | location (Bouvet Island) | `sul_initialize_all` | Specialization system version stamp |
| `sul_rebuilding` | global | `sul_version_check` | Guard: prevent concurrent rebuilds |
| `sul_active` | location (Bouvet Island) | `sul_initialize_all` | Modifier marker for mod detection |
| `sul_init_pop_rush` | country modifier | `sul_initialize_all` | 45-day modifier accelerating pop promotion on game start |

### Capital Relocation (event sul.1, four_yearly_country_pulse)
| Variable | Scope | Type | Purpose |
|----------|-------|------|---------|
| `sul_candidate_list` | country | variable list | Candidate capital locations for AI relocation |
| `sul_capital_score` | location | persistent | Scoring value for capital selection |
| `sul_capital_cooldown` | country | persistent | Cooldown preventing repeated relocation attempts |
| `sul_rank` | country | persistent | Rank counter for proximity scoring |
| `sul_current_capital` | temporary scope | scoped | Saved reference to current capital |
| `sul_add_loc` | temporary scope | scoped | Location being evaluated for candidacy |

### Demand Tier Maps (global variable maps, keyed by goods)
| Map | Set By | Purpose |
|-----|--------|---------|
| `sul_da_necessity` | `sul_init_demand_maps` (game start) | Demand add values: necessity tier |
| `sul_da_basic` | (same) | Demand add values: basic tier |
| `sul_da_common` | (same) | Demand add values: common tier |
| `sul_da_upper` | (same) | Demand add values: upper tier |
| `sul_da_luxury` | (same) | Demand add values: luxury tier |
| `sul_da_exotic` | (same) | Demand add values: exotic tier |

Initialized via `add_to_global_variable_map` in `sul_init_effects.txt` (~119 entries across all tiers). Read by `sul_demand_*` script values. Silenced in event sul.99.

### Mission Modifiers (country scope, applied by sul_missions.txt)
| Modifier | Purpose |
|----------|---------|
| `consolidated_trade_modifier` | Trade consolidation mission reward |
| `parliament_favor_merchants_modifier` | Burgher privileges mission reward |
| `mission_economy_growth` | Economy growth mission reward |
| `mission_specialist_cities` | Specialist cities mission reward |
| `mission_trade_domination` | Trade domination mission reward |

These use vanilla modifier names applied by custom mission trees.

---

## 6. War Momentum

### Country Variables — Persistent
| Variable | Set By | Updated | Read By | Purpose |
|----------|--------|---------|---------|---------|
| `sul_war_potential_peak` | `sul_war_update_peaks` | monthly (ratchet up) | army calc, exhaustion, GUI | Peak military strength during war |
| `sul_war_army_peak` | (same) | (same) | display | Peak army component |
| `sul_war_manpower_peak` | (same) | (same) | display | Peak manpower (capped at 4x regulars) |
| `sul_war_momentum_army_size` | `sul_war_calculate_army_penalty` | monthly | modifier scaling, GUI | Strength loss ratio 0-1 |
| `sul_war_was_auto_conquered` | `sul_war_on_auto_conquest` | on location capture | occupation counting | Flag: lost territory to auto-conquer |

### Location Variables
| Variable | Set By | Cleared By | Purpose |
|----------|--------|------------|---------|
| `sul_war_original_owner` | `sul_war_on_auto_conquest` | `sul_war_on_war_end_cleanup` | Who owned this location before auto-conquest |

### Country Modifiers (applied with size parameter, days=-1)
| Modifier | Effect | Scaled By |
|----------|--------|-----------|
| `sul_war_momentum_army` | -0.5 global_defensive | `sul_war_momentum_army_size` |
| `sul_war_momentum_army_exhaustion` | +0.5 monthly_war_exhaustion | exhaustion ratio |
| `sul_war_momentum_diplomatic_pressure` | +1.0 monthly_war_exhaustion | pressure ratio |
| `sul_war_momentum_occupation` | -0.5 global_defensive, +0.4 monthly_war_exhaustion | occupation ratio |
| `sul_war_momentum_capital_fallen` | -0.25 global_defensive | flat (1.0) |

### Location Modifiers
| Modifier | Effect | Purpose |
|----------|--------|---------|
| `sul_war_momentum_capital` | +0.25 local_defensive | Capital resilience offset |

### Variable Maps (GUI display, keyed by country scope)
All populated monthly, read by `aaa_sul_war_topbar_tooltips.gui`.

| Map | Set By | Purpose |
|-----|--------|---------|
| `sul_war_army_breakdown` | `sul_war_display_army_components` | Total effective strength (current) per country |
| `sul_war_army_peak_breakdown` | (same) | Total effective strength (peak) per country |
| `sul_war_army_strength_map` | (same) | Army component current (x1000) per country |
| `sul_war_army_strength_peak_map` | (same) | Army component peak (x1000) per country |
| `sul_war_manpower_map` | (same) | Manpower raw uncapped (x1000) per country |
| `sul_war_manpower_peak_map` | (same) | Manpower capped peak (x1000) per country |
| `sul_war_army_we_map` | `sul_war_display_army_losses` | Army's WE contribution per country |
| `sul_war_army_fort_def_map` | (same) | Army's fort defense contribution per country |
| `sul_war_manpower_we_map` | (same) | Manpower's WE contribution per country |
| `sul_war_manpower_fort_def_map` | (same) | Manpower's fort defense contribution per country |
| `sul_war_pressure_map` | `sul_war_update_pressure` | Pressure contribution per participant (raw) |
| `sul_war_pressure_visible_map` | (same) | Pressure contribution per participant (x10M for display) |

**Overlord display maps** (populated for subjects with overlords in war):
| Map | Set By | Purpose |
|-----|--------|---------|
| `sul_war_overlord_breakdown` | `sul_war_display_army_components` | Overlord total strength per country |
| `sul_war_overlord_strength_map` | (same) | Overlord army component (x1000) per country |
| `sul_war_overlord_strength_peak_map` | (same) | Overlord army peak (x1000) per country |
| `sul_war_overlord_manpower_map` | (same) | Overlord manpower (x1000) per country |

**Pressure contribution maps** (per-participant, on war leader scope):
| Map | Set By | Purpose |
|-----|--------|---------|
| `sul_war_sub_pressure_contribution` | `sul_war_update_pressure` | Subject pressure contribution per country |
| `sul_war_coal_pressure_contribution` | (same) | Coalition member pressure contribution per country |

### Display Variables (country scope)
All populated monthly, read only by GUI tooltip.

**Occupation:**
- `sul_war_display_occupied_forts` / `sul_war_display_total_forts`
- `sul_war_display_occupied_unfortified_locations` / `sul_war_display_total_unfortified_locations`
- `sul_war_display_occupation_fort_defense` / `sul_war_display_occupation_war_exhaustion`
- `sul_war_display_occupied_forts_fort_defense` / `sul_war_display_occupied_forts_war_exhaustion`
- `sul_war_display_occupied_locations_fort_defense` / `sul_war_display_occupied_locations_war_exhaustion`

**Civil War:**
- `sul_war_display_civil_war_penalty`
- `sul_war_display_civil_war_crown_forts` / `sul_war_display_civil_war_crown_locs`
- `sul_war_display_civil_war_pretender_forts` / `sul_war_display_civil_war_pretender_locs`
- `sul_war_display_civil_war_total_forts` / `sul_war_display_civil_war_total_locs`
- `sul_war_display_civil_war_is_rebel` (0=crown, 1=pretender)
- `sul_war_display_civil_war_forts_fort_defense` / `sul_war_display_civil_war_forts_war_exhaustion`
- `sul_war_display_civil_war_locs_fort_defense` / `sul_war_display_civil_war_locs_war_exhaustion`

**Other:**
- `sul_war_display_capital_resilience`
- `sul_war_display_has_pressure` (flag: show pressure section)
- `sul_war_display_pressure` (total pressure value)

### Version
| Variable | Scope | Purpose |
|----------|-------|---------|
| `sul_war_version` | location (Bouvet Island) | War system version stamp |
| `sul_war_active` | location (Bouvet Island) | Modifier marker for mod detection |
| `sul_war_rebuilding` | global | Guard: prevent concurrent rebuilds |

---

## 7. Combat Overcrowding

### Character Variables (supreme commander)
| Variable | Set By | Cleared By | Purpose |
|----------|--------|------------|---------|
| `sul_war_in_battle` | `sul_war_calculate_frontage_penalty` | `sul_war_battle_cleanup_action` | Active battle flag |
| `sul_war_prev_atk` | (same) | (same) | Cached attacker frontage (optimization) |
| `sul_war_prev_def` | (same) | (same) | Cached defender frontage (optimization) |

### Unit Modifier
| Modifier | Effect | Duration |
|----------|--------|----------|
| `sul_war_frontage_penalty` | -0.8 infantry, -0.65 cavalry, -0.25 artillery, -0.8 auxiliary | 5 days (auto-refresh per tick) |

Applied to larger side only. Size = `1 - (smaller x age_mult / larger)`, clamped to 0.

---

## Constants (@macros, file-scoped)

### Economy (sul_gdp_update.txt + sul_on_actions.txt)
- Wage rates: `@sul_wage_nobles=5.0`, `@sul_wage_clergy=2.0`, `@sul_wage_burghers=1.0`, `@sul_wage_soldiers=0.5`, `@sul_wage_laborers=0.25`, `@sul_wage_peasants=0.05`
- Power weights: `@sul_power_weight_nobles=100`, `@sul_power_weight_clergy=25`, `@sul_power_weight_burghers=20`
- Enrichment offsets: `@sul_enrichment_offset_nobles=0.30`, clergy=0.25, burghers=0.20, commoners=0.10
- Enfranchisement bounds: min=0.1, max=1.0
- Demand tiers: necessity=0, basic=0.05, common=0.12, upper=0.25, luxury=0.5, exotic=1.5

### Specialization (sul_effects.txt)
- Type IDs: `@sul_mining_type=1`, farming=2, gathering=3, woodland=4, commercial=5
- Rank offsets: town=0, city=10, rural=20
- `@sul_farming_weight=2`

### War Momentum (sul_war_on_actions.txt)
- `@sul_war_version=201`

### Batching
- `@sul_ai_batch_size=333` — locations per weather_monthly_pulse tick
