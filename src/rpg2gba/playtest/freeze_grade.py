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
    module's `NEVER_FIRES` dict (C9 ruling 3 -- a proof, not an exception),
    or claimed by the own beats of the generated chapter whose manifest owns
    the row (C9 ruling 12: a hand beat that tested another chapter's row,
    e.g. CH02's white-out on CH01's house, doesn't move the row).

(b) **Floor ⊇, on the rows rule (a) requires.** For every required row the
    generated chapter's own beats claim, the union of those beats' declared
    assertions for that row must cover the row's generic floor
    (`beat_floor.lookup.floor_for_row`), using the same ⊇ comparison
    `chapter_manifest.checker._check_floor_coverage` uses --
    `beat_floor.coverage.uncovered`/`contradicts` -- not a second one. A row
    whose claiming beats all declare `None` (undeclared) is a problem for a
    generated module (unlike a hand module, which only warns). A row whose
    floor itself refuses is reported distinctly: it should not have been
    claimed at all.

    Scoped by the 2026-09-24 grading rulings (REDERIVATION_PLAN.md §16.3,
    C9 rulings 6-10):
    - Only required rows are graded (ruling 6). A generator-only row that
      fails the same check is counted in `ChapterGrade.generator_only_partial`
      -- reported, never a problem; the review doc lists it as debt.
    - `audio`/`visual`/`displacement` floor assertions are walk-checked, not
      graded (ruling 7). A *contradicting* declaration of one is still a
      problem: a wrong claim is worse than a missing one.
    - A required row claimed only by a boundary warp (a `warp` beat that
      declares nothing for it) is graded against the successor chapter's
      generated claim instead (ruling 9); with no generated successor yet it
      is `deferred`, not a problem.
    - A floor carrying `blocked_obstacle` owes only that (ruling 10).

This module is pure logic over injected data (`grade_chapter`); I/O lives
only in `grade_chapter_from_disk`, the thin loader the CLI and the real-
data test call.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor
from rpg2gba.beat_floor.coverage import contradicts, uncovered
from rpg2gba.beat_floor.lookup import default_build_dir, floor_for_row
from rpg2gba.playtest.chapter import (
    Beat,
    Chapter,
    gen_chapter_names,
    load_chapter,
    load_chapter_module,
)
from rpg2gba.playtest.hand_freeze import (
    FROZEN_PATH,
    RESIDUE_PATH,
    FrozenBeat,
    load_frozen_hand_beats,
    manifest_row_ids,
)

logger = logging.getLogger(__name__)

#: Residue rulings that cite manifest rows (RESIDUE_RULINGS in hand_freeze.py
#: -- the ones whose extra-fields tuple is `("rows",)`). A row cited by one
#: of these entries is still owed coverage in the generated suite; the other
#: rulings (`retired`, `bgm_debt`, `build_check`, `not_residue`) name no rows
#: and need nothing graded.
_ROWED_RESIDUE_RULINGS = frozenset(
    {"arrival_floor", "blocked_obstacle", "state_model", "covered_elsewhere"})

#: Floor kinds the §9 boot walk checks by eye instead of rule (b) (C9 ruling
#: 7): the hand suite never asserted them either.
WALK_CHECKED_KINDS = frozenset({"audio", "visual", "displacement"})


@dataclass(frozen=True)
class ChapterGrade:
    """One chapter's grade. `problems == []` is a pass; the other two lists
    are reported, never failed."""

    problems: list[str] = field(default_factory=list)
    #: Required boundary rows whose crossing belongs to a successor chapter
    #: that has no generated module yet (C9 ruling 9).
    deferred: list[str] = field(default_factory=list)
    #: Generator-only rows (not required) that would fail rule (b) -- the
    #: tracked debt C9 ruling 6 keeps visible without grading.
    generator_only_partial: list[str] = field(default_factory=list)


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


@dataclass(frozen=True)
class OwnerSuite:
    """Another chapter's generated suite, as the grader needs it: its own
    beats' claims and the rows its manifest owns (C9 ruling 12)."""

    name: str
    claims: Mapping[str, list[Beat]]
    manifest_rows: frozenset[str]


def _owner_claims(
    chapter_id: str, owners: Sequence[OwnerSuite],
) -> dict[str, tuple[str, list[Beat]]]:
    """Rows another chapter both owns (in its manifest) and claims with its
    own generated beats -> (that chapter, those beats). First in the order
    given wins; the caller passes chain order."""
    found: dict[str, tuple[str, list[Beat]]] = {}
    for owner in owners:
        if owner.name.upper() == chapter_id:
            continue
        for row_id, beats in owner.claims.items():
            if row_id in owner.manifest_rows and row_id not in found:
                found[row_id] = (owner.name, beats)
    return found


def _check_row_coverage(
    chapter_id: str,
    required_rows: Mapping[str, list[str]],
    claimed_by_own: Mapping[str, list[Beat]],
    never_fires: Mapping[str, str],
    claimed_by_owner: Mapping[str, tuple[str, list[Beat]]],
) -> list[str]:
    # A beat asserting a row and a proof that the row never runs cannot both
    # be right; whichever is wrong, the generator emitted a contradiction.
    problems: list[str] = [
        f"{chapter_id}: row {row_id!r} is claimed by "
        f"{[b.name for b in claimed_by_own[row_id]]} AND listed in NEVER_FIRES"
        for row_id in sorted(set(claimed_by_own) & set(never_fires))
    ]
    for row_id, sources in sorted(required_rows.items()):
        if row_id in claimed_by_own or row_id in never_fires or row_id in claimed_by_owner:
            continue
        problems.append(
            f"{chapter_id}: row {row_id!r}, claimed by {sources}, is not "
            f"claimed by any own beat of the generated {chapter_id}, nor by "
            "the generated chapter whose manifest owns it, and is not in "
            "NEVER_FIRES")
    return problems


def _graded_gaps(
    floor: RowFloor, declared: frozenset[FloorAssertion],
) -> tuple[list[FloorAssertion], list[FloorAssertion]]:
    """(contradicted, missing) floor assertions rule (b) grades. Every
    contradiction counts; a merely-missing assertion counts unless it is
    walk-checked (C9 ruling 7) or the floor is a capability block, which
    owes only its `blocked_obstacle` (C9 ruling 10)."""
    missing = uncovered(floor, declared)
    contradicted = [f for f in missing if any(contradicts(d, f) for d in declared)]
    if any(a.kind == "blocked_obstacle" for a in floor.assertions):
        owed = [f for f in missing if f.kind == "blocked_obstacle"]
    else:
        owed = [f for f in missing if f.kind not in WALK_CHECKED_KINDS]
    return contradicted, [f for f in owed if f not in contradicted]


def _row_floor_problem(
    chapter_id: str, row_id: str, beats: Sequence[Beat], *, build_dir: Path,
) -> str | None:
    """Rule (b) for one row claimed by `beats`, or None if it passes."""
    beat_names = [b.name for b in beats]
    try:
        floor = floor_for_row(row_id, build_dir=build_dir)
    except KeyError as exc:
        return (f"{chapter_id}: row {row_id!r}, claimed by {beat_names}, has "
                f"no generic floor at all ({exc})")

    if floor.refused:
        return (f"{chapter_id}: row {row_id!r} is claimed by {beat_names}, "
                f"but its floor refuses ({[r.reason for r in floor.refusals]}) "
                "-- a refused row is the generator's own blocker and should "
                "not have been claimed")

    declaring = [b for b in beats if b.assertions is not None]
    if not declaring:
        return (f"{chapter_id}: row {row_id!r} is claimed by {beat_names}, "
                "but none of them declares assertions (undeclared claim in a "
                "generated module)")

    declared = frozenset(
        a for b in declaring for a in b.assertions if a.row_id == row_id)
    contradicted, missing = _graded_gaps(floor, declared)
    if not contradicted and not missing:
        return None
    parts = []
    if contradicted:
        parts.append(f"declared assertion(s) contradict the floor: {contradicted}")
    if missing:
        parts.append(f"floor assertion(s) not declared at all: {missing}")
    return (f"{row_id}: claimed by {beat_names} but does not cover its floor -- "
            + "; ".join(parts))


def _is_boundary_claim(row_id: str, beats: Sequence[Beat]) -> bool:
    """True iff every claiming beat is a warp declaring nothing for `row_id`
    -- the shape of `warp_beat(boundary=True)`, which stops on the approach
    cell and leaves the crossing to the successor chapter."""
    return all(b.archetype == "warp" for b in beats) and not any(
        a.row_id == row_id for b in beats for a in (b.assertions or ()))


def _check_floor_ge(
    chapter_id: str,
    claimed_by_own: Mapping[str, list[Beat]],
    required_rows: Mapping[str, list[str]],
    *,
    successor: Chapter | None,
    claimed_by_owner: Mapping[str, tuple[str, list[Beat]]],
    build_dir: Path,
) -> ChapterGrade:
    problems: list[str] = []
    deferred: list[str] = []
    generator_only: list[str] = []
    successor_claims = (
        _claimed_by_own(_own_beats(successor)) if successor is not None else {})

    for row_id, beats in sorted(claimed_by_own.items()):
        if row_id not in required_rows:
            message = _row_floor_problem(chapter_id, row_id, beats, build_dir=build_dir)
            if message is not None:
                generator_only.append(message)
            continue

        if _is_boundary_claim(row_id, beats):
            beat_names = [b.name for b in beats]
            if successor is None:
                deferred.append(
                    f"{chapter_id}: row {row_id!r} is claimed only by boundary "
                    f"warp {beat_names}; its crossing belongs to the successor "
                    "chapter, which has no generated module yet")
                continue
            crossing = successor_claims.get(row_id)
            if not crossing:
                problems.append(
                    f"{chapter_id}: row {row_id!r} is claimed only by boundary "
                    f"warp {beat_names}, and the successor {successor.name} "
                    "does not claim its crossing")
                continue
            message = _row_floor_problem(
                successor.name, row_id, crossing, build_dir=build_dir)
        else:
            message = _row_floor_problem(chapter_id, row_id, beats, build_dir=build_dir)
        if message is not None:
            problems.append(message)

    # Required rows only the owning chapter claims (C9 ruling 12) are graded
    # against that chapter's beats.
    for row_id, (owner, beats) in sorted(claimed_by_owner.items()):
        if row_id in required_rows and row_id not in claimed_by_own:
            message = _row_floor_problem(owner, row_id, beats, build_dir=build_dir)
            if message is not None:
                problems.append(message)
    return ChapterGrade(problems=problems, deferred=deferred,
                        generator_only_partial=generator_only)


def grade_chapter(
    chapter_id: str,
    *,
    frozen_beats: Sequence[FrozenBeat],
    residue_entries: Mapping[str, Mapping[str, Any]],
    gen_chapter: Chapter,
    never_fires: Mapping[str, str],
    build_dir: Path,
    successor: Chapter | None = None,
    owners: Sequence[OwnerSuite] = (),
) -> ChapterGrade:
    """Pure grade of one chapter. `.problems == []` means the generated suite
    covers the frozen hand suite for `chapter_id`. `successor` is the next
    chapter's generated suite, if one exists (boundary rows, C9 ruling 9);
    `owners` are the other chapters' generated suites in chain order (a
    frozen row another chapter owns and claims, C9 ruling 12).
    All inputs are already loaded; `grade_chapter_from_disk` is the I/O
    wrapper real callers use."""
    own_beats = _own_beats(gen_chapter)
    claimed_by_own = _claimed_by_own(own_beats)
    claimed_by_owner = _owner_claims(chapter_id, owners)

    required_rows = _required_rows(chapter_id, frozen_beats, residue_entries)
    row_problems = _check_row_coverage(
        chapter_id, required_rows, claimed_by_own, never_fires, claimed_by_owner)
    floor = _check_floor_ge(chapter_id, claimed_by_own, required_rows,
                            successor=successor, claimed_by_owner=claimed_by_owner,
                            build_dir=build_dir)
    return ChapterGrade(problems=row_problems + floor.problems,
                        deferred=floor.deferred,
                        generator_only_partial=floor.generator_only_partial)


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
) -> ChapterGrade:
    """Load everything `grade_chapter` needs from disk and grade
    `chapter_id` (e.g. `"CH05"`). Returns a single problem naming the
    missing module if `chapter_id` has no generated suite yet -- that is
    the ordinary state before C9 lands a chapter, not a crash."""
    chapter_id = chapter_id.upper()
    try:
        gen_chapter = load_chapter(chapter_id.lower(), suite="gen")
    except KeyError as exc:
        return ChapterGrade(problems=[f"{chapter_id}: no generated chapter module ({exc})"])
    module = load_chapter_module(chapter_id, suite="gen")
    never_fires: Mapping[str, str] = getattr(module, "NEVER_FIRES", {})

    all_frozen = load_frozen_hand_beats(frozen_path)
    frozen_beats = [b for b in all_frozen if b.chapter == chapter_id]
    residue_entries = _load_residue_entries(residue_path)

    others = [load_chapter(name, suite="gen") for name in sorted(gen_chapter_names())
              if name.upper() != chapter_id]
    owners = [
        OwnerSuite(name=other.name, claims=_claimed_by_own(_own_beats(other)),
                   manifest_rows=frozenset(manifest_row_ids(other.name)))
        for other in others
    ]

    resolved_build_dir = build_dir if build_dir is not None else default_build_dir()
    return grade_chapter(
        chapter_id,
        frozen_beats=frozen_beats,
        residue_entries=residue_entries,
        gen_chapter=gen_chapter,
        never_fires=never_fires,
        build_dir=resolved_build_dir,
        successor=_generated_successor(chapter_id, others),
        owners=owners,
    )


def _generated_successor(chapter_id: str, others: Sequence[Chapter]) -> Chapter | None:
    """The generated suite whose `predecessor` is `chapter_id`, or None if
    that chapter has no generated module yet. Fails loud if more than one
    generated suite names the same predecessor -- the chain is linear."""
    successors = [
        c for c in others
        if c.predecessor is not None and c.predecessor.upper() == chapter_id
    ]
    if len(successors) > 1:
        raise ValueError(
            f"{chapter_id}: several generated suites name it as predecessor: "
            f"{[c.name for c in successors]}")
    return successors[0] if successors else None
