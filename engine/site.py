"""
Deterministic site-plan placement engine.

Given a building footprint (from `ProjectSpec`, already fixed by the
envelope optimizer) and a lot (`SiteSpec`), computes where the building and
driveway sit on the lot and how well the fixed orientation captures passive
solar gain.

This module never changes `ProjectSpec.orientation` — that value already
drove the energy simulation upstream (`engine/simulator.py`), so the
building's compass-facing is a given, not something to re-optimize here.
What this module *does* optimize is placement within the buildable envelope
(lot minus setbacks) and it flags when the lot's shape can't cleanly fit the
footprint.

Solar-score heuristic (NREL/DOE passive-solar guidance, LEED orientation
credit): main glazing facing true south captures the most winter solar
gain; within ~30 degrees of south still captures the large majority of
optimal gain, falling off toward zero at due north. Modeled here as a
cosine falloff from due south (180 degrees), which gives 1.0 at south,
~0.93 at +/-30 degrees, 0.5 at due east/west, 0.0 at due north.
"""

import math
from dataclasses import dataclass, field

COMPASS_DEGREES = {"N": 0, "E": 90, "S": 180, "W": 270}
_SOUTH_DEG = COMPASS_DEGREES["S"]


@dataclass
class SiteSpec:
    lot_width_m: float          # east-west extent
    lot_depth_m: float          # north-south extent
    street_side: str            # "N", "S", "E", "W" -- lot edge that fronts the street
    front_setback_m: float = 6.0
    side_setback_m: float = 1.2
    rear_setback_m: float = 7.5


@dataclass
class BuildableEnvelope:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class SiteLayout:
    building_x_m: float
    building_y_m: float
    building_w_m: float   # east-west extent as placed
    building_h_m: float   # north-south extent as placed
    driveway_points_m: list
    orientation: str
    solar_score: float
    fits_on_lot: bool
    setbacks_ok: bool
    notes: list = field(default_factory=list)


def _angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def solar_score_for_orientation(orientation: str) -> float:
    """1.0 = main glazing faces true south, 0.0 = faces true north."""
    if orientation not in COMPASS_DEGREES:
        raise ValueError(f"orientation must be one of {list(COMPASS_DEGREES)}, got {orientation!r}")
    diff = _angle_diff(COMPASS_DEGREES[orientation], _SOUTH_DEG)
    return round(0.5 + 0.5 * math.cos(math.radians(diff)), 3)


def _buildable_envelope(site: SiteSpec) -> BuildableEnvelope:
    """Lot minus setbacks, in a coordinate system where x=0 is the west edge
    and y=0 is the north edge (both increasing east/south respectively)."""
    if site.street_side in ("N", "S"):
        x0, x1 = site.side_setback_m, site.lot_width_m - site.side_setback_m
        if site.street_side == "N":
            y0, y1 = site.front_setback_m, site.lot_depth_m - site.rear_setback_m
        else:
            y0, y1 = site.rear_setback_m, site.lot_depth_m - site.front_setback_m
    elif site.street_side in ("E", "W"):
        y0, y1 = site.side_setback_m, site.lot_depth_m - site.side_setback_m
        if site.street_side == "W":
            x0, x1 = site.front_setback_m, site.lot_width_m - site.rear_setback_m
        else:
            x0, x1 = site.rear_setback_m, site.lot_width_m - site.front_setback_m
    else:
        raise ValueError(f"street_side must be one of N/S/E/W, got {site.street_side!r}")
    return BuildableEnvelope(x0, y0, x1, y1)


def place_building(spec, site: SiteSpec) -> SiteLayout:
    """`spec` is an `engine.optimizer.ProjectSpec` (or anything with the same
    `orientation`, `footprint_length_m`, `footprint_width_m`, `floor_area_m2`
    attributes)."""
    notes = []
    length = spec.footprint_length_m or math.sqrt(spec.floor_area_m2)
    width = spec.footprint_width_m or math.sqrt(spec.floor_area_m2)
    long_dim, short_dim = max(length, width), min(length, width)

    # Longer dimension runs along the facade that faces the fixed orientation
    # (more glazing area on the solar-facing wall), per passive-solar siting
    # practice of orienting a rectangular footprint's broad side to the sun.
    if spec.orientation in ("N", "S"):
        building_w, building_h = long_dim, short_dim
    else:
        building_w, building_h = short_dim, long_dim

    envelope = _buildable_envelope(site)
    fits_on_lot = building_w <= envelope.width and building_h <= envelope.height
    if not fits_on_lot:
        notes.append(
            "Footprint does not fit within setbacks for this lot/street-side "
            "combination while keeping the specified orientation; placement "
            "below is centered but overflows the buildable envelope."
        )

    building_x = envelope.x0 + (envelope.width - building_w) / 2
    building_y = envelope.y0 + (envelope.height - building_h) / 2
    setbacks_ok = fits_on_lot

    driveway_points = _driveway_polygon(site, envelope, building_x, building_y, building_w, building_h)

    return SiteLayout(
        building_x_m=building_x,
        building_y_m=building_y,
        building_w_m=building_w,
        building_h_m=building_h,
        driveway_points_m=driveway_points,
        orientation=spec.orientation,
        solar_score=solar_score_for_orientation(spec.orientation),
        fits_on_lot=fits_on_lot,
        setbacks_ok=setbacks_ok,
        notes=notes,
    )


