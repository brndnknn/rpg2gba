"""Reset the Phase 4 output to a pristine state before a fresh bulk run.

Destructive + deliberate — run this ONCE before the first `run_bulk.py`, never
between resumes (resuming relies on the checkpoints this wipes). It:

  * restores flag_state.json from the blessed flag_state.baseline.json snapshot
    (falls back to a clean re-pre-seed if no baseline exists),
  * deletes every per-map checkpoint and emitted .pory,
  * deletes unhandled.jsonl, memo_manifest.json, token_usage.jsonl, run_state.json.

After this, `run_bulk.py` starts from Map (and common events) #1.

Usage:
  python scripts/prep_bulk_run.py          # prompts for confirmation
  python scripts/prep_bulk_run.py --yes     # skip the prompt
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from rpg2gba import pipeline


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()

    pipeline._load_dotenv()
    _, out_dir = pipeline._resolve_paths()
    out_dir = Path(out_dir)

    baseline = out_dir / "flag_state.baseline.json"
    state = out_dir / "flag_state.json"
    files = [
        out_dir / "unhandled.jsonl",
        out_dir / "memo_manifest.json",
        out_dir / "token_usage.jsonl",
        out_dir / "run_state.json",
    ]
    dirs = [out_dir / "checkpoints", out_dir / "scripts"]

    source = "baseline snapshot" if baseline.is_file() else "clean re-pre-seed"
    print(f"Pristine reset of {out_dir}:")
    print(f"  flag_state.json  <- {source}")
    for d in dirs:
        print(f"  wipe dir          {d}")
    for f in files:
        print(f"  delete            {f.name}")

    if not args.yes:
        reply = input("Proceed? type 'yes': ").strip().lower()
        if reply != "yes":
            print("aborted.")
            return 1

    for d in dirs:
        if d.exists():
            shutil.rmtree(d)
    for f in files:
        if f.exists():
            f.unlink()

    if baseline.is_file():
        shutil.copyfile(baseline, state)
        print(f"restored flag_state.json from {baseline.name}")
    else:
        if state.exists():
            state.unlink()
        fork = os.environ.get("RPG2GBA_POKEEMERALD")
        fork_path = Path(fork) if fork and Path(fork).is_dir() else None
        pipeline._phase4_registry(out_dir, clean=False, fork_path=fork_path)  # re-pre-seeds
        print("no baseline — re-pre-seeded a clean flag_state.json")

    print("done. `python scripts/run_bulk.py` will start from the first unfinished task.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
