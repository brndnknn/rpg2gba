"""W7 — PokePod (phone-rematch) trainer data: `gRematchTable` rows + their
`REMATCH_*` enum members.

Uranium's PokePod is functionally the engine's Match Call + rematch system:
an event battles you once, offers to "trade PokePod numbers"
(`pbPhoneRegisterBattle`), and on later pages re-battles you through
`createPhoneTrainer` / `customTrainerBattle`. The engine's equivalent is
`trainerbattle_single` + `register_matchcall` + `trainerbattle_rematch`, all
three of which are inert unless the trainer has a row in `gRematchTable`
(`engine/src/battle_setup.c:155-235`). This module generates that data side;
the Poryscript classifier that emits the three commands is a separate unit.

What is generated
-----------------
Per detected phone-rematch trainer:

* a `REMATCH_URANIUM_<TRAINERKEY>` enum member
  (`emit_rematch_enum`), and
* a `[REMATCH_URANIUM_<TRAINERKEY>] = REMATCH(t, t, t, t, t, MAP_<X>)` row
  (`emit_rematch_table`).

**Tier policy (user decision, implemented literally):** the same tier-1
trainer id is repeated across all five `trainerIds[]` slots. Uranium's
`createPhoneTrainer` re-levels and re-evolves the party dynamically at call
time; `struct RematchTrainer` (`engine/include/battle_setup.h:7-14`,
`REMATCHES_COUNT == 5`) is static and cannot express that, so the rematch
reuses the original party — the same thing vanilla does for the Elite Four
(`battle_setup.c:230-234`). No scaled duplicate trainers are synthesized.

**No `FLAG_REGISTERED_*` symbol is minted, by design.** Verified in the fork:
the registered flag is *derived numerically at runtime*, never referenced by
name from a script. `GetTrainerMatchCallFlag` (`battle_setup.c:1954-1965`)
returns `TRAINER_REGISTERED_FLAGS_START + i` for the rematch index `i` whose
`trainerIds[0]` matches, `TrainerIsMatchCallRegistered`
(`battle_setup.c:1787-1790`) reads the same expression, and the
`register_matchcall` macro (`asm/macros/event.inc:2150-2155`) takes a
`TRAINER_*` id — not a flag. The vanilla `FLAG_REGISTERED_*` defines
(`include/constants/flags.h:392-469`) are documentation aliases for that
arithmetic. So this pass creates **no new flag name**, and therefore has
nothing to put through the flag registry
(`src/rpg2gba/conversion_agent/flag_registry.py`) — which is correct, since
the registry allocates out of the `RPG2GBA_*` saved-flag region and could not
express an engine-derived `START + index` flag anyway.

That does NOT mean the flag is free: each appended rematch entry silently
*consumes* the flag number `TRAINER_REGISTERED_FLAGS_START + index`, and the
vanilla table already runs that block right up against occupied space. See
`registered_flag_headroom`.

Two independent capacity limits (both fail loud, never truncate)
----------------------------------------------------------------
1. **Saveblock.** `MAX_REMATCH_ENTRIES == 100` (`include/constants/global.h:103`)
   sizes `gSaveBlock1Ptr->trainerRematches[]`; vanilla uses
   `REMATCH_TABLE_ENTRIES == 78`, leaving 22. Growing past it moves the
   saveblock layout and invalidates saves — forbidden.
2. **Registered-flag space.** The `TRAINER_REGISTERED_FLAGS_START` (0x15C)
   block is 78 flags long, ending at 0x1A9. Only `FLAG_UNUSED_0x1AA` and
   `FLAG_UNUSED_0x1AB` follow before `FLAG_DEFEATED_DEOXYS` (0x1AC), so the
   real headroom is **2 entries**, not 22. Entry 3 would make
   `TRAINER_REGISTERED_FLAGS_START + 80` alias `FLAG_DEFEATED_DEOXYS`.
   `registered_flag_headroom` derives this from the fork rather than pinning
   it; CH02's two phone trainers fit exactly, the corpus will not.

Enum insertion point (important — NOT at the end)
--------------------------------------------------
New members must be inserted **immediately before `REMATCH_WALLY_VR`**, i.e.
at the end of the *normal trainer* region, not appended before the
`REMATCH_TABLE_ENTRIES` sentinel. Appending at the end places the entry above
`REMATCH_ELITE_FOUR_ENTRIES` (`= REMATCH_SIDNEY`), and `IsRematchForbidden`
(`battle_setup.c:1751-1761`) returns TRUE for every `rematchTableId >=
REMATCH_ELITE_FOUR_ENTRIES` — the rematch would never fire. The
normal-trainer scans in `match_call.c:1123/1135/1512` and
`battle_setup.c:1800` likewise stop at `REMATCH_SPECIAL_TRAINER_START`
(`= REMATCH_WALLY_VR`). Inserting there renumbers the vanilla special/E4
entries by N, which is compile-time only (every use is symbolic, including
`gMatchCallFlavorTexts`' designated initializers) but does shift
`trainerRematches[]` indices — irrelevant for a fresh save, and the CH02
trainer-capacity bump already invalidated saves.

Output / injection
------------------
This module writes nothing. It returns text fragments; the assembler pass
(`scripts/assemble_pathfinder.py`, S8b5) stages them under `out/trainers/`,
the same "never touch `engine/`" discipline `trainer_converter.battles`
follows. Unlike wild encounters, this data has **no Makefile-wildcard
injection path**: `gRematchTable` and the `REMATCH_*` enum are hand-written C
in committed vendored source with no generator tool and no data file for a
`$(or $(wildcard …))` hook to swap. Installing it requires two one-line
`#include` hooks in committed engine files (the
`constants/event_objects.h` → `uranium_event_objects.gen.h` precedent), which
this unit deliberately does not make.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.trainer_converter.rematch"

#: The fork symbol new members must be inserted immediately before. See the
#: "Enum insertion point" section of the module docstring for why the end of
#: the enum is the wrong place.
INSERT_BEFORE_MEMBER = "REMATCH_WALLY_VR"

#: The sentinel that must stay last in `enum { … }` in
#: `include/constants/rematches.h`.
SENTINEL_MEMBER = "REMATCH_TABLE_ENTRIES"

#: Prefix distinguishing minted members from the 78 vanilla `REMATCH_*` names.
REMATCH_PREFIX = "REMATCH_URANIUM_"

#: The object-like macro the generated enum fragment defines, expanded inside
#: the enum body in `include/constants/rematches.h` immediately before
#: INSERT_BEFORE_MEMBER. The members can NOT be `#include`d directly at that
#: point: `.s` files run through cpp before `tools/preproc`, and cpp's
#: enter/leave-file line markers (`# 1 "…" 1`) carry trailing flags that
#: `AsmFile::ParseLineSkipInEnum` cannot parse -- every assembly unit that
#: includes this header dies with "unterminated enum". A macro expands on the
#: invocation line, emitting no line markers inside the enum at all.
MEMBERS_MACRO = "URANIUM_REMATCH_MEMBERS"

#: The Essentials call that marks an event as a PokePod phone trainer.
PHONE_REGISTER_CALL = "pbPhoneRegisterBattle"

_SCRIPT_CODES = (355, 655)
_CONDITIONAL_CODE = 111
_CONDITIONAL_SCRIPT_KIND = 12

_TRAINER_REF_RE = re.compile(r'PBTrainers::(\w+)\s*,\s*"((?:[^"\\]|\\.)*)"')
_ENUM_BODY_RE = re.compile(r"enum\s*\{(.*?)\}\s*;", re.DOTALL)
_ENUM_MEMBER_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?:=[^,]*)?,?\s*$")
_FLAG_DEFINE_RE = re.compile(r"^#define\s+(FLAG_\w+)\s+(0[xX][0-9A-Fa-f]+|\d+)\s*(?://.*)?$")
_MAX_REMATCH_RE = re.compile(r"^#define\s+MAX_REMATCH_ENTRIES\s+(\d+)", re.MULTILINE)
_REGISTERED_START_RE = re.compile(
    r"^#define\s+TRAINER_REGISTERED_FLAGS_START\s+(0[xX][0-9A-Fa-f]+|\d+)", re.MULTILINE
)


# ===========================================================================
# Fork facts (CLAUDE.md §4.7 — read from the fork, never pinned from memory)
# ===========================================================================


@dataclass(frozen=True)
class ForkRematchFacts:
    """Everything this pass needs to know about the fork's rematch surface."""

    members: tuple[str, ...]  # vanilla REMATCH_* members, sentinel excluded
    max_rematch_entries: int  # MAX_REMATCH_ENTRIES (saveblock array size)
    registered_flags_start: int  # TRAINER_REGISTERED_FLAGS_START
    registered_flag_headroom: int  # free flag numbers past the vanilla block

    @property
    def vanilla_entries(self) -> int:
        return len(self.members)

    @property
    def saveblock_headroom(self) -> int:
        return self.max_rematch_entries - self.vanilla_entries

    @property
    def capacity(self) -> int:
        """Entries that can actually be added: the tighter of the two limits."""
        return min(self.saveblock_headroom, self.registered_flag_headroom)


