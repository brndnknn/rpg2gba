"""Graphics pre-pass (S8a) — build real Uranium tilesets for a slice.

Ties the image pipeline (sources -> raster -> quantize -> emit) to the assembler:
for each Uranium tileset used by the slice maps it enumerates the *topmost-visual*
tile ids (the same tile `layout.collapse_column` resolves per cell), emits a
dedicated pokeemerald PRIMARY+SECONDARY pair via `emit.emit_tileset`, and writes:

  - the GBA art under ``<fork>/data/tilesets/{primary,secondary}/uranium<ts>/``,
  - four generated, gitignored engine fragments pulled in by the committed
    sentinel ``#include`` hooks (``uranium_graphics.gen.h`` / ``uranium_metatiles.gen.h``
    / ``uranium_tilesets.gen.h`` in ``src/data/tilesets/`` and ``uranium_externs.gen.h``
    in ``include/``), and
  - a ``reference/tileset_map.gen.json`` overlay that `tile_map.load_tile_map`
    prefers over the committed Hoenn-bucket table (so the layout pass resolves each
    Uranium tile to its real metatile).

Each topmost-visual tile id becomes ONE single-layer metatile; autotile variants
are kept distinct (faithful edges). One synthetic transparent tile (RMXP id 0) is
appended as the void/border metatile. A representative door tile (the topmost tile
at a warp coord) gets ``MB_NON_ANIMATED_DOOR`` so the stamped warp metatile fires.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from rpg2gba.tileset_converter.layout import TileGrid, topmost_tile_id

from .emit import EmittedTileset, emit_tileset
from .raster import TileRasterizer
from .sources import load_tileset_sources

logger = logging.getLogger(__name__)

EMPTY_TILE = 0  # RMXP empty marker; rasterises transparent -> the void metatile

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
    dry_run: bool = False,
) -> dict[int, EmittedTileset]:
    """Emit real Uranium tilesets for the slice and write the engine + overlay glue.

    `maps` is ``[(map_id, map_json), ...]`` (each map_json has ``tileset_id`` and the
    Phase-3 ``tiles`` grid). `warp_coords` maps map_id -> warp source coords (the
    layout converter stamps the tileset's warp metatile there). `rasterizer_for`
    overrides tile rendering for tests; defaults to the real Uranium source pipeline.
    Returns the per-tileset `EmittedTileset`. Writes nothing when `dry_run`."""
    fork = Path(fork)
    make_rast = rasterizer_for or (
        lambda ts: _default_rasterizer(ts, tilesets_json, graphics_dir)
    )

    by_ts: dict[int, list[tuple[int, dict]]] = {}
    for map_id, map_json in maps:
        by_ts.setdefault(int(map_json["tileset_id"]), []).append((map_id, map_json))

    overlay = json.loads(Path(base_tile_map).read_text(encoding="utf-8"))
    for key in ("tilesets", "tiles", "buckets", "warps"):
        overlay.setdefault(key, {})

    door_behavior = _behavior_value(fork, "MB_NON_ANIMATED_DOOR")
    results: dict[int, EmittedTileset] = {}

    for ts, maplist in sorted(by_ts.items()):
        visuals: set[int] = set()
        door_ids: set[int] = set()
        for map_id, map_json in maplist:
            grid = _grid_of(map_json)
            for y in range(grid.ysize):
                for x in range(grid.xsize):
                    tid = topmost_tile_id(grid, x, y)
                    if tid != EMPTY_TILE:
                        visuals.add(tid)
            for wx, wy in warp_coords.get(map_id, set()):
                door = topmost_tile_id(grid, wx, wy)
                if door != EMPTY_TILE:
                    door_ids.add(door)

        if not visuals:
            raise ValueError(
                f"tileset {ts}: no visual tiles across maps "
                f"{[m for m, _ in maplist]} — wrong grid order or empty maps?"
            )

        # Deterministic order; RMXP id 0 (transparent) appended as the void metatile.
        tile_ids = sorted(visuals) + [EMPTY_TILE]
        rep_door = min(door_ids) if door_ids else None
        behavior_overrides = {rep_door: door_behavior} if rep_door is not None else {}

        primary_name = f"gTileset_Uranium{ts}"
        secondary_name = f"gTileset_Uranium{ts}B"
        primary_dir = fork / "data" / "tilesets" / "primary" / f"uranium{ts}"
        secondary_dir = fork / "data" / "tilesets" / "secondary" / f"uranium{ts}"

        if dry_run:
            logger.info(
                "[dry] S8a tileset %d: %d visual tiles, %d door tile(s) -> "
                "would emit %s + %s",
                ts, len(visuals), len(door_ids), primary_name, secondary_name,
            )
            continue

        emit = emit_tileset(
            tile_ids,
            make_rast(ts),
            primary_dir,
            secondary_dir,
            primary_name,
            secondary_name,
            behavior_overrides=behavior_overrides,
        )
        results[ts] = emit

        void_mt = emit.tile_to_metatile[EMPTY_TILE]
        overlay["tilesets"][str(ts)] = {
            "primary": primary_name, "secondary": secondary_name,
        }
        overlay["tiles"][str(ts)] = {
            str(tid): {"metatile": emit.tile_to_metatile[tid]} for tid in sorted(visuals)
        }
        # Fallback bucket -> transparent void (real cells hit the explicit `tiles`
        # entry; a fall-through would render transparent and be obvious at boot).
        overlay["buckets"][str(ts)] = {
            "passable": void_mt, "blocked": void_mt, "void": void_mt,
        }
        if rep_door is not None:
            overlay["warps"][str(ts)] = {
                "metatile": emit.tile_to_metatile[rep_door],
                "collision": 0,
                "elevation": 0,
            }
        logger.info(
            "S8a tileset %d: %d metatiles, %d GBA tiles, %d palettes "
            "(mean shift %.2f/31)",
            ts, emit.n_metatiles, emit.n_tiles, emit.n_palettes,
            emit.stats.get("mean_shift_5bit", 0.0),
        )

    if not dry_run:
        _write_fragments(fork, results)
        Path(overlay_out).write_text(
            json.dumps(overlay, indent=2) + "\n", encoding="utf-8"
        )
        logger.info(
            "S8a: wrote %s + 4 engine tileset fragments", overlay_out
        )
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
