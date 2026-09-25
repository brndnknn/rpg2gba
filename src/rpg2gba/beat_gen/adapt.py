"""Stage 5: template keyword arguments (C6 Task 5).

Two kinds of kwarg, from two sources:

- SOURCE-derived (`archetype_kwargs`): what the RMXP data says, e.g. the
  item a ball grants, the trainer an event battles, where a warp lands. The
  oracle is the hand-written `playtest/chapters/ch05.py`, whose author
  typed these same values by hand: the generator must arrive at the same
  answer without a person.
- ROUTE-derived (`route_kwargs`): what the solver picked, e.g. the side a
  beat approaches from, and for a warp the press direction that follows
  from it (C6 plan A2: "direction and return_direction are the solver's
  cheapest walkable approach side").

`warp_candidates` closes a gap between the two. The solver can only pick a
side from candidates, and `routing.locations.cell_for_row` gives a warp row
none (the player stands ON a warp), so this derives them.

STATUS: stub (`assignments/C6/05_adapt.md`).
"""
from __future__ import annotations

import functools
from collections.abc import Callable, Mapping, Sequence

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import Kwargs, PlannedBeat, make_kwargs
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch
from rpg2gba.chapter_manifest.schema import ManifestRow, parse_row_id
from rpg2gba.pbs_converter._naming import to_constant
from rpg2gba.playtest.archetypes.item_ball import _uranium_item_constants
from rpg2gba.routing.locations import ApproachCandidate
from rpg2gba.traversal.graph import Cell, MapGraph

MapConstantFn = Callable[[int], str]


class NoArrivalError(ValueError):
    """An arrival-nudge match no warp lands on: the autorun never fires.
    `build_plan` refuses its rows by name instead of failing the chapter."""

# A2's answer: every CH01-CH05 warp source cell this corpus carries is
# door-stamped, so crossing it is always a held-D-pad step-on threshold, not
# a literal door or an arrow tile. This is a corpus-wide constant, not a
# per-row derivation -- nothing on a `ManifestRow`/floor `warp` assertion
# distinguishes the three mechanisms (see `playtest/archetypes/warp.py`'s
# own module docstring). If a future chapter needs a different mechanism,
# this becomes a real per-row lookup then, not before.
_WARP_MECHANISM = "threshold"

# route_kwargs("warp", side): standing on `side` of the crossing tile, this
# is the held D-pad press that steps onto it, and the press that reverses it
# for the round trip back.
_WARP_PRESS: dict[str, tuple[str, str]] = {
    "south": ("UP", "DOWN"),
    "north": ("DOWN", "UP"),
    "west": ("RIGHT", "LEFT"),
    "east": ("LEFT", "RIGHT"),
}

_SIDE_DELTA: dict[str, tuple[int, int]] = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}


def _floor(floors: Mapping[str, RowFloor], row_id: str) -> RowFloor:
    try:
        return floors[row_id]
    except KeyError:
        raise ValueError(
            f"archetype_kwargs: {row_id}: no floor available -- the beat "
            "cannot derive its kwargs without it"
        ) from None


def _one_assertion(floor: RowFloor, kind: str, *, row_id: str):
    found = [a for a in floor.assertions if a.kind == kind]
    if len(found) != 1:
        raise ValueError(
            f"archetype_kwargs: {row_id}: floor carries {len(found)} "
            f"{kind!r} assertions (expected exactly 1)"
        )
    return found[0]


def _role_row(match: ArchetypeMatch, role: str) -> str | None:
    return next((rid for rid, r in match.roles.items() if r == role), None)


def _require_role_row(match: ArchetypeMatch, role: str) -> str:
    row_id = _role_row(match, role)
    if row_id is None:
        raise ValueError(
            f"archetype_kwargs: {match.archetype} match on map {match.map_id} "
            f"event {match.event_id} has no {role!r} role"
        )
    return row_id


