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

`extract_triggered_common_events` (REDERIVATION_PLAN.md §16.3 C2 ruling (e))
mints a second family of `RowState`: a pseudo-row `common/ceNNN` (and its
branch-arm children `common/ceNNN/bM`) per autorun/parallel common event,
covering behaviour that runs with no map event or page of its own at all
(RMXP fires a triggered common event globally, gated only on its own switch).
These ids are model-internal -- they follow no `chapter_manifest.schema`
grammar (`page_row_id`/`branch_row_id`/`seam_row_id`/`terrain_row_id`),
`schema.parse_row_id` does not and should not recognize them, and they never
appear in a manifest (`chapter_manifest` proper). `model.py` special-cases
them (never routed through `parse_row_id`) and reports them in a separate
`common_events` section rather than folding them into a chapter's own-map
row list.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace as _dc_replace
from pathlib import Path
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
from rpg2gba.story_state.scope_search import (
    ComputedScope,
    named_write_targets,
    scope_needs_interpreter,
    stripped_ce_ids_for,
    witness_citations,
    writes_from_result,
)
from rpg2gba.ruby_subset.builtins import STATIC_PREDICATES
from rpg2gba.ruby_subset.search import search_scope
from rpg2gba.story_state.graphics_vars import graphics_only_variables
from rpg2gba.story_state.bag import key_item_symbols, scan_bag_text
from rpg2gba.story_state.state import (
    Adjust,
    Assign,
    BagHas,
    Key,
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
CODE_CONDITIONAL = 111

_TRIGGER_NAMES: dict[int, str] = {
    0: "action", 1: "player_touch", 2: "event_touch", 3: "autorun", 4: "parallel",
}
_FORCED_TRIGGERS = frozenset({3, 4})  # autorun, parallel

# Common-event triggers are a SEPARATE, shorter numbering from event-page
# triggers above (RMXP's own `RPG::CommonEvent#trigger`: 0 none, 1 autorun,
# 2 parallel -- no action/player_touch/event_touch, since a common event has
# no map position of its own). Verified against the corpus: common event 51
# ("Only Day people") and 10/11 ("RACING-Main"/"RACING-Mini") are all
# `trigger=2` and are plainly parallel background processes, not something a
# player "touches".
_CE_TRIGGER_NAMES: dict[int, str] = {0: "none", 1: "autorun", 2: "parallel"}
_CE_FORCED_TRIGGERS = frozenset({1, 2})

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

    `opener_index` is `BranchRef.opener_index` -- the branch CONSTRUCT's own
    position (shared by every arm of one 111/102), always populated. Combined
    with a row's `parent_row_id` (the same for every arm of one construct),
    `(parent_row_id, opener_index)` identifies "this specific branch
    construct" -- `model.py`'s sibling-arm-join rule (REDERIVATION_PLAN.md
    §16.3 C2b handback: input/random siblings join rather than conflict at
    end-state) uses it to find which rows are mutually-exclusive alternatives
    of the SAME opener, as opposed to two unrelated branches that happen to
    share an enclosing scope.
    """

    tests: tuple[Test, ...] = ()
    negated: bool = False
    outcome: ArmOutcome | None = None
    choice_index: int | None = None
    opener_index: int | None = None


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
    # REDERIVATION_PLAN.md §16.3 C2b handback FIX 2b: keys an
    # `unparsed_state_write` on this row visibly named (best-effort, no
    # attempt at the value) and whether some such write named NO
    # recognizable key at all (a strictly worse "could be touching
    # anything" claim). Neither implies the other.
    havoc_keys: tuple[Key, ...] = ()
    havoc_global: bool = False
    # REDERIVATION_PLAN.md §16.3 C8 stage 4: populated instead of `writes`
    # when this row's own run reads state outside its own scope -- the
    # resolver in `story_state/model.py` re-runs `computed` (via
    # `scope_search.run_scope`) against saturated value sets until this
    # row's writes stop changing. `witnesses` is a JSON-serialisable
    # citation, one `(key_repr, value_repr, choice_labels)` entry per
    # `(key, value)` the interpreter search resolved for a row that
    # resolved fully at extraction time -- empty for a `computed` row
    # (nothing resolved yet) and for a row that never needed the
    # interpreter at all.
    computed: "ComputedScope | None" = None
    witnesses: tuple[tuple[str, str, tuple[str, ...]], ...] = ()


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


def _static_predicate_arm(text: str, is_else: bool) -> ArmOutcome | None:
    """A condition that is exactly a `static_predicates` entry (optionally
    negated with a leading `!`) is a compile-time constant: the arm it
    selects is `always`, the other is `dead` (REDERIVATION_PLAN.md §16.3
    ruling 14). Anything else, including a compound using one, is None and
    goes to the family table as before."""
    normalized = " ".join(text.split())
    negated = normalized.startswith("!")
    predicate = normalized[1:].strip() if negated else normalized
    if predicate not in STATIC_PREDICATES:
        return None
    holds = STATIC_PREDICATES[predicate] != negated
    arm_live = holds != is_else
    if arm_live:
        return ArmOutcome(kind="always", detail=f"{predicate}={STATIC_PREDICATES[predicate]}")
    return ArmOutcome(kind="dead", detail=f"{predicate}={STATIC_PREDICATES[predicate]}")


_BAG_QTY_RE = re.compile(
    r"\$PokemonBag\.pbQuantity\(\s*(?:::)?(?:PBItems::|:)([A-Z][A-Z0-9_]*)\s*\)"
    r"\s*(>|>=|==|<)\s*(0|1)")
# (operator, constant) -> does the THEN arm mean "the bag holds the item"?
_BAG_HAS_FORMS: dict[tuple[str, str], bool] = {
    (">", "0"): True, (">=", "1"): True, ("==", "0"): False, ("<", "1"): False,
}


def _bag_has_test(text: str, is_else: bool) -> Test | None:
    """`$PokemonBag.pbQuantity(<KEY ITEM>) > 0` (and `>= 1`, `== 0`, `< 1`),
    as a `BagHas` test; None for anything else (non-key item, other
    comparison, compound expression) so it falls through to the family table
    unchanged."""
    m = _BAG_QTY_RE.fullmatch(" ".join(text.split()))
    if m is None:
        return None
    has = _BAG_HAS_FORMS.get((m.group(2), m.group(3)))
    item = m.group(1)
    if has is None or item not in key_item_symbols():
        return None
    return Test(BagHas(item), "==", (not has) if is_else else has)


def _arm_guard(
    branch: BranchRef,
    raw_commands: list[dict[str, Any]],
    map_id: int,
    event_id: int,
) -> tuple[ArmGuard | None, tuple[Refusal, ...]]:
    if branch.arm_kind in ("choice", "cancel"):
        detail = "cancel" if branch.choice_index is None else f"choice_index={branch.choice_index}"
        return ArmGuard(outcome=ArmOutcome(kind="input", detail=detail),
                         choice_index=branch.choice_index,
                         opener_index=branch.opener_index), ()

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
        return ArmGuard(
            tests=(Test(Switch(switch_id), "==", value),), negated=is_else,
            opener_index=branch.opener_index,
        ), ()

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
        return ArmGuard(
            tests=(Test(Variable(var_id), op, operand),), negated=is_else,
            opener_index=branch.opener_index,
        ), ()

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
            negated=is_else, opener_index=branch.opener_index,
        ), ()

    if ctype == 6:  # character facing -- player input, both arms
        return ArmGuard(
            outcome=ArmOutcome(kind="input", detail="facing"),
            opener_index=branch.opener_index,
        ), ()

    if ctype == 12:  # script-typed -- classify via the family table
        text = branch.condition_text or ""
        static = _static_predicate_arm(text, is_else)
        if static is not None:
            return ArmGuard(outcome=static, negated=is_else, opener_index=branch.opener_index), ()
        bag_test = _bag_has_test(text, is_else)
        if bag_test is not None:
            return ArmGuard(
                tests=(bag_test,), negated=is_else, opener_index=branch.opener_index,
            ), ()
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
                    negated=is_else, outcome=outcome, opener_index=branch.opener_index,
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
                    negated=is_else, outcome=outcome, opener_index=branch.opener_index,
                ), ()

        return ArmGuard(outcome=outcome, negated=is_else, opener_index=branch.opener_index), ()

    return None, (Refusal(
        "unhandled_condition_type",
        f"branch at list[{branch.opener_index}]: condition type {ctype!r} not modelled",
    ),)


# --- writes ------------------------------------------------------------


def _default_reference_dir() -> Path:
    """`reference/` at the repo root -- same derivation `engine_audit.py`/
    `model.py` already use (`Path(__file__).resolve().parents[3]`)."""
    return Path(__file__).resolve().parents[3] / "reference"


@dataclass(frozen=True)
class ScopeExtraction:
    """Everything `_extract_scope_writes` (and its CE-inlining sibling
    `_extract_ce_writes`) derive for one flattened command list -- grown
    from a 4-tuple (REDERIVATION_PLAN.md §16.3 C8 stage 4) once `computed`/
    `witnesses` joined `writes`/`refusals`/`havoc_keys`/`havoc_global`."""

    writes: tuple[Write, ...] = ()
    refusals: tuple[Refusal, ...] = ()
    havoc_keys: frozenset[Key] = frozenset()
    havoc_global: bool = False
    computed: ComputedScope | None = None
    witnesses: tuple[tuple[str, str, tuple[str, ...]], ...] = ()


def _extract_leaf_writes(
    cmd: dict[str, Any],
    index: int,
    map_id: int,
    event_id: int,
    common_events_by_id: dict[int, dict[str, Any]],
    conditional: bool,
    visited_ce: frozenset[int],
    stripped_ce_ids: frozenset[int],
) -> tuple[tuple[Write, ...], tuple[Refusal, ...], frozenset[Key], bool]:
    """`index` is the WRITE'S ATTRIBUTED `list_index` (REDERIVATION_PLAN.md
    §16.3 C2b handback FIX 1) -- already resolved by the caller
    (`_extract_scope_writes`) to either the command's true page-list
    position, or (inside an inlined common event) the calling 117's own
    position -- used both for the human `source` citation and `Write.
    list_index`. `117` recurses into `_extract_ce_writes` with that SAME
    resolved `index` as the forced attribution for everything the inlined
    event writes."""
    code = cmd.get("code")
    params = cmd.get("parameters") or []

    if code == CODE_SWITCH_WRITE:
        if len(params) < 3:
            return (), (Refusal("malformed_write", f"code 121 @list[{index}]: too few params"),), frozenset(), False
        lo, hi, value = params[0], params[1], params[2]
        on = value == 0
        writes = tuple(
            Assign(Switch(sid), frozenset({on}), conditional, f"code 121 @list[{index}]", index)
            for sid in range(lo, hi + 1)
        )
        return writes, (), frozenset(), False

    if code == CODE_VAR_WRITE:
        if len(params) < 5:
            return (), (Refusal("malformed_write", f"code 122 @list[{index}]: too few params"),), frozenset(), False
        lo, hi, op, operand_kind, operand = params[0], params[1], params[2], params[3], params[4]
        writes: list[Write] = []
        refusals: list[Refusal] = []
        for vid in range(lo, hi + 1):
            source = f"code 122 @list[{index}]"
            if op == 0 and operand_kind == 0 and isinstance(operand, int):
                writes.append(Assign(
                    Variable(vid), frozenset({operand}), conditional, source, index))
            elif op == 0 and operand_kind == 2 and len(params) >= 6:
                rlo, rhi = operand, params[5]
                if isinstance(rlo, int) and isinstance(rhi, int) and rhi >= rlo:
                    writes.append(Assign(
                        Variable(vid), frozenset(range(rlo, rhi + 1)), conditional, source, index))
                else:
                    refusals.append(Refusal(
                        "nonconstant_variable_write",
                        f"{source}: variable {vid} random bounds {operand!r}/{params[5]!r}",
                    ))
            elif op in _VAR_OP_SYMBOLS and operand_kind == 0 and isinstance(operand, int):
                writes.append(Adjust(
                    Variable(vid), _VAR_OP_SYMBOLS[op], operand, conditional, source, index))
            else:
                refusals.append(Refusal(
                    "nonconstant_variable_write",
                    f"{source}: variable {vid} op {op!r} operand_kind {operand_kind!r} "
                    f"operand {operand!r} not a constant-write shape",
                ))
        return tuple(writes), tuple(refusals), frozenset(), False

    if code == CODE_SELF_SWITCH_WRITE:
        if len(params) < 2:
            return (), (Refusal("malformed_write", f"code 123 @list[{index}]: too few params"),), frozenset(), False
        letter, value = params[0], params[1]
        writes = (Assign(
            SelfSwitch(map_id, event_id, letter), frozenset({value == 0}),
            conditional, f"code 123 @list[{index}]", index,
        ),)
        return writes, (), frozenset(), False

    if code == CODE_COMMON_EVENT_CALL:
        if not params:
            return (), (Refusal("malformed_write", f"code 117 @list[{index}]: no params"),), frozenset(), False
        ce_id = params[0]
        source_prefix = f"code 117 @list[{index}] (common event {ce_id})"
        # A strip-listed CE (reference/strip_list.json's `common_events`) is
        # a no-op, same disposition as `ruby_subset.search._exec_ce`
        # (CLAUDE.md §4.3 -- one strip-honoring rule, not two).
        if ce_id in stripped_ce_ids:
            return (), (), frozenset(), False
        if ce_id in visited_ce:
            return (), (Refusal(
                "common_event_cycle",
                f"{source_prefix}: already inlined on this path -- cycle",
            ),), frozenset(), False
        ce = common_events_by_id.get(ce_id)
        if ce is None:
            return (), (Refusal("missing_common_event", f"{source_prefix}: not found"),), frozenset(), False
        ce_commands = ce.get("list") or []
        tree = parse_tree(ce_commands)
        sub = _extract_ce_writes(
            tree, ce_commands, map_id, event_id, common_events_by_id,
            conditional, visited_ce | {ce_id}, stripped_ce_ids,
            forced_list_index=index,
        )
        return sub.writes, sub.refusals, sub.havoc_keys, sub.havoc_global

    if code in (CODE_SCRIPT, CODE_SCRIPT_CONT):
        # Handled at the caller as grouped script blocks, not per-leaf.
        return (), (), frozenset(), False

    return (), (), frozenset(), False


def _bag_texts(commands: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """`(position in `commands`, text)` for every script block (355 plus its
    655 continuations) and every 111 type-12 condition in `commands`."""
    out: list[tuple[int, str]] = []
    i = 0
    while i < len(commands):
        cmd = commands[i]
        code = cmd.get("code")
        params = cmd.get("parameters") or []
        if code in (CODE_SCRIPT, CODE_SCRIPT_CONT) and params:
            lines = [str(params[0])]
            j = i + 1
            while j < len(commands) and commands[j].get("code") == CODE_SCRIPT_CONT:
                lines.append(str((commands[j].get("parameters") or [""])[0]))
                j += 1
            out.append((i, "\n".join(lines)))
            i = j
            continue
        if code == CODE_CONDITIONAL and len(params) > 1 and params[0] == 12:
            out.append((i, str(params[1])))
        i += 1
    return out


def _bag_effects(
    commands: list[dict[str, Any]],
    *,
    index_of: dict[int, int],
    forced_list_index: int | None,
    conditional: bool,
    common_events_by_id: dict[int, dict[str, Any]],
    stripped_ce_ids: frozenset[int],
    visited_ce: frozenset[int],
    inline_ce: bool,
) -> tuple[list[Write], set[Key]]:
    """Key-item grants (`BagHas(X) = True`) and havocs in this scope's script
    and condition text (`story_state.bag`). `inline_ce` additionally walks
    every 117-called common event's whole body (all arms, conditional) -- used
    only where the interpreter path inlines CEs itself, so the structural leaf
    walk (which recurses through `_extract_leaf_writes`) never double-counts."""
    writes: list[Write] = []
    havoc: set[Key] = set()
    for pos, text in _bag_texts(commands):
        scan = scan_bag_text(text)
        if not scan.grants and not scan.havocs:
            continue
        if forced_list_index is not None:
            idx = forced_list_index
        else:
            idx = index_of.get(id(commands[pos]), -1)
        for item in sorted(scan.grants):
            writes.append(Assign(
                BagHas(item), frozenset({True}), conditional,
                f"script @list[{idx}]: grants {item}", idx))
        havoc |= {BagHas(item) for item in scan.havocs}
    if inline_ce:
        for pos, cmd in enumerate(commands):
            if cmd.get("code") != CODE_COMMON_EVENT_CALL or not (cmd.get("parameters") or []):
                continue
            ce_id = cmd["parameters"][0]
            ce = common_events_by_id.get(ce_id)
            if ce_id in stripped_ce_ids or ce_id in visited_ce or ce is None:
                continue
            idx = forced_list_index if forced_list_index is not None else index_of.get(id(cmd), -1)
            ce_cmds = ce.get("list") or []
            w, h = _bag_effects(
                ce_cmds, index_of={}, forced_list_index=idx, conditional=True,
                common_events_by_id=common_events_by_id, stripped_ce_ids=stripped_ce_ids,
                visited_ce=visited_ce | {ce_id}, inline_ce=True)
            writes.extend(w)
            havoc |= h
    return writes, havoc


def _extract_scope_writes(
    commands: list[dict[str, Any]],
    map_id: int,
    event_id: int,
    common_events_by_id: dict[int, dict[str, Any]],
    conditional: bool,
    visited_ce: frozenset[int],
    *,
    index_of: dict[int, int],
    forced_list_index: int | None,
    stripped_ce_ids: frozenset[int],
    row_id: str | None = None,
) -> ScopeExtraction:
    """`_extract_scope_writes_core` plus the key-item bag grants/havocs
    (`BagHas`, `story_state.bag`) read off the same scope's script text."""
    base = _extract_scope_writes_core(
        commands, map_id, event_id, common_events_by_id, conditional, visited_ce,
        index_of=index_of, forced_list_index=forced_list_index,
        stripped_ce_ids=stripped_ce_ids, row_id=row_id)
    bag_writes, bag_havoc = _bag_effects(
        commands, index_of=index_of, forced_list_index=forced_list_index,
        conditional=conditional, common_events_by_id=common_events_by_id,
        stripped_ce_ids=stripped_ce_ids, visited_ce=visited_ce,
        inline_ce=scope_needs_interpreter(commands))
    if not bag_writes and not bag_havoc:
        return base
    return _dc_replace(
        base,
        writes=base.writes + tuple(bag_writes),
        havoc_keys=base.havoc_keys | frozenset(bag_havoc),
    )


