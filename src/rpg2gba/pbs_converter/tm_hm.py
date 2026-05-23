"""Phase 2 §2.5 — TM/HM compatibility from `tm.dat`.

Source (under `$RPG2GBA_URANIUM_SRC/Data/`):

  tm.dat    — Ruby Marshal (see `_marshal`): an array indexed by move id; each
              non-null entry is an Essentials `WordArray` of the species ids that
              can learn that move by TM/HM (Compiler.rb `pbCompileMachines`,
              ~1579-1638: `sections[move_id] = WordArray<species_id>`).
  tutor.dat — header-only / empty in Uranium (every species has a zero-length
              tutor list); asserted, nothing emitted.

The modern pokeemerald-expansion fork **build-generates** teachable learnsets
(`tools/learnset_helpers/make_teachables.py`) from
`src/data/pokemon/all_learnables.json` — a map of *species internal name* →
sorted list of `MOVE_*` the species can learn. So §2.5 does **not** hand-emit a
TM bitfield or `sXTeachableLearnset` arrays (MEMORY P4). It inverts `tm.dat`
(move→species) into that same shape and emits
`intermediate/uranium_tm_learnables.json`; V6 integration merges it into the
fork's `all_learnables.json` before the generator runs.

`MOVE_*` constants are minted through the shared `to_constant` rule + IdMap, so
they match the ones §2.2 emitted (idempotent — `IdMap.add` fails loud on a
conflict). Species keys are the bare internal names (the all_learnables key
form), from `reference/species_internal_names.json`.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from ._binary import DatReader
from ._id_map import IdMap
from ._marshal import dump_dat, load_json
from ._naming import load_fork_constants, to_constant

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.pbs_converter.tm_hm"


def _load_id_json(path: Path) -> dict[int, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


def assert_tutor_empty(path: Path) -> None:
    """Fail loud unless every tutor.dat entry is zero-length (Uranium ships none).

    tutor.dat is the indexed `(uint32 offset, uint32 length)` header followed by
    per-species uint16 bodies. Uranium's file is header-only (all lengths 0). If
    a future release adds tutor data, this raises so §2.5 gets revisited rather
    than silently dropping it.
    """
    reader = DatReader(path)
    if reader.size % 8 != 0:
        raise ValueError(f"{path}: size {reader.size} is not a multiple of 8")
    count = reader.size // 8
    nonempty = []
    for i in range(1, count + 1):
        _offset = reader.dw()
        length = reader.dw()
        if length != 0:
            nonempty.append(i)
    if nonempty:
        raise ValueError(
            f"{path}: expected an empty tutor table, but species "
            f"{nonempty[:10]}{' (+more)' if len(nonempty) > 10 else ''} have tutor moves"
        )


@dataclass
class _Resolver:
    """Resolves move ids → `MOVE_*` and species ids → internal-name keys."""

    id_map: IdMap
    move_internal: dict[int, str]
    move_names: dict[int, str]
    species_internal: dict[int, str]
    fork_moves: set[str]

    def move_constant(self, move_id: int) -> str:
        internal = self.move_internal.get(move_id)
        if internal is None:
            raise ValueError(f"move id {move_id} absent from move_internal_names.json")
        const = to_constant("MOVE", self.move_names.get(move_id) or internal)
        needs = bool(self.fork_moves) and const not in self.fork_moves
        self.id_map.add("moves", internal, const, needs_engine=needs)
        return const

    def species_key(self, species_id: int) -> str:
        internal = self.species_internal.get(species_id)
        if internal is None:
            raise ValueError(f"species id {species_id} absent from species_internal_names.json")
        return internal


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
        species_internal=_load_id_json(ref / "species_internal_names.json"),
        fork_moves=fork_moves,
    )


def parse_tm(raw: object) -> dict[int, list[int]]:
    """Turn the deserialized tm.dat array into `{move_id: [species_id, ...]}`.

    Each non-null element is a `WordArray` (`{"__class__": "WordArray", "a": [...]}`)
    whose `a` is the species-id list for that move id (the array index).
    """
    if not isinstance(raw, list):
        raise ValueError(f"tm.dat: expected a top-level array, got {type(raw).__name__}")
    out: dict[int, list[int]] = {}
    for move_id, entry in enumerate(raw):
        if entry is None:
            continue
        if not (isinstance(entry, dict) and entry.get("__class__") == "WordArray"):
            raise ValueError(f"tm.dat: move id {move_id} is {entry!r}, expected a WordArray")
        out[move_id] = list(entry["a"])
    return out


def build_learnables(tm: dict[int, list[int]], r: _Resolver) -> dict[str, list[str]]:
    """Invert move→species into `{species_internal: sorted [MOVE_*, ...]}`."""
    learnables: dict[str, set[str]] = {}
    for move_id, species_ids in tm.items():
        const = r.move_constant(move_id)
        for sid in species_ids:
            learnables.setdefault(r.species_key(sid), set()).add(const)
    return {sp: sorted(moves) for sp, moves in sorted(learnables.items())}


def run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None:
    """Phase 2 §2.5 entry point: emit the TM/HM teachable-learnables sidecar."""
    data = uranium_src / "Data"
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True, exist_ok=True)

    raw = load_json(dump_dat(data / "tm.dat", inter / "tm_raw.json"))
    ref = _reference_dir()
    r = _build_resolver(id_map, ref)
    tm = parse_tm(raw)
    learnables = build_learnables(tm, r)

    # tutor.dat ships empty in Uranium (§2.1 finding); confirm and emit nothing.
    assert_tutor_empty(data / "tutor.dat")

    payload = {
        "_comment": (
            "Uranium TM/HM compatibility, in pokeemerald-expansion all_learnables.json "
            "form (species internal name -> learnable MOVE_*). V6 merges this into the "
            "fork's all_learnables.json; make_teachables.py then build-generates the "
            "teachable learnsets. tutor.dat is empty -> no tutor learnsets."
        ),
        "learnables": learnables,
    }
    (inter / "uranium_tm_learnables.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    moves = len(tm)
    pairs = sum(len(v) for v in learnables.values())
    logger.info(
        "emitted TM/HM learnables for %d species across %d machine moves (%d species-move "
        "pairs); tutor.dat empty",
        len(learnables),
        moves,
        pairs,
    )
