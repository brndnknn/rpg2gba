# Slice 1 event inventory

Every RMXP event on the eight slice-1 maps (`tileset_converter/map_set.py`
`SLICE_MAP_IDS = [49, 48, 32, 50, 64, 65, 172, 89]`), what it does, how its
pieces chain together, what Emerald construct realizes it, whether it has ever
been hand-authored, and what it cost to debug.

**131 events total.** Compiled 2026-07-26 from the build in
`output/uranium-build/` (raw RMXP `maps/Map*.json`, emitted
`porymap/maps/*/map.json`, transpiled `scripts/Map*.pory`, spliced
`staging/scripts/Map*.pory`, `porymap/dispatch/Map*_dispatch.pory`), plus
`git log` over `src/rpg2gba/conversion_agent/hand_conversions/` for the
hand-authoring history. **§11 (debug history) is reconstructed, not recorded** —
read its caveat box before quoting its numbers. **The cited code and build output
stay authoritative — this file is a map, not a source of truth.** Late-game/postgame content is
described mechanically (command counts, gates, choreography shape) rather than
by plot.

---

## 1. How one RMXP event becomes ROM content

An RMXP event is not a script — it is *a stack of pages*, each with its own
activation condition, trigger, graphic, and command list. Only one page is
"active" at a time (RMXP picks the **highest-numbered page whose condition
holds**). Almost every "chain" in this document is that structure, unrolled
across several Emerald mechanisms at once:

| Piece | Where it lives | What it does |
|---|---|---|
| **Boot page** | `metadata_wiring.select_boot_page` | The page whose condition holds at *new-game* state. It alone decides the object's sprite, facing and movement type — GBA object events are static after spawn, so page-driven graphic/movement changes are not reflected. |
| **Page bodies** | `Map{m}_EV{e}_Page{n}` in `scripts/Map*.pory` | Each page's command list, transpiled 1:1 into Poryscript. |
| **Dispatcher** | `Map{m}_EV{e}_Dispatch` in `porymap/dispatch/` | RMXP's page selection, re-implemented at runtime: an if-chain over the page conditions, highest page first, `goto`-ing that page's body; falls through to `end` when no page matches. This is what turns "5 pages" into "one talkable NPC". |
| **Object event** | `map.json` `object_events` | The visible actor. Carries graphics id, movement type + range, visibility `flag`, and `script` = the dispatcher (or the single page body). |
| **BG event** | `map.json` `bg_events` (`type: sign`) | A blank-graphic, action-trigger event — signs, furniture, wall text. |
| **Coord event** | `map.json` `coord_events` | A blank/invisible **event-touch** event. `Trainer(N)`-named events become a *ray* of N coord events in the graphic's facing direction (the Essentials sight-line convention); a touch event on an unstandable tile is relocated to its standable orthogonal neighbours. |
| **Warp event** | `map.json` `warp_events` | A player-touch event whose page-1 body is a code-201 transfer into another slice map. Source warps keep indices `0..n-1`; **arrival** warps are appended at the RMXP destination coords, and a door's `dest_warp_id` names the *arrival* warp on the far map (`metadata_wiring._resolve_all_warp_events`). |
| **`ON_TRANSITION`** | `mapscripts` block | Sets/clears the `FLAG_TEMP_1x` visibility flag of every story-gated or hidden actor on map entry — this is how a page condition that a static object event can't express still gates whether the actor exists. |
| **`ON_FRAME_TABLE`** | `mapscripts` + `<Map>_OnFrame` | Autorun pages. Guard-checked once per map entry (latched on `VAR_TEMP_C`, re-armed by `metadata_wiring.insert_onframe_rearms` when a guard input changes). |
| **`ON_WARP_INTO_MAP_TABLE`** | `mapscripts` + `<Map>_OnWarpFacing` | Post-warp arrival facing, dispatched on the player's landing coords (`SLICE1_TODO.md` Done "#8/H4 OPTION C"). |
| **Sub-labels** | `_Move{n}`, `_Choice{n}_Opt{k}`, `_Tally`, `_TestBody` | Movement routes, `dynmultichoice` option text, and hand-authored helper scripts. One RMXP `Set Move Route` (code 209) becomes one `movement` block + `applymovement`/`waitmovement`. |
| **Hidden-actor bracket** | `tileset_converter/hidden_actor_bracket.py` | An RMXP event always exists even at opacity 0; a GBA flag-hidden object does not. The staging pass auto-inserts `addobject(N)` before the first reference to a hidden actor and `removeobject(N)` after its last one, so `applymovement` at it doesn't silently no-op. |

**Drops.** A boot page with a blank graphic on player-touch / autorun / parallel,
or an invisible (opacity-0) graphic on a non-touch trigger, or a door-sheet
graphic, emits no object (`DROP:*`). An event whose *every* page is story-gated
has no boot page at all (`DROP:no_boot_page`) — but if a cutscene still needs it
as a movement target, the required-actor pass places it anyway as a
**flag-hidden actor**. An event that warps to a map outside the slice is skipped
whole (`SKIP:out-of-slice warp`). Dropped-and-unreferenced page bodies are then
pruned out of `staging/scripts/`, which is why some events have transpiled
labels but none in the staged file.

### Column legend

- **Label** — canonical id `Map{mmm}_EV{eee}`; page bodies are `…_Page{n}`.
- **Name** — RMXP event name where it is meaningful, otherwise a description.
- **Realized as** — what actually reaches the ROM.
- **Emerald analog** — the native construct used, and (in *italics*) a native
  construct that could replace bespoke work.
- **Hand** — `–` never hand-authored · `yes` currently hand-authored ·
  `removed` hand file existed and has been deleted.

### Summary

| | Map 49 | Map 48 | Map 32 | Map 50 | Map 64 | Map 65 | Map 172 | Map 89 | **Total** |
|---|---|---|---|---|---|---|---|---|---|
| events | 22 | 13 | 52 | 27 | 4 | 3 | 4 | 6 | **131** |
| object events | 3 | 0 | 26 | 4 | 3 | 2 | 2 | 0 | **40** |
| bg events | 13 | 9 | 3 | 17 | 0 | 0 | 0 | 5 | **47** |
| coord-event hosts | 0 | 0 | 4 | 1 | 0 | 0 | 0 | 0 | **5** |
| warps (source) | 2 | 1 | 5 | 1 | 1 | 1 | 2 | 1 | **14** |
| autoruns (`ON_FRAME`) | 2 | 2 | 0 | 3 | 0 | 0 | 2 | 0 | **9** |
| nothing emitted | 2 | 1 | 14 | 2 | 0 | 0 | 0 | 0 | **19** |
| events in a debug thread (§11) | 1 | 0 | 16 | 3 | 0 | 0 | 1 | 0 | **21** |

Hand-authored, ever: **5 events** — `Map032_EV009`, `Map032_EV074` (removed),
`Map049_EV021`, `Map050_EV005`, `Map050_EV019`. Currently: **4**. Every other
event on every slice map is deterministic transpiler output.

---

## 2. Map 049 — Player's House 1F (`MokiTownPlayersHouse1F`)

Spawn map. 22 events → 3 object events, 13 bg events, 4 warp slots (2 source +
2 arrival), 2 `ON_FRAME` autoruns, 2 not emitted.

