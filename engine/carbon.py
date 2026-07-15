"""
Embodied and operational carbon calculations.

Embodied carbon uses EPD-based values stored in the assembly catalog.
Operational carbon uses Ontario grid emission factor (kgCO2e/kWh).
"""

# Ontario grid intensity: 73.8 gCO2e/kWh in 2024 (up 25% YoY as gas generation
# grew) — The Atmospheric Fund, Ontario Emissions Factors 2024.
ONTARIO_GRID_FACTOR = 0.074  # kgCO2e/kWh
GAS_FACTOR          = 0.19   # kgCO2e/kWh equivalent for natural gas combustion


# Surface area ratios relative to floor area (mirrors simulator.py)
SURFACE_RATIOS = {
    1: {"wall": 1.8, "roof": 1.05, "floor": 1.0},
    2: {"wall": 1.4, "roof": 0.55, "floor": 0.52},
    3: {"wall": 1.2, "roof": 0.40, "floor": 0.38},
}


def calculate_carbon(spec, env, window, mech, energy_result) -> dict:
    ratios = SURFACE_RATIOS.get(spec.storeys, SURFACE_RATIOS[2])
    wall_area   = spec.floor_area_m2 * ratios["wall"]
    roof_area   = spec.floor_area_m2 * ratios["roof"]
    floor_area  = spec.floor_area_m2 * ratios["floor"]
    window_area = wall_area * spec.window_to_wall_ratio
    opaque_wall = wall_area - window_area

    wall_c  = opaque_wall * env.wall.co2_m2
    roof_c  = roof_area   * env.roof.co2_m2
    floor_c_ = floor_area * env.floor.co2_m2
    window_c = window_area * window["embodied_carbon_kg_co2e_m2"]
    mech_c   = mech["embodied_carbon_kg_co2e"]
    embodied = wall_c + roof_c + floor_c_ + window_c + mech_c

    grid_factor = GAS_FACTOR if mech["type"] == "gas" else ONTARIO_GRID_FACTOR
    operational_annual = energy_result.total_energy_kwh_yr * grid_factor
    operational_60yr   = operational_annual * 60

    total_embodied_per_m2 = embodied / spec.floor_area_m2
    total_60yr_per_m2     = (embodied + operational_60yr) / spec.floor_area_m2

    return {
        "embodied_kg_co2e":       round(embodied, 1),
        "embodied_per_m2":        round(total_embodied_per_m2, 1),
        "operational_annual":     round(operational_annual, 1),
        "operational_60yr":       round(operational_60yr, 1),
        "total_60yr":             round(embodied + operational_60yr, 1),
        "total_per_m2":           round(total_embodied_per_m2, 1),
        "total_60yr_per_m2":      round(total_60yr_per_m2, 1),
        "carbon_hotspot": max(
            [("Wall", wall_c), ("Roof", roof_c), ("Floor", floor_c_),
             ("Windows", window_c), ("Mechanical", mech_c)],
            key=lambda x: x[1]
        )[0]
    }
