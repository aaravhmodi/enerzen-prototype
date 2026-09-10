"""
Shared SVG chrome for site plans: a clean technical drawing — white
background, black/grey linework, full dimension strings, a bordered title
block — matching what an actual site-plan submission or client drawing
looks like, not a marketing illustration.
"""

INK = "#1f2937"
LINE = "#4b5563"
DIM_LINE = "#374151"
DASH_ENVELOPE = "#9ca3af"
BUILDING_FILL = "#f8fafc"

STREET_BAND_PX = 22


def defs_block() -> str:
    return (
        '<defs>'
        '<marker id="svgKitArrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">'
        f'<path d="M0,0 L8,4 L0,8 z" fill="{INK}"/>'
        '</marker>'
        '</defs>'
    )


def lot_boundary(x: float, y: float, w: float, h: float) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="white" stroke="{INK}" stroke-width="1.75"/>'


def street_edge(street_side: str, lot_x: float, lot_y: float, lot_w: float, lot_h: float,
                 label: str = "STREET", band_px: float = STREET_BAND_PX) -> str:
    """A line + perpendicular hatch ticks along the street-facing edge,
    with a label — the way a road allowance reads on a real site plan."""
    if street_side == "N":
        x0, y0, x1, y1 = lot_x, lot_y - band_px, lot_x + lot_w, lot_y - band_px
        lx, ly = lot_x + lot_w / 2, y0 - 6
        ticks = [(lot_x + t * lot_w, y0 - 5, lot_x + t * lot_w, y0 + 5) for t in (0.15, 0.5, 0.85)]
    elif street_side == "S":
        x0, y0, x1, y1 = lot_x, lot_y + lot_h + band_px, lot_x + lot_w, lot_y + lot_h + band_px
        lx, ly = lot_x + lot_w / 2, y0 + 14
        ticks = [(lot_x + t * lot_w, y0 - 5, lot_x + t * lot_w, y0 + 5) for t in (0.15, 0.5, 0.85)]
    elif street_side == "W":
        x0, y0, x1, y1 = lot_x - band_px, lot_y, lot_x - band_px, lot_y + lot_h
        lx, ly = x0 - 8, lot_y + lot_h / 2
        ticks = [(x0 - 5, lot_y + t * lot_h, x0 + 5, lot_y + t * lot_h) for t in (0.15, 0.5, 0.85)]
    else:  # "E"
        x0, y0, x1, y1 = lot_x + lot_w + band_px, lot_y, lot_x + lot_w + band_px, lot_y + lot_h
        lx, ly = x0 + 8, lot_y + lot_h / 2
        ticks = [(x0 - 5, lot_y + t * lot_h, x0 + 5, lot_y + t * lot_h) for t in (0.15, 0.5, 0.85)]

    parts = [f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{LINE}" stroke-width="1.25"/>']
    for tx0, ty0, tx1, ty1 in ticks:
        parts.append(f'<line x1="{tx0:.1f}" y1="{ty0:.1f}" x2="{tx1:.1f}" y2="{ty1:.1f}" stroke="{LINE}" stroke-width="1"/>')
    rot = f' transform="rotate(-90 {lx:.1f} {ly:.1f})"' if street_side in ("W", "E") else ""
    parts.append(
        f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="9" '
        f'letter-spacing="1" fill="{LINE}"{rot}>{label}</text>'
    )
    return "".join(parts)


def compass(cx: float, cy: float, r: float = 13) -> str:
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="white" stroke="{INK}" stroke-width="1"/>'
        f'<line x1="{cx:.1f}" y1="{cy + r - 3:.1f}" x2="{cx:.1f}" y2="{cy - r + 4:.1f}" '
        f'stroke="{INK}" stroke-width="1.4" marker-end="url(#svgKitArrow)"/>'
        f'<text x="{cx:.1f}" y="{cy - r - 4:.1f}" text-anchor="middle" font-size="9" '
        f'font-weight="700" fill="{INK}">N</text>'
    )


def scale_bar(x: float, y: float, px_per_m: float, metres: float = 10) -> str:
    length = metres * px_per_m
    return (
        f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{x + length:.0f}" y2="{y:.0f}" stroke="{INK}" stroke-width="1.5"/>'
        f'<line x1="{x:.0f}" y1="{y - 4:.0f}" x2="{x:.0f}" y2="{y + 4:.0f}" stroke="{INK}" stroke-width="1"/>'
        f'<line x1="{x + length:.0f}" y1="{y - 4:.0f}" x2="{x + length:.0f}" y2="{y + 4:.0f}" '
        f'stroke="{INK}" stroke-width="1"/>'
        f'<text x="{x + length / 2:.0f}" y="{y - 6:.0f}" text-anchor="middle" font-size="9" '
        f'fill="{INK}">{metres:g} m</text>'
    )


