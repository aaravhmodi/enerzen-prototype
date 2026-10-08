"""
Feasibility assessment behind the nine-section report (flowchart "feasibility
report"), shared by both paths.

The status is decided from explicit checks, never assumed:

- FEASIBLE: every check passes and no constraint was relaxed.
- FEASIBLE WITH MODIFICATIONS: every check passes, but only after a named
  constraint was relaxed.
- FURTHER STUDY REQUIRED: any check failed or was not made (no parcel or
  zoning check, a site-fit failure, a data gap).

Zoning is never checked yet: no Pickering parcel is selected and no
municipal rule set is evaluated, so the zoning check is always "not checked"
and the status is FURTHER STUDY REQUIRED until one is.
"""

from dataclasses import dataclass, field

from engine.finance import lifecycle_cost

FEASIBLE = "FEASIBLE"
FEASIBLE_WITH_MODIFICATIONS = "FEASIBLE WITH MODIFICATIONS"
FURTHER_STUDY = "FURTHER STUDY REQUIRED"

PASS, FAIL, NOT_CHECKED = "pass", "fail", "not_checked"

SECTIONS = (
    "Executive feasibility",
    "Recommended solution",
    "Capital cost (Class D)",
    "Timeline",
    "Energy",
    "Carbon",
    "Lifecycle economics",
    "Priority achievement",
    "Next steps",
)


@dataclass
class Check:
    name: str
    status: str   # PASS, FAIL or NOT_CHECKED
    detail: str


@dataclass
class Assessment:
    status: str
    reasons: list[str]
    checks: list[Check]
    relaxed: list[str] = field(default_factory=list)


def assess(checks: list[Check], relaxed: list[str] | None = None) -> Assessment:
    relaxed = list(relaxed or [])
    open_items = [c for c in checks if c.status != PASS]
    if open_items:
        reasons = [f"{c.name}: {'failed' if c.status == FAIL else 'not checked'}. {c.detail}" for c in open_items]
        return Assessment(FURTHER_STUDY, reasons, checks, relaxed)
    if relaxed:
        return Assessment(FEASIBLE_WITH_MODIFICATIONS,
                          [f"Passes only after relaxing: {r}" for r in relaxed], checks, relaxed)
    return Assessment(FEASIBLE, ["Every hard constraint and gate passes."], checks, relaxed)


def zoning_check(location_name: str) -> Check:
    """Always not checked until a parcel is selected and its rules evaluated."""
    if location_name.startswith("Pickering"):
        detail = ("No Pickering parcel is selected, so zoning, permitted uses, height and setbacks are not "
                  "checked. Lot dimensions and setbacks are scenario assumptions.")
    else:
        detail = ("No parcel is selected and no zoning rules are evaluated. Lot dimensions and setbacks are "
                  "scenario assumptions.")
    return Check("Zoning and permitted use", NOT_CHECKED, detail)


def gate_check(gate: dict) -> Check:
    return Check("Budget and performance gate", PASS if gate["passed"] else FAIL,
                 f"{gate['passed']:,} of {gate['evaluated']:,} configurations passed "
                 f"({gate['over_budget']:,} over budget, {gate['missed_target']:,} missed the target).")


