"""Nine-section feasibility report (flowchart "feasibility report") as a PDF,
for Path A (one unit) and Path B (a development). The assessment behind it
lives in engine/feasibility.py; this module only lays it out."""

from datetime import date
from io import BytesIO

from reportlab.graphics.shapes import Circle, Drawing, Polygon as RLPolygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, ListFlowable, ListItem, PageTemplate, Paragraph, Spacer, Table,
    TableStyle,
)

from engine.feasibility import FEASIBLE, FEASIBLE_WITH_MODIFICATIONS, FAIL, PASS, SECTIONS
from engine.soft import SOFT_COST_FRACTION, soft_cost

INK = colors.HexColor("#18211D")
MUTED = colors.HexColor("#66706A")
FOREST = colors.HexColor("#214E3B")
SAGE = colors.HexColor("#D8E6DC")
PAPER = colors.HexColor("#FFFEFA")
LINE = colors.HexColor("#D9DDD8")
AMBER = colors.HexColor("#F4E7C8")
ROSE = colors.HexColor("#F2D9D9")
GREEN_FILL = colors.HexColor("#DDE8D4")
BUILDING = colors.HexColor("#E3E9F1")

STATUS_FILL = {FEASIBLE: SAGE, FEASIBLE_WITH_MODIFICATIONS: AMBER}
CHECK_LABEL = {PASS: "Pass", FAIL: "Fail"}

W = 7.2 * inch


def _money(value):
    return f"-${-value:,.0f}" if value < 0 else f"${value:,.0f}"


def _t(kg):
    return f"{kg / 1000:,.1f} tCO2e"


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=24, leading=28, textColor=INK, alignment=0, spaceAfter=8),
        "eyebrow": ParagraphStyle("Eyebrow", parent=base["BodyText"], fontName="Helvetica-Bold",
                                  fontSize=7.5, leading=10, textColor=FOREST, spaceAfter=7),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12, leading=15, textColor=INK, spaceBefore=14, spaceAfter=7),
        "h3": ParagraphStyle("H3", parent=base["Heading3"], fontName="Helvetica-Bold",
                             fontSize=9.5, leading=12, textColor=INK, spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=8.7, leading=12.5, textColor=INK, spaceAfter=5),
        "status": ParagraphStyle("Status", parent=base["BodyText"], fontName="Helvetica-Bold",
                                 fontSize=15, leading=19, textColor=INK),
        "cell": ParagraphStyle("Cell", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=8, leading=10.5, textColor=INK),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName="Helvetica",
                                fontSize=7.2, leading=10, textColor=MUTED),
        "right": ParagraphStyle("Right", parent=base["BodyText"], fontName="Helvetica",
                                fontSize=7.2, leading=10, textColor=MUTED, alignment=TA_RIGHT),
    }


def _table(rows, widths=None, header=True):
    styles = _styles()
    # Wrap long cells so tables never overflow the frame.
    rows = [[Paragraph(c, styles["cell"]) if isinstance(c, str) and len(c) > 48 and not (header and i == 0) else c
             for c in row] for i, row in enumerate(rows)]
    table = Table(rows, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [PAPER, colors.white]),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), FOREST),
                     ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                     ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    table.setStyle(TableStyle(commands))
    return table


def _bullets(items, style):
    return ListFlowable([ListItem(Paragraph(i, style), leftIndent=10) for i in items],
                        bulletType="bullet", start="•", leftIndent=10, bulletFontSize=7)


def _doc(out, title, footer):
    def page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(0.65 * inch, 0.52 * inch, 7.85 * inch, 0.52 * inch)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.setFillColor(FOREST)
        canvas.drawString(0.65 * inch, 0.34 * inch, "ENERZEN")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(7.85 * inch, 0.34 * inch, f"{footer}  |  {doc.page}")
        canvas.restoreState()

    frame = Frame(0.65 * inch, 0.68 * inch, W, 9.45 * inch,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    return BaseDocTemplate(out, pagesize=letter, pageTemplates=[PageTemplate("Report", [frame], onPage=page)],
                           title=title, author="EnerZen")


def _heading(n, styles):
    return Paragraph(f"{n}. {SECTIONS[n - 1]}", styles["h2"])


def _executive(assessment, headline_rows, styles):
    status = Table([[Paragraph(assessment.status, styles["status"])]], colWidths=[W])
    status.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), STATUS_FILL.get(assessment.status, ROSE)),
                                ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    checks = [["Check", "Result", "Detail"]] + [
        [c.name, CHECK_LABEL.get(c.status, "Not checked"), c.detail] for c in assessment.checks]
    return [
        _heading(1, styles), status, Spacer(1, 6), _bullets(assessment.reasons, styles["body"]), Spacer(1, 4),
        _table(checks, [1.7 * inch, 0.85 * inch, 4.65 * inch]), Spacer(1, 8),
        _table(headline_rows, [W / len(headline_rows[0])] * len(headline_rows[0])),
    ]


