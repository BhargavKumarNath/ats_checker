"""Job-description analysis (job_description_analysis.md §3-4, data_model.md §3).

Stage 1 (skill-sentence classification) is rule-based on the free path (build_plan.md
interpretation 5): section context, list structure, requirement verbs, taxonomy hits and
boilerplate exclusion. Stage 2 matches each kept line against the taxonomy.
"""

from __future__ import annotations

import re
from enum import StrEnum

from atsc.core.matcher import ClusterMatcher, get_default_matcher
from atsc.core.models import (
    ParsedJobDescription,
    Requirement,
    RequirementType,
    RoleTrack,
    RoleTrackSignal,
)
from atsc.core.parsing.text import clean_text, is_bullet_line, strip_bullet

# -- section context -------------------------------------------------------------


class _Mode(StrEnum):
    NONE = "none"
    REQUIRED = "required"
    PREFERRED = "preferred"
    RESPONSIBILITIES = "responsibilities"
    BOILERPLATE = "boilerplate"


_HEADER_RULES: list[tuple[_Mode, re.Pattern[str]]] = [
    (
        _Mode.PREFERRED,
        re.compile(
            r"\b(preferred|nice[\s-]+to[\s-]+have|bonus|desired|plus(es)?|ideal(ly)?|"
            r"great[\s-]+to[\s-]+have|extra[\s-]+credit|additional qualifications|"
            r"good[\s-]+to[\s-]+have)\b",
            re.I,
        ),
    ),
    (
        _Mode.REQUIRED,
        re.compile(
            r"\b(requirements?|qualifications?|minimum|basic|must[\s-]+haves?|"
            r"what (you|we)('ll| will)? (need|bring|are looking for|look for)|"
            r"who you are|about you|you have|your (background|experience|profile)|"
            r"skills?( and experience)?|what it takes|experience)\b",
            re.I,
        ),
    ),
    (
        _Mode.RESPONSIBILITIES,
        re.compile(
            r"\b(responsibilities|what you('ll| will)? do|the role|in this role|"
            r"your (role|mission|impact)|day[\s-]+to[\s-]+day|you will|duties|"
            r"what you'll be doing|key (tasks|outcomes))\b",
            re.I,
        ),
    ),
    (
        _Mode.BOILERPLATE,
        re.compile(
            r"\b(about (us|the (company|team)|[A-Z]\w+)|benefits|perks|compensation|"
            r"salary|pay range|why (join|work)|our (mission|values|culture|story)|"
            r"who we are|the company|equal opportunity|eeo|diversity|how to apply|"
            r"application process|location|interview process)\b",
            re.I,
        ),
    ),
]

_BOILERPLATE_LINE = re.compile(
    r"\b(equal[\s-]+opportunity|eeo|discriminat\w*|affirmative action|"
    r"401\s*\(?k\)?|health(care)?|dental|vision (insurance|coverage)|insurance|"
    r"pto|paid time off|vacation|parental leave|stock options|equity|salary|"
    r"compensation|bonus structure|wellness|gym|commuter|"
    r"authori[sz]ed to work|visa|sponsorship|background check|"
    r"we are (a|an|the) |our (mission|office|team|company|customers|culture)|"
    r"headquartered|founded in|fastest[\s-]+growing|remote[\s-]+first|hybrid|"
    r"work[\s-]+from[\s-]+home|apply|reasonable accommodation|"
    r"race|religion|gender|sexual orientation|veteran)\b",
    re.I,
)

_REQUIREMENT_VERB = re.compile(
    r"\b(experience|proficien(cy|t)|familiar(ity)?|knowledge|understanding|expertise|"
    r"background|ability|track record|hands[\s-]+on|fluent|fluency|comfortable|"
    r"exposure|competen(ce|cy|t)|skilled|mastery|degree|ph\.?d|m\.?s\.?c?|b\.?s\.?c?|"
    r"years?|must|should|strong|solid|deep|working knowledge|contributions?|"
    r"publications?|demonstrated)\b",
    re.I,
)

