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
    "59": "Has Raptorch",
    "60": "Has Eletux",
    "61": "Has Orchynx",
}
_VARIABLES = {
    "1": "Result Var",
    "2": "Other Var",
    "102": "Random Target",
    "200": "Temp Move Choice",
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


def test_parse_tree_text_continuations_merge_no_leading_spaces() -> None:
    """Realistic corpus-shaped data: continuations carry NO leading space (unlike
    the fixture above, which hand-wrote them and so passed for the wrong reason --
    the naive "".join assumption this pins is false for ~1320 corpus cases).
    Modeled on the real shipped Map033 event 34 Trainer(4) line."""
    commands = [
        cmd(T.SHOW_TEXT, ["Oh! Hey! I just got a new Pokémon and I want to"], indent=0),
        cmd(T.SHOW_TEXT_CONT, ["see how it fares!"], indent=0),
    ]
    nodes = T.parse_tree(commands)
    assert len(nodes) == 1
    assert isinstance(nodes[0], T.TextRun)
    assert "want to see how it fares!" in nodes[0].text


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


def test_condition_expr_variable_operand_queues(ctx: T.TranspileContext) -> None:
    """`var(X) OP var(Y)` doesn't compile in poryscript (verified against the
    real binary: "expected next token to be '{', got ')'") — queue, don't emit."""
    expr = T.condition_expr([1, 1, 1, 2, 0], ctx)
    assert expr is None


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


def test_warp_retain_direction_emits_bare_warp(ctx: T.TranspileContext) -> None:
    # RMXP direction 0 ("retain facing"): no facing special — the engine keeps
    # the player's facing across a script warp (RPG2GBA_WARP_RETAIN_FACING).
    res = run_event(ctx, [[cmd(T.TRANSFER_PLAYER, [0, 32, 28, 31, 0, 1])]], trigger=1)
    assert "SetWarpArrivalFacing" not in res.text
    assert "VAR_0x8004" not in res.text


@pytest.mark.parametrize(
    ("direction", "dir_const"),
    [(2, "DIR_SOUTH"), (4, "DIR_WEST"), (6, "DIR_EAST"), (8, "DIR_NORTH")],
)
def test_warp_explicit_direction_sets_arrival_facing(
    ctx: T.TranspileContext, direction: int, dir_const: str,
) -> None:
    # An explicit RMXP direction sets the pending arrival facing immediately
    # before the warp consumes it (WARP_RETAIN_FACING_PROPOSAL.md §0 R3).
    res = run_event(
        ctx, [[cmd(T.TRANSFER_PLAYER, [0, 49, 6, 8, direction, 1])]], trigger=1,
    )
    lines = [ln.strip() for ln in res.text.splitlines()]
    i = lines.index(f"setvar(VAR_0x8004, {dir_const})")
    assert lines[i:i + 4] == [
        f"setvar(VAR_0x8004, {dir_const})",
        "special(SetWarpArrivalFacing)",
        "warp(MAP_URANIUM_49, 6, 8)",
        "waitstate",
    ]
    assert not res.unhandled


def test_warp_unknown_direction_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.TRANSFER_PLAYER, [0, 32, 28, 31, 5, 1])]], trigger=1)
    assert "warp(" not in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.TRANSFER_PLAYER
    assert "unknown direction 5" in res.unhandled[0].description


def test_warp_variable_target_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.TRANSFER_PLAYER, [1, 32, 28, 31, 0, 1])]], trigger=1)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.TRANSFER_PLAYER


def test_warp_unconditional_state_write_after_is_hoisted(ctx: T.TranspileContext) -> None:
    # RMXP keeps running after Transfer Player; the fork's warp halts the
    # script (ScrCmd_warp/DoWarp), so a same-level unconditional switch
    # write after the transfer must move ahead of the warp instead of
    # becoming dead code (the NurseTut FLAG_NURSE_TUTORIAL bug).
    res = run_event(
        ctx,
        [[
            cmd(T.TRANSFER_PLAYER, [0, 32, 28, 31, 0, 1]),
            cmd(T.CONTROL_SWITCHES, [1, 1, 0]),
        ]],
        trigger=1,
    )
    lines = [ln.strip() for ln in res.text.splitlines()]
    assert lines.index("setflag(FLAG_GOT_STARTER)") < lines.index(
        "warp(MAP_URANIUM_32, 28, 31)"
    )
    assert not res.unhandled


def test_warp_state_write_inside_conditional_after_is_not_hoisted(
    ctx: T.TranspileContext,
) -> None:
    # A write nested in a branch after the warp must NOT be hoisted — its
    # guard may not hold — and must surface as a queue entry, not be
    # silently emitted as dead code.
    res = run_event(
        ctx,
        [[
            cmd(T.TRANSFER_PLAYER, [0, 32, 28, 31, 0, 1]),
            cmd(T.CONDITIONAL_BRANCH, [0, 1, 0], indent=0),
            cmd(T.CONTROL_SWITCHES, [1, 1, 0], indent=1),
            cmd(T.BRANCH_END, indent=0),
        ]],
        trigger=1,
    )
    assert "setflag(FLAG_GOT_STARTER)" not in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "follows a Transfer Player warp" in res.unhandled[0].description


def test_warp_dialogue_after_is_queued_not_emitted(ctx: T.TranspileContext) -> None:
    res = run_event(
        ctx,
        [[
            cmd(T.TRANSFER_PLAYER, [0, 32, 28, 31, 0, 1]),
            cmd(T.SHOW_TEXT, ["unreachable"]),
        ]],
        trigger=1,
    )
    assert "msgbox" not in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_TEXT
    assert "follows a Transfer Player warp" in res.unhandled[0].description


def test_warp_with_nothing_after_is_unchanged(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.TRANSFER_PLAYER, [0, 32, 28, 31, 0, 1])]], trigger=1)
    lines = res.text.splitlines()
    assert "    warp(MAP_URANIUM_32, 28, 31)" in lines
    assert "    waitstate" in lines
    assert not res.unhandled


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
# emitters — terminal hide -> removeobject (Map050 EV020 ghost-collision fix)
# ----------------------------------------------------------------------------


def test_terminal_hide_emits_removeobject_after_waitmovement(
    ctx: T.TranspileContext,
) -> None:
    """A route ending in opacity 0 with no later restore is a permanent
    hide — the object must be despawned or it leaves a solid, invisible
    ghost blocking its tile (root cause of the Map050 EV020 stuck tile)."""
    route = _route([{"code": 1}, {"code": 42, "parameters": [0]}])
    res = run_event(
        ctx,
        [[cmd(T.SET_MOVE_ROUTE, [20, route]), cmd(T.WAIT_MOVE_COMPLETION)]],
        trigger=1,
    )
    lines = [ln.strip() for ln in res.text.splitlines()]
    label = "Map049_EV005_Page1_Move1"
    i = lines.index(f"applymovement(20, {label})")
    assert lines[i + 1] == "waitmovement(0)"
    assert lines[i + 2] == f"setflag({T.TERMINAL_HIDE_FLAG_PLACEHOLDER})"
    assert lines[i + 3] == "removeobject(20)"
    assert res.unhandled == []


