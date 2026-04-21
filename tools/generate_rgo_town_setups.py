#!/usr/bin/env python3
"""
Generate SUL setup pre-seed: RGO buildings only.

Spec/guild buildings are placed by the runtime distributor
(sul_distribute_specialization_buildings) when the spec is assigned on
game start; this generator just seeds the RGO that backs each location's
raw_material and promotes enough peasants to staff laborer-run RGOs.

Reads:
  <vanilla>/in_game/map_data/location_templates.txt     (raw_material)
  <vanilla>/main_menu/setup/start/06_pops.txt           (pop distributions)
  <vanilla>/main_menu/setup/start/10_countries.txt      (loc -> owner + starting_technology_level)
  <mod>/in_game/common/scripted_effects/sul_init_effects.txt (sul_rgo_map)
  <mod>/in_game/common/building_types/sul_rgo_buildings.txt  (RGO pop_types)

Writes:
  <mod>/main_menu/setup/start/50_sul_setup.txt
        building_manager block: one entry per owned location with a mapped
        raw_material, placing sul_rgo_<good> at level 1 + floor(pop/50).
        Iron RGOs are skipped for countries that don't have iron_working
        researched at game start (tribal/stl<1 countries).
  <mod>/main_menu/setup/start/06_pops.txt
        Full override of vanilla 06_pops with peasant->RGO.pop_type shift.
        Only cross-type shift the generator performs — other spec building
        staffing emerges via the runtime distributor and engine promotion.
"""

import argparse
import re
import sys
from collections import defaultdict
from math import floor
from pathlib import Path


# Placement formulas
RGO_POP_PER_LEVEL = 50          # 1 RGO level per 50k
VILLAGE_POP_PER_LEVEL = 100     # 1 village level per 100k eligible pop
VILLAGE_RANK_BONUS = {"rural_settlement": 0, "town": 1, "city": 2}
LEVEL_CAP = 10

EXCLUDED_POP_TYPES = {"slaves", "tribesmen"}
SHIFT_DONOR = "peasants"

# iron_working unlocks both iron and coal extraction (STL >= 1).
# Tags without it don't receive sul_rgo_iron or sul_rgo_coal placements.
IRON_WORKING_REQUIRED_STL = 1
TECH_GATED_RGOS = {"sul_rgo_iron", "sul_rgo_coal"}

# Village selected from predicted spec (market center → commercial).
VILLAGE_BY_SPEC = {
    "farming":    "farming_village",
    "gathering":  "fishing_village",
    "mining":     "sul_mining_village",
    "woodland":   "forest_village",
    "commercial": "market_village",
}


# ─────────────────────────────────────────────────────────────────────────────
# Regexes
# ─────────────────────────────────────────────────────────────────────────────

LOCATION_ENTRY_RE = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*\{(.*?)\}\s*$", re.IGNORECASE)
RAW_MATERIAL_RE = re.compile(r"\braw_material\s*=\s*([a-z_][a-z0-9_]*)")
RGO_MAP_ENTRY_RE = re.compile(
    r"name\s*=\s*sul_rgo_map\s*key\s*=\s*goods:([a-z_][a-z0-9_]*)\s*value\s*=\s*building_type:(sul_rgo_[a-z_][a-z0-9_]*)",
    re.DOTALL,
)
GOODS_SPEC_ENTRY_RE = re.compile(
    r"name\s*=\s*sul_goods_to_spec_type\s*key\s*=\s*goods:([a-z_][a-z0-9_]*)\s*value\s*=\s*@(sul_[a-z_]+_type)",
    re.DOTALL,
)
SPEC_TYPE_MACRO = {
    "@sul_mining_type": "mining",
    "@sul_farming_type": "farming",
    "@sul_gathering_type": "gathering",
    "@sul_woodland_type": "woodland",
    "@sul_commercial_type": "commercial",
    "sul_mining_type": "mining",
    "sul_farming_type": "farming",
    "sul_gathering_type": "gathering",
    "sul_woodland_type": "woodland",
    "sul_commercial_type": "commercial",
}

