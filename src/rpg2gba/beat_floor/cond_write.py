"""Conditional state writes: check the write the ROM's inputs select.

`story_state` marks a write `conditional` when it lands on only some runs of
the row -- the canonical case is the lab rival scene's starter flags:

    $game_switches[61] = true if $game_variables[151]==1
    $game_switches[59] = true if $game_variables[151]==2
    $game_switches[60] = true if $game_variables[151]==3

Exactly one of the three is set, chosen by the starter pick in var 151. The
floor used to assert all three as certain (ROM run 33 failed on switch 60
after the ROM correctly set 59). Same shape as ruling 18's `var_text`: the
floor keeps the script block and the variables it reads, and at run time the
ROM's own values for those variables are fed to the Ruby-subset evaluator;
only the keys that evaluation writes are checked. A key the evaluation leaves
alone is not checked -- the floor has no "before" value for it.

A block qualifies only if it parses, consults no player input, and reads
nothing but game variables. Anything else stays refused by name
(`conditional_state_write`) rather than asserted as if it always happened.
"""
from __future__ import annotations

from collections.abc import Mapping

from rpg2gba.beat_floor.var_text import _RecordingOracle
from rpg2gba.ruby_subset import parse_program
from rpg2gba.ruby_subset.evaluate import FixedOracle, evaluate_program
from rpg2gba.ruby_subset.lexer import RubyParseError
from rpg2gba.story_state.state import Key, Variable


def cond_write_inputs(script: str) -> tuple[int, ...] | None:
    """The game variables `script` reads, sorted, if the block qualifies
    (module docstring); else None."""
    oracle = _RecordingOracle()
    try:
        result = evaluate_program(parse_program(script), oracle=oracle, event=None)
    except (ValueError, RubyParseError):
        return None
    if result.refusal is not None:
        return None
    if any(not isinstance(k, Variable) for k in oracle.keys):
        return None
    return tuple(sorted({k.id for k in oracle.keys}))


def evaluated_writes(script: str, inputs: Mapping[int, int]) -> dict[Key, object]:
    """Every key `script` writes for these variable values, last write
    winning. Raises ValueError if the evaluator refuses."""
    result = evaluate_program(
        parse_program(script),
        oracle=FixedOracle(reads={Variable(k): v for k, v in inputs.items()}),
        event=None,
    )
    if result.refusal is not None:
        raise ValueError(f"script refused: {result.refusal.code}")
    return {w.key: w.value for w in result.writes}
