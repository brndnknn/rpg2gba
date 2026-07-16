# Fix: RMXP blocked-move semantics (NPC movement, Moki Town boot-walk)

## Context

Three NPC bugs reported from the Moki Town boot-walk:

1. **West-exit woman** stands still facing **down**; should face **west** (toward the exit).
2. **Town-square Pokémon (Chyinmunk)** walks a square patrol loop. When the player blocks it, it
   changes direction and starts a *different* square in a different place. Walking far enough away
   (despawn) and returning resets it. Should instead **walk in place** against the obstruction and
   resume the same loop.
3. **"Birbie" girl** should stand still looking at the hedges; she currently **moves**.

All three are **one root cause**: the pipeline does not model RMXP's blocked-move semantics.

### The verified RMXP contract

From Uranium's real source, `reference/scripts_dump/021_Game_Character_v17.rb` (Essentials v17;
verified no later script overrides NPC behavior — `180_Pathfinder.rb` reopens `move_type_custom` but
is gated behind `$game_map.recalculate_paths`, default `false`):

- `move_down/left/right/up(turn_enabled=true)` (lines 440-482) **turn first, then check `passable?`**.
  If blocked: the character has *already turned*, does not move, and only `check_event_trigger_touch`
  runs. It stays turned.
- `move_type_custom` (lines 325-432) advances the index only on
  `if @move_route.skippable or moving? or jumping?` (line 363). With `skippable == false` (the RMXP
  default, `005_RGSS2Compatibility.rb:483-493`) a blocked move **stalls at the same index forever**
  and retries.
- `turnGeneric` (lines 670-679) is wrapped in `unless @direction_fix` — an event with
  `direction_fix == true` does **not** turn on a blocked move; it keeps its authored
  `graphic.direction`.
- A blocked character is never `moving?`, so it never enters `update_move` and **never animates**.

**The authoring idiom this creates:** RMXP authors routinely give a decorative NPC a move route and
let scenery box it in. The net effect on PC is a statue facing the direction of its first blocked
command. This is used across the corpus, so fixing it generalizes well beyond Moki Town.

### Root cause per bug (all confirmed against real data, `output/uranium-build/maps/Map032.json`)

| NPC | Source facts | Now | Should be |
|---|---|---|---|
| **EV012** (31,44) HGSS_017 | `graphic.direction=2`, `direction_fix=false`, route `[2,2,2,3,3,3,0]`, `skippable=false`. Spawn tile has layer-1 decoration tile **413, passage `0x0F`** (sealed 4 ways) | `MOVEMENT_TYPE_FACE_DOWN` | `MOVEMENT_TYPE_FACE_LEFT` |
| **EV073** (32,49) HGSS_005 | `graphic.direction=6`, `direction_fix=false`, route `[2,4,4,1,1,3,0]`, `skippable=false`. First move is `move_left` onto (31,49) = hedge tiles **1119/1094, passage `0x0F`** | `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` (route id 3) — she walks | `MOVEMENT_TYPE_FACE_LEFT`, static, no route id |
| **EV008** (35,44) Chyinmunk | route `[1×5,3×6,4×6,2,2,37,2,2,38,2,2,1,0]`, `skippable=false`. Genuinely mobile (blocked legs wrapped in through_on/off) | Loop reshapes on player collision | Walk in place, resume same loop |

- **EV012** — the demotion gate *correctly* fires (spawn tile sealed), but `static_face_spec`
  (`npc_gfx.py:682-688`) takes its facing from `_face_from_graphic(page)` = `graphic.direction`.
  Per RMXP she executes `move_left`, turns west, is blocked, stalls facing **west**.
- **EV073** — her spawn tile is *open*, so `exit_blocked(32,49)` is False and the gate
  (`metadata_wiring.py:831-847`) passes her through as a live route. The gate only ever checks
  `exit_blocked(spawn)` for CUSTOM_ROUTE and never simulates the route's cells — see its own comment
  at `metadata_wiring.py:841-842` ("PARTIAL blocking is left alone"). The hedge collision itself
  converted **correctly**; this is a gate-coverage gap, not a collision bug.
