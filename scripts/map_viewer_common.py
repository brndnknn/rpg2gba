# ruff: noqa: E501
"""Shared data-extraction and rendering core for the Uranium map viewer.

Used by both the static builder (build_map_viewer.py) and the lazy server
(map_viewer_server.py).  Module-level caches keep per-map rasterizer state alive
so repeated tile/metatile requests from the server don't rebuild from scratch.
"""
from __future__ import annotations

import io
import json
import logging
import os
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.build_slice_tilesets import (
    _render_column,
    column_keys_for_maps,
)
from rpg2gba.tileset_converter.graphics.emit import (
    MetatileImage,
    PaletteAnalysis,
    analyze_tileset_palettes,
)
from rpg2gba.tileset_converter.graphics.experimental_packers import (
    FamilyParams,
    build_quantized_tileset_family,
)
from rpg2gba.tileset_converter.graphics.raster import TileRasterizer
from rpg2gba.tileset_converter.graphics.sources import load_tileset_sources
from rpg2gba.tileset_converter.layout import TileGrid, column_key
from rpg2gba.tileset_converter.tile_map import serialize_column_key

sys.path.insert(0, str(Path(__file__).parent))
from compare_collision import our_blocked, uranium_blocked  # noqa: E402

log = logging.getLogger(__name__)

# The pathfinder slice the tileset build packs together (mirrors
# scripts/assemble_pathfinder.py SLICE_MAP_IDS).  build_slice_tilesets groups the
# slice maps BY tileset and quantizes each tileset over only the slice maps that
# share it, so the shipped palette for a tileset comes from exactly that pool.  The
# viewer scopes its analysis pool to these maps (plus whichever map is being opened)
# so palettes match the ROM — and so it never drags in a non-slice map whose tiles
# fall outside the tileset atlas (which would crash the rasterizer).
SLICE_MAP_IDS: list[int] = [49, 48, 32]

# ---------------------------------------------------------------------------
# Env / path helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    """Populate os.environ from repo-root .env-paths (shell values win)."""
    env_path = _repo_root() / ".env-paths"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _output_base() -> Path:
    _load_dotenv()
    return Path(os.environ.get("RPG2GBA_OUTPUT", str(_repo_root() / "output")))


def _maps_dir() -> Path:
    return _output_base() / "uranium-build" / "maps"


def _tilesets_json() -> Path:
    return _output_base() / "uranium-build" / "tilesets.json"


# ---------------------------------------------------------------------------
# Per-map cache
# ---------------------------------------------------------------------------


@dataclass
class _MapState:
    grid: TileGrid
    raster: TileRasterizer
    priorities: list[int]
    passages: list[int]
    terrain_tags: list[int]
    autotile_names: list[str]
    tileset_id: int
    ts_name: str
    ts_tileset_name: str
    map_width: int
    map_height: int
    events_raw: list
    colkeys_sorted: list[tuple]           # stable-sorted column-key tuples
    colkey_to_idx: dict[tuple, int]       # tuple -> index in colkeys_sorted
    metatile_imgs: list[MetatileImage | None]  # indexed by colkey idx; None = empty col
    metatile_imgs_postquant: list[tuple[np.ndarray, np.ndarray] | None]  # aligned with metatile_imgs; None = empty col
    analysis: PaletteAnalysis             # slice-scoped palette analysis for this map's tileset
    pool_key_to_idx: dict[tuple, int]     # column key -> index into analysis.metatiles


_map_cache: dict[int, _MapState] = {}
_tile_png_cache: dict[tuple[int, int], bytes] = {}          # (map_id, tile_id)
_metatile_png_cache: dict[tuple[int, int, str], bytes] = {}  # (map_id, idx, layer)
_tileset_analysis_cache: dict[frozenset[int], tuple[PaletteAnalysis, dict[tuple, int]]] = {}  # pool map-id set -> (analysis, pool_key_to_idx)


# ---------------------------------------------------------------------------
# Live quantization knobs
# ---------------------------------------------------------------------------
# The "Quantized" view uses the FAMILY packer; its parameters are tunable at runtime
# from the browser (POST /api/quantize) so the foliage/interior trade-offs can be A/B'd
# without re-running the pipeline.  Default FamilyParams() == the family packer's stock
# behavior.  Changing params invalidates the three quant-dependent caches (the RMXP
# source-tile cache is param-independent and kept).  `_quant_generation` is a monotonic
# token the client appends to post-quant image URLs to defeat the browser's immutable
# cache after an Apply.
_ENGINE_MAX_PALS = 13  # NUM_PALS_TOTAL — hardware/engine ceiling; knob can only lower it
_family_params: FamilyParams = FamilyParams()
_max_palettes: int = _ENGINE_MAX_PALS
_quant_generation: int = 0


def _make_quantizer():
    """Current packer as a ``(tiles, *, max_palettes) -> QuantizeResult`` callable."""
    return partial(build_quantized_tileset_family, params=_family_params)


def current_quantize_state() -> tuple[FamilyParams, int]:
    """Live (params, max_palettes) — for snapshot/rollback by the server."""
    return _family_params, _max_palettes


def get_quantize_params() -> dict:
    """Current knob state for injection into the page config (seeds the UI + the
    `generation` cache-bust token)."""
    return {
        "generation": _quant_generation,
        "max_palettes": _max_palettes,
        "dark_value": _family_params.dark_value,
        "neutral_sat": _family_params.neutral_sat,
        "green_cuts": list(_family_params.green_cuts),
        "palette_floor": _family_params.palette_floor,
        "overflow_weight": _family_params.overflow_weight,
    }


def set_quantize_params(params: FamilyParams, max_palettes: int) -> int:
    """Update the live family-quant knobs, invalidate the quant-dependent caches, and
    return the new generation token.  The RMXP source-tile cache is left intact."""
    global _family_params, _max_palettes, _quant_generation
    _family_params = params
    _max_palettes = max_palettes
    _quant_generation += 1
    _tileset_analysis_cache.clear()
    _map_cache.clear()
    _metatile_png_cache.clear()
    return _quant_generation


def params_from_dict(d: dict) -> tuple[FamilyParams, int]:
    """Parse + clamp a knob dict (from the Apply POST) into (FamilyParams, max_palettes)
    so a malformed value can never crash the packer.  green_cuts are kept only if they
    fall strictly inside the green band (70, 170)."""
    mp = max(1, min(_ENGINE_MAX_PALS, int(d.get("max_palettes", _ENGINE_MAX_PALS))))
    cuts = sorted({float(c) for c in d.get("green_cuts", []) if 70.0 < float(c) < 170.0})
    params = FamilyParams(
        dark_value=max(0, min(255, int(d.get("dark_value", 40)))),
        neutral_sat=max(0.0, min(1.0, float(d.get("neutral_sat", 0.18)))),
        green_cuts=tuple(cuts),
        palette_floor=max(1, min(_ENGINE_MAX_PALS, int(d.get("palette_floor", 1)))),
        overflow_weight=("coverage" if str(d.get("overflow_weight")) == "coverage" else "colors"),
    )
    return params, mp


def _ensure_tileset_analysis(
    tileset_id: int,
    raster: TileRasterizer,
    priorities: list[int],
    map_id: int,
) -> tuple[PaletteAnalysis, dict[tuple, int]]:
    """Build and cache the slice-scoped palette analysis for a tileset (idempotent).

    The pool is the SLICE maps (plus ``map_id`` itself) whose tileset_id matches —
    exactly the per-tileset pool build_slice_tilesets quantizes for the shipped ROM
    (see SLICE_MAP_IDS).  Scoping to the slice keeps palette assignment faithful and
    avoids rendering non-slice maps that reference tiles outside the tileset atlas.
    Opening a non-slice map analyzes that map on its own (no shipped truth exists).
    """
    maps_dir = _maps_dir()
    maplist: list[tuple[int, dict]] = []
    for mid in sorted(set(SLICE_MAP_IDS) | {map_id}):
        p = maps_dir / f"Map{mid:03d}.json"
        if not p.is_file():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if int(doc.get("tileset_id", -1)) == tileset_id:
            maplist.append((mid, doc))

    cache_key = frozenset(mid for mid, _ in maplist)
    if cache_key in _tileset_analysis_cache:
        return _tileset_analysis_cache[cache_key]

    pool_keys = column_keys_for_maps(maplist)
    print(
        f"    tileset {tileset_id}: pool of {len(maplist)} slice map(s) "
        f"{sorted(cache_key)}, {len(pool_keys)} unique non-empty column keys"
    )

    if not pool_keys:
        analysis: PaletteAnalysis = PaletteAnalysis(palettes=[], metatiles=[])
        pool_key_to_idx: dict[tuple, int] = {}
    else:
        pool_metatiles = [_render_column(ck, raster, priorities) for ck in pool_keys]
        analysis = analyze_tileset_palettes(
            pool_metatiles, max_palettes=_max_palettes, quantizer=_make_quantizer()
        )
        pool_key_to_idx = {ck: i for i, ck in enumerate(pool_keys)}

    _tileset_analysis_cache[cache_key] = (analysis, pool_key_to_idx)
    return analysis, pool_key_to_idx


