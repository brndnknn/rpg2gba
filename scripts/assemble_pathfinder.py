"""S8b + S8c: assemble the pathfinder slice into the pokeemerald-expansion fork.

Pass 1 (S8b) — layout conversion
    Convert each slice map's Phase-3 tile grid to map.bin + border.bin and a
    layouts.json entry, staged under output/uranium-build/staging/layouts/.

Pass 2 (S8c) — fork assembly
    Copy/compile everything into $RPG2GBA_POKEEMERALD:
      - staged .pory + dispatcher (if any) -> fork data/maps/<MapDir>/scripts.inc
      - CommonEvents.pory -> fork data/scripts/CommonEvents.inc
      - porymap map.json -> fork data/maps/<MapDir>/map.json
      - staged map.bin + border.bin -> fork data/layouts/<name>/
      - upsert fork data/layouts/layouts.json
      - add gMapGroup_Uranium to fork data/maps/map_groups.json (idempotent)
      - write fork data/scripts/uranium_map_aliases.h
      - write fork data/scripts/uranium_flags.h (flag registry dump)
      - append includes to fork data/event_scripts.s (idempotent, sentinel-guarded)

Usage:
    python scripts/assemble_pathfinder.py [--dry-run]

dry-run reports what would be written without touching the fork.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slice config (matches PATHFINDER_SLICE_ROADMAP.md S1 decisions)
# ---------------------------------------------------------------------------

SLICE_MAP_IDS = [49, 48, 32]  # order: 1F (spawn), 2F, Moki Town

# S5 warp overrides: warp-source coords. The layout converter stamps the
# tileset's warp metatile (MB_NON_ANIMATED_DOOR, collision 0) at each so the
# warp_event actually fires — a generic floor tile (MB_NORMAL) under a warp is
# inert (S9 fix 2026-06-18). Mirrors build_slice_maps' returned src_coords.
WARP_OVERRIDES: dict[int, set[tuple[int, int]]] = {
    49: {(10, 11), (12, 3)},
    48: {(3, 3)},
    32: {(28, 31)},
}

# Flag address layout for the pathfinder boot test (Phase 7 assigns final values).
# These must not overlap vanilla flags (FLAGS_COUNT ≈ 0x960; TEMP_FLAGS 0x0-0x1F).
FLAG_BASE = 0x1000        # named global flags
SELFSWITCH_BASE = 0x1100  # per-event self-switch flags
VAR_BASE = 0x40D0         # unused game-var range (vanilla VARS_END = 0x40FF)
TEMPSWITCH_BASE = 0x0014  # temp flags — 0x14+ are unused in the vanilla fork

# Sentinel that guards the appended block in event_scripts.s (idempotent).
_ES_SENTINEL_BEGIN = "@ BEGIN URANIUM PATHFINDER SLICE"
_ES_SENTINEL_END = "@ END URANIUM PATHFINDER SLICE"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_dotenv(repo_root: Path) -> None:
    env_file = repo_root / ".env-paths"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip()


def _compile_pory(text: str, dest: Path, label: str, dry_run: bool) -> None:
    """Compile poryscript text to `dest`.  Fails loud on compile error."""
    from rpg2gba.conversion_agent.poryscript import compile_to_file
    if dry_run:
        logger.info("  [dry] would compile %s -> %s", label, dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = compile_to_file(text, dest)
    if not result.ok:
        raise RuntimeError(
            f"poryscript failed on {label}:\n{result.stderr.strip()}"
        )
    logger.info("  compiled %s -> %s", label, dest.relative_to(dest.parents[3]))


def _write(path: Path, text: str, label: str, dry_run: bool) -> None:
    if dry_run:
        logger.info("  [dry] would write %s", label)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    logger.info("  wrote %s", label)


def _copy(src: Path, dest: Path, label: str, dry_run: bool) -> None:
    if dry_run:
        logger.info("  [dry] would copy %s -> %s", label, dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    logger.info("  copied %s -> %s", label, dest.relative_to(dest.parents[3]))


# ---------------------------------------------------------------------------
# S8b: Layout conversion
# ---------------------------------------------------------------------------

def run_layout_pass(
    out: Path,
    consts: dict,
    staging: Path,
    dry_run: bool,
) -> None:
    logger.info("=== S8b: layout conversion ===")
    from rpg2gba.tileset_converter.layout import append_layouts, convert_layout
    from rpg2gba.tileset_converter.tile_map import load_tile_map

    tile_map = load_tile_map(
        Path("reference/tileset_map.json"),
        out / "tilesets.json",
    )

    entries: list[dict] = []
    for map_id in SLICE_MAP_IDS:
        entry = consts[str(map_id)]
        map_json_path = out / "maps" / f"Map{map_id:03d}.json"
        map_json = json.loads(map_json_path.read_text(encoding="utf-8"))

        layout = convert_layout(
            map_json,
            tile_map,
            name=entry["dir_name"],
            layout_const=entry["layout_const"],
            warp_overrides=WARP_OVERRIDES.get(map_id),
        )
        entries.append(layout.to_layouts_entry())

        if not dry_run:
            layout.write(staging)
            logger.info(
                "  Map%03d (%s): wrote map.bin (%d blocks) + border.bin",
                map_id, entry["dir_name"], len(layout.blocks),
            )
        else:
            logger.info(
                "  [dry] Map%03d (%s): %d blocks",
                map_id, entry["dir_name"], len(layout.blocks),
            )

    layouts_json = staging / "layouts" / "layouts.json"
    if not dry_run:
        append_layouts(entries, layouts_json)
        logger.info("  upserted %d layouts -> %s", len(entries), layouts_json)
    else:
        logger.info("  [dry] would upsert %d layouts -> %s", len(entries), layouts_json)


# ---------------------------------------------------------------------------
# S8c: Fork assembly
# ---------------------------------------------------------------------------

def run_fork_pass(
    out: Path,
    fork: Path,
    consts: dict,
    staging: Path,
    dry_run: bool,
) -> None:
    logger.info("=== S8c: fork assembly ===")

    from rpg2gba.tileset_converter import assembly as asm
    # Single owner of charmap legality: rewrite \" -> typographic quotes, *->~,
    # [->(, ]->), heal alias, fail loud on any other unrepresentable glyph.
    allowed = asm.load_charmap_chars(fork / "charmap.txt")
    defined_multis = asm.load_multi_constants(
        fork / "include" / "constants" / "script_menu.h"
    )
    compiled_texts: list[str] = []  # for self/temp-switch reference completeness

    # --- Compile per-map scripts (staged .pory + optional dispatcher) ---
    disp_dir = out / "porymap" / "dispatch"
    for map_id in SLICE_MAP_IDS:
        entry = consts[str(map_id)]
        map_dir_name = entry["dir_name"]

        pory_path = staging / "scripts" / f"Map{map_id:03d}.pory"
        pory_text = asm.normalize_pory(pory_path.read_text(encoding="utf-8"), allowed)

        disp_path = disp_dir / f"Map{map_id:03d}_dispatch.pory"
        if disp_path.is_file():
            pory_text = pory_text.rstrip() + "\n\n" + disp_path.read_text(encoding="utf-8")

        # Every pokeemerald map needs a `<Map>_MapScripts` symbol (its map-script
        # header table). The agent emits none, so define an empty one.
        mapscripts_label = f"{map_dir_name}_MapScripts"
        if mapscripts_label not in pory_text:
            pory_text = f"mapscripts {mapscripts_label} {{}}\n\n" + pory_text

        compiled_texts.append(pory_text)
        dest_scripts_inc = fork / "data" / "maps" / map_dir_name / "scripts.inc"
        _compile_pory(pory_text, dest_scripts_inc, f"Map{map_id:03d}", dry_run)

    # --- Compile CommonEvents ---
    ce_pory = out / "scripts" / "CommonEvents.pory"
    if ce_pory.is_file():
        ce_text = asm.normalize_pory(ce_pory.read_text(encoding="utf-8"), allowed)
        ce_text = asm.patch_out_of_slice_warps(ce_text, set(SLICE_MAP_IDS))
        ce_text = asm.patch_undefined_multichoice(ce_text, defined_multis)
        compiled_texts.append(ce_text)
        dest_ce = fork / "data" / "scripts" / "CommonEvents.inc"
        _compile_pory(ce_text, dest_ce, "CommonEvents", dry_run)
    else:
        logger.warning("CommonEvents.pory not found — skipping")

    # --- Copy map.json per map ---
    for map_id in SLICE_MAP_IDS:
        entry = consts[str(map_id)]
        map_dir_name = entry["dir_name"]
        src_map_json = out / "porymap" / "maps" / map_dir_name / "map.json"
        dest_map_json = fork / "data" / "maps" / map_dir_name / "map.json"
        _copy(src_map_json, dest_map_json, f"map.json ({map_dir_name})", dry_run)

    # --- Copy layout .bin files ---
    staging_layouts = staging / "layouts"
    for map_id in SLICE_MAP_IDS:
        entry = consts[str(map_id)]
        layout_name = entry["dir_name"]
        for bin_name in ("map.bin", "border.bin"):
            src = staging_layouts / layout_name / bin_name
            if not dry_run and not src.is_file():
                raise FileNotFoundError(
                    f"S8b layout output missing: {src}\n"
                    "Run assemble_pathfinder.py without --skip-layout first."
                )
            dest = fork / "data" / "layouts" / layout_name / bin_name
            _copy(src, dest, f"{layout_name}/{bin_name}", dry_run)

    # --- Upsert fork layouts.json ---
    fork_layouts_json = fork / "data" / "layouts" / "layouts.json"
    staging_layouts_json = staging_layouts / "layouts.json"
    if staging_layouts_json.is_file():
        from rpg2gba.tileset_converter.layout import append_layouts
        entries = json.loads(staging_layouts_json.read_text(encoding="utf-8")).get("layouts", [])
        if not dry_run:
            append_layouts(entries, fork_layouts_json)
            logger.info("  upserted %d layouts -> fork layouts.json", len(entries))
        else:
            logger.info("  [dry] would upsert %d layouts -> fork layouts.json", len(entries))

    # --- Add gMapGroup_Uranium to fork map_groups.json (idempotent) ---
    fork_mg = fork / "data" / "maps" / "map_groups.json"
    mg = json.loads(fork_mg.read_text(encoding="utf-8"))
    uranium_group = "gMapGroup_Uranium"
    uranium_maps = [consts[str(mid)]["dir_name"] for mid in SLICE_MAP_IDS]
    if uranium_group not in mg.get("group_order", []):
        mg.setdefault("group_order", []).append(uranium_group)
        mg[uranium_group] = uranium_maps
        if not dry_run:
            fork_mg.write_text(json.dumps(mg, indent=2) + "\n", encoding="utf-8")
            logger.info("  added %s to fork map_groups.json", uranium_group)
        else:
            logger.info("  [dry] would add %s to fork map_groups.json", uranium_group)
    else:
        logger.info("  %s already in map_groups.json", uranium_group)

    # --- Write alias header ---
    alias_src = out / "porymap" / "uranium_map_aliases.h"
    dest_alias = fork / "data" / "scripts" / "uranium_map_aliases.h"
    _copy(alias_src, dest_alias, "uranium_map_aliases.h", dry_run)

    # --- Write flag registry header ---
    dest_flags = fork / "data" / "scripts" / "uranium_flags.h"
    _emit_flags_header(dest_flags, compiled_texts, dry_run)

    # --- Update event_scripts.s (idempotent) ---
    _update_event_scripts(fork, consts, ce_pory.is_file(), dry_run)


def _emit_flags_header(dest: Path, compiled_texts: list[str], dry_run: bool) -> None:
    from rpg2gba.conversion_agent.flag_registry import FlagRegistry
    from rpg2gba.tileset_converter import assembly as asm
    reg = FlagRegistry.load(Path("output/uranium-build/flag_state.json"))

    # Mint any self/temp-switch referenced in the final assembled scripts but not
    # registered during conversion (cross-event "set the next NPC's switch" sets
    # whose target event is bodyless) so dump_header gives every one an address.
    # In-memory only — flag_state.json (shared with the bulk run) is not rewritten;
    # the header is regenerated deterministically on every assembly.
    self_keys, temp_keys = asm.referenced_switch_keys(compiled_texts)
    for mid, eid, ch in self_keys:
        reg.mint_self_switch(mid, eid, ch)   # idempotent; only missing keys are added
    for mid, eid, key in temp_keys:
        reg.mint_temp_switch(mid, eid, key)

    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        reg.dump_header(
            dest,
            flag_base=FLAG_BASE,
            var_base=VAR_BASE,
            selfswitch_base=SELFSWITCH_BASE,
            tempswitch_base=TEMPSWITCH_BASE,
        )
        logger.info("  wrote uranium_flags.h (%s)", dest)
    else:
        logger.info("  [dry] would write uranium_flags.h")


def _update_event_scripts(
    fork: Path,
    consts: dict,
    has_common_events: bool,
    dry_run: bool,
) -> None:
    """Append a sentinel-guarded block of includes to data/event_scripts.s.

    Idempotent: replaces the existing sentinel block if present."""
    es = fork / "data" / "event_scripts.s"
    text = es.read_text(encoding="utf-8")

    includes: list[str] = [
        '	#include "data/scripts/uranium_map_aliases.h"',
        '	#include "data/scripts/uranium_flags.h"',
    ]
    if has_common_events:
        includes.append('	.include "data/scripts/CommonEvents.inc"')
    for mid in SLICE_MAP_IDS:
        dir_name = consts[str(mid)]["dir_name"]
        includes.append(f'	.include "data/maps/{dir_name}/scripts.inc"')

    block = (
        _ES_SENTINEL_BEGIN + "\n"
        + "\n".join(includes) + "\n"
        + _ES_SENTINEL_END
    )

    if _ES_SENTINEL_BEGIN in text:
        # Replace existing block
        start = text.index(_ES_SENTINEL_BEGIN)
        end = text.index(_ES_SENTINEL_END) + len(_ES_SENTINEL_END)
        new_text = text[:start] + block + text[end:]
    else:
        new_text = text.rstrip() + "\n" + block + "\n"

    if not dry_run:
        es.write_text(new_text, encoding="utf-8")
        logger.info("  updated data/event_scripts.s with %d includes", len(includes))
    else:
        logger.info("  [dry] would add %d includes to event_scripts.s", len(includes))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Report without modifying the fork.")
    ap.add_argument("--skip-layout", action="store_true",
                    help="Skip S8b (layout .bin already generated).")
    args = ap.parse_args()

    repo_root = Path(__file__).parent.parent
    _load_dotenv(repo_root)

    fork_path = os.environ.get("RPG2GBA_POKEEMERALD")
    if not fork_path:
        print("RPG2GBA_POKEEMERALD not set", file=sys.stderr)
        return 1
    fork = Path(fork_path)
    if not fork.is_dir():
        print(f"fork not found: {fork}", file=sys.stderr)
        return 1

    out = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
    staging = out / "staging"

    consts_path = out / "porymap" / "map_constants.json"
    consts = json.loads(consts_path.read_text(encoding="utf-8"))

    if not args.skip_layout:
        run_layout_pass(out, consts, staging, args.dry_run)

    run_fork_pass(out, fork, consts, staging, args.dry_run)

    if args.dry_run:
        logger.info("=== dry-run complete, no files written ===")
    else:
        logger.info("=== assembly complete — ready for: make -C %s -j$(nproc) modern ===", fork)
    return 0


if __name__ == "__main__":
    sys.exit(main())