def _extract_scope_writes_core(
    commands: list[dict[str, Any]],
    map_id: int,
    event_id: int,
    common_events_by_id: dict[int, dict[str, Any]],
    conditional: bool,
    visited_ce: frozenset[int],
    *,
    index_of: dict[int, int],
    forced_list_index: int | None,
    stripped_ce_ids: frozenset[int],
    row_id: str | None = None,
) -> ScopeExtraction:
    """Everything one flat (already-scoped) command list writes -- a page
    trunk's own commands, a branch arm's own commands, or one scope of an
    inlined common event.

    `index_of` maps `id(cmd)` -> that command's position in its OWNING
    PAGE's raw `list` (built once per page/common-event by the caller);
    `forced_list_index`, when not `None`, overrides it for every write in
    this scope -- used when this scope is itself inside an inlined common
    event, so every write it produces is attributed to the calling page's
    117 command instead of a meaningless position inside the callee's own
    body (REDERIVATION_PLAN.md §16.3 C2b handback FIX 1).

    `row_id`, when not `None`, marks this as a genuine manifest row scope
    (called directly from `extract_map`/`extract_triggered_common_events`,
    never from `_extract_ce_writes`'s inlining walk) -- the only case where
    an unresolved out-of-scope read can become a `ComputedScope` rather
    than a conservative refusal (REDERIVATION_PLAN.md §16.3 C8 stage 4:
    "the unit of evaluation is a row scope"; a CE-internal arm has no row
    identity of its own to defer against).

    If `commands` needs the interpreter (`scope_needs_interpreter` -- any
    355/655 script block or an inline `\\ch[...]` text choice), the WHOLE
    scope is run once through `ruby_subset.search.search_scope`, which
    itself handles 121/122/123, 355/655, 117 inlining and `\\ch` -- so this
    function does NOT also walk it leaf-by-leaf in that case. A scope with
    neither keeps the original structural leaf walk, unchanged.
    """
    if scope_needs_interpreter(commands):
        result = search_scope(
            commands,
            map_id=map_id, event_id=event_id,
            common_events_by_id=common_events_by_id,
            stripped_ce_ids=stripped_ce_ids,
            read_domain=lambda key: None,
            index_of=index_of if forced_list_index is None else None,
            graphics_only_vars=graphics_only_variables(),
        )
        label = row_id if row_id is not None else f"ce-scope @list[{forced_list_index}]"
        if result.refusal is None:
            writes, nonscalar = writes_from_result(
                result, conditional=conditional, source_prefix=f"interpreter {label}",
            )
            if forced_list_index is not None:
                writes = tuple(_dc_replace(w, list_index=forced_list_index) for w in writes)
            return ScopeExtraction(
                writes=writes, havoc_keys=frozenset(nonscalar),
                witnesses=witness_citations(result),
            )
        if result.refusal.code == "search_unknown_read" and row_id is not None:
            # C8 stage 4: this row's writes depend on state the resolver
            # (`story_state/model.py`) must saturate first -- defer, don't
            # refuse outright. Until the resolver half lands (same commit,
            # per the lead's design), ALSO surface an `unparsed_state_write`
            # refusal with `havoc_global=True` so `model.py` stays sound in
            # the interim: a computed row with no resolver yet must still
            # look, to every EXISTING consumer, like "writes unknown."
            computed = ComputedScope(
                row_id=row_id, map_id=map_id, event_id=event_id, commands=commands,
                index_of=dict(index_of), common_events_by_id=common_events_by_id,
                stripped_ce_ids=stripped_ce_ids, conditional=conditional,
                first_unknown_read=result.refusal.detail,
            )
            return ScopeExtraction(
                refusals=(Refusal(
                    "unparsed_state_write",
                    f"interpreter {label}: computed row, unresolved read "
                    f"{result.refusal.detail} -- {result.refusal.code}",
                ),),
                havoc_global=True,
                computed=computed,
            )
        # Any other refusal code (party_model, ruby_parse_error,
        # ruby_unknown_call:*, search_cap, search_loop, search_ce_branches,
        # ruby_type_error:*, or a CE-nested `search_unknown_read` with no
        # row of its own to defer) -- pass the interpreter's own code
        # through unchanged (do not invent/translate a new one) and stay
        # conservative for everything downstream.
        # The row still writes SOMETHING. Name what the scripts can be seen
        # to assign so the model havocs those keys rather than everything
        # (model.py FIX 2b); fall back to global havoc only when nothing
        # could be named, exactly as the regex reader this replaced did.
        named = named_write_targets(commands, map_id=map_id, event_id=event_id)
        return ScopeExtraction(
            refusals=(Refusal(
                result.refusal.code, f"interpreter {label}: {result.refusal.detail}",
            ),),
            havoc_keys=frozenset(named),
            havoc_global=not named,
        )

    writes: list[Write] = []
    refusals: list[Refusal] = []
    havoc_keys: set[Key] = set()
    havoc_global = False
    i = 0
    while i < len(commands):
        cmd = commands[i]
        code = cmd.get("code")
        resolved_index = forced_list_index if forced_list_index is not None else index_of.get(id(cmd), -1)
        if code in (CODE_SCRIPT, CODE_SCRIPT_CONT):
            # No script/`\ch` anywhere in this scope reached this branch
            # (scope_needs_interpreter would have routed it above), so a
            # lone 355/655 here is structurally unreachable in practice --
            # still a no-op, not a crash, matching the old grouping's
            # "nothing recognized" disposition for an empty/blank block.
            i += 1
            continue
        w, r, hk, hg = _extract_leaf_writes(
            cmd, resolved_index, map_id, event_id, common_events_by_id, conditional,
            visited_ce, stripped_ce_ids,
        )
        writes.extend(w)
        refusals.extend(r)
        havoc_keys |= hk
        havoc_global = havoc_global or hg
        i += 1
    return ScopeExtraction(
        writes=tuple(writes), refusals=tuple(refusals),
        havoc_keys=frozenset(havoc_keys), havoc_global=havoc_global,
    )


