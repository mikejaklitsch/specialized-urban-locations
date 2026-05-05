#!/usr/bin/env python3
"""
Demand System Calculator for Wages and Provisions Demand Overhaul
=================================================================

Computes universal demand_add values for EU5 pop goods.

FORMULA:
  demand_add = GOODS_BUDGET_SHARE / price × source_factor / weighted_in_cat

  All pop types get the same demand_add (uniform { all = value }).
  Pop-type differentiation comes from the WPP system at runtime.
  Tier allocation handled by continuous percentage model (no tier_weight in demand_add).

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

# Universal demand model: share = (floor + slope × WPP) / (A + WPP)
# floor = baseline need at zero wealth, slope = growth with wealth
# Constraint: sum(floors) = A, sum(slopes) = 1.0
DEMAND_A = 3.0
TIER_PARAMS = {
    "necessity":  {"floor": 1.50, "slope": 0.03},
    "basic":      {"floor": 0.70, "slope": 0.08},
    "common":     {"floor": 0.40, "slope": 0.07},
    "upper":      {"floor": 0.20, "slope": 0.16},
    "luxury":     {"floor": 0.10, "slope": 0.13},
    "exotic":     {"floor": 0.05, "slope": 0.06},
    "enrichment": {"floor": 0.05, "slope": 0.47},
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
    # ─── NECESSITY (5) — bare survival ───────────────────────────────────
    # provisions removed: demand driven by native food system (sul_goods.txt + pop_demands)
    {"name": "cloth", "category": "necessity", "source": "produced"},
    {"name": "pottery", "category": "necessity", "source": "produced"},
    {"name": "medicaments", "category": "necessity", "source": "raw"},
    {"name": "salt", "category": "necessity", "source": "raw"},
    {"name": "coal", "category": "necessity", "source": "raw"},

    # ─── BASIC (7) — daily household ─────────────────────────────────────
    {"name": "beer", "category": "basic", "source": "produced"},
    {"name": "wine", "category": "basic", "source": "raw"},
    {"name": "liquor", "category": "basic", "source": "produced"},
    {"name": "beeswax", "category": "basic", "source": "raw"},
    {"name": "leather", "category": "basic", "source": "produced"},
    {"name": "furniture", "category": "basic", "source": "produced"},
    {"name": "paper", "category": "basic", "source": "produced"},

    # ─── COMMON (5) — quality of life ────────────────────────────────────
    {"name": "glass", "category": "common", "source": "produced"},
    {"name": "fur", "category": "common", "source": "raw"},
    {"name": "horses", "category": "common", "source": "raw"},
    {"name": "weaponry", "category": "common", "source": "produced"},
    {"name": "incense", "category": "common", "source": "raw"},

    # ─── UPPER (9) — aspirational ────────────────────────────────────────
    {"name": "fine_cloth", "category": "upper", "source": "produced"},
    {"name": "books", "category": "upper", "source": "produced"},
    {"name": "porcelain", "category": "upper", "source": "produced"},
    {"name": "tea", "category": "upper", "source": "raw"},
    {"name": "coffee", "category": "upper", "source": "raw"},
    {"name": "cocoa", "category": "upper", "source": "raw"},
    {"name": "sugar", "category": "upper", "source": "raw"},
    {"name": "tobacco", "category": "upper", "source": "raw"},
    {"name": "amber", "category": "upper", "source": "raw"},

    # ─── LUXURY (5) — wealth display ────────────────────────────────────
    {"name": "jewelry", "category": "luxury", "source": "produced"},
    {"name": "pearls", "category": "luxury", "source": "raw"},
    {"name": "ivory", "category": "luxury", "source": "raw"},
    {"name": "gems", "category": "luxury", "source": "raw"},
    {"name": "marble", "category": "luxury", "source": "raw"},

    # ─── EXOTIC (5) — rare trade goods ───────────────────────────────────
    {"name": "lacquerware", "category": "exotic", "source": "produced"},
    {"name": "pepper", "category": "exotic", "source": "raw"},
    {"name": "cloves", "category": "exotic", "source": "raw"},
    {"name": "saffron", "category": "exotic", "source": "raw"},
    {"name": "chili", "category": "exotic", "source": "raw"},
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
        with open(filepath, encoding="utf-8") as f:
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

    Formula: demand_add = GOODS_BUDGET_SHARE × source_factor / price / weighted_in_cat
    Where weighted_in_cat = Σ(source_factor) for all goods in the category.
    Tier allocation handled at runtime by the continuous percentage model.
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

        source_factor = RAW_GOODS_FACTOR if g["source"] == "raw" else 1.0
        base = GOODS_BUDGET_SHARE / price * source_factor / weighted_in_cat
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
        f"# Formula: demand_add = {GOODS_BUDGET_SHARE} / price \u00d7 source_factor / weighted_in_cat",
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


def write_pdx(results):
    """Write PDX output to sul_goods.txt."""
    content = generate_pdx(results)
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


def compute_macros():
    """Compute the @macro values for the script files."""
    macros = {"A": DEMAND_A}
    for cat, p in TIER_PARAMS.items():
        macros[f"{cat}_floor"] = p["floor"]
        macros[f"{cat}_slope"] = p["slope"]
    return macros


def print_config():
    _section("CONFIGURATION")

    print(f"\n  Formula: demand_add = {GOODS_BUDGET_SHARE} / price × source_factor / weighted_in_cat")
    print(f"  Tier allocation: share = (floor + slope × WPP) / ({DEMAND_A} + WPP)")

    print(f"\n  {'Tier':<12s} {'Floor':>6s} {'Slope':>6s}")
    print(f"  {'-'*12} {'-'*6} {'-'*6}")
    for cat in CAT_ORDER + ["enrichment"]:
        p = TIER_PARAMS.get(cat)
        if p:
            print(f"  {cat:<12s} {p['floor']:>6.2f} {p['slope']:>6.2f}")

    floor_sum = sum(p["floor"] for p in TIER_PARAMS.values())
    slope_sum = sum(p["slope"] for p in TIER_PARAMS.values())
    print(f"\n  Σ floors = {floor_sum:.2f} (must = {DEMAND_A}), Σ slopes = {slope_sum:.2f} (must = 1.0)")

    print(f"\n  Budget shares at sample WPP values:")
    print(f"  {'WPP':>6s}  {'nec':>5s} {'bas':>5s} {'com':>5s} {'upp':>5s} {'lux':>5s} {'exo':>5s}  {'enr':>5s}")
    print(f"  {'-'*6}  {'-'*5} {'-'*5} {'-'*5} {'-'*5} {'-'*5} {'-'*5}  {'-'*5}")
    for wpp in [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0]:
        denom = DEMAND_A + wpp
        shares = {}
        for cat in CAT_ORDER + ["enrichment"]:
            p = TIER_PARAMS[cat]
            shares[cat] = (p["floor"] + p["slope"] * wpp) / denom
        total = sum(shares.values())
        print(f"  {wpp:>6.1f}  {shares['necessity']:>5.1%} {shares['basic']:>5.1%} {shares['common']:>5.1%} {shares['upper']:>5.1%} {shares['luxury']:>5.1%} {shares['exotic']:>5.1%}  {shares['enrichment']:>5.1%}")


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


PROVISIONS_COST_SV = {
    "nobles": "sul_noble_provisions_cost",
    "clergy": "sul_clergy_provisions_cost",
    "burghers": "sul_burgher_provisions_cost",
    "soldiers": "sul_soldier_provisions_cost",
    "laborers": "sul_laborer_provisions_cost",
}

PROVISIONS_QTY_SV = {
    "nobles": "sul_noble_provisions_qty",
    "clergy": "sul_clergy_provisions_qty",
    "burghers": "sul_burgher_provisions_qty",
    "soldiers": "sul_soldier_provisions_qty",
    "laborers": "sul_laborer_provisions_qty",
}

POP_WAGE_SV = {
    "nobles": "sul_noble_wage_rate", "clergy": "sul_clergy_wage_rate",
    "burghers": "sul_burgher_wage_rate", "soldiers": "sul_soldier_wage_rate",
    "laborers": "sul_laborer_wage_rate", "peasants": "sul_peasant_wage_rate",
    "tribesmen": "sul_tribesmen_wage_rate",
}

POP_RETURN_SV = {
    "nobles": "sul_noble_total_return", "clergy": "sul_clergy_total_return",
    "burghers": "sul_burgher_total_return", "soldiers": "sul_soldier_total_return",
    "laborers": "sul_laborer_total_return", "peasants": "sul_peasant_total_return",
    "tribesmen": "sul_tribesmen_total_return",
}

POP_WPP_SV = {
    "nobles": "sul_noble_demand_per_pop", "clergy": "sul_clergy_demand_per_pop",
    "burghers": "sul_burgher_demand_per_pop", "soldiers": "sul_soldier_demand_per_pop",
    "laborers": "sul_laborer_demand_per_pop", "peasants": "sul_peasant_demand_per_pop",
    "tribesmen": "sul_tribesmen_demand_per_pop",
}


def prov_qty_sv_label(pop):
    """Human-readable provisions qty for the subtraction line label."""
    qty_map = {
        "nobles": "0.80", "clergy": "0.20", "burghers": "0.20",
        "soldiers": "0.15", "laborers": "0.05",
    }
    return qty_map.get(pop, "0")


def _gen_demand_template(pop, display, results):
    """Generate a standalone template definition for one pop type's WPP breakdown.

    Contains WPP summation (Wages + Returns - Provisions = WPP), then
    per-tier demand breakdown with provisions showing actual cost.
    Returns a complete `template sul_{pop}_demand_breakdown_tooltip { ... }` block.
    """
    tier_labels = {
        "necessity": "Necessity", "basic": "Basic", "common": "Common",
        "upper": "Upper", "luxury": "Luxury", "exotic": "Exotic",
    }

    pop_key = pop.rstrip("s") if pop != "peasants" else "peasant"
    wage_sv = POP_WAGE_SV[pop]
    return_sv = POP_RETURN_SV[pop]
    wpp_sv = POP_WPP_SV[pop]
    prov_cost_sv = PROVISIONS_COST_SV.get(pop)
    prov_qty_sv = PROVISIONS_QTY_SV.get(pop)

    P = "\t\t\t\t\t\t"

    rows = []

    # WPP summation section
    rows.append(f'{P}TooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "#T Wealth Per 1k Pops#!" }} }} }}')
    rows.append(f'{P}TooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Wages" }} text_single = {{ min_width = 80 align = right raw_text = "[Location.MakeScope.ScriptValue(\'{wage_sv}\')|3]@gold!" }} }} }}')
    rows.append(f'{P}TooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "#G + Returns#!" }} text_single = {{ min_width = 80 align = right raw_text = "#G +[Location.MakeScope.ScriptValue(\'{return_sv}\')|3]@gold!#!" }} }} }}')
    if prov_cost_sv:
        rows.append(f'{P}TooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "#R − Provisions ({prov_qty_sv_label(pop)})#!" }} text_single = {{ min_width = 80 align = right raw_text = "#R −[Location.MakeScope.ScriptValue(\'{prov_cost_sv}\')|3]@gold!#!" }} }} }}')
    rows.append(f'{P}TooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "#bold = WPP#!" }} text_single = {{ min_width = 80 align = right raw_text = "#bold [Location.MakeScope.ScriptValue(\'{wpp_sv}\')|3]@gold!#!" }} }} }}')

    # Demand Breakdown header
    rows.append(f'{P}TooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "#T Demand Breakdown#!" }} }} }}')

    # Provisions demand row
    if prov_cost_sv:
        rows.append(f'{P}TooltipManualTableField = {{ blockoverride "field_content" {{ icon = {{ size = {{ 20 20 }} texture = "gfx/interface/icons/trade_goods/icon_goods_provisions.dds" }} text_single = {{ layoutpolicy_horizontal = expanding margin_left = 3 raw_text = "Provisions" }} text_single = {{ min_width = 80 align = right raw_text = "[Location.MakeScope.ScriptValue(\'{prov_qty_sv}\')|3]" }} }} }}')

    # Per-tier goods lists
    for tier in CAT_ORDER:
        map_name = f"sul_da_{tier}"
        sv_name = f"sul_{pop}_{tier}"
        label = tier_labels[tier]
        vis = f"GreaterThan_CFixedPoint(Location.MakeScope.ScriptValue('{sv_name}'), '(CFixedPoint)0')"

        rows.append(f"""
{P}TooltipManualTableField = {{
{P}\tvisible = "[{vis}]"
{P}\tblockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "#T {label}#!" }} }}
{P}}}
{P}TooltipListRowContent = {{
{P}\tvisible = "[{vis}]"
{P}\tmax_update_rate = 30
{P}\tdatamodel = "[GetGlobalMapKeys('{map_name}')]"
{P}\titem = {{
{P}\t\tTooltipManualTableField = {{
{P}\t\t\tblockoverride "field_content" {{
{P}\t\t\t\tdatacontext = "[Scope.GetGoods]"
{P}\t\t\t\ticon = {{ size = {{ 20 20 }} texture = "[GetGoodsIcon(Goods.Self)]" }}
{P}\t\t\t\ttext_single = {{ layoutpolicy_horizontal = expanding margin_left = 3 text = "[Goods.GetName]" }}
{P}\t\t\t\ttext_single = {{ min_width = 80 align = right raw_text = "[Multiply_CFixedPoint(GetVariableFromGlobalVariableMap('{map_name}', Goods.MakeScope).GetValue, Location.MakeScope.ScriptValue('{sv_name}'))|2]" }}
{P}\t\t\t}}
{P}\t\t}}
{P}\t}}
{P}}}""")

    content = "\n".join(rows)
    template_name = f"sul_{pop}_demand_breakdown_tooltip"
    return f"""template {template_name} {{
\ttooltipwidget = {{
\t\tContextualTooltipType = {{
\t\t\tblockoverride "tooltip_title" {{  }}
\t\t\tblockoverride "tooltip_content" {{
\t\t\t\tTooltipListBase = {{
\t\t\t\t\tmax_update_rate = 30
\t\t\t\t\tTooltipTableHeader = {{ blockoverride "tableheader_text" {{ raw_text = "#T {display} — WPP Breakdown#!" }} }}
\t\t\t\t\tTooltipListScrollArea = {{
\t\t\t\t\t\tblockoverride "block_scrollarea" {{ maximumsize = {{ -1 600 }} minimumsize = {{ -1 30 }} }}
\t\t\t\t\t\tblockoverride "scrollarea_content" {{
\t\t\t\t\t\t\tTooltipListRowContent = {{
{content}
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t}}
\t\t\t\t\t}}
\t\t\t\t}}
\t\t\t}}
\t\t}}
\t}}
}}"""


def generate_standalone_templates(results):
    """Generate all standalone demand breakdown templates."""
    all_pops = [
        ("nobles", "Nobles"), ("clergy", "Clergy"), ("burghers", "Burghers"),
        ("soldiers", "Soldiers"), ("laborers", "Laborers"), ("peasants", "Peasants"),
        ("tribesmen", "Tribesmen"),
    ]
    blocks = ["# Generated by demand_calculator.py", ""]
    for pop, display in all_pops:
        blocks.append(_gen_demand_template(pop, display, results))
        blocks.append("")
    return "\n".join(blocks)


def generate_wage_pool_template():
    """Generate the wage pool breakdown tooltip template."""
    return """template sul_wage_pool_breakdown_tooltip {
\ttooltipwidget = {
\t\tContextualTooltipType = {
\t\t\tblockoverride "tooltip_title" {
\t\t\t\tContextualTooltipHeader = { blockoverride "title_text" { raw_text = "GDP Wage Pool" } }
\t\t\t}
\t\t\tblockoverride "tooltip_content" {
\t\t\t\tTooltipListBase = {
\t\t\t\t\tTooltipTableHeader = {
\t\t\t\t\t\tblockoverride "tableheader_text" { raw_text = "#T Wage Share ([Location.MakeScope.ScriptValue('sul_wage_share_pct')|0]%)#!" }
\t\t\t\t\t}
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "Base" } text_single = { align = right min_width = 80 raw_text = "50%" } } }
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "× Urbanization" } text_single = { align = right min_width = 80 raw_text = "×[Location.MakeScope.ScriptValue('sul_wage_share_dev_factor')|2] ([Location.MakeScope.ScriptValue('sul_wage_share_dev_pct')|0] dev)" } } }
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "× Employment" } text_single = { align = right min_width = 80 raw_text = "×[Location.MakeScope.ScriptValue('sul_wage_share_emp_factor')|2] ([Location.MakeScope.ScriptValue('sul_wage_share_emp_pct')|0]%)" } } }
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "× Market Access" } text_single = { align = right min_width = 80 raw_text = "×[Multiply_CFixedPoint(Location.MakeScope.ScriptValue('sul_wage_share_market_access'), '(CFixedPoint)100')|0]%" } } }
\t\t\t\t\tTooltipTableHeader = { blockoverride "tableheader_text" { raw_text = "#T Estate Breakdown#!" } }
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "Nobles" } text_single = { align = right min_width = 80 raw_text = "[Location.MakeScope.ScriptValue('sul_wage_bill_nobles_display')|2]@gold!" } } }
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "Clergy" } text_single = { align = right min_width = 80 raw_text = "[Location.MakeScope.ScriptValue('sul_wage_bill_clergy_display')|2]@gold!" } } }
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "Burghers" } text_single = { align = right min_width = 80 raw_text = "[Location.MakeScope.ScriptValue('sul_wage_bill_burghers_display')|2]@gold!" } } }
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "Soldiers" } text_single = { align = right min_width = 80 raw_text = "[Location.MakeScope.ScriptValue('sul_wage_bill_soldiers_display')|2]@gold!" } } }
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "Laborers" } text_single = { align = right min_width = 80 raw_text = "[Location.MakeScope.ScriptValue('sul_wage_bill_laborers_display')|2]@gold!" } } }
\t\t\t\t\tTooltipManualTableField = { blockoverride "field_content" { text_single = { layoutpolicy_horizontal = expanding raw_text = "Peasants" } text_single = { align = right min_width = 80 raw_text = "[Location.MakeScope.ScriptValue('sul_wage_bill_peasants_display')|2]@gold!" } } }
\t\t\t\t}
\t\t\t}
\t\t}
\t}
}"""


WEALTH_BAR_ESTATES = [
    ("nobles", "Nobles", "0.33 0.49 0.80 1", "sul_wealth_slice_nobles"),
    ("clergy", "Clergy", "0.78 0.82 0.90 1", "sul_wealth_slice_clergy"),
    ("burghers", "Burghers", "0.79 0.55 0.10 1", "sul_wealth_slice_burghers"),
    ("peasants", "Commoners", "0.37 0.47 0.26 1", "sul_wealth_slice_commoners"),
    ("crown", "Crown", "0.54 0.36 0.80 1", "sul_wealth_slice_crown"),
]

WEALTH_BAR_DETAIL_ESTATES = [
    ("nobles", "Nobles", "0.33 0.49 0.80 1"),
    ("clergy", "Clergy", "0.78 0.82 0.90 1"),
    ("burghers", "Burghers", "0.79 0.55 0.10 1"),
    ("peasants", "Commoners", "0.37 0.47 0.26 1"),
    ("dhimmi", "Dhimmi", "0.85 0.05 0.35 1"),
    ("cossacks", "Cossacks", "0.76 0.78 0.24 1"),
    ("tribes", "Tribes", "0.47 0.33 0.26 1"),
    ("crown", "Crown", "0.54 0.36 0.80 1"),
]


def generate_wealth_bar_template():
    """Generate the wealth bar tooltip template with GDP section and hoverable breakdowns."""
    # Pie slices
    slices = []
    for key, _label, color, tt in WEALTH_BAR_ESTATES:
        slices.append(f"""\t\t\t\t\t\tpieslice = {{
\t\t\t\t\t\t\ttexture = "gfx/interface/pie_charts/pie_chart_alpha_80.dds"
\t\t\t\t\t\t\tvalue = "[FixedPointToFloat(LocationView.GetLocation.MakeScope.ScriptValue('sul_wealth_share_{key}'))]"
\t\t\t\t\t\t\tcolor = {{ {color} }}
\t\t\t\t\t\t\ttooltip = "{tt}"
\t\t\t\t\t\t}}""")
    pie_content = "\n".join(slices)

    # Estate asset rows
    estate_rows = []
    for key, label, color in WEALTH_BAR_DETAIL_ESTATES:
        vis_key = key if key != "crown" else None
        vis = ""
        if vis_key:
            sv = f"sul_dbg_local_power_{key}"
            vis = f'\n\t\t\t\t\t\tvisible = "[GreaterThan_CFixedPoint(LocationView.GetLocation.MakeScope.ScriptValue(\'{sv}\'), \'(CFixedPoint)0\')]"'
        estate_rows.append(f"""\t\t\t\t\t\tTooltipManualTableField = {{{vis}
\t\t\t\t\t\t\tblockoverride "field_content" {{
\t\t\t\t\t\t\t\ticon = {{ size = {{ 10 20 }} texture = "gfx/interface/component_tiles/bookmark_white.dds" tintcolor = {{ {color} }} }}
\t\t\t\t\t\t\t\ttext_single = {{ default_format = "#subtle_name" raw_text = "{label}" }}
\t\t\t\t\t\t\t\texpand = {{  }}
\t\t\t\t\t\t\t\ttext_single = {{ align = right raw_text = "[LocationView.GetLocation.MakeScope.ScriptValue('sul_map_asset_{key}')|2]@gold! (#green [LocationView.GetLocation.MakeScope.ScriptValue('sul_wealth_delta_{key}')|+=2]@gold!#!)" }}
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t}}""")
    estate_content = "\n".join(estate_rows)

    return f"""template sul_wealth_bar_tooltip {{
\tContextualTooltipType = {{
\t\tblockoverride "title_icon" {{ icon = {{ using = tooltip_title_icon_size texture = "[GetConceptTexture('wealth')]" }} }}
\t\tblockoverride "title_text" {{ raw_text = "#T [sul_location_assets|E]#!" }}
\t\tblockoverride "concept_link" {{ text = "[sul_location_assets|e]" }}
\t\tblockoverride "tooltip_content" {{
\t\t\thbox = {{
\t\t\t\tlayoutpolicy_horizontal = expanding
\t\t\t\tspacing = 10
\t\t\t\twidget = {{
\t\t\t\t\tsize = {{ 100 100 }}
\t\t\t\t\tusing = marker_bg_circle
\t\t\t\t\tpiechart = {{
\t\t\t\t\t\tparentanchor = center
\t\t\t\t\t\tsize = {{ 90% 90% }}
\t\t\t\t\t\tusing = piechart_angles
{pie_content}
\t\t\t\t\t\ticon = {{ parentanchor = center size = {{ 55% 55% }} texture = "[GetConceptTexture('wealth')]" }}
\t\t\t\t\t}}
\t\t\t\t}}
\t\t\t\tvbox = {{
\t\t\t\t\tspacing = 5
\t\t\t\t\tTooltipListBase = {{
\t\t\t\t\t\tTooltipListRowContent = {{
\t\t\t\t\t\t\tTooltipManualTableField = {{
\t\t\t\t\t\t\t\tblockoverride "field_content" {{
\t\t\t\t\t\t\t\t\ttext_single = {{ raw_text = "#T Local GDP#!" }}
\t\t\t\t\t\t\t\t\texpand = {{  }}
\t\t\t\t\t\t\t\t\ttext_single = {{ raw_text = "[LocationView.GetLocation.MakeScope.ScriptValue('sul_local_assets_gdp')|2]@gold!" }}
\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\tTooltipManualTableField = {{
\t\t\t\t\t\t\t\tblockoverride "field_content" {{
\t\t\t\t\t\t\t\t\ttext_single = {{ raw_text = "#T [sul_location_assets]#!" }}
\t\t\t\t\t\t\t\t\texpand = {{  }}
\t\t\t\t\t\t\t\t\ttext_single = {{ raw_text = "[LocationView.GetLocation.MakeScope.ScriptValue('sul_wealth_total')|2] [wealth_icon]" }}
\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\tTooltipManualTableField = {{
\t\t\t\t\t\t\t\tblockoverride "field_content" {{
\t\t\t\t\t\t\t\t\ttext_single = {{ raw_text = "Monthly" }}
\t\t\t\t\t\t\t\t\texpand = {{  }}
\t\t\t\t\t\t\t\t\ttext_single = {{
\t\t\t\t\t\t\t\t\t\traw_text = "#green [LocationView.GetLocation.MakeScope.ScriptValue('sul_wealth_delta_total')|+=2]#! [wealth_icon]"
\t\t\t\t\t\t\t\t\t\ttooltipwidget = {{
\t\t\t\t\t\t\t\t\t\t\tContextualTooltipType = {{
\t\t\t\t\t\t\t\t\t\t\t\tblockoverride "tooltip_title" {{ ContextualTooltipHeader = {{ blockoverride "title_text" {{ raw_text = "Monthly Asset Change" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\tblockoverride "tooltip_content" {{
\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipListBase = {{
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Potential" }} text_single = {{ align = right min_width = 100 raw_text = "[Location.MakeScope.ScriptValue('sul_local_assets_max')|2]@gold!" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Current" }} text_single = {{ align = right min_width = 100 raw_text = "[Location.MakeScope.ScriptValue('sul_local_assets_display')|2]@gold!" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Gap" }} text_single = {{ align = right min_width = 100 raw_text = "[Location.MakeScope.ScriptValue('sul_local_assets_gap')|2]@gold!" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Converge (5%/mo)" }} text_single = {{ align = right min_width = 100 raw_text = "[Location.MakeScope.ScriptValue('sul_local_assets_converge_step')|2]@gold!" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "#bold = Monthly Change#!" }} text_single = {{ align = right min_width = 100 raw_text = "#bold [Location.MakeScope.ScriptValue('sul_local_assets_delta')|+=2]@gold!#!" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\tTooltipManualTableField = {{
\t\t\t\t\t\t\t\tblockoverride "field_content" {{
\t\t\t\t\t\t\t\t\ttext_single = {{ raw_text = "Potential" }}
\t\t\t\t\t\t\t\t\texpand = {{  }}
\t\t\t\t\t\t\t\t\ttext_single = {{
\t\t\t\t\t\t\t\t\t\traw_text = "[LocationView.GetLocation.MakeScope.ScriptValue('sul_wealth_target_total')|2] [wealth_icon]"
\t\t\t\t\t\t\t\t\t\ttooltipwidget = {{
\t\t\t\t\t\t\t\t\t\t\tContextualTooltipType = {{
\t\t\t\t\t\t\t\t\t\t\t\tblockoverride "tooltip_title" {{ ContextualTooltipHeader = {{ blockoverride "title_text" {{ raw_text = "Potential Assets" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\tblockoverride "tooltip_content" {{
\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipListBase = {{
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Local GDP" }} text_single = {{ align = right min_width = 100 raw_text = "[Location.MakeScope.ScriptValue('sul_local_assets_gdp')|2]@gold!" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "× Multiplier" }} text_single = {{ align = right min_width = 100 raw_text = "×5" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "× Prosperity" }} text_single = {{ align = right min_width = 100 raw_text = "×[Location.MakeScope.ScriptValue('sul_local_assets_prosperity_factor')|2] ([Location.MakeScope.ScriptValue('sul_local_assets_prosperity_pct')|0]%)" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "#bold = Potential#!" }} text_single = {{ align = right min_width = 100 raw_text = "#bold [Location.MakeScope.ScriptValue('sul_local_assets_max')|2]@gold!#!" }} }} }}
\t\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t}}
\t\t\t\t\t}}
\t\t\t\t}}
\t\t\t}}
\t\t\tTooltipListBase = {{
\t\t\t\tTooltipTableHeader = {{ blockoverride "tableheader_text" {{ raw_text = "#T Estate Assets#!" }} }}
\t\t\t\tTooltipListRowContent = {{
{estate_content}
\t\t\t\t}}
\t\t\t}}
\t\t}}
\t}}
}}"""


def generate_gui_tooltip(results):
    """Generate the Pop Demand Budget tooltip for the GUI file.

    Columns: Pop Type | Wages | Returns | WPP
    Wages and Returns get hover breakdowns. WPP gets the per-tier demand breakdown.
    Upper estates (nobles/clergy/burghers) show capital returns.
    Commoners (soldiers/laborers/peasants) show flat wealth supplement.
    """
    pop_display = {
        "nobles": "Nobles", "clergy": "Clergy", "burghers": "Burghers",
        "soldiers": "Soldiers", "laborers": "Laborers", "peasants": "Peasants",
    }
    # Script value names for each column
    pop_wage_sv = {
        "nobles": "sul_noble_wage_rate", "clergy": "sul_clergy_wage_rate",
        "burghers": "sul_burgher_wage_rate", "soldiers": "sul_soldier_wage_rate",
        "laborers": "sul_laborer_wage_rate", "peasants": "sul_peasant_wage_rate",
    }
    pop_return_sv = {
        "nobles": "sul_noble_capital_return", "clergy": "sul_clergy_capital_return",
        "burghers": "sul_burgher_capital_return",
        "soldiers": "sul_commoner_flat_wealth", "laborers": "sul_commoner_flat_wealth",
        "peasants": "sul_commoner_flat_wealth",
    }
    pop_wpp_sv = {
        "nobles": "sul_noble_demand_per_pop", "clergy": "sul_clergy_demand_per_pop",
        "burghers": "sul_burgher_demand_per_pop", "soldiers": "sul_soldier_demand_per_pop",
        "laborers": "sul_laborer_demand_per_pop", "peasants": "sul_peasant_demand_per_pop",
    }
    # Wage breakdown script values (base, global mod, local mod)
    pop_base_wage_sv = {
        "nobles": "sul_noble_base_wage", "clergy": "sul_clergy_base_wage",
        "burghers": "sul_burgher_base_wage", "soldiers": "sul_soldier_base_wage",
        "laborers": "sul_laborer_base_wage", "peasants": "sul_peasant_base_wage",
    }
    pop_global_mod_sv = {
        "nobles": "sul_noble_global_wage_modifier", "clergy": "sul_clergy_global_wage_modifier",
        "burghers": "sul_burgher_global_wage_modifier", "soldiers": "sul_soldier_global_wage_modifier",
        "laborers": "sul_laborer_global_wage_modifier", "peasants": "sul_peasant_global_wage_modifier",
    }
    pop_local_mod_sv = {
        "nobles": "sul_noble_local_wage_modifier", "clergy": "sul_clergy_local_wage_modifier",
        "burghers": "sul_burgher_local_wage_modifier", "soldiers": "sul_soldier_local_wage_modifier",
        "laborers": "sul_laborer_local_wage_modifier", "peasants": "sul_peasant_local_wage_modifier",
    }
    pop_global_mod_key = {
        "nobles": "sul_global_nobles_wages_modifier", "clergy": "sul_global_clergy_wages_modifier",
        "burghers": "sul_global_burghers_wages_modifier", "soldiers": "sul_global_soldiers_wages_modifier",
        "laborers": "sul_global_laborers_wages_modifier", "peasants": "sul_global_peasants_wages_modifier",
    }
    # Upper vs commoner distinction
    upper_pops = {"nobles", "clergy", "burghers"}

    # Enrichment script value map: pop type → enrichment SV name
    pop_enrichment_sv = {
        "nobles": "sul_noble_enrichment_per_pop",
        "clergy": "sul_clergy_enrichment_per_pop",
        "burghers": "sul_burgher_enrichment_per_pop",
        "soldiers": "sul_commoner_enrichment_per_pop",
        "laborers": "sul_commoner_enrichment_per_pop",
        "peasants": "sul_commoner_enrichment_per_pop",
    }
    pop_enrichment_rate_sv = {
        "nobles": "sul_noble_enrichment_rate_display",
        "clergy": "sul_clergy_enrichment_rate_display",
        "burghers": "sul_burgher_enrichment_rate_display",
        "soldiers": "sul_commoner_enrichment_rate_display",
        "laborers": "sul_commoner_enrichment_rate_display",
        "peasants": "sul_commoner_enrichment_rate_display",
    }

    lines = []
    lines.append('\t### WPDO: POP DEMAND BUDGET')
    lines.append('')
    lines.append("\tTooltipListBase = {")
    lines.append("\t\tvisible = \"[Location.MakeScope.GetVariable('sul_local_gdp').IsSet]\"")
    lines.append("\t\tmax_update_rate = 30")
    lines.append("")
    lines.append('\t\tTooltipTableHeader = { blockoverride "tableheader_text" { raw_text = "#T Pop Demand Per Pop#!" } }')
    lines.append("")

    # Enrichment section at top
    lines.append("\t\tTooltipListRowContent = {")
    lines.append('\t\t\tTooltipManualTableField = {')
    lines.append('\t\t\t\tblockoverride "field_content" {')
    lines.append('\t\t\t\t\ttext_multi = { layoutpolicy_horizontal = expanding max_width = 420 raw_text = "#low Demand per pop represents the purchasing power of every 1,000 people. Wages are drawn from a shared pool distributed by political power. A fraction of income is saved as #bold Enrichment#! — wealth flowing to estate treasuries.#!" }')
    lines.append('\t\t\t\t}')
    lines.append('\t\t\t}')
    lines.append("\t\t}")
    lines.append("")

    lines.append("\t\tTooltipListRowContent = {")

    # Header row
    lines.append("\t\t\tTooltipManualTableField = {")
    lines.append('\t\t\t\tblockoverride "field_content" {')
    lines.append('\t\t\t\t\ttext_single = { layoutpolicy_horizontal = expanding margin_left = 5 raw_text = "#T Pop Type#!" }')
    lines.append('\t\t\t\t\ttext_single = { min_width = 70 max_width = 70 align = right raw_text = "#T Wages#!" }')
    lines.append('\t\t\t\t\ttext_single = { min_width = 70 max_width = 70 align = right raw_text = "#T Returns#!" }')
    lines.append('\t\t\t\t\ttext_single = { min_width = 70 max_width = 70 align = right raw_text = "#T Savings#!" }')
    lines.append('\t\t\t\t\ttext_single = { min_width = 70 max_width = 70 align = right raw_text = "#T WPP#!" }')
    lines.append('\t\t\t\t}')
    lines.append('\t\t\t}')

    for pop in GUI_POP_TYPES:
        display = pop_display[pop]
        wage_sv = pop_wage_sv[pop]
        return_sv = pop_return_sv[pop]
        wpp_sv = pop_wpp_sv[pop]
        base_sv = pop_base_wage_sv[pop]
        gmod_sv = pop_global_mod_sv[pop]
        lmod_sv = pop_local_mod_sv[pop]
        gmod_key = pop_global_mod_key[pop]
        is_upper = pop in upper_pops
        template_name = f"sul_{pop}_demand_breakdown_tooltip"

        lines.append(f"")
        lines.append(f"\t\t\t# {display}")
        lines.append(f"\t\t\tTooltipManualTableField = {{")
        lines.append(f"\t\t\t\tvisible = \"[GreaterThan_CFixedPoint(Location.MakeScope.ScriptValue('{wpp_sv}'), '(CFixedPoint)0.0001')]\"")
        lines.append(f'\t\t\t\tblockoverride "field_content" {{')
        lines.append(f"\t\t\t\t\ticon = {{ size = {{ 20 20 }} texture = \"[GetGraphicalCultureTextureForPopType(GetPopTypeByName('{pop}'))]\" }}")
        lines.append(f'\t\t\t\t\ttext_single = {{ layoutpolicy_horizontal = expanding margin_left = 5 raw_text = "{display}" }}')

        # Wages column: shows share of location wage pool captured by this estate
        pop_power_sv_w = {"nobles": "sul_noble_power_share", "clergy": "sul_clergy_power_share", "burghers": "sul_burgher_power_share"}.get(pop, "sul_commoner_power_share")
        lines.append(f"\t\t\t\t\ttext_single = {{")
        lines.append(f"\t\t\t\t\t\tmin_width = 70 max_width = 70 align = right")
        lines.append(f"\t\t\t\t\t\traw_text = \"[Location.MakeScope.ScriptValue('{wage_sv}')|2]@gold!\"")
        lines.append(f"\t\t\t\t\t\ttooltipwidget = {{")
        lines.append(f"\t\t\t\t\t\t\tContextualTooltipType = {{")
        lines.append(f'\t\t\t\t\t\t\t\tblockoverride "tooltip_title" {{ ContextualTooltipHeader = {{ blockoverride "title_text" {{ raw_text = "{display} Wages" }} }} }}')
        lines.append(f'\t\t\t\t\t\t\t\tblockoverride "tooltip_content" {{')
        lines.append(f"\t\t\t\t\t\t\t\t\tTooltipListBase = {{")
        lines.append(f'\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Location Wage Pool" }} text_single = {{ align = right min_width = 100 raw_text = "[Location.MakeScope.ScriptValue(\'sul_wage_pool_total\')|2]@gold!" }} }} }}')
        lines.append(f'\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Estate Power" }} text_single = {{ align = right min_width = 100 raw_text = "[Multiply_CFixedPoint(Location.MakeScope.ScriptValue(\'{pop_power_sv_w}\'), \'(CFixedPoint)100\')|0]%" }} }} }}')
        if not is_upper:
            bill_pct_sv = f"sul_{pop}_bill_pct"
            lines.append(f'\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Wage Bill Share" }} text_single = {{ align = right min_width = 100 raw_text = "[Multiply_CFixedPoint(Location.MakeScope.ScriptValue(\'{bill_pct_sv}\'), \'(CFixedPoint)100\')|0]%" }} }} }}')
        lines.append(f"\t\t\t\t\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t\t}}")

        # Returns column: capital returns for upper estates, flat wealth for commoners
        pop_power_sv_r = {"nobles": "sul_noble_power_share", "clergy": "sul_clergy_power_share", "burghers": "sul_burgher_power_share"}.get(pop)
        lines.append(f"\t\t\t\t\ttext_single = {{")
        lines.append(f"\t\t\t\t\t\tmin_width = 70 max_width = 70 align = right")
        lines.append(f"\t\t\t\t\t\traw_text = \"[Location.MakeScope.ScriptValue('{return_sv}')|2]@gold!\"")
        if is_upper:
            lines.append(f"\t\t\t\t\t\ttooltipwidget = {{")
            lines.append(f"\t\t\t\t\t\t\tContextualTooltipType = {{")
            lines.append(f'\t\t\t\t\t\t\t\tblockoverride "tooltip_title" {{ ContextualTooltipHeader = {{ blockoverride "title_text" {{ raw_text = "{display} Capital Returns" }} }} }}')
            lines.append(f'\t\t\t\t\t\t\t\tblockoverride "tooltip_content" {{')
            lines.append(f"\t\t\t\t\t\t\t\t\tTooltipListBase = {{")
            lines.append(f'\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Estate Return Rate" }} text_single = {{ align = right min_width = 100 raw_text = "[Location.MakeScope.ScriptValue(\'{return_sv}\')|2]@gold!" }} }} }}')
            lines.append(f'\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Asset Share" }} text_single = {{ align = right min_width = 100 raw_text = "[Location.MakeScope.ScriptValue(\'sul_asset_share_pct\')|0]%" }} }} }}')
            lines.append(f'\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Political Power" }} text_single = {{ align = right min_width = 100 raw_text = "[Multiply_CFixedPoint(Location.MakeScope.ScriptValue(\'{pop_power_sv_r}\'), \'(CFixedPoint)100\')|0]%" }} }} }}')
            lines.append(f"\t\t\t\t\t\t\t\t\t}}")
            lines.append(f"\t\t\t\t\t\t\t\t}}")
            lines.append(f"\t\t\t\t\t\t\t}}")
            lines.append(f"\t\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t\t}}")

        # Savings column: enrichment flowing to estate treasury
        enrichment_sv = pop_enrichment_sv[pop]
        enr_rate_sv = pop_enrichment_rate_sv[pop]
        lines.append(f"\t\t\t\t\ttext_single = {{")
        lines.append(f"\t\t\t\t\t\tmin_width = 70 max_width = 70 align = right")
        lines.append(f"\t\t\t\t\t\traw_text = \"[Location.MakeScope.ScriptValue('{enrichment_sv}')|2]@gold!\"")
        lines.append(f"\t\t\t\t\t\ttooltipwidget = {{")
        lines.append(f"\t\t\t\t\t\t\tContextualTooltipType = {{")
        lines.append(f'\t\t\t\t\t\t\t\tblockoverride "tooltip_title" {{ ContextualTooltipHeader = {{ blockoverride "title_text" {{ raw_text = "{display} Enrichment" }} }} }}')
        lines.append(f'\t\t\t\t\t\t\t\tblockoverride "tooltip_content" {{')
        lines.append(f"\t\t\t\t\t\t\t\t\tTooltipListBase = {{")
        lines.append(f'\t\t\t\t\t\t\t\t\t\tTooltipManualTableField = {{ blockoverride "field_content" {{ text_single = {{ layoutpolicy_horizontal = expanding raw_text = "Enrichment Rate" }} text_single = {{ align = right min_width = 100 raw_text = "[Multiply_CFixedPoint(Location.MakeScope.ScriptValue(\'{enr_rate_sv}\'), \'(CFixedPoint)100\')|0]%" }} }} }}')
        lines.append(f"\t\t\t\t\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t\t\t}}")
        lines.append(f"\t\t\t\t\t}}")

        # WPP column with demand breakdown tooltip (pluggable template)
        lines.append(f"\t\t\t\t\ttext_single = {{")
        lines.append(f"\t\t\t\t\t\tmin_width = 70 max_width = 70 align = right")
        lines.append(f"\t\t\t\t\t\traw_text = \"[Location.MakeScope.ScriptValue('{wpp_sv}')|2]@gold!\"")
        lines.append(f"\t\t\t\t\t\tusing = {template_name}")
        lines.append(f"\t\t\t\t\t}}")

        lines.append(f"\t\t\t\t}}")
        lines.append(f"\t\t\t}}")

    lines.append("\t\t}")
    lines.append("\t}")

    return "\n".join(lines)


def generate_demand_init(results):
    """Generate sul_demand_init.txt scripted effect.

    Creates 6 variable maps on the location (one per tier), each mapping
    goods to their demand_add constant. Called once during init.
    GUI iterates these maps to get all goods per tier.
    """
    lines = [
        "# Generated by demand_calculator.py --cache",
        "# Static demand_add maps for GUI tooltip iteration.",
        "# 6 maps (one per tier), each keyed by goods, value = demand_add.",
        "# Called once per location during sul_initialize_all.",
        "",
        "sul_init_demand_maps = {",
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
            lines.append(f"\tadd_to_global_variable_map = {{ name = sul_da_{cat} key = goods:{r['name']} value = {da_str} }}")
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
                            "sul_demand_init.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write(content)
    print(f"Wrote {out_path}")


def write_gui(results):
    """Write demand breakdown templates to aaa_sul_demand_breakdown_tooltips.gui.

    This file contains ONLY the per-pop-type demand breakdown templates
    (WPP summation + per-tier goods lists). Referenced via `using =` from
    the main tooltip file.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mod_dir = os.path.dirname(script_dir)
    gui_path = os.path.join(mod_dir, "in_game", "gui", "shared",
                            "aaa_sul_demand_breakdown_tooltips.gui")
    os.makedirs(os.path.dirname(gui_path), exist_ok=True)

    standalone = generate_standalone_templates(results)

    with open(gui_path, "w", encoding="utf-8-sig") as f:
        f.write(standalone)
        f.write("\n")

    print(f"Wrote demand breakdown templates to {gui_path}")


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
                        help="Write PDX output to sul_goods_overrides.txt")
    parser.add_argument("--gui", action="store_true",
                        help="Write generated GUI tooltip to aaa_sul_location_tooltips.gui")
    parser.add_argument("--cache", action="store_true",
                        help="Write demand init scripted effect (sul_demand_init.txt)")
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
