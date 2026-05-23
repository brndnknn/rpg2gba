# rpg2gba Agent Memory

> This file is maintained by the build agent. Protocol + section template: `reference/memory-protocol.md`.
> Update with targeted edits, not full rewrites. Keep entries concise.
> **Eviction discipline:** keep at most the 2 most recent Last Session Summary entries and only *live*
> Open Questions here; move retired summaries + resolved-question breadcrumbs to `reference/memory-archive.md`.

---

## Current Phase

**Active phase:** Phase 2 — PBS Data Conversion (§2.0 scaffolding ✓; **§2.1 species COMPLETE**; **§2.2 moves COMPLETE**; **§2.3 items COMPLETE** — parse + emit + tests; §2.4 abilities next)

**Completed phases:** Phase 0 (Reconnaissance ✓), Phase 1 (repo scaffold ✓; pokeemerald-expansion fork **cloned 2026-05-20** at `/home/b/repos/pokeemerald-expansion`, shallow `--depth 1`, HEAD `21c24202`; `make modern` **not yet run** — needs devkitARM, so V6 fork-build still deferred but P4 struct verification is unblocked)

**Env config:** `.env` at repo root (gitignored) holds `RPG2GBA_URANIUM_SRC=/home/b/Pokemon_Uranium_132/_unpacked` and `RPG2GBA_POKEEMERALD=/home/b/repos/pokeemerald-expansion`. `pipeline.py::_load_dotenv()` loads it (shell env wins). `.env.example` committed.

**Next concrete task:** §2.4 abilities — `pbs_converter/abilities.py`. Read every `Abilities`/`HiddenAbility` byte from `dexdata.dat` for the in-use ability ID set, map IDs→internal names via `reference/ability_internal_names.json` (210 entries), mint `ABILITY_*` via `_id_map`, mark Uranium-originals (incl. CHERNOBYL) needs_engine, emit `include/constants/abilities.h` (Uranium-original constants) + placeholder handler `.c`. Mirror the focused `_Resolver` pattern from moves.py/items.py. The plan file PHASE2_PLAN.md is the canonical task list — tick `- [ ]` boxes as items land.

---

## Key File Notes