**Debug history:** `EV001` 1 round (§11.10); the map's 2 warps share the
3-approach warp-facing thread (§11.4). Everything else here passed first walk.

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV001` | **Auntie** — guardian NPC | 5-page NPC. P1 = the running-shoes gift (12 msgboxes, ME + SE, sets `FLAG_SYS_B_DASH` and its own self-switch). P2 = one-line repeat. P3 = post-starter reaction, branching on which starter you carry (`checkspecies`). P4 = full heal + 13-way random small-talk. P5 = a shorter postgame heal. | **Chain of 5 pages → 1 dispatcher.** `Map049_EV001_Dispatch` tests, top down: `FLAG_FINAL_EVENT` → P5; `VAR_QUEST_LOG ≥ 2 && SSA` → P4; `≥ 1 && SSA` → P3; `SSA` → P2; else P1. P1 ends by setting `FLAG_MAP049_EVENT001_SSA`, which is what advances the chain. | Object event + `msgbox`; `setflag(FLAG_SYS_B_DASH)` is exactly `LittlerootTown_EventScript_SetReceivedRunningShoes`; heal = `special(HealPlayerParty)`; starter check = `checkspecies` (fork gate extra). *Heal arm could reuse `Common_EventScript_PkmnCenterNurse`.* | – |
| `EV002` | Front door → Moki Town | Player-touch transfer to Moki Town (28,31). 4 pages, but pages 1/3 are "say goodbye first" refusals and 2/4 the actual transfer. | **Whole 4-page event collapses to one warp.** `classify_event` sees a player-touch code-201 into a slice map → `WarpSpec`; the object event and all four page bodies are dropped (pruned from staging). The refusal gating is lost by design. | `warp_events` slot 0 → `MAP_MOKI_TOWN` arrival warp 5. | – |
| `EV003` | Stairs → 2F | Player-touch transfer to Map 48 (4,3), with a diagonal step-up route. | Single page → one warp. | `warp_events` slot 1 → `MOKI_TOWN_PLAYERS_HOUSE_2F` arrival warp 1. Vanilla uses `MB_NON_ANIMATED_DOOR` for interior stairs — verified identical (`SLICE1_TODO.md` Done #8). | – |
| `EV004` | TV (right) | One msgbox. | none | `bg_events` sign + `msgbox`. *`EventScript_TV` (`data/scripts/tv.inc`) is the vanilla common; not reused because the text is Uranium's.* | – |
| `EV005` | TV (left) | Same text as EV004. | none | as above | – |
| `EV006` | Framed embroidery | One msgbox. | none | bg sign + `msgbox` | – |
| `EV007` | China cabinet (right) | One msgbox. | none | bg sign + `msgbox`. *`EventScript_BookShelf` pattern.* | – |
| `EV008` | China cabinet (left) | Same text as EV007. | none | as above | – |
| `EV009` | Fridge | One msgbox. | none | bg sign + `msgbox` | – |
| `EV010` | Stove & sink | One msgbox. | none | bg sign + `msgbox` | – |
| `EV011` | Coffee cup on table | One msgbox. | none | bg sign + `msgbox` | – |
| `EV012` | Window (view of the lab) | One msgbox. | none | bg sign + `msgbox` | – |
| `EV013` | Dresser (right) | One msgbox. | none | bg sign + `msgbox` | – |
| `EV014` | Dresser (left) | Same text as EV013. | none | as above | – |
| `EV015` | Bookshelf (Pokémon books) | One msgbox. | none | bg sign + `msgbox`. *`EventScript_BookShelf`.* | – |
| `EV016` | Bookshelf (novels) | One msgbox. | none | as above | – |
| `EV017` | Lucille — bedside NPC | 3 msgboxes, single page gated on switch 125 (`FLAG_FINAL_EVENT`). | none — the only page is story-gated, so there is no boot page and nothing references it as an actor. | Would be an object event + `msgbox`. **Not emitted** (`DROP:no_boot_page`); body pruned from staging. | – |
| `EV018` | Post Cutscene (autorun) | 75-command postgame autorun: 20 msgboxes, 10 move routes across 3 actors, one `giveitem`, an emote, a fade. Gated on switch 125. | **Autorun → map script.** Not an object; the body becomes `Map049_EV018_Page1`, reached from `MokiTownPlayersHouse1F_OnFrame` under `FLAG_FINAL_EVENT && !SSA`. Its ten `_Move{n}` blocks drive local ids 1 (EV001) and 19 (EV019), including `set_visible`/`set_invisible` beats. | `MAP_SCRIPT_ON_FRAME_TABLE` + `applymovement`/`waitmovement`; emote = `Common_Movement_ExclamationMark`; `giveitem`. Vanilla shape: `LittlerootTown_EventScript_StepOffTruckMale`. | – |
| `EV019` | AuntieCutscene — actor | No commands at all. Exists purely as a second Auntie body for EV018's choreography. | **Actor-only.** Both pages are story-gated → no boot page, but EV018 targets local id 2, so the required-actor pass places it as a **flag-hidden object** (`FLAG_TEMP_11`), toggled in `ON_TRANSITION`. Its dispatcher resolves to two `end` bodies. | Object event with a visibility flag; vanilla analog = `FLAG_HIDE_*` objects toggled in `<Map>_OnTransition`. | – |
| `EV020` | Kellyn — postgame NPC | Single page, 11 msgboxes on a 4-state rotating counter. | **Counter chain inside one page:** `VAR_TEMP_POKEMON_CHOICE` 0→1→2→≥3→0, one branch per state. The transpiler also dropped one unsatisfiable numeric guard arm (flagged in-line). | Object event, `FLAG_TEMP_12`, `ON_TRANSITION` gate; branch = `compare`/`goto_if`. | – |
| `EV021` | **Letter** | Postgame letter: `displayNinjaLetter` (a bespoke full-screen letter-card scene in Uranium) plus 12 msgboxes, a code-202 actor teleport, two move routes and a two-hop warp. | **Hand-authored, single event.** Letter card → one scrolling `msgbox`; code-202 → `setobjectxy(20, 18, 9)`; then routes on actor 20 + the player, then `warp`→48→`warp`→49 to reposition. | No Emerald analog for the card UI (Phase-8 custom-C candidate). Teleport = `setobjectxy`; reposition = double `warp`. | **yes** |
| `EV022` | HEAL (white-out respawn) | Autorun gated on switch 5 (`FLAG_STARTING_OVER`): fade in, `HealPlayerParty`, clear the flag. | **Autorun → map script.** Second entry in `MokiTownPlayersHouse1F_OnFrame`. | `MAP_SCRIPT_ON_FRAME_TABLE` + `special(HealPlayerParty)`. *Emerald handles white-out respawn + heal natively; this whole event is Essentials plumbing that native respawn could replace.* | – |

---

## 3. Map 048 — Player's House 2F (`MokiTownPlayersHouse2F`)

13 events → 0 object events, 10 bg events, 1 source warp, 2 `ON_FRAME`
autoruns, 1 not emitted. No visible NPCs on this map.

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV001` | Wake-up autorun | Fade in, one msgbox ("come downstairs"), set self-switch A. P2 is the spent no-op. | **2 pages → autorun + latch.** P1 body reached from `MokiTownPlayersHouse2F_OnFrame` under `!FLAG_MAP048_EVENT001_SSA`; P1 sets that flag, which permanently retires it. | `ON_FRAME_TABLE` + `msgbox` + `setflag`. Vanilla shape: Littleroot's intro `map_script_2` entries. | – |
| `EV002` | Stairs → 1F | Player-touch transfer to Map 49 (11,3) with a diagonal step-down route. | Single page → one warp. | `warp_events` slot 0 → `…HOUSE_1F` arrival warp 2. | – |
| `EV003` | Games console | One msgbox. | none | bg sign + `msgbox` | – |
| `EV004` | PC | RMXP `pbTrainerPC` script call. | none | **`goto(EventScript_PC)`** — the native Emerald PC (`data/scripts/pc.inc`), used directly. | – |
| `EV005` | Boot init (parallel) | Sets switches `FLAG_GAME_RUNNING` + `FLAG_JUKEBOX`, then its own self-switch. | **Not emitted** (`DROP:parallel`) — a blank-graphic parallel page is map-script territory and its two flags are Essentials-runtime bookkeeping with no GBA meaning. | none needed | – |
| `EV006` | Bed | One msgbox. | none | bg sign + `msgbox` | – |
| `EV007` | Wall map (left) | msgbox + `pbShowMap`. | none | **`special(FieldShowRegionMap)`** (`engine/src/field_specials.c:1014`). *No vanilla map script uses it — FRLG's town map is a plain msgbox — so this is a deliberate upgrade over the flavour-text analog.* | – |
| `EV008` | Wall map (right) | Same as EV007. | none | as above | – |
| `EV009` | Bed (second tile) | One msgbox. | none | bg sign + `msgbox` | – |
| `EV010` | Bookshelf (left) | 3 msgboxes. | none | bg sign + `msgbox` ×3 | – |
| `EV011` | TV | 3-way random flavour line, then a closing line. | **Random chain in one page:** `random(3)` → `VAR_TEMP_POKEMON_CHOICE`, three `if` arms, shared tail. | `random` + `copyvar` + `compare`; `EventScript_TV` is the vanilla common. | – |
| `EV012` | Bookshelf (right) | Same 3 msgboxes as EV010. | none | bg sign + `msgbox` ×3 | – |
| `EV013` | HEAL (white-out respawn) | Same as Map 49 EV022. | Autorun → second entry in `MokiTownPlayersHouse2F_OnFrame`. | `ON_FRAME_TABLE` + `special(HealPlayerParty)`. *Native white-out respawn.* | – |

---

## 4. Map 032 — Moki Town (`MokiTown`)

The big one. 52 events → 26 object events, 3 bg events, 4 coord-event hosts
(18 coord tiles), 10 warp slots (5 source + 5 arrival), 14 not emitted. This
map is also the only one exercising the custom-route movement interpreter.

**Debug history — the most-debugged map in the slice:** ambient movers
(`EV008/010/012/035/048/068–073`) 6 rounds as a group (§11.2); `EV009` 3 rounds
and **still unwalked** (§11.5); `EV074` 2 rounds (§11.7); `EV080`/`EV081`
1 round (§11.9); `EV027` 1 round (§11.10); the 5 doors share §11.4.