def parse_rematch_members(engine_dir: Path) -> tuple[str, ...]:
    """The vanilla `REMATCH_*` enum members from
    `include/constants/rematches.h`, sentinel excluded, in declaration order.
    """
    path = engine_dir / "include" / "constants" / "rematches.h"
    text = path.read_text(encoding="utf-8")
    body = _ENUM_BODY_RE.search(text)
    if body is None:
        raise ValueError(f"{path}: no `enum {{ … }};` block found — fork header has drifted")
    members: list[str] = []
    for raw_line in body.group(1).splitlines():
        line = re.sub(r"//.*$", "", raw_line).strip()
        if not line:
            continue
        if line.startswith("#") or line == MEMBERS_MACRO:
            # Our own hook: the MEMBERS_MACRO expansion sitting inside the enum
            # just above INSERT_BEFORE_MEMBER (plus any preprocessor line).
            # Skipped deliberately: these facts are the VANILLA baseline that
            # capacity and insertion-index math are computed against, so counting
            # generated members here would double-count them on every re-run and
            # break idempotence.
            continue
        m = _ENUM_MEMBER_RE.match(line)
        if m is None:
            raise ValueError(f"{path}: unparsable enum line {raw_line!r}")
        members.append(m.group(1))
    if not members or members[-1] != SENTINEL_MEMBER:
        raise ValueError(
            f"{path}: expected {SENTINEL_MEMBER} last in the enum, got {members[-1:]!r}"
        )
    if INSERT_BEFORE_MEMBER not in members:
        raise ValueError(f"{path}: {INSERT_BEFORE_MEMBER} not present — insertion point is gone")
    return tuple(members[:-1])


