"""
Envelope surface areas for one dwelling — the single source used by the
energy, cost, schedule and carbon models so they always agree.

- 1–3 storey homes keep the typical residential ratios to floor area (walls
  and roof), with the slab taken from the footprint when one is given.
- Multi-unit buildings, and any building taller than the ratio table, are
  measured from their geometry instead: walls are the footprint perimeter
  times the storey count times the storey height, and the roof and slab are
  the footprint. A dwelling in a multi-unit building takes an equal share of
  the whole building's envelope (`num_units` dwellings share one footprint).
"""

import math

STOREY_HEIGHT_M = 2.7

# Envelope surface area ratios relative to floor area (typical residential forms).
SURFACE_RATIOS = {
    1: {"wall": 1.8, "roof": 1.05, "floor": 1.0},   # single storey
    2: {"wall": 1.4, "roof": 0.55, "floor": 0.52},  # two storey
    3: {"wall": 1.2, "roof": 0.40, "floor": 0.38},  # three storey
}


def surface_areas(spec) -> dict:
    """Wall, roof, slab, window and opaque-wall areas (m2) for one dwelling.

    `spec` is a ProjectSpec or BuildingSpec: floor_area_m2 (per dwelling),
    storeys, window_to_wall_ratio, and optionally footprint_length_m,
    footprint_width_m (the whole building) and num_units.
    """
    length = getattr(spec, "footprint_length_m", None)
    width = getattr(spec, "footprint_width_m", None)
    units = max(1, int(getattr(spec, "num_units", 1) or 1))
    storeys = spec.storeys

    if units > 1 or storeys not in SURFACE_RATIOS:
        if not (length and width):
            side = math.sqrt(spec.floor_area_m2 * units / storeys)
            length = width = side
        wall = 2 * (length + width) * storeys * STOREY_HEIGHT_M / units
        roof = floor = length * width / units
    else:
        ratios = SURFACE_RATIOS[storeys]
        wall = spec.floor_area_m2 * ratios["wall"]
        roof = spec.floor_area_m2 * ratios["roof"]
        floor = length * width if length and width else spec.floor_area_m2 * ratios["floor"]

    window = wall * spec.window_to_wall_ratio
    return {"wall": wall, "roof": roof, "floor": floor, "window": window, "opaque_wall": wall - window}
