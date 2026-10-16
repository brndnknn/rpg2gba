# Streaming tile engine: prototype plan

**Status:** draft for operator review, 2026-10-16 (A1→A2 intermission, item I4).
Branch `intermission-streaming`. Background and measurements:
`reference/intermission_a1_a2.md` §I4, including "Feasibility research".

## 1. Goal

Let one map use more than 1024 unique 8×8 tiles and more than 1024 metatiles.
The aim is to stop splitting maps (map 040 is split into seven pieces joined by
arrow warps) and to stop trading art quality for fit (the lossy tile merge).

**Non-goals for the prototype:**
- **Palettes.** The tile prototype keeps 13 palettes per map. Palette
  streaming is a separate, later stage (§3.6, stage P), because it only pays
  off with a new kind of quantizer.
- **Corpus-wide rollout.** Only opted-in maps take the new path. Everything
  else keeps today's load-once path.
- **The map viewer and oracle.** Their rework belongs to rollout (§6).

## 2. Why it fits: the numbers

These come from the real build with merge off, which is full-quality art,
and every window position (`output/scratch/window_census.py`). The engine fills
a 32×32-tile ring buffer, which is 16×16 metatiles and larger than the
screen, so that window is the one that has to be resident.

| Map | Unique tiles, whole map | Metatiles | Worst 16×16 window (resident set) |
|---|---|---|---|
| 040 (unsplit) | 1748 | 1277 | 662 |
| 094 | 2012 | 1815 | 498 |
| 101 | 2039 | 1556 | **671** |
| 122 | 1770 | 1008 | 611 |
| 187 | 1674 | 1412 | 579 |

Budget: 1024 slots, minus tile 0 (transparent), the 16 door slots
(1008–1023, `field_door.c:433`), and the pinned animation tiles. The
largest animated set today is uranium1033's 136 tiles. That leaves at least
about 870 slots for streaming, against a worst case of 671.

## 3. Design

### 3.1 Metatile ids: 10 → 12 bits (published recipe)

Follow the pret wiki's "Expanding The Metatile Count". The map grid cell
stays `u16`: 12-bit metatile id, 1 collision bit, 3 elevation bits. That
gives 4096 metatiles per map, enough for 094's 1815.
- **Data fit:** the converter writes only elevation 0 or 3 and two collision
  values (`tile_map.py:56-57`), so nothing is lost.
- **Engine:** the `MAPGRID_*` masks (`global.fieldmap.h:7-12`), the
  `NUM_METATILES_*` constants (`fieldmap.h`), and the primary/secondary split.
- **Pipeline:** `tile_map.py`'s packing, layout emit, the map-constant and
  porymap writers, and every Python reader of `map.bin` (the harness's
  collision reader `_collision_walkable`, the viewer and the oracle).
- **Save:** the save's `mapView` (`fieldmap.c:568-698`) holds raw grid cells.
  The size is unchanged, but saves made before this change decode wrongly
  near the player until the next map load. Accepted: walk ROMs re-seed on
  every boot.

This stage is useful on its own, because it removes the metatile cap for
every map.

### 3.2 Tile words wider than 10 bits

A metatile's eight tile words are `u16`: 10-bit tile index, flip bits, and
4-bit palette. A streamed tileset's tiles are numbered past 1023, so its
metatiles store **`u32` words**: a 16-bit tile id plus the flip and palette
bits. That costs about 30 KB more ROM for 094 (1815 × 8 × 2 extra bytes).
Only opted-in tilesets use the wide format. A per-tileset flag (or a
separate struct field) selects it.

### 3.3 The tile cache (VRAM slot allocator)

The tile cache lives in EWRAM. For a map with N tiles (N ≤ about 2100 today)
it costs about 6 KB:
- `tileToSlot[N]` (`u16`, 0 = not resident);
- `slotTile[1024]` and `slotRefs[1024]` (`u16` each);
- a free list.

**Drawing.** The single choke point is `field_camera.c` `DrawMetatile`. Every
runtime metatile change already goes through it: Cut, Rock Smash, doors,
scripts, braille and the escalator. For each of the 8 tile words it does:
1. Read the tilemap word currently at that buffer cell. That word's slot is
   the *old* tile, so decrement its refcount. When a refcount hits 0, the
   slot goes on the free list, but its contents and mapping are kept until
   the slot is reused. That makes walking back and forth cheap.
2. Look up the new tile. If it isn't resident, take a free slot and queue a
   32-byte upload.
3. Write the tilemap word using the **slot** index, keeping the flip and
   palette bits.

The tilemap buffers already store slot numbers, so no shadow copy is needed.

