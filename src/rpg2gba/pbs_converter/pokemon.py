"""Phase 2 §2.1 — convert `dexdata.dat` + species side-data into C tables.

Sources (all under `$RPG2GBA_URANIUM_SRC/Data/`):

  dexdata.dat       — flat 76-byte records, one per species ID 1..N.
  attacksRS.dat     — indexed: per-species [level uint16, move_id uint16] pairs.
  evolutions.dat    — indexed: per-species 5-byte evolution records.
  eggEmerald.dat    — indexed: per-species uint16 egg-move IDs.
  tutor.dat         — indexed: per-species uint16 tutor-move IDs.
  regionals.dat     — header (uint16 count, uint16 species_count), then matrix.
  metrics.dat       — Ruby Marshal: 3 parallel signed-word arrays.
  tmpbs.dat         — handled by `tmpbs.py` (§2.9), not here.

Side tables read from `reference/`:
  species_internal_names.json  (Uranium ID → INTERNALNAME)
  species_names.json           (Uranium ID → display name)
  species_kinds.json           (Uranium ID → "Mouse Pokémon" etc.)
  species_pokedex.json         (Uranium ID → dex entry text)
  ability_internal_names.json  (ability ID → INTERNALNAME, used for ability resolution)
  move_internal_names.json     (move ID → INTERNALNAME, used for learnset resolution)

The 76-byte dexdata layout was derived from `pbCompilePokemonData` in
`reference/scripts_dump/175__Compiler.rb` (lines ~2269-2470). All multi-byte
fields are little-endian; floats (height, weight) are stored as
`(value * 10).round` uint16, so divide by 10 on read.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from ._binary import DatReader
from ._c_emit import escape_c_string, generated_banner, wrap_header
from ._id_map import IdMap
from ._naming import load_fork_constants, to_constant

logger = logging.getLogger(__name__)

DEXDATA_RECORD_SIZE = 76


# Enum decode tables — order from Compiler.rb requiredtypes / optionaltypes.
COLOR_NAMES: tuple[str, ...] = (
    "Red", "Blue", "Yellow", "Green", "Black",
    "Brown", "Purple", "Gray", "White", "Pink",
)
HABITAT_NAMES: tuple[str, ...] = (
    "", "Grassland", "Forest", "WatersEdge", "Sea",
    "Cave", "Mountain", "RoughTerrain", "Urban", "Rare",
)
GROWTH_RATE_NAMES: dict[int, str] = {
    0: "MediumFast",   # also "Medium"
    1: "Erratic",
    2: "Fluctuating",
    3: "MediumSlow",   # also "Parabolic"
    4: "Fast",
    5: "Slow",
}
GENDER_RATE_NAMES: dict[int, str] = {
    0: "AlwaysMale",
    31: "FemaleOneEighth",
    63: "Female25Percent",
    127: "Female50Percent",
    191: "Female75Percent",
    223: "FemaleSevenEighths",
    254: "AlwaysFemale",
    255: "Genderless",
}


@dataclass
class Species:
    """One species record. IDs are 1-based; ID 0 is the null/placeholder slot."""

    id: int
    internal_name: str
    color: int                 # @6
    habitat: int               # @7  (0 = unset)
    type1: int                 # @8
    type2: int                 # @9
    base_stats: tuple[int, int, int, int, int, int]   # HP/Atk/Def/Spd/SpA/SpD @10-15
    rareness: int              # @16
    gender_rate: int           # @18
    happiness: int             # @19
    growth_rate: int           # @20
    steps_to_hatch: int        # @21-22 uint16
    effort_points: tuple[int, int, int, int, int, int]  # @23-28
    abilities: tuple[int, int]                   # @29-30
    compatibility: tuple[int, int]               # @31-32 (egg groups)
    height_dm: int             # @33-34 uint16 (decimeters; real_m = value / 10)
    weight_hg: int             # @35-36 uint16 (hectograms; real_kg = value / 10)
    base_exp: int              # @38-39 uint16
    hidden_abilities: tuple[int, int, int, int]  # @40-43
    wild_item_common: int      # @48-49
    wild_item_uncommon: int    # @50-51
    wild_item_rare: int        # @52-53

    # Side-data attached after dexdata parse:
    level_up_moves: list[tuple[int, int]] = field(default_factory=list)  # (level, move_id)
    evolutions: list[tuple[int, int, int]] = field(default_factory=list)  # (method, param, target)
    egg_moves: list[int] = field(default_factory=list)
    tutor_moves: list[int] = field(default_factory=list)
    regional_dex_number: int | None = None
    battler_player_y: int = 0
    battler_enemy_y: int = 0
    battler_altitude: int = 0


def parse_dexdata(path: Path) -> list[Species]:
    """Parse `dexdata.dat` into Species records, indexed 1..N (index 0 → None).

    Returns a list where `out[id]` is the Species for that ID, or `None` for
    unused slots. The caller is expected to fill `internal_name` afterwards.
    """
    reader = DatReader(path)
    if reader.size % DEXDATA_RECORD_SIZE != 0:
        raise ValueError(
            f"{path}: size {reader.size} is not a multiple of {DEXDATA_RECORD_SIZE}"
        )
    species_count = reader.size // DEXDATA_RECORD_SIZE
    out: list[Species | None] = [None] * (species_count + 1)
    for species_id in range(1, species_count + 1):
        offset = (species_id - 1) * DEXDATA_RECORD_SIZE
        rec = reader.at(offset, DEXDATA_RECORD_SIZE)
        raw = rec.bytes(DEXDATA_RECORD_SIZE)
        # All-zero slots are placeholders (dexdatas[i] == nil in Compiler.rb).
        if raw == b"\x00" * DEXDATA_RECORD_SIZE:
            continue
        out[species_id] = _parse_one(species_id, raw)
    return out  # type: ignore[return-value]


def _parse_one(species_id: int, raw: bytes) -> Species:
    u = raw  # alias

    def u16(off: int) -> int:
        return int.from_bytes(u[off:off + 2], "little", signed=False)

    return Species(
        id=species_id,
        internal_name="",  # filled in by caller after Constants.rxdata is read
        color=u[6],
        habitat=u[7],
        type1=u[8],
        type2=u[9],
        base_stats=tuple(u[10:16]),  # type: ignore[arg-type]
        rareness=u[16],
        gender_rate=u[18],
        happiness=u[19],
        growth_rate=u[20],
        steps_to_hatch=u16(21),
        effort_points=tuple(u[23:29]),  # type: ignore[arg-type]
        abilities=(u[29], u[30]),
        compatibility=(u[31], u[32]),
        height_dm=u16(33),
        weight_hg=u16(35),
        base_exp=u16(38),
        hidden_abilities=(u[40], u[41], u[42], u[43]),
        wild_item_common=u16(48),
        wild_item_uncommon=u16(50),
        wild_item_rare=u16(52),
    )


# ---- indexed aux files ---------------------------------------------------

# All `attacksRS.dat`/`evolutions.dat`/`eggEmerald.dat`/`tutor.dat`/`tmpbs.dat`
# share a "mx × 8 byte header (offset uint32, stored_length uint32), then
# per-species body" layout. `mx` matches the highest species ID — same as the
# count of records in `dexdata.dat`. Each file's stored-length semantics differ
# (see PHASE2_PLAN.md §"Cross-cutting components" table); we encode that
# difference per-parser rather than in a single shared helper.

def _read_indexed_header(reader: DatReader, species_count: int) -> list[tuple[int, int]]:
    return [(reader.dw(), reader.dw()) for _ in range(species_count)]


def parse_attacks_rs(path: Path, species_count: int) -> list[list[tuple[int, int]]]:
    """Parse `attacksRS.dat`: per-species level-up learnsets.

    Stored length = `pair_count × 2` (count of uint16 elements). Each pair is
    4 bytes (uint16 level, uint16 move_id). Returns a list indexed 1..N where
    `out[id]` is `[(level, move_id), ...]` sorted by appearance order.
    """
    reader = DatReader(path)
    headers = _read_indexed_header(reader, species_count)
    out: list[list[tuple[int, int]]] = [[] for _ in range(species_count + 1)]
    for i, (offset, stored_length) in enumerate(headers, start=1):
        if stored_length == 0:
            continue
        pair_count = stored_length // 2
        body = reader.at(offset, pair_count * 4)
        out[i] = [(body.w(), body.w()) for _ in range(pair_count)]
    return out


# Evolution record packing (Compiler.rb / 125__Pokemon_Evolution.rb:64-88):
#   byte = (data_bits << 6) | method_index
# where method_index is masked by _EVOTYPEMASK=0x3F and the top two bits
# (_EVODATAMASK=0xC0) flag form/prevolution variants. Only data_bits == 0
# (_EVONEXTFORM) records are *forward* evolutions; Essentials also stores the
# inverse (prevolution) and form-change rows in the same blob, which we drop.
_EVO_TYPE_MASK = 0x3F
_EVO_DATA_MASK = 0xC0
_EVO_NEXT_FORM = 0x00


def parse_evolutions(path: Path, species_count: int) -> list[list[tuple[int, int, int]]]:
    """Parse `evolutions.dat`: per-species *forward* evolution records.

    Stored length = `record_count × 5` (byte count). Each 5-byte record is
    `[packed uint8, param uint16, target_species uint16]` where
    `method = packed & 0x3F` and `packed & 0xC0` distinguishes forward
    evolutions (`0x00`) from the prevolution/form rows we skip. Returns
    `[(method, param, target_species), ...]` in file order.
    """
    reader = DatReader(path)
    headers = _read_indexed_header(reader, species_count)
    out: list[list[tuple[int, int, int]]] = [[] for _ in range(species_count + 1)]
    for i, (offset, stored_length) in enumerate(headers, start=1):
        if stored_length == 0:
            continue
        if stored_length % 5 != 0:
            raise ValueError(f"{path}: species {i} length {stored_length} not multiple of 5")
        record_count = stored_length // 5
        body = reader.at(offset, stored_length)
        rows: list[tuple[int, int, int]] = []
        for _ in range(record_count):
            packed = body.b()
            param = body.w()
            target = body.w()
            if (packed & _EVO_DATA_MASK) != _EVO_NEXT_FORM:
                continue  # prevolution / form-change row, not a forward evolution
            rows.append((packed & _EVO_TYPE_MASK, param, target))
        out[i] = rows
    return out


def parse_indexed_u16_list(path: Path, species_count: int) -> list[list[int]]:
    """Parse the recurring "per-species list of uint16 IDs" layout.

    Used by `eggEmerald.dat`, `tutor.dat`, `tmpbs.dat`. Stored length is the
    element count (count of uint16 IDs).
    """
    reader = DatReader(path)
    headers = _read_indexed_header(reader, species_count)
    out: list[list[int]] = [[] for _ in range(species_count + 1)]
    for i, (offset, stored_length) in enumerate(headers, start=1):
        if stored_length == 0:
            continue
        body = reader.at(offset, stored_length * 2)
        out[i] = [body.w() for _ in range(stored_length)]
    return out


def parse_regionals(path: Path) -> list[list[int]]:
    """Parse `regionals.dat`: per-regional-dex × per-species lookup matrix.

    Header is `[num_regionals: uint16, num_species: uint16]`. For Uranium,
    num_regionals = 1 (Tandor) and num_species = 202 (dexdatas.length, includes
    the ID-0 placeholder slot). Returns a `num_regionals`-long list of
    species-indexed lists, so `out[0][species_id]` is the Tandor dex number
    for that species (0 = no entry).
    """
    reader = DatReader(path)
    num_regionals = reader.w()
    num_species = reader.w()
    matrix = [[reader.w() for _ in range(num_species)] for _ in range(num_regionals)]
    return matrix


def attach_side_data(
    species: list[Species | None],
    *,
    level_up_moves: list[list[tuple[int, int]]] | None = None,
    evolutions: list[list[tuple[int, int, int]]] | None = None,
    egg_moves: list[list[int]] | None = None,
    tutor_moves: list[list[int]] | None = None,
    regionals_matrix: list[list[int]] | None = None,
) -> None:
    """Merge aux-file parse results onto the Species records.

    Each input list must be 1-based and the same length as `species`. Any
    species id present in an input but not in `species` is a fail-loud error.
    """
    for i, s in enumerate(species):
        if s is None:
            continue
        if level_up_moves is not None:
            s.level_up_moves = list(level_up_moves[i])
        if evolutions is not None:
            s.evolutions = list(evolutions[i])
        if egg_moves is not None:
            s.egg_moves = list(egg_moves[i])
        if tutor_moves is not None:
            s.tutor_moves = list(tutor_moves[i])
        if regionals_matrix is not None and regionals_matrix:
            # First regional dex (Tandor) only; cell[i] is the dex number.
            n = regionals_matrix[0][i] if i < len(regionals_matrix[0]) else 0
            s.regional_dex_number = n if n != 0 else None


def attach_internal_names(species: list[Species | None], names_by_id: dict[int, str]) -> None:
    """Populate Species.internal_name from species_internal_names.json.

    Fail-loud per CLAUDE.md §4.5: any species record without a corresponding
    internal name is reported with its id.
    """
    missing = []
    for s in species:
        if s is None:
            continue
        name = names_by_id.get(s.id)
        if name is None:
            missing.append(s.id)
            continue
        s.internal_name = name
    if missing:
        raise ValueError(
            f"species_internal_names.json missing IDs: {missing[:10]}"
            f"{' (+more)' if len(missing) > 10 else ''}"
        )


# ===========================================================================
# C emit  (§2.1)
#
# Target shapes are documented in reference/pokeemerald_struct_shapes.md (P4).
# The expansion consumes `gSpeciesInfo[]` via designated initializers, so we
# emit only the fields Uranium carries; everything else takes its struct
# default. Move/ability/item constants are resolved through `_naming.to_constant`
# (the single naming rule shared with §2.2–§2.4) and registered in the IdMap;
# a constant the fork doesn't define is a Uranium-original → `needs_engine`.
# ===========================================================================

# Uranium enum index → expansion constant (Compiler.rb stores these indices).
_BODY_COLOR_BY_INDEX: dict[int, str] = {
    i: f"BODY_COLOR_{name.upper()}" for i, name in enumerate(COLOR_NAMES)
}
_GROWTH_RATE_BY_INDEX: dict[int, str] = {
    0: "GROWTH_MEDIUM_FAST",
    1: "GROWTH_ERRATIC",
    2: "GROWTH_FLUCTUATING",
    3: "GROWTH_MEDIUM_SLOW",
    4: "GROWTH_FAST",
    5: "GROWTH_SLOW",
}
# Essentials Compatibility hash (Compiler.rb:2287) → expansion EGG_GROUP_*.
_EGG_GROUP_BY_INDEX: dict[int, str] = {
    0: "EGG_GROUP_NONE",
    1: "EGG_GROUP_MONSTER",
    2: "EGG_GROUP_WATER_1",
    3: "EGG_GROUP_BUG",
    4: "EGG_GROUP_FLYING",
    5: "EGG_GROUP_FIELD",
    6: "EGG_GROUP_FAIRY",
    7: "EGG_GROUP_GRASS",
    8: "EGG_GROUP_HUMAN_LIKE",
    9: "EGG_GROUP_WATER_3",
    10: "EGG_GROUP_MINERAL",
    11: "EGG_GROUP_AMORPHOUS",
    12: "EGG_GROUP_WATER_2",
    13: "EGG_GROUP_DITTO",
    14: "EGG_GROUP_DRAGON",
    15: "EGG_GROUP_NO_EGGS_DISCOVERED",
}
# Uranium type internal names that don't map by `TYPE_<INTERNAL>`.
_TYPE_NAME_OVERRIDES: dict[str, str] = {"QMARKS": "TYPE_MYSTERY"}

# struct SpeciesInfo field names, in Uranium base_stats / effort_points order
# (HP, Atk, Def, Spd, SpA, SpD — matches the expansion struct order).
_STAT_FIELDS: tuple[str, ...] = (
    "baseHP", "baseAttack", "baseDefense", "baseSpeed", "baseSpAttack", "baseSpDefense",
)
_EV_FIELDS: tuple[str, ...] = (
    "evYield_HP", "evYield_Attack", "evYield_Defense",
    "evYield_Speed", "evYield_SpAttack", "evYield_SpDefense",
)

# Evolution method names, indexed by the byte stored in evolutions.dat
# (125__Pokemon_Evolution.rb EVONAMES).
_EVONAMES: tuple[str, ...] = (
    "Unknown", "Happiness", "HappinessDay", "HappinessNight", "Level", "Trade",
    "TradeItem", "Item", "AttackGreater", "AtkDefEqual", "DefenseGreater",
    "Silcoon", "Cascoon", "Ninjask", "Shedinja", "Beauty", "ItemMale",
    "ItemFemale", "DayHoldItem", "NightHoldItem", "HasMove", "HasInParty",
    "LevelMale", "LevelFemale", "Location", "TradeSpecies", "Seikamater",
    "TypeNuclear", "Custom3", "Custom4", "Custom5", "Custom6", "Custom7",
)

GENERATOR = "rpg2gba.pbs_converter.pokemon"


def _reference_dir() -> Path:
    """The repo's `reference/` dir (committed sidecars from messages.dat etc.)."""
    return Path(__file__).resolve().parents[3] / "reference"


