# Error Assessment — May 1, 2026

After building category rework, building cap formula overhaul, icon transfer, and food removal restoration.

**Total:** 469 messages across 43 groups (16 suppressed as engine noise).

---

## Critical (ERROR)

### 1. `change_location_rank_effect` compilation failure (3x)
**File:** `location_effects.txt:114`
**Cause:** `modifier:sul_is_*_rank_tier` used inside a parameterized `scripted_effect`. Engine can't compile `modifier:` references when scope is ambiguous at definition time.
**Fix:** Replace with `location_rank` checks using specialization rank names, or delete the effect if rank routing is handled elsewhere (check `sul_rank_routing.txt`).

### 2. Unknown trigger types (9x)
**Sources:** `generic_traditional_economy_mission_pack.txt`, `sul_pop_demand_wpp.txt`, `country_triggers.txt`
**Values:** `scope:` (bare), `is_cossack`, `scope:recipient.is_rebel_country`, etc.
**Cause:** Mix of vanilla mission bugs (dot-notation in wrong scope) and possibly nonexistent triggers. Check `sul_pop_demand_wpp.txt` for a bare `scope:` reference.
**Fix:** Investigate each source individually. Mission file may need vanilla update sync.

### 3. Inconsistent trigger scopes in IO flood fill (6x)
**File:** `sul_io_flood_fill_actions.txt:7,11,36`
**Cause:** `is_member_of_international_organization` and `any_owned_location` used in wrong scope for generic actions.
**Fix:** Verify scope chain, add explicit scope transitions.

### 4. Variables set-but-never-used (5x)
**Values:** `sul_local_gdp`, `sul_country_pop_nobles`, `sul_country_pop_clergy`, `sul_country_pop_burghers`, `sul_asset_share`
**Cause:** GDP pipeline stubs from wealth system, not yet fully wired.
**Fix:** Wire up or remove dead code.

### 5. Variables used-but-never-set (4x)
**Values:** `sul_prior_peasant_levels`, `sul_prior_burgher_levels`, `sul_prior_clergy_levels`, `sul_prior_laborer_levels`
**File:** `sul_rgo_grant.txt:29,38,47,56`
**Cause:** RGO grant reads these to calculate building budget after destruction, but nothing populates them.
**Fix:** Add `set_variable` calls to snapshot current building levels before destruction, or guard reads with `has_variable`.
**Risk:** Medium — RGO grants may miscalculate their budget.

---

## Warnings

### 6. Building above max level (92x)
Three patterns:
- **tar_kiln (8x):** Max = 0 in locations without specialization. `tar_kiln` uses `basic_industry_category` which maps to our production cap. No specialization rank → `sul_production_size` = 0 from development alone at low dev.
- **sul_rgo_* (30+x):** Max = 0-1. Vanilla-placed RGO buildings exceed `sul_rgo_max_level_base` which reads `max_rgo_workers`.
- **tannery, brewery, tools/weapon guilds (~50x):** Max 2-3 but buildings have 3-5 levels. New cap formula evaluates lower than what vanilla originally placed.

**Fix:** Consider `min = 1` on production/extraction caps. Buildings above max don't crash — they can't expand but aren't destroyed. `remove_if` handles cleanup for truly invalid ones.

### 7. Invalid building at start (26x)
**Values:** `saltpeter_guild`, `university`, `charcoal_maker`, `sul_rural_winemaker`
**Cause:** INJECT gating (`modifier:sul_allows_*_production = yes`) makes these invalid at locations without specialization permission. `remove_if` destroys them within the first month.
**Fix:** Acceptable — transient startup noise.