**Uploads.** Queued tile uploads are flushed in VBlank **before** the tilemap
copy, in the same VBlank, so a cell never shows a slot that isn't filled
yet. The worst case per step is one incoming 16-metatile row or column on
two layers: at most 128 new tiles, 4 KB. The flush uses DMA3 and stays
well inside VBlank. If one ever doesn't fit, the step's tilemap copy waits a
frame instead of tearing.

**Full redraws.** `DrawWholeMapView` happens on map load, return from
battle or menus, and after some scripts. For these, the cache resets and
then everything redraws. The reset hook also runs from
`ResetScreenForMapLoad` (`overworld.c:2568`) and `fldeff_flash.c:138`,
which wipe VRAM.

**Pinned slots.** These are never handed out by the allocator:
- **Animated tiles** keep today's fixed slots. The generated anim code
  (`uranium_anims.gen.h`) is unchanged, and the packer places animated
  tiles first, as it does now.
- **Door tiles** keep 1008–1023.
- **Tile 0** stays transparent.

**Overflow.** The build guarantees no overflow (§3.4). The engine still
checks it: in a debug build, an exhausted pool fails loud (a halt with an
on-screen marker) instead of drawing garbage.

### 3.4 Build-time guarantee (fail loud in the pipeline)

The pipeline computes, for every streamed map, the worst 16×16-window
resident set plus the pinned slots. It fails the build if the total exceeds
1024, the same way the caps fail loud today. So the "too many tiles on
screen" bug class can't reach a ROM. This is `window_census.py` promoted
into `build_slice_tilesets`. The census needs to count connected neighbours,
because a window at a map edge also shows the neighbour's strip.

### 3.5 Connections and seams

*(Corrected 2026-10-16 after operator review: the first draft proposed
joining 040 and 035 into one shared tileset group. That would force
Kevlar, Route 2 and Nowtoch into one set of 13 palettes, and the group
grows transitively as chapters add connections.)*

The stock engine draws a connected neighbour's cells through the
**current** map's tileset. The pipeline has two ways to handle that:
1. **Shared group** (`map_set.tileset_groups`): maps on the *same* RMXP
   tileset, joined by a connection, share one synthetic tileset and so one
   set of 13 palettes. Kevlar (31) and Route 2 (035), both RMXP tileset 22,
   are such a group today.
2. **Remapped seam** (`connection_remap`): each side imports the other's
   border strip into its *own* tileset, re-quantized into its *own*
   palettes. No palettes are shared. Map 040 is RMXP tileset 23, so
   035↔040 is already a remapped seam and never joins the 31+35 group.

