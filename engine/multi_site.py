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

_SCALE_PX_PER_M = 8
_MARGIN_PX = 50
_GAP_M = 3.0       # gap between buildings (E-W and N-S)

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

    # Sort blocks tallest-first (N-S) so large buildings go at the rear
    blocks.sort(key=lambda b: b[2], reverse=True)

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
    """SVG site plan in the style of a land-development drawing: landscaped
    ground, a street band, numbered building badges with a legend (as in a
    land-dev site-plan sheet), a compass rose, a scale bar, and a title
    block — built from the same placement numbers, not a one-off illustration."""
    from engine import svg_kit

    top = _MARGIN_PX + (svg_kit.STREET_BAND_PX if lot.street_side == "N" else 0)
    bottom = _MARGIN_PX + (svg_kit.STREET_BAND_PX if lot.street_side == "S" else 0) + 96
    left = _MARGIN_PX + (svg_kit.STREET_BAND_PX if lot.street_side == "W" else 0)
    right = _MARGIN_PX + (svg_kit.STREET_BAND_PX if lot.street_side == "E" else 0)

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

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w_px:.0f}" height="{h_px:.0f}" '
        f'viewBox="0 0 {w_px:.0f} {h_px:.0f}" font-family="sans-serif">',
        svg_kit.defs_block(),
        svg_kit.street_band(lot.street_side, left, top, lot_w_px, lot_h_px),
        svg_kit.lot_ground(left, top, lot_w_px, lot_h_px),
        svg_kit.tree_row(left, top, left + lot_w_px, top, max(2, int(lot.lot_width_m // 8))) if lot.street_side != "N" else "",
        svg_kit.tree_row(left, top + lot_h_px, left + lot_w_px, top + lot_h_px, max(2, int(lot.lot_width_m // 8))) if lot.street_side != "S" else "",
        f'<rect x="{e_x0:.1f}" y="{e_y0:.1f}" width="{e_x1 - e_x0:.1f}" height="{e_y1 - e_y0:.1f}" '
        f'fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="6,4"/>',
    ]

    # Buildings — numbered badges so the legend below can key them, like a
    # land-dev site plan's numbered building callouts.
    archetype_order = [a for a in mix if mix.get(a, 0) > 0]
    number_by_archetype = {a: i + 1 for i, a in enumerate(archetype_order)}
    for p in placements:
        fill, stroke = _ARCHETYPE_COLORS.get(p.archetype_id, _DEFAULT_COLOR)
        bx0, by0 = px(p.x_m, p.y_m)
        bw_px = p.w_m * _SCALE_PX_PER_M
        bh_px = p.h_m * _SCALE_PX_PER_M
        cx = bx0 + bw_px / 2
        cy = by0 + bh_px / 2
        parts.append(
            f'<rect x="{bx0:.1f}" y="{by0:.1f}" width="{bw_px:.1f}" height="{bh_px:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2" rx="2"/>'
        )
        if bw_px > 16 and bh_px > 16:
            parts.append(svg_kit.numbered_badge(cx, cy, number_by_archetype.get(p.archetype_id, 0), stroke))

    parts.append(svg_kit.compass(w_px - right / 2, top / 2 + 4 if top > 20 else 16))
    parts.append(svg_kit.scale_bar(
        left, top + lot_h_px + (svg_kit.STREET_BAND_PX if lot.street_side == "S" else 0) + 20, _SCALE_PX_PER_M
    ))

    # Legend — numbered like the buildings, plus the mix summary line.
    legend_y = top + lot_h_px + (svg_kit.STREET_BAND_PX if lot.street_side == "S" else 0) + 44
    parts.append(svg_kit.title_block(
        left, legend_y,
        "Development site plan",
        f"Total: {total_units} unit{'s' if total_units != 1 else ''} | "
        f"Lot {lot.lot_width_m:g}x{lot.lot_depth_m:g} m | Street: {lot.street_side}",
    ))
    legend_y += 30
    legend_x = left
    from engine.archetypes import ARCHETYPES
    for arch_id in archetype_order:
        count = mix[arch_id]
        arch = ARCHETYPES[arch_id]
        fill, stroke = _ARCHETYPE_COLORS.get(arch_id, _DEFAULT_COLOR)
        parts.append(svg_kit.numbered_badge(legend_x + 8, legend_y - 3, number_by_archetype[arch_id], stroke))
        parts.append(
            f'<text x="{legend_x + 22:.0f}" y="{legend_y:.0f}" font-size="10" fill="#374151">'
            f'{arch.name} × {count}</text>'
        )
        legend_x += 170

    parts.append('</svg>')
    return "".join(parts)
