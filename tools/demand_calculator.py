#!/usr/bin/env python3
"""
Demand System Calculator for Specialized Urban Locations
========================================================

Interconnected system: price + food_consumption drive everything.
Category target is the primary design lever. Class spread, thresholds,
and demand magnitude all DERIVE from the same core variables.

FORMULA:
  spread         = (target / max_target) ^ SPREAD_CURVE
  class_weight_i = 1 + (food_consumption_i - 1) × spread
  affordability_i= min(1.0, food_consumption_i × THRESHOLD_SCALE / price)
  price_factor   = (REFERENCE_PRICE / price) ^ PRICE_CURVE
  weight_i       = class_weight_i × affordability_i × modifier_i
  demand_add_i   = output × price_factor × weight_i / target

  No assumed pop composition — target = weighted pop units per building.
  The game determines actual demand from actual pops.

USAGE:
  python demand_calculator.py                # Full report
  python demand_calculator.py --compact      # Summary table only
  python demand_calculator.py --pdx          # PDX script values
  python demand_calculator.py --location 10  # Location with 10 pop units
"""

import sys
import argparse
import math

# ================================================================
#  LEVER 1: CATEGORY TARGETS
#  How many pop units does ONE guild-tier building satisfy?
#    Lower  = more buildings needed = feels essential
#    Higher = fewer buildings needed = feels like a luxury
#
#  This is the PRIMARY design lever. Class spread derives from it.
# ================================================================

CATEGORY_TARGETS = {
    "necessity": 25,     # Always short, always building more
    "common":    80,     # Comfortable once established
    "upper":    250,     # One or two covers you
    "luxury":   800,     # One building oversupplies
}

# ================================================================
#  LEVER 2: SYSTEM PARAMETERS
#  Three scalars that control how the interconnected systems behave.
#  All work through price × food_consumption — not independently.
#
#  SPREAD_CURVE:   How aggressively category target → class spread.
#                  Higher = luxury categories diverge more from necessity.
#                  spread = (target / max_target) ^ SPREAD_CURVE
#
#  PRICE_CURVE:    How aggressively price affects demand magnitude.
#                  0 = price has no effect, 1 = linear, 0.5 = sqrt
#
#  THRESHOLD_SCALE: Affordability curve for demanding a good.
#                   affordability = min(1.0, food_cons × scale / price)
#                   Higher = more permissive (lower classes can afford more)
# ================================================================

SPREAD_CURVE = 0.5       # sqrt: necessity→0.18, common→0.32, upper→0.56, luxury→1.0
PRICE_CURVE = 0.5        # sqrt: price 6 → 0.71× demand vs price 3
REFERENCE_PRICE = 3.0    # neutral price point (factor = 1.0)
THRESHOLD_SCALE = 2.0    # food_cons >= price/2 to demand

# ================================================================
#  LEVER 3: POP FOOD CONSUMPTION (the anchor)
#  From pop_types — vanilla + SUL overrides.
#  Defines both the class hierarchy AND the threshold mechanism.
# ================================================================

POP_TYPES = [
    "nobles", "clergy", "burghers", "soldiers",
    "laborers", "peasants", "slaves", "tribesmen",
]

FOOD_CONSUMPTION = {
    "nobles":    20.0,   # vanilla
    "clergy":    10.0,   # SUL override (vanilla 5.0)
    "burghers":   8.0,   # SUL override (vanilla 4.0)
    "soldiers":   5.0,   # vanilla
    "laborers":   3.0,   # SUL override (vanilla 1.0)
    "peasants":   1.0,   # vanilla
    "slaves":     1.0,   # vanilla
    "tribesmen":  0.0,   # vanilla (never demands anything)
}

# ================================================================
#  LEVER 4: BUILDING CONSUMPTION (derived, not tuned)
#  Per-guild-equivalent consumption from production inputs + construction.
#  Military maintenance excluded — at realistic force ratios (~0.5% of
#  pop as soldiers), regiment maintenance is <1% of total goods demand.
#
#  Production inputs: sum across all building types at guild tier.
#  Construction costs: weighted average across common building types
#    (guild=0.5, workshop=1.0, manufactory=2.0, mill=4.0 masonry etc.)
#
#  consumer_share = output / (output + building_consumption)
#  Source: vanilla building_types/, goods_demand/building_construction_costs.txt
# ================================================================

