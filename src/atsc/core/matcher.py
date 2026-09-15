"""Maps text spans to taxonomy clusters (gap_analysis_spec.md §1).

Two methods, in priority order:
1. Exact surface-form match: case-insensitive, tolerant of hyphen/space/"&"
   variants, anchored on word boundaries so short acronyms (RAG, DPO, TGI)
   do not fire inside longer words.
2. Embedding similarity above a threshold, for phrasings not in the surface
   list. Only used by `match_phrases`, only when an Embedder is supplied, and
   only for phrases with no exact hit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import numpy as np

from atsc.core.embedding import Embedder
from atsc.core.taxonomy import Taxonomy

MatchMethod = Literal["exact", "embedding"]

_BOUNDARY_L = r"(?<![A-Za-z0-9])"
_BOUNDARY_R = r"(?![A-Za-z0-9])"
_JOINER = r"[\s\-_]*"


def _surface_form_pattern(form: str) -> re.Pattern[str]:
    tokens = [t for t in re.split(r"[\s\-_]+", form.strip()) if t]
    parts = []
    for tok in tokens:
        if tok.lower() in {"&", "and"}:
            parts.append(r"(?:&|and)")
        else:
            parts.append(re.escape(tok))
    return re.compile(_BOUNDARY_L + _JOINER.join(parts) + _BOUNDARY_R, re.IGNORECASE)


@dataclass(frozen=True)
class Match:
    cluster_id: str
    surface_form: str
    start: int
    end: int


@dataclass(frozen=True)
class PhraseMatch:
    phrase_index: int
    phrase: str
    cluster_id: str
    surface_form: str
    method: MatchMethod
    similarity: float | None = None


class ClusterMatcher:
    def __init__(
        self,
        taxonomy: Taxonomy,
        embedder: Embedder | None = None,
        similarity_threshold: float = 0.80,
    ) -> None:
        self.taxonomy = taxonomy
        self._embedder = embedder
        self._threshold = similarity_threshold
        self._patterns: list[tuple[str, str, re.Pattern[str]]] = [
            (c.cluster_id, form, _surface_form_pattern(form))
            for c in taxonomy.clusters
            for form in c.surface_forms
        ]
        # Lazily built: one row per surface form, aligned with _form_index.
        self._form_matrix: np.ndarray | None = None
        self._form_index: list[tuple[str, str]] = [
            (c.cluster_id, form) for c in taxonomy.clusters for form in c.surface_forms
        ]

    # -- method 1: exact -----------------------------------------------------

    def match(self, text: str) -> list[Match]:
        raw: list[Match] = []
        for cluster_id, form, pattern in self._patterns:
            for m in pattern.finditer(text):
                raw.append(Match(cluster_id, form, m.start(), m.end()))
        return _drop_nested(raw)

    # -- method 2: embedding fallback ---------------------------------------

    def match_phrases(self, phrases: list[str]) -> list[PhraseMatch]:
        hits: list[PhraseMatch] = []
        unresolved: list[int] = []
        for i, phrase in enumerate(phrases):
            exact = self.match(phrase)
            if exact:
                seen: set[str] = set()
                for m in exact:
                    if m.cluster_id not in seen:
                        seen.add(m.cluster_id)
                        hits.append(PhraseMatch(i, phrase, m.cluster_id, m.surface_form, "exact"))
            else:
                unresolved.append(i)

        if unresolved and self._embedder is not None:
            hits.extend(self._embedding_fallback(phrases, unresolved))
        hits.sort(key=lambda h: h.phrase_index)
        return hits

    def _embedding_fallback(self, phrases: list[str], indices: list[int]) -> list[PhraseMatch]:
        assert self._embedder is not None
        if self._form_matrix is None:
            self._form_matrix = self._embedder.embed([f for _, f in self._form_index])
        queries = self._embedder.embed([phrases[i] for i in indices])
        sims = queries @ self._form_matrix.T  # rows already L2-normalised → cosine
        out: list[PhraseMatch] = []
        for row, i in enumerate(indices):
            best_per_cluster: dict[str, tuple[float, str]] = {}
            for col, (cluster_id, form) in enumerate(self._form_index):
                s = float(sims[row, col])
                if s >= self._threshold and s > best_per_cluster.get(cluster_id, (-1.0, ""))[0]:
                    best_per_cluster[cluster_id] = (s, form)
            for cluster_id, (s, form) in best_per_cluster.items():
                out.append(PhraseMatch(i, phrases[i], cluster_id, form, "embedding", s))
        return out


def _drop_nested(matches: list[Match]) -> list[Match]:
    """Remove a match fully contained in a longer match of the same cluster."""
    matches = sorted(matches, key=lambda m: (m.cluster_id, m.start, -(m.end - m.start)))
    kept: list[Match] = []
    for m in matches:
        if (
            kept
            and kept[-1].cluster_id == m.cluster_id
            and kept[-1].start <= m.start
            and m.end <= kept[-1].end
        ):
            continue
        kept.append(m)
    kept.sort(key=lambda m: (m.start, m.cluster_id))
    return kept
