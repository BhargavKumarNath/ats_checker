"""Embedding-similarity fallback (gap_analysis_spec.md §1, method 2).

Tested here against a controllable fake embedder so the behaviour is pinned
independently of the model chosen in Phase 3. Phase 3 adds a golden test with
the real model.
"""

import numpy as np

from atsc.core.matcher import ClusterMatcher
from atsc.core.taxonomy import load_taxonomy


class FakeEmbedder:
    """Maps a handful of known strings to fixed unit vectors; everything else is orthogonal."""

    dim = 4

    def __init__(self) -> None:
        self._table = {
            "low-rank adapter training": np.array([1.0, 0.0, 0.0, 0.0]),
            "lora": np.array([0.95, 0.31, 0.0, 0.0]),  # cos ≈ 0.95 to the query above
            "kubernetes": np.array([0.0, 0.0, 1.0, 0.0]),
        }

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim))
        for i, t in enumerate(texts):
            v = self._table.get(t.lower())
            if v is None:
                v = np.array([0.0, 0.0, 0.0, 1.0])
            out[i] = v / np.linalg.norm(v)
        return out


def test_unlisted_phrase_maps_to_cluster_when_similarity_exceeds_threshold() -> None:
    m = ClusterMatcher(load_taxonomy(), embedder=FakeEmbedder(), similarity_threshold=0.9)
    hits = m.match_phrases(["low-rank adapter training"])
    assert [(h.cluster_id, h.method) for h in hits] == [("peft", "embedding")]
    assert hits[0].similarity is not None and hits[0].similarity > 0.9


def test_unlisted_phrase_below_threshold_does_not_match() -> None:
    m = ClusterMatcher(load_taxonomy(), embedder=FakeEmbedder(), similarity_threshold=0.99)
    assert m.match_phrases(["low-rank adapter training"]) == []


def test_exact_match_wins_and_is_reported_as_exact() -> None:
    m = ClusterMatcher(load_taxonomy(), embedder=FakeEmbedder(), similarity_threshold=0.5)
    hits = m.match_phrases(["Kubernetes"])
    assert [(h.cluster_id, h.method) for h in hits] == [("containers_deploy", "exact")]


def test_without_embedder_fallback_is_skipped() -> None:
    m = ClusterMatcher(load_taxonomy())
    assert m.match_phrases(["low-rank adapter training"]) == []
