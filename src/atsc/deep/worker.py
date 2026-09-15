"""Layer 2 worker: the only process that holds ANTHROPIC_API_KEY.

    python -m atsc.deep.worker

Polls the job table, generates one report at a time, emails the link. Runs as a
separate Fly process group from the web app (fly.toml), so the cost boundary is a
process boundary, not a convention.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

from atsc.config import get_settings
from atsc.core.models import ScoreResult
from atsc.deep.db import JobStore, make_engine
from atsc.deep.email import EmailSender, report_ready_message, sender_from_settings
from atsc.deep.models import DeepReport

log = logging.getLogger(__name__)


class Generator(Protocol):
    def generate(self, result: ScoreResult) -> DeepReport: ...


def report_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/report/{token}"


def run_once(store: JobStore, generator: Generator, sender: EmailSender, *, base_url: str) -> bool:
    """Process at most one queued job. Returns False when the queue is empty."""
    job = store.claim_next()
    if job is None:
        return False
    try:
        report = generator.generate(job.inputs.result)
    except Exception as e:
        log.exception("report %s failed", job.id)
        store.fail(job.id, f"{type(e).__name__}: {e}")
        return True
    store.complete(job.id, report)
    if job.email:
        try:
            sender.send(report_ready_message(job.email, report_url(base_url, job.token)))
        except Exception:
            log.exception("email for %s failed", job.id)
    return True


def main() -> None:
    import anthropic

    from atsc.deep.generation import DeepReportGenerator
    from atsc.deep.retrieval import get_default_index

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    store = JobStore(make_engine(settings.database_url))
    generator = DeepReportGenerator(
        anthropic.Anthropic(), model=settings.deep_llm_model, index=get_default_index()
    )
    sender = sender_from_settings(settings)
    log.info("worker ready (model %s)", settings.deep_llm_model)
    while True:
        if not run_once(store, generator, sender, base_url=settings.public_base_url):
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
