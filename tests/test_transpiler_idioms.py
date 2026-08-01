"""Unit tests for the slice1 idiom clusters added to the deterministic
transpiler (BUILD_PLAN §3, grill D10 #4 read-through — reference/
slice1_queue_readthrough.md). Covers: dialogue text-code wiring
(``translate_text_codes``), the door / give-item / align-loop type-12
condition idioms, and the code-207 emote tier.

Event/page shape mirrors ``tests/test_transpiler.py`` (same convention as the
Phase-3 deserializer output): an event is ``{id, name, x, y, pages:[...]}``
and each page is ``{trigger, list, ...}`` with ``list`` a sequence of
``{code, indent, parameters}`` commands.

No story dialogue is quoted anywhere below — every text fixture is a
mechanical placeholder string.
"""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import poryscript
from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.deterministic import TextTranslation
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, self_switch_flag_name

# ----------------------------------------------------------------------------
# builders (mirrors tests/test_transpiler.py; kept local per file-ownership)
# ----------------------------------------------------------------------------


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_event(
    pages_cmds: list[list[dict]],
    trigger: int = 0,
    id: int = 5,
    name: str = "npc",
    x: int = 0,
    y: int = 0,
) -> dict:
    pages = [{"trigger": trigger, "list": cmds} for cmds in pages_cmds]
    return {"id": id, "name": name, "x": x, "y": y, "pages": pages}


def _route(steps: list[dict], repeat: bool = False) -> dict:
    return {"list": [*steps, {"code": 0}], "repeat": repeat}


@pytest.fixture()
def ctx() -> T.TranspileContext:
    return T.TranspileContext(registry=FlagRegistry())


def run_event(
    ctx: T.TranspileContext,
    pages_cmds: list[list[dict]],
    trigger: int = 3,
    map_id: int = 32,
    event_id: int = 5,
    name: str = "npc",
    x: int = 0,
    y: int = 0,
) -> T.TranspiledEvent:
    ev = make_event(pages_cmds, trigger=trigger, id=event_id, name=name, x=x, y=y)
    return T.transpile_event(map_id, ev, ctx)


# ----------------------------------------------------------------------------
# Feature 1 — dialogue text-code wiring (translate_text_codes)
# ----------------------------------------------------------------------------


def test_text_wiring_plain_uses_current_baseline(ctx: T.TranspileContext) -> None:
    """Plain text (+ \\PN) is already translated by the baseline — no monkeypatch
    needed; this exercises the real wiring end to end."""
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, ["Hi \\PN!"])]])
    assert 'msgbox(format("Hi {PLAYER}!"))' in res.text
    assert res.unhandled == []


def test_text_wiring_none_still_queues(
    ctx: T.TranspileContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(T, "translate_text_codes", lambda raw: None)
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, ["placeholder"])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_TEXT
    assert "# UNHANDLED" in res.text
    assert "msgbox" not in res.text


def test_text_wiring_autoclose_emits_msgbox_autoclose(
    ctx: T.TranspileContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        T, "translate_text_codes",
        lambda raw: TextTranslation(text="Placeholder line.", autoclose=True),
    )
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, ["placeholder"])]])
    assert 'msgbox(format("Placeholder line."), MSGBOX_AUTOCLOSE)' in res.text
    assert res.unhandled == []


