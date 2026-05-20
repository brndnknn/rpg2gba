# rpg2gba Agent Memory

> This file is maintained by the build agent. Read CLAUDE.md for instructions on how to use it.
> Update with targeted edits, not full rewrites. Keep entries concise.

---

## Current Phase

**Active phase:** Phase 2 — PBS Data Conversion (§2.0 scaffolding ✓; **§2.1 species COMPLETE** — parse + emit + tests; §2.2 moves next)

**Completed phases:** Phase 0 (Reconnaissance ✓), Phase 1 (repo scaffold ✓; pokeemerald-expansion fork **cloned 2026-05-20** at `/home/b/repos/pokeemerald-expansion`, shallow `--depth 1`, HEAD `21c24202`; `make modern` **not yet run** — needs devkitARM, so V6 fork-build still deferred but P4 struct verification is unblocked)

**Env config:** `.env` at repo root (gitignored) holds `RPG2GBA_URANIUM_SRC=/home/b/Pokemon_Uranium_132/_unpacked` and `RPG2GBA_POKEEMERALD=/home/b/repos/pokeemerald-expansion`. `pipeline.py::_load_dotenv()` loads it (shell env wins). `.env.example` committed.

**Next concrete task:** §2.2 moves — `pbs_converter/moves.py` (flat 14-byte `moves.dat`, `gMovesInfo[]` emit). **First fix the `messages.dat` mojibake** (see Open Questions) since moves need clean display names, then reuse `_naming.to_constant` (already proven 94% hit on moves) + `_build_resolver` pattern. The plan file at PHASE2_PLAN.md is the canonical task list — tick `- [ ]` boxes as items land.

---

## Key File Notes

