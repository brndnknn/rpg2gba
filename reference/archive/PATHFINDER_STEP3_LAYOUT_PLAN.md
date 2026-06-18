# Pathfinder Step 3 — Map Layout Converter (`layout.py`)

> Detailed implementation plan for **S3** of `PATHFINDER_SLICE_ROADMAP.md`.
> Implements `PHASE5_PLAN.md §5.2` for the three slice maps (49 bedroom, 48 house,
> 32 Moki Town). Consumes S2's `TileMap` (`tile_map.lookup` / `tileset_for`).
> Q1 (layer collapse) and Q5 (border) are resolved in PHASE5_PLAN; this plan is
> the algorithm + serialization detail. The stub
> `src/rpg2gba/tileset_converter/layout.py` already defines `TileGrid`, `Layout`,
> the function signatures, and `write_blockdata`/`read_blockdata`.

---

## What "done" means for the slice

For each of maps 49/48/32, produce under `output/uranium-build/porymap/`:

```
layouts/<Name>/map.bin      # width*height little-endian u16 blocks
layouts/<Name>/border.bin   # 2x2 u16 = 8 bytes (Q5)
layouts/layouts.json        # one appended entry per map (fork schema)
```

byte-identical on re-run (idempotent), failing loud if S2 can't resolve any tile.
The real proof is S8: these layouts produce a **walkable** bedroom/house/town in
mGBA.

---

## Target formats (verified against the fork)

### `map.bin` block (the resolved stub already encodes this)

Each cell is one little-endian `u16`:

```
block = (metatile_id & 0x03FF) | (collision << 10) | (elevation << 12)
```

`Metatile.to_block()` (in `tile_map.py`) already does this. `len(map.bin) ==
width * height * 2`. Worked example: Map049 is 30×15 → 450 blocks → **900 bytes**.

### `border.bin` (Q5)

Standard Emerald border is **2×2 metatiles** = 4 blocks = 8 bytes. Q5 decision:
fill with **one neutral impassable "void" metatile** (`collision=1`). Same void
metatile authored in S2's `tileset_map.json` per tileset (interior void / town
void). So `border = [void_block, void_block, void_block, void_block]`.

### `layouts.json` entry (exact schema from `data/layouts/layouts.json`)

```json
{
  "id": "LAYOUT_MOKI_TOWN_PLAYERS_HOUSE_2F",
  "name": "MokiTown_PlayersHouse_2F_Layout",
  "width": 30,
  "height": 15,
  "primary_tileset": "gTileset_General",
  "secondary_tileset": "gTileset_BrendansMaysHouse",
  "border_filepath": "data/layouts/MokiTown_PlayersHouse_2F/border.bin",
  "blockdata_filepath": "data/layouts/MokiTown_PlayersHouse_2F/map.bin",
  "layout_version": "emerald"
}
```

The top-level file is `{ "layouts_table_label": "gMapLayouts", "layouts": [ ... ] }`.

**Path convention:** `border_filepath` / `blockdata_filepath` are written as
**fork-relative** (`data/layouts/<Name>/...`) — that is where S8/Phase-7 copies the
bins. During Phase 5 the bytes physically live under
`output/uranium-build/porymap/layouts/<Name>/`; the entry records the destination,
not the staging path (PHASE5_PLAN: "output never into the fork; Phase 7 copies").

`id` / `name` / `<Name>` come from **S4 `map_constants`** (`LAYOUT_*` and the
PascalCase layout name); do not mint them here — `layout.py` receives `name` and
`layout_const` as parameters (the stub already has them).

---

## The collapse algorithm (`collapse_column`) — the heart of S3

Per resolved **Q1 (hybrid)**, for each cell `(x,y)` with stacked ids
`z = [z0, z1, z2]` (bottom→top, via `grid.column(x,y)`):

```
1. composite override:
     key = f"{z0},{z1},{z2}"
     if tileset_id in tile_map.stacks and key in stacks[tileset_id]:
         return that Metatile
     (pathfinder rarely needs these — Q4's single-pair caps vocabulary — but the
      hook stays so slice #2+ can preserve specific stacks.)
2. topmost-non-empty:
     for zi in (z2, z1, z0):            # top layer first
         if zi != EMPTY_TILE (0):
             return tile_map.lookup(tileset_id, zi)
3. empty column (all three are 0):
     return the tileset's VOID metatile (collision=1).
```