# -- item constants (CLAUDE.md §4.3: reference/uranium_id_map.json's "items"
# table, minted by pbs_converter._resolve.ItemResolverMixin, is the single
# source of truth). Reuses item_ball.py's own cached loader -- the forward
# check the task brief points at -- rather than re-reading the JSON here a
# second time.


def _resolve_item_constant(symbol: str, *, row_id: str) -> str:
    table = _uranium_item_constants()
    const = table.get(symbol)
    if const is None:
        raise ValueError(
            f"archetype_kwargs: {row_id}: source item {symbol!r} has no "
            "entry in reference/uranium_id_map.json's 'items' table -- "
            "mint it there first"
        )
    return const


# -- trainer constants: no reverse (name, trainer_class) -> trainer_const
# helper exists anywhere in the codebase today (only the forward check,
# `trainer.py`'s `_validate_battle_identity`, confirms an author-supplied
# candidate) -- research/05_adapt.md §2. Built here, once, cached.
@functools.cache
def _trainers_json() -> dict[str, dict]:
    from rpg2gba.beat_floor.lookup import default_build_dir
    from rpg2gba.trainer_converter.battles import load_trainers_json

    return load_trainers_json(default_build_dir() / "intermediate")


def _trainer_const_for(name: str, trainer_class: str, *, row_id: str) -> str:
    candidates = sorted(
        const for const, entry in _trainers_json().items()
        if entry.get("name") == name and entry.get("trainer_class") == trainer_class
    )
    if not candidates:
        raise ValueError(
            f"archetype_kwargs: {row_id}: no trainers.json entry matches "
            f"name={name!r} trainer_class={trainer_class!r}"
        )
    if len(candidates) > 1:
        raise ValueError(
            f"archetype_kwargs: {row_id}: {len(candidates)} trainers.json "
            f"entries match name={name!r} trainer_class={trainer_class!r}: "
            f"{candidates} -- ambiguous, nothing on the floor distinguishes "
            "them; pick one and pass trainer_const= by hand"
        )
    return candidates[0]


# -- per-template kwarg derivation --------------------------------------

def _warp_kwargs(
    beat: PlannedBeat, match: ArchetypeMatch, floors: Mapping[str, RowFloor],
    map_constant_fn: MapConstantFn, rows: Sequence[ManifestRow] = (),
) -> dict:
    row_id = _require_role_row(match, "warp")
    floor = _floor(floors, row_id)
    warp = _one_assertion(floor, "warp", row_id=row_id)
    out = {
        "map_constant": map_constant_fn(beat.map_id),
        "map_id": beat.map_id,
        "event_id": match.event_id,
        "dest_map_constant": map_constant_fn(warp.param("map_id")),
        "mechanism": _WARP_MECHANISM,
    }
    # Page-level: two pages of one event can each be a warp (CH01's
    # map049/ev002 p1 and p3), so a non-zero page is named.
    page_idx = parse_row_id(row_id).page_idx
    if page_idx:
        out["page_idx"] = page_idx
    return out


def _arrival_nudge_kwargs(
    beat: PlannedBeat, match: ArchetypeMatch, floors: Mapping[str, RowFloor],
    map_constant_fn: MapConstantFn, rows: Sequence[ManifestRow] = (),
) -> dict:
    row_id = _require_role_row(match, "nudge")
    map_constant = map_constant_fn(beat.map_id)

    from rpg2gba.playtest.cells import event_cell

    ex, ey = event_cell(map_constant, match.event_id)

    found = sorted(
        candidate_row_id for candidate_row_id, candidate_floor in floors.items()
        for a in candidate_floor.assertions
        if a.kind == "warp"
        and (a.param("map_id"), a.param("x"), a.param("y")) == (beat.map_id, ex, ey))
    if not found:
        # Not a lookup failure: nothing in the game lands here, so this
        # arrival autorun never fires (Route 1's three exits all land on
        # Moki (8,43), event 37's tile; the nudges on events 23 and 36 are
        # dead). The caller turns this into a named refusal.
        raise NoArrivalError(
            f"archetype_kwargs: {row_id}: no warp lands on this arrival autorun's "
            f"cell ({ex},{ey}) on map {beat.map_id} -- it never fires")
    # The source is an EVENT (`arrival_nudge_beat` takes from_event_id). Two
    # pages of one event (CH01's map049/ev002 p1 and p3), or several exit
    # tiles landing on this same cell (Route 1's events 22-24), are one
    # arrival; the lowest event stands for it.
    from_map, from_event = min(parse_row_id(rid).event_key for rid in found)
    return {
        "map_constant": map_constant,
        "map_id": beat.map_id,
        "event_id": match.event_id,
        "from_map_constant": map_constant_fn(from_map),
        "from_event_id": from_event,
    }