def _timeline_rows(soft_timeline, build_weeks, build_basis):
    return [
        ["Phase", "Weeks", "Basis"],
        ["Design and engineering", f"{soft_timeline['design_engineering_weeks']:g}", "EnerZen default assumption"],
        ["Site plan approval", f"{soft_timeline['site_plan_weeks']:g}",
         "Exempt: 10 or fewer units (Planning Act)" if soft_timeline["site_plan_exempt"]
         else "60-day Planning Act timeline"],
        ["Building permit review", f"{soft_timeline['building_permit_weeks']:g}",
         f"Ontario Building Code review period ({soft_timeline['permit_class'].replace('part', 'Part ')})"],
        ["Soft timeline", f"{soft_timeline['total_weeks']:g}", "Assumes complete applications, no rezoning"],
        ["Fabrication and site work to envelope close", f"{build_weeks:g}", build_basis],
        ["Brief to envelope close", f"{soft_timeline['total_weeks'] + build_weeks:g}", "Soft plus hard, in sequence"],
    ]


def _lifecycle_rows(b, area, capex, eui, utility, lcc):
    return [
        ["Measure", "Recommended", "Code-built benchmark", "Difference"],
        ["Capital cost per m2", _money(b["cost_per_m2"]), _money(b["benchmark_cost_per_m2"]),
         _money(b["cost_per_m2"] - b["benchmark_cost_per_m2"])],
        ["Capital cost (hard)", _money(capex), _money(b["benchmark_cost_per_m2"] * area),
         _money(capex - b["benchmark_cost_per_m2"] * area)],
        ["Site EUI (kWh/m2/yr)", f"{eui:g}", f"{b['benchmark_eui']:g}", f"{eui - b['benchmark_eui']:+.1f}"],
        ["Annual energy saving", f"{b['energy_saving_kwh_yr']:,} kWh/yr", "", ""],
        ["Annual utility cost", _money(utility), _money(b["benchmark_annual_utility"]),
         f"{_money(b['utility_saving_yr'])} saved / yr"],
        ["30-year lifecycle cost (present value)", _money(lcc), _money(b["benchmark_lifecycle_cost_30yr"]),
         f"{_money(b['lifecycle_saving_30yr'])} saved"],
    ]


def _lifecycle_note(b, styles, rate=True):
    priced = (f"the recommended option's own variable rate (${b['rate_cad_per_kwh']:.3f}/kWh)" if rate
              else "each housing type's own variable rate")
    return Paragraph(
        f"Benchmark: a code-built new home of the same floor area. Capital cost {b['sources']['cost']}; "
        f"EUI {b['sources']['eui']}. Benchmark energy is priced at {priced}, so the comparison isolates "
        "consumption. Lifecycle cost is upfront capital plus 30 years of energy bills, 2% escalation, "
        "discounted at 3%.", styles["small"])


def _priority(ranks, weights, styles, unit):
    rows = [["Objective", "Weight", "Rank among feasible", "Value"]]
    for r in ranks:
        rows.append([r["objective"], f"{weights.get(r['key'], 0):.0%}", f"{r['rank']} of {r['of']}",
                     r["display"]])
    return [KeepTogether([_heading(8, styles), Paragraph(
        f"Where the recommended {unit} ranks among every feasible option on each weighted objective "
        "(1 is best). The recommendation balances the weights, so it need not rank first on each.",
        styles["body"]), _table(rows, [2.0 * inch, 0.9 * inch, 1.6 * inch, 2.7 * inch])])]


