# Complacency Coupling — Implementation Status

Companion to `power_projection_design.md`.

## Implemented

### Core Auto-Modifier (`REPLACE:complacency_impact`)

PP coupling: `power_projection = -100` (-2 PP per complacency point).

**Enticing side** (people want complacency):
- `global_population_growth = 0.005`
- `global_monthly_prosperity = 0.01`
- `monthly_prestige = 0.005`
- `hire_artist_cost_modifier = -0.5`
- `estate_enrichment = 0.25`
- `global_pop_food_consumption = 0.25` — demand rises, markets bustle with buyers

**Poison side** (state cannot act):
- `global_production_efficiency = -0.10` — unmotivated workforce
- `research_speed_modifier = -0.5`
- `country_cabinet_efficiency = -0.5`
- `global_institution_growth_modifier = -0.5`
- `embrace_institution_cost_modifier = 5.0`
- Military: morale -25%, discipline -10%, manpower -30%, sailors -30%, tradition decay
- Economic: building cost +0.2%/point, court cost +10%, diplo capacity -2
- Fragility: rebel growth, lowered rebel threshold, declaring war cost +100%

### War Exhaustion Coupling

`INJECT:war_exhaustion_impact` adds `monthly_complacency = -0.01`. At WE 20: -0.2/mo drain.

### PP → Complacency Coupling

In `REPLACE:power_projection`: `monthly_complacency = 0.0015`. At PP 200: +0.3/mo buildup. At PP -200: -0.3/mo drain.

### Top-Bar GUI

Full `hud_topbar.gui` override with `stat_complacency` + `stat_power_projection`.

### Files

- `in_game/common/auto_modifiers/sul_complacency_country.txt`
- `in_game/common/auto_modifiers/sul_projection_country.txt`
- `in_game/common/auto_modifiers/sul_war_auto_modifiers.txt`
- `in_game/gui/hud_topbar.gui`

---

## Remaining Work

### 1. Engagement Channels (complacency drains)

Players need tools to actively drain complacency beyond war exhaustion.

**1a. Diplomatic engagement:**
- Outgoing guarantees: -0.015/mo each (scaled by target size)
- Outgoing subsidies: -0.02/mo each (scaled by gold/mo)
- Inject `monthly_complacency` into vanilla static modifiers for active relations

**1b. War participation (non-leader):**
- Drain proportional to participation share × relative enemy strength
- Requires custom tracking — `on_ending_war` + monthly pulse

**1c. Peer rivalry expansion:**
- Per peer-strength rival: -0.02/mo beyond vanilla's existing -0.01
- Monthly pulse iterating `every_rival_country`

**1d. Receiving projection (symmetry):**
- Being a subject: +0.03/mo via `INJECT:is_subject`
- Being guaranteed: +0.01/mo
- Receiving subsidies: +0.02/mo

### 2. Success-Driven Buildup

Additional +0.025/mo when stability ≥ 2, crown_power ≥ 0.6, avg estate satisfaction ≥ 0, no peer rivals. May be redundant with PP coupling — test PP alone first.

### 3. Disaster Routing

**3a. Decline of Empire:** Reframe trigger from mandatory `stability < 0` to one-of-several stress conditions at complacency ≥ 75%.

**3b. Forced Opening:** New disaster for isolationist nations with high complacency, low PP, and significant advance gap contacted by peer-strength power. Meiji-vs-Qing fork. Needs dedicated design pass.

### 4. Vanilla Static Modifier Injects

- `is_subject`: `monthly_complacency = +0.03`
- `at_peace`: consider `monthly_complacency = +0.01`
- Verify existence of `is_guaranteed_by_other`, `is_receiving_subsidy`

---

## Calibration

Target: 25-40 year crisis window for an unmanaged great power.

At base PP 150: complacency builds at ~0.225/mo. Reaches complacency 50 in ~18 years. By then PP drag (-100 at complacency 50) has pulled PP down to ~50, slowing complacency growth to ~0.075/mo. System self-corrects but slowly — the player feels the slide and must act to reverse it.
