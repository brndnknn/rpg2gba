# ruff: noqa: E501
"""Shared data-extraction and rendering core for the Uranium map viewer.

Drives the lazy server (map_viewer_server.py).  Module-level caches keep per-map
rasterizer state alive so repeated tile/metatile requests from the server don't
rebuild from scratch.  The web pages themselves live as real files under
scripts/map_viewer/ and are assembled into MAP_VIEWER_HTML / PALETTE_VIEWER_HTML
at import (see the bottom of this module).
"""
from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.graphics.autotile import autotile_frame_count
from rpg2gba.tileset_converter.graphics.build_slice_tilesets import (
    _render_column,
    column_keys_for_maps,
    column_n_frames,
)
from rpg2gba.tileset_converter.graphics.emit import (
    MetatileImage,
    PaletteAnalysis,
    analyze_tileset_palettes,
)
from rpg2gba.tileset_converter.graphics.quantize import (
    FamilyParams,
    build_quantized_tileset_family,
)
from rpg2gba.tileset_converter.graphics.raster import TileRasterizer, column_in_atlas
from rpg2gba.tileset_converter.graphics.sources import (
    load_tileset_sources,
    tileset_source_paths,
)
from rpg2gba.tileset_converter.graphics.sprites import convert_character_sheet
from rpg2gba.tileset_converter.layout import TileGrid, column_key, mask_out_of_atlas
from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS
from rpg2gba.tileset_converter.sprite_pass import _characters_dir, _resolve_sheet
from rpg2gba.tileset_converter.tile_map import serialize_column_key

sys.path.insert(0, str(Path(__file__).parent))
from compare_collision import our_blocked, uranium_blocked  # noqa: E402

log = logging.getLogger(__name__)

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


def _file_fingerprint(path: Path) -> tuple[int, int]:
    """(mtime_ns, size) for cheap staleness detection — stat only, no read/parse.
    ``(-1, -1)`` if the file is missing (so a just-created or just-deleted file
    always compares unequal to any prior fingerprint)."""
    try:
        st = path.stat()
    except OSError:
        return (-1, -1)
    return (st.st_mtime_ns, st.st_size)


def _json_fingerprint(map_id: int) -> tuple[tuple[int, int], ...]:
    """Stat-only fingerprint of the JSON inputs that can change *map_id*'s
    rendered output at the data level: its own ``Map{NNN}.json``,
    ``tilesets.json``, and — for slice maps — every ``SLICE_MAP_IDS`` sibling's
    ``Map{NNN}.json`` too, since a sibling can join or leave this map's
    quantization pool without this map's own file changing (see
    ``_ensure_tileset_analysis``).

    A superset of what ``_derive_png_paths_for_map`` itself reads (that
    function only needs *map_id*'s own json — see its docstring for why pool
    siblings never add a distinct tileset), but it's safe and convenient to
    reuse this broader fingerprint as that derivation's memoization key too
    (see ``_slice_aware_fingerprint`` below): a sibling-json change some
    unrelated tileset never touches would just cost one extra cache-miss
    re-derivation, not an incorrect result."""
    maps_dir = _maps_dir()
    paths = [maps_dir / f"Map{map_id:03d}.json"]
    if map_id in SLICE_MAP_IDS:
        paths += [maps_dir / f"Map{m:03d}.json" for m in SLICE_MAP_IDS if m != map_id]
    paths.append(_tilesets_json())
    return tuple(_file_fingerprint(p) for p in paths)


# map_id -> (json_fingerprint at derivation time, derived tileset-PNG path tuple).
# Deriving the PNG path list requires parsing map JSON + tilesets.json — too
# expensive to redo on every request — so _slice_aware_fingerprint only re-derives
# it when a fresh _json_fingerprint(map_id) no longer matches the cached key.
# Never evicted: the map count is small and bounded (the corpus), and a stale
# entry can never be served since the key comparison guards correctness, not
# just an optimization.
_png_paths_cache: dict[int, tuple[tuple[tuple[int, int], ...], tuple[Path, ...]]] = {}


