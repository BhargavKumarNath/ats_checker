"""Layer 2 generation: retrieve, then ask Claude for explanations and rewrites.

This is the only module (with the worker) allowed to import the Anthropic SDK; the
import-linter contract and tests/test_cost_boundary.py keep it out of the free path.

Grounding contract (data_model.md §6): the model never writes the grounding strings.
It receives numbered context items and cites ids; the code maps the ids back to the
verbatim corpus text. An empty or unknown citation is a GroundingError, not a report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic
from pydantic import BaseModel

from atsc.core.matcher import get_default_matcher
from atsc.core.models import DISCLAIMER, ScoreResult
from atsc.deep.corpus import Chunk
from atsc.deep.models import DeepReport, Explanation, RewriteSuggestion
from atsc.deep.readability import readability_flag
from atsc.deep.retrieval import CorpusIndex

MAX_REWRITES = 6
WEAK_LINE_SCORE = 70  # requirement_matches below this get a rewrite
MIN_BULLET_WORDS = 6  # skill-list entries are not bullets

SYSTEM_PROMPT = "\n".join(
    [
        "You write the paid deep report for an ATS resume checker for ML, data science and AI",
        "roles. You are given a scored comparison of one resume against one job description",
        "and a numbered list of context items retrieved from a curated corpus: taxonomy",
        "equivalences, strong bullet examples, rewrite examples, platform behaviours and",
        "writing guidance.",
        "",
        "Rules:",
        "- Every statement you make must rest on the context items. Cite the ids you used;",
        "  cite at least one for every item you produce.",
        "- Explanations say why a skill matched or did not, naming the exact phrasings",
        '  involved (for example, "LoRA" on the resume counted as "parameter-efficient',
        '  fine-tuning" in the posting). Keep each under 60 words.',
        "- Rewrites keep every fact of the original bullet. Never add a tool, number, scale",
        "  or outcome that is not in the original. Make the line more specific in structure",
        "  (method, scale, outcome) and use the posting's phrasing only where the original",
        "  already supports it.",
        "- Do not repeat a keyword or list synonyms to game a scanner; one clear mention",
        "  beats three.",
        f"- Never describe the score as a prediction of hiring outcomes. {DISCLAIMER}",
        "- Plain, direct sentences. No praise, no filler.",
    ]
)


class GenerationError(RuntimeError):
    pass


class GroundingError(GenerationError):
    pass


class GenerationRefusedError(GenerationError):
    pass


# -- structured output the model returns (ids, never grounding text) ----------------------


class ExplanationOut(BaseModel):
    cluster_id: str
    explanation_text: str
    context_ids: list[int]


class ExplanationsOut(BaseModel):
    explanations: list[ExplanationOut]


class RewriteOut(BaseModel):
    original_bullet: str
    suggested_rewrite: str
    example_ids: list[int]


class RewritesOut(BaseModel):
    rewrites: list[RewriteOut]


# -- retrieval → request ------------------------------------------------------------------


@dataclass
class _Context:
    """Numbered context items shared by one request; id → verbatim chunk text."""

    by_id: dict[int, str] = field(default_factory=dict)
    display: dict[int, str] = field(default_factory=dict)
    _seen: dict[str, int] = field(default_factory=dict)

    def add(self, chunk: Chunk) -> int:
        if chunk.chunk_id in self._seen:
            return self._seen[chunk.chunk_id]
        cid = len(self.by_id) + 1
        self.by_id[cid] = chunk.text
        self.display[cid] = chunk.embed_text
        self._seen[chunk.chunk_id] = cid
        return cid

    def render(self) -> str:
        return "\n".join(f"[C{i}] {t}" for i, t in self.display.items())


@dataclass
class ExplanationRequest:
    items: list[tuple[str, str]]  # (cluster_id or check:<name>, brief)
    context: dict[int, str]
    prompt: str


@dataclass
class RewriteRequest:
    bullets: list[tuple[str, str]]  # (original bullet, requirement it should serve)
    context: dict[int, str]
    prompt: str


def _by_id(index: CorpusIndex, chunk_id: str) -> Chunk | None:
    return next((c for c in index.chunks if c.chunk_id == chunk_id), None)


def _cluster_context(index: CorpusIndex, ctx: _Context, cluster_id: str, query: str) -> list[int]:
    ids: list[int] = []
    equiv = _by_id(index, f"equiv:{cluster_id}")
    if equiv is not None:
        ids.append(ctx.add(equiv))
    for hit in index.search(query, k=2, kinds=["strong_bullet"], cluster_ids=[cluster_id]):
        ids.append(ctx.add(hit.chunk))
    return ids


def build_explanation_request(result: ScoreResult, index: CorpusIndex) -> ExplanationRequest:
    ctx = _Context()
    items: list[tuple[str, str]] = []
    lines: list[str] = []
    for m in result.matched_skills:
        ids = _cluster_context(index, ctx, m.cluster_id, f"{m.canonical_name} {m.jd_evidence}")
        brief = f'matched; resume: "{m.resume_evidence}"; posting: "{m.jd_evidence}"'
        items.append((m.cluster_id, brief))
        lines.append(f"- item {m.cluster_id} | {brief} | ids:{','.join(map(str, ids))}")
    for u in result.unmatched_required_skills:
        ids = _cluster_context(index, ctx, u.cluster_id, f"{u.canonical_name} {u.jd_evidence}")
        brief = f'required but not found on the resume; posting: "{u.jd_evidence}"'
        items.append((u.cluster_id, brief))
        lines.append(f"- item {u.cluster_id} | {brief} | ids:{','.join(map(str, ids))}")
    platform = result.platform.value if result.platform else None
    for check in result.parseability_issues:
        name = check.check_name.value
        query = name.replace("_", " ") + (f" {check.location}" if check.location else "")
        hits = index.search(query, k=2, kinds=["platform_quirk"], platform=platform)
        ids = [ctx.add(h.chunk) for h in hits]
        if not ids:
            continue
        brief = f"parseability check failed ({name}); location: {check.location or 'n/a'}"
        items.append((f"check:{name}", brief))
        lines.append(f"- item check:{name} | {brief} | ids:{','.join(map(str, ids))}")
    c = result.components
    prompt = (
        f"Overall score {result.overall_score}/100 (semantic {c.semantic_match_score}, "
        f"skill overlap {c.taxonomy_overlap_score}, parseability {c.parseability_score}).\n\n"
        "Write one explanation per item below. Return the item's id as cluster_id exactly as "
        "given, and cite context ids from the item's list (you may also cite any other item).\n\n"
        + "\n".join(lines)
        + "\n\nContext items:\n"
        + ctx.render()
    )
    return ExplanationRequest(items=items, context=ctx.by_id, prompt=prompt)


def _weak_lines(result: ScoreResult) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for m in sorted(result.requirement_matches, key=lambda x: x.score):
        line = m.resume_line
        if not line or m.score >= WEAK_LINE_SCORE or line in seen:
            continue
        if len(line.split()) < MIN_BULLET_WORDS:
            continue
        seen.add(line)
        out.append((line, m.jd_text))
        if len(out) == MAX_REWRITES:
            break
    return out


def build_rewrite_request(result: ScoreResult, index: CorpusIndex) -> RewriteRequest:
    ctx = _Context()
    matcher = get_default_matcher()
    bullets = _weak_lines(result)
    lines: list[str] = []
    guidance = _by_id(index, "guidance:keyword_density_versus_readability")
    guidance_id = ctx.add(guidance) if guidance is not None else None
    for i, (bullet, requirement) in enumerate(bullets, start=1):
        clusters = sorted({m.cluster_id for m in matcher.match(requirement + " " + bullet)})
        hits = index.search(
            requirement,
            k=3,
            kinds=["strong_bullet", "rewrite_pair"],
            cluster_ids=clusters or None,
        )
        ids = [ctx.add(h.chunk) for h in hits]
        if guidance_id is not None:
            ids.append(guidance_id)
        lines.append(f"- bullet {i} | {bullet} | ids:{','.join(map(str, ids))}")
        lines.append(f"  target requirement: {requirement}")
    prompt = (
        "Rewrite each bullet below so it serves its target requirement better, keeping every "
        "fact and adding none. Return original_bullet exactly as given and cite the example ids "
        "you drew on.\n\n" + "\n".join(lines) + "\n\nContext items:\n" + ctx.render()
    )
    return RewriteRequest(bullets=bullets, context=ctx.by_id, prompt=prompt)


# -- guards -----------------------------------------------------------------------------

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")


def introduces_numbers(original: str, rewrite: str) -> bool:
    """A rewrite that adds a figure the original did not contain is a fabricated claim."""
    return not set(_NUMBER.findall(rewrite)) <= set(_NUMBER.findall(original))


def _resolve(ids: list[int], context: dict[int, str], what: str) -> list[str]:
    if not ids:
        raise GroundingError(f"{what} cites no context")
    out: list[str] = []
    for i in ids:
        if i not in context:
            raise GroundingError(f"{what} cites unknown context id {i}")
        if context[i] not in out:
            out.append(context[i])
    return out


# -- generator ----------------------------------------------------------------------------


class _Messages(Protocol):
    def parse(self, **kwargs: Any) -> Any: ...


class _Client(Protocol):
    @property
    def messages(self) -> _Messages: ...


class DeepReportGenerator:
    def __init__(self, client: anthropic.Anthropic | _Client, *, model: str, index: CorpusIndex):
        self.client = client
        self.model = model
        self.index = index
        self.last_usage: list[Any] = []

    def _call(self, prompt: str, output_format: type[BaseModel]) -> Any:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ],
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
            output_format=output_format,
        )
        if getattr(response, "usage", None) is not None:
            self.last_usage.append(response.usage)
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise GenerationRefusedError(f"model declined: {details}")
        if response.stop_reason == "max_tokens":
            raise GenerationError("output truncated at max_tokens")
        if response.parsed_output is None:
            raise GenerationError("no structured output returned")
        return response.parsed_output

    def generate(self, result: ScoreResult) -> DeepReport:
        ex_req = build_explanation_request(result, self.index)
        explanations: list[Explanation] = []
        if ex_req.items:
            out: ExplanationsOut = self._call(ex_req.prompt, ExplanationsOut)
            for e in out.explanations:
                explanations.append(
                    Explanation(
                        cluster_id=e.cluster_id,
                        explanation_text=e.explanation_text,
                        retrieved_context=_resolve(
                            e.context_ids, ex_req.context, f"explanation {e.cluster_id}"
                        ),
                    )
                )

        rw_req = build_rewrite_request(result, self.index)
        rewrites: list[RewriteSuggestion] = []
        if rw_req.bullets:
            rout: RewritesOut = self._call(rw_req.prompt, RewritesOut)
            for r in rout.rewrites:
                if introduces_numbers(r.original_bullet, r.suggested_rewrite):
                    continue  # fabricated figure: drop the suggestion, keep the report
                rewrites.append(
                    RewriteSuggestion(
                        original_bullet=r.original_bullet,
                        suggested_rewrite=r.suggested_rewrite,
                        readability_flag=readability_flag(r.original_bullet, r.suggested_rewrite),
                        grounding_examples=_resolve(r.example_ids, rw_req.context, "rewrite"),
                    )
                )

        return DeepReport(
            score_result=result,
            explanations=explanations,
            rewrite_suggestions=rewrites,
            model=self.model,
        )


__all__ = [
    "DeepReportGenerator",
    "ExplanationRequest",
    "GenerationError",
    "GenerationRefusedError",
    "GroundingError",
    "RewriteRequest",
    "build_explanation_request",
    "build_rewrite_request",
    "introduces_numbers",
]
