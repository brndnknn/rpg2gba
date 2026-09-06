"""Stage the pinned species overlay into `output/`, without touching `engine/`.

There is no CLI for species staging: the sanctioned path is
`scripts/assemble_pathfinder.py` (its `--skip-species` flag guards
`run_species_pass`), which also runs the battler/icon/cry art converters and
copies the results into `$RPG2GBA_POKEEMERALD`. That is the right command when
you are building a ROM.

This script is the narrow version for the *staging chain* — it calls the same
`species_converter.stage.write_all` but writes only under
`$RPG2GBA_OUTPUT/uranium-build/species/`, which is all that
`trainer_converter.stage.stage_slice` and the transpiler's fork-index gate
actually read. Use it when you have appended to `common.STARTER_SPECIES` and
want the manifest refreshed before re-running the transpiler, without paying
for the art passes (step 7's assembler re-runs them anyway).

Idempotent (CLAUDE.md §4.2): re-running from scratch reproduces the same
manifest from the same inputs.

    python scripts/stage_species.py
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from rpg2gba.pipeline import _load_dotenv
from rpg2gba.species_converter import stage as species_stage
from rpg2gba.species_converter.common import SPECIES_OUT_SUBDIR

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    _load_dotenv()

    uranium_src = Path(os.environ["RPG2GBA_URANIUM_SRC"])
    engine_dir = Path(os.environ["RPG2GBA_POKEEMERALD"])
    out_dir = (
        Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
        / "uranium-build"
        / SPECIES_OUT_SUBDIR
    )

    manifest = species_stage.write_all(
        uranium_src=uranium_src,
        engine_dir=engine_dir,
        out_dir=out_dir,
    )
    logger.info("species staged: %d -> %s", len(manifest["species"]), out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
