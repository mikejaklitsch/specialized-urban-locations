# Complacency Coupling — Remaining Implementation Plan

Companion to `power_projection_design.md`. Tracks systems not yet implemented
after the auto_modifier coupling layer landed.

## What's already implemented

- `sul_complacency_pp_buildup` — PP writes `monthly_complacency` (0.0015 per PP)
- `sul_projection_pp_costs` — PP penalty package (stability decay, estate
  dissatisfaction, urban build cost up, trade efficiency down, migration
  outflow, baseline tax extraction bonus)
- `INJECT:complacency_impact` — complacency extension package including the
  PP drag (`power_projection = -200`, yielding -2 PP per complacency point
  under vanilla's `scales_with × 0.01`). Positives: estate satisfaction
  recovery, migration in, cultural output, monthly development. Negatives:
  institution spread, manpower/sailors, levy recovery, morale, discipline,
  civic build cost, CB fabrication, court cost, diplomatic capacity,
  assim/conv/integration, accepted culture cost, declare-war cost.
- `INJECT:war_exhaustion_impact` now carries `monthly_complacency = -0.01`
  (§1c complete). At WE 20 this drains 0.2 complacency/month, matching
  vanilla `recovery_motivation`.
- Top-bar GUI (§5 complete). Full `hud_topbar.gui` override places
  `stat_complacency` + `stat_power_projection` between prestige and diplo
  stats. Complacency reuses vanilla `ComplacencyResourceTooltip`; PP reuses
  `power_projection_tooltip`.

Files touched:
- `in_game/common/auto_modifiers/sul_projection_country.txt` (coupling + PP costs)
- `in_game/common/auto_modifiers/sul_complacency_country.txt` (INJECT complacency_impact)
- `in_game/common/auto_modifiers/sul_war_auto_modifiers.txt` (INJECT war_exhaustion_impact)
- `in_game/gui/hud_topbar.gui` (full vanilla override with SUL stat_player inserts)

Calibration target: 25-40y crisis window for unmanaged great power (base_PP 150 → complacency 24, PP 102 at year 25; PP ~halved by year 30).

---

## 1. Engagement channels (complacency drains)

**Status:** not implemented. Current model only has vanilla static_modifier
complacency contributions + our PP coupling. Players have no player-driven
drain tools beyond vanilla's rival/control/recovery channels.

### 1a. Diplomatic engagement

Channels to implement:
- Outgoing guarantees: -0.015/month each, scaled by target size
- Outgoing subsidies: -0.02/month each, scaled by gold per month
- Gifts: one-shot -0.02 × gold_equivalent_to_monthly_subsidy
- Tribute slider (Middle Kingdom / similar): -0.05 to -0.15/month at high tribute

**Implementation approach:**
Static modifiers with `monthly_complacency` effect, applied via country modifiers on the projector when the channel is active. Engine hooks needed:
- `on_action: on_create_guarantee` / `on_break_guarantee` (verify existence)
- `on_action: on_subsidy_start` / `on_subsidy_end` (verify existence)
- `on_gift_sent` (verify existence; may need polling)

If direct on_actions don't exist, fallback is monthly_country_pulse that iterates the country's active guarantees/subsidies and applies/refreshes a timed country modifier. Reviewable via `any_guaranteed_country`, `any_subsidy_target`, or similar iterators — need to verify scoped iterator availability in EU5.

### 1b. War participation when not war leader

Magnitude: `-0.5 × participation_share × (enemy_strength / your_side_total_strength)` per month for called-in allies / coalition / defenders.

**Implementation approach:**
On `in_war` or monthly pulse, iterate active wars the country participates in. For each:
- Detect war leader status (trigger exists: `is_war_leader`?)
- If not leader, compute participation share
- If leader, skip (or apply lesser drain against peer; zero against weaker)

Compute share: need per-country contribution in war. EU4-style `war_favors` or `contribution_in_war` trigger availability is unknown — investigate. If unavailable:
- Fallback: snapshot each country's casualties at war start; delta monthly; divide by side total casualties for share.
- Store as variable on each country; rebuild on war start, delete on war end.

Relative strength: `country_strength` / `war_side_total_strength`. Side total requires iteration over side members — `every_war_participant` or similar.

### 1c. Military channel via WE coupling

Magnitude: `monthly_complacency += -1.0 × modifier:monthly_war_exhaustion`

**Implementation approach:**
Easiest form: an auto_modifier scaling with `modifier:monthly_war_exhaustion` (the accumulated total).

```
sul_complacency_we_drain = {
    scales_with = { value = modifier:monthly_war_exhaustion }
    monthly_complacency = -1.0
}
```

Verify that `modifier:<name>` is a valid scales_with input. Vanilla `complacency_impact` uses `complacency` directly, which is a country scalar. `modifier:X` as a scales_with value needs engine confirmation. If unsupported, fall back to monthly pulse that reads `modifier:monthly_war_exhaustion` and writes via `add_complacency`.

### 1d. Rivalry channel

Vanilla already contributes via `threatening_rivals` (-0.01/month) and `non_threatening_rivals` (+0.03/month) static modifiers. Expansion:
- Per peer-strength rival (within 0.5x-2.0x country_strength band): additional -0.02/month

**Implementation approach:**
Country modifier applied on monthly pulse that iterates `every_rival_country` and counts peer-strength rivals. Apply `sul_complacency_peer_rival_drain` country modifier scaled by count.

Alternative: use `scaled_modifier` with `num_of_peer_rivals` as a custom script_value.

### 1e. Symmetry — receiving projection

Raises complacency when the country is the recipient of foreign projection.

- Being a tributary of another power: +0.05/month
- Receiving subsidies: +0.02/month
- Being guaranteed by a power: +0.01/month
- `INJECT:is_subject` (vanilla static_modifier): add `monthly_complacency = +0.03`

**Implementation approach:**
Most of these already have static_modifier slots in vanilla that apply when the relation is active. Inject `monthly_complacency` into those vanilla static modifiers. Verify which exist:
- `is_subject` — confirmed (already has PP inject)
- `is_guaranteed_by_other` — verify
- `is_receiving_subsidy` — verify
- Middle Kingdom tributary status — verify handle

---

## 2. Success-driven buildup

**Status:** not implemented. The PP coupling already provides the main "success breeds complacency" feedback, but the spec called for additional acceleration when a country is simultaneously stable, centralized, loyal, and unthreatened.

Magnitude: `+0.025/month` when all conditions met:
- stability >= 2
- crown_power >= 0.6
- avg_estate_satisfaction >= 0
- no peer-strength rivals

One-shot on decisive easy victory at war end:
- war_score margin > 80 AND strength ratio > 2:1
- `add_complacency = 5`

**Implementation approach:**
Static modifier `sul_complacency_success_pressure` with `monthly_complacency = +0.025` and a trigger that checks the four conditions. Apply/remove on monthly pulse.

One-shot hook on `on_ending_war` with trigger checking warscore margin and strength ratio; `add_complacency = 5` effect.

Open question: is the +0.025 redundant with the PP coupling? A country meeting all four success conditions likely has high PP, which already drives complacency growth. Recommend testing the PP coupling alone first and adding the success channel only if the slide feels too slow for the most dominant empires.

---

## 3. Disaster routing

### 3a. Decline of Empire — trigger reframe

**Status:** not implemented. Vanilla trigger is `complacency >= 75% AND stability < 0 AND (low_control_in_home_region OR high_unaccepted_culture_pop)`.

**Target:** reframe as cascade-manifestation. Fire when high complacency meets any stress condition.

**Implementation approach:**
Mod override of vanilla `decline_of_empire.txt` disaster file. Either:
- `REPLACE:decline_of_empire` block with new `can_start` trigger
- Or a filename-override (same filename as vanilla with full new content)

New `can_start` structure:
```
can_start = {
    NOT = { current_age = age_1_traditions }
    has_any_active_disaster = no
    complacency_percentage >= 0.75
    OR = {
        stability < 0
        has_variable_in_last_years = { name = recent_war_loss; years = 5 }
        manpower_percentage < 0.5
        is_in_debt = yes
        any_owned_location = { has_variable = recent_uprising_variable }
        average_pop_satisfaction < 0
    }
    # ... remaining vanilla conditions (China age gate, DoE cooldown, etc.)
}
```

Verify all triggers exist and behave as expected. The `stability < 0` disjunct is from the vanilla trigger — we're promoting it from mandatory to one-of-several.

Keep the original modifier block (`monthly_rebel_growth`, `bank_interest`, etc.) and on_monthly events unchanged — they express cascade, not trigger.

### 3b. Forced Opening — new disaster for isolationist failure

**Status:** not implemented. Fresh design needed.

Concept: fires when a country with high complacency, low foreign exposure, and significant advance gap is contacted by a peer-strength power with better tech.

Possible trigger shape:
```
can_start = {
    complacency_percentage >= 0.50
    power_projection < 20
    OR = {
        # low foreign trade
        any_market_in_country = { foreign_trade_share < 0.2 }
        # OR trigger flag from external contact event
        has_variable = sul_isolationist_contact_made
    }
    # advance gap
    num_of_advances < {
        value = average_num_of_advances_among_country_strength_peers
        subtract = 5
    }
}
```

`average_num_of_advances_among_country_strength_peers` would need to be a custom script_value iterating peer-strength countries.

**Implementation approach:**
- New disaster definition in `in_game/common/disasters/sul_forced_opening.txt`
- `on_start` event: forced trade concessions, modernizer faction event, treaty port locations lose control
- `on_monthly` events: accelerated advance adoption opportunities (at stability cost), estate privilege choices (military modernization grants estate power)
- Recovery branch keyed on closing advance gap + draining complacency
- Failure branch keyed on cascade continuing

Dedicated design pass needed. This is the Meiji-vs-Qing fork — the disaster should be survivable with the right reforms.

---

## 4. Vanilla static_modifier injects

Existing vanilla `monthly_complacency` sources are small (-0.01 to -0.2). Review for compatibility with new model:

- `non_threatening_rivals` +0.03 — **keep** (empty rivalry slots still breed complacency)
- `threatening_rivals` -0.01 — **keep** or absorb into new peer-rivalry channel
- `average_control_50` -0.1 — **keep** (vanilla — low control drains)
- `recovery_motivation` -0.2 — **keep** (vanilla — post-loss drains)
- `at_peace` — **verify**; may need inject of small `+0.01 monthly_complacency` to reinforce peaceful-drift

New injects:
- `is_subject`: add `monthly_complacency = +0.03` (being protected breeds complacency — mirror property)

**Implementation approach:**
Add to existing `main_menu/common/static_modifiers/sul_projection_vanilla_injects.txt` using `INJECT:is_subject`.

---

## 5. Top-bar GUI integration

**Status:** not implemented. User requested PP and complacency appear on the main top-bar stat row alongside legitimacy, prestige, stability, etc.

**Investigation notes:**
Top-bar stats live in `in_game/gui/hud_topbar.gui` (2495 lines). Each stat is a ~130-line templated block with `name = "stat_<currency>"`. They use the generic currency API:
- `Country.GetCurrencyValue('<name>')` — display value
- `Country.GetFixedPointCurrencyValue('<name>')` — for comparisons
- `Country.GetCurrencyMaxValue('<name>')` — progress bar max
- `Country.IsCurrencyValueEqualOrLessThanZero('<name>')` — red/green gradient gating
- `InGameTopbar.GetPlayerCurrencyChange('<name>')` — monthly delta
- `InGameTopbar.GetPlayerCurrencyChangeFormatted('<name>')` — formatted delta text

Existing stats using this API: `stability`, `legitimacy`, `prestige`, `manpower`, `sailors`, and others.

Tooltip widgets are specific per stat (e.g. `PrestigeResourceTooltip`); complacency and PP would each need their own tooltip widget or reuse a generic one.

Icon textures at `gfx/interface/icons/resources/<name>.dds` — would need new art assets for `complacency.dds` and `power_projection.dds`.

**Critical unknown:** is `'complacency'` or `'power_projection'` a valid currency key in the engine's currency system? The existing currency set appears to be hardcoded engine-side (`stability`, `legitimacy`, `prestige`, etc. are engine concepts with their own scope methods). `power_projection` is clearly a country scalar but may or may not be registered as a "currency" in the GetCurrencyValue sense. Complacency similarly.

**Implementation paths:**

Path A (if currency API supports complacency/PP):
- Copy stat_prestige block template
- Replace currency references with 'complacency' / 'power_projection'
- INJECT into hud_topbar.gui's stat container
- Add DDS icons at the expected texture paths
- Possibly author tooltip widget templates

Path B (if currency API does NOT support these as currencies):
- Custom GUI block that reads the values via scripted values or direct country scope
- Use `GetCurrencyValue` with an engine currency that happens to equal our value, or write custom data context accessors
- This may require scripted_gui bridging

Recommend starting with Path A by attempting `Country.GetCurrencyValue('power_projection')` and `('complacency')` in a test widget. If the values render, we're on the easy path. If not, fall back to Path B via scripted GUI.

Investigation to-do before implementation:
- Check `in_game/gui/shared/topbar_tooltips.gui` for existing complacency tooltip references (vanilla has some — found in prior grep)
- Grep vanilla GUI files for `power_projection` / `'complacency'` accessor patterns
- Verify the currency API's registration mechanism (if modifiable from mod-side)

---

## 6. Open verification items

These are not blockers, but the auto_modifier implementation assumes them and they should be verified during first playtest or via quick script tests:

1. **Modifier handle verification.** The new effects we added to `complacency_impact` assume these exist and work on country scope:
   - `global_institution_growth_modifier` — assumed exists from modifier_types grep
   - `global_manpower_modifier` — confirmed
   - `global_sailors_modifier` — confirmed
   - `levy_recovery_modifier` — confirmed
   - `land_morale_modifier` / `naval_morale_modifier` — confirmed
   - `discipline` — confirmed
   - `global_urban_build_buildings_cost` / `global_rural_build_buildings_cost` — confirmed
   - `settle_country_cost_modifier` — confirmed
   - `casus_belli_creation_speed_modifier` — confirmed
   - `court_spending_cost` — confirmed
   - `diplomatic_capacity` — confirmed
   - `global_pop_assimilation_speed_modifier` / `conversion` / `integration_speed_modifier` — confirmed
   - `add_accepted_culture_cost_modifier` — confirmed
   - `declaring_war_cost_modifier` — confirmed
   - `global_estate_satisfaction_recovery` — confirmed
   - `global_migration_speed_modifier` — confirmed
   - `cultural_tradition_modifier` — confirmed
   - `monthly_prestige` — confirmed
   - `global_monthly_development` — confirmed

2. **INJECT on auto_modifier blocks.** This is the primary structural assumption. If `INJECT:complacency_impact = { ... }` doesn't combine with vanilla's block (just replaces it or errors silently), we need to either:
   - Switch to `REPLACE:complacency_impact` with the full vanilla contents + our additions
   - Or author a parallel auto_modifier (`sul_complacency_extras`) with `scales_with = complacency` that holds only our additions (same pattern vanilla uses for `war_exhaustion_impact` vs `war_exhaustion`)

   Quick verification: load the mod, check that an in-game country at ~50 complacency shows both vanilla's `research_speed_modifier -0.5` and our `global_manpower_modifier -0.3` (partial values, since scales_with × 0.01 × 50 halves them).

3. **Negative-mirror math.** The `sul_complacency_pp_buildup` auto_modifier uses `scales_with = power_projection` with positive `monthly_complacency = 0.0015`. When PP is negative, this should yield negative `monthly_complacency` (drain). Verify the engine applies `scales_with × effect` as signed multiplication rather than clamping to non-negative.

4. **PP floor behavior.** `sul_projection_drag_complacency` contributes -2 × complacency to PP. For a country with base_PP 50 and complacency 50, the drag is -100, yielding actual PP of -50. Need to verify PP can go negative (vanilla injects suggest yes — `is_subject = -10`) and that scripts reading PP handle the sign correctly.

5. **Cumulative PP cost stacking.** `sul_projection_pp_costs` adds `stability_decay +0.001 × PP`, meaning at PP 100 we add +0.1 stability decay/month. Combined with vanilla sources (war, disasters, etc.), verify no engine-side clamp is hit for the worst-case combined state.

---

## Sequencing recommendation

1. Playtest the auto_modifier coupling in isolation. Verify the 25-40y window on an AI great power left unmanaged by the player.
2. Verify INJECT and negative-mirror assumptions via debug observation.
3. Implement vanilla static_modifier injects for `is_subject` (mirror) — low effort, reinforces model.
4. Implement engagement channels, in this order of value:
   - Diplomatic (guarantees + subsidies) — most player-facing
   - WE coupling — mechanically simple, high impact
   - Symmetry injects for receiving subsidies / being guaranteed
   - War participation — requires custom tracking
   - Peer-rivalry expansion — incremental
5. Implement Decline of Empire trigger reframe.
6. Design and implement Forced Opening disaster (separate pass).
7. Implement top-bar GUI integration (needs art assets + tooltip design).
8. Success-driven buildup — consider dropping if PP coupling alone produces the right pace.
