"""Row-scope input search (REDERIVATION_PLAN.md C8 stage 3 design, "Stages
3-4 refined").

`search_scope` runs ONE manifest row's own flattened command list
(`_flatten_scope`, the same one `story_state.extract` and
`chapter_manifest.generator.iter_page_scopes` use -- CLAUDE.md §4.3, one row
grammar) concretely, over EVERY combination of its inputs (text `\\ch`
choices, 122 random ranges, `ruby_subset.evaluate` `InputSource`s reached
through a 355/655 block) and every out-of-scope read (a switch/variable/
self-switch/temp-switch/engine key this row consults but never itself
writes first), capped at `cap` completed runs. Report per-key written value
sets, a first-DFS-order witness per `(key, value)`, and the distinct effect
sequences observed.

Enumeration is depth-first, replaying a recorded choice-prefix from the top
of the scope each time a run reaches a choice point beyond the prefix (the
brief's own name for this: "standard replay-DFS") -- see `_Frontier`/
`_run_once`/`search_scope` below. This is quadratic-ish in the number of
choice points (each new prefix element re-executes the whole scope from the
start), but real rows have at most a handful of choice points and the whole
search is capped, so the simplicity is worth it over a real coroutine-based
suspend/resume.

A refusal anywhere refuses the WHOLE search (CLAUDE.md §4.5: a row can't be
half-modelled) -- `SearchResult.refusal` is populated and every other field
is empty/zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from rpg2gba.conversion_agent.deterministic import join_text_lines
from rpg2gba.conversion_agent.inline_choice import (
    InlineChoiceError,
    has_inline_choice,
    parse_inline_choice,
)
from rpg2gba.ruby_subset.evaluate import (
    Effect as RubyEffect,
    InputSource,
    evaluate_program,
)
from rpg2gba.ruby_subset import ast
from rpg2gba.ruby_subset.lexer import RubyParseError
from rpg2gba.ruby_subset.parser import parse_program, script_block_source
from rpg2gba.story_state.state import (
    Key,
    Refusal,
    SelfSwitch,
    Switch,
    TempSwitch,
    Variable,
)

__all__ = [
    "Choice",
    "Effect",
    "SearchResult",
    "search_scope",
    "load_stripped_ce_ids",
]

# --- RMXP command codes (kept local -- see chapter_manifest.generator's own
# local-constant note for why these aren't re-derived from a shared enum:
# the corpus has no single canonical command-code module). --------------
CODE_SHOW_TEXT = 101
CODE_SHOW_TEXT_CONT = 401
CODE_SWITCH_WRITE = 121
CODE_VAR_WRITE = 122
CODE_SELF_SWITCH_WRITE = 123
CODE_COMMON_EVENT_CALL = 117
CODE_SCRIPT = 355
CODE_SCRIPT_CONT = 655
CODE_LOOP = 112

# The closer codes `_flatten_scope` (chapter_manifest/generator.py) never
# emits into a scope's own flattened command list -- `parse_tree` consumes
# them silently while walking a branch/choice/loop body, so they never
# become any `Node.cmd`. A genuine invariant, asserted below. `111`
# (CONDITIONAL_BRANCH) and `102` (SHOW_CHOICES) themselves DO legitimately
# appear -- a scope that directly contains a nested branch/choice owns that
# construct's OPENER command (its arm bodies are separate rows,
# `_flatten_scope`'s own docstring) -- e.g. the real corpus row
# `map050/ev019/p0` has its own code-111 opener sitting right in its
# flattened commands, followed by sibling content. `story_state.extract`
# treats that opener as a no-op leaf (falls through `_extract_leaf_writes`'s
# final `return (), (), frozenset(), False`); this module does the same, so
# a row that legitimately contains a nested branch opener is search-able,
# not an assertion failure.
_NEVER_FLATTENED_CODES = frozenset({402, 403, 404, 411, 412})

_VAR_OP_SYMBOLS: dict[int, str] = {1: "+", 2: "-", 3: "*", 4: "/", 5: "%"}

# Codes whose direct presence in a loop body counts as "state-writing"
# (C8 design refined, ruling C1: loops stay in the enclosing scope; a body
# with none of these is ignored entirely, one with any of them refuses
# `search_loop`). `117` errs conservative -- a common-event call MIGHT write
# state, and this module doesn't try to look inside it just to rule that
# out.
_LOOP_STATE_WRITING_CODES = frozenset({
    CODE_SWITCH_WRITE, CODE_VAR_WRITE, CODE_SELF_SWITCH_WRITE,
    CODE_SCRIPT, CODE_COMMON_EVENT_CALL,
})

# A common event "has branching commands" if its own raw list contains any
# of these -- the 111/102 openers plus every code their bodies could only be
# entered/exited through.
_CE_BRANCHING_CODES = frozenset({111, 102, 112, 402, 403, 404, 411, 412})


# --- results --------------------------------------------------------------


@dataclass(frozen=True)
class Choice:
    """One decided choice point in a run's trace, in the order it was
    decided. `point` is a stable, human-readable label (`"read
    Variable(151)"`, `"\\ch var 2 @list[7]"`, `"battle_result
    customTrainerBattle @list[3]"`, `"random var 5 @list[9]"`)."""

    point: str
    value: object


@dataclass(frozen=True)
class Effect:
    name: str
    args: tuple
    list_index: int


@dataclass(frozen=True)
class SearchResult:
    runs: int
    values: dict[Key, frozenset]
    always_written: frozenset[Key]
    # Per key, the LAST position in the scope at which any run wrote it --
    # the page-list index when the caller supplied `index_of`, otherwise the
    # flattened-scope offset. This is what `story_state.state.Assign`'s
    # `list_index` is specified against; the max over runs is taken because
    # a key written on several paths is ordered by the latest of them.
    write_index: dict[Key, int]
    witnesses: dict[tuple[Key, object], tuple[Choice, ...]]
    effects: tuple[tuple[Effect, ...], ...]
    reads: frozenset[Key]
    inputs: bool
    refusal: Refusal | None
    # Keys a graphics-only party read left unknown (`_graphics_party_write`):
    # the caller havocs them rather than refusing the row.
    havoc: frozenset[Key] = frozenset()


def _empty_result(refusal: Refusal) -> SearchResult:
    return SearchResult(
        runs=0, values={}, always_written=frozenset(), write_index={}, witnesses={},
        effects=(), reads=frozenset(), inputs=False, refusal=refusal,
    )


# --- strip-list loading (CLAUDE.md §4.3: reuse the existing loader) -------


def load_stripped_ce_ids(reference_dir: Path) -> frozenset[int]:
    """Common-event ids strip-listed whole (`reference/strip_list.json`'s
    `common_events`) -- a `117` call to one of these is a no-op, same as
    the transpiler/orchestrator's own strip enforcement. Reuses
    `conversion_agent.orchestrator._load_strip_list` rather than
    re-reading the file."""
    from rpg2gba.conversion_agent.orchestrator import _load_strip_list

    ces, _ = _load_strip_list(reference_dir)
    return frozenset(ces.keys())


# --- internal control-flow signals ----------------------------------------


class _Frontier(Exception):
    """Raised when a run's choice-prefix runs out: `point`/`domain` describe
    the choice `search_scope`'s driver must now branch over."""

    def __init__(self, point: str, domain: tuple) -> None:
        self.point = point
        self.domain = domain


