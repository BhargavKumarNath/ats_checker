"""Layer 2 generation (technical_architecture.md §5, data_model.md §6).

The Anthropic client is replaced by a fake that returns canned structured outputs, so
these tests pin the grounding contract, the guards and the prompt shape without a
metered call. A live smoke script lives in scripts/deep_report_smoke.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atsc.core.jd import parse_job_description
from atsc.core.models import ScoreResult
from atsc.core.parsing import parse_resume_text
from atsc.core.scoring import score
from atsc.deep.diff import rewrite_diff
from atsc.deep.generation import (
    DeepReportGenerator,
    GenerationRefusedError,
    GroundingError,
    build_explanation_request,
    build_rewrite_request,
)
from atsc.deep.models import DeepReport
from atsc.deep.retrieval import get_default_index

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def scored() -> ScoreResult:
    resume, report = parse_resume_text((FIXTURES / "resume_clean.txt").read_text())
    jd = parse_job_description((FIXTURES / "jd_mle_llm.txt").read_text())
    return score(resume, report, jd)


class _Parsed:
    def __init__(self, parsed_output: Any, stop_reason: str = "end_turn") -> None:
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason
        self.stop_details = None


class FakeMessages:
    """Stands in for client.messages: records requests, answers with a scripted output."""

    def __init__(self, script: Any) -> None:
        self.script = script
        self.requests: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> _Parsed:
        self.requests.append(kwargs)
        out = self.script(kwargs) if callable(self.script) else self.script
        if isinstance(out, _Parsed):
            return out
        return _Parsed(kwargs["output_format"].model_validate(out))


class FakeClient:
    def __init__(self, script: Any) -> None:
        self.messages = FakeMessages(script)


def _echo_script(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Cite the first context id offered for every item; rewrite = original + one word."""
    fmt = kwargs["output_format"].__name__
    prompt = kwargs["messages"][0]["content"]
    if fmt == "ExplanationsOut":
        items = [ln for ln in prompt.split("\n") if ln.startswith("- item ")]
        return {
            "explanations": [
                {
                    "cluster_id": ln.split()[2],
                    "explanation_text": f"Explained {ln.split()[2]}.",
                    "context_ids": [int(ln.split("ids:")[1].split(",")[0])],
                }
                for ln in items
            ]
        }
    items = [ln for ln in prompt.split("\n") if ln.startswith("- bullet ")]
    return {
        "rewrites": [
            {
                "original_bullet": ln.split("| ")[1].split(" | ids:")[0],
                "suggested_rewrite": ln.split("| ")[1].split(" | ids:")[0] + " Reworded.",
                "example_ids": [int(ln.split("ids:")[1].split(",")[0])],
            }
            for ln in items
        ]
    }


def _generator(script: Any) -> DeepReportGenerator:
    return DeepReportGenerator(
        FakeClient(script),  # type: ignore[arg-type]
        model="claude-sonnet-5",
        index=get_default_index(),
    )


# -- request shape -------------------------------------------------------------------


def test_explanation_request_numbers_context_and_covers_skills(scored: ScoreResult) -> None:
    req = build_explanation_request(scored, get_default_index())
    ids = {cid for cid, _ in req.items}
    assert {m.cluster_id for m in scored.matched_skills} <= ids
    assert {u.cluster_id for u in scored.unmatched_required_skills} <= ids
    assert any(cid.startswith("check:") for cid in ids) == bool(scored.parseability_issues)
    assert len(req.context) >= len(req.items)
    assert all(text for text in req.context.values())


def test_rewrite_request_targets_weak_lines_only(scored: ScoreResult) -> None:
    req = build_rewrite_request(scored, get_default_index())
    weak = {m.resume_line for m in scored.requirement_matches if m.score < 70 and m.resume_line}
    assert req.bullets and {b for b, _ in req.bullets} <= weak
    assert len(req.bullets) <= 6


# -- generation ------------------------------------------------------------------------


def test_report_carries_verbatim_grounding(scored: ScoreResult) -> None:
    report = _generator(_echo_script).generate(scored)
    assert isinstance(report, DeepReport)
    index = get_default_index()
    texts = {c.text for c in index.chunks}
    assert report.explanations
    for e in report.explanations:
        assert e.retrieved_context and all(t in texts for t in e.retrieved_context)
    assert report.rewrite_suggestions
    for r in report.rewrite_suggestions:
        assert r.grounding_examples and all(t in texts for t in r.grounding_examples)
    assert report.model == "claude-sonnet-5"
    assert report.score_result == scored


def test_generation_uses_configured_model_and_cached_system_prompt(scored: ScoreResult) -> None:
    gen = _generator(_echo_script)
    gen.generate(scored)
    reqs = gen.client.messages.requests  # type: ignore[attr-defined]
    assert len(reqs) == 2
    for r in reqs:
        assert r["model"] == "claude-sonnet-5"
        assert r["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert r["thinking"] == {"type": "adaptive"}
        assert "interview" not in r["system"][0]["text"].lower().replace(
            "not a prediction of interview", ""
        )


def test_ungrounded_explanation_is_a_defect(scored: ScoreResult) -> None:
    def script(kwargs: dict[str, Any]) -> dict[str, Any]:
        out = _echo_script(kwargs)
        for e in out.get("explanations", []):
            e["context_ids"] = []
        return out

    with pytest.raises(GroundingError):
        _generator(script).generate(scored)


def test_unknown_context_id_is_a_defect(scored: ScoreResult) -> None:
    def script(kwargs: dict[str, Any]) -> dict[str, Any]:
        out = _echo_script(kwargs)
        for e in out.get("explanations", []):
            e["context_ids"] = [9999]
        return out

    with pytest.raises(GroundingError):
        _generator(script).generate(scored)


def test_refusal_is_surfaced(scored: ScoreResult) -> None:
    with pytest.raises(GenerationRefusedError):
        _generator(_Parsed(None, stop_reason="refusal")).generate(scored)


def test_rewrite_with_fabricated_numbers_is_dropped(scored: ScoreResult) -> None:
    def script(kwargs: dict[str, Any]) -> dict[str, Any]:
        out = _echo_script(kwargs)
        for i, r in enumerate(out.get("rewrites", [])):
            if i == 0:
                r["suggested_rewrite"] = r["original_bullet"] + " Achieved 0.97 AUC on 5M rows."
        return out

    report = _generator(script).generate(scored)
    assert all("0.97" not in r.suggested_rewrite for r in report.rewrite_suggestions)


def test_readability_flag_is_set_from_the_metric(scored: ScoreResult) -> None:
    stuffed = (
        " RAG retrieval-augmented generation vector search LangChain LlamaIndex pgvector "
        "Pinecone embeddings LLM MLflow Kubernetes Docker Airflow PyTorch LoRA."
    )

    def script(kwargs: dict[str, Any]) -> dict[str, Any]:
        out = _echo_script(kwargs)
        for r in out.get("rewrites", []):
            r["suggested_rewrite"] = r["original_bullet"] + stuffed
        return out

    report = _generator(script).generate(scored)
    assert report.rewrite_suggestions and all(
        r.readability_flag for r in report.rewrite_suggestions
    )


# -- diff download ---------------------------------------------------------------------


def test_rewrite_diff_lists_only_changed_lines(scored: ScoreResult) -> None:
    report = _generator(_echo_script).generate(scored)
    diff = rewrite_diff(report)
    assert diff.startswith("--- resume (original)")
    for r in report.rewrite_suggestions:
        assert f"-{r.original_bullet}" in diff
        assert f"+{r.suggested_rewrite}" in diff
    assert "Priya Natarajan" not in diff  # untouched lines are not exported
