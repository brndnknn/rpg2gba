# Native-Reuse Audit — everything we emit or hand-wrote vs what pokeemerald-expansion already ships

**Date:** 2026-07-07
**Scope:** every place rpg2gba creates C code, C data, or scripts that run on the engine — the
sentinel-fenced engine divergences, the Python-emitted `.gen.h`/asset artifacts, and every script
construct the transpiler/classifiers/hand-overrides emit.
**Method:** three parallel research passes (engine C, generated artifacts, emitted scripts), each
required to cite fork evidence for *both* directions (our code + the native candidate). The
load-bearing negative claims ("no native equivalent exists") and the one critical finding were
re-verified directly by the lead session against `engine/` source.
**Verdict taxonomy:**
- **REUSES-NATIVE** — we call/instantiate the engine's own mechanism; nothing invented.
- **JUSTIFIED-CUSTOM** — no native analog exists; the searches that prove it are cited.
- **POSSIBLE-REINVENTION** — a native analog exists with real overlap; gaps are listed so you can
  judge whether to switch.

---

## TL;DR — ranked findings

The reinvention worry is mostly unfounded: the overwhelming majority of emitted scripts route
through existing std scripts/macros, and the generated C data uses the engine's own struct
formats and extension points. But the audit surfaced **one critical correctness bug** (worse than
reinvention) and a handful of genuine improvement targets:

| # | Severity | Finding |
|---|---|---|
| F1 | **CRITICAL** | Flag/self-switch registry bases **write out of bounds of `flags[]` into `vars[]`** (save-block corruption), and minted `VAR_*` bases **collide with live vanilla vars** (Battle Frontier/Scott/roamer). Verified by lead. §F1 below. |
| F2 | MEDIUM | Temp-switch flags 0x20–0x32 leak past the temp-clear range (become silently persistent) and shadow vanilla `FLAG_UNUSED_0x020+`; also, rock-respawn flags (`FLAG_TEMP_11..1F`) and temp-switch mints (base 0x14+) **share the same range** — any map with >3 smashable rocks collides. §F2. |
| F3 | MEDIUM | YES/NO choice emission is a two-step (`msgbox` + bare `yesnobox(0,0)`) instead of the native `msgbox(text, MSGBOX_YESNO)` idiom — behaviorally different (extra forced button press, wrong box position). §A2. |
| F4 | LOW | Sign idiom knowingly skips `MSGBOX_SIGN`'s `FLAG_SAFE_FOLLOWER_MOVEMENT` handling — fine now (no followers in slice), documented so it isn't rediscovered later. §A3. |
| F5 | INFO | Three engine-side near-misses worth knowing about but not switching to: `OW_FLAG_NO_COLLISION` (no bounds clamp), debug menu's warp utility (compiled out of release, needs live player context), `RemoveAllObjectEventsExceptPlayer` (one-shot, doesn't stop scroll-respawn). §C. |

Everything else audited is verified reuse or justified custom with the evidence inline below.

---

## F1 — CRITICAL: registry flag/var address layout is unsafe (verified by lead)

**What we're trying to do:** give every Uranium switch/variable a `FLAG_*`/`VAR_*` id the engine
can store. The registry mints names; `scripts/assemble_pathfinder.py:64-68` assigns the numeric
bases and dumps `engine/data/scripts/uranium_flags.h`:

```python
FLAG_BASE = 0x1000        # named global flags
SELFSWITCH_BASE = 0x1100  # per-event self-switch flags
VAR_BASE = 0x40D0         # "unused game-var range (vanilla VARS_END = 0x40FF)"
TEMPSWITCH_BASE = 0x0014  # temp flags
```

**Why it's broken — three separate problems:**

1. **Flags 0x1000/0x1100 are out-of-bounds writes.** `GetFlagPointer`
   (`engine/src/event_data.c:226`) does `if (id < SPECIAL_FLAGS_START /*0x4000*/) return
   &gSaveBlock1Ptr->flags[id / 8];` — **no check against `FLAGS_COUNT`**. The array is only
   `NUM_FLAG_BYTES` = 300 bytes (`FLAGS_COUNT ≈ 0x960` bits; `engine/include/global.h:1131`,
   offsets `flags` @0x1270, `vars` @0x139C confirm 0x12C = 300). Flag id 0x1000 indexes
   `flags[512]`, id 0x1100 indexes `flags[544]` — both land **inside `vars[]`** (0x139C–0x159C).
   Every `setflag(FLAG_MAP…_SSA)` the slice dispatchers execute today corrupts a bit of some
   vanilla var. It's silent in the slice because nothing reads those vars yet.
   The comment "must not overlap vanilla flags (FLAGS_COUNT ≈ 0x960)" got the constant right and
   the conclusion wrong: `FLAGS_COUNT` is the *allocation bound*, not a floor above which ids are
   free.

