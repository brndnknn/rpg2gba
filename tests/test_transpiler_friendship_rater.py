"""Friendship rater (Map060 EV042): ``pbChooseNonEggPokemon`` + the exact
happiness-ladder Ruby -> native ChoosePartyMon (egg re-prompt loop) +
``GetPartyMonFriendshipStageRpg2gba`` (engine/src/field_specials.c, Uranium's
thresholds 1/50/100/150/220/255). Fixtures are mechanical placeholder strings.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

_REF = Path(__file__).resolve().parents[1] / "reference"


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def sc(text: str, indent: int = 0) -> dict:
    return cmd(T.SCRIPT, [text], indent)


def sc_cont(text: str, indent: int = 0) -> dict:
    return cmd(T.SCRIPT_CONT, [text], indent)


def if_var(var: int, value: int, op: int, indent: int = 0) -> dict:
    return cmd(T.CONDITIONAL_BRANCH, [1, var, 0, value, op], indent)


def text(s: str, indent: int = 0) -> dict:
    return cmd(T.SHOW_TEXT, [s], indent)


END = cmd(T.BRANCH_END)
LADDER = [(1, 1), (2, 50), (3, 100), (4, 150), (5, 220), (6, 255)]


@pytest.fixture()
def ctx() -> T.TranspileContext:
    registry = FlagRegistry()
    registry.seed_labels(_REF / "uranium_switches.json", _REF / "uranium_variables.json")
    return T.TranspileContext(registry=registry)


def run(ctx: T.TranspileContext, page: list[dict]) -> T.TranspiledEvent:
    ev = {"id": 42, "name": "rater", "x": 0, "y": 0, "pages": [{"trigger": 0, "list": page}]}
    return T.transpile_event(60, ev, ctx)


def flat(res: T.TranspiledEvent) -> str:
    return "\n".join(ln.strip() for ln in res.text.splitlines())


def ladder_rows(ladder: list[tuple[int, int]] = LADDER) -> list[dict]:
    return [
        sc("poke=pbGetPokemon(1)"), sc_cont("h=poke.happiness"), sc_cont("stage=0"),
        *[sc_cont(f"stage={k} if h>={t}") for k, t in ladder],
        sc_cont("pbSet(3,stage)"),
    ]


def page(ladder: list[tuple[int, int]] = LADDER, pick: str = "pbChooseNonEggPokemon(1,2)") -> list[dict]:
    return [
        sc(pick),
        if_var(1, 0, 4),
        text("cancel", 1), cmd(T.EXIT_EVENT, indent=1), END,
        *ladder_rows(ladder),
        if_var(3, 0, 0),
        text("stage zero \\v[2]", 1), END,
        if_var(3, 6, 0),
        text("stage six \\v[2]", 1), END,
    ]


def test_friendship_rater_golden(ctx: T.TranspileContext) -> None:
    res = run(ctx, page())
    assert res.unhandled == []
    out = flat(res)
    var3 = ctx.var_for_variable(3)
    assert var3 is not None
    assert (
        "setvar(VAR_RESULT, SPECIES_EGG)\n"
        "while (var(VAR_RESULT) == SPECIES_EGG) {\n"
        "special(ChoosePartyMon)\n"
        "waitstate\n"
        "setvar(VAR_RESULT, 0)\n"
        "if (var(VAR_0x8004) != PARTY_NOTHING_CHOSEN) {\n"
        "specialvar(VAR_RESULT, ScriptGetPartyMonSpecies)\n"
        "}\n"
        "}\n"
        "if (var(VAR_0x8004) == PARTY_NOTHING_CHOSEN) {\n"
        'msgbox(format("cancel"))\n'
        "release\n"
        "end\n"
        "}\n"
        f"specialvar({var3}, GetPartyMonFriendshipStageRpg2gba)\n"
        f"if (var({var3}) == 0) {{\n"
        "special(BufferMonNickname)\n"
    ) in out
    assert "GetPartyMonFriendshipStageRpg2gba" in out
    assert "happiness" not in out


@pytest.mark.parametrize("bad", [
    # one threshold drifted (200 is stock Emerald's, not Uranium's)
    [(1, 1), (2, 50), (3, 100), (4, 150), (5, 200), (6, 255)],
    # missing final rung
    [(1, 1), (2, 50), (3, 100), (4, 150), (5, 220)],
])
def test_drifted_ladder_still_queues(ctx: T.TranspileContext, bad: list[tuple[int, int]]) -> None:
    res = run(ctx, page(bad))
    assert res.unhandled
    assert "GetPartyMonFriendshipStageRpg2gba" not in res.text


def test_nonegg_pick_with_other_readout_queues(ctx: T.TranspileContext) -> None:
    # Same head, unsupported shape: a bare happiness read, no ladder.
    res = run(ctx, [sc("pbChooseNonEggPokemon(1,2)"), sc("poke=pbGetPokemon(1)"),
                    sc_cont("h=poke.happiness"), sc_cont("pbSet(3,h)")])
    assert res.unhandled
    assert "GetPartyMonFriendshipStageRpg2gba" not in res.text


def test_plain_pick_does_not_take_ladder(ctx: T.TranspileContext) -> None:
    res = run(ctx, page(pick="pbChoosePokemon(1,2)"))
    assert res.unhandled
    assert "GetPartyMonFriendshipStageRpg2gba" not in res.text
