"""Tests for `rpg2gba.ruby_subset.evaluate` (REDERIVATION_PLAN.md C8 stage 2).

Section 1 is hand-picked unit tests, each asserting exact writes/effects for
a specific corpus shape. Section 2 is the real-corpus gate: every distinct
355/655 block and 111 type-12 condition on every event page of every
CH01-CH05 map (same collection discipline as
`test_ruby_subset_parser.py`'s own gate, but NOT de-duplicated by text --
this gate pins refusals to their exact (map, event, page, list_index)
occurrence, so two textually-identical blocks at different sites are two
rows). Section 3 is the §4.7 forward check for `ENGINE_ATTRIBUTES`.
Section 4 is the determinism gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.ruby_subset import ast, parse_expression, parse_program
from rpg2gba.ruby_subset import builtins as bi
from rpg2gba.ruby_subset.parser import script_block_source
from rpg2gba.ruby_subset.evaluate import (
    ConstRef,
    Effect,
    EvalResult,
    FixedOracle,
    Opaque,
    RubyRefusal,
    StateWrite,
    evaluate_expression,
    evaluate_program,
)
from rpg2gba.story_state.state import EngineKey, SelfSwitch, Switch, Variable

REPO = Path(__file__).resolve().parents[1]
MAPS_DIR = REPO / "output" / "uranium-build" / "maps"
COMMON_EVENTS_PATH = REPO / "output" / "uranium-build" / "common_events.json"
CHAPTERS_PATH = REPO / "reference" / "chapters.json"
ENGINE_FLAGS_PATH = REPO / "engine" / "include" / "constants" / "flags.h"


# --- section 1: hand-picked unit tests -------------------------------------


def test_bambo_tally_program_a_array_literal_assign():
    prog = parse_program("$game_variables[151]=[0,0,0]")
    res = evaluate_program(prog, oracle=FixedOracle(), event=None)
    assert res.refusal is None
    assert res.writes == (StateWrite(Variable(151), (0, 0, 0)),)
    assert res.effects == ()


def test_bambo_tally_program_b_index_op_assign_reference_semantics():
    prog = parse_program("pbGet(151)[pbGet(2)] += 1")
    oracle = FixedOracle(reads={Variable(151): [0, 0, 0], Variable(2): 1})
    res = evaluate_program(prog, oracle=oracle, event=None)
    assert res.refusal is None
    assert res.writes == (StateWrite(Variable(151), (0, 1, 0)),)


@pytest.mark.parametrize(
    "var151,expected",
    [
        ([2, 1, 1], 1),  # argmax=2 at index 0 -> x=0 -> elsif x==0 -> x=1
        ([1, 1, 2], 2),  # argmax=2 at index 2 -> x=2 -> neither arm -> x=2
        ([2, 2, 0], 1),  # tie -> lowest index 0 -> x=0 -> elsif x==0 -> x=1
    ],
)
def test_bambo_tally_program_c_argmax_remap(var151, expected):
    text = (
        "x=pbGet(151).index(pbGet(151).max)\n"
        "if x==1\n"
        "x=0\n"
        "elsif x==0\n"
        "x=1\n"
        "end\n"
        "$game_variables[151]=x\n"
        "pbStarterSelector(pbGet(151))"
    )
    prog = parse_program(text)
    oracle = FixedOracle(reads={Variable(151): list(var151)})
    res = evaluate_program(prog, oracle=oracle, event=None)
    assert res.refusal is None
    assert res.writes == (StateWrite(Variable(151), expected),)
    assert len(res.effects) == 1
    assert res.effects[0].name == "pbStarterSelector"
    assert res.effects[0].args == (expected,)


def test_add_pokemon_postfix_if_gate():
    prog = parse_program("pbAddPokemon(PBSpecies::ORCHYNX,5) if $game_variables[151]==1")
    hit = evaluate_program(prog, oracle=FixedOracle(reads={Variable(151): 1}), event=None)
    miss = evaluate_program(prog, oracle=FixedOracle(reads={Variable(151): 2}), event=None)
    assert hit.refusal is None and miss.refusal is None
    assert hit.effects == (
        Effect("pbAddPokemon", (ConstRef("PBSpecies", "ORCHYNX"), 5), hit.effects[0].span),
    )
    assert miss.effects == ()
    assert hit.writes == () and miss.writes == ()


def test_game_switch_postfix_if_single_line():
    prog = parse_program("$game_switches[61] = true if $game_variables[151]==1")
    hit = evaluate_program(prog, oracle=FixedOracle(reads={Variable(151): 1}), event=None)
    miss = evaluate_program(prog, oracle=FixedOracle(reads={Variable(151): 2}), event=None)
    assert hit.writes == (StateWrite(Switch(61), True),)
    assert miss.writes == ()


def test_game_switch_three_line_starter_block():
    text = (
        "$game_switches[59] = true if $game_variables[151]==1\n"
        "$game_switches[60] = true if $game_variables[151]==2\n"
        "$game_switches[61] = true if $game_variables[151]==3"
    )
    prog = parse_program(text)
    res = evaluate_program(prog, oracle=FixedOracle(reads={Variable(151): 2}), event=None)
    assert res.refusal is None
    assert res.writes == (StateWrite(Switch(60), True),)


@pytest.mark.parametrize(
    "var151,expected_x",
    [(1, 2), (2, 0), (3, 1)],
)
def test_decrement_local_postfix_if_reset(var151, expected_x):
    text = "x=pbGet(151)\nx-=2\nx=2 if x==-1\npbStarterSelector(x,true)"
    prog = parse_program(text)
    res = evaluate_program(prog, oracle=FixedOracle(reads={Variable(151): var151}), event=None)
    assert res.refusal is None
    # Brief shorthand ("effect args (2,), (0,), (1,)") names the x-value;
    # the real call also passes the literal `true` second argument, so the
    # full args tuple is (x, True) -- asserted in full here, see report.
    assert res.effects == (Effect("pbStarterSelector", (expected_x, True), res.effects[0].span),)


def test_for_loop_self_switch_range():
    prog = parse_program('for i in 14..18\n   pbSetSelfSwitch(i,"A",true)\nend')
    res = evaluate_program(prog, oracle=FixedOracle(), event=(35, 19))
    assert res.refusal is None
    assert res.writes == tuple(
        StateWrite(SelfSwitch(35, i, "A"), True) for i in range(14, 19)
    )


@pytest.mark.parametrize("choice,expected_var1", [(1, 0), (2, 1)])  # BR_WIN=1, BR_LOSS=2
def test_custom_trainer_battle_real_block(choice, expected_var1):
    # map033/ev039/page1 (Fisherman Brandon's phone rematch), verbatim.
    text = (
        'trainer = createPhoneTrainer(PBTrainers::FISHERMAN,"Brandon",0)\n'
        'result = customTrainerBattle(trainer, "Erh... Other types are good as well...")\n'
        'pbSet(1, result == BR_WIN ? 0 : 1)'
    )
    prog = parse_program(text)
    res = evaluate_program(prog, oracle=FixedOracle(choices=[choice]), event=(33, 39))
    assert res.refusal is None
    assert res.writes == (StateWrite(Variable(1), expected_var1),)
    battle_effects = [e for e in res.effects if e.name == "customTrainerBattle"]
    assert len(battle_effects) == 1
    assert battle_effects[0].args[0] == Opaque(
        "createPhoneTrainer", (ConstRef("PBTrainers", "FISHERMAN"), "Brandon", 0),
    )


def test_engine_attribute_writes():
    running_shoes = evaluate_program(
        parse_program("$PokemonGlobal.runningShoes=true"), oracle=FixedOracle(), event=None,
    )
    pokedex = evaluate_program(
        parse_program("$Trainer.pokedex=true"), oracle=FixedOracle(), event=None,
    )
    assert running_shoes.writes == (StateWrite(EngineKey("running_shoes"), True),)
    assert pokedex.writes == (StateWrite(EngineKey("pokedex"), True),)


def test_need_refresh_is_a_noop():
    res = evaluate_program(
        parse_program("$game_map.need_refresh=true"), oracle=FixedOracle(), event=None,
    )
    assert res.refusal is None
    assert res.writes == ()


def test_party_length_refuses_party_model():
    res = evaluate_program(
        parse_program("$game_variables[43]=$Trainer.party.length"), oracle=FixedOracle(), event=None,
    )
    assert res.refusal is not None
    assert res.refusal.code == "party_model"


def test_nuzlocke_heal_loop_is_a_noop_effect_not_party_model():
    res = evaluate_program(
        parse_program('for i in $Trainer.party\n  i.nuzlocke_heal\nend'),
        oracle=FixedOracle(), event=None,
    )
    assert res.refusal is None
    assert res.effects == (Effect("nuzlocke_heal_party", (), res.effects[0].span),)


def test_system_call_refuses_no_port():
    res = evaluate_program(
        parse_program('system("start http://x")'), oracle=FixedOracle(), event=None,
    )
    assert res.refusal is not None
    assert res.refusal.code == "no_port:system"


def test_unknown_head_refuses_named():
    res = evaluate_program(
        parse_program("totallyUnknownHead(1,2)"), oracle=FixedOracle(), event=None,
    )
    assert res.refusal is not None
    assert res.refusal.code == "ruby_unknown_call:totallyUnknownHead"


def test_randomizer_static_predicate_from_strip_list():
    value, res = evaluate_expression(
        parse_expression("$PokemonGlobal.randomizer"), oracle=FixedOracle(), event=None,
    )
    assert res.refusal is None
    assert value is False


def test_ruby_truthiness_zero_is_truthy():
    res = evaluate_program(
        parse_program("x = 0\n$game_switches[1] = true if x"), oracle=FixedOracle(), event=None,
    )
    assert res.refusal is None
    assert res.writes == (StateWrite(Switch(1), True),)


# --- section 2: real-corpus gate --------------------------------------


pytestmark_corpus = pytest.mark.skipif(
    not MAPS_DIR.is_dir(), reason="output/uranium-build/maps not staged",
)


def _load_common_events_by_id() -> dict[int, dict]:
    """Common events by id, minus strip-listed ones (GTS/VT/LOBBY): a
    stripped CE is never evaluated by any consumer, so the gate skips it too."""
    if not COMMON_EVENTS_PATH.exists():
        return {}
    data = json.loads(COMMON_EVENTS_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
        by_id = {ce["id"]: ce for ce in data if ce}
    else:
        by_id = {int(k): v for k, v in data.items()}
    strip = json.loads((REPO / "reference" / "strip_list.json").read_text(encoding="utf-8"))
    for entry in strip.get("common_events", []):
        by_id.pop(entry["id"], None)
    return by_id


def _ch01_ch05_map_ids() -> list[int]:
    chapters = json.loads(CHAPTERS_PATH.read_text(encoding="utf-8"))
    ids: list[int] = []
    for c in chapters["chapters"]:
        if c.get("id") in ("CH01", "CH02", "CH03", "CH04", "CH05"):
            ids.extend(c.get("maps", []))
    return sorted(set(ids))


def _iter_ruby_sources(commands, ce_by_id, visited_ce):
    """Yields (kind, text, list_index) for every 355/655 block and every 111
    type-12 condition in `commands`, inlining 117 common-event calls once
    each (same discipline as `test_ruby_subset_parser.py`'s corpus walk).
    Unlike that parser gate, this is NOT de-duplicated by text -- this
    evaluate gate pins refusals to their exact (map, event, page,
    list_index) occurrence."""
    i, n = 0, len(commands)
    while i < n:
        cmd = commands[i]
        code = cmd.get("code")
        if code == 355:
            text, j = script_block_source(commands, i)
            yield ("script", text, i)
            i = j
            continue
        if code == 111:
            params = cmd.get("parameters") or []
            if len(params) >= 2 and params[0] == 12:
                yield ("condition", params[1], i)
        if code == 117:
            params = cmd.get("parameters") or []
            if params and params[0] in ce_by_id and params[0] not in visited_ce:
                visited_ce.add(params[0])
                yield from _iter_ruby_sources(
                    ce_by_id[params[0]].get("list") or [], ce_by_id, visited_ce)
        i += 1


class _PermissiveOracle(FixedOracle):
    """The real-corpus gate's oracle: every read defaults per
    `FixedOracle.read` (switches/self-switches False, variables 0, engine
    flags False); every nondeterministic input takes `domain[0]`, the R10
    main path."""

    def choose(self, source):
        return source.domain[0]


def _evaluate_permissive(kind: str, text: str, map_id: int, event_id: int) -> EvalResult:
    """Evaluate one block/condition permissively. A handful of blocks
    (Bambo's tally family) assume `$game_variables[151]` holds an array --
    the brief's own instruction: retry with `var151=[0,0,0]` only for a
    block that actually needed it, detected by the shape of the first
    attempt's own type-error refusal (array/index/iterable), not by
    guessing from the source text up front."""
    oracle = _PermissiveOracle()
    if kind == "script":
        result = evaluate_program(parse_program(text), oracle=oracle, event=(map_id, event_id))
    else:
        _, result = evaluate_expression(parse_expression(text), oracle=oracle, event=(map_id, event_id))
    needs_array_retry = (
        result.refusal is not None
        and result.refusal.code.startswith("ruby_type_error")
        and any(s in result.refusal.detail for s in ("non-array", "not iterable", "non-indexable"))
    )
    if needs_array_retry:
        oracle = _PermissiveOracle(reads={Variable(151): [0, 0, 0]})
        if kind == "script":
            result = evaluate_program(parse_program(text), oracle=oracle, event=(map_id, event_id))
        else:
            _, result = evaluate_expression(
                parse_expression(text), oracle=oracle, event=(map_id, event_id),
            )
    return result


# (map_id, event_id, page_index, list_index, refusal_code) -- measured
# 2026-09-23 against the staged CH01-CH05 corpus. The only allowed code is
# `party_model` (REDERIVATION_PLAN.md C8 shape ruling (b)): $Trainer.party/
# pokedexOwned reached directly or through isRockSmashSoftlocked?/
# jvNextReward/PROFREWARDS[...]. The one `system(...)` call lives in
# strip-listed CE 6 and is no longer walked.
EXPECTED_REFUSALS: tuple[tuple[int, int, int, int, str], ...] = (
    (32, 14, 0, 17, "party_model"),
    (32, 15, 0, 17, "party_model"),
    (32, 33, 0, 17, "party_model"),
    (33, 39, 1, 0, "party_model"),
    (33, 39, 2, 0, "party_model"),
    (33, 53, 1, 0, "party_model"),
    (33, 53, 2, 0, "party_model"),
    (35, 3, 1, 0, "party_model"),
    (35, 3, 2, 0, "party_model"),
    (35, 23, 1, 0, "party_model"),
    (35, 23, 2, 0, "party_model"),
    (49, 1, 2, 2, "party_model"),
    (49, 1, 2, 10, "party_model"),
    (49, 1, 2, 18, "party_model"),
    (50, 5, 5, 6, "party_model"),
    (50, 5, 5, 12, "party_model"),
    (50, 5, 5, 13, "party_model"),
    (50, 5, 6, 0, "party_model"),
    (50, 24, 0, 7, "party_model"),
    (50, 27, 0, 10, "party_model"),
    (68, 1, 0, 14, "party_model"),
    (68, 1, 1, 8, "party_model"),
)


@pytestmark_corpus
def test_ch01_ch05_evaluate_refusal_set_is_pinned():
    ce_by_id = _load_common_events_by_id()
    found: list[tuple[int, int, int, int, str]] = []
    n_runs = 0
    for map_id in _ch01_ch05_map_ids():
        path = MAPS_DIR / f"Map{map_id:03d}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events") or []:
            if event is None:
                continue
            event_id = event.get("id")
            for page_idx, page in enumerate(event.get("pages") or []):
                visited_ce: set[int] = set()
                for kind, text, list_index in list(_iter_ruby_sources(
                    page.get("list") or [], ce_by_id, visited_ce,
                )):
                    n_runs += 1
                    result = _evaluate_permissive(kind, text, map_id, event_id)
                    if result.refusal is not None:
                        found.append((map_id, event_id, page_idx, list_index, result.refusal.code))

    assert n_runs > 0, "expected at least one 355/655 block or 111 condition in CH01-CH05"
    found.sort()
    disallowed = [r for r in found if r[4] != "party_model"]
    assert not disallowed, f"refusal codes other than party_model: {disallowed[:10]}"
    assert tuple(found) == EXPECTED_REFUSALS


# --- section 3: §4.7 forward check for ENGINE_ATTRIBUTES -------------


@pytest.mark.skipif(
    not ENGINE_FLAGS_PATH.exists(), reason="engine/include/constants/flags.h not present",
)
def test_engine_attribute_flags_exist_in_the_fork():
    text = ENGINE_FLAGS_PATH.read_text(encoding="utf-8")
    for (ns, attr), engine_attr in bi.ENGINE_ATTRIBUTES.items():
        assert f"#define {engine_attr.flag}" in text, (
            f"{ns}.{attr} claims native flag {engine_attr.flag!r}, "
            f"not found in {ENGINE_FLAGS_PATH}"
        )


# --- section 4: determinism ---------------------------------------------


@pytest.mark.parametrize(
    "text,kind,reads,choices",
    [
        ("$game_variables[151]=[0,0,0]", "script", {}, []),
        ("x=pbGet(151)\nx-=2\nx=2 if x==-1\npbStarterSelector(x,true)", "script",
         {Variable(151): 2}, []),
        ("$PokemonGlobal.randomizer", "condition", {}, []),
        # a refusal is deterministic too -- same code/detail/span both runs.
        ("$Trainer.party.length", "condition", {}, []),
    ],
)
def test_evaluating_twice_is_deterministic(text, kind, reads, choices):
    if kind == "script":
        node = parse_program(text)
        run = lambda: evaluate_program(  # noqa: E731
            node, oracle=FixedOracle(reads=dict(reads), choices=list(choices)), event=None,
        )
    else:
        node = parse_expression(text)
        run = lambda: evaluate_expression(  # noqa: E731
            node, oracle=FixedOracle(reads=dict(reads), choices=list(choices)), event=None,
        )[1]
    first = run()
    second = run()
    assert first == second
