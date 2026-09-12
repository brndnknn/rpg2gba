"""Unit tests for three transpiler features (REDERIVATION_PLAN.md §14.1
items 2, 4, 6):

* Item 2 — ``isRockSmashSoftlocked?`` static collapse
  (``_ROCK_SMASH_SOFTLOCKED_GUARD_RE`` / ``_emit_rock_smash_softlocked_strip``
  in ``transpiler.py``): statically FALSE on the GBA (gated behind Nuzlocke
  mode, which is already a not-ported, statically-false strip), so the
  then-arm is dropped and the else-arm's children are spliced in directly.
  Same idiom family as ``_emit_nuzlocke_mode_strip`` /
  ``_emit_mystery_gift_id_strip`` (tests/test_transpiler_strips.py).
* Item 4 — ``pbGet``/``pbSet`` literal forms -> ``getvar``/``setvar`` via the
  registry (``_PBSET_LITERAL_RE``/``_PBGET_ASSIGN_LITERAL_RE`` in
  ``_emit_ruby_statement``). Only fully-literal shapes resolve; any computed
  argument queues with a precise reason (no Ruby expression evaluator).
* Item 6 — ``isCustomGame?`` / ``showRulesetSettings`` strips
  (``_CUSTOM_GAME_GUARD_RE`` / ``_emit_custom_game_strip`` for the if-guard
  shape; ``_SHOW_RULESET_SETTINGS_STRIP_RE`` in ``_emit_script_call`` for the
  bare script-call shape). Custom Mode is not ported, so both are statically
  dead on this port.

Event/page shape mirrors ``tests/test_transpiler_strips.py``: an event is
``{id, name, x, y, pages:[...]}`` and each page is ``{trigger, list, ...}``
with ``list`` a sequence of ``{code, indent, parameters}`` commands.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

# ----------------------------------------------------------------------------
# builders
# ----------------------------------------------------------------------------


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_event(
    pages_cmds: list[list[dict]], trigger: int = 3, id: int = 5, name: str = "npc"
) -> dict:
    pages = [{"trigger": trigger, "list": cmds} for cmds in pages_cmds]
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": pages}


_VARIABLES = {
    "1": "Result Var",
    "2": "Other Var",
    # 99 deliberately absent/unnamed for negative-case coverage.
}
_PRESEED_MD = """\
# Pre-seed table