def test_text_wiring_sign_wraps_lock_release_no_faceplayer(
    ctx: T.TranspileContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matches deterministic._sign_block's shape exactly: lock/msgbox/release,
    no faceplayer, and MSGBOX_SIGN is never used."""
    monkeypatch.setattr(
        T, "translate_text_codes",
        lambda raw: TextTranslation(text="Placeholder sign text.", sign=True),
    )
    res = run_event(ctx, [[cmd(T.SHOW_TEXT, ["placeholder"])]])
    lines = [ln.strip() for ln in res.text.splitlines()]
    idx = lines.index('msgbox(format("Placeholder sign text."))')
    assert lines[idx - 1] == "lock"
    assert lines[idx + 1] == "release"
    assert "faceplayer" not in res.text
    assert "MSGBOX_SIGN" not in res.text
    assert res.unhandled == []


# ----------------------------------------------------------------------------
# Feature 2a — door idiom: get_character(0).onEvent?
# ----------------------------------------------------------------------------


def _door_commands(then_body: list[dict], else_body: list[dict] | None = None) -> list[dict]:
    cmds = [cmd(T.CONDITIONAL_BRANCH, [12, "get_character(0).onEvent?"], indent=0)]
    cmds += [dict(c, indent=1) for c in then_body]
    if else_body is not None:
        cmds.append(cmd(T.ELSE_BRANCH, indent=0))
        cmds += [dict(c, indent=1) for c in else_body]
    cmds.append(cmd(T.BRANCH_END, indent=0))
    return cmds


def test_door_idiom_emits_getplayerxy_and_position_check(ctx: T.TranspileContext) -> None:
    commands = _door_commands([cmd(T.CONTROL_SELF_SWITCH, ["A", 0])])
    res = run_event(ctx, [commands], map_id=32, event_id=3, x=10, y=5)
    assert "getplayerxy(VAR_TEMP_0, VAR_TEMP_1)" in res.text
    assert "if (var(VAR_TEMP_0) == 10 && var(VAR_TEMP_1) == 5) {" in res.text
    expected_flag = self_switch_flag_name(32, 3, "A")
    assert f"setflag({expected_flag})" in res.text
    assert res.unhandled == []


def test_door_idiom_with_else_branch(ctx: T.TranspileContext) -> None:
    commands = _door_commands(
        [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])],
        else_body=[cmd(T.CONTROL_SELF_SWITCH, ["B", 0])],
    )
    res = run_event(ctx, [commands], map_id=32, event_id=3, x=1, y=2)
    assert "} else {" in res.text
    assert f"setflag({self_switch_flag_name(32, 3, 'A')})" in res.text
    assert f"setflag({self_switch_flag_name(32, 3, 'B')})" in res.text


def test_door_idiom_other_get_character_form_still_queues(ctx: T.TranspileContext) -> None:
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "get_character(1).onEvent?"], indent=0),
        cmd(T.CONTROL_SELF_SWITCH, ["A", 0], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], x=10, y=5)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "getplayerxy" not in res.text


def test_door_idiom_in_common_event_queues(ctx: T.TranspileContext) -> None:
    """No owning event/tile in a common event — the idiom is meaningless there,
    same disposition as self-switch (123) in a common event."""
    ce = {
        "id": 7,
        "name": "CE",
        "list": [
            cmd(T.CONDITIONAL_BRANCH, [12, "get_character(0).onEvent?"], indent=0),
            cmd(T.WAIT, [1], indent=1),
            cmd(T.BRANCH_END, indent=0),
        ],
    }
    res = T.transpile_common_event(ce, ctx)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "getplayerxy" not in res.text


# ----------------------------------------------------------------------------
# Feature 2b — code 208 (change player transparency)
# ----------------------------------------------------------------------------


def test_change_player_transparency_invisible(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CHANGE_PLAYER_TRANSPARENCY, [0])]])
    assert "applymovement(OBJ_EVENT_ID_PLAYER, Map032_EV005_Page1_Move1)" in res.text
    assert "movement Map032_EV005_Page1_Move1 {\n    set_invisible\n}" in res.text
    assert "waitmovement(0)" in res.text
    assert res.unhandled == []


def test_change_player_transparency_visible(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CHANGE_PLAYER_TRANSPARENCY, [1])]])
    assert "applymovement(OBJ_EVENT_ID_PLAYER, Map032_EV005_Page1_Move1)" in res.text
    assert "movement Map032_EV005_Page1_Move1 {\n    set_visible\n}" in res.text
    assert res.unhandled == []


def test_change_player_transparency_bad_params_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CHANGE_PLAYER_TRANSPARENCY, [9])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CHANGE_PLAYER_TRANSPARENCY


# ----------------------------------------------------------------------------
# Feature 2c — Kernel.pbReceiveItem(...) give-item branches
# ----------------------------------------------------------------------------


def test_receive_item_both_arms_empty_emits_bare_giveitem(ctx: T.TranspileContext) -> None:
    ctx.items = {"LAVACOOKIE": "ITEM_LAVA_COOKIE"}
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "Kernel.pbReceiveItem(::PBItems::LAVACOOKIE)"], indent=0),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands])
    assert "giveitem(ITEM_LAVA_COOKIE)" in res.text
    assert "VAR_RESULT" not in res.text
    assert res.unhandled == []


def test_receive_item_then_only_omits_else(ctx: T.TranspileContext) -> None:
    ctx.items = {"RARECANDY": "ITEM_RARE_CANDY"}
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "Kernel.pbReceiveItem(::PBItems::RARECANDY)"], indent=0),
        cmd(T.CONTROL_SELF_SWITCH, ["A", 0], indent=1),
        cmd(T.ELSE_BRANCH, indent=0),  # present but empty in the real corpus shape
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands], map_id=32, event_id=27)
    assert "giveitem(ITEM_RARE_CANDY)" in res.text
    assert "if (var(VAR_RESULT) != 0) {" in res.text
    assert "} else {" not in res.text
    assert f"setflag({self_switch_flag_name(32, 27, 'A')})" in res.text


def test_receive_item_then_and_else_with_quantity(ctx: T.TranspileContext) -> None:
    ctx.items = {"POKeBALL": "ITEM_POKE_BALL"}
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "Kernel.pbReceiveItem(::PBItems::POKeBALL,5)"], indent=0),
        cmd(T.SHOW_TEXT, ["placeholder success text"], indent=1),
        cmd(T.ELSE_BRANCH, indent=0),
        cmd(T.SHOW_TEXT, ["placeholder failure text"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands])
    assert "giveitem(ITEM_POKE_BALL, 5)" in res.text
    assert "if (var(VAR_RESULT) != 0) {" in res.text
    assert "} else {" in res.text
    assert 'msgbox(format("placeholder success text"))' in res.text
    assert 'msgbox(format("placeholder failure text"))' in res.text


def test_receive_item_unknown_symbol_queues(ctx: T.TranspileContext) -> None:
    ctx.items = {"RARECANDY": "ITEM_RARE_CANDY"}  # MYSTERYTHING deliberately absent
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "Kernel.pbReceiveItem(::PBItems::MYSTERYTHING)"], indent=0),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "giveitem" not in res.text


# ----------------------------------------------------------------------------
# Feature 2d — align loops (code-112 wait-until-aligned idiom)
# ----------------------------------------------------------------------------


def _align_loop_commands(cond: str, move_step_code: int) -> list[dict]:
    return [
        cmd(T.LOOP, indent=0),
        cmd(T.CONDITIONAL_BRANCH, [12, cond], indent=1),
        cmd(T.BREAK_LOOP, indent=2),
        cmd(T.BRANCH_END, indent=1),
        cmd(T.SET_MOVE_ROUTE, [-1, _route([{"code": move_step_code}])], indent=1),
        cmd(T.WAIT_MOVE_COMPLETION, indent=1),
        cmd(T.REPEAT_ABOVE, indent=0),
    ]


def test_align_loop_y_variant(ctx: T.TranspileContext) -> None:
    commands = _align_loop_commands("$game_player.y>=15", 1)  # 1 = walk down
    res = run_event(ctx, [commands])
    assert "getplayerxy(VAR_TEMP_0, VAR_TEMP_1)" in res.text
    assert "while (var(VAR_TEMP_1) < 15) {" in res.text
    assert "applymovement(OBJ_EVENT_ID_PLAYER, Map032_EV005_Page1_Move1)" in res.text
    assert "movement Map032_EV005_Page1_Move1 {\n    walk_down\n}" in res.text
    assert res.unhandled == []


def test_align_loop_x_variant(ctx: T.TranspileContext) -> None:
    commands = _align_loop_commands("$game_player.x<=20", 3)  # 3 = walk right
    res = run_event(ctx, [commands])
    assert "while (var(VAR_TEMP_0) > 20) {" in res.text
    assert "applymovement(OBJ_EVENT_ID_PLAYER, Map032_EV005_Page1_Move1)" in res.text
    assert "movement Map032_EV005_Page1_Move1 {\n    walk_right\n}" in res.text
    assert res.unhandled == []


def test_align_loop_wrong_comparator_queues(ctx: T.TranspileContext) -> None:
    commands = _align_loop_commands("$game_player.y>15", 1)  # strict > not approved
    res = run_event(ctx, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.LOOP


def test_non_align_loop_shape_still_queues(ctx: T.TranspileContext) -> None:
    """A plain RMXP loop (no break/move-align shape) keeps the pre-existing
    v1 disposition: queue, subtree not emitted."""
    commands = [
        cmd(T.LOOP, indent=0),
        cmd(T.SHOW_TEXT, ["loop body placeholder"], indent=1),
        cmd(T.REPEAT_ABOVE, indent=0),
    ]
    res = run_event(ctx, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.LOOP
    assert "while (" not in res.text


# ----------------------------------------------------------------------------
# Feature 3 — code 207 emote tier
# ----------------------------------------------------------------------------


def test_show_animation_exclamation_on_player(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SHOW_ANIMATION, [-1, 17])]])
    assert "applymovement(OBJ_EVENT_ID_PLAYER, Common_Movement_ExclamationMark)" in res.text
    assert "waitmovement(0)" in res.text
    assert res.unhandled == []


def test_show_animation_exclamation_on_positive_local_id(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SHOW_ANIMATION, [75, 17])]])
    assert "applymovement(75, Common_Movement_ExclamationMark)" in res.text
    assert res.unhandled == []


def test_show_animation_question_mark_sibling_wired(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SHOW_ANIMATION, [-1, 19])]])
    assert "applymovement(OBJ_EVENT_ID_PLAYER, Common_Movement_QuestionMark)" in res.text
    assert res.unhandled == []


@pytest.mark.parametrize("animation_id", [104, 18])
def test_show_animation_unmapped_ids_queue(ctx: T.TranspileContext, animation_id: int) -> None:
    res = run_event(ctx, [[cmd(T.SHOW_ANIMATION, [76, animation_id])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_ANIMATION
    assert "Common_Movement_" not in res.text


def test_show_animation_self_target_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SHOW_ANIMATION, [0, 17])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SHOW_ANIMATION


# ----------------------------------------------------------------------------
# Feature 4 — canlose trainer battle idiom (type-12 pbTrainerBattle inside a
# 111), reference/guides/canlose_battle_pipeline_plan.md "Gap A — transpiler".
# Proven target shape: hand_conversions/Map050_EV019.pory (Theo's battle).
# ----------------------------------------------------------------------------


def _canlose_call(
    trainer_class: str = "YOUNGSTER",
    name: str = "Joey",
    defeat_text: str = "You beat me!",
    party_expr: str = "3",
    canlose: str = "true",
    double: str = "false",
) -> str:
    return (
        f'pbTrainerBattle(PBTrainers::{trainer_class},"{name}",'
        f'_I("{defeat_text}"),{double},{party_expr},{canlose})'
    )


def _canlose_commands(
    call: str, then_body: list[dict], else_body: list[dict] | None = None
) -> list[dict]:
    cmds = [cmd(T.CONDITIONAL_BRANCH, [12, call], indent=0)]
    cmds += [dict(c, indent=1) for c in then_body]
    if else_body is not None:
        cmds.append(cmd(T.ELSE_BRANCH, indent=0))
        cmds += [dict(c, indent=1) for c in else_body]
    cmds.append(cmd(T.BRANCH_END, indent=0))
    return cmds


def test_canlose_literal_party_emits_earlyrival_and_swapped_branches(
    ctx: T.TranspileContext,
) -> None:
    ctx.trainers = {("TRAINER_CLASS_YOUNGSTER", "Joey", 3): "TRAINER_JOEY_1"}
    commands = _canlose_commands(
        _canlose_call(),
        then_body=[cmd(T.CONTROL_SELF_SWITCH, ["A", 0])],  # RMXP then = WON
        else_body=[cmd(T.CONTROL_SELF_SWITCH, ["B", 0])],  # RMXP otherwise = LOST
    )
    res = run_event(ctx, [commands], map_id=32, event_id=5)

    assert (
        "trainerbattle_earlyrival(TRAINER_JOEY_1, RIVAL_BATTLE_HEAL_AFTER, "
        "Map032_EV005_Page1_CanloseDefeatText, "
        "Map032_EV005_Page1_CanloseVictoryText)"
    ) in res.text
    assert "if (var(VAR_RESULT) == 1) {" in res.text

    lines = [ln.strip() for ln in res.text.splitlines()]
    if_idx = lines.index("if (var(VAR_RESULT) == 1) {")
    else_idx = lines.index("} else {", if_idx)
    end_idx = lines.index("}", else_idx)
    lost_flag = self_switch_flag_name(32, 5, "B")
    won_flag = self_switch_flag_name(32, 5, "A")
    # VAR_RESULT==1 (lost) body must be the RMXP `otherwise` arm; the poryscript
    # `else` (won) body must be the RMXP `then` arm — branches SWAP polarity.
    assert f"setflag({lost_flag})" in lines[if_idx:else_idx]
    assert f"setflag({won_flag})" in lines[else_idx:end_idx]

    assert "text Map032_EV005_Page1_CanloseDefeatText {" in res.text
    assert 'format("You beat me!")' in res.text
    assert "text Map032_EV005_Page1_CanloseVictoryText {" in res.text
    # else block had no dialogue to lift -> generic fallback line
    assert 'format("Argh! I lost!")' in res.text
    assert res.unhandled == []


def test_canlose_pbget_plus_k_emits_switch_over_trainers(
    ctx: T.TranspileContext,
) -> None:
    ctx.registry.propose_var(151, "VAR_POKEMONTEST")
    ctx.trainers = {
        ("TRAINER_CLASS_RIVAL", "Theo", 19): "TRAINER_THEO_9",
        ("TRAINER_CLASS_RIVAL", "Theo", 20): "TRAINER_THEO_10",
        ("TRAINER_CLASS_RIVAL", "Theo", 21): "TRAINER_THEO_11",
    }
    commands = _canlose_commands(
        _canlose_call(
            trainer_class="RIVAL",
            name="Theo",
            defeat_text="B-but... how...",
            party_expr="pbGet(151)+18",
        ),
        then_body=[cmd(T.CONTROL_SELF_SWITCH, ["A", 0])],
        else_body=[cmd(T.SHOW_TEXT, ["Yes!! My first win!"])],
    )
    res = run_event(ctx, [commands], map_id=50, event_id=19)

    assert "switch (var(VAR_POKEMONTEST)) {" in res.text
    assert (
        "trainerbattle_earlyrival(TRAINER_THEO_9, RIVAL_BATTLE_HEAL_AFTER, "
        "Map050_EV019_Page1_CanloseDefeatText, Map050_EV019_Page1_CanloseVictoryText)"
        in res.text
    )
    assert "TRAINER_THEO_10" in res.text
    assert "TRAINER_THEO_11" in res.text
    assert "case 1:" in res.text
    assert "case 2:" in res.text
    assert "case 3:" in res.text
    assert "if (var(VAR_RESULT) == 1) {" in res.text
    # lifted from the RMXP otherwise (lost) block's own ShowText
    assert 'format("Yes!! My first win!")' in res.text
    assert res.unhandled == []


def test_canlose_false_falls_through_to_queue(ctx: T.TranspileContext) -> None:
    ctx.trainers = {("TRAINER_CLASS_YOUNGSTER", "Joey", 3): "TRAINER_JOEY_1"}
    commands = _canlose_commands(_canlose_call(canlose="false"), then_body=[], else_body=[])
    res = run_event(ctx, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "trainerbattle_earlyrival" not in res.text


def test_canlose_double_battle_falls_through_to_queue(ctx: T.TranspileContext) -> None:
    ctx.trainers = {("TRAINER_CLASS_YOUNGSTER", "Joey", 3): "TRAINER_JOEY_1"}
    call = _canlose_call() + "  # pbDoubleTrainerBattle marker"
    commands = _canlose_commands(call, then_body=[], else_body=[])
    res = run_event(ctx, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "trainerbattle_earlyrival" not in res.text


def test_canlose_unknown_trainer_falls_through_to_queue(ctx: T.TranspileContext) -> None:
    # ctx.trainers deliberately empty -- (class, name, party) has no entry
    commands = _canlose_commands(_canlose_call(), then_body=[], else_body=[])
    res = run_event(ctx, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "trainerbattle_earlyrival" not in res.text


def test_canlose_unrecognized_party_expr_falls_through_to_queue(
    ctx: T.TranspileContext,
) -> None:
    ctx.trainers = {("TRAINER_CLASS_YOUNGSTER", "Joey", 3): "TRAINER_JOEY_1"}
    commands = _canlose_commands(
        _canlose_call(party_expr="pbGet(151)*2"), then_body=[], else_body=[]
    )
    res = run_event(ctx, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "trainerbattle_earlyrival" not in res.text


# ----------------------------------------------------------------------------
# real-compile smoke test (real poryscript binary; skip when absent)
# ----------------------------------------------------------------------------


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_idiom_shapes_compile_through_real_poryscript() -> None:
    """One combined script exercising every new construct's syntax: getplayerxy,
    a while loop, a bare giveitem, msgbox(.., MSGBOX_AUTOCLOSE), and an emote
    applymovement — the shapes this module's idiom emitters actually produce."""
    script = (
        "script Test {\n"
        "    getplayerxy(VAR_TEMP_0, VAR_TEMP_1)\n"
        "    while (var(VAR_TEMP_1) < 15) {\n"
        "        applymovement(OBJ_EVENT_ID_PLAYER, Test_Move1)\n"
        "        waitmovement(0)\n"
        "        getplayerxy(VAR_TEMP_0, VAR_TEMP_1)\n"
        "    }\n"
        "    giveitem(ITEM_POTION)\n"
        '    msgbox("Bye!", MSGBOX_AUTOCLOSE)\n'
        "    applymovement(OBJ_EVENT_ID_PLAYER, Common_Movement_ExclamationMark)\n"
        "    waitmovement(0)\n"
        "    end\n"
        "}\n"
        "\n"
        "movement Test_Move1 {\n"
        "    walk_down\n"
        "}\n"
    )
    result = poryscript.compile_script(script)
    assert result.ok, result.stderr


# ----------------------------------------------------------------------------
# Consecutive move routes on one actor (reference/findings/
# hand_conversion_audit_2026-07-31.md §5.2)
# ----------------------------------------------------------------------------


def test_consecutive_routes_same_target_merge(ctx: T.TranspileContext) -> None:
    """Two 209s on one actor with no 210 between them fuse into one movement.

    The fork DROPS the second applymovement (the object's movement is still in
    flight), so emitting both verbatim silently loses the second route — the
    Map050 EV019 "Theo stops one tile short" defect.
    """
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [20, _route([{"code": 4}])]),
        cmd(T.SET_MOVE_ROUTE, [20, _route([{"code": 37}, {"code": 4}])]),
        cmd(T.WAIT_MOVE_COMPLETION),
    ]])
    assert res.text.count("applymovement(20,") == 1
    # code 37 (through on) is a SOFT-C drop; both walk_ups survive the fuse.
    assert res.text.count("walk_up") == 2
    assert res.unhandled == []


