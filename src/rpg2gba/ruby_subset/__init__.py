"""Shared embedded-Ruby subset: lexer, AST, and parser (REDERIVATION_PLAN.md
C8 stage 1). Replaces the five independent regex readers CLAUDE.md Sec4.3
lists (`story_state/extract.py`, `transpiler.py`'s `_RubyLocal`/array/argmax,
`beat_floor/script.py`, `beat_floor/condition.py`,
`chapter_manifest/conditions.py`) with one grammar. This package is
syntax-only -- no evaluation (that's C8 stage 2, `ruby_subset/evaluate.py`).
"""
from __future__ import annotations

from rpg2gba.ruby_subset import ast
from rpg2gba.ruby_subset.lexer import RubyParseError
from rpg2gba.ruby_subset.parser import (
    parse_expression,
    parse_program,
    script_block_source,
)

__all__ = [
    "ast",
    "parse_expression",
    "parse_program",
    "script_block_source",
    "RubyParseError",
]
