"""Can a chapter white out? (REDERIVATION_PLAN.md §16.3 ruling 15.)

`Kernel.pbStartOver` runs only after a lost battle that was not allowed to be
lost. A chapter can therefore white out only if one of its maps has either:

- a wild encounter table (land, water or fishing: `wild_encounters.json`'s
  `maps` entry), or
- a battle call whose `canlose` argument is absent or Ruby-falsy.

`canlose` sits at a different position in each battle helper, read from
Uranium's own signatures below. Ruby truthiness applies: only `false` and
`nil` are falsy, so a literal `0` means the battle *can* be lost (the body
tests `if canlose`). Strip-listed map events are skipped, since their battles
never reach the ROM. A battle call whose `canlose` is not a literal fails
loud (CLAUDE.md §4.5), as does a script block the Ruby subset can't parse
that names a battle helper.
"""
from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from rpg2gba.ruby_subset import ast, parse_expression, parse_program
from rpg2gba.ruby_subset.lexer import RubyParseError
from rpg2gba.ruby_subset.parser import script_block_source

# Zero-based position of `canlose` per helper (default false in every one):
#   pbTrainerBattle(trainerid,trainername,endspeech,doublebattle=false,
#                   trainerparty=0,canlose=false,...)  115_PTrainer_NPCTrainers.rb:358
#   pbDoubleTrainerBattle(id1,name1,party1,speech1,id2,name2,party2,speech2,
#                         canlose=false,...)          115_PTrainer_NPCTrainers.rb:240
#   pbWildBattle(species,level,variable=nil,canescape=true,canlose=false,...)
#                                                     101__PField_Field.rb:1097
#   pbDoubleWildBattle(sp1,lv1,sp2,lv2,variable=nil,canescape=true,
#                      canlose=false,...)             101__PField_Field.rb:1175
#   customTrainerBattle(trainer,endspeech,doublebattle=false,canlose=false)
#                                                     216_Custom_Trainers.rb:65
CANLOSE_ARG_INDEX: dict[str, int] = {
    "pbTrainerBattle": 5,
    "pbDoubleTrainerBattle": 8,
    "pbWildBattle": 4,
    "pbDoubleWildBattle": 6,
    "customTrainerBattle": 3,
}

_ENCOUNTER_KINDS = ("land_mons", "water_mons", "fishing_mons")
_SCRIPT_CODE = 355
_CONDITION_CODE = 111
_SCRIPT_CONDITION_TYPE = 12


def _nodes(node: object) -> Iterator[ast.Node]:
    """Every AST node under `node`, depth first."""
    if isinstance(node, ast.Node):
        yield node
        for f in dataclasses.fields(node):
            yield from _nodes(getattr(node, f.name))
    elif isinstance(node, tuple):
        for item in node:
            yield from _nodes(item)


def _can_lose(arg: ast.Node | None, where: str) -> bool:
    if arg is None:
        return False  # the default
    if isinstance(arg, ast.Bool):
        return arg.value
    if isinstance(arg, ast.Nil):
        return False
    if isinstance(arg, (ast.Int, ast.Float, ast.Str, ast.Sym)):
        return True  # Ruby: every literal but false/nil is truthy
    raise ValueError(f"{where}: canlose argument is not a literal ({arg!r})")


def losable_battle_sites(source: str, where: str, *, program: bool) -> list[str]:
    """`where` labels for every battle call in `source` that can white out."""
    if not any(name in source for name in CANLOSE_ARG_INDEX):
        return []
    try:
        tree = parse_program(source) if program else parse_expression(source)
    except RubyParseError as exc:
        raise ValueError(f"{where}: can't parse a battle call: {exc}") from exc
    sites = []
    for node in _nodes(tree):
        if isinstance(node, ast.Call) and node.name in CANLOSE_ARG_INDEX:
            idx = CANLOSE_ARG_INDEX[node.name]
            arg = node.args[idx] if idx < len(node.args) else None
            if not _can_lose(arg, where):
                sites.append(f"{where}: {node.name}")
    return sites


def _page_sites(commands: list[dict[str, Any]], where: str) -> list[str]:
    sites: list[str] = []
    i = 0
    while i < len(commands):
        cmd = commands[i]
        code = cmd.get("code")
        params = cmd.get("parameters") or []
        if code == _SCRIPT_CODE:
            source, nxt = script_block_source(commands, i)
            sites += losable_battle_sites(source, f"{where}@{i}", program=True)
            i = nxt
            continue
        if (code == _CONDITION_CODE and len(params) >= 2
                and params[0] == _SCRIPT_CONDITION_TYPE and isinstance(params[1], str)):
            sites += losable_battle_sites(params[1], f"{where}@{i}", program=False)
        i += 1
    return sites


def losable_battle_evidence(
    map_ids: set[int], build_dir: Path, stripped: set[tuple[int, int]],
) -> tuple[str, ...]:
    """Why a white-out is possible on `map_ids` (empty: it isn't)."""
    evidence: list[str] = []
    enc_path = build_dir / "intermediate" / "wild_encounters.json"
    encounters = json.loads(enc_path.read_text(encoding="utf-8"))["maps"]
    for map_id in sorted(map_ids):
        table = encounters.get(str(map_id), {})
        kinds = [k for k in _ENCOUNTER_KINDS if table.get(k)]
        if kinds:
            evidence.append(f"map{map_id:03d}: wild encounters ({', '.join(kinds)})")

        map_data = json.loads(
            (build_dir / "maps" / f"Map{map_id:03d}.json").read_text(encoding="utf-8"))
        for event in map_data.get("events", []):
            if (map_id, event["id"]) in stripped:
                continue
            for p, page in enumerate(event.get("pages", [])):
                where = f"map{map_id:03d}/ev{event['id']:03d}/p{p}"
                evidence += _page_sites(page.get("list") or [], where)
    return tuple(evidence)
