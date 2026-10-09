# ruff: noqa: E501
"""Shared data-extraction and rendering core for the Uranium map viewer.

Drives the lazy server (map_viewer_server.py).  Module-level caches keep per-map
rasterizer state alive so repeated tile/metatile requests from the server don't
rebuild from scratch.  The web pages themselves live as real files under
scripts/map_viewer/ and are assembled into MAP_VIEWER_HTML / PALETTE_VIEWER_HTML
at import (see the bottom of this module).
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import numpy as np
from PIL import Image

from rpg2gba.tileset_converter.connections import (
    EDGE_TO_DIRECTION,
    ConnectionRow,
    parse_connections,
)
from rpg2gba.tileset_converter.connection_remap import STRIP_DEPTH_EW, STRIP_DEPTH_NS, strip_depth
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
from rpg2gba.tileset_converter.graphics.palette_families import (
    compute_component_palettes,
    make_pinned_quantizer,
    seam_components,
)
from rpg2gba.tileset_converter.graphics.quantize import (
    FamilyParams,
    QuantizeResult,
    build_quantized_tileset_family,
)
from rpg2gba.tileset_converter.graphics.raster import TileRasterizer, column_in_atlas
from rpg2gba.tileset_converter.graphics.rom_quantize import (
    ROM_FAMILY_PARAMS,
    ROM_SHARED_PALETTES,
    ROM_TILE_MERGE,
)
from rpg2gba.tileset_converter.graphics.shared_palettes import make_shared_quantizer
from rpg2gba.tileset_converter.graphics.sources import (
    load_tileset_sources,
    tileset_source_paths,
)
from rpg2gba.tileset_converter.graphics.sprites import convert_character_sheet
from rpg2gba.tileset_converter.layout import TileGrid, column_key, mask_out_of_atlas
# Not used by the viewer any more (pooling is per map); kept as a module attribute
# because tests monkeypatch ``mvc.SLICE_MAP_IDS``.
from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS  # noqa: F401
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
    rendered output at the data level: its own ``Map{NNN}.json`` and
    ``tilesets.json``.

    Per-map pooling (see ``_ensure_tileset_analysis``) means no sibling map's json
    can change this map's quantization, so siblings are NOT folded in (they were,
    for ``SLICE_MAP_IDS`` members, while the viewer pooled by real tileset id).
    The opt-in seam-palette view depends on the other members of the seam
    component; that dependency is keyed separately (``_seam_key``)."""
    maps_dir = _maps_dir()
    paths = [maps_dir / f"Map{map_id:03d}.json", _tilesets_json()]
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

    Only *map_id*'s own tileset is resolved: the viewer pools per map
    (``_ensure_tileset_analysis``), so no other map's source art affects *map_id*'s
    render. (The seam-palette view's cross-map dependency is keyed by ``_seam_key``,
    which fingerprints each component member separately.)

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

    1. ``_json_fingerprint(map_id)``: the map's own ``Map{NNN}.json`` and
       ``tilesets.json`` — each a ``(mtime_ns, size)`` pair.
    2. The tileset source PNGs (sheet + autotiles) map_id's own tileset depends
       on (see ``_derive_png_paths_for_map``). Each entry is ``(str(path), mtime_ns, size)``:
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
_metatile_png_cache: dict[tuple, bytes] = {}  # (map_id, idx, layer, seam_key | None)
# Per-map metatile atlas PNGs: (map_id, layer, seam_key | None).  Same lifetime rules
# as _metatile_png_cache (cleared at every site that clears it).
_atlas_png_cache: dict[tuple, bytes] = {}
_npc_png_cache: dict[str, bytes] = {}                        # character_name.lower() -> PNG
_npc_unconvertible: dict[str, str] = {}                      # character_name.lower() -> converter error
# key: (pool map-id set, fingerprint of every pooled map's json + tilesets.json) ->
# (analysis, pool_key_to_idx). The fingerprint half means a rebuild that changes a
# pooled map's content invalidates the entry even if the pool's *membership*
# (the frozenset) didn't change.
# The trailing key element is the seam-palette key (``_seam_key``) or None for the
# plain per-map analysis, so the two views never alias.
_tileset_analysis_cache: dict[
    tuple[frozenset[int], tuple[tuple[int, int], ...], tuple | None],
    tuple[PaletteAnalysis, dict[tuple, int]],
] = {}


@dataclass
class _QuantView:
    """The quant-DEPENDENT half of a map's render: which palette analysis its
    metatiles were fitted by, and the resulting post-quant pixels. The plain view is
    a window onto ``_MapState``; the seam-palette view is built on demand."""

    analysis: PaletteAnalysis
    pool_key_to_idx: dict[tuple, int]
    postquant: list[tuple[np.ndarray, np.ndarray] | None]


# Seam-palette caches hold only the LATEST entry per key subject, so a changing
# fingerprint replaces rather than accumulates: component tuple -> (seam_key, palettes)
# and map id -> (seam_key, view).
class SeamSharedConflict(ValueError):
    """?sp=1 (seam palettes) requested while shared palettes (P2) are on. The server
    maps this to a 400 with the message telling the operator what to untick."""


_seam_palette_cache: dict[tuple[int, ...], tuple[tuple, list[np.ndarray]]] = {}
_seam_view_cache: dict[int, tuple[tuple, _QuantView]] = {}


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
# Two named configurations. ROM-STOCK is exactly what the ROM build does — read from
# rom_quantize, the single definition the build uses — and the oracle/parity checks
# must run under it. VIEWER-DEFAULT is the preview the viewer boots with. Since
# 2026-10-06 both are Ward + shared palettes (the ROM adopted the 10-05 preview), so
# `non_stock` (compares against ROM-STOCK) is False by default.
ROM_STOCK_PARAMS: FamilyParams = ROM_FAMILY_PARAMS
ROM_STOCK_MAX_PALETTES: int = _ENGINE_MAX_PALS
ROM_STOCK_SHARED: bool = ROM_SHARED_PALETTES
ROM_STOCK_TILE_MERGE: bool = ROM_TILE_MERGE
VIEWER_DEFAULT_PARAMS: FamilyParams = ROM_FAMILY_PARAMS
VIEWER_DEFAULT_MAX_PALETTES: int = _ENGINE_MAX_PALS
VIEWER_DEFAULT_SHARED: bool = ROM_SHARED_PALETTES
# Viewer default for the game-wide tile merge (tile_merge.py): ON, matching the ROM
# build (ROM_TILE_MERGE is True since 2026-10-06).
VIEWER_DEFAULT_TILE_MERGE: bool = True
_family_params: FamilyParams = VIEWER_DEFAULT_PARAMS
_max_palettes: int = VIEWER_DEFAULT_MAX_PALETTES
_quant_generation: int = int(time.time() * 1000)
# P2 shared fixed palettes on/off (the ROM build's setting is rom_quantize's
# ROM_SHARED_PALETTES; this is the viewer's live copy). Not a FamilyParams field. `_shared_info` holds the latest per-map reservation counts.
_shared_palettes: bool = VIEWER_DEFAULT_SHARED
_shared_info: dict[int, dict] = {}
# Game-wide near-duplicate tile merge on/off (viewer's live copy of ROM_TILE_MERGE).
_tile_merge: bool = VIEWER_DEFAULT_TILE_MERGE


def _make_quantizer(*, shared: bool = False):
    """Current packer as a ``(tiles, *, max_palettes) -> QuantizeResult`` callable.
    ``shared=True`` wraps it with the P2 shared-palette reservation (per-map path only)."""
    base = partial(build_quantized_tileset_family, params=_family_params)
    if shared:
        return make_shared_quantizer(base, family_params=_family_params)
    return base


def current_quantize_state() -> tuple[FamilyParams, int]:
    """Live (params, max_palettes) — for snapshot/rollback by the server. The
    viewer-only shared-palettes toggle is separate: ``current_shared_palettes()``."""
    return _family_params, _max_palettes


def current_shared_palettes() -> bool:
    """Live shared-palettes (P2 preview) toggle — snapshot/rollback companion of
    ``current_quantize_state``."""
    return _shared_palettes


def shared_palettes_from_dict(d: dict) -> bool:
    """Parse the Apply POST's ``shared_palettes``. A MISSING key means the viewer
    default (True); a present value is strict (only boolean True is on)."""
    if "shared_palettes" not in d:
        return VIEWER_DEFAULT_SHARED
    return d["shared_palettes"] is True


