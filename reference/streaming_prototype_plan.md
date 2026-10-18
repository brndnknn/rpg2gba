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

### 3.1 Metatile ids: 10 → 11 bits (built 2026-10-16)

*(Changed from the draft's 12-bit pret recipe during stage 1.)* The 12-bit
version cuts elevation to 3 bits. Emerald's own stock layouts use elevations 9
and 15 (bridges are `ELEVATION_MULTI_LEVEL` = 15), so they would break. The
11-bit version drops only the collision field's unused high bit:
- **Format:** the map grid cell stays `u16`, with an 11-bit metatile id
  (2048 per map), a 1-bit collision at bit 11, and 4-bit elevation
  unchanged.
- **Room:** 2048 covers the largest map, 094 with 1815. A map that ever
  exceeds it fails loud at emit.
- **Data fit:** measured on every built layout, Uranium uses only collision
  0/1 and elevation 0/3; stock uses only collision 0/1.
- **Engine:** `global.fieldmap.h` (masks), `fieldmap.h`
  (`NUM_METATILES_TOTAL` 2048), fenced `RPG2GBA STREAMING`. Every engine
  reader goes through the masks or `UNPACK_*`. The `== 1` collision checks
  (`fldeff_cut.c:207`, `rotating_gate.c:884`) now behave like their BUGFIX
  branches, because collision can only be 0 or 1.
- **Stock layouts:** the vendored stock `map.bin`/`border.bin` stay in the
  upstream layout and are never edited. Assembly writes repacked copies to
  `data/layouts/RpgRepackedStock/` (gitignored) and points
  `layouts.gen.json` at them (`layout.repack_stock_layouts`,
  `tile_map.repack_legacy_block`; it fails loud on collision 2/3).
- **Pipeline:** the constants live in one place (`tile_map.py`), and
  `emit.py`/`connection_remap.py` import them. `Metatile.to_block` now fails
  loud on any field overflow. The harness's `_collision_walkable` reads the
  shared mask.
- **Save:** the save's `mapView` (`fieldmap.c:568-698`) holds raw grid cells.
  The size is unchanged, but saves made before this change decode wrongly
  near the player until the next map load. Accepted: walk ROMs re-seed on
  every boot.

This stage is useful on its own, because it removes the 1024-metatile cap for
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
(2048 available) but no permanent VRAM. So remapped seams always fit, and
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
| **1. 11-bit metatile ids** | §3.1, engine + pipeline + harness readers | Full pytest green; CH08 suite green from boot; no visual change |
| **2. Streaming core** | §3.2–3.4, behind the per-map flag; the screen check (§4.3); Map Walker build including the over-cap maps | Zero screen-check mismatches on 040, 094, 101, 122, 187; your Map Walker walk, including the flash cart |
| **3. Map 040 unsplit** | Retire `split_maps.json`'s map-40 entry, keep 035↔040 as a remapped seam (§3.5), regenerate CH06–CH08 suites (§9 review), merge off for streamed maps | CH08 suite green from boot; your CH08 walk passes |
| **4. Rollout (later)** | Other maps opt in as their chapters arrive; maps over the map-data buffer load whole (windowed backup grid, built 2026-10-18); viewer/oracle learn the streamed format; I2b's palette tuning on merge-off art; #27 as a remapped seam |
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
- **Is map 071 live? Yes** (checked 2026-10-16 after operator asked, since
  some maps are test maps or old versions;
  `output/scratch/who_warps_to.py 71`). Six direct Transfer Player commands
  lead into it:
  - map 84 EV115;
  - map 97 EV53 pages 1 and 2;
  - map 204 EV29 p2;
  - map 213 EV51 p1;
  - common event 12, a reset handler that checks for this map and sends the
    player back into it.

  The atlas places it in **CH59**, an optional late side quest, with maps
  213 and 84. The entry maps 97 and 204 are CH36/CH47 and CH49. So the fix
  is due by CH59, not now.

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

### Stage 2 progress (2026-10-17)

**Built** (fenced `RPG2GBA STREAMING`):
- `engine/src/field_stream.c` + `include/field_stream.h`: the cache.
- `struct Tileset` gains `streamMetatiles`/`numStreamTiles`/`numPinnedTiles`.
- `field_camera.c` streamed draw path; `fieldmap.c` tileset-load hooks; `shop.c` buy-menu view.
- Pipeline: `reference/streamed_maps.json` (source of truth),
  `tileset_converter/streaming.py`, `emit_tileset(stream=True)`, merge exemption,
  build-time window check at both layout write sites.
- `playtest/screen_check.py` and a harness warp in the Map Walker.

**Where the build differs from §3.3 as drafted:**
- **Uploads are synchronous CPU copies, not VBlank-queued.** That is safe
  outside VBlank because a slot is only written while no tilemap cell
  references it. A slot freed this frame is not handed out again until the next
  frame (a per-slot generation stamp), so the old word's tilemap copy reaches VRAM
  first. Unless the pool is otherwise full; then any free slot is taken rather
  than fail. This removes the VBlank budget question; the hardware risk becomes
  plain CPU time per step.
- **No shadow array.** The tilemap words themselves record each cell's slot.
  Each cell acquires its new tile before releasing the old word.
- **Reset point = the whole-tileset copy functions.** `CopyPrimaryTilesetToVram`,
  `CopyMapTilesetsToVram` and the connection-crossing primary reload start the
  cache for a streamed layout (pinned upload, tilemap buffers cleared) and turn
  it off for any other. Every VRAM-wiping path (`ResetScreenForMapLoad`, Flash's
  `CB2_DoChangeMap`, battle/menu returns) reloads through them, so no separate
  hooks were needed.
- **The engine keeps 15×15 of the 16×16 ring buffer current.** The
  `RedrawMapSlice*` functions draw buffer rows/columns 0–29, so tiles 30–31 on
  each axis hold whatever scrolled out. They stay refcounted, so the 16×16
  budget is still the right (slightly conservative) bound. The screen check
  checks the maintained 30×30 tiles only.
- **NORMAL-layer metatiles draw tile 0 on BG3,** not the stock `0x3014`
  "garbage" word, because slot 0x14 is a streamed slot.
- **Shop buy menu** acquires slots for its map view and never releases them;
  leaving the menu reloads the field, which resets the cache.
- **The build-time window check** covers the map's own grid with the border
  pattern around it, not a connected neighbour's strip (resolved at runtime).
  The screen check measures strips on the real backup layout.

**Map Walker.** The walker recipe had rotted. A chapter-era engine line set a
story flag the walker build doesn't generate (`FLAG_STARTING_OVER` in
`DoWhiteOut`, now `#if URANIUM_MAP_WALKER == FALSE`). The chapter's generated
tables also name chapter maps, so a walker over a chapter build needs the
chapter's maps in its list. The `full` corpus now keeps streamed maps instead
of excluding them as overflow.

