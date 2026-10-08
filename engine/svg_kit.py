"""
Shared drawing kit for site plans.

A quiet architectural sheet in the app's visual language: warm paper,
charcoal linework, a trace of lavender, muted landscape tones. Every layer
is a plain primitive with a hex colour, because engine/ai.py rasterizes the
same SVG (without transforms or gradients) as a reference image.

Layers are wrapped in classed groups (sp-ground, sp-landscape, sp-access,
sp-building, sp-annotation) so the web app can animate them in sequence.
"""

from dataclasses import dataclass, field
from html import escape

FONT = "Inter, 'Helvetica Neue', Arial, sans-serif"

PAPER = "#fbfaf8"
LOT_FILL = "#f4f5f0"
INK = "#2f2a35"
LINE = "#6f6878"
MUTED = "#a39caa"
HAIRLINE = "#e4dfe9"
ENVELOPE = "#b9aecb"
ROAD = "#ebe8ee"
SIDEWALK = "#f6f4f7"
PAVING = "#ece8e3"
PAVING_EDGE = "#d6cfc7"
GREEN = "#e3eadc"
GREEN_EDGE = "#c3cfb9"
TREE = "#cddabf"
TREE_EDGE = "#9fb291"
WATER = "#dde7ee"
WATER_EDGE = "#a8bccb"
SOLAR = "#c49a5c"
SHADOW = "#e3dfe8"
PORCH = "#f2ece3"
PORCH_EDGE = "#c9b394"
WARN = "#9a4d5c"

ROAD_PX = 24
SIDEWALK_PX = 10
STREET_BAND_PX = ROAD_PX + SIDEWALK_PX
MARGIN_PX = 52
MIN_SHEET_W = 460


def text_width(text: str, size: float) -> float:
    return len(text) * size * 0.56


def text(x: float, y: float, value: str, size: float = 9, fill: str = LINE, anchor: str = "start",
         weight: int = 400, spacing: float = 0, rotate: bool = False, extra: str = "") -> str:
    rot = f' transform="rotate(-90 {x:.1f} {y:.1f})"' if rotate else ""
    ls = f' letter-spacing="{spacing:g}"' if spacing else ""
    fw = f' font-weight="{weight}"' if weight != 400 else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:g}" fill="{fill}" '
            f'text-anchor="{anchor}"{fw}{ls}{rot}{extra}>{escape(value)}</text>')


