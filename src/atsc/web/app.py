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
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    app.include_router(report_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
