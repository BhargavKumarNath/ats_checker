"""ATS parseability checks and the platform severity table (resume_parsing_spec.md §3).

Every report carries all eight checks in a fixed order. A check the input format
cannot support is `not_assessed`, never `pass` (build_plan.md interpretation 1).
"""

from __future__ import annotations

from atsc.core.models import CheckName, ParseabilityCheck, ParseabilityReport, Platform, Severity
from atsc.core.models import FileFormat as FileFormat
from atsc.core.parsing.dates import find_date_range
from atsc.core.parsing.sections import Section, SectionKind

_H, _M, _L = Severity.HIGH, Severity.MEDIUM, Severity.LOW
# Rows: resume_parsing_spec.md §3 "Platform sensitivity" column.
SEVERITY: dict[CheckName, dict[Platform, Severity]] = {
    CheckName.MULTI_COLUMN_LAYOUT: {
        Platform.WORKDAY: _H,
        Platform.GREENHOUSE: _M,
        Platform.LEVER: _M,
        Platform.ASHBY: _M,
    },
    CheckName.TABLE_DETECTED: {
        Platform.WORKDAY: _H,
        Platform.GREENHOUSE: _L,
        Platform.LEVER: _L,
        Platform.ASHBY: _L,
    },
    CheckName.TEXT_BOX_DETECTED: {
        Platform.WORKDAY: _H,
        Platform.GREENHOUSE: _H,
        Platform.LEVER: _H,
        Platform.ASHBY: _H,
    },
    CheckName.NON_STANDARD_FONT: {
        Platform.WORKDAY: _H,
        Platform.GREENHOUSE: _M,
        Platform.LEVER: _M,
        Platform.ASHBY: _M,
    },
    CheckName.IMAGE_BASED_PDF: {
        Platform.WORKDAY: _H,
        Platform.GREENHOUSE: _H,
        Platform.LEVER: _H,
        Platform.ASHBY: _H,
    },
    CheckName.INCONSISTENT_DATES: {
        Platform.WORKDAY: _M,
        Platform.GREENHOUSE: _M,
        Platform.LEVER: _M,
        Platform.ASHBY: _M,
    },
    CheckName.NON_STANDARD_SECTION_HEADERS: {
        Platform.WORKDAY: _M,
        Platform.GREENHOUSE: _M,
        Platform.LEVER: _M,
        Platform.ASHBY: _M,
    },
    CheckName.HEADER_FOOTER_CONTENT: {
        Platform.WORKDAY: _H,
        Platform.GREENHOUSE: _M,
        Platform.LEVER: _M,
        Platform.ASHBY: _M,
    },
}
CHECK_ORDER = tuple(SEVERITY)
LAYOUT_CHECKS = (
    CheckName.MULTI_COLUMN_LAYOUT,
    CheckName.TABLE_DETECTED,
    CheckName.TEXT_BOX_DETECTED,
    CheckName.NON_STANDARD_FONT,
    CheckName.IMAGE_BASED_PDF,
    CheckName.HEADER_FOOTER_CONTENT,
)
_FAMILY_EXAMPLE = {
    "text": "month name and year",
    "numeric": "numeric month/year",
    "year": "year only",
}


def make_check(name: CheckName, status: str, location: str = "") -> ParseabilityCheck:
    return ParseabilityCheck(
        check_name=name,
        status=status,  # type: ignore[arg-type]
        location=location,
        platform_severity=dict(SEVERITY[name]),
    )


def check_inconsistent_dates(sections: list[Section]) -> ParseabilityCheck:
    """Evaluated over work-experience date ranges only (build_plan.md Phase 4 note)."""
    exp = [s for s in sections if s.kind == SectionKind.EXPERIENCE] or [
        s for s in sections if s.kind == SectionKind.UNKNOWN
    ]
    families: dict[str, str] = {}
    for section in exp:
        for line in section.lines:
            rng = find_date_range(line)
            if rng and rng.family not in families:
                families[rng.family] = line[rng.span[0] : rng.span[1]]
    if len(families) <= 1:
        return make_check(CheckName.INCONSISTENT_DATES, "pass")
    detail = "; ".join(f"{_FAMILY_EXAMPLE[f]} ({ex})" for f, ex in families.items())
    return make_check(CheckName.INCONSISTENT_DATES, "fail", f"Experience section mixes {detail}")


def check_section_headers(sections: list[Section]) -> ParseabilityCheck:
    unknown = [s.header for s in sections if s.kind == SectionKind.UNKNOWN and s.header]
    if not unknown:
        return make_check(CheckName.NON_STANDARD_SECTION_HEADERS, "pass")
    return make_check(
        CheckName.NON_STANDARD_SECTION_HEADERS,
        "fail",
        "Unrecognised section headers: " + ", ".join(unknown),
    )


def build_report(
    file_format: FileFormat,
    sections: list[Section],
    layout_checks: dict[CheckName, ParseabilityCheck] | None = None,
) -> ParseabilityReport:
    layout_checks = layout_checks or {}
    checks: list[ParseabilityCheck] = []
    for name in CHECK_ORDER:
        if name == CheckName.INCONSISTENT_DATES:
            checks.append(check_inconsistent_dates(sections))
        elif name == CheckName.NON_STANDARD_SECTION_HEADERS:
            checks.append(check_section_headers(sections))
        elif name in layout_checks:
            checks.append(layout_checks[name])
        else:
            checks.append(make_check(name, "not_assessed"))
    return ParseabilityReport(file_format=file_format, checks=checks)
