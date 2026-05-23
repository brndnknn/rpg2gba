"""Phase 2 §2.4 — emit the Uranium-original ability constants + placeholder TU.

Abilities have no `.dat` file of their own: Essentials' `pbCompileAbilities`
writes them into the `PBAbilities` script section, not a binary blob. The
ID → internal-name map comes from the `reference/ability_internal_names.json`
sidecar (the dumped `PBAbilities` section); display names/descriptions come
from the `messages.dat` sidecars.

This converter only deals with the **Uranium-original** abilities — the ones
whose derived `ABILITY_*` constant is absent from the fork's
`include/constants/abilities.h` enum. Vanilla abilities (Stench, Drizzle, …)
already exist in pokeemerald-expansion, so we neither redefine them nor describe
them here; §2.1 references them directly. Distinguishing the two requires the
fork, so this converter fails loud if `$RPG2GBA_POKEEMERALD` isn't reachable.

**Why the sidecar, not just dexdata.** PHASE2_PLAN §2.4 suggested recovering the
in-use ability set from the `Abilities`/`HiddenAbility` bytes of `dexdata.dat`,
but that misses abilities assigned only to alternate *forms* via script — most
notably `CHERNOBYL` (URAYNE form 2), which the plan explicitly names. So the
authoritative Uranium-original set is "every `PBAbilities` entry whose derived
constant isn't in the fork enum" (a clean, contiguous Uranium id block). The
dexdata scan (`collect_ability_ids`) is kept as a sanity cross-check: every
ability a species actually references must exist in the sidecar, or we fail loud.

Ability *behavior* is Phase 6 engine work (D3): pokeemerald-expansion implements
ability effects inline across its battle scripts rather than through a single
handler table, so there is nothing to register in Phase 2. The emitted
`uranium_abilities.c` is a documented placeholder translation unit, and the
Uranium-original abilities (name + description, keyed by the minted constant)
are written to `intermediate/ability_codes.json` as the Phase 6 worklist.

The naming rule (`to_constant("ABILITY", display_name or internal)`) is shared
with §2.1's `_Resolver.ability_constant`, so the constants minted here and the
ones §2.1 references from `gSpeciesInfo[].abilities` are identical — `IdMap.add`
would otherwise fail loud on the conflict.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from . import pokemon
from ._c_emit import generated_banner, wrap_header
from ._id_map import IdMap
from ._naming import load_fork_constants, to_constant

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.pbs_converter.abilities"


def collect_ability_ids(dexdata_path: Path) -> set[int]:
    """Recover the set of ability IDs referenced by any species in dexdata.dat.

    Reads every `Abilities` (2 normal) and `HiddenAbility` (up to 4) slot from
    each species record. ID 0 (the empty slot / `ABILITY_NONE`) is excluded.
    """
    species = pokemon.parse_dexdata(dexdata_path)
    ids: set[int] = set()
    for s in species:
        if s is None:
            continue
        ids.update(s.abilities)
        ids.update(s.hidden_abilities)
    ids.discard(0)
    return ids


def _load_id_json(path: Path) -> dict[int, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


@dataclass
class _AbilityResolver:
    """Resolves Uranium ability IDs to `ABILITY_*` constants via the IdMap.

    Identical naming rule to pokemon.py's `_Resolver.ability_constant` so the
    constants stay in lockstep with the ones §2.1 references from species.
    """

    id_map: IdMap
    ability_internal: dict[int, str]
    ability_names: dict[int, str]
    ability_descs: dict[int, str]
    fork_abilities: set[str]

    def constant(self, ability_id: int) -> str:
        if ability_id == 0:
            return "ABILITY_NONE"
        internal = self.ability_internal.get(ability_id)
        if internal is None:
            raise ValueError(
                f"ability id {ability_id} absent from ability_internal_names.json"
            )
        const = to_constant("ABILITY", self.ability_names.get(ability_id) or internal)
        needs = bool(self.fork_abilities) and const not in self.fork_abilities
        self.id_map.add("abilities", internal, const, needs_engine=needs)
        return const

    def is_uranium_original(self, ability_id: int) -> bool:
        """True iff the derived constant is not in the fork's ability enum."""
        const = self.constant(ability_id)
        return const not in self.fork_abilities

    def name(self, ability_id: int) -> str:
        return self.ability_names.get(ability_id, self.ability_internal.get(ability_id, ""))

    def desc(self, ability_id: int) -> str:
        return self.ability_descs.get(ability_id, "")


def _build_resolver(id_map: IdMap, ref: Path) -> _AbilityResolver:
    fork_env = os.environ.get("RPG2GBA_POKEEMERALD")
    fork = Path(fork_env) if fork_env else None
    fork_abilities = (
        load_fork_constants(fork / "include/constants/abilities.h", "ABILITY")
        if fork
        else set()
    )
    return _AbilityResolver(
        id_map=id_map,
        ability_internal=_load_id_json(ref / "ability_internal_names.json"),
        ability_names=_load_id_json(ref / "ability_names.json"),
        ability_descs=_load_id_json(ref / "ability_descriptions.json"),
        fork_abilities=fork_abilities,
    )