- **EV008** — a runtime C bug at `engine/src/event_object_movement.c:6234-6242`:
  `URANIUM_ROUTE_SET_PC(sprite, pc + 1)` runs **before** the `GetCollisionInDirection` check, so a
  player-blocked step burns an opcode without moving. The bytecode's assumed position desyncs from
  the real one, reshaping the polygon. Despawn resets it because PC (`sprite->data[6]`, transient
  sprite scratch) and position both reload from the immutable ROM template.

### Corpus measurements (all `output/uranium-build/maps/Map*.json`, page-level `move_type == 3`)

**1065 routes total.**

- `skippable`: **False=1036, True=29**. Skip-on-block is a real minority. `encode_route`
  (`route_bytecode.py:111`) documents `skippable` in its docstring at line 115 but **never reads it**.
  The v1 bytecode `[idle, ops…, END]` has no bit for it (`route[0]` is the idle header, 0-255, no
  spare bits; the C interpreter starts PC at 1).
- `direction_fix`: **False=670, True=395 (37%)**. These 395 must **not** be re-faced by a blocked
  move. A naive "face the first route command" fix would break 37% of the corpus.
- Most common first opcode is **41 (`change_graphic`, 409 routes)**, not a movement command — so
  "the first move command" can only come from real simulation, never from `list[0]`.

### User decisions (binding)

- **Demote only if frozen at spawn.** Sim stalls on its first *executed* move without ever having
  moved → static `MOVEMENT_TYPE_FACE_<dir>`, drop the route id. Stalls later (moved ≥1 tile) → keep
  the live route; the fixed runtime interpreter reproduces "walks, then freezes there" exactly.
  Never stalls → keep the route.
- **Chyinmunk walk-in-place on block** — a deliberate divergence from RMXP (which shows no
  animation), matching pokeemerald's own idiom and the user's explicit request.
- **Scope:** fix Python + C, regenerate the whole corpus, report every changed `movement_type`,
  rebuild the ROM, verify Moki Town.

---

## Plan

### 1. New RMXP route simulator (Python)

New module `src/rpg2gba/tileset_converter/route_sim.py` — kept out of `npc_gfx.py`, which is already
large, and it is a distinct concern (RMXP execution semantics vs. movement classification).

```python
@dataclass(frozen=True)
class RouteSim:
    stalled: bool          # hit a permanent, non-skippable block
    moved: bool            # displaced >=1 tile before stalling
    stall_facing: str | None   # "DOWN"|"LEFT"|"RIGHT"|"UP" -- direction turned to when stalled
    stall_pos: tuple[int, int] | None
    steps: int             # commands executed before the verdict

def simulate_route(page: dict, x: int, y: int,
                   passability: MapPassability) -> RouteSim: ...
```

Must faithfully model, reusing the existing tables in `npc_gfx.py` (`_MOVE_CODE_TO_DIR`,
`_DIR_VECTOR`, `_TURN_CODE_TO_DIR`, `_DIRECTION_TO_FACING`):

- **turn-then-check**: on codes 1-4, compute the direction, turn (unless `direction_fix`), *then*
  test collision via `passability.cell_clear(target)`.
- **`direction_fix == true` suppresses the turn** — facing stays `graphic.direction`.
- **`skippable`**: if true, a blocked move advances the index (no stall); if false, it stalls.
- **through toggles** (codes 37/38) and the page's initial `through` bypass collision entirely.
- **`repeat`**, terminator code 0, wait (15), turns (16-19), and no-time-cost ops (41/42) skipped.

**Termination.** A permanent stall is decidable the instant a non-skippable move is blocked, because
scenery collision is static — return immediately. For the non-stalling case, detect the loop with a
visited-state set keyed on `(move_route_index, x, y, facing, through)`; a repeat means it cycles
forever. Also carry a hard step budget that **fails loud** (CLAUDE.md §4.5) rather than defaulting.

### 2. Demotion gate — `metadata_wiring.py` (~809-847)

