# Location Wealth Design

## Concept

Replace country-level estate gold as the capital returns source with per-location **wealth** — physical assets (land, workshops, trade networks, church property, crown treasury) placed at specific locations. Wealth is a stock that converges toward an equilibrium target, not a derived value. Fast to destroy, slow to rebuild.

All wealth is treated uniformly — crown, nobles, clergy, burghers. No distinction in mechanics, no special protection for crown gold. Occupation bleeds everything.

## Variables Per Location

- `sul_noble_assets`
- `sul_clergy_assets`
- `sul_burgher_assets`
- `sul_crown_assets`

Crown wealth distributed to locations using the same system as estates. Crown distribution weighting TBD (likely favors capital, governor seats, forts — but same convergence mechanics).

## Target Calculation

The equilibrium target is the share of estate/crown treasury that "should" be at this location based on political power distribution.

### Option A: Per-Estate Distribution (Precise)

Uses engine-exposed per-estate power values. No pre-computation pass needed.

```
target_noble   = noble_estate_gold   × local_estate_power(estate_type:nobles_estate)   / estate_power:nobles_estate
target_clergy  = clergy_estate_gold  × local_estate_power(estate_type:clergy_estate)    / estate_power:clergy_estate
target_burgher = burgher_estate_gold × local_estate_power(estate_type:burghers_estate)  / estate_power:burghers_estate
target_crown   = country_gold        × crown_distribution_weight (TBD)
```

- Burgher wealth only appears where burghers have power
- Noble wealth spreads across the countryside
- Clergy wealth concentrates at religious centers
- Two engine reads + one divide per estate per location

### Option B: Aggregate Distribution (Simple)

Uses aggregate political power fraction. One engine read per location, shared across all estates.

```
fraction = local_political_power_fraction
target_noble   = noble_estate_gold   × fraction
target_clergy  = clergy_estate_gold  × fraction
target_burgher = burgher_estate_gold × fraction
target_crown   = country_gold        × fraction
```

- Fewer ops but doesn't gate by estate presence
- Burgher wealth appears at locations with zero burghers (small amounts at low-power locations)
- Acceptable if the aggregate approximation is close enough in practice

## Monthly Convergence

Linear convergence at 1% of target per month, modified by prosperity/devastation.

```
rate = 0.01 × (1 + f(prosperity))
change = min(abs(target - current), target × rate) × sign(target - current)
```

- Prosperous locations recover faster (rate > 1%)
- Devastated locations recover slower or stagnate (rate near 0% or negative)
- Full recovery from zero at base rate: ~8.3 years
- With high prosperity: ~3-4 years
- With heavy devastation: much longer, possibly frozen

**Open**: Verify whether devastation is a separate mechanic or negative prosperity in EU5.

## Occupation Effects on Convergence

While a location is occupied, the normal wealth convergence flow is **redirected**:

- Estates stop investing in the occupied location (no inflow toward target)
- The wealth that *would* have flowed in is redirected to the occupier
- A portion of the redirected flow is destroyed (occupation is not efficient extraction)
- The location's wealth stagnates or decays, falling further behind its equilibrium every month

This means:
- Short occupation: one-time loot damage, minimal ongoing loss
- Long occupation: growing recovery deficit as the location falls further behind equilibrium
- Liberation: recovery resumes from a deeper hole — the longer occupied, the longer to rebuild
- Occupier income scales with the location's productive value (high GDP = more redirected flow)

Combined with war momentum, a nation losing economic centers faces simultaneous military degradation, treasury drain, estate wealth destruction, and growing recovery deficits. Genuine pressure to make peace.

## Execution

Runs in `monthly_country_pulse` inside a single unified `every_owned_location` wrapper alongside other per-location monthly work (WPP updates, etc.). Sub-effects called within the shared loop to avoid redundant scope traversal.

```
sul_monthly_location_pass = {
    every_owned_location = {
        sul_wealth_converge_effect = { }
        sul_wpp_update_effect = { }
        # other per-location monthly work
    }
}
```

## Seeding

On game start / version init, after the GDP pass runs:

