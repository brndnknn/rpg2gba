"""Name Rater (Map046 EV002) as generic head mappings, plus the Exit Event
Processing (115) release fix that EV002's early exits exposed.

Native flow: engine/data/maps/SlateportCity_NameRatersHouse/scripts.inc.
``special(ChoosePartyMon)`` (party only) rather than ``chooseboxmon``:
``ScriptGetPartyMonSpecies`` indexes ``gPlayerParty[0x8004]`` directly
(field_specials.c:1641) and would read out of bounds on a PC-box pick, while
every other special used here goes through GetSelectedBoxMonFromPcOrParty.
Fixtures are mechanical placeholder strings.
"""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import poryscript
from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

_ELSE = 411
_CHANGED = '$game_variables[5]=="" || $game_variables[5]==pbGet(3)'


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def sc(text: str, indent: int = 0) -> dict:
    return cmd(T.SCRIPT, [text], indent)


def sc_cont(text: str, indent: int = 0) -> dict:
    return cmd(T.SCRIPT_CONT, [text], indent)


def if_script(text: str, indent: int = 0) -> dict:
    return cmd(T.CONDITIONAL_BRANCH, [12, text], indent)


def if_var(var: int, value: int, op: int, indent: int = 0) -> dict:
    return cmd(T.CONDITIONAL_BRANCH, [1, var, 0, value, op], indent)


def text(s: str, indent: int = 0) -> dict:
    return cmd(T.SHOW_TEXT, [s], indent)


END = cmd(T.BRANCH_END)


@pytest.fixture()
def ctx() -> T.TranspileContext:
    return T.TranspileContext(registry=FlagRegistry())


def run(ctx: T.TranspileContext, page: list[dict], trigger: int = 0) -> T.TranspiledEvent:
    ev = {"id": 2, "name": "rater", "x": 0, "y": 0,
          "pages": [{"trigger": trigger, "list": page}]}
    return T.transpile_event(46, ev, ctx)


def flat(res: T.TranspiledEvent) -> str:
    return "\n".join(ln.strip() for ln in res.text.splitlines())


def entry_rows(indent: int = 0) -> list[dict]:
    return [
        sc("pkmn=$Trainer.party[", indent), sc_cont("pbGet(1)]", indent),
        sc_cont("species=PBSpecies.getName(", indent), sc_cont("pkmn.species)", indent),
        sc_cont("pbTextEntry(", indent),
        sc_cont('_I("{1}\'s nickname?",species),', indent),
        sc_cont("0,MAXPOKENAMELENGTH,5,pkmn)", indent),
    ]


def rename_rows(indent: int = 0) -> list[dict]:
    return [sc("pkmn=$Trainer.party[", indent), sc_cont("pbGet(1)]", indent),
            sc_cont("pkmn.name=pbGet(5)", indent)]


def full_page() -> list[dict]:
    """The EV002 control-flow shape with placeholder text."""
    return [
        sc("pbChoosePokemon(1,3)"),
        if_var(1, 0, 4),
        text("bye", 1), cmd(T.EXIT_EVENT, indent=1), END,
        if_script("pbGetPokemon(1).egg?"),
        text("egg", 1), cmd(T.EXIT_EVENT, indent=1), END,
        if_script("pbGetPokemon(1).isForeign?($Trainer)"),
        text("foreign \\v[3] a", 1), text("plain", 1), text("foreign \\v[3] b", 1),
        cmd(T.EXIT_EVENT, indent=1), END,
        text("rate \\v[3]"),
        cmd(T.SHOW_CHOICES, [["Yes", "No"], 2]),
        cmd(T.CHOICE_WHEN, [0, "Yes"]),
        *entry_rows(1),
        if_script(_CHANGED, 1),
        text("same \\v[3]", 2),
        cmd(_ELSE, indent=1),
        *rename_rows(2),
        text("new \\v[5]", 2),
        cmd(T.BRANCH_END, indent=1),
        cmd(T.CHOICE_WHEN, [1, "No"]),
        text("no", 1),
        cmd(T.CHOICES_END),
    ]


def test_name_rater_golden(ctx: T.TranspileContext) -> None:
    res = run(ctx, full_page())
    assert res.unhandled == []
    out = flat(res)
    assert (
        "special(ChoosePartyMon)\n"
        "waitstate\n"
        "if (var(VAR_0x8004) == PARTY_NOTHING_CHOSEN) {\n"
        'msgbox(format("bye"))\n'
        "release\n"
        "end\n"
        "}\n"
        "specialvar(VAR_RESULT, ScriptGetPartyMonSpecies)\n"
        "if (var(VAR_RESULT) == SPECIES_EGG) {\n"
        'msgbox(format("egg"))\n'
        "release\n"
        "end\n"
        "}\n"
        "special(IsMonOTIDNotPlayers)\n"
        "if (var(VAR_RESULT) == FALSE) {\n"
        "specialvar(VAR_RESULT, MonOTNameNotPlayer)\n"
        "}\n"
        "if (var(VAR_RESULT) == TRUE) {\n"
        "special(BufferMonNickname)\n"
        'msgbox(format("foreign {STR_VAR_1} a"))\n'
        'msgbox(format("plain"))\n'
        "special(BufferMonNickname)\n"
        'msgbox(format("foreign {STR_VAR_1} b"))\n'
        "release\n"
        "end\n"
        "}\n"
        "special(BufferMonNickname)\n"
        'msgbox(format("rate {STR_VAR_1}"))\n'
    ) in out
    assert (
        "call(Common_EventScript_NameReceivedPartyMon)\n"
        "specialvar(VAR_RESULT, TryPutNameRaterShowOnTheAir)\n"
        "if (var(VAR_RESULT) == FALSE) {\n"
        "special(BufferMonNickname)\n"
        'msgbox(format("same {STR_VAR_1}"))\n'
        "} else {\n"
        "special(BufferMonNickname)\n"
        'msgbox(format("new {STR_VAR_1}"))\n'
        "}"
    ) in out