class _Aborted(Exception):
    """Raised when this run cannot be modelled at all -- refuses the WHOLE
    search (CLAUDE.md §4.5)."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail


class _CapExceeded(Exception):
    pass


# --- one run's engine -------------------------------------------------


class _RunEngine:
    """Drives one concrete execution of a scope, replaying `prefix` for
    every choice point already decided and raising `_Frontier` the moment
    it needs a choice beyond the prefix."""

    def __init__(
        self,
        prefix: tuple,
        *,
        map_id: int,
        event_id: int,
        common_events_by_id: dict[int, dict[str, Any]],
        stripped_ce_ids: frozenset[int],
        read_domain: Callable[[Key], "frozenset | None"],
        index_of: dict[int, int] | None = None,
        graphics_only_vars: frozenset[int] = frozenset(),
    ) -> None:
        self.prefix = prefix
        self.graphics_only_vars = graphics_only_vars
        self.havoc: set[Key] = set()
        self._next = 0
        self.world: dict[Key, object] = {}
        self.explicit: set[Key] = set()
        # The command position every `set_key` below is attributed to -- set
        # by `_exec_commands` before it dispatches each command, so the write
        # primitives don't each have to thread an index through.
        self.current_index = -1
        self.write_index: dict[Key, int] = {}
        self.index_of = index_of or {}
        self.read_keys: set[Key] = set()
        self.trace: list[Choice] = []
        self.effects: list[Effect] = []
        self.has_input = False
        self.map_id = map_id
        self.event_id = event_id
        self.common_events_by_id = common_events_by_id
        self.stripped_ce_ids = stripped_ce_ids
        self.read_domain = read_domain

    # -- the one choice primitive -----------------------------------------

    def _decide(self, point: str, domain: tuple) -> object:
        if not domain:
            raise _Aborted("search_empty_domain", point)
        if self._next >= len(self.prefix):
            raise _Frontier(point, domain)
        value = self.prefix[self._next]
        self._next += 1
        self.trace.append(Choice(point, value))
        return value

    # -- world access -------------------------------------------------------

    def get_key(self, key: Key) -> object:
        if key in self.world:
            return self.world[key]
        domain = self.read_domain(key)
        if domain is None:
            raise _Aborted("search_unknown_read", repr(key))
        value = self._decide(f"read {key!r}", tuple(sorted(domain)))
        self.world[key] = value
        self.read_keys.add(key)
        return value

    def set_key(self, key: Key, value: object) -> None:
        self.world[key] = value
        self.explicit.add(key)
        # Last writer within one run wins, matching `Assign.list_index`'s
        # "where this row's execution places the write".
        self.write_index[key] = self.current_index

    # -- evaluate.Oracle adapter for one 355/655 block ---------------------

    def oracle_for(self, list_index: int) -> "_EvalOracleAdapter":
        return _EvalOracleAdapter(self, list_index)


@dataclass
class _EvalOracleAdapter:
    """Satisfies `ruby_subset.evaluate.Oracle` for one script block's run,
    routing every read/choice through the enclosing `_RunEngine`."""

    engine: _RunEngine
    list_index: int

    def read(self, key: Key) -> object:
        value = self.engine.get_key(key)
        if isinstance(value, tuple):
            # `engine.world` stores an ARRAY-valued key as the exported,
            # hashable tuple (needed for `SearchResult.values`/`witnesses`);
            # `evaluate.py` needs a genuinely mutable list to give Ruby's
            # array reference semantics (`pbGet(151)[pbGet(2)] += 1`) --
            # hand back a fresh copy so evaluate.py's own in-place mutation
            # never corrupts the engine's cached tuple. The block's own
            # `EvalResult.writes` re-exports the mutated list back to a
            # tuple, which `_exec_script` applies to `engine.world`.
            return list(value)
        return value

    def choose(self, source: InputSource) -> object:
        label = f"{source.kind} {source.detail} @list[{self.list_index}]"
        return self.engine._decide(label, tuple(source.domain))


# --- command dispatch ----------------------------------------------------


def _text_of(commands: list[dict[str, Any]], start: int) -> tuple[str, int]:
    """Join a code-101 Show Text with its 401 continuations, same joining
    (`join_text_lines`) `transpiler.parse_tree` uses for a `TextRun`."""
    cmd = commands[start]
    params = cmd.get("parameters") or [""]
    parts = [str(params[0]) if params else ""]
    i = start + 1
    while i < len(commands) and commands[i].get("code") == CODE_SHOW_TEXT_CONT:
        p = commands[i].get("parameters") or [""]
        parts.append(str(p[0]) if p else "")
        i += 1
    return join_text_lines(parts), i


def _freeze(value: object) -> object:
    """`evaluate.py`'s `Effect.args` are NOT run through its own `_export`
    (only `StateWrite` values are) -- an array-literal argument
    (`pbPokemonMart([...])`) arrives as a genuine Python `list`, unhashable.
    `SearchResult.effects` needs every effect sequence hashable/comparable
    (it's a `set` element and gets sorted), so freeze recursively here."""
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((_freeze(k), _freeze(v)) for k, v in value.items()))
    return value