2. **`VAR_BASE = 0x40D0` collides with live named vars.** `engine/include/constants/vars.h:230+`:
   0x40D0 = `VAR_HAS_ENTERED_BATTLE_FRONTIER`, 0x40D1 = `VAR_SCOTT_STATE`, 0x40D3 =
   `VAR_DEX_UPGRADE_JOHTO_STARTER_STATE`, 0x40D5 = `VAR_ROAMER_POKEMON`, … Our 11 minted vars
   alias 0x40D0–0x40DA — all actively referenced vanilla state. (Vars are bounds-checked, so no
   memory corruption — "just" state aliasing.) `VARS_END = 0x40FF` is the array's upper bound,
   not a free-space marker; only scattered `VAR_UNUSED_0x40xx` singletons are actually free.

3. See F2 for the temp-switch range.

**Status/known-ness:** `reference/flag_registry_policy.md` already says Phase 7 must grow
`FLAGS_COUNT` before final assignment — but these placeholder bases are **live in the booted
slice ROM right now**, not a someday problem. Fork headers are still pristine (no expansion has
happened).

**Recommended fix (pick one, before the next real assembly):**
- Short-term safe remap, zero engine edits: move `FLAG_BASE`/`SELFSWITCH_BASE` into the genuinely
  unused tail of the *real* flag space (the fork has large `FLAG_UNUSED_0x…` runs below
  `FLAGS_COUNT` — e.g. the 0x4B0–0x4FF and 0x8C0+ regions; pick after a grep for actual script
  references), and move `VAR_BASE` onto verified `VAR_UNUSED_0x40xx` slots — though there are
  fewer free vars than we may eventually need.
- Proper fix (Phase-7 item, but could be pulled forward): grow `FLAGS_COUNT`/`VARS_COUNT` in the
  vendored engine behind a sentinel fence (save-block size must be re-checked against sector
  budget) and put Uranium ranges above the vanilla ones with named `RPG2GBA_*_START` constants.

---

## F2 — MEDIUM: temp-switch range leaks and collides with rock-respawn flags

- 31 temp-switch flags are dumped from base 0x14 → ids 0x14–0x32. The temp-flag range ends at
  `TEMP_FLAGS_END = 0x1F`; `ClearTempFieldEventData` (`engine/src/event_data.c:58`) only clears
  0x00–0x1F on map transition. So mints at 0x20–0x32 **silently stop being temporary** (they
  persist like normal flags) and shadow vanilla `FLAG_UNUSED_0x020+` (in-bounds, unused by
  scripts — no corruption, but semantics drift).
- New collision created by the rock-respawn fix (2026-07-07): smashable rocks are assigned
  `FLAG_TEMP_11..1F` sequentially per map (vanilla obstacle convention,
  `SetHideObstacleFlag`, `event_object_movement.c:1466`). Temp-switch mints start at 0x14. Today
  Map032 uses 0x11–0x13 and nothing overlaps, but **the 4th rock on any map would be 0x14** — the
  same id as the first minted temp-switch. The two allocators don't know about each other.
- Recommended: move `TEMPSWITCH_BASE` out of 0x11–0x1F (or teach the registry that 0x11–0x1F is
  reserved for obstacles), and decide explicitly what "temp switch" should mean for mints that
  don't fit in the 32-bit temp window (they may simply belong in the normal flag range).

---

# Part A — Emitted script constructs (transpiler, classifiers, wiring, hand overrides)

Summary table; details for the non-trivial rows follow.

