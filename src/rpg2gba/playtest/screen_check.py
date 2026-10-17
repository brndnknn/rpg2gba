"""Screen check: is the overworld BG showing exactly what the map says it should?

The correctness test for the streaming tile cache (reference/streaming_prototype_plan.md
§4.3). After each step, rebuild from ROM data and the live map grid the tilemap the
engine *should* hold, then compare it with what is actually in VRAM, cell by cell on
BG1-BG3:

- the flip/palette bits of every tilemap word;
- for a streamed map, that the slot a cell names holds the right tile's pixels
  (the 32 bytes in VRAM equal the pool tile's 32 bytes in ROM), and that pinned
  tiles (tile 0 and the animated block) sit at their own slot number;
- for a stock map, that the cell names the tile index itself (identity).

It reads nothing from the cache's own bookkeeping to decide what is right, so a
stale slot, a missed upload or a refcount bug all show up as mismatches. The cache's
counters (`gFieldStream` overflows/errors) and a refcount recount from the tilemap
buffers are checked on top, as early warnings.

The check runs on a Map Walker ROM (`URANIUM_MAP_WALKER`), which can walk anywhere
and has a harness warp (`gUraniumWalkerHarnessWarp`).
"""
from __future__ import annotations

import json
import logging
import re
import struct
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import click

logger = logging.getLogger(__name__)

# sOverworldBgTemplates (engine/src/overworld.c): BG1-3 tilemaps live in screenblocks
# 29, 28 and 30; their tiles in charblock 0.
VRAM = 0x06000000
SCREENBLOCK = {1: VRAM + 29 * 0x800, 2: VRAM + 28 * 0x800, 3: VRAM + 30 * 0x800}
CHARBLOCK0 = VRAM
TILE_BYTES = 32
NUM_PRIMARY_METATILES = 512  # NUM_METATILES_IN_PRIMARY (non-FRLG)
METATILE_ID_MASK = 0x07FF    # MAPGRID_METATILE_ID_MASK (RPG2GBA STREAMING 11-bit ids)
MAPGRID_UNDEFINED = METATILE_ID_MASK
NUM_METATILES_TOTAL = 2048
MAX_MAP_DATA_SIZE = 10240  # fieldmap.h

LAYER_NORMAL, LAYER_COVERED, LAYER_SPLIT = 0, 1, 2
STOCK_NORMAL_BG3_WORD = 0x3014  # DrawMetatile's "garbage" for the NORMAL layer's BG3

KEYS = {"A": 0, "B": 1, "SELECT": 2, "START": 3, "RIGHT": 4, "LEFT": 5, "UP": 6, "DOWN": 7,
        "R": 8, "L": 9}
DIRS = {"RIGHT": (1, 0), "LEFT": (-1, 0), "UP": (0, -1), "DOWN": (0, 1)}


# -- pure geometry / expectation (unit-tested) ---------------------------------

# The engine keeps 15x15 metatiles of the 16x16 ring buffer current: the
# RedrawMapSlice* functions draw rows/columns 0 and 14 (tiles 0-1 and 28-29), so
# buffer tiles 30-31 on either axis hold whatever scrolled out (still refcounted,
# never on screen at rest).
MAINTAINED_TILES = 30


def cell_metatile(cx: int, cy: int, cam_x: int, cam_y: int,
                  pos_x: int, pos_y: int) -> tuple[int, int, int] | None:
    """Map position and quadrant (0..3, row-major) of ring-buffer cell (cx, cy),
    or None for a cell outside the maintained 15x15 metatiles.

    field_camera.c draws metatile (pos.x + j/2, pos.y + i/2) at buffer tile
    (camTileX + j, camTileY + i) mod 32; the camera tile offsets are always even."""
    dx = (cx - cam_x) % 32
    dy = (cy - cam_y) % 32
    if dx >= MAINTAINED_TILES or dy >= MAINTAINED_TILES:
        return None
    return pos_x + dx // 2, pos_y + dy // 2, (dx & 1) + 2 * (dy & 1)


