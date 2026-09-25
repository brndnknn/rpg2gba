"""Concrete evaluator for the embedded-Ruby subset (REDERIVATION_PLAN.md C8
stage 2).

This is CONCRETE execution -- one run, over one assignment of inputs and
world reads -- not abstract interpretation over sets. Arrays and
`index(max)` (Bambo's starter tally) don't survive being turned into value
sets; running the actual Ruby against a specific oracle is the only thing
that gets them right. Enumerating over the input/read space to find every
reachable outcome is stage 3's job (`REDERIVATION_PLAN.md` C8 design (3)) --
this module exposes exactly the two hooks that needs: `Oracle` (what
non-local state feeds in) and `InputSource.domain` (what to enumerate).

Two entry points, matching `ruby_subset.parser`'s two parse entry points:

* `evaluate_program(program, oracle=..., event=..., locals_in=...)` -- a
  whole 355/655 script block.
* `evaluate_expression(node, oracle=..., event=...)` -- a single expression
  (a 111 type-12 condition, or a 122 type-4 operand).

Both return an `EvalResult` and never raise `RubyRefusal` to the caller --
anything the evaluator can't model is caught at the top level and reported
as `EvalResult.refusal`, discarding any writes/effects the run produced
before the refusal (a refused run contributes nothing, CLAUDE.md §4.5: fail
loud, not partially).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from rpg2gba.ruby_subset import ast
from rpg2gba.ruby_subset import builtins as bi
from rpg2gba.story_state.state import (
    EngineKey,
    Key,
    SelfSwitch,
    Switch,
    TempSwitch,
    Variable,
)

__all__ = [
    "Symbol",
    "ConstRef",
    "InputSource",
    "Oracle",
    "FixedOracle",
    "RubyRefusal",
    "StateWrite",
    "Effect",
    "EvalResult",
    "evaluate_program",
    "evaluate_expression",
]

RESPAWN_MAP = EngineKey("respawn_map")

# RValue = int | float | bool | str | None | list | Symbol | ConstRef | _Opaque
# (documentation only -- Python has no useful runtime union to enforce here).


# --- values ---------------------------------------------------------------


@dataclass(frozen=True)
class Symbol:
    """A Ruby symbol literal (`:FISHERMAN`)."""

    name: str


@dataclass(frozen=True)
class ConstRef:
    """An opaque reference to a Ruby constant this evaluator doesn't (and
    doesn't need to) resolve to a number -- `PBSpecies::ORCHYNX` ->
    `ConstRef("PBSpecies", "ORCHYNX")`, a bare unscoped constant like
    `PROFREWARDS` -> `ConstRef(None, "PROFREWARDS")`. Equality is by
    (scope, name), so two evaluations of the same source produce equal,
    hashable values (needed for the determinism gate and for `Effect.args`
    to compare sanely)."""

    scope: str | None
    name: str


@dataclass(frozen=True)
class Opaque:
    """A constructed value with no further modelled meaning --
    `createPhoneTrainer(...)`/`get_character(...)`'s return. The evaluator
    never inspects it, only threads it through to wherever it's next used
    (e.g. as `customTrainerBattle`'s first argument)."""

    kind: str
    args: tuple


# --- oracle -----------------------------------------------------------


@dataclass(frozen=True)
class InputSource:
    """One nondeterministic input a run consulted. `kind` labels the family
    (`"battle_result"`, `"confirm"`, ...); `detail` is the call's own source
    head (`"customTrainerBattle"`); `domain` is every value the input can
    take, in source/semantic order -- `domain[0]` is the R10 "main path"
    outcome stage 3's enumerator tries first."""

    kind: str
    detail: str
    domain: tuple


@runtime_checkable
class Oracle(Protocol):
    """What a concrete run consults for anything not already known.
    `read` answers a game-state key read that isn't already tracked by this
    run (the key's "world" value); `choose` answers one nondeterministic
    input. Stage 3 implements this by enumeration; `FixedOracle` below is
    the stage-2 test double."""

    def read(self, key: Key) -> object: ...

    def choose(self, source: InputSource) -> object: ...


# Engine-held boolean unlock flags this evaluator knows about -- used only
# to pick a type-correct default for FixedOracle.read when the caller
# didn't supply one. Every other EngineKey this evaluator constructs
# (bag-quantity probes, `$game_player.x/y`) defaults to 0, an int, matching
# what they're compared against in the real corpus.
_BOOL_ENGINE_KEYS = frozenset(
    {attr.key_name for attr in bi.ENGINE_ATTRIBUTES.values()}
    | {"pokemonglobal_surfing"}
)


class FixedOracle:
    """Stage-2 test double: `reads` supplies concrete values for keys the
    run touches (default: switches/self-switches/temp-switches False,
    variables 0, engine flags False, anything else int 0); `choices` are
    consumed in source order, one per `choose()` call, raising once
    exhausted rather than guessing."""

    def __init__(
        self,
        reads: dict[Key, object] | None = None,
        choices: list[object] | None = None,
    ) -> None:
        self.reads: dict[Key, object] = dict(reads or {})
        self.choices: list[object] = list(choices or [])
        self._choice_index = 0

    def read(self, key: Key) -> object:
        if key in self.reads:
            return self.reads[key]
        if isinstance(key, Variable):
            return 0
        if isinstance(key, EngineKey):
            return False if key.name in _BOOL_ENGINE_KEYS else 0
        return False  # Switch / SelfSwitch / TempSwitch

    def choose(self, source: InputSource) -> object:
        if self._choice_index >= len(self.choices):
            raise IndexError(
                f"FixedOracle: no more choices queued (wanted one for {source!r}, "
                f"{len(self.choices)} supplied, {self._choice_index} already consumed)"
            )
        value = self.choices[self._choice_index]
        self._choice_index += 1
        return value


# --- refusal ----------------------------------------------------------


class RubyRefusal(Exception):
    """A run this evaluator can't model. Caught at the top level of
    `evaluate_program`/`evaluate_expression` and turned into
    `EvalResult.refusal` -- never escapes to the caller. Codes:
    `ruby_unknown_call:<name>`, `ruby_unknown_attribute:<receiver>.<name>`,
    `party_model`, `no_port:<name>`, `ruby_type_error:<detail>`,
    `ruby_unsupported_node:<NodeClass>`."""

    def __init__(self, family: str, detail: str, span: tuple[int, int] = (0, 0)) -> None:
        # `family` is the bare code ("ruby_type_error", "party_model", ...)
        # at every call site; `self.code` is the full dotted-detail code the
        # brief specifies (`ruby_type_error:<detail>`, `no_port:<name>`,
        # ...) -- built here once so call sites never hand-format it and
        # never risk drifting from this format. `party_model` (and anything
        # a caller already fully formed with its own ":") passes through
        # unchanged.
        self.code = family if ":" in family or family == "party_model" else f"{family}:{detail}"
        self.detail = detail
        self.span = span
        super().__init__(f"{self.code}: {detail}")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RubyRefusal):
            return NotImplemented
        return (self.code, self.detail, self.span) == (other.code, other.detail, other.span)

    def __hash__(self) -> int:
        return hash((self.code, self.detail, self.span))


