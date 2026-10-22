"""`beat_gen.continuity.thread_maps`'s transit-beat insertion (C6 part two),
exercised with a fake `route_between`."""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen.continuity import thread_maps as _thread_maps
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs


def _beat(name: str, map_id: int, template: str = "generic") -> PlannedBeat:
    return PlannedBeat(name=name, template=template, map_id=map_id, rows=(f"{name}/r",),
                       group=name)


def _thread(beats, *, start_map, warp_dest, nudge_source, route_between):
    """`thread_maps` over single-room maps: map m is the place `(m, 0)`."""
    wrapped = None
    if route_between is not None:
        def wrapped(a, b):
            return tuple(((s, 0), (d, 0), hop, ev)
                         for s, d, hop, ev in route_between(a[0], b[0]))
    return _thread_maps(
        beats, start=(start_map, 0), beat_place={b.name: (b.map_id, 0) for b in beats},
        warp_dest={k: (v, 0) for k, v in warp_dest.items()}, warp_origin={},
        nudge_source={k: v if isinstance(v, tuple) else (v, None)
                      for k, v in nudge_source.items()}, route_between=wrapped)


def _route_between_factory(table):
    """table: {(from, to): route steps} -> a `route_between` that raises
    ValueError for any pair not in the table. Each route step is
    `continuity.RouteStep` (src map id, dst map id, hop, event id) --
    the event id (added 2026-09-28 for the gated-door guard) is a dummy 0
    in these tests since none of them set `gated_doors=`."""
    def fn(a, b):
        if (a, b) in table:
            return table[(a, b)]
        raise ValueError(f"no route {a}->{b}")
    return fn


def test_non_warp_beat_on_another_map_gets_a_transit_inserted_before_it():
    hops = ((2, 1, ("warp", 2, 1, "L", "R"), 0),)
    route_between = _route_between_factory({(2, 1): hops})

    out = _thread(
        [_beat("a", 1)], start_map=2, warp_dest={}, nudge_source={},
        route_between=route_between,
    )

    assert [b.name for b in out] == ["a_transit", "a"]
    transit = out[0]
    assert transit.template == "transit"
    assert transit.group == "a"
    assert transit.rows == ()
    assert dict(transit.kwargs)["hops"] == (hops[0][2],)


def test_without_route_between_the_same_situation_raises_legacy_error():
    with pytest.raises(ValueError, match="no beat claims"):
        _thread(
            [_beat("a", 1)], start_map=2, warp_dest={}, nudge_source={},
            route_between=None,
        )


def test_arrival_nudge_not_right_after_its_crossing_gets_a_transit_via_its_source_map():
    # Player is on map 1, but the nudge beat's source is map 5 -- so the
    # transit must be routed (cur, source) then (source, nudge map), i.e.
    # (1, 5) then (5, 1), not a direct (1, 1) no-op.
    hop_out = ((1, 5, ("warp", 1, 5, "L", "R"), 0),)
    hop_back = ((5, 1, ("warp", 5, 1, "R", "L"), 0),)
    route_between = _route_between_factory({(1, 5): hop_out, (5, 1): hop_back})

    beats = [_beat("a", 1), _beat("n", 1, "arrival_nudge")]
    out = _thread(
        beats, start_map=1, warp_dest={}, nudge_source={"n": 5},
        route_between=route_between,
    )

    assert [b.name for b in out] == ["a", "n_transit", "n"]
    transit = out[1]
    assert transit.template == "transit"
    assert transit.group == "n"
    assert transit.rows == ()
    assert dict(transit.kwargs)["hops"] == (hop_out[0][2], hop_back[0][2])


def test_route_between_raising_for_every_target_raises_no_way():
    route_between = _route_between_factory({})  # every lookup raises

    with pytest.raises(ValueError, match="no way"):
        _thread(
            [_beat("a", 5)], start_map=1, warp_dest={}, nudge_source={},
            route_between=route_between,
        )


# -- which transfers a transit hop may cross ---------------------------------

def _page(trigger: int, *codes: int) -> dict:
    return {"trigger": trigger, "list": [{"code": c, "parameters": []} for c in codes]}


