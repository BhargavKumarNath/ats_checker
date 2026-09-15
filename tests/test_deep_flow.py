"""Phase 10: checkout → webhook → worker → report page. Stripe and Claude are faked."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from atsc.config import Settings
from atsc.core.jd import parse_job_description
from atsc.core.models import DISCLAIMER
from atsc.core.parsing import parse_resume_text
from atsc.core.scoring import score
from atsc.deep.db import JobStore, make_engine
from atsc.deep.email import RecordingSender
from atsc.deep.handoff import HandoffError, JobInputs, decode_inputs, encode_inputs
from atsc.deep.models import DeepReport, Explanation, RewriteSuggestion
from atsc.deep.worker import run_once

FIXTURES = Path(__file__).parent / "fixtures"
RESUME = (FIXTURES / "resume_clean.txt").read_text()
JD = (FIXTURES / "jd_mle_llm.txt").read_text()


@pytest.fixture(scope="module")
def inputs() -> JobInputs:
    resume, report = parse_resume_text(RESUME)
    jd = parse_job_description(JD)
    return JobInputs(resume=resume, report=report, jd=jd, result=score(resume, report, jd))


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(make_engine(f"sqlite:///{tmp_path}/t.db"))


def _fake_report(inp: JobInputs) -> DeepReport:
    return _fake_report_for(inp.result)


def _fake_report_for(result: Any) -> DeepReport:
    return DeepReport(
        score_result=result,
        explanations=[
            Explanation(
                cluster_id="rag",
                explanation_text="RAG on the resume counted as vector search in the posting.",
                retrieved_context=["Retrieval-augmented generation is also written as: RAG."],
            )
        ],
        rewrite_suggestions=[
            RewriteSuggestion(
                original_bullet="Built a RAG pipeline over 2M internal documents.",
                suggested_rewrite="Built a retrieval-augmented generation pipeline over 2M docs.",
                readability_flag=False,
                grounding_examples=["Built a retrieval-augmented generation pipeline over 2M."],
            )
        ],
        model="fake-model",
    )


class FakeGenerator:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def generate(self, result: Any) -> DeepReport:
        if self.fail:
            raise RuntimeError("boom")
        return _fake_report_for(result)


# -- settings and handoff -------------------------------------------------------------------


def test_payments_disabled_by_default() -> None:
    assert Settings(stripe_secret_key="", stripe_price_id="").payments_enabled is False
    s = Settings(
        stripe_secret_key="sk_test_x", stripe_price_id="price_x", stripe_webhook_secret="w"
    )
    assert s.payments_enabled is True


def test_handoff_round_trip_and_tamper_detection(inputs: JobInputs) -> None:
    token = encode_inputs(inputs)
    assert len(token) < 60_000 and "\n" not in token
    assert decode_inputs(token) == inputs
    with pytest.raises(HandoffError):
        decode_inputs(token[:-8] + "AAAAAAAA")
    with pytest.raises(HandoffError):
        decode_inputs("not-a-token")


# -- job store -------------------------------------------------------------------------------


def test_job_lifecycle(store: JobStore, inputs: JobInputs) -> None:
    job = store.create(inputs)
    assert job.status == "awaiting_payment" and len(job.token) >= 32
    assert store.get_by_token(job.token).id == job.id
    assert store.claim_next() is None  # unpaid jobs are never picked up

    store.mark_paid(job.id, stripe_session_id="cs_1", email="a@example.com")
    assert store.get_by_id(job.id).status == "queued"

    claimed = store.claim_next()
    assert claimed is not None and claimed.id == job.id and claimed.status == "running"
    assert store.claim_next() is None

    store.complete(job.id, _fake_report(inputs))
    done = store.get_by_id(job.id)
    assert done.status == "done" and done.report is not None
    assert done.report.explanations[0].cluster_id == "rag"


def test_job_failure_is_recorded(store: JobStore, inputs: JobInputs) -> None:
    job = store.create(inputs)
    store.mark_paid(job.id, stripe_session_id="cs_2", email=None)
    store.claim_next()
    store.fail(job.id, "boom")
    failed = store.get_by_id(job.id)
    assert failed.status == "failed" and failed.error == "boom"


def test_unknown_token_is_none(store: JobStore) -> None:
    assert store.get_by_token("nope") is None


# -- worker ------------------------------------------------------------------------------------


def test_worker_generates_report_and_emails_link(store: JobStore, inputs: JobInputs) -> None:
    job = store.create(inputs)
    store.mark_paid(job.id, stripe_session_id="cs_3", email="buyer@example.com")
    sender = RecordingSender()
    assert run_once(store, FakeGenerator(), sender, base_url="https://atsc.example") is True
    done = store.get_by_id(job.id)
    assert done.status == "done"
    assert sender.sent and sender.sent[0].to == "buyer@example.com"
    assert f"https://atsc.example/report/{job.token}" in sender.sent[0].body
    assert run_once(store, FakeGenerator(), sender, base_url="x") is False  # queue drained


def test_worker_records_failure_without_crashing(store: JobStore, inputs: JobInputs) -> None:
    job = store.create(inputs)
    store.mark_paid(job.id, stripe_session_id="cs_4", email=None)
    assert run_once(store, FakeGenerator(fail=True), RecordingSender(), base_url="x") is True
    assert store.get_by_id(job.id).status == "failed"


# -- web flow ----------------------------------------------------------------------------------


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ATSC_DATABASE_URL", f"sqlite:///{tmp_path}/web.db")
    monkeypatch.setenv("ATSC_STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("ATSC_STRIPE_PRICE_ID", "price_x")
    monkeypatch.setenv("ATSC_STRIPE_WEBHOOK_SECRET", "whsec_x")
    monkeypatch.setenv("ATSC_PUBLIC_BASE_URL", "https://atsc.example")
    from atsc.web.app import create_app

    return TestClient(create_app(warm=False))


def _score_page(client: TestClient) -> str:
    resp = client.post(
        "/score",
        data={"resume_text": RESUME, "jd_text": JD, "platform": "generic", "role_track": "auto"},
    )
    assert resp.status_code == 200
    return resp.text


def test_result_page_offers_checkout_when_payments_enabled(app_client: TestClient) -> None:
    html = _score_page(app_client)
    assert 'action="/report/checkout"' in html
    assert 'name="payload"' in html


def test_result_page_links_placeholder_when_payments_disabled(tmp_path: Path) -> None:
    from atsc.web.app import create_app

    client = TestClient(create_app(warm=False))
    html = _score_page(client)
    assert 'action="/report/checkout"' not in html
    assert 'href="/report"' in html


def test_checkout_creates_job_and_redirects_to_stripe(
    app_client: TestClient, inputs: JobInputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    import atsc.web.report as report_routes

    calls: list[dict[str, Any]] = []

    def fake_session(settings: Settings, **kw: Any) -> tuple[str, str]:
        calls.append(kw)
        return "https://checkout.stripe.test/s", "cs_test_1"

    monkeypatch.setattr(report_routes, "create_checkout_session", fake_session)
    resp = app_client.post(
        "/report/checkout", data={"payload": encode_inputs(inputs)}, follow_redirects=False
    )
    assert resp.status_code == 303 and resp.headers["location"] == "https://checkout.stripe.test/s"
    assert calls and calls[0]["success_url"].startswith("https://atsc.example/report/")
    job = report_routes.store(app_client.app).get_by_id(calls[0]["job_id"])
    assert job.status == "awaiting_payment" and job.stripe_session_id == "cs_test_1"


def test_checkout_with_bad_payload_is_422(app_client: TestClient) -> None:
    assert app_client.post("/report/checkout", data={"payload": "junk"}).status_code == 422


def test_webhook_marks_job_paid(
    app_client: TestClient, inputs: JobInputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    import atsc.web.report as report_routes

    job = report_routes.store(app_client.app).create(inputs)
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_2",
                "client_reference_id": job.id,
                "customer_details": {"email": "buyer@example.com"},
            }
        },
    }
    monkeypatch.setattr(report_routes, "verify_webhook", lambda s, payload, sig: event)
    resp = app_client.post(
        "/stripe/webhook", content=json.dumps(event), headers={"Stripe-Signature": "t=1,v1=x"}
    )
    assert resp.status_code == 200
    updated = report_routes.store(app_client.app).get_by_id(job.id)
    assert updated.status == "queued" and updated.email == "buyer@example.com"


def test_webhook_rejects_bad_signature(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import atsc.web.report as report_routes

    def bad(settings: Settings, payload: bytes, sig: str) -> Any:
        raise report_routes.WebhookError("bad signature")

    monkeypatch.setattr(report_routes, "verify_webhook", bad)
    resp = app_client.post("/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "x"})
    assert resp.status_code == 400


def test_report_page_states(app_client: TestClient, inputs: JobInputs) -> None:
    import atsc.web.report as report_routes

    st = report_routes.store(app_client.app)
    job = st.create(inputs)
    assert "payment" in app_client.get(f"/report/{job.token}").text.lower()

    st.mark_paid(job.id, stripe_session_id="cs", email=None)
    html = app_client.get(f"/report/{job.token}").text
    assert f'hx-get="/report/{job.token}/status"' in html
    assert "<html" not in app_client.get(f"/report/{job.token}/status").text

    st.claim_next()
    st.complete(job.id, _fake_report(inputs))
    html = app_client.get(f"/report/{job.token}").text
    assert "RAG on the resume counted as vector search" in html
    assert "<h3>Retrieval-augmented generation</h3>" in html  # canonical name, not the id
    assert "Retrieval-augmented generation is also written as" in html  # grounding shown
    assert "Built a retrieval-augmented generation pipeline over 2M docs." in html
    assert DISCLAIMER in html
    assert f'href="/report/{job.token}/diff"' in html
    assert "interview" not in html.replace(DISCLAIMER, "").lower()

    diff = app_client.get(f"/report/{job.token}/diff")
    assert diff.status_code == 200 and diff.headers["content-type"].startswith("text/plain")
    assert diff.text.startswith("--- resume (original)")

    st_failed = st.create(inputs)
    st.mark_paid(st_failed.id, stripe_session_id="cs2", email=None)
    st.claim_next()
    st.fail(st_failed.id, "boom")
    assert "went wrong" in app_client.get(f"/report/{st_failed.token}").text.lower()

    assert app_client.get("/report/unknown-token").status_code == 404
