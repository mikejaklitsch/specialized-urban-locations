# Market Passthrough / Trade Hub Design

## Goal

Make EU5's trade system support multi-hop passthrough: market A produces a surplus, market B accumulates a stockpile from imports, market C buys from B. Vanilla currently does pairwise A↔B trade only — B never accumulates inventory because imports get instantly satiated by local demand, so the B→C leg never forms.

This document captures the analysis from a research conversation about the existing **Market Stockpiles** mod (workshop ID `3629022149`, author "yosiu", id `yosiu_market_stockpiles`), the engine constraints that shaped its design, and a proposed cleaner architecture that targets *only* the passthrough problem instead of also trying to manipulate local pricing.

## Background: what the existing mod does

**Source:** `/mnt/d/Program Files (x86)/Steam/steamapps/workshop/content/3450310/3629022149/`

The mod is ~7,400 lines across 8 files. Architecture summary:

- **`on_action/country_monthly_stockpile.txt`** (4,364 lines) — main monthly pulse, hooks `monthly_country_pulse → stockpile_prices_adjustment`. Loops every market center × every good, branches on stockpile fill %:
  - **HIGH branch** (fill > 5% of capacity): adds negative-valued temp demand to push price down, scaled by cliff functions at 50/75/95% capacity. Also auto-builds a hidden warehouse building.
  - **NOT-HIGH branch:** removes the oversupply demand and demolishes the warehouse if present.
  - **LOW branch** (fill < 4.9%): adds price-up temp demand AND a small `add_goods_supply` injection to push price below base in shortage.
- **`building_types/market_stockpiles_buildings.txt`** (1,912 lines) — ~70 hidden warehouse buildings, one per good. `allow=always no`, `country_potential=always no`, `free_building_levels=1`, `can_close=no`. Each has a self-cancelling production method (e.g. `output=1, wool=0.97, net=+0.03`).
- **`goods_demand/full_stockpile.txt`** (150 lines) — two demand templates per good: `<good>_stockpile = <good> = -1` (price-down) and `<good>_oversupply = <good> = 1` (paired with the warehouse).
- **`script_values/stockpile_overflow.txt`** (885 lines) — fill % math, cliff cutoffs, `warehouse_efficiency_correction = 0.03 + production_efficiency_bonuses`, etc.
- **`on_action/_hardcoded_stockpile.txt`** — `on_game_start` initializer that pre-fills stockpiles.
- **`age/00_default_yosiu.txt`** — INJECTs `max_price = 1.9` into all six ages.
- **`auto_modifiers/country_yosiu_production.txt`** — INJECTs `produced_in_market_bonus = -0.2` (cancels vanilla local-producer discount).

### How the warehouse system actually works (the elegant part)

The warehouse looks like it adds supply but actually doesn't. The pairing:

