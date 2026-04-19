# Development Specialization: Design for SUL Integration

Development (0-100) as an extraction/production axis, driven primarily by what gets built at a location.

## Core Concept

- **Low development (toward 0)**: extraction economy. Raw material output, open land, primary sector.
- **High development (toward 100)**: production economy. Manufacturing, trade, capital formation.
- **Equilibrium at 50**: constant upward pressure + dev-scaled downward pressure = spring toward 50.
- **Extremes are hard to reach.** A location should only hit 0 or 100 in extreme cases -- roughly 250 buildings of the right type stacked in one direction.

### Relationship to SUL Specialization

- **Spec type** = WHAT (mining, farming, gathering, woodland, commercial)
- **Development level** = extraction vs production CHARACTER

A farming city at dev 25 is a breadbasket. The same farming city at dev 75 has breweries, wineries, and a tannery -- it processes agricultural output rather than just growing it. Rank doesn't determine this. A farming city can be deeply extractive or deeply productive depending on how it's been built up.

Specialization type does not directly influence development. Market centers get an injectable production push (see section 4), but spec modifiers themselves are agnostic to the dev axis.

### The Primary Lever: Buildings

Each building we already modify gets a `local_monthly_development` value in its existing INJECT/REPLACE block. No new INJECT blocks -- only buildings SUL already touches.

**Extraction buildings** push development DOWN (toward 0):
- All 53 RGO buildings (`sul_rgo_*`)
- Crop buildings (wheat field, rice paddy, fruit orchard, etc.)
- Mining/quarry buildings (stone quarry, bog iron smelter, iron mine, marble quarry)
- Gathering extraction (clay pit, salt collector, sand pit, sheep farms)
- Forestry (lumber mill, elephant hunting)
- Plantations (sugar, cotton, tobacco)
- Local smelters, mercury patio, sawmill, irrigation systems

**Production buildings** push development UP (toward 100):
- All guild buildings (tools, weapons, jewelry, brewery, winery, cloth, glass, pottery, furniture, paper, dyes, tannery, etc.)
- All workshop/manufactory/mill upgrades of guilds
- Rural processing buildings (rural blacksmith, rural brewer, rural carpenter, etc.)
- Commerce buildings (marketplace, merchants quarters, grand marketplace, commerce center)
- Printing/books chain (scriptorium, printing press, printing manufactory)
- Food processing (farmers market, windmill)
- Financial buildings (stock exchange, clearing house)
- Tar kiln, mason
- Trade infrastructure (entrepot, trading hub, customs house, port authority)

**Neutral buildings** (no development pressure):
- Military (armory, barracks, training fields)
- Warehouses (passthrough system)
- Granaries (food infrastructure)
- University
- Minting buildings
- Village buildings (farming village, fishing village, mining village, forest village, market village)

### The Math

The equilibrium spring: base upward B = +0.05/mo, dev scaler D = -0.001/dev. Equilibrium at dev 50 with zero building pressure.

Each building level contributes a small directional push. To reach dev 100 from equilibrium requires overcoming 50 dev-points of downward pressure:
- At dev 100: net spring force = +0.05 - 0.001 x 100 = -0.05/mo
- 250 production buildings must provide +0.05/mo to hold equilibrium at 100
- Per production building: **+0.0002/mo** to development
- Per extraction building: **-0.0002/mo** to development

A location with 50 production buildings and 0 extraction: equilibrium shifts to dev 60.
A location with 100 extraction and 20 production: equilibrium shifts to ~34.
A location with 250 production and 0 extraction: equilibrium at 100.

### Implementation

Add `local_monthly_development = 0.0002` (or `-0.0002`) to each building's existing INJECT or REPLACE block in SUL's building_types files. Only buildings we already modify get touched. Stateless, zero runtime overhead.

---

## 1. Core Equilibrium

Two forces:

```
TRY_INJECT:location_base_values = {
    local_monthly_development = 0.05           # constant upward push
}

TRY_INJECT:development = {
    local_monthly_development = -0.001         # per-dev downward push (equilibrium at 50)
}
```

