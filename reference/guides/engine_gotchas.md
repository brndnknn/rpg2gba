# Engine Gotchas

Hard-won pokeemerald-expansion engine landmines discovered during slice-1
(Moki Town). Each one cost real debug time once; this doc exists so a future
slice doesn't re-derive the diagnosis. Format per entry: symptom, root cause,
fix, how to avoid re-hitting it.

**Provenance:** extracted from `SLICE1_TODO.md` (slice-1 document, about to be
archived) on 2026-08-04. Every claim below was re-verified against the actual
engine/pipeline source at extraction time — see the specific file:line cited
in each entry.

---

## 1. The `compare` macro's literal-vs-var auto-selection

**Symptom:** the S6 aptitude quiz (Map050) always resolved to the same
starter (Eletux) regardless of the player's answers.

**Root cause:** poryscript/pokeemerald's `compare` asm macro
(`engine/asm/macros/event.inc:259-267`) auto-detects whether its second
argument is a literal or a variable id:

```
.macro compare var:req, arg:req
    .if ((\arg >= VARS_START && \arg <= VARS_END) || (\arg >= SPECIAL_VARS_START && \arg <= SPECIAL_VARS_END))
        compare_var_to_var \var, \arg
    .else
        compare_var_to_value \var, \arg
    .endif
.endm
```

`SPECIAL_VARS_START`/`SPECIAL_VARS_END` are `0x8000`/`0x8015`
(`engine/include/constants/vars.h:294,320`) — the engine's own scratch-var
range (`VAR_0x8000`..`VAR_0x8015`, same file :297ff). The quiz's argmax
sign-test compared against the literal `32768` (`0x8000`). Because `0x8000`
sits inside `[SPECIAL_VARS_START, SPECIAL_VARS_END]`, the macro silently
compiled it as `compare_var_to_var` — i.e. "compare against `VAR_0x8000`" —
instead of "compare against the literal 32768". `VAR_0x8000` happened to be
left holding the previous question's raw answer index by the quiz's own
per-question `switch()`, so the tally-override check almost always failed and
the starter defaulted to Eletux.

**Fix:** use `32767` instead of `32768` for the sign test (same
subtract-and-test-sign semantics, and 32767 falls outside both the temp-var
and special-var ranges). Landed in `hand_conversions/Map050_EV005.pory`,
commit `b3b1b623`.

**How to avoid re-hitting it:** any literal comparison value in the
`0x8000`–`0x8015` range (32768–32789 decimal) is a landmine for `compare` —
it will silently become a var-vs-var comparison against one of the engine's
own special scratch vars, not a literal test. This applies to any hand-tail
script or transpiler emission that does sign/threshold tests with round
hex-ish literals near 0x8000. Prefer literals clearly outside that 22-value
window (e.g. 32767, or values `< 0x8000`), or an explicit `compare_var_to_value`
if a literal genuinely needs to land in that range.

---

## 2. Sprite-data slot collisions in custom movement types

