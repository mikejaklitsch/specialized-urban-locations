"""
SUL — Manpower Maintenance Cost Calculator & Mod File Generator

Solves the AI budget bottleneck where manpower building maintenance
(building_maintenance category) indirectly gates army size. This script
shifts a configurable portion of that cost to regiment maintenance
by computing a per-unit-type goods multiplier.

Core formula:
    S = shift_pct × C_bm × D / effective_recovery

Where:
    S                  = target surcharge per max_strength (ducats)
    shift_pct          = fraction of building maintenance to shift (0.75)
    C_bm               = building maintenance cost per manpower (constant 520)
    D                  = building production method discount (0.2 = 80% off)
    effective_recovery = recovery / (1 + recovery × avg_drain)
    avg_drain          = AI-weight-averaged manpower drain per max_strength

Per-unit-type multiplier:
    M_u = S / d_u
    new_goods_u = existing_goods_u × (1 + M_u)

Where d_u is the existing maintenance goods cost at base prices.
The multiplier is independent of army size — buildings and army scale
together via AI_DESIRED_ARMY_MANPOWER_RECOVERY_MONTHS.

Adapted from AI Builds Armies for the SUL mod (new-game-only variant).

Usage:
    python tools/calculate_maintenance.py             # print report + generate
    python tools/calculate_maintenance.py --dry-run   # print report only
"""

from dataclasses import dataclass
from pathlib import Path
import sys


# ============================================================================
# Tunable Parameters
# ============================================================================

# Fraction of building maintenance cost to shift to regiment maintenance.
# 0.75 = shift 75%, keep 25% as building maintenance.
SHIFT_PERCENT = 0.75

# Vanilla building maintenance discount. Buildings pay this fraction of
# their listed goods cost (production method efficiency).
# Vanilla default: 0.2 (80% discount on buildings).
BUILDING_DISCOUNT = 0.2

# AI targeting parameter (from defines).
AI_RECOVERY_MONTHS = 48  # AI_DESIRED_ARMY_MANPOWER_RECOVERY_MONTHS

# All manpower buildings maintain a constant cost-per-manpower ratio.
# This is verified in the report — if any building deviates, the script
# will flag it. Value = sum(goods × base_price) / local_manpower.
COST_PER_MANPOWER = 520  # ducats at base prices


# ============================================================================
# Vanilla Data — Base Goods Prices
# ============================================================================

BASE_PRICES = {
    "firearms": 3, "leather": 3, "cloth": 3, "paper": 2, "weaponry": 3,
    "lumber": 2, "tools": 3, "horses": 3, "copper": 3, "tin": 2,
    "cannons": 4, "salt": 2, "elephants": 10, "slaves_goods": 3,
    "glass": 3, "medicaments": 3, "jewelry": 6, "books": 3,
}


# ============================================================================
# Vanilla Data — Unit Categories
#
# From unit_categories/*.txt and prices/02_units.txt.
# Used to compute the weighted average manpower drain for the effective
# recovery calculation.
# ============================================================================

@dataclass
class UnitCategory:
    """An army unit category with AI recruitment weight and price data."""
    name: str
    ai_weight: float           # from unit_categories/*.txt
    gold_maintenance: float    # from prices/02_units.txt (per max_strength)
    manpower_drain: float      # from prices/02_units.txt (per max_strength/month)
    default_maintenance: str   # category-default maintenance demand name

UNIT_CATEGORIES = {
    "army_infantry": UnitCategory("army_infantry", ai_weight=0.5,
                                  gold_maintenance=0.5, manpower_drain=0.02,
                                  default_maintenance="infantry_maintenance"),
    "army_cavalry": UnitCategory("army_cavalry", ai_weight=0.2,
                                 gold_maintenance=1.5, manpower_drain=0.04,
                                 default_maintenance="cavalry_maintenance"),
    "army_artillery": UnitCategory("army_artillery", ai_weight=0.4,
                                   gold_maintenance=2.0, manpower_drain=0.04,
                                   default_maintenance="artillery_maintenance"),
    "army_auxiliary": UnitCategory("army_auxiliary", ai_weight=0.1,
                                   gold_maintenance=1.0, manpower_drain=0.02,
                                   default_maintenance="auxuliary_maintenance"),
}


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class Building:
    """A manpower building with its maintenance goods and manpower output."""
    name: str
    local_manpower: float
    maintenance_goods: dict[str, float]
    chain: str   # "urban", "rural", or "both"
    tier: int    # 1, 2, or 3
    unique_method_name: str = ""
    template: str = ""

    @property
    def maintenance_cost(self) -> float:
        return sum(qty * BASE_PRICES[g] for g, qty in self.maintenance_goods.items())

    @property
    def cost_per_manpower(self) -> float:
        return self.maintenance_cost / self.local_manpower