def _next(steps, enhancements, styles):
    return [_heading(9, styles), Paragraph("Required before a go decision", styles["h3"]),
            _bullets(steps, styles["body"]), Paragraph("Enhancements", styles["h3"]),
            _bullets(enhancements, styles["body"]), Spacer(1, 8), Paragraph(
                "This report is a comparative concept-stage estimate, not a permit, tender or structural design. "
                "Confirm foundation, roof structure, energy compliance and geotechnical conditions with the "
                "appropriate qualified professionals.", styles["small"])]


# ── Path A ──────────────────────────────────────────────────────────────────

def generate_unit_report(*, spec, result, location, labels, soft_timeline, assessment, benchmark,
                         ranks, weights, steps, enhancements) -> bytes:
    """Path A feasibility report for the recommended configuration."""
    out = BytesIO()
    styles = _styles()
    doc = _doc(out, "EnerZen Feasibility Report", "Feasibility report · individual unit")
    area = spec.floor_area_m2

    story = [
        Paragraph("FEASIBILITY REPORT · INDIVIDUAL UNIT", styles["eyebrow"]),
        Paragraph("Feasibility of the recommended unit", styles["title"]),
        Paragraph(
            f"{location.name} &nbsp; | &nbsp; {spec.footprint_length_m:g} x "
            f"{spec.footprint_width_m:g} m footprint &nbsp; | &nbsp; {spec.storeys} storey"
            f"{'s' if spec.storeys > 1 else ''} &nbsp; | &nbsp; {area:g} m2 conditioned",
            styles["body"]),
        Paragraph(f"Prepared {date.today().strftime('%B %d, %Y')}", styles["small"]),
        Spacer(1, 8),
    ]
    hard = result.construction_cost
    story += _executive(assessment, [
        ["Total project cost", "Brief to close", "Site EUI", "Lifecycle carbon"],
        [_money(hard + soft_cost(hard)), f"{soft_timeline['total_weeks'] + result.construction_weeks:g} weeks",
         f"{result.eui_kwh_m2_yr:g} kWh/m2/yr", _t(result.lifecycle_carbon_30yr_kg_co2e_m2 * area)],
    ], styles)

    tedi_limit = (f"TEDI limit {result.tedi_threshold_kwh_m2_yr:g} kWh/m2/yr"
                  if result.tedi_threshold_kwh_m2_yr is not None else "No TEDI gate for the code target")
    story += [_heading(2, styles), Paragraph("Design basis", styles["h3"]), _table([
        ["Input", "Resolved value", "Design implication"],
        ["Location", location.name, f"Climate zone {location.climate_zone}; {location.region_name}"],
        ["Snow", f"Ss {location.ss:g} kPa; roof S {location.roof_snow_load_kpa:g} kPa",
         f"{location.snow_tier['name']}; {location.joist_depth_in}\" preliminary joist"],
        ["Soil defaults", f"{location.allowable_bearing_kpa:g} kPa bearing; {location.frost_depth_m:g} m frost depth",
         "Regional defaults; confirm by geotechnical investigation"],
        ["Target", labels["target"], tedi_limit],
    ], [1.25 * inch, 2.25 * inch, 3.7 * inch]), Paragraph("Selected systems", styles["h3"]), _table([
        ["System", "Selection", "Thermal result"],
        ["Wall", labels["wall"], f"Effective R-{result.assembly_breakdown['wall']['r_effective']}"],
        ["Roof", labels["roof"], f"Effective R-{result.assembly_breakdown['roof']['r_effective']}"],
        ["Foundation", labels["floor"], f"Effective R-{result.assembly_breakdown['floor']['r_effective']}"],
        ["Windows", labels["window"], result.window_id],
        ["Mechanical", labels["mechanical"], result.mechanical_id],
        ["Solar", labels["solar"], f"{result.pv_capacity_kw:g} kW"],
    ], [1.15 * inch, 4.25 * inch, 1.8 * inch])]
    floor = result.assembly_breakdown["floor"]
    if "eps_area_m2" in floor:
        story += [Paragraph("Foundation quantities", styles["h3"]), _table([
            ["Quantity", "Result"],
            ["Footprint", f"{floor['footprint_length_m']:g} x {floor['footprint_width_m']:g} m = "
                          f"{floor['footprint_area_m2']:g} m2"],
            ["EPS blanket", f"{floor['extended_length_m']:g} x {floor['extended_width_m']:g} m = "
                            f"{floor['eps_area_m2']:g} m2; {floor['eps_volume_m3']:g} m3"],
            ["Slab concrete", f"{floor['slab_concrete_m3']:g} m3"],
            ["Frost-wall concrete", f"{floor['frost_wall_concrete_m3']:g} m3"],
        ], [2.2 * inch, 5 * inch])]

    cb = result.cost_breakdown
    cost_rows = [["Cost line", "CAD"]]
    for key, value in cb["envelope_material_split"].items():
        cost_rows.append([key.replace("_", " ").title(), _money(value)])
    cost_rows += [
        ["Envelope installation labour", _money(cb["labour_cost"])],
        ["Connections and sealing", _money(cb["connections_cost"])],
        ["Interior partitions", _money(cb["partitions_cost"])],
        ["Exterior trim and finishes", _money(cb["ext_finishes_cost"])],
        ["Mechanical", _money(cb["mechanical_cost"])],
        ["Fit-out and services", _money(cb["fitout_cost"])],
        ["Contingency", _money(cb["contingency_cost"])],
    ]
    if hard > cb["total_per_unit"]:
        cost_rows.append(["Solar PV", _money(hard - cb["total_per_unit"])])
    cost_rows += [
        ["Construction total (hard cost)", _money(hard)],
        [f"Soft costs, Class D allowance ({SOFT_COST_FRACTION:.0%} of hard cost)", _money(soft_cost(hard))],
        ["Total project cost, Class D", _money(hard + soft_cost(hard))],
        ["Budget per unit (hard cost)", _money(spec.budget_per_unit)],
    ]
    story += [_heading(3, styles), _table(cost_rows, [5.8 * inch, 1.4 * inch]), Paragraph(
        "Class D feasibility estimate, not a construction quotation. Soft costs cover consultants, permits and "
        "development charges, legal, insurance and financing, as a default allowance until EnerZen data is "
        "available.", styles["small"])]

    story += [_heading(4, styles), _table(_timeline_rows(soft_timeline, result.construction_weeks,
                                                         "Engine build schedule"),
                                          [3.0 * inch, 0.9 * inch, 3.3 * inch])]

    story += _energy_unit(result, area, styles)
    story += _carbon_rows([("Recommended unit", result, area)], benchmark["benchmark_embodied_kg_m2"], styles)

    story += [_heading(7, styles), _table(_lifecycle_rows(benchmark, area, hard, result.eui_kwh_m2_yr,
                                                          result.annual_utility_cost, result.lifecycle_cost_30yr),
                                          [2.3 * inch, 1.5 * inch, 1.6 * inch, 1.8 * inch]),
              _lifecycle_note(benchmark, styles)]
    story += _priority(ranks, weights, styles, "configuration")
    story += _next(steps, enhancements, styles)
    doc.build(story)
    return out.getvalue()


