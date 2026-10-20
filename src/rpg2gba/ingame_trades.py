"""NPC in-game trades: Uranium `pbStartTrade` -> native pokeemerald `sIngameTrades[]` rows.

Single source of truth for trade specs (CLAUDE.md §4.3). Operator ruling
2026-10-09: each Uranium trade becomes ONE native in-game trade row with FIXED,
vanilla-style values; the received mon's level is copied from the given mon by
the engine (matches Essentials).

Uranium shape (Map046 EV014 page 0)::

    pbChoosePokemon(1,3, proc {|poke| !poke.egg? and poke.species==PBSpecies::FARTOG })
    ...
    pbStartTrade(pbGet(1), PBSpecies::BAASHAUN, "Yuoaman", "Baro"[, gender])

RMXP splits each script over a 355 command plus 655 continuations; they are
joined (newline-separated) before matching. The requested species comes from the
nearest preceding `pbChoosePokemon` with the same variable on the same page, and
only the exact filter "not egg and species == X" is understood: anything else
raises (CLAUDE.md §4.5). Species resolve exactly as the transpiler's
`TranspileContext.staged_species_constant` does (id map hit AND staged or
vanilla-reuse), failing loud otherwise.

Fixed values: ivs all 15, abilityNum 0, conditions 0, sheen 0, no held item, no
mail; `personality` and `otId` are crc32 hashes of the const name, so output is
idempotent across runs.

The generated fragments (`constants/rpg2gba_ingame_trades.gen.h`,
`data/rpg2gba_ingame_trade_table.gen.h`) are `#include`d by fenced hooks in the
vendored `include/constants/trade.h` and `src/data/trade.h`.
"""
from __future__ import annotations

import json
import re
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.map_split.ids import origin_of
from rpg2gba.pbs_converter._id_map import IdMap

GENERATOR = "rpg2gba.ingame_trades"
MEMBERS_MACRO = "RPG2GBA_INGAME_TRADE_MEMBERS"
ENUM_FILENAME = "rpg2gba_ingame_trades.gen.h"
TABLE_FILENAME = "rpg2gba_ingame_trade_table.gen.h"

#: Fixed vanilla-style values (operator ruling 2026-10-09).
FIXED_IV = 15
NUM_STATS = 6
CONTEST_CATEGORIES_COUNT = 5

_SCRIPT_CODE = 355
_SCRIPT_CONT = 655

_CHOOSE_ANY_RE = re.compile(r"pbChoosePokemon\s*\(\s*(\d+)")
_CHOOSE_RE = re.compile(
    r"pbChoosePokemon\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*proc\s*\{\s*\|(\w+)\|\s*"
    r"!\s*\3\.egg\?\s*(?:and|&&)\s*\3\.species\s*==\s*PBSpecies::(\w+)\s*\}\s*\)\s*$"
)
_TRADE_RE = re.compile(
    r'pbStartTrade\s*\(\s*pbGet\s*\(\s*(\d+)\s*\)\s*,\s*PBSpecies::(\w+)\s*,\s*'
    r'"([^"\\]*)"\s*,\s*"([^"\\]*)"\s*(?:,\s*([01])\s*)?\)\s*$'
)


@dataclass(frozen=True)
class InGameTradeSpec:
    const: str  # INGAME_TRADE_MAP046_EV014
    map_id: int  # the scanned map uid (a split piece uid for pieces)
    event_id: int
    page: int
    species: str  # SPECIES_* given to the player
    requested_species: str  # SPECIES_* the player must hand over
    nickname: str
    ot_name: str
    ot_gender: int  # 0 male, 1 female
    personality: int
    ot_id: int


@dataclass(frozen=True)
class NameLimits:
    pokemon_name: int
    trainer_name: int


def trade_const(map_id: int, event_id: int) -> str:
    """`INGAME_TRADE_MAP<origin>_EV<event>` — a split piece names by its origin map."""
    return f"INGAME_TRADE_MAP{origin_of(map_id):03d}_EV{event_id:03d}"


def load_name_limits(fork: Path) -> NameLimits:
    """POKEMON_NAME_LENGTH / TRAINER_NAME_LENGTH from the fork's global.h (§4.7)."""
    text = (fork / "include" / "constants" / "global.h").read_text(encoding="utf-8")
    found: dict[str, int] = {}
    for name in ("POKEMON_NAME_LENGTH", "TRAINER_NAME_LENGTH"):
        m = re.search(rf"^#define\s+{name}\s+(\d+)\s*$", text, re.M)
        if m is None:
            raise ValueError(f"{name} not found as a plain integer #define in {fork}")
        found[name] = int(m.group(1))
    return NameLimits(found["POKEMON_NAME_LENGTH"], found["TRAINER_NAME_LENGTH"])