Today the imported strips eat into the 1024 caps, and the caps are why
seams are hard (#27). With streaming, an imported strip costs metatile ids
(4096 available) but no permanent VRAM. So remapped seams always fit, and
the pipeline can **prefer remapped seams over shared groups**. That keeps
every map on its own 13 palettes, with no transitive growth. The visible
cost is a slight colour shift on the neighbour's strip, which already
exists on today's remapped seams.

This is also the answer for #27 (Moki E → Route 03).

### 3.6 Palettes: what streaming them would and wouldn't buy

Streaming palettes is mechanically possible, and the engine already does it
for overworld *sprites*: tag-based palette allocation, with
`UpdateSpritePaletteWithWeather` (`field_weather.c:849`) re-applying weather
when a palette loads. For BG tiles it works like slots: each tilemap word
carries a 4-bit palette number, so `DrawMetatile` can map a tileset's
"virtual" palette to one of the 13 hardware palettes, refcounted.

**But measured on the built ROM** (`output/scratch/window_palettes.py`), the
quantizer already fills all 13 palettes on almost every map. The worst
16×16 window on most maps uses all 13 too. The packer spreads colour
families across every palette, so each screen needs nearly all of them.
Streaming palettes alone gains nothing.

It only pays off together with a **location-aware quantizer**: more than 13
palettes per map, chosen so that any one screen needs at most 13. That
would mean:
- better colours on big maps;
- unsplit Nowtoch keeping roughly the colour budget its seven pieces get
  today (7 × 13 palettes);
- relief for I2b-type palette cramming.

Constraining palettes per window is a genuinely open problem. It is the
riskiest piece here and is kept **out of the tile prototype**. It gets its
own Python-only experiment first (§5, stage P), so no engine work is spent
until the art is judged by eye.

### 3.7 What unsplitting 040 costs in colour

Today map 040's seven pieces each have their own 13 palettes. Unsplit 040
with tile streaming but **not** palette streaming gets one set of 13 for
the whole city. That may look worse than today. Stage 0 renders unsplit
040 through the real ROM quantizer and compares it with the current pieces
by eye, before any engine work. If it looks worse, the choices are:
- unsplit 040 waits for stage P;
- accept the colours for the sake of removing the arrow warps (operator's
  call).

### 3.8 Opt-in

A layout-level flag marks a map as streamed:
- **Streamed maps:** the wide tile words (§3.2) and the cache path.
- **All other maps:** keep the stock load-once path, untouched.

Both paths live side by side. The prototype changes nothing for maps that
don't opt in, so the CH01–CH08 suites still guard the old path.

## 4. How we test maps the chapters haven't reached

Map 101 isn't reachable in any built chapter, so the plan doesn't depend on
story progress to test it.

1. **Prototype on map 040, not 101.**
   - Nowtoch City is built (CH06–CH08), already walked, covered by the
     generated suites, and it's the map whose split you want gone.
   - Unsplitting it under streaming is a real gameplay test: doors, the
     gym, cutscenes, battles and returning from them, the mart's buy menu,
     and the Route 2 connection.
   - Its worst window (662) is nearly as dense as 101's (671).

2. **Map Walker ROM for the unreached maps.** This already exists:
   - `URANIUM_MAP_WALKER` in `engine/include/config/uranium_walker.h`
     (README "Map Walker") builds a ROM with free movement, no NPCs or
     scripts, and a START-menu warp to any map.
   - Today it leaves out the over-cap maps (`WALKER_OVERFLOW_MAP_IDS`,
     `map_set.py:77`). Streaming puts 094, 101, 122 and 187 back in.
   - You can warp into any of them on your desktop or flash cart and walk
     around by eye, with no chapter progress needed.

3. **An automatic screen check in the emulator, the main correctness test.**
   - Drive the Map Walker ROM along a serpentine path that covers every
     camera position of a map, so every row and column streams in and out.
   - After each step, decode what the hardware is actually showing from
     VRAM: the BG1–BG3 tilemaps, the charblock and the palettes.
   - Compare it pixel for pixel with the expected render of those
     metatiles from the build's own tileset art. The expected render is
     the oracle's quantized output (`scripts/verify_viewer_rom_match.py`
     Mode A already decodes the emitted artifacts).
   - Any mismatch is a stale slot, a missed upload or a refcount bug, and
     the check reports the exact map, camera position and cell.
   - Run it on 040, 094, 101, 122 and 187, plus walking back and forth
     across one boundary repeatedly (refcount churn).

4. **The CH01–CH08 generated suite from boot,** with map 040 unsplit. Its
   map ids change (pieces 14000–14006 retire), so CH06–CH08 are regenerated
   with `beat_gen`, and their review docs come to you (§9 gate) as usual.

5. **Your walks.**
   - The Map Walker ROM, early. Include **one run on the flash cart**,
     because VBlank timing is the hardware risk.
   - Then a CH08 walk ROM with Nowtoch in one piece.

## 5. Stages, exit criteria, stop rule

| Stage | Work | Exit criterion |
|---|---|---|
| **0. Prep** | Per-map slot budget (anim + doors + worst window, including neighbour strips); **render unsplit 040 with one 13-palette set and compare by eye with today's pieces (§3.7)**; promote the window census into a build-time check (report-only for now); fix the missing `Floatstone.png` for map 071 if it's cheap | Budget table for all 204 maps; your by-eye verdict on unsplit-040 colours |
| **1. 12-bit metatile ids** | §3.1, engine + pipeline + harness readers | Full pytest green; CH08 suite green from boot; no visual change |
| **2. Streaming core** | §3.2–3.4, behind the per-map flag; the screen check (§4.3); Map Walker build including the over-cap maps | Zero screen-check mismatches on 040, 094, 101, 122, 187; your Map Walker walk, including the flash cart |
| **3. Map 040 unsplit** | Retire `split_maps.json`'s map-40 entry, keep 035↔040 as a remapped seam (§3.5), regenerate CH06–CH08 suites (§9 review), merge off for streamed maps | CH08 suite green from boot; your CH08 walk passes |
| **4. Rollout (later)** | Other maps opt in as their chapters arrive; viewer/oracle learn the streamed format; I2b's palette tuning on merge-off art; #27 as a remapped seam |
| **P. Palettes (separate, optional)** | Python-only first: a location-aware quantizer (more than 13 palettes per map, at most 13 per 16×16 window), rendered and judged by eye on 040 and a seam. Only if the art wins: the engine's palette cache (§3.6) | Your by-eye verdict before any engine work | Per chapter, as usual |

