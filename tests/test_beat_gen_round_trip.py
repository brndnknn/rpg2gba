"""Choice round trips (operator ruling 2026-09-29, `beat_gen/round_trip.py`):
No -> the re-offer page -> Yes -> the autorun re-fires into the Yes arm."""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen.arms import split_choice_arms
from rpg2gba.beat_gen.page_sim import Firing, run_page
from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.beat_gen.round_trip import RoundTrip, find_round_trip
from rpg2gba.chapter_manifest.generator import iter_page_scopes
from rpg2gba.story_state.extract import extract_map
from rpg2gba.story_state.state import SelfSwitch

MAP, EV = 50, 5
P, P1, Q = f"map{MAP:03d}/ev{EV:03d}/p0", f"map{MAP:03d}/ev{EV:03d}/p1", f"map{MAP:03d}/ev{EV:03d}/p2"
_NONE = {"switch1_valid": False, "switch2_valid": False,
         "variable_valid": False, "self_switch_valid": False}


def _cmd(code: int, indent: int, *params) -> dict:
    return {"code": code, "indent": indent, "parameters": list(params)}


def _when(letter: str) -> dict:
    return {**_NONE, "self_switch_valid": True, "self_switch_ch": letter}


def _event(*, reoffer_sets_b: bool = True) -> dict:
    """p0: an autorun. If SSB is set it jumps to `ready`; else asks Yes/No.
    Yes (b2, carries the `ready` label): sets SSC. No (b3): sets SSD.
    p1 (SSC): talk. p2 (SSD): asks again; its Yes sets SSB (when
    `reoffer_sets_b`) and clears SSD, its No writes nothing."""
    p0 = [
        _cmd(111, 0, 2, "B", 0), _cmd(119, 1, "ready"), _cmd(0, 1),
        _cmd(411, 0), _cmd(0, 1), _cmd(412, 0),
        _cmd(101, 0, "ready?"),
        _cmd(102, 0, ["Yes", "No"], 2),
        _cmd(402, 0, 0, "Yes"), _cmd(118, 1, "ready"), _cmd(123, 1, "C", 0), _cmd(0, 1),
        _cmd(402, 0, 1, "No"), _cmd(123, 1, "D", 0), _cmd(0, 1),
        _cmd(404, 0), _cmd(0, 0),
    ]
    p2 = [
        _cmd(102, 0, ["Yes", "No"], 2),
        _cmd(402, 0, 0, "Yes"),
        *([_cmd(123, 1, "B", 0)] if reoffer_sets_b else []),
        _cmd(123, 1, "D", 1), _cmd(0, 1),
        _cmd(402, 0, 1, "No"), _cmd(0, 1),
        _cmd(404, 0), _cmd(0, 0),
    ]
    return {"id": EV, "pages": [
        {"trigger": 3, "condition": dict(_NONE), "list": p0},
        {"trigger": 0, "condition": _when("C"), "list": [_cmd(101, 0, "go ahead"), _cmd(0, 0)]},
        {"trigger": 0, "condition": _when("D"), "list": p2},
    ]}


def _world(**kw):
    event = _event(**kw)
    states = extract_map(MAP, {"events": [event]}, common_events=[], switch_labels={})
    branches = {s.row_id: s.branch for i, p in enumerate(event["pages"])
                for s in iter_page_scopes(MAP, event, i, p)}
    arms: dict[str, list[str]] = {}
    for rid, b in branches.items():
        if b is not None:
            arms.setdefault(rid.rsplit("/b", 1)[0], []).append(rid)
    pages = {f"map{MAP:03d}/ev{EV:03d}/p{i}": p for i, p in enumerate(event["pages"])}
    return states, branches, arms, pages


def _find(**kw) -> RoundTrip | None:
    states, branches, arms, pages = _world(**kw)
    return find_round_trip(
        P, f"{P}/b3", f"{P}/b2", seed={}, row_states=lambda _m: states, page_for=pages.get,
        branch_of=branches.get, arms_of=lambda pg: arms.get(pg, ()),
        claimed=set(states), event_cell=lambda _p: (14, 6))


