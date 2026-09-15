"""Section detection (resume_parsing_spec.md §2 step 4).

A line is a section header when it is short, standalone, and either matches a
known label (any case) or is ALL CAPS and matches nothing (a "creative" header,
which the parseability check reports). Title-case lines that match no label are
content, never headers: job titles and company names look exactly like them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from atsc.core.parsing.dates import find_date_range
from atsc.core.parsing.text import is_bullet_line


class SectionKind(StrEnum):
    HEADER = "header"  # contact block before the first section
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"
    OTHER = "other"  # recognised but not modelled (publications, awards, ...)
    UNKNOWN = "unknown"  # creative header, not recognised


_ALIASES: dict[SectionKind, tuple[str, ...]] = {
    SectionKind.SUMMARY: (
        "summary",
        "professional summary",
        "profile",
        "professional profile",
        "about",
        "about me",
        "objective",
        "career objective",
        "career summary",
        "overview",
        "executive summary",
        "summary of qualifications",
    ),
    SectionKind.EXPERIENCE: (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "career history",
        "relevant experience",
        "industry experience",
        "professional background",
        "experience and employment",
    ),
    SectionKind.EDUCATION: (
        "education",
        "academic background",
        "academics",
        "education and training",
        "qualifications",
        "academic qualifications",
        "education & training",
    ),
    SectionKind.SKILLS: (
        "skills",
        "technical skills",
        "core competencies",
        "competencies",
        "technologies",
        "tech stack",
        "technical stack",
        "tools",
        "tools and technologies",
        "tools & technologies",
        "skills and tools",
        "skills & tools",
        "expertise",
        "technical expertise",
        "areas of expertise",
        "key skills",
        "core skills",
        "technical proficiencies",
        "proficiencies",
        "skills summary",
        "skills & expertise",
        "technical summary",
        "technologies and tools",
    ),
    SectionKind.PROJECTS: (
        "projects",
        "personal projects",
        "selected projects",
        "side projects",
        "open source",
        "open-source",
        "open source contributions",
        "key projects",
        "academic projects",
        "research projects",
        "notable projects",
    ),
    SectionKind.CERTIFICATIONS: (
        "certifications",
        "certificates",
        "certifications and licenses",
        "licenses and certifications",
        "licenses & certifications",
        "courses",
        "courses and certifications",
        "training",
        "professional development",
        "certifications & training",
    ),
    SectionKind.OTHER: (
        "publications",
        "awards",
        "honors",
        "honours",
        "awards and honors",
        "languages",
        "interests",
        "hobbies",
        "volunteering",
        "volunteer experience",
        "leadership",
        "activities",
        "extracurricular activities",
        "references",
        "patents",
        "talks",
        "presentations",
        "research",
        "teaching",
        "additional information",
        "additional",
        "conferences",
        "memberships",
    ),
}
_ALIAS_LOOKUP = {alias: kind for kind, aliases in _ALIASES.items() for alias in aliases}
# Word-level near-matches ("Technical Skills & Tools" → skills). Order matters: the
# OTHER rows come first so "Volunteer Experience" is not read as work experience.
_FUZZY: tuple[tuple[re.Pattern[str], SectionKind], ...] = tuple(
    (re.compile(rf"\b{pat}\b"), kind)
    for pat, kind in (
        (r"volunteer(?:ing)?", SectionKind.OTHER),
        (r"publications?", SectionKind.OTHER),
        (r"awards?", SectionKind.OTHER),
        (r"hono(?:u)?rs", SectionKind.OTHER),
        (r"languages?", SectionKind.OTHER),
        (r"interests?", SectionKind.OTHER),
        (r"skills?", SectionKind.SKILLS),
        (r"competenc(?:y|ies)", SectionKind.SKILLS),
        (r"technolog(?:y|ies)", SectionKind.SKILLS),
        (r"proficienc(?:y|ies)", SectionKind.SKILLS),
        (r"tools?", SectionKind.SKILLS),
        (r"experience", SectionKind.EXPERIENCE),
        (r"employment", SectionKind.EXPERIENCE),
        (r"work history", SectionKind.EXPERIENCE),
        (r"career", SectionKind.EXPERIENCE),
        (r"education", SectionKind.EDUCATION),
        (r"academics?", SectionKind.EDUCATION),
        (r"projects?", SectionKind.PROJECTS),
        (r"certif(?:icate|ication)s?", SectionKind.CERTIFICATIONS),
        (r"licen[cs]es?", SectionKind.CERTIFICATIONS),
        (r"courses?", SectionKind.CERTIFICATIONS),
        (r"summary", SectionKind.SUMMARY),
        (r"profile", SectionKind.SUMMARY),
        (r"objective", SectionKind.SUMMARY),
        (r"about", SectionKind.SUMMARY),
    )
)
_DECOR_RE = re.compile(r"^[\s\-=_—–·•|#*:]+|[\s\-=_—–·•|#*:]+$")
_SEPARATED_RE = re.compile(r"\s[—–|]\s|\sat\s|@")


@dataclass
class Section:
    kind: SectionKind
    header: str | None
    lines: list[str] = field(default_factory=list)


def normalise_label(line: str) -> str:
    return re.sub(r"\s+", " ", _DECOR_RE.sub("", line)).strip().lower()


def _looks_like_header(line: str) -> bool:
    if not line or is_bullet_line(line) or "@" in line or find_date_range(line):
        return False
    # "Languages: Python, SQL" is a labelled content line, not a header.
    if ":" in line.rstrip(":") or "," in line:
        return False
    label = normalise_label(line)
    return 0 < len(label) <= 48 and len(label.split()) <= 6 and not _SEPARATED_RE.search(line)


def classify_label(line: str) -> SectionKind | None:
    """Known label → kind (any case). Returns None when the line matches no label."""
    if not _looks_like_header(line):
        return None
    label = normalise_label(line)
    if label in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[label]
    for pattern, kind in _FUZZY:
        if pattern.search(label):
            return kind
    return None


def _is_creative_header(line: str, next_lines: list[str], current: SectionKind) -> bool:
    """ALL-CAPS short standalone line matching no known label."""
    if not _looks_like_header(line):
        return False
    letters = [c for c in line if c.isalpha()]
    if len(letters) < 3 or not all(c.isupper() for c in letters):
        return False
    # Inside an experience/projects section an employer name in caps is content;
    # it is typically followed within two lines by a date range.
    if current in (SectionKind.EXPERIENCE, SectionKind.PROJECTS):
        return not any(find_date_range(nl) for nl in next_lines[:2])
    return True


def split_sections(lines: list[str]) -> list[Section]:
    sections: list[Section] = [Section(SectionKind.HEADER, None)]
    for i, line in enumerate(lines):
        kind = classify_label(line)
        if kind is not None:
            sections.append(Section(kind, line))
        elif _is_creative_header(line, lines[i + 1 : i + 3], sections[-1].kind) and _past_name_line(
            sections
        ):
            sections.append(Section(SectionKind.UNKNOWN, line))
        else:
            sections[-1].lines.append(line)
    return sections


def _past_name_line(sections: list[Section]) -> bool:
    """Never treat the very first content line (the candidate's name) as a header."""
    first = sections[0]
    return len(sections) > 1 or any(first.lines)
