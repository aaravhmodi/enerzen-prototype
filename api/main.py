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
from engine.location import location_names, resolve as resolve_location
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


def _serialize_result(result: ConfigResult) -> dict:
    data = dataclasses.asdict(result, dict_factory=lambda items: {
        k: v for k, v in items if k != "_assembly"
    })
    data.pop("_assembly", None)
    return data


def _serialize_layout(layout: SiteLayout) -> dict:
    return dataclasses.asdict(layout)


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/locations")
def locations():
    return {"locations": location_names()}


@app.get("/catalog")
def catalog():
    return load_catalog()


@app.post("/optimize")
def run_optimize(req: OptimizeRequest):
    spec = req.spec.to_engine_spec()
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
    resolved = resolve_location(spec.location)

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
