"""Phase 2 §2.2 — convert `moves.dat` into the expansion's move tables.

Source (under `$RPG2GBA_URANIUM_SRC/Data/`):

  moves.dat — flat 14-byte records, one per move ID 0..maxID, zero-padded for
  unused IDs. Pack format `"vCCCCCCvCvC"` (Compiler.rb:1239-1251):
    uint16 function_code   effect ID (Essentials PBMoveData function code)
    uint8  base_damage
    uint8  type            PBTypes index
    uint8  category        0=Physical 1=Special 2=Status
    uint8  accuracy
    uint8  total_pp
    uint8  effect_chance   additional-effect chance
    uint16 target          PBTargets bitflag value (080_PBTargets.rb)
    int8   priority        signed
    uint16 flags           bitfield, flag letters a..p -> bits 0..15
    uint8  dummy           legacy contest slot, always 0

Display names/descriptions are NOT in `moves.dat` — they come from the
`messages.dat` sidecars (`reference/move_names.json`,
`reference/move_descriptions.json`). Internal names (the id_map key) come from
`reference/move_internal_names.json` (dumped from the `PBMoves` script section).

Move *effects* are deliberately NOT mapped here. Essentials function codes
(324 distinct, range 0..361) have no formula to the fork's
`enum BattleMoveEffects`; mapping them is fidelity-sensitive Phase 6 engine
work (CLAUDE.md §9 / D3). Every move is emitted with `EFFECT_PLACEHOLDER`, and
the raw function code + effect chance for each is written to a worklist sidecar
(`intermediate/move_function_codes.json`) so nothing is lost.
"""
from __future__ import annotations

import json
import logging
import os
import struct
from dataclasses import dataclass
from pathlib import Path

from ._c_emit import escape_c_string, generated_banner, wrap_header
from ._id_map import IdMap
from ._naming import load_fork_constants, to_constant

logger = logging.getLogger(__name__)

MOVE_RECORD_SIZE = 14
_RECORD_STRUCT = struct.Struct("<HBBBBBBHBHB")
GENERATOR = "rpg2gba.pbs_converter.moves"

# Essentials Nuclear type index (Compiler.rb / PBTypes); these moves need the
# Phase 6 Nuclear-type engine work, so they're additionally flagged needs_engine.
NUCLEAR_TYPE_INDEX = 18

# Essentials category index -> expansion DAMAGE_CATEGORY_* (pokemon.h).
_CATEGORY_BY_INDEX: dict[int, str] = {
    0: "DAMAGE_CATEGORY_PHYSICAL",
    1: "DAMAGE_CATEGORY_SPECIAL",
    2: "DAMAGE_CATEGORY_STATUS",
}

# PBTargets (080_PBTargets.rb) -> expansion TARGET_* (battle.h). A couple of
# Essentials targets have no exact expansion equivalent and fall back to the
# closest single-target / user-side option (noted inline).
_TARGET_BY_VALUE: dict[int, str] = {
    0x000: "TARGET_SELECTED",        # SingleNonUser
    0x001: "TARGET_SELECTED",        # NoTarget (no clean equivalent)
    0x002: "TARGET_RANDOM",          # RandomOpposing
    0x004: "TARGET_BOTH",            # AllOpposing
    0x008: "TARGET_FOES_AND_ALLY",   # AllNonUsers
    0x010: "TARGET_USER",            # User
    0x020: "TARGET_USER",            # UserSide (closest)
    0x040: "TARGET_ALL_BATTLERS",    # BothSides
    0x080: "TARGET_OPPONENTS_FIELD", # OpposingSide
    0x100: "TARGET_ALLY",            # Partner
    0x200: "TARGET_USER_OR_ALLY",    # UserOrPartner
    0x400: "TARGET_OPPONENT",        # SingleOpposing
    0x800: "TARGET_SELECTED",        # OppositeOpposing (closest)
}

# Move flag bits (085__PokeBattle_Move.rb) -> expansion bool32 MoveInfo fields.
# Only the *positive* (directly-stated) flags are emitted. The inverse Essentials
# flags map to expansion "ignores*"/"banned" fields whose FALSE default already
# matches the common case, so emitting them risks inverting wrongly:
#   b (0x02) affected-by-Protect      -> ignoresProtect      (default FALSE ok)
#   e (0x10) Mirror-Move-copyable     -> mirrorMoveBanned    (default FALSE ok)
#   f (0x20) affected-by-King's-Rock  -> ignoresKingsRock    (default FALSE ok)
_FLAG_FIELD_BY_BIT: dict[int, str] = {
    0: "makesContact",      # a
    2: "magicCoatAffected", # c
    3: "snatchAffected",    # d
    6: "thawsUser",         # g
    8: "healingMove",       # i
    9: "punchingMove",      # j
    10: "soundMove",        # k
    11: "gravityBanned",    # l
    12: "skyBattleBanned",  # m
}
_FLAG_HIGH_CRIT_BIT = 7  # h: high critical-hit rate -> criticalHitStage = 1

