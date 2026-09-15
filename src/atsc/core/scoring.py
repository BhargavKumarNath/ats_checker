"""Layer 1 scoring engine (ats_scoring_spec.md §2-6, data_model.md §5).

Three components, none of which touch a metered API:
1. semantic match: line-level cosine, self-hosted embeddings (§2)
2. taxonomy overlap: deterministic cluster lookup with role-track weights (§3)
3. parseability: penalties over the structural report (§4, build_plan.md interp. 8)

Constants marked "tunable" are starting hypotheses per spec §5 and are meant to be
re-fitted once labelled evaluation data exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from atsc.core.embedding import Embedder, get_default_embedder
from atsc.core.matcher import ClusterMatcher
from atsc.core.models import (
    DISCLAIMER,
    MatchedSkill,
    ParseabilityReport,
    ParsedJobDescription,
    ParsedResume,
    Platform,
    Requirement,
    RequirementMatch,
    RequirementType,
    RoleTrack,
    ScoreComponents,
    ScoreResult,
    Severity,
    UnmatchedSkill,
)
from atsc.core.taxonomy import Taxonomy, load_taxonomy

__all__ = [
    "DISCLAIMER",
    "QUERY_PREFIX",
    "OverlapResult",
    "blend",
    "parseability_score",
    "score",
    "semantic_match",
    "taxonomy_overlap",
    "warm",
]

# -- tunable constants ---------------------------------------------------------------

WEIGHT_SEMANTIC = 0.45  # spec §5
WEIGHT_TAXONOMY = 0.35
WEIGHT_PARSEABILITY = 0.20

# bge-* models are trained with this instruction on the query side for asymmetric retrieval
# (short query vs passage). JD requirements are the queries; resume lines are the passages.
# On the Phase 3 pairs it lifts the correct best-line pick rate visibly (build_plan.md Phase 6).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Cosine → 0-100 linear rescale (interp. 4). Calibrated on scripts/bench/pairs.json with the
# query prefix applied: positives mean 0.694, negatives mean 0.514 on bge-small-en-v1.5;
# these constants map them to ≈64 and ≈15.
COSINE_FLOOR = 0.47
COSINE_CEILING = 0.82

# Required vs preferred (job_description_analysis.md §4: preferred "weighted lower").
REQUIREMENT_WEIGHT: dict[RequirementType, float] = {"required": 1.0, "preferred": 0.5}

# Penalty per failed check by severity on the selected platform (interp. 8).
SEVERITY_PENALTY: dict[Severity, int] = {
    Severity.HIGH: 25,
    Severity.MEDIUM: 15,
    Severity.LOW: 5,
    Severity.NA: 0,
}
_SEVERITY_RANK = {Severity.NA: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}


def _clamp(x: float) -> int:
    return int(min(100, max(0, round(x))))


# -- component 1: semantic match ------------------------------------------------------


def _rescale(cosine: float) -> float:
    return min(1.0, max(0.0, (cosine - COSINE_FLOOR) / (COSINE_CEILING - COSINE_FLOOR)))


def semantic_match(
    resume_lines: list[str], requirements: list[Requirement], embedder: Embedder
) -> tuple[int, list[RequirementMatch]]:
    """For each JD requirement, the best-matching resume line; weighted mean of rescaled cosines."""
    if not resume_lines or not requirements:
        return 0, [
            RequirementMatch(
                jd_text=r.raw_text,
                requirement_type=r.requirement_type,
                resume_line=None,
                similarity=0.0,
                score=0,
            )
            for r in requirements
        ]
    line_vecs = embedder.embed(resume_lines)
    req_vecs = embedder.embed([QUERY_PREFIX + r.raw_text for r in requirements])
    sims = req_vecs @ line_vecs.T
    matches: list[RequirementMatch] = []
    weighted = 0.0
    total = 0.0
    for i, req in enumerate(requirements):
        j = int(np.argmax(sims[i]))
        cos = float(sims[i, j])
        line_score = _rescale(cos)
        w = REQUIREMENT_WEIGHT[req.requirement_type]
        weighted += w * line_score
        total += w
        matches.append(
            RequirementMatch(
                jd_text=req.raw_text,
                requirement_type=req.requirement_type,
                resume_line=resume_lines[j],
                similarity=cos,
                score=_clamp(line_score * 100),
            )
        )
    return _clamp(100 * weighted / total), matches


# -- component 2: taxonomy overlap ----------------------------------------------------


@dataclass
class OverlapResult:
    score: int
    matched: list[MatchedSkill] = field(default_factory=list)
    unmatched_required: list[UnmatchedSkill] = field(default_factory=list)
    unmatched_preferred: list[UnmatchedSkill] = field(default_factory=list)


def _resume_lines(resume: ParsedResume) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for entry in resume.work:
        out.extend((b.raw_text, b.matched_clusters) for b in entry.bullets)
    for project in resume.projects:
        out.extend((b.raw_text, b.matched_clusters) for b in project.bullets)
    out.extend((s.raw_text, s.matched_clusters) for s in resume.skills)
    return out


def _resume_clusters(resume: ParsedResume, matcher: ClusterMatcher) -> dict[str, str]:
    """cluster_id → first resume line naming it. Unmatched skill phrases get the fallback."""
    evidence: dict[str, str] = {}
    for text, clusters in _resume_lines(resume):
        for cid in clusters:
            evidence.setdefault(cid, text)
    unresolved = [s.raw_text for s in resume.skills if not s.matched_clusters]
    for hit in matcher.match_phrases(unresolved):
        evidence.setdefault(hit.cluster_id, hit.phrase)
    return evidence


def _jd_clusters(jd: ParsedJobDescription) -> dict[str, tuple[RequirementType, str]]:
    """cluster_id → (strongest requirement type, first JD line naming it)."""
    out: dict[str, tuple[RequirementType, str]] = {}
    for req in jd.requirements:
        for cid in req.matched_clusters:
            if cid not in out:
                out[cid] = (req.requirement_type, req.raw_text)
            elif out[cid][0] == "preferred" and req.requirement_type == "required":
                out[cid] = ("required", req.raw_text)
    return out


def taxonomy_overlap(
    resume: ParsedResume,
    jd: ParsedJobDescription,
    taxonomy: Taxonomy,
    role_track: RoleTrack | None,
    matcher: ClusterMatcher,
) -> OverlapResult:
    jd_clusters = _jd_clusters(jd)
    if not jd_clusters:
        return OverlapResult(score=0)
    resume_evidence = _resume_clusters(resume, matcher)

    def weight(cid: str, kind: RequirementType) -> float:
        track_w = 1.0 if role_track is None else taxonomy.by_id[cid].role_track_weight[role_track]
        return track_w * REQUIREMENT_WEIGHT[kind]

    ordered = sorted(jd_clusters.items(), key=lambda kv: (-weight(kv[0], kv[1][0]), kv[0]))
    result = OverlapResult(score=0)
    got = 0.0
    total = 0.0
    for cid, (kind, jd_text) in ordered:
        w = weight(cid, kind)
        total += w
        name = taxonomy.by_id[cid].canonical_name
        if cid in resume_evidence:
            got += w
            result.matched.append(
                MatchedSkill(
                    cluster_id=cid,
                    canonical_name=name,
                    resume_evidence=resume_evidence[cid],
                    jd_evidence=jd_text,
                )
            )
        else:
            target = result.unmatched_required if kind == "required" else result.unmatched_preferred
            target.append(UnmatchedSkill(cluster_id=cid, canonical_name=name, jd_evidence=jd_text))
    result.score = _clamp(100 * got / total) if total else 0
    return result


# -- component 3: parseability --------------------------------------------------------


def _severity(check_severity: dict[Platform, Severity], platform: Platform | None) -> Severity:
    if platform is not None:
        return check_severity[platform]
    return max(check_severity.values(), key=lambda s: _SEVERITY_RANK[s])


def parseability_score(report: ParseabilityReport, platform: Platform | None) -> int:
    penalty = sum(
        SEVERITY_PENALTY[_severity(check.platform_severity, platform)] for check in report.failed
    )
    return max(0, 100 - penalty)


# -- blend ------------------------------------------------------------------------------


def blend(semantic: int, taxonomy: int, parseability: int) -> int:
    return _clamp(
        WEIGHT_SEMANTIC * semantic + WEIGHT_TAXONOMY * taxonomy + WEIGHT_PARSEABILITY * parseability
    )


# -- entry point ------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _default_matcher() -> ClusterMatcher:
    """Exact + embedding-fallback matcher for the overlap component (interp. 2)."""
    return ClusterMatcher(load_taxonomy(), embedder=get_default_embedder())


def warm() -> None:
    """Load the embedding model and the surface-form matrix so the first request pays nothing."""
    _default_matcher().match_phrases(["warm up probe phrase"])


def _semantic_lines(resume: ParsedResume) -> list[str]:
    lines = [t for t, _ in _resume_lines(resume)]
    if lines:
        return lines
    return [ln for ln in resume.raw_text.split("\n") if len(ln.split()) >= 3]


def score(
    resume: ParsedResume,
    report: ParseabilityReport,
    jd: ParsedJobDescription,
    *,
    role_track: RoleTrack | None = None,
    platform: Platform | None = None,
    embedder: Embedder | None = None,
    matcher: ClusterMatcher | None = None,
) -> ScoreResult:
    if matcher is None:
        matcher = ClusterMatcher(load_taxonomy(), embedder) if embedder else _default_matcher()
    embedder = embedder or get_default_embedder()
    if role_track is None and isinstance(jd.role_track_signal, RoleTrack):
        role_track = jd.role_track_signal

    semantic, req_matches = semantic_match(_semantic_lines(resume), jd.requirements, embedder)
    overlap = taxonomy_overlap(resume, jd, matcher.taxonomy, role_track, matcher)
    parse = parseability_score(report, platform)

    return ScoreResult(
        overall_score=blend(semantic, overlap.score, parse),
        components=ScoreComponents(
            semantic_match_score=semantic,
            taxonomy_overlap_score=overlap.score,
            parseability_score=parse,
        ),
        matched_skills=overlap.matched,
        unmatched_required_skills=overlap.unmatched_required,
        unmatched_preferred_skills=overlap.unmatched_preferred,
        requirement_matches=req_matches,
        parseability_issues=report.failed,
        role_track=role_track,
        platform=platform,
    )
