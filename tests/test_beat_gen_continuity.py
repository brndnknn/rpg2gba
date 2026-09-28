"""`beat_gen.continuity.thread_maps` (C6 part two): each warp's start and end
side follow from where the player is and where the next beat is.

2026-09-28 (operator ruling, investigations/warp-round-trips-and-gated-
doors.md): warp beats are one-way by default -- a crossing warp always
starts on its origin and ends on `dest` (one leg) unless the very next beat
needs `origin` and not `dest`. These tests were rewritten for that rule;
see individual docstrings for what changed."""
import pytest

from rpg2gba.beat_gen.continuity import thread_maps
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs


def _warp(name: str, map_id: int, event_id: int = 1, **kw) -> PlannedBeat:
    return PlannedBeat(name=name, template="warp", map_id=map_id, rows=(f"{name}/r",),
                       group=name, kwargs=make_kwargs(
                           direction="UP", round_trip=True, event_id=event_id, **kw))


def _beat(name: str, map_id: int, template: str = "generic") -> PlannedBeat:
    return PlannedBeat(name=name, template=template, map_id=map_id, rows=(f"{name}/r",),
                       group=name)


def _sides(beats):
    return [(b.name, dict(b.kwargs).get("start_side"), dict(b.kwargs).get("end_side"))
            for b in beats if b.template == "warp"]


DEST = {"w": 2}


def _route_1_2(a: int, b: int):
    """Minimal two-map `route_between`: one hop each way, map1 event 1 is
    the door (matches `_warp`'s default `event_id=1`)."""
    if (a, b) == (1, 2):
        return ((1, 2, ("M1", 0, 0, "UP", "M2"), 1),)
    if (a, b) == (2, 1):
        return ((2, 1, ("M2", 0, 0, "UP", "M1"), 2),)
    raise ValueError(f"no route {a} -> {b}")


def test_warp_starting_on_the_far_side_transits_to_its_origin_first():
    """2026-09-28 ruling: a crossing warp beat always starts on its origin
    now -- there is no more "entered from the far side" case in continuity
    (that shape survives only in `warp_beat`'s own `start_side='dest'`
    parameter for a beat that owns a row on the far map). If the player is
    on `dest` when a warp beat comes up, a transit takes them to `origin`
    first."""
    out = thread_maps([_warp("w", 1), _beat("a", 1)], start_map=2, warp_dest=DEST,
                      nudge_source={}, route_between=_route_1_2)
    assert [b.name for b in out] == ["w_transit", "w", "a"]
    assert out[0].template == "transit"
    assert _sides(out) == [("w", "origin", "origin")]
    assert "round_trip" not in dict(out[1].kwargs)


def test_warp_returns_to_its_own_side_when_the_next_beat_is_there():
    out = thread_maps([_warp("w", 1), _beat("a", 1)], start_map=1, warp_dest=DEST,
                      nudge_source={})
    assert _sides(out) == [("w", "origin", "origin")]


def test_warp_crosses_over_when_the_next_beat_is_across():
    out = thread_maps([_warp("w", 1), _beat("a", 2)], start_map=1, warp_dest=DEST,
                      nudge_source={})
    assert _sides(out) == [("w", "origin", "dest")]


def test_last_warp_ends_on_dest_by_default():
    """2026-09-28 ruling: one-way by default. With no next beat to demand
    the origin back, a crossing warp ends on `dest` -- a single forward
    leg -- not a round trip back to where it started."""
    out = thread_maps([_warp("w", 1)], start_map=1, warp_dest=DEST, nudge_source={})
    assert _sides(out) == [("w", "origin", "dest")]


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


# -- gated-door transit guard (2026-09-28 ruling) --------------------------


def _route_via_gate(a: int, b: int):
    """A 3-map world where the only way between 2 and 3 crosses map 1's
    event 7 -- the gated door in these tests."""
    routes = {
        (1, 2): ((1, 2, ("M1", 0, 0, "UP", "M2"), 7),),
        (2, 3): ((2, 3, ("M2", 0, 0, "UP", "M3"), 9),),
        (3, 2): ((3, 1, ("M3", 0, 0, "UP", "M1"), 11), (1, 2, ("M1", 0, 0, "UP", "M2"), 7)),
    }
    if (a, b) not in routes:
        raise ValueError(f"no route {a} -> {b}")
    return routes[(a, b)]


def test_transit_over_a_gated_door_before_its_warp_beat_fails_loud():
    """No warp beat claims (map 1, event 7) at all here -- a transit that
    has to cross it anyway must fail loud, not silently walk through a
    door the ROM would refuse."""
    with pytest.raises(ValueError, match="gated door"):
        thread_maps([_beat("r", 2)], start_map=3, warp_dest={}, nudge_source={},
                   route_between=_route_via_gate, gated_doors=frozenset({(1, 7)}))


def test_transit_over_a_gated_door_after_its_warp_beat_has_run_passes():
    """`w1` claims (map 1, event 7) by running first; a later transit that
    re-crosses the same door (map 3 -> map 2, which this fake world routes
    back through map 1's event 7) is then allowed."""
    beats = [_warp("w1", 1, event_id=7), _beat("y", 3), _beat("z", 2)]
    out = thread_maps(beats, start_map=1, warp_dest={"w1": 2}, nudge_source={},
                      route_between=_route_via_gate, gated_doors=frozenset({(1, 7)}))
    assert [b.name for b in out] == ["w1", "y_transit", "y", "z_transit", "z"]
