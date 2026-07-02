# Walker Checkpoint 2 sign-off — certification + deferred findings (2026-07-02)

User boot-walked the 8-map batch ROM (49, 48, 32, 33, 50, 64, 65, 172) and the
map-viewer perf pass. **Everything functional passed** — boot, cursor, warp
follow (A) + back-stack (B), HUD (L), warp-reveal (R), START jump menu, all
warp pairs, viewer speedups. Two fidelity items were marked `[-]` and
**deliberately deferred past the Phase B merge**. They are converter-level
issues, not walker/viewer bugs, and both gate the §9 *playable-slice* bar, not
the walker checkpoint. Fix them before the next slice boot gate.

## What Checkpoint 2 certifies (grill target-2 session, 2026-07-02)

Certified, on the 8-map batch, by eye:

1. Warps-only pipeline (`phase5 --maps <ids>`) → clean link → bootable ROM
   (the toolchain, end to end)
2. Per-map synthetic-tileset packing is correct (real art renders, 0% void,
   budget guards hold)
3. Quantized art quality is acceptable under raw display (no DNS tint/weather)
4. Warp graph **data**: pairing, dest resolution, back-stack
5. Map constants / registry / name-override / walker-menu header generation
6. Walker UX itself (cursor, HUD, R overlay, START list menu)

The full 177-map corpus is certified **build+link only**; its art was walked
as a small random sample (follow-up open — sampled walk of ~15–20 risk maps:
MtTamaranch 43% void, dup-name cave floors, budget-edge maps).

**NOT certified** (walker structurally cannot see these): collision
(walker returns `COLLISION_NONE` everywhere in bounds), metatile behaviors
beyond the warp door (grass/ledges/water/counters — corpus has exactly
`MB_NORMAL` + `MB_NON_ANIMATED_DOOR`), NPCs/object events (suppressed and not
emitted), scripts (empty `scripts.inc` corpus-wide), warp **triggering** (the
walker calls `DoWarp` directly, bypassing the step-on
`IsWarpMetatileBehavior` path), player occlusion by top-layer art (no player
sprite), day/night tint + weather over the quantized palettes (forced off),
seamless map connections (finding 4), wild-encounter wiring, and stock-map
reachability in a product build (finding 5).

Dispositions agreed in the grill session: collision → slice gate for slice
maps + a later walker collision-respect toggle for corpus spot-walks; metatile
behaviors → slice-gate prerequisite, own unit after the warp fixes (reuses
fix 1's behavior-override mint), terrain_tag→`MB_*` mapping table becomes a
source-of-truth file; NPCs → viewer overlay + slice gate, no walker feature;
occlusion + tint → slice gate (tint escalation path = quantizer, not engine).

## 1. Warp cells lose their real art (doors → grass, indoor stairs → black void)

**Symptom:** every warp tile renders wrong — outdoor doors show the grass
under them, the 1F→2F stairs cell is a black void.

**Cause (designed-in shortcut, not a rendering bug):**
`layout.convert_layout` stamps every warp-override cell with a single generic
per-tileset warp metatile (`tile_map.warp(tileset_id)`), discarding the cell's
actual collapsed column. The substitution exists because a pokeemerald
warp_event is inert unless the metatile under it carries a warp
metatile-behavior (`MB_NON_ANIMATED_DOOR`) — but only the *behavior* +
collision 0 are required; replacing the visual too was the v1 shortcut.

**Fix direction:** keep the cell's real collapsed column (the same
`collapse_column` result every non-warp cell gets) and override only the
metatile **behavior** (+ collision 0). That means minting a per-cell metatile
variant — the column's graphics with `MB_NON_ANIMATED_DOOR` attrs — instead of
one canned metatile per tileset. Touches `layout.convert_layout` (the
`overrides` branch), `tile_map` (behavior-override lookup or mint), and the
graphics emit path (the variant needs a metatile id within the 1024 budget;
note the emitted attrs are keyed per metatile, so a column used both as a door
and as plain floor needs two metatile ids).

## 2. Warps land on the return-warp tile, not Uranium's arrival coords

**Symptom:** following a warp lands the cursor on the destination map's
*return* warp tile (the door/stairs itself), not where Uranium puts the player
(the tile in front of / beside it). Harmless for the walker; wrong for
playability (player would arrive standing "in" the door, and without door
metatile behaviors could immediately re-trigger or get stuck).

**Cause (structural):** pokeemerald warps land on the coords of the
destination warp event selected by `dest_warp_id`, and
`metadata_wiring._return_warp_index` pairs each warp to the destination's
return warp. Uranium's true arrival coords are already parsed and threaded
through as `WarpSpec.dest_x/dest_y` — currently marked "informational" and
dropped.