def expected_layer_words(layer_type: int, words: list[int], quadrant: int,
                         streamed: bool) -> dict[int, int] | None:
    """The word DrawMetatile puts on each BG for one quadrant of a metatile.

    `words` are the metatile's 8 entries (u32 wide words for a streamed map, u16
    otherwise). Returns {bg: word}, or None for a layer type DrawMetatile skips."""
    lo, hi = words[quadrant], words[4 + quadrant]
    if layer_type == LAYER_SPLIT:
        return {3: lo, 2: 0, 1: hi}
    if layer_type == LAYER_COVERED:
        return {3: lo, 2: hi, 1: 0}
    if layer_type == LAYER_NORMAL:
        return {3: 0 if streamed else STOCK_NORMAL_BG3_WORD, 2: lo, 1: hi}
    return None


def word_tile(word: int, streamed: bool) -> int:
    """The tile a metatile word names: pool id for a wide word, index otherwise."""
    return word >> 16 if streamed else word & 0x3FF


@dataclass
class Mismatch:
    map_id: int
    pos: tuple[int, int]
    bg: int
    cell: tuple[int, int]
    metatile_pos: tuple[int, int]
    metatile: int
    kind: str          # "attrs" | "slot" | "pixels"
    expected: int      # expected word (wide word for streamed) or tile id
    actual: int        # VRAM tilemap word


@dataclass
class CheckResult:
    map_id: int
    steps: int = 0
    checks: int = 0
    mismatches: int = 0
    first: list[Mismatch] = field(default_factory=list)
    cache_errors: int = 0
    cache_overflows: int = 0
    refcount_drift: int = 0
    max_resident: int = 0
    uploads: int = 0
    streamed: bool = False
    size: tuple[int, int] = (0, 0)
    left_map: int = 0  # steps that hit a warp and were walked around
    seconds: float = 0.0


# -- the emulator side ---------------------------------------------------------