def load_species_resolver(
    reference_dir: Path, species_manifest_path: Path
) -> Callable[[str], str | None]:
    """Internal name -> SPECIES_* iff defined in the fork: same rule and sources as
    `TranspileContext.staged_species_constant` (id map + needs_engine + staging manifest)."""
    id_map = IdMap.load(reference_dir / "uranium_id_map.json")
    species = dict(id_map.by_category["species"])
    needs_engine = set(id_map.needs_engine["species"])
    vanilla = {c for c in species.values() if c not in needs_engine}
    staged: set[str] = set()
    if species_manifest_path.is_file():
        manifest = json.loads(species_manifest_path.read_text(encoding="utf-8"))
        staged = {e["species_constant"] for e in manifest["species"]}

    def resolve(internal_name: str) -> str | None:
        const = species.get(internal_name)
        if const is not None and (const in staged or const in vanilla):
            return const
        return None

    return resolve


def _script_blocks(page: Mapping) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for cmd in page.get("list", []):
        code = cmd.get("code")
        params = cmd.get("parameters", [])
        if code == _SCRIPT_CODE:
            if current is not None:
                blocks.append("\n".join(current))
            current = [str(params[0]) if params else ""]
        elif code == _SCRIPT_CONT:
            if current is None:
                raise ValueError("script continuation (655) with no preceding 355 command")
            current.append(str(params[0]) if params else "")
        else:
            if current is not None:
                blocks.append("\n".join(current))
                current = None
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def _where(map_id: int, event: Mapping, page_no: int) -> str:
    return f"map {map_id} event {event.get('id')} ({event.get('name')!r}) page {page_no}"


def _check_string(what: str, value: str, limit: int, where: str) -> None:
    if len(value) > limit:
        raise ValueError(f"{where}: {what} {value!r} is {len(value)} chars; fork limit {limit}")
    if not value.isascii() or not value.isprintable():
        raise ValueError(f"{where}: {what} {value!r} has non-ASCII/unprintable characters")


def detect_trades_in_map(
    map_json: Mapping,
    map_id: int,
    resolve_species: Callable[[str], str | None],
    limits: NameLimits,
) -> list[InGameTradeSpec]:
    specs: list[InGameTradeSpec] = []
    for event in map_json.get("events", []):
        for page_no, page in enumerate(event.get("pages", [])):
            where = _where(map_id, event, page_no)
            last_choose: dict[int, str | None] = {}  # var -> requested internal name | None
            for block in _script_blocks(page):
                stripped = block.strip()
                cm = _CHOOSE_ANY_RE.search(stripped)
                if cm is not None:
                    var = int(cm.group(1))
                    fm = _CHOOSE_RE.search(stripped)
                    last_choose[var] = fm.group(4) if fm else None
                    if fm is None and "proc" in stripped:
                        raise ValueError(
                            f"{where}: unsupported pbChoosePokemon filter (only "
                            f"'!poke.egg? and poke.species==PBSpecies::X' is understood): "
                            f"{stripped!r}"
                        )
                    continue
                if "pbStartTrade" not in stripped:
                    continue
                tm = _TRADE_RE.search(stripped)
                if tm is None:
                    raise ValueError(f"{where}: unparseable pbStartTrade call: {stripped!r}")
                var = int(tm.group(1))
                if last_choose.get(var) is None:
                    raise ValueError(
                        f"{where}: pbStartTrade(pbGet({var}), ...) has no preceding "
                        f"pbChoosePokemon({var}, ..., proc {{...}}) species filter on this page"
                    )
                given = resolve_species(tm.group(2))
                if given is None:
                    raise ValueError(f"{where}: given species {tm.group(2)} not staged/defined")
                wanted = resolve_species(last_choose[var])
                if wanted is None:
                    raise ValueError(f"{where}: requested species {last_choose[var]} not staged/defined")
                nickname, ot_name = tm.group(3), tm.group(4)
                _check_string("nickname", nickname, limits.pokemon_name, where)
                _check_string("OT name", ot_name, limits.trainer_name, where)
                const = trade_const(map_id, int(event["id"]))
                specs.append(
                    InGameTradeSpec(
                        const=const,
                        map_id=map_id,
                        event_id=int(event["id"]),
                        page=page_no,
                        species=given,
                        requested_species=wanted,
                        nickname=nickname,
                        ot_name=ot_name,
                        ot_gender=int(tm.group(5) or 0),
                        personality=zlib.crc32(const.encode("ascii")) & 0xFFFFFFFF,
                        ot_id=zlib.crc32((const + ":otId").encode("ascii")) & 0xFFFFFFFF,
                    )
                )
    return specs


