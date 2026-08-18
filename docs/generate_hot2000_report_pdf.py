"""
Render docs/HOT2000_Surrogate_Report.md to docs/HOT2000_Surrogate_Report.pdf.

    python docs/generate_hot2000_report_pdf.py

Same look as docs/generate_pdf.py (EnerZen Methodology) — reuses its
markdown renderer and styling directly rather than duplicating it, just
with this report's own title/footer and no {{PLACEHOLDER}} data tables.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_pdf import (  # noqa: E402
    MARGIN, MUTED, PAGE_H, PAGE_W, RULE, CONTENT_W,
    build_styles, md_to_flowables,
)

from reportlab.lib.pagesizes import letter
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

ROOT = Path(__file__).parent.parent
MD_PATH = ROOT / "docs" / "HOT2000_Surrogate_Report.md"
PDF_PATH = ROOT / "docs" / "HOT2000_Surrogate_Report.pdf"

TITLE = "EnerZen — HOT2000 Surrogate Model Progress Report"


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 0.55 * 72, "EnerZen R&D — HOT2000 Surrogate Model")
    canvas.drawRightString(PAGE_W - MARGIN, 0.55 * 72, f"Page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, 0.72 * 72, PAGE_W - MARGIN, 0.72 * 72)
    canvas.restoreState()


def main() -> int:
    if not MD_PATH.exists():
        print(f"error: {MD_PATH} not found", file=sys.stderr)
        return 1

    md = MD_PATH.read_text(encoding="utf-8").replace("{{DATE}}", date.today().isoformat())

    styles = build_styles()
    story = md_to_flowables(md, styles)

    doc = BaseDocTemplate(
        str(PDF_PATH), pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=TITLE, author="EnerZen",
    )
    frame = Frame(MARGIN, MARGIN, CONTENT_W, PAGE_H - 2 * MARGIN, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])
    doc.build(story)

    print(f"wrote {PDF_PATH.relative_to(ROOT)} ({PDF_PATH.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
