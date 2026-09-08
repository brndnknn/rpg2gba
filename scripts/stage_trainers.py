"""Stage the pinned trainer pics + battles into `output/`, without touching `engine/`.

Companion to `scripts/stage_species.py`, and the second link in the staging
chain: species overlay -> trainer battles -> transpiler fork-index gate. Each
link reads the previous one's manifest, so run them in that order.

Calls `trainer_converter.stage.stage_slice`, which writes only under
`$RPG2GBA_OUTPUT/uranium-build/trainers/` (never into `engine/`) — the same
call `scripts/assemble_pathfinder.py`'s `run_trainer_pass` makes before it
copies generated headers into the fork. Use this when you have appended to
`trainer_converter.common.SLICE_TRAINER_BATTLES` / `SLICE_TRAINER_PICS` and
want the manifest refreshed before re-running the transpiler.

Since 2026-09-08 (`PROJECT_TODO.md` #83) a battle-staging failure is FATAL:
`stage_slice` raises `TrainerStagingError` listing every offending trainer
rather than logging a WARNING and returning a manifest with zero battles. The
manual "check the battle count, not the exit code" instruction that used to
live here is retired — the exit code is now trustworthy.

    python scripts/stage_trainers.py
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from rpg2gba.pipeline import _load_dotenv
from rpg2gba.trainer_converter import stage as trainer_stage

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    _load_dotenv()

    uranium_src = Path(os.environ["RPG2GBA_URANIUM_SRC"])
    out_dir = (
        Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build" / "trainers"
    )

    manifest_path = trainer_stage.stage_slice(uranium_src, out_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    battles = [t for t in manifest["trainers"] if t.get("kind") == "battle"]
    logger.info("trainer manifest: %s", manifest_path)
    logger.info("battle entries staged: %d", len(battles))
    if not battles:
        # Unreachable via a staging failure since #83 (stage_slice raises), but a
        # genuinely empty SLICE_TRAINER_BATTLES would land here. Still not a pass.
        logger.error("0 battles staged and no staging error — SLICE_TRAINER_BATTLES is empty?")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
