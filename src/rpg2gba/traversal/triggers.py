"""Per-map trigger overlay — the set of tiles that fire a script when the
player steps on them (coord events) or is seen from them (trainer sight),
derived from the ALREADY-EMITTED pokeemerald map data, not from the RPG Maker
source. Modelling the emitted ROM data is deliberate: it is what actually
ships, and the deterministic transpiler that produced it can already diverge
from Uranium's original RGSS event in ways this overlay needs to see.

Data chain:

    output/uranium-build/porymap/map_constants.json  -- Uranium map id -> dir_name
    engine/data/maps/<dir_name>/map.json              -- object_events, coord_events

Only a fraction of the 198-map corpus is emitted so far (see
`map_constants.json`'s `dir_name` vs what actually exists under
`engine/data/maps/`); `build_trigger_overlay` fails loud (raises, names the
map id and the path it tried) rather than returning an empty overlay when a
map hasn't been emitted yet -- CLAUDE.md §4.5.

== Trainer sight, matched against engine/src/trainer_see.c ==

`GetTrainerApproachDistance` (trainer_see.c:636-660):
  - TRAINER_TYPE_NORMAL sees along exactly one direction: the trainer's
    *current* `facingDirection` (trainer_see.c:642-649).
  - TRAINER_TYPE_SEE_ALL_DIRECTIONS and TRAINER_TYPE_BURIED scan all four
    cardinal directions regardless of movement type (trainer_see.c:651-659) --
    modelled here by overriding `facings` to all four `CARDINALS` for those
    two trainer types, ignoring the movement type's own facing table.

The four directional distance functions (trainer_see.c:665-706,
`GetTrainerApproachDistanceSouth/North/West/East`) require the player to
match the trainer's coordinate on the perpendicular axis EXACTLY (e.g. south:
`trainerObj->currentCoords.x == x`) -- the sight cone is a one-tile-wide
straight line, never a widening cone. Distance runs `range` tiles, starting
at 1 tile away (excludes the trainer's own cell) through `range` tiles away
inclusive.

`CheckPathBetweenTrainerAndPlayer` (trainer_see.c:708 onward) walks the
`approachDistance - 1` intervening tiles and aborts the whole approach if any
of them carries a collision flag -- impassable terrain/elevation, or another
object event occupying the tile. SIMPLIFICATION, documented (in the spirit of
`graph.py`'s own documented simplifications): the engine only ever runs this
check once the player is already standing at a specific candidate distance,
because runtime trainer-sight is polled against the player's actual position,
not pre-computed as a static overlay. This module instead ray-marches
outward from the trainer's spawn tile along each facing direction and stops
at (excludes) the first tile that is either not walkable per the supplied
`MapGraph` or is the static spawn tile of another object event -- the offline
equivalent of "the path is blocked, so nothing past this point can trigger
the trainer", which is the same terminal effect `CheckPathBetweenTrainerAndPlayer`
produces for any player position beyond the blocker.

== Movement type -> facing/wander profile ==

`gInitialMovementTypeFacingDirections` (event_object_movement.c:403-475) only
gives the INITIAL facing direction; the runtime `MovementType_*` callback
(dispatched via `sMovementTypeFuncs`, event_object_movement.c:260-357) can
turn the object to a different facing, or move it, over time. Each profile
below cites the callback(s) it was derived from. The table only covers
movement types that actually appear on a `trainer_type != TRAINER_TYPE_NONE`
object event in the currently-emitted Uranium maps (verified against every
`engine/data/maps/<dir>/map.json` reachable from `map_constants.json`, 2026):
`build_trigger_overlay` fails loud if it meets a trainer with a movement type
outside this table, rather than silently guessing a profile for a movement
type this overlay has never been asked to model.

  MOVEMENT_TYPE_FACE_DOWN/UP/LEFT/RIGHT
      Callback: MovementType_FaceDirection (event_object_movement.c:4396-4420).
      Step0 faces `objectEvent->facingDirection` once (the initial direction
      from `gInitialMovementTypeFacingDirections`) and every subsequent step
      is a no-op -- the object never turns again and never moves.
      facings = {initial direction}, wanders = False.

  MOVEMENT_TYPE_FACE_UP_AND_LEFT / FACE_DOWN_AND_LEFT / FACE_DOWN_AND_RIGHT
      Callbacks: MovementType_FaceUpAndLeft (4649-4697),
      MovementType_FaceDownAndLeft (4749-4797),
      MovementType_FaceDownAndRight (4799-4847). Step4 of each picks a random
      direction from a fixed 2-element table --
      `gUpAndLeftDirections = {DIR_NORTH, DIR_WEST}`,
      `gDownAndLeftDirections = {DIR_SOUTH, DIR_WEST}`,
      `gDownAndRightDirections = {DIR_SOUTH, DIR_EAST}`
      (src/data/object_events/movement_type_func_tables.h:107-137) -- and
      only ever calls `GetFaceDirectionMovementAction` (a turn-in-place
      action), never a walk action. facings = that 2-direction set,
      wanders = False.

  MOVEMENT_TYPE_LOOK_AROUND
      Callback: MovementType_LookAround (4229-4270). Step4 picks a random
      direction from `gStandardDirections = {DIR_SOUTH, DIR_NORTH, DIR_WEST,
      DIR_EAST}` (movement_type_func_tables.h:21) and only turns in place
      (GetFaceDirectionMovementAction). facings = all four CARDINALS,
      wanders = False.

  MOVEMENT_TYPE_WALK_UP_AND_DOWN
      Callback: MovementType_WalkBackAndForth (5129-5187), shared by all
      WALK_*_AND_*/WALK_RIGHT_AND_LEFT types. Step1 faces either the
      movement type's initial direction or its opposite
      (`GetOppositeDirection`); Step2 issues a genuine walk action
      (`GetWalkNormalMovementAction`) each cycle, so the object changes
      *tile position*, patrolling between its spawn cell and
      `movement_range_x/y` tiles away. Initial direction for
      MOVEMENT_TYPE_WALK_UP_AND_DOWN is DIR_NORTH
      (gInitialMovementTypeFacingDirections, line 429).
      facings = {NORTH, SOUTH}, wanders = True.

  MOVEMENT_TYPE_WANDER_AROUND
      Callback: MovementType_WanderAround (3945-...). Step4 picks a random
      direction from `gStandardDirections` and Step2 issues a walk action
      via ObjectEventExecSingleMovementAction on that heading, changing tile
      position. facings = all four CARDINALS, wanders = True.

Certainty rule (per the brief): a trainer whose `facings` is a single
direction AND is not `wanders` yields CERTAIN tiles (its cone is fully
determined). Any trainer with more than one possible facing, or that
wanders, yields POSSIBLE tiles for the union over all its facings, because
this overlay does not simulate the RNG or the patrol path -- only the set of
directions/positions the trainer *could* be facing/at. TRAINER_TYPE_SEE_ALL_
DIRECTIONS and TRAINER_TYPE_BURIED are always POSSIBLE by this rule, since
their effective facing set is all four CARDINALS regardless of movement type.
Coord events are always CERTAIN: stepping on the tile always fires the
script, no facing/RNG involved.

If no `MapGraph` is supplied, sight-line occlusion is not modelled at all --
every candidate cell out to the trainer's full sight range is included, and
every one of those trainer-sight tiles is forced to POSSIBLE (never CERTAIN),
because we cannot rule out an intervening blocker we didn't check for. A
warning is logged once per `build_trigger_overlay` call in that case.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .direction import CARDINALS, Direction

if TYPE_CHECKING:
    from .graph import MapGraph

logger = logging.getLogger(__name__)

Cell = tuple[int, int]

DEFAULT_MAP_CONSTANTS_JSON = Path("output/uranium-build/porymap/map_constants.json")
DEFAULT_ENGINE_MAPS_DIR = Path("engine/data/maps")

_TRAINER_TYPE_NONE = "TRAINER_TYPE_NONE"
_TRAINER_TYPE_NORMAL = "TRAINER_TYPE_NORMAL"
_TRAINER_TYPE_SEE_ALL_DIRECTIONS = "TRAINER_TYPE_SEE_ALL_DIRECTIONS"
_TRAINER_TYPE_BURIED = "TRAINER_TYPE_BURIED"

_ALL_DIRECTIONS_TRAINER_TYPES = frozenset(
    {_TRAINER_TYPE_SEE_ALL_DIRECTIONS, _TRAINER_TYPE_BURIED}
)
_KNOWN_TRAINER_TYPES = frozenset(
    {_TRAINER_TYPE_NORMAL, _TRAINER_TYPE_SEE_ALL_DIRECTIONS, _TRAINER_TYPE_BURIED}
)


class TriggerKind(Enum):
    COORD_EVENT = "coord_event"
    TRAINER_SIGHT = "trainer_sight"


class Certainty(Enum):
    CERTAIN = "certain"
    POSSIBLE = "possible"


@dataclass(frozen=True)
class TriggerRef:
    """One reason a tile is a trigger. `owner_xy` is the trainer's spawn
    tile for TRAINER_SIGHT refs, or None for COORD_EVENT refs (a coord event
    has no "owner" position distinct from the trigger tile itself)."""

    kind: TriggerKind
    script: str
    certainty: Certainty
    owner_xy: Cell | None
    detail: str


@dataclass
class TriggerOverlay:
    """The trigger overlay for one map: every tile that can fire a script,
    and every reason it can."""

    map_id: int
    tiles: dict[Cell, list[TriggerRef]] = field(default_factory=dict)

    def refs_at(self, cell: Cell) -> list[TriggerRef]:
        return self.tiles.get(cell, [])

    def certain_tiles(self) -> set[Cell]:
        """Tiles carrying at least one CERTAIN trigger."""
        return {
            cell
            for cell, refs in self.tiles.items()
            if any(r.certainty is Certainty.CERTAIN for r in refs)
        }

    def possible_tiles(self) -> set[Cell]:
        """Tiles carrying at least one POSSIBLE trigger."""
        return {
            cell
            for cell, refs in self.tiles.items()
            if any(r.certainty is Certainty.POSSIBLE for r in refs)
        }

    def foreign_tiles(self, destination_scripts: set[str]) -> set[Cell]:
        """Tiles whose triggers all belong to scripts OTHER than
        `destination_scripts` -- i.e. tiles that are safe to treat as "not
        this destination's own trigger" (a tile with a mix of a destination
        script and a foreign script is excluded, since it *does* belong at
        least partly to the destination)."""
        return {
            cell
            for cell, refs in self.tiles.items()
            if refs and all(r.script not in destination_scripts for r in refs)
        }


@dataclass(frozen=True)
class MovementProfile:
    """What a movement type does to a trainer's facing/position over time,
    per the module docstring's engine citations."""

    facings: frozenset[Direction]
    wanders: bool


