"""Recurring RPG Maker event archetypes, recognized from `ManifestRow` alone.

This is the single source of truth for archetype fingerprints. A checker rule
(`checker.py`) and a set of playtest beat templates both import
`ARCHETYPE_NAMES` / `classify_event` / `classify_manifest` from here rather
than re-deriving the shapes themselves, so the two halves of the pipeline
cannot quietly drift apart on what counts as "a trainer" or "an item ball".

**Hard constraint (task-given): classify using ONLY fields present on
`ManifestRow`.** Nothing here opens `output/uranium-build/maps/Map###.json`.
Where a fingerprint might have wanted the sprite graphic name or move-route
contents, `script_heads` is used instead -- more robust, and the only thing
actually on the row.

Classification is event-level for `trainer` and `item_ball` (a battle page and
its post-battle re-talk pages, or a grant page and its spent page, only mean
anything read together -- the `B14` bug was exactly a per-page question asked
about a page whose meaning only existed at the event level) but page-level for
`warp` and `arrival_nudge`. That split is deliberate, not an oversight: a warp
page and an arrival-nudge page routinely sit in the *same* event (the cave
entrance is p0's warp, the facing/BGM staging is p1's nudge -- see
`map035/ev001`), and the two pages don't need to agree with each other about
anything to each be independently correct. Grouping them into one
event-spanning match would invent a relationship the data doesn't assert.
Classifying them at page level instead means a single event can legitimately
produce two `ArchetypeMatch` objects (one `warp`, one `arrival_nudge`), each
owning exactly the one row it describes -- which is what `classify_event`
does below: run the two event-level checks first (they claim every row they
match), then run the two page-level checks over whatever rows are left
unclaimed.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .schema import COSMETIC_SAFE_TAGS, ManifestRow

ARCHETYPE_NAMES: frozenset[str] = frozenset({
    "trainer",
    "item_ball",
    "warp",
    "arrival_nudge",
})

_TRAINER_BATTLE_HEADS: frozenset[str] = frozenset({
    "pbTrainerBattle",
    "pbDoubleTrainerBattle",
})
_PHONE_HEADS: frozenset[str] = frozenset({
    "pbPhoneRegisterBattle",
    "createPhoneTrainer",
})
# `giveitem` only, deliberately. `self_switch_write` was in this set until
# 2026-09-01 and made the `rider` param constant-True: every `pbTrainerBattle`
# page 0 in CH04 and CH05 writes a self-switch, because that is how the
# post-battle re-talk page is gated. A parameter true of every instance
# discriminates nothing. The axis this is meant to capture is the V2 census's
# "item-grant rider folded into the battle page" (33 events corpus-wide).
_RIDER_TAGS: frozenset[str] = frozenset({"giveitem"})

_NUDGE_HEADS: frozenset[str] = frozenset({"get_character", "setTempSwitchOn"})
_NUDGE_EFFECTS_REQUIRED: frozenset[str] = frozenset({
    "graphic", "move_route", "temp_switch_write",
})


@dataclass(frozen=True)
class ArchetypeMatch:
    """One recognized archetype instance, scoped to the rows it explains.

    `roles` maps every row_id this match owns to a role name ("battle",
    "retalk", "grant", "spent", "warp", "nudge"). `prescribed` maps the same
    row_ids to the verdict HEAD the archetype prescribes ("beat" or
    "cosmetic") -- never the beat NAME, which is the beat author's call, not
    a classification.
    """

    archetype: str
    map_id: int
    event_id: int
    params: Mapping[str, object]
    roles: Mapping[str, str]
    prescribed: Mapping[str, str]


def _is_cosmetic_safe(row: ManifestRow) -> bool:
    return not row.effects or not (set(row.effects) - COSMETIC_SAFE_TAGS)


def _match_trainer(rows: Sequence[ManifestRow]) -> ArchetypeMatch | None:
    p0 = rows[0]
    if not (set(p0.script_heads) & _TRAINER_BATTLE_HEADS):
        return None

    all_heads: set[str] = set()
    for row in rows:
        all_heads.update(row.script_heads)

    retalk_pages = len(rows) - 1
    roles: dict[str, str] = {p0.row_id: "battle"}
    prescribed: dict[str, str] = {p0.row_id: "beat"}
    for row in rows[1:]:
        roles[row.row_id] = "retalk"
        prescribed[row.row_id] = "beat"

    params = {
        "trigger": p0.trigger,
        "phone": bool(all_heads & _PHONE_HEADS),
        "double": "pbDoubleTrainerBattle" in all_heads,
        "retalk_pages": retalk_pages,
        "rider": bool(set(p0.effects) & _RIDER_TAGS),
    }
    return ArchetypeMatch(
        archetype="trainer",
        map_id=p0.map_id,
        event_id=p0.event_id,  # type: ignore[arg-type]
        params=params,
        roles=roles,
        prescribed=prescribed,
    )


def _match_item_ball(rows: Sequence[ManifestRow]) -> ArchetypeMatch | None:
    p0 = rows[0]
    if "pbItemBall" not in p0.script_heads:
        return None
    p1 = next((row for row in rows if row.page_idx == 1), None)
    if p1 is None:
        return None
    if not _is_cosmetic_safe(p1):
        return None
    if p1.condition is None or p1.condition.self_switch_ch is None:
        return None

    return ArchetypeMatch(
        archetype="item_ball",
        map_id=p0.map_id,
        event_id=p0.event_id,  # type: ignore[arg-type]
        params={},
        roles={p0.row_id: "grant", p1.row_id: "spent"},
        prescribed={p0.row_id: "beat", p1.row_id: "cosmetic"},
    )


def _match_warp(row: ManifestRow) -> ArchetypeMatch | None:
    if "warp" not in row.effects:
        return None
    return ArchetypeMatch(
        archetype="warp",
        map_id=row.map_id,
        event_id=row.event_id,  # type: ignore[arg-type]
        params={"trigger": row.trigger},
        roles={row.row_id: "warp"},
        prescribed={row.row_id: "beat"},
    )


def _match_arrival_nudge(row: ManifestRow) -> ArchetypeMatch | None:
    if row.trigger != "autorun":
        return None
    if not _NUDGE_HEADS.issubset(row.script_heads):
        return None
    if not _NUDGE_EFFECTS_REQUIRED.issubset(row.effects):
        return None
    if row.script_typed_conditions < 1:
        return None
    if row.condition is None:
        return None
    if row.condition.switch1_id is None and row.condition.switch2_id is None:
        return None
    return ArchetypeMatch(
        archetype="arrival_nudge",
        map_id=row.map_id,
        event_id=row.event_id,  # type: ignore[arg-type]
        params={},
        roles={row.row_id: "nudge"},
        prescribed={row.row_id: "beat"},
    )


def classify_event(rows: Sequence[ManifestRow]) -> tuple[ArchetypeMatch, ...]:
    """All rows of a single (map_id, event_id), page-ordered.

    Empty tuple = no archetype. Only `kind == "page"` rows may match; callers
    are expected to have already filtered out `seam` and `terrain` rows (see
    `classify_manifest`), but this function defensively drops them too so it
    is safe to call directly with a mixed-kind slice.
    """
    page_rows = tuple(row for row in rows if row.kind == "page")
    if not page_rows:
        return ()
    page_rows = tuple(sorted(page_rows, key=lambda row: row.page_idx or 0))

    matches: list[ArchetypeMatch] = []
    claimed: set[str] = set()

    trainer_match = _match_trainer(page_rows)
    if trainer_match is not None:
        matches.append(trainer_match)
        claimed.update(trainer_match.roles)

    if not claimed:
        item_ball_match = _match_item_ball(page_rows)
        if item_ball_match is not None:
            matches.append(item_ball_match)
            claimed.update(item_ball_match.roles)

    # Page-level archetypes run over whatever rows the event-level checks
    # above did not already claim -- this is what lets one event (e.g. a
    # cave entrance) produce both a `warp` match on one page and an
    # `arrival_nudge` match on another. See module docstring.
    for row in page_rows:
        if row.row_id in claimed:
            continue
        warp_match = _match_warp(row)
        if warp_match is not None:
            matches.append(warp_match)
            claimed.add(row.row_id)
            continue
        nudge_match = _match_arrival_nudge(row)
        if nudge_match is not None:
            matches.append(nudge_match)
            claimed.add(row.row_id)

    return tuple(matches)


def classify_manifest(rows: Sequence[ManifestRow]) -> tuple[ArchetypeMatch, ...]:
    """Group `rows` by (map_id, event_id), classify each, return all matches.

    Sorted by the lowest row_id each match owns, so output order is stable
    and independent of input order. Only `kind == "page"` rows are ever
    considered; `seam` and `terrain` rows are skipped up front.
    """
    groups: dict[tuple[int, int], list[ManifestRow]] = {}
    for row in rows:
        if row.kind != "page":
            continue
        if row.event_id is None:
            continue
        groups.setdefault((row.map_id, row.event_id), []).append(row)

    matches: list[ArchetypeMatch] = []
    for key in sorted(groups):
        matches.extend(classify_event(groups[key]))

    matches.sort(key=lambda match: min(match.roles))
    return tuple(matches)
