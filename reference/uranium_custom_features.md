# Uranium Custom Features: Conversion Decisions

This document lists Uranium-specific mechanics found in `Scripts.rxdata` and makes explicit decisions about each one for the conversion pipeline.

## Core Uranium Mechanics

### Nuclear Type
- **Where it lives:** Scripts 217 (Nuclear Forms/Moves), 224 (Nuclear Horde Battles), 225 (Nuclear Cleaning)
- **What it does:** A new type (15th type, after Steel) with custom effectiveness chart. Nuclear-type Pokémon lose 1/8 HP per turn outside battle until cured. Some Nuclear Pokémon have "clean" non-Nuclear forms available via evolution or item use.
- **Decision: CONVERT**
- **Justification:** Nuclear type is core to Uranium's identity. Phase 6 will implement `TYPE_NUCLEAR` in the pokeemerald-expansion fork with proper type effectiveness and the field effect damage system. Custom Nuclear-type move codenames identified in `scripts_dump/217_Nuclear_Forms_Moves.rb`: `GAMMARAY`, `RADIOACID`, `NUCLEARWASTE`, `HALFLIFE`, `NUCLEARSLASH`, `NUCLEARWIND`, `PROTONBEAM`, `ATOMICPUNCH`, `METALCRUNCHER`. Also references the Uranium-only ability `CHERNOBYL` (URAYNE form 2). **Note:** The 1/8-HP-per-turn out-of-battle effect is *not* defined in script 217 — it lives elsewhere (likely a field/step hook or PokeBattle_Pokemon patch). Locate before Phase 6.

### Nuclear Form Transitions
- **Where it lives:** Script 217, with data in `regionals.dat`
- **What it does:** Some Uranium Pokémon have species-like form variants (e.g., normal Chyinmunk vs. Nuclear Chyinmunk). These are tracked as form IDs in the species data, not separate species.
- **Decision: CONVERT**
- **Justification:** Pokeemerald-expansion already has a sophisticated form system. Map Uranium's form transitions to expansion's form macros. Decision point: whether to implement as Evolution (easier, uses existing engine) or pure form change (more faithful). **Recommend: Evolution method**, treating nuclear forms as "evolution" to a nuclear variant.

### Mega Evolution
- **Where it lives:** Script 123 (Pokemon_MultipleForms, has `hasMegaEvolution?` method)
- **What it does:** Standard Mega Evolution mechanic, likely integrated into the v17 engine via a community extension
- **Decision: STRIP**
- **Justification:** Pokeemerald-expansion already has full Mega Evolution support. No conversion needed; Uranium's implementation can be discarded, and the expansion's native Mega system handles the feature.

## Online / Network Features

### URANIUM_ONLINE, Online Main, POLL
- **Where it lives:** Scripts 233 (URANIUM_ONLINE), 235 (Online Main), 236 (POLL)
- **What it does:** 
  - GTS (Global Trade Station) – online Pokémon trading
  - Online battles and rankings
  - Periodic polling for server updates (mystery gifts, news, etc.)
- **Decision: STRIP**
- **Justification:** Per ROADMAP.md §0.4, online features are out of scope. GBA has no network capability without a peripheral (which is not being supported). Mystery gifts and event distributions can be implemented as static in-game events if desired (Phase 8 enhancement), but the network infrastructure itself is removed.

## UI and Scene Customization

### BW-Style UI Overhaul
- **Where it lives:** Scripts 196–205 (BW_EvolutionScene, BW_Utilities, BW_ModernMessage, BW_Bag, BW_KeyItemList, BW_Pokedex, BW_PokedexNestForm, BW_Options, BW_HallOfFame, BW_Summary)
- **What it does:** Replaces vanilla Essentials UI with Black/White generation visual style (menus, Pokédex, party screen, summary screen, etc.)
- **Decision: STRIP**
- **Justification:** Pokeemerald-expansion has its own modern UI (HeartGold/Platinum-inspired). The BW UI will be replaced by the expansion's native UI. Custom Uranium styling can be applied later (Phase 8) if desired.

