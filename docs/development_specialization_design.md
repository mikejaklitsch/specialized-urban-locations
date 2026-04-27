# Development (Urbanization): Design Document

Development (0-100) represents a location's economic character on the extraction/production axis. Low development = raw material extraction. High development = manufacturing and trade. Equilibrium at 50 via a spring mechanism.

## System Roles

Each system has ONE job. They don't overlap.

| System | Job |
|--------|-----|
| Development (0-100) | Output quality: extraction vs production goods modifiers |
| Location ranks | Scale + compensatory urbanization push |
| Building caps (3 axes) | Capacity: what CAN be built, driven by development (zero-sum) |
| Building density (total levels) | Congestion: squeezes RGO capacity |

## Relationship to Specialization

- **Spec type** = WHAT (mining, farming, gathering, woodland, commercial)
- **Development** = extraction vs production CHARACTER

A farming city at dev 25 is a breadbasket. The same farming city at dev 75 has breweries and tanneries. Rank doesn't determine this — the player's building choices do.

## Forces on Development

Multiple forces compete. The spring pulls toward 50; everything else pushes away from it.

### Core Equilibrium (spring)

```
location_base_values:  local_monthly_development = +0.50    (constant upward)
development scaler:    local_monthly_development = -0.01    (per dev point)
```

At dev 50: +0.50 - 0.50 = 0. Equilibrium.

### Buildings (directional)

Each building contributes ±0.0002/mo to development via `local_monthly_development` in its INJECT/REPLACE block.

- **Extraction buildings** push DOWN: RGO buildings, crop buildings, mining, forestry, plantations
- **Production buildings** push UP: guilds, workshops, manufactories, mills, commerce, trade infrastructure
- **Neutral buildings**: military, warehouses, granaries, universities, minting, villages

250 production buildings hold equilibrium at dev 100. That's the design target for extremes.

### Pop Composition (directional)

Via `pop_percentage_impact` in `sul_development_pressure.txt`:

| Pop Type | Coefficient | At 100% of location |
|----------|-------------|---------------------|
| Burghers | +0.30 | +0.30/mo (urbanizing) |
| Peasants | -0.30 | -0.30/mo (de-urbanizing) |
| Slaves | -0.30 | -0.30/mo |
| Tribesmen | -0.30 | -0.30/mo |
| Laborers | -0.15 | -0.15/mo (work both sectors) |

A location 80% peasants gets -0.24/mo — a strong rural anchor. Pop composition is one of the largest forces on development outside the spring itself.

### Terrain (directional)

Vegetation, topography, and climate apply flat `local_monthly_development` pushes downward. Vanilla used percentage rate modifiers; we converted to flat directional forces because geography shapes what a location IS, not just how fast it changes.

| Source | Push | File |
|--------|------|------|
| Jungle | -0.20/mo | `sul_vegetation.txt` |
| Desert | -0.12/mo | `sul_vegetation.txt` |
| Forest | -0.08/mo | `sul_vegetation.txt` |
| Woods | -0.03/mo | `sul_vegetation.txt` |
| Mountains | -0.25/mo | `sul_topography.txt` |
| Wetlands | -0.15/mo | `sul_topography.txt` |
| Hills | -0.02/mo | `sul_topography.txt` |
| Plateau | -0.01/mo | `sul_topography.txt` |
| Arctic | -0.30/mo | `sul_climates.txt` |
| Tropical | -0.02/mo | `sul_climates.txt` |

Farmland and grasslands are neutral.

### Location Rank Push (compensatory)

Higher ranks push development upward — NOT to make locations trend above 50, but to counterbalance terrain and rural pop composition so the location can find its identity based on the player's building decisions.

Without rank push, a mountain location (terrain -0.25) with 80% peasants (pop -0.24) equilibrates at dev ~1 regardless of what gets built. The rank push gives the player room to steer.

| Rank | Non-commercial | Commercial |
|------|---------------|------------|
| Rural | 0 | +0.10/mo |
| Town | +0.10/mo | +0.25/mo |
| City | +0.25/mo | +0.50/mo |

Commercial pushes hard because commercial locations explicitly don't try extraction.

### Market Center (directional)

```
TRY_INJECT:market_center = {
    local_monthly_development = 0.005     # equivalent to 25 production buildings
}
```

### Rate Modifiers (non-directional)

These speed or slow development change without pushing in either direction:

- **Prosperity**: +25% (`local_monthly_development_modifier`)
- **Devastation**: -50%
- **War/disruption**: siege -20%, blockade -20%, looted -25%
- **Location size**: -0.003% per pixel from baseline 250
- **Infrastructure**: roads, rivers, coastal = positive rate modifiers (vanilla, kept as-is)

**Warning:** `local_monthly_development_modifier` is dangerous when negative. Devastation + siege + looted = -95%. Any additional negative contribution risks breaching -100%, which inverts the spring direction. Never add country-scope negative `global_monthly_development_modifier`.

## Building Caps (Zero-Sum with Development)

Three building axes. Development is a zero-sum input: high dev expands production capacity while squeezing extraction, and vice versa.

**Production caps** (guild, workshop, manufactory, mill, market):
```
cap = base + (development × expansion) - ((100 - development) × squeeze) + pop + rank
```
High dev: more production slots. Low dev: production squeezed.

**Extraction caps** (rural_building_cap):
```
cap = base + ((100 - development) × expansion) - (development × squeeze) + rgo_workers + rank
```
Low dev: more extraction slots. High dev: extraction squeezed.

**RGO caps** (raw_material-gated, one unified block):
Driven by population, rank, and building density — NOT development directly. All RGO building types share one cap per location.

## Building Density → RGO Squeeze

Total building levels at a location reduce RGO capacity:

```
TRY_INJECT:building_levels = {
    sul_rgo_size = -0.04    # 100 levels = -4 RGO size
}
```

This is the "urbanizing away the forests" mechanic. Building anything — production or extraction — reduces the location's ability to sustain raw material extraction. A densely built city has physically displaced the land that RGOs need.

Development no longer contributes positively to RGO size. The old `INJECT:development = { sul_rgo_size = 0.1 }` was removed because urbanization expanding extraction capacity is backwards.

## Vanilla Modifier Overrides

All vanilla flat `local_monthly_development` modifiers were converted to `local_monthly_development_modifier` (percentage rate) to preserve the rule: only buildings, pops, terrain, rank, and market centers apply directional pressure. Everything else modulates rate.

Full override list in Appendix A (preserved below for reference, values unchanged).

---

## Equilibrium Examples

**Mountain mining rural, 80% peasants, no buildings:**
- Spring: +0.50
- Terrain: -0.25
- Pop: -0.24
- Rank push: 0
- Net at dev 0: +0.01 → equilibrium at dev ~1

**Farmland farming town, 50% peasants 20% burghers, no buildings:**
- Spring: +0.50
- Terrain: 0
- Pop: -0.15 + 0.06 = -0.09
- Rank push: +0.10
- Net at dev 0: +0.51 → equilibrium at dev ~51

**Commercial city, 50% burghers, 100 production buildings:**
- Spring: +0.50
- Terrain: 0 (assume flat)
- Pop: +0.15
- Rank push: +0.50
- Buildings: +0.02
- Net at dev 0: +1.17 → equilibrium capped at dev 100

---

# Appendix A: Vanilla Modifier Audit

(Unchanged from original — all flat-to-percentage conversions remain valid.)
