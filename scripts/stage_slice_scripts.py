"""S8: stage the pathfinder slice's .pory for fork assembly.

Deterministic transforms, in order, per slice map:
  1. NORMALIZE labels — strip the agent's inconsistent event-name component so
     blocks match S5's un-named ``Map{m}_EV{e}_Page{n}`` references (Option A).
  2. REGENERATE map.json — re-run the S5 wiring with the *real* converted page
     labels (the ``pory_labels`` hook). An event S6 left bodyless (a standing NPC
     / globally-gated cutscene actor with no commands) is then wired as a static
     object (``script "0x0"``) instead of a dangling ``Map{m}_EV{e}_Page1`` ref.
     The S5 *preview* map.json was optimistic (``pory_labels=None``); this run
     supersedes it.
  3. PRUNE orphans — drop blocks for events ``map.json`` does not wire (the
     out-of-slice doors whose ``warp(MAP_URANIUM_<N>)`` the alias header can't
     resolve), with the fail-loud guards in ``tileset_converter.assembly``.
Then, across the whole staged set (normalized+pruned map scripts + dispatchers +
``CommonEvents.pory`` + the ``map.json``s):
  4. EXISTENCE CHECK — every referenced script label must be defined (no
     undefined ``goto``/``call``/``map.json`` script — catches EV074-style gaps),
     and no label may be defined twice (no duplicate symbol).

map.json + dispatchers (regenerable ``porymap/`` output) are rewritten on every
run; ``--write`` controls only whether the transformed ``.pory`` is staged under
``output/uranium-build/staging/scripts/``. The canonical S6 output in
``scripts/`` is never modified (CLAUDE.md §4.4). The checks always run and still
fail loud. The future ``assemble_pathfinder.py`` consumes the staged copies.

Usage:
    python scripts/stage_slice_scripts.py            # regenerate + report + checks
    python scripts/stage_slice_scripts.py --write     # also stage transformed .pory
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from rpg2gba.pipeline import _load_dotenv
from rpg2gba.tileset_converter import assembly as asm
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter import metadata_wiring as mw
from rpg2gba.tileset_converter import sprite_pass
from rpg2gba.tileset_converter.local_id_remap import (
    load_local_id_table,
    remap_pory_object_ids,
)
from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS
from rpg2gba.tileset_converter.npc_gfx import DEFAULT_NPC_GFX_MAP, load_npc_gfx_map

DEFAULT_SLICE = tuple(SLICE_MAP_IDS)
ALLOWED_MAPS = {49, 48, 32}
OVERRIDES = Path("reference/map_name_overrides.json")


def _load_event_traits(out: Path, map_id: int, pory_path: Path) -> dict[int, list[str]]:
    """Load `Map{id:03d}.traits.json` from the same scripts dir as the .pory
    (the transpile driver's fixed-schema sidecar — see metadata_wiring.py). No
    sidecar is a fail-loud data-integrity error (CLAUDE.md §4.5), not a skip:
    the driver is expected to emit one, empty or not, for every map it transpiles."""
    traits_path = out / "scripts" / f"Map{map_id:03d}.traits.json"
    if not traits_path.is_file():
        raise FileNotFoundError(
            f"{traits_path} missing (expected alongside {pory_path.name}) — "
            f"re-run the transpile driver to regenerate the trait sidecar"
        )
    sidecar = json.loads(traits_path.read_text(encoding="utf-8"))
    return {int(eid): traits for eid, traits in sidecar["events"].items()}


def _regenerate_map_json(
    out: Path,
    pory_labels: set[str],
    npc_gfx: dict[str, str],
    local_id_dir: Path,
    event_traits: dict[int, dict[int, list[str]]],
) -> None:
    """Re-run S5 wiring over the whole slice with the real converted page labels,
    so bodyless events become static objects. Warp pairing needs the full slice,
    so this always covers ``DEFAULT_SLICE`` regardless of the requested subset.

    `npc_gfx` (character_name -> OBJ_EVENT_GFX_*) places visible NPCs; the per-map
    RMXP-id -> compiled-local-id tables are written to `local_id_dir` for the
    staging remap pass below. `event_traits` (Uranium map id -> event id -> trait
    list, from the per-map `.traits.json` sidecars) assigns smashable-rock
    visibility flags."""
    reg = mc.build_map_constants(
        list(DEFAULT_SLICE),
        map_infos_path=out / "map_infos.json",
        overrides_path=OVERRIDES,
        state_path=out / "porymap" / "map_constants.json",
    )
    mw.build_slice_maps(
        list(DEFAULT_SLICE),
        maps_dir=out / "maps",
        registry=reg,
        metadata_path=out / "intermediate" / "map_metadata.json",
        out_dir=out / "porymap" / "maps",
        dispatcher_dir=out / "porymap" / "dispatch",
        pory_labels=pory_labels,
        npc_gfx=npc_gfx,
        local_id_dir=local_id_dir,
        event_traits=event_traits,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("maps", nargs="*", type=int, default=list(DEFAULT_SLICE),
                    help=f"Uranium map ids to stage (default: the slice {DEFAULT_SLICE}).")
    ap.add_argument("--write", action="store_true",
                    help="stage transformed .pory under output/.../staging/scripts/.")
    args = ap.parse_args()

    _load_dotenv()
    out = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
    consts = json.loads((out / "porymap" / "map_constants.json").read_text(encoding="utf-8"))
    staging = out / "staging" / "scripts"
    local_id_dir = out / "staging" / "local_ids"

    fork_path = os.environ.get("RPG2GBA_POKEEMERALD")
    if not fork_path:
        print("RPG2GBA_POKEEMERALD not set", file=sys.stderr)
        return 1
    fork = Path(fork_path)

    # NPC sprites first: populate engine/include/constants/uranium_event_objects.gen.h
    # so load_npc_gfx_map can validate every OBJ_EVENT_GFX_URANIUM_* against a real
    # #define (idempotent — assemble_pathfinder re-runs it before make).
    sprite_pass.run_sprite_pass(fork)
    npc_gfx = load_npc_gfx_map(
        DEFAULT_NPC_GFX_MAP,
        [
            fork / "include" / "constants" / "event_objects.h",
            fork / "include" / "constants" / "uranium_event_objects.gen.h",
        ],
    )

    # --- pass 1: normalize every slice .pory, collect the canonical (un-named)
    # page-label definition set the regenerated map.json must agree with ---
    normalized: dict[int, asm.NormalizeResult] = {}
    pory_labels: set[str] = set()
    event_traits: dict[int, dict[int, list[str]]] = {}
    for map_id in DEFAULT_SLICE:
        pory_path = out / "scripts" / f"Map{map_id:03d}.pory"
        if consts.get(str(map_id)) is None or not pory_path.is_file():
            continue
        norm = asm.normalize_labels(pory_path.read_text(encoding="utf-8"))
        normalized[map_id] = norm
        pory_labels.update(asm.script_definitions(norm.text))
        event_traits[map_id] = _load_event_traits(out, map_id, pory_path)

    # --- regenerate map.json with the real labels (the S5 stub hook) +
    # per-map local-id tables (RMXP id -> compiled object-event local id) ---
    _regenerate_map_json(out, pory_labels, npc_gfx, local_id_dir, event_traits)

    # --- pass 2: prune + report per requested map (reads the fresh map.json) ---
    staged: dict[str, str] = {}   # filename -> transformed text (for the staged-set checks)
    map_jsons: list[dict] = []

    for map_id in args.maps:
        entry = consts.get(str(map_id))
        if entry is None or map_id not in normalized:
            print(f"Map{map_id:03d}: no map_constants entry or .pory — skipped", file=sys.stderr)
            continue
        map_json_path = out / "porymap" / "maps" / entry["dir_name"] / "map.json"
        if not map_json_path.is_file():
            print(f"Map{map_id:03d}: missing map.json — skipped", file=sys.stderr)
            continue

        map_json = json.loads(map_json_path.read_text(encoding="utf-8"))
        map_jsons.append(map_json)

        norm = normalized[map_id]
        result = asm.prune_map_pory(norm.text, map_json, allowed_uranium_maps=ALLOWED_MAPS)

        # Remap RMXP event ids in object-targeting commands (applymovement/
        # setobjectxy/addobject/removeobject/turnobject) to compiled local ids.
        # EXACTLY ONCE, on fresh (pruned) transpiler output — this is the sole
        # application site; assemble_pathfinder must not remap again.
        table = load_local_id_table(local_id_dir / f"Map{map_id:03d}.json")
        remap = remap_pory_object_ids(
            result.text, table, source_name=f"Map{map_id:03d}.pory"
        )
        staged[f"Map{map_id:03d}.pory"] = remap.text

        statics = sum(1 for o in map_json.get("object_events", []) if o.get("script") == "0x0")
        print(f"Map{map_id:03d} ({entry['dir_name']}): "
              f"normalized {len(norm.renames)} label(s), "
              f"kept {len(result.kept)}, dropped {len(result.dropped)} orphan(s), "
              f"{statics} static object(s), "
              f"{len(remap.replacements)} local-id remap(s), "
              f"{len(remap.warnings)} unmapped")
        for old, new in sorted(norm.renames.items()):
            print(f"    rename  {old} -> {new}")
        for label in result.dropped:
            print(f"    drop    {label}")
        for line, command, old_id, new_id in remap.replacements:
            print(f"    remap   line {line}: {command}({old_id}) -> {new_id}")
        for line, command, old_id in remap.warnings:
            print(f"    remap   WARN line {line}: {command}({old_id}) not in local-id table")

    # --- staged-set checks (read-only; dispatchers + CommonEvents define labels
    # the map scripts reference, so they must be in the defined set) ---
    aux_texts: list[str] = []
    disp_dir = out / "porymap" / "dispatch"
    if disp_dir.is_dir():
        aux_texts += [f.read_text(encoding="utf-8") for f in sorted(disp_dir.glob("*.pory"))]
    ce = out / "scripts" / "CommonEvents.pory"
    if ce.is_file():
        aux_texts.append(ce.read_text(encoding="utf-8"))

    all_texts = list(staged.values()) + aux_texts
    dangling = asm.find_dangling_references(all_texts, map_jsons)
    duplicates = asm.find_duplicate_definitions(all_texts)

    print()
    if dangling or duplicates:
        if dangling:
            print(f"FAIL: {len(dangling)} undefined script reference(s):", file=sys.stderr)
            for ref in sorted(dangling):
                print(f"    {ref}", file=sys.stderr)
        if duplicates:
            print(f"FAIL: {len(duplicates)} duplicate definition(s):", file=sys.stderr)
            for label, n in sorted(duplicates.items()):
                print(f"    {label}  x{n}", file=sys.stderr)
        return 1
    print("existence check: every referenced script label is defined exactly once.")

    if args.write:
        staging.mkdir(parents=True, exist_ok=True)
        for name, text in staged.items():
            (staging / name).write_text(text, encoding="utf-8")
            print(f"staged -> {staging / name}")
    else:
        print("(dry-run — re-run with --write to stage the transformed .pory)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