def benchmark_comparison(result, floor_area_m2: float, catalog: dict, rates: dict) -> dict:
    """The recommended configuration against a code-built new home of the same
    area, using catalog["benchmarks"]: capital cost per m2 (conventional new
    build), site EUI (code-built new) and embodied carbon per m2.

    The benchmark home's energy is priced at this configuration's own
    variable rate (its energy bill less fixed charges, per gross kWh), so the
    comparison isolates consumption, not fuel choice. Lifecycle cost uses the
    same 30-year present-value method as the optimizer (engine/finance.py)."""
    bench = catalog["benchmarks"]
    bench_cost_m2 = bench["cost_per_m2"]["conventional_new_build"]
    bench_eui = bench["eui_kwh_m2_yr"]["code_built_new"]
    bench_carbon = bench["embodied_carbon_kg_co2e_m2"]["conventional_new_build"]

    gross_kwh = result.energy.total_energy_kwh_yr if result.energy else result.eui_kwh_m2_yr * floor_area_m2
    gas = result.utility and result.utility.get("annual_gas_cost", 0) > 0
    fixed = 12 * (rates.get("electricity_fixed_monthly_cad", 0) + (rates.get("natural_gas_fixed_monthly_cad", 0) if gas else 0))
    variable = max(0.0, result.annual_utility_cost - fixed)
    billed_kwh = gross_kwh - result.pv_generation_kwh_yr
    rate = variable / billed_kwh if billed_kwh > 0 and variable > 0 else rates["electricity_cad_per_kwh"]

    bench_kwh = bench_eui * floor_area_m2
    bench_capex = bench_cost_m2 * floor_area_m2
    bench_utility = round(fixed + bench_kwh * rate)
    bench_lcc = lifecycle_cost(bench_capex, bench_utility, years=30)["total"]
    return {
        "benchmark_cost_per_m2": bench_cost_m2,
        "cost_per_m2": round(result.construction_cost / floor_area_m2),
        "benchmark_eui": bench_eui,
        "benchmark_embodied_kg_m2": bench_carbon,
        "energy_saving_kwh_yr": round(bench_kwh - (gross_kwh - result.pv_generation_kwh_yr)),
        "benchmark_annual_utility": bench_utility,
        "utility_saving_yr": round(bench_utility - result.annual_utility_cost),
        "benchmark_lifecycle_cost_30yr": round(bench_lcc),
        "lifecycle_saving_30yr": round(bench_lcc - result.lifecycle_cost_30yr),
        "rate_cad_per_kwh": round(rate, 3),
        "sources": {
            "cost": bench["cost_per_m2"]["_source"],
            "eui": bench["eui_kwh_m2_yr"]["_source"],
            "carbon": bench["embodied_carbon_kg_co2e_m2"]["_source"],
        },
    }


def objective_ranks(chosen, feasible: list, objectives: list[tuple]) -> list[dict]:
    """Where the chosen option ranks among the feasible set on each objective.
    objectives: (label, weight key, attribute, higher_is_better, formatter).
    Rank 1 is best; ties share the better rank."""
    rows = []
    for label, key, attr, higher, fmt in objectives:
        value = getattr(chosen, attr)
        better = sum(1 for r in feasible if (getattr(r, attr) > value if higher else getattr(r, attr) < value))
        rows.append({"objective": label, "key": key, "rank": better + 1, "of": len(feasible),
                     "value": value, "display": fmt(value)})
    return rows


def next_steps(*, location, checks: list[Check], target_label: str, surrogate_verified: bool,
               dwellings: int, part3: bool, has_pv: bool) -> tuple[list[str], list[str]]:
    """Required next steps, driven by what the engine did not check, and
    optional enhancements listed separately."""
    steps = []
    by_name = {c.name: c for c in checks}
    zoning = by_name.get("Zoning and permitted use")
    if zoning and zoning.status != PASS:
        municipality = location.name.split(" (")[0]
        steps.append(f"Municipal pre-consultation with {municipality} to confirm zoning, permitted uses, height, "
                     "setbacks and parking for the selected parcel.")
    site = by_name.get("Site fit")
    if site and site.status == NOT_CHECKED:
        steps.append("Supply the lot dimensions and setbacks so the engine can check site fit.")
    elif site and site.status == FAIL:
        steps.append(f"Resolve the site-fit failure: {site.detail}")
    steps.append(f"Geotechnical investigation: bearing capacity ({location.allowable_bearing_kpa:g} kPa) and "
                 f"frost depth ({location.frost_depth_m:g} m) are regional defaults.")
    steps.append(f"Structural engineer to confirm roof and floor framing for the ground snow load "
                 f"(Ss {location.ss:g} kPa); the snow-to-joist mapping is preliminary.")
    if target_label != "code" and not surrogate_verified:
        steps.append("Confirm the energy target with a compliance model (HOT2000 for Part 9, whole-building "
                     "simulation for Part 3); the engine's degree-day model is a screening estimate.")
    if part3:
        steps.append("Engage Part 3 consultants (architect, structural, mechanical, fire) for a building over "
                     "3 storeys or 600 m2.")
    if dwellings > 10:
        steps.append("Prepare a site plan approval application (more than 10 dwellings are subject to site plan "
                     "control).")
    steps.append("Replace catalog cost and carbon defaults with EnerZen procurement data before quotation.")

    enhancements = []
    if not has_pv:
        enhancements.append("Test rooftop PV to lower net energy and operating cost.")
    enhancements.append("Resilience (hours of safety in an outage) once a method is chosen.")
    enhancements.append("3D massing and elevations once the unit designs are final.")
    return steps, enhancements
