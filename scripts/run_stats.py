"""Print a snapshot of Phase 4 bulk-run progress and token spend.

Safe to run any time — including while `run_bulk.py` is running in another
terminal; it only reads the on-disk artifacts.

  python scripts/run_stats.py
"""
from __future__ import annotations

import sys

from rpg2gba import pipeline
from rpg2gba.conversion_agent import run_report


def main() -> int:
    pipeline._load_dotenv()
    _, out_dir = pipeline._resolve_paths()
    print(run_report.format_stats(run_report.collect_stats(out_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
