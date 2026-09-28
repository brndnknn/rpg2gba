"""Tests for `rpg2gba.beat_gen.interiors` -- dead-end interior detection and
the soft precedence edges it derives (2026-09-28 ruling, see
`investigations/warp-round-trips-and-gated-doors.md`).

`WorldGraph`/`WorldEdge` are built by hand, following `tests/
test_routing_solver.py`'s style (no `output/`/`engine/` dependency).
"""
from __future__ import annotations

from rpg2gba.beat_gen.interiors import (
    arrival_nudge_edges, interior_exit_edges, region_order_check,
)
from rpg2gba.routing.plan import PrecedenceEdge
from rpg2gba.traversal.world import WorldEdge, WorldGraph


def _world(edges: list[WorldEdge], map_ids: set[int]) -> WorldGraph:
    return WorldGraph(
        edges=edges, names={m: f"Map{m:03d}" for m in map_ids}, map_ids=frozenset(map_ids),
        maps_without_info=frozenset(), infos_without_map=frozenset(),
        variable_warp_count=0, variable_warp_maps={},
    )


def _door(town: int, house: int, in_event: int, out_event: int) -> list[WorldEdge]:
    return [
        WorldEdge(src_map=town, dst_map=house, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=in_event),
        WorldEdge(src_map=house, dst_map=town, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=out_event),
    ]


# ---------------------------------------------------------------------------
# town hub, two single-room houses
# ---------------------------------------------------------------------------


def test_two_houses_each_get_interior_before_own_exit() -> None:
    town, house_a, house_b, outside = 1, 2, 3, 99
    edges = (
        _door(town, house_a, 10, 11)
        + _door(town, house_b, 20, 21)
        # Without an exit from town that leaves the chapter entirely, "the
        # rest of the town+house_b graph" looks like a dead end *behind*
        # house_a too (nothing outside blocks it) -- a real town always has
        # a further connection (a route, a seam) that breaks the symmetry;
        # model that here so only the two genuine house interiors qualify.
        + [WorldEdge(src_map=town, dst_map=outside, kind="connection")]
    )
    world = _world(edges, {town, house_a, house_b, outside})

    group_map = {
        "a_in": town, "a_out": house_a, "a_int": house_a,
        "b_in": town, "b_out": house_b, "b_int": house_b,
    }
    group_warps = {
        "a_in": ((town, 10),), "a_out": ((house_a, 11),),
        "b_in": ((town, 20),), "b_out": ((house_b, 21),),
    }

    result = interior_exit_edges(
        world, chapter_maps=frozenset({town, house_a, house_b}), entry_map=town,
        group_map=group_map, group_warps=group_warps, hard_and_story=(),
    )

    assert PrecedenceEdge(
        before="a_int", after="a_out", reason="interior_exit:map001<-map002",
    ) in result
    assert PrecedenceEdge(
        before="b_int", after="b_out", reason="interior_exit:map001<-map003",
    ) in result
    # entrance groups (located on the parent map) never get an edge; they
    # aren't "interior" to their own house.
    assert not any(e.before in ("a_in", "b_in") for e in result)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# nested region: 2F behind 1F behind the town
# ---------------------------------------------------------------------------


def test_nested_2f_behind_1f_each_region_gets_own_edges() -> None:
    town, first_floor, second_floor = 1, 2, 4
    edges = (
        _door(town, first_floor, 10, 11)
        + _door(first_floor, second_floor, 30, 31)
    )
    world = _world(edges, {town, first_floor, second_floor})

    group_map = {
        "h_in": town, "h_out": first_floor,
        "stairs_up": first_floor, "stairs_down": second_floor,
        "up_int": second_floor,
    }
    group_warps = {
        "h_in": ((town, 10),), "h_out": ((first_floor, 11),),
        "stairs_up": ((first_floor, 30),), "stairs_down": ((second_floor, 31),),
    }

    result = interior_exit_edges(
        world, chapter_maps=frozenset({town, first_floor, second_floor}), entry_map=town,
        group_map=group_map, group_warps=group_warps, hard_and_story=(),
    )

    # region behind town (via 1F): {1F, 2F} -- everything in it precedes h_out.
    for before in ("stairs_up", "stairs_down", "up_int"):
        assert PrecedenceEdge(
            before=before, after="h_out", reason="interior_exit:map001<-map002",
        ) in result

    # region behind 1F (via 2F): {2F} -- up_int precedes stairs_down.
    assert PrecedenceEdge(
        before="up_int", after="stairs_down", reason="interior_exit:map002<-map004",
    ) in result


# ---------------------------------------------------------------------------
# two-door building: still one dead-end region
# ---------------------------------------------------------------------------


