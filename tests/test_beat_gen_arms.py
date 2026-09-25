"""Ruling 19: exclusive branch arms (REDERIVATION_PLAN.md §16.3)."""
from __future__ import annotations

from types import SimpleNamespace

from rpg2gba.beat_gen.arms import blocked_arms
from rpg2gba.beat_gen.plan import Selection


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
