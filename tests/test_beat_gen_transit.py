"""`beat_gen.continuity.thread_maps`'s transit-beat insertion (C6 part two),
exercised with a fake `route_between`."""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen.continuity import thread_maps
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs


def _beat(name: str, map_id: int, template: str = "generic") -> PlannedBeat:
    return PlannedBeat(name=name, template=template, map_id=map_id, rows=(f"{name}/r",),
                       group=name)


def _route_between_factory(table):
    """table: {(from, to): hops} -> a `route_between` that raises ValueError
    for any pair not in the table."""
    def fn(a, b):
        if (a, b) in table:
            return table[(a, b)]
        raise ValueError(f"no route {a}->{b}")
    return fn


def test_non_warp_beat_on_another_map_gets_a_transit_inserted_before_it():
    hops = ((2, 1, ("warp", 2, 1, "L", "R")),)
    route_between = _route_between_factory({(2, 1): hops})

    out = thread_maps(
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
        thread_maps(
            [_beat("a", 1)], start_map=2, warp_dest={}, nudge_source={},
            route_between=None,
        )


def test_arrival_nudge_not_right_after_its_crossing_gets_a_transit_via_its_source_map():
    # Player is on map 1, but the nudge beat's source is map 5 -- so the
    # transit must be routed (cur, source) then (source, nudge map), i.e.
    # (1, 5) then (5, 1), not a direct (1, 1) no-op.
    hop_out = ((1, 5, ("warp", 1, 5, "L", "R")),)
    hop_back = ((5, 1, ("warp", 5, 1, "R", "L")),)
    route_between = _route_between_factory({(1, 5): hop_out, (5, 1): hop_back})

    beats = [_beat("a", 1), _beat("n", 1, "arrival_nudge")]
    out = thread_maps(
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
        thread_maps(
            [_beat("a", 5)], start_map=1, warp_dest={}, nudge_source={},
            route_between=route_between,
        )
