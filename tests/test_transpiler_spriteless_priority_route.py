"""A move route that only toggles render priority (39/40) on another event with
no character sheet is dropped (Map066 EV048-053 "Fakefloor" under the Gym 2
pillar); the same route on a sprited event, or any route with a real step, still
emits. Setup idiom from ``tests/test_transpiler_remote_rocks_heart.py``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

_PRESEED_MD = """\
# Pre-seed table

| kind | index | uranium label | constant | notes |
|------|-------|---------------|----------|-------|
| flag | 999 | Preseed Only | FLAG_PRESEED_ONLY | unrelated pre-seed row so pre_seed() has content |
"""
MAP_ID = 66


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def route(*codes: int) -> dict:
    return {"list": [*({"code": c, "parameters": []} for c in codes), {"code": 0, "parameters": []}],
            "repeat": False, "skippable": False}


def event(ev_id: int, sheet: str) -> dict:
    return {"id": ev_id, "name": "e", "x": 0, "y": 0,
            "pages": [{"trigger": 0, "graphic": {"character_name": sheet}, "list": [cmd(0)]}]}


@pytest.fixture()
def ctx(tmp_path: Path) -> T.TranspileContext:
    (tmp_path / "s.json").write_text("{}", encoding="utf-8")
    (tmp_path / "v.json").write_text("{}", encoding="utf-8")
    (tmp_path / "p.md").write_text(_PRESEED_MD, encoding="utf-8")
    reg = FlagRegistry()
    reg.pre_seed(tmp_path / "p.md", tmp_path / "s.json", tmp_path / "v.json")
    c = T.TranspileContext(registry=reg)
    c.register_map_rocks(MAP_ID, [event(48, ""), event(46, "HGSS_000"), event(45, "PU-BurolePillar")])
    return c


def run(ctx: T.TranspileContext, cmds: list[dict]) -> T.TranspiledEvent:
    ev = {"id": 45, "name": "Pillar", "x": 0, "y": 0,
          "pages": [{"trigger": 0, "graphic": {"character_name": "PU-BurolePillar"},
                     "list": [*cmds, cmd(0)]}]}
    return T.transpile_event(MAP_ID, ev, ctx)


def test_prescan_records_spriteless_events(ctx: T.TranspileContext) -> None:
    assert ctx.spriteless_event_ids[MAP_ID] == frozenset({48})


def test_priority_only_route_on_spriteless_event_is_dropped(ctx: T.TranspileContext) -> None:
    out = run(ctx, [cmd(209, [48, route(39)]), cmd(210)])
    assert "applymovement(48" not in out.text
    assert "render-priority only on sprite-less event 48" in out.text
    assert not out.unhandled


def test_priority_only_route_on_sprited_event_still_emits(ctx: T.TranspileContext) -> None:
    out = run(ctx, [cmd(209, [46, route(39)]), cmd(210)])
    assert "applymovement(46" in out.text


def test_real_step_on_spriteless_event_still_emits(ctx: T.TranspileContext) -> None:
    out = run(ctx, [cmd(209, [48, route(39, 1)]), cmd(210)])
    assert "applymovement(48" in out.text