def test_terminal_hide_records_trait_keyed_by_hidden_event_not_scripting_event(
    ctx: T.TranspileContext,
) -> None:
    """Regression: after the Map050 starter ceremony, Theo/the professor
    reappeared on the player's first step because the object TEMPLATE's flag
    was the "0" null sentinel — TrySpawnObjectEvents' `!FlagGet(flagId)`
    respawn gate always passed. The fix records a `terminal_hide` trait
    keyed by (map, the HIDDEN event's id) — event 20 here — even though the
    scripting event (which run_event defaults to id 5) is a different event.

    The transpiler does NOT mint a flag itself — which flag belongs here (a
    fresh FLAG_HIDE_* vs. an existing rock/hidden-actor FLAG_TEMP_* it must
    reuse) is a decision only metadata_wiring.build_object_events can make,
    downstream, once the whole map's visibility-flag pool is known. So the
    emitted `setflag` names the shared placeholder token, resolved later by
    metadata_wiring.resolve_terminal_hide_setflags during staging."""
    route = _route([{"code": 1}, {"code": 42, "parameters": [0]}])
    res = run_event(
        ctx,
        [[cmd(T.SET_MOVE_ROUTE, [20, route]), cmd(T.WAIT_MOVE_COMPLETION)]],
        trigger=1,
        map_id=50,
        event_id=5,
    )
    assert ctx.traits == {(50, 20): {"terminal_hide"}}
    assert f"setflag({T.TERMINAL_HIDE_FLAG_PLACEHOLDER})" in res.text
    # The transpiler never mints anything for this idiom — no hide_flags
    # entries should appear in the registry state at all.
    assert ctx.registry.to_state()["hide_flags"] == {}


def test_terminal_hide_synthesizes_waitmovement_if_missing(
    ctx: T.TranspileContext,
) -> None:
    """If the paired 210 (Wait For Move Completion) wasn't emitted, the
    removeobject pass must still not fire mid-walk — it synthesizes the
    wait rather than despawning the object before its movement plays out."""
    route = _route([{"code": 1}, {"code": 42, "parameters": [0]}])
    res = run_event(ctx, [[cmd(T.SET_MOVE_ROUTE, [20, route])]], trigger=1)
    lines = [ln.strip() for ln in res.text.splitlines()]
    label = "Map049_EV005_Page1_Move1"
    i = lines.index(f"applymovement(20, {label})")
    assert lines[i + 1] == "waitmovement(0)"
    assert lines[i + 2] == f"setflag({T.TERMINAL_HIDE_FLAG_PLACEHOLDER})"
    assert lines[i + 3] == "removeobject(20)"


def test_hide_reveal_idiom_does_not_emit_removeobject(ctx: T.TranspileContext) -> None:
    """A transient hide (opacity 0) followed later in the same page by a
    restore (opacity 255) for the same target is the Map032/Map049 idiom —
    must be left alone, no removeobject."""
    hide_route = _route([{"code": 1}, {"code": 42, "parameters": [0]}])
    reveal_route = _route([{"code": 42, "parameters": [255]}])
    res = run_event(
        ctx,
        [[
            cmd(T.SET_MOVE_ROUTE, [20, hide_route]),
            cmd(T.WAIT_MOVE_COMPLETION),
            cmd(T.SET_MOVE_ROUTE, [20, reveal_route]),
            cmd(T.WAIT_MOVE_COMPLETION),
        ]],
        trigger=1,
    )
    assert "removeobject" not in res.text
    assert "setflag" not in res.text
    assert ctx.traits == {}


