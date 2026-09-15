"""Paid-report routes in the web process: checkout, Stripe webhook, report page, diff.

Cost boundary: this module imports the job store and Stripe, never the generator. The
worker (a separate process) is the only thing that calls a model.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from atsc.core.models import CheckName
from atsc.core.taxonomy import load_taxonomy
from atsc.deep.db import JobStore, make_engine
from atsc.deep.diff import rewrite_diff
from atsc.deep.handoff import HandoffError, decode_inputs
from atsc.deep.payments import (
    WebhookError,
    completed_session,
    create_checkout_session,
    verify_webhook,
)
from atsc.free.presentation import CHECK_LABELS
from atsc.web.routes import templates

router = APIRouter()


def store(app: FastAPI) -> JobStore:
    if not hasattr(app.state, "job_store"):
        app.state.job_store = JobStore(make_engine(app.state.settings.database_url))
    return app.state.job_store  # type: ignore[no-any-return]


def _display_names() -> dict[str, str]:
    """cluster_id (or check:<name>) → the label a reader knows it by."""
    names = {c.cluster_id: c.canonical_name for c in load_taxonomy().clusters}
    for check in CheckName:
        names[f"check:{check.value}"] = f"Formatting: {CHECK_LABELS[check][0]}"
    return names


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@router.post("/report/checkout")
def checkout(request: Request, payload: Annotated[str, Form()] = "") -> HTMLResponse:
    settings = request.app.state.settings
    if not settings.payments_enabled:
        return templates.TemplateResponse(request, "report.html", {}, status_code=200)
    try:
        inputs = decode_inputs(payload)
    except HandoffError as e:
        ctx = {"message": f"{e}. Run the free check again and retry."}
        return templates.TemplateResponse(request, "report_error.html", ctx, status_code=422)
    job = store(request.app).create(inputs)
    base = settings.public_base_url.rstrip("/")
    url, session_id = create_checkout_session(
        settings,
        job_id=job.id,
        success_url=f"{base}/report/{job.token}",
        cancel_url=f"{base}/report/{job.token}?cancelled=1",
    )
    store(request.app).set_stripe_session(job.id, session_id)
    return RedirectResponse(url, status_code=303)  # type: ignore[return-value]


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> PlainTextResponse:
    settings = request.app.state.settings
    payload = await request.body()
    try:
        event = verify_webhook(settings, payload, request.headers.get("Stripe-Signature", ""))
    except WebhookError as e:
        return PlainTextResponse(str(e), status_code=400)
    done = completed_session(event)
    if done is not None:
        job_id, session_id, email = done
        store(request.app).mark_paid(job_id, stripe_session_id=session_id, email=email)
    return PlainTextResponse("ok")


@router.get("/report/{token}", response_class=HTMLResponse)
def report_page(request: Request, token: str) -> HTMLResponse:
    job = store(request.app).get_by_token(token)
    if job is None:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    ctx = {
        "job": job,
        "token": token,
        "cancelled": request.query_params.get("cancelled") == "1",
        "payload": None,
    }
    if job.status == "done" and job.report is not None:
        ctx["report"] = job.report
        ctx["names"] = _display_names()
        return templates.TemplateResponse(request, "report_done.html", ctx)
    return templates.TemplateResponse(request, "report_status.html", ctx)


@router.get("/report/{token}/status", response_class=HTMLResponse)
def report_status(request: Request, token: str) -> HTMLResponse:
    job = store(request.app).get_by_token(token)
    if job is None:
        return HTMLResponse("", status_code=404)
    ctx = {"job": job, "token": token, "cancelled": False}
    resp = templates.TemplateResponse(request, "partials/report_status.html", ctx)
    if job.status in ("done", "failed"):
        resp.headers["HX-Redirect"] = f"/report/{token}"
    return resp


@router.get("/report/{token}/diff")
def report_diff(request: Request, token: str) -> PlainTextResponse:
    job = store(request.app).get_by_token(token)
    if job is None or job.report is None:
        return PlainTextResponse("not found", status_code=404)
    return PlainTextResponse(
        rewrite_diff(job.report),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="resume-rewrites.diff"'},
    )
