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

One `const u8` array per DISTINCT route (deduped across the slice). Shape:

```
[ idle, op, op, ..., END ]
  ^byte0 = idle frames between commands (u8, 0-255), from move_frequency:
           idle = (40 - 2*f) * (6 - f)   →  f1=190 f3=102 f5=30 f6=0
  then an opcode stream, terminated by END_LOOP or END_STOP.
```

Opcodes (byte after the idle header):

| byte | op | arg | meaning |
|---|---|---|---|
| `0x00` | END_LOOP | — | jump PC back to byte 1 (repeat=true routes) |
| `0x0F` | END_STOP | — | halt, hold position (repeat=false routes) |
| `0x01..0x04` | STEP | — | walk one tile: 1=down 2=left 3=right 4=up (RMXP order). Collision-respecting unless through-mode. |
| `0x11..0x14` | FACE | — | turn in place: 1=down 2=left 3=right 4=up |
| `0x20` | WAIT | next byte | idle for `frames` (on top of per-command idle) |
| `0x30` | THROUGH_ON | — | subsequent STEPs ignore collision |
| `0x31` | THROUGH_OFF | — | subsequent STEPs respect collision |

Route ids are assigned by the **route registry** (build-time, lead-owned): dedup
identical byte arrays across all slice objects → 1-based id → both (a) each
object's `trainer_sight_or_berry_tree_id` in map.json and (b) the gen.h index
table `sUraniumRoutes[]`. Single assignment, two consumers — must agree.

## Engine interpreter FSM (`MovementType_UraniumCustomRoute`)

Hand-rolled wrapper (precedent: `MovementType_BerryTreeGrowth`, not the
`movement_type_def` macro — step count is bytecode-length-dependent). Calls
`UpdateObjectEventCurrentMovement(&gObjectEvents[sprite->sObjEventId], sprite, fn)`.

Sub-states (`data[1]`):
- **0 init:** route = `sUraniumRoutes[objectEvent->trainerRange_berryTreeId]`;
  `data[4]=1` (PC past idle header); `data[5]=0`; `data[6]=route[0]`; → state 1.
- **1 fetch/exec:** `op = route[data[4]]`:
  - END_LOOP → `data[4]=1`; re-enter state 1.
  - END_STOP → return FALSE (idle forever).
  - STEP dir → if `!through` and `GetCollisionInDirection(objEvent,dir) != COLLISION_NONE`: skip (advance PC, go to wait). Else `ObjectEventSetSingleMovement(objEvent, sprite, GetWalkNormalMovementAction(dir))`; **`objEvent->singleMovementActive = TRUE`** (REQUIRED — every stock movement type sets this after issuing a single movement; without it the exec action never advances autonomously and the object only steps when an interaction force-ticks it, cf. `MovementType_WalkBackAndForth_Step2`); `data[4]++`; → state 2.
  - FACE dir → `SetObjectEventDirection(objEvent, dir)`; `data[4]++`; → wait (state 3).
  - WAIT → `SetMovementDelay(sprite, route[data[4]+1])`; `data[4]+=2`; → state 3.
  - THROUGH_ON/OFF → set `data[5]`; `data[4]++`; re-enter state 1 (no time cost).
- **2 exec-walk:** if `ObjectEventExecSingleMovementAction(objEvent, sprite)` done → `objEvent->singleMovementActive = FALSE` (pair with the TRUE set in state 1); `SetMovementDelay(sprite, data[6])`; → state 3.
- **3 wait:** if `WaitForMovementDelay(sprite)` → state 1.

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
