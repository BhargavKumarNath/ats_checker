"""Deterministic readability metric behind `RewriteSuggestion.readability_flag`.

product_requirements.md §5 item 5: flag a rewrite that raises keyword density at the
cost of readability. No model call; the same inputs always give the same answer.
"""

from __future__ import annotations

import re

from atsc.core.matcher import get_default_matcher

_WORD = re.compile(r"[A-Za-z]+")
_SENTENCE_END = re.compile(r"[.!?]+")
_VOWEL_GROUP = re.compile(r"[aeiouy]+")

# Tunable. A rewrite is flagged when density rises by more than this and either the
# text got markedly harder to read or density is high in absolute terms.
DENSITY_RISE = 0.02
EASE_DROP = 10.0
DENSITY_CEILING = 0.20


def _syllables(word: str) -> int:
    w = word.lower()
    n = len(_VOWEL_GROUP.findall(w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def reading_ease(text: str) -> float:
    """Flesch reading ease: higher is easier. Plain English sits around 60-70."""
    words = _WORD.findall(text)
    if not words:
        return 100.0
    sentences = max(1, len(_SENTENCE_END.findall(text)))
    syllables = sum(_syllables(w) for w in words)
    return 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syllables / len(words))


def keyword_density(text: str) -> float:
    """Taxonomy surface-form mentions per word."""
    words = text.split()
    if not words:
        return 0.0
    return len(get_default_matcher().match(text)) / len(words)


def readability_flag(original: str, rewrite: str) -> bool:
    d0, d1 = keyword_density(original), keyword_density(rewrite)
    if d1 <= d0 + DENSITY_RISE:
        return False
    harder = reading_ease(rewrite) < reading_ease(original) - EASE_DROP
    return harder or d1 > DENSITY_CEILING