@dataclass
class SharedProductionMethod:
    """A shared production method used by buildings via possible_production_methods."""
    name: str
    goods: dict[str, float]

    @property
    def maintenance_cost(self) -> float:
        return sum(qty * BASE_PRICES[g] for g, qty in self.goods.items())


@dataclass
class RegimentMaintenance:
    """A regiment maintenance demand definition from army_demands.txt."""
    name: str
    goods: dict[str, float]
    category: str  # vanilla category (regiment_maintenance or regiment_construction)

    @property
    def total_cost(self) -> float:
        return sum(qty * BASE_PRICES[g] for g, qty in self.goods.items())


# ============================================================================
# Vanilla Data — Manpower Buildings (with unique_production_methods)
# ============================================================================

BUILDINGS = {
    # --- Urban chain: armory -> barracks -> conscription_center ---
    "armory": Building(
        name="armory", local_manpower=0.01,
        maintenance_goods={
            "firearms": 0.5, "leather": 0.5, "cloth": 0.10,
            "paper": 0.20, "weaponry": 0.5,
        },
        chain="urban", tier=1, unique_method_name="sul_armory_maintenance",
        template="""\
REPLACE:armory = {
	is_foreign = no
	pop_type = soldiers
	max_levels = manpower_max_level
	category = military_category
	forbidden_for_estates = yes
	employment_size = manpower_employment
	town = yes
	city = yes
	important_for_AI = yes
	build_time = soldier_building
	obsolete = provincial_garrison
	obsolete = korean_barracks
	allow = {
		owner = { has_primary_or_accepted_culture = prev.dominant_culture }
	}
	remove_if = {
		NOT = { owner = { has_primary_or_accepted_culture = prev.location.dominant_culture } }
	}
	modifier = {
		local_manpower = 0.01
		can_recruit_regiment_in_this_location = yes
	}
	unique_production_methods = {
__MAINTENANCE__
	}
	construction_demand = early_soldier_building_construction
}""",
    ),
    "barracks": Building(
        name="barracks", local_manpower=0.02,
        maintenance_goods={
            "firearms": 1.0, "leather": 1.0, "cloth": 0.20,
            "paper": 0.40, "weaponry": 1.0,
        },
        chain="urban", tier=2, unique_method_name="sul_barracks_maintenance",
        template="""\
REPLACE:barracks = {
	is_foreign = no
	pop_type = soldiers
	max_levels = manpower_max_level
	category = military_category
	forbidden_for_estates = yes
	employment_size = manpower_employment
	town = yes
	city = yes
	important_for_AI = yes
	obsolete = armory
	build_time = soldier_building
	allow = {
		owner = { has_primary_or_accepted_culture = prev.dominant_culture }
	}
	remove_if = {
		NOT = { owner = { has_primary_or_accepted_culture = prev.location.dominant_culture } }
	}
	modifier = {
		local_manpower = 0.02
		can_recruit_regiment_in_this_location = yes
		max_regiments_trained_at_same_time = 1
	}
	unique_production_methods = {
__MAINTENANCE__
	}
	construction_demand = soldier_building_construction
}""",
    ),

    # --- Rural chain: training_fields -> regimental_camp -> conscription_center ---
    "training_fields": Building(
        name="training_fields", local_manpower=0.01,
        maintenance_goods={
            "firearms": 0.5, "leather": 0.5, "cloth": 0.10,
            "paper": 0.20, "weaponry": 0.5,
        },
        chain="rural", tier=1, unique_method_name="sul_training_fields_maintenance",
        template="""\
REPLACE:training_fields = {
	is_foreign = no
	pop_type = soldiers
	max_levels = manpower_max_level
	category = military_category
	forbidden_for_estates = yes
	employment_size = manpower_employment
	rural_settlement = yes
	important_for_AI = yes
	build_time = soldier_building
	allow = {
		owner = { has_primary_or_accepted_culture = prev.dominant_culture }
	}
	remove_if = {
		NOT = { owner = { has_primary_or_accepted_culture = prev.location.dominant_culture } }
	}
	modifier = {
		local_manpower = 0.01
		can_recruit_regiment_in_this_location = yes
	}
	unique_production_methods = {
__MAINTENANCE__
	}
	construction_demand = soldier_building_construction
}""",
    ),
    "regimental_camp": Building(
        name="regimental_camp", local_manpower=0.02,
        maintenance_goods={
            "firearms": 1.0, "leather": 1.0, "cloth": 0.20,
            "paper": 0.40, "weaponry": 1.0,
        },
        chain="rural", tier=2, unique_method_name="sul_regimental_camp_maintenance",
        template="""\
REPLACE:regimental_camp = {
	is_foreign = no
	pop_type = soldiers
	max_levels = manpower_max_level
	category = military_category
	forbidden_for_estates = yes
	employment_size = manpower_employment
	important_for_AI = yes
	obsolete = training_fields
	rural_settlement = yes
	build_time = soldier_building
	allow = {
		owner = { has_primary_or_accepted_culture = prev.dominant_culture }
	}
	remove_if = {
		NOT = { owner = { has_primary_or_accepted_culture = prev.location.dominant_culture } }
	}
	modifier = {
		local_manpower = 0.02
		can_recruit_regiment_in_this_location = yes
	}
	unique_production_methods = {
__MAINTENANCE__
	}
	construction_demand = soldier_building_construction
}""",
    ),

    # --- Shared tier 3 (both chains converge) ---
    "conscription_center": Building(
        name="conscription_center", local_manpower=0.04,
        maintenance_goods={
            "firearms": 2.0, "leather": 2.0, "cloth": 0.40,
            "paper": 0.80, "weaponry": 2.0,
        },
        chain="both", tier=3,
        unique_method_name="sul_conscription_center_maintenance",
        template="""\
REPLACE:conscription_center = {
	is_foreign = no
	pop_type = soldiers
	max_levels = manpower_max_level
	employment_size = manpower_employment
	category = military_category
	forbidden_for_estates = yes
	important_for_AI = yes
	obsolete = regimental_camp
	obsolete = barracks
	rural_settlement = yes
	town = yes
	city = yes
	build_time = soldier_building
	allow = {
		owner = { has_primary_or_accepted_culture = prev.dominant_culture }
	}
	remove_if = {
		NOT = { owner = { has_primary_or_accepted_culture = prev.location.dominant_culture } }
	}
	modifier = {
		local_manpower = 0.04
		can_recruit_regiment_in_this_location = yes
		max_regiments_trained_at_same_time = 5
	}
	unique_production_methods = {
__MAINTENANCE__
	}
	construction_demand = soldier_building_construction
}""",
    ),
}


