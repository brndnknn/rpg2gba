"""One-shot pages: an arms beat for a page another beat already fires is folded
into ELSEWHERE instead of re-bumping an event that ended itself (CH08, Moki
Town ev078 p0)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from rpg2gba.beat_gen.facing import OneShot, fold_one_shot_arms, one_shot_pages
from rpg2gba.beat_gen.plan import PlannedBeat

PAGE = "map009/ev001/p0"
ARM = f"{PAGE}/b0"


def _cmd(code: int, indent: int, *params: object) -> dict:
    return {"code": code, "indent": indent, "parameters": list(params)}


def _event(trunk_extra: list[dict], *, arm_extra: list[dict] | None = None,
           own_switch: str | None = None, higher: str | None = "A") -> dict:
    """Page 0: one conditional branch (b0) then `trunk_extra` at top level."""
    cmds = [_cmd(111, 0, 12, "x"), *(arm_extra or []), _cmd(0, 1), _cmd(412, 0),
            *trunk_extra, _cmd(0, 0)]
    page0 = {"trigger": 2, "list": cmds,
             "condition": ({"self_switch_valid": True, "self_switch_ch": own_switch}
                           if own_switch else {})}
    pages = [page0]
    if higher:
        pages.append({"trigger": 0, "list": [_cmd(0, 0)],
                      "condition": {"self_switch_valid": True, "self_switch_ch": higher}})
    return {"id": 1, "pages": pages}


def _data(event: dict) -> dict:
    return {"events": [event]}


def test_script_lift_of_higher_page_is_one_shot():
    ev = _event([_cmd(355, 0, 'pbSetSelfSwitch(1,"A",true)')])
    got = one_shot_pages(9, _data(ev), [PAGE])
    assert got == {PAGE: OneShot(PAGE, "A", PAGE, lifts=True)}


def test_code_123_off_write_of_own_condition_is_one_shot():
    ev = _event([_cmd(123, 0, "D", 1)], own_switch="D", higher=None)
    got = one_shot_pages(9, _data(ev), [PAGE])
    assert got == {PAGE: OneShot(PAGE, "D", PAGE, lifts=False)}


def test_page_without_ender_is_untouched():
    assert one_shot_pages(9, _data(_event([])), [PAGE]) == {}
    other = _event([_cmd(355, 0, 'pbSetSelfSwitch(7,"A",true)')])   # another event's switch
    assert one_shot_pages(9, _data(other), [PAGE]) == {}


def test_ender_inside_an_arm_does_not_make_the_page_one_shot():
    ev = _event([], arm_extra=[_cmd(123, 1, "A", 0)])
    assert one_shot_pages(9, _data(ev), [PAGE]) == {}


def _beats(arm_kinds: set[str]) -> tuple[tuple[PlannedBeat, ...], dict]:
    trunk = PlannedBeat(name="m009e001_warp", template="warp", map_id=9, rows=(PAGE,),
                        group="m009e001_warp")
    arms = PlannedBeat(name="m009e001_warp_arms", template="generic", map_id=9, rows=(ARM,),
                       group="m009e001_warp")
    floors = {ARM: SimpleNamespace(assertions=[SimpleNamespace(kind=k) for k in arm_kinds])}
    return (trunk, arms), floors


_SHOT = {PAGE: OneShot(PAGE, "A", PAGE, lifts=True)}


def test_arms_beat_of_one_shot_page_becomes_elsewhere():
    beats, floors = _beats({"trigger", "completes"})
    kept, elsewhere = fold_one_shot_arms(beats, _SHOT, floors)
    assert [b.name for b in kept] == ["m009e001_warp"]
    (e,) = elsewhere
    assert (e.row_id, e.status) == (ARM, "walked_with_page")
    assert "m009e001_warp" in e.detail and "A" in e.detail and "completes, trigger" in e.detail


def test_extra_floor_kinds_fail_loud():
    beats, floors = _beats({"trigger", "completes", "text"})
    with pytest.raises(ValueError, match=r"m009e001_warp.*\['text'\]|\['text'\].*m009e001_warp"):
        fold_one_shot_arms(beats, _SHOT, floors)


def test_non_one_shot_page_keeps_its_arms_beat():
    beats, floors = _beats({"trigger", "completes"})
    kept, elsewhere = fold_one_shot_arms(beats, {}, floors)
    assert kept == beats and elsewhere == ()


def test_unclaimed_trunk_keeps_arms_beat():
    beats, floors = _beats({"trigger", "completes"})
    kept, elsewhere = fold_one_shot_arms(beats[1:], _SHOT, floors)
    assert kept == beats[1:] and elsewhere == ()
