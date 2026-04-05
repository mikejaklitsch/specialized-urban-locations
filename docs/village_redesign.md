# Village Building Redesign

Status: **Discussion phase, not yet approved for implementation**

## Problem

Villages currently have `free_building_levels = 1` and `local_population_capacity = 1` but produce nothing meaningful. With 15-150 base building levels per location, a non-producing building is a dead slot. The specialization system feels underexploited — no strategic depth within a specialization.

## Core Design Goal

The player should feel a reason to dig into each location and optimize. The fundamental tension: **raw material extraction vs produced goods manufacturing** as opposing paths within each specialization. Production should feel like a big city with benefits and pains, extraction the opposite.

## Building Level Drag System (existing)

The mod already reduces output of everything per building level. Each building boosts its own production more than the drag it creates. This naturally rewards focus — stacking one type compounds bonuses while drag is linear.

## Village Role: Drag Canceller + Infrastructure

Villages don't produce goods. Instead they cancel their own building-level drag, then add small universal + spec-specific bonuses. They're infrastructure that makes density work.

### All villages share:
- Cancel own drag (express via modifiers that offset the per-level penalty)
- `local_population_growth = 0.0001` (0.01% per level)
- `local_population_capacity = 1`
- Maintenance cost (basic goods, varies by type)

### Per-type flavor (small but distinct):
- **Mining village:** `local_manpower` — mining towns produce soldiers
- **Farming village:** `local_monthly_food` or provisions-related — breadbasket
- **Gathering village:** `local_sailors` — coastal/river settlements
- **Woodland village:** `local_construction_speed` — lumber/carpentry expertise
- **Commercial village:** `local_market_access` — trade connector (already has this)

### Maintenance goods by type (creates local demand for own spec's goods):
- Mining → tools
- Farming → provisions
- Woodland → lumber
- Gathering → TBD
- Commercial → TBD

## Extraction vs Production Tension

Rejected approach: single building toggle per location. AI would flip-flop or pick randomly, player would feel like they're micromanaging village types across hundreds of locations.

Preferred approach: tension emerges from **building composition**. The ratio of RGO/enhancement buildings vs guild/workshop/manufactory buildings determines the location's identity. This is partially achieved by the existing drag system but needs further development. Villages enable deeper stacking without drowning in diminishing returns.

## Crop Buildings (separate from villages)

Wheat, rice, maize, potato, legume buildings gated by geography/climate/vegetation rather than `raw_material`. Lower output than RGOs. Distinct from the RGO system which gates on `raw_material` (natural deposits).

- **RGO buildings**: Large-scale extraction, gated by `raw_material`. High output, primary production.
- **Specialization crop buildings**: Small-scale cultivation, gated by geography. Lower output, supplementary.

This maps historically — `raw_material = goods:wheat` is prime wheat country (RGO handles that). A nearby farming location without wheat as raw material could still grow some wheat if climate/terrain allow. That's the crop building's niche.

Design not started.

## Open Questions

- What exactly are the per-building-level drag modifiers? Need to verify before designing cancellation.
- Pop growth at 0.0001 per level — sustainable without disease overhaul? Provisions scarcity may self-regulate.
- How aggressively should extraction vs production bonuses scale with building composition?
- Gathering village rename from "fishing village"? (Yes — gathering covers more than fish)
- `sul_rural_apiary` and `sul_rural_herbalist` produce raw materials without raw_material gating — needs resolution.

## Decisions Made

- Villages should NOT be the extraction/production toggle
- Each village type needs distinct modifiers (not identical effects)
- Villages need maintenance costs (prevents spam, creates economic decision)
- Iron mine and marble quarry restored as custom terrain-gated buildings
- Output modifiers on SUL buildings removed — will be reintroduced as production efficiency per building level
