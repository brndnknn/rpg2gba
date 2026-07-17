# Moki-Town slice: story chain + event-trigger bugs

**Date:** 2026-07-16
**Status:** research complete, **no fix implemented yet** — awaiting user instruction.
**Trigger:** boot-walk report — "the Theo event never triggers; the Pokédex one triggers
when I talk to the professor and it causes the player to walk through the back wall into
the void."

This doc exists because the previous session's mental model was wrong in two ways: it
believed the slice was 3 maps, and it believed the reported "Pokédex ceremony" bug was
Map032 EV009. Both are corrected below. Read this before touching any Moki event.

---

## 1. Slice scope (corrected)

Source of truth: `src/rpg2gba/tileset_converter/map_set.py:30`

```python
SLICE_MAP_IDS: list[int] = [49, 48, 32, 50, 64, 65, 172, 89]
```

The interiors were added 2026-07-13 (SLICE1_TODO #13). Any note saying the slice is
"Map 49 ↔ 48 ↔ 32" predates that and is stale.

| RMXP id | Uranium identity | Engine dir | porymap constant |
|---|---|---|---|
| 49 | Player's House 1F (spawn @7,7) | `MokiTownPlayersHouse1F` | `MAP_MOKI_TOWN_PLAYERS_HOUSE_1F` |
| 48 | Player's House 2F | `MokiTownPlayersHouse2F` | `MAP_MOKI_TOWN_PLAYERS_HOUSE_2F` |
| 32 | Moki Town (outdoors) | `MokiTown` | `MAP_MOKI_TOWN` |
| 50 | Professor Bamb'o's Lab | `MokiTownProfessorLab` | `MAP_MOKI_TOWN_PROFESSOR_LAB` |
| 65 | Unnamed house 1 (door @32:24,42) | `MokiTownHouse1` | `MAP_MOKI_TOWN_HOUSE_1` |
| 64 | Unnamed house 2 (door @32:43,31) | `MokiTownHouse2` | `MAP_MOKI_TOWN_HOUSE_2` |
| 172 | Theo's House 1F (door @32:56,42) | `MokiTownTheo172` | `MAP_MOKI_TOWN_THEO_172` |
| 89 | Theo's House 2F (via 172 EV3) | `MokiTownTheo` | `MAP_MOKI_TOWN_THEO` |

Wired in `engine/data/maps/groups.inc:592-599` and `connections.inc:523-530`; layouts come
from `layouts.gen.json` (generator output), not the stock `layouts.json`.

---

## 2. The opening story chain

Two independent sources agree: the Uranium wiki walkthrough (narrative order) and the
deserialized RMXP data (gating). Where they disagree, **the RMXP data wins** — the wiki is
a player-written walkthrough.

### 2.1 Beat list

| # | Where | Beat | Gate / effect |
|---|---|---|---|
| 1 | 48 (House 2F) | Wake up; PC holds a free Potion | — |
| 2 | 49 (House 1F) | Talk to Auntie | **Hard gate.** Leaving without talking is blocked ("I'd better say goodbye to Auntie first"). Grants Running Shoes (`$PokemonGlobal.runningShoes=true` → `FLAG_SYS_B_DASH`). |
| 3 | 32 (outdoors) | Walk toward the lab door @(17,11) | — |
| 4 | 32 (outdoors) | **Theo runs up behind you** ("Hey, wait up!!!") — first rival encounter, no battle | EV074, invisible event-touch trip tile @(26,12), directly outside the lab door. **BUG A — never fires.** |
| 5 | 50 (Lab) | Enter; Prof. Bamb'o intro plays | EV005 "Bambo" page 0, **trigger=3 autorun**, ungated. **BUG B — fires on talk, not on entry.** |
| 6 | 50 (Lab) | Bamb'o offers the **Trainer Aptitude Test** (Yes! / Wait a minute...) | EV005 page 2, gated `self_switch D` — set by the page-0 autorun. |
| 7 | 50 (Lab) | Test result assigns the starter: Offensive→Raptorch, Defensive→Orchynx, Balanced→Eletux. Pick it up from the machine | EV019 "Machine" page 0 → **`var101 += 1`** ⇒ `VAR_QUEST_LOG = 1`. This is the lab's only quest-log write. |
| 8 | 50 (Lab) | Theo battles you (he gets the starter weak to yours) | EV020 "Theo" page 0; page 1 (`var101>=1`) blanks him — he leaves. |
| 9 | 32 → 172 | Go to Theo's house (east side, by the breakable rocks) | Lab exit warp EV001 page 1 only unlocks at `var101>=1`. |
| 10 | 172 (Theo 1F) | Cameron (Theo's dad) scene; both get a **PokéPod** | EV004 "Theo" page 0, **trigger=3 autorun**, gated `var101>=1`, opacity=0 → **`var101 = 2`** (hard set). **BUG B' — dropped entirely, see §3.2.** |
| 11 | 32 (outdoors, west) | Theo + Bamb'o wait by the tall grass at the west exit; Bamb'o demos catching a wild Chyinmunk and hands over the **Pokédex + 5 Poké Balls** | EV009 "Trainer(6)" page 2 → the real "Pokédex ceremony". Coord trigger @(16,42), needs `var101>=2`. Ends **`var101 = 4`**. **BUG C — choreography lands on the wrong NPCs.** |
| 12 | 32 → Route 1 | Head west | Out of slice. |

### 2.2 `VAR_QUEST_LOG` (RMXP var 101) state machine

Only three writes exist in the whole slice:

```
0 ──[50 EV019 Machine: +1]──> 1 ──[172 EV004 Theo autorun: =2]──> 2 ──[32 EV009 p2: =4]──> 4
```

`>=5` is read by 50 EV005 pages 5/6 but never written in-slice — that increment lives
outside the frontier. Maps 48, 64, 65, 89 never touch var 101.

**Ordering is enforced by data, not by narrative convention:** the lab exit warp is gated
`>=1`, Theo's house cutscene is gated `>=1`, and the ceremony is gated `>=2`. So the chain
cannot be skipped — but it also means **any one broken write stalls everything downstream.**

### 2.3 Wiki gaps worth knowing

- The wiki does **not** describe the professor sending you to fetch Theo. But Map032 EV009
  **page 1** (`var101>=1`) says exactly that: *"I want to show you and Theo how to catch a
  Pokémon. Can you go get him? He should be in his house."* The RMXP data is authoritative
  — page 1 is the "go fetch Theo" state between the lab and Theo's house. The wiki skips it.
- Wiki is inconsistent on whether the tutorial wild battle precedes or follows the Pokédex
  hand-off at beat 11. RMXP data: it's all one scripted scene inside EV009 page 2, no real
  battle — Bamb'o's capture demo is pure choreography.
- Direct `WebFetch` of fandom.com returns HTTP 402 in this environment; the research went
  through `WebSearch` snippets plus a third-party mirror. Treat wiki detail as soft.

---

## 3. The bugs

Three distinct root causes, all confirmed against source. None are fixed yet.

### 3.1 BUG A — every coord event after the first is dead (kills Theo, beat 4)

`metadata_wiring.py:258` hardcodes the gate on **every** coord event, on every map:

```python
var: str = "VAR_TEMP_0"
var_value: str = "0"
```

pokeemerald only runs a trigger's script when that var equals that value
(`ShouldTriggerScriptRun`, `src/field_control_avatar.c`). But `VAR_TEMP_0` is *also* the
transpiler's generic `getplayerxy` scratch register — `transpiler.py:163`
(`_ALIGN_AXIS_VAR`), `:869` (door `onEvent?`), `:1118` (align loops), and every page of the
hand-authored `Map032_EV009.pory`.

So the first coord event to fire on a map writes the player's x into `VAR_TEMP_0`, and from
that instant until the player leaves the map, **`VAR_TEMP_0 != 0` and no other coord event
on that map can ever fire.** Moki Town has exactly two coord events — EV009 @(16,42) and
EV074 @(26,12) — and they share the identical gate.

EV074 itself converts **correctly**: right position, right dispatcher
(`Map032_EV074_Dispatch`, gating on `VAR_QUEST_LOG`/`FLAG_MAP032_EVENT074_SSA`), correctly
classified as a coord event by `select_boot_page`/`build_object_events`. Nothing about the
event conversion is wrong. It's purely the shared-scratch-register gate.

This is a **corpus-wide** bug, not a Moki bug: any map with ≥2 coord events has it.

### 3.2 BUG B — autorun pages become action-button NPCs (the reported "talk to the professor")

`build_object_events` (`metadata_wiring.py:759-786`) only consults `trigger` when the boot
page's graphic is blank, or present-but-opacity-0:

```python
if not name:
    if trigger == TRIGGER_ACTION:      emit_kind = "bg"
    elif trigger == TRIGGER_EVENT_TOUCH: emit_kind = "coord"
    elif trigger == TRIGGER_PLAYER_TOUCH: _drop(eid, DROP_BLANK_TRIGGER1); continue
    elif trigger == TRIGGER_AUTORUN:   _drop(eid, DROP_AUTORUN); continue
    elif trigger == TRIGGER_PARALLEL:  _drop(eid, DROP_PARALLEL); continue
    else: raise ValueError(...)
elif opacity == 0:
    if trigger == TRIGGER_EVENT_TOUCH: emit_kind = "coord"
    else: _drop(eid, DROP_OPACITY0); continue
elif is_door_sheet(name): _drop(eid, DROP_DOOR_SHEET); continue
else:
    emit_kind = "object"        # <-- trigger is never consulted here
```

**A page with a visible graphic falls straight to `emit_kind = "object"` regardless of
trigger.** An autorun page therefore becomes a plain object event whose script is only
reachable via the action-button interact path.

`Map050` EV005 "Bambo" page 0 is `trigger=3` (autorun), ungated, graphic
`ZP- Professor2` — visible. So the lab intro that should fire **the moment you walk in**
instead fires **when you talk to him**. That is precisely the user's report.

And it explains the wall-walk: the autorun body choreographs the player from the *lab
entrance* (where the player stands when the scene is meant to fire). Firing it while the
player is standing next to Bamb'o at the far end of the lab runs that same route from the
wrong origin — and `applymovement` ignores collision — so the player walks out through the
back wall. **The route isn't wrong; the trigger point is.**

Note the transpiler side is *also* silent here: `transpile_event` (`transpiler.py:1362-1371`)
wraps trigger 0 in `lock/faceplayer/…/release` and triggers 1/2 in `lock/…/release`, but
triggers **3 and 4 hit neither branch** and get no wrapper at all. It emits the script text
and leaves the "how is this ever invoked" question entirely to the wiring, which then
answers it wrong.

**BUG B' (same root, opposite failure):** `Map172` EV004 "Theo" page 0 is `trigger=3`
autorun with `opacity=0` → hits the `elif opacity == 0` branch, `trigger != 2`, so it is
**`_drop`ped outright**. The PokéPod cutscene never exists in the ROM — which means
**`var101` never reaches 2**, which means beat 11 (the real Pokédex ceremony) is
unreachable. The same shape drops `Map050` EV027 and the Postgame Cutscene.

There is currently **no channel to emit a map script**. The only map-script emitter is
`render_arrival_facing_script` (`metadata_wiring.py:998-1038`), purpose-built for
`ON_WARP_INTO_MAP_TABLE` warp-arrival facing with a hardcoded `VAR_TEMP_1` guard and
`turnobject` body. It is not generic and cannot carry an arbitrary autorun body.

### 3.3 BUG C — `applymovement` silently drives the wrong NPC (the real ceremony, beat 11)

`Map032_EV009.pory` (hand override) choreographs RMXP events **16** (Bamb'o), **2** (Theo),
**76** (the Chyinmunk), **77** (the starter). All four are gated `var101 >= 2`, so at boot
`select_boot_page` returns `None` and `build_object_events` drops them — **correctly**;
in Uranium they genuinely aren't on the map yet.

Dropped events get no local id (`metadata_wiring.py:890` only assigns one on the
`emit_kind == "object"` path). `local_id_remap.remap_pory_object_ids` then hits its
"unmapped id → warn and leave" rule (`local_id_remap.py:163-173`) and leaves the literal
integers in place. But local ids are a dense `1..N` sequence, so the leftovers **collide**:

| script says | intends | actually hits |
|---|---|---|
| `applymovement(16, …)` | Bamb'o @(15,44) | local 16 = **RMXP EV070**, an unrelated townsfolk @(43,50) |
| `applymovement(2, …)` | Theo @(16,45) | local 2 = **RMXP EV010**, a wandering Chyinmunk @(27,9) |
| `applymovement(76, …)` | Chyinmunk @(12,44) | nothing — only locals 1..19 exist |
| `applymovement(77, …)` | starter @(13,44) | nothing |

`Map032_EV009_Page3_Move8` is a 15-step walk ending in `set_invisible`, so a random
townsfolk marches across Moki Town through walls and vanishes.

`local_id_remap` has **no collision detection** — it checks membership as a *key* only,
never whether the left-alone integer is a live local id. Its docstring (lines 142-144)
explicitly rationalises leftovers as "legitimately-absent objects whose scripts are
unreachable", which is false exactly when the integer lands in `1..N`.

Nothing else catches it either. `fork_index.verify_script` is purely lexical — its five
rules match ALL_CAPS constants, call-position identifiers, special() args, and movement
tokens. A bare integer argument is invisible to every one. There is a fail-loud check that
the *traits sidecar* references only emitted events (`metadata_wiring.py:892-901`) but no
equivalent for movement targets.

**This also violates a documented invariant.** `transpiler.py:1208-1210` and `:1154-1156`
both assume "local id == RMXP event id"; `reference/findings/slice1_queue_readthrough.md:38-40`
records it as the TASK-4 constraint. Sequential `1..N` assignment over only the emitted
events breaks it on essentially every map — `local_id_remap` exists to paper over that, and
can't, whenever the target was dropped.

### 3.4 BUG D — the ceremony never advances the quest log (minor, hand-authoring error)

`Map032_EV009.pory:205` ends with `setvar(VAR_AUNTIE_VISIT_STAGE, 4)`. It should be
`setvar(VAR_QUEST_LOG, 4)`. Per `output/uranium-build/flag_state.json`:

```
variables | 101  -> VAR_QUEST_LOG            <- RMXP var 101 = "Quest Log"
variables | 1000 -> VAR_AUNTIE_VISIT_STAGE   <- a different, bogus id
```

The RMXP command is `ControlVars([101,101, op=0/set, value=4])` — var 101. So the ceremony
currently leaves the quest log at 2 and would re-fire.

---

## 4. What is NOT broken (checked, ruled out)

- **EV078 / EV080 absent from Moki Town** — correct. Gated on switch 55 ("Gym 1 defeated")
  and switch 125 ("FINAL EVENT"); no active page at boot. Faithful.
- **EV074's dispatcher, position, and page gating** — correct. Only the coord gate (§3.1).
- **The var range** — `VAR_QUEST_LOG = RPG2GBA_VAR_BASE + 53 = 0x4135`, inside
  `[0x4100, 0x41FF]` given `RPG2GBA_VARS_COUNT = 0x100`. In bounds, zeroed on new game.
- **Bamb'o (EV016) / Theo (EV002) / 76 / 77 being dropped from Moki Town at boot** — correct
  and faithful. The bug is that the ceremony choreographs them anyway (§3.3), not that
  they're absent.
- **Map032 EV009's own trigger** — genuinely `trigger=2` event-touch in RMXP, correctly
  emitted as a coord event. Faithful.

---

## 5. Open design question (user answered 2026-07-16)

*How should the pipeline model cutscene actors that are gated off at boot but choreographed
by a script?* → **"Emit them with a visibility flag"**: emit gated-off events as object
events anyway, spawned hidden behind a per-event flag, so they get real local ids and the
choreography lands on the right sprites. Mirrors vanilla's cutscene-NPC handling and
generalises to the corpus.

Not yet designed or implemented. Interacts with §3.3 (would obviate the collision by giving
16/2/76/77 real local ids) and needs a story-state → visibility-flag mapping, since these
actors' RMXP gating is `var101 >= N`, not a boolean.

---

## 6. Fix sketch (not implemented — for discussion)

Rough shape, in dependency order. Each needs sign-off before building.

1. **§3.1 coord gate.** Stop gating coord events on `VAR_TEMP_0`. Cheapest correct fix:
   reserve a var the transpiler never writes, keep `var_value = 0` (temp vars zero on map
   entry, so an unwritten reserved temp var reads as "always fire on this visit"), and
   fail loud if the transpiler ever emits that name. The dispatchers already do the real
   story gating, so "always fire, let the dispatcher decide" is the right semantics.
   Smallest change, unblocks Theo, corpus-wide win.
2. **§3.2 autorun channel.** Needs a real map-script emitter — an `ON_TRANSITION` /
   `ON_FRAME_TABLE` block with a self-guard, generalising what `render_arrival_facing_script`
   does for one hardcoded case. Trigger info can ride the existing per-map `.traits.json`
   sidecar (`transpile_driver.py:139-165` writes, `stage_slice_scripts.py:61-73` reads);
   its `{event_id: [trait]}` schema is generic enough. Until this lands, autorun pages are
   either mis-triggered (visible graphic) or silently dropped (opacity 0), and **the slice's
   quest chain cannot complete** — 172 EV004 is the `var101 = 2` write.
3. **§3.3 fail-loud.** `local_id_remap` must error, not warn, when a remapped command
   targets an id absent from the table — and separately when a left-alone integer collides
   with a live local id. This will immediately red-build the ceremony, which is correct:
   it is currently emitting garbage silently. Sequence it *after* §5's actor model, or the
   build stays broken.
4. **§3.4** one-line override fix; do it whenever.

**Ordering note:** §3.2 gates the slice more than §3.1 does. Theo (beat 4) is cosmetic —
a missed rival cameo. But 172 EV004 being dropped means `var101` never reaches 2, so beats
11–12 are unreachable and the slice cannot be walked to Route 1. If only one thing gets
built, build §3.2.

---

## 7. Provenance

Research done 2026-07-16 via `/delegate` — five read-only sub-agents (RMXP source dump for
Map032/050/172, hand-override read, pipeline trigger-path trace, compiled-output audit,
wiki walkthrough) plus lead verification of the flag registry, var ranges, generated
headers, and the EV009 dispatcher. No code changed except this doc and the MEMORY.md
slice-scope correction.