def test_consecutive_routes_different_targets_do_not_merge(
    ctx: T.TranspileContext,
) -> None:
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [20, _route([{"code": 4}])]),
        cmd(T.SET_MOVE_ROUTE, [-1, _route([{"code": 2}])]),
        cmd(T.WAIT_MOVE_COMPLETION),
    ]])
    assert res.text.count("applymovement(") == 2
    assert "applymovement(20," in res.text
    assert "applymovement(OBJ_EVENT_ID_PLAYER," in res.text


def test_routes_split_by_a_wait_do_not_merge(ctx: T.TranspileContext) -> None:
    """A 210 between them means the author DID want two separate motions."""
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [20, _route([{"code": 4}])]),
        cmd(T.WAIT_MOVE_COMPLETION),
        cmd(T.SET_MOVE_ROUTE, [20, _route([{"code": 4}])]),
        cmd(T.WAIT_MOVE_COMPLETION),
    ]])
    assert res.text.count("applymovement(20,") == 2


# ----------------------------------------------------------------------------
# Starter grant: randomizer collapse + guarded one-line Ruby
# ----------------------------------------------------------------------------


def test_randomizer_branch_emits_else_arm_only(ctx: T.TranspileContext) -> None:
    """The normal-play arm is the RMXP else block. Emitting the then block (or
    queuing the whole conditional, as before) loses the starter grant."""
    res = run_event(ctx, [[
        cmd(T.CONDITIONAL_BRANCH, [12, "$PokemonGlobal.randomizer"]),
        cmd(T.SHOW_TEXT, ["then-arm"], indent=1),
        cmd(411, [], indent=0),
        cmd(T.SHOW_TEXT, ["else-arm"], indent=1),
        cmd(412, [], indent=0),
    ]])
    assert "else-arm" in res.text
    assert "then-arm" not in res.text
    assert res.unhandled == []