def test_two_door_building_is_one_region_both_exits_after_interior() -> None:
    town, house = 1, 2
    edges = _door(town, house, 10, 11) + _door(town, house, 20, 21)
    world = _world(edges, {town, house})

    group_map = {
        "in1": town, "in2": town, "out1": house, "out2": house, "h_int": house,
    }
    group_warps = {
        "in1": ((town, 10),), "in2": ((town, 20),),
        "out1": ((house, 11),), "out2": ((house, 21),),
    }

    result = interior_exit_edges(
        world, chapter_maps=frozenset({town, house}), entry_map=town,
        group_map=group_map, group_warps=group_warps, hard_and_story=(),
    )

    assert PrecedenceEdge(
        before="h_int", after="out1", reason="interior_exit:map001<-map002",
    ) in result
    assert PrecedenceEdge(
        before="h_int", after="out2", reason="interior_exit:map001<-map002",
    ) in result
    assert len(result) == 2


# ---------------------------------------------------------------------------
# through map: no dead end, no edges
# ---------------------------------------------------------------------------


def test_through_map_gets_no_edges() -> None:
    town, through = 1, 5
    outside = 6  # deliberately NOT a chapter map -- through leads elsewhere
    edges = _door(town, through, 10, 11) + [
        WorldEdge(src_map=through, dst_map=outside, kind="warp",
                  src_cell=(1, 0), dst_cell=(0, 0), event_id=30),
    ]
    world = _world(edges, {town, through, outside})

    group_map = {"t_in": town, "t_out": through}
    group_warps = {"t_in": ((town, 10),), "t_out": ((through, 11),)}

    result = interior_exit_edges(
        world, chapter_maps=frozenset({town, through}), entry_map=town,
        group_map=group_map, group_warps=group_warps, hard_and_story=(),
    )

    assert result == ()


# ---------------------------------------------------------------------------
# later-visit exclusion
# ---------------------------------------------------------------------------


def test_later_visit_interior_group_gets_no_edge() -> None:
    town, house, elsewhere = 1, 2, 7
    edges = _door(town, house, 10, 11)
    world = _world(edges, {town, house, elsewhere})

    group_map = {
        "h_in": town, "h_out": house, "h_int": house,
        "scene": house, "outside_thing": elsewhere,
    }
    group_warps = {"h_in": ((town, 10),), "h_out": ((house, 11),)}

    # `scene`'s only precondition is a group OUTSIDE the region that is not
    # itself an ancestor of the region's entry group -- `scene` can't fire on
    # the first visit, so it must not be forced before `h_out`.
    hard_and_story = (
        PrecedenceEdge(before="outside_thing", after="scene", reason="story:x"),
    )

    result = interior_exit_edges(
        world, chapter_maps=frozenset({town, house, elsewhere}), entry_map=town,
        group_map=group_map, group_warps=group_warps, hard_and_story=hard_and_story,
    )

    assert not any(e.before == "scene" for e in result)
    assert PrecedenceEdge(
        before="h_int", after="h_out", reason="interior_exit:map001<-map002",
    ) in result


# ---------------------------------------------------------------------------
# entry map inside a region
# ---------------------------------------------------------------------------


def test_entry_map_inside_region_does_not_change_edges() -> None:
    town, house = 1, 2
    edges = _door(town, house, 10, 11)
    world = _world(edges, {town, house})

    group_map = {"h_in": town, "h_out": house, "h_int": house}
    group_warps = {"h_in": ((town, 10),), "h_out": ((house, 11),)}

    baseline = interior_exit_edges(
        world, chapter_maps=frozenset({town, house}), entry_map=town,
        group_map=group_map, group_warps=group_warps, hard_and_story=(),
    )
    with_entry_inside = interior_exit_edges(
        world, chapter_maps=frozenset({town, house}), entry_map=house,
        group_map=group_map, group_warps=group_warps, hard_and_story=(),
    )

    assert baseline == with_entry_inside
    assert PrecedenceEdge(
        before="h_int", after="h_out", reason="interior_exit:map001<-map002",
    ) in baseline


# ---------------------------------------------------------------------------
# arrival_nudge_edges
# ---------------------------------------------------------------------------


def test_arrival_nudge_edges_orders_warp_before_nudge() -> None:
    nudge_groups = {"n1": (2, 1)}  # nudge lives on map 2, must arrive from map 1
    warp_groups = {
        "w_in": (1, 2),   # origin 1 -> dest 2: matches
        "w_other": (3, 2),  # wrong origin: no match
    }

    result = arrival_nudge_edges(nudge_groups=nudge_groups, warp_groups=warp_groups)

    assert result == (
        PrecedenceEdge(before="w_in", after="n1", reason="arrival_nudge:map001->map002"),
    )


