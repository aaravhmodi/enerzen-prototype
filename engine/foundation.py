"""
Slab-on-grade foundation model (Phase 4).

Concrete slab over a sub-slab rigid EPS strip around the perimeter — the zone
where slab heat loss actually concentrates. The strip is 1.5 m wide; its
thickness is swept by the optimizer (100/150/200/250 mm). The slab core loses
heat through deep ground, which is far more resistive, so insulating the core
buys little — this matches Part 9 practice.

Heat loss model (parallel paths, area-weighted like rvalue.py):

    U_strip = 1 / (film + concrete + EPS + shallow-soil RSI)
    U_core  = 1 / (film + concrete + deep-soil  RSI)
    U_slab  = (f x U_strip + (1-f) x U_core) x GROUND_TEMP_FACTOR

where f is the strip's share of the footprint. GROUND_TEMP_FACTOR scales for
ground being warmer than outdoor air over the heating season, so the degree-day
model can use U_slab against air HDD unchanged.

Cost/carbon (per m2 of footprint) come from engine.materials plus a thickened
edge / frost wall: perimeter x frost depth (from the location's soil data) of
300 mm concrete. Deeper frost lines in the north mean more concrete — the
location now drives foundation cost.
"""

from math import sqrt

from engine.materials import r_per_in, cost_per_m2, co2_per_m2, RSI_PER_R

EPS_MM_OPTIONS = [100, 150, 200, 250]
STRIP_WIDTH_M = 1.5
SLAB_MM = 100            # 4" slab
EDGE_WALL_MM = 300       # thickened edge / frost wall
GROUND_TEMP_FACTOR = 0.6  # ground delta-T ~60% of air delta-T (heating season)
RSI_SOIL_EDGE = 0.5      # shallow soil path near the perimeter
RSI_SOIL_CORE = 2.0      # deep ground under the slab core
RSI_FILM_FLOOR = 0.16    # interior still-air film, floor (NRCan)
MM_PER_IN = 25.4


class SlabOnGrade:
    """Duck-types rvalue.Assembly: exposes u_value, cost_m2, co2_m2, breakdown()."""

    kind = "floor"

    def __init__(self, eps_mm: float, floor_area_m2: float, storeys: int,
                 frost_depth_m: float = 1.2):
        footprint = floor_area_m2 / max(1, storeys)
        perimeter = 4 * sqrt(footprint)          # square plan, consistent with cost.py ratios
        strip_area = min(perimeter * STRIP_WIDTH_M, footprint)
        f = strip_area / footprint

        slab_in = SLAB_MM / MM_PER_IN
        eps_in = eps_mm / MM_PER_IN
        rsi_concrete = r_per_in("concrete") * slab_in * RSI_PER_R
        rsi_eps = r_per_in("eps") * eps_in * RSI_PER_R

        u_strip = 1 / (RSI_FILM_FLOOR + rsi_concrete + rsi_eps + RSI_SOIL_EDGE)
        u_core = 1 / (RSI_FILM_FLOOR + rsi_concrete + RSI_SOIL_CORE)
        u_raw = f * u_strip + (1 - f) * u_core
        self.u_value = round(u_raw * GROUND_TEMP_FACTOR, 4)
        self.r_effective = round(5.678 / self.u_value, 1)

        edge_in = EDGE_WALL_MM / MM_PER_IN
        edge_area = perimeter * frost_depth_m    # frost wall, both storeys share it
        slab_cost = cost_per_m2("concrete", slab_in)
        eps_cost = cost_per_m2("eps", eps_in) * f
        edge_cost = cost_per_m2("concrete", edge_in) * edge_area / footprint
        self.cost_m2 = round(slab_cost + eps_cost + edge_cost, 2)

        slab_co2 = co2_per_m2("concrete", slab_in)
        eps_co2 = co2_per_m2("eps", eps_in) * f
        edge_co2 = co2_per_m2("concrete", edge_in) * edge_area / footprint
        self.co2_m2 = round(slab_co2 + eps_co2 + edge_co2, 2)

        self.name = f"Slab on grade — {eps_mm:.0f} mm sub-slab EPS ({STRIP_WIDTH_M} m perimeter strip)"
        self._detail = {
            "eps_mm": eps_mm,
            "strip_fraction": round(f, 3),
            "perimeter_m": round(perimeter, 1),
            "frost_depth_m": frost_depth_m,
            "u_strip": round(u_strip, 3),
            "u_core": round(u_core, 3),
            "cost_split_m2": {"slab": round(slab_cost, 2), "eps": round(eps_cost, 2),
                              "frost_wall": round(edge_cost, 2)},
        }

    def breakdown(self) -> dict:
        return {
            "name": self.name, "kind": self.kind,
            "u_value": self.u_value, "r_effective": self.r_effective,
            "cost_m2": self.cost_m2, "co2_m2": self.co2_m2,
            **self._detail,
        }


GRADE_BEAM_MM = 250


class RaisedFloorFoundation:
    """Wraps the raised-cassette Assembly and adds the foundation it sits on
    (perimeter grade beam to frost depth), so slab vs cassette compare fairly —
    neither floats in mid-air for free."""

    kind = "floor"

    def __init__(self, asm, floor_area_m2: float, storeys: int,
                 frost_depth_m: float = 1.2):
        footprint = floor_area_m2 / max(1, storeys)
        perimeter = 4 * sqrt(footprint)
        beam_in = GRADE_BEAM_MM / MM_PER_IN
        beam_area = perimeter * frost_depth_m
        add_cost = cost_per_m2("concrete", beam_in) * beam_area / footprint
        add_co2 = co2_per_m2("concrete", beam_in) * beam_area / footprint

        self._asm = asm
        self.u_value = asm.u_value
        self.cost_m2 = round(asm.cost_m2 + add_cost, 2)
        self.co2_m2 = round(asm.co2_m2 + add_co2, 2)
        self.name = asm.name + " + grade-beam foundation"

    def breakdown(self) -> dict:
        b = dict(self._asm.breakdown())
        b["name"] = self.name
        b["cost_m2"] = self.cost_m2
        b["co2_m2"] = self.co2_m2
        return b