**Stop rule.** Stop and keep Stage 1 plus splitting if either happens:
- Stage 2 can't reach zero screen-check mismatches on 040 and 101 within
  three working sessions.
- Your flash-cart run shows tearing or garbage that ordering uploads before
  the tilemap copy doesn't fix.

Stage 1 is kept either way.

### Stage 0 results (2026-10-16)

**Budget census, the whole corpus**
(`output/scratch/budget_census.py`, results in `budget_census.jsonl`, summary
via `budget_summary.py`). Merge off, every map in the build, map 040 unsplit.
- **Every buildable map fits** (193 of 199). Slack = 1024 − tile 0 − 16 door
  slots − animated tiles − worst 16×16 window.
- **The tightest is map 101,** with 176 slots spare. It has 184 animated
  tiles, which is a pinned cost.
- The next tightest are 151 (272), 122 (304), 040 (323), 146 (333), 187 (340)
  and 094 (399).
- No map comes near zero.
- **Without streaming,** 21 maps go over 1024 tiles with merge off and 8 go
  over 1024 metatiles. Those are what full-quality art would cost under
  today's engine.
- **Errors:** the 5 known empty maps (14, 30, 38, 55, 56), and map 071.
- **Caveat:** each map's own grid only. A window at a connected edge also
  shows the neighbour's strip, which isn't counted. The build-time check
  (stage 2) counts it, because it runs on the final layout with imported
  strips.

**Map 071 (`Floatstone.png`)**
- The missing autotile is tileset 54's slot 0, and it is **map 071's base
  floor**: 4566 of 6724 layer-0 cells.
- It is absent everywhere under the Uranium source tree, and nothing near
  it is named similarly.
- A transparent fallback would produce a void map, so it isn't a fix.
- The fix is to **re-extract the asset from the game's original archive or
  install** into `Graphics/Autotiles/`. No code change is needed. The
  `CORPUS_UNRENDERABLE` entry (`tile_merge.py:59-61`) then goes.
- This is an operator action. A placeholder floor is the fallback if the
  file can't be found.

**Unsplit 040 on one 13-palette set, compared with today's pieces**
(`output/scratch/render_unsplit40.py`; images in `output/scratch/s0_40/`,
`piece_<uid>.png` = source | today's piece from the built ROM | unsplit 13
palettes).
- Mean colour error against the source is slightly higher for every piece:

  | | Today's pieces | Unsplit, 13 palettes |
  |---|---|---|
  | Mean error (range over pieces) | 9.3–16.4 | 13.4–18.4 |
  | Share of pixels with error above 60 | 1.0–2.0% | 1.4–2.5% |

- **By eye** (pieces 14000 and 14003 checked): both are close to the
  source. The visible difference is pavement contrast. The unsplit version
  shows the paving checker pattern more strongly, and today's pieces are
  slightly darker and flatter. Trees, buildings and roads are near
  identical.
- **Operator verdict pending.**

**Build-time window check:** moved to stage 2. Its correct input is the
final layout, with imported neighbour strips, which only exists at layout
conversion. The scratch census answers stage 0's question with the same
numbers.

## 6. Risks

| Risk | Mitigation |
|---|---|
| A code path writes map tiles to fixed slots that the audit missed | The audit found the hazard surface (intermission doc §I4). The screen check catches anything drawn wrong, and the CH08 suite covers gameplay paths. |
| VBlank timing on hardware | Uploads go before the tilemap in the same VBlank. Flash-cart check at Stage 2 exit, not at the end. |
| Refcount drift (a slot freed while still on screen) | The screen check plus back-and-forth churn runs. A debug-build consistency check can recount refs from the tilemaps on demand. |
| Unsplit 040 looks worse on one 13-palette set | By-eye comparison in Stage 0, before any engine work (§3.7). |
| Our tools assume fixed tile numbering | Streamed maps are opt-in; viewer/oracle work is in Stage 4. Until then, the screen check is the oracle for streamed maps. |
| Engine baseline change | Approval needed (CLAUDE.md §10). The changes are fenced under a new sentinel, `RPG2GBA STREAMING`, so they can be found against upstream. |

## 7. Decisions needed from the operator

1. Approve the engine baseline changes: 12-bit metatile ids for all maps,
   and the opt-in streaming path.
2. Merge off for streamed maps, the full-quality art (recommended), or keep
   the merge on.
3. Confirm map 040 as the prototype map and the Map Walker as the test bed
   for the unreached maps.
4. CH09 timing: open CH09 now and build the #27 seam the existing way, or
   wait for Stage 3 and build it as a shared group.