def _apply_var_op(op: int, current: object, rhs: object, point: str) -> int:
    if not isinstance(current, int) or isinstance(current, bool):
        raise _Aborted("search_type_error", f"{point}: non-int current value {current!r}")
    if not isinstance(rhs, int) or isinstance(rhs, bool):
        raise _Aborted("search_type_error", f"{point}: non-int operand {rhs!r}")
    if op == 2:
        return current - rhs
    if op == 3:
        return current * rhs
    if op == 4:
        if rhs == 0:
            raise _Aborted("search_type_error", f"{point}: division by zero")
        return current // rhs
    if op == 5:
        if rhs == 0:
            raise _Aborted("search_type_error", f"{point}: modulo by zero")
        return current % rhs
    return current + rhs  # op == 1


def _exec_121(engine: _RunEngine, cmd: dict, idx: int) -> None:
    params = cmd.get("parameters") or []
    if len(params) < 3:
        raise _Aborted("search_malformed_write", f"code 121 @list[{idx}]: too few params")
    lo, hi, value = params[0], params[1], params[2]
    on = value == 0
    for sid in range(lo, hi + 1):
        engine.set_key(Switch(sid), on)


def _exec_122(engine: _RunEngine, cmd: dict, idx: int) -> None:
    params = cmd.get("parameters") or []
    if len(params) < 5:
        raise _Aborted("search_malformed_write", f"code 122 @list[{idx}]: too few params")
    lo, hi, op, operand_kind, operand = params[0], params[1], params[2], params[3], params[4]
    point = f"code 122 @list[{idx}]"

    if operand_kind == 0:
        if not isinstance(operand, int) or isinstance(operand, bool):
            raise _Aborted("search_malformed_write", f"{point}: non-int constant operand {operand!r}")
        rhs: object = operand
    elif operand_kind == 1:
        if not isinstance(operand, int) or isinstance(operand, bool):
            raise _Aborted("search_malformed_write", f"{point}: non-int variable-operand id {operand!r}")
        rhs = engine.get_key(Variable(operand))
    elif operand_kind == 2:
        if len(params) < 6:
            raise _Aborted("search_malformed_write", f"{point}: random operand missing upper bound")
        rlo, rhi = operand, params[5]
        if not (isinstance(rlo, int) and isinstance(rhi, int) and rhi >= rlo):
            raise _Aborted("search_malformed_write", f"{point}: bad random bounds {rlo!r}/{rhi!r}")
        rhs = engine._decide(f"random var @list[{idx}]", tuple(range(rlo, rhi + 1)))
    else:
        raise _Aborted("search_malformed_write", f"{point}: unknown operand_kind {operand_kind!r}")

    if op not in (0, *_VAR_OP_SYMBOLS):
        raise _Aborted("search_malformed_write", f"{point}: unknown op {op!r}")

    for vid in range(lo, hi + 1):
        if op == 0:
            engine.set_key(Variable(vid), rhs)
        else:
            current = engine.get_key(Variable(vid))
            engine.set_key(Variable(vid), _apply_var_op(op, current, rhs, point))


