"""Self-hosted embedding inference for the free path (ats_scoring_spec.md §2).

Runs on CPU via ONNX Runtime (fastembed). No PyTorch, no network call at
request time: the model is downloaded once (at image build) and loaded lazily
on first use. Callers depend on the `Embedder` Protocol, not on this class.

Model choice (Phase 3 benchmark, docs/build_plan.md §6): BAAI/bge-small-en-v1.5.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    from fastembed import TextEmbedding

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_DIM = 384


class Embedder(Protocol):
    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array with L2-normalised rows, one per input text."""
        ...


def _default_threads() -> int:
    return max(1, min(4, os.cpu_count() or 1))


class LocalEmbedder:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        threads: int | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.model_name = model_name
        self._threads = threads or _default_threads()
        self._cache_dir = cache_dir or _env_path("ATSC_MODEL_CACHE_DIR")
        self._model: TextEmbedding | None = None
        self._dim: int | None = None

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = int(self.embed(["dim probe"]).shape[1])
        return self._dim

    def _load(self) -> TextEmbedding:
        if self._model is None:
            from fastembed import TextEmbedding

            kwargs: dict[str, object] = {"threads": self._threads}
            if self._cache_dir is not None:
                kwargs["cache_dir"] = str(self._cache_dir)
            self._model = TextEmbedding(self.model_name, **kwargs)  # type: ignore[arg-type]
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim or DEFAULT_DIM), dtype=np.float32)
        vecs = np.asarray(list(self._load().embed(texts, batch_size=32)), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms


def _env_path(var: str) -> Path | None:
    v = os.environ.get(var)
    return Path(v) if v else None


@lru_cache(maxsize=1)
def get_default_embedder() -> LocalEmbedder:
    """Process-wide Layer 1 embedder. Model name from $ATSC_EMBEDDING_MODEL if set."""
    return LocalEmbedder(os.environ.get("ATSC_EMBEDDING_MODEL", DEFAULT_MODEL))