### Empty-column policy (slice decision)

All-empty is legitimate at map edges (RMXP leaves the out-of-bounds margin empty).
Emit the **void** metatile rather than failing — but **count** void cells and
`logger.info` the ratio per map. A sanity guard: if `> 60%` of a map's cells are
void, that signals a wrong index order or a misread grid → `logger.warning` (not a
hard fail; the boot will make it obvious). Never emit raw metatile `0` for an empty
column — that is `gTileset_General`'s tile 0 and would silently look like floor.

> **Why topmost-non-empty is right for the slice:** z0 carries the floor/ground
> autotile; z1/z2 carry furniture, walls, signs, trees. Picking the top non-empty
> layer shows the object the player sees, and S2 gave those object metatiles
> `collision=1`. The floor under a wall is lost (Approach-A lossy step, recorded),
> which is invisible because you can't stand there anyway.

### Collision (v1 buckets) + warp-tile override

With pure buckets, **collision comes from the source `passages`, not the substituted
metatile.** Per-cell rule (RMXP-style, validated in
`scripts/pathfinder_collision_preview.py::cell_blocked`): scan layers **top→bottom**;
the first non-empty tile whose `tm.passage(ts,tid) & 0x0F != 0` → blocked; a non-empty
tile with `tm.priority(ts,tid) == 0` → passable (stop); all-empty → void (blocked).
The visual metatile still comes from `lookup(topmost-non-empty)`; collision is this
combined value (they can differ — an invisible-wall cell is correct, not a bug).

**Warp-tile override (S2 finding 2026-06-15):** warp/door tiles are drawn into walls,
so their source passage is *blocked* — but the player must step onto them for the
warp to fire. `convert_layout` therefore accepts an optional
`walkable_overrides: set[tuple[int,int]]` (the map's warp-source coords, supplied by
S5 from the S1 trace) and forces those cells to **collision 0** after the collapse.
Without this, the slice's door→town warp is unreachable (proven on Map049 (10,11)).

### Fail-loud propagation

`collapse_column` calls `tile_map.lookup`, which raises on an unmapped id (S2).
`convert_layout` does **not** catch it — an unresolved tile **aborts this map** with
the offending `(tileset_id, tile_id)` in the message. That is the signal to add the
tile to `tileset_map.json` (S2) and re-run. Do not swallow it into a default.

---

## `convert_layout(map_json, tile_map, *, name, layout_const)`

```
1. tiles = map_json["tiles"]; grid = TileGrid(tiles["xsize"], tiles["ysize"],
                                              tiles["zsize"], tiles["data"])
   assert grid.zsize == RMXP_LAYERS (3)            # fail loud if Phase-3 shape drifts
   width  = map_json["width"]  (== grid.xsize)     # assert equal
   height = map_json["height"] (== grid.ysize)     # assert equal
2. tileset_id = map_json["tileset_id"]
   choice = tile_map.tileset_for(tileset_id)       # (primary, secondary)
3. blocks = []
   for y in range(height):                         # row-major: y outer, x inner
       for x in range(width):
           blocks.append(collapse_column(grid, x, y, tile_map, tileset_id).to_block())
   assert len(blocks) == width * height
4. void = tile_map.lookup(tileset_id, <void tile sentinel>)  # or a TileMap.void(tileset_id) helper
   border = [void.to_block()] * 4
5. return Layout(name=name, layout_const=layout_const, width=width, height=height,
                 primary_tileset=choice.primary, secondary_tileset=choice.secondary,
                 blocks=blocks, border=border)
```

**Block order** is row-major `y*width + x` (pokeemerald reads blockdata left-to-
right, top-to-bottom). RMXP's source array is layer-major (`z*H*W + y*W + x`); the
`TileGrid.tile_at` helper already hides that — never index `data` directly here.

