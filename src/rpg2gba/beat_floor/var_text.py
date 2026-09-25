"""`\\v[N]` dialogue: predict the line from the page's own Ruby
(REDERIVATION_PLAN.md §16.3 ruling 18).

RMXP substitutes variable N into the message at display time. The catch
ceremony's "Go! \\v[3]!" is the canonical case: var 3 is set two lines up by
`list[x]` over the three starters, with `x` read from var 151 and remapped.
It names neither the player's starter nor the rival's.

The floor keeps the unsubstituted fragments plus the script block that
writes var N, and at run time the ROM's own values for the script's input
variables are fed to the Ruby-subset evaluator (`expected_var_text`). That
reproduces the source's logic independently of the transpiler's emitted
branches (`transpiler._emit_value_var_text`), which is the point: a wrong
remap there shows up as a mismatch here.

A line qualifies only if it holds exactly one `\\v[N]` and the nearest
earlier script block in the same scope parses, reads nothing but game
variables, and writes a string to var N. Anything else stays refused
(`text_unnormalizable`).
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from rpg2gba.conversion_agent.deterministic import join_text_lines, translate_text_codes
from rpg2gba.playtest.text_source import _char_canon_table, _default_engine_dir, rom_text
from rpg2gba.ruby_subset import parse_program
from rpg2gba.ruby_subset.evaluate import FixedOracle, InputSource, evaluate_program
from rpg2gba.ruby_subset.lexer import RubyParseError
from rpg2gba.story_state.state import Key, Variable

_VALUE_VAR_RE = re.compile(r"\\[vV]\[(\d+)\]")


class _RecordingOracle(FixedOracle):
    """Answers every read with the default and remembers what was read."""

    def __init__(self) -> None:
        super().__init__()
        self.keys: list[Key] = []

    def read(self, key: Key) -> object:
        self.keys.append(key)
        return super().read(key)

    def choose(self, source: InputSource) -> object:
        raise ValueError(f"script consults a player input ({source.detail})")


def _written_value(script: str, var_id: int, oracle: FixedOracle) -> object:
    result = evaluate_program(parse_program(script), oracle=oracle, event=None)
    if result.refusal is not None:
        raise ValueError(f"script refused: {result.refusal.code}")
    values = [w.value for w in result.writes if w.key == Variable(var_id)]
    if len(values) != 1:
        raise ValueError(f"script writes var {var_id} {len(values)} times")
    return values[0]


def var_text_source(
    fragments: Sequence[str], earlier_scripts: Sequence[str],
) -> tuple[int, str, tuple[int, ...]] | None:
    """`(var_id, script, input_vars)` if `fragments` is a qualifying
    `\\v[N]` line (module docstring), else None. `earlier_scripts` are the
    scope's script blocks before this message, oldest first."""
    ids = _VALUE_VAR_RE.findall(join_text_lines(list(fragments)))
    if len(ids) != 1:
        return None
    var_id = int(ids[0])
    for script in reversed(earlier_scripts):
        if f"$game_variables[{var_id}]" not in script and f"pbSet({var_id}" not in script:
            continue
        oracle = _RecordingOracle()
        try:
            value = _written_value(script, var_id, oracle)
        except (ValueError, RubyParseError):
            return None
        if not isinstance(value, str) or any(not isinstance(k, Variable) for k in oracle.keys):
            return None
        inputs = tuple(sorted({k.id for k in oracle.keys}))
        return var_id, script, inputs
    return None


def expected_var_text(
    fragments: Sequence[str], var_id: int, script: str, inputs: Mapping[int, int],
) -> str:
    """The ROM-comparable line for these input variable values."""
    value = _written_value(script, var_id,
                           FixedOracle(reads={Variable(k): v for k, v in inputs.items()}))
    joined = _VALUE_VAR_RE.sub(lambda m: str(value), join_text_lines(list(fragments)))
    translated = translate_text_codes(joined)
    if translated is None:
        raise ValueError(f"unrecognized control code in {joined!r}")
    return rom_text(translated.text, _char_canon_table(_default_engine_dir()))