def test_guarded_add_pokemon_emits_givemon_and_menu_flag(
    ctx: T.TranspileContext,
) -> None:
    ctx.species = {"ORCHYNX": "SPECIES_ORCHYNX"}
    ctx.staged_species = frozenset({"SPECIES_ORCHYNX"})
    ctx.registry.propose_var(151, "VAR_POKEMONTEST")
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ["pbAddPokemon(PBSpecies::ORCHYNX,5) if $game_variables[151]==1"]),
    ]])
    assert "givemon(SPECIES_ORCHYNX, 5)" in res.text
    # Emerald gates the START-menu POKEMON option on this; Essentials doesn't.
    assert "setflag(FLAG_SYS_POKEMON_GET)" in res.text
    assert "== 1) {" in res.text
    assert res.unhandled == []


def test_add_pokemon_unstaged_species_queues(ctx: T.TranspileContext) -> None:
    """Id-mapped but never staged: emitting the constant would invent a symbol
    the fork doesn't define (CLAUDE.md §4.7 forward gate)."""
    ctx.species = {"URAYNE": "SPECIES_URAYNE"}
    ctx.staged_species = frozenset()
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbAddPokemon(PBSpecies::URAYNE,5)"])]])
    assert "givemon" not in res.text
    assert len(res.unhandled) == 1


