"""PDF and DOCX parsing with structural layout detection (resume_parsing_spec.md §2 step 2, §3)."""

from pathlib import Path

import pytest

from atsc.core.models import CheckName, ParseabilityReport, Platform, Severity
from atsc.core.parsing import UnsupportedFormatError, parse_resume_file

FIXTURES = Path(__file__).parent / "fixtures"


def _parse(name: str):
    return parse_resume_file((FIXTURES / name).read_bytes(), name)


def _status(report: ParseabilityReport, name: CheckName) -> str:
    return next(c for c in report.checks if c.check_name == name).status


def _location(report: ParseabilityReport, name: CheckName) -> str:
    return next(c for c in report.checks if c.check_name == name).location


# -- PDF --------------------------------------------------------------------------


def test_clean_pdf_parses_content_and_passes_layout_checks() -> None:
    resume, report = _parse("resume_clean.pdf")
    assert report.file_format == "pdf"
    assert resume.basics.email == "priya.natarajan@example.com"
    assert [w.company for w in resume.work] == ["Acme Robotics", "Northwind Analytics"]
    for name in (
        CheckName.MULTI_COLUMN_LAYOUT,
        CheckName.TABLE_DETECTED,
        CheckName.NON_STANDARD_FONT,
        CheckName.IMAGE_BASED_PDF,
        CheckName.HEADER_FOOTER_CONTENT,
    ):
        assert _status(report, name) == "pass", name
    # Text boxes are not detectable in a PDF text stream.
    assert _status(report, CheckName.TEXT_BOX_DETECTED) == "not_assessed"


def test_two_column_pdf_is_flagged_with_workday_high_severity() -> None:
    _, report = _parse("resume_two_column.pdf")
    check = next(c for c in report.checks if c.check_name == CheckName.MULTI_COLUMN_LAYOUT)
    assert check.status == "fail"
    assert "page 1" in check.location
    assert check.platform_severity[Platform.WORKDAY] == Severity.HIGH
    assert check.platform_severity[Platform.GREENHOUSE] == Severity.MEDIUM


def test_ruled_table_in_pdf_is_flagged() -> None:
    _, report = _parse("resume_table.pdf")
    assert _status(report, CheckName.TABLE_DETECTED) == "fail"
    assert "page 1" in _location(report, CheckName.TABLE_DETECTED)


def test_image_only_pdf_is_flagged_and_yields_no_content() -> None:
    resume, report = _parse("resume_image_only.pdf")
    assert _status(report, CheckName.IMAGE_BASED_PDF) == "fail"
    assert resume.raw_text == "" and resume.work == []


def test_symbol_font_skill_bars_are_flagged() -> None:
    _, report = _parse("resume_icon_font.pdf")
    assert _status(report, CheckName.NON_STANDARD_FONT) == "fail"
    assert "ZapfDingbats" in _location(report, CheckName.NON_STANDARD_FONT)


def test_contact_info_in_repeated_footer_is_flagged() -> None:
    _, report = _parse("resume_header_footer.pdf")
    assert _status(report, CheckName.HEADER_FOOTER_CONTENT) == "fail"
    assert "footer" in _location(report, CheckName.HEADER_FOOTER_CONTENT).lower()


# -- DOCX -------------------------------------------------------------------------


def test_clean_docx_parses_content_and_passes_layout_checks() -> None:
    resume, report = _parse("resume_clean.docx")
    assert report.file_format == "docx"
    assert resume.basics.name == "Priya Natarajan"
    assert len(resume.work) == 2 and len(resume.work[0].bullets) == 4
    for name in (
        CheckName.MULTI_COLUMN_LAYOUT,
        CheckName.TABLE_DETECTED,
        CheckName.TEXT_BOX_DETECTED,
        CheckName.NON_STANDARD_FONT,
        CheckName.HEADER_FOOTER_CONTENT,
    ):
        assert _status(report, name) == "pass", name


def test_docx_table_is_flagged_and_its_text_is_still_extracted() -> None:
    resume, report = _parse("resume_table.docx")
    assert _status(report, CheckName.TABLE_DETECTED) == "fail"
    assert "Skills" in _location(report, CheckName.TABLE_DETECTED) or "SKILLS" in _location(
        report, CheckName.TABLE_DETECTED
    )
    assert any(s.raw_text == "PyTorch" for s in resume.skills)


def test_docx_text_box_is_flagged() -> None:
    _, report = _parse("resume_textbox.docx")
    assert _status(report, CheckName.TEXT_BOX_DETECTED) == "fail"
    assert "Priya Natarajan" in _location(report, CheckName.TEXT_BOX_DETECTED)


def test_docx_two_column_section_is_flagged() -> None:
    _, report = _parse("resume_two_column.docx")
    assert _status(report, CheckName.MULTI_COLUMN_LAYOUT) == "fail"


def test_docx_contact_in_header_is_flagged() -> None:
    _, report = _parse("resume_header_footer.docx")
    assert _status(report, CheckName.HEADER_FOOTER_CONTENT) == "fail"
    assert "header" in _location(report, CheckName.HEADER_FOOTER_CONTENT).lower()


# -- unsupported ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["resume.pages", "scan.png", "resume.odt"])
def test_unsupported_formats_are_declined_plainly(name: str) -> None:
    with pytest.raises(UnsupportedFormatError) as exc:
        parse_resume_file(b"\x00\x01", name)
    assert "not supported" in str(exc.value)


def test_format_is_sniffed_from_bytes_not_only_extension() -> None:
    data = (FIXTURES / "resume_clean.pdf").read_bytes()
    _, report = parse_resume_file(data, "upload.bin")
    assert report.file_format == "pdf"
