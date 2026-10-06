#!/usr/bin/env python3
"""Independent oracle: decode the REAL emitted GBA tileset artifacts and byte-
compare them against the pipeline's own quantize+emit simulation.

Per-map tileset scheme (since 4db0deb9, 2026-08-05). The ROM build gives every
slice map its OWN tileset with the synthetic id synth_tileset_id(map_id) ==
1000 + map_id (tileset_converter/map_set.py): assemble_pathfinder.py's
graphics pass rewrites each map's tileset_id to that id on a shallow copy
and passes source_tileset_of so the synthetic id resolves back to the real
RMXP tileset for art / passages / priorities / terrain tags. So there is one
group per map, and the artifacts live at
/data/tilesets/{primary,secondary}/uranium<1000+map_id>/
(tiles.png, palettes/NN.pal, metatiles.bin, metatile_attributes.bin; the C
symbols are gTileset_Uranium<synth> / gTileset_Uranium<synth>B).
Pooling per real RMXP tileset no longer exists. Dirs named uranium<real_ts>
(uranium19, uranium22, *_cmp*) are pre-2026-08-05 leftovers and are
ignored.

Rather than re-deriving the metatile list (which had drifted: animated-tile
frames, inlined stair columns, stair/seam behaviour copies, ...), Mode A calls
the build's OWN build_slice_tilesets with the same arguments the graphics
pass uses (warp overrides, stair + seam-warp behaviour cells via
seam_warps.behavior_cells_for, source_tileset_of), but with
emit_tileset and _write_fragments replaced by capture stubs and the
overlay written to a temp file -- so nothing is written to engine/ or
reference/. The captured metatile lists are then:

  1. the overlay the build just produced is compared, per synthetic tileset,
     against the committed reference/tileset_map.gen.json; and
  2. quantized with the pipeline quantizer (rom_quantize.make_rom_quantizer, the
     same definition the build emits with) and compared pixel-for-pixel with
     the literal bytes decoded from the emitted artifacts.

Maps with no emitted artifacts and no overlay entry (e.g. map 40, in
WALKER_OVERFLOW_MAP_IDS) are reported as SKIPPED, not failed.

Mode A (--mode pipeline, DEFAULT): the ROM bytes vs. the pipeline's own
quantize+emit simulation. No viewer code touched.

Mode B (--mode viewer): the viewer's own post-quant render path
(map_viewer_common: ``_ensure_loaded`` -> per-colkey ``metatile_imgs_postquant``)
vs the decoded ROM artifacts, per slice map. The ROM dedups and renumbers metatiles,
so each viewer column key is looked up in the committed overlay's ``tiles`` table
(column key -> post-dedup ROM metatile index) rather than assumed equal to the pool
index. A tileset shared by connected maps (e.g. 1031) is compared once per member map
against the same ROM artifacts. Runs the viewer's
quantizer once per map (about a minute or two for the whole slice).

Usage:
    python scripts/verify_viewer_rom_match.py                    # Mode A (default)
    python scripts/verify_viewer_rom_match.py --mode pipeline
    python scripts/verify_viewer_rom_match.py --mode viewer      # viewer vs ROM
    python scripts/verify_viewer_rom_match.py -v                  # debug logging

Exit 0 if every compared tileset matches (overlay agreement + byte-for-byte
mask and colour on opaque pixels) and nothing failed; 1 otherwise. Skips do not
fail the run.
"""
from __future__ import annotations

import argparse
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
    out = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
    return out if out.is_absolute() else REPO_ROOT / out