def test_stepped_transfers_keeps_touch_pages_and_drops_scripted_scenes(tmp_path):
    import json

    from rpg2gba.beat_gen.__main__ import _stepped_transfers

    maps = tmp_path / "maps"
    maps.mkdir()
    events = [
        {"id": 1, "pages": [_page(1, 201)]},                 # stairs: player touch
        {"id": 2, "pages": [_page(1, 101), _page(1, 201)]},  # gated door: a touch page transfers
        {"id": 3, "pages": [_page(2, 201)]},                 # event touch
        {"id": 4, "pages": [_page(0, 123, 201)]},            # A-to-read cutscene (the Letter)
        {"id": 5, "pages": [_page(3, 201)]},                 # autorun scene
        {"id": 6, "pages": [_page(1, 101)]},                 # touch, no transfer
    ]
    (maps / "Map049.json").write_text(json.dumps({"events": events}), encoding="utf-8")

    assert _stepped_transfers(frozenset({49}), tmp_path) == frozenset(
        {(49, 1), (49, 2), (49, 3)})


def test_stepped_transfers_real_map049_excludes_the_letter():
    """The 2026-09-27 ROM run: CH01's 1F->2F transit pressed DOWN into the
    Letter (event 21, action-triggered, switch-gated) instead of the stairs
    (event 3), and never left 1F."""
    from rpg2gba.beat_gen.__main__ import BUILD_DIR, _stepped_transfers

    if not (BUILD_DIR / "maps" / "Map049.json").exists():
        pytest.skip("decoded maps not built")
    stepped = _stepped_transfers(frozenset({49}), BUILD_DIR)
    assert (49, 3) in stepped
    assert (49, 21) not in stepped


def test_warp_presses_reads_each_warp_beats_side():
    from rpg2gba.beat_gen.__main__ import _warp_presses

    beats = [
        PlannedBeat(name="w", template="warp", map_id=48, rows=("map048/ev002/p0",), group="w",
                    kwargs=make_kwargs(event_id=2, direction="LEFT", map_id=48)),
        _beat("g", 48),
    ]
    assert _warp_presses(beats) == {(48, 2): "LEFT"}


def test_arrival_nudge_transit_leaves_by_its_own_source_door():
    # 2026-10-02: map 5 is two rooms, each with a door to map 1 (events 2 and
    # 4). A nudge that needs event 4's arrival routes into room 1 and out of
    # its door, not out of room 0's first-sorted door.
    hops = {
        ((1, 0), (5, 0)): (((1, 0), (5, 0), ("in0",), 10),),
        ((1, 0), (5, 1)): (((1, 0), (5, 1), ("in1",), 11),),
        ((5, 0), (1, 0)): (((5, 0), (1, 0), ("out0",), 2),),
        ((5, 1), (1, 0)): (((5, 1), (1, 0), ("out1",), 4),),
    }

    def route_between(a, b):
        try:
            return hops[(a, b)]
        except KeyError:
            raise ValueError((a, b)) from None

    beats = [_beat("a", 1), _beat("n", 1, "arrival_nudge")]
    out = _thread_maps(
        beats, start=(1, 0), beat_place={"a": (1, 0), "n": (1, 0)}, warp_dest={},
        warp_origin={}, nudge_source={"n": (5, 4)},
        places_on_map={5: ((5, 0), (5, 1))}, route_between=route_between)

    transit = next(b for b in out if b.template == "transit")
    assert dict(transit.kwargs)["hops"] == (("in1",), ("out1",))


def test_arrival_nudge_transit_uses_door_steps_when_the_route_picks_another_door():
    # 2026-10-02, CH02: Moki's stacked west exit -- three warps (events 37,
    # 23, 36) from map 32 to map 33. The shortest route crosses event 37; a
    # nudge that needs event 23's arrival takes event 23's own step.
    out37 = ((32, 0), (33, 0), ("ev37",), 37)
    out23 = ((32, 0), (33, 0), ("ev23",), 23)
    hops = {((33, 0), (32, 0)): (((33, 0), (32, 0), ("back",), 1),),
            ((32, 0), (33, 0)): (out37,)}

    def route_between(a, b):
        try:
            return hops[(a, b)]
        except KeyError:
            raise ValueError((a, b)) from None

    beats = [_beat("a", 33), _beat("n", 33, "arrival_nudge")]
    out = _thread_maps(
        beats, start=(33, 0), beat_place={"a": (33, 0), "n": (33, 0)}, warp_dest={},
        warp_origin={}, nudge_source={"n": (32, 23)}, route_between=route_between,
        door_steps={(32, 23): (out23,), (32, 37): (out37,)})

    transit = next(b for b in out if b.template == "transit")
    assert dict(transit.kwargs)["hops"] == (("back",), ("ev23",))


