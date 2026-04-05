#!/usr/bin/env python3
"""
Demand System Calculator for Wages and Provisions Demand Overhaul
=================================================================

Computes universal demand_add values for EU5 pop goods.

FORMULA:
  demand_add = GOODS_BUDGET_SHARE × tier_weight / price × source_factor / weighted_in_cat

  All pop types get the same demand_add (uniform { all = value }).
  Pop-type differentiation comes from the WPP system at runtime.
  tier_weight baked into demand_add; threshold checked in pop_demands.txt.

USAGE:
  python demand_calculator.py                # Full report
  python demand_calculator.py --pdx          # PDX REPLACE blocks to stdout
  python demand_calculator.py --write        # Write to sul_goods.txt
"""

import sys
import argparse
import os


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

CAT_ORDER = ["necessity", "basic", "common", "upper", "luxury", "exotic"]

GOODS_BUDGET_SHARE = 0.65  # 65% of wealth goes to goods demand, rest to estate activities
RAW_GOODS_FACTOR = 0.75 # Raw goods get 75% of produced goods demand (25% dampening)

# Ramped threshold model: pop_demand = tier_weight × max(0, wpp - threshold)
# tier_weight baked into demand_add, threshold checked in pop_demands.txt.
# No monthly tier computation needed — all evaluation in engine's pop demand cycle.
TIER_WEIGHT = {
    "necessity": 0.30,
    "basic":     0.25,
    "common":    0.20,
    "upper":     0.12,
    "luxury":    0.08,
    "exotic":    0.05,
}
TIER_THRESHOLD = {
    "necessity": 0,
    "basic":     0.05,
    "common":    0.12,
    "upper":     0.25,
    "luxury":    0.5,
    "exotic":    1.5,
}