# --- results ------------------------------------------------------------


@dataclass(frozen=True)
class StateWrite:
    key: Key
    value: object


@dataclass(frozen=True)
class Effect:
    name: str
    args: tuple
    span: tuple[int, int]


@dataclass(frozen=True)
class EvalResult:
    writes: tuple[StateWrite, ...]
    effects: tuple[Effect, ...]
    refusal: RubyRefusal | None


def _export(value: object) -> object:
    """Lists get reference semantics during a run (`pbGet` returns the live
    stored object) but must come out as hashable, comparable tuples in the
    final result."""
    if isinstance(value, list):
        return tuple(_export(v) for v in value)
    return value


def _write_sort_key(write: StateWrite) -> tuple:
    key = write.key
    return (type(key).__name__, dataclasses.astuple(key))


# --- jump signals (return/break/next) --------------------------------


class _JumpSignal(Exception):
    def __init__(self, value: object) -> None:
        self.value = value


class _ReturnSignal(_JumpSignal):
    pass


class _BreakSignal(_JumpSignal):
    pass


class _NextSignal(_JumpSignal):
    pass


# --- interpreter state ------------------------------------------------


class _Interp:
    def __init__(
        self,
        oracle: Oracle,
        event: tuple[int, int] | None,
        locals_in: dict[str, object] | None,
    ) -> None:
        self.oracle = oracle
        self.event = event
        self.locals: dict[str, object] = dict(locals_in or {})
        self._state: dict[Key, object] = {}
        self._initial: dict[Key, object] = {}
        self._explicit: set[Key] = set()
        self.effects: list[Effect] = []

    def _touch(self, key: Key) -> None:
        if key not in self._state:
            value = self.oracle.read(key)
            self._state[key] = value
            # `_export` recursively turns any list into a tuple, which is
            # itself a deep, immutable snapshot -- no separate copy needed.
            self._initial[key] = _export(value)

    def get_key(self, key: Key) -> object:
        self._touch(key)
        return self._state[key]

    def set_key(self, key: Key, value: object) -> None:
        # A plain assignment is not a read: the oracle is not consulted, so a
        # write-only key never becomes an out-of-scope read for the search.
        # An explicitly assigned key is always reported, so it needs no
        # initial snapshot.
        self._state[key] = value
        self._explicit.add(key)

    def writes(self) -> tuple[StateWrite, ...]:
        out: list[StateWrite] = []
        for key, final in self._state.items():
            final_x = _export(final)
            # Only keys first reached through a read have a snapshot; a key
            # mutated in place (`pbGet(151)[i] += 1`) was read first.
            changed = key in self._initial and final_x != self._initial[key]
            if changed or key in self._explicit:
                out.append(StateWrite(key, final_x))
        out.sort(key=_write_sort_key)
        return tuple(out)


