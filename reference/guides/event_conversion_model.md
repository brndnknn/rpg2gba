# Event Conversion Model

How rpg2gba turns one RMXP event into pokeemerald-expansion ROM content: the
page-dispatcher model, coordinate-event rays, the hidden-actor bracket
mechanism, the drop rules, and the RMXP-construct → Emerald-construct mapping.
General teaching/reference material for every slice, not slice-specific data.

**Provenance:** extracted from `SLICE1_EVENTS.md` §1 ("How one RMXP event
becomes ROM content") and §12 ("Emerald constructs used across the slice") —
a slice-1 document, about to be archived — on 2026-08-04. Rewritten to read
as a general guide; slice-1 map/event ids are kept only where a concrete
example genuinely aids understanding, and are labeled as examples. The
per-event debug history (`SLICE1_EVENTS.md` §11) is slice-1 history and stays
behind in the archived document — it is not reproduced here.

---

## 1. How one RMXP event becomes ROM content

An RMXP event is not a script — it is *a stack of pages*, each with its own
activation condition, trigger, graphic, and command list. Only one page is
"active" at a time (RMXP picks the **highest-numbered page whose condition
holds**). Almost every conversion "chain" in the pipeline is this one
structure, unrolled across several Emerald mechanisms at once:

| Piece | Where it lives | What it does |
|---|---|---|
| **Boot page** | `metadata_wiring.select_boot_page` | The page whose condition holds at *new-game* state. It alone decides the object's sprite, facing and movement type — GBA object events are static after spawn, so page-driven graphic/movement changes are not reflected. |
| **Page bodies** | `Map{m}_EV{e}_Page{n}` in `scripts/Map*.pory` | Each page's command list, transpiled 1:1 into Poryscript. |
| **Dispatcher** | `Map{m}_EV{e}_Dispatch` in `porymap/dispatch/` | RMXP's page selection, re-implemented at runtime: an if-chain over the page conditions, highest page first, `goto`-ing that page's body; falls through to `end` when no page matches. This is what turns "5 pages" into "one talkable NPC". |
| **Object event** | `map.json` `object_events` | The visible actor. Carries graphics id, movement type + range, visibility `flag`, and `script` = the dispatcher (or the single page body). |
| **BG event** | `map.json` `bg_events` (`type: sign`) | A blank-graphic, action-trigger event — signs, furniture, wall text. |
| **Coord event** | `map.json` `coord_events` | A blank/invisible **event-touch** event. `Trainer(N)`-named events become a *ray* of N coord events in the graphic's facing direction (the Essentials sight-line convention, see §2 below); a touch event on an unstandable tile is relocated to its standable orthogonal neighbours. |
| **Warp event** | `map.json` `warp_events` | A player-touch event whose page-1 body is a code-201 transfer into another map. Source warps keep indices `0..n-1`; **arrival** warps are appended at the RMXP destination coords, and a door's `dest_warp_id` names the *arrival* warp on the far map (`metadata_wiring._resolve_all_warp_events`). |
| **`ON_TRANSITION`** | `mapscripts` block | Sets/clears the `FLAG_TEMP_1x` visibility flag of every story-gated or hidden actor on map entry — this is how a page condition that a static object event can't express still gates whether the actor exists. |
| **`ON_FRAME_TABLE`** | `mapscripts` + `<Map>_OnFrame` | Autorun pages. Guard-checked once per map entry (latched on `VAR_TEMP_C`, re-armed by `metadata_wiring.insert_onframe_rearms` when a guard input changes — see `reference/guides/engine_gotchas.md` §3). |
| **`ON_WARP_INTO_MAP_TABLE`** | `mapscripts` + `<Map>_OnWarpFacing` | Post-warp arrival facing, dispatched on the player's landing coords. |
| **Sub-labels** | `_Move{n}`, `_Choice{n}_Opt{k}`, `_Tally`, `_TestBody` | Movement routes, `dynmultichoice` option text, and hand-authored helper scripts. One RMXP "Set Move Route" (code 209) becomes one `movement` block + `applymovement`/`waitmovement`. |
| **Hidden-actor bracket** | `tileset_converter/hidden_actor_bracket.py` | An RMXP event always exists even at opacity 0; a GBA flag-hidden object does not. The staging pass auto-inserts `addobject(N)` before the first reference to a hidden actor and `removeobject(N)` after its last one, so `applymovement` at it doesn't silently no-op — see §3 below. |

### Drop rules

Not every RMXP event emits an object into the ROM. The pipeline drops:

- A boot page with a blank graphic on player-touch / autorun / parallel
  trigger, or an invisible (opacity-0) graphic on a non-touch trigger, or a
  door-sheet graphic (`DROP:*` in the pipeline's own vocabulary — these have
  nothing for the player to see or touch as a real object).
- An event whose *every* page is story-gated — it has no boot page at all
  (`DROP:no_boot_page`). **Exception:** if a cutscene still needs it as a
  movement target, the required-actor pass places it anyway as a
  **flag-hidden actor** (invisible via a `FLAG_TEMP_1x` visibility flag,
  present in `object_events` so scripted movement can still target it).
- An event that warps to a map outside the current slice — skipped whole
  (`SKIP:out-of-slice warp`).
- Dropped-and-unreferenced page bodies are pruned out of the staged script
  output, so it's normal to see an event with transpiled page labels but none
  in the final staged file.

---

## 2. Coordinate-event rays — the `Trainer(N)` sight-line convention

Essentials names an event `Trainer(N)` to give it a sight-line trip: an
invisible tripwire along `N` tiles in the direction the event's graphic
faces, that fires when the player crosses it (`pbEventCanReachPlayer?` in
Essentials terms). The pipeline converts this into a **run of `N`
pokeemerald `coord_events`** painted along that ray — one native GBA
mechanism (touch-by-standing coord events) chained instead of a single
tripwire at the event's own tile.

This applies whether the event is a real battle trainer or (as is common in
early-game story maps) a cutscene tripwire used purely for scripted dialogue
or movement, never a native trainer battle. Converting a `Trainer(N)` event
into a *visible*, native `TRAINER_TYPE_NORMAL` sight-ray battle trainer is a
different, larger conversion that the pipeline does not currently attempt —
if a slice needs a real battle trainer with a sight-ray, that path still has
to be built; treat any `Trainer(N)` naming as "coord-event ray tripwire"
only, not "battle trainer," until that native trainer-object path exists.

A touch-triggered coord event whose target tile is itself unstandable is
relocated to its standable orthogonal neighbours — pokeemerald's own
collision model must agree a tile is walkable before a coord event can be
placed on it (see `reference/guides/custom_route_interpreter.md`'s
`MapPassability.standable` for the exact rule this relocation depends on).

---

## 3. The hidden-actor bracket mechanism

RMXP events always exist in the engine's internal model even at opacity 0 —
a "hidden" NPC used purely as a scripted movement target (e.g. an actor that
walks into frame mid-cutscene) is still a fully real, addressable object on
the RMXP side. A GBA object event with no spawn condition met simply does not
exist at all: there is nothing for `applymovement` or similar commands to
act on.

The staging pass (`tileset_converter/hidden_actor_bracket.py`) closes this
gap for events that a script references but that would otherwise never spawn
(flag-hidden actors, per the drop-rule exception above): it scans each script
body for the actor's first and last reference within a control-flow-aware
pass (branch-path dominance, not just first/last line order — a reference
inside an alternate `if`/`switch` branch is handled correctly), and inserts
`addobject(N)` immediately before the first reference and `removeobject(N)`
immediately after the last, so the actor is present in `gObjectEvents` for
exactly the span of script that needs it and gone otherwise. Without this
bracket, a scripted reference to a hidden actor silently no-ops — no crash,
no build error, just a movement command that does nothing because the object
was never spawned.

---

## 4. RMXP construct → Emerald construct mapping

The table below is the accumulated mapping of which native (or fork-added)
Emerald mechanism realizes which RMXP construct, drawn from everything a real
slice's corpus has exercised so far. Not exhaustive for the whole Essentials
command set — it is what has actually been converted and verified, and is
meant to grow as later slices exercise more of Essentials' surface.

| RMXP construct / behavior | Realized via | Notes |
|---|---|---|
| Flavour-text sign/furniture/wall text | `bg_events` (`type: sign`) + `msgbox` | Vanilla mechanism, direct mapping — the largest single category in any slice's event count. |
| `pbTrainerPC` (any PC call) | `goto(EventScript_PC)` (`data/scripts/pc.inc`) | Native Emerald PC used directly, no bespoke script. |
| Rock Smash field move | `EventScript_RockSmash` (`data/scripts/field_move_scripts.inc:64`) | Vanilla. |
| Heal/white-out respawn point | `special(HealPlayerParty)` | Vanilla special; a common `ON_FRAME_TABLE` autorun target for respawn tiles. |
| `pbShowMap` (region/town map) | `special(FieldShowRegionMap)` (`engine/src/field_specials.c:1014`) | Fork special, unused by any vanilla map script — no vanilla analog exists (FRLG's town map sign is plain flavour text), so this is a deliberate upgrade over the closest native idiom rather than a like-for-like substitution. |
| Running Shoes grant | `setflag(FLAG_SYS_B_DASH)` | Same flag `LittlerootTown_EventScript_SetReceivedRunningShoes` sets. |
| Pokédex grant | `setflag(FLAG_SYS_POKEDEX_GET)` + `special(SetUnlockedPokedexFlags)` | Same primitives as `LittlerootTown_ProfessorBirchsLab/scripts.inc`. |
| Starter/gift Pokémon grant (`pbAddPokemon` ceremony) | `givemon` + `setflag(FLAG_SYS_POKEMON_GET)` | See `reference/guides/engine_gotchas.md` §5 — `givemon` alone never sets the START-menu visibility flag; it must be paired explicitly. |
| Scripted/story rival battle | `trainerbattle_earlyrival` + `RIVAL_BATTLE_HEAL_AFTER` | FRLG's Oak's-lab rival macro (`asm/macros/event.inc:828`) — reused as-is for any early-game scripted rival fight, not just a slice-1-specific one. |
| Multi-option branching choice | `dynmultichoice` (expansion) | Vanilla analog is the more limited `multichoice`; `dynmultichoice` is used when option count/text needs to be dynamic. |
| Yes/No prompt | `yesnobox` | Vanilla, direct mapping. |
| Item grant | `giveitem` | Vanilla, direct mapping. |
| "!" exclamation reaction bubble | `Common_Movement_ExclamationMark` (`data/scripts/movement.inc`) | Vanilla common movement, reused for any surprised-NPC beat. |
| Map transfer (any warp) | `warp_events` + paired arrival warp | Converter-side pairing on top of the vanilla schema — see the Warp event row in §1. |
| Autorun (RMXP trigger 3, "Parallel"/conditional-repeat pages) | `MAP_SCRIPT_ON_FRAME_TABLE` | Vanilla mechanism (same shape as Littleroot's intro `map_script_2` entries); see `reference/guides/engine_gotchas.md` §3 for the latch-staleness gotcha. |
| Story-gated / conditionally-hidden actor | `MAP_SCRIPT_ON_TRANSITION` + a `FLAG_HIDE_*`-pattern visibility flag | Vanilla pattern, reused generically for any page condition a static object event can't express on its own. |
| Post-warp arrival facing | `MAP_SCRIPT_ON_WARP_INTO_MAP_TABLE` + `turnobject` | Vanilla mechanism; the arrival-facing feature this pipeline builds on top of it is documented in `MEMORY.md`/history under "WARP-ARRIVAL FACING". |
| Simple back-and-forth patrol/wander | `MOVEMENT_TYPE_WANDER_AROUND` and other native `MOVEMENT_TYPE_*` | Used when the RMXP route is natively expressible; see the next row for when it isn't. |
| Arbitrary/looping custom move route | `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` (fork addition, `0x53`) | Full spec: `reference/guides/custom_route_interpreter.md`. Superseded the native-approximation path (`WALK_LEFT_AND_RIGHT`/`WALK_SEQUENCE_*`/`LOOK_AROUND`) because roughly 62% of a real corpus's custom routes are not natively expressible. |

### Deliberately not used, with reasons on file

These are constructs that look like the "obvious" native mapping but were
scoped and rejected — worth knowing about before re-proposing them:

- **`MB_ANIMATED_DOOR` + `sDoorAnimGraphicsTable`** for RMXP's charset-driven
  animated doors — real engine work (a C table edit per door, plus the door
  frames must quantize into an existing BG palette), scoped twice and
  deferred by user decision; see `reference/guides/engine_gotchas.md` §7 for
  the mandatory-table-entry gotcha (`GetDoorGraphics` silently no-ops with no
  match).
- **Native `MOVEMENT_TYPE_WALK_LEFT_AND_RIGHT`/`WALK_SEQUENCE_*`/
  `LOOK_AROUND`-family approximation** for arbitrary custom routes — built
  and shipped once, then superseded by the custom-route interpreter once the
  corpus-wide unrepresentable-route rate (62%) was measured.
- **Visible `TRAINER_TYPE_NORMAL` sight-ray battle trainers** for
  `Trainer(N)`-named events — those are frequently cutscene tripwires, not
  battle trainers (§2 above); a real native trainer-object conversion path
  for genuine battle trainers isn't built yet, so any `Trainer(N)` event that
  actually needs to be a visible fightable trainer fails loud today rather
  than silently becoming something wrong.
- **`Common_EventScript_PkmnCenterNurse`** for a healing-machine-style prop —
  an inline fade/heal script was used instead of the vanilla nurse common;
  tracked as an open cleanup item, not a hard rejection.
