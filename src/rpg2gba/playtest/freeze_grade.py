"""C9 grader: does a generated chapter suite cover the frozen hand suite?
(REDERIVATION_PLAN.md §16.3 C9 rulings, R12 amended 2026-09-17.)

Two rules, both scoped to ONE chapter's OWN generated beats (inherited
`<OWNER>:` beats are ignored on both sides -- R12 amended says order,
grouping and which chapter replays what are recorded, never graded):

(a) **Row coverage.** Every row a frozen hand beat of this chapter claims
    (`reference/frozen/hand_beats_ch01-ch05.json`, `hand_freeze.
    load_frozen_hand_beats`), plus every row cited by a rows-carrying
    residue-ledger entry for this chapter (`reference/frozen/
    hand_beats_residue.json`, rulings `arrival_floor`/`blocked_obstacle`/
    `state_model`/`covered_elsewhere`), must be claimed by some OWN beat of
    the generated chapter, or proven `never_fires` by the generated
    module's `NEVER_FIRES` dict (C9 ruling 3 -- a proof, not an exception).

(b) **Floor ⊇.** For every row the generated chapter's own beats claim, the
    union of those beats' declared assertions for that row must cover the
    row's generic floor (`beat_floor.lookup.floor_for_row`), using the same
    ⊇ comparison `chapter_manifest.checker._check_floor_coverage` uses --
    `beat_floor.coverage.uncovered`/`contradicts` -- not a second one. A row
    whose claiming beats all declare `None` (undeclared) is a problem for a
    generated module (unlike a hand module, which only warns). A row whose
    floor itself refuses is reported distinctly: it should not have been
    claimed at all.

This module is pure logic over injected data (`grade_chapter`); I/O lives
only in `grade_chapter_from_disk`, the thin loader the CLI and the real-
data test call.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor
from rpg2gba.beat_floor.coverage import contradicts, uncovered
from rpg2gba.beat_floor.lookup import default_build_dir, floor_for_row
from rpg2gba.playtest.chapter import Beat, Chapter, load_chapter, load_chapter_module
from rpg2gba.playtest.hand_freeze import (
    FROZEN_PATH,
    RESIDUE_PATH,
    FrozenBeat,
    load_frozen_hand_beats,
)

logger = logging.getLogger(__name__)

#: Residue rulings that cite manifest rows (RESIDUE_RULINGS in hand_freeze.py
#: -- the ones whose extra-fields tuple is `("rows",)`). A row cited by one
#: of these entries is still owed coverage in the generated suite; the other
#: rulings (`retired`, `bgm_debt`, `build_check`, `not_residue`) name no rows
#: and need nothing graded.
_ROWED_RESIDUE_RULINGS = frozenset(
    {"arrival_floor", "blocked_obstacle", "state_model", "covered_elsewhere"})


def _own_beats(chapter: Chapter) -> tuple[Beat, ...]:
    """This chapter's own beats -- inherited `<OWNER>:` beats excluded, per
    R12 amended: routing/replay is not graded, only what this chapter's own
    generated beats claim and declare."""
    return tuple(b for b in chapter.beats if ":" not in b.name)


def _claimed_by_own(own_beats: Sequence[Beat]) -> dict[str, list[Beat]]:
    claimed: dict[str, list[Beat]] = {}
    for beat in own_beats:
        for row_id in beat.rows:
            claimed.setdefault(row_id, []).append(beat)
    return claimed


def _required_rows(
    chapter_id: str,
    frozen_beats: Sequence[FrozenBeat],
    residue_entries: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[str]]:
    """Every row this chapter's generated suite owes coverage for, mapped to
    the frozen-beat/residue-entry name(s) that require it (for the problem
    message)."""
    required: dict[str, list[str]] = {}
    for beat in frozen_beats:
        if beat.chapter != chapter_id:
            continue
        for row_id in beat.rows:
            required.setdefault(row_id, []).append(f"{chapter_id}:{beat.name}")
    for key, entry in residue_entries.items():
        entry_chapter, _, _name = key.partition(":")
        if entry_chapter != chapter_id:
            continue
        if entry.get("ruling") not in _ROWED_RESIDUE_RULINGS:
            continue
        for row_id in entry.get("rows", ()):
            required.setdefault(row_id, []).append(f"{key} (residue)")
    return required


def _check_row_coverage(
    chapter_id: str,
    required_rows: Mapping[str, list[str]],
    claimed_by_own: Mapping[str, list[Beat]],
    never_fires: Mapping[str, str],
) -> list[str]:
    # A beat asserting a row and a proof that the row never runs cannot both
    # be right; whichever is wrong, the generator emitted a contradiction.
    problems: list[str] = [
        f"{chapter_id}: row {row_id!r} is claimed by "
        f"{[b.name for b in claimed_by_own[row_id]]} AND listed in NEVER_FIRES"
        for row_id in sorted(set(claimed_by_own) & set(never_fires))
    ]
    for row_id, sources in sorted(required_rows.items()):
        if row_id in claimed_by_own or row_id in never_fires:
            continue
        problems.append(
            f"{chapter_id}: row {row_id!r}, claimed by {sources}, is not "
            f"claimed by any own beat of the generated {chapter_id} and is "
            "not in NEVER_FIRES")
    return problems


def _uncovered_message(row_id: str, beat_names: list[str], floor: RowFloor,
                        declared: frozenset[FloorAssertion]) -> str:
    missing = uncovered(floor, declared)
    contradicted = [f for f in missing if any(contradicts(d, f) for d in declared)]
    plain_missing = [f for f in missing if f not in contradicted]
    parts = []
    if contradicted:
        parts.append(
            f"declared assertion(s) contradict the floor: {list(contradicted)}")
    if plain_missing:
        parts.append(f"floor assertion(s) not declared at all: {list(plain_missing)}")
    return (f"{row_id}: claimed by {beat_names} but does not cover its floor -- "
            + "; ".join(parts))


def _check_floor_ge(
    chapter_id: str, claimed_by_own: Mapping[str, list[Beat]], *, build_dir: Path,
) -> list[str]:
    problems: list[str] = []
    for row_id, beats in sorted(claimed_by_own.items()):
        beat_names = [b.name for b in beats]
        try:
            floor = floor_for_row(row_id, build_dir=build_dir)
        except KeyError as exc:
            problems.append(
                f"{chapter_id}: row {row_id!r}, claimed by {beat_names}, has "
                f"no generic floor at all ({exc})")
            continue

        if floor.refused:
            problems.append(
                f"{chapter_id}: row {row_id!r} is claimed by {beat_names}, "
                f"but its floor refuses ({[r.reason for r in floor.refusals]}) "
                "-- a refused row is the generator's own blocker and should "
                "not have been claimed")
            continue

        declaring = [b for b in beats if b.assertions is not None]
        if not declaring:
            problems.append(
                f"{chapter_id}: row {row_id!r} is claimed by {beat_names}, "
                "but none of them declares assertions (undeclared claim in a "
                "generated module)")
            continue

        declared = frozenset(
            a for b in declaring for a in b.assertions if a.row_id == row_id)
        if uncovered(floor, declared):
            problems.append(_uncovered_message(row_id, beat_names, floor, declared))
    return problems


def grade_chapter(
    chapter_id: str,
    *,
    frozen_beats: Sequence[FrozenBeat],
    residue_entries: Mapping[str, Mapping[str, Any]],
    gen_chapter: Chapter,
    never_fires: Mapping[str, str],
    build_dir: Path,
) -> list[str]:
    """Pure grade of one chapter. `[]` means the generated suite covers the
    frozen hand suite for `chapter_id`. All inputs are already loaded;
    `grade_chapter_from_disk` is the I/O wrapper real callers use."""
    own_beats = _own_beats(gen_chapter)
    claimed_by_own = _claimed_by_own(own_beats)

    required_rows = _required_rows(chapter_id, frozen_beats, residue_entries)
    problems = _check_row_coverage(chapter_id, required_rows, claimed_by_own, never_fires)
    problems += _check_floor_ge(chapter_id, claimed_by_own, build_dir=build_dir)
    return problems


def _load_residue_entries(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, dict[str, Any]] = data.get("entries", {})
    return entries


def grade_chapter_from_disk(
    chapter_id: str, *,
    build_dir: Path | None = None,
    frozen_path: Path = FROZEN_PATH,
    residue_path: Path = RESIDUE_PATH,
) -> list[str]:
    """Load everything `grade_chapter` needs from disk and grade
    `chapter_id` (e.g. `"CH05"`). Returns a single problem naming the
    missing module if `chapter_id` has no generated suite yet -- that is
    the ordinary state before C9 lands a chapter, not a crash."""
    chapter_id = chapter_id.upper()
    try:
        gen_chapter = load_chapter(chapter_id.lower(), suite="gen")
    except KeyError as exc:
        return [f"{chapter_id}: no generated chapter module ({exc})"]
    module = load_chapter_module(chapter_id, suite="gen")
    never_fires: Mapping[str, str] = getattr(module, "NEVER_FIRES", {})

    all_frozen = load_frozen_hand_beats(frozen_path)
    frozen_beats = [b for b in all_frozen if b.chapter == chapter_id]
    residue_entries = _load_residue_entries(residue_path)

    resolved_build_dir = build_dir if build_dir is not None else default_build_dir()
    return grade_chapter(
        chapter_id,
        frozen_beats=frozen_beats,
        residue_entries=residue_entries,
        gen_chapter=gen_chapter,
        never_fires=never_fires,
        build_dir=resolved_build_dir,
    )