class ScreenChecker:
    """Drives a Map Walker ROM and checks the BG after each step."""

    def __init__(self, rom: Path, engine: Path) -> None:
        import mgba.core
        import mgba.image
        import mgba.log

        from .offsets import probe_constants, probe_offsets
        from .symbols import SymbolMap

        mgba.log.silence()
        self.engine = engine
        self.sym = SymbolMap(engine / "pokeemerald.map")
        self.off = probe_offsets(engine)
        for needed in ("gUraniumWalkerHarnessWarp", "gFieldStream"):
            if needed not in self.sym:
                raise click.ClickException(
                    f"{needed} is not in {engine / 'pokeemerald.map'}: the screen check "
                    "needs a Map Walker build (URANIUM_MAP_WALKER TRUE) with the streaming cache"
                )
        self._map_consts = _walker_map_constants(engine)
        values = probe_constants(engine, sorted(self._map_consts.values()))
        self._map_value = {mid: values[name] for mid, name in self._map_consts.items()}
        self.core = mgba.core.load_path(str(rom))
        if self.core is None:
            raise click.ClickException(f"could not load ROM {rom}")
        self._screen = mgba.image.Image(*self.core.desired_video_dimensions())
        self.core.set_video_buffer(self._screen)
        self.core.autoload_save()
        self.core.reset()
        self._rom_cache: dict[tuple[int, int], bytes] = {}

    # raw access
    def run(self, frames: int, keys: tuple[str, ...] = ()) -> None:
        mask = 0
        for k in keys:
            mask |= 1 << KEYS[k]
        self.core._core.setKeys(self.core._core, mask)
        for _ in range(frames):
            self.core.run_frame()
        self.core._core.setKeys(self.core._core, 0)

    def u8(self, a: int) -> int:
        return self.core.memory.u8[a]

    def u16(self, a: int) -> int:
        return self.core.memory.u16[a]

    def u32(self, a: int) -> int:
        return self.core.memory.u32[a]

    def read(self, a: int, n: int) -> bytes:
        return bytes(self.core.memory.u8[a:a + n])

    def rom(self, a: int, n: int) -> bytes:
        """ROM bytes, cached (ROM never changes)."""
        key = (a, n)
        got = self._rom_cache.get(key)
        if got is None:
            got = self._rom_cache[key] = self.read(a, n)
        return got

    # game state
    def pos(self) -> tuple[int, int]:
        sb1 = self.u32(self.sym["gSaveBlock1Ptr"])
        base = sb1 + self.off["off_sb1_pos"]
        return _s16(self.u16(base)), _s16(self.u16(base + 2))

    def location(self) -> tuple[int, int]:
        sb1 = self.u32(self.sym["gSaveBlock1Ptr"])
        base = sb1 + self.off["off_sb1_location"]
        return self.u8(base), self.u8(base + 1)

    def layout(self) -> int:
        return self.u32(self.sym["gMapHeader"] + self.off["off_mapheader_maplayout"])

    def map_size(self) -> tuple[int, int]:
        lay = self.layout()
        return (self.u32(lay + self.off["off_maplayout_width"]),
                self.u32(lay + self.off["off_maplayout_height"]))

    def boot(self, frames: int = 900) -> None:
        self.run(frames)

    def warp(self, map_id: int, x: int, y: int) -> None:
        """Warp through the walker's harness hook and wait for the map to settle."""
        value = self._map_value[map_id]
        group, num = value >> 8, value & 0xFF
        base = self.sym["gUraniumWalkerHarnessWarp"]
        self.core.memory.u8.raw_write(base + 1, group)
        self.core.memory.u8.raw_write(base + 2, num)
        self.core.memory.u8.raw_write(base + 3, x & 0xFF)
        self.core.memory.u8.raw_write(base + 4, y & 0xFF)
        self.core.memory.u8.raw_write(base + 0, 1)
        for _ in range(60):
            self.run(10)
            if self.location() == (group, num) and self.u8(base) == 0:
                break
        else:
            raise click.ClickException(f"harness warp to map {map_id} did not land")
        self.run(120)

    def step(self, direction: str) -> bool:
        """One step; returns whether the position changed (a first press may turn)."""
        before = self.pos()
        for _ in range(3):
            self.run(10, (direction,))
            self.run(14)
            if self.pos() != before:
                self.run(8)
                return True
        return False

    # the check
    def check(self, map_id: int, result: CheckResult, max_report: int = 20) -> None:
        o = self.off
        result.checks += 1
        lay = self.layout()
        prim = self.u32(lay + o["off_maplayout_primarytileset"])
        sec = self.u32(lay + o["off_maplayout_secondarytileset"])
        border = self.u32(lay + o["off_maplayout_border"])
        wide = self.u32(prim + o["off_tileset_streammetatiles"])
        streamed = wide != 0
        result.streamed = streamed
        tiles_ptr = self.u32(prim + o["off_tileset_tiles"])
        n_pinned = self.u16(prim + o["off_tileset_numpinnedtiles"]) if streamed else 0

        bk = self.sym["gBackupMapLayout"]
        bw = _s32(self.u32(bk + o["off_backup_width"]))
        bh = _s32(self.u32(bk + o["off_backup_height"]))
        grid_ptr = self.u32(bk + o["off_backup_map"])
        if bw * bh > MAX_MAP_DATA_SIZE:
            raise click.ClickException(
                f"map {map_id}: backup grid {bw}x{bh} exceeds MAX_MAP_DATA_SIZE; the engine "
                "loaded only its border, so there is nothing to check"
            )
        grid = struct.unpack(f"<{bw * bh}H", self.read(grid_ptr, bw * bh * 2))
        border_blocks = struct.unpack("<4H", self.rom(border, 8))

        fs = self.sym["gFieldStream"]
        cam_x = self.u8(fs + o["off_fs_camtilex"])
        cam_y = self.u8(fs + o["off_fs_camtiley"])
        pos_x, pos_y = self.pos()

        vram_maps = {bg: struct.unpack("<1024H", self.read(SCREENBLOCK[bg], 2048))
                     for bg in (1, 2, 3)}
        charblock = self.read(CHARBLOCK0, 1024 * TILE_BYTES) if streamed else b""

        def metatile_at(x: int, y: int) -> int:
            if 0 <= x < bw and 0 <= y < bh:
                block = grid[x + bw * y]
            else:
                block = border_blocks[((x + 1) & 1) + ((y + 1) & 1) * 2]
            if block == MAPGRID_UNDEFINED:
                block = border_blocks[((x + 1) & 1) + ((y + 1) & 1) * 2]
            mid = block & METATILE_ID_MASK
            return 0 if mid > NUM_METATILES_TOTAL else mid

        def layer_type(mid: int) -> int:
            if mid < NUM_PRIMARY_METATILES:
                attrs = self.u32(prim + o["off_tileset_metatileattributes"])
                raw = struct.unpack("<H", self.rom(attrs + mid * 2, 2))[0]
            else:
                attrs = self.u32(sec + o["off_tileset_metatileattributes"])
                raw = struct.unpack("<H", self.rom(attrs + (mid - NUM_PRIMARY_METATILES) * 2, 2))[0]
            return (raw >> 12) & 0xF

        def words_of(mid: int) -> list[int]:
            if streamed:
                return list(struct.unpack("<8I", self.rom(wide + mid * 32, 32)))
            if mid < NUM_PRIMARY_METATILES:
                base = self.u32(prim + o["off_tileset_metatiles"])
                return list(struct.unpack("<8H", self.rom(base + mid * 16, 16)))
            base = self.u32(sec + o["off_tileset_metatiles"])
            return list(struct.unpack("<8H", self.rom(base + (mid - NUM_PRIMARY_METATILES) * 16, 16)))

        resident: set[int] = set()
        for cy in range(32):
            for cx in range(32):
                where = cell_metatile(cx, cy, cam_x, cam_y, pos_x, pos_y)
                if where is None:
                    continue
                mx, my, q = where
                mid = metatile_at(mx, my)
                exp = expected_layer_words(layer_type(mid), words_of(mid), q, streamed)
                if exp is None:
                    continue
                for bg, want in exp.items():
                    got = vram_maps[bg][cx + 32 * cy]
                    kind = _compare(want, got, streamed, n_pinned, tiles_ptr, charblock, self.rom)
                    if streamed and (got & 0x3FF) >= n_pinned:
                        resident.add(got & 0x3FF)
                    if kind is None:
                        continue
                    result.mismatches += 1
                    if len(result.first) < max_report:
                        result.first.append(Mismatch(
                            map_id, (pos_x, pos_y), bg, (cx, cy), (mx, my), mid, kind, want, got))

        if streamed:
            result.max_resident = max(result.max_resident, len(resident))
            result.cache_errors = self.u32(fs + o["off_fs_errors"])
            result.cache_overflows = self.u32(fs + o["off_fs_overflows"])
            result.uploads = self.u32(fs + o["off_fs_uploads"])
            result.refcount_drift += self._refcount_drift(n_pinned)

    def _refcount_drift(self, n_pinned: int) -> int:
        """Slots whose refcount differs from the cells in the EWRAM tilemap buffers."""
        o = self.off
        counts: Counter[int] = Counter()
        for name in ("gOverworldTilemapBuffer_Bg1", "gOverworldTilemapBuffer_Bg2",
                     "gOverworldTilemapBuffer_Bg3"):
            buf = self.u32(self.sym[name])
            for w in struct.unpack("<1024H", self.read(buf, 2048)):
                counts[w & 0x3FF] += 1
        door = o["val_fs_first_door_slot"]
        refs = struct.unpack("<1024H", self.read(self.sym["gFieldStream"] + o["off_fs_slotrefs"], 2048))
        return sum(1 for s in range(n_pinned, door) if refs[s] != counts.get(s, 0))


