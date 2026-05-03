# SUL Mod — Variable & Data Flow Reference

Authoritative map of every persistent variable, variable map, modifier, and global flag.
Organized by subsystem. **Update this document when adding, removing, or renaming any variable.**

---

## Execution Order (sul_hardcoded.txt)

### Game Start
1. `sul_rgo_init` — populate `sul_rgo_map` (goods → building_type)
2. `sul_rgo_removal_start` — remove vanilla RGO buildings
3. `sul_initialize_all` — full specialization rebuild, set `sul_version` global variable
4. `sul_initialize_economy` — seed budget pressure + GDP init + first economy update. Runs `sul_update_location_wpp` per location, but minority return_per_pop variables (`sul_dhimmi_return_per_pop`, `sul_cossacks_return_per_pop`) are left at 0 because wealth hasn't been seeded yet — step 7 bootstraps them.
5. `sul_war_on_game_start` — initialize war momentum for countries already at war
6. ... (other subsystem inits: integration, minting, EPBM, migration)
7. `sul_wealth_seed_all` — seed location wealth at equilibrium (last, so all gold-spending inits have finished). Also computes minority return_per_pop via `sul_compute_minority_returns` — the call in step 4's WPP pass produces 0 because wealth doesn't exist yet.

### Monthly Country Pulse
Sequential on_actions first, then parallelized events, then sequential EPBM/DWUI.

**Sequential (sul_hardcoded.txt):**
1. `sul_projection_monthly` — recompute subject-strength drag, decay conquest debt

**Parallel events (sul_parallel_on_actions.txt → sul_monthly_country_pulse):**
- `sul_economy.monthly` — wealth convergence + power accumulation + wage payment
- `sul_trade_maint.0` — convert summed efficiency to merchant_maintenance_cost
- `sul_minting_pulse.0` — minting price cache, debasement, AI minting modifiers
- `sul_war_pulse.0` — war momentum update (countries at war only)
- `sul_war_pulse.1` — war rebellions

**Sequential (after parallel):**
- `sul_epbm_player_monthly` — player EPBM collect
- `sul_epbm_ai_monthly_charge` — AI EPBM charge
- `sul_dwui_monthly_recalc` — unit composition recalc

### Yearly Country Pulse
Parallelized events, then sequential EPBM.

**Parallel events (sul_parallel_on_actions.txt → sul_yearly_country_pulse):**
- `sul_economy.yearly_wages` — recalculate location wage rates
- `sul_economy.yearly_gdp` — GDP + asset shares for capital returns
- `sul_rgo_pulse.0` — RGO trim
- `sul_rgo_pulse.1` — cleanup dead units
- `sul_minting_pulse.1` — AI minting price cache + minting modifier refresh

**Sequential (after parallel):**
- `sul_epbm_ai_yearly_recalc` — AI EPBM recalc
- `sul_epbm_decade_rebuild` — structural rebuild every 10 years

### Weather Monthly Pulse (every month, scopeless)
All version checks live here because the pulse fires once globally (no per-country race, so no reentrance guard needed). Each check compares a `sul_X_version` global variable against its matching `sul_X_version_value` script_value (defined in `main_menu/common/script_values/sul_versions.txt`) and re-runs full init on mismatch.
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

### Rank Modifiers (authoritative specialization identity)
Each custom location rank carries boolean modifiers in its `rank_modifier` block:
- `sul_mining_specialization = yes` — on all mining_city/town/rural ranks
- `sul_farming_specialization = yes` — on all farming ranks
- `sul_gathering_specialization = yes` — on all gathering ranks
- `sul_woodland_specialization = yes` — on all woodland ranks
- `sul_commercial_specialization = yes` — on all commercial ranks
- `sul_is_rural_settlement_rank_tier = yes` / `sul_is_town_rank_tier` / `sul_is_city_rank_tier` — tier identification

These are the authoritative source for specialization identity in script. `sul_spec_id` has been removed.

**Unreachable vanilla ranks:** `city`, `town`, and `rural_settlement` remain defined in 00_default.txt only to avoid major structural rewrites. No location ever holds these ranks — every location is assigned a specialization rank. Treat them as non-existent.