**A second size limit: the map-data buffer.** The engine copies the current map
plus a 7-cell margin into a fixed buffer, `sBackupMapData[MAX_MAP_DATA_SIZE]`
(10240 cells, `fieldmap.c:184`). A map with `(w+15)*(h+14)` over that silently
loads **nothing but its border**, in every build, streamed or not. Found when the
screen check on 094 failed: its checker read past the buffer. 15 maps are over
(`output/scratch/map_data_size.py`). The largest are 094 (150×150, 27060 cells),
187 (22022), 143, 117, 106, and 184/133/008 (100×100). So 094 and 187 left the
streamed set; streaming fixes tiles, not this. Unsplit **040 needs 8272 cells
and fits**, as do 101 (8170) and 122 (9880).
- Raising the buffer costs 2 bytes a cell of EWRAM. 094 would need about 33 KB
  more, which is more than is free (about 18 KB after the cache).
- So the over-buffer maps need either splitting or a different backup-grid
  design. That is a rollout question, not stage 2.
- The build now fails loud for a streamed map over the buffer. The Map Walker
  `full` corpus still builds the other 13 silently border-only; that's filed
  separately.

**Map 040** exists only as split pieces in phase-3 output, so it can't be
streamed until stage 3 retires the split. Its screen check moves to stage 3.

**Results** (Walker ROM with CH01–CH08 maps + 094, 101, 122, 187;
`output/streaming/map_walker_stage2.gba`):

| Map | Pool tiles | Pinned | Worst window (build check) | Cache slots | Slack |
|---|---|---|---|---|---|
| 101 | 1717 | 172 | 565 | 836 | 271 |
| 122 | 1641 | 90 | 575 | 918 | 343 |
| (094, over the map-data buffer) | 1753 | 83 | 470 | 925 | 455 |
| (187, over the map-data buffer) | 1520 | 81 | 551 | 927 | 376 |

**Screen check, full serpentine** (stride 2, 8 churn crossings;
`output/screen_check_stage2.json`):

| Map | Kind | Size | Steps | Mismatches | Errors / overflows / drift | Peak live slots |
|---|---|---|---|---|---|---|
| 101 | streamed | 80×72 | 1656 | **0** | 0 / 0 / 0 | 525 of 836 |
| 122 | streamed | 80×90 | 2051 | **0** | 0 / 0 / 0 | 526 of 918 |
| 032 | stock (checker control) | 72×64 | 1621 | **0** | — | — |

