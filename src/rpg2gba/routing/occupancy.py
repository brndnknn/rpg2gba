"""Per-map stationary-NPC occupancy -- the set of cells the offline route
solver may never step onto because a stationary object event stands there.

Reads the SAME staged engine map data `traversal.triggers.build_trigger_overlay`
reads (`engine/data/maps/<dir_name>/map.json`'s `object_events`, keyed off
`map_constants.json`'s `dir_name`) -- for the same reason that module's own
docstring gives: occupancy and trigger sight cones must be present or absent
together for a given map, or a chapter could get one without the other.

`build_trigger_overlay` only inspects object events with `trainer_type !=
TRAINER_TYPE_NONE`, because it only cares about sight cones. Occupancy is
broader: EVERY object event on a map -- trainer or plain NPC -- stands on its
spawn tile and blocks it just the same, so this module walks the whole
`object_events` list, not just the trainer subset.

== Classification: stationary vs. mobile vs. unrecognized ==

Classification is by `movement_type` string alone, against two explicit
tables cross-checked against `engine/src/event_object_movement.c`'s
`sMovementTypeCallbacks` dispatch table (CLAUDE.md §4.7 -- verify against the
real fork, not memory):

STATIONARY (blocked) -- the callback never changes the object's tile
position, whether it turns in place or does nothing at all:
  - `MOVEMENT_TYPE_NONE` -- `MovementType_None` is a literal empty callback
    (`movement_type_empty_callback(MovementType_None)`,
    event_object_movement.c:3944).
  - The whole `MOVEMENT_TYPE_FACE_*` family (`FACE_DOWN`, `FACE_UP`,
    `FACE_LEFT`, `FACE_RIGHT`, `FACE_DOWN_AND_UP`, `FACE_LEFT_AND_RIGHT`,
    `FACE_UP_AND_LEFT`, `FACE_UP_AND_RIGHT`, `FACE_DOWN_AND_LEFT`,
    `FACE_DOWN_AND_RIGHT`, `FACE_DOWN_UP_AND_LEFT`, `FACE_DOWN_UP_AND_RIGHT`,
    `FACE_UP_LEFT_AND_RIGHT`, `FACE_DOWN_LEFT_AND_RIGHT`) -- every one of
    these dispatches to a `MovementType_Face*` callback
    (event_object_movement.c:4396-5028) that only ever issues a
    `GetFaceDirectionMovementAction` (a turn-in-place action), never a walk
    action. `traversal.triggers`'s own module docstring independently
    verifies this for the UP_AND_LEFT/DOWN_AND_LEFT/DOWN_AND_RIGHT/LOOK_AROUND
    subset; the rest follow the same `MovementType_Face*` shape by
    inspection of the dispatch table.
  - `MOVEMENT_TYPE_LOOK_AROUND` -- `MovementType_LookAround`
    (event_object_movement.c:4229-4270), turn-in-place only, per
    `traversal.triggers`'s own citation.

MOBILE (not blocked) -- the callback issues a genuine walk action, changing
tile position, so its offline location can't be predicted:
  - The whole `MOVEMENT_TYPE_WANDER_*` family (`WANDER_AROUND`,
    `WANDER_AROUND_SLOWER`, `WANDER_UP_AND_DOWN`, `WANDER_DOWN_AND_UP`,
    `WANDER_LEFT_AND_RIGHT`, `WANDER_RIGHT_AND_LEFT`) -- `MovementType_Wander*`
    (event_object_movement.c:3945-4386), each issues a walk action on a
    (possibly randomised) heading.
  - `MOVEMENT_TYPE_WALK_UP_AND_DOWN` / `WALK_DOWN_AND_UP` /
    `WALK_LEFT_AND_RIGHT` / `WALK_RIGHT_AND_LEFT` -- all four share
    `MovementType_WalkBackAndForth` (event_object_movement.c:5129-5187),
    patrolling `movement_range_x/y` tiles from spawn, per
    `traversal.triggers`'s own citation for this callback.
  - The whole `MOVEMENT_TYPE_WALK_SEQUENCE_*` family (24 fixed-order-patrol
    variants) -- each dispatches to its own `MovementType_WalkSequence*`
    callback (event_object_movement.c:5234-5522), all of which patrol a fixed
    cycle of walk actions, changing tile position.

UNRECOGNIZED -- fails loud (`OccupancyError`), never defaulted to either
bucket (CLAUDE.md §4.5). This deliberately includes
`MOVEMENT_TYPE_RPG2GBA_CUSTOM_ROUTE` (this fork's own addition, `0x53`,
`MovementType_Rpg2gbaCustomRoute` -- an autonomous per-object route-bytecode
player, `reference/guides/custom_route_interpreter.md`): per that guide and
`reference/archive/SLICE1_EVENTS.md`, a custom route can be a stand-in-place
idle (turn/wait commands only) OR a genuine patrol that walks the object
around a loop -- which one depends on the SPECIFIC route's bytecode (keyed
by the object event's `trainer_sight_or_berry_tree_id`, reused as a route
index for this movement type -- see `reference/memory-archive.md`'s "an
object can pace or it can see, never both" note). That bytecode is not part
of the staged `map.json` this module (or `build_trigger_overlay`) reads, so
there is no way to tell the two cases apart from the data available here.
Guessing either way would be exactly the silent-default failure mode CLAUDE.md
§4.5 exists to prevent: guessing "stationary" would misblock a patrol that
has walked off its spawn tile by playtest time, guessing "mobile" would
silently under-block a standing NPC the player cannot actually walk through.
Also unrecognized (never encountered on Uranium's corpus so far, and outside
what has been verified above): `MOVEMENT_TYPE_PLAYER`,
the `ROTATE_*`/`COPY_PLAYER*` families,
`TREE_DISGUISE`/`MOUNTAIN_DISGUISE`, `BURIED`, the `WALK_IN_PLACE_*` /
`JOG_IN_PLACE_*` / `RUN_IN_PLACE_*` / `WALK_SLOWLY_IN_PLACE_*` families
(despite the "WALK"/"JOG"/"RUN" in the name, these dispatch to
`MovementType_WalkInPlace`/`WalkSlowlyInPlace`, event_object_movement.c:6392-
6402, which animate stepping WITHOUT changing tile position -- a naive
prefix match on "WALK_" would misclassify these as mobile, which is why this
module uses an explicit table rather than a prefix rule), `INVISIBLE`, and
`FOLLOW_PLAYER`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ..traversal.triggers import DEFAULT_ENGINE_MAPS_DIR, DEFAULT_MAP_CONSTANTS_JSON

logger = logging.getLogger(__name__)

Cell = tuple[int, int]


class OccupancyError(ValueError):
    """An object event's movement type could not be classified as
    stationary or mobile -- see module docstring."""


_STATIONARY_MOVEMENT_TYPES = frozenset({
    "MOVEMENT_TYPE_NONE",
    "MOVEMENT_TYPE_FACE_DOWN",
    "MOVEMENT_TYPE_FACE_UP",
    "MOVEMENT_TYPE_FACE_LEFT",
    "MOVEMENT_TYPE_FACE_RIGHT",
    "MOVEMENT_TYPE_FACE_DOWN_AND_UP",
    "MOVEMENT_TYPE_FACE_LEFT_AND_RIGHT",
    "MOVEMENT_TYPE_FACE_UP_AND_LEFT",
    "MOVEMENT_TYPE_FACE_UP_AND_RIGHT",
    "MOVEMENT_TYPE_FACE_DOWN_AND_LEFT",
    "MOVEMENT_TYPE_FACE_DOWN_AND_RIGHT",
    "MOVEMENT_TYPE_FACE_DOWN_UP_AND_LEFT",
    "MOVEMENT_TYPE_FACE_DOWN_UP_AND_RIGHT",
    "MOVEMENT_TYPE_FACE_UP_LEFT_AND_RIGHT",
    "MOVEMENT_TYPE_FACE_DOWN_LEFT_AND_RIGHT",
    "MOVEMENT_TYPE_LOOK_AROUND",
    # Added 2026-09-09, when CH03's map 31 became the first Uranium map to
    # carry one ('BerryTreeScript' at (32,5)) -- the docstring above used to
    # list this type as never-encountered. Verified stationary against the
    # fork per CLAUDE.md 4.7 rather than assumed from the name:
    # `MovementType_BerryTreeGrowth` (event_object_movement.c:4445) dispatches
    # through `gMovementTypeFuncs_BerryTreeGrowth`, whose five states are
    # NORMAL / MOVE / SPARKLE_START / SPARKLE / SPARKLE_END. The only
    # movement action any of them issues is
    # `MOVEMENT_ACTION_START_ANIM_IN_DIRECTION` (line 4491) -- an animation,
    # not a step -- so the object never leaves its spawn tile and the
    # BERRYTREEFUNC_MOVE state's name is about the growth animation, not
    # locomotion. It occupies its cell at every berry stage: the stage-0
    # branch sets `invisible = TRUE` (line 4467) but does not remove the
    # object event, so the tile stays blocked whether or not a berry is
    # showing.
    "MOVEMENT_TYPE_BERRY_TREE_GROWTH",
})

_MOBILE_MOVEMENT_TYPES = frozenset({
    "MOVEMENT_TYPE_WANDER_AROUND",
    "MOVEMENT_TYPE_WANDER_AROUND_SLOWER",
    "MOVEMENT_TYPE_WANDER_UP_AND_DOWN",
    "MOVEMENT_TYPE_WANDER_DOWN_AND_UP",
    "MOVEMENT_TYPE_WANDER_LEFT_AND_RIGHT",
    "MOVEMENT_TYPE_WANDER_RIGHT_AND_LEFT",
    "MOVEMENT_TYPE_WALK_UP_AND_DOWN",
    "MOVEMENT_TYPE_WALK_DOWN_AND_UP",
    "MOVEMENT_TYPE_WALK_LEFT_AND_RIGHT",
    "MOVEMENT_TYPE_WALK_RIGHT_AND_LEFT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_UP_RIGHT_LEFT_DOWN",
    "MOVEMENT_TYPE_WALK_SEQUENCE_RIGHT_LEFT_DOWN_UP",
    "MOVEMENT_TYPE_WALK_SEQUENCE_DOWN_UP_RIGHT_LEFT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_LEFT_DOWN_UP_RIGHT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_UP_LEFT_RIGHT_DOWN",
    "MOVEMENT_TYPE_WALK_SEQUENCE_LEFT_RIGHT_DOWN_UP",
    "MOVEMENT_TYPE_WALK_SEQUENCE_DOWN_UP_LEFT_RIGHT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_RIGHT_DOWN_UP_LEFT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_LEFT_UP_DOWN_RIGHT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_UP_DOWN_RIGHT_LEFT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_RIGHT_LEFT_UP_DOWN",
    "MOVEMENT_TYPE_WALK_SEQUENCE_DOWN_RIGHT_LEFT_UP",
    "MOVEMENT_TYPE_WALK_SEQUENCE_RIGHT_UP_DOWN_LEFT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_UP_DOWN_LEFT_RIGHT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_LEFT_RIGHT_UP_DOWN",
    "MOVEMENT_TYPE_WALK_SEQUENCE_DOWN_LEFT_RIGHT_UP",
    "MOVEMENT_TYPE_WALK_SEQUENCE_UP_LEFT_DOWN_RIGHT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_DOWN_RIGHT_UP_LEFT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_LEFT_DOWN_RIGHT_UP",
    "MOVEMENT_TYPE_WALK_SEQUENCE_RIGHT_UP_LEFT_DOWN",
    "MOVEMENT_TYPE_WALK_SEQUENCE_UP_RIGHT_DOWN_LEFT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_DOWN_LEFT_UP_RIGHT",
    "MOVEMENT_TYPE_WALK_SEQUENCE_LEFT_UP_RIGHT_DOWN",
    "MOVEMENT_TYPE_WALK_SEQUENCE_RIGHT_DOWN_LEFT_UP",
    # This fork's autonomous route-bytecode player. OPERATOR RULING
    # 2026-09-04: patrolling NPCs stay PASSABLE offline -- only genuinely
    # stationary ones are blocked. Recorded here because the classification
    # is a decision, not a fact about the callback: a custom route steps
    # (Map037 ev005 paces 1,1,4,4 = DOWN,DOWN,UP,UP over (8,7),(8,8),(8,9)),
    # so its footprint IS derivable from the RMXP move_route in the Uranium
    # map JSON -- we choose not to use it, and accept two consequences:
    # offline tile costs stay optimistic on patrol tiles, and a custom route
    # with no step opcodes (idle in place) is under-blocked. The runtime
    # walker still re-plans around live object tiles
    # (playtest/emulator.py `_occupied_object_tiles`), which is what makes
    # this safe rather than merely cheap.
    "MOVEMENT_TYPE_RPG2GBA_CUSTOM_ROUTE",
})


@dataclass(frozen=True)
class OccupiedTile:
    """One stationary object event blocking one cell."""

    cell: Cell
    script: str
    movement_type: str


@dataclass(frozen=True)
class MapOccupancy:
    """The occupancy overlay for one map: every stationary object event's
    spawn tile, and the event that owns it."""

    map_id: int
    tiles: tuple[OccupiedTile, ...]

    def blocked_cells(self) -> frozenset[Cell]:
        return frozenset(t.cell for t in self.tiles)

    def at(self, cell: Cell) -> OccupiedTile | None:
        for tile in self.tiles:
            if tile.cell == cell:
                return tile
        return None


def _load_map_constants_entry(map_id: int, path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entry = raw.get(str(map_id))
    if entry is None:
        raise KeyError(f"map id {map_id} absent from {path}")
    return entry


def _load_emitted_map(map_id: int, dir_name: str, maps_dir: Path) -> dict:
    path = maps_dir / dir_name / "map.json"
    if not path.exists():
        raise FileNotFoundError(
            f"map id {map_id} (dir_name={dir_name!r}) has no emitted map data -- "
            f"tried {path}. Only a subset of the corpus is emitted so far; this "
            "map hasn't been converted yet."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def build_occupancy(
    map_id: int,
    *,
    map_constants_json: Path = DEFAULT_MAP_CONSTANTS_JSON,
    engine_maps_dir: Path = DEFAULT_ENGINE_MAPS_DIR,
) -> MapOccupancy:
    """Build the occupancy overlay for `map_id` from the same already-emitted
    pokeemerald map data `build_trigger_overlay` reads (see module
    docstring). Fails loud (raises `FileNotFoundError`/`KeyError`) on the same
    terms as `build_trigger_overlay` if the map hasn't been emitted yet, and
    raises `OccupancyError` if any object event's `movement_type` isn't in
    either classification table."""
    constants_entry = _load_map_constants_entry(map_id, map_constants_json)
    dir_name = constants_entry["dir_name"]
    map_json = _load_emitted_map(map_id, dir_name, engine_maps_dir)

    object_events = map_json.get("object_events", [])

    tiles: list[OccupiedTile] = []
    mobile_count = 0
    for oe in object_events:
        movement_type = oe["movement_type"]
        script = oe.get("script", "<unnamed>")
        cell = (oe["x"], oe["y"])

        if movement_type in _STATIONARY_MOVEMENT_TYPES:
            tiles.append(OccupiedTile(cell=cell, script=script, movement_type=movement_type))
            continue
        if movement_type in _MOBILE_MOVEMENT_TYPES:
            mobile_count += 1
            continue
        raise OccupancyError(
            f"map {map_id}: object event {script!r} at {cell} uses movement_type "
            f"{movement_type!r}, which has no derived stationary/mobile "
            "occupancy classification -- verify it against "
            "engine/src/event_object_movement.c's sMovementTypeCallbacks "
            "dispatch table and add it to occupancy.py's tables before "
            "proceeding (see module docstring); refusing to guess."
        )

    logger.info(
        "map %s: %d object event(s), %d blocked (stationary), %d mobile",
        map_id, len(object_events), len(tiles), mobile_count,
    )
    return MapOccupancy(map_id=map_id, tiles=tuple(tiles))
