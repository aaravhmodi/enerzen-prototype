"""
Generates .h2k variant files by editing XML attributes on the base
single-family template (data/hot2000/base_single_family.h2k), so the batch
runner can calculate each variant without going through the HOT2000 "New
House" wizard per design point.

XML locations were found by building the base file through the wizard,
setting a value through the UI (e.g. wall RSI = 3.32), saving, and grepping
the saved file for that value. See scripts/hot2000/HANDOFF.md for the
session that did this. Locations used here:

  Wall RSI          House/Components/Wall/Construction/Type/@rValue
                     (there are 2 <Wall> elements in the base — "Main floor"
                     and "Second level" — both must be set together for a
                     single-storey-equivalent wall assembly swap)
  Ceiling RSI        House/Components/Ceiling/Construction/CeilingType/@rValue
  Window RSI + SHGC  House/Components/Wall/Components/Window/Construction/Type/@rValue
                     and .../Window/@shgc (8 <Window> elements in the base —
                     4 per wall x 2 walls)
  Slab insulation    House/Components/Slab/Floor/Construction/AddedToSlab/@rValue
                     (HOT2000's simplified "top of slab" model — does not
                     match engine/foundation.py's perimeter-strip EPS model
                     exactly; treat as an approximation until a better
                     mapping is found)
  Furnace efficiency House/HeatingCooling/Type1/Furnace/Specifications/@efficiency
  Furnace fuel       House/HeatingCooling/Type1/Furnace/Equipment/EnergySource/@code
                     (2 = Natural gas in the base file; other codes not yet
                     catalogued — check Schemas/H2k Schema.xsd or the Code
                     Editor in HOT2000 before using other fuels)
  Blower door ACH    House/NaturalAirInfiltration/Specifications/BlowerTest/@airChangeRate
                     (base file's test pressure is "10 Pa", code="1" — NOT
                     the standard 50 Pa that engine.optimizer's ach50 means.
                     Whoever wires this up needs to either change Pressure
                     to the 50 Pa code or convert engine's ach50 to an
                     equivalent 10 Pa value before writing it here — not
                     resolved in this session, sweep_infiltration() raises
                     until it is.)

`nominalInsulation` attributes are left untouched (set equal to rValue is
a reasonable simplification if HOT2000 complains, but in testing HOT2000
accepted rValue changes alone without HOT2000 rejecting the file).
"""

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

BASE_TEMPLATE = Path(__file__).parent.parent.parent / "data" / "hot2000" / "base_single_family.h2k"


@dataclass
class VariantParams:
    wall_rsi: Optional[float] = None
    ceiling_rsi: Optional[float] = None
    window_rsi: Optional[float] = None     # RSI = 1/U; H2K stores window R as RSI too (see base: 0.3049 for U~3.28)
    window_shgc: Optional[float] = None
    slab_rsi: Optional[float] = None
    furnace_efficiency_pct: Optional[float] = None


def generate_variant(params: VariantParams, out_path: Path, base_path: Path = BASE_TEMPLATE) -> Path:
    tree = ET.parse(base_path)
    root = tree.getroot()
    house = root.find("House")

    if params.wall_rsi is not None:
        for wall in house.findall("Components/Wall"):
            type_el = wall.find("Construction/Type")
            type_el.set("rValue", f"{params.wall_rsi:.4f}")

    if params.ceiling_rsi is not None:
        ceiling_type = house.find("Components/Ceiling/Construction/CeilingType")
        ceiling_type.set("rValue", f"{params.ceiling_rsi:.4f}")
        ceiling_type.set("nominalInsulation", f"{params.ceiling_rsi:.4f}")

    if params.window_rsi is not None or params.window_shgc is not None:
        for window in house.findall("Components/Wall/Components/Window"):
            if params.window_shgc is not None:
                window.set("shgc", f"{params.window_shgc:.4f}")
            if params.window_rsi is not None:
                type_el = window.find("Construction/Type")
                type_el.set("rValue", f"{params.window_rsi:.4f}")

    if params.slab_rsi is not None:
        added = house.find("Components/Slab/Floor/Construction/AddedToSlab")
        added.set("rValue", f"{params.slab_rsi:.4f}")

    if params.furnace_efficiency_pct is not None:
        specs = house.find("HeatingCooling/Type1/Furnace/Specifications")
        specs.set("efficiency", f"{params.furnace_efficiency_pct:.1f}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="UTF-8", xml_declaration=True)
    return out_path


if __name__ == "__main__":
    from engine.assemblies import WALLS, ROOFS

    scratch = Path(__file__).parent.parent.parent / "data" / "hot2000" / "_variant_test.h2k"
    wa1_4in = WALLS[0].build(4)   # WA1 with 4" exterior rigid — should be a noticeably better wall than the base's 0"
    ra1_4in = ROOFS[0].build(10, 4)

    params = VariantParams(
        wall_rsi=wa1_4in.rsi_effective,
        ceiling_rsi=ra1_4in.rsi_effective,
    )
    generate_variant(params, scratch)
    print(f"wrote {scratch} with wall_rsi={wa1_4in.rsi_effective:.2f}, ceiling_rsi={ra1_4in.rsi_effective:.2f}")
