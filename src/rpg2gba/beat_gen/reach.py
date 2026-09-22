"""Geographic reachability over a chapter's own maps (C6 part two; A5).

The story model's "live" means narratively enabled, not walkable. The
manifest's `requires` answers "which field move opens this", but from the
hand-kept `_CHAPTER_MAP_START_CELLS`, whose starts are every in-slice warp
into a map -- including warps from LATER chapters' maps. So a region only a
later chapter can enter (CH01's north Moki Town, reached from Route 1)
reads as reachable in CH01.

This pass answers the question from the concrete chapter instead: from the
chapter's entry, over the maps its ROM stages (the chain), walking and
crossing warps, seam warps and map connections -- which cells can the
player stand on? A group none of whose sites is reachable isn't this
chapter's to walk; `later_owner` names the first successor whose added maps
make it reachable.
"""
from __future__ import annotations

import functools
from collections import deque
from collections.abc import Mapping

from rpg2gba.routing.connections import connections_between, crossing_cells, load_connections
from rpg2gba.routing.occupancy import MapOccupancy
from rpg2gba.routing.pathing import RoutePlanningError, landing_cell
from rpg2gba.traversal.graph import Cell, MapGraph
from rpg2gba.traversal.world import WorldGraph

Site = tuple[int, Cell]          # (map id, cell)
_ORTHO = ((0, -1), (0, 1), (1, 0), (-1, 0))


@functools.cache
def _connections():  # noqa: ANN202
    return load_connections()


def reachable_sites(
    entry: Site, graphs: Mapping[int, MapGraph], world: WorldGraph, maps: frozenset[int],
    occupancy: Mapping[int, MapOccupancy] | None = None,
) -> frozenset[Site]:
    """Every (map, cell) the player can stand on from `entry`, moving only
    among `maps`. Warps fire by stepping on a walkable warp tile or pressing
    into a solid one (a building's exit mat); seam warps and map
    connections cross at their shared cells. Stationary-NPC tiles
    (`occupancy`) are walls, exactly as the route solver treats them."""
    seen: set[Site] = {entry}
    queue: deque[Site] = deque([entry])
    blocked = {m: occupancy[m].blocked_cells() for m in maps} if occupancy is not None else {}

    def visit(site: Site) -> None:
        if (site not in seen and site[0] in maps and graphs[site[0]].is_walkable(site[1])
                and site[1] not in blocked.get(site[0], ())):
            seen.add(site)
            queue.append(site)

    # Seam crossings, per (from, to) map pair: exit cell -> entry cells.
    seam_moves: dict[int, dict[Cell, list[Site]]] = {}
    for m in maps:
        moves: dict[Cell, list[Site]] = {}
        for edge in world.edges_from(m):
            if edge.dst_map not in maps:
                continue
            if edge.kind == "seam_warp" and edge.src_cell is not None:
                moves.setdefault(edge.src_cell, []).append((edge.dst_map, edge.dst_cell))
            elif edge.kind == "connection":
                for conn in connections_between(_connections(), m, edge.dst_map):
                    for exit_cell, entry_cell in crossing_cells(
                            conn, from_graph=graphs[m], to_graph=graphs[edge.dst_map]):
                        moves.setdefault(exit_cell, []).append((edge.dst_map, entry_cell))
        seam_moves[m] = moves

    while queue:
        map_id, cell = queue.popleft()
        graph = graphs[map_id]
        for e in graph.neighbors(cell):
            visit((map_id, e.target))
        x, y = cell
        for tile in [cell] + [(x + dx, y + dy) for dx, dy in _ORTHO]:
            if tile != cell and graph.is_walkable(tile):
                continue          # a walkable warp tile fires when stood on
            press = (tile[0] - x, tile[1] - y) if tile != cell else None
            for exit_ in graph.warp_exits.get(tile, ()):
                if exit_.dest_map not in maps:
                    continue
                try:
                    land = landing_cell(graphs[exit_.dest_map], (exit_.dest_x, exit_.dest_y),
                                        facing=exit_.dest_facing, press=press)
                except RoutePlanningError:
                    continue      # a landing nobody can stand on leads nowhere
                visit((exit_.dest_map, land))
        for target in seam_moves[map_id].get(cell, ()):
            visit(target)
    return frozenset(seen)
