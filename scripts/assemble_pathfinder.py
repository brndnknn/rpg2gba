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
      - write fork data/layouts/layouts.gen.json (upstream + slice; overlay, gitignored)
      - write fork data/maps/map_groups.gen.json (upstream + gMapGroup_Uranium; overlay)
      - write fork data/scripts/uranium_map_aliases.h
      - write fork data/scripts/uranium_flags.h (flag registry dump)
      - write fork data/maps/uranium_includes.inc (gitignored; pulled in by the committed
        URANIUM PATHFINDER SLICE include-hook in data/event_scripts.s)

NOTE: this no longer edits ANY tracked upstream file in place. The vendored
event_scripts.s + map_data_rules.mk carry committed, stable include-hooks (see
engine/RPG2GBA_VENDOR.md); all per-slice content lands in gitignored *.gen.json /
*.inc files, so the vendored tree stays pristine.

Usage:
    python scripts/assemble_pathfinder.py [--dry-run]

dry-run reports what would be written without touching the fork.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path

from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS, WALKABLE_OVERRIDES

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slice config (matches PATHFINDER_SLICE_ROADMAP.md S1 decisions)
# ---------------------------------------------------------------------------

# SLICE_MAP_IDS (the 3-map slice, boot order 1F/2F/Moki) is the single source of
# truth in rpg2gba.tileset_converter.map_set, imported above. Phase B will set the
# build target from a --maps selector (slice/full/id-list) via map_set.parse_map_ids.

# S5 warp overrides: warp-source coords. The layout converter stamps the
# tileset's warp metatile (MB_NON_ANIMATED_DOOR, collision 0) at each so the
# warp_event actually fires — a generic floor tile (MB_NORMAL) under a warp is
# inert (S9 fix 2026-06-18). Mirrors build_slice_maps' returned src_coords.
WARP_OVERRIDES: dict[int, set[tuple[int, int]]] = {
    49: {(10, 11), (12, 3)},
    48: {(3, 3)},
    # 32: player's house (28,31) + the interior doors added by SLICE1_TODO #13:
    # lab EV003 (17,11), house-2 EV006 (43,31), house-1 EV007 (24,42),
    # Theo's-house EV017 (56,42). The Route-01 triad EV023/036/037 stays
    # out-of-slice (blocked cells by design).
    32: {(28, 31), (17, 11), (43, 31), (24, 42), (56, 42)},
    50: {(14, 19)},           # lab exit EV001
    64: {(9, 14)},            # house-2 exit EV003
    65: {(9, 14)},            # house-1 exit EV003
    172: {(10, 11), (12, 3)},  # Theo 1F: street exit EV002 + stairs up EV003
    89: {(3, 3)},             # Theo 2F: stairs down EV002
}

# Flag/var address layout for the pathfinder boot test. The numeric layout now
# lives in the ENGINE, single source of truth: include/config/rpg2gba.h defines
# the region capacities, constants/flags.h + constants/vars.h derive the region
# starts. These names are resolved symbolically by cpp when uranium_flags.h is
# #included from data/event_scripts.s (after constants/flags.h / vars.h) — no
# numeric literals here anymore (audit findings F1/F2 fix; the old hardcoded
# bases were out-of-bounds writes / aliased live vanilla vars — see
# reference/guides/engine_extension_surface.md §2).
FLAG_BASE = "RPG2GBA_GLOBAL_FLAGS_START"
SELFSWITCH_BASE = "RPG2GBA_SELFSWITCH_FLAGS_START"
VAR_BASE = "RPG2GBA_VARS_START"
TEMPSWITCH_BASE = "RPG2GBA_TEMP_FLAGS_START"

# Overlay manifests read by the committed map_data_rules.mk hook (URANIUM_*) when
# present, else the pristine upstream files. Keeps the tracked manifests untouched.
_GEN_MAP_GROUPS = "map_groups.gen.json"
_GEN_LAYOUTS = "layouts.gen.json"


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
# S8a: Tileset graphics (real Uranium art)
# ---------------------------------------------------------------------------