def _exec_123(engine: _RunEngine, cmd: dict, idx: int) -> None:
    params = cmd.get("parameters") or []
    if len(params) < 2:
        raise _Aborted("search_malformed_write", f"code 123 @list[{idx}]: too few params")
    letter, value = params[0], params[1]
    engine.set_key(SelfSwitch(engine.map_id, engine.event_id, letter), value == 0)


def _exec_text(engine: _RunEngine, commands: list[dict], i: int, idx: int) -> int:
    text, next_i = _text_of(commands, i)
    if has_inline_choice(text):
        try:
            choice = parse_inline_choice(text)
        except InlineChoiceError as exc:
            raise _Aborted("search_inline_choice", f"@list[{idx}]: {exc.message}") from None
        label = f"\\ch var {choice.var_id} @list[{idx}]"
        value = engine._decide(label, choice.domain())
        engine.set_key(Variable(choice.var_id), value)
    return next_i


def _reads_party(node: object) -> bool:
    """Does this expression read `$Trainer.party` anywhere inside it?"""
    if isinstance(node, ast.Call) and node.name == "party" and isinstance(
            node.receiver, ast.GlobalVar) and node.receiver.name == "$Trainer":
        return True
    if isinstance(node, ast.Node):
        return any(_reads_party(getattr(node, f)) for f in node.__dataclass_fields__
                   if f != "span")
    if isinstance(node, tuple):
        return any(_reads_party(n) for n in node)
    return False


def _graphics_party_write(stmt: ast.Node, graphics_only_vars: frozenset[int]) -> int | None:
    """The variable id when `stmt` is `$game_variables[N] = <reads the party>`
    and N only drives graphics (`story_state.graphics_vars`, operator ruling
    2026-09-25): exempt from ruling (b)'s party_model refusal."""
    if not (isinstance(stmt, ast.Assign) and isinstance(stmt.target, ast.Index)):
        return None
    target = stmt.target
    if not (isinstance(target.receiver, ast.GlobalVar)
            and target.receiver.name == "$game_variables"
            and len(target.args) == 1 and isinstance(target.args[0], ast.Int)):
        return None
    var_id = target.args[0].value
    if var_id in graphics_only_vars and _reads_party(stmt.value):
        return var_id
    return None


