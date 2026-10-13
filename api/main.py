"""
FastAPI service wrapping the EnerZen engine: envelope optimization, deterministic
site placement, and OpenAI-backed spec parsing / rationale / concept renders.

Run: uvicorn api.main:app --reload
"""

import base64
import dataclasses
import os
import threading
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.ai import (
    AiUnavailableError,
    generate_concept_render,
    generate_development_concept_render,
    generate_design_rationale,
    parse_freeform_spec,
)
from engine.archetypes import ARCHETYPES, archetype_list
from engine.dev_optimizer import (DevSpec, best_configurations, evaluate_dev_mixes, excluded_types,
                                  optimize_dev_mix, screen_dev_mixes)
from engine import feasibility as fz
from engine.location import location_names, resolve as resolve_location
from engine.municipal import is_pickering, pickering_context
from engine import pickering_zoning
from engine.multi_site import development_geometry, multi_site_plan_svg, place_units
from engine.optimizer import ConfigResult, ProjectSpec, load_catalog, optimize_with_gate
from engine.report import generate_development_report, generate_unit_report
from engine.soft import SOFT_COST_FRACTION, permit_class, soft_cost, soft_timeline
from engine.regulatory import toronto_zoning_lookup
from engine.site import SiteLayout, SiteSpec, place_building, site_plan_svg
from engine.units import Units

@asynccontextmanager
async def lifespan(_app):
    # Load the stored Pickering layers in the background so the first lot lookup is quick.
    threading.Thread(target=pickering_zoning.warm, daemon=True).start()
    yield


app = FastAPI(title="EnerZen API", lifespan=lifespan)

# A self-hosted web app (see compose.yaml) names its own address here, comma-separated.
EXTRA_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://enerzen-prototype.vercel.app",
                   *EXTRA_ORIGINS],
    # Preview deployments get per-build URLs like
    # enerzen-prototype-<hash>-aaravhmodis-projects.vercel.app; allow those too.
    allow_origin_regex=r"https://enerzen-prototype-[a-z0-9]+-aaravhmodis-projects\.vercel\.app",
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
    mechanical_option_id: Optional[str] = None
    location: Optional[str] = None
    num_units: int = 1
    has_ac: bool = True
    allow_gas: bool = True
    excluded_mechanical_ids: list[str] = []
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
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_engine_spec(self) -> SiteSpec:
        return SiteSpec(**self.model_dump(exclude={"latitude", "longitude"}))


class OptimizeRequest(BaseModel):
    spec: ProjectSpecIn
    weights: Optional[dict] = None
    top_n: int = 20
    site: Optional[SiteSpecIn] = None


# Display units for drawings and reports. Inputs and results are always SI.
UnitSystem = Literal["metric", "imperial"]


class SitePlanRequest(BaseModel):
    spec: ProjectSpecIn
    site: SiteSpecIn
    render_concept: bool = False
    units: UnitSystem = "metric"


class ReportRequest(BaseModel):
    spec: ProjectSpecIn
    site: Optional[SiteSpecIn] = None
    weights: Optional[dict] = None
    top_n_index: int = 0
    include_rationale: bool = False
    units: UnitSystem = "metric"


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
    weights: Optional[dict] = None
    min_bedrooms: int = 0
    max_storeys: Optional[int] = None
    excluded_mechanical_ids: list[str] = []

    def to_engine_spec(self) -> DevSpec:
        return DevSpec(**self.model_dump())


class DevOptimizeRequest(BaseModel):
    spec: DevSpecIn
    top_n: int = 10
    mixes: Optional[list[dict[str, int]]] = None  # approved scenarios to evaluate


class DevReportRequest(BaseModel):
    spec: DevSpecIn
    mixes: list[dict[str, int]]                # the approved scenarios: the feasible set to rank against
    mix: Optional[dict[str, int]] = None       # the one to report; defaults to the top-ranked
    units: UnitSystem = "metric"


