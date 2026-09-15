"""Text cleaning and normalisation (resume_parsing_spec.md §2 step 3)."""

from __future__ import annotations

import re
import unicodedata

BULLET_GLYPHS = "•·▪▫◦○●■□–—*►▶➢➤✓✔◆◇»▸‣⁃"
_BULLET_RE = re.compile(rf"^\s*(?:[{re.escape(BULLET_GLYPHS)}]|-)\s+")
_MOJIBAKE = {
    "â€“": "–",
    "â€”": "—",
    "â€™": "'",
    "â€˜": "'",
    "â€œ": '"',
    "â€\x9d": '"',
    "â€¢": "•",
    "Â·": "·",
    "Â ": " ",
    "﻿": "",
}


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for bad, good in _MOJIBAKE.items():
        text = text.replace(bad, good)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\t", " ").replace(" ", " ").replace("​", "")
    lines = [re.sub(r" {2,}", " ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if line == "" and out and out[-1] == "":
            continue
        out.append(line)
    return "\n".join(out).strip()


def is_bullet_line(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def strip_bullet(line: str) -> str:
    return _BULLET_RE.sub("", line, count=1).strip()
