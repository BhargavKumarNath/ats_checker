"""Print the most frequent unmatched skill terms (taxonomy growth loop, Phase 11).

    ATSC_GROWTH_LOG_PATH=./growth.db uv run python scripts/growth_report.py [N]

A term near the top is a candidate surface form or a missing cluster in taxonomy/.
"""

from __future__ import annotations

import sys
from pathlib import Path

from atsc.config import get_settings
from atsc.free.growth import GrowthLog


def main(n: int) -> None:
    path = get_settings().growth_log_path
    if not path:
        print("ATSC_GROWTH_LOG_PATH is not set; the growth log is off.")
        return
    rows = GrowthLog(Path(path)).top(n)
    if not rows:
        print("no unmatched terms recorded yet")
        return
    width = max(len(t) for t, _ in rows)
    for term, count in rows:
        print(f"{term:{width}}  {count}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 50)
