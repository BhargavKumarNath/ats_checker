"""Compare Layer 2 embedding models and retrieval modes on tests/fixtures/retrieval_eval.json.

    uv run python scripts/bench/retrieval_bench.py [model ...]

Prints recall@5 and MRR for dense / sparse / hybrid per model, plus index build time and
mean query latency. Used in Phase 8 to pick the model and decide whether a reranker is needed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from atsc.core.embedding import LocalEmbedder
from atsc.deep.corpus import load_corpus
from atsc.deep.retrieval import CorpusIndex, evaluate

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS = ["BAAI/bge-small-en-v1.5", "BAAI/bge-base-en-v1.5"]


def main(models: list[str]) -> None:
    cases = json.loads((ROOT / "tests/fixtures/retrieval_eval.json").read_text())
    chunks = load_corpus()
    print(f"{len(chunks)} chunks, {len(cases)} labelled queries\n")
    print(f"{'model':28} {'mode':7} {'recall@5':>9} {'mrr':>6} {'build s':>8} {'q ms':>6}")
    for model in models:
        t0 = time.perf_counter()
        index = CorpusIndex(chunks, LocalEmbedder(model))
        build = time.perf_counter() - t0
        for mode in ("dense", "sparse", "hybrid"):
            t0 = time.perf_counter()
            m = evaluate(index, cases, k=5, mode=mode)  # type: ignore[arg-type]
            q_ms = 1000 * (time.perf_counter() - t0) / len(cases)
            row = f"{m['recall_at_k']:9.2f} {m['mrr']:6.2f} {build:8.2f} {q_ms:6.1f}"
            print(f"{model:28} {mode:7} {row}")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_MODELS)