def test_guarded_switch_assignment_uses_the_registry(
    ctx: T.TranspileContext,
) -> None:
    ctx.registry.propose_flag(61, "FLAG_HAS_ORCHYNX")
    ctx.registry.propose_var(151, "VAR_POKEMONTEST")
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ["$game_switches[61] = true if $game_variables[151]==1"]),
    ]])
    assert "setflag(FLAG_" in res.text
    assert res.unhandled == []


def test_unnamed_switch_assignment_still_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["$game_switches[9999] = true"])]])
    assert "setflag" not in res.text
    assert len(res.unhandled) == 1


# ----------------------------------------------------------------------------
# code-41 live sprite swap (RPG2GBA_SetObjectEventGfx)
# ----------------------------------------------------------------------------


def test_change_graphic_emits_the_gfx_special(ctx: T.TranspileContext) -> None:
    ctx.npc_gfx = {"PU-Machine": "OBJ_EVENT_GFX_URANIUM_PU_MACHINE"}
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [19, _route([
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Machine", 0, 6, 2]},
        ])]),
        cmd(T.WAIT_MOVE_COMPLETION),
    ]])
    assert "setvar(VAR_0x8004, 19)" in res.text
    assert "setvar(VAR_0x8005, OBJ_EVENT_GFX_URANIUM_PU_MACHINE)" in res.text
    assert "special(RPG2GBA_SetObjectEventGfx)" in res.text
    assert res.unhandled == []