# --- entry points -------------------------------------------------------


def evaluate_program(
    program: ast.Program,
    *,
    oracle: Oracle,
    event: tuple[int, int] | None,
    locals_in: dict[str, object] | None = None,
) -> EvalResult:
    interp = _Interp(oracle, event, locals_in)
    try:
        _exec_body(interp, program.statements)
    except _ReturnSignal:
        pass
    except _JumpSignal:
        return EvalResult(
            (), (),
            RubyRefusal("ruby_unsupported_node", "break/next outside a loop", program.span),
        )
    except RubyRefusal as refusal:
        return EvalResult((), (), refusal)
    return EvalResult(interp.writes(), tuple(interp.effects), None)


def evaluate_expression(
    node: ast.Node,
    *,
    oracle: Oracle,
    event: tuple[int, int] | None,
) -> tuple[object, EvalResult]:
    interp = _Interp(oracle, event, None)
    try:
        value = _eval(interp, node)
    except _JumpSignal:
        return None, EvalResult(
            (), (),
            RubyRefusal("ruby_unsupported_node", "return/break/next in an expression", node.span),
        )
    except RubyRefusal as refusal:
        return None, EvalResult((), (), refusal)
    return value, EvalResult(interp.writes(), tuple(interp.effects), None)


# --- statement execution ------------------------------------------------


def _exec_body(interp: _Interp, statements: tuple[ast.Node, ...]) -> None:
    for stmt in statements:
        _exec_stmt(interp, stmt)


def _exec_stmt(interp: _Interp, node: ast.Node) -> None:
    if isinstance(node, ast.If):
        _exec_if(interp, node)
    elif isinstance(node, ast.Unless):
        _exec_unless(interp, node)
    elif isinstance(node, ast.For):
        _exec_for(interp, node)
    elif isinstance(node, ast.While):
        _exec_while(interp, node)
    elif isinstance(node, ast.Return):
        raise _ReturnSignal(_eval(interp, node.value) if node.value is not None else None)
    elif isinstance(node, ast.Break):
        raise _BreakSignal(_eval(interp, node.value) if node.value is not None else None)
    elif isinstance(node, ast.Next):
        raise _NextSignal(_eval(interp, node.value) if node.value is not None else None)
    else:
        _eval(interp, node)  # expression statement; value discarded


def _exec_if(interp: _Interp, node: ast.If) -> None:
    if _truthy(_eval(interp, node.cond)):
        _exec_body(interp, node.then_body)
        return
    for econd, ebody in node.elifs:
        if _truthy(_eval(interp, econd)):
            _exec_body(interp, ebody)
            return
    if node.else_body is not None:
        _exec_body(interp, node.else_body)


def _exec_unless(interp: _Interp, node: ast.Unless) -> None:
    if not _truthy(_eval(interp, node.cond)):
        _exec_body(interp, node.then_body)
    elif node.else_body is not None:
        _exec_body(interp, node.else_body)


def _is_nuzlocke_party_loop(node: ast.For) -> bool:
    """`for i in $Trainer.party \\n i.nuzlocke_heal \\n end` -- Uranium's
    Nuzlocke override aliases the original `heal` as `nuzlocke_heal`
    (`reference/scripts_dump/220_Custom_Mode.rb:214-222`), always followed
    by a code-314 Recover All. With no Nuzlocke mode in this port
    (STATIC_PREDICATE_ATTRS: nuzlocke is always False) the alias is just
    `heal`, i.e. a no-op here -- the real healing is the sibling 314
    command, outside this block's own text. This is the ONE exception to
    "`$Trainer.party` always refuses party_model" (C8 design (7)): matched
    structurally, not just by a `.party` receiver, so any other loop body
    over the party still refuses normally."""
    iterable = node.iterable
    if not (
        isinstance(iterable, ast.Call)
        and iterable.receiver is not None
        and isinstance(iterable.receiver, ast.GlobalVar)
        and iterable.receiver.name == "$Trainer"
        and iterable.name == "party"
        and not iterable.args
    ):
        return False
    if len(node.body) != 1:
        return False
    (stmt,) = node.body
    return (
        isinstance(stmt, ast.Call)
        and stmt.receiver is not None
        and isinstance(stmt.receiver, ast.Local)
        and stmt.receiver.name == node.var
        and stmt.name == "nuzlocke_heal"
        and not stmt.args
    )


