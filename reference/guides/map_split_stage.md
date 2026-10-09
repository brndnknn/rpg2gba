# Map-split stage — design

**Status: APPROVED 2026-10-09 (operator).** First user: map 40 (Nowtoch City, CH06).
Rulings on §10:
1. The approach, `reference/split_maps.json` and the id scheme are approved.
2. The build agent picks the piece names.
3. (61,23), (41,42) and (27,60) are dropped from the cuts.
4. The engine popup fix, §8 (a), is approved.
5. NPCs that can't be seen across a cut are accepted for now.

## As built (2026-10-09)

The code lives in `src/rpg2gba/map_split/` (`ids`, `spec`, `derive`, `stage`,
`engine`). It runs as `rpg2gba split-maps`, and also automatically after
`phase3`. It differs from the sections below in four places:

- **The original JSON moves out of `maps/`.** It goes to `maps_presplit/`
  instead of staying beside the pieces (§2). The world graph
  (`traversal/world.py`) globs every `Map*.json`, so leaving the original in
  place would double-count map 40.
- **Other maps' transfers are rewritten in place.** Every transfer into map 40
  is rewritten in its own map's JSON. Each original is kept in
  `maps_presplit/` and restored at the start of the next run, so the stage
  stays idempotent. Because of this, there is no `split_resolve` call in the
  transpiler or in metadata_wiring (§6). `connections.json` is rewritten the
  same way, with `connections_presplit.json` as the backup.
- **The popup check is per split map, not per MAPSEC (§8).** Every slice map
  currently shares `MAPSEC_LITTLEROOT_TOWN` (`metadata_wiring.DEFAULT_MAPSEC`),
  so a "same MAPSEC" test would silence popups across the whole game. The
  engine instead compares `gLastUsedWarp` with the current map against a
  generated sibling table (`engine/src/uranium_split_maps.c`,
  `src/data/uranium_split_siblings.gen.h`). It skips the popup only when both
  maps are pieces of the same split map.
- **Split pieces never get the tile merge.** `rom_quantize.tile_merge_exempt`
  keeps it off for any tileset holding a piece. That was the purpose of the
  split, but §1–§11 never said it explicitly.

The ROM tile counts per piece came out close to the §1 estimates: main 946
(including the Route 2 strip), Gym Plaza 993, Park 667, and every other piece at
574 or fewer.

## 1. Problem and the decision it implements

Map 40 does not fit one GBA tileset without the near-duplicate tile merge, and
the operator doesn't want to keep that merge for this map. Without it the whole
map is 1051 metatiles / 1544 tiles, against caps of 1024 / 1024. The operator's
compromise (2026-10-09):

- keep the real scrolling connection Route 2 (35) ↔ Nowtoch (design R);
- cut map 40 into pieces joined by **arrow warps**, with the main path from
  Route 2 as one piece;
- give each piece **real art for every cell the player can see**, including
  art across a cut. There is no visible filler and no merge.

The chosen cut set is "base cuts + A". Base cuts are the `potential arrow warp
boundaries` set in `reference/map_feedback/Map040.json`; cut A is the x=42,
y 22–30 line. R3 and R5 (the park and the stairs-east area) share a piece.
Measured budgets (exact quantize + emit, ROM palette settings, merge off):

| Piece | Area | Rect | Metatiles | Tiles |
|---|---|---|---|---|
| P0 main (+ Route 2 strip) | Route 2 entrance → plaza | 24×62 @ (22,12) | 496 | 965 |
| P1 | gym yard, Poké Center front, NE plaza | 33×30 @ (40,9) | 486 | 995 |
| P2 | park + stairs-east (R3+R5) | 38×25 @ (40,31) | 372 | 667 |
| P3 | west block | 22×22 @ (6,30) | 256 | 570 |
| P4 | SW block | 23×14 @ (5,51) | 217 | 492 |
| P5 | NW garden | 18×18 @ (11,13) | 235 | 556 |
| P6 | SE strip | 21×14 @ (41,56) | 159 | 403 |