def _energy_unit(result, area, styles):
    threshold = result.tedi_threshold_kwh_m2_yr
    rows = [
        ["Measure", "Achieved", "Target"],
        ["Site EUI", f"{result.eui_kwh_m2_yr:g} kWh/m2/yr", ""],
        ["TEDI (heating demand)", f"{result.tedi_kwh_m2_yr:g} kWh/m2/yr",
         f"<= {threshold:g} kWh/m2/yr" if threshold is not None else "No TEDI gate (code)"],
        ["MEUI", f"{result.meui_kwh_m2_yr:g} kWh/m2/yr", ""],
        ["PV generation", f"{result.pv_generation_kwh_yr:,.0f} kWh/yr ({result.pv_capacity_kw:g} kW)", ""],
        ["Net energy after PV", f"{result.net_operational_energy_kwh_yr:,.0f} kWh/yr "
                                f"({result.net_eui_kwh_m2_yr:g} kWh/m2/yr)", "Net zero" if result.net_zero else ""],
        ["EnerGuide rating", f"{result.energuide_score:g} / 100", ""],
        ["NZR probability", f"{result.nzr_probability:.0%}", "Monte Carlo over weather, airtightness, occupants"],
    ]
    basis = ("Corrected against a model trained on HOT2000 output (engine/surrogate.py)."
             if result.surrogate_verified else
             "Degree-day screening model (METHODOLOGY section 3); confirm with a compliance model.")
    return [_heading(5, styles), _table(rows, [2.0 * inch, 2.6 * inch, 2.6 * inch]), Paragraph(basis, styles["small"])]


