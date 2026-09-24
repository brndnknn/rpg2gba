"""Uranium's Bambo reward ladder (`PROFREWARDS`), read from source.

`reference/scripts_dump/213_Bambo_Reward.rb` is the single source of truth
for what each rung of the ladder pays out (CLAUDE.md §4.3). This module
parses that table; it does not re-implement the Ruby that walks it.

The distinction this module exists to make (C8 stage 7, assignment task 1):

* `jvNextReward` reads `$Trainer.pokedexOwned` to decide whether the player
  has EARNED the next rung. That is a dex quantity, which ruling (b)
  deliberately declines to model, so it refuses `party_model` and must keep
  refusing.
* `jvGiveReward` reads only `$game_variables[22]` (the claimed-rung index)
  and `$game_switches[59/60/61]` (the starter choice). Both are ordinary
  modelled state, so what it pays out IS knowable -- which is why the
  blanket `non_literal_args` refusal it carries today is wrong.

Parsing note: `parse_program` refuses `PROFREWARDS=[...]` outright --
assignment to a capitalised Ruby constant is deliberately outside the shared
subset (a Ruby constant is not game state the interpreter models). This
module isolates the bracketed array literal by bracket-depth scanning and
hands *that* substring to `parse_expression`, which parses a bare array
literal fine.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rpg2gba.ruby_subset import RubyParseError, ast, parse_expression

_SOURCE_FILENAME = "213_Bambo_Reward.rb"
_CONST_NAME = "PROFREWARDS"
_DEFAULT_SCRIPTS_DUMP_DIR = Path(__file__).resolve().parents[3] / "reference" / "scripts_dump"


@dataclass(frozen=True)
class Rung:
    """One entry of `PROFREWARDS`.

    `index` is the position in the table, which is what `$game_variables[22]`
    holds. `threshold` is the `pokedexOwned` count `jvNextReward` compares
    against -- carried for completeness, never consulted here (see the module
    docstring on why this module must not need it).

    An item rung carries one or more item symbols in `items` (index 5 pays
    two) and `species is None`. An egg rung carries `is_egg=True` and either
    a species symbol or the literal `"starter"` sentinel in `species`.
    """

    index: int
    threshold: int
    items: tuple[str, ...] = ()
    species: str | None = None
    is_egg: bool = False


def _isolate_array_literal(source: str, const_name: str) -> str:
    """The bracketed literal assigned to `const_name` (e.g. `PROFREWARDS=[...]`),
    isolated by bracket-depth scanning so it can be handed to
    `parse_expression` on its own (`parse_program` refuses the constant
    assignment itself; see the module docstring)."""
    marker = f"{const_name}="
    start = source.find(marker)
    if start == -1:
        raise ValueError(f"{const_name!r} assignment not found in source")
    bracket_start = source.find("[", start)
    if bracket_start == -1:
        raise ValueError(f"{const_name!r} assignment has no array literal")
    depth = 0
    for i in range(bracket_start, len(source)):
        ch = source[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return source[bracket_start:i + 1]
    raise ValueError(f"{const_name!r} array literal never closes")


def _rung_from_node(index: int, node: ast.Node) -> Rung:
    if not isinstance(node, ast.ArrayLit):
        raise ValueError(f"{_CONST_NAME}[{index}] is not an array literal: {node!r}")
    elements = node.elements
    if not elements:
        raise ValueError(f"{_CONST_NAME}[{index}] is empty")
    threshold_node = elements[0]
    if not isinstance(threshold_node, ast.Int):
        raise ValueError(
            f"{_CONST_NAME}[{index}][0] is not an integer literal: {threshold_node!r}"
        )
    threshold = threshold_node.value

    items: list[str] = []
    species: str | None = None
    is_egg = False
    for element in elements[1:]:
        if isinstance(element, ast.ScopedConst):
            scope = element.scope
            scope_name = scope.name if isinstance(scope, ast.Const) else None
            if scope_name == "PBItems":
                items.append(element.name)
            elif scope_name == "PBSpecies":
                species = element.name
                is_egg = True
            else:
                raise ValueError(
                    f"{_CONST_NAME}[{index}]: unrecognized scoped const "
                    f"{scope_name}::{element.name}"
                )
        elif isinstance(element, ast.Str):
            if element.value != "starter":
                raise ValueError(
                    f"{_CONST_NAME}[{index}]: unexpected string literal {element.value!r}"
                )
            species = "starter"
            is_egg = True
        else:
            raise ValueError(f"{_CONST_NAME}[{index}]: unrecognized element {element!r}")

    return Rung(
        index=index, threshold=threshold, items=tuple(items), species=species, is_egg=is_egg,
    )


def load_profrewards(scripts_dump_dir: Path | None = None) -> tuple[Rung, ...]:
    """The `PROFREWARDS` table, parsed from the vendored Ruby source.

    `scripts_dump_dir` defaults to the repo's `reference/scripts_dump/`.

    Raises `FileNotFoundError` if the source is missing and `ValueError` if
    the array literal cannot be parsed -- a silently empty ladder would turn
    every rung into a no-op and the floor would under-assert without saying
    so (CLAUDE.md §4.5).

    Uses `ruby_subset.parse_expression` on the isolated bracketed literal;
    the table is a Ruby array literal of array literals, and this repo has a
    parser for exactly that (see the module docstring on why `parse_program`
    itself can't be used directly).
    """
    directory = scripts_dump_dir if scripts_dump_dir is not None else _DEFAULT_SCRIPTS_DUMP_DIR
    path = directory / _SOURCE_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"{path}: {_CONST_NAME} source not found")
    source = path.read_text(encoding="utf-8")
    literal = _isolate_array_literal(source, _CONST_NAME)
    try:
        node = parse_expression(literal)
    except RubyParseError as exc:
        raise ValueError(f"{path}: {_CONST_NAME} literal did not parse: {exc}") from exc
    if not isinstance(node, ast.ArrayLit):
        raise ValueError(f"{path}: {_CONST_NAME} is not an array literal")
    return tuple(_rung_from_node(i, element) for i, element in enumerate(node.elements))


def rungs_for_variable(
    rungs: tuple[Rung, ...], values: frozenset[int] | None = None
) -> tuple[Rung, ...]:
    """The rungs that could fire, given what is known about variable 22.

    `values is None` means "unconstrained": every reachable rung is possible.
    An explicit set narrows to those indices.

    Index 0 pays nothing and index 11 is the original author's crash
    workaround (`[999]`, unreachable in play) -- decide what this returns for
    each and document it.

    Note this returns CANDIDATES, not a decision. Widening is safe here;
    turning a plural candidate set into floor assertions is NOT (see the task
    file's R2 -- the floor is a conjunction, and several same-key grant
    assertions contradict each other). Narrowing to a set of two is still a
    set of two.
    """
    if values is None:
        return tuple(rungs)
    return tuple(r for r in rungs if r.index in values)
