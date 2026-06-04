# Uranium script-call translation reference (Phase 4)

> Hand-authored for the conversion agent (Phase 4 calibration, Part A1).
> A compact disposition table for the most common **Script** commands (RPG Maker
> codes 355/655), whose leading signatures are inventoried in
> `reference/rgss_event_commands.md`. Uranium adds no custom command *codes* — all
> of its custom behaviour rides in these `pbXxx` / `Kernel.*` / `$game_*` calls.
>
> This covers the highest-frequency signatures — **≈92% of the 7,925 script-call
> lines** (the top ~60 of 250 distinct signatures; full distribution measured via
> `scripts/_tmp_scriptcall_dict.py`). The long tail (~190 rare signatures, 77 of them
> one-offs) is intentionally undocumented: the agent must queue anything not listed
> here. Tags are **advisory** and get human review at the §9 #2 calibration gate.

## How to use this table

Each row is tagged exactly one of:

- **MAP** — there is a confident Poryscript equivalent; emit it.
- **STRIP** — cosmetic, engine-bookkeeping, or handled deterministically elsewhere
  in the pipeline; emit nothing.
- **UNHANDLED** — no safe equivalent, or needs an engine feature we haven't built;
  do **not** guess. Queue it (`unhandled[]`) and mark its position in the script
  with a `# UNHANDLED` comment. Honors CLAUDE.md §4.5 (fail loud) / §9.

Rules:

- A signature **absent from this table** is treated as UNHANDLED — queue it.
- Never invent a Poryscript special, macro, or constant to satisfy a MAP row beyond
  what the row's equivalent column states.
- The `FLAG_*` / `VAR_*` names in MAP equivalents come from the flag registry (or
  the deterministic self-switch pattern) — never raw numeric IDs.

---

## MAP — emit the Poryscript equivalent

| Signature | Count | Poryscript equivalent | Notes |
|---|---|---|---|
| `setTempSwitchOn` / `setTempSwitchOff` | 345 | `setflag(<flag>)` / `clearflag(<flag>)` | Per-**map-visit** temp switch (`Game_Event#@tempSwitches`, rebuilt every map load) — **NOT** a saved self-switch. Use the `FLAG_MAP{ID}_EVENT{ID}_TS{LETTER}` pattern (**TS**, not SS); the orchestrator allocates it from the engine auto-reset-on-warp TEMP range, preserving the temporary semantics. Always `"A"` in this corpus. |
| `tsOn?` / `tsOff?` / `isTempSwitchOn?` / `isTempSwitchOff?` | — | `flag(FLAG_..._TS{L})` / `!flag(...)` | Reads the temp switch above. If wrapped in an untranslatable cooldown helper (`cooledDown?`, `expired?`, `expiredDays?`), queue that branch instead. |
| `pbSetSelfSwitch` | 336 | `setflag(<self-switch flag>)` / `clearflag(...)` | Args `(event, switch, value)`; `value` 0 → clear, else set. Same per-event flag pattern as code 123. |
| `pbSet` / `setVariable` | 46 | `setvar(VAR_*, n)` | Sets an event/game variable. |
| `$game_variables[N]=...` | 78 | `setvar(VAR_*, n)` when RHS is a literal | If the RHS is an expression (e.g. `$Trainer.party.length`) with no Poryscript analogue → UNHANDLED. |
| `Kernel.pbReceiveItem` / `pbReceiveItem` | 40 | `giveitem(ITEM_*, qty)` | Item symbol → `ITEM_*` constant (Phase 2 item map). |
| `Kernel.pbItemBall` | 46 | `giveitem(ITEM_*, qty)` | Ground item-ball pickup; same as `giveitem`. The one-time guard is the event's self-switch. |
| `$PokemonBag.pbDeleteItem` / `pbDeleteItem` | 27 | `removeitem(ITEM_*, qty)` | Removes `qty` of an item from the bag (`130_PScreen_Bag.rb`). Item symbol → `ITEM_*` (Phase 2 map); `qty` defaults to 1. |
| `pbAddPokemon` / `pbAddPokemonSilent` | 32 | `givemon(SPECIES_*, level)` | Species symbol → `SPECIES_*`. `Silent` variant suppresses the fanfare — emit `givemon` either way. |
| `pbPokemonMart` | 48 | `pokemart(<list label>)` | Opens a shop with the given item list; define the item list as a Poryscript `mart` data block. |
| `pbPokemonBerryMart` | 3 | `pokemart(<list label>)` | Same as `pbPokemonMart`. |
| `pbTrainerIntro` | 247 | (trainer pre-battle text) | Sets the intro line for the following `trainerbattle_single`; fold into that call's "before" text rather than emitting standalone. |
| `pbTrainerEnd` | 250 | (trainer post-battle text) | The defeat/after line for the preceding battle; fold into `trainerbattle`'s "defeat" text. |
| `Kernel.pbMessage` | 6 | `msgbox("...")` | Same as Show Text (101). |
| `pbHealAll` | 3 | `healparty` | Full party heal. (Code 314 "Recover All" maps the same way.) |
| `pbEraseThisEvent` | 17 | `removeobject(LOCALID)` + `setflag(<SS flag>)` | Removes the event for the rest of the session; pair with the self-switch guard so it stays gone. |

