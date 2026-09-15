"""Carry a scored Layer 1 result into checkout without storing anything before the buyer acts.

The free check is stateless (build_plan.md §3). The result page embeds the full inputs
as an opaque payload in the checkout form; the checkout handler decodes it and only then
creates a job row. A checksum catches truncation or tampering with a clear error.
"""

from __future__ import annotations

import base64
import hashlib
import json
import zlib

from pydantic import BaseModel, ValidationError

from atsc.core.models import ParseabilityReport, ParsedJobDescription, ParsedResume, ScoreResult

_DIGEST_CHARS = 16


class HandoffError(ValueError):
    pass


class JobInputs(BaseModel):
    resume: ParsedResume
    report: ParseabilityReport
    jd: ParsedJobDescription
    result: ScoreResult


def _digest(body: str) -> str:
    return hashlib.sha256(body.encode("ascii")).hexdigest()[:_DIGEST_CHARS]


def encode_inputs(inputs: JobInputs) -> str:
    raw = inputs.model_dump_json().encode("utf-8")
    body = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")
    return f"{body}.{_digest(body)}"


def decode_inputs(token: str) -> JobInputs:
    body, sep, digest = token.rpartition(".")
    if not sep or _digest(body) != digest:
        raise HandoffError("payload is missing, truncated or altered")
    try:
        raw = zlib.decompress(base64.urlsafe_b64decode(body.encode("ascii")))
        return JobInputs.model_validate(json.loads(raw))
    except (ValueError, zlib.error, ValidationError) as e:
        raise HandoffError("payload could not be decoded") from e
