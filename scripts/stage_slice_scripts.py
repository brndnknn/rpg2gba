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

DEFAULT_SLICE = (49, 48, 32)
ALLOWED_MAPS = {49, 48, 32}
OVERRIDES = Path("reference/map_name_overrides.json")


def _regenerate_map_json(out: Path, pory_labels: set[str]) -> None:
    """Re-run S5 wiring over the whole slice with the real converted page labels,
    so bodyless events become static objects. Warp pairing needs the full slice,
    so this always covers ``DEFAULT_SLICE`` regardless of the requested subset."""
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

    # --- pass 1: normalize every slice .pory, collect the canonical (un-named)
    # page-label definition set the regenerated map.json must agree with ---
    normalized: dict[int, asm.NormalizeResult] = {}
    pory_labels: set[str] = set()
    for map_id in DEFAULT_SLICE:
        pory_path = out / "scripts" / f"Map{map_id:03d}.pory"
        if consts.get(str(map_id)) is None or not pory_path.is_file():
            continue
        norm = asm.normalize_labels(pory_path.read_text(encoding="utf-8"))
        normalized[map_id] = norm
        pory_labels.update(asm.script_definitions(norm.text))

    # --- regenerate map.json with the real labels (the S5 stub hook) ---
    _regenerate_map_json(out, pory_labels)

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
        staged[f"Map{map_id:03d}.pory"] = result.text

        statics = sum(1 for o in map_json.get("object_events", []) if o.get("script") == "0x0")
        print(f"Map{map_id:03d} ({entry['dir_name']}): "
              f"normalized {len(norm.renames)} label(s), "
              f"kept {len(result.kept)}, dropped {len(result.dropped)} orphan(s), "
              f"{statics} static object(s)")
        for old, new in sorted(norm.renames.items()):
            print(f"    rename  {old} -> {new}")
        for label in result.dropped:
            print(f"    drop    {label}")

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
