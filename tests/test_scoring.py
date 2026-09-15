"""Scoring engine (ats_scoring_spec.md §2-6, data_model.md §5, build_plan.md interp. 4/7/8)."""

from __future__ import annotations

import socket
import time
from pathlib import Path

import numpy as np
import pytest

from atsc.core.jd import parse_job_description
from atsc.core.matcher import ClusterMatcher
from atsc.core.models import (
    Bullet,
    CheckName,
    ParseabilityReport,
    ParsedJobDescription,
    ParsedResume,
    Platform,
    Requirement,
    RoleTrack,
    ScoreResult,
    SkillEntry,
    WorkEntry,
)
from atsc.core.parsing import parse_resume_text
from atsc.core.parsing.checks import make_check
from atsc.core.scoring import (
    DISCLAIMER,
    QUERY_PREFIX,
    blend,
    parseability_score,
    score,
    semantic_match,
    taxonomy_overlap,
    warm,
)
from atsc.core.taxonomy import load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures"


class FakeEmbedder:
    """Known strings map to fixed directions so cosines are exact; others are orthogonal."""

    dim = 4

    def __init__(self, table: dict[str, list[float]]) -> None:
        self._table = {k.lower(): np.array(v, dtype=np.float32) for k, v in table.items()}

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            key = t.removeprefix(QUERY_PREFIX).lower()
            v = self._table.get(key, np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32))
            out[i] = v / np.linalg.norm(v)
        return out


def _unit_at(cos: float) -> list[float]:
    """A unit vector whose cosine with [1,0,0,0] is exactly `cos`."""
    return [cos, float(np.sqrt(1 - cos * cos)), 0.0, 0.0]


# -- component 3: parseability (interp. 7, 8) -----------------------------------


def _report(**fails: str) -> ParseabilityReport:
    """Pasted-text report where the named checks fail; other text checks pass."""
    checks = [
        make_check(CheckName.INCONSISTENT_DATES, fails.get("inconsistent_dates", "pass")),
        make_check(CheckName.NON_STANDARD_SECTION_HEADERS, fails.get("headers", "pass")),
        make_check(CheckName.TABLE_DETECTED, fails.get("table", "not_assessed")),
        make_check(CheckName.MULTI_COLUMN_LAYOUT, fails.get("columns", "not_assessed")),
        make_check(CheckName.IMAGE_BASED_PDF, fails.get("image", "not_assessed")),
    ]
    return ParseabilityReport(file_format="pasted_text", checks=checks)


def test_parseability_all_pass_is_100() -> None:
    assert parseability_score(_report(), Platform.WORKDAY) == 100


def test_parseability_medium_failure_costs_15() -> None:
    assert parseability_score(_report(inconsistent_dates="fail"), Platform.GREENHOUSE) == 85


def test_parseability_penalty_follows_platform_severity() -> None:
    r = _report(table="fail")
    assert parseability_score(r, Platform.WORKDAY) == 75  # high
    assert parseability_score(r, Platform.LEVER) == 95  # low


def test_parseability_generic_platform_uses_max_severity() -> None:
    assert parseability_score(_report(table="fail"), None) == 75


def test_parseability_floors_at_zero() -> None:
    r = _report(
        inconsistent_dates="fail", headers="fail", table="fail", columns="fail", image="fail"
    )
    assert parseability_score(r, Platform.WORKDAY) == 0


def test_parseability_ignores_unassessed_checks() -> None:
    assert parseability_score(_report(), None) == 100


# -- blend (spec §5) ---------------------------------------------------------------


def test_blend_weights() -> None:
    assert blend(100, 100, 100) == 100
    assert blend(80, 60, 100) == 77  # 36 + 21 + 20
    assert blend(0, 0, 0) == 0


# -- component 1: semantic match (spec §2.1, interp. 4) ---------------------------


def _reqs(*pairs: tuple[str, str]) -> list[Requirement]:
    return [Requirement(raw_text=t, requirement_type=k) for t, k in pairs]  # type: ignore[arg-type]