# Uranium type internal names that don't map by `TYPE_<INTERNAL>`. Mirrors
# pokemon.py's table (kept in sync; QMARKS is the "???" type).
_TYPE_NAME_OVERRIDES: dict[str, str] = {"QMARKS": "TYPE_MYSTERY"}


@dataclass
class Move:
    """One move record. IDs are 0-based; ID 0 is MOVE_NONE."""

    id: int
    function_code: int   # Essentials effect ID (mapped to EFFECT_* in Phase 6)
    power: int
    type_index: int
    category: int
    accuracy: int
    pp: int
    effect_chance: int
    target: int
    priority: int        # signed
    flags: int
    internal_name: str = ""


def parse(path: Path) -> list[Move | None]:
    """Parse `moves.dat` into Move records indexed 0..max (gaps -> None)."""
    raw = Path(path).read_bytes()
    if len(raw) % MOVE_RECORD_SIZE != 0:
        raise ValueError(
            f"{path}: size {len(raw)} is not a multiple of {MOVE_RECORD_SIZE}"
        )
    count = len(raw) // MOVE_RECORD_SIZE
    out: list[Move | None] = [None] * count
    for mid in range(count):
        chunk = raw[mid * MOVE_RECORD_SIZE:(mid + 1) * MOVE_RECORD_SIZE]
        if chunk == b"\x00" * MOVE_RECORD_SIZE:
            continue  # default/unused slot (Compiler.rb defaultdata)
        out[mid] = _parse_one(mid, chunk)
    return out


def _parse_one(mid: int, raw: bytes) -> Move:
    func, dmg, typ, cat, acc, pp, eff, tgt, prio, flags, _dummy = _RECORD_STRUCT.unpack(raw)
    return Move(
        id=mid,
        function_code=func,
        power=dmg,
        type_index=typ,
        category=cat,
        accuracy=acc,
        pp=pp,
        effect_chance=eff,
        target=tgt,
        priority=prio - 256 if prio >= 128 else prio,
        flags=flags,
    )


def attach_internal_names(moves: list[Move | None], names_by_id: dict[int, str]) -> None:
    """Populate Move.internal_name from move_internal_names.json (fail-loud)."""
    missing: list[int] = []
    for m in moves:
        if m is None:
            continue
        name = names_by_id.get(m.id)
        if name is None:
            missing.append(m.id)
            continue
        m.internal_name = name
    if missing:
        raise ValueError(
            f"move_internal_names.json missing IDs: {missing[:10]}"
            f"{' (+more)' if len(missing) > 10 else ''}"
        )


# ===========================================================================
# C emit  (§2.2)
# ===========================================================================


