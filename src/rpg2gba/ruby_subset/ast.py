"""AST node kinds for the embedded-Ruby subset (REDERIVATION_PLAN.md C8).

All nodes are frozen dataclasses. Every node carries `span: tuple[int, int]`
-- char offsets into the source it was parsed from -- so a later consumer
(the evaluator, a diagnostic) can point back at the exact source text.

This module is pure data: no parsing logic lives here (see `parser.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

Span = tuple[int, int]


@dataclass(frozen=True)
class Node:
    span: Span


# --- literals --------------------------------------------------------------

@dataclass(frozen=True)
class Int(Node):
    value: int


@dataclass(frozen=True)
class Float(Node):
    value: float


@dataclass(frozen=True)
class Str(Node):
    """A single/double quoted string literal.

    `value` is the decoded text when the string has no `#{...}`
    interpolation; `None` when `interpolated` is True (decoding would
    require evaluating the interpolated expression, which is out of scope
    for a syntax-only stage). `raw` is the literal source text between the
    quotes (escapes not decoded), always populated.
    """
    value: str | None
    interpolated: bool
    raw: str


@dataclass(frozen=True)
class Sym(Node):
    name: str


@dataclass(frozen=True)
class Bool(Node):
    value: bool


@dataclass(frozen=True)
class Nil(Node):
    pass


@dataclass(frozen=True)
class ArrayLit(Node):
    elements: tuple[Node, ...]


@dataclass(frozen=True)
class HashLit(Node):
    pairs: tuple[tuple[Node, Node], ...]


@dataclass(frozen=True)
class RangeLit(Node):
    lo: Node
    hi: Node
    exclusive: bool


# --- names -------------------------------------------------------------

@dataclass(frozen=True)
class Local(Node):
    """A bare lowercase identifier resolved (by the parser's flat
    known-locals tracking, not real Ruby scoping) as a variable read
    rather than a zero-arg method call. See parser.py's module docstring
    for the disambiguation rule."""
    name: str


@dataclass(frozen=True)
class GlobalVar(Node):
    name: str  # includes the leading "$", e.g. "$game_variables"


@dataclass(frozen=True)
class InstanceVar(Node):
    name: str  # includes the leading "@"


@dataclass(frozen=True)
class Const(Node):
    name: str
    top_level: bool = False  # a leading "::" before this name


@dataclass(frozen=True)
class ScopedConst(Node):
    scope: Node
    name: str


# --- calls / indexing ----------------------------------------------------

@dataclass(frozen=True)
class Block(Node):
    params: tuple[str, ...]
    body: tuple[Node, ...]


@dataclass(frozen=True)
class Call(Node):
    receiver: Node | None
    name: str
    args: tuple[Node, ...]
    block: Block | None = None


@dataclass(frozen=True)
class Index(Node):
    receiver: Node
    args: tuple[Node, ...]


# --- assignment ------------------------------------------------------------

@dataclass(frozen=True)
class Assign(Node):
    target: Node
    value: Node


@dataclass(frozen=True)
class OpAssign(Node):
    target: Node
    op: str  # "+", "-", "*", "/", "%"
    value: Node


# --- operators -------------------------------------------------------------

@dataclass(frozen=True)
class BinOp(Node):
    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class UnaryOp(Node):
    op: str  # "!", "-"
    operand: Node


@dataclass(frozen=True)
class Ternary(Node):
    cond: Node
    then: Node
    else_: Node


# --- control flow ------------------------------------------------------

@dataclass(frozen=True)
class If(Node):
    cond: Node
    then_body: tuple[Node, ...]
    elifs: tuple[tuple[Node, tuple[Node, ...]], ...] = ()
    else_body: tuple[Node, ...] | None = None
    postfix: bool = False


@dataclass(frozen=True)
class Unless(Node):
    cond: Node
    then_body: tuple[Node, ...]
    else_body: tuple[Node, ...] | None = None
    postfix: bool = False


@dataclass(frozen=True)
class For(Node):
    var: str
    iterable: Node
    body: tuple[Node, ...]


@dataclass(frozen=True)
class While(Node):
    cond: Node
    body: tuple[Node, ...]


@dataclass(frozen=True)
class Return(Node):
    value: Node | None = None


@dataclass(frozen=True)
class Break(Node):
    value: Node | None = None


@dataclass(frozen=True)
class Next(Node):
    value: Node | None = None


@dataclass(frozen=True)
class Program(Node):
    statements: tuple[Node, ...] = field(default_factory=tuple)
