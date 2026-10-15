"""Deferred (computed) row scopes and the glue around `ruby_subset.search`
(REDERIVATION_PLAN.md §16.3 C8 stage 4, "Stages 3-4 refined").

`story_state/extract.py` runs a row's own flattened command list through
`ruby_subset.search.search_scope` the moment the scope contains embedded
Ruby the old regex readers used to guess at (a 355/655 script block, or an
inline `\\ch[...]` text choice). Most such scopes are fully self-contained
and resolve at extraction time. A row whose run reads state OUTSIDE its own
scope (a switch/variable/self-switch/temp-switch/engine key it consults but
never itself writes first) cannot be resolved yet -- that row becomes
*computed*: `ComputedScope` freezes everything needed to re-run the exact
same search later, once the resolver in `story_state/model.py` has a
saturated value set to answer the read with. The resolver repeats this
(`run_scope` against successively larger `read_domain`s) until the written
value sets stop growing, which terminates because they are capped
(`ruby_subset.search.search_scope`'s own `cap`) and can only grow, never
shrink, across iterations (REDERIVATION_PLAN.md §16.3, "Stages 3-4
refined").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from rpg2gba.conversion_agent.deterministic import join_text_lines
from rpg2gba.conversion_agent.inline_choice import has_inline_choice
from rpg2gba.ruby_subset import ast as ast_
from rpg2gba.ruby_subset.builtins import EFFECT_CALLS
from rpg2gba.ruby_subset.lexer import RubyParseError
from rpg2gba.ruby_subset.parser import parse_program, script_block_source
from rpg2gba.ruby_subset.search import (
    SearchResult,
    load_stripped_ce_ids,
    search_scope,
)
from rpg2gba.story_state.display_vars import display_var_policy
from rpg2gba.story_state.graphics_vars import graphics_only_variables
from rpg2gba.story_state.state import (
    Assign,
    Key,
    Refusal,
    SelfSwitch,
    Switch,
    Variable,
    Write,
)

__all__ = [
    "ComputedScope",
    "run_scope",
    "scope_needs_interpreter",
    "self_contained_counters",
    "writes_from_result",
    "witness_citations",
    "stripped_ce_ids_for",
    "named_write_targets",
]

# Same local-constant convention as ruby_subset.search / chapter_manifest.
# generator (no single canonical command-code module in this corpus).
_CODE_SHOW_TEXT = 101
_CODE_SHOW_TEXT_CONT = 401
_CODE_SCRIPT = 355
_CODE_CONTROL_SWITCHES = 121
_CODE_CONTROL_SELF_SWITCH = 123


@dataclass(frozen=True, eq=False)
class ComputedScope:
    """Everything needed to RE-RUN one row's search against a different
    `read_domain` (REDERIVATION_PLAN.md §16.3, "Stages 3-4 refined").

    This row's writes could not be resolved at extraction time because its
    run reads state outside its own scope (a key it consults but never
    itself writes first) -- `first_unknown_read` is that read's `repr(key)`
    citation, from the `search_unknown_read` refusal `ruby_subset.search.
    search_scope` raised. The resolver in `story_state/model.py` re-runs
    this scope (`run_scope`, below) against the previous saturation
    iteration's value sets until the row's own written value sets stop
    changing -- sound because saturation is already a flow-insensitive
    union, so widening the read domain can only add possibilities, never
    invalidate ones already recorded.

    `eq=False` (frozen dataclasses default to a structural `__eq__`/
    `__hash__` over all fields, but `commands`/`common_events_by_id` are
    raw dicts sliced from the corpus -- unhashable, and identity comparison
    is the only sensible notion of "same computed scope" here anyway).
    """

    row_id: str
    map_id: int
    event_id: int
    commands: list[dict[str, Any]]
    index_of: dict[int, int]
    common_events_by_id: dict[int, dict[str, Any]]
    stripped_ce_ids: frozenset[int]
    conditional: bool
    first_unknown_read: str


def run_scope(
    scope: ComputedScope, read_domain: Callable[[Key], "frozenset | None"],
) -> SearchResult:
    """Re-run `scope`'s search against `read_domain` -- a one-line wrapper
    over `ruby_subset.search.search_scope` using the scope's own frozen
    arguments, so a resolver never has to reconstruct them."""
    return search_scope(
        scope.commands,
        map_id=scope.map_id,
        event_id=scope.event_id,
        common_events_by_id=scope.common_events_by_id,
        stripped_ce_ids=scope.stripped_ce_ids,
        read_domain=read_domain,
        index_of=scope.index_of,
        graphics_only_vars=graphics_only_variables(),
        display_write_ok=display_var_policy().write_ok,
    )


def _joined_text(commands: list[dict[str, Any]], start: int) -> str:
    """Join a code-101 Show Text with its 401 continuations -- same
    joining (`join_text_lines`) `ruby_subset.search._text_of` and
    `transpiler.parse_tree` both use (CLAUDE.md §4.3: one joiner)."""
    cmd = commands[start]
    params = cmd.get("parameters") or [""]
    parts = [str(params[0]) if params else ""]
    i = start + 1
    while i < len(commands) and commands[i].get("code") == _CODE_SHOW_TEXT_CONT:
        p = commands[i].get("parameters") or [""]
        parts.append(str(p[0]) if p else "")
        i += 1
    return join_text_lines(parts)


def scope_needs_interpreter(commands: list[dict[str, Any]]) -> bool:
    """True when `commands` (one row's own flattened list) contains any
    embedded Ruby the old regex readers used to guess at: a 355 script
    block, or a 101/401 text run carrying an inline `\\ch[...]` choice."""
    for i, cmd in enumerate(commands):
        code = cmd.get("code")
        if code == _CODE_SCRIPT:
            return True
        if code == _CODE_SHOW_TEXT:
            if has_inline_choice(_joined_text(commands, i)):
                return True
    return False


def _walk_nodes(nodes: tuple[ast_.Node, ...]):
    """Every node in `nodes`, recursively -- the one traversal this module's
    best-effort target scan needs."""
    for node in nodes:
        yield node
        for value in vars(node).values():
            if isinstance(value, ast_.Node):
                yield from _walk_nodes((value,))
            elif isinstance(value, tuple):
                for item in value:
                    if isinstance(item, ast_.Node):
                        yield from _walk_nodes((item,))
                    elif isinstance(item, tuple):
                        yield from _walk_nodes(
                            tuple(x for x in item if isinstance(x, ast_.Node)))


def _target_key(node: ast_.Node, map_id: int, event_id: int) -> Key | None:
    if isinstance(node, ast_.Index) and isinstance(node.receiver, ast_.GlobalVar):
        if len(node.args) == 1 and isinstance(node.args[0], ast_.Int):
            if node.receiver.name == "$game_switches":
                return Switch(node.args[0].value)
            if node.receiver.name == "$game_variables":
                return Variable(node.args[0].value)
    if isinstance(node, ast_.Call) and node.args:
        first = node.args[0]
        if node.name == "pbSet" and isinstance(first, ast_.Int):
            return Variable(first.value)
        if node.name == "pbSetSelfSwitch" and isinstance(first, ast_.Int):
            letter = node.args[1] if len(node.args) > 1 else None
            if isinstance(letter, ast_.Str) and letter.value:
                return SelfSwitch(map_id, first.value, letter.value)
        # pbTextEntry(help, minlen, maxlen, variableNumber[, pkmn]) stores the
        # entered text in $game_variables[variableNumber] (Name Rater, CH06).
        if node.name == "pbTextEntry" and len(node.args) >= 4 \
                and isinstance(node.args[3], ast_.Int):
            return Variable(node.args[3].value)
    return None


def _command_write_keys(cmd: dict[str, Any], map_id: int, event_id: int) -> tuple[Key, ...]:
    """Keys a plain RMXP write command assigns: 121 Control Switches (a
    literal id range), 122 Control Variables (a literal id range), 123 Control
    Self Switch (this event)."""
    code, params = cmd.get("code"), cmd.get("parameters") or []
    if code == _CODE_CONTROL_SWITCHES and len(params) >= 2:
        return tuple(Switch(i) for i in range(params[0], params[1] + 1))
    if code == _CODE_CONTROL_VARIABLES and len(params) >= 2:
        return tuple(Variable(i) for i in range(params[0], params[1] + 1))
    if code == _CODE_CONTROL_SELF_SWITCH and params and isinstance(params[0], str):
        return (SelfSwitch(map_id, event_id, params[0]),)
    return ()


#: `pbChoosePokemon(varA, varB, proc {|x| <predicate>})` -- the party pick
#: with an eligibility filter (Map046 EV014's trade). The subset parser has no
#: block parameters, but the shape is fully known: the call writes vars A and B
#: (chosen slot, chosen name), and the proc is a pure predicate (no `=` other
#: than a comparison). Any other unparseable block keeps `havoc_global`.
_CHOOSE_WITH_FILTER_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbChoosePokemon\(\s*(\d+)\s*,\s*(\d+)\s*,\s*proc\s*\{\s*\|\w+\|"
    r"(?P<body>[^{}]*)\}\s*\)\s*$", re.S)


def _choose_with_filter_keys(source: str) -> tuple[Key, ...] | None:
    m = _CHOOSE_WITH_FILTER_RE.match(source)
    if m is None or re.search(r"(?<![=!<>])=(?!=)", m.group("body")):
        return None
    return (Variable(int(m.group(1))), Variable(int(m.group(2))))


#: Calls whose state effect `named_write_targets` names itself.
_NAMING_CALLS = frozenset({"pbSet", "pbGet", "pbSetSelfSwitch", "pbTextEntry", "_I"})
#: `$Trainer`-style global attributes that are pure reads of party/dex state.
_GLOBAL_READS = frozenset({"party", "pokedexSeen", "pokedexOwned"})


def _call_ok(node: ast_.Call) -> bool:
    receiver = node.receiver
    if receiver is None or (isinstance(receiver, ast_.Const) and receiver.name == "Kernel"):
        return node.name in EFFECT_CALLS or node.name in _NAMING_CALLS
    root = receiver
    while isinstance(root, (ast_.Call, ast_.Index)):
        root = root.receiver
        if root is None:
            return False
    if isinstance(root, (ast_.Local, ast_.Const, ast_.ScopedConst)):
        return True   # a method on a local object or a constant (PBSpecies.getName)
    if isinstance(root, ast_.GlobalVar):
        return node.name in _GLOBAL_READS or (
            isinstance(node.receiver, ast_.GlobalVar) and node.name in _GLOBAL_READS)
    return False


def _assign_ok(target: ast_.Node, map_id: int, event_id: int) -> bool:
    if isinstance(target, ast_.Local) or _target_key(target, map_id, event_id) is not None:
        return True
    root = target
    while isinstance(root, (ast_.Call, ast_.Index)):
        root = root.receiver
        if root is None:
            return False
    return isinstance(root, ast_.Local)   # `pkmn.name = ...` on a local object


def writes_exhaustively_named(
    commands: list[dict[str, Any]], *, map_id: int, event_id: int,
) -> bool:
    """True iff `named_write_targets` provably names EVERY story-state key
    the scope can write, so an empty result means "writes nothing modelled"
    rather than "cannot tell" (2026-10-15, CH08; CH06's Name Rater nickname
    arm and trade arm, Map046, were turning everything TOP downstream).

    Every script block parses; every call is a known no-modelled-state
    effect (`builtins.EFFECT_CALLS`), a state accessor this module names, a
    method on a local object or constant, or a read of `$Trainer.party`/dex
    counts; every assignment targets a local, a local object's attribute, or
    a key `_target_key` names; and the scope calls no common event (117),
    which could write anything."""
    i = 0
    while i < len(commands):
        code = commands[i].get("code")
        if code == _CODE_CALL_COMMON_EVENT:
            return False
        if code != _CODE_SCRIPT:
            i += 1
            continue
        try:
            source, next_i = script_block_source(commands, i)
        except ValueError:
            return False
        if _choose_with_filter_keys(source) is not None:
            i = next_i
            continue
        try:
            program = parse_program(source)
        except RubyParseError:
            return False
        for node in _walk_nodes(program.statements):
            if isinstance(node, ast_.Call) and not _call_ok(node):
                return False
            if isinstance(node, (ast_.Assign, ast_.OpAssign)) \
                    and not _assign_ok(node.target, map_id, event_id):
                return False
            if isinstance(node, (ast_.InstanceVar,)):
                return False
        i = next_i
    return True


def named_write_targets(
    commands: list[dict[str, Any]], *, map_id: int, event_id: int,
) -> tuple[Key, ...]:
    """Best-effort: the state keys a scope's scripts can be SEEN to write,
    named without running anything.

    This is the havoc-naming aid, not an authority on what the scope writes
    -- `search_scope` is that, and when it succeeds nothing here is
    consulted. It exists for the refusal case: a row whose script the
    interpreter could not evaluate still writes something, and naming the
    keys it syntactically assigns keeps `model.py`'s FIX 2b precision (havoc
    THOSE keys) instead of falling back to havoc-everything. Deliberately
    conservative: a script block that will not even parse contributes
    nothing, and a dynamically-indexed target (`$game_switches[i]`) is not
    named -- both leave the caller on `havoc_global`, which is sound.

    *(2026-10-15, CH08: when every script block parses, the scope's plain
    121/122/123 write commands are named too -- before, a refused row whose
    only nameable writes were commands (CH06's Name Rater and trade NPC,
    Map046) fell to `havoc_global` and turned var 101 TOP for every later
    chapter. A block that will not parse still leaves the row global.)*
    """
    keys: list[Key] = []
    all_parse = True
    i = 0
    while i < len(commands):
        if commands[i].get("code") != _CODE_SCRIPT:
            i += 1
            continue
        try:
            source, next_i = script_block_source(commands, i)
        except ValueError:
            all_parse = False
            i += 1
            continue
        chosen = _choose_with_filter_keys(source)
        if chosen is not None:
            keys.extend(k for k in chosen if k not in keys)
            i = next_i
            continue
        try:
            program = parse_program(source)
        except RubyParseError:
            all_parse = False
            i += 1
            continue
        for node in _walk_nodes(program.statements):
            target = None
            if isinstance(node, (ast_.Assign, ast_.OpAssign)):
                target = _target_key(node.target, map_id, event_id)
            elif isinstance(node, ast_.Call):
                target = _target_key(node, map_id, event_id)
            if target is not None and target not in keys:
                keys.append(target)
        i = next_i
    if all_parse:
        for cmd in commands:
            for key in _command_write_keys(cmd, map_id, event_id):
                if key not in keys:
                    keys.append(key)
    return tuple(keys)


# RMXP Control Variables (122): [start_id, end_id, operation, operand_type,
# operand, ...]. Operations 1-5 (add/sub/mul/div/mod) read the target's own
# value; 0 (set) does not. Operand type 1 reads another variable.
_CODE_CONTROL_VARIABLES = 122
_CODE_CONDITIONAL = 111
_CODE_CALL_COMMON_EVENT = 117
_CODE_SCRIPT_CONT = 655
_SELF_READING_OPS = frozenset({1, 2, 3, 4, 5})
_INT_RE = re.compile(r"\b(\d+)\b")
# Commands that take a variable id as a designated operand, with the index of
# their "designated by variable" flag and the param indices it switches on.
_VARIABLE_DESIGNATED = {
    201: (0, (1, 2, 3)),   # Transfer Player
    202: (1, (2, 3)),      # Set Event Location
    231: (3, (4, 5)),      # Show Picture
    232: (3, (4, 5)),      # Move Picture
}


def _foreign_variable_reads(
    commands: list[dict[str, Any]],
    common_events_by_id: dict[int, dict[str, Any]],
    visited_ce: frozenset[int] = frozenset(),
) -> tuple[set[int], bool]:
    """Variable ids `commands` reads for any purpose OTHER than updating that
    same variable in place, and whether a script block appears (scripts are
    matched textually by the caller). Recurses through common-event calls."""
    reads: set[int] = set()
    scripts: list[str] = []
    for cmd in commands:
        code = cmd.get("code")
        params = cmd.get("parameters") or []
        if code == _CODE_CONDITIONAL and len(params) >= 4 and params[0] == 1:
            reads.add(params[1])
            if params[2] == 1:
                reads.add(params[3])
        elif code == _CODE_CONTROL_VARIABLES and len(params) >= 5 and params[3] == 1:
            reads.add(params[4])
        elif code in _VARIABLE_DESIGNATED:
            flag_idx, id_idxs = _VARIABLE_DESIGNATED[code]
            if len(params) > max(id_idxs) and params[flag_idx] == 1:
                reads.update(params[i] for i in id_idxs)
        elif code in (_CODE_SCRIPT, _CODE_SCRIPT_CONT) and params:
            scripts.append(str(params[0]))
        elif code == _CODE_CALL_COMMON_EVENT and params:
            ce_id = params[0]
            ce = common_events_by_id.get(ce_id)
            if ce is None or ce_id in visited_ce:
                return reads, True  # unknown callee: treat as reading anything
            sub_reads, sub_unknown = _foreign_variable_reads(
                ce.get("list") or [], common_events_by_id, visited_ce | {ce_id})
            reads |= sub_reads
            if sub_unknown:
                return reads, True
    joined = "\n".join(scripts)
    reads.update(int(n) for n in _INT_RE.findall(joined))
    return reads, False


def self_contained_counters(
    commands: list[dict[str, Any]],
    common_events_by_id: dict[int, dict[str, Any]],
) -> frozenset[Key]:
    """Variables this scope updates in place (Control Variables add/sub/mul/
    div/mod on the variable itself) and reads NOWHERE else -- no branch, no
    other variable's operand, no designated coordinate, no script (any
    integer literal in a script counts, deliberately conservative), no
    common event this scope calls.

    Such a counter's value flows only back into itself, so nothing else the
    row writes can depend on it: the resolver can evaluate the row with any
    placeholder value for it, keep the other writes, and mark the counter
    alone "could be anything" (C9 ruling 13). Without this, reading and
    writing the same key has no fixpoint and the whole row widens to TOP
    (`computed_row_self_reference`)."""
    self_updated: set[int] = set()
    for cmd in commands:
        params = cmd.get("parameters") or []
        if (cmd.get("code") == _CODE_CONTROL_VARIABLES and len(params) >= 3
                and params[2] in _SELF_READING_OPS):
            self_updated.update(range(params[0], params[1] + 1))
    if not self_updated:
        return frozenset()
    foreign, unknown = _foreign_variable_reads(commands, common_events_by_id)
    if unknown:
        return frozenset()
    return frozenset(Variable(i) for i in sorted(self_updated - foreign))


def writes_from_result(
    result: SearchResult, *, conditional: bool, source_prefix: str,
) -> tuple[tuple[Write, ...], tuple[Key, ...]]:
    """Convert a refusal-free `SearchResult` into `state.Assign` writes,
    plus the keys it wrote a non-scalar value to.

    Every value in `result.values[key]` must be a `bool` or `int` -- an
    `Opaque`/`ConstRef`/`Symbol` or a string (a species NAME stored in a
    variable) is not a representable state value (CLAUDE.md §5's
    dataclass-shape discipline): no write is emitted for that key, and it
    is returned as a havoc key instead, so every reader of it sees "could
    be anything" and refuses by name there (`computed_row_top_read`). The
    row's other writes stand (C9 ruling 13, 2026-09-25): one text-valued
    variable says nothing about the quest log written beside it. Before
    that ruling this raised `search_nonscalar_value` and the whole row was
    refused.

    A key written on every completed run (`key in result.always_written`)
    is unconditional unless the caller says otherwise; a key written on
    only SOME runs is never guaranteed, regardless of what the caller
    says.

    A key in `result.havoc` (a graphics-only variable written from a party
    read, `story_state.graphics_vars`) is havoc too, whatever else the row
    wrote to it.
    """
    writes: list[Write] = []
    havoc: list[Key] = sorted(result.havoc, key=repr)
    for key in sorted(result.values, key=repr):
        values = result.values[key]
        if key in result.havoc:
            continue
        if any(not isinstance(v, (bool, int)) for v in values):
            havoc.append(key)
            continue
        is_conditional = conditional or key not in result.always_written
        writes.append(Assign(
            key, values, is_conditional,
            f"{source_prefix}: search over {result.runs} runs",
            result.write_index[key],
        ))
    return tuple(writes), tuple(havoc)


def witness_citations(
    result: SearchResult,
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """One JSON-serialisable citation per `(key, value)` the search
    resolved: `(key_repr, value_repr, tuple of rendered Choice labels)`.

    Each `Choice` renders as ``f"{point}={value!r}"`` -- a single stable
    string combining the choice's label and the value decided there (the
    exact form doesn't matter beyond staying stable across calls, since
    this is a citation for a human/report, not something re-parsed).
    Deterministic: sorted by `(key_repr, value_repr)` -- both the resolver
    (`story_state/model.py`, re-running a `ComputedScope` against a
    saturated `read_domain`) and this module's own caller
    (`story_state/extract.py`) must produce byte-identical output for the
    same inputs (CLAUDE.md §4.2 idempotence).
    """
    out: list[tuple[str, str, tuple[str, ...]]] = []
    for (key, value), trace in result.witnesses.items():
        labels = tuple(f"{c.point}={c.value!r}" for c in trace)
        out.append((repr(key), repr(value), labels))
    out.sort(key=lambda t: (t[0], t[1]))
    return tuple(out)


_STRIPPED_CE_CACHE: dict[Path, frozenset[int]] = {}


def stripped_ce_ids_for(reference_dir: Path) -> frozenset[int]:
    """Cached wrapper over `ruby_subset.search.load_stripped_ce_ids` --
    every `story_state` caller wants the same strip list for the same
    `reference/` directory within one process, so this avoids re-reading
    `strip_list.json` once per row."""
    cached = _STRIPPED_CE_CACHE.get(reference_dir)
    if cached is None:
        cached = load_stripped_ce_ids(reference_dir)
        _STRIPPED_CE_CACHE[reference_dir] = cached
    return cached
