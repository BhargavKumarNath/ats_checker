"""Plain-language labels and view models for Layer 1 output. No scoring logic here."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from atsc.core.models import (
    Category,
    CheckName,
    ParseabilityReport,
    Platform,
    RoleTrack,
    Severity,
)
from atsc.core.parsing.checks import CHECK_ORDER, SEVERITY
from atsc.core.taxonomy import Taxonomy

ROLE_LABELS: dict[RoleTrack, str] = {
    RoleTrack.MLE: "ML Engineer",
    RoleTrack.APPLIED_SCIENTIST: "Applied Scientist",
    RoleTrack.DATA_SCIENTIST: "Data Scientist",
    RoleTrack.ML_RESEARCH: "ML Research",
    RoleTrack.DATA_ENGINEER: "Data Engineer",
}

PLATFORM_LABELS: dict[Platform, str] = {
    Platform.WORKDAY: "Workday",
    Platform.GREENHOUSE: "Greenhouse",
    Platform.LEVER: "Lever",
    Platform.ASHBY: "Ashby",
}
GENERIC_LABEL = "Any platform"

PLATFORM_NOTES: dict[Platform, str] = {
    Platform.WORKDAY: (
        "The strictest parser of the four. Tables and multi-column layouts fail here in the "
        "large majority of independent parser audits, and contact details in a page header "
        "are usually dropped."
    ),
    Platform.GREENHOUSE: (
        "More forgiving of simple tables than Workday, but genuine multi-column layouts still "
        "come out with the columns interleaved."
    ),
    Platform.LEVER: (
        "Similar to Greenhouse: tolerant of simple tables, misreads real column layouts, and "
        "skips text boxes like everyone else."
    ),
    Platform.ASHBY: (
        "A newer parser with behaviour close to Greenhouse and Lever on the checks below."
    ),
}

# Check name → (label, what goes wrong). Sentence case, no jargon, one job per line.
CHECK_LABELS: dict[CheckName, tuple[str, str]] = {
    CheckName.MULTI_COLUMN_LAYOUT: (
        "Multi-column layout",
        "Parsers read one line at a time across the page, so two columns come out interleaved.",
    ),
    CheckName.TABLE_DETECTED: (
        "Table",
        "A grid is read cell by cell in an order the parser chooses, not the one you see.",
    ),
    CheckName.TEXT_BOX_DETECTED: (
        "Text box",
        "Content in a floating box is often skipped entirely rather than misordered.",
    ),
    CheckName.NON_STANDARD_FONT: (
        "Unreadable font",
        "Icon and symbol fonts carry no extractable text, so that content is invisible.",
    ),
    CheckName.IMAGE_BASED_PDF: (
        "Image-only PDF",
        "There is no text layer to read. Nothing on the page reaches the parser.",
    ),
    CheckName.INCONSISTENT_DATES: (
        "Mixed date formats",
        "Tenure is computed from your dates; mixing styles can miscount or drop a role.",
    ),
    CheckName.NON_STANDARD_SECTION_HEADERS: (
        "Unusual section headers",
        "Sections are found by their labels. A creative label may not be recognised at all.",
    ),
    CheckName.HEADER_FOOTER_CONTENT: (
        "Contact details in the page header or footer",
        "Page headers and footers are frequently stripped before parsing.",
    ),
}

SEVERITY_LABELS: dict[Severity, str] = {
    Severity.HIGH: "high",
    Severity.MEDIUM: "medium",
    Severity.LOW: "low",
    Severity.NA: "none",
}

STATUS_LABELS = {"pass": "pass", "fail": "fail", "not_assessed": "not assessed"}


@dataclass
class CheckView:
    label: str
    explanation: str
    status: str
    status_label: str
    severity: Severity
    severity_label: str
    location: str


def platform_severity(
    check_severity: dict[Platform, Severity], platform: Platform | None
) -> Severity:
    if platform is not None:
        return check_severity[platform]
    order = [Severity.NA, Severity.LOW, Severity.MEDIUM, Severity.HIGH]
    return max(check_severity.values(), key=order.index)


def checks_view(report: ParseabilityReport, platform: Platform | None) -> list[CheckView]:
    by_name = {c.check_name: c for c in report.checks}
    out: list[CheckView] = []
    for name in CHECK_ORDER:
        check = by_name[name]
        label, explanation = CHECK_LABELS[name]
        sev = platform_severity(check.platform_severity, platform)
        out.append(
            CheckView(
                label=label,
                explanation=explanation,
                status=check.status,
                status_label=STATUS_LABELS[check.status],
                severity=sev,
                severity_label=SEVERITY_LABELS[sev],
                location=check.location,
            )
        )
    return out


def platform_check_table(platform: Platform) -> list[tuple[str, str, str]]:
    """(label, explanation, severity label) for every check on one platform."""
    return [
        (CHECK_LABELS[name][0], CHECK_LABELS[name][1], SEVERITY_LABELS[SEVERITY[name][platform]])
        for name in CHECK_ORDER
    ]


def weight_word(w: float) -> str:
    if w >= 0.9:
        return "high"
    if w >= 0.5:
        return "medium"
    return "low"


def role_category_weights(taxonomy: Taxonomy, track: RoleTrack) -> list[tuple[str, str]]:
    """(category, typical weight word) for one track, from the clusters' actual weights."""
    out: list[tuple[str, str]] = []
    for category in Category:
        ws = [c.role_track_weight[track] for c in taxonomy.clusters if c.category is category]
        if ws:
            out.append((category.value, weight_word(median(ws))))
    return out