def run_graphics_pass(out: Path, fork: Path, dry_run: bool) -> None:
    """Quantise each slice tileset's real Uranium art into a pokeemerald
    PRIMARY+SECONDARY pair, write the engine fragments + tileset_map.gen.json overlay.

    Must run BEFORE S8b: the layout pass's `load_tile_map` prefers the overlay this
    writes, so map.bin then references the real Uranium metatiles instead of the
    committed Hoenn buckets."""
    logger.info("=== S8a: tileset graphics ===")
    from rpg2gba.tileset_converter import sprite_pass
    from rpg2gba.tileset_converter.graphics.build_slice_tilesets import (
        build_slice_tilesets,
    )

    # NPC sprite gen files first: real Uranium object-event sprites + the
    # constants header the fork's map_events.s TU needs to resolve every
    # OBJ_EVENT_GFX_URANIUM_* the slice map.json references. Deterministic +
    # idempotent (also run at staging), so a double execution is harmless.
    if not dry_run:
        sprite_pass.run_sprite_pass(fork)
    else:
        logger.info("  [dry] would run NPC sprite pass -> engine gen files")

    maps: list[tuple[int, dict]] = []
    for map_id in SLICE_MAP_IDS:
        map_json = json.loads(
            (out / "maps" / f"Map{map_id:03d}.json").read_text(encoding="utf-8")
        )
        maps.append((map_id, map_json))

    build_slice_tilesets(
        maps,
        WARP_OVERRIDES,
        fork=fork,
        base_tile_map=Path("reference/tileset_map.json"),
        overlay_out=Path("reference/tileset_map.gen.json"),
        tilesets_json=out / "tilesets.json",
        dry_run=dry_run,
    )


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
    from rpg2gba.tileset_converter.metadata_wiring import collect_through_block_cells
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

        warp_overrides = WARP_OVERRIDES.get(map_id, set())
        # A working (in-slice) door matches the same blank-graphic/through=False
        # predicate collect_through_block_cells uses (see its docstring) — exclude
        # the map's own warp coords so its tile stays enterable. An out-of-slice
        # door (not in warp_overrides — NO-EMIT, classify_event's "skip") correctly
        # stays in blocked_cells: nothing will ever warp there.
        blocked_cells = collect_through_block_cells(map_json) - warp_overrides

        layout = convert_layout(
            map_json,
            tile_map,
            name=entry["dir_name"],
            layout_const=entry["layout_const"],
            warp_overrides=warp_overrides,
            blocked_cells=blocked_cells,
            unblocked_cells=WALKABLE_OVERRIDES.get(map_id, frozenset()),
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

    from rpg2gba.conversion_agent import fork_index as fi
    from rpg2gba.tileset_converter import assembly as asm

    # Staging-time forward gate (grill D4): every script staged into engine/
    # is checked against the fork's real symbol surface (index) plus the
    # Uranium-minted registries (D3). A violation is OUR bug — abort loud
    # before make, never stage, never queue.
    gate_index = fi.load_or_build()
    gate_extras = fi.registry_extra_symbols(
        flag_state_path=out / "flag_state.json",
        map_constants_path=out / "porymap" / "map_constants.json",
    )
    def _gate(pory_text: str, label: str) -> None:
        violations = fi.verify_script(pory_text, gate_index, extra_symbols=gate_extras)
        if violations:
            lines = "\n".join(
                f"  {label}:{v.line_no}: [{v.kind}] {v.symbol} — {v.context.strip()}"
                for v in violations
            )
            raise RuntimeError(
                f"fork-index gate: {len(violations)} unresolved symbol(s) in "
                f"{label} — this is a converter bug; nothing staged:\n{lines}"
            )
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
        _gate(pory_text, f"Map{map_id:03d}")
        dest_scripts_inc = fork / "data" / "maps" / map_dir_name / "scripts.inc"
        _compile_pory(pory_text, dest_scripts_inc, f"Map{map_id:03d}", dry_run)

    # --- Compile CommonEvents ---
    ce_pory = out / "scripts" / "CommonEvents.pory"
    if ce_pory.is_file():
        ce_text = asm.normalize_pory(ce_pory.read_text(encoding="utf-8"), allowed)
        ce_text = asm.patch_out_of_slice_warps(ce_text, set(SLICE_MAP_IDS))
        ce_text = asm.patch_undefined_multichoice(ce_text, defined_multis)
        compiled_texts.append(ce_text)
        _gate(ce_text, "CommonEvents")
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

    # --- Write layouts overlay (data/layouts/layouts.gen.json) ---
    # Seed from the PRISTINE upstream layouts.json (the full vanilla manifest) so the
    # tracked file is never touched; upsert the slice layouts. map_data_rules.mk reads
    # this overlay when present (URANIUM_LAYOUTS).
    pristine_layouts_json = fork / "data" / "layouts" / "layouts.json"
    gen_layouts_json = fork / "data" / "layouts" / _GEN_LAYOUTS
    staging_layouts_json = staging_layouts / "layouts.json"
    if staging_layouts_json.is_file():
        from rpg2gba.tileset_converter.layout import append_layouts
        entries = json.loads(staging_layouts_json.read_text(encoding="utf-8")).get("layouts", [])
        if not dry_run:
            shutil.copy2(pristine_layouts_json, gen_layouts_json)  # full upstream manifest
            append_layouts(entries, gen_layouts_json)             # + slice layouts
            logger.info("  wrote %s (+%d slice layouts)", _GEN_LAYOUTS, len(entries))
        else:
            logger.info("  [dry] would write %s (+%d slice layouts)", _GEN_LAYOUTS, len(entries))

    # --- Write map_groups overlay (data/maps/map_groups.gen.json) ---
    # Seed from the PRISTINE upstream map_groups.json, append gMapGroup_Uranium. Always
    # built fresh from pristine (deterministic; the tracked file stays byte-for-byte
    # upstream). map_data_rules.mk reads this overlay when present (URANIUM_MAP_GROUPS).
    pristine_mg = fork / "data" / "maps" / "map_groups.json"
    gen_mg = fork / "data" / "maps" / _GEN_MAP_GROUPS
    mg = json.loads(pristine_mg.read_text(encoding="utf-8"))
    uranium_group = "gMapGroup_Uranium"
    uranium_maps = [consts[str(mid)]["dir_name"] for mid in SLICE_MAP_IDS]
    mg.setdefault("group_order", []).append(uranium_group)
    mg[uranium_group] = uranium_maps
    if not dry_run:
        gen_mg.write_text(json.dumps(mg, indent=2) + "\n", encoding="utf-8")
        logger.info("  wrote %s (+%s: %d maps)", _GEN_MAP_GROUPS, uranium_group, len(uranium_maps))
    else:
        logger.info("  [dry] would write %s (+%s)", _GEN_MAP_GROUPS, uranium_group)

    # --- Write alias header ---
    alias_src = out / "porymap" / "uranium_map_aliases.h"
    dest_alias = fork / "data" / "scripts" / "uranium_map_aliases.h"
    _copy(alias_src, dest_alias, "uranium_map_aliases.h", dry_run)

    # --- Write walker maps header (debug jump-menu macro) ---
    from rpg2gba.tileset_converter.map_constants import MapConstantRegistry
    _walker_reg = MapConstantRegistry(state_path=out / "porymap" / "map_constants.json")
    _walker_reg.load()
    dest_walker = fork / "include" / "uranium_walker_maps.h"
    if not dry_run:
        _walker_reg.write_walker_maps_header(SLICE_MAP_IDS, dest_walker)
        logger.info("  wrote uranium_walker_maps.h (%d maps)", len(SLICE_MAP_IDS))
    else:
        logger.info("  [dry] would write uranium_walker_maps.h")

    # --- Write flag registry header ---
    dest_flags = fork / "data" / "scripts" / "uranium_flags.h"
    _emit_flags_header(fork, dest_flags, compiled_texts, dry_run)

    # --- Write the slice include list pulled in by the event_scripts.s hook ---
    _write_event_includes(fork, consts, ce_pory.is_file(), dry_run)


# Region-capacity #defines in include/config/rpg2gba.h, keyed to the dump_header
# capacities dict (flag_registry.py) they gate.
_RPG2GBA_COUNT_DEFINES = {
    "flags": "RPG2GBA_GLOBAL_FLAGS_COUNT",
    "vars": "RPG2GBA_VARS_COUNT",
    "selfswitches": "RPG2GBA_SELFSWITCH_FLAGS_COUNT",
    "tempswitches": "RPG2GBA_TEMP_FLAGS_COUNT",
}
_RPG2GBA_GATE_RE = re.compile(r"#define\s+RPG2GBA_EXPAND_EVENT_RANGES\s+(\S+)")


def _load_rpg2gba_capacities(fork: Path) -> dict[str, int]:
    """Read include/config/rpg2gba.h and return the four region capacities.

    Fails loud if the fork lacks the RPG2GBA event-range expansion (missing
    header, gate compiled out, or a missing count #define) — emitting
    uranium_flags.h against an unexpanded engine would reintroduce the
    out-of-bounds-write bug the expansion fixed (audit findings F1/F2; see
    reference/guides/engine_extension_surface.md §2).
    """
    header = fork / "include" / "config" / "rpg2gba.h"
    if not header.is_file():
        raise RuntimeError(
            f"{header} not found — this fork lacks the RPG2GBA event-range "
            "expansion, so uranium_flags.h cannot be emitted safely (see "
            "reference/guides/engine_extension_surface.md §2)."
        )
    text = header.read_text(encoding="utf-8")

    gate = _RPG2GBA_GATE_RE.search(text)
    if gate is None or gate.group(1) != "TRUE":
        raise RuntimeError(
            f"{header}: RPG2GBA_EXPAND_EVENT_RANGES is not TRUE — the event-range "
            "expansion is compiled out, so emitting uranium_flags.h would "
            "reintroduce the out-of-bounds-write bug it fixed (see "
            "reference/guides/engine_extension_surface.md §2)."
        )

    capacities: dict[str, int] = {}
    for key, define in _RPG2GBA_COUNT_DEFINES.items():
        m = re.search(rf"#define\s+{define}\s+(\S+)", text)
        if m is None:
            raise RuntimeError(f"{header}: missing #define {define}")
        capacities[key] = int(m.group(1), 0)
    return capacities


def _emit_flags_header(
    fork: Path, dest: Path, compiled_texts: list[str], dry_run: bool
) -> None:
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
            capacities=_load_rpg2gba_capacities(fork),
        )
        logger.info("  wrote uranium_flags.h (%s)", dest)
    else:
        logger.info("  [dry] would write uranium_flags.h")