DEFINE_POP_BLOCK_RE = re.compile(r"define_pop\s*=\s*\{[^}]*\}", re.DOTALL)
POP_FIELD_RE = re.compile(r"\b(type|size|culture|religion)\s*=\s*([A-Za-z_][A-Za-z0-9_]*|[0-9.]+)")
RGO_BUILDING_RE = re.compile(
    r"^(sul_rgo_[a-z_][a-z0-9_]*)\s*=\s*\{(.*?)^\}", re.DOTALL | re.MULTILINE
)
POP_TYPE_RE = re.compile(r"\bpop_type\s*=\s*([a-z_]+)")
MAX_LEVELS_RE = re.compile(r"\bmax_levels\s*=\s*(\S+)")
EMPLOYMENT_SIZE_RE = re.compile(r"\bemployment_size\s*=\s*(\S+)")
RANK_FLAG_RE_TMPL = r"\b{}\s*=\s*(yes|no)"
RANK_RE = re.compile(r"\brank\s*=\s*(rural_settlement|town|city)")
GOODS_SPEC_ENTRY_RE = re.compile(
    r"name\s*=\s*sul_goods_to_spec_type\s*key\s*=\s*goods:([a-z_][a-z0-9_]*)\s*value\s*=\s*@(sul_[a-z_]+_type)",
    re.DOTALL,
)
SPEC_TYPE_MACRO = {
    "@sul_mining_type": "mining",     "sul_mining_type": "mining",
    "@sul_farming_type": "farming",   "sul_farming_type": "farming",
    "@sul_gathering_type": "gathering", "sul_gathering_type": "gathering",
    "@sul_woodland_type": "woodland", "sul_woodland_type": "woodland",
    "@sul_commercial_type": "commercial", "sul_commercial_type": "commercial",
}
MARKET_ADD_RE = re.compile(r"\badd_market\s*=\s*([a-z_][a-z0-9_]*)")
# Top-level building definition: "name = { ... }" or "REPLACE:name = { ... }" or "INJECT:name = { ... }"
TOP_BUILDING_RE = re.compile(
    r"^(?:(REPLACE|TRY_REPLACE|REPLACE_OR_CREATE|INJECT|TRY_INJECT|INJECT_OR_CREATE):)?([a-z_][a-z0-9_]*)\s*=\s*\{",
    re.MULTILINE | re.IGNORECASE,
)

OWN_BLOCK_RE = re.compile(r"\b(own_[a-z_]+)\s*=\s*\{([^{}]*)\}", re.DOTALL)
LOC_TOKEN_RE = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)

STL_RE = re.compile(r"\bstarting_technology_level\s*=\s*(\d+)")
INCLUDE_RE = re.compile(r'\binclude\s*=\s*"?([a-z_][a-z0-9_]*)"?')


# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────

def parse_raw_materials(path: Path) -> dict:
    result = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        m = LOCATION_ENTRY_RE.match(raw_line)
        if not m:
            continue
        loc, body = m.group(1), m.group(2)
        rm = RAW_MATERIAL_RE.search(body)
        if rm:
            result[loc] = rm.group(1)
    return result


def parse_harbor_suitability(path: Path) -> dict:
    """location_templates.txt: loc -> natural_harbor_suitability (0.0-1.0)."""
    result = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        m = LOCATION_ENTRY_RE.match(raw_line)
        if not m:
            continue
        loc, body = m.group(1), m.group(2)
        h = HARBOR_RE.search(body)
        if h:
            try:
                result[loc] = float(h.group(1))
            except ValueError:
                pass
    return result


