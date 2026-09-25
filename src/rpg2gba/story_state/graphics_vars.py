"""Variables that only drive graphics (operator ruling 2026-09-25, REDERIVATION_PLAN.md
§16.3 "Graphics-only party reads").

Ruling (b) (C8 shape) refuses a row `party_model` when its script reads the
player's party. A Pokémon Center nurse's heal writes
`$game_variables[43]=$Trainer.party.length` and resets var 43 to 0 forty
frames later; the only readers of var 43 are the heal machine's two events
(Map068 events 5/6), whose pages have no commands and exist only to draw one
Poké Ball per party member. The operator ruled that such a read is exempt:
the write becomes an unknown value (havoc) for that variable, and the rest of
the row is modelled as usual.

A variable qualifies when, across the WHOLE decoded corpus (every map, every
common event, and Uranium's own Ruby scripts in `reference/scripts_dump/`),
it is read only by page conditions of pages with an empty command list. An
empty page can still change the event's passability or priority as well as
its graphic; that is accepted as part of "graphics". Every other read
counts, and so disqualifies the variable:

- a conditional branch on it (code 111 type 1, either operand),
- an arithmetic write to it or from it (code 122: a non-`=` op reads the
  target, a variable operand reads the source),
- a transfer/event-location/picture placed by variables (201/202/231/232),
- any `\\v[N]` in a string, and any `$game_variables[N]` or `pbGet(N)` in a
  string that isn't the left side of a plain `=` assignment -- this covers
  script blocks, script conditions and move-route scripts alike, because
  every string in a command's parameters is scanned.

A read through a named constant in the Ruby scripts (`$game_variables[FOO]`)
can't be resolved here; the scripts dump uses literal indices for the
variables this exemption currently covers.
"""
from __future__ import annotations

import functools
import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

__all__ = ["graphics_only_variables", "scan_graphics_only_variables"]

_REPO_ROOT = Path(__file__).resolve().parents[3]

_VAR_REF = re.compile(r"\$game_variables\[\s*(\d+)\s*\]|pbGet\(\s*(\d+)\s*\)")
_VAR_ASSIGN = re.compile(r"\$game_variables\[\s*(\d+)\s*\]\s*=(?!=)")
_TEXT_VAR = re.compile(r"\\[vV]\[\s*(\d+)\s*\]")


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def _string_reads(text: str) -> set[int]:
    assigned = {m.start() for m in _VAR_ASSIGN.finditer(text)}
    reads = {int(m.group(1) or m.group(2)) for m in _VAR_REF.finditer(text)
             if m.start() not in assigned}
    reads |= {int(m.group(1)) for m in _TEXT_VAR.finditer(text)}
    return reads


def _command_reads(cmd: dict[str, Any]) -> set[int]:
    code, p = cmd.get("code"), cmd.get("parameters") or []
    reads: set[int] = set()
    if code == 111 and p and p[0] == 1:
        reads.add(p[1])
        if len(p) > 3 and p[2] != 0:
            reads.add(p[3])
    elif code == 122 and len(p) >= 5:
        if p[2] != 0:                          # +=, -=, ... read the target
            reads.update(range(p[0], p[1] + 1))
        if p[3] == 1:                          # operand is a variable
            reads.add(p[4])
    elif code == 201 and len(p) >= 4 and p[0] == 1:
        reads.update(p[1:4])
    elif code == 202 and len(p) >= 4 and p[1] == 1:
        reads.update(p[2:4])
    elif code in (231, 232) and len(p) >= 6 and p[3] == 1:
        reads.update(p[4:6])
    for text in _strings(p):
        reads |= _string_reads(text)
    return reads


def _list_reads(commands: Iterable[dict[str, Any]]) -> set[int]:
    reads: set[int] = set()
    for cmd in commands:
        reads |= _command_reads(cmd)
    return reads


def scan_graphics_only_variables(
    maps: Iterable[dict[str, Any]], common_events: Iterable[dict[str, Any]],
    ruby_sources: Iterable[str] = (),
) -> frozenset[int]:
    """The variables read only by page conditions of empty pages (module
    docstring), from already-loaded map dicts, common events and Ruby
    sources."""
    cosmetic: set[int] = set()
    reads: set[int] = set()
    for map_data in maps:
        for event in map_data.get("events", []):
            for page in event.get("pages", []):
                commands = page.get("list") or []
                cond = page.get("condition") or {}
                if cond.get("variable_valid"):
                    empty = all(c.get("code") == 0 for c in commands)
                    (cosmetic if empty else reads).add(cond["variable_id"])
                reads |= _list_reads(commands)
    for ce in common_events:
        reads |= _list_reads(ce.get("list") or [])
    for source in ruby_sources:
        reads |= _string_reads(source)
    return frozenset(cosmetic - reads)


@functools.cache
def graphics_only_variables(build_dir: Path | None = None) -> frozenset[int]:
    """`scan_graphics_only_variables` over the decoded build
    (`output/uranium-build/` by default) and the scripts dump. Empty when the
    build has no decoded maps -- no exemption without the corpus to prove it."""
    from rpg2gba.beat_floor.lookup import default_build_dir

    root = Path(build_dir) if build_dir is not None else default_build_dir()
    map_paths = sorted((root / "maps").glob("Map*.json"))
    ce_path = root / "common_events.json"
    if not map_paths or not ce_path.is_file():
        return frozenset()
    maps = (json.loads(p.read_text(encoding="utf-8")) for p in map_paths)
    common_events = json.loads(ce_path.read_text(encoding="utf-8"))
    scripts = sorted((_REPO_ROOT / "reference" / "scripts_dump").glob("*.rb"))
    ruby = (p.read_text(encoding="utf-8", errors="replace") for p in scripts)
    return scan_graphics_only_variables(maps, [ce for ce in common_events if ce], ruby)