def _driveway_polygon(site: SiteSpec, envelope: BuildableEnvelope,
                       bx: float, by: float, bw: float, bh: float) -> list:
    """A simple driveway strip from the street edge to the building, offset
    to one side so it doesn't cross in front of the solar-facing facade."""
    driveway_width = 3.0
    if site.street_side == "N":
        x = min(bx + bw - driveway_width, site.lot_width_m - site.side_setback_m - driveway_width)
        x = max(x, site.side_setback_m)
        return [(x, 0), (x + driveway_width, 0), (x + driveway_width, by), (x, by)]
    if site.street_side == "S":
        x = min(bx + bw - driveway_width, site.lot_width_m - site.side_setback_m - driveway_width)
        x = max(x, site.side_setback_m)
        return [(x, by + bh), (x + driveway_width, by + bh),
                (x + driveway_width, site.lot_depth_m), (x, site.lot_depth_m)]
    if site.street_side == "W":
        y = min(by + bh - driveway_width, site.lot_depth_m - site.side_setback_m - driveway_width)
        y = max(y, site.side_setback_m)
        return [(0, y), (0, y + driveway_width), (bx, y + driveway_width), (bx, y)]
    # "E"
    y = min(by + bh - driveway_width, site.lot_depth_m - site.side_setback_m - driveway_width)
    y = max(y, site.side_setback_m)
    return [(bx + bw, y), (bx + bw, y + driveway_width), (site.lot_width_m, y + driveway_width), (site.lot_width_m, y)]


_SCALE_PX_PER_M = 8
_MARGIN_PX = 40


def site_plan_svg(layout: SiteLayout, spec, site: SiteSpec) -> str:
    """Hand-built SVG (no rendering dependency) of the lot, setbacks,
    building footprint, north arrow, and driveway."""
    w_px = site.lot_width_m * _SCALE_PX_PER_M + 2 * _MARGIN_PX
    h_px = site.lot_depth_m * _SCALE_PX_PER_M + 2 * _MARGIN_PX

    def px(x_m, y_m):
        return (_MARGIN_PX + x_m * _SCALE_PX_PER_M, _MARGIN_PX + y_m * _SCALE_PX_PER_M)

    envelope = _buildable_envelope(site)
    e_x0, e_y0 = px(envelope.x0, envelope.y0)
    e_x1, e_y1 = px(envelope.x1, envelope.y1)
    b_x0, b_y0 = px(layout.building_x_m, layout.building_y_m)
    b_x1, b_y1 = px(layout.building_x_m + layout.building_w_m,
                     layout.building_y_m + layout.building_h_m)

    drive_pts = " ".join(f"{px(x, y)[0]:.1f},{px(x, y)[1]:.1f}" for x, y in layout.driveway_points_m)

    solar_edge = {
        "N": (b_x0, b_y0, b_x1, b_y0),
        "S": (b_x0, b_y1, b_x1, b_y1),
        "E": (b_x1, b_y0, b_x1, b_y1),
        "W": (b_x0, b_y0, b_x0, b_y1),
    }[layout.orientation]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w_px:.0f}" height="{h_px:.0f}" '
        f'viewBox="0 0 {w_px:.0f} {h_px:.0f}" font-family="sans-serif">',
        f'<rect x="{_MARGIN_PX}" y="{_MARGIN_PX}" width="{site.lot_width_m * _SCALE_PX_PER_M:.1f}" '
        f'height="{site.lot_depth_m * _SCALE_PX_PER_M:.1f}" fill="#eef6ea" stroke="#4a7c3c" stroke-width="2"/>',
        f'<rect x="{e_x0:.1f}" y="{e_y0:.1f}" width="{e_x1 - e_x0:.1f}" height="{e_y1 - e_y0:.1f}" '
        f'fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="6,4"/>',
        f'<polygon points="{drive_pts}" fill="#c9ccd1" stroke="#6b7280" stroke-width="1"/>',
        f'<rect x="{b_x0:.1f}" y="{b_y0:.1f}" width="{b_x1 - b_x0:.1f}" height="{b_y1 - b_y0:.1f}" '
        f'fill="#f4e6c8" stroke="#8a6d3b" stroke-width="2"/>',
        f'<line x1="{solar_edge[0]:.1f}" y1="{solar_edge[1]:.1f}" x2="{solar_edge[2]:.1f}" y2="{solar_edge[3]:.1f}" '
        f'stroke="#e08e2b" stroke-width="5"/>',
        f'<text x="{w_px - _MARGIN_PX:.0f}" y="{_MARGIN_PX - 12:.0f}" text-anchor="end" font-size="12" fill="#374151">'
        f'N ↑ street: {site.street_side} | solar score: {layout.solar_score:.2f}</text>',
    ]
    if layout.notes:
        parts.append(
            f'<text x="{_MARGIN_PX}" y="{h_px - 10:.0f}" font-size="11" fill="#b91c1c">'
            f'{layout.notes[0]}</text>'
        )
    parts.append('</svg>')
    return "".join(parts)
