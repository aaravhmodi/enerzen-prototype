"""
Multi-unit site placement and SVG generation.

Places multiple building archetypes on a lot using a row-based layout:
buildings fill left-to-right in rows, rear to street, with configurable
gaps between buildings. Generates an SVG site plan showing all buildings
labelled by archetype type, with a colour legend.
"""

from dataclasses import dataclass

from engine.site import SiteSpec, _buildable_envelope
from engine.site_geometry import SitePlanGeometry, build_site_geometry, spine_centre

_GAP_M = 3.0       # gap between buildings (E-W and N-S)
_PEDESTRIAN_SPINE_M = 1.8
_SPINE_CLEARANCE_M = 1.5

# Colour palette per archetype (fill, stroke)
_ARCHETYPE_COLORS: dict[str, tuple[str, str]] = {
    "garden_suite": ("#ece7f4", "#6e5a86"),  # lavender
    "three_bhk":    ("#e3e9f1", "#4f6580"),  # slate
    "murb":         ("#f1e6ea", "#86566a"),  # rose
    "townhouse":    ("#f2ece2", "#8a6d45"),  # sand
}
_DEFAULT_COLOR = ("#efedf1", "#6f6878")


@dataclass
class UnitPlacement:
    archetype_id: str
    x_m: float   # west edge from lot west
    y_m: float   # north edge from lot north
    w_m: float   # E-W extent
    h_m: float   # N-S extent
    label: str   # short display label


def place_units(mix: dict[str, int], lot: SiteSpec) -> list[UnitPlacement]:
    """
    Row-based placement inside the buildable envelope.

    Buildings are arranged rear-to-street (y increases toward street).
    Townhouse units of the same block are grouped horizontally.
    Returns a list of UnitPlacement objects; empty list if nothing fits.
    """
    from engine.archetypes import ARCHETYPES

    if not mix or all(v == 0 for v in mix.values()):
        return []

    envelope = _buildable_envelope(lot)
    env_w = envelope.x1 - envelope.x0
    env_h = envelope.y1 - envelope.y0

    # Build an ordered list of individual "blocks" to place.
    # Townhouse units in the same archetype are grouped into rows of attached units.
    blocks: list[tuple[str, float, float]] = []  # (archetype_id, w_m, h_m)

    for arch_id, count in mix.items():
        if count <= 0:
            continue
        arch = ARCHETYPES[arch_id]
        if arch_id == "townhouse":
            # Group all townhouse units into one or more attached rows of up to 6
            remaining = count
            while remaining > 0:
                row_units = min(remaining, 6)
                blocks.append((arch_id, arch.footprint_length_m * row_units, arch.footprint_width_m))
                remaining -= row_units
        else:
            for _ in range(count):
                blocks.append((arch_id, arch.footprint_length_m, arch.footprint_width_m))

    # Orient the long face east-west for a south-facing solar strategy. For an
    # east/west-facing scheme, rotate the blocks so the main face follows the
    # selected orientation. This keeps the layout tied to the same orientation
    # used by the energy model instead of treating buildings as unlabelled
    # rectangles.
    if lot.solar_orientation in ("E", "W"):
        blocks = [(arch_id, bh, bw) for arch_id, bw, bh in blocks]

    # Sort blocks tallest-first (N-S) so large buildings go at the rear
    blocks.sort(key=lambda b: b[2], reverse=True)

    courtyard = _courtyard_placements(blocks, envelope, lot.street_side)
    if courtyard is not None:
        return courtyard

    placements: list[UnitPlacement] = []
    cur_y = envelope.y0  # start at rear setback (north edge if street is N)

    i = 0
    while i < len(blocks):
        # Fill one row: as many blocks as fit horizontally
        row_blocks: list[tuple[str, float, float]] = []
        row_w = 0.0
        row_h = 0.0
        j = i
        while j < len(blocks):
            arch_id, bw, bh = blocks[j]
            needed_w = bw + (_GAP_M if row_blocks else 0.0)
            if row_w + needed_w > env_w + 0.01:
                break
            row_blocks.append(blocks[j])
            row_w += needed_w
            row_h = max(row_h, bh)
            j += 1

        if not row_blocks:
            # Single block wider than envelope — still place it (overflow)
            row_blocks = [blocks[i]]
            row_h = blocks[i][2]
            j = i + 1

        if cur_y + row_h > envelope.y1 + 0.01:
            break  # no vertical space left

        # Place blocks in this row, centred horizontally
        total_row_w = sum(b[1] for b in row_blocks) + _GAP_M * (len(row_blocks) - 1)
        cur_x = envelope.x0 + (env_w - total_row_w) / 2

        for arch_id, bw, bh in row_blocks:
            from engine.archetypes import ARCHETYPES
            arch = ARCHETYPES[arch_id]
            placements.append(UnitPlacement(
                archetype_id=arch_id,
                x_m=cur_x,
                y_m=cur_y,
                w_m=bw,
                h_m=bh,
                label=arch.name.split("(")[0].strip(),
            ))
            cur_x += bw + _GAP_M

        cur_y += row_h + _GAP_M
        i = j

    return placements


