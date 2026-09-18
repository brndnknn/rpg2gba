"""Freeze CH01–CH05's hand beats: rows + identity (REDERIVATION_PLAN.md §16.3 C7).

Writes `reference/frozen/hand_beats_ch01-ch05.json`, the grading target C9
holds the generated suites to (R12 as amended 2026-09-17: every frozen row
must be claimed by some generated beat; order and group are recorded for
review, never graded).

Only each chapter's OWN beats are frozen. `load_chapter` returns a composed
list in which predecessor beats arrive renamed `CHnn:Bn`; those are frozen
once, under the chapter that owns them.

Usage:

    .venv/bin/python -m rpg2gba.playtest.hand_freeze write [--force]
    .venv/bin/python -m rpg2gba.playtest.hand_freeze check

STATUS: stub. The CLI (bottom of file) is complete; every function marked
`NotImplementedError` is the assignment (`assignments/C7/01_freeze_capture.md`).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess  # noqa: F401  -- you'll need it for the git helpers
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from rpg2gba.playtest.chapter import load_chapter  # noqa: F401  -- used by own_beats

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_PATH = REPO_ROOT / "reference" / "frozen" / "hand_beats_ch01-ch05.json"
RESIDUE_PATH = REPO_ROOT / "reference" / "frozen" / "hand_beats_residue.json"
CHAPTERS = ("CH01", "CH02", "CH03", "CH04", "CH05")
AUTHORED = "2026-09-18"
SCHEMA = 1
RULE = ("REDERIVATION_PLAN.md §16.3 R12 (amended 2026-09-17): "
        "rows + identity; order/group recorded, not graded")

# A predecessor's beats arrive under a `CHnn:` name prefix; own beats are bare.
_INHERITED = re.compile(r"^CH\d\d:")


class FreezeError(Exception):
    """One or more problems that make a freeze unsafe to write. The message
    lists every problem found, one per line (collect, then raise)."""


@dataclass(frozen=True)
class FrozenBeat:
    chapter: str
    name: str
    order: int
    group: str | None
    map_constant: str | None
    rows: tuple[str, ...]


def module_path(chapter: str) -> str:
    """Repo-relative path of a chapter's hand module."""
    return f"src/rpg2gba/playtest/chapters/{chapter.lower()}.py"


# --- git provenance (R2) -------------------------------------------------

def head_blob_sha(repo_relative: str) -> str:
    """Blob sha of `repo_relative` as committed at HEAD
    (`git rev-parse HEAD:<path>`). Raises if git can't resolve it."""
    raise NotImplementedError


def worktree_blob_sha(repo_relative: str) -> str:
    """Blob sha of `repo_relative` as it is on disk now
    (`git hash-object <path>`). Raises if git fails."""
    raise NotImplementedError


# --- capture (R1, R3) ----------------------------------------------------

def manifest_row_ids(chapter: str) -> set[str]:
    """Every `row_id` in `reference/manifests/<chapter>.manifest.json`,
    read as raw JSON."""
    raise NotImplementedError


def own_beats(chapter: str) -> list[dict[str, Any]]:
    """The chapter's own beats, in registration order, as R1's dicts:
    `name`, `order`, `group`, `map_constant`, `rows`."""
    raise NotImplementedError


def build_freeze() -> dict[str, Any]:
    """The whole freeze document (R1's shape), built in memory.

    Collect-then-raise: raises `FreezeError` listing EVERY problem (a module
    with uncommitted edits, a claimed row missing from its manifest) rather
    than stopping at the first. Never returns a partial document."""
    raise NotImplementedError


def dump(data: dict[str, Any]) -> str:
    """Byte-stable serialisation. Already done -- don't change it without a
    reason, or every committed freeze diffs."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --- check (R4) ----------------------------------------------------------

def diff_freeze(committed: dict[str, Any], rebuilt: dict[str, Any]) -> list[str]:
    """Problems with the committed freeze, one string each; `[]` means clean.

    Report (a) any chapter whose `sources[ch].blob_sha` differs between the
    two ("stale: CHnn module changed since freeze"), and (b) any chapter
    whose beat list differs. Pure function: no I/O."""
    raise NotImplementedError


def validate_residue(
    frozen: dict[str, Any], ledger: dict[str, Any] | None,
) -> list[str]:
    """Task 2 hook. Until Task 2, the only rule: a missing ledger (`None`)
    while any frozen beat has `rows == []` is one problem. Task 2 replaces
    the body with the full validation."""
    raise NotImplementedError


# --- downstream loader (R5) ----------------------------------------------

def load_frozen_hand_beats(path: Path = FROZEN_PATH) -> list[FrozenBeat]:
    """Every frozen hand beat, CH01 first, in order. Raises on a `schema`
    this code doesn't know."""
    raise NotImplementedError


# --- CLI (wired; you shouldn't need to edit below) -----------------------

def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@click.group()
def cli() -> None:
    """Freeze and check CH01–CH05's hand beats (C7)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite an existing freeze file.")
def write(force: bool) -> None:
    """Build the freeze and write it. Writes nothing if any problem is found."""
    if FROZEN_PATH.exists() and not force:
        raise click.ClickException(
            f"{FROZEN_PATH.relative_to(REPO_ROOT)} exists; pass --force to overwrite")
    try:
        data = build_freeze()
    except FreezeError as exc:
        raise click.ClickException(f"freeze NOT written:\n{exc}") from exc
    FROZEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    FROZEN_PATH.write_text(dump(data), encoding="utf-8")
    total = sum(len(beats) for beats in data["chapters"].values())
    logger.info("wrote %s (%d beats)", FROZEN_PATH.relative_to(REPO_ROOT), total)


@cli.command()
def check() -> None:
    """Rebuild in memory and compare with the committed freeze; exit 1 on any problem."""
    if not FROZEN_PATH.exists():
        raise click.ClickException(
            f"{FROZEN_PATH.relative_to(REPO_ROOT)} missing; run `write` first")
    committed = _read_json(FROZEN_PATH)
    try:
        rebuilt = build_freeze()
    except FreezeError as exc:
        raise click.ClickException(f"cannot rebuild freeze:\n{exc}") from exc
    ledger = _read_json(RESIDUE_PATH) if RESIDUE_PATH.exists() else None
    problems = diff_freeze(committed, rebuilt) + validate_residue(committed, ledger)
    for problem in problems:
        click.echo(problem, err=True)
    if problems:
        raise SystemExit(1)
    click.echo("hand-beat freeze OK")


if __name__ == "__main__":
    cli()
