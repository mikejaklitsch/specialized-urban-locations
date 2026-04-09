# Power Projection Extension — Design Plan

## Intent

Turn vanilla `power_projection` from a flavor stat into the primary slowdown mechanic governing conquest and integration. A decentralized nation — many subjects, weak control over its own land — cannot project enough authority to take or absorb new territory. A centralized one can. The mechanic intentionally makes early expansion harder but provides clear paths out through proper management.

**France at 1337** is the canonical calibration scenario: a nation overwhelmed by its appanages should start structurally unable to project power until it consolidates.

## Core Pattern

Power projection is a vanilla static-modifier key, not a script value or country variable. It accumulates from every modifier source that declares `power_projection = N`. Negative values stack the same way as positive ones (confirmed via test modifiers).

- **Zero is neutral** — no buffs, no maluses. No hidden baseline wall.
- **Symmetric scaling** — every lever scales the same per point in both directions.
- **Expected range** — roughly -100 to +100, skewed lower because drags outnumber sources.
- PP is read via `value = power_projection` inside script_value blocks, and via `scales_with = power_projection` inside static modifiers / auto_modifiers.
- PP is changed only by adding or removing modifier sources — there is no `add_power_projection` effect.

## Two-Layer Architecture

PP drives two distinct systems that share the same score:

### Scale Layer
PP continuously modifies rates via auto-modifiers using `scales_with = power_projection`. Every scaled lever gets a small per-point coefficient. Per-lever values will be tuned by feel during testing; start conservatively so +100 PP isn't god mode on every axis simultaneously.

### Gate Layer
PP comparison between two countries hard-disables specific interactions. Uses the same pattern vanilla already wires up for `stronger_power_projection = yes` on building types (see `building_types/foreign_buildings.txt`, `unique_buildings.txt`). Binary triggers, no scaling coefficient involved.

## Sources of PP

### Negative (drags)

| Source | Type | Notes |
|---|---|---|
| Control-weighted population share | Structural | `(total_control_scaled_population / total_population) - 1` × constant. Decentralized = negative. Cleanest structural drag. |
| Cultural non-acceptance share | Structural | Share of population in non-accepted cultures. Player can accept cultures to offset. |
| Religious non-acceptance share | Structural | Share of population in non-accepted religions. |
| Relative subject strength | Structural | Sum across subjects of `(subject_country_strength × per-subject-type constant)`. Per-type constants defined later. |
| Low stability | Structural | Negative stability bleeds PP. |
| Conquest debt | Decaying | See dedicated section below. |

Structural drags are continuously recomputed — they do not decay. A country that stops fighting only recovers its conquest debt; structural PP pits require active investment (control infrastructure, culture acceptance, releasing subjects, raising stability).

### Positive

| Source | Notes |
|---|---|
| Vanilla sources | Advances, estates, values, government reforms, etc. — left untouched. |
| Monarch / cabinet skill | New. Scaled so skilled rulers can partially offset the drag floor. Tuning informed by how punishing the negative side ends up feeling. |
| Unused diplomatic capacity filled by non-subjects | **Stretch goal.** Requires `diplomatic_relations_used` and `num_subjects` exposed as script values. Drop if the formula is engine-opaque. |

## Scale Layer Effects

Coefficients are placeholder; real values set during testing.

| Lever | Vanilla modifier | Status |
|---|---|---|
| Integration speed | `global_integration_speed_modifier` | Exists (vanilla already uses it). Amplify coefficient. |
| Assimilation speed | `global_pop_assimilation_speed_modifier` | Exists. |
| Religious conversion speed | `global_pop_conversion_speed_modifier` | Exists. |
| Warscore cost of locations | `global_war_score_cost` | Exists. Negative value = cheaper, positive = more expensive. Used in laws, societal values, estates. |
| Antagonism generated | — | AE-analog. PP scales the antagonism your conquests/wars **generate**, not the antagonism you receive. Identify the exact vanilla modifier during implementation. |
| Proximity / control range | `global_distance_from_capital_speed_propagation` | Exists. Scales proximity propagation speed from capital to all locations. Used in ruler traits, laws, societal values, estate privileges. |
| Vassal loyalty | Subject opinion / loyalty modifiers | Creates feedback loop: weak projection → disloyal subjects → risk of losing them. |
| Diplomatic annexation cost | `diplomatic_annexation_cost` | Exists. Free second warscore-adjacent lever. |

## Gate Layer Effects

Binary action gates based on PP comparison between two specific countries. **Subject-interaction-only scope** — these gates do not apply to non-subject targets.

| Gate | Condition | Effect |
|---|---|---|
| Forced religious conversion of subject | Overlord PP < subject PP | Disabled |
| Forced cultural conversion of subject | Overlord PP < subject PP | Disabled |

Additional subject-interaction gates can be added under the same pattern. Encourages centralization: an overlord outclassed by its own vassals cannot push them around.

## Conquest Debt (Decaying Drag)

**Chosen pattern:** single variable-scaled modifier.

- One static modifier: `sul_projection_conquest_debt` with `scales_with = sul_projection_conquest_debt` (country variable).
- On conquest, the variable increments by an amount size-weighted by the conquered location's dev or population (weighting formula TBD).
- Monthly pulse decays the variable toward zero at a base rate **modified by diplomatic reputation**. Higher dip rep = faster decay.
- Dip rep realistically hovers between 8 and 20 and rarely hits zero — calibrate the base decay rate for a mid-rep country (~12-14) and let high/low rep swing it from there.

Every point of diplomatic reputation also contributes some positive PP directly (magnitude TBD).

This pattern trades individual conquest visibility for simplicity and single-point decay tuning. All conquest drag lives in one modifier line, easy to read in the outliner.

## Namespace and Hook Integration

- **Namespace:** `sul_projection_`
- **Hook:** `monthly_country_pulse` via the existing `sul_hardcoded.txt` dispatcher. Add `sul_projection_monthly_update` to the pulse list, alongside `sul_minting_monthly_update`, `sul_war_monthly_pulse`, etc.
- **Monthly update responsibilities:**
  1. Recompute each structural drag source and apply as static modifiers scaled by country variables.
  2. Decay the conquest debt variable (rate modified by dip rep).
  3. Refresh monarch/cabinet skill contribution.
- **Conquest entry point:** `on_location_changed_owner` (already in the dispatcher) — increment conquest debt variable on winner.

## Open Obstacles

One remaining: **antagonism generated** — I still need to find the exact vanilla modifier name during implementation. Everything else has a confirmed lever.

## Calibration Notes

- Per-lever coefficients start lower than vanilla's current +1%/PP for integration. Target ~0.3-0.5%/PP per lever as a starting guess, since eight levers stack.
- Positive sources are deliberately thinner than negatives. Reaching high positive PP should feel like an achievement, not a baseline state.
- PP is unbounded in both directions. No hard floor, no hard ceiling — extreme values are tuning feedback, not bugs.
- User will handle tuning and scenario testing. Do not make autonomous balance decisions without authorization.

## Out of Scope

Explicitly **not** touched by this mechanic:
- Combat stats (morale, discipline, combat width, tactics) — PP shapes what you can hold and absorb, not what you win battles with.
- Army size or manpower recovery.
- Trade, economy, or production.
- Any territory size / province count penalty (would punish tall empires that are behaving correctly).
