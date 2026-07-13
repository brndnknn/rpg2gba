"""Graphics pre-pass (S8a) — build real Uranium tilesets for a slice.

Ties the image pipeline (sources -> raster -> quantize -> emit) to the assembler:
for each Uranium tileset used by the slice maps it enumerates the *column keys*
(the full z-stack of non-empty tile ids per cell) across all maps, renders each
column to a two-layer MetatileImage via `_render_column` (a tiered RMXP-priority
split — p>=2 canopy goes to the GBA top/BG1 layer as LAYER_NORMAL, p==1 overlays
go to the top/BG2 layer as LAYER_COVERED, p==0 always to the bottom layer; see
`_render_column`'s docstring for the row-relative-priority rationale), emits a
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
import math
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


MAX_COLUMN_FRAMES = 64  # fail-loud guard: a column's lcm(per-tile frame counts)
# past this is almost certainly a mismatched/garbage autotile pairing, not a real
# animation (the slice's real cases — 19-frame pond, 4-frame flowers — are tiny).


def column_n_frames(key: tuple[tuple[int, int], ...], rasterizer: object) -> int:
    """lcm of every tile-in-column's animation frame count (1 if the rasterizer
    doesn't expose `frame_count_for_tile` — e.g. the synthetic test stubs, which
    only ever render frame 0). Fails loud past `MAX_COLUMN_FRAMES`."""
    if not hasattr(rasterizer, "frame_count_for_tile"):
        return 1
    n = 1
    for _, tid in key:
        n = math.lcm(n, rasterizer.frame_count_for_tile(tid))
    if n > MAX_COLUMN_FRAMES:
        raise ValueError(
            f"column {key}: frame-count lcm {n} exceeds the {MAX_COLUMN_FRAMES} guard"
        )
    return n


def _render_column(
    key: tuple[tuple[int, int], ...],
    rasterizer: object,
    priorities: list[int],
    *,
    behavior: int = 0,
    n_frames: int = 1,
) -> MetatileImage:
    """Tiered priority split, not a flat p>0 test.

    RMXP priority is row-relative: a p==1 tile draws under a character standing
    one row south of it (head overlap) but over a character standing in its own
    row. GBA's BG1 (the LAYER_NORMAL top slot) draws over sprites unconditionally,
    so a flat p>0 -> BG1 rule wrongly covers the player's head with p==1
    cliff/hedge-lip/tall-grass tiles. Tiered by the highest priority present in
    the column:

      p >= 2 present -> LAYER_NORMAL (BG1); p>=2 tiles -> TOP (always-over
        canopy); p==1 and p==0 tiles -> BOTTOM.
      else p == 1 present -> LAYER_COVERED (BG2 top slot: under sprites, over
        ground); p==1 tiles -> TOP; p==0 tiles -> BOTTOM.
      else -> LAYER_COVERED; everything -> BOTTOM (unchanged, empty TOP).

    z-ascending key order is preserved within each slot.

    ``n_frames`` (normally `column_n_frames(key, rasterizer)`) renders the column
    ``n_frames`` times; frame 0 becomes ``.bottom``/``.top`` as before, frames
    1..n_frames-1 populate ``.frames`` (each tile in the column contributes its
    OWN frame ``f % that tile's own frame count`` — a 19-frame pond tile and a
    static bank tile in the same column both render correctly at every f)."""
    pr = [priorities[tid] if 0 <= tid < len(priorities) else 0 for _, tid in key]
    if any(p >= 2 for p in pr):
        layer_type, top_min = LAYER_NORMAL, 2
    elif any(p == 1 for p in pr):
        layer_type, top_min = LAYER_COVERED, 1
    else:
        layer_type, top_min = LAYER_COVERED, None

    def render_frame(f: int) -> tuple[np.ndarray, np.ndarray]:
        bottom = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        top = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        for (z, tid), p in zip(key, pr):
            if f and hasattr(rasterizer, "frame_count_for_tile"):
                tf = f % rasterizer.frame_count_for_tile(tid)
            else:
                tf = 0
            img = rasterizer.render(tid) if tf == 0 else rasterizer.render(tid, tf)
            if top_min is not None and p >= top_min:
                top.alpha_composite(img)
            else:
                bottom.alpha_composite(img)
        return np.asarray(bottom, dtype=np.uint8), np.asarray(top, dtype=np.uint8)

    bottom0, top0 = render_frame(0)
    frames = [render_frame(f) for f in range(1, n_frames)] if n_frames > 1 else None

    return MetatileImage(bottom0, top0, layer_type, behavior, frames=frames)


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
                n_frames=column_n_frames(k, rast),
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
                metatile_list.append(
                    _render_column(
                        k, rast, priorities, behavior=door_behavior,
                        n_frames=column_n_frames(k, rast),
                    )
                )
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
        logger.info("S8a: wrote %s + 5 engine tileset fragments", overlay_out)
    return results


_GEN_HEADER = (
    "// GENERATED by rpg2gba build_slice_tilesets.py — DO NOT EDIT, DO NOT COMMIT.\n"
    "// Pulled in by the URANIUM PATHFINDER SLICE tileset include-hooks.\n\n"
)


def _write_fragments(fork: Path, results: dict[int, EmittedTileset]) -> None:
    """Write the five generated engine fragments registering every emitted tileset
    (four static-art fragments + `uranium_anims.gen.h` for animated tiles)."""
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

            # Only PRIMARY gets the animation callback — animated tiles are always
            # assigned into the primary tile block (emit.py Step 3); secondary
            # stays NULL. A tileset with no animated effects also stays NULL.
            has_anims = is_secondary == "FALSE" and bool(results[ts].effects)
            callback = f"InitTilesetAnim_Uranium{ts}" if has_anims else "NULL"
            structs.append(
                f"const struct Tileset {name} = {{\n"
                f"    .isCompressed = FALSE,\n"
                f"    .isSecondary = {is_secondary},\n"
                f"    .tiles = gTilesetTiles_{stem},\n"
                f"    .palettes = gTilesetPalettes_{stem},\n"
                f"    .metatiles = gMetatiles_{stem},\n"
                f"    .metatileAttributes = gMetatileAttributes_{stem},\n"
                f"    .callback = {callback},\n"
                f"}};"
            )
            externs.append(f"extern const struct Tileset {name};")

    # Forward-declare each tileset's InitTilesetAnim_Uranium* install fn (defined
    # in uranium_anims.gen.h, #included into engine/src/tileset_anims.c) so the
    # struct initializers above can reference it before that TU is linked.
    anim_decls = [
        f"void InitTilesetAnim_Uranium{ts}(void);"
        for ts in sorted(results) if results[ts].effects
    ]

    (fork / "src" / "data" / "tilesets" / "uranium_graphics.gen.h").write_text(
        _GEN_HEADER + "\n".join(graphics) + "\n", encoding="utf-8"
    )
    (fork / "src" / "data" / "tilesets" / "uranium_metatiles.gen.h").write_text(
        _GEN_HEADER + "\n".join(metatiles) + "\n", encoding="utf-8"
    )
    (fork / "src" / "data" / "tilesets" / "uranium_tilesets.gen.h").write_text(
        _GEN_HEADER + "\n".join(anim_decls + [""] + structs) + "\n", encoding="utf-8"
    )
    (fork / "include" / "uranium_externs.gen.h").write_text(
        _GEN_HEADER + "\n".join(externs) + "\n", encoding="utf-8"
    )
    _write_anim_fragment(fork, results)


def _anim_effect_symbol(ts: int, effect_name: str) -> str:
    """C symbol stem for one tileset's effect, e.g. ts=22, "anim19" -> "Uranium22_Anim19"."""
    return f"Uranium{ts}_{effect_name.capitalize()}"