### Location Variables
| Variable | Set By | Updated | Read By | Purpose |
|----------|--------|---------|---------|---------|
| `sul_spec_type` | `sul_specialization_update_designation` | after rank change | GUI visibility checks | Derived from boolean rank modifiers. 1=mining, 2=farming, 3=gathering, 4=woodland, 5=commercial |
| `sul_can_mine` | `sul_specialization_calculate_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |
| `sul_can_farm` | `sul_specialization_calculate_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |
| `sul_can_gather` | `sul_specialization_calculate_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |
| `sul_can_woodland` | `sul_specialization_calculate_eligibility` | on_raw_material_changed, rank change | triggers | Eligibility flag |

**Removed:** `sul_designation` — replaced by `Location.GetRankIcon` (native engine call) for icon display.

### Country Variables
| Variable | Set By | Updated | Read By | Purpose |
|----------|--------|---------|---------|---------|
| `sul_mining_count` | `sul_specialization_count_initialize` | on spec change | diversity pressure | Per-spec location count |
| `sul_farming_count` | (same) | (same) | (same) | (same) |
| `sul_woodland_count` | (same) | (same) | (same) | (same) |
| `sul_gathering_count` | (same) | (same) | (same) | (same) |
| `sul_commercial_count` | (same) | (same) | (same) | (same) |
| `sul_total_weighted` | (same) | (same) | (same) | Weighted count (farming=2x) |

### Location Modifiers
| Modifier | Scope | Purpose |
|----------|-------|---------|
| `sul_recently_respecialized` | location | 5-year penalty after spec change, scaled by buildings destroyed. Applied by carrier building on_built + `sul_specialization_destroy_and_penalize`. Removed on raw material change. |

### Init-Only Variables (location scope, 1-day expiry)
Set by `sul_specialization_set_init_production_variables` during game start. Gate building validation before modifiers load. All auto-expire.

**Mining:** `sul_allows_tools_production`, `sul_allows_weapons_production`, `sul_allows_cannon_production`, `sul_allows_firearms_production`, `sul_allows_jewelry_production`, `sul_allows_steel_production`

**Farming:** `sul_allows_beer_production`, `sul_allows_wine_production`, `sul_allows_liquor_production`, `sul_allows_leather_production`

**Gathering:** `sul_allows_glass_production`, `sul_allows_pottery_production`, `sul_allows_porcelain_production`, `sul_allows_saltpeter_production`, `sul_allows_apothecary_production`

**Woodland:** `sul_allows_furniture_production`, `sul_allows_paper_production`, `sul_allows_lacquerware_production`, `sul_allows_dye_production`, `sul_allows_charcoal_production`, `sul_allows_leather_production` (shared with farming), `sul_allows_incense_production`

**Commercial:** `sul_allows_printing_production`, `sul_allows_cloth_production`, `sul_allows_fine_cloth_production`, `sul_allows_naval_supplies_production`, `sul_allows_commerce_buildings`

---

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

---

## 4. Economy / GDP / Wages

### Location Variables — WPP (refreshed by `sul_update_location_wpp`)
| Variable | Updated | Read By | Purpose |
|----------|---------|---------|---------|
| `sul_local_wages` | weather_monthly_pulse (AI batch) | wage accumulation, tooltips | Population x wage rates x market_access |
| `sul_local_gdp` | (same) | tooltips | Sum of WPP x pop counts per location |
| `sul_local_gdp_output` | yearly (sul_gdp_yearly_update) | national GDP computation | Location building profit proxy |
| `sul_wealth_per_pop` | monthly | `sul_read_wpp`, pop_demands | Variable map: pop_type → WPP |
| `sul_demand_base` | monthly | `sul_read_demand_base`, demand tiers | Variable map: pop_type → WPP/(A+B*WPP) |
| `sul_last_update` | monthly (AI batch) | batch scheduling | Year of last WPP update |

### Location Variable Maps — Estate Assets & Targets (sole storage)
`sul_estate_assets` and `sul_estate_targets` are the only persistent storage for per-location wealth. No intermediate variables — seed, convergence, occupation drain, and loot all read from and write directly to these maps using `cmf_change_variable_map` (CMF helper: remove key then add, because `add_to_variable_map` does not overwrite existing keys). Keyed by `estate_type`. Convergence uses local variables for intermediate math within a tick.

| Map | Key | Written By | Read By | Purpose |
|-----|-----|-----------|---------|---------|
| `sul_estate_assets` | `estate_type:nobles_estate` | seed, convergence, loot | `sul_map_asset_nobles`, WPP capital returns, GUI | Current noble wealth |
| | `estate_type:clergy_estate` | (same) | (same pattern) | Current clergy wealth |
| | `estate_type:burghers_estate` | (same) | (same) | Current burgher wealth |
| | `estate_type:peasants_estate` | (same) | (same) | Current peasant wealth |
| | `estate_type:crown_estate` | (same) | (same) | Current crown wealth |
| | `estate_type:dhimmi_estate` | (same, conditional) | (same) | Current dhimmi wealth |
| | `estate_type:cossacks_estate` | (same, conditional) | (same) | Current cossack wealth |
| | `estate_type:tribes_estate` | (same, conditional) | (same) | Current tribes wealth |
| `sul_estate_targets` | (same keys) | seed, convergence | `sul_map_target_*`, GUI tooltip | Convergence target per estate |

**Guard pattern:** Script values use `has_variable_map` + `is_key_in_variable_map` (short-circuits). Effects use `owner = { country_has_estate }` when the map is guaranteed to exist (inside convergence after seeding check).

### Location Variables — Minority Returns (set by `sul_compute_minority_returns`)
| Variable | Set By | Read By | Purpose |
|----------|--------|---------|---------|
| `sul_dhimmi_return_per_pop` | `sul_compute_minority_returns` | tooltip script values, demand WPP | Per-pop capital return for dhimmi minority pops |
| `sul_cossacks_return_per_pop` | (same) | (same) | Per-pop capital return for cossack minority pops |
| `sul_enrichment_dhimmi` | (same) | `sul_init_economy_full_pass` | Per-location dhimmi enrichment (accumulated → paid to estate) |
| `sul_enrichment_cossacks` | (same) | (same) | Per-location cossack enrichment |

### Country Variables — Budget Pressure (monthly, set by `sul_compute_budget_pressure`)
| Variable | Init | Updated By | Read By | Formula |
|----------|------|------------|---------|---------|
| `sul_budget_pressure_nobles` | seeded to 1 | `sul_compute_budget_pressure` | `sul_demand_*` script values | max(1, 1 + (estate_gold - 1000) x 0.00025) |
| `sul_budget_pressure_clergy` | (same) | (same) | (same) | (same) |
| `sul_budget_pressure_burghers` | (same) | (same) | (same) | (same) |
| `sul_budget_pressure_peasants` | (same) | (same) | (same) | (same) |
| `sul_country_pop_nobles` | seeded to 1 | `sul_converge_wealth_and_accumulate_power` | WPP per-pop division | Country-wide noble pop count |
| `sul_country_pop_clergy` | (same) | (same) | (same) | Country-wide clergy pop count |
| `sul_country_pop_burghers` | (same) | (same) | (same) | Country-wide burgher pop count |

### Country Variables — GDP (yearly)
| Variable | Init | Updated By | Read By | Formula |
|----------|------|------------|---------|---------|
| `sul_national_gdp` | sul_gdp_init | `sul_gdp_yearly_update` (yearly) | tooltips | Sum of all location building profits |

### Country Variables — Accumulated Wages (monthly player / yearly AI)
| Variable | Set By | Read By | Purpose |
|----------|--------|---------|---------|
| `sul_monthly_wages_nobles` | `sul_converge_wealth_and_accumulate_power` / `sul_init_economy_full_pass` | `sul_estate_wages_pay_all` | Noble estate payment |
| `sul_monthly_wages_clergy` | (same) | (same) | Clergy estate payment |
| `sul_monthly_wages_burghers` | (same) | (same) | Burgher estate payment |
| `sul_monthly_wages_peasants` | (same) | (same) | Peasant estate payment |
| `sul_monthly_wages_dhimmi` | (same, always 0) | (same) | Placeholder |
| `sul_monthly_wages_cossacks` | (same, always 0) | (same) | Placeholder |
| `sul_monthly_wages_tribes` | (same, always 0) | (same) | Placeholder |

### Country Variables — Location Wealth Accumulators (monthly player / yearly AI)
Accumulated by `sul_converge_wealth_and_accumulate_power` / `sul_init_economy_full_pass`. Raw power is summed from `local_estate_power` across all owned locations. `_prev` vars hold last month's totals for use as convergence denominators. Estate gold is a country-scope cache of the engine's complex `estate_gold` formula, cached AFTER enrichment payments.

| Variable | Set By | Read By | Purpose |
|----------|--------|---------|---------|
| `sul_national_power_nobles` | `sul_converge_wealth_and_accumulate_power` / `sul_init_economy_full_pass` | wealth convergence, debug panel | Sum of local_estate_power(nobles) across all locations |
| `sul_national_power_clergy` | (same) | (same) | Sum of local_estate_power(clergy) across all locations |
| `sul_national_power_burghers` | (same) | (same) | Sum of local_estate_power(burghers) across all locations |
| `sul_national_power_peasants` | (same) | (same) | Sum of local_estate_power(peasants) across all locations |
| `sul_national_power_dhimmi` | (same, conditional) | (same) | Sum of local_estate_power(dhimmi) — only if estate exists |
| `sul_national_power_cossacks` | (same, conditional) | (same) | Sum of local_estate_power(cossacks) — only if estate exists |
| `sul_national_power_tribes` | (same, conditional) | (same) | Sum of local_estate_power(tribes) — only if estate exists |
| `sul_national_power_crown` | (same, derived) | (same) | Sum of all estate power (all 7 estates) |
| `sul_national_power_prev_nobles` | saved before zeroing | `sul_converge_location_assets` | Last month's denominator for convergence fraction |
| `sul_national_power_prev_clergy` | (same) | (same) | (same) |
| `sul_national_power_prev_burghers` | (same) | (same) | (same) |
| `sul_national_power_prev_peasants` | (same) | (same) | (same) |
| `sul_national_power_prev_dhimmi` | (same) | (same) | (same) |
| `sul_national_power_prev_cossacks` | (same) | (same) | (same) |
| `sul_national_power_prev_tribes` | (same) | (same) | (same) |
| `sul_national_power_prev_crown` | (same) | (same) | (same) |
| `sul_estate_gold_nobles` | (same) | wealth convergence, debug panel | Cached estate_gold for nobles |
| `sul_estate_gold_clergy` | (same) | (same) | Cached estate_gold for clergy |
| `sul_estate_gold_burghers` | (same) | (same) | Cached estate_gold for burghers |
| `sul_estate_gold_peasants` | (same, null-safe) | (same) | Cached estate_gold for peasants |
| `sul_estate_gold_dhimmi` | (same, null-safe) | (same) | Cached estate_gold for dhimmi |
| `sul_estate_gold_cossacks` | (same, null-safe) | (same) | Cached estate_gold for cossacks |
| `sul_estate_gold_tribes` | (same, null-safe) | (same) | Cached estate_gold for tribes |
| `sul_enrich_rate_nobles` | `sul_converge_wealth_and_accumulate_power` / `sul_init_economy_full_pass` | enrichment formula | Cached (1 + estate_enrichment) × (1 + sul_nobles_enrichment_rate) |
| `sul_enrich_rate_clergy` | (same) | (same) | Same for clergy |
| `sul_enrich_rate_burghers` | (same) | (same) | Same for burghers |
| `sul_enrich_rate_commoners` | (same) | (same) | Same for commoners |
| `sul_enrich_rate_tribesmen` | (same) | (same) | Same for tribesmen |
| `sul_enrich_rate_dhimmi` | (same) | (same) | Same for dhimmi |
| `sul_enrich_rate_cossacks` | (same) | (same) | Same for cossacks |

### Estate Power Block Modifiers (`in_game/common/estates/sul_estates.txt`)
Each non-crown estate's `power = {}` block scales these modifiers linearly by estate_power (0–1). Combined non-crown estates at ~70% total power produce `food_purchase_cost = -0.70` and `building_upkeep_costs = -0.70`. Crown low_power/high_power blocks zero out vanilla's building_upkeep_costs so only per-estate power blocks contribute.

| Modifier | Value | Applied To | Purpose |
|----------|-------|-----------|---------|
| `food_purchase_cost` | -1.0 | nobles, clergy, burghers, peasants, tribes, dhimmi, cossacks | Estates subsidize food purchases proportional to power |
| `building_upkeep_costs` | -1.0 | (same 7 estates) | Estates cover building maintenance proportional to power |

All vanilla `food_purchase_cost` sources (advances, laws, parliament) have been cancelled and re-emitted as `sul_granary_max_levels`.

### Custom Modifier Types — Economy
Registered in `main_menu/common/modifier_type_definitions/sul_modifier_types.txt`. These are INJECT-able hooks — any advance, privilege, law, or static modifier can source them to modify the enrichment pipeline.

| Modifier | Category | Base Value | Purpose |
|----------|----------|------------|---------|
| `sul_nobles_enrichment_rate` | country (percent) | 0 | Per-estate enrichment multiplier. Cached as (1 + estate_enrichment) × (1 + rate) per country. INJECT via advances/privileges. |
| `sul_clergy_enrichment_rate` | country (percent) | 0 | Same for clergy |
| `sul_burghers_enrichment_rate` | country (percent) | 0 | Same for burghers |
| `sul_commoners_enrichment_rate` | country (percent) | 0 | Same for commoners (soldiers + laborers + peasants) |
| `sul_tribesmen_enrichment_rate` | country (percent) | 0 | Same for tribesmen |
| `sul_dhimmi_enrichment_rate` | country (percent) | 0 | Same for dhimmi |
| `sul_cossacks_enrichment_rate` | country (percent) | 0 | Same for cossacks |
| `sul_looting_efficiency` | country (percent) | 0 (unsourced) | Shifts loot split from destroyed toward kept. Higher = more gold to occupier. |
| `sul_granary_max_levels` | country (additive) | 0 | Extra building levels for granaries + rural granaries. Read by `sul_granary_max_level` and `sul_rural_granary_max_level` via `owner.modifier:sul_granary_max_levels`. Sourced from converted vanilla `food_purchase_cost` values (×10). |

### Economy Data Flow
```
YEARLY (sul_gdp_yearly_update):
  location_net_building_profit → sul_local_gdp_output → sul_national_gdp