def _extract_ce_writes(
    tree: list[Node],
    commands: list[dict[str, Any]],
    map_id: int,
    event_id: int,
    common_events_by_id: dict[int, dict[str, Any]],
    conditional: bool,
    visited_ce: frozenset[int],
    stripped_ce_ids: frozenset[int],
    *,
    forced_list_index: int,
) -> ScopeExtraction:
    """Inlines one common event: its own trunk writes inherit the caller's
    `conditional` flag; anything inside any of ITS OWN branch arms
    (recursively) is forced `conditional=True` (REDERIVATION_PLAN.md §16.3
    C2a item 4). EVERY write produced here -- trunk or nested arm -- carries
    `forced_list_index` (the calling 117's own position), never a position
    inside the callee's own command list; the callee's internal branching
    still matters for `conditional`, just not for cross-page write ordering.

    None of this recursion ever passes a `row_id` down to `_extract_scope_
    writes` -- a CE inlined into a row has no row identity of its own, so
    an unresolved out-of-scope read inside it can only become a
    conservative refusal, never a `ComputedScope` (see `_extract_scope_
    writes`'s own docstring)."""
    writes: list[Write] = []
    refusals: list[Refusal] = []
    havoc_keys: set[Key] = set()
    havoc_global = False

    trunk_commands = _flatten_scope(tree, commands)
    sub = _extract_scope_writes(
        trunk_commands, map_id, event_id, common_events_by_id, conditional, visited_ce,
        index_of={}, forced_list_index=forced_list_index, stripped_ce_ids=stripped_ce_ids,
    )
    writes.extend(sub.writes)
    refusals.extend(sub.refusals)
    havoc_keys |= sub.havoc_keys
    havoc_global = havoc_global or sub.havoc_global

    def _walk(nodes: list[Node]) -> None:
        nonlocal havoc_global
        for node in nodes:
            if isinstance(node, IfNode):
                for children in (node.then, node.otherwise if node.otherwise is not None else []):
                    arm_commands = _flatten_scope(children, commands)
                    sub2 = _extract_scope_writes(
                        arm_commands, map_id, event_id, common_events_by_id, True, visited_ce,
                        index_of={}, forced_list_index=forced_list_index,
                        stripped_ce_ids=stripped_ce_ids,
                    )
                    writes.extend(sub2.writes)
                    refusals.extend(sub2.refusals)
                    havoc_keys.update(sub2.havoc_keys)
                    havoc_global = havoc_global or sub2.havoc_global
                    _walk(children)
            elif isinstance(node, ChoiceNode):
                for _, _, children in node.arms:
                    arm_commands = _flatten_scope(children, commands)
                    sub2 = _extract_scope_writes(
                        arm_commands, map_id, event_id, common_events_by_id, True, visited_ce,
                        index_of={}, forced_list_index=forced_list_index,
                        stripped_ce_ids=stripped_ce_ids,
                    )
                    writes.extend(sub2.writes)
                    refusals.extend(sub2.refusals)
                    havoc_keys.update(sub2.havoc_keys)
                    havoc_global = havoc_global or sub2.havoc_global
                    _walk(children)
            elif isinstance(node, LoopNode):
                _walk(node.children)
            # Leaf / TextRun: no nested branch structure.

    _walk(tree)
    return ScopeExtraction(
        writes=tuple(writes), refusals=tuple(refusals),
        havoc_keys=frozenset(havoc_keys), havoc_global=havoc_global,
    )