@dataclass
class PlanSheet:
    """Places a lot on a sheet: an adaptive scale, street band, margins for
    dimension strings, and a footer region below for the key and legend."""
    lot_w_m: float
    lot_d_m: float
    street_side: str
    scale: float = 0
    left: float = 0
    top: float = 0
    width: float = 0
    footer_y: float = 0
    body: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.scale = max(5.0, min(16.0, 440.0 / max(self.lot_w_m, self.lot_d_m, 1)))
        band = STREET_BAND_PX
        self.lot_w_px = self.lot_w_m * self.scale
        self.lot_h_px = self.lot_d_m * self.scale
        left = MARGIN_PX + (band if self.street_side == "W" else 0)
        right = MARGIN_PX + (band if self.street_side == "E" else 0)
        content_w = left + self.lot_w_px + right
        self.width = max(content_w, MIN_SHEET_W)
        self.left = left + (self.width - content_w) / 2
        self.top = MARGIN_PX + (band if self.street_side == "N" else 0)
        bottom_band = band if self.street_side == "S" else 0
        self.footer_y = self.top + self.lot_h_px + bottom_band + 44

    def px(self, x_m: float, y_m: float) -> tuple[float, float]:
        return self.left + x_m * self.scale, self.top + y_m * self.scale

    def points(self, coords) -> str:
        return " ".join(f"{self.px(x, y)[0]:.1f},{self.px(x, y)[1]:.1f}" for x, y in coords)

    def rect_m(self, x0: float, y0: float, x1: float, y1: float, fill: str, stroke: str = "none",
               width: float = 1, extra: str = "") -> str:
        a, b = self.px(x0, y0)
        c, d = self.px(x1, y1)
        stroke_attr = f' stroke="{stroke}" stroke-width="{width:g}"' if stroke != "none" else ' stroke="none"'
        return (f'<rect x="{a:.1f}" y="{b:.1f}" width="{c - a:.1f}" height="{d - b:.1f}" '
                f'fill="{fill}"{stroke_attr}{extra}/>')

    # ── Ground ─────────────────────────────────────────────────────────────
    def ground(self, envelope) -> str:
        x, y, w, h = self.left, self.top, self.lot_w_px, self.lot_h_px
        e0 = self.px(envelope.x0, envelope.y0)
        e1 = self.px(envelope.x1, envelope.y1)
        return (
            '<g class="sp-ground">'
            + self.street()
            + f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{LOT_FILL}" '
              f'stroke="{INK}" stroke-width="1.4"/>'
            + f'<rect x="{e0[0]:.1f}" y="{e0[1]:.1f}" width="{e1[0] - e0[0]:.1f}" height="{e1[1] - e0[1]:.1f}" '
              f'fill="none" stroke="{ENVELOPE}" stroke-width="1" stroke-dasharray="4,3"/>'
            + '</g>'
        )

    def street(self) -> str:
        """Sidewalk against the property line, then the road with a centre line."""
        x, y, w, h = self.left, self.top, self.lot_w_px, self.lot_h_px
        s, r = SIDEWALK_PX, ROAD_PX
        side = self.street_side
        if side == "N":
            walk = (x, y - s, w, s)
            road = (x - 12, y - s - r, w + 24, r)
        elif side == "S":
            walk = (x, y + h, w, s)
            road = (x - 12, y + h + s, w + 24, r)
        elif side == "W":
            walk = (x - s, y, s, h)
            road = (x - s - r, y - 12, r, h + 24)
        else:
            walk = (x + w, y, s, h)
            road = (x + w + s, y - 12, r, h + 24)
        rx, ry, rw, rh = road
        parts = [
            f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" fill="{ROAD}" stroke="none"/>',
            f'<rect id="public-sidewalk" x="{walk[0]:.1f}" y="{walk[1]:.1f}" width="{walk[2]:.1f}" '
            f'height="{walk[3]:.1f}" fill="{SIDEWALK}" stroke="{HAIRLINE}" stroke-width="0.8"/>',
        ]
        if side in ("N", "S"):
            cy = ry + rh / 2
            parts.append(f'<line x1="{rx + 8:.1f}" y1="{cy:.1f}" x2="{rx + rw - 8:.1f}" y2="{cy:.1f}" '
                         f'stroke="white" stroke-width="1.2" stroke-dasharray="10,8"/>')
            label_w = text_width("STREET", 7.5) + 18
            parts.append(f'<rect x="{rx + rw / 2 - label_w / 2:.1f}" y="{cy - 6:.1f}" width="{label_w:.1f}" '
                         f'height="12" fill="{ROAD}" stroke="none"/>')
            parts.append(text(rx + rw / 2, cy + 2.6, "STREET", 7.5, LINE, "middle", 500, 2))
        else:
            cx = rx + rw / 2
            parts.append(f'<line x1="{cx:.1f}" y1="{ry + 8:.1f}" x2="{cx:.1f}" y2="{ry + rh - 8:.1f}" '
                         f'stroke="white" stroke-width="1.2" stroke-dasharray="10,8"/>')
            label_w = text_width("STREET", 7.5) + 18
            parts.append(f'<rect x="{cx - 6:.1f}" y="{ry + rh / 2 - label_w / 2:.1f}" width="12" '
                         f'height="{label_w:.1f}" fill="{ROAD}" stroke="none"/>')
            parts.append(text(cx + 2.6, ry + rh / 2, "STREET", 7.5, LINE, "middle", 500, 2, rotate=True))
        return "".join(parts)

    # ── Buildings ──────────────────────────────────────────────────────────
    def building(self, x0: float, y0: float, x1: float, y1: float, fill: str, stroke: str,
                 index: int, solar_side: str | None, extra: str = "") -> str:
        """A footprint with a soft offset shadow and, when given, an accent on
        the solar-facing edge. The caller adds any detail and closes the group."""
        a, b = self.px(x0, y0)
        c, d = self.px(x1, y1)
        w, h = c - a, d - b
        parts = [
            f'<g class="sp-building" style="--i:{index}">',
            f'<rect x="{a + 2.5:.1f}" y="{b + 2.5:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{SHADOW}" stroke="none"/>',
            f'<rect x="{a:.1f}" y="{b:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="1.3"{extra}/>',
        ]
        if solar_side:
            edge = {"N": (a, b, c, b), "S": (a, d, c, d), "E": (c, b, c, d), "W": (a, b, a, d)}[solar_side]
            parts.append(f'<line x1="{edge[0]:.1f}" y1="{edge[1]:.1f}" x2="{edge[2]:.1f}" y2="{edge[3]:.1f}" '
                         f'stroke="{SOLAR}" stroke-width="2.6"/>')
        return "".join(parts)

    # ── Annotation ─────────────────────────────────────────────────────────
    def dimension(self, x0: float, y0: float, x1: float, y1: float, label: str) -> str:
        """A thin dimension string with architectural slash ticks and a label
        set on a paper-coloured break in the line."""
        parts = [f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{MUTED}" stroke-width="0.8"/>']
        for tx, ty in ((x0, y0), (x1, y1)):
            parts.append(f'<line x1="{tx - 3:.1f}" y1="{ty + 3:.1f}" x2="{tx + 3:.1f}" y2="{ty - 3:.1f}" '
                         f'stroke="{LINE}" stroke-width="1"/>')
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        lw = text_width(label, 8.5) + 10
        if abs(x1 - x0) >= abs(y1 - y0):
            parts.append(f'<rect x="{cx - lw / 2:.1f}" y="{cy - 6:.1f}" width="{lw:.1f}" height="12" '
                         f'fill="{PAPER}" stroke="none"/>')
            parts.append(text(cx, cy + 3, label, 8.5, LINE, "middle"))
        else:
            parts.append(f'<rect x="{cx - 6:.1f}" y="{cy - lw / 2:.1f}" width="12" height="{lw:.1f}" '
                         f'fill="{PAPER}" stroke="none"/>')
            parts.append(text(cx + 3, cy, label, 8.5, LINE, "middle", rotate=True))
        return "".join(parts)

    def overall_dimensions(self) -> str:
        x, y, w, h = self.left, self.top, self.lot_w_px, self.lot_h_px
        width_label = f"{self.lot_w_m:g} m"
        depth_label = f"{self.lot_d_m:g} m"
        wy = y - 20 if self.street_side == "S" else y + h + 20
        dx = x - 20 if self.street_side == "E" else x + w + 20
        return self.dimension(x, wy, x + w, wy, width_label) + self.dimension(dx, y, dx, y + h, depth_label)

    def compass(self, cx: float, cy: float) -> str:
        return (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="12" fill="none" stroke="{HAIRLINE}" stroke-width="1"/>'
            f'<polygon points="{cx:.1f},{cy - 9:.1f} {cx + 3.6:.1f},{cy + 5:.1f} {cx:.1f},{cy + 2.4:.1f} '
            f'{cx - 3.6:.1f},{cy + 5:.1f}" fill="{INK}" stroke="none"/>'
            + text(cx, cy - 15, "N", 8, INK, "middle", 600)
        )

    def scale_bar(self, x: float, y: float) -> str:
        metres = next((m for m in (5, 10, 20, 50, 100) if m * self.scale >= 60), 100)
        length = metres * self.scale
        half = length / 2
        return (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{half:.1f}" height="3" fill="{INK}" stroke="none"/>'
            f'<rect x="{x + half:.1f}" y="{y:.1f}" width="{half:.1f}" height="3" fill="white" stroke="{INK}" stroke-width="0.8"/>'
            + text(x, y + 14, "0", 7.5, MUTED)
            + text(x + length, y + 14, f"{metres:g} m", 7.5, MUTED, "middle")
        )

    def footer(self, title: str, fields: list[tuple[str, str]], legend: list[tuple[str, str]],
               notes: list[tuple[str, str]]) -> float:
        """Scale, compass, title, key fields, a wrapping legend and fine print.
        Appends to the sheet body and returns the sheet's total height.

        Legend entries are (swatch_svg_kind, label); kinds are 'fill:#hex:#edge',
        'line:#hex', 'dash:#hex', 'dot:#hex', 'badge:#hex:N'.
        """
        x = self.left
        avail = max(self.lot_w_px, MIN_SHEET_W - 2 * MARGIN_PX)
        y = self.footer_y
        out = ['<g class="sp-annotation sp-footer">']
        out.append(self.scale_bar(x, y))
        out.append(self.compass(x + avail - 12, y + 4))
        y += 34
        out.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + avail:.1f}" y2="{y:.1f}" stroke="{HAIRLINE}" stroke-width="1"/>')
        y += 22
        out.append(text(x, y, title.upper(), 9.5, INK, "start", 600, 1.6))
        y += 20
        for label, value in fields:
            out.append(text(x, y, label, 8.5, MUTED))
            out.append(text(x + 86, y, value, 9, INK, "start", 500))
            y += 15
        y += 10
        cursor = x
        for kind, label in legend:
            item_w = 20 + text_width(label, 8.5) + 18
            if cursor > x and cursor + item_w > x + avail:
                cursor = x
                y += 18
            out.append(_swatch(kind, cursor, y - 3))
            out.append(text(cursor + 20, y, label, 8.5, LINE))
            cursor += item_w
        y += 8
        for colour, note in notes:
            y += 15
            out.append(text(x, y, note, 8, colour))
        out.append('</g>')
        self.body.extend(out)
        return y + 28

    def render(self, height: float) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width:.0f}" height="{height:.0f}" '
            f'viewBox="0 0 {self.width:.0f} {height:.0f}" font-family="{FONT}">'
            f'<rect x="0" y="0" width="{self.width:.0f}" height="{height:.0f}" fill="{PAPER}" stroke="none"/>'
            + "".join(self.body)
            + '</svg>'
        )


