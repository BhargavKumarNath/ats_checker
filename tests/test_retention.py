"""Phase 12: retention job deletes finished report jobs (and abandoned checkouts) by age."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from atsc.core.jd import parse_job_description
from atsc.core.parsing import parse_resume_text
from atsc.core.scoring import score
from atsc.deep.db import JobStore, ReportJob, make_engine
from atsc.deep.handoff import JobInputs
from atsc.deep.retention import main, purge

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def inputs() -> JobInputs:
    resume, report = parse_resume_text((FIXTURES / "resume_clean.txt").read_text())
    jd = parse_job_description((FIXTURES / "jd_mle_llm.txt").read_text())
    return JobInputs(resume=resume, report=report, jd=jd, result=score(resume, report, jd))


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path}/t.db"


def _seed(store: JobStore, inputs: JobInputs, status: str, age_days: int) -> str:
    job = store.create(inputs)
    with Session(store.engine) as s:
        row = s.get(ReportJob, job.id)
        assert row is not None
        row.status = status
        row.updated_at = NOW - timedelta(days=age_days)
        s.commit()
    return job.id


def _statuses(store: JobStore) -> dict[str, str]:
    with Session(store.engine) as s:
        return {j.id: j.status for j in s.scalars(select(ReportJob))}


def test_purge_deletes_only_old_finished_jobs(db_url: str, inputs: JobInputs) -> None:
    store = JobStore(make_engine(db_url))
    old_done = _seed(store, inputs, "done", 31)
    old_failed = _seed(store, inputs, "failed", 45)
    fresh_done = _seed(store, inputs, "done", 29)
    old_running = _seed(store, inputs, "running", 40)
    old_queued = _seed(store, inputs, "queued", 40)

    removed = purge(store, now=NOW, finished_days=30, abandoned_days=None)

    assert removed == {"finished": 2, "abandoned": 0}
    remaining = _statuses(store)
    assert old_done not in remaining and old_failed not in remaining
    assert {fresh_done, old_running, old_queued} <= set(remaining)


def test_purge_deletes_abandoned_checkouts_separately(db_url: str, inputs: JobInputs) -> None:
    store = JobStore(make_engine(db_url))
    stale_unpaid = _seed(store, inputs, "awaiting_payment", 8)
    recent_unpaid = _seed(store, inputs, "awaiting_payment", 1)

    assert purge(store, now=NOW, finished_days=30, abandoned_days=7) == {
        "finished": 0,
        "abandoned": 1,
    }
    remaining = _statuses(store)
    assert stale_unpaid not in remaining
    assert recent_unpaid in remaining


def test_purge_is_idempotent(db_url: str, inputs: JobInputs) -> None:
    store = JobStore(make_engine(db_url))
    _seed(store, inputs, "done", 60)
    assert purge(store, now=NOW)["finished"] == 1
    assert purge(store, now=NOW)["finished"] == 0


def test_cli_dry_run_counts_without_deleting(
    db_url: str, inputs: JobInputs, capsys: pytest.CaptureFixture[str]
) -> None:
    store = JobStore(make_engine(db_url))
    _seed(store, inputs, "done", 400)
    assert main(["--database-url", db_url, "--dry-run"]) == 0
    assert "would delete 1 finished" in capsys.readouterr().out
    assert len(_statuses(store)) == 1


def test_cli_deletes_and_reports(
    db_url: str, inputs: JobInputs, capsys: pytest.CaptureFixture[str]
) -> None:
    store = JobStore(make_engine(db_url))
    _seed(store, inputs, "done", 400)
    _seed(store, inputs, "awaiting_payment", 400)
    assert main(["--database-url", db_url, "--finished-days", "30", "--abandoned-days", "7"]) == 0
    out = capsys.readouterr().out
    assert "deleted 1 finished" in out and "1 abandoned" in out
    assert _statuses(store) == {}