```
per location:
    sul_noble_assets   = noble_estate_gold   × distribution_weight
    sul_clergy_assets  = clergy_estate_gold   × distribution_weight
    sul_burgher_assets = burgher_estate_gold  × distribution_weight
    sul_crown_assets   = country_gold         × distribution_weight
```

Where `distribution_weight` is either Option A or Option B from above.

## Looting & Destruction

### Vanilla Override

Vanilla `loot_location` is a hardcoded engine effect used by horde raid events. Normal occupations do NOT trigger vanilla looting — `amount_looted_modifier` defaults to 0 and the `looted` modifier is not set by standard occupation. We build our own system from scratch.

### Looting Efficiency (`sul_looting_efficiency`)

Custom modifier. Does NOT change how much wealth is extracted — it shifts the split between **destroyed** and **kept**.

- Low efficiency: most extracted wealth is destroyed (fires, breakage, chaos). Attacker gets little.
- High efficiency: more goes to crown + estates. Disciplined looting, intact capture.
- The victim loses the same amount regardless of attacker efficiency.

Sources: advances, commander traits, military traditions, policies, etc.

### Principles

- Total extraction from a location is capped and variably effective
- No artificial unlootable reserve — poverty itself is the defense
- Diminishing returns across wars (devastated nation has less to take)
- Looting has political consequences: loyalty shifts for both sides

### Loot Event — Trigger & Three Buckets

**Trigger:** `on_location_occupied` — one-time extraction when a location is occupied.

**Extraction (loser side):**
- Wealth taken from crown assets at the location
- Wealth taken from estate assets at the location (nobles, clergy, burghers proportional to their local share)

**Distribution (winner side):**
1. **Destroyed**: base percentage of extracted wealth lost in the chaos. Reduced by `sul_looting_efficiency`.
2. **To the crown**: portion goes to the occupying nation's treasury. War spoils seized by the military.
3. **To the estates**: portion distributed to the occupying nation's estates. Soldiers and camp followers enriching themselves.

Base split TBD (e.g. 50% destroyed / 30% crown / 20% estates at zero efficiency). Higher `sul_looting_efficiency` shifts from destroyed toward crown + estates.

### Loyalty Effects

Looting triggers estate loyalty shifts on both sides:

**Loser estates**: loyalty malus proportional to wealth lost. Their property was destroyed or stolen — they blame the crown for failing to protect them.

**Winner estates**: loyalty boost proportional to wealth received. The estates profited from the war — satisfaction with the crown increases.

This creates a political feedback loop:
- Aggressive looting enriches your estates and boosts loyalty
- Getting looted damages loyalty, potentially destabilizing the losing nation
- A nation that gets repeatedly looted faces both economic AND political collapse

### Extraction Effectiveness Modifiers

- **Looted modifier**: location already picked clean, reduced total extraction
- **Devastation/low prosperity**: damaged infrastructure, less extractable wealth
- **Hard cap**: no single event takes more than X% of current location wealth

### Anti-Snowball (Emergent)

No explicit protection needed. The system self-limits:

1. First war: loot rich cities, big payoff
2. Nation recovers slowly (devastation suppresses recovery rate AND occupation redirects convergence flow)
3. Devastation also suppresses GDP target, so equilibrium itself is lower
4. Second war: less wealth to take, diminishing returns
5. Attacker is incentivized to target new, prosperous locations rather than re-sacking ruins

## Capital Returns (WPP Change)

Current system: `estate_gold × 2% / country_pops × asset_share × power`

Proposed: `location_assets × return_rate / local_pops`

- No more country-level asset_share computation
- Returns are inherently local — wealthy locations generate more WPP
- War destruction directly impacts WPP at affected locations

## Open Questions

1. **Crown distribution weight**: How to weight crown assets across locations? Capital + governor seats + forts favored, but formula TBD.
2. **Asset cap**: Should assets have a maximum per location (proportional to building levels or development)?
3. **EPBM interaction**: Estate building maintenance drains estate gold. Should it also drain location assets, or keep EPBM on liquid capital only?
4. **Prosperity/devastation axis**: Is devastation negative prosperity or a separate mechanic? Affects how the rate modifier works.
5. **Occupation flow split**: What percentage of redirected convergence flow is destroyed vs kept by occupier?

