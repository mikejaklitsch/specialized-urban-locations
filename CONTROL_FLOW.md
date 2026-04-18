# SUL Mod — Variable & Data Flow Reference

Authoritative map of every persistent variable, variable map, modifier, and global flag.
Organized by subsystem. **Update this document when adding, removing, or renaming any variable.**

---

## Execution Order (sul_hardcoded.txt)

### Game Start
1. `sul_rgo_init` — populate `sul_rgo_map` (goods → building_type)
2. `sul_rgo_removal_start` — remove vanilla RGO buildings
3. `sul_initialize_all` — full specialization rebuild, set `sul_version` global variable
4. `sul_initialize_economy` — seed spending rates + budget pressure, run first economy update
5. `sul_war_on_game_start` — initialize war momentum for countries already at war

### Monthly Country Pulse
1. `sul_clear_market_cache` / `sul_refresh_market_cache` — invalidate + repopulate market cache
2. `sul_update_spending_rates` — recalculate 4 spending vars per country
3. `sul_player_wage_update` — accumulate + pay wages (player only)
4. `sul_ai_monthly_wage_payment` — pay previously accumulated wages (AI only)
5. `sul_trade_maintenance_apply_action` — convert summed efficiency to merchant_maintenance_cost
6. `sul_minting_monthly_update` — minting price cache, debasement, AI minting modifiers
7. `sul_war_monthly_pulse` — war momentum update (countries at war only)
8. `sul_projection_monthly_update` — recompute subject-strength drag, decay conquest debt
9. `sul_epbm_player_monthly` / `sul_epbm_ai_monthly_charge` — EPBM maintenance charging

### Yearly Country Pulse
- `sul_ai_yearly_wage_accumulate` — accumulate wages (AI only, paid next month)
- `sul_cleanup_dead_units` — remove dead unit references
- `sul_yearly_rgo_trim` — cap RGO levels
- `sul_minting_yearly_update` — AI minting price cache + minting modifier refresh
- `sul_epbm_ai_yearly_recalc` / `sul_epbm_decade_rebuild` — EPBM AI recalc + safety rebuild

### Weather Monthly Pulse (every month, scopeless)
All version checks live here because the pulse fires once globally (no per-country race, so no reentrance guard needed). Each check compares a `sul_X_version` global variable against its matching `sul_X_version_value` script_value (defined in `main_menu/common/script_values/sul_versions.txt`) and re-runs full init on mismatch.
- `sul_passthrough_pulse` — per-market stockpile-driven temp demand pass
- `sul_batch_location_update` — WPP refresh for up to 333 stale AI locations
- `sul_version_check` — specialization system version gate
- `sul_war_init_pulse` — war system version gate
- `sul_minting_version_check` — minting system version gate
- `sul_integration_init_check` — integration system version gate
- `sul_epbm_version_check` — EPBM version gate
- `sul_integration_monthly_update` — refresh capacity bonus on tracked conquered locations, drain remove queue
- `sul_epbm_monthly_cache_clear` — clear PM cost caches globally

### On-Action Hooks
| Hook | Handler | Purpose |
|------|---------|---------|
| on_location_changed_rank | `sul_on_rank_changed` | Rebuild spec + trim RGO |
| on_raw_material_changed | `sul_on_raw_material_changed` | Swap RGO + validate spec |
| on_location_changed_owner | `sul_on_location_changed_owner` | Seed RGO for new colonies |
| on_location_changed_owner | `sul_war_on_auto_conquest` | Tag auto-conquered locations |
| on_location_changed_owner | `sul_integration_on_location_conquered` | Track + apply capacity bonus on new conquered locations |
| on_location_changed_owner | `sul_projection_on_location_conquered` | Increment conquest debt on the winner, weighted by location development |
| on_annex | `sul_war_on_annex` | Clean capital modifier + tags |
| on_capital_moved | `sul_war_on_capital_moved` | Strip old capital modifier |
| on_ending_war | `sul_war_on_war_end_cleanup` | Clean auto-conquest tags |
| in_battle | `sul_war_in_battle_action` | Frontage penalty per tick |
| on_battle_won/lost_character | `sul_war_battle_cleanup_action` | Clear cached battle vars |
| on_policy_changed | `sul_minting_on_policy_changed` | Rebuild minting goods list when currency law changes |

---

## 1. Specialization Core

### Location Variables
| Variable | Set By | Updated | Read By | Purpose |
|----------|--------|---------|---------|---------|
| `sul_spec_type` | `sul_specialization_assign_by_resources` | on_raw_material_changed, rank change | triggers, effects, GUI | Type: 1=mining, 2=farming, 3=gathering, 4=woodland, 5=commercial |
| `sul_designation` | `sul_specialization_update_designation` | after spec change | GUI | Combined type+rank encoding for tooltip display |
| `sul_can_mine` | `sul_specialization_calculate_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |
| `sul_can_farm` | `sul_specialization_calculate_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |
| `sul_can_gather` | `sul_specialization_calculate_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |
| `sul_can_woodland` | `sul_specialization_calculate_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |

### Country Variables
| Variable | Set By | Updated | Read By | Purpose |
|----------|--------|---------|---------|---------|
| `sul_mining_count` | `sul_specialization_count_initialize` | on spec change | diversity pressure | Per-spec location count |
| `sul_farming_count` | (same) | (same) | (same) | (same) |
| `sul_woodland_count` | (same) | (same) | (same) | (same) |
| `sul_gathering_count` | (same) | (same) | (same) | (same) |
| `sul_commercial_count` | (same) | (same) | (same) | (same) |
| `sul_total_weighted` | (same) | (same) | (same) | Weighted count (farming=2x) |

### Location Modifiers (15 total: 5 specs x 3 ranks)
Pattern: `sul_{spec}_{rank}_specialization` where spec = mining/farming/gathering/woodland/commercial, rank = rural/town/city.
Applied by `sul_specialization_apply_modifier`, removed by `sul_specialization_clear_all_modifiers`.

| Modifier | Scope | Purpose |
|----------|-------|---------|
| `sul_recently_respecialized` | location | 5-year cooldown after spec change. Applied by generic_actions + missions. Removed on raw material change. |

### Init-Only Variables (location scope, 1-day expiry)
Set by `sul_specialization_set_init_production_variables` during game start. Gate building validation before modifiers load. All auto-expire.

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
| `sul_iron_pressure` | `sul_market_cache_update` | monthly cache refresh | spec eligibility | Iron market pressure |
| `sul_mining_finished_composite` | (same) | (same) | spec eligibility | Mining output demand/supply ratio |
| `sul_farming_finished_composite` | (same) | (same) | spec eligibility | Farming output demand/supply ratio |
| `sul_woodland_finished_composite` | (same) | (same) | spec eligibility | Woodland output demand/supply ratio |
| `sul_gathering_finished_composite` | (same) | (same) | spec eligibility | Gathering output demand/supply ratio |
| `sul_commercial_finished_composite` | (same) | (same) | spec eligibility | Commercial output demand/supply ratio |
| `sul_trade_spread` | `sul_market_cache_refresh_all` | monthly cache refresh | commercial spec gating | Price deviation across all goods in market |

