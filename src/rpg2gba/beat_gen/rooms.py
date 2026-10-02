"""Rooms: the place the player stands in is `(map id, room)`, not a map.

2026-10-02 (ROM run 63, operator ruling "room-aware continuity + solver"):
one map can hold several disconnected rooms -- map 73 (Kevlar's shop
interiors) is four shops, each a separate connected component with its own
door to map 31. Continuity and the solver's region rules (`interiors.py`)
tracked the player at MAP granularity, so a beat in one shop followed by a
beat in another got no transit and the walker had no path. A `Place` is
`(map id, room)`; a room is a connected component of the map's walkable graph
(`MapGraph.connected_components`, union-find over `neighbors()`, so ledges and
stairs connect exactly as the walker sees them), ranked by its minimum cell.

A map is multi-room when two or more of its components each touch a warp
(each warp counts for ONE room: the cell it sits on if walkable, else the
largest component among its walkable neighbours -- so a pocket of decor behind
an exterior door does not make a town a multi-room map). Every other map is one room:
`place_of` answers `(map, 0)` for any cell on it without a lookup, so a
single-room map behaves and prints exactly as it did before rooms existed.
`PlaceWorld` is a `WorldGraph` seen through places, for `interiors.py`.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

from rpg2gba.routing.pathing import RoutePlanningError, landing_cell
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.world import WorldEdge, WorldGraph

logger = logging.getLogger(__name__)

Cell = tuple[int, int]
Place = tuple[int, int]
"""(map id, room). Room 0 is the only room of a single-room map."""

NO_ROOM = -1
"""Room of a world-edge endpoint no room touches (`PlaceWorld` only)."""

_NESW = ((0, -1), (1, 0), (0, 1), (-1, 0))


@dataclass(frozen=True)
class _MapRooms:
    room_of: Mapping[Cell, int]     # walkable cell -> room rank
    size: Mapping[int, int]         # room rank -> walkable cell count
    count: int                      # components on the map
    multi: bool                     # >= 2 components touching a warp


@dataclass(frozen=True)
class RoomIndex:
    """Rooms of every map in `graphs`, computed lazily per map."""

    graphs: Mapping[int, MapGraph]
    _cache: dict[int, _MapRooms] = field(default_factory=dict, init=False, repr=False,
                                         compare=False)

    def _rooms(self, map_id: int) -> _MapRooms:
        found = self._cache.get(map_id)
        if found is not None:
            return found
        try:
            graph = self.graphs[map_id]
        except Exception as exc:    # noqa: BLE001 -- lazy graphs raise whatever a build does
            # A map outside the chapter that no graph can be built for (not
            # staged yet): nothing walks it, so it is one room, as before rooms.
            logger.debug("map %d has no graph (%s): one room", map_id, exc)
            found = _MapRooms(room_of={}, size={}, count=1, multi=False)
            self._cache[map_id] = found
            return found
        comps = sorted(graph.connected_components(), key=min)
        room_of = {cell: rank for rank, comp in enumerate(comps) for cell in comp}
        size = {rank: len(comp) for rank, comp in enumerate(comps)}
        found = _MapRooms(room_of=room_of, size=size, count=len(comps), multi=False)
        touching = {r for wx, wy in graph.warp_exits
                    if (r := self._door_room(found, (wx, wy))) is not None}
        found = _MapRooms(room_of=room_of, size=size, count=len(comps),
                          multi=len(touching) >= 2)
        self._cache[map_id] = found
        return found

    @staticmethod
    def _door_room(info: _MapRooms, cell: Cell) -> int | None:
        """The room a cell belongs to: its own if walkable, else the largest
        room among its walkable neighbours (first in N E S W order on a tie);
        None when it has none."""
        if cell in info.room_of:
            return info.room_of[cell]
        x, y = cell
        best: int | None = None
        for dx, dy in _NESW:
            rank = info.room_of.get((x + dx, y + dy))
            if rank is not None and (best is None or info.size[rank] > info.size[best]):
                best = rank
        return best

    def is_multi_room(self, map_id: int) -> bool:
        return self._rooms(map_id).multi

    def room_count(self, map_id: int) -> int:
        """Connected components on the map (whether or not they touch a warp)."""
        return self._rooms(map_id).count

    def places_on_map(self, map_id: int) -> tuple[Place, ...]:
        info = self._rooms(map_id)
        if not info.multi:
            return ((map_id, 0),)
        return tuple((map_id, r) for r in range(info.count))

    def place_of(self, map_id: int, cell: Cell) -> Place:
        """The room of `cell`. A cell that is not walkable (a door mat, a solid
        warp tile) takes the room of its largest walkable neighbour (N E S W on a tie).
        Fails loud when a multi-room map has no room for the cell."""
        info = self._rooms(map_id)
        if not info.multi:
            return (map_id, 0)
        room = self._door_room(info, cell)
        if room is not None:
            return (map_id, room)
        raise ValueError(f"map {map_id}: cell {cell} is in no room (not walkable, no walkable "
                         f"neighbour)")

    def label(self, place: Place) -> str:
        map_id, room = place
        if self.is_multi_room(map_id):
            return f"map{map_id:03d}r{room}"
        return f"map{map_id:03d}"

    def landing_place(self, edge: WorldEdge) -> Place:
        """The place a world edge lands the player in: the room of the landing
        cell (a door arrival's destination is the solid door tile; the player
        stands one step off it, `landing_cell`). Falls back to the room of the
        destination cell itself when no landing can be told."""
        if edge.dst_cell is None or not self.is_multi_room(edge.dst_map):
            return self._cellless(edge.dst_map)
        facing = self._facing(edge)
        try:
            cell = landing_cell(self.graphs[edge.dst_map], edge.dst_cell, facing=facing)
        except RoutePlanningError:
            cell = edge.dst_cell
        return self.place_of(edge.dst_map, cell)

    def _facing(self, edge: WorldEdge) -> int:
        """The warp's own destination facing, as `__main__._route_between`
        reads it (0 when the edge is no warp or its map has no graph)."""
        if edge.src_cell is None:
            return 0
        try:
            exits = self.graphs[edge.src_map].warp_exits.get(edge.src_cell, ())
        except Exception:    # noqa: BLE001 -- no graph for the source map
            return 0
        return next((w.dest_facing for w in exits if w.event_id == edge.event_id), 0)

    def _cellless(self, map_id: int) -> Place:
        if self.is_multi_room(map_id):
            raise ValueError(f"map {map_id} is multi-room; an edge with no cell has no room")
        return (map_id, 0)


@dataclass(frozen=True)
class PlaceEdge:
    """What `interiors.py` reads off an edge, with places for the endpoints."""

    src_map: Place
    dst_map: Place
    kind: str
    event_id: int | None = None


class PlaceWorld:
    """A `WorldGraph` seen through rooms: `edges_from(place)` returns the edges
    leaving that room, each landing in the room of its arrival cell."""

    def __init__(self, world: WorldGraph, rooms: RoomIndex) -> None:
        self._world = world
        self._rooms = rooms
        self._by_map: dict[int, list[PlaceEdge]] = {}

    def _map_edges(self, map_id: int) -> list[PlaceEdge]:
        found = self._by_map.get(map_id)
        if found is not None:
            return found
        out: list[PlaceEdge] = []
        for e in self._world.edges_from(map_id):
            try:
                if e.src_cell is None:
                    if self._rooms.is_multi_room(e.src_map):
                        continue
                    src: Place = (e.src_map, 0)
                else:
                    src = self._rooms.place_of(e.src_map, e.src_cell)
                if e.dst_cell is None:
                    if self._rooms.is_multi_room(e.dst_map):
                        continue
                    dst: Place = (e.dst_map, 0)
                else:
                    dst = self._rooms.landing_place(e)
            except ValueError as exc:
                # A warp onto/from a wall cell no room touches (map 83's (6,2),
                # entered from map 150): keep the edge -- dropping it would make
                # a region look closed -- in room -1, "no room".
                logger.debug("world edge %s: %s -- placed in room %d", e, exc, NO_ROOM)
                src = (e.src_map, 0) if e.src_cell is None else self._safe(e.src_map, e.src_cell)
                dst = self._safe(e.dst_map, e.dst_cell)
            out.append(PlaceEdge(src_map=src, dst_map=dst, kind=e.kind, event_id=e.event_id))
        self._by_map[map_id] = out
        return out

    def _safe(self, map_id: int, cell: Cell | None) -> Place:
        if cell is None:
            return (map_id, NO_ROOM)
        try:
            return self._rooms.place_of(map_id, cell)
        except ValueError:
            return (map_id, NO_ROOM)

    def edges_from(self, place: Place) -> list[PlaceEdge]:
        return [e for e in self._map_edges(place[0]) if e.src_map == place]