# ============================================================================
# Vanilla Data — Shared Production Methods
# ============================================================================

SHARED_METHODS = {
    "early_soldier_building_maintenance": SharedProductionMethod(
        name="early_soldier_building_maintenance",
        goods={"leather": 0.5, "cloth": 0.10, "paper": 0.20, "weaponry": 0.5},
    ),
    "nahuatl_warrior_building_maintenance": SharedProductionMethod(
        name="nahuatl_warrior_building_maintenance",
        goods={"weaponry": 1.0},
    ),
    "warrior_monks_training_grounds_maintenance": SharedProductionMethod(
        name="warrior_monks_training_grounds_maintenance",
        goods={"cloth": 0.01, "paper": 0.05, "weaponry": 0.05},
    ),
}


# ============================================================================
# Vanilla Data — Regiment Maintenance Demands
#
# All 23 maintenance demands from army_demands.txt. Values are per 1k men
# (max_strength = 1.0). The game scales by max_strength.
#
# Each type's existing goods are multiplied by (1 + M_u) where M_u is
# computed to achieve a uniform surcharge per max_strength across all types.
# ============================================================================

REGIMENT_MAINTENANCE = {
    # --- Infantry (regiment_maintenance) ---
    "early_infantry_maintenance": RegimentMaintenance(
        name="early_infantry_maintenance",
        goods={"weaponry": 0.05, "leather": 0.03},
        category="regiment_maintenance",
    ),
    "early_heavy_infantry_maintenance": RegimentMaintenance(
        name="early_heavy_infantry_maintenance",
        goods={"weaponry": 0.05, "leather": 0.03},
        category="regiment_maintenance",
    ),
    "archer_infantry_maintenance": RegimentMaintenance(
        name="archer_infantry_maintenance",
        goods={"weaponry": 0.03, "leather": 0.03, "lumber": 0.03},
        category="regiment_maintenance",
    ),
    "infantry_maintenance": RegimentMaintenance(
        name="infantry_maintenance",
        goods={"firearms": 0.05, "weaponry": 0.05, "leather": 0.03},
        category="regiment_maintenance",
    ),
    "pikemen_maintenance": RegimentMaintenance(
        name="pikemen_maintenance",
        goods={"weaponry": 0.04, "leather": 0.04, "lumber": 0.04, "tools": 0.04},
        category="regiment_maintenance",
    ),
    "heavy_infantry_maintenance": RegimentMaintenance(
        name="heavy_infantry_maintenance",
        goods={"firearms": 0.05, "weaponry": 0.05, "leather": 0.03, "tools": 0.02},
        category="regiment_maintenance",
    ),
    "rifle_infantry_maintenance": RegimentMaintenance(
        name="rifle_infantry_maintenance",
        goods={"firearms": 0.30, "weaponry": 0.05, "leather": 0.03},
        category="regiment_maintenance",
    ),

    # --- Cavalry (mixed categories) ---
    "cavalry_maintenance": RegimentMaintenance(
        name="cavalry_maintenance",
        goods={"leather": 0.04, "cloth": 0.04, "horses": 0.25, "weaponry": 0.05},
        category="regiment_construction",
    ),
    "heavy_cavalry_maintenance": RegimentMaintenance(
        name="heavy_cavalry_maintenance",
        goods={"leather": 0.05, "weaponry": 0.1, "cloth": 0.05,
               "horses": 0.5, "tools": 0.1},
        category="regiment_maintenance",
    ),
    "expensive_heavy_cavalry_maintenance": RegimentMaintenance(
        name="expensive_heavy_cavalry_maintenance",
        goods={"leather": 0.1, "weaponry": 0.2, "cloth": 0.1,
               "horses": 1.0, "tools": 0.2},
        category="regiment_maintenance",
    ),
    "steppe_horse_archers_maintenance": RegimentMaintenance(
        name="steppe_horse_archers_maintenance",
        goods={"leather": 0.01, "horses": 0.2, "weaponry": 0.01},
        category="regiment_construction",
    ),
    "steppe_horse_auxiliary_maintenance": RegimentMaintenance(
        name="steppe_horse_auxiliary_maintenance",
        goods={"leather": 0.01, "horses": 0.5, "salt": 0.01},
        category="regiment_construction",
    ),
    "clan_retainer_cavalry_maintenance": RegimentMaintenance(
        name="clan_retainer_cavalry_maintenance",
        goods={"weaponry": 0.02, "leather": 0.01, "horses": 0.02},
        category="regiment_maintenance",
    ),

    # --- Artillery (regiment_maintenance) ---
    "artillery_maintenance": RegimentMaintenance(
        name="artillery_maintenance",
        goods={"cannons": 0.5, "copper": 0.1, "tin": 0.05},
        category="regiment_maintenance",
    ),

    # --- Auxiliaries (regiment_maintenance) ---
    "auxuliary_maintenance": RegimentMaintenance(
        name="auxuliary_maintenance",
        goods={"paper": 0.02, "medicaments": 0.02, "tools": 0.02,
               "leather": 0.02, "salt": 0.025},
        category="regiment_maintenance",
    ),

    # --- Elephants (regiment_maintenance) ---
    "elephant_auxiliary_maintenance": RegimentMaintenance(
        name="elephant_auxiliary_maintenance",
        goods={"paper": 0.05, "medicaments": 0.05, "tools": 0.05,
               "leather": 0.05, "cloth": 0.05, "salt": 0.025,
               "elephants": 0.2},
        category="regiment_maintenance",
    ),
    "elephant_cavalry_maintenance": RegimentMaintenance(
        name="elephant_cavalry_maintenance",
        goods={"leather": 0.05, "cloth": 0.05, "elephants": 1.0,
               "weaponry": 0.05},
        category="regiment_maintenance",
    ),
    "elephant_infantry_maintenance": RegimentMaintenance(
        name="elephant_infantry_maintenance",
        goods={"leather": 0.05, "elephants": 0.5, "weaponry": 0.1,
               "lumber": 0.5},
        category="regiment_maintenance",
    ),

    # --- Tribal (regiment_construction) ---
    "a_tribesmen_maintenance": RegimentMaintenance(
        name="a_tribesmen_maintenance",
        goods={"weaponry": 0.05},
        category="regiment_construction",
    ),
    "a_warriors_maintenance": RegimentMaintenance(
        name="a_warriors_maintenance",
        goods={"weaponry": 0.05, "leather": 0.05},
        category="regiment_construction",
    ),
    "a_champions_maintenance": RegimentMaintenance(
        name="a_champions_maintenance",
        goods={"weaponry": 0.1, "leather": 0.1},
        category="regiment_construction",
    ),
    "a_chieftains_maintenance": RegimentMaintenance(
        name="a_chieftains_maintenance",
        goods={"weaponry": 0.1, "leather": 0.1, "jewelry": 0.05},
        category="regiment_construction",
    ),

    # --- Clan retainers (regiment_maintenance) ---
    "clan_retainers_maintenance": RegimentMaintenance(
        name="clan_retainers_maintenance",
        goods={"weaponry": 0.02, "leather": 0.01},
        category="regiment_maintenance",
    ),
}