def title_block(x: float, y: float, w: float, title: str, fields: list[tuple[str, str]]) -> str:
    """A bordered title block with labelled fields, like a real drawing sheet."""
    row_h = 15
    h = 20 + row_h * len(fields)
    parts = [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="white" stroke="{INK}" stroke-width="1"/>',
        f'<line x1="{x:.1f}" y1="{y + 22:.1f}" x2="{x + w:.1f}" y2="{y + 22:.1f}" stroke="{INK}" stroke-width="1"/>',
        f'<text x="{x + 8:.1f}" y="{y + 15:.1f}" font-size="11" font-weight="700" letter-spacing="1" '
        f'fill="{INK}">{title.upper()}</text>',
    ]
    fy = y + 22 + 13
    for label, value in fields:
        parts.append(
            f'<text x="{x + 8:.1f}" y="{fy:.1f}" font-size="8.5" fill="#6b7280">{label}: '
            f'<tspan fill="{INK}" font-weight="600">{value}</tspan></text>'
        )
        fy += row_h
    return "".join(parts)


def dimension_line(x0: float, y0: float, x1: float, y1: float, label: str, offset: float = 10) -> str:
    """A dimension line with end ticks and a centred label, offset
    perpendicular to the run — the standard way to call out a distance."""
    horizontal = abs(x1 - x0) >= abs(y1 - y0)
    if horizontal:
        ly = y0 - offset
        cx = (x0 + x1) / 2
        return (
            f'<line x1="{x0:.1f}" y1="{ly:.1f}" x2="{x1:.1f}" y2="{ly:.1f}" '
            f'stroke="{DIM_LINE}" stroke-width="0.9" stroke-dasharray="3,2"/>'
            f'<line x1="{x0:.1f}" y1="{ly - 3:.1f}" x2="{x0:.1f}" y2="{ly + 3:.1f}" stroke="{DIM_LINE}" stroke-width="1"/>'
            f'<line x1="{x1:.1f}" y1="{ly - 3:.1f}" x2="{x1:.1f}" y2="{ly + 3:.1f}" stroke="{DIM_LINE}" stroke-width="1"/>'
            f'<text x="{cx:.1f}" y="{ly - 3:.1f}" text-anchor="middle" font-size="8.5" fill="{DIM_LINE}">{label}</text>'
        )
    lx = x0 - offset
    cy = (y0 + y1) / 2
    return (
        f'<line x1="{lx:.1f}" y1="{y0:.1f}" x2="{lx:.1f}" y2="{y1:.1f}" '
        f'stroke="{DIM_LINE}" stroke-width="0.9" stroke-dasharray="3,2"/>'
        f'<line x1="{lx - 3:.1f}" y1="{y0:.1f}" x2="{lx + 3:.1f}" y2="{y0:.1f}" stroke="{DIM_LINE}" stroke-width="1"/>'
        f'<line x1="{lx - 3:.1f}" y1="{y1:.1f}" x2="{lx + 3:.1f}" y2="{y1:.1f}" stroke="{DIM_LINE}" stroke-width="1"/>'
        f'<text x="{lx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="8.5" fill="{DIM_LINE}" '
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


def overall_dimensions(lot_x: float, lot_y: float, lot_w: float, lot_h: float,
                        width_m: float, depth_m: float, width_offset: float, depth_offset: float) -> str:
    """Overall lot width/depth dimension strings, offset further out than
    the setback callouts so the two don't collide."""
    return (
        dimension_line(lot_x, lot_y + lot_h, lot_x + lot_w, lot_y + lot_h, f"{width_m:g} m", offset=width_offset)
        + dimension_line(lot_x + lot_w, lot_y, lot_x + lot_w, lot_y + lot_h, f"{depth_m:g} m", offset=depth_offset)
    )


def numbered_badge(cx: float, cy: float, number: int, fill: str = "#374151") -> str:
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8.5" fill="{fill}" stroke="white" stroke-width="1.25"/>'
        f'<text x="{cx:.1f}" y="{cy + 3:.1f}" text-anchor="middle" font-size="9" '
        f'font-weight="700" fill="white">{number}</text>'
    )
