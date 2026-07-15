"""
Construction cost and schedule estimation.

Phase 5: the old $1200/m2 blanket "base cost" is retired. Every line is now
itemized so it can be challenged and refined individually:

  envelope       walls/roof/floor from material layers + install labour
  connections    panel-to-panel joints, sealing, fasteners (~10% of envelope)
  partitions     interior walls, from the same materials table
  ext. finishes  trim, flashings, soffits/fascia (cladding is already a layer)
  mechanical     catalog price scaled by floor area; optional AC for furnaces
  fit-out        kitchens/baths/flooring/paint + plumbing/electrical services
  contingency    on everything above

Rates are Canadian 2025 defaults — replace with EnerZen procurement data.
"""

from engine.materials import cost_per_m2 as mat_cost

SURFACE_RATIOS = {
    1: {"wall": 1.8, "roof": 1.05, "floor": 1.0},
    2: {"wall": 1.4, "roof": 0.55, "floor": 0.52},
    3: {"wall": 1.2, "roof": 0.40, "floor": 0.38},
}

LABOUR_RATE_PER_HR = 75      # CAD, blended panelized installation crew

CONNECTION_RATE = 0.10       # panel joints/sealing/fasteners, share of envelope
CONTINGENCY_RATE = 0.08

# Interior partitions: wall area per m2 of floor (typical residential layouts),
# built as 2x4 studs @ 16" o.c. (16% framing) with gypsum both sides + labour.
PARTITION_M2_PER_FLOOR_M2 = 0.9
PARTITION_LABOUR_HR_M2 = 0.4

EXT_TRIM_PER_WALL_M2 = 15    # trim/flashings/soffits/fascia, CAD per m2 wall

# Fit-out and services: kitchens, baths, flooring, paint, plumbing, electrical.
# Explicit and challengeable — the residue of the old $1200 blanket.
FITOUT_PER_M2 = 650

# Mechanical scales with conditioned area (fan/duct/plant sizing), reference
# 150 m2, square-root law (capacity, not linear cost).
MECH_REF_M2 = 150
AC_BASE_COST = 3000          # central AC for furnace systems; heat pumps cool inherently
AC_PER_M2 = 10


def _partition_cost_m2() -> float:
    materials = (2 * mat_cost("gypsum", 0.5)
                 + mat_cost("spf_lumber", 3.5) * 0.16)
    return materials + PARTITION_LABOUR_HR_M2 * LABOUR_RATE_PER_HR


def mechanical_cost(spec, mech) -> float:
    scaled = mech["cost"] * (spec.floor_area_m2 / MECH_REF_M2) ** 0.5
    if getattr(spec, "has_ac", True) and mech["type"] == "gas":
        scaled += AC_BASE_COST + AC_PER_M2 * spec.floor_area_m2
    return scaled


def estimate_cost(spec, env, window, mech) -> dict:
    """
    env: assemblies.EnvelopeCombo — carries the wall/roof/floor Assembly objects
    whose .cost_m2 is derived from the material layers (engine.materials).
    window, mech: catalog dicts (still list-priced products).
    """
    ratios = SURFACE_RATIOS.get(spec.storeys, SURFACE_RATIOS[2])
    wall_area   = spec.floor_area_m2 * ratios["wall"]
    roof_area   = spec.floor_area_m2 * ratios["roof"]
    floor_area  = spec.floor_area_m2 * ratios["floor"]
    window_area = wall_area * spec.window_to_wall_ratio
    opaque_wall = wall_area - window_area

    material_cost = (
        opaque_wall * env.wall.cost_m2 +
        roof_area   * env.roof.cost_m2 +
        floor_area  * env.floor.cost_m2 +
        window_area * window["cost_per_m2"]
    )

    labour_hours = (
        opaque_wall * env.wall_hours_per_m2 +
        roof_area   * env.roof_hours_per_m2 +
        floor_area  * env.floor_hours_per_m2
    )
    labour_cost = labour_hours * LABOUR_RATE_PER_HR

    envelope_cost = material_cost + labour_cost
    connections   = envelope_cost * CONNECTION_RATE
    partitions    = spec.floor_area_m2 * PARTITION_M2_PER_FLOOR_M2 * _partition_cost_m2()
    ext_finishes  = wall_area * EXT_TRIM_PER_WALL_M2
    mech_cost     = mechanical_cost(spec, mech)
    fitout        = spec.floor_area_m2 * FITOUT_PER_M2

    subtotal    = envelope_cost + connections + partitions + ext_finishes + mech_cost + fitout
    contingency = subtotal * CONTINGENCY_RATE
    total       = subtotal + contingency

    return {
        "material_cost":     round(material_cost, 0),
        "labour_cost":       round(labour_cost, 0),
        "envelope_cost":     round(envelope_cost, 0),
        "connections_cost":  round(connections, 0),
        "partitions_cost":   round(partitions, 0),
        "ext_finishes_cost": round(ext_finishes, 0),
        "mechanical_cost":   round(mech_cost, 0),
        "fitout_cost":       round(fitout, 0),
        "contingency_cost":  round(contingency, 0),
        "total_per_unit":    round(total, 0),
        "cost_per_m2":       round(total / spec.floor_area_m2, 0),
        "labour_hours":      round(labour_hours, 1),
    }


def estimate_schedule(spec, env) -> dict:
    """
    Estimate weeks to envelope close (fabrication + install) and panel counts.
    Panelized/cassette assemblies install significantly faster (lower hours/m2).
    """
    ratios = SURFACE_RATIOS.get(spec.storeys, SURFACE_RATIOS[2])
    wall_area  = spec.floor_area_m2 * ratios["wall"]
    roof_area  = spec.floor_area_m2 * ratios["roof"]
    floor_area = spec.floor_area_m2 * ratios["floor"]
    window_area = wall_area * spec.window_to_wall_ratio
    opaque_wall = wall_area - window_area

    labour_hours = (
        opaque_wall * env.wall_hours_per_m2 +
        roof_area   * env.roof_hours_per_m2 +
        floor_area  * env.floor_hours_per_m2
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