POP_TYPES = [
    "nobles", "clergy", "burghers", "soldiers",
    "laborers", "peasants", "slaves", "tribesmen",
]


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
    {"name": "cloth", "category": "necessity", "source": "produced"},
    {"name": "pottery", "category": "necessity", "source": "produced"},
    {"name": "provisions", "category": "necessity", "source": "produced", "price": 2.4,
     "extra_fields": {"category": "produced", "color": "goods_provisions",
                       "default_market_price": 2.4, "transport_cost": 1.0},
     "set_food": 0.0001},

    # ─── FOOD ────────────────────────────────────────────────────────────
    {"name": "wheat", "category": "necessity", "source": "raw"},
    {"name": "rice", "category": "necessity", "source": "raw"},
    {"name": "maize", "category": "necessity", "source": "raw"},
    {"name": "millet", "category": "necessity", "source": "raw"},
    {"name": "potato", "category": "necessity", "source": "raw"},
    {"name": "fish", "category": "necessity", "source": "raw"},
    {"name": "legumes", "category": "necessity", "source": "raw"},
    {"name": "olives", "category": "necessity", "source": "raw"},
    {"name": "fruit", "category": "necessity", "source": "raw"},
    {"name": "livestock", "category": "necessity", "source": "raw"},
    {"name": "wild_game", "category": "necessity", "source": "raw"},

    # ─── BASIC ───────────────────────────────────────────────────────────
    {"name": "beer", "category": "basic", "source": "produced"},
    {"name": "salt", "category": "basic", "source": "raw"},
    {"name": "coal", "category": "basic", "source": "raw"},
    {"name": "beeswax", "category": "basic", "source": "raw"},

    # ─── COMMON ──────────────────────────────────────────────────────────
    {"name": "furniture", "category": "common", "source": "produced"},
    {"name": "leather", "category": "common", "source": "produced"},
    {"name": "glass", "category": "common", "source": "produced"},
    {"name": "paper", "category": "common", "source": "produced"},
    {"name": "medicaments", "category": "necessity", "source": "raw"},
    {"name": "weaponry", "category": "common", "source": "produced"},
    {"name": "liquor", "category": "common", "source": "produced"},
    {"name": "horses", "category": "common", "source": "raw"},

    # ─── UPPER ───────────────────────────────────────────────────────────
    {"name": "fine_cloth", "category": "upper", "source": "produced"},
    {"name": "silk", "category": "upper", "source": "raw"},
    {"name": "books", "category": "upper", "source": "produced"},
    {"name": "wine", "category": "common", "source": "raw"},
    {"name": "fur", "category": "common", "source": "raw"},
    {"name": "tea", "category": "upper", "source": "raw"},
    {"name": "coffee", "category": "upper", "source": "raw"},
    {"name": "cocoa", "category": "upper", "source": "raw"},
    {"name": "sugar", "category": "upper", "source": "raw"},
    {"name": "tobacco", "category": "upper", "source": "raw"},
    {"name": "amber", "category": "upper", "source": "raw"},

    # ─── LUXURIES ────────────────────────────────────────────────────────
    {"name": "jewelry", "category": "luxury", "source": "produced"},
    {"name": "porcelain", "category": "upper", "source": "produced"},
    {"name": "pearls", "category": "luxury", "source": "raw"},
    {"name": "ivory", "category": "luxury", "source": "raw"},
    {"name": "silver", "category": "luxury", "source": "raw"},
    {"name": "goods_gold", "category": "luxury", "source": "raw"},
    {"name": "gems", "category": "luxury", "source": "raw"},
    {"name": "marble", "category": "luxury", "source": "raw"},
    {"name": "elephants", "category": "luxury", "source": "raw"},

    # ─── EXOTIC ─────────────────────────────────────────────────────────
    {"name": "lacquerware", "category": "exotic", "source": "produced"},
    {"name": "pepper", "category": "exotic", "source": "raw"},
    {"name": "cloves", "category": "exotic", "source": "raw"},
    {"name": "saffron", "category": "exotic", "source": "raw"},
    {"name": "chili", "category": "exotic", "source": "raw"},
    {"name": "incense", "category": "upper", "source": "raw"},
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
    """Parse tokens inside { } into a dict. Returns (dict, next_pos).
    Bare values (no = sign) are collected into a '_list' key."""
    result = {}
    bare = []
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
        else:
            bare.append(key)
    if pos < len(tokens) and tokens[pos] == '}':
        pos += 1
    if bare:
        result["_list"] = bare
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

                info = {"_block": block}
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
        g["_block"] = vd.get("_block", {})

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


# ═══════════════════════════════════════════════════════════════════════════
# COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════

