"""NPC in-game trade (Map046 EV014): ``pbChoosePokemon(v, n, proc{not egg and
species==X})`` plus its "a mon was chosen" test plus ``pbStartTrade(pbGet(v),
PBSpecies::Y, "nick", "ot")`` -> the fork's ``ingame_trade`` flow (event.inc:2684):
``chooseboxmon SELECT_PC_MON_TRADE`` + ``GetTradeSpecies`` re-check +
``CreateInGameTradePokemon`` / ``DoInGameTradeScene``.

The trade row is ``ingame_trades.py``'s single source of truth; the call text is
asserted equal to it. Fixtures are mechanical placeholder strings.
"""
from __future__ import annotations

import pytest

from rpg2gba import ingame_trades as it
from rpg2gba.conversion_agent import poryscript
from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

_ELSE = 411

_CHOOSE = [
    "pbChoosePokemon(1,3,", "proc {|poke|", " !poke.egg? and ",
    "  poke.species==PBSpecies::FARTOG", "})",
]
_TRADE = [
    "pbStartTrade(", "pbGet(1),", "PBSpecies::BAASHAUN,", '"Yuoaman",', '"Baro"', ")",
]


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def script(rows: list[str], indent: int) -> list[dict]:
    return [cmd(T.SCRIPT if k == 0 else T.SCRIPT_CONT, [r], indent) for k, r in enumerate(rows)]


def spec(**over: object) -> it.InGameTradeSpec:
    fields = dict(
        const=it.trade_const(46, 14), map_id=46, event_id=14, page=0,
        species="SPECIES_BAASHAUN", requested_species="SPECIES_FARTOG",
        nickname="Yuoaman", ot_name="Baro", ot_gender=0, personality=1, ot_id=2,
    )
    fields.update(over)
    return it.InGameTradeSpec(**fields)  # type: ignore[arg-type]


@pytest.fixture()
def ctx() -> T.TranspileContext:
    c = T.TranspileContext(registry=FlagRegistry())
    c.species = {"FARTOG": "SPECIES_FARTOG", "BAASHAUN": "SPECIES_BAASHAUN"}
    c.staged_species = frozenset({"SPECIES_FARTOG", "SPECIES_BAASHAUN"})
    s = spec()
    c.ingame_trades = {s.const: s}
    return c


def trade_page(test: list | None = None, trade: list[str] = _TRADE,
               extra: list[dict] | None = None, with_else: bool = False) -> list[dict]:
    page = script(_CHOOSE, 0)
    page.append(cmd(T.CONDITIONAL_BRANCH, test or [1, 1, 0, -1, 5]))
    page += script(trade, 1)
    page.append(cmd(T.SHOW_TEXT, ["traded"], indent=1))
    if with_else:
        page += [cmd(_ELSE), cmd(T.SHOW_TEXT, ["declined"], indent=1)]
    page.append(cmd(T.BRANCH_END))
    page.append(cmd(T.SHOW_TEXT, ["after"]))
    return page + (extra or [])


def run(ctx: T.TranspileContext, page: list[dict], trigger: int = 0) -> T.TranspiledEvent:
    ev = {"id": 14, "name": "trader", "x": 0, "y": 0,
          "pages": [{"trigger": trigger, "list": page}]}
    return T.transpile_event(46, ev, ctx)


def body(res: T.TranspiledEvent) -> str:
    return "\n".join(ln.strip() for ln in res.text.splitlines())


