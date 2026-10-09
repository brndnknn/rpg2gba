"""CH06 transpiler heads: pbDeleteItem(:SYM), pbPlayCry, party-length test,
capital-N text break, 207 self-target."""

from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.deterministic import translate_text_codes
from rpg2gba.conversion_agent.flag_registry import FlagRegistry


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


@pytest.fixture()
def ctx() -> T.TranspileContext:
    return T.TranspileContext(registry=FlagRegistry())


def run(ctx: T.TranspileContext, commands: list[dict], event_id: int = 5) -> T.TranspiledEvent:
    ev = {"id": event_id, "name": "npc", "x": 0, "y": 0,
          "pages": [{"trigger": 3, "list": commands}]}
    return T.transpile_event(47, ev, ctx)


# -- 1. pbDeleteItem symbol forms -------------------------------------------


@pytest.mark.parametrize("text", [
    "$PokemonBag.pbDeleteItem(:MARIAKEY)",
    "$PokemonBag.pbDeleteItem(PBItems::MARIAKEY)",
    "$PokemonBag.pbDeleteItem(::PBItems::MARIAKEY)",
])
def test_delete_item_forms(ctx: T.TranspileContext, text: str) -> None:
    ctx.items = {"MARIAKEY": "ITEM_MARIAS_KEY"}
    res = run(ctx, [cmd(T.SCRIPT, [text])])
    assert "removeitem(ITEM_MARIAS_KEY)" in res.text
    assert res.unhandled == []


def test_delete_item_symbol_with_quantity(ctx: T.TranspileContext) -> None:
    ctx.items = {"POTION": "ITEM_POTION"}
    res = run(ctx, [cmd(T.SCRIPT, ["$PokemonBag.pbDeleteItem(:POTION,3)"])])
    assert "removeitem(ITEM_POTION, 3)" in res.text


def test_delete_item_wrapped_across_655_rows(ctx: T.TranspileContext) -> None:
    ctx.items = {"TURTICKET": "ITEM_TUR_TICKET"}
    res = run(ctx, [
        cmd(T.SCRIPT, ["$PokemonBag.pbDeleteItem("]),
        cmd(T.SCRIPT_CONT, ["    PBItems::TURTICKET"]),
        cmd(T.SCRIPT_CONT, ["   )"]),
    ])
    assert "removeitem(ITEM_TUR_TICKET)" in res.text
    assert res.unhandled == []


def test_delete_item_unknown_symbol_queues(ctx: T.TranspileContext) -> None:
    res = run(ctx, [cmd(T.SCRIPT, ["$PokemonBag.pbDeleteItem(:NOSUCH)"])])
    assert "removeitem" not in res.text
    assert len(res.unhandled) == 1


# -- 2. pbPlayCry ------------------------------------------------------------


@pytest.mark.parametrize("text", ["pbPlayCry(PBSpecies::TANCOON)", "pbPlayCry(:TANCOON)"])
def test_play_cry(ctx: T.TranspileContext, text: str) -> None:
    ctx.species = {"TANCOON": "SPECIES_TANCOON"}
    ctx.staged_species = frozenset({"SPECIES_TANCOON"})
    res = run(ctx, [cmd(T.SCRIPT, [text])])
    assert "playmoncry(SPECIES_TANCOON, CRY_MODE_NORMAL)" in res.text
    assert "waitmoncry" in res.text
    assert res.unhandled == []


def test_play_cry_unstaged_species_queues(ctx: T.TranspileContext) -> None:
    ctx.species = {"TANCOON": "SPECIES_TANCOON"}
    res = run(ctx, [cmd(T.SCRIPT, ["pbPlayCry(PBSpecies::TANCOON)"])])
    assert "playmoncry" not in res.text
    assert len(res.unhandled) == 1


# -- 3. $Trainer.party.length condition --------------------------------------


def _party_branch(expr: str) -> list[dict]:
    return [
        cmd(T.CONDITIONAL_BRANCH, [12, expr]),
        cmd(T.CONTROL_SELF_SWITCH, ["A", 0], indent=1),
        cmd(T.ELSE_BRANCH),
        cmd(T.CONTROL_SELF_SWITCH, ["B", 0], indent=1),
        cmd(T.BRANCH_END),
    ]


@pytest.mark.parametrize("expr", [
    "$Trainer.party.length<=0", "$Trainer.party.length==0", "$Trainer.party.length<1",
])
def test_party_length_zero(ctx: T.TranspileContext, expr: str) -> None:
    res = run(ctx, _party_branch(expr))
    assert "getpartysize" in res.text
    assert "if (var(VAR_RESULT) == 0) {" in res.text
    assert "} else {" in res.text
    assert res.unhandled == []


@pytest.mark.parametrize("expr", ["$Trainer.party.length>0", "$Trainer.party.length>=1"])
def test_party_length_nonzero(ctx: T.TranspileContext, expr: str) -> None:
    res = run(ctx, _party_branch(expr))
    assert "if (var(VAR_RESULT) != 0) {" in res.text
    assert res.unhandled == []


def test_party_length_other_comparison_queues(ctx: T.TranspileContext) -> None:
    res = run(ctx, _party_branch("$Trainer.party.length<3"))
    assert "getpartysize" not in res.text
    assert len(res.unhandled) == 1


# -- 4. \N text break --------------------------------------------------------


def test_capital_n_is_a_line_break() -> None:
    raw = "Zzzzzz\\..\\..\\.. muh?\\NIs...\\. someone there...?"
    tr = translate_text_codes(raw)
    assert tr is not None
    assert tr.text == (
        "Zzzzzz{PAUSE 0x0F}.{PAUSE 0x0F}.{PAUSE 0x0F}. muh?\\nIs...{PAUSE 0x0F} someone there...?"
    )


def test_lowercase_n_unchanged() -> None:
    tr = translate_text_codes("a\\nb")
    assert tr is not None and tr.text == "a\\nb"


# -- 5. 207 self target ------------------------------------------------------


def test_show_animation_self_uses_event_id(ctx: T.TranspileContext) -> None:
    res = run(ctx, [cmd(T.SHOW_ANIMATION, [0, 17])], event_id=18)
    assert "applymovement(18, Common_Movement_ExclamationMark)" in res.text
    assert res.unhandled == []