MONTHLY (country-level, sul_compute_budget_pressure):
  estate_gold thresholds → sul_budget_pressure_*

MONTHLY (per-location, sul_update_location_wpp):
  Upper WPP = wage_pool × power_share / pops + assets × 2% / pops
  Commoner WPP = commoner_pool × bill_share / pops + peasant_assets × 2% / pops
  Tribesmen WPP = wage_pool × tribes_power_share / pops + tribes_assets × 2% / pops
  WPP → sul_wealth_per_pop map → sul_demand_* → pop_demands (tribesmen + slaves included)
  WPP → sul_demand_base map → demand tier formulas
  Enrichment = demand_base × WPP × 0.53 × cached_enrich_rate → paid to estates
  Minority returns: dhimmi/cossacks = assets × 2% × power_per_pop / local_power
  Minority enrichment: return_per_pop through demand formula × estimated_pops × enrich_rate

MONTHLY (sul_converge_wealth_and_accumulate_power — single every_owned_location loop):
  Cache enrichment rates: (1 + estate_enrichment) × (1 + per_estate_rate) per country
  Cache estate gold (after enrichment payments in init path)
  Convergence: assets drift toward (local_power / prev_national_power × estate_gold) at 2.5%/month
               occupied locations drain 2%/month instead
               hard cap: assets can never exceed target
  Accumulate:  local_estate_power per location → sul_*_estate_raw_power (all 7 estates + crown derived)
  Wages:       cached wage bills → sul_monthly_wages_* → sul_estate_wages_pay_all
               → estate gold → sul_estate_wage_transfer (enfranchisement-scaled)