BUILDING_CONSUMPTION = {
    # ── Produced goods ──────────────────────────────────────────
    # cloth: fine_cloth input(0.8) + paper input(0.5) + bldg maint(0.1)
    #   + construction(opera/theater avg 0.5)
    "cloth":       1.9,
    # beer: never consumed as input or construction
    "beer":        0.0,
    # tools: production inputs(2.7) + construction(avg 0.5)
    "tools":       3.2,
    # pottery: distillers(0.1) + saltpeter(0.2)
    "pottery":     0.3,
    # masonry: zero production input BUT massive construction demand:
    #   guild(0.5) + workshop(1.0) + manufactory(2.0) + mill(4.0) + village(0.25)
    #   + town_building(0.75) + forts(1-6) + capital(5) + granary(0.5) ≈ avg 1.2
    "masonry":     1.2,
    # furniture: admin maint(0.1)
    "furniture":   0.1,
    # leather: no significant building production input or construction
    "leather":     0.0,
    # glass: distillers(0.1) + bldg maint(0.5) + construction(avg 0.4)
    "glass":       1.0,
    # paper: books input(0.3) + bldg maint(1.2) + construction(avg 0.5)
    "paper":       2.0,
    # weaponry: hunting input(0.05) + order buildings(0.25)
    "weaponry":    0.3,
    # fine_cloth: admin maint(0.4) + construction(capital/important avg 0.5)
    "fine_cloth":  0.9,
    # books: construction(school/library/university avg 0.3)
    "books":       0.3,
    # liquor: incense production(0.2)
    "liquor":      0.2,
    # jewelry, porcelain, lacquerware: negligible
    "jewelry":     0.0,
    "porcelain":   0.0,
    "lacquerware": 0.0,

    # ── Raw materials ───────────────────────────────────────────
    # salt: fishing(0.05) + caravan construction(0.1)
    "salt":        0.15,
    # lumber: production inputs(4.7) + construction(avg 0.8)
    "lumber":      5.5,
    # medicaments: no building consumption
    "medicaments": 0.0,
    # wine: distillers(0.85)
    "wine":        0.85,
    # incense, tea, coffee, cocoa, tobacco, fur, spices: never consumed
    "incense":     0.0,
    "tea":         0.0,
    "coffee":      0.0,
    "cocoa":       0.0,
    "sugar":       0.6,   # distillers(0.6)
    "tobacco":     0.0,
    "fur":         0.0,
    "spices":      0.0,
}

# ================================================================
#  LEVER 5: BUILDING TIERS
#  output:     production multiplier relative to guild (1.0x)
#  employment: pop units employed per building level
#  pop_type:   which pop type works this building tier
#
#  Building a guild creates BURGHERS who then demand upper/luxury goods.
#  Building a mill creates LABORERS. Villages create PEASANTS.
#  The producer pop type is itself a demand driver.
#
#  Supply-demand ratio: how many producer pops per demand pop unit?
#    producers_per_demand = price_factor × employment / (target × output)
# ================================================================

BUILDING_TIERS = {
    "village":      {"output": 0.5,  "employment": 1.0,  "pop_type": "peasants"},
    "rural":        {"output": 1.0,  "employment": 1.0,  "pop_type": "laborers"},
    "guild":        {"output": 1.0,  "employment": 0.2,  "pop_type": "burghers"},
    "workshop":     {"output": 1.1,  "employment": 0.25, "pop_type": "burghers"},
    "manufactory":  {"output": 2.0,  "employment": 0.3,  "pop_type": "burghers"},
    "mill":         {"output": 4.0,  "employment": 0.5,  "pop_type": "laborers"},
    "plantation":   {"output": 1.0,  "employment": 1.0,  "pop_type": "slaves"},
}

# Legacy accessor for display functions
TIER_MULTIPLIERS = {k: v["output"] for k, v in BUILDING_TIERS.items()}

# ================================================================
#  LEVER 6: GOODS DEFINITIONS
#
#  category  : which target tier (necessity/common/upper/luxury)
#  source    : "produced" (guilds/workshops) or "raw" (RGOs)
#  output    : base production at guild tier (produced) or RGO base (raw)
#  price     : default_market_price from vanilla
#  consumers : which pop types demand this good.
#              Listed types OVERRIDE the price threshold — if you
#              explicitly list peasants, they demand it even if
#              the price would normally exclude them.
#  modifiers : (optional) per-class multiplier on top of weight.
#
#  consumer_share is DERIVED from BUILDING_CONSUMPTION, not set here.
#  consumer_share = output / (output + building_consumption)
#
#  Threshold (auto-derived): food_consumption >= price / THRESHOLD_SCALE
#  Any pop meeting the threshold demands the good UNLESS excluded
#  by not being in consumers (consumers acts as the maximum set).
# ================================================================

