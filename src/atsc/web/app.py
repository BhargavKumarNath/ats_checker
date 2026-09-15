"""FastAPI app factory for the web process (Layer 1 routes + Layer 2 non-generating routes)."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="ATS Checker", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
