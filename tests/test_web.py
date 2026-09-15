"""Web layer (Phase 7): two-box flow, selectors, landing pages, honesty copy."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atsc.core.models import DISCLAIMER
from atsc.web.app import create_app

FIXTURES = Path(__file__).parent / "fixtures"
RESUME = (FIXTURES / "resume_clean.txt").read_text()
JD = (FIXTURES / "jd_mle_llm.txt").read_text()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(warm=False))


def _score(client: TestClient, **overrides: object) -> str:
    data: dict[str, object] = {
        "resume_text": RESUME,
        "jd_text": JD,
        "platform": "generic",
        "role_track": "auto",
    }
    data.update(overrides)
    resp = client.post("/score", data=data)
    assert resp.status_code == 200, resp.text[:500]
    return resp.text


# -- landing / form ------------------------------------------------------------------


def test_home_renders_two_box_form(client: TestClient) -> None:
    html = client.get("/").text
    assert 'name="resume_text"' in html
    assert 'name="resume_file"' in html
    assert 'name="jd_text"' in html
    assert 'name="platform"' in html and 'value="workday"' in html
    assert 'name="role_track"' in html and 'value="applied_scientist"' in html
    assert 'hx-post="/score"' in html


def test_static_assets_are_served(client: TestClient) -> None:
    assert client.get("/static/site.css").status_code == 200
    assert client.get("/static/htmx.min.js").status_code == 200


# -- scoring flow ------------------------------------------------------------------


def test_score_pasted_text_full_page(client: TestClient) -> None:
    html = _score(client)
    assert "<html" in html
    assert 'class="score-number"' in html
    assert DISCLAIMER in html
    assert "Retrieval-augmented generation" in html  # matched skill canonical name
    assert "not assessed" in html  # pasted text leaves layout checks unassessed


def test_score_htmx_request_returns_fragment(client: TestClient) -> None:
    resp = client.post(
        "/score",
        data={"resume_text": RESUME, "jd_text": JD, "platform": "generic", "role_track": "auto"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "<html" not in resp.text
    assert 'class="score-number"' in resp.text


def test_score_with_pdf_upload(client: TestClient) -> None:
    pdf = (FIXTURES / "resume_two_column.pdf").read_bytes()
    resp = client.post(
        "/score",
        data={"jd_text": JD, "platform": "workday", "role_track": "mle"},
        files={"resume_file": ("resume.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    assert 'class="score-number"' in resp.text
    assert "Multi-column layout" in resp.text  # failed check is listed by name


def test_score_shows_selected_role_and_platform(client: TestClient) -> None:
    html = _score(client, platform="lever", role_track="data_engineer")
    assert "Lever" in html
    assert "Data Engineer" in html


def test_score_lists_unmatched_required_and_requirement_lines(client: TestClient) -> None:
    html = _score(client)
    assert "LLM APIs" in html or "llm_apis" in html  # unmatched required cluster name
    assert "Strong proficiency in Python and PyTorch." in html  # JD requirement line quoted


# -- validation ----------------------------------------------------------------------


def test_missing_resume_is_explained(client: TestClient) -> None:
    resp = client.post(
        "/score",
        data={"resume_text": "", "jd_text": JD, "platform": "generic", "role_track": "auto"},
    )
    assert resp.status_code == 422
    assert "resume" in resp.text.lower()
    assert 'class="score-number"' not in resp.text


def test_missing_jd_is_explained(client: TestClient) -> None:
    resp = client.post(
        "/score",
        data={"resume_text": RESUME, "jd_text": " ", "platform": "generic", "role_track": "auto"},
    )
    assert resp.status_code == 422
    assert "job description" in resp.text.lower()


def test_unsupported_file_is_declined_in_plain_language(client: TestClient) -> None:
    resp = client.post(
        "/score",
        data={"jd_text": JD, "platform": "generic", "role_track": "auto"},
        files={"resume_file": ("resume.pages", b"not really", "application/octet-stream")},
    )
    assert resp.status_code == 422
    assert ".pages" in resp.text
    assert "not supported" in resp.text


def test_oversized_upload_is_rejected(client: TestClient) -> None:
    resp = client.post(
        "/score",
        data={"jd_text": JD, "platform": "generic", "role_track": "auto"},
        files={"resume_file": ("big.pdf", b"%PDF-" + b"0" * 3_000_000, "application/pdf")},
    )
    assert resp.status_code == 413
    assert "2 MB" in resp.text


def test_htmx_validation_error_is_a_fragment(client: TestClient) -> None:
    resp = client.post(
        "/score",
        data={"resume_text": "", "jd_text": JD, "platform": "generic", "role_track": "auto"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 422
    assert "<html" not in resp.text


# -- landing pages -----------------------------------------------------------------


def test_role_landing_pages(client: TestClient) -> None:
    html = client.get("/roles/mle").text
    assert "ML Engineer" in html
    assert 'value="mle" selected' in html
    assert client.get("/roles/nope").status_code == 404


def test_platform_landing_pages(client: TestClient) -> None:
    html = client.get("/ats/workday").text
    assert "Workday" in html
    assert 'value="workday" selected' in html
    assert "Multi-column layout" in html
    assert client.get("/ats/taleo").status_code == 404


def test_how_it_works_states_weights_and_disclaimer(client: TestClient) -> None:
    html = client.get("/how-it-works").text
    assert "45" in html and "35" in html and "20" in html
    assert DISCLAIMER in html
    assert "starting hypothesis" in html


# -- honesty (ats_scoring_spec.md §6) -------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/how-it-works", "/roles/mle", "/ats/workday"])
def test_pages_never_claim_interview_odds(client: TestClient, path: str) -> None:
    html = client.get(path).text
    stripped = html.replace(DISCLAIMER, "")
    for word in ("interview", "hired", "callback", "odds", "chances"):
        assert word not in stripped.lower(), f"{path} mentions '{word}' outside the disclaimer"


def test_result_page_never_claims_interview_odds(client: TestClient) -> None:
    html = _score(client).replace(DISCLAIMER, "")
    for word in ("interview", "hired", "callback", "odds", "chances"):
        assert word not in html.lower()


# -- presentation details -----------------------------------------------------------


def test_clip_filter_shortens_long_evidence() -> None:
    from atsc.web.routes import clip

    long = "word " * 100
    out = clip(long, 160)
    assert len(out) <= 161 and out.endswith("…")
    assert clip("short line", 160) == "short line"
    assert not out.endswith(" …")  # no dangling space before the ellipsis


def test_scrambled_pdf_evidence_is_clipped(client: TestClient) -> None:
    pdf = (FIXTURES / "resume_two_column.pdf").read_bytes()
    resp = client.post(
        "/score",
        data={"jd_text": JD, "platform": "workday", "role_track": "auto"},
        files={"resume_file": ("resume.pdf", pdf, "application/pdf")},
    )
    quotes = [q for q in resp.text.split("<q>")[1:]]
    assert all(len(q.split("</q>")[0]) <= 200 for q in quotes)


def test_role_track_default_option_is_short(client: TestClient) -> None:
    assert 'value="auto" selected>Detect from the posting<' in client.get("/").text


def test_zero_missing_required_heading_is_not_red(client: TestClient) -> None:
    html = _score(client, resume_text=RESUME + "\nLLM: OpenAI API, function calling\n")
    if 'Required skills your resume does not name <span class="count">0' in html:
        assert '<h2 class="missing">Required skills' not in html
