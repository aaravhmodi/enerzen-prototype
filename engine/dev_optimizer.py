"""
Development mix optimizer for EnerZen.

Given a lot, budget, location, and a set of allowed archetype types,
enumerates feasible unit-mix configurations (combinations of archetypes
that fit on the lot and within budget), simulates energy for each,
and returns the top mixes ranked by total units, energy performance,
and NZR compliance count.
"""

import itertools
import math
from dataclasses import dataclass, field
from typing import Optional

from engine.archetypes import ARCHETYPES, Archetype
from engine.multi_site import fits_on_lot, place_units, _all_placed
from engine.optimizer import ProjectSpec, optimize
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


def _make_site_spec(dev: DevSpec) -> SiteSpec:
    return SiteSpec(
        lot_width_m=dev.lot_width_m,
        lot_depth_m=dev.lot_depth_m,
        street_side=dev.street_side,
        front_setback_m=dev.front_setback_m,
        side_setback_m=dev.side_setback_m,
        rear_setback_m=dev.rear_setback_m,
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
        num_units=1,
        has_ac=True,
        allow_gas=True,
        footprint_length_m=arch.footprint_length_m,
        footprint_width_m=arch.footprint_width_m,
    )


def _mix_label(units: dict) -> str:
    parts = []
    for arch_id, count in units.items():
        if count > 0:
            parts.append(f"{count}× {ARCHETYPES[arch_id].name.split('(')[0].strip()}")
    return " + ".join(parts) if parts else "Empty"


def optimize_dev_mix(dev: DevSpec, top_n: int = 10) -> list[DevMixResult]:
    """
    Enumerate feasible unit-mix configurations and return the top `top_n` ranked results.

    Strategy:
    1. For each allowed archetype, run the single-unit optimizer to get best energy/cost.
    2. Compute buildable envelope area to cap max units per archetype.
    3. Enumerate all (archetype × count) combinations up to the per-type cap.
    4. Filter: fits on lot + total cost ≤ budget + at least 1 unit.
    5. Rank: total_units DESC, avg_eui ASC, nzr_count DESC.
    """
    if not dev.allowed_types:
        return []

    valid_types = [t for t in dev.allowed_types if t in ARCHETYPES]
    if not valid_types:
        return []

    site = _make_site_spec(dev)

    # --- Step 1: cache best energy/cost result per archetype ---
    arch_results: dict[str, dict] = {}
    for arch_id in valid_types:
        arch = ARCHETYPES[arch_id]
        spec = _arch_project_spec(arch, dev)
        results = optimize(spec)
        if results:
            best = results[0]
            arch_results[arch_id] = {
                "cost": best.construction_cost,
                "eui": best.eui_kwh_m2_yr,
                "carbon": best.embodied_carbon_kg_co2e_m2,
                "nzr": best.nzr_compliant,
                "monthly_utility": best.avg_monthly_utility,
                "floor_area": arch.floor_area_m2 / arch.units_per_building,
            }
        else:
            # No feasible config for this archetype — skip it
            arch_results[arch_id] = None  # type: ignore

    feasible_types = [t for t in valid_types if arch_results[t] is not None]
    if not feasible_types:
        return []

    # --- Step 2: compute max units per archetype from lot area ---
    from engine.site import _buildable_envelope
    envelope = _buildable_envelope(site)
    buildable_area = max(0.0, (envelope.x1 - envelope.x0) * (envelope.y1 - envelope.y0))

    max_per_type: dict[str, int] = {}
    for arch_id in feasible_types:
        arch = ARCHETYPES[arch_id]
        footprint_area = arch.footprint_length_m * arch.footprint_width_m
        if footprint_area <= 0:
            max_per_type[arch_id] = 0
            continue
        area_cap = int(buildable_area / footprint_area)
        budget_cap = int(dev.total_budget_cad / max(arch_results[arch_id]["cost"], 1))
        max_per_type[arch_id] = max(0, min(area_cap, budget_cap, 12))

    # --- Step 3: enumerate all combinations ---
    ranges = [range(0, max_per_type.get(t, 0) + 1) for t in feasible_types]

    candidates: list[DevMixResult] = []
    for counts in itertools.product(*ranges):
        mix = {t: c for t, c in zip(feasible_types, counts)}
        total_units = sum(mix.values())
        if total_units == 0:
            continue

        # Cost check
        total_cost = sum(
            arch_results[arch_id]["cost"] * count
            for arch_id, count in mix.items()
        )
        if total_cost > dev.total_budget_cad:
            continue

        # Lot-fit check
        placements = place_units(mix, site)
        if not _all_placed(placements, mix):
            continue

        # Aggregate energy metrics (weighted by floor area)
        total_area = 0.0
        area_eui = 0.0
        area_carbon = 0.0
        nzr_count = 0
        monthly_util = 0.0
        for arch_id, count in mix.items():
            if count == 0:
                continue
            r = arch_results[arch_id]
            fa = r["floor_area"] * count
            total_area += fa
            area_eui += r["eui"] * fa
            area_carbon += r["carbon"] * fa
            nzr_count += count if r["nzr"] else 0
            monthly_util += r["monthly_utility"] * count

        avg_eui = area_eui / total_area if total_area > 0 else 0.0
        avg_carbon = area_carbon / total_area if total_area > 0 else 0.0

        candidates.append(DevMixResult(
            units=mix,
            total_units=total_units,
            total_cost=total_cost,
            avg_eui_kwh_m2_yr=round(avg_eui, 1),
            avg_carbon_kg_co2e_m2=round(avg_carbon, 1),
            nzr_unit_count=nzr_count,
            fits_on_lot=True,
            total_floor_area_m2=round(total_area, 1),
            avg_monthly_utility=round(monthly_util / total_units, 0),
            mix_label=_mix_label(mix),
        ))

    # --- Step 5: rank ---
    candidates.sort(key=lambda r: (
        -r.total_units,
        r.avg_eui_kwh_m2_yr,
        -r.nzr_unit_count,
    ))

    return candidates[:top_n]
