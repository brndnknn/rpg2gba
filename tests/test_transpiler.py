"""Unit tests for the deterministic event->Poryscript transpiler (BUILD_PLAN §3).

Event/page shape mirrors the Phase-3 deserializer output: an event is
``{id, name, x, y, pages:[...]}`` and each page is ``{trigger, list, ...}``
with ``list`` a sequence of ``{code, indent, parameters}`` commands — same
convention as ``tests/test_deterministic.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, self_switch_flag_name

_REPO_ROOT = Path(__file__).resolve().parents[1]

# ----------------------------------------------------------------------------
# builders
# ----------------------------------------------------------------------------


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_event(
    pages_cmds: list[list[dict]], trigger: int = 0, id: int = 5, name: str = "npc"
) -> dict:
    pages = [{"trigger": trigger, "list": cmds} for cmds in pages_cmds]
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": pages}


# ----------------------------------------------------------------------------
# registry fixture
# ----------------------------------------------------------------------------

_SWITCHES = {
    "1": "Got Starter",
    "2": "Rival Battled",
    "3": "s: time of day check",
    "10": "Switch Ten",
}
_VARIABLES = {
    "1": "Result Var",
    "2": "Other Var",
    "102": "Random Target",
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
# parse_tree
# ----------------------------------------------------------------------------


def test_parse_tree_if_else() -> None:
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [0, 1, 0], indent=0),
        cmd(T.SHOW_TEXT, ["A"], indent=1),
        cmd(T.ELSE_BRANCH, indent=0),
        cmd(T.SHOW_TEXT, ["B"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    nodes = T.parse_tree(commands)
    assert len(nodes) == 1
    node = nodes[0]
    assert isinstance(node, T.IfNode)
    assert len(node.then) == 1 and isinstance(node.then[0], T.TextRun)
    assert node.then[0].text == "A"
    assert node.otherwise is not None
    assert len(node.otherwise) == 1
    assert node.otherwise[0].text == "B"


def test_parse_tree_if_no_else() -> None:
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [0, 1, 0], indent=0),
        cmd(T.SHOW_TEXT, ["A"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    nodes = T.parse_tree(commands)
    node = nodes[0]
    assert isinstance(node, T.IfNode)
    assert node.otherwise is None


def test_parse_tree_nested_ifs() -> None:
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [0, 1, 0], indent=0),
        cmd(T.CONDITIONAL_BRANCH, [0, 2, 0], indent=1),
        cmd(T.SHOW_TEXT, ["inner"], indent=2),
        cmd(T.BRANCH_END, indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    nodes = T.parse_tree(commands)
    outer = nodes[0]
    assert isinstance(outer, T.IfNode)
    assert len(outer.then) == 1
    inner = outer.then[0]
    assert isinstance(inner, T.IfNode)
    assert inner.then[0].text == "inner"


def test_parse_tree_choice_arms_cancel_and_end() -> None:
    commands = [
        cmd(T.SHOW_CHOICES, [["Yes", "No"], 2], indent=0),
        cmd(T.CHOICE_WHEN, [0, "Yes"], indent=0),
        cmd(T.SHOW_TEXT, ["chose yes"], indent=1),
        cmd(T.CHOICE_WHEN, [1, "No"], indent=0),
        cmd(T.SHOW_TEXT, ["chose no"], indent=1),
        cmd(T.CHOICE_CANCEL, indent=0),
        cmd(T.SHOW_TEXT, ["cancelled"], indent=1),
        cmd(T.CHOICES_END, indent=0),
    ]
    nodes = T.parse_tree(commands)
    node = nodes[0]
    assert isinstance(node, T.ChoiceNode)
    assert len(node.arms) == 3
    idx0, text0, children0 = node.arms[0]
    assert idx0 == 0 and text0 == "Yes" and children0[0].text == "chose yes"
    idx1, text1, children1 = node.arms[1]
    assert idx1 == 1 and text1 == "No" and children1[0].text == "chose no"
    idx_cancel, text_cancel, children_cancel = node.arms[2]
    assert idx_cancel is None
    assert children_cancel[0].text == "cancelled"


def test_parse_tree_loop() -> None:
    commands = [
        cmd(T.LOOP, indent=0),
        cmd(T.SHOW_TEXT, ["loop body"], indent=1),
        cmd(T.REPEAT_ABOVE, indent=0),
    ]
    nodes = T.parse_tree(commands)
    node = nodes[0]
    assert isinstance(node, T.LoopNode)
    assert len(node.children) == 1
    assert node.children[0].text == "loop body"


def test_parse_tree_text_continuations_merge() -> None:
    commands = [
        cmd(T.SHOW_TEXT, ["Hello there!"], indent=0),
        cmd(T.SHOW_TEXT_CONT, [" How are"], indent=0),
        cmd(T.SHOW_TEXT_CONT, [" you?"], indent=0),
    ]
    nodes = T.parse_tree(commands)
    assert len(nodes) == 1
    assert isinstance(nodes[0], T.TextRun)
    assert nodes[0].text == "Hello there! How are you?"


def test_parse_tree_blank_rows_disappear() -> None:
    commands = [
        cmd(T.WAIT, [1], indent=0),
        cmd(0, indent=0),
        cmd(T.EXIT_EVENT, indent=0),
    ]
    nodes = T.parse_tree(commands)
    assert len(nodes) == 2
    assert isinstance(nodes[0], T.Leaf) and nodes[0].cmd["code"] == T.WAIT
    assert isinstance(nodes[1], T.Leaf) and nodes[1].cmd["code"] == T.EXIT_EVENT


# ----------------------------------------------------------------------------
# condition_expr
# ----------------------------------------------------------------------------


def test_condition_expr_switch_on_off(ctx: T.TranspileContext) -> None:
    assert T.condition_expr([0, 1, 0], ctx) == "flag(FLAG_GOT_STARTER)"
    assert T.condition_expr([0, 1, 1], ctx) == "!flag(FLAG_GOT_STARTER)"


@pytest.mark.parametrize(
    "opcode,expected",
    [(0, "=="), (1, ">="), (2, "<="), (3, ">"), (4, "<"), (5, "!=")],
)
def test_condition_expr_variable_constant_ops(
    ctx: T.TranspileContext, opcode: int, expected: str
) -> None:
    expr = T.condition_expr([1, 1, 0, 7, opcode], ctx)
    assert expr == f"var(VAR_RESULT_VAR) {expected} 7"


def test_condition_expr_variable_operand(ctx: T.TranspileContext) -> None:
    expr = T.condition_expr([1, 1, 1, 2, 0], ctx)
    assert expr == "var(VAR_RESULT_VAR) == var(VAR_OTHER_VAR)"


def test_condition_expr_self_switch(ctx: T.TranspileContext) -> None:
    ctx.map_id = 49
    ctx.event_id = 5
    expected = self_switch_flag_name(49, 5, "A")
    assert T.condition_expr([2, "A", 0], ctx) == f"flag({expected})"
    assert T.condition_expr([2, "A", 1], ctx) == f"!flag({expected})"


def test_condition_expr_script_and_facing_return_none(ctx: T.TranspileContext) -> None:
    assert T.condition_expr([12, "some.ruby.call"], ctx) is None
    assert T.condition_expr([6, 1, 2], ctx) is None


def test_condition_expr_unnamed_switch_returns_none(ctx: T.TranspileContext) -> None:
    assert T.condition_expr([0, 500, 0], ctx) is None


# ----------------------------------------------------------------------------
# emitters — self-switch (123) and switch range (121)
# ----------------------------------------------------------------------------


def test_self_switch_value_semantics_inverted(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CONTROL_SELF_SWITCH, ["A", 0])]], trigger=1)
    name = self_switch_flag_name(49, 5, "A")
    assert f"setflag({name})" in res.text

    ctx2 = T.TranspileContext(registry=ctx.registry)
    res2 = run_event(ctx2, [[cmd(T.CONTROL_SELF_SWITCH, ["A", 1])]], trigger=1)
    assert f"clearflag({name})" in res2.text


def test_control_switches_range_named(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CONTROL_SWITCHES, [1, 2, 0])]], trigger=1)
    assert "setflag(FLAG_GOT_STARTER)" in res.text
    assert "setflag(FLAG_RIVAL_BATTLED)" in res.text
    assert res.unhandled == []


def test_control_switches_range_with_script_switch_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CONTROL_SWITCHES, [1, 3, 0])]], trigger=1)
    assert "setflag(FLAG_GOT_STARTER)" in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONTROL_SWITCHES
    assert "# UNHANDLED" in res.text


# ----------------------------------------------------------------------------
# emitters — control variables (122)
# ----------------------------------------------------------------------------


def test_control_variables_set_add_sub(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CONTROL_VARIABLES, [1, 1, 0, 0, 5])]], trigger=1)
    assert "setvar(VAR_RESULT_VAR, 5)" in res.text

    ctx2 = T.TranspileContext(registry=ctx.registry)
    res2 = run_event(ctx2, [[cmd(T.CONTROL_VARIABLES, [1, 1, 1, 0, 5])]], trigger=1)
    assert "addvar(VAR_RESULT_VAR, 5)" in res2.text

    ctx3 = T.TranspileContext(registry=ctx.registry)
    res3 = run_event(ctx3, [[cmd(T.CONTROL_VARIABLES, [1, 1, 2, 0, 5])]], trigger=1)
    assert "subvar(VAR_RESULT_VAR, 5)" in res3.text


def test_control_variables_copy_from_variable(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CONTROL_VARIABLES, [1, 1, 0, 1, 2])]], trigger=1)
    assert "copyvar(VAR_RESULT_VAR, VAR_OTHER_VAR)" in res.text


def test_control_variables_mul_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CONTROL_VARIABLES, [1, 1, 3, 0, 5])]], trigger=1)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONTROL_VARIABLES


# ----------------------------------------------------------------------------
# emitters — warp (201)
# ----------------------------------------------------------------------------


def test_warp_emits_map_and_waitstate(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.TRANSFER_PLAYER, [0, 32, 28, 31, 0, 1])]], trigger=1)
    lines = res.text.splitlines()
    assert "    warp(MAP_URANIUM_32, 28, 31)" in lines
    assert "    waitstate" in lines


def test_warp_variable_target_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.TRANSFER_PLAYER, [1, 32, 28, 31, 0, 1])]], trigger=1)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.TRANSFER_PLAYER


# ----------------------------------------------------------------------------
# emitters — move routes (209/210)
# ----------------------------------------------------------------------------


def _route(steps: list[dict], repeat: bool = False) -> dict:
    return {"list": [*steps, {"code": 0}], "repeat": repeat}


def test_move_route_self_target_and_waitmovement(ctx: T.TranspileContext) -> None:
    route = _route([{"code": 1}, {"code": 16}])
    res = run_event(
        ctx,
        [[cmd(T.SET_MOVE_ROUTE, [0, route]), cmd(T.WAIT_MOVE_COMPLETION)]],
        trigger=1,
    )
    label = "Map049_EV005_Page1_Move1"
    assert f"applymovement(5, {label})" in res.text
    assert "waitmovement(0)" in res.text
    assert f"movement {label} {{" in res.text
    assert "    walk_down" in res.text
    assert "    face_down" in res.text
    assert res.unhandled == []


def test_move_route_player_target(ctx: T.TranspileContext) -> None:
    route = _route([{"code": 1}])
    res = run_event(ctx, [[cmd(T.SET_MOVE_ROUTE, [-1, route])]], trigger=1)
    assert "applymovement(OBJ_EVENT_ID_PLAYER, Map049_EV005_Page1_Move1)" in res.text


def test_move_route_out_of_tier_code_queues(ctx: T.TranspileContext) -> None:
    route = _route([{"code": 9}])  # e.g. random-move — outside the tier
    res = run_event(ctx, [[cmd(T.SET_MOVE_ROUTE, [0, route])]], trigger=1)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SET_MOVE_ROUTE


def test_move_route_repeat_queues(ctx: T.TranspileContext) -> None:
    route = _route([{"code": 1}], repeat=True)
    res = run_event(ctx, [[cmd(T.SET_MOVE_ROUTE, [0, route])]], trigger=1)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SET_MOVE_ROUTE


def test_wait_move_completion_neutralized_after_queued_route(ctx: T.TranspileContext) -> None:
    route = _route([{"code": 9}])
    res = run_event(
        ctx,
        [[cmd(T.SET_MOVE_ROUTE, [0, route]), cmd(T.WAIT_MOVE_COMPLETION)]],
        trigger=1,
    )
    assert "waitmovement" not in res.text
    # Only the 209 itself should have queued — the neutralized 210 emits nothing.
    assert len(res.unhandled) == 1


def test_route_wait_step_expands_to_delay_chain() -> None:
    route = _route([{"code": 15, "parameters": [20]}])
    tokens = T.route_tokens(route)
    assert tokens == ["delay_16", "delay_4"]


# ----------------------------------------------------------------------------
# stripped codes
# ----------------------------------------------------------------------------


def test_code_509_silently_stripped(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(509), cmd(T.EXIT_EVENT)]], trigger=1)
    assert res.unhandled == []
    assert "509" not in res.text


@pytest.mark.parametrize("code", [T.CHANGE_TEXT_OPTIONS, T.COMMENT, T.COMMENT_CONT])
def test_stripped_codes_produce_no_output_or_queue(ctx: T.TranspileContext, code: int) -> None:
    res = run_event(ctx, [[cmd(code), cmd(T.EXIT_EVENT)]], trigger=1)
    assert res.unhandled == []
    # trigger 1 (player-touch) with a non-empty body (the explicit EXIT_EVENT
    # "end") now gets lock/release wrapping (no faceplayer).
    assert res.text.splitlines() == [
        "# npc",
        "script Map049_EV005_Page1 {",
        "    lock",
        "    end",
        "    release",
        "    end",
        "}",
    ]


# ----------------------------------------------------------------------------
# misc leaf emitters
# ----------------------------------------------------------------------------


def test_wait_delay(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.WAIT, [6])]], trigger=1)
    assert "delay(6)" in res.text


def test_exit_event_emits_end(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.EXIT_EVENT)]], trigger=1)
    assert res.text.count("end") == 2  # the explicit 115 plus the trailer


def test_erase_event_emits_removeobject(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.ERASE_EVENT)]], trigger=1, event_id=42)
    assert "removeobject(42)" in res.text


def test_call_common_event_zero_padded(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CALL_COMMON_EVENT, [7])]], trigger=1)
    assert "call CommonEvent_007" in res.text


def test_prepare_and_execute_transition(ctx: T.TranspileContext) -> None:
    res = run_event(
        ctx,
        [[cmd(T.PREPARE_TRANSITION), cmd(T.EXECUTE_TRANSITION)]],
        trigger=1,
    )
    assert "fadescreen(FADE_TO_BLACK)" in res.text
    assert "fadescreen(FADE_FROM_BLACK)" in res.text


@pytest.mark.parametrize(
    "rgba,expected",
    [
        ([-255, -255, -255, 0], "FADE_TO_BLACK"),
        ([0, 0, 0, 0], "FADE_FROM_BLACK"),
    ],
)
def test_change_tone_maps_to_fadescreen(
    ctx: T.TranspileContext, rgba: list[int], expected: str
) -> None:
    res = run_event(ctx, [[cmd(T.CHANGE_TONE, [{"rgba": rgba}])]], trigger=1)
    assert f"fadescreen({expected})" in res.text
    assert res.unhandled == []


def test_change_tone_unmapped_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CHANGE_TONE, [{"rgba": [10, 20, 30, 0]}])]], trigger=1)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CHANGE_TONE


def test_recover_all_special(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.RECOVER_ALL)]], trigger=1)
    assert "special(HealPlayerParty)" in res.text


@pytest.mark.parametrize("code", [T.PLAY_SE, T.PLAY_ME, T.PLAY_BGM])
def test_audio_codes_emit_comment_only(ctx: T.TranspileContext, code: int) -> None:
    audio_param = {"name": "se_bump", "volume": 80, "pitch": 100}
    res = run_event(ctx, [[cmd(code, [audio_param])]], trigger=1)
    assert f"# audio (code {code}): se_bump" in res.text
    assert res.unhandled == []


def test_script_strip_set_emits_nothing(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbCallBub(2)"])]], trigger=1)
    assert res.unhandled == []
    assert "pbCallBub" not in res.text


def test_script_unknown_call_queues_with_text(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbItemBall(:POTION)"])]], trigger=1)
    assert len(res.unhandled) == 1
    assert "pbItemBall" in res.unhandled[0].description


# ----------------------------------------------------------------------------
# dialogue text
# ----------------------------------------------------------------------------


def test_text_with_control_code_queues(ctx: T.TranspileContext) -> None:
    # \r (deferred colour shorthand) and \v[n] (variable interpolation) are the
    # codes still outside the approved 2026-07-05 mapping table; \. and trailing
    # \wtnp[n] now translate (tests/test_text_codes.py, test_transpiler_idioms.py).
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, ["wait\\r for it"])]], trigger=1)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_TEXT

    ctx2 = T.TranspileContext(registry=ctx.registry)
    res2 = run_event(ctx2, [[cmd(T.SHOW_TEXT, ["Go! \\v[3]!"])]], trigger=1)
    assert len(res2.unhandled) == 1


def test_text_with_player_name_code(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, ["Hi \\PN!"])]], trigger=1)
    assert 'msgbox("Hi {PLAYER}!")' in res.text
    assert res.unhandled == []


# ----------------------------------------------------------------------------
# YES/NO choice
# ----------------------------------------------------------------------------


def test_yesno_choice_emits_yesnobox_and_branches(ctx: T.TranspileContext) -> None:
    commands = [
        cmd(T.SHOW_CHOICES, [["YES", "NO"], 2], indent=0),
        cmd(T.CHOICE_WHEN, [0, "YES"], indent=0),
        cmd(T.SHOW_TEXT, ["yes path"], indent=1),
        cmd(T.CHOICE_WHEN, [1, "NO"], indent=0),
        cmd(T.SHOW_TEXT, ["no path"], indent=1),
        cmd(T.CHOICES_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=1)
    assert "yesnobox(0, 0)" in res.text
    assert "if (var(VAR_RESULT) == 1) {" in res.text
    assert 'msgbox("yes path")' in res.text
    assert 'msgbox("no path")' in res.text
    assert res.unhandled == []


# ----------------------------------------------------------------------------
# unresolvable 111 condition
# ----------------------------------------------------------------------------


def test_unresolvable_condition_queues_and_hides_branch(ctx: T.TranspileContext) -> None:
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "some.ruby.call"], indent=0),
        cmd(T.SHOW_TEXT, ["SECRET_TEXT_INSIDE_BRANCH"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=1)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "SECRET_TEXT_INSIDE_BRANCH" not in res.text


# ----------------------------------------------------------------------------
# transpile_event wrapper
# ----------------------------------------------------------------------------


def test_trigger_zero_wraps_lock_faceplayer_release(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.WAIT, [1])]], trigger=0)
    lines = [ln.strip() for ln in res.text.splitlines()]
    assert lines == [
        "# npc",
        "script Map049_EV005_Page1 {",
        "lock",
        "faceplayer",
        "delay(1)",
        "release",
        "end",
        "}",
    ]


def test_trigger_zero_empty_body_no_wrapper(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[]], trigger=0)
    lines = [ln.strip() for ln in res.text.splitlines()]
    assert lines == [
        "# npc",
        "script Map049_EV005_Page1 {",
        "end",
        "}",
    ]
    assert "lock" not in res.text
    assert "faceplayer" not in res.text


def test_nonzero_trigger_no_wrapper(ctx: T.TranspileContext) -> None:
    # Only triggers 3/4 (autorun/parallel) get no lock/release wrapping —
    # triggers 1/2 now do (see test_trigger_one_wraps_lock_release_no_faceplayer).
    res = run_event(ctx, [[cmd(T.WAIT, [1])]], trigger=3)
    assert "lock" not in res.text
    assert "faceplayer" not in res.text
    assert "release" not in res.text


def test_trigger_one_wraps_lock_release_no_faceplayer(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.WAIT, [1])]], trigger=1)
    lines = [ln.strip() for ln in res.text.splitlines()]
    assert lines == [
        "# npc",
        "script Map049_EV005_Page1 {",
        "lock",
        "delay(1)",
        "release",
        "end",
        "}",
    ]
    assert "faceplayer" not in res.text


def test_page_label_format(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.WAIT, [1])]], trigger=1, map_id=7, event_id=3, name="Guard")
    assert "script Map007_EV003_Page1 {" in res.text


def test_same_name_events_produce_distinct_labels(ctx: T.TranspileContext) -> None:
    ev1 = make_event([[cmd(T.WAIT, [1])]], trigger=1, id=1, name="Guard")
    ev2 = make_event([[cmd(T.WAIT, [1])]], trigger=1, id=2, name="Guard")
    r1 = T.transpile_event(7, ev1, ctx)
    r2 = T.transpile_event(7, ev2, ctx)
    assert "script Map007_EV001_Page1 {" in r1.text
    assert "script Map007_EV002_Page1 {" in r2.text


def test_movement_block_appended_after_script_block(ctx: T.TranspileContext) -> None:
    route = _route([{"code": 1}])
    res = run_event(ctx, [[cmd(T.SET_MOVE_ROUTE, [0, route])]], trigger=1)
    script_idx = res.text.index("script Map049_EV005_Page1 {")
    movement_idx = res.text.index("movement Map049_EV005_Page1_Move1 {")
    assert script_idx < movement_idx


def test_control_variables_random_operand_with_named_variable(
    ctx: T.TranspileContext,
) -> None:
    res = run_event(ctx, [[cmd(T.CONTROL_VARIABLES, [102, 102, 0, 2, 1, 2])]], trigger=1)
    assert res.unhandled == []
    random_idx = res.text.index("random(2)")
    addvar_idx = res.text.index("addvar(VAR_RESULT, 1)")
    copyvar_idx = res.text.index("copyvar(VAR_RANDOM_TARGET, VAR_RESULT)")
    assert random_idx < addvar_idx < copyvar_idx

    ctx2 = T.TranspileContext(registry=ctx.registry)
    res2 = run_event(ctx2, [[cmd(T.CONTROL_VARIABLES, [102, 102, 0, 2, 0, 2])]], trigger=1)
    assert res2.unhandled == []
    assert "random(3)" in res2.text
    assert "addvar" not in res2.text
    assert "copyvar(VAR_RANDOM_TARGET, VAR_RESULT)" in res2.text


# ----------------------------------------------------------------------------
# QueueEntry
# ----------------------------------------------------------------------------


def test_queue_entry_shape_and_to_json(ctx: T.TranspileContext) -> None:
    ctx.map_id = 49
    ctx.event_id = 5
    ctx.event_name = "npc"
    ctx.page_no = 1
    marker = ctx.queue(3, 999, "test description")
    assert marker == "# UNHANDLED code 999: test description"
    assert len(ctx.unhandled) == 1
    entry = ctx.unhandled[0]
    assert entry.map_id == 49
    assert entry.event_id == 5
    assert entry.event_name == "npc"
    assert entry.page == 1
    assert entry.line == 3
    assert entry.command_code == 999
    assert entry.description == "test description"
    assert entry.reason == "transpiler-unhandled"

    payload = entry.to_json()
    assert payload == {
        "map_id": 49,
        "event_id": 5,
        "event_name": "npc",
        "page": 1,
        "line": 3,
        "command_code": 999,
        "description": "test description",
        "reason": "transpiler-unhandled",
    }


# ----------------------------------------------------------------------------
# real-corpus integration smoke test
# ----------------------------------------------------------------------------

_MAP049_JSON = _REPO_ROOT / "output" / "uranium-build" / "maps" / "Map049.json"
_FLAG_STATE_JSON = _REPO_ROOT / "output" / "uranium-build" / "flag_state.json"


@pytest.mark.skipif(
    not (_MAP049_JSON.is_file() and _FLAG_STATE_JSON.is_file()),
    reason="real corpus data (output/uranium-build) not present",
)
def test_transpile_map049_against_real_corpus() -> None:
    map_data = json.loads(_MAP049_JSON.read_text(encoding="utf-8"))
    reg = FlagRegistry.load(_FLAG_STATE_JSON)
    run_ctx = T.TranspileContext(registry=reg)

    total_unhandled = 0
    for event in map_data["events"]:
        result = T.transpile_event(map_data["map_id"], event, run_ctx)
        total_unhandled += len(result.unhandled)
        for block in result.text.split("\n\n"):
            if not block.strip():
                continue
            assert (
                block.startswith("script ")
                or block.startswith("movement ")
                or block.startswith("# ")
            ), block[:80]

    assert total_unhandled < 40
    assert all(entry.command_code != T.MOVE_COMMAND_ROW for entry in run_ctx.unhandled)