def _courtyard_placements(
    blocks: list[tuple[str, float, float]],
    envelope,
    street_side: str,
) -> list[UnitPlacement] | None:
    """Place blocks on both sides of a shared pedestrian spine.

    This creates a legible cluster with a continuous access route rather than
    filling rows blindly. It returns ``None`` when the buildable envelope is
    too narrow or shallow, allowing the conservative row fallback to handle
    tight lots.
    """
    if not blocks:
        return []

    side_width = (envelope.width - _PEDESTRIAN_SPINE_M - 2 * _SPINE_CLEARANCE_M) / 2
    if side_width <= 0:
        return None

    # The spine runs from the street into the site, leaving two coherent
    # building bands. This prioritizes legible arrival over blind area packing.
    if street_side in ("N", "S"):
        if any(bw > side_width + 0.01 for _, bw, _ in blocks):
            return None
        cursors = [envelope.y0, envelope.y0]
        placements: list[UnitPlacement] = []
        for arch_id, bw, bh in blocks:
            options = [i for i in range(2) if cursors[i] + bh <= envelope.y1 + 0.01]
            if not options:
                return None
            band = min(options, key=lambda i: cursors[i])
            x0 = envelope.x0 if band == 0 else envelope.x1 - side_width
            x = x0 + (side_width - bw) / 2
            y = cursors[band]
            placements.append(UnitPlacement(arch_id, x, y, bw, bh, ""))
            cursors[band] += bh + _GAP_M
    else:
        side_height = (envelope.height - _PEDESTRIAN_SPINE_M - 2 * _SPINE_CLEARANCE_M) / 2
        if any(bh > side_height + 0.01 for _, _, bh in blocks):
            return None
        cursors = [envelope.x0, envelope.x0]
        placements = []
        for arch_id, bw, bh in blocks:
            options = [i for i in range(2) if cursors[i] + bw <= envelope.x1 + 0.01]
            if not options:
                return None
            band = min(options, key=lambda i: cursors[i])
            y0 = envelope.y0 if band == 0 else envelope.y1 - side_height
            x = cursors[band]
            y = y0 + (side_height - bh) / 2
            placements.append(UnitPlacement(arch_id, x, y, bw, bh, ""))
            cursors[band] += bw + _GAP_M

    from engine.archetypes import ARCHETYPES
    for placement in placements:
        placement.label = ARCHETYPES[placement.archetype_id].name.split("(")[0].strip()
    return placements


