#!/usr/bin/env python3
"""
Demand System Calculator for Specialized Urban Locations
========================================================

Computes demand_add values for EU5 pop goods using an interconnected system
where price and food_consumption drive class hierarchy, thresholds, and
demand magnitude from a small set of global parameters.

FORMULA:
  target         = CATEGORY_BASE[cat] × (price / REFERENCE_PRICE) ^ TARGET_PRICE_CURVE
  spread         = (CATEGORY_BASE[cat] / max_base) ^ SPREAD_CURVE
  class_weight   = 1 + (food_consumption - 1) * spread
  affordability  = min(1, fc * THRESHOLD_SCALE / price) ^ AFFORDABILITY_CURVE
  price_factor   = (REFERENCE_PRICE / price) ^ PRICE_CURVE
  consumer_share = output / (output + building_consumption)
  refinement     = min(1, price * REFINEMENT_SCALE / fc) ^ REFINEMENT_CURVE
  weight         = class_weight * affordability * refinement
  demand_add     = output * price_factor * weight * consumer_share / target

  All pop types with food_consumption > 0 consume all goods.
  Category sets the spread (class hierarchy). Price adjusts the target (demand volume).
  Affordability gates who can afford expensive goods. Refinement dampens rich demand for cheap goods.

USAGE:
  python demand_calculator.py                # Full report
  python demand_calculator.py --compact      # Summary tables only
  python demand_calculator.py --pdx          # PDX INJECT blocks to stdout
  python demand_calculator.py --write        # Write to sul_goods_overrides.txt
  python demand_calculator.py --location 10  # Location with 10 pop units
"""

import sys
import argparse
import os
import re


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
#
# System parameters that define the demand formula behavior.
# Category targets are the primary design lever.
# ═══════════════════════════════════════════════════════════════════════════

# Path to vanilla game files. Scanned at startup for prices and demand values.
VANILLA_BASE = os.path.join(
    "/mnt/d/Program Files (x86)/Steam/steamapps/common",
    "Europa Universalis V/game/in_game/common")
VANILLA_GOODS_DIR = os.path.join(VANILLA_BASE, "goods")

# Mod game files — scanned for production methods alongside vanilla.
MOD_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "in_game", "common")

CATEGORY_BASES = {
    "necessity": 30,     # Always short, always building more
    "common":    75,     # Comfortable once established
    "upper":    150,     # One or two covers you
    "luxury":   300,     # One building oversupplies
}
CAT_ORDER = ["necessity", "common", "upper", "luxury"]

SPREAD_CURVE = 0.5       # How aggressively category -> spread. sqrt gives nice curve.
PRICE_CURVE = 0.5        # How aggressively price affects demand magnitude. sqrt.
TARGET_PRICE_CURVE = 1.0 # How aggressively price adjusts target (0=no effect, 1=linear)
REFERENCE_PRICE = 3.0    # Neutral price point (price_factor=1, target=base)
THRESHOLD_SCALE = 2.0    # Affordability: fc * scale / price, capped at 1.0
AFFORDABILITY_CURVE = 2.0  # Power curve on affordability (1=linear, 2=quadratic)
REFINEMENT_SCALE = 5.0   # Refinement: price * scale / fc, capped at 1.0
REFINEMENT_CURVE = 0.5   # Power curve on refinement (0.5=sqrt/soft, 1=linear, 2=quadratic)

POP_TYPES = [
    "nobles", "clergy", "burghers", "soldiers",
    "laborers", "peasants", "slaves", "tribesmen",
]

# Food consumption defines the class hierarchy and affordability thresholds.
# These are MOD design values (SUL overrides noted).
FOOD_CONSUMPTION = {
    "nobles":    20.0,
    "clergy":    10.0,   # SUL override (vanilla 5.0)
    "burghers":   8.0,   # SUL override (vanilla 4.0)
    "soldiers":   5.0,
    "laborers":   3.0,   # SUL override (vanilla 1.0)
    "peasants":   1.0,
    "slaves":     1.0,
    "tribesmen":  0.0,   # Never demands anything
}

BUILDING_TIERS = {
    "village":      {"output": 0.5,  "employment": 1.0,  "pop_type": "peasants"},
    "rural":        {"output": 1.0,  "employment": 1.0,  "pop_type": "laborers"},
    "guild":        {"output": 1.0,  "employment": 0.2,  "pop_type": "burghers"},
    "workshop":     {"output": 1.1,  "employment": 0.25, "pop_type": "burghers"},
    "manufactory":  {"output": 2.0,  "employment": 0.3,  "pop_type": "burghers"},
    "mill":         {"output": 4.0,  "employment": 0.5,  "pop_type": "laborers"},
    "plantation":   {"output": 1.0,  "employment": 1.0,  "pop_type": "slaves"},
}

LOCATION_POP_UNITS = 5.0
LOCATION_BUILDING_SLOTS = 30

# ═══════════════════════════════════════════════════════════════════════════
# BUILDING → GOOD MAPPING PER SPECIALIZATION
#
# Used to derive production weights from demand data. Each entry maps a
# building name to the good it produces. Split into rural and guild tiers.
# Only includes buildings that produce consumer goods tracked by the demand
# system. RGO/infrastructure buildings are handled separately.
# ═══════════════════════════════════════════════════════════════════════════

