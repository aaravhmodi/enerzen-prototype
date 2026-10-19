"""
Development path (flowchart Path B) in two stages.

1. screen_dev_mixes: the typology engine and 2D site plan generator. Mixes of
   the allowed catalog types that fit inside the setbacks and could be built
   within budget, before any performance optimization.
2. evaluate_dev_mixes: after the user approves scenarios, optimize building
   performance for each housing type, run the development calculations and
   rank the scenarios by the user's priorities.

Mix counts are buildings for a MURB and units otherwise; dwelling totals use
each archetype's units_per_building.
"""

import itertools
from dataclasses import dataclass, field

from engine.archetypes import ARCHETYPES, Archetype
from engine.multi_site import place_units, _all_placed
from engine.finance import rental_pro_forma
from engine.optimizer import ProjectSpec, baseline_cost, load_catalog, optimize
from engine.soft import soft_cost, soft_timeline
from engine.site import SiteSpec
from engine.location import resolve as resolve_location


@dataclass
class DevSpec:
    lot_width_m: float
    lot_depth_m: float
    street_side: str            # "N", "S", "E", "W"
    total_budget_cad: float
    location: str
    allowed_types: list         # list of archetype IDs
    target_label: str = "nzr"
    orientation: str = "S"
    front_setback_m: float = 6.0
    side_setback_m: float = 1.2
    rear_setback_m: float = 7.5
    weights: dict | None = None
    min_bedrooms: int = 0               # hard constraint: every dwelling has at least this many
    max_storeys: int | None = None      # hard constraint: no building taller than this
    excluded_mechanical_ids: list = field(default_factory=list)  # hard constraint: never use these systems
    # The lot's zoning, when known: {"zone", "permitted_types" (archetype IDs, or None when the zone's uses
    # are only in an exception's text), "min_lot_area_m2"}. See zoning_issue.
    zoning: dict | None = None


@dataclass
class DevMixResult:
    units: dict                      # {archetype_id: count}
    total_units: int
    total_cost: float
    avg_eui_kwh_m2_yr: float
    avg_carbon_kg_co2e_m2: float
    nzr_unit_count: int
    fits_on_lot: bool
    total_floor_area_m2: float
    avg_monthly_utility: float = 0.0
    mix_label: str = ""              # human-readable, e.g. "2× Garden Suite + 1× 3BHK"
    soft_cost: float = 0.0
    total_project_cost: float = 0.0
    construction_weeks: float = 0.0  # sequential factory fabrication + site work to close
    soft_timeline_weeks: float = 0.0
    lifecycle_carbon_30yr_kg_co2e_m2: float = 0.0
    lifecycle_cost_30yr: float = 0.0
    configurations: dict = field(default_factory=dict)  # {archetype_id: selected systems}
    rental: dict = field(default_factory=dict)  # finance.rental_pro_forma: market rent and MLI Select
    weighted_score: float = field(repr=False, default=0.0)


def _make_site_spec(dev: DevSpec) -> SiteSpec:
    return SiteSpec(
        lot_width_m=dev.lot_width_m,
        lot_depth_m=dev.lot_depth_m,
        street_side=dev.street_side,
        front_setback_m=dev.front_setback_m,
        side_setback_m=dev.side_setback_m,
        rear_setback_m=dev.rear_setback_m,
        solar_orientation=dev.orientation,
    )


def _arch_project_spec(arch: Archetype, dev: DevSpec) -> ProjectSpec:
    """Build a ProjectSpec from an archetype for single-unit energy simulation."""
    loc = resolve_location(dev.location) if dev.location else None
    climate_zone = loc.climate_zone if loc else "6"
    return ProjectSpec(
        typology=arch.typology,
        climate_zone=climate_zone,
        floor_area_m2=arch.floor_area_m2 / arch.units_per_building,
        storeys=arch.storeys,
        orientation=dev.orientation,
        window_to_wall_ratio=arch.window_to_wall_ratio,
        budget_per_unit=dev.total_budget_cad,  # upper bound; filtered below
        target_label=dev.target_label,
        solar_option_id="PV0",
        location=dev.location,
        num_units=arch.units_per_building,  # one dwelling's share of the building envelope
        has_ac=True,
        allow_gas=True,
        excluded_mechanical_ids=list(dev.excluded_mechanical_ids or []),
        footprint_length_m=arch.footprint_length_m,
        footprint_width_m=arch.footprint_width_m,
    )