def test_change_graphic_mid_route_splits_the_movement(
    ctx: T.TranspileContext,
) -> None:
    """Steps either side of the swap stay as movement; the swap lands between."""
    ctx.npc_gfx = {"PU-Ball": "OBJ_EVENT_GFX_URANIUM_PU_BALL"}
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [7, _route([
            {"code": 4},
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Ball", 0, 6, 2]},
            {"code": 1},
        ])]),
    ]])
    gfx_at = res.text.index("special(RPG2GBA_SetObjectEventGfx)")
    assert res.text.count("applymovement(7,") == 2
    assert res.text.index("applymovement(7,") < gfx_at
    assert res.text.rindex("applymovement(7,") > gfx_at
    assert res.unhandled == []


def test_change_graphic_unmapped_sheet_queues(ctx: T.TranspileContext) -> None:
    """An unmapped sheet must not invent a constant (CLAUDE.md §4.3)."""
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [19, _route([
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Unknown", 0, 6, 2]},
        ])]),
    ]])
    assert "RPG2GBA_SetObjectEventGfx" not in res.text
    assert len(res.unhandled) == 1
    assert "npc_gfx_map.json" in res.unhandled[0].description


# ----------------------------------------------------------------------------
# pbStarterSelector full-screen reveal
# ----------------------------------------------------------------------------


