# Pathfinder Findings

> The running log of what the pathfinder slice surfaces (roadmap S9). Started with
> S1. Each entry: what we found + the disposition. Read alongside
> `PATHFINDER_SLICE_ROADMAP.md`.

---

## S1 — Slice warp trace (2026-06-15)

**Method.** `scripts/pathfinder_warp_trace.py` (read-only) walks
`output/uranium-build/maps/Map0{49,48,32}.json` events→pages→list, collecting every
code-201 Transfer (params `[method, map_id, x, y, dir, fade]`) and every 355/655
script warp (`pbTransferPlayer` / `pbCaveEntrance` / `pbCaveExit`). All slice warps
are **literal** (no variable-designated targets).

### Reconstructed topology

```
            stairs (49 EV003 @12,3 → 48@4,3)
   Map049  ───────────────────────────────►  Map048
  (1F, tileset 19, 30×15)   ◄───────────────  (2F, tileset 19, 20×15)
   SPAWN @ (7,7)            stairs (48 EV002 @3,3 → 49@11,3)
        │  ▲
 street │  │ town→house
  door  │  │ (32 EV005 @28,31 → 49@10,9)
 (49 EV002 @10,11 → 32@28,31)
        ▼  │
   Map032  Moki Town  (tileset 22, 72×64, 52 events)
        │
        ├─ buildings / route → OUT OF SLICE (see table)
```

**Correction to the roadmap's S1 guess.** The roadmap assumed `48→32` for the town
exit; the data shows **049** carries the street door (it has the bottom-edge door
at (10,11) and the player spawns there), and **048 is the upper floor** reachable
only from 049. The roadmap slice table + S4 naming had 1F/2F swapped — fixed.
Inference basis: 049 has a bottom-of-map street door → ground floor; 048 has no
street door, only a top-of-map staircase → upstairs.

### Warp disposition table

| Map | Event @ tile | → target | Disposition | Why |
|---|---|---|---|---|
| 049 | EV003 @ (12,3) | Map048 @ (4,3) | **KEEP** | stairs up (in-slice) |
| 049 | EV002 @ (10,11) p1,p3 | Map032 @ (28,31) | **KEEP** | street door → town (in-slice) |
| 049 | Letter @ (5,8) | Map048 @ (4,6); Map049 @ (6,8) | **KEEP** | story event; both targets in-slice. May not trigger in v1; harmless |
| 048 | EV002 @ (3,3) | Map049 @ (11,3) | **KEEP** | stairs down (in-slice); 048's *only* warp |
| 032 | EV005 @ (28,31) | Map049 @ (10,9) | **KEEP** | town → player's-house door (in-slice) |
| 032 | EV003 @ (17,11) | Map050 @ (14,18) | **NO-EMIT** | building (out-of-slice) |
| 032 | Trainer(6) @ (27,42) | Map050 @ (14,7) | **NO-EMIT** | building (out-of-slice) |
| 032 | EV006 @ (43,31) | Map064 @ (9,12) | **NO-EMIT** | building (out-of-slice) |
| 032 | EV007 @ (24,42) | Map065 @ (9,12) | **NO-EMIT** | building (out-of-slice) |
| 032 | EV017 @ (56,42) | Map172 @ (10,10) | **NO-EMIT** | building (out-of-slice) |
| 032 | EV023/036/037 @ (8,43-45) | Map033 @ (70,11) | **WALL** | west exit to a CAVE (`pbCaveEntrance`); map-edge → wall so the player can't walk off into unconverted space |

### v1 walling/stubbing policy (resolves S1's keep/wall/stub question)

- **NO-EMIT** for out-of-slice *building doors* (Map050/064/065/172): emit no
  `warp_event`. The door metatile stays; stepping on it does nothing. No `MAP_*`
  reference to the missing maps → **zero dangling targets** (we never name
  050/064/065/172/033).
- **WALL** the three west cave-exit tiles (→Map033): place an impassable metatile
  there so the player cannot walk through the town's west edge into nothing. (Also
  drop the `pbCaveEntrance` script calls — out-of-slice.)
- **KEEP** the five in-slice warps; S5 emits real `warp_event`s for them.

Result: Moki Town is a closed sandbox where only the player's-house door works;
the interiors 049↔048 round-trip; nothing references an out-of-slice map.

### Notes for downstream steps

- **Moki Town dominates the slice effort.** 72×64 = 4,608 cells (vs 30×15 and
  20×15 for the interiors) and 52 events. It will dominate S2 tileset-22 authoring
  (more distinct static tiles), S5 event placement, and S6 conversion. The two
  interiors are small and share tileset 19.
- **Slice #2 cave candidate identified.** Map033 (west of Moki Town, entered via
  `pbCaveEntrance`) is the natural next slice — it exercises the `requires_flash` /
  `gTileset_General`+`gTileset_Cave` darkness path we verified is engine-native.
- **Spawn sanity:** player spawns Map049 @ (7,7); reachable warps from there are the
  street door (10,11) and the up-stairs (12,3) — both within a small ground floor.
