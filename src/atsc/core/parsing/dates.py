"""Date detection and normalisation for work/education entries.

Normalised forms: "YYYY-MM", "YYYY", or "present". Each date also carries a
style family (text / numeric / year) so the inconsistent_dates check can tell
"Jun 2018" from "03/2020" from "2023" (resume_parsing_spec.md §3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

StyleFamily = Literal["text", "numeric", "year"]

_MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ]
    )
    for m in names
}
_MON = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
DATE_RE = re.compile(
    rf"(?P<text>\b(?P<tmon>{_MON})\.?,?\s+(?P<tyear>(?:19|20)\d{{2}})\b)"
    r"|(?P<num>(?<!\d)(?P<nmon>0?[1-9]|1[0-2])[/.](?P<nyear>(?:19|20)\d{2}|\d{2})(?!\d))"
    r"|(?P<iso>(?<!\d)(?P<iyear>(?:19|20)\d{2})-(?P<imon>0[1-9]|1[0-2])(?!\d))"
    r"|(?P<year>(?<![\d/.-])(?:19|20)\d{2}(?![\d/.-]))",
    re.IGNORECASE,
)
PRESENT_RE = re.compile(
    r"\b(?:present|current|currently|now|ongoing|to date|till date|today)\b", re.IGNORECASE
)
# en dash, em dash, hyphen-minus, U+2010 hyphen, U+2011 non-breaking hyphen
_SEP_RE = re.compile(
    r"^\s*(?:[\u2013\u2014\-\u2010\u2011]|to|until|through|till)\s*$", re.IGNORECASE
)


@dataclass(frozen=True)
class DateToken:
    start: int
    end: int
    normalised: str
    family: StyleFamily | None  # None for "present"


@dataclass(frozen=True)
class DateRange:
    start: str
    end: str
    family: StyleFamily
    span: tuple[int, int]


def _normalise(m: re.Match[str]) -> DateToken:
    if m.group("text"):
        return DateToken(
            m.start(), m.end(), f"{m.group('tyear')}-{_MONTHS[m.group('tmon').lower()]:02d}", "text"
        )
    if m.group("num"):
        y = m.group("nyear")
        year = int(y) if len(y) == 4 else 2000 + int(y)
        return DateToken(m.start(), m.end(), f"{year}-{int(m.group('nmon')):02d}", "numeric")
    if m.group("iso"):
        return DateToken(m.start(), m.end(), f"{m.group('iyear')}-{m.group('imon')}", "numeric")
    return DateToken(m.start(), m.end(), m.group("year"), "year")


def find_dates(text: str) -> list[DateToken]:
    tokens = [_normalise(m) for m in DATE_RE.finditer(text)]
    tokens += [DateToken(m.start(), m.end(), "present", None) for m in PRESENT_RE.finditer(text)]
    return sorted(tokens, key=lambda t: t.start)


def find_date_range(text: str) -> DateRange | None:
    tokens = find_dates(text)
    for a, b in pairwise(tokens):
        if a.family is None:
            continue
        if _SEP_RE.match(text[a.end : b.start]):
            return DateRange(a.normalised, b.normalised, a.family, (a.start, b.end))
    return None


def strip_dates(text: str) -> str:
    rng = find_date_range(text)
    if rng:
        text = text[: rng.span[0]] + text[rng.span[1] :]
    for t in reversed(find_dates(text)):
        text = text[: t.start] + text[t.end :]
    return text