def per_map_inputs(
    out_dir: Path, slice_map_ids: list[int], seam_behavior_cells: dict,
) -> tuple[list[tuple[int, dict]], dict[int, int], dict[int, dict[tuple[int, int], str]]]:
    """Mirror of the map-prep loop in assemble_pathfinder.run_graphics_pass:
    one (map_id, shallow copy with tileset_id = synth id) per slice map, the
    synth -> real RMXP tileset table, and the merged stair + seam-warp behaviour
    cells per map. Returns (maps, synth_to_real, stair_cells)."""
    from rpg2gba.tileset_converter.map_set import load_slice_tileset_groups
    from rpg2gba.tileset_converter.metadata_wiring import collect_stair_behavior_cells

    groups = load_slice_tileset_groups(out_dir, slice_map_ids)
    maps: list[tuple[int, dict]] = []
    synth_to_real: dict[int, int] = {}
    stair_cells: dict[int, dict[tuple[int, int], str]] = {}
    for map_id in slice_map_ids:
        map_json = json.loads(
            (out_dir / "maps" / f"Map{map_id:03d}.json").read_text(encoding="utf-8")
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
    return maps, synth_to_real, stair_cells


# ---------------------------------------------------------------------------
# Mode A: capture the metatile lists the real build_slice_tilesets builds
# ---------------------------------------------------------------------------


@dataclass
class Captured:
    """What the build handed to emit_tileset for one synthetic tileset."""

    synth: int
    metatile_list: list  # list[MetatileImage], in metatile-index order


def run_build_capture(
    out_dir: Path, fork: Path, tilesets_json: Path, overlay_out: Path,
) -> tuple[dict[int, Captured], dict, dict[int, int]]:
    """Run the build's own ``build_slice_tilesets`` exactly as the graphics pass
    does, but with ``emit_tileset`` / ``_write_fragments`` stubbed so no engine
    artifact is written, and the overlay sent to ``overlay_out`` (a temp path).
    Returns (captured per synth id, the freshly built overlay, synth_to_real)."""
    from rpg2gba.tileset_converter.graphics import build_slice_tilesets as bst
    from rpg2gba.tileset_converter.graphics.emit import EmittedTileset
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS
    from rpg2gba.tileset_converter.seam_warps import (
        behavior_cells_for,
        load_seam_warps,
        seams_for_slice,
    )

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import assemble_pathfinder as ap  # the real build's exact input

    slice_seams = seams_for_slice(load_seam_warps(), set(SLICE_MAP_IDS))
    seam_behavior_cells = behavior_cells_for(slice_seams)
    maps, synth_to_real, stair_cells = per_map_inputs(
        out_dir, SLICE_MAP_IDS, seam_behavior_cells,
    )

    captured: dict[int, Captured] = {}

    def _capture_emit(metatile_list, primary_dir, secondary_dir, primary_name,
                      secondary_name, **_kwargs):
        synth = int(primary_name[len("gTileset_Uranium"):])
        captured[synth] = Captured(synth, list(metatile_list))
        return EmittedTileset(
            primary_name=primary_name, secondary_name=secondary_name,
            n_metatiles=len(metatile_list), n_tiles=0, n_palettes=0,
        )

    real_emit, real_frag = bst.emit_tileset, bst._write_fragments
    bst.emit_tileset = _capture_emit
    bst._write_fragments = lambda *_a, **_k: None
    try:
        bst.build_slice_tilesets(
            maps,
            ap._load_warp_overrides(out_dir),
            fork=fork,
            base_tile_map=REPO_ROOT / "reference" / "tileset_map.json",
            overlay_out=overlay_out,
            tilesets_json=tilesets_json,
            source_tileset_of=lambda s: synth_to_real[s],
            stair_cells=stair_cells,
            dry_run=False,
        )
    finally:
        bst.emit_tileset, bst._write_fragments = real_emit, real_frag
    fresh = json.loads(overlay_out.read_text(encoding="utf-8"))
    return captured, fresh, synth_to_real


_OVERLAY_SECTIONS = (
    "tilesets", "tiles", "buckets", "warps", "atlas_max", "behavior_overrides",
    "source_tilesets",
)


def _cross_check_overlay(fresh: dict, committed: dict, synth: int) -> list[str]:
    """Compare the overlay the build just produced against the committed
    reference/tileset_map.gen.json for one synthetic tileset. Returns
    human-readable problems (empty == clean agreement)."""
    problems: list[str] = []
    key = str(synth)
    for section in _OVERLAY_SECTIONS:
        a = fresh.get(section, {}).get(key)
        b = committed.get(section, {}).get(key)
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            missing = set(a) - set(b)
            extra = set(b) - set(a)
            differing = {k for k in set(a) & set(b) if a[k] != b[k]}
            problems.append(
                f"{section}: {len(missing)} only in fresh build, {len(extra)} only in "
                f"committed overlay, {len(differing)} differing"
            )
        else:
            problems.append(f"{section}: fresh={a!r} committed={b!r}")
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


def run_pipeline_mode() -> int:
    import tempfile

    fork = _resolve_fork()
    out_dir = _output_dir()
    tilesets_json = out_dir / "tilesets.json"

    from rpg2gba.tileset_converter.graphics.emit import (
        NUM_METATILES_IN_PRIMARY,
        NUM_PALS_TOTAL,
        analyze_tileset_palettes,
    )
    from rpg2gba.tileset_converter.graphics.rom_quantize import make_rom_quantizer
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS, load_slice_tileset_groups

    groups = load_slice_tileset_groups(out_dir, SLICE_MAP_IDS)

    if not tilesets_json.is_file():
        print(f"MISSING: {tilesets_json} -- run the phase-3/5 pipeline first", file=sys.stderr)
        return 1
    if not OVERLAY_PATH.is_file():
        print(f"MISSING: {OVERLAY_PATH} -- run assemble_pathfinder.py first", file=sys.stderr)
        return 1

    committed = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="verify_rom_match_") as tmp:
        captured, fresh, _synth_to_real = run_build_capture(
            out_dir, fork, tilesets_json, Path(tmp) / "tileset_map.fresh.json",
        )

    passed: list[int] = []
    skipped: list[int] = []
    failed: list[int] = []
    for map_id in SLICE_MAP_IDS:
        synth = groups[map_id]
        print(f"=== Map{map_id:03d} (tileset {synth}) ===")
        primary_dir = fork / "data" / "tilesets" / "primary" / f"uranium{synth}"
        secondary_dir = fork / "data" / "tilesets" / "secondary" / f"uranium{synth}"
        have_artifacts = primary_dir.is_dir() and secondary_dir.is_dir()
        in_committed = str(synth) in committed.get("tilesets", {})
        if not have_artifacts and not in_committed:
            print("  SKIPPED: no emitted artifacts and no entry in the committed overlay")
            skipped.append(map_id)
            continue
        if not have_artifacts:
            print(f"  MISSING ARTIFACTS: {primary_dir} and/or {secondary_dir}")
            failed.append(map_id)
            continue
        if synth not in captured:
            print("  FAIL: the build produced no tileset for this map")
            failed.append(map_id)
            continue

        problems = _cross_check_overlay(fresh, committed, synth)
        if problems:
            print(f"  RECONSTRUCTION DIVERGED from {OVERLAY_PATH.name} for ts{synth}:")
            for p in problems:
                print(f"    - {p}")
            print("  Skipping pixel comparison for this tileset (would be meaningless).")
            failed.append(map_id)
            continue
        metatile_list = captured[synth].metatile_list
        print(f"  fresh build agrees with {OVERLAY_PATH.name}: {len(metatile_list)} metatiles")

        analysis = analyze_tileset_palettes(
            metatile_list, max_palettes=NUM_PALS_TOTAL,
            quantizer=make_rom_quantizer(),
        )
        rom = load_tileset_rom(primary_dir, secondary_dir)

        n_metatiles = len(metatile_list)
        # emit.py's Step 7 writes `metatile_entries[512:] or [[0]*8]`: whichever
        # half is empty still gets ONE all-zero placeholder metatile so its .bin
        # is never zero-length. Never referenced by the overlay or any layout.
        expected_rom_total = (
            n_metatiles + 1 if n_metatiles <= NUM_METATILES_IN_PRIMARY else n_metatiles
        )
        if rom.n_metatiles() != expected_rom_total:
            print(
                f"  METATILE COUNT MISMATCH: ROM has {rom.n_metatiles()}, expected "
                f"{expected_rom_total} ({n_metatiles} real + emit.py's empty-half "
                f"placeholder) -- stopping comparison for ts{synth}."
            )
            failed.append(map_id)
            continue

        mismatch_px = 0
        mismatch_mts = 0
        for i in range(n_metatiles):
            mp = analysis.metatiles[i]
            dec_bottom, dec_top = rom.decode_metatile(i)
            n_bot = _report_layer(f"ts{synth}", i, "bottom", mp.quant_bottom, dec_bottom)
            n_top = _report_layer(f"ts{synth}", i, "top", mp.quant_top, dec_top)
            if n_bot or n_top:
                mismatch_mts += 1
            mismatch_px += n_bot + n_top

        total_px = n_metatiles * 2 * 16 * 16
        print(
            f"  RESULT ts{synth}: {n_metatiles} metatiles compared, "
            f"{mismatch_mts} metatile(s) with a mismatch, "
            f"{mismatch_px}/{total_px} differing px"
        )
        (failed if mismatch_px else passed).append(map_id)

    print(
        f"\nSUMMARY: {len(passed)} passed, {len(skipped)} skipped, {len(failed)} failed "
        f"of {len(SLICE_MAP_IDS)} maps"
    )
    if skipped:
        print(f"  skipped maps: {skipped}")
    if failed:
        print(f"  FAILED maps: {failed}")
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# Mode B: the viewer's post-quant render vs the ROM artifacts
# ---------------------------------------------------------------------------