No other engine scalers. Building pressure is directional per-building, not uniform per-level.

---

## 2. Prosperity and Devastation

Prosperity and devastation control the RATE of development change, not the direction.

```
TRY_INJECT:prosperity = {
    local_monthly_development_modifier = 0.25      # +25% dev change speed at full prosperity
}

TRY_INJECT:devastation = {
    local_monthly_development_modifier = -1.0      # -100% dev change speed at full devastation
}
```

The percentage modifier amplifies or dampens whatever direction development is already moving. It cannot push directionally -- it multiplies the net monthly delta, which can be positive or negative. Asymmetric: full devastation freezes development entirely.

- Prosperity = economic dynamism. The location adapts to its building mix faster.
- Devastation = economic paralysis. The location is stuck, resistant to change.

---

## 3. Geography: Development Change Speed

Geography modulates how quickly a location responds to its building mix. Harsh or remote terrain slows all development change (in either direction). Buildings are the only directional force.

### Vegetation

| Type | Vanilla % | Our % | Rationale |
|------|-----------|-------|-----------|
| Farmland | +0.10 | **+0.05** | Minimum positive. Open land adapts easily. |
| Woods | -0.20 | **-0.10** | Minimum negative. Light cover, clearable. |
| Forest | -0.25 | **-0.25** | Average. Clearable but takes effort, timber while you cut. |
| Desert | -0.33 | **-0.35** | Between average and large. No water/timber/soil, but flat and open. |
| Jungle | -0.30 | **-0.50** | Large. Dense canopy, regrows when cleared, fights you physically. |

### Topography

| Type | Vanilla % | Our % | Rationale |
|------|-----------|-------|-----------|
| Mountains | -0.50 | **-0.75** | Very large. Physical barrier to everything. |
| Wetlands | -0.30 | **-0.50** | Large. Drainable but expensive, same tier as jungle. |
| Hills | -0.25 | **-0.10** | Minimum. Many historical hill cities. |
| Plateau | -0.10 | **-0.10** | Minimum. Elevated but buildable. |

### Climate

| Type | Vanilla % | Our % | Rationale |
|------|-----------|-------|-----------|
| Arctic | -0.25 | **-0.90** | Max. Extreme cold shuts down nearly all activity. |
| Tropical | -0.10 | **-0.10** | Minimum. Disease and heat slow things, but major tropical cities exist. |

### What Geography Does

Geography says "this location is harder to change." A mountain mining location takes longer to shift toward production if you build guilds there. A farmland location adapts quickly in either direction. Geography does NOT push toward extraction or production -- only buildings do that.

---

## 4. Market Centers

Market centers get a permanent production push equivalent to 25 building levels:

```
TRY_INJECT:market_center = {
    local_monthly_development = 0.005         # 25 x 0.0002 = 0.005
}
```

Shifts the equilibrium for market centers to ~55 with no other forces. A farming market center trends urban; a mining market center becomes a processing hub. Not tied to spec type.

---

## 5. Location Size

Calculated once on game start. Larger locations are harder to change (open land resists concentration in either direction). Smaller locations adapt faster.

**Baseline: 250 pixels.** For every 100 pixels away from baseline, 25% development growth modifier. Linear scaling.

```
modifier_percent = (250 - location_size) / 100 * 25

Examples:
  50 pixels:  (250 - 50)  / 100 * 25 = +50% dev growth modifier
  150 pixels: (250 - 150) / 100 * 25 = +25% dev growth modifier
  250 pixels: (250 - 250) / 100 * 25 = 0%
  350 pixels: (250 - 350) / 100 * 25 = -25% dev growth modifier
  550 pixels: (250 - 550) / 100 * 25 = -75% dev growth modifier
```

Delivered via `add_location_modifier` with `local_monthly_development_modifier` and a `size` parameter computed from the formula. Applied once at game start, never recalculated (location size is fixed geography).

This is a rate modifier like prosperity/devastation:
- Small locations are volatile. They respond quickly to building investment. A small town that builds 30 guilds urbanizes noticeably within a decade.
- Large locations are sluggish. It takes massive sustained investment to shift their character. A sprawling province resists change in either direction.