def _item_ball_kwargs(
    beat: PlannedBeat, match: ArchetypeMatch, floors: Mapping[str, RowFloor],
    map_constant_fn: MapConstantFn, rows: Sequence[ManifestRow] = (),
) -> dict:
    grant_row_id = _require_role_row(match, "grant")
    floor = _floor(floors, grant_row_id)
    grant = _one_assertion(floor, "item_grant", row_id=grant_row_id)
    item = _resolve_item_constant(grant.param("item"), row_id=grant_row_id)
    has_spent = _role_row(match, "spent") is not None
    out: dict = {
        "map_constant": map_constant_fn(beat.map_id),
        "map_id": beat.map_id,
        "event_id": match.event_id,
        "item": item,
        "negative_beat": has_spent,
    }
    if not has_spent:
        # A single-page ball has no spent page whose condition names the
        # letter, so the template demands it: read it off the grant page's
        # own code-123 write (page or arm), as `_toggled_page` does.
        letters = sorted({a.param("letter") for rid, f in floors.items()
                          if rid == grant_row_id or rid.startswith(f"{grant_row_id}/")
                          for a in f.assertions if a.kind == "self_switch_write"})
        if len(letters) != 1:
            raise ValueError(
                f"archetype_kwargs: {grant_row_id}: single-page item ball writes "
                f"self-switch letters {letters} (expected exactly 1)")
        out["self_switch_letter"] = letters[0]
    return out


def _trainer_kwargs(
    beat: PlannedBeat, match: ArchetypeMatch, floors: Mapping[str, RowFloor],
    map_constant_fn: MapConstantFn, rows: Sequence[ManifestRow] = (),
) -> dict:
    battle_row_id = _require_role_row(match, "battle")
    _floor(floors, battle_row_id)
    # The battle can sit in an arm of the page (Kevlar's Pokemon Center
    # trainer fights only on "Wanna fight? -> Yes": map068/ev014/p0/b0).
    battles = [a for rid, f in sorted(floors.items())
               if rid == battle_row_id or rid.startswith(f"{battle_row_id}/")
               for a in f.assertions if a.kind == "battle"]
    if len(battles) != 1:
        raise ValueError(
            f"archetype_kwargs: {battle_row_id}: page and arms carry {len(battles)} "
            "'battle' assertions (expected exactly 1)")
    battle = battles[0]
    if battle.param("kind") != "trainer":
        raise ValueError(
            f"archetype_kwargs: {battle_row_id}: floor battle kind is "
            f"{battle.param('kind')!r}, not 'trainer'"
        )
    trainer_type = battle.param("trainer_type")
    name = battle.param("name")
    trainer_class = to_constant("TRAINER_CLASS", trainer_type)
    trainer_const = _trainer_const_for(name, trainer_class, row_id=battle_row_id)
    defeat_flag = f"TRAINER_FLAGS_START + {trainer_const}"
    return {
        "map_constant": map_constant_fn(beat.map_id),
        "map_id": beat.map_id,
        "event_id": match.event_id,
        "trainer_const": trainer_const,
        "defeat_flag": defeat_flag,
        "trigger": match.params["trigger"],
        "phone": match.params["phone"],
        "double": match.params["double"],
        "retalk_pages": match.params["retalk_pages"],
        "rider": match.params["rider"],
    }


