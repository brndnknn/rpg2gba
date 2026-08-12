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


@pytest.mark.parametrize("animation_id", [999, 7])
def test_show_animation_unmapped_ids_queue(ctx: T.TranspileContext, animation_id: int) -> None:
    """104 ("Rustle" -> exclamation) and 18 ("EM scratch" -> decided drop) are
    no longer in this bucket — see test_emote_anim_104_maps_to_exclamation /
    test_emote_anim_18_drops_with_breadcrumb_not_a_queue_entry."""
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
# code-41 live sprite swap (setobjectgfx / RPG2GBA_SetObjectEventGfx)
# ----------------------------------------------------------------------------


def test_change_graphic_emits_the_gfx_special(ctx: T.TranspileContext) -> None:
    ctx.npc_gfx = {"PU-Machine": "OBJ_EVENT_GFX_URANIUM_PU_MACHINE"}
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [19, _route([
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Machine", 0, 6, 2]},
        ])]),
        cmd(T.WAIT_MOVE_COMPLETION),
    ]])
    assert "setobjectgfx(19, OBJ_EVENT_GFX_URANIUM_PU_MACHINE)" in res.text
    # RMXP direction 6 = right: props use facing to pick a visual state, and the
    # converted sheet has the same four rows, so it carries through as facing.
    assert "face_right" in res.text
    # ...but pattern 2 (the frame within that row) has no analog, and saying so
    # is the point: a sheet-only swap would have been a silent no-op.
    assert len(res.unhandled) == 1
    assert "frame 2" in res.unhandled[0].description


def test_change_graphic_direction_only_needs_no_frame_note(
    ctx: T.TranspileContext,
) -> None:
    ctx.npc_gfx = {"PU-Machine": "OBJ_EVENT_GFX_URANIUM_PU_MACHINE"}
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [19, _route([
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Machine", 0, 8, 0]},
        ])]),
    ]])
    assert "face_up" in res.text
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
    gfx_at = res.text.index("setobjectgfx(7,")
    # Three now: the steps before, the swap's own facing, and the steps after.
    assert res.text.count("applymovement(7,") == 3
    assert res.text.index("applymovement(7,") < gfx_at
    assert res.text.rindex("applymovement(7,") > gfx_at
    assert [q.description for q in res.unhandled] == [
        res.unhandled[0].description]  # only the frame-drop note
    assert "frame 2" in res.unhandled[0].description


_MACHINE_STATES = {
    (2, 0): "OBJ_EVENT_GFX_URANIUM_PU_MACHINE",
    (2, 1): "OBJ_EVENT_GFX_URANIUM_PU_MACHINE_D2P1",
    (6, 2): "OBJ_EVENT_GFX_URANIUM_PU_MACHINE_D6P2",
}


def test_change_graphic_on_a_multi_state_sheet_swaps_to_that_state(
    ctx: T.TranspileContext,
) -> None:
    """The machine in Professor Bamb'o's lab (SLICE1_TODO #25): RMXP re-poses a
    prop by keeping the sheet and moving (direction, pattern). When the sprite
    pass emitted one frame, the swap was a visible no-op; with per-state art the
    swap targets the state's own constant — no facing, nothing dropped."""
    ctx.npc_gfx = {"PU-Machine": "OBJ_EVENT_GFX_URANIUM_PU_MACHINE"}
    ctx.npc_gfx_states = {"PU-Machine": _MACHINE_STATES}
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [19, _route([
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Machine", 0, 6, 2]},
        ])]),
    ]])
    assert "setobjectgfx(19, OBJ_EVENT_GFX_URANIUM_PU_MACHINE_D6P2)" in res.text
    # A state constant carries the direction, so no facing block is needed...
    assert "face_right" not in res.text
    # ...and the pattern is no longer a drop.
    assert res.unhandled == []


def test_change_graphic_to_the_idle_state_uses_the_bare_constant(
    ctx: T.TranspileContext,
) -> None:
    ctx.npc_gfx = {"PU-Machine": "OBJ_EVENT_GFX_URANIUM_PU_MACHINE"}
    ctx.npc_gfx_states = {"PU-Machine": _MACHINE_STATES}
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [19, _route([
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Machine", 0, 2, 0]},
        ])]),
    ]])
    assert "setobjectgfx(19, OBJ_EVENT_GFX_URANIUM_PU_MACHINE)" in res.text
    assert res.unhandled == []


