# Inter-Market Migration Design

## Goal

Bridge the gap between EU5's intra-market migration system and the lack of any cross-market population movement. The game already computes per-location migration attractiveness and uses it to move pops within a market, but this signal stops at market boundaries. Markets with high demand for labor and attractive locations cannot pull pops from other markets — even when those markets are overpopulated and actively trading.

This system adds a thin scripted layer that periodically moves a small number of pops between market centers along existing trade routes. The native intra-market migration system handles all distribution from the center outward. The goal is not to replace or duplicate the existing migration system but to extend its reach across markets.

## Problem

1. **Migration is market-bound.** Pops migrate between locations within a market based on `local_migration_attraction`, but this signal cannot cross market boundaries. A booming colonial market with empty attractive land cannot pull settlers from a crowded European market.

2. **No native cross-market migration exists.** There is no engine-level mechanism for inter-market population movement. The `add_migration` effect exists and can move pops between any two locations, but nothing in vanilla uses it across market boundaries automatically.

3. **Urbanization conflict.** Market centers already receive large migration attraction bonuses from urbanization. Any system that funnels pops through market centers must account for this — the center will naturally hoard incoming pops unless suppressed.

## Design

### Overview

Each month, 1/12 of all markets are processed via `weather_monthly_pulse`. For each market in the current batch:

1. Scan the market's locations to compute **weighted attractiveness** (demand signal) and **population density** (supply signal)
2. Walk the market's **export routes** via `ordered_export` to find the single best migration target among active trade partners
3. Fire `add_migration` between their market centers with a 12-month duration

Migrants follow the ships — they leave on the same routes that carry trade goods outward. Each market is processed exactly once per year, but the work is spread evenly across 12 months. A suppression modifier on the destination center prevents it from hoarding the incoming pops, letting the native system distribute them.

### Batch Assignment

On game start, each market is assigned a batch number 0-11 (round-robin) stored on the market center location. A global variable `sul_migration_current_batch` tracks which batch to process this month. After processing, the counter increments mod 12.

### Phase 1: Location Scan (Per-Market)

For each market in the current batch, iterate its locations via `every_location_in_market`. For each location, compute:

```
location_need = (1 - location_population_percentage) × migration_attraction
```

`migration_attraction` is a location-scope trigger that reads the numeric value directly.

This captures both "this place has room" and "this place is desirable." A full location contributes nothing regardless of attraction. An empty location with zero attraction also contributes nothing.

Accumulate per market:
- Sum of `location_need` across all owned locations in the market
- Count of owned locations
- Sum of `location_population_percentage` across all owned locations

Store the averages in global variable maps:
- `sul_migration_attractiveness[market] = sum(location_need) / count`
- `sul_migration_density[market] = sum(population_percentage) / count`

### Phase 2: Target Selection

For each market, use `ordered_export` to find the highest-scoring trade partner:

```pdx
ordered_export = {
    order_by = sul_migration_target_score
    max = 1
    to_market = {
        save_scope_as = migration_target
    }
}
```

The score is a script value evaluated per export, scoping into `to_market` for the candidate:

```
score = candidate_attractiveness
      × (source_density - target_density)
      × (target_center_attraction / (source_center_attraction + target_center_attraction))
      / distance_to_squared(source_center, target_center)
```