### Ambient / scenery

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV001` | Town sign | One msgbox. | none | bg sign + `msgbox`; vanilla analog `LittlerootTown_EventScript_TownSign`. | – |
| `EV004` | Lab sign | One msgbox. | none | bg sign; analog `LittlerootTown_EventScript_BirchsLabSign`. | – |
| `EV011` | Route 03 sign | One msgbox. | none | bg sign + `msgbox` | – |
| `EV008` | Chyinmunk — square patrol | Talk → one cry msgbox. Carries a 26-command RMXP custom route (ring patrol with through-toggles). | **Object + engine route.** Script is the bare page body; the *movement* is `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` with route id 1 in `uranium_move_routes.gen.h`. | Custom engine movement type `0x53` (`event_object_movement.c`, sentinel-fenced). *Natives considered and rejected: `WANDER_AROUND` randomises, `WALK_SEQUENCE_*` can't pause, `LOOK_AROUND`/`WALK_LEFT_AND_RIGHT` can't express the route — 62 % of the corpus doesn't fit (`reference/guides/custom_route_interpreter.md`).* | – |
| `EV010` | Chyinmunk — wanderer | Talk → one cry msgbox. RMXP move_type 1 (random). | none | `MOVEMENT_TYPE_WANDER_AROUND`, range (0,0) = unbounded (the faithful conversion of Essentials' passability-bounded random walk). | – |
| `EV035` | Barewl — wanderer | Talk → one cry msgbox. move_type 1. | none | `MOVEMENT_TYPE_WANDER_AROUND` | – |
| `EV018` | Orchynx scenery mon | No commands. | none | Object event, `MOVEMENT_TYPE_FACE_DOWN`, script body is a bare `end`. | – |
| `EV020` | Eletux scenery mon | No commands. | none | as above (`FACE_LEFT`) | – |
| `EV022` | Raptorch scenery mon | No commands. | none | as above (`FACE_LEFT`) | – |
| `EV021` `EV024` `EV025` `EV030` `EV031` `EV032` `EV034` `EV052` `EV053` `EV054` `EV055` | **Luz** — 11 street-light props | No commands. Single page gated on switch 106 (`FLAG_NIGHT_PEOPLE`); the "animation" is a change-graphic flicker route. | **Not emitted** (`DROP:no_boot_page`) ×11. Even if emitted they'd be static: the flicker is a live graphic swap, which has no script-callable equivalent (`SLICE1_TODO.md` open #6). | Would be object events; no native live-gfx-swap analog (`VAR_OBJ_GFX_ID_x` resolves at spawn only). | – |

### Townsfolk (dialogue + movement)

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV012` | Woman by the ball decoration | P1 = 3-way random flavour line; P2 = one postgame line. | **2 pages → dispatcher** (`FLAG_FINAL_EVENT` → P2, else P1) + `random(3)` inside P1. Movement **demoted to static**: she spawns on an all-exits-blocked RMXP tile (`MapPassability.exit_blocked`), so she never moves on PC either; the emitted `FACE_LEFT` is the *simulated stall facing* from `route_sim.py`, not the page's authored `graphic.direction` (which says DOWN). | Object + dispatcher; `random`/`compare`. | – |
| `EV013` | Man by the pond | P1 = 2-way random line; P2 = one postgame line. | 2 pages → dispatcher + `random(2)`. | Object + dispatcher | – |
| `EV027` | Rare-Candy giver | 4 pages: give a Rare Candy → thank-you line → a second (post-gym) give → a fourth line. | **4 pages → dispatcher** over self-switches A/B and switch 125; each give arm is `giveitem` + `if (VAR_RESULT != 0) setflag(SS)` — the transpiler's give-item idiom. Movement = `URANIUM_CUSTOM_ROUTE` id 2. | `giveitem` (`Common_EventScript_ObtainedItem` under the hood) + dispatcher + custom route. | – |
| `EV048` | Child NPC (east square) | 2 pages, one line each. | Dispatcher on `FLAG_FINAL_EVENT`; movement `URANIUM_CUSTOM_ROUTE` id 3. | Object + dispatcher + custom route | – |
| `EV068` | Townswoman (SE corner) | 2 pages, one line each. | Dispatcher; `URANIUM_CUSTOM_ROUTE` id 4. | as above | – |
| `EV069` | Townsman (mid town) | 2 pages, one line each. | Dispatcher; `URANIUM_CUSTOM_ROUTE` id 5 (shared with EV071 — routes are deduped by the `RouteRegistry`). | as above | – |
| `EV070` | Townsman (south) | 2 pages, one line each. | Dispatcher; `URANIUM_CUSTOM_ROUTE` id 6. | as above | – |
| `EV071` | Townswoman (north) | 2 pages, one line each. | Dispatcher; `URANIUM_CUSTOM_ROUTE` id 5 (deduped). | as above | – |
| `EV072` | Child NPC (SW) | 2 pages, one line each. | Dispatcher; `URANIUM_CUSTOM_ROUTE` id 3 (deduped with EV048). | as above | – |
| `EV073` | Child NPC (SW, by the hedge) | 2 pages, one line each. | Dispatcher; movement **demoted to static** — its walk loop crosses a cell fenced off in Uranium's own data (`MapPassability.cell_clear`), so it stalls on PC too; emitted `FACE_LEFT` is the simulated stall facing, not the authored RIGHT. | Object + dispatcher | – |

### Doors and exits

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV003` | Lab door | P1 = door-open frame cycle + SE + walk-in + transfer to Map 50 (14,18). P2 = the matching arrival walk-out, gated on a temp switch. | **Both pages collapse into one warp.** The door sprite is a `FKdoors1` charset event and is dropped (`DROP:door_sheet`); the 12 transpiled labels (5 movement blocks per page) are pruned from staging. | `warp_events` slots 0 (source) + 6 (arrival). ***Could* be replaced by a native animated door: `MB_ANIMATED_DOOR` + a `sDoorAnimGraphicsTable` entry per door (`engine/src/field_door.c`) — scoped and deliberately skipped 2026-07-16 (`SLICE1_TODO.md` Done #8); a table entry is mandatory or the animation silently no-ops.** | – |
| `EV005` | Player's-house door | Same pattern (`PU-doorsdew` sheet) → Map 49 (10,9). | as EV003 | `warp_events` slots 1 + 5 | – |
| `EV006` | House-2 door | Same pattern → Map 64 (9,12). | as EV003 | `warp_events` slots 2 + 7 | – |
| `EV007` | House-1 door | Same pattern → Map 65 (9,12). | as EV003 | `warp_events` slots 3 + 8 | – |
| `EV017` | Theo's-house door | Same pattern → Map 172 (10,10). | as EV003 | `warp_events` slots 4 + 9 | – |
| `EV023` `EV036` `EV037` | Cave-entrance triad (west edge) | Player-touch transfer to Map 33 (Route 01) via `pbCaveEntrance` + fog settings. | **Not emitted** ×3 (`SKIP:out-of-slice warp`) — Map 33 is the slice-2 frontier. | Would be plain `warp_events`; the fog has no GBA layer and was already being dropped. | – |

### Field-move objects

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV014` | Smashable rock (65,45) | RMXP: HM check → SE → shake route → `pbEraseThisEvent` → `Kernel.pbRockSmashRandomEncounter`, twice (two branch arms). | **Whole RMXP choreography replaced by one native call.** Page 1 body is `goto(EventScript_RockSmash)`; page 2 is the spent `end`. Respawn is the native flag (`FLAG_TEMP_12`) rather than the RMXP self-switch. Tagged `smashable_rock` in `Map032.traits.json`. | **`EventScript_RockSmash`** (`data/scripts/field_move_scripts.inc:64`) — native Emerald, verbatim. | – |
| `EV015` | Smashable rock (66,46) | as EV014 | as EV014, flag `FLAG_TEMP_13` | `EventScript_RockSmash` | – |
| `EV033` | Smashable rock (66,44) | as EV014 | as EV014, flag `FLAG_TEMP_15` | `EventScript_RockSmash` | – |

