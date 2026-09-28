"""Playtest beat templates for the four recurring RPG Maker archetypes.

Each sibling module (`trainer.py`, `item_ball.py`, `warp.py`,
`arrival_nudge.py`) exports one function a chapter author calls once per
instance. The template's job is narrow and deliberate: the *set* of beats
an archetype instance needs is complete, and the *assertions* inside them
are uniform and strong -- it is emphatically NOT a beat generator. A
chapter file stays a linear, hand-controlled, approvable document; these
templates just save an author from re-deriving the same coordinate lookups
and the same assertion shape on every trainer/item ball/warp/nudge in the
corpus.

**Manifest-driven validation.** Every template looks up the
`ArchetypeMatch` `chapter_manifest.archetypes.classify_manifest` derives
for the instance's `(map_id, event_id)`, and checks that whatever the
author stated about the instance (trigger, phone, double, ...) actually
agrees with what the manifest independently derives. Disagreement is a
loud `ValueError` at beat-registration time (import time, for a chapter
module) -- never a silently-accepted author claim. This is the whole
point: the data drives the test, not the other way around.

This module holds what all four templates share:

- `load_chapter_rows` / manifest loading with a module-level cache, the
  same discipline `playtest.cells` uses for its per-map graph cache
  (CLAUDE.md sec 4.2 idempotence -- repeated calls for the same chapter id
  are pure cache hits, never a second disk read that could disagree with
  the first).
- `find_match`, the one place that calls `classify_manifest` and picks out
  the single `ArchetypeMatch` a template asked for, failing loud on zero or
  ambiguous matches.
- `ChapterArchetypeModel`, the concrete adapter satisfying
  `chapter_manifest.checker.ArchetypeModel` -- the checker deliberately
  never imports `playtest` (same discipline as `CapabilityModel`/
  `ApproachModel`/`RouteModel`), so this lives on the `playtest` side of
  that seam.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from ...beat_floor.assertion import FloorAssertion, RowFloor
from ...chapter_manifest.archetypes import ArchetypeMatch, classify_manifest
from ...chapter_manifest.schema import ManifestRow, row_from_dict
from .. import chapter as _chapter

logger = logging.getLogger(__name__)

__all__ = [
    "ChapterArchetypeModel",
    "declare_assertions",
    "default_manifest_dir",
    "facing_toward",
    "find_match",
    "load_chapter_rows",
    "map_uranium_id",
    "walked_arms",
]


# -- facing, shared by every template that talks to something ---------------
#
# Consolidated here 2026-09-15 when `flavour_npc` would have become the
# FOURTH byte-identical copy (trainer.py, item_ball.py, chapters/ch01.py were
# the first three, differing only in their error prefix). CLAUDE.md §4.3 --
# one source of truth per concept; the repo had just made the same move on
# five hand-copied `*_constant` helpers, two of which had drifted.
#
# Values are the emulator's key names (`emulator.KEYS`), uppercase. The
# 2026-09-15 consolidation lowercased them, which no unit test could see and
# which made every template's `emu.face(...)` raise `KeyError: 'up'` on the
# first ROM run (2026-09-27). `trainer.py`'s live-press table keys on the
# uppercase names too.
_DIR_TOWARD: dict[tuple[int, int], str] = {
    (0, -1): "UP",
    (0, 1): "DOWN",
    (-1, 0): "LEFT",
    (1, 0): "RIGHT",
}


def facing_toward(
    approach: tuple[int, int], target: tuple[int, int], *, caller: str,
) -> str:
    """Which way to face, standing on `approach`, to look at `target`.

    `caller` names the template in the error, because "approach is not
    adjacent to target" is otherwise indistinguishable between four call
    sites. Fails loud rather than picking a diagonal: `cells.approach_to`
    is supposed to return an orthogonally adjacent cell, so a delta this
    table does not hold means the cell derivation is wrong upstream and
    guessing a direction here would bury it.
    """
    delta = (target[0] - approach[0], target[1] - approach[1])
    if delta[0] == 0 and abs(delta[1]) == 2 or delta[1] == 0 and abs(delta[0]) == 2:
        # Across a counter (`MapGraph.interaction_cells`): straight, two out.
        delta = (delta[0] // 2, delta[1] // 2)
    facing = _DIR_TOWARD.get(delta)
    if facing is None:
        raise ValueError(
            f"{caller}: approach {approach} is not orthogonally adjacent "
            f"to target {target} (delta {delta}) -- cells.approach_to "
            "should never produce this"
        )
    return facing

# -- declared assertions (REDERIVATION_PLAN.md §16.3 C5) ---------------------

FloorLookup = Callable[[str], RowFloor]


def walked_arms(
    row_id: str, kind: str, *, floor_lookup: FloorLookup,
) -> tuple[str, ...]:
    """Branch children (`row_id/b0`, `/b1`, ...) whose floor carries a `kind`
    assertion -- the arm a fresh walk actually traverses, per an archetype's
    own fingerprint. Walks `bN` until `floor_lookup` reports there is no such
    row; `()` for a page with no branches at all. Never a hardcoded index.

    Shared by `warp.py` and `arrival_nudge.py` (hoisted 2026-09-17, C5
    audit -- the two were byte-identical apart from which kind each filtered
    on, so that became the one parameter that varies).
    """
    walked: list[str] = []
    index = 0
    while True:
        candidate = f"{row_id}/b{index}"
        try:
            floor = floor_lookup(candidate)
        except KeyError:
            break
        if any(a.kind == kind for a in floor.assertions):
            walked.append(candidate)
        index += 1
    return tuple(walked)


def declare_assertions(
    rows: Sequence[str],
    *,
    executed_kinds: frozenset[str],
    template: str,
    extras: Sequence[FloorAssertion] = (),
    floor_lookup: FloorLookup | None = None,
) -> frozenset[FloorAssertion]:
    """What a template's beat declares for `rows`: each row's floor filtered
    to the kinds the template's body actually checks, with `extras` layered
    on top (an extra sharing a floor key replaces that floor assertion and
    must `covers` it -- a stronger oracle, never a different one).

    Honest by construction: a floor kind the template does not execute is
    left out rather than declared, so the checker's ⊇ rule reports it as
    uncovered instead of the template claiming a check it never makes. A
    refused floor contributes nothing (its refusal is the row's blocker).
    An extra that contradicts the source, or names a row outside `rows`,
    fails loud at registration.
    """
    from ...beat_floor.coverage import assertion_key, contradicts, covers
    from ...beat_floor.lookup import floor_for_row

    lookup = floor_lookup if floor_lookup is not None else floor_for_row
    row_set = set(rows)
    stray = sorted({a.row_id for a in extras} - row_set)
    if stray:
        raise ValueError(f"{template}: extras name row(s) {stray} outside rows={sorted(row_set)}")

    declared: dict[tuple, list[FloorAssertion]] = {}
    for row_id in rows:
        floor = lookup(row_id)
        if floor.refused:
            continue
        for a in floor.assertions:
            if a.kind in executed_kinds:
                declared.setdefault(assertion_key(a), []).append(a)
        for extra in extras:
            if extra.row_id != row_id:
                continue
            for f in floor.assertions:
                if contradicts(extra, f):
                    raise ValueError(
                        f"{template}: declared {extra} contradicts the source "
                        f"floor assertion {f}")
    for extra in extras:
        key = assertion_key(extra)
        matched = [f for f in declared.get(key, []) if covers(extra, f)]
        if key in declared:
            declared[key] = [f for f in declared[key] if f not in matched]
        declared.setdefault(key, []).append(extra)
    return frozenset(a for group in declared.values() for a in group)


# -- manifest loading, cached (mirrors playtest.cells' graph cache) ----------

_MANIFEST_CACHE: dict[str, tuple[ManifestRow, ...]] = {}


def default_manifest_dir() -> Path:
    return Path("reference/manifests")


def load_chapter_rows(
    chapter_id: str, *, manifest_dir: Path | None = None,
) -> tuple[ManifestRow, ...]:
    """`row_id -> ManifestRow` isn't the shape -- the classifier wants the
    whole row sequence -- so this returns every row for `chapter_id`,
    loaded once and cached by `(manifest_dir, chapter_id)`.

    Fails loud with an actionable message if
    `reference/manifests/<CHAPTER>.manifest.json` is missing: a template
    cannot derive anything without it, and guessing is exactly what this
    whole package exists to refuse to do.
    """
    resolved_dir = manifest_dir if manifest_dir is not None else default_manifest_dir()
    cache_key = f"{resolved_dir}/{chapter_id}"
    cached = _MANIFEST_CACHE.get(cache_key)
    if cached is not None:
        return cached

    path = resolved_dir / f"{chapter_id}.manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"archetype templates: no chapter manifest at {path} -- run "
            "chapter_manifest.generator.generate_chapter_manifest for "
            f"{chapter_id!r} and commit its output to "
            f"reference/manifests/{chapter_id}.manifest.json before "
            "authoring archetype beats for this chapter"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = tuple(row_from_dict(entry) for entry in raw)
    _MANIFEST_CACHE[cache_key] = rows
    return rows


def find_match(
    chapter_id: str,
    map_id: int,
    event_id: int,
    archetype: str,
    *,
    row_id: str | None = None,
    rows: Sequence[ManifestRow] | None = None,
    manifest_dir: Path | None = None,
    manifest_chapter_id: str | None = None,
) -> ArchetypeMatch:
    """The one `ArchetypeMatch` a template call is asking about.

    `rows=` lets a caller (chiefly tests) supply an in-memory manifest
    (e.g. `generate_chapter_manifest` run against a build dir) instead of
    reading `reference/manifests/`; real chapter modules never pass it, and
    get the cached on-disk load via `load_chapter_rows`.

    `row_id=` disambiguates the page-level archetypes (`warp`,
    `arrival_nudge`), where more than one page on the same event can
    independently match the same archetype (rare, but the classifier's
    shape allows it -- see `chapter_manifest.archetypes`' module
    docstring). `trainer`/`item_ball` are event-level and never need it.

    `manifest_chapter_id=` lets a chapter claim an archetype instance that
    physically sits on a PREDECESSOR chapter's map (operator ruling,
    `REDERIVATION_PLAN.md` §10 R3: `map035/ev001/p1`, an arrival-nudge
    autorun on CH04's map 35 that only CH05's walk can ever trigger --
    emerging from a cave CH04 never opens). `chapter_id` still identifies
    the chapter doing the registering (it appears in beat names, error
    messages, etc.); `manifest_chapter_id`, when given, is the chapter
    whose *manifest* is actually loaded and searched, overriding the
    default of reading `chapter_id`'s own manifest. Left `None` (the
    default) this parameter is a complete no-op and `find_match` behaves
    exactly as before -- only the caller that needs the split passes it.
    Ignored when `rows=` is supplied directly, same as `manifest_dir=`.

    Fails loud on zero or more-than-one candidate, naming what WAS found --
    and, once `chapter_id` and the manifest actually searched can differ,
    naming the searched manifest's own chapter id too, so a cross-chapter
    call's failure doesn't misleadingly read as "CH05 has no rows on map
    35" when the real search happened against CH04's manifest.
    """
    manifest_id = manifest_chapter_id if manifest_chapter_id is not None else chapter_id
    resolved_rows = rows if rows is not None else load_chapter_rows(
        manifest_id, manifest_dir=manifest_dir)
    matches = classify_manifest(resolved_rows)
    candidates = [
        m for m in matches
        if m.map_id == map_id and m.event_id == event_id and m.archetype == archetype
    ]
    if row_id is not None:
        candidates = [m for m in candidates if row_id in m.roles]

    if not candidates:
        same_event = [
            (m.archetype, sorted(m.roles)) for m in matches
            if m.map_id == map_id and m.event_id == event_id
        ]
        searched = (
            f" (searched {manifest_id}'s manifest)"
            if manifest_id != chapter_id else ""
        )
        raise ValueError(
            f"find_match: {chapter_id} map {map_id} event {event_id} has no "
            f"{archetype!r} archetype match{searched}"
            + (f" with row_id={row_id!r}" if row_id is not None else "")
            + (f" -- this event DOES classify as: {same_event}" if same_event
               else " -- classify_manifest finds no archetype at all on this event")
        )
    if len(candidates) > 1:
        listing = [sorted(m.roles) for m in candidates]
        raise ValueError(
            f"find_match: {chapter_id} map {map_id} event {event_id} has "
            f"{len(candidates)} distinct {archetype!r} matches: {listing} "
            "-- disambiguate with row_id="
        )
    return candidates[0]


# -- map constant -> Uranium id, reused for the same reason cells.py reuses
# chapter.py's loader rather than re-parsing the persisted state a second
# time (CLAUDE.md sec 4.3, one source of truth). --------------------------

_URANIUM_ID_CACHE: dict[str, int] | None = None


def map_uranium_id(map_constant: str) -> int:
    global _URANIUM_ID_CACHE
    if _URANIUM_ID_CACHE is None:
        _URANIUM_ID_CACHE = _chapter._load_map_const_to_uranium_id(
            _chapter.default_map_constants_state_path())
    uid = _URANIUM_ID_CACHE.get(map_constant)
    if uid is None:
        raise ValueError(
            f"map_uranium_id: {map_constant!r} does not resolve to any "
            "minted Uranium map id -- check "
            "output/uranium-build/porymap/map_constants.json"
        )
    return uid


# -- ChapterArchetypeModel: playtest.chapter.Chapter -> checker.ArchetypeModel

class ChapterArchetypeModel:
    """Satisfies `chapter_manifest.checker.ArchetypeModel`.

    Built from a fully-composed `Chapter` (predecessor beats included --
    `chapter.beats` already carries them, per `Chapter`'s own docstring).
    Indexes every registered beat's `rows` to its `archetype`; a row two
    beats claim under *different* archetypes fails loud at construction
    time, because that is a real authoring contradiction (two beats
    disagreeing about what one page of RGSS content even is), not something
    resolvable by silently picking one and moving on.
    """

    def __init__(self, chapter: _chapter.Chapter) -> None:
        index: dict[str, str] = {}
        for beat in chapter.beats:
            for row in beat.rows:
                archetype = beat.archetype_of(row)
                if archetype is None:
                    continue
                existing = index.get(row)
                if existing is not None and existing != archetype:
                    raise ValueError(
                        f"ChapterArchetypeModel: row {row!r} in chapter "
                        f"{chapter.name!r} is claimed as both {existing!r} "
                        f"(by an earlier beat) and {archetype!r} (by "
                        f"beat {beat.name!r}) -- two beats disagree about "
                        "what archetype this row is; that is an authoring "
                        "contradiction to resolve by hand, not something "
                        "this model may pick a winner for"
                    )
                index[row] = archetype
        self._index = index

    def claimed_archetype(self, row_id: str) -> str | None:
        return self._index.get(row_id)
