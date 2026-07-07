"""Graphics pre-pass (S8a) — build real Uranium tilesets for a slice.

Ties the image pipeline (sources -> raster -> quantize -> emit) to the assembler:
for each Uranium tileset used by the slice maps it enumerates the *column keys*
(the full z-stack of non-empty tile ids per cell) across all maps, renders each
column to a two-layer MetatileImage via `_render_column` (tiles with RMXP priority>0
go to the GBA top BG layer; the rest composite into the bottom layer), emits a
dedicated pokeemerald PRIMARY+SECONDARY pair via `emit.emit_tileset`, and writes:

  - the GBA art under ``<fork>/data/tilesets/{primary,secondary}/uranium<ts>/``,
  - four generated, gitignored engine fragments pulled in by the committed
    sentinel ``#include`` hooks (``uranium_graphics.gen.h`` / ``uranium_metatiles.gen.h``
    / ``uranium_tilesets.gen.h`` in ``src/data/tilesets/`` and ``uranium_externs.gen.h``
    in ``include/``), and
  - a ``reference/tileset_map.gen.json`` overlay that `tile_map.load_tile_map`
    prefers over the committed Hoenn-bucket table (so the layout pass resolves each
    Uranium column key to its real metatile via ``lookup_column``).

Each unique column key becomes ONE metatile (bottom + top layer split by RMXP
priority). Autotile variants are kept distinct (faithful edges). One synthetic
all-transparent metatile (void) is appended as the border/empty-column metatile.

Warp cells get a per-column MB_NON_ANIMATED_DOOR copy (fix #1,
walker_checkpoint2_findings.md): for EVERY distinct door column key used by a
warp coord in this tileset, a SEPARATE metatile is appended carrying that
column's real art + the door behavior, so non-warp cells sharing the same
column key keep ``MB_NORMAL`` on their own (unmodified) metatile. One extra
all-transparent door metatile is appended as the fallback, for warp coords
whose column is empty or out-of-atlas. The layout converter looks up the
right one per cell via ``tile_map.warp_for_column(tileset_id, key)``.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.layout import TileGrid, column_key
from rpg2gba.tileset_converter.terrain_tags import (
    TerrainTagTable,
    load_terrain_tag_map,
    load_terrain_tags_json,
)
from rpg2gba.tileset_converter.tile_map import serialize_column_key

from .emit import (
    LAYER_COVERED,
    LAYER_NORMAL,
    EmittedTileset,
    MetatileImage,
    emit_tileset,
)
from .quantize import build_quantized_tileset_family
from .raster import TileRasterizer
from .sources import STATIC_BASE, load_tileset_sources

logger = logging.getLogger(__name__)

EMPTY_TILE = 0  # RMXP empty marker; column_key skips these automatically

DEFAULT_BASE_TILE_MAP = Path("reference/tileset_map.json")
DEFAULT_OVERLAY_OUT = Path("reference/tileset_map.gen.json")
DEFAULT_TILESETS_JSON = Path("output/uranium-build/tilesets.json")


def _behavior_value(fork: Path, name: str) -> int:
    """Resolve a ``MB_*`` metatile-behavior to its numeric enum value from the fork.

    Parses the first ``enum { ... }`` in ``include/constants/metatile_behaviors.h``
    (sequential from 0, honouring any explicit ``= N``). Verifying against the fork
    rather than hard-coding a magic number (CLAUDE.md §4.7)."""
    path = fork / "include" / "constants" / "metatile_behaviors.h"
    val = 0
    in_enum = False
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.split("//")[0].strip()
        if not in_enum:
            if s.startswith("enum") and "{" in s:
                in_enum = True
            continue
        if "}" in s:
            break
        s = s.rstrip(",").strip()
        if not s:
            continue
        if "=" in s:
            ident, _, num = s.partition("=")
            ident, val = ident.strip(), int(num.strip(), 0)
        else:
            ident = s
        if ident == name:
            return val
        val += 1
    raise KeyError(f"{name} not found in {path}")


def _grid_of(map_json: dict) -> TileGrid:
    t = map_json["tiles"]
    return TileGrid(t["xsize"], t["ysize"], t["zsize"], t["data"])


def _default_rasterizer(
    tileset_id: int, tilesets_json: Path, graphics_dir: Path | None
) -> TileRasterizer:
    sources = load_tileset_sources(
        tileset_id, tilesets_json=tilesets_json, graphics_dir=graphics_dir
    )
    return TileRasterizer(sources)


def _load_priorities(tilesets_json: Path, ts: int) -> list[int]:
    """Load the priorities array for tileset ``ts`` from the Phase-3 tilesets oracle."""
    raw = json.loads(Path(tilesets_json).read_text(encoding="utf-8"))
    entry = raw.get(str(ts))
    if entry is None:
        raise KeyError(f"tileset {ts} absent from {tilesets_json}")
    return entry["priorities"]


def _load_terrain_tags(tilesets_json: Path, ts: int) -> list[int]:
    """Load the terrain_tags array for tileset ``ts`` from the Phase-3 tilesets oracle."""
    return load_terrain_tags_json(tilesets_json, ts)


def _render_column(
    key: tuple[tuple[int, int], ...],
    rasterizer: object,
    priorities: list[int],
    *,
    behavior: int = 0,
) -> MetatileImage:
    """Priority split: tiles with RMXP priority>0 (drawn over the player) go to the TOP
    layer; the rest composite into the BOTTOM layer. z-ascending = bottom-first."""
    bottom = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    top = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    has_overlay = False
    for z, tid in key:
        img = rasterizer.render(tid)
        pr = priorities[tid] if 0 <= tid < len(priorities) else 0
        if pr > 0:
            top.alpha_composite(img)
            has_overlay = True
        else:
            bottom.alpha_composite(img)
    layer_type = LAYER_NORMAL if has_overlay else LAYER_COVERED
    return MetatileImage(
        np.asarray(bottom, dtype=np.uint8),
        np.asarray(top, dtype=np.uint8),
        layer_type,
        behavior,
    )


def _void_metatile() -> MetatileImage:
    """All-transparent metatile: the void/border placeholder.

    ``buckets.void`` points here; ``collapse_column`` returns this for empty
    columns. Being all-transparent makes mis-rendered void cells visually obvious."""
    z = np.zeros((16, 16, 4), dtype=np.uint8)
    return MetatileImage(z, z.copy(), LAYER_COVERED, 0)


def column_keys_for_maps(
    maplist: list[tuple[int, dict]],
) -> list[tuple[tuple[int, int], ...]]:
    """Return sorted unique non-empty column keys across all maps in ``maplist``.

    ``maplist`` is ``[(map_id, map_json), ...]``.  The stable sort gives
    deterministic metatile-id assignment across re-runs.  Empty column keys
    (cells that contain no tiles) are excluded."""
    keys: set[tuple[tuple[int, int], ...]] = set()
    for _map_id, map_json in maplist:
        grid = _grid_of(map_json)
        for y in range(grid.ysize):
            for x in range(grid.xsize):
                k = column_key(grid, x, y)
                if k:
                    keys.add(k)
    return sorted(keys)


def build_slice_tilesets(
    maps: list[tuple[int, dict]],
    warp_coords: dict[int, set[tuple[int, int]]],
    *,
    fork: Path,
    base_tile_map: Path = DEFAULT_BASE_TILE_MAP,
    overlay_out: Path = DEFAULT_OVERLAY_OUT,
    tilesets_json: Path = DEFAULT_TILESETS_JSON,
    graphics_dir: Path | None = None,
    rasterizer_for: Callable[[int], object] | None = None,
    priorities_for: Callable[[int], list[int]] | None = None,
    terrain_tags_for: Callable[[int], list[int]] | None = None,
    terrain_tag_table: TerrainTagTable | None = None,
    source_tileset_of: Callable[[int], int] | None = None,
    dry_run: bool = False,
) -> dict[int, EmittedTileset]:
    """Emit real Uranium tilesets for the slice and write the engine + overlay glue.

    `maps` is ``[(map_id, map_json), ...]`` (each map_json has ``tileset_id`` and the
    Phase-3 ``tiles`` grid). `warp_coords` maps map_id -> warp source coords (the
    layout converter stamps the tileset's warp metatile there). `rasterizer_for`
    overrides tile rendering for tests; defaults to the real Uranium source pipeline.
    `priorities_for` overrides priority loading for tests; defaults to reading
    tilesets.json. `terrain_tags_for` overrides terrain-tag loading for tests;
    defaults to reading tilesets.json (same synthetic-id resolution as priorities).
    `terrain_tag_table` overrides the loaded terrain_tag_map.json table for tests;
    defaults to `load_terrain_tag_map(fork)`. `source_tileset_of` maps a synthetic
    per-map tileset id back to its real RMXP tileset id, so per-map physical
    tilesets still load the correct source art / passages. Identity when None (the
    default — legacy per-RMXP-tileset behavior).
    Returns the per-tileset `EmittedTileset`. Writes nothing when `dry_run`."""
    fork = Path(fork)
    resolve = source_tileset_of or (lambda ts: ts)
    make_rast = rasterizer_for or (
        lambda ts: _default_rasterizer(resolve(ts), tilesets_json, graphics_dir)
    )
    get_priorities = priorities_for or (lambda ts: _load_priorities(tilesets_json, resolve(ts)))
    get_terrain_tags = terrain_tags_for or (
        lambda ts: _load_terrain_tags(tilesets_json, resolve(ts))
    )
    terrain_table = terrain_tag_table or load_terrain_tag_map(fork)

    by_ts: dict[int, list[tuple[int, dict]]] = {}
    for map_id, map_json in maps:
        by_ts.setdefault(int(map_json["tileset_id"]), []).append((map_id, map_json))

    overlay = json.loads(Path(base_tile_map).read_text(encoding="utf-8"))
    for key in ("tilesets", "tiles", "buckets", "warps", "atlas_max"):
        overlay.setdefault(key, {})

    door_behavior = _behavior_value(fork, "MB_NON_ANIMATED_DOOR")
    results: dict[int, EmittedTileset] = {}

    for ts, maplist in sorted(by_ts.items()):
        rast = make_rast(ts)
        priorities = get_priorities(ts)
        terrain_tags = get_terrain_tags(ts)

        # Enumerate all unique column keys across all maps for this tileset.
        ordered = column_keys_for_maps(maplist)

        # Drop column keys that reference out-of-atlas (garbage) static tile ids:
        # some Uranium maps carry stray tile ids far outside their tileset atlas
        # (e.g. 3408 in a 304-tile Gatehouse), which the rasterizer fails loud on.
        # Autotile ids (< STATIC_BASE) are always valid; static ids must be in range.
        # Dropped columns resolve to the void metatile in convert_layout, matching
        # the map viewer's pre-render filter (map_viewer_common._ensure_tileset_analysis).
        # A synthetic test rasterizer has no atlas bounds -> nothing to drop.
        max_tid = rast.max_static_tile_id() if hasattr(rast, "max_static_tile_id") else None

        def _in_atlas(k: tuple) -> bool:
            if max_tid is None:
                return True
            return all(tid < STATIC_BASE or tid <= max_tid for _, tid in k)

        garbage = len(ordered) - len([k for k in ordered if _in_atlas(k)])
        if garbage:
            logger.warning(
                "tileset %d: dropped %d column key(s) with out-of-atlas tile ids "
                "(max static id %d) -> void", ts, garbage, max_tid,
            )
            ordered = [k for k in ordered if _in_atlas(k)]

        if not ordered:
            raise ValueError(
                f"tileset {ts}: no non-empty columns across maps "
                f"{[m for m, _ in maplist]} — wrong grid order or empty maps?"
            )

        # Collect door (warp) column keys separately — need the MB_NON_ANIMATED_DOOR copy.
        door_keys: set[tuple] = set()
        for map_id, map_json in maplist:
            grid = _grid_of(map_json)
            for wx, wy in warp_coords.get(map_id, set()):
                dk = column_key(grid, wx, wy)
                if dk and _in_atlas(dk):
                    door_keys.add(dk)

        primary_name = f"gTileset_Uranium{ts}"
        secondary_name = f"gTileset_Uranium{ts}B"
        primary_dir = fork / "data" / "tilesets" / "primary" / f"uranium{ts}"
        secondary_dir = fork / "data" / "tilesets" / "secondary" / f"uranium{ts}"

        if dry_run:
            logger.info(
                "[dry] S8a tileset %d: %d columns, %d door column(s) -> "
                "would emit %s + %s",
                ts, len(ordered), len(door_keys), primary_name, secondary_name,
            )
            continue

        # Build metatile list: one per column key + void + optional warp copy.
        # Terrain-tag behavior (MB_TALL_GRASS, MB_ICE, ...) is per-column; the door
        # copies below override it with MB_NON_ANIMATED_DOOR (door > terrain).
        # A fully-opaque tag-0 tile stops the tag fall-through (RMXP water
        # flood-fill under land must not leak MB_POND_WATER up — see
        # terrain_tags.effective_tag).
        opaque_cache: dict[int, bool] = {}

        def _is_opaque(tile_id: int, _rast=rast, _cache=opaque_cache) -> bool:
            hit = _cache.get(tile_id)
            if hit is None:
                alpha = np.asarray(_rast.render(tile_id).convert("RGBA"))[..., 3]
                hit = bool((alpha == 255).all())
                _cache[tile_id] = hit
            return hit

        metatile_list = [
            _render_column(
                k, rast, priorities,
                behavior=terrain_table.column_behavior(
                    ts, k, terrain_tags, is_opaque=_is_opaque
                ),
            )
            for k in ordered
        ]

        # The void metatile is all-transparent; buckets.void points here.
        # collapse_column returns this for empty-column cells.
        void_idx = len(metatile_list)
        metatile_list.append(_void_metatile())

        needs_warp = any(warp_coords.get(mid) for mid, _ in maplist)
        warp_tiles: dict[str, int] = {}
        warp_fallback_idx: int | None = None
        if needs_warp:
            # One MB_NON_ANIMATED_DOOR copy PER DISTINCT door column key: non-warp
            # cells that share a column keep MB_NORMAL on the plain overlay["tiles"]
            # entry for that key; only the warp coord's own cell gets the door copy,
            # so each warp keeps its own real art (fix #1).
            for k in sorted(door_keys):
                idx = len(metatile_list)
                metatile_list.append(_render_column(k, rast, priorities, behavior=door_behavior))
                warp_tiles[serialize_column_key(k)] = idx

            # Fallback: warps that sit on an empty/garbage cell (no door column to
            # copy) still need a metatile carrying the door behavior so the
            # warp_event fires — a transparent tile (the walker's R-overlay marks
            # warp tiles anyway, so an invisible warp square is fine for a debug
            # build).
            warp_fallback_idx = len(metatile_list)
            z = np.zeros((16, 16, 4), dtype=np.uint8)
            metatile_list.append(MetatileImage(z, z.copy(), LAYER_COVERED, door_behavior))

        # Family packer is the pipeline standard (per-hue-family palette budget; see
        # quantize.build_quantized_tileset_family) — keeps the ROM render consistent
        # with the map viewer, which previews the same packer.
        emit = emit_tileset(
            metatile_list, primary_dir, secondary_dir, primary_name, secondary_name,
            quantizer=build_quantized_tileset_family,
        )
        results[ts] = emit

        overlay["tilesets"][str(ts)] = {"primary": primary_name, "secondary": secondary_name}
        if source_tileset_of is not None:
            overlay.setdefault("source_tilesets", {})[str(ts)] = source_tileset_of(ts)
        # Record the atlas bound so convert_layout can void columns with the same
        # out-of-atlas garbage tiles this pre-pass dropped (keeps both paths in sync).
        if max_tid is not None:
            overlay["atlas_max"][str(ts)] = max_tid
        # Column-key strings are the shared format (serialize_column_key) that
        # lookup_column expects at layout-conversion time.
        overlay["tiles"][str(ts)] = {
            serialize_column_key(k): {"metatile": i} for i, k in enumerate(ordered)
        }
        # All bucket roles point at void_idx; real cells always hit the explicit
        # tiles table so the bucket is only reached for genuinely empty fallback.
        overlay["buckets"][str(ts)] = {
            "passable": void_idx, "blocked": void_idx, "void": void_idx,
        }
        if needs_warp:
            overlay["warps"][str(ts)] = {
                "tiles": warp_tiles,
                "fallback": warp_fallback_idx,
                "collision": 0,
                "elevation": 0,
            }
        logger.info(
            "S8a tileset %d: %d columns -> %d metatiles, %d GBA tiles, "
            "%d palettes (mean shift %.2f/31)",
            ts, len(ordered), emit.n_metatiles, emit.n_tiles, emit.n_palettes,
            emit.stats.get("mean_shift_5bit", 0.0),
        )

    if not dry_run:
        _write_fragments(fork, results)
        Path(overlay_out).write_text(
            json.dumps(overlay, indent=2) + "\n", encoding="utf-8"
        )
        logger.info("S8a: wrote %s + 4 engine tileset fragments", overlay_out)
    return results


_GEN_HEADER = (
    "// GENERATED by rpg2gba build_slice_tilesets.py — DO NOT EDIT, DO NOT COMMIT.\n"
    "// Pulled in by the URANIUM PATHFINDER SLICE tileset include-hooks.\n\n"
)


def _write_fragments(fork: Path, results: dict[int, EmittedTileset]) -> None:
    """Write the four generated engine fragments registering every emitted tileset."""
    graphics: list[str] = []
    metatiles: list[str] = []
    structs: list[str] = []
    externs: list[str] = []

    for ts in sorted(results):
        prim = f"data/tilesets/primary/uranium{ts}"
        sec = f"data/tilesets/secondary/uranium{ts}"
        for name, ddir, is_secondary in (
            (f"gTileset_Uranium{ts}", prim, "FALSE"),
            (f"gTileset_Uranium{ts}B", sec, "TRUE"),
        ):
            stem = name[len("gTileset_"):]
            graphics.append(
                f'const u32 gTilesetTiles_{stem}[] = '
                f'INCGFX_U32("{ddir}/tiles.png", ".4bpp");'
            )
            pal = [f"const u16 ALIGNED(4) gTilesetPalettes_{stem}[][16] = {{"]
            pal += [
                f'    INCGFX_U16("{ddir}/palettes/{n:02}.pal", ".gbapal"),'
                for n in range(16)
            ]
            pal.append("};")
            graphics.append("\n".join(pal))

            metatiles.append(
                f'const u16 gMetatiles_{stem}[] = '
                f'INCBIN_U16("{ddir}/metatiles.bin");'
            )
            metatiles.append(
                f'const u16 gMetatileAttributes_{stem}[] = '
                f'INCBIN_U16("{ddir}/metatile_attributes.bin");'
            )

            structs.append(
                f"const struct Tileset {name} = {{\n"
                f"    .isCompressed = FALSE,\n"
                f"    .isSecondary = {is_secondary},\n"
                f"    .tiles = gTilesetTiles_{stem},\n"
                f"    .palettes = gTilesetPalettes_{stem},\n"
                f"    .metatiles = gMetatiles_{stem},\n"
                f"    .metatileAttributes = gMetatileAttributes_{stem},\n"
                f"    .callback = NULL,\n"
                f"}};"
            )
            externs.append(f"extern const struct Tileset {name};")

    (fork / "src" / "data" / "tilesets" / "uranium_graphics.gen.h").write_text(
        _GEN_HEADER + "\n".join(graphics) + "\n", encoding="utf-8"
    )
    (fork / "src" / "data" / "tilesets" / "uranium_metatiles.gen.h").write_text(
        _GEN_HEADER + "\n".join(metatiles) + "\n", encoding="utf-8"
    )
    (fork / "src" / "data" / "tilesets" / "uranium_tilesets.gen.h").write_text(
        _GEN_HEADER + "\n".join(structs) + "\n", encoding="utf-8"
    )
    (fork / "include" / "uranium_externs.gen.h").write_text(
        _GEN_HEADER + "\n".join(externs) + "\n", encoding="utf-8"
    )