def test_trade_golden(ctx: T.TranspileContext) -> None:
    res = run(ctx, trade_page())
    assert res.unhandled == []
    assert (
        "setvar(VAR_0x8005, INGAME_TRADE_MAP046_EV014)\n"
        "specialvar(VAR_0x8009, GetInGameTradeSpeciesInfo)\n"
        "chooseboxmon(SELECT_PC_MON_TRADE)\n"
        "waitstate\n"
        "setvar(VAR_RESULT, FALSE)\n"
        "if (var(VAR_0x8004) != PARTY_NOTHING_CHOSEN) {\n"
        "specialvar(VAR_0x800B, GetTradeSpecies)\n"
        "if (var(VAR_0x800B) == SPECIES_FARTOG) {\n"
        "setvar(VAR_RESULT, TRUE)\n"
        "}\n"
        "}\n"
        "if (var(VAR_RESULT) == TRUE) {\n"
        "special(CreateInGameTradePokemon)\n"
        "special(DoInGameTradeScene)\n"
        "waitstate\n"
        'msgbox(format("traded"))\n'
        "}\n"
        'msgbox(format("after"))'
    ) in body(res)


def test_trade_never_compares_u16_var_against_minus_one(ctx: T.TranspileContext) -> None:
    res = run(ctx, trade_page())
    assert "-1" not in res.text and "< 0" not in res.text and "> -1" not in res.text


@pytest.mark.parametrize("test", [[1, 1, 0, -1, 5], [1, 1, 0, 0, 1], [1, 1, 0, -1, 3]])
def test_trade_accepts_every_chosen_form(ctx: T.TranspileContext, test: list[int]) -> None:
    res = run(ctx, trade_page(test=test))
    assert res.unhandled == []
    assert "special(CreateInGameTradePokemon)" in res.text


def test_trade_else_arm_emitted_once(ctx: T.TranspileContext) -> None:
    res = run(ctx, trade_page(with_else=True))
    assert res.unhandled == []
    assert res.text.count('msgbox(format("declined"))') == 1
    assert "} else {" in res.text


@pytest.mark.parametrize("over", [
    {"species": "SPECIES_OTHER"},
    {"nickname": "Wrong"},
    {"ot_name": "Other"},
    {"ot_gender": 1},
])
def test_trade_spec_drift_fails_loud(ctx: T.TranspileContext, over: dict) -> None:
    s = spec(**over)
    ctx.ingame_trades = {s.const: s}
    with pytest.raises(ValueError, match="drift"):
        run(ctx, trade_page())


def test_trade_requested_species_drift_fails_loud(ctx: T.TranspileContext) -> None:
    s = spec(requested_species="SPECIES_OTHER")
    ctx.ingame_trades = {s.const: s}
    with pytest.raises(ValueError, match="drift"):
        run(ctx, trade_page())


def test_trade_without_staged_row_queues(ctx: T.TranspileContext) -> None:
    ctx.ingame_trades = {}
    res = run(ctx, trade_page())
    assert any("no staged in-game trade row" in q.description for q in res.unhandled)
    assert "CreateInGameTradePokemon" not in res.text


def test_trade_var_read_elsewhere_queues(ctx: T.TranspileContext) -> None:
    extra = [cmd(T.CONDITIONAL_BRANCH, [1, 1, 0, 3, 3]), cmd(T.SHOW_TEXT, ["x"], 1),
             cmd(T.BRANCH_END)]
    res = run(ctx, trade_page(extra=extra))
    assert res.unhandled  # the pair is not collapsed; rows queue
    assert "CreateInGameTradePokemon" not in res.text
    assert "chooseboxmon" not in res.text


def test_trade_name_var_read_in_text_queues(ctx: T.TranspileContext) -> None:
    res = run(ctx, trade_page(extra=[cmd(T.SHOW_TEXT, ["name \\v[3]"])]))
    assert "CreateInGameTradePokemon" not in res.text


def test_trade_start_outside_chosen_arm_queues(ctx: T.TranspileContext) -> None:
    page = trade_page()
    page += script(_TRADE, 0)  # a second, unguarded pbStartTrade after the pair
    res = run(ctx, page)
    assert any("pbStartTrade" in q.description for q in res.unhandled)


@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_trade_compiles_through_real_poryscript(ctx: T.TranspileContext) -> None:
    res = run(ctx, trade_page(with_else=True))
    result = poryscript.compile_script(res.text)
    assert result.ok, result.stderr