def _flavour_npc_kwargs(
    beat: PlannedBeat, match: ArchetypeMatch, floors: Mapping[str, RowFloor],
    map_constant_fn: MapConstantFn, rows: Sequence[ManifestRow] = (),
) -> dict:
    # No CH05 EXPECTED row pins this (research/05_adapt.md §9: CH05 has no
    # flavour_npc match), so only what the stub signature calls for and
    # what is directly, honestly manifest-derived: the identity triple, plus
    # `variant`, since `flavour_npc_beat` cross-checks a stated `variant=`
    # against the same `match.params["variant"]` this reads (module
    # docstring: "checked against the manifest independently derives"), so
    # stating it costs nothing and makes the generated call self-documenting
    # rather than silent about which of the three variants it claims to be.
    out: dict = {
        "map_constant": map_constant_fn(beat.map_id),
        "map_id": beat.map_id,
        "event_id": match.event_id,
        "variant": str(match.params["variant"]),
    }
    # Page-level archetype: an event can carry one match per page (a
    # multi-page NPC talks differently per story state; CH01 has 17 such
    # events), so the call names its page. 0 is the template default.
    talk_row = _require_role_row(match, "talk")
    page_idx = parse_row_id(talk_row).page_idx
    if page_idx:
        out["page_idx"] = page_idx
    if out["variant"] == "toggling":
        out.update(_toggled_page(talk_row, floors, rows))
    return out


def _toggled_page(talk_row: str, floors: Mapping[str, RowFloor],
                  rows: Sequence[ManifestRow]) -> dict:
    """For a toggling NPC: the self-switch its page (or an arm of it)
    writes, and the page of the same event that switch reveals -- the page
    whose own condition is that self-switch. Template defaults ("A", page
    1) are left implicit. No revealed page: nothing to add (the template's
    `_again` beat then claims no row). More than one: fail loud."""
    letters = sorted({a.param("letter") for rid, f in floors.items()
                      if rid == talk_row or rid.startswith(f"{talk_row}/")
                      for a in f.assertions if a.kind == "self_switch_write"})
    if len(letters) != 1:
        return {}
    letter = letters[0]
    key = parse_row_id(talk_row).event_key
    revealed = sorted(r.page_idx for r in rows
                      if r.kind == "page" and parse_row_id(r.row_id).event_key == key
                      and r.condition is not None and r.condition.self_switch_ch == letter)
    if len(revealed) > 1:
        raise ValueError(f"archetype_kwargs: {talk_row}: self-switch {letter} reveals "
                         f"pages {revealed} -- expected one")
    out: dict = {}
    if letter != "A":
        out["self_switch_letter"] = letter
    if revealed and revealed[0] != 1:
        out["toggled_page_idx"] = revealed[0]
    return out


_ARCHETYPE_KWARGS: dict[str, Callable] = {
    "warp": _warp_kwargs,
    "arrival_nudge": _arrival_nudge_kwargs,
    "item_ball": _item_ball_kwargs,
    "trainer": _trainer_kwargs,
    "flavour_npc": _flavour_npc_kwargs,
}


def archetype_kwargs(
    beat: PlannedBeat,
    match: ArchetypeMatch,
    floors: Mapping[str, RowFloor],
    *,
    map_constant_fn: MapConstantFn,
    rows: Sequence[ManifestRow] = (),
) -> Kwargs:
    """The source-derived kwargs for one archetype beat (sorted, via
    `make_kwargs`). Only keywords the template accepts. Raises `ValueError`
    naming the row if a value can't be derived (a floor without the
    expected assertion, an unknown item, an unmintable trainer). `rows` is
    the manifest, needed only to find a toggling NPC's revealed page."""
    fn = _ARCHETYPE_KWARGS.get(match.archetype)
    if fn is None:
        raise ValueError(
            f"archetype_kwargs: unknown archetype {match.archetype!r} for "
            f"beat {beat.name!r}"
        )
    values = fn(beat, match, floors, map_constant_fn, rows)
    return make_kwargs(**values)