# -- a real connection outside the reached world is not an edge ----------------

def _connection_route(monkeypatch, reach):
    """`_route_between` over one synthetic connection, map 1 -> map 2, whose
    only crossing is (9,0) -> (0,0)."""
    from types import SimpleNamespace

    from rpg2gba.beat_gen import __main__ as bg

    crossing = SimpleNamespace(exit_cell=(9, 0), entry_cell=(0, 0), press="RIGHT")
    monkeypatch.setattr(bg, "load_connections", lambda: ["conn"])
    monkeypatch.setattr(bg, "connections_between", lambda loaded, a, b: ["conn"])
    monkeypatch.setattr(bg, "connection_crossings", lambda conn, **kw: [crossing])
    monkeypatch.setattr(bg, "_map_constant_for", lambda m: f"MAP_{m}")
    edge = SimpleNamespace(kind="connection", src_map=1, dst_map=2, event_id=None,
                           src_cell=None, dst_cell=None)
    world = SimpleNamespace(edges_from=lambda m: [edge] if m == 1 else [])
    graphs = {1: SimpleNamespace(warp_exits={}), 2: SimpleNamespace(warp_exits={})}
    rooms = SimpleNamespace(place_of=lambda m, cell: (m, 0),
                            landing_place=lambda e: (e.dst_map, 0))
    return bg._route_between(world, frozenset({1, 2}), frozenset(reach), graphs, rooms=rooms)


def test_connection_with_an_unreached_map_is_skipped(monkeypatch):
    # 2026-10-22, CH09: entered at Moki's east edge, Kevlar/Route 2 are never
    # reached, and their connection used to fail the whole plan.
    route, _ = _connection_route(monkeypatch, {(1, (5, 0))})
    with pytest.raises(ValueError, match="no warp route"):
        route((1, 0), (2, 0))


def test_connection_reached_on_both_maps_but_misaligned_still_raises(monkeypatch):
    with pytest.raises(ValueError, match="no edge cell is passable"):
        _connection_route(monkeypatch, {(1, (5, 0)), (2, (5, 5))})


# -- a seam hop must land on a cell the walker can leave -----------------------

def _seam_route(monkeypatch, pairs, *, press="UP", reach_extra=()):
    """`_route_between` over a two-map synthetic seam, map 1 -> map 2. Each pair
    is (event id, src cell, dst cell). Map 2's arrow cells are (6,5) -- the
    twin of the pocketed arrival (5,5) -- and the open arrivals' own cells.
    Reach: the pocketed arrival and its twin only; around the open arrival
    (5,9) a walkable (5,10)."""
    from types import SimpleNamespace

    from rpg2gba.beat_gen import __main__ as bg

    monkeypatch.setattr(bg, "seam_warp_cells", lambda dst, src: {(6, 5), (5, 9)})
    monkeypatch.setattr(bg, "seam_press", lambda m, other, cell: press)
    monkeypatch.setattr(bg, "_map_constant_for", lambda m: f"MAP_{m}")
    edges = [SimpleNamespace(kind="seam_warp", src_map=1, dst_map=2, event_id=ev,
                             src_cell=src, dst_cell=dst) for ev, src, dst in pairs]
    world = SimpleNamespace(edges_from=lambda m: edges if m == 1 else [])
    graphs = {1: SimpleNamespace(warp_exits={}), 2: SimpleNamespace(warp_exits={})}
    rooms = SimpleNamespace(place_of=lambda m, cell: (m, 0),
                            landing_place=lambda e: (e.dst_map, 0))
    reach = frozenset({(1, (0, 6)), (1, (0, 10)), (2, (5, 5)), (2, (6, 5)),
                       (2, (5, 9)), (2, (5, 10)), *reach_extra})
    return bg._route_between(world, frozenset({1, 2}), reach, graphs, rooms=rooms)


