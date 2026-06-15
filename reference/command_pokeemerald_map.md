# Command → pokeemerald disposition map (build-agent backlog)

> **Status:** living artifact, started 2026-06-14 (the "go through every command
> together" pass). The authoritative per-command vocabulary map that drives the
> **deterministic-classifier + Track-B/C backlog**. Fork-verified where marked
> ✓VERIFIED; ⚠RECHECK rows are proposals not yet confirmed against the fork.
>
> **This is NOT the agent's prompt.** The frozen conversion-agent guidance lives in
> `reference/uranium_script_calls.md` (loaded by `prompt_builder.load_command_reference`,
> part of the §9-frozen system prompt — do **not** edit mid-campaign, invariant 1).
> The deterministic classifiers run *before* the agent, so a `DET` row here is built
> as a classifier that **overrides** the agent's (often conservative) disposition —
> e.g. the frozen table marks `pbPokeCenterPC` UNHANDLED, but it maps cleanly to a
> native fork script, so we determinize it here without touching the frozen table.
>
> **Key finding (2026-06-14):** the frozen table *under-converts* — it tags as
> "needs engine" many idioms that are **native pokeemerald-expansion features**
> (rock smash, berry trees, cave Flash, bridges, day care, move relearner, in-game
> trade, mystery gift, the Poké Center PC). Their conversion is **Track-B wiring**
> (point an object at the native script / set a metatile behavior / map flag),
> **not new C.** This sharply shrinks the genuine Track-C set (Nuclear-type, the
> custom minigames, Uranium-custom UI). The fork is the oracle, not Opus.

## Disposition categories

| Tag | Meaning | Track |
|---|---|---|
| **DET** | Clean event-script target; determinizable as a classifier now, no Phase-5/6 dependency. | A |
| **WIRE** | Native pokeemerald feature, but conversion needs Phase-5 map wiring (local object ids / real `MAP_*` / metatile behavior / map flag / point-object-at-native-script). **No new C.** | B |
| **C** | Genuinely needs new fork C (absent feature or Uranium-custom). Per-mechanic fidelity call (replicate vs stub→Phase-8 ADAPT). | C |
| **STRIP** | No game state; emit nothing. | A |
| **JUDGE** | Context-dependent (branch conditions, choices, free expressions); the irreducible Opus tail. | (Opus) |

Counts are corpus event-counts (`scripts/idiom_frequency.py` / census); `#opus` =
still-Opus-bound today.

---

## Structural RMXP codes (53 distinct)

These are claimed by **composite idiom classifiers** (a classifier recognizes a
whole-event command combination), not one-classifier-per-code. The DET vocabulary
below is what those classifiers may emit.

| Code | Name | #ev | #opus | Tag | pokeemerald target / note |
|---|---|---|---|---|---|
| 101/401 | Show Text | 1567 | 875 | DET | `msgbox("…")` — plain text + `\PN`→`{PLAYER}` only (classifiers 1/7). Other control codes → JUDGE. |
| 111 | Conditional Branch | 1778 | 1397 | JUDGE | Mostly judgment. **DET subsets:** self-switch check, script-type `pbItemBall` (classifier 8). 412/411 are its scaffolding. |
| 412/411 | Branch End / Else | — | — | — | Scaffolding of 111. |
| 106 | Wait | 1285 | 953 | STRIP | Pure pacing; dropped as plumbing (gate G2). |
| 209/509 | Set Move Route / Move Command | 1191 | 1191 | WIRE | `applymovement(localid, …)` — needs local-ids (OQ-3: player-only ~45% reclaimable first). |
| 210 | Wait for Move Completion | 1064 | 1064 | WIRE | `waitmovement(0)`; pairs with 209. |
| 223 | Change Screen Color Tone | 1013 | 714 | DET | `fadescreen(FADE_TO/FROM_BLACK)` for the warp fade idiom; arbitrary tones → JUDGE. |
| 201 | Transfer Player | 926 | 622 | WIRE | `warp(MAP_*, x, y)` — classifier 4 emits `MAP_URANIUM_<N>` placeholder; Group 2 resolves real constants. |
| 123 | Control Self Switch | 887 | 446 | DET | `setflag`/`clearflag(<self-switch flag>)` (orchestrator mints; classifier 3). |
| 250/249 | Play SE / ME | 841 | 547 | STRIP | Audio plumbing; host action reproduces meaningful ones. |
| 122 | Control Variables | 412 | 412 | JUDGE | `setvar(VAR_*, n)` for a literal RHS (DET); expressions → JUDGE. |
| 208 | Change Transparent Flag | 268 | 268 | WIRE | Object visibility (`removeobject`/`addobject`/subpriority) — needs local-id. |
| 121 | Control Switches | 246 | 246 | JUDGE | `setflag(FLAG_*)` global switch; needs registry naming (global) → Opus territory. |
| 102/402/404 | Show Choices | 219 | 219 | JUDGE | `multichoice` + `switch(VAR_RESULT)` scaffolding is DET, but per-branch logic varies → JUDGE. |
| 108/408 | Comment | 201 | 92 | STRIP | — |
| 207 | Show Animation | 116 | 116 | C/JUDGE | Field animation; no clean field-script analogue. |
| 202 | Set Event Location | 91 | 91 | WIRE | `setobjectxy(localid, …)` — needs local-id. |
| 116 | Erase Event | 88 | 88 | WIRE | `removeobject(localid)` — needs local-id. |
| 204 | Change Map Settings | 82 | 82 | JUDGE | Varies (often STRIP). |
| 117 | Call Common Event | 68 | 18 | DET | `call CommonEvent_<NNN>` (classifier 2). |
| 115 | Exit Event Processing | 68 | 68 | DET | `return`/`end`. |
| 206 | Change Fog Opacity | 65 | 65 | STRIP | No GBA analogue. |
| 241/242/245/246 | BGM ops | ~90 | ~90 | DET/STRIP | `playbgm`/`fadedefaultbgm`; memorize/restore → STRIP. |
| 314 | Recover All | 54 | 54 | DET | `healparty` (= `pbHealAll`). |
| 224 | Screen Flash | 50 | 50 | DET/STRIP | Brief flash; often plumbing. |
| 118/119 | Label / Jump to Label | 78 | 78 | DET | poryscript `label`/`goto`. |
| 104 | Change Text Options | 35 | 35 | STRIP | — |
| 112/413/113 | Loop / Repeat / Break | ~95 | ~95 | JUDGE | `while`/loop control (often the random-item events). |
| 203 | Scroll Map | 33 | 33 | C/JUDGE | Camera pan — needs a special. |
| 225 | Screen Shake | 30 | 30 | STRIP/C | No clean field analogue. |
| 221/222 | Transition prep/execute | 39 | 39 | STRIP | Plumbing of the warp/transition idiom. |
| 132 | Change Battle BGM | 18 | 18 | JUDGE | `nextBattleBack`-adjacent; usually STRIP. |
| 231/232/235/234 | Picture ops | 50 | 50 | C | Image overlays (`NeedsC` in the RGSS table). |
| 125 | Change Gold | 11 | 11 | DET ⚠RECHECK | money add/remove — confirm the poryscript/special. |
| 403 | When Cancel | 9 | 9 | JUDGE | Part of choices. |
| 135 | Change Menu Access | 4 | 4 | STRIP/JUDGE | — |
| 124 | Control Timer | 3 | 3 | C/JUDGE | — |
| 103 | Input Number | 1 | 1 | JUDGE | One occurrence. |

---

## Script-calls (145 distinct heads)

### DET — determinizable now (classifier built or buildable, no Phase-5/6 dep)

| Head | #ev | #opus | pokeemerald target | Status |
|---|---|---|---|---|
| `pbItemBall` | 230* | 0 | `giveitem(ITEM_*, 1)` + self-switch | ✓ classifier 8 (built; *via the `{111,123,411,412}` idiom) |
| `pbPokemonMart` / `pbPokemonBerryMart` | 41 | 24 | `pokemart(<label>)` + `mart` block | ✓ classifier 9 (built; mart only so far) |
| `setTempSwitchOn/Off`, `tsOn?/tsOff?` | 345 | 345 | `setflag`/`clearflag`/`flag(FLAG_…_TS…)` | orchestrator mints; clean cases = classifier candidate |
| `pbSetSelfSwitch` | 94 | 94 | `setflag`/`clearflag(<self-switch>)` | classifier candidate (= code 123) |
| **`pbPokeCenterPC`** | 21 | 21 | **`goto(EventScript_PC)`** | ✓VERIFIED fork; **NEW DET win** (frozen table wrongly UNHANDLED) |
| `pbHealAll` | 2 | 2 | `healparty` | ✓ vocabulary (= code 314) |
| `pbReceiveItem` | 16 | 16 | `giveitem(ITEM_*, qty)` | DET vocab; embedded in dialogue/branches + dynamic `pbGet` forms → needs a dialogue+item classifier or → JUDGE |
| `pbAddPokemon(Silent)` | 9 | 9 | `givemon(SPECIES_*, level)` | DET vocab (species map) |
| `pbDeleteItem` | 8 | 8 | `removeitem(ITEM_*, qty)` | DET vocab |
| `pbSet` / `setVariable` | 7 | 7 | `setvar(VAR_*, n)` | DET vocab (literal RHS) |
| `pbEraseThisEvent` | 14 | 14 | `removeobject(localid)` + `setflag` | WIRE-adjacent (local-id) — see WIRE |

### WIRE — native fork feature, needs Phase-5 wiring (no new C)

| Head | #ev | #opus | Native fork target | Status |
|---|---|---|---|---|
| `pbNoticePlayer` | 250 | 100 | trainer approach+`!` (native in `trainerbattle`; standalone → `applymovement`) | ✓ native; local-id |
| `pbRockSmashRandomEncounter` | 65 | 65 | `EventScript_RockSmash` + `special RockSmashWildEncounter` | ✓VERIFIED native |
| `pbBerryPlant` | 53 | 53 | `data/scripts/berry_tree.inc` (berry-tree object) | ✓VERIFIED native |
| `pbCaveEntrance` / `pbCaveExit` / `…Ex` | 102 | 102 | cave-darkness map flag + `EventScript_UseFlash`; exit may be a `warp` | ✓VERIFIED native (mostly map setup) |
| `pbBridgeOn` / `pbBridgeOff` | 65 | 65 | `MB_*_BRIDGE` metatile behaviors | ✓VERIFIED native (map data) |
| `pkmn.pbLearnMove` | (≈87 in table) | — | `ChooseMonForMoveRelearner` + `TeachMoveRelearnerMove` specials | ✓VERIFIED native (move relearner) |
| `pbStartTrade` | 5 | 5 | in-game trade (`ingame_trades` + trade scene special) | ⚠RECHECK exact special |
| `pbDayCare*` | ~5 | ~5 | native day care (Route117 + day-care specials) | ✓VERIFIED native exists; ⚠RECHECK call mapping |
| `pbReceiveMysteryGift` | (table 11) | — | `src/mystery_gift.c` native; Uranium use likely just gives items → maybe STRIP/substitute | ⚠RECHECK |
| `pbPushThisBoulder` | 7 | 7 | Strength boulder (`MB_PUSHABLE_BOULDER` + native) | ⚠RECHECK |
| `pbFlyAnimation` / `pbCancelVehicles` | 10 | 10 | fly/vehicle native | ⚠RECHECK |

### C — genuinely needs new fork C (per-mechanic fidelity call)

| Head | #ev | #opus | Why | Disposition |
|---|---|---|---|---|
| `nextBattleNuclearHorde` | 17 | 17 | Nuclear horde battle | Phase 6 (Nuclear track) |
| `pbPhoneRegisterBattle/NPC/Increment` | ~28 | ~28 | Pokégear/phone rematch | C — or stub→Phase 8 |
| `pbSlotMachine` / `pbVoltorbFlip` | 24 | 24 | Game-corner minigames | C — or stub→Phase 8 ADAPT (cf. racing) |
| `pbLottery` / `pbSetLotteryNumber` | 4 | 4 | Lottery | C — or stub |
| `pbRegisterPartner` / `pbDeregisterPartner` | 19 | 19 | Single-player tag-battle ally | ⚠RECHECK (expansion multi-battle); likely C-light |
| `pkmn.setAbility` / `pkmn.setItem` | (table 28) | — | Mutate a chosen party mon's ability/held item | JUDGE/C (after party selection) |
| Uranium-custom (`pbGenerateChampionship`, `setupWaitingRoom`, `openPunkBroPC`, `createPuzzle`, gym puzzle helpers, `jv*`, `nuz*`) | ~1 each | — | Story/feature-specific | per-feature §10 call (several already ADAPT/Phase-8) |

### STRIP — emit nothing (carried from the frozen table, ✓consistent)

`pbCallBub` (3413 occ), `set_fog2`/206, `XInput.vibrate`, `pbSEPlay`, `pbPlayCry`,
`$scene.spriteset.addUserSprite`, `$game_map.need_refresh`, `pb(Add|Remove)Dependency2`,
**`pbSetPokemonCenter` / `pbSetHealingSpot`** (respawn captured by §2.8 `metadata.py`),
`$game_map.replace_tileset`, `pbMEStop`.

### JUDGE — Opus tail (context-dependent)

`pbChoose*Pokemon` (party selection + varying downstream use), Ruby control-flow &
expression fragments (`if`/`for`/`<expr>`/bare loop vars), `item=rand(…)` random-shard
pickup logic, `pbWildBattle` (contextual), and the bulk of 111/122/121/102 branch logic.

---

## Operator decisions needed

These are the §10 fidelity / track-assignment calls surfaced by this pass:

1. **`pbPokeCenterPC` → `goto(EventScript_PC)`** — substitute the standard vanilla
   PC; drops Uranium's conditional `openPunkBroPC` skin. (Recommended: accept; flag
   Punk Bros as Phase-8 if wanted.) Unblocks an immediate ~17-event DET classifier.
2. **WIRE mechanics fidelity** (rock smash / berry / cave-Flash / bridge / day care /
   move relearner / trade): replicate via the native fork script (faithful) vs stub.
   Default lean: **use the native script** (they exist; faithful + cheap). Each is a
   §10 call but the native target makes "replicate" the obvious choice.
3. **True Track-C set** (Nuclear horde, slots/Voltorb-Flip/lottery, phone): build now
   vs **stub→Phase-8 ADAPT** (precedent: racing minigame, dream sequence, Custom Mode).
   This is OQ-R4.
4. **⚠RECHECK rows** still to fork-verify (trade special, day-care call mapping,
   mystery gift, boulder, partner, code 125 money) — next pass.