Replace the `exit_blocked`-only `elif` branch for `MOVEMENT_TYPE_CUSTOM_ROUTE` with a simulator call:

```
spec = movement_spec_for(page)
if passability and spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE:
    sim = simulate_route(page, event["x"], event["y"], passability)
    if sim.stalled and not sim.moved:
        spec = static_face_spec(page, reason, facing=sim.stall_facing)   # drop route id
    # sim.stalled and sim.moved -> keep the route; runtime stalls identically
    # not sim.stalled           -> keep the route
```

`exit_blocked(spawn)` becomes redundant here — a sealed spawn tile is just the case where the sim
stalls at step 0 having never moved. Keep `exit_blocked` on the **WANDER/WALK `path_cells` branch**
as-is: those specs are native pokeemerald movement types with no bytecode, so the simulator's
opcode-level semantics don't apply. Leave that branch alone.

### 3. `static_face_spec` / `_demote` — `npc_gfx.py` (~674-688)

Add an optional explicit facing, preserving the existing `graphic.direction` default so the
*other* caller (`_spec_for_custom_route`'s case-h demotion for unrepresentable routes, which has no
passability data) keeps working unchanged:

```python
def static_face_spec(page: dict, reason: str, facing: str | None = None) -> MovementSpec:
    movement = f"MOVEMENT_TYPE_FACE_{facing}" if facing else _face_from_graphic(page)
    return MovementSpec(movement, demoted=reason)
```

The simulator already applies the `direction_fix` rule, so it returns `stall_facing ==
graphic.direction`'s facing for the 395 direction-fixed events — no special-casing at the call site.

### 4. Bytecode v2 — carry `skippable` (29 routes)

Format `[idle, flags, ops…, END]`; `flags` bit0 = skippable. PC starts at **2**. Chosen over
per-step encoding: `skippable` is a whole-route property in RMXP, so per-step would misrepresent the
model and cost a byte per op.

Files that must change together:
- `route_bytecode.py` — `encode_route` reads `route["skippable"]`, emits the flags byte.
- `route_table_emit.py` — regenerate `uranium_move_routes.gen.h`.
- `engine/src/event_object_movement.c` — PC init `1` → `2`; `route[0]` idle reads unchanged;
  read `route[1]` for the skippable bit.
- `reference/guides/custom_route_interpreter.md` — the bytecode contract doc. **Must** be updated.
- Tests below.

### 5. C interpreter fix — `engine/src/event_object_movement.c:6234-6242`

Corrected STEP branch (collision **before** PC advance):

```c
case URANIUM_ROUTE_OP_STEP_DOWN: case URANIUM_ROUTE_OP_STEP_LEFT:
case URANIUM_ROUTE_OP_STEP_RIGHT: case URANIUM_ROUTE_OP_STEP_UP:
    dir = UraniumRoute_RmxpDirToEngine(op);
    if (!URANIUM_ROUTE_THROUGH(sprite)
        && GetCollisionInDirection(objectEvent, dir) != COLLISION_NONE)
    {
        if (URANIUM_ROUTE_SKIPPABLE(route))          // skippable: advance past it, idle
        {
            URANIUM_ROUTE_SET_PC(sprite, pc + 1);
            return UraniumRoute_BeginIdle(sprite, route[0]);
        }
        SetObjectEventDirection(objectEvent, dir);   // RMXP turns even when blocked
        ObjectEventSetSingleMovement(objectEvent, sprite,
            GetWalkInPlaceNormalMovementAction(dir));
        objectEvent->singleMovementActive = TRUE;
        sprite->sTypeFuncId = URANIUM_ROUTE_STATE_EXEC_WALK;
        return TRUE;                                  // PC NOT advanced -> retries same opcode
    }
    URANIUM_ROUTE_SET_PC(sprite, pc + 1);             // commit only on the success path
    ObjectEventSetSingleMovement(objectEvent, sprite, GetWalkNormalMovementAction(dir));
    objectEvent->singleMovementActive = TRUE;
    sprite->sTypeFuncId = URANIUM_ROUTE_STATE_EXEC_WALK;
    return TRUE;
```

