"""Entity extraction within sections (resume_parsing_spec.md §2 step 5).

Regex for structured fields, line structure for work/education/project entries,
the taxonomy matcher for skills, spaCy NER only as a tie-breaker.
"""

from __future__ import annotations

import re

from atsc.core.matcher import ClusterMatcher
from atsc.core.models import Basics, Bullet, EducationEntry, ProjectEntry, SkillEntry, WorkEntry
from atsc.core.parsing.dates import DateRange, find_date_range, find_dates, strip_dates
from atsc.core.parsing.sections import Section, SectionKind
from atsc.core.parsing.text import is_bullet_line, strip_bullet

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\(?\+?\d[\d\s().-]{7,}\d")
LOCATION_RE = re.compile(r"\b([A-Z][a-zA-Z.]+(?: [A-Z][a-zA-Z.]+){0,3}, ?[A-Z]{2})\b")
REMOTE_RE = re.compile(r"\b(remote|hybrid|on-site|onsite)\b", re.IGNORECASE)
TITLE_RE = re.compile(
    r"\b(engineer|scientist|analyst|developer|researcher|manager|director|lead|intern|architect|"
    r"consultant|specialist|head|vp|president|founder|fellow|professor|associate|principal|staff|"
    r"phd|postdoc|technician|administrator|officer|coordinator)\b",
    re.IGNORECASE,
)
DEGREE_RE = re.compile(
    r"\b(b\.?\s?(?:s|a|e|tech|eng|sc)\.?|m\.?\s?(?:s|a|e|tech|eng|sc|phil|res)\.?|ph\.?\s?d\.?|"
    r"bachelor(?:'s|s)?|master(?:'s|s)?|doctorate|doctoral|mba|bba|associate(?:'s|s)? degree|"
    r"diploma|postgraduate|undergraduate)\b",
    re.IGNORECASE,
)
INSTITUTION_RE = re.compile(
    r"\b(university|college|institute|school|academy|polytechnic|iit|nit|mit|iisc|eth|ucl|caltech)\b",
    re.IGNORECASE,
)
_SPLIT_RE = re.compile(r"\s+[\u2014\u2013|]\s+|\s+\|\s*|\s+@\s+|,\s+")  # em/en dash, pipe
_AT_RE = re.compile(r"\s+at\s+")
_SKILL_SPLIT_RE = re.compile(r"\s*[,;|•·/]\s*|\s{2,}")
_CATEGORY_RE = re.compile(r"^([^:]{1,40}):\s*(.+)$")
_TRIM = " ,|\u2014\u2013-\u00b7"  # space, comma, pipe, em/en dash, hyphen, middle dot
_RANGE_JOIN = " \u2013 "  # en dash


# -- basics --------------------------------------------------------------------------


def _looks_like_name(line: str) -> bool:
    words = line.replace(",", "").split()
    if not 2 <= len(words) <= 4 or any(ch.isdigit() for ch in line) or "@" in line:
        return False
    return all(w[0].isupper() for w in words if w[0].isalpha())


def extract_basics(header: Section) -> Basics:
    lines = [ln for ln in header.lines if ln]
    block = "\n".join(lines)
    name = next((ln for ln in lines[:3] if _looks_like_name(ln)), None)
    if name is None:
        from atsc.core.nlp import get_nlp

        ents = [e.text for e in get_nlp()(block[:400]).ents if e.label_ == "PERSON"]
        name = ents[0] if ents else None
    email = EMAIL_RE.search(block)
    phone = PHONE_RE.search(block)
    loc = LOCATION_RE.search(block)
    location = loc.group(1) if loc else None
    if location is None and (rm := REMOTE_RE.search(block)):
        location = rm.group(1).title()
    return Basics(
        name=name,
        email=email.group(0) if email else None,
        phone=phone.group(0).strip() if phone else None,
        location=location,
    )


# -- work ------------------------------------------------------------------------------


def _blocks(lines: list[str]) -> list[tuple[list[str], DateRange | None, list[str]]]:
    """Group lines into (header_lines, date_range, bullet_lines) entries.

    An entry begins at a non-bullet line carrying a date range; up to two preceding
    non-bullet lines (title / company) belong to the same header.
    """
    entries: list[tuple[list[str], DateRange | None, list[str]]] = []
    pending: list[str] = []
    current: tuple[list[str], DateRange | None, list[str]] | None = None
    for line in lines:
        if not line:
            continue
        if is_bullet_line(line):
            if current is None:
                current = (pending, None, [])
                pending = []
                entries.append(current)
            elif pending:
                current[2].extend(pending)
                pending = []
            current[2].append(strip_bullet(line))
            continue
        rng = find_date_range(line)
        if rng is not None:
            header = [*pending[-2:], line]
            pending = []
            current = (header, rng, [])
            entries.append(current)
            continue
        if current is not None and current[2] and line[:1].islower():
            current[2][-1] += " " + line
            continue
        pending.append(line)
    if pending and current is not None:
        current[2].extend(pending)
    return entries


def _split_header(header_lines: list[str]) -> list[str]:
    parts: list[str] = []
    for line in header_lines:
        for part in _SPLIT_RE.split(strip_dates(line)):
            part = part.strip(_TRIM)
            if not part or LOCATION_RE.fullmatch(part) or REMOTE_RE.fullmatch(part):
                continue
            # "Senior MLE at Acme" → two parts, but only when the left side is a title,
            # so institution names like "University of Texas at Austin" stay whole.
            if (at := _AT_RE.search(part)) and TITLE_RE.search(part[: at.start()]):
                parts.extend([part[: at.start()].strip(), part[at.end() :].strip()])
            else:
                parts.append(part)
    return parts


def _position_and_company(parts: list[str]) -> tuple[str | None, str | None]:
    if not parts:
        return None, None
    titled = [p for p in parts if TITLE_RE.search(p)]
    others = [p for p in parts if p not in titled]
    if titled and others:
        return titled[0], others[0]
    if len(parts) == 1:
        return (parts[0], None) if titled else (None, parts[0])
    if not titled:
        from atsc.core.nlp import get_nlp

        orgs = {e.text for e in get_nlp()(" | ".join(parts)).ents if e.label_ == "ORG"}
        for p in parts:
            if p in orgs:
                return next((q for q in parts if q != p), None), p
    return parts[0], parts[1]


def _make_bullets(texts: list[str], matcher: ClusterMatcher) -> list[Bullet]:
    out: list[Bullet] = []
    for t in texts:
        seen: list[str] = []
        for m in matcher.match(t):
            if m.cluster_id not in seen:
                seen.append(m.cluster_id)
        out.append(Bullet(raw_text=t, matched_clusters=seen))
    return out


def extract_work(sections: list[Section], matcher: ClusterMatcher) -> list[WorkEntry]:
    exp = [s for s in sections if s.kind == SectionKind.EXPERIENCE]
    # No recognised experience section: fall back to date-headed blocks in unknown sections.
    candidates = exp or [s for s in sections if s.kind == SectionKind.UNKNOWN]
    work: list[WorkEntry] = []
    for section in candidates:
        for header, rng, bullets in _blocks(section.lines):
            if rng is None and not exp:
                continue
            position, company = _position_and_company(_split_header(header))
            work.append(
                WorkEntry(
                    company=company,
                    position=position,
                    start_date=rng.start if rng else None,
                    end_date=rng.end if rng else None,
                    bullets=_make_bullets(bullets, matcher),
                )
            )
    return work


# -- education ---------------------------------------------------------------------------


def extract_education(sections: list[Section]) -> list[EducationEntry]:
    out: list[EducationEntry] = []
    for section in (s for s in sections if s.kind == SectionKind.EDUCATION):
        for line in section.lines:
            if not line or not (DEGREE_RE.search(line) or INSTITUTION_RE.search(line)):
                continue
            dates = find_dates(line)
            date_str = _RANGE_JOIN.join(d.normalised for d in dates[:2]) if dates else None
            parts = [p.strip(_TRIM) for p in _SPLIT_RE.split(strip_dates(line))]
            parts = [p for p in parts if p]
            degree = next((p for p in parts if DEGREE_RE.search(p)), None)
            institution = next((p for p in parts if INSTITUTION_RE.search(p) and p != degree), None)
            if institution is None:
                institution = next((p for p in parts if p != degree), None)
            out.append(EducationEntry(institution=institution, degree=degree, dates=date_str))
    return out


# -- skills ------------------------------------------------------------------------------


def extract_skills(sections: list[Section], matcher: ClusterMatcher) -> list[SkillEntry]:
    seen: dict[str, SkillEntry] = {}
    for section in (s for s in sections if s.kind == SectionKind.SKILLS):
        for line in section.lines:
            if not line:
                continue
            body = strip_bullet(line) if is_bullet_line(line) else line
            if m := _CATEGORY_RE.match(body):
                body = m.group(2)
            for item in _SKILL_SPLIT_RE.split(body):
                item = item.strip(" .")
                if not item or len(item.split()) > 6 or item.lower() in seen:
                    continue
                clusters: list[str] = []
                for hit in matcher.match(item):
                    if hit.cluster_id not in clusters:
                        clusters.append(hit.cluster_id)
                seen[item.lower()] = SkillEntry(raw_text=item, matched_clusters=clusters)
    return list(seen.values())


# -- projects ----------------------------------------------------------------------------


def extract_projects(sections: list[Section], matcher: ClusterMatcher) -> list[ProjectEntry]:
    out: list[ProjectEntry] = []
    for section in (s for s in sections if s.kind == SectionKind.PROJECTS):
        current: ProjectEntry | None = None
        for line in section.lines:
            if not line:
                continue
            if is_bullet_line(line):
                if current is None:
                    current = ProjectEntry()
                    out.append(current)
                current.bullets.extend(_make_bullets([strip_bullet(line)], matcher))
            elif current is None or current.bullets:
                current = ProjectEntry(name=strip_dates(line).strip(_TRIM))
                out.append(current)
            else:
                current.description = (
                    line if current.description is None else current.description + " " + line
                )
    return out