This is NOT directional. It doesn't push toward extraction or production -- it modulates how fast buildings and other forces take effect.

---

## 6. Vanilla Modifier Adaptation

### Design Principle

**Buildings are the only directional force.** Everything else is a rate modifier — it makes the location adapt faster or slower, but does not push toward extraction or production.

- **Positive `local_monthly_development_modifier`** = location adapts faster. Dynamism, investment, connectivity, technological progress.
- **Negative `local_monthly_development_modifier`** = location is stuck. Isolation, disruption, harsh conditions.
- **Flat `local_monthly_development`** = reserved for: core equilibrium spring, market centers, and building pressure (via `sul_extraction_size` / `sul_production_size`). No vanilla event/static modifier should use flat.

All vanilla flat modifiers that aren't part of the core spring get converted to percentage. The question for each is only: does this make the location more dynamic (+%) or more stuck (-%)?

Full audit in Appendix A.

---

## 7. Implementation Plan

### Phase 1: Core Equilibrium

Base upward pressure + dev-scaled downward. Merge into existing TRY_INJECT blocks in `sul_vanilla_economy_injects.txt`.

### Phase 2: Building Pressure

Add `local_monthly_development` to every extraction/production building in SUL's existing INJECT/REPLACE files. Market center inject.

### Phase 3: Prosperity/Devastation

Add `local_monthly_development_modifier` to prosperity and devastation TRY_INJECT blocks.

### Phase 4: Geography

Vegetation, topography, climate overrides in new files. Farmland neutral, mountains strongest anti-urban.

### Phase 5: Location Size

Game-start script: compute `(250 - location_size) / 100 * 25 / 100` as modifier size, apply permanent `local_monthly_development_modifier` location modifier.

### Phase 6: Vanilla Modifier Audit

Walk every vanilla source of `local_monthly_development` and `local_monthly_development_modifier`. Classify each as fitting or not fitting the specialization framing. Override where needed.

### File Integration

- `sul_vanilla_economy_injects.txt`: `location_base_values`, `development`, `prosperity`, `devastation`, `market_center`
- Existing building INJECT/REPLACE files: add `local_monthly_development` per building
- New files: `sul_dev_vegetation.txt`, `sul_dev_topography.txt`, `sul_dev_climates.txt`
- Location size: scripted_effect in game-start init chain

---

## Open Questions

None. Vanilla modifier audit follows in Appendix A.

---

# Appendix A: Vanilla Modifier Audit

Complete walk of every vanilla source of `local_monthly_development` (flat) and `local_monthly_development_modifier` (percentage). Each entry classified per our design:

- **Flat positive** = pushes toward production. Keep if urbanization/trade/capital themed. Reverse if extraction/agricultural themed.
- **Flat negative** = pushes toward extraction. Keep if destruction/rural themed. Reverse if urbanization themed.
- **Percentage positive** = location adapts faster. Keep if dynamism/connectivity/prosperity themed.
- **Percentage negative** = location is stuck. Keep if isolation/disruption/stagnation themed.

## A.1 Percentage Modifiers (`local_monthly_development_modifier`)

### Geography (vegetation, topography, climate)

These are the largest vanilla percentage modifiers. In our system, geography pushes downward (flat, anti-urban). The vanilla percentage values get CANCELLED and replaced with our flat values from section 3.

| Source | Block | Vanilla % | Action | New Value |
|--------|-------|-----------|--------|-----------|
| vegetation | `farmland` | +0.10 | Override to **+0.05** | Min positive. Open land. |
| vegetation | `woods` | -0.20 | Override to **-0.10** | Min negative. Light cover. |
| vegetation | `forest` | -0.25 | Keep **-0.25** | Average. Clearable timber. |
| vegetation | `desert` | -0.33 | Override to **-0.35** | Between average and large. No water/timber. |
| vegetation | `jungle` | -0.30 | Override to **-0.50** | Large. Dense, regrows, fights construction. |
| topography | `mountains` | -0.50 | Override to **-0.75** | Very large. Physical barrier. |
| topography | `hills` | -0.25 | Override to **-0.10** | Min. Historical hill cities. |
| topography | `plateau` | -0.10 | Keep **-0.10** | Min. Elevated but buildable. |
| topography | `wetlands` | -0.30 | Override to **-0.50** | Large. Drainable but expensive. |
| climates | `tropical` | -0.10 | Keep **-0.10** | Min. Disease/heat, but major cities exist. |
| climates | `arctic` | -0.25 | Override to **-0.90** | Max. Extreme cold. |