def _ensure_loaded(map_id: int) -> None:
    """Load and cache all per-map rendering state (idempotent)."""
    if map_id in _map_cache:
        return

    maps_dir = _maps_dir()
    tilesets_json_path = _tilesets_json()

    map_path = maps_dir / f"Map{map_id:03d}.json"
    if not map_path.is_file():
        raise FileNotFoundError(f"Map JSON not found: {map_path}")

    doc = json.loads(map_path.read_text(encoding="utf-8"))
    tileset_id = int(doc["tileset_id"])

    all_tilesets = json.loads(tilesets_json_path.read_text(encoding="utf-8"))
    ts_entry = all_tilesets.get(str(tileset_id))
    if ts_entry is None:
        raise KeyError(f"tileset {tileset_id} absent from {tilesets_json_path}")

    t = doc["tiles"]
    grid = TileGrid(t["xsize"], t["ysize"], t["zsize"], t["data"])
    passages: list[int] = ts_entry["passages"]
    priorities: list[int] = ts_entry["priorities"]
    terrain_tags: list[int] = ts_entry["terrain_tags"]
    autotile_names: list[str] = ts_entry["autotile_names"]

    raster = TileRasterizer(load_tileset_sources(tileset_id, tilesets_json=tilesets_json_path))

    log.info(
        "Map%03d: %dx%d cells, tileset %d (%s / %s)",
        map_id, grid.xsize, grid.ysize, tileset_id,
        ts_entry.get("name", ""), ts_entry.get("tileset_name", ""),
    )
    print(
        f"  Map{map_id:03d}: {grid.xsize}x{grid.ysize} cells, tileset {tileset_id}"
        f" ({ts_entry.get('name', '')} / {ts_entry.get('tileset_name', '')})"
    )

    # Collect distinct column keys; sort for stable per-map index assignment.
    used: set[tuple] = set()
    for y in range(grid.ysize):
        for x in range(grid.xsize):
            used.add(column_key(grid, x, y))

    colkeys_sorted = sorted(used)
    colkey_to_idx = {ck: i for i, ck in enumerate(colkeys_sorted)}

    # Pre-render all metatiles (cheap numpy compositing; persists for server reuse).
    metatile_imgs: list[MetatileImage | None] = []
    for ck in colkeys_sorted:
        if not ck:
            metatile_imgs.append(None)  # empty column -> transparent
        else:
            metatile_imgs.append(_render_column(ck, raster, priorities))

    n_rendered = sum(1 for m in metatile_imgs if m is not None)
    print(f"    {len(colkeys_sorted)} distinct columns, {n_rendered} metatile renders")

    # Build the slice-scoped palette analysis for this tileset (matches the ROM pool).
    analysis, pool_key_to_idx = _ensure_tileset_analysis(tileset_id, raster, priorities, map_id)

    # Build post-quant metatile pairs aligned 1:1 with metatile_imgs / colkeys_sorted.
    metatile_imgs_postquant: list[tuple[np.ndarray, np.ndarray] | None] = []
    for ck in colkeys_sorted:
        if not ck:
            metatile_imgs_postquant.append(None)
        else:
            pool_idx = pool_key_to_idx.get(ck)
            if pool_idx is None:
                raise ValueError(
                    f"Map{map_id:03d}: column key {ck!r} absent from tileset {tileset_id} pool — "
                    "analysis is inconsistent with this map's column keys"
                )
            mp = analysis.metatiles[pool_idx]
            metatile_imgs_postquant.append((mp.quant_bottom, mp.quant_top))

    _map_cache[map_id] = _MapState(
        grid=grid,
        raster=raster,
        priorities=priorities,
        passages=passages,
        terrain_tags=terrain_tags,
        autotile_names=autotile_names,
        tileset_id=tileset_id,
        ts_name=ts_entry.get("name", ""),
        ts_tileset_name=ts_entry.get("tileset_name", ""),
        map_width=int(doc.get("width", grid.xsize)),
        map_height=int(doc.get("height", grid.ysize)),
        events_raw=doc.get("events", []),
        colkeys_sorted=colkeys_sorted,
        colkey_to_idx=colkey_to_idx,
        metatile_imgs=metatile_imgs,
        metatile_imgs_postquant=metatile_imgs_postquant,
        analysis=analysis,
        pool_key_to_idx=pool_key_to_idx,
    )


# ---------------------------------------------------------------------------
# Public rendering API
# ---------------------------------------------------------------------------


