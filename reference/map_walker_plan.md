# Map Walker — Design & Build Plan

**Status:** Proposed (awaiting build greenlight)
**Author:** build agent
**Date:** 2026-06-27

---

## 1. Purpose

The family quantization looks good in the Python map viewer, but the viewer and
the actual ROM don't always agree. We want a way to judge the *real* on-hardware
result across every map without playing through the game.

The **Map Walker** is a purpose-built debug ROM mode: it boots straight into the
player's house and lets you move a **cursor** (not a player character) tile-by-tile
across a map, follow **warps** between maps, and jump directly to any map. Nothing
from Emerald is shown — no player sprite, no NPCs, no triggered events. Only warps
are live. It exists to inspect quantized tileset art as it actually renders on the
GBA.

A second, equally important outcome: to walk *all* maps, we must finally build all
199 Uranium maps into the ROM (today only 3 are vendored). The converters already
exist and are proven by the viewer; this plan wires them over the full corpus.

---

## 2. Scope & non-goals

**In scope**
- A compile-time `URANIUM_MAP_WALKER` mode in the vendored engine (`engine/`).
- Cursor movement, warp-follow (A) / back-stack (B), warp reveal (hold R),
  jump-to-map menu (Start), debug HUD (L toggle).
- Building all 199 Uranium maps' **tilesets + layouts + headers + warps** into the
  ROM (no gameplay scripts).
- Aligning the Python viewer's quantization pool to match the ROM.

**Non-goals**
- No Poryscript / event / NPC / Phase-4 conversion. The walker strips everything
  but warps, so per-map gameplay logic is **not** needed.
- No map connections (seamless route stitching) — cursor is clamped to each map.
- Not a player-facing feature; this is a developer inspection tool.

---

## 3. Locked design decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Inter-map navigation | Warp-walk (A) + back-stack (B) **and** a jump-to-map menu |
| 2 | Map edges | Clamp the cursor to the real metatile grid (no border, no connections) |
| 3 | Warp marking | Cursor tile flashes white when on a warp; **hold R** reveals all visible warps |
| 4 | Back button | Full back-stack (every warp & menu jump pushes; B unwinds the whole chain) |
| 5 | Debug HUD | Toggle with **L**: map name + cursor (x,y) + metatile id under cursor |
| 6 | Movement feel | Smooth glide at walk speed (reuse the normal step machinery) |
| 7 | Tile display | Raw: `WEATHER_NONE`, neutral palette (no day/night tint); keep tile anims |
| 8 | Jump-menu scope | Uranium maps only (group 75) |
| 9 | Build mode | Compile-time flag; existing slice still builds when off |
| 10 | Foreign warps | Block any warp whose destination isn't in the built corpus |
| 11 | Map corpus | Build all 199 Uranium maps; warps-only, no script conversion |
| 12 | Quantization pool | Full-corpus pool per tileset in the ROM **and** fix the viewer to match |
| 13 | Tileset packing | Per-map physical tilesets sharing the full-pool palette (§5.4) |
| 14 | Overflow maps (9/199) | Excluded from v1; jump menu omits/greys them; dedup-or-split is a later follow-up |

---

## 4. Engine architecture (walker mode)

All engine paths are relative to `/home/b/repos/rpg2gba/engine/`. Line numbers are
from research and may drift; function names are authoritative. New code lives in a
new file plus sentinel-fenced hooks, all revertable against upstream.

### 4.1 New files
- `src/uranium_map_walker.c` — the walker field controller, cursor/warp sprites,
  HUD, jump menu, back-stack.
- `include/uranium_map_walker.h` — public hooks called from gated sites.
- `include/config/uranium_walker.h` — `#define URANIUM_MAP_WALKER FALSE` (flip to
  `TRUE` for the walker build).

### 4.2 Boot & flag
Reuse the existing PATHFINDER boot chain (intro/title/menu already bypassed):
- `src/intro.c` (`COPYRIGHT_START_INTRO`, ~1107) → `CB2_StartUraniumSlice`
- `src/new_game.c` `CB2_StartUraniumSlice` (~239) → stamps identity → `CB2_NewGame`
- `src/new_game.c` `WarpToTruck` (~137) → spawn override to
  `MAP_MOKI_TOWN_PLAYERS_HOUSE_1F` @ (7,7)