Implementation: `TRY_INJECT` into each block with `local_monthly_development_modifier = (our value - vanilla value)` to adjust to target.

### Static Modifiers — Infrastructure/Connectivity

These represent "the location is connected, dynamic, accessible" = adapts faster. Percentage fits.

| Source | Block | Vanilla % | Action | Rationale |
|--------|-------|-----------|--------|-----------|
| location.txt | `has_road` | +0.05 | **Keep** | Road = connectivity = adapts faster |
| location.txt | `has_road_connected_to_capital` | +0.20 | **Keep** | Capital road = strong connectivity |
| location.txt | `coastal` | +0.10 | **Keep** | Maritime access = adapts faster |
| location.txt | `river_flowing_through` | +0.05 | **Keep** | River trade = connectivity |
| location.txt | `location_imports` | +0.0002/import | **Keep** | Trade = market integration = adapts faster |
| location.txt | `location_exports` | +0.0002/export | **Keep** | Trade = market integration = adapts faster |

No overrides needed. Vanilla values fit the "adapts faster" framing.

### Static Modifiers — War/Disruption

These represent "location is stuck, disrupted, paralyzed" = negative percentage fits.

| Source | Block | Vanilla % | Action | Rationale |
|--------|-------|-----------|--------|-----------|
| location.txt | `is_blockaded_by_enemies` | -0.20 | **Keep** | Trade cut = stuck |
| location.txt | `is_blockaded_by_ice` | -0.20 | **Keep** | Isolated = stuck |
| location.txt | `under_siege` | -0.20 | **Keep** | Destruction = paralyzed |
| location.txt | `looted` | -0.25 | **Keep** | Pillaged = stuck |

No overrides needed.

### Static Modifiers — Event Modifiers (Percentage)

| Source | Block | Vanilla % | Action | Rationale |
|--------|-------|-----------|--------|-----------|
| location.txt | `maintained_waterways_modifier` | +0.10 | **Keep** | Waterway maintenance = dynamism |
| location.txt | `schladming_bergordnung` | +0.05 | **Keep** | Mining regulation = organized economy adapts faster |
| location.txt | `freiberger_berggeschrey` | +0.05 | **Keep** | Mining boom = economic dynamism |
| location.txt | `fra_venus_tard_brigands` | -0.50 | **Keep** | Brigand damage = stuck |
| location.txt | `fra_english_ports_raided` | -0.50 | **Keep** | Port raid = stuck |
| location.txt | `fra_pont_neuf_constructed` | +0.25 | **Keep** | Monumental bridge = connectivity/dynamism |
| location.txt | `fra_pont_neuf_constructed_scaled_back` | +0.10 | **Keep** | Modest bridge = mild dynamism |
| location.txt | `birth_of_a_new_city_adm` | +0.25 | **Keep** | New city = strong dynamism |
| location.txt | `por_estudo_geral` | +0.10 | **Keep** | University = knowledge dynamism |
| location.txt | `urban_growing_pains` | +0.33 | **Keep** | Rapid growth = extreme dynamism |
| location.txt | `nanban_port` | +0.10 | **Keep** | Foreign trade = connectivity |
| location.txt | `pap_drained_marshes` | +0.30 | **Keep** | Land reclamation = adapts faster |
| location.txt | `chi_grand_canal` | +0.05 | **Keep** | Canal = connectivity |
| location.txt | `pue_mesa_verde_reclaimed` | +0.05 | **Keep** | Reclaimed site = adapts faster |
| location.txt | `center_of_urbanization_modifier` | +0.25 | **Keep** | Urbanization hub = dynamism |
| location.txt | `rural_development_modifier` | +0.10 | **Keep** | Rural growth = adapts faster (not directional) |

