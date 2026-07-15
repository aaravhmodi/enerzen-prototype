"""Generate a client-ready PDF summary for one optimized configuration."""

from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

INK = colors.HexColor("#18211D")
MUTED = colors.HexColor("#66706A")
FOREST = colors.HexColor("#214E3B")
SAGE = colors.HexColor("#D8E6DC")
PAPER = colors.HexColor("#FFFEFA")
LINE = colors.HexColor("#D9DDD8")


def _money(value):
    return f"${value:,.0f}"


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=24, leading=28, textColor=INK, alignment=0,
                                spaceAfter=8),
        "eyebrow": ParagraphStyle("Eyebrow", parent=base["BodyText"], fontName="Helvetica-Bold",
                                  fontSize=7.5, leading=10, textColor=FOREST,
                                  spaceAfter=7, uppercase=True),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12, leading=15, textColor=INK, spaceBefore=14,
                             spaceAfter=7),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=8.7, leading=12.5, textColor=INK, spaceAfter=5),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName="Helvetica",
                                fontSize=7.2, leading=10, textColor=MUTED),
        "right": ParagraphStyle("Right", parent=base["BodyText"], fontName="Helvetica",
                                fontSize=7.2, leading=10, textColor=MUTED, alignment=TA_RIGHT),
    }


def _table(rows, widths=None, header=True):
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


def generate_results_pdf(spec, result, location, labels: dict) -> bytes:
    """Return a complete results report as PDF bytes."""
    out = BytesIO()
    styles = _styles()

    def page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(0.65 * inch, 0.52 * inch, 7.85 * inch, 0.52 * inch)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.setFillColor(FOREST)
        canvas.drawString(0.65 * inch, 0.34 * inch, "ENERZEN")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(7.85 * inch, 0.34 * inch, f"Project performance report  |  {doc.page}")
        canvas.restoreState()

    frame = Frame(0.65 * inch, 0.68 * inch, 7.2 * inch, 9.45 * inch,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(out, pagesize=letter, pageTemplates=[PageTemplate("Report", [frame], onPage=page)],
                          title="EnerZen Project Performance Report", author="EnerZen")

    story = [
        Paragraph("PROJECT PERFORMANCE REPORT", styles["eyebrow"]),
        Paragraph("Recommended building configuration", styles["title"]),
        Paragraph(
            f"{location.name} &nbsp; | &nbsp; {spec.footprint_length_m:g} x "
            f"{spec.footprint_width_m:g} m footprint &nbsp; | &nbsp; {spec.storeys} storey"
            f"{'s' if spec.storeys > 1 else ''} &nbsp; | &nbsp; {spec.floor_area_m2:g} m2 conditioned",
            styles["body"]),
        Paragraph(f"Prepared {date.today().strftime('%B %d, %Y')}", styles["small"]),
        Spacer(1, 12),
    ]

    metrics = [
        ["Construction", "Energy", "Carbon", "Confidence"],
        [_money(result.construction_cost), f"{result.net_eui_kwh_m2_yr:g} kWh/m2/yr",
         f"{result.embodied_carbon_kg_co2e_m2:.0f} kgCO2e/m2", f"{result.nzr_probability:.0%} NZR"],
        [f"{result.construction_weeks:g} weeks to close", f"{result.energy.tedi_kwh_m2_yr:g} TEDI",
         f"{result.energy.meui_kwh_m2_yr:g} MEUI", f"EnerGuide {result.energuide_score:g}/100"],
    ]
    summary = _table(metrics, [1.8 * inch] * 4)
    summary.setStyle(TableStyle([("BACKGROUND", (0, 1), (-1, -1), SAGE),
                                 ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                                 ("FONTSIZE", (0, 1), (-1, 1), 12)]))
    story += [summary, Paragraph("Site and design basis", styles["h2"])]

    story.append(_table([
        ["Input", "Resolved value", "Design implication"],
        ["Location", location.name, f"Climate zone {location.climate_zone}; {location.region_name}"],
        ["Snow", f"Ss {location.ss:g} kPa; roof S {location.roof_snow_load_kpa:g} kPa",
         f"{location.snow_tier['name']}; {location.joist_depth_in}\" preliminary joist"],
        ["Soil defaults", f"{location.allowable_bearing_kpa:g} kPa bearing; "
                          f"{location.frost_depth_m:g} m frost depth",
         "Regional defaults; confirm by geotechnical investigation"],
        ["Target", labels["target"], f"TEDI limit {result.energy.nzr_threshold:g} kWh/m2/yr"],
    ], [1.25 * inch, 2.25 * inch, 3.7 * inch]))

    story += [Paragraph("Selected systems", styles["h2"]), _table([
        ["System", "Selection", "Thermal result"],
        ["Wall", labels["wall"], f"Effective R-{result.assembly_breakdown['wall']['r_effective']}"],
        ["Roof", labels["roof"], f"Effective R-{result.assembly_breakdown['roof']['r_effective']}"],
        ["Foundation", labels["floor"], f"Effective R-{result.assembly_breakdown['floor']['r_effective']}"],
        ["Windows", labels["window"], result.window_id],
        ["Mechanical", labels["mechanical"], result.mechanical_id],
        ["Solar", labels["solar"], f"{result.pv_capacity_kw:g} kW; {result.pv_generation_kwh_yr:,.0f} kWh/yr"],
    ], [1.15 * inch, 4.25 * inch, 1.8 * inch])]

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
        ["Construction total", _money(cb["total_per_unit"])],
    ]
    story += [Paragraph("Cost plan", styles["h2"]), _table(cost_rows, [5.8 * inch, 1.4 * inch])]

    floor = result.assembly_breakdown["floor"]
    if "eps_area_m2" in floor:
        story += [Paragraph("Foundation quantities", styles["h2"]), _table([
            ["Quantity", "Result"],
            ["Footprint", f"{floor['footprint_length_m']:g} x {floor['footprint_width_m']:g} m = "
                          f"{floor['footprint_area_m2']:g} m2"],
            ["EPS blanket", f"{floor['extended_length_m']:g} x {floor['extended_width_m']:g} m = "
                            f"{floor['eps_area_m2']:g} m2; {floor['eps_volume_m3']:g} m3"],
            ["Slab concrete", f"{floor['slab_concrete_m3']:g} m3"],
            ["Frost-wall concrete", f"{floor['frost_wall_concrete_m3']:g} m3"],
        ], [2.2 * inch, 5 * inch])]

    story += [Paragraph("Operating and lifecycle outlook", styles["h2"]), _table([
        ["Measure", "Estimate"],
        ["Average utility bill", f"{_money(result.avg_monthly_utility)} / month"],
        ["Annual utility cost", f"{_money(result.annual_utility_cost)} / year"],
        ["20-year lifecycle cost", _money(result.lifecycle_cost_20yr)],
        ["30-year lifecycle cost", _money(result.lifecycle_cost_30yr)],
    ], [3.6 * inch, 3.6 * inch])]

    story += [Paragraph("Important limitations", styles["h2"]), Paragraph(
        "This report is a comparative concept-stage estimate, not a permit, tender or structural design. "
        "Snow-to-joist mapping is preliminary. Soil bearing and frost depth are regional defaults. "
        "Material prices, embodied-carbon factors, installation productivity, fit-out allowances and "
        "mechanical costs must be replaced with EnerZen procurement and project data before quotation. "
        "Confirm foundation, roof structure, energy compliance and geotechnical conditions with the "
        "appropriate qualified professionals.", styles["small"])]

    doc.build(story)
    return out.getvalue()
