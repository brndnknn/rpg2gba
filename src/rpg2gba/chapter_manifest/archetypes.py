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

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from .schema import COSMETIC_SAFE_TAGS, ManifestRow, whole_page_views

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
# `graphic` was required until 2026-09-10 (REDERIVATION_PLAN.md sec 13.3 T1):
# real arrival-nudge pages exist that stage facing/BGM without ever touching
# the sprite graphic (no `Set Graphic` command on the page) -- `map068/ev012/p1`
# (CH03) is the instance that motivated dropping it: effects are exactly
# `{move_route, temp_switch_write}`, trigger is autorun, script_heads match
# `_NUDGE_HEADS` exactly, and the switch-condition fingerprint below is intact.
# `move_route` and `temp_switch_write` stay mandatory -- they are the two
# effects that are actually load-bearing for "this page moves/faces the
# player and won't re-fire" (module docstring); `graphic` was only ever a
# coincidental third tag on the instances the fingerprint was first written
# against, not a defining feature of the archetype.
_NUDGE_EFFECTS_REQUIRED: frozenset[str] = frozenset({
    "move_route", "temp_switch_write",
})


# --- flavour_npc (REDERIVATION_PLAN.md sec 13.3 T2) ------------------------
#
# The corpus's largest *talk* population: an NPC you press A on, who says
# something and changes nothing you could observe later. Three variants only
# -- plain, toggling (a self-switch flips to a second thing-to-say), and
# randomized (`random()` picks a line) -- which is why this is one archetype
# with a `variant` param rather than three registry entries. The V2 census's
# eight fingerprint clusters fragment only on cosmetic tags (`pbCallBub`,
# `se`, `var_write`), not on behaviour.
#
# These predicates were measured against the CH01-CH03 residue on 2026-09-15,
# not estimated: of 111 action-triggered text rows, 97 qualify (83 plain, 11
# toggling, 3 randomized) and the 14 rejects are all correctly rejected.
# Keep them tight -- every loosening below was considered and refused:
#
#   `switch_write` is NOT allowed (5 rows). A global switch is story state:
#     §15.8's whole point is that an observable write is not flavour. A
#     self-switch is different -- it is page-local by construction, and is
#     exactly how the toggling variant stores "I already said the first line".
#   `script_heads` must be a subset of `pbCallBub` alone (9 rows rejected).
#     `pbShowMap` is T8's region-map NPC, `displayNinjaLetter` is #9's card
#     UI, `jvGiveReward` grants something. Each is its own archetype or its
#     own backlog item; none is flavour, and all three read as "just talking"
#     if you look only at effects.
#   `unhandled` must be 0 and `script_typed_conditions` must be 0. A page
#     with a queued command or an unparsed condition is a page whose
#     behaviour we do not know -- claiming it as flavour would be the silent
#     default CLAUDE.md §4.5 exists to forbid.
_FLAVOUR_ALLOWED_EFFECTS: frozenset[str] = frozenset({
    "text", "bubble_ui", "se", "self_switch_write", "var_write",
})
# `pbCallBub` is Uranium's speech-bubble helper -- it draws an emote over the
# speaker's head and returns. Purely presentational, and by far the most
# common head in this population (68 of 111 candidate rows).
_FLAVOUR_COSMETIC_HEADS: frozenset[str] = frozenset({"pbCallBub"})


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
    # A page-1 "spent" remainder page was required until 2026-09-10
    # (REDERIVATION_PLAN.md sec 13.3 T1): single-page item balls exist that
    # never leave a remainder page behind at all -- `map068/ev018/p0` (CH03)
    # is the instance that motivated dropping the requirement: page 0 alone
    # has `script_heads = (pbItemBall,)` and `effects = (giveitem,
    # self_switch_write)`, everything page 0 ever needed, and there is no
    # page 1 in the event to demand anything of. When a page-1 row IS
    # present, every prior requirement on it (cosmetic-safe, self-switch
    # gated) still applies unchanged -- this only widens the "no p1 at all"
    # case from a non-match to a match with no "spent" role.
    if p1 is not None:
        if not _is_cosmetic_safe(p1):
            return None
        if p1.condition is None or p1.condition.self_switch_ch is None:
            return None

    roles: dict[str, str] = {p0.row_id: "grant"}
    prescribed: dict[str, str] = {p0.row_id: "beat"}
    if p1 is not None:
        roles[p1.row_id] = "spent"
        prescribed[p1.row_id] = "cosmetic"

    return ArchetypeMatch(
        archetype="item_ball",
        map_id=p0.map_id,
        event_id=p0.event_id,  # type: ignore[arg-type]
        params={},
        roles=roles,
        prescribed=prescribed,
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


def _flavour_variant(effects: frozenset[str]) -> str:
    """Which of T2's three variants this page is.

    Order matters: a toggling page may also carry `var_write`, and the
    self-switch is the more specific signal (it is what makes the page
    two-state at all), so it wins.
    """
    if "self_switch_write" in effects:
        return "toggling"
    if "var_write" in effects:
        return "randomized"
    return "plain"


def _match_flavour_npc(row: ManifestRow) -> ArchetypeMatch | None:
    if row.trigger != "action":
        return None
    effects = frozenset(row.effects)
    if "text" not in effects:
        return None
    if effects - _FLAVOUR_ALLOWED_EFFECTS:
        return None
    if set(row.script_heads) - _FLAVOUR_COSMETIC_HEADS:
        return None
    # A queued command or an unclassified condition means we do not know what
    # this page does; see the constants block above.
    if row.unhandled:
        return None
    if row.script_typed_conditions:
        return None
    if row.condition_unclassified:
        return None
    return ArchetypeMatch(
        archetype="flavour_npc",
        map_id=row.map_id,
        event_id=row.event_id,  # type: ignore[arg-type]
        params={"variant": _flavour_variant(effects)},
        roles={row.row_id: "talk"},
        prescribed={row.row_id: "beat"},
    )


# --- the archetype registry ---------------------------------------------
#
# Adding a fifth archetype means writing its `_match_*` matcher and adding
# one `_ArchetypeEntry` below -- nothing else in this module changes.
# `ARCHETYPE_NAMES` and `classify_event`'s dispatch both derive from this
# sequence, so they cannot drift apart the way a hand-written set and a
# hand-written if/elif chain eventually would.
#
# ORDER IS LOAD-BEARING. Event-level entries run in the order listed here,
# each claiming every row it matches before the next event-level entry
# gets a turn (`if not claimed` today, `if row_id not in claimed` in
# spirit). Page-level entries then run in the order listed here, once per
# still-unclaimed row, first match wins for that row. The sequence below --
# trainer, item_ball, warp, arrival_nudge -- reproduces today's precedence
# exactly; do not reorder it as part of this refactor.

EventMatcher = Callable[[Sequence[ManifestRow]], ArchetypeMatch | None]
PageMatcher = Callable[[ManifestRow], ArchetypeMatch | None]


@dataclass(frozen=True)
class _ArchetypeEntry:
    """One registered archetype: its name, its level, and its matcher.

    `level="event"` matchers receive the whole page-ordered row sequence
    for the event and may claim more than one row at once (trainer's
    retalk pages, item_ball's grant+spent pair). `level="page"` matchers
    receive a single still-unclaimed row and claim at most that one row.
    The two calling conventions are why the field is typed loosely
    (`Callable[..., ArchetypeMatch | None]`) rather than as a precise
    union -- `classify_event` below is the one place that knows, per
    entry, which shape to call it with.
    """

    name: str
    level: Literal["event", "page"]
    matcher: Callable[..., ArchetypeMatch | None]


def _build_registry(entries: Sequence[_ArchetypeEntry]) -> tuple[_ArchetypeEntry, ...]:
    seen: set[str] = set()
    for entry in entries:
        if entry.name in seen:
            raise ValueError(f"archetype {entry.name!r} registered more than once")
        if entry.level not in ("event", "page"):
            raise ValueError(f"archetype {entry.name!r} has unknown level {entry.level!r}")
        seen.add(entry.name)
    return tuple(entries)


_ARCHETYPE_REGISTRY: tuple[_ArchetypeEntry, ...] = _build_registry([
    _ArchetypeEntry("trainer", "event", _match_trainer),
    _ArchetypeEntry("item_ball", "event", _match_item_ball),
    _ArchetypeEntry("warp", "page", _match_warp),
    _ArchetypeEntry("arrival_nudge", "page", _match_arrival_nudge),
    # flavour_npc is deliberately LAST. Its fingerprint is the loosest here
    # ("an action page that only talks"), so any row a more specific
    # page-level archetype can explain must be claimed by that one first.
    _ArchetypeEntry("flavour_npc", "page", _match_flavour_npc),
])

ARCHETYPE_NAMES: frozenset[str] = frozenset(
    entry.name for entry in _ARCHETYPE_REGISTRY
)

_EVENT_LEVEL_ENTRIES: tuple[_ArchetypeEntry, ...] = tuple(
    entry for entry in _ARCHETYPE_REGISTRY if entry.level == "event"
)
_PAGE_LEVEL_ENTRIES: tuple[_ArchetypeEntry, ...] = tuple(
    entry for entry in _ARCHETYPE_REGISTRY if entry.level == "page"
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

    # Event-level archetypes run first, in registry order. Each claims
    # every row it matches; once any event-level archetype has claimed
    # rows, later event-level entries do not get a turn -- this preserves
    # the original "if not claimed" gate between trainer and item_ball.
    for entry in _EVENT_LEVEL_ENTRIES:
        if claimed:
            break
        event_match = entry.matcher(page_rows)
        if event_match is not None:
            matches.append(event_match)
            claimed.update(event_match.roles)

    # Page-level archetypes run over whatever rows the event-level checks
    # above did not already claim -- this is what lets one event (e.g. a
    # cave entrance) produce both a `warp` match on one page and an
    # `arrival_nudge` match on another. See module docstring.
    for row in page_rows:
        if row.row_id in claimed:
            continue
        for entry in _PAGE_LEVEL_ENTRIES:
            page_match = entry.matcher(row)
            if page_match is not None:
                matches.append(page_match)
                claimed.add(row.row_id)
                break

    return tuple(matches)


def classify_manifest(rows: Sequence[ManifestRow]) -> tuple[ArchetypeMatch, ...]:
    """Group `rows` by (map_id, event_id), classify each, return all matches.

    Sorted by the lowest row_id each match owns, so output order is stable
    and independent of input order. Only `kind == "page"` rows are ever
    considered; `seam` and `terrain` rows are skipped up front.
    """
    # Fingerprints are whole-page facts; C1's trunk-only page rows would hide
    # every command inside a conditional (see `whole_page_views`).
    views = whole_page_views(rows)
    groups: dict[tuple[int, int], list[ManifestRow]] = {}
    for row in rows:
        if row.kind != "page":
            continue
        if row.event_id is None:
            continue
        groups.setdefault((row.map_id, row.event_id), []).append(views[row.row_id])

    matches: list[ArchetypeMatch] = []
    for key in sorted(groups):
        matches.extend(classify_event(groups[key]))

    matches.sort(key=lambda match: min(match.roles))
    return tuple(matches)