Using `distance_to_squared` (cheaper than `distance_to`, appropriate since we're only ranking) with division means closer markets score higher naturally. No normalization or clamping needed for ranking — the ordered iterator just picks the best.

Multiple exports to the same market (different goods) produce identical scores, so duplicates are harmless — the ordered selection is idempotent over them.

Only one target per market per year. The system nudges the biggest imbalance each cycle and lets the game's own systems smooth the rest.

### Phase 3: Fire Migration

For the chosen source→destination pair, fire `add_migration` between their market centers with a 12-month duration:

```pdx
add_migration = {
    from_location = scope:source_center
    to_location = scope:migration_target_center
    months = 12
    amount = <computed_amount>
}
```

**Base amount:** 2.5% of source market center's location population.

**Modifiers** (all values between 0 and 1, pulling the base down):

| Modifier | Formula | Purpose |
|----------|---------|---------|
| Distance | `clamp(1 - distance_to_squared / max_export_dist_sq, 0, 1)` | Nearby markets get near-full flow, edge-of-range markets get a trickle. Uses squared distance for performance; steeper falloff than linear, which favors nearby markets appropriately. |
| Density differential | `source_density - target_density` | Large gap = strong push. Equalizes as pops move. Self-correcting. |
| Market attractiveness ratio | `target_attractiveness / (source_attractiveness + target_attractiveness)` | High target demand relative to source = stronger pull. Equal attractiveness = half strength. |
| Center attractiveness ratio | `dest_center_attraction / (source_center_attraction + dest_center_attraction)` | Pops resist leaving an attractive center for a worse one. High destination center attraction relative to source = stronger pull. |

**Combined strength:**
```
amount = source_center_pop × 0.025
       × clamp(1 - distance_to_squared / max_export_dist_sq, 0, 1)
       × (source_density - target_density)
       × (target_market_attractiveness / (source + target market_attractiveness))
       × (dest_center_attraction / (source + dest center_attraction))
```

`max_export_dist_sq` is the `distance_to_squared` of the source market's farthest export partner, computed once per yearly cycle. This normalizes distance against each market's actual trade reach rather than a global constant.

All four modifiers are naturally bounded and self-correcting. As pops move, density equalizes and the flow weakens toward zero.

### Phase 4: Center Suppression Modifier

The destination market center receives a dynamic `add_location_modifier` that reduces its `local_migration_attraction` based on how full it is, preventing it from hoarding incoming pops:

```pdx
add_location_modifier = {
    modifier = sul_migration_center_suppression
    months = -1
    size = location_population_percentage
    mode = replace
}
```

Key properties:
- `mode = replace` — recomputed each batch cycle, no stacking
- Scales with `location_population_percentage` — a full center (pop% near 1.0) gets strong suppression, an empty center (pop% near 0) keeps its attraction
- The static modifier defines `local_migration_attraction = -1`, so a size of 0.8 (80% full) reduces attraction by 0.8
- Self-correcting: as the native migration system distributes pops outward and the center empties, suppression weakens and the center becomes attractive again to receive the next batch

## Performance

The key design decisions:
1. **`ordered_export`** instead of O(M²) `can_find_trade_route` — walks existing trade graph
2. **Monthly batching** — 1/12 of markets per month instead of all at once

| Approach | Per-tick cost | Per-check cost |
|----------|--------------|----------------|
| All-pairs yearly | O(M²) pathfinding in one tick | Expensive |
| `ordered_export` monthly | O(M/12 × avg_exports) | Script value arithmetic (cheap) |

A market's export count is naturally bounded by merchant count and trade connections — typically 5-20 routes. For M=300 markets: ~25 markets/month × ~15 exports = ~375 script value evaluations per tick. Negligible.

The location scan is the heavier operation: ~25 markets/month × ~60 locations/market = ~1,500 trigger reads per tick. Still light — comparable to what the specialization batch update already does.

## Data Flow

```
weather_monthly_pulse
    │
    ├─► Version check (re-init if stale)
    │
    └─► sul_migration_monthly_update
            │
            ├─► Select batch: markets where batch == current_batch
            │
            └─► For each market in batch:
                    │
                    ├─► Phase 1: every_location_in_market
                    │       └─► Accumulate (1 - pop%) × migration_attraction
                    │       └─► Store averages in global_variable_map
                    │
                    ├─► Phase 2: ordered_export (max = 1)
                    │       └─► Score = attractiveness × density × center_ratio / distance²
                    │       └─► Save best as migration_target
                    │
                    ├─► Phase 3: add_migration
                    │       └─► from source center → target center, 12 months
                    │       └─► amount = 2.5% × distance × density × attractiveness × center
                    │
                    └─► Phase 4: add_location_modifier on target center
                            └─�� sul_migration_center_suppression, mode = add
            │
            └─► Increment batch counter (mod 12)
```

## Interaction with Existing Systems

### Native intra-market migration (game engine)
This system is purely additive. It deposits pops at market centers; the engine's own `local_migration_attraction` system handles all distribution within the market. The only interference is the suppression modifier on the center, which deliberately manipulates the same attraction value to prevent hoarding.

### Urbanization bonuses
Market centers already have high `local_migration_attraction` from urbanization. The suppression modifier counteracts this for destination centers receiving inter-market migration. Source centers are unaffected — their natural attraction helps retain pops, which is correct behavior (the center attraction ratio in the strength formula already accounts for this).

### Integration system (`sul_integration_*`)
Integration applies `sul_integration_capacity_bonus` based on `(1 - pop/cap)²` to conquered locations. Inter-market migration to these locations (via the center → distribution pipeline) would reduce the bonus as population fills in. This is correct and desirable — conquered empty land attracting settlers who then integrate.

### Market cache (`sul_market_cache_*`)
The migration system reads `migration_attraction` per location but does not modify it (except the center suppression). It stores its own global variable maps (`sul_migration_*`) separate from the market cache maps (`sul_*_pressure`, `sul_trade_spread`, etc.). No conflicts.

### Population density as shared data
The yearly location scan computes `location_population_percentage` per location. This value is also useful for other systems (integration speed already uses it, urbanization may want it). The migration system reads it but does not cache it per-location — it only accumulates the market-level average. If a shared per-location density cache is added later for other consumers, the migration system can read from it instead of re-scanning.

## Engine Reference

### Triggers
| Name | Scope | Returns | Notes |
|------|-------|---------|-------|
| `migration_attraction` | location | value | Numeric migration attractiveness |
| `can_find_trade_route` | country | bool | `can_find_trade_route = { from = <market> to = <market> }` |
| `distance_to_squared` | location | value | Squared crow-flies distance (cheaper than `distance_to`) |
| `distance_to` | location | value | Euclidean distance between locations |

### Effects
| Name | Scope | Notes |
|------|-------|-------|
| `add_migration` | none | `add_migration = { from_location = <loc> to_location = <loc> months = x amount = y }`. Optional: `culture`, `religion`, `type`. |
| `remove_migration` | none | Same parameters as `add_migration` |

### Iterators
| Name | Scope | Target | Notes |
|------|-------|--------|-------|
| `ordered_export` | market | trade | Iterate exports with `order_by`, `max`, `limit` |
| `every_export` | market | trade | All exports from a market |
| `every_import` | market | trade | All imports to a market |
| `any_trade` | country | trade | All trades a country participates in |

### Trade Scope Transitions
| Name | From | To | Notes |
|------|------|----|-------|
| `from_market` | trade | market | Source market of the trade |
| `to_market` | trade | market | Destination market of the trade |
| `traded_goods` | trade | goods | Good being traded |
| `capacity_market` | trade | market | Market providing capacity |

### Math Operations
| Name | Notes |
|------|-------|
| `pow = x` | Exponentiation. `pow = 0.5` for square root, `pow = 2` for squaring. |
| `distance_to_squared` | Preferred over `distance_to` when only comparing/ranking (avoids sqrt). |

## Open Questions

1. **~~Performance of the location scan.~~** Resolved by monthly batching — ~1,500 trigger reads per tick instead of ~20k.

2. **Suppression modifier calibration.** Too strong and the center becomes unattractive to its own market's pops, stalling the pipeline. Too weak and pops pile up. The scaling factor needs empirical tuning. Start conservative (low suppression) and increase.

3. **Market center changes mid-cycle.** If a market center relocates during the 12-month migration period, the `add_migration` is firing toward the old center. The suppression modifier is on the old center. Minor edge case — the yearly update corrects it on the next cycle.

4. **One target per market per year.** Deliberate simplification. A market surrounded by three underpopulated markets only feeds the neediest one each year. Over multiple years the rotation handles all three. If this feels unresponsive, consider allowing 2-3 targets with flow split proportionally.

5. **Markets without exports.** A market with no export routes has no migration candidates. This is thematically correct — isolated markets don't send settlers. As trade routes develop, migration follows.

6. **Minimum density threshold for source markets.** Should a market below some minimum density even export pops? The density differential naturally prevents this (low density = low or negative differential = no flow), but an explicit floor might be cleaner.

7. **Cultural composition of migrants.** `add_migration` can specify a culture. Options: source center's majority culture, random culture from source market, or omit the parameter and let the engine default. Minor detail for v1.

## File Structure

```
in_game/common/
├── on_action/
│   ├── sul_hardcoded.txt                  # dispatcher hooks (on_game_start + weather_monthly_pulse)
│   └── sul_migration_on_actions.txt       # init, version check, monthly pulse handlers
├── scripted_effects/
│   └── sul_migration_effects.txt          # initialize, monthly update, process, find target, fire
└── script_values/
    └── sul_migration_values.txt           # target score, distance/density/attractiveness/center ratios, amount

main_menu/common/
├── static_modifiers/
│   └── sul_migration_modifiers.txt        # center suppression modifier definition
└── script_values/
    └── sul_versions.txt                   # sul_migration_version_value (added)
```