def current_tile_merge() -> bool:
    """Live tile-merge toggle — snapshot/rollback companion of ``current_quantize_state``."""
    return _tile_merge


def tile_merge_from_dict(d: dict) -> bool:
    """Parse the Apply POST's ``tile_merge``. A MISSING key means the viewer default
    (True); a present value is strict (only boolean True is on)."""
    if "tile_merge" not in d:
        return VIEWER_DEFAULT_TILE_MERGE
    return d["tile_merge"] is True


_merge_table_lock = threading.Lock()
_merge_table = None  # tile_merge.MergeTable, loaded lazily once per process


def _get_merge_table():
    """The corpus tile-merge table (cache hit is instant; a stale cache rebuilds from
    the whole corpus, which takes minutes). Loaded once per process."""
    global _merge_table
    with _merge_table_lock:
        if _merge_table is None:
            from rpg2gba.tileset_converter.graphics.tile_merge import (
                MergeParams,
                corpus_merge_table,
            )

            build = _maps_dir().parent
            _merge_table = corpus_merge_table(
                MergeParams(), out_dir=build, tilesets_json=_tilesets_json(),
                cache_path=build / "tile_merge_table.npz",
            )
        return _merge_table


def get_quantize_params() -> dict:
    """Current knob state for injection into the page config (seeds the UI + the
    `generation` cache-bust token). `non_stock` is True when the live knobs differ
    from the ROM build's (ROM_STOCK_*), so it is True in the viewer-default state;
    `viewer_default` is True when the live state IS the viewer default. Both drive
    the always-visible (non-Advanced-gated) toolbar badge."""
    return {
        "generation": _quant_generation,
        "max_palettes": _max_palettes,
        "non_stock": (
            _family_params != ROM_STOCK_PARAMS or _max_palettes != ROM_STOCK_MAX_PALETTES
            or _shared_palettes != ROM_STOCK_SHARED or _tile_merge != ROM_STOCK_TILE_MERGE
        ),
        "viewer_default": (
            _family_params == VIEWER_DEFAULT_PARAMS
            and _max_palettes == VIEWER_DEFAULT_MAX_PALETTES
            and _shared_palettes == VIEWER_DEFAULT_SHARED
            and _tile_merge == VIEWER_DEFAULT_TILE_MERGE
        ),
        "shared_palettes": _shared_palettes,
        "tile_merge": _tile_merge,
        "dark_value": _family_params.dark_value,
        "neutral_sat": _family_params.neutral_sat,
        "green_cuts": list(_family_params.green_cuts),
        "palette_floor": _family_params.palette_floor,
        "overflow_weight": _family_params.overflow_weight,
        "reduction": _family_params.reduction,
    }


def set_quantize_params(
    params: FamilyParams, max_palettes: int, *, shared_palettes: bool | None = None,
    tile_merge: bool | None = None,
) -> int:
    """Update the live family-quant knobs, invalidate the quant-dependent caches, and
    return the new generation token.

    The param-INDEPENDENT state is preserved: the RMXP source-tile PNG cache
    (``_tile_png_cache``) and the whole ``_map_cache`` — including each map's warm
    ``TileRasterizer`` and its pre-quant metatile composites — stay alive.  Only the
    quant-DEPENDENT caches are dropped (the palette analysis and the post-quant
    metatile PNGs).  Bumping ``_quant_generation`` marks every cached ``_MapState``
    stale; ``_ensure_loaded`` re-runs *only* the quantize step for a map the next time
    it's touched, so a knob change no longer rebuilds grids or re-renders tiles.

    ``shared_palettes`` (viewer-only P2 preview toggle) is part of the applied state:
    it is keyword-only; ``None`` (omitted) keeps the live toggle unchanged (the server
    snapshots it with ``current_shared_palettes()`` for rollback). ``tile_merge`` is the
    same kind of keyword-only toggle (``current_tile_merge()`` for rollback)."""
    global _family_params, _max_palettes, _quant_generation, _shared_palettes, _tile_merge
    _family_params = params
    _max_palettes = max_palettes
    if shared_palettes is not None:
        _shared_palettes = bool(shared_palettes)
    if tile_merge is not None:
        _tile_merge = bool(tile_merge)
    _shared_info.clear()
    _budget_cache.clear()
    _quant_generation += 1
    _tileset_analysis_cache.clear()
    _metatile_png_cache.clear()
    _atlas_png_cache.clear()
    _seam_palette_cache.clear()
    _seam_view_cache.clear()
    return _quant_generation


def set_rom_stock_quantize() -> int:
    """Put the viewer in the ROM-equivalent config (median cut, no shared palettes,
    engine max palettes). The oracle/parity checks must call this first."""
    return set_quantize_params(
        ROM_STOCK_PARAMS, ROM_STOCK_MAX_PALETTES, shared_palettes=ROM_STOCK_SHARED,
        tile_merge=ROM_STOCK_TILE_MERGE,
    )


def set_viewer_default_quantize() -> int:
    """Put the viewer in its default preview config (Ward + shared palettes)."""
    return set_quantize_params(
        VIEWER_DEFAULT_PARAMS, VIEWER_DEFAULT_MAX_PALETTES,
        shared_palettes=VIEWER_DEFAULT_SHARED, tile_merge=VIEWER_DEFAULT_TILE_MERGE,
    )


def params_from_dict(d: dict) -> tuple[FamilyParams, int]:
    """Parse + clamp a knob dict (from the Apply POST) into (FamilyParams, max_palettes)
    so a malformed value can never crash the packer.  green_cuts are kept only if they
    fall strictly inside the green band (70, 170).  A MISSING ``reduction`` means the
    viewer default (ward); a present value is strict (only "ward" selects Ward).
    ``{}`` therefore parses to the viewer default (the reset path)."""
    mp = max(1, min(_ENGINE_MAX_PALS, int(d.get("max_palettes", _ENGINE_MAX_PALS))))
    cuts = sorted({float(c) for c in d.get("green_cuts", []) if 70.0 < float(c) < 170.0})
    params = FamilyParams(
        dark_value=max(0, min(255, int(d.get("dark_value", 40)))),
        neutral_sat=max(0.0, min(1.0, float(d.get("neutral_sat", 0.18)))),
        green_cuts=tuple(cuts),
        palette_floor=max(1, min(_ENGINE_MAX_PALS, int(d.get("palette_floor", 1)))),
        overflow_weight=("coverage" if str(d.get("overflow_weight")) == "coverage" else "colors"),
        reduction=(
            VIEWER_DEFAULT_PARAMS.reduction if "reduction" not in d
            else ("ward" if d["reduction"] == "ward" else "median_cut")
        ),
    )
    return params, mp


def _render_pool_column(
    ck: tuple, raster: TileRasterizer, priorities: list[int], passages: list[int],
    terrain_tags: list[int],
) -> MetatileImage:
    """A pool metatile exactly as ``build_slice_tilesets`` hands it to the emitter:
    ``n_frames=column_n_frames`` so an animated column's later frames feed the
    quantizer (their colours must fit the chosen palette too). Without it the viewer
    quantizes a different input than the ROM and animated-water maps drift. A column
    over the frame-count guard falls back to frame 0 (the build fails loud there; the
    viewer must still open)."""
    try:
        n = column_n_frames(ck, raster)
    except ValueError as e:
        log.warning("colkey %r: %s; quantizing frame 0 only", ck, e)
        n = 1
    return _render_column(ck, raster, priorities, passages, terrain_tags, n_frames=n)


def _pool_members(map_id: int) -> list[int]:
    """Sorted map ids sharing *map_id*'s emitted ROM tileset (itself included).

    Slice maps use ``load_slice_tileset_groups`` (the build's own grouping); a map
    outside the slice, or a build dir with no connections.json, is its own pool."""
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS, load_slice_tileset_groups

    if map_id not in SLICE_MAP_IDS:
        return [map_id]
    out_dir = _maps_dir().parent
    if not (out_dir / "connections.json").is_file():
        return [map_id]
    groups = load_slice_tileset_groups(out_dir, SLICE_MAP_IDS)
    return sorted(m for m, g in groups.items() if g == groups[map_id])


