"""Convert specific Uranium events through the real pipeline — ISOLATED validation.

Used for bounded frozen-Opus validation spikes (e.g. FABLES gate G2: does Opus
strip Wait(106)/SE(250)/pbCallBub plumbing in a dialogue event?). Runs the exact
production path — registry collision-check -> claude backend with the frozen
system prompt -> poryscript compile gate -> flush — but against a THROWAWAY temp
out_dir so it never mutates the live bulk-run state (no checkpoint, no .pory, no
memo entry, no flag_state mutation written to output/uranium-build).

Faithfulness: the temp registry is seeded from a COPY of the live flag_state.json
when present, so reuse/fork-constant collision checks match production; mutations
land in the temp copy. The frozen system prompt + model are loaded from the repo
reference dir and are out_dir-independent. No memo manifest in temp => every event
is a real spawn (no accidental reuse masking the agent's actual output).

Usage:
  python scripts/convert_one_event.py --event 174:9 --event 31:9 --yes
  python scripts/convert_one_event.py --event 174:9 --model claude-opus-4-8 --yes

With no --event, defaults to the G2 candidates (174:9 family-1 dialogue+Wait,
31:9 family-2 dialogue+SE+pbCallBub). Each spawn spends Pro/API budget, so the
run is gated behind a confirmation prompt unless --yes is passed.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

from rpg2gba import pipeline
from rpg2gba.conversion_agent import orchestrator as orch

logger = logging.getLogger(__name__)

FROZEN_MODEL = "claude-opus-4-8"
DEFAULT_EVENTS = [(174, 9), (31, 9)]


def parse_pairs(raw: list[str]) -> list[tuple[int, int]]:
    """Parse ``MAP:EVENT`` strings into (map_id, event_id) pairs."""
    pairs: list[tuple[int, int]] = []
    for item in raw:
        try:
            m, e = item.split(":")
            pairs.append((int(m), int(e)))
        except ValueError:
            raise SystemExit(f"bad --event {item!r}: expected MAP:EVENT, e.g. 174:9")
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--event",
        action="append",
        default=[],
        metavar="MAP:EVENT",
        help="Event to convert, e.g. --event 174:9 (repeatable).",
    )
    ap.add_argument("--model", default=FROZEN_MODEL, help="Claude model for the spawn.")
    ap.add_argument("--yes", action="store_true", help="Skip the spend confirmation.")
    ap.add_argument("-v", "--verbose", action="store_true", help="DEBUG logging.")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pairs = parse_pairs(args.event) if args.event else list(DEFAULT_EVENTS)

    pipeline._load_dotenv()
    _, live_out = pipeline._resolve_paths()
    live_out = Path(live_out)
    fork = os.environ.get("RPG2GBA_POKEEMERALD")
    fork_path = Path(fork) if fork and Path(fork).is_dir() else None

    print(f"ISOLATED validation — {len(pairs)} spawn(s) via {args.model}:")
    for m, e in pairs:
        print(f"  Map{m:03d} event {e}")
    print(f"  live out_dir (read-only): {live_out}")
    print("  output goes to a throwaway temp dir — live state is NOT touched.")
    if not args.yes:
        if input("Proceed? type 'yes': ").strip().lower() != "yes":
            print("aborted.")
            return 1

    # Isolated temp out_dir: seed only the live registry state (read as a copy) so
    # collision checks are production-faithful; everything else stays empty so the
    # orchestrator writes scripts/checkpoints/memo into the throwaway dir.
    tmp_out = Path(tempfile.mkdtemp(prefix="g2_validate_"))
    live_state = live_out / "flag_state.json"
    if live_state.is_file():
        shutil.copy2(live_state, tmp_out / "flag_state.json")
        logger.info("seeded temp registry from live flag_state.json")

    registry = pipeline._phase4_registry(tmp_out, clean=False, fork_path=fork_path)
    backend = pipeline._phase4_backend("claude_code", args.model)
    orchestrator = orch.Orchestrator(backend, registry, tmp_out)

    for m, e in pairs:
        src = json.loads(
            (live_out / "maps" / f"Map{m:03d}.json").read_text(encoding="utf-8")
        )
        event = next((ev for ev in src["events"] if ev["id"] == e), None)
        if event is None:
            logger.error("Map%03d has no event %d — skipped", m, e)
            continue
        trimmed = {"map_id": src["map_id"], "events": [event]}
        tmp_map = tmp_out / f"Map{m:03d}.json"
        tmp_map.write_text(json.dumps(trimmed), encoding="utf-8")

        print(f"\n===== converting Map{m:03d} event {e} =====", flush=True)
        # Fresh per-map checkpoint each pass (different events share Map{m}.pory name
        # only if same map id; we use distinct map ids here).
        orchestrator.convert_map(tmp_map)
        pory = tmp_out / "scripts" / f"Map{m:03d}.pory"
        print(pory.read_text(encoding="utf-8") if pory.is_file() else "(no .pory written)")

    print(f"\ntemp dir (inspect/delete): {tmp_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