def parse_max_rematch_entries(engine_dir: Path) -> int:
    path = engine_dir / "include" / "constants" / "global.h"
    m = _MAX_REMATCH_RE.search(path.read_text(encoding="utf-8"))
    if m is None:
        raise ValueError(f"{path}: `#define MAX_REMATCH_ENTRIES <N>` not found")
    return int(m.group(1))


def registered_flag_headroom(engine_dir: Path, vanilla_entries: int) -> tuple[int, int]:
    """`(TRAINER_REGISTERED_FLAGS_START, free flag numbers after the block)`.

    The vanilla registered block occupies `START .. START + vanilla_entries - 1`.
    Headroom is the distance from the first number past it to the first *used*
    flag number at or above it. `FLAG_UNUSED_*` defines are excluded from
    "used" — they exist precisely to name reservable gaps (0x1AA/0x1AB in the
    pinned fork), which is where appended rematch entries land.
    """
    path = engine_dir / "include" / "constants" / "flags.h"
    text = path.read_text(encoding="utf-8")
    m = _REGISTERED_START_RE.search(text)
    if m is None:
        raise ValueError(f"{path}: `#define TRAINER_REGISTERED_FLAGS_START <N>` not found")
    start = int(m.group(1), 0)

    first_free = start + vanilla_entries
    occupied: list[int] = []
    for line in text.splitlines():
        d = _FLAG_DEFINE_RE.match(line.strip())
        if d is None:
            continue
        if d.group(1).startswith("FLAG_UNUSED"):
            continue
        occupied.append(int(d.group(2), 0))
    above = [v for v in occupied if v >= first_free]
    if not above:
        raise ValueError(
            f"{path}: no numeric FLAG_* define at or above {first_free:#x} — cannot bound "
            "the registered-flag block; refusing to guess its headroom"
        )
    return start, min(above) - first_free


