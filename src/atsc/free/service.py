"""Layer 1 request handling: validate the submission, parse both sides, score.

Pure service layer: no HTTP types here. The web layer maps SubmissionError.status
to a response code and renders the message verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass

from atsc.core.jd import parse_job_description
from atsc.core.models import (
    ParseabilityReport,
    ParsedJobDescription,
    ParsedResume,
    Platform,
    RoleTrack,
    ScoreResult,
)
from atsc.core.parsing import UnsupportedFormatError, parse_resume_file, parse_resume_text
from atsc.core.scoring import score

MIN_RESUME_CHARS = 200
MIN_JD_CHARS = 100


class SubmissionError(ValueError):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class Submission:
    resume_text: str = ""
    resume_bytes: bytes | None = None
    resume_filename: str = ""
    jd_text: str = ""
    platform: Platform | None = None  # None = generic
    role_track: RoleTrack | None = None  # None = use the JD's signal


@dataclass
class Outcome:
    result: ScoreResult
    resume: ParsedResume
    report: ParseabilityReport
    jd: ParsedJobDescription


def parse_platform(value: str) -> Platform | None:
    try:
        return Platform(value)
    except ValueError:
        return None


def parse_role_track(value: str) -> RoleTrack | None:
    try:
        return RoleTrack(value)
    except ValueError:
        return None


def run(sub: Submission, *, max_upload_bytes: int) -> Outcome:
    if sub.resume_bytes is not None and len(sub.resume_bytes) > max_upload_bytes:
        mb = max_upload_bytes / 1_000_000
        raise SubmissionError(
            f"That file is larger than {mb:g} MB. Export a smaller PDF or paste the text instead.",
            status=413,
        )
    if len(sub.jd_text.strip()) < MIN_JD_CHARS:
        raise SubmissionError(
            "Paste the full job description. The requirements section is what gets matched, "
            "so a title alone is not enough."
        )
    if sub.resume_bytes:
        try:
            resume, report = parse_resume_file(sub.resume_bytes, sub.resume_filename)
        except UnsupportedFormatError as e:
            raise SubmissionError(str(e)) from e
    elif len(sub.resume_text.strip()) >= MIN_RESUME_CHARS:
        resume, report = parse_resume_text(sub.resume_text)
    else:
        raise SubmissionError(
            "Add your resume: upload a PDF or .docx, or paste the full text. "
            "Uploading a file gives a fuller parseability check."
        )
    if len(resume.raw_text.strip()) < MIN_RESUME_CHARS:
        raise SubmissionError(
            "Almost no text could be read from that resume file. If it is a scanned or "
            "image-only PDF, most ATS platforms cannot read it either. Paste the text instead."
        )
    jd = parse_job_description(sub.jd_text)
    result = score(resume, report, jd, role_track=sub.role_track, platform=sub.platform)
    return Outcome(result=result, resume=resume, report=report, jd=jd)
