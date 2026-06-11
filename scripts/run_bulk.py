"""Drive the Phase 4 bulk conversion run (all maps + common events via Opus).

Always resumes: every start picks up at the first unfinished task (per-map
checkpoints skip done maps; the event memo skips events already converted within a
map that was interrupted mid-way), so a fresh `prep_bulk_run.py` is only needed for
a clean restart.

Two modes:

  python scripts/run_bulk.py
      Run until everything is done OR a usage limit is hit, then stop. Restart to
      continue once your limit resets.

  python scripts/run_bulk.py --timed
      Start a 5-hour clock, run until the rolling-window limit is hit, sleep until
      the clock (+ a small buffer) elapses so the window resets, then restart the
      clock and keep going — repeating until the whole corpus is converted. A
      *weekly* limit stops it outright (restart it next week).

Either mode accepts `-n / --limit N` to stop cleanly after N LLM conversions this
run (a bounded, controlled batch — run once, five, any number). It is resumable:
each restart picks up where the last stopped, so bounded rounds accumulate. Free
deterministic / memo reuse does not count toward N.

  python scripts/run_bulk.py --limit 5
      Convert at most 5 events via the LLM, then stop. Run it again for the next 5.

Token/progress tally is written to token_usage.jsonl as it goes; see it any time
with `python scripts/run_stats.py`. A summary also prints on exit.
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

# The §9 #2 gate froze this model; the bulk run must use it. Overridable, with a warning.
FROZEN_MODEL = "claude-opus-4-8"

logger = logging.getLogger("run_bulk")


def _write_state(path: Path, **fields) -> None:
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
    """Sleep (in short, interruptible chunks) until `resume_at` wall-clock time."""
    while True:
        remaining = resume_at - time.time()
        if remaining <= 0:
            return
        mins = int(remaining // 60)
        logger.info("paused — resuming in %dh%02dm", mins // 60, mins % 60)
        time.sleep(min(remaining, 60.0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
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
        help="stop cleanly after N LLM conversions (spawns) this run, then exit — "
        "use it to run a bounded, controlled batch (once, five, any number). "
        "Resumable: each restart picks up where the last stopped. Deterministic "
        "pre-filter matches and memo reuse are free and do NOT count toward N.",
    )
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG-level logging: also show skipped/no-command events, retries, and "
        "per-spawn detail. Without it you still get a per-event/per-map progress heartbeat.",
    )
    args = ap.parse_args()
    if args.limit is not None and args.limit < 1:
        ap.error("--limit must be >= 1")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.model != FROZEN_MODEL:
        logger.warning(
            "model %s != frozen %s — the §9 #2 gate froze %s for the bulk run",
            args.model,
            FROZEN_MODEL,
            FROZEN_MODEL,
        )

    pipeline._load_dotenv()
    _, out_dir = pipeline._resolve_paths()
    out_dir = Path(out_dir)
    maps_dir = out_dir / "maps"
    if not maps_dir.is_dir():
        logger.error("%s not found — run `phase3` first", maps_dir)
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
    state_path = out_dir / "run_state.json"
    ce_file = out_dir / "common_events.json"

    def run_chunk() -> None:
        """One unit of work: convert common events, then every pending map.
        Returns normally when the corpus is fully converted; raises on a limit."""
        if ce_file.is_file():
            orchestrator.convert_common_events(ce_file)
        orchestrator.convert_all(maps_dir)

    mode = "timed" if args.timed else "plain"
    logger.info("bulk run starting (mode=%s, model=%s)", mode, args.model)
    final_status = "complete"
    try:
        while True:
            window_start = time.time()
            _write_state(
                state_path,
                mode=mode,
                status="running",
                window_start=window_start,
                window_hours=args.window_hours,
                resume_at=None,
            )
            try:
                run_chunk()
                logger.info("ALL DONE — corpus fully converted")
                final_status = "complete"
                break
            except BudgetReached as e:
                final_status = "limit_reached"
                _write_state(state_path, status="limit_reached", resume_at=None)
                logger.info("%s — stopping cleanly. Restart to convert more.", e)
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
                    logger.warning("rate limit — stopping. Restart with --timed to auto-wait.")
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
                logger.error("stopping — just restart to resume once the network recovers.")
                break
    except KeyboardInterrupt:
        final_status = "interrupted"
        _write_state(state_path, status="interrupted", resume_at=None)
        logger.warning("interrupted — progress is checkpointed; restart to resume.")
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