N, S, E, W = Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST

MOVEMENT_TYPE_PROFILES: dict[str, MovementProfile] = {
    "MOVEMENT_TYPE_FACE_DOWN": MovementProfile(frozenset({S}), False),
    "MOVEMENT_TYPE_FACE_UP": MovementProfile(frozenset({N}), False),
    "MOVEMENT_TYPE_FACE_LEFT": MovementProfile(frozenset({W}), False),
    "MOVEMENT_TYPE_FACE_RIGHT": MovementProfile(frozenset({E}), False),
    "MOVEMENT_TYPE_FACE_UP_AND_LEFT": MovementProfile(frozenset({N, W}), False),
    "MOVEMENT_TYPE_FACE_DOWN_AND_LEFT": MovementProfile(frozenset({S, W}), False),
    "MOVEMENT_TYPE_FACE_DOWN_AND_RIGHT": MovementProfile(frozenset({S, E}), False),
    "MOVEMENT_TYPE_LOOK_AROUND": MovementProfile(frozenset({N, S, E, W}), False),
    "MOVEMENT_TYPE_WALK_UP_AND_DOWN": MovementProfile(frozenset({N, S}), True),
    "MOVEMENT_TYPE_WANDER_AROUND": MovementProfile(frozenset({N, S, E, W}), True),
}