def _ensure_tileset_analysis(
    tileset_id: int,
    raster: TileRasterizer,
    priorities: list[int],
    map_id: int,
    passages: list[int],
    terrain_tags: list[int],
    *,
    seam_key: tuple | None = None,
    quantizer: Callable[..., QuantizeResult] | None = None,
) -> tuple[PaletteAnalysis, dict[tuple, int]]:
    """Build and cache the palette-quantization pool for a map (idempotent).

    Pool = the map's TILESET GROUP (``_pool_members``), exactly as the shipped ROM
    builds it. ``build_slice_tilesets`` gives every slice map its own synthetic
    tileset (1000+id) EXCEPT maps joined by an emitted in-slice connection, which
    share ONE (``map_set.tileset_groups``: e.g. Kevlar Town 31 + Route 2 35 = 1031),
    quantized/merged over the union of the members' metatile columns. A non-slice
    map keeps its own pool. The analysis is cached per group, so every member shares
    one entry (the key is the pool's map-id set, not *map_id*). All members of a group
    share one real RMXP tileset, so *raster* (the caller's) renders every pooled key.
    ``scripts/verify_viewer_rom_match.py`` Mode A rebuilds the real tilesets via
    ``build_slice_tilesets`` and Mode B checks this viewer against the shipped
    artifacts, 0 px diff for all 18 slice maps.

    ``seam_key`` / ``quantizer`` are the opt-in "seam palettes" view: the same
    per-map pool, but quantized by ``quantizer`` (a ``make_pinned_quantizer`` over the
    palettes shared by the map's seam component). ``seam_key`` (see ``_seam_key``)
    is folded into the cache key so the two views never alias.
    """
    maps_dir = _maps_dir()
    docs: dict[int, dict] = {}
    pool_map_ids = _pool_members(map_id)

    # Cache key includes a stat-only fingerprint of every pooled map's json (+ tilesets.json)
    # alongside the pool membership, so a rebuild that changes the map's content
    # invalidates the entry.
    pool_fp = tuple(_file_fingerprint(maps_dir / f"Map{m:03d}.json") for m in pool_map_ids)
    pool_fp += (_file_fingerprint(_tilesets_json()),)
    cache_key = (frozenset(pool_map_ids), pool_fp, seam_key)
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
    print(
        f"    tileset {tileset_id}: pool [{pool_desc}], {len(pool_keys)} pool keys"
        + (" (seam palettes)" if seam_key is not None else "")
    )

    if not pool_keys:
        analysis: PaletteAnalysis = PaletteAnalysis(palettes=[], metatiles=[])
        pool_key_to_idx: dict[tuple, int] = {}
    else:
        pool_metatiles = [
            _render_pool_column(ck, raster, priorities, passages, terrain_tags)
            for ck in pool_keys
        ]
        if _tile_merge:
            # Lossy game-wide near-duplicate tile merge. Substitute IN PLACE: pool key i
            # must stay pool index i (verify_viewer_rom_match Mode B relies on it), so
            # no dedup/reorder here — the lossless metatile dedup only enters the
            # budget readout (``tileset_budget``).
            table = _get_merge_table()
            pool_metatiles = [table.apply_metatile(mt) for mt in pool_metatiles]
        if quantizer is not None:
            q = quantizer
        else:
            q = _make_quantizer(shared=_shared_palettes)
        analysis = analyze_tileset_palettes(
            pool_metatiles, max_palettes=_max_palettes, quantizer=q,
        )
        if quantizer is None and _shared_palettes:
            _shared_info[map_id] = dict(q.info)
        pool_key_to_idx = {ck: i for i, ck in enumerate(pool_keys)}

    _tileset_analysis_cache[cache_key] = (analysis, pool_key_to_idx)
    return analysis, pool_key_to_idx


# ---------------------------------------------------------------------------
# Tileset budget readout (GBA 1024 tiles / 1024 metatiles)
# ---------------------------------------------------------------------------

_BUDGET_CAP_TILES = 1024
_BUDGET_CAP_METATILES = 1024
# (map_id, generation) -> payload. Cleared by every knob Apply as well.
_budget_cache: dict[tuple[int, int], dict] = {}
_budget_lock = threading.Lock()


def _budget_probe(metatiles: list[MetatileImage], max_palettes: int, shared: bool,
                  params: FamilyParams) -> dict:
    """Exact tile / metatile counts of ``metatiles`` through ``emit_tileset`` with
    the caps disabled, quantized by the viewer's quantizer for the given knobs."""
    from rpg2gba.tileset_converter.graphics.emit import emit_tileset

    base = partial(build_quantized_tileset_family, params=params)
    q = make_shared_quantizer(base, family_params=params) if shared else base
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        em = emit_tileset(
            metatiles, root / "p", root / "s", "budget_p", "budget_s",
            max_palettes=max_palettes, quantizer=q, enforce_caps=False,
        )
    return {
        "metatiles": em.n_metatiles,
        "tiles": em.n_tiles,
        "over": em.n_metatiles > _BUDGET_CAP_METATILES or em.n_tiles > _BUDGET_CAP_TILES,
    }


def tileset_budget(map_id: int) -> dict:
    """The map's GBA tileset budget under the CURRENT knobs plus both merge variants.

    Input mirrors the build's metatile list minus door/stair copies (not modelled
    here): the map's tileset-group pool (``_pool_members``) + the all-transparent void. ``merge_off`` = raw pool + void.
    ``merge_on`` = tile-merged pool + void, then the lossless ``dedup_metatiles``.
    ``current`` is whichever matches the live tile-merge knob. Cached per
    (map, generation)."""
    from rpg2gba.tileset_converter.graphics.build_slice_tilesets import _void_metatile
    from rpg2gba.tileset_converter.graphics.tile_merge import merge_and_dedup_metatiles

    with _budget_lock:
        gen, merge_now = _quant_generation, _tile_merge
        params, max_pals, shared = _family_params, _max_palettes, _shared_palettes
        hit = _budget_cache.get((map_id, gen))
        if hit is not None:
            return hit
        _ensure_loaded(map_id)
        st = _map_cache[map_id]
        pool_keys = column_keys_for_maps(
            [(m, json.loads((_maps_dir() / f"Map{m:03d}.json").read_text(encoding="utf-8")))
             for m in _pool_members(map_id)],
            max_static_tile_id=st.raster.max_static_tile_id(),
        )
        pool = [_render_pool_column(ck, st.raster, st.priorities, st.passages, st.terrain_tags)
                for ck in pool_keys]
        off_list = [*pool, _void_metatile()]
        table = _get_merge_table()
        on_list, _remap = merge_and_dedup_metatiles(off_list, table)
        out = {
            "map_id": map_id,
            "generation": gen,
            "cap_tiles": _BUDGET_CAP_TILES,
            "cap_metatiles": _BUDGET_CAP_METATILES,
            "pool": len(pool),
            "tile_merge": merge_now,
            "merge_off": _budget_probe(off_list, max_pals, shared, params),
            "merge_on": _budget_probe(on_list, max_pals, shared, params),
        }
        out["current"] = out["merge_on" if merge_now else "merge_off"]
        _budget_cache[(map_id, gen)] = out
        return out


# ---------------------------------------------------------------------------
# Hand-split planner (/split/<id>)
# ---------------------------------------------------------------------------
# The page paints cells into pieces and counts each piece's art itself: the metatiles
# under its own cells plus those under every other piece's cell it can SEE (the player
# camera's box around each of its cells). That needs, per cell, a metatile id, and per
# metatile, its 8x8 tile ids; both ship once and every repaint is client-side.

# (map_id, generation, merge) -> (payload, metatiles indexed by payload metatile id)
_split_cache: dict[tuple[int, int, bool], tuple[dict, list[MetatileImage]]] = {}


def _split_path(map_id: int) -> Path:
    """Saved hand-split layout. Under reference/ like the tile feedback: it is
    hand-authored operator data that must survive ``rm -rf output/``. Not read by
    the build."""
    d = _repo_root() / "reference" / "map_splits"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"Map{map_id:03d}.json"