def load_fork_facts(engine_dir: Path) -> ForkRematchFacts:
    members = parse_rematch_members(engine_dir)
    start, headroom = registered_flag_headroom(engine_dir, len(members))
    return ForkRematchFacts(
        members=members,
        max_rematch_entries=parse_max_rematch_entries(engine_dir),
        registered_flags_start=start,
        registered_flag_headroom=headroom,
    )


# ===========================================================================
# Detection
# ===========================================================================


@dataclass(frozen=True)
class PhoneRematchEvent:
    """A map event structurally identified as a PokePod phone trainer."""

    uranium_map_id: int
    event_id: int
    event_name: str
    trainer_class_internal: str  # Uranium's PBTrainers:: symbol, e.g. "FISHERMAN"
    trainer_display_name: str  # e.g. "Brandon"


def _script_blocks(page: Mapping) -> list[str]:
    """Every logically-complete script string on a page.

    RMXP splits a long script across one `355` command plus N `655`
    continuations; a `111` conditional of kind 12 carries its own script in
    `parameters[1]`. Both shapes are joined/collected here so a call can be
    matched even when its arguments wrap across commands (which is exactly
    what `pbPhoneRegisterBattle` does — the trainer reference lives on the
    `655` line).
    """
    blocks: list[str] = []
    current: list[str] | None = None
    for cmd in page.get("list", []):
        code = cmd.get("code")
        params = cmd.get("parameters", [])
        if code == _SCRIPT_CODES[0]:
            if current is not None:
                blocks.append("\n".join(current))
            current = [str(params[0]) if params else ""]
            continue
        if code == _SCRIPT_CODES[1]:
            if current is None:
                raise ValueError("script continuation (655) with no preceding 355 command")
            current.append(str(params[0]) if params else "")
            continue
        if current is not None:
            blocks.append("\n".join(current))
            current = None
        if code == _CONDITIONAL_CODE and params and params[0] == _CONDITIONAL_SCRIPT_KIND:
            blocks.append(str(params[1]))
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def detect_phone_rematch_events(
    map_json: Mapping, uranium_map_id: int
) -> list[PhoneRematchEvent]:
    """Every phone-rematch event on one deserialized map, sorted by event id.

    Detection is structural: any event with a script block calling
    `pbPhoneRegisterBattle`. The trainer is read from the
    `PBTrainers::<CLASS>, "<Name>"` pair inside that same block — never
    hardcoded per map.

    Fails loud when a `pbPhoneRegisterBattle` block carries no trainer
    reference, or when one event's blocks disagree about which trainer they
    register (both would mean the shape this detector was written against has
    changed).
    """
    found: list[PhoneRematchEvent] = []
    for event in map_json.get("events", []):
        refs: set[tuple[str, str]] = set()
        for page in event.get("pages", []):
            for block in _script_blocks(page):
                if PHONE_REGISTER_CALL not in block:
                    continue
                tail = block[block.index(PHONE_REGISTER_CALL) :]
                m = _TRAINER_REF_RE.search(tail)
                if m is None:
                    raise ValueError(
                        f"map {uranium_map_id} event {event.get('id')} "
                        f"({event.get('name')!r}): {PHONE_REGISTER_CALL} call has no "
                        f'`PBTrainers::<CLASS>, "<Name>"` argument pair — cannot resolve '
                        f"the trainer it registers: {tail[:160]!r}"
                    )
                refs.add((m.group(1), m.group(2)))
        if not refs:
            continue
        if len(refs) > 1:
            raise ValueError(
                f"map {uranium_map_id} event {event.get('id')}: {PHONE_REGISTER_CALL} "
                f"registers more than one distinct trainer {sorted(refs)} — one rematch "
                "entry per event is assumed"
            )
        cls, name = refs.pop()
        found.append(
            PhoneRematchEvent(
                uranium_map_id=uranium_map_id,
                event_id=int(event["id"]),
                event_name=str(event.get("name", "")),
                trainer_class_internal=cls,
                trainer_display_name=name,
            )
        )
    return sorted(found, key=lambda e: e.event_id)