When `URANIUM_MAP_WALKER == TRUE`, after `CB2_NewGame` finishes its map-load loop,
install the walker field controller (a task + input hook) instead of normal field
control. The spawn tile (7,7) becomes the cursor's starting tile.

### 4.3 No player, nothing from Emerald
- **Invisible camera anchor:** keep the player object event but hide its sprite.
  After `InitPlayerAvatar` in `InitObjectEventsAtMapLoad` (`src/overworld.c:2578`),
  gated: `SetPlayerInvisibility(TRUE)` (`src/field_player_avatar.c:1750`). The
  object event remains so the camera (`SetCameraToTrackPlayer`, `overworld.c:2594`)
  and coordinate helpers keep working; we move it to move the view.
- **No NPCs:** gate `TrySpawnObjectEvents` (`src/event_object_movement.c:2888`) to
  return immediately under the flag — no object events spawn.
- **No coord/bg/script events:** gate `TryStartCoordEventScript`,
  `GetInteractedBackgroundEventScript`, and the on-warp map-script calls in
  `src/field_control_avatar.c` so they no-op under the flag. We do **not** mutate
  `gMapHeader.events` (it's in ROM); we gate the readers. Warps stay live.
- Because the generated 199-map headers are warps-only anyway (§5.3), this runtime
  gating mainly covers the 3 pre-existing slice maps that still carry events.

### 4.4 Movement & bounds clamp
Reuse the normal step pipeline (`PlayerStep` → `MovePlayerNotOnBike` →
`PlayerNotOnBikeMoving`) for smooth walk-speed glide. Replace collision with a
walker rule in `GetCollisionAtCoords` (`src/event_object_movement.c:6502`), gated:
- target tile inside the real grid `[0..width-1] × [0..height-1]` → `COLLISION_NONE`
- target tile outside → impassable

This yields free movement (walk onto any tile) **and** clamps to map bounds in one
hook, without enabling the global `OW_FLAG_NO_COLLISION` (which wouldn't clamp).
Map dimensions come from `gMapHeader.mapLayout->width/height`; convert cursor coords
with `MAP_OFFSET` (`include/fieldmap.h:23`, = 7).

### 4.5 Cursor & warp visuals (OAM sprites)
The cursor is always at screen center (the camera centers the anchor tile). Use a
hardware sprite at OAM priority 1 (in front of the top map layer, behind text),
following the region-map-cursor precedent (`src/region_map.c` `sRegionMapCursorOam`,
`SpriteCB_PlayerIcon` blink at ~16 frames):
- **Cursor frames:** frame A fully transparent (tile shows through), frame B a 2-px
  black ring around the 16×16 edge. Toggle ~every 16 frames → "outer two pixels
  blink between the tile's pixels and black."
- **On a warp tile:** switch the cursor to a whole-tile white↔transparent flash
  (the tile "flashes between white and its normal graphics").
- Detect "on a warp" by matching cursor (x,y) against `gMapHeader.events->warps[i]`
  (`include/global.fieldmap.h:200`/`165`); coords are map-local, no offset.

### 4.6 Warp reveal (hold R)
While R is held, position a small pool of white-flashing sprites over every warp
tile currently inside the 15×14 visible window (set `coordOffsetEnabled` so they
scroll with the map). Release R → hide the pool. Cursor's own flash is unaffected.

### 4.7 Warp follow (A) / back (B)
- **Destination side-table:** RMXP transfers target arbitrary (x,y), which the
  decomp `WarpEvent` (warpId only) can't hold. Emit a generated
  `gUraniumWarpDests[]` keyed by (mapNum, warpIndex) → (destGroup, destNum, destX,
  destY). The A-handler reads it directly.
- **A on a warp:** push current (mapGroup, mapNum, cursorX, cursorY) to the
  back-stack, then `SetWarpDestination(destGroup, destNum, WARP_ID_NONE, destX,
  destY)` + `DoWarp()` (`src/overworld.c:709`, `field_screen_effect.c` `DoWarp`).
  Block if destination isn't group 75 / not in corpus.
- **B:** pop the back-stack, `SetWarpDestination(...popped..., WARP_ID_NONE, x, y)` +
  `DoWarp()` → land on the exact tile you left.
- **Back-stack:** EWRAM array, depth ~32. Jump-menu teleports also push.

### 4.8 Jump menu (Start)
A list menu of group-75 maps by display name (pattern from the debug warp menu,
`src/debug.c:1490`, which already iterates `MAP_GROUP_COUNT`). Selecting a map:
push the stack, `SetWarpDestination(75, mapNum, WARP_ID_NONE, centerX, centerY)` +
`DoWarp()`. Cursor starts at map center.

### 4.9 Debug HUD (L toggle)
A small corner window (standard textbox/window system) showing:
- map display name (from the generated name table / `regionMapSectionId`)
- cursor (x, y) in map-local coords
- metatile id under cursor (`MapGridGetMetatileIdAt(x+7, y+7)`, `src/fieldmap.c:443`)

Toggled on/off with L so it never obscures art while judging.

### 4.10 Raw display (no weather/tint)
On every walker map load: force `WEATHER_NONE` and disable the expansion's
time-of-day palette blend so colors equal the raw quantized values. Keep animated
tiles (water/flower) — they're part of the tileset. (Exact tint hook to be located
in the expansion's time-of-day palette path during implementation.)

---

## 5. Build all 199 Uranium maps (pipeline)

Today's gate: `SLICE_MAP_IDS = [49, 48, 32]` hard-coded and mirrored in
`scripts/assemble_pathfinder.py:47`, `scripts/stage_slice_scripts.py:44`,
`scripts/map_viewer_common.py:52`, `scripts/pathfinder_tile_census.py:25`,
`scripts/pathfinder_warp_trace.py:19`. The converters themselves are general and
viewer-proven; the all-corpus orchestrator `tileset_converter/phase5.py`
`convert_all` is a `NotImplementedError` stub.

All 199 maps' inputs already exist on disk:
`output/uranium-build/maps/Map*.json` (RMXP tile grids + events/warps),
`output/uranium-build/tilesets.json`, raw art under `$RPG2GBA_URANIUM_SRC`.

### 5.1 Single source of truth for the map set
Replace the five `SLICE_MAP_IDS` copies with one resolver (e.g. discover all
`output/uranium-build/maps/Map*.json` ids, or a config constant), with a "slice vs
full" selector so the 3-map slice remains reproducible.

### 5.2 Implement `phase5.convert_all`
Drive the **existing** converters over the full corpus:
- group maps by `tileset_id`; run `build_slice_tilesets` / `emit_tileset` per
  tileset over **all** maps that share it (full-corpus pool) → `tiles.png` (4bpp),
  `palettes/NN.pal`, `metatiles.bin`, `metatile_attributes.bin`, tileset structs,
  `tileset_map.gen.json`.
- `convert_layout` per map → `map.bin` + `border.bin`, registered in
  `layouts.gen.json`.
- emit map headers + warp events for all maps (generalize `assemble_pathfinder.py`
  passes; they're already parameterized by `slice_ids`).

### 5.3 Warps-only emission
Emit each map header with `objectEventCount = coordEventCount = bgEventCount = 0`
and only warp events (from RMXP code-201: `[mode, dest_map_id, dest_x, dest_y]`).
Build the `gUraniumWarpDests[]` side-table (§4.7) alongside. **No** Poryscript /
event / NPC conversion. Empty `scripts.inc` per map. Run `build_map_constants` over
all 199 for dir names, map/layout/mapsec consts, and display names (HUD + menu).

### 5.4 Tileset packing — the metatile budget (measured)

A census (scratchpad `census_metatiles.py` / `census_per_map.py`, using the
converter's own `column_keys_for_maps`) settled the overflow risk with real
numbers. GBA metatile id is 10-bit → hard cap **1024** per tileset (primary 512 +
secondary 512), effective budget **1022** after void+warp.

- **Pooling all maps that share a tileset overflows badly:** 19 of 38 tilesets
  exceed 1024, several by 3–4× (ts19/59 maps = 3151, ts22 = 3766, ts55 = 3405). So
  a single shared physical tileset per RMXP tileset is **not viable**.
- **Per-map tilesets fit for 190 of 199 maps:** computed per individual map, 162
  fit in a primary half alone (<512), 28 need a dedicated primary+secondary pair
  (512–1024). Tile *diversity*, not area, drives the count.
- **9 maps overflow even a dedicated per-map pair:** Map094/ts22 (1831),
  Map101/ts28 (1556), Map187/ts50 (1412), then Map040, 084, 117, 143, 071, 144
  (1063–1279).

**Chosen strategy: per-map physical tilesets**, each carrying only that map's
metatiles and referencing the **shared full-corpus family palette** (so the §6
viewer-parity / pool decision is preserved — palettes pool per RMXP tileset,
metatiles are per-map). This is *simpler* than per-group packing because metatiles
no longer pool across maps. The converter's grouping unit changes from "RMXP
tileset" to "map"; `convert_layout`'s column→metatile-id map becomes per-map.

**The 9 overflow maps** are out of scope for the first build (handled per the
decision recorded below — exclude / dedup / split). The emitter still **fails loud**
naming any map/tileset that exceeds the budget (CLAUDE.md §4.5); no silent
truncation.

### 5.5 ROM size
Per-map tilesets duplicate tile graphics across maps that share source art, but the
rough estimate is ~8–12 MB of Uranium data on top of the ~16 MB Emerald base →
likely under the 32 MB cap. **Confirm by actual build.** If it overflows: fall back
to per-group packing (share art within a metatile-budget-bounded group) and/or drop
stock Emerald map data (the walker never shows it).

---

## 6. Viewer parity

Change the pool scoping in `scripts/map_viewer_common.py` (~209–219) from
`{32,48,49} ∪ {opened map}` to **all maps sharing the opened map's `tileset_id`**.
The viewer then quantizes with the same pool the ROM uses, becoming a faithful
preview. Keep a way to reproduce the old slice pool for regression comparison.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Metatile overflow (MEASURED: 19/38 tilesets pooled, 9/199 maps even per-map) | Per-map tilesets (§5.4) fit 190/199; 9 overflow maps handled separately; emitter fails loud on any overflow |
| ROM exceeds 32 MB | Per-map est. ~8–12 MB Uranium over ~16 MB base; confirm by build; fall back to per-group packing / drop Emerald map data |
| Time-of-day tint path differs in expansion | Locate exact hook during impl; fall back to forcing a fixed palette state |
| RMXP arbitrary-coord warps | Side-table `gUraniumWarpDests[]` bypasses the warpId-only `WarpEvent` |
| Camera with invisible anchor | Keep the player object event alive (invisible) as the camera's followed sprite |
| Viewer pool change shifts known-good slice colors | Keep slice-pool repro mode for before/after comparison |

---

## 8. Checkpoints (boot gates)

1. **Walker on 3 maps** — builds with the flag, boots in mGBA; cursor blink, warp
   white-flash, A/B back-stack, R reveal, L HUD, Start jump menu all work. *User
   walks it.*
2. **All 199 maps** — `phase5.convert_all` emits the corpus; ROM builds (watch size
   + metatile overflow); walker traverses arbitrary maps. *User spot-checks
   tilesets vs viewer.*
3. **Viewer parity** — viewer pool aligned; viewer ≈ ROM by eye on sampled maps.

---

## 9. Implementation sequence

**Phase A — Engine walker (on the current 3 maps)**
1. Add `include/config/uranium_walker.h` flag + new
   `uranium_map_walker.{c,h}` skeleton; wire the field controller under the flag.
2. Invisible anchor + event gating (§4.3); raw display (§4.10).
3. Movement + bounds clamp (§4.4).
4. Cursor sprite + blink + warp white-flash (§4.5).
5. A/B warp + back-stack using a temporary hand-built side-table for the 3 maps
   (§4.7).
6. R reveal (§4.6), L HUD (§4.9), Start jump menu (§4.8).
7. **Checkpoint 1.**

**Phase B — Build all 199 maps**
8. Single source of truth for the map set (§5.1).
9. Implement `phase5.convert_all` + overflow guard (§5.2, §5.4).
10. Warps-only emission + `gUraniumWarpDests[]` + map constants for all 199 (§5.3).
11. Full build; measure ROM size; fix overflow/size issues.
12. **Checkpoint 2.**

**Phase C — Viewer parity**
13. Full-corpus pool in the viewer (§6).
14. **Checkpoint 3.**

---

## 10. Open items
- Exact time-of-day/tint disable hook in the expansion (locate during Phase A).
- Whether stock Emerald map data must be dropped for ROM size (decide at step 11).
- Jump-menu UX for ~190 entries (flat scroll vs grouped) — refine at step 6/10.
- The 9 overflow maps (Map094/101/187/040/084/117/143/071/144): excluded from v1;
  revisit with a metatile-dedup pass and/or intra-map splitting as a follow-up.