- **No variable-designated or `pbTransferPlayer` warps** in the slice — all transfers
  are literal code-201, so S5 warp wiring is straightforward.

---

## S2 prerequisites P1 + P2 (2026-06-15)

**P1 — passages oracle generated.** `deserialize.rb tilesets` →
`output/uranium-build/tilesets.json` (60 tilesets; each has `passages` /
`priorities` / `terrain_tags` flat arrays indexed by tile_id).

**P2 — tile-id census.** `scripts/pathfinder_tile_census.py` (read-only; reproduce
anytime). Distinct *normalized* tiles actually used by the slice:

| Tileset | Distinct tiles | Slice cells |
|---|---|---|
| 19 (interior) | **117** | 49: 450, 48: 300 |
| 22 (Moki Town) | **316** | 32: 4,608 |

**Finding:** the earlier "~28 metatiles" estimate was wrong — **433 distinct
tiles**, Moki Town being 316. *But* the distribution is steeply power-law: in
tileset 22 one tile (id 384 grass) = 2,025 occ and the top ~15 cover most cells;
the tail is 1–3-occ building facades. **The `passages` column is clean per-tile
collision ground truth** (floor/grass=`0` passable, walls=`15` blocked) and even
encodes ledges (ids 840–842 = `14` = blocked L/R/U, open down = south ledge) — a
better collision source than inheriting from the substituted metatile (Q3). The
`priorities` array marks over-the-player tiles (roofs/treetops) that should not
block.

**DECISION (user, 2026-06-15): pure passability buckets first, hand-map later.**
Do not hand-author 433 tiles for throwaway Approach-A art. v1 maps every tile by
its source `passages` → a generic **passable** vs **blocked** metatile per tileset
(plus a void/border tile), with collision taken from `passages`. Warp/door/stair
tiles need no special metatile — they are walkable (passable bucket) and S5's
`warp_event` fires on the coordinate regardless of the tile's look. Recognizable
hand-mapping of the high-frequency tiles is a **later refinement iteration**, not
a v1 blocker. See the amended `PATHFINDER_STEP2_TILE_MAP_PLAN.md`.

## S2 — bucket metatile harvest (2026-06-15)

`scripts/harvest_bucket_metatiles.py` decoded the vanilla analogue maps' `map.bin`
/ `border.bin` (block = `metatile | collision<<10 | elevation<<12`) and ranked
metatiles by collision class. Picks written to `reference/tileset_map.json`
`buckets`:

| Uranium tileset | primary + secondary | passable | blocked | void |
|---|---|---|---|---|
| **19** interior | `gTileset_Building` + `gTileset_BrendansMaysHouse` | `0x201` (513) floor ×23 | `0x26E` (622) wall | `0x001` (1) black void |
| **22** town | `gTileset_General` + `gTileset_Petalburg` | `0x001` (1) grass ×213 | `0x1D4` (468) tree | `0x1D4` (468) tree |

All six ids are harvested from real vanilla `map.bin`s using the **same** tileset
pairs we assigned, so they are guaranteed-legal metatiles. `blocked`/`void` are
"good enough obstacle" picks (the town blocks render as tree fragments, house
walls may be a furniture tile) — fine for pure-buckets v1; the hand-mapping pass
refines them.

**Harvest caught a plan bug:** the interior primary is **`gTileset_Building`** (the
indoor primary), not `gTileset_General` (outdoor) — fixed in the step-2 plan +
`tileset_map.json`. This is exactly why the "harvest from the real vanilla map"
method exists: the map's own layout entry is authoritative for the tileset pair.

## S2 — tile_map.py implemented + validated (2026-06-15)

`src/rpg2gba/tileset_converter/tile_map.py` implemented: `load_tile_map` (also
loads the `tilesets.json` passages/priorities oracle), `_validate`, `lookup`
(explicit `tiles` → bucket fallback by `passages`), `tileset_for`, `void`,
`passage`/`priority`/`is_passable` accessors. 8 unit tests pass, ruff clean, full
suite **353 passed / 17 skipped**. Confirmed the oracle **replicates passage across
all 48 autotile variants** (ts19/ts22 ids 48–95 identical), so `passages[tile_id]`
is correct without normalization.

**Walkability validated** via `scripts/pathfinder_collision_preview.py` (RMXP-style
top-down multi-layer passability + BFS from spawn): Map049 interior is walkable
(spawn passable, 114-cell room, stairs→2F reachable); Map032 town spawn walkable
(686 cells reachable); walls/void correctly blocked.

**FINDING — warp/door tiles read BLOCKED; must be force-walkable.** Map049's
door→town tile (10,11) is drawn into the bottom wall, so its source passage is
blocked and BFS can't reach it. pokeemerald warps require the player to **step onto**
the warp tile, so **every S1 warp-source coordinate must be force-set collision 0
in the emitted layout**, regardless of source passage. This is *not* a `tile_map`
bug — it's a layout/wiring rule: `convert_layout` (S3) takes a walkable-override set
(the warp coords, owned by S5) and forces those cells to collision 0. Recorded in
the step-3 + step-5 plans.
