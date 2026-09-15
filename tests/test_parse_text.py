"""Pasted-text resume parsing (resume_parsing_spec.md §2 steps 3-6; §3 text-level checks)."""

from pathlib import Path

import pytest

from atsc.core.models import CheckName, ParseabilityReport, ParsedResume
from atsc.core.parsing import parse_resume_text

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def clean() -> tuple[ParsedResume, ParseabilityReport]:
    return parse_resume_text((FIXTURES / "resume_clean.txt").read_text())


@pytest.fixture(scope="module")
def creative() -> tuple[ParsedResume, ParseabilityReport]:
    return parse_resume_text((FIXTURES / "resume_creative_headers.txt").read_text())


@pytest.fixture(scope="module")
def mixed() -> tuple[ParsedResume, ParseabilityReport]:
    return parse_resume_text((FIXTURES / "resume_mixed_dates.txt").read_text())


# -- basics --------------------------------------------------------------------


def test_basics_from_header_block(clean: tuple[ParsedResume, ParseabilityReport]) -> None:
    b = clean[0].basics
    assert b.name == "Priya Natarajan"
    assert b.email == "priya.natarajan@example.com"
    assert b.phone == "(512) 555-0143"
    assert b.location == "Austin, TX"


def test_basics_with_pipe_separated_header(
    creative: tuple[ParsedResume, ParseabilityReport],
) -> None:
    b = creative[0].basics
    assert b.name == "Jordan Lee"
    assert b.phone == "415-555-0199"
    assert b.location == "San Francisco, CA"


# -- work ------------------------------------------------------------------------


def test_work_entries_split_by_date_headed_blocks(
    clean: tuple[ParsedResume, ParseabilityReport],
) -> None:
    work = clean[0].work
    assert [w.company for w in work] == ["Acme Robotics", "Northwind Analytics"]
    assert [w.position for w in work] == [
        "Senior Machine Learning Engineer",
        "Machine Learning Engineer",
    ]
    assert (work[0].start_date, work[0].end_date) == ("2021-03", "present")
    assert (work[1].start_date, work[1].end_date) == ("2018-06", "2021-02")


def test_bullets_are_captured_per_entry_with_glyphs_stripped(
    clean: tuple[ParsedResume, ParseabilityReport],
) -> None:
    work = clean[0].work
    assert len(work[0].bullets) == 4 and len(work[1].bullets) == 3
    assert work[0].bullets[0].raw_text.startswith("Fine-tuned Llama-3-8B with LoRA")


def test_bullets_carry_taxonomy_clusters(clean: tuple[ParsedResume, ParseabilityReport]) -> None:
    first = clean[0].work[0].bullets[0]
    assert "peft" in first.matched_clusters
    second = clean[0].work[0].bullets[1]
    assert {"rag", "vector_databases", "rag_orchestration"} <= set(second.matched_clusters)


def test_work_dates_normalise_numeric_and_long_month_formats(
    mixed: tuple[ParsedResume, ParseabilityReport],
) -> None:
    work = mixed[0].work
    assert [(w.start_date, w.end_date) for w in work] == [
        ("2023", "present"),
        ("2020-03", "2022-12"),
        ("2018-06", "2020-02"),
    ]


# -- education / skills / projects ------------------------------------------------


def test_education_entries(clean: tuple[ParsedResume, ParseabilityReport]) -> None:
    edu = clean[0].education
    assert len(edu) == 2
    assert edu[0].degree is not None and edu[0].degree.startswith("M.S.")
    assert edu[0].institution == "University of Texas at Austin"
    assert edu[0].dates == "2018"


def test_skills_split_on_delimiters_and_category_prefixes(
    clean: tuple[ParsedResume, ParseabilityReport],
) -> None:
    raw = [s.raw_text for s in clean[0].skills]
    assert "Python" in raw and "PyTorch" in raw and "AWS SageMaker" in raw
    assert "Languages" not in raw and "ML" not in raw  # category labels are not skills
    by_text = {s.raw_text: s.matched_clusters for s in clean[0].skills}
    assert by_text["PyTorch"] == ["dl_frameworks"]
    assert set(by_text["Airflow"]) == {"orchestration", "data_eng_tooling"}
    assert by_text["Go"] == []


def test_projects_are_captured(clean: tuple[ParsedResume, ParseabilityReport]) -> None:
    projects = clean[0].projects
    assert len(projects) == 1
    assert projects[0].name is not None and projects[0].name.startswith("Open-source reranker")
    assert len(projects[0].bullets) == 1


def test_fuzzy_section_labels_resolve_to_standard_sections(
    mixed: tuple[ParsedResume, ParseabilityReport],
) -> None:
    assert [s.raw_text for s in mixed[0].skills][:2] == ["SQL", "Python"]  # "Technical Skills"
    assert len(mixed[0].work) == 3  # "Experience" in title case
    assert len(mixed[0].education) == 1


# -- text-level parseability checks -----------------------------------------------


def _check(report: ParseabilityReport, name: CheckName):
    return next(c for c in report.checks if c.check_name == name)


def test_pasted_text_marks_layout_checks_as_not_assessed(
    clean: tuple[ParsedResume, ParseabilityReport],
) -> None:
    report = clean[1]
    assert report.file_format == "pasted_text"
    for name in (
        CheckName.MULTI_COLUMN_LAYOUT,
        CheckName.TABLE_DETECTED,
        CheckName.TEXT_BOX_DETECTED,
        CheckName.NON_STANDARD_FONT,
        CheckName.IMAGE_BASED_PDF,
        CheckName.HEADER_FOOTER_CONTENT,
    ):
        assert _check(report, name).status == "not_assessed", name


def test_consistent_dates_pass(clean: tuple[ParsedResume, ParseabilityReport]) -> None:
    assert _check(clean[1], CheckName.INCONSISTENT_DATES).status == "pass"


def test_mixed_date_styles_fail_with_location(
    mixed: tuple[ParsedResume, ParseabilityReport],
) -> None:
    c = _check(mixed[1], CheckName.INCONSISTENT_DATES)
    assert c.status == "fail"
    assert "Experience" in c.location


def test_standard_headers_pass(clean: tuple[ParsedResume, ParseabilityReport]) -> None:
    assert _check(clean[1], CheckName.NON_STANDARD_SECTION_HEADERS).status == "pass"


def test_creative_headers_fail_and_are_named(
    creative: tuple[ParsedResume, ParseabilityReport],
) -> None:
    c = _check(creative[1], CheckName.NON_STANDARD_SECTION_HEADERS)
    assert c.status == "fail"
    assert "MY JOURNEY" in c.location and "TOOLBOX" in c.location


def test_creative_headers_still_yield_content_via_structure(
    creative: tuple[ParsedResume, ParseabilityReport],
) -> None:
    # Even with unrecognised headers, date-headed blocks should still be found as work.
    assert len(creative[0].work) == 1
    assert creative[0].work[0].company == "Fabrikam"


def test_raw_text_is_normalised(clean: tuple[ParsedResume, ParseabilityReport]) -> None:
    text = clean[0].raw_text
    assert "\r" not in text and "\t" not in text
    assert "  " not in text.replace("\n\n", "")