P1 has only 29 tiles of headroom. The fallback if it overflows is a short cut
between the gym yard and the NE plaza, around y=20 east of x=52, which keeps
the EV018 gym cutscene (x 49–50) inside one piece. No scripted multi-step move
crosses any cut in this set.

## 2. Approach: split upstream, as synthetic maps

The split runs as a stage **between deserialization and everything else**. It
reads `output/uranium-build/maps/Map040.json` and writes one ordinary map JSON
per piece. Every downstream consumer (layout, tilesets, metadata_wiring,
transpiler, registry, assembly, playtest) then sees plain maps. The one
exception is coordinates that point *into* a split map (§6).

The alternative was splitting at emit time, inside each consumer. That would
put split awareness into every module that touches a map id. Splitting
upstream confines it to one stage plus a single resolver.

Piece ids are synthetic: **`10000 + origin*100 + k`**, with `k` = 0 for the
main piece. Map 40's pieces are therefore 14000–14006. This can't collide with
a real Uranium id (max 999). `Map{:03d}` formatting renders them as
`Map14000`.

The original `Map040.json` stays in `maps/` untouched, so the stage is
idempotent: it re-reads the original on every run and overwrites its own
outputs. A split origin is **excluded from the build** and replaced by its
pieces through one expansion function, `map_set.expand_split_ids` (§7).

## 3. Source of truth: `reference/split_maps.json`

This adds a new §4.3 row: *map split decisions (cut cells, piece identity) →
`reference/split_maps.json`*. It is hand-authored and lists one entry per
split origin. In the example below, the seed cells and names are illustrative:

```json
{
  "40": {
    "cuts": [[28,23], [28,24], ...],
    "pieces": [
      {"k": 0, "name": "Nowtoch City",          "seeds": [[34,60]]},
      {"k": 1, "name": "Nowtoch City East",     "seeds": [[55,25]]},
      {"k": 2, "name": "Nowtoch City Park",     "seeds": [[52,42], [60,45]]},
      ...
    ],
    "decided": "2026-10-09, operator (base cuts + A)"
  }
}
```

- `cuts`: source cells that become walls. A cut cell that has walkable pieces
  on two *opposite* sides becomes an arrow-warp pair (§5). Any other cut cell
  is just a wall.
- `pieces`: each piece is named by one or more **seed cells**. Its walkable
  area is the union of the components that contain its seeds, after the cut
  cells are removed. Two seeds join components that the cuts already
  separate, e.g. R3+R5, which are linked by scripted stairs.
- `name`: sets the display name and therefore the `MAP_*` constant.
  `map_name_overrides.json` is still the rule for unsplit maps.

The viewer exports (`map_feedback/`, `map_splits/`) stay planning aids. The
build reads only this file.

## 4. Derivation: from the spec to piece maps

All inputs are deterministic: map JSON, `tilesets.json` and the cut spec.

1. **Walkable cells:** our collision (`compare_collision.our_blocked`),
   flood-filled from every warp arrival into the seam component. This is the
   same reach model as `map_viewer_common.reachable_cells`, which moves into
   `src/`. Cut cells are then removed.
2. **Components → pieces** via seeds. The stage **fails loud** if:
   - a walkable component has no seed (unassigned area);
   - a seed sits on a cut or blocked cell;
   - seeds of two different pieces land in one component (the cuts don't
     separate them).
3. **Cell ownership:** every source cell goes to its nearest piece by 8-way BFS
   from the pieces' walkable cells. Ownership decides which piece an event,
   door or arrival tile on a non-walkable cell belongs to.
4. **Piece rectangle:** the bounding box of the camera box around the piece's
   walkable cells, clipped to the source map. The camera box is ±7 columns and
   ±5 rows: the visible extent, `connection_remap.STRIP_DEPTH_EW/_NS`. Outside
   this rectangle the player never sees anything except the map's border block,
   and that is already how map 40's real edges render.
5. **Piece tiles:** crop the source layers to the rectangle.
   - Cells within camera range of the piece's walkable cells keep their real
     art, including cells owned by another piece.
   - Cells in the rectangle that are never in view become the piece's **filler
     column**. That is the border block's column, so it adds no new tiles.
     This keeps the emitted budget equal to the measured one.
   - Cut cells keep real art and are forced blocked.