GOODS = [
    # ─── NECESSITIES ─────────────────────────────────────────────
    # Everyone needs these. You're always building more.

    # Clothing, canvas, uniforms — broad personal demand. Some cloth goes to fine_cloth production.
    {"name": "cloth",       "category": "necessity", "source": "produced", "output": 1.0, "price": 3,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants", "slaves"]},

    # Cheap alcohol — almost entirely personal consumption
    {"name": "beer",        "category": "necessity", "source": "produced", "output": 1.0, "price": 2,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]},

    # Working implements — mostly consumed by buildings (farms, mines, workshops all need tools)
    {"name": "tools",       "category": "necessity", "source": "produced", "output": 1.0, "price": 3,

     "consumers": ["burghers", "soldiers", "laborers", "peasants"]},

    # Cheap ceramics — mostly personal household use
    {"name": "pottery",     "category": "necessity", "source": "produced", "output": 1.0, "price": 2,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]},

    # Bricks, construction materials — almost entirely consumed by buildings/construction
    {"name": "masonry",     "category": "necessity", "source": "produced", "output": 1.0, "price": 2,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]},

    # ─── COMMON ──────────────────────────────────────────────────
    # Broadly useful. A few buildings satisfy a location.

    # Universal preservative — personal food use. Some used in production (leather tanning, etc.)
    {"name": "salt",        "category": "common",    "source": "raw",      "output": 0.3, "price": 2,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]},

    # Construction timber — mostly consumed by buildings (construction, shipbuilding, furniture)
    {"name": "lumber",      "category": "common",    "source": "raw",      "output": 1.0, "price": 1.5,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]},

    # Household furnishings — mostly personal consumption
    {"name": "furniture",   "category": "common",    "source": "produced", "output": 1.0, "price": 3,

     "consumers": ["nobles", "clergy", "burghers", "laborers", "peasants"]},

    # Boots, belts, armor components — personal + military. Some used in production.
    {"name": "leather",     "category": "common",    "source": "produced", "output": 1.0, "price": 3,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"],
     "modifiers": {"soldiers": 3}},

    # Windows, bottles, lenses — personal + construction/industrial use
    {"name": "glass",       "category": "common",    "source": "produced", "output": 0.75, "price": 2,

     "consumers": ["nobles", "clergy", "burghers", "laborers"]},

    # Writing material — personal + institutional. Used in books production.
    {"name": "paper",       "category": "common",    "source": "produced", "output": 1.0, "price": 2,

     "consumers": ["nobles", "clergy", "burghers"]},

    # Herbal remedies, medicines — almost entirely personal consumption
    {"name": "medicaments", "category": "common",    "source": "raw",      "output": 0.5, "price": 1,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants", "slaves"]},

    # Swords, spears, bows — military procurement is institutional, personal demand lower
    {"name": "weaponry",    "category": "common",    "source": "produced", "output": 1.0, "price": 3,

     "consumers": ["nobles", "soldiers", "laborers", "peasants"],
     "modifiers": {"soldiers": 3, "nobles": 2}},

    # ─── UPPER ───────────────────────────────────────────────────
    # Wealthy classes primarily. A couple buildings suffices.

    # Silks, embroidery, luxury clothing — personal consumption
    {"name": "fine_cloth",  "category": "upper",     "source": "produced", "output": 0.6, "price": 6,

     "consumers": ["nobles", "clergy", "burghers"]},

    # Books, pamphlets — personal + institutional
    {"name": "books",       "category": "upper",     "source": "produced", "output": 1.0, "price": 5,

     "consumers": ["nobles", "clergy", "burghers"],
     "modifiers": {"clergy": 2}},

    # Grape wine — personal consumption
    {"name": "wine",        "category": "upper",     "source": "raw",      "output": 1.0, "price": 2,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers"]},

    # Distilled spirits — personal consumption. Some used in medicaments/production.
    {"name": "liquor",      "category": "upper",     "source": "produced", "output": 1.0, "price": 2.5,

     "consumers": ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]},

    # Frankincense, myrrh — religious/personal consumption
    {"name": "incense",     "category": "upper",     "source": "raw",      "output": 1.0, "price": 2.5,

     "consumers": ["nobles", "clergy", "burghers"],
     "modifiers": {"clergy": 5}},

    # Luxury beverages — personal consumption
    {"name": "tea",         "category": "upper",     "source": "raw",      "output": 1.0, "price": 3,

     "consumers": ["nobles", "clergy", "burghers"]},

    {"name": "coffee",      "category": "upper",     "source": "raw",      "output": 1.0, "price": 3,

     "consumers": ["nobles", "clergy", "burghers", "soldiers"]},

    {"name": "cocoa",       "category": "upper",     "source": "raw",      "output": 1.0, "price": 4,

     "consumers": ["nobles", "clergy", "burghers"]},

    # Colonial trade goods — personal consumption. Sugar also used in production (liquor, etc.)
    {"name": "sugar",       "category": "upper",     "source": "raw",      "output": 1.0, "price": 3,

     "consumers": ["nobles", "clergy", "burghers"]},

    {"name": "tobacco",     "category": "upper",     "source": "raw",      "output": 1.0, "price": 3,

     "consumers": ["nobles", "clergy", "burghers"]},

    # ─── LUXURIES ────────────────────────────────────────────────
    # Elites only. One building oversupplies.

    {"name": "jewelry",     "category": "luxury",    "source": "produced", "output": 1.0, "price": 5,

     "consumers": ["nobles", "clergy", "burghers"]},

    {"name": "porcelain",   "category": "luxury",    "source": "produced", "output": 1.0, "price": 3,

     "consumers": ["nobles", "clergy", "burghers"]},

    {"name": "lacquerware", "category": "luxury",    "source": "produced", "output": 1.0, "price": 5,

     "consumers": ["nobles", "clergy", "burghers"]},

    # Fur clothing/trim — drove colonial expansion (Hudson's Bay, Russian fur trade).
    # Vanilla price 2 is trade cost; actual demand status is high luxury. Price 5.
    {"name": "fur",         "category": "luxury",    "source": "raw",      "output": 1.0, "price": 5,

     "consumers": ["nobles", "clergy", "burghers"],
     "modifiers": {"nobles": 2}},

    # Spices — grouped as representative (saffron/pepper/cloves/chili all price 5)
    {"name": "spices",      "category": "luxury",    "source": "raw",      "output": 1.0, "price": 5,

     "consumers": ["nobles", "clergy", "burghers"]},
]

# ================================================================
#  LEVER 7: SAMPLE LOCATION
# ================================================================

LOCATION_POP_UNITS = 5.0
LOCATION_BUILDING_SLOTS = 30