# ===========================================================================
# Resolution
# ===========================================================================


@dataclass(frozen=True)
class RematchEntry:
    """One resolved `gRematchTable` row, ready to emit."""

    uranium_map_id: int
    event_id: int
    trainer_key: str  # TRAINER_BRANDON_16 — also the engine TRAINER_* constant
    uranium_trainer_id: int
    trainer_display_name: str
    rematch_const: str  # REMATCH_URANIUM_BRANDON_16
    registered_flag_name: str  # documentation only, see module docstring
    registered_flag_value: int
    map_const: str  # MAP_ROUTE_01


def rematch_const_for(trainer_key: str) -> str:
    if not trainer_key.startswith("TRAINER_"):
        raise ValueError(f"trainer key {trainer_key!r} does not start with TRAINER_")
    return REMATCH_PREFIX + trainer_key[len("TRAINER_") :]


def registered_flag_name_for(rematch_const: str) -> str:
    return "FLAG_REGISTERED_" + rematch_const[len("REMATCH_") :]


def resolve_trainer_key(event: PhoneRematchEvent, trainers: Mapping[str, Mapping]) -> str:
    """The `TRAINER_*` key in `intermediate/trainers.json` for a phone event.

    Uranium's `PBTrainers::<CLASS>` symbol IS the `trainertypes.dat` internal
    name `pbs_converter.trainers` builds its `trainer_class` constant from, so
    the class matches on `TRAINER_CLASS_<CLASS>` and the trainer on the
    display `name`. Both a miss and an ambiguity fail loud — the corpus has
    same-named trainers in different classes (two "Brandon"s on Route 1
    alone), which is precisely why the class is part of the key.
    """
    class_const = f"TRAINER_CLASS_{event.trainer_class_internal}"
    matches = sorted(
        key
        for key, rec in trainers.items()
        if rec.get("trainer_class") == class_const
        and rec.get("name") == event.trainer_display_name
    )
    if not matches:
        raise ValueError(
            f"map {event.uranium_map_id} event {event.event_id}: no trainers.json entry "
            f"for class {class_const} name {event.trainer_display_name!r} — cannot resolve "
            "the trainer constant for a phone rematch"
        )
    if len(matches) > 1:
        raise ValueError(
            f"map {event.uranium_map_id} event {event.event_id}: class {class_const} name "
            f"{event.trainer_display_name!r} is ambiguous across {matches} — cannot pick a "
            "rematch trainer"
        )
    return matches[0]


