"""AST recognizers for the transpiler's Ruby-local / array / argmax idioms.

C8 stage 6 (REDERIVATION_PLAN.md §16). These twelve shapes used to be twelve
anchored regexes in `transpiler.py`; they now match against a real parse from
`ruby_subset` (CLAUDE.md §4.3 — one grammar, not a sixth independent reader).

**This module recognizes; it does not emit.** Every matcher is a pure
function from one 355/655 row's Ruby text to a small frozen record, or
`None` when the row isn't that idiom. The Poryscript for each idiom, and all
the symbol resolution behind it (`ctx.var_for_variable`, the scratch-var
allocation, the `>=`-chain argmax), stays in `transpiler._PageEmitter` where
it was — this is a swap of the *reader*, not of the emitter.

Two deliberate non-widenings, both so C8 stage 6 lands as a provably
output-neutral change (it was gated on byte-identical transpiler output over
every staged map):

* `pbGet(N)` is accepted only where the original regex wrote `pbGet(N)`, even
  though `$game_variables[N]` means exactly the same thing and the AST could
  now see that for free. Accepting both is a one-line change to `_pbget_var`
  (fall back to `_game_variable_target`), and it was measured on 2026-09-23:
  across all 664 script rows in the staged corpus it matches the same 8 rows
  either way, so widening buys nothing today. It stays narrow because the
  narrow miss is the SAFE failure — a `x = $game_variables[151]` spelling
  queues the row where a human sees it (§4.5), where the wide form would
  quietly handle a shape nobody has measured.
* The `if x==A / x=B / elsif ... / end` remap chain is still matched one row
  at a time, because RMXP delivers it as separate 655 rows and
  `_merge_script_call_rows` deliberately refuses to fuse them (they are
  complete statements, not wrap fragments). Parsing the chain as one `ast.If`
  would mean buffering rows across the page and flushing unterminated ones,
  which is a larger change than this stage bought.
"""
from __future__ import annotations

from dataclasses import dataclass

from rpg2gba.ruby_subset import ast, parse_program
from rpg2gba.ruby_subset.lexer import RubyParseError

# --- records ---------------------------------------------------------------


@dataclass(frozen=True)
class LocalFromVar:
    """``x = pbGet(N)`` — bind a Ruby local to a game variable's value."""

    name: str
    source_var: int


@dataclass(frozen=True)
class LocalAddSub:
    """``x += n`` / ``x -= n`` — signed offset onto a tracked local."""

    name: str
    delta: int


@dataclass(frozen=True)
class LocalWrap:
    """``x = to if x == from`` — the postfix-if wrap-around remap."""

    name: str
    from_value: int
    to_value: int


@dataclass(frozen=True)
class ArrayLiteral:
    """``$game_variables[N] = [0,0,0]`` — an array-valued game variable."""

    var_id: int
    values: tuple[int, ...]


@dataclass(frozen=True)
class ArrayBump:
    """``pbGet(A)[pbGet(B)] += n`` — bump the bucket B selects."""

    var_id: int
    index_var: int
    delta: int


@dataclass(frozen=True)
class ArrayArgmax:
    """``x = pbGet(A).index(pbGet(A).max)`` — lowest-index-wins argmax.

    Only minted when both `pbGet`s name the SAME variable; the regex this
    replaced checked that separately at its call site.
    """

    name: str
    var_id: int


@dataclass(frozen=True)
class RemapArmOpen:
    """``if x == A`` / ``elsif x == A`` — opens one arm of a remap chain."""

    name: str
    tested_value: int


@dataclass(frozen=True)
class LocalConstAssign:
    """``x = A`` — a bare integer into a local (a remap arm's body)."""

    name: str
    value: int


@dataclass(frozen=True)
class VarFromLocal:
    """``$game_variables[N] = x`` — write a tracked local back to a var."""

    var_id: int
    name: str


@dataclass(frozen=True)
class StringList:
    """``list = ["a","b","c"]`` — a local bound to an ordered string list."""

    name: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class VarFromListIndex:
    """``$game_variables[N] = list[x]`` — indexed readback of a StringList."""

    var_id: int
    list_name: str
    index_name: str


# --- shared shape helpers --------------------------------------------------


