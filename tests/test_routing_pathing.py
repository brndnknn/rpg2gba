"""Tests for `rpg2gba.routing.pathing`."""
from __future__ import annotations

import pytest

from rpg2gba.tileset_converter.stairs import StairSide
from rpg2gba.traversal.direction import Direction
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.triggers import Certainty, TriggerKind, TriggerOverlay, TriggerRef
from rpg2gba.traversal.world import WorldEdge, WorldGraph

from rpg2gba.routing.occupancy import (
    MapOccupancy,
    OccupancyError,
    OccupiedTile,
    build_occupancy,
)
from rpg2gba.routing.pathing import RoutePlanningError, path_avoiding, plan_segment


def _open_grid(width: int, height: int) -> dict[tuple[int, int], bool]:
    return {(x, y): False for x in range(width) for y in range(height)}


def _walled_grid(
    width: int, height: int, walls: set[tuple[int, int]],
) -> dict[tuple[int, int], bool]:
    return {(x, y): (x, y) in walls for x in range(width) for y in range(height)}


def _coord_ref(script: str, certainty: Certainty = Certainty.CERTAIN) -> TriggerRef:
    return TriggerRef(
        kind=TriggerKind.COORD_EVENT, script=script, certainty=certainty,
        owner_xy=None, detail="unconditional",
    )


def _empty_overlay(map_id: int) -> TriggerOverlay:
    return TriggerOverlay(map_id=map_id, tiles={})


def _world(edges: list[WorldEdge]) -> WorldGraph:
    map_ids = frozenset({e.src_map for e in edges} | {e.dst_map for e in edges})
    return WorldGraph(
        edges=edges,
        names={m: f"Map{m:03d}" for m in map_ids},
        map_ids=map_ids,
        maps_without_info=frozenset(),
        infos_without_map=frozenset(),
        variable_warp_count=0,
        variable_warp_maps={},
    )


# ---------------------------------------------------------------------------
# path_avoiding
# ---------------------------------------------------------------------------


def test_path_avoiding_detours_around_an_avoided_cell():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    avoid = frozenset({(1, 1)})

    path = path_avoiding(graph, (0, 1), (2, 1), avoid)

    assert path is not None
    assert (1, 1) not in path
    assert path[0] == (0, 1)
    assert path[-1] == (2, 1)
    assert len(path) > 3  # detour is longer than the direct 3-cell route


def test_path_avoiding_permits_start_and_goal_even_if_in_avoid_set():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    avoid = frozenset({(0, 0), (2, 2)})

    path = path_avoiding(graph, (0, 0), (2, 2), avoid)

    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (2, 2)


def test_path_avoiding_raises_when_start_not_walkable():
    walls = {(0, 0)}
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    with pytest.raises(ValueError, match="not walkable"):
        path_avoiding(graph, (0, 0), (2, 2), frozenset())


def test_path_avoiding_returns_none_when_truly_unreachable():
    walls = {(x, 1) for x in range(3)}
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    assert path_avoiding(graph, (0, 0), (0, 2), frozenset()) is None


def test_path_avoiding_honors_stair_diagonal_edge():
    # A single stair cell at (1,1), RIGHT side (NW/SE axis). Pressing EAST
    # from the stair lands SE at (2,2). Wall off the ordinary N/S neighbours
    # of the stair so the only way to (2,2) is through the diagonal.
    walls = {(1, 0), (1, 2)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0,
        blocked=_walled_grid(3, 3, walls),
        stair_sides={(1, 1): StairSide.RIGHT},
    )
    path = path_avoiding(graph, (0, 1), (2, 2), frozenset())
    # `graph.neighbors()` presents the stair as a single displacement edge
    # straight from the approach cell to the landing cell -- the stair cell
    # itself never appears as a distinct step (see graph.py's module
    # docstring on why this is a displacement, not an 8-neighbour edge).
    assert path == [(0, 1), (2, 2)]


