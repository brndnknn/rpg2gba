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

Pass 2.5 (S8b4) — wild encounter table staging
    Upsert the slice's converted wild-encounter tables (Phase 2 output,
    intermediate/wild_encounters.json) into an overlay of the fork's
    src/data/wild_encounters.json (gWildMonHeaders group), keyed by MAP_* --
    an overlay like layouts/map_groups (src/data/wild_encounters.gen.json,
    gitignored; see run_encounters_pass docstring for the URANIUM_WILD_ENCOUNTERS
    hook in engine/Makefile that selects it over the committed file).

Pass 2.6 (S8b5) — PokePod rematch table staging
    Detect phone-rematch events (pbPhoneRegisterBattle) across the build set and
    emit the REMATCH_* enum members + gRematchTable rows they need, then install
    them as gitignored .gen.h fragments behind committed #include hooks in
    include/constants/rematches.h and src/battle_setup.c (see run_rematch_pass).

Pass 2.7 (S8b6) — heal-location overlay
    Derive the slice's white-out respawn points from `pbSetPokemonCenter` call
    sites (`rpg2gba.pbs_converter.heal_locations`) and append them to an
    overlay of the fork's `src/data/heal_locations.json`
    (src/data/heal_locations.gen.json, gitignored; see run_heal_location_pass
    docstring for the URANIUM_HEAL_LOCATIONS hook in
    engine/json_data_rules.mk that selects it over the committed file).

Pass 3 (S8d) — berry tree seed table
    Emit fork data/scripts/uranium_berry_trees.h (gitignored): the pre-planted
    berry-tree save-slot table consumed by new_game.c's NewGameInitData, right
    after ClearBerryTrees().

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

