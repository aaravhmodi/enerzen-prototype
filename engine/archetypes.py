"""
Fixed dimensional and energy-simulation parameters for each EnerZen building archetype.
These correspond to the physical DWG designs: Garden Suite, 3BHK, MURB, Townhouse.
"""

from dataclasses import dataclass, field


@dataclass
class Archetype:
    id: str
    name: str
    floor_area_m2: float       # per dwelling unit
    storeys: int
    footprint_length_m: float  # E-W extent of the building/unit on the lot
    footprint_width_m: float   # N-S extent
    typology: str              # matches optimizer.ProjectSpec.typology
    units_per_building: int = 1  # >1 for MURB (whole building placed once)
    bedrooms: int = 1          # per dwelling; the guaranteed minimum for mixed-unit types
    window_to_wall_ratio: float = 0.20
    orientation: str = "S"


ARCHETYPES: dict[str, Archetype] = {
    "garden_suite": Archetype(
        id="garden_suite",
        name="Garden Suite (1 BR)",
        floor_area_m2=46.0,
        storeys=1,
        footprint_length_m=7.0,
        footprint_width_m=6.5,
        typology="single_family",
        bedrooms=1,
    ),
    "three_bhk": Archetype(
        id="three_bhk",
        name="3-Bedroom Unit",
        floor_area_m2=163.0,
        storeys=2,
        footprint_length_m=10.0,
        footprint_width_m=8.0,
        typology="single_family",
        bedrooms=3,
    ),
    # MURB.pdf / ENERZEN_PLAN_G+4.dwg: ground + 4 floors, 4 units per floor,
    # a square plan scaling to about 19 x 18 m, 2-bed units of 695 ft2 (65 m2).
    # MURB.pdf mixes 1- and 2-bed units, so 1 bedroom is the guaranteed minimum.
    "murb": Archetype(
        id="murb",
        name="MURB (5-storey, 4 units/floor)",
        floor_area_m2=65.0 * 20,   # 20 dwelling units total
        storeys=5,
        footprint_length_m=19.0,
        footprint_width_m=18.0,
        typology="murb",
        units_per_building=20,
        bedrooms=1,
    ),
    "townhouse": Archetype(
        id="townhouse",
        name="Townhouse (3 BR, attached)",
        floor_area_m2=150.0,
        storeys=2,
        footprint_length_m=6.0,   # per unit (units attach side-by-side)
        footprint_width_m=12.0,
        typology="townhouse",
        bedrooms=3,
    ),
}


def archetype_list() -> list[dict]:
    return [
        {
            "id": a.id,
            "name": a.name,
            "floor_area_m2": a.floor_area_m2,
            "storeys": a.storeys,
            "footprint_length_m": a.footprint_length_m,
            "footprint_width_m": a.footprint_width_m,
            "typology": a.typology,
            "units_per_building": a.units_per_building,
            "bedrooms": a.bedrooms,
        }
        for a in ARCHETYPES.values()
    ]