### 8. Building in invalid location rank (110x)
**Values:** `monastery`, `charcoal_maker`, `lumber_mill`, `stone_quarry`, `sand_pit`, etc.
**Cause:** Vanilla places these in generic ranks (`rural_settlement`, `town`, `city`). Our mod replaces those with specialization ranks. Buildings flagged for vanilla ranks don't match.
**Fix:** These buildings need INJECT blocks adding specialization rank flags — same pattern as the production building rework done today (`city = no, town = no, rural_settlement = no` + spec rank flags). Scope: identify all vanilla buildings placed at game start that use generic ranks and add appropriate specialization rank availability.

### 9. Production method profit out of range (3x)
**Values:** `sul_pastureland_maintenance`, `sul_sugar_provisions`, `sul_lumber_mill_maintenance`
**Fix:** Add `debug_max_profit = -1` to exempt intentional high-profit PMs, or rebalance input costs.

---

## UI Issue

### 10. Population tooltip shows negative in building cap breakdown
**Observed:** Winery shows population line as negative value, but final max level is correct.
**Cause:** `desc` on `multiply` in EU5 script values displays the **delta** (difference between post-multiply and pre-multiply result). The engine may not handle complex expressions inside multiply's desc the way it handles simple `add` desc lines. Vanilla only uses `multiply` desc for flat values (e.g. `value = 2`).

**Fix options:**
- **(A) Remove desc from multiply.** Accept no tooltip line for population. Simplest.
- **(B) Restructure as pure additive.** Split into two `add` lines with separate descs:
  ```pdx
  add = { desc = "SUL_CAP_PRODUCTION_SIZE" value = modifier:sul_production_size }
  add = { desc = "SUL_CAP_POPULATION" value = modifier:sul_production_size multiply = { value = population divide = 50 } }
  ```
  First line = base from size, second line = population bonus (size × pop/50). Both always positive. Clear tooltip.
- **(C) Keep current.** Final value is correct; accept visual quirk.

**Recommendation:** Option B — gives accurate, always-positive tooltip with clear labeling.

---

## Cosmetic (low priority)

### 11. Missing modifier icons (72x)
Enrichment rates, rank tiers, upgrade cost modifiers, etc. Need batch icon generation.

### 12. Missing localization keys (35x)
`sul_looting_efficiency`, enrichment rates, base wages, etc. Need loc pass.

### 13. Location rank color collisions (15x)
All 5 specialization types share colors per tier. Assign unique colors.

### 14. Missing texture (3x)
`gfx/interface/icons/modifier_types/local_max_rgo_size.dds` — needs icon file.

---

## Session Summary (what changed today)

1. **Building categories:** Assigned `rgo_building_category`, `basic_industry_category`, `consumer_goods_category` based on pop demand presence. Deleted unused custom categories.
2. **Building rank flags:** Laborer buildings locked to natural specialization. Burgher INJECT buildings expanded to all specs at town+.
3. **Building cap overhaul:** `sul_production_size` and `sul_extraction_size` modifiers wired via `location_base_values` (+10 extraction at dev 0) and `development` (±0.1/point). Rank bonuses: +2 town, +5 city. Population multiplier: 1 + pop/50.
4. **RGO base:** 3 → 5, population added to base (pop/50).
5. **Free building levels:** Rural +25, town +50, city +100. Population scaling 1 per 5 pops (0.2/pop via total_population inject).
6. **Specialization icons:** 45 icons transferred (64x64, red=mining, blue=gathering, green=farming, purple=commercial, brown=woodland).
7. **Food removal restored:** `sul_goods_food_removal.txt` recreated (lost during April 5 consolidation, broke visibly April 27 when REPLACE blocks were removed). `land_owning_farmers` and `elephant_hunting_grounds` food modifiers also removed.
8. **RGO output fix:** `location_rank = rural_settlement` → `modifier:sul_is_rural_settlement_rank_tier` (4 instances, was causing 402 errors/tick).
9. **Loot fix:** `prev.local_var:sul_loot_total` → `local_var:sul_loot_total`.
10. **Dead file cleanup:** Deleted `building_caps.txt` (generated, fully overridden), `sul_building_categories.txt`.
