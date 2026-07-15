"""
Layer-by-layer effective R-value / U-value calculation.

Replaces the hand-typed r_value/u_value pairs that used to sit in
assemblies.json. Those were wrong: every u_value was literally 1/r_value, i.e.
imperial R was treated as if it were metric RSI, making every assembly about
5.7x better insulated than reality. See RSI_PER_R below for the real conversion.

Method: ASHRAE parallel-path. Heat takes two routes through a framed assembly —
through the insulated cavity, and through the framing members (a thermal
bridge). Each path's total resistance is computed, converted to a U-factor, and
area-weighted by the framing factor.

    U_assembly = ff x (1 / R_framing_path) + (1 - ff) x (1 / R_cavity_path)
    R_effective = 1 / U_assembly

This is what finally makes `thermal_bridging_factor` meaningful — the old
catalog carried that field but no code ever read it.

Material values are published R/inch (imperial), the unit builders quote.
Conversion to metric happens once, here.

Sources:
  - NRCan, "Tables for Calculating Effective Thermal Resistance of Opaque
    Assemblies" (air films, method)
  - ASHRAE Handbook of Fundamentals (parallel-path)
  - Published R/inch tables (DOE / manufacturer data)
"""

from dataclasses import dataclass, field

from engine.materials import RSI_PER_R, rsi, cost_per_m2, co2_per_m2

# Surface air films, already in RSI (m2.K/W) — NRCan values.
AIR_FILM_EXTERIOR = 0.03
AIR_FILM_INTERIOR = {
    "wall":    0.12,
    "ceiling": 0.11,   # heat flow up
    "floor":   0.16,   # heat flow down
}


@dataclass
class Layer:
    """A continuous layer — spans the full area, no thermal bridge."""
    material: str
    thickness_in: float

    @property
    def rsi(self) -> float:
        return rsi(self.material, self.thickness_in)

    @property
    def cost_m2(self) -> float:
        return cost_per_m2(self.material, self.thickness_in)

    @property
    def co2_m2(self) -> float:
        return co2_per_m2(self.material, self.thickness_in)


@dataclass
class FramedCavity:
    """
    An insulated cavity interrupted by framing members. `framing_factor` is the
    fraction of area occupied by framing — 0.23 is typical for 2x6 @ 16" o.c.
    (21% studs + 4% headers per NRCan/ASHRAE).
    """
    cavity_material: str
    thickness_in: float
    framing_factor: float = 0.23
    framing_material: str = "spf_lumber"

    @property
    def rsi_cavity(self) -> float:
        return rsi(self.cavity_material, self.thickness_in)

    @property
    def rsi_framing(self) -> float:
        return rsi(self.framing_material, self.thickness_in)


@dataclass
class Assembly:
    """
    A full build-up. `orientation` picks the interior air film (wall / ceiling /
    floor). `cavity` is optional — a slab or an all-rigid assembly has none, in
    which case the calculation is a simple series sum.
    """
    name: str
    orientation: str                      # "wall" | "ceiling" | "floor"
    layers: list[Layer] = field(default_factory=list)
    cavity: FramedCavity | None = None
    exterior_film: bool = True            # False for below-grade / sub-slab

    # ── Results ─────────────────────────────────────────────────────────────
    @property
    def rsi_continuous(self) -> float:
        """Everything outside the framing plane, including air films."""
        total = sum(l.rsi for l in self.layers)
        total += AIR_FILM_INTERIOR.get(self.orientation, 0.12)
        if self.exterior_film:
            total += AIR_FILM_EXTERIOR
        return total

    @property
    def u_value(self) -> float:
        """Effective U in W/m2.K — the number the energy model consumes."""
        cont = self.rsi_continuous
        if self.cavity is None:
            return 1 / cont
        ff = self.cavity.framing_factor
        r_cav = cont + self.cavity.rsi_cavity
        r_frm = cont + self.cavity.rsi_framing
        return ff / r_frm + (1 - ff) / r_cav

    @property
    def rsi_effective(self) -> float:
        return 1 / self.u_value

    @property
    def r_effective(self) -> float:
        """Effective R in imperial — what a spec sheet would quote."""
        return self.rsi_effective / RSI_PER_R

    @property
    def r_nominal(self) -> float:
        """
        Nominal (centre-of-cavity) R, ignoring the framing bridge. This is the
        number marketing quotes; r_effective is the number the building gets.
        """
        total = self.rsi_continuous
        if self.cavity:
            total += self.cavity.rsi_cavity
        return total / RSI_PER_R

    def breakdown(self) -> dict:
        return {
            "name": self.name,
            "r_nominal": round(self.r_nominal, 1),
            "r_effective": round(self.r_effective, 1),
            "rsi_effective": round(self.rsi_effective, 2),
            "u_value": round(self.u_value, 3),
            "bridging_loss_pct": round(
                (1 - self.r_effective / self.r_nominal) * 100, 1) if self.r_nominal else 0,
        }