def test_terminal_hide_of_player_never_emits_removeobject(
    ctx: T.TranspileContext,
) -> None:
    """The player is never a valid removeobject target, even if a route
    hides them with no later restore."""
    route = _route([{"code": 1}, {"code": 42, "parameters": [0]}])
    res = run_event(
        ctx,
        [[cmd(T.SET_MOVE_ROUTE, [-1, route]), cmd(T.WAIT_MOVE_COMPLETION)]],
        trigger=1,
    )
    assert "removeobject" not in res.text
    assert "setflag" not in res.text
    assert "set_invisible" in res.text
    assert ctx.traits == {}


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
    # "end") now gets lock/release wrapping (no faceplayer). Expectation
    # changed 2026-10-09: the early exit emits the page's `release` BEFORE its
    # `end` (the closing release is skipped by `end`, which left the player
    # frozen on every early exit), so the body reads lock/release/end.
    assert res.text.splitlines() == [
        "# npc",
        "script Map049_EV005_Page1 {",
        "    lock",
        "    release",
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
    assert "call(CommonEvent_007)" in res.text


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


def test_party_length_assignment_emits_specialvar(ctx: T.TranspileContext) -> None:
    # "Random Target" (variable 102) is pre-seeded by the registry fixture ->
    # VAR_RANDOM_TARGET (Map068 EV001 shape, real var is 43 but any registry-
    # resolved id exercises the idiom identically).
    res = run_event(
        ctx,
        [[cmd(T.SCRIPT, ["$game_variables[102]=$Trainer.party.length"])]],
        trigger=1,
    )
    assert res.unhandled == []
    assert "specialvar(VAR_RANDOM_TARGET, CalculatePlayerPartyCount)" in res.text


def test_party_length_assignment_queues_when_variable_unresolved(
    ctx: T.TranspileContext,
) -> None:
    # Variable 44 is genuinely unnamed in reference/uranium_variables.json, so
    # var_for_variable(44) returns None and the row must keep queueing rather
    # than emit a scratch/invented VAR_* (CLAUDE.md §4.5/§6).
    #
    # Deliberately NOT variable 43 (the real corpus id at Map068 EV001): 43 is
    # labelled "Reserved - Pokemon Count" upstream and resolves to
    # VAR_RESERVED_POKEMON_COUNT once the registry is seeded, so using it here
    # would assert the opposite of production behaviour (2026-08-19).
    res = run_event(
        ctx,
        [[cmd(T.SCRIPT, ["$game_variables[44]=$Trainer.party.length"])]],
        trigger=1,
    )
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SCRIPT
    assert "specialvar" not in res.text


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
    assert 'msgbox(format("Hi {PLAYER}!"))' in res.text
    assert res.unhandled == []


def test_blue_text_code_stripped_lowercase_and_uppercase(
    ctx: T.TranspileContext,
) -> None:
    # \b/\B is Essentials' whole-line blue-tint colour code (gsub to
    # <c2=6546675A>, mirroring \r's red <c2=043C675A>) — no gameplay meaning,
    # so it's dropped rather than reproduced (design decision 2026-08-19, see
    # _BLUE_TEXT_CODE_RE). Real occurrence: Map067 EV009 "Deliveryman" page 2.
    res = run_event(
        ctx, [[cmd(T.SHOW_TEXT, ["\\bWe look forward to your next visit."])]],
        trigger=1,
    )
    assert res.unhandled == []
    assert 'msgbox(format("We look forward to your next visit."))' in res.text

    ctx2 = T.TranspileContext(registry=ctx.registry)
    res2 = run_event(
        ctx2, [[cmd(T.SHOW_TEXT, ["\\BHello there!"])]], trigger=1,
    )
    assert res2.unhandled == []
    assert 'msgbox(format("Hello there!"))' in res2.text


def test_other_control_code_still_queues_alongside_blue(
    ctx: T.TranspileContext,
) -> None:
    # \b is handled specifically, not as a general "strip unknown backslash
    # codes" change — \r right after it must still queue the whole line.
    res = run_event(
        ctx, [[cmd(T.SHOW_TEXT, ["\\bwait\\r for it"])]], trigger=1,
    )
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_TEXT


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
    assert 'msgbox(format("yes path"))' in res.text
    assert 'msgbox(format("no path"))' in res.text
    assert res.unhandled == []


def test_two_arm_choice_custom_labels_emits_yesnobox(ctx: T.TranspileContext) -> None:
    """Any 2-way choice maps to yesnobox, regardless of the choice labels —
    dropping custom-labeled arms is the bug that shipped a broken autorun
    loop (arms held the self-switch deactivation writes)."""
    commands = [
        cmd(T.SHOW_CHOICES, [["Yes!", "Wait a minute..."], 2], indent=0),
        cmd(T.CHOICE_WHEN, [0, "Yes!"], indent=0),
        cmd(T.CONTROL_SELF_SWITCH, ["C", 0], indent=1),
        cmd(T.CHOICE_WHEN, [1, "Wait a minute..."], indent=0),
        cmd(T.CONTROL_SELF_SWITCH, ["D", 0], indent=1),
        cmd(T.CHOICES_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=1)
    name_c = self_switch_flag_name(49, 5, "C")
    name_d = self_switch_flag_name(49, 5, "D")
    assert "yesnobox(0, 0)" in res.text
    assert f"setflag({name_c})" in res.text
    assert f"setflag({name_d})" in res.text
    assert res.unhandled == []


def test_three_arm_choice_still_queued(ctx: T.TranspileContext) -> None:
    commands = [
        cmd(T.SHOW_CHOICES, [["A", "B", "C"], 3], indent=0),
        cmd(T.CHOICE_WHEN, [0, "A"], indent=0),
        cmd(T.SHOW_TEXT, ["a path"], indent=1),
        cmd(T.CHOICE_WHEN, [1, "B"], indent=0),
        cmd(T.SHOW_TEXT, ["b path"], indent=1),
        cmd(T.CHOICE_WHEN, [2, "C"], indent=0),
        cmd(T.SHOW_TEXT, ["c path"], indent=1),
        cmd(T.CHOICES_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=1)
    assert "yesnobox" not in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_CHOICES


def test_two_arm_choice_with_cancel_arm_lands_in_else(ctx: T.TranspileContext) -> None:
    commands = [
        cmd(T.SHOW_CHOICES, [["Yes!", "Nevermind"], 1], indent=0),
        cmd(T.CHOICE_WHEN, [0, "Yes!"], indent=0),
        cmd(T.SHOW_TEXT, ["yes path"], indent=1),
        cmd(T.CHOICE_CANCEL, indent=0),
        cmd(T.SHOW_TEXT, ["cancel path"], indent=1),
        cmd(T.CHOICES_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=1)
    assert "yesnobox(0, 0)" in res.text
    assert res.unhandled == []
    then_idx = res.text.index("if (var(VAR_RESULT) == 1) {")
    else_idx = res.text.index("} else {")
    yes_idx = res.text.index('msgbox(format("yes path"))')
    cancel_idx = res.text.index('msgbox(format("cancel path"))')
    assert then_idx < yes_idx < else_idx < cancel_idx


# ----------------------------------------------------------------------------
# inline \ch[...] choice escape (SLICE1_TODO #17)
# ----------------------------------------------------------------------------

# Real corpus text, Map050 EV005 Q1 (the aptitude test) — the registry fixture
# names variable 200 "Temp Move Choice" (-> VAR_TEMP_MOVE_CHOICE) rather than
# reusing variable id 2 (already claimed by "Other Var" -> VAR_OTHER_VAR
# elsewhere in this fixture); the \ch parsing logic under test doesn't care
# which id resolves, only that it does.
_CH_Q1_TEXT = (
    "When you encounter a new\\nkind of Pokémon in the wild,\\n"
    "what is your first reaction?"
    "\\ch[200,0,<c2=043c3aff>Attack it right away!,"
    "\\c[4]Wait and see what it does.,"
    "<c2=65467b14>Throw a Poké Ball at it!]"
)


def test_inline_choice_emits_msgbox_dynmultichoice_and_text_blocks(
    ctx: T.TranspileContext,
) -> None:
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, [_CH_Q1_TEXT])]], trigger=0)
    assert res.unhandled == []
    assert "your first reaction?" in res.text
    assert (
        "dynmultichoice(0, 0, TRUE, 6, 0, DYN_MULTICHOICE_CB_NONE, "
        "Map049_EV005_Page1_Choice1_Opt0, Map049_EV005_Page1_Choice1_Opt1, "
        "Map049_EV005_Page1_Choice1_Opt2)"
    ) in res.text
    assert "copyvar(VAR_TEMP_MOVE_CHOICE, VAR_RESULT)" in res.text
    assert (
        "text Map049_EV005_Page1_Choice1_Opt0 {\n"
        '    format("Attack it right away!")\n}'
    ) in res.text
    assert (
        "text Map049_EV005_Page1_Choice1_Opt1 {\n"
        '    format("Wait and see what it does.")\n}'
    ) in res.text
    assert (
        "text Map049_EV005_Page1_Choice1_Opt2 {\n"
        '    format("Throw a Poké Ball at it!")\n}'
    ) in res.text


def test_inline_choice_positive_ifcancel_branches_on_multi_b_pressed(
    ctx: T.TranspileContext,
) -> None:
    text = "Pick one?\\ch[200,3,First,Second]"
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, [text])]], trigger=0)
    assert res.unhandled == []
    assert (
        "dynmultichoice(0, 0, FALSE, 6, 0, DYN_MULTICHOICE_CB_NONE, "
        "Map049_EV005_Page1_Choice1_Opt0, Map049_EV005_Page1_Choice1_Opt1)"
    ) in res.text
    assert "if (var(VAR_RESULT) == MULTI_B_PRESSED) {" in res.text
    assert "    setvar(VAR_TEMP_MOVE_CHOICE, 2)" in res.text
    assert "} else {" in res.text
    assert "    copyvar(VAR_TEMP_MOVE_CHOICE, VAR_RESULT)" in res.text


def test_inline_choice_minus_two_ifcancel_still_queues(ctx: T.TranspileContext) -> None:
    """Only ifCancel == -1 gets the 0x7FFF cancel sentinel (2026-10-09); any
    other negative still queues. (This test was `-1` and asserted a queue
    until the sentinel landed; -1 is covered in test_transpiler_idioms.py.)"""
    text = "Pick one?\\ch[200,-2,First,Second]"
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, [text])]], trigger=0)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_TEXT
    assert "dynmultichoice" not in res.text


def test_inline_choice_unresolvable_var_queues(ctx: T.TranspileContext) -> None:
    text = "Pick one?\\ch[999,0,First,Second]"
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, [text])]], trigger=0)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_TEXT
    assert "dynmultichoice" not in res.text


def test_inline_choice_trailing_text_after_bracket_queues(ctx: T.TranspileContext) -> None:
    text = "Pick one?\\ch[200,0,First,Second] extra text"
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, [text])]], trigger=0)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_TEXT
    assert "dynmultichoice" not in res.text


