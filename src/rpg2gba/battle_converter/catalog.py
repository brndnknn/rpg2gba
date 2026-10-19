"""Which moves, abilities and machines to generate, and how each behaves."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rpg2gba.pbs_converter import items as pbs_items
from rpg2gba.pbs_converter import moves as pbs_moves
from rpg2gba.pbs_converter._id_map import IdMap
from rpg2gba.pbs_converter._naming import load_fork_constants

from .function_codes import FUNCTION_CODES, AddedEffect, EffectSpec, effect_for

logger = logging.getLogger(__name__)

REFERENCE = Path(__file__).resolve().parents[3] / "reference"
ID_MAP_PATH = REFERENCE / "uranium_id_map.json"
RULINGS_PATH = REFERENCE / "battle_rulings.json"

MoveKind = Literal["generate", "alias", "blocked"]
AbilityKind = Literal["implemented", "inert"]
_MOVE_KINDS = frozenset({"generate", "alias", "blocked"})
_ABILITY_KINDS = frozenset({"implemented", "inert"})
_CATEGORIES = {0: "DAMAGE_CATEGORY_PHYSICAL", 1: "DAMAGE_CATEGORY_SPECIAL",
               2: "DAMAGE_CATEGORY_STATUS"}
_MACHINE_RE = re.compile(r"^(TM|HM)(\d+)$")


@dataclass(frozen=True)
class GenMove:
    uranium_id: int
    internal: str
    constant: str
    name: str
    description: str             # shown in game: the ruling's rewrite, else Uranium's
    uranium_description: str
    kind: MoveKind
    type_: str = ""
    power: int = 0
    accuracy: int = 0
    pp: int = 0
    category: str = ""
    target: str = ""
    priority: int = 0
    flag_lines: tuple[str, ...] = ()
    spec: EffectSpec | None = None
    effect_chance: int = 0
    anim: str = ""
    alias_of: str = ""
    reason: str = ""

    @property
    def ident(self) -> str:
        return "".join(p.capitalize() for p in self.constant.removeprefix("MOVE_").split("_"))


@dataclass(frozen=True)
class GenAbility:
    uranium_id: int
    internal: str
    constant: str
    name: str
    description: str
    uranium_description: str
    kind: AbilityKind
    reason: str = ""
    breakable: bool = False   # Mold Breaker and kin ignore it


@dataclass(frozen=True)
class Catalog:
    moves: tuple[GenMove, ...]        # generated, Uranium-id order
    aliases: tuple[GenMove, ...]
    blocked: tuple[GenMove, ...]
    abilities: tuple[GenAbility, ...]  # every one is generated (inert ones by name)
    tms: tuple[str, ...]               # MOVE_* per TM, TM01 first
    hms: tuple[str, ...]


def _rulings(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def generated_constants(*, id_map_path: Path = ID_MAP_PATH,
                        rulings_path: Path = RULINGS_PATH) -> frozenset[str]:
    """The `MOVE_*` / `ABILITY_*` constants the battle pass generates.

    From the two reference files alone, so the conversion-time gate accepts
    them before the assembler has run: generated and aliased moves, and every
    ruled ability."""
    id_map = json.loads(Path(id_map_path).read_text(encoding="utf-8"))
    rulings = _rulings(rulings_path)
    out = {id_map["moves"][i] for i, r in rulings["moves"].items() if r["kind"] != "blocked"}
    out |= {id_map["abilities"][i] for i in rulings["abilities"]}
    return frozenset(out)


def _load_ids(path: Path) -> dict[int, str]:
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def _added(raw: dict) -> AddedEffect:
    return AddedEffect(raw["moveEffect"], raw.get("chance", "always"), bool(raw.get("self")))


def _spec(ruling: dict, code: int, label: str) -> EffectSpec:
    """The function code's mapping, with the ruling's effect / argument /
    additional_effects replacing the matching parts. A game's custom code has
    no mapping, so its ruling must give the effect."""
    if "effect" not in ruling:
        return effect_for(code, label)
    base = FUNCTION_CODES.get(code)
    if "additional_effects" in ruling:
        added = tuple(_added(a) for a in ruling["additional_effects"])
    else:
        added = base.added if base else ()
    return EffectSpec(ruling["effect"], added,
                      ruling.get("argument", base.argument if base else None),
                      base.fields if base else ())


def _missing(id_map: dict, kind: str, stock: set[str]) -> list[str]:
    """`needs_engine` entries the engine really lacks. Entries the engine does
    define are stale id-map rows (named before the fork index read the whole
    enum) and are skipped, logged."""
    stale = sorted(c for c in id_map["needs_engine"][kind] if c in stock)
    if stale:
        logger.info("  %s: id map marks %s needs_engine, but the engine defines them",
                    kind, stale)
    return sorted(c for c in id_map["needs_engine"][kind] if c not in stock)


def _check_coverage(kind: str, missing: list[str], ruled: dict, internal_by_const: dict) -> None:
    missing_internals = {internal_by_const[c] for c in missing}
    unruled = sorted(missing_internals - set(ruled))
    stray = sorted(set(ruled) - missing_internals)
    if unruled:
        raise ValueError(f"battle_rulings.json has no {kind} ruling for {unruled}")
    if stray:
        raise ValueError(f"battle_rulings.json rules {kind} the engine already has: {stray}")


def build_catalog(uranium_src: Path, fork: Path, *, id_map_path: Path = ID_MAP_PATH,
                  rulings_path: Path = RULINGS_PATH,
                  reference_dir: Path = REFERENCE) -> Catalog:
    id_map = json.loads(Path(id_map_path).read_text(encoding="utf-8"))
    rulings = _rulings(rulings_path)
    data = Path(reference_dir) / "uranium_data"
    fork = Path(fork)
    stock_moves = load_fork_constants(fork / "include/constants/moves.h", "MOVE")
    stock_abilities = load_fork_constants(fork / "include/constants/abilities.h", "ABILITY")

    # --- moves --------------------------------------------------------------
    move_internal_by_const = {c: i for i, c in id_map["moves"].items()}
    missing_moves = _missing(id_map, "moves", stock_moves)
    _check_coverage("move", missing_moves, rulings["moves"], move_internal_by_const)
    records = pbs_moves.parse(Path(uranium_src) / "Data" / "moves.dat")
    pbs_moves.attach_internal_names(records, _load_ids(data / "move_internal_names.json"))
    resolver = pbs_moves._build_resolver(IdMap(), Path(reference_dir))
    by_internal = {m.internal_name: m for m in records if m is not None}

    moves: list[GenMove] = []
    for const in missing_moves:
        internal = move_internal_by_const[const]
        ruling = rulings["moves"][internal]
        kind = ruling["kind"]
        if kind not in _MOVE_KINDS:
            raise ValueError(f"{internal}: unknown move kind {kind!r}")
        rec = by_internal[internal]
        common = dict(uranium_id=rec.id, internal=internal, constant=const,
                      name=resolver.name(rec.id),
                      description=ruling.get("description") or resolver.desc(rec.id),
                      uranium_description=resolver.desc(rec.id), kind=kind)
        if kind == "blocked":
            moves.append(GenMove(**common, reason=ruling["reason"]))
            continue
        if kind == "alias":
            if ruling["of"] not in stock_moves:
                raise ValueError(f"{internal}: alias target {ruling['of']} is not a stock move")
            moves.append(GenMove(**common, alias_of=ruling["of"]))
            continue
        if rec.type_index == pbs_moves.NUCLEAR_TYPE_INDEX:
            raise ValueError(f"{internal} is Nuclear-type; the engine has no Nuclear type yet")
        anim = ruling.get("anim")
        if anim not in stock_moves:
            raise ValueError(f"{internal}: anim {anim!r} must name a stock move")
        moves.append(GenMove(
            **common,
            type_=resolver.type_constant(rec.type_index),
            power=int(ruling.get("power", rec.power)),
            accuracy=rec.accuracy,
            pp=rec.pp,
            category=ruling.get("category", _CATEGORIES[rec.category]),
            target=ruling.get("target", pbs_moves._target_constant(rec.target)),
            priority=rec.priority,
            flag_lines=tuple(pbs_moves._emit_flag_lines(rec.flags)),
            spec=_spec(ruling, rec.function_code, internal),
            effect_chance=rec.effect_chance,
            anim=anim,
        ))
    moves.sort(key=lambda g: g.uranium_id)

    # --- abilities ----------------------------------------------------------
    ability_internal_by_const = {c: i for i, c in id_map["abilities"].items()}
    missing_abilities = _missing(id_map, "abilities", stock_abilities)
    _check_coverage("ability", missing_abilities, rulings["abilities"], ability_internal_by_const)
    a_internal = _load_ids(data / "ability_internal_names.json")
    a_names = _load_ids(data / "ability_names.json")
    a_descs = _load_ids(data / "ability_descriptions.json")
    a_id_by_internal = {v: k for k, v in a_internal.items()}
    abilities: list[GenAbility] = []
    for const in missing_abilities:
        internal = ability_internal_by_const[const]
        ruling = rulings["abilities"][internal]
        if ruling["kind"] not in _ABILITY_KINDS:
            raise ValueError(f"{internal}: unknown ability kind {ruling['kind']!r}")
        aid = a_id_by_internal[internal]
        abilities.append(GenAbility(
            uranium_id=aid, internal=internal, constant=const,
            name=a_names.get(aid) or internal,
            description=ruling.get("description") or a_descs.get(aid, ""),
            uranium_description=a_descs.get(aid, ""),
            kind=ruling["kind"], reason=ruling.get("reason", ""),
            breakable=bool(ruling.get("breakable", False)),
        ))
    abilities.sort(key=lambda g: g.uranium_id)

    generated = {g.constant for g in moves if g.kind == "generate"}
    tms, hms = _machines(uranium_src, data, resolver, rulings.get("machines", {}),
                         stock_moves | generated | {g.constant for g in moves if g.kind == "alias"})
    return Catalog(
        moves=tuple(g for g in moves if g.kind == "generate"),
        aliases=tuple(g for g in moves if g.kind == "alias"),
        blocked=tuple(g for g in moves if g.kind == "blocked"),
        abilities=tuple(abilities),
        tms=tms, hms=hms,
    )


def _machines(uranium_src: Path, data: Path, resolver, ruled: dict,
              known: set[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """MOVE_* per TM and per HM, numbered order, from the game's machine items."""
    items = pbs_items.parse(Path(uranium_src) / "Data" / "items.dat")
    pbs_items.attach_internal_names(items, pbs_items._load_id_json(
        data / "item_internal_names.json"))
    numbered: dict[str, dict[int, str]] = {"TM": {}, "HM": {}}
    for it in items:
        m = _MACHINE_RE.match(it.internal_name)
        if not it.machine_move or not m:
            continue
        numbered[m.group(1)][int(m.group(2))] = it.internal_name
    seen: dict[str, str] = {}
    out: dict[str, list[str]] = {"TM": [], "HM": []}
    by_internal = {it.internal_name: it for it in items}
    for kind in ("TM", "HM"):
        nums = sorted(numbered[kind])
        if nums != list(range(1, len(nums) + 1)):
            raise ValueError(f"{kind} numbers are not contiguous from 1: {nums}")
        for n in nums:
            machine = numbered[kind][n]
            move = resolver.move_constant(by_internal[machine].machine_move)
            ruling = ruled.get(machine)
            if move in seen:
                if not ruling:
                    raise ValueError(
                        f"{machine} teaches {move}, which {seen[move]} already teaches; the "
                        "engine needs one move per machine -- add a placeholder ruling")
                move = ruling["placeholder"]
            elif ruling:
                raise ValueError(f"{machine}: placeholder ruling for a machine with a unique move")
            if move not in known:
                raise ValueError(f"{machine} teaches {move}, which the engine will not define")
            seen[move] = machine
            out[kind].append(move)
    stray = sorted(set(ruled) - {"_doc"} - set(seen.values()))
    if stray:
        raise ValueError(f"battle_rulings.json machines rules unknown machines: {stray}")
    return tuple(out["TM"]), tuple(out["HM"])
