"""`beat_gen.rooms` (2026-10-02, ROM run 63): place = (map id, room), and the
continuity / region rules that run on places."""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen.continuity import thread_maps
from rpg2gba.beat_gen.interiors import interior_exit_edges, region_order_check
from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.beat_gen.rooms import PlaceWorld, RoomIndex
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.warps import WarpExit
from rpg2gba.traversal.world import WorldEdge, WorldGraph


def _two_rooms(map_id: int = 73, doors: bool = True) -> MapGraph:
    """7x3: a wall column at x=3 splits two rooms (x 0..2 and 4..6); each room's
    bottom row holds a solid door tile, (1,2) and (5,2)."""
    blocked = {(x, y): False for x in range(7) for y in range(3)}
    for y in range(3):
        blocked[(3, y)] = True
    blocked[(1, 2)] = True
    blocked[(5, 2)] = True
    exits = {}
    if doors:
        for event_id, cell in ((1, (1, 2)), (2, (5, 2))):
            exits[cell] = [WarpExit(cell=cell, event_id=event_id, dest_map=31, dest_x=0,
                                    dest_y=0, dest_facing=0)]
    return MapGraph(map_id=map_id, width=7, height=3, tileset_id=0, blocked=blocked,
                    warp_exits=exits)


def test_two_rooms_are_two_places() -> None:
    rooms = RoomIndex({73: _two_rooms()})
    assert rooms.is_multi_room(73)
    assert rooms.place_of(73, (0, 0)) == (73, 0)
    assert rooms.place_of(73, (6, 1)) == (73, 1)
    assert rooms.places_on_map(73) == ((73, 0), (73, 1))
    assert rooms.label((73, 1)) == "map073r1"


def test_solid_door_tile_takes_its_first_walkable_neighbour_room() -> None:
    rooms = RoomIndex({73: _two_rooms()})
    assert rooms.place_of(73, (1, 2)) == (73, 0)      # north (1,1) is in room 0
    assert rooms.place_of(73, (5, 2)) == (73, 1)
    assert rooms.place_of(73, (3, 1)) == (73, 1)      # wall: north (3,0) is solid, east wins


def test_wall_cell_with_no_walkable_neighbour_fails_loud() -> None:
    rooms = RoomIndex({73: _two_rooms()})
    with pytest.raises(ValueError, match="no room"):
        rooms.place_of(73, (50, 50))


def test_single_room_map_is_room_zero_and_unsuffixed() -> None:
    rooms = RoomIndex({31: _two_rooms(31, doors=False)})   # two components, no warps
    assert not rooms.is_multi_room(31)
    assert rooms.room_count(31) == 2
    assert rooms.place_of(31, (6, 1)) == (31, 0)
    assert rooms.label((31, 0)) == "map031"


def test_real_map_73_is_four_shops() -> None:
    from rpg2gba.traversal.graph import build_map_graph

    try:
        graph = build_map_graph(73)
    except Exception as exc:    # noqa: BLE001 -- decoded corpus not built here
        pytest.skip(f"map 73 not buildable: {exc}")
    rooms = RoomIndex({73: graph})
    assert rooms.is_multi_room(73)
    doors = [(5, 12), (24, 13), (44, 13), (64, 13)]
    places = [rooms.place_of(73, d) for d in doors]
    assert len(set(places)) == 4
    assert rooms.room_count(73) == 5      # four shops and one room with no door


def test_place_world_lands_edges_in_rooms() -> None:
    graphs = {73: _two_rooms(), 31: _two_rooms(31, doors=False)}
    rooms = RoomIndex(graphs)
    edges = [
        WorldEdge(src_map=31, dst_map=73, kind="warp", src_cell=(0, 0), dst_cell=(5, 2),
                  event_id=7),
        WorldEdge(src_map=73, dst_map=31, kind="warp", src_cell=(1, 2), dst_cell=(0, 0),
                  event_id=1),
    ]
    world = WorldGraph(edges=edges, names={}, map_ids=frozenset({31, 73}),
                       maps_without_info=frozenset(), infos_without_map=frozenset(),
                       variable_warp_count=0, variable_warp_maps={})
    pw = PlaceWorld(world, rooms)
    [into] = pw.edges_from((31, 0))
    assert (into.src_map, into.dst_map, into.event_id) == ((31, 0), (73, 1), 7)
    assert pw.edges_from((73, 1)) == []
    [out] = pw.edges_from((73, 0))
    assert out.dst_map == (31, 0)