def _derive_png_paths_for_map(
    map_id: int,
    *,
    maps_dir: Path,
    tilesets_json_path: Path,
    graphics_dir: Path | None = None,
) -> tuple[Path, ...]:
    """Pure(ish) derivation of every tileset source-PNG path *map_id*'s rendering
    depends on: the sheet + non-empty autotile PNGs of *map_id*'s own
    ``tileset_id``.

    Only *map_id*'s own tileset is resolved — even for slice maps, deliberately
    NOT every ``SLICE_MAP_IDS`` sibling's tileset. ``_ensure_tileset_analysis``
    (~line 394) pools a slice sibling into *map_id*'s shared quantization only
    when the sibling's CURRENT ``tileset_id`` is an EXACT match to *map_id*'s
    own; every pool member therefore shares the identical ``tileset_name`` and
    PNGs by construction, so "the pool siblings' tileset PNGs" collapses to
    this same single tileset — there's nothing distinct left to resolve. A
    sibling with a genuinely different ``tileset_id`` is, by definition, not
    in the pool, so its source art has zero effect on *map_id*'s render and is
    correctly excluded. (Sibling json *changes*, which could shift pool
    membership, are still caught independently — ``_json_fingerprint`` watches
    every ``SLICE_MAP_IDS`` sibling's json unconditionally, regardless of this
    function.)

    Takes explicit ``maps_dir`` / ``tilesets_json_path`` / ``graphics_dir``
    params rather than reading the module's env-derived state directly, so
    tests can point this at a ``tmp_path`` tree without monkeypatching global
    state. ``graphics_dir=None`` mirrors ``load_tileset_sources``'s own default
    (env-derived via ``default_graphics_dir()``), and — like
    ``tileset_source_paths`` itself — degrades to no PNG entries rather than
    raising if that env var is unset.

    Degrades to ``()`` at every failure point (unreadable/malformed map JSON, a
    missing ``tileset_id`` key, or — via ``tileset_source_paths`` — a missing
    tilesets.json entry or unset graphics dir) rather than raising: this is
    fingerprinting only, and an under-covering fingerprint is far better than a
    viewer that won't start. The real load path (``_ensure_loaded`` /
    ``load_tileset_sources``) still fails loud with a precise error."""
    try:
        doc = json.loads((maps_dir / f"Map{map_id:03d}.json").read_text(encoding="utf-8"))
        tileset_id = int(doc["tileset_id"])
    except (OSError, ValueError, KeyError, TypeError):
        return ()

    return tuple(
        tileset_source_paths(
            tileset_id, tilesets_json=tilesets_json_path, graphics_dir=graphics_dir
        )
    )


def _slice_aware_fingerprint(map_id: int) -> tuple[tuple[int, int] | tuple[str, int, int], ...]:
    """Stat-only fingerprint of every on-disk input that can change *map_id*'s
    rendered output — JSON inputs AND their tileset source-art PNGs.

    Two halves, concatenated:

    1. ``_json_fingerprint(map_id)``: the map's own ``Map{NNN}.json``,
       ``tilesets.json``, and (for slice maps) every sibling's json — each a
       ``(mtime_ns, size)`` pair.
    2. The tileset source PNGs (sheet + autotiles) map_id's own tileset depends
       on (see ``_derive_png_paths_for_map`` for why pool siblings never add a
       distinct tileset here). Each entry is ``(str(path), mtime_ns, size)``:
       the path string is included, not just the stat, so a changed PNG *path
       set* (e.g. tilesets.json renaming an autotile) is caught even when
       stats happen to coincide (e.g. two same-sized files).

    Deriving the PNG path list needs parsing map JSON(s) + tilesets.json, so it's
    memoized in ``_png_paths_cache`` and only recomputed when a fresh
    ``_json_fingerprint`` no longer matches the cached key. Steady-state
    per-request cost is then stat()-ing the JSONs (already happening) plus
    stat()-ing the PNGs — no re-parsing — so this stays cheap enough to call on
    every request, unlike actually resolving the tileset-analysis pool
    (``_ensure_tileset_analysis``)."""
    json_fp = _json_fingerprint(map_id)

    cached = _png_paths_cache.get(map_id)
    if cached is not None and cached[0] == json_fp:
        png_paths = cached[1]
    else:
        png_paths = _derive_png_paths_for_map(
            map_id, maps_dir=_maps_dir(), tilesets_json_path=_tilesets_json()
        )
        _png_paths_cache[map_id] = (json_fp, png_paths)

    png_fp = tuple((str(p),) + _file_fingerprint(p) for p in png_paths)
    return json_fp + png_fp


def _feedback_path(map_id: int) -> Path:
    """Per-map tile-feedback file. Lives under version-controlled reference/ (NOT
    gitignored output/): flags are hand-authored review data, not regenerable
    output, so they must survive `rm -rf output/` / `pipeline --clean`."""
    d = _repo_root() / "reference" / "map_feedback"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"Map{map_id:03d}.json"


def _export_path(map_id: int) -> Path:
    """Where the viewer's "Export JSON" button drops a snapshot, server-side.

    Distinct from _feedback_path(): that's the live, version-controlled review data;
    this is a regenerable dump, so it lands under output/ per CLAUDE.md §4.4."""
    d = _output_base() / "map_feedback"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"Map{map_id:03d}_feedback.json"


