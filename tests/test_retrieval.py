"""Hybrid retrieval over the Layer 2 corpus: RRF fusion, filters, labelled eval."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from atsc.deep.corpus import Chunk, load_corpus
from atsc.deep.retrieval import CorpusIndex, evaluate

FIXTURES = Path(__file__).parent / "fixtures"


class FakeEmbedder:
    """Dense similarity is driven by a hand-set table so fusion can be checked exactly."""

    dim = 3

    def __init__(self, table: dict[str, list[float]]) -> None:
        self._table = {k: np.array(v, dtype=np.float32) for k, v in table.items()}

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            key = next((k for k in self._table if k in t), None)
            v = self._table[key] if key else np.array([0, 0, 1], dtype=np.float32)
            out[i] = v / np.linalg.norm(v)
        return out


def _chunk(cid: str, text: str, **kw: object) -> Chunk:
    base: dict[str, object] = {
        "chunk_id": cid,
        "kind": "guidance",
        "text": text,
        "context": "ctx",
        "cluster_ids": [],
        "platform": None,
        "role_tracks": [],
    }
    base.update(kw)
    return Chunk(**base)  # type: ignore[arg-type]


CHUNKS = [
    _chunk("both", "zebra habitat facts", kind="strong_bullet", cluster_ids=["rag"]),
    _chunk("dense_only", "unrelated words entirely", kind="strong_bullet", cluster_ids=["peft"]),
    _chunk("sparse_only", "zebra zebra zebra stripes", kind="platform_quirk", platform="workday"),
    _chunk("neither", "nothing to see", kind="guidance"),
    # Padding so the query term sits in under half the documents: rank_bm25 floors the IDF
    # of a term found in half or more of a corpus, which would empty the sparse list.
    _chunk("pad1", "lorem ipsum dolor", kind="guidance"),
    _chunk("pad2", "sit amet consectetur", kind="guidance"),
    _chunk("pad3", "adipiscing elit sed", kind="guidance"),
]
TABLE = {
    "QUERY": [1, 0, 0],
    "zebra habitat facts": [0.9, 0.1, 0],  # both: strong dense
    "unrelated words entirely": [0.95, 0.05, 0],  # dense_only: strongest dense, no lexical overlap
    "zebra zebra zebra stripes": [0, 1, 0],  # sparse_only: lexical only
}


def test_hybrid_ranks_chunk_present_in_both_lists_first() -> None:
    index = CorpusIndex(CHUNKS, FakeEmbedder(TABLE), query_prefix="QUERY ")
    hits = index.search("zebra", k=4)
    assert hits[0].chunk.chunk_id == "both"
    assert {h.chunk.chunk_id for h in hits[:3]} == {"both", "dense_only", "sparse_only"}
    assert hits[0].dense_rank is not None and hits[0].sparse_rank is not None


def test_dense_and_sparse_modes_are_separable() -> None:
    index = CorpusIndex(CHUNKS, FakeEmbedder(TABLE), query_prefix="QUERY ")
    assert index.search("zebra", k=1, mode="dense")[0].chunk.chunk_id == "dense_only"
    assert index.search("zebra", k=1, mode="sparse")[0].chunk.chunk_id == "sparse_only"


def test_filters_restrict_candidates() -> None:
    index = CorpusIndex(CHUNKS, FakeEmbedder(TABLE), query_prefix="QUERY ")
    assert [h.chunk.chunk_id for h in index.search("zebra", kinds=["platform_quirk"])] == [
        "sparse_only"
    ]
    assert [h.chunk.chunk_id for h in index.search("zebra", cluster_ids=["peft"])] == ["dense_only"]
    assert [h.chunk.chunk_id for h in index.search("zebra", platform="workday")] == ["sparse_only"]
    assert index.search("zebra", kinds=["rewrite_pair"]) == []


def test_k_limits_results() -> None:
    index = CorpusIndex(CHUNKS, FakeEmbedder(TABLE), query_prefix="QUERY ")
    assert len(index.search("zebra", k=2)) == 2


# -- labelled eval with the real model (build_plan.md Phase 8: decide reranker from numbers) --


@pytest.fixture(scope="module")
def real_index() -> CorpusIndex:
    from atsc.deep.retrieval import get_default_index

    return get_default_index()


def test_hybrid_retrieval_meets_eval_thresholds(real_index: CorpusIndex) -> None:
    cases = json.loads((FIXTURES / "retrieval_eval.json").read_text())
    assert len(cases) >= 20
    metrics = evaluate(real_index, cases, k=5, mode="hybrid")
    assert metrics["recall_at_k"] >= 0.85, metrics
    assert metrics["mrr"] >= 0.6, metrics


def test_corpus_index_covers_whole_corpus(real_index: CorpusIndex) -> None:
    assert len(real_index.chunks) == len(load_corpus())
