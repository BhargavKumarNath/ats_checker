"""Deterministic readability / keyword-density metric behind DeepReport.readability_flag."""

from atsc.deep.readability import keyword_density, readability_flag, reading_ease

ORIGINAL = "Built a RAG pipeline over 2M internal documents using pgvector and LangChain."
CLEAN_REWRITE = (
    "Built a retrieval-augmented generation pipeline over 2M internal documents with "
    "pgvector and LangChain, serving answers with page-level citations."
)
STUFFED_REWRITE = (
    "RAG retrieval-augmented generation vector search semantic search LangChain LlamaIndex "
    "pgvector Pinecone embeddings LLM pipeline over 2M documents."
)


def test_reading_ease_is_lower_for_dense_text() -> None:
    assert reading_ease("The cat sat on the mat.") > reading_ease(
        "Parameter-efficient fine-tuning methodologies substantially outperform baselines."
    )


def test_keyword_density_counts_taxonomy_mentions_per_word() -> None:
    assert keyword_density(STUFFED_REWRITE) > keyword_density(ORIGINAL) > 0
    assert keyword_density("We had a nice picnic by the lake.") == 0


def test_flag_is_false_for_a_clean_rewrite() -> None:
    assert readability_flag(ORIGINAL, CLEAN_REWRITE) is False


def test_flag_is_true_for_keyword_stuffing() -> None:
    assert readability_flag(ORIGINAL, STUFFED_REWRITE) is True


def test_flag_is_false_when_density_does_not_rise() -> None:
    assert readability_flag(STUFFED_REWRITE, ORIGINAL) is False
