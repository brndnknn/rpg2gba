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
    assert 'msgbox("Hi {PLAYER}!")' in res.text
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
    assert 'msgbox("Placeholder line.", MSGBOX_AUTOCLOSE)' in res.text
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
    idx = lines.index('msgbox("Placeholder sign text.")')
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
    assert "applymovement(OBJ_EVENT_ID_PLAYER, [set_invisible])" in res.text
    assert "waitmovement(0)" in res.text
    assert res.unhandled == []


def test_change_player_transparency_visible(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CHANGE_PLAYER_TRANSPARENCY, [1])]])
    assert "applymovement(OBJ_EVENT_ID_PLAYER, [set_visible])" in res.text
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
    assert 'msgbox("placeholder success text")' in res.text
    assert 'msgbox("placeholder failure text")' in res.text


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
    assert "applymovement(OBJ_EVENT_ID_PLAYER, [walk_down])" in res.text
    assert res.unhandled == []


def test_align_loop_x_variant(ctx: T.TranspileContext) -> None:
    commands = _align_loop_commands("$game_player.x<=20", 3)  # 3 = walk right
    res = run_event(ctx, [commands])
    assert "while (var(VAR_TEMP_0) > 20) {" in res.text
    assert "applymovement(OBJ_EVENT_ID_PLAYER, [walk_right])" in res.text
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
        "        applymovement(OBJ_EVENT_ID_PLAYER, [walk_down])\n"
        "        waitmovement(0)\n"
        "        getplayerxy(VAR_TEMP_0, VAR_TEMP_1)\n"
        "    }\n"
        "    giveitem(ITEM_POTION)\n"
        '    msgbox("Bye!", MSGBOX_AUTOCLOSE)\n'
        "    applymovement(OBJ_EVENT_ID_PLAYER, Common_Movement_ExclamationMark)\n"
        "    waitmovement(0)\n"
        "    end\n"
        "}\n"
    )
    result = poryscript.compile_script(script)
    assert result.ok, result.stderr
