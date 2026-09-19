"""`python -m rpg2gba.beat_gen generate --chapter CHnn` (C6 Task 9).

Ties the stages together and writes, under `--out-dir` (default
`output/beats/`):

    chNN.generated.py   the module (emit.py)
    CHnn.review.md      the review doc (review.py)
    CHnn.route.json     the solved route (routing.plan.write_plan)

Output lands in `output/` by ruling (C6 plan B1): C9, not C6, owns putting
a generated module under `playtest/chapters/` and a route under
`reference/routes/`.

STATUS: stub (`assignments/C6/09_cli.md`). The click wiring is done; the
two functions above it are the task.
"""
from __future__ import annotations

import logging
from pathlib import Path

import click

from rpg2gba.beat_gen.plan import ChapterPlan

logger = logging.getLogger(__name__)

BUILD_DIR = Path("output/uranium-build")
DEFAULT_OUT_DIR = Path("output/beats")


def build_plan(chapter_id: str, *, build_dir: Path = BUILD_DIR) -> ChapterPlan:
    """Run stages 1-4 for one chapter and return the fully decided plan."""
    raise NotImplementedError


def write_outputs(plan: ChapterPlan, out_dir: Path, *, build_dir: Path = BUILD_DIR) -> list[Path]:
    """Write the three artifacts; return their paths in a fixed order
    (module, review, route). Overwrites; must be byte-identical on re-run."""
    raise NotImplementedError


@click.group()
def cli() -> None:
    """The C6 beat generator."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@cli.command()
@click.option("--chapter", "chapter_id", required=True, help="e.g. CH05")
@click.option("--out-dir", type=click.Path(path_type=Path), default=DEFAULT_OUT_DIR,
              show_default=True)
def generate(chapter_id: str, out_dir: Path) -> None:
    """Generate one chapter's module, review doc and route."""
    plan = build_plan(chapter_id)
    for path in write_outputs(plan, out_dir):
        logger.info("wrote %s", path)
    if plan.refusals:
        logger.warning("%s: %d rows refused -- see the review doc",
                       chapter_id, len(plan.refusals))


if __name__ == "__main__":
    cli()