def test_inline_choice_residual_unknown_tag_queues(ctx: T.TranspileContext) -> None:
    # \v[3] survives the color-code strip (<c2=...>/\c[N] only) — queue the
    # whole command rather than emit mystery text into a menu option.
    text = "Pick one?\\ch[200,0,First,\\v[3]Second]"
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, [text])]], trigger=0)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_TEXT
    assert "dynmultichoice" not in res.text


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
    # Only trigger 4 (parallel) gets no lock/release wrapping — triggers 1/2
    # wrap lock/release (see test_trigger_one_wraps_lock_release_no_faceplayer)
    # and trigger 3 (autorun) wraps lockall/releaseall (see
    # test_trigger_three_wraps_lockall_releaseall).
    res = run_event(ctx, [[cmd(T.WAIT, [1])]], trigger=4)
    assert "lock" not in res.text
    assert "faceplayer" not in res.text
    assert "release" not in res.text


def test_trigger_three_wraps_lockall_releaseall(ctx: T.TranspileContext) -> None:
    # Autorun pages (trigger 3) are invoked from an ON_FRAME_TABLE map script;
    # vanilla ON_FRAME cutscenes use lockall/releaseall, not lock/release.
    res = run_event(ctx, [[cmd(T.WAIT, [1])]], trigger=3)
    lines = [ln.strip() for ln in res.text.splitlines()]
    assert lines == [
        "# npc",
        "script Map049_EV005_Page1 {",
        "lockall",
        "delay(1)",
        "releaseall",
        "end",
        "}",
    ]
    assert "faceplayer" not in res.text


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
# pbReceiveItem (shape B: bare 355/655 statement, shape C: type-12 condition)
# ----------------------------------------------------------------------------


def test_receive_item_bare_call_no_qty(ctx: T.TranspileContext) -> None:
    ctx.items = {"RARECANDY": "ITEM_RARE_CANDY"}
    res = run_event(
        ctx, [[cmd(T.SCRIPT, ["Kernel.pbReceiveItem(::PBItems::RARECANDY)"])]], trigger=1
    )
    assert res.unhandled == []
    assert "giveitem(ITEM_RARE_CANDY)" in res.text


def test_receive_item_bare_call_with_qty(ctx: T.TranspileContext) -> None:
    ctx.items = {"ANTIDOTE": "ITEM_ANTIDOTE"}
    res = run_event(
        ctx, [[cmd(T.SCRIPT, ["Kernel.pbReceiveItem(::PBItems::ANTIDOTE, 5)"])]], trigger=1
    )
    assert res.unhandled == []
    assert "giveitem(ITEM_ANTIDOTE, 5)" in res.text


def test_receive_item_bare_call_with_qty_and_display_name(ctx: T.TranspileContext) -> None:
    # The trailing _I("...") display string has no Emerald equivalent —
    # STD_OBTAIN_ITEM already names the item — and is dropped, not queued.
    ctx.items = {"ORANBERRY": "ITEM_ORAN_BERRY"}
    res = run_event(
        ctx,
        [[cmd(T.SCRIPT, ['Kernel.pbReceiveItem(::PBItems::ORANBERRY,5,_I("Oran Berries"))'])]],
        trigger=1,
    )
    assert res.unhandled == []
    assert "giveitem(ITEM_ORAN_BERRY, 5)" in res.text
    assert "Oran Berries" not in res.text


def test_receive_item_bare_call_no_module_scope_prefix(ctx: T.TranspileContext) -> None:
    # The leading `::` before PBItems is corpus-inconsistent (Map073 EV6).
    ctx.items = {"BACUBERRY": "ITEM_BACU_BERRY"}
    res = run_event(
        ctx, [[cmd(T.SCRIPT, ["Kernel.pbReceiveItem(PBItems::BACUBERRY)"])]], trigger=1
    )
    assert res.unhandled == []
    assert "giveitem(ITEM_BACU_BERRY)" in res.text


def test_receive_item_bare_call_unmapped_item_queues(ctx: T.TranspileContext) -> None:
    ctx.items = {}
    res = run_event(
        ctx, [[cmd(T.SCRIPT, ["Kernel.pbReceiveItem(::PBItems::NOSUCHITEM)"])]], trigger=1
    )
    assert len(res.unhandled) == 1
    assert "giveitem" not in res.text
    assert "ITEM_" not in res.text


def test_receive_item_bare_call_unforked_constant_queues(ctx: T.TranspileContext) -> None:
    # ctx.items resolves the symbol, but the resulting constant does not
    # exist in the fork's own headers (the real BACUBERRY case,
    # output/uranium-build/maps/Map073.json EV6) — must queue, never emit an
    # invented symbol (CLAUDE.md §4.7 forward check).
    ctx.items = {"BACUBERRY": "ITEM_BACU_BERRY"}
    ctx.fork_item_constants = frozenset({"ITEM_POTION", "ITEM_ORAN_BERRY"})
    res = run_event(
        ctx, [[cmd(T.SCRIPT, ["Kernel.pbReceiveItem(PBItems::BACUBERRY)"])]], trigger=1
    )
    assert len(res.unhandled) == 1
    assert "giveitem" not in res.text
    assert "ITEM_BACU_BERRY" not in res.text


def test_receive_item_map073_ev6_four_consecutive_grants_stay_separate(
    ctx: T.TranspileContext,
) -> None:
    # output/uranium-build/maps/Map073.json event 6 page 0, commands 5-8: one
    # code-355 row plus three code-655 rows, each its own complete statement
    # (not continuation fragments of one call) — _merge_script_call_rows must
    # not fuse them.
    ctx.items = {
        "BACUBERRY": "ITEM_BACU_BERRY",
        "GUARABERRY": "ITEM_GUARA_BERRY",
        "CUPUBERRY": "ITEM_CUPU_BERRY",
        "ACAIBERRY": "ITEM_ACAI_BERRY",
    }
    commands = [
        cmd(T.SCRIPT, ["Kernel.pbReceiveItem(PBItems::BACUBERRY)"]),
        cmd(T.SCRIPT_CONT, ["Kernel.pbReceiveItem(PBItems::GUARABERRY)"]),
        cmd(T.SCRIPT_CONT, ["Kernel.pbReceiveItem(PBItems::CUPUBERRY)"]),
        cmd(T.SCRIPT_CONT, ["Kernel.pbReceiveItem(PBItems::ACAIBERRY)"]),
    ]
    res = run_event(ctx, [commands], trigger=1)
    assert res.unhandled == []
    assert res.text.count("giveitem(") == 4
    for const in ("ITEM_BACU_BERRY", "ITEM_GUARA_BERRY", "ITEM_CUPU_BERRY", "ITEM_ACAI_BERRY"):
        assert f"giveitem({const})" in res.text


def test_receive_item_type12_condition_empty_then_body(ctx: T.TranspileContext) -> None:
    # output/uranium-build/maps/Map068.json event 15 page 0 command 83 — a
    # pure side-effect wrapper (empty then/else), exactly faithful as a bare
    # giveitem with no branch.
    ctx.items = {"ORANBERRY": "ITEM_ORAN_BERRY"}
    commands = [
        cmd(
            T.CONDITIONAL_BRANCH,
            [12, 'Kernel.pbReceiveItem(::PBItems::ORANBERRY,5,_I("Oran Berries"))'],
            indent=0,
        ),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=1)
    assert res.unhandled == []
    assert "giveitem(ITEM_ORAN_BERRY, 5)" in res.text
    assert "VAR_RESULT" not in res.text


