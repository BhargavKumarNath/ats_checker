"""Live smoke test for Layer 2 generation. Spends real tokens; run it yourself.

    ANTHROPIC_API_KEY=... uv run python scripts/deep_report_smoke.py [resume.txt] [jd.txt]

Prints the DeepReport as JSON, the rewrite diff, and token usage. Never wired into
pytest or CI: the free path must stay free and the paid path must stay explicit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import anthropic

from atsc.config import get_settings
from atsc.core.jd import parse_job_description
from atsc.core.parsing import parse_resume_text
from atsc.core.scoring import score
from atsc.deep.diff import rewrite_diff
from atsc.deep.generation import DeepReportGenerator
from atsc.deep.retrieval import get_default_index

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> None:
    resume_path = Path(argv[1]) if len(argv) > 1 else ROOT / "tests/fixtures/resume_clean.txt"
    jd_path = Path(argv[2]) if len(argv) > 2 else ROOT / "tests/fixtures/jd_mle_llm.txt"
    resume, report = parse_resume_text(resume_path.read_text())
    jd = parse_job_description(jd_path.read_text())
    result = score(resume, report, jd)
    settings = get_settings()
    gen = DeepReportGenerator(
        anthropic.Anthropic(), model=settings.deep_llm_model, index=get_default_index()
    )
    deep = gen.generate(result)
    print(deep.model_dump_json(indent=2))
    print(rewrite_diff(deep))
    print(f"usage: {gen.last_usage}")


if __name__ == "__main__":
    main(sys.argv)