### EliteBattle Scene
- **Where it lives:** Scripts 238–245 (EliteBattle_Battle, EliteBattle_Scene, EliteBattle_Animations, EliteBattle_UI, EliteBattle_Sprites, EliteBattle_BitmapWrappers, EliteBattle_Math, EliteBattle_EntryAnimations)
- **What it does:** Sophisticated 3D-ish battle animation and visual effects system, more advanced than vanilla Essentials
- **Decision: STRIP**
- **Justification:** Pokeemerald-expansion has its own native battle scene. The visual differences (sprite scaling, animation timing, effect particles) are primarily cosmetic. The expansion's battle logic is what matters; animations will differ but battles will be functionally equivalent.

### Title Screen
- **Where it lives:** Script 219 (Title Screen)
- **What it does:** Uranium-branded title screen with custom background, music, and start menu styling
- **Decision: ADAPT**
- **Justification:** Keep the concept (custom title screen) but replace Uranium-specific graphics with expansion-compatible art. The GBA ROM will have a custom title screen that fits Uranium's branding without using Uranium-specific code.

## Game Progression and Rewards

### Achievements System
- **Where it lives:** Script 209 (Achievements System)
- **What it does:** Tracks in-game milestones and unlocks rewards (similar to modern Pokémon games)
- **Decision: STRIP**
- **Justification:** Achievements are a cosmetic feature with no impact on core gameplay. Pokeemerald-expansion doesn't have a built-in achievements system, and adding one is Phase 8 polish at earliest. Core gameplay doesn't require it.

### Bambo Reward System
- **Where it lives:** Script 213 (Bambo Reward)
- **What it does:** Rewards the player for Pokédex completion (Pokédex milestones → items/species from Professor Bambo)
- **Decision: CONVERT**
- **Justification:** This is a core engagement loop. Implement as event-driven rewards (when Pokédex count reaches threshold, trigger event to give item/Pokémon). Flag registry will map "reward unlocked" switches cleanly.

### Tandor Championship
- **Where it lives:** Script 227 (Tandor Championship, 170 lines)
- **What it does:** Defines a 4-round randomized rematch bracket. `TCTRAINERS` (2 generic NPCs: Lady Angelica, Gentleman Sr. Goldkorn) + `TCTRAINERS2` (8 ex-Gym-Leaders/bosses: Maria, Davern, Cali, Sheldon, Tiko, Rosalind, Vaeryn, Hokage). `pbGenerateChampionship` randomly picks 2 + 2 and stores the bracket in `$game_variables[23]`; round counter is `$game_variables[24]`. `setupWaitingRoom` mutates map event NPC graphics (events 6/8/9/10) via `pbMoveRoute` to show upcoming opponents. Announcer dialogue uses `pbCallBub` and `Kernel.pbMessage`. Round-4 victory sets the player as Champion.
- **Decision: CONVERT**
- **Justification:** Major post-game progression worth full-fidelity replication. The 4-round randomized bracket fits Poryscript (random var + lookup table over the `TCTRAINERS` / `TCTRAINERS2` pools); the waiting-room NPC graphic swap maps to per-event sprite changes. Hardcoded vars `$game_variables[23]` (bracket) and `[24]` (round) go through the flag registry. Higher Phase-4 effort than ADAPT but preserves the championship's intended structure.

### Beta Save Transfer
- **Where it lives:** Script 231 (Beta Save Transfer)
- **What it does:** Allows players with beta version saves to transfer their progress to release versions
- **Decision: STRIP**
- **Justification:** This is a legacy compatibility feature specific to Uranium's beta releases. The GBA ROM is a fresh game; no transfer mechanism is needed.

### Scoreboard
- **Where it lives:** Script 226 (Scoreboard)
- **What it does:** Tracks leaderboard data (likely linked to online features or local high-score tracking)
- **Decision: STRIP**
- **Justification:** If it's online-dependent, it goes with other online features. If it's local-only, it's a Phase 8 nice-to-have but not critical to core gameplay.

## Utility and Support Scripts