def _compare(want: int, got: int, streamed: bool, n_pinned: int, tiles_ptr: int,
             charblock: bytes, rom) -> str | None:
    if (want & 0xFC00) != (got & 0xFC00):
        return "attrs"
    tile = word_tile(want, streamed)
    slot = got & 0x3FF
    if not streamed or tile < n_pinned:
        return None if slot == tile else "slot"
    if slot < n_pinned:
        return "slot"
    vram = charblock[slot * TILE_BYTES:(slot + 1) * TILE_BYTES]
    return None if vram == rom(tiles_ptr + tile * TILE_BYTES, TILE_BYTES) else "pixels"


def _s16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def _s32(v: int) -> int:
    return v - 0x100000000 if v & 0x80000000 else v


_WALKER_ENTRY = re.compile(r'X\((MAP_\w+), COMPOUND_STRING\("(\d+) ')


def _walker_map_constants(engine: Path) -> dict[int, str]:
    """Uranium map id -> MAP_* constant, from the walker's generated map list."""
    text = (engine / "include" / "uranium_walker_maps.h").read_text(encoding="utf-8")
    return {int(mid): const for const, mid in _WALKER_ENTRY.findall(text)}


def serpentine(width: int, height: int, stride: int) -> list[tuple[int, int]]:
    """Waypoints for a boustrophedon over the map: full rows `stride` apart."""
    points: list[tuple[int, int]] = []
    rows = list(range(0, height, stride))
    if rows[-1] != height - 1:
        rows.append(height - 1)
    for i, y in enumerate(rows):
        xs = (0, width - 1) if i % 2 == 0 else (width - 1, 0)
        points += [(xs[0], y), (xs[1], y)]
    return points