def _exec_for(interp: _Interp, node: ast.For) -> None:
    if _is_nuzlocke_party_loop(node):
        interp.effects.append(Effect("nuzlocke_heal_party", (), node.span))
        return
    iterable = _eval(interp, node.iterable)
    items = _iterable_values(iterable, node.span)
    for item in items:
        interp.locals[node.var] = item
        try:
            _exec_body(interp, node.body)
        except _NextSignal:
            continue
        except _BreakSignal:
            break


_MAX_WHILE_ITERATIONS = 100_000


def _exec_while(interp: _Interp, node: ast.While) -> None:
    count = 0
    while _truthy(_eval(interp, node.cond)):
        count += 1
        if count > _MAX_WHILE_ITERATIONS:
            raise RubyRefusal("ruby_type_error", "while loop exceeded iteration cap", node.span)
        try:
            _exec_body(interp, node.body)
        except _NextSignal:
            continue
        except _BreakSignal:
            break


def _iterable_values(value: object, span: tuple[int, int]) -> list:
    if isinstance(value, range):
        return list(value)
    if isinstance(value, list):
        return list(value)
    raise RubyRefusal("ruby_type_error", f"not iterable: {value!r}", span)


# --- expression evaluation ------------------------------------------------


def _eval(interp: _Interp, node: ast.Node) -> object:
    if isinstance(node, ast.Int):
        return node.value
    if isinstance(node, ast.Float):
        return node.value
    if isinstance(node, ast.Bool):
        return node.value
    if isinstance(node, ast.Nil):
        return None
    if isinstance(node, ast.Str):
        if node.interpolated or node.value is None:
            raise RubyRefusal("ruby_type_error", "interpolated string literal", node.span)
        return node.value
    if isinstance(node, ast.Sym):
        return Symbol(node.name)
    if isinstance(node, ast.ArrayLit):
        return [_eval(interp, e) for e in node.elements]
    if isinstance(node, ast.HashLit):
        return {_eval(interp, k): _eval(interp, v) for k, v in node.pairs}
    if isinstance(node, ast.RangeLit):
        return _eval_range(interp, node)
    if isinstance(node, ast.Local):
        if node.name not in interp.locals:
            raise RubyRefusal("ruby_type_error", f"read of unset local {node.name!r}", node.span)
        return interp.locals[node.name]
    if isinstance(node, ast.GlobalVar):
        if node.name in bi.STATIC_GLOBALS:
            return bi.STATIC_GLOBALS[node.name]
        raise RubyRefusal("ruby_unknown_attribute", f"bare {node.name}", node.span)
    if isinstance(node, ast.InstanceVar):
        raise RubyRefusal("ruby_unsupported_node", "InstanceVar", node.span)
    if isinstance(node, ast.Const):
        return bi.CONST_VALUES.get(node.name, ConstRef(None, node.name))
    if isinstance(node, ast.ScopedConst):
        if not isinstance(node.scope, ast.Const):
            raise RubyRefusal("ruby_type_error", "non-constant scope in ::", node.span)
        return ConstRef(node.scope.name, node.name)
    if isinstance(node, ast.UnaryOp):
        return _eval_unary(interp, node)
    if isinstance(node, ast.BinOp):
        return _eval_binop(interp, node)
    if isinstance(node, ast.Ternary):
        return _eval(interp, node.then) if _truthy(_eval(interp, node.cond)) else _eval(interp, node.else_)
    if isinstance(node, ast.Index):
        return _eval_index_get(interp, node)
    if isinstance(node, ast.Call):
        return _eval_call(interp, node)
    if isinstance(node, ast.Assign):
        value = _eval(interp, node.value)
        _assign_to(interp, node.target, value, node.span)
        return value
    if isinstance(node, ast.OpAssign):
        current = _eval(interp, node.target)
        rhs = _eval(interp, node.value)
        new_value = _ruby_arith(node.op, current, rhs, node.span)
        _assign_to(interp, node.target, new_value, node.span)
        return new_value
    raise RubyRefusal("ruby_unsupported_node", type(node).__name__, node.span)


def _eval_range(interp: _Interp, node: ast.RangeLit) -> range:
    lo = _eval(interp, node.lo)
    hi = _eval(interp, node.hi)
    if not _is_int(lo) or not _is_int(hi):
        raise RubyRefusal("ruby_type_error", f"non-integer range {lo!r}..{hi!r}", node.span)
    return range(lo, hi if node.exclusive else hi + 1)


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _truthy(v: object) -> bool:
    return v is not None and v is not False