- `scripts/extract_rgssad.py` — pure-stdlib RGSSAD v1 extractor. Run it once per Uranium release to unpack `Uranium.rgssad` → `<dir>/_unpacked/`. Algorithm: XOR stream cipher, initial key 0xDEADCAFE, advance `key = key * 7 + 3`. File data uses the global key as starting seed and advances per 4-byte group within the file; the global key is *not* advanced by file data, only by name and size fields.
- `scripts/recon_maps.rb` — Marshal stubs for RMXP classes. Critical: `RPG::Event::Page` (and its `Condition`/`Graphic`) must be **nested** inside `RPG::Event`, not flat. `Color`/`Tone`/`Table` use the user-defined `_dump`/`_load` *class-method* pattern, not `marshal_dump`/`marshal_load` instance methods. Both gotchas were live bugs we hit on first run.
- `scripts/recon_scripts.rb` — section name normalization handles spaces, `*`, leading `_`, divider strings (`=====`); use `vanilla?(name)` rather than direct allowlist lookup. Inflated source is transcoded `Windows-1252 → UTF-8` (with replacement) and written via `File.binwrite` — the prior `File.write(..., encoding: 'utf-8')` raised on 85 of 260 sections leaving 0-byte files. If a future change reintroduces UTF-8-strict writes, ~85 sections will silently fail to dump.
- `reference/scripts_dump/` — verbatim Uranium Ruby source extracted from `Scripts.rxdata`. **Gitignored.** Do not commit. Treat as read-only research material.
- **P4 — pokeemerald-expansion struct shapes (verified 2026-05-20, HEAD `21c24202`).** Full field maps, struct layouts, file locations, and emit syntax (SpeciesInfo/designated initializers, level-up/egg/evolution move tables, the §2.1 Uranium→expansion field table) are in **`reference/pokeemerald_struct_shapes.md`** — consult it before any C-emit section. The gotchas still *ahead* of us, kept live here:
  - **`.teachableLearnset` is BUILD-GENERATED** by `tools/learnset_helpers/make_teachables.py` from `all_learnables.json` + TM/HM/tutor JSON — do **not** emit `sXTeachableLearnset` arrays. Affects §2.5 (feed TM/tutor compat into that generator, don't hand-write the arrays).
  - **Hidden-ability drift (affects §2.4 abilities, next):** expansion has `NUM_ABILITY_SLOTS=3` = 2 normal + **1** hidden; Uranium ships up to **4** hidden abilities/species. See Open Questions for the best-effort plan.
  - **Type enum** (include/constants/pokemon.h): `TYPE_NONE=0 … TYPE_FAIRY=19, TYPE_STELLAR=20`. **No Nuclear** (that's §2.10/Phase 6). Uranium type indices differ — map via `reference/type_internal_names.json`.
- **`items.py` (§2.3).** `items.dat` is **SerialRecords TLV** (NOT fput): header = `numrec`×(uint32 off, uint32 len), first uint32 = `numrec<<3`; each body is type-tagged fields (`i`/`"`/`0`/`T`/`F`). 9 fields: ITEMID, ITEMNAME, ITEMPOCKET(1..8), ITEMPRICE, ITEMDESC, ITEMUSE, ITEMBATTLEUSE, ITEMTYPE, ITEMMACHINE(move id). 607 items. Embedded strings = raw UTF-8, discarded (display from sidecars). Emits `gItemsInfo[]` (`src/data/items.h`) + `ITEM_*` defines + `intermediate/item_field_codes.json` worklist. **Behavior deferred to Phase 6** (same as moves): only name/price/desc/pocket/importance emitted. Pocket map is lossy (fork has 5 pockets; Medicine/Mail/Battle Items→POCKET_ITEMS; Key Items→`.importance=1`). 111 needs_engine.
- **`_naming.to_constant` now folds diacritics** (NFKD + drop combining marks): "Poké Ball" → ITEM_POKE_BALL. Added in §2.3; only 3 item names were accented, no move/species/ability names, so §2.1/§2.2 constants unaffected.
- **`moves.py` (§2.2).** `moves.dat` is flat 14-byte records (struct `"<HBBBBBBHBHB"`), indexed by move ID 0..max, zero-padded gaps. Emits `gMovesInfo[]` (`src/data/moves_info.h`) + `MOVE_*` defines (`include/constants/moves.h`) + worklist `intermediate/move_function_codes.json`. `struct MoveInfo` (fork `include/move.h`) consumed via designated initializers; `.category = DAMAGE_CATEGORY_*` (pokemon.h), `.target = TARGET_*` (battle.h enum, **no `MOVE_` prefix**), `.type = TYPE_*`, name/desc via `COMPOUND_STRING`. Target map = PBTargets (080_PBTargets.rb) → TARGET_*; flag bits (085__PokeBattle_Move.rb) → bool32 fields, positive flags only. **Effect is NOT mapped** — see Decisions.
- **`.claude/skills/pbs-convert/SKILL.md` (added 2026-05-22).** Project skill encoding the repeated Phase 2 per-section pipeline (inspect→reconcile→map→emit→worklist→test), keyed to the real helpers (`_binary`/`_naming`/`_id_map`/`_c_emit`) with §2.1–§2.3 as golden references. Advisory only — the *how*, not the *what*; deliberately does NOT track which section is next (user drives that). Includes a sub-agent delegation guide (delegate inspect/fork-lookup/test-scaffolding/validation to Haiku/Sonnet; keep resolver + fidelity decisions on the main Opus session). Triggers when asked to convert a §2.x PBS section. Built from `pbs-convert-concept.md` (High-impact rec, `recommendations/2026-05-21.md`).

---

## Decisions Made

- [2026-05-09] Decision: Source artifact is the distributed `Pokemon_Uranium_1.3.2.zip`, unpacked to `~/Pokemon_Uranium_132/_unpacked/` via `scripts/extract_rgssad.py`. Reason: Uranium was *not* open-sourced (the previous ROADMAP claim was wrong); the rgssad archive is the only path. Audio/Graphics/Fonts symlinked into `_unpacked/` so a single `RPG2GBA_URANIUM_SRC` env var works.
- [2026-05-09] Decision: Phase 2 reads compiled `.dat` files via Ruby `Marshal.load`, not text PBS. Reason: distribution ships only `.dat`. Roadmap §Phase 2 updated; new spike task added before any per-record converter starts.
- [2026-05-09] Decision: `reference/scripts_dump/`, `reference/maps_dump/`, `reference/dat_dump/` are gitignored. Reason: verbatim Uranium source per CLAUDE.md "do not commit Uranium source tree"; only derived summary docs are tracked.
- [2026-05-12] Decision: `recon_scripts.rb` writes inflated source as transcoded UTF-8 (Windows-1252 → UTF-8 with replacement) and uses `File.binwrite`. Reason: prior `File.write(..., encoding: 'utf-8')` raised `Encoding::UndefinedConversionError` on 85 of 260 sections, leaving them as 0-byte files on disk — including `175__Compiler.rb`, `124_Pokemon_ShadowPokemon.rb`, `220_Custom_Mode.rb`, `222_Gym_8.rb`, `227_Tandor_Championship.rb`. CLAUDE.md §5 already flagged the Windows-1252 hazard for Python; the Ruby side now applies the same rule.
- [2026-05-15] Decision: Custom Mode (script 220, Nuzlocke/randomizer) is **ADAPT (Phase 8)**, not STRIP. Reason: user feedback — preserving Nuzlocke/randomizer as an opt-in post-MVP feature retains a meaningful Uranium play option; no flag-registry debt since the script uses no hardcoded `$game_switches`/`$game_variables`. Implementation requires building Nuzlocke + randomizer infrastructure in the fork (no native support).
- [2026-05-15] Decision: Tandor Championship (script 227) is **CONVERT**, not ADAPT. Reason: user feedback — preserve the 4-round randomized bracket in full. Poryscript can express the bracket as `random var + lookup table` over `TCTRAINERS`/`TCTRAINERS2`; the waiting-room NPC graphic swap maps to per-event sprite changes. Higher Phase-4 effort than ADAPT but full fidelity.
- [2026-05-20] Decision: §2.2 move **effects are deferred to Phase 6**, not mapped in Phase 2. Reason: 324 distinct Essentials function codes (range 0..361) have no formula to the fork's `enum BattleMoveEffects`; guessing maps near-but-wrong constants (violates D3/§9). Every move emits `.effect = EFFECT_PLACEHOLDER` + an inline `// TODO Phase 6: function code N` comment; the raw code+chance for all 637 moves is preserved losslessly in `intermediate/move_function_codes.json` (the Phase 6 worklist). The 9 Nuclear-type moves (type idx 18) are additionally flagged `needs_engine`. Inverse Essentials flags (b=Protect / e=Mirror-Move / f=King's-Rock affinity) left at struct default (their FALSE default matches the common case; inverting risks errors).
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
- **`messages.dat` exists and is required.** All display strings (names, descriptions, Pokédex entries, dialogue) live here, NOT in the custom-binary `.dat` files. `scripts/dump_messages.rb` extracts to `reference/*.json` sidecars. The `OrderedHash` class needs a custom `_load`/`_dump` matching Essentials' `[keys, values]` Marshal format (see scripts_dump/044_Intl_Messages.rb:348-399). **Encoding:** strings are raw **UTF-8 bytes tagged ASCII-8BIT** — `dump_messages.rb` must `force_encoding('UTF-8')` and fall back to windows-1252 only if `!valid_encoding?`. (The old windows-1252→UTF-8 transcode produced mojibake like `Ã©`; fixed 2026-05-20. Breadcrumb in `reference/memory-archive.md`.)
- **Shadow Pokémon STRIP confirmed.** 0 TPSHADOW hits in 331 trainers. `shadowmoves.dat` = Array[0] (empty).
- **types.dat = 20-type effectiveness matrix.** Array[400] = 20×20. Nuclear type already encoded (Uranium extends vanilla 18 types → 20 total).
- **`dump_constants.rb` regex was all-caps-only → silently dropped mixed-case constants.** Item 211's PBS constant is the author typo `POKeBALL` (lowercase `e`), and ~70 `PBTrainers` classes are mixed-case (PkMnTRAINER_Male, LEADER_Roxanne, SWIMMERfE, POKeFAN_Female, …). Loosened the regex to `[A-Za-z][A-Za-z0-9_]*` (2026-05-21) and regenerated sidecars. **`trainer_class_internal_names.json` grew from ~60 to 130 entries — §2.6 trainers depends on this.** Species/moves/abilities/types sidecars were already complete (all-caps), so they're unchanged.
- **Item 211 = "Poké Ball"** (internal `POKeBALL`). The canonical Poké Ball lives at Uranium item id 211, not the vanilla id 1. Accent-folded to ITEM_POKE_BALL.
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
- **GBA charmap handling for accented chars.** Sidecars are now correct UTF-8 (`Pok\xE9mon`), but the GBA charmap is custom — accented chars (é, ♀, ♂) need charmap translation downstream. Phase 5/6 integration concern, not a Phase 2 emit bug. (The upstream `messages.dat` mojibake was resolved 2026-05-20; see Discoveries + `reference/memory-archive.md`.)
- **P4 content-fidelity drifts (best-effort emit per user direction; flag all at V5 manual gate):**
  - *Hidden abilities:* expansion has 1 hidden slot, Uranium has up to 4. Best-effort plan: emit first hidden ability into `.abilities[2]`; record the full Uranium hidden list per species in a sidecar + mark extras `needs_engine`. Confirm at gate whether multi-hidden is worth Phase 6 engine work.
  - *natDexNum:* Uranium has no national dex (Tandor only). Best-effort: leave `.natDexNum` at default (NONE); carry Tandor number in a sidecar for Phase 5/Pokédex wiring. Confirm at gate.
  - *eggCycles conversion:* Essentials `StepsToHatch` is total steps; expansion `.eggCycles` is 256-step cycles. Planned: `eggCycles = round(steps/256)`. Verify the divisor against a known species at gate.
  - *Species 201 "Gengar":* emit as a normal species (it has real dexdata stats) with no Tandor entry, or STRIP. Leaning emit-and-mark; confirm at gate.
- **Exact TMPBS field purpose** — `tmpbs.dat` is confirmed a Uranium-custom extra move list per species (identity resolved 2026-05-18); the exact *semantics* (move-reminder vs broad compatibility list) are still open. Determine before deciding how to represent in Phase 2 JSON output.
- **Verify pre-seeded `VAR_GYM8_*` / `VAR_TANDOR_CHAMPIONSHIP_*` names** at Phase 4 flag-registry build (proposed in Flag Registry Notes; subject to renaming based on registry policy).

*Resolved questions (species 201 = Gengar, species `.dat` = dexdata.dat, Tandor dex 200/201, no TPSHADOW rows, undumped-section accuracy) are archived in `reference/memory-archive.md`; their conclusions live in Decisions Made / Uranium-Specific Discoveries.*

---

## Last Session Summary

**2026-05-21 (§2.3 items):** Completed §2.3 items. `items.dat` turned out to be Essentials `writeSerialRecords` TLV format (not the simple fput indexed binary the plan assumed) — corrected the schema in PHASE2_PLAN.md. `items.py` parses 607 items and emits `gItemsInfo[]` (`src/data/items.h`), `ITEM_*` defines (`include/constants/items.h`), and the `intermediate/item_field_codes.json` Phase 6 worklist. Mapped only deterministic fields (name/price/desc/pocket/importance); **deferred all item behavior to Phase 6** (mirrors §2.2/D3). 111 needs_engine. Hit two shared-code fixes: (1) `dump_constants.rb` all-caps regex dropped `POKeBALL=211` and ~70 mixed-case trainer classes — loosened regex, regenerated sidecars (trainer_class sidecar 60→130 entries, **matters for §2.6**); (2) added diacritic folding to `_naming.to_constant` so "Poké Ball"→ITEM_POKE_BALL. Verified idempotent (`diff -r` clean across two runs). **41 tests pass** (5 new §2.3), ruff clean. Not yet committed. Pickup: §2.4 abilities. **Phase 2 manual review gate (§9 #1) is at the END of Phase 2 — not yet reached.**

**2026-05-20 (§2.2 moves):** Fixed the `messages.dat` mojibake in `dump_messages.rb` (UTF-8 bytes were being mis-transcoded as windows-1252) and regenerated all 22 sidecars; re-pinned the §2.1 golden fixture to the corrected `Pok\xE9mon`. **Completed §2.2 moves:** `moves.py` parses flat 14-byte `moves.dat` (637 nonzero of 639) and emits `gMovesInfo[]`, `moves.h` (`MOVE_*` defines), and the `move_function_codes.json` Phase 6 worklist. Mapped target (PBTargets→TARGET_*), category, type, and positive flags faithfully; **deferred all move effects to Phase 6** via `EFFECT_PLACEHOLDER` + worklist (see Decisions) — 324 function codes have no clean map. 9 Nuclear moves flagged needs_engine (32 moves total). Output idempotent (`diff -r` clean across two full `phase2 --clean` runs); id_map now 201 species / 637 moves / 19 types. **9 phase2 tests pass** (4 new §2.2: roundtrip, golden Tackle+Atomic Punch, effect-placeholder/worklist, Nuclear needs_engine), ruff clean. New working-pref memory: prefer temp script files over inline multi-line shell. Pickup: §2.3 items. **Phase 2 manual review gate (§9 #1) still NOT reached — it's at the END of Phase 2.** Not yet committed this session.

*Older summaries (05-20 §2.1 species, 05-18 ×2, 05-12, 05-09) are archived in `reference/memory-archive.md`.*
