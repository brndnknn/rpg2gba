#!/usr/bin/env python3
"""Independent oracle: decode the REAL emitted GBA tileset artifacts and byte-
compare them against the pipeline's own quantize+emit simulation.

The pipeline (``build_slice_tilesets.py`` + ``emit.py``) writes, per slice
tileset, a PRIMARY+SECONDARY pokeemerald-expansion tileset pair under
``$RPG2GBA_POKEEMERALD/data/tilesets/{primary,secondary}/uranium<ts>/``
(``tiles.png``, ``palettes/NN.pal``, ``metatiles.bin``,
``metatile_attributes.bin``). Separately, the map viewer (``map_viewer_common.py``)
re-simulates the SAME quantize step for its preview. This script is a THIRD,
independent path: it reconstructs the exact metatile list the build produced
(same helpers, same order, read-only), re-runs the quantizer, and decodes the
literal emitted bytes back into RGBA -- then compares the two, pixel-for-pixel,
without going through either the viewer's code or the pipeline's own emit
path. A clean match here proves the ROM bytes really are what the pipeline
intended; a mismatch pinpoints exactly which metatile/layer/pixel disagrees.

Mode A (--mode pipeline, DEFAULT): the ROM bytes vs. the pipeline's own
quantize+emit simulation (`emit.analyze_tileset_palettes` with the same
quantizer `build_slice_tilesets.py` used). No viewer code touched.

Mode B (--mode viewer): the ROM bytes vs. `scripts/map_viewer_common.py`'s own
render path (`render_metatile_png`), so the two independent CONSUMERS of the
same `tileset_map.gen.json` (the ROM build and the live viewer) can be checked
against each other directly. Implemented, but see `run_viewer_mode`'s
docstring -- it documents unverified assumptions about the concurrently-edited
`map_viewer_common.py` and should be run (and re-checked) only after that
file's edits land.

Usage:
    python scripts/verify_viewer_rom_match.py                    # Mode A (default)
    python scripts/verify_viewer_rom_match.py --mode pipeline
    python scripts/verify_viewer_rom_match.py --mode viewer       # see caveats above
    python scripts/verify_viewer_rom_match.py -v                  # debug logging

Exit 0 if every compared tileset matches byte-for-byte (mask + colour, on
opaque pixels); 1 otherwise (mismatch, missing artifacts, or a reconstruction
that disagrees with reference/tileset_map.gen.json -- in which case the pixel
comparison is skipped for that tileset, since it would be meaningless).
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY_PATH = REPO_ROOT / "reference" / "tileset_map.gen.json"


# ---------------------------------------------------------------------------
# Env / path resolution (mirrors scripts/assemble_pathfinder.py::_load_dotenv)
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


def _resolve_fork() -> Path:
    """$RPG2GBA_POKEEMERALD, falling back to .env-paths (shell wins)."""
    _load_dotenv(REPO_ROOT)
    fork_path = os.environ.get("RPG2GBA_POKEEMERALD")
    if not fork_path:
        raise RuntimeError(
            "RPG2GBA_POKEEMERALD not set (and .env-paths didn't provide it)"
        )
    fork = Path(fork_path)
    if not fork.is_dir():
        raise RuntimeError(f"fork not found: {fork}")
    return fork


def _output_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"


def _grouped_slice_maps(
    out_dir: Path, slice_map_ids: list[int]
) -> dict[int, list[tuple[int, dict]]]:
    """Group SLICE_MAP_IDS maps by real tileset_id, in encounter order -- mirrors
    build_slice_tilesets.py's ``by_ts`` construction (~line 249-251)."""
    by_ts: dict[int, list[tuple[int, dict]]] = {}
    for map_id in slice_map_ids:
        map_json = json.loads(
            (out_dir / "maps" / f"Map{map_id:03d}.json").read_text(encoding="utf-8")
        )
        by_ts.setdefault(int(map_json["tileset_id"]), []).append((map_id, map_json))
    return by_ts


# ---------------------------------------------------------------------------
# Mode A: reconstruct the metatile list build_slice_tilesets.py built
# ---------------------------------------------------------------------------


