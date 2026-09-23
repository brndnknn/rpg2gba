"""Shared embedded-Ruby subset: lexer, AST, parser, and evaluator
(REDERIVATION_PLAN.md C8). Replaces the five independent regex readers
CLAUDE.md Sec4.3 lists (`story_state/extract.py`, `transpiler.py`'s
`_RubyLocal`/array/argmax, `beat_floor/script.py`, `beat_floor/condition.py`,
`chapter_manifest/conditions.py`) with one grammar and one concrete
evaluator. Stage 1 (`lexer.py`/`ast.py`/`parser.py`) is syntax-only; stage 2
(`evaluate.py`/`builtins.py`) runs a parsed program or expression
concretely against a caller-supplied `Oracle`.
"""
from __future__ import annotations

from rpg2gba.ruby_subset import ast, builtins
from rpg2gba.ruby_subset.evaluate import (
    ConstRef,
    Effect,
    EvalResult,
    FixedOracle,
    InputSource,
    Opaque,
    Oracle,
    RubyRefusal,
    StateWrite,
    Symbol,
    evaluate_expression,
    evaluate_program,
)
from rpg2gba.ruby_subset.lexer import RubyParseError
from rpg2gba.ruby_subset.parser import (
    parse_expression,
    parse_program,
    script_block_source,
)
from rpg2gba.ruby_subset.search import (
    Choice,
    SearchResult,
    load_stripped_ce_ids,
    search_scope,
)

__all__ = [
    "ast",
    "builtins",
    "parse_expression",
    "parse_program",
    "script_block_source",
    "RubyParseError",
    "ConstRef",
    "Effect",
    "EvalResult",
    "FixedOracle",
    "InputSource",
    "Opaque",
    "Oracle",
    "RubyRefusal",
    "StateWrite",
    "Symbol",
    "evaluate_expression",
    "evaluate_program",
    "Choice",
    "SearchResult",
    "load_stripped_ce_ids",
    "search_scope",
]
