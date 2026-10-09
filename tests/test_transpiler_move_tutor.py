"""`pbMoveTutorChoose(PBMoves::X)` as a code-111 script condition (Map046 EV003,
the Nowtoch City move tutor) -> fork-native tutor sequence:
``setvar(VAR_0x8005, MOVE_X)`` + ``call(MoveTutor_EventScript_OpenBox)`` +
a ``VAR_RESULT`` branch (the ``move_tutor`` macro's own contract,
engine/asm/macros/event.inc:2700).

Fixtures are mechanical placeholder strings; no story dialogue.
"""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import poryscript
from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

_ELSE = 411


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


@pytest.fixture()
def ctx() -> T.TranspileContext:
    return T.TranspileContext(registry=FlagRegistry())


def run(ctx: T.TranspileContext, page: list[dict]) -> T.TranspiledEvent:
    ev = {"id": 3, "name": "tutor", "x": 0, "y": 0,
          "pages": [{"trigger": 0, "list": page}]}
    return T.transpile_event(46, ev, ctx)


def _tutor_page(call: str, with_else: bool = True, empty_then: bool = False) -> list[dict]:
    page = [cmd(T.CONDITIONAL_BRANCH, [12, call])]
    if not empty_then:
        page.append(cmd(T.SHOW_TEXT, ["taught"], indent=1))
    if with_else:
        page += [cmd(_ELSE), cmd(T.SHOW_TEXT, ["declined"], indent=1)]
    page.append(cmd(T.BRANCH_END))
    return page


def test_move_tutor_choose_golden(ctx: T.TranspileContext) -> None:
    res = run(ctx, _tutor_page("pbMoveTutorChoose(PBMoves::FEINT)"))
    assert res.unhandled == []
    body = "\n".join(ln.strip() for ln in res.text.splitlines())
    assert (
        "setvar(VAR_0x8005, MOVE_FEINT)\n"
        "call(MoveTutor_EventScript_OpenBox)\n"
        "if (var(VAR_RESULT) == TRUE) {\n"
        'msgbox(format("taught"))\n'
        "} else {\n"
        'msgbox(format("declined"))\n'
        "}"
    ) in body


def test_move_tutor_choose_without_else(ctx: T.TranspileContext) -> None:
    res = run(ctx, _tutor_page("pbMoveTutorChoose(PBMoves::FEINT)", with_else=False))
    assert res.unhandled == []
    assert "} else {" not in res.text
    assert "if (var(VAR_RESULT) == TRUE) {" in res.text


def test_move_tutor_choose_empty_then_inverts_to_false_arm(ctx: T.TranspileContext) -> None:
    res = run(ctx, _tutor_page("pbMoveTutorChoose(PBMoves::FEINT)", empty_then=True))
    assert res.unhandled == []
    assert "if (var(VAR_RESULT) == FALSE) {" in res.text
    assert "} else {" not in res.text
    assert 'msgbox(format("declined"))' in res.text


@pytest.mark.parametrize("name,const", [
    ("NASTYPLOT", "MOVE_NASTY_PLOT"),
    ("TOXICSPIKES", "MOVE_TOXIC_SPIKES"),
    ("WONDERROOM", "MOVE_WONDER_ROOM"),
])
def test_move_tutor_choose_resolves_through_id_map(
    ctx: T.TranspileContext, name: str, const: str
) -> None:
    res = run(ctx, _tutor_page(f"pbMoveTutorChoose(PBMoves::{name})"))
    assert f"setvar(VAR_0x8005, {const})" in res.text
    assert res.unhandled == []


def test_move_tutor_choose_accepts_wired_move_table(ctx: T.TranspileContext) -> None:
    ctx.moves = {"FEINT": "MOVE_TEST_ONLY"}
    res = run(ctx, _tutor_page("pbMoveTutorChoose(PBMoves::FEINT)"))
    assert "setvar(VAR_0x8005, MOVE_TEST_ONLY)" in res.text


