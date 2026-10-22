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


# --- count lines (#144) -------------------------------------------------------
#
# Bambo's lab lines show numbers, not script-built strings: "seen \r\v[2]\c[0]
# Pokémon and caught \r\v[3]\c[0]" after `pbSet(2, $Trainer.pokedexSeen)` /
# `pbSet(3, $Trainer.pokedexOwned)`, and "When you catch \r\v[1]\c[0] Pokémon"
# after `pbSet(1, PROFREWARDS[pbGet(22)+1][0])`. The transpiler emits them with
# `ScriptGetPokedexInfo` + `buffernumberstring` (`_emit_numeric_var_text`). The
# floor predicts each number independently of that: the dex counts from the
# ROM's seen/caught flags (`Emulator.pokedex_counts`), a threshold from the
# parsed `PROFREWARDS` table (`reward_ladder`) at the ROM's rung variable.

_DEX_SEEN_RE = re.compile(r"^\s*(?:Kernel\.)?pbSet\(\s*(\d+)\s*,\s*\$Trainer\.pokedexSeen\s*\)\s*$")
_DEX_OWNED_RE = re.compile(r"^\s*(?:Kernel\.)?pbSet\(\s*(\d+)\s*,\s*\$Trainer\.pokedexOwned\s*\)\s*$")
_THRESHOLD_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbSet\(\s*(\d+)\s*,\s*PROFREWARDS\[\s*pbGet\(\s*(\d+)\s*\)\s*\+\s*1\s*\]\[0\]\s*\)\s*$")
#: The red tint Uranium wraps a shown number in: `\r` before it, `\c[0]` after.
_TINT_BEFORE_VAR_RE = re.compile(r"\\r(?=\\[vV]\[\d+\])")
_BLUE_RE = re.compile(r"\\[bB]")
_COLOUR_RE = re.compile(r"\\C\[\d+\]")


def _count_source(script: str, var_id: int) -> tuple[str, int] | None:
    """`("dex_seen"|"dex_owned", 0)` or `("rung_threshold", rung_var)` if one
    line of `script` writes var `var_id` from that count, else None."""
    for line in script.splitlines():
        for kind, rx in (("dex_seen", _DEX_SEEN_RE), ("dex_owned", _DEX_OWNED_RE)):
            m = rx.match(line)
            if m and int(m.group(1)) == var_id:
                return kind, 0
        m = _THRESHOLD_RE.match(line)
        if m and int(m.group(1)) == var_id:
            return "rung_threshold", int(m.group(2))
    return None


def count_text_source(
    fragments: Sequence[str], earlier_scripts: Sequence[str],
) -> tuple[tuple[int, str, int], ...] | None:
    """`((var_id, kind, arg), ...)` for a line whose every `\\v[N]` holds a
    count (see above), each found in the nearest earlier script block that
    writes var N; None if any `\\v[N]` has no such source."""
    ids = list(dict.fromkeys(int(i) for i in _VALUE_VAR_RE.findall(join_text_lines(list(fragments)))))
    if not ids or len(ids) > 3:
        return None
    sources: list[tuple[int, str, int]] = []
    for var_id in ids:
        found = None
        for script in reversed(earlier_scripts):
            if f"pbSet({var_id}" not in script.replace(" ", ""):
                continue
            found = _count_source(script, var_id)
            break
        if found is None:
            return None
        sources.append((var_id, *found))
    return tuple(sources)


def expected_count_text(fragments: Sequence[str], values: Mapping[int, int]) -> str:
    """The ROM-comparable line with each `\\v[N]` replaced by `values[N]`, the
    tint dropped as the transpiler drops it."""
    joined = _TINT_BEFORE_VAR_RE.sub("", join_text_lines(list(fragments)))
    joined = _VALUE_VAR_RE.sub(lambda m: str(values[int(m.group(1))]), joined)
    joined = _COLOUR_RE.sub("", _BLUE_RE.sub("", joined)).strip()
    translated = translate_text_codes(joined)
    if translated is None:
        raise ValueError(f"unrecognized control code in {joined!r}")
    return rom_text(translated.text, _char_canon_table(_default_engine_dir()))