def build_rematch_entries(
    events: Sequence[PhoneRematchEvent],
    trainers: Mapping[str, Mapping],
    map_consts: Mapping[int, str],
    staged_trainer_keys: frozenset[str] | set[str],
    facts: ForkRematchFacts,
) -> list[RematchEntry]:
    """Resolve detected phone events into `gRematchTable` rows.

    Deterministic order: `(uranium_map_id, event_id)`.

    Fails loud (never skips, never truncates) on:
      * a trainer constant that can't be resolved or isn't staged as a battle
        trainer (emitting `TRAINER_X` the fork won't define is CLAUDE.md
        §4.7's forward gate);
      * a map with no `MAP_*` constant;
      * a `REMATCH_*` name colliding with a vanilla member or with another
        entry in this batch;
      * a batch exceeding the fork's capacity (see `ForkRematchFacts`).
    """
    vanilla = set(facts.members)
    entries: list[RematchEntry] = []
    seen: dict[str, RematchEntry] = {}

    for event in sorted(events, key=lambda e: (e.uranium_map_id, e.event_id)):
        trainer_key = resolve_trainer_key(event, trainers)
        if trainer_key not in staged_trainer_keys:
            raise ValueError(
                f"map {event.uranium_map_id} event {event.event_id}: {trainer_key} is not "
                "staged as a battle trainer (trainer_manifest.json kind=='battle') — a "
                "rematch row cannot reference a TRAINER_* constant the fork won't define; "
                "stage the trainer first"
            )
        map_const = map_consts.get(event.uranium_map_id)
        if map_const is None:
            raise ValueError(
                f"map {event.uranium_map_id}: has a phone-rematch event but no MAP_* "
                "constant in map_consts"
            )
        rematch_const = rematch_const_for(trainer_key)
        if rematch_const in vanilla:
            raise ValueError(
                f"{rematch_const} collides with a vanilla member of the fork's REMATCH_* enum"
            )
        prior = seen.get(rematch_const)
        if prior is not None:
            raise ValueError(
                f"{rematch_const} minted twice: map {prior.uranium_map_id} event "
                f"{prior.event_id} and map {event.uranium_map_id} event {event.event_id} "
                f"both register {trainer_key}"
            )

        entry = RematchEntry(
            uranium_map_id=event.uranium_map_id,
            event_id=event.event_id,
            trainer_key=trainer_key,
            uranium_trainer_id=int(trainers[trainer_key]["id"]),
            trainer_display_name=event.trainer_display_name,
            rematch_const=rematch_const,
            registered_flag_name=registered_flag_name_for(rematch_const),
            # Insertion is before REMATCH_WALLY_VR, so this entry takes the
            # index currently held by that member, offset by its position in
            # the batch. The flag is START + index (battle_setup.c:1954-1965).
            registered_flag_value=(
                facts.registered_flags_start
                + facts.members.index(INSERT_BEFORE_MEMBER)
                + len(entries)
            ),
            map_const=map_const,
        )
        seen[rematch_const] = entry
        entries.append(entry)

    if len(entries) > facts.capacity:
        raise ValueError(
            f"{len(entries)} Uranium rematch entries requested but only {facts.capacity} "
            f"can be added: saveblock headroom is {facts.saveblock_headroom} "
            f"(MAX_REMATCH_ENTRIES={facts.max_rematch_entries} minus "
            f"{facts.vanilla_entries} vanilla entries — growing it moves the saveblock "
            f"layout and invalidates saves) and registered-flag headroom is "
            f"{facts.registered_flag_headroom} (free flag numbers after "
            f"TRAINER_REGISTERED_FLAGS_START+{facts.vanilla_entries}). Refusing to "
            "truncate; the corpus needs an engine-side plan for the overflow."
        )
    return entries


# ===========================================================================
# Emit
# ===========================================================================


def _banner(kind: str) -> str:
    return (
        f"// DO NOT EDIT — generated by {GENERATOR}\n"
        f"// {kind}\n"
        f"// source: output/uranium-build/maps/Map*.json ({PHONE_REGISTER_CALL} events)\n"
    )


def emit_rematch_enum(entries: Sequence[RematchEntry]) -> str:
    """`uranium_rematches.gen.h` — the `MEMBERS_MACRO` definition whose expansion
    supplies the new enum members inside the `enum { … }` of
    `include/constants/rematches.h`, immediately BEFORE `REMATCH_WALLY_VR` (see
    the module docstring; appending at the end makes every entry
    rematch-forbidden).

    The header is `#include`d ABOVE the enum and only the macro is written
    inside it — see `MEMBERS_MACRO` for why an in-enum `#include` cannot work.
    Member provenance rides along as comments outside the macro body, since a
    `//` comment would swallow a `\\` line-continuation.

    Always emitted, even empty — a comment-only no-op definition, so the include
    hook can exist unconditionally (the `constants/event_objects.h` precedent).
    """
    head = _banner(
        f"REMATCH_* enum members, expanded by {MEMBERS_MACRO} immediately "
        f"before {INSERT_BEFORE_MEMBER}."
    )
    if not entries:
        return (
            head
            + "// (no Uranium phone-rematch trainers in this build set)\n"
            + f"#define {MEMBERS_MACRO}\n"
        )
    provenance = "".join(
        f"// {e.rematch_const}: map {e.uranium_map_id} EV{e.event_id:03d} "
        f"{e.trainer_display_name} ({e.trainer_key}); "
        f"{e.registered_flag_name} = {e.registered_flag_value:#x}\n"
        for e in entries
    )
    body = " \\\n".join(f"    {e.rematch_const}," for e in entries)
    return head + provenance + f"#define {MEMBERS_MACRO} \\\n" + body + "\n"