def test_gfx_swap_target_survives_the_staging_remap(
    ctx: T.TranspileContext,
) -> None:
    """The emitter and the staging remap are coupled: the swap's target is the
    `setobjectgfx` macro call's first argument, so `local_id_remap` has to
    recognise the emitted shape or the RMXP id reaches the ROM unrewritten and
    the special silently no-ops (the machine bug, boot-walked twice). Run real
    output through the real remap so a change to either side fails here."""
    from rpg2gba.tileset_converter.local_id_remap import remap_pory_object_ids

    ctx.npc_gfx = {"PU-Machine": "OBJ_EVENT_GFX_URANIUM_PU_MACHINE"}
    ctx.npc_gfx_states = {"PU-Machine": _MACHINE_STATES}
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [19, _route([
            {"code": 4},
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Machine", 0, 6, 2]},
        ])]),
    ]])

    remapped = remap_pory_object_ids(res.text, {"19": 3}, source_name="Map050")

    assert "setobjectgfx(3," in remapped.text
    assert "setobjectgfx(19," not in remapped.text


def test_change_graphic_to_a_state_with_no_art_queues(
    ctx: T.TranspileContext,
) -> None:
    """A state the sheet's art has no cell for has no frame in the ROM, so it
    must queue rather than target a constant nothing defines (§4.5)."""
    ctx.npc_gfx = {"PU-Machine": "OBJ_EVENT_GFX_URANIUM_PU_MACHINE"}
    ctx.npc_gfx_states = {"PU-Machine": _MACHINE_STATES}
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [19, _route([
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Machine", 0, 8, 3]},
        ])]),
    ]])
    assert "RPG2GBA_SetObjectEventGfx" not in res.text
    assert len(res.unhandled) == 1
    assert "no cell for" in res.unhandled[0].description


def test_change_graphic_mid_route_on_a_multi_state_sheet_still_splits(
    ctx: T.TranspileContext,
) -> None:
    """Only the swap's own facing block goes away — the ordinary steps either
    side of it still become their own applymovement runs."""
    ctx.npc_gfx = {"PU-Machine": "OBJ_EVENT_GFX_URANIUM_PU_MACHINE"}
    ctx.npc_gfx_states = {"PU-Machine": _MACHINE_STATES}
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [19, _route([
            {"code": 4},
            {"code": T.CHANGE_GRAPHIC, "parameters": ["PU-Machine", 0, 6, 2]},
            {"code": 1},
        ])]),
    ]])
    gfx_at = res.text.index("setobjectgfx(19,")
    assert res.text.count("applymovement(19,") == 2
    assert res.text.index("applymovement(19,") < gfx_at
    assert res.text.rindex("applymovement(19,") > gfx_at
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
    # The reveal line is what identifies the arm's starter now that the sprite
    # is the gift ceremony's job.
    assert "C!" in res.text[case1:case2]               # 1 - 2 = -1 -> wraps to 2
    assert "A!" in res.text[case2:]                    # 2 - 2 = 0
    assert res.unhandled == []


def test_starter_selector_leaves_the_sprite_to_the_gift_ceremony(
    ctx: T.TranspileContext,
) -> None:
    """The reveal is speech only. pbAddPokemon shows the same mon a few lines
    later (with the nickname prompt), and two pop-ups for one starter is the
    duplication the 2026-08-01 boot-walk called out."""
    _starter_ctx(ctx)
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ["x=pbGet(151)"]),
        cmd(T.SCRIPT_CONT, ["x-=1"]),
        cmd(T.SCRIPT_CONT, ["pbStarterSelector(x)"]),
    ]])
    assert "showmonpic" not in res.text and "hidemonpic" not in res.text
    assert "a1" in res.text                    # the speech itself still lands
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
    assert "fadescreen" not in res.text  # the reveal's own wrapper: nothing emitted
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
    assert "fadescreen" not in res.text  # the reveal's own wrapper: nothing emitted
    assert len(res.unhandled) == 1


def test_starter_selector_untracked_local_queues(ctx: T.TranspileContext) -> None:
    """No preceding pbGet — the argument's provenance is unknown, so guessing
    a variable would be a silent default (CLAUDE.md §4.5)."""
    _starter_ctx(ctx)
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbStarterSelector(q,true)"])]])
    assert "fadescreen" not in res.text  # the reveal's own wrapper: nothing emitted
    assert len(res.unhandled) == 1


