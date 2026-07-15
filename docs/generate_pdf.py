"""
Render docs/METHODOLOGY.md to docs/EnerZen_Methodology.pdf.

    python docs/generate_pdf.py

Requires reportlab (see docs/requirements-docs.txt). It is a documentation-only
dependency and is deliberately kept out of the app's requirements.txt so the
Streamlit deploy stays lean.

WHEN YOU CHANGE A CALCULATION: edit docs/METHODOLOGY.md and re-run this script.
The reference-data and catalog tables are generated from data/assemblies.json at
build time via the {{PLACEHOLDER}} tokens below, so those stay in sync on their
own — you only hand-edit the prose and formulas.

Supported Markdown subset: # / ## / ### headings, paragraphs, - bullets,
``` fenced code, | pipe tables |, --- rules, **bold**, `inline code`.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, ListFlowable, ListItem, PageTemplate,
    Paragraph, Preformatted, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).parent.parent
MD_PATH = ROOT / "docs" / "METHODOLOGY.md"
PDF_PATH = ROOT / "docs" / "EnerZen_Methodology.pdf"
DATA_PATH = ROOT / "data" / "assemblies.json"

BRAND = colors.HexColor("#1A5276")
MUTED = colors.HexColor("#666666")
RULE = colors.HexColor("#D5DBDB")
CODE_BG = colors.HexColor("#F4F6F7")

PAGE_W, PAGE_H = letter
MARGIN = 0.9 * inch
CONTENT_W = PAGE_W - 2 * MARGIN


# ── Styles ───────────────────────────────────────────────────────────────────

def build_styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                             fontSize=19, leading=23, spaceBefore=6, spaceAfter=10,
                             textColor=BRAND),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                             fontSize=13.5, leading=17, spaceBefore=16, spaceAfter=7,
                             textColor=BRAND),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold",
                             fontSize=11, leading=14, spaceBefore=11, spaceAfter=5,
                             textColor=colors.HexColor("#21618C")),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica",
                               fontSize=9.5, leading=13.5, spaceAfter=6,
                               alignment=TA_LEFT),
        "bullet": ParagraphStyle("bullet", parent=ss["BodyText"], fontName="Helvetica",
                                 fontSize=9.5, leading=13.5, spaceAfter=2),
        "code": ParagraphStyle("code", parent=ss["Code"], fontName="Courier",
                               fontSize=8.2, leading=10.5, textColor=colors.HexColor("#212F3D"),
                               backColor=CODE_BG, borderPadding=6, spaceBefore=4, spaceAfter=8),
        "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                             textColor=colors.white),
        "td": ParagraphStyle("td", fontName="Helvetica", fontSize=8.5, leading=11),
    }


# ── Inline markdown ──────────────────────────────────────────────────────────

def inline(text: str) -> str:
    """Escape XML, then apply **bold** and `code` for reportlab's mini-markup."""
    text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r'<font face="Courier" size="8.6">\1</font>', text)
    return text


# ── Table rendering ──────────────────────────────────────────────────────────

def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def make_table(rows: list[list[str]], styles) -> Table:
    header, body = rows[0], rows[1:]
    ncols = len(header)

    # Distribute width proportionally to the longest cell in each column.
    widths = []
    for c in range(ncols):
        longest = max((len(r[c]) for r in rows if c < len(r)), default=8)
        widths.append(max(longest, 6))
    total = sum(widths)
    col_widths = [CONTENT_W * w / total for w in widths]

    data = [[Paragraph(inline(c), styles["th"]) for c in header]]
    for r in body:
        r = (r + [""] * ncols)[:ncols]
        data.append([Paragraph(inline(c), styles["td"]) for c in r])

    t = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9F9")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
    ]))
    return t


# ── Markdown → flowables ─────────────────────────────────────────────────────

