"""
Embodied and operational carbon calculations.

Embodied carbon uses EPD-based values stored in the assembly catalog.
Operational carbon uses Ontario grid emission factor (kgCO2e/kWh).
"""

from engine.cost import PARTITION_M2_PER_FLOOR_M2
from engine.geometry import surface_areas
from engine.materials import co2_per_m2

# Ontario grid intensity: 73.8 gCO2e/kWh in 2024 (up 25% YoY as gas generation
# grew) — The Atmospheric Fund, Ontario Emissions Factors 2024.
ONTARIO_GRID_FACTOR = 0.074  # kgCO2e/kWh
GAS_FACTOR          = 0.19   # kgCO2e/kWh equivalent for natural gas combustion


# Interior elements counted by published Part 9 studies (BfCA EMBARC: interior
# walls, floors, ceilings), built from the same material table as the envelope.
# Interior partition: 2x4 studs at 16" o.c. (16% of area), 1/2" gypsum both sides.
PARTITION_KG_PER_M2 = 2 * co2_per_m2("gypsum", 0.5) + co2_per_m2("spf_lumber", 3.5) * 0.16
# Intermediate floor: 2x10 joists at 16" o.c. (9.4% of area), 3/4" OSB subfloor,
# 1/2" gypsum ceiling below.
INTERMEDIATE_FLOOR_KG_PER_M2 = (co2_per_m2("spf_lumber", 9.25) * 0.094 + co2_per_m2("osb", 0.75)
                                + co2_per_m2("gypsum", 0.5))


def intermediate_floor_area(spec, slab_area: float) -> float:
    """Floor plates above the slab carried by one dwelling: (storeys - 1) times
    its share of the footprint."""
    return max(spec.storeys - 1, 0) * slab_area


def calculate_carbon(spec, env, window, mech, energy_result) -> dict:
    areas = surface_areas(spec)
    roof_area, floor_area = areas["roof"], areas["floor"]
    window_area, opaque_wall = areas["window"], areas["opaque_wall"]

    wall_c  = opaque_wall * env.wall.co2_m2
    roof_c  = roof_area   * env.roof.co2_m2
    floor_c_ = floor_area * env.floor.co2_m2
    window_c = window_area * window["embodied_carbon_kg_co2e_m2"]
    mech_c   = mech["embodied_carbon_kg_co2e"]
    partition_c = spec.floor_area_m2 * PARTITION_M2_PER_FLOOR_M2 * PARTITION_KG_PER_M2
    intermediate_c = intermediate_floor_area(spec, floor_area) * INTERMEDIATE_FLOOR_KG_PER_M2
    embodied = wall_c + roof_c + floor_c_ + window_c + mech_c + partition_c + intermediate_c

    # Only heating burns gas in a gas home; base loads and cooling are always
    # electric. (Previously the gas factor was applied to ALL energy, inflating
    # gas homes' operational carbon by ~2x.)
    heating_kwh = energy_result.heating_demand_kwh_yr
    other_kwh = energy_result.total_energy_kwh_yr - heating_kwh
    if mech["type"] == "gas":
        operational_annual = heating_kwh * GAS_FACTOR + other_kwh * ONTARIO_GRID_FACTOR
    else:
        operational_annual = energy_result.total_energy_kwh_yr * ONTARIO_GRID_FACTOR
    operational_30yr = operational_annual * 30   # aligned with lifecycle horizon

    total_embodied_per_m2 = embodied / spec.floor_area_m2
    total_30yr_per_m2     = (embodied + operational_30yr) / spec.floor_area_m2

    return {
        "embodied_kg_co2e":       round(embodied, 1),
        "embodied_per_m2":        round(total_embodied_per_m2, 1),
        "operational_annual":     round(operational_annual, 1),
        "operational_30yr":       round(operational_30yr, 1),
        "total_30yr":             round(embodied + operational_30yr, 1),
        "total_per_m2":           round(total_embodied_per_m2, 1),
        "total_30yr_per_m2":      round(total_30yr_per_m2, 1),
        "carbon_hotspot": max(
            [("Wall", wall_c), ("Roof", roof_c), ("Floor", floor_c_),
             ("Windows", window_c), ("Mechanical", mech_c),
             ("Interior walls", partition_c), ("Intermediate floors", intermediate_c)],
            key=lambda x: x[1]
        )[0]
    }
