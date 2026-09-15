"""Loads the skill taxonomy dataset (taxonomy/*.yaml) into validated SkillCluster objects.

The dataset lives outside application code on purpose (technical_architecture.md §3).
Location: $ATSC_TAXONOMY_DIR if set, else <repo>/taxonomy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from atsc.core.models import Category, RoleTrack, SkillCluster

_REPO_ROOT = Path(__file__).resolve().parents[3]


def default_taxonomy_dir() -> Path:
    env = os.environ.get("ATSC_TAXONOMY_DIR")
    return Path(env) if env else _REPO_ROOT / "taxonomy"


class _CategoryWeights(BaseModel):
    category: Category
    weights: dict[RoleTrack, float]


class _ClusterFile(BaseModel):
    category: Category
    clusters: list[dict[str, Any]]


class TaxonomyError(ValueError):
    pass


@dataclass(frozen=True)
class Taxonomy:
    clusters: tuple[SkillCluster, ...]

    @property
    def by_id(self) -> dict[str, SkillCluster]:
        return {c.cluster_id: c for c in self.clusters}


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_taxonomy(directory: Path | None = None) -> Taxonomy:
    directory = directory or default_taxonomy_dir()
    if not directory.is_dir():
        raise TaxonomyError(f"taxonomy directory not found: {directory}")

    try:
        category_defaults = {
            cw.category: cw.weights
            for cw in (_CategoryWeights(**row) for row in _load_yaml(directory / "categories.yaml"))
        }
    except (ValidationError, TypeError) as exc:
        raise TaxonomyError(f"invalid categories.yaml: {exc}") from exc
    missing = set(Category) - set(category_defaults)
    if missing:
        raise TaxonomyError(f"categories.yaml lacks weights for: {sorted(missing)}")

    clusters: list[SkillCluster] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.yaml")):
        if path.name == "categories.yaml":
            continue
        try:
            file = _ClusterFile(**_load_yaml(path))
        except (ValidationError, TypeError) as exc:
            raise TaxonomyError(f"invalid cluster file {path.name}: {exc}") from exc
        for raw in file.clusters:
            weights = dict(category_defaults[file.category])
            weights.update(
                {RoleTrack(k): float(v) for k, v in raw.get("role_track_weight", {}).items()}
            )
            try:
                cluster = SkillCluster(
                    cluster_id=raw["cluster_id"],
                    canonical_name=raw["canonical_name"],
                    category=file.category,
                    surface_forms=raw["surface_forms"],
                    role_track_weight=weights,
                )
            except (ValidationError, KeyError) as exc:
                raise TaxonomyError(f"invalid cluster in {path.name}: {exc}") from exc
            if cluster.cluster_id in seen:
                raise TaxonomyError(f"duplicate cluster_id {cluster.cluster_id!r} in {path.name}")
            seen.add(cluster.cluster_id)
            clusters.append(cluster)
    if not clusters:
        raise TaxonomyError(f"no clusters found in {directory}")
    return Taxonomy(clusters=tuple(clusters))
