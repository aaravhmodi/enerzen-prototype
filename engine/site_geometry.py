"""Geometry-first site-plan primitives.

The renderer should draw a site model, not independently invent rectangles for
each visual layer.  This module keeps all concept geometry in metres so it can
later be exported to DXF/GeoJSON or sent to a CAD/geometry service.
"""

from dataclasses import dataclass

from shapely.geometry import Point, Polygon, box

from engine.site import SiteSpec, _buildable_envelope


@dataclass(frozen=True)
class SitePlanGeometry:
    lot_boundary: Polygon
    buildable_envelope: Polygon
    buildings: tuple[Polygon, ...]
    pedestrian_spine: Polygon
    parking: tuple[Polygon, ...]
    vehicle_access: Polygon | None
    shared_green: Polygon
    trees: tuple[Point, ...]
    rain_garden: Polygon | None


def _shared_green(site: SiteSpec) -> Polygon:
    green_w = min(4.0, max(2.5, site.lot_width_m * 0.18), site.lot_width_m)
    green_h = min(4.0, max(2.5, site.lot_depth_m * 0.10), site.lot_depth_m)
    if site.street_side == "N":
        green_x, green_y = site.lot_width_m - site.side_setback_m - green_w, site.lot_depth_m - green_h
    elif site.street_side == "S":
        green_x, green_y = site.lot_width_m - site.side_setback_m - green_w, 0
    elif site.street_side == "W":
        green_x, green_y = site.lot_width_m - green_w, site.lot_depth_m - site.side_setback_m - green_h
    else:
        green_x, green_y = 0, site.lot_depth_m - site.side_setback_m - green_h
    return box(green_x, green_y, green_x + green_w, green_y + green_h)


def _pedestrian_spine(site: SiteSpec, width_m: float = 1.8) -> Polygon:
    if site.street_side in ("N", "S"):
        center = site.lot_width_m / 2
        return box(center - width_m / 2, 0, center + width_m / 2, site.lot_depth_m)
    center = site.lot_depth_m / 2
    return box(0, center - width_m / 2, site.lot_width_m, center + width_m / 2)


def _vehicle_access(site: SiteSpec, parking: tuple[Polygon, ...]) -> Polygon | None:
    if not parking:
        return None
    stall = parking[0]
    min_x, min_y, max_x, max_y = stall.bounds
    if site.street_side == "N":
        return box(min_x, 0, max_x, max_y)
    if site.street_side == "S":
        return box(min_x, min_y, max_x, site.lot_depth_m)
    if site.street_side == "W":
        return box(0, min_y, max_x, max_y)
    return box(min_x, min_y, site.lot_width_m, max_y)


def build_site_geometry(
    placements,
    site: SiteSpec,
    parking_spaces: list[tuple[float, float, float, float]],
) -> SitePlanGeometry:
    """Build one coherent, metre-based geometry model for a concept plan."""
    lot = box(0, 0, site.lot_width_m, site.lot_depth_m)
    envelope = _buildable_envelope(site)
    buildable = box(envelope.x0, envelope.y0, envelope.x1, envelope.y1)
    buildings = tuple(
        box(p.x_m, p.y_m, p.x_m + p.w_m, p.y_m + p.h_m)
        for p in placements
    )
    parking = tuple(box(x, y, x + w, y + h) for x, y, w, h in parking_spaces)
    green = _shared_green(site).intersection(lot)
    tree_radius = min(0.55, green.bounds[2] - green.bounds[0], green.bounds[3] - green.bounds[1]) / 7
    tree_points = tuple(
        Point(green.bounds[0] + (green.bounds[2] - green.bounds[0]) * x,
              green.bounds[1] + (green.bounds[3] - green.bounds[1]) * y)
        for x, y in ((0.18, 0.28), (0.82, 0.28), (0.18, 0.78), (0.82, 0.78))
    )
    rain_center = Point(
        green.bounds[0] + (green.bounds[2] - green.bounds[0]) * 0.5,
        green.bounds[1] + (green.bounds[3] - green.bounds[1]) * 0.55,
    )
    rain_radius = min(0.65, green.bounds[2] - green.bounds[0], green.bounds[3] - green.bounds[1]) / 6
    return SitePlanGeometry(
        lot_boundary=lot,
        buildable_envelope=buildable,
        buildings=buildings,
        pedestrian_spine=_pedestrian_spine(site),
        parking=parking,
        vehicle_access=_vehicle_access(site, parking),
        shared_green=green,
        trees=tree_points,
        rain_garden=rain_center.buffer(rain_radius),
    )