def test_semantic_ceiling_cosine_scores_100() -> None:
    emb = FakeEmbedder({"req a": [1, 0, 0, 0], "line a": _unit_at(0.82)})
    s, matches = semantic_match(["line a"], _reqs(("req a", "required")), emb)
    assert s == 100
    assert matches[0].resume_line == "line a"
    assert matches[0].similarity == pytest.approx(0.82, abs=1e-3)


def test_semantic_floor_cosine_scores_0() -> None:
    emb = FakeEmbedder({"req a": [1, 0, 0, 0], "line a": _unit_at(0.47)})
    s, _ = semantic_match(["line a"], _reqs(("req a", "required")), emb)
    assert s == 0


def test_semantic_midpoint_and_best_line_selection() -> None:
    emb = FakeEmbedder({"req a": [1, 0, 0, 0], "weak": _unit_at(0.55), "strong": _unit_at(0.645)})
    s, matches = semantic_match(["weak", "strong"], _reqs(("req a", "required")), emb)
    assert s == 50
    assert matches[0].resume_line == "strong"


def test_semantic_preferred_requirements_weigh_half() -> None:
    emb = FakeEmbedder(
        {
            "req a": [1, 0, 0, 0],
            "req b": [0, 0, 1, 0],
            "line a": _unit_at(0.85),
            "line b": [0, float(np.sqrt(1 - 0.47**2)), 0.47, 0],  # cos 0.47 with req b → 0
        }
    )
    # req a (required) scores 100, req b (preferred) scores 0 → (100·1 + 0·0.5)/1.5 = 67
    s, _ = semantic_match(
        ["line a", "line b"], _reqs(("req a", "required"), ("req b", "preferred")), emb
    )
    assert s == 67


def test_semantic_empty_inputs_score_0() -> None:
    emb = FakeEmbedder({})
    assert semantic_match([], _reqs(("req a", "required")), emb)[0] == 0
    assert semantic_match(["line a"], [], emb)[0] == 0


# -- component 2: taxonomy overlap (spec §3) --------------------------------------


def _resume(
    skills: list[tuple[str, list[str]]], bullets: list[tuple[str, list[str]]] | None = None
) -> ParsedResume:
    bullets = bullets or []
    return ParsedResume(
        skills=[SkillEntry(raw_text=t, matched_clusters=c) for t, c in skills],
        work=[WorkEntry(bullets=[Bullet(raw_text=t, matched_clusters=c) for t, c in bullets])],
    )


def _jd(
    reqs: list[tuple[str, str, list[str]]], track: RoleTrack | str = "unclear"
) -> ParsedJobDescription:
    return ParsedJobDescription(
        role_track_signal=track,  # type: ignore[arg-type]
        requirements=[
            Requirement(raw_text=t, requirement_type=k, matched_clusters=c)  # type: ignore[arg-type]
            for t, k, c in reqs
        ],
    )


JD = _jd(
    [
        ("Experience with RAG.", "required", ["rag"]),
        ("Strong PyTorch skills.", "required", ["dl_frameworks"]),
        ("Fine-tuning with LoRA.", "required", ["peft"]),
        ("Quantization is a plus.", "preferred", ["quantization"]),
    ]
)


def test_overlap_uniform_weights_when_track_unclear() -> None:
    resume = _resume([("RAG", ["rag"])], [("Trained models in PyTorch", ["dl_frameworks"])])
    res = taxonomy_overlap(resume, JD, load_taxonomy(), None, ClusterMatcher(load_taxonomy()))
    # matched 2 of (3 required x1 + 1 preferred x0.5 = 3.5) -> 57
    assert res.score == 57
    assert [m.cluster_id for m in res.matched] == ["dl_frameworks", "rag"]
    assert [u.cluster_id for u in res.unmatched_required] == ["peft"]
    assert [u.cluster_id for u in res.unmatched_preferred] == ["quantization"]


def test_overlap_carries_evidence_and_canonical_names() -> None:
    resume = _resume([("RAG pipelines", ["rag"])])
    res = taxonomy_overlap(resume, JD, load_taxonomy(), None, ClusterMatcher(load_taxonomy()))
    m = res.matched[0]
    assert m.canonical_name == "Retrieval-augmented generation"
    assert m.resume_evidence == "RAG pipelines"
    assert m.jd_evidence == "Experience with RAG."
    assert res.unmatched_required[0].jd_evidence == "Strong PyTorch skills."


