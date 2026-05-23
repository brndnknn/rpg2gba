"""Phase 2 §2.7 — wild encounters from `encounters.dat`.

Source (Ruby Marshal; deserialized via `_marshal.dump_dat`):
  encounters.dat — hash keyed by Uranium map id → `[densities, slots]`
  (Compiler.rb `pbCompileEncounters`:1001-1104).
    densities: 13 ints, one per EncounterType (EnctypeDensities order).
    slots: array indexed by EncounterType; `slots[enc]` is a list of
           `[species_id, min_level, max_level]` (or null/absent).
  EncounterType order (104_PField_Encounters.rb): 0 Land, 1 Cave, 2 Water,
  3 RockSmash, 4 OldRod, 5 GoodRod, 6 SuperRod, 7 HeadbuttLow, 8 HeadbuttHigh,
  9 LandMorning, 10 LandDay, 11 LandNight, 12 BugContest.

Per PHASE2_PLAN §2.7 the Essentials types are mapped to the fork's
`wild_encounters.json` fields (land_mons / water_mons / rock_smash_mons /
fishing_mons with old/good/super rod groups) and emitted keyed by **Uranium map
id** (Phase 5 remaps ids → `MAP_*`). The fork has no host for Cave-vs-Land split,
time-of-day land variants, Headbutt, or Bug Contest — rather than silently drop
them (CLAUDE §4.5), those are preserved verbatim under a per-map `uranium_extra`
block for V6/Phase 5. `SPECIES_*` resolve through the shared `to_constant`/IdMap
rule (idempotent vs §2.1).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from ._id_map import IdMap
from ._marshal import dump_dat, load_json
from ._naming import load_fork_constants, to_constant

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.pbs_converter.encounters"

# EncounterType indices (104_PField_Encounters.rb).
LAND, CAVE, WATER, ROCKSMASH = 0, 1, 2, 3
OLDROD, GOODROD, SUPERROD = 4, 5, 6
HEADBUTT_LOW, HEADBUTT_HIGH = 7, 8
LAND_MORNING, LAND_DAY, LAND_NIGHT, BUG_CONTEST = 9, 10, 11, 12
_NUM_TYPES = 13

# Uranium-only types with no fork wild_encounters host → preserved under
# uranium_extra (keyed by these labels) instead of being dropped.
_EXTRA_LABELS: dict[int, str] = {
    CAVE: "cave",
    HEADBUTT_LOW: "headbutt_low",
    HEADBUTT_HIGH: "headbutt_high",
    LAND_MORNING: "land_morning",
    LAND_DAY: "land_day",
    LAND_NIGHT: "land_night",
    BUG_CONTEST: "bug_contest",
}
# Preference order for which table fills the fork's single land_mons field.
_LAND_SOURCES = (LAND, CAVE, LAND_DAY, LAND_MORNING, LAND_NIGHT)


@dataclass
class _Resolver:
    id_map: IdMap
    species_internal: dict[int, str]
    fork_species: set[str]

    def species_constant(self, species_id: int) -> str:
        internal = self.species_internal.get(species_id)
        if internal is None:
            raise ValueError(f"species id {species_id} absent from species_internal_names.json")
        const = to_constant("SPECIES", internal)
        needs = bool(self.fork_species) and const not in self.fork_species
        self.id_map.add("species", internal, const, needs_engine=needs)
        return const


def _load_id_json(path: Path) -> dict[int, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


def _build_resolver(id_map: IdMap, ref: Path) -> _Resolver:
    fork_env = os.environ.get("RPG2GBA_POKEEMERALD")
    fork = Path(fork_env) if fork_env else None
    fork_species = (
        load_fork_constants(fork / "include/constants/species.h", "SPECIES") if fork else set()
    )
    return _Resolver(
        id_map=id_map,
        species_internal=_load_id_json(ref / "species_internal_names.json"),
        fork_species=fork_species,
    )


def _slot(entry: list, r: _Resolver) -> dict[str, object]:
    if not isinstance(entry, list) or len(entry) != 3:
        raise ValueError(f"encounter slot {entry!r} is not [species, min, max]")
    species_id, min_level, max_level = entry
    return {
        "species": r.species_constant(species_id),
        "min_level": min_level,
        "max_level": max_level,
    }


def _slots_at(slots: list, enc: int, r: _Resolver) -> list[dict[str, object]] | None:
    """The resolved slot list for encounter type `enc`, or None if absent/empty."""
    if enc >= len(slots):
        return None
    raw = slots[enc]
    if not raw:
        return None
    return [_slot(e, r) for e in raw]


def _emit_map(densities: list, slots: list, r: _Resolver) -> dict[str, object]:
    out: dict[str, object] = {}

    # land_mons: first present of Land/Cave/time-of-day (the rest go to extra).
    land_src = next((t for t in _LAND_SOURCES if _slots_at(slots, t, r)), None)
    if land_src is not None:
        out["land_mons"] = {
            "encounter_rate": densities[land_src],
            "mons": _slots_at(slots, land_src, r),
        }

    water = _slots_at(slots, WATER, r)
    if water:
        out["water_mons"] = {"encounter_rate": densities[WATER], "mons": water}

    rock = _slots_at(slots, ROCKSMASH, r)
    if rock:
        out["rock_smash_mons"] = {"encounter_rate": densities[ROCKSMASH], "mons": rock}

    fishing: dict[str, object] = {}
    for label, enc in (("old_rod", OLDROD), ("good_rod", GOODROD), ("super_rod", SUPERROD)):
        s = _slots_at(slots, enc, r)
        if s:
            fishing[label] = s
    if fishing:
        out["fishing_mons"] = fishing

    # Anything Uranium carries that the fork can't host (incl. the land tables
    # not chosen as land_mons) is preserved, not dropped.
    extra: dict[str, object] = {}
    for enc, label in _EXTRA_LABELS.items():
        if enc == land_src:
            continue  # already represented as land_mons
        s = _slots_at(slots, enc, r)
        if s:
            extra[label] = {"encounter_rate": densities[enc], "mons": s}
    if extra:
        out["uranium_extra"] = dict(sorted(extra.items()))
    return out


def parse_and_build(raw: object, r: _Resolver) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError("encounters.dat: expected a top-level hash keyed by map id")
    out: dict[str, object] = {}
    for map_id, value in raw.items():
        if not (isinstance(value, list) and len(value) == 2):
            raise ValueError(
                f"encounters.dat[{map_id}]: expected [densities, slots], got {value!r}"
            )
        densities, slots = value
        if not isinstance(densities, list) or len(densities) != _NUM_TYPES:
            raise ValueError(f"encounters.dat[{map_id}]: densities must be {_NUM_TYPES} ints")
        if not isinstance(slots, list):
            raise ValueError(f"encounters.dat[{map_id}]: slots must be an array")
        out[str(int(map_id))] = _emit_map(densities, slots, r)
    return {k: out[k] for k in sorted(out, key=int)}


def run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None:
    """Phase 2 §2.7 entry point: emit wild_encounters.json keyed by Uranium map id."""
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True, exist_ok=True)
    raw = load_json(
        dump_dat(uranium_src / "Data" / "encounters.dat", inter / "encounters_raw.json")
    )
    r = _build_resolver(id_map, _reference_dir())
    tables = parse_and_build(raw, r)

    note = (
        "Uranium wild encounters keyed by Uranium map id (Phase 5 remaps to MAP_*). "
        "Mapped to the fork's wild_encounters.json fields; Cave/time-of-day/Headbutt/"
        "BugContest tables the fork can't host are preserved under per-map uranium_extra."
    )
    (inter / "wild_encounters.json").write_text(
        json.dumps({"_comment": note, "maps": tables}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    extra = sum(1 for m in tables.values() if isinstance(m, dict) and "uranium_extra" in m)
    logger.info("emitted wild encounters for %d maps (%d carry uranium_extra)", len(tables), extra)
