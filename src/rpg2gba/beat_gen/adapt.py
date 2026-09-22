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
from collections.abc import Callable, Mapping

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import Kwargs, PlannedBeat, make_kwargs
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.pbs_converter._naming import to_constant
from rpg2gba.playtest.archetypes.item_ball import _uranium_item_constants
from rpg2gba.routing.locations import ApproachCandidate
from rpg2gba.traversal.graph import Cell, MapGraph

MapConstantFn = Callable[[int], str]

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
    map_constant_fn: MapConstantFn,
) -> dict:
    row_id = _require_role_row(match, "warp")
    floor = _floor(floors, row_id)
    warp = _one_assertion(floor, "warp", row_id=row_id)
    return {
        "map_constant": map_constant_fn(beat.map_id),
        "map_id": beat.map_id,
        "event_id": match.event_id,
        "dest_map_constant": map_constant_fn(warp.param("map_id")),
        "mechanism": _WARP_MECHANISM,
    }


def _arrival_nudge_kwargs(
    beat: PlannedBeat, match: ArchetypeMatch, floors: Mapping[str, RowFloor],
    map_constant_fn: MapConstantFn,
) -> dict:
    row_id = _require_role_row(match, "nudge")
    map_constant = map_constant_fn(beat.map_id)

    from rpg2gba.playtest.cells import event_cell

    ex, ey = event_cell(map_constant, match.event_id)

    found: list[str] = []
    for candidate_row_id, candidate_floor in floors.items():
        for a in candidate_floor.assertions:
            if a.kind != "warp":
                continue
            if (a.param("map_id"), a.param("x"), a.param("y")) == (beat.map_id, ex, ey):
                found.append(candidate_row_id)
    found = sorted(set(found))
    if not found:
        raise ValueError(
            f"archetype_kwargs: {row_id}: no warp floor assertion in the "
            f"supplied floors lands on this event's own cell ({ex},{ey}) on "
            f"map {beat.map_id} -- the source warp cannot be identified"
        )
    if len(found) > 1:
        raise ValueError(
            f"archetype_kwargs: {row_id}: {len(found)} warp floor "
            f"assertions land on ({ex},{ey}) on map {beat.map_id}: {found} "
            "-- ambiguous"
        )
    source_row_id = found[0]
    parsed = parse_row_id(source_row_id)
    return {
        "map_constant": map_constant,
        "map_id": beat.map_id,
        "event_id": match.event_id,
        "from_map_constant": map_constant_fn(parsed.map_id),
        "from_event_id": parsed.event_id,
    }


def _item_ball_kwargs(
    beat: PlannedBeat, match: ArchetypeMatch, floors: Mapping[str, RowFloor],
    map_constant_fn: MapConstantFn,
) -> dict:
    grant_row_id = _require_role_row(match, "grant")
    floor = _floor(floors, grant_row_id)
    grant = _one_assertion(floor, "item_grant", row_id=grant_row_id)
    item = _resolve_item_constant(grant.param("item"), row_id=grant_row_id)
    return {
        "map_constant": map_constant_fn(beat.map_id),
        "map_id": beat.map_id,
        "event_id": match.event_id,
        "item": item,
        "negative_beat": _role_row(match, "spent") is not None,
    }


def _trainer_kwargs(
    beat: PlannedBeat, match: ArchetypeMatch, floors: Mapping[str, RowFloor],
    map_constant_fn: MapConstantFn,
) -> dict:
    battle_row_id = _require_role_row(match, "battle")
    floor = _floor(floors, battle_row_id)
    battle = _one_assertion(floor, "battle", row_id=battle_row_id)
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
    map_constant_fn: MapConstantFn,
) -> dict:
    # No CH05 EXPECTED row pins this (research/05_adapt.md §9: CH05 has no
    # flavour_npc match), so only what the stub signature calls for and
    # what is directly, honestly manifest-derived: the identity triple, plus
    # `variant`, since `flavour_npc_beat` cross-checks a stated `variant=`
    # against the same `match.params["variant"]` this reads (module
    # docstring: "checked against the manifest independently derives"), so
    # stating it costs nothing and makes the generated call self-documenting
    # rather than silent about which of the three variants it claims to be.
    return {
        "map_constant": map_constant_fn(beat.map_id),
        "map_id": beat.map_id,
        "event_id": match.event_id,
        "variant": str(match.params["variant"]),
    }


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
) -> Kwargs:
    """The source-derived kwargs for one archetype beat (sorted, via
    `make_kwargs`). Only keywords the template accepts. Raises `ValueError`
    naming the row if a value can't be derived (a floor without the
    expected assertion, an unknown item, an unmintable trainer)."""
    fn = _ARCHETYPE_KWARGS.get(match.archetype)
    if fn is None:
        raise ValueError(
            f"archetype_kwargs: unknown archetype {match.archetype!r} for "
            f"beat {beat.name!r}"
        )
    values = fn(beat, match, floors, map_constant_fn)
    return make_kwargs(**values)


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


def route_kwargs(template: str, side: str) -> Kwargs:
    """The kwargs a solver pick turns into for `template`. For `warp`: the
    press direction (standing south of the tile, you press UP), a round trip
    and the reverse press. For every other template: `approach_prefer`.
    Raises `ValueError` on an unknown side."""
    if template == "warp":
        press = _WARP_PRESS.get(side)
        if press is None:
            raise ValueError(
                f"route_kwargs: unknown side {side!r} for template 'warp' "
                f"-- expected one of {sorted(_WARP_PRESS)}"
            )
        direction, return_direction = press
        return make_kwargs(
            direction=direction, return_direction=return_direction, round_trip=True)
    return make_kwargs(approach_prefer=side)
