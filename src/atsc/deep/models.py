"""Deep report objects (data_model.md §6).

Grounding is schema-required: `retrieved_context` and `grounding_examples` must be
non-empty, so an ungrounded explanation or rewrite cannot be constructed at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from atsc.core.models import ScoreResult


class Explanation(BaseModel):
    # A taxonomy cluster id, or "check:<check_name>" for a parseability finding.
    cluster_id: str
    explanation_text: str
    retrieved_context: list[str] = Field(min_length=1)


class RewriteSuggestion(BaseModel):
    original_bullet: str
    suggested_rewrite: str
    readability_flag: bool
    grounding_examples: list[str] = Field(min_length=1)


class DeepReport(BaseModel):
    score_result: ScoreResult
    explanations: list[Explanation] = Field(default_factory=list)
    rewrite_suggestions: list[RewriteSuggestion] = Field(default_factory=list)
    # Traceability (additive to the spec): which model produced the text and when.
    model: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
