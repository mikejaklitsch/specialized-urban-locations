# Minting System Overhaul: Monetization Model

## Summary

Replace the flat liquidity premium with a derived **monetization** metric that ties minting profitability to the real economy. Unify the inflation formula so income and inflation scale proportionally, with a Gresham's Law penalty on debasement that worsens with accumulated inflation.

### Core Changes
- **Rename** `sul_minting_liquidity` → `sul_minting_monetization` everywhere
- **Remove** static base 1.0 from `country_base_values`
- **Add** dynamic base monetization from two sources:
  - Wages: `total_wages / (country_economical_base × 4)` — domestic monetary circulation
  - Trade: `max(0, monthly_trade_income / monthly_income_trade_and_tax)` — commercial activity share
- **Add** building-sourced monetization: counting_house (+0.05), minting_office (+0.10)
- **Unify** inflation formula: single scalar using total efficiency + Gresham debasement penalty
- **Rewrite** AI debasement: monthly evaluation with ±0.2 inertia
- **Fix** barter exchange: add `provisions_used_for_minting = yes`
- **Rebalance** all static monetization sources against the new lower baseline

---

## Phase 1: Rename `sul_minting_liquidity` → `sul_minting_monetization`

Mechanical find-and-replace across all files. No logic changes.

### Modifier Type Definition
**File:** `main_menu/common/modifier_type_definitions/sul_minting_modifier_types.txt`
- Rename `sul_minting_liquidity` → `sul_minting_monetization`

### Modifier Icons
**File:** `main_menu/common/modifier_icons/sul_minting_modifier_icons.txt`
- Rename `sul_minting_liquidity` → `sul_minting_monetization`

### Base Values
**File:** `in_game/common/auto_modifiers/sul_base_values.txt`
- Rename `sul_minting_liquidity = 1.0` → `sul_minting_monetization = 1.0`
- (Phase 2 will remove this line entirely; rename first for clean diff)

### Coin Laws
**File:** `in_game/common/laws/sul_minting_coin_laws.txt`
- Replace all `sul_minting_liquidity` → `sul_minting_monetization` (7 occurrences across gold_and_silver, gold_coins, silver_coins, copper_coins, bullion_coins, barter_exchange, hanseatic_coins)

### Country Laws
**File:** `in_game/common/laws/sul_minting_country_laws.txt`
- Replace `sul_minting_liquidity` → `sul_minting_monetization` (2 occurrences: kor_metal_coinage, ministry_of_revenue)

### Precious Metal Distribution
**File:** `in_game/common/laws/sul_minting_precious_metals.txt`
- Replace `sul_minting_liquidity` → `sul_minting_monetization` (2 occurrences: gold_export_ban, unlimited_gold_export)

### Advances
**File:** `in_game/common/advances/sul_minting_advances.txt`
- Replace all `sul_minting_liquidity` → `sul_minting_monetization` (18 occurrences across all INJECT blocks)

### Estate Privileges
**File:** `in_game/common/estate_privileges/sul_minting_burghers.txt`
- Replace all `sul_minting_liquidity` → `sul_minting_monetization` (4 occurrences)

### Religious Aspects
**File:** `in_game/common/religious_aspects/sul_minting_aspects.txt`
- Replace `sul_minting_liquidity` → `sul_minting_monetization` (1 occurrence)

### Government Reforms
**File:** `in_game/common/government_reforms/sul_minting_reforms.txt`
- Replace `sul_minting_liquidity` → `sul_minting_monetization` (1 occurrence)

### Event Buildings
**File:** `in_game/common/building_types/sul_minting_buildings.txt`
- Replace all `sul_minting_liquidity` → `sul_minting_monetization` (3 occurrences: wisselbank, usa_national_bank, usa_national_mint)

### Vanilla Static Modifier Injects
**File:** `main_menu/common/static_modifiers/sul_minting_vanilla_injects.txt`
- Replace all `sul_minting_liquidity` → `sul_minting_monetization` (5 occurrences)

