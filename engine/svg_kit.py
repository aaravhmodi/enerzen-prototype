"""
Shared SVG "chrome" for site plans — landscaped ground texture, a street
band, a compass rose, a scale bar, dimension lines, and a title block —
so the technical site-plan drawings read like a land-development site
plan (rounded card, greenery, numbered buildings, legend) rather than a
bare CAD-style rectangle diagram.

Deliberately still a schematic, not a rendered aerial photo: every shape
here is generated from the same numbers driving the placement math, so
it stays accurate as inputs change, unlike a one-off AI illustration.
"""

GRASS_FILL = "#e4edd8"
GRASS_STROKE = "#4a7c3c"
ASPHALT = "#52565c"
ASPHALT_EDGE = "#d8d8d2"
INK = "#374151"
TREE_CANOPY = "#8fb377"
TREE_CANOPY_DARK = "#729a5c"

STREET_BAND_PX = 26


def defs_block() -> str:
    return (
        '<defs>'
        '<pattern id="grassTex" width="16" height="16" patternUnits="userSpaceOnUse" patternTransform="rotate(18)">'
        f'<rect width="16" height="16" fill="{GRASS_FILL}"/>'
        '<line x1="0" y1="0" x2="0" y2="16" stroke="#d3e2c2" stroke-width="2"/>'
        '</pattern>'
        '<marker id="svgKitArrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">'
        f'<path d="M0,0 L8,4 L0,8 z" fill="{INK}"/>'
        '</marker>'
        '</defs>'
    )


def lot_ground(x: float, y: float, w: float, h: float, rx: float = 12) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
        f'fill="url(#grassTex)" stroke="{GRASS_STROKE}" stroke-width="2"/>'
    )


def tree(cx: float, cy: float, r: float = 5) -> str:
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{TREE_CANOPY}" '
        f'stroke="{TREE_CANOPY_DARK}" stroke-width="0.75"/>'
    )


def tree_row(x0: float, y0: float, x1: float, y1: float, count: int, r: float = 4.5) -> str:
    """A row of small tree canopies along a straight edge, evenly spaced."""
    if count <= 0:
        return ""
    parts = []
    for i in range(count):
        t = (i + 0.5) / count
        parts.append(tree(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r))
    return "".join(parts)


def street_band(street_side: str, lot_x: float, lot_y: float, lot_w: float, lot_h: float,
                 band_px: float = STREET_BAND_PX) -> str:
    """An asphalt strip with a dashed centreline along the street-facing edge,
    drawn just outside the lot boundary."""
    if street_side == "N":
        x, y, w, h = lot_x, lot_y - band_px, lot_w, band_px
        cl = f'<line x1="{x:.1f}" y1="{y + h / 2:.1f}" x2="{x + w:.1f}" y2="{y + h / 2:.1f}"'
    elif street_side == "S":
        x, y, w, h = lot_x, lot_y + lot_h, lot_w, band_px
        cl = f'<line x1="{x:.1f}" y1="{y + h / 2:.1f}" x2="{x + w:.1f}" y2="{y + h / 2:.1f}"'
    elif street_side == "W":
        x, y, w, h = lot_x - band_px, lot_y, band_px, lot_h
        cl = f'<line x1="{x + w / 2:.1f}" y1="{y:.1f}" x2="{x + w / 2:.1f}" y2="{y + h:.1f}"'
    else:  # "E"
        x, y, w, h = lot_x + lot_w, lot_y, band_px, lot_h
        cl = f'<line x1="{x + w / 2:.1f}" y1="{y:.1f}" x2="{x + w / 2:.1f}" y2="{y + h:.1f}"'
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{ASPHALT}"/>'
        f'{cl} stroke="{ASPHALT_EDGE}" stroke-width="1.5" stroke-dasharray="6,5"/>'
    )


def compass(cx: float, cy: float, r: float = 15) -> str:
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="white" stroke="{INK}" stroke-width="1.2"/>'
        f'<line x1="{cx:.1f}" y1="{cy + r - 3:.1f}" x2="{cx:.1f}" y2="{cy - r + 4:.1f}" '
        f'stroke="{INK}" stroke-width="1.6" marker-end="url(#svgKitArrow)"/>'
        f'<text x="{cx:.1f}" y="{cy - r - 4:.1f}" text-anchor="middle" font-size="10" '
        f'font-weight="700" fill="{INK}">N</text>'
    )


def scale_bar(x: float, y: float, px_per_m: float, metres: float = 10) -> str:
    length = metres * px_per_m
    return (
        f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{x + length:.0f}" y2="{y:.0f}" stroke="{INK}" stroke-width="2"/>'
        f'<line x1="{x:.0f}" y1="{y - 4:.0f}" x2="{x:.0f}" y2="{y + 4:.0f}" stroke="{INK}" stroke-width="1.5"/>'
        f'<line x1="{x + length:.0f}" y1="{y - 4:.0f}" x2="{x + length:.0f}" y2="{y + 4:.0f}" '
        f'stroke="{INK}" stroke-width="1.5"/>'
        f'<text x="{x + length / 2:.0f}" y="{y - 6:.0f}" text-anchor="middle" font-size="10" '
        f'fill="{INK}">{metres:g} m</text>'
    )