# ================================================================
#  CURRENT VANILLA/SUL VALUES (for comparison)
# ================================================================

CURRENT_VALUES = {
    # EFFECTIVE demand per pop type: demand_add × demand_multiply (stacked)
    # Source: vanilla goods files + SUL INJECT overrides

    "cloth":       {"clergy": 0.02, "burghers": 0.01, "soldiers": 0.001, "laborers": 0.0005, "peasants": 0.0005, "slaves": 0.0002},
    "beer":        {"nobles": 0.016, "clergy": 0.008, "burghers": 0.008, "soldiers": 0.0066, "laborers": 0.0056, "peasants": 0.0066},
    "tools":       {"laborers": 0.001},
    "pottery":     {"nobles": 0.006, "clergy": 0.006, "burghers": 0.0072, "soldiers": 0.006, "laborers": 0.0066, "peasants": 0.006},
    "masonry":     {"nobles": 0.000015, "clergy": 0.000015, "burghers": 0.000018, "soldiers": 0.000015, "laborers": 0.0000165, "peasants": 0.000015},
    "salt":        {"nobles": 0.05, "burghers": 0.02, "clergy": 0.02},
    "lumber":      {"nobles": 0.00125, "clergy": 0.00125, "burghers": 0.00125, "soldiers": 0.00025, "laborers": 0.00025, "peasants": 0.00025},
    "furniture":   {"nobles": 0.02, "clergy": 0.01, "burghers": 0.01, "soldiers": 0.001, "laborers": 0.001, "peasants": 0.001},
    "leather":     {},
    "glass":       {},
    "paper":       {"nobles": 0.01, "burghers": 0.02, "clergy": 0.04},
    "medicaments": {"nobles": 0.006, "clergy": 0.003, "burghers": 0.0018, "soldiers": 0.0012, "laborers": 0.0012, "peasants": 0.0012},
    "weaponry":    {"nobles": 0.1, "soldiers": 0.0025, "laborers": 0.0005, "peasants": 0.0005},
    "fine_cloth":  {"nobles": 0.2, "burghers": 0.025, "clergy": 0.025},
    "books":       {"nobles": 0.01, "burghers": 0.02, "clergy": 0.04},
    "wine":        {"nobles": 0.018, "clergy": 0.012, "burghers": 0.012, "soldiers": 0.0012, "laborers": 0.0012},
    "liquor":      {"nobles": 0.008, "clergy": 0.004, "burghers": 0.004, "soldiers": 0.0033, "laborers": 0.0028, "peasants": 0.0033},
    "incense":     {"clergy": 0.01},
    "tea":         {"nobles": 0.2, "burghers": 0.01, "clergy": 0.01},
    "coffee":      {"nobles": 0.01, "burghers": 0.001, "clergy": 0.0005, "soldiers": 0.001},
    "cocoa":       {"nobles": 0.1, "burghers": 0.01, "clergy": 0.01},
    "sugar":       {"nobles": 0.05, "burghers": 0.005, "clergy": 0.005},
    "tobacco":     {"nobles": 0.05, "burghers": 0.005, "clergy": 0.005},
    "jewelry":     {"nobles": 0.1, "burghers": 0.005},
    "porcelain":   {"nobles": 0.01, "clergy": 0.0005, "burghers": 0.0005},
    "lacquerware": {"nobles": 0.05, "burghers": 0.02},
    "fur":         {"nobles": 0.5, "clergy": 0.05, "burghers": 0.05},
    "spices":      {"nobles": 0.05, "burghers": 0.0025, "clergy": 0.005},
}


# ================================================================
#  COMPUTATION
# ================================================================

def get_max_target():
    return max(CATEGORY_TARGETS.values())


def get_spread(target):
    """Derive class spread from category target.
    Higher target (luxury) → spread closer to 1.0 (full hierarchy).
    Lower target (necessity) → spread closer to 0 (flat demand)."""
    max_t = get_max_target()
    if max_t <= 0:
        return 1.0
    return (target / max_t) ** SPREAD_CURVE


def get_weight(food_cons, spread):
    """Compute class weight from food_consumption + spread.
    spread=0 → everyone weighs 1 (flat).
    spread=1 → weight = food_consumption (full hierarchy)."""
    return 1.0 + (food_cons - 1.0) * spread


def price_factor(price):
    """Demand magnitude scaling from price.
    Cheap goods → higher demand, expensive → lower.
    Returns 1.0 at REFERENCE_PRICE."""
    if PRICE_CURVE == 0 or price <= 0:
        return 1.0
    raw = REFERENCE_PRICE / price
    if PRICE_CURVE == 1.0:
        return raw
    return raw ** PRICE_CURVE


def affordability(food_cons, price):
    """Continuous affordability curve: how much of full demand this pop gets.
    Returns 1.0 when food_cons is high relative to price, tapers toward 0.
    Same variables as the old hard threshold, just continuous.
    affordability = min(1.0, food_cons × THRESHOLD_SCALE / price)"""
    if THRESHOLD_SCALE <= 0 or price <= 0:
        return 1.0
    return min(1.0, food_cons * THRESHOLD_SCALE / price)


