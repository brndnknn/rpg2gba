# Proposal — implement RMXP "retain facing" in the engine, delete tier 3

**Written:** 2026-09-17, against `625c8cc9` on `rederive-ch01-ch04`.
**Status:** **DECIDED 2026-09-18 (operator), in a wider form than proposed — read §0 first.** §0 is
authoritative; §§1–7 below are the original proposal, kept for its reasoning and measurements.
Where they disagree, §0 wins. Lands as step **C5b** of `REDERIVATION_PLAN.md` §16.3.
**Origin:** operator, 2026-09-17, while auditing `reference/warp_facing_overrides.json`.
**Scope:** the 449 of 1085 RMXP transfers (41.4%) whose `dir` parameter is 0.

---

## 0. Decisions — 2026-09-18 (operator, grill session)

The proposal asked only for retain-facing (dir 0). The session widened it: **RMXP's transfer
direction lives on the departure side, so carry it there, and delete the arrival-facing table
entirely** — not shrink it by 41%.

**Root cause, stated once.** Stock pokeemerald warps carry no direction. The engine therefore
infers post-warp facing from the *arrival tile's* metatile behavior (`GetAdjustedInitialDirection`,
`overworld.c:1078-1105`), and the pipeline compensated by keying facing on arrival coordinates
(`ON_WARP_INTO_MAP_TABLE`). Every defect class in this area — tier-3 ambiguity, wall-facers from
derivation, coordinate clashes, door tiles forcing south — descends from that missing field.

| # | Ruling |
|---|---|
| **R1** | **Engine retains facing, behind `RPG2GBA_WARP_RETAIN_FACING` in `include/config/rpg2gba.h`, default ON.** Fallback at `overworld.c:1103-1104` returns `playerStruct->direction`. `ScrCmd_warp` (`scrcmd.c:969-981`) calls `StoreInitialPlayerAvatarState()` instead of `ResetInitialPlayerAvatarState()`. **Only `ScrCmd_warp` changes** — the transpiler and `deterministic.py` emit only `warp(...)`; the other seven `ScrCmd_warp*` sites are stock flows we never call (answers original Q2). Fly / Teleport / Dig-Escape Rope / white-out each call `ResetInitialPlayerAvatarState()` themselves (`overworld.c:420/431/443/478`) and keep DIR_SOUTH. |
| **R2** | **Direction on the departure warp.** `struct WarpEvent` (`include/global.fieldmap.h:165`) gains a direction byte, 0 = retain, else `DIR_*`; size 8 → 10 with alignment, guarded by `STATIC_ASSERT(sizeof(struct WarpEvent) == 10)`. `warp_def` (`asm/macros/map.inc:63`) emits the byte and an explicit pad byte; `tools/mapjson/mapjson.cpp:287-292` reads an optional per-warp `"facing"` field, default 0. The step-on/door warp paths in `field_control_avatar.c` override the stored facing with a non-zero field after `StoreInitialPlayerAvatarState()`. ROM cost < 10 KB; no RAM (warp tables stay in ROM, read by pointer); **no save-format change** (not in the save block — seed blobs still load). Pipeline: `metadata_wiring` writes `"facing"` from RMXP `dest_dir` on the departure warp. **Deleted:** `compute_arrival_facings`, `_on_warp_block`/the ON_WARP_INTO_MAP_TABLE facing block, all three tiers, `_derive_retain_facing`, `reference/warp_facing_overrides.json`. |
| **R3** | **Explicit-direction script warps use a pending-facing special.** `setvar(VAR_0x8004, DIR_*)` → `special(SetWarpArrivalFacing)` → `warp(...)`. `ScrCmd_warp` stores facing, then applies and clears the pending value if set; the pending value is also cleared on map load so a branch that never warps cannot leak it. Invisible, like RMXP (which applies the direction while the screen is dark); `turnobject` before `warp` was rejected because the turn shows before the fade. The transpiler starts reading `params[4]` — **today it drops it** (`transpiler.py:2092-2100`), so every explicit-direction script warp currently arrives facing south. |
| **R4** | **Uranium-authored wall-facers are reproduced faithfully** (maps 49/172, `dir=4` into a wall). `test_uranium_authored_wall_facers_are_pinned` stays, reworded from "pending a fidelity call" to "decided: faithful". |
| **R5** | **Under the switch, the warp's direction wins on door tiles.** The `IsNonAnimDoor`/`IsDoor` branch of `GetAdjustedInitialDirection` returns the stored direction instead of `DIR_SOUTH`. The pipeline stamps `MB_NON_ANIMATED_DOOR` on *every* warp source tile as a trigger mechanism (S9), so "door → face south" is a stock-game guess firing on tiles that are not doors. **The arrival auto-step (`Task_ExitNonAnimDoor`, `field_screen_effect.c:393-414`) is kept** — it is what subsumed Uranium's own door walk-out autoruns — and now follows the warp's direction. Arrow, stair, ladder and surf/dive branches are untouched (they drive mechanics). **Guard test:** every dir-0 arrival on a door tile must step onto walkable ground for every direction its source warp can be entered from, and no arrival may land on an arrow/stair tile; both fail loud. |
| **R6** | **Lands as C5b on `rederive-ch01-ch04`, before C6**, unit-green; first ROM run at P11. Playtest facing expectations (`ch03.py::_expected_arrival_facing`, which reads `compute_arrival_facings`) are re-sourced from RMXP `dest_dir` in the same step. |