def compute():
    """Compute demand values for all goods. Returns list of result dicts.

    Formula: demand_add = GOODS_BUDGET_SHARE × tier_weight × source_factor / price / weighted_in_cat
    Where weighted_in_cat = Σ(source_factor) for all goods in the category.
    tier_weight baked into demand_add; pop_demand = max(0, wpp - threshold) at runtime.
    """
    cat_weighted = {}
    for g in GOODS:
        if "price" in g:
            sf = RAW_GOODS_FACTOR if g["source"] == "raw" else 1.0
            cat_weighted[g["category"]] = cat_weighted.get(g["category"], 0) + sf

    results = []
    for g in GOODS:
        if "price" not in g:
            print(f"  WARNING: {g['name']} has no price (vanilla scan missing?), skipping",
                  file=sys.stderr)
            continue

        cat = g["category"]
        price = g["price"]
        weighted_in_cat = cat_weighted.get(cat, 1)
        tier_weight = TIER_WEIGHT.get(cat, 0.10)

        source_factor = RAW_GOODS_FACTOR if g["source"] == "raw" else 1.0
        base = GOODS_BUDGET_SHARE * tier_weight / price * source_factor / weighted_in_cat
        demand_add = {"all": base}

        results.append({
            "name": g["name"],
            "category": g["category"],
            "source": g["source"],
            "price": price,
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


def _serialize_value(val, indent=1):
    """Serialize a parsed value back to PDX script."""
    prefix = "\t" * indent
    if isinstance(val, dict):
        inner = []
        # Bare list items first
        for item in val.get("_list", []):
            inner.append(f"{prefix}\t{item}")
        # Key-value pairs
        for k, v in val.items():
            if k == "_list":
                continue
            if isinstance(v, dict):
                inner.append(f"{prefix}\t{k} = {{")
                inner.append(_serialize_value(v, indent + 1))
                inner.append(f"{prefix}\t}}")
            elif isinstance(v, float):
                inner.append(f"{prefix}\t{k} = {_fmt(v)}")
            else:
                inner.append(f"{prefix}\t{v}")
        return "\n".join(inner)
    elif isinstance(val, float):
        return f"{prefix}{_fmt(val)}"
    else:
        return f"{prefix}{val}"


# Fields to strip from vanilla when writing REPLACE blocks.
# Our computed demand_add and wealth_impact_threshold replace these.
# food is stripped because provisions replaces vanilla food system.
_STRIP_FIELDS = {"demand_add", "demand_multiply", "wealth_impact_threshold",
                 "development_threshold", "food"}


def generate_pdx(results):
    """Generate PDX REPLACE blocks as a string.

    For each good in our system, outputs a complete REPLACE block containing
    all vanilla fields (method, category, color, price, etc.) with demand
    fields replaced by our computed values. No demand_multiply or
    development_threshold in output.
    """
    lines = [
        "# WPDO: Merged goods overrides",
        "# Generated by demand_calculator.py",
        f"# Formula: demand_add = {GOODS_BUDGET_SHARE} \u00d7 tier_weight / price \u00d7 source_factor / weighted_in_cat",
        "",
    ]

    # Find the matching GOODS entry to get _block
    goods_by_name = {g["name"]: g for g in GOODS}

    for r in results:
        name = r["name"]
        da = r["demand_add"]
        g_entry = goods_by_name.get(name, {})
        block = g_entry.get("_block", {})
        extra = g_entry.get("extra_fields", {})

        # Use extra_fields for mod-only goods that aren't in vanilla
        if not block and extra:
            block = extra

        # Header comment
        lines.append(
            f"# {name} [{r['category']}/{r['source']}] "
            f"price={r['price']:.1f}")

        # Only REPLACE vanilla goods; mod-only goods (no vanilla _block) get no prefix
        prefix = "REPLACE:" if g_entry.get("_block") else ""
        lines.append(f"{prefix}{name} = {{")

        # Emit all vanilla fields except stripped ones
        for k, v in block.items():
            if k in _STRIP_FIELDS or k == "_list":
                continue
            if isinstance(v, dict):
                lines.append(f"\t{k} = {{")
                for item in v.get("_list", []):
                    lines.append(f"\t\t{item}")
                for sk, sv in v.items():
                    if sk == "_list":
                        continue
                    if isinstance(sv, float):
                        lines.append(f"\t\t{sk} = {_fmt(sv)}")
                    else:
                        lines.append(f"\t\t{sk} = {sv}")
                lines.append("\t}")
            elif isinstance(v, float):
                lines.append(f"\t{k} = {_fmt(v)}")
            else:
                lines.append(f"\t{k} = {v}")

        # Explicit food override (e.g. provisions needs food = 0.0001)
        set_food = g_entry.get("set_food")
        if set_food is not None:
            lines.append(f"\tfood = {_fmt(set_food)}")

        # Our demand_add — flat for all pops, differentiation comes from WPP gate
        if da:
            lines.append("\tdemand_add = {")
            if "all" in da:
                lines.append(f"\t\tall = {_fmt(da['all'])}")
            else:
                for p in POP_TYPES:
                    if p in da:
                        lines.append(f"\t\t{p} = {_fmt(da[p])}")
            lines.append("\t}")

        # Disable engine wealth gate — our budget system handles gating
        lines.append("\twealth_impact_threshold = {")
        lines.append("\t\tall = 0")
        lines.append("\t}")

        lines.append("}")
        lines.append("")

    return "\n".join(lines)


MANUAL_TAIL = """
# ─────────────────────────────────
# NON-DEMAND OVERRIDES
# ─────────────────────────────────

# Wool — zeroes food (not in REPLACE list above)

INJECT:wool = {
\tfood = 0
}

# Tools — production input, not consumer good; base_production for RGO bootstrapping

INJECT:tools = {
\tbase_production = 1
}

# ─────────────────────────────────
# CONSTRUCTION — no pop demand
# ─────────────────────────────────

REPLACE:lumber = {
\tmethod = forestry
\tcategory = raw_material
\tcolor = goods_lumber
\tdefault_market_price = 1.5
\tbase_production = 0.1
\ttransport_cost = 1
\tai_rgo_size_importance = 3
\tai_rgo_expansion_priority = 0.025
}

REPLACE:masonry = {
\tcategory = produced
\tcolor = goods_masonry
\tdefault_market_price = 1
\tai_rgo_expansion_priority = 0.25
}
"""


def write_pdx(results):
    """Write PDX output to sul_goods.txt."""
    content = generate_pdx(results)
    content += MANUAL_TAIL
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mod_dir = os.path.dirname(script_dir)
    out_path = os.path.join(mod_dir, "in_game", "common", "goods", "sul_goods.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write(content)
    print(f"Wrote {out_path}")


# ═══════════════════════════════════════════════════════════════════════════
# DISPLAY
# ═══════════════════════════════════════════════════════════════════════════

def _section(title):
    w = 76
    print(f"\n{'=' * w}")
    print(f"  {title}")
    print(f"{'=' * w}")


def print_config():
    _section("CONFIGURATION")

    print(f"\n  Formula: demand_add = {GOODS_BUDGET_SHARE} × tier_weight / price × source_factor / weighted_in_cat")

    print(f"\n  Tier weights and thresholds:")
    print(f"  {'Category':<12s} {'Weight':>8s} {'Threshold':>10s}")
    print(f"  {'-' * 12} {'-' * 8} {'-' * 10}")
    for cat in CAT_ORDER:
        w = TIER_WEIGHT[cat]
        t = TIER_THRESHOLD[cat]
        print(f"  {cat:<12s} {w:>8.2f} {t:>10.1f}")


def print_demands(results):
    _section("DEMAND_ADD (uniform, before WPP multiplier)")

    print(f"\n  {'Good':<14s} {'Cat':<10s} {'Price':>6s} {'Source':>8s} {'demand_add':>10s}")
    print(f"  {'-' * 14} {'-' * 10} {'-' * 6} {'-' * 8} {'-' * 10}")

    last_cat = None
    for r in results:
        if r["category"] != last_cat:
            if last_cat:
                print()
            last_cat = r["category"]
        da_val = r["demand_add"].get("all", 0)
        print(f"  {r['name']:<14s} {r['category']:<10s} {r['price']:>6.1f} {r['source']:>8s} {da_val:>10.4f}")


# ═══════════════════════════════════════════════════════════════════════════
# GUI TOOLTIP GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

# Pop types shown in the budget tooltip (matches the main table rows)
GUI_POP_TYPES = ["nobles", "clergy", "burghers", "soldiers", "laborers", "peasants"]


def _gen_pop_subtip(pop, display, results):
    """Generate the budget sub-tooltip block for one pop type.

    Per tier: a header TooltipManualTableField + a TooltipListRowContent with
    datamodel iterating the global demand_add map. Both gated on tier visibility.
    """
    tier_labels = {
        "necessity": "Necessity", "basic": "Basic", "common": "Common",
        "upper": "Upper", "luxury": "Luxury", "exotic": "Exotic",
    }

    blocks = []
    for tier in CAT_ORDER:
        map_name = f"pdo_da_{tier}"
        sv_name = f"pdo_{pop}_{tier}"
        label = tier_labels[tier]
        vis = f"GreaterThan_CFixedPoint(Location.MakeScope.ScriptValue('{sv_name}'), '(CFixedPoint)0')"

        blocks.append(f"""
\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{
\t\t\t\t\t\t\t\t\t\t\t\t\tvisible = "[{vis}]"
\t\t\t\t\t\t\t\t\t\t\t\t\tblockoverride "field_content" {{
\t\t\t\t\t\t\t\t\t\t\t\t\t\ttext_single = {{ layoutpolicy_horizontal = expanding raw_text = "#T {label}#!" }}
\t\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t\tTooltipListRowContent = {{
\t\t\t\t\t\t\t\t\t\t\t\t\tvisible = "[{vis}]"
\t\t\t\t\t\t\t\t\t\t\t\t\tmax_update_rate = 30
\t\t\t\t\t\t\t\t\t\t\t\t\tdatamodel = "[GetGlobalMapKeys('{map_name}')]"
\t\t\t\t\t\t\t\t\t\t\t\t\titem = {{
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\tblockoverride "field_content" {{
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\tdatacontext = "[Scope.GetGoods]"
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\ticon = {{ size = {{ 20 20 }} texture = "[GetGoodsIcon(Goods.Self)]" }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\ttext_single = {{ layoutpolicy_horizontal = expanding margin_left = 3 text = "[Goods.GetName]" }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\ttext_single = {{ min_width = 60 align = right raw_text = "[Multiply_CFixedPoint(GetVariableFromGlobalVariableMap('{map_name}', Goods.MakeScope).GetValue, Location.MakeScope.ScriptValue('{sv_name}'))|2]" }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t\t}}""")

    tier_content = "".join(blocks)
    return f"""
\t\t\t\t\t\ttooltipwidget = {{
\t\t\t\t\t\t\tContextualTooltipType = {{
\t\t\t\t\t\t\t\tblockoverride "tooltip_title" {{  }}
\t\t\t\t\t\t\t\tblockoverride "tooltip_content" {{
\t\t\t\t\t\t\t\t\tTooltipListBase = {{
\t\t\t\t\t\t\t\t\t\tmax_update_rate = 30
\t\t\t\t\t\t\t\t\t\tTooltipTableHeader = {{ blockoverride "tableheader_text" {{ raw_text = "#T {display} — Demand Breakdown#!" }} }}
\t\t\t\t\t\t\t\t\t\tTooltipListScrollArea = {{
\t\t\t\t\t\t\t\t\t\t\tblockoverride "block_scrollarea" {{ maximumsize = {{ -1 600 }} minimumsize = {{ -1 30 }} }}
\t\t\t\t\t\t\t\t\t\t\tblockoverride "scrollarea_content" {{
\t\t\t\t\t\t\t\t\t\t\t\tTooltipListRowContent = {{
{tier_content}
\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t}}"""


def generate_gui_tooltip(results):
    """Generate the complete PDO budget tooltip section for the GUI file."""
    pop_display = {
        "nobles": "Nobles", "clergy": "Clergy", "burghers": "Burghers",
        "soldiers": "Soldiers", "laborers": "Laborers", "peasants": "Peasants",
    }
    pop_share_sv = {
        "nobles": "pdo_noble_share_pct", "clergy": "pdo_clergy_share_pct",
        "burghers": "pdo_burgher_share_pct", "soldiers": "pdo_soldier_share_pct",
        "laborers": "pdo_laborer_share_pct", "peasants": "pdo_peasant_share_pct",
    }
    pop_rw_sv = {
        "nobles": "pdo_noble_rents_wages", "clergy": "pdo_clergy_rents_wages",
        "burghers": "pdo_burgher_rents_wages", "soldiers": "pdo_soldier_rents_wages",
        "laborers": "pdo_laborer_rents_wages", "peasants": "pdo_peasant_rents_wages",
    }
    pop_tax_sv = {
        "nobles": "pdo_noble_tax_income", "clergy": "pdo_clergy_tax_income",
        "burghers": "pdo_burgher_tax_income", "soldiers": "pdo_soldier_tax_income",
        "laborers": "pdo_laborer_tax_income", "peasants": "pdo_peasant_tax_income",
    }

    lines = []
    lines.append('\t### PDO: POP DEMAND BUDGET')
    lines.append('')
    lines.append("\tTooltipListBase = {")
    lines.append("\t\tvisible = \"[Location.MakeScope.GetVariable('pdo_local_gdp').IsSet]\"")
    lines.append("\t\tmax_update_rate = 30")
    lines.append("")
    lines.append('\t\tTooltipTableHeader = { blockoverride "tableheader_text" { raw_text = "#T Pop Demand Budget#!" } }')
    lines.append("")
    lines.append("\t\tTooltipListRowContent = {")

    # Header row with hover tooltips
    lines.append("\t\t\t# Header row")
    lines.append('\t\t\tTooltipManualTableField = {')
    lines.append('\t\t\t\tblockoverride "field_content" {')
    lines.append('\t\t\t\t\ttext_single = { layoutpolicy_horizontal = expanding margin_left = 5 raw_text = "#T Pop Type#!" }')
    lines.append('\t\t\t\t\ttext_single = { min_width = 80 max_width = 80 align = right raw_text = "#T Share#!" tooltip = "Percentage of this location\'s wealth controlled by this pop type, based on estate power." }')
    lines.append('\t\t\t\t\ttext_single = { min_width = 80 max_width = 80 align = right raw_text = "#T Tax Base#!" tooltip = "Income from the location\'s tax base, distributed by wealth share." }')
    lines.append('\t\t\t\t\ttext_single = { min_width = 80 max_width = 80 align = right raw_text = "#T Wages#!" tooltip = "Imputed wage income added to GDP based on pop type and population." }')
    lines.append('\t\t\t\t\ttext_single = { min_width = 80 max_width = 80 align = right raw_text = "#T Budget#!" tooltip = "Total income allocated to goods demand (Tax Base + Wages)." }')
    lines.append('\t\t\t\t}')
    lines.append('\t\t\t}')

    for pop in GUI_POP_TYPES:
        display = pop_display[pop]
        share_sv = pop_share_sv[pop]
        rw_sv = pop_rw_sv[pop]
        tax_sv = pop_tax_sv[pop]
        subtip = _gen_pop_subtip(pop, display, results)

        lines.append(f"")
        lines.append(f"\t\t\t# {display}")
        lines.append(f"\t\t\tTooltipManualTableField = {{")
        lines.append(f"\t\t\t\tvisible = \"[GreaterThan_CFixedPoint(Location.MakeScope.ScriptValue('{share_sv}'), '(CFixedPoint)0')]\"")
        lines.append(f"")
        lines.append(f'\t\t\t\tblockoverride "field_content" {{')
        lines.append(f"\t\t\t\t\ticon = {{ size = {{ 20 20 }} texture = \"[GetGraphicalCultureTextureForPopType(GetPopTypeByName('{pop}'))]\" }}")
        lines.append(f'\t\t\t\t\ttext_single = {{ layoutpolicy_horizontal = expanding margin_left = 5 raw_text = "{display}" }}')
        lines.append(f"\t\t\t\t\ttext_single = {{ min_width = 80 max_width = 80 align = right raw_text = \"[Location.MakeScope.ScriptValue('{share_sv}')|0]%\" }}")
        lines.append(f"\t\t\t\t\ttext_single = {{ min_width = 80 max_width = 80 align = right raw_text = \"[Location.MakeScope.ScriptValue('{tax_sv}')|2]@gold!\" }}")
        lines.append(f"\t\t\t\t\ttext_single = {{ min_width = 80 max_width = 80 align = right raw_text = \"[Subtract_CFixedPoint(Location.MakeScope.ScriptValue('{rw_sv}'), Location.MakeScope.ScriptValue('{tax_sv}'))|2]@gold!\" }}")
        lines.append(f"\t\t\t\t\ttext_single = {{")
        lines.append(f"\t\t\t\t\t\tmin_width = 80")
        lines.append(f"\t\t\t\t\t\tmax_width = 80")
        lines.append(f"\t\t\t\t\t\talign = right")
        lines.append(f"\t\t\t\t\t\traw_text = \"[Location.MakeScope.ScriptValue('{rw_sv}')|2]@gold!\"")
        lines.append(subtip)
        lines.append(f"\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t}}")
        lines.append(f"\t\t\t}}")

    # Estate-only rows (dhimmi, cossacks, tribes) — visible when share > 0
    estate_rows = [
        ("Dhimmi", "pdo_dhimmi_share_pct", "pdo_dhimmi_tax_income", "pdo_dhimmi_rents_wages"),
        ("Cossacks", "pdo_cossacks_share_pct", "pdo_cossacks_tax_income", "pdo_cossacks_rents_wages"),
        ("Tribes", "pdo_tribes_share_pct", "pdo_tribes_tax_income", "pdo_tribes_rents_wages"),
    ]
    for display, share_sv, tax_sv, rw_sv in estate_rows:
        lines.append(f"")
        lines.append(f"\t\t\t# {display}")
        lines.append(f"\t\t\tTooltipManualTableField = {{")
        lines.append(f"\t\t\t\tvisible = \"[GreaterThan_CFixedPoint(Location.MakeScope.ScriptValue('{share_sv}'), '(CFixedPoint)0')]\"")
        lines.append(f"")
        lines.append(f'\t\t\t\tblockoverride "field_content" {{')
        lines.append(f'\t\t\t\t\ttext_single = {{ layoutpolicy_horizontal = expanding layoutpolicy_horizontal = expanding margin_left = 5 raw_text = "{display}" }}')
        lines.append(f"\t\t\t\t\ttext_single = {{ min_width = 80 max_width = 80 align = right raw_text = \"[Location.MakeScope.ScriptValue('{share_sv}')|0]%\" }}")
        lines.append(f"\t\t\t\t\ttext_single = {{ min_width = 80 max_width = 80 align = right raw_text = \"[Location.MakeScope.ScriptValue('{tax_sv}')|2]@gold!\" }}")
        lines.append(f"\t\t\t\t\ttext_single = {{ min_width = 80 max_width = 80 align = right raw_text = \"[Subtract_CFixedPoint(Location.MakeScope.ScriptValue('{rw_sv}'), Location.MakeScope.ScriptValue('{tax_sv}'))|2]@gold!\" }}")
        lines.append(f"\t\t\t\t\ttext_single = {{ min_width = 80 max_width = 80 align = right raw_text = \"[Location.MakeScope.ScriptValue('{rw_sv}')|2]@gold!\" }}")
        lines.append(f"\t\t\t\t}}")
        lines.append(f"\t\t\t}}")

    lines.append("\t\t}")
    lines.append("\t}")

    return "\n".join(lines)


def generate_demand_init(results):
    """Generate pdo_demand_init.txt scripted effect.

    Creates 6 variable maps on the location (one per tier), each mapping
    goods to their demand_add constant. Called once during init.
    GUI iterates these maps to get all goods per tier.
    """
    lines = [
        "# Generated by demand_calculator.py --cache",
        "# Static demand_add maps for GUI tooltip iteration.",
        "# 6 maps (one per tier), each keyed by goods, value = demand_add.",
        "# Called once per location during pdo_initialize_all.",
        "",
        "pdo_init_demand_maps = {",
    ]

    # Group by category
    by_cat = {}
    for r in results:
        da = r["demand_add"].get("all", 0)
        if da <= 0:
            continue
        cat = r["category"]
        by_cat.setdefault(cat, []).append(r)

    for cat in CAT_ORDER:
        goods_in_cat = by_cat.get(cat, [])
        if not goods_in_cat:
            continue
        lines.append(f"\t# {cat}")
        for r in goods_in_cat:
            da_str = _fmt(r["demand_add"]["all"])
            lines.append(f"\tadd_to_global_variable_map = {{ name = pdo_da_{cat} key = goods:{r['name']} value = {da_str} }}")
        lines.append("")

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def write_demand_init(results):
    """Write the demand init scripted effect."""
    content = generate_demand_init(results)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mod_dir = os.path.dirname(script_dir)
    out_path = os.path.join(mod_dir, "in_game", "common", "scripted_effects",
                            "pdo_demand_init.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write(content)
    print(f"Wrote {out_path}")


def write_gui(results):
    """Write the generated GUI tooltip to aaa_pdo_location_tooltips.gui.

    Replaces everything from ### PDO: POP DEMAND BUDGET to the end of the template.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mod_dir = os.path.dirname(script_dir)
    gui_path = os.path.join(mod_dir, "in_game", "gui", "shared",
                            "aaa_pdo_location_tooltips.gui")

    with open(gui_path, encoding="utf-8-sig") as f:
        content = f.read()

    marker = "### PDO: POP DEMAND BUDGET"
    idx = content.find(marker)
    if idx < 0:
        print(f"  ERROR: marker '{marker}' not found in {gui_path}", file=sys.stderr)
        return

    # Find the start of the line containing the marker
    line_start = content.rfind("\n", 0, idx)
    if line_start < 0:
        line_start = 0
    else:
        line_start += 1

    # The template ends with "}\n" — keep everything before the marker,
    # insert our generated block, close the template
    before = content[:line_start]
    generated = generate_gui_tooltip(results)

    with open(gui_path, "w", encoding="utf-8-sig") as f:
        f.write(before)
        f.write(generated)
        f.write("\n}\n")

    print(f"Wrote GUI tooltip to {gui_path}")


# ===============================================================
# CLI
# ===============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Demand System Calculator: GOODS_BUDGET_SHARE x fc / price"
    )
    parser.add_argument("--pdx", action="store_true",
                        help="Output PDX REPLACE blocks to stdout")
    parser.add_argument("--write", action="store_true",
                        help="Write PDX output to pdo_goods_overrides.txt")
    parser.add_argument("--gui", action="store_true",
                        help="Write generated GUI tooltip to aaa_pdo_location_tooltips.gui")
    parser.add_argument("--cache", action="store_true",
                        help="Write demand init scripted effect (pdo_demand_init.txt)")
    parser.add_argument("--vanilla-dir", metavar="DIR",
                        help="Override vanilla goods directory path")
    args = parser.parse_args()

    # Scan vanilla game files
    vdir = args.vanilla_dir or VANILLA_GOODS_DIR
    vanilla_data = scan_vanilla(vdir)
    if vanilla_data:
        merge_vanilla(GOODS, vanilla_data)
        print(f"  Scanned {len(vanilla_data)} goods from {vdir}", file=sys.stderr)
    else:
        print(f"  WARNING: Vanilla dir not found: {vdir}", file=sys.stderr)

    results = compute()

    if args.write:
        write_pdx(results)
        if not args.gui:
            return

    if args.cache:
        write_demand_init(results)
        if not args.gui:
            return

    if args.gui:
        write_gui(results)
        return

    if args.pdx:
        print(generate_pdx(results))
        return

    print_config()
    print_demands(results)


if __name__ == "__main__":
    main()
