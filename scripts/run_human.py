"""Hand-convert the easy events yourself — zero Claude usage — and seed the memo.

Serves you the *easiest* events first (pure dialogue, self-switch NPCs, simple
flag-gated branches) one at a time; you type the Poryscript, it runs through the
same compile-gate / registry / memo machinery as the bulk run. Each accepted
conversion lands in the memo, so when `run_bulk.py` (Opus) later sweeps the corpus
those events — and every structurally identical twin — are free memo hits.

The genuinely hard events (move-routes, Uranium script-calls, global-switch/var
naming) are held back for Opus and never shown here. Type `opus` on any event to
punt it to the bulk run; `quit` (or Ctrl-D) to stop — progress is saved as you go.

  python scripts/run_human.py                # all easy events, easiest first
  python scripts/run_human.py --limit 20     # do 20, then stop
  python scripts/run_human.py --max-score 0  # pure-dialogue only (no branches)
  python scripts/run_human.py --map 42       # only Map042

Resumable: accepted events are memoized and skipped next time; punted/queued ones
reappear. Run it as many short sessions as you like.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from rpg2gba import pipeline
from rpg2gba.conversion_agent import deterministic
from rpg2gba.conversion_agent import orchestrator as orch
from rpg2gba.conversion_agent.backends import EventDeferred
from rpg2gba.conversion_agent.lane import in_lane, real_commands

logger = logging.getLogger("run_human")


def _difficulty(event: dict) -> int:
    """Lower = easier (served first). Branches and choices cost most; extra content
    pages and raw length break ties."""
    cmds = real_commands(event)
    branches = sum(1 for c in cmds if c.get("code") == 111)
    choices = sum(1 for c in cmds if c.get("code") == 102)
    content_pages = sum(
        1 for p in event.get("pages", []) if any(c.get("code", 0) != 0 for c in p.get("list", []))
    )
    return 3 * branches + 4 * choices + 2 * max(0, content_pages - 1) + len(cmds)


def _build_queue(orchestrator: orch.Orchestrator, maps_dir: Path, only_map: int | None) -> list:
    """Easy, not-yet-done, non-deterministic events across the corpus, easiest first."""
    queue: list[tuple[int, int, dict]] = []  # (difficulty, map_id, event)
    for path in sorted(maps_dir.glob("Map*.json")):
        if orchestrator._checkpoint(path.stem).exists():
            continue  # whole map already converted by the bulk run
        m = json.loads(path.read_text(encoding="utf-8"))
        map_id = m["map_id"]
        if only_map is not None and map_id != only_map:
            continue
        for ev in m["events"]:
            if not in_lane(ev):
                continue  # held for Opus
            payload = {"map_id": map_id, **ev}
            if orch._memo_key(payload) in orchestrator._memo:
                continue  # already converted (by hand or Opus) — free memo hit later
            if deterministic.try_deterministic(map_id, ev, orchestrator._det_context) is not None:
                continue  # the pipeline claims this for free; no human needed
            queue.append((_difficulty(ev), map_id, ev))
    queue.sort(key=lambda t: (t[0], t[1], t[2].get("id", 0)))
    return queue


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("-n", "--limit", type=int, default=None, metavar="N",
                    help="stop after N events accepted/queued this session")
    ap.add_argument("--max-score", type=int, default=None, metavar="S",
                    help="only show events with difficulty <= S (0 = pure dialogue, no branches)")
    ap.add_argument("--map", type=int, default=None, metavar="ID", help="restrict to one map id")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
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
    backend = pipeline._phase4_backend("human")
    orchestrator = orch.Orchestrator(backend, registry, out_dir)

    queue = _build_queue(orchestrator, maps_dir, args.map)
    if args.max_score is not None:
        queue = [t for t in queue if t[0] <= args.max_score]
    if not queue:
        print("No easy events left in your lane. 🎉  (Run run_bulk.py for the rest.)")
        return 0

    total = len(queue)
    qr = pipeline.REFERENCE_DIR / "human_quickref.md"
    print(f"{total} easy events in your lane (easiest first).")
    print("opus = punt   quit = stop   ? = refs")
    print(f"2nd-tab cheat: {qr}\n")
    converted = queued = deferred = 0
    try:
        for i, (score, map_id, ev) in enumerate(queue, start=1):
            print(f"\n┌─ event {i}/{total}  ·  difficulty {score} ".ljust(45, "─"))
            try:
                script = orchestrator.convert_single(map_id, ev)
            except EventDeferred:
                deferred += 1
                print("  → punted to Opus")
            else:
                registry.save(orchestrator.registry_state_path)
                if script is None:
                    queued += 1
                    print("  → queued (could not convert / compile) — will reappear next session")
                else:
                    converted += 1
                    print("  ✓ stored in memo — Opus will skip this event (and twins) for free")
            if args.limit is not None and (converted + queued + deferred) >= args.limit:
                print(f"\nreached --limit of {args.limit}.")
                break
    except KeyboardInterrupt:
        print("\nsession ended — progress saved.")

    print(f"\nThis session: {converted} converted, {queued} queued, {deferred} punted to Opus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