| # | Construct | What we're reproducing | Verdict |
|---|---|---|---|
| A1 | `giveitem` / `pbReceiveItem` | Essentials item-give w/ fanfare + bag-full | REUSES-NATIVE |
| A2 | YES/NO choice | RMXP Show Choices yes/no | **POSSIBLE-REINVENTION (F3)** |
| A3 | Sign dialogue (`\sign`) | signpost text | POSSIBLE-REINVENTION, knowing (F4) |
| A4 | `{PAUSE}` / `MSGBOX_AUTOCLOSE` text codes | `\wt[n]` `\.` `\|` `\wtnp` | REUSES-NATIVE |
| A5 | Rock smash | `Kernel.pbRockSmash` | REUSES-NATIVE |
| A6 | PC | `pbTrainerPC` | REUSES-NATIVE |
| A7 | Region map | `pbShowMap` | REUSES-NATIVE |
| A8 | Running shoes | `$PokemonGlobal.runningShoes=true` | REUSES-NATIVE |
| A9 | Party heal | RMXP Recover All / code 314 | REUSES-NATIVE |
| A10 | Screen fades (221/222/223) | fade/tone commands | REUSES-NATIVE |
| A11 | Emotes (code 207, anims 17/19) | ! / ? balloon | REUSES-NATIVE |
| A12 | Player transparency (code 208) | hide/show player | REUSES-NATIVE |
| A13 | Move-route tokens | RMXP move routes | REUSES-NATIVE |
| A14 | Door `onEvent?` coordinate check | arrival-position branch | REUSES-NATIVE (vanilla idiom) |
| A15 | Align-loops (112) | wait-until-player-aligned | JUSTIFIED-CUSTOM |
| A16 | Trainer battles | Essentials trainer intro/defeat/post | REUSES-NATIVE |
| A17 | Poké Mart | shop clerk | REUSES-NATIVE |
| A18 | Scripted warps (doormats) | transfer player | REUSES-NATIVE |
| A19 | Temp/self-switch → `setflag` | RMXP switch model | REUSES-NATIVE primitive / JUSTIFIED mapping |
| A20 | CE stubs (strip list) | deliberate feature drop | N/A (stub, not a reproduction) |
| A21 | Page dispatchers | RMXP multi-page events | JUSTIFIED-CUSTOM (confirmed necessary) |
| A22 | Arrival warp events | Uranium warp dest coords | REUSES-NATIVE (vanilla landing trick) |
| A23 | Rock respawn flags | obstacle persistence | REUSES-NATIVE (vanilla convention) — but see F2 |
| A24 | Pokédex ceremony (hand) | starter/dex cutscene | REUSES-NATIVE primitives / JUSTIFIED choreography |
| A25 | Letter scene (hand) | `displayNinjaLetter` card UI | JUSTIFIED-CUSTOM |

### A1 — giveitem (REUSES-NATIVE)
We emit `giveitem(ITEM_X[, qty])` + an `if (var(VAR_RESULT) != 0)` branch
(`transpiler.py:896-926`; ground pickups in `deterministic.py:560-624`). The `giveitem` macro
(`engine/asm/macros/event.inc:2111`) already routes through `Std_ObtainItem`
(`engine/data/scripts/obtain_item.inc`) which does additem, bag-full check, pocket buffer,
fanfare, and sets `VAR_RESULT`. Our branch is exactly the macro's documented contract — we did
NOT re-implement fanfare/bag logic.

### A2 — YES/NO choice (POSSIBLE-REINVENTION → fix, F3)
We emit the prompt as a standalone default-type `msgbox(text)` (which ends in
`waitbuttonpress`), then a bare `yesnobox(0, 0)` + `if (var(VAR_RESULT) == 1)`
(`transpiler.py:982-1000`). The native idiom is `msgbox(text, MSGBOX_YESNO)` →
`Std_MsgboxYesNo` (`engine/data/scripts/std_msgbox.inc:19`): `message / waitmessage /
yesnobox 20, 8` — no intervening button press, and the choice box at the standard (20,8)
position instead of (0,0). Dozens of vanilla examples (e.g.
`engine/data/maps/MossdeepCity/scripts.inc:228`). **Ours is behaviorally different in two
user-visible ways** (extra A-press before the box appears; box drawn top-left). The code comment
already marks the prompt-merge as deferred. Recommended: when a TextRun immediately precedes a
YES/NO choice, collapse to `msgbox(prompt, MSGBOX_YESNO)`.

