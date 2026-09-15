"""Layer 2 persistence: report jobs (build_plan.md §3 "Persistence").

Postgres in production, SQLite for local dev and tests, through SQLAlchemy 2.0. The
free layer never touches this module; only the checkout/webhook/report routes and the
worker do.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from atsc.deep.handoff import JobInputs
from atsc.deep.models import DeepReport

JobStatus = Literal["awaiting_payment", "queued", "running", "done", "failed"]


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class ReportJob(Base):
    __tablename__ = "report_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="awaiting_payment")
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    stripe_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    input_json: Mapped[str] = mapped_column(Text)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def inputs(self) -> JobInputs:
        return JobInputs.model_validate_json(self.input_json)

    @property
    def report(self) -> DeepReport | None:
        return DeepReport.model_validate_json(self.report_json) if self.report_json else None


def make_engine(url: str) -> Engine:
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    engine = create_engine(url, future=True, **kwargs)
    Base.metadata.create_all(engine)
    return engine


class JobStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _session(self) -> Session:
        return Session(self._engine, expire_on_commit=False)

    def create(self, inputs: JobInputs) -> ReportJob:
        job = ReportJob(
            id=uuid.uuid4().hex,
            token=secrets.token_urlsafe(32),
            status="awaiting_payment",
            input_json=inputs.model_dump_json(),
        )
        with self._session() as s:
            s.add(job)
            s.commit()
        return job

    def get_by_id(self, job_id: str) -> ReportJob | None:
        with self._session() as s:
            return s.get(ReportJob, job_id)

    def get_by_token(self, token: str) -> ReportJob | None:
        with self._session() as s:
            return s.scalar(select(ReportJob).where(ReportJob.token == token))

    def set_stripe_session(self, job_id: str, stripe_session_id: str) -> None:
        with self._session() as s:
            job = s.get(ReportJob, job_id)
            if job is not None:
                job.stripe_session_id = stripe_session_id
                job.updated_at = _now()
                s.commit()

    def mark_paid(self, job_id: str, *, stripe_session_id: str, email: str | None) -> bool:
        """Idempotent: a replayed webhook never re-queues a job that already moved on."""
        with self._session() as s:
            job = s.get(ReportJob, job_id)
            if job is None or job.status != "awaiting_payment":
                return False
            job.status = "queued"
            job.stripe_session_id = stripe_session_id
            job.email = email
            job.paid_at = _now()
            job.updated_at = _now()
            s.commit()
            return True

    def claim_next(self) -> ReportJob | None:
        """Move the oldest queued job to running and return it; None when the queue is empty."""
        with self._session() as s:
            job = s.scalar(
                select(ReportJob)
                .where(ReportJob.status == "queued")
                .order_by(ReportJob.paid_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.status = "running"
            job.updated_at = _now()
            s.commit()
            return job

    def complete(self, job_id: str, report: DeepReport) -> None:
        with self._session() as s:
            job = s.get(ReportJob, job_id)
            if job is not None:
                job.status = "done"
                job.report_json = report.model_dump_json()
                job.error = None
                job.updated_at = _now()
                s.commit()

    def fail(self, job_id: str, error: str) -> None:
        with self._session() as s:
            job = s.get(ReportJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error = error[:2000]
                job.updated_at = _now()
                s.commit()