### Story cutscenes and their actors

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV009` | **Trainer(6)** — catching-tutorial ceremony host | The slice's largest cutscene. P1/P2 = "don't leave without a Pokémon" gate lines; **P3 = the full ceremony** (141 commands: 30 msgboxes, 20 move routes across 4 actors, 2 animations, BGM/ME/SE, a Pokédex grant and a `giveitem` of 5 Poké Balls); P4 = a road-sign line afterwards. | **The deepest chain in the slice.** ① 4 pages → `Map032_EV009_Dispatch`. ② Because the boot page is invisible + event-touch and the event is named `Trainer(6)`, it emits as a **3-tile coord-event ray** at (16,43)–(16,45) rather than an object. ③ P3 opens with a `getplayerxy` early-exit reproducing RMXP's `$game_player.x==17` road-sign fork, then a `y<=43` reposition route. ④ It `addobject`s the two flag-hidden prop actors (76, 77), choreographs them plus actors 16 and 2 through 12 movement blocks + 5 named pose routes, then `removeobject`s them. ⑤ Starter readback: `copyvar(VAR_TEMP_POKEMON_CHOICE, VAR_POKEMONTEST)` + clamp + one literal msgbox per starter. ⑥ Ends by setting `VAR_QUEST_LOG = 4`. | `coord_events` ray; `applymovement`/`waitmovement`; `Common_Movement_ExclamationMark` for the RMXP "Rustle" animation; **Pokédex grant = `setflag(FLAG_SYS_POKEDEX_GET)` + `special(SetUnlockedPokedexFlags)`, the Birch/Oak-lab pattern (`LittlerootTown_ProfessorBirchsLab/scripts.inc:547`)**; `giveitem(ITEM_POKE_BALL, 5)`. *Not available: live graphic swap (RMXP change-graphic routes) and an overworld attack animation — both dropped, poses kept.* | **yes** |
| `EV074` | **Trainer(5)** — rival intro tripwire | 34 commands: an off-screen shout, BGM change, two `while` loops that walk the player onto the trigger row, an emote, one long msgbox, the actor's run-off route, then two self-switch sets. | ① Boot page is invisible + event-touch, name `Trainer(5)` → **5-tile coord ray** at (26,13)–(26,17). ② Dispatcher over 3 pages. ③ The RMXP alignment loops become real `while (var(VAR_TEMP_1) …) applymovement` loops. ④ Drives hidden actor 75 (EV075) — the `addobject`/`removeobject` bracket around it used to be the *entire* delta of a hand file. | `coord_events` ray + `applymovement` + `Common_Movement_ExclamationMark`. | **removed** — `Map032_EV074.pory` existed 2026-07-17 (commit `a64f579f`) and was deleted in `b8e15294` once `hidden_actor_bracket.py` reproduced it automatically. |
| `EV075` | Theo75 — hidden rival actor | No commands. | **Actor-only.** Boot page is opacity-0 on an action trigger → `DROP:opacity0`, but EV074 targets it, so the required-actor pass places it as a flag-hidden object (`FLAG_TEMP_16`) with an `ON_TRANSITION` entry. | Object event + visibility flag + `addobject`/`removeobject`; vanilla analog `FLAG_HIDE_*`. | – |
| `EV076` | Chyinmunk76 — ceremony prop | No commands. | Actor-only, `FLAG_TEMP_17`; spawned/despawned inside EV009 P3. | as EV075 | – |
| `EV077` | Starter77 — ceremony prop | No commands. | Actor-only, `FLAG_TEMP_18`; spawned/despawned inside EV009 P3. Its per-starter graphic swap is the unsupported live-swap case. | as EV075 | – |
| `EV002` | Theo — ceremony-site actor | No commands. Pages gated on `VAR_QUEST_LOG ≥ 2` / `≥ 4`. | Actor-only, `FLAG_TEMP_11`; `ON_TRANSITION` clears it while `2 ≤ VAR_QUEST_LOG < 4`. | Object + visibility flag | – |
| `EV016` | Bambo — ceremony-site actor | No commands. Pages gated on `VAR_QUEST_LOG ≥ 1` / `≥ 4`. | Actor-only, `FLAG_TEMP_14`; `ON_TRANSITION` window `1 ≤ VAR_QUEST_LOG < 4`. Target of EV009 P3's routes (local id 16). | Object + visibility flag | – |
| `EV078` | **Trainer(6)** — post-gym-1 tripwire | 35 commands: player-alignment `while` loops, emote, 2 msgboxes, actor walk-in, fade, then a transfer into the lab (Map 50, 14,7). | ① `Trainer(6)` + invisible boot page → **6-tile coord ray** at (27,43)–(27,48). ② Gated on switch 55 (`FLAG_DEFEATED_GYM1_LEADER`). ③ Drives hidden actor 79 (EV079). ④ Ends in a scripted `warp`, not a warp event. **This event was silently dropped before the 2026-07-17 tripwire fix** (no page held at boot → `select_boot_page` returned `None`); the `Trainer(N)` stand-in-page rule recovered it. | `coord_events` ray + `warp` + `waitstate` | – |
| `EV079` | BamboAfterGym — actor | No commands. | Actor-only, `FLAG_TEMP_19`, `ON_TRANSITION` gated on `FLAG_DEFEATED_GYM1_LEADER && !SSA`. | Object + visibility flag | – |
| `EV080` | **Trainer(4)** — postgame tripwire | 39 commands, same tripwire shape as EV074 (alignment loops, emote, 8 msgboxes, actor arrive/leave routes). Gated on switch 125. | 4-tile coord ray at (31,32)–(31,35); dispatcher; drives hidden actor 81. Also recovered by the `Trainer(N)` stand-in-page rule. | `coord_events` ray + `applymovement` | – |
| `EV081` | TheoChamp — actor | No commands. | Actor-only, `FLAG_TEMP_1A`, `ON_TRANSITION` gated on switch 125. **This actor was the boot-time false-fire fixed in round 3 of the 2026-07-17 walks** — `build_page_dispatcher` never checked page 0's own condition. | Object + visibility flag | – |

---

## 5. Map 050 — Professor's Lab (`MokiTownProfessorLab`)

27 events → 4 object events, 17 bg events, 1 coord-event host (8 tiles), 1
source warp, 3 `ON_FRAME` autoruns, 2 not emitted. Both remaining hand files
live here.

**Debug history — the most expensive events in the slice live here:** `EV019`
~8 rounds and **still pending retest** (§11.1); `EV005` 5 rounds for the quiz
(§11.3) plus 2 more for its autorun page (§11.6); `EV026` is an **open,
never-reported defect** (§11.11).

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV001` | Lab door → Moki Town | P1 = "get your Pokémon first" refusal + push-back route; P2 (once `VAR_QUEST_LOG ≥ 1`) = the transfer to Moki Town (17,11). | **2 pages → one warp**; the refusal gate is lost, same as Map 49 EV002. | `warp_events` slot 0 → `MAP_MOKI_TOWN` arrival warp 6 | – |
| `EV002` | **Trainer(10)** — exit tripwire | One msgbox + a push-back route: stops you leaving before the ceremony. | `Trainer(10)` + invisible event-touch boot page → an **8-tile coord ray** along y=16 (11,16)…(17,16) and (20,16); tiles 18–19 are unstandable and dropped. Dispatcher over 2 pages (P2 = spent). | `coord_events` + `applymovement`. *Native trainer sight (`TRAINER_TYPE_NORMAL` + `trainer_sight_or_berry_tree_id` radius) exists but is for real battle trainers; a cutscene tripwire is correctly a coord event.* | – |
| `EV003` | Potted plant | One msgbox. | none | bg sign + `msgbox` | – |
| `EV004` | **Aide** | 3 pages: pre-test explanation of the aptitude test (6 msgboxes), a one-line filler, and a long postgame Poké-Radar tutorial with 2 choice menus and a label/jump loop. | 3 pages → dispatcher (`FLAG_FINAL_EVENT` → P3, `VAR_QUEST_LOG ≥ 1` → P2, else P1). P3's RMXP label/jump pair is one of only two unhandled-queue entries on this map. | Object + dispatcher + `msgbox`; choices → `dynmultichoice`. | – |
| `EV005` | **Bambo** — aptitude test | 8 pages, 112 + 114-command bodies. P1 is the autorun lab-intro scene → the 4-question aptitude test → argmax scoring → starter announcement. P2/P3 are re-offer/retake arms; P4–P8 are later-game Pokédex-evaluation pages. | **The most heavily chained event in the slice.** ① 8 pages → `Map050_EV005_Dispatch`, *and* P1 is an autorun so it also has an `ON_FRAME` entry with a 6-term guard. ② P1's yes-arm and P3's retake arm both `goto(Map050_EV005_TestBody)` — the RMXP label collapsed into a shared script. ③ `TestBody` runs 4 × (`msgbox` → `dynmultichoice` → `copyvar` → `call(Map050_EV005_Tally)`); `Tally` is a `switch` that bumps one of three scratch vars. ④ Argmax is done as u16 subtract-and-test-sign (`subvar` + `compare` against **32767**, not 32768 — 0x8000 collides with `VAR_0x8000`, the bug that made every quiz resolve to one starter). ⑤ Result written 0-based to `VAR_POKEMONTEST`, then `+1` on accept so EV019 can read it 1-based. ⑥ Ends with an explicit `releaseall` (P1's `lockall` epilogue is skipped by the `goto`). | `dynmultichoice` (expansion; vanilla analog `multichoice`) + `call`/`return` + `switch` + `subvar`. *Uranium's `pbStarterSelector` fullscreen reveal has no analog — replaced by an announcement `msgbox`.* | **yes** |
| `EV006` `EV007` | Wall map ×2 | msgbox + `pbShowMap`. | none | `special(FieldShowRegionMap)` | – |
| `EV008` | Papers on the wall | One msgbox. | none | bg sign + `msgbox` | – |
| `EV009` | Healing machine (left) | P1 = description line. P2 (once `FLAG_RECEIVED_STARTER`) = description + yes/no + full heal with fade sequence. | 2 pages → dispatcher; P2's choice = `yesnobox` + `VAR_RESULT`. | bg sign + dispatcher + `special(HealPlayerParty)`. ***Could be `Common_EventScript_PkmnCenterNurse`*** (`data/scripts/pkmn_center_nurse.inc`), which does the fade/jingle natively. | – |
| `EV010` `EV011` `EV012` `EV016` | Book cases ×4 | One msgbox each (same text). | none | bg sign + `msgbox`. *`EventScript_BookShelf`.* | – |
| `EV013` | Potted plant | One msgbox. | none | bg sign + `msgbox` | – |
| `EV014` | Wall notices | One msgbox. | none | bg sign + `msgbox` | – |
| `EV015` | Window | One msgbox. | none | bg sign + `msgbox` | – |
| `EV017` `EV018` | machine-invi ×2 | No commands; opacity-0 blocker tiles flanking the ball machine. | Emitted as **empty bg events** (blank graphic + action trigger) whose body is a bare `end`. | bg event with an `end` script. *Their real job (blocking the tiles) is done by the layout collision stamp, not the event.* | – |
| `EV019` | **Machine** — starter grant + rival battle | 170 commands on page 1: the starter grant, the rival's counter-pick, a walk-up, the first trainer battle, both outcome arms, the actor's exit, and the professor's send-off. Pages 2/3 are spent no-ops. | **Hand-authored chain.** ① 3 pages → dispatcher. ② `switch (VAR_POKEMONTEST)` → `givemon(SPECIES_ORCHYNX/RAPTORCH/ELETUX, 5)` + a `FLAG_HAS_*`, with a `default:` early-out (added after a sequence-break bug when the var was still 0). ③ `setflag(FLAG_SYS_POKEMON_GET)` — Emerald gates the START-menu party on it; Essentials has no equivalent, so `givemon` alone left the party invisible. ④ Second `switch` announces the rival's counter-pick. ⑤ Third `switch` runs `trainerbattle_earlyrival(TRAINER_THEO_9/10/11, RIVAL_BATTLE_HEAL_AFTER, …)`. ⑥ `VAR_RESULT` is read immediately after and mirrored into `FLAG_LOST_FIRST_BATTLE`, which Map 172 EV004 branches on. ⑦ Exit route + send-off + `VAR_QUEST_LOG += 1` + `FLAG_RECEIVED_STARTER`. | `givemon` (Birch-lab starter pattern); **`trainerbattle_earlyrival` + `RIVAL_BATTLE_HEAL_AFTER`** (`asm/macros/event.inc:828`, `include/constants/battle.h:130`) — the FRLG Oak's-lab losable rival battle. *Do **not** use `RIVAL_BATTLE_TUTORIAL`: it adds `BATTLE_TYPE_FIRST_BATTLE`, which reroutes the loss text into the FRLG Oak voiceover and hangs (`SLICE1_TODO.md` 2026-07-22 entry).* Vanilla Emerald's own analog would be the Route 103 rival's `trainerbattle_no_intro`, which cannot be lost. | **yes** |
| `EV020` | Theo — lab actor | P1 = one line; P2 spent once `VAR_QUEST_LOG ≥ 1`. | 2 pages → dispatcher. Also the movement target (local id 4) of EV019's choreography. | Object + dispatcher | – |
| `EV021` | Healing machine (right) | Identical to EV009. | 2 pages → dispatcher; `yesnobox` + heal. | as EV009 | – |
| `EV022` | Postgame Cutscene | 57-command postgame autorun (24 msgboxes, 2 move routes, 4 branches), gated on switch 125. | Autorun → second entry in `MokiTownProfessorLab_OnFrame`. Not an object. | `ON_FRAME_TABLE` + `applymovement` | – |
| `EV023` | bub | No commands. | Empty bg event (`end`). | bg event | – |
| `EV024` | LilyHazma — purification NPC | 30 commands: yes/no + a party-selection script call + a cure sequence. Single page gated on switch 125. | **Not emitted** (`DROP:no_boot_page`); body pruned. Its `pbChooseNuclearCurePokemon` and `\v[3]` text codes are the map's other unhandled-queue entries. | Would be object + `yesnobox`; the party-selection UI has no analog yet (Phase-6 nuclear-type work, `reference/guides/nuclear_type_spec.md`). | – |
| `EV025` | Hazma — pet mon | One cry msgbox. Single page gated on switch 125. | **Not emitted** (`DROP:no_boot_page`). | Would be object + `msgbox`. | – |
| `EV026` | Lab PC | RMXP `pbPokeCenterPC` behind a facing check. | Emitted as a bg event whose body is just `release`/`end` — the facing conditional (code 111 on character facing) is unhandled, so the PC call inside it was not emitted. | *Should be `goto(EventScript_PC)`, like Map 48 EV004.* **Known gap.** | – |
| `EV027` | Post-gym-1 briefing | 23-command autorun (14 msgboxes + `giveitem(ITEM_POKE_BALL, 10)`), gated on switch 55. | Autorun → third entry in `MokiTownProfessorLab_OnFrame`; 3 pages, P2/P3 spent. Two Pokédex-count script calls are unhandled and commented out. | `ON_FRAME_TABLE` + `giveitem` | – |

---

## 6. Map 064 — Moki Town House 2 (`MokiTownHouse2`)

4 events → 3 object events, 1 source warp.

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV001` | Householder (man) | 2 pages × 2 alternating lines each. | **Dispatcher + toggle.** Dispatcher picks P1/P2 on `FLAG_FINAL_EVENT`; inside each page an `if (!flag(SSA)) … setflag else … clearflag` alternates the line on repeat talks — the transpiler's self-switch-toggle idiom. | Object + dispatcher + `setflag`/`clearflag` | – |
| `EV002` | Householder (woman) | Same 2-page × 2-line shape. | as EV001 | as EV001 | – |
| `EV003` | Front door → Moki Town | Player-touch transfer to Moki Town (43,31). | Single page → one warp. | `warp_events` slot 0 → `MAP_MOKI_TOWN` arrival warp 7 | – |
| `EV004` | Chyinmunk (pet) | One cry msgbox + SE. Carries a 26-command RMXP route, but on RMXP `move_type 0` (fixed) — the route is authored and never run. | Static by construction, not by demotion: `movement_spec_for` only reads a route when `move_type == 3`, so this emits `FACE_DOWN` from the page graphic. The SE is a dropped audio comment. | Object + `msgbox` | – |

---

## 7. Map 065 — Moki Town House 1 (`MokiTownHouse1`)

3 events → 2 object events, 1 source warp.

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV001` | Child NPC | 2 pages × 2 alternating lines. | Dispatcher on `FLAG_FINAL_EVENT` + self-switch toggle inside each page. | Object + dispatcher | – |
| `EV002` | Parent NPC | Same shape. | as EV001 | as EV001 | – |
| `EV003` | Front door → Moki Town | Player-touch transfer to Moki Town (24,42). | Single page → one warp. | `warp_events` slot 0 → `MAP_MOKI_TOWN` arrival warp 8 | – |

---

## 8. Map 172 — Theo's House 1F (`MokiTownTheo172`)

4 events → 2 object events, 2 warp slots + 1 arrival, 2 `ON_FRAME` entries
(both from the same event).

**Debug history:** `EV004` 2 rounds, **retest pending** (§11.8). Because it
carries the `var101 = 2` write, its first-round failure blocked the entire quest
chain.

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV001` | **Cam** | 4 pages: a 4-msgbox intro, a 4-msgbox send-off (`VAR_QUEST_LOG ≥ 2`), a spent page, and an 11-msgbox rotating-counter page (switch 125). | 4 pages → dispatcher; P4 uses the same 4-state counter pattern as Map 49 EV020, and the same unsatisfiable numeric guard was dropped with an in-line note. | Object + dispatcher + `compare`/`goto_if` | – |
| `EV002` | Front door → Moki Town | Player-touch transfer to Moki Town (56,42). | Single page → one warp. | `warp_events` slot 0 → `MAP_MOKI_TOWN` arrival warp 9 | – |
| `EV003` | Stairs → 2F | Player-touch transfer to Map 89 (4,3) with a diagonal step-up. | Single page → one warp. | `warp_events` slot 1 → `MOKI_TOWN_THEO` arrival warp 1 | – |
| `EV004` | **Theo** — house cutscene | Two full autorun cutscenes on one event. P1 (121 commands) is the post-battle scene, which **branches on `FLAG_LOST_FIRST_BATTLE`** into two completely different choreographies before converging on a shared item-grant tail; P3 (124 commands) is the postgame variant. P2/P4 are spent. | **Autorun + actor at once.** ① It is a required actor, so it also emits as a flag-hidden object (`FLAG_TEMP_11`) with an `ON_TRANSITION` gate. ② `MokiTownTheo172_OnFrame` has **two** entries: P1 under `1 ≤ VAR_QUEST_LOG < 2 && !FLAG_FINAL_EVENT && !SSA`, P3 under `FLAG_FINAL_EVENT && !SSA`. ③ P1's branch reads the flag EV019 wrote after the rival battle. ④ 19 movement blocks on P1 alone, driving actors 1 and 4 plus the player; a `yesnobox` sits inside the lose arm. ⑤ Ends with `VAR_QUEST_LOG = 2`. | `ON_FRAME_TABLE` + `applymovement` + `yesnobox` + `Common_Movement_ExclamationMark`. Five code-202 `Set Event Location` commands and 2 animations are unhandled here (the map's only queue entries). | – |

---

## 9. Map 089 — Theo's House 2F (`MokiTownTheo`)

6 events → 0 object events, 5 bg events, 1 source warp. Reachable only through
Map 172's internal stairs.

| Label | Name | What it does | Chain | Emerald analog | Hand |
|---|---|---|---|---|---|
| `EV002` | Stairs → 1F | Player-touch transfer to Map 172 (11,3) with a diagonal step-down. | Single page → one warp. | `warp_events` slot 0 → `MOKI_TOWN_THEO_172` arrival warp 3 | – |
| `EV003` | Wall map (right) | msgbox + `pbShowMap`. | none | `special(FieldShowRegionMap)` | – |
| `EV004` | Computer | 2 msgboxes → yes/no → one of two msgboxes. | Choice chain inside one page: `yesnobox` + `VAR_RESULT` branch. | bg sign + `yesnobox` | – |
| `EV005` | Wall map (left) | Same as EV003. | none | `special(FieldShowRegionMap)` | – |
| `EV006` | TV | 2 msgboxes. | none | bg sign + `msgbox`. *`EventScript_TV`.* | – |
| `EV007` | Games console | One msgbox. | none | bg sign + `msgbox` | – |

---

## 10. Hand-authoring history

`src/rpg2gba/conversion_agent/hand_conversions/` is the only hand-authoring
path in the pipeline (`hand_overrides.py`, loaded by
`transpile_driver.transpile_map`); a file there is the event's **entire**
output — the driver never merges hand and generated content for one event.
Hand output is not exempt from the fork-index gate, `make modern`, or the §9
boot gate.

| Event | Added | Why it needed hands | Status |
|---|---|---|---|
| `Map032_EV009` | `4b0e551a` (2026-07-05), revised `f8803c6d`, `a64f579f` | The catching-tutorial ceremony: a `$game_player.x` fork, a player-reposition route, an array-indexed starter readback, RMXP change-graphic routes with no fork-native live swap, and two overworld animations with no analog. | **current** |
| `Map049_EV021` | `4b0e551a` (2026-07-05), revised `f8803c6d` | `displayNinjaLetter` is a bespoke full-screen letter-card scene (`reference/scripts_dump/221_Extra_Scripts.rb:457`) with no Poryscript analog, plus a code-202 actor teleport. | **current** |
| `Map050_EV005` | `b8e15294` (2026-07-17), revised `2b045012`, `b3b1b623`, `80963f9e` | The aptitude test's scoring is novel embedded Ruby: an array in `$game_variables[151]`, a per-answer tally, an argmax with a 0↔1 swap, and `pbStarterSelector`. | **current** |
| `Map050_EV019` | `b8e15294` (2026-07-17), revised `2b045012`, `ad70308a`, `9971428e` | The starter grant + rival counter-pick are novel embedded Ruby, and the rival battle needed the `trainerbattle_earlyrival` mapping plus its `RIVAL_BATTLE_HEAL_AFTER` engine fix. | **current** |
| `Map032_EV074` | `a64f579f` (2026-07-17) | Its **only** delta from transpiler output was `addobject(75)`/`removeobject(75)` around the hidden actor's routes. | **removed** in `b8e15294` — `tileset_converter/hidden_actor_bracket.py` now derives the bracket from the visibility-flag pool and reproduces the file exactly. |

---

## 11. Debug history

> **Reconstructed, not recorded.** Nothing in this repo tracks debugging effort
> per event. The rounds below are rebuilt from three independent traces: ROM
> hashes cited in `SLICE1_TODO.md` / `MEMORY.md` / `BOOT_WALK_CHECKLIST.md`, the
> named ROM artifacts still in `output/uranium-build/`, and commits touching each
> event. **A "round" = one build → taildrop → on-device retest cycle**, which is
> the unit the process actually works in — not a work session (one session often
> produced several ROMs; two threads spanned sessions). Two known biases: ROM
> artifacts on disk only go back to 2026-07-16, so pre-07-16 counts come from the
> docs alone and are probably low; and several 07-22 ROMs are *instrumentation
> rigs* (`-losetest`, `-harness`), not fix attempts, so EV019's count overstates
> fixes and understates builds.

### Summary

| Thread | Events | Rounds | Status |
|---|---|---|---|
| §11.1 Rival battle + starter grant | `Map050_EV019` | **~8** | **retest pending** |
| §11.2 Ambient NPC movement | `Map032_EV008/010/012/035/048/068–073` | **6** | verified `5158b084`; one refinement pending |
| §11.3 Aptitude test | `Map050_EV005` | **5** | PASS 2026-07-21 |
| §11.4 Warp-arrival facing | all 14 warps | **3 approaches** | PASS 2026-07-16 |
| §11.5 Pokédex ceremony | `Map032_EV009` | **3** | **never walked**; 1 open defect |
| §11.6 Lab intro autorun | `Map050_EV005` p1 | **2** | PASS 2026-07-17 |
| §11.7 Rival trip tile | `Map032_EV074` | **2** | PASS 2026-07-17 |
| §11.8 PokéPod scene | `Map172_EV004` | **2** | **retest pending** |
| §11.9 Postgame tripwire misfire | `Map032_EV080/EV081` | **1** | PASS 2026-07-17 |
| §11.10 Repeated NPC dialogue | `Map049_EV001`, `Map032_EV027` | **1** | verified 2026-07-11 |
| §11.11 Dead lab PC | `Map050_EV026` | **0** | **open, unreported** |
| — | the other **96** events | **0** | passed first walk |

**Coverage:** 11 threads over **21 events** with an event-specific history, plus
**14 warps** hit at once by the one cross-cutting thread (§11.4) — 35 of 131
events touched, **96 never needing a round at all**. Concentration is sharper
than the headcount suggests: `Map050_EV019` alone burned more cycles than every
other thread combined, and the 11-event movers thread (§11.2) was one bug class
fixed six times, not eleven separate investigations.

### 11.1 `Map050_EV019` — rival battle + starter grant (~8 rounds, still pending)

**Initially:** the rival battle wasn't converted at all. The RMXP source ran
`pbTrainerBattle(...,canlose)` inside a code-111 branch; the first build
(`b8e15294`, ROM `6e85edb3`) emitted the surrounding scene and commented the
battle out, so the scene converged to the professor's farewell either way. The
starters were Emerald stand-ins (TREECKO/TORCHIC/MUDKIP).

**Then, in order:**

1. **Real species land** (`2b045012`, 07-19/20) — and the walk finds three
   separate bugs in this one event. *(a)* The lab NPCs froze after the quiz:
   page 1 opens `lockall` and the accept path `goto`s `TestBody`, skipping the
   shared `releaseall` epilogue — player controls auto-unlock at script end, but
   object freeze does not. *(b)* `switch (VAR_POKEMONTEST)` had no `default:`
   arm, so before the test (var still 0) the switch matched nothing and **fell
   through into the entire rival cutscene** — bumping `VAR_QUEST_LOG` and setting
   `FLAG_RECEIVED_STARTER` with no starter granted, a clean sequence break.
   *(c)* `givemon` adds to `gPlayerParty` but never sets `FLAG_SYS_POKEMON_GET`,
   which Emerald gates the START-menu party on (`start_menu.c:340`) — the starter
   was in the party but had no menu slot. Essentials has no equivalent gate;
   this is a general Essentials→Emerald pairing gap, now Phase-7 debt.
2. **Battle emitted** (`3893aac7` + `ad70308a`, ROM `51be1e63`, 07-21) — mapped
   to `trainerbattle_earlyrival` + `RIVAL_BATTLE_HEAL_AFTER`. **Win path PASSED.**
   Also fixed the stranded-sprite bug: the rival's walk-off had lived *inside*
   the un-emitted battle branch, so his sprite used to strand beside the machine.
3. **Loss path freezes.** Losing hangs on the last line as the screen begins
   fading to black. Two instrumentation ROMs (`5869e037` no-Geodude,
   `9ce7da5a` Body-Slam) exist purely to make losing reproducible, plus
   `7dae4f4b` for the outcome flag.
4. **First fix treats a symptom** (`9971428e`, ROMs `6da41f93` / `56bdd086`,
   07-21) — added `HEAL_AFTER` + `waitmessage`. Still froze. The `waitmessage`
   was waiting on a print controller that never signals done.
5. **Real root cause** (`e84b8d0a`, ROM `f5867449`, 07-22): `RIVAL_BATTLE_HEAL_AFTER`
   is `1` (`0b01`) and `RIVAL_BATTLE_TUTORIAL` is `3` (`0b11`), so the mask at
   `battle_setup.c:1322` — `GetRivalBattleFlags() & RIVAL_BATTLE_TUTORIAL` — is
   **truthy for HEAL_AFTER too**. The battle therefore got
   `BATTLE_TYPE_FIRST_BATTLE`, and on a loss `battle_controllers.c:2658` reroutes
   the trainer win-text into the FRLG Oak "How disappointing" voiceover, which
   `BeginNormalPaletteFade(..., RGB_BLACK)`s and then waits on Oak-controller
   state that doesn't exist in a normal trainer battle → fade to black, hang.
   Fix: require the **full** flag (`(flags & TUTORIAL) == TUTORIAL`), fenced
   `URANIUM PATHFINDER SLICE`. Zero reachable vanilla impact — only FRLG uses
   `earlyrival`, always with `TUTORIAL` or `0`.
6. **Post-quiz cleanup** (07-22): four more ROMs (`fd90ff8f`, `6daee71c`,
   `65e34b3e`, `3f75336681`) covering the repro harness, actor spawning and the
   professor's exit move; `64bb697b` tears the test rig back down.

**Status: retest pending.** The win path is signed off (S6b); the loss path fix
has never been walked.

**What made it expensive:** the failure was in engine C two layers below the
converted script, the loss path needed a purpose-built rig to reproduce at all,
and two plausible-looking fixes shipped before the flag-mask bug was found.

### 11.2 Ambient NPC movement — `Map032` townsfolk (6 rounds)

**Initially:** every NPC in Moki Town stood frozen.

1. **Research corrects the premise** (`a87a406f`, 07-13). The assumed cause
   (move_type 1) was wrong: `npc_gfx.movement_type_for` already mapped type 1 →
   `WANDER_AROUND`, but collapsed 0/2/3 → static `FACE_<dir>`. Moki's life is
   almost all **move_type 3 (custom route)**. Corpus census: 7342 pages type 0,
   22 type 1, **0 type 2**, 1065 type 3.
2. **Route classifier lands** (`0e41c259`, 07-13) — type-3 routes classified into
   native `WALK_LEFT_AND_RIGHT` / `WALK_UP_AND_DOWN` / `LOOK_AROUND` / static.
   Walk verdict: *"NPCs move now but need fine-tuning."*
3. **Fine-tune round** (ROM `a107c65c`, 07-15) — three new rules: freq-gated
   pacing (pacers never paused; RMXP idle-gates every route command by
   `(40−2f)(6−f)` frames), 4-leg closed loops → `WALK_SEQUENCE_*`, and
   map-passability gates. That last one explained a reported "itemball I can't
   pick up, and an NPC bumping into it" — the ball is **map art** the NPC's
   sprite covers, and the NPC stands on an all-exits-blocked tile so she never
   moves on PC either.
4. **Approach abandoned** (ROM `7b290f02`, 07-15). A census killed it: 834 custom
   routes corpus-wide, **62 % not natively expressible** — `WANDER` randomises
   where Uranium is deterministic, `WALK_SEQUENCE` can't pause or do variable
   legs, `COMPLEX` demotes to static. Replaced by one new engine movement type
   (`MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`, `0x53`) that plays a per-object route
   bytecode.
5. **Interpreter ships broken** (ROM `66097603`, 07-15). Walk: *"no NPC moves
   until you talk to them, then one step per talk."* Two engine bugs. The minor
   one: missing `singleMovementActive = TRUE/FALSE` around the single movement.
   The **root cause**: a sprite-data slot collision — the FSM kept its program
   counter in `data[4]` and through-flag in `data[5]`, but the normal-walk action
   (`SetSpriteDataForNormalStep` → `NpcTakeStep`) reuses `data[4]` as `sSpeed` and
   `data[5]` as `sTimer`. So the first step ran, the walk overwrote the PC, and
   only an interaction force-tick advanced it. Fix: pack PC + through into
   `data[6]`, the only slot safe across both a walk and a wait. Also clamped
   idle ≥ 1 — freq-6 routes emit idle 0 and `WaitForMovementDelay`'s
   pre-decrement underflows to a ~65 000-frame stall.
6. **Clean walk** (ROM `5158b084`, 07-15) — *"looks great, movement issue is
   done."* **User-verified done.**
7. **Refinement** (`70231143`, ROM `332f30e8`, 07-16): three residual complaints
   (EV012 faced DOWN not LEFT, EV073 walked when it should stand, EV008's patrol
   reshaped when the player blocked it) turned out to be **one** root cause — RMXP
   blocked-move semantics were never modelled. `move_*` turns **before** the
   `passable?` check, and a non-skippable blocked move stalls forever facing the
   blocked direction without animating. Fix: `route_sim.py` + `static_face_spec(facing=)`,
   so a demoted mover's facing is the *simulated stall facing*, not the authored
   `graphic.direction`. **Retest pending.**

### 11.3 `Map050_EV005` — aptitude test (5 rounds, PASS)

**Initially:** built 07-17 (`b8e15294`, ROM `6e85edb3`) with the `\ch`
inline-choice transpiler support + a hand tail for scoring, against Emerald
stand-in starters.

- **Quiz-retake soft-lock** (07-19/20, `2b045012`): a stale `ON_FRAME` latch left
  the retake path dead. General fix — `metadata_wiring.insert_onframe_rearms`
  re-arms the dispatch whenever an autorun guard input changes.
- **The quiz always resolved to Eletux** regardless of answers (found in the
  07-21 walk, fixed in `b3b1b623`, ROM `b0b21993`). Root cause is a genuinely
  nasty one: the argmax sign-test compared against the literal `32768` = `0x8000`,
  which is `SPECIAL_VARS_START`. The `compare` asm macro auto-selects
  `compare_var_to_var` vs `compare_var_to_value` by whether the literal falls in
  `[0x8000, 0x8015]` — so `< 32768` **silently compiled to "compare against the
  value stored in `VAR_0x8000`"**, the engine's own switch-statement scratch var,
  which the per-question `Tally` switch had just left holding the last answer
  index. Every override compared a 0–4 tally delta against a 0–2 leftover, never
  matched, and the result stayed at its hardcoded default. Fix: use `32767`.

**Status: S6 PASSED 2026-07-21** — user confirmed all four answer combinations
resolve correctly.

### 11.4 Warp-arrival facing — all 14 warps (3 approaches, PASS)

**Initially:** post-warp facing was always DOWN.

- **Option A** (`b7c5b8d7`) — stamp native `MB_*_ARROW_WARP` metatile behaviours.
  Got 3 of 4 directions working, then the fourth hijacked `TryArrowWarp` and
  stairs re-triggered. **Structurally dead**, not case-specific.
- **Option B** — add an `arrivalDirection` field to `struct WarpEvent`
  (end-to-end schema change: struct, `warp_def` macro, `mapjson.cpp`). It was
  independently code-reviewed byte-for-byte correct — and the device retest showed
  *"warps completely broken."* **Four** from-scratch rebuilds reproduced
  byte-identical, previously-verified-correct warp data while the user still saw
  it broken. Rolled back `--hard`. Later diagnosis: `struct WarpEvent` is exactly
  8 bytes, fully packed; +1 `u8` → 9 → padded to 10 at align-2, and any
  struct/macro stride disagreement walks the warp table wrong and silently kills
  every warp. **Do not re-attempt.** One real bug was found en route and kept:
  `engine/map_data_rules.mk` never listed the `mapjson` binary as a prerequisite,
  so an engine-only rebuild could silently skip regenerating stale per-map data.
- **Option C** (`e520c529`, ROM `e035dac1`, 07-16) — **data-only, zero engine
  change**: native `MAP_SCRIPT_ON_WARP_INTO_MAP_TABLE` + `turnobject`, dispatched
  on the player's landing coords via `getplayerxy`. `map_scripts.h:22-24`
  documents this hook's purpose verbatim as *"update something about the player
  as they warp in (e.g. their facing dir)."* **PASSED.**

**The lesson, recorded at the time:** both failed attempts changed *engine/schema*
surface to carry converter data; the one that worked carried it in **generated
script data**. Prefer the data-only seam when the fork already ships a hook — and
read `map_scripts.h`'s own doc comments before assuming a hook doesn't exist.

### 11.5 `Map032_EV009` — Pokédex ceremony (3 rounds, never walked)

**Initially:** hand-authored 07-05, revised 07-13 for NPC graphics. Two bugs were
then found by *reading*, not walking (findings doc, 07-16):

- **Bug C — `applymovement` silently drove the wrong NPCs.** The hand file
  choreographed RMXP event ids 16, 2, 76 and 77, but `applymovement` takes
  **local** ids: local 16 was RMXP EV070 (an unrelated townsfolk across the map),
  local 2 was RMXP EV010 (a wandering Chyinmunk). `Move8` is a 15-step walk
  ending in `set_invisible`, so a random townsfolk would have walked off and
  vanished.
- **Bug D** — the scene ended with `setvar(VAR_AUNTIE_VISIT_STAGE, 4)` instead of
  `VAR_QUEST_LOG`, so the quest log never advanced.

Both fixed in `a64f579f` (07-17), along with the `addobject`/`removeobject`
bracket. Round 2 then found the trigger tile itself was unstandable (see §11.7)
and relocated it to (17,42)/(16,43) — **beat 11 had been silently unreachable
the whole time.**

**Status: still not walked.** S8/S9 are unchecked, and `SLICE1_TODO` #14 records
one known open defect (fires on A-press instead of on entry; the reposition route
walks the player into a black void — the `y<=43` clamp was written for the old
Moki-side ceremony and the Map-50 doorway coords differ).

### 11.6 `Map050_EV005` page 1 — lab intro autorun (2 rounds, PASS)

**Initially (bug B):** the intro fired *on talking to the professor*, not on
entering the lab. A visible-graphic autorun page had no channel to run on, so the
converter emitted the page body as the object's talk script. Fixed 07-17 round 1
by the unified `render_map_scripts` + `compute_autorun_entries` pass, which
reproduces RMXP page activation into `ON_FRAME_TABLE` entries.

**Round 2 (ROM `762e98aa`):** the intro then **looped forever** — dialogue
restarted and the player walked through a wall. Root cause: `_emit_choice` only
handled a literal `["YES","NO"]` pair. The scene's `["Yes!", "Wait a minute..."]`
choice went to the unhandled queue as a comment, **dropping both arms** — and
those arms held the self-switch C/D deactivation writes, so the `ON_FRAME` guard
`!SSC && !SSD` never flipped and the dispatcher re-fired page 1 every frame. Fix:
handle any exactly-2-arm choice via `yesnobox` (custom labels degrade to YES/NO,
a known cosmetic loss). That unlocked 7 yesnoboxes across the slice.

**The durable win:** a new staging invariant, `check_onframe_deactivation` — every
`ON_FRAME`-dispatched page body must write at least one flag/var appearing in that
map's OnFrame guards, or the build fails. It catches the exact shipped bug class
(dropped deactivation → ROM loop) at build time.

**Status: S3/S4/S5 PASS** on `c9128e58`.

### 11.7 `Map032_EV074` — rival trip tile (2 rounds, PASS)

**Initially (bug A):** never fired. First diagnosis blamed a shared coord-event
gate ("every coord event after the first is dead"), fixed in round 1 with a
reserved `VAR_TEMP_F` gate.

**It still didn't fire.** The real cause, found in round 2: tile (26,12) has RMXP
passage `0x0F` — blocked in Uranium too, and faithfully converted to collision=1
on GBA. RMXP trigger-1/2 touch fires on a **bump** into a blocked tile; a GBA
`coord_event` fires only when the player **stands on** it. A step-on trigger on an
unstandable tile can never fire. Fix: `metadata_wiring` relocates a blocked-tile
touch trigger to each standable orthogonal neighbour. The findings doc's own
claim that "EV074 converts correctly — right position" was wrong about
reachability, and is annotated as such.

Its hand file was added in the same round and **deleted the next day** once
`hidden_actor_bracket.py` reproduced its only delta automatically.

**Status: S2 PASS** on `c9128e58`.

### 11.8 `Map172_EV004` — PokéPod scene (2 rounds, pending)

**Initially (bug B'):** dropped entirely — same autorun root cause as §11.6, but
the opposite failure mode (blank/opacity-0 page → no object → nothing emitted).
This one mattered structurally: EV004 is the `var101 = 2` write, so **the whole
quest chain could not complete past beat 10.** Fixed 07-17 in `a64f579f`.

**Round 2** (`2aeaa46a`, ROM `8fe9d9ff`, 07-21): the scene fired, but the rival was
**invisible on the win path only.** The hidden-actor auto-bracket had placed its
`addobject` inside the `if (FLAG_LOST_FIRST_BATTLE)` branch, so the `else` (win)
path ran `set_visible` on an actor that was never spawned. Fix:
`hidden_actor_bracket.py` is now branch-aware and spawns the actor on every
execution path.

**Status: retest pending** (S7 unchecked).

### 11.9 `Map032_EV080` / `EV081` — postgame tripwire misfire (1 round, PASS)

**Symptom:** a postgame scene fired **at boot**, right outside the player's house,
with the actor invisible.

**Root cause:** `build_page_dispatcher` never checked RMXP page index 0's *own*
condition — index 0 was always treated as the unconditional fallback. EV080
reached the ROM via round 2's `Trainer(N)` no-boot-page carve-out, which trusts
the dispatcher to gate at runtime; the dispatcher fell straight through to page 1.
The actor looked invisible because the sprite is a separate event (EV081), which
*was* correctly hidden.

**Fix:** the dispatcher now scans high→low **including index 0**, and falls to a
bare `end` when no page matches (RMXP's "no active page" is inert). This silently
fixed EV078 and EV081 too, which were the same class.

**Status: PASS** on `c9128e58` — scene gone.

### 11.10 `Map049_EV001` / `Map032_EV027` — repeated dialogue (1 round, verified)

**Symptom:** NPCs replayed their first-page dialogue forever; story progress never
changed what they said.

**Root cause:** there was no page dispatch at all — the converter emitted page 1's
body as the object's script and ignored the rest of the stack.

**Fix** (`710e258c`, 07-11): page dispatchers for global switch/var gates — the
mechanism §1 describes, and now the backbone of 30 of the slice's 40 object
events. It also flushed out a live bug: `FlagRegistry.load()` never restored
labels, so `label_for_switch` was dead at the staging call site; new
`FlagRegistry.seed_labels()` fixed it.

**Status: user-verified on device 2026-07-11.**

### 11.11 `Map050_EV026` — dead lab PC (0 rounds, open)

Not a debug thread — a defect **found while compiling this document**, never
reported or walked. The lab PC emits a bg event whose body is `lock` / `release` /
`end`: the `pbPokeCenterPC` call sits inside an unhandled code-111
character-facing conditional, so it was never emitted. Interacting with it does
nothing. Map 48's PC works because its call isn't wrapped in a conditional.
Fix is one line — `goto(EventScript_PC)` — but it needs a build and a walk.

### What the shape of this says

- **Cost concentrates in cutscenes, not in volume.** 96 of 131 events (73 %)
  never needed a round; counting only events with an event-specific thread, 110
  of 131 (84 %) were free. Everything expensive was multi-actor, story-gated, or
  crossed into engine C.
- **The first root cause was wrong three times out of ten** (§11.1 twice, §11.2
  once, §11.7 once, §11.5's trigger). In each case the fix was plausible, shipped,
  and disproved by the next walk. That is the real cost driver — not the fixes.
- **Two classes of bug were invisible to the build.** Silent-wrong-target
  (`applymovement` local-vs-RMXP ids, §11.5) and silent-wrong-opcode (the
  `compare` macro's var-vs-literal auto-select, §11.3) both compiled clean and
  passed tests. Both now have guards; neither had one when it shipped.
- **Three fixes generalised past their own event** —
  `check_onframe_deactivation`, `insert_onframe_rearms`, and the branch-aware
  `hidden_actor_bracket` — and one of them deleted a hand file outright.

### Making this real data

The cheap fix is one line per retest round in `BOOT_WALK_CHECKLIST.md` naming the
ROM hash and the event ids that round covered. Everything above had to be
triangulated from three places because that line doesn't exist; with it, this
section would be a query.

---

## 12. Emerald constructs used across the slice

| Native construct | Where it came from | Used by |
|---|---|---|
| `bg_events` (`type: sign`) + `msgbox` | vanilla | 47 flavour events |
| `EventScript_PC` (`data/scripts/pc.inc`) | vanilla | Map 48 EV004 *(Map 50 EV026 should but doesn't)* |
| `EventScript_RockSmash` (`data/scripts/field_move_scripts.inc:64`) | vanilla | Map 32 EV014/015/033 |
| `special(HealPlayerParty)` | vanilla | Map 49 EV001/EV022, Map 48 EV013, Map 50 EV009/EV021 |
| `special(FieldShowRegionMap)` (`src/field_specials.c:1014`) | fork special, unused by vanilla map scripts | Map 48 EV007/008, Map 50 EV006/007, Map 89 EV003/005 |
| `setflag(FLAG_SYS_B_DASH)` | `LittlerootTown_EventScript_SetReceivedRunningShoes` | Map 49 EV001 P1 |
| `setflag(FLAG_SYS_POKEDEX_GET)` + `special(SetUnlockedPokedexFlags)` | `LittlerootTown_ProfessorBirchsLab/scripts.inc:547` | Map 32 EV009 P3 |
| `givemon` + `setflag(FLAG_SYS_POKEMON_GET)` | Birch-lab starter grant | Map 50 EV019 |
| `trainerbattle_earlyrival` + `RIVAL_BATTLE_HEAL_AFTER` | FRLG Oak's-lab rival (`asm/macros/event.inc:828`) | Map 50 EV019 |
| `dynmultichoice` | expansion (vanilla analog: `multichoice`) | Map 50 EV004 P3, EV005 |
| `yesnobox` | vanilla | Map 50 EV009/021/024, Map 89 EV004, Map 172 EV004 |
| `giveitem` | vanilla | Map 32 EV009/EV027, Map 49 EV018, Map 50 EV027 |
| `Common_Movement_ExclamationMark` | vanilla (`data/scripts/movement.inc`) | Map 32 EV009/074/078/080, Map 49 EV018, Map 50 EV019, Map 172 EV004 |
| `warp_events` + arrival warps | vanilla schema, converter-side pairing | 14 source warps |
| `MAP_SCRIPT_ON_FRAME_TABLE` | vanilla (Littleroot intro) | 9 autoruns |
| `MAP_SCRIPT_ON_TRANSITION` visibility flags | vanilla `FLAG_HIDE_*` pattern | 10 hidden/gated actors |
| `MAP_SCRIPT_ON_WARP_INTO_MAP_TABLE` + `turnobject` | vanilla | all 8 maps (arrival facing) |
| `MOVEMENT_TYPE_WANDER_AROUND` | vanilla | Map 32 EV010, EV035 |
| `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` (`0x53`) | **fork addition**, sentinel-fenced | Map 32 EV008/027/048/068/069/070/071/072 (6 deduped routes) |

**Deliberately not used, with reasons on file:**

- `MB_ANIMATED_DOOR` + `sDoorAnimGraphicsTable` for the 5 Moki doors — scoped
  twice, skipped by user decision 2026-07-16 (`SLICE1_TODO.md` Done #8). A
  table entry is mandatory or `GetDoorGraphics` returns `NULL` and the
  animation silently no-ops.
- `MOVEMENT_TYPE_WALK_LEFT_AND_RIGHT` / `WALK_SEQUENCE_*` / `LOOK_AROUND` for
  the townsfolk — built, shipped, then superseded: 62 % of the corpus's custom
  routes aren't natively expressible
  (`reference/guides/custom_route_interpreter.md`).
- `TRAINER_TYPE_NORMAL` sight rays for the `Trainer(N)` events — those are
  cutscene tripwires, not battle trainers; a visible `Trainer(N)` event would
  fail loud today (the native trainer-object path isn't built).
- `Common_EventScript_PkmnCenterNurse` for the lab healing machines — the
  converted script does the fade/heal inline instead. Open cleanup.