- `scripts/extract_rgssad.py` — pure-stdlib RGSSAD v1 extractor. Run it once per Uranium release to unpack `Uranium.rgssad` → `<dir>/_unpacked/`. Algorithm: XOR stream cipher, initial key 0xDEADCAFE, advance `key = key * 7 + 3`. File data uses the global key as starting seed and advances per 4-byte group within the file; the global key is *not* advanced by file data, only by name and size fields.
- `scripts/recon_maps.rb` — Marshal stubs for RMXP classes. Critical: `RPG::Event::Page` (and its `Condition`/`Graphic`) must be **nested** inside `RPG::Event`, not flat. `Color`/`Tone`/`Table` use the user-defined `_dump`/`_load` *class-method* pattern, not `marshal_dump`/`marshal_load` instance methods. Both gotchas were live bugs we hit on first run.
- `scripts/recon_scripts.rb` — section name normalization handles spaces, `*`, leading `_`, divider strings (`=====`); use `vanilla?(name)` rather than direct allowlist lookup. Inflated source is transcoded `Windows-1252 → UTF-8` (with replacement) and written via `File.binwrite` — the prior `File.write(..., encoding: 'utf-8')` raised on 85 of 260 sections leaving 0-byte files. If a future change reintroduces UTF-8-strict writes, ~85 sections will silently fail to dump.
- `reference/scripts_dump/` — verbatim Uranium Ruby source extracted from `Scripts.rxdata`. **Gitignored.** Do not commit. Treat as read-only research material.
- **P4 — pokeemerald-expansion struct shapes (verified 2026-05-20, HEAD `21c24202`).** Full notes in `reference/pokeemerald_struct_shapes.md`. Headlines:
  - `struct SpeciesInfo` (include/pokemon.h) is consumed via **designated initializers** — emit only fields we have data for; everything else defaults. Data lives in `src/data/pokemon/species_info/gen_N_families.h` (all `#include`d by `species_info.h`), keyed `[SPECIES_X] = { ... }`.
  - Field map (Uranium → expansion): BaseStats→`.baseHP/.baseAttack/.baseDefense/.baseSpeed/.baseSpAttack/.baseSpDefense`; Type1/2→`.types = MON_TYPES(TYPE_A, TYPE_B)`; Rareness→`.catchRate`; BaseEXP→`.expYield` (u16); EffortPoints→`.evYield_HP/.evYield_Attack/...` (each a **2-bit** bitfield, max 3); GenderRate→`.genderRatio = PERCENT_FEMALE(x)` or `MON_GENDERLESS`(0xFF); StepsToHatch→`.eggCycles` (**needs conversion** — Essentials stores steps, expansion stores cycles ≈ steps/256); Happiness→`.friendship`; GrowthRate→`.growthRate = GROWTH_*`; Compatibility→`.eggGroups = MON_EGG_GROUPS(EGG_GROUP_A, EGG_GROUP_B)`; Abilities/HiddenAbility→`.abilities = { ABILITY_A, ABILITY_B, ABILITY_HIDDEN }`; Color→`.bodyColor = BODY_COLOR_*`; Height/Weight→`.height`/`.weight` (decimeters/hectograms — Uranium fixed-point, **needs conversion**). Names from sidecars: `.speciesName=_("..")`, `.categoryName=_("..")`, `.description=COMPOUND_STRING("..")`.
  - Move tables: `LEVEL_UP_MOVE(lvl, MOVE_X)` + `LEVEL_UP_END` terminator (`{.move=LEVEL_UP_MOVE_END,.level=0}`). Egg moves = `const u16[]` terminated by `MOVE_UNAVAILABLE`. Evolutions = `.evolutions = EVOLUTION({EVO_LEVEL, param, SPECIES_X})` (macro appends `{EVOLUTIONS_END}`). Evolution struct = `{u16 method, u16 param, u16 targetSpecies, const EvolutionParam* params}`.
  - **`.teachableLearnset` is BUILD-GENERATED** by `tools/learnset_helpers/make_teachables.py` from `all_learnables.json` + TM/HM/tutor JSON — do **not** emit `sXTeachableLearnset` arrays. Affects §2.5 (feed TM/tutor compat into that generator, don't hand-write the arrays).
  - Type enum (include/constants/pokemon.h): `TYPE_NONE=0, TYPE_NORMAL=1, ... TYPE_FAIRY=19, TYPE_STELLAR=20`. **No Nuclear** — that's §2.10/Phase 6. Uranium type indices differ; map via `reference/type_internal_names.json`.
  - **Drift — hidden abilities:** expansion has `NUM_ABILITY_SLOTS=3` = 2 normal + **1** hidden. Uranium ships up to **4** hidden abilities/species. See Open Questions.

---

## Decisions Made

- [2026-05-09] Decision: Source artifact is the distributed `Pokemon_Uranium_1.3.2.zip`, unpacked to `~/Pokemon_Uranium_132/_unpacked/` via `scripts/extract_rgssad.py`. Reason: Uranium was *not* open-sourced (the previous ROADMAP claim was wrong); the rgssad archive is the only path. Audio/Graphics/Fonts symlinked into `_unpacked/` so a single `RPG2GBA_URANIUM_SRC` env var works.
- [2026-05-09] Decision: Phase 2 reads compiled `.dat` files via Ruby `Marshal.load`, not text PBS. Reason: distribution ships only `.dat`. Roadmap §Phase 2 updated; new spike task added before any per-record converter starts.
- [2026-05-09] Decision: `reference/scripts_dump/`, `reference/maps_dump/`, `reference/dat_dump/` are gitignored. Reason: verbatim Uranium source per CLAUDE.md "do not commit Uranium source tree"; only derived summary docs are tracked.
- [2026-05-12] Decision: `recon_scripts.rb` writes inflated source as transcoded UTF-8 (Windows-1252 → UTF-8 with replacement) and uses `File.binwrite`. Reason: prior `File.write(..., encoding: 'utf-8')` raised `Encoding::UndefinedConversionError` on 85 of 260 sections, leaving them as 0-byte files on disk — including `175__Compiler.rb`, `124_Pokemon_ShadowPokemon.rb`, `220_Custom_Mode.rb`, `222_Gym_8.rb`, `227_Tandor_Championship.rb`. CLAUDE.md §5 already flagged the Windows-1252 hazard for Python; the Ruby side now applies the same rule.
- [2026-05-15] Decision: Custom Mode (script 220, Nuzlocke/randomizer) is **ADAPT (Phase 8)**, not STRIP. Reason: user feedback — preserving Nuzlocke/randomizer as an opt-in post-MVP feature retains a meaningful Uranium play option; no flag-registry debt since the script uses no hardcoded `$game_switches`/`$game_variables`. Implementation requires building Nuzlocke + randomizer infrastructure in the fork (no native support).
- [2026-05-15] Decision: Tandor Championship (script 227) is **CONVERT**, not ADAPT. Reason: user feedback — preserve the 4-round randomized bracket in full. Poryscript can express the bracket as `random var + lookup table` over `TCTRAINERS`/`TCTRAINERS2`; the waiting-room NPC graphic swap maps to per-event sprite changes. Higher Phase-4 effort than ADAPT but full fidelity.
- [2026-05-15] Decision: Custom Trainers (script 216) effort/phase upgraded from "None/2" to "Medium/4". Reason: original doc described it as "no custom code needed beyond standard data conversion" based on the filename; agent verification against the corrected dump showed it's a Stochastic-authored runtime trainer builder (`createTrainer`, `customTrainerBattle` with `BR_WIN`/`LOSS`/`DRAW` return codes, dynamic level-scaling rematches) — real Phase 4 conversion-agent work.

---

## Uranium-Specific Discoveries

- **Essentials version: v17.** Evidenced by 29 sections suffixed `_v17` in `Scripts.rxdata`. See `reference/uranium_essentials_version.md`.
- **No PBS source files ship.** Only Essentials' compiled `.dat` files are distributed — see `reference/uranium_dat_inventory.md`.
- **No `pokemon.dat`/`abilities.dat` despite Essentials convention.** Species data lives somewhere else in Uranium's Data/ — candidates are `attacksRS.dat`, `tmpbs.dat`, or inside `dexdata.dat`. **Open question — needs spike before Phase 2.**
- **Map/event scale:** 199 maps, 5,301 events, 8,429 event pages. 132/199 maps have at least one page with ≥30 commands.
- **Scripts.rxdata has 260 sections;** ~13 are clearly Uranium-original (Nuclear_*, URANIUM_*, Bambo, Tandor, Custom_Trainers, GenderSelect, StarterSelect, etc.). See `reference/scripts_index.md` ⚠ flags. Note: `220_Custom_Mode.rb` and `222_Gym_8.rb` were in the dump but missed in the agent's `uranium_custom_features.md` summary.
- **Audio middleware: FMOD.** Uranium uses FMOD via DLL (`fmodex.dll`), wrapped by scripts 247–249. Strip — GBA cannot use FMOD.
- **EliteBattle and BW UI overrides** are third-party Essentials mods (not Uranium-original) shipped with the game; both strip on conversion since pokeemerald-expansion has its own UI/battle scene.
- **Tandor dex: 200 entries, 201 internal species IDs.** Confirmed from `dexdata.dat` (15276 bytes ÷ 76 = 201) and `regionals.dat` (200 species with Tandor numbers 1–200; 1 species has no Tandor number — identity TBD). The "~200 species, 18 Uranium-original" claim is resolved for count but fakemon identity still unconfirmed.
- **Two `.dat` binary formats.** Custom Essentials binary (`dexdata.dat`, `attacksRS.dat`, `tmpbs.dat`, `evolutions.dat`, `eggEmerald.dat`, `regionals.dat`, `moves.dat`, `items.dat`, `tutor.dat`, `tm.dat`, `metrics.dat`) — parse from `Compiler.rb` write schema, no Ruby needed. Ruby Marshal (`trainers.dat`, `encounters.dat`, `connections.dat`, `metadata.dat`, etc.) — load with stubs. See `uranium_dat_inventory.md`.
- **`dexdata.dat` = main species table.** 76 bytes per species, no header, field offsets in `Compiler.rb` `requiredtypes`/`optionaltypes` dicts. Start `pbs_converter/pokemon.py` here.
- **`attacksRS.dat` = level-up learnsets.** Indexed binary: (offset, byte_length) table at front, then [level uint16, move_id uint16] pairs per species.
- **`tmpbs.dat` = Uranium-custom TMPBS field.** Same indexed format as attacksRS, single move IDs per entry. Extra move compatibility list — semantics TBD.
- **Species ID 201 = "Gengar".** Resolved 2026-05-18 via `messages.dat` dump (`reference/species_names.json[201]`). Explains why `regionals.dat` has no Tandor dex entry for ID 201 — it's a placeholder/Easter-egg slot, not a real Tandor Pokémon. Treat as STRIP (or `needs_engine` if wanted as an unobtainable curiosity) during Phase 2 species emit.
- **`messages.dat` exists and is required.** All display strings (names, descriptions, Pokédex entries, dialogue) live here, NOT in the custom-binary `.dat` files. `scripts/dump_messages.rb` extracts to `reference/*.json` sidecars. The `OrderedHash` class needs a custom `_load`/`_dump` matching Essentials' `[keys, values]` Marshal format (see scripts_dump/044_Intl_Messages.rb:348-399).
- **Shadow Pokémon STRIP confirmed.** 0 TPSHADOW hits in 331 trainers. `shadowmoves.dat` = Array[0] (empty).
- **types.dat = 20-type effectiveness matrix.** Array[400] = 20×20. Nuclear type already encoded (Uranium extends vanilla 18 types → 20 total).
- **Shadow Pokémon code is complete but inert.** `scripts_dump/124_Pokemon_ShadowPokemon.rb` (806 lines) + `145_PScreen_PurifyChamber.rb` implement the full Colosseum/XD mechanic (heart gauge, hyper mode, Relic Stone, Purify Chamber, Shadow Sky), but no script ever sets `$PokemonGlobal.snagMachine = true`, and only `224_Nuclear_Horde_Battles.rb:7-11` aliases `pbIsSnagBall?` (for Nuclear hordes, not shadows). Treat as dead code — STRIP after Phase 2 spike confirms no `TPSHADOW=true` rows in `trainers.txt`.
- **Gym 8 has a custom tile puzzle.** `scripts_dump/222_Gym_8.rb` defines three hardcoded layouts (5×4, 10×9, 16×15) plus a spawn-event runtime patch and a live HUD. Story-critical (cannot beat 8th gym without it). ADAPT — re-express as a Poryscript movement/event puzzle.
- **Tandor Championship is a 4-round randomized bracket**, not a fixed sequence. `scripts_dump/227_Tandor_Championship.rb` picks 2 from `TCTRAINERS` + 2 from `TCTRAINERS2` (former Gym Leaders). Decision changed to ADAPT (was CONVERT) since the map-event NPC graphic mutation doesn't translate directly.
- **Nuclear-type custom moves (9 codenames).** From `scripts_dump/217_Nuclear_Forms_Moves.rb`: GAMMARAY, RADIOACID, NUCLEARWASTE, HALFLIFE, NUCLEARSLASH, NUCLEARWIND, PROTONBEAM, ATOMICPUNCH, METALCRUNCHER. Plus ability CHERNOBYL (URAYNE form 2). The 1/8-HP-per-turn out-of-battle effect is NOT in script 217 — locate before Phase 6.
- **Dumper history note (2026-05-12):** original `recon_scripts.rb` left 85 sections as 0-byte files due to Windows-1252 encoding errors. Several Phase 0 "this script is empty" findings from that period were artifacts of the bug, not facts about Uranium. The corrected dump (Windows-1252 transcode + `binwrite`) leaves only 40 genuinely-empty sections.

---

## Flag Registry Notes

*Registry not yet initialized. Full state will live in `src/rpg2gba/conversion_agent/flag_registry.py`; notable assignments go here.*

### Pre-seed candidates from Phase 0 verification (uncommitted; subject to Phase 4 review)

| Uranium `$game_variables[N]` | Proposed `VAR_*` | Source script | Purpose |
|---|---|---|---|
| `[1]` | `VAR_GYM8_WHITE_TILES` | `222_Gym_8.rb` | Live white-tile counter for 8th-gym puzzle HUD |
| `[23]` | `VAR_TANDOR_CHAMPIONSHIP_BRACKET` | `227_Tandor_Championship.rb` | 4-trainer bracket array (random 2+2 selection) |
| `[24]` | `VAR_TANDOR_CHAMPIONSHIP_ROUND` | `227_Tandor_Championship.rb` | Current round 1–4 |
| `[121]` | `VAR_GYM8_PROGRESS` | `222_Gym_8.rb` | Gym-8 quest-state sentinel; HUD dismisses on change |

Bambo reward thresholds (count-of-owned, not switches/vars) from `213_Bambo_Reward.rb`: 10, 20, 30, 50, 75, 100, 125, 150, 175, **194** (SHINYCHARM, final real tier).

---

## Open Questions

- **Locate the Nuclear 1/8-HP-per-turn out-of-battle effect.** Not in `217_Nuclear_Forms_Moves.rb`; likely in a field/step hook or `PokeBattle_Pokemon` patch. Resolve before Phase 6.
- **`messages.dat` sidecars are double-encoded (mojibake).** Display strings with non-ASCII show `é`→`Ã©` (e.g. `species_pokedex.json` "PokÃ©mon", `item_names.json` "PokÃ© Ball"). `scripts/dump_messages.rb` ran a Windows-1252→UTF-8 transcode on bytes that were already UTF-8 (or messages.dat is UTF-8, not 1252). Affects all display strings across §2.1–§2.4. §2.1 species emit passes the bytes through faithfully (`Pok\xC3\xA9mon` in `species_info.h`), so it's a sidecar-source bug, not an emit bug. **Fix `dump_messages.rb` encoding + regenerate the 22 sidecars when tackling §2.2 (moves), which also needs clean display names.** Also note: GBA charmap is custom — accented chars need charmap handling downstream regardless.
- **P4 content-fidelity drifts (best-effort emit per user direction; flag all at V5 manual gate):**
  - *Hidden abilities:* expansion has 1 hidden slot, Uranium has up to 4. Best-effort plan: emit first hidden ability into `.abilities[2]`; record the full Uranium hidden list per species in a sidecar + mark extras `needs_engine`. Confirm at gate whether multi-hidden is worth Phase 6 engine work.
  - *natDexNum:* Uranium has no national dex (Tandor only). Best-effort: leave `.natDexNum` at default (NONE); carry Tandor number in a sidecar for Phase 5/Pokédex wiring. Confirm at gate.
  - *eggCycles conversion:* Essentials `StepsToHatch` is total steps; expansion `.eggCycles` is 256-step cycles. Planned: `eggCycles = round(steps/256)`. Verify the divisor against a known species at gate.
  - *Species 201 "Gengar":* emit as a normal species (it has real dexdata stats) with no Tandor entry, or STRIP. Leaning emit-and-mark; confirm at gate.
- ~~**Identity of species ID 201** — has no Tandor dex number in `regionals.dat`.~~ **Resolved 2026-05-18: "Gengar" — placeholder/Easter-egg slot.**
- **Exact TMPBS field purpose** — Uranium-custom extra move list per species (`tmpbs.dat`); likely move-reminder or broad compatibility list. Determine exact semantics before deciding how to represent in Phase 2 JSON output.
- **Verify pre-seeded `VAR_GYM8_*` / `VAR_TANDOR_CHAMPIONSHIP_*` names** at Phase 4 flag-registry build (proposed in Flag Registry Notes; subject to renaming based on registry policy).
- ~~Re-examine other previously-undumped sections for description accuracy.~~ **Resolved 2026-05-15.**
- ~~Which `.dat` holds the species table?~~ **Resolved 2026-05-18: `dexdata.dat`.**
- ~~Exact Tandor dex size.~~ **Resolved 2026-05-18: 200 entries (regionals.dat), 201 internal species IDs.**
- ~~Confirm no TPSHADOW=true rows.~~ **Resolved 2026-05-18: 0 hits in 331 trainers. STRIP confirmed.**
- ~~tmpbs.dat unknown.~~ **Resolved 2026-05-18: Uranium-custom TMPBS extra move list per species.**

---

## Last Session Summary

**2026-05-20:** Cloned the pokeemerald-expansion fork (`/home/b/repos/pokeemerald-expansion`, shallow, HEAD `21c24202`; `make modern` not yet run — needs devkitARM). Added `.env` (gitignored) + `pipeline.py::_load_dotenv()` so `RPG2GBA_URANIUM_SRC` (`/home/b/Pokemon_Uranium_132/_unpacked`) and `RPG2GBA_POKEEMERALD` resolve without shell exports; `.env.example` committed. Did P4 (struct verification → `reference/pokeemerald_struct_shapes.md`). **Completed §2.1 species C-emit:** new `_naming.py` (shared name→constant rule + fork-enum loader), rewrote evolution parser (0x3F mask + 0xC0 forward-only filter), and `pokemon.py::run()` emits `species.h`, `species_info.h` (designated initializers, inline evolutions), `level_up_learnsets.h`, `egg_moves.h`, `intermediate/tandor_dex.json`. Output validated (Orchynx Grass/Steel→Metalynx@28, Urayne Nuclear/genderless), idempotent (`diff -r` clean), needs_engine = 27 moves/17 abilities/7 items/166 species. **37 tests pass** (5 new §2.1). Found the `messages.dat` sidecar mojibake bug (logged in Open Questions) — fix in §2.2. Pickup: §2.2 moves (`moves.py`). Added working-pref memory: don't `cd` to the current dir in Bash calls. Allowlist expanded in `.claude/settings.local.json`. **Phase 2 manual review gate (CLAUDE.md §9 #1) is NOT yet reached — it's at the END of Phase 2, after all converters.**

**2026-05-18 (afternoon):** Wrote PHASE2_PLAN.md (also copied to `/home/b/.claude/plans/`). Implemented Phase 2 §2.0 scaffolding: `_binary.py` (DatReader + parse_indexed + Essentials varint string decoder), `_id_map.py` (single-source-of-truth for SPECIES_*/MOVE_*/etc., fail-loud on conflict), `_c_emit.py` (escape/banner/header-guard helpers), extended `deserialize.rb` with `dat <in> <out>` mode (Marshal-format `.dat` → JSON), wired `pipeline.py phase2 --clean` with lazy converter discovery, and `scripts/dump_messages.rb` to extract the `messages.dat` strings to 22 sidecars under `reference/`. **27/27 unit tests passing.** Found species 201 = "Gengar" via the names dump. Pickup point: implement §2.1 (`pbs_converter/pokemon.py`) — parse `dexdata.dat` (76-byte flat records) + aux files (`attacksRS.dat`, `evolutions.dat`, `eggEmerald.dat`, `tutor.dat`, `regionals.dat`, `metrics.dat`) and emit C. Tick boxes in PHASE2_PLAN.md as items land. The fork (`$RPG2GBA_POKEEMERALD`) is **not** set up yet — V6 (fork drop-in build) deferred until it is.

**2026-05-18 (morning):** Closed Phase 0 and ran the `.dat` deserialization spike. Confirmed: species data in `dexdata.dat` (76 bytes/species, 201 species); level-up learnsets in `attacksRS.dat`; `tmpbs.dat` = Uranium-custom extra move list; Shadow Pokémon STRIP confirmed (0 TPSHADOW hits, `shadowmoves.dat` empty); Tandor dex = 200 entries; two distinct binary formats (custom Essentials binary vs Ruby Marshal). Updated `uranium_dat_inventory.md` throughout. Spike script at `scripts/spike_dat_inventory.rb`. Phase 2 is now unblocked — start with `dexdata.dat` parser in `pbs_converter/pokemon.py`.

**2026-05-12:** Phase 0 verification pass. Walked the user through the seven Phase-0 deliverables. Then attempted the four quick-win + two medium verification items from Open Questions via three parallel Opus sub-agents. First-round agents reported several files as "0 bytes / empty stubs" — investigation revealed a **dumper encoding bug** in `recon_scripts.rb`: 85 of 260 sections had failed to write because `File.write(out, source, encoding: 'utf-8')` raised on Windows-1252 bytes. Fixed by transcoding `Windows-1252 → UTF-8` and using `File.binwrite`; re-ran the dumper (all 260 sections now valid; 40 genuinely empty). Re-spawned the three Opus agents against the corrected dump. Applied verified updates to `uranium_custom_features.md` (expanded Nuclear-move list to 9 codenames, corrected Multiple Fogs #232→#223, rewrote Tandor Championship entry + downgraded CONVERT→ADAPT, added new sections for Custom Mode and Gym 8 puzzle, updated Summary Decision Matrix), `phase0_summary.md` (Tandor dex statement now lower-bound-only with citation, expanded Shadow note with code-complete-but-inert finding), `uranium_dat_inventory.md` (shadowmoves entry updated). Populated Flag Registry Notes with 4 pre-seed candidates from gym-8 and championship scripts. Pick up at: user re-reviews Phase 0 docs at exit gate, then Phase 1 fork setup + `.dat` deserialization spike. The Bambo SHINYCHARM threshold ≥194 + the missing exact species/fakemon counts are now top of Open Questions.

**2026-05-09:** Did Phase 0 reconnaissance. Wrote `scripts/extract_rgssad.py`, extracted `Uranium.rgssad` to `~/Pokemon_Uranium_132/_unpacked/`, fixed two pre-existing bugs in `recon_maps.rb` (RPG class nesting, `_load` vs `marshal_load`) and one in `recon_scripts.rb` (allowlist normalization). Ran 4/5 recon scripts (skipped `recon_pbs.py` — no PBS source). Spawned a Haiku agent to produce `reference/uranium_essentials_version.md`, `uranium_dat_inventory.md`, `uranium_custom_features.md`, `phase0_summary.md`; rewrote the dat inventory after spotting hallucinations (claimed `pokemon.dat`/`abilities.dat` that don't exist). Updated ROADMAP.md (removed wrong "team open-sourced it" claim, restructured Phase 2 around `.dat` inputs instead of PBS text).