SPEC_BUILDINGS = {
    "mining": {
        "rural": {
            "sul_rural_blacksmith": "tools",
            "sul_rural_weaponmaker": "weaponry",
            "sul_rural_jeweler": "jewelry",
        },
        "guild": {
            "jewelry_guild": "jewelry",
            "tools_guild": "tools",
            "weapon_guild": "weaponry",
            "cannon_maker": "cannons",
        },
    },
    "farming": {
        "rural": {
            "sul_rural_brewer": "beer",
            "sul_rural_winemaker": "wine",
            "sul_rural_distiller": "liquor",
            "sul_rural_tanner": "leather",
        },
        "guild": {
            "brewery": "beer",
            "winery": "wine",
            "distillers_guild": "liquor",
        },
    },
    "gathering": {
        "rural": {
            "sul_rural_glassmaker": "glass",
            "sul_rural_potter": "pottery",
            "sul_rural_herbalist": "medicaments",
        },
        "guild": {
            "pottery_guild": "pottery",
            "glass_guild": "glass",
            "apothecary": "medicaments",
            "saltpeter_guild": "saltpeter",
        },
    },
    "woodland": {
        "rural": {
            "sul_rural_carpenter": "furniture",
            "sul_rural_papermaker": "paper",
            "sul_rural_apiary": "beeswax",
            "sul_rural_tanner": "leather",
        },
        "guild": {
            "furniture_guild": "furniture",
            "tannery": "leather",
            "dyes_guild": "dyes",
            "paper_guild": "paper",
            "lacquerware_guild": "lacquerware",
        },
    },
    "commercial": {
        "rural": {
            "rural_clothmaker": "cloth",
            "sul_rural_ropemaker": "naval_supplies",
        },
        "guild": {
            "marketplace": "cloth",          # trade building; proxy to cloth
            "cloth_guild": "cloth",
            "fine_cloth_guild": "fine_cloth",
            "naval_supplies_guild": "naval_supplies",
            "scriptorium": "books",
        },
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTION-ONLY GOODS
#
# Goods not consumed by pops but demanded by buildings. Computed at startup
# by scanning production methods from vanilla + mod files. Feed ONLY into
# building distribution weights, not PDX demand_add output.
#
# Populated by scan_production_demand() during startup.
# ═══════════════════════════════════════════════════════════════════════════

PRODUCTION_DEMAND = {}  # filled at runtime by scan_production_demand()

# Which goods to track for production demand.
# Only goods produced by spec buildings but not in the pop demand system.
PRODUCTION_GOODS = {
    "tools", "masonry", "cannons", "saltpeter",
    "naval_supplies", "dyes", "beeswax", "tar",
}

# Scale factor for production demand. The scanner sums consumption across ALL
# production methods globally, but a location only has ~5-10 buildings. This
# factor converts global PM sums to per-location scale comparable to pop demand.
# Set so the highest production good (tools) is roughly mid-range pop good level.
PRODUCTION_DEMAND_SCALE = 0.01


# ═══════════════════════════════════════════════════════════════════════════
# GOODS
#
# Each record defines our MOD's design intent for one good.
# Price and vanilla reference data are scanned from base game files at
# startup and merged into these entries automatically.
#
# Fields (design — set here):
#   name                : game identifier
#   category            : necessity / common / upper / luxury
#   source              : "produced" (guilds/workshops) or "raw" (RGOs)
#   output              : base production per building at guild/RGO tier
#   building_consumption: non-pop demand per building (inputs + construction)
#   vanilla_key         : (optional) vanilla good name if different from name
#
# All pop types consume all goods. Price + spread + affordability curve
# determine who demands how much — no per-good consumer lists or modifiers.
#
# Fields (scanned — added at startup by merge_vanilla):
#   price               : default_market_price from vanilla
#   vanilla             : {demand_add, demand_multiply, development_threshold}
# ═══════════════════════════════════════════════════════════════════════════

GOODS = [
    # ─── NECESSITIES ─────────────────────────────────────────────────────
    # Everyone needs these. You're always building more.

    # Clothing — broad personal demand, some goes to fine_cloth production
    {"name": "cloth", "category": "necessity", "source": "produced",
     "output": 1.0,
     "building_consumption": 1.9},  # fine_cloth(0.8)+paper(0.5)+maint(0.1)+construction(0.5)

    # Cheap alcohol — almost entirely personal consumption
    {"name": "beer", "category": "necessity", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.0},

    # Cheap ceramics — household use
    {"name": "pottery", "category": "necessity", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.3},  # distillers(0.1)+saltpeter(0.2)

    # ─── COMMON ──────────────────────────────────────────────────────────
    # Broadly useful. A few buildings satisfy a location.

    # Universal preservative — personal food use
    {"name": "salt", "category": "common", "source": "raw",
     "output": 0.3,
     "building_consumption": 0.15},  # fishing(0.05)+caravan construction(0.1)

    # Household furnishings
    {"name": "furniture", "category": "common", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.1},  # admin maint(0.1)

    # Boots, belts, armor — personal + military
    {"name": "leather", "category": "common", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.0},

    # Windows, bottles, lenses
    {"name": "glass", "category": "common", "source": "produced",
     "output": 0.75,
     "building_consumption": 1.0},  # distillers(0.1)+maint(0.5)+construction(0.4)

    # Writing material — personal + institutional
    {"name": "paper", "category": "common", "source": "produced",
     "output": 1.0,
     "building_consumption": 2.0},  # books input(0.3)+maint(1.2)+construction(0.5)

    # Herbal remedies, medicines
    {"name": "medicaments", "category": "common", "source": "raw",
     "output": 0.5,
     "building_consumption": 0.0},

    # Swords, spears, bows — military procurement
    {"name": "weaponry", "category": "common", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.3},  # hunting input(0.05)+order buildings(0.25)

    # Heating and cooking fuel
    {"name": "coal", "category": "common", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.5},  # ironworks/steel fuel input

    # ─── UPPER ───────────────────────────────────────────────────────────
    # Wealthy classes primarily. A couple buildings suffices.

    # Silks, embroidery, luxury clothing
    {"name": "fine_cloth", "category": "upper", "source": "produced",
     "output": 0.6,
     "building_consumption": 0.9},  # admin maint(0.4)+construction(0.5)

    # Silk fabric — garments, furnishings, vestments
    {"name": "silk", "category": "upper", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.5},  # fine_cloth production input

    # Books, pamphlets — personal + institutional
    {"name": "books", "category": "upper", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.3},  # construction(school/library/university avg)

    # Grape wine
    {"name": "wine", "category": "upper", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.85},  # distillers(0.85)

    # Distilled spirits
    {"name": "liquor", "category": "upper", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.2},  # incense production(0.2)

    # Frankincense, myrrh — religious/personal
    {"name": "incense", "category": "upper", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.0},

    # Luxury beverages
    {"name": "tea", "category": "upper", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.0},

    {"name": "coffee", "category": "upper", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.0},

    {"name": "cocoa", "category": "upper", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.0},

    # Colonial trade goods
    {"name": "sugar", "category": "upper", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.6},  # distillers(0.6)

    {"name": "tobacco", "category": "upper", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.0},

    # Fur — high-volume trade good (Hudson's Bay, Russian fur trade)
    {"name": "fur", "category": "upper", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.0},

    # ─── LUXURIES ────────────────────────────────────────────────────────
    # Elites only. One building oversupplies.

    {"name": "jewelry", "category": "luxury", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.0},

    {"name": "porcelain", "category": "luxury", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.0},

    {"name": "lacquerware", "category": "luxury", "source": "produced",
     "output": 1.0,
     "building_consumption": 0.0},

    # Spices — representative good (saffron/pepper/cloves/chili all price 5)
    {"name": "spices", "category": "luxury", "source": "raw",
     "output": 1.0,
     "building_consumption": 0.0,
     "vanilla_key": "pepper"},
]

# ─── EXCLUDED: MATERIAL / INDUSTRIAL GOODS ──────────────────────────────
# These are building inputs, not personal consumption goods. Their demand
# is driven by production chains, not pop class preferences.
#   Raw materials:  clay, sand, stone, iron, copper, tin, lead, lumber,
#                   saltpeter, alum, coal (partial), mercury, fiber_crops
#   Produced:       masonry, tools, tar, naval_supplies, steel, cannons
#   Textile inputs: dyes, cotton (demand captured via cloth/fine_cloth)
# ────────────────────────────────────────────────────────────────────────

# Fallback food removal list — used only if vanilla scan fails.
FOOD_REMOVAL_FALLBACK = [
    "wheat", "rice", "maize", "millet", "potato", "legumes",
    "livestock", "fish", "olives", "fruit", "wild_game",
    "wool", "fur", "beeswax",
]


# ═══════════════════════════════════════════════════════════════════════════
# VANILLA SCANNER
#
# Reads base game goods files to extract prices, demand values, and
# thresholds. This ensures the calculator always uses current vanilla
# data, regardless of game patches.
# ═══════════════════════════════════════════════════════════════════════════

def _tokenize(text):
    """Tokenize PDX script: strips comments, yields words and punctuation."""
    tokens = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '#':
            while i < len(text) and text[i] != '\n':
                i += 1
        elif c in '{}=':
            tokens.append(c)
            i += 1
        elif c in ' \t\n\r':
            i += 1
        else:
            j = i
            while j < len(text) and text[j] not in ' \t\n\r{}=#':
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_block(tokens, pos):
    """Parse tokens inside { } into a dict. Returns (dict, next_pos)."""
    result = {}
    while pos < len(tokens) and tokens[pos] != '}':
        key = tokens[pos]
        pos += 1
        if pos < len(tokens) and tokens[pos] == '=':
            pos += 1
            if pos < len(tokens) and tokens[pos] == '{':
                pos += 1
                sub, pos = _parse_block(tokens, pos)
                result[key] = sub
            elif pos < len(tokens):
                val = tokens[pos]
                try:
                    val = float(val)
                except ValueError:
                    pass
                result[key] = val
                pos += 1
        # else: bare value in a list (custom_tags etc.), skip
    if pos < len(tokens) and tokens[pos] == '}':
        pos += 1
    return result, pos


def _to_float_dict(d):
    """Convert a dict's values to float, dropping non-numeric entries."""
    result = {}
    if not isinstance(d, dict):
        return result
    for k, v in d.items():
        try:
            result[k] = float(v)
        except (ValueError, TypeError):
            pass
    return result


def scan_vanilla(vanilla_dir=None):
    """Scan vanilla goods files. Returns {good_name: {price, demand_add, ...}}.

    Returns empty dict if the directory doesn't exist.
    """
    vanilla_dir = vanilla_dir or VANILLA_GOODS_DIR
    if not os.path.isdir(vanilla_dir):
        return {}

    goods = {}
    for filename in sorted(os.listdir(vanilla_dir)):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(vanilla_dir, filename)
        with open(filepath, encoding="utf-8-sig") as f:
            text = f.read()

        tokens = _tokenize(text)
        pos = 0
        while pos < len(tokens):
            if (pos + 2 < len(tokens)
                    and tokens[pos + 1] == '='
                    and tokens[pos + 2] == '{'):
                name = tokens[pos]
                pos += 3
                block, pos = _parse_block(tokens, pos)

                info = {}
                if "default_market_price" in block:
                    info["price"] = float(block["default_market_price"])
                da = _to_float_dict(block.get("demand_add"))
                if da:
                    info["demand_add"] = da
                dm = _to_float_dict(block.get("demand_multiply"))
                if dm:
                    info["demand_multiply"] = dm
                if "development_threshold" in block:
                    info["development_threshold"] = int(float(
                        block["development_threshold"]))
                if "food" in block:
                    info["food"] = float(block["food"])

                goods[name] = info
            else:
                pos += 1

    return goods


def merge_vanilla(goods, vanilla_data):
    """Merge scanned vanilla data into goods entries.

    Updates each good's price and vanilla reference from the scan.
    Uses vanilla_key field to map mod good names to vanilla good names
    (e.g., "spices" -> "pepper").
    """
    for g in goods:
        vkey = g.get("vanilla_key", g["name"])
        vd = vanilla_data.get(vkey)
        if not vd:
            continue

        g["price"] = vd.get("price", g.get("price"))

        vanilla = {}
        if "demand_add" in vd:
            vanilla["demand_add"] = vd["demand_add"]
        if "demand_multiply" in vd:
            vanilla["demand_multiply"] = vd["demand_multiply"]
        if "development_threshold" in vd:
            vanilla["development_threshold"] = vd["development_threshold"]
        if vanilla:
            g["vanilla"] = vanilla


def get_food_goods(vanilla_data):
    """Get sorted list of goods with food > 0 in vanilla."""
    return sorted(name for name, info in vanilla_data.items()
                  if info.get("food", 0) > 0)


def scan_production_demand():
    """Scan production method files to compute consumption of production-only goods.

    Reads all production methods from:
      - Vanilla: production_methods/ and building_types/ (unique_production_methods)
      - Mod: production_methods/ and building_types/ (unique_production_methods)

    Returns {good_name: total_consumption} for goods in PRODUCTION_GOODS.
    """
    # Non-goods keys that appear in PM blocks
    PM_SKIP_KEYS = {
        "produced", "output", "category", "no_upkeep", "employment",
        "potential", "trigger", "limit", "modifier", "icon",
    }

    def _extract_consumption(block, totals):
        """Add goods consumption from a PM block to totals."""
        for key, val in block.items():
            if key in PM_SKIP_KEYS:
                continue
            if key not in PRODUCTION_GOODS:
                continue
            try:
                totals[key] = totals.get(key, 0) + float(val)
            except (ValueError, TypeError):
                pass

    def _scan_pm_file(filepath, totals):
        """Parse a production_methods file: each top-level block is a PM."""
        with open(filepath, encoding="utf-8-sig") as f:
            text = f.read()
        tokens = _tokenize(text)
        pos = 0
        while pos < len(tokens):
            if (pos + 2 < len(tokens)
                    and tokens[pos + 1] == '='
                    and tokens[pos + 2] == '{'):
                pos += 3
                block, pos = _parse_block(tokens, pos)
                _extract_consumption(block, totals)
            else:
                pos += 1

    def _scan_building_file(filepath, totals):
        """Parse a building_types file, extracting unique_production_methods blocks."""
        with open(filepath, encoding="utf-8-sig") as f:
            text = f.read()
        tokens = _tokenize(text)
        pos = 0
        while pos < len(tokens):
            if (pos + 2 < len(tokens)
                    and tokens[pos + 1] == '='
                    and tokens[pos + 2] == '{'):
                name = tokens[pos]
                pos += 3
                block, pos = _parse_block(tokens, pos)
                # Look for unique_production_methods inside building blocks
                upm = block.get("unique_production_methods")
                if isinstance(upm, dict):
                    for pm_name, pm_block in upm.items():
                        if isinstance(pm_block, dict):
                            _extract_consumption(pm_block, totals)
            else:
                pos += 1

    totals = {}

    # Scan vanilla production_methods
    pm_dirs = [
        os.path.join(VANILLA_BASE, "production_methods"),
        os.path.join(MOD_BASE, "production_methods"),
    ]
    for d in pm_dirs:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".txt"):
                _scan_pm_file(os.path.join(d, fn), totals)

    # Scan building_types for inline unique_production_methods
    bt_dirs = [
        os.path.join(VANILLA_BASE, "building_types"),
        os.path.join(MOD_BASE, "building_types"),
    ]
    for d in bt_dirs:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".txt"):
                _scan_building_file(os.path.join(d, fn), totals)

    return {k: v * PRODUCTION_DEMAND_SCALE
            for k, v in totals.items() if k in PRODUCTION_GOODS}


