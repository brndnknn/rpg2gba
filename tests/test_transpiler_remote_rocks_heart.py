"""Remote self-switch writes onto smashable rocks (rocks respawn; never SSA),
the `for i in A..B` self-switch loop idiom, and animation 32 -> emote_heart.

Setup idiom copied from ``tests/test_transpiler_set_event_location.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, self_switch_flag_name

_PRESEED_MD = """\
# Pre-seed table

| kind | index | uranium label | constant | notes |
|------|-------|---------------|----------|-------|
| flag | 999 | Preseed Only | FLAG_PRESEED_ONLY | unrelated pre-seed row so pre_seed() has content |
"""
MAP_ID = 35


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def rock_event(ev_id: int) -> dict:
    cond = cmd(111, [12, "Kernel.pbRockSmash"])
    return {"id": ev_id, "name": "rock", "x": 0, "y": 0,
            "pages": [{"trigger": 0, "list": [cond, cmd(412), cmd(0)]}]}


@pytest.fixture()
def ctx(tmp_path: Path) -> T.TranspileContext:
    (tmp_path / "s.json").write_text("{}", encoding="utf-8")
    (tmp_path / "v.json").write_text("{}", encoding="utf-8")
    (tmp_path / "p.md").write_text(_PRESEED_MD, encoding="utf-8")
    reg = FlagRegistry()
    reg.pre_seed(tmp_path / "p.md", tmp_path / "s.json", tmp_path / "v.json")
    c = T.TranspileContext(registry=reg)
    c.register_map_rocks(MAP_ID, [rock_event(14), rock_event(15)])
    return c


def run(ctx: T.TranspileContext, cmds: list[dict], event_id: int = 19) -> T.TranspiledEvent:
    ev = {"id": event_id, "name": "cut", "x": 0, "y": 0,
          "pages": [{"trigger": 3, "list": [*cmds, cmd(0)]}]}
    return T.transpile_event(MAP_ID, ev, ctx)


def ss(text: str, code: int = 355) -> dict:
    return cmd(code, [text])


def loop_rows(body: str = '   pbSetSelfSwitch(i,"A",true)') -> list[dict]:
    return [ss("for i in 14..17"), ss(body, 655), ss("end", 655)]


def test_prescan_finds_rocks_only() -> None:
    plain = {"id": 3, "name": "n", "pages": [{"list": [cmd(111, [12, "foo()"])]}]}
    assert T.smashable_rock_event_ids([rock_event(14), plain]) == frozenset({14})


def test_single_write_to_rock_removes_object(ctx: T.TranspileContext) -> None:
    out = run(ctx, [ss('pbSetSelfSwitch(14,"A",true)')])
    assert "removeobject(14)" in out.text
    assert "setflag(" not in out.text
    assert not out.unhandled


def test_false_write_to_rock_unchanged(ctx: T.TranspileContext) -> None:
    out = run(ctx, [ss('pbSetSelfSwitch(14,"A",false)')])
    assert "removeobject" not in out.text
    assert f"clearflag({self_switch_flag_name(MAP_ID, 14, 'A')})" in out.text


def test_single_write_to_non_rock_sets_ssa(ctx: T.TranspileContext) -> None:
    out = run(ctx, [ss('pbSetSelfSwitch(16,"A",true)')])
    assert f"setflag({self_switch_flag_name(MAP_ID, 16, 'A')})" in out.text
    assert "removeobject" not in out.text


def test_loop_mixed_range_in_order(ctx: T.TranspileContext) -> None:
    out = run(ctx, loop_rows())
    assert not out.unhandled
    lines = [ln.strip() for ln in out.text.splitlines() if not ln.strip().startswith("#")]
    body = [ln for ln in lines if ln.startswith(("removeobject", "setflag"))]
    assert body == [
        "removeobject(14)",
        "removeobject(15)",
        f"setflag({self_switch_flag_name(MAP_ID, 16, 'A')})",
        f"setflag({self_switch_flag_name(MAP_ID, 17, 'A')})",
    ]


def test_loop_malformed_body_still_queues(ctx: T.TranspileContext) -> None:
    rows = [ss("for i in 14..17"), ss('   pbSetSelfSwitch(i,"A",true)', 655),
            ss("   pbSetSelfSwitch(3,\"A\",true)", 655), ss("end", 655)]
    out = run(ctx, rows)
    assert out.unhandled
    assert "removeobject" not in out.text


def test_loop_wrong_var_still_queues(ctx: T.TranspileContext) -> None:
    out = run(ctx, loop_rows('   pbSetSelfSwitch(j,"A",true)'))
    assert out.unhandled


def test_loop_in_common_event_queues(ctx: T.TranspileContext) -> None:
    ce = {"id": 7, "name": "ce", "list": [*loop_rows(), cmd(0)]}
    out = T.transpile_common_event(ce, ctx)
    assert out.unhandled
    assert "removeobject" not in out.text


def test_animation_32_emits_heart_movement(ctx: T.TranspileContext) -> None:
    out = run(ctx, [cmd(207, [21, 32])])
    assert not out.unhandled
    assert "movement Map035_EV019_Page1_Move1 {\n    emote_heart\n}" in out.text
    assert "applymovement(21, Map035_EV019_Page1_Move1)" in out.text
    assert "waitmovement(0)" in out.text


def test_animation_32_player_target(ctx: T.TranspileContext) -> None:
    out = run(ctx, [cmd(207, [-1, 32])])
    assert "applymovement(OBJ_EVENT_ID_PLAYER, Map035_EV019_Page1_Move1)" in out.text


def test_unknown_animation_still_queues(ctx: T.TranspileContext) -> None:
    out = run(ctx, [cmd(207, [21, 9999])])
    assert out.unhandled
    assert "emote_heart" not in out.text