def scan_trades(
    maps_dir: Path,
    map_ids: Iterable[int],
    resolve_species: Callable[[str], str | None],
    limits: NameLimits,
) -> list[InGameTradeSpec]:
    """All trades over `map_ids` (scan the build's maps/ dir, which holds split pieces
    not the presplit original). Sorted by (map, event); duplicate consts fail loud."""
    specs: list[InGameTradeSpec] = []
    for mid in map_ids:
        path = maps_dir / f"Map{mid:03d}.json"
        if not path.is_file():
            raise FileNotFoundError(f"{path} missing — deserialize the map before staging trades")
        specs.extend(
            detect_trades_in_map(json.loads(path.read_text(encoding="utf-8")), mid,
                                 resolve_species, limits)
        )
    specs.sort(key=lambda s: (s.map_id, s.event_id, s.page))
    seen: set[str] = set()
    for s in specs:
        if s.const in seen:
            raise ValueError(f"duplicate trade const {s.const} (two trades on one origin event)")
        seen.add(s.const)
    return specs


def _banner(kind: str) -> str:
    return (
        f"// DO NOT EDIT — generated by {GENERATOR}\n"
        f"// {kind}\n"
        "// source: output/uranium-build/maps/Map*.json (pbStartTrade events)\n"
    )


def _provenance(s: InGameTradeSpec) -> str:
    return f"// {s.const}: map {s.map_id} EV{s.event_id:03d} page {s.page}\n"


def emit_enum(specs: Sequence[InGameTradeSpec]) -> str:
    """`constants/rpg2gba_ingame_trades.gen.h` — defines MEMBERS_MACRO, expanded inside
    `enum InGameTradeID` (a macro, not an in-enum #include: see the rematch hook)."""
    head = _banner(f"INGAME_TRADE_* enum members, expanded by {MEMBERS_MACRO}.")
    if not specs:
        return head + "// (no Uranium in-game trades in this build set)\n" + f"#define {MEMBERS_MACRO}\n"
    prov = "".join(_provenance(s) for s in specs)
    body = " \\\n".join(f"    {s.const}," for s in specs)
    return head + prov + f"#define {MEMBERS_MACRO} \\\n" + body + "\n"


def emit_table(specs: Sequence[InGameTradeSpec]) -> str:
    """`data/rpg2gba_ingame_trades.gen.h` — rows included inside `sIngameTrades[]`."""
    head = _banner("sIngameTrades[] rows, #included after the vanilla rows.")
    if not specs:
        return head + "// (no Uranium in-game trades in this build set)\n"
    ivs = ", ".join([str(FIXED_IV)] * NUM_STATS)
    conds = ", ".join(["0"] * CONTEST_CATEGORIES_COUNT)
    rows = []
    for s in specs:
        rows.append(
            f"    [{s.const}] =\n"
            "    {\n"
            f'        .nickname = _("{s.nickname}"),\n'
            f"        .species = {s.species},\n"
            f"        .ivs = {{{ivs}}},\n"
            "        .abilityNum = 0,\n"
            f"        .otId = {s.ot_id},\n"
            f"        .conditions = {{{conds}}},\n"
            f"        .personality = {s.personality:#010x},\n"
            "        .heldItem = ITEM_NONE,\n"
            "        .mailNum = -1,\n"
            f'        .otName = _("{s.ot_name}"),\n'
            f"        .otGender = {'FEMALE' if s.ot_gender else 'MALE'},\n"
            "        .sheen = 0,\n"
            f"        .requestedSpecies = {s.requested_species}\n"
            "    },\n"
        )
    return head + "".join(_provenance(s) for s in specs) + "".join(rows)


def build_manifest_records(specs: Sequence[InGameTradeSpec]) -> list[dict]:
    return [
        {
            "const": s.const, "map_id": s.map_id, "event_id": s.event_id, "page": s.page,
            "species": s.species, "requested_species": s.requested_species,
            "nickname": s.nickname, "ot_name": s.ot_name, "ot_gender": s.ot_gender,
        }
        for s in specs
    ]