def test_receive_item_type12_condition_nonempty_then_body_branches_on_result(
    ctx: T.TranspileContext,
) -> None:
    # A non-empty then-body is the success path — pbReceiveItem's boolean
    # return is exactly giveitem's VAR_RESULT (engine/asm/macros/event.inc:
    # 2118-2126: TRUE on success, FALSE if the bag has no room), so this is
    # expressible natively rather than queued.
    ctx.items = {"NUGGET": "ITEM_NUGGET"}
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "Kernel.pbReceiveItem(::PBItems::NUGGET)"], indent=0),
        cmd(T.SHOW_TEXT, ["Thanks!"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=1)
    assert res.unhandled == []
    assert "giveitem(ITEM_NUGGET)" in res.text
    assert "if (var(VAR_RESULT) != 0) {" in res.text
    assert "Thanks!" in res.text


def test_receive_item_type12_condition_unmapped_item_queues(ctx: T.TranspileContext) -> None:
    ctx.items = {}
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "Kernel.pbReceiveItem(::PBItems::NOSUCHITEM)"], indent=0),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=1)
    assert len(res.unhandled) == 1
    assert "giveitem" not in res.text


# ----------------------------------------------------------------------------
# player-facing conditional (RMXP condition kind 6, character id -1)
# ----------------------------------------------------------------------------


def test_player_facing_up_emits_specialvar_and_branches(ctx: T.TranspileContext) -> None:
    # Map031 EV049 "NurseTut" page 1, cmds 5/42: [6, -1, 8].
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [6, -1, 8], indent=0),
        cmd(T.SHOW_TEXT, ["facing up"], indent=1),
        cmd(T.ELSE_BRANCH, indent=0),
        cmd(T.SHOW_TEXT, ["not facing up"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], map_id=31, event_id=49, trigger=0)
    assert res.unhandled == []
    assert "specialvar(VAR_TEMP_0, GetPlayerFacingDirection)" in res.text
    assert "if (var(VAR_TEMP_0) == DIR_NORTH) {" in res.text
    assert "facing up" in res.text
    assert "not facing up" in res.text


@pytest.mark.parametrize(
    "direction,dir_const",
    [(2, "DIR_SOUTH"), (4, "DIR_WEST"), (6, "DIR_EAST")],
)
def test_player_facing_other_cardinal_directions(
    ctx: T.TranspileContext, direction: int, dir_const: str
) -> None:
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [6, -1, direction], indent=0),
        cmd(T.SHOW_TEXT, ["facing"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], map_id=31, event_id=49, trigger=0)
    assert res.unhandled == []
    assert f"if (var(VAR_TEMP_0) == {dir_const}) {{" in res.text


def test_player_facing_non_player_character_id_still_queues(ctx: T.TranspileContext) -> None:
    # Same direction, but an NPC local id instead of the player (-1) — no
    # established RMXP-local-id -> fork-local-id mapping, must not be guessed at.
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [6, 3, 8], indent=0),
        cmd(T.SHOW_TEXT, ["facing"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=0)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "specialvar" not in res.text
    assert "GetPlayerFacingDirection" not in res.text


def test_player_facing_unmapped_direction_still_queues(ctx: T.TranspileContext) -> None:
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [6, -1, 1], indent=0),  # 1 is not a cardinal RMXP direction
        cmd(T.SHOW_TEXT, ["facing"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=0)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "specialvar" not in res.text


# ----------------------------------------------------------------------------
# bag item-quantity conditional ($PokemonBag.pbQuantity(...) <op> 0)
# ----------------------------------------------------------------------------


def test_bag_quantity_greater_than_zero_has_item(ctx: T.TranspileContext) -> None:
    # Map073 EV1 page 1 cmd 4: ...BIKEWHEEL)>0
    ctx.items = {"BIKEWHEEL": "ITEM_BIKE_WHEEL"}
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "$PokemonBag.pbQuantity(PBItems::BIKEWHEEL)>0"], indent=0),
        cmd(T.SHOW_TEXT, ["has wheel"], indent=1),
        cmd(T.ELSE_BRANCH, indent=0),
        cmd(T.SHOW_TEXT, ["no wheel"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], map_id=73, event_id=1, trigger=0)
    assert res.unhandled == []
    assert "checkitem(ITEM_BIKE_WHEEL)" in res.text
    assert "if (var(VAR_RESULT) == TRUE) {" in res.text
    assert "has wheel" in res.text
    assert "no wheel" in res.text


def test_bag_quantity_equals_zero_lacks_item(ctx: T.TranspileContext) -> None:
    # Map073 EV3 page 1 cmd 0 / EV6 page 2 cmd 2: ...SPRINKLOTAD)==0
    ctx.items = {"SPRINKLOTAD": "ITEM_SPRINKLOTAD"}
    ctx.fork_item_constants = frozenset({"ITEM_SPRINKLOTAD"})
    commands = [
        cmd(
            T.CONDITIONAL_BRANCH,
            [12, "$PokemonBag.pbQuantity(PBItems::SPRINKLOTAD)==0"],
            indent=0,
        ),
        cmd(T.SHOW_TEXT, ["lacks it"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], map_id=73, event_id=3, trigger=0)
    assert res.unhandled == []
    assert "checkitem(ITEM_SPRINKLOTAD)" in res.text
    assert "if (var(VAR_RESULT) == FALSE) {" in res.text
    assert "lacks it" in res.text


def test_bag_quantity_ruby_symbol_form_checkitem(ctx: T.TranspileContext) -> None:
    # Map040 EV017 page 0 cmd 0: `$PokemonBag.pbQuantity(:MARIAKEY)>0` — the
    # bare Ruby-symbol spelling names the same Essentials item symbol.
    ctx.items = {"MARIAKEY": "ITEM_MARIAS_KEY"}
    ctx.fork_item_constants = frozenset({"ITEM_MARIAS_KEY"})
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "$PokemonBag.pbQuantity(:MARIAKEY)>0"], indent=0),
        cmd(T.SHOW_TEXT, ["used key"], indent=1),
        cmd(T.ELSE_BRANCH, indent=0),
        cmd(T.SHOW_TEXT, ["locked"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], map_id=40, event_id=17, trigger=1)
    assert res.unhandled == []
    assert "checkitem(ITEM_MARIAS_KEY)" in res.text
    assert "if (var(VAR_RESULT) == TRUE) {" in res.text
    assert "used key" in res.text and "locked" in res.text