def _swatch(kind: str, x: float, cy: float) -> str:
    parts = kind.split(":")
    if parts[0] == "fill":
        edge = parts[2] if len(parts) > 2 else parts[1]
        return (f'<rect x="{x:.1f}" y="{cy - 4.5:.1f}" width="13" height="9" fill="{parts[1]}" '
                f'stroke="{edge}" stroke-width="0.9"/>')
    if parts[0] == "line":
        return f'<line x1="{x:.1f}" y1="{cy:.1f}" x2="{x + 13:.1f}" y2="{cy:.1f}" stroke="{parts[1]}" stroke-width="2.6"/>'
    if parts[0] == "dash":
        return (f'<line x1="{x:.1f}" y1="{cy:.1f}" x2="{x + 13:.1f}" y2="{cy:.1f}" stroke="{parts[1]}" '
                f'stroke-width="1" stroke-dasharray="4,3"/>')
    if parts[0] == "dot":
        return f'<circle cx="{x + 6.5:.1f}" cy="{cy:.1f}" r="4.5" fill="{parts[1]}" stroke="{parts[2] if len(parts) > 2 else parts[1]}" stroke-width="0.9"/>'
    if parts[0] == "badge":
        return numbered_badge(x + 6.5, cy, int(parts[2]), parts[1])
    return ""


def numbered_badge(cx: float, cy: float, number: int, fill: str = INK) -> str:
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6.5" fill="{fill}" stroke="white" stroke-width="1.2"/>'
        f'<text x="{cx:.1f}" y="{cy + 2.6:.1f}" text-anchor="middle" font-size="7.5" '
        f'font-weight="600" fill="white">{number}</text>'
    )
