"""spaCy singleton: NER only (resume_parsing_spec.md §2 step 5).

Parser and tagger are disabled for speed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spacy.language import Language


@lru_cache(maxsize=1)
def get_nlp() -> Language:
    import spacy

    return spacy.load(
        "en_core_web_sm", disable=["parser", "lemmatizer", "tagger", "attribute_ruler"]
    )
