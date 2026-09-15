"""Taxonomy growth loop (gap_analysis_spec.md §4), opt-in and aggregate only.

When `ATSC_GROWTH_LOG_PATH` is set, short skill phrases that matched no cluster are
counted in a SQLite table: term and count, nothing else. No resume or posting text is
kept, no session or timestamp per submission, and anything that looks personal or
numeric is dropped before counting. The footer says so whenever it is on.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from atsc.core.models import ParsedJobDescription, ParsedResume

MAX_CHARS = 40
MAX_RESUME_WORDS = 5
MAX_JD_WORDS = 3

_LEAD_IN = re.compile(
    r"^(?:\W*(?:strong|solid|deep|hands[\s-]+on|working|proven|demonstrated|prior|previous|"
    r"extensive|some|basic|good|excellent|practical|professional)\s+)*"
    r"(?:experience|proficiency|proficient|familiarity|familiar|knowledge|expertise|"
    r"understanding|background|exposure|competence|competency|skills?|ability|comfortable|"
    r"fluency|fluent)\s*(?:with|in|of|using|to|on)?\s*",
    re.I,
)
_SPLIT = re.compile(r"\s*(?:,|;|/|\(|\)|\bor\b|\band\b|\betc\.?)\s*", re.I)
_REJECT = re.compile(r"[@\d]")
_NOISE = {
    "",
    "a",
    "an",
    "the",
    "other",
    "others",
    "similar",
    "related",
    "tools",
    "technologies",
    "frameworks",
    "equivalent",
    "such as",
    "e.g",
    "eg",
    "ie",
    "i.e",
}


def _clean(term: str, max_words: int) -> str | None:
    t = term.strip().strip(".:;-\u2013\u2014'\"").strip().lower()
    if not t or t in _NOISE or _REJECT.search(t) or len(t) > MAX_CHARS or len(t) < 2:
        return None
    if len(t.split()) > max_words:
        return None
    return t


def candidate_terms(resume: ParsedResume, jd: ParsedJobDescription) -> list[str]:
    """Unmatched skill phrases from both sides, cleaned; order preserved, duplicates removed."""
    out: list[str] = []
    for s in resume.skills:
        if not s.matched_clusters and (t := _clean(s.raw_text, MAX_RESUME_WORDS)):
            out.append(t)
    for r in jd.requirements:
        if r.matched_clusters:
            continue
        body = _LEAD_IN.sub("", r.raw_text.strip(), count=1)
        if body == r.raw_text.strip():
            continue  # no requirement lead-in: a prose sentence, not a list of skills
        for frag in _SPLIT.split(body):
            if t := _clean(frag, MAX_JD_WORDS):
                out.append(t)
    return list(dict.fromkeys(out))


class GrowthLog:
    def __init__(self, path: Path | None) -> None:
        self._path = path

    @property
    def enabled(self) -> bool:
        return self._path is not None

    def _connect(self) -> sqlite3.Connection:
        assert self._path is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS unmatched_terms "
            "(term TEXT PRIMARY KEY, count INTEGER NOT NULL)"
        )
        return conn

    def record(self, terms: Iterable[str]) -> None:
        if self._path is None:
            return
        cleaned = {t for t in (_clean(x, MAX_RESUME_WORDS) for x in terms) if t}
        if not cleaned:
            return
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO unmatched_terms (term, count) VALUES (?, 1) "
                "ON CONFLICT(term) DO UPDATE SET count = count + 1",
                [(t,) for t in sorted(cleaned)],
            )

    def top(self, n: int) -> list[tuple[str, int]]:
        if self._path is None or not self._path.exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT term, count FROM unmatched_terms ORDER BY count DESC, term ASC LIMIT ?",
                (n,),
            ).fetchall()
        return [(str(t), int(c)) for t, c in rows]
