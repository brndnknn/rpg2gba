"""Scene funnels (``tileset_converter.funnels``, operator ruling 2026-10-27):
a blank player-touch event that pushes the player onto a scene trigger ends
its pushing page by entering that scene, instead of `end`."""
from __future__ import annotations

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry


def cmd(code: int, *params: object) -> dict:
    return {"code": code, "indent": 0, "parameters": list(params)}


def push(*moves: int) -> dict:
    return cmd(209, -1, {"list": [{"code": c, "parameters": []} for c in (*moves, 0)]})


def blank_page(cmds: list[dict], cond: dict | None = None) -> dict:
    return {"trigger": 1, "condition": cond or {}, "graphic": {"character_name": ""},
            "list": [*cmds, cmd(0)]}


def route4() -> list[dict]:
    return [
        {"id": 32, "name": "EV032", "x": 38, "y": 44, "pages": [
            blank_page([push(3, 19), cmd(210), cmd(123, "A", 0)]),
            blank_page([], {"self_switch_valid": True, "self_switch_ch": "A"}),
        ]},
        {"id": 70, "name": "EV070", "x": 39, "y": 44, "pages": [
            blank_page([cmd(101, "Oops!")]),
        ]},
    ]


def test_funnel_page_enters_the_scene() -> None:
    ctx = T.TranspileContext(registry=FlagRegistry())
    events = route4()
    ctx.register_map_funnels(76, events)
    text = T.transpile_event(76, events[0], ctx).text
    page1 = text.split("script Map076_EV032_Page1 {")[1].split("}")[0]
    assert page1.rstrip().endswith("release\n    goto(Map076_EV070_TouchEntry)")
    assert "end" not in page1
    # the spent page is untouched
    assert "script Map076_EV032_Page2 {\n    end\n}" in text


def test_unregistered_map_keeps_end() -> None:
    ctx = T.TranspileContext(registry=FlagRegistry())
    text = T.transpile_event(76, route4()[0], ctx).text
    assert "TouchEntry" not in text