def parse_statement(text: str) -> ast.Node | None:
    """The single statement `text` spells, or `None`.

    `None` covers both "doesn't parse" (an out-of-subset row — the caller
    queues it, exactly as an unmatched regex did) and "parses as more than
    one statement", which none of these idioms ever are.
    """
    try:
        program = parse_program(text)
    except RubyParseError:
        return None
    if len(program.statements) != 1:
        return None
    return program.statements[0]


def _local_name(node: ast.Node) -> str | None:
    """The bare lowercase identifier `node` reads, or `None`.

    A first mention parses as a zero-arg `Call` rather than a `Local` —
    the parser's flat known-locals tracking can't tell `x` the variable from
    `x` the receiverless method until it has seen an assignment (see
    `ruby_subset/parser.py`'s module docstring). Both spell the same thing
    here, so both are accepted.
    """
    if isinstance(node, ast.Local):
        return node.name
    if (
        isinstance(node, ast.Call)
        and node.receiver is None
        and not node.args
        and node.block is None
        and (node.name[:1].islower() or node.name.startswith("_"))
    ):
        return node.name
    return None


def _int_value(node: ast.Node) -> int | None:
    """An integer literal, with a unary minus folded in (`-1` parses as
    `UnaryOp("-", Int(1))`, and the regexes this replaced all wrote `-?\\d+`)."""
    if isinstance(node, ast.Int):
        return node.value
    if isinstance(node, ast.UnaryOp) and node.op == "-":
        inner = _int_value(node.operand)
        return None if inner is None else -inner
    return None


def _pbget_var(node: ast.Node) -> int | None:
    """``pbGet(<int>)`` -> the variable id. See the module docstring on why
    `$game_variables[<int>]` is deliberately NOT accepted here."""
    if (
        isinstance(node, ast.Call)
        and node.receiver is None
        and node.name == "pbGet"
        and node.block is None
        and len(node.args) == 1
    ):
        return _int_value(node.args[0])
    return None


def _game_variable_target(node: ast.Node) -> int | None:
    """``$game_variables[<int>]`` as an assignment target -> the variable id."""
    if (
        isinstance(node, ast.Index)
        and isinstance(node.receiver, ast.GlobalVar)
        and node.receiver.name == "$game_variables"
        and len(node.args) == 1
    ):
        return _int_value(node.args[0])
    return None


# --- matchers --------------------------------------------------------------


def match_local_from_var(node: ast.Node) -> LocalFromVar | None:
    if not isinstance(node, ast.Assign):
        return None
    name = _local_name(node.target)
    source = _pbget_var(node.value)
    if name is None or source is None:
        return None
    return LocalFromVar(name, source)


def match_local_addsub(node: ast.Node) -> LocalAddSub | None:
    if not isinstance(node, ast.OpAssign) or node.op not in ("+", "-"):
        return None
    name = _local_name(node.target)
    magnitude = _int_value(node.value)
    # The regex was `(\d+)` — unsigned. A literal `x -= -1` is not this idiom.
    if name is None or magnitude is None or magnitude < 0:
        return None
    return LocalAddSub(name, magnitude if node.op == "+" else -magnitude)


def match_local_wrap(node: ast.Node) -> LocalWrap | None:
    """``x = to if x == from`` — one postfix-if, both sides the same local."""
    if not isinstance(node, ast.If) or not node.postfix:
        return None
    if node.elifs or node.else_body or len(node.then_body) != 1:
        return None
    assign = node.then_body[0]
    if not isinstance(assign, ast.Assign):
        return None
    name = _local_name(assign.target)
    to_value = _int_value(assign.value)
    cond = node.cond
    if not isinstance(cond, ast.BinOp) or cond.op != "==":
        return None
    cond_name = _local_name(cond.left)
    from_value = _int_value(cond.right)
    if name is None or to_value is None or from_value is None:
        return None
    if cond_name != name:  # the regex's backreference \1
        return None
    return LocalWrap(name, from_value, to_value)


def match_array_literal(node: ast.Node) -> ArrayLiteral | None:
    if not isinstance(node, ast.Assign):
        return None
    var_id = _game_variable_target(node.target)
    if var_id is None or not isinstance(node.value, ast.ArrayLit):
        return None
    values: list[int] = []
    for element in node.value.elements:
        value = _int_value(element)
        if value is None:
            return None  # a non-integer element is not this idiom
        values.append(value)
    return ArrayLiteral(var_id, tuple(values))


