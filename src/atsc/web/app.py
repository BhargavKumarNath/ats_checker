"""FastAPI app factory for the web process (Layer 1 routes + Layer 2 non-generating routes).

Cost boundary: this process never imports a metered client (import-linter contract,
tests/test_cost_boundary.py) and runs without ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from atsc.config import get_settings
from atsc.free.growth import GrowthLog
from atsc.web.ratelimit import RateLimitMiddleware, SlidingWindowLimiter
from atsc.web.report import router as report_router
from atsc.web.routes import router

STATIC_DIR = Path(__file__).parent / "static"


def create_app(*, warm: bool | None = None) -> FastAPI:
    settings = get_settings()
    warm_on_start = settings.warm_on_start if warm is None else warm

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if warm_on_start:
            from atsc.core.scoring import warm as warm_models

            await asyncio.to_thread(warm_models)
        yield

    app = FastAPI(title="ATS Checker", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.growth = GrowthLog(
        Path(settings.growth_log_path) if settings.growth_log_path else None
    )
    if settings.score_rate_limit > 0:
        app.add_middleware(
            RateLimitMiddleware,
            limiter=SlidingWindowLimiter(
                limit=settings.score_rate_limit, window_seconds=settings.score_rate_window_seconds
            ),
            client_ip_header=settings.client_ip_header,
        )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    app.include_router(report_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