### A3 — Sign idiom (knowing simplification, F4)
We emit `lock / msgbox(text) / release` explicitly instead of `MSGBOX_SIGN`
(`deterministic.py:344-348`, mirrored in `transpiler.py:733-737`; user-validated against the
frozen classifier outputs). Native `Std_MsgboxSign` (`std_msgbox.inc:11`) additionally wraps the
box in `setflag FLAG_SAFE_FOLLOWER_MOVEMENT` / `clearflag …` and uses `lockall`. Consequence:
if/when follower Pokémon are enabled, our signs can let the follower move mid-box. Not a bug
today (no followers in the slice); recorded here so the difference is a decision, not a surprise.

### A5–A13, A16–A18 (REUSES-NATIVE, spot detail)
- Rock smash: `goto(EventScript_RockSmash)` (`field_move_scripts.inc:64`) — full delegation;
  `VAR_LAST_TALKED` contract holds for object scripts. Both RMXP arms intentionally dropped
  (the native script subsumes them; never returns).
- PC: `goto(EventScript_PC)` (`pc.inc:1`); `goto` (not `call`) is correct — the native script
  ends the thread itself.
- Region map: `special(FieldShowRegionMap)`; `def_special … waitstate=1`
  (`data/specials.inc:274`) auto-injects the waitstate, so we correctly do NOT emit one.
- Fades: `fadescreen(FADE_TO/FROM_BLACK)` — the native primitive for exactly this
  (`event.inc:1393`).
- Emotes: `applymovement(who, Common_Movement_ExclamationMark/QuestionMark)` — ships verbatim in
  `data/scripts/movement.inc:1-9`.
- Player transparency: `set_invisible`/`set_visible` movement tokens
  (`asm/macros/movement.inc:91-92`), used the same way by vanilla maps.
- Move routes: pure token mapping onto the fork's movement vocabulary, including expansion-only
  `walk_diag_*` (fork-verified before use, §4.7).
- Trainer battles: `trainerbattle_single(...)` macro 1:1 (`event.inc:784`).
- Mart: `pokemart` + `mart` block (`event.inc:1271`).
- Warps: `warp/waitstate` standard shape (`event.inc:475+`).

### A14/A15 — coordinate checks and align-loops
`getplayerxy` + literal-coordinate compare is a genuine vanilla idiom (identical shape at
`engine/data/maps/Route111/scripts.inc:65-74`); there is no native "arrival trigger" primitive
because RMXP's page-condition concept has no GBA equivalent. The align-loop (`while` +
`applymovement`/`getplayerxy`, `transpiler.py:1083-1141`) is a composition of native primitives
with no shorter native form (searched `data/scripts/*.inc` — nothing equivalent).

### A21 — Page dispatchers (JUSTIFIED-CUSTOM, confirmed)
`build_page_dispatcher` (`metadata_wiring.py:340-371`) emits per-event
`if (flag(SW)) { goto(PageN) }` chains to emulate RMXP's highest-page-wins model. Confirmed
necessary: `ObjectEventTemplate` has exactly **one** `const u8 *script` field
(`engine/include/global.fieldmap.h:160`) — no native multi-page mechanism; map-level
`MAP_SCRIPT_ON_FRAME_TABLE`/`ON_TRANSITION` hooks are per-map, not per-object, and cannot
substitute.

### A24/A25 — Hand overrides
- Pokédex ceremony (`hand_conversions/Map032_EV009.pory`): the two state-changing steps are
  byte-for-byte the vanilla Birch-lab pattern — `setflag FLAG_SYS_POKEDEX_GET` +
  `special SetUnlockedPokedexFlags` (`LittlerootTown_ProfessorBirchsLab/scripts.inc:546-547`);
  item grant via `giveitem` (A1). The choreography is bespoke by nature. The live NPC
  graphic-swap was correctly deferred (verified: no script-callable live gfx-swap macro exists;
  `VAR_OBJ_GFX_ID_x` resolves at spawn only).
- Letter scene (`hand_conversions/Map049_EV021.pory`): searched for any native letter/mail-card
  display — none (`bufferstring`/`messageautoscroll` are generic primitives; the "Mail" item
  system is unrelated). msgbox chain is the closest primitive; card art logged as a Phase-8
  custom-C candidate rather than silently dropped.

---

# Part B — Generated C data artifacts (Python emitters)