## Resolved Questions

- **Commoner assets**: Yes. Commoners (peasants_estate) get location-based assets on the same footing as upper estates. 2% of assets becomes demand spending for all estates.
- **Enrichment tier**: Already implemented. The 7th demand tier feeds estate gold via `add_gold_to_estate` in `sul_update_country_economy`. Estate gold is the source pool that location wealth converges toward.
- **Dhimmi/Cossacks**: Dropped from wealth system. They are subsets of other estates and are excluded from existing economy systems. Only nobles, clergy, burghers, peasants, and crown are tracked.

---

## What Exists (April 2026)

### Infrastructure (complete)

**`sul_monthly_location_pass`** (country scope, `sul_gdp_update.txt`) — single `every_owned_location` loop runs monthly for player, yearly for AI. Handles:
- **Wage accumulation**: reads cached per-location wage bills into country locals, finalized into `sul_monthly_wages_*` after the loop.
- **Estate power accumulation**: sums `local_estate_power` for nobles, clergy, burghers, peasants across all locations into country vars (`sul_nobles_estate_raw_power`, etc.). Crown = sum of all four. These are the denominators for wealth fraction calculations.
- **Estate gold caching**: reads `estate_gold` (complex engine formula) once per country into `sul_nobles_estate_gold`, `sul_clergy_estate_gold`, `sul_burghers_estate_gold`.

**`sul_update_country_economy`** (country scope, `sul_gdp_update.txt`) — full init-time pass with identical wealth accumulation. Also computes WPP, enrichment, and wage transfer weighting.

**Debug panel** (`sul_wealth_debug_values.txt` + `aaa_sul_location_tooltips.gui`) — tooltip table showing per-estate: Local power, National power, Frac%, Gold, Target. Reads accumulated country vars for national/gold (cheap variable lookups), live `local_estate_power` for local (engine call per hover). Crown derived as sum of all estates for both local and national.

**Enrichment** (already in `sul_update_location_wpp`) — 7th demand tier. Per-location enrichment computed as `demand_base × WPP × @sul_w_enrichment × num_pops`, accumulated per estate in the location loop, paid to estates via `add_gold_to_estate` after the loop. This is the savings mechanism: income → enrichment → estate gold → location wealth target.

---

## Implementation Plan

### Phase 1: Per-Location Asset Variables + Seeding

**New location-scope variables** (5 total):
- `sul_noble_assets`
- `sul_clergy_assets`
- `sul_burgher_assets`
- `sul_peasant_assets`
- `sul_crown_assets`

**New scripted effect** `sul_wealth_seed_location` (location scope). Defined in `sul_gdp_update.txt` alongside the other wealth code.

For each estate, seed at equilibrium:
```
set_variable = {
    name = sul_noble_assets
    value = "local_estate_power(estate_type:nobles_estate)"
}
change_variable = {
    name = sul_noble_assets
    divide = { value = owner.var:sul_nobles_estate_raw_power min = 0.001 }
}
change_variable = {
    name = sul_noble_assets
    multiply = owner.var:sul_nobles_estate_gold
}
```
Repeat for clergy, burghers (same pattern with their estate types). Peasants use `peasants_estate`. Crown uses:
```
set_variable = { name = sul_crown_assets value = local_political_power_fraction }
change_variable = { name = sul_crown_assets multiply = owner.gold }
```

**Call site**: In `sul_initialize_economy` (`sul_economy_on_actions.txt`), add a new `every_owned_location` loop **after** the `sul_update_country_economy` call (raw power accumulators must be populated first):
```
every_country = {
    limit = { is_real_country = yes }
    every_owned_location = {
        if = {
            limit = { NOT = { has_variable = sul_noble_assets } }
            sul_wealth_seed_location = yes
        }
    }
}
```
The `NOT = { has_variable = ... }` guard prevents re-seeding on version migration.

### Phase 2: Monthly Convergence

**New scripted effect** `sul_location_converge_wealth` (location scope). Defined in `sul_gdp_update.txt`.

**Insertion point**: Inside `sul_monthly_location_pass`'s `every_owned_location` loop, as the first call **before** the `owner ?= { }` block:
```
every_owned_location = {
    sul_location_converge_wealth = yes     # ← NEW
    owner ?= {
        # existing wealth accumulation (raw power)
        # existing wage accumulation
    }
}
```

