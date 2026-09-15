"""Layer 2 retrieval corpus (technical_architecture.md §5, build_plan.md §3 "vector store")."""

from pathlib import Path

import pytest

from atsc.core.models import Platform
from atsc.core.taxonomy import load_taxonomy
from atsc.deep.corpus import Chunk, CorpusError, load_corpus


@pytest.fixture(scope="module")
def chunks() -> list[Chunk]:
    return load_corpus()


def test_corpus_loads_with_a_useful_size(chunks: list[Chunk]) -> None:
    assert len(chunks) >= 120


def test_chunk_ids_are_unique(chunks: list[Chunk]) -> None:
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_every_cluster_has_an_equivalence_chunk_and_strong_bullets(chunks: list[Chunk]) -> None:
    tax = load_taxonomy()
    for cluster in tax.clusters:
        mine = [c for c in chunks if cluster.cluster_id in c.cluster_ids]
        equiv = [c for c in mine if c.kind == "equivalence"]
        strong = [c for c in mine if c.kind == "strong_bullet"]
        assert len(equiv) == 1, cluster.cluster_id
        assert len(strong) >= 2, cluster.cluster_id
        assert cluster.canonical_name in equiv[0].context


def test_every_platform_has_quirks(chunks: list[Chunk]) -> None:
    for p in Platform:
        assert (
            sum(1 for c in chunks if c.kind == "platform_quirk" and c.platform == p.value) >= 3
        ), p


def test_rewrite_pairs_carry_weak_strong_and_why(chunks: list[Chunk]) -> None:
    pairs = [c for c in chunks if c.kind == "rewrite_pair"]
    assert len(pairs) >= 10
    for c in pairs:
        assert "Weak:" in c.text and "Stronger:" in c.text
        assert c.why


def test_guidance_covers_keyword_density(chunks: list[Chunk]) -> None:
    guidance = [c for c in chunks if c.kind == "guidance"]
    assert len(guidance) >= 8
    assert any("keyword" in c.text.lower() and "readab" in c.text.lower() for c in guidance)


def test_embed_text_is_context_then_text(chunks: list[Chunk]) -> None:
    c = chunks[0]
    assert c.embed_text.startswith(c.context)
    assert c.embed_text.endswith(c.text)


def test_unknown_cluster_id_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "bullets").mkdir()
    (tmp_path / "bullets" / "x.yaml").write_text(
        "category: LLM / GenAI\nstrong:\n"
        "  - cluster_id: not_a_cluster\n    text: Built things.\n    why: none\n"
    )
    (tmp_path / "platforms.yaml").write_text("[]\n")
    (tmp_path / "guidance.yaml").write_text("[]\n")
    with pytest.raises(CorpusError, match="not_a_cluster"):
        load_corpus(tmp_path)


def test_deep_embedding_model_is_configurable() -> None:
    from atsc.config import Settings

    assert Settings().deep_embedding_model == "BAAI/bge-base-en-v1.5"
    assert Settings(deep_embedding_model="x/y").deep_embedding_model == "x/y"