def rom_index_table(committed: dict, synth: int) -> dict[str, int]:
    """column-key string -> ROM metatile index for one synthetic tileset, read from the
    overlay (reference/tileset_map.gen.json). These indices are POST-dedup: the ROM
    build folds identical metatiles and renumbers, recording the survivor per column."""
    return {
        k: int(v["metatile"]) for k, v in committed.get("tiles", {}).get(str(synth), {}).items()
    }


def compare_viewer_to_rom(
    map_id: int, state, rom: TilesetROM, label: str,
    rom_index: dict[str, int] | None = None,
) -> tuple[int, int, int]:
    """Compare one loaded viewer ``_MapState`` against its decoded ROM tileset.
    Returns (metatiles compared, metatiles with a mismatch, differing px). Each
    distinct non-empty column key is compared once. With ``rom_index`` (the overlay's
    column-key -> ROM metatile table, see ``rom_index_table``) the ROM index is looked
    up through the build's dedup remap and a column missing from it is a hard error;
    without it the viewer pool index is assumed to equal the ROM index (pre-dedup)."""
    from rpg2gba.tileset_converter.tile_map import serialize_column_key

    n_cmp = n_bad_mt = n_px = 0
    for cidx, ck in enumerate(state.colkeys_sorted):
        pq = state.metatile_imgs_postquant[cidx]
        if not ck or pq is None:
            continue
        if rom_index is None:
            rom_idx = state.pool_key_to_idx[ck]
        else:
            skey = serialize_column_key(ck)
            if skey not in rom_index:
                raise KeyError(f"{label}: column key {skey} absent from the overlay")
            rom_idx = rom_index[skey]
        dec_bottom, dec_top = rom.decode_metatile(rom_idx)
        n_bot = _report_layer(label, rom_idx, "bottom", pq[0], dec_bottom)
        n_top = _report_layer(label, rom_idx, "top", pq[1], dec_top)
        n_cmp += 1
        if n_bot or n_top:
            n_bad_mt += 1
        n_px += n_bot + n_top
    return n_cmp, n_bad_mt, n_px