class DevSitePlanRequest(BaseModel):
    spec: DevSpecIn
    mix: dict[str, int]
    render_concept: bool = False
    units: UnitSystem = "metric"


def _serialize_result(result: ConfigResult) -> dict:
    data = dataclasses.asdict(result, dict_factory=lambda items: {
        k: v for k, v in items if k != "_assembly"
    })
    data.pop("_assembly", None)
    data["soft_cost"] = soft_cost(result.construction_cost)
    data["total_project_cost"] = round(result.construction_cost + data["soft_cost"])
    return data


def _spec_soft_timeline(spec) -> dict:
    footprint = (spec.footprint_length_m or 0) * (spec.footprint_width_m or 0) or spec.floor_area_m2 / max(spec.storeys, 1)
    return soft_timeline(spec.typology, spec.storeys, footprint, spec.num_units).as_dict()


def _serialize_layout(layout: SiteLayout) -> dict:
    return dataclasses.asdict(layout)


def _validate_location(location: Optional[str]) -> None:
    if location and location not in location_names():
        raise HTTPException(422, f"Unknown location {location!r}. Must be one of the /locations values.")


def _validate_mechanical_selection(spec: ProjectSpecIn) -> None:
    if not spec.mechanical_option_id:
        return
    option = next(
        (m for m in load_catalog().get("mechanical", []) if m["id"] == spec.mechanical_option_id),
        None,
    )
    if option is None:
        raise HTTPException(422, f"Unknown mechanical option {spec.mechanical_option_id!r}.")
    if not spec.allow_gas and option.get("type") == "gas":
        raise HTTPException(422, "The selected mechanical option burns natural gas, but gas systems are disabled.")
    if option["id"] in spec.excluded_mechanical_ids:
        raise HTTPException(422, "The selected mechanical option is one the brief excludes.")


def _gate_message(gate: dict) -> str:
    return (f"No configurations fit the given budget and target: {gate['evaluated']} evaluated, "
            f"{gate['over_budget']} over budget, {gate['missed_target']} missed the target.")


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
    toronto_benchmark = None
    regulatory_intelligence = {
        "status": "not_available",
        "label": "Municipal connector not configured",
        "detail": "Parcel-level zoning and bylaw rules are not available for this municipality yet.",
        "source_url": None,
        "source_label": None,
    }

    if name == "Toronto":
        toronto_benchmark = load_catalog().get("benchmarks", {}).get(
            "toronto_ewrb_2024_multifamily"
        )
        regulatory_intelligence = {
            "status": "not_checked",
            "label": "Parcel lookup required",
            "detail": "The city selection is not a zoning determination. Add parcel or address lookup before relying on use, height, setback, or parking rules.",
            "source_url": "https://open.toronto.ca/dataset/zoning-by-law/",
            "source_label": "City of Toronto Zoning By-law dataset",
        }
    municipal = pickering_context() if is_pickering(name) else None
    if municipal:
        toronto_benchmark = municipal['energy_benchmark']
        regulatory_intelligence = {
            'status': 'not_checked',
            'label': 'Pickering city-wide context',
            'detail': 'Municipal inventories and energy benchmarks are loaded. Select a parcel later to establish its zoning, setbacks and permitted uses. Current lot dimensions are scenario assumptions.',
            'source_url': municipal['sources'][1]['url'],
            'source_label': 'City of Pickering zoning maps and by-laws',
        }
    return {
        "municipal_context": municipal,
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
        "multifamily_energy_benchmark": toronto_benchmark,
        "regulatory_intelligence": regulatory_intelligence,
    }


