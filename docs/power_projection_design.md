# Power Projection — Design Document

## Intent

Power projection governs a country's ability to act internally and externally. A decentralized nation — many subjects, weak control, cultural/religious friction — cannot project authority. A centralized one can. This makes early expansion harder but provides clear paths out through consolidation.

**France at 1337** is the canonical calibration scenario: overwhelmed by appanages, structurally unable to project power until consolidated.

## Architecture

### Single Unified Auto-Modifier

All PP-scaling effects live in one `REPLACE:power_projection` block (`sul_projection_country.txt`). The engine multiplies each coefficient by the signed PP value, so positive PP produces benefits and negative PP produces penalties automatically. No split into positive/negative blocks — a single set of coefficients covers the full range. Clamped to [-200, 200].

### Structural Drag Layer

Separate auto_modifiers that WRITE power_projection from country state:

| Drag | Scales With | Coefficient | At Worst |
|------|-------------|-------------|----------|
| Control | `(control_pop / total_pop) - 1` | ×50 | -50 PP |
| Culture | `(accepted_pop / total_pop) - 1` | ×25 | -25 PP |
| Religion | `(religion_pop / total_pop) - 1` | ×25 | -25 PP |
| Diplomacy | `used_diplo / total_diplo` | ×-50 | -50 PP |
| Rank | county=5, duchy=10, kingdom=15 | ×1 | +15 PP |

### Vanilla Static Modifier Injects

| Source | PP Contribution |
|--------|-----------------|
| Stability (×0.01) | +25 at stability 100 |
| Prestige (×0.01) | +25 at prestige 100 |
| Num locations (÷10) | -0.25 per 10 locations |
| Regular army size | +0.5 per unit |
| Regular navy size | +0.5 per unit |
| Is subject | -10 flat |
| Ruler military skill | +0.25 per point |

## Scale Layer Effects (at PP = +200)

| Category | Effect | Value |
|----------|--------|-------|
| Subjects | subject_loyalty | +50 |
| Integration | global_integration_speed_modifier | +100% |
| Assimilation | global_pop_assimilation_speed_modifier | +100% |
| Conversion | global_pop_conversion_speed_modifier | +100% |
| War cost | global_war_score_cost | -50% |
| Annexation | diplomatic_annexation_cost | -50% |
| AE | antagonism_taking_land_giving_modifier | -100% |
| Trade | sul_trade_maintenance_efficiency | +25% |
| Settlement | settle_country_cost_modifier | -50% |
| CB creation | casus_belli_creation_speed_modifier | +50% |
| Capital reach | global_distance_from_capital_speed_propagation | +50% |
| Military | levy_recovery_modifier, global_levy_size_modifier | +200% each |
| Stability | stability_decay | -1% |
| Estates | global_estate_target_satisfaction | -20% |
| Estates | global_estate_power | -50% |

### Complacency Coupling

`monthly_complacency = 0.0015` — at PP 200, generates +0.3 complacency/mo. At PP -200, drains -0.3/mo. This is the rise-and-fall cycle: success breeds complacency, which erodes projection via the complacency_impact auto_modifier's `power_projection = -100` drag.

## Gate Layer

Binary triggers based on PP comparison between overlord and subject:

| Gate | Condition | Effect |
|------|-----------|--------|
| Forced religious conversion | Overlord PP < subject PP | Disabled |
| Forced cultural conversion | Overlord PP < subject PP | Disabled |

## Calibration

- Per-lever coefficients are conservative — eight levers stack, so each is modest individually.
- Positive sources are deliberately thinner than negatives. High PP is an achievement.
- PP is unbounded. Extreme values are tuning feedback, not bugs.
- Target: 25-40 year complacency crisis window for an unmanaged great power.

## Files

- `in_game/common/auto_modifiers/sul_projection_country.txt` — unified scale + drag layer
- `in_game/common/script_values/sul_projection_values.txt` — drag computations
- `main_menu/common/static_modifiers/sul_projection_vanilla_injects.txt` — is_subject, ruler_mil
- `main_menu/localization/english/sul_projection_l_english.yml` — localization