### Custom Trainers System
- **Where it lives:** Script 216 (Custom Trainers, 243 lines)
- **What it does:** Stochastic-authored runtime trainer builder — **not** a vanilla shadow. Provides `createTrainer` / `createPokemon` (build trainers and Pokémon with arbitrary movesets at runtime, independent of `trainers.dat`), `customTrainerBattle` (a fork of `pbTrainerBattle` returning `BR_WIN`/`BR_LOSS`/`BR_DRAW` so event scripts can branch on outcome instead of relying on map self-switches; supports tag-team doubles, partner trainers, debug skip), and `createPhoneTrainer` + `getNextEvolution` (dynamically level-scale rematch parties via `pbBalancedLevel($Trainer.party)` with auto-evolution at level thresholds 15+rand(20), 35+rand(20)).
- **Decision: ADAPT**
- **Justification:** Real porting work, not zero-effort. Events calling `customTrainerBattle` need conversion-agent handling: the return-code branching translates naturally to Poryscript `if/elif` on a result var, but the dynamic level-scaling and runtime party construction will need either a custom pokeemerald-expansion helper or pre-baked party variants per level band. No hardcoded `$game_switches` / `$game_variables` IDs — uses engine globals (`$PokemonTemp.waitingTrainer`, `$PokemonGlobal.partner`).

### GenderSelect, StarterSelect
- **Where it lives:** Scripts 229–230 (GenderSelect, StarterSelect)
- **What it does:** Custom UI for choosing player gender and starter Pokémon at game start
- **Decision: ADAPT**
- **Justification:** Pokeemerald-expansion already has gender selection. The starter selection is a standard Essentials feature. Keep the logic, replace the UI assets.

### Multiple Fogs
- **Where it lives:** Script 223 (Multiple Fogs)
- **What it does:** Allows stacking and layering of multiple fog effects on a map
- **Decision: STRIP**
- **Justification:** This is a visual enhancement. Pokeemerald-expansion has its own fog and particle system. Use the expansion's native system; custom fog stacking can be added later if needed.

### Custom Mode (Nuzlocke / Randomizer / Challenge)
- **Where it lives:** Script 220 (Custom Mode, 802 lines)
- **What it does:** Implements an opt-in challenge-mode system selectable at new-game. Reopens `PokemonGlobalMetadata` to add toggles (`nuzlocke`, `randomizer`, `nuzlockedupesclause`, `nuzlockeshinyclause`, `challengemode`, `nuzlockenomart`, `nuzlockehealbattle`, `nuzlockepoisonfield`). Aliases `PokeBattle_Battle#pbThrowPokeBall`/`pbEndOfBattle`/`pbJudge` to enforce one-encounter-per-map and instant-loss on full party faint; aliases `PokeBattle_Pokemon#heal` to block revives; aliases `pbPokemonMart`/`pbPokemonBerryMart` to disable shops. Defines `Scene_Gameover`, the `MEGASTONES` whitelist, `RandomizerSettings` (with `OLD_SPECIES_BLACKLIST`/`NEW_SPECIES_BLACKLIST`/`FORM_WHITELIST`), `pbGetRandomPokemon`, and the `PokemonRulesetScene` ruleset-selection UI.
- **Decision: ADAPT (Phase 8)**
- **Justification:** Preserved as a post-MVP enhancement. Some Uranium players specifically engage with Nuzlocke / randomizer modes; cutting them removes a meaningful replay option. Implementation requires building Nuzlocke + randomizer infrastructure into pokeemerald-expansion (no native support) — deferrable until the core game is playable. No hardcoded `$game_switches` / `$game_variables` IDs to migrate, so deferring carries no flag-registry debt.

### Gym 8 Tile Puzzle
- **Where it lives:** Script 222 (Gym 8, 253 lines)
- **What it does:** Two coupled pieces. First ~95 lines port a Yanfly/Wrinkle **Spawn Event** runtime patch — monkey-patches `Spriteset_Map`, `Game_Map.spawn_event` (clones an event from any `Data/Map%03d.rxdata` and registers it), and `Interpreter.spawn_event_location`. Remaining lines define `GymWindow` (HUD overlay showing live white/black tile counts driven by `$game_variables[1]`, dismissed when `$game_variables[121]` changes) and `createPuzzle(room, ewhite, eblack)`, which holds **three hardcoded 2D puzzle layouts** (sized 5×4, 10×9, and 16×15) and spawns black/white tile events at specific map coordinates, attaching the HUD via `$scene.spriteset.addUserSprite`.
- **Decision: ADAPT**
- **Justification:** Story-critical (the player cannot beat the 8th gym leader without completing the puzzle). The underlying spawn-event engine and live HUD don't translate directly — re-express the puzzle as a Poryscript / movement-script encounter on the gym map, with the tile layouts becoming statically-placed events and the HUD becoming a `VAR_*`-driven message line. Flag registry pre-seeds: `$game_variables[1]` → `VAR_GYM8_WHITE_TILES`, `$game_variables[121]` → `VAR_GYM8_PROGRESS` (proposed names; confirm during flag-registry build).

