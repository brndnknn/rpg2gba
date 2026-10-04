"""The frozen CH01–CH05 hand beats: rows + identity (REDERIVATION_PLAN.md §16.3 C7).

`reference/frozen/hand_beats_ch01-ch05.json` is the grading target C9 holds
the generated suites to (R12 as amended 2026-09-17: every frozen row must be
claimed by some generated beat; order and group are recorded for review,
never graded).

The hand suites it was captured from were deleted after the C9/P11 gate
(2026-10-03), so the freeze is now a fixed artifact: there is nothing left to
re-capture it from, and the capture half of this module (`write`, the
blob-sha provenance, the rebuild-and-diff `check`) went with them. What
remains is the loader, the residue-ledger validation and the C9 grader.

Usage:

    .venv/bin/python -m rpg2gba.playtest.hand_freeze check
    .venv/bin/python -m rpg2gba.playtest.hand_freeze grade [--chapter CHnn]
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_PATH = REPO_ROOT / "reference" / "frozen" / "hand_beats_ch01-ch05.json"
RESIDUE_PATH = REPO_ROOT / "reference" / "frozen" / "hand_beats_residue.json"
CHAPTERS = ("CH01", "CH02", "CH03", "CH04", "CH05")
AUTHORED = "2026-09-18"
SCHEMA = 1
RULE = ("REDERIVATION_PLAN.md §16.3 R12 (amended 2026-09-17): "
        "rows + identity; order/group recorded, not graded")

@dataclass(frozen=True)
class FrozenBeat:
    chapter: str
    name: str
    order: int
    group: str | None
    map_constant: str | None
    rows: tuple[str, ...]


def manifest_row_ids(chapter: str) -> set[str]:
    """Every `row_id` in `reference/manifests/<chapter>.manifest.json`,
    read as raw JSON."""
    path = REPO_ROOT / "reference" / "manifests" / f"{chapter.upper()}.manifest.json"
    ids: set[str] = set()
    for row in _read_json(path):
        row_id = row["row_id"]
        if row_id in ids:
            raise ValueError(
                f"{chapter}: duplicate row_id {row_id!r} in {path.name} "
                "-- data defect, refusing to merge silently")
        ids.add(row_id)
    return ids


# The ruling vocabulary as data: ruling -> the extra fields it requires
# (REDERIVATION_PLAN.md §16.3 "DECIDED 2026-09-18"). `note` is required of all.
RESIDUE_SCHEMA = 1
RESIDUE_RULINGS: dict[str, tuple[str, ...]] = {
    "arrival_floor": ("rows",),
    "bgm_debt": (),
    "blocked_obstacle": ("rows",),
    "state_model": ("rows",),
    "covered_elsewhere": ("rows",),
    "build_check": ("cites",),
    "retired": ("cites",),
    "not_residue": (),
    "open": ("question",),
}


def validate_residue(
    frozen: dict[str, Any],
    ledger: dict[str, Any] | None,
    manifest_ids: dict[str, set[str]],
) -> list[str]:
    """Problems with the residue ledger, one string each; `[]` means clean.

    Every frozen beat with `rows == []` needs exactly one ledger entry, and
    every entry must name such a beat, use a known ruling, carry that
    ruling's extra fields plus a `note`, and cite only manifest rows. Pure:
    `manifest_ids` (chapter -> row ids) is a parameter so callers and tests
    control the I/O. A row is known if any manifest from CH01 up to the
    entry's chapter carries it."""
    rowless: set[str] = set()
    rowed: set[str] = set()
    for chapter, beats in frozen["chapters"].items():
        for beat in beats:
            (rowed if beat["rows"] else rowless).add(f"{chapter}:{beat['name']}")

    if ledger is None:
        if not rowless:
            return []
        return [f"residue ledger {RESIDUE_PATH.name} missing, but "
                f"{len(rowless)} frozen beats claim no rows"]

    problems: list[str] = []
    if ledger.get("schema") != RESIDUE_SCHEMA:
        problems.append(
            f"residue ledger schema {ledger.get('schema')!r}, expected {RESIDUE_SCHEMA}")
    entries: dict[str, dict[str, Any]] = ledger.get("entries", {})

    for key in sorted(rowless - entries.keys()):
        problems.append(f"{key} claims no rows and has no residue ledger entry")
    for key in sorted(entries):
        if key in rowless:
            problems.extend(_entry_problems(key, entries[key], manifest_ids))
        elif key in rowed:
            problems.append(f"{key}: stale ledger entry -- the beat now claims rows")
        else:
            problems.append(f"{key}: ledger entry names a beat that is not frozen")
    return problems