def run_viewer_mode() -> int:
    """Mode B: viewer post-quant pixels vs decoded ROM artifacts, per slice map.
    Maps without artifacts are SKIPPED (e.g. 40); a map whose artifacts exist but
    that the viewer cannot load, or any pixel difference, FAILS."""
    fork = _resolve_fork()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import map_viewer_common as mvc

    mvc._load_dotenv()
    # The viewer boots with the Ward + shared-palettes PREVIEW; this compares to the ROM.
    mvc.set_rom_stock_quantize()
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS, load_slice_tileset_groups

    groups = load_slice_tileset_groups(_output_dir(), SLICE_MAP_IDS)
    committed = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
    passed: list[int] = []
    skipped: list[int] = []
    failed: list[int] = []
    tot_px = tot_mt = 0
    for map_id in SLICE_MAP_IDS:
        synth = groups[map_id]
        print(f"=== Map{map_id:03d} (tileset {synth}) ===")
        primary_dir = fork / "data" / "tilesets" / "primary" / f"uranium{synth}"
        secondary_dir = fork / "data" / "tilesets" / "secondary" / f"uranium{synth}"
        if not (primary_dir.is_dir() and secondary_dir.is_dir()):
            print("  SKIPPED: no emitted artifacts")
            skipped.append(map_id)
            continue
        try:
            mvc._ensure_loaded(map_id)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  FAIL: viewer could not load the map: {exc!r}")
            failed.append(map_id)
            continue
        state = mvc._map_cache[map_id]
        rom = load_tileset_rom(primary_dir, secondary_dir)
        try:
            n_cmp, n_bad_mt, n_px = compare_viewer_to_rom(
                map_id, state, rom, f"ts{synth}", rom_index_table(committed, synth),
            )
        except KeyError as exc:
            print(f"  FAIL: {exc}")
            failed.append(map_id)
            continue
        tot_px += n_px
        tot_mt += n_cmp
        print(
            f"  RESULT ts{synth}: {n_cmp} metatiles compared, {n_bad_mt} with a mismatch, "
            f"{n_px}/{n_cmp * 2 * 16 * 16} differing px"
        )
        (failed if n_px else passed).append(map_id)

    print(
        f"\nSUMMARY (viewer vs ROM): {len(passed)} passed, {len(skipped)} skipped, "
        f"{len(failed)} failed of {len(SLICE_MAP_IDS)} maps; {tot_mt} metatiles, "
        f"{tot_px} differing px total"
    )
    if skipped:
        print(f"  skipped maps: {skipped}")
    if failed:
        print(f"  FAILED maps: {failed}")
    return 0 if not failed else 1


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
             "viewer: the map viewer's post-quant render vs the ROM artifacts.",
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
