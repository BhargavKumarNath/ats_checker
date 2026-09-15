"""Pydantic models mirroring docs/data_model.md. Field names follow the spec where given."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Category(StrEnum):
    CORE_ML = "Core ML Foundations"
    LLM_GENAI = "LLM / GenAI"
    INFERENCE_SERVING = "Inference & Serving"
    MLOPS = "MLOps & Lifecycle"
    EVAL_SAFETY = "Evaluation & Safety"
    CLASSICAL_DS = "Classical Data Science"


class RoleTrack(StrEnum):
    MLE = "mle"
    APPLIED_SCIENTIST = "applied_scientist"
    DATA_SCIENTIST = "data_scientist"
    ML_RESEARCH = "ml_research"
    DATA_ENGINEER = "data_engineer"


class SkillCluster(BaseModel):
    """data_model.md §4. One underlying competency with many valid phrasings."""

    cluster_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    canonical_name: str
    category: Category
    surface_forms: list[str] = Field(min_length=2)
    role_track_weight: dict[RoleTrack, float]