def md_to_flowables(md: str, styles) -> list:
    out = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Fenced code
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append(Preformatted("\n".join(buf), styles["code"]))
            continue

        # Table
        if stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            rows = [_split_row(b) for b in block]
            rows = [r for r in rows if not all(set(c) <= set("-: ") and c for c in r)]
            if rows:
                out.append(Spacer(1, 3))
                out.append(make_table(rows, styles))
                out.append(Spacer(1, 8))
            continue

        # Horizontal rule
        if stripped == "---":
            out.append(Spacer(1, 5))
            out.append(HRFlowable(width="100%", thickness=0.6, color=RULE))
            out.append(Spacer(1, 7))
            i += 1
            continue

        # Headings
        if stripped.startswith("### "):
            out.append(Paragraph(inline(stripped[4:]), styles["h3"]))
            i += 1
            continue
        if stripped.startswith("## "):
            out.append(Paragraph(inline(stripped[3:]), styles["h2"]))
            i += 1
            continue
        if stripped.startswith("# "):
            out.append(Paragraph(inline(stripped[2:]), styles["h1"]))
            i += 1
            continue

        # Bullets
        if stripped.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                buf = [lines[i].strip()[2:]]
                i += 1
                # continuation lines (indented, not a new bullet)
                while (i < len(lines) and lines[i].strip()
                       and not lines[i].strip().startswith("- ")
                       and lines[i].startswith("  ")):
                    buf.append(lines[i].strip())
                    i += 1
                items.append(ListItem(Paragraph(inline(" ".join(buf)), styles["bullet"]),
                                      leftIndent=14))
            out.append(ListFlowable(items, bulletType="bullet", bulletFontSize=6,
                                    bulletOffsetY=1, leftIndent=12, spaceAfter=7))
            continue

        # Paragraph
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^\s*(#{1,3} |- |\||```|---\s*$)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append(Paragraph(inline(" ".join(buf)), styles["body"]))

    return out


# ── Auto-generated tables from assemblies.json ───────────────────────────────

def climate_table(cat) -> str:
    rows = ["### Climate zones", "",
            "| Zone | Region | HDD | CDD | Design temp | NZR EUI threshold | Solar yield |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for z, c in cat["climate_zones"].items():
        rows.append(f"| {z} | {c['name']} | {c['hdd']} | {c['cdd']} | "
                    f"{c['design_temp_heating']} C | {c['nzr_eui_threshold']} kWh/m2/yr | "
                    f"{c.get('solar_yield_kwh_per_kwp', '-')} kWh/kWp |")
    return "\n".join(rows)


def rates_table(cat) -> str:
    r = cat["energy_rates"]
    rows = ["### Energy rates and factors", "",
            "| Parameter | Value | Source |", "| --- | --- | --- |",
            f"| Electricity | {r['electricity_cad_per_kwh']} CAD/kWh | {r['electricity_source']} |",
            f"| Natural gas | {r['natural_gas_cad_per_kwh']} CAD/kWh | {r['natural_gas_source']} |",
            f"| Grid intensity | {r['grid_intensity_kg_co2e_per_kwh']} kgCO2e/kWh | {r['grid_intensity_source']} |",
            f"| Solar rebate | {r['solar_rebate_cad']} CAD | {r['solar_rebate_source']} |"]
    return "\n".join(rows)


def benchmark_table(cat) -> str:
    b = cat["benchmarks"]
    rows = ["### Comparison benchmarks", "",
            "| Metric | Value | Source |", "| --- | --- | --- |",
            f"| Existing home EUI | {b['eui_kwh_m2_yr']['existing_home']} kWh/m2/yr | {b['eui_kwh_m2_yr']['_source']} |",
            f"| Code-built new home EUI | {b['eui_kwh_m2_yr']['code_built_new']} kWh/m2/yr | {b['eui_kwh_m2_yr']['_source']} |",
            f"| Conventional build cost | {b['cost_per_m2']['conventional_new_build']} CAD/m2 | {b['cost_per_m2']['_source']} |",
            f"| Conventional embodied carbon | {b['embodied_carbon_kg_co2e_m2']['conventional_new_build']} kgCO2e/m2 | {b['embodied_carbon_kg_co2e_m2']['_source']} |"]
    return "\n".join(rows)


def catalog_tables(cat) -> str:
    out = []

    def envelope(key, title, extra_r=True):
        rows = [f"### {title}", "",
                "| ID | Name | R | U (W/m2K) | Cost /m2 | Carbon /m2 | Install hr/m2 |",
                "| --- | --- | --- | --- | --- | --- | --- |"]
        for a in cat[key]:
            rows.append(f"| {a['id']} | {a['name']} | R{a['r_value']} | {a['u_value']} | "
                        f"{a['cost_per_m2']} | {a['embodied_carbon_kg_co2e_m2']} | "
                        f"{a['install_hours_per_m2']} |")
        out.append("\n".join(rows))

    envelope("wall_panels", "Wall panels")
    envelope("roof_cassettes", "Roof cassettes")
    envelope("floor_cassettes", "Floor cassettes")

    rows = ["### Window packages", "",
            "| ID | Name | U (W/m2K) | SHGC | Cost /m2 | Carbon /m2 |",
            "| --- | --- | --- | --- | --- | --- |"]
    for w in cat["windows"]:
        rows.append(f"| {w['id']} | {w['name']} | {w['u_value']} | {w['shgc']} | "
                    f"{w['cost_per_m2']} | {w['embodied_carbon_kg_co2e_m2']} |")
    out.append("\n".join(rows))

    rows = ["### Mechanical systems", "",
            "| ID | Name | Type | Heating COP | Cooling COP | HRV | Cost | Carbon |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for m in cat["mechanical"]:
        rows.append(f"| {m['id']} | {m['name']} | {m['type']} | {m['heating_cop']} | "
                    f"{m['cooling_cop']} | {m.get('hrv_efficiency', '-')} | {m['cost']} | "
                    f"{m['embodied_carbon_kg_co2e']} |")
    out.append("\n".join(rows))

    rows = ["### Solar options", "",
            "| ID | Name | Capacity | Cost /kW | Carbon /kW |",
            "| --- | --- | --- | --- | --- |"]
    for s in cat["solar"]:
        rows.append(f"| {s['id']} | {s['name']} | {s['capacity_kw']} kW | "
                    f"{s['cost_per_kw']} | {s['embodied_carbon_kg_co2e_per_kw']} |")
    out.append("\n".join(rows))

    return "\n\n".join(out)


# ── Page furniture ───────────────────────────────────────────────────────────

def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 0.55 * inch, "EnerZen Performance Engine — Methodology")
    canvas.drawRightString(PAGE_W - MARGIN, 0.55 * inch, f"Page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, 0.72 * inch, PAGE_W - MARGIN, 0.72 * inch)
    canvas.restoreState()


def main() -> int:
    if not MD_PATH.exists():
        print(f"error: {MD_PATH} not found", file=sys.stderr)
        return 1

    cat = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    md = MD_PATH.read_text(encoding="utf-8")

    md = (md.replace("{{DATE}}", date.today().isoformat())
            .replace("{{CLIMATE_TABLE}}", climate_table(cat))
            .replace("{{RATES_TABLE}}", rates_table(cat))
            .replace("{{BENCHMARK_TABLE}}", benchmark_table(cat))
            .replace("{{CATALOG_TABLES}}", catalog_tables(cat)))

    styles = build_styles()
    story = md_to_flowables(md, styles)

    doc = BaseDocTemplate(
        str(PDF_PATH), pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title="EnerZen Performance Engine — Methodology",
        author="EnerZen",
    )
    frame = Frame(MARGIN, MARGIN, CONTENT_W, PAGE_H - 2 * MARGIN, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    doc.build(story)

    print(f"wrote {PDF_PATH.relative_to(ROOT)} ({PDF_PATH.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