def compute():
    results = []
    for g in GOODS:
        cat = g["category"]
        target = CATEGORY_TARGETS[cat]
        output = g["output"]
        price = g.get("price", REFERENCE_PRICE)
        source = g.get("source", "produced")
        consumer_list = set(g.get("consumers", []))
        modifiers = g.get("modifiers", {})

        bldg_cons = BUILDING_CONSUMPTION.get(g["name"], 0)
        cs = output / (output + bldg_cons) if (output + bldg_cons) > 0 else 1.0
        spread = get_spread(target)
        pf = price_factor(price)

        # Determine eligible consumers:
        # - Must be in consumer_list (the maximum set)
        # - Must have food_consumption > 0
        # - Affordability scales demand continuously (no hard cutoff)
        consumers = set()
        excluded = set()
        for p in POP_TYPES:
            if p not in consumer_list:
                continue
            fc = FOOD_CONSUMPTION[p]
            if fc <= 0:
                excluded.add(p)
            else:
                consumers.add(p)

        # Compute weights: class_weight × affordability × modifier
        weights = {}
        afford = {}
        for p in consumers:
            fc = FOOD_CONSUMPTION[p]
            aff = affordability(fc, price)
            afford[p] = aff
            w = get_weight(fc, spread) * aff
            weights[p] = w * modifiers.get(p, 1.0)

        # demand_add = output × pf × weight × consumer_share / target
        # consumer_share scales down pop demand for goods where buildings
        # are the primary consumers (tools, lumber, masonry)
        effective = {}
        for p in POP_TYPES:
            if p in consumers:
                effective[p] = output * pf * weights[p] * cs / target
            else:
                effective[p] = 0.0

        demand_add = {p: effective[p] for p in POP_TYPES if effective[p] > 0}

        results.append({
            "name": g["name"],
            "category": cat,
            "source": source,
            "target": target,
            "output": output,
            "price": price,
            "price_factor": pf,
            "spread": spread,
            "consumer_share": cs,
            "weights": weights,
            "afford": afford,
            "effective": effective,
            "demand_add": demand_add,
            "consumers": consumers,
            "excluded": excluded,
            "modifiers": modifiers,
        })

    return results


# ================================================================
#  DISPLAY
# ================================================================

COL_TYPES = ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]
COL_LABELS = ["noble", "clergy", "burghr", "soldr", "labor", "peasnt"]
COL_FOOD = [FOOD_CONSUMPTION[p] for p in COL_TYPES]
CAT_ORDER = ["necessity", "common", "upper", "luxury"]


def section(title):
    w = 76
    print(f"\n{'━' * w}")
    print(f"  {title}")
    print(f"{'━' * w}")


def print_config():
    section("CONFIGURATION")
    max_t = get_max_target()

    print("\n  Category targets + derived spread:")
    print(f"  {'Category':<12s} {'Target':>8s} {'Spread':>8s} {'Nob:Pea ratio'}")
    print(f"  {'─' * 12} {'─' * 8} {'─' * 8} {'─' * 16}")
    for cat in CAT_ORDER:
        t = CATEGORY_TARGETS[cat]
        s = get_spread(t)
        w_noble = get_weight(FOOD_CONSUMPTION["nobles"], s)
        w_peasant = get_weight(FOOD_CONSUMPTION["peasants"], s)
        ratio = w_noble / w_peasant if w_peasant > 0 else float('inf')
        print(f"  {cat:<12s} {t:>8.0f} {s:>8.2f} {ratio:>6.1f} : 1")

    print(f"\n  System parameters:")
    print(f"    SPREAD_CURVE    = {SPREAD_CURVE:.2f}  (target→spread aggressiveness)")
    print(f"    PRICE_CURVE     = {PRICE_CURVE:.2f}  (price→demand magnitude)")
    print(f"    REFERENCE_PRICE = {REFERENCE_PRICE:.1f}  (neutral price)")
    print(f"    THRESHOLD_SCALE = {THRESHOLD_SCALE:.1f}  (food_cons >= price/scale)")

    print(f"\n  Affordability by price (fc × {THRESHOLD_SCALE:.0f} / price, capped at 1.0):")
    aff_types = ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants", "slaves"]
    aff_labels = ["noble", "clergy", "burghr", "soldr", "labor", "peasnt", "slave"]
    print(f"    {'price':>6s}", end="")
    for label in aff_labels:
        print(f" {label:>7s}", end="")
    print()
    print(f"    {'─' * 6}", end="")
    for _ in aff_labels:
        print(f" {'─' * 7}", end="")
    print()
    for pr in [1, 2, 3, 4, 5, 6, 8, 10]:
        print(f"    {pr:>6d}", end="")
        for p in aff_types:
            aff = affordability(FOOD_CONSUMPTION[p], pr)
            if aff >= 1.0:
                print(f"    1.0", end="")
            else:
                print(f"   {aff:>.2f}", end="")
        print()

    print(f"\n  Food consumption anchor:")
    parts = [f"{p}: {FOOD_CONSUMPTION[p]:.0f}" for p in POP_TYPES if FOOD_CONSUMPTION[p] > 0]
    print(f"    {', '.join(parts)}")

    print(f"\n  Pop composition: determined by game (no assumed mix)")

    print(f"\n  Location: {LOCATION_POP_UNITS:.0f} pop units, "
          f"{LOCATION_BUILDING_SLOTS} building slots")


