"""The taxonomy is a versioned dataset (gap_analysis_spec.md, data_model.md §4)."""

import pytest

from atsc.core.models import Category, RoleTrack
from atsc.core.taxonomy import Taxonomy, load_taxonomy

EXPECTED_CATEGORIES = {
    Category.CORE_ML,
    Category.LLM_GENAI,
    Category.INFERENCE_SERVING,
    Category.MLOPS,
    Category.EVAL_SAFETY,
    Category.CLASSICAL_DS,
}


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    return load_taxonomy()


def test_all_six_categories_are_present(taxonomy: Taxonomy) -> None:
    assert {c.category for c in taxonomy.clusters} == EXPECTED_CATEGORIES


def test_seed_clusters_from_spec_are_present(taxonomy: Taxonomy) -> None:
    for cid in (
        "dl_frameworks",
        "peft",
        "rag",
        "vector_databases",
        "quantization",
        "experiment_tracking",
    ):
        assert cid in taxonomy.by_id, cid


def test_cluster_ids_are_unique(taxonomy: Taxonomy) -> None:
    ids = [c.cluster_id for c in taxonomy.clusters]
    assert len(ids) == len(set(ids))


def test_every_cluster_has_at_least_two_surface_forms(taxonomy: Taxonomy) -> None:
    thin = [c.cluster_id for c in taxonomy.clusters if len(c.surface_forms) < 2]
    assert thin == []


def test_role_track_weights_default_from_category_table(taxonomy: Taxonomy) -> None:
    # gap_analysis_spec.md §3: Inference & Serving is High for MLE, Low for Data Scientist.
    # build_plan.md interpretation 3: High=1.0, Medium=0.6, Low=0.3.
    c = taxonomy.by_id["quantization"]
    assert c.role_track_weight[RoleTrack.MLE] == 1.0
    assert c.role_track_weight[RoleTrack.DATA_SCIENTIST] == 0.3
    assert c.role_track_weight[RoleTrack.DATA_ENGINEER] == 0.6


def test_every_cluster_has_a_weight_for_every_track(taxonomy: Taxonomy) -> None:
    for c in taxonomy.clusters:
        assert set(c.role_track_weight) == set(RoleTrack), c.cluster_id
        assert all(0.0 <= w <= 1.0 for w in c.role_track_weight.values()), c.cluster_id


def test_surface_forms_within_a_cluster_are_unique_after_normalisation(taxonomy: Taxonomy) -> None:
    for c in taxonomy.clusters:
        norm = [s.lower().strip() for s in c.surface_forms]
        assert len(norm) == len(set(norm)), c.cluster_id


def test_per_cluster_weight_override_beats_category_default(taxonomy: Taxonomy) -> None:
    assert taxonomy.by_id["python_data_stack"].role_track_weight[RoleTrack.MLE] == 1.0
    assert taxonomy.by_id["classical_ml"].role_track_weight[RoleTrack.MLE] == 0.3
