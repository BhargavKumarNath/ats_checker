"""Retention job for `report_jobs`: delete old finished jobs and abandoned checkouts.

Run on a schedule, never from the always-on web or worker processes:

    python -m atsc.deep.retention                # defaults: finished 30 days, abandoned 7 days
    python -m atsc.deep.retention --dry-run      # count only

On Fly: `fly machine run <image> --schedule daily "python -m atsc.deep.retention"` with
ATSC_DATABASE_URL set; the machine exits when the job finishes. Locally `scripts/purge_jobs.py`
is a thin wrapper around `main`.

Why two ages: a `done`/`failed` job stores a resume and a report the buyer has had weeks to
download. An `awaiting_payment` job stores a resume for a checkout that never completed;
Stripe Checkout sessions expire within 24 hours, so after a few days it can never be paid.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atsc.config import get_settings
from atsc.deep.db import JobStore, ReportJob, make_engine

FINISHED = ("done", "failed")
ABANDONED = ("awaiting_payment",)
DEFAULT_FINISHED_DAYS = 30
DEFAULT_ABANDONED_DAYS = 7


def purge(
    store: JobStore,
    *,
    now: datetime | None = None,
    finished_days: int = DEFAULT_FINISHED_DAYS,
    abandoned_days: int | None = DEFAULT_ABANDONED_DAYS,
) -> dict[str, int]:
    """Delete by age and return counts per class. `abandoned_days=None` leaves unpaid jobs alone."""
    now = now or datetime.now(UTC)
    finished = store.purge(FINISHED, older_than=timedelta(days=finished_days), now=now)
    abandoned = (
        store.purge(ABANDONED, older_than=timedelta(days=abandoned_days), now=now)
        if abandoned_days is not None
        else 0
    )
    return {"finished": finished, "abandoned": abandoned}


def _count(store: JobStore, statuses: tuple[str, ...], *, older_than: timedelta) -> int:
    cutoff = datetime.now(UTC) - older_than
    with Session(store.engine) as s:
        n = s.scalar(
            select(func.count())
            .select_from(ReportJob)
            .where(ReportJob.status.in_(statuses))
            .where(ReportJob.updated_at < cutoff)
        )
        return int(n or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--database-url", default=None, help="defaults to ATSC_DATABASE_URL from settings"
    )
    parser.add_argument("--finished-days", type=int, default=DEFAULT_FINISHED_DAYS)
    parser.add_argument(
        "--abandoned-days",
        type=int,
        default=DEFAULT_ABANDONED_DAYS,
        help="age for unpaid awaiting_payment jobs; negative keeps them",
    )
    parser.add_argument("--dry-run", action="store_true", help="count, do not delete")
    args = parser.parse_args(argv)

    url = args.database_url or get_settings().database_url
    store = JobStore(make_engine(url))
    abandoned_days = args.abandoned_days if args.abandoned_days >= 0 else None

    if args.dry_run:
        finished = _count(store, FINISHED, older_than=timedelta(days=args.finished_days))
        abandoned = (
            _count(store, ABANDONED, older_than=timedelta(days=abandoned_days))
            if abandoned_days is not None
            else 0
        )
        print(f"would delete {finished} finished and {abandoned} abandoned report jobs")
        return 0

    counts = purge(store, finished_days=args.finished_days, abandoned_days=abandoned_days)
    print(f"deleted {counts['finished']} finished and {counts['abandoned']} abandoned report jobs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
