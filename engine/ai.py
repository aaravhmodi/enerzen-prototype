"""
OpenAI integration: freeform-text spec parsing, an optional illustrative
concept render of a computed site plan, and short design-rationale text for
the PDF report.

Deliberately NOT used for: computing the site layout itself. Text-to-image
models cannot hold exact setback distances or right angles, so the layout
geometry always comes from `engine.site.place_building` (rule-based);
`generate_concept_render` only decorates an already-computed layout.

Every public function fails soft: if the API key is missing or the call
errors, they raise `AiUnavailableError` so callers can fall back to the
deterministic output instead of crashing the request.
"""

import json
import os
import re
import xml.etree.ElementTree as ET
from io import BytesIO

from dotenv import load_dotenv

load_dotenv()

_client = None
DEFAULT_TEXT_MODEL = os.environ.get("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
DEFAULT_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")


class AiUnavailableError(RuntimeError):
    """Raised when an OpenAI-backed feature can't run (no key, API error)."""


def _svg_reference_png(svg: str) -> bytes:
    """Rasterize the plan's basic vector primitives without native libraries."""
    from PIL import Image, ImageDraw

    root = ET.fromstring(svg)
    view_box = [float(value) for value in root.attrib.get("viewBox", "0 0 1024 1024").split()]
    view_x, view_y, view_w, view_h = view_box
    scale = min(1536 / view_w, 1024 / view_h)
    output_w, output_h = round(view_w * scale), round(view_h * scale)
    image = Image.new("RGB", (output_w, output_h), "white")
    draw = ImageDraw.Draw(image)

    def point(x: float, y: float) -> tuple[int, int]:
        return round((x - view_x) * scale), round((y - view_y) * scale)

    def number(value: str | None, default: float = 0.0) -> float:
        match = re.search(r"[-+]?\d*\.?\d+", value or "")
        return float(match.group()) if match else default

    def colour(value: str | None, fallback: str) -> str | None:
        if not value or value == "none":
            return None
        if value.startswith("#"):
            return value
        return value if value in {"white", "black", "grey", "gray", "red", "blue", "green"} else fallback

    def points(value: str) -> list[tuple[int, int]]:
        values = [float(v) for v in re.findall(r"[-+]?\d*\.?\d+", value)]
        return [point(values[index], values[index + 1]) for index in range(0, len(values) - 1, 2)]

    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in {"svg", "defs", "marker", "text", "title", "desc"} or element.attrib.get("id") == "svgKitArrow":
            continue
        fill = colour(element.attrib.get("fill"), "white")
        stroke = colour(element.attrib.get("stroke"), "#64748b")
        width = max(1, round(number(element.attrib.get("stroke-width"), 1) * scale))
        if tag == "rect":
            x, y = point(number(element.attrib.get("x")), number(element.attrib.get("y")))
            right, bottom = point(
                number(element.attrib.get("x")) + number(element.attrib.get("width")),
                number(element.attrib.get("y")) + number(element.attrib.get("height")),
            )
            draw.rectangle((x, y, right, bottom), fill=fill, outline=stroke, width=width)
        elif tag == "polygon":
            polygon = points(element.attrib.get("points", ""))
            if polygon:
                draw.polygon(polygon, fill=fill, outline=stroke)
                if stroke:
                    draw.line(polygon + [polygon[0]], fill=stroke, width=width)
        elif tag == "circle":
            cx, cy = point(number(element.attrib.get("cx")), number(element.attrib.get("cy")))
            radius = number(element.attrib.get("r")) * scale
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=fill, outline=stroke, width=width)
        elif tag == "line":
            draw.line(
                [point(number(element.attrib.get("x1")), number(element.attrib.get("y1"))),
                 point(number(element.attrib.get("x2")), number(element.attrib.get("y2")))],
                fill=stroke,
                width=width,
            )
        elif tag == "path":
            path_points = points(element.attrib.get("d", ""))
            if len(path_points) >= 2:
                draw.line(path_points, fill=stroke, width=width)

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENAI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise AiUnavailableError("OPENAI_KEY is not set in the environment/.env")
    try:
        from openai import OpenAI
    except ImportError as e:
        raise AiUnavailableError("the 'openai' package is not installed") from e
    _client = OpenAI(api_key=api_key)
    return _client


def _build_spec_schema() -> dict:
    """Built at call time (not import time) so it always reflects the current
    location catalog, and so importing this module doesn't require the data
    files to already be loadable."""
    from engine.location import location_names

    return {
        "name": "project_and_site_spec",
        "schema": {
            "type": "object",
            "properties": {
                "typology": {"type": "string", "enum": ["single_family", "townhouse", "murb"]},
                "floor_area_m2": {"type": "number"},
                "storeys": {"type": "integer"},
                "orientation": {"type": "string", "enum": ["N", "S", "E", "W"]},
                "window_to_wall_ratio": {"type": "number"},
                "budget_per_unit": {"type": "number"},
                "target_label": {"type": "string", "enum": ["code", "nzr", "passive_house"]},
                "location": {
                    "type": ["string", "null"],
                    "enum": [*location_names(), None],
                    "description": "Must exactly match one of the known Ontario place names, or "
                                    "null if the text doesn't name a specific recognized place "
                                    "(a province/region name like 'Ontario' is NOT a valid value here).",
                },
                "num_units": {"type": "integer"},
                "has_ac": {"type": "boolean"},
                "allow_gas": {"type": "boolean"},
                "footprint_length_m": {"type": ["number", "null"]},
                "footprint_width_m": {"type": ["number", "null"]},
                "lot_width_m": {"type": ["number", "null"]},
                "lot_depth_m": {"type": ["number", "null"]},
                "street_side": {"type": ["string", "null"], "enum": ["N", "S", "E", "W", None]},
                "assumptions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Plain-language notes on any field the model had to guess/default.",
                },
            },
            "required": ["typology", "floor_area_m2", "storeys", "orientation",
                          "window_to_wall_ratio", "budget_per_unit", "target_label",
                          "location", "num_units", "has_ac", "allow_gas",
                          "footprint_length_m", "footprint_width_m",
                          "lot_width_m", "lot_depth_m", "street_side", "assumptions"],
            "additionalProperties": False,
        },
        "strict": True,
    }