def _eval_unary(interp: _Interp, node: ast.UnaryOp) -> object:
    v = _eval(interp, node.operand)
    if node.op == "!":
        return not _truthy(v)
    if node.op == "-":
        if not _is_num(v):
            raise RubyRefusal("ruby_type_error", f"unary - on non-numeric {v!r}", node.span)
        return -v
    raise RubyRefusal("ruby_unsupported_node", f"UnaryOp {node.op!r}", node.span)


def _ruby_eq(left: object, right: object) -> bool:
    # Ruby: an Integer/Float is never == a boolean, regardless of value
    # (0 == false is false). Python's bool-is-an-int means `0 == False` is
    # True, so this has to be checked explicitly rather than falling
    # through to Python's own `==`.
    if isinstance(left, bool) != isinstance(right, bool):
        other = right if isinstance(left, bool) else left
        if isinstance(other, (int, float)):
            return False
    try:
        return bool(left == right)
    except TypeError:
        return False


def _ruby_cmp(op: str, left: object, right: object, span: tuple[int, int]) -> object:
    if not (_is_num(left) and _is_num(right)):
        raise RubyRefusal("ruby_type_error", f"comparison on non-numeric {left!r} {op} {right!r}", span)
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<=>":
        return -1 if left < right else (1 if left > right else 0)
    raise RubyRefusal("ruby_unsupported_node", f"cmp op {op!r}", span)


def _ruby_arith(op: str, left: object, right: object, span: tuple[int, int]) -> object:
    if op == "+" and isinstance(left, str) and isinstance(right, str):
        return left + right
    if not (_is_num(left) and _is_num(right)):
        raise RubyRefusal("ruby_type_error", f"arithmetic on non-numeric {left!r} {op} {right!r}", span)
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        if right == 0:
            raise RubyRefusal("ruby_type_error", "division by zero", span)
        if isinstance(left, int) and isinstance(right, int):
            return left // right  # Ruby Integer#/ floors toward -infinity, same as Python //
        return left / right
    if op == "%":
        return left % right  # Ruby Integer#% and Python % both floor-mod
    raise RubyRefusal("ruby_unsupported_node", f"arith op {op!r}", span)


def _eval_binop(interp: _Interp, node: ast.BinOp) -> object:
    op = node.op
    if op == "&&":
        left = _eval(interp, node.left)
        return _eval(interp, node.right) if _truthy(left) else left
    if op == "||":
        left = _eval(interp, node.left)
        return left if _truthy(left) else _eval(interp, node.right)
    left = _eval(interp, node.left)
    right = _eval(interp, node.right)
    if op == "==":
        return _ruby_eq(left, right)
    if op == "!=":
        return not _ruby_eq(left, right)
    if op in ("<", "<=", ">", ">=", "<=>"):
        return _ruby_cmp(op, left, right, node.span)
    if op in ("+", "-", "*", "/", "%"):
        return _ruby_arith(op, left, right, node.span)
    raise RubyRefusal("ruby_unsupported_node", f"BinOp {op!r}", node.span)


# --- $game_switches/$game_variables/$game_self_switches[...] -------------


def _resolve_state_key(
    interp: _Interp, receiver: ast.Node, args: tuple[ast.Node, ...], span: tuple[int, int],
) -> Key | None:
    if not isinstance(receiver, ast.GlobalVar):
        return None
    if receiver.name == "$game_switches":
        if len(args) != 1:
            raise RubyRefusal("ruby_type_error", "$game_switches[] arity", span)
        n = _eval(interp, args[0])
        if not _is_int(n):
            raise RubyRefusal("ruby_type_error", f"$game_switches[] non-int index {n!r}", span)
        return Switch(n)
    if receiver.name == "$game_variables":
        if len(args) != 1:
            raise RubyRefusal("ruby_type_error", "$game_variables[] arity", span)
        n = _eval(interp, args[0])
        if not _is_int(n):
            raise RubyRefusal("ruby_type_error", f"$game_variables[] non-int index {n!r}", span)
        return Variable(n)
    if receiver.name == "$game_self_switches":
        if len(args) != 1:
            raise RubyRefusal("ruby_type_error", "$game_self_switches[] arity", span)
        triple = _eval(interp, args[0])
        if not (isinstance(triple, list) and len(triple) == 3):
            raise RubyRefusal("ruby_type_error", "$game_self_switches[[map,ev,letter]] shape", span)
        m, e, letter = triple
        return SelfSwitch(m, e, letter)
    return None


