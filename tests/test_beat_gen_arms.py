"""Ruling 19: exclusive branch arms (REDERIVATION_PLAN.md §16.3)."""
from __future__ import annotations

from types import SimpleNamespace

from rpg2gba.beat_gen.arms import blocked_arms, random_arm_guards, walk_checked
from rpg2gba.beat_gen.plan import PlannedBeat, Selection, make_kwargs
from rpg2gba.story_state.state import Switch, Test, Variable


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

def _state(parent, *tests):
    guard = SimpleNamespace(tests=tuple(tests))
    return SimpleNamespace(parent_row_id=parent, arm_guard=guard)


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
        "map049/ev001/p3/b0": "random arm (var 102 == 0); the walk checks whichever the RNG picks"}