def print_demands(results):
    section("COMPUTED DEMAND VALUES")

    for cat in CAT_ORDER:
        goods = [r for r in results if r["category"] == cat]
        if not goods:
            continue
        spread = get_spread(CATEGORY_TARGETS[cat])
        print(f"\n  [{cat.upper()}]  target={CATEGORY_TARGETS[cat]:.0f}  spread={spread:.2f}")
        print(f"  {'Good':<14s} {'Src':>4s} {'Price':>6s} {'Prc.F':>6s} {'CShr':>5s} {'Consumers'}")
        print(f"  {'─' * 14} {'─' * 4} {'─' * 6} {'─' * 6} {'─' * 5} {'─' * 28}")
        for r in goods:
            nc = len(r["consumers"])
            excl = r["excluded"]
            mods = r["modifiers"]
            src = "raw" if r["source"] == "raw" else "prod"
            parts = []
            if excl:
                parts.append(f"{nc}/{nc + len(excl)}")
                parts.append(f"-{','.join(sorted(p[:3] for p in excl))}")
            else:
                parts.append(f"({nc})")
            if mods:
                parts.append("+" + ",".join(f"{k[:3]}×{v}" for k, v in mods.items()))
            cons_str = " ".join(parts)
            print(f"  {r['name']:<14s} {src:>4s} {r['price']:>6.1f} {r['price_factor']:>6.2f} "
                  f"{r['consumer_share']:>5.0%} {cons_str}")


def print_effective(results):
    section("EFFECTIVE DEMAND PER POP UNIT")
    print(f"  weight = spread_weight × affordability × modifier")
    print(f"\n  {'Good':<14s} {'sprd':>5s}", end="")
    for label in COL_LABELS:
        print(f" {label:>8s}", end="")
    print()
    print(f"  {'(food_cons)':<14s} {'':>5s}", end="")
    for f in COL_FOOD:
        print(f" {f:>7.0f}×", end="")
    print()
    print(f"  {'─' * 14} {'─' * 5}", end="")
    for _ in COL_LABELS:
        print(f" {'─' * 8}", end="")
    print()

    last_cat = None
    for r in results:
        if r["category"] != last_cat:
            if last_cat:
                print()
            last_cat = r["category"]
        print(f"  {r['name']:<14s} {r['spread']:>5.2f}", end="")
        for c in COL_TYPES:
            v = r["effective"].get(c, 0)
            aff = r["afford"].get(c, 1.0)
            if v > 0 and aff < 1.0:
                # Show reduced demand with affordability marker
                print(f" {v:>7.4f}~", end="")
            elif v > 0:
                print(f" {v:>8.4f}", end="")
            else:
                print(f" {'·':>8s}", end="")
        print()


def print_weights(results):
    section("CLASS WEIGHTS  (how spread compresses the hierarchy)")
    print(f"\n  {'Category':<12s} {'Spread':>6s}", end="")
    for label in COL_LABELS:
        print(f" {label:>8s}", end="")
    print()
    print(f"  {'─' * 12} {'─' * 6}", end="")
    for _ in COL_LABELS:
        print(f" {'─' * 8}", end="")
    print()

    for cat in CAT_ORDER:
        t = CATEGORY_TARGETS[cat]
        s = get_spread(t)
        print(f"  {cat:<12s} {s:>6.2f}", end="")
        for c in COL_TYPES:
            w = get_weight(FOOD_CONSUMPTION[c], s)
            print(f" {w:>8.2f}", end="")
        print()

    print(f"\n  {'(full fc)':<12s} {'1.00':>6s}", end="")
    for c in COL_TYPES:
        print(f" {FOOD_CONSUMPTION[c]:>8.1f}", end="")
    print()


def print_satisfaction(results):
    section("POPS SATISFIED PER BUILDING  (by tier, produced goods only)")
    tiers = [("guild", 1.0), ("workshop", 1.1), ("manuf.", 2.0), ("mill", 4.0)]

    produced = [r for r in results if r["source"] == "produced"]
    if not produced:
        print("\n  (no produced goods)")
        return

    print(f"\n  {'Good':<14s}", end="")
    for name, _ in tiers:
        print(f" {name:>10s}", end="")
    print()
    print(f"  {'─' * 14}", end="")
    for _ in tiers:
        print(f" {'─' * 10}", end="")
    print()

    last_cat = None
    for r in produced:
        if r["category"] != last_cat:
            if last_cat:
                print()
            last_cat = r["category"]
        eff_target = r["target"] / r["price_factor"]
        print(f"  {r['name']:<14s}", end="")
        for _, mult in tiers:
            pops = eff_target * mult
            print(f" {pops:>10.1f}", end="")
        print()