# ═══════════════════════════════════════════════════════════════════════════
# COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════

def get_spread(category):
    """Derive class spread from category base.
    Higher base (luxury) -> spread closer to 1.0 (full hierarchy).
    Lower base (necessity) -> spread closer to 0 (flat demand)."""
    base = CATEGORY_BASES[category]
    max_b = max(CATEGORY_BASES.values())
    return (base / max_b) ** SPREAD_CURVE if max_b > 0 else 1.0


def get_target(category, price):
    """Per-good target: category base adjusted by price.
    At REFERENCE_PRICE, target = category base.
    Cheaper goods -> lower target (more demand).
    Expensive goods -> higher target (less demand)."""
    base = CATEGORY_BASES[category]
    return base * (price / REFERENCE_PRICE) ** TARGET_PRICE_CURVE


def get_weight(food_cons, s):
    """Class weight: spread=0 -> flat, spread=1 -> full hierarchy."""
    return 1.0 + (food_cons - 1.0) * s


def price_factor(price):
    """Demand magnitude from price. Returns 1.0 at REFERENCE_PRICE."""
    if PRICE_CURVE == 0 or price <= 0:
        return 1.0
    return (REFERENCE_PRICE / price) ** PRICE_CURVE


def affordability(food_cons, price):
    """Continuous affordability curve with power scaling.
    Raw ratio capped at 1.0, then raised to AFFORDABILITY_CURVE power.
    Higher curve = steeper penalty for pops that can barely afford it."""
    if THRESHOLD_SCALE <= 0 or price <= 0:
        return 1.0
    raw = food_cons * THRESHOLD_SCALE / price
    if raw >= 1.0:
        return 1.0
    return raw ** AFFORDABILITY_CURVE


