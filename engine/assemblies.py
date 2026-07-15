"""
The six parametric assemblies: 2 walls, 2 roofs, 2 floors.

Each is a builder that returns a rvalue.Assembly for a given set of swept
parameters (exterior/over-deck insulation thickness; roof cavity depth from the
snow-driven joist). R-value, cost, and embodied carbon all fall out of the
layer build-up via engine.materials — nothing is hand-typed per assembly.

`variants()` enumerates the coarse thickness sweep the optimizer searches.

NOTE: these build-ups are reasonable industry defaults, not EnerZen's real
panel specs. Swap the layer lists when the real schedules are available; every
downstream number updates automatically.
"""

from dataclasses import dataclass
from typing import Callable

from engine.rvalue import Assembly, Layer, FramedCavity

# Coarse thickness sweeps (inches). Kept small so the optimizer stays fast.
WALL_EXT_RIGID_IN = [0, 2, 4]      # exterior continuous mineral wool
ROOF_DECK_RIGID_IN = [0, 2, 4]     # rigid above the roof deck
FLOOR_RIGID_IN = [2, 4]            # under-slab / under-floor rigid (Phase 4 refines slab)


# ── Wall builders ────────────────────────────────────────────────────────────

def _wall_2x6(ext_rigid_in: float) -> Assembly:
    layers = [Layer("vinyl_siding", 1), Layer("air_gap", 0.75)]
    if ext_rigid_in:
        layers.append(Layer("mineral_wool_board", ext_rigid_in))
    layers += [Layer("osb", 0.5), Layer("gypsum", 0.5)]
    return Assembly("2x6 wood frame + ext. mineral wool", "wall", layers,
                    FramedCavity("mineral_wool_batt", 5.5, framing_factor=0.23))


def _wall_2x8(ext_rigid_in: float) -> Assembly:
    layers = [Layer("vinyl_siding", 1), Layer("air_gap", 0.75)]
    if ext_rigid_in:
        layers.append(Layer("mineral_wool_board", ext_rigid_in))
    layers += [Layer("osb", 0.5), Layer("gypsum", 0.5)]
    return Assembly("2x8 wood frame + ext. mineral wool", "wall", layers,
                    FramedCavity("mineral_wool_batt", 7.25, framing_factor=0.21))


# ── Roof builders (cavity depth = joist depth from snow tier) ─────────────────

def _roof_cellulose(joist_depth_in: float, deck_rigid_in: float) -> Assembly:
    layers = [Layer("asphalt_shingle", 0.25), Layer("osb", 0.5)]
    if deck_rigid_in:
        layers.append(Layer("polyiso", deck_rigid_in))
    layers += [Layer("osb", 0.5), Layer("gypsum", 0.5)]
    # cavity fills the joist; blown cellulose to ~90% of depth
    return Assembly("Vented cassette — blown cellulose", "ceiling", layers,
                    FramedCavity("cellulose_blown", joist_depth_in * 0.9, framing_factor=0.11))


def _roof_mineral(joist_depth_in: float, deck_rigid_in: float) -> Assembly:
    layers = [Layer("asphalt_shingle", 0.25), Layer("osb", 0.5)]
    if deck_rigid_in:
        layers.append(Layer("polyiso", deck_rigid_in))
    layers += [Layer("osb", 0.5), Layer("gypsum", 0.5)]
    return Assembly("Unvented cassette — mineral wool", "ceiling", layers,
                    FramedCavity("mineral_wool_batt", joist_depth_in * 0.95, framing_factor=0.11))


# ── Floor builders ───────────────────────────────────────────────────────────
# Slab-on-grade concrete + sub-slab rigid is detailed in Phase 4 (foundation).
# Here the floor's thermal layer is the rigid under it.

def _floor_slab(rigid_in: float) -> Assembly:
    return Assembly("Slab on grade + sub-slab rigid", "floor",
                    [Layer("concrete", 4), Layer("eps", rigid_in)],
                    exterior_film=False)


def _floor_cassette(rigid_in: float) -> Assembly:
    layers = [Layer("osb", 0.75)]
    return Assembly("Raised floor cassette", "floor", layers,
                    FramedCavity("mineral_wool_batt", 9.25, framing_factor=0.10),
                    exterior_film=False)


@dataclass
class AssemblyOption:
    id: str
    name: str
    kind: str                       # "wall" | "roof" | "floor"
    build: Callable                 # signature depends on kind
    sweep: list                     # thickness options to search
    install_hours_per_m2: float     # fabrication/install labour (panelized = low)


# install_hours_per_m2: EnerZen panelized/cassette assemblies install fast;
# site-built slab is slower. Defaults — refine with real crew data.
WALLS = [
    AssemblyOption("WA1", "2x6 frame + ext. mineral wool", "wall", _wall_2x6, WALL_EXT_RIGID_IN, 0.50),
    AssemblyOption("WA2", "2x8 frame + ext. mineral wool", "wall", _wall_2x8, WALL_EXT_RIGID_IN, 0.55),
]
ROOFS = [
    AssemblyOption("RA1", "Vented cassette — cellulose", "roof", _roof_cellulose, ROOF_DECK_RIGID_IN, 0.45),
    AssemblyOption("RA2", "Unvented cassette — mineral wool", "roof", _roof_mineral, ROOF_DECK_RIGID_IN, 0.50),
]
FLOORS = [
    AssemblyOption("FA1", "Slab on grade", "floor", _floor_slab, FLOOR_RIGID_IN, 0.80),
    AssemblyOption("FA2", "Raised floor cassette", "floor", _floor_cassette, [0], 0.40),
]