def _write_event_includes(
    fork: Path,
    consts: dict,
    has_common_events: bool,
    dry_run: bool,
) -> None:
    """Write data/maps/uranium_includes.inc — the GENERATED, gitignored list of slice
    script includes pulled in by the committed include-hook in data/event_scripts.s.

    The hook itself also `#include`s uranium_map_aliases.h + uranium_flags.h; those are
    C-preprocessor headers and must stay as `#include` lines in event_scripts.s (so the
    CPP pass sees them), which is why they live in the committed hook, not here."""
    includes: list[str] = []
    if has_common_events:
        includes.append('	.include "data/scripts/CommonEvents.inc"')
    for mid in SLICE_MAP_IDS:
        dir_name = consts[str(mid)]["dir_name"]
        includes.append(f'	.include "data/maps/{dir_name}/scripts.inc"')

    text = (
        "@ GENERATED by scripts/assemble_pathfinder.py — DO NOT EDIT, DO NOT COMMIT.\n"
        "@ Pulled in by the URANIUM PATHFINDER SLICE include-hook in data/event_scripts.s.\n"
        + "\n".join(includes) + "\n"
    )

    dest = fork / "data" / "maps" / "uranium_includes.inc"
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        logger.info("  wrote data/maps/uranium_includes.inc (%d includes)", len(includes))
    else:
        logger.info("  [dry] would write uranium_includes.inc (%d includes)", len(includes))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Report without modifying the fork.")
    ap.add_argument("--skip-graphics", action="store_true",
                    help="Skip S8a (Uranium tilesets already emitted).")
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

    if not args.skip_graphics:
        run_graphics_pass(out, fork, args.dry_run)

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
