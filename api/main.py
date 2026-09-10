"""
FastAPI service wrapping the EnerZen engine: envelope optimization, deterministic
site placement, and OpenAI-backed spec parsing / rationale / concept renders.

Run: uvicorn api.main:app --reload
"""

import base64
import dataclasses
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.ai import AiUnavailableError, generate_concept_render, generate_design_rationale, parse_freeform_spec
from engine.archetypes import archetype_list
from engine.dev_optimizer import DevSpec, optimize_dev_mix
from engine.location import location_names, resolve as resolve_location
from engine.multi_site import multi_site_plan_svg, place_units
from engine.optimizer import ConfigResult, ProjectSpec, load_catalog, optimize
from engine.report import generate_results_pdf
from engine.site import SiteLayout, SiteSpec, place_building, site_plan_svg

app = FastAPI(title="EnerZen API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/response models ────────────────────────────────────────────────

class ProjectSpecIn(BaseModel):
    typology: str
    climate_zone: str = "6"
    floor_area_m2: float
    storeys: int
    orientation: str
    window_to_wall_ratio: float
    budget_per_unit: float
    target_label: str
    solar_option_id: str = "PV0"
    location: Optional[str] = None
    num_units: int = 1
    has_ac: bool = True
    allow_gas: bool = True
    footprint_length_m: Optional[float] = None
    footprint_width_m: Optional[float] = None

    def to_engine_spec(self) -> ProjectSpec:
        return ProjectSpec(**self.model_dump())


class SiteSpecIn(BaseModel):
    lot_width_m: float
    lot_depth_m: float
    street_side: str
    front_setback_m: float = 6.0
    side_setback_m: float = 1.2
    rear_setback_m: float = 7.5

    def to_engine_spec(self) -> SiteSpec:
        return SiteSpec(**self.model_dump())


class OptimizeRequest(BaseModel):
    spec: ProjectSpecIn
    weights: Optional[dict] = None
    top_n: int = 20


class SitePlanRequest(BaseModel):
    spec: ProjectSpecIn
    site: SiteSpecIn
    render_concept: bool = False


class ReportRequest(BaseModel):
    spec: ProjectSpecIn
    site: Optional[SiteSpecIn] = None
    top_n_index: int = 0
    include_rationale: bool = False


class ParseSpecRequest(BaseModel):
    text: str


class DevSpecIn(BaseModel):
    lot_width_m: float
    lot_depth_m: float
    street_side: str = "N"
    front_setback_m: float = 6.0
    side_setback_m: float = 1.2
    rear_setback_m: float = 7.5
    total_budget_cad: float
    location: str
    target_label: str = "nzr"
    allowed_types: list[str]
    orientation: str = "S"

    def to_engine_spec(self) -> DevSpec:
        return DevSpec(**self.model_dump())


class DevOptimizeRequest(BaseModel):
    spec: DevSpecIn
    top_n: int = 10


class DevSitePlanRequest(BaseModel):
    spec: DevSpecIn
    mix: dict[str, int]


def _serialize_result(result: ConfigResult) -> dict:
    data = dataclasses.asdict(result, dict_factory=lambda items: {
        k: v for k, v in items if k != "_assembly"
    })
    data.pop("_assembly", None)
    return data


def _serialize_layout(layout: SiteLayout) -> dict:
    return dataclasses.asdict(layout)


def _validate_location(location: Optional[str]) -> None:
    if location and location not in location_names():
        raise HTTPException(422, f"Unknown location {location!r}. Must be one of the /locations values.")


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/locations")
def locations():
    return {"locations": location_names()}


@app.get("/locations/{name}")
def location_detail(name: str):
    _validate_location(name)
    loc = resolve_location(name)
    return {
        "name": loc.name,
        "climate_zone": loc.climate_zone,
        "region_name": loc.region_name,
        "ground_snow_load_kpa": loc.ss,
        "associated_rain_load_kpa": loc.sr,
        "roof_snow_load_kpa": loc.roof_snow_load_kpa,
        "snow_tier": loc.snow_tier,
        "joist_depth_in": loc.joist_depth_in,
        "over_snow_range": loc.over_snow_range,
        "allowable_bearing_kpa": loc.allowable_bearing_kpa,
        "frost_depth_m": loc.frost_depth_m,
        "electricity_cad_per_kwh": loc.electricity_cad_per_kwh,
        "natural_gas_cad_per_kwh": loc.natural_gas_cad_per_kwh,
    }


@app.get("/catalog")
def catalog():
    return load_catalog()


@app.post("/optimize")
def run_optimize(req: OptimizeRequest):
    spec = req.spec.to_engine_spec()
    _validate_location(spec.location)
    results = optimize(spec, req.weights)
    if not results:
        raise HTTPException(422, "No configurations fit the given budget and target.")
    return {"results": [_serialize_result(r) for r in results[: req.top_n]]}


@app.post("/parse-spec")
def run_parse_spec(req: ParseSpecRequest):
    try:
        return parse_freeform_spec(req.text)
    except AiUnavailableError as e:
        raise HTTPException(503, str(e))


@app.post("/site-plan")
def run_site_plan(req: SitePlanRequest):
    spec = req.spec.to_engine_spec()
    site = req.site.to_engine_spec()
    layout = place_building(spec, site)
    svg = site_plan_svg(layout, spec, site)

    response = {"layout": _serialize_layout(layout), "svg": svg, "concept_render_b64": None}
    if req.render_concept:
        try:
            png_bytes = generate_concept_render(layout, spec)
            response["concept_render_b64"] = base64.b64encode(png_bytes).decode("ascii")
        except AiUnavailableError:
            pass  # concept render is illustrative-only; fail soft, SVG remains authoritative
    return response


@app.post("/report")
def run_report(req: ReportRequest):
    spec = req.spec.to_engine_spec()
    if not spec.location:
        raise HTTPException(422, "A location is required to generate a report.")
    _validate_location(spec.location)
    resolved = resolve_location(spec.location)
    if spec.footprint_length_m is None or spec.footprint_width_m is None:
        import math
        side = math.sqrt(spec.floor_area_m2)
        spec.footprint_length_m = spec.footprint_length_m or side
        spec.footprint_width_m = spec.footprint_width_m or side

    results = optimize(spec)
    if not results:
        raise HTTPException(422, "No configurations fit the given budget and target.")
    if req.top_n_index >= len(results):
        raise HTTPException(422, f"top_n_index out of range (only {len(results)} results).")
    top = results[req.top_n_index]

    catalog = load_catalog()
    labels = _report_labels(top, spec, catalog)

    pdf_bytes = generate_results_pdf(spec, top, resolved, labels)
    return {"pdf_b64": base64.b64encode(pdf_bytes).decode("ascii")}


@app.get("/archetypes")
def get_archetypes():
    return {"archetypes": archetype_list()}


@app.post("/dev-optimize")
def run_dev_optimize(req: DevOptimizeRequest):
    dev = req.spec.to_engine_spec()
    _validate_location(dev.location)
    mixes = optimize_dev_mix(dev, req.top_n)
    if not mixes:
        raise HTTPException(422, "No feasible unit-mix configurations found for the given lot, budget, and unit types.")
    return {
        "mixes": [
            {
                "units": m.units,
                "total_units": m.total_units,
                "total_cost": round(m.total_cost),
                "avg_eui_kwh_m2_yr": m.avg_eui_kwh_m2_yr,
                "avg_carbon_kg_co2e_m2": m.avg_carbon_kg_co2e_m2,
                "nzr_unit_count": m.nzr_unit_count,
                "fits_on_lot": m.fits_on_lot,
                "total_floor_area_m2": m.total_floor_area_m2,
                "avg_monthly_utility": m.avg_monthly_utility,
                "mix_label": m.mix_label,
            }
            for m in mixes
        ]
    }


@app.post("/dev-site-plan")
def run_dev_site_plan(req: DevSitePlanRequest):
    dev = req.spec.to_engine_spec()
    _validate_location(dev.location)
    site = SiteSpec(
        lot_width_m=dev.lot_width_m,
        lot_depth_m=dev.lot_depth_m,
        street_side=dev.street_side,
        front_setback_m=dev.front_setback_m,
        side_setback_m=dev.side_setback_m,
        rear_setback_m=dev.rear_setback_m,
    )
    placements = place_units(req.mix, site)
    svg = multi_site_plan_svg(placements, site, req.mix)
    return {"svg": svg}


def _report_labels(top: ConfigResult, spec: ProjectSpec, catalog: dict) -> dict:
    from engine.assemblies import FLOORS, ROOFS, WALLS

    wall_labels = {w.id: w.name for w in WALLS}
    roof_labels = {r.id: r.name for r in ROOFS}
    floor_labels = {f.id: f.name for f in FLOORS}
    window_labels = {w["id"]: w["name"] for w in catalog["windows"]}
    mech_labels = {m["id"]: m["name"] for m in catalog["mechanical"]}
    solar_labels = {s["id"]: s["name"] for s in catalog["solar"]}
    target_names = {"code": "Code minimum", "nzr": "Net Zero Ready", "passive_house": "Passive House"}

    return {
        "target": target_names.get(spec.target_label, spec.target_label),
        "wall": wall_labels[top.wall_id] +
                (f" + {top.wall_ext_rigid_in:g}\" exterior rigid" if top.wall_ext_rigid_in else ""),
        "roof": roof_labels[top.roof_id] + f"; {top.joist_depth_in}\" joist" +
                (f" + {top.roof_deck_rigid_in:g}\" over-deck rigid" if top.roof_deck_rigid_in else ""),
        "floor": floor_labels[top.floor_id] +
                 (f"; {top.floor_rigid_in:g} mm EPS blanket" if top.floor_id == "FA1" else ""),
        "window": window_labels[top.window_id],
        "mechanical": mech_labels[top.mechanical_id],
        "solar": solar_labels[spec.solar_option_id],
    }