These all fit. Mining modifiers (Schladming, Freiberger) no longer need reversal -- as percentages they mean "this economy is active and adapting," not "push toward production." The mining DIRECTION comes from the extraction buildings at the location.

### Building Types (Percentage)

| Source | Block | Vanilla % | Action | Rationale |
|--------|-------|-----------|--------|-----------|
| capital_buildings.txt | `supreme_court` | +0.10 | **Keep** | Seat of justice = institutional dynamism |
| unique_buildings.txt | `hexamilion_wall` | -0.10 | **Keep** | Defensive wall = fortified, resistant to change |
| unique_buildings.txt | `pap_drained_marshes` | +0.025 | **Keep** | Reclamation = adapts faster (building-scope, stacks with static modifier) |
| unique_buildings.txt | `pue_mesa_verde_reclaimed` | +0.025 | **Keep** | Reclaimed site = adapts faster |

### Government Reforms (Percentage)

| Source | Block | Vanilla % | Action | Rationale |
|--------|-------|-----------|--------|-----------|
| common.txt | Harbor admin (naval reform) | +0.10 on coastal | **Keep** | Naval governance = coastal dynamism |

### Laws (Percentage)

| Source | Block | Vanilla % | Action | Rationale |
|--------|-------|-----------|--------|-----------|
| 20_hre.txt | `imperial_reform_rhenish_palatinate` | +0.10 | **Keep** | HRE reform = institutional dynamism |

### Pop Types (Percentage)

| Source | Block | Vanilla % | Action | Rationale |
|--------|-------|-----------|--------|-----------|
| 00_default.txt | Burgher `literacy_impact` | +0.25 | **Keep** | Literate merchants = economic dynamism |

### Avatars (Percentage)

| Source | Block | Vanilla % | Action | Rationale |
|--------|-------|-----------|--------|-----------|
| hindu.txt | `rakshasa` | +0.10 on ports | **Keep** | Divine maritime blessing = port dynamism |

---

## A.2 Flat Modifiers (`local_monthly_development`)

**All** vanilla flat modifiers convert to percentage. Buildings are the only directional force. The question for each modifier is only: does this make the location more dynamic (+%) or more stuck (%)?

### Static Modifiers — Prosperity/Devastation (Engine-Scaled)

| Block | Vanilla Flat | Action |
|-------|-------------|--------|
| `prosperity` | +0.004 (scaled 0-1) | **Cancel flat, add +25%** | 
| `devastation` | +0.004 (scaled 0 to -1) | **Cancel flat, add -100%** |

```
TRY_INJECT:prosperity = { local_monthly_development = -0.004  local_monthly_development_modifier = 0.25 }
TRY_INJECT:devastation = { local_monthly_development = -0.004  local_monthly_development_modifier = -1.0 }
```

### Static Modifiers — Institutions

Only `military_revolution_birth` has a flat development modifier — handled in the dynamism table below. No per-institution scaling exists in vanilla; the design doc's original `institutions_full` entry was incorrect.

### Static Modifiers — Dynamism (positive %)

These all represent activity, investment, or progress that makes the location more responsive to its building mix.

