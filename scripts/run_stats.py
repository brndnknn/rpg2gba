"""Print a snapshot of Phase 4 bulk-run progress and token spend.

Safe to run any time — including while `run_bulk.py` is running in another
terminal; it only reads the on-disk artifacts.

  python scripts/run_stats.py            # progress + clustered triage summary
  python scripts/run_stats.py --novel    # novel-cluster detail (build-agent review queue)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rpg2gba import pipeline
from rpg2gba.conversion_agent import run_report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--novel",
        action="store_true",
        help="Print novel-cluster detail (the build-agent review queue) instead of the summary.",
    )
    args = ap.parse_args()

    pipeline._load_dotenv()
    _, out_dir = pipeline._resolve_paths()
    stats = run_report.collect_stats(Path(out_dir))

    if args.novel:
        report = stats.get("triage_clustered")
        if report is None:
            print("clustered triage unavailable (see warnings) — no novel listing")
            return 1
        print(f"novel clusters ({report.novel_total} entries):")
        for line in report.novel_lines():
            print(line)
        return 0

    print(run_report.format_stats(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