def print_location(results, pop_units=None, slots=None):
    pop_units = pop_units or LOCATION_POP_UNITS
    slots = slots or LOCATION_BUILDING_SLOTS

    produced = [r for r in results if r["source"] == "produced"]
    if not produced:
        return

    section(f"LOCATION VIEW: {pop_units:.0f} POP UNITS, {slots} SLOTS  (produced only)")

    tiers_show = [("guild", 1.0), ("wkshop", 1.1), ("manuf.", 2.0), ("mill", 4.0)]

    print(f"\n  {'Good':<14s} {'Cat.':<10s}", end="")
    for name, _ in tiers_show:
        print(f" {name:>8s}", end="")
    print()
    print(f"  {'─' * 14} {'─' * 10}", end="")
    for _ in tiers_show:
        print(f" {'─' * 8}", end="")
    print()

    cat_totals = {}
    grand = {name: 0 for name, _ in tiers_show}

    last_cat = None
    for r in produced:
        cat = r["category"]
        if cat != last_cat:
            if last_cat:
                print()
            last_cat = cat
        if cat not in cat_totals:
            cat_totals[cat] = {name: 0 for name, _ in tiers_show}

        eff_target = r["target"] / r["price_factor"]
        vals = {}
        for name, mult in tiers_show:
            b = pop_units / (eff_target * mult)
            vals[name] = b
            cat_totals[cat][name] += b
            grand[name] += b

        print(f"  {r['name']:<14s} {cat:<10s}", end="")
        for name, _ in tiers_show:
            print(f" {vals[name]:>8.1f}", end="")
        print()

    print(f"\n  {'─' * 14} {'─' * 10}", end="")
    for _ in tiers_show:
        print(f" {'─' * 8}", end="")
    print()

    for cat in CAT_ORDER:
        if cat not in cat_totals:
            continue
        print(f"  {'':14s} {cat:<10s}", end="")
        for name, _ in tiers_show:
            print(f" {cat_totals[cat][name]:>8.1f}", end="")
        print()

    print(f"  {'':14s} {'TOTAL':<10s}", end="")
    for name, _ in tiers_show:
        print(f" {grand[name]:>8.1f}", end="")
    print()

    # Slot budget at guild tier
    used = grand["guild"]
    free = slots - used
    print(f"\n  Slot budget (guild tier):")
    for cat in CAT_ORDER:
        if cat not in cat_totals:
            continue
        g = cat_totals[cat]["guild"]
        pct = g / slots * 100
        bar = "█" * int(pct / 2)
        print(f"    {cat:<12s} {g:>5.1f} ({pct:>4.0f}%)  {bar}")
    pct = max(0, free / slots * 100)
    bar = "░" * int(pct / 2)
    print(f"    {'remaining':<12s} {free:>5.1f} ({pct:>4.0f}%)  {bar}")


def print_supply_demand(results):
    """Show producer pops needed per demand pop unit, broken down by tier.

    Key insight: building tier determines WHICH pop type works there.
    Guild/workshop/manufactory → burghers. Mill/RGO → laborers.
    Village → peasants. Plantation → slaves.

    Building a cloth guild doesn't just produce cloth — it creates burghers
    who then demand fine_cloth, books, jewelry at the burgher consumption rate.
    """
    section("SUPPLY-DEMAND BALANCE")
    print(f"  Producers per demand pop unit = pf × employment / (target × output)")
    print(f"  Each tier shows: [ratio] as [pop_type]")

    # Tier groups for display
    raw_tier_keys = ["village", "rural", "plantation"]
    prod_tier_keys = ["guild", "workshop", "manufactory", "mill"]
    raw_tier_labels = ["village", "rural", "plantn"]
    prod_tier_labels = ["guild", "wkshop", "manuf.", "mill"]

    def tier_ratio(r, tier_key):
        tier = BUILDING_TIERS[tier_key]
        return r["price_factor"] * tier["employment"] / (r["target"] * tier["output"])

    def pop_label(tier_key):
        return BUILDING_TIERS[tier_key]["pop_type"][:3]

    # --- RAW MATERIALS ---
    raw_goods = [r for r in results if r["source"] == "raw"]
    if raw_goods:
        print(f"\n  RAW MATERIALS:")
        print(f"  {'Good':<14s} {'Cat.':<10s}", end="")
        for i, label in enumerate(raw_tier_labels):
            pt = pop_label(raw_tier_keys[i])
            print(f" {label + '(' + pt + ')':>14s}", end="")
        print()
        print(f"  {'─' * 14} {'─' * 10}", end="")
        for _ in raw_tier_labels:
            print(f" {'─' * 14}", end="")
        print()

        for r in raw_goods:
            print(f"  {r['name']:<14s} {r['category']:<10s}", end="")
            for tk in raw_tier_keys:
                ratio = tier_ratio(r, tk)
                print(f" {ratio:>14.4f}", end="")
            print()

    # --- PRODUCED GOODS ---
    produced = [r for r in results if r["source"] == "produced"]
    if produced:
        print(f"\n  PRODUCED GOODS:")
        print(f"  {'Good':<14s} {'Cat.':<10s}", end="")
        for i, label in enumerate(prod_tier_labels):
            pt = pop_label(prod_tier_keys[i])
            print(f" {label + '(' + pt + ')':>14s}", end="")
        print()
        print(f"  {'─' * 14} {'─' * 10}", end="")
        for _ in prod_tier_labels:
            print(f" {'─' * 14}", end="")
        print()

        last_cat = None
        for r in produced:
            if r["category"] != last_cat:
                if last_cat:
                    print()
                last_cat = r["category"]
            print(f"  {r['name']:<14s} {r['category']:<10s}", end="")
            for tk in prod_tier_keys:
                ratio = tier_ratio(r, tk)
                print(f" {ratio:>14.4f}", end="")
            print()

    # --- POP TYPE BUDGET ---
    # For a reference market: how many of each pop type are needed as producers?
    print(f"\n  POP TYPE BUDGET (all goods, base tier per source):")
    print(f"  How many pop units of each type must be producers?")

    # Accumulate by pop type
    pop_budget = {}
    for r in results:
        if r["source"] == "raw":
            # Use rural as reference tier for raw materials
            tier = BUILDING_TIERS["rural"]
        else:
            # Use guild as reference tier for produced goods
            tier = BUILDING_TIERS["guild"]
        pt = tier["pop_type"]
        ratio = r["price_factor"] * tier["employment"] / (r["target"] * tier["output"])
        pop_budget.setdefault(pt, {"total": 0.0, "goods": []})
        pop_budget[pt]["total"] += ratio
        pop_budget[pt]["goods"].append((r["name"], ratio))

    grand_total = sum(v["total"] for v in pop_budget.values())
    for pt in ["burghers", "laborers", "peasants", "slaves"]:
        if pt not in pop_budget:
            continue
        info = pop_budget[pt]
        goods_str = ", ".join(f"{n}" for n, _ in info["goods"])
        print(f"    {pt:<12s} {info['total']:>8.4f}  ({info['total'] * 100:>5.1f}%)  "
              f"← {len(info['goods'])} goods")

    print(f"    {'TOTAL':<12s} {grand_total:>8.4f}  ({grand_total * 100:>5.1f}%)")

    # --- DEMAND FEEDBACK ---
    # Each producer pop also demands goods. Show the demand their pop type generates.
    print(f"\n  DEMAND FEEDBACK (each producer also consumes):")
    print(f"  Building guilds creates burghers → more demand for upper/luxury goods")
    print(f"  Building mills creates laborers → more demand for common goods")

    for pt in ["burghers", "laborers", "peasants"]:
        fc = FOOD_CONSUMPTION[pt]
        consumes = []
        for r in results:
            eff = r["effective"].get(pt, 0)
            if eff > 0:
                consumes.append((r["name"], eff))
        consumes.sort(key=lambda x: -x[1])
        top = consumes[:5]
        if top:
            top_str = ", ".join(f"{n}({v:.4f})" for n, v in top)
            print(f"    {pt:<12s} fc={fc:>4.0f}  top demand: {top_str}")


