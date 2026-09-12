"""Unit tests for RMXP code 202 ("Set Event Location") -> ``setobjectxy``.

Setup idiom copied from ``tests/test_transpiler.py`` (``cmd``/``make_event``/
``run_event``, the ``registry``/``ctx`` fixtures).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

_SWITCHES: dict[str, str] = {}
_VARIABLES: dict[str, str] = {}
_PRESEED_MD = """\
# Pre-seed table

| kind | index | uranium label | constant | notes |
|------|-------|---------------|----------|-------|
| flag | 999 | Preseed Only | FLAG_PRESEED_ONLY | unrelated pre-seed row so pre_seed() has content |
"""


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_event(
    pages_cmds: list[list[dict]], trigger: int = 0, id: int = 5, name: str = "npc"
) -> dict:
    pages = [{"trigger": trigger, "list": cmds} for cmds in pages_cmds]
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": pages}


@pytest.fixture()
def registry(tmp_path: Path) -> FlagRegistry:
    switches_path = tmp_path / "uranium_switches.json"
    variables_path = tmp_path / "uranium_variables.json"
    preseed_path = tmp_path / "essentials_to_emerald_map.md"
    switches_path.write_text(json.dumps(_SWITCHES), encoding="utf-8")
    variables_path.write_text(json.dumps(_VARIABLES), encoding="utf-8")
    preseed_path.write_text(_PRESEED_MD, encoding="utf-8")
    reg = FlagRegistry()
    reg.pre_seed(preseed_path, switches_path, variables_path)
    return reg


@pytest.fixture()
def ctx(registry: FlagRegistry) -> T.TranspileContext:
    return T.TranspileContext(registry=registry)


def run_event(
    ctx: T.TranspileContext,
    pages_cmds: list[list[dict]],
    trigger: int = 0,
    map_id: int = 49,
    event_id: int = 5,
    name: str = "npc",
) -> T.TranspiledEvent:
    ev = make_event(pages_cmds, trigger=trigger, id=event_id, name=name)
    return T.transpile_event(map_id, ev, ctx)


# ----------------------------------------------------------------------------
# direct designation (designation_type 0)
# ----------------------------------------------------------------------------


def test_direct_designation_emits_setobjectxy(ctx: T.TranspileContext) -> None:
    # [event_id, designation_type, x, y, direction] — real shape,
    # output/uranium-build/maps/Map197.json event 3 page 0.
    commands = [cmd(T.SET_EVENT_LOCATION, [10, 0, 31, 18, 0])]
    res = run_event(ctx, [commands], trigger=1)
    assert "setobjectxy(10, 31, 18)" in res.text
    assert "turnobject" not in res.text
    assert res.unhandled == []


def test_self_target_event_id_zero_resolves_to_current_event(
    ctx: T.TranspileContext,
) -> None:
    commands = [cmd(T.SET_EVENT_LOCATION, [0, 0, 5, 6, 0])]
    res = run_event(ctx, [commands], trigger=1, event_id=42)
    assert "setobjectxy(42, 5, 6)" in res.text
    assert res.unhandled == []


def test_direct_designation_nonzero_direction_emits_turnobject(
    ctx: T.TranspileContext,
) -> None:
    # direction 8 == RMXP "up" -> DIR_NORTH.
    commands = [cmd(T.SET_EVENT_LOCATION, [10, 0, 31, 18, 8])]
    res = run_event(ctx, [commands], trigger=1)
    lines = [ln.strip() for ln in res.text.splitlines()]
    assert "setobjectxy(10, 31, 18)" in lines
    assert "turnobject(10, DIR_NORTH)" in lines
    # position must be set before facing is changed.
    assert lines.index("setobjectxy(10, 31, 18)") < lines.index(
        "turnobject(10, DIR_NORTH)"
    )
    assert res.unhandled == []


# ----------------------------------------------------------------------------
# out-of-scope designation types -> queue, never emit
# ----------------------------------------------------------------------------


def test_variable_designation_queues(ctx: T.TranspileContext) -> None:
    # designation_type 1 = designate with variables.
    commands = [cmd(T.SET_EVENT_LOCATION, [10, 1, 1, 2, 0])]
    res = run_event(ctx, [commands], trigger=1)
    assert "setobjectxy" not in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SET_EVENT_LOCATION


def test_exchange_designation_queues(ctx: T.TranspileContext) -> None:
    # designation_type 2 = exchange position with another event.
    commands = [cmd(T.SET_EVENT_LOCATION, [10, 2, 7, 0, 0])]
    res = run_event(ctx, [commands], trigger=1)
    assert "setobjectxy" not in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SET_EVENT_LOCATION