| kind | index | uranium label | constant | notes |
|------|-------|---------------|----------|-------|
| flag | 999 | Preseed Only | FLAG_PRESEED_ONLY | unrelated pre-seed row so pre_seed() has content |
"""


@pytest.fixture()
def registry(tmp_path: Path) -> FlagRegistry:
    switches_path = tmp_path / "uranium_switches.json"
    variables_path = tmp_path / "uranium_variables.json"
    preseed_path = tmp_path / "essentials_to_emerald_map.md"
    switches_path.write_text(json.dumps({}), encoding="utf-8")
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
    trigger: int = 3,
    map_id: int = 49,
    event_id: int = 20,
    name: str = "npc",
) -> T.TranspiledEvent:
    ev = make_event(pages_cmds, trigger=trigger, id=event_id, name=name)
    return T.transpile_event(map_id, ev, ctx)


def _guard_commands(
    condition: str,
    then_body: list[dict],
    else_body: list[dict] | None = None,
) -> list[dict]:
    cmds = [cmd(T.CONDITIONAL_BRANCH, [12, condition], indent=0)]
    cmds += [dict(c, indent=1) for c in then_body]
    if else_body is not None:
        cmds.append(cmd(T.ELSE_BRANCH, indent=0))
        cmds += [dict(c, indent=1) for c in else_body]
    cmds.append(cmd(T.BRANCH_END, indent=0))
    return cmds


# ----------------------------------------------------------------------------
# Item 2 — isRockSmashSoftlocked? static collapse
# ----------------------------------------------------------------------------


def test_rock_smash_softlocked_empty_else_drops_then_arm(ctx: T.TranspileContext) -> None:
    commands = _guard_commands(
        "isRockSmashSoftlocked?", [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])]
    )
    res = run_event(ctx, [commands], map_id=32, event_id=20)
    assert res.unhandled == []
    assert "# isRockSmashSoftlocked?: unsatisfiable on GBA" in res.text
    assert "setflag" not in res.text


def test_rock_smash_softlocked_with_else_emits_else_children_inline(
    ctx: T.TranspileContext,
) -> None:
    commands = _guard_commands(
        "isRockSmashSoftlocked?",
        then_body=[cmd(T.SCRIPT, ["pbEraseThisEvent"])],
        else_body=[cmd(T.CONTROL_SELF_SWITCH, ["B", 0])],
    )
    res = run_event(ctx, [commands], map_id=32, event_id=20)
    assert res.unhandled == []
    assert "# isRockSmashSoftlocked?: unsatisfiable on GBA" in res.text
    assert "if (" not in res.text
    assert "} else {" not in res.text


@pytest.mark.parametrize(
    "condition",
    [
        "isRockSmashSoftlocked",  # missing the trailing '?'
        "!isRockSmashSoftlocked?",  # negated — different shape
        "isRockSmashSoftlocked?(true)",  # unexpected argument
    ],
)
def test_rock_smash_softlocked_near_miss_still_queues(
    ctx: T.TranspileContext, condition: str
) -> None:
    commands = _guard_commands(condition, [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])])
    res = run_event(ctx, [commands], map_id=32, event_id=20)
    assert len(res.unhandled) == 1
    assert "# isRockSmashSoftlocked?" not in res.text


# ----------------------------------------------------------------------------
# Item 6 — isCustomGame? / showRulesetSettings strips
# ----------------------------------------------------------------------------


def test_custom_game_guard_drops_then_arm(ctx: T.TranspileContext) -> None:
    commands = _guard_commands(
        "isCustomGame?", [cmd(T.SCRIPT, ["pbCallBub(2)"])]
    )
    res = run_event(ctx, [commands], map_id=50, event_id=5)
    assert res.unhandled == []
    assert "# isCustomGame?: Custom Mode not ported" in res.text
    assert "pbCallBub" not in res.text


def test_custom_game_guard_with_else_emits_else_children_inline(
    ctx: T.TranspileContext,
) -> None:
    commands = _guard_commands(
        "isCustomGame?",
        then_body=[cmd(T.CONTROL_SELF_SWITCH, ["A", 0])],
        else_body=[cmd(T.CONTROL_SELF_SWITCH, ["B", 0])],
    )
    res = run_event(ctx, [commands], map_id=50, event_id=5)
    assert res.unhandled == []
    assert "if (" not in res.text
    assert "} else {" not in res.text


@pytest.mark.parametrize(
    "condition",
    [
        "isCustomGame",  # missing '?'
        "isCustomGame?(true)",  # the any=true form — not covered
        "!isCustomGame?",  # negated
    ],
)
def test_custom_game_guard_near_miss_still_queues(
    ctx: T.TranspileContext, condition: str
) -> None:
    commands = _guard_commands(condition, [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])])
    res = run_event(ctx, [commands], map_id=50, event_id=5)
    assert len(res.unhandled) == 1
    assert "# isCustomGame?" not in res.text


def test_show_ruleset_settings_strips_bare_call(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["showRulesetSettings(1)"])]])
    assert res.unhandled == []
    assert "# custom mode: showRulesetSettings stripped" in res.text


def test_show_ruleset_settings_near_miss_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["showRulesetSettings(1,2)"])]])
    assert len(res.unhandled) == 1
    assert "# custom mode" not in res.text


# ----------------------------------------------------------------------------
# Item 4 — pbGet/pbSet literal forms
# ----------------------------------------------------------------------------


def test_pbset_literal_emits_setvar(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbSet(1, 7)"])]])
    assert res.unhandled == []
    assert "setvar(VAR_RESULT_VAR, 7)" in res.text


def test_pbset_literal_unnamed_variable_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbSet(99, 7)"])]])
    assert len(res.unhandled) == 1
    assert "unnamed" in res.unhandled[0].description
    assert "setvar" not in res.text


def test_pbset_computed_argument_queues_with_precise_reason(
    ctx: T.TranspileContext,
) -> None:
    res = run_event(
        ctx, [[cmd(T.SCRIPT, ["pbSet(1, result == BR_WIN ? 0 : 1)"])]]
    )
    assert len(res.unhandled) == 1
    assert "computed argument" in res.unhandled[0].description
    assert "setvar" not in res.text


def test_pbget_assign_literal_emits_copyvar(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["$game_variables[2]=pbGet(1)"])]])
    assert res.unhandled == []
    assert "copyvar(VAR_OTHER_VAR, VAR_RESULT_VAR)" in res.text


def test_pbget_assign_literal_unnamed_variable_queues(
    ctx: T.TranspileContext,
) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["$game_variables[99]=pbGet(1)"])]])
    assert len(res.unhandled) == 1
    assert "unnamed" in res.unhandled[0].description
    assert "copyvar" not in res.text


def test_pbget_computed_argument_queues_with_precise_reason(
    ctx: T.TranspileContext,
) -> None:
    res = run_event(
        ctx, [[cmd(T.SCRIPT, ["item=[:OWTEN,:KINETMUNK][pbGet(1)]"])]]
    )
    assert len(res.unhandled) == 1
    assert "no expression evaluator" in res.unhandled[0].description
    assert "copyvar" not in res.text