# --- top-level entry point -----------------------------------------------


def extract_map(
    map_id: int,
    map_data: dict[str, Any],
    *,
    common_events: list[dict[str, Any]],
    switch_labels: dict[int, str],
    stripped_ce_ids: frozenset[int] | None = None,
) -> dict[str, "RowState"]:
    """Every row's `RowState` for one map's events, keyed by manifest row id
    (the same ids `chapter_manifest.generator.iter_page_scopes` mints).

    `stripped_ce_ids` defaults to `scope_search.stripped_ce_ids_for` against
    the repo's own `reference/` dir when not supplied -- so a caller that
    hasn't been updated to thread it through explicitly still gets
    strip-list-honoring 117 inlining for free (REDERIVATION_PLAN.md §16.3
    C8 stage 4 measurement note: this changed CE 4/5/6 GTS/VT/LOBBY
    inlining, previously unconditional)."""
    sce = stripped_ce_ids if stripped_ce_ids is not None else stripped_ce_ids_for(_default_reference_dir())
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
            # id(cmd) -> this command's true position in THIS PAGE's own
            # list (REDERIVATION_PLAN.md §16.3 C2b handback FIX 1) -- every
            # scope's commands are the SAME dict objects sliced out of
            # `raw_commands` by `_flatten_scope`, so identity lookup works.
            index_of = {id(cmd): idx for idx, cmd in enumerate(raw_commands)}
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

                sub = _extract_scope_writes(
                    scope.commands, map_id, event_id, common_events_by_id,
                    False, frozenset(),
                    index_of=index_of, forced_list_index=None,
                    stripped_ce_ids=sce, row_id=scope.row_id,
                )
                writes, write_refusals = sub.writes, sub.refusals
                havoc_keys, havoc_global = sub.havoc_keys, sub.havoc_global

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
                    havoc_keys=tuple(sorted(havoc_keys, key=repr)),
                    havoc_global=havoc_global,
                    computed=sub.computed,
                    witnesses=sub.witnesses,
                )

    return result


