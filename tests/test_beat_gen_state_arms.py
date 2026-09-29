"""Ruling 19 steps 4-5: arms the walk's state and cell select
(`beat_gen/state_arms.py`). `run_page` is stubbed: `page_sim` has its own
tests; these pin what the stage does with a firing's result."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from rpg2gba.beat_gen import state_arms
from rpg2gba.beat_gen.page_sim import Firing, PageRun
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs
from rpg2gba.beat_gen.state_arms import apply_taint, select_state_arms
from rpg2gba.story_state.model import VARIABLE_TOP
from rpg2gba.story_state.state import Adjust, Assign, SelfSwitch, Switch, Test, Variable

PAGE = "map064/ev001/p0"
A = SelfSwitch(64, 1, "A")


def _fix(states):
    """Fill the page-condition fields the liveness check reads: no
    conditions, each trunk row the only page of its event."""
    for rid, rs in states.items():
        for name, default in (("page_tests", ()), ("page_refusals", ())):
            if not hasattr(rs, name):
                setattr(rs, name, default)
        if not hasattr(rs, "event_page_row_ids"):
            rs.event_page_row_ids = (rid if rs.parent_row_id is None else rs.parent_row_id,)
    return states


def _guard(*tests, negated=False, opener=1):
    return SimpleNamespace(tests=tests, negated=negated, outcome=None, opener_index=opener,
                           choice_index=None)


STATES = {
    PAGE: SimpleNamespace(trigger="action", arm_guard=None, parent_row_id=None),
    f"{PAGE}/b0": SimpleNamespace(trigger="action", parent_row_id=PAGE,
                                  arm_guard=_guard(Test(A, "==", False))),
    f"{PAGE}/b1": SimpleNamespace(trigger="action", parent_row_id=PAGE,
                                  arm_guard=_guard(Test(A, "==", True), negated=True)),
}
_fix(STATES)


def _toggle(page_id, page, states, state, firing):
    """map064/ev001/p0: A off takes b0 and sets A; A on takes b1 and clears it."""
    on = True in state.get(A, frozenset({False}))
    taken, skipped = (f"{PAGE}/b1", f"{PAGE}/b0") if on else (f"{PAGE}/b0", f"{PAGE}/b1")
    return PageRun(taken=frozenset({taken}), not_taken=frozenset({skipped}),
                   undecided=frozenset(), state={**state, A: frozenset({not on})}, exact=True)


def _beats():
    principal = PlannedBeat(name="m064e001_flavour_npc", template="flavour_npc", map_id=64,
                            rows=(PAGE,), group="m064e001_flavour_npc")
    arms = PlannedBeat(name="m064e001_flavour_npc_arms", template="generic", map_id=64,
                       rows=(f"{PAGE}/b0", f"{PAGE}/b1"), group="m064e001_flavour_npc",
                       kwargs=make_kwargs(skip_claimed=True))
    return principal, arms


def _run(beats, stub, monkeypatch, **kw):
    monkeypatch.setattr(state_arms, "run_page", stub)
    return select_state_arms(
        beats, {}, row_states=lambda _m: STATES, page_for=lambda _p: {"list": []},
        firing_for=lambda _b, _p: Firing(cell=None, event_cell=None), **kw)


def test_a_page_that_flips_its_own_switch_is_refired_for_the_other_arm(monkeypatch):
    principal, arms = _beats()
    beats, elsewhere = _run((principal, arms), _toggle, monkeypatch)
    # The NPC's first talk (the flavour beat) sets A, so the arms beat's talk
    # takes b1; a third talk, from A cleared again, takes b0.
    assert [(b.name, b.rows) for b in beats] == [
        ("m064e001_flavour_npc", (PAGE,)),
        ("m064e001_flavour_npc_arms", (f"{PAGE}/b1",)),
        ("m064e001_flavour_npc_arms_r1", (f"{PAGE}/b0",)),
    ]
    assert beats[2].kwarg("walk_rows") == (PAGE,)
    assert beats[2].group == "m064e001_flavour_npc"
    assert elsewhere == ()


def test_an_arm_no_firing_takes_leaves_with_what_selected_its_sibling(monkeypatch):
    var200 = Variable(200)
    states = {**STATES, f"{PAGE}/b0": SimpleNamespace(
        trigger="action", parent_row_id=PAGE, arm_guard=_guard(Test(var200, "==", 99)))}

    def never(page_id, page, st, state, firing):
        return PageRun(taken=frozenset({f"{PAGE}/b1"}), not_taken=frozenset({f"{PAGE}/b0"}),
                       undecided=frozenset(), state=dict(state), exact=True)

    _, arms = _beats()
    monkeypatch.setattr(state_arms, "run_page", never)
    beats, elsewhere = select_state_arms(
        (arms,), {var200: frozenset({1})}, row_states=lambda _m: _fix(states),
        page_for=lambda _p: {"list": []},
        firing_for=lambda _b, _p: Firing(cell=None, event_cell=None))
    assert [b.rows for b in beats] == [(f"{PAGE}/b1",)]
    assert [(e.row_id, e.status) for e in elsewhere] == [(f"{PAGE}/b0", "unselected_arm")]
    assert "needs var 200 == 99, and here var 200 is [1]" in elsewhere[0].detail


def test_a_refire_that_needs_an_unanswered_choice_or_a_refused_row_is_not_made(monkeypatch):
    principal, arms = _beats()
    beats, elsewhere = _run((principal, arms), _toggle, monkeypatch,
                            walkable=lambda rid: rid != f"{PAGE}/b0")
    assert [b.name for b in beats] == ["m064e001_flavour_npc", "m064e001_flavour_npc_arms"]
    assert [e.row_id for e in elsewhere] == [f"{PAGE}/b0"]
    beats, _ = _run((principal, arms), _toggle, monkeypatch,
                    choice_openers=lambda rid: [5] if rid == PAGE else [])
    assert [b.name for b in beats] == ["m064e001_flavour_npc", "m064e001_flavour_npc_arms"]


def test_an_arrival_page_fires_once_per_group(monkeypatch):
    nudge = "map032/ev005/p1"
    states = {
        nudge: SimpleNamespace(trigger="autorun", arm_guard=None, parent_row_id=None),
        f"{nudge}/b0": SimpleNamespace(trigger="autorun", parent_row_id=nudge,
                                       arm_guard=_guard(opener=0)),
        f"{nudge}/b1": SimpleNamespace(trigger="autorun", parent_row_id=nudge,
                                       arm_guard=_guard(negated=True, opener=0)),
    }
    calls = []

    def on_event(page_id, page, st, state, firing):
        calls.append(page_id)
        return PageRun(taken=frozenset({f"{nudge}/b0"}), not_taken=frozenset({f"{nudge}/b1"}),
                       undecided=frozenset(), state=dict(state), exact=True)

    monkeypatch.setattr(state_arms, "run_page", on_event)
    beats, elsewhere = select_state_arms(
        (PlannedBeat(name="m032e005_arrival_nudge", template="arrival_nudge", map_id=32,
                     rows=(nudge,), group="g"),
         PlannedBeat(name="m032e005_arrival_nudge_arms", template="generic", map_id=32,
                     rows=(f"{nudge}/b0", f"{nudge}/b1"), group="g")),
        {}, row_states=lambda _m: _fix(states), page_for=lambda _p: {"list": [
            {"code": 111, "parameters": [12, "get_character(0).onEvent?"]}]},
        firing_for=lambda _b, _p: Firing(cell=(3, 4), event_cell=(3, 4)))
    assert calls == [nudge]
    assert beats[1].rows == (f"{nudge}/b0",)
    assert [e.row_id for e in elsewhere] == [f"{nudge}/b1"]


def test_undecided_and_random_arms_stay_claimed_and_other_templates_pass(monkeypatch):
    def undecided(page_id, page, st, state, firing):
        return PageRun(taken=frozenset(), not_taken=frozenset({f"{PAGE}/b1"}),
                       undecided=frozenset({f"{PAGE}/b0"}), state=dict(state), exact=False)

    _, arms = _beats()
    rolled = PlannedBeat(name=arms.name, template="generic", map_id=64, rows=arms.rows,
                         group=arms.group,
                         kwargs=make_kwargs(random_arms=((f"{PAGE}/b1", ((102, "==", 0),)),)))
    stair = PlannedBeat(name="stair", template="stair", map_id=64, rows=("x",), group="s")
    beats, elsewhere = _run((rolled, stair), undecided, monkeypatch)
    assert beats == (rolled, stair) and elsewhere == ()


def test_an_escort_skipped_arm_drops_to_unselected_arm_and_is_never_refired(monkeypatch):
    # Same page shape as the toggle NPC, but claimed as an escort beat: the
    # firing takes b0 (A off), so b1 is skipped. Unlike a generic beat, an
    # escort must NOT get a `_r1` re-fire even though a second run_page
    # would take b1 (ruling 11 -- the ride happens once).
    escort = PlannedBeat(name="m064e001_escort", template="escort", map_id=64,
                         rows=(PAGE, f"{PAGE}/b0", f"{PAGE}/b1"), group="m064e001_escort")

    calls = []

    def stub(page_id, page, states, state, firing):
        calls.append(page_id)
        return _toggle(page_id, page, states, state, firing)

    beats, elsewhere = _run((escort,), stub, monkeypatch)
    assert len(calls) == 1   # never re-fired
    assert [(b.name, b.rows) for b in beats] == [
        ("m064e001_escort", (PAGE, f"{PAGE}/b0")),
    ]
    assert [(e.row_id, e.status) for e in elsewhere] == [(f"{PAGE}/b1", "unselected_arm")]


def test_taint_folds_every_unwalked_write_in_as_a_possibility():
    state = {Switch(35): frozenset({False}), Variable(3): frozenset({1})}
    out = apply_taint(state, [Assign(Switch(35), frozenset({True}), False, "s"),
                              Adjust(Variable(3), "+", 1, False, "s"), A])
    assert out[Switch(35)] == frozenset({False, True})
    assert out[Variable(3)] == frozenset({VARIABLE_TOP})
    assert out[A] == frozenset({False, True})
    assert state[Switch(35)] == frozenset({False})



# --- page liveness (ROM run 20: the lab's aptitude-test NPC) --------------------

EV = "map050/ev005"
P0, P1, P2 = f"{EV}/p0", f"{EV}/p1", f"{EV}/p2"
B2 = f"{P0}/b2"
SS_C, SS_D = SelfSwitch(50, 5, "C"), SelfSwitch(50, 5, "D")


def _lab_states():
    pages = (P0, P1, P2)
    common = dict(page_refusals=(), event_page_row_ids=pages, writes=(), arm_guard=None,
                  parent_row_id=None, trigger="action")
    return {
        P0: SimpleNamespace(**{**common, "page_tests": ()}),
        # the "Yes" arm: sets C, but no beat claims it
        B2: SimpleNamespace(**{**common, "page_tests": (), "parent_row_id": P0,
                               "writes": (Assign(SS_C, frozenset({True}), False, "s"),)}),
        P1: SimpleNamespace(**{**common, "page_tests": (Test(SS_C, "==", True),)}),
        P2: SimpleNamespace(**{**common, "page_tests": (Test(SS_D, "==", True),)}),
    }


def _sets(key):
    def stub(page_id, page, states, state, firing):
        out = dict(state)
        if page_id == P0:
            out[key] = frozenset({True})
        return PageRun(taken=frozenset(), not_taken=frozenset(), undecided=frozenset(),
                       state=out, exact=True)
    return stub


def _lab(beats, stub, monkeypatch, seed=None):
    monkeypatch.setattr(state_arms, "run_page", stub)
    states = _lab_states()
    return select_state_arms(
        beats, seed or {}, row_states=lambda _m: states, page_for=lambda _p: {"list": []},
        firing_for=lambda _b, _p: Firing(cell=None, event_cell=None))


def _lab_beat(name, template, *rows):
    return PlannedBeat(name=name, template=template, map_id=50, rows=rows, group=name)


def test_a_flavour_page_only_an_unwalked_arm_enables_is_arm_gated(monkeypatch):
    # The enabler (the "Yes" arm b2) is an arm of p0, which the route fires
    # and answers "No": p1 is reachable on the ROM, just not on this route.
    p0 = _lab_beat("p0", "generic", P0)
    p1 = _lab_beat("p1", "flavour_npc", P1)
    beats, elsewhere = _lab((p0, p1), _sets(SS_D), monkeypatch)   # answering "No" sets D
    assert [b.name for b in beats] == ["p0"]
    assert [(e.row_id, e.status) for e in elsewhere] == [(P1, "arm_gated")]
    detail = elsewhere[0].detail
    assert P1 in detail and "self switch C == True" in detail
    assert f"live page: {P2}" in detail and "self switch D == True" in detail
    assert B2 in detail and "not walked" in detail and "unwalked arm" in detail


def test_a_page_whose_only_enabler_sits_on_an_unfired_page_never_fires(monkeypatch):
    # Nothing claims p0, so b2 is not an arm of a page the route fires: no
    # answer on this route reaches p1 -- `never_fires`, not `arm_gated`.
    p1 = _lab_beat("p1", "flavour_npc", P1)
    beats, elsewhere = _lab((p1,), _sets(SS_D), monkeypatch)
    assert beats == ()
    assert [(e.row_id, e.status) for e in elsewhere] == [(P1, "never_fires")]
    assert "unwalked arm" not in elsewhere[0].detail


def test_a_page_whose_enabler_is_claimed_and_ordered_before_is_kept(monkeypatch):
    p0 = _lab_beat("p0", "generic", P0)
    p1 = _lab_beat("p1", "flavour_npc", P1)
    beats, elsewhere = _lab((p0, p1), _sets(SS_C), monkeypatch)   # "Yes" sets C
    assert [b.name for b in beats] == ["p0", "p1"] and elsewhere == ()


def test_an_enabler_claimed_but_ordered_after_is_kept_and_reported(monkeypatch):
    p1 = _lab_beat("p1", "flavour_npc", P1)
    writer = _lab_beat("b2", "generic", B2)
    monkeypatch.setattr(state_arms, "run_page", _sets(SS_D))
    states = _lab_states()
    problems = []
    beats, elsewhere = select_state_arms(
        (p1, writer), {}, row_states=lambda _m: states, page_for=lambda _p: {"list": []},
        firing_for=lambda _b, _p: Firing(cell=None, event_cell=None), order_problems=problems)
    assert [b.name for b in beats] == ["p1", "b2"] and elsewhere == ()
    assert [(q.beat, q.page, q.kind, q.position) for q in problems] == [
        ("p1", P1, "enabler_later", 0)]
    assert B2 in problems[0].detail and "later on the route" in problems[0].detail


def test_a_page_live_earlier_and_killed_by_a_write_is_reported_not_demoted(monkeypatch):
    # P0 needs nothing; P2 (needs D) lifts over it once D is set. A beat for
    # P0 placed after the write is `killer_first`.
    setter = _lab_beat("set", "generic", P2)          # P2 itself is dead at seed: never
    p0_late = _lab_beat("p0", "generic", P0)
    states = _lab_states()
    calls = []

    def stub(page_id, page, st, state, firing):
        calls.append(page_id)
        return PageRun(taken=frozenset(), not_taken=frozenset(), undecided=frozenset(),
                       state={**state, SS_D: frozenset({True})}, exact=True)

    monkeypatch.setattr(state_arms, "run_page", stub)
    other = SimpleNamespace(**{**vars(states[P0]), "event_page_row_ids": ("map050/ev009/p0",)})
    states["map050/ev009/p0"] = other
    setter = _lab_beat("set", "generic", "map050/ev009/p0")
    problems = []
    beats, elsewhere = select_state_arms(
        (setter, p0_late), {}, row_states=lambda _m: states, page_for=lambda _p: {"list": []},
        firing_for=lambda _b, _p: Firing(cell=None, event_cell=None), order_problems=problems)
    assert [b.name for b in beats] == ["set", "p0"] and elsewhere == ()
    assert [(q.beat, q.kind) for q in problems] == [("p0", "killer_first")]
    assert "live at route position 0" in problems[0].detail


def test_a_beat_that_fires_p0_then_p1_judges_p1_after_p0s_writes(monkeypatch):
    # A trainer's re-talk / an item ball's negative check: one beat, two pages.
    both = _lab_beat("both", "trainer", P0, P1)
    beats, elsewhere = _lab((both,), _sets(SS_C), monkeypatch)
    assert beats == (both,) and elsewhere == ()
    problems = []
    monkeypatch.setattr(state_arms, "run_page", _sets(SS_C))
    states = _lab_states()
    select_state_arms(
        (both,), {}, row_states=lambda _m: states, page_for=lambda _p: {"list": []},
        firing_for=lambda _b, _p: Firing(cell=None, event_cell=None), order_problems=problems)
    assert problems == []


def test_an_indeterminate_state_keeps_the_beat(monkeypatch):
    p1 = _lab_beat("p1", "flavour_npc", P1)
    for seed in ({SS_C: frozenset({False, True})}, {SS_C: frozenset({VARIABLE_TOP})}):
        beats, elsewhere = _lab((p1,), _sets(SS_D), monkeypatch, seed=seed)
        assert beats == (p1,) and elsewhere == ()
    # a page condition the story model refused is not proof either
    monkeypatch.setattr(state_arms, "run_page", _sets(SS_D))
    states = _lab_states()
    states[P1].page_refusals = (object(),)
    beats, elsewhere = select_state_arms(
        (p1,), {}, row_states=lambda _m: states, page_for=lambda _p: {"list": []},
        firing_for=lambda _b, _p: Firing(cell=None, event_cell=None))
    assert beats == (p1,) and elsewhere == ()


def test_a_dead_page_writes_never_reach_later_beats(monkeypatch):
    # P1 is dead, so its own write (D) must not make P2's beat live later.
    states = _lab_states()
    states[P1].writes = (Assign(SS_D, frozenset({True}), False, "s"),)
    monkeypatch.setattr(state_arms, "run_page", _sets(SS_C))
    p0 = _lab_beat("p0", "generic", P0)
    dead = _lab_beat("p1", "flavour_npc", P1)
    p2 = _lab_beat("p2", "flavour_npc", P2)
    # seed: C True would make P1 live; start instead with everything False.
    calls = []

    def stub(page_id, page, st, state, firing):
        calls.append(page_id)
        return PageRun(taken=frozenset(), not_taken=frozenset(), undecided=frozenset(),
                       state=dict(state), exact=True)

    monkeypatch.setattr(state_arms, "run_page", stub)
    beats, elsewhere = select_state_arms(
        (p0, dead, p2), {}, row_states=lambda _m: states, page_for=lambda _p: {"list": []},
        firing_for=lambda _b, _p: Firing(cell=None, event_cell=None))
    assert calls == [P0]            # neither dead page was fired
    assert [b.name for b in beats] == ["p0"]
    assert sorted(e.row_id for e in elsewhere) == [P1, P2]


def test_an_indeterminate_earlier_state_gives_killer_first_never_a_demotion(monkeypatch):
    # P1 needs C. Earlier the walk can't tell (C is havoc'd by a write the
    # model can't resolve, like the lab starter scene); later C is definitely
    # False and P2 (needs D) holds. That is not proof the page never fires.
    other = "map050/ev009/p0"
    states = _lab_states()
    states[other] = SimpleNamespace(**{**vars(states[P0]), "event_page_row_ids": (other,)})
    steps = iter([{SS_C: frozenset({VARIABLE_TOP})}, {SS_C: frozenset({False}),
                                                      SS_D: frozenset({True})}, {}])

    def stub(page_id, page, st, state, firing):
        return PageRun(taken=frozenset(), not_taken=frozenset(), undecided=frozenset(),
                       state={**state, **next(steps)}, exact=True)

    monkeypatch.setattr(state_arms, "run_page", stub)
    beats = (_lab_beat("a", "generic", other), _lab_beat("b", "generic", other),
             _lab_beat("p1", "flavour_npc", P1))
    problems = []
    out, elsewhere = select_state_arms(
        beats, {}, row_states=lambda _m: states, page_for=lambda _p: {"list": []},
        firing_for=lambda _b, _p: Firing(cell=None, event_cell=None), order_problems=problems)
    assert [b.name for b in out] == ["a", "b", "p1"] and elsewhere == ()
    assert [(q.page, q.kind) for q in problems] == [(P1, "killer_first")]
    assert "possibly live" in problems[0].detail


def test_a_page_that_ended_itself_is_not_walked_again_by_another_group(monkeypatch):
    # p2's own firing clears D (the Yes arm ends the page). A second group of
    # the same page -- facing arms, split off before the route -- would find it
    # dead, and no claimed row brings it back: its rows are unselected arms.
    def stub(page_id, page, states, state, firing):
        out = dict(state)
        if page_id == P2:
            out[SS_D] = frozenset({False})
        return PageRun(taken=frozenset(), not_taken=frozenset(), undecided=frozenset(),
                       state=out, exact=True)

    first = _lab_beat("a", "generic", P2)
    again = _lab_beat("b", "generic", f"{P2}/b1")
    beats, elsewhere = _lab((first, again), stub, monkeypatch, seed={SS_D: frozenset({True})})
    assert [b.name for b in beats] == ["a"]
    assert [(e.row_id, e.status) for e in elsewhere] == [(f"{P2}/b1", "unselected_arm")]
    assert "ended itself" in elsewhere[0].detail
