from io import BytesIO

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def render_pdf(run, start=1, end=None, copies=1):
    """Render pages start..end (1-based, inclusive) of a finished report."""
    pages = run.pages
    total = len(pages)
    start = max(1, start)
    end = min(end or total, total)
    if total == 0 or start > end:
        raise ValueError("That page range has no pages.")
    selection = list(range(start - 1, end)) * max(1, copies)

    styles = getSampleStyleSheet()
    heading, small = styles["Heading2"], styles["Normal"]
    station = "TotalEnergies Bonje"
    result = run.result

    def footer(canvas, doc):
        index = selection[min(doc.page, len(selection)) - 1]
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(12 * mm, 8 * mm, f"{station}  |  {result['title']}  |  {result['subtitle']}")
        canvas.drawRightString(landscape(A4)[0] - 12 * mm, 8 * mm, f"Page {index + 1} of {total}")
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=15 * mm,
        title=result["title"],
    )
    story = []
    for position, index in enumerate(selection):
        page = pages[index]
        title = page["title"] + (f" ({page['part']})" if page["part"] else "")
        story += [Paragraph(result["title"], styles["Heading1"]), Paragraph(result["subtitle"], small), Spacer(1, 3 * mm), Paragraph(title, heading)]
        data = [page["columns"]] + page["rows"] + ([page["totals"]] if page["totals"] else [])
        table = Table(data, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2A44")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEADING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8BFCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F9")]),
            ("ALIGN", (3 if len(page["columns"]) > 4 else 1, 1), (-1, -1), "RIGHT"),
        ]
        if page["totals"]:
            style += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black)]
        table.setStyle(TableStyle(style))
        story.append(table)
        if page["note"]:
            story += [Spacer(1, 3 * mm), Paragraph(page["note"], small)]
        if position < len(selection) - 1:
            story.append(PageBreak())
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