def test_bag_quantity_ruby_symbol_form_unforked_still_queues(ctx: T.TranspileContext) -> None:
    # The real fork today lacks ITEM_MARIAS_KEY (Phase-2 items not yet in
    # engine/include/constants/items.h): §4.7 forward gate -> queue, no invention.
    ctx.items = {"MARIAKEY": "ITEM_MARIAS_KEY"}
    ctx.fork_item_constants = frozenset({"ITEM_POTION"})
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "$PokemonBag.pbQuantity(:MARIAKEY)>0"], indent=0),
        cmd(T.SHOW_TEXT, ["used key"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=1)
    assert len(res.unhandled) == 1
    assert "ITEM_MARIAS_KEY" not in res.text


def test_bag_quantity_unresolvable_item_symbol_still_queues(ctx: T.TranspileContext) -> None:
    ctx.items = {}
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "$PokemonBag.pbQuantity(PBItems::NOSUCHITEM)>0"], indent=0),
        cmd(T.SHOW_TEXT, ["has it"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=0)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "checkitem" not in res.text


def test_bag_quantity_unforked_constant_still_queues(ctx: T.TranspileContext) -> None:
    # ctx.items resolves the symbol, but the constant does not exist in the
    # fork's own headers (CLAUDE.md §4.7 forward check).
    ctx.items = {"BACUBERRY": "ITEM_BACU_BERRY"}
    ctx.fork_item_constants = frozenset({"ITEM_POTION"})
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "$PokemonBag.pbQuantity(PBItems::BACUBERRY)>0"], indent=0),
        cmd(T.SHOW_TEXT, ["has it"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=0)
    assert len(res.unhandled) == 1
    assert "checkitem" not in res.text
    assert "ITEM_BACU_BERRY" not in res.text


def test_bag_quantity_wrong_operator_still_queues(ctx: T.TranspileContext) -> None:
    ctx.items = {"BIKEWHEEL": "ITEM_BIKE_WHEEL"}
    commands = [
        cmd(
            T.CONDITIONAL_BRANCH,
            [12, "$PokemonBag.pbQuantity(PBItems::BIKEWHEEL)>=1"],
            indent=0,
        ),
        cmd(T.SHOW_TEXT, ["has it"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=0)
    assert len(res.unhandled) == 1
    assert "checkitem" not in res.text


# ----------------------------------------------------------------------------
# three-option starter-pick choice menu (multichoice)
# ----------------------------------------------------------------------------


def _starter_pick_commands() -> list[dict]:
    # Map068 EV003 page 1 cmd 3: ['Orchynx', 'Raptorch', 'Eletux'], no cancel arm.
    return [
        cmd(T.SHOW_CHOICES, [["Orchynx", "Raptorch", "Eletux"], 0], indent=0),
        cmd(T.CHOICE_WHEN, [0, "Orchynx"], indent=0),
        cmd(T.SHOW_TEXT, ["orchynx path"], indent=1),
        cmd(T.CHOICE_WHEN, [1, "Raptorch"], indent=0),
        cmd(T.SHOW_TEXT, ["raptorch path"], indent=1),
        cmd(T.CHOICE_WHEN, [2, "Eletux"], indent=0),
        cmd(T.SHOW_TEXT, ["eletux path"], indent=1),
        cmd(T.CHOICES_END, indent=0),
    ]


def test_starter_pick_choice_emits_multichoice_and_switch(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [_starter_pick_commands()], map_id=68, event_id=3, trigger=0)
    assert res.unhandled == []
    assert "multichoice(0, 0, MULTI_URANIUM_STARTER_PICK, TRUE)" in res.text
    assert "switch (var(VAR_RESULT)) {" in res.text
    assert "    case 0:" in res.text
    assert "    case 1:" in res.text
    assert "    case 2:" in res.text
    assert "orchynx path" in res.text
    assert "raptorch path" in res.text
    assert "eletux path" in res.text
    case0_idx = res.text.index("case 0:")
    case1_idx = res.text.index("case 1:")
    case2_idx = res.text.index("case 2:")
    orchynx_idx = res.text.index("orchynx path")
    raptorch_idx = res.text.index("raptorch path")
    eletux_idx = res.text.index("eletux path")
    assert case0_idx < orchynx_idx < case1_idx < raptorch_idx < case2_idx < eletux_idx


def test_starter_pick_choice_with_cancel_arm_falls_through_to_queue(
    ctx: T.TranspileContext,
) -> None:
    # Same labels, but a cancel arm present — not the verified shape, must
    # not silently reference the minted constant.
    commands = [
        cmd(T.SHOW_CHOICES, [["Orchynx", "Raptorch", "Eletux"], 3], indent=0),
        cmd(T.CHOICE_WHEN, [0, "Orchynx"], indent=0),
        cmd(T.SHOW_TEXT, ["orchynx path"], indent=1),
        cmd(T.CHOICE_WHEN, [1, "Raptorch"], indent=0),
        cmd(T.SHOW_TEXT, ["raptorch path"], indent=1),
        cmd(T.CHOICE_WHEN, [2, "Eletux"], indent=0),
        cmd(T.SHOW_TEXT, ["eletux path"], indent=1),
        cmd(T.CHOICE_CANCEL, indent=0),
        cmd(T.SHOW_TEXT, ["cancel path"], indent=1),
        cmd(T.CHOICES_END, indent=0),
    ]
    res = run_event(ctx, [commands], map_id=68, event_id=3, trigger=0)
    assert "MULTI_URANIUM_STARTER_PICK" not in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_CHOICES


def test_different_three_option_labels_do_not_get_starter_multichoice(
    ctx: T.TranspileContext,
) -> None:
    # Different labels — must keep queueing like every other 3+-option menu,
    # not silently reuse the starter-pick constant.
    commands = [
        cmd(T.SHOW_CHOICES, [["A", "B", "C"], 3], indent=0),
        cmd(T.CHOICE_WHEN, [0, "A"], indent=0),
        cmd(T.SHOW_TEXT, ["a path"], indent=1),
        cmd(T.CHOICE_WHEN, [1, "B"], indent=0),
        cmd(T.SHOW_TEXT, ["b path"], indent=1),
        cmd(T.CHOICE_WHEN, [2, "C"], indent=0),
        cmd(T.SHOW_TEXT, ["c path"], indent=1),
        cmd(T.CHOICES_END, indent=0),
    ]
    res = run_event(ctx, [commands], trigger=0)
    assert "MULTI_URANIUM_STARTER_PICK" not in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_CHOICES


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


# ----------------------------------------------------------------------------
# pbDeleteItem (the consuming counterpart to pbReceiveItem)
# ----------------------------------------------------------------------------


def test_delete_item_bare_call_no_qty(ctx: T.TranspileContext) -> None:
    # Real occurrence: Map073 EV001 cmd 9, inside the BIKEWHEEL trade's
    # then-arm — consumes the wheel that the same branch trades for a Bicycle.
    ctx.items = {"BIKEWHEEL": "ITEM_BIKE_WHEEL"}
    res = run_event(
        ctx,
        [[cmd(T.SCRIPT, ["$PokemonBag.pbDeleteItem(PBItems::BIKEWHEEL)"])]],
        trigger=1,
    )
    assert res.unhandled == []
    assert "removeitem(ITEM_BIKE_WHEEL)" in res.text


def test_delete_item_bare_call_with_qty(ctx: T.TranspileContext) -> None:
    ctx.items = {"ANTIDOTE": "ITEM_ANTIDOTE"}
    res = run_event(
        ctx,
        [[cmd(T.SCRIPT, ["$PokemonBag.pbDeleteItem(::PBItems::ANTIDOTE, 3)"])]],
        trigger=1,
    )
    assert res.unhandled == []
    assert "removeitem(ITEM_ANTIDOTE, 3)" in res.text


def test_delete_item_unresolved_symbol_still_queues(ctx: T.TranspileContext) -> None:
    # No ctx.items entry — must queue rather than invent an ITEM_* (§4.5/§4.7).
    res = run_event(
        ctx,
        [[cmd(T.SCRIPT, ["$PokemonBag.pbDeleteItem(PBItems::NOSUCHITEM)"])]],
        trigger=1,
    )
    assert len(res.unhandled) == 1
    assert "removeitem" not in res.text


def test_colour_text_code_stripped(ctx: T.TranspileContext) -> None:
    # RMXP's \C[n] palette-slot colour code; \C[0] resets. Uranium uses it to
    # highlight an item name mid-sentence (Map073 EV001 cmd 18). Same
    # disposition as \b — a tint with no mechanical meaning (2026-08-19).
    res = run_event(
        ctx,
        [[cmd(T.SHOW_TEXT, ["bring me a \\C[3]Bike wheel\\C[0] I can fix it"])]],
        trigger=1,
    )
    assert res.unhandled == []
    assert "\\C[" not in res.text
    assert "Bike wheel" in res.text


def test_colour_text_code_does_not_swallow_other_codes(
    ctx: T.TranspileContext,
) -> None:
    # \r must keep queueing — stripping \C[n] is specific, not a general
    # "unknown backslash code" strip (CLAUDE.md §4.5).
    res = run_event(
        ctx, [[cmd(T.SHOW_TEXT, ["\\C[3]Red \\r text"])]], trigger=1,
    )
    assert len(res.unhandled) == 1


# ----------------------------------------------------------------------------
# door-sheet self animation -> native door commands
# ----------------------------------------------------------------------------


def _run_door_event(
    ctx: T.TranspileContext, steps: list[dict], sheet: str = "door habidome",
    target: int = 0,
) -> T.TranspiledEvent:
    ev = {
        "id": 14, "name": "door", "x": 49, "y": 14,
        "pages": [{
            "trigger": 1, "graphic": {"character_name": sheet},
            "list": [
                cmd(T.SET_MOVE_ROUTE, [target, _route(steps)]),
                cmd(T.WAIT_MOVE_COMPLETION),
            ],
        }],
    }
    return T.transpile_event(40, ev, ctx)


_DELAY2 = {"code": 15, "parameters": [2]}
# RMXP face codes: 16 down, 17 left, 18 right, 19 up
_OPENING = [{"code": 44, "parameters": [{}]}, _DELAY2, {"code": 18}, _DELAY2,
            {"code": 19}, _DELAY2, {"code": 17}, _DELAY2]
_CLOSING = [_DELAY2, {"code": 19}, _DELAY2, {"code": 18}, _DELAY2,
            {"code": 16}, _DELAY2]


def test_door_self_route_opening_emits_opendoor(ctx: T.TranspileContext) -> None:
    res = _run_door_event(ctx, _OPENING)
    assert "opendoor(49, 14)" in res.text
    assert "waitdooranim" in res.text
    assert "applymovement" not in res.text
    assert "waitmovement" not in res.text
    assert res.unhandled == []


def test_door_self_route_closing_emits_closedoor(ctx: T.TranspileContext) -> None:
    res = _run_door_event(ctx, _CLOSING, sheet="PU-doorsdew")
    assert "closedoor(49, 14)" in res.text
    assert "waitdooranim" in res.text
    assert "applymovement" not in res.text
    assert res.unhandled == []


def test_door_self_route_snap_open_and_closed(ctx: T.TranspileContext) -> None:
    res = _run_door_event(ctx, [{"code": 17}, {"code": 15, "parameters": [6]}])
    assert "setdooropen(49, 14)" in res.text
    assert "waitdooranim" not in res.text
    assert "waitmovement" not in res.text
    assert res.unhandled == []
    res = _run_door_event(ctx, [{"code": 16}])
    assert "setdoorclosed(49, 14)" in res.text


def test_door_self_route_by_own_event_id(ctx: T.TranspileContext) -> None:
    res = _run_door_event(ctx, _OPENING, target=14)
    assert "opendoor(49, 14)" in res.text


def test_non_door_self_route_unchanged(ctx: T.TranspileContext) -> None:
    res = _run_door_event(ctx, _OPENING, sheet="NPC 01")
    assert "applymovement(14, Map040_EV014_Page1_Move1)" in res.text
    assert "opendoor" not in res.text
    assert "waitmovement(0)" in res.text


def test_door_sheet_player_route_unchanged(ctx: T.TranspileContext) -> None:
    res = _run_door_event(ctx, [{"code": 1}], target=-1)
    assert "applymovement(OBJ_EVENT_ID_PLAYER" in res.text


@pytest.mark.parametrize("steps", [
    [{"code": 17}, {"code": 1}],            # walk step
    [{"code": 18}],                         # ends facing right: neither row
    [_DELAY2],                              # no face step at all
])
def test_door_self_route_unsupported_fails_loud(
    ctx: T.TranspileContext, steps: list[dict]
) -> None:
    res = _run_door_event(ctx, steps)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SET_MOVE_ROUTE
    assert "door-sheet" in res.unhandled[0].description
    assert "applymovement" not in res.text
    assert "waitmovement" not in res.text


# ----------------------------------------------------------------------------
# Gym Leader badge battle (CH06 Map042 EV003): LEADER_* class, win-body writes
# a self-switch -> trainerbattle_no_intro WITHOUT cleartrainerflag.
# ----------------------------------------------------------------------------


def _leader_commands(class_sym: str, then_body: list[dict]) -> list[dict]:
    call = (
        f'pbTrainerBattle(PBTrainers::{class_sym},"Maria",'
        '_I("There!~\\nThat\'s the fighting spirit!"),false,0)'
    )
    cmds = [cmd(T.CONDITIONAL_BRANCH, [12, call], indent=0)]
    cmds += [dict(c, indent=1) for c in then_body]
    cmds += [cmd(T.ELSE_BRANCH, indent=0), cmd(T.BRANCH_END, indent=0)]
    return cmds


def test_leader_battle_self_switch_win_body_emits_no_intro_without_clear(
    ctx: T.TranspileContext,
) -> None:
    ctx.trainers = {("TRAINER_CLASS_LEADER_ROXANNE", "Maria", 0): "TRAINER_MARIA_15"}
    commands = _leader_commands(
        "LEADER_Roxanne",
        [cmd(T.SHOW_TEXT, ["Congrats!"]), cmd(T.CONTROL_SELF_SWITCH, ["A", 0])],
    )
    res = run_event(ctx, [commands], map_id=42, event_id=3)
    assert "trainerbattle_no_intro(TRAINER_MARIA_15, Map042_EV003_Page1_FacilityLoseText)" in res.text
    assert "cleartrainerflag" not in res.text
    assert 'format("Congrats!")' in res.text
    assert "text Map042_EV003_Page1_FacilityLoseText {" in res.text
    assert not any("pbTrainerBattle" in str(u) for u in res.unhandled)


def test_non_leader_self_switch_win_body_still_queues(ctx: T.TranspileContext) -> None:
    """The self-switch guard stays for every non-LEADER class (Map019 EV6)."""
    ctx.trainers = {("TRAINER_CLASS_BIKER", "Maria", 0): "TRAINER_MARIA_15"}
    commands = _leader_commands("BIKER", [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])])
    res = run_event(ctx, [commands], map_id=42, event_id=3)
    assert "trainerbattle_no_intro" not in res.text
    assert len(res.unhandled) == 1


# ----------------------------------------------------------------------------
# $Trainer.badges[N]=true / Kernel.pbSetHealingSpot
# ----------------------------------------------------------------------------


@pytest.mark.parametrize("n", range(8))
def test_badge_true_emits_native_badge_flag(ctx: T.TranspileContext, n: int) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, [f"$Trainer.badges[{n}]=true"])]], trigger=1)
    assert res.unhandled == []
    assert f"setflag(FLAG_BADGE0{n + 1}_GET)" in res.text