def _carbon_rows(items, bench_embodied, styles):
    """items: (label, ConfigResult, conditioned area m2), totals first."""
    rows = [["", "Embodied", "Operational, 30 yr", "Lifecycle, 30 yr"]]
    tot = [0.0, 0.0, 0.0]
    for label, r, area in items:
        vals = [r.embodied_carbon_kg_co2e_m2 * area, r.operational_carbon_30yr_kg_co2e_m2 * area,
                r.lifecycle_carbon_30yr_kg_co2e_m2 * area]
        tot = [a + b for a, b in zip(tot, vals)]
        if len(items) > 1:
            rows.append([label] + [_t(v) for v in vals])
    rows.append(["Total" if len(items) > 1 else "Total (tCO2e)"] + [_t(v) for v in tot])
    total_area = sum(a for _l, _r, a in items)
    rows.append(["Per m2 (kgCO2e/m2)"] + [f"{v / total_area:,.0f}" for v in tot])
    rows.append(["Benchmark embodied, new low-rise", f"{bench_embodied:g} kgCO2e/m2", "", ""])
    return [_heading(6, styles), _table(rows, [2.3 * inch, 1.6 * inch, 1.65 * inch, 1.65 * inch]), Paragraph(
        "Embodied carbon is cradle-to-gate for the catalog assemblies and systems; operational carbon uses the "
        "Ontario grid and natural gas factors over 30 years (METHODOLOGY section 8).", styles["small"])]


# ── Path B ──────────────────────────────────────────────────────────────────

def _plan_drawing(site, placements, geometry, names):
    """To-scale plan: lot, buildable envelope, shared green and buildings."""
    max_w, max_h = 3.4 * inch, 3.6 * inch
    s = min(max_w / site.lot_width_m, max_h / site.lot_depth_m)
    w, h = site.lot_width_m * s, site.lot_depth_m * s
    d = Drawing(w + 70, h + 24)
    ox, oy = 4, 14

    def pt(x, y):  # lot metres (y from north) to drawing points
        return ox + x * s, oy + h - y * s

    def shape(polygon, fill, stroke):
        for part in getattr(polygon, "geoms", [polygon]):
            if not part.is_empty and hasattr(part, "exterior"):
                d.add(RLPolygon([c for x, y in part.exterior.coords for c in pt(x, y)],
                                fillColor=fill, strokeColor=stroke, strokeWidth=0.5))

    d.add(Rect(ox, oy, w, h, fillColor=PAPER, strokeColor=INK, strokeWidth=0.8))
    shape(geometry.shared_green, GREEN_FILL, colors.HexColor("#8EA582"))
    if geometry.rain_garden is not None:
        c = geometry.rain_garden.centroid
        r = (geometry.rain_garden.bounds[2] - c.x) * s
        cx, cy = pt(c.x, c.y)
        d.add(Circle(cx, cy, r, fillColor=colors.HexColor("#DCE9F2"), strokeColor=colors.HexColor("#7FA3BC"),
                     strokeWidth=0.5))
    shape(geometry.pedestrian_spine, colors.HexColor("#EEE9E2"), colors.HexColor("#CFC6BA"))
    for stall in geometry.parking:
        shape(stall, colors.HexColor("#ECEAE6"), colors.HexColor("#B9B3AA"))
    for i, p in enumerate(placements):
        x0, y1 = pt(p.x_m, p.y_m + p.h_m)
        d.add(Rect(x0, y1, p.w_m * s, p.h_m * s, fillColor=BUILDING, strokeColor=FOREST, strokeWidth=0.6))
        d.add(String(x0 + p.w_m * s / 2, y1 + p.h_m * s / 2 - 3, str(names.index(p.archetype_id) + 1),
                     fontName="Helvetica-Bold", fontSize=7, fillColor=FOREST, textAnchor="middle"))
    side = {"N": (ox + w / 2, oy + h + 4), "S": (ox + w / 2, oy - 10),
            "E": (ox + w + 4, oy + h / 2), "W": (ox - 2, oy + h / 2)}[site.street_side]
    d.add(String(side[0], side[1], "STREET", fontName="Helvetica", fontSize=6, fillColor=MUTED,
                 textAnchor="start" if site.street_side == "E" else "middle"))
    d.add(String(ox + w + 6, oy + 4, "N ↑", fontName="Helvetica", fontSize=6, fillColor=MUTED))
    return d