- Building production method: `output = 1, wool = 0.97` → net +0.03 wool/cycle (scaled by production efficiency)
- Paired temp demand: `add_temporary_demand = { type = demand:wool_oversupply scale = warehouse_efficiency_correction }` where `warehouse_efficiency_correction = 0.03 + local_production_efficiency + global_production_efficiency + (raw material bonus)` — *exactly* the building's net output term-for-term
- Net effect on (supply − demand): zero
- Net effect on stockpile: zero
- Net effect on `goods_supply_in_market(wool)` reading: positive (the supply line still shows the building's contribution before the demand cancels it)

The warehouse exists *purely* to inflate the supply rate reading that vanilla's trade routing consumes, without leaking actual goods into inventory. This is the only way to do this in current EU5 because there is no `add_temporary_supply` effect.

## Engine constraints (verified during research)

These are facts about EU5's market simulation that aren't documented in game files but were established during the conversation. They are load-bearing for any redesign.

### `add_goods_supply` is a direct inventory write, not a flow injection

**Proof:** Tested by calling `add_goods_supply` on a market while paused. Stockpile changed instantly. Normal building production only flows into stockpile on the monthly tick consolidation, so an instant change while paused proves the function bypasses the supply pool entirely and writes directly to inventory.

**Implications:**
- `add_goods_supply` increments both `stockpile_in_market` and `goods_supply_in_market` (the engine reads supply as a delta from inventory state)
- Pairing `add_goods_supply(+X)` with `add_temporary_demand(-X)` does *not* cancel cleanly. The demand operates at the flow layer; the inventory bump already happened. Net result is stockpile inflation.
- This is why the original mod uses fake buildings instead of `add_goods_supply` — production from a building is the only available *flow-layer* supply injection. Building output goes to the supply pool, where temp demand can consume it before consolidation, leaving inventory untouched.

### Demand sums probably clamp at 0

The mod author claims (forum suggestion #5) that "demand can only go to 0, not negative." This is plausible based on:
- The mod's HIGH branch uses negative demand templates × positive scale to subtract from existing positive demand sources
- In a market with no/little natural demand for a good (e.g. one supplied entirely by trade with no local consumption), there's nothing to subtract from, and price can't be pushed below base
- The mod's LOW branch additionally calls `add_goods_supply` (a real inventory injection) to push price below base in shortage, which would be unnecessary if negative demand alone could do it

**Not formally verified.** The cleanest test would be a market with zero positive demand for a good, applying a negative-template temp demand, and checking whether price drops below base. Until tested, treat the clamp as "very likely true."

### `$VAR$` substitution works on compound identifiers in scripted effects/triggers

**Proof:** Vanilla uses this pattern in:
- `scripted_triggers/country_triggers.txt:719` → `has_building = building_type:$type$`
- `scripted_triggers/location_triggers.txt:135-137` → `building_type:$building_type$`
- `scripted_effects/___test_effects.txt:32` → `building_type:$building_type$`
- `scripted_triggers/00_clothing_triggers.txt:3` → `gfx_culture_applicable = $CULTURE_FLAG$`

This means the per-good unrolling in the existing mod's 4,364-line monthly file is *not* engine-forced. A scripted effect templated on `$GOOD$` can write `goods:$GOOD$`, `building_type:$GOOD$_warehouse`, `demand:$GOOD$_stockpile`, etc., and be called 70 times. The unique logic lives in one place (~30 lines) instead of 70 unrolled switch cases.

The mod author either didn't know about this or didn't use it. Their forum suggestion #4 explicitly complains about needing to write per-good if-chains, which suggests they didn't know.

### `set_variable` works on all scopes including market

**Source:** `effects.log:9461` lists `**Supported Scopes**: none` for `set_variable`. In PDX docs, "none" for universally-available effects means "all scopes" (the docs only filter when an effect is scope-restricted).

The mod author's forum suggestion #7 claims "no market scope variables exist" and stashes vars on the market's location instead. This contradicts the docs — likely the author didn't test or hit something unrelated. **Worth a 30-second test in a debug mod** to confirm `set_variable` actually persists on a market scope.

### No `on_market_*` monthly action

**Source:** `on_actions.log` — no market-scope monthly pulse exists. Only `monthly_country_pulse`, location pulses, and IO pulses. To run market logic monthly you must hook `monthly_country_pulse` (or one of the staggered country pulses like `four_yearly_country_pulse_25_percent` for performance) and use `every_market_center_in_country` with `has_markets = yes` filter.

### Vanilla 1.1 stockpile→trade-supply mechanism

Two defines in `00_defines.txt`:
```
1530: MARKET_MIN_STOCKPILE_TO_ALLOW_EXTRA_TRADE = 0.5
1531: MARKET_STOCKPILE_PERCENTAGE_FOR_EXTRA_TRADE = 0.05
```

When a market's stockpile fill exceeds the threshold, it grants `(percentage × stockpile)` as **extra trade supply**. The localization key `MARKET_GOOD_SUPPLY_FROM_STOCKPILE` confirms this is for trade routing. It enables middleman behavior at the engine level — exactly what the original mod's warehouse hack was simulating in 1.0.

**Working interpretation** (not formally verified): the extra trade supply is consumable by trade routing at the source market and shows up at destination markets as imports, which then count toward local supply at the destination via `TRADE_IMPACT_ON_SUPPLY_SCALE = 0.75`. So the source market's local price isn't directly affected, but the destination market's price drops naturally as imports flow in.

### Other relevant defines

```
1572: SUPPLY_AND_DEMAND_STABILITY_OFFSET_CONSTANT = 1
      # Added to S and D when computing market price.
      # Higher = lower volatility. Lower this to make prices more reactive.

1473: TRADE_IMPACT_ON_SUPPLY_SCALE = 0.75
1476: TRADE_IMPACT_ON_DEMAND_SCALE = 0.75
1472: BURGHER_TRADE_IMPACT_ON_SUPPLY_SCALE = 0.25
1475: BURGHER_TRADE_IMPACT_ON_DEMAND_SCALE = 0.25
1624: TRADE_IMPACT_ON_SUPPLY_AND_DEMAND = yes  # kill switch, leave alone

1338: PRODUCED_IN_MARKET_DEMAND = 0.1
      # The vanilla "produce locally → demand boost" the original mod
      # was canceling with produced_in_market_bonus = -0.2
```

## Current state of user's defines work

The user has already implemented a defines-based partial solution:

1. **Normalized trade impact on demand ratios** so trade imports/exports count as full demand (vanilla dampens them). Likely raised `TRADE_IMPACT_ON_DEMAND_SCALE` and possibly `BURGHER_TRADE_IMPACT_ON_DEMAND_SCALE` toward 1.0.
2. **Raised price reactiveness** to demand changes. Likely lowered `SUPPLY_AND_DEMAND_STABILITY_OFFSET_CONSTANT` from 1.0 to something smaller.
3. **Made stockpile→trade-supply always-on at 20%.** Set `MARKET_MIN_STOCKPILE_TO_ALLOW_EXTRA_TRADE = 0.0` and `MARKET_STOCKPILE_PERCENTAGE_FOR_EXTRA_TRADE = 0.20`.
4. **Improved sea trade.** Separate concern, not relevant to passthrough.

**What works:** Market A creates a surplus, A's price crashes, B has demand and higher price, trade A→B happens. Standard pairwise routing.

**What doesn't work:** Market B never accumulates stockpile, because incoming imports get instantly satiated by B's local demand. With no stockpile in B, the 20% extra-trade-supply mechanism never activates for B, so B can't act as a passthrough hub feeding C. The B→C leg never forms.

## The structural problem

EU5's trade routing is **consumption-driven**, not **speculation-driven**. Trade volume between two markets is capped by destination demand. Steeper price gradients (e.g., from asymmetric over/undersupply response) make traders saturate routes faster but don't change the equilibrium volume — they still stop importing once destination demand is satisfied. Real economies have merchants who hold inventory speculatively, expecting future profit; EU5 has no equivalent mechanism.

**The fix required:** create artificial demand in transit markets so they import *more than they consume*, accumulating stockpile that then activates the passthrough chain via the 20% define.

## Proposed solution: inverse-fill temp demand

### The formula

For each market center × each good, every monthly tick:

```
temp_demand_scale = (stop_point - fill_pct) * natural_demand * dampener
```

Where:
- `fill_pct = stockpile_in_market(good) / location.modifier:maximum_stockpile_capacity`
- `stop_point` is the target fill ratio (e.g., 1.0 for full, 0.5 for half-full target)
- `natural_demand` is the market's *pre-temp-template* demand for the good — must be read before applying the temp template to avoid feedback loops. Use `goods_demand_in_market(good)` at the start of the tick.
- `dampener` is the global tuning multiplier

When fill is 0%, the scale is at its max — a multiplier on the market's natural demand. This creates strong artificial pull, the market imports aggressively, stockpile climbs. As stockpile fills, the artificial demand decays toward zero. At full fill, only natural demand remains.

### Steady-state behavior

1. B starts empty. Inverse-fill temp demand creates strong pull.
2. B imports from A aggressively (price gradient + amplified demand).
3. B's stockpile climbs toward target.
4. As fill rises, B's artificial demand drops, prices stabilize.
5. B's stockpile activates vanilla's 20% extra-trade-supply mechanism.
6. C now sees B as a viable supplier (B has tradeable surplus).
7. B exports to C, stockpile drains.
8. Drop in fill re-activates B's artificial demand.
9. B re-imports from A.
10. Stable A→B→C chain forms.

### Why direction matters

If you scaled temp demand *with* stockpile fill (positive correlation) instead of inversely, you'd create a feedback loop that drains stockpile faster the fuller it gets. That's the opposite of what you want — markets would consume their own imports locally instead of acting as transit. **The negative correlation (`(stop_point - fill)`) is load-bearing.**

### Why asymmetric price response doesn't solve this

Considered as an alternative: scale price impact more from oversupply than from undersupply. This shifts where prices equilibrate but doesn't change the volume cap on trade between two markets. Trade is consumption-driven; price gradients only adjust the rate of approach to equilibrium, not the level. Asymmetric pricing is a tuning knob, not an architectural fix.

## Implementation outline

### File structure

```
in_game/common/
├── goods_demand/
│   └── passthrough_demands.txt        # ~70 lines: <good>_passthrough templates
├── script_values/
│   └── passthrough_values.txt         # fill % helper, dampener, stop_point
├── scripted_effects/
│   └── passthrough_effects.txt        # ~30 lines: $GOOD$-templated effect
└── on_action/
    └── passthrough_pulse.txt          # ~80 lines: monthly hook + 70 calls
```

### `passthrough_demands.txt`

One template per good, all positive (`<good> = 1`):

```
wool_passthrough = { wool = 1 hidden = no category = government_activities }
wild_game_passthrough = { wild_game = 1 hidden = no category = government_activities }
# ... 68 more
```

### `passthrough_effects.txt`

```
apply_passthrough_for_good = {
    if = {
        limit = {
            scope:full_market = {
                stockpile_in_market = {
                    goods = goods:$GOOD$
                    value < scope:full_market.passthrough_target_value
                }
            }
        }
        scope:full_market = {
            add_temporary_demand = {
                type = demand:$GOOD$_passthrough
                scale = {
                    value = passthrough_target_value
                    subtract = "scope:full_market.stockpile_in_market(goods:$GOOD$)"
                    divide = passthrough_target_value
                    multiply = "scope:full_market.goods_demand_in_market(goods:$GOOD$)"
                    multiply = passthrough_dampener
                }
                months = 1
            }
        }
    }
}

clear_passthrough_for_good = {
    scope:full_market = {
        remove_temporary_demand = demand:$GOOD$_passthrough
    }
}
```

(Pseudocode — specific scope and value syntax may need tweaking based on what the engine accepts. Verify against existing market-scope effect patterns.)

### `passthrough_pulse.txt`

```
monthly_country_pulse = {
    on_actions = {
        passthrough_apply_pulse
    }
}

passthrough_apply_pulse = {
    trigger = { has_markets = yes }
    effect = {
        every_market_center_in_country = {
            save_scope_as = full_market
            
            # Clear last month's templates first
            clear_passthrough_for_good = { GOOD = wool }
            clear_passthrough_for_good = { GOOD = wild_game }
            # ... 68 more
            
            # Apply new ones based on current fill
            apply_passthrough_for_good = { GOOD = wool }
            apply_passthrough_for_good = { GOOD = wild_game }
            # ... 68 more
        }
    }
}
```

### `passthrough_values.txt`

```
passthrough_target_value = {
    value = location.modifier:maximum_stockpile_capacity
    multiply = 0.5   # target 50% fill
}

passthrough_dampener = {
    value = 1.0   # global tuning multiplier
}
```

### Total scope

- ~80 calls (40 clear + 40 apply, or merged into one effect that handles both) per market per tick
- ~30 lines of unique scripted effect logic
- ~70 lines of demand templates (forced data declaration, not bloat)
- ~80 lines of monthly pulse boilerplate
- **Total: ~250 lines vs the original mod's ~7,400.** The 70 demand templates are the only forced repetition; everything else collapses via `$VAR$`.

## Things to watch / open questions

1. **Test `set_variable` on market scope** before relying on location-variable workarounds. Stash the natural demand in a market variable at the start of the tick to avoid the feedback loop, instead of reading it in the temp demand scale formula.

2. **Verify the `$VAR$` syntax against EU5's actual parser.** CK3/Vic3 patterns are the model but EU5 may have quirks. Test with a single good before unrolling 70 times.

3. **Tune the dampener carefully.** Too low → markets don't fill. Too high → import-from-source becomes unprofitable because the destination price rises too much. The valid window depends on transit costs and the price gradient from source markets. Start at 1.0 and adjust.

4. **Consider per-good or per-good-category dampeners.** Strategic goods (iron, naval supplies) may want aggressive stockpiling. Perishables (food) probably less so. Defines are global; if you want per-good control, a script value table works.

5. **Markets with zero natural demand** for a good will get zero artificial pull and never become hubs for it. If you want pure transit hubs (think Venice for spices it doesn't consume), add a `max(natural_demand, market_size_floor)` term to the formula. Likely not needed for v1 but worth knowing.

6. **The cliff dynamics from the original mod are intentionally dropped.** The user's goal is passthrough, not aggressive local price manipulation. If a steeper price response is wanted, tune `SUPPLY_AND_DEMAND_STABILITY_OFFSET_CONSTANT` rather than reintroducing scripted cliff functions.

7. **Shortage handling stays vanilla.** The user assessed this as "more a scaling issue" — natural supply/demand math handles low-stockpile price spikes if the stability constant is tuned. No scripted LOW branch needed. If shortages don't bite hard enough at very low fill levels, lower the stability constant further before reaching for script.

8. **Performance.** Monthly × every market × 70 goods × 2 calls per good = up to ~10k operations per country per month. Probably fine but if it's a problem, the staggered pulses (`four_yearly_country_pulse_25_percent`) can spread the work across calendar ticks.

9. **The fake-warehouse system from the original mod is completely unnecessary** for the passthrough goal. Vanilla's 20% define replaces the warehouse-as-supply-flag-flipper. Don't recreate it.

10. **The author's `produced_in_market_bonus = -0.2` workaround is also unnecessary** if you're not trying to manipulate local pricing the way the original mod does. Tune `PRODUCED_IN_MARKET_DEMAND` directly in defines if you want a different baseline.

## What this does NOT address

- Local price manipulation in surplus source markets (the original mod's HIGH branch). If you want A's wool price to *crash* when A has surplus (rather than just become tradeable), you still need scripted negative demand in A. But the original mod's design already shows this mostly works for markets with positive natural demand — the value-add of crashing prices in zero-demand markets is the edge case the demand-clamps-at-0 issue can't reach.
- Strategic resource hoarding gameplay (e.g., "I want to stockpile 5 years of grain"). Out of scope.
- AI-aware passthrough decisions. AI will use vanilla trade routing as it stands; the artificial demand makes routes more attractive but doesn't change the AI's decision algorithm.

## Quick reference: relevant files in vanilla

- `game/loading_screen/common/defines/00_defines.txt:1530-1531` — extra trade supply defines
- `game/loading_screen/common/defines/00_defines.txt:1572` — stability offset constant
- `game/loading_screen/common/defines/00_defines.txt:1472-1476` — trade impact scales
- `game/in_game/common/effect_localization/market_effects.txt` — market effect localization
- `game/in_game/common/scripted_triggers/country_triggers.txt:719, 870-873` — `$VAR$` examples
- `game/in_game/common/goods_demand/from_events.txt` — vanilla negative-template demand examples
- `game/in_game/common/country_interactions/demand_silver_tribute.txt:54-78` — vanilla `add_goods_supply` usage
- `~/Documents/Paradox Interactive/Europa Universalis V/docs/effects.log` — auto-generated effect reference (search for `add_temporary_demand`, `add_goods_supply`, `set_variable`)
- `~/Documents/Paradox Interactive/Europa Universalis V/docs/event_targets.log` — readers (`stockpile_in_market`, `goods_supply_in_market`, `market_price`, `target_price`)
- `~/Documents/Paradox Interactive/Europa Universalis V/docs/triggers.log` — `goods_supply_in_market`, `goods_demand_in_market`, `market_food_*`
- `~/Documents/Paradox Interactive/Europa Universalis V/docs/modifiers.log` — per-good output modifiers, stockpile capacity modifier