# ============================================================================
# Special manpower buildings that get important_for_AI = yes
# ============================================================================

SPECIAL_MANPOWER_BUILDINGS = [
    "sergeantry",
    "warrior_temple",
    "jurchen_barracks",
    "thema_headquarters",
    "city_guard",
]


# ============================================================================
# Calculations
# ============================================================================

def compute_avg_manpower_drain() -> float:
    """
    Weighted average manpower drain per max_strength per month,
    using AI recruitment weights from unit categories.
    """
    total_weight = sum(c.ai_weight for c in UNIT_CATEGORIES.values())
    return sum(
        c.ai_weight / total_weight * c.manpower_drain
        for c in UNIT_CATEGORIES.values()
    )


def compute_effective_recovery() -> float:
    """
    Recovery months adjusted for standing manpower drain.

    The AI wants to rebuild from zero in AI_RECOVERY_MONTHS, but during
    rebuild the growing army also consumes manpower. Solving:
        dM/dt = monthly_mp - M × avg_drain
    gives an effective recovery shorter than the nominal value.

    Simplified: effective = recovery / (1 + recovery × avg_drain)
    """
    avg_drain = compute_avg_manpower_drain()
    return AI_RECOVERY_MONTHS / (1.0 + AI_RECOVERY_MONTHS * avg_drain)


