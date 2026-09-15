"""Resume parsing pipeline (resume_parsing_spec.md).

Entry points: parse_resume_text, parse_resume_file.
"""

from __future__ import annotations

from atsc.core.matcher import ClusterMatcher, get_default_matcher
from atsc.core.models import CheckName, ParseabilityCheck, ParseabilityReport, ParsedResume
from atsc.core.parsing.checks import build_report
from atsc.core.parsing.entities import (
    extract_basics,
    extract_education,
    extract_projects,
    extract_skills,
    extract_work,
)
from atsc.core.parsing.sections import split_sections
from atsc.core.parsing.text import clean_text


def structure_text(
    text: str,
    *,
    file_format: str = "pasted_text",
    layout_checks: dict[CheckName, ParseabilityCheck] | None = None,
    matcher: ClusterMatcher | None = None,
) -> tuple[ParsedResume, ParseabilityReport]:
    matcher = matcher or get_default_matcher()
    cleaned = clean_text(text)
    sections = split_sections(cleaned.split("\n"))
    resume = ParsedResume(
        basics=extract_basics(sections[0]),
        work=extract_work(sections, matcher),
        education=extract_education(sections),
        skills=extract_skills(sections, matcher),
        projects=extract_projects(sections, matcher),
        raw_text=cleaned,
    )
    report = build_report(file_format, sections, layout_checks)  # type: ignore[arg-type]
    return resume, report


def parse_resume_text(
    text: str, *, matcher: ClusterMatcher | None = None
) -> tuple[ParsedResume, ParseabilityReport]:
    return structure_text(text, file_format="pasted_text", matcher=matcher)


class UnsupportedFormatError(ValueError):
    """Raised for formats the spec declines on purpose (resume_parsing_spec.md §1)."""


def sniff_format(data: bytes, filename: str) -> str:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04") and b"word/" in data[:4096]:
        return "docx"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return "pdf"
    if ext == "docx":
        return "docx"
    if ext in {"txt", "md", "text"}:
        return "pasted_text"
    raise UnsupportedFormatError(
        f"'.{ext}' files are not supported. Upload a text-layer PDF or a .docx, or paste the text. "
        "Scanned/image PDFs, .pages, .odt and image files are declined because most ATS platforms "
        "cannot read them either."
    )


def parse_resume_file(
    data: bytes, filename: str, *, matcher: ClusterMatcher | None = None
) -> tuple[ParsedResume, ParseabilityReport]:
    fmt = sniff_format(data, filename)
    if fmt == "pdf":
        from atsc.core.parsing.pdf import extract_pdf

        ex = extract_pdf(data)
        return structure_text(ex.text, file_format="pdf", layout_checks=ex.checks, matcher=matcher)
    if fmt == "docx":
        from atsc.core.parsing.docx_reader import extract_docx

        dx = extract_docx(data)
        return structure_text(dx.text, file_format="docx", layout_checks=dx.checks, matcher=matcher)
    return parse_resume_text(data.decode("utf-8", errors="replace"), matcher=matcher)


__all__ = ["UnsupportedFormatError", "parse_resume_file", "parse_resume_text", "structure_text"]
