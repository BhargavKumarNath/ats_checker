"""Exact surface-form matching (gap_analysis_spec.md §1, method 1).

The four equivalence classes in product_requirements.md §6 must resolve to the
same cluster from either side with no string overlap between the two phrasings.
"""

import pytest

from atsc.core.matcher import ClusterMatcher
from atsc.core.taxonomy import load_taxonomy


@pytest.fixture(scope="module")
def matcher() -> ClusterMatcher:
    return ClusterMatcher(load_taxonomy())


def ids(matcher: ClusterMatcher, text: str) -> set[str]:
    return {m.cluster_id for m in matcher.match(text)}


@pytest.mark.parametrize(
    ("resume_phrase", "jd_phrase", "cluster_id"),
    [
        (
            "Fine-tuned Llama-3 with LoRA on 8 GPUs",
            "parameter-efficient fine-tuning experience",
            "peft",
        ),
        ("Built a RAG pipeline for support docs", "vector search over a knowledge base", "rag"),
        ("Trained CNNs in PyTorch", "experience with a deep learning framework", "dl_frameworks"),
        (
            "Applied 4-bit quantization to serve on edge",
            "model compression techniques",
            "quantization",
        ),
    ],
)
def test_required_equivalence_classes_resolve_to_same_cluster(
    matcher: ClusterMatcher, resume_phrase: str, jd_phrase: str, cluster_id: str
) -> None:
    assert cluster_id in ids(matcher, resume_phrase)
    assert cluster_id in ids(matcher, jd_phrase)


def test_matching_is_case_insensitive(matcher: ClusterMatcher) -> None:
    assert "dl_frameworks" in ids(matcher, "pytorch and TENSORFLOW")


def test_short_acronyms_respect_word_boundaries(matcher: ClusterMatcher) -> None:
    assert "rag" not in ids(matcher, "object storage and drag-and-drop tooling")
    assert "peft" not in ids(matcher, "the left adapter")


def test_hyphen_space_and_ampersand_variants_match(matcher: ClusterMatcher) -> None:
    assert "experiment_tracking" in ids(matcher, "logged runs to Weights and Biases")
    assert "experiment_tracking" in ids(matcher, "logged runs to Weights & Biases")
    assert "classical_ml" in ids(matcher, "models in scikit learn and xgboost")
    assert "classical_ml" in ids(matcher, "models in scikit-learn")


def test_match_carries_evidence_span(matcher: ClusterMatcher) -> None:
    text = "Deployed with vLLM behind Triton"
    m = next(m for m in matcher.match(text) if m.cluster_id == "llm_serving")
    assert text[m.start : m.end] == "vLLM"
    assert m.surface_form.lower() == "vllm"


def test_one_surface_form_may_belong_to_several_clusters(matcher: ClusterMatcher) -> None:
    # gap_analysis_spec.md §2 explicitly cross-references Airflow in two clusters.
    assert {"orchestration", "data_eng_tooling"} <= ids(matcher, "scheduled DAGs in Airflow")


def test_no_match_returns_empty(matcher: ClusterMatcher) -> None:
    assert matcher.match("Managed a team of baristas") == []
