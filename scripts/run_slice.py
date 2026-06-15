"""Drive the Phase 4 conversion for ONE play-order slice (pathfinder S6).

Unlike `run_bulk.py` (which walks the whole corpus in id order), this converts only
the named maps — by default the pathfinder slice **49, 48, 32** (player's house 1F/2F
+ Moki Town). Use it to spend a small, bounded amount on just the slice without
grinding through maps 008..048 first.

Fully resumable, exactly like run_bulk:
  - per-map `.done` checkpoints skip finished maps;
  - a map interrupted mid-way re-enters and replays its already-converted events as
    FREE memo hits (orchestrator flushes .pory + registry + memo after every event),
    so a session refresh costs nothing already paid for.

It shares the SAME persisted state as the bulk run (flag registry, memo manifest,
checkpoints), so the slice maps land in the same corpus — do NOT run
`prep_bulk_run.py` (that resets to baseline and wipes the done maps + CommonEvents).
CommonEvents is converted first if its pass isn't already done, so the slice's
`call CommonEvent_NNN` references resolve at assembly.

Modes (identical to run_bulk):

  python scripts/run_slice.py
      Convert the slice until done OR a usage limit is hit, then stop cleanly.
      Re-run after your limit resets to pick up where it stopped.

  python scripts/run_slice.py --timed
      Wait out each 5-hour rolling-window limit and resume automatically until the
      slice is fully converted. A weekly limit stops it outright.

  python scripts/run_slice.py --limit 5
      Stop cleanly after 5 LLM conversions this run (free deterministic/memo reuse
      does not count). Re-run for the next batch.

  python scripts/run_slice.py 33 76 142
      Convert a different set of maps (e.g. a later slice) instead of the default.

Progress: `python scripts/run_stats.py`, or check
output/uranium-build/checkpoints/Map0{49,48,32}.done.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import time
from pathlib import Path

from rpg2gba import pipeline
from rpg2gba.conversion_agent import orchestrator as orch
from rpg2gba.conversion_agent import run_report
from rpg2gba.conversion_agent.backends import (
    BackendTransportError,
    BudgetReached,
    CappingBackend,
    RateLimitError,
)

# The §9 #2 gate froze this model; the run must use it (memo is fingerprinted by the
# frozen system prompt — see run_bulk). Overridable, with a warning.
FROZEN_MODEL = "claude-opus-4-8"

# Default play-order slice: player's house 1F (spawn), 2F, Moki Town.
DEFAULT_SLICE = [49, 48, 32]

logger = logging.getLogger("run_slice")


def _write_state(path: Path, **fields) -> None:
    """Mirror of run_bulk._write_state (kept local so the bulk machinery is untouched)."""
    state: dict = {}
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    state.update(fields)
    state["updated"] = dt.datetime.now(dt.timezone.utc).isoformat()
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _sleep_until(resume_at: float) -> None:
    """Sleep in short, interruptible chunks until `resume_at` wall-clock time."""
    while True:
        remaining = resume_at - time.time()
        if remaining <= 0:
            return
        mins = int(remaining // 60)
        logger.info("paused — resuming in %dh%02dm", mins // 60, mins % 60)
        time.sleep(min(remaining, 60.0))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "maps",
        nargs="*",
        type=int,
        default=DEFAULT_SLICE,
        help=f"Uranium map ids to convert (default: the pathfinder slice {DEFAULT_SLICE}).",
    )
    ap.add_argument(
        "--timed",
        action="store_true",
        help="5-hour-window loop: wait out each rolling-window limit and resume.",
    )
    ap.add_argument("--window-hours", type=float, default=5.0)
    ap.add_argument(
        "--buffer-min",
        type=float,
        default=3.0,
        help="extra minutes to wait past the window before resuming (reset slack).",
    )
    ap.add_argument("--model", default=FROZEN_MODEL)
    ap.add_argument("--backend", default="claude_code", choices=["claude_code", "ollama"])
    ap.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="stop cleanly after N LLM conversions (spawns) this run, then exit. "
        "Resumable. Deterministic pre-filter matches and memo reuse are free and do "
        "NOT count toward N.",
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="DEBUG-level logging.")
    args = ap.parse_args()
    if args.limit is not None and args.limit < 1:
        ap.error("--limit must be >= 1")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.model != FROZEN_MODEL:
        logger.warning(
            "model %s != frozen %s — the §9 #2 gate froze %s; using a different model "
            "discards the memo (re-spend)",
            args.model, FROZEN_MODEL, FROZEN_MODEL,
        )

    pipeline._load_dotenv()
    _, out_dir = pipeline._resolve_paths()
    out_dir = Path(out_dir)
    maps_dir = out_dir / "maps"
    if not maps_dir.is_dir():
        logger.error("%s not found — run `phase3` first", maps_dir)
        return 2

    slice_ids = list(args.maps)
    map_files = [(mid, maps_dir / f"Map{mid:03d}.json") for mid in slice_ids]
    missing = [mid for mid, p in map_files if not p.is_file()]
    if missing:
        logger.error("map JSON not found for %s — run `phase3` first", missing)
    present = [(mid, p) for mid, p in map_files if p.is_file()]
    if not present:
        return 2

    fork = os.environ.get("RPG2GBA_POKEEMERALD")
    fork_path = Path(fork) if fork and Path(fork).is_dir() else None
    registry = pipeline._phase4_registry(out_dir, clean=False, fork_path=fork_path)
    usage_log = out_dir / "token_usage.jsonl"
    backend = pipeline._phase4_backend(args.backend, args.model, usage_log_path=usage_log)
    if args.limit is not None:
        backend = CappingBackend(backend, args.limit)
        logger.info("bounded run: stopping after %d LLM conversion(s) this invocation", args.limit)
    orchestrator = orch.Orchestrator(backend, registry, out_dir)
    state_path = out_dir / "slice_run_state.json"
    ce_file = out_dir / "common_events.json"

    def run_chunk() -> None:
        """Convert common events (skipped if already done) then every pending slice map.
        Returns normally when all are converted; raises on a usage/budget limit."""
        if ce_file.is_file():
            orchestrator.convert_common_events(ce_file)
        for mid, path in present:
            orchestrator.convert_map(path)  # skips its own .done checkpoint internally

    mode = "timed" if args.timed else "plain"
    logger.info("slice run starting (maps=%s, mode=%s, model=%s)", slice_ids, mode, args.model)
    final_status = "complete"
    try:
        while True:
            window_start = time.time()
            _write_state(
                state_path, maps=slice_ids, mode=mode, status="running",
                window_start=window_start, window_hours=args.window_hours, resume_at=None,
            )
            try:
                run_chunk()
                logger.info("SLICE DONE — maps %s fully converted", slice_ids)
                final_status = "complete"
                break
            except BudgetReached as e:
                final_status = "limit_reached"
                _write_state(state_path, status="limit_reached", resume_at=None)
                logger.info("%s — stopping cleanly. Re-run to convert more.", e)
                break
            except RateLimitError as e:
                kind = "weekly" if e.weekly else "5-hour-window"
                logger.warning("usage limit hit (%s): %s", kind, e)
                if e.reset_hint:
                    logger.warning("provider reset hint: %s", e.reset_hint)
                if e.weekly:
                    final_status = "weekly_limit"
                    _write_state(state_path, status="weekly_limit", resume_at=None)
                    logger.warning("weekly limit — stopping. Restart after it resets.")
                    break
                if not args.timed:
                    final_status = "rate_limit"
                    _write_state(state_path, status="rate_limit", resume_at=None)
                    logger.warning("rate limit — stopping. Re-run with --timed to auto-wait.")
                    break
                resume_at = window_start + args.window_hours * 3600 + args.buffer_min * 60
                _write_state(state_path, status="paused", resume_at=resume_at)
                logger.warning(
                    "waiting out the window — resuming at %s",
                    dt.datetime.fromtimestamp(resume_at).isoformat(timespec="seconds"),
                )
                _sleep_until(resume_at)
                # loop: restart the clock and resume from the next unfinished task
            except BackendTransportError as e:
                final_status = "transport_error"
                _write_state(state_path, status="transport_error", resume_at=None)
                logger.error("transport failure (not a usage limit): %s", e)
                logger.error("stopping — just re-run to resume once the network recovers.")
                break
    except KeyboardInterrupt:
        final_status = "interrupted"
        _write_state(state_path, status="interrupted", resume_at=None)
        logger.warning("interrupted — progress is checkpointed; re-run to resume.")
    finally:
        _write_state(state_path, status=final_status, resume_at=None)
        try:
            registry.dump_header(out_dir / "intermediate" / "rpg2gba_flags.h")
        except Exception:  # header dump is a convenience, never fatal to the run
            logger.debug("flag header dump skipped", exc_info=True)
        print("\n" + run_report.format_stats(run_report.collect_stats(out_dir)))

    return 0 if final_status in ("complete", "interrupted", "limit_reached") else 1


if __name__ == "__main__":
    sys.exit(main())
