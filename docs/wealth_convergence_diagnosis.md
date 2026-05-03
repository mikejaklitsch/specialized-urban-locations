# Wealth Convergence Diagnosis

## Symptom
Every location: identical asset values + distribution from game start through 500 years. Zero change in both actual (assets) and potential (target).

---

## Data Architecture

Two parallel storage layers exist for wealth data:

| Layer | Written by | Read by |
|-------|-----------|---------|
| **Location variables** (`sul_wealth_nobles`, `sul_wealth_target_nobles`, etc.) | Convergence: `set_variable` / `change_variable` | Nothing in GUI — only used as intermediaries |
| **Variable maps** (`sul_estate_assets`, `sul_estate_targets`) | `sul_wealth_write_maps`: `add_to_variable_map` | GUI: `variable_map(sul_estate_assets\|estate_type:X)` |

The GUI **never reads the location variables directly** — it reads exclusively from the variable maps. The variable maps are written by `sul_wealth_write_maps`, called at the end of `sul_location_converge_wealth`.

---

## Monthly Write Chain

```
sul_economy.0 (country_event, monthly)
└── sul_monthly_location_pass (country scope)
    └── every_owned_location:
        └── sul_location_converge_wealth (location scope)
            │
            ├── [COMPUTE] target = (local_power / nat_power_prev) × estate_gold
            │     All three inputs sourced fresh:
            │       local_power         ← engine live
            │       nat_power_prev      ← snapshotted from last month's accumulation
            │       estate_gold         ← cached from engine at top of pass
            │
            ├── [WRITE] var:sul_wealth_X += (target - wealth) × 0.025   ← location variable
            ├── [WRITE] var:sul_wealth_target_X = target                ← location variable
            │
            └── sul_wealth_write_maps
                  ├── add_to_variable_map: sul_estate_assets[X]  = var:sul_wealth_X
                  └── add_to_variable_map: sul_estate_targets[X] = var:sul_wealth_target_X
```

## GUI Read Chain

```
LocationView.GetLocation.MakeScope.ScriptValue('sul_wealth_total')
└── sul_wealth_total (script_value, location scope)
    └── if has_variable = sul_wealth_nobles:
            add = "variable_map(sul_estate_assets|estate_type:nobles_estate)"
```

---

## Verified Correct

- **Target formula inputs**: all three are freshly sourced each month (engine calls + snapshotted/cached country vars)
- **Convergence math**: `delta = (target - wealth) × 0.025`, applied via `change_variable`
- **No self-reference**: target formula reads (local_power, nat_power_prev, estate_gold) — none of which are wealth variables
- **No duplicate writers**: `sul_wealth_nobles` is only modified by seed and convergence
- **Event fires**: `sul_economy.0` trigger is `is_ai = no, is_real_country = yes, has_variable = sul_budget_pressure_nobles` — all satisfied after init

## Remaining Suspects

### 1. `add_to_variable_map` may not overwrite existing keys

The seed writes map entries via `sul_wealth_write_maps`. Monthly convergence writes the same map entries via the same function. If `add_to_variable_map` appends rather than overwrites, the GUI reads the original seed entry forever.

**Evidence against**: The demand system uses `add_to_variable_map` the same way (WPP maps written monthly by `sul_update_location_wpp`, read by `variable_map()` in goods_demand script values), and demand IS dynamic.

**Evidence for**: The demand maps use `pop_type:X` keys while wealth maps use `estate_type:X` keys. Different key types could behave differently.

### 2. GUI `variable_map()` reads are stale

Script values are re-evaluated each GUI frame. But `variable_map()` inside a script_value might cache its result per-frame or per-session, rather than reading the live map. If the engine optimizes script_value resolution by caching `variable_map()` lookups, the GUI would show frozen values even though the underlying map is updated.

**Evidence against**: Demand script values use `variable_map()` identically and produce dynamic results.

### 3. The convergence is correct but the GUI reads the wrong variable

The GUI guard checks `has_variable = sul_wealth_nobles` (a location variable). It then reads `variable_map(sul_estate_assets|estate_type:nobles_estate)`. These are semantically linked but physically separate. If one updates and the other doesn't, the displayed value is frozen.

---

## Proposed Diagnostic Test

**Bypass the maps entirely**: Change the GUI script values to read raw variables instead of variable maps.

Replace:
```pdx
sul_map_asset_nobles = {
    value = 0
    if = { limit = { has_variable = sul_wealth_nobles }
        add = "variable_map(sul_estate_assets|estate_type:nobles_estate)"
    }
}
```

With:
```pdx
sul_map_asset_nobles = {
    value = 0
    if = { limit = { has_variable = sul_wealth_nobles }
        add = var:sul_wealth_nobles
    }
}
```

**If assets start moving**: the bug is in the variable map layer (either `add_to_variable_map` doesn't overwrite, or `variable_map()` reads are cached).

**If assets still don't move**: the bug is in the convergence itself — `var:sul_wealth_nobles` isn't actually changing, meaning the delta is truly zero every month.

Either way, this test identifies which half of the system to investigate.
