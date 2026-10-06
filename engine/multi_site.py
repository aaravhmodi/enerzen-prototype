"""
Multi-unit site placement and SVG generation.

Places multiple building archetypes on a lot using a row-based layout:
buildings fill left-to-right in rows, rear to street, with configurable
gaps between buildings. Generates an SVG site plan showing all buildings
labelled by archetype type, with a colour legend.
"""

import math
from dataclasses import dataclass

from engine.site import SiteSpec, _buildable_envelope
from engine.site_geometry import SitePlanGeometry, build_site_geometry

_SCALE_PX_PER_M = 8
_MARGIN_PX = 50
_GAP_M = 3.0       # gap between buildings (E-W and N-S)
_PEDESTRIAN_SPINE_M = 1.8
_SPINE_CLEARANCE_M = 1.5

# Colour palette per archetype (fill, stroke)
_ARCHETYPE_COLORS: dict[str, tuple[str, str]] = {
    "garden_suite": ("#d1fae5", "#059669"),  # green
    "three_bhk":    ("#dbeafe", "#2563eb"),  # blue
    "murb":         ("#fce7f3", "#db2777"),  # pink
    "townhouse":    ("#fef3c7", "#d97706"),  # amber
}
_DEFAULT_COLOR = ("#f3f4f6", "#6b7280")


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


def _parking_spaces(total_units: int, lot: SiteSpec) -> list[tuple[float, float, float, float]]:
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
        center = lot.lot_width_m / 2
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
        center = lot.lot_depth_m / 2
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