def test_path_avoiding_honors_ledge_jump_edge():
    # A ledge at (1,1) facing SOUTH: approach from (1,0), jump lands at (1,2).
    # No other route exists (side columns walled).
    walls = {(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)}
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0,
        blocked=_walled_grid(3, 3, walls),
        ledge_directions={(1, 1): Direction.SOUTH},
    )
    path = path_avoiding(graph, (1, 0), (1, 2), frozenset())
    assert path == [(1, 0), (1, 2)]


# ---------------------------------------------------------------------------
# plan_segment -- same map
# ---------------------------------------------------------------------------


def test_plan_segment_same_map_no_crossings_when_avoid_route_exists():
    # (1, 1) carries a script foreign to this chapter's destination_scripts,
    # so it lands in the avoid set -- but an open grid has a detour, so the
    # segment succeeds with no crossings at all.
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    overlay = TriggerOverlay(
        map_id=1, tiles={(1, 1): [_coord_ref("map099/someone_elses_event")]},
    )
    result = plan_segment(
        1, (0, 1), 1, (2, 1),
        graphs={1: graph}, overlays={1: overlay},
        destination_scripts=frozenset({"map001/ev001"}),
    )
    assert len(result.legs) == 1
    assert result.legs[0].map_id == 1
    assert (1, 1) not in result.legs[0].tiles
    assert result.crossings == ()
    assert result.tile_count == len(result.legs[0].tiles) - 1


def test_plan_segment_same_map_permits_own_script_tile_directly():
    # Same trigger tile, but its script IS one of this chapter's own
    # destination scripts -- `foreign_tiles` excludes it, so it's not
    # avoided at all and the direct route through it is fine.
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    overlay = TriggerOverlay(
        map_id=1, tiles={(1, 1): [_coord_ref("map001/ev001")]},
    )
    result = plan_segment(
        1, (0, 1), 1, (2, 1),
        graphs={1: graph}, overlays={1: overlay},
        destination_scripts=frozenset({"map001/ev001"}),
    )
    assert result.legs[0].tiles == ((0, 1), (1, 1), (2, 1))
    assert result.crossings == ()


def test_plan_segment_fallback_records_crossing_when_only_route_is_foreign():
    # Single-file corridor: (0,1)-(1,1)-(2,1). The middle cell is a foreign
    # trigger tile, and it's the only path through.
    walls = {(0, 0), (1, 0), (2, 0), (0, 2), (1, 2), (2, 2)}
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    overlay = TriggerOverlay(
        map_id=1,
        tiles={(1, 1): [_coord_ref("map099/ev005", Certainty.CERTAIN)]},
    )
    result = plan_segment(
        1, (0, 1), 1, (2, 1),
        graphs={1: graph}, overlays={1: overlay},
        destination_scripts=frozenset({"map001/ev_mine"}),  # doesn't match the foreign script
    )
    assert len(result.legs) == 1
    assert result.legs[0].tiles == ((0, 1), (1, 1), (2, 1))
    assert len(result.crossings) == 1
    crossing = result.crossings[0]
    assert crossing.map_id == 1
    assert crossing.cell == (1, 1)
    assert crossing.script == "map099/ev005"
    assert crossing.certainty == "certain"


def test_plan_segment_raises_when_goal_truly_unreachable():
    walls = {(x, 1) for x in range(3)}
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    overlay = _empty_overlay(1)
    with pytest.raises(RoutePlanningError, match="unreachable"):
        plan_segment(
            1, (0, 0), 1, (0, 2),
            graphs={1: graph}, overlays={1: overlay},
            destination_scripts=frozenset(),
        )


# ---------------------------------------------------------------------------
# plan_segment -- cross map
# ---------------------------------------------------------------------------


def test_plan_segment_missing_world_raises():
    graph1 = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    with pytest.raises(RoutePlanningError, match="WorldGraph"):
        plan_segment(
            1, (0, 0), 2, (2, 2),
            graphs={1: graph1, 2: graph2},
            overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
            destination_scripts=frozenset(),
            world=None,
        )