@dataclass
class Reconstruction:
    ts: int
    metatile_list: list  # list[MetatileImage]
    ordered: list[tuple]  # column keys, in metatile-index order (void/door excluded)
    void_idx: int
    warp_tiles: dict[str, int]
    warp_fallback_idx: int | None
    door_keys: set


def _reconstruct_tileset(
    ts: int,
    maplist: list[tuple[int, dict]],
    warp_coords: dict[int, set[tuple[int, int]]],
    fork: Path,
    tilesets_json: Path,
    terrain_table,
) -> Reconstruction:
    """Replicate build_slice_tilesets.py's per-tileset metatile-list construction
    (same helpers, same order), writing nothing. Mirrors
    src/rpg2gba/tileset_converter/graphics/build_slice_tilesets.py ~lines 260-370
    (the loop body of build_slice_tilesets, for one tileset, with
    source_tileset_of=None so `resolve(ts) == ts` throughout -- matches the real
    build's call in scripts/assemble_pathfinder.py::run_graphics_pass)."""
    from rpg2gba.tileset_converter.graphics import build_slice_tilesets as bst
    from rpg2gba.tileset_converter.graphics.sources import STATIC_BASE
    from rpg2gba.tileset_converter.layout import column_key
    from rpg2gba.tileset_converter.tile_map import serialize_column_key

    rast = bst._default_rasterizer(ts, tilesets_json, None)
    priorities = bst._load_priorities(tilesets_json, ts)
    terrain_tags = bst._load_terrain_tags(tilesets_json, ts)

    ordered = bst.column_keys_for_maps(maplist)
    max_tid = rast.max_static_tile_id()

    def _in_atlas(k: tuple) -> bool:
        return all(tid < STATIC_BASE or tid <= max_tid for _, tid in k)

    garbage = len(ordered) - len([k for k in ordered if _in_atlas(k)])
    if garbage:
        logger.warning(
            "tileset %d: %d out-of-atlas column key(s) dropped (matches build)",
            ts, garbage,
        )
    ordered = [k for k in ordered if _in_atlas(k)]
    if not ordered:
        raise ValueError(f"tileset {ts}: no non-empty in-atlas columns")

    door_keys: set = set()
    for map_id, map_json in maplist:
        grid = bst._grid_of(map_json)
        for wx, wy in warp_coords.get(map_id, set()):
            dk = column_key(grid, wx, wy)
            if dk and _in_atlas(dk):
                door_keys.add(dk)

    opaque_cache: dict[int, bool] = {}

    def _is_opaque(tile_id: int) -> bool:
        hit = opaque_cache.get(tile_id)
        if hit is None:
            alpha = np.asarray(rast.render(tile_id).convert("RGBA"))[..., 3]
            hit = bool((alpha == 255).all())
            opaque_cache[tile_id] = hit
        return hit

    metatile_list = [
        bst._render_column(
            k, rast, priorities,
            behavior=terrain_table.column_behavior(ts, k, terrain_tags, is_opaque=_is_opaque),
        )
        for k in ordered
    ]
    void_idx = len(metatile_list)
    metatile_list.append(bst._void_metatile())

    needs_warp = any(warp_coords.get(mid) for mid, _ in maplist)
    warp_tiles: dict[str, int] = {}
    warp_fallback_idx: int | None = None
    if needs_warp:
        door_behavior = bst._behavior_value(fork, "MB_NON_ANIMATED_DOOR")
        for k in sorted(door_keys):
            idx = len(metatile_list)
            metatile_list.append(bst._render_column(k, rast, priorities, behavior=door_behavior))
            warp_tiles[serialize_column_key(k)] = idx
        warp_fallback_idx = len(metatile_list)
        z = np.zeros((16, 16, 4), dtype=np.uint8)
        metatile_list.append(bst.MetatileImage(z, z.copy(), bst.LAYER_COVERED, door_behavior))

    return Reconstruction(
        ts=ts, metatile_list=metatile_list, ordered=ordered, void_idx=void_idx,
        warp_tiles=warp_tiles, warp_fallback_idx=warp_fallback_idx, door_keys=door_keys,
    )


