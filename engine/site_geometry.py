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
    entrances: tuple[Point, ...]
    porches: tuple[Polygon, ...]
    pedestrian_spine: Polygon
    parking: tuple[Polygon, ...]
    vehicle_access: Polygon | None
    shared_green: Polygon
    trees: tuple[Point, ...]
    rain_garden: Polygon | None


def _shared_green(site: SiteSpec) -> Polygon:
    """The rear yard becomes one shared garden strip when the rear setback is
    deep enough; otherwise fall back to a small amenity corner."""
    envelope = _buildable_envelope(site)
    inset = 0.75
    if site.street_side == "N":
        strip = box(site.side_setback_m, envelope.y1 + inset, site.lot_width_m - site.side_setback_m, site.lot_depth_m - inset)
    elif site.street_side == "S":
        strip = box(site.side_setback_m, inset, site.lot_width_m - site.side_setback_m, envelope.y0 - inset)
    elif site.street_side == "W":
        strip = box(envelope.x1 + inset, site.side_setback_m, site.lot_width_m - inset, site.lot_depth_m - site.side_setback_m)
    else:
        strip = box(inset, site.side_setback_m, envelope.x0 - inset, site.lot_depth_m - site.side_setback_m)
    min_x, min_y, max_x, max_y = strip.bounds
    if strip.is_valid and not strip.is_empty and min(max_x - min_x, max_y - min_y) >= 2.5:
        return strip

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


def spine_centre(buildings, site: SiteSpec, width_m: float = 1.8, clearance_m: float = 0.4) -> float | None:
    """Where the shared walkway can run from the street without crossing a
    building: the lot centre if it is clear, otherwise the clear corridor
    between buildings nearest the centre. ``None`` when no corridor exists."""
    along_x = site.street_side in ("N", "S")
    extent = site.lot_width_m if along_x else site.lot_depth_m
    centre = extent / 2
    need = width_m + 2 * clearance_m
    spans = sorted(
        (b.bounds[0], b.bounds[2]) if along_x else (b.bounds[1], b.bounds[3])
        for b in buildings
    )
    if all(hi <= centre - need / 2 or lo >= centre + need / 2 for lo, hi in spans):
        return centre
    gaps: list[tuple[float, float]] = []
    cursor = site.side_setback_m
    for lo, hi in spans:
        if lo - cursor >= need:
            gaps.append((cursor, lo))
        cursor = max(cursor, hi)
    if extent - site.side_setback_m - cursor >= need:
        gaps.append((cursor, extent - site.side_setback_m))
    if not gaps:
        return None
    return min(((lo + hi) / 2 for lo, hi in gaps), key=lambda c: abs(c - centre))


def _pedestrian_spine(site: SiteSpec, centre: float | None, width_m: float = 1.8) -> Polygon:
    """Walkway from the street to the rear garden along ``centre``; with no
    clear corridor it stops at the setback line as an entry walk."""
    envelope = _buildable_envelope(site)
    half = width_m / 2
    if site.street_side in ("N", "S"):
        c = site.lot_width_m / 2 if centre is None else centre
        if site.street_side == "N":
            return box(c - half, 0, c + half, envelope.y0 if centre is None else envelope.y1)
        return box(c - half, envelope.y1 if centre is None else envelope.y0, c + half, site.lot_depth_m)
    c = site.lot_depth_m / 2 if centre is None else centre
    if site.street_side == "W":
        return box(0, c - half, envelope.x0 if centre is None else envelope.x1, c + half)
    return box(envelope.x1 if centre is None else envelope.x0, c - half, site.lot_width_m, c + half)


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
    walk = spine_centre(buildings, site)
    walk_x = site.lot_width_m / 2 if walk is None else walk
    walk_y = site.lot_depth_m / 2 if walk is None else walk
    entrances: list[Point] = []
    porches: list[Polygon] = []
    for building in buildings:
        min_x, min_y, max_x, max_y = building.bounds
        center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2
        if site.street_side in ("N", "S"):
            if center_x < walk_x:
                entrances.append(Point(max_x, center_y))
                porches.append(box(max_x, center_y - 0.75, max_x + 0.9, center_y + 0.75))
            else:
                entrances.append(Point(min_x, center_y))
                porches.append(box(min_x - 0.9, center_y - 0.75, min_x, center_y + 0.75))
        elif center_y < walk_y:
            entrances.append(Point(center_x, max_y))
            porches.append(box(center_x - 0.75, max_y, center_x + 0.75, max_y + 0.9))
        else:
            entrances.append(Point(center_x, min_y))
            porches.append(box(center_x - 0.75, min_y - 0.9, center_x + 0.75, min_y))
    parking = tuple(box(x, y, x + w, y + h) for x, y, w, h in parking_spaces)
    green = _shared_green(site).intersection(lot)
    g_min_x, g_min_y, g_max_x, g_max_y = green.bounds
    long_x = (g_max_x - g_min_x) >= (g_max_y - g_min_y)
    length = (g_max_x - g_min_x) if long_x else (g_max_y - g_min_y)
    depth = (g_max_y - g_min_y) if long_x else (g_max_x - g_min_x)

    def along(t: float, offset: float = 0.5) -> Point:
        if long_x:
            return Point(g_min_x + length * t, g_min_y + depth * offset)
        return Point(g_min_x + depth * offset, g_min_y + length * t)

    # Trees sit along the garden's long axis, leaving its first stretch for
    # the rain garden and label.
    tree_count = max(2, min(8, int(length // 5)))
    tree_points = tuple(along(0.32 + 0.62 * i / max(1, tree_count - 1)) for i in range(tree_count))
    rain_radius = min(1.3, depth / 3, length / 8)
    rain_garden = along(0.13, 0.62).buffer(rain_radius) if rain_radius >= 0.4 else None
    return SitePlanGeometry(
        lot_boundary=lot,
        buildable_envelope=buildable,
        buildings=buildings,
        entrances=tuple(entrances),
        porches=tuple(porches),
        pedestrian_spine=_pedestrian_spine(site, walk),
        parking=parking,
        vehicle_access=_vehicle_access(site, parking),
        shared_green=green,
        trees=tree_points,
        rain_garden=rain_garden,
    )