def _arr_to_png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def render_tile_png(map_id: int, tile_id: int) -> bytes:
    """Render one RMXP tile to PNG bytes (module-level cache)."""
    _ensure_loaded(map_id)
    key = (map_id, tile_id)
    if key in _tile_png_cache:
        return _tile_png_cache[key]
    state = _map_cache[map_id]
    if tile_id == 0:
        img: Image.Image = Image.fromarray(np.zeros((16, 16, 4), dtype=np.uint8), "RGBA")
    else:
        img = state.raster.render(tile_id)
        if img is None:
            raise ValueError(f"tile {tile_id} rendered None for map {map_id}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png = buf.getvalue()
    _tile_png_cache[key] = png
    return png


def render_metatile_png(map_id: int, idx: int, layer: str) -> bytes:
    """Render one metatile layer to PNG bytes (cached).

    ``layer`` is one of: ``'bottom'``, ``'top'``, ``'post_bottom'``, ``'post_top'``.
    ``post_bottom`` / ``post_top`` return the quantized-and-alpha-resolved pixels
    that match the shipped ROM's palette assignment.

    ``idx`` is the per-map colkey index returned in ``build_map_data``."""
    _ensure_loaded(map_id)
    key = (map_id, idx, layer)
    if key in _metatile_png_cache:
        return _metatile_png_cache[key]
    state = _map_cache[map_id]
    if idx < 0 or idx >= len(state.metatile_imgs):
        raise IndexError(f"metatile idx {idx} out of range for map {map_id}")

    if layer in ("post_bottom", "post_top"):
        pq = state.metatile_imgs_postquant[idx]
        if pq is None:
            arr: np.ndarray = np.zeros((16, 16, 4), dtype=np.uint8)
        else:
            arr = pq[0] if layer == "post_bottom" else pq[1]
    else:
        mt = state.metatile_imgs[idx]
        if mt is None:
            arr = np.zeros((16, 16, 4), dtype=np.uint8)
        else:
            arr = mt.top if layer == "top" else mt.bottom

    png = _arr_to_png(arr)
    _metatile_png_cache[key] = png
    return png


# ---------------------------------------------------------------------------
# Data collection (no image bytes — used directly by the server)
# ---------------------------------------------------------------------------


def _parse_events(events_list: list) -> list[dict]:
    result = []
    for evt in events_list:
        is_warp = any(
            any(cmd.get("code") == 201 for cmd in page.get("list", []))
            for page in evt.get("pages", [])
        )
        result.append({
            "id": evt.get("id"),
            "name": evt.get("name", ""),
            "x": evt.get("x"),
            "y": evt.get("y"),
            "npages": len(evt.get("pages", [])),
            "is_warp": is_warp,
        })
    return result


def build_map_data(map_id: int) -> dict:
    """Return all per-map data WITHOUT inline image bytes.

    Distinct column keys are assigned stable integer indices (``colkeys_list``);
    cells reference these via ``colkey_idx`` rather than the URL-unsafe colkey
    string.  Per-cell tile references stay as ``tile_id`` ints.
    Use ``render_tile_png`` / ``render_metatile_png`` to obtain image bytes.
    """
    _ensure_loaded(map_id)
    state = _map_cache[map_id]
    grid = state.grid

    colkeys_list = [serialize_column_key(ck) for ck in state.colkeys_sorted]

    metatile_attrs: list[dict] = []
    for mt in state.metatile_imgs:
        if mt is None:
            metatile_attrs.append({"layer_type": 0, "behavior": 0})
        else:
            metatile_attrs.append({"layer_type": int(mt.layer_type), "behavior": int(mt.behavior)})

    cells: list[dict] = []
    for y in range(grid.ysize):
        for x in range(grid.xsize):
            layers = [grid.tile_at(x, y, z) for z in range(grid.zsize)]
            ck = column_key(grid, x, y)
            colkey_idx = state.colkey_to_idx[ck]

            layer_detail: list[dict] = []
            for z, tid in enumerate(layers):
                if tid == 0:
                    continue
                pas = state.passages[tid] if 0 <= tid < len(state.passages) else 0
                pri = state.priorities[tid] if 0 <= tid < len(state.priorities) else 0
                ter = state.terrain_tags[tid] if 0 <= tid < len(state.terrain_tags) else 0
                at_name: str | None = (
                    state.autotile_names[tid // 48 - 1] if 48 <= tid < 384 else None
                )
                layer_detail.append({
                    "z": z, "tile_id": tid, "passage": pas,
                    "priority": pri, "terrain": ter, "autotile_name": at_name,
                })

            col_ours = our_blocked(grid, state.passages, state.priorities, x, y)
            col_ur = uranium_blocked(grid, state.passages, state.priorities, state.terrain_tags, x, y)
            pmax = max(
                (state.priorities[tid] for tid in layers if tid > 0 and tid < len(state.priorities)),
                default=0,
            )

            cells.append({
                "x": x, "y": y,
                "layers": layers,
                "colkey_idx": colkey_idx,
                "layer_detail": layer_detail,
                "collision_ours": col_ours,
                "collision_uranium": col_ur,
                "mismatch": col_ours != col_ur,
                "priority_max": pmax,
            })

    # ---- palette data -------------------------------------------------------
    analysis, pool_key_to_idx = state.analysis, state.pool_key_to_idx

    # palettes: JSON-friendly list[list[[r,g,b]]]
    palettes_json: list[list[list[int]]] = [
        [[r, g, b] for (r, g, b) in pal]
        for pal in analysis.palettes
    ]

    # rmxp_tile_colors: distinct source colors per tile_id used in this map
    used_tile_ids: set[int] = set()
    for cell in cells:
        for ld in cell["layer_detail"]:
            used_tile_ids.add(ld["tile_id"])

    rmxp_tile_colors: dict[str, list[list[int]]] = {}
    for tid in used_tile_ids:
        img = state.raster.render(tid)
        if img is None:
            rmxp_tile_colors[str(tid)] = []
            continue
        arr = np.array(img)  # RGBA
        visible = arr[arr[:, :, 3] > 0, :3]
        seen_rgb: set[tuple[int, int, int]] = set()
        unique_colors: list[list[int]] = []
        for px in visible:
            t = (int(px[0]), int(px[1]), int(px[2]))
            if t not in seen_rgb:
                seen_rgb.add(t)
                unique_colors.append([t[0], t[1], t[2]])
        rmxp_tile_colors[str(tid)] = unique_colors

    # colkey_palettes: per-colkey-idx summary of palette usage and color changes
    # A "merge" is a colour whose 5-bit value moved (orig>>3 != final>>3): the
    # palette packer couldn't keep it, so it snapped to a neighbour.  A pair with
    # zero shift is pure 8->5-bit truncation, not merging.  merge_severity sums the
    # L1 5-bit distance over snapped colours so the worst tiles can be heat-mapped.
    colkey_palettes: list[dict] = []
    for ck in state.colkeys_sorted:
        if not ck:
            colkey_palettes.append({
                "palette_indices": [], "color_changes": [],
                "quadrant_fit": [], "merge_colors": 0, "merge_severity": 0,
            })
            continue
        pool_idx = pool_key_to_idx[ck]
        mt_pal = analysis.metatiles[pool_idx]
        pi_set: set[int] = set()
        cc_seen: set[tuple] = set()
        cc_list: list[list[list[int]]] = []
        quadrant_fit: list[dict] = []
        merge_colors = 0
        merge_severity = 0
        for slot, qp in enumerate(mt_pal.quadrants):
            if qp.palette_index == -1:
                continue  # fully transparent quadrant: nothing to fit
            pi_set.add(qp.palette_index)
            q_merged = 0
            q_max_shift = 0
            for orig, final in qp.color_changes:
                d = [abs((orig[k] >> 3) - (final[k] >> 3)) for k in range(3)]
                shift = d[0] + d[1] + d[2]  # L1 distance in 5-bit units
                if shift > 0:               # snapped to a non-identical palette colour
                    q_merged += 1
                    merge_severity += shift
                    q_max_shift = max(q_max_shift, max(d))
                key_cc = (orig, final)
                if key_cc not in cc_seen:
                    cc_seen.add(key_cc)
                    cc_list.append([
                        [orig[0], orig[1], orig[2]],
                        [final[0], final[1], final[2]],
                    ])
            merge_colors += q_merged
            quadrant_fit.append({
                "slot": slot, "pal": qp.palette_index,
                "n": len(qp.color_changes), "merged": q_merged, "max_shift": q_max_shift,
            })
        colkey_palettes.append({
            "palette_indices": sorted(pi_set),
            "color_changes": cc_list,
            "quadrant_fit": quadrant_fit,
            "merge_colors": merge_colors,
            "merge_severity": merge_severity,
        })

    # ---- palette_usage: inverse map palette -> tiles that use it ------------
    # For each GBA sub-palette, list the metatiles (by colkey idx) drawing from it
    # and which palette entries each one actually uses.  This is the data behind the
    # palette-centric inspector page: a tile that uses only 1-2 entries while needing
    # a colour the palette lacks shows up as low n_colors + high merge_severity.
    #
    # Slot indexing matches the page's swatch layout: slot 0 = transparent (index 0),
    # so a palette colour at analysis.palettes[pi][j] is referenced as slot j+1.
    pal_rev: list[dict[tuple[int, int, int], int]] = [
        {rgb: j + 1 for j, rgb in enumerate(pal)} for pal in analysis.palettes
    ]
    # pal -> { colkey_idx -> set(slot) }
    pal_tile_slots: list[dict[int, set[int]]] = [{} for _ in analysis.palettes]
    for ck_idx, ck in enumerate(state.colkeys_sorted):
        if not ck:
            continue
        mt_pal = analysis.metatiles[pool_key_to_idx[ck]]
        for qp in mt_pal.quadrants:
            pi = qp.palette_index
            if pi == -1:
                continue
            rev = pal_rev[pi]
            slot_set = pal_tile_slots[pi].setdefault(ck_idx, set())
            for _orig, final in qp.color_changes:
                slot = rev.get(final)
                if slot is not None:
                    slot_set.add(slot)

    palette_usage: list[dict] = []
    for pi, pal in enumerate(analysis.palettes):
        tiles_for_pal = pal_tile_slots[pi]
        used_slots: set[int] = set()
        tiles: list[dict] = []
        for ck_idx, slots in tiles_for_pal.items():
            used_slots |= slots
            sev = colkey_palettes[ck_idx]["merge_severity"]
            tiles.append({
                "idx": ck_idx,
                "n_colors": len(slots),
                "slots": sorted(slots),
                "merge_severity": sev,
            })
        # Suspect-first: fewest colours, then worst merge loss.
        tiles.sort(key=lambda t: (t["n_colors"], -t["merge_severity"]))
        palette_usage.append({
            "pal": pi,
            "colors": [[r, g, b] for (r, g, b) in pal],
            "used_slots": sorted(used_slots),
            "n_tiles": len(tiles),
            "tiles": tiles,
        })

    return {
        "meta": {
            "map_id": map_id,
            "tileset_id": state.tileset_id,
            "name": state.ts_name,
            "tileset_name": state.ts_tileset_name,
            "xsize": grid.xsize,
            "ysize": grid.ysize,
            "zsize": grid.zsize,
            "width": state.map_width,
            "height": state.map_height,
        },
        "colkeys_list": colkeys_list,
        "metatile_attrs": metatile_attrs,
        "cells": cells,
        "events": _parse_events(state.events_raw),
        "palettes": palettes_json,
        "rmxp_tile_colors": rmxp_tile_colors,
        "colkey_palettes": colkey_palettes,
        "palette_usage": palette_usage,
    }


# ---------------------------------------------------------------------------
# Shared HTML/CSS/JS template
# ---------------------------------------------------------------------------
# getTileURL(tileId) and getMetatileURL(idx, layer) implement the mode seam:
#   SERVER mode  -> /api/tile/<mapid>/<tid>.png  etc.
#   STATIC mode  -> data: URIs from window.__VIEWER__.tile_images / .metatile_images
#
# The Python side replaces __VIEWER_CONFIG__ with a JSON blob:
#   { mode, data, [tile_images], [metatile_images] }

MAP_VIEWER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Map Inspector</title>
<script>window.__VIEWER__=__VIEWER_CONFIG__;</script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1a1a;color:#ddd;font:12px/1.4 monospace;display:flex;flex-direction:column;height:100vh;overflow:hidden}
#toolbar{background:#252525;border-bottom:1px solid #444;padding:4px 8px;display:flex;flex-wrap:wrap;gap:4px 6px;align-items:center;flex-shrink:0}
#toolbar label{cursor:pointer;user-select:none;display:flex;align-items:center;gap:3px}
#toolbar input[type=radio]{accent-color:#5af}
#toolbar input[type=checkbox]{accent-color:#fa5}
.sep{width:1px;background:#555;height:20px;margin:0 2px;flex-shrink:0}
.btn{background:#333;border:1px solid #555;color:#ddd;padding:2px 8px;cursor:pointer;font:11px monospace;border-radius:2px}
.btn:hover{background:#444}
/* ---- map nav strip ---- */
#mapnav{display:none;background:#1c1c1c;border-bottom:1px solid #383838;padding:4px 8px;gap:6px;align-items:center;overflow-x:auto;white-space:nowrap;flex-shrink:0;font-size:11px}
#mapnav.show{display:flex}
#knobbar{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center;background:#1f241f;border-bottom:1px solid #3a463a;padding:4px 8px;flex-shrink:0;font-size:11px}
#knobbar label{color:#9a9;display:flex;align-items:center;gap:3px}
#knobbar input,#knobbar select{background:#222;color:#dfe;border:1px solid #4a5a4a;font:11px monospace;padding:2px 3px;border-radius:2px}
#knobbar input[type=number]{width:52px}
#knobbar #k_apply{background:#2c3a2c;border-color:#5a7a5a;color:#cfe}
#knobbar #k_status{color:#fa0}
#mapnav .navcur{color:#8cf;font-weight:bold;flex-shrink:0}
#mapnav .navgrp{color:#777;flex-shrink:0;margin-left:2px}
#mapnav .navchip{display:inline-block;background:#2a2a2a;border:1px solid #4a4a4a;color:#bcd;text-decoration:none;padding:1px 7px;border-radius:10px;flex-shrink:0}
#mapnav .navchip:hover{background:#33414e;border-color:#5af;color:#cfe}
#mapnav .navchip.home{background:#243d2e;border-color:#475}
#mapnav .navsep{width:1px;height:16px;background:#444;flex-shrink:0;margin:0 2px}
#main{display:flex;flex:1;min-height:0;position:relative}
#canvas-wrap{flex:1;position:relative;overflow:hidden;background:#111}
canvas{display:block;image-rendering:pixelated;image-rendering:crisp-edges;touch-action:none;width:100%;height:100%}
#sidebar{width:300px;background:#1e1e1e;border-left:1px solid #444;overflow-y:auto;flex-shrink:0;display:flex;flex-direction:column;transition:transform .2s}
#sidebar-toggle{display:none}
#cell-info{padding:8px;flex:1;overflow-y:auto}
#issue-panel{background:#1a1810;border-top:1px solid #554;padding:8px;flex-shrink:0}
#merge-panel{background:#1a1018;border-top:1px solid #534;padding:6px 8px;flex-shrink:0}
#merge-list{margin-top:4px;max-height:200px;overflow-y:auto}
.merge-item{display:flex;align-items:center;gap:6px;background:#251820;border:1px solid #534;padding:2px 5px;margin:2px 0;font-size:11px;cursor:pointer}
.merge-item:hover{background:#3a2433}
#statusbar{background:#111;border-top:1px solid #333;padding:2px 8px;font-size:11px;color:#999;flex-shrink:0;height:22px;white-space:nowrap;overflow:hidden}
.section-title{color:#5af;font-weight:bold;margin:6px 0 3px;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.layer-row{display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid #2a2a2a}
.thumb{width:32px;height:32px;image-rendering:pixelated;border:1px solid #444;background:#000;flex-shrink:0}
.thumb-pair{display:flex;gap:4px}
.lbl{color:#888;font-size:11px}
.val{color:#eee}
.mismatch{color:#f66;font-weight:bold}
.match{color:#6f6}
.blocked{color:#f55}
.passable{color:#5d5}
#issue-list{margin-top:6px;max-height:150px;overflow-y:auto}
.issue-item{background:#252018;border:1px solid #554;padding:3px 5px;margin:2px 0;font-size:11px}
.issue-del{color:#f55;cursor:pointer;float:right}
#note-area{display:none;margin-top:4px}
#note-area textarea{width:100%;height:50px;background:#222;color:#eee;border:1px solid #555;font:11px monospace;padding:3px;resize:vertical}
/* ---- palette / swatch display ---- */
.swatch{display:inline-block;width:14px;height:14px;border:1px solid #555;vertical-align:middle;cursor:default;margin:1px;flex-shrink:0}
.swatch-checker{background-image:repeating-conic-gradient(#777 0% 25%,#bbb 0% 50%);background-size:8px 8px}
.pal-strip{display:flex;flex-wrap:wrap;align-items:center;gap:1px;margin:2px 0}
.pal-label{color:#888;font-size:10px;margin-right:4px;white-space:nowrap}
.cc-row{display:flex;align-items:center;gap:4px;padding:2px 0;font-size:10px;border-bottom:1px solid #222}
.cc-row.changed .swatch{outline:2px solid #fa0}
.cc-arrow{color:#666}
.cc-tag-same{color:#556}
.cc-tag-changed{color:#fa0}
.qfit{font-size:10px;padding:1px 5px;margin:1px 0;border-left:3px solid #555;background:#222}
.qfit-ok{border-left-color:#4a4;color:#9c9}
.qfit-warn{border-left-color:#fa0;color:#fc8}
.qfit-bad{border-left-color:#f44;color:#f99}
.qfit-ok-txt{color:#6d6}
.qfit-bad-txt{color:#f77;font-weight:bold}
/* ---- responsive: narrow viewport ---- */
@media (max-width:720px){
  body{height:100dvh}
  #main{flex-direction:column}
  #sidebar{position:fixed;bottom:0;left:0;right:0;z-index:10;width:auto;max-height:55vh;border-left:none;border-top:2px solid #5af;transform:translateY(100%)}
  #sidebar.open{transform:translateY(0)}
  #sidebar-toggle{display:flex;align-items:center;justify-content:center;position:fixed;bottom:14px;right:14px;z-index:20;min-width:44px;min-height:44px;padding:0 14px;background:#2a2a2a;border:1px solid #555;border-radius:22px;color:#ddd;font:12px monospace;cursor:pointer}
  #toolbar label{min-height:32px}
  .btn{min-height:32px;padding:4px 10px}
  .sep{height:28px}
  #mapnav{gap:8px;padding:6px 8px}
  #mapnav .navchip{min-height:32px;padding:6px 12px;display:flex;align-items:center}
  #mapnav .navsep{height:24px}
}
</style>
</head>
<body>
<div id="toolbar">
  <span class="lbl">View:</span>
  <label><input type="radio" name="view2" value="rmxp" checked> RPG Maker</label>
  <label><input type="radio" name="view2" value="post-quant"> Quantized (family)</label>
  <!-- Dormant: the original per-layer radios are kept intact but hidden; the 2-way
       toggle above drives the same `currentLayer`. Unhide #layer-debug (or set its
       display) to restore the full RMXP/L0/L1/L2/GBA/Post-Q layer inspector. -->
  <span id="layer-debug" style="display:none">
  <span class="lbl">Layer:</span>
  <label><input type="radio" name="layer" value="rmxp" checked> RMXP</label>
  <label><input type="radio" name="layer" value="l0"> L0</label>
  <label><input type="radio" name="layer" value="l1"> L1</label>
  <label><input type="radio" name="layer" value="l2"> L2</label>
  <label><input type="radio" name="layer" value="gba"> GBA</label>
  <label><input type="radio" name="layer" value="gba_bottom"> GBA&#8595;</label>
  <label><input type="radio" name="layer" value="gba_top"> GBA&#8593;</label>
  <label><input type="radio" name="layer" value="post-quant"> Post-Q</label>
  </span>
  <div class="sep"></div>
  <span class="lbl">Overlay:</span>
  <label><input type="checkbox" id="ov_collision"> Collision</label>
  <label><input type="checkbox" id="ov_diff"> Diff</label>
  <label><input type="checkbox" id="ov_priority"> Priority</label>
  <label title="Heat-map cells by palette-merge loss (brighter = more colour snapped)"><input type="checkbox" id="ov_merge"> Merge</label>
  <label><input type="checkbox" id="ov_events" checked> Events</label>
  <label><input type="checkbox" id="ov_warps" checked> Warps</label>
  <div class="sep"></div>
  <span class="lbl">Zoom:</span>
  <button class="btn" id="zoom-out">-</button>
  <span id="zoom-val" style="min-width:28px;text-align:center">2x</span>
  <button class="btn" id="zoom-in">+</button>
  <button class="btn" id="zoom-fit">Fit</button>
  <div class="sep"></div>
  <a class="btn" id="nav-palettes" href="#" style="display:none;text-decoration:none">Palettes &rarr;</a>
  <span class="lbl" id="map-title" style="color:#8cf"></span>
</div>
<div id="mapnav"></div>
<div id="knobbar">
  <span class="lbl">Family knobs:</span>
  <label title="Interior hue degrees in (70,170) that split the green band into sub-families. Comma-separated, e.g. 120 or 100,140. Empty = one green.">green cuts <input id="k_green" type="text" size="9" placeholder="e.g. 120"></label>
  <label title="max(R,G,B) below this = 'dark' family">dark&lt; <input id="k_dark" type="number" min="0" max="255" step="1"></label>
  <label title="HSV saturation below this = 'neutral' family">neutral sat&lt; <input id="k_neutral" type="number" min="0" max="1" step="0.01"></label>
  <label title="Minimum sub-palettes guaranteed to every family">pal floor <input id="k_floor" type="number" min="1" max="13" step="1"></label>
  <label title="How leftover palettes are handed out: by distinct-colour overflow, or weighted by how many tiles a family covers">overflow
    <select id="k_overflow"><option value="colors">colors</option><option value="coverage">coverage</option></select></label>
  <label title="Total sub-palette budget (engine ceiling 13)">max pals <input id="k_maxpal" type="number" min="1" max="13" step="1"></label>
  <button class="btn" id="k_apply">Apply &amp; re-render</button>
  <span id="k_status" class="lbl"></span>
</div>
<div id="main">
  <div id="canvas-wrap">
    <canvas id="mapCanvas"></canvas>
  </div>
  <div id="sidebar">
    <div id="cell-info"><span style="color:#555">Click a cell to inspect.</span></div>
    <div id="merge-panel">
      <div class="section-title" id="merge-head" style="cursor:pointer"><span id="merge-tri">&#9656;</span> Worst palette merges <span id="merge-count" class="lbl"></span></div>
      <div id="merge-list" style="display:none"></div>
    </div>
    <div id="issue-panel">
      <div class="section-title">Issues</div>
      <button class="btn" id="btn-flag" disabled>Flag selected cell</button>
      <button class="btn" id="btn-export">Export JSON</button>
      <div id="note-area">
        <textarea id="note-text" placeholder="Note about this cell..."></textarea>
        <button class="btn" id="btn-note-save">Save</button>
        <button class="btn" id="btn-note-cancel">Cancel</button>
      </div>
      <div id="issue-list"></div>
    </div>
  </div>
</div>
<button class="btn" id="sidebar-toggle">&#9660; Inspector</button>
<div id="statusbar"></div>
<script>
// ---- viewer config --------------------------------------------------------
const V = window.__VIEWER__;
const D = V.data;

// ---- mode seam: getTileURL / getMetatileURL -------------------------------
function getTileURL(tileId) {
  if (!tileId) return null;
  if (V.mode === 'static') return (V.tile_images || {})[String(tileId)] || null;
  return '/api/tile/' + D.meta.map_id + '/' + tileId + '.png';
}
function getMetatileURL(idx, layer) {
  if (V.mode === 'static') {
    const m = (V.metatile_images || {})[idx];
    return m ? m[layer] : null;
  }
  // `g` = quant generation: bumped on every knob Apply so the post-quant PNGs (served
  // with Cache-Control: immutable) are re-fetched instead of served stale by the browser.
  const g = (V.quant && V.quant.generation) || 0;
  return '/api/metatile/' + D.meta.map_id + '/' + idx + '.png?layer=' + layer + '&g=' + g;
}

// ---- lazy image cache -----------------------------------------------------
const imgCache = new Map(); // url -> HTMLImageElement | 'loading' | 'err'
let renderPending = false;
function scheduleRender() {
  if (renderPending) return;
  renderPending = true;
  requestAnimationFrame(function() { renderPending = false; render(); });
}
function drawImg(url, dx, dy, cp) {
  if (!url) return;
  const c = imgCache.get(url);
  if (!c) {
    imgCache.set(url, 'loading');
    const img = new Image();
    img.onload = function() { imgCache.set(url, img); scheduleRender(); };
    img.onerror = function() { imgCache.set(url, 'err'); };
    img.src = url;
    ctx.fillStyle = '#1c1c22'; ctx.fillRect(dx, dy, cp, cp);
    return;
  }
  if (c === 'loading') { ctx.fillStyle = '#1c1c22'; ctx.fillRect(dx, dy, cp, cp); return; }
  if (c === 'err') return;
  ctx.drawImage(c, dx, dy, cp, cp);
}

// ---- state ----------------------------------------------------------------
let zoom = 2;
let panX = 0, panY = 0;
let currentLayer = 'rmxp';
let overlays = {collision:false, diff:false, priority:false, merge:false, events:true, warps:true};
// Max merge severity across this map's metatiles, for normalizing the Merge heat-map.
let maxMergeSeverity = 1;
(function() {
  const cps = D.colkey_palettes || [];
  for (const cp of cps) { if (cp && cp.merge_severity > maxMergeSeverity) maxMergeSeverity = cp.merge_severity; }
})();
let selectedCell = null;
let issues = {};
let ready = false;

// pointer tracking
const pointers = new Map(); // pointerId -> {x,y}
let dragStartX = 0, dragStartY = 0, dragPanX = 0, dragPanY = 0;
let dragMoved = false;
let pinchRef = null; // {dist,zoom,midX,midY,panX,panY}

// ---- canvas ---------------------------------------------------------------
const canvas = document.getElementById('mapCanvas');
const ctx = canvas.getContext('2d');
const wrap = document.getElementById('canvas-wrap');
ctx.imageSmoothingEnabled = false;

function resizeCanvas() {
  canvas.width = wrap.clientWidth;
  canvas.height = wrap.clientHeight;
  render();
}
new ResizeObserver(resizeCanvas).observe(wrap);

// ---- coordinate helpers ---------------------------------------------------
function cellPx() { return 16 * zoom; }
function canvasToCell(cx, cy) {
  const cp = cellPx();
  return {x: Math.floor((cx - panX) / cp), y: Math.floor((cy - panY) / cp)};
}
function fitMap() {
  const m = D.meta;
  const sx = canvas.width  / (m.xsize * 16);
  const sy = canvas.height / (m.ysize * 16);
  zoom = Math.max(0.5, Math.min(4, Math.min(sx, sy)));
  panX = Math.floor((canvas.width  - m.xsize * cellPx()) / 2);
  panY = Math.floor((canvas.height - m.ysize * cellPx()) / 2);
  updateZoomDisplay();
  render();
}
function updateZoomDisplay() {
  document.getElementById('zoom-val').textContent =
    (zoom % 1 === 0 ? zoom : zoom.toFixed(1)) + 'x';
}

// ---- rendering ------------------------------------------------------------
function drawCellBase(cell, dx, dy, cp) {
  ctx.imageSmoothingEnabled = false;
  const lyr = currentLayer;
  if (lyr === 'rmxp') {
    for (const tid of cell.layers) { if (tid) drawImg(getTileURL(tid), dx, dy, cp); }
  } else if (lyr === 'l0' || lyr === 'l1' || lyr === 'l2') {
    const tid = cell.layers[parseInt(lyr[1])];
    if (tid) drawImg(getTileURL(tid), dx, dy, cp);
  } else if (lyr === 'gba') {
    drawImg(getMetatileURL(cell.colkey_idx, 'bottom'), dx, dy, cp);
    drawImg(getMetatileURL(cell.colkey_idx, 'top'),    dx, dy, cp);
  } else if (lyr === 'gba_bottom') {
    drawImg(getMetatileURL(cell.colkey_idx, 'bottom'), dx, dy, cp);
  } else if (lyr === 'gba_top') {
    drawImg(getMetatileURL(cell.colkey_idx, 'top'), dx, dy, cp);
  } else if (lyr === 'post-quant') {
    drawImg(getMetatileURL(cell.colkey_idx, 'post_bottom'), dx, dy, cp);
    drawImg(getMetatileURL(cell.colkey_idx, 'post_top'),    dx, dy, cp);
  }
}

function drawOverlayCell(cell, dx, dy, cp) {
  if (overlays.collision) {
    ctx.fillStyle = cell.collision_ours ? 'rgba(255,40,40,0.35)' : 'rgba(40,220,80,0.25)';
    ctx.fillRect(dx, dy, cp, cp);
  }
  if (overlays.diff && cell.mismatch) {
    ctx.strokeStyle = 'rgba(255,0,255,0.9)';
    ctx.lineWidth = Math.max(1, zoom);
    ctx.strokeRect(dx+1, dy+1, cp-2, cp-2);
  }
  if (overlays.priority && cell.priority_max > 0) {
    ctx.fillStyle = 'rgba(255,165,0,' + Math.min(0.85, cell.priority_max * 0.3) + ')';
    ctx.fillRect(dx, dy, cp, cp);
  }
  if (overlays.merge) {
    const cpal = (D.colkey_palettes || [])[cell.colkey_idx];
    const sev = cpal ? (cpal.merge_severity || 0) : 0;
    if (sev > 0) {
      // brightness scales with severity relative to this map's worst tile
      const a = 0.15 + 0.7 * Math.min(1, sev / maxMergeSeverity);
      ctx.fillStyle = 'rgba(255,40,200,' + a.toFixed(3) + ')';
      ctx.fillRect(dx, dy, cp, cp);
    }
  }
  const ik = cell.x + ',' + cell.y;
  if (issues[ik]) {
    ctx.fillStyle = 'rgba(255,120,0,0.5)'; ctx.fillRect(dx, dy, cp, cp);
    ctx.fillStyle = '#fa0';
    ctx.font = Math.max(8, cp-2) + 'px monospace';
    ctx.fillText('⚑', dx+1, dy+cp-1);
  }
  if (selectedCell && selectedCell.x === cell.x && selectedCell.y === cell.y) {
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = Math.max(1, zoom);
    ctx.strokeRect(dx+1, dy+1, cp-2, cp-2);
  }
}

function render() {
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = '#111118';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!ready) {
    ctx.fillStyle = '#5af'; ctx.font = '14px monospace';
    ctx.fillText('Loading…', 10, 30);
    return;
  }
  const cp = cellPx();
  const m = D.meta;
  for (let y = 0; y < m.ysize; y++) {
    const dy = panY + y * cp;
    if (dy + cp < 0 || dy >= canvas.height) continue;
    for (let x = 0; x < m.xsize; x++) {
      const dx = panX + x * cp;
      if (dx + cp < 0 || dx >= canvas.width) continue;
      drawCellBase(D.cells[y * m.xsize + x], dx, dy, cp);
    }
  }
  for (let y = 0; y < m.ysize; y++) {
    const dy = panY + y * cp;
    if (dy + cp < 0 || dy >= canvas.height) continue;
    for (let x = 0; x < m.xsize; x++) {
      const dx = panX + x * cp;
      if (dx + cp < 0 || dx >= canvas.width) continue;
      drawOverlayCell(D.cells[y * m.xsize + x], dx, dy, cp);
    }
  }
  const dotR = Math.max(3, Math.floor(cp / 5));
  ctx.save();
  ctx.font = Math.max(8, cp-4) + 'px monospace';
  for (const evt of D.events) {
    const dx = panX + evt.x * cp, dy = panY + evt.y * cp;
    if (dx+cp < 0 || dx >= canvas.width || dy+cp < 0 || dy >= canvas.height) continue;
    if (evt.is_warp && overlays.warps) {
      ctx.fillStyle = '#0ff';
      ctx.beginPath(); ctx.arc(dx+cp/2, dy+cp/2, dotR, 0, Math.PI*2); ctx.fill();
    } else if (!evt.is_warp && overlays.events) {
      ctx.fillStyle = '#ff0';
      ctx.beginPath(); ctx.arc(dx+cp/2, dy+cp/2, dotR, 0, Math.PI*2); ctx.fill();
    }
    if (overlays.events && cp >= 16) {
      ctx.fillStyle = '#fff';
      ctx.fillText(evt.name.slice(0,4), dx+1, dy+cp-2);
    }
  }
  ctx.restore();
}

// ---- pointer events (covers mouse + touch) --------------------------------
function ptrRect() { return canvas.getBoundingClientRect(); }
function ptDist(a, b) { return Math.hypot(b.x - a.x, b.y - a.y); }

canvas.addEventListener('pointerdown', function(e) {
  canvas.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
  if (pointers.size === 1) {
    dragStartX = e.clientX; dragStartY = e.clientY;
    dragPanX = panX; dragPanY = panY;
    dragMoved = false; pinchRef = null;
  } else if (pointers.size === 2) {
    const pts = [...pointers.values()];
    const rect = ptrRect();
    pinchRef = {
      dist: ptDist(pts[0], pts[1]),
      zoom: zoom, panX: panX, panY: panY,
      midX: (pts[0].x + pts[1].x) / 2 - rect.left,
      midY: (pts[0].y + pts[1].y) / 2 - rect.top,
    };
    dragMoved = true; // suppress tap on lift
  }
});

canvas.addEventListener('pointermove', function(e) {
  // status bar update (always, including mouse hover without button)
  if (pointers.size <= 1) {
    const rect = ptrRect();
    const {x, y} = canvasToCell(e.clientX - rect.left, e.clientY - rect.top);
    const m = D.meta;
    if (x >= 0 && x < m.xsize && y >= 0 && y < m.ysize) {
      document.getElementById('statusbar').textContent =
        'Map' + String(m.map_id).padStart(3,'0') + ' (' + x + ', ' + y + ')  tileset ' + m.tileset_id;
    }
  }
  if (!pointers.has(e.pointerId)) return;
  pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
  if (pointers.size === 1 && !pinchRef) {
    const ddx = e.clientX - dragStartX, ddy = e.clientY - dragStartY;
    if (Math.abs(ddx) > 4 || Math.abs(ddy) > 4) dragMoved = true;
    panX = dragPanX + ddx; panY = dragPanY + ddy;
    scheduleRender();
  } else if (pointers.size === 2 && pinchRef) {
    const pts = [...pointers.values()];
    const d = ptDist(pts[0], pts[1]);
    const newZoom = Math.max(0.5, Math.min(8, pinchRef.zoom * d / pinchRef.dist));
    const scale = (newZoom * 16) / (pinchRef.zoom * 16);
    panX = pinchRef.midX - (pinchRef.midX - pinchRef.panX) * scale;
    panY = pinchRef.midY - (pinchRef.midY - pinchRef.panY) * scale;
    zoom = newZoom;
    updateZoomDisplay(); scheduleRender();
  }
});

canvas.addEventListener('pointerup', function(e) {
  const wasTap = pointers.size === 1 && !dragMoved;
  const ex = e.clientX, ey = e.clientY;
  pointers.delete(e.pointerId);
  if (pointers.size === 0) pinchRef = null;
  if (wasTap) {
    const rect = ptrRect();
    const {x, y} = canvasToCell(ex - rect.left, ey - rect.top);
    const m = D.meta;
    if (x >= 0 && x < m.xsize && y >= 0 && y < m.ysize) {
      selectedCell = D.cells[y * m.xsize + x];
      updateSidebar();
      document.getElementById('btn-flag').disabled = false;
      scheduleRender();
      // open sidebar on mobile tap
      const sb = document.getElementById('sidebar');
      if (sb.style.position === 'fixed' || window.innerWidth <= 720) sb.classList.add('open');
    }
  }
});

canvas.addEventListener('pointercancel', function(e) {
  pointers.delete(e.pointerId);
  if (pointers.size === 0) pinchRef = null;
});

canvas.addEventListener('wheel', function(e) {
  e.preventDefault();
  const rect = ptrRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const oldCp = cellPx();
  const step = e.deltaY < 0 ? 0.5 : -0.5;
  const newZoom = Math.max(0.5, Math.min(8, Math.round((zoom + step) * 2) / 2));
  if (newZoom === zoom) return;
  const newCp = newZoom * 16;
  panX = mx - (mx - panX) * newCp / oldCp;
  panY = my - (my - panY) * newCp / oldCp;
  zoom = newZoom;
  updateZoomDisplay(); scheduleRender();
}, {passive: false});

// ---- toolbar controls -----------------------------------------------------
document.querySelectorAll('input[name="layer"]').forEach(function(r) {
  r.addEventListener('change', function() { currentLayer = r.value; scheduleRender(); });
});
// 2-way RPG-Maker <-> Quantized(family) toggle: drives the same `currentLayer` as the
// dormant per-layer radios above (values 'rmxp' / 'post-quant').
document.querySelectorAll('input[name="view2"]').forEach(function(r) {
  r.addEventListener('change', function() { currentLayer = r.value; scheduleRender(); });
});
/*KNOBBAR_JS*/
['collision','diff','priority','merge','events','warps'].forEach(function(name) {
  const el = document.getElementById('ov_' + name);
  el.addEventListener('change', function() { overlays[name] = el.checked; scheduleRender(); });
});
document.getElementById('zoom-in').onclick = function() {
  zoom = Math.min(8, Math.round((zoom + 0.5) * 2) / 2);
  updateZoomDisplay(); scheduleRender();
};
document.getElementById('zoom-out').onclick = function() {
  zoom = Math.max(0.5, Math.round((zoom - 0.5) * 2) / 2);
  updateZoomDisplay(); scheduleRender();
};
document.getElementById('zoom-fit').onclick = fitMap;

// ---- sidebar toggle (mobile) ----------------------------------------------
document.getElementById('sidebar-toggle').onclick = function() {
  document.getElementById('sidebar').classList.toggle('open');
};

// ---- cell inspector sidebar -----------------------------------------------
// ---- palette/swatch helpers -----------------------------------------------
let showAllColorChanges = false;

function swatchTitle(c) {
  const r = c[0], g = c[1], b = c[2];
  const hex = '#' + [r,g,b].map(function(v){return v.toString(16).padStart(2,'0');}).join('').toUpperCase();
  const r5 = r>>3, g5 = g>>3, b5 = b>>3;
  const bgr555 = (b5<<10)|(g5<<5)|r5;
  return 'rgb(' + r + ',' + g + ',' + b + ')  ' + hex + '  BGR555: 0x' + bgr555.toString(16).toUpperCase().padStart(4,'0') + ' (' + r5 + ',' + g5 + ',' + b5 + ')';
}
function swatchHtml(c) {
  const hex = '#' + c.map(function(v){return v.toString(16).padStart(2,'0');}).join('');
  return '<span class="swatch" style="background:' + hex + '" title="' + swatchTitle(c) + '"></span>';
}
function buildCCRows(colorChanges, showAll) {
  let h = '';
  for (const cc of colorChanges) {
    const orig = cc[0], final = cc[1];
    const changed = orig[0] !== final[0] || orig[1] !== final[1] || orig[2] !== final[2];
    if (!showAll && !changed) continue;
    h += '<div class="cc-row' + (changed ? ' changed' : '') + '">';
    h += swatchHtml(orig);
    h += '<span class="cc-arrow">&rarr;</span>';
    h += swatchHtml(final);
    h += '<span class="' + (changed ? 'cc-tag-changed' : 'cc-tag-same') + '">' + (changed ? 'changed' : 'same') + '</span>';
    h += '</div>';
  }
  if (!h) h = '<span class="lbl">' + (showAll ? '(none)' : '(no changes)') + '</span>';
  return h;
}
function updateCCSection() {
  const el = document.getElementById('cc-section');
  if (!el || !selectedCell) return;
  const ckPal = D.colkey_palettes ? D.colkey_palettes[selectedCell.colkey_idx] : null;
  if (!ckPal) return;
  const ccId = 'cc_toggle_' + selectedCell.x + '_' + selectedCell.y;
  const cb = document.getElementById(ccId);
  if (cb) showAllColorChanges = cb.checked;
  el.innerHTML = buildCCRows(ckPal.color_changes, showAllColorChanges);
}

function thumbHtml(url, label) {
  if (!url) return '<span class="lbl">[no img]</span>';
  return '<img class="thumb" src="' + url + '" title="' + label + '" loading="lazy">';
}
// Per-8x8-quadrant palette fit: how many of a quadrant's source colours had to be
// merged (snapped to a different palette colour) to fit its 15-colour sub-palette.
function quadFitHtml(cpal) {
  if (!cpal || !cpal.quadrant_fit || !cpal.quadrant_fit.length) return '';
  let h = '<div class="lbl" style="margin-top:5px">Palette fit (per 8&times;8 quadrant):</div>';
  for (const q of cpal.quadrant_fit) {
    const loc = (q.slot < 4 ? 'B' : 'T') + (q.slot % 4);  // Bottom/Top quadrant 0-3
    let cls = 'qfit-ok';
    if (q.merged > 0) cls = (q.max_shift >= 3 || q.merged >= 6) ? 'qfit-bad' : 'qfit-warn';
    const detail = q.merged > 0
      ? (q.merged + '/' + q.n + ' merged, &Delta;&le;' + q.max_shift)
      : (q.n + ' colours fit');
    h += '<div class="qfit ' + cls + '"><b>' + loc + '</b> pal' + q.pal + ' &middot; ' + detail + '</div>';
  }
  if (cpal.merge_colors > 0) {
    h += '<div class="lbl" style="margin-top:3px">metatile: <span class="qfit-bad-txt">' +
      cpal.merge_colors + ' colours merged</span>, severity ' + cpal.merge_severity + '</div>';
  } else {
    h += '<div class="lbl" style="margin-top:3px"><span class="qfit-ok-txt">no merge loss</span> (truncation only)</div>';
  }
  return h;
}
function passageStr(p) {
  if (!p) return '0x00 (open)';
  if ((p & 0x0F) === 0x0F) return '0x0F (blocked)';
  const dirs = [];
  if (p & 1) dirs.push('D'); if (p & 2) dirs.push('L');
  if (p & 4) dirs.push('R'); if (p & 8) dirs.push('U');
  return '0x' + p.toString(16).padStart(2,'0') + ' (' + (dirs.join(',') || 'open') + ')';
}

function updateSidebar() {
  if (!selectedCell) return;
  const cell = selectedCell;
  const m = D.meta;
  const ck_str = D.colkeys_list ? D.colkeys_list[cell.colkey_idx] : '';
  const attrs = D.metatile_attrs ? D.metatile_attrs[cell.colkey_idx] : null;
  const ik = cell.x + ',' + cell.y;
  const hasIssue = !!issues[ik];
  let html = '';
  html += '<div class="section-title">Cell (' + cell.x + ', ' + cell.y + ')</div>';
  html += '<div class="lbl">Tileset ' + m.tileset_id + ': ' + m.name + ' / ' + m.tileset_name + '</div>';
  if (hasIssue) html += '<div style="color:#fa0">&#9873; Flagged: ' + (issues[ik].note || '') + '</div>';

  html += '<div class="section-title">RMXP Layers</div>';
  if (cell.layer_detail.length === 0) {
    html += '<div class="lbl">(empty cell)</div>';
  } else {
    for (const ld of cell.layer_detail) {
      html += '<div class="layer-row">';
      html += thumbHtml(getTileURL(ld.tile_id), 'tile ' + ld.tile_id);
      html += '<div>';
      html += '<div><span class="lbl">L' + ld.z + ' tid</span> <span class="val">' + ld.tile_id + '</span>';
      if (ld.autotile_name) html += ' <span class="lbl">(' + ld.autotile_name + ')</span>';
      html += '</div>';
      html += '<div><span class="lbl">pass</span> <span class="val">' + passageStr(ld.passage) + '</span></div>';
      html += '<div><span class="lbl">pri</span> <span class="val">' + ld.priority + '</span> ';
      html += '<span class="lbl">terrain</span> <span class="val">' + ld.terrain + '</span></div>';
      html += '</div></div>';
    }
  }

  html += '<div class="section-title">GBA Metatile</div>';
  html += '<div class="lbl">Column key: <code style="font-size:10px">' + ck_str + '</code></div>';
  if (ck_str && ck_str !== '[]') {
    html += '<div class="layer-row">';
    html += '<div>';
    html += '<div class="lbl">raw (pre-quant) &#8595;/&#8593;</div>';
    html += '<div class="thumb-pair">';
    html += thumbHtml(getMetatileURL(cell.colkey_idx, 'bottom'), 'raw bottom');
    html += thumbHtml(getMetatileURL(cell.colkey_idx, 'top'), 'raw top');
    html += '</div>';
    html += '<div class="lbl" style="margin-top:4px">post-quant (shipped) &#8595;/&#8593;</div>';
    html += '<div class="thumb-pair">';
    html += thumbHtml(getMetatileURL(cell.colkey_idx, 'post_bottom'), 'post-quant bottom');
    html += thumbHtml(getMetatileURL(cell.colkey_idx, 'post_top'), 'post-quant top');
    html += '</div>';
    html += '</div>';
    if (attrs) {
      html += '<div style="padding-left:8px">';
      html += '<div><span class="lbl">layer_type</span> <span class="val">' + attrs.layer_type + '</span></div>';
      html += '<div><span class="lbl">behavior</span> <span class="val">0x' + attrs.behavior.toString(16) + '</span></div>';
      html += '</div>';
    }
    html += '</div>';
    html += quadFitHtml(D.colkey_palettes ? D.colkey_palettes[cell.colkey_idx] : null);
  } else {
    html += '<div class="lbl">(void / no metatile)</div>';
  }

  html += '<div class="section-title">Collision</div>';
  html += '<div><span class="lbl">Ours: </span><span class="' + (cell.collision_ours ? 'blocked' : 'passable') + '">' + (cell.collision_ours ? 'BLOCKED' : 'passable') + '</span></div>';
  html += '<div><span class="lbl">Uranium: </span><span class="' + (cell.collision_uranium ? 'blocked' : 'passable') + '">' + (cell.collision_uranium ? 'BLOCKED' : 'passable') + '</span></div>';
  html += cell.mismatch ? '<div class="mismatch">&#9888; MISMATCH</div>' : '<div class="match">&#10003; Match</div>';
  html += '<div><span class="lbl">priority_max</span> <span class="val">' + cell.priority_max + '</span></div>';

  const evtsHere = D.events.filter(function(ev) { return ev.x === cell.x && ev.y === cell.y; });
  if (evtsHere.length > 0) {
    html += '<div class="section-title">Events</div>';
    for (const ev of evtsHere) {
      html += '<div><span class="lbl">' + ev.id + ': </span><span class="val">' + ev.name + '</span>';
      html += ' <span class="lbl">(' + ev.npages + 'p' + (ev.is_warp ? ', warp' : '') + ')</span></div>';
    }
  }

  // ---- Palettes section ----
  const ckPal = D.colkey_palettes ? D.colkey_palettes[cell.colkey_idx] : null;
  if (ck_str && ck_str !== '[]') {
    html += '<div class="section-title">Palettes</div>';

    // RMXP source colors: union of tile colors from this cell's layer_detail
    const rmxpColors = [];
    const rmxpSeen = new Set();
    if (D.rmxp_tile_colors) {
      for (const ld of cell.layer_detail) {
        const tColors = D.rmxp_tile_colors[String(ld.tile_id)] || [];
        for (const c of tColors) {
          const k = c.join(',');
          if (!rmxpSeen.has(k)) { rmxpSeen.add(k); rmxpColors.push(c); }
        }
      }
    }
    html += '<div class="lbl" style="margin-top:4px">RMXP source colors</div>';
    html += '<div class="pal-strip">';
    for (const c of rmxpColors) html += swatchHtml(c);
    if (!rmxpColors.length) html += '<span class="lbl">(none)</span>';
    html += '</div>';

    // GBA sub-palettes used by this metatile
    if (ckPal && ckPal.palette_indices.length > 0 && D.palettes) {
      html += '<div class="lbl" style="margin-top:4px">GBA sub-palettes</div>';
      for (const pi of ckPal.palette_indices) {
        const pal = D.palettes[pi] || [];
        html += '<div style="margin:2px 0;display:flex;align-items:center;flex-wrap:wrap">';
        html += '<span class="pal-label">Pal ' + pi + '</span>';
        html += '<span class="swatch swatch-checker" title="index 0 (transparent)"></span>';
        for (const c of pal) html += swatchHtml(c);
        html += '</div>';
      }
    }

    // Color changes
    if (ckPal && ckPal.color_changes.length > 0) {
      const ccId = 'cc_toggle_' + cell.x + '_' + cell.y;
      const nChanged = ckPal.color_changes.filter(function(cc){return cc[0][0]!==cc[1][0]||cc[0][1]!==cc[1][1]||cc[0][2]!==cc[1][2];}).length;
      html += '<div class="lbl" style="margin-top:4px;display:flex;align-items:center;gap:6px">';
      html += 'Color changes (' + nChanged + '/' + ckPal.color_changes.length + ')';
      html += '<label style="font-size:10px;cursor:pointer"><input type="checkbox" id="' + ccId + '" onchange="updateCCSection()"' + (showAllColorChanges ? ' checked' : '') + '> show all</label>';
      html += '</div>';
      html += '<div id="cc-section">';
      html += buildCCRows(ckPal.color_changes, showAllColorChanges);
      html += '</div>';
    } else if (ckPal) {
      html += '<div class="lbl" style="margin-top:2px">(no color changes)</div>';
    }
  }

  document.getElementById('cell-info').innerHTML = html;
}

// ---- issue annotation -----------------------------------------------------
document.getElementById('btn-flag').onclick = function() {
  if (!selectedCell) return;
  const area = document.getElementById('note-area');
  area.style.display = area.style.display === 'none' ? 'block' : 'none';
};
document.getElementById('btn-note-save').onclick = function() {
  if (!selectedCell) return;
  const note = document.getElementById('note-text').value.trim();
  const key = selectedCell.x + ',' + selectedCell.y;
  issues[key] = {x: selectedCell.x, y: selectedCell.y, note: note};
  document.getElementById('note-text').value = '';
  document.getElementById('note-area').style.display = 'none';
  updateIssueList(); updateSidebar(); scheduleRender();
};
document.getElementById('btn-note-cancel').onclick = function() {
  document.getElementById('note-area').style.display = 'none';
  document.getElementById('note-text').value = '';
};
document.getElementById('btn-export').onclick = function() {
  const blob = new Blob([JSON.stringify(Object.values(issues), null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'Map' + String(D.meta.map_id).padStart(3,'0') + '_issues.json';
  a.click();
  URL.revokeObjectURL(url);
};
function updateIssueList() {
  const el = document.getElementById('issue-list');
  const arr = Object.values(issues);
  if (!arr.length) { el.innerHTML = '<span class="lbl">No issues.</span>'; return; }
  el.innerHTML = arr.map(function(i) {
    return '<div class="issue-item">(' + i.x + ',' + i.y + ') ' + (i.note || '') +
      ' <span class="issue-del" onclick="deleteIssue(\'' + i.x + ',' + i.y + '\')">&#10005;</span></div>';
  }).join('');
}
function deleteIssue(key) { delete issues[key]; updateIssueList(); scheduleRender(); }

// ---- worst-merge ranking --------------------------------------------------
let worstBuilt = false;
function buildWorstList() {
  const el = document.getElementById('merge-list');
  const cps = D.colkey_palettes || [];
  const ranked = [];
  for (let i = 0; i < cps.length; i++) {
    const cp = cps[i];
    if (cp && cp.merge_severity > 0) ranked.push({idx: i, sev: cp.merge_severity, merged: cp.merge_colors});
  }
  ranked.sort(function(a, b) { return b.sev - a.sev; });
  const top = ranked.slice(0, 20);
  if (!top.length) { el.innerHTML = '<span class="lbl">No palette-merge loss on this map.</span>'; return; }
  let h = '';
  for (const r of top) {
    const url = getMetatileURL(r.idx, 'post_bottom');
    h += '<div class="merge-item" onclick="jumpToColkey(' + r.idx + ')" title="jump to a tile using this metatile">';
    h += (url ? '<img class="thumb" src="' + url + '" loading="lazy">' : '');
    h += '<span class="lbl">sev <b class="qfit-bad-txt">' + r.sev + '</b> &middot; ' + r.merged + ' merged</span>';
    h += '</div>';
  }
  el.innerHTML = h;
}
function jumpToColkey(idx) {
  let target = null;
  for (const c of D.cells) { if (c.colkey_idx === idx) { target = c; break; } }
  if (!target) return;
  selectedCell = target;
  const cp = cellPx();
  panX = Math.floor(canvas.width / 2 - (target.x + 0.5) * cp);
  panY = Math.floor(canvas.height / 2 - (target.y + 0.5) * cp);
  document.getElementById('btn-flag').disabled = false;
  updateSidebar();
  scheduleRender();
  const sb = document.getElementById('sidebar');
  if (sb.style.position === 'fixed' || window.innerWidth <= 720) sb.classList.add('open');
}
document.getElementById('merge-head').onclick = function() {
  const list = document.getElementById('merge-list');
  const open = list.style.display === 'none';
  if (open && !worstBuilt) { buildWorstList(); worstBuilt = true; }
  list.style.display = open ? 'block' : 'none';
  document.getElementById('merge-tri').innerHTML = open ? '&#9662;' : '&#9656;';
};

// ---- static preload -------------------------------------------------------
function preloadStatic() {
  const uris = [];
  for (const uri of Object.values(V.tile_images || {})) uris.push(uri);
  for (const m of Object.values(V.metatile_images || {})) { uris.push(m.bottom); uris.push(m.top); }
  if (!uris.length) {
    ready = true;
    requestAnimationFrame(function() { canvas.width = wrap.clientWidth; canvas.height = wrap.clientHeight; fitMap(); });
    return;
  }
  let done = 0;
  function onOne() {
    done++;
    if (done >= uris.length) {
      ready = true;
      canvas.width = wrap.clientWidth; canvas.height = wrap.clientHeight;
      fitMap();
    }
  }
  for (const uri of uris) {
    imgCache.set(uri, 'loading');
    const img = new Image();
    img.onload = function() { imgCache.set(uri, img); onOne(); };
    img.onerror = function() { imgCache.set(uri, 'err'); onOne(); };
    img.src = uri;
  }
}

// ---- map nav strip (server mode only; populated from V.graph) --------------
function renderMapNav() {
  const nav = document.getElementById('mapnav');
  if (!nav) return;
  const g = V.graph;
  if (V.mode !== 'server' || !g) { nav.classList.remove('show'); return; }
  const pad = function(n){ return String(n).padStart(3,'0'); };
  const esc = function(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };
  const chip = function(id, name){
    return '<a class="navchip" href="/map/' + id + '" title="Map' + pad(id) + '">M' + pad(id) + ' ' + esc(name) + '</a>';
  };
  let h = '<a class="navchip home" href="/" title="Map index">&#8962; Index</a><span class="navsep"></span>';
  h += '<span class="navcur">Map' + pad(g.id) + ' &middot; ' + esc(g.name) + '</span>';
  const seen = new Set([g.id]);
  if (g.parent) { h += '<span class="navsep"></span><span class="navgrp">up</span>' + chip(g.parent.id, g.parent.name); seen.add(g.parent.id); }
  const kids = (g.children || []).filter(function(c){ return !seen.has(c.id); });
  if (kids.length) { h += '<span class="navsep"></span><span class="navgrp">sub</span>'; kids.forEach(function(c){ seen.add(c.id); h += chip(c.id, c.name); }); }
  const warps = (g.warps || []).filter(function(w){ return !seen.has(w.id); });
  if (warps.length) { h += '<span class="navsep"></span><span class="navgrp">warp&rarr;</span>'; warps.forEach(function(w){ seen.add(w.id); h += chip(w.id, w.name); }); }
  nav.innerHTML = h;
  nav.classList.add('show');
}

// ---- init -----------------------------------------------------------------
(function init() {
  const m = D.meta;
  document.title = 'Map Inspector — Map' + String(m.map_id).padStart(3,'0');
  document.getElementById('map-title').textContent =
    'Map' + String(m.map_id).padStart(3,'0') + ' — ' + (m.name || '') +
    ' (' + m.xsize + '\xd7' + m.ysize + ')';
  document.getElementById('statusbar').textContent =
    'Map' + String(m.map_id).padStart(3,'0') + ' — ' + m.xsize + '\xd7' + m.ysize +
    ' cells, tileset ' + m.tileset_id + ' (' + m.tileset_name + ')';
  updateIssueList();
  // merge-panel count: how many distinct metatiles on this map lose colour to merging
  const mergeN = (D.colkey_palettes || []).filter(function(cp) { return cp && cp.merge_severity > 0; }).length;
  document.getElementById('merge-count').textContent = '(' + mergeN + ' tiles)';
  renderMapNav();
  if (V.mode === 'server') {
    const navp = document.getElementById('nav-palettes');
    navp.href = '/palettes/' + m.map_id;
    navp.style.display = '';
  }
  if (V.mode === 'static') {
    preloadStatic();
  } else {
    ready = true;
    setTimeout(function() { canvas.width = wrap.clientWidth; canvas.height = wrap.clientHeight; fitMap(); }, 0);
  }
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Shared knob-panel JS (injected into both MAP_VIEWER_HTML and PALETTE_VIEWER_HTML at
# the `/*KNOBBAR_JS*/` token). Server mode only — the panel hides itself otherwise,
# since live re-quantization needs the Python packer. Apply POSTs the knobs and, on
# success, reloads: the reload re-renders the map + palette views from fresh state and
# carries the new generation token that busts the post-quant image cache.
# ---------------------------------------------------------------------------
KNOBBAR_JS = r"""
(function(){
  var kb = document.getElementById('knobbar');
  if (!kb) return;
  if (V.mode !== 'server') { kb.style.display = 'none'; return; }
  var q = V.quant || {};
  var setv = function(id, val){ var e = document.getElementById(id); if (e != null && val != null) e.value = val; };
  setv('k_green', (q.green_cuts || []).join(','));
  setv('k_dark', q.dark_value);
  setv('k_neutral', q.neutral_sat);
  setv('k_floor', q.palette_floor);
  setv('k_maxpal', q.max_palettes);
  var ov = document.getElementById('k_overflow'); if (ov && q.overflow_weight) ov.value = q.overflow_weight;
  var apply = document.getElementById('k_apply');
  var status = document.getElementById('k_status');
  apply.addEventListener('click', function(){
    var greens = (document.getElementById('k_green').value || '').split(',')
      .map(function(s){ return parseFloat(s.trim()); }).filter(function(n){ return !isNaN(n); });
    var body = {
      map_id: D.meta.map_id,
      green_cuts: greens,
      dark_value: parseInt(document.getElementById('k_dark').value, 10),
      neutral_sat: parseFloat(document.getElementById('k_neutral').value),
      palette_floor: parseInt(document.getElementById('k_floor').value, 10),
      overflow_weight: document.getElementById('k_overflow').value,
      max_palettes: parseInt(document.getElementById('k_maxpal').value, 10)
    };
    status.textContent = 're-quantizing…'; apply.disabled = true;
    fetch('/api/quantize', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) })
      .then(function(r){ return r.text().then(function(t){ return { ok:r.ok, t:t }; }); })
      .then(function(res){
        if (!res.ok) {
          var msg = res.t; try { msg = JSON.parse(res.t).error || res.t; } catch (e) {}
          status.textContent = 'error: ' + msg; apply.disabled = false; return;
        }
        location.reload();  // re-render map + palettes from fresh state (new generation busts image cache)
      })
      .catch(function(e){ status.textContent = 'error: ' + e; apply.disabled = false; });
  });
})();
"""

MAP_VIEWER_HTML = MAP_VIEWER_HTML.replace("/*KNOBBAR_JS*/", KNOBBAR_JS)
