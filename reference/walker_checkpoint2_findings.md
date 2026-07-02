# Walker Checkpoint 2 sign-off — deferred findings (2026-07-02)

User boot-walked the 8-map batch ROM (49, 48, 32, 33, 50, 64, 65, 172) and the
map-viewer perf pass. **Everything functional passed** — boot, cursor, warp
follow (A) + back-stack (B), HUD (L), warp-reveal (R), START jump menu, all
warp pairs, viewer speedups. Two fidelity items were marked `[-]` and
**deliberately deferred past the Phase B merge**. They are converter-level
issues, not walker/viewer bugs, and both gate the §9 *playable-slice* bar, not
the walker checkpoint. Fix them before the next slice boot gate.

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

## Sequencing

Both fixes are converter work on `layout.py` / `tile_map.py` /
`metadata_wiring.py`; do them as their own unit on a fresh branch after the
Phase B merge, re-run `phase5 --maps 49,48,32,33,50,64,65,172`, rebuild, and
re-walk the batch (doors show real art; A lands beside the door, not on it).
