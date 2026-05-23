"""Phase 2 §2.6 — trainers + trainer classes from `trainers.dat`/`trainertypes.dat`.

Both are Ruby Marshal (D2; deserialized via `_marshal.dump_dat`).

`trainertypes.dat` — array of records (CSV schema `unsUSSSeU`, Compiler.rb:1334):
  [id, internal_name, display_name, base_money, battle_bgm, win_bgm, intro_bgm,
   gender(0=Male/1=Female/2=Mixed), skill/AI]

`trainers.dat` — array of `[class_id, name, items, party, party_id]`
(Compiler.rb `pbCompileTrainers`:1525). Each party mon is a 17-slot array indexed
by the TP* constants (115_PTrainer_NPCTrainers.rb:1-17):
  TPSPECIES=0 TPLEVEL=1 TPITEM=2 TPMOVE1..4=3..6 TPABILITY=7 TPGENDER=8 TPFORM=9
  TPSHINY=10 TPNATURE=11 TPIV=12 TPHAPPINESS=13 TPNAME=14 TPSHADOW=15 TPBALL=16
A trainer's identity is (class_id, name, party_id) (NPCTrainers.rb:36).

Emit form (reconciled from the plan's `trainers.h`): the modern fork
**build-generates** `src/data/trainers.h` from `data/trainers.party` via
`trainerproc`, so Phase 2 does not hand-write that C. Instead — as with §2.5 —
this extracts faithful, constants-keyed intermediate JSON
(`intermediate/trainers.json`, `intermediate/trainer_types.json`); V6 generates
the `.party` DSL from it. `TRAINER_*` / `TRAINER_CLASS_*` are minted through the
IdMap (the single source of truth); party species/moves/items resolve to the
same `SPECIES_*`/`MOVE_*`/`ITEM_*` constants §2.1–§2.3 minted (idempotent).

Custom runtime trainers (script 216) are Phase 4 conversion-agent work, not here
(MEMORY 2026-05-15). Shadow Pokémon are confirmed absent (0 `TPSHADOW`); the
parser asserts that invariant and fails loud if it ever changes.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from ._id_map import IdMap
from ._marshal import dump_dat, load_json
from ._naming import load_fork_constants, to_constant

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.pbs_converter.trainers"

# TP* party-mon slot indices (115_PTrainer_NPCTrainers.rb).
TPSPECIES, TPLEVEL, TPITEM = 0, 1, 2
TPMOVES = (3, 4, 5, 6)
TPABILITY, TPGENDER, TPFORM, TPSHINY, TPNATURE = 7, 8, 9, 10, 11
TPIV, TPHAPPINESS, TPNAME, TPSHADOW, TPBALL = 12, 13, 14, 15, 16
_MON_SLOTS = 17

_GENDER_NAMES = {0: "Male", 1: "Female", 2: "Mixed"}


@dataclass
class TrainerType:
    id: int
    internal_name: str
    display_name: str
    base_money: int
    battle_bgm: str | None
    win_bgm: str | None
    intro_bgm: str | None
    gender: int
    skill: int


@dataclass
class TrainerMon:
    species: int
    level: int
    item: int
    moves: list[int]          # nonzero custom moves only
    ability_flag: int | None  # ability SLOT selector (0/1/2-5), not an ability id
    gender: int | None
    form: int
    shiny: bool
    nature: int | None
    iv: int
    happiness: int
    nickname: str | None
    ball: int


@dataclass
class Trainer:
    index: int                # array position = the de-facto Uranium trainer id
    class_id: int
    name: str
    items: list[int]
    party_id: int
    party: list[TrainerMon] = field(default_factory=list)


def parse_trainer_types(raw: object) -> list[TrainerType]:
    if not isinstance(raw, list):
        raise ValueError("trainertypes.dat: expected a top-level array")
    out: list[TrainerType] = []
    for rec in raw:
        if rec is None:
            continue
        if not isinstance(rec, list) or len(rec) < 9:
            raise ValueError(f"trainertypes.dat: bad record {rec!r} (expected >=9 fields)")
        out.append(
            TrainerType(
                id=rec[0],
                internal_name=rec[1],
                display_name=rec[2],
                base_money=rec[3],
                battle_bgm=rec[4],
                win_bgm=rec[5],
                intro_bgm=rec[6],
                gender=rec[7],
                skill=rec[8],
            )
        )
    return out


def _parse_mon(rec: list, where: str) -> TrainerMon:
    if not isinstance(rec, list) or len(rec) != _MON_SLOTS:
        raise ValueError(
            f"{where}: party mon has {len(rec) if isinstance(rec, list) else '?'} "
            f"slots, expected {_MON_SLOTS}"
        )
    if rec[TPSHADOW]:
        raise ValueError(f"{where}: TPSHADOW set — Shadow Pokémon were assumed absent (MEMORY)")
    moves = [rec[i] for i in TPMOVES if rec[i]]
    return TrainerMon(
        species=rec[TPSPECIES],
        level=rec[TPLEVEL],
        item=rec[TPITEM] or 0,
        moves=moves,
        ability_flag=rec[TPABILITY],
        gender=rec[TPGENDER],
        form=rec[TPFORM] or 0,
        shiny=bool(rec[TPSHINY]),
        nature=rec[TPNATURE],
        iv=rec[TPIV] if rec[TPIV] is not None else 0,
        happiness=rec[TPHAPPINESS] if rec[TPHAPPINESS] is not None else 0,
        nickname=rec[TPNAME],
        ball=rec[TPBALL] or 0,
    )


def parse_trainers(raw: object) -> list[Trainer]:
    if not isinstance(raw, list):
        raise ValueError("trainers.dat: expected a top-level array")
    out: list[Trainer] = []
    for index, rec in enumerate(raw):
        if rec is None:
            continue
        if not isinstance(rec, list) or len(rec) != 5:
            raise ValueError(f"trainers.dat[{index}]: bad record {rec!r} (expected 5 fields)")
        class_id, name, items, party, party_id = rec
        t = Trainer(
            index=index,
            class_id=class_id,
            name=name,
            items=[i for i in (items or []) if i],
            party_id=party_id or 0,
        )
        t.party = [_parse_mon(m, f"trainers.dat[{index}] mon {j}") for j, m in enumerate(party)]
        out.append(t)
    return out


# ---- resolver -------------------------------------------------------------


def _load_id_json(path: Path) -> dict[int, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


@dataclass
class _Resolver:
    """Mints TRAINER_*/TRAINER_CLASS_* and resolves party SPECIES_*/MOVE_*/ITEM_*."""

    id_map: IdMap
    species_internal: dict[int, str]
    move_internal: dict[int, str]
    move_names: dict[int, str]
    item_internal: dict[int, str]
    item_names: dict[int, str]
    fork_species: set[str]
    fork_moves: set[str]
    fork_items: set[str]

    def class_constant(self, tt: TrainerType) -> str:
        const = to_constant("TRAINER_CLASS", tt.internal_name)
        self.id_map.add("trainer_classes", tt.internal_name, const)
        return const

    def trainer_constant(self, t: Trainer) -> str:
        # Identity is (class, name, party_id); the array index guarantees a
        # unique, stable key (the de-facto Uranium id). V6 may rename.
        key = f"{t.name}_{t.index}"
        const = to_constant("TRAINER", key)
        self.id_map.add("trainers", key, const)
        return const

    def species_constant(self, species_id: int) -> str:
        internal = self.species_internal.get(species_id)
        if internal is None:
            raise ValueError(f"species id {species_id} absent from species_internal_names.json")
        const = to_constant("SPECIES", internal)
        needs = bool(self.fork_species) and const not in self.fork_species
        self.id_map.add("species", internal, const, needs_engine=needs)
        return const

    def move_constant(self, move_id: int) -> str:
        internal = self.move_internal.get(move_id)
        if internal is None:
            raise ValueError(f"move id {move_id} absent from move_internal_names.json")
        const = to_constant("MOVE", self.move_names.get(move_id) or internal)
        needs = bool(self.fork_moves) and const not in self.fork_moves
        self.id_map.add("moves", internal, const, needs_engine=needs)
        return const

    def item_constant(self, item_id: int) -> str:
        if item_id == 0:
            return "ITEM_NONE"
        internal = self.item_internal.get(item_id)
        if internal is None:
            raise ValueError(f"item id {item_id} absent from item_internal_names.json")
        const = to_constant("ITEM", self.item_names.get(item_id) or internal)
        needs = bool(self.fork_items) and const not in self.fork_items
        self.id_map.add("items", internal, const, needs_engine=needs)
        return const


def _build_resolver(id_map: IdMap, ref: Path) -> _Resolver:
    fork_env = os.environ.get("RPG2GBA_POKEEMERALD")
    fork = Path(fork_env) if fork_env else None

    def fork_set(rel: str, prefix: str) -> set[str]:
        return load_fork_constants(fork / rel, prefix) if fork else set()

    return _Resolver(
        id_map=id_map,
        species_internal=_load_id_json(ref / "species_internal_names.json"),
        move_internal=_load_id_json(ref / "move_internal_names.json"),
        move_names=_load_id_json(ref / "move_names.json"),
        item_internal=_load_id_json(ref / "item_internal_names.json"),
        item_names=_load_id_json(ref / "item_names.json"),
        fork_species=fork_set("include/constants/species.h", "SPECIES"),
        fork_moves=fork_set("include/constants/moves.h", "MOVE"),
        fork_items=fork_set("include/constants/items.h", "ITEM"),
    )


# ---- emit -----------------------------------------------------------------


def _emit_mon(m: TrainerMon, r: _Resolver) -> dict[str, object]:
    out: dict[str, object] = {
        "species": r.species_constant(m.species),
        "level": m.level,
    }
    if m.item:
        out["item"] = r.item_constant(m.item)
    if m.moves:
        out["moves"] = [r.move_constant(mv) for mv in m.moves]
    if m.ability_flag is not None:
        out["ability_flag"] = m.ability_flag
    if m.gender is not None:
        out["gender"] = m.gender
    if m.form:
        out["form"] = m.form
    if m.shiny:
        out["shiny"] = True
    if m.nature is not None:
        out["nature"] = m.nature
    out["iv"] = m.iv
    out["happiness"] = m.happiness
    if m.nickname:
        out["nickname"] = m.nickname
    if m.ball:
        out["ball"] = m.ball
    return out


def build_trainer_types(types: list[TrainerType], r: _Resolver) -> dict[str, object]:
    out: dict[str, object] = {}
    for tt in types:
        const = r.class_constant(tt)
        if const in out:
            raise ValueError(f"trainer class constant collision: {const}")
        out[const] = {
            "id": tt.id,
            "name": tt.display_name,
            "base_money": tt.base_money,
            "battle_bgm": tt.battle_bgm,
            "win_bgm": tt.win_bgm,
            "intro_bgm": tt.intro_bgm,
            "gender": _GENDER_NAMES.get(tt.gender, tt.gender),
            "skill": tt.skill,
        }
    return dict(sorted(out.items()))


def build_trainers(
    trainers: list[Trainer], types_by_id: dict[int, TrainerType], r: _Resolver
) -> dict[str, object]:
    out: dict[str, object] = {}
    for t in trainers:
        const = r.trainer_constant(t)
        tt = types_by_id.get(t.class_id)
        if tt is None:
            raise ValueError(f"trainers.dat[{t.index}]: unknown trainer class id {t.class_id}")
        out[const] = {
            "id": t.index,
            "trainer_class": to_constant("TRAINER_CLASS", tt.internal_name),
            "name": t.name,
            "party_id": t.party_id,
            "items": [r.item_constant(i) for i in t.items],
            "party": [_emit_mon(m, r) for m in t.party],
        }
    return dict(sorted(out.items()))


def run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None:
    """Phase 2 §2.6 entry point: emit trainer + trainer-class intermediate JSON."""
    data = uranium_src / "Data"
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True, exist_ok=True)

    types = parse_trainer_types(
        load_json(dump_dat(data / "trainertypes.dat", inter / "trainertypes_raw.json"))
    )
    trainers = parse_trainers(
        load_json(dump_dat(data / "trainers.dat", inter / "trainers_raw.json"))
    )

    r = _build_resolver(id_map, _reference_dir())
    types_by_id = {tt.id: tt for tt in types}

    types_json = build_trainer_types(types, r)
    trainers_json = build_trainers(trainers, types_by_id, r)

    note = (
        "Uranium trainers/trainer-classes as constants-keyed intermediate JSON. "
        "V6 generates data/trainers.party (trainerproc input) from this; the fork "
        "build-generates src/data/trainers.h. Custom runtime trainers (script 216) "
        "are Phase 4 work (MEMORY 2026-05-15). 0 TPSHADOW rows asserted at parse."
    )
    (inter / "trainer_types.json").write_text(
        json.dumps({"_comment": note, "trainer_classes": types_json}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (inter / "trainers.json").write_text(
        json.dumps({"_comment": note, "trainers": trainers_json}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    party_total = sum(len(t.party) for t in trainers)
    logger.info(
        "emitted %d trainers (%d party mons) across %d trainer classes; 0 TPSHADOW",
        len(trainers),
        party_total,
        len(types),
    )