def _load_map_constants(map_id: int, path: Path) -> dict:
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


def _sight_line(
    origin: Cell,
    direction: Direction,
    sight_range: int,
    *,
    graph: "MapGraph | None",
    blockers: set[Cell],
) -> list[Cell]:
    """Cells from 1 tile away (exclusive of `origin`) through `sight_range`
    tiles away (inclusive) along `direction`, ray-marched and truncated at
    the first blocked cell -- see module docstring's
    CheckPathBetweenTrainerAndPlayer discussion. `blockers` is the set of
    other object events' spawn tiles (occlusion by another object,
    trainer_see.c's COLLISION_OBJECT_EVENT case). If `graph` is None, no
    walkability clipping happens at all (only `blockers` still applies --
    those come from decoded map data, not the graph)."""
    dx, dy = direction.delta
    cells: list[Cell] = []
    for i in range(1, sight_range + 1):
        cell = (origin[0] + dx * i, origin[1] + dy * i)
        if cell in blockers:
            break
        if graph is not None and not graph.is_walkable(cell):
            break
        cells.append(cell)
    return cells


def build_trigger_overlay(
    map_id: int,
    *,
    graph: "MapGraph | None" = None,
    map_constants_json: Path = DEFAULT_MAP_CONSTANTS_JSON,
    engine_maps_dir: Path = DEFAULT_ENGINE_MAPS_DIR,
) -> TriggerOverlay:
    """Build the trigger overlay for `map_id` from the already-emitted
    pokeemerald map data (never the RPG Maker source -- see module
    docstring). Fails loud (raises) if the map hasn't been emitted yet."""
    constants_entry = _load_map_constants(map_id, map_constants_json)
    dir_name = constants_entry["dir_name"]
    map_json = _load_emitted_map(map_id, dir_name, engine_maps_dir)

    object_events = map_json.get("object_events", [])
    coord_events = map_json.get("coord_events", [])

    occlusion_modelled = graph is not None
    if not occlusion_modelled:
        logger.warning(
            "map %s: no MapGraph supplied -- trainer sight occlusion is not "
            "modelled; every sight tile is marked POSSIBLE",
            map_id,
        )

    tiles: dict[Cell, list[TriggerRef]] = defaultdict(list)

    all_spawn_cells = {(oe["x"], oe["y"]) for oe in object_events}

    for oe in object_events:
        trainer_type = oe.get("trainer_type", _TRAINER_TYPE_NONE)
        if trainer_type == _TRAINER_TYPE_NONE:
            continue
        if trainer_type not in _KNOWN_TRAINER_TYPES:
            raise ValueError(
                f"map {map_id}: object event {oe.get('script')!r} has "
                f"unrecognized trainer_type {trainer_type!r} -- not one of "
                f"{sorted(_KNOWN_TRAINER_TYPES)}"
            )

        movement_type = oe["movement_type"]
        profile = MOVEMENT_TYPE_PROFILES.get(movement_type)
        if profile is None:
            raise ValueError(
                f"map {map_id}: trainer object event {oe.get('script')!r} uses "
                f"movement_type {movement_type!r}, which has no derived "
                "facing/wander profile in MOVEMENT_TYPE_PROFILES -- derive it "
                "from engine/src/event_object_movement.c before proceeding "
                "(see module docstring); refusing to guess."
            )

        spawn = (oe["x"], oe["y"])
        sight_range = int(oe["trainer_sight_or_berry_tree_id"])
        script = oe["script"]

        if trainer_type in _ALL_DIRECTIONS_TRAINER_TYPES:
            # trainer_see.c:651-659: SEE_ALL_DIRECTIONS/BURIED scan all four
            # cardinal directions regardless of movement type -- overrides
            # the movement profile's own facings entirely.
            facings = CARDINALS
            wanders = profile.wanders
        else:
            facings = tuple(profile.facings)
            wanders = profile.wanders

        single_facing_stationary = len(facings) == 1 and not wanders
        certainty = (
            Certainty.CERTAIN
            if (single_facing_stationary and occlusion_modelled)
            else Certainty.POSSIBLE
        )

        blockers = all_spawn_cells - {spawn}
        for direction in facings:
            line = _sight_line(
                spawn, direction, sight_range, graph=graph, blockers=blockers
            )
            for cell in line:
                tiles[cell].append(
                    TriggerRef(
                        kind=TriggerKind.TRAINER_SIGHT,
                        script=script,
                        certainty=certainty,
                        owner_xy=spawn,
                        detail=f"sight range {sight_range} facing {direction.name}",
                    )
                )

    for ce in coord_events:
        cell = (ce["x"], ce["y"])
        var = ce.get("var")
        var_value = ce.get("var_value")
        detail = f"{var}={var_value}" if var is not None else "unconditional"
        tiles[cell].append(
            TriggerRef(
                kind=TriggerKind.COORD_EVENT,
                script=ce["script"],
                certainty=Certainty.CERTAIN,
                owner_xy=None,
                detail=detail,
            )
        )

    return TriggerOverlay(map_id=map_id, tiles=dict(tiles))