# ----------------------------------------------------------------------------
# RMXP labels (118) / jump-to-label (119) — basic-block hoisting
# ----------------------------------------------------------------------------


def test_label_region_running_to_page_end_is_hoisted(ctx: T.TranspileContext) -> None:
    """The fall-through and the jump both become `goto` into one block."""
    ctx.registry.propose_flag(7, "FLAG_RETAKE")
    out = run_event(ctx, [[
        cmd(T.CONDITIONAL_BRANCH, [0, 7, 0]),
        cmd(T.JUMP_TO_LABEL, ["Start"], indent=1),
        cmd(T.BRANCH_END),
        cmd(T.SHOW_TEXT, ["intro"]),
        cmd(T.LABEL, ["Start"]),
        cmd(T.SHOW_TEXT, ["body"]),
    ]], trigger=3)
    assert "goto(Map050_EV005_Page1_Start)" not in out.text  # not this map/event
    assert "script Map032_EV005_Page1_Start {" in out.text
    assert out.text.count("goto(Map032_EV005_Page1_Start)") == 2
    # The hoisted block carries the trigger's epilogue: entered by goto with the
    # lock already held, it would otherwise end without ever releasing.
    body = out.text.split("script Map032_EV005_Page1_Start {")[1]
    assert "releaseall" in body
    assert not out.unhandled


def test_hoisted_region_ending_in_exit_event_keeps_one_terminator(
    ctx: T.TranspileContext,
) -> None:
    out = run_event(ctx, [[
        cmd(T.SHOW_CHOICES, [["Yes", "No"]]),
        cmd(T.CHOICE_WHEN, [0, "Yes"]),
        cmd(T.LABEL, ["Go"], indent=1),
        cmd(T.SHOW_TEXT, ["body"], indent=1),
        cmd(T.EXIT_EVENT, [], indent=1),
        cmd(T.CHOICE_WHEN, [1, "No"]),
        cmd(T.SHOW_TEXT, ["nope"], indent=1),
        cmd(T.CHOICES_END),
    ]], trigger=3)
    block = out.text.split("script Map032_EV005_Page1_Go {")[1].split("\n}")[0]
    assert block.strip().splitlines()[-1].strip() == "end"
    # release goes BEFORE the terminator, not after it as dead code.
    assert block.index("releaseall") < block.rindex("end")
    assert block.count("end") == 1


def test_label_falling_out_of_a_choice_arm_queues(ctx: T.TranspileContext) -> None:
    """No continuation exists for a region that dedents back into its arm."""
    out = run_event(ctx, [[
        cmd(T.SHOW_CHOICES, [["Yes", "No"]]),
        cmd(T.CHOICE_WHEN, [0, "Yes"]),
        cmd(T.LABEL, ["Go"], indent=1),
        cmd(T.SHOW_TEXT, ["body"], indent=1),
        cmd(T.CHOICE_WHEN, [1, "No"]),
        cmd(T.SHOW_TEXT, ["nope"], indent=1),
        cmd(T.CHOICES_END),
        cmd(T.SHOW_TEXT, ["after"]),
    ]], trigger=3)
    assert "script Map032_EV005_Page1_Go {" not in out.text
    assert any(q.command_code == T.LABEL for q in out.unhandled)


def test_two_labels_on_one_page_queue_rather_than_nest(
    ctx: T.TranspileContext,
) -> None:
    out = run_event(ctx, [[
        cmd(T.LABEL, ["A"]),
        cmd(T.SHOW_TEXT, ["a"]),
        cmd(T.LABEL, ["B"]),
        cmd(T.SHOW_TEXT, ["b"]),
    ]], trigger=3)
    assert T.hoistable_label_region([
        cmd(T.LABEL, ["A"]), cmd(T.LABEL, ["B"])]) is None
    assert len([q for q in out.unhandled if q.command_code == T.LABEL]) == 2


def test_label_block_suffix_sanitizes_spaces() -> None:
    assert T._label_block_suffix("Choice Made") == "ChoiceMade"
    assert T._label_block_suffix("pergunta") == "Pergunta"


# ----------------------------------------------------------------------------
# Array-valued game variables — the Map050 EV005 aptitude tally
# ----------------------------------------------------------------------------


def _tally_ctx() -> T.TranspileContext:
    reg = FlagRegistry()
    reg.propose_var(2, "VAR_TEMP_MOVE_CHOICE")
    reg.propose_var(151, "VAR_POKEMONTEST")
    return T.TranspileContext(registry=reg)