def run_map(checker: ScreenChecker, map_id: int, stride: int, churn: int,
            max_steps: int | None) -> CheckResult:
    result = CheckResult(map_id)
    started = time.monotonic()
    checker.warp(map_id, 0, 0)
    width, height = checker.map_size()
    result.size = (width, height)
    checker.check(map_id, result)

    home = checker.location()

    def walk_to(tx: int, ty: int) -> None:
        # A straight-line walk never needs more than this; a bounce or loop does.
        budget = abs(width) + abs(height) + 4
        while budget > 0:
            budget -= 1
            if max_steps is not None and result.steps >= max_steps:
                return
            # The camera's top-left (pos) sits MAP_OFFSET up-left of the player in
            # backup-grid coordinates, so pos is the player's map-local tile.
            x, y = checker.pos()
            if (x, y) == (tx, ty):
                return
            direction = ("RIGHT" if tx > x else "LEFT") if x != tx else ("DOWN" if ty > y else "UP")
            if not checker.step(direction):
                logger.warning("map %d: blocked at %s heading %s", map_id, (x, y), direction)
                return
            if checker.location() != home:
                # Stepped onto a warp: come back past it and give up on this leg.
                logger.warning("map %d: a step %s from %s left the map; warping back",
                               map_id, direction, (x, y))
                result.left_map += 1
                dx, dy = DIRS[direction]
                checker.warp(map_id, min(max(x + 2 * dx, 0), width - 1),
                             min(max(y + 2 * dy, 0), height - 1))
                return
            result.steps += 1
            checker.check(map_id, result)
        logger.warning("map %d: gave up walking to %s", map_id, (tx, ty))

    for i, (tx, ty) in enumerate(serpentine(width, height, stride)):
        if i % 2 == 0:
            logger.info("map %d: row %d/%d, %d steps, %d mismatches", map_id, ty, height,
                        result.steps, result.mismatches)
        walk_to(tx, ty)
    # Refcount churn: back and forth across one boundary.
    cx, cy = width // 2, height // 2
    walk_to(cx, cy)
    for _ in range(churn):
        walk_to(min(cx + 1, width - 1), cy)
        walk_to(cx, cy)
        walk_to(cx, min(cy + 1, height - 1))
        walk_to(cx, cy)
    result.seconds = time.monotonic() - started
    return result


@click.command()
@click.option("--rom", type=click.Path(path_type=Path, exists=True), default=Path("engine/pokeemerald.gba"))
@click.option("--engine", type=click.Path(path_type=Path, exists=True), default=Path("engine"))
@click.option("--map", "map_ids", type=int, multiple=True, required=True, help="Uranium map id (repeatable)")
@click.option("--stride", type=int, default=2, show_default=True, help="rows between serpentine passes")
@click.option("--churn", type=int, default=8, show_default=True, help="back-and-forth crossings at the centre")
@click.option("--max-steps", type=int, default=None, help="cap steps per map (smoke runs)")
@click.option("--out", type=click.Path(path_type=Path), default=Path("output/screen_check.json"))
def main(rom: Path, engine: Path, map_ids: tuple[int, ...], stride: int, churn: int,
         max_steps: int | None, out: Path) -> None:
    """Walk each map on a Map Walker ROM and check every BG cell after every step."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    checker = ScreenChecker(rom, engine)
    checker.boot()
    results = []
    failed = False
    for map_id in map_ids:
        res = run_map(checker, map_id, stride, churn, max_steps)
        results.append(res)
        bad = res.mismatches or res.cache_errors or res.cache_overflows or res.refcount_drift
        failed |= bool(bad)
        click.echo(
            f"map {map_id:3d} {'streamed' if res.streamed else 'stock   '} steps={res.steps} "
            f"checks={res.checks} mismatches={res.mismatches} errors={res.cache_errors} "
            f"overflows={res.cache_overflows} drift={res.refcount_drift} "
            f"max_resident={res.max_resident} uploads={res.uploads} size={res.size} "
            f"{res.seconds:.0f}s -> {'FAIL' if bad else 'ok'}"
        )
        for m in res.first[:5]:
            click.echo(f"    {m}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([asdict(r) for r in results], indent=2) + "\n", encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
