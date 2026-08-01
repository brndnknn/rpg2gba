# Slice 1 TODO — Map 49 (Player's House 1F) ↔ 48 (2F) ↔ 32 (Moki Town)

Working checklist for finishing the pathfinder slice to the §9 bar (boots in
mGBA, genuinely playable, warps/NPCs/layout/art all real). Commit updates as
items close; move an item to **Done** with a one-line result rather than
deleting it. Facts here are pointers — the cited code/docs stay authoritative.

## Open

### 24. `pbAddPokemon` is a ceremony, not a bare `givemon` — BUILT 2026-08-01, boot-walk pending

**User ask:** show the Pokémon's sprite when you actually receive it, and make
it general for every later gift.

**It was never ours to invent — we were dropping it.** Essentials'
`pbAddPokemon` (`scripts_dump/170__PSystem_Utilities.rb:1710`) is
*"{player} obtained {species}!"* + `\me[PU-PokemonObtained]` + `pbNicknameAndStore`
(nickname prompt, party or box). We emitted a bare `givemon` +
`FLAG_SYS_POKEMON_GET`, dropping a sprite, a fanfare, a message and a prompt at
**26 call sites across 11 events**.

Every piece has a native host, and vanilla's own gift flow
(`LittlerootTown_ProfessorBirchsLab/scripts.inc:333-372` +
`data/scripts/pc_transfer.inc`) is the same primitives in the same order, so
this is a §4.7 restoration: `bufferspeciesname` → `showmonpic` → `givemon` →
branch on `VAR_RESULT` (`MON_GIVEN_TO_PARTY` / `MON_GIVEN_TO_PC` /
`MON_CANT_GIVE`) → `playfanfare MUS_OBTAIN_ITEM` + `message`/`waitmessage`/
`waitfanfare` → `gText_NicknameThisPokemon` YES/NO →
`Common_EventScript_GetGiftMonPartySlot` + `NameReceivedPartyMon` (or
`NameReceivedBoxMon` + `TransferredToPC`), full party/full box handled by
`Common_EventScript_NoMoreRoomForPokemon`.

**`pbAddPokemonSilent` (6 sites) deliberately keeps the bare `givemon`** — the
silent form is exactly the one Essentials defines as ceremony-free, so the old
conversion was right for it and wrong for the loud one.

**Fork-index gap found doing this:** `STR_VAR_1` is assigned only in
`engine/charmap.txt` — not in any constants header, not in `event.inc` — so the
gate rejected `bufferspeciesname STR_VAR_1, ...`, *which is what vanilla itself
writes*. `charmap.txt` is now scanned (`_extract_charmap_constants`,
`_INDEX_FORMAT` 3→4), restricted to 2+-character ALL_CAPS names so the file's
single-letter assignments can't let a typo'd `A` through.

**Shipped:** `lab-doorstep.gba` sha1 `d39c55d6` (pristine `26408202`). 1544
tests; moki GREEN 17/17 first attempt with the new nickname prompt in the path.

### 25. The lab machine didn't animate — BUILT 2026-08-01, boot-walk pending

Reported twice; the earlier direction-carrying fix was never going to be
enough. **The sheet had exactly one frame in the ROM.** `PU-PokeballMachine` is
a `graphics/sprites.py` `LARGE_PROP_SHEETS` entry, so `sprite_emit` gave it the
fork's 64×64 static-object treatment (`gObjectEventGraphicsInfo_RayquazaStill`
convention): `.anims = sAnimTable_Inanimate`, `.inanimate = TRUE`, and a
one-frame pic table. No script command can show a frame that isn't in the ROM,
so both the pattern selection *and* the direction carry were dead for it.

**A large prop is not a walk cycle — every grid cell is a selectable STATE.**
RMXP re-poses a static prop with a code-41 Change Graphic that names the sheet
it's already wearing and moves only `(direction, pattern)`. The conversion now
treats those as states end to end:

- `graphics/sprites.py` extracts every **non-empty** cell as its own frame,
  recording `ConvertedSprite.states` (index-aligned `(direction, pattern)`),
  all anchored with one shared offset so the prop doesn't hop between states.
  The machine yields 9: directions 2/4/6 × patterns 0/1/2 (row 8 and column 3
  are blank in the art).
- `graphics/sprite_emit.py` emits one `ObjectEventGraphicsInfo` + one
  `OBJ_EVENT_GFX_URANIUM_*` id per state, each over a one-frame pic table
  (`overworld_frame(strip, 8, 8, k)`, `engine/include/sprite.h:35`) indexing
  the sheet's **single** strip PNG and palette. `sAnimTable_Inanimate` only
  ever shows frame 0, so a state has to *be* frame 0 of its own table. The idle
  state (2,0) keeps the bare constant, so every already-placed object_event and
  the existing `"gfx"` entry keep resolving; the rest are suffixed
  `_D<dir>P<pattern>`. `NUM_URANIUM_OBJ_EVENT_GFX` now counts constants (40),
  not sheets (32).
- `reference/npc_gfx_map.json` (§4.3 SoT) gains a `"states"` map, cross-checked
  against the real PNG's non-empty cells on every sprite pass
  (`sprite_pass._check_declared_states`) — declaring a state the art lacks, or
  emitting one the JSON never declared, fails loud.
- The transpiler's code-41 resolves `(sheet, direction, pattern)` → that
  state's constant; the facing block and the pattern-drop queue note are gone
  for state sheets (nothing is dropped), and a state with no cell queues.
  Walk-cycle sheets keep the old facing-carry behaviour unchanged.
- `metadata_wiring.build_object_events` places a multi-state prop in its boot
  page's own authored state, so a page authored mid-sequence (Map050 EV019 p2
  is `(4,2)`) boots showing that, not the idle cell.
- The fork gate (`fork_index.registry_extra_symbols`) accepts the per-state
  constants, same as the sheet's own.

All four Map050 swaps now target distinct states (`Map050.pory` D2P1 / D2P2 /
D6P2 / D4P2). Verified by eye against a fresh-boot replay: the machine is the
idle unit through B6/N3 and a visibly different unit after the quiz.

**Corpus note:** 1115 code-41 uses across 44 maps, 30 sheets used with more
than one `(direction, pattern)`. Only the large-prop subset is converted this
way — ordinary NPC sheets are genuine walk cycles whose frames the fork drives
itself, and their pattern-moving swaps still queue as before.

**Shipped:** `lab-doorstep.gba` sha1 `f64db6ca` (pristine `583a431f`). 1564
tests; moki GREEN 17/17 first attempt.

### 23. Map050 EV005 retired onto the transpiler — BUILT 2026-08-01, boot-walk pending

The last hand conversion in the lab is gone; `hand_conversions/` is down to
Map032_EV009 and Map049_EV021. Queue entries on the event: **14 → 0 on the
quiz page** (the 8 that remain are pages 3/6/7, the Pokédex-reward pages,
which the hand file also left queued — it was verbatim transpiler output
there). Three transpiler features, all corpus-censused first:

1. **RMXP Label (118) / Jump to Label (119)** — the intra-page goto, now a
   basic-block hoist: the labelled region becomes its own `script` and both
   the fall-through and every jump become `goto`. **Corpus reach: 51 labels /
   138 jumps over 23 names.** Scoped to regions that provably TERMINATE
   (run to page end, or end on a same-indent code-115), because a hoisted
   block has no way to fall back into an enclosing branch/choice arm — 31 of
   51 labels qualify; the rest queue. Pages with more than one label also
   queue (the regions nest; chaining them is its own unit). Hoisted blocks
   inherit the trigger's *epilogue* only — which is the general fix for the
   freeze the hand file had to patch by hand (W8 fix A).
2. **Array-valued game variables** — `$game_variables[N]=[0,0,0]`, the
   indexed bump `pbGet(A)[pbGet(B)]+=1`, and the `index(max)` argmax with its
   `if x==1 / x=0` permutation. **Corpus reach: 1 site, this event** — so
   this is deliberately a narrow idiom, not a general array subsystem, and
   `test_aptitude_tally_is_still_one_of_a_kind` pins the count so a second
   site re-opens the design. The emitted argmax is byte-identical to the
   hand version you boot-verified on 2026-07-21, 32767 sign-test included.
