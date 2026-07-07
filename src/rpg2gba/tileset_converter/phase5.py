"""Phase 5 orchestrator — build the Uranium map corpus into the fork.

ASSIGNMENT
==========
Objective
    Drive the existing, viewer-proven converters (graphics / layout / map
    constants / warp wiring) over an arbitrary batch of Uranium maps and assemble
    them into the vendored engine as a **warps-only** Map Walker corpus
    (`reference/map_walker_plan.md` §5). No Poryscript / event / NPC conversion —
    only warp_events survive (§5.3), so the whole Phase-4 script pipeline is
    skipped.

Per-map packing (the key §5.4 decision)
    Pooling metatiles per RMXP tileset overflows the 1024 budget for 19/38
    tilesets at full corpus, so each map gets its OWN physical tileset. The enabler
    is a synthetic per-map tileset id (`_synth_id` = 1000 + map_id) fed to
    `build_slice_tilesets`, whose group-by-`tileset_id` loop then yields one tileset
    per map with no loop rewrite. The synth id resolves back to the real RMXP
    tileset (for source art / passages) via the `source_tilesets` overlay key;
    `convert_layout` looks up by the same synth key (`tileset_key=`).

Five steps (`convert_all`)
    1. mint MAP_*/LAYOUT_* constants + alias header        (map_constants)
    2. warps-only map.json per map + warp-source coords     (metadata_wiring)
    3. per-map graphics: synth tilesets + overlay            (build_slice_tilesets)
    4. layout .bin per map (synth tileset_key)               (convert_layout)
    5. assemble into the fork (copy map.json/.bin, empty scripts.inc, overlays,
       alias header, includes — warps-only, no .pory/CommonEvents/flags)

Constraints
    - Idempotent: a clean re-run reproduces byte-identical output (CLAUDE.md §4.2).
    - Fail loud per map with the map id in context (CLAUDE.md §4.5); the metatile
      budget guard in `emit_tileset` already fails loud on overflow.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Output tree (under output/uranium-build/, set by the caller / pipeline).
PORYMAP_SUBDIR = "porymap"

# Synthetic per-map tileset ids live above the real RMXP range (0..60) so they
# never collide; one physical tileset per map (§5.4).
_SYNTH_BASE = 1000

_URANIUM_GROUP = "gMapGroup_Uranium"
_GEN_MAP_GROUPS = "map_groups.gen.json"
_GEN_LAYOUTS = "layouts.gen.json"

# Shared tiny dummy layout the stock Emerald maps are repointed at when dropping
# stock map data (§5.5). Never rendered — the walker only shows Uranium maps.
_STUB_LAYOUT_DIR = "UraniumWalkerStub"


def _synth_id(map_id: int) -> int:
    """The synthetic tileset id that gives `map_id` its own physical tileset."""
    return _SYNTH_BASE + map_id


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _stub_stock_layout_bins(fork: Path, gen_layouts: Path) -> None:
    """Drop stock Emerald map data from the ROM (map_walker_plan §5.5).

    Repoint every layout entry in ``gen_layouts`` at a shared tiny dummy
    blockdata/border pair. Called on the freshly-copied pristine manifest (stock
    entries only) BEFORE the Uranium batch is appended, so only stock maps are
    stubbed. Each stock ``.incbin`` then embeds ~2/8 bytes instead of the real
    map, cutting ~1.1 MB while every ``MAP_*``/``LAYOUT_*`` constant (and the
    ``gMapLayouts[]`` slot count) is untouched — no C reference breaks. The stub
    layout is never rendered: the walker only shows Uranium maps.
    """
    stub_dir = fork / "data" / "layouts" / _STUB_LAYOUT_DIR
    stub_dir.mkdir(parents=True, exist_ok=True)
    # 1x1 blockdata (2 bytes) + a 2x2 border (8 bytes); dimensions in the layout
    # struct are left as-is (a stock map is never actually loaded in walker mode).
    (stub_dir / "map.bin").write_bytes(b"\x00\x00")
    (stub_dir / "border.bin").write_bytes(b"\x00" * 8)
    rel_map = f"data/layouts/{_STUB_LAYOUT_DIR}/map.bin"
    rel_border = f"data/layouts/{_STUB_LAYOUT_DIR}/border.bin"
    data = json.loads(gen_layouts.read_text(encoding="utf-8"))
    stubbed = 0
    for entry in data.get("layouts", []):
        if "blockdata_filepath" in entry:
            entry["blockdata_filepath"] = rel_map
        if "border_filepath" in entry:
            entry["border_filepath"] = rel_border
        stubbed += 1
    gen_layouts.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "  dropped stock map data: repointed %d layout(s) at %s/",
        stubbed, _STUB_LAYOUT_DIR,
    )


def _git_tracked_dirs(fork: Path, rel: str) -> set[str]:
    """Names of git-tracked subdirectories of ``fork/rel`` (the pristine set)."""
    proc = subprocess.run(
        ["git", "-C", str(fork), "ls-files", "-z", "--", rel],
        capture_output=True, check=True,
    )
    tracked: set[str] = set()
    for path in proc.stdout.decode("utf-8").split("\0"):
        parts = Path(path).parts
        # rel is e.g. "data/maps" (2 components); a file inside a subdir has >3.
        if len(parts) > 3:
            tracked.add(parts[2])
    return tracked


def _prune_stale_generated_dirs(
    fork: Path, batch_dirs: set[str], *, tracked_dirs: set[str] | None = None,
) -> None:
    """Delete generated per-map dirs left by a prior (wider) run (§4.2 idempotence).

    The engine makefile discovers maps by globbing ``data/maps/*/`` — a stale
    Uranium dir from an earlier, larger batch breaks the build (missing
    events.inc / unmatched LAYOUT_*). Stock = git-tracked content (generated
    output is gitignored, and map_groups.json is NOT a complete stock list —
    upstream ships tracked dirs outside every group, e.g. Route6_UnusedHouse_Frlg,
    that event_scripts.s still includes). Anything untracked that is not in THIS
    batch (or the stub) is stale generated output and is removed. ``tracked_dirs``
    is injectable for tests; by default it is read from git, fail-loud.
    """
    pruned = 0
    for rel in ("data/maps", "data/layouts"):
        tracked = _git_tracked_dirs(fork, rel) if tracked_dirs is None else tracked_dirs
        keep = tracked | batch_dirs | {_STUB_LAYOUT_DIR}
        for child in (fork / rel).iterdir():
            if child.is_dir() and child.name not in keep:
                shutil.rmtree(child)
                pruned += 1
    if pruned:
        logger.info("  pruned %d stale generated map/layout dir(s) from a prior run", pruned)


def convert_all(
    map_ids: list[int],
    *,
    out_dir: Path,
    fork: Path,
    reference_dir: Path = Path("reference"),
    clean: bool = False,
    dry_run: bool = False,
    drop_stock_map_data: bool = True,
) -> None:
    """Build `map_ids` into `fork` as a warps-only Map Walker corpus.

    `out_dir` is the build root (``output/uranium-build``); `fork` is
    ``$RPG2GBA_POKEEMERALD`` (the vendored ``engine/``). `reference_dir` holds the
    base ``tileset_map.json`` + ``map_name_overrides.json``. `clean` wipes the
    regenerable staging/overlay first.

    `drop_stock_map_data` (default True) repoints every stock Emerald layout at a
    tiny shared dummy so ~1.1 MB of stock map blockdata stays out of the ROM (§5.5).
    Safe: the walker never loads stock maps (Uranium maps have ``connections:null``
    and walker mode suppresses stock events), and every ``MAP_*``/``LAYOUT_*``
    constant is preserved, so no C reference breaks."""
    from rpg2gba.tileset_converter import map_constants as mc
    from rpg2gba.tileset_converter import metadata_wiring as mw
    from rpg2gba.tileset_converter.graphics.build_slice_tilesets import (
        build_slice_tilesets,
    )
    from rpg2gba.tileset_converter.layout import append_layouts, convert_layout
    from rpg2gba.tileset_converter.tile_map import load_tile_map

    map_ids = list(map_ids)
    maps_dir = out_dir / "maps"
    porymap = out_dir / PORYMAP_SUBDIR
    staging = out_dir / "staging"
    overlay_out = reference_dir / "tileset_map.gen.json"

    if clean and not dry_run:
        for victim in (staging, porymap / "maps", overlay_out):
            if victim.is_dir():
                shutil.rmtree(victim)
            elif victim.is_file():
                victim.unlink()
        logger.info("clean: wiped staging + porymap/maps + %s", overlay_out)

    logger.info("phase5 walker build: %d maps -> %s", len(map_ids), fork)

    # --- 1. constants + alias header -----------------------------------------
    registry = mc.build_map_constants(
        map_ids,
        map_infos_path=out_dir / "map_infos.json",
        overrides_path=reference_dir / "map_name_overrides.json",
        state_path=porymap / "map_constants.json",
        alias_header_path=porymap / "uranium_map_aliases.h",
        # Walker corpus: ~32 duplicate-name groups (multi-floor caves, "(Metro)"
        # variants). Suffix their internal constants with the map id rather than
        # demanding ~80 hand-authored map_name_overrides for a debug build.
        auto_disambiguate=True,
    )

    # --- 2. warps-only map.json + warp-source coords -------------------------
    warp_overrides = mw.build_warps_only_maps(
        map_ids,
        maps_dir=maps_dir,
        registry=registry,
        metadata_path=out_dir / "intermediate" / "map_metadata.json",
        out_dir=porymap / "maps",
    )

    # --- 3. per-map graphics (synthetic tileset ids) -------------------------
    maps: list[tuple[int, dict]] = [
        (mid, json.loads((maps_dir / f"Map{mid:03d}.json").read_text(encoding="utf-8")))
        for mid in map_ids
    ]
    synth_to_real: dict[int, int] = {}
    synth_maps: list[tuple[int, dict]] = []
    for mid, map_json in maps:
        synth = _synth_id(mid)
        synth_to_real[synth] = int(map_json["tileset_id"])
        synth_json = dict(map_json)  # shallow: only the top-level tileset_id changes
        synth_json["tileset_id"] = synth
        synth_maps.append((mid, synth_json))

    build_slice_tilesets(
        synth_maps,
        warp_overrides,
        fork=fork,
        base_tile_map=reference_dir / "tileset_map.json",
        overlay_out=overlay_out,
        tilesets_json=out_dir / "tilesets.json",
        source_tileset_of=lambda s: synth_to_real[s],
        dry_run=dry_run,
    )

    # --- 4. layout .bin per map (looked up by the synthetic key) -------------
    tile_map = load_tile_map(reference_dir / "tileset_map.json", out_dir / "tilesets.json")
    entries: list[dict] = []
    for mid, map_json in maps:
        consts = registry.get(mid)
        layout = convert_layout(
            map_json,
            tile_map,
            name=consts.dir_name,
            layout_const=consts.layout_const,
            warp_overrides=warp_overrides.get(mid),
            tileset_key=_synth_id(mid),
        )
        entries.append(layout.to_layouts_entry())
        if not dry_run:
            layout.write(staging)
        logger.info("  Map%03d (%s): %d blocks", mid, consts.dir_name, len(layout.blocks))

    if not dry_run:
        append_layouts(entries, staging / "layouts" / "layouts.json")

    # --- 5. assemble into the fork (warps-only) ------------------------------
    if dry_run:
        logger.info("=== dry-run complete, fork untouched ===")
        return
    _assemble_fork(
        map_ids, registry, porymap, staging, fork,
        batch_layouts=entries,
        drop_stock_map_data=drop_stock_map_data,
    )
    logger.info("=== walker corpus assembled — build: make -C %s -j$(nproc) modern ===", fork)


def _assemble_fork(
    map_ids, registry, porymap: Path, staging: Path, fork: Path,
    *, batch_layouts: list[dict], drop_stock_map_data: bool = True,
) -> None:
    """Copy the warps-only corpus into the fork + write the overlay glue the
    engine include-hook (data/event_scripts.s) pulls in. No scripts: each map gets
    an empty `<Dir>_MapScripts` table; `uranium_flags.h` is an empty stub."""
    staging_layouts = staging / "layouts"

    _prune_stale_generated_dirs(fork, {registry.get(mid).dir_name for mid in map_ids})

    for mid in map_ids:
        dir_name = registry.get(mid).dir_name

        _copy(porymap / "maps" / dir_name / "map.json",
              fork / "data" / "maps" / dir_name / "map.json")

        # Every pokeemerald map needs its `<Dir>_MapScripts` symbol; warps-only =
        # an empty map-script table (the poryscript `mapscripts X {}` equivalent).
        scripts_inc = fork / "data" / "maps" / dir_name / "scripts.inc"
        scripts_inc.parent.mkdir(parents=True, exist_ok=True)
        scripts_inc.write_text(f"{dir_name}_MapScripts::\n\t.byte 0\n", encoding="utf-8")

        for bin_name in ("map.bin", "border.bin"):
            src = staging_layouts / dir_name / bin_name
            if not src.is_file():
                raise FileNotFoundError(f"layout output missing: {src} (run step 4 first)")
            _copy(src, fork / "data" / "layouts" / dir_name / bin_name)

    # layouts.gen.json: pristine upstream manifest + the batch layouts (the tracked
    # layouts.json stays byte-for-byte upstream; map_data_rules.mk reads the overlay).
    from rpg2gba.tileset_converter.layout import append_layouts
    gen_layouts = fork / "data" / "layouts" / _GEN_LAYOUTS
    shutil.copy2(fork / "data" / "layouts" / "layouts.json", gen_layouts)
    # Repoint the pristine (stock-only) entries at a dummy BEFORE appending the
    # Uranium batch, so only stock maps are stubbed; the batch keeps real art.
    if drop_stock_map_data:
        _stub_stock_layout_bins(fork, gen_layouts)
    # Append THIS batch's entries (passed in), never the cumulative staging
    # layouts.json — a prior wider run would leak layouts whose tilesets this
    # build doesn't emit (undefined gTileset_Uranium* refs at link).
    append_layouts(batch_layouts, gen_layouts)
    logger.info("  wrote %s (+%d layouts)", _GEN_LAYOUTS, len(batch_layouts))

    # map_groups.gen.json: pristine upstream + gMapGroup_Uranium (the batch dirs).
    mg = json.loads((fork / "data" / "maps" / "map_groups.json").read_text(encoding="utf-8"))
    mg.setdefault("group_order", []).append(_URANIUM_GROUP)
    mg[_URANIUM_GROUP] = [registry.get(mid).dir_name for mid in map_ids]
    (fork / "data" / "maps" / _GEN_MAP_GROUPS).write_text(
        json.dumps(mg, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("  wrote %s (+%s: %d maps)", _GEN_MAP_GROUPS, _URANIUM_GROUP, len(map_ids))

    # Alias header (MAP_URANIUM_<N> -> MAP_<NAME>) — #included by the hook.
    registry.write_alias_header(fork / "data" / "scripts" / "uranium_map_aliases.h")

    # Walker maps header (debug jump-menu macro) — #included by uranium_map_walker.c.
    # List the maps actually in THIS build (the batch), not the fixed slice, so the
    # jump menu can reach every map present in the ROM.
    registry.write_walker_maps_header(
        list(map_ids), fork / "include" / "uranium_walker_maps.h"
    )

    # Empty flags header — the hook #includes it; warps-only has no flags.
    (fork / "data" / "scripts" / "uranium_flags.h").write_text(
        "// GENERATED by phase5 — Map Walker warps-only build: no flags.\n",
        encoding="utf-8",
    )

    # Empty NPC-sprite gen files — the committed object-event sentinel hooks
    # #include them, so even a warps-only (no-NPC) walker build must have at
    # least the stub forms on disk or make fails on missing includes.
    from .graphics import sprite_emit
    sprite_emit.write_stub_gen_files(fork)

    # The include list the event_scripts.s hook pulls in (no CommonEvents).
    includes = [
        f'\t.include "data/maps/{registry.get(mid).dir_name}/scripts.inc"'
        for mid in map_ids
    ]
    (fork / "data" / "maps" / "uranium_includes.inc").write_text(
        "@ GENERATED by phase5 (Map Walker) — DO NOT EDIT, DO NOT COMMIT.\n"
        "@ Pulled in by the URANIUM PATHFINDER SLICE include-hook in data/event_scripts.s.\n"
        + "\n".join(includes) + "\n",
        encoding="utf-8",
    )
    logger.info("  wrote uranium_includes.inc (%d maps) + empty uranium_flags.h", len(includes))


def convert_one(map_path: Path, out_dir: Path) -> None:
    """Single-map debug conversion. Warp pairing needs the whole batch, so this just
    routes a one-map batch through `convert_all` (out-of-batch warps drop out)."""
    raise NotImplementedError(
        "phase5.convert_one: use convert_all([map_id], ...) — warp pairing is batch-level"
    )