def compute_surcharge_per_max_strength() -> float:
    """
    Target surcharge in ducats per max_strength for regiment maintenance.

    S = shift_pct × C_bm × D / effective_recovery

    This is the total surcharge the average regiment must absorb.
    """
    eff = compute_effective_recovery()
    return SHIFT_PERCENT * COST_PER_MANPOWER * BUILDING_DISCOUNT / eff


def compute_weighted_avg_goods_cost() -> float:
    """
    AI-weight-averaged maintenance goods cost per max_strength, using
    each category's default maintenance demand.

    weighted_avg_d = Σ(f_c × d_default_c)

    Where f_c = ai_weight_c / total_weight.
    """
    total_weight = sum(c.ai_weight for c in UNIT_CATEGORIES.values())
    return sum(
        c.ai_weight / total_weight
        * REGIMENT_MAINTENANCE[c.default_maintenance].total_cost
        for c in UNIT_CATEGORIES.values()
    )


def compute_uniform_multiplier() -> float:
    """
    Single multiplier applied to ALL regiment goods to achieve balance.

    M = S / weighted_avg_d

    Every unit type's goods are scaled by (1 + M). Cheap units stay
    cheap, expensive units stay expensive — the proportional cost
    structure is preserved.
    """
    S = compute_surcharge_per_max_strength()
    avg_d = compute_weighted_avg_goods_cost()
    return S / avg_d


def compute_remaining_building_goods(building: Building) -> dict[str, float]:
    """Building goods that stay as building_maintenance (the kept fraction)."""
    kept = 1.0 - SHIFT_PERCENT
    return {g: round(qty * kept, 2) for g, qty in building.maintenance_goods.items()}


def compute_remaining_shared_goods(method: SharedProductionMethod) -> dict[str, float]:
    """Reduce a shared production method by the shift percentage."""
    kept = 1.0 - SHIFT_PERCENT
    return {g: round(qty * kept, 2) for g, qty in method.goods.items()}


def compute_regiment_final_goods(reg: RegimentMaintenance) -> dict[str, float]:
    """
    Scale existing regiment goods by (1 + M) using the uniform multiplier.
    Preserves both the goods mix and the relative cost between unit types.
    """
    factor = 1.0 + compute_uniform_multiplier()
    return {g: round(qty * factor, 2) for g, qty in reg.goods.items()}


# ============================================================================
# Paradox Script Formatting
# ============================================================================

def fmt(value: float) -> str:
    """Format a float for Paradox script output, trimming excess zeros."""
    if value == int(value):
        return f"{value:.1f}"
    s = f"{value:.2f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s


def pdx_block(name: str, entries: dict[str, str], indent: int = 0,
              prefix: str = "") -> str:
    """Format a Paradox script block."""
    tabs = "\t" * indent
    inner = "\t" * (indent + 1)
    lines = [f"{tabs}{prefix}{name} = {{"]
    for key, val in entries.items():
        lines.append(f"{inner}{key} = {val}")
    lines.append(f"{tabs}}}")
    return "\n".join(lines)


