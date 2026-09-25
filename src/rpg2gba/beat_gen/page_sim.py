"""One page, one firing (REDERIVATION_PLAN.md §16.3 ruling 19, steps 4-5;
the caller is `beat_gen/state_arms.py`). This module decides, given a
concrete firing (player cell, the
firing event's own cell, and Show-Choices answers), which of ONE page's
branch-arm rows a real walk-through certainly runs, certainly skips, or
can't be resolved without playing it -- a small, bounded interpreter, not
another sound-over-approximation pass like `story_state/model.py`'s
saturation.

The two modules solve different problems on purpose. `model.py` asks "across
every route through the whole chapter, what MIGHT this key be" -- a join
over every possibly-live row, flow-insensitive. This module asks "given ONE
concrete pass through ONE page, starting from ONE concrete state, what
DEFINITELY happens" -- flow-sensitive, single-path, and (where the page
itself is undecidable -- a random roll, an unresolved script, a lost
`goto`) explicitly bounded rather than silently wrong. Where this module
can't decide, it says so (`undecided`) rather than guessing, and once
anything forces it to guess anyway (a havoc'd read, an ambiguous branch
whose body still had to run SOMETHING), `PageRun.exact` drops to `False` so
the caller knows the resulting state is a sound superset, not a fact.

Reuses `story_state.model`'s `possible`/`certain`/`VARIABLE_TOP`/`_get` for
reading the value-set abstraction a `RowState`'s tests are written against,
and `chapter_manifest.generator.iter_page_scopes` (the same walk
`story_state.extract` used to mint each arm's row id) for navigation --
which row id is the "then" vs "else" of a construct, which choice arm
answers which index, which rows nest under which -- so this module never
has to re-derive that from `RowState.arm_guard`, which is `None` (no
`opener_index` to navigate by) for a hard-refused arm.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from rpg2gba.chapter_manifest.generator import PageScope, iter_page_scopes
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.conversion_agent.transpiler import (
    LABEL,
    JUMP_TO_LABEL,
    EXIT_EVENT,
    SET_MOVE_ROUTE,
    TRANSFER_PLAYER,
    WAIT_MOVE_COMPLETION,
    ChoiceNode,
    IfNode,
    Leaf,
    LoopNode,
    Node,
)
from rpg2gba.story_state.extract import ArmGuard, RowState
from rpg2gba.story_state.model import VARIABLE_TOP, _get, certain, possible
from rpg2gba.story_state.state import (
    Adjust,
    Assign,
    EngineKey,
    Key,
    TempSwitch,
    Variable,
    Write,
)

# --- RMXP command/leaf codes this interpreter cares about, not already
# exported by `conversion_agent.transpiler` (kept local, same disposition as
# `story_state/extract.py`'s own "no single canonical command-code module"
# note). ---------------------------------------------------------------
_BREAK_LOOP = 113
_MOVE_ROUTE_STEP = 509

# RPG::MoveCommand codes: 1-4 cardinal, 5-8 diagonal, 9-13 random/toward/
# away/forward/backward (undeciding), 14 jump-by-delta.
_MOVE_DELTA: dict[int, tuple[int, int]] = {
    1: (0, 1), 2: (-1, 0), 3: (1, 0), 4: (0, -1),
    5: (-1, 1), 6: (1, 1), 7: (-1, -1), 8: (1, -1),
}
_MOVE_UNDECIDING = frozenset({9, 10, 11, 12, 13})
_MOVE_JUMP = 14

# The player's facing, as RMXP numbers it (2 down, 4 left, 6 right, 8 up),
# for a type-6 "character is facing" condition on the player (params
# `[6, -1, dir]`). A cardinal move or a turn sets it; anything that turns
# the player some other way loses it (None: undecided). Direction fix (35)
# freezes it until 36, which we can't see past either, so both lose it.
_MOVE_FACES: dict[int, int] = {1: 2, 2: 4, 3: 6, 4: 8, 16: 2, 17: 4, 18: 6, 19: 8}
_MOVE_LOSES_FACING = frozenset({5, 6, 7, 8, 9, 10, 11, 12, 13, 20, 21, 22, 23, 24, 25, 26})
_DIRECTION_FIX_ON, _DIRECTION_FIX_OFF = 35, 36
_CHARACTER_DIRECTION = 6
_PLAYER = -1

_MAX_STEPS = 2000

# --- public shapes -----------------------------------------------------


@dataclass(frozen=True)
class Firing:
    """One concrete firing of one page: where the player stood, where the
    firing event itself sits (for `get_character(0).onEvent?`), and how any
    102 Show Choices were answered -- `choice_answers[opener_index]` is the
    402 arm's own `choice_index`, or `-1` for the 403 cancel arm. A talk or
    touch page's player starts out facing the event from `cell`, which
    decides a `[6, -1, dir]` player-facing branch (tracked through the
    player's move routes)."""

    cell: tuple[int, int] | None
    event_cell: tuple[int, int] | None
    choice_answers: Mapping[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class PageRun:
    """`taken | not_taken | undecided` partitions every branch-arm row id of
    `page_row_id` in `row_states` -- pairwise disjoint, no leftovers.
    `state` is the input state plus this firing's effects (a fresh dict; the
    input is never mutated). `exact` drops to `False` the first time an
    undecided construct's conservative writes actually touched `state`, a
    row's `havoc_global` fired, or control flow was lost (poison, below) --
    from that point on `state` is a sound superset of the truth, not the
    truth itself."""

    taken: frozenset[str]
    not_taken: frozenset[str]
    undecided: frozenset[str]
    state: dict
    exact: bool


# --- control-flow signals -----------------------------------------------


class _Break(Exception):
    """113 Break Loop."""


class _ExitPage(Exception):
    """115 Exit Event Processing."""


class _Poison(Exception):
    """Control flow (or the step budget) was lost -- see module docstring
    and `run_page`'s poison handling."""


# --- row-id helpers ------------------------------------------------------


def _is_branch_row(row_id: str) -> bool:
    try:
        return parse_row_id(row_id).kind == "branch"
    except ValueError:
        return False


def _owning_page_row_id(row_id: str) -> str | None:
    try:
        return parse_row_id(row_id).owning_page_row_id
    except ValueError:
        return None


# --- small value-set helpers (mirrors story_state/model.py's own, kept
# local rather than importing more private symbols than the ones the brief
# names -- possible/certain/VARIABLE_TOP/_get). --------------------------


def _cmp(op: str, a: int, b: int) -> bool:
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    raise ValueError(f"page_sim: unknown comparison op {op!r}")


def _apply_op(op: str, v: int, amount: int) -> int:
    if op == "+":
        return v + amount
    if op == "-":
        return v - amount
    if op == "*":
        return v * amount
    if op == "/":
        return v // amount if amount != 0 else v
    if op == "%":
        return v % amount if amount != 0 else v
    raise ValueError(f"page_sim: unknown adjust op {op!r}")


def _union(a: frozenset, b: frozenset) -> frozenset:
    if VARIABLE_TOP in a or VARIABLE_TOP in b:
        return frozenset({VARIABLE_TOP})
    return a | b


# --- deciding one arm's guard --------------------------------------------


def _facing_toward(cell: tuple[int, int] | None,
                   event_cell: tuple[int, int] | None) -> int | None:
    """The RMXP facing of a player who fires a talk/touch page from `cell`
    at an event on `event_cell`: toward it, along one axis (a counter puts
    it two tiles away). None when that isn't a straight line."""
    if cell is None or event_cell is None:
        return None
    dx, dy = event_cell[0] - cell[0], event_cell[1] - cell[1]
    if dx == 0 and dy != 0:
        return 2 if dy > 0 else 8
    if dy == 0 and dx != 0:
        return 6 if dx > 0 else 4
    return None


_GAME_PLAYER_RE = re.compile(r"\$game_player\.([xy])\s*(==|!=|>=|<=|>|<)\s*(-?\d+)")
_ON_EVENT_RE = re.compile(r"get_character\(-?\d+\)\.onEvent\?")
_PICK_BERRY_RE = re.compile(r"pbPickBerry\(.*\)")


def _decide_input(
    opener_params: list[Any], negated: bool,
    cell: tuple[int, int] | None, event_cell: tuple[int, int] | None,
) -> bool | None:
    """A script-typed (`[12, text]`) condition whose family is `input`:
    player position, `onEvent?`, or a berry-pick confirm. `negated` is
    `ArmGuard.negated` (True for the else arm) -- the text itself is always
    the THEN sense; the else arm's truth is its logical negation."""
    text = opener_params[1] if len(opener_params) > 1 and isinstance(opener_params[1], str) else ""
    normalized = " ".join(text.split())

    m = _GAME_PLAYER_RE.fullmatch(normalized)
    if m:
        if cell is None:
            return None
        axis, op, value = m.group(1), m.group(2), int(m.group(3))
        actual = cell[0] if axis == "x" else cell[1]
        base = _cmp(op, actual, value)
        return base if not negated else not base

    if _ON_EVENT_RE.fullmatch(normalized):
        if cell is None or event_cell is None:
            return None
        base = cell == event_cell
        return base if not negated else not base

    if _PICK_BERRY_RE.fullmatch(normalized):
        # The walk always answers the harvest confirm "yes" (module docstring).
        return not negated

    return None


def _decide_arm(
    guard: ArmGuard | None, opener_params: list[Any],
    cell: tuple[int, int] | None, event_cell: tuple[int, int] | None,
    state: dict, global_havoc: bool,
) -> bool | None:
    """True/False when this arm's own guard is decided against `state` (or
    `cell`/`event_cell`), else `None` -- undecided."""
    if guard is None:
        return None
    if guard.tests:
        if global_havoc:
            return None
        if all(certain(t, state) for t in guard.tests):
            return True
        if any(not possible(t, state) for t in guard.tests):
            return False
        return None
    outcome = guard.outcome
    if outcome is None:
        return None
    if outcome.kind == "always":
        return True
    if outcome.kind == "dead":
        return False
    if outcome.kind in ("fork", "harness", "capability"):
        # The walk wins battles, has bag space, holds every capability --
        # same policy as beat_gen/arms.py's blocked_arms.
        return False
    if outcome.kind == "input":
        return _decide_input(opener_params, guard.negated, cell, event_cell)
    return None  # random, unmodelled, or a "state" outcome with no regex match


# --- poison detection ------------------------------------------------------

_POISON_LEAF_CODES = frozenset({_BREAK_LOOP, EXIT_EVENT, JUMP_TO_LABEL})


def _contains_poison_code(nodes: list[Node]) -> bool:
    """True if `nodes`, recursively (through nested ifs/choices/loops),
    contains a 113/115/119 leaf -- taking this subtree without knowing
    whether it runs would lose control flow (module docstring)."""
    for node in nodes:
        if isinstance(node, Leaf) and node.cmd.get("code") in _POISON_LEAF_CODES:
            return True
        if isinstance(node, IfNode):
            if _contains_poison_code(node.then):
                return True
            if node.otherwise is not None and _contains_poison_code(node.otherwise):
                return True
        elif isinstance(node, ChoiceNode):
            for _, _, children in node.arms:
                if _contains_poison_code(children):
                    return True
        elif isinstance(node, LoopNode):
            if _contains_poison_code(node.children):
                return True
    return False


# --- the interpreter -------------------------------------------------------


class _Runner:
    """Mutable interpreter state for one `run_page` call."""

    def __init__(
        self, page_row_id: str, scopes: list[PageScope],
        row_states: Mapping[str, RowState],
        state: Mapping[Key, frozenset], firing: Firing,
    ) -> None:
        self.row_states = row_states
        self.state: dict[Key, frozenset] = dict(state)
        self.cell = firing.cell
        self.event_cell = firing.event_cell
        self.choice_answers = firing.choice_answers
        self.facing: int | None = None
        self._direction_fixed = False
        page_row = row_states.get(page_row_id)
        if page_row is not None and page_row.trigger in ("action", "player_touch", "event_touch"):
            self.facing = _facing_toward(firing.cell, firing.event_cell)

        self.taken: set[str] = set()
        self.not_taken: set[str] = set()
        self.undecided: set[str] = set()
        self.exact = True
        self.global_havoc = False
        self.steps = 0
        self._route_target: int | None = None
        self._writes_cache: dict[str, dict[int, tuple[Write, ...]]] = {}

        # Structural navigation (which row id is which arm of which
        # construct) comes from `iter_page_scopes` -- the SAME walk
        # `story_state.extract` used to mint these row ids -- never from
        # `RowState.arm_guard`, which is `None` for a hard-refused arm
        # (extract.py couldn't parse its condition at all) and so carries
        # no `opener_index`/`negated` to navigate by. Content (the actual
        # guard to decide, writes, havoc) still comes from `row_states`.
        self.scope_children: dict[str, list[str]] = {}
        self.if_arms: dict[tuple[str, int], dict[str, str]] = {}
        self.choice_arms: dict[tuple[str, int], dict[int, str]] = {}
        for scope in scopes:
            if scope.parent_row_id is not None:
                self.scope_children.setdefault(scope.parent_row_id, []).append(scope.row_id)
            branch = scope.branch
            if branch is None:
                continue
            key = (scope.parent_row_id, branch.opener_index)
            if branch.arm_kind in ("then", "else"):
                self.if_arms.setdefault(key, {})[branch.arm_kind] = scope.row_id
            else:
                choice_key = -1 if branch.choice_index is None else branch.choice_index
                self.choice_arms.setdefault(key, {})[choice_key] = scope.row_id

        self.all_arms = frozenset(
            rid for rid in row_states
            if _owning_page_row_id(rid) == page_row_id and _is_branch_row(rid)
        )

    # -- state mutation ----------------------------------------------------

    def _step(self) -> None:
        self.steps += 1
        if self.steps > _MAX_STEPS:
            raise _Poison()

    def _apply_havoc(self, key: Key) -> None:
        if isinstance(key, (Variable, EngineKey)):
            self.state[key] = frozenset({VARIABLE_TOP})
        else:
            self.state[key] = _get(self.state, key) | frozenset({False, True})

    def _enter(self, row: RowState) -> None:
        for key in row.havoc_keys:
            self._apply_havoc(key)
        if row.havoc_global:
            self.exact = False
            self.global_havoc = True

    def _apply_write_certain(self, write: Write) -> None:
        if isinstance(write.key, TempSwitch):
            return  # never persisted (state.py)
        if isinstance(write, Assign):
            if write.conditional:
                self.state[write.key] = _get(self.state, write.key) | write.values
            else:
                self.state[write.key] = frozenset(write.values)
        elif isinstance(write, Adjust):
            cur = _get(self.state, write.key)
            if VARIABLE_TOP in cur:
                return
            self.state[write.key] = frozenset(_apply_op(write.op, v, write.amount) for v in cur)
        else:
            raise TypeError(f"page_sim: unknown write shape {write!r}")

    def _apply_write_conservative(self, write: Write) -> None:
        if isinstance(write.key, TempSwitch):
            return
        cur = _get(self.state, write.key)
        if isinstance(write, Assign):
            self.state[write.key] = _union(cur, write.values)
        elif isinstance(write, Adjust):
            if VARIABLE_TOP in cur:
                return
            adjusted = frozenset(_apply_op(write.op, v, write.amount) for v in cur)
            self.state[write.key] = _union(cur, adjusted)
        else:
            raise TypeError(f"page_sim: unknown write shape {write!r}")

    def _writes_index(self, row_id: str) -> dict[int, tuple[Write, ...]]:
        cached = self._writes_cache.get(row_id)
        if cached is not None:
            return cached
        row = self.row_states.get(row_id)
        by_index: dict[int, list[Write]] = {}
        if row is not None:
            for w in row.writes:
                by_index.setdefault(w.list_index, []).append(w)
        result = {idx: tuple(ws) for idx, ws in by_index.items()}
        self._writes_cache[row_id] = result
        return result

    def _apply_indexed_writes(self, writes_by_index: dict[int, tuple[Write, ...]], idx: int) -> None:
        for w in writes_by_index.get(idx, ()):
            self._apply_write_certain(w)

    # -- arm/row bookkeeping ------------------------------------------------

    def _mark_not_taken_subtree(self, row_id: str) -> None:
        stack = [row_id]
        while stack:
            r = stack.pop()
            self.not_taken.add(r)
            stack.extend(self.scope_children.get(r, ()))

    def _undecide(self, row_ids: list[str], node_lists: list[list[Node]]) -> None:
        touched: set[str] = set()
        for r in row_ids:
            stack = [r]
            while stack:
                cur = stack.pop()
                if cur in touched:
                    continue
                touched.add(cur)
                stack.extend(self.scope_children.get(cur, ()))
        self.undecided.update(touched)

        wrote = False
        for r in touched:
            row = self.row_states.get(r)
            if row is None:
                continue
            for w in row.writes:
                self._apply_write_conservative(w)
                wrote = True
            for key in row.havoc_keys:
                self._apply_havoc(key)
                wrote = True
            if row.havoc_global:
                self.exact = False
                self.global_havoc = True
        if wrote:
            self.exact = False

        if any(_contains_poison_code(nl) for nl in node_lists):
            raise _Poison()

    def _if_children(self, row_id: str, opener_index: int) -> tuple[str, str]:
        arms = self.if_arms.get((row_id, opener_index), {})
        then_row, else_row = arms.get("then"), arms.get("else")
        if then_row is None or else_row is None:
            raise ValueError(
                f"page_sim: {row_id!r} opener {opener_index}: missing then/else row state")
        return then_row, else_row

    def _choice_children(self, row_id: str, opener_index: int) -> dict[int, str]:
        return dict(self.choice_arms.get((row_id, opener_index), {}))

    # -- node execution ------------------------------------------------------

    def _exec_if(self, node: IfNode, row_id: str) -> None:
        then_row, else_row = self._if_children(row_id, node.index)
        then_rs = self.row_states.get(then_row)
        else_rs = self.row_states.get(else_row)
        params = node.cmd.get("parameters") or []
        if len(params) >= 3 and params[0] == _CHARACTER_DIRECTION and params[1] == _PLAYER:
            # Decided here, not by `_decide_arm`: the facing guard carries no
            # `negated`, and only the construct knows which arm is which.
            t, e = self._decide_player_facing(params)
        else:
            t = _decide_arm(then_rs.arm_guard if then_rs else None, params,
                             self.cell, self.event_cell, self.state, self.global_havoc)
            e = _decide_arm(else_rs.arm_guard if else_rs else None, params,
                             self.cell, self.event_cell, self.state, self.global_havoc)
        if t is True and e is True:
            raise ValueError(
                f"page_sim: {then_row!r}/{else_row!r} both decided true -- contradiction")
        if t is False and e is False:
            raise ValueError(
                f"page_sim: {then_row!r}/{else_row!r} both decided false -- contradiction")

        if t is True:
            self._mark_not_taken_subtree(else_row)
            self.taken.add(then_row)
            if then_rs is not None:
                self._enter(then_rs)
            self._exec(node.then, then_row)
        elif e is True:
            self._mark_not_taken_subtree(then_row)
            self.taken.add(else_row)
            if else_rs is not None:
                self._enter(else_rs)
            self._exec(node.otherwise if node.otherwise is not None else [], else_row)
        else:
            self._undecide(
                [then_row, else_row],
                [node.then, node.otherwise if node.otherwise is not None else []],
            )

    def _exec_choice(self, node: ChoiceNode, row_id: str) -> None:
        opener_index = node.index
        by_key = self._choice_children(row_id, opener_index)
        arms_by_key = {
            (-1 if choice_index is None else choice_index): children
            for choice_index, _text, children in node.arms
        }
        answer = self.choice_answers.get(opener_index)
        if answer is None:
            self._undecide(list(by_key.values()), list(arms_by_key.values()))
            return
        if answer not in by_key or answer not in arms_by_key:
            raise ValueError(
                f"page_sim: choice at list[{opener_index}] answered {answer!r}, "
                f"no such arm among {sorted(by_key)}")
        chosen_row = by_key[answer]
        chosen_nodes = arms_by_key[answer]
        for key, rid in by_key.items():
            if key != answer:
                self._mark_not_taken_subtree(rid)
        self.taken.add(chosen_row)
        chosen_rs = self.row_states.get(chosen_row)
        if chosen_rs is not None:
            self._enter(chosen_rs)
        self._exec(chosen_nodes, chosen_row)

    def _exec_loop(self, node: LoopNode, row_id: str) -> None:
        while True:
            self._step()
            try:
                self._exec(node.children, row_id)
            except _Break:
                return
            # Falling off the end of the body means RMXP's own 413 Repeat
            # Above fired -- go again.

    def _find_label(self, nodes: list[Node], jump_cmd: dict[str, Any]) -> int | None:
        """The position within `nodes` (this SAME scope -- see module
        docstring's deviation note) of a 118 Label leaf matching the 119's
        own target name, or `None` if it isn't a sibling here."""
        params = jump_cmd.get("parameters") or []
        name = params[0] if params else None
        for j, n in enumerate(nodes):
            if isinstance(n, Leaf) and n.cmd.get("code") == LABEL:
                p = n.cmd.get("parameters") or []
                if p and p[0] == name:
                    return j
        return None

    def _apply_move_step(self, cmd: dict[str, Any]) -> None:
        if self._route_target != -1:
            return
        params = cmd.get("parameters") or []
        sub = params[0] if params else {}
        subcode = sub.get("code") if isinstance(sub, dict) else None
        self._apply_facing_step(subcode, sub)
        if self.cell is None:
            return
        x, y = self.cell
        if subcode in _MOVE_DELTA:
            dx, dy = _MOVE_DELTA[subcode]
            self.cell = (x + dx, y + dy)
        elif subcode in _MOVE_UNDECIDING:
            self.cell = None
        elif subcode == _MOVE_JUMP:
            sp = sub.get("parameters") or []
            dx = sp[0] if len(sp) > 0 else 0
            dy = sp[1] if len(sp) > 1 else 0
            self.cell = (x + dx, y + dy)
        # Any other move sub-command (turn, wait, speed change, ...)
        # doesn't reposition the player.

    def _apply_facing_step(self, subcode: int | None, sub: Any) -> None:
        if subcode in (_DIRECTION_FIX_ON, _DIRECTION_FIX_OFF):
            self._direction_fixed = subcode == _DIRECTION_FIX_ON
            self.facing = None
        elif self._direction_fixed:
            return
        elif subcode in _MOVE_FACES:
            self.facing = _MOVE_FACES[subcode]
        elif subcode in _MOVE_LOSES_FACING:
            self.facing = None
        elif subcode == _MOVE_JUMP:
            sp = (sub.get("parameters") or []) if isinstance(sub, dict) else []
            if any(sp[:2]):
                self.facing = None   # a jump turns toward its larger axis

    def _decide_player_facing(self, params: list[Any]) -> tuple[bool | None, bool | None]:
        """(then, else) for a `[6, -1, dir]` condition on the player."""
        if self.facing is None:
            return None, None
        base = self.facing == params[2]
        return base, not base

    def _exec(self, nodes: list[Node], row_id: str) -> None:
        writes_by_index = self._writes_index(row_id)
        i = 0
        while i < len(nodes):
            node = nodes[i]
            self._step()
            if isinstance(node, IfNode):
                self._exec_if(node, row_id)
            elif isinstance(node, ChoiceNode):
                self._exec_choice(node, row_id)
            elif isinstance(node, LoopNode):
                self._exec_loop(node, row_id)
            else:
                self._apply_indexed_writes(writes_by_index, node.index)
                if isinstance(node, Leaf):
                    code = node.cmd.get("code")
                    if code == _BREAK_LOOP:
                        raise _Break()
                    if code == EXIT_EVENT:
                        raise _ExitPage()
                    if code == JUMP_TO_LABEL:
                        target = self._find_label(nodes, node.cmd)
                        if target is None:
                            raise _Poison()
                        i = target
                        continue
                    if code == TRANSFER_PLAYER:
                        self.cell = None
                        tp = node.cmd.get("parameters") or []
                        if len(tp) > 4 and tp[4] in (2, 4, 6, 8):
                            self.facing = tp[4]   # 0 retains it (engine: WARP_RETAIN_FACING)
                    elif code == SET_MOVE_ROUTE:
                        params = node.cmd.get("parameters") or []
                        self._route_target = params[0] if params else None
                    elif code == _MOVE_ROUTE_STEP:
                        self._apply_move_step(node.cmd)
                    elif code == WAIT_MOVE_COMPLETION:
                        self._route_target = None
            i += 1


# --- entry point -----------------------------------------------------------


def run_page(
    page_row_id: str, page: Mapping[str, Any],
    row_states: Mapping[str, RowState], state: Mapping[Key, frozenset],
    firing: Firing,
) -> PageRun:
    """One firing of one page -- see module docstring for the contract."""
    row = row_states.get(page_row_id)
    if row is None:
        raise ValueError(f"page_sim: no RowState for page {page_row_id!r}")

    parsed = parse_row_id(page_row_id)
    scopes = iter_page_scopes(parsed.map_id, {"id": parsed.event_id}, parsed.page_idx, page)
    tree = scopes[0].nodes  # the trunk scope is always first (iter_page_scopes docstring)

    runner = _Runner(page_row_id, scopes, row_states, state, firing)
    runner._enter(row)

    poisoned = False
    try:
        runner._exec(tree, page_row_id)
    except _ExitPage:
        pass
    except _Break:
        # A 113 with no enclosing loop is a malformed page, not our problem
        # to diagnose -- treat it the same as reaching the end of the page.
        pass
    except _Poison:
        poisoned = True

    if poisoned:
        # Every arm not already proven taken/not-taken is undecided; its
        # writes (and any row still reachable from it) are folded in
        # conservatively before we stop (module docstring, "poison").
        remaining = runner.all_arms - runner.taken - runner.not_taken
        for rid in remaining:
            rs = row_states.get(rid)
            if rs is None:
                continue
            for w in rs.writes:
                runner._apply_write_conservative(w)
            for key in rs.havoc_keys:
                runner._apply_havoc(key)
        runner.exact = False
        not_taken_final = runner.not_taken - runner.taken
    else:
        # Execution finished on its own (fell off the page, or a certain
        # 115): everything not taken and not explicitly undecided genuinely
        # never ran.
        not_taken_final = runner.all_arms - runner.taken - runner.undecided

    taken_final = frozenset(runner.taken)
    not_taken_final = frozenset(not_taken_final) - taken_final
    undecided_final = runner.all_arms - taken_final - not_taken_final

    return PageRun(
        taken=taken_final, not_taken=frozenset(not_taken_final),
        undecided=frozenset(undecided_final), state=dict(runner.state),
        exact=runner.exact,
    )