_PREFERRED_INLINE = re.compile(
    r"\b(preferred|bonus|(a|big|huge|strong|definite) plus|nice[\s-]+to[\s-]+have|"
    r"not required|optional|would be (great|nice|a plus|beneficial|welcome)|"
    r"ideally|is a plus|are a plus|desirable|good to have|great to have)\b",
    re.I,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")


def _header_mode(line: str) -> _Mode | None:
    """Return the section mode a short heading line switches to, or None if not a heading."""
    stripped = line.rstrip(":").strip()
    if not stripped or len(stripped) > 60 or len(stripped.split()) > 8:
        return None
    if is_bullet_line(line) or stripped.endswith((".", ",", ";")):
        return None
    for mode, pattern in _HEADER_RULES:
        if pattern.search(stripped):
            return mode
    return None


def _units(line: str) -> list[str]:
    """One bullet = one unit; a prose paragraph = one unit per sentence."""
    if is_bullet_line(line):
        return [strip_bullet(line)]
    return [s.strip() for s in _SENTENCE_SPLIT.split(line) if s.strip()]


def _is_requirement(unit: str, mode: _Mode, has_taxonomy_hit: bool) -> bool:
    if len(unit.split()) < 3 or _BOILERPLATE_LINE.search(unit):
        return False
    if mode is _Mode.BOILERPLATE:
        return False
    if mode in (_Mode.REQUIRED, _Mode.PREFERRED):
        return True
    if mode is _Mode.RESPONSIBILITIES:
        return has_taxonomy_hit
    # No section context (prose JD): keep skill-bearing or requirement-shaped sentences.
    return has_taxonomy_hit or bool(_REQUIREMENT_VERB.search(unit))


def _requirement_type(unit: str, mode: _Mode) -> RequirementType:
    if mode is _Mode.PREFERRED or _PREFERRED_INLINE.search(unit):
        return "preferred"
    return "required"


# -- role track ----------------------------------------------------------------------

_TITLE_PATTERNS: dict[RoleTrack, re.Pattern[str]] = {
    RoleTrack.MLE: re.compile(
        r"\b(machine learning engineer|ml engineer|mle|ai engineer|llm engineer|"
        r"genai engineer|mlops engineer|ml platform engineer|ml infrastructure)\b",
        re.I,
    ),
    RoleTrack.APPLIED_SCIENTIST: re.compile(
        r"\b(applied scientist|applied (ml|machine learning|research) scientist|"
        r"applied ai)\b",
        re.I,
    ),
    RoleTrack.DATA_SCIENTIST: re.compile(
        r"\b(data scientist|data science|decision scientist|product analyst|"
        r"analytics engineer)\b",
        re.I,
    ),
    RoleTrack.ML_RESEARCH: re.compile(
        r"\b(research scientist|research engineer|ml researcher|member of technical staff|"
        r"ai researcher|machine learning researcher)\b",
        re.I,
    ),
    RoleTrack.DATA_ENGINEER: re.compile(
        r"\b(data engineer|data platform engineer|etl developer|data infrastructure)\b",
        re.I,
    ),
}

_BODY_PATTERNS: dict[RoleTrack, re.Pattern[str]] = {
    RoleTrack.MLE: re.compile(
        r"\b(deploy\w*|production|serving|inference|mlops|latency|scal(e|ing|able))\b", re.I
    ),
    RoleTrack.APPLIED_SCIENTIST: re.compile(
        r"\b(applied research|prototype\w*|experiment\w* with (new|novel)|"
        r"state[\s-]+of[\s-]+the[\s-]+art)\b",
        re.I,
    ),
    RoleTrack.DATA_SCIENTIST: re.compile(
        r"\b(a/b test\w*|experimentation|statistical|analytics|dashboards?|"
        r"stakeholders?|insights?|causal inference|hypothesis)\b",
        re.I,
    ),
    RoleTrack.ML_RESEARCH: re.compile(
        r"\b(publications?|papers?|neurips|icml|iclr|acl|cvpr|novel (methods?|algorithms?)|"
        r"phd|research agenda)\b",
        re.I,
    ),
    RoleTrack.DATA_ENGINEER: re.compile(
        r"\b(data pipelines?|etl|elt|data warehouse\w*|lakehouse|spark|airflow|dbt|"
        r"kafka|data quality|data modell?ing)\b",
        re.I,
    ),
}

_TITLE_WEIGHT = 5


def _role_track(title: str, body: str) -> RoleTrackSignal:
    scores: dict[RoleTrack, int] = {}
    for track in RoleTrack:
        score = _TITLE_WEIGHT * len(_TITLE_PATTERNS[track].findall(title))
        score += len(_TITLE_PATTERNS[track].findall(body))
        score += len(_BODY_PATTERNS[track].findall(body))
        scores[track] = score
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, runner_up = ranked[0], ranked[1]
    if best[1] == 0 or best[1] == runner_up[1]:
        return "unclear"
    return best[0]


# -- seniority ---------------------------------------------------------------------

_YEARS = re.compile(
    r"\b(\d{1,2})\s*(?:\+|-|\u2013|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b", re.I
)
_YEARS_CONTEXT = re.compile(r"\b(experience|background|track record|working|in|of)\b", re.I)

_LEVEL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("intern", re.compile(r"\b(intern(ship)?|co-?op)\b", re.I)),
    (
        "junior",
        re.compile(r"\b(junior|jr\.?|entry[\s-]+level|new grad(uate)?|associate|\bI)\b", re.I),
    ),
    ("principal", re.compile(r"\b(principal|distinguished|fellow|\bIV|\bV)\b", re.I)),
    ("staff", re.compile(r"\b(staff|lead|head of|director)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?|\bIII)\b", re.I)),
    ("mid", re.compile(r"\b(mid[\s-]+level|intermediate|\bII)\b", re.I)),
]


