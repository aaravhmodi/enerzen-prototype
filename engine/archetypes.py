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
    ),
    "three_bhk": Archetype(
        id="three_bhk",
        name="3-Bedroom Unit",
        floor_area_m2=163.0,
        storeys=2,
        footprint_length_m=10.0,
        footprint_width_m=8.0,
        typology="single_family",
    ),
    "murb": Archetype(
        id="murb",
        name="MURB (6-storey, 4 units/floor)",
        floor_area_m2=65.0 * 24,   # 24 dwelling units total
        storeys=6,
        footprint_length_m=20.0,
        footprint_width_m=15.0,
        typology="murb",
        units_per_building=24,
    ),
    "townhouse": Archetype(
        id="townhouse",
        name="Townhouse (3 BR, attached)",
        floor_area_m2=150.0,
        storeys=2,
        footprint_length_m=6.0,   # per unit (units attach side-by-side)
        footprint_width_m=12.0,
        typology="townhouse",
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
        }
        for a in ARCHETYPES.values()
    ]