def test_overlap_role_track_weights_change_score() -> None:
    resume = _resume([("RAG", ["rag"])])
    tax = load_taxonomy()
    mle = taxonomy_overlap(resume, JD, tax, RoleTrack.MLE, ClusterMatcher(tax)).score
    ds = taxonomy_overlap(resume, JD, tax, RoleTrack.DATA_SCIENTIST, ClusterMatcher(tax)).score
    # Every JD cluster here is LLM/Inference (High for MLE, Medium/Low for DS). The matched
    # share is identical under uniform scaling, so the scores must differ only if the
    # weights are actually applied per cluster: quantization is Inference & Serving,
    # weighted Low for DS, so DS's unmatched mass is smaller and its score is higher.
    assert ds > mle


def test_overlap_embedding_fallback_resolves_unlisted_skill_phrase() -> None:
    emb = FakeEmbedder({"low-rank adapter training": [1, 0, 0, 0], "lora": _unit_at(0.95)})
    matcher = ClusterMatcher(load_taxonomy(), embedder=emb, similarity_threshold=0.9)
    resume = _resume([("low-rank adapter training", [])])
    res = taxonomy_overlap(resume, JD, load_taxonomy(), None, matcher)
    assert [m.cluster_id for m in res.matched] == ["peft"]
    assert res.matched[0].resume_evidence == "low-rank adapter training"


def test_overlap_no_jd_clusters_scores_0() -> None:
    res = taxonomy_overlap(
        _resume([]), _jd([]), load_taxonomy(), None, ClusterMatcher(load_taxonomy())
    )
    assert res.score == 0
    assert res.matched == []


# -- end to end (spec §1, product_requirements.md §7: < 3 s, no network) ----------


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_: object, **__: object) -> None:
        raise RuntimeError("network access attempted during free-path scoring")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_e2e_fixture_pair_scores_under_three_seconds(no_network: None) -> None:
    warm()  # model load and form matrix are a startup cost, not per-request
    resume, report = parse_resume_text((FIXTURES / "resume_clean.txt").read_text())
    jd = parse_job_description((FIXTURES / "jd_mle_llm.txt").read_text())

    t0 = time.perf_counter()
    result = score(resume, report, jd)
    elapsed = time.perf_counter() - t0

    assert elapsed < 3.0, elapsed
    assert isinstance(result, ScoreResult)
    assert 0 <= result.overall_score <= 100
    c = result.components
    assert result.overall_score == blend(
        c.semantic_match_score, c.taxonomy_overlap_score, c.parseability_score
    )
    assert result.matched_skills, "clean resume vs MLE JD should share clusters"
    assert result.requirement_matches
    assert all(i.status == "fail" for i in result.parseability_issues)
    assert result.disclaimer == DISCLAIMER


def test_disclaimer_scopes_score_to_alignment_only() -> None:
    assert "alignment" in DISCLAIMER
    assert "not a prediction of interview" in DISCLAIMER


def test_score_result_never_serialises_embeddings() -> None:
    resume, report = parse_resume_text((FIXTURES / "resume_clean.txt").read_text())
    jd = parse_job_description((FIXTURES / "jd_mle_llm.txt").read_text())
    dumped = score(resume, report, jd).model_dump_json()
    assert "embedding" not in dumped


def test_semantic_embeds_requirements_as_retrieval_queries() -> None:
    """bge-* models expect the query-side instruction for asymmetric matching."""
    seen: list[str] = []

    class Recording(FakeEmbedder):
        def embed(self, texts: list[str]) -> np.ndarray:
            seen.extend(texts)
            return super().embed(texts)

    semantic_match(["line a"], _reqs(("req a", "required")), Recording({}))
    assert "line a" in seen
    assert QUERY_PREFIX + "req a" in seen
    assert QUERY_PREFIX.startswith("Represent this sentence")