# ---------------------------------------------------------------------------
# region_order_check
# ---------------------------------------------------------------------------


def test_region_order_check_town_house_order_ok_and_rejected() -> None:
    town, house, outside = 1, 2, 99
    edges = _door(town, house, 10, 11) + [
        WorldEdge(src_map=town, dst_map=outside, kind="connection")
    ]
    world = _world(edges, {town, house, outside})

    group_map = {"enter": town, "interior": house, "exit": house, "town_beat": town}
    group_warps = {"enter": ((town, 10),), "exit": ((house, 11),)}

    check = region_order_check(
        world, chapter_maps=frozenset({town, house}), entry_map=town,
        group_map=group_map, group_warps=group_warps,
    )

    assert check(["enter", "interior", "exit", "town_beat"]) == 0
    assert check(["enter", "town_beat", "interior", "exit"]) == 1


def test_region_order_check_entry_map_inside_region() -> None:
    town, house, outside = 1, 2, 99
    edges = _door(town, house, 10, 11) + [
        WorldEdge(src_map=town, dst_map=outside, kind="connection")
    ]
    world = _world(edges, {town, house, outside})

    group_map = {"enter": town, "town_beat": town, "exit": house}
    group_warps = {"enter": ((town, 10),), "exit": ((house, 11),)}

    check = region_order_check(
        world, chapter_maps=frozenset({town, house}), entry_map=house,
        group_map=group_map, group_warps=group_warps,
    )

    # entry_map (house) sits inside the region -- a town_beat before the
    # exit warp fires is rejected...
    assert check(["town_beat", "exit"]) == 1
    # ...but once the exit has fired, the region is free.
    assert check(["exit", "town_beat"]) == 0


def test_region_order_check_nested_2f_1f() -> None:
    town, first_floor, second_floor = 1, 2, 4
    edges = _door(town, first_floor, 10, 11) + _door(first_floor, second_floor, 30, 31)
    world = _world(edges, {town, first_floor, second_floor})

    group_map = {
        "h_in": town, "h_out": first_floor,
        "stairs_up": first_floor, "stairs_down": second_floor,
        "up_int": second_floor, "onef_thing": first_floor,
    }
    group_warps = {
        "h_in": ((town, 10),), "h_out": ((first_floor, 11),),
        "stairs_up": ((first_floor, 30),), "stairs_down": ((second_floor, 31),),
    }

    check = region_order_check(
        world, chapter_maps=frozenset({town, first_floor, second_floor}), entry_map=town,
        group_map=group_map, group_warps=group_warps,
    )

    # a 1F beat while still up on 2F (before stairs_down) is rejected...
    assert check(["h_in", "stairs_up", "onef_thing", "stairs_down"]) == 1
    # ...but is fine once the 2F exit (stairs_down) has fired.
    assert check(["h_in", "stairs_up", "stairs_down", "onef_thing", "h_out"]) == 0


def test_region_order_check_revisit_after_leaving_not_reheld() -> None:
    town, house, outside = 1, 2, 99
    edges = _door(town, house, 10, 11) + [
        WorldEdge(src_map=town, dst_map=outside, kind="connection")
    ]
    world = _world(edges, {town, house, outside})

    group_map = {
        "enter": town, "interior": house, "exit": house,
        "town_beat": town, "interior2": house,
    }
    group_warps = {"enter": ((town, 10),), "exit": ((house, 11),)}

    check = region_order_check(
        world, chapter_maps=frozenset({town, house}), entry_map=town,
        group_map=group_map, group_warps=group_warps,
    )

    # once the region has been entered and exited, a later group sitting on
    # the same region's map is NOT re-held -- the region is free.
    assert check(["enter", "interior", "exit", "town_beat", "interior2"]) == 0


def test_region_order_check_no_exit_group_never_held() -> None:
    town, house, outside = 1, 2, 99
    edges = _door(town, house, 10, 11) + [
        WorldEdge(src_map=town, dst_map=outside, kind="connection")
    ]
    world = _world(edges, {town, house, outside})

    group_map = {"enter": town, "interior": house, "town_beat": town}
    # no group owns the house -> town warp, so exit_groups is empty and this
    # region is never held.
    group_warps = {"enter": ((town, 10),)}

    check = region_order_check(
        world, chapter_maps=frozenset({town, house}), entry_map=town,
        group_map=group_map, group_warps=group_warps,
    )

    assert check(["enter", "town_beat", "interior"]) == 0