def test_array_literal_binds_one_scratch_var_per_element() -> None:
    ctx = _tally_ctx()
    out = run_event(ctx, [[
        cmd(T.SCRIPT, ["$game_variables[151]=[0,0,0]"]),
    ]], trigger=3)
    for var in ("VAR_TEMP_3", "VAR_TEMP_4", "VAR_TEMP_5"):
        assert f"setvar({var}, 0)" in out.text
    assert not out.unhandled


def test_indexed_bump_switches_on_the_index_variable() -> None:
    ctx = _tally_ctx()
    out = run_event(ctx, [[
        cmd(T.SCRIPT, ["$game_variables[151]=[0,0,0]"]),
        cmd(T.SCRIPT, ["pbGet(151)[pbGet(2)]+=1"]),
    ]], trigger=3)
    assert "switch (var(VAR_TEMP_MOVE_CHOICE)) {" in out.text
    assert "addvar(VAR_TEMP_4, 1)" in out.text
    assert not out.unhandled


def test_bump_without_a_bound_array_queues() -> None:
    ctx = _tally_ctx()
    out = run_event(ctx, [[
        cmd(T.SCRIPT, ["pbGet(151)[pbGet(2)]+=1"]),
    ]], trigger=3)
    assert out.unhandled


def test_argmax_with_swap_emits_the_sign_test_chain() -> None:
    ctx = _tally_ctx()
    out = run_event(ctx, [[
        cmd(T.SCRIPT, ["$game_variables[151]=[0,0,0]"]),
        cmd(T.SCRIPT, ["x=pbGet(151).index(pbGet(151).max)"]),
        cmd(T.SCRIPT, ["if x==1"]),
        cmd(T.SCRIPT_CONT, ["x=0"]),
        cmd(T.SCRIPT_CONT, ["elsif x==0"]),
        cmd(T.SCRIPT_CONT, ["x=1"]),
        cmd(T.SCRIPT_CONT, ["end"]),
        cmd(T.SCRIPT_CONT, ["$game_variables[151]=x"]),
    ]], trigger=3)
    # Default is the LAST bucket (Ruby ties resolve to the lowest index, so the
    # earlier buckets only win on a >= test).
    assert "setvar(VAR_POKEMONTEST, 2)" in out.text
    # The 0<->1 swap is applied to the emitted indices, not to a runtime var.
    assert "setvar(VAR_POKEMONTEST, 0)" in out.text  # bucket 1 -> 0
    assert "setvar(VAR_POKEMONTEST, 1)" in out.text  # bucket 0 -> 1
    assert "copyvar(VAR_RESULT, VAR_TEMP_4)" in out.text
    assert "subvar(VAR_RESULT, VAR_TEMP_5)" in out.text
    assert not out.unhandled


def test_argmax_sign_test_never_uses_the_special_var_literal() -> None:
    """32768 is VAR_0x8000: `compare` would silently switch to var-vs-var.

    This is the 2026-07-21 always-Eletux bug; the constant is the fix.
    """
    assert T._SIGN_TEST_MAX == 32767
    ctx = _tally_ctx()
    out = run_event(ctx, [[
        cmd(T.SCRIPT, ["$game_variables[151]=[0,0,0]"]),
        cmd(T.SCRIPT, ["x=pbGet(151).index(pbGet(151).max)"]),
        cmd(T.SCRIPT, ["$game_variables[151]=x"]),
    ]], trigger=3)
    assert "32768" not in out.text
    assert "32767" in out.text


def test_aptitude_tally_is_still_one_of_a_kind() -> None:
    """The idiom is deliberately narrow: one site in the whole corpus.

    If a second one appears, the shortcuts above (three buckets, VAR_TEMP_3/4/5,
    a hardcoded >= chain) need re-deriving rather than silently reusing.
    """
    import json
    import re
    from pathlib import Path

    maps = Path("output/uranium-build/maps")
    if not maps.is_dir():
        pytest.skip("map JSON not generated")
    literal = re.compile(r"\$game_variables\[\d+\]\s*=\s*\[")
    argmax = re.compile(r"\.index\(.*\.max\)")
    sites: set[tuple[str, int]] = set()
    for path in maps.glob("Map*.json"):
        for ev in json.loads(path.read_text(encoding="utf-8")).get("events", []):
            for page in ev.get("pages", []):
                for c in page.get("list", []):
                    if c["code"] in (T.SCRIPT, T.SCRIPT_CONT):
                        p = c.get("parameters") or []
                        s = p[0] if p and isinstance(p[0], str) else ""
                        if literal.search(s) or argmax.search(s):
                            sites.add((path.stem, ev["id"]))
    assert sites == {("Map050", 5)}, sites


