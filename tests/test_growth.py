"""Taxonomy growth loop (gap_analysis_spec.md §4): count unmatched terms, in aggregate, opt-in."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atsc.core.models import (
    ParsedJobDescription,
    ParsedResume,
    Requirement,
    SkillEntry,
)
from atsc.free.growth import GrowthLog, candidate_terms

FIXTURES = Path(__file__).parent / "fixtures"


def _resume(skills: list[tuple[str, list[str]]]) -> ParsedResume:
    return ParsedResume(skills=[SkillEntry(raw_text=t, matched_clusters=c) for t, c in skills])


def _jd(reqs: list[tuple[str, list[str]]]) -> ParsedJobDescription:
    return ParsedJobDescription(
        requirements=[
            Requirement(raw_text=t, requirement_type="required", matched_clusters=c)
            for t, c in reqs
        ]
    )


def test_candidate_terms_take_unmatched_skill_phrases_only() -> None:
    resume = _resume([("Snowflake", []), ("PyTorch", ["dl_frameworks"]), ("Go", [])])
    terms = candidate_terms(resume, _jd([]))
    assert "snowflake" in terms and "go" in terms
    assert "pytorch" not in terms


def test_candidate_terms_split_unmatched_requirement_lists() -> None:
    jd = _jd(
        [
            ("Experience with Snowflake, dbt, or Fivetran.", []),
            ("Strong proficiency in Python and PyTorch.", ["python_data_stack"]),
        ]
    )
    terms = candidate_terms(_resume([]), jd)
    assert {"snowflake", "dbt", "fivetran"} <= set(terms)
    assert not any("experience" in t for t in terms)
    assert not any("python" in t for t in terms)


def test_candidate_terms_drop_personal_and_noisy_fragments() -> None:
    resume = _resume(
        [
            ("priya@example.com", []),
            ("(512) 555-0143", []),
            ("a very long phrase that could only come from one person's resume text", []),
            ("2019", []),
        ]
    )
    assert candidate_terms(resume, _jd([])) == []


def test_growth_log_counts_in_aggregate(tmp_path: Path) -> None:
    log = GrowthLog(tmp_path / "growth.db")
    log.record(["Snowflake", "dbt"])
    log.record(["snowflake"])
    top = log.top(10)
    assert top[0] == ("snowflake", 2)
    assert ("dbt", 1) in top


def test_growth_log_disabled_when_path_empty() -> None:
    log = GrowthLog(None)
    log.record(["anything"])
    assert log.top(5) == []


# -- wiring -----------------------------------------------------------------------------


def test_free_check_records_only_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atsc.web.app import create_app

    resume = (FIXTURES / "resume_clean.txt").read_text()
    resume = resume.replace("Infra: Docker", "Other: Airbyte, Fivetran\nInfra: Docker")
    jd = (FIXTURES / "jd_mle_llm.txt").read_text()
    data = {"resume_text": resume, "jd_text": jd, "platform": "generic", "role_track": "auto"}

    off = TestClient(create_app(warm=False))
    assert off.post("/score", data=data).status_code == 200
    assert "counted in aggregate" not in off.get("/").text
    assert not (tmp_path / "growth.db").exists()

    monkeypatch.setenv("ATSC_GROWTH_LOG_PATH", str(tmp_path / "growth.db"))
    on = TestClient(create_app(warm=False))
    assert on.post("/score", data=data).status_code == 200
    assert "counted in aggregate" in on.get("/").text
    terms = dict(GrowthLog(tmp_path / "growth.db").top(50))
    assert terms.get("airbyte") == 1 and terms.get("fivetran") == 1
