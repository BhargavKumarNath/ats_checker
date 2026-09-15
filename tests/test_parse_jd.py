"""Job-description analysis (job_description_analysis.md §3-4, data_model.md §3)."""

from pathlib import Path

import pytest

from atsc.core.jd import parse_job_description
from atsc.core.models import ParsedJobDescription, RoleTrack

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def mle() -> ParsedJobDescription:
    return parse_job_description((FIXTURES / "jd_mle_llm.txt").read_text())


@pytest.fixture(scope="module")
def ds() -> ParsedJobDescription:
    return parse_job_description((FIXTURES / "jd_ds_prose.txt").read_text())


def _texts(jd: ParsedJobDescription, kind: str | None = None) -> list[str]:
    return [r.raw_text for r in jd.requirements if kind is None or r.requirement_type == kind]


# -- stage 1: skill-sentence classification -------------------------------------


def test_boilerplate_is_excluded(mle: ParsedJobDescription) -> None:
    joined = "\n".join(_texts(mle)).lower()
    assert "equal opportunity" not in joined
    assert "401(k)" not in joined
    assert "dental" not in joined
    assert "fastest-growing" not in joined
    assert "authorized to work" not in joined


def test_minimum_qualifications_are_required(mle: ParsedJobDescription) -> None:
    required = _texts(mle, "required")
    assert any(t.startswith("Strong proficiency in Python and PyTorch") for t in required)
    assert any(t.startswith("Experience deploying models with Docker") for t in required)
    assert any(t.startswith("5+ years of professional software") for t in required)


def test_preferred_section_is_preferred(mle: ParsedJobDescription) -> None:
    preferred = _texts(mle, "preferred")
    assert any(t.startswith("Experience with LangChain") for t in preferred)
    assert any(t.startswith("Contributions to open-source") for t in preferred)


def test_inline_qualifier_marks_preferred(ds: ParsedJobDescription) -> None:
    preferred = _texts(ds, "preferred")
    assert any("causal inference" in t for t in preferred)
    assert any("dbt and Airflow" in t for t in preferred)


def test_responsibility_with_concrete_skill_is_kept(mle: ParsedJobDescription) -> None:
    required = _texts(mle, "required")
    assert any("retrieval-augmented generation" in t for t in required)
    assert any("vLLM, Triton" in t for t in required)


def test_responsibility_without_skill_is_dropped(mle: ParsedJobDescription) -> None:
    joined = "\n".join(_texts(mle))
    assert "Partner with product managers" not in joined
    assert "Mentor junior engineers" not in joined


def test_prose_sentences_are_split_into_requirements(ds: ParsedJobDescription) -> None:
    required = _texts(ds, "required")
    assert any(t.startswith("You are fluent in SQL and Python") for t in required)
    assert any(t.startswith("You have 2-4 years of experience") for t in required)
    assert all("\n" not in t for t in required)


def test_section_headers_are_not_requirements(mle: ParsedJobDescription) -> None:
    texts = _texts(mle)
    assert "Minimum qualifications" not in texts
    assert "Preferred qualifications" not in texts
    assert "What you'll do" not in texts


# -- stage 2: taxonomy matching -------------------------------------------------


def test_requirements_carry_matched_clusters(mle: ParsedJobDescription) -> None:
    by_text = {r.raw_text: r for r in mle.requirements}
    rag_line = next(t for t in by_text if "retrieval-augmented generation" in t)
    assert "rag" in by_text[rag_line].matched_clusters
    assert "vector_databases" in by_text[rag_line].matched_clusters
    peft_line = next(t for t in by_text if "LoRA" in t)
    assert "peft" in by_text[peft_line].matched_clusters


def test_embedding_is_never_serialised(mle: ParsedJobDescription) -> None:
    dumped = mle.model_dump()
    assert all("embedding" not in r for r in dumped["requirements"])


# -- role track and seniority ---------------------------------------------------


def test_role_track_mle(mle: ParsedJobDescription) -> None:
    assert mle.role_track_signal == RoleTrack.MLE


def test_role_track_data_scientist(ds: ParsedJobDescription) -> None:
    assert ds.role_track_signal == RoleTrack.DATA_SCIENTIST


def test_role_track_unclear_without_signal() -> None:
    jd = parse_job_description("Software Engineer\n- Experience with Go and gRPC.\n")
    assert jd.role_track_signal == "unclear"


def test_seniority_from_title(mle: ParsedJobDescription) -> None:
    assert mle.seniority_signal == "senior"
    assert mle.years_experience == 5


def test_seniority_from_roman_numeral(ds: ParsedJobDescription) -> None:
    assert ds.seniority_signal == "mid"
    assert ds.years_experience == 2


def test_seniority_unclear_without_signal() -> None:
    jd = parse_job_description("Machine Learning Engineer\n- Experience with PyTorch.\n")
    assert jd.seniority_signal == "unclear"
    assert jd.years_experience is None


def test_empty_text_gives_empty_object() -> None:
    jd = parse_job_description("   \n\n ")
    assert jd.requirements == []
    assert jd.role_track_signal == "unclear"
    assert jd.seniority_signal == "unclear"


def test_title_line_is_not_a_requirement(mle: ParsedJobDescription) -> None:
    assert not any(t.startswith("Senior Machine Learning Engineer") for t in _texts(mle))


def test_role_track_from_title_variants() -> None:
    cases = {
        "Staff Research Scientist, Alignment\n- Publications at NeurIPS.": RoleTrack.ML_RESEARCH,
        "Data Engineer\n- Build data pipelines with Spark and Airflow.": RoleTrack.DATA_ENGINEER,
        "Lead Applied Scientist\n- Applied research on ranking.": RoleTrack.APPLIED_SCIENTIST,
    }
    for text, expected in cases.items():
        assert parse_job_description(text).role_track_signal == expected, text


def test_seniority_from_years_only() -> None:
    assert (
        parse_job_description("Data Scientist\n- 1 year of experience with SQL.").seniority_signal
        == "junior"
    )
    assert (
        parse_job_description("ML Engineer\n- 8+ years of experience.").seniority_signal == "staff"
    )