**Measurements behind the rulings (2026-09-18, all 199 decoded maps):**

- **Coordinate clashes (why R2 over "retain + keep the table for explicit dirs").** 777 step-on
  `WarpSpec`s land on 591 in-bounds tiles; **4 tiles** receive both a dir-0 and an explicit-dir
  transfer — map 71 (18,73), 117 (45,70), 213 (26,20), 216 (21,38), all out of slice. 0 tiles
  receive two different explicit directions. Departure-side direction makes the clash impossible.
- **Script warps in CH01–CH05: 8 `warp()` calls / 7 event-pages** (6 in CH01, 1 in CH03; none in
  CH02/CH04/CH05). 3 explicit-direction — map032/ev078/p1 (up), map049/ev021/p1 2nd warp (right,
  same-map), map172/ev004/p3 (left, same-map) — none walked by a playtest. The 3 walked ones
  (CH01 B4, B10; CH03 B2) are all dir 0.
- **Door-tile arrivals on the 18 built maps: 15 tiles, 20 transfers**, all `MB_NON_ANIMATED_DOOR`
  (no arrow/stair/animated-door arrivals). 15 dir-0 — building exits onto their own front door,
  plus Passage Cave 2F→1F (36)(17,4) and Route 1→Moki (32)(8,43). 5 explicit, **3 disagreeing with
  the forced south**: Moki (32)(8,43..45) → Route 1 (33)(70,11), `dir=4`. Today the table's
  `turnobject` runs before the auto-step and masks this; with the table gone, R5 is what keeps it.
  Stair-tile arrivals beyond the built maps are unverified — stair behavior overrides are computed
  by the assembler, not persisted — and are covered by R5's guard test as maps get built.

