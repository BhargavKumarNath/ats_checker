"""Layer 2 retrieval corpus: curated files in corpus/ plus taxonomy-derived equivalences.

Every chunk carries a contextual prefix (technical_architecture.md §5) so it keeps its
meaning when retrieved on its own. Nothing here calls a metered API; the corpus is
plain data. Layout (see corpus/README.md):

    corpus/bullets/<category>.yaml   strong bullets and weak→strong rewrite pairs per cluster
    corpus/platforms.yaml            ATS platform behaviours, sourced from resume_parsing_spec.md
    corpus/guidance.yaml             writing guidance for ML/DS/AI resumes
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from atsc.core.models import Category, Platform, RoleTrack
from atsc.core.taxonomy import Taxonomy, load_taxonomy

ChunkKind = Literal["equivalence", "strong_bullet", "rewrite_pair", "platform_quirk", "guidance"]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLATFORM_NAMES = {
    Platform.WORKDAY: "Workday",
    Platform.GREENHOUSE: "Greenhouse",
    Platform.LEVER: "Lever",
    Platform.ASHBY: "Ashby",
}
_ROLE_NAMES = {
    RoleTrack.MLE: "ML Engineer",
    RoleTrack.APPLIED_SCIENTIST: "Applied Scientist",
    RoleTrack.DATA_SCIENTIST: "Data Scientist",
    RoleTrack.ML_RESEARCH: "ML Research",
    RoleTrack.DATA_ENGINEER: "Data Engineer",
}


class CorpusError(ValueError):
    pass


class Chunk(BaseModel):
    chunk_id: str
    kind: ChunkKind
    text: str
    context: str
    cluster_ids: list[str] = Field(default_factory=list)
    category: str | None = None
    platform: str | None = None
    role_tracks: list[str] = Field(default_factory=list)
    why: str = ""
    source: str = ""

    @property
    def embed_text(self) -> str:
        return f"{self.context}\n{self.text}"


def default_corpus_dir() -> Path:
    env = os.environ.get("ATSC_CORPUS_DIR")
    return Path(env) if env else _REPO_ROOT / "corpus"


# -- file schemas ------------------------------------------------------------------


class _StrongBullet(BaseModel):
    cluster_id: str
    text: str
    why: str
    role_tracks: list[RoleTrack] = Field(default_factory=list)


class _RewritePair(BaseModel):
    cluster_id: str
    weak: str
    strong: str
    why: str


class _BulletFile(BaseModel):
    category: Category
    strong: list[_StrongBullet] = Field(default_factory=list)
    pairs: list[_RewritePair] = Field(default_factory=list)


class _PlatformQuirk(BaseModel):
    platform: Platform
    title: str
    text: str
    source: str = ""


class _Guidance(BaseModel):
    topic: str
    text: str
    source: str = ""


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text()) or []
    except yaml.YAMLError as e:
        raise CorpusError(f"{path.name}: {e}") from e


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# -- builders ------------------------------------------------------------------------


def _equivalence_chunks(taxonomy: Taxonomy) -> list[Chunk]:
    out: list[Chunk] = []
    for c in taxonomy.clusters:
        forms = [f for f in c.surface_forms if f.lower() != c.canonical_name.lower()]
        out.append(
            Chunk(
                chunk_id=f"equiv:{c.cluster_id}",
                kind="equivalence",
                context=(
                    f"Skill taxonomy entry: {c.canonical_name} ({c.category.value}). "
                    "Phrasings that count as this one skill."
                ),
                text=(
                    f"{c.canonical_name} is also written as: {', '.join(forms)}. "
                    "Any of these phrasings on a resume matches a job description that asks "
                    "for any other; the checker scores them as the same skill."
                ),
                cluster_ids=[c.cluster_id],
                category=c.category.value,
                source="taxonomy",
            )
        )
    return out


def _bullet_chunks(path: Path, taxonomy: Taxonomy) -> list[Chunk]:
    raw = _read_yaml(path)
    try:
        f = _BulletFile.model_validate(raw)
    except ValueError as e:
        raise CorpusError(f"{path.name}: {e}") from e
    out: list[Chunk] = []
    counters: dict[str, int] = {}
    for b in f.strong:
        cluster = taxonomy.by_id.get(b.cluster_id)
        if cluster is None:
            raise CorpusError(f"{path.name}: unknown cluster_id {b.cluster_id!r}")
        n = counters[b.cluster_id] = counters.get(b.cluster_id, 0) + 1
        roles = ", ".join(_ROLE_NAMES[r] for r in b.role_tracks)
        context = f"Strong resume bullet example for {cluster.canonical_name} ({f.category.value})"
        context += f", typical for {roles} roles." if roles else "."
        out.append(
            Chunk(
                chunk_id=f"strong:{b.cluster_id}:{n}",
                kind="strong_bullet",
                context=context,
                text=b.text,
                cluster_ids=[b.cluster_id],
                category=f.category.value,
                role_tracks=[r.value for r in b.role_tracks],
                why=b.why,
                source=path.name,
            )
        )
    pair_counters: dict[str, int] = {}
    for p in f.pairs:
        cluster = taxonomy.by_id.get(p.cluster_id)
        if cluster is None:
            raise CorpusError(f"{path.name}: unknown cluster_id {p.cluster_id!r}")
        n = pair_counters[p.cluster_id] = pair_counters.get(p.cluster_id, 0) + 1
        out.append(
            Chunk(
                chunk_id=f"pair:{p.cluster_id}:{n}",
                kind="rewrite_pair",
                context=(
                    f"Rewrite example for {cluster.canonical_name} ({f.category.value}): "
                    "a weak resume bullet and a stronger version of the same experience."
                ),
                text=f"Weak: {p.weak}\nStronger: {p.strong}",
                cluster_ids=[p.cluster_id],
                category=f.category.value,
                why=p.why,
                source=path.name,
            )
        )
    return out


def _platform_chunks(path: Path) -> list[Chunk]:
    out: list[Chunk] = []
    counters: dict[Platform, int] = {}
    for raw in _read_yaml(path):
        try:
            q = _PlatformQuirk.model_validate(raw)
        except ValueError as e:
            raise CorpusError(f"{path.name}: {e}") from e
        n = counters[q.platform] = counters.get(q.platform, 0) + 1
        out.append(
            Chunk(
                chunk_id=f"platform:{q.platform.value}:{n}",
                kind="platform_quirk",
                context=f"ATS platform behaviour on {_PLATFORM_NAMES[q.platform]}: {q.title}.",
                text=q.text,
                platform=q.platform.value,
                source=q.source or path.name,
            )
        )
    return out


def _guidance_chunks(path: Path) -> list[Chunk]:
    out: list[Chunk] = []
    for raw in _read_yaml(path):
        try:
            g = _Guidance.model_validate(raw)
        except ValueError as e:
            raise CorpusError(f"{path.name}: {e}") from e
        out.append(
            Chunk(
                chunk_id=f"guidance:{_slug(g.topic)}",
                kind="guidance",
                context=f"Resume writing guidance for ML, data science and AI roles: {g.topic}.",
                text=g.text,
                source=g.source or path.name,
            )
        )
    return out


def load_corpus(directory: Path | None = None, taxonomy: Taxonomy | None = None) -> list[Chunk]:
    directory = directory or default_corpus_dir()
    taxonomy = taxonomy or load_taxonomy()
    chunks = _equivalence_chunks(taxonomy)
    for path in sorted((directory / "bullets").glob("*.yaml")):
        chunks.extend(_bullet_chunks(path, taxonomy))
    platforms = directory / "platforms.yaml"
    if platforms.exists():
        chunks.extend(_platform_chunks(platforms))
    guidance = directory / "guidance.yaml"
    if guidance.exists():
        chunks.extend(_guidance_chunks(guidance))
    ids = [c.chunk_id for c in chunks]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise CorpusError(f"duplicate chunk ids: {dupes}")
    return chunks