### Actan Scripts
- **Where it lives:** Script 228 (Actan Scripts) – 32 lines, likely small utility functions
- **What it does:** Unknown from name alone; likely Uranium developer utilities or small patches
- **Decision: INVESTIGATE AND DECIDE**
- **Justification:** Need to read the actual script to determine purpose. If it's utility-only (debug, profiling), strip. If it patches core mechanics, understand and port as needed.

### Custom Input and Controls
- **Where it lives:** Scripts 7 (Win32API), 8 (Sockets), 165–167 (PSystem_Controls, XInput, Control Binding)
- **What it does:** Platform-specific I/O and gamepad input handling
- **Decision: STRIP / REPLACE**
- **Justification:** These are Windows-specific and GBA-specific I/O is handled entirely by the decomp. Discard Uranium's input code; use pokeemerald-expansion's input system.

## Minor Custom Utilities

### Klein Utilities (Animation Fix, BitmapFunctions, Stat Animation, Fly Animation, Footprints)
- **Where it lives:** Scripts 189–193
- **What it does:** Small sprite animation and rendering optimization utilities
- **Decision: STRIP**
- **Justification:** These are tweaks to the Ruby rendering system (which doesn't exist in GBA). Pokeemerald-expansion's C rendering handles these concerns at a lower level.

### Uranium Pause Menu
- **Where it lives:** Script 215 (Uranium Pause Menu) – 0 lines (empty/stub)
- **What it does:** Likely placeholder or custom menu customization
- **Decision: STRIP**
- **Justification:** Empty file. Menu system is part of standard Essentials/Expansion. Use expansion's native menus.

### FMOD Audio System
- **Where it lives:** Scripts 247–249 (FMOD, RGSS Linker, F-mod main script)
- **What it does:** Integration with FMOD audio middleware (a professional audio engine)
- **Decision: STRIP**
- **Justification:** GBA doesn't support FMOD. Audio will be handled by pokeemerald-expansion's native audio system (sappy/m4a).

## Summary Decision Matrix

| Feature | Decision | Effort | Phase |
|---|---|---|---|
| Nuclear type | CONVERT | High | 6 |
| Nuclear forms | CONVERT | Medium | 2/6 |
| Mega Evolution | STRIP | None | — |
| Online/GTS/Battles | STRIP | None | — |
| Online polling | STRIP | None | — |
| BW UI | STRIP | None | — |
| EliteBattle scene | STRIP | None | — |
| Title screen | ADAPT | Low | 1/7 |
| Achievements | STRIP | None | — |
| Bambo rewards | CONVERT | Low | 4 |
| Tandor Championship | CONVERT | Medium | 4 |
| Beta save transfer | STRIP | None | — |
| Scoreboard | STRIP | None | — |
| Custom trainers | ADAPT | Medium | 4 |
| Gender/starter select | ADAPT | Low | 7 |
| Multiple fogs | STRIP | None | — |
| Custom Mode (Nuzlocke/randomizer) | ADAPT (Phase 8) | High | 8 |
| Gym 8 tile puzzle | ADAPT | Medium | 3/4 |
| Actan scripts | INVESTIGATE | TBD | — |
| Input/Win32API | STRIP/REPLACE | None | — |
| Klein utilities | STRIP | None | — |
| FMOD | STRIP | None | — |

---

**Note on decision confidence:** CONVERT and STRIP decisions are high confidence. ADAPT decisions assume pokeemerald-expansion provides equivalent functionality (it does for most). INVESTIGATE decisions require reading the actual script code before committing.