Do the same in `sul_update_country_economy`'s `every_owned_location` loop, as the first call before the `owner ?= { }` block.

**Formula** for each estate (example: nobles). The effect handles its own `owner ?=` scoping internally:
```
sul_location_converge_wealth = {
    # Skip if assets not yet seeded
    if = {
        limit = { has_variable = sul_noble_assets }

        # Compute target from last month's accumulated power
        set_local_variable = {
            name = sul_target_nobles
            value = "local_estate_power(estate_type:nobles_estate)"
        }
        change_local_variable = {
            name = sul_target_nobles
            divide = { value = owner.var:sul_nobles_estate_raw_power min = 0.001 }
        }
        change_local_variable = {
            name = sul_target_nobles
            multiply = owner.var:sul_nobles_estate_gold
        }

        # gap × rate
        set_local_variable = {
            name = sul_wealth_delta
            value = local_var:sul_target_nobles
        }
        change_local_variable = {
            name = sul_wealth_delta
            subtract = var:sul_noble_assets
        }
        change_local_variable = {
            name = sul_wealth_delta
            multiply = 0.01
        }
        # TODO: multiply by (1 + prosperity_factor) once prosperity is verified

        change_variable = {
            name = sul_noble_assets
            add = local_var:sul_wealth_delta
        }
        # Clamp to zero
        if = {
            limit = { var:sul_noble_assets < 0 }
            set_variable = { name = sul_noble_assets value = 0 }
        }

        # Repeat for clergy, burghers, peasants, crown
        # (same pattern, crown uses local_political_power_fraction × owner.gold for target)
    }
}
```

**Denominator note**: `owner.var:sul_nobles_estate_raw_power` holds last month's accumulated total. It was zeroed at the top of `sul_monthly_location_pass` and is being re-accumulated in the `owner ?= { }` block that runs after this call. This one-month staleness is intentional — it avoids a second location pass.

**Capital returns from assets**: After convergence runs, 2% of each estate's assets becomes demand spending for that estate's pops at this location. This is the return on physical wealth. Implementation: add `var:sul_noble_assets × 0.02` to the noble WPP computation in `sul_update_location_wpp` where capital returns are currently added. Same for all 5 estate types. This replaces the current country-level `sul_return_*` path with a local one, but the WPP formula structure stays the same — only the source changes from `sul_return_nobles × sul_asset_share × power_share` to `sul_noble_assets × 0.02 / local_noble_pops`.

### Phase 3: Destruction Mechanics

**3a. Occupation drain** — inside `sul_location_converge_wealth`, add an occupation branch:
```
if = {
    limit = { is_occupied = yes }
    # No convergence — drain instead
    change_variable = { name = sul_noble_assets multiply = 0.98 }
    # repeat for clergy, burghers, peasants, crown
}
else = {
    # Normal convergence (Phase 2 code)
}
```
Occupation bleeds 2% per month. The drained amount can optionally be routed to the controller's treasury.

**3b. Looting on occupation** — new scripted effect `sul_wealth_loot_location` (location scope).

Triggered from `on_location_occupied` in `sul_hardcoded.txt`:
```
on_location_occupied = {
    on_actions = { sul_wealth_on_location_occupied }
}
```

Define `sul_wealth_on_location_occupied` in `sul_economy_on_actions.txt`:
```
sul_wealth_on_location_occupied = {
    effect = {
        sul_wealth_loot_location = yes
    }
}
```

Loot effect extracts a percentage of each asset variable. Split into three buckets:
1. **Destroyed** (base 50%, reduced by `sul_looting_efficiency` modifier)
2. **To crown** (base 30%, increased by efficiency)
3. **To estates** (base 20%, increased by efficiency)

The victim loses the full extracted amount regardless of efficiency.

**3c. `sul_looting_efficiency`** — new custom modifier type. Defined in `main_menu/common/modifier_type_definitions/sul_modifier_types.txt`. Country scope, percent. Sources: advances, commander traits, military traditions, policies.

### Phase 4: Wealth Bar GUI