# ===========================================================================
# C emit  (§2.4)
# ===========================================================================


def emit_constants(uranium_ids: list[int], r: _AbilityResolver) -> str:
    """Emit `#define ABILITY_* <id>` for the Uranium-original abilities only."""
    lines: list[str] = []
    seen: dict[str, int] = {}
    for aid in uranium_ids:
        const = r.constant(aid)
        prev = seen.get(const)
        if prev is not None:
            raise ValueError(
                f"ability constant collision: {const} minted for both id {prev} "
                f"and {aid} (distinct names normalized to the same constant)"
            )
        seen[const] = aid
        lines.append(f"#define {const} {aid}")
    banner = generated_banner(
        "dexdata.dat (ability refs) + Constants.rxdata", GENERATOR, timestamp=False
    )
    note = (
        "// Uranium-original abilities only — these have no equivalent in the\n"
        "// fork's ABILITY_* enum. Vanilla abilities are referenced directly by\n"
        "// gSpeciesInfo[] and are NOT redefined here. NOTE: these are Uranium's\n"
        "// own ability IDs and overlap vanilla numbering — V6 integration must\n"
        "// reconcile them with the fork enum.\n"
    )
    body = note + "\n".join(lines) if lines else note.rstrip()
    return wrap_header("GUARD_URANIUM_CONSTANTS_ABILITIES_H", body, banner=banner)


def emit_uranium_abilities_c(uranium_ids: list[int], r: _AbilityResolver) -> str:
    """Emit the placeholder translation unit documenting each Uranium ability.

    pokeemerald-expansion has no single ability-handler table to register into
    (effects are inline in battle scripts), so there is nothing to wire up in
    Phase 2. This file is the documented home for that Phase 6 work; the machine
    -readable worklist is `intermediate/ability_codes.json`.
    """
    banner = generated_banner(
        "dexdata.dat (ability refs) + messages.dat sidecars", GENERATOR, timestamp=False
    )
    note = (
        "//\n"
        "// Uranium-original ability behavior is Phase 6 engine work (PHASE2_PLAN\n"
        "// §D3). The fork implements ability effects inline across its battle\n"
        "// scripts rather than through a handler table, so nothing is registered\n"
        "// here yet. Each Uranium-original ability is listed below with its\n"
        "// display name and description; the same data is in machine-readable\n"
        "// form at intermediate/ability_codes.json (the Phase 6 worklist).\n"
        "//\n"
    )
    blocks: list[str] = []
    for aid in uranium_ids:
        const = r.constant(aid)
        name = r.name(aid)
        desc = r.desc(aid)
        block = f"// {const} (Uranium ability id {aid}) — {name}"
        if desc:
            block += f"\n//   {desc}"
        block += "\n//   TODO Phase 6: implement ability behavior."
        blocks.append(block)
    body = "\n//\n".join(blocks) if blocks else "// (no Uranium-original abilities in use)"
    return banner + note + "\n" + body + "\n"


def run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None:
    """Phase 2 §2.4 entry point: emit Uranium-original ability constants + TU."""
    ref = _reference_dir()
    r = _build_resolver(id_map, ref)
    if not r.fork_abilities:
        raise RuntimeError(
            "§2.4 needs $RPG2GBA_POKEEMERALD to point at the fork so it can tell "
            "Uranium-original abilities apart from vanilla ones "
            "(include/constants/abilities.h was missing or empty)."
        )

    # Authoritative Uranium-original set: every PBAbilities entry whose derived
    # constant is absent from the fork enum (a contiguous Uranium id block).
    originals = sorted(aid for aid in r.ability_internal if r.is_uranium_original(aid))

    # Sanity cross-check + §2.1 consistency: mint every ability a species
    # actually references (r.constant fails loud if dexdata names an ability the
    # sidecar lacks). This also records the in-use vanilla abilities in the IdMap
    # when §2.4 runs standalone, matching what a full pipeline run produces.
    in_use = collect_ability_ids(uranium_src / "Data" / "dexdata.dat")
    for aid in sorted(in_use):
        r.constant(aid)

    inc = out_dir / "include" / "constants"
    abil = out_dir / "src" / "data" / "abilities"
    inter = out_dir / "intermediate"
    for d in (inc, abil, inter):
        d.mkdir(parents=True, exist_ok=True)

    (inc / "abilities.h").write_text(emit_constants(originals, r), encoding="utf-8")
    (abil / "uranium_abilities.c").write_text(
        emit_uranium_abilities_c(originals, r), encoding="utf-8"
    )

    # Phase 6 worklist: every Uranium-original ability's display name + description,
    # keyed by the minted ABILITY_* constant.
    worklist = {
        r.constant(aid): {"name": r.name(aid), "description": r.desc(aid)}
        for aid in originals
    }
    (inter / "ability_codes.json").write_text(
        json.dumps(dict(sorted(worklist.items())), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    logger.info(
        "emitted %d Uranium-original abilities (%d distinct abilities referenced by "
        "species; behavior deferred to Phase 6)",
        len(originals),
        len(in_use),
    )