The walker moves about two tiles per held step, so checks land on every second
position. A stale slot persists into later checks, so a missed one would still
show. On map 32 the walk stalled at one tile (15,44), and the follow-on harness
warp to 035 never landed. That's a Walker/harness quirk on a scripted
chapter map, not the cache.

Screen-check sensitivity was proven by corrupting one resident tile in VRAM:
exactly one `pixels` mismatch at that cell. A bumped refcount shows as drift.

**Operator walk (2026-10-17): passed.** "The graphics look pretty good." There
are small glitches at the edges of trees and similar objects, which the operator
reads as a Map Walker issue. The screen check found zero VRAM mismatches on those
maps, so whatever it is, VRAM matches the build's tile data (a source-art or
quantize edge, not the cache). Kevlar is as far as a walk can go in that ROM.

### Stage 3 progress (2026-10-17)

- **The split is retired.** `split_maps.json` is `{}`. `rpg2gba split-maps`
  restored `Map040.json` and the original transfers and connections.
- **One fix was needed:** `build_map_constants` now retires persisted piece
  constants whose split is gone. Without it, 40's re-mint of `MAP_NOWTOCH_CITY`
  collides with piece 14000, which held that name. The transpiler's gate reads the
  minted constants before staging, so the first build after un-splitting has to mint
  first (`output/scratch/mint_map_consts.py`; staging does the same afterwards).
- **The build:** tileset 1040 has 1323 metatiles and 1579 tiles (merge off). The
  worst window is 612 of 981 cache slots (slack 369). The map-data buffer needs
  8272 cells, under the 10240 cap. The 35↔40 seam is a remapped seam: 36 strip
  metatiles imported into 1040.
- **Suites:** CH04–CH08 were regenerated.
  - CH04, CH05 and CH07 changed only by rename: 14000→40, with coordinates
    shifted by the piece origin (+20, +12).
  - CH06 lost its 13 cross-piece transit beats (169→156). Its stair beat moved to
    whole-map coordinates, and the solver reordered the city route.
  - CH08's module is unchanged.
  - The operator approved them on the summary.
  - CH04's seam disposition was re-affirmed (same ruling, new content hash).