def _mix_label(units: dict) -> str:
    parts = []
    for arch_id, count in units.items():
        if count > 0:
            parts.append(f"{count}× {ARCHETYPES[arch_id].name.split('(')[0].strip()}")
    return " + ".join(parts) if parts else "Empty"


@dataclass
class DevScenario:
    """A housing mix that fits the land, before building performance is optimized."""
    units: dict                      # {archetype_id: count of buildings / units placed}
    dwellings: int
    screening_cost: float            # cheapest-catalog hard cost: a floor, not an estimate
    total_floor_area_m2: float
    site_coverage: float             # building footprint / lot area
    mix_label: str = ""


def _dwellings(arch_id: str, count: int) -> int:
    return count * ARCHETYPES[arch_id].units_per_building


def _screening_cost_per_dwelling(arch: Archetype, dev: DevSpec) -> float:
    return baseline_cost(_arch_project_spec(arch, dev))


# Houses a garden suite can sit behind: Planning Act s.35.1 allows an additional unit in an ancillary
# building on a lot with a detached, semi-detached or row house, so never on its own or beside a MURB.
HOUSES = ("three_bhk", "townhouse")


def excluded_types(dev: DevSpec) -> list[dict]:
    """Allowed catalog types the hard constraints or the lot's zoning rule out, each with its reason."""
    out = []
    zoning = dev.zoning or {}
    permitted = zoning.get("permitted_types")
    for t in dev.allowed_types:
        arch = ARCHETYPES.get(t)
        if arch is None:
            out.append({"id": t, "reason": "Not a catalog housing type"})
        elif arch.bedrooms < (dev.min_bedrooms or 0):
            out.append({"id": t, "reason": f"{arch.name} has {arch.bedrooms} bedroom"
                                           f"{'' if arch.bedrooms == 1 else 's'}; the brief needs at least {dev.min_bedrooms}"})
        elif dev.max_storeys is not None and arch.storeys > dev.max_storeys:
            out.append({"id": t, "reason": f"{arch.name} is {arch.storeys} storeys; the brief allows at most {dev.max_storeys}"})
        elif permitted is not None and t not in permitted:
            out.append({"id": t, "reason": f"Zone {zoning.get('zone')} does not permit a {arch.name}; it would need a rezoning"})
    dropped = {e["id"] for e in out}
    if "garden_suite" in dev.allowed_types and "garden_suite" not in dropped             and not any(t in dev.allowed_types and t not in dropped for t in HOUSES):
        out.append({"id": "garden_suite", "reason": "A garden suite is an additional unit behind a house, so it needs "
                                                    "the 3-Bedroom Unit or Townhouse in the mix"})
    return out