| Block | Vanilla Flat | New % | Rationale |
|-------|-------------|-------|-----------|
| `monumental_architecture` | +0.05 | **+0.20** | Very large. Massive construction reshapes the location. |
| `ira_building_isfahan` | +0.01 | **+0.10** | Average. Major city construction project. |
| `ira_isfahan_maidan` | +0.01 | **+0.10** | Average. Grand public square = activity hub. |
| `ira_second_capital` | +0.02 | **+0.15** | Large. Administrative center = organized economy. |
| `introduction_of_newcommen_engine` | +0.01 | **+0.05** | Min. Technological progress = adapts faster. |
| `introduction_of_steam_power_blast` | +0.01 | **+0.05** | Min. Technological progress. |
| `introduction_of_watt_engine` | +0.01 | **+0.05** | Min. Technological progress. |
| `introduction_of_flying_shuttle` | +0.01 | **+0.05** | Min. Manufacturing innovation. |
| `introduction_of_spinning_jenny` | +0.01 | **+0.05** | Min. Manufacturing innovation. |
| `growing_glass_industry_modifier` | +0.02 | **+0.10** | Average. Proto-industrial growth = dynamism. |
| `growing_paper_industry_modifier` | +0.02 | **+0.10** | Average. Proto-industrial growth. |
| `growing_cloth_industry_modifier` | +0.02 | **+0.10** | Average. Proto-industrial growth. |
| `industrial_urbanization_modifier` | +0.01 | **+0.10** | Average. Economic transformation. |
| `jap_yoshiwara_district` | +0.02 | **+0.10** | Average. Urban entertainment district. |
| `jap_dejima_island` | +0.05 | **+0.20** | Very large. Foreign trade enclave = high dynamism. |
| `pue_mesa_verde_capital` | +0.10 | **+0.25** | Max. Major capital construction. |
| `crown_investments_modifier` | +0.05 (decaying) | **+0.20** | Very large. Crown capital injection (temporary). |
| `trading_settlement` | +0.015 | **+0.10** | Average. Trade activity = dynamism. |
| `capital_connection_modifier` | +0.05 | **+0.20** | Very large. Capital connectivity = adapts faster. |
| `forced_labor` | +0.01 | **+0.05** | Min. Coerced productivity. |
| `rice_compensation` | +0.02 | **+0.10** | Average. Agricultural subsidy = active intervention. |
| `introduction_of_self_sharpening_plows` | +0.01 | **+0.05** | Min. Agricultural tech = progress. |
| `agricultural_revolution` | +0.01 | **+0.10** | Average. Revolution = major adaptation. |
| `iro_three_sisters_harvest` | +0.01 | **+0.05** | Min. Harvest innovation. |
| `pue_improve_capital_irrigation` | +0.03 | **+0.15** | Large. Major infrastructure investment. |
| `swe_slash_and_burn_new_farms` | +0.01 | **+0.05** | Min. Land clearing = active development. |
| `por_wool_town` | +0.10 | **+0.25** | Max. Designated wool center = high activity. |
| `shinto_local_christian_mission` | +0.015 | **+0.05** | Min. Foreign religious contact. |
| `islamic_missionaries` | +0.015 | **+0.05** | Min. Missionary activity. |
| `muslim_sailor_community` | +0.015 | **+0.05** | Min. Maritime cultural contact. |
| `mosque_of_x` | +0.015 | **+0.10** | Average. Major mosque = pilgrimage hub. |
| `famous_icon` | +0.005 | **+0.05** | Min. Cultural prestige. |
| `monasteries_blooming` | +0.01 | **+0.05** | Min. Monastic institutional vitality. |
| `waqfs_donated` | +0.01 | **+0.05** | Min. Religious endowments fund activity. |
| `chk_rebuilding_woodhenge` | +0.02 | **+0.10** | Average. Monumental construction activity. |
| `chk_protection_against_flooding` | +0.03 | **+0.15** | Large. Major infrastructure. |
| `chk_outer_cahokia_protected_flooding` | +0.03 | **+0.15** | Large. Major infrastructure. |
| `PRU_settlers_in_silesia` | +0.02 | **+0.10** | Average. Settlement = active development. |
| `parliament_location` | +0.01 | **+0.10** | Average. Seat of government = institutional dynamism. |
| `improved_flow_of_goods` | +0.01 | **+0.05** | Min. Trade improvement. |
| `develop_province` (cabinet) | +0.0025 | **+0.05** | Min. Crown attention. |
| `aid_constantinople` (cabinet) | +0.005 | **+0.05** | Min. Imperial investment. |
| `swe_slash_and_burn_new_farms` (cabinet) | +0.01 | **+0.05** | Min. Land clearing. |
| `military_revolution_birth` (institution) | +0.001 | **+0.05** | Min. Military modernization. |