def generate_development_report(*, dev, mix, best, location, labels, placements, site, geometry,
                                 soft_timeline, assessment, benchmarks, ranks, weights, steps,
                                 enhancements, excluded) -> bytes:
    """Path B feasibility report for the recommended housing mix.

    mix: DevMixResult; best: {archetype_id: ConfigResult per dwelling};
    benchmarks: {archetype_id: benchmark_comparison per dwelling}."""
    from engine.archetypes import ARCHETYPES

    out = BytesIO()
    styles = _styles()
    doc = _doc(out, "EnerZen Development Feasibility Report", "Feasibility report · community development")
    types = list(mix.units)
    dwellings = {t: mix.units[t] * ARCHETYPES[t].units_per_building for t in types}
    area_per = {t: ARCHETYPES[t].floor_area_m2 / ARCHETYPES[t].units_per_building for t in types}
    lot_area = dev.lot_width_m * dev.lot_depth_m

    story = [
        Paragraph("FEASIBILITY REPORT · COMMUNITY DEVELOPMENT", styles["eyebrow"]),
        Paragraph("Feasibility of the recommended mix", styles["title"]),
        Paragraph(f"{location.name} &nbsp; | &nbsp; {dev.lot_width_m:g} x {dev.lot_depth_m:g} m lot "
                  f"({lot_area:,.0f} m2) &nbsp; | &nbsp; {mix.mix_label}", styles["body"]),
        Paragraph(f"Prepared {date.today().strftime('%B %d, %Y')}", styles["small"]),
        Spacer(1, 8),
    ]
    story += _executive(assessment, [
        ["Homes", "Total project cost", "Brief to close", "Average EUI"],
        [f"{mix.total_units}", _money(mix.total_project_cost),
         f"{mix.soft_timeline_weeks + mix.construction_weeks:g} weeks", f"{mix.avg_eui_kwh_m2_yr:g} kWh/m2/yr"],
    ], styles)

    # 2. Recommended solution
    names = types
    type_rows = [["#", "Housing type", "Buildings", "Homes", "Systems"]]
    for i, t in enumerate(types):
        r = best[t]
        type_rows.append([str(i + 1), ARCHETYPES[t].name, str(mix.units[t]), str(dwellings[t]),
                          f"{labels['wall'][r.wall_id]}; {labels['roof'][r.roof_id]}; "
                          f"{labels['window'][r.window_id]}; {labels['mechanical'][r.mechanical_id]}"])
    green_area = geometry.shared_green.area if not geometry.shared_green.is_empty else 0.0
    footprint = sum(p.w_m * p.h_m for p in placements)
    walkway = not geometry.pedestrian_spine.is_empty
    green_text = (
        f"A shared rear green of {green_area:,.0f} m2 ({green_area / lot_area:.0%} of the lot) gives every home "
        "access to common open space"
        + (", reached by a shared walkway from the street. " if walkway else ". ")
        + (f"{len(geometry.parking)} concept parking stalls sit on the street side. " if geometry.parking else "")
        + ("A rain-garden location is marked in the shared green for stormwater; it is not sized. "
           if geometry.rain_garden is not None else "")
        + f"Buildings cover {footprint / lot_area:.0%} of the lot. Walkway, parking and the green are concept "
        "layers, not a site plan approval.")
    plan = _plan_drawing(site, placements, geometry, names)
    legend = Paragraph("<br/>".join(f"{i + 1}. {ARCHETYPES[t].name}" for i, t in enumerate(types))
                       + "<br/>Green: shared green; blue: rain garden; beige: walkway and parking."
                       + f"<br/><br/>Lot {dev.lot_width_m:g} x {dev.lot_depth_m:g} m; setbacks front "
                         f"{dev.front_setback_m:g}, side {dev.side_setback_m:g}, rear {dev.rear_setback_m:g} m. "
                         "Drawn to scale from the placement engine.", styles["small"])
    plan_table = Table([[plan, legend]], colWidths=[3.9 * inch, 3.3 * inch])
    plan_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [_heading(2, styles), _table(type_rows, [0.3 * inch, 1.9 * inch, 0.75 * inch, 0.6 * inch, 3.65 * inch]),
              KeepTogether([Paragraph("Site plan", styles["h3"]), plan_table]),
              Paragraph("Green-space strategy", styles["h3"]), Paragraph(green_text, styles["body"])]
    if excluded:
        story.append(Paragraph("Ruled out by the brief: " + "; ".join(e["reason"] for e in excluded) + ".",
                               styles["small"]))

    # 3. Capital cost
    cost_rows = [["Housing type", "Homes", "Hard cost per home", "Hard cost"]]
    for t in types:
        cost_rows.append([ARCHETYPES[t].name, str(dwellings[t]), _money(best[t].construction_cost),
                          _money(best[t].construction_cost * dwellings[t])])
    cost_rows += [
        ["Construction total (hard cost)", "", "", _money(mix.total_cost)],
        [f"Soft costs, Class D allowance ({SOFT_COST_FRACTION:.0%})", "", "", _money(mix.soft_cost)],
        ["Total project cost, Class D", "", "", _money(mix.total_project_cost)],
        ["Budget (hard cost)", "", "", _money(dev.total_budget_cad)],
    ]
    story += [_heading(3, styles), _table(cost_rows, [3.2 * inch, 0.8 * inch, 1.6 * inch, 1.6 * inch]), Paragraph(
        "Class D feasibility estimate, not a construction quotation. Site servicing, roads and land are not "
        "included.", styles["small"])]

    story += [_heading(4, styles), _table(_timeline_rows(
        soft_timeline, mix.construction_weeks, "Engine build schedule, buildings in sequence"),
        [3.0 * inch, 0.9 * inch, 3.3 * inch])]

    # 5. Energy
    e_rows = [["Housing type", "Site EUI", "TEDI achieved", "TEDI target", "PV"]]
    for t in types:
        r = best[t]
        e_rows.append([ARCHETYPES[t].name, f"{r.eui_kwh_m2_yr:g}", f"{r.tedi_kwh_m2_yr:g}",
                       f"<= {r.tedi_threshold_kwh_m2_yr:g}" if r.tedi_threshold_kwh_m2_yr is not None else "No gate",
                       f"{r.pv_generation_kwh_yr * dwellings[t]:,.0f} kWh/yr"])
    e_rows.append(["Area-weighted", f"{mix.avg_eui_kwh_m2_yr:g}", "", "", ""])
    story += [_heading(5, styles), _table(e_rows, [2.4 * inch, 1.0 * inch, 1.1 * inch, 1.1 * inch, 1.6 * inch]),
              Paragraph(f"kWh/m2/yr. {mix.nzr_unit_count} of {mix.total_units} homes meet Net Zero Ready. "
                        "Degree-day screening model; confirm with a compliance model.", styles["small"])]

    story += _carbon_rows([(ARCHETYPES[t].name, best[t], area_per[t] * dwellings[t]) for t in types],
                          next(iter(benchmarks.values()))["benchmark_embodied_kg_m2"], styles)

    # 7. Lifecycle economics, summed over every home
    agg = {k: sum(benchmarks[t][k] * dwellings[t] for t in types)
           for k in ("energy_saving_kwh_yr", "benchmark_annual_utility", "utility_saving_yr",
                     "benchmark_lifecycle_cost_30yr", "lifecycle_saving_30yr")}
    total_area = sum(area_per[t] * dwellings[t] for t in types)
    first = benchmarks[types[0]]
    agg.update({"cost_per_m2": round(mix.total_cost / total_area),
                "benchmark_cost_per_m2": first["benchmark_cost_per_m2"], "benchmark_eui": first["benchmark_eui"],
                "rate_cad_per_kwh": first["rate_cad_per_kwh"], "sources": first["sources"]})
    annual_utility = sum(best[t].annual_utility_cost * dwellings[t] for t in types)
    story += [_heading(7, styles), _table(_lifecycle_rows(agg, total_area, mix.total_cost, mix.avg_eui_kwh_m2_yr,
                                                          annual_utility, mix.lifecycle_cost_30yr),
                                          [2.3 * inch, 1.5 * inch, 1.6 * inch, 1.8 * inch]),
              _lifecycle_note(agg, styles, rate=len(types) == 1)]
    story += _priority(ranks, weights, styles, "mix")
    story += _next(steps, enhancements, styles)
    doc.build(story)
    return out.getvalue()