@app.get("/locations/{name}/zoning")
def zoning_lookup(name: str, latitude: Optional[float] = None, longitude: Optional[float] = None,
                  query: Optional[str] = None):
    """Parcel zoning context from a point, or (Pickering) an address, roll number or PIN."""
    _validate_location(name)
    if query and is_pickering(name) and (latitude is None or longitude is None):
        found = pickering_zoning.find_property(query)
        if found is None:
            return {**pickering_zoning.status(), "status": "not_found", "label": "No matching property",
                    "detail": "No parcel or address in the stored Pickering data matches; try coordinates."}
        latitude, longitude = found["latitude"], found["longitude"]
        return {**pickering_zoning.lookup(latitude, longitude), "matched_property": found["matched"]}
    if latitude is None or longitude is None:
        raise HTTPException(422, "Give latitude and longitude, or a Pickering address, roll number or PIN as query.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise HTTPException(422, "Latitude must be between -90 and 90; longitude must be between -180 and 180.")
    if is_pickering(name):
        return pickering_zoning.lookup(latitude, longitude)
    if name != "Toronto":
        return {
            "status": "not_available",
            "label": "Municipal connector not configured",
            "detail": "Parcel-level zoning lookup is currently available only for Toronto and Pickering.",
        }
    return toronto_zoning_lookup(latitude, longitude)


@app.get("/municipal/pickering/status")
def pickering_data_status():
    """What the server's Pickering zoning store holds, and when it was scraped."""
    return pickering_zoning.status()


@app.get("/municipal/pickering/geocode")
def pickering_geocode(q: str, limit: int = 8):
    """Parcels and address points in the stored City data matching an address, roll number or PIN."""
    return {"query": q, "candidates": pickering_zoning.search_properties(q, limit=max(1, min(limit, 25)))}


@app.get("/municipal/pickering/map")
def pickering_map(latitude: float, longitude: float, radius_m: float = 250):
    """GeoJSON of the lot and every stored zoning, plan and overlay layer around it."""
    if not 43.7 <= latitude <= 44.1 or not -79.3 <= longitude <= -78.9:
        raise HTTPException(422, "That point is outside Pickering.")
    return pickering_zoning.map_features(latitude, longitude, max(25.0, min(radius_m, 1000.0)))


@app.get("/municipal/pickering/documents")
def pickering_documents():
    """Every stored by-law, plan and regulation, grouped by framework."""
    return pickering_zoning.documents()


@app.get("/municipal/pickering/documents/file")
def pickering_document_file(path: str):
    """A stored document, served from the server's copy (open a PDF at a page with #page=N)."""
    file = pickering_zoning.document_path(path)
    if file is None:
        raise HTTPException(404, "No such stored document.")
    media = "application/pdf" if file.suffix == ".pdf" else "text/html; charset=utf-8"
    # Saved city pages are third-party HTML: sandboxed so their scripts never run on this origin.
    return FileResponse(file, media_type=media, headers={"Content-Disposition": f'inline; filename="{file.name}"',
                                                         "Content-Security-Policy": "sandbox"})


@app.get("/municipal/pickering/search")
def pickering_search(q: str, limit: int = 50):
    """Full-text search across every stored by-law and plan page."""
    return pickering_zoning.search_documents(q, limit=max(1, min(limit, 200)))


@app.get("/catalog")
def catalog():
    return load_catalog()


@app.post("/optimize")
def run_optimize(req: OptimizeRequest):
    spec = req.spec.to_engine_spec()
    _validate_location(spec.location)
    _validate_mechanical_selection(req.spec)
    if req.site is not None:
        layout = place_building(spec, req.site.to_engine_spec())
        if not layout.fits_on_lot or not layout.setbacks_ok:
            notes = "; ".join(layout.notes) or "The building does not fit within the supplied site constraints."
            raise HTTPException(422, f"Site feasibility gate failed: {notes}")
    results, gate = optimize_with_gate(spec, req.weights)
    if not results:
        raise HTTPException(422, _gate_message(gate))
    return {
        "results": [_serialize_result(r) for r in results[: req.top_n]],
        "gate": gate,
        "soft": {"soft_cost_fraction": SOFT_COST_FRACTION, "timeline": _spec_soft_timeline(spec)},
    }


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
    svg = site_plan_svg(layout, spec, site, Units(req.units))

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
    """Path A nine-section feasibility report for one ranked configuration."""
    spec = req.spec.to_engine_spec()
    if not spec.location:
        raise HTTPException(422, "A location is required to generate a report.")
    _validate_location(spec.location)
    _validate_mechanical_selection(req.spec)
    resolved = resolve_location(spec.location)
    if spec.footprint_length_m is None or spec.footprint_width_m is None:
        import math
        side = math.sqrt(spec.floor_area_m2)
        spec.footprint_length_m = spec.footprint_length_m or side
        spec.footprint_width_m = spec.footprint_width_m or side

    # A site-fit failure does not block the report: it is one of the checks
    # that decides the feasibility status.
    if req.site is None:
        site_check = fz.Check("Site fit", fz.NOT_CHECKED, "No lot dimensions or setbacks were supplied.")
    else:
        layout = place_building(spec, req.site.to_engine_spec())
        ok = layout.fits_on_lot and layout.setbacks_ok
        site_check = fz.Check("Site fit", fz.PASS if ok else fz.FAIL,
                              "Fits inside the setbacks." if ok else
                              ("; ".join(layout.notes) or "The building does not fit within the setbacks."))

    weights = _normalized(req.weights, ("cost", "speed", "carbon", "energy"))
    results, gate = optimize_with_gate(spec, weights)
    if not results:
        raise HTTPException(422, _gate_message(gate))
    if req.top_n_index >= len(results):
        raise HTTPException(422, f"top_n_index out of range (only {len(results)} results).")
    top = results[req.top_n_index]

    catalog = load_catalog()
    parcel = None
    if is_pickering(spec.location) and req.site and req.site.latitude is not None and req.site.longitude is not None:
        parcel = pickering_zoning.lookup(req.site.latitude, req.site.longitude).get("parcel")
    checks = [fz.gate_check(gate), _constraints_check(spec, catalog), site_check,
              fz.zoning_check(resolved.name, parcel)]
    timeline = _spec_soft_timeline(spec)
    units = Units(req.units)
    steps, enhancements = fz.next_steps(
        location=resolved, checks=checks, target_label=spec.target_label,
        surrogate_verified=top.surrogate_verified, dwellings=spec.num_units,
        part3=timeline["permit_class"] == "part3", has_pv=top.pv_capacity_kw > 0, units=units)
    pdf_bytes = generate_unit_report(
        spec=spec, result=top, location=resolved, labels=_report_labels(top, spec, catalog),
        soft_timeline=timeline, assessment=fz.assess(checks),
        benchmark=fz.benchmark_comparison(top, spec.floor_area_m2, catalog, _rates(resolved, catalog)),
        ranks=fz.objective_ranks(top, results, [
            ("Capital cost", "cost", "construction_cost", False, lambda v: f"${v:,.0f}"),
            ("Construction speed", "speed", "construction_weeks", False, lambda v: f"{v:g} weeks"),
            ("Embodied carbon", "carbon", "embodied_carbon_kg_co2e_m2", False, units.carbon),
            ("Operating energy", "energy", "eui_kwh_m2_yr", False, units.eui),
        ]),
        weights=weights, steps=steps, enhancements=enhancements, units=units)
    return {"pdf_b64": base64.b64encode(pdf_bytes).decode("ascii")}


def _normalized(weights: Optional[dict], keys: tuple) -> dict:
    raw = {k: max(0.0, float((weights or {}).get(k, 0.0))) for k in keys}
    total = sum(raw.values())
    return {k: (v / total if total else 1 / len(keys)) for k, v in raw.items()}


def _rates(loc, catalog: dict) -> dict:
    rates = dict(catalog["energy_rates"])
    rates["electricity_cad_per_kwh"] = loc.electricity_cad_per_kwh
    rates["natural_gas_cad_per_kwh"] = loc.natural_gas_cad_per_kwh
    return rates


def _constraints_check(spec, catalog: dict) -> fz.Check:
    names = {m["id"]: m["name"] for m in catalog["mechanical"]}
    parts = []
    if spec.excluded_mechanical_ids:
        parts.append("excluded " + ", ".join(names.get(i, i) for i in spec.excluded_mechanical_ids))
    if not spec.allow_gas:
        parts.append("all-electric")
    return fz.Check("Hard constraints", fz.PASS,
                    ("Respected: " + "; ".join(parts) + ".") if parts else "No system exclusions in the brief.")


@app.post("/dev-report")
def run_dev_report(req: DevReportRequest):
    """Path B nine-section feasibility report for one approved housing mix,
    ranked against the other approved mixes."""
    dev = req.spec.to_engine_spec()
    _validate_location(dev.location)
    mixes = [{t: c for t, c in m.items() if c > 0} for m in req.mixes]
    if not any(mixes):
        raise HTTPException(422, "Send the approved scenarios to report on.")
    best = best_configurations(dev, mixes)
    feasible, rejected = evaluate_dev_mixes(dev, mixes, best)
    if not feasible:
        reasons = "; ".join(f"{r['mix_label']}: {r['reason']}" for r in rejected[:3])
        raise HTTPException(422, "No approved scenario passed the performance and budget gate. " + reasons)
    if req.mix:
        wanted = {t: c for t, c in req.mix.items() if c > 0}
        chosen = next((m for m in feasible if m.units == wanted), None)
        if chosen is None:
            raise HTTPException(422, "The selected mix is not among the feasible approved scenarios.")
    else:
        chosen = feasible[0]

    resolved = resolve_location(dev.location)
    catalog = load_catalog()
    site = SiteSpec(lot_width_m=dev.lot_width_m, lot_depth_m=dev.lot_depth_m, street_side=dev.street_side,
                    front_setback_m=dev.front_setback_m, side_setback_m=dev.side_setback_m,
                    rear_setback_m=dev.rear_setback_m, solar_orientation=dev.orientation)
    placements = place_units(chosen.units, site)
    _walk, geometry = development_geometry(placements, site, chosen.units)
    excluded = excluded_types(dev)
    checks = [
        fz.Check("Budget and performance gate", fz.PASS,
                 f"{len(feasible)} of {len(mixes)} approved scenarios passed"
                 + (f"; rejected: {'; '.join(r['mix_label'] + ' (' + r['reason'] + ')' for r in rejected)}."
                    if rejected else ".")),
        fz.Check("Hard constraints", fz.PASS,
                 ("Types ruled out by the brief never entered a mix: "
                  + "; ".join(e["reason"] for e in excluded) + ".") if excluded
                 else "Every selected type meets the bedroom and storey limits."),
        fz.Check("Site fit", fz.PASS, f"All {len(placements)} buildings fit inside the setbacks."),
        fz.zoning_check(resolved.name),
    ]
    units = Units(req.units)
    types = list(chosen.units)
    largest = max(types, key=lambda t: (ARCHETYPES[t].storeys, ARCHETYPES[t].units_per_building))
    arch = ARCHETYPES[largest]
    timeline = soft_timeline(arch.typology, arch.storeys, arch.footprint_length_m * arch.footprint_width_m,
                             chosen.total_units).as_dict()
    part3 = any(permit_class(ARCHETYPES[t].typology, ARCHETYPES[t].storeys,
                             ARCHETYPES[t].footprint_length_m * ARCHETYPES[t].footprint_width_m) == "part3"
                for t in types)
    steps, enhancements = fz.next_steps(
        location=resolved, checks=checks, target_label=dev.target_label,
        surrogate_verified=all(best[t].surrogate_verified for t in types), dwellings=chosen.total_units,
        part3=part3, has_pv=False, units=units)
    rates = _rates(resolved, catalog)
    benchmarks = {t: fz.benchmark_comparison(best[t], ARCHETYPES[t].floor_area_m2 / ARCHETYPES[t].units_per_building,
                                             catalog, rates) for t in types}
    weights = _normalized(dev.weights, ("yield", "cost", "energy", "carbon"))
    pdf_bytes = generate_development_report(
        dev=dev, mix=chosen, best=best, location=resolved, labels=_catalog_labels(catalog),
        placements=placements, site=site, geometry=geometry, soft_timeline=timeline,
        assessment=fz.assess(checks), benchmarks=benchmarks,
        ranks=fz.objective_ranks(chosen, feasible, [
            ("Unit yield", "yield", "total_units", True, lambda v: f"{v} homes"),
            ("Capital cost", "cost", "total_cost", False, lambda v: f"${v:,.0f}"),
            ("Operating energy", "energy", "avg_eui_kwh_m2_yr", False, units.eui),
            ("Embodied carbon", "carbon", "avg_carbon_kg_co2e_m2", False, units.carbon),
        ]),
        weights=weights, steps=steps, enhancements=enhancements, excluded=excluded, units=units)
    return {"pdf_b64": base64.b64encode(pdf_bytes).decode("ascii")}


@app.get("/archetypes")
def get_archetypes():
    return {"archetypes": archetype_list()}


@app.post("/dev-scenarios")
def run_dev_scenarios(req: DevOptimizeRequest):
    """Path B steps 3-4: housing-mix scenarios that fit the land, before
    building performance is optimized."""
    dev = req.spec.to_engine_spec()
    _validate_location(dev.location)
    excluded = excluded_types(dev)
    if dev.allowed_types and len(excluded) == len(dev.allowed_types):
        raise HTTPException(422, "Every selected housing type is ruled out by the brief: "
                                 + "; ".join(e["reason"] for e in excluded) + ".")
    scenarios = screen_dev_mixes(dev, req.top_n)
    if not scenarios:
        raise HTTPException(422, "No housing mix fits inside the setbacks within the budget. "
                                 "Try a larger lot, smaller setbacks, another housing type or a higher budget.")
    return {"scenarios": [dataclasses.asdict(s) for s in scenarios], "excluded_types": excluded}


@app.post("/dev-optimize")
def run_dev_optimize(req: DevOptimizeRequest):
    """Path B steps 5-7: optimize building performance for the approved
    scenarios, run development calculations and rank them. Without
    approved mixes, screens and evaluates in one call."""
    dev = req.spec.to_engine_spec()
    _validate_location(dev.location)
    if req.mixes:
        mixes, rejected = evaluate_dev_mixes(dev, req.mixes)
    else:
        mixes, rejected = optimize_dev_mix(dev, req.top_n), []
    if not mixes:
        reasons = "; ".join(f"{r['mix_label']}: {r['reason']}" for r in rejected[:3])
        raise HTTPException(422, "No approved scenario passed the performance and budget gate."
                                 + (f" {reasons}" if reasons else ""))
    return {
        "mixes": [
            {k: v for k, v in dataclasses.asdict(m).items() if k != "weighted_score"}
            for m in mixes[: req.top_n]
        ],
        "rejected": rejected,
        "soft_cost_fraction": SOFT_COST_FRACTION,
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
        solar_orientation=dev.orientation,
    )
    placements = place_units(req.mix, site)
    svg = multi_site_plan_svg(placements, site, req.mix, Units(req.units))
    response = {"svg": svg, "concept_render_b64": None}
    if req.render_concept:
        try:
            png_bytes = generate_development_concept_render(svg, req.mix)
            response["concept_render_b64"] = base64.b64encode(png_bytes).decode("ascii")
        except AiUnavailableError:
            pass  # SVG remains authoritative when image generation is unavailable.
    return response


def _catalog_labels(catalog: dict) -> dict:
    from engine.assemblies import ROOFS, WALLS

    return {
        "wall": {w.id: w.name for w in WALLS},
        "roof": {r.id: r.name for r in ROOFS},
        "window": {w["id"]: w["name"] for w in catalog["windows"]},
        "mechanical": {m["id"]: m["name"] for m in catalog["mechanical"]},
    }


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
