"""Downloadable rewrite diff (product_requirements.md §5 item 7): changed lines only."""

from __future__ import annotations

from atsc.deep.models import DeepReport

FLAG_NOTE = "# readability flag: raises keyword density at the cost of readability"


def rewrite_diff(report: DeepReport) -> str:
    lines = ["--- resume (original)", "+++ resume (suggested)"]
    for i, r in enumerate(report.rewrite_suggestions, start=1):
        lines.append(f"@@ bullet {i} @@")
        lines.append(f"-{r.original_bullet}")
        lines.append(f"+{r.suggested_rewrite}")
        if r.readability_flag:
            lines.append(FLAG_NOTE)
    return "\n".join(lines) + "\n"
