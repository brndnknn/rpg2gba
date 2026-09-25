"""Ruling 19 steps 4-5: arms the walk's state and cell select
(`beat_gen/state_arms.py`). `run_page` is stubbed: `page_sim` has its own
tests; these pin what the stage does with a firing's result."""
from __future__ import annotations

from types import SimpleNamespace

from rpg2gba.beat_gen import state_arms
from rpg2gba.beat_gen.page_sim import Firing, PageRun
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs
from rpg2gba.beat_gen.state_arms import apply_taint, select_state_arms
from rpg2gba.story_state.model import VARIABLE_TOP
from rpg2gba.story_state.state import Adjust, Assign, SelfSwitch, Switch, Test, Variable

PAGE = "map064/ev001/p0"
A = SelfSwitch(64, 1, "A")


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
        (arms,), {var200: frozenset({1})}, row_states=lambda _m: states,
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
        {}, row_states=lambda _m: states, page_for=lambda _p: {"list": [
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