_SCENE = {
    "starters": [
        {"index": 0, "internal_name": "AAA", "reveal": "A!", "player_speech": ["a1"]},
        {"index": 1, "internal_name": "BBB", "reveal": "B!", "player_speech": ["b1"]},
        {"index": 2, "internal_name": "CCC", "reveal": "C!", "player_speech": ["c1"]},
    ],
    "theo_speech": ["t1", "t2"],
}


def _starter_ctx(ctx: T.TranspileContext) -> T.TranspileContext:
    ctx.starter_scene = _SCENE
    ctx.species = {"AAA": "SPECIES_AAA", "BBB": "SPECIES_BBB", "CCC": "SPECIES_CCC"}
    ctx.staged_species = frozenset({"SPECIES_AAA", "SPECIES_BBB", "SPECIES_CCC"})
    ctx.registry.propose_var(151, "VAR_POKEMONTEST")
    return ctx


def test_starter_selector_replays_tracked_arithmetic(
    ctx: T.TranspileContext,
) -> None:
    """x = pbGet(151) - 2, wrapping -1 to 2 — the rock-paper-scissors counter
    pick. Source value 1 must land on index 2, not index -1."""
    _starter_ctx(ctx)
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ["x=pbGet(151)"]),
        cmd(T.SCRIPT_CONT, ["x-=2"]),
        cmd(T.SCRIPT_CONT, ["x=2 if x==-1"]),
        cmd(T.SCRIPT_CONT, ["pbStarterSelector(x,true)"]),
    ]])
    case1 = res.text.index("case 1:")
    case2 = res.text.index("case 2:")
    assert "SPECIES_CCC" in res.text[case1:case2]      # 1 - 2 = -1 -> wraps to 2
    assert "SPECIES_AAA" in res.text[case2:]           # 2 - 2 = 0
    assert "showmonpic" in res.text and "hidemonpic" in res.text
    assert res.unhandled == []