3. **`pbStarterSelector(pbGet(N))`** — the player's own reveal, which takes
   the variable directly rather than through Ruby arithmetic (0-based domain,
   vs Theo's 1-based). Shares one emitter with the Theo form now.

**Visible payoff:** your own starter reveal is no longer one line — it's the
mon sprite plus the full 5–6-line personality read, matching Theo's.

**Also fixed, and it corrects something I told you earlier:** RMXP code-41
Change Graphic sets sheet *and* (direction, pattern), and props use those to
pick a STATE. We only ever emitted the sheet, so Map050's pokéball machine
swapping to its own sheet twice was a **visible no-op** — the "machine
visibly changes" claim on 2026-08-01 was wrong. Direction has an exact analog
(the object's facing selects the same row of the converted 4-direction
sheet), so it now emits as facing. `pattern` — the frame within the row — has
none, and a swap that selects one now files a queue entry instead of
pretending. EV005's two machine swaps are direction-2 both times, so that
animation is still a frame-only drop, now loudly recorded.

**Shipped:** `lab-doorstep.gba` sha1 `4eb25ce1` (pristine `9c118fec`),
taildropped 2026-08-01. 1538 tests pass; moki GREEN all 17 beats first
attempt, incl. N3 (the retake path, which is what exercises the new
label/goto hoist).

### 22. Stamped review ROMs were shadowed by save-file residue — FIXED + RETEST PASSED 2026-08-01

**Symptom (user, lab-doorstep ROM `a86e073c`):** the ROM should boot on the lab
doorstep with the Auntie + Theo-cameo prerequisites done. Instead it showed a
spot near the player's-house exit, with **no player sprite and dead input** —
viewport frozen.

**Root cause:** `CB2_StartUraniumSlice` (`engine/src/new_game.c`) tested
`gSaveFileStatus == SAVE_STATUS_OK || UraniumEmbeddedSave_TryLoad()` — *flash
first*. Any leftover `.sav` on the test device therefore won the race and the
stamped blob was never loaded, so the ROM continued an older build's save
whose map/coords no longer line up (hence the missing player object).
Reproduced headlessly: pairing the stamped ROM with a foreign `.sav` booted
into the player's house at (7,7) instead of Moki Town (17,12). The ROM's
*stamped state itself was always correct* — a fresh-flash boot passed, which is
why this was never caught.

**Fix:** swap the order — the blob wins. `TryLoad()` returns FALSE untouched
when `magic == 0`, so a pristine ROM still continues a flash save and a player
keeps in-game saves across launches. Consequence, by design: on a *stamped*
ROM an in-game save is inert; every boot returns to the stamped state.

**Invariant pinned:** `playtest.stamp.verify_stamped_rom` — every
`python -m rpg2gba.playtest.stamp` now re-boots the stamped ROM **with a
deliberately foreign `.sav` paired** and asserts map/pos/field-unlocked. A
fresh-flash boot passes either way, so the foreign save is the whole point.

**Collateral found + fixed:** the fork-index gate had no extras for the
`OBJ_EVENT_GFX_URANIUM_*` constants the sprite pass mints into generated,
gitignored `uranium_*.gen.h` headers, so the transpiler's code-41 live sprite
swap (added 2026-07-31, `d5ae2e3e`) gated as an invented constant and
`transpile_driver run --maps slice` aborted on Map050. **The whole slice was
unbuildable, and the ROM shipped on 2026-07-31 did not contain that commit's
Map050 conversion at all** (`scripts/Map050.pory` on disk was still dated
07-30, and `scripts.inc` had zero `RPG2GBA_SetObjectEventGfx`) — the commit
message's "moki chapter GREEN on transpiler-generated Map050 EV019" was not
backed by the artifacts. Extras now flow from `reference/npc_gfx_map.json`
(the same §4.3 SoT the transpiler resolves sheets through) in both
`transpile_driver` and `assemble_pathfinder`; two tests pin it. With the gate
fixed, the real conversion built and moki went GREEN on all 17 beats.

**Shipped:** `lab-doorstep.gba` sha1 `9596c8b7` (pristine `128f2edd`),
taildropped 2026-08-01. **User boot-walked it the same day: correct spawn, and
the lab scene now carries the real EV019 conversion — "it includes a lot more
than before".** Committed `a4a97e2a`.

### 20. Chapter harness planned routes on the *previous* map's grid — FIXED 2026-07-30, moki GREEN

**Symptom:** moki beat B4 failed deterministically (same frame `f3464` across
four runs) — `walk_to(27,17)`'s BFS reported *no planned route from (28,31)*
on Map032, and the greedy fallback walked the player back through the house
door. **The ROM was never wrong**; nothing was visible in a hand boot-walk.

**Root cause:** a warp writes `SaveBlock1.location` in `ApplyCurrentWarp`
(`engine/src/overworld.c:620`) long before it rebuilds `gBackupMapLayout` in
the `InitMap` call inside `LoadMapFromWarp` (`overworld.c:982`).
`_wait_for_map` polls *location*, so it returned inside that window: measured
at the failing instant, `map_location`=(75,2) MokiTown and `player_pos`=(28,31),
but the grid was still the house's 45×29 (→30×15). The goal (27,17) fell
outside those bounds, so BFS returned `None`, and `_route_waypoints`' documented
"harmless" greedy fallback stepped off (28,31) — which *is* the warp back into
Map049. 30 frames later the grid read 87×78 and BFS found a 410-tile reachable
set. The field lock is no signal either: `CB2_LoadMap` calls
`UnlockPlayerFieldControls` on the way in, so controls read unlocked all
through the window — which is why the 2026-07-27d "wait the lock out first"
experiment changed nothing and was (correctly) reverted.

**Why it regressed:** latent race, tipped by 27d's `RPG2GBA_FADE_DELTA_Y 4`.
The fade speedup moved where the 10-frame poll lands relative to the layout
rebuild. MEMORY.md's note that "fade constants cannot reach the BFS" was wrong
— they reach it through *when* the grid is read, not what it contains.

**Fix (harness only, no converter or engine change):** `Emulator` grew
`_grid_dims_for_current_map` / `map_grid_loaded` / `wait_for_map_grid`, keyed
on `gMapHeader.mapLayout`'s own dimensions plus the border margin
(`fieldmap.c:171-174`); `walk_to` waits for the grid before planning, and
`_map_grid` refuses a grid whose dims disagree with the current map header.
`_plan_route` now *raises* on a goal outside the grid bounds instead of
returning `None` — that shape is a wrong grid, not a planner blind spot, and
degrading it to greedy is exactly what caused the damage.

**Invariant pinned:** nothing asserted the grid belonged to the map the game
reports being on. Five new tests in `tests/test_playtest.py` cover it (dims
match/mismatch, `_map_grid` refusal, the wait's success and timeout, and the
out-of-bounds-goal raise). 1471 tests pass; **moki is GREEN, all 17 beats,
first attempt** on ROM `ec2fb783`.

### 21. Contact-sheet tiles can now be chosen by the beat — DONE 2026-07-30

The sheet's two automatic rules (last completed message, else the live frame
at the beat boundary) can't serve a beat whose interesting moment is neither.
`Emulator.mark_frame()` pins the current frame as that beat's tile: sticky
(later dialogue won't silently override an explicit choice), refuses a
blank/mid-fade frame unless `force=True`, cleared per beat by `waypoint`.
Still one tile per beat, no runner change.

**B6 rewired on the back of it.** It ran *zero* frames — asserting only that
the field was still locked — so it proved nothing B5 hadn't and its tile was
a duplicate of B5's; the Yes/No prompt is only reached later, inside N3's
mash. New observable `Emulator.yesno_prompt_up()` scans `gTasks` exactly as
`FuncIsActiveTask` does, for the handler `ScriptMenu_YesNo` installs
(`script_menu.c:584-596`) — its lifetime *is* the prompt's, so no frame
counting and no dependence on text speed. B6 now mashes Bambo's dialogue
forward, stops the moment the prompt opens, asserts it opened, and pins that
frame. **Its tile now reads "RED, are you ready to take the Trainer Aptitude
Test?" with the YES/NO menu up.**

`Task_HandleYesNoInput` is `static` and so never reaches the link map; new
`symbols.static_fn_via_literal_pool` recovers it from `ScriptMenu_YesNo`'s
literal pool (third sibling of the two existing accessor tricks), keeping the
**Thumb bit** — `gTasks[i].func` stores the odd address, and comparing against
the even one silently never matches. Deliberately not `gSpecialVar_Result ==
0xFF`: multichoice sets that sentinel too, so it can't tell a yes/no prompt
from one of the quiz's `dynmultichoice` questions.

9 new tests; 1480 pass; chapter re-run **GREEN, all 17 beats**. Which option
is *highlighted* is still unobservable — answers are still made by button.

### 18. Gated doors collapse into unconditional warps — CONVERTER FIXED 2026-07-26, ROM re-run pending

Found 2026-07-26 by the chapter harness (Moki beat B2: you could walk out of
Player's House 1F without talking to Auntie). Full write-up:
**`reference/findings/gated_door_collapse_2026-07-26.md`**.

`classify_event` turned any player-touch event containing *any* code-201 into one
unconditional `warp_event` and dropped the object_event, so multi-page doors lost
their refusal pages silently (§4.5 violation). Map049 EV002's gate is Switch 52
`FLAG_MUM`, set by Auntie — the Auntie side converted fine, only the door lost
its gate.

**Fixed:** collapse only when every *player-touch* page transfers (an autorun
page must not gate a door — that distinction spares Moki Town's five house
doors); gated doors emit a `coord_event` on their own cell, no relocation; the
cell is unioned into the returned warp-override set so it keeps door metatile +
collision 0. Verified in staged output: (10,11) → `Map049_EV002_Dispatch` gating
on `FLAG_MUM`, (14,19) → `Map050_EV001_Dispatch` gating on `VAR_QUEST_LOG >= 1`
(**this is beat B10's gate**), neither with a warp_event racing it. 1439 tests
pass.

**DONE 2026-07-27:** rebuilt (stage → assemble → `make modern`) and re-ran the
chapter suite — **B2 passes on ROM `1066eac4`/`90757612`**, the door refuses
until Auntie sets `FLAG_MUM`. Corpus-wide follow-up (341 events / 75 maps
pre-narrowing, not re-measured) stays out of slice-1 scope.

### 19. Per-page RMXP trigger types are ignored — FIXED 2026-07-27, chapter suite GREEN

`classify_event`/`build_object_events` emit one `coord_event` per event and
`build_page_dispatcher` selects by page *condition* only, so a page whose RMXP
trigger differs from its siblings' fires the wrong way. Live case: Map032 EV009
("Trainer(6)", the west-exit ceremony host) has pages 0-2 at trigger 2 (player
touch) and **page 3 at trigger 0 (action button)**; at `VAR_QUEST_LOG >= 4` the
converted page 4 `lock`s and prints on every walk over (16,43)-(16,45), where
Uranium needs an A press on an opacity-0 event — effectively never.

Same family as #18's gated-door fix (that was a per-page trigger distinction
too) and the "base-page own condition ignored" deferral.

**Fixed:** dispatch is now channel-aware (`metadata_wiring`). `CHANNEL_TOUCH`
(a walk-on `coord_event`) dispatches only touch pages (1/2); `CHANNEL_ACTION`
(an event's primary talkable host) keeps today's action + bump→talk
approximation; `CHANNEL_ACTION_ONLY` serves the **new secondary host**: an
event whose host is a `coord_event` but which also has action pages now emits
a `bg_event` sign on its own tile (`Map###_EV###_ActionDispatch`), so the
A-press pages stay reachable exactly as in RMXP without becoming a second way
to fire the walk-on ones. `_goto_or_end` takes the channel and `end`s any page
whose trigger it doesn't serve (the autorun/parallel rule is now a case of the
general one).

Slice 1: 4 new signs on Map032 (EV009/074/078/080) + Map050 EV002; EV009's
walk-on dispatcher now `end`s at `VAR_QUEST_LOG >= 4` instead of printing.
Corpus reach: of 1183 walk-on hosts, **135 events across 50 maps carry 181
action pages** that were firing on the wrong channel. 1444 tests pass;
**chapter suite `moki` is GREEN, all 18 beats, first attempt** (ROM
`d6a54593`; review ROM + contact sheets under `output/playtest/review/`).

### 6. Pokédex-ceremony live sprite swaps (EV76 ball / EV77 starters)

Deferred from task 4: RMXP change-graphic move-route commands on the ceremony
events have no fork-native script-callable gfx swap (`VAR_OBJ_GFX_ID_x`
resolves at spawn only). Recipe if wanted: `setvar` + `removeobject` +
`addobject`. General limitation behind it: page-driven sprite changes aren't
reflected — object gfx is the static boot page's. Judge in-game whether the
ceremony reads acceptably without it.

### 7. Audio — everything is a `# audio` comment

The transpiler comments out all RMXP audio commands; no Uranium BGM/SFX are
converted. Verify what actually plays on the slice maps (likely stock Emerald
defaults from map.json) and decide the slice-1 bar: accept stock audio, silence,
or start a minimal BGM mapping. §9 doesn't name audio, but "genuinely playable"
is the user's call.

**Architecture decided (sketch) 2026-07-14 →
`reference/findings/audio_decision_2026-07-14.md`:** substitution table
`reference/audio_map.json` (fork-index-validated SoT) wired into
metadata_wiring per-map BGM + transpiler playbgm/playfanfare/playse;
conversion/streaming rejected by arithmetic. Slice-1 bar still the user's
call: recommended = ~15-row table covering the 8 slice maps (vs. accept
today's MUS_LITTLEROOT-everywhere).

### 9. Moki Town east edge — the Route 03 seam

`connections.dat` seams are unconverted (Checkpoint-2 deferral); Moki Town E ↔
Route 03 is on the slice-2 frontier. For slice 1, verify the east edge fails
*cleanly* (blocked, no walk-into-void) rather than converting the connection.

### 10. Tile-animation follow-ups (core feature done + user-verified — see Done)

Open questions left behind by the 2026-07-12 animation build:

- **Cadence fidelity.** 16 ticks/frame (~267 ms) is vanilla Emerald's water
  cadence, adopted as a first guess and approved by eye — RMXP's actual
  autotile speed was never measured against Uranium running in-engine. If a
  side-by-side ever shows a mismatch, adjust the `% 16` divisor in
  `_write_anim_fragment` (one place).
- **Corpus generalization.** Slice 1 exercises 2 effects on 1 tileset; the
  corpus has 69 multi-frame autotiles (up to 64 frames — `seatest.png`).
  Untested at scale: animated tiles landing in the SECONDARY tileset (current
  code packs them into the primary block and fails loud past 512 — fine for
  the slice, needs a secondary-callback variant eventually), many effects per
  tileset (DMA queue caps at 20 entries/frame), and columns hitting the
  64-frame lcm guard.
- **Waterfall / transparency.** ts22 slot 1 (`PU-Waterfall(transp)`, 5
  frames) is unused by Map032 cells — the first animated+transparent autotile
  arrives with Route 01 (slice 2). Stipple/alpha classify interaction with
  frame quantization untested.
- **Viewer "expand similar" over-split — FIXED 2026-07-13** (see Done). The
  build-side half (collapsing pixel-identical column keys into one metatile)
  stays deferred deliberately: 8×8 tiles are already pixel-deduped in
  `emit.py`, so the only win is metatile-table entries — not the tight
  budget (that's 8×8 tiles, e.g. ts22 997/1024). Revisit only if a slice
  nears the metatile cap; merge key would need pixels + frames + attrs, and
  it changes ROM output (full rebuild + oracle re-verify). The *color* half
  of the 2026-07-13 report stays separate — `PROJECT_TODO.md` #13/#14.

### 11. Remaining boot-gate walk findings

The user is mid-walk. Bugs #1–#7 (palette off-by-one, dialogue overflow,
invisible rocks, pond reflections, rock debris/respawn, repeated dialogue) are
fixed. Add new findings here as they're reported. Reported 2026-07-13, split
out as items #12 and #13 below: NPCs never move; only the player's house is
enterable.

**2026-07-14 boot walk (BOOT_WALK_CHECKLIST.md + map_feedback/Map032.json),
dispositions 2026-07-15:**

- Map032 NPC movement (M5 + all four map-feedback flags) → fixed under #12
  (fine-tune round), rebuilt + taildropped 2026-07-15, retest pending.
- Lab Pokédex ceremony trigger + void-walk (L section) → NEW item #14.
- H4 post-warp facing → **FIXED + retest PASSED 2026-07-16** (native
  ON_WARP_INTO_MAP_TABLE + turnobject; see MEMORY.md "OPTION C" and Done #8).
- M6 "granny sprite wrong" → NOT a bug: the Rare-Candy giver (M32 EV027) is
  sheet HGSS_008 in Uranium's own data, which is a *young woman in a tank
  top*; our strip converts it faithfully. "Granny" was the checklist's label
  (from an earlier session's shorthand), not the game's. If she looks
  different in PC Uranium, flag again with a screenshot.
- M17 "can't find EV005" → it's the door-sheet event at (28,31) (PU-doorsdew,
  dropped by design, dest never wired — the known inert wall).
- M10 emotes → nothing ambient in Moki; the only slice emote sites are inside
  the Pokédex ceremony (anim 104 → exclamation) and Theo-chase events, so
  M10 can only be judged during M9.
- H3 ninja letter → user is right, it's gated on later story state (EV021's
  boot page isn't the letter); nothing to fix for slice 1.
- X2 audio = stock Emerald everywhere → matches decision #7, no action.

**2026-07-17 story-chain walks (rounds 1–3, ROMs `59a13ba1` → `762e98aa` →
`c9128e58`):**

- Postgame Theo "Champion" scene fired at boot outside the player's house
  (EV080 tripwire) → **FIXED round 3**: `build_page_dispatcher` never checked
  page index 0's own condition (always the unconditional fallback); now scans
  all pages and falls to inert `end` when none matches. Also silently fixed
  EV078/EV081 (same class). Retest **PASSED** — scene gone.
- Story chain **S1–S5 PASS** on `c9128e58` (shoes, Theo trip tile, lab intro
  autorun, YES/NO prompt, NO-then-re-offer).
- **Open frontier: S6** — answering YES to the aptitude test misbehaves
  (details not yet gathered; next /debug session starts here, likely
  overlapping #14's ceremony territory).

**2026-07-22 — S6b Theo loss-path FREEZE fix (ROM `f5867449`, taildropped; retest PENDING):**

- **Symptom:** after LOSING the Moki-lab rival battle (Map050 EV019), the game
  freezes on Theo's last line as the screen begins fading to black (image still
  visible, slightly darkened). Persisted despite the 2026-07-21 fix (`9971428e`:
  HEAL_AFTER + `waitmessage`).
- **Root cause:** `RIVAL_BATTLE_HEAL_AFTER` == 1 (0b01), `RIVAL_BATTLE_TUTORIAL`
  == 3 (0b11). The upstream mask at `battle_setup.c:1322` (`GetRivalBattleFlags()
  & RIVAL_BATTLE_TUTORIAL`) is truthy for HEAL_AFTER too, so the Theo battle
  still got `BATTLE_TYPE_FIRST_BATTLE`. On a loss, `battle_controllers.c:2658`
  reroutes the trainer win-text (`STRINGID_TRAINER1WINTEXT`) under FIRST_BATTLE
  into the FRLG Oak "How disappointing" voiceover
  (`PrintOakText_HowDisappointing` → `BeginNormalPaletteFade(..., RGB_BLACK)`),
  which then waits on Oak-controller graphics/state absent in a normal trainer
  battle → fades to black and hangs. The prior `waitmessage` was treating a
  symptom (it waits on a print controller that never signals done). FRLG's
  Oak's-lab battle works because it uses `TUTORIAL` (Oak voiceover is correct
  there).
- **Fix:** `battle_setup.c:1322` now requires the FULL flag —
  `(GetRivalBattleFlags() & RIVAL_BATTLE_TUTORIAL) == RIVAL_BATTLE_TUTORIAL` —
  so HEAL_AFTER-only earlyrival is a plain losable+heal trainer battle (no
  FIRST_BATTLE, no Oak reroute). Fenced `URANIUM PATHFINDER SLICE`. Zero
  reachable vanilla impact (grep: only FRLG uses earlyrival, with TUTORIAL/0;
  nobody uses HEAL_AFTER alone). Win path unchanged (gated on `BATTLE_TYPE_
  TRAINER`, and the win prints `TRAINER1LOSETEXT` which the reroute never
  touched — S6b win stays as PASSED). `waitmessage` kept (correct hygiene, now
  on a clean path). 1328 tests pass. Verified: hash `2010bbd0` → `f5867449`.

### 14. Lab Pokédex ceremony: wrong trigger + reposition walks into void (boot-walk 2026-07-14)

In PC Uranium the ceremony autostarts on entering the lab (game takes
controls, auto-walks the player next to Theo, prof speaks). In the ROM the
event only fires when the player walks up to the prof and presses A, and the
reposition route then walks the player into a black void before the speech.
Two suspects: (a) the ceremony host event's trigger/page classification on
Map 50 (autorun/touch vs action — cf. the EV009 invisible-host pattern that
became a coord_event on Map 32); (b) the hand-converted reposition route
(`hand_conversions/Map032_EV009.pory` y<=43 clamp was written for the OLD
Moki-side ceremony; the Map-50 doorway coords differ — walk target likely
off-map there). User deferred this behind the Map-32 fixes; localize per the
/debug flow before touching anything.

### 16. Auto-bracket flag-hidden actor spawns (promote EV074's hand fix into the pipeline)

`Map032_EV074.pory` is a hand file whose ONLY delta from transpiler output is
`addobject(75)`/`removeobject(75)` around Theo's walk-in/fade-out — on GBA a
flag-hidden object is never spawned, so `applymovement` at it silently no-ops
(RMXP events always exist; opacity-0 still moves). The wiring layer already
knows every flag-hidden actor id (`_assign_visibility_flags` pool), so staging
can bracket deterministically: `addobject(N)` before a script's first command
referencing hidden actor N (skip if the script already addobjects it — hand
files like EV009); `removeobject(N)` after the last reference (+ trailing
`waitmovement(0)`) ONLY when the actor's last route ends `set_invisible`
(fade-out) — otherwise leave spawned, ON_TRANSITION re-hides on re-entry.
Corpus has many hidden-actor cutscenes; this kills a whole class of 2-line
hand files. Once the pass reproduces EV074, delete that hand file.
(2026-07-17, from the user's "why is the chase hand-converted" challenge.)

**BUILT 2026-07-17** (`tileset_converter/hidden_actor_bracket.py`, wired in
staging pre-remap; EV074 hand file deleted — pass reproduces it; latent fixes:
M32 EV078/EV080, M49 EV018, M172 EV004 actors now spawn). ROM `6e85edb3`,
retest pending.

### 12. NPCs don't move — ✅ USER-VERIFIED DONE 2026-07-15 (custom-route interpreter; ROM `5158b084` walked clean, "looks great, movement issue is done")

All NPCs stand frozen; in Uranium the Moki townsfolk wander/turn. Research
done (3 sub-agents: pipeline audit, fork inventory, corpus census + RGSS
read). Verified facts, superseding the old from-memory notes:

- **Real cause: move_type 3 (custom route), not move_type 1.** `npc_gfx.
  movement_type_for` already maps 1 → `MOVEMENT_TYPE_WANDER_AROUND` (2 Moki
  mons carry it today) but collapses 0/2/3 → static `FACE_<dir>`. Moki's
  visible "life" is almost all type 3: pacing walkers (EV12/48/68–73,
  `move_left×N`/`move_right×N` loops), turn-in-place lookers, and Luz
  flicker props. Corpus: 7342 pages type 0 / 22 type 1 / **0 type 2** /
  1065 type 3 (1051 repeat=true; only ~400 actually translate, 240
  turn-only, 425 no-movement props).
- **Fork facts** (event_object_movement.c): `movement_range 0 = axis check
  SKIPPED` (unlimited, :6598-6622) — so range doesn't need inventing for
  type 1; Essentials random walk is passability-bounded only (RGSS
  `move_type_random` verified: 4/6 random step, 1/6 forward, 1/6 pause) and
  (0,0) is the faithful conversion. Native inventory: WANDER_* family,
  LOOK_AROUND, WALK_LEFT_AND_RIGHT/UP_AND_DOWN patrols (range-respecting),
  FACE_X_AND_Y look combos, WANDER_AROUND_SLOWER. **No approach-player
  type exists** (exhaustive MovementType_* sweep) — moot, type 2 is unused
  corpus-wide. Wander delays (32–128f medium table) ≈ Uranium's freq-3
  102-frame idle gate; speeds close enough (GBA 16 f/tile vs speed-3 9.5).
- **Blocker worry resolved:** blank-gfx through=false events are collision-
  stamped, never emitted as objects — nothing invisible can wander.
- **Plan:** extend `movement_type_for` → (movement_type, range_x, range_y):
  type 3 route classifier — no-translation props → FACE (unchanged);
  turn-only → LOOK_AROUND (or exact FACE_X_AND_Y combo from turn codes);
  pure-horizontal loop → WALK_LEFT_AND_RIGHT + range_x from simulated route
  excursion; pure-vertical → WALK_UP_AND_DOWN + range_y; other translating
  routes → static + drop-report (v1). Type 1 → WANDER_AROUND (0,0). Type 2
  → fail loud. Fidelity note for eye-check: GBA range is centered on spawn,
  RMXP routes are one-sided (pacer left×3 spans [x-3,x]; ±2 vs ±3 call at
  build). `ObjectEvent` grows range fields; wire through
  `build_object_events`; rebuild slice + boot-walk (also confirms the 2
  existing WANDER mons actually move in-engine).
- **Slice roster for the post-fix boot walk** (census): Map049 = 4 visible
  NPCs, all type 0 (Auntie/Lucille/AuntieCutscene/Kellyn — correctly
  static); Map048 = zero visible NPCs (blank-gfx triggers only); Map032 is
  the only map that changes. Expected movers there: EV10 Chyinmunk + EV35
  Barewl (type 1, already WANDER_AROUND — first confirm these move at all
  in-engine), pacers EV12/48/68–73 (type 3 left/right loops), the
  turn-in-place lookers, EV16 Bambo (type 3, speed 4 / freq 5 — the one
  corpus outlier). The 12 "Luz" light props stay static: their route is a
  `(41,15,0)` change-graphic flicker loop — same unsupported live-gfx-swap
  class as #6, not a movement bug.
- **Numbers behind the pacing call** (RGSS verified,
  `021_Game_Character_v17.rb`): idle gate between self-moves =
  `(40−2f)(6−f)` frames → freq 1/3/5 = 190/102/30; corpus random movers use
  freq 1 or 3 only. Speed: page speed ×1.25, `2^s` subpx/frame over
  128 subpx/tile → speed 3 ≈ 9.5 frames/tile (GBA walk = 16 f/tile; wander
  pause table 32–128f ≈ freq 3). Random tick = 4/6 random step, 1/6
  forward, 1/6 pause. Type-3 route shape census (repeat=true): flicker
  `(41,15,0)` ×391, turn-cycle ×61, left×3/right×3 ×25, left×2/right×2 ×24,
  right×3/left×3 ×23.
- **Code locations:** classifier = `npc_gfx.py:135 movement_type_for`
  (consts :36); consumption = `metadata_wiring.py:749`; hardcoded 0 ranges
  = `ObjectEvent.to_dict` metadata_wiring.py:187-188; boot-page rule =
  `npc_gfx.select_boot_page:114`.
- Static-boot-page limitation stands: movement comes from the boot page;
  page-driven movement changes aren't reflected.
- **Landed + rebuilt 2026-07-13:** `movement_spec_for` (renamed from
  `movement_type_for`) classifies move_type 3 routes per the plan above,
  wired through `metadata_wiring.build_object_events`
  (`movement_range_x`/`_y` added to `ObjectEvent`); 51 npc_gfx tests + 1054
  total pass. Staged/assembled/`make modern` clean, ROM taildropped.
  **User boot-walk verdict: NPCs move now but need fine-tuning** — exact
  behavior (range/timing/which routes patrol vs sit static) hasn't been
  checked eye-to-eye against Uranium running on PC yet. **TODO before
  calling this done:** run Uranium on PC side-by-side with the ROM on the
  Moki roster (EV10/35 wander, EV12/48/68–73 pacers, EV16 Bambo outlier,
  turn-in-place lookers) and compare actual movement — range width, pacing
  cadence, which NPCs feel off — then adjust the classifier (`npc_gfx.py`
  `_spec_for_axis`/`_look_spec_for`/the demotion cases) accordingly. Demoted
  routes to recheck against the PC reference: Map032 EV008/48/72/73
  (translation+turns or mixed-axis, codes `[1,2,3,4]`).
- **Fine-tune round BUILT 2026-07-15** (user's 2026-07-14 boot walk +
  map_feedback/Map032.json — pacers never pause; EV048/072 + the
  town-square Chyinmunk frozen; phantom "itemball" at (31,44)). Three new
  classifier rules in `npc_gfx.py`, all pinned by tests:
  1. **freq-gated pacing:** RMXP idle-gates every route command by
     `(40-2f)(6-f)` frames, so wait-free loops below freq 6 now emit
     WANDER_LEFT_AND_RIGHT/UP_AND_DOWN (step + random 0.5–2 s pause)
     instead of continuous WALK_* — EV012/027/068/069/070/071. Note:
     WANDER's direction order is random within the same range (Uranium's
     is deterministic 3-left-then-3-right) — accepted.
  2. **4-leg closed loops → MOVEMENT_TYPE_WALK_SEQUENCE_\*** (`_spec_for_
     loop_route` + `_simulate_walk_sequence`, a GBA-exact replay of the
     fork's automaton — quirk table `_WALK_SEQUENCE_QUIRKS` re-derived
     from the C source by a test): EV008 town-square ring →
     DOWN_RIGHT_UP_LEFT rx6 ry6 with a (0,-1) spawn shift to the ring
     corner (the engine closes the loop at the object's initial coords);
     EV048/072 → LEFT_UP_DOWN_RIGHT rx1 ry2. Walk sequences are
     continuous — EV048/072's freq-3 pauses are lost (no paused sequence
     type exists in the fork); eye-judge at retest.
  3. **map-passability gates** (`npc_gfx.MapPassability`, plumbed via
     `build_slice_maps(tilesets_path=, walkable_overrides=)`): a mover
     spawned on an RMXP all-exits-blocked tile demotes to static — EV012
     stands on a passage-15 pokeball decoration and never moves on PC
     either; this fixes the "itemball I can't pick up + NPC bumping into
     it" report (the ball is map art the NPC's sprite covers, and its
     dialogue works by talking to the NPC). A walk-sequence loop crossing
     a non-clear cell demotes loud — EV073's west path is fenced off in
     Uranium's own data, so it's static on PC too.
  Plus **`map_set.WALKABLE_OVERRIDES = {32: {(38, 43)}}`** (user approved
  2026-07-15): the one tree-crown cell EV008's ring crosses via RMXP
  `through`; `convert_layout(unblocked_cells=)` forces it walkable (art
  kept; the crown's priority-3 top layer draws over sprites) and the
  passability gate treats it open. Side effect: the player can step onto
  that cell (PC blocks it). NOTE: the map viewer's collision overlay
  doesn't know about stamp-level overrides — (38,43) shows blocked in the
  viewer but is walkable in the ROM (same known gap as warp/through-block
  stamps).
  1089 tests pass; full chain rerun; ROM sha1 `a107c65c` taildropped
  2026-07-15. **Retest checklist:** pacers step-pause-step (~1–2 s);
  Chyinmunk laps the square counterclockwise nonstop, vanishing behind
  the big tree for a step; EV048/072 walk their L-loops (continuously —
  acceptable?); the (31,44) NPC stands on the ball art and talks when
  addressed.
- **Round 2 — CUSTOM-ROUTE INTERPRETER BUILT 2026-07-15 (supersedes the
  native-approximation approach above for move_type-3 routes; user
  approved the engine change).** Root insight (from the wiki+recon this
  session): Uranium autonomous routes don't map to native `MOVEMENT_TYPE_*`
  — WANDER randomizes (not deterministic pacing), WALK_SEQUENCE can't pause
  or do variable legs, COMPLEX demotes to static. Corpus census: 834 custom
  routes, 62% not natively expressible. So we added ONE new engine movement
  type that plays a per-object route **bytecode** faithfully. Full design =
  `reference/guides/custom_route_interpreter.md` (SoT: opcode table, FSM,
  data channel, scope). Pieces (all landed, /delegate — lead owned contract
  + integration seam):
  - **Engine (sentinel fence, KEEP, `engine_extension_surface.md` §3):**
    `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE 0x53`, `NUM_MOVEMENT_TYPES`→0x54,
    hand-rolled `MovementType_UraniumCustomRoute` FSM in
    `event_object_movement.c` (BerryTreeGrowth precedent). Route id rides
    `trainerRange_berryTreeId` (u8, same overload berries use — no struct
    change); runtime scratch = `sprite->data[4..7]`; "through" = skip the
    collision call (no engine field). `make modern` clean.
  - **Python:** `route_bytecode.py` (`encode_route` RMXP→bytecode +
    `RouteRegistry` dedup, u8-bounded fail-loud); `npc_gfx` interpreter-first
    in `_spec_for_custom_route` (encode succeeds → CUSTOM_ROUTE spec; the
    v1-out-of-scope codes — diagonals/random/approach/jump/relative-turns —
    fall through to the existing native/static classifier UNCHANGED);
    `metadata_wiring` `ObjectEvent.route_id` → map.json
    `trainer_sight_or_berry_tree_id`, interned via a single slice-wide
    `RouteRegistry`; `route_table_emit.py` writes the engine gen.h
    (`uranium_move_routes.gen.h`). Fully-exit-blocked CUSTOM_ROUTE movers
    still demote to static FACE (preserves graphic facing; interpreter would
    else force DIR_SOUTH).
  - **Integration (lead):** one `RouteRegistry` in `stage_slice_scripts.
    _regenerate_map_json` feeds BOTH map.json route ids AND
    `emit_route_table` — single instance, no cross-pass id rebuild; assemble
    has a defensive only-if-missing stub.
  - **Live result:** Moki Town → 9 CUSTOM_ROUTE movers, 6 deduped engine
    routes; Chyinmunk 27-cmd through-toggle patrol intact (idle 0 = freq-6
    continuous), freq-3 townsfolk idle 102. Full suite 1137 pass, 0 fail.
    ROM sha1 `7b290f02` taildropped 2026-07-15. **ALL UNCOMMITTED.**
  - **v1 scope boundary (eye-test these + the demote fallbacks):** covers
    cardinal steps + turns + wait + through-toggle + freq pacing. NOT yet:
    diagonals, move-random, toward/away-player, forward/backward, jump,
    relative turns (these demote to the native/static path), and mid-route
    speed/graphic/SE (dropped from the stream, route still plays). move_speed
    is ignored in v1 (all steps normal-walk speed) — if pacing looks off vs
    PC Uranium, that's the first knob (per-route speed byte). **Retest
    checklist unchanged from round 1**, but now EVERY custom-route mover
    should step-pause-step with the EXACT RMXP route (deterministic, not
    WANDER-random); EV048/072 now pause too (freq-3, was continuous
    WALK_SEQUENCE). Corpus-wide rollout beyond the slice = future work
    (interpreter is corpus-ready; only Moki exercises it today).
  - **BUGFIX 2026-07-15 (boot-walk: "no NPC moves until you talk to them,
    then one step per talk").** TWO engine bugs in
    `MovementType_UraniumCustomRoute_Callback`, both now fixed:
    1. **(minor)** missing `objectEvent->singleMovementActive = TRUE`/`FALSE`
       around the single-movement (every stock type sets it). Fixed first;
       did NOT resolve the symptom → deeper bug:
    2. **(ROOT CAUSE) sprite-data slot collision.** The FSM stored program
       counter in `data[4]` and through-flag in `data[5]`, but the normal-walk
       movement action (`SetSpriteDataForNormalStep`→`NpcTakeStep`) reuses
       `data[4]`=sSpeed / `data[5]`=sTimer as its own per-frame scratch. So
       the first step (PC=1 from INIT) ran, then the walk overwrote the PC →
       garbage thereafter; only an interaction force-tick advanced it one step.
       Fix: pack PC (low byte) + through (bit 8) into **`data[6]`** — the only
       slot safe across both a walk and a wait (walk uses 3/4/5, delay uses
       3/7) — and re-read idle from `route[0]`. Also added
       `ClearObjectEventMovement` on INIT and clamped idle≥1 (a separate bug:
       freq-6 routes emit idle 0, and `WaitForMovementDelay`'s pre-decrement
       underflows 0→~65k-frame stall). Contract doc data-channel + FSM §§
       corrected so the slot map can't be re-broken. `make modern` clean, ROM
       sha1 `5158b084` taildropped 2026-07-15 (supersedes `66097603` /
       `7b290f02`). Retest pending.

### 13. Expand Moki interiors — BUILT 2026-07-14, needs boot-walk

Slice widened 3→8 maps; full chain (stage → assemble → `make modern`) clean
2026-07-14, ROM taildropped. Built per
`reference/guides/slice_expansion_runbook.md`.

- **New maps:** 50 (Moki Town Professor Lab), 64 (MokiTownHouse2), 65
  (MokiTownHouse1), 172 (Theo's House 1F), 89 (Theo's House 2F — reachable
  only via 172's internal stairs, mirrors the 48/49 floor pattern).
  `SLICE_MAP_IDS` / `ALLOWED_MAPS` / `WARP_OVERRIDES` all widened.
- **Door dests resolved** (were "unrecorded"): Map032 EV003→50 (door 17,11),
  EV006→64 (43,31), EV007→65 (24,42), EV017→172 (56,42). Interior exits
  wired (64/65 EV003 @9,14; 172 street exit EV002 @10,11 + stairs EV003
  @12,3).
- **Still blocked, by design:** cave triad EV023/036/037→map 33 (Route 01,
  slice-2 frontier) and **EV005** (door left unwired this round — inert
  wall).
- **Supporting work:** +11 `npc_gfx_map.json` entries (HGSS townsfolk,
  PU-Cam, PU-Hazma, ZP-Professor2, PU-PokeballMachine); NEW `large_prop`
  64×64 sprite class in sprites.py/sprite_emit.py (lab ball machine, 96×128
  source, RayquazaStill-style static object); +3 `map_name_overrides`.
- **Build facts:** mints 196 flags / 106 vars / 27 self-switches (16→27) /
  8 temp-switches; ROM 78.88%; 1064 tests pass (npc_gfx count re-pinned
  18→29; `test_build_slice_maps_smoke` cleared once the sprite pass
  regenerated `uranium_event_objects.gen.h`). Map172 staging dropped 6
  orphan pages (EV002/003/004×4 — non-emitted events).
- **§9 boot-walk checklist:** 4 street doors warp in + exits warp back;
  Theo 1F↔2F stairs; interior art + NPC palettes **by eye** (all converted
  sheets share ≤4 palette banks — overflow is silent color garbage, the eye
  is the gate); lab machine prop renders 64×64; nothing visibly missing in
  Theo's house (the dropped orphan pages); interior NPCs sane. All
  uncommitted — commit after the walk.

### 15. Theo intro cutscene missing (boot-walk 2026-07-15) — SEPARATE work unit, own session

Boot-walk: Theo's intro cutscene (runs up → talks → runs ahead) entirely
absent; no Theo anywhere on Moki Town. Root-caused 2026-07-15.

**Root cause — the drop is CORRECT for boot state, not a bug in itself.**
`select_boot_page` (`npc_gfx.py:114`) picks Theo's RMXP boot page, which the
Uranium author drew with `opacity == 0` — Theo genuinely doesn't exist in town
at game start. The converter drops opacity-0 events in `build_object_events`
(`metadata_wiring.py:743-747`): opacity-0 + event-touch → reclassified to an
invisible `coord` event (line 745); opacity-0 + action-trigger → fully dropped
via `_drop(eid, DROP_OPACITY0)` (line 747). Confirmed against
`output/uranium-build/maps/Map032.json`:
- **EV075 "Theo"** (35,15), gfx `Rivaltheo`, boot page0 `opacity=0` trigger=0
  (action) → `_drop(DROP_OPACITY0)`. Not emitted.
- **EV009 / EV074** (intro trainers, gfx HGSS_014), boot page0 `opacity=0`
  trigger=2 (event-touch) → become invisible coord events, not object events.
- Ambient NPCs survive because their boot page is `opacity=255` from the start.

So the missing thing is the **triggered cutscene**, not a standing NPC.

**CORRECTION (logged):** an earlier roster read claimed "Theo stands at
(35,15) at boot" — WRONG. It read the `Rivaltheo` graphic name and missed
`opacity=0`. Theo is invisible at boot by design.

**Story context (wiki-confirmed).** Moki intro = wiki step 5: after the lab
starter test, Theo + Prof. Bamb'o run the catching tutorial at the west grass
(Kevlar/Route-1 exit) and give Pokédex + Poké Balls. The whole ceremony cast is
gated by **var 101 (intro/starter-ceremony progress counter; confirm the exact
name in `reference/uranium_variables.json`)**: EV002 Theo (16,45, var101≥2/≥4),
EV016 Bambo (15,44, var101≥1→ZP-Professor), EV075 Theo (35,15), EV076
Chyinmunk76, EV077 Starter77, EV009/EV074 trainers, EV081 TheoChamp (switch
125). See MEMORY "hand bucket" — `hand_conversions/Map032_EV009.pory` is the
Pokédex-ceremony hand override (Moki-side; Map-50 lab-side is item #14).

**Fix scope — medium-large, higher-uncertainty. NOT "un-drop the actor"**
(that would wrongly park Theo in town at boot). Needs, together:
- (a) emit Theo as a **hidden actor the cutscene reveals/spawns** (not a static
  boot NPC);
- (b) convert the **trigger + var101 gating** that starts the scene (per-page
  dispatcher exists from bug-#7 work; needs trigger-type wired);
- (c) **reveal the opacity-0 actor mid-script** — THE THORNY PART: no fork-
  native script-callable live gfx/opacity swap (`VAR_OBJ_GFX_ID_x` resolves at
  spawn only). Recipe = `setvar`+`removeobject`+`addobject`, same unsupported
  class as item #6 (ceremony sprite swaps);
- (d) **run-up / run-ahead movement** = cmd-209 `applymovement` — ALREADY
  handled by the transpiler (`_emit_move_route`, transpiler.py:1182);
- (e) advance story flags on exit — handled.

**Represents a whole class:** every rival/intro/story cutscene corpus-wide
works this way (actor hidden at boot, revealed + choreographed by a gated
trigger). Do it as its own focused session, not a bolt-on to the ambient-NPC
interpreter (which is a different subsystem: autonomous `movement_type`, no
actor-reveal). Distinct from the ambient movement work being built 2026-07-15.

**First step when the session starts** (user declined this probe for now):
pin the exact event/page that fires the scene and how it reveals Theo (opacity
command? page-graphic swap? spawn?) — that determines whether (c)'s spawn
recipe is truly required. Localize per the `/debug` flow before touching code.
Cross-ref item #14 (lab ceremony, same trigger/reveal class on Map 50).

## Accepted deferrals (not slice-1 work — listed so they aren't re-litigated)

- **HEROINE player** — slice boots MALE hardcoded; heroine sheets are exact-2×
  and convert cleanly when wanted.
- **Bike/surf/fish/field-move player poses** beyond rock smash — still Emerald
  Brendan; none slice-reachable.
- **`displayNinjaLetter` card UI** — letter renders as a scrolling msgbox;
  bespoke scene is a Phase-8 custom-C candidate.
- **88 CommonEvent queue entries** — slice calls zero CEs.
- **Base-page own condition ignored by dispatchers** — Page1 is always the
  fallback; sprite is static anyway (see bug-#7 notes in MEMORY).

## Done

- **2026-07-21 — S6 aptitude test + starter species: CLOSED, boot-walk PASSED
  on ROM `b0b21993`.** Supersedes the 2026-07-17 "#17" entry and closes #2
  (Auntie's RAPTORCH branch). Full arc: `\ch` inline-choice transpiler support
  + hand-tail scoring landed 2026-07-17 (ROM `6e85edb3`, Emerald stand-in
  starters pending real species); real Orchynx/Raptorch/Eletux lines (+
  Metalynx/Archilles/Electruxo evolutions) landed 2026-07-19/20 via
  `STARTER_SPECIES_PLAN.md` W1-W9 (species staging emitter, battler/icon/cry
  converters, fork gate extras — `SPECIES_RAPTORCH` etc. now pass the
  capability gate, closing #2's blocker for real: `checkspecies(SPECIES_*)`
  compiles clean in Map049's Auntie dialogue); two boot-walk defects fixed en
  route (lab-NPC freeze from a missing `releaseall`, invisible party from a
  missing `FLAG_SYS_POKEMON_GET` on `givemon`). Final bug, found in the
  2026-07-21 walk: the quiz **always** resolved to Eletux regardless of
  answers — the argmax sign-test literal `32768` (0x8000) fell inside the
  engine's `SPECIAL_VARS` range, so the `compare` asm macro silently compiled
  it as "compare against `VAR_0x8000`" (the engine's own switch-statement
  scratch var, left holding the last question's raw answer index by the
  quiz's per-question `switch()`) instead of the literal — fixed by using
  32767 instead (`hand_conversions/Map050_EV005.pory`, commit `b3b1b623`).
  User boot-walked and confirmed all four answer combos resolve correctly.
- **2026-07-16 — #8 Warp-class refinement: CLOSED. Its premise was wrong; the
  one real gap (door animation) is a user-accepted skip.** Investigated the three
  warp classes the Checkpoint-2 deferral named
  (`reference/viewer/walker_checkpoint2_findings.md` §3) and all three resolved
  without a build:
  - **Stairs/mats — already correct, nothing to fix.** `MB_NON_ANIMATED_DOOR` is
    exactly what vanilla uses for interior floor-to-floor stairs; verified by
    decoding real Game Freak data, not from memory:
    `LittlerootTown_BrendansHouse_1F`'s upstairs warp (8,2) sits on metatile
    `0x211` of `gTileset_BrendansMaysHouse`, whose byte in
    `metatile_attributes.bin` is `0x60` = `MB_NON_ANIMATED_DOOR` (the 2F return
    warp matches). "Stairs/mats behave like doors" was a misreading of the
    engine, not a defect.
  - **Map-edge arrow warps — not slice-1.** These are the unconverted
    `connections.dat` seams (the Moki Town x=8 exits EV23/36/37 → Route 01);
    tracked under #9 / the slice-2 connections work, not here.
  - **Doors don't animate — REAL, but skipped (user decision 2026-07-16).**
    Uranium's 5 Moki Town doors are genuinely animated, the RPG Maker way: a
    player-touch event carrying a door charset (EV3 `FKdoors1`; EV5/6/7/17
    `PU-doorsdew`) whose 4 "facing" rows are opening frames, cycled by
    `Turn`/`Wait` move-route commands + an "Entering Door" SE, then the player
    walks up through and it closes. `metadata_wiring.classify_event` drops all
    of it — a player-touch event with a code-201 becomes a bare `WarpSpec` and
    the object event (door sprite included) is discarded; today's door art is
    just the closed door baked into the tileset column.
  Two approaches were scoped and both rejected as not worth the cost for pure
  feel — **if this is ever revisited, don't re-derive them:** (A) *faithful RMXP*
  — keep the door as an object event + `coord_event` trigger and let the
  transpiler emit the SE/frame-cycle/walk/warp it already converts; zero engine
  change, reuses the sprite pipeline so frames get an OBJ palette bank (the door
  sheet is a prop, cf. `BREAK_PROP_SHEETS`/`fk107-rocksmash`); open risks =
  sprite draw order over the door tile and `coord_event` trigger semantics.
  (B) *native Emerald door* — convert frames to BG door-anim tiles + a
  `sDoorAnimGraphicsTable` entry per door (keyed metatile+tileset,
  `engine/src/field_door.c:16-24, 331-338, 612-620`), gated by `MB_ANIMATED_DOOR`
  and `TryDoorWarp` (`field_control_avatar.c:1097`, north-approach only); gives
  the native open/walk-in/close + exit animation, but costs a C table edit per
  door AND the frames must quantize into one of the map's existing **BG**
  palettes (they come from a sprite sheet — real silent-colour-garbage risk).
  Note a table entry is mandatory: `MB_ANIMATED_DOOR` with no match makes
  `GetDoorGraphics` return NULL and the animation silently no-ops.
- **2026-07-16 — #8/H4 post-warp facing: FIXED, user retest PASSED** (ROM
  `e035dac1`, commit `e520c529`). Native `MAP_SCRIPT_ON_WARP_INTO_MAP_TABLE` +
  `turnobject`, data-only — no engine, struct, schema or `mapjson.cpp` change.
  Two earlier attempts failed and are **dead ends — do not re-attempt**: Option A
  (`MB_*_ARROW_WARP` stamping) re-triggers structurally, Option B
  (`arrivalDirection` on `struct WarpEvent`) broke every warp via an 8→10 byte
  stride change. Full narrative + verified engine gotchas: MEMORY.md
  "WARP-ARRIVAL FACING" / "OPTION C".
- **2026-07-13 — #5 new_game.c test harness: user decision — KEEP
  indefinitely** as the standing HM/field-move test rig for slice expansion
  (new maps will need badge/move grants to exercise their HM paths; expected
  to grow per-HM). No longer a remove-when-progression-covers-it obligation —
  strip only for a release ROM. Ledger disposition + in-code comment updated
  (`engine_extension_surface.md` §3, `engine/src/new_game.c:277`).
- **2026-07-13 — #10 viewer "expand similar" over-split fixed (viewer-only),
  user-verified by eye (one click grabs all the flowers)**:
  new `_pixel_classes` in `map_viewer_common.py` groups column keys by
  frame-aware rendered pixels (layer split + behavior + every animation
  frame; a column tripping the 64-frame lcm guard stays ungrouped rather
  than merging off frame 0); payload ships `pix_class` (colkey_idx → class
  rep), `btn-expand` selects by it. Map032: 839 colkeys → 697 classes; the
  12 flower shape-variants collapse to one 31-cell group, the 3 sparkle-
  overlay cells correctly stay out; animated merged only with animated.
  Pipeline/ROM output untouched. 7 tests
  (`test_map_viewer_pixel_classes.py`); 1036 pass.
- **2026-07-13 — #3 `\wt[n]` text-pause timing: user-approved by eye** — the
  first-guess `n*3` frames formula in `deterministic.translate_text_codes`
  feels right during the boot-gate walk; no multiplier change needed.
- **2026-07-13 — #1 temp-switch page dispatch: carve-out landed, premise
  corrected — the "8 Moki NPCs" are warp doors, dispatch was moot in-game**:
  the 8 ts-gated events (Map032 EV003/005/006/007/017 = door gfx, EV023/036/
  037 = the blank cave-entrance triad) are NOT dialogue toggles — P1 (touch) =
  the code-201 transfer, P2 (`s:tsOff?("A")` autorun) = `get_character(0).
  onEvent?` arrival walk-out + `setTempSwitchOn("A")`. Both halves are subsumed
  by the native warp conversion, and none of the 8 is emitted as an object
  event, so page dispatch never affected gameplay. Corpus census
  (ts_gate_census): all 324 ts-gated multi-page events corpus-wide are this
  door pattern (5 matching switch ids 12–15/22; 136 door-gfx + 188 blank;
  zero NPCs). Landed anyway as correctness insurance: `metadata_wiring.
  _resolve_switch_gate_term` resolves `s:tsOn?/tsOff?("X")` labels to
  `flag()`/`!flag()` on the event's own `mint_temp_switch` flag (verified
  event-scoped in `022_Game_Event_v17.rb:70-86,126-134`; other `s:` labels
  still defer; no `FLAG_*` for the `s:` id — §6 intact). Plus the REAL live
  fix it flushed out: `FlagRegistry.load()` never restores labels, so
  `label_for_switch` — and bug-#7's own label-mint path in
  `resolve_switch_flag` — was dead at the staging call site; new
  `FlagRegistry.seed_labels()` (split from `pre_seed`) is now called in
  `stage_slice_scripts` after `load()`. Slice output byte-identical (same 15
  dispatchers, 0 new mints — the 8 temp-switch flags were already transpiler-
  minted) → no rebuild needed. EV036's P2 gated tsOn (id 12) not tsOff = a
  Uranium mapper bug (choreography unreachable); moot, event not emitted.
  1029 tests pass.
- **2026-07-13 — #4 Moki ledge tiles: resolved by analysis, work moved to
  `SLICE2_TODO.md` #1**: the 3 warning tiles (ts22 840/841/842) are the
  pond-dock front at Map032 (37–39,53); Essentials gates ledge jumps purely by
  the tile's 4-dir passage bits (stock v17 — jump dir = movement dir, never
  stored), and 0x0E opens only the water side → from land they're walls, so
  the MB_NORMAL fallback is already faithful. Nothing to hand-map, and no
  slice-1 surface to test jumps on. Jump directions are auto-derivable
  corpus-wide from passage bits — derivation rule + ts22 inventory in
  SLICE2_TODO #1; the ~30 south-ledge over-block residual moves there too.
  The 3 build warnings stay (benign) until the derivation lands.
- **2026-07-12 — tile animation (Map032 flowers + pond)**: RMXP animated
  autotiles → GBA tileset anims, deterministic pipeline end-to-end (per-column
  lcm frame rendering, frame-aware dedup with static-demotion, union-color
  quantization, contiguous per-effect tile blocks, gen'd
  `uranium_anims.gen.h` callback via sentinel hook in
  `engine/src/tileset_anims.c`). ts22 = pond 57×19f + flowers 4×4f,
  997/1024 tiles. Viewer gained an "Animated" overlay. User-verified in-game.
  Follow-ups tracked in Open #10.
- **2026-07-11 — bug #7 repeated NPC dialogue** (`710e258c`): page dispatchers
  for global switch/var gates; Auntie + rare-candy granny advance correctly.
  User-verified on device.
- **2026-07-10 — audit F1+F2** (`5fc67dbf`): flag/var ranges grown behind
  `RPG2GBA_EXPAND_EVENT_RANGES`; temp-switch region clears on map transition.
  User boot-walked.
- **2026-07-11 — test debt: 2 known MAP_MOKI_TOWN failures**: root cause was a
  real registry gap, not just a test-fixture issue. `map_constants.
  load_vanilla_map_consts` read the *working tree's* generated
  `include/constants/map_groups.h`; a **built** engine's copy already carries
  this slice's own previously-emitted `MAP_MOKI_TOWN` etc. from a prior
  assemble, so a fresh mint saw its own output as a false "vanilla"
  collision. Fixed at the source: `load_vanilla_map_consts` now reads the
  vanilla `MAP_*` set from **git HEAD** (`_load_vanilla_map_ids_pristine`,
  one `git archive` of `data/maps/`, ~900 dirs' `map.json` `"id"` fields —
  `map_groups.h` itself is upstream-gitignored/build-generated, never
  committed) instead of the working tree, mirroring `fork_index`'s
  pristine-git-read pattern. Uranium map dirs are excluded by construction
  (`data/maps/*/` gitignored repo-root-side, never committed) — no false
  collision, and real vanilla-collision detection still works. Applies to
  every caller of `build_map_constants` (`assemble_pathfinder`, `phase5`,
  `stage_slice_scripts`), not just these two tests. Also uncovered + fixed a
  second, previously-masked bug: `test_build_slice_maps_smoke` never passed
  `npc_gfx` to `build_slice_maps`, which real slice maps (visible NPCs)
  require since the 2026-07-06 NPC-gfx-map landing — fixed by loading the
  real `reference/npc_gfx_map.json` against the built fork headers, skipping
  cleanly if either isn't present. 964 pass, 0 known failures.