---

## STRIP — emit nothing

| Signature | Count | Why it's safe to drop |
|---|---|---|
| `pbCallBub` | 3456 | Cosmetic speech-bubble emote: sets `$talkingEvent`/`$Bubble`/`$Numbubbles` globals an emote routine reads later (`170__PSystem_Utilities.rb`). No game state. (Emote fidelity is an open follow-up — revisit mapping to a pokeemerald field emote later.) |
| `set_fog2` | 82 | Fog-layer overlay (matches code 206 "Change Fog Opacity", already tagged Strip). No GBA analogue. |
| `XInput.vibrate` | 54 | Gamepad rumble. No GBA analogue. |
| `pbSEPlay` | 19 | Plays a sound effect (`048_AudioPlay_v17.rb`). Audio plumbing — same disposition as Play SE (249/250); where an SE is meaningful (a door/warp), its host action reproduces it. No game state. |
| `pbPlayCry` | 26 | Plays a Pokémon's cry (`170__PSystem_Utilities.rb`). Cosmetic audio flavor; no game state. (Possible later fidelity: pokeemerald `playmoncry` — same status as the `pbCallBub` emote follow-up.) |
| `$scene.spriteset.addUserSprite` | 17 | Pushes a custom sprite onto the event scene's sprite list (`061_EventScene_v17.rb`). Cosmetic visual overlay; no game state. |
| `$game_map.need_refresh` (`=true`) | 34 | RPG Maker tile/event refresh bookkeeping; meaningless on GBA. |
| `pbRemoveDependency2` / `Kernel.pbRemoveDependency2` / `pbAddDependency2` / `Kernel.pbAddDependency2` | 107 | Follower/dependent-NPC bookkeeping (e.g. partner trailing the player). Cosmetic for conversion; no party/state effect. |
| `Kernel.pbSetPokemonCenter` | 66 | **Sets the respawn point to the current map/x/y/dir** (`101__PField_Field.rb:1666`). This is captured deterministically by §2.8 `metadata.py` as `HealingSpot` and wired in Phase 5 — it is **not** event-driven on our side, so the event call is redundant. (Divergence from the calibration plan's initial `→setrespawn` guess: `setrespawn` needs a map-specific `HEAL_LOCATION_*` constant the agent can't derive from the event JSON; respawn comes from metadata instead. Flagged for gate review.) |
| `Kernel.pbSetHealingSpot` | 14 | Same as above — sets `$PokemonGlobal.healingSpot`; handled by §2.8 metadata. |
| `$game_map.replace_tileset` | 3 | Runtime tileset swap (visual); Phase 5 tileset concern, not event logic. |

---

## UNHANDLED — queue it (do not guess)