@pytest.mark.parametrize(
    "text",
    [
        "$Trainer.badges[0]=false",
        "$Trainer.badges[$game_variables[5]]=true",
        "$Trainer.badges[8]=true",
    ],
)
def test_badge_non_literal_true_queues(ctx: T.TranspileContext, text: str) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, [text])]], trigger=1)
    assert len(res.unhandled) == 1
    assert "badges" in res.unhandled[0].description
    assert "FLAG_BADGE" not in res.text


def test_set_healing_spot_known_triple_emits_setrespawn(
    ctx: T.TranspileContext,
) -> None:
    ctx.healing_spots[(40, 24, 56)] = "HEAL_LOCATION_NOWTOCH_CITY"
    res = run_event(
        ctx, [[cmd(T.SCRIPT, ["Kernel.pbSetHealingSpot(40,24,56)"])]], trigger=1
    )
    assert res.unhandled == []
    assert "setrespawn(HEAL_LOCATION_NOWTOCH_CITY)" in res.text


@pytest.mark.parametrize(
    "text", ["Kernel.pbSetHealingSpot(40,24,56)", "pbSetHealingSpot(40,24,56)"]
)
def test_set_healing_spot_unknown_triple_queues(
    ctx: T.TranspileContext, text: str
) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, [text])]], trigger=1)
    assert len(res.unhandled) == 1
    assert "(40, 24, 56)" in res.unhandled[0].description
    assert "setrespawn(" not in "\n".join(
        l for l in res.text.splitlines() if not l.lstrip().startswith("#")
    )