def test_seam_hop_whose_arrival_is_pocketed_by_its_twin_arrow_is_not_used(monkeypatch):
    # 2026-10-02, ROM run 74 (Route 2 (20,56)): the arrival's only reachable
    # neighbour is its twin arrow tile, which the walker never steps on.
    pocketed = (10, (0, 5), (5, 5))
    open_ = (11, (0, 9), (5, 9))
    route, door_steps = _seam_route(monkeypatch, [pocketed, open_])

    assert [step[3] for step in route((1, 0), (2, 0))] == [11]
    assert set(door_steps) == {(1, 11)}


def test_seam_with_only_a_pocketed_arrival_has_no_route(monkeypatch):
    route, door_steps = _seam_route(monkeypatch, [(10, (0, 5), (5, 5))])

    with pytest.raises(ValueError, match="no warp route"):
        route((1, 0), (2, 0))
    assert door_steps == {}


def test_seam_hop_presses_the_arrows_own_direction(monkeypatch):
    # 2026-10-11, CH06 park seam: twin arrow cells stacked vertically and
    # pressed LEFT. `reach` floods through arrows, so the old first-reachable
    # side was the twin cell below, pressing UP -- which never fires.
    edge = (12, (0, 9), (5, 9))
    route, _ = _seam_route(monkeypatch, [edge], press="LEFT",
                           reach_extra=((1, (1, 9)),))
    [step] = route((1, 0), (2, 0))
    assert step[2] == ("MAP_1", 1, 9, "LEFT", "MAP_2")


def test_warp_hop_never_stands_on_another_warp_tile(monkeypatch):
    # 2026-10-15, CH08 ROM run: Route 1's stacked east exits EV022-24 at
    # (70,11)-(70,13). `reach` floods through warp tiles, so EV023's first
    # side in `_PRESS_INTO` order (south, pressing UP) was EV022's own tile;
    # the walk warped on arrival instead of pressing. The west side wins.
    from types import SimpleNamespace

    from rpg2gba.beat_gen import __main__ as bg

    monkeypatch.setattr(bg, "_map_constant_for", lambda m: f"MAP_{m}")
    monkeypatch.setattr(bg, "landing_cell", lambda graph, cell, facing: cell)
    stack = {(5, 4): 23, (5, 5): 22, (5, 6): 24}
    edges = [SimpleNamespace(kind="warp", src_map=1, dst_map=2, event_id=ev,
                             src_cell=cell, dst_cell=(1, 1)) for cell, ev in stack.items()]
    world = SimpleNamespace(edges_from=lambda m: edges if m == 1 else [])
    exits = {cell: (SimpleNamespace(event_id=ev, dest_facing=0),) for cell, ev in stack.items()}

    def neighbors(cell):
        x, y = cell
        return [SimpleNamespace(target=n) for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))]

    graphs = {1: SimpleNamespace(warp_exits=exits, neighbors=neighbors),
              2: SimpleNamespace(warp_exits={}, neighbors=neighbors)}
    rooms = SimpleNamespace(place_of=lambda m, cell: (m, 0),
                            landing_place=lambda e: (e.dst_map, 0))
    # (5,3) is a pocket above the stack: in `reach` only through the warps.
    reach = frozenset({(1, c) for c in stack} | {(1, (4, 4)), (1, (4, 5)), (1, (4, 6)),
                                                 (1, (5, 3)), (2, (1, 1))})
    _route, door_steps = bg._route_between(world, frozenset({1, 2}), reach, graphs, rooms=rooms)

    for (_m, ev), steps in door_steps.items():
        for _src, _dst, hop, _ev in steps:
            assert (hop[1], hop[2]) not in stack, (ev, hop)
            assert hop[3] == "RIGHT"


def test_seam_hop_unreachable_from_its_press_side_is_not_used(monkeypatch):
    route, door_steps = _seam_route(monkeypatch, [(12, (0, 9), (5, 9))], press="LEFT")
    with pytest.raises(ValueError, match="no warp route"):
        route((1, 0), (2, 0))
    assert door_steps == {}