# --- triggered common events (pseudo-rows) --------------------------------


def _pseudo_ce_row_id(ce_id: int) -> str:
    return f"common/ce{ce_id:03d}"


def extract_triggered_common_events(
    common_events: list[dict[str, Any]],
    *,
    switch_labels: dict[int, str],
    stripped_ce_ids: frozenset[int] | None = None,
) -> dict[str, "RowState"]:
    """One pseudo-`RowState` family per autorun/parallel common event
    (REDERIVATION_PLAN.md §16.3 C2 ruling (e)): a trunk row `common/ceNNN`
    gated on the common event's own `switch_id`, plus a branch-arm child row
    `common/ceNNN/bM` per branch arm, using the SAME scope walk as a map
    page (`chapter_manifest.generator.iter_page_scopes`) -- the common
    event's own command list is walked exactly as if it were one page's
    `list`, then the resulting row ids are remapped from the page/branch
    grammar onto the `common/ceNNN[/bM]` pseudo grammar (see this module's
    docstring for why these ids never go through `schema.parse_row_id`).

    A common event has no map or event identity of its own, so:
      - its trunk `page_tests` is exactly the one `Switch(switch_id) == True`
        gate RMXP itself checks before running it (both `forced=True`, a
        single-page `event_page_row_ids`, so the highest-live-page kill rule
        never applies -- there IS no higher page);
      - a self-switch write inside it is invalid (RMXP has no "current event"
        for a common event to write its own self-switch against) and is
        refused rather than silently attributed to a bogus (map_id, event_id).
    """
    sce = stripped_ce_ids if stripped_ce_ids is not None else stripped_ce_ids_for(_default_reference_dir())
    result: dict[str, RowState] = {}

    for ce in common_events:
        trigger_raw = ce.get("trigger")
        if trigger_raw not in _CE_FORCED_TRIGGERS:
            continue
        switch_id = ce.get("switch_id")
        if not switch_id:
            continue
        ce_id = ce["id"]
        trunk_row_id = _pseudo_ce_row_id(ce_id)
        trigger = _CE_TRIGGER_NAMES.get(trigger_raw, str(trigger_raw))

        label = switch_labels.get(switch_id)
        if label is not None and label.startswith("s:"):
            result[trunk_row_id] = RowState(
                row_id=trunk_row_id, parent_row_id=None,
                page_tests=(), page_refusals=(Refusal(
                    "unmodelled_predicate",
                    f"common event {ce_id} gating switch {switch_id}: runtime "
                    f"predicate {label!r}, not a plain switch -- not modelled",
                ),),
                arm_guard=None, writes=(), trigger=trigger, forced=True,
                refusals=(), event_page_row_ids=(trunk_row_id,),
            )
            continue

        page_tests = (Test(Switch(switch_id), "==", True),)
        commands = ce.get("list") or []
        index_of = {id(cmd): idx for idx, cmd in enumerate(commands)}
        scopes = iter_page_scopes(0, {"id": ce_id}, 0, {"list": commands})

        id_map: dict[str, str] = {scopes[0].row_id: trunk_row_id}
        page_prefix = scopes[0].row_id
        for scope in scopes[1:]:
            suffix = scope.row_id[len(page_prefix):]  # e.g. "/b2"
            id_map[scope.row_id] = trunk_row_id + suffix

        for scope in scopes:
            new_row_id = id_map[scope.row_id]
            new_parent_row_id = (
                id_map[scope.parent_row_id] if scope.parent_row_id is not None else None
            )
            arm_guard: ArmGuard | None = None
            guard_refusals: tuple[Refusal, ...] = ()
            if scope.branch is not None:
                arm_guard, guard_refusals = _arm_guard(
                    scope.branch, commands, map_id=0, event_id=ce_id)

            sub = _extract_scope_writes(
                scope.commands, 0, ce_id, {}, False, frozenset(),
                index_of=index_of, forced_list_index=None,
                stripped_ce_ids=sce, row_id=new_row_id,
            )
            raw_writes, write_refusals = sub.writes, sub.refusals
            havoc_keys, havoc_global = sub.havoc_keys, sub.havoc_global
            writes: list[Write] = []
            self_switch_refusals: list[Refusal] = []
            for w in raw_writes:
                if isinstance(w.key, SelfSwitch):
                    self_switch_refusals.append(Refusal(
                        "invalid_self_switch_write_in_common_event",
                        f"common event {ce_id}: {w.source} -- a common event "
                        "has no self-switch of its own",
                    ))
                else:
                    writes.append(w)

            result[new_row_id] = RowState(
                row_id=new_row_id,
                parent_row_id=new_parent_row_id,
                page_tests=page_tests,
                page_refusals=(),
                arm_guard=arm_guard,
                writes=tuple(writes),
                trigger=trigger,
                forced=True,
                refusals=guard_refusals + write_refusals + tuple(self_switch_refusals),
                event_page_row_ids=(trunk_row_id,),
                havoc_keys=tuple(sorted(havoc_keys, key=repr)),
                havoc_global=havoc_global,
                computed=sub.computed,
                witnesses=sub.witnesses,
            )

    return result