# ----------------------------------------------------------------------------
# Starter-dependent rival battle (CH06 Map040 EV079): p=N if sw -> var1 -> pbGet(1)
# ----------------------------------------------------------------------------

_STARTER_ROWS = [
    "p=1 if $game_switches[61] == true",
    "p=2 if $game_switches[59] == true",
    "p=3 if $game_switches[60] == true",
    "$game_variables[1]=p",
]
_STARTER_CALL = (
    'pbTrainerBattle(PBTrainers::RIVAL,"Theo",'
    '_I("No! Not even my new Pokemon could help me win...?"),false,pbGet(1))'
)


def _starter_rival_commands(
    rows: list[str] | None = None,
    call: str = _STARTER_CALL,
    otherwise: list[dict] | None = None,
) -> list[dict]:
    rows = _STARTER_ROWS if rows is None else rows
    cmds = [cmd(T.SCRIPT if i == 0 else T.SCRIPT_CONT, [r]) for i, r in enumerate(rows)]
    cmds.append(cmd(T.CONDITIONAL_BRANCH, [12, call], indent=0))
    cmds.append(cmd(T.ELSE_BRANCH, indent=0))
    cmds += otherwise if otherwise is not None else [cmd(T.EXIT_EVENT, indent=1)]
    cmds.append(cmd(T.BRANCH_END, indent=0))
    return cmds


def _theo_ctx(ctx: T.TranspileContext) -> T.TranspileContext:
    ctx.trainers = {
        ("TRAINER_CLASS_RIVAL", "Theo", 1): "TRAINER_THEO_12",
        ("TRAINER_CLASS_RIVAL", "Theo", 2): "TRAINER_THEO_13",
        ("TRAINER_CLASS_RIVAL", "Theo", 3): "TRAINER_THEO_14",
    }
    return ctx


def test_starter_rival_battle_emits_three_arms(ctx: T.TranspileContext) -> None:
    res = run_event(_theo_ctx(ctx), [_starter_rival_commands()], map_id=40, event_id=79)
    assert res.unhandled == []
    text = res.text
    lose = "Map040_EV079_Page1_StarterRivalLoseText"
    assert f"trainerbattle_no_intro(TRAINER_THEO_12, {lose})" in text
    assert f"trainerbattle_no_intro(TRAINER_THEO_13, {lose})" in text
    assert f"trainerbattle_no_intro(TRAINER_THEO_14, {lose})" in text
    # RMXP's last true `p=` row wins (sw60 > sw59 > sw61), so the chain tests
    # them in that order: Eletux (party 3) first, Orchynx (party 1) last.
    i_eletux = text.index("if (flag(FLAG_HAS_ELETUX)) {")
    i_raptorch = text.index("} elif (flag(FLAG_HAS_RAPTORCH)) {")
    i_orchynx = text.index("} elif (flag(FLAG_HAS_ORCHYNX)) {")
    assert i_eletux < text.index("TRAINER_THEO_14") < i_raptorch
    assert i_raptorch < text.index("TRAINER_THEO_13") < i_orchynx
    assert i_orchynx < text.index("TRAINER_THEO_12")
    # var-1 write preserved per arm (Kellyn/Cam read its prior value)
    assert "setvar(VAR_RESULT_VAR, 1)" in text and "setvar(VAR_RESULT_VAR, 3)" in text
    assert f"text {lose} {{" in text
    assert "UNHANDLED" not in text


@pytest.mark.parametrize(
    "rows",
    [
        ["p=1 if $game_switches[62] == true", *_STARTER_ROWS[1:]],
        [*_STARTER_ROWS[:2], "p=3 if $game_switches[10] == true", _STARTER_ROWS[3]],
        [*_STARTER_ROWS, "p=4 if $game_switches[1] == true"],
        _STARTER_ROWS[:3],
        [*_STARTER_ROWS[:3], "$game_variables[2]=p"],
    ],
)
def test_starter_rival_battle_variant_rows_unhandled(
    ctx: T.TranspileContext, rows: list[str]
) -> None:
    res = run_event(_theo_ctx(ctx), [_starter_rival_commands(rows=rows)], map_id=40, event_id=79)
    assert res.unhandled
    assert "TRAINER_THEO_12" not in res.text


def test_starter_rival_battle_nonmatching_call_or_else_unhandled(
    ctx: T.TranspileContext,
) -> None:
    _theo_ctx(ctx)
    bad_call = _STARTER_CALL.replace("false,pbGet(1)", "true,pbGet(1)")
    res = run_event(ctx, [_starter_rival_commands(call=bad_call)], map_id=40, event_id=79)
    assert res.unhandled and "TRAINER_THEO_12" not in res.text
    res = run_event(
        ctx, [_starter_rival_commands(otherwise=[cmd(T.SHOW_TEXT, ["Hi"], indent=1)])],
        map_id=40, event_id=79,
    )
    assert res.unhandled and "TRAINER_THEO_12" not in res.text