def refinement(food_cons, price):
    """Rich pops demand less of cheap goods (inverse of affordability).
    Raw ratio capped at 1.0, then raised to REFINEMENT_CURVE power.
    Higher food_cons + lower price = more dampening."""
    if REFINEMENT_SCALE <= 0 or food_cons <= 0:
        return 1.0
    raw = price * REFINEMENT_SCALE / food_cons
    if raw >= 1.0:
        return 1.0
    return raw ** REFINEMENT_CURVE


def expand_group_keys(d):
    """Expand all/upper shorthand to per-type values.
    Handles both vanilla keys (all, upper) and legacy prefixed keys (_all, _upper)."""
    expanded = {}
    for k, v in d.items():
        if k in ("all", "_all"):
            for t in POP_TYPES:
                expanded[t] = expanded.get(t, 0) + v
        elif k in ("upper", "_upper"):
            for t in ("nobles", "clergy", "burghers"):
                expanded[t] = expanded.get(t, 0) + v
        else:
            expanded[k] = expanded.get(k, 0) + v
    return expanded


def vanilla_effective(good):
    """Compute vanilla effective demand (demand_add * demand_multiply).
    Used for comparison display."""
    vanilla = good.get("vanilla", {})
    da = expand_group_keys(vanilla.get("demand_add", {}))
    dm = vanilla.get("demand_multiply", {})
    upper = {"nobles", "clergy", "burghers"}
    result = {}
    for pop, base in da.items():
        mult = 1.0
        if pop in upper and "upper" in dm:
            mult *= dm["upper"]
        if pop in dm:
            mult *= dm[pop]
        result[pop] = base * mult
    return result


