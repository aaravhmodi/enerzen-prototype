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

from dotenv import load_dotenv

load_dotenv()

_client = None
DEFAULT_TEXT_MODEL = os.environ.get("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
DEFAULT_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")


class AiUnavailableError(RuntimeError):
    """Raised when an OpenAI-backed feature can't run (no key, API error)."""


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


SPEC_JSON_SCHEMA = {
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
            "location": {"type": ["string", "null"]},
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
                      "num_units", "has_ac", "allow_gas", "assumptions"],
        "additionalProperties": False,
    },
    "strict": True,
}

_PARSE_SYSTEM_PROMPT = """You turn a homeowner/builder's freeform description of a \
housing project into a structured spec for EnerZen's building-envelope optimizer \
and site-placement engine. Fields you can't determine from the text should get a \
reasonable Ontario-residential default, and every default/guess must be listed in \
`assumptions`. floor_area_m2, footprint_length_m/width_m, lot_width_m/depth_m are \
always in metres (convert from feet/sq ft if the user gave imperial units)."""


def parse_freeform_spec(text: str) -> dict:
    """Turn a freeform project description into a dict of ProjectSpec/SiteSpec
    fields (see SPEC_JSON_SCHEMA). Raises AiUnavailableError on any failure."""
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=DEFAULT_TEXT_MODEL,
            messages=[
                {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_schema", "json_schema": SPEC_JSON_SCHEMA},
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