# ----------------------------------------------------------------------------
# pbAddPokemon — the gift ceremony (sprite + fanfare + nickname prompt)
# ----------------------------------------------------------------------------


def _gift_ctx() -> T.TranspileContext:
    ctx = T.TranspileContext(registry=FlagRegistry())
    ctx.species = {"ORCHYNX": "SPECIES_ORCHYNX"}
    ctx.staged_species = {"SPECIES_ORCHYNX"}
    return ctx


def test_add_pokemon_shows_the_species_and_offers_a_nickname() -> None:
    """Essentials' pbAddPokemon is a ceremony, not a bare party add."""
    ctx = _gift_ctx()
    out = run_event(ctx, [[
        cmd(T.SCRIPT, ["pbAddPokemon(PBSpecies::ORCHYNX,5)"]),
    ]], trigger=3)
    for line in (
        "bufferspeciesname(STR_VAR_1, SPECIES_ORCHYNX)",
        "showmonpic(SPECIES_ORCHYNX, 10, 3)",
        "givemon(SPECIES_ORCHYNX, 5)",
        "playfanfare(MUS_OBTAIN_ITEM)",
        "waitfanfare",
        "msgbox(gText_NicknameThisPokemon, MSGBOX_YESNO)",
        "call(Common_EventScript_NameReceivedPartyMon)",
        "hidemonpic",
    ):
        assert line in out.text, line
    # The sprite must go up BEFORE the mon is handed over, and come down after.
    assert out.text.index("showmonpic") < out.text.index("givemon(")
    assert out.text.rindex("hidemonpic") > out.text.index("givemon(")
    assert not out.unhandled


def test_add_pokemon_handles_a_full_party_and_a_full_pc() -> None:
    ctx = _gift_ctx()
    out = run_event(ctx, [[
        cmd(T.SCRIPT, ["pbAddPokemon(PBSpecies::ORCHYNX,5)"]),
    ]], trigger=3)
    # Party full -> box, with the species buffered for the "sent to PC" text.
    assert "setvar(VAR_TEMP_TRANSFERRED_SPECIES, SPECIES_ORCHYNX)" in out.text
    assert "call(Common_EventScript_NameReceivedBoxMon)" in out.text
    assert "call(Common_EventScript_TransferredToPC)" in out.text
    # Boxes full too -> vanilla's own bail-out, and the sprite comes down first.
    assert "goto(Common_EventScript_NoMoreRoomForPokemon)" in out.text
    cant = out.text.index("MON_CANT_GIVE")
    assert "hidemonpic" in out.text[cant:cant + 120]


def test_add_pokemon_silent_stays_a_bare_givemon() -> None:
    """pbAddPokemonSilent is the form that deliberately has no ceremony."""
    ctx = _gift_ctx()
    out = run_event(ctx, [[
        cmd(T.SCRIPT, ["pbAddPokemonSilent(PBSpecies::ORCHYNX,5)"]),
    ]], trigger=3)
    assert "givemon(SPECIES_ORCHYNX, 5)" in out.text
    assert "setflag(FLAG_SYS_POKEMON_GET)" in out.text
    for absent in ("showmonpic", "playfanfare", "gText_NicknameThisPokemon"):
        assert absent not in out.text
    assert not out.unhandled


def test_add_pokemon_unstaged_species_still_queues() -> None:
    """No ceremony for a species the fork doesn't define (§4.3)."""
    ctx = _gift_ctx()
    out = run_event(ctx, [[
        cmd(T.SCRIPT, ["pbAddPokemon(PBSpecies::NOTSTAGED,5)"]),
    ]], trigger=3)
    assert "givemon" not in out.text
    assert out.unhandled


# ----------------------------------------------------------------------------
# Map032 EV9 retirement — player-position guard, move-token additions,
# forward/backward gesture, Pokédex grant, emote table, string readback
# ----------------------------------------------------------------------------


