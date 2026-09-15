"""Hybrid retrieval over the Layer 2 corpus (build_plan.md §3 "vector store").

In-process only: a dense matrix from the self-hosted embedder plus a BM25 index,
fused by reciprocal rank fusion. No vector database, no metered API. The corpus is
a few hundred chunks; re-evaluate the design above ~50k.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import numpy as np
from rank_bm25 import BM25Okapi

from atsc.core.embedding import Embedder, LocalEmbedder
from atsc.core.scoring import QUERY_PREFIX
from atsc.deep.corpus import Chunk, ChunkKind, load_corpus

Mode = Literal["hybrid", "dense", "sparse"]

RRF_K = 60  # standard constant; rank 1 → 1/61
CANDIDATES = 50  # per retriever before fusion

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Hit:
    chunk: Chunk
    score: float
    dense_rank: int | None
    sparse_rank: int | None


class CorpusIndex:
    def __init__(
        self, chunks: Sequence[Chunk], embedder: Embedder, *, query_prefix: str = QUERY_PREFIX
    ) -> None:
        self.chunks = list(chunks)
        self._embedder = embedder
        self._prefix = query_prefix
        self._matrix = embedder.embed([c.embed_text for c in self.chunks])
        self._bm25 = BM25Okapi([tokenize(c.embed_text) for c in self.chunks])

    def _candidates(
        self,
        kinds: Iterable[ChunkKind] | None,
        cluster_ids: Iterable[str] | None,
        platform: str | None,
    ) -> np.ndarray:
        kinds_set = set(kinds) if kinds is not None else None
        clusters_set = set(cluster_ids) if cluster_ids is not None else None

        def keep(c: Chunk) -> bool:
            if kinds_set is not None and c.kind not in kinds_set:
                return False
            if clusters_set is not None and not clusters_set.intersection(c.cluster_ids):
                return False
            return platform is None or c.platform == platform

        return np.array([keep(c) for c in self.chunks], dtype=bool)

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        mode: Mode = "hybrid",
        kinds: Iterable[ChunkKind] | None = None,
        cluster_ids: Iterable[str] | None = None,
        platform: str | None = None,
    ) -> list[Hit]:
        mask = self._candidates(kinds, cluster_ids, platform)
        idx = np.flatnonzero(mask)
        if idx.size == 0:
            return []

        dense_rank: dict[int, int] = {}
        sparse_rank: dict[int, int] = {}
        if mode in ("hybrid", "dense"):
            q = self._embedder.embed([self._prefix + query])[0]
            sims = self._matrix[idx] @ q
            pos = sims > 0  # same rule as the sparse side: no rank for a zero-signal document
            order = idx[pos][np.argsort(-sims[pos], kind="stable")][:CANDIDATES]
            dense_rank = {int(i): r + 1 for r, i in enumerate(order)}
        if mode in ("hybrid", "sparse"):
            scores = np.asarray(self._bm25.get_scores(tokenize(query)))[idx]
            keep = idx[scores > 0]
            order = keep[np.argsort(-scores[scores > 0], kind="stable")][:CANDIDATES]
            sparse_rank = {int(i): r + 1 for r, i in enumerate(order)}

        fused: dict[int, float] = {}
        for i, r in dense_rank.items():
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r)
        for i, r in sparse_rank.items():
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r)
        ranked = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        return [
            Hit(self.chunks[i], score, dense_rank.get(i), sparse_rank.get(i)) for i, score in ranked
        ]


def _satisfies(chunk: Chunk, expect: dict[str, Any]) -> bool:
    if "chunk_id" in expect and chunk.chunk_id != expect["chunk_id"]:
        return False
    if "kind" in expect and chunk.kind != expect["kind"]:
        return False
    if "cluster_id" in expect and expect["cluster_id"] not in chunk.cluster_ids:
        return False
    return not ("platform" in expect and chunk.platform != expect["platform"])


def evaluate(
    index: CorpusIndex, cases: list[dict[str, Any]], *, k: int = 5, mode: Mode = "hybrid"
) -> dict[str, float]:
    """recall@k (any satisfying chunk in the top k) and MRR over labelled queries."""
    hits = 0
    rr = 0.0
    for case in cases:
        results = index.search(case["query"], k=k, mode=mode)
        for rank, h in enumerate(results, start=1):
            if _satisfies(h.chunk, case["expect"]):
                hits += 1
                rr += 1.0 / rank
                break
    n = max(1, len(cases))
    return {"recall_at_k": hits / n, "mrr": rr / n, "n": float(len(cases))}


@lru_cache(maxsize=1)
def get_default_index() -> CorpusIndex:
    """Process-wide index over the default corpus with the Layer 2 embedding model."""
    from atsc.config import get_settings

    return CorpusIndex(load_corpus(), LocalEmbedder(get_settings().deep_embedding_model))
