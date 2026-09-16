"""Phase 12: per-IP sliding-window rate limit on POST /score, as ASGI middleware."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atsc.web.app import create_app
from atsc.web.ratelimit import SlidingWindowLimiter

FIXTURES = Path(__file__).parent / "fixtures"
RESUME = (FIXTURES / "resume_clean.txt").read_text()
JD = (FIXTURES / "jd_mle_llm.txt").read_text()
FORM = {"resume_text": RESUME, "jd_text": JD, "platform": "generic", "role_track": "auto"}


# -- limiter ---------------------------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_limiter_allows_up_to_limit_then_blocks() -> None:
    clock = Clock()
    lim = SlidingWindowLimiter(limit=3, window_seconds=60, clock=clock)
    assert [lim.check("a").allowed for _ in range(3)] == [True, True, True]
    verdict = lim.check("a")
    assert verdict.allowed is False
    assert verdict.retry_after == 60


def test_limiter_window_slides() -> None:
    clock = Clock()
    lim = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)
    lim.check("a")
    clock.t += 30
    lim.check("a")
    assert lim.check("a").allowed is False
    clock.t += 31  # first hit is now outside the window
    verdict = lim.check("a")
    assert verdict.allowed is True
    assert lim.check("a").allowed is False


def test_limiter_keys_are_independent_and_idle_keys_are_forgotten() -> None:
    clock = Clock()
    lim = SlidingWindowLimiter(limit=1, window_seconds=10, clock=clock)
    assert lim.check("a").allowed
    assert lim.check("b").allowed
    assert lim.check("a").allowed is False
    clock.t += 11
    assert lim.check("a").allowed
    lim.prune()
    assert lim.tracked_keys == 1  # "b" expired and was dropped; "a" was just hit


def test_limiter_retry_after_is_ceiling_of_remaining_seconds() -> None:
    clock = Clock()
    lim = SlidingWindowLimiter(limit=1, window_seconds=60, clock=clock)
    lim.check("a")
    clock.t += 45.2
    assert lim.check("a").retry_after == 15


# -- middleware ------------------------------------------------------------------------------


@pytest.fixture
def limited_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ATSC_SCORE_RATE_LIMIT", "2")
    monkeypatch.setenv("ATSC_SCORE_RATE_WINDOW_SECONDS", "600")
    return TestClient(create_app(warm=False))


def test_third_score_in_window_is_429_with_retry_after(limited_client: TestClient) -> None:
    assert limited_client.post("/score", data=FORM).status_code == 200
    assert limited_client.post("/score", data=FORM).status_code == 200
    resp = limited_client.post("/score", data=FORM)
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) >= 1
    assert "<html" in resp.text  # full page for a non-htmx request
    assert "Too many checks" in resp.text
    assert "interview" not in resp.text.lower()


def test_htmx_request_gets_fragment_on_429(limited_client: TestClient) -> None:
    for _ in range(2):
        limited_client.post("/score", data=FORM)
    resp = limited_client.post("/score", data=FORM, headers={"HX-Request": "true"})
    assert resp.status_code == 429
    assert "<html" not in resp.text
    assert 'role="alert"' in resp.text


def test_other_routes_are_not_limited(limited_client: TestClient) -> None:
    for _ in range(5):
        assert limited_client.get("/").status_code == 200
        assert limited_client.get("/healthz").status_code == 200
    # A GET to /score is not a submission and is not counted.
    for _ in range(3):
        assert limited_client.get("/score").status_code == 405


def test_client_ip_header_is_ignored_unless_configured(limited_client: TestClient) -> None:
    # Without ATSC_CLIENT_IP_HEADER, a spoofed forwarding header cannot buy a fresh bucket.
    for i in range(2):
        r = limited_client.post("/score", data=FORM, headers={"Fly-Client-IP": f"10.0.0.{i}"})
        assert r.status_code == 200
    r = limited_client.post("/score", data=FORM, headers={"Fly-Client-IP": "10.0.0.9"})
    assert r.status_code == 429


def test_configured_client_ip_header_separates_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATSC_SCORE_RATE_LIMIT", "1")
    monkeypatch.setenv("ATSC_CLIENT_IP_HEADER", "Fly-Client-IP")
    client = TestClient(create_app(warm=False))
    assert client.post("/score", data=FORM, headers={"Fly-Client-IP": "1.1.1.1"}).status_code == 200
    assert client.post("/score", data=FORM, headers={"Fly-Client-IP": "2.2.2.2"}).status_code == 200
    assert client.post("/score", data=FORM, headers={"Fly-Client-IP": "1.1.1.1"}).status_code == 429


def test_limit_zero_disables_the_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATSC_SCORE_RATE_LIMIT", "0")
    client = TestClient(create_app(warm=False))
    for _ in range(3):
        assert client.post("/score", data=FORM).status_code == 200
