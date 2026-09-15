"""ParsedResume and ParseabilityReport shapes (data_model.md §1, §2)."""

import pytest
from pydantic import ValidationError

from atsc.core.models import (
    Bullet,
    CheckName,
    ParseabilityCheck,
    ParseabilityReport,
    ParsedResume,
    Platform,
    Severity,
    SkillEntry,
    WorkEntry,
)


def test_bullet_embedding_is_excluded_from_serialisation() -> None:
    # build_plan.md interpretation 6: vectors never leave the process.
    b = Bullet(raw_text="Shipped a thing", matched_clusters=["rag"])
    b.embedding = [0.1, 0.2]
    assert "embedding" not in b.model_dump()
    assert b.model_dump()["matched_clusters"] == ["rag"]


def test_work_entry_requires_bullets_list_but_allows_missing_dates() -> None:
    w = WorkEntry(company="Acme", position="MLE", bullets=[])
    assert w.start_date is None and w.end_date is None


def test_skill_entry_can_map_to_several_clusters() -> None:
    s = SkillEntry(raw_text="Airflow", matched_clusters=["orchestration", "data_eng_tooling"])
    assert len(s.matched_clusters) == 2


def test_parsed_resume_defaults_to_empty_sections() -> None:
    r = ParsedResume()
    assert r.work == [] and r.education == [] and r.skills == [] and r.projects == []
    assert r.basics.name is None


def test_parseability_check_needs_a_severity_for_every_platform() -> None:
    with pytest.raises(ValidationError):
        ParseabilityCheck(
            check_name=CheckName.TABLE_DETECTED,
            status="fail",
            location="Skills section",
            platform_severity={Platform.WORKDAY: Severity.HIGH},
        )


def test_parseability_report_lists_failed_checks() -> None:
    sev = dict.fromkeys(Platform, Severity.MEDIUM)
    report = ParseabilityReport(
        file_format="pdf",
        checks=[
            ParseabilityCheck(
                check_name=CheckName.TABLE_DETECTED,
                status="fail",
                location="p1",
                platform_severity=sev,
            ),
            ParseabilityCheck(
                check_name=CheckName.MULTI_COLUMN_LAYOUT,
                status="pass",
                location="",
                platform_severity=sev,
            ),
            ParseabilityCheck(
                check_name=CheckName.TEXT_BOX_DETECTED,
                status="not_assessed",
                location="",
                platform_severity=sev,
            ),
        ],
    )
    assert [c.check_name for c in report.failed] == [CheckName.TABLE_DETECTED]
    assert [c.check_name for c in report.assessed] == [
        CheckName.TABLE_DETECTED,
        CheckName.MULTI_COLUMN_LAYOUT,
    ]