def max_houses(dev: DevSpec) -> int | None:
    """Houses the parcel could hold if divided into lots of the zone's minimum area; None when unknown.
    An existing lot below the minimum still takes one house."""
    minimum = (dev.zoning or {}).get("min_lot_area_m2")
    return max(1, int(dev.lot_width_m * dev.lot_depth_m // minimum)) if minimum else None


def zoning_issue(dev: DevSpec, mix: dict) -> str | None:
    """Why a mix breaks the lot's zoning or the additional-unit rules; None when it doesn't."""
    houses = sum(_dwellings(t, mix.get(t, 0)) for t in HOUSES)
    suites = mix.get("garden_suite", 0)
    if suites > houses:
        return (f"{suites} garden suite{'s' if suites != 1 else ''} need{'s' if suites == 1 else ''} as many houses; "
                f"the mix has {houses}")
    cap = max_houses(dev)
    if cap is not None and houses > cap:
        return (f"{houses} houses need {houses} lots of at least {dev.zoning['min_lot_area_m2']:g} m² "
                f"(zone {dev.zoning.get('zone')}); the parcel divides into at most {cap}")
    return None


def zoning_notes(dev: DevSpec) -> list[str]:
    """The zoning rules the mixes were held to, in words."""
    zoning = dev.zoning or {}
    notes = ["At most one garden suite per house: it is an additional unit in an ancillary building (Planning Act s.35.1)."]
    if zoning.get("permitted_types") is not None:
        names = [ARCHETYPES[t].name.split("(")[0].strip() for t in zoning["permitted_types"] if t in ARCHETYPES]
        notes.insert(0, f"Zone {zoning.get('zone')} permits: {', '.join(names) or 'none of the catalog types'}.")
    elif zoning.get("zone"):
        notes.insert(0, f"Zone {zoning['zone']}'s uses are set in its exception text; confirm the housing types with the City.")
    if (cap := max_houses(dev)) is not None:
        notes.append(f"At most {cap} houses: the parcel divided into lots of the zone's {zoning['min_lot_area_m2']:g} m² "
                     "minimum, which needs a plan of subdivision or consents.")
    return notes


def screen_dev_mixes(dev: DevSpec, top_n: int = 10) -> list[DevScenario]:
    """Typology engine and 2D site plan generator (flowchart Path B, steps 3-4).

    Enumerates mixes of the allowed catalog types, keeps those that fit inside
    the setbacks and whose cheapest-catalog cost is within budget, and orders
    them by the yield and cost priorities. Types that fail the brief's hard
    constraints (see excluded_types) never enter a mix. Building performance
    is optimized later, only for the scenarios the user approves.
    """
    dropped = {e["id"] for e in excluded_types(dev)}
    valid_types = [t for t in dev.allowed_types if t in ARCHETYPES and t not in dropped]
    if not valid_types:
        return []
    site = _make_site_spec(dev)
    from engine.site import _buildable_envelope
    envelope = _buildable_envelope(site)
    buildable_area = max(0.0, (envelope.x1 - envelope.x0) * (envelope.y1 - envelope.y0))
    lot_area = dev.lot_width_m * dev.lot_depth_m

    floor_cost = {t: _screening_cost_per_dwelling(ARCHETYPES[t], dev) for t in valid_types}
    caps = {}
    for arch_id in valid_types:
        arch = ARCHETYPES[arch_id]
        footprint = arch.footprint_length_m * arch.footprint_width_m
        building_cost = floor_cost[arch_id] * arch.units_per_building
        area_cap = int(buildable_area / footprint) if footprint > 0 else 0
        budget_cap = int(dev.total_budget_cad / max(building_cost, 1))
        caps[arch_id] = max(0, min(area_cap, budget_cap, 12))

    scenarios: list[DevScenario] = []
    for counts in itertools.product(*(range(caps[t] + 1) for t in valid_types)):
        mix = {t: c for t, c in zip(valid_types, counts)}
        if sum(counts) == 0:
            continue
        cost = sum(floor_cost[t] * _dwellings(t, c) for t, c in mix.items())
        if cost > dev.total_budget_cad or zoning_issue(dev, mix):
            continue
        if not _all_placed(place_units(mix, site), mix):
            continue
        footprint = sum(ARCHETYPES[t].footprint_length_m * ARCHETYPES[t].footprint_width_m * c for t, c in mix.items())
        scenarios.append(DevScenario(
            units=mix,
            dwellings=sum(_dwellings(t, c) for t, c in mix.items()),
            screening_cost=round(cost),
            total_floor_area_m2=round(sum(
                ARCHETYPES[t].floor_area_m2 / ARCHETYPES[t].units_per_building * _dwellings(t, c)
                for t, c in mix.items()), 1),
            site_coverage=round(footprint / lot_area, 3) if lot_area else 0.0,
            mix_label=_mix_label(mix),
        ))
    if not scenarios:
        return []

    weights = _normalized_weights(dev.weights)
    yields = [s.dwellings for s in scenarios]
    costs = [s.screening_cost for s in scenarios]
    yield_cost = (weights["yield"] + weights["cost"]) or 1.0
    scenarios.sort(key=lambda s: (
        (weights["yield"] * (1 - _norm(s.dwellings, yields)) + weights["cost"] * _norm(s.screening_cost, costs)) / yield_cost,
        -s.dwellings,
        s.screening_cost,
    ))
    return scenarios[:top_n]


def best_configurations(dev: DevSpec, mixes: list[dict]) -> dict:
    """The top-ranked configuration for each eligible housing type in the
    mixes (None when nothing passes the gate), one optimizer run per type."""
    dropped = {e["id"] for e in excluded_types(dev)}
    types = sorted({t for mix in mixes for t, c in mix.items() if c > 0 and t in ARCHETYPES and t not in dropped})
    best: dict[str, object] = {}
    for arch_id in types:
        results = optimize(_arch_project_spec(ARCHETYPES[arch_id], dev))
        best[arch_id] = results[0] if results else None
    return best


def evaluate_dev_mixes(dev: DevSpec, mixes: list[dict], best: dict | None = None) -> tuple[list[DevMixResult], list[dict]]:
    """Building performance optimization, development calculations and
    ranking (flowchart Path B, steps 5-7) for the approved scenarios.

    Each housing type is optimized once (pass `best` from
    best_configurations to reuse a run); a mix's totals scale by its dwelling
    count. Returns (ranked feasible results, rejected mixes with a reason).
    """
    site = _make_site_spec(dev)
    dropped = {e["id"]: e["reason"] for e in excluded_types(dev)}
    if best is None:
        best = best_configurations(dev, mixes)

    feasible: list[DevMixResult] = []
    rejected: list[dict] = []
    for mix in mixes:
        mix = {t: c for t, c in mix.items() if c > 0 and t in ARCHETYPES}
        label = _mix_label(mix)
        failed = [dropped[t] for t in mix if t in dropped]
        if failed:
            rejected.append({"units": mix, "mix_label": label, "reason": "; ".join(failed)})
            continue
        if issue := zoning_issue(dev, mix):
            rejected.append({"units": mix, "mix_label": label, "reason": issue})
            continue
        missing = [ARCHETYPES[t].name for t in mix if best.get(t) is None]
        if missing:
            rejected.append({"units": mix, "mix_label": label,
                             "reason": f"No configuration of {', '.join(missing)} meets the "
                                       f"{dev.target_label.upper()} target within the budget"})
            continue
        if not _all_placed(place_units(mix, site), mix):
            rejected.append({"units": mix, "mix_label": label, "reason": "Does not fit inside the setbacks"})
            continue
        dwellings = {t: _dwellings(t, c) for t, c in mix.items()}
        total_dwellings = sum(dwellings.values())
        area = {t: ARCHETYPES[t].floor_area_m2 / ARCHETYPES[t].units_per_building * n for t, n in dwellings.items()}
        total_area = sum(area.values())
        hard = sum(best[t].construction_cost * n for t, n in dwellings.items())
        if hard > dev.total_budget_cad:
            rejected.append({"units": mix, "mix_label": label,
                             "reason": f"Optimized hard cost ${hard:,.0f} exceeds the ${dev.total_budget_cad:,.0f} budget"})
            continue

        def area_avg(field_name: str) -> float:
            return round(sum(getattr(best[t], field_name) * a for t, a in area.items()) / total_area, 1)

        by_bedrooms = {}
        for t, n in dwellings.items():
            by_bedrooms[ARCHETYPES[t].bedrooms] = by_bedrooms.get(ARCHETYPES[t].bedrooms, 0) + n
        largest = max(mix, key=lambda t: (ARCHETYPES[t].storeys, ARCHETYPES[t].units_per_building))
        arch = ARCHETYPES[largest]
        timeline = soft_timeline(arch.typology, arch.storeys,
                                 arch.footprint_length_m * arch.footprint_width_m, total_dwellings)
        feasible.append(DevMixResult(
            units=mix,
            total_units=total_dwellings,
            total_cost=round(hard),
            avg_eui_kwh_m2_yr=area_avg("eui_kwh_m2_yr"),
            avg_carbon_kg_co2e_m2=area_avg("embodied_carbon_kg_co2e_m2"),
            nzr_unit_count=sum(n for t, n in dwellings.items() if best[t].nzr_compliant),
            fits_on_lot=True,
            total_floor_area_m2=round(total_area, 1),
            avg_monthly_utility=round(sum(best[t].avg_monthly_utility * n for t, n in dwellings.items()) / total_dwellings),
            mix_label=label,
            soft_cost=soft_cost(hard),
            total_project_cost=round(hard + soft_cost(hard)),
            construction_weeks=round(sum(best[t].construction_weeks * n for t, n in dwellings.items()), 1),
            soft_timeline_weeks=timeline.total_weeks,
            lifecycle_carbon_30yr_kg_co2e_m2=area_avg("lifecycle_carbon_30yr_kg_co2e_m2"),
            lifecycle_cost_30yr=round(sum(best[t].lifecycle_cost_30yr * n for t, n in dwellings.items())),
            configurations={t: f"{best[t].wall_id} wall · {best[t].roof_id} roof · {best[t].mechanical_id}" for t in mix},
            rental=rental_pro_forma(by_bedrooms, round(hard + soft_cost(hard)), area_avg("eui_kwh_m2_yr"),
                                    load_catalog()["benchmarks"]["eui_kwh_m2_yr"]["code_built_new"]),
        ))

    weights = _normalized_weights(dev.weights)
    if feasible:
        yields = [r.total_units for r in feasible]
        costs = [r.total_cost for r in feasible]
        energies = [r.avg_eui_kwh_m2_yr for r in feasible]
        carbons = [r.avg_carbon_kg_co2e_m2 for r in feasible]
        for r in feasible:
            r.weighted_score = (
                weights["yield"] * (1 - _norm(r.total_units, yields))
                + weights["cost"] * _norm(r.total_cost, costs)
                + weights["energy"] * _norm(r.avg_eui_kwh_m2_yr, energies)
                + weights["carbon"] * _norm(r.avg_carbon_kg_co2e_m2, carbons)
            )
        feasible.sort(key=lambda r: (r.weighted_score, -r.total_units, r.avg_eui_kwh_m2_yr, -r.nzr_unit_count))
    return feasible, rejected


def optimize_dev_mix(dev: DevSpec, top_n: int = 10) -> list[DevMixResult]:
    """Both stages in one call: screen scenarios, then optimize and rank them."""
    scenarios = screen_dev_mixes(dev, top_n=max(top_n, 20))
    feasible, _ = evaluate_dev_mixes(dev, [s.units for s in scenarios])
    return feasible[:top_n]


def _normalized_weights(weights: dict | None) -> dict:
    keys = ("yield", "cost", "energy", "carbon")
    raw = {k: max(0.0, float((weights or {}).get(k, 0.0))) for k in keys}
    total = sum(raw.values())
    if total == 0:
        return {"yield": 1.0, "cost": 0.0, "energy": 0.0, "carbon": 0.0}
    return {k: v / total for k, v in raw.items()}


def _norm(value: float, values: list[float]) -> float:
    lo, hi = min(values), max(values)
    return (value - lo) / (hi - lo) if hi > lo else 0.0