def _cross_check_overlay(recon: Reconstruction, overlay: dict) -> list[str]:
    """Compare the reconstructed column-key -> metatile-index mapping (and warp
    mapping) against the build's own reference/tileset_map.gen.json overlay.
    Returns a list of human-readable problems (empty == clean agreement)."""
    from rpg2gba.tileset_converter.tile_map import serialize_column_key

    problems: list[str] = []
    ts_str = str(recon.ts)
    tiles_for_ts = {
        k: v["metatile"] for k, v in overlay.get("tiles", {}).get(ts_str, {}).items()
    }
    recon_tiles = {serialize_column_key(k): i for i, k in enumerate(recon.ordered)}
    if tiles_for_ts != recon_tiles:
        missing = set(recon_tiles) - set(tiles_for_ts)
        extra = set(tiles_for_ts) - set(recon_tiles)
        differing = {
            k for k in (set(recon_tiles) & set(tiles_for_ts))
            if recon_tiles[k] != tiles_for_ts[k]
        }
        problems.append(
            f"tiles mapping mismatch: {len(missing)} missing from overlay, "
            f"{len(extra)} extra in overlay, {len(differing)} differing index"
        )

    warps_for_ts = overlay.get("warps", {}).get(ts_str)
    if warps_for_ts is not None:
        if warps_for_ts.get("tiles") != recon.warp_tiles:
            problems.append(
                f"warps.tiles mismatch: overlay={warps_for_ts.get('tiles')} "
                f"reconstructed={recon.warp_tiles}"
            )
        if warps_for_ts.get("fallback") != recon.warp_fallback_idx:
            problems.append(
                f"warps.fallback mismatch: overlay={warps_for_ts.get('fallback')} "
                f"reconstructed={recon.warp_fallback_idx}"
            )
    elif recon.warp_fallback_idx is not None:
        problems.append("overlay has no warps entry but reconstruction produced one")

    return problems


# ---------------------------------------------------------------------------
# ROM-artifact decode (shared by Mode A and Mode B)
# ---------------------------------------------------------------------------

_NUM_PALS_IN_PRIMARY = 6   # engine/include/fieldmap.h NUM_PALS_IN_PRIMARY (verified below)
_NUM_TILES_IN_PRIMARY = 512