def _eval_index_get(interp: _Interp, node: ast.Index) -> object:
    key = _resolve_state_key(interp, node.receiver, node.args, node.span)
    if key is not None:
        return interp.get_key(key)
    recv = _eval(interp, node.receiver)
    if isinstance(recv, ConstRef) and recv.scope is None and recv.name == "PROFREWARDS":
        # `PROFREWARDS[$game_variables[22]+1][0]` (213_Bambo_Reward.rb) --
        # the same reward-tier ladder jvGiveReward/jvNextReward read, just
        # inlined instead of called through the method (real corpus,
        # map###/ev009-family blocks). Same bucket as those two
        # (PARTY_MODEL_CALLS): the ladder is gated on
        # `$Trainer.pokedexOwned`, an explicitly party_model attribute.
        raise RubyRefusal("party_model", "PROFREWARDS[...]", node.span)
    if len(node.args) != 1:
        raise RubyRefusal("ruby_type_error", "multi-arg index on a non-state receiver", node.span)
    idx = _eval(interp, node.args[0])
    if isinstance(recv, list):
        if not _is_int(idx):
            raise RubyRefusal("ruby_type_error", f"list index not an int: {idx!r}", node.span)
        if -len(recv) <= idx < len(recv):
            return recv[idx]
        return None  # Ruby: an out-of-range array read is nil, not an error
    if isinstance(recv, dict):
        return recv.get(idx)
    raise RubyRefusal("ruby_type_error", f"index on non-indexable {recv!r}", node.span)


def _assign_to(interp: _Interp, target: ast.Node, value: object, span: tuple[int, int]) -> None:
    if isinstance(target, ast.Local):
        interp.locals[target.name] = value
        return
    if isinstance(target, ast.Index):
        key = _resolve_state_key(interp, target.receiver, target.args, span)
        if key is not None:
            if isinstance(key, Switch) and not isinstance(value, bool):
                raise RubyRefusal("ruby_type_error", f"$game_switches[] assigned non-bool {value!r}", span)
            interp.set_key(key, value)
            return
        recv = _eval(interp, target.receiver)
        if len(target.args) != 1:
            raise RubyRefusal("ruby_type_error", "multi-arg index assignment", span)
        idx = _eval(interp, target.args[0])
        if not isinstance(recv, list):
            raise RubyRefusal("ruby_type_error", f"index-assign on non-list {recv!r}", span)
        if not _is_int(idx):
            raise RubyRefusal("ruby_type_error", f"list index assign not an int: {idx!r}", span)
        while len(recv) <= idx:
            recv.append(None)
        recv[idx] = value
        return
    if isinstance(target, ast.GlobalVar):
        # A bare `$something = value` to an untracked global. The one
        # CH01-CH05 instance (`$lobbyreset`) lives only in strip-listed common
        # events 4/5/6, which callers never evaluate -- so reaching here is a
        # real gap, and it refuses (CLAUDE.md §4.5).
        raise RubyRefusal("ruby_unknown_attribute", f"bare {target.name} =", span)
    if isinstance(target, ast.Call):
        _assign_attribute(interp, target, value, span)
        return
    raise RubyRefusal("ruby_unsupported_node", f"assignment target {type(target).__name__}", span)


def _namespace_of(node: ast.Node) -> str | None:
    if isinstance(node, ast.GlobalVar) and node.name in bi.NAMESPACE_GLOBALS:
        return node.name
    if isinstance(node, ast.Const) and node.name in bi.NAMESPACE_CONSTS:
        return node.name
    return None


def _assign_attribute(interp: _Interp, target: ast.Call, value: object, span: tuple[int, int]) -> None:
    ns = _namespace_of(target.receiver)
    if ns is None:
        # A compound receiver like `$Trainer.party[i].nuclearFree=true` --
        # evaluate it generically so a party read surfaces its own
        # party_model refusal rather than this function inventing one.
        _eval(interp, target.receiver)
        raise RubyRefusal(
            "ruby_unknown_attribute", f"<{type(target.receiver).__name__}>.{target.name}", span,
        )
    key = (ns, target.name)
    if key in bi.PARTY_MODEL_ATTRS:
        raise RubyRefusal("party_model", f"{ns}.{target.name}", span)
    if key in bi.ENGINE_ATTRIBUTES:
        interp.set_key(EngineKey(bi.ENGINE_ATTRIBUTES[key].key_name), value)
        return
    if key in bi.NOOP_ATTRS:
        return
    if key in bi.PASSTHROUGH_ENGINE_ATTRS:
        interp.set_key(EngineKey(bi.PASSTHROUGH_ENGINE_ATTRS[key]), value)
        return
    raise RubyRefusal("ruby_unknown_attribute", f"{ns}.{target.name}", span)


# --- calls -----------------------------------------------------------


def _current_map(interp: _Interp, span: tuple[int, int]) -> int:
    if interp.event is None:
        raise RubyRefusal("ruby_type_error", "no event context for current map id", span)
    return interp.event[0]


