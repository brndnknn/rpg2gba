"""Per-row state extraction (REDERIVATION_PLAN.md §16.3 C2a item 4).

`extract_map` derives, for every manifest row on one map (page trunk or
branch arm -- the same row ids `chapter_manifest.generator.iter_page_scopes`
mints), what it READS (the page's own appearance condition, plus this arm's
own selection guard -- ancestor arm guards are reachable through
`RowState.parent_row_id`, not repeated here) and WRITES (121/122/123,
recognized script idioms, and 117 common-event inlining).

C2b (liveness, saturation, ordering, chapter chaining) consumes this
module's `RowState` records; nothing here decides whether a row is ever
actually reached.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rpg2gba.chapter_manifest.conditions import ArmOutcome, classify_condition
from rpg2gba.chapter_manifest.generator import (
    _flatten_scope,
    iter_page_scopes,
)
from rpg2gba.chapter_manifest.schema import BranchRef
from rpg2gba.conversion_agent.transpiler import (
    ChoiceNode,
    IfNode,
    LoopNode,
    Node,
    TextRun,
    parse_tree,
)
from rpg2gba.story_state.state import (
    Adjust,
    Assign,
    Refusal,
    SelfSwitch,
    Switch,
    TempSwitch,
    Test,
    Variable,
    Write,
)

# --- RMXP command codes used by this module (kept local; see
# `chapter_manifest.generator`'s own local-constant note for why these are
# not re-derived from a shared enum -- the corpus has no single canonical
# command-code module). ------------------------------------------------
CODE_SWITCH_WRITE = 121
CODE_VAR_WRITE = 122
CODE_SELF_SWITCH_WRITE = 123
CODE_COMMON_EVENT_CALL = 117
CODE_SCRIPT = 355
CODE_SCRIPT_CONT = 655

_TRIGGER_NAMES: dict[int, str] = {
    0: "action", 1: "player_touch", 2: "event_touch", 3: "autorun", 4: "parallel",
}
_FORCED_TRIGGERS = frozenset({3, 4})  # autorun, parallel

_VAR_COMPARISONS: dict[int, str] = {0: "==", 1: ">=", 2: "<=", 3: ">", 4: "<", 5: "!="}
_NEGATE_CMP: dict[str, str] = {
    "==": "!=", "!=": "==", ">=": "<", "<=": ">", ">": "<=", "<": ">=",
}
_VAR_OP_SYMBOLS: dict[int, str] = {1: "+", 2: "-", 3: "*", 4: "/", 5: "%"}


@dataclass(frozen=True)
class ArmGuard:
    """How ONE branch-arm row is itself selected.

    `tests` holds the concrete `Test`(s) this arm's own guard resolves to,
    when the condition is directly evaluable from a modelled key (switch/
    variable/self-switch 111, or a `state`-kind condition family such as
    `game_variables_cmp`/`is_temp_switch_off`). `negated` is True for an
    `else` arm -- `tests` already holds the arm-specific (already negated)
    Test, `negated` is purely an explicit marker of which arm this is
    (REDERIVATION_PLAN.md §16.3 C2a item 4: "not by rewriting ops
    ambiguously" -- the flag documents the relationship rather than leaving
    a caller to infer it from `tests` alone).

    `outcome` is the family/condition-type-level `ArmOutcome` -- non-empty
    whenever this arm's liveness is not (fully) captured by `tests` alone:
    `input`/`random`/`fork`/`harness`/`capability`/`unmodelled` arms carry
    an outcome and empty `tests`; a `state`-kind arm this module could
    concretely parse (game_variables_cmp, is_temp_switch_off, plain
    switch/variable/self-switch 111) carries `tests` and the outcome for
    context. `choice_index` is set only for a 102/402/403 arm.
    """

    tests: tuple[Test, ...] = ()
    negated: bool = False
    outcome: ArmOutcome | None = None
    choice_index: int | None = None


@dataclass(frozen=True)
class RowState:
    """Everything `extract_map` derived for one manifest row.

    `row_id`/`parent_row_id` match `chapter_manifest.schema`'s row-id
    grammar exactly (both come from `iter_page_scopes`, the single source of
    row scopes). `page_tests` is the row's PAGE's own appearance condition
    (identical across the page's trunk row and every one of its arm rows --
    ancestor ARM guards, by contrast, are reached through `parent_row_id`,
    not duplicated here). `arm_guard` is `None` for a page-trunk row (kind
    `"page"`); populated for a branch-arm row. `event_page_row_ids` is the
    full ordered page-row-id tuple for this row's event, so C2b can apply
    RMXP's highest-live-page rule without a second pass over the map data.
    """

    row_id: str
    parent_row_id: str | None
    page_tests: tuple[Test, ...]
    page_refusals: tuple[Refusal, ...]
    arm_guard: ArmGuard | None
    writes: tuple[Write, ...]
    trigger: str
    forced: bool
    refusals: tuple[Refusal, ...]
    event_page_row_ids: tuple[str, ...]


# --- page-condition reads ------------------------------------------------


def _page_condition_reads(
    raw_condition: dict[str, Any],
    map_id: int,
    event_id: int,
    switch_labels: dict[int, str],
) -> tuple[tuple[Test, ...], tuple[Refusal, ...]]:
    tests: list[Test] = []
    refusals: list[Refusal] = []

    for key_name in ("switch1", "switch2"):
        if not raw_condition.get(f"{key_name}_valid"):
            continue
        switch_id = raw_condition[f"{key_name}_id"]
        label = switch_labels.get(switch_id)
        if label is not None and label.startswith("s:"):
            temp = _match_temp_switch_predicate(label, map_id, event_id)
            if temp is not None:
                tests.append(temp)
            else:
                refusals.append(Refusal(
                    "unmodelled_predicate",
                    f"page condition {key_name} (switch {switch_id}): runtime "
                    f"predicate {label!r} is not tsOn?/tsOff? -- not modelled",
                ))
            continue
        tests.append(Test(Switch(switch_id), "==", True))

    if raw_condition.get("variable_valid"):
        var_id = raw_condition["variable_id"]
        min_value = raw_condition.get("variable_value")
        if isinstance(min_value, int):
            tests.append(Test(Variable(var_id), ">=", min_value))
        else:
            refusals.append(Refusal(
                "malformed_page_condition",
                f"page condition variable {var_id}: variable_value {min_value!r} is not an int",
            ))

    if raw_condition.get("self_switch_valid"):
        letter = raw_condition.get("self_switch_ch")
        if isinstance(letter, str):
            tests.append(Test(SelfSwitch(map_id, event_id, letter), "==", True))
        else:
            refusals.append(Refusal(
                "malformed_page_condition",
                f"page condition self_switch_ch {letter!r} is not a string",
            ))

    return tuple(tests), tuple(refusals)


_TEMP_PREDICATE_RE = re.compile(r's:ts(On|Off)\?\("(\w+)"\)')


def _match_temp_switch_predicate(label: str, map_id: int, event_id: int) -> Test | None:
    """`s:tsOn?("X")` / `s:tsOff?("X")` -> a TempSwitch Test on THIS row's own
    event (022_Game_Event_v17.rb / 101__PField_Field.rb's tsOn?/tsOff? both
    resolve via `get_character(0)`, the currently-running event -- see
    `is_temp_switch_off`'s family description in `conditions.py`)."""
    m = _TEMP_PREDICATE_RE.fullmatch(label)
    if not m:
        return None
    is_on = m.group(1) == "On"
    letter = m.group(2)
    return Test(TempSwitch(map_id, event_id, letter), "==", is_on)


# --- arm guards ------------------------------------------------------------

_GAME_VARIABLES_CMP_RE = re.compile(
    r"\$game_variables\[(\d+)\]\s*(==|!=|<=|>=|<|>)\s*(-?\d+)")
_IS_TEMP_SWITCH_OFF_RE = re.compile(r'isTempSwitchOff\?\("(\w+)"\)')


def _arm_guard(
    branch: BranchRef,
    raw_commands: list[dict[str, Any]],
    map_id: int,
    event_id: int,
) -> tuple[ArmGuard | None, tuple[Refusal, ...]]:
    if branch.arm_kind in ("choice", "cancel"):
        detail = "cancel" if branch.choice_index is None else f"choice_index={branch.choice_index}"
        return ArmGuard(outcome=ArmOutcome(kind="input", detail=detail),
                         choice_index=branch.choice_index), ()

    is_else = branch.arm_kind == "else"
    opener = raw_commands[branch.opener_index]
    params = opener.get("parameters") or []
    ctype = branch.condition_type

    if ctype == 0:  # switch [0, id, 0=ON/1=OFF]
        if len(params) < 3:
            return None, (Refusal(
                "malformed_branch_condition",
                f"type 0 branch at list[{branch.opener_index}]: too few params",
            ),)
        switch_id, onoff = params[1], params[2]
        on = onoff == 0
        value = (not on) if is_else else on
        return ArmGuard(tests=(Test(Switch(switch_id), "==", value),), negated=is_else), ()

    if ctype == 1:  # variable [1, id, operand_kind, operand, cmp]
        if len(params) < 5:
            return None, (Refusal(
                "malformed_branch_condition",
                f"type 1 branch at list[{branch.opener_index}]: too few params",
            ),)
        var_id, operand_kind, operand, cmp_code = params[1], params[2], params[3], params[4]
        if operand_kind != 0 or not isinstance(operand, int):
            return None, (Refusal(
                "nonconstant_variable_condition",
                f"type 1 branch at list[{branch.opener_index}]: variable {var_id} "
                f"compared to a non-constant operand (kind {operand_kind!r})",
            ),)
        op = _VAR_COMPARISONS.get(cmp_code)
        if op is None:
            return None, (Refusal(
                "malformed_branch_condition",
                f"type 1 branch at list[{branch.opener_index}]: unknown cmp code {cmp_code!r}",
            ),)
        if is_else:
            op = _NEGATE_CMP[op]
        return ArmGuard(tests=(Test(Variable(var_id), op, operand),), negated=is_else), ()

    if ctype == 2:  # self-switch [2, "A", 0=ON/1=OFF]
        if len(params) < 3:
            return None, (Refusal(
                "malformed_branch_condition",
                f"type 2 branch at list[{branch.opener_index}]: too few params",
            ),)
        letter, onoff = params[1], params[2]
        on = onoff == 0
        value = (not on) if is_else else on
        return ArmGuard(
            tests=(Test(SelfSwitch(map_id, event_id, letter), "==", value),),
            negated=is_else,
        ), ()

    if ctype == 6:  # character facing -- player input, both arms
        return ArmGuard(outcome=ArmOutcome(kind="input", detail="facing")), ()

    if ctype == 12:  # script-typed -- classify via the family table
        text = branch.condition_text or ""
        family = classify_condition(text)
        if family is None:
            return None, (Refusal(
                "unclassified_condition",
                f"type 12 branch at list[{branch.opener_index}]: {' '.join(text.split())!r}",
            ),)
        outcome = family.else_outcome if is_else else family.then_outcome

        if family.name == "game_variables_cmp":
            m = _GAME_VARIABLES_CMP_RE.fullmatch(" ".join(text.split()))
            if m:
                var_id, op, value = int(m.group(1)), m.group(2), int(m.group(3))
                if is_else:
                    op = _NEGATE_CMP[op]
                return ArmGuard(
                    tests=(Test(Variable(var_id), op, value),),
                    negated=is_else, outcome=outcome,
                ), ()
        elif family.name == "is_temp_switch_off":
            m = _IS_TEMP_SWITCH_OFF_RE.fullmatch(" ".join(text.split()))
            if m:
                letter = m.group(1)
                # isTempSwitchOff? true (then) means the temp switch is OFF
                # (value False); else means it is ON.
                value = is_else
                return ArmGuard(
                    tests=(Test(TempSwitch(map_id, event_id, letter), "==", value),),
                    negated=is_else, outcome=outcome,
                ), ()

        return ArmGuard(outcome=outcome, negated=is_else), ()

    return None, (Refusal(
        "unhandled_condition_type",
        f"branch at list[{branch.opener_index}]: condition type {ctype!r} not modelled",
    ),)


# --- writes ------------------------------------------------------------

_RE_SET_SELF_SWITCH = re.compile(
    r'^pbSetSelfSwitch\(\s*(\d+)\s*,\s*"([A-Za-z0-9])"\s*,\s*(true|false)\s*\)$')
_RE_SET_TEMP_ON = re.compile(r'^setTempSwitchOn\(\s*"(\w+)"\s*\)$')
_RE_SET_TEMP_OFF = re.compile(r'^setTempSwitchOff\(\s*"(\w+)"\s*\)$')
_RE_GAME_SWITCH_ASSIGN = re.compile(r'^\$game_switches\[\s*(\d+)\s*\]\s*=\s*(true|false)$')
_RE_GAME_VAR_ASSIGN = re.compile(r'^\$game_variables\[\s*(\d+)\s*\]\s*=\s*(-?\d+)$')
_RE_PBSET = re.compile(r'^pbSet\(\s*(\d+)\s*,\s*(-?\d+)\s*\)$')

_STATE_WRITE_SMELL_RE = re.compile(
    r'\$game_switches\[|\$game_variables\[|\$game_self_switches|pbSet\(|'
    r'pbSetSelfSwitch\(|setTempSwitch\w*\s*\(.*(=|On|Off)|[+\-*/%]=')


def _extract_script_writes(
    text: str, map_id: int, event_id: int, conditional: bool, source_prefix: str,
) -> tuple[tuple[Write, ...], tuple[Refusal, ...]]:
    writes: list[Write] = []
    refusals: list[Refusal] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        source = f"{source_prefix}: {line}"
        m = _RE_SET_SELF_SWITCH.match(line)
        if m:
            other_event_id, letter, value = int(m.group(1)), m.group(2), m.group(3) == "true"
            writes.append(Assign(
                SelfSwitch(map_id, other_event_id, letter), frozenset({value}),
                conditional, source,
            ))
            continue
        m = _RE_SET_TEMP_ON.match(line)
        if m:
            writes.append(Assign(
                TempSwitch(map_id, event_id, m.group(1)), frozenset({True}),
                conditional, source,
            ))
            continue
        m = _RE_SET_TEMP_OFF.match(line)
        if m:
            writes.append(Assign(
                TempSwitch(map_id, event_id, m.group(1)), frozenset({False}),
                conditional, source,
            ))
            continue
        m = _RE_GAME_SWITCH_ASSIGN.match(line)
        if m:
            writes.append(Assign(
                Switch(int(m.group(1))), frozenset({m.group(2) == "true"}),
                conditional, source,
            ))
            continue
        m = _RE_GAME_VAR_ASSIGN.match(line)
        if m:
            writes.append(Assign(
                Variable(int(m.group(1))), frozenset({int(m.group(2))}),
                conditional, source,
            ))
            continue
        m = _RE_PBSET.match(line)
        if m:
            writes.append(Assign(
                Variable(int(m.group(1))), frozenset({int(m.group(2))}),
                conditional, source,
            ))
            continue
        if _STATE_WRITE_SMELL_RE.search(line):
            refusals.append(Refusal("unparsed_state_write", source))
    return tuple(writes), tuple(refusals)


def _extract_leaf_writes(
    cmd: dict[str, Any],
    index: int,
    map_id: int,
    event_id: int,
    common_events_by_id: dict[int, dict[str, Any]],
    conditional: bool,
    visited_ce: frozenset[int],
) -> tuple[tuple[Write, ...], tuple[Refusal, ...]]:
    code = cmd.get("code")
    params = cmd.get("parameters") or []

    if code == CODE_SWITCH_WRITE:
        if len(params) < 3:
            return (), (Refusal("malformed_write", f"code 121 @list[{index}]: too few params"),)
        lo, hi, value = params[0], params[1], params[2]
        on = value == 0
        writes = tuple(
            Assign(Switch(sid), frozenset({on}), conditional, f"code 121 @list[{index}]")
            for sid in range(lo, hi + 1)
        )
        return writes, ()

    if code == CODE_VAR_WRITE:
        if len(params) < 5:
            return (), (Refusal("malformed_write", f"code 122 @list[{index}]: too few params"),)
        lo, hi, op, operand_kind, operand = params[0], params[1], params[2], params[3], params[4]
        writes: list[Write] = []
        refusals: list[Refusal] = []
        for vid in range(lo, hi + 1):
            source = f"code 122 @list[{index}]"
            if op == 0 and operand_kind == 0 and isinstance(operand, int):
                writes.append(Assign(Variable(vid), frozenset({operand}), conditional, source))
            elif op == 0 and operand_kind == 2 and len(params) >= 6:
                rlo, rhi = operand, params[5]
                if isinstance(rlo, int) and isinstance(rhi, int) and rhi >= rlo:
                    writes.append(Assign(
                        Variable(vid), frozenset(range(rlo, rhi + 1)), conditional, source))
                else:
                    refusals.append(Refusal(
                        "nonconstant_variable_write",
                        f"{source}: variable {vid} random bounds {operand!r}/{params[5]!r}",
                    ))
            elif op in _VAR_OP_SYMBOLS and operand_kind == 0 and isinstance(operand, int):
                writes.append(Adjust(
                    Variable(vid), _VAR_OP_SYMBOLS[op], operand, conditional, source))
            else:
                refusals.append(Refusal(
                    "nonconstant_variable_write",
                    f"{source}: variable {vid} op {op!r} operand_kind {operand_kind!r} "
                    f"operand {operand!r} not a constant-write shape",
                ))
        return tuple(writes), tuple(refusals)

    if code == CODE_SELF_SWITCH_WRITE:
        if len(params) < 2:
            return (), (Refusal("malformed_write", f"code 123 @list[{index}]: too few params"),)
        letter, value = params[0], params[1]
        writes = (Assign(
            SelfSwitch(map_id, event_id, letter), frozenset({value == 0}),
            conditional, f"code 123 @list[{index}]",
        ),)
        return writes, ()

    if code == CODE_COMMON_EVENT_CALL:
        if not params:
            return (), (Refusal("malformed_write", f"code 117 @list[{index}]: no params"),)
        ce_id = params[0]
        source_prefix = f"code 117 @list[{index}] (common event {ce_id})"
        if ce_id in visited_ce:
            return (), (Refusal(
                "common_event_cycle",
                f"{source_prefix}: already inlined on this path -- cycle",
            ),)
        ce = common_events_by_id.get(ce_id)
        if ce is None:
            return (), (Refusal("missing_common_event", f"{source_prefix}: not found"),)
        ce_commands = ce.get("list") or []
        tree = parse_tree(ce_commands)
        return _extract_ce_writes(
            tree, ce_commands, map_id, event_id, common_events_by_id,
            conditional, visited_ce | {ce_id},
        )

    if code in (CODE_SCRIPT, CODE_SCRIPT_CONT):
        # Handled at the caller as grouped script blocks, not per-leaf.
        return (), ()

    return (), ()


def _extract_scope_writes(
    commands: list[dict[str, Any]],
    map_id: int,
    event_id: int,
    common_events_by_id: dict[int, dict[str, Any]],
    conditional: bool,
    visited_ce: frozenset[int],
) -> tuple[tuple[Write, ...], tuple[Refusal, ...]]:
    """Writes directly in one flat (already-scoped) command list -- a page
    trunk's own commands, a branch arm's own commands, or one scope of an
    inlined common event. Scripts (355/655) are grouped into blocks first
    (a block can span several consecutive commands), everything else is
    dispatched per leaf command."""
    writes: list[Write] = []
    refusals: list[Refusal] = []
    i = 0
    while i < len(commands):
        cmd = commands[i]
        code = cmd.get("code")
        if code == CODE_SCRIPT:
            parts = [str((cmd.get("parameters") or [""])[0] if cmd.get("parameters") else "")]
            j = i + 1
            while j < len(commands) and commands[j].get("code") == CODE_SCRIPT_CONT:
                p = commands[j].get("parameters") or [""]
                parts.append(str(p[0]) if p else "")
                j += 1
            text = "\n".join(parts)
            source_prefix = f"script @list[{i}]"
            w, r = _extract_script_writes(text, map_id, event_id, conditional, source_prefix)
            writes.extend(w)
            refusals.extend(r)
            i = j
            continue
        w, r = _extract_leaf_writes(
            cmd, i, map_id, event_id, common_events_by_id, conditional, visited_ce)
        writes.extend(w)
        refusals.extend(r)
        i += 1
    return tuple(writes), tuple(refusals)


def _extract_ce_writes(
    tree: list[Node],
    commands: list[dict[str, Any]],
    map_id: int,
    event_id: int,
    common_events_by_id: dict[int, dict[str, Any]],
    conditional: bool,
    visited_ce: frozenset[int],
) -> tuple[tuple[Write, ...], tuple[Refusal, ...]]:
    """Inlines one common event: its own trunk writes inherit the caller's
    `conditional` flag; anything inside any of ITS OWN branch arms
    (recursively) is forced `conditional=True` (REDERIVATION_PLAN.md §16.3
    C2a item 4)."""
    writes: list[Write] = []
    refusals: list[Refusal] = []

    trunk_commands = _flatten_scope(tree, commands)
    w, r = _extract_scope_writes(
        trunk_commands, map_id, event_id, common_events_by_id, conditional, visited_ce)
    writes.extend(w)
    refusals.extend(r)

    def _walk(nodes: list[Node]) -> None:
        for node in nodes:
            if isinstance(node, IfNode):
                for children in (node.then, node.otherwise if node.otherwise is not None else []):
                    arm_commands = _flatten_scope(children, commands)
                    w2, r2 = _extract_scope_writes(
                        arm_commands, map_id, event_id, common_events_by_id, True, visited_ce)
                    writes.extend(w2)
                    refusals.extend(r2)
                    _walk(children)
            elif isinstance(node, ChoiceNode):
                for _, _, children in node.arms:
                    arm_commands = _flatten_scope(children, commands)
                    w2, r2 = _extract_scope_writes(
                        arm_commands, map_id, event_id, common_events_by_id, True, visited_ce)
                    writes.extend(w2)
                    refusals.extend(r2)
                    _walk(children)
            elif isinstance(node, LoopNode):
                _walk(node.children)
            # Leaf / TextRun: no nested branch structure.

    _walk(tree)
    return tuple(writes), tuple(refusals)


# --- top-level entry point -----------------------------------------------


def extract_map(
    map_id: int,
    map_data: dict[str, Any],
    *,
    common_events: list[dict[str, Any]],
    switch_labels: dict[int, str],
) -> dict[str, "RowState"]:
    """Every row's `RowState` for one map's events, keyed by manifest row id
    (the same ids `chapter_manifest.generator.iter_page_scopes` mints).
    """
    common_events_by_id = {ce["id"]: ce for ce in common_events}
    result: dict[str, RowState] = {}

    for event in map_data.get("events", []):
        event_id = event["id"]
        pages = event.get("pages", [])
        page_row_ids: list[str] = []
        per_page_scopes = []
        for page_idx, page in enumerate(pages):
            scopes = iter_page_scopes(map_id, event, page_idx, page)
            page_row_ids.append(scopes[0].row_id)
            per_page_scopes.append((page, scopes))
        event_page_row_ids = tuple(page_row_ids)

        for page, scopes in per_page_scopes:
            raw_condition = page.get("condition") or {}
            raw_commands = page.get("list") or []
            page_tests, page_refusals = _page_condition_reads(
                raw_condition, map_id, event_id, switch_labels)
            trigger_raw = page.get("trigger")
            trigger = _TRIGGER_NAMES.get(trigger_raw, str(trigger_raw))
            forced = trigger_raw in _FORCED_TRIGGERS

            for scope in scopes:
                arm_guard: ArmGuard | None = None
                guard_refusals: tuple[Refusal, ...] = ()
                if scope.branch is not None:
                    arm_guard, guard_refusals = _arm_guard(
                        scope.branch, raw_commands, map_id, event_id)

                writes, write_refusals = _extract_scope_writes(
                    scope.commands, map_id, event_id, common_events_by_id,
                    False, frozenset(),
                )

                result[scope.row_id] = RowState(
                    row_id=scope.row_id,
                    parent_row_id=scope.parent_row_id,
                    page_tests=page_tests,
                    page_refusals=page_refusals,
                    arm_guard=arm_guard,
                    writes=writes,
                    trigger=trigger,
                    forced=forced,
                    refusals=guard_refusals + write_refusals,
                    event_page_row_ids=event_page_row_ids,
                )

    return result