def parse_pops_structured(path: Path):
    """Return (pre_text, locations_list, post_text). Each location entry:
      {leading_ws, name, header_suffix, segments, pops}
    where pops is list of {type, size, culture, religion, original_text, new?}
    """
    text = path.read_text(encoding="utf-8-sig")
    outer = re.search(r"locations\s*=\s*\{", text)
    if not outer:
        return text, [], ""
    pre_text = text[: outer.end()]
    i = outer.end()
    n = len(text)
    locations = []
    depth = 1
    while i < n and depth > 0:
        c = text[i]
        if c == "{":
            depth += 1
            i += 1
        elif c == "}":
            depth -= 1
            i += 1
            if depth == 0:
                break
        elif depth == 1:
            m = re.match(r"(\s*)([a-z_][a-z0-9_]*)\s*=\s*\{", text[i:], re.IGNORECASE)
            if m:
                leading_ws = m.group(1)
                name = m.group(2)
                header_end = i + m.end()
                inner_depth = 1
                j = header_end
                while j < n and inner_depth > 0:
                    if text[j] == "{":
                        inner_depth += 1
                    elif text[j] == "}":
                        inner_depth -= 1
                    j += 1
                body = text[header_end : j - 1]
                pops = []
                last = 0
                segments = []
                for pm in DEFINE_POP_BLOCK_RE.finditer(body):
                    segments.append(("text", body[last : pm.start()]))
                    fields = {k: v for k, v in POP_FIELD_RE.findall(pm.group(0))}
                    pops.append({
                        "type": fields.get("type", ""),
                        "size": float(fields.get("size", "0")),
                        "culture": fields.get("culture", ""),
                        "religion": fields.get("religion", ""),
                    })
                    segments.append(("pop", len(pops) - 1))
                    last = pm.end()
                segments.append(("text", body[last:]))
                locations.append({
                    "leading_ws": leading_ws,
                    "name": name,
                    "header_suffix": text[i + len(leading_ws) + len(name) : header_end],
                    "segments": segments,
                    "pops": pops,
                })
                i = j
            else:
                i += 1
        else:
            i += 1
    post_text = text[i:]
    return pre_text, locations, post_text