def export_feedback(map_id: int, flags: list[dict]) -> Path:
    """Write a flag-list snapshot to output/map_feedback/ and return the path."""
    path = _export_path(map_id)
    path.write_text(
        json.dumps(flags, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def load_feedback(map_id: int) -> list[dict]:
    """This map's tile-feedback flags (empty list if none saved yet).

    Schema: a list of grouped flags, each ``{"cells": [[x, y], ...], "note": str}``.
    One flag covers a whole selection set (built by tap-to-toggle + expand-similar),
    so a single note can span many cells / several metatile identities."""
    path = _feedback_path(map_id)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def save_feedback(map_id: int, flags: list[dict]) -> None:
    """Persist this map's flags, overwriting the file whole (the set per map is
    always tiny, so a full rewrite per save/delete is fine)."""
    _feedback_path(map_id).write_text(
        json.dumps(flags, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


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
    animated_slots: set[int]        # autotile slots (0..6) with a multi-frame source PNG
    tileset_id: int
    ts_name: str
    ts_tileset_name: str
    map_width: int
    map_height: int
    events_raw: list
    masked_cells: list[tuple[int, int, int, int]]  # (x, y, z, orig_tile_id) zeroed by mask_out_of_atlas
    colkeys_sorted: list[tuple]           # stable-sorted column-key tuples
    colkey_to_idx: dict[tuple, int]       # tuple -> index in colkeys_sorted
    metatile_imgs: list[MetatileImage | None]  # indexed by colkey idx; None = empty col
    pix_class: list[int]                  # colkey idx -> smallest colkey idx rendering pixel-identical (see _pixel_classes)
    metatile_imgs_postquant: list[tuple[np.ndarray, np.ndarray] | None]  # aligned with metatile_imgs; None = empty col
    analysis: PaletteAnalysis             # slice-scoped palette analysis for this map's tileset
    pool_key_to_idx: dict[tuple, int]     # column key -> index into analysis.metatiles
    quant_generation: int                 # _quant_generation the postquant fields were built at
    # _slice_aware_fingerprint at load time; each element is either a JSON stat
    # pair (mtime_ns, size) or a PNG stat triple (str(path), mtime_ns, size).
    input_fingerprint: tuple[tuple[int, int] | tuple[str, int, int], ...]


_map_cache: dict[int, _MapState] = {}
_tile_png_cache: dict[tuple[int, int], bytes] = {}          # (map_id, tile_id)
_metatile_png_cache: dict[tuple[int, int, str], bytes] = {}  # (map_id, idx, layer)
_npc_png_cache: dict[str, bytes] = {}                        # character_name.lower() -> PNG
# key: (pool map-id set, fingerprint of every pooled map's json + tilesets.json) ->
# (analysis, pool_key_to_idx). The fingerprint half means a rebuild that changes a
# pooled map's content invalidates the entry even if the pool's *membership*
# (the frozenset) didn't change.
_tileset_analysis_cache: dict[
    tuple[frozenset[int], tuple[tuple[int, int], ...]],
    tuple[PaletteAnalysis, dict[tuple, int]],
] = {}


# ---------------------------------------------------------------------------
# Live quantization knobs
# ---------------------------------------------------------------------------
# The "Quantized" view uses the FAMILY packer; its parameters are tunable at runtime
# from the browser (POST /api/quantize) so the foliage/interior trade-offs can be A/B'd
# without re-running the pipeline.  Default FamilyParams() == the family packer's stock
# behavior.  Changing params invalidates the three quant-dependent caches (the RMXP
# source-tile cache is param-independent and kept).  `_quant_generation` is a monotonic
# token the client appends to ALL image URLs to defeat the browser's immutable cache
# after an Apply or a disk reload.  It is seeded from the clock, NOT 0: the PNGs are
# served `immutable` with the token as the only cache-buster, so the token must never
# repeat across process lifetimes — a constant seed made every launch (incl. the
# source-watch self-restarts) re-serve whatever bytes the browser cached under the
# same low generation in an earlier lifetime, forever (PROJECT_TODO #13).  Millisecond
# resolution so per-lifetime `+= 1` bumps can't catch up to a later lifetime's seed;
# still far below JS's 2^53 (nanoseconds would NOT survive the JSON→double round-trip).
_ENGINE_MAX_PALS = 13  # NUM_PALS_TOTAL — hardware/engine ceiling; knob can only lower it
_family_params: FamilyParams = FamilyParams()
_max_palettes: int = _ENGINE_MAX_PALS
_quant_generation: int = int(time.time() * 1000)


def _make_quantizer():
    """Current packer as a ``(tiles, *, max_palettes) -> QuantizeResult`` callable."""
    return partial(build_quantized_tileset_family, params=_family_params)


def current_quantize_state() -> tuple[FamilyParams, int]:
    """Live (params, max_palettes) — for snapshot/rollback by the server."""
    return _family_params, _max_palettes


def get_quantize_params() -> dict:
    """Current knob state for injection into the page config (seeds the UI + the
    `generation` cache-bust token). `non_stock` is True when the live knobs differ
    from stock (`FamilyParams()` defaults, `max_palettes == _ENGINE_MAX_PALS`) —
    drives the always-visible (non-Advanced-gated) toolbar warning badge."""
    return {
        "generation": _quant_generation,
        "max_palettes": _max_palettes,
        "non_stock": _family_params != FamilyParams() or _max_palettes != _ENGINE_MAX_PALS,
        "dark_value": _family_params.dark_value,
        "neutral_sat": _family_params.neutral_sat,
        "green_cuts": list(_family_params.green_cuts),
        "palette_floor": _family_params.palette_floor,
        "overflow_weight": _family_params.overflow_weight,
    }


def set_quantize_params(params: FamilyParams, max_palettes: int) -> int:
    """Update the live family-quant knobs, invalidate the quant-dependent caches, and
    return the new generation token.

    The param-INDEPENDENT state is preserved: the RMXP source-tile PNG cache
    (``_tile_png_cache``) and the whole ``_map_cache`` — including each map's warm
    ``TileRasterizer`` and its pre-quant metatile composites — stay alive.  Only the
    quant-DEPENDENT caches are dropped (the palette analysis and the post-quant
    metatile PNGs).  Bumping ``_quant_generation`` marks every cached ``_MapState``
    stale; ``_ensure_loaded`` re-runs *only* the quantize step for a map the next time
    it's touched, so a knob change no longer rebuilds grids or re-renders tiles."""
    global _family_params, _max_palettes, _quant_generation
    _family_params = params
    _max_palettes = max_palettes
    _quant_generation += 1
    _tileset_analysis_cache.clear()
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
    passages: list[int],
    terrain_tags: list[int],
) -> tuple[PaletteAnalysis, dict[tuple, int]]:
    """Build and cache the palette-quantization pool for a map (idempotent).

    Pool = whatever the SHIPPED ROM quantizes together, replicated exactly. The
    boot-gate ROM is built by ``scripts/assemble_pathfinder.py`` (``run_graphics_pass``),
    which calls ``build_slice_tilesets(maps, ...)`` with no ``source_tileset_of``
    over ``SLICE_MAP_IDS`` (``rpg2gba.tileset_converter.map_set``). Inside,
    ``build_slice_tilesets`` groups maps by their REAL ``map_json["tileset_id"]``
    (``build_slice_tilesets.py`` ~line 249-251): Map048 and Map049 (Player's House
    1F/2F) both carry tileset 19 and are pooled into ONE shared 13-palette
    quantization; Map032 (Moki Town, tileset 22) is alone. This function replicates
    that grouping — for a slice map, the pool is every ``SLICE_MAP_IDS`` member
    sharing the opened map's real ``tileset_id`` — so the "Quantized (family)" view
    matches the ROM byte-for-byte given the same inputs.

    Non-slice maps have no shipped ROM truth to match: the Map Walker's phase5
    build feeds ``build_slice_tilesets`` a unique synthetic tileset id per map
    (``1000 + map_id``), a per-map pool that is NOT what the §9 boot-gate ROM
    compares against. They self-pool (``pool_map_ids = [map_id]``) as a
    preview-only best effort, not a fidelity claim.
    """
    maps_dir = _maps_dir()

    if map_id in SLICE_MAP_IDS:
        docs: dict[int, dict] = {}
        for m in SLICE_MAP_IDS:
            p = maps_dir / f"Map{m:03d}.json"
            try:
                docs[m] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
        if map_id not in docs:
            raise FileNotFoundError(f"Map JSON not found: {maps_dir / f'Map{map_id:03d}.json'}")
        opened_ts = int(docs[map_id]["tileset_id"])
        pool_map_ids = [
            m for m in SLICE_MAP_IDS if m in docs and int(docs[m]["tileset_id"]) == opened_ts
        ]
    else:
        docs = {}
        pool_map_ids = [map_id]

    # Cache key includes a stat-only fingerprint of every pooled map's json (+
    # tilesets.json) alongside the pool membership, so a rebuild that changes a
    # pooled map's content invalidates the entry even when membership is unchanged
    # (e.g. Map049 rebuilt while viewing Map048 — same {48,49} pool, new content).
    pool_fp = tuple(_file_fingerprint(maps_dir / f"Map{m:03d}.json") for m in pool_map_ids)
    pool_fp += (_file_fingerprint(_tilesets_json()),)
    cache_key = (frozenset(pool_map_ids), pool_fp)
    if cache_key in _tileset_analysis_cache:
        return _tileset_analysis_cache[cache_key]

    maplist: list[tuple[int, dict]] = []
    for mid in pool_map_ids:
        doc = docs.get(mid)
        if doc is None:
            p = maps_dir / f"Map{mid:03d}.json"
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
        maplist.append((mid, doc))

    # Column keys are computed from a `mask_out_of_atlas`-masked grid per map (see
    # `column_keys_for_maps`), so a stale RMXP tile id past the atlas bound
    # (e.g. Map094's 1550, 4531, 8197 …) never appears in a key here — the cell's
    # other layers still contribute their own key, they just don't drag the whole
    # cell out of the pool any more.
    max_tid = raster.max_static_tile_id()
    pool_keys = column_keys_for_maps(maplist, max_static_tile_id=max_tid)

    # Fail-loud backstop: every key above was built from a masked grid, so none
    # of them should ever fail this — a hit means a masking site was missed.
    still_bad = [k for k in pool_keys if not column_in_atlas(raster, k)]
    if still_bad:
        raise AssertionError(
            f"tileset {tileset_id}: {len(still_bad)} pool column key(s) still "
            f"reference out-of-atlas tile ids after masking (max static id "
            f"{max_tid}) — e.g. {still_bad[0]!r}"
        )

    pool_desc = "+".join(f"Map{m:03d}" for m in pool_map_ids)
    print(f"    tileset {tileset_id}: pool [{pool_desc}], {len(pool_keys)} pool keys")

    if not pool_keys:
        analysis: PaletteAnalysis = PaletteAnalysis(palettes=[], metatiles=[])
        pool_key_to_idx: dict[tuple, int] = {}
    else:
        pool_metatiles = [
            _render_column(ck, raster, priorities, passages, terrain_tags) for ck in pool_keys
        ]
        analysis = analyze_tileset_palettes(
            pool_metatiles, max_palettes=_max_palettes, quantizer=_make_quantizer()
        )
        pool_key_to_idx = {ck: i for i, ck in enumerate(pool_keys)}

    _tileset_analysis_cache[cache_key] = (analysis, pool_key_to_idx)
    return analysis, pool_key_to_idx


def _refresh_postquant(map_id: int, state: _MapState) -> None:
    """Recompute only the quant-DEPENDENT fields of an already-loaded map state
    (palette analysis + post-quant metatile pairs), reusing the param-independent
    grid, warm rasterizer, and pre-quant metatile composites already in ``state``.

    Called on first load and whenever the cached state is stale after a re-quant, so
    a knob change re-runs the quantize step alone — not the grid load or tile renders."""
    analysis, pool_key_to_idx = _ensure_tileset_analysis(
        state.tileset_id, state.raster, state.priorities, map_id,
        state.passages, state.terrain_tags,
    )
    postquant: list[tuple[np.ndarray, np.ndarray] | None] = []
    for ck in state.colkeys_sorted:
        if not ck:
            # Empty column (either genuinely empty, or every non-empty layer was
            # out-of-atlas and got masked away — state.grid is already masked, see
            # _ensure_loaded) -> void, same as the pre-quant render.
            postquant.append(None)
            continue
        pool_idx = pool_key_to_idx.get(ck)
        if pool_idx is None:
            raise ValueError(
                f"Map{map_id:03d}: column key {ck!r} absent from tileset {state.tileset_id} pool — "
                "analysis is inconsistent with this map's column keys"
            )
        mp = analysis.metatiles[pool_idx]
        postquant.append((mp.quant_bottom, mp.quant_top))

    state.analysis = analysis
    state.pool_key_to_idx = pool_key_to_idx
    state.metatile_imgs_postquant = postquant
    state.quant_generation = _quant_generation


def _invalidate_for_reload(map_id: int) -> None:
    """Drop ``map_id``'s cached state and every image cache, and bump the quant
    generation, because its on-disk inputs changed since it was loaded (a pipeline
    rebuild while the server was running).

    Clears ALL tile/metatile PNG caches and the whole tileset-analysis cache, not
    just this map's — simplest safe invalidation (these are just in-process dict
    caches, cheap to rebuild lazily) and it correctly handles a changed pool
    sibling too: bumping ``_quant_generation`` marks every OTHER cached map's
    ``_MapState`` stale as well, so the next ``_ensure_loaded`` for e.g. Map048
    re-runs ``_refresh_postquant`` (and re-reads Map049 fresh) even though
    Map048's own file never changed. Bumping the generation also drives the
    client: post-quant (and now all) image URLs carry ``&g=<generation>`` to
    defeat the browser's ``immutable`` cache after a reload."""
    global _quant_generation
    _map_cache.pop(map_id, None)
    _tile_png_cache.clear()
    _metatile_png_cache.clear()
    _tileset_analysis_cache.clear()
    _quant_generation += 1


def _pixel_classes(
    colkeys_sorted: list[tuple],
    metatile_imgs: list[MetatileImage | None],
    raster: TileRasterizer,
    priorities: list[int],
    passages: list[int] | None = None,
    terrain_tags: list[int] | None = None,
) -> list[int]:
    """Pixel-equivalence class per colkey index: ``pix_class[i]`` is the smallest
    colkey index whose metatile renders EXACTLY like ``i``'s — same layer split,
    behavior, frame count, and every animation frame's pixels.

    ``column_key`` deliberately keeps autotile shape-variants distinct (faithful
    edges — see layout.column_key), but many variants rasterize identically
    (e.g. the flower autotile's 12 interior shapes), which over-splits the
    viewer's "Expand similar" (SLICE1_TODO #10). This equivalence is a viewer
    grouping only — the pipeline still emits one metatile per column key.

    Frame-aware on purpose: an animated column never merges with a static
    lookalike of its frame 0, and two animated columns merge only if every
    frame matches. A column whose frame-count lcm trips the fail-loud guard
    can't be hashed faithfully, so it stays alone in its own class."""
    class_by_key: dict[tuple, int] = {}
    out: list[int] = []
    for i, ck in enumerate(colkeys_sorted):
        mt = metatile_imgs[i]
        if mt is None:
            out.append(i)  # the empty column is alone in its class
            continue
        try:
            n = column_n_frames(ck, raster)
        except ValueError as e:
            log.warning("colkey %r unhashable for pixel grouping (%s); left ungrouped", ck, e)
            out.append(i)
            continue
        if n > 1:
            mt = _render_column(ck, raster, priorities, passages, terrain_tags, n_frames=n)
        parts = [mt.bottom.tobytes(), mt.top.tobytes()]
        for fb, ft in mt.frames or []:
            parts += [fb.tobytes(), ft.tobytes()]
        key = (int(mt.layer_type), int(mt.behavior), n, *parts)
        out.append(class_by_key.setdefault(key, i))
    return out


def _ensure_loaded(map_id: int) -> None:
    """Load and cache all per-map rendering state (idempotent).

    Checks a stat-only fingerprint of the on-disk inputs (``_slice_aware_fingerprint``)
    on every call — cheap, no JSON parsing — so a pipeline rebuild while the server
    is running is detected and forces a full reload instead of silently continuing
    to serve pre-rebuild bytes."""
    current_fp = _slice_aware_fingerprint(map_id)

    if map_id in _map_cache:
        state = _map_cache[map_id]
        if state.input_fingerprint != current_fp:
            log.info("Map%03d: on-disk inputs changed since load, reloading", map_id)
            _invalidate_for_reload(map_id)
        else:
            if state.quant_generation != _quant_generation:
                _refresh_postquant(map_id, state)
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

    tileset_sources = load_tileset_sources(tileset_id, tilesets_json=tilesets_json_path)
    raster = TileRasterizer(tileset_sources)

    # Mask stale out-of-atlas static tile ids (module docstring of
    # graphics/raster.py) BEFORE any column_key below: only the bad layer is
    # zeroed, the rest of the cell renders normally. The ORIGINAL (x, y, z,
    # tile_id) tuples are kept on state for build_map_data's out_of_atlas report.
    max_tid = raster.max_static_tile_id()
    grid, masked_cells = mask_out_of_atlas(grid, max_tid)
    if masked_cells:
        log.warning(
            "Map%03d: masked %d out-of-atlas cell-layer(s) (stale RMXP ids past "
            "static id %d)", map_id, len(masked_cells), max_tid,
        )
    animated_slots: set[int] = {
        slot
        for slot, path in enumerate(tileset_sources.autotiles)
        if path is not None and autotile_frame_count(path) > 1
    }

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
    # `grid` is already masked above, so every non-empty key here is fully
    # in-atlas and renders normally; only a genuinely all-empty column is void.
    metatile_imgs: list[MetatileImage | None] = []
    for ck in colkeys_sorted:
        if not ck:
            metatile_imgs.append(None)  # empty column -> transparent
        else:
            metatile_imgs.append(_render_column(ck, raster, priorities, passages, terrain_tags))

    n_rendered = sum(1 for m in metatile_imgs if m is not None)
    pix_class = _pixel_classes(
        colkeys_sorted, metatile_imgs, raster, priorities, passages, terrain_tags
    )
    n_classes = len(set(pix_class))
    print(
        f"    {len(colkeys_sorted)} distinct columns, {n_rendered} metatile renders,"
        f" {n_classes} pixel classes"
    )

    # Param-independent state first; the quant-dependent fields (analysis, post-quant
    # metatiles) are filled by _refresh_postquant so the same path serves a re-quant.
    state = _MapState(
        grid=grid,
        raster=raster,
        priorities=priorities,
        passages=passages,
        terrain_tags=terrain_tags,
        autotile_names=autotile_names,
        animated_slots=animated_slots,
        tileset_id=tileset_id,
        ts_name=ts_entry.get("name", ""),
        ts_tileset_name=ts_entry.get("tileset_name", ""),
        map_width=int(doc.get("width", grid.xsize)),
        map_height=int(doc.get("height", grid.ysize)),
        events_raw=doc.get("events", []),
        masked_cells=masked_cells,
        colkeys_sorted=colkeys_sorted,
        colkey_to_idx=colkey_to_idx,
        metatile_imgs=metatile_imgs,
        pix_class=pix_class,
        metatile_imgs_postquant=[],
        analysis=PaletteAnalysis(palettes=[], metatiles=[]),
        pool_key_to_idx={},
        quant_generation=-1,  # forces the initial _refresh_postquant below
        input_fingerprint=current_fp,
    )
    _map_cache[map_id] = state
    _refresh_postquant(map_id, state)


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
    elif not state.raster.in_atlas(tile_id):
        # Stale RMXP tile id past atlas bounds — a clean 404, not the
        # fail-loud ValueError _render_static would raise (CLAUDE.md §4.5:
        # that fail-loud behaviour is intentional for the build pipeline, but
        # the viewer must not 500 on a known, already-voided cell).
        raise FileNotFoundError(
            f"tile {tile_id} is out-of-atlas (stale RMXP id) for map {map_id}"
        )
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


_map_png_cache: dict[int, tuple[object, int, bytes]] = {}  # map_id -> (fingerprint, quant_gen, PNG)


def render_map_png(map_id: int) -> bytes:
    """Whole map as ONE PNG, matching the client's default 'gba' layer.

    Per cell (16 px): metatile ``bottom`` then ``top`` alpha-composited (same
    order as viewer.js drawCellBase). No background fill; cells with no metatile
    stay transparent. Memoized per map_id; stale when the on-disk input
    fingerprint or the quantize generation changes (mirrors ``_ensure_loaded``)."""
    _ensure_loaded(map_id)
    state = _map_cache[map_id]
    hit = _map_png_cache.get(map_id)
    if hit is not None and hit[0] == state.input_fingerprint and hit[1] == _quant_generation:
        return hit[2]

    grid = state.grid
    comp: dict[int, Image.Image] = {}
    out = Image.new("RGBA", (grid.xsize * 16, grid.ysize * 16), (0, 0, 0, 0))
    for y in range(grid.ysize):
        for x in range(grid.xsize):
            idx = state.colkey_to_idx[column_key(grid, x, y)]
            tile = comp.get(idx)
            if tile is None:
                tile = Image.open(io.BytesIO(render_metatile_png(map_id, idx, "bottom"))).convert("RGBA")
                top = Image.open(io.BytesIO(render_metatile_png(map_id, idx, "top"))).convert("RGBA")
                tile = Image.alpha_composite(tile, top)
                comp[idx] = tile
            out.paste(tile, (x * 16, y * 16))
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    png = buf.getvalue()
    _map_png_cache[map_id] = (state.input_fingerprint, _quant_generation, png)
    return png


def render_npc_png(character_name: str) -> bytes:
    """Render one NPC's sheet to PNG bytes (cached by lowercased name).

    Always frame 0 (RMXP's down-facing idle, or the intact/idle frame for a
    break-prop/large-prop sheet) -- the viewer just needs a recognizable
    sprite per event, not per-direction accuracy. Raises FileNotFoundError if
    the sheet isn't under RPG2GBA_URANIUM_SRC/Graphics/Characters (fails loud;
    the client falls back to a dot marker on a 404).
    """
    key = character_name.lower()
    if key in _npc_png_cache:
        return _npc_png_cache[key]
    sheet_path = _resolve_sheet(_characters_dir(), character_name)
    sprite = convert_character_sheet(sheet_path)
    png = _arr_to_png(sprite.frames[0])
    _npc_png_cache[key] = png
    return png


# ---------------------------------------------------------------------------
# Data collection (no image bytes — used directly by the server)
# ---------------------------------------------------------------------------


def _tile_is_animated(tile_id: int, animated_slots: set[int]) -> bool:
    """True if `tile_id` is an autotile (48..383) whose slot has >1 frame."""
    return 48 <= tile_id < 384 and (tile_id // 48 - 1) in animated_slots


def _parse_events(events_list: list) -> list[dict]:
    result = []
    for evt in events_list:
        is_warp = any(
            any(cmd.get("code") == 201 for cmd in page.get("list", []))
            for page in evt.get("pages", [])
        )
        pages = evt.get("pages", [])
        character_name = pages[0].get("graphic", {}).get("character_name", "") if pages else ""
        result.append({
            "id": evt.get("id"),
            "name": evt.get("name", ""),
            "x": evt.get("x"),
            "y": evt.get("y"),
            "npages": len(evt.get("pages", [])),
            "is_warp": is_warp,
            "character_name": character_name or "",
        })
    return result


def _build_events_payload(map_id: int, events_list: list) -> list[dict]:
    """Route the event list through the EVENTS-mode enrichment layer
    (``map_viewer_events.enrich_events`` — trainer/item identity, kind
    classification, ...), falling back to the bare ``_parse_events`` shape if
    that layer raises, so the GRAPHICS mode never goes dark because of an
    EVENTS-mode bug. Imported lazily (not at module top) to avoid a circular
    import: ``map_viewer_events`` itself imports this module at ITS top
    level, to reuse the path/cache helpers below."""
    try:
        import map_viewer_events

        return map_viewer_events.enrich_events(map_id, events_list)
    except Exception:
        log.exception(
            "map_viewer_events.enrich_events failed for map %s; falling back to _parse_events",
            map_id,
        )
        return _parse_events(events_list)


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

    # (x, y) -> {z: original_tile_id} for every layer `mask_out_of_atlas` zeroed
    # (see _ensure_loaded) — `grid` itself only has the post-mask (0) value, so
    # this is the only place the ORIGINAL stale id survives for reporting.
    masked_by_xy: dict[tuple[int, int], dict[int, int]] = {}
    for mx, my, mz, mtid in state.masked_cells:
        masked_by_xy.setdefault((mx, my), {})[mz] = mtid

    cells: list[dict] = []
    out_of_atlas: list[dict] = []
    for y in range(grid.ysize):
        for x in range(grid.xsize):
            layers = [grid.tile_at(x, y, z) for z in range(grid.zsize)]
            ck = column_key(grid, x, y)
            colkey_idx = state.colkey_to_idx[ck]
            masked_here = masked_by_xy.get((x, y), {})

            layer_detail: list[dict] = []
            cell_out_of_atlas = bool(masked_here)
            for z, tid in enumerate(layers):
                orig_tid = masked_here.get(z)
                if orig_tid is not None:
                    # This layer was masked to empty (stale out-of-atlas RMXP
                    # id) — report the ORIGINAL id, not the post-mask 0. Nothing
                    # meaningful to look up for a tile id that was never real.
                    out_of_atlas.append({"x": x, "y": y, "layer": z, "tile_id": orig_tid})
                    layer_detail.append({
                        "z": z, "tile_id": orig_tid, "passage": 0,
                        "priority": 0, "terrain": 0, "autotile_name": None,
                        "out_of_atlas": True,
                    })
                    continue
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

            # `grid` is already masked, so these read only in-atlas tile ids —
            # a masked-away layer is correctly treated as absent (RMXP itself
            # draws/tests nothing for it; layout._passage_lookup never sees it).
            col_ours = our_blocked(grid, state.passages, state.priorities, state.terrain_tags, x, y)
            col_ur = uranium_blocked(grid, state.passages, state.priorities, state.terrain_tags, x, y)
            pmax = max(
                (state.priorities[tid] for tid in layers if tid > 0 and tid < len(state.priorities)),
                default=0,
            )

            cell = {
                "x": x, "y": y,
                "layers": layers,
                "colkey_idx": colkey_idx,
                "layer_detail": layer_detail,
                "collision_ours": col_ours,
                "collision_uranium": col_ur,
                "mismatch": col_ours != col_ur,
                "priority_max": pmax,
            }
            if any(_tile_is_animated(tid, state.animated_slots) for tid in layers):
                cell["animated"] = True
            if cell_out_of_atlas:
                cell["out_of_atlas"] = True
            cells.append(cell)

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
        if not state.raster.in_atlas(tid):
            # Stale RMXP tile id past atlas bounds — never render, just report no colors.
            rmxp_tile_colors[str(tid)] = []
            continue
        img = state.raster.render(tid)
        if img is None:
            rmxp_tile_colors[str(tid)] = []
            continue
        arr = np.asarray(img)  # RGBA
        visible = arr[arr[:, :, 3] > 0, :3]
        # Distinct source RGBs (order-insensitive: this feeds a debug sidebar).
        rmxp_tile_colors[str(tid)] = (
            np.unique(visible, axis=0).tolist() if visible.size else []
        )

    # colkey_palettes: per-colkey-idx summary of palette usage and color changes
    # A "merge" is a colour whose 5-bit value moved (orig>>3 != final>>3): the
    # palette packer couldn't keep it, so it snapped to a neighbour.  A pair with
    # zero shift is pure 8->5-bit truncation, not merging.  merge_severity sums the
    # L1 5-bit distance over snapped colours so the worst tiles can be heat-mapped.
    colkey_palettes: list[dict] = []
    for ck in state.colkeys_sorted:
        if not ck or ck not in pool_key_to_idx:
            # Empty column, or an out-of-atlas colkey dropped from the pool
            # (see _ensure_tileset_analysis) -> no palette data, same as empty.
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
        if not ck or ck not in pool_key_to_idx:
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
        "pix_class": state.pix_class,
        "cells": cells,
        "events": _build_events_payload(map_id, state.events_raw),
        "palettes": palettes_json,
        "rmxp_tile_colors": rmxp_tile_colors,
        "colkey_palettes": colkey_palettes,
        "palette_usage": palette_usage,
        "out_of_atlas": out_of_atlas,
    }


# ---------------------------------------------------------------------------
# Web assets: the map-viewer and palette-inspector pages live as real files in
# scripts/map_viewer/ (viewer.{html,css,js}, palette.{html,css,js}, knobbar.js).
# Each *.html carries /*VIEWER_CSS*/ and /*VIEWER_JS*/ placeholders plus the
# __VIEWER_CONFIG__ token the server fills in per request; viewer.js / palette.js
# carry a /*KNOBBAR_JS*/ token for the shared knob-panel script.
# ---------------------------------------------------------------------------
_ASSET_DIR = Path(__file__).parent / "map_viewer"


def _asset(name: str) -> str:
    return (_ASSET_DIR / name).read_text(encoding="utf-8")


KNOBBAR_JS = _asset("knobbar.js")


def _assemble(html: str, css: str, js: str) -> str:
    body_js = _asset(js).replace("/*KNOBBAR_JS*/", KNOBBAR_JS)
    return _asset(html).replace("/*VIEWER_CSS*/", _asset(css)).replace("/*VIEWER_JS*/", body_js)


MAP_VIEWER_HTML = _assemble("viewer.html", "viewer.css", "viewer.js")
PALETTE_VIEWER_HTML = _assemble("palette.html", "palette.css", "palette.js")