def test_starter_selector_theo_variant_uses_theo_speech(
    ctx: T.TranspileContext,
) -> None:
    _starter_ctx(ctx)
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ["x=pbGet(151)"]),
        cmd(T.SCRIPT_CONT, ["x-=1"]),
        cmd(T.SCRIPT_CONT, ["pbStarterSelector(x,true)"]),
    ]])
    assert "t1" in res.text and "t2" in res.text
    assert "a1" not in res.text


def test_starter_selector_arithmetic_out_of_range_queues(
    ctx: T.TranspileContext,
) -> None:
    """Offset 0 over a 1-based source variable maps the last value past the end
    of the starter list — a sign the tracked arithmetic is wrong. Emit nothing
    rather than a switch missing an arm (CLAUDE.md §4.5)."""
    _starter_ctx(ctx)
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ["x=pbGet(151)"]),
        cmd(T.SCRIPT_CONT, ["pbStarterSelector(x,true)"]),
    ]])
    assert "showmonpic" not in res.text
    assert len(res.unhandled) == 1


def test_starter_selector_player_variant_uses_per_starter_speech(
    ctx: T.TranspileContext,
) -> None:
    _starter_ctx(ctx)
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ["x=pbGet(151)"]),
        cmd(T.SCRIPT_CONT, ["x-=1"]),
        cmd(T.SCRIPT_CONT, ["pbStarterSelector(x)"]),
    ]])
    assert "a1" in res.text and "b1" in res.text and "c1" in res.text
    assert "t1" not in res.text


def test_starter_selector_without_scene_data_queues(
    ctx: T.TranspileContext,
) -> None:
    ctx.registry.propose_var(151, "VAR_POKEMONTEST")
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ["x=pbGet(151)"]),
        cmd(T.SCRIPT_CONT, ["pbStarterSelector(x,true)"]),
    ]])
    assert "showmonpic" not in res.text
    assert len(res.unhandled) == 1


def test_starter_selector_untracked_local_queues(ctx: T.TranspileContext) -> None:
    """No preceding pbGet — the argument's provenance is unknown, so guessing
    a variable would be a silent default (CLAUDE.md §4.5)."""
    _starter_ctx(ctx)
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbStarterSelector(q,true)"])]])
    assert "showmonpic" not in res.text
    assert len(res.unhandled) == 1