def test_plan_segment_warp_stitch_produces_two_legs_with_exit_warp():
    graph1 = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="warp", src_cell=(2, 2), dst_cell=(0, 0), event_id=7),
    ])

    result = plan_segment(
        1, (0, 0), 2, (2, 2),
        graphs={1: graph1, 2: graph2},
        overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
        destination_scripts=frozenset(),
        world=world,
    )

    assert len(result.legs) == 2
    first, second = result.legs
    assert first.map_id == 1
    assert first.tiles[0] == (0, 0)
    assert first.tiles[-1] == (2, 2)
    assert first.exit_warp is not None
    assert first.exit_warp.event_id == 7
    assert first.exit_warp.dest_map == 2
    assert first.exit_warp.dest_cell == (0, 0)

    assert second.map_id == 2
    assert second.tiles[0] == (0, 0)
    assert second.tiles[-1] == (2, 2)
    assert second.exit_warp is None


def _split_town(start: int, hub: int, door_piece: int, interior: int):
    """A town cut into three pieces (start -> hub -> door_piece) whose two doors
    lead into two rooms of one interior that don't connect inside it (x=2 is a
    wall). The goal room's door is on `door_piece`, two seams from `start`."""
    graphs = {m: MapGraph(map_id=m, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
              for m in (start, hub, door_piece)}
    graphs[interior] = MapGraph(map_id=interior, width=5, height=3, tileset_id=0,
                                blocked=_walled_grid(5, 3, {(2, 0), (2, 1), (2, 2)}))
    world = _world([
        WorldEdge(src_map=start, dst_map=interior, kind="warp", src_cell=(2, 0),
                  dst_cell=(0, 1), event_id=1),
        WorldEdge(src_map=start, dst_map=hub, kind="warp", src_cell=(2, 2),
                  dst_cell=(0, 0), event_id=2),
        WorldEdge(src_map=hub, dst_map=door_piece, kind="warp", src_cell=(2, 2),
                  dst_cell=(0, 0), event_id=3),
        WorldEdge(src_map=door_piece, dst_map=interior, kind="warp", src_cell=(2, 2),
                  dst_cell=(4, 1), event_id=4),
    ])
    overlays = {m: _empty_overlay(m) for m in graphs}
    return graphs, overlays, world


def test_plan_segment_detour_treats_split_pieces_as_one_map():
    from rpg2gba.map_split.ids import piece_uid

    start, hub, door = piece_uid(40, 3), piece_uid(40, 0), piece_uid(40, 1)
    graphs, overlays, world = _split_town(start, hub, door, 46)

    result = plan_segment(start, (0, 0), 46, (4, 2), graphs=graphs, overlays=overlays,
                          destination_scripts=frozenset(), world=world)

    assert [leg.map_id for leg in result.legs] == [start, hub, door, 46]
    assert result.legs[-1].tiles[-1] == (4, 2)


def test_plan_segment_detour_unchanged_for_unsplit_maps():
    # Same topology on ordinary maps: the hub has no warp into the goal, so
    # the bounded detour still never visits it.
    graphs, overlays, world = _split_town(1, 2, 3, 46)

    with pytest.raises(RoutePlanningError):
        plan_segment(1, (0, 0), 46, (4, 2), graphs=graphs, overlays=overlays,
                     destination_scripts=frozenset(), world=world)


def test_plan_segment_connection_hop_raises():
    graph1 = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    graph2 = MapGraph(map_id=2, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    world = _world([
        WorldEdge(src_map=1, dst_map=2, kind="connection", src_cell=None, dst_cell=None),
    ])

    with pytest.raises(RoutePlanningError, match="connection"):
        plan_segment(
            1, (0, 0), 2, (2, 2),
            graphs={1: graph1, 2: graph2},
            overlays={1: _empty_overlay(1), 2: _empty_overlay(2)},
            destination_scripts=frozenset(),
            world=world,
        )


# ---------------------------------------------------------------------------
# NPC occupancy -- hard block, distinct from the soft avoid-set
# ---------------------------------------------------------------------------


def _npc(cell: tuple[int, int], script: str = "map001/npc") -> OccupiedTile:
    return OccupiedTile(cell=cell, script=script, movement_type="MOVEMENT_TYPE_FACE_DOWN")


def test_path_avoiding_routes_around_a_blocked_cell():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))

    path = path_avoiding(graph, (0, 1), (2, 1), frozenset(), blocked=frozenset({(1, 1)}))

    assert path is not None
    assert (1, 1) not in path
    assert path[0] == (0, 1)
    assert path[-1] == (2, 1)