def _exec_script(engine: _RunEngine, commands: list[dict], i: int, idx: int) -> int:
    source, next_i = script_block_source(commands, i)
    try:
        program = parse_program(source)
    except RubyParseError as exc:
        raise _Aborted("ruby_parse_error", f"@list[{idx}]: {exc.reason}: {exc}") from None
    kept = []
    for stmt in program.statements:
        var_id = _graphics_party_write(stmt, engine.graphics_only_vars)
        if var_id is None:
            kept.append(stmt)
        else:
            engine.havoc.add(Variable(var_id))
    if len(kept) != len(program.statements):
        program = ast.Program(program.span, tuple(kept))
    oracle = engine.oracle_for(idx)
    result = evaluate_program(program, oracle=oracle, event=(engine.map_id, engine.event_id))
    if result.refusal is not None:
        raise _Aborted(result.refusal.code, f"@list[{idx}]: {result.refusal.detail}")
    for write in result.writes:
        engine.set_key(write.key, write.value)
    for eff in result.effects:
        engine.effects.append(Effect(eff.name, tuple(_freeze(a) for a in eff.args), idx))
    return next_i


def _loop_body_end(commands: list[dict], i: int) -> int:
    indent = commands[i].get("indent", 0)
    j = i + 1
    while j < len(commands) and (commands[j].get("indent", 0) or 0) > indent:
        j += 1
    return j


def _exec_loop(engine: _RunEngine, commands: list[dict], i: int, idx: int) -> int:
    body_end = _loop_body_end(commands, i)
    body = commands[i + 1 : body_end]
    for cmd in body:
        if cmd.get("code") in _LOOP_STATE_WRITING_CODES:
            raise _Aborted("search_loop", f"code 112 @list[{idx}]: state-writing loop body")
    return body_end


def _exec_ce(
    engine: _RunEngine, cmd: dict, idx: int, visited_ce: frozenset[int],
) -> None:
    params = cmd.get("parameters") or []
    if not params:
        raise _Aborted("search_malformed_write", f"code 117 @list[{idx}]: no params")
    ce_id = params[0]
    if ce_id in engine.stripped_ce_ids:
        return
    if ce_id in visited_ce:
        raise _Aborted("search_ce_cycle", f"@list[{idx}]: common event {ce_id} already inlined -- cycle")
    ce = engine.common_events_by_id.get(ce_id)
    if ce is None:
        raise _Aborted("search_missing_common_event", f"@list[{idx}]: common event {ce_id} not found")
    ce_commands = ce.get("list") or []
    if any(c.get("code") in _CE_BRANCHING_CODES for c in ce_commands):
        raise _Aborted("search_ce_branches", f"{ce_id}")
    _exec_commands(
        engine, ce_commands, visited_ce | {ce_id}, forced_index=idx,
    )


def _exec_commands(
    engine: _RunEngine,
    commands: list[dict[str, Any]],
    visited_ce: frozenset[int],
    *,
    forced_index: int | None,
) -> None:
    i = 0
    n = len(commands)
    while i < n:
        cmd = commands[i]
        code = cmd.get("code")
        if forced_index is not None:
            idx = forced_index
        else:
            # `i` is a position in the FLATTENED scope; a caller that has the
            # owning page's raw list (story_state's extraction does) passes
            # `index_of` so writes carry the page index `Assign.list_index`
            # is specified in. Without it, the flattened position stands.
            idx = engine.index_of.get(id(cmd), i)
        engine.current_index = idx

        if code in _NEVER_FLATTENED_CODES:
            raise AssertionError(
                f"search_scope: closer code {code} present in a flattened scope "
                f"@list[{idx}] -- mis-flattened input"
            )

        if code == CODE_SHOW_TEXT:
            i = _exec_text(engine, commands, i, idx)
            continue
        if code == CODE_SCRIPT:
            i = _exec_script(engine, commands, i, idx)
            continue
        if code == CODE_SWITCH_WRITE:
            _exec_121(engine, cmd, idx)
            i += 1
            continue
        if code == CODE_VAR_WRITE:
            _exec_122(engine, cmd, idx)
            i += 1
            continue
        if code == CODE_SELF_SWITCH_WRITE:
            _exec_123(engine, cmd, idx)
            i += 1
            continue
        if code == CODE_COMMON_EVENT_CALL:
            _exec_ce(engine, cmd, idx, visited_ce)
            i += 1
            continue
        if code == CODE_LOOP:
            i = _exec_loop(engine, commands, i, idx)
            continue

        # 111/102 branch openers (legitimate, see _NEVER_FLATTENED_CODES's
        # docstring) and everything else this module doesn't model as a
        # state effect: skip.
        i += 1


