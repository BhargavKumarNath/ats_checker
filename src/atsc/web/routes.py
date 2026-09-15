"""HTTP routes for the free layer: the two-box flow, landing pages, methodology."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from atsc.core.models import DISCLAIMER, Platform, RoleTrack
from atsc.core.parsing.checks import CHECK_ORDER
from atsc.core.scoring import (
    COSINE_CEILING,
    COSINE_FLOOR,
    REQUIREMENT_WEIGHT,
    SEVERITY_PENALTY,
    WEIGHT_PARSEABILITY,
    WEIGHT_SEMANTIC,
    WEIGHT_TAXONOMY,
)
from atsc.core.taxonomy import load_taxonomy
from atsc.free.presentation import (
    CHECK_LABELS,
    GENERIC_LABEL,
    PLATFORM_LABELS,
    PLATFORM_NOTES,
    ROLE_LABELS,
    checks_view,
    platform_check_table,
    role_category_weights,
)
from atsc.free.service import (
    Submission,
    SubmissionError,
    parse_platform,
    parse_role_track,
    run,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def clip(text: str, limit: int = 160) -> str:
    """Shorten a quoted evidence line for display; the full line still drove the score."""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


templates.env.filters["clip"] = clip
templates.env.globals.update(
    ROLE_LABELS=ROLE_LABELS,
    PLATFORM_LABELS=PLATFORM_LABELS,
    GENERIC_LABEL=GENERIC_LABEL,
    DISCLAIMER=DISCLAIMER,
)


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _form_context(
    *,
    platform: str = "generic",
    role_track: str = "auto",
    resume_text: str = "",
    jd_text: str = "",
) -> dict[str, Any]:
    return {
        "selected_platform": platform,
        "selected_role": role_track,
        "resume_text": resume_text,
        "jd_text": jd_text,
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", _form_context())


@router.post("/score", response_class=HTMLResponse)
async def score_endpoint(
    request: Request,
    jd_text: Annotated[str, Form()] = "",
    resume_text: Annotated[str, Form()] = "",
    platform: Annotated[str, Form()] = "generic",
    role_track: Annotated[str, Form()] = "auto",
    resume_file: Annotated[UploadFile | None, File()] = None,
) -> HTMLResponse:
    settings = request.app.state.settings
    resume_bytes: bytes | None = None
    filename = ""
    if resume_file is not None and resume_file.filename:
        # Read one byte past the limit so an oversized upload is detected without buffering it all.
        resume_bytes = await resume_file.read(settings.max_upload_bytes + 1)
        filename = resume_file.filename
        if not resume_bytes:
            resume_bytes = None

    sub = Submission(
        resume_text=resume_text,
        resume_bytes=resume_bytes,
        resume_filename=filename,
        jd_text=jd_text,
        platform=parse_platform(platform),
        role_track=parse_role_track(role_track),
    )
    form = _form_context(
        platform=platform, role_track=role_track, resume_text=resume_text, jd_text=jd_text
    )
    try:
        outcome = await asyncio.to_thread(run, sub, max_upload_bytes=settings.max_upload_bytes)
    except SubmissionError as e:
        ctx = {**form, "message": e.message}
        name = "partials/error.html" if _is_htmx(request) else "index.html"
        return templates.TemplateResponse(request, name, ctx, status_code=e.status)

    result = outcome.result
    ctx = {
        **form,
        "result": result,
        "checks": checks_view(outcome.report, result.platform),
        "file_format": outcome.report.file_format,
        "unassessed": sum(1 for c in outcome.report.checks if c.status == "not_assessed"),
        "role_label": ROLE_LABELS[result.role_track] if result.role_track else None,
        "role_source": "selector"
        if sub.role_track
        else ("job description" if result.role_track else None),
        "platform_label": PLATFORM_LABELS[result.platform] if result.platform else GENERIC_LABEL,
        "requirement_count": len(outcome.jd.requirements),
    }
    name = "partials/result.html" if _is_htmx(request) else "index.html"
    return templates.TemplateResponse(request, name, ctx)


@router.get("/roles/{track}", response_class=HTMLResponse)
def role_page(request: Request, track: str) -> HTMLResponse:
    rt = parse_role_track(track)
    if rt is None:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    ctx = {
        **_form_context(role_track=track),
        "track": rt,
        "label": ROLE_LABELS[rt],
        "weights": role_category_weights(load_taxonomy(), rt),
        "other_tracks": [(t.value, ROLE_LABELS[t]) for t in RoleTrack if t is not rt],
    }
    return templates.TemplateResponse(request, "role.html", ctx)


@router.get("/ats/{platform}", response_class=HTMLResponse)
def platform_page(request: Request, platform: str) -> HTMLResponse:
    p = parse_platform(platform)
    if p is None:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    ctx = {
        **_form_context(platform=platform),
        "platform": p,
        "label": PLATFORM_LABELS[p],
        "note": PLATFORM_NOTES[p],
        "table": platform_check_table(p),
        "other_platforms": [(x.value, PLATFORM_LABELS[x]) for x in Platform if x is not p],
    }
    return templates.TemplateResponse(request, "platform.html", ctx)


@router.get("/how-it-works", response_class=HTMLResponse)
def how_it_works(request: Request) -> HTMLResponse:
    ctx = {
        "w_semantic": round(WEIGHT_SEMANTIC * 100),
        "w_taxonomy": round(WEIGHT_TAXONOMY * 100),
        "w_parse": round(WEIGHT_PARSEABILITY * 100),
        "floor": COSINE_FLOOR,
        "ceiling": COSINE_CEILING,
        "preferred_weight": REQUIREMENT_WEIGHT["preferred"],
        "penalties": [(k.value, v) for k, v in SEVERITY_PENALTY.items() if v],
        "checks": [CHECK_LABELS[n][0] for n in CHECK_ORDER],
    }
    return templates.TemplateResponse(request, "how_it_works.html", ctx)


@router.get("/report", response_class=HTMLResponse)
def report_placeholder(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "report.html", {})