def test_plan_segment_blocked_still_honored_on_fallback_path():
    """Two equal-length routes from start to goal, both single-file: one
    (through (0,1)) is occupied by a stationary NPC, the other (through
    (2,1)) crosses a foreign trigger. Avoiding BOTH the trigger and the NPC
    at once is impossible (each route hits one or the other), so the
    preferred attempt fails and `_path_on_map` falls back -- and the
    fallback must still refuse to walk through the NPC, even though nothing
    stops it from crossing the trigger. This is the core regression: before
    `blocked` existed, the fallback ignored occupancy entirely.
    """
    walls = {(1, 1)}  # wall off the middle row's center cell -- no direct
    # shortcut between the two vertical corridors except via the top/bottom
    # connecting rows.
    graph = MapGraph(
        map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls),
    )
    overlay = TriggerOverlay(
        map_id=1, tiles={(2, 1): [_coord_ref("map099/ev_someone_else")]},
    )
    occupancy = MapOccupancy(map_id=1, tiles=(_npc((0, 1), "map001/ev_stationary"),))

    result = plan_segment(
        1, (1, 0), 1, (1, 2),
        graphs={1: graph}, overlays={1: overlay},
        destination_scripts=frozenset(),
        occupancy={1: occupancy},
    )

    tiles = result.legs[0].tiles
    assert (0, 1) not in tiles  # never walks through the NPC
    assert (2, 1) in tiles  # only remaining route crosses the trigger tile
    assert len(result.crossings) == 1
    assert result.crossings[0].cell == (2, 1)


def test_plan_segment_raises_when_goal_is_a_blocked_npc_tile():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    overlay = _empty_overlay(1)
    occupancy = MapOccupancy(map_id=1, tiles=(_npc((2, 1), "map001/ev005"),))

    with pytest.raises(RoutePlanningError, match="map001/ev005"):
        plan_segment(
            1, (0, 1), 1, (2, 1),
            graphs={1: graph}, overlays={1: overlay},
            destination_scripts=frozenset(),
            occupancy={1: occupancy},
        )


def test_plan_segment_raises_when_start_is_a_blocked_npc_tile():
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    overlay = _empty_overlay(1)
    occupancy = MapOccupancy(map_id=1, tiles=(_npc((0, 1), "map001/ev004"),))

    with pytest.raises(RoutePlanningError, match="map001/ev004"):
        plan_segment(
            1, (0, 1), 1, (2, 1),
            graphs={1: graph}, overlays={1: overlay},
            destination_scripts=frozenset(),
            occupancy={1: occupancy},
        )


def test_plan_segment_raises_when_only_route_is_through_a_blocked_npc_tile():
    # Single-file corridor, no foreign trigger at all -- the NPC sits on the
    # only possible route, so this is genuinely unroutable, distinct from a
    # segment that's merely trigger-blocked.
    walls = {(0, 0), (1, 0), (2, 0), (0, 2), (1, 2), (2, 2)}
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_walled_grid(3, 3, walls))
    overlay = _empty_overlay(1)
    occupancy = MapOccupancy(map_id=1, tiles=(_npc((1, 1), "map001/ev009"),))

    with pytest.raises(RoutePlanningError, match="blocked by stationary-NPC"):
        plan_segment(
            1, (0, 1), 1, (2, 1),
            graphs={1: graph}, overlays={1: overlay},
            destination_scripts=frozenset(),
            occupancy={1: occupancy},
        )


def test_plan_segment_absent_occupancy_reproduces_prior_behavior():
    # No `occupancy=` argument at all -- must behave exactly as before this
    # feature existed.
    graph = MapGraph(map_id=1, width=3, height=3, tileset_id=0, blocked=_open_grid(3, 3))
    overlay = TriggerOverlay(
        map_id=1, tiles={(1, 1): [_coord_ref("map099/someone_elses_event")]},
    )
    result = plan_segment(
        1, (0, 1), 1, (2, 1),
        graphs={1: graph}, overlays={1: overlay},
        destination_scripts=frozenset({"map001/ev001"}),
    )
    assert (1, 1) not in result.legs[0].tiles
    assert result.crossings == ()