- **Tests:** 9 tests asserted split-era facts (piece ids, `MAP_NOWTOCH_CITY_PARK`,
  CH06's 30-map slice). They were updated to 40 and 24.
- **Screen check** (Walker ROM over the chapter maps + 101, 122,
  `output/streaming/map_walker_stage3.gba`; `output/screen_check_stage3.json`):

  | Map | Kind | Size | Steps | Mismatches | Errors / overflows / drift | Peak live slots |
  |---|---|---|---|---|---|---|
  | 040 | streamed | 79×74 | 3144 | **0** | 0 / 0 / 0 | 569 of 981 |
  | 035 | stock (control) | 42×57 | 64 | 0 | — | — |

  The 035 walk stalled at (20,2), the same Walker quirk as 032 in stage 2. The
  seam strip into 040 is covered by 040's own walk along its south edge.
- **Operator Walker walk of 040 (2026-10-17):** "Map 40 looks great."
- **CH08 gen suite: GREEN 498/498 from boot** (511 before, minus the 13 transit beats). Full pytest: 5558 passed.
- **Left for the exit:** the operator's real-game walk from CH06's end in Nowtoch
  (`output/playtest-gen/walk/nowtoch-streamed-walk.gba`, Nowtoch (32,73)).

### Seam swap (2026-10-17)

**Operator:** crossing Nowtoch → Route 2, "everything flashes". It's the same at any
connection where the tileset changes, and stage 4 prefers exactly those seams (§3.5).
- **Cause:** `LoadMapFromCameraTransition` rewrote the tiles (synchronous for streamed, a
  DMA queue for stock) and the palettes. The tilemap reached VRAM at a later VBlank, so the
  displayed frames in between showed the old tilemap over the new tiles. The probe saw two
  garbage frames going down and several wrong-tile frames going up
  (`output/scratch/seam_flash_probe.py`, strips in `output/scratch/seam_flash/`).
- **Operator's choice:** a one-VBlank swap, not a fade ("I'd rather keep the current
  glitch than have the dip"). It's a separate commit, so `git revert` undoes it.
- **How it works** (`field_stream.h`, "Seam swap"):
  - `SeamBegin` (on a primary-tileset change) records which slots the displayed frame
    shows, from the VRAM tilemaps and scroll. It also holds the palette transfer.
  - **Stock tileset loads** write every other slot at once and defer the visible ones.
  - **The streaming allocator** prefers non-visible slots, and its uploads to visible
    slots wait.
  - `SeamReady` (end of `CameraUpdate`) builds the copy list in main-loop time.
  - `SeamCommit` runs first in `VBlankCB_Field`. It DMAs the listed tiles and the three
    tilemaps and releases the palettes, all in that one VBlank.
  - Until then the field VBlank skips the scroll and tile-animation transfers. A transition
    frame that runs long just shows the old frame for longer.
- **Result:**
  - Zero jump frames in both directions; checked by eye on the strips.
  - The commit copies 144 tiles in 21 scanlines (VCOUNT 160→181) going down, and 2 tiles
    in 10 going up, out of 67 VBlank lines. The first version did the per-slot decisions
    inside VBlank and finished at line 226; the list moved that work out.
  - The pre-existing load stall (about 4–5 frames) now shows as a still frame instead of
    garbage.
  - Cost: 6 KB EWRAM for the copy list (now 93.5% used).
- **Operator walk on the swap ROM (2026-10-17): "That looks great!"** This is the stage 3
  exit. That walk was in an emulator; the flash-cart check of the swap is still open.
- **Not the swap:** a thin black band at the screen edge for the rest of the step after a
  crossing is the seam strip depth (#150), and it was there before.

### Stage 4: maps over the map-data buffer (2026-10-18)

**Operator:** "I don't want to break up maps with arrow warps, let's do the engine work".
Fifteen maps have a backup grid `(w+15)*(h+14)` over `MAX_MAP_DATA_SIZE` (10240), so stock
loads only their border (#148). The first is Route 3 (59, 130×66), in CH09. This limit is
separate from the tile cache.
- **How it works** (`fieldmap.h`, "windowed backup grid"):
  - A map that fits takes the stock path unchanged.
  - An oversized map keeps a 128×64 window of its grid in `sBackupMapData`, as a ring
    (`BIGMAP_INDEX`).
  - `BigMap_Track` recentres the window on the camera. It's called at the end of
    `CameraMove`, and in `InitMapView`. Each step refills one 64- or 128-cell strip.
  - At load, the layout and each connection are recorded as source rectangles
    (`FillConnection` records instead of copying). A read outside the window rebuilds the
    cell from them, so every read is correct wherever the window sits; only speed depends
    on tracking.
  - Runtime edits (setmetatile, doors, collision, the saved map view) also go to an
    overlay of up to 256 cells. It keeps only cells that differ from the layout, and
    re-applies them when the window slides back.
  - `assertf` fires on more than 8 rectangles or 256 edits.
  - Cost: 1.7 KB EWRAM (now 94.35%). The window reuses the existing buffer.
- **Pipeline:** `check_streamed_layout` no longer rejects oversized streamed maps.
  `screen_check` reads the ring when `gBigMap.active`, and fails if an on-screen cell is
  outside the window.
- **Result on Route 3** (Map Walker build with CH08's maps plus CH09's 59, 1, 54, 177):
  - The screen check gave 0 mismatches over 4581 positions (stock tileset, tile-merged).
  - `output/scratch/bigmap_ring_probe.py` compares every in-window cell with the ROM layout
    after a 70×35 loop. It found 0 mismatches, and the view stayed inside the window
    throughout.
  - Not yet exercised: the overlay (no scripted edits on a Walker build), and an oversized
    map that is also streamed.

## 6. Risks

| Risk | Mitigation |
|---|---|
| A code path writes map tiles to fixed slots that the audit missed | The audit found the hazard surface (intermission doc §I4). The screen check catches anything drawn wrong, and the CH08 suite covers gameplay paths. |
| VBlank timing on hardware | Uploads go before the tilemap in the same VBlank. Flash-cart check at Stage 2 exit, not at the end. |
| Refcount drift (a slot freed while still on screen) | The screen check plus back-and-forth churn runs. A debug-build consistency check can recount refs from the tilemaps on demand. |
| Unsplit 040 looks worse on one 13-palette set | By-eye comparison in Stage 0, before any engine work (§3.7). |
| Our tools assume fixed tile numbering | Streamed maps are opt-in; viewer/oracle work is in Stage 4. Until then, the screen check is the oracle for streamed maps. |
| Engine baseline change | Approval needed (CLAUDE.md §10). The changes are fenced under a new sentinel, `RPG2GBA STREAMING`, so they can be found against upstream. |

## 7. Operator decisions (2026-10-16)

1. **Engine baseline changes: APPROVED.** This covers 11-bit metatile ids for
   all maps and the opt-in streaming path.
2. **Streamed maps turn the tile merge OFF**, for full-quality art.
3. **Unsplit-040 colours on one 13-palette set: ACCEPTED** ("the colors look
   fine"). Map 040 is the prototype map, with the Map Walker and the screen
   check as the test bed for the unreached maps.
4. **CH09 is not opening.** The intermission continues on branch
   `intermission-streaming`. The operator asked that between-acts work live on
   a branch.