def title_block(x: float, y: float, title: str, subtitle: str = "") -> str:
    parts = [
        f'<text x="{x:.0f}" y="{y:.0f}" font-size="13" font-weight="700" letter-spacing="1.5" '
        f'fill="{INK}">{title.upper()}</text>'
    ]
    if subtitle:
        parts.append(
            f'<text x="{x:.0f}" y="{y + 15:.0f}" font-size="9.5" fill="#78716c">{subtitle}</text>'
        )
    return "".join(parts)


def dimension_line(x0: float, y0: float, x1: float, y1: float, label: str, offset: float = 10) -> str:
    """A short dimension line with end ticks and a centred label, offset
    perpendicular to the run — used to call out setback distances."""
    horizontal = abs(x1 - x0) >= abs(y1 - y0)
    if horizontal:
        ly = y0 - offset
        cx = (x0 + x1) / 2
        return (
            f'<line x1="{x0:.1f}" y1="{ly:.1f}" x2="{x1:.1f}" y2="{ly:.1f}" '
            f'stroke="{INK}" stroke-width="1" stroke-dasharray="3,2"/>'
            f'<line x1="{x0:.1f}" y1="{ly - 3:.1f}" x2="{x0:.1f}" y2="{ly + 3:.1f}" stroke="{INK}" stroke-width="1"/>'
            f'<line x1="{x1:.1f}" y1="{ly - 3:.1f}" x2="{x1:.1f}" y2="{ly + 3:.1f}" stroke="{INK}" stroke-width="1"/>'
            f'<text x="{cx:.1f}" y="{ly - 3:.1f}" text-anchor="middle" font-size="8.5" fill="{INK}">{label}</text>'
        )
    lx = x0 - offset
    cy = (y0 + y1) / 2
    return (
        f'<line x1="{lx:.1f}" y1="{y0:.1f}" x2="{lx:.1f}" y2="{y1:.1f}" '
        f'stroke="{INK}" stroke-width="1" stroke-dasharray="3,2"/>'
        f'<line x1="{lx - 3:.1f}" y1="{y0:.1f}" x2="{lx + 3:.1f}" y2="{y0:.1f}" stroke="{INK}" stroke-width="1"/>'
        f'<line x1="{lx - 3:.1f}" y1="{y1:.1f}" x2="{lx + 3:.1f}" y2="{y1:.1f}" stroke="{INK}" stroke-width="1"/>'
        f'<text x="{lx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="8.5" fill="{INK}" '
        f'transform="rotate(-90 {lx:.1f} {cy:.1f})">{label}</text>'
    )


def setback_dimensions(street_side: str, e_x0: float, e_y0: float, e_x1: float, e_y1: float,
                        lot_x: float, lot_y: float, lot_w: float, lot_h: float,
                        front_m: float, side_m: float, rear_m: float) -> str:
    """Dimension-line callouts for the four setback gaps between the lot
    boundary and the buildable envelope, labelled with their real distances."""
    parts = []
    if street_side in ("N", "S"):
        mid_y = (e_y0 + e_y1) / 2
        parts.append(dimension_line(lot_x, mid_y, e_x0, mid_y, f"{side_m:g} m", offset=8))
        parts.append(dimension_line(e_x1, mid_y, lot_x + lot_w, mid_y, f"{side_m:g} m", offset=8))
        mid_x = (e_x0 + e_x1) / 2
        if street_side == "N":
            front_gap, rear_gap = (lot_y, e_y0), (e_y1, lot_y + lot_h)
        else:
            front_gap, rear_gap = (e_y1, lot_y + lot_h), (lot_y, e_y0)
        parts.append(dimension_line(mid_x, front_gap[0], mid_x, front_gap[1], f"{front_m:g} m", offset=10))
        parts.append(dimension_line(mid_x, rear_gap[0], mid_x, rear_gap[1], f"{rear_m:g} m", offset=10))
    else:
        mid_x = (e_x0 + e_x1) / 2
        parts.append(dimension_line(mid_x, lot_y, mid_x, e_y0, f"{side_m:g} m", offset=10))
        parts.append(dimension_line(mid_x, e_y1, mid_x, lot_y + lot_h, f"{side_m:g} m", offset=10))
        mid_y = (e_y0 + e_y1) / 2
        if street_side == "W":
            front_gap, rear_gap = (lot_x, e_x0), (e_x1, lot_x + lot_w)
        else:
            front_gap, rear_gap = (e_x1, lot_x + lot_w), (lot_x, e_x0)
        parts.append(dimension_line(front_gap[0], mid_y, front_gap[1], mid_y, f"{front_m:g} m", offset=8))
        parts.append(dimension_line(rear_gap[0], mid_y, rear_gap[1], mid_y, f"{rear_m:g} m", offset=8))
    return "".join(parts)


def numbered_badge(cx: float, cy: float, number: int, fill: str = "#0f766e") -> str:
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" fill="{fill}" stroke="white" stroke-width="1.5"/>'
        f'<text x="{cx:.1f}" y="{cy + 3.2:.1f}" text-anchor="middle" font-size="9.5" '
        f'font-weight="700" fill="white">{number}</text>'
    )
