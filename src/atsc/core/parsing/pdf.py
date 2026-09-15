"""PDF extraction and structural layout detection (resume_parsing_spec.md §2 step 2, §3).

Text comes from pdfplumber's linear extraction on purpose: that is what an ATS
sees, scrambled columns included. The checks then explain why.
"""

from __future__ import annotations

import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import pdfplumber

from atsc.core.models import CheckName, ParseabilityCheck
from atsc.core.parsing.checks import make_check

_SYMBOL_FONT_RE = re.compile(
    r"zapf|dingbat|wingding|webding|symbol|fontawesome|font-awesome|icomoon|material.?icons|glyphicons",
    re.IGNORECASE,
)
_TYPE3_RE = re.compile(r"type3|\bT3\b|unnamed", re.IGNORECASE)
_CID_RE = re.compile(r"\(cid:\d+\)")
_CONTACT_RE = re.compile(r"@|\(?\+?\d[\d\s().-]{7,}\d")
_MARGIN = 0.08  # top/bottom 8% of the page height counts as header/footer zone
_MIN_TEXT_CHARS = 40


@dataclass
class PdfExtraction:
    text: str
    checks: dict[CheckName, ParseabilityCheck] = field(default_factory=dict)


def _strip_subset(fontname: str) -> str:
    return fontname.split("+", 1)[1] if "+" in fontname[:8] else fontname


def _detect_columns(page: pdfplumber.page.Page) -> bool:
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    if len(words) < 30:
        return False
    width = float(page.width)
    bins = 60
    coverage = [0] * bins
    for w in words:
        lo = int(max(0.0, float(w["x0"])) / width * bins)
        hi = int(min(width, float(w["x1"])) / width * bins)
        for b in range(max(0, lo), min(bins, hi + 1)):
            coverage[b] += 1
    # A gutter: a run of empty bins in the middle half of the page.
    gutters = [b for b in range(int(bins * 0.25), int(bins * 0.75)) if coverage[b] == 0]
    if not gutters:
        return False
    split_x = (gutters[len(gutters) // 2] + 0.5) / bins * width
    # Words on both sides must share the same rows: that is what makes it two columns
    # rather than an indented block.
    rows_left: set[int] = set()
    rows_right: set[int] = set()
    for w in words:
        row = int(float(w["top"]) // 4)
        (rows_left if float(w["x1"]) <= split_x else rows_right).add(row)
    shared = len(rows_left & rows_right)
    return shared >= 6 and len(rows_left) >= 6 and len(rows_right) >= 6


def _margin_lines(page: pdfplumber.page.Page) -> tuple[list[str], list[str]]:
    height = float(page.height)
    top, bottom = [], []
    for line in page.extract_text_lines(layout=False):
        text = line["text"].strip()
        if not text:
            continue
        if float(line["bottom"]) <= height * _MARGIN:
            top.append(text)
        elif float(line["top"]) >= height * (1 - _MARGIN):
            bottom.append(text)
    return top, bottom


def extract_pdf(data: bytes) -> PdfExtraction:
    checks: dict[CheckName, ParseabilityCheck] = {}
    texts: list[str] = []
    column_pages: list[int] = []
    table_pages: list[int] = []
    fonts: Counter[str] = Counter()
    n_images = 0
    margin_hits: dict[str, list[tuple[int, str]]] = defaultdict(list)

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            texts.append(page_text)
            n_images += len(page.images)
            for ch in page.chars:
                fonts[_strip_subset(str(ch.get("fontname", "")))] += 1
            if _detect_columns(page):
                column_pages.append(pno)
            if any(len(t.rows) >= 2 and len(t.rows[0].cells) >= 2 for t in page.find_tables()):
                table_pages.append(pno)
            top, bottom = _margin_lines(page)
            for zone, lines in (("header", top), ("footer", bottom)):
                for text in lines:
                    margin_hits[text].append((pno, zone))
        n_pages = len(pdf.pages)

    full_text = "\n".join(texts).strip()
    text_chars = len(re.sub(r"\s", "", full_text))

    # image_based_pdf
    if text_chars < _MIN_TEXT_CHARS and n_images > 0:
        checks[CheckName.IMAGE_BASED_PDF] = make_check(
            CheckName.IMAGE_BASED_PDF,
            "fail",
            f"No text layer found ({n_images} image(s), {text_chars} extractable characters)",
        )
        full_text = ""
    else:
        checks[CheckName.IMAGE_BASED_PDF] = make_check(CheckName.IMAGE_BASED_PDF, "pass")

    # multi_column_layout
    checks[CheckName.MULTI_COLUMN_LAYOUT] = (
        make_check(
            CheckName.MULTI_COLUMN_LAYOUT,
            "fail",
            "Two or more text columns on " + ", ".join(f"page {p}" for p in column_pages),
        )
        if column_pages
        else make_check(CheckName.MULTI_COLUMN_LAYOUT, "pass")
    )

    # table_detected
    checks[CheckName.TABLE_DETECTED] = (
        make_check(
            CheckName.TABLE_DETECTED,
            "fail",
            "Ruled table on " + ", ".join(f"page {p}" for p in table_pages),
        )
        if table_pages
        else make_check(CheckName.TABLE_DETECTED, "pass")
    )

    # non_standard_font: symbol/icon fonts, Type 3 fonts, or glyphs with no Unicode mapping
    bad_fonts = sorted({f for f in fonts if _SYMBOL_FONT_RE.search(f) or _TYPE3_RE.search(f)})
    cid_count = len(_CID_RE.findall(full_text))
    if bad_fonts or (text_chars and cid_count / max(text_chars, 1) > 0.01):
        detail = []
        if bad_fonts:
            detail.append("symbol/icon or Type 3 fonts: " + ", ".join(bad_fonts))
        if cid_count:
            detail.append(f"{cid_count} glyph(s) with no text mapping")
        checks[CheckName.NON_STANDARD_FONT] = make_check(
            CheckName.NON_STANDARD_FONT, "fail", "; ".join(detail)
        )
    else:
        checks[CheckName.NON_STANDARD_FONT] = make_check(CheckName.NON_STANDARD_FONT, "pass")

    # header_footer_content: contact info in text that repeats in a margin zone across pages
    repeated = [
        (text, hits)
        for text, hits in margin_hits.items()
        if n_pages > 1 and len({p for p, _ in hits}) > 1 and _CONTACT_RE.search(text)
    ]
    if repeated:
        text, hits = repeated[0]
        zone = hits[0][1]
        checks[CheckName.HEADER_FOOTER_CONTENT] = make_check(
            CheckName.HEADER_FOOTER_CONTENT,
            "fail",
            f'Contact details in a running {zone} on every page: "{text[:60]}"',
        )
    else:
        checks[CheckName.HEADER_FOOTER_CONTENT] = make_check(
            CheckName.HEADER_FOOTER_CONTENT, "pass"
        )

    # text boxes are not distinguishable in a PDF text stream: left not_assessed
    return PdfExtraction(text=full_text, checks=checks)
