"""Standalone CLI for the chapter runner (ROM_TEST_DEV C5(b)).

    python -m rpg2gba.playtest run --chapter moki
    python -m rpg2gba.playtest run --chapter moki --from-beat B7
    python -m rpg2gba.playtest list

This is the iteration-loop consumer of `runner.run_chapter`; the gate/CI
consumer is the thin pytest wrapper in `tests/test_runner.py`. Both drive the
same chapters and beats — this one just prints progress and artifact paths
as it goes, and exits non-zero only on a real (twice-failed) failure.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from .chapter import chapter_names, load_chapter
from .runner import RunnerError, run_chapter

logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """rpg2gba chapter playtest runner."""


@cli.command("list")
def list_chapters() -> None:
    """List available chapters and their beats."""
    names = chapter_names()
    if not names:
        click.echo("no chapters found under rpg2gba.playtest.chapters")
        return
    for name in names:
        chapter = load_chapter(name)
        click.echo(f"{chapter.name}  ({chapter.doc})")
        for beat in chapter.beats:
            click.echo(f"  {beat.name}: {beat.description}")


@cli.command("run")
@click.option("--chapter", required=True, help="Chapter name (see `list`).")
@click.option("--from-beat", default=None,
              help="Seed from a prior green run's blob and start at this beat "
                   "(iteration only — the gate/CI wrapper never sets this).")
@click.option("--rom", type=click.Path(exists=True, path_type=Path), default=None,
              help="Pristine ROM (default: <engine>/pokeemerald.gba)")
@click.option("--engine", type=click.Path(exists=True, path_type=Path),
              envvar="RPG2GBA_POKEEMERALD", required=True,
              help="Engine build dir (map/elf must match the ROM)")
@click.option("--output", type=click.Path(path_type=Path), default=None,
              help="Output root for artifacts (default: output/playtest)")
@click.option("--no-rerun", is_flag=True,
              help="Disable the F3 auto-rerun-once flake check.")
def run(chapter: str, from_beat: str | None, rom: Path | None, engine: Path,
        output: Path | None, no_rerun: bool) -> None:
    """Run one chapter's beats headlessly; report pass/flake/fail."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rom = rom or engine / "pokeemerald.gba"
    output = output or Path("output") / "playtest"

    try:
        chap = load_chapter(chapter)
        result = run_chapter(chap, rom, engine, from_beat=from_beat,
                              output_root=output, rerun_on_failure=not no_rerun)
    except (KeyError, RunnerError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(2)

    click.echo(f"chapter {result.chapter}: {result.verdict.upper()}")
    for attempt_no, attempt in enumerate(result.attempts, start=1):
        for beat in attempt.beats:
            marker = "PASS" if beat.status == "pass" else "FAIL"
            click.echo(f"  attempt {attempt_no} [{marker}] {beat.name}: {beat.description}")
            if beat.error:
                click.echo(f"      {beat.error}")

    if result.stamped_rom:
        click.echo(f"green review ROM: {result.stamped_rom}")
    if result.flake_log:
        click.echo(f"flake logged (harness bug, not a game bug): {result.flake_log}")
    if result.bundle_dir:
        click.echo(f"repro bundle: {result.bundle_dir}")
    for page in result.contact_sheet:
        click.echo(f"contact sheet (by-eye review): {page}")

    sys.exit(0 if result.verdict in ("pass", "flake") else 1)


if __name__ == "__main__":
    cli()