def test_page_sim_follows_a_jump_into_a_sibling_arm():
    states, _b, _a, pages = _world()
    state = {SelfSwitch(MAP, EV, "B"): frozenset({True})}
    run = run_page(P, pages[P], states, state, Firing(cell=None, event_cell=None))
    assert run.taken == {f"{P}/b0", f"{P}/b2"}
    assert run.not_taken == {f"{P}/b1", f"{P}/b3"}
    assert run.exact
    assert run.state[SelfSwitch(MAP, EV, "C")] == frozenset({True})
    assert SelfSwitch(MAP, EV, "D") not in run.state


def test_no_then_the_reoffer_then_yes_is_a_round_trip_into_the_yes_arm():
    trip = _find()
    assert trip == RoundTrip(page=P, killed=f"{P}/b3", via=Q, via_arm=f"{Q}/b0",
                             into=f"{P}/b2")


def test_no_round_trip_when_the_reoffer_does_not_re_enable_the_sibling():
    assert _find(reoffer_sets_b=False) is None


def test_no_round_trip_through_an_arm_nobody_claims():
    states, branches, arms, pages = _world()
    assert find_round_trip(
        P, f"{P}/b3", f"{P}/b2", seed={}, row_states=lambda _m: states, page_for=pages.get,
        branch_of=branches.get, arms_of=lambda pg: arms.get(pg, ()),
        claimed={r for r in states if not r.startswith(Q + "/")}) is None


def _beats():
    return (
        PlannedBeat(name="p0", template="generic", map_id=MAP, group="p0",
                    rows=(P, f"{P}/b1", f"{P}/b2", f"{P}/b3")),
        PlannedBeat(name="p2", template="generic", map_id=MAP, group="p2",
                    rows=(Q, f"{Q}/b0")),
    )


def _split(trip: RoundTrip | None, openers=None):
    states, branches, _arms, _pages = _world()
    table = openers or {P: [7], f"{P}/b2": [11, 12], Q: [2]}
    return split_choice_arms(
        _beats(), branch_of=lambda rid: branches.get(rid),
        parent_of=lambda rid: states[rid].parent_row_id,
        killed_by=lambda page: (f"{P}/b2", f"{P}/b3") if page == P else (f"{Q}/b0",),
        choice_openers=lambda rid: table.get(rid, []),
        round_trip=lambda *_a: trip)


def test_split_walks_the_losing_arm_first_and_moves_the_walked_arm_to_the_reoffer():
    trip = _find()
    beats, unselected = _split(trip)
    assert unselected == ()
    by = {b.name: b for b in beats}
    assert by["p0"].rows == (P, f"{P}/b1", f"{P}/b3")
    assert by["p0"].kwarg("choice_answers") == ((7, 1),)
    # the re-offer beat claims its own rows, then the re-fired page's Yes arm; every
    # choice on either page has an answer (the quiz's two inline choices too)
    assert by["p2"].rows == (Q, f"{Q}/b0", f"{P}/b2")
    assert by["p2"].kwarg("choice_answers") == ((2, 0), (11, 0), (12, 0))


def test_split_keeps_the_single_arm_and_arm_gated_shape_without_a_round_trip():
    beats, unselected = _split(None)
    by = {b.name: b for b in beats}
    assert by["p0"].rows == (P, f"{P}/b1", f"{P}/b2")
    assert [e.row_id for e in unselected] == [f"{P}/b3"]
    assert by["p2"].rows == (Q, f"{Q}/b0")


def test_a_choice_index_shared_by_both_pages_fails_loud():
    trip = _find()
    with pytest.raises(ValueError, match="list index"):
        _split(trip, openers={P: [7], f"{P}/b2": [2], Q: [2]})