def _write_anim_fragment(fork: Path, results: dict[int, EmittedTileset]) -> None:
    """Write ``engine/src/data/tilesets/uranium_anims.gen.h``: per-tileset animated-
    tile frame tables + DMA queue/dispatch/install functions.

    #include'd (not compiled as its own TU) into ``engine/src/tileset_anims.c``'s
    committed URANIUM PATHFINDER SLICE sentinel hook, so the generated functions
    can reach that file's static `AppendTilesetAnimToBuffer` / `sPrimaryTilesetAnim*`
    state directly. Every symbol here is `static` EXCEPT `InitTilesetAnim_Uranium{ts}`
    (the install fn a tileset's `.callback` points at from a different TU —
    `uranium_tilesets.gen.h`/`headers.h` — so it needs external linkage).

    Always written, even with zero animated tilesets (stub comment body), so the
    engine's unconditional `#include` compiles."""
    lines: list[str] = []
    for ts in sorted(results):
        emitted = results[ts]
        if not emitted.effects:
            continue
        prim = f"data/tilesets/primary/uranium{ts}"
        for eff in emitted.effects:
            sym = _anim_effect_symbol(ts, eff.name)
            frame_syms = [f"sTilesetAnims_{sym}_Frame{f}" for f in range(eff.n_frames)]
            for f, fsym in enumerate(frame_syms):
                lines.append(
                    f'static const u16 {fsym}[] = '
                    f'INCGFX_U16("{prim}/{eff.rel_dir}/f{f:02}.png", ".4bpp");'
                )
            lines.append(
                f"static const u16 *const sTilesetAnims_{sym}[] = {{\n    "
                + ",\n    ".join(frame_syms) + "\n};"
            )
            lines.append(
                f"static void QueueAnimTiles_{sym}(u16 f)\n"
                f"{{\n"
                f"    u16 i = f % ARRAY_COUNT(sTilesetAnims_{sym});\n"
                f"    AppendTilesetAnimToBuffer(sTilesetAnims_{sym}[i], "
                f"(u16 *)(BG_VRAM + TILE_OFFSET_4BPP({eff.first_tile_index})), "
                f"{eff.n_tiles} * TILE_SIZE_4BPP);\n"
                f"}}"
            )

        # Spread effects across the 16-tick window (one per tick offset), same
        # pattern as the vanilla TilesetAnim_General dispatcher.
        dispatch_body = "\n".join(
            f"    if (timer % 16 == {i})\n"
            f"        QueueAnimTiles_{_anim_effect_symbol(ts, eff.name)}(timer / 16);"
            for i, eff in enumerate(emitted.effects)
        )
        lines.append(
            f"static void TilesetAnim_Uranium{ts}(u16 timer)\n{{\n{dispatch_body}\n}}"
        )
        counter_max = 16 * math.lcm(*(eff.n_frames for eff in emitted.effects))
        lines.append(
            f"void InitTilesetAnim_Uranium{ts}(void)\n"
            f"{{\n"
            f"    sPrimaryTilesetAnimCounter = 0;\n"
            f"    sPrimaryTilesetAnimCounterMax = {counter_max};\n"
            f"    sPrimaryTilesetAnimCallback = TilesetAnim_Uranium{ts};\n"
            f"}}"
        )

    body = "\n\n".join(lines) if lines else "// no animated Uranium tilesets staged.\n"
    (fork / "src" / "data" / "tilesets" / "uranium_anims.gen.h").write_text(
        _GEN_HEADER + body + "\n", encoding="utf-8"
    )