### Script Values
**File:** `in_game/common/script_values/sul_minting_efficiency.txt`
- Replace `modifier:sul_minting_liquidity` → `modifier:sul_minting_monetization` (1 occurrence in `sul_minting_mint_liquidity_value`)
- Rename script value `sul_minting_mint_liquidity_value` → `sul_minting_mint_monetization_value`
- Update any references to this script value name elsewhere in the file

### Localization
**File:** `main_menu/localization/english/sul_minting_l_english.yml`
- Rename all keys: `MODIFIER_TYPE_NAME_sul_minting_liquidity`, `MODIFIER_TYPE_DESC_sul_minting_liquidity`, `modifier_sul_minting_liquidity`, `modifier_sul_minting_liquidity_desc`
- Update display text from "Liquidity" / "Minting Liquidity" → "Monetization" / "Minting Monetization"
- Rename game concept keys: `game_concept_sul_minting_mint_liquidity`, `game_concept_mint_liquidity`, `game_concept_liquidity_value`
- Update all descriptive text that says "liquidity" to say "monetization" and update the concept descriptions (base 100% is no longer true — it's now derived from the economy)
- Update `TGS_MINT_UNPROFITABLE_NOTE` and other tooltip references

### Game Concepts
**File:** `main_menu/common/game_concepts/sul_minting_game_concepts.txt`
- Rename `sul_minting_mint_liquidity` concept → `sul_minting_mint_monetization` (or similar)
- Update aliases

---

## Phase 2: Base Monetization

### Remove Static Base
**File:** `in_game/common/auto_modifiers/sul_base_values.txt`
- Remove the `sul_minting_monetization = 1.0` line entirely (was renamed in Phase 1)

### New Script Value
**File:** `in_game/common/script_values/sul_minting_efficiency.txt`
- Add new script value that reads total wages (sum of all estate monthly wages) and divides by economic base:

```pdx
sul_minting_monetization_base = {
    value = 0
    if = {
        limit = { has_variable = sul_monthly_wages_nobles }
        add = var:sul_monthly_wages_nobles
    }
    if = {
        limit = { has_variable = sul_monthly_wages_clergy }
        add = var:sul_monthly_wages_clergy
    }
    if = {
        limit = { has_variable = sul_monthly_wages_burghers }
        add = var:sul_monthly_wages_burghers
    }
    if = {
        limit = { has_variable = sul_monthly_wages_peasants }
        add = var:sul_monthly_wages_peasants
    }
    divide = {
        value = country_economical_base
        multiply = 4
        min = 1
    }
}
```

These variables are already accumulated per-country by the wage system in `sul_gdp_update.txt` (player monthly, AI yearly). The auto_modifier reads the latest cached values. The ÷4 keeps the result in a sensible fraction — if wages ≈ economic_base, the base monetization is ~0.25.

- Add second script value for trade-based monetization (trade share of total income):

```pdx
sul_minting_trade_monetization_value = {
    value = monthly_trade_income
    divide = {
        value = monthly_income_trade_and_tax
        min = 1
    }
    min = 0
}
```

Gives the fraction of income from trade (0.0 to ~0.5). Clamped to 0 when trade income is zero or negative. Nations with no trade contribute nothing from this component; nations with high trade share get a significant boost. Range ~0.05–0.33 for typical nations, higher for trade empires.

Together, the two components capture both domestic monetary circulation (wages) and commercial activity (trade share). They're additive via separate auto_modifiers on the same `sul_minting_monetization` modifier.

### New Auto Modifiers
**File:** `in_game/common/auto_modifiers/sul_minting_country.txt`
- Add two auto_modifiers for base monetization. Both apply to ALL countries (player and AI) so that `modifier:sul_minting_monetization` returns the correct accumulated value for minting calculations:

```pdx
sul_minting_wage_monetization = {
    scales_with = sul_minting_monetization_base

    sul_minting_monetization = 1.0
}

sul_minting_trade_monetization = {
    scales_with = sul_minting_trade_monetization_value

    sul_minting_monetization = 1.0
}
```

No `potential_trigger` on either — must be universal. Wages reads 4 cached variables + 1 engine value; trade reads 2 engine values. Both cheap enough for all countries.

### Building INJECTs
**File:** `in_game/common/building_types/sul_minting_buildings.txt`
- Add INJECT blocks for counting_house and minting_office:

```pdx
INJECT:counting_house = {
    country_modifier = { sul_minting_monetization = 0.05 }
}

INJECT:minting_office = {
    country_modifier = { sul_minting_monetization = 0.10 }
}
```

These stack per building instance (one per location). A nation with 10 counting houses gets +0.50 monetization.

---

## Phase 3: Unified Inflation Formula

### Design

Replace the three-part inflation system:
- ~~`sul_minting_debasement_inflation` auto_modifier (additive debasement inflation)~~
- ~~`sul_minting_inflation_scaling` auto_modifier (scales by real_scalar - 1)~~
- ~~`sul_minting_real_efficiency` script values~~

With a single unified auto_modifier:
- `sul_minting_inflation_scaling` scales by `(inflation_scalar - 1)` where inflation_scalar uses total efficiency with Gresham debasement penalty

**Income formula** (unchanged):
```
E = [target × (1+M) × (1+d) - market_cost] / 25 - 1
```

**Inflation formula** (new):
```
debasement_penalty = 2 × (1 + inflation)
inflation_face_value = target × (1+M) × (1 + debasement_penalty × d)
inflation_scalar = (inflation_face_value - market_cost) / 25
total_minting_inflation = vanilla_inflation × inflation_scalar
```

The engine adds `vanilla_inflation` natively. Our auto_modifier adds `vanilla_inflation × (inflation_scalar - 1)`. Sum = `vanilla_inflation × inflation_scalar`.

Properties:
- At d=0: inflation_scalar = real_profit/25 = same as income scalar. Income and inflation are perfectly proportional. Monetization cancels in the ratio.
- At d>0: debasement income uses (1+d), inflation uses (1 + 2×(1+inflation)×d). Each marginal debasement ducat costs exactly 2× the inflation of a legitimate ducat at zero inflation, worsening as inflation accumulates (Gresham's Law).
- At E<0 (unprofitable minting): inflation_scalar < 1, our modifier is negative, reducing vanilla inflation. Protects AI from maxing slider for pennies.

### New Script Values
**File:** `in_game/common/script_values/sul_minting_efficiency.txt`

Add:
```pdx
sul_minting_debasement_inflation_penalty = {
    value = 2
    multiply = { value = 1 add = inflation }
}

sul_minting_inflation_output_value = {
    value = sul_minting_mint_output_value
    multiply = {
        value = 1
        if = {
            limit = { has_variable = sul_minting_debasement_level }
            add = {
                value = var:sul_minting_debasement_level
                multiply = sul_minting_debasement_inflation_penalty
            }
        }
    }
}

sul_minting_inflation_scalar = {
    value = sul_minting_inflation_output_value
    subtract = var:sul_minting_market_cost
    divide = @sul_minting_vanilla_rate
    min = 0
}

sul_minting_unified_inflation_adjustment = {
    value = sul_minting_vanilla_minting_inflation
    multiply = { value = sul_minting_inflation_scalar subtract = 1 }
}
```

### Remove Old Script Values
**File:** `in_game/common/script_values/sul_minting_efficiency.txt`

Remove these script values (or comment out if needed for tooltip reference):
- `sul_minting_real_efficiency_from_cached_cost`
- `sul_minting_cached_real_efficiency`
- `sul_minting_real_minting_scalar`
- `sul_minting_inflation_adjustment` (replaced by `sul_minting_unified_inflation_adjustment`)
- `sul_minting_total_minting_inflation` (replaced by `vanilla × inflation_scalar`)

### Update Auto Modifiers
**File:** `in_game/common/auto_modifiers/sul_minting_country.txt`

**Remove:**
```pdx
sul_minting_debasement_inflation = { ... }
```

**Replace** `sul_minting_inflation_scaling`:
```pdx
sul_minting_inflation_scaling = {
    potential_trigger = { is_ai = no }

    scales_with = sul_minting_unified_inflation_adjustment

    monthly_inflation = 1.0
}
```

### Update AI Inflation Sizing
**File:** `in_game/common/script_values/sul_minting_efficiency.txt`

Replace `sul_minting_ai_inflation_size`:
```pdx
sul_minting_ai_inflation_size = {
    value = sul_minting_unified_inflation_adjustment

    if = {
        limit = {
            has_variable = sul_minting_rebasement_level
            var:sul_minting_rebasement_level > 0
            inflation > 0
        }

        add = sul_minting_rebasement_deflation_effect
    }
}
```

Note: For AI, `sul_minting_unified_inflation_adjustment` reads `var:sul_minting_market_cost` (cached yearly) and `modifier:sul_minting_monetization` (from auto_modifier, live). The debasement penalty reads `inflation` (live) and `var:sul_minting_debasement_level` (updated on AI debasement action). This means AI inflation updates monthly with live inflation values even though market cost is cached yearly. This is correct — the Gresham penalty should respond to current inflation.

### Update AI Monthly Pulse
**File:** `in_game/common/on_action/sul_minting_on_actions.txt`

In `sul_minting_monthly_update`, the AI inflation block: remove the separate debasement inflation handling. The unified `sul_minting_ai_inflation_size` now handles everything. Simplify to:

```pdx
if = {
    limit = { is_ai = yes }

    # First tick: apply minting modifier
    if = {
        limit = { has_variable = sul_minting_first_month_tick }
        add_country_modifier = {
            modifier = sul_minting_ai_minting
            days = -1
            mode = replace
            size = sul_minting_ai_minting_size
        }
    }

    # Inflation: unified adjustment + rebasement deflation
    add_country_modifier = {
        modifier = sul_minting_ai_inflation
        days = -1
        mode = replace
        size = sul_minting_ai_inflation_size
    }

    # Rebasement cost (unchanged)
    if = {
        limit = {
            has_variable = sul_minting_rebasement_level
            var:sul_minting_rebasement_level > 0
            inflation > 0
        }
        add_country_modifier = {
            modifier = sul_minting_ai_rebasement
            days = -1
            mode = replace
        }
        change_country_modifier_size = {
            modifier = sul_minting_ai_rebasement
            value = sul_minting_ai_rebasement_size
        }
    }
    else = { remove_country_modifier = sul_minting_ai_rebasement }
}
```

### Remove Cached Real Efficiency from Effects
**File:** `in_game/common/scripted_effects/sul_minting_effects.txt`

In `sul_minting_initialize_country`:
- Remove `sul_minting_init_variable = { name = sul_minting_real_minting_efficiency value = 0 }`

In `sul_minting_update_price_cache`:
- Remove the `set_variable = { name = sul_minting_real_minting_efficiency ... }` line

---

## Phase 4: AI Debasement Rewrite

### Change to Monthly with Inertia
**File:** `in_game/common/generic_actions/sul_minting_debasement.txt`

Change `ai_tick_frequency = 6` → `ai_tick_frequency = 1` (monthly).

Replace the effect block's jump-to-target logic with inertia-based movement:

```pdx
effect = {
    scope:actor = {
        set_variable = {
            name = sul_minting_ai_debasement_target_temp
            value = sul_minting_ai_debasement_target
        }

        # Calculate desired change from current position
        # Positive target = wants to debase, negative = wants to rebase

        if = {
            limit = { var:sul_minting_ai_debasement_target_temp > 0 }

            # Move debasement toward target, capped at ±0.2/month
            set_local_variable = {
                name = sul_minting_desired_delta
                value = var:sul_minting_ai_debasement_target_temp
            }
            change_local_variable = {
                name = sul_minting_desired_delta
                subtract = var:sul_minting_debasement_level
            }
            clamp_local_variable = { name = sul_minting_desired_delta min = -0.2 max = 0.2 }

            change_variable = {
                name = sul_minting_debasement_level
                add = local_var:sul_minting_desired_delta
            }
            clamp_variable = { name = sul_minting_debasement_level min = 0 max = 2.0 }

            # Clear rebasement when debasing
            if = {
                limit = { var:sul_minting_debasement_level > 0 }
                set_variable = { name = sul_minting_rebasement_level value = 0 }
            }
        }
        else_if = {
            limit = {
                var:sul_minting_ai_debasement_target_temp < 0
                inflation > 0.03
                num_loans = 0
                monthly_balance > 0
            }

            # Move rebasement toward |target|, capped at ±0.2/month
            set_local_variable = {
                name = sul_minting_desired_rebase
                value = var:sul_minting_ai_debasement_target_temp
            }
            change_local_variable = {
                name = sul_minting_desired_rebase
                multiply = -1
            }
            set_local_variable = {
                name = sul_minting_desired_delta
                value = local_var:sul_minting_desired_rebase
            }
            change_local_variable = {
                name = sul_minting_desired_delta
                subtract = var:sul_minting_rebasement_level
            }
            clamp_local_variable = { name = sul_minting_desired_delta min = -0.2 max = 0.2 }

            change_variable = {
                name = sul_minting_rebasement_level
                add = local_var:sul_minting_desired_delta
            }
            clamp_variable = { name = sul_minting_rebasement_level min = 0 max = 2.0 }

            # Clear debasement when rebasing
            if = {
                limit = { var:sul_minting_rebasement_level > 0 }
                set_variable = { name = sul_minting_debasement_level value = 0 }
            }
        }
        else = {
            # Target near zero, no rebase conditions: wind both down
            if = {
                limit = { var:sul_minting_debasement_level > 0 }
                change_variable = { name = sul_minting_debasement_level add = -0.2 }
                clamp_variable = { name = sul_minting_debasement_level min = 0 max = 2.0 }
            }
            if = {
                limit = { var:sul_minting_rebasement_level > 0 }
                change_variable = { name = sul_minting_rebasement_level add = -0.2 }
                clamp_variable = { name = sul_minting_rebasement_level min = 0 max = 2.0 }
            }
        }

        remove_variable = sul_minting_ai_debasement_target_temp

        # Recompute E from new debasement level
        set_variable = {
            name = sul_minting_efficiency
            value = sul_minting_efficiency_from_cached_cost
        }

        add_country_modifier = {
            modifier = sul_minting_ai_minting
            days = -1
            mode = replace
            size = sul_minting_ai_minting_size
        }
    }
}
```

### Update AI Will Do
The `ai_will_do` block should fire more broadly since the action is now responsible for gradual wind-down. Add a condition so it fires whenever any level is non-zero OR financial conditions suggest action:

```pdx
ai_will_do = {
    if = {
        limit = {
            scope:actor = {
                OR = {
                    NOT = { var:sul_minting_debasement_level = 0 }
                    NOT = { var:sul_minting_rebasement_level = 0 }
                    num_loans >= 1
                    monthly_balance < 0
                    AND = {
                        inflation > 0.03
                        num_loans = 0
                        monthly_balance > 0
                    }
                }
            }
        }

        add = { value = 100 }
    }
}
```

---

## Phase 5: Barter Fix

**File:** `in_game/common/laws/sul_minting_coin_laws.txt`

In the `barter_exchange` block, add `provisions_used_for_minting = yes` to the country_modifier:

```pdx
barter_exchange = {
    ...
    country_modifier = {
        provisions_used_for_minting = yes
        minting_inflation_threshold = 0.01
        sul_minting_monetization = 0.05
    }
    ...
}
```

Note: provisions default_price = 2.4. At low monetization, barter nations get near-zero minting income. This is intentional — grain-as-currency economies don't have functional mints.

---

## Phase 6: Modifier Rebalancing

With the static 1.0 base removed, all existing monetization sources now operate against a much lower baseline (trade-derived, roughly 0.05-0.33). Each +0.05 or +0.10 is proportionally much more impactful. Review and adjust:

### Coin Laws (`sul_minting_coin_laws.txt`)

| Law | Current | New | Reasoning |
|---|---|---|---|
| gold_and_silver_coins | 0.15 | 0.15 | Strong bimetallic system, keep as premium |
| gold_coins | 0.05 | 0.05 | Fine |
| silver_coins | 0.05 | 0.05 | Fine |
| copper_coins | **-0.125** | **0.02** | Copper is still money. Negative monetization makes no sense — it should be the worst metal coinage but still positive |
| bullion_coins | 0.10 | 0.10 | Fine |
| barter_exchange | 0.05 | 0.05 | Fine (provisions added in Phase 5) |
| hanseatic_coins | 0.05 | 0.05 | Fine |

### Precious Metal Distribution (`sul_minting_precious_metals.txt`)

| Option | Current | New | Reasoning |
|---|---|---|---|
| gold_export_ban | +0.33 | **+0.20** | Keeping metal in-country boosts monetization but +0.33 is disproportionate against a 0.1-0.3 base. Still the single largest law source. |
| unlimited_gold_export | -0.33 | **-0.15** | Exporting metal reduces monetization but shouldn't negate it. At base 0.15, the old -0.33 would drive monetization negative. |

### Advances (`sul_minting_advances.txt`)

Threshold-derived sources (0.05 each): **Keep all at 0.05.** These are small incremental improvements from institutional development, appropriate against the new baseline.

Income-derived sources: **Keep current values.** These range from 0.05 to 0.25 and represent significant investments (banking, national banks, regional coinage standardization). Their magnitude relative to the new baseline makes them meaningful progression markers:
- 0.05: minor advances (georgian_numismatics)
- 0.10: standard banking/coinage (banking_advance, national_bank, bohemian_thaler, etc.)
- 0.15: regional specialization (bng_rupees, nov_minting_of_novgorodka)
- 0.20: major reforms (bavarian_coinage, usa_national_bank, usa_national_mint)
- 0.25: exceptional (mint_of_the_gulf, coins_in_our_name)

### Estate Privileges (`sul_minting_burghers.txt`)

| Privilege | Current | New | Reasoning |
|---|---|---|---|
| control_over_the_coinage | 0.05 | 0.05 | Fine |
| fra_marcel_great_ordinance | 0.05 | 0.05 | Fine |
| fra_marcel_compromise | 0.05 | 0.05 | Fine |
| bra_kreditwerk | **0.25** | **0.15** | Was tuned against base 1.0. At 0.25 it's equivalent to a top-tier advance from a single privilege. Reduce to 0.15. |

### Event Buildings (`sul_minting_buildings.txt`)

| Building | Current | New | Reasoning |
|---|---|---|---|
| wisselbank | 0.10 | 0.10 | Bank of Amsterdam, appropriate for a unique wonder |
| usa_national_bank | **0.20** | **0.15** | Was tuned against base 1.0. Still strong but not dominant. |
| usa_national_mint | **0.20** | **0.15** | Same reasoning. |

### Vanilla Static Modifier Injects (`sul_minting_vanilla_injects.txt`)

| Modifier | Current | New | Reasoning |
|---|---|---|---|
| exploiting_the_franc_coinage | 0.05 | 0.05 | Fine |
| minting_of_the_franc | 0.00 | 0.00 | Intentional zero (replaces minting_income_factor = 0) |
| cas_spanish_dollar_not_adopted | 0.00 | 0.00 | Same |
| strengthened_ministry_of_revenue | 0.15 | 0.15 | Fine |
| coins_in_our_name_modifier | 0.25 | **0.20** | Reduce slightly for consistency |
| nov_minting_of_novgorodka | 0.15 | 0.15 | Fine |

### Country Laws (`sul_minting_country_laws.txt`)

| Law | Current | New | Reasoning |
|---|---|---|---|
| kor_metal_coinage | 0.05 | 0.05 | Fine |
| ministry_of_revenue | 0.05 | 0.05 | Fine |

### Religious Aspects (`sul_minting_aspects.txt`)
- usury_allowed: 0.05 → **keep 0.05**

### Government Reforms (`sul_minting_reforms.txt`)
- control_of_the_mahdali_coinage: 0.10 → **keep 0.10**

---

## Phase 7: Version Bump and Deploy

### Version Bump
**File:** `main_menu/common/script_values/sul_versions.txt`
- Bump `sul_minting_version_value` by 1 to force re-initialization on existing saves

### Update CONTROL_FLOW.md
- Document new variables: none added (we're removing `sul_minting_real_minting_efficiency`)
- Document renamed modifier: `sul_minting_liquidity` → `sul_minting_monetization`
- Document new auto_modifier: `sul_minting_base_monetization`
- Document removed auto_modifier: `sul_minting_debasement_inflation`
- Document changed inflation formula
- Document AI debasement inertia change

### Update CLAUDE.md
- Update the Minting / Gold Standard section to reflect new modifier name and formula changes
- Remove references to `real_efficiency`
- Add note about Gresham penalty

### Update Design Doc
**File:** `docs/complacency_coupling_plan.md` or create new `docs/minting_monetization_design.md`
- Document the full monetization model for future reference

### Deploy
```bash
python "/mnt/c/Users/Mjaklitsch/Documents/Paradox Interactive/Europa Universalis V/mod/tools/deploy.py" sul
```

---

## Testing Checklist

- [ ] Game loads without errors (check error.log with `eu5-logs error -p -f sul_minting`)
- [ ] New game: monetization auto_modifier appears on country tooltips
- [ ] Coin law change triggers goods list rebuild + monetization recalculation
- [ ] Debasement slider increases income via (1+d) multiplier
- [ ] Inflation scales proportionally: at d=0, income/inflation ratio is constant regardless of monetization level
- [ ] Gresham penalty: same debasement level causes more inflation at higher existing inflation
- [ ] Rebasement still works (deflation formula unchanged)
- [ ] AI gradually ramps debasement over multiple months (inertia), not instant jump
- [ ] AI winds down debasement when conditions improve
- [ ] Barter nations show provisions demand when minting
- [ ] Counting house and minting office provide monetization (check modifier tooltip)
- [ ] Copper coin law gives small positive monetization
- [ ] Nation with zero trade income still has monetization from laws/buildings/advances
- [ ] `modifier:sul_minting_monetization` reads correctly for both player and AI

## Reference: Expected Monetization Ranges

These are approximate, for sanity-checking in-game values:

| Stage | Wages | Trade | Laws | Advances | Buildings | Total M |
|---|---|---|---|---|---|---|
| Early game (1337) | 0.05 | 0.05 | 0.05 (gold) | 0.00 | 0.00 | ~0.15 |
| Early-mid (1400) | 0.10 | 0.08 | 0.15 (gold+silver) | 0.10 | 0.05 (1 CH) | ~0.48 |
| Mid game (1500) | 0.18 | 0.15 | 0.15 | 0.30 | 0.15 (3 CH) | ~0.93 |
| Late game (1650+) | 0.25 | 0.20 | 0.15 | 0.60 | 0.55 (5 CH + 3 MO) | ~1.75 |
| Trade empire peak | 0.30 | 0.35 | 0.15 | 0.70 | 0.80 (6 CH + 5 MO) + event | ~2.52 |

With post-patch gold+silver (target=14), E at these levels:
- M=0.08: E = (14×1.08 - 14)/25 - 1 = -0.955 → near zero income
- M=0.38: E = (14×1.38 - 14)/25 - 1 = -0.787 → modest income
- M=0.75: E = (14×1.75 - 14)/25 - 1 = -0.58 → growing income
- M=1.55: E = (14×2.55 - 14)/25 - 1 = -0.132 → approaching vanilla parity
- M=2.20: E = (14×3.20 - 14)/25 - 1 = +0.232 → above vanilla

Minting income starts very low and grows with economic development. This is the intended progression — medieval minting barely covers costs, modern financial systems make it profitable.