def _beat(name: str, map_id: int, template: str = "generic") -> PlannedBeat:
    return PlannedBeat(name=name, template=template, map_id=map_id, rows=(f"{name}/r",),
                       group=name)


def test_thread_maps_inserts_a_transit_between_rooms_of_one_map() -> None:
    hop_out = (("M73", 5, 1, "UP", "M31"))
    hop_in = (("M31", 9, 9, "UP", "M73"))

    def route(a, b):
        if (a, b) == ((73, 1), (73, 0)):
            return (((73, 1), (31, 0), hop_out, 2), ((31, 0), (73, 0), hop_in, 7))
        raise ValueError("no route")

    beats = [_beat("a", 73), _beat("b", 73)]
    out = thread_maps(
        beats, start=(73, 1), beat_place={"a": (73, 1), "b": (73, 0)}, warp_dest={},
        warp_origin={}, nudge_source={}, route_between=route)
    assert [b.name for b in out] == ["a", "b_transit", "b"]
    assert out[1].map_id == 73
    # without rooms the old check saw "same map" and inserted nothing
    with pytest.raises(ValueError, match="no beat claims"):
        thread_maps(beats, start=(73, 1), beat_place={"a": (73, 1), "b": (73, 0)},
                    warp_dest={}, warp_origin={}, nudge_source={})


def _world(edges: list[WorldEdge], map_ids: set[int]) -> WorldGraph:
    return WorldGraph(edges=edges, names={}, map_ids=frozenset(map_ids),
                      maps_without_info=frozenset(), infos_without_map=frozenset(),
                      variable_warp_count=0, variable_warp_maps={})


def test_one_map_two_rooms_are_two_regions_and_hopping_between_them_breaks_the_stay() -> None:
    """Town (1) has doors into map 73's room 0 and room 1; each room is its own
    dead end, so entering room 0, doing a room-1 beat, then leaving breaks."""
    graphs = {73: _two_rooms(), 1: _two_rooms(1, doors=False)}
    rooms = RoomIndex(graphs)
    edges = [
        WorldEdge(src_map=1, dst_map=73, kind="warp", src_cell=(0, 0), dst_cell=(1, 2),
                  event_id=10),
        WorldEdge(src_map=73, dst_map=1, kind="warp", src_cell=(1, 2), dst_cell=(0, 0),
                  event_id=11),
        WorldEdge(src_map=1, dst_map=73, kind="warp", src_cell=(0, 0), dst_cell=(5, 2),
                  event_id=20),
        WorldEdge(src_map=73, dst_map=1, kind="warp", src_cell=(5, 2), dst_cell=(0, 0),
                  event_id=21),
        WorldEdge(src_map=1, dst_map=99, kind="connection"),
    ]
    world = PlaceWorld(_world(edges, {1, 73, 99}), rooms)
    town, room_a, room_b = (1, 0), (73, 0), (73, 1)
    group_map = {"a_in": town, "a_int": room_a, "a_out": room_a,
                 "b_in": town, "b_int": room_b, "b_out": room_b}
    group_warps = {"a_in": ((1, 10),), "a_out": ((73, 11),),
                   "b_in": ((1, 20),), "b_out": ((73, 21),)}
    kw = dict(chapter_maps=frozenset({town, room_a, room_b}), entry_map=town,
              group_map=group_map, group_warps=group_warps, label=rooms.label,
              node_map=lambda p: p[0])
    edges_out = interior_exit_edges(world, hard_and_story=[], **kw)
    assert {(e.before, e.after, e.reason) for e in edges_out} == {
        ("a_int", "a_out", "interior_exit:map001<-map073r0"),
        ("b_int", "b_out", "interior_exit:map001<-map073r1"),
    }
    check = region_order_check(world, **kw)
    assert check(["a_in", "a_int", "a_out", "b_in", "b_int", "b_out"]) == 0
    # enter room A, do a room-B beat (b_int), then leave A: one break
    assert check(["a_in", "b_int", "a_out"]) == 1
