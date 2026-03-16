#!/usr/bin/env python3
"""
Demand System Calculator for Specialized Urban Locations
========================================================

Computes demand_add values for EU5 pop goods using food_consumption as the
primary scaling factor.

FORMULA:
  price_factor   = (REFERENCE_PRICE / price) ^ PRICE_CURVE
  affordability  = min(1, fc * THRESHOLD_SCALE / price) ^ AFFORDABILITY_CURVE
  consumer_share = CONSUMER_SHARE[category]
  demand_add     = price_factor * affordability * consumer_share * fc * DEMAND_SCALE

  All pop types with food_consumption > 0 consume all goods.
  Price_factor: cheap goods are bought in larger quantities.
  Affordability: poor pops can't afford expensive goods (quadratic gate).
  Food_consumption: wealth-proportional base demand (nobles consume more of everything).
  Consumer_share: category weight (necessities vs luxuries).

  In-game, demand_add is further multiplied by the pop_demand scriptvalue which
  applies GDP-based scaling with elasticity dampening per category:
    necessity=0.2, common=0.5, upper=0.8, luxury=1.0

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

CAT_ORDER = ["necessity", "common", "upper", "luxury"]

PRICE_CURVE = 0.5        # How aggressively price affects demand quantity. sqrt.
REFERENCE_PRICE = 3.0    # Neutral price point (price_factor=1)
THRESHOLD_SCALE = 2.0    # Affordability: fc * scale / price, capped at 1.0
AFFORDABILITY_CURVE = 2.0  # Power curve on affordability (1=linear, 2=quadratic)
DEMAND_SCALE = 0.001     # Global calibration constant (anchored to food_consumption)

# Wealth impact threshold: minimum estate income/expense ratio to demand a good.
# Formula: threshold = WEALTH_THRESHOLD_BASE + elasticity × WEALTH_THRESHOLD_SCALE
# Ties directly to category elasticity — inelastic goods demanded even when poor.
WEALTH_THRESHOLD_BASE = 0.5
WEALTH_THRESHOLD_SCALE = 0.75

# Consumer share: fraction of total demand that is pop consumption (vs building inputs).
CONSUMER_SHARE = {
    "necessity": 0.60,
    "common":    0.70,
    "upper":     0.80,
    "luxury":    0.90,
}

# Elasticity: how much the in-game GDP wealth multiplier affects each category.
# These values are mirrored in sul_gdp_scaling.txt script values.
# 0 = perfectly inelastic (wealth doesn't matter), 1 = fully elastic.
ELASTICITY = {
    "necessity": 0.2,
    "common":    0.5,
    "upper":     0.8,
    "luxury":    1.0,
}

POP_TYPES = [
    "nobles", "clergy", "burghers", "soldiers",
    "laborers", "peasants", "slaves", "tribesmen",
]

# Food consumption defines the class hierarchy and affordability thresholds.
FOOD_CONSUMPTION = {
    "nobles":    25.0,
    "clergy":     6.5,
    "burghers":   6.5,
    "soldiers":   5.0,
    "laborers":   1.5,
    "peasants":   0.95,
    "slaves":     0.5,
    "tribesmen":  0.0,
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

    # Clothing — broad personal demand
    {"name": "cloth", "category": "necessity", "source": "produced",
     "output": 3.0,
     "building_consumption": 1.0},

    # Cheap alcohol
    {"name": "beer", "category": "necessity", "source": "produced",
     "output": 3.0,
     "building_consumption": 1.0},

    # Cheap ceramics — household use
    {"name": "pottery", "category": "necessity", "source": "produced",
     "output": 3.0,
     "building_consumption": 1.0},

    # Salt — universal preservative
    {"name": "salt", "category": "necessity", "source": "raw"},

    # Heating and cooking fuel
    {"name": "coal", "category": "necessity", "source": "raw"},

    # ─── COMMON ──────────────────────────────────────────────────────────
    # Broadly useful. A few buildings satisfy a location.

    {"name": "furniture", "category": "common", "source": "produced"},
    {"name": "leather", "category": "common", "source": "produced"},
    {"name": "glass", "category": "common", "source": "produced"},
    {"name": "paper", "category": "common", "source": "produced"},
    {"name": "medicaments", "category": "common", "source": "raw"},
    {"name": "weaponry", "category": "common", "source": "produced"},
    {"name": "liquor", "category": "common", "source": "produced"},
    {"name": "fur", "category": "common", "source": "raw"},

    # ─── UPPER ───────────────────────────────────────────────────────────
    # Wealthy classes primarily. A couple buildings suffices.

    {"name": "fine_cloth", "category": "upper", "source": "produced"},
    {"name": "silk", "category": "upper", "source": "raw"},
    {"name": "books", "category": "upper", "source": "produced"},
    {"name": "wine", "category": "upper", "source": "raw"},
    {"name": "tea", "category": "upper", "source": "raw"},
    {"name": "coffee", "category": "upper", "source": "raw"},
    {"name": "cocoa", "category": "upper", "source": "raw"},
    {"name": "sugar", "category": "upper", "source": "raw"},
    {"name": "tobacco", "category": "upper", "source": "raw"},

    # ─── LUXURIES ────────────────────────────────────────────────────────
    # Elites only. One building oversupplies.

    {"name": "jewelry", "category": "luxury", "source": "produced"},
    {"name": "porcelain", "category": "luxury", "source": "produced"},
    {"name": "lacquerware", "category": "luxury", "source": "produced"},
    {"name": "pepper", "category": "luxury", "source": "raw"},
    {"name": "cloves", "category": "luxury", "source": "raw"},
    {"name": "saffron", "category": "luxury", "source": "raw"},
    {"name": "chili", "category": "luxury", "source": "raw"},
    {"name": "incense", "category": "luxury", "source": "raw"},
    {"name": "pearls", "category": "luxury", "source": "raw"},
    {"name": "ivory", "category": "luxury", "source": "raw"},
]

# ─── EXCLUDED: MATERIAL / INDUSTRIAL GOODS ──────────────────────────────
# These are building inputs, not personal consumption goods. Their demand
# is driven by production chains, not pop class preferences.
#   Raw materials:  clay, sand, stone, iron, copper, tin, lead, lumber,
#                   saltpeter, alum, mercury, fiber_crops, elephants
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
                wit = _to_float_dict(block.get("wealth_impact_threshold"))
                if wit:
                    info["wealth_impact_threshold"] = wit
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
        if "wealth_impact_threshold" in vd:
            vanilla["wealth_impact_threshold"] = vd["wealth_impact_threshold"]
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

def get_gdp_multiplier(food_cons, elasticity):
    """In-game GDP wealth multiplier for display purposes.
    Formula: 1 + (fc / FC_ANCHOR - 1) * elasticity
    Mirrors the sul_gdp_scale_* script values."""
    FC_ANCHOR = 3.0  # Laborer level — multiply = 1.0 at this wealth
    return 1.0 + (food_cons / FC_ANCHOR - 1.0) * elasticity


def price_factor(price):
    """Demand quantity from price. Cheap goods = more quantity.
    Returns 1.0 at REFERENCE_PRICE."""
    if PRICE_CURVE == 0 or price <= 0:
        return 1.0
    return (REFERENCE_PRICE / price) ** PRICE_CURVE


def affordability(food_cons, price):
    """Continuous affordability gate with power scaling.
    Raw ratio capped at 1.0, then raised to AFFORDABILITY_CURVE power.
    Higher curve = steeper penalty for pops that can barely afford it."""
    if THRESHOLD_SCALE <= 0 or price <= 0:
        return 1.0
    raw = food_cons * THRESHOLD_SCALE / price
    if raw >= 1.0:
        return 1.0
    return raw ** AFFORDABILITY_CURVE


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
    """Compute demand values for all goods. Returns list of result dicts.

    Formula: demand_add = price_factor × affordability × consumer_share × fc × DEMAND_SCALE
    """
    results = []
    for g in GOODS:
        if "price" not in g:
            print(f"  WARNING: {g['name']} has no price (vanilla scan missing?), skipping",
                  file=sys.stderr)
            continue

        cat = g["category"]
        price = g["price"]

        elasticity = ELASTICITY[cat]
        pf = price_factor(price)
        cs = CONSUMER_SHARE[cat]

        afford = {}
        effective = {}
        for p in POP_TYPES:
            fc = FOOD_CONSUMPTION[p]
            if fc <= 0:
                continue
            aff = affordability(fc, price)
            afford[p] = aff
            effective[p] = pf * aff * cs * fc * DEMAND_SCALE

        demand_add = {p: v for p, v in effective.items() if v > 0}

        results.append({
            "name": g["name"],
            "category": g["category"],
            "source": g["source"],
            "price": price,
            "elasticity": elasticity,
            "price_factor": pf,
            "consumer_share": cs,
            "afford": afford,
            "effective": effective,
            "demand_add": demand_add,
            "vanilla": g.get("vanilla", {}),
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════
# PDX OUTPUT
# ═══════════════════════════════════════════════════════════════════════════

def _fmt(v):
    """Format a value for PDX output, rounded to 4 decimal places."""
    if v == 0:
        return "0"
    r = round(v, 4)
    if r == 0:
        return "0"
    return f"{r:.4f}".rstrip("0").rstrip(".")


def generate_pdx(results, food_goods):
    """Generate PDX INJECT blocks as a string.

    For each good:
      1. Zeros vanilla demand_add (inject negative of vanilla values)
      2. Adds our computed demand_add (absolute values from formula)
      3. Cancels vanilla demand_multiply to 1.0
      4. Removes development_threshold
      5. Sets food=0 for food goods

    Net inject delta = computed_value - vanilla_value.
    Comments show the computed absolute values and formula inputs.
    """
    lines = [
        "# Generated by demand_calculator.py",
        "# Formula: demand_add = pf × aff × cs × fc × DEMAND_SCALE",
        f"# DEMAND_SCALE={DEMAND_SCALE}  PRICE_CURVE={PRICE_CURVE}  "
        f"REF_PRICE={REFERENCE_PRICE}",
        f"# THRESHOLD_SCALE={THRESHOLD_SCALE}  AFFORDABILITY_CURVE={AFFORDABILITY_CURVE}",
        "# INJECT deltas zero vanilla demand_add/multiply, then set computed values",
        "",
    ]

    food_set = set(food_goods)
    demand_names = {r["name"] for r in results}
    for r in results:
        name = r["name"]
        da = r["demand_add"]
        elasticity = r["elasticity"]
        vanilla = r["vanilla"]
        van_da = expand_group_keys(vanilla.get("demand_add", {}))
        van_dm = vanilla.get("demand_multiply", {})
        van_dt = vanilla.get("development_threshold")

        # demand_add deltas: INJECT adds to vanilla, so delta = ours - vanilla
        deltas = {}
        for p in POP_TYPES:
            our_val = da.get(p, 0)
            van_val = van_da.get(p, 0)
            delta = our_val - van_val
            if abs(delta) > 1e-9:
                deltas[p] = delta

        # demand_multiply cancellation: inject negative to reach 1.0
        dm_cancel = {}
        for k, v in van_dm.items():
            if abs(v) < 1e-9:
                continue
            cancel = -(v - 1.0)
            if abs(cancel) > 1e-9:
                dm_cancel[k] = cancel

        # wealth_impact_threshold: set to elasticity-derived value
        # Formula: threshold = WEALTH_THRESHOLD_BASE + elasticity × WEALTH_THRESHOLD_SCALE
        van_wit = vanilla.get("wealth_impact_threshold", {})
        our_threshold = WEALTH_THRESHOLD_BASE + elasticity * WEALTH_THRESHOLD_SCALE
        wit_deltas = {}
        # For "all" key: compute delta to reach our threshold
        van_all = van_wit.get("all")
        if van_all is not None:
            delta = our_threshold - van_all
            if abs(delta) > 0.001:
                wit_deltas["all"] = delta
        else:
            # No vanilla "all" — add it
            wit_deltas["all"] = our_threshold
        # For per-type keys: set delta so vanilla + delta = our threshold
        for k, v in van_wit.items():
            if k == "all":
                continue
            delta = our_threshold - v
            if abs(delta) > 0.001:
                wit_deltas[k] = delta

        has_food = name in food_set
        if (not deltas and not dm_cancel and not van_dt
                and not has_food and not wit_deltas):
            continue

        # Header comment: good info + formula inputs
        lines.append(
            f"# {name} [{r['category']}/{r['source']}] "
            f"price={r['price']:.1f}  pf={r['price_factor']:.3f}  "
            f"cs={r['consumer_share']:.2f}  "
            f"wit={our_threshold:.3f}")

        # Show computed absolute values per pop type
        if da:
            parts = []
            for p in POP_TYPES:
                v = da.get(p, 0)
                if v > 0:
                    aff = r["afford"].get(p, 1.0)
                    fc = FOOD_CONSUMPTION[p]
                    if aff < 1.0:
                        parts.append(f"{p}={v:.4f}(fc={fc:.1f} aff={aff:.2f})")
                    else:
                        parts.append(f"{p}={v:.4f}(fc={fc:.1f})")
            if parts:
                line = "#   final: " + ", ".join(parts)
                lines.append(line)

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

        if wit_deltas:
            lines.append("\twealth_impact_threshold = {")
            # Output "all" first, then any per-type cancellations
            if "all" in wit_deltas:
                lines.append(f"\t\tall = {_fmt(wit_deltas['all'])}")
            for k, v in wit_deltas.items():
                if k != "all":
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

    print("\n  Category elasticity + consumer share:")
    print(f"  {'Category':<12s} {'Elast.':>8s} {'CShare':>8s}")
    print(f"  {'\u2500' * 12} {'\u2500' * 8} {'\u2500' * 8}")
    for cat in CAT_ORDER:
        e = ELASTICITY[cat]
        cs = CONSUMER_SHARE[cat]
        print(f"  {cat:<12s} {e:>8.2f} {cs:>8.0%}")

    print(f"\n  Formula: demand_add = pf \u00d7 aff \u00d7 cs \u00d7 fc \u00d7 DEMAND_SCALE")
    print(f"\n  System parameters:")
    print(f"    DEMAND_SCALE        = {DEMAND_SCALE}  (global calibration)")
    print(f"    PRICE_CURVE         = {PRICE_CURVE:.2f}  (price\u2192demand quantity)")
    print(f"    REFERENCE_PRICE     = {REFERENCE_PRICE:.1f}  (neutral price)")
    print(f"    THRESHOLD_SCALE     = {THRESHOLD_SCALE:.1f}  (affordability: fc*scale/price)")
    print(f"    AFFORDABILITY_CURVE = {AFFORDABILITY_CURVE:.1f}  (poor can't afford expensive)")

    print(f"\n  GDP wealth multiplier (in-game, per category elasticity):")
    print(f"  Formula: 1 + (fc / 3.0 - 1) \u00d7 elasticity")
    gdp_types = ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]
    gdp_labels = ["noble", "clergy", "burghr", "soldr", "labor", "peasnt"]
    print(f"    {'Category':<12s} {'elast':>6s}", end="")
    for label in gdp_labels:
        print(f" {label:>7s}", end="")
    print()
    print(f"    {'\u2500' * 12} {'\u2500' * 6}", end="")
    for _ in gdp_labels:
        print(f" {'\u2500' * 7}", end="")
    print()
    for cat in CAT_ORDER:
        e = ELASTICITY[cat]
        print(f"    {cat:<12s} {e:>6.2f}", end="")
        for p in gdp_types:
            fc = FOOD_CONSUMPTION[p]
            m = get_gdp_multiplier(fc, e)
            print(f" {m:>7.2f}", end="")
        print()

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
        e = ELASTICITY[cat]
        cs = CONSUMER_SHARE[cat]
        print(f"\n  [{cat.upper()}]  elasticity={e:.2f}  consumer_share={cs:.0%}")
        print(f"  {'Good':<14s} {'Src':>4s} {'Price':>6s} {'Prc.F':>6s} {'CShr':>5s}")
        print(f"  {'\u2500' * 14} {'\u2500' * 4} {'\u2500' * 6} {'\u2500' * 6} {'\u2500' * 5}")
        for r in goods:
            src = "raw" if r["source"] == "raw" else "prod"
            print(f"  {r['name']:<14s} {src:>4s} {r['price']:>6.1f} {r['price_factor']:>6.2f} "
                  f"{r['consumer_share']:>5.0%}")


def print_effective(results):
    _section("EFFECTIVE DEMAND_ADD PER POP UNIT (base, before GDP multiplier)")
    print(f"  demand_add = pf \u00d7 aff \u00d7 cs \u00d7 fc \u00d7 {DEMAND_SCALE}")
    print(f"\n  {'Good':<14s} {'elast':>5s}", end="")
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
        print(f"  {r['name']:<14s} {r['elasticity']:>5.2f}", end="")
        for c in DISPLAY_TYPES:
            v = r["effective"].get(c, 0)
            aff = r["afford"].get(c, 1.0)
            if v > 0 and aff < 1.0:
                print(f" {v:>7.4f}~", end="")
            elif v > 0:
                print(f" {v:>8.4f}", end="")
            else:
                print(f" {'\u00b7':>8s}", end="")
        print()


def print_weights(results):
    _section("GDP WEALTH MULTIPLIER  (in-game, by category elasticity)")
    print(f"  Formula: 1 + (fc / 3.0 - 1) \u00d7 elasticity")
    print(f"  Applied in-game via sul_gdp_scale_* script values")
    print(f"\n  {'Category':<12s} {'Elast':>6s}", end="")
    for label in DISPLAY_LABELS:
        print(f" {label:>8s}", end="")
    print()
    print(f"  {'\u2500' * 12} {'\u2500' * 6}", end="")
    for _ in DISPLAY_LABELS:
        print(f" {'\u2500' * 8}", end="")
    print()

    for cat in CAT_ORDER:
        e = ELASTICITY[cat]
        print(f"  {cat:<12s} {e:>6.2f}", end="")
        for c in DISPLAY_TYPES:
            m = get_gdp_multiplier(FOOD_CONSUMPTION[c], e)
            print(f" {m:>8.2f}", end="")
        print()

    nob_lux = get_gdp_multiplier(FOOD_CONSUMPTION["nobles"], ELASTICITY["luxury"])
    pea_lux = get_gdp_multiplier(FOOD_CONSUMPTION["peasants"], ELASTICITY["luxury"])
    nob_nec = get_gdp_multiplier(FOOD_CONSUMPTION["nobles"], ELASTICITY["necessity"])
    pea_nec = get_gdp_multiplier(FOOD_CONSUMPTION["peasants"], ELASTICITY["necessity"])
    print(f"\n  Noble:Peasant ratios  luxury={nob_lux / pea_lux:.1f}:1  necessity={nob_nec / pea_nec:.1f}:1")




def compute_building_weights(results):
    """Compute production weights per specialization tier based on demand.

    For each spec's rural and guild tier, looks up the TOTAL demand for each
    building's produced good (pop demand + production chain demand) and
    normalizes into integer weights (per-mille).

    Total demand = pop_demand / consumer_share, where consumer_share < 1
    means production chains consume part of the output. This ensures goods
    with lower consumer share get proportionally more building levels than
    their pop demand alone would suggest.

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
        print_comparison(results)
        print_building_weights(results)


if __name__ == "__main__":
    main()