@pytest.mark.parametrize("call", [
    "pbMoveTutorChoose(PBMoves::NOSUCHMOVEXYZ)",           # id-map miss
    "pbMoveTutorChoose(PBMoves::FEINT,[PBMoves::SPITE])",  # movelist arg: other shape
    "pbMoveTutorChoose(move)",                              # non-literal
])
def test_move_tutor_choose_unresolved_shapes_queue(ctx: T.TranspileContext, call: str) -> None:
    res = run(ctx, _tutor_page(call))
    assert any(q.command_code == T.CONDITIONAL_BRANCH for q in res.unhandled)
    assert "MoveTutor_EventScript_OpenBox" not in res.text


def test_move_tutor_choose_move_missing_from_fork_queues(ctx: T.TranspileContext) -> None:
    """§4.7 forward check: id-mapped but not defined by the fork -> queue."""
    ctx.fork_item_constants = frozenset({"MOVE_SPITE"})
    res = run(ctx, _tutor_page("pbMoveTutorChoose(PBMoves::FEINT)"))
    assert any(q.command_code == T.CONDITIONAL_BRANCH for q in res.unhandled)
    res_ok = run(ctx, _tutor_page("pbMoveTutorChoose(PBMoves::SPITE)"))
    assert "setvar(VAR_0x8005, MOVE_SPITE)" in res_ok.text


def test_tutor_loop_page_end_to_end(ctx: T.TranspileContext) -> None:
    """Reduced Map046 EV003: Yes/No -> label -> tutor condition whose else (and
    whose 'teach another? Yes') jumps back; the page is one while loop with no
    queue rows."""
    ctx.registry.propose_var(2, "VAR_TEMP_MOVE_CHOICE")
    page = [
        cmd(T.SHOW_CHOICES, [["Yes", "No"]]),
        cmd(T.CHOICE_WHEN, [0, "Yes"]),
        cmd(T.LABEL, ["Start"], indent=1),
        cmd(T.SHOW_TEXT, ["Pick?\\ch[2,-1,Feint,Spite]"], indent=1),
        cmd(T.CONDITIONAL_BRANCH, [1, 2, 0, 0, 0], indent=1),
        cmd(T.CONDITIONAL_BRANCH, [12, "pbMoveTutorChoose(PBMoves::FEINT)"], indent=2),
        cmd(T.SHOW_CHOICES, [["Yes", "No"]], indent=3),
        cmd(T.CHOICE_WHEN, [0, "Yes"], indent=3),
        cmd(T.JUMP_TO_LABEL, ["Start"], indent=4),
        cmd(T.CHOICE_WHEN, [1, "No"], indent=3),
        cmd(T.CHOICES_END, indent=3),
        cmd(_ELSE, indent=2),
        cmd(T.JUMP_TO_LABEL, ["Start"], indent=3),
        cmd(T.BRANCH_END, indent=2),
        cmd(T.BRANCH_END, indent=1),
        cmd(T.CONTROL_VARIABLES, [2, 2, 0, 0, 0], indent=1),
        cmd(T.SHOW_TEXT, ["bye"], indent=1),
        cmd(T.CHOICE_WHEN, [1, "No"]),
        cmd(T.SHOW_TEXT, ["no"], indent=1),
        cmd(T.CHOICES_END),
    ]
    res = run(ctx, page)
    assert res.unhandled == []
    assert res.text.count("continue") == 2
    assert res.text.count("while (var(VAR_RESULT) >= 0) {") == 1
    assert "setvar(VAR_TEMP_MOVE_CHOICE, 32767)" in res.text
    if poryscript.is_available():
        result = poryscript.compile_script(res.text)
        assert result.ok, result.stderr


@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_move_tutor_choose_compiles_through_real_poryscript(ctx: T.TranspileContext) -> None:
    res = run(ctx, _tutor_page("pbMoveTutorChoose(PBMoves::FEINT)"))
    result = poryscript.compile_script(res.text)
    assert result.ok, result.stderr
