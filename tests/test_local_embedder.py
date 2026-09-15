"""Self-hosted embedding inference (ats_scoring_spec.md §2, technical_architecture.md §3).

These tests load the real Layer 1 model. It is small (~67MB) and cached after
first download.
"""

import importlib.util
import subprocess
import sys
import time

import numpy as np
import pytest

from atsc.core.embedding import LocalEmbedder, get_default_embedder


@pytest.fixture(scope="module")
def embedder() -> LocalEmbedder:
    return get_default_embedder()


def test_returns_one_unit_vector_per_text(embedder: LocalEmbedder) -> None:
    v = embedder.embed(["fine-tuned a transformer", "managed a coffee shop"])
    assert v.shape == (2, embedder.dim)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5)


def test_empty_input_returns_empty_matrix(embedder: LocalEmbedder) -> None:
    v = embedder.embed([])
    assert v.shape == (0, embedder.dim)


def test_is_deterministic(embedder: LocalEmbedder) -> None:
    a = embedder.embed(["distributed training on 32 GPUs"])
    b = embedder.embed(["distributed training on 32 GPUs"])
    assert np.allclose(a, b)


def test_related_lines_are_closer_than_unrelated(embedder: LocalEmbedder) -> None:
    v = embedder.embed(
        [
            "Fine-tuned Llama-3 with low-rank adapters",
            "Experience with parameter-efficient fine-tuning of LLMs",
            "Managed a team of eight baristas",
        ]
    )
    assert v[0] @ v[1] > v[0] @ v[2] + 0.1


def test_default_embedder_is_a_singleton() -> None:
    assert get_default_embedder() is get_default_embedder()


def test_resume_plus_jd_sized_batch_embeds_inside_budget(embedder: LocalEmbedder) -> None:
    # 60 resume bullets + 20 JD requirement lines. Budget is generous for CI;
    # locally this is ~0.3 s. The whole free request must stay under 3 s.
    line = "Built and deployed gradient-boosted churn models on Spark, lifting retention 4%."
    embedder.embed([line])  # warm
    t0 = time.perf_counter()
    embedder.embed([line] * 80)
    assert time.perf_counter() - t0 < 1.5


def test_embedding_module_does_not_pull_in_torch() -> None:
    # Dependency-footprint guard: the free-tier image must stay ONNX-only.
    assert importlib.util.find_spec("torch") is None
    code = "import sys, atsc.core.embedding; print('torch' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