6. **Map limit:** `(w+15)·(h+14) ≤ 10240` is asserted per piece. The largest,
   P0, is 39·76 = 2964.
7. **Events:** each event goes to the piece that owns its cell, with x/y
   rebased to the rectangle. **Fails loud** if an event's page refers to an
   event in another piece. That covers Set Move Route on another event, Set
   Event Location, `addobject`/`removeobject` targets, and an autonomous
   patrol whose route crosses a cut cell. All of these would silently break.
8. **Metadata:** each piece inherits the origin's music, weather, map type,
   encounter table and **MAPSEC**, so the region map and popup treat the
   pieces as one town (§8).

## 5. Arrow warps between pieces

These reuse the seam-warp machinery (`seam_warps.py`: `behavior_cells_for`,
`warp_pairs_for`, `WarpSpec(direct_pair=True)`). The stage emits the
seam-warp-shaped rows in memory; it does **not** write them into
`reference/seam_warps.json`, which stays hand-authored.

Take a cut cell `c` with walkable `a` in piece A and walkable `b` in piece B on
opposite sides of it:
- `a` gets an `arrow_warp_<dir a→c>` behaviour copy, and `b` gets
  `arrow_warp_<dir b→c>`.
- They form a direct pair, so stepping toward the cut from `a` lands on `b`.
- The arrival never re-fires, because the player is moving the opposite way
  to `b`'s arrow, as with today's seams.
- The cut cell itself is a blocked wall drawn with its real art.

Cost: one behaviour-copy metatile per distinct arrow cell art, and zero new
tiles.

**The current base cuts need three fixes before they're valid:**
- **(61,23) is a door arrival tile** for Map046 EV018's transfer. It can't be a
  cut, so remove it.
- **(41,42) and (27,60) border no walkable piece**, so they are inert walls. That
  is allowed, but they're probably leftovers.
- Line-end cells that border only one piece, such as (28,26) and (26,42), also
  become plain walls. That's fine.

## 6. Coordinates that point into a split map

These include transfers (code 201, from anywhere in the corpus), heal and
respawn tiles, connections, strip_list and seam_warps entries, playtest and
route locations, and manifest beats. All of them name `(40, x, y)` in RMXP
coordinates. One function translates them:

```
split_resolve(uid, x, y) -> (piece_uid, px, py)   # identity for unsplit maps
```

It resolves by cell ownership (§4.3) and **fails loud** on a cut cell or a cell
outside every piece's rectangle. Callers that must route through it:
- `metadata_wiring` warp resolution;
- the transpiler's `TRANSFER_PLAYER` (`warp_lines`);
- `heal_locations`;
- `connections` (below);
- playtest/beat_gen location loaders.

Transfers into map 40 found in the corpus today, and where they land:

| Source | Arrival | Piece |
|---|---|---|
| Map037 EV002 (Passage Cave exit, the **CH05→CH06 crossing**) | (68,43) | P2 |
| Map042 EV005 (gym) | (49,14) | P1 |
| Map044 EV002 (metro) | (34,19) | P0 |
| Map046 EV001/EV023 | (14,35) / (19,35) | P3 |
| Map046 EV004, Map047 EV001 | (42,61) / (47,61) | P6 |
| Map041 EV001 (mart door tile) | (23,33) | P3, by ownership |
| Map043 EV002/EV009 (PC door tile) | (24,55) | P4, by ownership |
| Map047 EV003 | (19,55) | P4 |
| Map046 EV018 | (61,23) | P1, by ownership, **but currently a cut cell** — see §5 |

**Connections:** a connection on the origin's edge goes to the piece whose
rectangle covers the connection's whole span on that edge, with the offset
rebased by the rectangle origin. The stage fails loud if zero pieces or more
than one piece covers it. Route 2's edge (y=73) is covered by P0 alone. Design
R's strip import and remap tables then apply to P0 ↔ 35 unchanged. Pieces have
no connections to each other.