**Void sentinel:** add a small `TileMap.void(tileset_id) -> Metatile` (or reserve a
table key like `"void"` per tileset in `tileset_map.json`) so `layout.py` has a
clean way to ask S2 for the border/empty metatile rather than hardcoding an id.
Decide this interface in S2; the cleanest is a top-level `"void"` entry per tileset
in the table.

---

## Serialization

### `Layout` writer

Add a `Layout.write(staging_dir: Path) -> None` (the stub mentions "serialize with
`write()`" but doesn't define it):

```
dir = staging_dir / "layouts" / self.name
dir.mkdir(parents=True, exist_ok=True)
write_blockdata(self.blocks, dir / "map.bin")
write_blockdata(self.border, dir / "border.bin")
```

`write_blockdata` (already stubbed): `struct.pack(f"<{len(blocks)}H", *blocks)` →
`path.write_bytes(...)`. Deterministic ⇒ idempotent.

### `to_layouts_entry(layouts_dir)`

Return the dict shown above. `border_filepath`/`blockdata_filepath` are built from
the **fork-relative** base `data/layouts/<name>/...` (not `layouts_dir`, which is
the staging path — `layouts_dir` is only used if you ever want absolute staging
paths; for the entry, emit fork-relative). `layout_version = "emerald"`.

### Merging `layouts.json`

A module-level `append_layouts(entries, path)`:
- if `path` exists, load it; else seed `{"layouts_table_label": "gMapLayouts",
  "layouts": []}`;
- **idempotent upsert**: replace any existing entry with the same `id` rather than
  appending a duplicate (so re-running the slice doesn't grow the list);
- sort `layouts` by `id` before writing for stable diffs;
- `json.dump(..., indent=2)` + trailing newline, `encoding="utf-8"`.

(During the slice this writes `output/uranium-build/porymap/layouts/layouts.json`
with the 3 entries; S8 merges them into the fork's real `layouts.json`.)

---

## Idempotence checklist (CLAUDE.md §4.2)

- `map.bin` / `border.bin`: pure function of (grid, table) → byte-identical.
- `layouts.json`: upsert-by-id + sorted → re-run is a no-op diff.
- No timestamps, no run-order dependence, no dict-iteration-order leakage (sort).

---

## Tests (`tests/test_tileset_converter.py`, un-skip the 5.2 cases)

- **Golden 2×2 synthetic:** a hand-built 2×2×3 grid + a tiny `TileMap`; assert the
  exact 4 blocks (metatile|collision|elevation packed) and that `len(map.bin)==8`.
- **Collapse precedence:** a cell with `z=[floor, 0, table]` picks `table`;
  `[floor,0,0]` picks `floor`; `[0,0,0]` picks `void`. A composite-stack entry for
  `"a,b,c"` wins over topmost-non-empty.
- **Index order:** build a grid where `tile_at(x,y,z)` differs per axis and assert
  the emitted block order is row-major `y*width+x` (guards the layer-major→row-
  major transposition — the single most likely bug).
- **len invariant:** `len(map.bin) == width*height*2` for a non-square grid
  (e.g. 3×2) to catch width/height swaps.
- **Round-trip:** `read_blockdata(write_blockdata(blocks))` == `blocks`, and every
  decoded metatile id is one S2 emitted.
- **Idempotence:** convert+write twice → identical bytes; `append_layouts` twice →
  identical json.
- **Fail loud:** a grid referencing a tile absent from the table aborts with the
  ids (propagated from `lookup`).
- **Slice smoke (skippable):** convert the real Map049 with the real table; assert
  `len == 900` bytes and void-ratio is sane (< 60%).

---

## Work order

1. Implement `collapse_column` (+ the void interface agreed with S2) and its unit
   tests first — it is the logic; everything else is plumbing.
2. `convert_layout` + the index-order / len tests.
3. `Layout.write` + `to_layouts_entry` + `append_layouts` + idempotence tests.
4. Run on real Map049 → inspect `map.bin` size + void ratio; then 48 and 32.
5. Hand the 3 layouts to S4/S5 (constants + map.json) and S8 (assembly).

**Gate to S8:** all three maps convert with **zero unresolved tiles** and sane
void ratios. A boot with a broken layout wastes a full build cycle — get the bytes
right first.
