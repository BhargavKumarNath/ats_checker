"""Delete old report jobs. Thin wrapper around `python -m atsc.deep.retention` for local use.

uv run python scripts/purge_jobs.py --dry-run
uv run python scripts/purge_jobs.py --finished-days 30 --abandoned-days 7
"""

import sys

from atsc.deep.retention import main

if __name__ == "__main__":
    sys.exit(main())