def emit_rematch_table(entries: Sequence[RematchEntry]) -> str:
    """`uranium_rematch_table.gen.h` — `gRematchTable` rows to be `#include`d
    inside the initializer in `src/battle_setup.c`.

    Tier policy: the tier-1 trainer id in all five slots (module docstring).
    """
    head = _banner("gRematchTable rows. Insertion point: inside the gRematchTable initializer.")
    if not entries:
        return head + "// (no Uranium phone-rematch trainers in this build set)\n"
    lines = [
        f"    [{e.rematch_const}] = REMATCH("
        + ", ".join([e.trainer_key] * 5)
        + f", {e.map_const}),"
        for e in entries
    ]
    return head + "\n".join(lines) + "\n"


def build_rematch_manifest_records(entries: Sequence[RematchEntry]) -> list[dict]:
    return [
        {
            "kind": "rematch",
            "uranium_map_id": e.uranium_map_id,
            "event_id": e.event_id,
            "trainer_key": e.trainer_key,
            "trainer_constant": e.trainer_key,
            "uranium_trainer_id": e.uranium_trainer_id,
            "name": e.trainer_display_name,
            "rematch_constant": e.rematch_const,
            "registered_flag_name": e.registered_flag_name,
            "registered_flag_value": e.registered_flag_value,
            "map_const": e.map_const,
            "trainer_ids": [e.trainer_key] * 5,
        }
        for e in entries
    ]


# ===========================================================================
# Convenience loaders (the assembler pass's inputs)
# ===========================================================================


def load_map_json(maps_dir: Path, uranium_map_id: int) -> dict:
    path = maps_dir / f"Map{uranium_map_id:03d}.json"
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing — deserialize the map before staging rematches")
    return json.loads(path.read_text(encoding="utf-8"))


def load_staged_battle_trainer_keys(trainer_manifest_path: Path) -> frozenset[str]:
    manifest = json.loads(trainer_manifest_path.read_text(encoding="utf-8"))
    return frozenset(
        entry["trainer_key"] for entry in manifest["trainers"] if entry.get("kind") == "battle"
    )


def detect_over_maps(maps_dir: Path, map_ids: Sequence[int]) -> list[PhoneRematchEvent]:
    events: list[PhoneRematchEvent] = []
    for mid in map_ids:
        events.extend(detect_phone_rematch_events(load_map_json(maps_dir, mid), mid))
    return sorted(events, key=lambda e: (e.uranium_map_id, e.event_id))


__all__ = [
    "GENERATOR",
    "INSERT_BEFORE_MEMBER",
    "PHONE_REGISTER_CALL",
    "REMATCH_PREFIX",
    "SENTINEL_MEMBER",
    "ForkRematchFacts",
    "PhoneRematchEvent",
    "RematchEntry",
    "build_rematch_entries",
    "build_rematch_manifest_records",
    "detect_over_maps",
    "detect_phone_rematch_events",
    "emit_rematch_enum",
    "emit_rematch_table",
    "load_fork_facts",
    "load_map_json",
    "load_staged_battle_trainer_keys",
    "parse_max_rematch_entries",
    "parse_rematch_members",
    "registered_flag_headroom",
    "registered_flag_name_for",
    "rematch_const_for",
    "resolve_trainer_key",
]