# ============================================================================
# File Generation
# ============================================================================

MOD_ROOT = Path(__file__).resolve().parent.parent


def write_mod_file(relative_path: str, content: str):
    """Write a mod file with UTF-8 BOM, creating directories as needed."""
    path = MOD_ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(content)
    print(f"  wrote: {relative_path}")


def generate_buildings():
    """Generate REPLACE building definitions with reduced maintenance."""
    header = (
        "# SUL — Manpower Building Replacement\n"
        "#\n"
        f"# Replaces manpower buildings with {SHIFT_PERCENT:.0%}"
        " reduced maintenance.\n"
        "# Shifted cost absorbed by regiment maintenance"
        " (sul_army_demands.txt).\n"
        "#\n"
        "# Generated by tools/calculate_maintenance.py\n"
        "\n"
    )

    blocks = []
    for building in BUILDINGS.values():
        remaining = compute_remaining_building_goods(building)
        entries = {g: fmt(qty) for g, qty in remaining.items()}
        entries["category"] = "building_maintenance"
        maintenance_block = pdx_block(
            building.unique_method_name, entries, indent=2,
        )
        block = building.template.replace("__MAINTENANCE__", maintenance_block)
        blocks.append(
            f"# {building.name} ({building.chain} tier {building.tier})"
            f"\n{block}"
        )

    write_mod_file(
        "in_game/common/building_types/sul_manpower_buildings.txt",
        header + "\n\n".join(blocks) + "\n",
    )


def generate_shared_method_overrides():
    """Generate REPLACE overrides for shared production methods."""
    header = (
        "# SUL — Shared Manpower Production Method Reduction\n"
        "#\n"
        f"# Reduces shared manpower building maintenance by"
        f" {SHIFT_PERCENT:.0%}.\n"
        "# These methods are used by buildings that reference them via\n"
        "# possible_production_methods (sergeantry, jurchen_barracks, etc.).\n"
        "#\n"
        "# Generated by tools/calculate_maintenance.py\n"
        "\n"
    )

    blocks = []
    for method in SHARED_METHODS.values():
        remaining = compute_remaining_shared_goods(method)
        entries = {g: fmt(qty) for g, qty in remaining.items()}
        entries["category"] = "building_maintenance"
        block = pdx_block(method.name, entries, prefix="REPLACE:")
        blocks.append(block)

    content = header + "\n\n".join(blocks) + "\n"
    write_mod_file(
        "in_game/common/production_methods/sul_manpower_production_methods.txt",
        content,
    )


def generate_regiment_overrides():
    """
    Generate REPLACE overrides for ALL regiment maintenance demands.
    Each type's goods are multiplied by (1 + M_u) to absorb the shifted
    building maintenance cost.
    """
    S = compute_surcharge_per_max_strength()
    M = compute_uniform_multiplier()
    eff = compute_effective_recovery()
    avg_d = compute_weighted_avg_goods_cost()

    header = (
        "# SUL — Regiment Maintenance Increase\n"
        "#\n"
        f"# Absorbs {SHIFT_PERCENT:.0%} of manpower building"
        " maintenance cost.\n"
        f"# All goods multiplied by x{1 + M:.2f}"
        " (uniform across all types).\n"
        "#\n"
        f"# M = S / avg_d = {S:.3f} / {avg_d:.3f} = {M:.3f}\n"
        f"# S = {SHIFT_PERCENT} × {COST_PER_MANPOWER} × {BUILDING_DISCOUNT}"
        f" / {eff:.2f} = {S:.3f}\n"
        "#\n"
        "# Generated by tools/calculate_maintenance.py\n"
        "\n"
    )

    blocks = []
    for reg in REGIMENT_MAINTENANCE.values():
        final_goods = compute_regiment_final_goods(reg)

        entries = {g: fmt(qty) for g, qty in final_goods.items()}
        entries["category"] = reg.category

        block = pdx_block(reg.name, entries, prefix="REPLACE:")
        comment = (f"# {reg.name}: vanilla {reg.total_cost:.2f}"
                   f" → {reg.total_cost * (1 + M):.2f} ducats")
        blocks.append(f"{comment}\n{block}")

    content = header + "\n\n".join(blocks) + "\n"
    write_mod_file(
        "in_game/common/goods_demand/sul_army_demands.txt",
        content,
    )