def test_player_position_x_equal_idiom(ctx: T.TranspileContext) -> None:
    """``$game_player.x==17`` — a one-shot boundary guard with no else-arm;
    the guarded content is a road-sign message + early exit, and anything
    after the ``if`` still runs on the non-matching path."""
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "$game_player.x==17"], indent=0),
        cmd(T.SHOW_TEXT, ["sign text"], indent=1),
        cmd(T.BRANCH_END, indent=0),
        cmd(T.SHOW_TEXT, ["after the guard"], indent=0),
    ]
    res = run_event(ctx, [commands])
    assert "getplayerxy(VAR_TEMP_0, VAR_TEMP_1)" in res.text
    assert "if (var(VAR_TEMP_0) == 17) {" in res.text
    assert 'msgbox(format("sign text"))' in res.text
    assert 'msgbox(format("after the guard"))' in res.text
    assert res.unhandled == []


def test_player_position_y_lte_idiom(ctx: T.TranspileContext) -> None:
    """``$game_player.y<=43`` — same idiom, different axis/operator."""
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "$game_player.y<=43"], indent=0),
        cmd(T.SHOW_TEXT, ["reposition"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands])
    assert "if (var(VAR_TEMP_1) <= 43) {" in res.text
    assert res.unhandled == []


def test_player_position_other_operator_still_queues(ctx: T.TranspileContext) -> None:
    """Anything outside ``==``/``<=``/``>=`` over ``$game_player.x``/``y``
    falls through to the generic script-condition queue."""
    commands = [
        cmd(T.CONDITIONAL_BRANCH, [12, "$game_player.x<17"], indent=0),
        cmd(T.SHOW_TEXT, ["never"], indent=1),
        cmd(T.BRANCH_END, indent=0),
    ]
    res = run_event(ctx, [commands])
    assert "getplayerxy" not in res.text
    assert len(res.unhandled) == 1


def test_move_route_disable_and_restore_anim(ctx: T.TranspileContext) -> None:
    """Codes 32/31 (``@walk_anime`` off/on) — the fork's own
    ``disable_anim``/``restore_anim`` movement actions freeze/unfreeze the
    walking animation, an exact analog (event_object_movement.c
    ``MovementAction_DisableAnimation_Step0`` sets ``inanimate = TRUE``)."""
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [5, _route([{"code": 32}, {"code": 31}])]),
    ]])
    assert "disable_anim" in res.text
    assert "restore_anim" in res.text
    assert res.unhandled == []


def test_move_route_step_anime_toggle_drops(ctx: T.TranspileContext) -> None:
    """Codes 33/34 (``@step_anime`` on/off — continuous idle animation) have
    no per-step fork analog and drop silently, same disposition as the other
    SOFT-C physics toggles (30/37/38/43/44)."""
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [5, _route([{"code": 18}, {"code": 34}])]),
    ]])
    assert res.unhandled == []
    # face_right (18) survives; nothing stands in for the dropped 34.
    movement_block = res.text[res.text.index("movement "):]
    assert "face_right" in movement_block


def test_forward_backward_gesture_idiom(ctx: T.TranspileContext) -> None:
    """RMXP move-codes 12 (1 Step Forward) + 13 (1 Step Backward), back to
    back — a facing-relative, zero-net-displacement bob with no absolute-
    direction fork token. Substitutes the fork's own same-tile gesture."""
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [5, _route([{"code": 12}, {"code": 13}])]),
    ]])
    assert res.unhandled == []
    assert res.text.count("walk_in_place_right") == 2


def test_forward_backward_gesture_only_matches_the_exact_pair(
    ctx: T.TranspileContext,
) -> None:
    """A lone code 12 (or 13) mixed with anything else is still outside the
    tier — this idiom only fires on the exact [12, 13] shape."""
    res = run_event(ctx, [[
        cmd(T.SET_MOVE_ROUTE, [5, _route([{"code": 12}, {"code": 1}])]),
    ]])
    assert len(res.unhandled) == 1
    assert "walk_in_place_right" not in res.text


def test_pokedex_grant_idiom(ctx: T.TranspileContext) -> None:
    """``$Trainer.pokedex=true`` -> the canonical native-analog pair
    (CLAUDE.md §4.7): FLAG_SYS_POKEDEX_GET + special SetUnlockedPokedexFlags,
    the same pair vanilla's own Birch/Oak-lab script uses."""
    res = run_event(ctx, [[cmd(T.SCRIPT, ["$Trainer.pokedex=true"])]])
    assert "setflag(FLAG_SYS_POKEDEX_GET)" in res.text
    assert "special(SetUnlockedPokedexFlags)" in res.text
    assert res.unhandled == []