def match_array_bump(node: ast.Node) -> ArrayBump | None:
    if not isinstance(node, ast.OpAssign) or node.op != "+":
        return None
    target = node.target
    if not isinstance(target, ast.Index) or len(target.args) != 1:
        return None
    var_id = _pbget_var(target.receiver)
    index_var = _pbget_var(target.args[0])
    delta = _int_value(node.value)
    if var_id is None or index_var is None or delta is None or delta < 0:
        return None
    return ArrayBump(var_id, index_var, delta)


def match_array_argmax(node: ast.Node) -> ArrayArgmax | None:
    if not isinstance(node, ast.Assign):
        return None
    name = _local_name(node.target)
    call = node.value
    if name is None or not isinstance(call, ast.Call):
        return None
    if call.name != "index" or call.receiver is None or len(call.args) != 1:
        return None
    var_id = _pbget_var(call.receiver)
    inner = call.args[0]
    if not isinstance(inner, ast.Call) or inner.name != "max" or inner.args:
        return None
    if inner.receiver is None:
        return None
    max_var = _pbget_var(inner.receiver)
    if var_id is None or max_var is None or var_id != max_var:
        return None
    return ArrayArgmax(name, var_id)


def match_remap_arm_open(text: str) -> RemapArmOpen | None:
    """``if x == A`` / ``elsif x == A`` as a row of its own.

    RMXP hands these over one 655 row at a time, so the row is not a
    complete Ruby statement. Two lines of normalization make it one — an
    `elsif` head becomes `if`, and a closing `end` is appended — and the
    parser does the rest. Nothing else about the row is assumed; a body on
    the same line, an `&&`, or an `else` all fail to match the empty-body
    single-condition shape below and fall through to the caller's queue.
    """
    stripped = text.strip()
    if stripped.startswith("elsif"):
        stripped = "if" + stripped[len("elsif"):]
    elif not stripped.startswith("if"):
        return None
    node = parse_statement(f"{stripped}\nend")
    if not isinstance(node, ast.If) or node.postfix:
        return None
    if node.then_body or node.elifs or node.else_body:
        return None
    cond = node.cond
    if not isinstance(cond, ast.BinOp) or cond.op != "==":
        return None
    name = _local_name(cond.left)
    tested = _int_value(cond.right)
    if name is None or tested is None:
        return None
    return RemapArmOpen(name, tested)


def is_block_end(text: str) -> bool:
    """A bare ``end`` row — a block terminator, not a Ruby statement, so
    there is nothing for the parser to say about it."""
    return text.strip() == "end"


def match_local_const_assign(node: ast.Node) -> LocalConstAssign | None:
    if not isinstance(node, ast.Assign):
        return None
    name = _local_name(node.target)
    value = _int_value(node.value)
    if name is None or value is None:
        return None
    return LocalConstAssign(name, value)


def match_var_from_local(node: ast.Node) -> VarFromLocal | None:
    if not isinstance(node, ast.Assign):
        return None
    var_id = _game_variable_target(node.target)
    name = _local_name(node.value)
    if var_id is None or name is None:
        return None
    return VarFromLocal(var_id, name)


def match_string_list(node: ast.Node) -> StringList | None:
    if not isinstance(node, ast.Assign):
        return None
    name = _local_name(node.target)
    if name is None or not isinstance(node.value, ast.ArrayLit):
        return None
    values: list[str] = []
    for element in node.value.elements:
        # The regex was `"[^"]*"` — double-quoted, no interpolation. An
        # interpolated element has `value is None` and isn't this idiom.
        if not isinstance(element, ast.Str) or element.value is None:
            return None
        values.append(element.value)
    return StringList(name, tuple(values))


def match_var_from_list_index(node: ast.Node) -> VarFromListIndex | None:
    if not isinstance(node, ast.Assign):
        return None
    var_id = _game_variable_target(node.target)
    value = node.value
    if var_id is None or not isinstance(value, ast.Index):
        return None
    if len(value.args) != 1:
        return None
    list_name = _local_name(value.receiver)
    index_name = _local_name(value.args[0])
    if list_name is None or index_name is None:
        return None
    return VarFromListIndex(var_id, list_name, index_name)