def print_comparison(results):
    section("VS CURRENT VALUES  (proposed / current ratio)")
    print(f"\n  {'Good':<14s}", end="")
    for label in COL_LABELS:
        print(f" {label:>8s}", end="")
    print()
    print(f"  {'─' * 14}", end="")
    for _ in COL_LABELS:
        print(f" {'─' * 8}", end="")
    print()

    for r in results:
        name = r["name"]
        cur = CURRENT_VALUES.get(name, {})
        if not cur:
            continue
        print(f"  {name:<14s}", end="")
        for c in COL_TYPES:
            proposed = r["effective"].get(c, 0)
            current = cur.get(c, cur.get("all", 0))
            if proposed > 0 and current > 0:
                ratio = proposed / current
                if ratio >= 100:
                    print(f" {ratio:>7.0f}×", end="")
                elif ratio >= 10:
                    print(f" {ratio:>7.1f}×", end="")
                else:
                    print(f" {ratio:>7.2f}×", end="")
            elif proposed > 0 and current == 0:
                print(f" {'NEW':>8s}", end="")
            else:
                print(f" {'·':>8s}", end="")
        print()


def print_pdx(results):
    section("PDX SCRIPT OUTPUT")
    print()
    print("# Generated by demand_calculator.py")
    print("# Interconnected system: spread derived from target, threshold from food_cons/price")
    print("# demand_add per type (pre-multiplied, no demand_multiply needed)")
    print()

    for r in results:
        name = r["name"]
        da = r["demand_add"]

        print(f"# {name} [{r['category']}/{r['source']}] target={r['target']:.0f} "
              f"spread={r['spread']:.2f} price={r['price']:.1f} (×{r['price_factor']:.2f})")
        print(f"INJECT:{name} = {{")
        print(f"\tdemand_add = {{")
        for p in POP_TYPES:
            if p in da:
                print(f"\t\t{p} = {da[p]:.6f}")
        print(f"\t}}")
        print(f"}}")
        print()


# ================================================================
#  MAIN
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Demand System Calculator — interconnected price/food_consumption design"
    )
    parser.add_argument("--compact", action="store_true",
                        help="Summary tables only")
    parser.add_argument("--pdx", action="store_true",
                        help="Output PDX script format")
    parser.add_argument("--location", type=float, metavar="N",
                        help="Override location pop units")
    parser.add_argument("--slots", type=int, metavar="N",
                        help="Override location building slots")
    args = parser.parse_args()

    if args.location:
        global LOCATION_POP_UNITS
        LOCATION_POP_UNITS = args.location
    if args.slots:
        global LOCATION_BUILDING_SLOTS
        LOCATION_BUILDING_SLOTS = args.slots

    results = compute()

    if args.pdx:
        print_pdx(results)
        return

    print_config()
    print_demands(results)
    print_effective(results)

    if not args.compact:
        print_weights(results)
        print_satisfaction(results)
        print_supply_demand(results)
        print_location(results)
        print_comparison(results)


if __name__ == "__main__":
    main()
