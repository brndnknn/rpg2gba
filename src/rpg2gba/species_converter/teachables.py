"""Uranium TM/HM/tutor compatibility -> the fork's build-generated teachable learnsets.

`engine/tools/learnset_helpers/make_teachables.py` builds each species'
`sXTeachableLearnset` from `src/data/pokemon/all_learnables.json` (species ->
every move it can learn) intersected with the fork's TM/HM list and the tutor
moves it discovers in scripts. Uranium's own compatibility lives in
`intermediate/uranium_tm_learnables.json` (`pbs_converter/tm_hm.py`, inverted
`tm.dat`; Uranium's `tutor.dat` is empty so tutor compatibility is in `tm.dat`
too). This module merges the two into a generated, gitignored overlay,
`engine/src/data/pokemon/all_learnables.gen.json`, that make_teachables.py
prefers when present (fenced hook; absent = pristine upstream).

Why here and not in `pbs_converter/`: it needs the staged-species manifest and
the symbol convention `species_converter/stage.py` emits into
`uranium_species_info.h`; both are species-staging concerns, and stage.py
imports `teachable_symbol` from here so the two cannot drift.

Merge rules (fidelity choices, flagged for the operator):
  * Staged Uranium-custom species (listed in `species_manifest.json`) get
    EXACTLY Uranium's list under the key `URANIUM_<INTERNAL>`.
  * Vanilla-reuse species (id-map constant defined in the fork, not staged)
    keep the fork's stock list and gain the UNION with Uranium's entries, so
    nothing Uranium allows is refused. (Consequence: a vanilla species can
    learn stock-fork machine moves Uranium never allowed it.)
  * Uranium species neither staged nor defined in the fork are skipped (no
    species to attach to); counted in the stats.
  * Uranium-original moves the fork lacks (id map `needs_engine.moves`) are
    dropped and reported; a move that is neither fork-defined nor
    `needs_engine` fails loud (CLAUDE.md 4.5).
  * Tutor-only moves (e.g. CH06's tutor) are not special here: they sit in the
    sidecar like any machine move. They reach the teachable list because the
    fenced `make_tutors.py` hook now also recognises the transpiled
    `call MoveTutor_EventScript_OpenBox` idiom in map scripts.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from rpg2gba.battle_converter.catalog import generated_constants as generated_battle_constants
from rpg2gba.pbs_converter._id_map import IdMap
from rpg2gba.pbs_converter._naming import load_fork_constants

logger = logging.getLogger(__name__)

OVERLAY_RELPATH = Path("src/data/pokemon/all_learnables.gen.json")
UPSTREAM_RELPATH = Path("src/data/pokemon/all_learnables.json")
SIDECAR_RELPATH = Path("intermediate/uranium_tm_learnables.json")

# Mirrors make_teachables.py / make_teaching_types.py exactly: the generator
# derives the learnables key from the symbol name with this regex.
_SNAKIFY = re.compile(r"(?!^)([A-Z]+)")
_SYMBOL = re.compile(r"\s*\.teachableLearnset\s*=\s*s(?P<name>\w+?)TeachableLearnset")


def teachable_name(internal_name: str) -> str:
    return f"Uranium{internal_name}"


def teachable_symbol(internal_name: str) -> str:
    """The `.teachableLearnset` symbol stage.py emits for a staged species."""
    return f"s{teachable_name(internal_name)}TeachableLearnset"


def learnables_key(internal_name: str) -> str:
    """The all_learnables key make_teachables.py derives for that symbol."""
    m = _SYMBOL.match(f".teachableLearnset = {teachable_symbol(internal_name)},")
    assert m is not None
    return _SNAKIFY.sub(r"_\1", m.group("name")).upper()


@dataclass
class TeachablesOverlay:
    learnables: dict[str, list[str]]
    custom_species: int = 0
    vanilla_species: int = 0
    skipped_species: list[str] = field(default_factory=list)
    dropped_moves: list[str] = field(default_factory=list)
    added_pairs: int = 0


def build_overlay(
    *,
    upstream: dict[str, list[str]],
    sidecar: dict[str, list[str]],
    species_ids: dict[str, str],
    needs_engine_species: set[str],
    staged: dict[str, str],
    fork_moves: set[str],
    needs_engine_moves: set[str],
) -> TeachablesOverlay:
    """Merge Uranium compatibility into the upstream learnables map.

    `species_ids` is the id-map internal-name -> SPECIES_*; `staged` maps the
    staged species' internal names to their SPECIES_* constants. Pure.
    """
    merged: dict[str, set[str]] = {k: set(v) for k, v in upstream.items()}
    result = TeachablesOverlay(learnables={})
    dropped: set[str] = set()
    custom: dict[str, set[str]] = {}

    for internal in sorted(sidecar):
        moves: set[str] = set()
        for move in sidecar[internal]:
            if move in fork_moves:
                moves.add(move)
            elif move in needs_engine_moves:
                dropped.add(move)
            else:
                raise ValueError(
                    f"uranium_tm_learnables: {internal} lists {move}, which the fork does "
                    "not define and the id map does not mark needs_engine"
                )

        if internal in staged:
            custom[learnables_key(internal)] = moves
            result.custom_species += 1
            continue

        const = species_ids.get(internal)
        if const is None or const in needs_engine_species:
            result.skipped_species.append(internal)
            continue
        key = const.removeprefix("SPECIES_")
        if key not in merged:
            raise ValueError(
                f"uranium_tm_learnables: vanilla species {internal} -> {const} has no "
                f"{UPSTREAM_RELPATH} entry (key {key!r}); cannot merge its compatibility"
            )
        before = len(merged[key])
        merged[key] |= moves
        result.added_pairs += len(merged[key]) - before
        result.vanilla_species += 1

    for key in custom:
        if key in merged:
            raise ValueError(f"custom species key {key!r} collides with an upstream entry")
    out = {k: sorted(v) for k, v in merged.items()}
    for key in sorted(custom):
        out[key] = sorted(custom[key])
    result.learnables = out
    result.dropped_moves = sorted(dropped)
    return result


def render(overlay: TeachablesOverlay) -> str:
    return json.dumps(overlay.learnables, indent=2, ensure_ascii=False) + "\n"


def generate(*, out: Path, fork: Path, reference_dir: Path) -> TeachablesOverlay:
    """Read the sidecar, staged manifest and id map; return the merged overlay.

    `out` is `output/uranium-build`. Raises FileNotFoundError if the upstream
    learnables file or the TM/HM sidecar is missing.
    """
    upstream_path = fork / UPSTREAM_RELPATH
    sidecar_path = out / SIDECAR_RELPATH
    for p in (upstream_path, sidecar_path):
        if not p.is_file():
            raise FileNotFoundError(f"{p} missing -- run the Phase 2 TM/HM pass / check the engine")

    upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))["learnables"]

    manifest_path = out / "species" / "species_manifest.json"
    staged: dict[str, str] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        staged = {e["internal_name"]: e["species_constant"] for e in manifest["species"]}

    id_map = IdMap.load(reference_dir / "uranium_id_map.json")
    return build_overlay(
        upstream=upstream,
        sidecar=sidecar,
        species_ids=dict(id_map.by_category["species"]),
        needs_engine_species=set(id_map.needs_engine["species"]),
        staged=staged,
        # Stock moves plus the game's own the battle pass generates (I3 S3);
        # blocked ones stay needs_engine and are dropped.
        fork_moves=(load_fork_constants(fork / "include/constants/moves.h", "MOVE")
                    | {c for c in generated_battle_constants() if c.startswith("MOVE_")}),
        needs_engine_moves=set(id_map.needs_engine["moves"]),
    )


def write_overlay(overlay: TeachablesOverlay, fork: Path) -> Path:
    path = fork / OVERLAY_RELPATH
    path.write_text(render(overlay), encoding="utf-8")
    return path