**Out of scope:** variable-target transfers (`method=1`, map 212, PROJECT_TODO #113) and
collapsed doors whose pages disagree on direction/destination (#112) — both latent, both
independent of this design.

---

## 1. The ask, in one paragraph

RMXP direction 0 means "retain the player's current facing." pokeemerald cannot express it, so
the pipeline *reconstructs* it at conversion time from map geometry
(`metadata_wiring._derive_retain_facing`, "tier 3"). That reconstruction is ambiguous for 74 of
347 in-bounds cases and needs hand overrides. **Implement retain-facing in the engine instead,
and the reconstruction becomes unnecessary for all 449 dir-0 transfers.**

## 2. Why every arrival currently faces south

`GetAdjustedInitialDirection` (`engine/src/overworld.c:1077-1105`) picks the post-warp facing from
the **metatile behavior of the arrival tile**, and ends:

```c
    else if (MetatileBehavior_IsLadder(metatileBehavior) == TRUE)
        return playerStruct->direction;   // 1101-1102
    else
        return DIR_SOUTH;                 // 1103-1104
```

Two branches already retain facing — ladder, and the underwater/surfing transition. Everything
else falls through to an unconditional `DIR_SOUTH`.

The pipeline deliberately leaves arrival tiles as **plain floor**, because the `MB_*_ARROW_WARP`
behaviors that would give a facing natively are also live step-triggers. Plain floor matches no
branch, so *every* arrival in this ROM hits the `DIR_SOUTH` default. That is the sole reason the
tier system exists.

## 3. The change

**(a) The fallback** — `engine/src/overworld.c:1103-1104`:

```c
    else
        return playerStruct->direction;   // was: return DIR_SOUTH
```

Structurally identical to the ladder branch two lines above. `ResetInitialPlayerAvatarState()`
(`overworld.c:1009-1013`) still sets `DIR_SOUTH`, so a cold boot / new game keeps the safe default.

**(b) The script-warp path — this is the part that is easy to miss.** Facing is captured by
`StoreInitialPlayerAvatarState()` (`overworld.c:1015-1028`, reads `GetPlayerFacingDirection()`),
and that is called **only** from `field_control_avatar.c`'s warp-event paths (step-on, door,
arrow, escalator — 5 sites). The script path does the *opposite*: every `ScrCmd_warp*` calls
`ResetInitialPlayerAvatarState()` immediately after `DoWarp()`, explicitly forcing `DIR_SOUTH`:

```c
bool8 ScrCmd_warp(struct ScriptContext *ctx)          // scrcmd.c:969
{
    ...
    SetWarpDestination(mapGroup, mapNum, warpId, x, y);
    DoWarp();
    ResetInitialPlayerAvatarState();                   // scrcmd.c:981
```

Eight such sites exist in `scrcmd.c` (981, 997, 1013, 1032, 1049, 1065, 3002, 3063). **Change (a)
alone does nothing for script warps** — the reset clobbers the stored direction before the map
load reads it.

This matters because a large share of Uranium's transfers are script warps by design: 172 of the
636 explicit-direction transfers, plus every *gated door* — events whose player-touch pages don't
all transfer, like Map049's "say goodbye to Auntie first." `classify_event` deliberately keeps
those as multi-page objects so the refusal pages survive
(`reference/findings/gated_door_collapse_2026-07-26.md`).

So (b) is: on the script-warp path, capture the facing instead of resetting it — for the warps
that should retain it. Which raises the one real design question in §6.

**(c) Python side, once (a)+(b) land:** delete `_derive_retain_facing` (tier 3) and everything
downstream of it — `reference/warp_facing_overrides.json`, the 74 ambiguous cases, and
PROJECT_TODO #107's proposed second-order rule. `compute_arrival_facings` keeps **tier 1 and
tier 2 only**: an explicit RMXP `dir` of 2/4/6/8 is an authored fact and still needs carrying via
`ON_WARP_INTO_MAP_TABLE`.

## 4. What it buys

Measured over all 199 decoded maps, 2026-09-17:

| | count |
|---|---|
| code-201 transfers, total | 1085 |
| **dir = 0 (this proposal's scope)** | **449 (41.4%)** |
| tier-3-eligible with an in-bounds arrival | 347 |
| — resolved uniquely by tier 3 today | 273 |
| — **ambiguous, needing a hand override** | **74** |
| hand overrides currently in the file | 3 |

- 449 `ON_WARP_INTO_MAP_TABLE` entries no longer needed.
- Tier 3 and its 74 ambiguities deleted rather than mitigated.
- `warp_facing_overrides.json` deleted rather than grown. Only 3 entries exist today because most
  ambiguous specs share a destination key with a clean sibling; later chapters widen the slice and
  that luck does not hold.
- Semantics become *exactly* RMXP direction 0 rather than a static reconstruction of a runtime fact.

It also removes a whole class of latent defect: tier 3 currently derives a facing that points
**into a wall** for four same-map warps on map 216 (arrivals at (21,38), (24,38), (29,38) — north
blocked, south open). `tests/test_warp_facing_invariant.py` would catch it, but it runs over the
slice and map 216 is out-of-slice. Retain-facing cannot produce a wall-facer.

## 5. What it explicitly does NOT do

It does not touch the 636 explicit-direction transfers. A separate idea — realizing those as
native `MB_*_ARROW_WARP` behaviors instead of the table — was measured the same day and is **not
recommended**; see `investigations/warp_arrival_facing_examples.md` for why, in short:

- Only 256 of 464 warp_event-realized explicit transfers are geometrically safe to stamp; 192
  would create a walk-into trap.
- 172 more are script/autorun/action-button transfers where a metatile behavior cannot apply.
- Arrow-warp stamping on arrival tiles was already tried, shipped, boot-tested, broken and
  reverted on 2026-07-16, and carries an explicit "do not re-apply" marker in PROJECT_TODO.
- Metatile budget is 1024 per synthetic tileset pair (`graphics/emit.py:545`); ts1033 is at
  1022/1024.

So the table survives regardless, for at least 364 transfers. This proposal shrinks it by 41%, it
does not remove it.

## 6. Open questions

**All answered 2026-09-18 — see §0.** Q1 → R2/R5 (the "brief wrong facing" was never visible: the
table's `turnobject` runs in `InitObjectEventsLocal` before fade-in; the real Q1 was coordinate
clashes and door tiles). Q2 → R1 (only `ScrCmd_warp`). Q3 → R1 (yes, default on). Q4 → yes:
`InitPlayerAvatar` applies the facing before the `URANIUM_MAP_WALKER` block
(`overworld.c:2604-2615`), so the design works in the walker build.

**Q1 — How does the engine know a warp should retain facing?** The fallback in (a) is reached by
*any* arrival with no behavior match, which under our plain-floor arrivals is all of them —
including the 636 that have an authored direction. Today those are corrected after the fact by
`ON_WARP_INTO_MAP_TABLE`'s `turnobject`, so the fallback value is overwritten a frame later and
does not matter. Is that good enough (simple, but the player is briefly facing the wrong way on an
authored-direction warp), or should the warp carry a retain/explicit bit so the fallback only
applies where RMXP asked for it? The stashed `struct WarpEvent.arrivalDirection` work from
2026-07-16 is the precedent for the second option — **note it never landed; `arrivalDirection` and
`RPG2GBA_WARP_ARRIVAL_DIRECTION` do not exist in `engine/` today (verified 2026-09-17).**

**Q2 — Which `ScrCmd_warp*` sites change?** All eight, or only plain `warp`/`warpsilent`? Several
(`3002`, `3063`) are special flows worth reading before touching.

**Q3 — Gate it behind `include/config/rpg2gba.h`?** The header already carries this repo's engine
knobs. A `RPG2GBA_WARP_RETAIN_FACING` define would make the change revertible and self-documenting,
consistent with `RPG2GBA_FAST_TEXT_DEFAULT` and friends.

**Q4 — Does it interact with the map-walker build?** `TryRunOnWarpIntoMapScript()` is compiled out
under `URANIUM_MAP_WALKER` (`overworld.c:2608-2615`), which is why the 2026-08-18 facing fix could
not be exercised there. A fallback-based approach needs no map script, so it may in fact work in
the walker build where the table does not — worth confirming, since it would make this cheaper to
verify.

## 7. Verification

Not ROM-verified by the build agent — CLAUDE.md §9 and the standing rule that chapter walks wait
for the P11 gate. Proposed evidence:

1. `tests/test_warp_facing_invariant.py` still passes, with its tier-3 assertions replaced by the
   new semantics rather than deleted.
2. A unit test that tier 3 is gone and `compute_arrival_facings` emits no entry for a dir-0 warp.
3. Full `pytest`.
4. On the next chapter walk: enter a dir-0 warp from two different approach directions and confirm
   the arrival facing differs and matches the approach. The map33 → map32 (8,43) corridor is the
   natural case — it is the reason `warp_facing_overrides.json` exists.