_PARSE_SYSTEM_PROMPT = """You turn a homeowner/builder's freeform description of a \
housing project into a structured spec for EnerZen's building-envelope optimizer \
and site-placement engine. Fields you can't determine from the text should get a \
reasonable Ontario-residential default, and every default/guess must be listed in \
`assumptions`. floor_area_m2, footprint_length_m/width_m, lot_width_m/depth_m are \
always in metres (convert from feet/sq ft if the user gave imperial units). \
`location` must be an exact match from the provided enum of real Ontario place names, \
or null — never a province, county or region name."""


def parse_freeform_spec(text: str) -> dict:
    """Turn a freeform project description into a dict of ProjectSpec/SiteSpec
    fields (see _build_spec_schema). Raises AiUnavailableError on any failure."""
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=DEFAULT_TEXT_MODEL,
            messages=[
                {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_schema", "json_schema": _build_spec_schema()},
        )
        return json.loads(response.choices[0].message.content)
    except AiUnavailableError:
        raise
    except Exception as e:
        raise AiUnavailableError(f"spec parsing failed: {e}") from e


def generate_design_rationale(spec, result, layout) -> str:
    """Short (~120 word) narrative explaining the chosen orientation/placement,
    for the PDF report. `spec` is a ProjectSpec, `result` a ConfigResult,
    `layout` a SiteLayout (see engine.site)."""
    client = _get_client()
    prompt = (
        f"Building: {spec.typology}, {spec.floor_area_m2:.0f} m^2, {spec.storeys} storey(s), "
        f"orientation {spec.orientation}, target {spec.target_label}.\n"
        f"Result: EUI {result.eui_kwh_m2_yr:.0f} kWh/m2/yr, embodied carbon "
        f"{result.embodied_carbon_kg_co2e_m2:.0f} kgCO2e/m2, cost ${result.construction_cost:,.0f}.\n"
        f"Site: solar score {layout.solar_score:.2f} (1.0 = due south glazing), "
        f"fits on lot: {layout.fits_on_lot}, notes: {layout.notes or 'none'}.\n"
        "Write a short, plain-language paragraph (~120 words) explaining why this "
        "orientation and placement were chosen and what it means for the occupants' "
        "energy performance. No headings, no bullet points."
    )
    try:
        response = client.chat.completions.create(
            model=DEFAULT_TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise AiUnavailableError(f"rationale generation failed: {e}") from e


def generate_concept_render(layout, spec) -> bytes:
    """Illustrative (NOT to-scale, NOT authoritative) rendering of the site
    plan, for visual flavor alongside the precise SVG from engine.site.
    Returns raw PNG bytes."""
    client = _get_client()
    prompt = (
        f"Architectural concept illustration of a {spec.typology.replace('_', ' ')} "
        f"on a suburban Ontario lot, {spec.storeys}-storey, main glazing facing "
        f"{layout.orientation}, driveway visible, landscaped yard, daytime, "
        "top-down site-plan illustration style, clean minimal line-art with soft color "
        "fills -- not a technical drawing, no dimension labels or text."
    )
    try:
        response = client.images.generate(
            model=DEFAULT_IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
        )
        import base64
        return base64.b64decode(response.data[0].b64_json)
    except Exception as e:
        raise AiUnavailableError(f"concept render failed: {e}") from e


def generate_development_concept_render(svg: str, mix: dict[str, int]) -> bytes:
    """Polish a verified development SVG without changing its composition.

    The SVG is rasterized and passed as an image reference so the model can add
    material/landscape character while the deterministic geometry remains the
    authoritative plan.
    """
    client = _get_client()
    try:
        reference_png = _svg_reference_png(svg)
        units = ", ".join(f"{count} {unit.replace('_', ' ')}" for unit, count in mix.items() if count > 0)
        prompt = (
            "Create a polished architectural presentation rendering of the supplied site plan. "
            "Treat the reference image as a strict spatial blueprint. Preserve the exact property "
            "boundary, north orientation, building count and positions, footprint proportions, "
            "street edge, parking bays, pedestrian spine, shared green, trees, and rain garden. "
            "Add believable low-rise housing massing, roof planes, paving, planting, and soft daylight. "
            "Do not add, remove, rotate, or relocate any building, road, parking space, or landscape room. "
            "Do not invent readable labels, dimensions, numbers, or text. This is a visual presentation "
            f"render for a sustainable housing community with {units}; keep it clean and architectural."
        )
        response = client.images.edit(
            model=DEFAULT_IMAGE_MODEL,
            image=("verified-site-plan.png", reference_png, "image/png"),
            prompt=prompt,
            input_fidelity="high",
            quality="high",
            size="1536x1024",
            output_format="png",
            response_format="b64_json",
        )
        import base64
        return base64.b64decode(response.data[0].b64_json)
    except AiUnavailableError:
        raise
    except Exception as e:
        raise AiUnavailableError(f"development concept render failed: {e}") from e