# ---------------------------------------------------------------------------
# occupancy.build_occupancy -- movement-type classification
# ---------------------------------------------------------------------------


def _write_occupancy_fixture(tmp_path, object_events: list[dict]) -> tuple:
    import json

    constants_json = tmp_path / "map_constants.json"
    constants_json.write_text(json.dumps({"1": {"dir_name": "TestMap"}}), encoding="utf-8")

    maps_dir = tmp_path / "maps"
    (maps_dir / "TestMap").mkdir(parents=True)
    (maps_dir / "TestMap" / "map.json").write_text(
        json.dumps({"object_events": object_events}), encoding="utf-8",
    )
    return constants_json, maps_dir


def test_build_occupancy_blocks_stationary_and_ignores_mobile(tmp_path):
    constants_json, maps_dir = _write_occupancy_fixture(tmp_path, [
        {"x": 5, "y": 5, "movement_type": "MOVEMENT_TYPE_FACE_DOWN", "script": "ev_stationary"},
        {"x": 6, "y": 6, "movement_type": "MOVEMENT_TYPE_WANDER_AROUND", "script": "ev_mobile"},
    ])

    occupancy = build_occupancy(1, map_constants_json=constants_json, engine_maps_dir=maps_dir)

    assert occupancy.blocked_cells() == frozenset({(5, 5)})
    assert occupancy.at((5, 5)).script == "ev_stationary"
    assert occupancy.at((6, 6)) is None


def test_build_occupancy_raises_on_unrecognized_movement_type(tmp_path):
    constants_json, maps_dir = _write_occupancy_fixture(tmp_path, [
        {
            "x": 8, "y": 7,
            "movement_type": "MOVEMENT_TYPE_NOT_A_REAL_TYPE",
            "script": "ev_unknown",
        },
    ])

    with pytest.raises(OccupancyError, match="MOVEMENT_TYPE_NOT_A_REAL_TYPE"):
        build_occupancy(1, map_constants_json=constants_json, engine_maps_dir=maps_dir)


def test_build_occupancy_blocks_berry_tree(tmp_path):
    """A berry tree occupies its tile at every growth stage.

    CH03's map 31 carries the corpus's first one ('BerryTreeScript' at
    (32,5)), which fails-loud'd the CH03/CH04 route solve until it was
    classified. It is stationary despite its BERRYTREEFUNC_MOVE state: the
    only movement action `MovementType_BerryTreeGrowth` issues is
    `MOVEMENT_ACTION_START_ANIM_IN_DIRECTION`, an animation rather than a
    step (`engine/src/event_object_movement.c:4491`).
    """
    constants_json, maps_dir = _write_occupancy_fixture(tmp_path, [
        {
            "x": 32, "y": 5,
            "movement_type": "MOVEMENT_TYPE_BERRY_TREE_GROWTH",
            "script": "BerryTreeScript",
        },
    ])

    occupancy = build_occupancy(1, map_constants_json=constants_json, engine_maps_dir=maps_dir)

    assert occupancy.blocked_cells() == frozenset({(32, 5)})
    assert occupancy.at((32, 5)).script == "BerryTreeScript"


def test_build_occupancy_leaves_custom_route_patrols_passable(tmp_path):
    """Operator ruling 2026-09-04: a patrolling NPC stays passable offline.

    Map037 ev005 is the live case -- a custom route that paces
    DOWN,DOWN,UP,UP over (8,7),(8,8),(8,9). Its footprint is derivable from
    the Uranium move_route, and we deliberately do not block it; the runtime
    walker re-plans around live object tiles instead.
    """
    constants_json, maps_dir = _write_occupancy_fixture(tmp_path, [
        {
            "x": 8, "y": 7,
            "movement_type": "MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE",
            "script": "Map037_EV005_Dispatch",
        },
    ])

    occupancy = build_occupancy(1, map_constants_json=constants_json, engine_maps_dir=maps_dir)

    assert occupancy.blocked_cells() == frozenset()
    assert occupancy.at((8, 7)) is None
