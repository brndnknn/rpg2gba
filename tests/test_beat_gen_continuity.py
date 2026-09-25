"""`beat_gen.continuity.thread_maps` (C6 part two): each warp's start and end
side follow from where the player is and where the next beat is."""
import pytest

from rpg2gba.beat_gen.continuity import thread_maps
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs


def _warp(name: str, map_id: int, **kw) -> PlannedBeat:
    return PlannedBeat(name=name, template="warp", map_id=map_id, rows=(f"{name}/r",),
                       group=name, kwargs=make_kwargs(direction="UP", round_trip=True, **kw))


def _beat(name: str, map_id: int, template: str = "generic") -> PlannedBeat:
    return PlannedBeat(name=name, template=template, map_id=map_id, rows=(f"{name}/r",),
                       group=name)


def _sides(beats):
    return [(b.name, dict(b.kwargs).get("start_side"), dict(b.kwargs).get("end_side"))
            for b in beats if b.template == "warp"]


DEST = {"w": 2}


def test_warp_entered_from_the_far_side_ends_where_the_next_beat_is():
    out = thread_maps([_warp("w", 1), _beat("a", 1)], start_map=2, warp_dest=DEST,
                      nudge_source={})
    assert _sides(out) == [("w", "dest", "origin")]
    assert "round_trip" not in dict(out[0].kwargs)


def test_warp_returns_to_its_own_side_when_the_next_beat_is_there():
    out = thread_maps([_warp("w", 1), _beat("a", 1)], start_map=1, warp_dest=DEST,
                      nudge_source={})
    assert _sides(out) == [("w", "origin", "origin")]


def test_warp_crosses_over_when_the_next_beat_is_across():
    out = thread_maps([_warp("w", 1), _beat("a", 2)], start_map=1, warp_dest=DEST,
                      nudge_source={})
    assert _sides(out) == [("w", "origin", "dest")]


def test_last_warp_ends_where_it_started():
    out = thread_maps([_warp("w", 1)], start_map=1, warp_dest=DEST, nudge_source={})
    assert _sides(out) == [("w", "origin", "origin")]


def test_beat_on_a_map_the_player_cannot_be_on_fails_loud():
    with pytest.raises(ValueError, match="no beat claims"):
        thread_maps([_beat("a", 1), _beat("b", 3)], start_map=1, warp_dest={}, nudge_source={})


def test_warp_the_player_is_on_neither_side_of_fails_loud():
    with pytest.raises(ValueError, match="no beat claims"):
        thread_maps([_warp("w", 1)], start_map=3, warp_dest=DEST, nudge_source={})


def test_nudge_after_a_warp_that_lands_from_its_source_passes():
    beats = [_warp("w", 1), _beat("n", 1, "arrival_nudge")]
    out = thread_maps(beats, start_map=1, warp_dest=DEST, nudge_source={"n": 2})
    assert _sides(out) == [("w", "origin", "origin")]       # F,B: lands on 1 from 2


def test_nudge_not_right_after_its_crossing_fails_loud():
    beats = [_warp("w", 1), _beat("a", 1), _beat("n", 1, "arrival_nudge")]
    with pytest.raises(ValueError, match="just landed"):
        thread_maps(beats, start_map=1, warp_dest=DEST, nudge_source={"n": 2})


def _escort(name: str, map_id: int) -> PlannedBeat:
    return PlannedBeat(name=name, template="escort", map_id=map_id, rows=(f"{name}/r",),
                       group=name)


def test_escort_then_a_beat_on_the_destination_needs_no_transit():
    beats = [_escort("e", 1), _beat("a", 2)]
    out = thread_maps(beats, start_map=1, warp_dest={"e": 2}, nudge_source={})
    assert [b.name for b in out] == ["e", "a"]   # no transit inserted


def test_escort_then_an_arrival_nudge_from_its_origin_is_accepted():
    beats = [_escort("e", 1), _beat("n", 2, "arrival_nudge")]
    out = thread_maps(beats, start_map=1, warp_dest={"e": 2}, nudge_source={"n": 1})
    assert [b.name for b in out] == ["e", "n"]


def test_boundary_warp_is_left_alone_and_must_be_on_its_own_map():
    boundary = PlannedBeat(name="x", template="warp", map_id=1, rows=("x/r",), group="x",
                           kwargs=make_kwargs(direction="UP", boundary=True))
    out = thread_maps([boundary], start_map=1, warp_dest={"x": 9}, nudge_source={})
    assert out == (boundary,)
    with pytest.raises(ValueError, match="no beat claims"):
        thread_maps([boundary], start_map=2, warp_dest={"x": 9}, nudge_source={})