def _run_once(
    prefix: tuple,
    commands: list[dict[str, Any]],
    *,
    map_id: int,
    event_id: int,
    common_events_by_id: dict[int, dict[str, Any]],
    stripped_ce_ids: frozenset[int],
    read_domain: Callable[[Key], "frozenset | None"],
    index_of: dict[int, int] | None = None,
    graphics_only_vars: frozenset[int] = frozenset(),
) -> _RunEngine | _Frontier:
    engine = _RunEngine(
        prefix, map_id=map_id, event_id=event_id,
        common_events_by_id=common_events_by_id, stripped_ce_ids=stripped_ce_ids,
        read_domain=read_domain, index_of=index_of,
        graphics_only_vars=graphics_only_vars,
    )
    try:
        _exec_commands(engine, commands, frozenset(), forced_index=None)
    except _Frontier as fr:
        return fr
    return engine


# --- driver -----------------------------------------------------------


def search_scope(
    commands: list[dict[str, Any]],
    *,
    map_id: int,
    event_id: int,
    common_events_by_id: dict[int, dict[str, Any]],
    stripped_ce_ids: frozenset[int],
    read_domain: Callable[[Key], "frozenset | None"],
    index_of: dict[int, int] | None = None,
    cap: int = 4096,
    graphics_only_vars: frozenset[int] = frozenset(),
) -> SearchResult:
    """`graphics_only_vars`: variables a `$game_variables[N] = <party read>`
    may write without refusing the scope; N comes back in `havoc`
    (`story_state.graphics_vars`)."""
    values: dict[Key, frozenset] = {}
    havoc: set[Key] = set()
    always_written: set[Key] | None = None
    write_index: dict[Key, int] = {}
    witnesses: dict[tuple[Key, object], tuple[Choice, ...]] = {}
    effect_seqs: set[tuple[Effect, ...]] = set()
    reads: set[Key] = set()
    inputs = False
    completed = 0

    def record(engine: _RunEngine) -> None:
        nonlocal always_written, inputs, completed
        completed += 1
        if completed > cap:
            raise _Aborted("search_cap", f"exceeded {cap} completed runs")
        for key in engine.explicit:
            value = engine.world[key]
            values.setdefault(key, frozenset())
            values[key] = values[key] | frozenset({value})
            idx = engine.write_index[key]
            if idx > write_index.get(key, -1):
                write_index[key] = idx
            witness_key = (key, value)
            if witness_key not in witnesses:
                witnesses[witness_key] = tuple(engine.trace)
        if always_written is None:
            always_written = set(engine.explicit)
        else:
            always_written &= engine.explicit
        reads.update(engine.read_keys)
        havoc.update(engine.havoc)
        if engine.has_input or any(
            not c.point.startswith("read ") for c in engine.trace
        ):
            inputs = True
        effect_seqs.add(tuple(engine.effects))

    def dfs(prefix: tuple) -> None:
        outcome = _run_once(
            prefix, commands, map_id=map_id, event_id=event_id,
            common_events_by_id=common_events_by_id,
            stripped_ce_ids=stripped_ce_ids, read_domain=read_domain,
            index_of=index_of, graphics_only_vars=graphics_only_vars,
        )
        if isinstance(outcome, _Frontier):
            for value in outcome.domain:
                dfs(prefix + (value,))
            return
        record(outcome)

    try:
        dfs(())
    except _Aborted as exc:
        return _empty_result(Refusal(exc.code, exc.detail))
    except AssertionError:
        raise

    return SearchResult(
        runs=completed,
        values=values,
        always_written=frozenset(always_written or ()),
        write_index=write_index,
        witnesses=witnesses,
        effects=tuple(sorted(effect_seqs, key=lambda seq: tuple((e.name, e.list_index) for e in seq))),
        reads=frozenset(reads),
        inputs=inputs,
        refusal=None,
        havoc=frozenset(havoc),
    )
