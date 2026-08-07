"""Standalone CLI for the chapter runner (ROM_TEST_DEV C5(b)).

    python -m rpg2gba.playtest run --chapter moki
    python -m rpg2gba.playtest run --chapter moki --from-beat B7
    python -m rpg2gba.playtest list
    python -m rpg2gba.playtest walk --chapter moki --at-beat B7
    python -m rpg2gba.playtest walk --chapter moki --at-end
    python -m rpg2gba.playtest seeds --chapter moki

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
from . import walk

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


@cli.command("walk")
@click.option("--chapter", required=True, help="Chapter name (see `list`).")
@click.option("--at-beat", default=None,
              help="Walk to the state just before this beat.")
@click.option("--at-end", is_flag=True,
              help="Walk to the chapter-complete state.")
@click.option("--rom", type=click.Path(exists=True, path_type=Path), default=None,
              help="Pristine ROM (default: <engine>/pokeemerald.gba)")
@click.option("--engine", type=click.Path(exists=True, path_type=Path),
              envvar="RPG2GBA_POKEEMERALD", required=True,
              help="Engine build dir (map/elf must match the ROM)")
@click.option("--output", type=click.Path(path_type=Path), default=None,
              help="Output root for artifacts (default: output/playtest)")
@click.option("--out", type=click.Path(path_type=Path), default=None,
              help="Destination ROM path (default: <output>/walk/<chapter>-<beat>.gba "
                   "or <output>/walk/<chapter>-complete.gba)")
@click.option("--verify/--no-verify", default=True,
              help="Verify by booting the built ROM with a foreign save paired, "
                   "to prove the embedded state wins over any .sav residue on "
                   "the target device.")
def walk_cmd(chapter: str, at_beat: str | None, at_end: bool, rom: Path | None,
             engine: Path, output: Path | None, out: Path | None,
             verify: bool) -> None:
    """Build a bootable ROM positioned at a chosen point in a chapter.

    Patches an embedded-save seed blob into a copy of the pristine ROM so it
    boots straight into that state on a real device ("boot walk"). Seeds are
    keyed by the ROM's sha256 and invalidated by any ROM rebuild.

    Verification (on by default) boots the built ROM with a deliberately
    foreign save file paired, to prove the embedded state wins over any
    .sav residue already on the target device.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if bool(at_beat) == bool(at_end):
        click.echo("error: specify exactly one of --at-beat or --at-end", err=True)
        sys.exit(2)

    rom = rom or engine / "pokeemerald.gba"
    output = output or Path("output") / "playtest"

    if out is None:
        suffix = at_beat if at_beat else "complete"
        out = output / "walk" / f"{chapter}-{suffix}.gba"
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        chap = load_chapter(chapter)
        seed = walk.build_walk_rom(output, chap, rom, engine, at_beat=at_beat,
                                    at_end=at_end, out=out, verify=verify)
    except (KeyError, RunnerError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(2)

    target = f"before {seed.beat}" if seed.beat else "chapter complete"
    click.echo(f"seed: {seed.kind} ({target})")
    click.echo(f"  map_location={seed.map_location} player_pos={seed.player_pos}")
    click.echo(f"  created: {seed.created}")
    click.echo(f"verified: {'yes' if verify else 'no'}")
    click.echo(f"walk ROM: {out}")

    sys.exit(0)


@cli.command("seeds")
@click.option("--chapter", required=True, help="Chapter name (see `list`).")
@click.option("--rom", type=click.Path(exists=True, path_type=Path), default=None,
              help="Pristine ROM (default: <engine>/pokeemerald.gba)")
@click.option("--engine", type=click.Path(exists=True, path_type=Path),
              envvar="RPG2GBA_POKEEMERALD", required=True,
              help="Engine build dir (map/elf must match the ROM)")
@click.option("--output", type=click.Path(path_type=Path), default=None,
              help="Output root for artifacts (default: output/playtest)")
def seeds_cmd(chapter: str, rom: Path | None, engine: Path,
              output: Path | None) -> None:
    """List seed blobs available to walk from for this chapter/ROM build."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rom = rom or engine / "pokeemerald.gba"
    output = output or Path("output") / "playtest"

    try:
        chap = load_chapter(chapter)
        available = walk.available_seeds(output, chap, rom)
    except (KeyError, RunnerError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(2)

    if not available:
        click.echo("no seeds for this ROM build (seeds are invalidated by any "
                    "ROM rebuild) — run the chapter green from the start first: "
                    f"`run --chapter {chapter}`")
        sys.exit(0)

    for seed in available:
        label = seed.beat if seed.beat else "complete"
        click.echo(f"{label}  [{seed.kind}]  map_location={seed.map_location} "
                   f"player_pos={seed.player_pos}  created={seed.created}")

    sys.exit(0)


if __name__ == "__main__":
    cli()
