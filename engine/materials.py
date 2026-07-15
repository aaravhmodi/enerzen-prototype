"""
Single source of truth for material properties.

Every material carries three per-unit properties so that thermal performance,
cost, and embodied carbon all derive from ONE place — change a build-up and all
three outputs move together, consistently.

    r_per_in        R-value per inch (imperial, hr.ft2.F/Btu)
    cost_per_m2_in  installed material cost, CAD per m2 per inch of thickness
    co2_per_m2_in   embodied carbon, kgCO2e per m2 per inch (cradle-to-gate)

For sheet goods quoted per area (drywall, cladding, membrane) the "_in" is the
nominal layer thickness used in the build-up; cost/carbon are still expressed
per-inch so one formula covers everything.

Sources:
  - r_per_in: DOE / manufacturer R-value tables (see rvalue.py history)
  - cost/carbon: published EPD ranges + Canadian material cost surveys, 2025.
    These are DEFAULTS to be replaced with EnerZen's real procurement data.
"""

RSI_PER_R = 0.17611  # RSI = R / 5.678

MATERIALS = {
    # material            r/in   $/m2/in  kgCO2e/m2/in
    "mineral_wool_batt":  (4.0,   2.20,   1.45),
    "mineral_wool_board": (4.2,   5.50,   1.65),   # exterior continuous
    "fiberglass_batt":    (3.5,   1.40,   0.85),
    "cellulose_blown":    (3.6,   1.10,   0.35),   # recycled, low carbon
    "eps":                (4.2,   3.40,   3.10),
    "xps":                (5.0,   6.20,  12.50),   # high-GWP blowing agents
    "polyiso":            (5.6,   5.00,   4.60),
    "spray_foam_closed":  (6.0,  11.00,   9.80),
    "spf_lumber":         (1.25,  6.00,   0.90),   # framing (biogenic-adjusted)
    "osb":                (1.25,  4.20,   3.40),
    "plywood":            (1.25,  6.50,   2.90),
    "gypsum":             (0.90,  3.10,   2.60),
    "concrete":           (0.08, 18.00,  55.00),   # per inch; very high carbon
    "air_gap":            (1.00,  0.00,   0.00),
    "vinyl_siding":       (0.61,  9.00,   4.80),
    "fiber_cement":       (0.15, 16.00,   7.50),
    "wood_siding":        (0.81, 22.00,   2.40),
    "asphalt_shingle":    (0.44, 12.00,   6.20),
    "membrane_roof":      (0.10, 20.00,   5.50),
}


def _prop(material: str, idx: int) -> float:
    if material not in MATERIALS:
        raise KeyError(f"unknown material {material!r}; add it to MATERIALS")
    return MATERIALS[material][idx]


def r_per_in(material: str) -> float:
    return _prop(material, 0)


def rsi(material: str, thickness_in: float) -> float:
    return r_per_in(material) * thickness_in * RSI_PER_R


def cost_per_m2(material: str, thickness_in: float) -> float:
    return _prop(material, 1) * thickness_in


def co2_per_m2(material: str, thickness_in: float) -> float:
    return _prop(material, 2) * thickness_in
