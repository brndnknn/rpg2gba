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
import subprocess
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
    result = subprocess.run(
        ["git", "rev-parse", f"HEAD:{repo_relative}"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Cannot resolve path for '{repo_relative}': "
            f"{result.stderr.strip()}")
    return result.stdout.strip()


def worktree_blob_sha(repo_relative: str) -> str:
    """Blob sha of `repo_relative` as it is on disk now
    (`git hash-object <path>`). Raises if git fails."""
    result = subprocess.run(
        ["git", "hash-object", f"{repo_relative}"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Cannot resolve path for '{repo_relative}': "
            f"{result.stderr.strip()}")
    return result.stdout.strip()


# --- capture (R1, R3) ----------------------------------------------------

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


def own_beats(chapter: str) -> list[dict[str, Any]]:
    """The chapter's own beats, in registration order, as R1's dicts:
    `name`, `order`, `group`, `map_constant`, `rows`."""
    own = [b for b in load_chapter(chapter).beats if not _INHERITED.match(b.name)]
    result: list[dict[str, Any]] = []
    for order, beat in enumerate(own):
        map_constant = beat.locations[0].map_constant if beat.locations else None
        result.append({
            "name": beat.name,
            "order": order,
            "group": beat.group,
            "map_constant": map_constant,
            "rows": list(beat.rows),
        })
    return result


def build_freeze() -> dict[str, Any]:
    """The whole freeze document (R1's shape), built in memory.

    Collect-then-raise: raises `FreezeError` listing EVERY problem (a module
    with uncommitted edits, a claimed row missing from its manifest) rather
    than stopping at the first. Never returns a partial document."""
    problems: list[str] = []
    sources: dict[str, dict[str, str]] = {}
    chapters: dict[str, list[dict[str, Any]]] = {}
    # A chapter's beats legitimately claim rows a predecessor's manifest owns
    # (CH02 re-walks map032, CH05 claims into map035): a row is known if any
    # manifest from CH01 up to this chapter carries it. Measured 2026-09-21.
    known: set[str] = set()
    for chapter in CHAPTERS:
        module = module_path(chapter)
        head = head_blob_sha(module)
        if worktree_blob_sha(module) != head:
            problems.append(
                f"{chapter}: {module} has uncommitted changes; a freeze of "
                "uncommitted code cannot name its own source")
        # A dirty module still gets its rows checked, so one run reports both.
        known |= manifest_row_ids(chapter)
        beats = own_beats(chapter)
        for beat in beats:
            for row in beat["rows"]:
                if row not in known:
                    problems.append(
                        f"{chapter}:{beat['name']} claims {row!r}, "
                        f"not in any manifest CH01..{chapter}")
        sources[chapter] = {"module": module, "blob_sha": head}
        chapters[chapter] = beats
    if problems:
        raise FreezeError("\n".join(problems))
    return {
        "schema": SCHEMA,
        "authored": AUTHORED,
        "rule": RULE,
        "sources": sources,
        "chapters": chapters,
    }


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
    problems: list[str] = []
    for chapter in CHAPTERS:
        old_sha = committed["sources"][chapter]["blob_sha"]
        new_sha = rebuilt["sources"][chapter]["blob_sha"]
        if old_sha != new_sha:
            problems.append(f"stale: {chapter} module changed since freeze")
        # Both are reported even when stale: the beat diff says WHAT changed,
        # which is what the operator needs to decide whether to re-freeze.
        old = {b["name"]: b for b in committed["chapters"][chapter]}
        new = {b["name"]: b for b in rebuilt["chapters"][chapter]}
        for name in sorted(old.keys() - new.keys()):
            problems.append(f"{chapter}:{name} frozen but no longer registered")
        for name in sorted(new.keys() - old.keys()):
            problems.append(f"{chapter}:{name} registered but not frozen")
        for name in sorted(old.keys() & new.keys()):
            if old[name] != new[name]:
                fields = sorted(k for k in old[name] if old[name][k] != new[name].get(k))
                problems.append(f"{chapter}:{name} differs from freeze ({', '.join(fields)})")
    return problems


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
    entry's chapter carries it, matching `build_freeze`."""
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
    manifest_ids = {ch: manifest_row_ids(ch) for ch in CHAPTERS}
    problems = (diff_freeze(committed, rebuilt)
                + validate_residue(committed, ledger, manifest_ids))
    for problem in problems:
        click.echo(problem, err=True)
    if problems:
        raise SystemExit(1)
    click.echo("hand-beat freeze OK")


if __name__ == "__main__":
    cli()