def compute():
    """Compute demand values for all goods. Returns list of result dicts."""
    results = []
    for g in GOODS:
        if "price" not in g:
            print(f"  WARNING: {g['name']} has no price (vanilla scan missing?), skipping",
                  file=sys.stderr)
            continue

        cat = g["category"]
        output = g["output"]
        price = g["price"]
        bldg_cons = g.get("building_consumption", 0)

        target = get_target(cat, price)
        s = get_spread(cat)
        pf = price_factor(price)
        cs = output / (output + bldg_cons) if bldg_cons else 1.0

        weights = {}
        afford = {}
        refine = {}
        for p in POP_TYPES:
            fc = FOOD_CONSUMPTION[p]
            if fc <= 0:
                continue
            aff = affordability(fc, price)
            ref = refinement(fc, price)
            afford[p] = aff
            refine[p] = ref
            weights[p] = get_weight(fc, s) * aff * ref

        effective = {}
        for p in POP_TYPES:
            effective[p] = output * pf * weights[p] * cs / target if p in weights else 0.0

        demand_add = {p: v for p, v in effective.items() if v > 0}

        results.append({
            "name": g["name"],
            "category": g["category"],
            "source": g["source"],
            "output": output,
            "price": price,
            "target": target,
            "spread": s,
            "price_factor": pf,
            "consumer_share": cs,
            "building_consumption": bldg_cons,
            "weights": weights,
            "afford": afford,
            "refine": refine,
            "effective": effective,
            "demand_add": demand_add,
            "vanilla": g.get("vanilla", {}),
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════
# PDX OUTPUT
# ═══════════════════════════════════════════════════════════════════════════

def _fmt(v):
    """Format a value for PDX output, rounded to nearest thousandth."""
    if v == 0:
        return "0"
    r = round(v, 3)
    if r == 0:
        return "0"
    return f"{r:.3f}".rstrip("0").rstrip(".")


def generate_pdx(results, food_goods):
    """Generate PDX INJECT blocks as a string.

    Computes three kinds of overrides per good:
      1. demand_add deltas (our_value - vanilla_base)
      2. demand_multiply cancellation (inject negative to reach 1.0)
      3. development_threshold removal (set to 0)
    Also merges food=0 for goods in food_goods list.
    """
    lines = [
        "# Generated by demand_calculator.py",
        "# INJECT deltas: computed_value - vanilla_base",
        "# demand_multiply cancelled to 1.0, development_threshold removed",
        "",
    ]

    food_set = set(food_goods)
    demand_names = {r["name"] for r in results}
    for r in results:
        name = r["name"]
        da = r["demand_add"]
        vanilla = r["vanilla"]
        van_da = expand_group_keys(vanilla.get("demand_add", {}))
        van_dm = vanilla.get("demand_multiply", {})
        van_dt = vanilla.get("development_threshold")

        # demand_add deltas: INJECT adds to vanilla, so delta = ours - vanilla
        deltas = {}
        for p in POP_TYPES:
            delta = da.get(p, 0) - van_da.get(p, 0)
            if abs(delta) > 1e-9:
                deltas[p] = delta

        # demand_multiply cancellation using ORIGINAL keys (upper, nobles, etc.)
        # Skip entries where vanilla value is 0 — those mean "no demand for this pop",
        # and since our demand_add delta already handles zeroing, cancellation is noise.
        dm_cancel = {}
        for k, v in van_dm.items():
            if abs(v) < 1e-9:
                continue
            cancel = -(v - 1.0)
            if abs(cancel) > 1e-9:
                dm_cancel[k] = cancel

        has_food = name in food_set
        if not deltas and not dm_cancel and not van_dt and not has_food:
            continue

        lines.append(
            f"# {name} [{r['category']}/{r['source']}] "
            f"target={r['target']:.0f} spread={r['spread']:.2f} "
            f"price={r['price']:.1f} (\u00d7{r['price_factor']:.2f})")

        lines.append(f"INJECT:{name} = {{")

        if deltas:
            lines.append("\tdemand_add = {")
            for p in POP_TYPES:
                if p in deltas:
                    lines.append(f"\t\t{p} = {_fmt(deltas[p])}")
            lines.append("\t}")

        if dm_cancel:
            lines.append("\tdemand_multiply = {")
            for k, v in dm_cancel.items():
                lines.append(f"\t\t{k} = {_fmt(v)}")
            lines.append("\t}")

        if van_dt:
            lines.append("\tdevelopment_threshold = 0")

        if has_food:
            lines.append("\tfood = 0")

        lines.append("}")
        lines.append("")

    # Food removal for goods not in our demand system
    remaining_food = [g for g in food_goods if g not in demand_names]
    if remaining_food:
        lines.append("# " + "\u2500" * 73)
        lines.append("# Food removal \u2014 raw goods no longer provide food as a side-effect.")
        lines.append("# All food now comes from provisions (produced good).")
        lines.append("# " + "\u2500" * 73)
        lines.append("")
        for g in remaining_food:
            lines.append(f"INJECT:{g} = {{")
            lines.append("\tfood = 0")
            lines.append("}")
            lines.append("")

    return "\n".join(lines)


def write_pdx(results, food_goods):
    """Write PDX output to sul_goods_overrides.txt."""
    content = generate_pdx(results, food_goods)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mod_dir = os.path.dirname(script_dir)
    out_path = os.path.join(mod_dir, "in_game", "common", "goods", "sul_goods_overrides.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote {out_path}")


# ═══════════════════════════════════════════════════════════════════════════
# DISPLAY
# ═══════════════════════════════════════════════════════════════════════════

DISPLAY_TYPES = ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]
DISPLAY_LABELS = ["noble", "clergy", "burghr", "soldr", "labor", "peasnt"]
DISPLAY_FOOD = [FOOD_CONSUMPTION[p] for p in DISPLAY_TYPES]


def _section(title):
    w = 76
    print(f"\n{'\u2501' * w}")
    print(f"  {title}")
    print(f"{'\u2501' * w}")


def print_config():
    _section("CONFIGURATION")

    print("\n  Category bases + derived spread:")
    print(f"  {'Category':<12s} {'Base':>8s} {'Spread':>8s} {'Nob:Pea ratio'}")
    print(f"  {'\u2500' * 12} {'\u2500' * 8} {'\u2500' * 8} {'\u2500' * 16}")
    for cat in CAT_ORDER:
        b = CATEGORY_BASES[cat]
        s = get_spread(cat)
        w_noble = get_weight(FOOD_CONSUMPTION["nobles"], s)
        w_peasant = get_weight(FOOD_CONSUMPTION["peasants"], s)
        ratio = w_noble / w_peasant if w_peasant > 0 else float('inf')
        print(f"  {cat:<12s} {b:>8.0f} {s:>8.2f} {ratio:>6.1f} : 1")

    print(f"\n  Per-good target = base \u00d7 (price / {REFERENCE_PRICE:.0f}) ^ {TARGET_PRICE_CURVE:.1f}")
    print(f"  Example targets at each price:")
    print(f"  {'Category':<12s}", end="")
    for p in [1, 2, 3, 5, 8]:
        print(f" {'p='+str(p):>6s}", end="")
    print()
    print(f"  {'\u2500' * 12}", end="")
    for _ in [1, 2, 3, 5, 8]:
        print(f" {'\u2500' * 6}", end="")
    print()
    for cat in CAT_ORDER:
        print(f"  {cat:<12s}", end="")
        for p in [1, 2, 3, 5, 8]:
            t = get_target(cat, p)
            print(f" {t:>6.0f}", end="")
        print()

    print(f"\n  System parameters:")
    print(f"    SPREAD_CURVE        = {SPREAD_CURVE:.2f}  (category\u2192spread aggressiveness)")
    print(f"    PRICE_CURVE         = {PRICE_CURVE:.2f}  (price\u2192demand magnitude)")
    print(f"    TARGET_PRICE_CURVE  = {TARGET_PRICE_CURVE:.2f}  (price\u2192target adjustment)")
    print(f"    REFERENCE_PRICE     = {REFERENCE_PRICE:.1f}  (neutral price)")
    print(f"    THRESHOLD_SCALE     = {THRESHOLD_SCALE:.1f}  (affordability: fc*scale/price)")
    print(f"    AFFORDABILITY_CURVE = {AFFORDABILITY_CURVE:.1f}  (poor can't afford expensive)")
    print(f"    REFINEMENT_SCALE    = {REFINEMENT_SCALE:.2f}  (refinement: price*scale/fc)")
    print(f"    REFINEMENT_CURVE    = {REFINEMENT_CURVE:.1f}  (rich don't want cheap)")

    print(f"\n  Affordability by price (fc \u00d7 {THRESHOLD_SCALE:.0f} / price, capped at 1.0, ^{AFFORDABILITY_CURVE:.0f}):")
    aff_types = ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants", "slaves"]
    aff_labels = ["noble", "clergy", "burghr", "soldr", "labor", "peasnt", "slave"]
    print(f"    {'price':>6s}", end="")
    for label in aff_labels:
        print(f" {label:>7s}", end="")
    print()
    print(f"    {'\u2500' * 6}", end="")
    for _ in aff_labels:
        print(f" {'\u2500' * 7}", end="")
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

    print(f"\n  Refinement by price (price \u00d7 {REFINEMENT_SCALE:.2f} / fc, capped at 1.0, ^{REFINEMENT_CURVE:.0f}):")
    print(f"    {'price':>6s}", end="")
    for label in aff_labels:
        print(f" {label:>7s}", end="")
    print()
    print(f"    {'\u2500' * 6}", end="")
    for _ in aff_labels:
        print(f" {'\u2500' * 7}", end="")
    print()
    for pr in [1, 2, 3, 4, 5, 6, 8, 10]:
        print(f"    {pr:>6d}", end="")
        for p in aff_types:
            ref = refinement(FOOD_CONSUMPTION[p], pr)
            if ref >= 1.0:
                print(f"    1.0", end="")
            else:
                print(f"   {ref:>.2f}", end="")
        print()

    print(f"\n  Food consumption anchor:")
    parts = [f"{p}: {FOOD_CONSUMPTION[p]:.0f}" for p in POP_TYPES if FOOD_CONSUMPTION[p] > 0]
    print(f"    {', '.join(parts)}")

    print(f"\n  Pop composition: determined by game (no assumed mix)")

    print(f"\n  Location: {LOCATION_POP_UNITS:.0f} pop units, "
          f"{LOCATION_BUILDING_SLOTS} building slots")


def print_demands(results):
    _section("COMPUTED DEMAND VALUES")

    for cat in CAT_ORDER:
        goods = [r for r in results if r["category"] == cat]
        if not goods:
            continue
        sp = get_spread(cat)
        print(f"\n  [{cat.upper()}]  base={CATEGORY_BASES[cat]:.0f}  spread={sp:.2f}")
        print(f"  {'Good':<14s} {'Src':>4s} {'Price':>6s} {'Trgt':>6s} {'Prc.F':>6s} {'CShr':>5s}")
        print(f"  {'\u2500' * 14} {'\u2500' * 4} {'\u2500' * 6} {'\u2500' * 6} {'\u2500' * 6} {'\u2500' * 5}")
        for r in goods:
            src = "raw" if r["source"] == "raw" else "prod"
            print(f"  {r['name']:<14s} {src:>4s} {r['price']:>6.1f} {r['target']:>6.0f} {r['price_factor']:>6.2f} "
                  f"{r['consumer_share']:>5.0%}")


def print_effective(results):
    _section("EFFECTIVE DEMAND PER POP UNIT")
    print(f"  weight = spread_weight \u00d7 affordability \u00d7 refinement")
    print(f"\n  {'Good':<14s} {'sprd':>5s}", end="")
    for label in DISPLAY_LABELS:
        print(f" {label:>8s}", end="")
    print()
    print(f"  {'(food_cons)':<14s} {'':>5s}", end="")
    for f in DISPLAY_FOOD:
        print(f" {f:>7.0f}\u00d7", end="")
    print()
    print(f"  {'\u2500' * 14} {'\u2500' * 5}", end="")
    for _ in DISPLAY_LABELS:
        print(f" {'\u2500' * 8}", end="")
    print()

    last_cat = None
    for r in results:
        if r["category"] != last_cat:
            if last_cat:
                print()
            last_cat = r["category"]
        print(f"  {r['name']:<14s} {r['spread']:>5.2f}", end="")
        for c in DISPLAY_TYPES:
            v = r["effective"].get(c, 0)
            aff = r["afford"].get(c, 1.0)
            ref = r["refine"].get(c, 1.0)
            if v > 0 and (aff < 1.0 or ref < 1.0):
                print(f" {v:>7.4f}~", end="")
            elif v > 0:
                print(f" {v:>8.4f}", end="")
            else:
                print(f" {'\u00b7':>8s}", end="")
        print()


def print_weights(results):
    _section("CLASS WEIGHTS  (how spread compresses the hierarchy)")
    print(f"\n  {'Category':<12s} {'Spread':>6s}", end="")
    for label in DISPLAY_LABELS:
        print(f" {label:>8s}", end="")
    print()
    print(f"  {'\u2500' * 12} {'\u2500' * 6}", end="")
    for _ in DISPLAY_LABELS:
        print(f" {'\u2500' * 8}", end="")
    print()

    for cat in CAT_ORDER:
        s = get_spread(cat)
        print(f"  {cat:<12s} {s:>6.2f}", end="")
        for c in DISPLAY_TYPES:
            w = get_weight(FOOD_CONSUMPTION[c], s)
            print(f" {w:>8.2f}", end="")
        print()

    print(f"\n  {'(full fc)':<12s} {'1.00':>6s}", end="")
    for c in DISPLAY_TYPES:
        print(f" {FOOD_CONSUMPTION[c]:>8.1f}", end="")
    print()


def print_satisfaction(results):
    _section("POPS SATISFIED PER BUILDING  (by tier, produced goods only)")
    tiers = [("guild", 1.0), ("workshop", 1.1), ("manuf.", 2.0), ("mill", 4.0)]

    produced = [r for r in results if r["source"] == "produced"]
    if not produced:
        print("\n  (no produced goods)")
        return

    print(f"\n  {'Good':<14s}", end="")
    for name, _ in tiers:
        print(f" {name:>10s}", end="")
    print()
    print(f"  {'\u2500' * 14}", end="")
    for _ in tiers:
        print(f" {'\u2500' * 10}", end="")
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

    _section(f"LOCATION VIEW: {pop_units:.0f} POP UNITS, {slots} SLOTS  (produced only)")

    tiers_show = [("guild", 1.0), ("wkshop", 1.1), ("manuf.", 2.0), ("mill", 4.0)]

    print(f"\n  {'Good':<14s} {'Cat.':<10s}", end="")
    for name, _ in tiers_show:
        print(f" {name:>8s}", end="")
    print()
    print(f"  {'\u2500' * 14} {'\u2500' * 10}", end="")
    for _ in tiers_show:
        print(f" {'\u2500' * 8}", end="")
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

    print(f"\n  {'\u2500' * 14} {'\u2500' * 10}", end="")
    for _ in tiers_show:
        print(f" {'\u2500' * 8}", end="")
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

    used = grand["guild"]
    free = slots - used
    print(f"\n  Slot budget (guild tier):")
    for cat in CAT_ORDER:
        if cat not in cat_totals:
            continue
        g = cat_totals[cat]["guild"]
        pct = g / slots * 100
        bar = "\u2588" * int(pct / 2)
        print(f"    {cat:<12s} {g:>5.1f} ({pct:>4.0f}%)  {bar}")
    pct = max(0, free / slots * 100)
    bar = "\u2591" * int(pct / 2)
    print(f"    {'remaining':<12s} {free:>5.1f} ({pct:>4.0f}%)  {bar}")


def print_supply_demand(results):
    """Supply-demand balance: producer pops needed per demand pop unit."""
    _section("SUPPLY-DEMAND BALANCE")
    print(f"  Producers per demand pop unit = pf \u00d7 employment / (target \u00d7 output)")
    print(f"  Each tier shows: [ratio] as [pop_type]")

    raw_tier_keys = ["village", "rural", "plantation"]
    prod_tier_keys = ["guild", "workshop", "manufactory", "mill"]
    raw_tier_labels = ["village", "rural", "plantn"]
    prod_tier_labels = ["guild", "wkshop", "manuf.", "mill"]

    def tier_ratio(r, tier_key):
        tier = BUILDING_TIERS[tier_key]
        return r["price_factor"] * tier["employment"] / (r["target"] * tier["output"])

    def pop_label(tier_key):
        return BUILDING_TIERS[tier_key]["pop_type"][:3]

    raw_goods = [r for r in results if r["source"] == "raw"]
    if raw_goods:
        print(f"\n  RAW MATERIALS:")
        print(f"  {'Good':<14s} {'Cat.':<10s}", end="")
        for i, label in enumerate(raw_tier_labels):
            pt = pop_label(raw_tier_keys[i])
            print(f" {label + '(' + pt + ')':>14s}", end="")
        print()
        print(f"  {'\u2500' * 14} {'\u2500' * 10}", end="")
        for _ in raw_tier_labels:
            print(f" {'\u2500' * 14}", end="")
        print()

        for r in raw_goods:
            print(f"  {r['name']:<14s} {r['category']:<10s}", end="")
            for tk in raw_tier_keys:
                ratio = tier_ratio(r, tk)
                print(f" {ratio:>14.4f}", end="")
            print()

    produced = [r for r in results if r["source"] == "produced"]
    if produced:
        print(f"\n  PRODUCED GOODS:")
        print(f"  {'Good':<14s} {'Cat.':<10s}", end="")
        for i, label in enumerate(prod_tier_labels):
            pt = pop_label(prod_tier_keys[i])
            print(f" {label + '(' + pt + ')':>14s}", end="")
        print()
        print(f"  {'\u2500' * 14} {'\u2500' * 10}", end="")
        for _ in prod_tier_labels:
            print(f" {'\u2500' * 14}", end="")
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

    print(f"\n  POP TYPE BUDGET (all goods, base tier per source):")
    print(f"  How many pop units of each type must be producers?")

    pop_budget = {}
    for r in results:
        tk = "rural" if r["source"] == "raw" else "guild"
        tier = BUILDING_TIERS[tk]
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
        print(f"    {pt:<12s} {info['total']:>8.4f}  ({info['total'] * 100:>5.1f}%)  "
              f"\u2190 {len(info['goods'])} goods")

    print(f"    {'TOTAL':<12s} {grand_total:>8.4f}  ({grand_total * 100:>5.1f}%)")

    print(f"\n  DEMAND FEEDBACK (each producer also consumes):")
    print(f"  Building guilds creates burghers \u2192 more demand for upper/luxury goods")
    print(f"  Building mills creates laborers \u2192 more demand for common goods")

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


def compute_building_weights(results):
    """Compute production weights per specialization tier based on demand.

    For each spec's rural and guild tier, looks up the TOTAL demand for each
    building's produced good (pop demand + production chain demand) and
    normalizes into integer weights (per-mille).

    Total demand = pop_demand / consumer_share, where consumer_share < 1
    means production chains consume part of the output. This ensures goods
    like cloth (cs=0.34, most output feeds fine_cloth/paper) get proportionally
    more building levels than their pop demand alone would suggest.

    Returns dict: {spec: {tier: {building_name: weight_permille, ...}, ...}, ...}
    """
    # Build demand lookup: good_name -> total demand (pop + production chain)
    demand_by_good = {}
    for r in results:
        pop_demand = sum(r["demand_add"].values())
        cs = r.get("consumer_share", 1.0)
        # Total demand: pop demand accounts for consumer_share in the formula,
        # so dividing by cs recovers the full production need
        total = pop_demand / cs if cs > 0 else pop_demand
        demand_by_good[r["name"]] = total

    # Add production-only goods (not in pop demand system)
    for good, demand in PRODUCTION_DEMAND.items():
        if good not in demand_by_good:
            demand_by_good[good] = demand

    weights = {}
    for spec, tiers in SPEC_BUILDINGS.items():
        weights[spec] = {}
        for tier, buildings in tiers.items():
            # Get raw demand weight per building
            raw = {}
            for bldg, good in buildings.items():
                raw[bldg] = demand_by_good.get(good, 0.01)  # fallback for unmapped

            total = sum(raw.values())
            if total <= 0:
                # Equal distribution fallback
                n = len(raw)
                weights[spec][tier] = {b: 1000 // n for b in raw}
                continue

            # Normalize to per-mille (1000 total) for integer math in PDX
            normed = {}
            for bldg, w in raw.items():
                normed[bldg] = int(round(w / total * 1000))

            # Fix rounding to sum to exactly 1000
            diff = 1000 - sum(normed.values())
            if diff != 0:
                # Add remainder to highest-weight building
                top = max(normed, key=normed.get)
                normed[top] += diff

            weights[spec][tier] = normed

    return weights


def generate_weight_macros(weights):
    """Generate @macro definitions for building distribution weights."""
    lines = [
        "# Building distribution weights (per-mille, sum to 1000 per tier)",
        "# Generated by demand_calculator.py from demand data",
        "# Higher weight = more building levels allocated",
        "",
    ]
    for spec in ["mining", "farming", "gathering", "woodland", "commercial"]:
        if spec not in weights:
            continue
        lines.append(f"# {spec.upper()}")
        for tier in ["rural", "guild"]:
            if tier not in weights[spec]:
                continue
            for bldg, w in weights[spec][tier].items():
                macro_name = f"@sul_w_{bldg}"
                lines.append(f"{macro_name} = {w}")
        lines.append("")
    return "\n".join(lines)


def print_building_weights(results):
    """Display building distribution weights."""
    weights = compute_building_weights(results)

    _section("BUILDING DISTRIBUTION WEIGHTS (demand-derived)")
    print(f"\n  Weights include production chain demand (pop_demand / consumer_share).")
    print(f"  Per-mille: sum to 1000 per tier. Higher = more building levels.\n")

    # Build lookups for display
    total_demand_by_good = {}
    cs_by_good = {}
    source_by_good = {}
    for r in results:
        pop_d = sum(r["demand_add"].values())
        cs = r.get("consumer_share", 1.0)
        total_demand_by_good[r["name"]] = pop_d / cs if cs > 0 else pop_d
        cs_by_good[r["name"]] = cs
        source_by_good[r["name"]] = "pop"
    for good, demand in PRODUCTION_DEMAND.items():
        if good not in total_demand_by_good:
            total_demand_by_good[good] = demand
            cs_by_good[good] = 0.0
            source_by_good[good] = "prod"

    for spec in ["mining", "farming", "gathering", "woodland", "commercial"]:
        if spec not in weights:
            continue
        print(f"  [{spec.upper()}]")
        for tier in ["rural", "guild"]:
            if tier not in weights[spec]:
                continue
            print(f"    {tier}:")
            for bldg, w in weights[spec][tier].items():
                good = SPEC_BUILDINGS[spec][tier][bldg]
                src = source_by_good.get(good, "?")
                cs = cs_by_good.get(good, 1.0)
                pct = w / 10
                bar = "\u2588" * int(pct / 2)
                tag = ""
                if src == "prod":
                    tag = " [prod]"
                elif cs < 1.0:
                    tag = f" cs={cs:.0%}"
                print(f"      {bldg:<28s} \u2192 {good:<14s}  {w:>4d}  ({pct:>5.1f}%){tag}  {bar}")
        print()


def print_comparison(results):
    _section("VS VANILLA  (proposed / vanilla_effective ratio)")
    print(f"\n  {'Good':<14s}", end="")
    for label in DISPLAY_LABELS:
        print(f" {label:>8s}", end="")
    print()
    print(f"  {'\u2500' * 14}", end="")
    for _ in DISPLAY_LABELS:
        print(f" {'\u2500' * 8}", end="")
    print()

    for r in results:
        van = vanilla_effective(r)
        if not van:
            continue
        print(f"  {r['name']:<14s}", end="")
        for c in DISPLAY_TYPES:
            proposed = r["effective"].get(c, 0)
            current = van.get(c, 0)
            if proposed > 0 and current > 0:
                ratio = proposed / current
                if ratio >= 100:
                    print(f" {ratio:>7.0f}\u00d7", end="")
                elif ratio >= 10:
                    print(f" {ratio:>7.1f}\u00d7", end="")
                else:
                    print(f" {ratio:>7.2f}\u00d7", end="")
            elif proposed > 0 and current == 0:
                print(f" {'NEW':>8s}", end="")
            else:
                print(f" {'\u00b7':>8s}", end="")
        print()


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Demand System Calculator \u2014 interconnected price/food_consumption design"
    )
    parser.add_argument("--compact", action="store_true",
                        help="Summary tables only")
    parser.add_argument("--pdx", action="store_true",
                        help="Output PDX INJECT blocks to stdout")
    parser.add_argument("--write", action="store_true",
                        help="Write PDX output to sul_goods_overrides.txt")
    parser.add_argument("--location", type=float, metavar="N",
                        help="Override location pop units")
    parser.add_argument("--slots", type=int, metavar="N",
                        help="Override location building slots")
    parser.add_argument("--weights", action="store_true",
                        help="Show building distribution weights")
    parser.add_argument("--write-weights", action="store_true",
                        help="Write weight macros to sul_bootstrap_weights.txt")
    parser.add_argument("--vanilla-dir", metavar="DIR",
                        help="Override vanilla goods directory path")
    args = parser.parse_args()

    if args.location:
        global LOCATION_POP_UNITS
        LOCATION_POP_UNITS = args.location
    if args.slots:
        global LOCATION_BUILDING_SLOTS
        LOCATION_BUILDING_SLOTS = args.slots

    # Scan vanilla game files
    vdir = args.vanilla_dir or VANILLA_GOODS_DIR
    vanilla_data = scan_vanilla(vdir)
    if vanilla_data:
        merge_vanilla(GOODS, vanilla_data)
        food_goods = get_food_goods(vanilla_data)
        print(f"  Scanned {len(vanilla_data)} goods from {vdir}", file=sys.stderr)
    else:
        print(f"  WARNING: Vanilla dir not found: {vdir}", file=sys.stderr)
        print(f"  Using fallback food list; prices/vanilla data may be missing",
              file=sys.stderr)
        food_goods = FOOD_REMOVAL_FALLBACK

    # Scan production methods for non-pop goods demand
    global PRODUCTION_DEMAND
    PRODUCTION_DEMAND = scan_production_demand()
    if PRODUCTION_DEMAND:
        parts = [f"{k}={v:.2f}" for k, v in sorted(PRODUCTION_DEMAND.items(),
                                                     key=lambda x: -x[1])]
        print(f"  Production demand: {', '.join(parts)}", file=sys.stderr)

    results = compute()

    if args.write:
        write_pdx(results, food_goods)
        return

    if args.write_weights:
        bw = compute_building_weights(results)
        content = generate_weight_macros(bw)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        mod_dir = os.path.dirname(script_dir)
        out_path = os.path.join(mod_dir, "in_game", "common", "scripted_effects",
                                "sul_bootstrap_weights.txt")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {out_path}")
        return

    if args.pdx:
        print(generate_pdx(results, food_goods))
        return

    if args.weights:
        print_building_weights(results)
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
        print_building_weights(results)


if __name__ == "__main__":
    main()
