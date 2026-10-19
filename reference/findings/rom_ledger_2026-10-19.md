# ROM ledger and engine-change census (2026-10-19)

Evidence for `reference/engine_layers_i3_i5.md`. These are measurements, not
decisions. Five read-only research passes produced them, against the
CH01–CH08 build (24 Uranium maps, 35 Uranium species, 26 Uranium trainers).
Scratch parsers and JSON are in `output/scratch/i3/`.

Method:
- Sizes come from `engine/pokeemerald.map` and `arm-none-eabi-nm` on
  `engine/pokeemerald.elf`.
- Most `.s`/`.incbin` labels carry no ELF size, so their size is the gap to
  the next symbol.
- Content is assigned to a category by symbol-name prefix.

Treat each figure as ±a few percent.

## 1. Where the ROM goes

**ROM in use: 27,844,032 B (26.55 MiB) of 32 MiB, so 5.45 MiB is free.**

| Object | Bytes | What it actually is |
|---|---|---|
| `data/sound_data.o` | 10,539,908 | **Cries 9,504,720** (Uranium's 35 are 172,156 of that). Direct-sound samples 753,700, voicegroups 247,092, cry tables 28,656, song table 4,880. |
| `src/pokemon.o` | 6,169,448 | Front pics 1.54 M, icons 1.49 M, follower overworld pics 1.09 M, back pics 0.91 M, `gSpeciesInfo` 0.42 M, dex/evolution literals 0.25 M, learnsets 0.16 M, palettes 0.18 M, footprints 0.03 M |
| `src/tilesets.o` | 1,095,052 | Stock ≈ 714 K, Uranium ≈ 381 K |
| `data/event_scripts.o` | 1,085,891 | Stock map scripts and their text ≈ 1,077 K. Uranium ≈ 9 K. |
| `src/event_object_movement.o` | 1,038,944 | Overworld sprites: stock NPC sprites ≈ 495 K, Uranium 394 K |
| `src/graphics.o` | 961,344 | UI, battle, intro and other graphics |
| `data/maps.o` | 753,900 | Layout block data. Stock ≈ 667 K (785 repacked layouts, still shipped), Uranium 66 K. |
| `src/fonts.o` | 432,128 | Japanese-only glyph sets are 131 K of this |
| `src/tileset_anims.o` | 343,496 | Stock ≈ 110 K, Uranium ≈ 234 K |
| `src/trainer_slide.o` | 268,376 | **≈ 266 K of zero pointers.** See §4. |
| `src/data.o` | 259,692 | `gTrainers` 185 K plus stock parties |
| `data/battle_anim_scripts.o` | 253,112 | Move animations |
| `sound/songs/midi/*.o` (530 objects) | 684,080 | 210 songs (651 K) and 269 sound effects (31 K) |

**Correction to I5 (2026-10-16).** I5 listed `sound_data.o` at 10 MiB as
"stock Emerald music". In fact **90% of it is Pokémon cries**. All stock music
put together is about **1.7 MB**: songs 0.68 MB, samples 0.75 MB, voicegroups
0.25 MB. This changes #22's audio budget arithmetic.

**Species-related data is about 15.4 MB, 55% of the ROM**, and nearly all of it
belongs to the ~1,537 stock species Uranium never uses.

## 2. What Uranium reuses from stock (must survive any strip)

From `reference/uranium_id_map.json` and grep over generated output:

| Kind | Uranium total | Maps to a stock constant | Needs new engine data |
|---|---|---|---|
| Species | 201 | **35** canon species, plus their evolution and form partners | 166 |
| Moves | 637 | 605 | 32 (the Nuclear moves and others) |
| Items | 607 | 497 | 110 (#41) |
| Abilities | 210 | 191 | 19 |
| Types | 19 | 18 | 1 (Nuclear) |

The 35 canon species:
- Ampharos, Arbok, Aromatisse, Buizel, Corsola, Cottonee, Dunsparce, Eevee
  and all 8 eeveelutions.
- Ekans, Flaaffy, Floatzel, Gengar, Gligar, Gliscor, Gyarados, Lombre, Lotad,
  Ludicolo, Magikarp, Mankey, Mareep, Misdreavus, Mismagius, Primeape,
  Sableye, Spritzee, Whimsicott.

Other stock content the generated output names today:
- **Overworld sprites:** `OBJ_EVENT_GFX_{ITEM_BALL, BERRY_TREE, POKE_BALL, PUSHABLE_BOULDER}`.
- **Trainer classes:** 13 stock `TRAINER_CLASS_*`, plus stock encounter-music ids.
- **Music:** `MUS_LITTLEROOT` as the placeholder on every map, and `MUS_OBTAIN_ITEM`.
- **Map section:** `MAPSEC_LITTLEROOT_TOWN` as the placeholder (#140).
- **Stock script labels:** `EventScript_PC`, `EventScript_RockSmash`, five `Common_EventScript_*` gift-mon helpers.
- **Specials:** `SetUnlockedPokedexFlags`, `EnableNationalPokedex`.
- **Stock flags:** `FLAG_TEMP_11..1F`, `FLAG_SYS_*`, `FLAG_BADGE0n_GET`.
- **Stock vars:** `VAR_RESULT`, `VAR_TEMP_*`, `VAR_0x800x`.

Uranium maps use **no** stock tileset. Stock tilesets are reached only through
the 785 stock layouts.

## 3. Stock systems (code), and how entangled they are

The code for Emerald's own game systems is **small next to the data**, and the
big systems are **heavily wired into core files**:

| System | ≈ ROM | Config switch to remove it | Entanglement |
|---|---|---|---|
| Battle Frontier (all facilities) | 0.46 MB incl. maps and scripts | none | High: ~70 core `.c` files, battle engine, `pokemon.c`, `field_specials.c`; 2.3 KB of SaveBlock2 |
| Union Room / link / trade | 0.22 MB | none | High: `main.c` VBlank, every battle controller; `trade.c` also runs in-game NPC trades, which Uranium uses |
| Mauville Bard / Easy Chat | 0.22 MB | `PHONEMES_SHARED` shrinks it | Medium |
| Contests | 0.14 MB | none | Medium: contest fields live in the move table and the Pokémon substruct |
| Pokénav / Match Call | 0.13 MB | `FREE_MATCH_CALL` frees save space only | Medium: called every step and from the start menu |
| TV / Lottery / Lilycove Lady | 0.12 MB | none | Medium |
| Intro, title, Rayquaza scene | 0.10 MB | — | Low (already bypassed) |
| Secret bases, Pokéblocks, Game Corner, Safari, minigames, Mystery Gift, credits, Hall of Fame, roamers, braille | 0.03–0.07 MB each | only `FREE_*` save switches | Low to medium |
| Debug menus | 0.074 MB | `make release` | none |

- The `FREE_*` switches in `config/save.h` reclaim **save bytes, not ROM**.
- No expansion switch removes Frontier, Contests, Pokénav, Link, TV, Safari or
  Secret Bases as a whole.

The only ROM-removing switches are:
- `species_enabled.h` (`P_GEN_n_POKEMON`, `P_FAMILY_*`, form switches);
- `P_CRIES_ENABLED`, `P_FOOTPRINTS`;
- `OW_POKEMON_OBJECT_EVENTS`;
- `PHONEMES_SHARED`;
- `DEXNAV_ENABLED`, the follower switches;
- `RELEASE`.

## 4. Strip levers, measured

"Recoverable" means what Uranium could drop. It already nets out what Uranium
reuses.

| Lever | Mechanism | Recoverable | Status |
|---|---|---|---|
| **Disable unused species families** | `P_FAMILY_*` = FALSE for every family outside the 35 canon species' families. `SPECIES_*` ids are not gated (0 gate sites in `constants/species.h`), so nothing renumbers. `gSpeciesInfo` keeps one slot per id. | **≈ 14 MB** (cries ≈ 9.2, pics/icons/palettes ≈ 3.9, follower overworld pics 1.1, learnsets/dex ≈ 0.35) | Built into expansion; rpg2gba sets none. Not yet built with Uranium's appended species. |
| `OW_POKEMON_OBJECT_EVENTS` = FALSE | Drops per-species overworld sprites. Nothing in the pipeline uses `OBJ_EVENT_GFX_SPECIES`. | 1.17 MB (mostly inside the line above) | Config only |
| **Stub stock layouts in chapter builds** | `phase5._stub_stock_layout_bins` already exists. Chapter builds call `repack_stock_layouts` instead and ship all 785 stock layouts. | 0.67 MB | Walker path only today |
| Stub stock tilesets | Repoint the stubbed layouts at one stub tileset in `layouts.gen.json` | ≈ 0.8 MB (tiles, metatiles, animations) | New, same overlay pattern |
| Stub stock map scripts and events | Overlay `event_scripts.s`'s per-map includes with label-only stubs. Keep the shared `data/scripts/*.inc` labels the engine calls. | ≈ 1.1 MB | New. Needs an overlay hook in `event_scripts.s`. |
| Stock music | Point unused `song_table.inc` rows at a stub song. Prune voicegroups and samples nothing kept still uses. | ≤ 1.5 MB | Waits on #22 |
| Trainer-slide tables | `sTrainerSlides[DIFFICULTY][TRAINER_PARTNER(PARTNER_COUNT)][SLIDE]` (`trainer_slide.c:59`) is sized by `MAX_TRAINERS_COUNT` and is empty. Our raise from 864 to 1280 added ≈ 70 K; the whole table is ≈ 210 K of zeros. | 0.07–0.21 MB | Sparse lookup = baseline engine change (ask) |
| Release build | `make release` drops the debug menus | 0.07 MB | Flag |
| Japanese fonts | Not referenced by an English build? Unverified. | ≤ 0.13 MB | Unverified |
| Compile out Emerald systems | Frontier, link, contests and so on | ≈ 1–1.5 MB total | High entanglement, no switch. Not needed for budget. |

**Budget outlook.**
- **Need.** The 2026-07-14 audit estimated the full Uranium corpus at
  8.5–11 MB more. The remaining 166 Uranium species add about 1.2 MB more
  (≈ 6.9 KB each, measured on the staged 35).
- **Supply.** Today there is 5.45 MiB free. The species lever alone adds
  ≈ 14 MB, for ≈ 19 MB of headroom.
- **Result.** The full game fits with room for real audio, and nothing else has
  to be stripped.

### 4a. Measured (experiment, 2026-10-19)

**Setup.** One throwaway build on the CH01–CH08 chapter assembly, reverted
afterwards (the engine is back to 27,844,048 B and the tree is clean).
- **Species:** in `species_enabled.h`, all `P_GEN_n_POKEMON` were set FALSE,
  then the 15 families of Uranium's 35 canon species were set back to TRUE:
  Ekans, Mankey, Gastly, Magikarp, Eevee, Mareep, Misdreavus, Dunsparce,
  Gligar, Corsola, Lotad, Sableye, Buizel, Cottonee, Spritzee.
- **Layouts:** the chapter assembler called `_stub_stock_layout_bins` instead
  of `repack_stock_layouts`.
- Scripts: `output/scratch/i3/snap.py`, snapshots `snap_*.json`.

| Build | ROM used | Change |
|---|---|---|
| Baseline (CH08 chapter ROM) | 27,844,048 B (26.55 MiB) | — |
| + species profile | 13,391,968 B | **−14,452,080 B** (`sound_data.o` −9.08 MB, `pokemon.o` −5.37 MB) |
| + stock layouts stubbed | **12,744,356 B (12.15 MiB, 38%)** | −647,612 B (`maps.o`) |
| + the 15 canon families off too (build only) | 12,256,912 B | −487,444 B |

What the experiment showed:
- **It compiled first time**, with Uranium's appended species. No errors.
- **CH08 gen suite 498/498 from boot** on the species + layout build, the same
  as the full ROM (`output/playtest-i3exp/`).
- **Save structures unchanged:** `gSaveblock1` 0x3cb0, `gSaveblock2` 0xfac,
  `gPokemonStorage` 0x85e0. Old saves still load.
- **`gSpeciesInfo` keeps its full size**, 0x66224 B. Slots stay, data goes.
- **Spot-checked symbols:** the Uranium species, `Cry_Eevee`, `Cry_Sylveon`
  (a cross-generation evolution) and `Cry_Gliscor` are present. Pikachu and
  Treecko are gone.
- **The canon families cost ≈ 0.49 MB.** Whose art they use is a fidelity
  question, not a space one.
- **Not exercised:** the national-dex UI scrolling over disabled species. The
  suite checks dex counts, not the dex screen.

## 5. How the pipeline writes into the engine today

**Every write is additive and gitignored.** No build step edits a tracked
stock file in place; `git status` stays clean after assembly.

There are three mechanisms:
1. **About 49 include hooks** (37 C/header, 12 asm/Makefile).
   - Each one is a committed, fenced `#include` of a gitignored generated
     file.
   - `engine/RPG2GBA_VENDOR.md:141` says "roughly 16". That count is stale.
2. **Overlays.** A gitignored `*.gen.json` copy of a stock table, rebuilt from
   the pristine file every run, for:
   - `map_groups`
   - `layouts`
   - `wild_encounters`
   - `heal_locations`
   - `all_learnables`

   The Makefile prefers the overlay when it exists.
3. **New directories** beside stock ones: `data/maps/<Dir>`,
   `data/layouts/<Dir>`, tilesets, graphics.

New ids are **appended after stock ids**:
- Species after `SPECIES_GLIMMORA_MEGA` (1572).
- Trainers after stock 854.
- Overworld graphics after 388.
- The map group last.

Phase 2's own `species_info.h` / `moves_info.h` / `items.h` / abilities
output never reaches the engine (#41). The engine is fed by later
converters (`species_converter`, `trainer_converter`, `sprite_emit`, …)
through the hooks.

Coupling to stock symbols:
- The playtest harness reads stock structs and symbols (`gSaveBlock1Ptr`,
  `gPlayerParty`, `struct Bag`, …) through `playtest/offsets.py`.
- Any engine shape must keep them.

## 6. Our engine changes, classified

`git diff 80cdfce2 HEAD -- engine/` gives 101 files, +4354/−382, plus 3
pre-import files.

| Category | Size | Contents |
|---|---|---|
| Generated hooks | 49 hooks, ~350 hook lines | species, cries, dex ids, learnsets, trainers, pics, parties, rematches, trades, tilesets, metatiles, animations, overworld sprites and palettes, move routes, connection remaps, split siblings, berry trees, flags, map aliases, map groups, layouts, encounters, heal locations, teachables |
| **Generic engine** (wanted by any RMXP conversion) | ~30 files, ~2,000 lines | streaming tile cache, windowed big-map grid, 11-bit metatile ids (≈1,200 lines together); expanded flag/var ranges; RMXP move-route interpreter; Change Graphic; warp retain-facing; connection remap; split siblings; pacing knobs; three vanilla bug fixes |
| **Hand-written Uranium facts** | ~22 files, ~1,000 lines | HM badge gates (`field_move.c`); new-game spawn, name and heal point (`new_game.c`); starter multichoice with literal names (`script_menu.h`); 4 berries + 3 key items **inserted mid-enum** in `constants/items.h` (every id from `ITEM_TM01` shifts by +4), plus `items.h`, `berry.c` and 14 art files; `FLAG_STARTING_OVER` on white-out (`overworld.c`); trainer capacity 1189/1280 (`opponents.h`); flag/var region sizes from Uranium's census (`config/rpg2gba.h`) |
| Test harness | 7 files, ~1,100 lines | map walker (gated), embedded save, intro skip (**ungated**), truck-scene skip |

Uranium names on generic mechanisms:
- `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`
- `Uranium{Get,Apply}ConnectionRemap`
- `UraniumIsSplitSiblingWarp`
- `UraniumCopyPrimaryTilesetToVramUsingHeap`
- `HEAL_LOCATION_URANIUM_START`
- `OBJ_EVENT_GFX_URANIUM_*`
- the `URANIUM_*` contract names in generated files

Global, unswitched behaviour changes:
- **Map grid and data structures:**
  - map grid bit layout (11-bit id, 1-bit collision);
  - `NUM_METATILES_TOTAL` 2048;
  - `struct Tileset` +8 B and `struct WarpEvent` 8→12 B.
- **Save, ids and boot:**
  - save layout (event ranges, trainer flags, `FREE_MYSTERY_EVENT_BUFFERS`);
  - the item renumbering;
  - the HM gates;
  - the boot path.
- **Streaming and big map:** compiled in for every map. Only data gates them
  (`FieldStream_IsLayoutStreamed`, `gBigMap.active`).

## 7. Prior art

- **No maintained "blank" pokeemerald or expansion base was found** in about 8
  searches. Treat that as not found, not as proof none exists.
- The expansion describes itself as a feature branch for existing hacks.
- **The expansion's own vanilla-map deletion** is
  `engine/docs/tutorials/how_to_delete_vanilla_maps.md`.
  - `mapjson` writes dummy values for deleted maps, so `MAP_*` references
    still compile.
  - The doc calls it "not fully tested and will likely break your game". Two
    known issues: stale script references, and a freeze when entering a map
    that connected to a deleted one.
- The pret wiki's
  [How to delete a map](https://github.com/pret/pokeemerald/wiki/How-to-delete-a-map)
  is a one-map, by-hand, follow-the-build-errors procedure.
- Upstream updates touch exactly the files a blank base would edit. For
  example, expansion 1.14.0 warned it may break `map_groups`, heal location,
  region map section and wild encounter JSON.
- Our vendor is a flat import with no upstream history (`RPG2GBA_VENDOR.md`).
  Every upgrade is already a manual re-vendor.
