"""
Construction cost and schedule estimation.

Unit rates are based on EnerZen's panelized assembly cost model.
Stick-frame baselines (W1, W2) use BCIS-equivalent Canadian labor rates.
"""

SURFACE_RATIOS = {
    1: {"wall": 1.8, "roof": 1.05, "floor": 1.0},
    2: {"wall": 1.4, "roof": 0.55, "floor": 0.52},
    3: {"wall": 1.2, "roof": 0.40, "floor": 0.38},
}

# Base costs beyond envelope (foundation, framing structure, finishes, etc.)
# per m² of floor area — held constant across configs so comparison is valid
BASE_COST_PER_M2 = 1200  # CAD

LABOUR_RATE_PER_HR = 75  # CAD, blended rate for panelized installation crew


def estimate_cost(spec, wall, roof, floor_c, window, mech) -> dict:
    ratios = SURFACE_RATIOS.get(spec.storeys, SURFACE_RATIOS[2])
    wall_area   = spec.floor_area_m2 * ratios["wall"]
    roof_area   = spec.floor_area_m2 * ratios["roof"]
    floor_area  = spec.floor_area_m2 * ratios["floor"]
    window_area = wall_area * spec.window_to_wall_ratio
    opaque_wall = wall_area - window_area

    material_cost = (
        opaque_wall * wall["cost_per_m2"] +
        roof_area   * roof["cost_per_m2"] +
        floor_area  * floor_c["cost_per_m2"] +
        window_area * window["cost_per_m2"] +
        mech["cost"]
    )

    labour_hours = (
        opaque_wall * wall["install_hours_per_m2"] +
        roof_area   * roof["install_hours_per_m2"] +
        floor_area  * floor_c["install_hours_per_m2"]
    )
    labour_cost = labour_hours * LABOUR_RATE_PER_HR

    envelope_cost = material_cost + labour_cost
    base_cost = spec.floor_area_m2 * BASE_COST_PER_M2

    total = envelope_cost + base_cost

    return {
        "material_cost":     round(material_cost, 0),
        "labour_cost":       round(labour_cost, 0),
        "envelope_cost":     round(envelope_cost, 0),
        "base_cost":         round(base_cost, 0),
        "total_per_unit":    round(total, 0),
        "cost_per_m2":       round(total / spec.floor_area_m2, 0),
        "labour_hours":      round(labour_hours, 1),
    }


def estimate_schedule(spec, wall, roof, floor_c) -> dict:
    """
    Estimate weeks to envelope close and panel counts.
    Panelized assemblies (EnerZen IDs W3+, R2+, F2) install significantly faster.
    """
    ratios = SURFACE_RATIOS.get(spec.storeys, SURFACE_RATIOS[2])
    wall_area  = spec.floor_area_m2 * ratios["wall"]
    roof_area  = spec.floor_area_m2 * ratios["roof"]
    floor_area = spec.floor_area_m2 * ratios["floor"]
    window_area = wall_area * spec.window_to_wall_ratio
    opaque_wall = wall_area - window_area

    labour_hours = (
        opaque_wall * wall["install_hours_per_m2"] +
        roof_area   * roof["install_hours_per_m2"] +
        floor_area  * floor_c["install_hours_per_m2"]
    )

    # 4-person crew, 40hr week
    crew_size = 4
    weeks = labour_hours / (crew_size * 40)

    # Panel counts (approximate 2.4m x 3.0m standard panel)
    panel_area = 2.4 * 3.0
    wall_panels  = max(1, round(opaque_wall / panel_area))
    roof_panels  = max(1, round(roof_area / panel_area))
    floor_panels = max(1, round(floor_area / panel_area))

    return {
        "weeks_to_envelope_close": round(weeks, 1),
        "total_labour_hours": round(labour_hours, 1),
        "panel_counts": {
            "wall_panels":  wall_panels,
            "roof_panels":  roof_panels,
            "floor_panels": floor_panels,
            "total_panels": wall_panels + roof_panels + floor_panels,
            "crane_lifts":  wall_panels + roof_panels + floor_panels,
        }
    }