def escort_kwargs(
    beat: PlannedBeat, floors: Mapping[str, RowFloor], *, map_constant_fn: MapConstantFn,
) -> Kwargs:
    """The source-derived kwargs for an `escort` beat (ruling 11): the
    event, and the map its page's one transfer lands on. The landing cell
    the template reads off the same floor itself."""
    row_id = beat.rows[0]
    warp = _one_assertion(_floor(floors, row_id), "warp", row_id=row_id)
    return make_kwargs(
        map_constant=map_constant_fn(beat.map_id),
        map_id=beat.map_id,
        event_id=parse_row_id(row_id).event_id,
        dest_map_constant=map_constant_fn(warp.param("map_id")),
    )


def warp_candidates(cell: Cell, graph: MapGraph) -> tuple[ApproachCandidate, ...]:
    """Every side a warp cell can be stepped onto from: one candidate per
    walkable orthogonal neighbour, `side` naming where the player stands
    ("north" = the cell above). In N, E, S, W order."""
    x, y = cell
    candidates: list[ApproachCandidate] = []
    for side, (dx, dy) in _SIDE_DELTA.items():
        nx, ny = x + dx, y + dy
        if not graph.is_walkable((nx, ny)):
            continue
        candidates.append(ApproachCandidate(
            x=nx, y=ny, side=side,
            resolver=f"warp_candidates(({x}, {y}), side={side!r})",
        ))
    return tuple(candidates)


def is_boundary_warp(
    beat: PlannedBeat, floors: Mapping[str, RowFloor], chain_maps: frozenset[int],
) -> bool:
    """Does this warp beat leave the chapter? True when its floor's warp
    destination is on none of `chain_maps` -- the maps of this chapter and
    every predecessor (`reference/chapters.json`, the §4.3 source of truth
    for membership), i.e. every map this chapter's ROM stages. Such a warp
    can't be round-tripped: the far side belongs to a chapter not built yet
    (C6 Task 9's blocker). Raises on a non-warp beat or a floor without
    exactly one warp assertion."""
    if beat.template != "warp":
        raise ValueError(f"is_boundary_warp: beat {beat.name!r} is a {beat.template!r}")
    dests = {a.param("map_id") for row_id in beat.rows
             for a in _floor(floors, row_id).assertions if a.kind == "warp"}
    if len(dests) != 1:
        raise ValueError(
            f"is_boundary_warp: beat {beat.name!r} has {len(dests)} warp "
            f"destinations {sorted(dests)} (expected exactly 1)")
    return dests.pop() not in chain_maps


def route_kwargs(template: str, side: str, *, boundary: bool = False) -> Kwargs:
    """The kwargs a solver pick turns into for `template`. For `warp`: the
    press direction (standing south of the tile, you press UP), a round trip
    and the reverse press -- or, for a `boundary` warp (its destination is
    a later chapter's map, see `is_boundary_warp`), the press direction and
    `boundary=True`, with no round trip: the beat stops on `side` and never
    crosses. For every other template: `approach_prefer`. Raises
    `ValueError` on an unknown side, or `boundary` on a non-warp."""
    if boundary and template != "warp":
        raise ValueError(f"route_kwargs: boundary=True on template {template!r}, not 'warp'")
    if template == "warp":
        press = _WARP_PRESS.get(side)
        if press is None:
            raise ValueError(
                f"route_kwargs: unknown side {side!r} for template 'warp' "
                f"-- expected one of {sorted(_WARP_PRESS)}"
            )
        direction, return_direction = press
        if boundary:
            return make_kwargs(direction=direction, boundary=True)
        return make_kwargs(
            direction=direction, return_direction=return_direction, round_trip=True)
    return make_kwargs(approach_prefer=side)