def _temp_switch(interp: _Interp, letter: object, span: tuple[int, int]) -> TempSwitch:
    if not isinstance(letter, str):
        raise RubyRefusal("ruby_type_error", f"temp switch letter not a string: {letter!r}", span)
    if interp.event is None:
        raise RubyRefusal("ruby_type_error", "no event context for a temp switch", span)
    map_id, event_id = interp.event
    return TempSwitch(map_id, event_id, letter)


def _require_args(args: list, n: int, head: str, span: tuple[int, int]) -> None:
    if len(args) != n:
        raise RubyRefusal("ruby_type_error", f"{head} expected {n} arg(s), got {len(args)}", span)


def _key_repr(v: object) -> str:
    if isinstance(v, ConstRef):
        return f"{v.scope}.{v.name}" if v.scope else v.name
    return repr(v)


def _eval_call(interp: _Interp, node: ast.Call) -> object:
    if node.block is not None:
        raise RubyRefusal("ruby_unsupported_node", "block argument", node.span)
    if node.receiver is None:
        return _dispatch_head(interp, node.name, node.args, node.span, ns=None)
    if isinstance(node.receiver, ast.Const) and node.receiver.name == "Kernel":
        # `Kernel.` normalizes away, same as census._script_head -- the two
        # spellings are one head.
        return _dispatch_head(interp, node.name, node.args, node.span, ns=None)
    ns = _namespace_of(node.receiver)
    if ns is not None:
        return _dispatch_head(interp, node.name, node.args, node.span, ns=ns)
    recv = _eval(interp, node.receiver)
    return _eval_value_method(interp, recv, node)


def _dispatch_head(
    interp: _Interp, name: str, arg_nodes: tuple[ast.Node, ...], span: tuple[int, int], ns: str | None,
) -> object:
    head = name if ns is None else f"{ns}.{name}"

    if ns is not None and not arg_nodes:
        key = (ns, name)
        if key in bi.PARTY_MODEL_ATTRS:
            raise RubyRefusal("party_model", head, span)
        if key in bi.ENGINE_ATTRIBUTES:
            return interp.get_key(EngineKey(bi.ENGINE_ATTRIBUTES[key].key_name))
        if key in bi.STATIC_PREDICATE_ATTRS:
            return bi.STATIC_PREDICATE_ATTRS[key]
        if key in bi.NOOP_ATTRS:
            return None
        if key in bi.PASSTHROUGH_ENGINE_ATTRS:
            return interp.get_key(EngineKey(bi.PASSTHROUGH_ENGINE_ATTRS[key]))

    args = [_eval(interp, a) for a in arg_nodes]

    # -- category 1: state accessors with arguments ----------------------
    if head == "pbGet":
        _require_args(args, 1, head, span)
        if not _is_int(args[0]):
            raise RubyRefusal("ruby_type_error", f"pbGet non-int arg {args[0]!r}", span)
        return interp.get_key(Variable(args[0]))
    if head == "pbSet":
        _require_args(args, 2, head, span)
        if not _is_int(args[0]):
            raise RubyRefusal("ruby_type_error", f"pbSet non-int arg {args[0]!r}", span)
        interp.set_key(Variable(args[0]), args[1])
        return None
    if head == "pbSetSelfSwitch":
        _require_args(args, 3, head, span)
        event_id, letter, value = args
        if not _is_int(event_id):
            raise RubyRefusal("ruby_type_error", f"pbSetSelfSwitch non-int event id {event_id!r}", span)
        if not isinstance(letter, str):
            raise RubyRefusal("ruby_type_error", f"pbSetSelfSwitch non-str letter {letter!r}", span)
        if not isinstance(value, bool):
            raise RubyRefusal("ruby_type_error", f"pbSetSelfSwitch non-bool value {value!r}", span)
        interp.set_key(SelfSwitch(_current_map(interp, span), event_id, letter), value)
        return None
    if head == "setTempSwitchOn":
        _require_args(args, 1, head, span)
        interp.set_key(_temp_switch(interp, args[0], span), True)
        return None
    if head == "setTempSwitchOff":
        _require_args(args, 1, head, span)
        interp.set_key(_temp_switch(interp, args[0], span), False)
        return None
    if head == "tsOn?":
        _require_args(args, 1, head, span)
        return interp.get_key(_temp_switch(interp, args[0], span)) is True
    if head == "tsOff?":
        _require_args(args, 1, head, span)
        return interp.get_key(_temp_switch(interp, args[0], span)) is False
    if head == "pbSetPokemonCenter":
        # heal_locations._parse_call's own shape (story_state/extract.py):
        # bare call -> this row's own map; 4 literal int args -> args[0] is
        # the target map id. Reused by meaning, not by import (§4.3's
        # single-parser rule is about Ruby *parsing*; this is a game-shape
        # fact about one call, cheap to restate here for a concrete run).
        if not args:
            interp.set_key(RESPAWN_MAP, _current_map(interp, span))
        elif len(args) == 4 and all(_is_int(a) for a in args):
            interp.set_key(RESPAWN_MAP, args[0])
        else:
            raise RubyRefusal("ruby_type_error", f"pbSetPokemonCenter args {args!r}", span)
        return None

    # -- $game_map / $game_player / $PokemonBag calls with arguments -----
    if head == "$game_map.map_id":
        return _current_map(interp, span)
    if head in ("$game_player.x", "$game_player.y"):
        return interp.get_key(EngineKey("player_" + head.rsplit(".", 1)[1]))
    if head == "$PokemonBag.pbQuantity":
        _require_args(args, 1, head, span)
        return interp.get_key(EngineKey(f"bag_qty:{_key_repr(args[0])}"))

    if head == bi.RANDOM_SPECIES_CALL:
        value = interp.oracle.choose(InputSource(
            kind="random_species", detail=head, domain=(ConstRef("PBSpecies", "RANDOM"),),
        ))
        return value

    if head in bi.NO_PORT_CALLS:
        raise RubyRefusal("no_port", head, span)
    if head in bi.CONSTRUCTOR_CALLS:
        return Opaque(head, tuple(args))
    if head == "_I":
        return args[0] if args else ""
    if head in bi.PARTY_MODEL_CALLS:
        raise RubyRefusal("party_model", head, span)
    if head in bi.STATIC_FALSE_CALLS:
        if head in bi.EFFECT_CALLS:
            interp.effects.append(Effect(head, tuple(args), span))
        return False
    if head in bi.STATIC_ZERO_CALLS:
        if head in bi.EFFECT_CALLS:
            interp.effects.append(Effect(head, tuple(args), span))
        return 0
    if head in bi.INPUT_CALLS:
        spec = bi.INPUT_CALLS[head]
        value = interp.oracle.choose(InputSource(kind=spec.kind, detail=head, domain=spec.domain))
        if head in bi.EFFECT_CALLS:
            interp.effects.append(Effect(head, tuple(args), span))
        return value
    if head in bi.EFFECT_CALLS:
        interp.effects.append(Effect(head, tuple(args), span))
        return None

    raise RubyRefusal("ruby_unknown_call", head, span)