This mirrors vanilla `MoveNextDirectionInSequence` (~5155-5181) and
`MovementType_WalkBackAndForth_Step2` (~5109-5136), which substitute the movement *action* on a
plain collision and never touch the route index.

**Watch:** the `EXEC_WALK` completion path calls `BeginIdle` unconditionally. Since the blocked path
leaves the PC untouched, completion of a walk-in-place naturally re-fetches the same opcode — verify
this holds and that no other branch mutates the PC.

**Per §4.7, grep-verify in the fork before writing:** `GetWalkInPlaceNormalMovementAction`,
`SetObjectEventDirection`, `ObjectEventSetSingleMovement`, `GetCollisionInDirection`,
`COLLISION_NONE`, `gWalkInPlaceNormalMovementActions`.

### 6. Tests (§4.6)

- `tests/test_route_sim.py` (new)
  - `test_blocked_first_move_stalls_facing_that_direction` — EV073's shape: stalls, `moved=False`,
    `stall_facing="LEFT"`.
  - `test_direction_fix_suppresses_turn_on_block` — same route with `direction_fix=True` → facing
    stays `graphic.direction`.
  - `test_skippable_route_does_not_stall` — `skippable=True` + blocked first move → `stalled=False`.
  - `test_through_bypasses_collision` — codes 37/38 around a sealed cell.
  - `test_clean_loop_terminates_via_cycle_detection`.
  - `test_stall_after_moving_reports_moved_true` — the keep-the-route case.
- `tests/test_npc_gfx.py` — `static_face_spec` honors an explicit `facing`; defaults to
  `graphic.direction` when omitted (protects the case-h caller).
- `tests/test_route_bytecode.py` — v2 flags byte; skippable bit round-trips; existing golden vectors
  updated for the shifted opcode offset.
- `tests/test_tileset_converter.py` — **regression tests pinned to Map032**: EV012 →
  `MOVEMENT_TYPE_FACE_LEFT`; EV073 → `MOVEMENT_TYPE_FACE_LEFT` with **no route id**; EV008 → still
  `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` with its route id intact.

### 7. Verification

1. `pytest` green.
2. **Corpus diff report** — snapshot every emitted `movement_type` + route id across all maps before
   and after; print each change with its RMXP reason. This diff *is* the corpus-wide evidence.
   Expect: a population of routed NPCs collapsing to `FACE_*`, and a set of `FACE_*` facings
   correcting to the blocked direction. Sanity-check that the 395 `direction_fix` events are
   **unchanged**.
3. Re-emit route tables; confirm `uranium_move_routes.gen.h` is v2 and re-run the assembler.
4. `make -j$(nproc) modern` in `engine/` — clean build; report the ROM hash.
5. **Boot gate (§9)** — taildrop to the phone (`tailscale file cp <rom> iphone182:`); user walks Moki
   Town: woman faces west, Birbie girl stands still facing the hedges, Chyinmunk walks in place when
   body-blocked and resumes the same square.

### 8. Risks

- **RMXP passability vs GBA collision may disagree.** The simulator reads RMXP `@passages`; the
  runtime reads GBA metatile collision. Now that a blocked step **stalls forever** instead of
  skipping, a disagreement turns a cosmetic desync into a **permanently frozen NPC**. Mitigation:
  add a validation pass that replays each surviving route's cells against the *emitted GBA*
  collision and logs loud where the two oracles disagree. Failure mode is visible and debuggable
  rather than silent, which is the tradeoff §4.5 asks for — but it should be measured, not assumed.
- **Bytecode v2 is a lockstep change.** The encoder, emitter, `.gen.h`, C interpreter, and doc must
  land together; a stale `.gen.h` against a v2 interpreter reads the flags byte as an opcode. Ensure
  the assemble step regenerates rather than reuses.
- **"Demote only if frozen at spawn" leans on the runtime fix** for the stall-after-moving case. If
  the C fix regresses, those NPCs desync rather than freeze. Covered by the EV008 regression test.