from rpg2gba.tileset_converter.map_set import (
    SLICE_MAP_IDS,
    WALKABLE_OVERRIDES,
    load_slice_tileset_groups,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slice config (matches PATHFINDER_SLICE_ROADMAP.md S1 decisions)
# ---------------------------------------------------------------------------

# SLICE_MAP_IDS (the 3-map slice, boot order 1F/2F/Moki) is the single source of
# truth in rpg2gba.tileset_converter.map_set, imported above. Phase B will set the
# build target from a --maps selector (slice/full/id-list) via map_set.parse_map_ids.

# S5 warp overrides: warp-source + gated-door coords. The layout converter
# stamps the tileset's warp metatile (MB_NON_ANIMATED_DOOR, collision 0) at each
# so the warp_event actually fires -- a generic floor tile (MB_NORMAL) under a
# warp is inert (S9 fix 2026-06-18).
#
# DERIVED, not hand-listed, since 2026-09-08 (PROJECT_TODO #25, POST_CH05_REVIEW
# G2). `metadata_wiring.build_slice_maps` already computes this exact set
# (`src_coords | gated_door_cells`) while wiring the maps; runbook step 4
# (`scripts/stage_slice_scripts.py --write`) persists it to
# `warp_overrides.gen.json` and this pass reads it back. Before that, a
# hand-written dict here had to be extended once per chapter, and CH02, CH03 and
# CH05 each opened their own gate by hand -- CH05's four cells were the
# difference between a working chapter and a completely inert one, with every
# warp event compiling cleanly the whole time.
#
# The arrival warps `_resolve_all_warp_events` mints on every destination are
# correctly absent: they are not real code-201 events, so they never enter
# `src_coords`. They are plain floor by design and must stay that way.
#
# `load_warp_overrides` fails loud when the file is missing rather than
# defaulting to an empty set -- "no doors anywhere" is the exact failure this
# guards against, and it must never be the silent default (CLAUDE.md section 4.5).


def _load_warp_overrides(out: Path) -> dict[int, set[tuple[int, int]]]:
    from rpg2gba.tileset_converter.metadata_wiring import load_warp_overrides

    return load_warp_overrides(out)


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
        # Custom-route table gen.h: staging writes the real table (route ids keyed
        # to map.json). Here just guarantee a stub exists so a fork assembled
        # without a prior staging pass still resolves the engine #include — never
        # clobber a real table (only-if-missing).
        from rpg2gba.tileset_converter.route_table_emit import write_stub

        route_gen = (
            fork / "src" / "data" / "object_events" / "uranium_move_routes.gen.h"
        )
        if not route_gen.exists():
            write_stub(fork)
    else:
        logger.info("  [dry] would run NPC sprite pass -> engine gen files")

    # Per-map synthetic tileset ids (map_set.synth_tileset_id; maps joined by an
    # emitted connection share one, see tileset_groups): pooling metatiles
    # per RMXP tileset overflows the GBA's 1024 hard caps once two maps share an
    # RMXP tileset id (e.g. Map032 union Map033 on RMXP tileset 22 -> 1607
    # metatiles / 1611 tiles). Giving each map its own synthetic tileset_id makes
    # build_slice_tilesets' group-by-tileset_id loop yield one physical tileset
    # per map; source_tileset_of resolves the synthetic id back to the real RMXP
    # id for source art / passages / priorities / terrain tags (mirrors phase5's
    # walker path — phase5.py convert_all step 3).
    from rpg2gba.tileset_converter.metadata_wiring import collect_stair_behavior_cells
    from rpg2gba.tileset_converter.seam_warps import (
        behavior_cells_for,
        load_seam_warps,
        seams_for_slice,
    )

    # seam_warps.json (CLAUDE.md §4.3): synthetic arrow-warp cells get behavior
    # overrides through the SAME kind-generic mechanism as diagonal stairs —
    # merged straight into `stair_cells` (see build_slice_tilesets' docstring).
    slice_seams = seams_for_slice(load_seam_warps(), set(SLICE_MAP_IDS))
    seam_behavior_cells = behavior_cells_for(slice_seams)

    # Maps joined by an emitted scrolling connection share ONE synthetic tileset
    # (the engine draws a neighbour through the current map's tileset); every
    # other map keeps its own. Fails loud if a joined pair has different real
    # RMXP tilesets.
    groups = load_slice_tileset_groups(out, SLICE_MAP_IDS)

    maps: list[tuple[int, dict]] = []
    synth_to_real: dict[int, int] = {}
    stair_cells: dict[int, dict[tuple[int, int], str]] = {}
    for map_id in SLICE_MAP_IDS:
        map_json = json.loads(
            (out / "maps" / f"Map{map_id:03d}.json").read_text(encoding="utf-8")
        )
        synth = groups[map_id]
        synth_to_real[synth] = int(map_json["tileset_id"])
        synth_json = dict(map_json)  # shallow: only the top-level tileset_id changes
        synth_json["tileset_id"] = synth
        maps.append((map_id, synth_json))
        stair_cells[map_id] = {
            **collect_stair_behavior_cells(map_json),
            **seam_behavior_cells.get(map_id, {}),
        }

    build_slice_tilesets(
        maps,
        _load_warp_overrides(out),
        fork=fork,
        base_tile_map=Path("reference/tileset_map.json"),
        overlay_out=Path("reference/tileset_map.gen.json"),
        tilesets_json=out / "tilesets.json",
        source_tileset_of=lambda s: synth_to_real[s],
        stair_cells=stair_cells,
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
) -> list[dict]:
    """Returns this batch's layout entries (`Layout.to_layouts_entry()` dicts) so
    `run_fork_pass` can append exactly this batch to the fork overlay, rather than
    re-reading the cumulative staging layouts.json (see `run_fork_pass` docstring)."""
    logger.info("=== S8b: layout conversion ===")
    from rpg2gba.tileset_converter.layout import append_layouts, convert_layout
    from rpg2gba.tileset_converter.metadata_wiring import (
        collect_stair_behavior_cells,
        collect_through_block_cells,
    )
    from rpg2gba.tileset_converter.seam_warps import (
        behavior_cells_for,
        load_seam_warps,
        seams_for_slice,
    )
    from rpg2gba.tileset_converter.tile_map import load_tile_map

    tile_map = load_tile_map(
        Path("reference/tileset_map.json"),
        out / "tilesets.json",
    )

    # seam_warps.json (CLAUDE.md §4.3): same merge as run_graphics_pass — the
    # arrow-warp cells go through convert_layout's `behavior_overrides` param,
    # the exact mechanism collect_stair_behavior_cells already feeds.
    slice_seams = seams_for_slice(load_seam_warps(), set(SLICE_MAP_IDS))
    seam_behavior_cells = behavior_cells_for(slice_seams)

    all_warp_overrides = _load_warp_overrides(out)
    groups = load_slice_tileset_groups(out, SLICE_MAP_IDS)

    entries: list[dict] = []
    for map_id in SLICE_MAP_IDS:
        entry = consts[str(map_id)]
        map_json_path = out / "maps" / f"Map{map_id:03d}.json"
        map_json = json.loads(map_json_path.read_text(encoding="utf-8"))

        warp_overrides = all_warp_overrides.get(map_id, set())
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
            tileset_key=groups[map_id],
            behavior_overrides={
                **collect_stair_behavior_cells(map_json),
                **seam_behavior_cells.get(map_id, {}),
            },
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

    return entries


# ---------------------------------------------------------------------------
# S8b2: Species staging (STARTER_SPECIES_PLAN.md §4-W6)
# ---------------------------------------------------------------------------

# Header/inc filename -> engine-relative destination directory. Mirrors the
# mapping documented in species_converter/stage.py's module docstring
# ("Generated files" list) and STARTER_SPECIES_PLAN.md §3's table.
_SPECIES_HEADER_DEST_DIRS: dict[str, str] = {
    "uranium_species_constants.h": "include/constants",
    "uranium_pokedex_ids.h": "include/constants",
    "uranium_cries_enum.h": "include/constants",
    "uranium_learnsets.h": "src/data/pokemon",
    "uranium_species_info.h": "src/data/pokemon",
    "uranium_species_graphics.h": "src/data/graphics",
    "uranium_cry_table_forward.inc": "sound",
    "uranium_cry_table_reverse.inc": "sound",
    "uranium_cry_sound_data.inc": "sound",
}


def run_species_pass(out: Path, fork: Path, uranium_src: Path, dry_run: bool) -> None:
    """Convert the six STARTER_SPECIES starters + stage the overlay into the
    fork: run the art converters (battlers/icons/cries) first so their
    measured Y-offsets/icon-palette-index sidecars can be threaded into
    `stage.write_all`'s `overrides=`, then emit the generated headers/incs
    and copy everything (headers, per-species art, per-species cry wavs)
    into `$RPG2GBA_POKEEMERALD`.

    Must run BEFORE S8c (`run_fork_pass`): the poryscript capability gate
    there reads `species_manifest.json` from the same `out/species/` path
    this pass writes it to, so an unstaged/stale manifest would silently
    under-gate species references.

    Conversion + emission always run (writing only into `out/`, never
    `fork/`) so a --dry-run log is a faithful preview of what WOULD be
    copied; only the copies into `fork/` are gated by `dry_run` (via
    `_copy`, matching every other pass in this script).
    """
    logger.info("=== S8b2: species staging ===")
    from dataclasses import replace

    from rpg2gba.species_converter import battlers as species_battlers
    from rpg2gba.species_converter import common as species_common
    from rpg2gba.species_converter import cries as species_cries
    from rpg2gba.species_converter import icons as species_icons
    from rpg2gba.species_converter import stage as species_stage

    species_dir = out / species_common.SPECIES_OUT_SUBDIR
    art_dir = species_dir / "art"
    cries_dir = species_dir / "cries"

    # --- Art converters first: their sidecars feed stage.write_all's overrides ---
    battler_results = species_battlers.convert_starter_battlers(uranium_src, art_dir)
    icon_result = species_icons.convert_starter_icons(uranium_src, fork, art_dir)
    species_cries.convert_starter_cries(uranium_src, cries_dir)

    overrides: dict[str, species_stage.SpeciesOverride] = {}
    for r in battler_results:
        ov = overrides.get(r.internal_name, species_stage.SpeciesOverride())
        overrides[r.internal_name] = replace(
            ov, front_pic_y_offset=r.front_y_offset, back_pic_y_offset=r.back_y_offset
        )
    for r in icon_result.species:
        ov = overrides.get(r.spec.internal_name, species_stage.SpeciesOverride())
        overrides[r.spec.internal_name] = replace(ov, icon_pal_index=r.icon_pal_index)

    manifest = species_stage.write_all(
        uranium_src=uranium_src,
        engine_dir=fork,
        out_dir=species_dir,
        overrides=overrides,
    )
    logger.info("  staged %d species into the manifest", len(manifest["species"]))

    # --- Copy generated headers/incs into the fork tree ---
    for name, dest_dir in _SPECIES_HEADER_DEST_DIRS.items():
        _copy(species_dir / name, fork / dest_dir / name, name, dry_run)

    # --- Copy per-species art + cry wavs into the fork tree ---
    for spec in species_common.STARTER_SPECIES:
        asset_name = species_common.asset_dir_name(spec)
        src_art_dir = art_dir / asset_name
        dest_art_dir = fork / species_common.ENGINE_GFX_ROOT / asset_name
        for fname in (
            species_common.FRONT_PNG,
            species_common.BACK_PNG,
            species_common.NORMAL_PAL,
            species_common.SHINY_PAL,
            species_common.ICON_PNG,
        ):
            _copy(
                src_art_dir / fname,
                dest_art_dir / fname,
                f"{spec.internal_name} {fname}",
                dry_run,
            )

        wav_name = f"{asset_name}.wav"
        _copy(
            cries_dir / wav_name,
            fork / species_common.ENGINE_CRY_ROOT / wav_name,
            f"{spec.internal_name} cry",
            dry_run,
        )


# ---------------------------------------------------------------------------
# S8b3: Trainer pic staging
# ---------------------------------------------------------------------------

# Header/inc filename -> engine-relative destination directory. Mirrors
# _SPECIES_HEADER_DEST_DIRS above and trainer_converter/stage.py's module
# docstring ("Generated files" list).
_TRAINER_HEADER_DEST_DIRS: dict[str, str] = {
    "uranium_trainer_front_pic_ids.h": "include/constants",
    "uranium_trainer_back_pic_ids.h": "include/constants",
    "uranium_trainer_graphics.h": "src/data/graphics",
    "uranium_trainer_sprites.h": "src/data/graphics",
    "uranium_trainer_backsprites.h": "src/data/graphics",
    # Trainer battle data (2026-08-05). The .party fragment lands under include/
    # rather than src/data/ on purpose: trainer_rules.mk pipes trainers.party
    # through `$(CPP) $(CPPFLAGS) -traditional-cpp -` on STDIN, so there is no
    # current-file directory and only `-iquote include` resolves the hook's
    # `#include "data/uranium_trainer_party.inc"`.
    "uranium_trainer_ids.h": "include/constants",
    "uranium_trainer_party.inc": "include/data",
}


def run_trainer_pass(out: Path, fork: Path, uranium_src: Path, dry_run: bool) -> None:
    """Convert the slice trainer pics (RIVAL front, PLAYER_MALE back) and
    stage the overlay into the fork: run `trainer_converter.stage.stage_slice`
    (always writes into `out/`, never `fork/`), then copy the generated
    headers and per-trainer art into `$RPG2GBA_POKEEMERALD`.

    Must run BEFORE S8c (`run_fork_pass`): the poryscript capability gate
    there reads `trainer_manifest.json` from the same `out/trainers/` path
    this pass writes it to, so an unstaged/stale manifest would silently
    under-gate trainer-pic references.

    Conversion + emission always run (writing only into `out/`, never
    `fork/`) so a --dry-run log is a faithful preview of what WOULD be
    copied; only the copies into `fork/` are gated by `dry_run` (via
    `_copy`, matching every other pass in this script).
    """
    logger.info("=== S8b3: trainer pic staging ===")
    from rpg2gba.trainer_converter import pics as trainer_pics
    from rpg2gba.trainer_converter import stage as trainer_stage

    trainer_dir = out / "trainers"
    manifest_path = trainer_stage.stage_slice(uranium_src, trainer_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    logger.info("  staged %d trainer pic(s) into the manifest", len(manifest["trainers"]))

    # --- Copy generated headers into the fork tree ---
    for name, dest_dir in _TRAINER_HEADER_DEST_DIRS.items():
        _copy(trainer_dir / name, fork / dest_dir / name, name, dry_run)

    # trainer_rules.mk's `%.h: %.party $(TRAINERPROC)` rule only lists
    # trainers.party itself as a prerequisite -- it doesn't know
    # trainers.party #includes uranium_trainer_party.inc, so copying a
    # changed .inc above leaves src/data/trainers.h stale (make sees
    # trainers.party's own mtime unchanged and skips TRAINERPROC). A newly
    # staged battle then compiles with a trainer id `gTrainers[]` has no
    # entry for -- not a build error, a runtime "OPPONENT NEEDS A VALID
    # NAME" assert (2026-08-15 finding, Mawuli/CH03). Touch trainers.party
    # so its mtime always wins and make regenerates trainers.h.
    if not dry_run:
        trainers_party = fork / "src" / "data" / "trainers.party"
        if trainers_party.is_file():
            trainers_party.touch()
            logger.info("  touched %s (force trainers.h regen)", trainers_party)

    # --- Copy per-trainer art into the fork tree ---
    # stage.py bakes `graphics/trainers/uranium/<asset_dir>/<file>` engine-relative
    # paths into its INCGFX declarations (uranium_trainer_graphics.h) and the
    # manifest's art_files entries. A mismatch here is a silent build break
    # (INCGFX would point at a file that was never copied), so assert
    # agreement rather than assuming it.
    # One asset dir PER staged pic since 2026-08-05 (CH02 staged 7 trainer-class
    # sprites alongside the original RIVAL/PLAYER_MALE pair) — the old single
    # flat `slice1` dir silently collided once more than one pic existed.
    art_by_kind = {
        "front": (trainer_pics.FRONT_PNG, trainer_pics.FRONT_PAL),
        "back": (trainer_pics.BACK_PNG, trainer_pics.BACK_PAL),
    }
    for entry in manifest["trainers"]:
        kind = entry["kind"]
        if kind not in art_by_kind:
            continue  # "battle" entries are party data; they carry no art_files
        expected_asset_dir = (
            f"{trainer_stage.ENGINE_GFX_ROOT.as_posix()}/{entry['internal_name'].lower()}"
        )
        if entry["asset_dir"] != expected_asset_dir:
            raise RuntimeError(
                f"trainer manifest asset_dir mismatch for {entry.get('internal_name')}: "
                f"manifest says {entry['asset_dir']!r}, stage.py constants say "
                f"{expected_asset_dir!r} — INCGFX paths and copy destinations would diverge"
            )
        png_name, pal_name = art_by_kind[kind]
        for fname, art_key in ((png_name, "png"), (pal_name, "pal")):
            src = trainer_dir / entry["internal_name"].lower() / fname
            dest_rel = entry["art_files"][art_key]
            expected_dest_rel = f"{expected_asset_dir}/{fname}"
            if dest_rel != expected_dest_rel:
                raise RuntimeError(
                    f"trainer manifest art path mismatch for {entry.get('internal_name')}: "
                    f"manifest says {dest_rel!r}, expected {expected_dest_rel!r}"
                )
            dest = fork / dest_rel
            _copy(src, dest, f"{entry.get('internal_name')} {art_key} ({kind})", dry_run)


# ---------------------------------------------------------------------------
# S8b4: Wild encounter table staging
# ---------------------------------------------------------------------------

def run_encounters_pass(out: Path, fork: Path, consts: dict, dry_run: bool) -> None:
    """Stage the slice's wild-encounter tables into an overlay of the fork's
    `gWildMonHeaders` group so `GetCurrentMapWildMonHeaderId`
    (engine/src/wild_encounter.c:379-404) finds a row for each slice map instead
    of returning `HEADER_NONE` and silently suppressing all encounters -- the
    bug this pass fixes. Encounter DATA is already fully converted
    (`output/uranium-build/intermediate/wild_encounters.json`,
    `pbs_converter/encounters.py`); this pass is purely the missing wiring step.

    Writes `src/data/wild_encounters.gen.json` (gitignored), never the committed
    `src/data/wild_encounters.json` -- mirrors the `layouts.gen.json` /
    `map_groups.gen.json` overlay pattern `run_fork_pass` already uses.
    `engine/Makefile`'s `URANIUM_WILD_ENCOUNTERS` var (near line 253) prefers the
    `.gen.json` overlay when present, falling back to the committed file when
    absent, so a repo with no overlay on disk builds pristine upstream behavior.
    `wild_encounters.py.upsert_encounters` always reads the committed file fresh
    as its base (never a prior overlay), so repeated runs are idempotent and
    never dirty tracked vendored source.

    Named S8b4 (not S8b3 -- that label is already `run_trainer_pass`). Placed
    AFTER the species/trainer staging block in `main()`: the known-species
    union it builds needs `species/species_manifest.json`, which only exists
    once S8b2 (`run_species_pass`) has run (this run or a prior one -- fails
    loud, matching `run_fork_pass`'s species-manifest gate, if the manifest is
    absent rather than silently forcing S8b2 to run). It does not need to run
    after `run_fork_pass` (S8c) or `run_berry_tree_pass` (S8d) since it writes
    to a different fork target (`src/data/wild_encounters.json`) that no other
    pass touches; running it before S8c/S8d keeps all "mutate the fork tree"
    passes grouped together ahead of the final assembly step, matching the
    existing S8b2/S8b3/S8c/S8d ordering.

    `consts` is the already-loaded `map_constants.json` dict (`main()` reads it
    once, before any pass runs) -- the map-id -> MAP_* mapping this pass needs
    is read straight from it (`consts[str(mid)]["map_const"]`), never re-minted
    (CLAUDE.md §4.3: `map_constants.py`'s registry is the one place that mints
    `MAP_*` names).

    The known-species set is the union of:
      - Uranium species staged by S8b2 (`species/species_manifest.json`'s
        `species_constant` field per entry -- ONLY species actually staged,
        mirroring `fork_index.registry_extra_symbols`' species-manifest scoping
        discipline: a species merely named in `reference/uranium_id_map.json`
        but never staged must still be rejected)
      - vanilla species the fork already defines, read via the fork capability
        index (`conversion_agent.fork_index`, CLAUDE.md §4.7) rather than a new
        header parser -- `ForkIndex.constants` already aggregates every
        `#define`/enum member across `engine/include/constants/*.h` (species.h
        included), filtered here to the `SPECIES_` prefix.
    """
    logger.info("=== S8b4: encounter staging ===")
    from rpg2gba.conversion_agent import fork_index as fi
    from rpg2gba.tileset_converter import wild_encounters as we

    species_manifest_path = out / "species" / "species_manifest.json"
    if not species_manifest_path.is_file():
        raise FileNotFoundError(
            f"{species_manifest_path} missing -- run the species pass (S8b2) "
            "first; the known-species union for encounter validation needs "
            "its manifest"
        )
    manifest = json.loads(species_manifest_path.read_text(encoding="utf-8"))
    known_species: set[str] = {entry["species_constant"] for entry in manifest["species"]}

    gate_index = fi.load_or_build()
    known_species |= {c for c in gate_index.constants if c.startswith("SPECIES_")}

    encounters_path = out / "intermediate" / "wild_encounters.json"
    map_consts = {mid: consts[str(mid)]["map_const"] for mid in SLICE_MAP_IDS}
    fork_encounters_path = fork / "src" / "data" / "wild_encounters.json"
    gen_encounters_path = we.overlay_path(fork_encounters_path)

    entries = we.build_encounter_entries(
        encounters_path,
        SLICE_MAP_IDS,
        map_consts,
        known_species,
        fork_encounters_path=fork_encounters_path,
    )
    staged_ids = {e.uranium_map_id for e in entries}
    skipped = [mid for mid in SLICE_MAP_IDS if mid not in staged_ids]

    if not dry_run:
        written = we.upsert_encounters(fork_encounters_path, entries, out_path=gen_encounters_path)
        logger.info(
            "  wrote %s (+%d slice encounter entries)", gen_encounters_path.name, written
        )
    else:
        logger.info(
            "  [dry] would write %s (+%d slice encounter entries)",
            gen_encounters_path.name, len(entries),
        )
    if skipped:
        logger.info("  no encounter table for map id(s): %s", skipped)


# ---------------------------------------------------------------------------
# S8b5: PokePod rematch table staging
# ---------------------------------------------------------------------------

def run_rematch_pass(out: Path, fork: Path, consts: dict, dry_run: bool) -> None:
    """Stage the `gRematchTable` data behind Uranium's PokePod phone rematches.

    Detects phone-rematch events structurally (`pbPhoneRegisterBattle` in a map
    event's script) across `SLICE_MAP_IDS`, resolves each to its staged
    `TRAINER_*` constant, and emits the two C fragments the engine needs: the
    `REMATCH_*` enum members and the `gRematchTable` rows
    (`rpg2gba.trainer_converter.rematch`). Fork facts (enum members,
    `MAX_REMATCH_ENTRIES`, `TRAINER_REGISTERED_FLAGS_START` headroom) are read
    from `fork` at run time, never pinned (CLAUDE.md §4.7).

    Unlike S8b4's wild encounters there is no Makefile-wildcard injection path:
    `gRematchTable` (`src/battle_setup.c`) and the `REMATCH_*` enum
    (`include/constants/rematches.h`) are hand-written C in committed vendored
    source, with no generator tool and no data file for a `$(or $(wildcard …))`
    hook to swap. So the fragments are installed the other sanctioned way — the
    `constants/event_objects.h` -> `uranium_event_objects.gen.h` precedent: two
    committed `URANIUM PATHFINDER SLICE` `#include` hooks pull in gitignored
    generated headers, which this pass writes into `out/trainers/rematch/` and
    then copies into the fork. Both are always written (comment-only stubs when
    no phone-rematch trainers are staged), so a build never sees a missing
    include.

    The enum fragment MUST land above `REMATCH_WALLY_VR` — `IsRematchForbidden`
    rejects every id >= `REMATCH_ELITE_FOUR_ENTRIES`. That ordering lives in the
    committed hook's position, not here.

    Must run AFTER S8b3 (`run_trainer_pass`): it gates every rematch row
    against `out/trainers/trainer_manifest.json`'s staged battle trainers, so
    a row can never name a `TRAINER_*` the fork won't define.

    `consts` is the already-loaded `map_constants.json` dict — the map-id ->
    `MAP_*` mapping is read straight from it, never re-minted (CLAUDE.md §4.3).
    """
    logger.info("=== S8b5: rematch table staging ===")
    from rpg2gba.trainer_converter import battles as tb
    from rpg2gba.trainer_converter import rematch as rm

    trainer_manifest_path = out / "trainers" / "trainer_manifest.json"
    if not trainer_manifest_path.is_file():
        raise FileNotFoundError(
            f"{trainer_manifest_path} missing -- run the trainer pass (S8b3) first; the "
            "rematch rows are gated against its staged battle trainers"
        )
    staged_keys = rm.load_staged_battle_trainer_keys(trainer_manifest_path)
    trainers = tb.load_trainers_json(out / "intermediate")

    facts = rm.load_fork_facts(fork)
    events = rm.detect_over_maps(out / "maps", SLICE_MAP_IDS)
    map_consts = {mid: consts[str(mid)]["map_const"] for mid in SLICE_MAP_IDS}
    entries = rm.build_rematch_entries(events, trainers, map_consts, staged_keys, facts)

    logger.info(
        "  %d phone-rematch trainer(s); fork capacity %d (saveblock %d, registered-flag %d)",
        len(entries), facts.capacity, facts.saveblock_headroom, facts.registered_flag_headroom,
    )
    for e in entries:
        logger.info(
            "    map %d EV%03d %s -> %s @ %s",
            e.uranium_map_id, e.event_id, e.trainer_key, e.rematch_const, e.map_const,
        )

    dest = out / "trainers" / "rematch"
    _write(dest / "uranium_rematches.gen.h", rm.emit_rematch_enum(entries),
           "rematch enum members", dry_run)
    _write(dest / "uranium_rematch_table.gen.h", rm.emit_rematch_table(entries),
           "gRematchTable rows", dry_run)
    _write(
        dest / "rematch_manifest.json",
        json.dumps(
            {
                "version": 1,
                "generator": rm.GENERATOR,
                "insert_before": rm.INSERT_BEFORE_MEMBER,
                "rematches": rm.build_rematch_manifest_records(entries),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        "rematch manifest",
        dry_run,
    )
    _copy(
        dest / "uranium_rematches.gen.h",
        fork / "include" / "constants" / "uranium_rematches.gen.h",
        "rematch enum members", dry_run,
    )
    _copy(
        dest / "uranium_rematch_table.gen.h",
        fork / "src" / "data" / "uranium_rematch_table.gen.h",
        "gRematchTable rows", dry_run,
    )


# ---------------------------------------------------------------------------
# S8b6: Heal-location overlay
# ---------------------------------------------------------------------------

def run_heal_location_pass(out: Path, fork: Path, consts: dict, dry_run: bool) -> None:
    """Append the slice's white-out respawn points to an overlay of the fork's
    `src/data/heal_locations.json`.

    Entries come from `rpg2gba.pbs_converter.heal_locations.generate_entries`
    (the start-anchor `HEAL_LOCATION_URANIUM_START` first, then Pokémon Center
    entries derived from `pbSetPokemonCenter` call sites, sorted by id) — never
    reimplemented or hand-listed here (CLAUDE.md §4.3).

    Writes `fork/src/data/heal_locations.gen.json` (gitignored): the committed
    upstream file's own `heal_locations` array with the slice's entries
    appended, in the returned order. `engine/json_data_rules.mk`'s
    `URANIUM_HEAL_LOCATIONS` var (near the top of the file) prefers this
    overlay when present, falling back to the committed file when absent — a
    repo with no overlay on disk builds pristine upstream behavior. The
    committed file is always re-read fresh as the base (never a prior
    overlay), mirroring `run_encounters_pass`'s `upsert_encounters` pattern, so
    N runs with the same corpus produce byte-identical output (CLAUDE.md
    §4.2) and entries never accumulate.

    Two fail-loud checks beyond what `generate_entries` itself does:
      - an id already present in the committed upstream file (never shadow a
        vanilla heal location);
      - a `map` value that is not one of `SLICE_MAP_IDS`' own `MAP_*`
        constants (read from `consts`, the already-loaded `map_constants.json`
        dict — never re-minted, CLAUDE.md §4.3) — `generate_entries` fails
        loud on a *source call site's* map missing from the staged set, but a
        resolved respawn can legally point at a DIFFERENT map (explicit
        `pbSetPokemonCenter` args, or the anchor itself), so that destination
        map needs its own check here or a heal location could reference a map
        this build never assembles.

    Also writes `out/heal_locations.json` via `heal_locations.write_entries`,
    a plain review copy of just the slice's own entries (not the merged
    overlay) — CLAUDE.md §4.4.
    """
    logger.info("=== S8b6: heal location overlay ===")
    from rpg2gba.pbs_converter import heal_locations as hl

    fork_heal_locations_path = fork / "src" / "data" / "heal_locations.json"
    if not fork_heal_locations_path.is_file():
        raise FileNotFoundError(
            f"{fork_heal_locations_path} missing -- vendored engine incomplete"
        )

    upstream_text = fork_heal_locations_path.read_text(encoding="utf-8")
    had_trailing_newline = upstream_text.endswith("\n")
    upstream = json.loads(upstream_text)
    upstream_list = upstream.get("heal_locations", [])
    upstream_ids = {e["id"] for e in upstream_list}

    entries, _resolutions = hl.generate_entries(
        maps_dir=out / "maps",
        tilesets_json=out / "tilesets.json",
        map_constants_json=out / "porymap" / "map_constants.json",
        staged_map_ids=frozenset(SLICE_MAP_IDS),
        metadata_header=out / "include" / "constants" / "metadata.h",
    )

    valid_maps = {consts[str(mid)]["map_const"] for mid in SLICE_MAP_IDS}
    for entry in entries:
        if entry.id in upstream_ids:
            raise ValueError(
                f"heal location id {entry.id!r} already exists in the committed "
                f"{fork_heal_locations_path} -- refusing to shadow an upstream entry"
            )
        if entry.map not in valid_maps:
            raise ValueError(
                f"heal location {entry.id!r} respawns onto {entry.map!r}, which "
                "is not one of the maps this slice builds (SLICE_MAP_IDS) -- the "
                "ROM would reference a map this build never assembles"
            )

    merged = dict(upstream)
    merged["heal_locations"] = list(upstream_list) + [
        {"id": e.id, "map": e.map, "x": e.x, "y": e.y} for e in entries
    ]
    gen_text = json.dumps(merged, indent=2, ensure_ascii=False)
    if had_trailing_newline:
        gen_text += "\n"

    gen_path = fork_heal_locations_path.with_name(
        fork_heal_locations_path.stem + ".gen" + fork_heal_locations_path.suffix
    )
    review_path = out / "heal_locations.json"

    if not dry_run:
        gen_path.parent.mkdir(parents=True, exist_ok=True)
        gen_path.write_text(gen_text, encoding="utf-8")
        hl.write_entries(entries, out_path=review_path)
        logger.info("  wrote %s (+%d heal location(s))", gen_path.name, len(entries))
    else:
        logger.info(
            "  [dry] would write %s (+%d heal location(s))", gen_path.name, len(entries)
        )


# ---------------------------------------------------------------------------
# S8c: Fork assembly
# ---------------------------------------------------------------------------

def _resolve_batch_layout_entries(
    consts: dict,
    map_ids: list[int],
    batch_layouts: list[dict] | None,
    staging_layouts_json: Path,
) -> list[dict]:
    """The layout entries to append to the fork's layouts overlay for THIS run.

    `batch_layouts` (from `run_layout_pass`) is the normal path: use it directly.
    When it's None (S8b was skipped via --skip-layout), fall back to the
    cumulative `staging/layouts/layouts.json` — but filtered down to exactly
    `map_ids`, never used wholesale. With per-map synthetic tileset ids
    (`map_set.synth_tileset_id`), the un-filtered cumulative file is a link-time
    bomb: any prior run with a different SLICE_MAP_IDS leaves layout entries
    referencing gTileset_Uranium<synth> symbols this run never emits, producing
    undefined-symbol errors at link. Fails loud if a needed entry is missing.
    """
    if batch_layouts is not None:
        return batch_layouts

    if not staging_layouts_json.is_file():
        raise FileNotFoundError(
            f"S8b layout output missing: {staging_layouts_json}\n"
            "Run assemble_pathfinder.py without --skip-layout first."
        )
    cumulative = json.loads(staging_layouts_json.read_text(encoding="utf-8")).get("layouts", [])
    by_layout_const = {e["id"]: e for e in cumulative}
    expected_ids = [consts[str(mid)]["layout_const"] for mid in map_ids]
    missing = [lid for lid in expected_ids if lid not in by_layout_const]
    if missing:
        raise KeyError(
            f"layout entries missing from {staging_layouts_json} for the current "
            f"map set: {sorted(missing)}\n"
            "Run assemble_pathfinder.py without --skip-layout first."
        )
    return [by_layout_const[lid] for lid in expected_ids]


def run_fork_pass(
    out: Path,
    fork: Path,
    consts: dict,
    staging: Path,
    dry_run: bool,
    batch_layouts: list[dict] | None = None,
) -> None:
    """`batch_layouts` is THIS batch's layout entries, normally threaded straight
    from `run_layout_pass`'s return value. When None (S8b was skipped via
    --skip-layout, so this run never produced its own batch), the cumulative
    `staging/layouts/layouts.json` is filtered down to just the current
    SLICE_MAP_IDS' entries — never used wholesale. Per-map synthetic tileset ids
    (map_set.synth_tileset_id) make the un-filtered cumulative file a link-time
    bomb: any prior run with a different map set leaves layout entries
    referencing gTileset_Uranium<synth> symbols this run never emits, producing
    undefined-symbol errors at link (mirrors phase5.py's `_assemble_fork`
    comment on `batch_layouts`)."""
    logger.info("=== S8c: fork assembly ===")

    from rpg2gba.conversion_agent import fork_index as fi
    from rpg2gba.tileset_converter import assembly as asm

    # Staging-time forward gate (grill D4): every script staged into engine/
    # is checked against the fork's real symbol surface (index) plus the
    # Uranium-minted registries (D3). A violation is OUR bug — abort loud
    # before make, never stage, never queue.
    gate_index = fi.load_or_build()
    species_manifest_path = out / "species" / "species_manifest.json"
    # The sprite pass's OBJ_EVENT_GFX_URANIUM_* constants land in generated,
    # gitignored `uranium_*.gen.h` headers, so the index can never carry them;
    # they come from the same §4.3 SoT the transpiler resolves sheets through.
    npc_gfx_map_path = Path("reference/npc_gfx_map.json")
    trainer_manifest_path = out / "trainers" / "trainer_manifest.json"
    gate_extras = fi.registry_extra_symbols(
        flag_state_path=out / "flag_state.json",
        map_constants_path=out / "porymap" / "map_constants.json",
        species_manifest_path=species_manifest_path if species_manifest_path.is_file() else None,
        npc_gfx_map_path=npc_gfx_map_path if npc_gfx_map_path.is_file() else None,
        trainer_manifest_path=trainer_manifest_path if trainer_manifest_path.is_file() else None,
    )
    # HEAL_LOCATION_* constants are generated from heal_locations(.gen).json
    # into an untracked header, so the index never carries them. Read the
    # same file the build's URANIUM_HEAL_LOCATIONS hook selects (overlay if
    # S8b6 wrote one, else upstream) — a setrespawn target absent from it
    # would fail at make, so it must fail here first.
    heal_json = fork / "src" / "data" / "heal_locations.gen.json"
    if not heal_json.is_file():
        heal_json = fork / "src" / "data" / "heal_locations.json"
    gate_extras |= {
        e["id"] for e in json.loads(heal_json.read_text(encoding="utf-8"))["heal_locations"]
    }
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

    # Staging-time text gate (ROM_TEST_DEV C3): the same four static rules the
    # corpus scanner runs, applied per staged script so a defect that would
    # render as literal `<b>` characters (or overflow the message box) in the
    # ROM aborts here instead of surfacing in a boot walk. Sits alongside the
    # fork-index gate above — same contract: our bug, nothing staged.
    from rpg2gba.text_validator import TextGate

    text_gate = TextGate(fork)
    def _gate_text(pory_text: str, label: str) -> None:
        text_gate.check(pory_text, label)

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
        # header table). Maps with a mapscripts block (metadata_wiring
        # .render_map_scripts -- ON_TRANSITION / ON_FRAME_TABLE, appended above
        # via the dispatcher file) bring their own; the rest get an empty one.
        mapscripts_label = f"{map_dir_name}_MapScripts"
        if mapscripts_label not in pory_text:
            pory_text = f"mapscripts {mapscripts_label} {{}}\n\n" + pory_text

        compiled_texts.append(pory_text)
        _gate(pory_text, f"Map{map_id:03d}")
        _gate_text(pory_text, f"Map{map_id:03d}")
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
        _gate_text(ce_text, "CommonEvents")
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

    entries = _resolve_batch_layout_entries(
        consts, SLICE_MAP_IDS, batch_layouts, staging_layouts_json,
    )

    from rpg2gba.tileset_converter.layout import append_layouts
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
# S8d: Berry tree seed table
# ---------------------------------------------------------------------------

def run_berry_tree_pass(out: Path, fork: Path, dry_run: bool) -> None:
    """Emit data/scripts/uranium_berry_trees.h: the pre-planted berry-tree
    seed table consumed by new_game.c's NewGameInitData, right after
    `ClearBerryTrees()` (BEGIN URANIUM PATHFINDER SLICE fence).

    Reads the same `Map{id:03d}.template_fields.json` sidecars
    `stage_slice_scripts._load_template_fields` already validates (`kind ==
    "berry_tree"` entries carry `berry_item`/`planted`/`yield`; each emitted
    row is `X(treeId, ITEM_*_BERRY, yield)` — the source `pbPickBerry` count,
    applied by new_game.c after `PlantBerryTree`) for every
    `SLICE_MAP_IDS` map, and calls the EXISTING
    `metadata_wiring.assign_berry_tree_ids` to get the SAME save-slot ids the
    object-event `trainer_sight_or_berry_tree_id` field already carries —
    never reimplemented, never hardcoded (CLAUDE.md §4.3).

    Only `planted: true` rows are emitted; bare-soil `planted: false` patches
    boot empty, which is correct (nothing to seed). `planted: true` with a
    null `berry_item` is a contradictory sidecar and fails loud. Every
    emitted `ITEM_*_BERRY` constant is checked against the fork's own symbol
    index (`fork_index.load_or_build`) before being written — §4.7 forward
    gate; `reference/uranium_id_map.json` is known to assert `ITEM_*_BERRY`
    constants the fork does not define, so a constant reaching this pass is
    not proof it is real.

    Deterministic: rows sorted by tree id (§4.2)."""
    logger.info("=== S8d: berry tree seed table ===")
    from rpg2gba.conversion_agent import fork_index as fi
    from rpg2gba.tileset_converter.metadata_wiring import assign_berry_tree_ids

    template_fields: dict[int, dict[int, dict]] = {}
    for map_id in SLICE_MAP_IDS:
        fields_path = out / "scripts" / f"Map{map_id:03d}.template_fields.json"
        if not fields_path.is_file():
            raise FileNotFoundError(
                f"{fields_path} missing — re-run the transpile driver to "
                "regenerate the template-fields sidecar"
            )
        sidecar = json.loads(fields_path.read_text(encoding="utf-8"))
        template_fields[map_id] = {
            int(eid): payload for eid, payload in sidecar["events"].items()
        }

    tree_ids = assign_berry_tree_ids(template_fields)  # {(map_id, event_id): tree_id}

    gate_index = fi.load_or_build()

    rows: list[tuple[int, str]] = []
    for (map_id, event_id), tree_id in tree_ids.items():
        payload = template_fields[map_id][event_id]
        if not payload.get("planted", False):
            continue  # bare soil — nothing to seed
        berry_item = payload.get("berry_item")
        if berry_item is None:
            raise ValueError(
                f"Map{map_id:03d} event {event_id} (berry tree id {tree_id}): "
                "planted=true but berry_item is null — contradictory sidecar"
            )
        if berry_item not in gate_index.constants:
            raise ValueError(
                f"Map{map_id:03d} event {event_id} (berry tree id {tree_id}): "
                f"{berry_item} not found in the fork's constants index "
                "(engine/include/constants) — reference/uranium_id_map.json "
                "is known to assert ITEM_*_BERRY constants the fork does not "
                "define; this is a converter/reference-data bug, not "
                "something to default around"
            )
        berry_yield = payload.get("yield")
        if (
            not isinstance(berry_yield, int)
            or isinstance(berry_yield, bool)
            or not 1 <= berry_yield <= 31  # struct BerryTree.berryYield is 5 bits
        ):
            raise ValueError(
                f"Map{map_id:03d} event {event_id} (berry tree id {tree_id}): "
                f"planted=true but yield is {berry_yield!r} — expected an int "
                "in 1..31 (re-run the transpile driver)"
            )
        rows.append((tree_id, berry_item, berry_yield))

    rows.sort(key=lambda r: r[0])

    lines = [
        "// GENERATED by rpg2gba assembler (assemble_pathfinder.py run_berry_tree_pass)",
        "// from Map{id:03d}.template_fields.json via metadata_wiring.assign_berry_tree_ids.",
        "// Row fields: treeId, ITEM_*_BERRY, firstPickYield; yield = source pbPickBerry count.",
        "// DO NOT EDIT, DO NOT COMMIT.",
        f"#define URANIUM_BERRY_TREE_SEED_COUNT {len(rows)}",
    ]
    if rows:
        lines.append("#define URANIUM_BERRY_TREE_SEED_LIST(X) \\")
        for i, (tree_id, berry_item, berry_yield) in enumerate(rows):
            suffix = " \\" if i < len(rows) - 1 else ""
            lines.append(f"    X({tree_id}, {berry_item}, {berry_yield}){suffix}")
    else:
        lines.append("#define URANIUM_BERRY_TREE_SEED_LIST(X)")
    lines.append("")

    dest = fork / "data" / "scripts" / "uranium_berry_trees.h"
    text = "\n".join(lines)
    _write(dest, text, "uranium_berry_trees.h", dry_run)
    logger.info("  %d pre-planted berry tree(s)", len(rows))


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
    ap.add_argument("--skip-species", action="store_true",
                    help="Skip S8b2 (Uranium starter species already staged).")
    ap.add_argument("--skip-trainers", action="store_true",
                    help="Skip S8b3 (Uranium trainer pics already staged).")
    ap.add_argument("--skip-encounters", action="store_true",
                    help="Skip S8b4 (wild encounter tables already staged).")
    ap.add_argument("--skip-rematches", action="store_true",
                    help="Skip S8b5 (PokePod rematch table already staged).")
    ap.add_argument("--skip-heal-locations", action="store_true",
                    help="Skip S8b6 (heal-location overlay already staged).")
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

    batch_layouts: list[dict] | None = None
    if not args.skip_layout:
        batch_layouts = run_layout_pass(out, consts, staging, args.dry_run)

    if not args.skip_species or not args.skip_trainers:
        uranium_src_path = os.environ.get("RPG2GBA_URANIUM_SRC")
        if not uranium_src_path:
            print("RPG2GBA_URANIUM_SRC not set", file=sys.stderr)
            return 1
        uranium_src = Path(uranium_src_path)
        if not uranium_src.is_dir():
            print(f"Uranium source tree not found: {uranium_src}", file=sys.stderr)
            return 1

        if not args.skip_species:
            run_species_pass(out, fork, uranium_src, args.dry_run)

        if not args.skip_trainers:
            run_trainer_pass(out, fork, uranium_src, args.dry_run)

    if not args.skip_encounters:
        run_encounters_pass(out, fork, consts, args.dry_run)

    if not args.skip_rematches:
        run_rematch_pass(out, fork, consts, args.dry_run)

    if not args.skip_heal_locations:
        run_heal_location_pass(out, fork, consts, args.dry_run)

    run_fork_pass(out, fork, consts, staging, args.dry_run, batch_layouts=batch_layouts)
    run_berry_tree_pass(out, fork, args.dry_run)

    if args.dry_run:
        logger.info("=== dry-run complete, no files written ===")
    else:
        logger.info("=== assembly complete — ready for: make -C %s -j$(nproc) modern ===", fork)
    return 0


if __name__ == "__main__":
    sys.exit(main())