def _parking_spaces(total_units: int, lot: SiteSpec,
                    walk_centre: float | None = None) -> list[tuple[float, float, float, float]]:
    """Return a simple street-side parking concept when the frontage allows it.

    The 2.7 x 5.5 m stall is a planning placeholder, not a municipal parking
    standard. A missing result is intentionally visible in the plan rather than
    silently drawing spaces that do not fit the supplied lot.
    """
    stall_w, stall_d = 2.7, 5.5
    if total_units <= 0 or lot.front_setback_m < stall_d:
        return []

    spaces: list[tuple[float, float, float, float]] = []
    if lot.street_side in ("N", "S"):
        center = lot.lot_width_m / 2 if walk_centre is None else walk_centre
        left_start = lot.side_setback_m
        left_end = center - _SPINE_CLEARANCE_M
        right_start = center + _SPINE_CLEARANCE_M
        right_end = lot.lot_width_m - lot.side_setback_m
        left_capacity = int(max(0, left_end - left_start) // stall_w)
        right_capacity = int(max(0, right_end - right_start) // stall_w)
        if left_capacity + right_capacity < total_units:
            return []
        y0 = 0.25 if lot.street_side == "N" else lot.lot_depth_m - stall_d - 0.25
        remaining = total_units
        for i in range(min(remaining, left_capacity)):
            spaces.append((left_start + i * stall_w, y0, stall_w - 0.15, stall_d))
        remaining -= min(remaining, left_capacity)
        for i in range(remaining):
            spaces.append((right_start + i * stall_w, y0, stall_w - 0.15, stall_d))
    else:
        center = lot.lot_depth_m / 2 if walk_centre is None else walk_centre
        top_start = lot.side_setback_m
        top_end = center - _SPINE_CLEARANCE_M
        bottom_start = center + _SPINE_CLEARANCE_M
        bottom_end = lot.lot_depth_m - lot.side_setback_m
        top_capacity = int(max(0, top_end - top_start) // stall_w)
        bottom_capacity = int(max(0, bottom_end - bottom_start) // stall_w)
        if top_capacity + bottom_capacity < total_units:
            return []
        x0 = 0.25 if lot.street_side == "W" else lot.lot_width_m - stall_d - 0.25
        remaining = total_units
        for i in range(min(remaining, top_capacity)):
            spaces.append((x0, top_start + i * stall_w, stall_d, stall_w - 0.15))
        remaining -= min(remaining, top_capacity)
        for i in range(remaining):
            spaces.append((x0, bottom_start + i * stall_w, stall_d, stall_w - 0.15))
    return spaces


def fits_on_lot(mix: dict[str, int], lot: SiteSpec) -> bool:
    """Quick check: do all requested units fit within the buildable envelope?"""
    placements = place_units(mix, lot)
    total_requested = sum(
        v if k != "townhouse" else v  # townhouse: count units not blocks
        for k, v in mix.items() if v > 0
    )
    if total_requested == 0:
        return True
    return len(placements) > 0 and _all_placed(placements, mix)


def _all_placed(placements: list[UnitPlacement], mix: dict[str, int]) -> bool:
    from engine.archetypes import ARCHETYPES
    placed_units: dict[str, int] = {}
    for p in placements:
        arch = ARCHETYPES[p.archetype_id]
        if p.archetype_id == "townhouse":
            units_in_block = round(p.w_m / arch.footprint_length_m)
            placed_units[p.archetype_id] = placed_units.get(p.archetype_id, 0) + units_in_block
        else:
            placed_units[p.archetype_id] = placed_units.get(p.archetype_id, 0) + 1
    return all(placed_units.get(k, 0) >= v for k, v in mix.items() if v > 0)


def _archetype_detail(arch_id: str, sheet, bounds, entrance, stroke: str) -> tuple[str, tuple[float, float]]:
    """Plan detail taken from the EnerZen unit drawings, and where the
    numbered badge should sit so it does not cover that detail.

    MURB: a corridor across the long axis with the elevator core at its centre
    and balconies on both long faces. Townhouse: party walls between units
    and a front door per unit along the entrance face.
    """
    from engine import svg_kit
    from engine.archetypes import ARCHETYPES

    x0, y0, x1, y1 = bounds
    a, b = sheet.px(x0, y0)
    c, d = sheet.px(x1, y1)
    cx, cy = (a + c) / 2, (b + d) / 2
    long_x = (c - a) >= (d - b)
    parts: list[str] = []
    badge = (cx, cy)
    if arch_id == "murb":
        band = (min(c - a, d - b)) * 0.08
        core = min(c - a, d - b) * 0.16
        if long_x:
            parts.append(f'<rect x="{a:.1f}" y="{cy - band:.1f}" width="{c - a:.1f}" height="{2 * band:.1f}" '
                         f'fill="white" stroke="{stroke}" stroke-width="0.6"/>')
            balcony_faces = (b, d)
        else:
            parts.append(f'<rect x="{cx - band:.1f}" y="{b:.1f}" width="{2 * band:.1f}" height="{d - b:.1f}" '
                         f'fill="white" stroke="{stroke}" stroke-width="0.6"/>')
            balcony_faces = (a, c)
        parts.append(f'<rect x="{cx - core / 2:.1f}" y="{cy - core / 2:.1f}" width="{core:.1f}" height="{core:.1f}" '
                     f'fill="{stroke}" stroke="none"/>')
        parts.append(f'<line x1="{cx - core / 2 + 2:.1f}" y1="{cy - core / 2 + 2:.1f}" x2="{cx + core / 2 - 2:.1f}" '
                     f'y2="{cy + core / 2 - 2:.1f}" stroke="white" stroke-width="0.7"/>')
        bal_long, bal_deep = 2.7 * sheet.scale, 1.2 * sheet.scale
        for face in balcony_faces:
            for t in (0.3, 0.7):
                if long_x:
                    bx, by = a + (c - a) * t - bal_long / 2, (face - bal_deep) if face == b else face
                    w, h = bal_long, bal_deep
                else:
                    bx, by = (face - bal_deep) if face == a else face, b + (d - b) * t - bal_long / 2
                    w, h = bal_deep, bal_long
                parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{w:.1f}" height="{h:.1f}" '
                             f'fill="white" stroke="{stroke}" stroke-width="0.6"/>')
        badge = (a + (c - a) * 0.22, b + (d - b) * 0.25) if long_x else (a + (c - a) * 0.25, b + (d - b) * 0.22)
    elif arch_id == "townhouse":
        unit = ARCHETYPES["townhouse"].footprint_length_m * sheet.scale
        span = (c - a) if long_x else (d - b)
        n = max(1, round(span / unit))
        for k in range(1, n):
            if long_x:
                lx = a + span * k / n
                parts.append(f'<line x1="{lx:.1f}" y1="{b:.1f}" x2="{lx:.1f}" y2="{d:.1f}" stroke="{stroke}" stroke-width="0.9"/>')
            else:
                ly = b + span * k / n
                parts.append(f'<line x1="{a:.1f}" y1="{ly:.1f}" x2="{c:.1f}" y2="{ly:.1f}" stroke="{stroke}" stroke-width="0.9"/>')
        ex, ey = sheet.px(entrance.x, entrance.y)
        on_long_face = abs(ey - b) < 1 or abs(ey - d) < 1 if long_x else abs(ex - a) < 1 or abs(ex - c) < 1
        if on_long_face:
            for k in range(n):
                t = (k + 0.5) / n
                dx, dy = (a + (c - a) * t, ey) if long_x else (ex, b + (d - b) * t)
                parts.append(f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="1.8" fill="{svg_kit.INK}" stroke="white" stroke-width="0.6"/>')
        badge = (a + span / n / 2, cy) if long_x else (cx, b + span / n / 2)
    return "".join(parts), badge


def multi_site_plan_svg(
    placements: list[UnitPlacement],
    lot: SiteSpec,
    mix: dict[str, int],
) -> str:
    """SVG concept plan for a development: street and sidewalk, a shared
    walkway through a clear corridor, parking, the rear shared garden, and
    numbered buildings keyed to a legend."""
    from shapely.geometry import box

    from engine import svg_kit
    from engine.archetypes import ARCHETYPES

    sheet = svg_kit.PlanSheet(lot.lot_width_m, lot.lot_depth_m, lot.street_side)
    envelope = _buildable_envelope(lot)
    total_units = sum(mix.values())
    walk = spine_centre([box(p.x_m, p.y_m, p.x_m + p.w_m, p.y_m + p.h_m) for p in placements], lot)
    parking_spaces = _parking_spaces(total_units, lot, walk)
    geometry = build_site_geometry(placements, lot, parking_spaces)
    s = sheet.scale

    def poly(polygon) -> str:
        return sheet.points(polygon.exterior.coords)

    body = sheet.body
    body.append(sheet.ground(envelope))

    # Landscape: the shared garden, its trees and the rain garden.
    green = geometry.shared_green
    g0 = sheet.px(green.bounds[0], green.bounds[1])
    g1 = sheet.px(green.bounds[2], green.bounds[3])
    body.append('<g class="sp-landscape">')
    body.append(f'<polygon id="shared-green-space" points="{poly(green)}" fill="{svg_kit.GREEN}" '
                f'stroke="{svg_kit.GREEN_EDGE}" stroke-width="0.9"/>')
    if geometry.rain_garden is not None:
        rc = geometry.rain_garden.centroid
        rx, ry = sheet.px(rc.x, rc.y)
        r = (geometry.rain_garden.bounds[2] - rc.x) * s
        body.append(f'<circle id="rain-garden" cx="{rx:.1f}" cy="{ry:.1f}" r="{r:.1f}" fill="{svg_kit.WATER}" '
                    f'stroke="{svg_kit.WATER_EDGE}" stroke-width="0.8"/>')
    short_side_m = min(green.bounds[2] - green.bounds[0], green.bounds[3] - green.bounds[1])
    tree_r = min(1.6, short_side_m * 0.3) * s
    for index, tree in enumerate(geometry.trees, start=1):
        tx, ty = sheet.px(tree.x, tree.y)
        body.append(f'<circle id="tree-{index}" cx="{tx:.1f}" cy="{ty:.1f}" r="{tree_r:.1f}" '
                    f'fill="{svg_kit.TREE}" stroke="{svg_kit.TREE_EDGE}" stroke-width="0.8"/>')
        body.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="1.2" fill="{svg_kit.TREE_EDGE}" stroke="none"/>')
    if g1[0] - g0[0] >= g1[1] - g0[1]:
        body.append(svg_kit.text(g0[0] + 6, g0[1] + 11, "Shared green / amenity", 7.5, "#5f7154", "start", 500))
    else:
        body.append(svg_kit.text(g0[0] + 11, g1[1] - 6, "Shared green / amenity", 7.5, "#5f7154", "start", 500,
                                 rotate=True))
    body.append('</g>')

    # Access: walkway, vehicle access and parking.
    body.append('<g class="sp-access">')
    body.append(f'<polygon id="pedestrian-walkway" points="{poly(geometry.pedestrian_spine)}" '
                f'fill="{svg_kit.PAVING}" stroke="{svg_kit.PAVING_EDGE}" stroke-width="0.8"/>')
    if geometry.vehicle_access is not None:
        body.append(f'<polygon id="vehicle-access" points="{poly(geometry.vehicle_access)}" '
                    f'fill="{svg_kit.PAVING}" stroke="{svg_kit.PAVING_EDGE}" stroke-width="0.8"/>')
    for i, stall in enumerate(geometry.parking, start=1):
        p0 = sheet.px(stall.bounds[0], stall.bounds[1])
        p1 = sheet.px(stall.bounds[2], stall.bounds[3])
        body.append(f'<rect id="parking-space-{i}" x="{p0[0]:.1f}" y="{p0[1]:.1f}" width="{p1[0] - p0[0]:.1f}" '
                    f'height="{p1[1] - p0[1]:.1f}" fill="{svg_kit.PAVING}" stroke="{svg_kit.LINE}" stroke-width="0.6"/>')
        body.append(svg_kit.text((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 + 3, "P", 7.5, svg_kit.MUTED, "middle", 600))
    for i, path in enumerate(geometry.entry_paths, start=1):
        for part in getattr(path, "geoms", [path]):
            body.append(f'<polygon id="entry-path-{i}" points="{poly(part)}" fill="{svg_kit.PAVING}" '
                        f'stroke="{svg_kit.PAVING_EDGE}" stroke-width="0.6"/>')
    body.append('</g>')

    # Buildings, numbered by archetype and keyed to the legend.
    archetype_order = [a for a in mix if mix.get(a, 0) > 0]
    number_by_archetype = {a: i + 1 for i, a in enumerate(archetype_order)}
    for index, (p, building, porch, entrance) in enumerate(
        zip(placements, geometry.buildings, geometry.porches, geometry.entrances), start=1
    ):
        fill, stroke = _ARCHETYPE_COLORS.get(p.archetype_id, _DEFAULT_COLOR)
        x0, y0, x1, y1 = building.bounds
        body.append(sheet.building(x0, y0, x1, y1, fill, stroke, index, lot.solar_orientation))
        detail, badge_at = _archetype_detail(p.archetype_id, sheet, building.bounds, entrance, stroke)
        body.append(detail)
        body.append(f'<polygon id="porch-{index}" points="{poly(porch)}" fill="{svg_kit.PORCH}" '
                    f'stroke="{svg_kit.PORCH_EDGE}" stroke-width="0.7"/>')
        ex, ey = sheet.px(entrance.x, entrance.y)
        body.append(f'<circle id="building-entrance-{index}" cx="{ex:.1f}" cy="{ey:.1f}" r="2.2" '
                    f'fill="{svg_kit.INK}" stroke="white" stroke-width="0.7"/>')
        if min(x1 - x0, y1 - y0) * s >= 16:
            body.append(svg_kit.numbered_badge(*badge_at, number_by_archetype.get(p.archetype_id, 0), stroke))
        body.append('</g>')

    body.append('<g class="sp-annotation">' + sheet.overall_dimensions() + '</g>')

    parking_label = f"{len(parking_spaces)} concept stalls" if parking_spaces else "Not allocated on supplied lot"
    legend = [
        (f"badge:{_ARCHETYPE_COLORS.get(a, _DEFAULT_COLOR)[1]}:{number_by_archetype[a]}",
         f"{ARCHETYPES[a].name} × {mix[a]}")
        for a in archetype_order
    ]
    legend += [
        (f"line:{svg_kit.SOLAR}", "Solar face"),
        (f"fill:{svg_kit.PAVING}:{svg_kit.PAVING_EDGE}", "Walkway & parking"),
        (f"fill:{svg_kit.GREEN}:{svg_kit.GREEN_EDGE}", "Shared green"),
        (f"dot:{svg_kit.WATER}:{svg_kit.WATER_EDGE}", "Rain garden"),
        (f"dash:{svg_kit.ENVELOPE}", "Setback line"),
    ]
    notes = []
    if walk is None and placements:
        notes.append((svg_kit.WARN, "No clear walkway corridor between buildings; entry walk shown to the setback line."))
    notes.append((svg_kit.MUTED, "Walkway / parking / shared green are concept layers, not a site plan approval."))
    height = sheet.footer(
        "Development site plan",
        [
            ("Total units", f"{total_units}"),
            ("Lot size", f"{lot.lot_width_m:g} × {lot.lot_depth_m:g} m"),
            ("Street", lot.street_side),
            ("Setbacks", f"front {lot.front_setback_m:g} · side {lot.side_setback_m:g} · rear {lot.rear_setback_m:g} m"),
            ("Parking", parking_label),
        ],
        legend,
        notes,
    )
    return sheet.render(height)
