"""Ruling 19: exclusive branch arms (REDERIVATION_PLAN.md §16.3)."""
from __future__ import annotations

from types import SimpleNamespace

from rpg2gba.beat_gen.arms import (
    blocked_arms,
    random_arm_guards,
    split_choice_arms,
    walk_checked,
)
from rpg2gba.beat_gen.plan import PlannedBeat, Selection, make_kwargs
from rpg2gba.story_state.state import Assign, Switch, Test, Variable


def _row(row_id: str, kind: str = "branch"):
    return SimpleNamespace(row_id=row_id, kind=kind)


def _verdict(*blockers: str):
    return SimpleNamespace(blockers=tuple(blockers))


def test_blocked_sibling_arms_leave_the_plan():
    rows = (_row("map033/ev002/p0", "page"),
            _row("map033/ev002/p0/b0"),               # got the item: always
            _row("map033/ev002/p0/b1"),               # bag full: harness
            _row("map033/ev034/p0/b1"),               # trainer loss: fork
            _row("map049/ev022/p0/b0"))               # a fork-owned landing row
    verdicts = {"map033/ev002/p0": _verdict(), "map033/ev002/p0/b0": _verdict(),
                "map033/ev002/p0/b1": _verdict("harness:full_bag"),
                "map033/ev034/p0/b1": _verdict("fork:whiteout"),
                "map049/ev022/p0/b0": _verdict("fork:whiteout")}
    out = blocked_arms(Selection(owned=rows, refusals=(), elsewhere=()), verdicts,
                       fork_owned={"map049/ev022/p0/b0"})
    assert [r.row_id for r in out.owned] == [
        "map033/ev002/p0", "map033/ev002/p0/b0", "map049/ev022/p0/b0"]
    assert [(e.row_id, e.status) for e in out.elsewhere] == [
        ("map033/ev002/p0/b1", "unselected_arm"), ("map033/ev034/p0/b1", "unselected_arm")]
    assert "harness:full_bag" in out.elsewhere[0].detail


def test_a_blocked_page_row_is_not_an_arm_and_stays():
    rows = (_row("map010/ev001/p0", "page"),)
    out = blocked_arms(Selection(owned=rows, refusals=(), elsewhere=()),
                       {"map010/ev001/p0": _verdict("harness:full_bag")}, fork_owned=())
    assert out.owned == rows and out.elsewhere == ()


# --- random arms ------------------------------------------------------------

def _state(parent, *tests, writes=(), havoc=()):
    guard = None if parent is None else SimpleNamespace(tests=tuple(tests))
    return SimpleNamespace(parent_row_id=parent, arm_guard=guard, writes=writes,
                           havoc_keys=havoc)


def test_random_arms_carry_their_guard_path():
    """Auntie's shape: the page rolls var 102 (122 operand type 2), then
    branches on it; a nested arm keeps its parent's test first."""
    page = {"list": [{"code": 122, "parameters": [102, 102, 0, 2, 0, 12]}]}
    states = {
        "map049/ev001/p3/b0": _state("map049/ev001/p3", Test(Variable(102), "==", 0)),
        "map049/ev001/p3/b1": _state("map049/ev001/p3", Test(Variable(102), "!=", 0)),
        "map049/ev001/p3/b2": _state("map049/ev001/p3/b1", Test(Variable(102), "==", 1)),
    }
    guards = random_arm_guards(list(states), states, lambda _page: page)
    assert guards["map049/ev001/p3/b0"] == ((102, "==", 0),)
    assert guards["map049/ev001/p3/b2"] == ((102, "!=", 0), (102, "==", 1))


def test_arms_on_state_the_page_did_not_roll_are_not_random():
    page = {"list": [{"code": 122, "parameters": [102, 102, 0, 2, 0, 12]}]}
    states = {
        "map010/ev001/p0/b0": _state("map010/ev001/p0", Test(Variable(1), "==", 0)),
        "map010/ev001/p0/b1": _state("map010/ev001/p0", Test(Switch(35), "==", True)),
    }
    assert random_arm_guards(list(states), states, lambda _page: page) == {}
    no_roll = {"list": [{"code": 122, "parameters": [102, 102, 0, 0, 3]}]}
    assert random_arm_guards(["map010/ev001/p0/b0"], states, lambda _p: no_roll) == {}


