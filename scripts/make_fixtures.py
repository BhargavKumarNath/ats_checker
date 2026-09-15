"""Generate PDF/DOCX resume fixtures exhibiting each parseability failure mode.

Run: uv run python scripts/make_fixtures.py
Outputs are committed under tests/fixtures/ so CI needs no fonts or generators.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CLEAN = (OUT / "resume_clean.txt").read_text().split("\n")
W, H = LETTER


def _lines_to_canvas(
    c: canvas.Canvas,
    lines: list[str],
    x: float,
    y: float,
    font: str = "Helvetica",
    max_width: float = W - 2 * inch,
) -> float:
    for line in lines:
        if y < inch:
            break
        upper = line.isupper() and len(line) < 30
        name, size = ("Helvetica-Bold" if upper else font), (11 if upper else 10)
        c.setFont(name, size)
        for piece in simpleSplit(line.replace("•", "-"), name, size, max_width) or [""]:
            c.drawString(x, y, piece)
            y -= 14
    return y


def pdf_clean() -> None:
    c = canvas.Canvas(str(OUT / "resume_clean.pdf"), pagesize=LETTER)
    _lines_to_canvas(c, CLEAN, inch, H - inch)
    c.save()


def pdf_two_column() -> None:
    c = canvas.Canvas(str(OUT / "resume_two_column.pdf"), pagesize=LETTER)
    idx = CLEAN.index("EXPERIENCE")
    left = CLEAN[:idx]  # header + summary on the left
    right = CLEAN[idx:]  # experience onward on the right, side by side
    left += CLEAN[CLEAN.index("SKILLS") :]
    col = W / 2 - inch * 0.9
    _lines_to_canvas(c, left, inch * 0.6, H - inch, max_width=col)
    _lines_to_canvas(c, right[: right.index("SKILLS")], W / 2 + inch * 0.3, H - inch, max_width=col)
    c.save()


def pdf_table() -> None:
    doc = SimpleDocTemplate(str(OUT / "resume_table.pdf"), pagesize=LETTER)
    styles = getSampleStyleSheet()
    body = [Paragraph(ln or "&nbsp;", styles["Normal"]) for ln in CLEAN[: CLEAN.index("SKILLS")]]
    body.append(Paragraph("SKILLS", styles["Heading3"]))
    rows = [
        ["Languages", "Python, SQL, Go"],
        ["ML", "PyTorch, scikit-learn, XGBoost, PEFT"],
        ["LLM", "RAG, vector search, DPO"],
        ["Infra", "Docker, Kubernetes, SageMaker, MLflow, Airflow"],
    ]
    t = Table(rows, colWidths=[1.2 * inch, 4.5 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, (0, 0, 0))]))
    body += [Spacer(1, 6), t]
    doc.build(body)


def pdf_image_only() -> None:
    img = Image.new("RGB", (1700, 2200), "white")
    d = ImageDraw.Draw(img)
    y = 100
    for line in CLEAN[:30]:
        d.text((120, y), line, fill="black")
        y += 40
    png = OUT / "_scan.png"
    img.save(png)
    c = canvas.Canvas(str(OUT / "resume_image_only.pdf"), pagesize=LETTER)
    c.drawImage(str(png), 0, 0, width=W, height=H)
    c.save()
    png.unlink()


def pdf_icon_font() -> None:
    c = canvas.Canvas(str(OUT / "resume_icon_font.pdf"), pagesize=LETTER)
    y = _lines_to_canvas(c, CLEAN[: CLEAN.index("SKILLS") + 1], inch, H - inch)
    for skill, stars in [("Python", 5), ("PyTorch", 4), ("Kubernetes", 3), ("Spark", 3)]:
        c.setFont("Helvetica", 10)
        c.drawString(inch, y, skill)
        c.setFont("ZapfDingbats", 10)  # skill-bar / rating glyphs in a symbol font
        c.drawString(inch * 2.5, y, "H" * stars + "I" * (5 - stars))
        y -= 14
    c.save()


def pdf_header_footer() -> None:
    c = canvas.Canvas(str(OUT / "resume_header_footer.pdf"), pagesize=LETTER)
    body = [ln for ln in CLEAN[2:]]  # name/contact only in the running footer
    for page in range(2):
        chunk = body[page * 28 : (page + 1) * 28]
        c.setFont("Helvetica-Bold", 12)
        c.drawString(inch, H - inch * 0.6, "Priya Natarajan")
        _lines_to_canvas(c, chunk, inch, H - inch)
        c.setFont("Helvetica", 8)
        c.drawString(inch, inch * 0.5, "priya.natarajan@example.com · (512) 555-0143 · Austin, TX")
        c.showPage()
    c.save()


# --- DOCX ---------------------------------------------------------------------


def _fill(doc: Document, lines: list[str]) -> None:
    for line in lines:
        doc.add_paragraph(line)


def docx_clean() -> None:
    doc = Document()
    _fill(doc, CLEAN)
    doc.save(OUT / "resume_clean.docx")


def docx_table() -> None:
    doc = Document()
    idx = CLEAN.index("SKILLS")
    _fill(doc, CLEAN[: idx + 1])
    rows = [ln.split(": ", 1) for ln in CLEAN[idx + 1 : idx + 5]]
    t = doc.add_table(rows=len(rows), cols=2)
    t.style = "Table Grid"
    for r, (label, items) in enumerate(rows):
        t.cell(r, 0).text = label
        t.cell(r, 1).text = items
    _fill(doc, CLEAN[idx + 5 :])
    doc.save(OUT / "resume_table.docx")


def docx_textbox() -> None:
    doc = Document()
    p = doc.add_paragraph()
    run = p.add_run()
    # Minimal DrawingML text box carrying the contact block.
    xml = (
        '<w:pict xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:v="urn:schemas-microsoft-com:vml">'
        '<v:shape style="width:400pt;height:40pt"><v:textbox>'
        "<w:txbxContent><w:p><w:r><w:t>Priya Natarajan</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Austin, TX · priya.natarajan@example.com · (512) 555-0143</w:t></w:r></w:p>"
        "</w:txbxContent></v:textbox></v:shape></w:pict>"
    )
    from lxml import etree

    run._r.append(etree.fromstring(xml))
    _fill(doc, CLEAN[2:])
    doc.save(OUT / "resume_textbox.docx")


def docx_two_column() -> None:
    doc = Document()
    _fill(doc, CLEAN)
    sect_pr = doc.sections[0]._sectPr
    cols = OxmlElement("w:cols")
    cols.set(qn("w:num"), "2")
    sect_pr.append(cols)
    doc.save(OUT / "resume_two_column.docx")


def docx_header_footer() -> None:
    doc = Document()
    header = doc.sections[0].header
    header.paragraphs[0].text = "Priya Natarajan · priya.natarajan@example.com · (512) 555-0143"
    _fill(doc, CLEAN[2:])
    doc.save(OUT / "resume_header_footer.docx")


if __name__ == "__main__":
    for fn in (
        pdf_clean,
        pdf_two_column,
        pdf_table,
        pdf_image_only,
        pdf_icon_font,
        pdf_header_footer,
        docx_clean,
        docx_table,
        docx_textbox,
        docx_two_column,
        docx_header_footer,
    ):
        fn()
        print("wrote", fn.__name__)
