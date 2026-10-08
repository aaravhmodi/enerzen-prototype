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
    solar_orientation: str = "S"


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


def buildable_envelope(site: SiteSpec) -> BuildableEnvelope:
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


# Keep private-name alias for internal callers and multi_site.py
_buildable_envelope = buildable_envelope


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


def site_plan_svg(layout: SiteLayout, spec, site: SiteSpec) -> str:
    """SVG site plan for a single building: lot, street, buildable envelope,
    driveway and footprint with its solar face, plus a key and legend."""
    from engine import svg_kit

    sheet = svg_kit.PlanSheet(site.lot_width_m, site.lot_depth_m, site.street_side)
    envelope = _buildable_envelope(site)
    bx0, by0 = layout.building_x_m, layout.building_y_m
    bx1, by1 = bx0 + layout.building_w_m, by0 + layout.building_h_m
    b_center = sheet.px((bx0 + bx1) / 2, (by0 + by1) / 2)

    body = sheet.body
    body.append(sheet.ground(envelope))
    body.append(
        '<g class="sp-access">'
        f'<polygon points="{sheet.points(layout.driveway_points_m)}" fill="{svg_kit.PAVING}" '
        f'stroke="{svg_kit.PAVING_EDGE}" stroke-width="0.9"/></g>'
    )
    body.append(sheet.building(bx0, by0, bx1, by1, "#ece7f4", "#6e5a86", 0, layout.orientation))
    label = f"{layout.building_w_m:.1f} × {layout.building_h_m:.1f} m"
    label_w = svg_kit.text_width(label, 8.5) + 12
    body.append(f'<rect x="{b_center[0] - label_w / 2:.1f}" y="{b_center[1] - 7:.1f}" width="{label_w:.1f}" '
                f'height="14" fill="#ece7f4" stroke="none"/>')
    body.append(svg_kit.text(b_center[0], b_center[1] + 3, label, 8.5, svg_kit.INK, "middle", 500))
    body.append('</g>')
    body.append('<g class="sp-annotation">' + sheet.overall_dimensions() + '</g>')

    notes = [(svg_kit.WARN, note) for note in layout.notes]
    notes.append((svg_kit.MUTED, "Concept placement from passive-solar rules; not a survey or zoning review."))
    height = sheet.footer(
        "Site plan",
        [
            ("Lot size", f"{site.lot_width_m:g} × {site.lot_depth_m:g} m"),
            ("Street", site.street_side),
            ("Setbacks", f"front {site.front_setback_m:g} · side {site.side_setback_m:g} · rear {site.rear_setback_m:g} m"),
            ("Solar score", f"{layout.solar_score:.2f}"),
        ],
        [
            ("fill:#ece7f4:#6e5a86", "Building"),
            (f"line:{svg_kit.SOLAR}", "Solar face"),
            (f"fill:{svg_kit.PAVING}:{svg_kit.PAVING_EDGE}", "Driveway"),
            (f"dash:{svg_kit.ENVELOPE}", "Setback line"),
        ],
        notes,
    )
    return sheet.render(height)