**Symptom (2026-07-15 boot-walk):** no custom-route NPC moved autonomously;
each one advanced exactly one step per player interaction ("moves only when
talked to").

**Root cause:** `MovementType_UraniumCustomRoute_Callback`'s FSM originally
stored its program counter in `sprite->data[4]` and its through-mode flag in
`sprite->data[5]`. But the normal-walk movement action
(`SetSpriteDataForNormalStep` → `NpcTakeStep`) reuses `data[4]`=sSpeed and
`data[5]`=sTimer as its own per-frame scratch during every step. The FSM's
first step (PC=1 from INIT) ran fine, then the walk action clobbered the PC
slot mid-step — only an interaction force-tick (which drives the object
regardless of its own FSM state) advanced it further.

**Fix:** pack PC (low byte) + through-mode (bit 8) into a single slot,
`sprite->data[6]` — verified as the ONLY sprite-data slot safe across both a
walk action and a wait, per `engine/src/event_object_movement.c:6217-6223`
(`URANIUM_ROUTE_SET_PC`/`URANIUM_ROUTE_PC` macros operate on `sRoutePacked` =
`data[6]`). `data[3]`/`data[4]`/`data[5]` are walk-action scratch;
`data[3]`/`data[7]` are owned by `SetMovementDelay`/`WaitForMovementDelay`.
Also added `ClearObjectEventMovement` on FSM INIT and clamped idle to `>= 1`
(a related bug: freq-6 routes emit idle 0, and `WaitForMovementDelay`'s
pre-decrement underflows 0 to a ~65k-frame stall).

**How to avoid re-hitting it:** before adding ANY new custom `MOVEMENT_TYPE_*`
that needs FSM state to survive across a walk step, check which `data[]`
indices the stock movement actions your FSM invokes actually touch
(`SetSpriteDataForNormalStep`/`NpcTakeStep` own 3/4/5; the delay helpers own
3/7). `data[6]` is free precedent (`MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`
already claims it for this exact reason); `data[0]`=objEventId and
`data[2]`=sActionFuncId are owned by `ObjectEventExecSingleMovementAction` —
never touch those either. Full slot map:
`reference/guides/custom_route_interpreter.md` (Data channel / Engine
interpreter FSM sections).

---

## 3. The ON_FRAME latch goes stale when something outside the dispatcher changes a guard input

**Symptom:** after declining the S6 quiz once and being offered a retake, the
retake never started — the autorun dispatcher had gone permanently inert for
the rest of the map visit.

**Root cause:** RMXP autorun (trigger=3) page conditions are re-evaluated
every frame, forever. The transpiler's `<Dir>_OnFrame` dispatcher
(`_render_onframe_script`, `src/rpg2gba/tileset_converter/metadata_wiring.py:825-843`)
only approximates that: it dispatches once per frame until no autorun guard
matches, then latches `setvar(VAR_TEMP_C, 1)` (`_ON_FRAME_GUARD_VAR`,
`metadata_wiring.py:101-104`) to stop per-frame dispatch for the rest of the
visit — a perf optimization RMXP itself doesn't need. That latch goes stale
the instant something OUTSIDE the dispatcher changes a symbol one of the
autorun guards depends on (e.g. an interactive NPC script clears a flag an
autorun page's condition tests, expecting the autorun to reconsider itself
next frame) — with the latch still set to 1, the dispatcher never re-fires
for the rest of the visit.

**Fix:** `metadata_wiring.insert_onframe_rearms` (`metadata_wiring.py:854-`,
called from staging) scans every top-level `script Name { ... }` block
(excluding `movement`/`text`/`mapscripts` blocks and the `_OnFrame`
dispatcher itself) for a line writing one of the map's guard flags/vars
(`setflag`/`clearflag`/`setvar`/`addvar`/`subvar`/`copyvar`), and inserts
`setvar(VAR_TEMP_C, 0)` immediately after — re-arming the latch so the
dispatcher reconsiders next frame. Idempotent (safe to re-run at every
staging pass).

**How to avoid re-hitting it:** any new map whose autorun (ON_FRAME) pages
gate on a flag/var also written by an *interactive* (non-autorun) script on
the same map needs `insert_onframe_rearms` to have actually run over that
script — it already runs generically in staging, so this is a "verify it ran"
check, not a "write it again" task if a future map exhibits the same
symptom (a page that should re-trigger but doesn't, after some other script
changed state).

---

## 4. FlagRegistry never persists switch/var labels across a `load()`

**Symptom:** the temp-switch page-dispatch carve-out
(`build_page_dispatcher`'s `s:tsOn?/tsOff?` resolution) silently failed to
resolve script-switch labels on any pipeline run that loaded persisted
registry state rather than building it fresh.

**Root cause:** `FlagRegistry.to_state()`/`.load()`
(`src/rpg2gba/conversion_agent/flag_registry.py:415-`) persist flag/var
**mints** and script-switch **ids**, but never the Uranium switch/variable
**labels** (`reference/uranium_switches.json` / `uranium_variables.json`
content) — those were only ever populated by `pre_seed`, which a `load()`-based
run never calls. Any code path doing `label_for_switch`/`label_for_var` after
a `load()` silently got `None` back for every lookup — no exception, just
wrong-looking output.

**Fix:** `seed_labels()` (`flag_registry.py:359-379`) was split out of
`pre_seed` specifically so it can be called standalone after `load()`.
`transpile_driver.py:290-302` now calls
`FlagRegistry.load(...)` (or constructs fresh) then unconditionally
`registry.seed_labels(...)` right after, regardless of which path was taken.

**How to avoid re-hitting it:** any new call site that does
`FlagRegistry.load(path)` and later needs `label_for_switch`/`label_for_var`
must call `.seed_labels(switches_json, variables_json)` immediately after
`load()` — `load()` alone is not enough. Grep for `FlagRegistry.load(` before
adding a new caller and confirm a `seed_labels` call follows it.

---

## 5. `givemon` never sets `FLAG_SYS_POKEMON_GET` — a general Essentials→Emerald gap

**Symptom:** after a starter grant, the party count was correct (`checkparty`
etc. worked) but the START menu showed no POKÉMON option / no party — the
game behaved as if the player had no Pokémon at all.

**Root cause:** Emerald's START-menu POKÉMON action gates on
`FLAG_SYS_POKEMON_GET` (`engine/src/start_menu.c:340`,
`FlagGet(FLAG_SYS_POKEMON_GET) == TRUE`) — a flag `givemon`/`ScrCmd_createmon`
never sets itself. Essentials has no equivalent gate (a nonempty party is
just visible), so nothing in the Uranium source ever "sets" this flag — there
is no Essentials event to convert that would emit it. This is a structural
gap between the two engines' start-menu visibility models, not a
conversion bug in the traditional sense.

**Fix:** `src/rpg2gba/conversion_agent/transpiler.py:2608-2631` now emits
`setflag(FLAG_SYS_POKEMON_GET)` immediately after every `givemon(...)` call
on the loud (`pbAddPokemon`-ceremony) grant path. Confirmed still present at
verification time. `FLAG_SYS_POKEMON_GET` is also in the flag registry's
reserved floor (`_RESERVED_FLOOR`, `flag_registry.py:53`) so nothing else can
mint over it.

**How to avoid re-hitting it:** any NEW code path that emits a raw `givemon`
(a hand-tail script, a new transpiler branch, a Phase-7 species/starter
flow) must pair it with `setflag(FLAG_SYS_POKEMON_GET)` unless it is
deliberately silent (`pbAddPokemonSilent`-equivalent — Essentials itself
defines that variant as ceremony-free, so the auto-pairing is deliberately
skipped for those 6 call sites; see `SLICE1_TODO.md` #24 for the
enumeration). If a future hand-authored script calls `givemon` directly
without going through the transpiler's grant path, remember the flag by hand.

---

## 6. Missing `releaseall` after `lockall` freezes every NPC on the map

**Symptom:** during the S6 quiz work, lab NPCs froze permanently (could no
longer be interacted with) after a cutscene-style script ran.

**Root cause:** a script that opens a cutscene with `lockall` (freezing every
object event on the map so the player can't interrupt scripted movement/
dialogue) must close it with `releaseall`. A `lockall` with no matching
`releaseall` (or a `switch` branch that reaches its end without one) leaves
every NPC on the map permanently frozen for the rest of the visit — nothing
in the engine times this out.

**Fix (systemic, not just point):** the deterministic transpiler now pairs
`lockall`/`releaseall` automatically for its own cutscene emission —
`src/rpg2gba/conversion_agent/transpiler.py:3016-3017`:
`body = ["lockall", *body, "releaseall"]`. The original bug that motivated
this was in a **hand-authored tail script** (S6 quiz, `hand_conversions/`),
outside the transpiler's automatic pairing.

**How to avoid re-hitting it:** the deterministic transpiler's own cutscene
emission is safe by construction (verify the pairing survives if that code
is touched). Any HAND-WRITTEN tail-tool script that uses `lockall` must be
checked for a `releaseall` on every exit path, including every `switch`
branch and any early `end` — a branch that reaches `end` without
`releaseall` is exactly the shape that bit S6 (a missing `default` arm on a
`switch` fell through into an unrelated cutscene that itself never released).

---

## 7. `MB_NON_ANIMATED_DOOR` vs `MB_ANIMATED_DOOR` — what each actually gets you

Investigated for slice-1's warp-class refinement (#8); not a bug, but a fact
worth preserving so it isn't re-derived from scratch.

- **`MB_NON_ANIMATED_DOOR`** (`engine/include/constants/metatile_behaviors.h:101`)
  is exactly what vanilla uses for interior floor-to-floor stairs/mats — e.g.
  `LittlerootTown_BrendansHouse_1F`'s upstairs warp sits on a metatile whose
  `metatile_attributes.bin` byte decodes to `MB_NON_ANIMATED_DOOR` (`0x60`).
  A converted map's stairs/mat warps using this behavior are already correct
  — "stairs/mats behave like doors" is a description of vanilla, not a defect
  to fix.
- **`MB_ANIMATED_DOOR`** (`metatile_behaviors.h:110`) is consumed by
  `TryDoorWarp` (`engine/src/field_control_avatar.c:1098`, called from
  `:229`, north-approach only) via `GetDoorGraphics`
  (`engine/src/field_door.c:612`). It requires a matching
  `sDoorAnimGraphicsTable` entry (keyed by metatile+tileset,
  `field_door.c:16-24,331-338,612-620`) — **a table entry is mandatory**:
  `GetDoorGraphics` with no match returns `NULL` and the door animation
  silently no-ops (no crash, no log — just a door that doesn't open).
- Converting an RMXP animated player-touch door (a charset-driven open/close
  cycle, Uranium's actual door idiom) into a native `MB_ANIMATED_DOOR` is
  real engine work — costs a C table edit per door AND the door frames must
  quantize into one of the map's existing BG palettes (they originate as a
  sprite sheet, so this carries real color-collision risk). This was scoped
  and explicitly deferred for slice-1 (user decision, doors render as the
  closed frame baked into the tileset) — see `SLICE1_TODO.md` #8 for the two
  scoped-and-rejected approaches if this is revisited; don't re-derive them
  from scratch.

---

## Extra landmines found in `SLICE1_TODO.md` beyond the requested list

Two more of the same character turned up while paging through the source
document. Both are corpus-general (would re-hit any future slice touching
the same mechanism), so included here even though not on the original list.

### 8. `ObjectEventSetGraphics` repoints art but never copies a tile — frozen sprite under `lockall`

**Symptom (2026-08-01/02, lab starter scene):** a scripted object-graphics
swap (RMXP "change graphic" re-pose of a large prop, converted to
`RPG2GBA_SetObjectEventGfx`) compiled and ran with no error, but the sprite
on screen never visibly changed state.

**Root cause:** `ObjectEventSetGraphics` repoints `sprite->images` but issues
no tile copy of its own — the actual VRAM tile copy comes from the sprite
animation engine's `AnimCmd_frame`/`ContinueAnim`. Every swap in this scene
ran inside a `lockall`, and `FreezeObjectEvents` sets `animPaused` on every
non-player object event sprite — so `ContinueAnim` never reached the next
frame command, and the tiles stayed stale (showing whatever was last drawn)
until the object respawned.

**Fix:** the custom special that performs the swap now re-begins the
sprite's anim (`BeginAnim`, which is NOT gated on `animPaused`) after
repointing graphics, mirroring what `SpawnObjectEventOnMap` already does for
a freshly spawned sprite.

**How to avoid re-hitting it:** any custom C that changes an object event's
graphics/pose WHILE the map is `lockall`ed (i.e. `animPaused` is set on that
sprite) must explicitly re-arm the sprite's animation (`BeginAnim`) — a bare
`ObjectEventSetGraphics`/pointer repoint is not enough, and the failure is
silent (no error, sprite just looks frozen).

### 9. A script-carried object id inside a `special`'s `setvar` argument is invisible to `local_id_remap`

**Symptom (2026-08-01, same lab scene):** four scripted graphics-state swaps
were no-ops — the prop never animated — while `applymovement` calls on the
very same object, in the very same script, worked fine.

**Root cause:** `local_id_remap` rewrites RMXP event ids into compiled
object-local ids, but only for a fixed set of command shapes
(`REMAP_COMMANDS`: `applymovement`/`setobjectxy`/`addobject`/`removeobject`/
`turnobject`). The graphics-swap special carried its target object id as the
argument to `setvar(VAR_0x8004, <id>)` feeding a `callnative`/`special` —
a shape `local_id_remap` never scanned. The compiled script asked
`TryGetObjectEventIdByLocalIdAndMap` for the RMXP-numbered id (19) on a map
whose `object_events` array only had 4 entries (the prop was local id 3) —
lookup failed, function returned, swap silently no-op'd. No compile error,
no runtime error, nothing.

**Fix:** `local_id_remap` gained a second reference-shape scanner
(`iter_object_id_refs`, shared with `stage_slice_scripts._scan_required_actor_ids`
so a swap-only target still gets spawned in the first place), and a
`RPG2GBA_SetObjectEventGfx` call it can't pair with a target is now a hard
build-time error.

**How to avoid re-hitting it:** any NEW special/custom command whose
arguments carry an object id via `setvar` (rather than as a direct script
argument to a `REMAP_COMMANDS`-listed command) needs its own entry in
`iter_object_id_refs`, or the id will silently stay RMXP-numbered and
mismatch the compiled map's local ids — with zero compile/runtime signal.
Treat "does this command carry an object id, and if so in what shape" as a
mandatory question for every new transpiler emission that touches object
events.
