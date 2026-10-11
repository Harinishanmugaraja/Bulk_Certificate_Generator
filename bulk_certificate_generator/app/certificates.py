"""PDF certificate rendering helpers."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas


def generate_certificate(output_path: str | Path, recipient_name: str, course_name: str,
                        issue_date: str, certificate_id: str) -> None:
    """Render one certificate using the application's single predefined template."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))

    # Simple fixed template: double border, title, recipient, course and identifier.
    pdf.setFillColor(colors.HexColor("#16324F"))
    pdf.rect(0, page_height - 18, page_width, 18, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#C69C3F"))
    pdf.setLineWidth(3)
    pdf.rect(24, 24, page_width - 48, page_height - 48, fill=0, stroke=1)
    pdf.setLineWidth(1)
    pdf.rect(32, 32, page_width - 64, page_height - 64, fill=0, stroke=1)

    pdf.setFillColor(colors.HexColor("#16324F"))
    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawCentredString(page_width / 2, page_height - 105, "CERTIFICATE OF ACHIEVEMENT")
    pdf.setFillColor(colors.HexColor("#444444"))
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(page_width / 2, page_height - 150, "This certificate is proudly presented to")
    pdf.setFillColor(colors.HexColor("#16324F"))
    pdf.setFont("Helvetica-Bold", 26)
    # ReportLab's standard font encoding may not support every Unicode glyph;
    # escaping is handled by ReportLab, while user input is kept out of PDF markup.
    safe_name = recipient_name.encode("latin-1", "replace").decode("latin-1")
    pdf.drawCentredString(page_width / 2, page_height - 195, safe_name[:90])
    pdf.setStrokeColor(colors.HexColor("#C69C3F"))
    pdf.line(page_width * 0.25, page_height - 207, page_width * 0.75, page_height - 207)
    pdf.setFillColor(colors.HexColor("#444444"))
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(page_width / 2, page_height - 245, "for successfully completing")
    pdf.setFillColor(colors.HexColor("#16324F"))
    pdf.setFont("Helvetica-Bold", 20)
    safe_course = course_name.encode("latin-1", "replace").decode("latin-1")
    pdf.drawCentredString(page_width / 2, page_height - 278, safe_course[:100])
    pdf.setFillColor(colors.HexColor("#444444"))
    pdf.setFont("Helvetica", 11)
    pdf.drawString(65, 65, f"Issue date: {issue_date}")
    pdf.drawRightString(page_width - 65, 65, f"Certificate ID: {certificate_id}")
    pdf.save()