def generate_important_for_ai():
    """Generate INJECT important_for_AI = yes for special manpower buildings."""
    header = (
        "# SUL — AI Building Priority\n"
        "#\n"
        "# Adds important_for_AI = yes to special manpower buildings\n"
        "# so the AI prioritizes building them.\n"
        "#\n"
        "# Generated by tools/calculate_maintenance.py\n"
        "\n"
    )

    blocks = []
    for name in SPECIAL_MANPOWER_BUILDINGS:
        blocks.append(
            f"INJECT:{name} = {{\n"
            f"\timportant_for_AI = yes\n"
            f"}}"
        )

    content = header + "\n\n".join(blocks) + "\n"
    write_mod_file(
        "in_game/common/building_types/sul_manpower_ai_priority.txt",
        content,
    )


def generate_all():
    """Generate all mod override files."""
    print()
    print("=" * 70)
    print("GENERATING MOD FILES")
    print("=" * 70)
    generate_buildings()
    generate_shared_method_overrides()
    generate_regiment_overrides()
    generate_important_for_ai()

    print()
    print("  Run pdx-format on generated .txt files before testing.")


# ============================================================================
# Reporting
# ============================================================================

def print_parameters():
    """Print the current tunable parameters and derived values."""
    avg_drain = compute_avg_manpower_drain()
    eff = compute_effective_recovery()
    S = compute_surcharge_per_max_strength()

    print("=" * 70)
    print("PARAMETERS")
    print("=" * 70)
    print(f"  Shift percentage:          {SHIFT_PERCENT:.0%}")
    print(f"  Building discount (D):     {BUILDING_DISCOUNT}"
          f" ({1 - BUILDING_DISCOUNT:.0%} off)")
    print(f"  AI recovery months:        {AI_RECOVERY_MONTHS}")
    print(f"  Cost per manpower (C_bm):  {COST_PER_MANPOWER}")
    print()
    avg_d = compute_weighted_avg_goods_cost()
    M = compute_uniform_multiplier()

    print(f"  AI weights:  infantry={UNIT_CATEGORIES['army_infantry'].ai_weight}"
          f"  cavalry={UNIT_CATEGORIES['army_cavalry'].ai_weight}"
          f"  artillery={UNIT_CATEGORIES['army_artillery'].ai_weight}"
          f"  auxiliary={UNIT_CATEGORIES['army_auxiliary'].ai_weight}")
    print(f"  MP drain:    infantry={UNIT_CATEGORIES['army_infantry'].manpower_drain}"
          f"  cavalry={UNIT_CATEGORIES['army_cavalry'].manpower_drain}"
          f"  artillery={UNIT_CATEGORIES['army_artillery'].manpower_drain}"
          f"  auxiliary={UNIT_CATEGORIES['army_auxiliary'].manpower_drain}")
    print(f"  Avg manpower drain:        {avg_drain:.4f} per max_str/month")
    print(f"  Effective recovery:        {eff:.2f} months"
          f" (nominal {AI_RECOVERY_MONTHS})")
    print(f"  Surcharge per max_str (S): {S:.3f} ducats")
    print(f"  Weighted avg goods cost:   {avg_d:.3f} ducats")
    print(f"  Uniform multiplier (M):    {M:.3f}  (all goods ×{1 + M:.2f})")
    print()

    # Verify cost/mp is constant across buildings.
    cpm_values = {b.name: b.cost_per_manpower for b in BUILDINGS.values()}
    if len(set(cpm_values.values())) > 1:
        print("  WARNING: cost/mp is not constant across buildings!")
        for name, cpm in cpm_values.items():
            print(f"    {name}: {cpm:.1f}")
    else:
        print(f"  cost/mp verified: {COST_PER_MANPOWER} across all buildings")
    print()


def print_building_results():
    """Print building maintenance reduction results."""
    print("=" * 70)
    print("BUILDING MAINTENANCE (what stays as building_maintenance)")
    print("=" * 70)

    for b in BUILDINGS.values():
        remaining = compute_remaining_building_goods(b)
        remaining_cost = sum(qty * BASE_PRICES[g] for g, qty in remaining.items())

        print(f"\n  {b.name} ({b.chain} tier {b.tier})")
        print(f"  mp = {b.local_manpower},  cost/mp = {b.cost_per_manpower:.0f}")
        print(f"  vanilla: {b.maintenance_cost:.2f} ducats  →  "
              f"mod: {remaining_cost:.2f} ducats  "
              f"({remaining_cost / b.maintenance_cost:.0%})")
        for g, qty in sorted(remaining.items()):
            if qty > 0:
                print(f"    {g}: {qty}")

    print(f"\n  --- Shared production methods ---")
    for m in SHARED_METHODS.values():
        remaining = compute_remaining_shared_goods(m)
        remaining_cost = sum(qty * BASE_PRICES[g] for g, qty in remaining.items())
        print(f"\n  {m.name}")
        print(f"  vanilla: {m.maintenance_cost:.2f}  →  mod: {remaining_cost:.2f}"
              f"  ({remaining_cost / m.maintenance_cost:.0%})")
        for g, qty in sorted(remaining.items()):
            if qty > 0:
                print(f"    {g}: {qty}")