def test_pokedex_grant_enables_national_mode(ctx: T.TranspileContext) -> None:
    """The grant must also enable National mode, or every Uranium species is
    caught-but-invisible: they are chained past NATIONAL_DEX_PECHARUNT with no
    regional number, and a Hoenn-mode dex enumerates only the regional range
    (`pokedex.c` CreatePokedexList). Setting FLAG_SYS_NATIONAL_DEX by hand
    would not do it -- IsNationalPokedexEnabled also checks nationalMagic and
    VAR_NATIONAL_DEX, which only the special writes."""
    res = run_event(ctx, [[cmd(T.SCRIPT, ["$Trainer.pokedex=true"])]])
    assert "special(EnableNationalPokedex)" in res.text
    assert res.unhandled == []


def test_emote_anim_104_maps_to_exclamation(ctx: T.TranspileContext) -> None:
    """Animation id 104 ("Rustle" per reference/animation_names.json) — the
    wild-encounter grass-rustle cue — substitutes the exclamation emote."""
    res = run_event(ctx, [[cmd(T.SHOW_ANIMATION, [5, 104])]])
    assert "applymovement(5, Common_Movement_ExclamationMark)" in res.text
    assert res.unhandled == []


def test_emote_anim_18_drops_with_breadcrumb_not_a_queue_entry(
    ctx: T.TranspileContext,
) -> None:
    """Animation id 18 ("EM scratch") is a decided drop (no OW hit-flourish
    analog) — a comment, not an UNHANDLED queue entry."""
    res = run_event(ctx, [[cmd(T.SHOW_ANIMATION, [5, 18])]])
    assert res.unhandled == []
    assert "no OW analog, dropped" in res.text


def test_string_list_readback_resolves_v_control_code(
    ctx: T.TranspileContext,
) -> None:
    """The Map032 EV9 starter name-back cluster: a string-literal local
    indexed by the same wrap-clamped local that materializes into a real,
    reused var — and the ``\\v[N]`` dialogue row that reads it resolves into
    one ``if``-branch per possible value of that real var."""
    ctx.registry.propose_var(151, "VAR_POKEMONTEST")
    ctx.registry.propose_var(1, "VAR_TEMP_POKEMON_CHOICE")
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ['list=["Orchynx","Raptorch","Eletux"]']),
        cmd(T.SCRIPT_CONT, ["x=pbGet(151)"]),
        cmd(T.SCRIPT_CONT, ["x=0 if x==3"]),
        cmd(T.SCRIPT_CONT, ["$game_variables[1]=x"]),
        cmd(T.SCRIPT_CONT, ["$game_variables[3]=list[x]"]),
        cmd(T.SHOW_TEXT, ["Go! \\v[3]!"]),
    ]])
    assert "copyvar(VAR_TEMP_POKEMON_CHOICE, VAR_POKEMONTEST)" in res.text
    assert "if (var(VAR_TEMP_POKEMON_CHOICE) == 3) {" in res.text
    assert "setvar(VAR_TEMP_POKEMON_CHOICE, 0)" in res.text
    assert 'if (var(VAR_TEMP_POKEMON_CHOICE) == 0) {\n        msgbox(format("Go! Orchynx!"))' in res.text
    assert 'if (var(VAR_TEMP_POKEMON_CHOICE) == 1) {\n        msgbox(format("Go! Raptorch!"))' in res.text
    assert 'if (var(VAR_TEMP_POKEMON_CHOICE) == 2) {\n        msgbox(format("Go! Eletux!"))' in res.text
    assert res.unhandled == []


def test_string_list_readback_without_prior_materialize_queues(
    ctx: T.TranspileContext,
) -> None:
    """A list-index readback whose local was never written into a real var
    (the plain-local materialize arm) can't resolve a text substitution:
    both the readback row itself and the \\v[N] dialogue row that depended
    on it queue, rather than either guessing."""
    res = run_event(ctx, [[
        cmd(T.SCRIPT, ['list=["Orchynx","Raptorch","Eletux"]']),
        cmd(T.SCRIPT_CONT, ["x=pbGet(151)"]),
        cmd(T.SCRIPT_CONT, ["$game_variables[3]=list[x]"]),
        cmd(T.SHOW_TEXT, ["Go! \\v[3]!"]),
    ]])
    codes = sorted(e.command_code for e in res.unhandled)
    assert codes == [T.SHOW_TEXT, T.SCRIPT]