def test_walk_checked_lists_every_random_arm():
    beat = PlannedBeat(name="m049e001p3", template="generic", map_id=49,
                       rows=("map049/ev001/p3", "map049/ev001/p3/b0"), group="g",
                       kwargs=make_kwargs(random_arms=(("map049/ev001/p3/b0",
                                                        ((102, "==", 0),)),)))
    assert walk_checked((beat,)) == {
        "map049/ev001/p3/b0":
            "arm on a rolled or computed value (var 102 == 0); the walk checks whichever fires"}


def test_arms_on_a_value_the_page_computes_are_read_back_too():
    """The lesson's shape (`map032/ev009/p2`): a script sets var 1 from the
    starter index, which the model can only bound to {0, 1, 2}."""
    page_id = "map032/ev009/p2"
    states = {
        page_id: _state(None, writes=(Assign(Variable(1), frozenset({0, 1, 2}), False, "s", 45),)),
        f"{page_id}/b4": _state(page_id, Test(Variable(1), "==", 0)),
        f"{page_id}/b5": _state(page_id, Test(Variable(1), "!=", 0)),
    }
    guards = random_arm_guards([f"{page_id}/b4", f"{page_id}/b5"], states, lambda _p: {"list": []})
    assert guards == {f"{page_id}/b4": ((1, "==", 0),), f"{page_id}/b5": ((1, "!=", 0),)}
    exact = {**states, page_id: _state(None, writes=(Assign(Variable(1), frozenset({2}), False,
                                                            "s", 45),))}
    assert random_arm_guards([f"{page_id}/b4"], exact, lambda _p: {"list": []}) == {}
    havoc = {**states, page_id: _state(None, havoc=(Variable(1),))}
    assert set(random_arm_guards([f"{page_id}/b4"], havoc, lambda _p: {"list": []})) == {
        f"{page_id}/b4"}


# --- choice arms ------------------------------------------------------------

PAGE = "map068/ev003/p0"
BRANCHES = {
    f"{PAGE}/b0": SimpleNamespace(arm_kind="choice", choice_index=0, opener_index=3),
    f"{PAGE}/b1": SimpleNamespace(arm_kind="choice", choice_index=1, opener_index=3),
    f"{PAGE}/b2": SimpleNamespace(arm_kind="choice", choice_index=2, opener_index=3),
    f"{PAGE}/b3": SimpleNamespace(arm_kind="then", choice_index=None, opener_index=9),
}
PARENT = {f"{PAGE}/b0": PAGE, f"{PAGE}/b1": PAGE, f"{PAGE}/b2": PAGE,
          f"{PAGE}/b3": f"{PAGE}/b1"}   # b3 is nested in answer 1


def _split(rows, killers=()):
    beat = PlannedBeat(name="m068e003p0", template="generic", map_id=68, rows=rows, group="g")
    return split_choice_arms(
        (beat,), branch_of=BRANCHES.get, parent_of=PARENT.get,
        killed_by=lambda page: killers, choice_openers=lambda rid: [3] if rid == PAGE else [])


def test_repeatable_answers_each_get_a_beat_and_the_last_claims_the_page():
    beats, unselected = _split((PAGE, f"{PAGE}/b0", f"{PAGE}/b1", f"{PAGE}/b3", f"{PAGE}/b2"))
    assert unselected == ()
    assert [(b.name, b.rows) for b in beats] == [
        ("m068e003p0_c3a0", (f"{PAGE}/b0",)),
        ("m068e003p0_c3a1", (f"{PAGE}/b1", f"{PAGE}/b3")),
        ("m068e003p0", (PAGE, f"{PAGE}/b2")),
    ]
    assert beats[0].kwarg("walk_rows") == (PAGE,)
    assert [b.kwarg("choice_answers") for b in beats] == [((3, 0),), ((3, 1),), ((3, 2),)]
    assert {b.group for b in beats} == {"g"}


def test_answers_that_end_the_page_run_last_and_only_one_of_them():
    beats, unselected = _split((PAGE, f"{PAGE}/b0", f"{PAGE}/b1", f"{PAGE}/b3", f"{PAGE}/b2"),
                               killers={f"{PAGE}/b0", f"{PAGE}/b3"})
    # b2 repeats; b0 and b1 (via its nested b3) both end the page: b0 is walked last.
    assert [b.name for b in beats] == ["m068e003p0_c3a2", "m068e003p0"]
    assert beats[-1].rows == (PAGE, f"{PAGE}/b0")
    assert sorted(e.row_id for e in unselected) == [f"{PAGE}/b1", f"{PAGE}/b3"]