| # | Artifact | Emitter | Verdict |
|---|---|---|---|
| B1 | NPC sprite structs/pics/palettes/pointer entries | `sprite_emit.py` | REUSES-NATIVE (vanilla's own per-sprite static-data pattern) |
| B2 | Player field-move anim table | `sprite_emit.py:601-609` | JUSTIFIED-CUSTOM (verified: no native terminating 1-frame table) |
| B3 | Break-prop rock struct | `sprite_emit.py` | JUSTIFIED-CUSTOM (anim table IS vanilla's; struct differs only in size) |
| B4 | Tileset artifacts (tiles/metatiles/attrs/pals + structs) | `graphics/emit.py`, `build_slice_tilesets.py` | REUSES-NATIVE (byte-identical formats/layout to vanilla tilesets) |
| B5 | map_groups/layouts `.gen.json` | `phase5.py`, `assemble_pathfinder.py` | REUSES-NATIVE (feeds the fork's own generator, doesn't replace it) |
| B6 | Map alias + walker maps headers | `map_constants.py` | JUSTIFIED-CUSTOM (pure glue, no analog) |
| B7 | `uranium_flags.h` registry dump | `flag_registry.py` | **BROKEN — see F1/F2** (mechanism fine, address layout unsafe) |
| B8 | Stub `.gen.h` / empty `scripts.inc` | `sprite_emit.py`, `phase5.py` | N/A (scaffolding for the committed hooks) |

### B1 — NPC graphics data (REUSES-NATIVE)
Every emitted shape matches vanilla's own convention exactly: `ObjectEventGraphicsInfo` structs
(same fields as the ~200 hand-written vanilla ones in `object_event_graphics_info.h`),
`{data, tag}` palette entries matching `sObjectEventSpritePalettes` format
(`event_object_movement.c:490`), pic tables via the same frame macros. Palette tags 0x1134–0x1138
verified free (vanilla stops at 0x1133, resumes 0x1150). There is no runtime-loadable
alternative in the engine that we skipped — `OBJ_EVENT_GFX_VAR_*`/`OBJ_EVENT_GFX_SPECIES()` only
select among *already-compiled* structs.

### B2 — Field-move anim table (JUSTIFIED-CUSTOM, exhaustively verified)
The rock-smash flow waits on `SpriteAnimEnded()` (`fldeff_rocksmash.c`); only `ANIMCMD_END`
satisfies it. Vanilla `sAnimTable_FieldMove` (`object_event_anims.h:1558`) needs 5 distinct
frames we don't have (Uranium has no field-move pose); the only 1-frame native table
(`sAnimTable_Inanimate` → `sAnim_StayStill`) **loops** via `ANIMCMD_JUMP(0)` and would softlock.
Grep for any native `ANIMCMD_FRAME(0,1)`+`ANIMCMD_END` table at index 0: zero hits. Our 4-line
table is the minimum viable artifact.

### B4 — Tilesets (REUSES-NATIVE)
Diffed against vanilla: identical directory layout (`tiles.png`, `metatiles.bin`,
`metatile_attributes.bin`, `palettes/*.pal`), identical `struct Tileset` field layout
(vs `src/data/tilesets/headers.h:33`), same `INCGFX_U32`/`INCGFX_U16`/INCBIN macros. Our gen
fragments are additional *instances* of the vanilla pattern spliced at committed vendor hooks —
no parallel format was invented.

### B5 — map_groups/layouts (REUSES-NATIVE)
`include/constants/map_groups.h` is generated by the fork's own build from
`data/maps/map_groups.json`; our `.gen.json` overlays feed that same generator via the committed
`map_data_rules.mk` wildcard-preference hook. We did not duplicate the generator.

---

# Part C — Engine C divergences (sentinel-fenced)

| # | Unit | Verdict |
|---|---|---|
| C1 | Gen-file include hooks (tilesets, obj-event tables, event_scripts.s, map_data_rules.mk) | JUSTIFIED-CUSTOM — this *is* the decomp's intended extension mechanism, automated |
| C2 | Player sprite pointer repoints (normal + field-move) | JUSTIFIED-CUSTOM — same table vanilla uses for player variants |
| C3 | New-game spawn override (`WarpToTruck`) | JUSTIFIED-CUSTOM — vanilla spawn is hardcoded the same way; no config knob exists |
| C4 | `CB2_StartUraniumSlice` + rock-smash test harness | JUSTIFIED-CUSTOM — near-miss: debug menu's `DebugAction_Give_PokemonComplex`/`CheatStart` do similar *state setup* but are only reachable from a running overworld (R+START, `DEBUG_OVERWORLD_MENU`, `DISABLED_ON_RELEASE`) — nothing native boots straight into a playable state. Harness is a tracked REMOVE obligation. |
| C5 | Copyright/intro skip (`intro.c`) | JUSTIFIED-CUSTOM — verified: no `SKIP_TITLESCREEN`-style config exists in this fork (only unrelated `B_FAST_INTRO_*`) |
| C6 | Truck-cutscene suppression (`overworld.c CB2_NewGame`) | JUSTIFIED-CUSTOM — hardcoded upstream, no toggle; `gFieldCallback` timing constraint documented |
| C7/C10 | Walker: NPC spawn + on-warp-script suppression | JUSTIFIED-CUSTOM with a near-miss: native `RemoveAllObjectEventsExceptPlayer` (`event_object_movement.c:1722`, dead code — zero callers) covers only the one-shot half; it cannot stop `TrySpawnObjectEvents`' continuous scroll-spawn path, which is why the gate exists |
| C8/C9 | Walker: field-input takeover + step-script suppression | JUSTIFIED-CUSTOM — `DEBUG_OVERWORLD_MENU` gate is the only precedent and only intercepts one combo |
| C11 | Walker: bounds-clamp collision | JUSTIFIED-CUSTOM, near-miss worth knowing: native `OW_FLAG_NO_COLLISION` (`config/overworld.h:122`) is a real noclip flag but has **no map-bounds clamp** — walking off-grid would read garbage; our version is that flag plus a clamp (gap was known at design time, `reference/map_walker_plan.md` §4.4) |
| C12 | Walker: raw display (DNS off) | REUSES-NATIVE — just wires the existing `OW_ENABLE_DNS` config under our build flag |
| C13a | Walker: invisible anchor boot | JUSTIFIED composition of native primitives (`SetPlayerInvisibility`, `SetUpFieldTasks`, `UnlockPlayerFieldControls` are all stock calls) |
| C13b | Walker: cursor sprite | JUSTIFIED-CUSTOM — mirrors `region_map.c`'s cursor *pattern*; that code lives in a different renderer and can't be reused |
| C13c | Walker: warp-follow + back-stack | JUSTIFIED-CUSTOM — warp primitives (`SetWarpDestination*`, `DoWarp`) are native; no location-undo concept exists anywhere in the engine |
| C13d | Walker: L-toggle HUD | JUSTIFIED-CUSTOM — no native live coord/metatile overlay exists; window template copied from `debug.c`'s |
| C13e | Walker: R warp-overlay | JUSTIFIED-CUSTOM — nothing native visualizes warp tiles in-field |
| C13f | Walker: START jump-menu | **POSSIBLE-REINVENTION (accepted)** — `debug.c`'s `DebugAction_Util_Warp_Warp` chain already offers warp-to-any-map. Real gaps that justified ours: it's `DISABLED_ON_RELEASE` (compiled out), digit-stepper entry vs a named scrollable list of ~190 unfamiliar maps, assumes live player/party/NPC context (walker needs the opposite), no back-stack integration. The ListMenu wiring itself does re-tread a solved pattern — acknowledged. |

**Note on the walker as a whole:** it is debug tooling, deliberately temporary, and every fence
is revertable. The three near-misses (C7/C10, C11, C13f) are listed for honesty, not as action
items — in each case the native mechanism covers less than half the need.

---

## Action items (proposed, in order)

1. **F1 — fix the registry bases before the next real assembly.** Decide: safe remap into
   verified-unused vanilla ranges now, or pull the Phase-7 `FLAGS_COUNT`/`VARS_COUNT` expansion
   forward (sentinel-fenced engine edit — needs your §10 sign-off + save-sector budget check).
2. **F2 — de-conflict `TEMPSWITCH_BASE` vs the rock-flag range** (0x11–0x1F) and decide the
   semantics for temp-switch mints that don't fit the 32-flag temp window.
3. **F3 — collapse prompt+choice into `msgbox(text, MSGBOX_YESNO)`** in the transpiler's choice
   emission (small, user-visible fidelity win).
4. **F4 — no action**; revisit the sign idiom only if followers are ever enabled.