def _load_id_json(path: Path) -> dict[int, str]:
    """Load a `{ "<id>": "<string>" }` sidecar into an int-keyed dict."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


@dataclass
class _Resolver:
    """Resolves Uranium IDs to expansion constants, registering them in IdMap.

    The fork constant sets are the ground truth for `needs_engine`: a derived
    constant absent from the fork is a Uranium-original. Empty sets mean the
    fork wasn't available, so we can't validate and skip the marking.
    """

    id_map: IdMap
    species_internal: dict[int, str]
    species_names: dict[int, str]
    species_kinds: dict[int, str]
    species_pokedex: dict[int, str]
    move_internal: dict[int, str]
    move_names: dict[int, str]
    ability_internal: dict[int, str]
    ability_names: dict[int, str]
    item_internal: dict[int, str]
    item_names: dict[int, str]
    type_internal: dict[int, str]
    fork_species: set[str]
    fork_moves: set[str]
    fork_abilities: set[str]
    fork_items: set[str]

    def species_constant(self, species_id: int) -> str:
        internal = self.species_internal.get(species_id)
        if internal is None:
            raise ValueError(f"no internal name for species id {species_id}")
        const = to_constant("SPECIES", internal)
        needs = bool(self.fork_species) and const not in self.fork_species
        self.id_map.add("species", internal, const, needs_engine=needs)
        return const

    def name(self, species_id: int) -> str:
        return self.species_names.get(species_id, self.species_internal.get(species_id, ""))

    def kind(self, species_id: int) -> str:
        return self.species_kinds.get(species_id, "")

    def dex(self, species_id: int) -> str:
        return self.species_pokedex.get(species_id, "")

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

    def ability_constant(self, ability_id: int) -> str:
        if ability_id == 0:
            return "ABILITY_NONE"
        internal = self.ability_internal.get(ability_id)
        if internal is None:
            raise ValueError(f"ability id {ability_id} absent from ability_internal_names.json")
        const = to_constant("ABILITY", self.ability_names.get(ability_id) or internal)
        needs = bool(self.fork_abilities) and const not in self.fork_abilities
        self.id_map.add("abilities", internal, const, needs_engine=needs)
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

    def type_constant(self, type_idx: int) -> str:
        internal = self.type_internal.get(type_idx)
        if internal is None:
            raise ValueError(f"type index {type_idx} absent from type_internal_names.json")
        const = _TYPE_NAME_OVERRIDES.get(internal, to_constant("TYPE", internal))
        self.id_map.add("types", internal, const)
        return const


def _build_resolver(id_map: IdMap, ref: Path) -> _Resolver:
    fork_env = os.environ.get("RPG2GBA_POKEEMERALD")
    fork = Path(fork_env) if fork_env else None

    def fork_set(rel: str, prefix: str) -> set[str]:
        return load_fork_constants(fork / rel, prefix) if fork else set()

    return _Resolver(
        id_map=id_map,
        species_internal=_load_id_json(ref / "species_internal_names.json"),
        species_names=_load_id_json(ref / "species_names.json"),
        species_kinds=_load_id_json(ref / "species_kinds.json"),
        species_pokedex=_load_id_json(ref / "species_pokedex.json"),
        move_internal=_load_id_json(ref / "move_internal_names.json"),
        move_names=_load_id_json(ref / "move_names.json"),
        ability_internal=_load_id_json(ref / "ability_internal_names.json"),
        ability_names=_load_id_json(ref / "ability_names.json"),
        item_internal=_load_id_json(ref / "item_internal_names.json"),
        item_names=_load_id_json(ref / "item_names.json"),
        type_internal=_load_id_json(ref / "type_internal_names.json"),
        fork_species=fork_set("include/constants/species.h", "SPECIES"),
        fork_moves=fork_set("include/constants/moves.h", "MOVE"),
        fork_abilities=fork_set("include/constants/abilities.h", "ABILITY"),
        fork_items=fork_set("include/constants/items.h", "ITEM"),
    )


def _learnset_symbol(internal: str) -> str:
    return f"sLevelUpLearnset_{internal}"


def _egg_symbol(internal: str) -> str:
    return f"sEggMoveLearnset_{internal}"


def _emit_evolution(
    method_idx: int, param: int, target: str, r: _Resolver
) -> tuple[str, str | None]:
    """Return (record_str, todo_method_name | None) for one forward evolution.

    Maps the clean/common Uranium methods to expansion `EVO_*` + `CONDITIONS`.
    Uranium-original or unmapped methods emit an `{EVO_NONE, ...}` placeholder
    and return the method name so the caller can leave a Phase 6 TODO.
    """
    def rec(method: str, param_val: object, *conditions: str) -> str:
        body = f"{{{method}, {param_val}, {target}"
        if conditions:
            inner = ", ".join("{" + c + "}" for c in conditions)
            body += f", CONDITIONS({inner})"
        return body + "}"

    friend = "IF_MIN_FRIENDSHIP, FRIENDSHIP_EVO_THRESHOLD"
    if method_idx == 4:  # Level
        return rec("EVO_LEVEL", param), None
    if method_idx == 1:  # Happiness
        return rec("EVO_LEVEL", 0, friend), None
    if method_idx == 2:  # HappinessDay
        return rec("EVO_LEVEL", 0, friend, "IF_TIME, TIME_DAY"), None
    if method_idx == 3:  # HappinessNight
        return rec("EVO_LEVEL", 0, friend, "IF_TIME, TIME_NIGHT"), None
    if method_idx == 5:  # Trade
        return rec("EVO_TRADE", 0), None
    if method_idx == 6:  # TradeItem (param = item)
        return rec("EVO_TRADE", 0, f"IF_HOLD_ITEM, {r.item_constant(param)}"), None
    if method_idx == 7:  # Item (param = item)
        return rec("EVO_ITEM", r.item_constant(param)), None
    if method_idx == 8:  # AttackGreater (param = level)
        return rec("EVO_LEVEL", param, "IF_ATK_GT_DEF"), None
    if method_idx == 9:  # AtkDefEqual
        return rec("EVO_LEVEL", param, "IF_ATK_EQ_DEF"), None
    if method_idx == 10:  # DefenseGreater
        return rec("EVO_LEVEL", param, "IF_ATK_LT_DEF"), None
    if method_idx == 18:  # DayHoldItem (param = item)
        hold = f"IF_HOLD_ITEM, {r.item_constant(param)}"
        return rec("EVO_LEVEL", 0, "IF_TIME, TIME_DAY", hold), None
    if method_idx == 19:  # NightHoldItem (param = item)
        hold = f"IF_HOLD_ITEM, {r.item_constant(param)}"
        return rec("EVO_LEVEL", 0, "IF_TIME, TIME_NIGHT", hold), None
    if method_idx == 20:  # HasMove (param = move)
        return rec("EVO_LEVEL", 0, f"IF_KNOWS_MOVE, {r.move_constant(param)}"), None
    if method_idx == 21:  # HasInParty (param = species)
        return rec("EVO_LEVEL", 0, f"IF_SPECIES_IN_PARTY, {r.species_constant(param)}"), None
    if method_idx == 25:  # TradeSpecies (param = species)
        return rec("EVO_TRADE", 0, f"IF_TRADE_PARTNER_SPECIES, {r.species_constant(param)}"), None
    # Silcoon/Cascoon/Ninjask/Shedinja/Beauty/ItemMale/Female/LevelMale/Female/
    # Location/Seikamater/TypeNuclear/Custom* — needs Phase 6 engine support.
    name = _EVONAMES[method_idx] if method_idx < len(_EVONAMES) else f"#{method_idx}"
    return rec("EVO_NONE", 0), name


def _emit_species_constants(species: list[Species | None], r: _Resolver) -> str:
    lines = ["#define SPECIES_NONE 0"]
    for s in species:
        if s is None:
            continue
        lines.append(f"#define {r.species_constant(s.id)} {s.id}")
    banner = generated_banner("dexdata.dat + Constants.rxdata", GENERATOR, timestamp=False)
    note = (
        "// NOTE: these are Uranium's own species IDs (1-based, Tandor space).\n"
        "// They overlap vanilla SPECIES_* numbering — V6 integration must\n"
        "// reconcile them with the fork's species enum.\n"
    )
    return wrap_header("GUARD_URANIUM_CONSTANTS_SPECIES_H", note + "\n".join(lines), banner=banner)


def _emit_level_up_learnsets(species: list[Species | None], r: _Resolver) -> str:
    blocks: list[str] = []
    for s in species:
        if s is None:
            continue
        rows = [
            f"    LEVEL_UP_MOVE({lvl:>3}, {r.move_constant(mv)}),"
            for lvl, mv in s.level_up_moves
        ]
        body = "\n".join(rows)
        blocks.append(
            f"static const struct LevelUpMove {_learnset_symbol(s.internal_name)}[] = {{\n"
            + (body + "\n" if body else "")
            + "    LEVEL_UP_END\n};"
        )
    banner = generated_banner("attacksRS.dat", GENERATOR, timestamp=False)
    return banner + "\n" + "\n\n".join(blocks) + "\n"


def _emit_egg_moves(species: list[Species | None], r: _Resolver) -> str:
    blocks: list[str] = []
    for s in species:
        if s is None or not s.egg_moves:
            continue
        rows = [f"    {r.move_constant(mv)}," for mv in s.egg_moves]
        blocks.append(
            f"static const u16 {_egg_symbol(s.internal_name)}[] = {{\n"
            + "\n".join(rows)
            + "\n    MOVE_UNAVAILABLE,\n};"
        )
    banner = generated_banner("eggEmerald.dat", GENERATOR, timestamp=False)
    return banner + "\n" + "\n\n".join(blocks) + "\n"


def _emit_species_info(species: list[Species | None], r: _Resolver) -> str:
    entries: list[str] = []
    for s in species:
        if s is None:
            continue
        const = r.species_constant(s.id)
        lines: list[str] = [f"    [{const}] =", "    {"]

        for fld, val in zip(_STAT_FIELDS, s.base_stats):
            lines.append(f"        .{fld} = {val},")

        t1 = r.type_constant(s.type1)
        t2 = r.type_constant(s.type2)
        types = f"MON_TYPES({t1})" if t1 == t2 else f"MON_TYPES({t1}, {t2})"
        lines.append(f"        .types = {types},")

        lines.append(f"        .catchRate = {s.rareness},")
        lines.append(f"        .expYield = {s.base_exp},")
        for fld, val in zip(_EV_FIELDS, s.effort_points):
            if val:
                lines.append(f"        .{fld} = {min(val, 3)},")

        gender = "MON_GENDERLESS" if s.gender_rate == 255 else str(s.gender_rate)
        lines.append(f"        .genderRatio = {gender},")
        lines.append(f"        .eggCycles = {round(s.steps_to_hatch / 256)},")
        lines.append(f"        .friendship = {s.happiness},")

        growth = _GROWTH_RATE_BY_INDEX.get(s.growth_rate)
        if growth is None:
            raise ValueError(f"{s.internal_name}: unknown growth rate index {s.growth_rate}")
        lines.append(f"        .growthRate = {growth},")

        eg1 = _EGG_GROUP_BY_INDEX.get(s.compatibility[0])
        eg2 = _EGG_GROUP_BY_INDEX.get(s.compatibility[1])
        if eg1 is None or eg2 is None:
            raise ValueError(f"{s.internal_name}: unknown egg group {s.compatibility}")
        groups = f"MON_EGG_GROUPS({eg1})" if eg1 == eg2 else f"MON_EGG_GROUPS({eg1}, {eg2})"
        lines.append(f"        .eggGroups = {groups},")

        a1 = r.ability_constant(s.abilities[0])
        a2 = r.ability_constant(s.abilities[1])
        hidden = r.ability_constant(s.hidden_abilities[0])
        lines.append(f"        .abilities = {{ {a1}, {a2}, {hidden} }},")
        extra_hidden = [h for h in s.hidden_abilities[1:] if h]
        if extra_hidden:
            extras = ", ".join(r.ability_constant(h) for h in extra_hidden)
            note = "// TODO Phase 6: extra hidden abilities (fork has 1 slot):"
            lines.append(f"        {note} {extras}")

        color = _BODY_COLOR_BY_INDEX.get(s.color)
        if color is None:
            raise ValueError(f"{s.internal_name}: unknown body color index {s.color}")
        lines.append(f"        .bodyColor = {color},")

        lines.append(f"        .height = {s.height_dm},")
        lines.append(f"        .weight = {s.weight_hg},")

        lines.append(f'        .speciesName = _("{escape_c_string(r.name(s.id))}"),')
        kind = r.kind(s.id)
        if kind:
            lines.append(f'        .categoryName = _("{escape_c_string(kind)}"),')
        dex = r.dex(s.id)
        if dex:
            lines.append(f'        .description = COMPOUND_STRING("{escape_c_string(dex)}"),')

        lines.append(f"        .levelUpLearnset = {_learnset_symbol(s.internal_name)},")
        if s.egg_moves:
            lines.append(f"        .eggMoveLearnset = {_egg_symbol(s.internal_name)},")

        if s.evolutions:
            recs: list[str] = []
            todos: list[str] = []
            for method_idx, param, tgt in s.evolutions:
                target_const = r.species_constant(tgt) if tgt else "SPECIES_NONE"
                rec, todo = _emit_evolution(method_idx, param, target_const, r)
                recs.append(rec)
                if todo:
                    todos.append(f"{todo}->{target_const}")
            lines.append(f"        .evolutions = EVOLUTION({', '.join(recs)}),")
            if todos:
                lines.append(f"        // TODO Phase 6: unmapped evo method(s): {', '.join(todos)}")

        lines.append("    },")
        entries.append("\n".join(lines))

    banner = generated_banner(
        "dexdata.dat (+ attacksRS/evolutions/eggEmerald + messages.dat sidecars)",
        GENERATOR,
        timestamp=False,
    )
    includes = (
        '#include "constants/species.h"\n'
        '#include "constants/abilities.h"\n'
        '#include "constants/moves.h"\n'
        '#include "constants/items.h"\n'
        '#include "level_up_learnsets.h"\n'
        '#include "egg_moves.h"\n'
    )
    head = "const struct SpeciesInfo gSpeciesInfo[] =\n{\n"
    return banner + "\n" + includes + "\n" + head + "\n".join(entries) + "\n};\n"


def run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None:
    """Phase 2 §2.1 entry point: parse species data and emit C tables."""
    data = uranium_src / "Data"
    species = parse_dexdata(data / "dexdata.dat")
    n = len(species) - 1
    attach_side_data(
        species,
        level_up_moves=parse_attacks_rs(data / "attacksRS.dat", n),
        evolutions=parse_evolutions(data / "evolutions.dat", n),
        egg_moves=parse_indexed_u16_list(data / "eggEmerald.dat", n),
        tutor_moves=parse_indexed_u16_list(data / "tutor.dat", n),
        regionals_matrix=parse_regionals(data / "regionals.dat"),
    )

    ref = _reference_dir()
    attach_internal_names(species, _load_id_json(ref / "species_internal_names.json"))
    r = _build_resolver(id_map, ref)

    # Pre-mint every species constant so cross-references (evolution targets,
    # IF_SPECIES_IN_PARTY) always resolve regardless of emit order.
    for s in species:
        if s is not None:
            r.species_constant(s.id)

    inc = out_dir / "include" / "constants"
    pkm = out_dir / "src" / "data" / "pokemon"
    inter = out_dir / "intermediate"
    for d in (inc, pkm, inter):
        d.mkdir(parents=True, exist_ok=True)

    (inc / "species.h").write_text(_emit_species_constants(species, r), encoding="utf-8")
    (pkm / "level_up_learnsets.h").write_text(
        _emit_level_up_learnsets(species, r), encoding="utf-8"
    )
    (pkm / "egg_moves.h").write_text(_emit_egg_moves(species, r), encoding="utf-8")
    (pkm / "species_info.h").write_text(_emit_species_info(species, r), encoding="utf-8")

    # Tandor regional dex numbers carried for Phase 5 Pokédex wiring (P4 decision:
    # .natDexNum is left at default since Uranium has no national dex).
    tandor = {
        r.species_constant(s.id): s.regional_dex_number
        for s in species
        if s is not None and s.regional_dex_number
    }
    (inter / "tandor_dex.json").write_text(
        json.dumps(dict(sorted(tandor.items())), indent=2) + "\n", encoding="utf-8"
    )

    logger.info("emitted species data for %d species", sum(1 for s in species if s is not None))