def _years_experience(text: str) -> int | None:
    lows: list[int] = []
    for m in _YEARS.finditer(text):
        tail = text[m.end() : m.end() + 40]
        if _YEARS_CONTEXT.search(tail) or _YEARS_CONTEXT.search(
            text[max(0, m.start() - 40) : m.start()]
        ):
            lows.append(int(m.group(1)))
    return max(lows) if lows else None


def _seniority(title: str, years: int | None) -> str:
    for level, pattern in _LEVEL_PATTERNS:
        if pattern.search(title):
            return level
    if years is None:
        return "unclear"
    if years < 2:
        return "junior"
    if years < 5:
        return "mid"
    if years < 8:
        return "senior"
    return "staff"


# -- entry point -------------------------------------------------------------------


def parse_job_description(
    text: str, *, matcher: ClusterMatcher | None = None
) -> ParsedJobDescription:
    matcher = matcher or get_default_matcher()
    cleaned = clean_text(text)
    if not cleaned:
        return ParsedJobDescription()
    lines = [ln for ln in cleaned.split("\n") if ln.strip()]
    title, body_lines = lines[0], lines[1:]

    mode = _Mode.NONE
    requirements: list[Requirement] = []
    seen: set[str] = set()
    for line in body_lines:
        header = _header_mode(line)
        if header is not None:
            mode = header
            continue
        for unit in _units(line):
            clusters: list[str] = []
            for m in matcher.match(unit):
                if m.cluster_id not in clusters:
                    clusters.append(m.cluster_id)
            if not _is_requirement(unit, mode, bool(clusters)):
                continue
            key = unit.lower()
            if key in seen:
                continue
            seen.add(key)
            requirements.append(
                Requirement(
                    raw_text=unit,
                    requirement_type=_requirement_type(unit, mode),
                    matched_clusters=clusters,
                )
            )

    body = "\n".join(body_lines)
    years = _years_experience(cleaned)
    return ParsedJobDescription(
        role_track_signal=_role_track(title, body),
        seniority_signal=_seniority(title, years),
        years_experience=years,
        requirements=requirements,
        raw_text=cleaned,
    )
