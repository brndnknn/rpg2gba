"""Standalone CLI for the chapter runner (ROM_TEST_DEV C5(b)).

    python -m rpg2gba.playtest run --chapter CH01
    python -m rpg2gba.playtest run --chapter CH01 --from-beat B7
    python -m rpg2gba.playtest list
    python -m rpg2gba.playtest walk --chapter CH01 --at-beat B7
    python -m rpg2gba.playtest walk --chapter CH01 --at-end
    python -m rpg2gba.playtest seeds --chapter CH01
    python -m rpg2gba.playtest rules-lag
    python -m rpg2gba.playtest conformance --chapter CH04

This is the iteration-loop consumer of `runner.run_chapter`; the gate/CI
consumer is the thin pytest wrapper in `tests/test_runner.py`. Both drive the
same chapters and beats — this one just prints progress and artifact paths
as it goes, and exits non-zero only on a real (twice-failed) failure.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from .chapter import chapter_names, load_chapter
from .runner import DEFAULT_BEAT_TIMEOUT_S, RunnerError, run_chapter
from . import rules as playtest_rules
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
@click.option("--beat-timeout", type=int, default=DEFAULT_BEAT_TIMEOUT_S,
              help="Per-beat wall-clock hang budget in seconds (Q10). "
                   f"Default: {DEFAULT_BEAT_TIMEOUT_S}.")
@click.option("--suite", type=click.Choice(["hand", "gen"]), default="hand",
              show_default=True, help="Load the chapter from the hand-written "
                   "or beat-gen-generated module suite.")
def run(chapter: str, from_beat: str | None, rom: Path | None, engine: Path,
        output: Path | None, no_rerun: bool, beat_timeout: int, suite: str) -> None:
    """Run one chapter's beats headlessly; report pass/flake/fail."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rom = rom or engine / "pokeemerald.gba"
    output = output or Path("output") / "playtest"

    try:
        chap = load_chapter(chapter, suite=suite)
        result = run_chapter(chap, rom, engine, from_beat=from_beat,
                              output_root=output, rerun_on_failure=not no_rerun,
                              beat_timeout_s=beat_timeout)
    except (KeyError, RunnerError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(2)

    click.echo(f"chapter {result.chapter}: {result.verdict.upper()}")
    for attempt_no, attempt in enumerate(result.attempts, start=1):
        for beat in attempt.beats:
            marker = {"pass": "PASS", "fail": "FAIL", "hang": "HANG",
                      "not_run": "NOT_RUN"}[beat.status]
            click.echo(f"  attempt {attempt_no} [{marker}] {beat.name}: {beat.description}")
            if beat.error:
                click.echo(f"      {beat.error}")

    if result.tally:
        # Generated from the outcomes, never hand-assembled (§5.8): this is
        # the number that replaces the old hand-written "60/60" prose.
        click.echo(f"tally: {result.tally.render()}")
    if result.rule_set_version is not None:
        click.echo(f"rule-set version recorded: v{result.rule_set_version}")

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
@click.option("--suite", type=click.Choice(["hand", "gen"]), default="hand",
              show_default=True, help="Load the chapter from the hand-written "
                   "or beat-gen-generated module suite.")
def walk_cmd(chapter: str, at_beat: str | None, at_end: bool, rom: Path | None,
             engine: Path, output: Path | None, out: Path | None,
             verify: bool, suite: str) -> None:
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
        chap = load_chapter(chapter, suite=suite)
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
@click.option("--suite", type=click.Choice(["hand", "gen"]), default="hand",
              show_default=True, help="Load the chapter from the hand-written "
                   "or beat-gen-generated module suite.")
def seeds_cmd(chapter: str, rom: Path | None, engine: Path,
              output: Path | None, suite: str) -> None:
    """List seed blobs available to walk from for this chapter/ROM build."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rom = rom or engine / "pokeemerald.gba"
    output = output or Path("output") / "playtest"

    try:
        chap = load_chapter(chapter, suite=suite)
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


@cli.command("rules-lag")
def rules_lag() -> None:
    """Print the generated lag report (Q7.3): which chapters have not been
    re-verified against which rules added since they last gated green.

    Generated from `reference/playtest_rule_versions.json` -- written only
    by the runner (`run` above, on a full green run) -- and the live rule
    set in `rules.py`. This is Q7's ledger; nothing else maintains it.
    """
    reports = playtest_rules.lag_reports()
    if not reports:
        click.echo("no chapter has ever recorded a rule-set version yet")
        return
    for report in reports:
        click.echo(report.render())


@cli.command("conformance")
@click.option("--chapter", default=None,
              help="One chapter (default: every chapter with a run artifact).")
@click.option("--output", type=click.Path(path_type=Path), default=None,
              help="Output root the runner wrote to (default: output/playtest)")
def conformance(chapter: str | None, output: Path | None) -> None:
    """Print Q7's conformance report and Q8's carried contradictions.

    **There is no expectation table behind this, deliberately.** Q7's grill
    finding was that a conformance suite whose expected values come from
    the harness goes green when the harness lies -- the lying primitive and
    the lying oracle agree, and `interact()`'s stale sample would have
    passed a suite whose expectations `interact()` recorded. Only two
    independent oracles exist: decoded map data (Q13's offline graph) and a
    human reading a frame. So the conformance number here IS the count of
    places the harness's live reads disagreed with the offline graph over
    the run that actually happened, drawn from the same ledger the
    divergence check writes. One mechanism, not two (Q7 decision 2).

    Everything printed is a *carried* finding. None of it failed a run, and
    none of it is closed by reading this report -- closure is against an
    independent oracle (Q8 decision 3), never against another inference.
    """
    root = output or (Path("output") / "playtest")
    obs_dir = root / "observed_beats"
    if not obs_dir.is_dir():
        click.echo(f"no run artifacts under {obs_dir} — run a chapter first")
        return
    paths = sorted(obs_dir.glob("*.json"))
    if chapter is not None:
        paths = [p for p in paths if p.stem == chapter]
        if not paths:
            raise click.ClickException(
                f"no run artifact for chapter {chapter!r} under {obs_dir}")
    shown = 0
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        version = record.get("version")
        if version is None or int(version) < 2:
            click.echo(f"{path.stem}: schema v{version} predates the "
                        "conformance record — re-run the chapter")
            continue
        shown += 1
        conf = record.get("conformance") or {}
        click.echo(f"{path.stem}  (rom {str(record.get('rom_sha256'))[:8]}, "
                    f"{record.get('generated_at')})")
        click.echo(f"  oracle: {conf.get('oracle', '-')}  "
                    f"walkability disagreements: "
                    f"{conf.get('walkability_disagreements', 0)} "
                    f"over {conf.get('distinct_cells', 0)} distinct cells")
        for map_id, count in sorted((conf.get("by_map") or {}).items()):
            click.echo(f"    map {map_id}: {count}")
        carried = record.get("contradictions") or []
        if not carried:
            click.echo("  no carried contradictions")
            continue
        click.echo(f"  {len(carried)} carried contradiction(s):")
        for item in carried:
            beat = item.get("beat") or "-"
            click.echo(f"    [{item.get('kind')}] {beat}: {item.get('detail')}")
            click.echo(f"      model={item.get('model')!r} "
                        f"measurement={item.get('measurement')!r} "
                        f"assumed={item.get('assumption')!r} "
                        f"x{item.get('count', 1)}")
    if shown == 0:
        click.echo("nothing to report")


if __name__ == "__main__":
    cli()