def _entry_problems(
    key: str, entry: dict[str, Any], manifest_ids: dict[str, set[str]],
) -> list[str]:
    """Field-level problems for one ledger entry whose beat is rowless."""
    ruling = entry.get("ruling")
    if ruling not in RESIDUE_RULINGS:
        # Unknown ruling: its required fields are unknowable, so stop here.
        return [f"{key}: unknown ruling {ruling!r}"]
    problems = [
        f"{key}: ruling {ruling!r} requires {field!r}"
        for field in ("note", *RESIDUE_RULINGS[ruling])
        if not entry.get(field)  # absent and empty are the same defect
    ]
    chapter = key.partition(":")[0]
    known: set[str] = set()
    for ch in CHAPTERS[:CHAPTERS.index(chapter) + 1]:
        known |= manifest_ids.get(ch, set())
    problems.extend(
        f"{key}: row {row!r} not in any manifest CH01..{chapter}"
        for row in entry.get("rows", ()) if row not in known
    )
    return problems


# --- downstream loader (R5) ----------------------------------------------

def load_frozen_hand_beats(path: Path = FROZEN_PATH) -> list[FrozenBeat]:
    """Every frozen hand beat, CH01 first, in order. Raises on a `schema`
    this code doesn't know."""
    data = _read_json(path)
    if data.get("schema") != SCHEMA:
        raise ValueError(
            f"{path}: unknown freeze schema {data.get('schema')!r}, expected {SCHEMA}")
    # Walk CHAPTERS, not file order: the promised "CH01 first" survives a
    # reordered file, and a missing chapter raises KeyError instead of vanishing.
    return [
        FrozenBeat(
            chapter=chapter, name=b["name"], order=b["order"], group=b["group"],
            map_constant=b["map_constant"], rows=tuple(b["rows"]),
        )
        for chapter in CHAPTERS
        for b in data["chapters"][chapter]
    ]


# --- CLI ------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@click.group()
def cli() -> None:
    """Check the frozen CH01–CH05 hand beats and grade the generated suites (C7/C9)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@cli.command()
def check() -> None:
    """Validate the committed freeze's residue ledger; exit 1 on any problem."""
    if not FROZEN_PATH.exists():
        raise click.ClickException(f"{FROZEN_PATH.relative_to(REPO_ROOT)} missing")
    committed = _read_json(FROZEN_PATH)
    ledger = _read_json(RESIDUE_PATH) if RESIDUE_PATH.exists() else None
    manifest_ids = {ch: manifest_row_ids(ch) for ch in CHAPTERS}
    problems = validate_residue(committed, ledger, manifest_ids)
    for problem in problems:
        click.echo(problem, err=True)
    if problems:
        raise SystemExit(1)
    click.echo("hand-beat freeze OK")


@cli.command()
@click.option("--chapter", default=None,
              help="Grade one chapter (e.g. CH05). Omit to grade every "
                   "chapter with a generated module.")
def grade(chapter: str | None) -> None:
    """C9 grader: does the generated suite cover the frozen hand suite?
    (`freeze_grade.grade_chapter_from_disk`.) Exits 1 on any problem."""
    from rpg2gba.playtest import freeze_grade
    from rpg2gba.playtest.chapter import gen_chapter_names

    if chapter is not None:
        chapters = [chapter.upper()]
    else:
        chapters = [name.upper() for name in gen_chapter_names()]
        if not chapters:
            click.echo("no generated chapters")
            return

    any_problems = False
    for ch in chapters:
        result = freeze_grade.grade_chapter_from_disk(ch)
        if result.problems:
            any_problems = True
            click.echo(f"{ch}: {len(result.problems)} problem(s)")
            for problem in result.problems:
                click.echo(f"  {problem}")
        else:
            click.echo(f"{ch}: OK")
        # Reported, never failed (C9 rulings 6 and 9). The count is enough
        # here; the chapter's review doc lists the rows.
        for line in result.deferred:
            click.echo(f"  deferred: {line}")
        if result.generator_only_partial:
            click.echo(f"  info: {len(result.generator_only_partial)} generator-only "
                       "row(s) with partial floor coverage (tracked in the review doc)")
    if any_problems:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
