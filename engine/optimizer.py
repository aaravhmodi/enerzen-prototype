"""
Multi-objective optimizer for EnerZen assembly selection.

Takes a building spec and budget constraint, evaluates all feasible combinations
from the assembly catalog, and returns Pareto-optimal configurations ranked by
a weighted score. The Pareto frontier is returned so the user can choose their
preferred trade-off.
"""

import json
import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from engine.simulator import BuildingSpec, AssemblyConfig, simulate, EnergyResult, nzr_probability
from engine.carbon import calculate_carbon
from engine.cost import estimate_cost, estimate_schedule
from engine.solar import calculate_solar
from engine.finance import monthly_utility, lifecycle_cost
from engine.location import resolve as resolve_location
from engine.assemblies import WALLS, ROOFS, FLOORS, EnvelopeCombo


DATA_PATH = Path(__file__).parent.parent / "data" / "assemblies.json"


@dataclass
class ProjectSpec:
    # Project info
    typology: str           # "single_family", "townhouse", "murb"
    climate_zone: str       # "6", "7a", "7b" — overridden by `location` if set
    floor_area_m2: float
    storeys: int
    orientation: str        # "N", "S", "E", "W"
    window_to_wall_ratio: float
    budget_per_unit: float  # CAD
    target_label: str       # "code", "nzr", "passive_house"
    solar_option_id: str = "PV0"  # from catalog["solar"]; PV0 = none
    location: str = None    # Ontario place name; drives zone, snow tier, regional rates
    num_units: int = 1
    has_ac: bool = True     # add central AC when the heating plant is a furnace
    allow_gas: bool = True  # False = all-electric: gas systems excluded

    # Derived
    infiltration_ach50: float = 3.0  # default target; tightens for higher labels


@dataclass
class ConfigResult:
    wall_id: str
    roof_id: str
    floor_id: str
    window_id: str
    mechanical_id: str

    # Scores
    construction_cost: float
    construction_weeks: float
    embodied_carbon_kg_co2e_m2: float
    eui_kwh_m2_yr: float
    nzr_compliant: bool
    nzr_probability: float
    energuide_score: float

    # Solar / net energy
    pv_capacity_kw: float = 0.0
    pv_generation_kwh_yr: float = 0.0
    net_operational_energy_kwh_yr: float = 0.0
    net_eui_kwh_m2_yr: float = 0.0
    net_zero: bool = False

    # Utility + lifecycle
    annual_utility_cost: float = 0.0
    avg_monthly_utility: float = 0.0
    lifecycle_cost_60yr: float = 0.0

    # Assembly build parameters (swept)
    wall_ext_rigid_in: float = 0.0
    roof_deck_rigid_in: float = 0.0
    floor_rigid_in: float = 0.0
    joist_depth_in: int = 0

    # Details
    energy: EnergyResult = field(repr=False, default=None)
    panel_schedule: dict = field(repr=False, default=None)
    utility: dict = field(repr=False, default=None)
    _assembly: AssemblyConfig = field(repr=False, default=None)  # for deferred MC

    # Pareto rank (1 = non-dominated)
    pareto_rank: int = 0
    weighted_score: float = 0.0


def load_catalog() -> dict:
    with open(DATA_PATH) as f:
        return json.load(f)


def _ach50_for_label(label: str) -> float:
    return {"code": 5.0, "nzr": 3.0, "passive_house": 1.5}.get(label, 3.0)


def _is_dominated(a: ConfigResult, b: ConfigResult) -> bool:
    """Return True if b dominates a (b is better or equal on all 4 objectives)."""
    return (
        b.construction_cost       <= a.construction_cost and
        b.construction_weeks      <= a.construction_weeks and
        b.embodied_carbon_kg_co2e_m2 <= a.embodied_carbon_kg_co2e_m2 and
        b.eui_kwh_m2_yr           <= a.eui_kwh_m2_yr and
        (
            b.construction_cost < a.construction_cost or
            b.construction_weeks < a.construction_weeks or
            b.embodied_carbon_kg_co2e_m2 < a.embodied_carbon_kg_co2e_m2 or
            b.eui_kwh_m2_yr < a.eui_kwh_m2_yr
        )
    )


