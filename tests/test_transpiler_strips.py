"""Unit tests for the two user-approved strip rules (approved 2026-07-05,
slice1 hand-bucket review) added to the deterministic transpiler:

* Rule 1 — the unsatisfiable defensive numeric guard
  (``_UNSATISFIABLE_NUMERIC_GUARD_RE`` / ``_emit_unsatisfiable_numeric_guard``
  in ``transpiler.py``): a code-111 script condition of the exact shape
  ``!pbGet(N).is_a?(Numeric) || $game_variables[M] < 0`` is statically FALSE
  on the GBA (game vars are always unsigned integers), so the then-arm is
  dropped and the else-arm's children are spliced in directly.
* Rule 2 — ``pbPhoneRegisterNPC(...)`` script-call strip
  (``_PHONE_REGISTER_NPC_STRIP_RE`` in ``transpiler.py``): the Essentials
  phone system has no slice-relevant analog; the call is dropped with a
  breadcrumb comment.

Event/page shape mirrors ``tests/test_transpiler.py``: an event is
``{id, name, x, y, pages:[...]}`` and each page is ``{trigger, list, ...}``
with ``list`` a sequence of ``{code, indent, parameters}`` commands. Builders
are kept local per file-ownership (same convention as
``tests/test_transpiler_idioms.py``).
"""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, self_switch_flag_name

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


@pytest.fixture()
def ctx() -> T.TranspileContext:
    return T.TranspileContext(registry=FlagRegistry())


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


_EXACT_GUARD = "!pbGet(1).is_a?(Numeric) || $game_variables[1] < 0"

# ----------------------------------------------------------------------------
# Rule 1 — unsatisfiable numeric guard
# ----------------------------------------------------------------------------


def test_numeric_guard_exact_match_empty_else_drops_then_arm(ctx: T.TranspileContext) -> None:
    commands = _guard_commands(_EXACT_GUARD, [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])])
    res = run_event(ctx, [commands], map_id=49, event_id=20)
    assert res.unhandled == []
    assert "# numeric guard: unsatisfiable on GBA" in res.text
    assert "slice1, 2026-07-05" in res.text
    # then-arm content (the self-switch write) never emits — the branch is
    # unreachable, so its body is dropped, not merely un-taken.
    assert "setflag" not in res.text


def test_numeric_guard_with_else_emits_else_children_inline(ctx: T.TranspileContext) -> None:
    commands = _guard_commands(
        _EXACT_GUARD,
        then_body=[cmd(T.CONTROL_SELF_SWITCH, ["A", 0])],
        else_body=[cmd(T.CONTROL_SELF_SWITCH, ["B", 0])],
    )
    res = run_event(ctx, [commands], map_id=49, event_id=20)
    assert res.unhandled == []
    assert "# numeric guard: unsatisfiable on GBA" in res.text
    a_flag = self_switch_flag_name(49, 20, "A")
    b_flag = self_switch_flag_name(49, 20, "B")
    assert f"setflag({a_flag})" not in res.text  # then-arm dropped
    assert f"setflag({b_flag})" in res.text  # else-arm spliced in inline
    # No wrapping conditional — the else content is unconditional now.
    assert "if (" not in res.text
    assert "} else {" not in res.text


@pytest.mark.parametrize(
    "condition",
    [
        # different combinator (&&, not ||)
        "!pbGet(1).is_a?(Numeric) && $game_variables[1] < 0",
        # un-negated is_a? check
        "pbGet(1).is_a?(Numeric)",
        # wrong comparison (> not <)
        "!pbGet(1).is_a?(Numeric) || $game_variables[1] > 0",
    ],
)
def test_numeric_guard_near_miss_still_queues(ctx: T.TranspileContext, condition: str) -> None:
    commands = _guard_commands(condition, [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])])
    res = run_event(ctx, [commands], map_id=49, event_id=20)
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "# numeric guard" not in res.text
    # unreached then-arm content still hidden behind the queue marker.
    assert "setflag" not in res.text


# ----------------------------------------------------------------------------
# Rule 2 — pbPhoneRegisterNPC(...) strip
# ----------------------------------------------------------------------------


def test_phone_register_npc_strips_with_breadcrumb(ctx: T.TranspileContext) -> None:
    res = run_event(
        ctx,
        [[cmd(T.SCRIPT, ["pbPhoneRegisterNPC(35,\"Professor Bamb'o\",50)"])]],
    )
    assert res.unhandled == []
    assert "# phone: pbPhoneRegisterNPC stripped (slice1)" in res.text
    assert "35" not in res.text
    assert "Bamb'o" not in res.text


def test_phone_register_npc_kernel_prefix_variant(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["Kernel.pbPhoneRegisterNPC(1,\"X\",2)"])]])
    assert res.unhandled == []
    assert "# phone: pbPhoneRegisterNPC stripped (slice1)" in res.text


def test_phone_register_npc_near_miss_still_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbPhoneRegisterNPCFoo(1,2)"])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SCRIPT
    assert "pbPhoneRegisterNPCFoo" in res.unhandled[0].description
    assert "# phone" not in res.text