### Static Modifiers — Stagnation (negative %)

These represent disruption, decay, or paralysis that makes the location resistant to change.

| Block | Vanilla Flat | New % | Rationale |
|-------|-------------|-------|-----------|
| `chastening_of_venice` | -0.01 | **-0.10** | Min. Political punishment = economic paralysis. |
| `chk_river_water_polluted` | -0.03 | **-0.25** | Average. Environmental damage = stuck. |
| `chk_shadow_of_cahokia_city` | -0.04 | **-0.25** | Average. City decline = stagnation. |
| `PRU_robber_barons` | -0.01 | **-0.10** | Min. Banditry = economic disruption. |

### Static Modifiers — Cancel Entirely

| Block | Vanilla Flat | Rationale |
|-------|-------------|-----------|
| `tribals_expelled` | +0.001 | **Cancel.** Negligible, no clear dynamism signal. |
| `dhimmi_residence` | +0.001 | **Cancel.** Negligible. |
| `has_ongoing_colonial_charter_migration` | +0.0025 | **Cancel.** Let buildings handle direction. |

### Building Types (Flat → %)

| Building | Vanilla Flat | New % | Rationale |
|----------|-------------|-------|-----------|
| `trade_company_headquarters` | +0.01 | **+0.10** | Average. Trade company HQ = economic hub. |
| `trade_company_foreign_influence` | +0.005 | **+0.05** | Min. Satellite trade presence. |
| `venkateswara_temple` | +0.005 | **+0.05** | Min. Hindu temple = cultural activity. |
| `piazza_san_marco` | +0.01 | **+0.10** | Average. Iconic civic square. |

---

## A.3 Summary of Required Overrides

All vanilla flat `local_monthly_development` modifiers are converted to `local_monthly_development_modifier` (percentage). Only the core spring (location_base_values, development scaler) and market centers remain flat.

### Geography (8 TRY_INJECT blocks)
Override vanilla `local_monthly_development_modifier` in vegetation/topography/climate files. Three blocks (forest, plateau, tropical) already at target — no adjustment needed.

### Prosperity/Devastation (2 TRY_INJECT blocks)
Cancel vanilla flat +0.004, apply +25% / -100% `local_monthly_development_modifier`.

### Core Spring + Location Size (3 additions)
`location_base_values`: +0.05 flat upward + 0.625 modifier baseline. `development`: -0.001 flat per dev. `location_size_impact`: -0.0025 modifier per pixel.

### Market Center (1 TRY_INJECT block)
Flat +0.005 production push (equivalent to 25 building levels).

### Flat-to-Percentage Conversions (all remaining)
Every vanilla flat modifier gets: cancel flat (`local_monthly_development = -(vanilla value)`), add percentage (`local_monthly_development_modifier = X`).

Total unique blocks requiring override:
- 8 geography (vegetation/topography/climate TRY_INJECTs — 3 at target already)
- 2 prosperity/devastation (static modifier TRY_INJECT)
- 2 core spring (location_base_values + development in existing economy injects)
- 1 market center (static modifier TRY_INJECT)
- 1 location_size_impact (static modifier TRY_INJECT)
- 1 institution (military_revolution_birth TRY_INJECT)
- 37 dynamism conversions (static modifier TRY_INJECT — cancel flat + add positive %)
- 3 stagnation conversions (static modifier TRY_INJECT — cancel flat + add negative %)
- 3 cancellations (static modifier TRY_INJECT — cancel flat only)
- 4 building types (INJECT — cancel flat + add positive %)
- 3 cabinet actions (INJECT — cancel flat + add positive %)

### One-Time Development Effects (no overrides)
Vanilla uses `change_development` with 8 named script values (+0.25 to +2.5) across 471 callsites in events, missions, parliament issues, and cabinet actions. These are intentionally left alone -- the equilibrium spring absorbs small perturbations naturally, and overriding individual events would require maintaining 117 file copies across patches.

### Total override count: 65 blocks (57 TRY_INJECT + 4 building INJECT + 3 cabinet INJECT + 1 location_base_values constant)
