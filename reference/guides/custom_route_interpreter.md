# Custom-Route Movement Interpreter — contract (SoT for C + Python)

**Status:** BUILD IN PROGRESS 2026-07-15. This doc is the single source of truth
for the bytecode contract shared by the engine C interpreter and the Python
emitter. Both sides cite it; neither invents encoding.

## Why

RMXP autonomous `move_type == 3` (Custom) routes are arbitrary looping command
lists (census: 834 corpus-wide, 62% not natively expressible; classes
MULTI_LEG_LOOP + COMPLEX). Native `MOVEMENT_TYPE_*` can't reproduce deterministic
pacing, variable-leg loops, or through-toggle patrols (see
`reference/findings/` recon + SLICE1_TODO #12). This adds ONE new engine
movement type that plays a per-object route bytecode faithfully, replacing the
native-approximation path (WANDER/WALK_SEQUENCE/demote) for the routes it covers.

## v1 scope boundary (bounded, fail-loud)

**Covered** (encoded → played): cardinal steps (RMXP 1-4), turn-in-place
(16-19), wait (15), through on/off (37/38). Per-route idle pacing from
`move_frequency`.

**Dropped from the stream but route still plays** (no movement meaning):
graphic-change (41), opacity (42), blend (43), SE (44), switch (27/28), speed
(29) [v1: ignored — eye-tune later], freq-change mid-route (30).

**Demoted — whole route falls back to the existing native/static path** (Python
`_spec_for_custom_route`), logged loud, NOT encoded: diagonals (5-8), move-random
(9), toward/away-player (10-11), forward/backward (12-13), jump (14), relative/
random turns (20-26). These need engine primitives v1 doesn't wire.

## Data channel (engine)

- **Route id** → `ObjectEventTemplate.trainerRange_berryTreeId` (u16 template →
  u8 runtime, offset 0x1D). Fed from map.json `trainer_sight_or_berry_tree_id`.
  0 = no route (never a valid route id; route table is 1-indexed). Precedent:
  `MOVEMENT_TYPE_BERRY_TREE_GROWTH` uses this exact field the same way. FREE for
  our type because `trainerType == TRAINER_TYPE_NONE` (0) gates out every trainer
  reader. DO NOT use `trainerType` (globally scanned) or `range.rangeX/Y`
  (unconditional collision box) — both are landmines per the engine probe.
- **Runtime scratch** → `sprite->data[]`. **CRITICAL / learned the hard way:**
  the normal-walk movement action (`SetSpriteDataForNormalStep` → `NpcTakeStep`)
  reuses `data[3]`=sDirection, `data[4]`=sSpeed, `data[5]`=sTimer as its OWN
  per-frame scratch during a step, and `SetMovementDelay`/`WaitForMovementDelay`
  own `data[3]`/`data[7]`. So the ONLY sprite-data slot safe across BOTH a walk
  and a wait is **`data[6]`**. The FSM therefore packs **program counter (low
  byte) + through flag (bit 8) into `data[6]`**, uses `data[1]` = FSM sub-state
  (movement-type state, untouched by actions), `data[7]` = the delay timer (via
  the delay helpers, only live in WAIT), and **re-reads the per-route idle from
  `route[0]`** (no stored slot). Do NOT put persistent FSM state in `data[4]` or
  `data[5]` — the walk clobbers them after one step (that was the "NPC only steps
  when talked to" bug). `data[0]`=objEventId, `data[2]`=sActionFuncId (used by
  `ObjectEventExecSingleMovementAction`) — leave both alone. Scratch does NOT
  survive despawn; route id in `trainerRange_berryTreeId` is the persistent
  identity, re-read at FSM init (which also calls `ClearObjectEventMovement`).

## Bytecode format

One `const u8` array per DISTINCT route (deduped across the slice). Shape (v2):

```
[ idle, flags, op, op, ..., END ]
  ^byte0 = idle frames between commands (u8, 0-255), from move_frequency:
           idle = (40 - 2*f) * (6 - f)   →  f1=190 f3=102 f5=30 f6=0
  ^byte1 = flags byte. Bit0 (0x01) = RMXP route.skippable. All other bits
           reserved, always emitted 0.
  then an opcode stream (starting at byte 2), terminated by END_LOOP or END_STOP.
```

v1 was `[idle, op, ..., END]` (opcodes starting at byte 1, no flags byte). v2
adds the flags byte at index 1 and shifts the opcode stream to start at byte 2;
this doc and both the C interpreter and Python emitter must agree on v2 or the
route table will be misread.

Opcodes (byte after the flags byte, i.e. byte 2 onward):

| byte | op | arg | meaning |
|---|---|---|---|
| `0x00` | END_LOOP | — | jump PC back to byte 2 (repeat=true routes) |
| `0x0F` | END_STOP | — | halt, hold position (repeat=false routes) |
| `0x01..0x04` | STEP | — | walk one tile: 1=down 2=left 3=right 4=up (RMXP order). Collision-respecting unless through-mode. |
| `0x11..0x14` | FACE | — | turn in place: 1=down 2=left 3=right 4=up |
| `0x20` | WAIT | next byte | idle for `frames` (on top of per-command idle) |
| `0x30` | THROUGH_ON | — | subsequent STEPs ignore collision |
| `0x31` | THROUGH_OFF | — | subsequent STEPs respect collision |

(Table above numbers turn/through ops by their bytecode *opcode* — e.g. FACE is
`0x11..0x14`, THROUGH_ON/OFF are `0x30`/`0x31` — not by the RMXP move-route
*command code* those opcodes were derived from. Don't conflate the two: RMXP's
own command codes for turn-in-place are 16-19 and for through on/off are 37/38
(see "v1 scope boundary" above, which does cite RMXP command codes on purpose,
since it's describing RMXP route features, not wire format). Byte values in
this table and in the enum in `event_object_movement.c` are the only wire
format; treat any other number as an RMXP command code, not an opcode.)

### Blocked-step semantics (STEP opcodes only)

A STEP opcode is only ever blocked by inline collision (not through-mode). What
happens next depends on the route's `skippable` flag (byte 1, bit 0):

- **`skippable = false`** (RMXP default; 1036 of 1065 corpus routes): the PC is
  **not** advanced. The same STEP opcode is retried every cycle (after the
  normal per-step idle) until the obstruction clears. This matches RMXP: a
  non-skippable blocked move stalls at the same route index forever and keeps
  retrying — it never silently skips ahead or desyncs the interpreter's
  position from the sprite's actual tile.
- **`skippable = true`** (29 corpus routes): the PC **is** advanced past the
  blocked STEP, same as a normal idle tick, and the route continues from the
  next opcode. Nothing at that tile is walked.

**Divergence from RMXP (intentional, requested):** in real RMXP a blocked
character shows no walk animation at all — it's never `moving?`, so it never
animates, full stop. This interpreter instead plays a walk-in-place animation
(`GetWalkInPlaceNormalMovementAction`) while blocked and non-skippable, and
still turns to face the blocked direction (`SetObjectEventDirection`) even
though it doesn't move. This mirrors pokeemerald's own native idiom for the
same situation — see `MovementType_WalkBackAndForth_Step2` and
`MoveNextDirectionInSequence` in `event_object_movement.c`, both of which turn
unconditionally and substitute a walk-in-place action on collision while
leaving their sequence index untouched. We prefer matching the engine's own
behavior over exactly replicating RMXP's "no animation" freeze; it reads better
and is a deliberate divergence, not a bug.

The prior bug this replaces: PC used to advance *before* the collision check,
so a blocked step silently consumed an opcode without moving — desyncing the
interpreter's assumed position from the sprite's real tile (visible in-game as
a patrolling NPC that, once body-blocked by the player, resumes walking a
different square than the one it started on). Collision must always be
checked before the PC is committed.

Route ids are assigned by the **route registry** (build-time, lead-owned): dedup
identical byte arrays across all slice objects → 1-based id → both (a) each
object's `trainer_sight_or_berry_tree_id` in map.json and (b) the gen.h index
table `sUraniumRoutes[]`. Single assignment, two consumers — must agree.

## Engine interpreter FSM (`MovementType_UraniumCustomRoute`)

Hand-rolled wrapper (precedent: `MovementType_BerryTreeGrowth`, not the
`movement_type_def` macro — step count is bytecode-length-dependent). Calls
`UpdateObjectEventCurrentMovement(&gObjectEvents[sprite->sObjEventId], sprite, fn)`.

**Actual sprite-data layout (as shipped — this replaces an earlier draft that
described `data[4]`=PC / `data[5]`=through / `data[6]`=cached idle; that layout
was never shipped and does not match the code):**

- `data[1]` (`sTypeFuncId`) = FSM sub-state (see below).
- `data[6]` (`sRoutePacked`) packs **both** the PC and the through flag: low
  byte = PC (`URANIUM_ROUTE_PC`/`URANIUM_ROUTE_SET_PC`), bit 8 = through-mode
  (`URANIUM_ROUTE_THROUGH`/`URANIUM_ROUTE_SET_THROUGH`). This is the *only*
  sprite-data slot safe across both a walk and a wait — the normal-walk
  movement action clobbers `data[3]`/`data[4]`/`data[5]` every frame as its own
  scratch, and the delay helpers own `data[3]`/`data[7]`.
- The per-route idle (`route[0]`) is **not** cached in sprite data at all — it
  is re-read from the route pointer fresh every time `UraniumRoute_BeginIdle`
  is called.
- `skippable` (`route[1]` bit 0) is likewise never copied into sprite data —
  it's immutable per-route data, read directly off `route` via
  `URANIUM_ROUTE_SKIPPABLE(route)` whenever a STEP is blocked.

Sub-states (`sprite->sTypeFuncId`, values `URANIUM_ROUTE_STATE_*`):
- **INIT (0):** `route = sUraniumRoutes[objectEvent->trainerRange_berryTreeId]`;
  `URANIUM_ROUTE_SET_PC(sprite, 2)` (byte 0 = idle, byte 1 = flags, opcodes
  start at byte 2); `URANIUM_ROUTE_SET_THROUGH(sprite, FALSE)`; → FETCH_EXEC.
- **FETCH_EXEC (1):** `pc = URANIUM_ROUTE_PC(sprite)`; `op = route[pc]`:
  - END_LOOP → `URANIUM_ROUTE_SET_PC(sprite, 2)`; re-enter FETCH_EXEC (no time
    cost).
  - END_STOP → return FALSE (idle forever).
  - STEP dir → if `!through` and `GetCollisionInDirection(objEvent, dir) !=
    COLLISION_NONE` (blocked): if `URANIUM_ROUTE_SKIPPABLE(route)`, advance the
    PC and idle (skip past it); else leave the PC untouched, turn to face
    `dir`, and issue a walk-in-place action — see "Blocked-step semantics"
    above. Otherwise (clear): commit `pc + 1` to the PC, issue
    `GetWalkNormalMovementAction(dir)`, set
    `objectEvent->singleMovementActive = TRUE` (REQUIRED — every stock
    movement type sets this after issuing a single movement; without it the
    exec action never advances autonomously and the object only steps when an
    interaction force-ticks it, cf. `MovementType_WalkBackAndForth_Step2`) → EXEC_WALK.
  - FACE dir → `SetObjectEventDirection(objEvent, dir)`; PC += 1; → idle
    (WAIT).
  - WAIT op → `SetMovementDelay(sprite, route[pc+1])`; PC += 2; → WAIT.
  - THROUGH_ON/OFF → `URANIUM_ROUTE_SET_THROUGH(sprite, on)`; PC += 1;
    re-enter FETCH_EXEC (no time cost).
- **EXEC_WALK (2):** if `ObjectEventExecSingleMovementAction(objEvent, sprite)`
  done → `objectEvent->singleMovementActive = FALSE` (pairs with the TRUE set
  in FETCH_EXEC); `UraniumRoute_BeginIdle(sprite, route[0])` → WAIT. This path
  is shared by both a real step and a blocked walk-in-place; since the
  blocked/non-skippable branch never advanced the PC, completing a
  walk-in-place naturally re-fetches the *same* STEP opcode on the next
  FETCH_EXEC and retries it.
- **WAIT (3):** if `WaitForMovementDelay(sprite)` → FETCH_EXEC.

Direction mapping: RMXP 1/2/3/4 → `DIR_SOUTH/WEST/EAST/NORTH`.

## Engine registration (sentinel fences — `engine_extension_surface.md` §3, KEEP)

- `include/constants/event_object_movement.h`: `#define
  MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE 0x53`; bump `NUM_MOVEMENT_TYPES` → `0x54`.
- `src/event_object_movement.c`: entries in `sMovementTypeCallbacks[]` and
  `gInitialMovementTypeFacingDirections[]` (= `DIR_SOUTH`); OMIT
  `sMovementTypeHasRange[]` (defaults FALSE — no range box). The callback + FSM.
  Gen-hook `#include` for the route table above the callback.
- Gotchas (`engine_extension_surface.md` §4): `-Woverride-init`+`-Werror` (never
  re-designate an index); route pointer array must be `const`; gen header must
  exist before `make` (ship an empty stub for zero-route clones).

## Gen-hook: `src/data/object_events/uranium_move_routes.gen.h`

Modeled on `sprite_emit.py`. Holds `const u8 sUraniumRoute_N[]` bytecode arrays
+ `const u8 *const sUraniumRoutes[]` 1-indexed index table (`[0] = NULL`).
Gitignored; empty-but-valid stub when zero routes so a fresh clone compiles.

## Pipeline data path (in-process, NO sidecar)

Autonomous move-routes are processed on the **metadata side** (`npc_gfx` already
reads `page["move_route"]`), not by the transpiler — so no cross-process sidecar
is needed (unlike traits, whose producer is the transpiler). Path, all inside
`build_slice_maps`:

1. NEW `route_bytecode.py`: `encode_route(route, move_frequency) -> list[int] |
   None` — fresh small decoder, RMXP codes → the opcodes above (returns `None`
   for the demote cases in the scope boundary). Independent of `transpiler.py`'s
   `route_tokens` (that stays for cmd-209 script movement, which emits poryscript
   strings, not bytecode) — it only shares the RMXP-code semantics.
2. `npc_gfx._spec_for_custom_route`: new branch before the demote fallback —
   `encode_route` succeeds → `MovementSpec(movement_type=
   MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE, route_bytecode=...)`.
3. `metadata_wiring.build_object_events`: collect each object's `route_bytecode`
   into a **route registry** (dedup identical byte arrays → 1-based id); set
   `ObjectEvent.route_id`; `to_dict` emits it as `trainer_sight_or_berry_tree_id`.
4. `route_table_emit.py` (new, modeled on `sprite_emit.py`): the registry → the
   gen.h. Same assemble pass as sprite_emit; empty stub when zero routes.

The registry is the shared seam: one id assignment, two consumers (map.json
`trainer_sight_or_berry_tree_id` + gen.h `sUraniumRoutes[]`). Lead-owned.