**Prerequisite**: Clean up the specialization button panel first.

**Button panel cleanup** (`location_window.gui` lines 3540-3818):
- Remove the debug `textbox` elements from each spec button (lines 3593-3601, and equivalents for farming/woodland/gathering/commercial). These show `sul_debug_net_*` script value calls.
- Remove the "AI" debug toggle button (lines 3804-3817).
- Leave the `sul_debug_net_*` script value definitions in their script_values file untouched — they have future purpose.
- The panel size `{ 46 240 }` and vbox structure stay.

**Wealth bar widget** — a new `widget` placed immediately to the left of the specialization button panel, inside the same parent container.

Position and size:
- Height: matches button panel exactly (240px)
- Width: 30% of button panel width = ~14px. Use `size = { 14 240 }`.
- Position: button panel is at `parentanchor = right|vcenter`, `position = { -5 0 }`. The wealth bar sits to its left with no gap: `position = { -19 0 }` (button panel's -5 minus its 46 width = -51, but since it's relative, wealth bar right edge = button panel left edge). The exact offset depends on the parent layout — measure from the button panel's left edge: `position = { -51 0 }` with `parentanchor = right|vcenter`.

Alternatively, wrap both in an `hbox` with `spacing = 0` so the engine handles alignment.

**Bar structure**: A vertical stack from bottom to top. Each estate gets a colored section. Section height = `(estate_assets / total_assets) × fill_ratio × 240`. Fill ratio = `min(1.0, total_assets / total_target)`.

**New script values** (in `sul_wealth_debug_values.txt`):
- `sul_wealth_total` = `var:sul_noble_assets + var:sul_clergy_assets + var:sul_burgher_assets + var:sul_peasant_assets + var:sul_crown_assets`
- `sul_wealth_target_total` = sum of all 5 target values
- `sul_wealth_fill_pct` = `min(100, (total / target_total) × 100)` — fill as percentage of bar height
- `sul_wealth_bar_nobles` = `(noble_assets / total) × fill_pct × 2.4` — pixel height for this section (240 × pct / 100)
- Same for clergy, burghers, peasants, crown

**Estate colors** (use vanilla estate palette):
- Nobles: `color = { 0.6 0.15 0.15 1 }` (dark red)
- Clergy: `color = { 0.2 0.3 0.7 1 }` (blue)
- Burghers: `color = { 0.7 0.6 0.1 1 }` (gold)
- Peasants: `color = { 0.4 0.3 0.2 1 }` (brown)
- Crown: `color = { 0.5 0.2 0.6 1 }` (purple)
- Empty: background shows through (black/dark)

**Bar implementation**: Five stacked `widget` blocks inside a bottom-anchored `vbox`, each containing a colored `icon` (solid texture) sized by the script values. The vbox fills from bottom, leaving black space at top when below target.

### Phase Order

1 → 2 → capital returns adjustment (sequential, each depends on prior).
3 can begin after 2.
4 (button cleanup) can begin immediately. Wealth bar itself needs Phase 1 (asset variables must exist).

## Files That Change

| Phase | File | Change |
|-------|------|--------|
| 1 | `sul_gdp_update.txt` | Add `sul_wealth_seed_location` effect |
| 1 | `sul_economy_on_actions.txt` | Add seeding loop after init |
| 1 | `CONTROL_FLOW.md` | Document 5 new location variables |
| 2 | `sul_gdp_update.txt` | Add `sul_location_converge_wealth`, call in both loops |
| 2 | `sul_gdp_update.txt` | Modify `sul_update_location_wpp` — add local asset returns |
| 3 | `sul_gdp_update.txt` | Occupation branch in convergence effect |
| 3 | `sul_hardcoded.txt` | Hook `on_location_occupied` |
| 3 | `sul_economy_on_actions.txt` | Add loot on_action + effect |
| 3 | `sul_modifier_types.txt` | Add `sul_looting_efficiency` modifier |
| 4 | `location_window.gui` | Remove debug textboxes + AI toggle from button panel |
| 4 | `location_window.gui` | Add wealth bar widget adjacent to button panel |
| 4 | `sul_wealth_debug_values.txt` | Add bar sizing script values |