def pareto_rank(results: list[ConfigResult]) -> list[ConfigResult]:
    for i, a in enumerate(results):
        rank = 1
        for j, b in enumerate(results):
            if i != j and _is_dominated(a, b):
                rank += 1
        a.pareto_rank = rank
    return sorted(results, key=lambda r: (r.pareto_rank, r.weighted_score))


def optimize(spec: ProjectSpec, weights: Optional[dict] = None) -> list[ConfigResult]:
    """
    Run optimization over all feasible assembly combinations.

    weights: dict with keys cost, speed, carbon, energy (must sum to 1.0)
             defaults to equal weighting
    """
    if weights is None:
        weights = {"cost": 0.25, "speed": 0.25, "carbon": 0.25, "energy": 0.25}

    catalog = load_catalog()
    ach50 = _ach50_for_label(spec.target_label)

    # A location, if given, overrides the climate zone and supplies regional
    # energy rates and the structural snow tier.
    loc = resolve_location(spec.location) if spec.location else None
    climate_zone = loc.climate_zone if loc else spec.climate_zone

    solar_option = next(
        (s for s in catalog["solar"] if s["id"] == spec.solar_option_id),
        catalog["solar"][0],
    )
    climate = catalog["climate_zones"][climate_zone]
    solar = calculate_solar(solar_option, climate, spec.orientation)

    rates = dict(catalog["energy_rates"])
    if loc:
        rates["electricity_cad_per_kwh"] = loc.electricity_cad_per_kwh
        rates["natural_gas_cad_per_kwh"] = loc.natural_gas_cad_per_kwh
    solar_rebate = rates.get("solar_rebate_cad", 0) if solar["capacity_kw"] > 0 else 0

    building = BuildingSpec(
        floor_area_m2=spec.floor_area_m2,
        storeys=spec.storeys,
        climate_zone=climate_zone,
        orientation=spec.orientation,
        window_to_wall_ratio=spec.window_to_wall_ratio,
        infiltration_ach50=ach50,
    )

    # Roof joist depth is set by the structural snow tier (from location).
    # Without a location, default to the lightest tier.
    joist_depth = loc.joist_depth_in if loc else catalog["snow"]["tiers"][0]["joist_depth_in"]

    mech_options = [m for m in catalog["mechanical"]
                    if spec.allow_gas or m["type"] != "gas"]

    all_configs = []
    for wall_opt, roof_opt, floor_opt, window, mech in itertools.product(
            WALLS, ROOFS, FLOORS, catalog["windows"], mech_options):
        for w_rigid, r_rigid, f_rigid in itertools.product(
                wall_opt.sweep, roof_opt.sweep, floor_opt.sweep):

            wall_asm  = wall_opt.build(w_rigid)
            roof_asm  = roof_opt.build(joist_depth, r_rigid)
            floor_asm = floor_opt.build(
                f_rigid,
                floor_area_m2=spec.floor_area_m2,
                storeys=spec.storeys,
                frost_depth_m=loc.frost_depth_m if loc else 1.2,
            )

            env = EnvelopeCombo(
                wall_id=wall_opt.id, roof_id=roof_opt.id, floor_id=floor_opt.id,
                wall=wall_asm, roof=roof_asm, floor=floor_asm,
                wall_ext_rigid_in=w_rigid, roof_deck_rigid_in=r_rigid,
                floor_rigid_in=f_rigid, joist_depth_in=joist_depth,
                wall_hours_per_m2=wall_opt.install_hours_per_m2,
                roof_hours_per_m2=roof_opt.install_hours_per_m2,
                floor_hours_per_m2=floor_opt.install_hours_per_m2,
            )

            assembly = AssemblyConfig(
                wall_u=wall_asm.u_value,
                roof_u=roof_asm.u_value,
                floor_u=floor_asm.u_value,
                window_u=window["u_value"],
                window_shgc=window["shgc"],
                mechanical_cop=mech.get("heating_cop", 1.0),
                mechanical_type=mech["type"],
                hrv_efficiency=mech.get("hrv_efficiency", 0.0),
            )

            energy = simulate(building, assembly)
            cost_data = estimate_cost(spec, env, window, mech)
            carbon_data = calculate_carbon(spec, env, window, mech, energy)
            schedule = estimate_schedule(spec, env)

            net_operational = energy.total_energy_kwh_yr - solar["annual_generation_kwh"]
            net_eui = net_operational / spec.floor_area_m2
            total_cost = cost_data["total_per_unit"] + solar["cost"]

            if total_cost > spec.budget_per_unit:
                continue
            if spec.target_label == "nzr" and not energy.nzr_compliant:
                continue

            utility = monthly_utility(energy, mech["type"], solar["annual_generation_kwh"], rates)
            lcc = lifecycle_cost(total_cost, utility["annual_total"], rebate=solar_rebate)

            result = ConfigResult(
                wall_id=wall_opt.id,
                roof_id=roof_opt.id,
                floor_id=floor_opt.id,
                window_id=window["id"],
                mechanical_id=mech["id"],
                construction_cost=total_cost,
                construction_weeks=schedule["weeks_to_envelope_close"],
                embodied_carbon_kg_co2e_m2=carbon_data["total_per_m2"]
                    + solar["embodied_carbon_kg_co2e"] / spec.floor_area_m2,
                eui_kwh_m2_yr=energy.eui_kwh_m2_yr,
                nzr_compliant=energy.nzr_compliant,
                nzr_probability=0.0,   # deferred; computed for top configs below
                energuide_score=energy.energuide_score,
                pv_capacity_kw=solar["capacity_kw"],
                pv_generation_kwh_yr=solar["annual_generation_kwh"],
                net_operational_energy_kwh_yr=round(net_operational, 0),
                net_eui_kwh_m2_yr=round(net_eui, 1),
                net_zero=net_operational <= 0,
                annual_utility_cost=utility["annual_total"],
                avg_monthly_utility=utility["avg_monthly"],
                lifecycle_cost_60yr=lcc["total"],
                wall_ext_rigid_in=w_rigid,
                roof_deck_rigid_in=r_rigid,
                floor_rigid_in=f_rigid,
                joist_depth_in=joist_depth,
                energy=energy,
                panel_schedule=schedule["panel_counts"],
                utility=utility,
                _assembly=assembly,
            )
            all_configs.append(result)

    if not all_configs:
        return []

    # Normalize objectives for weighted scoring
    costs   = [r.construction_cost for r in all_configs]
    weeks   = [r.construction_weeks for r in all_configs]
    carbons = [r.embodied_carbon_kg_co2e_m2 for r in all_configs]
    euis    = [r.eui_kwh_m2_yr for r in all_configs]

    def norm(val, vals):
        lo, hi = min(vals), max(vals)
        return (val - lo) / (hi - lo) if hi > lo else 0.0

    for r in all_configs:
        r.weighted_score = (
            weights["cost"]   * norm(r.construction_cost, costs) +
            weights["speed"]  * norm(r.construction_weeks, weeks) +
            weights["carbon"] * norm(r.embodied_carbon_kg_co2e_m2, carbons) +
            weights["energy"] * norm(r.eui_kwh_m2_yr, euis)
        )

    ranked = pareto_rank(all_configs)

    # NZR probability is a 400-run Monte Carlo — only worth computing for the
    # configs actually shown. Run it on the top ranked results.
    for r in ranked[:20]:
        if r._assembly is not None:
            r.nzr_probability = nzr_probability(building, r._assembly)

    return ranked