def _read_pal16(path: Path) -> np.ndarray:
    """Decode a JASC-PAL file into its 16 RGB colours (index 0 = the dummy
    transparent slot, always (0,0,0); indices 1..15 are the real palette)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    colors = []
    for line in lines[3:19]:
        r, g, b = (int(x) for x in line.split())
        colors.append((r, g, b))
    if len(colors) != 16:
        raise ValueError(f"{path}: expected 16 JASC-PAL colour lines, got {len(colors)}")
    return np.array(colors, dtype=np.uint8)


def _read_tiles_png(path: Path) -> np.ndarray:
    """Raw 4bpp palette-index pixels (0..15) -- the embedded PNG palette is a
    dummy greyscale ramp and must be ignored (see emit.py's `_write_tiles_png`)."""
    img = Image.open(path)
    if img.mode != "P":
        raise ValueError(f"{path}: expected P-mode PNG, got {img.mode!r}")
    arr = np.asarray(img)
    if arr.max(initial=0) > 15:
        raise ValueError(f"{path}: pixel value > 15 found ({arr.max()}) -- not 4bpp indices")
    return arr


def _read_metatiles_bin(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if len(data) % 16 != 0:
        raise ValueError(f"{path}: {len(data)} bytes is not a multiple of 16 (8 u16/metatile)")
    return np.frombuffer(data, dtype="<u2").reshape(-1, 8)


def _read_attrs_bin(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if len(data) % 2 != 0:
        raise ValueError(f"{path}: odd byte length for a u16 array")
    return np.frombuffer(data, dtype="<u2")


@dataclass
class TilesetROM:
    """Decoded view of one emitted PRIMARY+SECONDARY tileset pair."""

    primary_dir: Path
    secondary_dir: Path
    tiles_prim: np.ndarray
    tiles_sec: np.ndarray
    metatiles_prim: np.ndarray
    metatiles_sec: np.ndarray
    attrs_prim: np.ndarray
    attrs_sec: np.ndarray
    _pal_cache: dict[int, np.ndarray] = field(default_factory=dict)

    def n_metatiles(self) -> int:
        return len(self.metatiles_prim) + len(self.metatiles_sec)

    def _entries(self, i: int) -> np.ndarray:
        if i < len(self.metatiles_prim):
            return self.metatiles_prim[i]
        return self.metatiles_sec[i - len(self.metatiles_prim)]

    def _palette(self, palnum: int) -> np.ndarray:
        """The 16-colour palette for GBA palette slot `palnum`. Primary and
        secondary each write ALL 16 NN.pal files, but only one side carries real
        (non-dummy) data for a given slot: primary owns 0..NUM_PALS_IN_PRIMARY-1,
        secondary owns the rest (verified against engine/include/fieldmap.h and
        by inspecting the actual .pal contents -- the two sides are NOT
        interchangeable, unlike the docstring's "if identical, either works"
        hedge suggested; they differ, so side selection matters)."""
        if palnum not in self._pal_cache:
            side_dir = self.primary_dir if palnum < _NUM_PALS_IN_PRIMARY else self.secondary_dir
            self._pal_cache[palnum] = _read_pal16(side_dir / "palettes" / f"{palnum:02}.pal")
        return self._pal_cache[palnum]

    def _tile_pixels(self, gba_tile: int) -> np.ndarray:
        if gba_tile < _NUM_TILES_IN_PRIMARY:
            arr, local = self.tiles_prim, gba_tile
        else:
            arr, local = self.tiles_sec, gba_tile - _NUM_TILES_IN_PRIMARY
        row, col = local // 16, local % 16
        return arr[row * 8 : row * 8 + 8, col * 8 : col * 8 + 8]

    def _decode_quadrant(self, entry: int) -> np.ndarray:
        tile = entry & 0x3FF
        hflip = (entry >> 10) & 1
        vflip = (entry >> 11) & 1
        palnum = (entry >> 12) & 0xF
        idxs = self._tile_pixels(tile)
        pal = self._palette(palnum)
        rgb = pal[idxs]
        alpha = np.where(idxs > 0, 255, 0).astype(np.uint8)
        rgba = np.dstack([rgb, alpha]).astype(np.uint8)
        if hflip:
            rgba = rgba[:, ::-1]
        if vflip:
            rgba = rgba[::-1, :]
        return rgba

    def decode_metatile(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """Reassemble metatile `i`'s bottom + top 16x16 RGBA from the real
        emitted bytes -- the ROM-side counterpart of emit.py's
        ``_reassemble_quantized``."""
        entries = self._entries(i)
        bottom = np.zeros((16, 16, 4), dtype=np.uint8)
        top = np.zeros((16, 16, 4), dtype=np.uint8)
        positions = [(0, 0), (0, 8), (8, 0), (8, 8)]  # TL, TR, BL, BR
        for layer_arr, base in ((bottom, 0), (top, 4)):
            for q, (r, c) in enumerate(positions):
                layer_arr[r : r + 8, c : c + 8] = self._decode_quadrant(int(entries[base + q]))
        return bottom, top


def load_tileset_rom(primary_dir: Path, secondary_dir: Path) -> TilesetROM:
    for d in (primary_dir, secondary_dir):
        if not d.is_dir():
            raise FileNotFoundError(f"tileset artifact directory missing: {d}")
    return TilesetROM(
        primary_dir=primary_dir,
        secondary_dir=secondary_dir,
        tiles_prim=_read_tiles_png(primary_dir / "tiles.png"),
        tiles_sec=_read_tiles_png(secondary_dir / "tiles.png"),
        metatiles_prim=_read_metatiles_bin(primary_dir / "metatiles.bin"),
        metatiles_sec=_read_metatiles_bin(secondary_dir / "metatiles.bin"),
        attrs_prim=_read_attrs_bin(primary_dir / "metatile_attributes.bin"),
        attrs_sec=_read_attrs_bin(secondary_dir / "metatile_attributes.bin"),
    )


# ---------------------------------------------------------------------------
# Pixel comparison
# ---------------------------------------------------------------------------


def _compare_rgba(expected: np.ndarray, decoded: np.ndarray) -> np.ndarray:
    """Boolean (16,16) mismatch mask: disagreement on the opacity mask itself,
    or (when both sides agree the pixel is opaque) disagreement on colour."""
    exp_op = expected[..., 3] == 255
    dec_op = decoded[..., 3] == 255
    mask_mismatch = exp_op != dec_op
    color_mismatch = exp_op & dec_op & (expected[..., :3] != decoded[..., :3]).any(-1)
    return mask_mismatch | color_mismatch


def _report_layer(
    label: str, mt_idx: int, layer: str, expected: np.ndarray, decoded: np.ndarray,
    examples_limit: int = 3,
) -> int:
    bad = _compare_rgba(expected, decoded)
    n = int(bad.sum())
    if n:
        ys, xs = np.nonzero(bad)
        print(f"    MISMATCH {label} metatile {mt_idx} [{layer}]: {n} differing px")
        for x, y in list(zip(xs.tolist(), ys.tolist()))[:examples_limit]:
            sim = tuple(int(v) for v in expected[y, x])
            rom = tuple(int(v) for v in decoded[y, x])
            print(f"      (x={x}, y={y}) simulated={sim} decoded={rom}")
    return n


# ---------------------------------------------------------------------------
# Mode A: pipeline simulation vs. decoded ROM bytes
# ---------------------------------------------------------------------------


def run_pipeline_mode() -> int:
    fork = _resolve_fork()
    out_dir = _output_dir()
    tilesets_json = out_dir / "tilesets.json"

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import assemble_pathfinder as ap  # WARP_OVERRIDES -- the real build's exact input

    from rpg2gba.tileset_converter.graphics.emit import (
        NUM_METATILES_IN_PRIMARY,
        NUM_PALS_TOTAL,
        analyze_tileset_palettes,
    )
    from rpg2gba.tileset_converter.graphics.quantize import build_quantized_tileset_family
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS
    from rpg2gba.tileset_converter.terrain_tags import load_terrain_tag_map

    if not tilesets_json.is_file():
        print(f"MISSING: {tilesets_json} -- run the phase-3/5 pipeline first", file=sys.stderr)
        return 1
    if not OVERLAY_PATH.is_file():
        print(f"MISSING: {OVERLAY_PATH} -- run assemble_pathfinder.py first", file=sys.stderr)
        return 1

    overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
    by_ts = _grouped_slice_maps(out_dir, SLICE_MAP_IDS)
    terrain_table = load_terrain_tag_map(fork)

    overall_ok = True
    for ts, maplist in sorted(by_ts.items()):
        maps_desc = "+".join(f"Map{m:03d}" for m, _ in maplist)
        print(f"=== tileset {ts} ({maps_desc}) ===")

        recon = _reconstruct_tileset(
            ts, maplist, ap.WARP_OVERRIDES, fork, tilesets_json, terrain_table,
        )

        problems = _cross_check_overlay(recon, overlay)
        if problems:
            print(f"  RECONSTRUCTION DIVERGED from {OVERLAY_PATH.name} for ts{ts}:")
            for p in problems:
                print(f"    - {p}")
            print("  Skipping pixel comparison for this tileset (would be meaningless).")
            overall_ok = False
            continue
        print(
            f"  reconstruction agrees with {OVERLAY_PATH.name}: {len(recon.ordered)} columns, "
            f"void@{recon.void_idx}, {len(recon.door_keys)} door metatile(s), "
            f"fallback@{recon.warp_fallback_idx}"
        )

        analysis = analyze_tileset_palettes(
            recon.metatile_list, max_palettes=NUM_PALS_TOTAL,
            quantizer=build_quantized_tileset_family,
        )

        primary_dir = fork / "data" / "tilesets" / "primary" / f"uranium{ts}"
        secondary_dir = fork / "data" / "tilesets" / "secondary" / f"uranium{ts}"
        if not primary_dir.is_dir() or not secondary_dir.is_dir():
            print(f"  MISSING ARTIFACTS: {primary_dir} and/or {secondary_dir}")
            overall_ok = False
            continue
        rom = load_tileset_rom(primary_dir, secondary_dir)

        n_metatiles = len(recon.metatile_list)
        # emit.py's Step 7 writes `metatile_entries[512:] or [[0]*8]` (and the
        # primary-side mirror): whichever half is empty (all real metatiles fit
        # in the other) still gets ONE all-zero placeholder metatile so its
        # .bin is never zero-length. That placeholder is real on-disk bytes but
        # not a real metatile -- never referenced by tileset_map.gen.json or any
        # layout cell -- so the expected ROM total is n_metatiles+1 when
        # everything fits in one half, else exactly n_metatiles.
        expected_rom_total = (
            n_metatiles + 1 if n_metatiles <= NUM_METATILES_IN_PRIMARY else n_metatiles
        )
        if rom.n_metatiles() != expected_rom_total:
            print(
                f"  METATILE COUNT MISMATCH: ROM has {rom.n_metatiles()}, expected "
                f"{expected_rom_total} ({n_metatiles} real + emit.py's empty-half "
                f"placeholder) -- stopping comparison for ts{ts}."
            )
            overall_ok = False
            continue

        mismatch_px = 0
        mismatch_mts = 0
        for i in range(n_metatiles):
            mp = analysis.metatiles[i]
            dec_bottom, dec_top = rom.decode_metatile(i)
            n_bot = _report_layer(f"ts{ts}", i, "bottom", mp.quant_bottom, dec_bottom)
            n_top = _report_layer(f"ts{ts}", i, "top", mp.quant_top, dec_top)
            if n_bot or n_top:
                mismatch_mts += 1
            mismatch_px += n_bot + n_top

        total_px = n_metatiles * 2 * 16 * 16
        print(
            f"  RESULT ts{ts}: {n_metatiles} metatiles compared, "
            f"{mismatch_mts} metatile(s) with a mismatch, "
            f"{mismatch_px}/{total_px} differing px"
        )
        if mismatch_px:
            overall_ok = False

    return 0 if overall_ok else 1


# ---------------------------------------------------------------------------
# Mode B: decoded ROM bytes vs. map_viewer_common.py's own render path
# ---------------------------------------------------------------------------


def run_viewer_mode() -> int:
    """NOT RUN as part of this script's own verification pass -- implemented per
    spec, to be run by the lead once scripts/map_viewer_common.py's concurrent
    edit lands. Assumptions below were read from that file's state as of
    2026-07-12 and MUST be re-checked before trusting a result:

      - ``build_map_data(map_id)['colkeys_list'][i]`` is
        ``serialize_column_key(colkeys_sorted[i])`` for map_id's OWN per-map
        column-key list (confirmed at map_viewer_common.py:619 as read). This
        per-map list is NOT the tileset-wide ``ordered`` list
        build_slice_tilesets.py (and Mode A above) uses -- ``colkeys_sorted`` is
        built from a single map's grid only (``_ensure_loaded``). So a viewer
        colkey_idx and a ROM metatile index are different numbering schemes;
        the only safe join key between them is the SERIALIZED COLUMN-KEY
        STRING, resolved through reference/tileset_map.gen.json's
        ``tiles[str(ts)][colkey_str]['metatile']``.
      - ``render_metatile_png(map_id, idx, layer)`` takes that per-map
        colkey_idx for EVERY layer, including ``'post_bottom'``/``'post_top'``
        (confirmed at map_viewer_common.py:550-577 as read).
      - Use ``'post_bottom'``/``'post_top'`` here, NOT ``'bottom'``/``'top'`` --
        the latter are PRE-quantization composites and will never byte-match
        the ROM even when everything is correct; only the post_* pair is
        documented to "match the shipped ROM's palette assignment".
      - The viewer's quantizer/max_palettes come from the module-level
        ``current_quantize_state()``, mutable via the Advanced tab's
        POST /api/quantize (map_viewer_common.py:357-358's
        ``_max_palettes``/``_make_quantizer()``). If that state has ever been
        changed from the pipeline default (``FamilyParams()``,
        ``NUM_PALS_TOTAL``=13) on a long-running server, a mismatch here is a
        QUANTIZER-PARAMETER difference, not a viewer/ROM bug -- check
        ``current_quantize_state()`` reports the stock default first.
      - ``_ensure_tileset_analysis`` pools every SLICE_MAP_IDS map that shares
        a real tileset_id into ONE shared quantization (Map048+Map049 for
        ts19), matching build_slice_tilesets.py's own grouping -- so opening
        EITHER pooled map_id should give identical post-quant pixels; this
        function only opens one map per tileset (the first in `by_ts`), not
        every pooled member.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import map_viewer_common as mvc  # lazy: concurrently edited, see docstring above

    fork = _resolve_fork()
    out_dir = _output_dir()
    if not OVERLAY_PATH.is_file():
        print(f"MISSING: {OVERLAY_PATH} -- run assemble_pathfinder.py first", file=sys.stderr)
        return 1
    overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))

    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

    by_ts = _grouped_slice_maps(out_dir, SLICE_MAP_IDS)

    overall_ok = True
    for ts, maplist in sorted(by_ts.items()):
        # Walk EVERY pooled map, not just one representative: pooled maps share
        # one tileset analysis, but each map's colkeys_list only covers its own
        # columns, so ts19 needs both Map049 and Map048 to compare all columns.
        pooled_ids = [mid for mid, _ in maplist]
        print(f"=== tileset {ts} (viewer via {', '.join(f'Map{m:03d}' for m in pooled_ids)}) ===")

        tiles_for_ts: dict[str, dict] = overlay.get("tiles", {}).get(str(ts), {})

        primary_dir = fork / "data" / "tilesets" / "primary" / f"uranium{ts}"
        secondary_dir = fork / "data" / "tilesets" / "secondary" / f"uranium{ts}"
        if not primary_dir.is_dir() or not secondary_dir.is_dir():
            print(f"  MISSING ARTIFACTS: {primary_dir} and/or {secondary_dir}")
            overall_ok = False
            continue
        rom = load_tileset_rom(primary_dir, secondary_dir)

        n_compared = 0
        mismatch_px = 0
        seen_rom_idx: set[int] = set()
        for map_id in pooled_ids:
            data = mvc.build_map_data(map_id)
            colkeys_list: list[str] = data["colkeys_list"]
            for colkey_idx, ck_str in enumerate(colkeys_list):
                entry = tiles_for_ts.get(ck_str)
                if entry is None:
                    continue  # empty/void/out-of-atlas column -- no real emitted metatile
                rom_idx = entry["metatile"]
                if rom_idx in seen_rom_idx:
                    continue  # column already compared via a pooled sibling map
                seen_rom_idx.add(rom_idx)
                dec_bottom, dec_top = rom.decode_metatile(rom_idx)

                bottom_png = mvc.render_metatile_png(map_id, colkey_idx, "post_bottom")
                top_png = mvc.render_metatile_png(map_id, colkey_idx, "post_top")
                exp_bottom = np.asarray(Image.open(io.BytesIO(bottom_png)).convert("RGBA"))
                exp_top = np.asarray(Image.open(io.BytesIO(top_png)).convert("RGBA"))

                n_compared += 1
                mismatch_px += _report_layer(f"ts{ts}", rom_idx, "bottom", exp_bottom, dec_bottom)
                mismatch_px += _report_layer(f"ts{ts}", rom_idx, "top", exp_top, dec_top)

        print(
            f"  RESULT ts{ts}: {n_compared} metatiles compared vs viewer, "
            f"{mismatch_px} differing px"
        )
        if mismatch_px:
            overall_ok = False

    return 0 if overall_ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--mode", choices=["pipeline", "viewer"], default="pipeline",
        help="pipeline (default): ROM vs pipeline simulation, no viewer code touched. "
             "viewer: ROM vs scripts/map_viewer_common.py's own render path (see caveats).",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.mode == "viewer":
        return run_viewer_mode()
    return run_pipeline_mode()


if __name__ == "__main__":
    sys.exit(main())