def print_regiment_results():
    """Print regiment maintenance multiplier results."""
    M = compute_uniform_multiplier()
    print()
    print("=" * 70)
    print(f"REGIMENT MAINTENANCE (all goods ×{1 + M:.2f})")
    print("=" * 70)

    for reg in REGIMENT_MAINTENANCE.values():
        final_goods = compute_regiment_final_goods(reg)
        final_cost = sum(qty * BASE_PRICES[g] for g, qty in final_goods.items())

        print(f"\n  {reg.name}  [{reg.category}]")
        print(f"  vanilla: {reg.total_cost:.2f} ducats  →  "
              f"{final_cost:.2f} ducats")
        for g in sorted(final_goods):
            old = reg.goods.get(g, 0)
            new = final_goods[g]
            print(f"    {g}: {old} → {new}")


def print_balance_check():
    """Print a balance verification for a hypothetical country."""
    S = compute_surcharge_per_max_strength()
    eff = compute_effective_recovery()
    avg_drain = compute_avg_manpower_drain()

    print()
    print("=" * 70)
    print("BALANCE CHECK — Hypothetical country")
    print("=" * 70)

    # Use a round number of building levels.
    n_levels = 200
    building = BUILDINGS["armory"]
    mp = building.local_manpower
    monthly_mp = n_levels * mp

    # Army at drain-adjusted equilibrium.
    total_max_str = monthly_mp / (1.0 / AI_RECOVERY_MONTHS + avg_drain)

    # Building costs.
    vanilla_bldg = n_levels * building.maintenance_cost * BUILDING_DISCOUNT
    remaining = compute_remaining_building_goods(building)
    remaining_cost = sum(qty * BASE_PRICES[g] for g, qty in remaining.items())
    mod_bldg = n_levels * remaining_cost * BUILDING_DISCOUNT
    savings = vanilla_bldg - mod_bldg

    # Regiment surcharge.
    surcharge = S * total_max_str

    print(f"  {n_levels} armory levels, mp/level = {mp}")
    print(f"  Monthly manpower: {monthly_mp}")
    print(f"  Avg drain: {avg_drain:.4f}")
    print(f"  Effective recovery: {eff:.2f} months")
    print(f"  Equilibrium army: {total_max_str:.1f} max_str")
    print()
    print(f"  Vanilla building maintenance:  {vanilla_bldg:.1f}")
    print(f"  Mod building maintenance:      {mod_bldg:.1f}")
    print(f"  Building savings:              {savings:.1f}")
    print(f"  Regiment surcharge:            {surcharge:.1f}")
    print(f"  Balance (savings - surcharge): {savings - surcharge:.1f}")

    # Per-category breakdown using AI weights and uniform multiplier.
    M = compute_uniform_multiplier()
    print()
    print(f"  --- Army composition at equilibrium (×{1 + M:.2f} multiplier) ---")
    total_weight = sum(c.ai_weight for c in UNIT_CATEGORIES.values())
    cat_surcharge_total = 0
    for cat in UNIT_CATEGORIES.values():
        frac = cat.ai_weight / total_weight
        cat_max_str = total_max_str * frac
        cat_d = REGIMENT_MAINTENANCE[cat.default_maintenance].total_cost
        cat_gold = cat_max_str * cat.gold_maintenance
        cat_surcharge = cat_max_str * cat_d * M
        cat_surcharge_total += cat_surcharge
        print(f"  {cat.name}: {frac:.0%} = {cat_max_str:.1f} max_str"
              f"  gold={cat_gold:.1f}"
              f"  goods: {cat_d:.2f}→{cat_d * (1 + M):.2f}"
              f"  surcharge={cat_surcharge:.1f}")
    print(f"  Total goods surcharge: {cat_surcharge_total:.1f}"
          f"  (savings: {savings:.1f})")


# ============================================================================
# Main
# ============================================================================

def main():
    dry_run = "--dry-run" in sys.argv

    print_parameters()
    print_building_results()
    print_regiment_results()
    print_balance_check()

    if not dry_run:
        generate_all()
    else:
        print("\n  (dry run — no files generated)")


if __name__ == "__main__":
    main()