def _eval_value_method(interp: _Interp, recv: object, node: ast.Call) -> object:
    # Array#index/max/length and a narrow is_a? -- the only value-level
    # methods the CH01-CH05 corpus actually calls (Bambo's starter tally
    # and one defensive `pbGet(1).is_a?(Numeric)` guard).
    name = node.name
    args = [_eval(interp, a) for a in node.args]

    if name == "onEvent?":
        # `get_character(N).onEvent?` -- Game_Event#onEvent?
        # (022_Game_Event_v17.rb:117) compares the character's position to
        # $game_player's: a player-position read, both arms player input
        # (chapter_manifest/conditions.py get_character_on_event family --
        # the single most common condition shape in the corpus). Not
        # modelled as a story-state key (no PlayerPosition Key exists), so
        # it's an input, not a read.
        return interp.oracle.choose(InputSource(
            kind="player_position", detail="onEvent?", domain=(True, False),
        ))
    if name == "index":
        _require_args(args, 1, "index", node.span)
        if not isinstance(recv, list):
            raise RubyRefusal("ruby_type_error", f"index on non-array {recv!r}", node.span)
        target = args[0]
        for i, v in enumerate(recv):
            if _ruby_eq(v, target):
                return i
        return None
    if name == "max":
        if not isinstance(recv, list):
            raise RubyRefusal("ruby_type_error", f"max on non-array {recv!r}", node.span)
        if not recv:
            return None
        return max(recv)
    if name == "length":
        if not isinstance(recv, (list, str)):
            raise RubyRefusal("ruby_type_error", f"length on non-array {recv!r}", node.span)
        return len(recv)
    if name == "is_a?":
        _require_args(args, 1, "is_a?", node.span)
        cls = args[0]
        cls_name = cls.name if isinstance(cls, ConstRef) and cls.scope is None else None
        if cls_name == "Numeric":
            return _is_num(recv)
        if cls_name == "Integer":
            return _is_int(recv)
        if cls_name == "Float":
            return isinstance(recv, float)
        if cls_name == "String":
            return isinstance(recv, str)
        if cls_name == "Symbol":
            return isinstance(recv, Symbol)
        raise RubyRefusal("ruby_unknown_attribute", f"is_a?({cls!r})", node.span)
    raise RubyRefusal("ruby_unknown_attribute", f"<{type(recv).__name__}>.{name}", node.span)
