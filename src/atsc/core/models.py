"""Pydantic models mirroring docs/data_model.md. Field names follow the spec where given."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


# ---------------------------------------------------------------------------
# Parsed resume (data_model.md §1), aligned to the JSON Resume open standard.
# ---------------------------------------------------------------------------


class Bullet(BaseModel):
    raw_text: str
    matched_clusters: list[str] = Field(default_factory=list)
    # Internal only (build_plan.md interpretation 6): never serialised.
    embedding: list[float] | None = Field(default=None, exclude=True, repr=False)


class Basics(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None


class WorkEntry(BaseModel):
    company: str | None = None
    position: str | None = None
    start_date: str | None = None  # ISO-8601-like ("2021-03") or None
    end_date: str | None = None  # ISO-8601-like, "present", or None
    bullets: list[Bullet] = Field(default_factory=list)


class EducationEntry(BaseModel):
    institution: str | None = None
    degree: str | None = None
    dates: str | None = None


class SkillEntry(BaseModel):
    raw_text: str
    # data_model.md shows a single `matched_cluster`; a surface form may legitimately
    # belong to several clusters (Airflow), so this is a list. Empty = unmatched.
    matched_clusters: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    name: str | None = None
    description: str | None = None
    bullets: list[Bullet] = Field(default_factory=list)


class ParsedResume(BaseModel):
    basics: Basics = Field(default_factory=Basics)
    work: list[WorkEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    skills: list[SkillEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    # Full cleaned text, for the semantic component and for evidence quotes.
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Parseability metadata (data_model.md §2, resume_parsing_spec.md §3).
# ---------------------------------------------------------------------------


class CheckName(StrEnum):
    MULTI_COLUMN_LAYOUT = "multi_column_layout"
    TABLE_DETECTED = "table_detected"
    TEXT_BOX_DETECTED = "text_box_detected"
    NON_STANDARD_FONT = "non_standard_font"
    IMAGE_BASED_PDF = "image_based_pdf"
    INCONSISTENT_DATES = "inconsistent_dates"
    NON_STANDARD_SECTION_HEADERS = "non_standard_section_headers"
    # Listed in resume_parsing_spec.md §2 step 2 but absent from data_model.md's enum;
    # added as an eighth check (build_plan.md Phase 4 note).
    HEADER_FOOTER_CONTENT = "header_footer_content"


class Platform(StrEnum):
    WORKDAY = "workday"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NA = "n/a"


CheckStatus = Literal["pass", "fail", "not_assessed"]
FileFormat = Literal["pdf", "docx", "pasted_text"]


class ParseabilityCheck(BaseModel):
    check_name: CheckName
    status: CheckStatus
    location: str = ""
    platform_severity: dict[Platform, Severity]

    @field_validator("platform_severity")
    @classmethod
    def _every_platform(cls, v: dict[Platform, Severity]) -> dict[Platform, Severity]:
        missing = set(Platform) - set(v)
        if missing:
            raise ValueError(f"missing severity for platforms: {sorted(missing)}")
        return v


class ParseabilityReport(BaseModel):
    file_format: FileFormat
    checks: list[ParseabilityCheck]

    @property
    def failed(self) -> list[ParseabilityCheck]:
        return [c for c in self.checks if c.status == "fail"]

    @property
    def assessed(self) -> list[ParseabilityCheck]:
        return [c for c in self.checks if c.status != "not_assessed"]
