"""Phase 3 embedding model selection. Run: uv run python scripts/bench/embedding_bench.py

Measures, per candidate model (CPU, ONNX via fastembed):
  - load time, warm latency to embed a resume+JD-sized batch (80 lines)
  - separation quality on scripts/bench/pairs.json (AUC, mean pos/neg cosine)
  - embedding-fallback accuracy on unlisted phrasings vs taxonomy surface forms,
    and the cosine each hit lands at (informs the similarity threshold)
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

from atsc.core.taxonomy import load_taxonomy

CANDIDATES = [
    "BAAI/bge-small-en-v1.5",
    "sentence-transformers/all-MiniLM-L6-v2",
    "snowflake/snowflake-arctic-embed-s",
    "nomic-ai/nomic-embed-text-v1.5-Q",
]
BATCH_LINE = (
    "Designed and shipped a feature store on Spark and Delta Lake feeding 40 production models; "
    "cut training-data prep from 6 hours to 40 minutes."
)


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    return float(np.mean([p > n for p in pos for n in neg]))


def main() -> None:
    data = json.loads((Path(__file__).parent / "pairs.json").read_text())
    pairs = data["pairs"]
    unlisted = {k: v for k, v in data["unlisted_phrasings"].items() if not k.startswith("_")}
    tax = load_taxonomy()
    forms = [(c.cluster_id, f) for c in tax.clusters for f in c.surface_forms]

    only = sys.argv[1:]
    for name in CANDIDATES:
        if only and name not in only:
            continue
        t0 = time.perf_counter()
        model = TextEmbedding(name, threads=4)
        list(model.embed(["warm up"]))
        load_s = time.perf_counter() - t0

        batch = [BATCH_LINE] * 80
        t0 = time.perf_counter()
        for _ in range(3):
            list(model.embed(batch, batch_size=32))
        lat_ms = (time.perf_counter() - t0) / 3 * 1000

        a = np.array(list(model.embed([p[0] for p in pairs])))
        b = np.array(list(model.embed([p[1] for p in pairs])))
        a /= np.linalg.norm(a, axis=1, keepdims=True)
        b /= np.linalg.norm(b, axis=1, keepdims=True)
        sims = np.sum(a * b, axis=1)
        labels = np.array([p[2] for p in pairs])
        pos, neg = sims[labels == 1], sims[labels == 0]

        fm = np.array(list(model.embed([f for _, f in forms])))
        fm /= np.linalg.norm(fm, axis=1, keepdims=True)
        q = np.array(list(model.embed(list(unlisted))))
        q /= np.linalg.norm(q, axis=1, keepdims=True)
        s = q @ fm.T
        hits = []
        for i, expected in enumerate(unlisted.values()):
            j = int(np.argmax(s[i]))
            hits.append((expected, forms[j][0], forms[j][1], float(s[i, j])))
        correct = sum(1 for e, got, _, _ in hits if e == got)

        print(f"\n=== {name}")
        print(f"load {load_s:.2f}s | 80-line batch {lat_ms:.0f} ms | dim {a.shape[1]}")
        print(
            f"pairs: AUC {auc(pos, neg):.3f} | pos mean {pos.mean():.3f} min {pos.min():.3f}"
            f" | neg mean {neg.mean():.3f} max {neg.max():.3f}"
        )
        print(f"unlisted phrasings: {correct}/{len(hits)} correct")
        for e, got, form, sim in hits:
            flag = "ok " if e == got else "BAD"
            print(f"  {flag} expected={e:22s} got={got:22s} via {form!r:40s} cos={sim:.3f}")


if __name__ == "__main__":
    main()