def parse_rgo_map(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    compact = re.sub(r"\s+", " ", text)
    return {m.group(1): m.group(2) for m in RGO_MAP_ENTRY_RE.finditer(compact)}


def parse_goods_to_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    compact = re.sub(r"\s+", " ", text)
    return {
        m.group(1): SPEC_TYPE_MACRO.get(m.group(2), "?")
        for m in GOODS_SPEC_ENTRY_RE.finditer(compact)
    }


def parse_ranks(path: Path) -> dict:
    """07_cities_and_buildings.txt: loc -> rank. Locs absent default rural_settlement."""
    text = re.sub(r"#[^\n]*", "", path.read_text(encoding="utf-8-sig"))
    result = {}
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*=\s*\{([^{}]*)\}", text):
        rm = RANK_RE.search(m.group(2))
        if rm:
            result[m.group(1)] = rm.group(1)
    return result


def parse_market_centers(path: Path) -> set:
    text = re.sub(r"#[^\n]*", "", path.read_text(encoding="utf-8-sig"))
    return {m.group(1) for m in MARKET_ADD_RE.finditer(text)}


def parse_goods_to_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    compact = re.sub(r"\s+", " ", text)
    return {
        m.group(1): SPEC_TYPE_MACRO.get(m.group(2), "?")
        for m in GOODS_SPEC_ENTRY_RE.finditer(compact)
    }


def parse_rgo_building_pop_types(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    result = {}
    for m in RGO_BUILDING_RE.finditer(text):
        name, body = m.group(1), m.group(2)
        pt = POP_TYPE_RE.search(body)
        if pt:
            result[name] = pt.group(1)
    return result


def parse_ranks(path: Path) -> dict:
    """07_cities_and_buildings.txt: loc -> rank. Defaults to rural_settlement if absent."""
    text = path.read_text(encoding="utf-8-sig")
    # Strip comments
    text = re.sub(r"#[^\n]*", "", text)
    result = {}
    # Find each "loc = { ... }" block body and look for rank =
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\s*=\s*\{([^{}]*)\}", text):
        body = m.group(2)
        rm = RANK_RE.search(body)
        if rm:
            result[m.group(1)] = rm.group(1)
    return result


MARKET_ADD_RE = re.compile(r"\badd_market\s*=\s*([a-z_][a-z0-9_]*)")


def parse_market_centers(path: Path) -> set:
    """03_markets.txt: set of locations with 'add_market = <loc>'."""
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(r"#[^\n]*", "", text)
    return {m.group(1) for m in MARKET_ADD_RE.finditer(text)}


def _load_templates(vanilla: Path) -> dict:
    """Load setup templates, returning {name: text_content}."""
    tpl_dir = vanilla / "main_menu/setup/templates"
    templates = {}
    if tpl_dir.is_dir():
        for f in tpl_dir.glob("*.txt"):
            templates[f.stem] = f.read_text(encoding="utf-8-sig")
    return templates


def _resolve_stl(body: str, templates: dict, depth: int = 0) -> int:
    """Find starting_technology_level in body or its includes (recursive)."""
    if depth > 10:
        return 0
    m = STL_RE.search(body)
    if m:
        return int(m.group(1))
    for inc in INCLUDE_RE.findall(body):
        tpl = templates.get(inc, "")
        if tpl:
            result = _resolve_stl(tpl, templates, depth + 1)
            if result > 0:
                return result
    return 0


def parse_countries(path: Path, vanilla: Path = None):
    """10_countries.txt: returns (loc_to_tag, tag_to_info).
    tag_to_info[tag] = {'stl': int}. Only info the RGO-only generator needs."""
    templates = _load_templates(vanilla) if vanilla else {}
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(r"#[^\n]*", "", text)
    outer = re.search(r"\bcountries\s*=\s*\{\s*countries\s*=\s*\{", text)
    if not outer:
        return {}, {}
    i = outer.end()
    n = len(text)
    depth = 2
    loc_to_tag = {}
    tag_info = {}
    while i < n and depth > 0:
        c = text[i]
        if c == "{":
            depth += 1
            i += 1
        elif c == "}":
            depth -= 1
            i += 1
        elif depth == 2:
            m = re.match(r"\s*([A-Z][A-Z0-9_]{1,5})\s*=\s*\{", text[i:])
            if m:
                tag = m.group(1)
                header_end = i + m.end()
                j = header_end
                inner_depth = 1
                while j < n and inner_depth > 0:
                    if text[j] == "{":
                        inner_depth += 1
                    elif text[j] == "}":
                        inner_depth -= 1
                    j += 1
                country_body = text[header_end : j - 1]
                for om in OWN_BLOCK_RE.finditer(country_body):
                    for tok in LOC_TOKEN_RE.findall(om.group(2)):
                        loc_to_tag[tok] = tag
                tag_info[tag] = {
                    "stl": _resolve_stl(country_body, templates),
                }
                i = j
            else:
                i += 1
        else:
            i += 1
    return loc_to_tag, tag_info


def parse_building_metadata(vanilla_dir: Path, mod_dir: Path) -> dict:
    """Merged vanilla+mod metadata: name -> {pop_type, rural, town, city, employment_size, max_levels}.
    Mod REPLACE: fully replaces vanilla. Mod INJECT: adds/overrides fields. Mod
    sul_* is new. Fields not found default sensibly."""
    buildings = {}

    def scan_dir(d: Path, vanilla=False):
        for f in sorted(d.glob("*.txt")):
            if f.name.startswith("sul_epbm_generated"):
                continue
            try:
                text = f.read_text(encoding="utf-8-sig")
            except Exception:
                continue
            for m in TOP_BUILDING_RE.finditer(text):
                kind = (m.group(1) or "").upper()
                name = m.group(2)
                start = m.end()
                depth = 1
                j = start
                while j < len(text) and depth > 0:
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                    j += 1
                body = text[start : j - 1]
                fields = extract_building_fields(body)
                if kind in ("", "REPLACE", "TRY_REPLACE", "REPLACE_OR_CREATE") or vanilla:
                    buildings[name] = fields
                elif kind in ("INJECT", "TRY_INJECT", "INJECT_OR_CREATE"):
                    existing = buildings.get(name, default_fields())
                    merged = {**existing}
                    for k, v in fields.items():
                        if v is not None:
                            merged[k] = v
                    buildings[name] = merged

    scan_dir(vanilla_dir, vanilla=True)
    scan_dir(mod_dir, vanilla=False)
    return buildings


def default_fields() -> dict:
    return {
        "pop_type": None,
        "rural_settlement": None,
        "town": None,
        "city": None,
        "employment_size": None,
        "max_levels": None,
    }


def extract_building_fields(body: str) -> dict:
    fields = default_fields()
    pt = POP_TYPE_RE.search(body)
    if pt:
        fields["pop_type"] = pt.group(1)
    for flag in ("rural_settlement", "town", "city"):
        rm = re.search(RANK_FLAG_RE_TMPL.format(flag), body)
        if rm:
            fields[flag] = (rm.group(1) == "yes")
    em = EMPLOYMENT_SIZE_RE.search(body)
    if em:
        fields["employment_size"] = em.group(1)
    ml = MAX_LEVELS_RE.search(body)
    if ml:
        fields["max_levels"] = ml.group(1)
    return fields


# Employment sizes — named script values we resolve by best-known defaults.
# The actual values at runtime may differ; these drive pop-shift heuristics only.
EMPLOYMENT_SIZE_VALUES = {
    "employment_size_RGO": 1,
    "rural_peasant_produce_employment": 1,
    "rural_peasant_employment": 1,
    "town_burgher_employment": 1,
    "town_laborer_employment": 1,
    "city_burgher_employment": 1,
    "city_laborer_employment": 1,
    "basic_employment": 1,
    "standard_employment": 1,
}


def resolve_employment_size(token) -> float:
    if token is None:
        return 1.0
    try:
        return float(token)
    except (TypeError, ValueError):
        return float(EMPLOYMENT_SIZE_VALUES.get(token, 1))


def resolve_max_levels(token) -> int:
    if token is None:
        return LEVEL_CAP
    try:
        return int(token)
    except (TypeError, ValueError):
        # Named script-value; assume it resolves at/above LEVEL_CAP — clamp later
        return LEVEL_CAP


# ─────────────────────────────────────────────────────────────────────────────
# Placement math
# ─────────────────────────────────────────────────────────────────────────────

def rank_allows(building_meta: dict, rank: str) -> bool:
    flag = {"rural_settlement": "rural_settlement", "town": "town", "city": "city"}[rank]
    val = building_meta.get(flag)
    # Missing flag = default allow (vanilla convention)
    return val is not False


def distribute_levels_even(budget: int, pool: list) -> dict:
    """Spread `budget` levels across `pool` buildings evenly, clamped to
    LEVEL_CAP per building. Deterministic order (pool order)."""
    if not pool or budget <= 0:
        return {}
    result = {b: 0 for b in pool}
    remaining = budget
    # First pass: base per building
    base = remaining // len(pool)
    base = min(base, LEVEL_CAP)
    for b in pool:
        result[b] = base
        remaining -= base
    # Remainder: add 1 to first N buildings (respecting cap)
    i = 0
    while remaining > 0 and i < len(pool) * LEVEL_CAP:
        idx = i % len(pool)
        if result[pool[idx]] < LEVEL_CAP:
            result[pool[idx]] += 1
            remaining -= 1
        i += 1
    return {b: lvl for b, lvl in result.items() if lvl > 0}


def compute_eligible_pop(pops: list) -> float:
    return sum(
        p["size"] for p in pops
        if p.get("type") not in EXCLUDED_POP_TYPES
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pop shift
# ─────────────────────────────────────────────────────────────────────────────

def shift_peasants_to_target(pops: list, target_type: str, amount: float):
    """Subtract amount from largest peasant entry, create/merge into
    target-type entry with matching culture/religion. If amount > peasants
    available, take as much as possible."""
    if amount <= 0 or target_type == SHIFT_DONOR:
        return
    peasants = [p for p in pops if p["type"] == SHIFT_DONOR]
    if not peasants:
        return
    peasants.sort(key=lambda p: p["size"], reverse=True)
    remaining = amount
    for p in peasants:
        if remaining <= 0:
            break
        take = min(remaining, p["size"])
        if take <= 0:
            continue
        p["size"] -= take
        remaining -= take
        target = next(
            (q for q in pops
             if q["type"] == target_type
             and q["culture"] == p["culture"]
             and q["religion"] == p["religion"]),
            None,
        )
        if target is not None:
            target["size"] += take
        else:
            pops.append({
                "type": target_type,
                "size": take,
                "culture": p["culture"],
                "religion": p["religion"],
                "new": True,
            })


# ─────────────────────────────────────────────────────────────────────────────
# Output emitters
# ─────────────────────────────────────────────────────────────────────────────

def emit_setup_file(out_path: Path, bm_entries: list, _unused=None):
    """building_manager block — one entry per (loc, RGO building, level)."""
    lines = [
        "# Generated by tools/generate_rgo_town_setups.py — do not hand-edit.",
        "# Pre-seeds the RGO building backing each location's raw_material.",
        "# Level scales with starting pop. Iron RGOs are omitted for owners",
        "# without iron_working researched. Spec + guild buildings are",
        "# placed at runtime by sul_distribute_specialization_buildings.",
        "",
        "building_manager = {",
    ]
    for building, loc, tag, level in bm_entries:
        lines.append(f"\t{building} = {{ location = {loc} tag = {tag} level = {level} }}")
    lines.append("}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_pop(pop: dict) -> str:
    size = pop["size"]
    size_str = f"{size:g}" if size != int(size) else f"{int(size)}"
    return (
        f"define_pop = {{\ttype = {pop['type']}\tsize = {size_str}"
        f"\tculture = {pop['culture']}\treligion = {pop['religion']} }}"
    )


def write_pops_override(out_path: Path, pre_text: str, locations: list, post_text: str):
    parts = [pre_text]
    for loc in locations:
        parts.append(loc["leading_ws"])
        parts.append(loc["name"])
        parts.append(loc["header_suffix"])
        for kind, payload in loc["segments"]:
            if kind == "text":
                parts.append(payload)
            else:
                pop = loc["pops"][payload]
                if pop.get("new") or pop["size"] <= 0:
                    continue
                parts.append(format_pop(pop))
        new_pops = [p for p in loc["pops"] if p.get("new") and p["size"] > 0]
        for np in new_pops:
            parts.append("\t" + format_pop(np) + "\n")
        parts.append("}")
    parts.append(post_text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(parts), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vanilla", required=True, type=Path)
    ap.add_argument("--mod", required=True, type=Path)
    args = ap.parse_args()

    loc_tpl        = args.vanilla / "in_game/map_data/location_templates.txt"
    pops_file      = args.vanilla / "main_menu/setup/start/06_pops.txt"
    markets_file   = args.vanilla / "main_menu/setup/start/03_markets.txt"
    cities_file    = args.vanilla / "main_menu/setup/start/07_cities_and_buildings.txt"
    countries_file = args.vanilla / "main_menu/setup/start/10_countries.txt"
    rgo_map_file   = args.mod     / "in_game/common/scripted_effects/sul_init_effects.txt"
    rgo_bldg_file  = args.mod     / "in_game/common/building_types/sul_rgo_buildings.txt"

    for f in (loc_tpl, pops_file, markets_file, cities_file, countries_file, rgo_map_file,
              rgo_bldg_file):
        if not f.exists():
            sys.exit(f"missing: {f}")

    raw_materials      = parse_raw_materials(loc_tpl)
    rgo_map            = parse_rgo_map(rgo_map_file)
    goods_to_spec      = parse_goods_to_spec(rgo_map_file)
    rgo_pop_types      = parse_rgo_building_pop_types(rgo_bldg_file)
    owned, tag_info    = parse_countries(countries_file, vanilla=args.vanilla)
    ranks              = parse_ranks(cities_file)
    market_centers     = parse_market_centers(markets_file)

    pre_text, locations_list, post_text = parse_pops_structured(pops_file)
    pops_by_loc = {loc["name"]: loc for loc in locations_list}

    bm_entries = []
    stats = defaultdict(int)

    for loc_name, tag in owned.items():
        if loc_name not in pops_by_loc:
            stats["owned_no_pop_entry"] += 1
            continue
        loc = pops_by_loc[loc_name]
        eligible_pop = compute_eligible_pop(loc["pops"])
        rank = ranks.get(loc_name, "rural_settlement")
        rm = raw_materials.get(loc_name)

        # ---- RGO ----
        rgo_bldg = rgo_map.get(rm) if rm else None
        if rgo_bldg:
            # Tech gate: iron_working (STL >= 1) unlocks iron + coal.
            if rgo_bldg in TECH_GATED_RGOS and tag_info.get(tag, {}).get("stl", 0) < IRON_WORKING_REQUIRED_STL:
                stats["tech_gated_skipped"] += 1
            else:
                rgo_level = min(LEVEL_CAP, 1 + floor(eligible_pop / RGO_POP_PER_LEVEL))
                if rgo_level > 0:
                    bm_entries.append((rgo_bldg, loc_name, tag, rgo_level))
                    stats["rgo_placed"] += 1
                    # Pop shift: peasants -> RGO.pop_type (only cross-type).
                    rgo_pt = rgo_pop_types.get(rgo_bldg)
                    if rgo_pt and rgo_pt != SHIFT_DONOR:
                        shift_peasants_to_target(loc["pops"], rgo_pt, rgo_level)

        # ---- Village (matching spec) ----
        # Level = rank_bonus (0/1/2 for rural/town/city) + floor(eligible_pop/100).
        # Spec predicted from market-center status or raw_material -> spec map.
        if loc_name in market_centers:
            predicted_spec = "commercial"
        else:
            predicted_spec = goods_to_spec.get(rm) if rm else None
        village_bldg = VILLAGE_BY_SPEC.get(predicted_spec)
        if village_bldg:
            village_level = VILLAGE_RANK_BONUS.get(rank, 0) + floor(eligible_pop / VILLAGE_POP_PER_LEVEL)
            village_level = min(village_level, LEVEL_CAP)
            if village_level > 0:
                bm_entries.append((village_bldg, loc_name, tag, village_level))
                stats["village_placed"] += 1

    # Write outputs
    setup_out = args.mod / "main_menu/setup/start/50_sul_setup.txt"
    pops_out  = args.mod / "main_menu/setup/start/06_pops.txt"
    # Retire old generator artifacts
    for stale in [
        args.mod / "main_menu/setup/start/50_sul_rgo_setup.txt",
        args.mod / "in_game/common/town_setups/sul_generated_rgo_setups.txt",
        args.mod / "in_game/common/town_setups/sul_generated_spec_setups.txt",
    ]:
        if stale.exists():
            stale.unlink()

    emit_setup_file(setup_out, bm_entries, [])
    write_pops_override(pops_out, pre_text, locations_list, post_text)

    print(f"raw_material entries parsed:        {len(raw_materials)}")
    print(f"owned locations (loc→tag):          {len(owned)}")
    print(f"market centers:                     {len(market_centers)}")
    print(f"ranks parsed:                       {len(ranks)}")
    print(f"RGO placements:                     {stats['rgo_placed']}")
    print(f"RGOs skipped (no iron_working):      {stats['tech_gated_skipped']}")
    print(f"village placements:                 {stats['village_placed']}")
    print(f"owned but no pop entry:             {stats['owned_no_pop_entry']}")
    print(f"wrote: {setup_out}")
    print(f"wrote: {pops_out}")


if __name__ == "__main__":
    main()