ON_LOCATION_OCCUPIED (sul_wealth_loot_location):
  Extract 25% of all 8 estate assets. Conditional estates guarded by has_variable.
  Split: (1 - 50% + looting_efficiency) kept by controller.

INIT (sul_initialize_economy → sul_wealth_seed_all):
  sul_init_economy_full_pass → accumulate raw power + enrichment
    → pay enrichment to all 7 estates (dhimmi/cossacks conditional)
    → cache enrichment rates + estate gold after payments
    → sul_update_location_wpp → sul_compute_minority_returns: produces 0 (wealth doesn't exist yet)
  → sul_wealth_seed_location: assets = (local_power / national_power) × estate_gold
    → sul_compute_minority_returns: now produces real values (wealth just created)
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

### Linear Population Bonus
A scripted location modifier `sul_integration_capacity_bonus` is applied to
each tracked conquered location with population below 100 (i.e. 100,000 people).
`size = (100 - population) / 100`, clamped to 0–1. The modifier value is
`local_integration_speed_modifier = 1.0`, so size *is* the applied integration
speed bonus. Result:
- 0 pop → +100%
- 50k pop → +50%
- 100k+ pop → 0% (modifier removed)

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

### Architecture: Monthly Accumulator

Country-scope variable `var:sul_power_projection` (-100 to 100) replaces the
engine's `power_projection` as the authoritative PP value. All PP sources
write to the custom modifier type `monthly_sul_power_projection`. A monthly
scripted effect reads `modifier:monthly_sul_power_projection`, applies
percentage decay (base 5%, doubled at complacency 100), and writes the
result to `var:sul_power_projection`.

Every PP source feeds through one of two channels:
- `monthly_sul_power_projection` — growth/contribution
- Decay — percentage pull toward zero (complacency-scaled)

Auto_modifiers are reserved for dynamic ratios that have no native modifier
hook (control/pop, culture acceptance, religion, diplomacy). All other sources
(ranks, advances, reforms, static modifiers) apply `monthly_sul_power_projection`
directly through native game mechanisms (INJECT into rank_modifier, advance
modifier blocks, etc.).

### Vanilla Bridge (`sul_projection_vanilla_bridge`)

Separate auto_modifier that writes vanilla `power_projection = 1` scaled by
`var:sul_power_projection`. Keeps hardcoded engine systems (AI weighting,
war score, subject interactions) working. Split from `sul_power_projection_impact`
so vanilla PP never leaks into the player-facing effects tooltip.

Vanilla's `REPLACE:power_projection` auto_modifier is emptied (no effects).
Vanilla PP sources are cancelled via INJECTs (negative `power_projection`
values net to zero).

### Scale Layer (`sul_power_projection_impact`)

One auto_modifier scales_with `sul_power_projection_value` (reads
`var:sul_power_projection`) and holds every effect proportional to current PP.

| Modifier | Coefficient (per PP) | Category |
|---|---|---|
| `subject_loyalty` | +0.5 | benefit |
| `global_pop_assimilation_speed_modifier` | +0.01 | benefit |
| `global_pop_conversion_speed_modifier` | +0.01 | benefit |
| `global_distance_from_capital_speed_propagation` | +0.005 | benefit |
| `global_war_score_cost` | -0.005 | benefit |
| `diplomatic_annexation_cost` | -0.005 | benefit |
| `antagonism_taking_land_giving_modifier` | -0.01 | benefit |
| `sul_trade_maintenance_efficiency` | +0.0025 | benefit |
| `global_integration_speed_modifier` | +0.01 | benefit |
| `settle_country_cost_modifier` | -0.005 | benefit |
| `casus_belli_creation_speed_modifier` | +0.005 | benefit |
| `levy_recovery_modifier` | +0.02 | military |
| `global_levy_size_modifier` | +0.02 | military |
| `monthly_complacency` | +0.003 | **coupling** (negative PP drains complacency) |
| `stability_decay` | -0.0001 | **PP cost** |
| `global_estate_target_satisfaction` | -0.002 | **PP cost** |
| `global_estate_power` | -0.005 | **PP cost** |
| `aggressiveness_modifier` | +0.05 | AI behavior |
| `control_importance_modifier` | -0.05 | AI behavior |
| `gold_importance_modifier` | -0.05 | AI behavior |

### Gate Layer

REPLACE on `enforce_culture` and `enforce_religion` country interactions.
Vanilla bodies reproduced verbatim with one extra trigger appended to
`select_trigger.enabled`: `scope:actor.var:sul_power_projection >= var:sul_power_projection`.
Action is visible but disabled until the overlord out-projects the subject.

### Monthly Contribution Sources

All sources write to `monthly_sul_power_projection`. Organized by mechanism:

**Auto_modifiers (dynamic ratios, no native hook):**

| Auto modifier | Source script_value | Coefficient | Effect |
|---|---|---|---|
| `sul_projection_drag_control` | `sul_projection_control_drag` | 0.5 | -0.5/mo at zero control |
| `sul_projection_drag_culture` | `sul_projection_culture_drag` | 0.25 | -0.25/mo at zero accepted-culture pop |
| `sul_projection_drag_religion` | `sul_projection_religion_drag` | 0.2 | -0.2/mo at zero same-religion pop |
| `sul_projection_drag_diplomacy` | `sul_projection_diplo_usage_ratio` | -0.5 | -0.5/mo at full diplomatic overextension |

**Vanilla auto_modifier INJECTs (scaling engine values):**

| Vanilla auto_modifier | Coefficient | Notes |
|---|---|---|
| `stability_impact` | 0.1 | |
| `prestige` | 0.1 | |
| `num_locations_impact` | -0.001 | |
| `regular_army_size` | 0.005 | |
| `regular_navy_size` | 0.005 | |
| `num_advances_impact` | 0.01 | Also cancels vanilla `power_projection = -1` |

**Country rank INJECTs (in_game/common/country_ranks/):**

| Rank | Monthly PP |
|---|---|
| Duchy | 0.1 |
| Kingdom | 0.2 |
| Empire | 0.3 |

**Static modifier INJECTs (main_menu/common/static_modifiers/):**

| Source | Monthly PP | Tier |
|---|---|---|
| `is_subject` | -0.1 | minor |
| `ruler_mil` | 0.02 | per-point |
| `is_great_power` | 0.25 | major |
| `supremacy_over_rival_modifier` | 0.25 | major |
| `country_art` | 1.0 | scaling (×art share) |
| Vanilla 10PP sources (7 nation-specific) | 0.25 | major |
| Vanilla 5PP sources (5 nation-specific) | 0.1 | minor |

**Advance INJECTs:**

| Source | Monthly PP |
|---|---|
| `power_projection_advance_1` | 0.25 |
| `power_projection_advance_2` through `_6` | 0.1 each |

**Other sources:**

| Source | File | Monthly PP |
|---|---|---|
| `legacy_of_osman` reform | sul_reform_adjustments.txt | 0.5 |
| `french_centralized_monarchy` reform | sul_reform_adjustments.txt | 0.1 |
| `outward_vs_inward` societal value | sul_societal_value_adjustments.txt | 0.1 |
| `decline_of_majapahit` disaster | sul_projection_disaster_mirrors.txt | -0.25 |

### Complacency Coupling

Two-way feedback. PP builds complacency via the scale layer above;
complacency drags PP back via `INJECT:complacency_impact`. Vanilla's
`scales_with = complacency × 0.01` applies to every entry we inject.

**Complacency → PP** (in `REPLACE:complacency_impact`)
- `sul_power_projection = -100` → -1 PP per complacency point

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
- `stat_power_projection` — `Country.MakeScope.ScriptValue('sul_power_projection_display')|1`
  (reads custom modifier accumulator); reuses overridden `power_projection_tooltip`.

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
| `sul_projection_monthly_update` | Reads `modifier:monthly_sul_power_projection`, applies decay (5% base, scaled by complacency), writes to `var:sul_power_projection`. Clamps to -100/100. |
| `sul_projection_init_variable` | One-time init: sets `var:sul_power_projection = 0` if missing. |
| `sul_projection_recompute_subject_drag` | Sums `country_strength × sul_projection_subject_type_weight` across subjects, divides by overlord `country_strength` (min 1), negates, clamps to min -6. Also populates `sul_projection_weight_map` and `sul_projection_contribution_map` for tooltip display. |

### Script Values (sul_projection_values.txt)
| Script value | Purpose |
|---|---|
| `sul_projection_control_drag` | `(total_control_scaled_population / total_population) - 1` |
| `sul_projection_culture_drag` | `(total_accepted_culture_population / total_population) - 1` |
| `sul_projection_religion_drag` | `religion_percentage_in_country(root.religion) - 1` |
| `sul_projection_diplo_usage_ratio` | `used_diplomatic_capacity / total_diplomatic_capacity` (0–1) |
| `sul_power_projection_value` | Reads `var:sul_power_projection`. Used by scale layer and vanilla bridge. |
| `sul_power_projection_display` | GUI alias for `var:sul_power_projection`. |
| `sul_power_projection_monthly_delta` | Net monthly change (contributions + decay) for top bar delta display. |
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
| `main_menu/common/modifier_type_definitions/sul_modifier_types.txt` | Defines `sul_power_projection` custom modifier type |
| `in_game/common/auto_modifiers/sul_projection_country.txt` | Scale layer (`sul_power_projection_impact`) + 5 structural drag auto_modifiers + vanilla INJECT mirrors |
| `in_game/common/auto_modifiers/sul_complacency_country.txt` | `INJECT:complacency_impact` — PP drag + wellbeing/atrophy package |
| `in_game/common/auto_modifiers/sul_war_auto_modifiers.txt` | `INJECT:war_exhaustion_impact` — stability decay + complacency drain |
| `in_game/common/script_values/sul_projection_values.txt` | Drag formulas, rank/army ratios, subject type weights |
| `in_game/common/scripted_effects/sul_projection_effects.txt` | Subject drag monthly recompute |
| `in_game/common/on_action/sul_projection_on_actions.txt` | Game start + monthly handlers |
| `in_game/common/country_interactions/sul_projection_subject_gates.txt` | REPLACE `enforce_culture` / `enforce_religion` with PP gate |
| `in_game/gui/hud_topbar.gui` | Full vanilla override adding `stat_complacency` + `stat_power_projection` |
| `in_game/gui/shared/aaa_sul_power_projection_tooltip.gui` | Override vanilla PP tooltip with scrollable subject breakdown |
| `in_game/common/advances/sul_projection_advance_mirrors.txt` | Mirror 6 vanilla PP advances to `sul_power_projection` |
| `in_game/common/disasters/sul_projection_disaster_mirrors.txt` | Mirror vanilla disaster PP to `sul_power_projection` |
| `main_menu/common/static_modifiers/sul_projection_vanilla_injects.txt` | Custom PP sources + mirror 13 vanilla static modifier PP sources |
| `main_menu/localization/english/sul_projection_l_english.yml` | `MODIFIER_TYPE_NAME_*`, `AUTO_MODIFIER_NAME_*` strings, tooltip labels |

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
- Enrichment: `@sul_w_enrichment=0.53` weight, rates cached as `sul_enrich_rate_*` = (1 + estate_enrichment) × (1 + per_estate_rate)
- Wealth convergence: `@sul_wealth_converge_rate=0.025`, occupation drain `@sul_wealth_occupation_drain=0.02`, capital return `@sul_return_rate=0.02`
- Looting: `@sul_loot_extraction_rate=0.25`, destroyed `@sul_loot_destroyed_base=0.50`
- Enfranchisement bounds: min=0.1, max=1.0
- Demand tiers: necessity=0, basic=0.05, common=0.12, upper=0.25, luxury=0.5, exotic=1.5

### Specialization (sul_specialization.txt)
- Type IDs: `@sul_mining_type=1`, farming=2, gathering=3, woodland=4, commercial=5
- Rank offsets: town=0, city=10, rural=20
- `@sul_farming_weight=2`


### Batching
- `@sul_ai_batch_size=333` — locations per weather_monthly_pulse tick
