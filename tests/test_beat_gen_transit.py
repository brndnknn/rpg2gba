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