def _load_id_json(path: Path) -> dict[int, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


@dataclass
class _MoveResolver:
    """Resolves Uranium move/type IDs to expansion constants via the IdMap.

    The MOVE_* naming rule is identical to pokemon.py's (display name through
    `_naming.to_constant`), so a move referenced from a learnset and the same
    move emitted here mint the same constant.
    """

    id_map: IdMap
    move_internal: dict[int, str]
    move_names: dict[int, str]
    move_descs: dict[int, str]
    type_internal: dict[int, str]
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

    def type_constant(self, type_idx: int) -> str:
        internal = self.type_internal.get(type_idx)
        if internal is None:
            raise ValueError(f"type index {type_idx} absent from type_internal_names.json")
        const = _TYPE_NAME_OVERRIDES.get(internal, to_constant("TYPE", internal))
        self.id_map.add("types", internal, const)
        return const

    def name(self, move_id: int) -> str:
        return self.move_names.get(move_id, self.move_internal.get(move_id, ""))

    def desc(self, move_id: int) -> str:
        return self.move_descs.get(move_id, "")


def _build_resolver(id_map: IdMap, ref: Path) -> _MoveResolver:
    fork_env = os.environ.get("RPG2GBA_POKEEMERALD")
    fork = Path(fork_env) if fork_env else None
    fork_moves = (
        load_fork_constants(fork / "include/constants/moves.h", "MOVE") if fork else set()
    )
    return _MoveResolver(
        id_map=id_map,
        move_internal=_load_id_json(ref / "move_internal_names.json"),
        move_names=_load_id_json(ref / "move_names.json"),
        move_descs=_load_id_json(ref / "move_descriptions.json"),
        type_internal=_load_id_json(ref / "type_internal_names.json"),
        fork_moves=fork_moves,
    )


def _target_constant(value: int) -> str:
    const = _TARGET_BY_VALUE.get(value)
    if const is None:
        raise ValueError(f"unknown Essentials move target value {value:#x}")
    return const


def _emit_flag_lines(flags: int) -> list[str]:
    lines: list[str] = []
    for bit, fld in _FLAG_FIELD_BY_BIT.items():
        if flags & (1 << bit):
            lines.append(f"        .{fld} = TRUE,")
    if flags & (1 << _FLAG_HIGH_CRIT_BIT):
        lines.append("        .criticalHitStage = 1,")
    return lines


def _emit_one(m: Move, r: _MoveResolver) -> str:
    """Return the C entry text for one move."""
    const = r.move_constant(m.id)
    cat = _CATEGORY_BY_INDEX.get(m.category)
    if cat is None:
        raise ValueError(f"{m.internal_name}: unknown category index {m.category}")

    lines: list[str] = [f"    [{const}] =", "    {"]
    lines.append(f'        .name = COMPOUND_STRING("{escape_c_string(r.name(m.id))}"),')
    desc = r.desc(m.id)
    if desc:
        lines.append(f'        .description = COMPOUND_STRING("{escape_c_string(desc)}"),')
    # Effect deferred to Phase 6 (see module docstring); raw code kept in worklist.
    effect_note = (
        f"        .effect = EFFECT_PLACEHOLDER,  // TODO Phase 6: Essentials function code "
        f"{m.function_code}"
    )
    if m.effect_chance:
        effect_note += f" (chance {m.effect_chance})"
    lines.append(effect_note)
    lines.append(f"        .power = {m.power},")
    lines.append(f"        .type = {r.type_constant(m.type_index)},")
    lines.append(f"        .accuracy = {m.accuracy},")
    lines.append(f"        .pp = {m.pp},")
    lines.append(f"        .target = {_target_constant(m.target)},")
    lines.append(f"        .priority = {m.priority},")
    lines.append(f"        .category = {cat},")
    lines.extend(_emit_flag_lines(m.flags))
    lines.append("    },")
    return "\n".join(lines)


def emit_moves_info(moves: list[Move | None], r: _MoveResolver) -> str:
    entries = [_emit_one(m, r) for m in moves if m is not None]
    banner = generated_banner(
        "moves.dat (+ move_names/move_descriptions.json sidecars)", GENERATOR, timestamp=False
    )
    note = (
        "// NOTE: .effect is EFFECT_PLACEHOLDER for every move. Essentials\n"
        "// function codes have no direct map to enum BattleMoveEffects; that\n"
        "// mapping is Phase 6 work. Raw codes are in intermediate/\n"
        "// move_function_codes.json. Inverse flags (Protect/Mirror Move/King's\n"
        "// Rock affinity) are left at struct default — see moves.py.\n"
    )
    includes = (
        '#include "constants/moves.h"\n'
        '#include "constants/battle.h"\n'
        '#include "constants/battle_move_effects.h"\n'
        '#include "constants/pokemon.h"\n'
    )
    head = "const struct MoveInfo gMovesInfo[] =\n{\n"
    return banner + note + "\n" + includes + "\n" + head + "\n".join(entries) + "\n};\n"


def emit_constants(moves: list[Move | None], r: _MoveResolver) -> str:
    lines = ["#define MOVE_NONE 0"]
    for m in moves:
        if m is None:
            continue
        lines.append(f"#define {r.move_constant(m.id)} {m.id}")
    banner = generated_banner("moves.dat + Constants.rxdata", GENERATOR, timestamp=False)
    note = (
        "// NOTE: these are Uranium's own move IDs. They overlap vanilla MOVE_*\n"
        "// numbering — V6 integration must reconcile them with the fork enum.\n"
    )
    return wrap_header("GUARD_URANIUM_CONSTANTS_MOVES_H", note + "\n".join(lines), banner=banner)


def run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None:
    """Phase 2 §2.2 entry point: parse moves and emit C tables + worklist."""
    moves = parse(uranium_src / "Data" / "moves.dat")
    ref = _reference_dir()
    attach_internal_names(moves, _load_id_json(ref / "move_internal_names.json"))
    r = _build_resolver(id_map, ref)

    # Pre-mint every move constant so the worklist and learnset cross-refs agree,
    # and additionally flag Nuclear-type moves as needs_engine (Phase 6).
    for m in moves:
        if m is None:
            continue
        const = r.move_constant(m.id)
        if m.type_index == NUCLEAR_TYPE_INDEX:
            id_map.mark_needs_engine("moves", const)

    inc = out_dir / "include" / "constants"
    data = out_dir / "src" / "data"
    inter = out_dir / "intermediate"
    for d in (inc, data, inter):
        d.mkdir(parents=True, exist_ok=True)

    (inc / "moves.h").write_text(emit_constants(moves, r), encoding="utf-8")
    (data / "moves_info.h").write_text(emit_moves_info(moves, r), encoding="utf-8")

    # Phase 6 worklist: every move's raw Essentials effect code + chance, keyed
    # by the minted MOVE_* constant. Nothing about move effects is lost here.
    worklist = {
        r.move_constant(m.id): {
            "function_code": m.function_code,
            "effect_chance": m.effect_chance,
        }
        for m in moves
        if m is not None
    }
    (inter / "move_function_codes.json").write_text(
        json.dumps(dict(sorted(worklist.items())), indent=2) + "\n", encoding="utf-8"
    )

    n = sum(1 for m in moves if m is not None)
    logger.info("emitted move data for %d moves (effects deferred to Phase 6)", n)
