# Warp arrival facing — worked examples

**Written:** 2026-09-17, against `625c8cc9`. Measured over all 199 decoded maps in
`output/uranium-build/maps/` using the real `classify_event` / `column_blocked`, not
reimplemented passability.

**Why this exists:** the operator asked whether pokeemerald's native `MB_*_ARROW_WARP`
behaviors could replace the generated `ON_WARP_INTO_MAP_TABLE` machinery. The answer is
"for some warps, and the boundary is geometric." These are the worked examples behind the
counts in `WARP_RETAIN_FACING_PROPOSAL.md` §5.

In every ASCII map below: `.` walkable, `#` blocked, `A`/`X` the tile under discussion.

---

## 1. The census

Of 1085 RMXP code-201 transfers:

| bucket | count | share |
|---|---|---|
| `dir = 0` (retain facing) | 449 | 41.4% |
| explicit dir, warp_event, **SAFE** to stamp | 256 | 23.6% |
| explicit dir, warp_event, **UNSAFE-OPEN** | 192 | 17.7% |
| explicit dir, **script-realized** | 172 | 15.9% |
| undetermined (map 97 tile-id defect) | 16 | 1.5% |

Of the 256 SAFE, 108 are also reciprocal-and-tile-identical — the cleanest possible shape.

---

## 2. How native arrow warps work

Verified in `engine/src/field_control_avatar.c` and `overworld.c`:

- `IsArrowWarpMetatileBehavior(behavior, direction)` — a NORTH-arrow tile triggers a warp when
  the player walks **north** off it.
- `GetAdjustedInitialDirection` — landing on a NORTH-arrow tile sets facing **south**.

Arrival facing is always the *opposite* of the trigger direction. So to produce a desired facing
`F` you stamp the arrow whose trigger is `opposite(F)` — and that tile becomes a live trigger for
anyone walking `opposite(F)` across it, arriving player or not.

**That last clause is the whole problem.** The hazard is through-traffic, not the arriving player.

---

## 3. SAFE — the shape that fits natively

`map7 ev5 (46,25) -> map142 (88,10) dir=2`, and its exact reciprocal
`map142 ev33 (88,10) -> map7 (46,25) dir=2`.

```
map142 around (88,10)          map7 around (46,25)
   8 ###############           23 ###############
   9 #######.#######           24 #######.#######
  10 #######X#######           25 #######X#######
  11 ..###....######           26 ######....#####
  12 ..###....######           27 ####......#####
```

Both tiles are blocked east and west. North is open for exactly **one** tile and then blocked — a
dead-end alcove, i.e. the cave-mouth graphic. South opens into the real map.

Desired facing is south (`dir=2`), so the trigger would be north — into the alcove. The only
reason to walk north there is to take the warp, which is exactly what a cave mouth means. No
through-traffic can cross the tile northward, because there is nowhere north to go.

This is the same invariant `seam_warps.py` relies on today (its docstring: "an arriving player is
moving in a direction that does NOT match the tile they land on").

---

## 4. UNSAFE-OPEN — same mechanism, opposite outcome (192 cases)

The arrival tile sits in ordinary walkable space, so the trigger direction is a direction people
genuinely walk.

**A corridor.** `map83 ev25 (66,21) -> map83 (12,45) dir=2`; trigger would be NORTH.

```
  42 #####...#####
  43 #####...#####
  44 ...##...##...
  45 ...##.A.##...     <- arrival, mid-corridor
  46 ...##...##...
  47 ...##...##...
```

Arrive facing south. A north-arrow stamp fires when anyone walks north up this corridor — which
is just walking up the corridor.

**An open field.** `map71 ev45 (62,69) -> map71 (18,73) dir=8`; trigger would be SOUTH.

```
  72 .............
  73 ......A......     <- arrival, open ground on all sides
  74 .............
```

**A room interior.** `map183 ev20 (26,22) -> map92 (9,12) dir=8`; trigger SOUTH.

```
  11 ###.......##.
  12 #.....A......
  13 #............
```

**Another, same shape.** `map183 ev21 (28,38) -> map93 (9,12) dir=8`; trigger SOUTH.

**And one more.** `map45 ev10 (5,12) -> map44 (14,5) dir=6`; trigger WEST.

```
   4 #.###..#####
   5 ###...A.####
   6 .......#####
```

This is not hypothetical. It is the documented 2026-07-16 revert: Map089 (4,3) was stamped
`MB_WEST_ARROW_WARP`, then **intercepted a player walking toward the down-stairs** —
`TryArrowWarp` fired one tile early, landing them on Map172's staircase tile, whose non-anim-door
exit walked them south, surfacing as "drops one tile below." See `reference/memory-archive.md`
and PROJECT_TODO's "HISTORICAL (do not re-apply)" marker.

---

## 5. Script-realized — arrow warps cannot apply at all (172 cases)

These are not step-on doors. pokeemerald `warp_event`s are step-on only, so a metatile behavior
has nothing to attach to.

```
map45  ev3  (10,7)  -> map6   (10,8)  dir=2   first page trigger = action button
map11  ev2  (10,7)  -> map6   (10,8)  dir=2   first page trigger = action button
map83  ev13 (12,31) -> map143 (30,39) dir=2   first page trigger = action button
map156 ev1  (25,1)  -> map156 (31,3)  dir=4   first page trigger = action button
map197 ev3  (31,18) -> map199 (8,13)  dir=8   first page trigger = autorun
map122 ev16 (16,34) -> map8   (79,13) dir=4   first page trigger = autorun
```

Three sub-shapes:

1. **Action-button transfers** — the player walks up and presses A. Nothing steps on anything.
2. **Autorun transfers** — a cutscene moves the player. No deliberate tile step at all.
3. **Gated doors** — touch pages that don't *all* transfer, e.g. Map049's "say goodbye to Auntie
   first." `classify_event` keeps these as multi-page objects on purpose so the refusal pages are
   not discarded (`reference/findings/gated_door_collapse_2026-07-26.md`). Filtered out of the
   sample above; they are the same story.

---

## 6. Conclusion

The table cannot be eliminated. Even granting every SAFE stamp, **364 transfers (192 UNSAFE-OPEN
+ 172 script-realized) still need `ON_WARP_INTO_MAP_TABLE`.**

Arrow-warp stamping would shrink it by 256 entries in exchange for metatile budget that does not
exist (1024 cap per synthetic tileset pair, `graphics/emit.py:545`; ts1033 is at 1022/1024) and a
mechanism already reverted once for a boot-verified defect. Not recommended.

The `dir = 0` half is a different story and is proposed separately — see
`WARP_RETAIN_FACING_PROPOSAL.md`.