def multi_site_plan_svg(
    placements: list[UnitPlacement],
    lot: SiteSpec,
    mix: dict[str, int],
) -> str:
    """SVG site plan as a clean technical drawing — white background, black
    linework, numbered building badges keyed to a legend, full dimension
    strings, and a bordered title block — matching an actual site-plan
    submission rather than a marketing illustration."""
    from engine import svg_kit

    band = svg_kit.STREET_BAND_PX
    top = _MARGIN_PX + (band if lot.street_side == "N" else 0)
    bottom = (band if lot.street_side == "S" else 0) + 190
    left = _MARGIN_PX + (band if lot.street_side == "W" else 0)
    right = _MARGIN_PX + (band if lot.street_side == "E" else 0) + 30

    lot_w_px = lot.lot_width_m * _SCALE_PX_PER_M
    lot_h_px = lot.lot_depth_m * _SCALE_PX_PER_M
    w_px = lot_w_px + left + right
    h_px = lot_h_px + top + bottom

    def px(x_m: float, y_m: float) -> tuple[float, float]:
        return (left + x_m * _SCALE_PX_PER_M, top + y_m * _SCALE_PX_PER_M)

    envelope = _buildable_envelope(lot)
    e_x0, e_y0 = px(envelope.x0, envelope.y0)
    e_x1, e_y1 = px(envelope.x1, envelope.y1)

    total_units = sum(mix.values())
    parking_spaces = _parking_spaces(total_units, lot)
    geometry = build_site_geometry(placements, lot, parking_spaces)

    width_dim_offset = (band if lot.street_side == "S" else 0) + 16
    depth_dim_offset = -(16 + (band if lot.street_side == "E" else 0))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w_px:.0f}" height="{h_px:.0f}" '
        f'viewBox="0 0 {w_px:.0f} {h_px:.0f}" font-family="sans-serif">',
        svg_kit.defs_block(),
        svg_kit.street_edge(lot.street_side, left, top, lot_w_px, lot_h_px),
        svg_kit.lot_boundary(left, top, lot_w_px, lot_h_px),
        f'<rect x="{e_x0:.1f}" y="{e_y0:.1f}" width="{e_x1 - e_x0:.1f}" height="{e_y1 - e_y0:.1f}" '
        f'fill="none" stroke="{svg_kit.DASH_ENVELOPE}" stroke-width="1.25" stroke-dasharray="5,3"/>',
        svg_kit.overall_dimensions(left, top, lot_w_px, lot_h_px, lot.lot_width_m, lot.lot_depth_m,
                                    width_dim_offset, depth_dim_offset),
    ]

    # Public-realm context makes the lot read as part of a neighbourhood plan:
    # a narrow sidewalk strip sits between the street edge and the property
    # line, consistent with the permit-style context/site-plan drawing set.
    if lot.street_side == "N":
        sidewalk_x, sidewalk_y, sidewalk_w, sidewalk_h = left, top - band, lot_w_px, band
        sidewalk_label_x, sidewalk_label_y = left + lot_w_px / 2, sidewalk_y + 14
    elif lot.street_side == "S":
        sidewalk_x, sidewalk_y, sidewalk_w, sidewalk_h = left, top + lot_h_px, lot_w_px, band
        sidewalk_label_x, sidewalk_label_y = left + lot_w_px / 2, sidewalk_y + 14
    elif lot.street_side == "W":
        sidewalk_x, sidewalk_y, sidewalk_w, sidewalk_h = left - band, top, band, lot_h_px
        sidewalk_label_x, sidewalk_label_y = sidewalk_x + 8, top + lot_h_px / 2
    else:
        sidewalk_x, sidewalk_y, sidewalk_w, sidewalk_h = left + lot_w_px, top, band, lot_h_px
        sidewalk_label_x, sidewalk_label_y = sidewalk_x + 14, top + lot_h_px / 2
    sidewalk_rotation = (
        f' transform="rotate(-90 {sidewalk_label_x:.1f} {sidewalk_label_y:.1f})"'
        if lot.street_side in ("W", "E") else ""
    )
    parts.append(
        f'<rect id="public-sidewalk" x="{sidewalk_x:.1f}" y="{sidewalk_y:.1f}" '
        f'width="{sidewalk_w:.1f}" height="{sidewalk_h:.1f}" fill="#f3f4f6" stroke="#9ca3af" stroke-width="0.8"/>'
    )
    parts.append(
        f'<text x="{sidewalk_label_x:.1f}" y="{sidewalk_label_y:.1f}" text-anchor="middle" '
        f'font-size="7.5" letter-spacing="0.5" fill="#6b7280"{sidewalk_rotation}>PUBLIC SIDEWALK</text>'
    )

    def polygon_points(polygon):
        return " ".join(f"{px(x, y)[0]:.1f},{px(x, y)[1]:.1f}" for x, y in polygon.exterior.coords)

    # Concept layers requested by the development flow: pedestrian access and
    # shared open space. These are planning context, not permit or landscape
    # design determinations.
    parts.append(
        f'<polygon id="pedestrian-walkway" points="{polygon_points(geometry.pedestrian_spine)}" '
        'fill="#f1f5f9" stroke="#64748b" stroke-width="1.1" opacity="0.95"/>'
    )
    spine_mid = geometry.pedestrian_spine.centroid
    spine_x1, spine_y1 = px(spine_mid.x, spine_mid.y)
    if lot.street_side in ("N", "S"):
        spine_x2, spine_y2 = px(spine_mid.x, 0)
    else:
        spine_x2, spine_y2 = px(0, spine_mid.y)
    parts.append(
        f'<path d="M {spine_x1:.1f},{spine_y1:.1f} L {spine_x2:.1f},{spine_y2:.1f}" '
        'fill="none" stroke="#64748b" stroke-width="2" stroke-dasharray="6,4" opacity="0.8"/>'
    )
    green_min_x, green_min_y, green_max_x, green_max_y = geometry.shared_green.bounds
    gx, gy = px(green_min_x, green_min_y)
    parts.append(
        f'<polygon id="shared-green-space" points="{polygon_points(geometry.shared_green)}" '
        'fill="#dcfce7" stroke="#16a34a" stroke-width="1.2" stroke-dasharray="3,2"/>'
    )
    parts.append(
        f'<text x="{gx + 4:.1f}" y="{gy + 12:.1f}" font-size="8" fill="#166534">'
        'Shared green / amenity</text>'
    )

    for i, parking_polygon in enumerate(geometry.parking, start=1):
        parking_min_x, parking_min_y, parking_max_x, parking_max_y = parking_polygon.bounds
        parking_x, parking_y = px(parking_min_x, parking_min_y)
        pw_m, ph_m = parking_max_x - parking_min_x, parking_max_y - parking_min_y
        parts.append(
            f'<rect id="parking-space-{i}" x="{parking_x:.1f}" y="{parking_y:.1f}" '
            f'width="{pw_m * _SCALE_PX_PER_M:.1f}" height="{ph_m * _SCALE_PX_PER_M:.1f}" '
            'fill="#e5e7eb" stroke="#6b7280" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{parking_x + pw_m * _SCALE_PX_PER_M / 2:.1f}" '
            f'y="{parking_y + ph_m * _SCALE_PX_PER_M / 2 + 3:.1f}" text-anchor="middle" '
            'font-size="8" fill="#374151">P</text>'
        )

    if geometry.vehicle_access is not None:
        access_path = polygon_points(geometry.vehicle_access)
        access_centroid = geometry.vehicle_access.centroid
        label_x, label_y = px(access_centroid.x, access_centroid.y)
        parts.append(
            f'<polygon id="vehicle-access" points="{access_path}" fill="#cbd5e1" '
            'stroke="#64748b" stroke-width="1" opacity="0.9"/>'
        )
        parts.append(
            f'<text x="{label_x:.1f}" y="{label_y - 4:.1f}" text-anchor="middle" font-size="7.5" '
            'fill="#64748b">driveway / curb cut</text>'
        )

    # Green infrastructure is shown as a small shared landscape system rather
    # than an unlabelled leftover rectangle: trees and a rain-garden marker
    # make the sustainable-community intent legible in the visual plan.
    tree_radius = min(0.55, green_max_x - green_min_x, green_max_y - green_min_y) / 7
    for index, tree in enumerate(geometry.trees, start=1):
        tree_cx, tree_cy = px(tree.x, tree.y)
        parts.append(
            f'<circle id="tree-{index}" cx="{tree_cx:.1f}" cy="{tree_cy:.1f}" '
            f'r="{tree_radius * _SCALE_PX_PER_M:.1f}" fill="#86efac" stroke="#15803d" stroke-width="0.9"/>'
        )
    rain_cx, rain_cy = px(geometry.rain_garden.centroid.x, geometry.rain_garden.centroid.y)
    parts.append(
        f'<circle id="rain-garden" cx="{rain_cx:.1f}" cy="{rain_cy:.1f}" '
        f'r="{geometry.rain_garden.bounds[2] - geometry.rain_garden.centroid.x:.1f}" '
        'fill="#bfdbfe" stroke="#2563eb" stroke-width="0.9" stroke-dasharray="2,2"/>'
    )
    parts.append(
        f'<text x="{rain_cx:.1f}" y="{rain_cy + 3:.1f}" text-anchor="middle" font-size="6.5" fill="#1d4ed8">RAIN</text>'
    )

    # Buildings — numbered badges so the legend below can key them, like a
    # land-dev site plan's numbered building callouts.
    archetype_order = [a for a in mix if mix.get(a, 0) > 0]
    number_by_archetype = {a: i + 1 for i, a in enumerate(archetype_order)}
    for index, (p, building, porch, entrance) in enumerate(
        zip(placements, geometry.buildings, geometry.porches, geometry.entrances), start=1
    ):
        fill, stroke = _ARCHETYPE_COLORS.get(p.archetype_id, _DEFAULT_COLOR)
        bx0, by0 = px(building.bounds[0], building.bounds[1])
        bw_px = (building.bounds[2] - building.bounds[0]) * _SCALE_PX_PER_M
        bh_px = (building.bounds[3] - building.bounds[1]) * _SCALE_PX_PER_M
        cx = bx0 + bw_px / 2
        cy = by0 + bh_px / 2
        parts.append(
            f'<polygon points="{polygon_points(building)}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<polygon id="porch-{index}" points="{polygon_points(porch)}" fill="#fef3c7" '
            'stroke="#b45309" stroke-width="0.9"/>'
        )
        entry_x, entry_y = px(entrance.x, entrance.y)
        parts.append(
            f'<circle id="building-entrance-{index}" cx="{entry_x:.1f}" cy="{entry_y:.1f}" '
            'r="2.7" fill="#92400e" stroke="white" stroke-width="0.8"/>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" font-size="7" '
            f'fill="{stroke}">{p.label}</text>'
        )
        if bw_px > 16 and bh_px > 16:
            parts.append(svg_kit.numbered_badge(cx, cy, number_by_archetype.get(p.archetype_id, 0), stroke))

    parts.append(svg_kit.compass(w_px - (right - 30) / 2 if right > 30 else w_px - 20,
                                  top / 2 + 4 if top > 20 else 16))
    scale_y = top + lot_h_px + (band if lot.street_side == "S" else 0) + 34
    parts.append(svg_kit.scale_bar(left, scale_y, _SCALE_PX_PER_M))

    # Title block, then a numbered legend keyed to the building badges.
    title_y = scale_y + 20
    parking_label = f"{len(parking_spaces)} concept stalls" if parking_spaces else "Not allocated on supplied lot"
    title_fields = [
        ("Total units", f"{total_units}"),
        ("Lot size", f"{lot.lot_width_m:g} x {lot.lot_depth_m:g} m"),
        ("Street", lot.street_side),
        ("Parking", parking_label),
    ]
    parts.append(svg_kit.title_block(
        left, title_y, min(260, lot_w_px),
        "Development site plan",
        title_fields,
    ))
    legend_y = title_y + 20 + 15 * len(title_fields) + 20
    legend_x = left
    from engine.archetypes import ARCHETYPES
    for arch_id in archetype_order:
        count = mix[arch_id]
        arch = ARCHETYPES[arch_id]
        fill, stroke = _ARCHETYPE_COLORS.get(arch_id, _DEFAULT_COLOR)
        parts.append(svg_kit.numbered_badge(legend_x + 8, legend_y - 3, number_by_archetype[arch_id], stroke))
        parts.append(
            f'<text x="{legend_x + 22:.0f}" y="{legend_y:.0f}" font-size="9.5" fill="{svg_kit.LINE}">'
            f'{arch.name} x {count}</text>'
        )
        legend_x += 170
        if legend_x > w_px - 150:
            legend_x = left
            legend_y += 18

    parts.append(
        f'<text x="{left:.0f}" y="{legend_y + 18:.0f}" font-size="8.5" fill="{svg_kit.LINE}">'
        'Walkway / parking / shared green are concept layers</text>'
    )

    parts.append('</svg>')
    return "".join(parts)