**Fix direction (cheap — data already present):** the vanilla trick — for each
incoming warp, emit an extra "arrival" warp event in the destination map at
Uranium's real `dest_x/dest_y` and point the source's `dest_warp_id` at it.
Touches `metadata_wiring.build_warp_events` / `build_warps_only_maps` (two-pass:
collect arrival warps per destination, then resolve indices). The arrival warp's
own `dest_map` can point back at the source (it sits on a walkable tile, and
warp_events only fire on warp-behavior metatiles, so a plain-floor arrival tile
stays inert — verify that holds once fix #1 lands). This supersedes the deferred
`gUraniumWarpDests` side-table idea (§4.7): no custom C needed.

## 3. Warp-class refinement (deferred 2026-07-02, grill target-2 session)

All warps get one behavior — step-on `MB_NON_ANIMATED_DOOR` — regardless of
class. Real game distinguishes: animated doors (buildings), non-animated
(stairs/holes), arrow warps / connections (map-edge route exits, e.g.
32↔33 Moki Town↔Route 01). Wrong class → wrong feel (no walk-off at edges, no
door animation) or possible no-fire. Also note: the walker's A-button calls
`DoWarp` directly, so Checkpoint 2 certified warp *data* only — the real
step-on trigger path (`IsWarpMetatileBehavior` in field_control) has never
fired. Certify triggering at the slice gate; classify warp types
(door/stairs/edge) in the converter as a later refinement. Accepted as-is for
slice v1.

## 4. Seamless map connections unconverted (recon 2026-07-02)

Uranium ships `Data/connections.dat` (Marshal): **14 seamless edge connections**,
all route↔town seams, shape `[map_a, edge, offset, map_b, edge, offset]`:

```
[32,E,26, 59,W,0]   Moki Town ↔ Route 03      ← slice frontier (slice 2+)
[142,S,52, 76,N,0]  Route 05 ↔ Route 04
[142,E,0,  87,W,7]  Route 05 ↔ Route 12
[12,W,0,   22,E,0]  Rochfale Town ↔ Route 06
[134,S,0,  133,N,36] Silverport Town ↔ Route 15
[136,S,0,  135,N,14] Snowbank Gym ↔ Snowbank Town
[35,N,0,   40,S,15]  Route 02 ↔ Nowtoch City
[31,N,11,  35,S,0]   Kevlar Town ↔ Route 02
[117,N,0,  28,S,1]   Route 08 ↔ Route 08 (plant)
[8,W,8,    117,E,0]  Route 07 ↔ Route 08
[8,N,53,   101,S,0]  Route 07 ↔ Bealbeach City
[144,E,20, 99,W,0]   Venesi City ↔ Route 14
[146,W,0,  99,E,36]  Tsukinami Village ↔ Route 14
[145,S,63, 144,N,0]  Route 13 ↔ Venesi City
```

The converter emits `connections: null` for every map, so these 22 maps join
only via the START menu today. Slice 1 (49/48/32) is unaffected; 32↔33
(Route 01) is warp-based. **Defer until the frontier reaches a connection seam
(first: Moki Town east → Route 03).** Conversion maps 1:1 onto pokeemerald's
native `connections` map.json field, BUT per-map synth tileset packing breaks
the seamless render: the engine draws the neighbor's edge strip with the
*current* VRAM tilesets, so fully-disjoint per-map tilesets show garbage at
the seam until crossing reloads ("tileset bleed"). Options when this lands:
shared primary tileset per connected pair, border-block masking, or accepting
the bleed for a debug pass. Dump script: scratchpad recon; re-derive with
`_marshal.dump_dat(URANIUM_SRC/Data/connections.dat, out)`.

## 5. Stock-layout stubbing is walker-build-only (formalized 2026-07-02)

`phase5._stub_stock_layout_bins` (default-on) repoints all 785 stock Emerald
layouts to a dummy. Safe **only** under the walker (stock events suppressed,
nothing warps to Hoenn). A product ROM can reach stock layouts via engine
paths (intro/Birch, PC, battle transitions, C specials) → void map. Rule:
stubbing stays a walker-build feature; if `phase5` ever unifies into the
product build path, the default flips to opt-in, and the real stock-content
removal goes through the Emerald-subtraction plan (critique target #3) with a
linker-map ledger.

## Sequencing

Both fixes are converter work on `layout.py` / `tile_map.py` /
`metadata_wiring.py`; do them as their own unit on a fresh branch after the
Phase B merge, re-run `phase5 --maps 49,48,32,33,50,64,65,172`, rebuild, and
re-walk the batch (doors show real art; A lands beside the door, not on it).
