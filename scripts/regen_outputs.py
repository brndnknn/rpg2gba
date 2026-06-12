"""Targeted output regeneration for Phase 4 checkpointed maps and common events.

After the F1 label-collision fix, already-converted maps carry old colliding
labels on disk. Because every accepted event is stored in the memo manifest,
wiping their checkpoints and replaying via NullBackend replays everything
through memo/deterministic at ZERO LLM cost, with the fix active.

This tool performs that targeted regeneration. It can also prepare specific
common events for re-conversion by patching the per-CE ledger (the actual
re-conversion then happens via ``run_bulk.py``, since CEs are not memoised).

Selection:
  --maps 2 5 7   Regenerate specific map ids.
  --all-done     Regenerate every map that has an existing checkpoint.
  --ce 4 5 6     Drop specific common event ids from the blocks ledger so
                 ``run_bulk.py`` re-converts them on the next run.

At least one selection flag is required.  Add --yes to skip the prompt.

Usage:
  # Regenerate maps 1-7 (F1 fix):
  python scripts/regen_outputs.py --maps 1 2 3 4 5 6 7 --yes

  # Prepare CEs 4 5 6 for re-conversion (run run_bulk.py afterwards):
  python scripts/regen_outputs.py --ce 4 5 6 --yes

  # Regenerate all done maps and prepare CEs:
  python scripts/regen_outputs.py --all-done --ce 4 5 6
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from rpg2gba import pipeline
from rpg2gba.conversion_agent import orchestrator as orch
from rpg2gba.conversion_agent.backends import BudgetReached, NullBackend

logger = logging.getLogger(__name__)

# Frozen model from run_bulk.py — the NullBackend wraps the production backend only for
# its system_prompt (memo fingerprint). Using the same model + prompt-loading path as
# run_bulk.py ensures the fingerprint matches and memo entries are not discarded.
FROZEN_MODEL = "claude-opus-4-8"


def resolve_map_ids(
    checkpoint_dir: Path, explicit: list[int], all_done: bool
) -> list[int]:
    """Return the sorted, de-duped list of map IDs to regenerate.

    Combines explicitly listed ids (``--maps``) with those discovered from existing
    checkpoints (``--all-done``). IDs not present on disk are included as-is: the
    caller will simply find nothing to delete for them."""
    ids: set[int] = set(explicit)
    if all_done and checkpoint_dir.is_dir():
        for cp in checkpoint_dir.glob("Map*.done"):
            try:
                ids.add(int(cp.stem[3:]))  # "Map042" → 42
            except (ValueError, IndexError):
                pass
    return sorted(ids)


def clear_map_checkpoints(checkpoint_dir: Path, map_ids: list[int]) -> int:
    """Delete ``MapNNN.done`` checkpoints for the specified map IDs.

    Returns the number of checkpoints actually deleted (IDs with no checkpoint on
    disk are silently ignored — they were already clear)."""
    deleted = 0
    for mid in map_ids:
        cp = checkpoint_dir / f"Map{mid:03d}.done"
        if cp.exists():
            cp.unlink()
            logger.debug("deleted checkpoint %s", cp.name)
            deleted += 1
    return deleted


def clear_orphan_porys(scripts_dir: Path, checkpoint_dir: Path) -> list[Path]:
    """Delete ``scripts/Map*.pory`` files whose corresponding checkpoint does not exist.

    A partial ``.pory`` produced by an interrupted mid-conversion run has no ``.done``
    checkpoint. It will be overwritten on the next run anyway, but keeping the stale
    partial around confuses downstream tooling that scans ``scripts/``. Returns the
    list of paths deleted."""
    deleted: list[Path] = []
    if not scripts_dir.is_dir():
        return deleted
    for pory in sorted(scripts_dir.glob("Map*.pory")):
        cp = checkpoint_dir / f"{pory.stem}.done"
        if not cp.exists():
            pory.unlink()
            deleted.append(pory)
            logger.debug("deleted orphan .pory %s", pory.name)
    return deleted


def clear_ce_checkpoints(checkpoint_dir: Path, ce_ids: set[int]) -> None:
    """Drop selected CE ids from the blocks ledger and delete ``CommonEvents.done``.

    The orchestrator's per-CE ledger (``checkpoints/CommonEvents.blocks.json``)
    records which CEs have been processed; on restart it skips those and only
    re-processes the rest. Dropping specific ids causes only those ids to be
    re-processed on the next run. ``CommonEvents.done`` is deleted so the
    orchestrator enters the CE pass at all (it short-circuits when the checkpoint
    exists)."""
    ledger_path = checkpoint_dir / "CommonEvents.blocks.json"
    done_path = checkpoint_dir / "CommonEvents.done"

    if ledger_path.is_file():
        try:
            ledger: dict[str, str | None] = json.loads(
                ledger_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            ledger = {}
        for ce_id in ce_ids:
            ledger.pop(str(ce_id), None)
            logger.debug("dropped CE %d from blocks ledger", ce_id)
        ledger_path.write_text(
            json.dumps(ledger, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    else:
        logger.debug("no CE blocks ledger found — nothing to patch")

    if done_path.exists():
        done_path.unlink()
        logger.debug("deleted CommonEvents.done")


def run_replay(
    out_dir: Path,
    maps_dir: Path,
    map_ids: list[int],
    backend_name: str = "claude_code",
    model: str = FROZEN_MODEL,
) -> tuple[int, int]:
    """Execute the NullBackend replay for cleared maps and/or common events.

    Builds the production backend (solely for its ``system_prompt`` / memo
    fingerprint), wraps it in a ``NullBackend`` (zero-spend guarantee), then runs
    ``convert_common_events`` (if the CE file exists) followed by ``convert_map``
    on exactly the selected *map_ids* — NOT ``convert_all``, which would walk
    into not-yet-converted maps and abort (and mutate memo/registry state for
    maps the bulk run hasn't reached).

    The memo fingerprint must match the production run or memo entries are discarded
    and every event needs a real spawn. For maps, memo/deterministic replay should
    cover all cleared events. For common events, CEs are not memoised, so the CE
    pass will raise ``BudgetReached`` on the first un-memoised event — the caller
    catches this, logs the fail-loud message, and directs the user to ``run_bulk.py``.

    Returns ``(maps_processed_count, ces_in_ledger)``.
    Raises ``BudgetReached`` if any event requires a real spawn."""
    fork = os.environ.get("RPG2GBA_POKEEMERALD")
    fork_path = Path(fork) if fork and Path(fork).is_dir() else None
    registry = pipeline._phase4_registry(out_dir, clean=False, fork_path=fork_path)

    real_backend = pipeline._phase4_backend(
        backend_name, model, usage_log_path=out_dir / "token_usage.jsonl"
    )
    null_backend = NullBackend(real_backend)
    orchestrator = orch.Orchestrator(null_backend, registry, out_dir)

    ces_in_ledger = 0
    ce_file = out_dir / "common_events.json"
    if ce_file.is_file():
        orchestrator.convert_common_events(ce_file)
        ledger_path = out_dir / "checkpoints" / "CommonEvents.blocks.json"
        if ledger_path.is_file():
            try:
                ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
                ces_in_ledger = len(ledger)
            except (json.JSONDecodeError, OSError):
                pass

    maps_count = 0
    for mid in map_ids:
        map_path = maps_dir / f"Map{mid:03d}.json"
        if not map_path.is_file():
            logger.warning("Map%03d.json not found in %s — skipped", mid, maps_dir)
            continue
        orchestrator.convert_map(map_path)
        maps_count += 1
    return maps_count, ces_in_ledger


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--maps",
        nargs="+",
        type=int,
        metavar="ID",
        default=[],
        help="Map ids to regenerate (e.g. --maps 1 2 3 4 5 6 7).",
    )
    ap.add_argument(
        "--all-done",
        action="store_true",
        help="Regenerate every map that has an existing .done checkpoint.",
    )
    ap.add_argument(
        "--ce",
        nargs="+",
        type=int,
        metavar="ID",
        default=[],
        help="Common event ids to drop from the ledger for re-conversion (e.g. --ce 4 5 6). "
        "Strip-listed CEs re-emit deterministic stubs here (zero spend); for normal CEs, "
        "run run_bulk.py afterwards to actually re-convert them (CEs are not memoised).",
    )
    ap.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    ap.add_argument(
        "--backend",
        default="claude_code",
        choices=["claude_code", "ollama"],
        help="Backend used only to derive the system_prompt memo fingerprint.",
    )
    ap.add_argument(
        "--model",
        default=FROZEN_MODEL,
        help="Model for the system_prompt fingerprint (must match the production run).",
    )
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG-level logging.",
    )
    args = ap.parse_args()

    # Validate selection BEFORE resolving paths so the tool gives a clean usage
    # error even when RPG2GBA_URANIUM_SRC is not set in the environment.
    if not args.maps and not args.all_done and not args.ce:
        ap.error("at least one of --maps, --all-done, or --ce is required")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pipeline._load_dotenv()
    _, out_dir = pipeline._resolve_paths()
    out_dir = Path(out_dir)
    maps_dir = out_dir / "maps"
    if not maps_dir.is_dir():
        logger.error("%s not found — run `phase3` first", maps_dir)
        return 2

    checkpoint_dir = out_dir / "checkpoints"
    scripts_dir = out_dir / "scripts"
    ce_ids: set[int] = set(args.ce)

    # Partition the requested CEs into strip-listed (re-emit deterministic stubs,
    # zero spend, complete here) vs normal (need a real spawn via run_bulk.py). The
    # strip path never touches the backend, so BudgetReached is NOT raised for them —
    # the messaging below must reflect that or it tells the user to run run_bulk.py
    # for CEs that are already done.
    strip_ces, _ = orch._load_strip_list(Path("reference"))
    stripped_ids = sorted(ce_ids & strip_ces.keys())
    normal_ids = sorted(ce_ids - strip_ces.keys())

    # Resolve the final map id list (explicit + all-done).
    map_ids = resolve_map_ids(checkpoint_dir, args.maps, args.all_done)

    # Print the plan before prompting.
    print(f"Targeted regen of {out_dir}:")
    if map_ids:
        print(f"  clear checkpoints : {[f'Map{i:03d}' for i in map_ids]}")
        print("  delete orphan .pory: Map*.pory with no checkpoint")
    if ce_ids:
        print(f"  patch CE ledger   : drop ids {sorted(ce_ids)}")
        print("  delete CommonEvents.done")
    print("  replay via NullBackend (memo/deterministic — zero LLM spend)")
    if stripped_ids:
        print(f"  strip-listed CEs  : {stripped_ids} → deterministic # STRIPPED: stubs, 0 spawns")
    if normal_ids:
        print(f"  NOTE: CEs {normal_ids} are not memoised — BudgetReached is expected;")
        print("        run run_bulk.py afterwards to actually re-convert them.")

    if not args.yes:
        reply = input("Proceed? type 'yes': ").strip().lower()
        if reply != "yes":
            print("aborted.")
            return 1

    # Phase 1: clear checkpoints and orphan .pory files.
    n_cp_deleted = clear_map_checkpoints(checkpoint_dir, map_ids)
    orphans = clear_orphan_porys(scripts_dir, checkpoint_dir)
    if ce_ids:
        clear_ce_checkpoints(checkpoint_dir, ce_ids)

    logger.info(
        "cleared %d map checkpoint(s), %d orphan .pory(s), %d CE ledger entr(ies)",
        n_cp_deleted,
        len(orphans),
        len(ce_ids),
    )

    # Phase 2: replay via NullBackend.
    try:
        _, _ = run_replay(
            out_dir, maps_dir, map_ids, backend_name=args.backend, model=args.model
        )
    except BudgetReached as exc:
        logger.error(
            "INCOMPLETE REGEN: an event was not covered by memo/deterministic "
            "and would require a real LLM spawn (NullBackend limit=%d). "
            "Checkpoints are held. Run `python scripts/run_bulk.py` to resume "
            "with real budget — it will finish any pending maps and/or re-convert "
            "CEs whose ledger entries were dropped.",
            exc.limit,
        )
        return 1

    print(
        f"\nregen complete: {n_cp_deleted} map checkpoint(s) cleared and replayed, "
        f"{len(ce_ids)} CE(s) prepared for re-conversion, "
        f"{len(orphans)} orphan .pory(s) deleted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
