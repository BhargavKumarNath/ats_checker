"""Embedding interface. The real self-hosted implementation arrives in Phase 3.

Everything that needs vectors depends on this Protocol, not on a model library,
so the free path can be tested without loading a model and so the model can be
swapped without touching callers.
"""

from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float array with L2-normalised rows, one per input text."""
        ...