def test_name_rater_emits_no_u16_negative_compare_and_no_ruby_var(ctx: T.TranspileContext) -> None:
    res = run(ctx, full_page())
    assert "< 0" not in res.text and "-1" not in res.text
    assert "pkmn" not in res.text and "pbGet" not in res.text


@pytest.mark.parametrize("test,cmp", [
    ((0, -1, 0), "=="), ((2, -1, 0), "=="), ((4, 0, 0), "=="),
])
def test_cancel_forms(ctx: T.TranspileContext, test: tuple, cmp: str) -> None:
    value, op = test[1], test[0]
    res = run(ctx, [sc("pbChoosePokemon(1,3)"), if_var(1, value, op), text("c", 1), END])
    assert f"if (var(VAR_0x8004) {cmp} PARTY_NOTHING_CHOSEN) {{" in res.text


def test_chosen_form_is_inverted_test(ctx: T.TranspileContext) -> None:
    res = run(ctx, [sc("pbChoosePokemon(1,3)"), if_var(1, 0, 1), text("ok", 1), END])
    assert "if (var(VAR_0x8004) != PARTY_NOTHING_CHOSEN) {" in res.text


def test_unrecorded_pick_var_does_not_translate(ctx: T.TranspileContext) -> None:
    """Heads are keyed on the variable the choose recorded; a different one queues."""
    res = run(ctx, [sc("pbChoosePokemon(1,3)"), if_script("pbGetPokemon(2).egg?"),
                    text("egg", 1), END])
    assert any(q.command_code == T.CONDITIONAL_BRANCH for q in res.unhandled)


def test_pick_var_read_elsewhere_queues(ctx: T.TranspileContext) -> None:
    page = [sc("pbChoosePokemon(1,3)"), if_var(1, 3, 3), text("x", 1), END]
    res = run(ctx, page)
    assert "ChoosePartyMon" not in res.text
    assert res.unhandled


def test_unknown_foreign_shape_queues(ctx: T.TranspileContext) -> None:
    page = [sc("pbChoosePokemon(1,3)"), if_script("pbGetPokemon(1).isShadow?"),
            text("x", 1), END]
    res = run(ctx, page)
    assert any(q.command_code == T.CONDITIONAL_BRANCH for q in res.unhandled)


def test_entry_on_unrecorded_mon_queues(ctx: T.TranspileContext) -> None:
    res = run(ctx, entry_rows())  # no preceding pbChoosePokemon
    assert "Common_EventScript_NameReceivedPartyMon" not in res.text
    assert res.unhandled


def test_name_text_with_foreign_var_falls_through_to_queue(ctx: T.TranspileContext) -> None:
    page = [sc("pbChoosePokemon(1,3)"), text("a \\v[9]")]
    res = run(ctx, page)
    assert any(q.command_code == T.SHOW_TEXT for q in res.unhandled)


@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_name_rater_compiles_through_real_poryscript(ctx: T.TranspileContext) -> None:
    res = run(ctx, full_page())
    result = poryscript.compile_script(res.text)
    assert result.ok, result.stderr


# -- code 115 (Exit Event Processing) releases before `end` --------------------


@pytest.mark.parametrize("trigger,expected", [
    (0, ["lock", "faceplayer", "release", "end", "release", "end"]),
    (1, ["lock", "release", "end", "release", "end"]),
    (2, ["lock", "release", "end", "release", "end"]),
    (3, ["lockall", "releaseall", "end", "releaseall", "end"]),
])
def test_exit_event_releases_before_end(ctx: T.TranspileContext, trigger: int,
                                        expected: list[str]) -> None:
    res = run(ctx, [cmd(T.EXIT_EVENT)], trigger=trigger)
    body = [ln.strip() for ln in res.text.splitlines()[2:-1]]
    assert body == expected


def test_exit_event_inside_branch_releases(ctx: T.TranspileContext) -> None:
    res = run(ctx, [if_script("$Trainer.party.length<=0"), cmd(T.EXIT_EVENT, indent=1), END,
                    text("later")])
    assert "release\n        end\n    }" in res.text


def test_exit_event_in_common_event_still_returns(ctx: T.TranspileContext) -> None:
    res = T.transpile_common_event(
        {"id": 7, "name": "ce", "list": [cmd(T.EXIT_EVENT)]}, ctx)
    assert "release" not in res.text
    assert "return" in res.text


def test_exit_event_in_hoisted_region_has_single_release(ctx: T.TranspileContext) -> None:
    """A hoisted label region ending on 115 gets the epilogue once, not twice."""
    page = [
        cmd(T.LABEL, ["Top"]), text("body"), cmd(T.EXIT_EVENT),
    ]
    res = run(ctx, page)
    assert res.text.endswith(
        "script Map046_EV002_Page1_Top {\n"
        '    msgbox(format("body"))\n'
        "    release\n"
        "    end\n"
        "}"
    )