**Identity that does NOT move:** self-switch and hide flags stay keyed by the
**origin** id and the original event id (`FLAG_MAP040_EVENT079_SSA`). The
registry's persistent state is untouched and names stay stable if the cuts
change later. Script labels follow the piece id (`Map14000_EV079_…`), since
labels are regenerated anyway.

## 7. Map lists and chapter tooling

- `chapters.json` and the chapter docs keep the origin id 40; chapter
  membership is a Uranium concept.
- `map_set.expand_split_ids(ids)` replaces 40 with 14000–14006 wherever a build
  list is consumed: the `SLICE_MAP_IDS` consumers, tileset groups, assembly,
  `slice_growth`.
- **Routing, beat_gen and playtest** see the pieces as ordinary maps with
  arrow-warp edges. CH04's seam warp was the precedent, so the solver has
  handled arrow pairs before. This layer is the least-known part of the change.
  The first implementation step is a survey of every place there that reads a
  map id as "Uranium map" vs "GBA map", before committing to the expansion
  point.
- The viewer keeps showing the original map 40. A piece view can come later.

## 8. Engine: map-name popup on arrow warps

On warps, the fork shows the popup whenever `showMapName` is set
(`overworld.c:2172` and `:2420`). The guard that skips a popup when the MAPSEC
hasn't changed (`OW_HIDE_REPEAT_MAP_POPUP`, `overworld.c:965`) exists **only on
the connection path**. Crossing a cut would therefore show "Nowtoch City" every
time.

There are two options:
- **(a) Recommended:** a fenced `URANIUM PATHFINDER SLICE` edit that applies the
  same "same MAPSEC as the map just left → no popup" check on the warp path.
  This changes baseline behaviour (vanilla shows the popup on re-entering the
  same section by door), so it needs approval under §10.
- **(b)** `showMapName = FALSE` on pieces 1–6. P0 still pops up on every return
  from a side piece, and the side pieces never pop up even when you arrive from
  a building.

## 9. Tests

- **Derivation:** components from seeds; each fail-loud case; rectangle =
  camera box clipped to the map; filler only outside camera range.
- **Events:** rebasing; the cross-piece reference fail-loud cases (move route,
  Set Event Location, add/remove object, patrol over a cut).
- **Arrow pairs:** pairing geometry; one-sided cut cells become walls.
- **`split_resolve`:** ownership of non-walkable door tiles; fail-loud on cut
  or out-of-rectangle cells.
- **Connections:** rebase, and fail-loud when no piece or several pieces cover
  the edge.
- **Idempotence:** two runs produce byte-identical output, and the original
  `Map040.json` is untouched.
- **Golden:** map 40 with the approved spec gives seven pieces whose emitted
  budgets match §1 within a small tolerance. The stage fails loud on any piece
  over 1024/1024, which `build_slice_tilesets` already does.

## 10. Operator decisions needed

1. Approve the approach, the new `reference/split_maps.json` (§3) and the
   synthetic id scheme (§2).
2. **Piece names**, which become the `MAP_*` constants. P0 keeps
   `MAP_NOWTOCH_CITY`.
3. Remove (61,23) from the cuts. Keep or drop (41,42) and (27,60).
4. The popup: engine tweak (a) or `showMapName` (b) (§8).
5. **NPCs visible across a cut:** an NPC standing just past a cut is in view
   from the neighbouring piece but isn't present there, so it can't be seen.
   The default is to accept this, since it's cosmetic. The alternative is
   copying static, script-less NPC sprites into neighbours whose camera reaches
   them.

## 11. Build order once approved

1. Survey of map-id consumers in routing, beat_gen, playtest and manifest
   (bounded, read-only), then fix the expansion point.
2. `split_maps.json` loader and validation, the derivation (§4), and the stage
   writing the piece JSONs. Unit-tested.
3. `split_resolve` wired into the §6 callers; arrow pairs into the seam-warp
   path; connection rebase.
4. `expand_split_ids` into the build lists; full suite.
5. Assemble, then `make modern`, then the remap header for P0↔35. Then the
   CH06 loop as usual (manifest → beat_gen → review doc → walk).
