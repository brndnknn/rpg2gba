"""Phase 2 §2.9 — `tmpbs.dat` (Uranium-custom per-species extra moves) → C table.

Source (under `$RPG2GBA_URANIUM_SRC/Data/`):
  tmpbs.dat — indexed binary, identical layout to eggEmerald.dat: a
  `species_count × 8`-byte header of (uint32 offset, uint32 length) pairs
  (length = element count), then per-species bodies of single uint16 move IDs
  (Compiler.rb ~2595-2609). Reused via `pokemon.parse_indexed_u16_list`.

TMPBS is a Uranium-original auxiliary move list per species; its exact semantics
(broad TM compatibility vs move-reminder pool) are still open — see MEMORY.md
Open Questions. Phase 2 extracts it faithfully as a per-species extra-moves
table and emits `uranium_tmpbs.h` in the egg-move array style (each list
terminated by `MOVE_UNAVAILABLE`), carrying a TODO banner. `MOVE_*` constants
resolve through the shared `to_constant`/IdMap rule (idempotent vs §2.2);
species names key the arrays via `reference/species_internal_names.json`.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from ._c_emit import generated_banner
from ._id_map import IdMap
from ._naming import load_fork_constants, to_constant
from .pokemon import parse_dexdata, parse_indexed_u16_list

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.pbs_converter.tmpbs"


def _load_id_json(path: Path) -> dict[int, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


@dataclass
class _Resolver:
    """Resolves move ids → `MOVE_*` (mirrors pokemon.py's move_constant)."""

    id_map: IdMap
    move_internal: dict[int, str]
    move_names: dict[int, str]
    fork_moves: set[str]

    def move_constant(self, move_id: int) -> str:
        if move_id == 0:
            return "MOVE_NONE"
        internal = self.move_internal.get(move_id)
        if internal is None:
            raise ValueError(f"move id {move_id} absent from move_internal_names.json")
        const = to_constant("MOVE", self.move_names.get(move_id) or internal)
        needs = bool(self.fork_moves) and const not in self.fork_moves
        self.id_map.add("moves", internal, const, needs_engine=needs)
        return const


def _build_resolver(id_map: IdMap, ref: Path) -> _Resolver:
    fork_env = os.environ.get("RPG2GBA_POKEEMERALD")
    fork = Path(fork_env) if fork_env else None
    fork_moves = (
        load_fork_constants(fork / "include/constants/moves.h", "MOVE") if fork else set()
    )
    return _Resolver(
        id_map=id_map,
        move_internal=_load_id_json(ref / "move_internal_names.json"),
        move_names=_load_id_json(ref / "move_names.json"),
        fork_moves=fork_moves,
    )


def _symbol(internal: str) -> str:
    return f"sUraniumTMPBS_{internal}"


def emit_header(
    tmpbs: list[list[int]], species_internal: dict[int, str], r: _Resolver
) -> str:
    """Emit `uranium_tmpbs.h`: one MOVE_* array per species with a non-empty list."""
    blocks: list[str] = []
    for species_id, moves in enumerate(tmpbs):
        if species_id == 0 or not moves:
            continue
        internal = species_internal.get(species_id)
        if internal is None:
            raise ValueError(f"species id {species_id} has TMPBS moves but no internal name")
        rows = [f"    {r.move_constant(mv)}," for mv in moves]
        blocks.append(
            f"static const u16 {_symbol(internal)}[] = {{\n"
            + "\n".join(rows)
            + "\n    MOVE_UNAVAILABLE,\n};"
        )
    banner = generated_banner("tmpbs.dat", GENERATOR, timestamp=False)
    todo = "// TODO: confirm tmpbs semantics — see MEMORY.md Open Questions\n"
    body = "\n\n".join(blocks) + "\n" if blocks else ""
    return banner + todo + "\n" + body


def run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None:
    """Phase 2 §2.9 entry point: parse tmpbs.dat and emit uranium_tmpbs.h."""
    data = uranium_src / "Data"
    species = parse_dexdata(data / "dexdata.dat")
    species_count = len(species) - 1
    tmpbs = parse_indexed_u16_list(data / "tmpbs.dat", species_count)

    ref = _reference_dir()
    species_internal = _load_id_json(ref / "species_internal_names.json")
    r = _build_resolver(id_map, ref)

    out_file = out_dir / "src" / "data" / "pokemon" / "uranium_tmpbs.h"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(emit_header(tmpbs, species_internal, r), encoding="utf-8")

    n = sum(1 for i, m in enumerate(tmpbs) if i != 0 and m)
    total = sum(len(m) for m in tmpbs)
    logger.info("emitted TMPBS for %d species (%d move entries)", n, total)