def load_split(map_id: int) -> dict | None:
    path = _split_path(map_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_split(map_id: int, layout: dict) -> Path:
    """Persist a layout ``{"pieces": n, "assign": [piece per cell, row-major], ...}``
    after checking it covers the map exactly."""
    _ensure_loaded(map_id)
    st = _map_cache[map_id]
    assign = layout.get("assign")
    n = int(layout.get("pieces", 0))
    if not isinstance(assign, list) or len(assign) != st.grid.xsize * st.grid.ysize:
        raise ValueError(f"assign must list {st.grid.xsize * st.grid.ysize} cells")
    if n < 1 or any(not isinstance(a, int) or not 0 <= a < n for a in assign):
        raise ValueError(f"every cell must name a piece in 0..{n - 1}")
    path = _split_path(map_id)
    path.write_text(json.dumps(layout, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def _split_state(map_id: int, merge: bool | None = None) -> tuple[dict, list[MetatileImage]]:
    from rpg2gba.tileset_converter.graphics.emit import (
        _effective_frames,
        _flip_canonical_multi,
        _slot_frames_for_metatile,
    )
    from rpg2gba.tileset_converter.graphics.tile_merge import (
        dedup_metatiles,
        merge_and_dedup_metatiles,
    )

    with _budget_lock:
        gen = _quant_generation
        merge_now = _tile_merge if merge is None else merge
        _ensure_loaded(map_id)
        hit = _split_cache.get((map_id, gen, merge_now))
        if hit is not None:
            return hit
        st = _map_cache[map_id]
        nonempty = [i for i, ck in enumerate(st.colkeys_sorted) if ck]
        rendered = [
            _render_pool_column(st.colkeys_sorted[i], st.raster, st.priorities,
                                st.passages, st.terrain_tags)
            for i in nonempty
        ]
        if merge_now:
            mts, remap = merge_and_dedup_metatiles(rendered, _get_merge_table())
        else:
            mts, remap = dedup_metatiles(rendered)
        colkey_mt = [-1] * len(st.colkeys_sorted)
        for j, i in enumerate(nonempty):
            colkey_mt[i] = remap[j]

        tile_ids: dict[bytes, int] = {}
        mt_tiles: list[list[int]] = []
        for mt in mts:
            ids: set[int] = set()
            for frames in _slot_frames_for_metatile(mt):
                frames = _effective_frames(frames)
                if all(int(f[..., 3].max()) == 0 for f in frames):
                    continue  # transparent quad -> the shared tile 0
                key = _flip_canonical_multi(frames)[0]
                ids.add(tile_ids.setdefault(key, len(tile_ids)))
            mt_tiles.append(sorted(ids))

        grid = st.grid
        cells = [
            colkey_mt[st.colkey_to_idx[column_key(grid, x, y)]]
            for y in range(grid.ysize) for x in range(grid.xsize)
        ]
        events = [
            {"x": e["x"], "y": e["y"], "name": e["name"], "warp": e["is_warp"]}
            for e in _parse_events(st.events_raw)
        ]
        payload = {
            "map_id": map_id,
            "generation": gen,
            "tile_merge": merge_now,
            "width": grid.xsize,
            "height": grid.ysize,
            "cells": cells,
            "mt_tiles": mt_tiles,
            "n_tiles": len(tile_ids),
            "cap_tiles": _BUDGET_CAP_TILES,
            "cap_metatiles": _BUDGET_CAP_METATILES,
            "events": events,
        }
        _split_cache[(map_id, gen, merge_now)] = (payload, mts)
        return payload, mts


_arrivals_cache: dict[int, list[tuple[int, int]]] | None = None
_reach_cache: dict[int, dict] = {}


def _warp_arrivals() -> dict[int, list[tuple[int, int]]]:
    """Every direct transfer (event code 201, designation 0) target in the corpus:
    map id -> sorted [(x, y)]. Variable-designated transfers can't be resolved
    statically and are skipped. Built once per process."""
    global _arrivals_cache
    if _arrivals_cache is None:
        out: dict[int, set[tuple[int, int]]] = {}
        for path in sorted(_maps_dir().glob("Map*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            for ev in doc.get("events", []):
                for page in ev.get("pages", []):
                    for cmd in page.get("list", []):
                        p = cmd.get("parameters") or []
                        if cmd.get("code") == 201 and len(p) >= 4 and p[0] == 0:
                            out.setdefault(int(p[1]), set()).add((int(p[2]), int(p[3])))
        _arrivals_cache = {m: sorted(v) for m, v in out.items()}
    return _arrivals_cache


def _blocked_from_json(map_id: int) -> np.ndarray:
    """(H, W) bool, our collision (compare_collision.our_blocked) from the map JSON and
    tilesets.json alone -- no rasterizer, so it is cheap for neighbour maps."""
    doc = json.loads((_maps_dir() / f"Map{map_id:03d}.json").read_text(encoding="utf-8"))
    ts = json.loads(_tilesets_json().read_text(encoding="utf-8"))[str(int(doc["tileset_id"]))]
    t = doc["tiles"]
    grid = TileGrid(t["xsize"], t["ysize"], t["zsize"], t["data"])
    return np.array([[our_blocked(grid, ts["passages"], ts["priorities"], ts["terrain_tags"], x, y)
                      for x in range(grid.xsize)] for y in range(grid.ysize)])


def reachable_cells(map_id: int) -> dict:
    """Cells of *map_id* the player can stand on. The map's whole seam component
    (``map_graph.component_layout``) is laid out in one cell space and flood-filled
    over our collision from every warp arrival into ANY member, so walking across a
    connection is modelled and an unreachable plateau that merely continues over a
    seam stays unreachable. Does not model ledges, surfing, or scripted player moves
    through walls. Returns ``{"reach": [0/1 row-major], "seeds": [[x, y], ...] (this
    map's own arrivals), "component": [member ids]}``."""
    from map_graph import component_layout

    if map_id in _reach_cache:
        return _reach_cache[map_id]
    layout = component_layout(map_id)
    world = np.ones((layout["h"], layout["w"]), dtype=bool)   # True = blocked
    placed: dict[int, tuple[int, int, int, int]] = {}
    for m in layout["members"]:
        try:
            b = _blocked_from_json(m["id"])
        except FileNotFoundError:
            continue
        h, w = b.shape
        world[m["oy"]:m["oy"] + h, m["ox"]:m["ox"] + w] = b
        placed[m["id"]] = (m["ox"], m["oy"], w, h)
    arrivals = _warp_arrivals()
    stack: list[tuple[int, int]] = []
    for mid, (ox, oy, w, h) in placed.items():
        for x, y in arrivals.get(mid, []):
            if 0 <= x < w and 0 <= y < h and not world[oy + y, ox + x]:
                stack.append((ox + x, oy + y))
    reach = np.zeros_like(world)
    for x, y in stack:
        reach[y, x] = True
    WH, WW = world.shape
    while stack:
        x, y = stack.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < WW and 0 <= ny < WH and not reach[ny, nx] and not world[ny, nx]:
                reach[ny, nx] = True
                stack.append((nx, ny))
    ox, oy, w, h = placed[map_id]
    out = {"reach": reach[oy:oy + h, ox:ox + w].astype(np.uint8).ravel().tolist(),
           "seeds": [list(s) for s in arrivals.get(map_id, [])],
           "component": sorted(placed)}
    _reach_cache[map_id] = out
    return out


def split_data(map_id: int, merge: bool | None = None) -> dict:
    """Planner payload (``merge`` None = the live tile-merge knob): ``cells`` (row-major metatile id per cell, -1 = empty column,
    i.e. the void metatile) and ``mt_tiles`` (8x8 tile ids per metatile id), plus the
    saved layout if any.

    Metatiles are this map's columns rendered as the build renders them, then the
    live tile-merge knob's transformation (``merge_and_dedup_metatiles`` on, the
    lossless ``dedup_metatiles`` off). Tile ids are emit's dedup identity
    (flip-canonical, whole animation) BEFORE quantization, so a piece's tile count
    is a proxy that quantization can only lower; ``split_exact`` gives the real
    number. Neither count includes the void metatile or the transparent tile 0.
    Only this map's own columns: a tileset-group pool (``_pool_members``) is not
    modelled. Cached per (map, generation)."""
    payload, _mts = _split_state(map_id, merge)
    blocked = _blocked_from_json(map_id).astype(np.uint8).ravel().tolist()
    return {**payload, **reachable_cells(map_id), "blocked": blocked, "saved": load_split(map_id)}


def split_exact(map_id: int, pieces: list[list[int]], merge: bool | None = None) -> list[dict]:
    """Exact emitted counts per piece: each piece's metatile ids (own + seen, as the
    page computed them) plus the void metatile, through ``_budget_probe`` under the
    live knobs. Slow: one quantize + emit per piece."""
    from rpg2gba.tileset_converter.graphics.build_slice_tilesets import _void_metatile

    _payload, mts = _split_state(map_id, merge)
    params, max_pals, shared = _family_params, _max_palettes, _shared_palettes
    out = []
    for ids in pieces:
        if any(not 0 <= i < len(mts) for i in ids):
            raise IndexError(f"metatile id out of range 0..{len(mts) - 1}")
        chosen = [mts[i] for i in sorted(set(ids))] + [_void_metatile()]
        out.append(_budget_probe(chosen, max_pals, shared, params))
    return out


def _postquant_for(
    map_id: int,
    state: _MapState,
    analysis: PaletteAnalysis,
    pool_key_to_idx: dict[tuple, int],
) -> list[tuple[np.ndarray, np.ndarray] | None]:
    """Post-quant (bottom, top) pixels per colkey idx of *state*, read out of *analysis*."""
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
    return postquant


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
    state.analysis = analysis
    state.pool_key_to_idx = pool_key_to_idx
    state.metatile_imgs_postquant = _postquant_for(map_id, state, analysis, pool_key_to_idx)
    state.quant_generation = _quant_generation


# ---------------------------------------------------------------------------
# Seam palettes (opt-in): palettes shared across a seam component
# ---------------------------------------------------------------------------


def _connection_rows() -> list[ConnectionRow]:
    """ALL rows of connections.json (not restricted to SLICE_MAP_IDS: Map040 is not in
    it). Same loader the viewer's seam geometry uses (``map_graph``); [] if the file
    is unavailable."""
    import map_graph

    return parse_connections([list(e) for e in map_graph._load_connections_raw()])


def _seam_component(map_id: int) -> tuple[int, ...] | None:
    """The sorted seam component containing *map_id*, or None if it has no seams."""
    return seam_components(_connection_rows()).get(map_id)


def _seam_key(map_id: int, seam: bool) -> tuple | None:
    """Cache key for the seam-palette view of *map_id*; None when the toggle is off
    or the map is in no component (then the render is the plain per-map one).

    (component, every member's full stat fingerprint — json, tilesets.json, source
    PNGs —, quantize generation, max palettes): a sibling rebuild or a knob Apply
    changes the key, so a toggle never serves a stale image."""
    if not seam:
        return None
    if _shared_palettes:
        raise SeamSharedConflict(
            "seam palettes (?sp=1) cannot be combined with shared palettes (P2): "
            "untick \"shared palettes\" in the knob bar and Apply, then retry"
        )
    if _tile_merge:
        raise SeamSharedConflict(
            "seam palettes (?sp=1) cannot be combined with tile merge: the seam view "
            "quantizes the unmerged pool. Untick \"tile merge\" in the knob bar and "
            "Apply, then retry"
        )
    comp = _seam_component(map_id)
    if comp is None:
        return None
    return (
        comp,
        tuple(_slice_aware_fingerprint(m) for m in comp),
        _quant_generation,
        _max_palettes,
    )


def _member_metatiles(mid: int) -> list[MetatileImage] | None:
    """One component member's metatile list, rendered with that member's OWN
    rasterizer: every distinct non-empty (masked) column key, sorted, through
    ``_render_column`` — the same list ``_ensure_tileset_analysis`` quantizes for the
    map (and the emitter's input minus its void/door/stair copies, which are
    transparent or duplicate art and add no palette demand). None if the map json
    is absent (a seam neighbour that was never converted)."""
    maps_dir = _maps_dir()
    p = maps_dir / f"Map{mid:03d}.json"
    if not p.is_file():
        log.warning("seam palettes: Map%03d.json missing, member skipped", mid)
        return None
    cached = _map_cache.get(mid)
    if cached is not None:
        raster, priorities, passages, terrain_tags = (
            cached.raster, cached.priorities, cached.passages, cached.terrain_tags,
        )
        doc = json.loads(p.read_text(encoding="utf-8"))
    else:
        doc = json.loads(p.read_text(encoding="utf-8"))
        tileset_id = int(doc["tileset_id"])
        all_ts = json.loads(_tilesets_json().read_text(encoding="utf-8"))
        ts_entry = all_ts[str(tileset_id)]
        raster = TileRasterizer(load_tileset_sources(tileset_id, tilesets_json=_tilesets_json()))
        priorities, passages = ts_entry["priorities"], ts_entry["passages"]
        terrain_tags = ts_entry["terrain_tags"]
    keys = column_keys_for_maps([(mid, doc)], max_static_tile_id=raster.max_static_tile_id())
    return [_render_pool_column(ck, raster, priorities, passages, terrain_tags) for ck in keys]


def _component_palettes(key: tuple) -> list[np.ndarray]:
    """Shared palettes for the component in *key* (cached, latest per component)."""
    comp = key[0]
    hit = _seam_palette_cache.get(comp)
    if hit is not None and hit[0] == key:
        return hit[1]
    lists = [lst for m in comp for lst in [_member_metatiles(m)] if lst is not None]  # sorted by id
    pals = compute_component_palettes(
        lists, max_palettes=_max_palettes, quantizer=_make_quantizer()
    )
    print(
        f"    seam palettes {'+'.join(f'Map{m:03d}' for m in comp)}: "
        f"{sum(len(x) for x in lists)} metatiles -> {len(pals)} palettes"
    )
    _seam_palette_cache[comp] = (key, pals)
    return pals


def _quant_view(map_id: int, seam: bool = False) -> _QuantView:
    """The quant-dependent view of *map_id*: plain per-map, or (seam on, map in a
    component) the same per-map pool quantized against the component's shared
    palettes via ``make_pinned_quantizer``. Maps with no component, or seam off,
    return the plain view unchanged."""
    _ensure_loaded(map_id)
    state = _map_cache[map_id]
    key = _seam_key(map_id, seam)
    if key is None:
        return _QuantView(state.analysis, state.pool_key_to_idx, state.metatile_imgs_postquant)
    hit = _seam_view_cache.get(map_id)
    if hit is not None and hit[0] == key:
        return hit[1]
    pals = _component_palettes(key)
    analysis, p2i = _ensure_tileset_analysis(
        state.tileset_id, state.raster, state.priorities, map_id,
        state.passages, state.terrain_tags,
        seam_key=key, quantizer=make_pinned_quantizer(pals),
    )
    view = _QuantView(analysis, p2i, _postquant_for(map_id, state, analysis, p2i))
    _seam_view_cache[map_id] = (key, view)
    return view


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
    _atlas_png_cache.clear()
    _tileset_analysis_cache.clear()
    _seam_palette_cache.clear()
    _seam_view_cache.clear()
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


# Metatile atlas geometry, shared with the client via ``build_map_data`` meta.atlas.
# Metatile ``idx`` lives at cell (idx % cols, idx // cols), each cell cell_px square.
ATLAS_COLS = 64
ATLAS_CELL_PX = 16


def _metatile_arr(map_id: int, state: _MapState, idx: int, layer: str, seam: bool) -> np.ndarray:
    """RGBA pixels for one metatile layer -- the single pixel source for both the
    per-metatile PNG and the atlas, so the two can never disagree."""
    if layer in ("post_bottom", "post_top"):
        pq = _quant_view(map_id, seam).postquant[idx]
        if pq is None:
            return np.zeros((16, 16, 4), dtype=np.uint8)
        return pq[0] if layer == "post_bottom" else pq[1]
    mt = state.metatile_imgs[idx]
    if mt is None:
        return np.zeros((16, 16, 4), dtype=np.uint8)
    return mt.top if layer == "top" else mt.bottom


def render_metatile_png(map_id: int, idx: int, layer: str, seam: bool = False) -> bytes:
    """Render one metatile layer to PNG bytes (cached).

    ``layer`` is one of: ``'bottom'``, ``'top'``, ``'post_bottom'``, ``'post_top'``.
    ``post_bottom`` / ``post_top`` return the quantized-and-alpha-resolved pixels
    that match the shipped ROM's palette assignment.

    ``seam=True`` swaps the post-quant layers for the seam-palette view (see
    ``_quant_view``); the cache key carries ``_seam_key`` so the views never alias.
    The raw layers ignore it.

    ``idx`` is the per-map colkey index returned in ``build_map_data``."""
    _ensure_loaded(map_id)
    post = layer in ("post_bottom", "post_top")
    key = (map_id, idx, layer, _seam_key(map_id, seam) if post else None)
    if key in _metatile_png_cache:
        return _metatile_png_cache[key]
    state = _map_cache[map_id]
    if idx < 0 or idx >= len(state.metatile_imgs):
        raise IndexError(f"metatile idx {idx} out of range for map {map_id}")
    arr = _metatile_arr(map_id, state, idx, layer, seam)
    png = _arr_to_png(arr)
    _metatile_png_cache[key] = png
    return png


def render_atlas_png(map_id: int, layer: str, seam: bool = False) -> bytes:
    """Every metatile of ``map_id`` for ``layer`` as ONE PNG (cached).

    Fixed ``ATLAS_COLS``-wide grid of ``ATLAS_CELL_PX`` cells; metatile ``idx`` is at
    cell (idx % cols, idx // cols).  Pixels come from ``_metatile_arr``, so each cell
    is identical to ``render_metatile_png(map_id, idx, layer, seam)``.  Replaces
    thousands of per-metatile requests per page load with one per layer."""
    _ensure_loaded(map_id)
    post = layer in ("post_bottom", "post_top")
    key = (map_id, layer, _seam_key(map_id, seam) if post else None)
    if key in _atlas_png_cache:
        return _atlas_png_cache[key]
    state = _map_cache[map_id]
    n = len(state.metatile_imgs)
    rows = max(1, -(-n // ATLAS_COLS))
    cp = ATLAS_CELL_PX
    sheet = np.zeros((rows * cp, ATLAS_COLS * cp, 4), dtype=np.uint8)
    for idx in range(n):
        y, x = divmod(idx, ATLAS_COLS)
        sheet[y * cp:(y + 1) * cp, x * cp:(x + 1) * cp] = _metatile_arr(map_id, state, idx, layer, seam)
    png = _arr_to_png(sheet)
    _atlas_png_cache[key] = png
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


# ---------------------------------------------------------------------------
# ROM seam check: cost of border-strip import
# ---------------------------------------------------------------------------
# fieldmap.c draws a connected map's metatile IDs through the CURRENT map's tileset;
# the visible part is connection_remap.strip_depth deep (N/S 5, E/W 7), the depth the
# ROM build imports. A neighbour strip metatile whose image is not in the
# current map's own pool therefore has nothing to resolve to; the count of those is
# what importing the strip into A's tileset would cost.


def metatile_image_hash(mt: MetatileImage | None) -> str | None:
    """sha1 of a metatile's rendered 16x16 RGBA (bottom then top). None for the
    empty column (it is void, never imported)."""
    if mt is None:
        return None
    h = hashlib.sha1()
    h.update(np.ascontiguousarray(mt.bottom).tobytes())
    h.update(np.ascontiguousarray(mt.top).tobytes())
    return h.hexdigest()


def seam_strip_cells(
    edge: str,
    origin: tuple[int, int],
    a_dims: tuple[int, int],
    b_dims: tuple[int, int],
    depth: int | None = None,
) -> list[tuple[int, int]]:
    """B-local cells of neighbour B's strip along the seam.

    ``edge`` is A's own edge the seam sits on and ``origin`` is B's (0,0) in A's
    frame (``map_graph.connections_for``'s fields). The strip is the ``depth`` rows
    (N/S) or columns (E/W) of B nearest the shared edge (default per axis,
    ``connection_remap.strip_depth``), clamped to the span where
    A's edge and B overlap. Row-major order."""
    if depth is None:
        depth = strip_depth(EDGE_TO_DIRECTION[edge])
    aw, ah = a_dims
    bw, bh = b_dims
    dx, dy = origin
    if edge in ("N", "S"):
        xs = range(max(0, dx), min(aw, dx + bw))
        ys = range(max(0, bh - depth), bh) if edge == "N" else range(0, min(depth, bh))
        return [(ax - dx, y) for y in ys for ax in xs]
    ys_a = range(max(0, dy), min(ah, dy + bh))
    xs_b = range(max(0, bw - depth), bw) if edge == "W" else range(0, min(depth, bw))
    return [(x, ay - dy) for ay in ys_a for x in xs_b]


def compute_seam_entry(
    conn: dict,
    a_dims: tuple[int, int],
    b_dims: tuple[int, int],
    a_hashes: set[str],
    b_hash_at: Callable[[int, int], str | None],
) -> dict:
    """One seam's record: B's strip cells, those whose metatile image is absent from
    A's pool (*a_hashes*), and the unique-metatile counts. Empty cells (hash None)
    are neither strip nor missing."""
    cells = seam_strip_cells(conn["edge"], tuple(conn["origin"]), a_dims, b_dims)
    strip: list[list[int]] = []
    missing: list[list[int]] = []
    strip_u: set[str] = set()
    missing_u: set[str] = set()
    for x, y in cells:
        hx = b_hash_at(x, y)
        if hx is None:
            continue
        strip.append([x, y])
        strip_u.add(hx)
        if hx not in a_hashes:
            missing.append([x, y])
            missing_u.add(hx)
    return {
        "neighbor": conn["id"],
        "name": conn.get("name", ""),
        "edge": conn["edge"],
        "direction": EDGE_TO_DIRECTION[conn["edge"]],
        "origin": list(conn["origin"]),
        "depth": strip_depth(EDGE_TO_DIRECTION[conn["edge"]]),
        "strip": strip,
        "missing": missing,
        "strip_unique": len(strip_u),
        "missing_unique": len(missing_u),
    }


def seam_check(map_id: int) -> dict:
    """ROM seam check for *map_id* (A): per neighbour B, B's strip and which of it is
    absent from A's per-map pool, compared by rendered metatile image hash (not
    column key: two column keys, or two different tilesets, can render one image).
    Cell coordinates are B-local. Loads A and each B (``_ensure_loaded``)."""
    import map_graph

    _ensure_loaded(map_id)
    a = _map_cache[map_id]
    a_hashes = {h for h in map(metatile_image_hash, a.metatile_imgs) if h is not None}
    seams: list[dict] = []
    for conn in map_graph.connections_for(map_id):
        bid = conn["id"]
        _ensure_loaded(bid)
        b = _map_cache[bid]
        memo: dict[int, str | None] = {}

        def b_hash_at(x: int, y: int, _b: _MapState = b, _memo: dict = memo) -> str | None:
            idx = _b.colkey_to_idx[column_key(_b.grid, x, y)]
            if idx not in _memo:
                _memo[idx] = metatile_image_hash(_b.metatile_imgs[idx])
            return _memo[idx]

        seams.append(compute_seam_entry(
            conn, (a.grid.xsize, a.grid.ysize), (b.grid.xsize, b.grid.ysize),
            a_hashes, b_hash_at,
        ))
    return {
        "map_id": map_id, "depth_ns": STRIP_DEPTH_NS, "depth_ew": STRIP_DEPTH_EW,
        "pool_unique": len(a_hashes), "seams": seams,
    }


# ---------------------------------------------------------------------------
# Shared tiles: what a set of maps shares in the RMXP data vs the emitted ROM
# ---------------------------------------------------------------------------
# Four bases, per map a SET of keys:
#   rmxp_id     (real RMXP tileset id, column key)     same tileset + same tile ids
#   rmxp_image  sha1 of the pre-quant 16x16 render     identical art across tilesets
#   rom_mt      sha1 of the DECODED ROM metatile       real emitted artifacts, post-quant,
#               (bottom+top RGBA, palette resolved)
#   rom_tile    sha1 of the DECODED 8x8 quadrant       FLIP-CANONICAL: the min over the 4
#               (RGBA, palette resolved)               h/v flips of the pixel block.
# Flip decision: the emitter flip-dedups 8x8 tiles, so one stored tile may be used
# mirrored by one map and upright by another; two blocks that differ only by a flip are
# the same ROM tile for sharing purposes. Pixels are compared as palette COLOURS, so the
# same art under different palette-index layouts still matches. Fully transparent
# quadrants (and empty metatiles) are never counted. ROM sets cover the metatiles the map
# actually uses (cells), not the tileset's unused void/door/stair copies, so the four
# bases measure the same population. A map with no uranium<1000+id> artifacts has
# ``rom: null`` and null ROM sets/pairs.

SHARED_BASES = ("rmxp_id", "rmxp_image", "rom_mt", "rom_tile")
_CELL_BASES = ("rmxp_id", "rmxp_image", "rom_mt")  # bases with a per-cell highlight

_shared_profile_cache: dict[int, tuple[tuple, dict]] = {}
_shared_result_cache: dict[tuple[int, ...], tuple[tuple, dict]] = {}


def canon_tile_hash(rgba: np.ndarray) -> str | None:
    """Flip-canonical sha1 of an 8x8 RGBA block; None if fully transparent."""
    if not np.any(rgba[..., 3]):
        return None
    best: bytes | None = None
    for blk in (rgba, rgba[:, ::-1], rgba[::-1, :], rgba[::-1, ::-1]):
        b = np.ascontiguousarray(blk).tobytes()
        if best is None or b < best:
            best = b
    return hashlib.sha1(best).hexdigest()


def rom_metatile_hashes(bottom: np.ndarray, top: np.ndarray) -> tuple[str | None, list[str]]:
    """(metatile hash or None if both layers are transparent, flip-canonical hashes of
    its non-transparent 8x8 quadrants) from a decoded ROM metatile's RGBA layers."""
    tiles: list[str] = []
    for layer in (bottom, top):
        for r in (0, 8):
            for c in (0, 8):
                h = canon_tile_hash(layer[r:r + 8, c:c + 8])
                if h is not None:
                    tiles.append(h)
    if not np.any(bottom[..., 3]) and not np.any(top[..., 3]):
        return None, tiles
    h = hashlib.sha1()
    h.update(np.ascontiguousarray(bottom).tobytes())
    h.update(np.ascontiguousarray(top).tobytes())
    return h.hexdigest(), tiles


def pair_stats(a: set | None, b: set | None) -> dict | None:
    """Shared / only-A / only-B unique-key counts; None if either side is absent."""
    if a is None or b is None:
        return None
    s = len(a & b)
    return {"shared": s, "only_a": len(a) - s, "only_b": len(b) - s}


def shared_cells(cell_keys: list, partner: set | None) -> list[int] | None:
    """Flat (row-major) indices of cells whose key is in *partner*; None if either the
    map's keys or the partner set is absent. Empty cells (None) never match."""
    if partner is None or cell_keys is None:
        return None
    return [i for i, k in enumerate(cell_keys) if k is not None and k in partner]


def build_shared(profiles: dict[int, dict]) -> dict:
    """Assemble the /api/shared payload from per-map profiles. A profile is
    ``{"w","h","tileset","rom": dict|None, "sets": {basis: set|None},
    "cells": {basis: list|None}}`` (cells: per-cell key, None = empty)."""
    ids = sorted(profiles)
    maps: dict[str, dict] = {}
    for m in ids:
        p = profiles[m]
        maps[str(m)] = {
            "w": p["w"], "h": p["h"], "rmxp_tileset": p["tileset"], "rom": p["rom"],
            "counts": {b: (None if p["sets"][b] is None else len(p["sets"][b]))
                       for b in SHARED_BASES},
        }
    pairs = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            e: dict = {"a": a, "b": b}
            for basis in SHARED_BASES:
                e[basis] = pair_stats(profiles[a]["sets"][basis], profiles[b]["sets"][basis])
            pairs.append(e)
    cells: dict[str, dict] = {}
    for a in ids:
        cells[str(a)] = {
            str(b): {basis: shared_cells(profiles[a]["cells"][basis], profiles[b]["sets"][basis])
                     for basis in _CELL_BASES}
            for b in ids if b != a
        }
    return {"maps": ids, "bases": list(SHARED_BASES), "info": maps, "pairs": pairs, "cells": cells}


def _rom_artifact_dirs(map_id: int) -> tuple[int, Path, Path] | None:
    """(synth tileset id, primary dir, secondary dir) of the map's emitted per-map
    tileset, or None if either directory is absent."""
    from rpg2gba.tileset_converter.map_set import (
        SLICE_MAP_IDS,
        load_slice_tileset_groups,
        synth_tileset_id,
    )
    from verify_viewer_rom_match import _output_dir, _resolve_fork

    # Group id (maps joined by an emitted connection share one emitted tileset);
    # a non-slice map keeps its own per-map id.
    synth = load_slice_tileset_groups(_output_dir(), SLICE_MAP_IDS).get(
        map_id, synth_tileset_id(map_id)
    )
    base = _resolve_fork() / "data" / "tilesets"
    prim, sec = base / "primary" / f"uranium{synth}", base / "secondary" / f"uranium{synth}"
    if prim.is_dir() and sec.is_dir():
        return synth, prim, sec
    return None


def _artifact_stat(dirs: tuple[int, Path, Path] | None) -> tuple:
    """(path, mtime_ns, size) of every artifact file; () when there are none."""
    if dirs is None:
        return ()
    out = []
    for d in dirs[1:]:
        for p in sorted(d.rglob("*")):
            if p.is_file():
                st = p.stat()
                out.append((str(p), st.st_mtime_ns, st.st_size))
    return tuple(out)


def _shared_profile(map_id: int) -> dict:
    """One map's shared-tiles profile (cached by member fingerprint + artifact stats)."""
    from verify_viewer_rom_match import load_tileset_rom

    _ensure_loaded(map_id)
    state = _map_cache[map_id]
    dirs = _rom_artifact_dirs(map_id)
    key = (state.input_fingerprint, _artifact_stat(dirs))
    hit = _shared_profile_cache.get(map_id)
    if hit is not None and hit[0] == key:
        return hit[1]
    rom = load_tileset_rom(dirs[1], dirs[2]) if dirs is not None else None
    w, h = state.grid.xsize, state.grid.ysize
    memo: dict[int, tuple] = {}

    def per_idx(idx: int) -> tuple:
        if idx in memo:
            return memo[idx]
        ck = state.colkeys_sorted[idx]
        mt = state.metatile_imgs[idx]
        if not ck or mt is None:
            res: tuple = (None, None, None, [])
        else:
            rid, rtiles = None, []
            if rom is not None:
                ri = state.pool_key_to_idx.get(ck)
                if ri is not None and ri < rom.n_metatiles():
                    rid, rtiles = rom_metatile_hashes(*rom.decode_metatile(ri))
            res = (repr((state.tileset_id, ck)), metatile_image_hash(mt), rid, rtiles)
        memo[idx] = res
        return res

    cells: dict[str, list] = {b: [] for b in _CELL_BASES}
    for y in range(h):
        for x in range(w):
            rk, ih, rm, _ = per_idx(state.colkey_to_idx[column_key(state.grid, x, y)])
            cells["rmxp_id"].append(rk)
            cells["rmxp_image"].append(ih)
            cells["rom_mt"].append(rm)
    tile_set: set[str] = set()
    for _rk, _ih, _rm, tl in memo.values():
        tile_set.update(tl)
    sets: dict[str, set | None] = {
        b: {k for k in cells[b] if k is not None} for b in _CELL_BASES
    }
    sets["rom_tile"] = tile_set
    if rom is None:
        sets["rom_mt"] = sets["rom_tile"] = None
        cells["rom_mt"] = None  # type: ignore[assignment]
    profile = {
        "w": w, "h": h, "tileset": state.tileset_id, "sets": sets, "cells": cells,
        "rom": None if dirs is None else {
            "synth_tileset": dirs[0], "n_metatiles": rom.n_metatiles(),  # type: ignore[union-attr]
        },
    }
    _shared_profile_cache[map_id] = (key, profile)
    return profile


def shared_tiles(map_ids: list[int]) -> dict:
    """The /api/shared payload for *map_ids* (deduped, sorted). Cached by the members'
    profile keys; a rebuild or new artifacts change the key."""
    ids = tuple(sorted(set(map_ids)))
    if len(ids) < 2:
        raise ValueError("shared tiles needs at least two maps")
    profiles = {m: _shared_profile(m) for m in ids}
    key = tuple(_shared_profile_cache[m][0] for m in ids)
    hit = _shared_result_cache.get(ids)
    if hit is not None and hit[0] == key:
        return hit[1]
    result = build_shared(profiles)
    _shared_result_cache[ids] = (key, result)
    return result


def shared_default_maps(map_id: int) -> list[int]:
    """The default pick for ``/api/shared?map=<id>``: the map's seam component."""
    comp = _seam_component(map_id)
    return list(comp) if comp else [map_id]


# ---------------------------------------------------------------------------
# Palette-sets overlay (/api/palsets): which 8x8 tiles the P2 shared palettes pin
# ---------------------------------------------------------------------------

SHARED_MIN_TILES: int = 8  # make_shared_quantizer's default reservation threshold
_PALSET_CODES = {-1: "empty", 0: "packer", 1: "rock V1", 2: "green G0", 3: "green G1", 4: "green G2"}
_palsets_cache: dict[int, tuple[tuple, dict]] = {}


def palette_sets(map_id: int) -> dict:
    """Classify every 8x8 quadrant of *map_id* against the shared palettes (P2).

    The quantizer sees COMPOSITED columns, not RMXP layers: each metatile has a bottom
    and a top BG layer (slots 0-3 / 4-7), so the grids are per ROM BG layer
    (``bottom`` / ``top``), each at 8x8-quadrant resolution (2W x 2H, row-major).
    Codes: -1 empty, 0 packer, 1 rock V1, 2/3/4 green G0/G1/G2. Classification is
    reported whether or not shared palettes are ON; a group below ``threshold`` unique
    tiles is not reserved on the map, so its tiles really go to the packer
    (``effective[code]`` False). Counts are over the flip-canonical unique tiles the
    quantizer sees, same as ``make_shared_quantizer``'s ``info``."""
    from rpg2gba.tileset_converter.graphics.emit import (
        _effective_frames,
        _flip_canonical_multi,
        _slot_frames_for_metatile,
    )
    from rpg2gba.tileset_converter.graphics.quantize import frame_opaque_colors
    from rpg2gba.tileset_converter.graphics.shared_palettes import classify_tile

    _ensure_loaded(map_id)
    state = _map_cache[map_id]
    ckey = (id(state), _quant_generation, _family_params, _shared_palettes)
    hit = _palsets_cache.get(map_id)
    if hit is not None and hit[0] == ckey:
        return hit[1]

    # Same flip-canonical dedup as emit._canonicalize_and_quantize, minus quantizing.
    canon_to_idx: dict[bytes, int] = {}
    unique: list[np.ndarray] = []
    frames_of: list[list[np.ndarray]] = []
    slots_of: dict[int, list[int]] = {}  # colkey idx -> 8 canon idx
    for ci, mt in enumerate(state.metatile_imgs):
        if mt is None:
            continue
        row: list[int] = []
        for fl in _slot_frames_for_metatile(mt):
            key, transformed, _h, _v = _flip_canonical_multi(_effective_frames(fl))
            idx = canon_to_idx.get(key)
            if idx is None:
                idx = len(unique)
                canon_to_idx[key] = idx
                unique.append(transformed[0])
                frames_of.append(transformed)
            row.append(idx)
        slots_of[ci] = row

    classes = []
    for i, fr in enumerate(frames_of):
        extra = None
        if len(fr) > 1:
            cols = [c for c in (frame_opaque_colors(f) for f in fr[1:]) if len(c)]
            if cols:
                extra = np.unique(np.concatenate(cols), axis=0)
        classes.append(classify_tile(
            unique[i], extra, family_params=_family_params, detail=True,
        ))

    def code_of(c) -> int:
        if c.empty:
            return -1
        return {None: 0, "rock": 1}.get(c.group, 2 + (c.palette or 0))

    codes = [code_of(c) for c in classes]
    n_rock = sum(1 for c in codes if c == 1)
    n_green = sum(1 for c in codes if c >= 2)
    rock_res = n_rock >= SHARED_MIN_TILES
    green_res = n_green >= SHARED_MIN_TILES
    tile_info = [
        [codes[i],
         c.rock_fit[0] if c.rock_fit else None, c.rock_fit[1] if c.rock_fit else None,
         c.green_fit[0] if c.green_fit else None, c.green_fit[1] if c.green_fit else None,
         c.green_fit[2] if c.green_fit else None]
        for i, c in enumerate(classes)
    ]

    grid = state.grid
    W, H = grid.xsize, grid.ysize
    tiles = {"bottom": [-1] * (4 * W * H), "top": [-1] * (4 * W * H)}
    for y in range(H):
        for x in range(W):
            row = slots_of.get(state.colkey_to_idx[column_key(grid, x, y)])
            if row is None:
                continue
            for layer, base in (("bottom", 0), ("top", 4)):
                arr = tiles[layer]
                for q in range(4):
                    arr[(2 * y + q // 2) * 2 * W + 2 * x + q % 2] = row[base + q]
    code_grids = {
        k: [codes[t] if t >= 0 else -1 for t in v] for k, v in tiles.items()
    }
    count_by_code: dict[str, dict[str, int]] = {}
    for k, v in code_grids.items():
        cnt: dict[str, int] = {}
        for c in v:
            cnt[str(c)] = cnt.get(str(c), 0) + 1
        count_by_code[k] = cnt
    out = {
        "map_id": map_id,
        "width": 2 * W, "height": 2 * H,
        "layers": ["bottom", "top"],
        "code_names": {str(k): v for k, v in _PALSET_CODES.items()},
        "codes": code_grids,
        "tiles": tiles,
        "tile_info": tile_info,  # [code, rock_shift, rock_sse, green_idx, green_shift, green_sse]
        "counts_quadrants": count_by_code,
        "counts_unique_tiles": {
            str(c): codes.count(c) for c in sorted(set(codes))
        },
        "reservation": {
            "n_rock": n_rock, "n_green": n_green, "threshold": SHARED_MIN_TILES,
            "rock_reserved": rock_res, "green_reserved": green_res,
        },
        "effective": {"-1": False, "0": True, "1": rock_res,
                      "2": green_res, "3": green_res, "4": green_res},
        "shared_on": bool(_shared_palettes),
    }
    _palsets_cache[map_id] = (ckey, out)
    return out


def render_npc_png(character_name: str) -> bytes:
    """Render one NPC's sheet to PNG bytes (cached by lowercased name).

    Always frame 0 (RMXP's down-facing idle, or the intact/idle frame for a
    break-prop/large-prop sheet) -- the viewer just needs a recognizable
    sprite per event, not per-direction accuracy. Raises FileNotFoundError if
    the sheet isn't under RPG2GBA_URANIUM_SRC/Graphics/Characters (fails loud;
    the client falls back to a dot marker on a 404).

    A sheet the converter rejects (e.g. ``light``, a 46x45 additive glow that the
    ROM strips via ``strip_list.json``) is also surfaced as FileNotFoundError, so it
    404s to the same dot marker; the rejection is logged once and remembered.
    """
    key = character_name.lower()
    if key in _npc_png_cache:
        return _npc_png_cache[key]
    if key in _npc_unconvertible:
        raise FileNotFoundError(_npc_unconvertible[key])
    sheet_path = _resolve_sheet(_characters_dir(), character_name)
    try:
        sprite = convert_character_sheet(sheet_path)
    except ValueError as exc:
        log.warning("NPC sheet %s not convertible, drawing a dot: %s", character_name, exc)
        _npc_unconvertible[key] = str(exc)
        raise FileNotFoundError(str(exc)) from exc
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


def build_map_data(map_id: int, seam: bool = False) -> dict:
    """Return all per-map data WITHOUT inline image bytes.

    Distinct column keys are assigned stable integer indices (``colkeys_list``);
    cells reference these via ``colkey_idx`` rather than the URL-unsafe colkey
    string.  Per-cell tile references stay as ``tile_id`` ints.
    Use ``render_tile_png`` / ``render_metatile_png`` to obtain image bytes.

    ``seam=True`` reports the seam-palette analysis (palettes shared across the map's
    seam component) instead of the per-map one; a map in no component is unchanged.
    """
    _ensure_loaded(map_id)
    state = _map_cache[map_id]
    seam_comp = _seam_component(map_id)
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
    view = _quant_view(map_id, seam)
    analysis, pool_key_to_idx = view.analysis, view.pool_key_to_idx

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
            "atlas": {"cols": ATLAS_COLS, "cell": ATLAS_CELL_PX, "count": len(state.metatile_imgs)},
            "shared_palettes": _shared_info.get(map_id) if _shared_palettes else None,
            "tile_merge": bool(_tile_merge),
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
        "seam": {
            "component": list(seam_comp) if seam_comp else None,
            "active": bool(seam and seam_comp),
        },
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