### Global Flags
| Variable | Set By | Cleared By | Purpose |
|----------|--------|------------|---------|
| `sul_market_demand_cached` | `sul_market_cache_refresh_all` | `sul_clear_market_cache` (monthly) | Cache validity flag |
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
| `sul_rgo_building_type` | `sul_on_location_changed_owner`, RGO init | on_raw_material_changed | building construction/destruction, `sul_location_rgo_building_level` script value | Cached building_type for this location's RGO |
| `sul_rgo_constructing` | RGO construction callbacks | on_construction_ended (-1) | construction tracking | Levels under construction |
| `sul_prior_building_levels` | `sul_specialization_save_building_levels` | on spec change | building redistribution | Saved levels before destruction |

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
| `sul_monthly_wages_nobles` | `sul_accumulate_wages` / `sul_update_country_economy` | `sul_estate_wages_pay_all` | Noble estate payment |
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
location wages          → sul_accumulate_wages → sul_monthly_wages_* → sul_estate_wages_pay_all → estate gold
```

---

## 5. Version / Init

All subsystems use the same pattern: a `sul_X_version` **global variable** (integer, saved in save file) is compared against a matching `sul_X_version_value` **script_value** (defined in `main_menu/common/script_values/sul_versions.txt` — single source of truth). On mismatch, the version check fires on `weather_monthly_pulse` and triggers a full re-init of that subsystem only. Weather pulse is scopeless and global, so no reentrance guard is needed.

Bump **only** the subsystem's value you're changing — other subsystems keep their saved state and skip re-init. Each integer is independent.

| Global Variable | Script Value (in sul_versions.txt) | Set By |
|-----------------|------------------------------------|--------|
| `sul_version` | `sul_specialization_version_value` | `sul_initialize_all` |
| `sul_war_version` | `sul_war_version_value` | `sul_war_init` |
| `sul_minting_version` | `sul_minting_version_value` | `sul_minting_initialize_all` |
| `sul_integration_version` | `sul_integration_version_value` | `sul_integration_initialize` |
| `sul_epbm_version` | `sul_epbm_version_value` | `sul_epbm_initialize_all` |
| `sul_init_pop_rush` | — (country modifier, 45 days, pop promotion on game start) | `sul_initialize_all` |

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
See the unified version-stamp table in section 5. War uses `sul_war_version` (global variable) paired with `sul_war_version_value` (script_value).

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

## 8. Passthrough / Middleman Trading

Stockpile-driven price-crush mechanism adapted from `yosiu_market_stockpiles`
workshop mod, compressed via `$GOOD$` argument substitution. **Stateless** —
no persistent variables, variable maps, or location flags. All state is read
live from `stockpile_in_market`, `goods_supply_in_market`, and the
`maximum_stockpile_capacity` location modifier.

### Execution
- `sul_passthrough_pulse` (on_action, monthly_country_pulse, `has_markets = yes` trigger)
  → `sul_passthrough_apply` (every_market_center_in_country)
  → bulk-removes 75 `sul_<good>_stockpile` + 75 `sul_<good>_oversupply` temp demands
  → calls `sul_passthrough_per_good = { GOOD = <name> }` 75 times (parse-time expansion)

`sul_passthrough_per_good` checks `sul_passthrough_fill_ratio` against tier
thresholds (5% / 50% / 75% / 95%) and applies the appropriate temp demand.
Above 5% fill: piecewise linear ramp via `sul_passthrough_supply_effect`,
plus paired `_oversupply` (cancels warehouse output). Below 4.9% fill on
relevant goods: small reverse demand + `add_goods_supply` drip to keep
depleted hubs visible to trade routing.

### Files
| Path | Purpose |
|---|---|
| `goods_demand/sul_passthrough_demands.txt` | 150 templates (75 `_stockpile`, 75 `_oversupply`), one pair per good |
| `building_types/sul_warehouse_buildings.txt` | 75 fake `sul_<good>_warehouse` buildings (`free_building_levels = 1`, self-cancelling production method) |
| `auto_modifiers/sul_passthrough_modifiers.txt` | INJECT `produced_in_market_bonus = -0.2` into `country_base_values` to cancel vanilla local-producer discount |
| `generic_actions/sul_destroy_market.txt` | REPLACE vanilla `destroy_market` with the `has_temporary_demands = no` check removed |
| `script_values/sul_passthrough_warehouse_values.txt` | `sul_passthrough_local_capacity`, `_fill_ratio`, `_upper_value`, `_lower_value`, `_upper_overflow`, `_supply_effect`, `_warehouse_correction`, `_low_supply_effect`, `_low_stockpile_effect`, `_1cutoff`, `_2cutoff`, `_3cutoff` |
| `scripted_effects/sul_passthrough_pulse.txt` | `sul_passthrough_apply`, `sul_passthrough_per_good` |
| `on_action/sul_passthrough_on_actions.txt` | `sul_passthrough_pulse` handler |
| `on_action/sul_hardcoded.txt` | `sul_passthrough_pulse` registered in `monthly_country_pulse` |

### Defines tuned for passthrough (`loading_screen/common/defines/sul_food_defines.txt`)
- `MARKET_MIN_STOCKPILE_TO_ALLOW_EXTRA_TRADE = 0.0`, `MARKET_STOCKPILE_PERCENTAGE_FOR_EXTRA_TRADE = 0.20` — vanilla extra-trade-supply mechanism always-on at 20%
- `TRADE_IMPACT_ON_SUPPLY/DEMAND_SCALE = 1.0`, `BURGHER_TRADE_IMPACT_ON_SUPPLY/DEMAND_SCALE = 1.0` — trade counts at full weight on both sides
- `SUPPLY_AND_DEMAND_STABILITY_OFFSET_CONSTANT = 0.02` — hyper-volatile prices (workshop mod's value)
- `MONTHLY_PRICE_CHANGE = 0.2` — prices converge to target 4× faster than vanilla
- `ADJUST_TRADE_ROUTE_CHANCE = 0.25` — AI trade route changes more conservative
- `POP_MISSING_GOODS_UTILITY_FACTOR = 0.5` — AI strongly prioritizes filling pop shortages

---

## 9. Trade Maintenance Efficiency

Reframes vanilla `merchant_maintenance_cost` (linear additive cost) as
`sul_trade_maintenance_efficiency` (multiplicatively compounding bonus).
Every vanilla source is overridden via INJECT to cancel its
`merchant_maintenance_cost = X` and re-emit it as
`sul_trade_maintenance_efficiency = -X`. Each month the engine-summed
efficiency total `E` is read and converted to the actual cost via
`final_cost = 1 / (1 + E) - 1`, then applied through one of two carrier
modifiers (only one of which is ever active at a time).

### Custom Modifier
| Modifier | Category | Notes |
|---|---|---|
| `sul_trade_maintenance_efficiency` | country (percent) | Engine sums every source. Read via `modifier:sul_trade_maintenance_efficiency`. |

### Country Variables
| Variable | Set By | Lifetime | Purpose |
|---|---|---|---|
| `sul_trade_maintenance_efficiency_total` | `sul_trade_maintenance_apply` | monthly | Clamped (`min = -0.99`) snapshot of engine sum, fed into the formula |

### Carrier Static Modifiers (`main_menu/common/static_modifiers/sul_modifiers.txt`)
| Modifier | Effect | Applied When |
|---|---|---|
| `sul_trade_maintenance_reduction` | `merchant_maintenance_cost = -1.0` | `E > 0` (cost reduction); size = `E / (1 + E)` |
| `sul_trade_maintenance_penalty` | `merchant_maintenance_cost = +1.0` | `E < 0` (cost increase); size = `1 / (1 + E) - 1` |

`add_country_modifier`'s `size` parameter only takes positive values, so
the sign of the result picks which carrier to apply.

### Files
| Path | Purpose |
|---|---|
| `main_menu/common/modifier_type_definitions/sul_modifier_types.txt` | Defines `sul_trade_maintenance_efficiency` modifier type |
| `main_menu/common/modifier_icons/sul_modifier_icons.txt` | Reuses vanilla `merchant_maintenance_cost.dds` icon |
| `main_menu/localization/english/sul_modifier_types_l_english.yml` | `MODIFIER_TYPE_NAME_sul_trade_maintenance_efficiency` |
| `main_menu/common/static_modifiers/sul_modifiers.txt` | Carrier modifiers + country/IO source overrides |
| `in_game/common/scripted_effects/sul_trade_maintenance.txt` | `sul_trade_maintenance_apply` |
| `in_game/common/on_action/sul_on_actions.txt` | `sul_trade_maintenance_apply_action` (monthly trigger wrapper) |
| `in_game/common/on_action/sul_hardcoded.txt` | Wires the action into `monthly_country_pulse` |
| `in_game/common/advances/sul_advances.txt` | 15 advance overrides |
| `in_game/common/religions/sul_religion_overrides.txt` | 53 folk asian religion overrides |
| `in_game/common/government_reforms/sul_reform_adjustments.txt` | 5 reform overrides |
| `in_game/common/societal_values/sul_societal_value_adjustments.txt` | `mercantilism_vs_free_trade` left-modifier override |
| `in_game/common/estate_privileges/sul_estate_privilege_adjustments.txt` | `novgorod_ivans_hundred` override |
| `in_game/common/age/sul_age_efficiency.txt` | `age_4_reformation` unique-block override |
| `in_game/common/parliament_issues/sul_parliament_overrides.txt` | `expand_our_market` debate override |
| `in_game/common/subject_types/sul_subject_type_overrides.txt` | `hanseatic_member` subject_modifier override |

---

## 10. Population-Based Integration

Conquered locations integrate faster when they're below population capacity
and slower when they're over it. Originally the standalone "Population Based
Integration" mod, integrated under the `sul_integration_` prefix.

### Quadratic Capacity Bonus
A scripted location modifier `sul_integration_capacity_bonus` is applied to
each tracked conquered location with `size = 2.5 × (1 - pop/cap)²`. The
modifier value is `local_integration_speed_modifier = 1.0`, so size *is* the
applied integration speed bonus. Result:
- 0% filled → +250%
- 50% filled → +63%
- 100% filled → 0% (modifier removed)

### Diplomatic Reputation Bonus
`sul_integration_diplo_rep_annexation` is an auto_modifier that grants
`annexation_speed_base = 1.0` scaled with `modifier:diplomatic_reputation`,
so +1 flat annexation speed per 10 displayed diplomatic reputation.

### Tracked-list Pattern
Rather than iterating every owned location each month, the system tracks
conquered locations in a global list `sul_integration_conquered_locations`.
`sul_integration_on_location_conquered` adds entries on
`on_location_changed_owner`. The monthly update walks the list, refreshes
the bonus on still-conquered entries, and queues for removal anything that
has advanced past `integration_level = conquered`. A second pass drains the
removal queue (avoids mutating the list during iteration).

### Files
| Path | Purpose |
|---|---|
| `main_menu/common/static_modifiers/sul_integration_location.txt` | `sul_integration_capacity_bonus` static modifier |
| `in_game/common/auto_modifiers/sul_integration_country.txt` | `sul_integration_diplo_rep_annexation` |
| `in_game/common/scripted_effects/sul_integration_effects.txt` | `sul_integration_apply_capacity_bonus`, `_track_location`, `_initialize` |
| `in_game/common/on_action/sul_integration_on_actions.txt` | `_on_game_start`, `_init_check`, `_on_location_conquered`, `_monthly_update` |
| `main_menu/localization/english/sul_integration_l_english.yml` | Modifier loc |

### Version Check
`sul_integration_version` is a **global variable** set to the `sul_integration_version_value` script_value on init.
`sul_integration_init_check` runs on `weather_monthly_pulse`, compares the stored value against the script_value, and re-runs `sul_integration_initialize` on mismatch.
Bumping `sul_integration_version_value` in `main_menu/common/script_values/sul_versions.txt` forces a full re-init on existing saves.

---

## 11. Minting / Gold Standard

Replaces vanilla minting with a price-based profitability system.
Originally "The Gold Standard" mod, integrated under the `sul_minting_`
prefix. Names that were already `tgs_minting_X` end up as
`sul_minting_X` from the mechanical prefix swap — that doubling is
intentional and grep-safe.

### Core Concept
Vanilla minting pays a flat 25 ducats per unit of demanded goods regardless
of actual market price. This system computes a per-country
`sul_minting_efficiency` (E) such that `25 × (1 + E)` equals the actual
profit per coin set, then applies E via `minting_income_factor` modifiers.
Coin sets that cost more on the market than they're worth as coins produce
negative income; rare/cheap goods produce windfall.

### Subsystems
- **Liquidity** — `sul_minting_liquidity` modifier (replaces vanilla
  `minting_income_factor` everywhere it appeared) tracks the face value
  premium of coins above raw metal content. Sourced from coin laws,
  advances, religious aspects, estate privileges, government reforms.
- **Debasement** — Player and AI can debase coinage (variable
  `sul_minting_debasement_level`, range 0–2.0), stretching bullion across
  more coins for extra income at the cost of monthly inflation.
- **Rebasement** — Negative debasement: crown buys impure coins 1-for-1
  with fresh ones to reduce inflation, costing gold scaled by tax base.
- **Minting Goods List** — `sul_minting_goods` variable list, kept
  in sync with the active currency law's `*_used_for_minting` modifiers
  via `sul_minting_rebuild_minting_goods` on init and `on_policy_changed`.
- **Price Cache** — Market prices for the active minting goods are cached
  on the market center location each month (player) or year (AI) to avoid
  recomputing 70 per-good price lookups every tick.

### Player/AI Split
Auto modifiers (`scales_with`) drive the player display because they
recompute live every frame. AI countries receive equivalent effects via
direct `add_country_modifier` + `change_country_modifier_size` calls in
`sul_minting_monthly_update` to keep the AI cost down to one tick per
month.

### AI Debasement
`sul_minting_ai_set_debasement` (generic action, runs every 6 months)
computes a target debasement level from monthly balance, num_loans, and
current inflation, then sets `sul_minting_debasement_level` or
`sul_minting_rebasement_level` accordingly.

### Files (28 total)
| Path | Purpose |
|---|---|
| `main_menu/common/modifier_type_definitions/sul_minting_modifier_types.txt` | `sul_minting_liquidity` modifier type |
| `main_menu/common/modifier_icons/sul_minting_modifier_icons.txt` | Icon mapping |
| `main_menu/common/static_modifiers/sul_minting_modifiers.txt` | `_ai_minting`, `_ai_inflation`, `_ai_rebasement` |
| `main_menu/common/static_modifiers/sul_minting_vanilla_injects.txt` | INJECTs into vanilla static modifiers (franc coinage, novgorodka, etc.) to swap minting_income_factor → sul_minting_liquidity |
| `main_menu/common/game_concepts/sul_minting_game_concepts.txt` | Game concept aliases for tooltip text |
| `main_menu/gui/sul_minting_messagetypes.txt` | AI debasement message hidden from player |
| `main_menu/localization/english/sul_minting_l_english.yml` | All TGS loc keys |
| `in_game/common/script_values/sul_minting_efficiency.txt` | E formula, market cost, total income, AI modifier sizes |
| `in_game/common/script_values/sul_minting_debasement.txt` | Debasement/rebasement formulas, AI target |
| `in_game/common/scripted_effects/sul_minting_effects.txt` | `_initialize_country`, `_rebuild_minting_goods`, `_cache_market_center`, `_update_price_cache` |
| `in_game/common/scripted_triggers/sul_minting_triggers.txt` | `sul_minting_is_active_country` |
| `in_game/common/scripted_guis/sul_minting_debasement.txt` | Debasement panel button effects |
| `in_game/common/on_action/sul_minting_on_actions.txt` | `_initialize_all`, `_on_policy_changed`, `_version_check`, `_monthly_update`, `_yearly_update` |
| `in_game/common/auto_modifiers/sul_minting_country.txt` | Player auto modifiers (E → minting income, inflation scaling, debasement, rebasement) |
| `in_game/common/auto_modifiers/sul_minting_base_values.txt` | INJECT `country_base_values` with baseline `sul_minting_liquidity = 0.5` |
| `in_game/common/advances/sul_minting_advances.txt` | Vanilla advance INJECTs (banking_advance, photduang, mint_of_the_gulf, etc.) |
| `in_game/common/laws/sul_minting_coin_laws.txt` | REPLACE `coin_laws` (full vanilla copy with `tgs_minting_liquidity` swaps) |
| `in_game/common/laws/sul_minting_country_laws.txt` | REPLACE `kor_currency`, `six_ministries` |
| `in_game/common/laws/sul_minting_precious_metals.txt` | REPLACE `precious_metal_distribution_law` |
| `in_game/common/government_reforms/sul_minting_reforms.txt` | REPLACE `control_of_the_mahdali_coinage_reform` |
| `in_game/common/estate_privileges/sul_minting_burghers.txt` | REPLACE `control_over_the_coinage`, `fra_marcel_*`, `bra_kreditwerk` |
| `in_game/common/religious_aspects/sul_minting_aspects.txt` | REPLACE `usury_allowed` |
| `in_game/common/building_types/sul_minting_buildings.txt` | INJECTs into `wisselbank`, `usa_national_bank`, `usa_national_mint` |
| `in_game/common/generic_actions/sul_minting_debasement.txt` | AI debasement action |
| `in_game/common/generic_action_ai_lists/sul_minting_debasement_list.txt` | AI list registration |
| `in_game/gui/economy_lateralview.gui` | Full vanilla replacement (mint income panel + debasement breakdown) |
| `in_game/gui/z_sul_minting_debasement_panel.gui` | Debasement adjustment panel |
| `in_game/gui/shared/z_sul_minting_economy_tooltips.gui` | Tooltip windows for mint profitability/coinage value/etc. |

### Engine Hook Bug Fix
TGS originally registered its version-check on `monthly_weather_pulse`,
which doesn't exist in EU5 (the real action is `weather_monthly_pulse`).
This was silently a no-op in the source mod. The integrated version moves
`sul_minting_version_check` to the correct `weather_monthly_pulse` block
in `sul_hardcoded.txt`.

---

## 12. Power Projection + Complacency

PP is the central slowdown lever for conquest and integration; complacency
is its long-run counterweight. The two are coupled both ways so sustained
high PP breeds complacency, and complacency in turn drags PP back down.

### Scale Layer (`sul_power_projection_impact`)

One auto_modifier scales_with `power_projection` and holds every effect
proportional to current PP — benefits, complacency coupling, and the PP
cost package. Defined fresh (not INJECT on vanilla) because INJECTing into
vanilla's `power_projection` block hits a self-referential name collision.

| Modifier | Coefficient (per PP) | Category |
|---|---|---|
| `global_pop_assimilation_speed_modifier` | +0.005 | benefit |
| `global_pop_conversion_speed_modifier` | +0.005 | benefit |
| `global_war_score_cost` | -0.003 | benefit |
| `global_distance_from_capital_speed_propagation` | +0.005 | benefit |
| `subject_loyalty` | +0.5 | benefit |
| `diplomatic_annexation_cost` | -0.003 | benefit |
| `antagonism_taking_land_giving_modifier` | -0.005 | benefit |
| `levy_recovery_modifier` | +0.02 | benefit |
| `global_levy_size_modifier` | +0.0025 | benefit |
| `monthly_complacency` | +0.0015 | **coupling** (negative PP drains complacency) |
| `stability_decay` | +0.001 | **PP cost** (mobilization strains the state) |
| `global_estate_target_satisfaction` | -0.001 | **PP cost** (estates resent projection) |
| `trade_efficiency` | -0.0005 | **PP cost** (commercial friction) |
| `global_urban_build_buildings_cost` | +0.002 | **PP cost** (bureaucratic overhead) |
| `global_migration_speed_modifier` | -0.001 | **PP cost** (migration outflow) |

Coefficients are placeholders pending playtest.

### Gate Layer

REPLACE on `enforce_culture` and `enforce_religion` country interactions.
Vanilla bodies reproduced verbatim with one extra trigger appended to
`select_trigger.enabled`: `scope:actor.power_projection >= power_projection`.
Action is visible but disabled until the overlord out-projects the subject.

### Structural Drag Layer

Nine auto_modifiers write PP from country state. Each scales off a signed
script_value so the coefficient stays positive on the auto_modifier side.

| Auto modifier | Source script_value | Coefficient | Effect |
|---|---|---|---|
| `sul_projection_drag_control` | `sul_projection_control_drag` | 25 | -25 PP at zero control |
| `sul_projection_drag_culture` | `sul_projection_culture_drag` | 25 | -25 PP at zero accepted-culture pop |
| `sul_projection_drag_religion` | `sul_projection_religion_drag` | 25 | -25 PP at zero same-religion pop (captures heretics and heathens together) |
| `sul_projection_drag_stability` | `sul_projection_stability_drag` | 0.1 | ±10 PP at stability ±100 |
| `sul_projection_drag_subjects` | `sul_projection_subject_drag` | 50 | -50 PP per multiple of overlord strength in weighted subjects. Linear, no cap. |
| `sul_projection_drag_size` | `sul_projection_size_drag` | -0.05 | -1 PP per 20 locations (coefficient flips the positive location count to negative PP) |
| `sul_projection_rank` | `sul_projection_rank_value` | 1 | +5 duchy / +10 kingdom / +15 empire |
| `sul_projection_army` | `sul_projection_regular_army_ratio` | 10 | +10 PP per multiple of expected regular army (excludes levies) |
| `sul_projection_navy` | `navy_size_percentage` | 10 | +10 PP per multiple of expected navy (vanilla script_value) |

Control/culture/religion/stability/size drags compute inline in the
script_value — no country variables, no monthly maintenance. Subject drag
requires iteration and so caches a variable.

### Complacency Coupling

Two-way feedback. PP builds complacency via the scale layer above;
complacency drags PP back via `INJECT:complacency_impact`. Vanilla's
`scales_with = complacency × 0.01` applies to every entry we inject.

**Complacency → PP** (in `INJECT:complacency_impact`)
- `power_projection = -200` → -2 PP per complacency point

**Vanilla complacency_impact extensions** (same INJECT)

Positives (comfortable-empire wellbeing):
| Modifier | Coefficient | Effect at complacency 100 |
|---|---|---|
| `global_estate_satisfaction_recovery` | 0.005 | +0.5 estate recovery |
| `global_migration_speed_modifier` | 0.003 | +0.3 migration |
| `cultural_tradition_modifier` | 0.005 | +0.5 cultural tradition |
| `monthly_prestige` | 0.005 | +0.5 prestige/month |
| `global_monthly_development` | 0.003 | +0.3 dev/month |

Negatives (state-as-instrument atrophy):
| Modifier | Coefficient | Effect at complacency 100 |
|---|---|---|
| `global_institution_growth_modifier` | -0.5 | -50% |
| `global_manpower_modifier` | -0.3 | -30% |
| `global_sailors_modifier` | -0.3 | -30% |
| `levy_recovery_modifier` | -0.3 | -30% |
| `land_morale_modifier` | -0.15 | -15% |
| `naval_morale_modifier` | -0.15 | -15% |
| `discipline` | -0.10 | -10% |
| `global_urban_build_buildings_cost` | 0.002 | +0.2 |
| `global_rural_build_buildings_cost` | 0.002 | +0.2 |
| `settle_country_cost_modifier` | 0.005 | +0.5 |
| `casus_belli_creation_speed_modifier` | -0.5 | -50% |
| `court_spending_cost` | 0.003 | +0.3 |
| `diplomatic_capacity` | -2.0 | -2 slots |
| `global_pop_assimilation_speed_modifier` | -0.003 | -0.3 |
| `global_pop_conversion_speed_modifier` | -0.003 | -0.3 |
| `global_integration_speed_modifier` | -0.003 | -0.3 |
| `add_accepted_culture_cost_modifier` | 1.0 | +100% |
| `declaring_war_cost_modifier` | 1.0 | +100% |

**War Exhaustion → complacency** (in `INJECT:war_exhaustion_impact`)
- `monthly_complacency = -0.01` per WE point. At WE=20 drains 0.2/month,
  matching vanilla `recovery_motivation`.

### Top-bar GUI

`in_game/gui/hud_topbar.gui` is a full vanilla copy with two `stat_player`
blocks inserted between `stat_prestige` and `stat_diplo`:
- `stat_complacency` — `Country.GetCurrencyValue('complacency')` + delta row
  using `GetModifierValue('monthly_complacency')`; reuses vanilla
  `ComplacencyResourceTooltip`.
- `stat_power_projection` — `Country.GetPowerProjection|1` (no currency-API
  delta getter available); reuses vanilla `power_projection_tooltip`.

Patch fragility: copying 2495 lines of vanilla means a Paradox edit to
`hud_topbar.gui` breaks us silently. On patch days, grep for
`stat_complacency` / `stat_power_projection` and re-apply the inserts on
top of fresh vanilla.

### Country Variables
| Variable | Set By | Updated | Read By | Purpose |
|---|---|---|---|---|
| `sul_projection_subject_drag_value` | `sul_projection_recompute_subject_drag` | on_game_start + monthly_country_pulse | `sul_projection_subject_drag` script_value | Signed load: `-sum(subject_strength × type_weight) / max(1, overlord_strength)`, clamped to min -6. Negative-weight types (marches) can make this positive. |
| `sul_projection_weight_map` | `sul_projection_recompute_subject_drag` | monthly_country_pulse | GUI tooltip | Variable map: subject_scope → type weight. Display only. |
| `sul_projection_contribution_map` | `sul_projection_recompute_subject_drag` | monthly_country_pulse | GUI tooltip | Variable map: subject_scope → PP contribution per subject. Display only. |

### Effects (sul_projection_effects.txt)
| Effect | Purpose |
|---|---|
| `sul_projection_recompute_subject_drag` | Sums `country_strength × sul_projection_subject_type_weight` across subjects, divides by overlord `country_strength` (min 1), negates, clamps to min -6. Also populates `sul_projection_weight_map` and `sul_projection_contribution_map` for tooltip display. |

### Script Values (sul_projection_values.txt)
| Script value | Purpose |
|---|---|
| `sul_projection_control_drag` | `(total_control_scaled_population / total_population) - 1` |
| `sul_projection_culture_drag` | `(total_accepted_culture_population / total_population) - 1` |
| `sul_projection_religion_drag` | `religion_percentage_in_country(root.religion) - 1` |
| `sul_projection_stability_drag` | `stability` |
| `sul_projection_size_drag` | `num_locations` |
| `sul_projection_regular_army_ratio` | `regular_army_size / max(1, expected_army_size)` |
| `sul_projection_rank_value` | 5 duchy / 10 kingdom / 15 empire |
| `sul_projection_subject_type_weight` | Per-subject-type scalar. Tuned per type: tributary 0.1, colonial 0.25, dominion 0.5, fiefdom/uc_bey/tusi 0.75, vassal/conquistador/hanseatic 1.0, appanage 1.25, march -0.25 (adds PP), secessionist/state_bank/trade_company 0.25, samanta 1.0. |
| `sul_projection_subject_drag` | Safe wrapper around `var:sul_projection_subject_drag_value` (0 when variable missing). |

### On-Action Handlers (sul_projection_on_actions.txt)
| Handler | Hook | Purpose |
|---|---|---|
| `sul_projection_on_game_start` | on_game_start | Seed `sul_projection_subject_drag_value` on every country so the scale layer reads a real value on tick one. |
| `sul_projection_monthly_update` | monthly_country_pulse | Refresh subject drag variable. |

### Files
| Path | Purpose |
|---|---|
| `in_game/common/auto_modifiers/sul_projection_country.txt` | Unified scale layer + 9 structural drag auto_modifiers |
| `in_game/common/auto_modifiers/sul_complacency_country.txt` | `INJECT:complacency_impact` — PP drag + wellbeing/atrophy package |
| `in_game/common/auto_modifiers/sul_war_auto_modifiers.txt` | `INJECT:war_exhaustion_impact` — stability decay + complacency drain |
| `in_game/common/script_values/sul_projection_values.txt` | Drag formulas, rank/army ratios, subject type weights |
| `in_game/common/scripted_effects/sul_projection_effects.txt` | Subject drag monthly recompute |
| `in_game/common/on_action/sul_projection_on_actions.txt` | Game start + monthly handlers |
| `in_game/common/country_interactions/sul_projection_subject_gates.txt` | REPLACE `enforce_culture` / `enforce_religion` with PP gate |
| `in_game/gui/hud_topbar.gui` | Full vanilla override adding `stat_complacency` + `stat_power_projection` |
| `in_game/gui/shared/aaa_sul_power_projection_tooltip.gui` | Override vanilla PP tooltip with scrollable subject breakdown |
| `main_menu/localization/english/sul_projection_l_english.yml` | `AUTO_MODIFIER_NAME_*` strings, tooltip labels |

### Known Gaps
- **Subject type weights** — tuned but may need further balancing.
- **All scale/drag/impact coefficients are placeholders** pending playtest.
- **Engagement channels, DoE reframe, Forced Opening disaster** — deferred.
  See `docs/complacency_coupling_plan.md` for design context.

---

## Constants (@macros, file-scoped)

### Economy (sul_gdp_update.txt + sul_on_actions.txt)
- Wage rates: `@sul_wage_nobles=5.0`, `@sul_wage_clergy=2.0`, `@sul_wage_burghers=1.0`, `@sul_wage_soldiers=0.5`, `@sul_wage_laborers=0.25`, `@sul_wage_peasants=0.05`
- Power weights: `@sul_power_weight_nobles=100`, `@sul_power_weight_clergy=25`, `@sul_power_weight_burghers=20`
- Enrichment offsets: `@sul_enrichment_offset_nobles=0.30`, clergy=0.25, burghers=0.20, commoners=0.10
- Enfranchisement bounds: min=0.1, max=1.0
- Demand tiers: necessity=0, basic=0.05, common=0.12, upper=0.25, luxury=0.5, exotic=1.5

### Specialization (sul_specialization.txt)
- Type IDs: `@sul_mining_type=1`, farming=2, gathering=3, woodland=4, commercial=5
- Rank offsets: town=0, city=10, rural=20
- `@sul_farming_weight=2`


### Batching
- `@sul_ai_batch_size=333` — locations per weather_monthly_pulse tick
