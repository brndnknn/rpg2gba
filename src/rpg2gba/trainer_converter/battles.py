"""W6 -- trainer battle-data staging: engine trainer id constants + `.party`
entries for `common.SLICE_TRAINER_BATTLES` (Route 1's nine trainers plus the
three existing Theo counter-pick entries).

Reuses the Phase-2 `pbs_converter.trainers` **intermediate JSON**
(`output/uranium-build/intermediate/{trainers,trainer_types}.json`) -- never
its emitter -- as the source of truth for party/class/gender data, and emits:

  - a `TRAINER_*` id constants header, chained off the pristine fork anchor
    `TRAINER_MAY_PLACEHOLDER` (mirrors `species_converter.stage`'s
    `SPECIES_EGG`-anchor chaining), plus a staged-count symbol so the
    engine's TRAINERS_COUNT provisioning never needs a hand-edited number
    per chapter;
  - a `.party`-DSL text fragment (`tools/trainerproc` input, NOT C) for every
    staged trainer.

This module does not touch anything under `engine/`; `stage.py` writes the
generated files into the trainer staging dir, and a later step (the lead's
`assemble_pathfinder.py`) stages them into the vendored fork behind committed
`URANIUM PATHFINDER SLICE` include-hooks.

**Trainer Class / Music / Gender resolution (CLAUDE.md §4.7):** Uranium's own
minted `trainer_class` constant spelling (`trainers.json`'s `trainer_class`
field, e.g. `TRAINER_CLASS_BUGCATCHER`) does NOT always match the real fork
spelling (`TRAINER_CLASS_BUG_CATCHER`) -- Phase 2's `to_constant()` derives
its constant from Uranium's own `trainertypes.dat` internal name, which was
never checked against the fork. This module instead derives the candidate
constant from `trainer_types.json`'s *display* `name` field
(`to_constant("TRAINER_CLASS", "BUG CATCHER")` -> `TRAINER_CLASS_BUG_CATCHER`,
the same transform `tools/trainerproc`'s own `fprint_constant` applies to a
literal `Class:` value) and verifies the result against the live fork header
before ever writing it -- fail loud on a class that doesn't resolve, never
invent or silently substitute.

`Music:` has no Uranium analog at all (`trainer_types.json`'s battle/win/intro
bgm fields are literal Uranium audio filenames, not engine
`TRAINER_ENCOUNTER_MUSIC_*` symbols) so `_CLASS_ENCOUNTER_MUSIC` hand-maps
each of the eight classes this slice touches to the vanilla encounter-music
family documented directly in the fork's own comments
(`include/constants/trainers.h` "Used for ..." annotations next to each
`TRAINER_ENCOUNTER_MUSIC_*` -- Fishermen -> HIKER, Youngsters/Bug Catchers/
male-running Triathletes -> MALE, female School Kids -> GIRL, Experts ->
INTENSE, Lasses -> FEMALE). RIVAL -> MALE matches the existing hand-written
Theo fence (retained for continuity, not re-derived from a fork comment --
Rival isn't in that annotated list).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.pbs_converter._naming import to_constant
from rpg2gba.trainer_converter import common

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.trainer_converter.battles"

# --- Class -> Pic / Music resolution (verified against the fork, §4.7) ------

#: Real `TRAINER_CLASS_*` constant -> the `internal_name` staged into
#: `common.SLICE_TRAINER_PICS` for that class's battle sprite.
_CLASS_PIC_INTERNAL_NAME: dict[str, str] = {
    "TRAINER_CLASS_FISHERMAN": "FISHERMAN",
    "TRAINER_CLASS_YOUNGSTER": "YOUNGSTER",
    "TRAINER_CLASS_BUG_CATCHER": "BUGCATCHER",
    "TRAINER_CLASS_SCHOOL_KID": "SCHOOLKID",
    "TRAINER_CLASS_TRIATHLETE": "TRIATHLETE_MALERUNNER",
    "TRAINER_CLASS_EXPERT": "EXPERT_FEMALE",
    "TRAINER_CLASS_LASS": "LASS",
    "TRAINER_CLASS_RIVAL": "RIVAL",
}

#: Real `TRAINER_CLASS_*` constant -> real `TRAINER_ENCOUNTER_MUSIC_*`
#: constant. See module docstring for the fork-comment provenance of each row.
_CLASS_ENCOUNTER_MUSIC: dict[str, str] = {
    "TRAINER_CLASS_FISHERMAN": "TRAINER_ENCOUNTER_MUSIC_HIKER",
    "TRAINER_CLASS_YOUNGSTER": "TRAINER_ENCOUNTER_MUSIC_MALE",
    "TRAINER_CLASS_BUG_CATCHER": "TRAINER_ENCOUNTER_MUSIC_MALE",
    "TRAINER_CLASS_SCHOOL_KID": "TRAINER_ENCOUNTER_MUSIC_GIRL",
    "TRAINER_CLASS_TRIATHLETE": "TRAINER_ENCOUNTER_MUSIC_MALE",
    "TRAINER_CLASS_EXPERT": "TRAINER_ENCOUNTER_MUSIC_INTENSE",
    "TRAINER_CLASS_LASS": "TRAINER_ENCOUNTER_MUSIC_FEMALE",
    "TRAINER_CLASS_RIVAL": "TRAINER_ENCOUNTER_MUSIC_MALE",
}

_TRAINER_ANCHOR_RE_TMPL = r"^#define\s+{anchor}\s+(\d+)\s*$"


# ===========================================================================
# Pristine-anchor reading
# ===========================================================================


def read_pristine_trainer_anchor(engine_dir: Path) -> int:
    """Read `TRAINER_MAY_PLACEHOLDER`'s pristine numeric value from
    `include/constants/opponents.h`.

    Fails loud if the anchor line has drifted from the pinned shape this
    emitter was verified against (CLAUDE.md §4.2 drift guard, mirrors
    `species_converter.stage.read_pristine_species_egg`).
    """
    path = engine_dir / "include" / "constants" / "opponents.h"
    text = path.read_text(encoding="utf-8")
    pattern = _TRAINER_ANCHOR_RE_TMPL.format(anchor=re.escape(common.PRISTINE_TRAINER_ANCHOR))
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        raise ValueError(
            f"{path}: expected '#define {common.PRISTINE_TRAINER_ANCHOR} <N>' line, not found. "
            "Fork header has drifted from the pinned shape this emitter was verified against."
        )
    value = int(m.group(1))
    if value != common.PRISTINE_TRAINER_MAY_PLACEHOLDER:
        raise ValueError(
            f"{path}: {common.PRISTINE_TRAINER_ANCHOR} read as {value}, but "
            f"common.PRISTINE_TRAINER_MAY_PLACEHOLDER={common.PRISTINE_TRAINER_MAY_PLACEHOLDER} -- "
            "the fork header has moved; update common.py's pinned constant."
        )
    return value


# ===========================================================================
# Intermediate JSON loading
# ===========================================================================


def load_trainers_json(intermediate_dir: Path) -> dict:
    path = intermediate_dir / "trainers.json"
    return json.loads(path.read_text(encoding="utf-8"))["trainers"]


def load_trainer_types_json(intermediate_dir: Path) -> dict:
    path = intermediate_dir / "trainer_types.json"
    return json.loads(path.read_text(encoding="utf-8"))["trainer_classes"]


def load_species_manifest_constants(species_manifest_path: Path | None) -> set[str]:
    """`species_constant` values actually staged by `species_converter.stage`
    -- mirrors the fork-capability gate's own species-manifest scoping
    (`conversion_agent.fork_index.registry_extra_symbols`): a species that
    merely appears in `reference/uranium_id_map.json` but hasn't been staged
    must still be rejected here, same as at the gate.
    """
    if species_manifest_path is None or not species_manifest_path.is_file():
        return set()
    manifest = json.loads(species_manifest_path.read_text(encoding="utf-8"))
    return {entry["species_constant"] for entry in manifest["species"]}


# ===========================================================================
# Resolve + verify
# ===========================================================================


@dataclass(frozen=True)
class StagedTrainerBattle:
    """One selected trainer, resolved and ready to emit.

    `trainer_key` is the identity `pbs_converter.trainers` minted into
    `trainers.json` -- it IS the final engine `TRAINER_*` constant name (no
    renaming happens in this module).
    """

    trainer_key: str
    fork_id: int
    uranium_trainer_id: int
    name: str
    trainer_class_constant: str
    gender_constant: str
    encounter_music_constant: str
    pic_constant: str
    items: list[str]
    party: list[dict]


def _class_display_name(trainer_class_const: str, trainer_types: dict) -> str:
    tt = trainer_types.get(trainer_class_const)
    if tt is None:
        raise ValueError(
            f"trainer_types.json has no entry for {trainer_class_const} "
            "(trainers.json references a class trainer_types.json doesn't define)"
        )
    return tt["name"]


def resolve_trainer_class(
    trainer_class_const_uranium: str, trainer_types: dict, fork_classes: set[str]
) -> str:
    """Real fork `TRAINER_CLASS_*` constant for a trainers.json class key.

    `trainer_class_const_uranium` is Uranium's OWN minted spelling (may not
    match the fork); the real candidate is derived from `trainer_types.json`'s
    display name via the same uppercase/underscore transform
    `tools/trainerproc`'s `fprint_constant` applies to a literal `Class:`
    value (see module docstring). Fails loud if the result isn't a real fork
    constant -- never invented, never silently substituted (CLAUDE.md §4.7).
    """
    display_name = _class_display_name(trainer_class_const_uranium, trainer_types)
    candidate = to_constant("TRAINER_CLASS", display_name)
    if candidate not in fork_classes:
        raise ValueError(
            f"{trainer_class_const_uranium} (display name {display_name!r}) resolves to "
            f"{candidate}, which is not a TRAINER_CLASS_* constant the fork defines -- "
            "verify include/constants/trainers.h, do not invent one"
        )
    return candidate


def resolve_gender(gender_str: str, fork_genders: set[str]) -> str:
    candidate = to_constant("TRAINER_GENDER", gender_str)
    if candidate not in fork_genders:
        raise ValueError(
            f"trainer gender {gender_str!r} resolves to {candidate}, which is not a "
            "TRAINER_GENDER_* constant the fork defines"
        )
    return candidate


def resolve_encounter_music(class_const: str, fork_music: set[str]) -> str:
    music = _CLASS_ENCOUNTER_MUSIC.get(class_const)
    if music is None:
        raise ValueError(
            f"{class_const}: no encounter-music mapping -- _CLASS_ENCOUNTER_MUSIC must be "
            "extended (sourced from include/constants/trainers.h's own class annotations) "
            "before this class can be staged"
        )
    if music not in fork_music:
        raise ValueError(f"{music}: not a TRAINER_ENCOUNTER_MUSIC_* constant the fork defines")
    return music


def resolve_pic_constant(class_const: str, staged_pic_internal_names: set[str]) -> str:
    internal_name = _CLASS_PIC_INTERNAL_NAME.get(class_const)
    if internal_name is None:
        raise ValueError(
            f"{class_const}: no pic mapping -- _CLASS_PIC_INTERNAL_NAME must be extended "
            "before this class can be staged"
        )
    if internal_name not in staged_pic_internal_names:
        raise ValueError(
            f"{class_const}: pic internal_name {internal_name!r} is not staged in "
            "common.SLICE_TRAINER_PICS -- append it there first"
        )
    for spec in common.SLICE_TRAINER_PICS:
        if spec.internal_name == internal_name:
            return spec.pic_constant
    raise AssertionError("unreachable: internal_name checked present above")


def verify_party_species(
    party: list[dict], fork_species: set[str], staged_species: set[str]
) -> None:
    available = fork_species | staged_species
    missing = sorted({m["species"] for m in party if m["species"] not in available})
    if missing:
        raise ValueError(
            f"species not available (neither in the fork nor in the staged species overlay): "
            f"{missing} -- convert these species first (species_converter), do not invent "
            "or substitute"
        )


def verify_party_moves(party: list[dict], fork_moves: set[str]) -> None:
    missing = sorted(
        {mv for m in party for mv in m.get("moves", []) if mv not in fork_moves}
    )
    if missing:
        raise ValueError(f"moves not defined in the fork: {missing}")


def verify_party_items(party: list[dict], fork_items: set[str]) -> None:
    missing = sorted(
        {m["item"] for m in party if m.get("item") and m["item"] not in fork_items}
    )
    if missing:
        raise ValueError(f"items not defined in the fork: {missing}")


def build_staged_battles(
    selected_keys: tuple[str, ...],
    trainers: dict,
    trainer_types: dict,
    pristine_trainer_anchor_value: int,
    *,
    fork_classes: set[str],
    fork_genders: set[str],
    fork_music: set[str],
    fork_species: set[str],
    fork_moves: set[str],
    fork_items: set[str],
    staged_species: set[str],
    staged_pic_internal_names: set[str],
) -> list[StagedTrainerBattle]:
    """Resolve every selected trainer key, assigning fork ids by position off
    `pristine_trainer_anchor_value` (append-only -- never renumber).

    Raises `ValueError` (with every offending trainer's problems collected,
    not just the first) if any selected trainer references data that isn't
    actually available yet -- an unstaged species, an unmapped class, etc.
    This is deliberately loud rather than skipping the trainer: a pinned
    selection that can't be fully staged is a corpus-readiness gap, not
    something to paper over.
    """
    staged: list[StagedTrainerBattle] = []
    errors: list[str] = []

    for i, key in enumerate(selected_keys):
        rec = trainers.get(key)
        if rec is None:
            errors.append(f"{key}: not present in trainers.json")
            continue
        try:
            class_const = resolve_trainer_class(rec["trainer_class"], trainer_types, fork_classes)
            tt = trainer_types[rec["trainer_class"]]
            gender_const = resolve_gender(tt["gender"], fork_genders)
            music_const = resolve_encounter_music(class_const, fork_music)
            pic_const = resolve_pic_constant(class_const, staged_pic_internal_names)
            verify_party_species(rec["party"], fork_species, staged_species)
            verify_party_moves(rec["party"], fork_moves)
            verify_party_items(rec["party"], fork_items)
        except ValueError as e:
            errors.append(f"{key}: {e}")
            continue

        staged.append(
            StagedTrainerBattle(
                trainer_key=key,
                fork_id=pristine_trainer_anchor_value + 1 + i,
                uranium_trainer_id=rec["id"],
                name=rec["name"],
                trainer_class_constant=class_const,
                gender_constant=gender_const,
                encounter_music_constant=music_const,
                pic_constant=pic_const,
                items=rec["items"],
                party=rec["party"],
            )
        )

    if errors:
        raise ValueError(
            f"{len(errors)}/{len(selected_keys)} pinned trainer(s) could not be staged:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
    return staged


# ===========================================================================
# `.party` DSL emit
# ===========================================================================

_STAT_ORDER = ("HP", "Atk", "Def", "SpA", "SpD", "Spe")


def _emit_iv_line(iv: int) -> str:
    spread = " / ".join(f"{iv} {stat}" for stat in _STAT_ORDER)
    return f"IVs: {spread}"


#: Per-mon `gender` int -> the parenthesized letter trainerproc's Pokemon
#: header line expects ("Roberta (SPECIES_ABRA) (F) @ ..."). Mirrors
#: `pbs_converter.trainers._GENDER_NAMES`'s 0/1 rows (per-mon gender has no
#: "Mixed" case -- a 2 here would be a schema surprise, fail loud rather than
#: guess).
_MON_GENDER_LETTER = {0: "M", 1: "F"}


def _emit_mon_header(mon: dict) -> str:
    """`[Nickname ](Species|SPECIES_X)[ (Gender)][ @ Item]` -- the Pokemon
    header line format (module docstring / trainers.party's own doc header).
    Bare species (Theo's precedent) when nickname/gender/item are all absent.
    """
    species = mon["species"]
    head = f"{mon['nickname']} ({species})" if mon.get("nickname") else species
    if mon.get("gender") is not None:
        letter = _MON_GENDER_LETTER.get(mon["gender"])
        if letter is None:
            raise ValueError(f"{species}: unexpected per-mon gender value {mon['gender']!r}")
        head += f" ({letter})"
    if mon.get("item"):
        head += f" @ {mon['item']}"
    return head


def _emit_mon_block(mon: dict) -> str:
    lines = [_emit_mon_header(mon)]
    lines.append(f"Level: {mon['level']}")
    lines.append(_emit_iv_line(mon["iv"]))
    lines.append(f"Happiness: {mon['happiness']}")
    if mon.get("nature") is not None:
        # `pbs_converter.trainers._emit_mon` stores the raw Essentials nature
        # INDEX (TPNATURE), not a resolved name/constant -- it was never
        # meant to be handed straight to trainerproc's `Nature:` field (which
        # wants "Rash" or "NATURE_RASH"). No pinned trainer in this slice
        # sets it; fail loud rather than emit a bogus numeric nature if a
        # future selection ever does.
        raise NotImplementedError(
            f"{mon['species']}: party mon has a `nature` index ({mon['nature']!r}) but "
            "pbs_converter.trainers.py doesn't resolve nature indices to names -- "
            "extend that resolver before staging a trainer that uses one"
        )
    if mon.get("form"):
        raise NotImplementedError(
            f"{mon['species']}: party mon has a non-default `form` ({mon['form']!r}) -- "
            "the .party DSL (tools/trainerproc) has no Form: field; this slice's emitter "
            "doesn't support alt-form party mons"
        )
    if mon.get("ball"):
        # Same unresolved-index problem as `nature` above (`_emit_mon` passes
        # the raw TPBALL int straight through) -- fail loud rather than emit
        # a numeric `Ball:` value trainerproc can't parse.
        raise NotImplementedError(
            f"{mon['species']}: party mon has a `ball` index ({mon['ball']!r}) but "
            "pbs_converter.trainers.py doesn't resolve ball indices to names -- extend "
            "that resolver before staging a trainer that uses one"
        )
    if mon.get("shiny"):
        lines.append("Shiny: Yes")
    if mon.get("moves"):
        lines.extend(f"- {mv}" for mv in mon["moves"])
    return "\n".join(lines)


def _emit_trainer_block(t: StagedTrainerBattle) -> str:
    header = [
        f"=== {t.trainer_key} ===",
        f"Name: {t.name}",
        f"Class: {t.trainer_class_constant}",
        f"Pic: {t.pic_constant}",
        f"Gender: {t.gender_constant.removeprefix('TRAINER_GENDER_').capitalize()}",
        f"Music: {t.encounter_music_constant}",
        # Uranium's trainers.dat party schema has no double-battle field at
        # all (Compiler.rb pbCompileTrainers/NPCTrainers.rb never encode
        # one) -- verified absent, not assumed; every trainer in this slice
        # is therefore a single battle.
        "Double Battle: No",
    ]
    if t.items:
        header.append("Items: " + " / ".join(t.items))
    mon_blocks = [_emit_mon_block(m) for m in t.party]
    return "\n".join(header) + "\n\n" + "\n\n".join(mon_blocks)


def emit_party_fragment(staged: list[StagedTrainerBattle]) -> str:
    """`uranium_trainer_party.inc` -- `.party` DSL text (NOT C), destined for
    `#include` at the end of `src/data/trainers.party` (see `stage.py`'s
    module docstring for the exact `-iquote include`-relative hook path).

    Always emitted, even with zero staged trainers -- a comment-only no-op
    (a plain `/* ... */` C comment, since this file is run through
    `cpp -traditional-cpp` before `trainerproc` sees it).
    """
    if not staged:
        return "/* (no Uranium trainer battles selected -- this fragment is a no-op) */\n"
    banner = (
        "/* DO NOT EDIT -- generated by " + GENERATOR + "\n"
        "   source: intermediate/trainers.json + intermediate/trainer_types.json */\n"
    )
    return banner + "\n" + "\n\n".join(_emit_trainer_block(t) for t in staged) + "\n"


# ===========================================================================
# Trainer id constants emit
# ===========================================================================


def emit_trainer_ids(staged: list[StagedTrainerBattle], anchor: str) -> str:
    """`uranium_trainer_ids.h`: chained `#define`s + `URANIUM_TRAINERS_LAST` +
    `URANIUM_TRAINERS_STAGED_COUNT`.

    Mirrors `species_converter.stage.emit_species_constants`'s anchor-chain
    shape. Deliberately does NOT touch `TRAINERS_COUNT_EMERALD` /
    `MAX_TRAINERS_COUNT_EMERALD` -- those are hand-provisioned corpus-sized
    (see stage.py's write-up) rather than derived per chapter; the count
    symbol here is informational / for a compile-time bounds check the
    engine hook can assert against.
    """
    if not staged:
        return "// (no Uranium trainer battles selected -- this overlay is a no-op)\n"
    lines: list[str] = []
    prev = anchor
    for t in staged:
        lines.append(f"#define {t.trainer_key} ({prev} + 1)")
        prev = t.trainer_key
    lines.append(f"#define URANIUM_TRAINERS_LAST {prev}")
    lines.append(f"#define URANIUM_TRAINERS_STAGED_COUNT {len(staged)}")
    return "\n".join(lines) + "\n"


# ===========================================================================
# Manifest records
# ===========================================================================


def build_battle_manifest_records(staged: list[StagedTrainerBattle]) -> list[dict]:
    return [
        {
            "kind": "battle",
            "trainer_key": t.trainer_key,
            "trainer_constant": t.trainer_key,
            "uranium_trainer_id": t.uranium_trainer_id,
            "fork_trainer_id": t.fork_id,
            "name": t.name,
            "trainer_class_constant": t.trainer_class_constant,
            "gender_constant": t.gender_constant,
            "encounter_music_constant": t.encounter_music_constant,
            "pic_constant": t.pic_constant,
            "items": t.items,
            "party_species": [m["species"] for m in t.party],
        }
        for t in staged
    ]


__all__ = [
    "GENERATOR",
    "StagedTrainerBattle",
    "read_pristine_trainer_anchor",
    "load_trainers_json",
    "load_trainer_types_json",
    "load_species_manifest_constants",
    "resolve_trainer_class",
    "resolve_gender",
    "resolve_encounter_music",
    "resolve_pic_constant",
    "verify_party_species",
    "verify_party_moves",
    "verify_party_items",
    "build_staged_battles",
    "emit_party_fragment",
    "emit_trainer_ids",
    "build_battle_manifest_records",
]