| Signature | Count | What it does | Why queue |
|---|---|---|---|
| `pbPokeCenterPC` | 21 | Opens the PC storage/box UI (`140_PScreen_Storage.rb:2648`). | pokeemerald's PC is opened by a dedicated tile-script/special, not a simple field command; wiring is a Phase 5/6 overworld concern. Verify before mapping. |
| `pkmn.pbLearnMove` / `pok.pbLearnMove` | 87 | Teach a specific move to a chosen party Pokémon (Move Tutor / story move). | Needs the party-mon selection + move-teach flow; no clean single Poryscript command. |
| `pbPhoneRegisterBattle` / `pbPhoneRegisterNPC` / `pbPhoneIncrement` | 54 | Pokégear/phone registration & rematch tracking. | No phone/pokegear feature wired yet (engine). |
| `pbBerryPlant` | 55 | Berry-tree planting/growth/harvest interaction. | Berry-tree mechanic not yet wired (engine). |
| `pbChoosePokemon` / `pbChooseNonEggPokemon` / `pbChooseAblePokemon` / `pbChooseMegaPokemon` / `pbChooseNuclearCurePokemon` | ~40 | Open the party menu and return a chosen Pokémon. | Needs party-selection flow + downstream use of the result; too contextual to auto-map. |
| `Kernel.pbRockSmashRandomEncounter` | 68 | Roll a wild encounter after Rock Smash. | Field-move encounter hook; engine feature. |
| `pbCaveEntrance` / `pbCaveExit` / `pbCaveEntranceEx` | 102 | Toggle cave darkness / Flash radius. | Darkness/Flash overlay is an engine feature (Phase 6). |
| `pbBridgeOn` / `pbBridgeOff` | 67 | Enter/leave an over-or-under bridge layer. | Bridge layering is an engine/metatile-behaviour feature. |
| `pbSetEventTime` | 63 | Stamp an event with the current in-game time. | Time-of-day state; verify against the day/night feature before mapping. |
| `Kernel.pbNoticePlayer` | 251 | Trainer turns toward & walks up to the player, with an "!" exclaim (`170__PSystem_Utilities.rb:1046`). | The exclaim+approach is automatic inside pokeemerald `trainerbattle`; standalone use needs contextual `applymovement` we can't synthesize reliably. |
| `pbRegisterPartner` / `pbDeregisterPartner` | 34 | Add/remove a multi-battle ally trainer. | Tag-battle partner system; engine feature. |
| `pbStartTrade` | 5 | In-game NPC trade. | Trade flow not wired (engine). |
| `pbShowMap` | 18 | Opens the region/town map UI (`132__PScreen_RegionMap.rb`). | A menu screen, not a field command; verify against the Phase 5 town-map work before mapping. |
| `pkmn.setAbility` / `pkmn.setItem` | 28 | Set a chosen party Pokémon's ability slot or held item (`122__PokeBattle_Pokemon.rb`). | Operate on a selected party mon (usually after `pbChoosePokemon`); no field-script command sets ability/held item on an arbitrary slot. |
| `$PokemonGlobal.nextBattleNuclearHorde` | 17 | Flags the next wild battle as a Nuclear horde. | Nuclear horde battles are an unbuilt engine feature (Phase 6). |
| `pbReceiveMysteryGift` | 11 | Mystery Gift delivery. | Feature not wired. |
| `pbSlotMachine` / `pbVoltorbFlip` / `pbLottery` / `pbSetLotteryNumber` | ~28 | Game-corner / lottery minigames. | Minigames not wired (engine). |
| `pbDayCare*` (`Deposit`/`Withdraw`/`Choose`/`GenerateEgg`/…) | ~12 | Day-Care deposit/breeding flow. | Day-Care not wired (engine). |

---

## Ruby control-flow & expression fragments (not script calls)

Some "signatures" in the inventory are just fragments of multi-line Ruby that the
deserializer split across 355/655 lines — not callable commands:

- Keywords `if` / `elsif` / `else` / `end` / `while` / `for` / `return` / `next` —
  these are the *control flow around* a script block. Reconstruct the intent from
  the surrounding lines and express it with Poryscript `if/elif/else` or a labeled
  `goto`; do not queue the keyword itself.
- `(non-identifier)` and bare lowercase tokens (`i`, `x`, `p`, `poke`, `pkmn`,
  `result`, `stat`, `trainer`, `id`, …) are assignment targets / loop variables
  inside a larger expression. Read the full line in the event JSON before deciding;
  if the whole statement has no game-state effect, STRIP it; if it does but has no
  equivalent, queue the statement (not the token).
- `pbGet(N)` reads game variable N (`170__PSystem_Utilities.rb` → `$game_variables[N]`)
  and `pbGetPokemon(id)` returns the party Pokémon at the index in variable `id`.
  These are **accessors used inside a larger statement** — translate the whole
  statement (e.g. `if pbGet(43) == 2` → `if (var(VAR_*) == 2)`), never the getter alone.
- Pokémon-object mutation chains (`poke.ev[...] = …`, `poke.calcStats`, building or
  editing a mon's stats/EVs/ability/item across several lines) are fragments of a
  custom routine with **no field-script equivalent** → queue the whole statement as
  UNHANDLED.
