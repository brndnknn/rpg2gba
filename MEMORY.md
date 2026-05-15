# rpg2gba Agent Memory

> This file is maintained by the build agent. Read CLAUDE.md for instructions on how to use it.
> Update with targeted edits, not full rewrites. Keep entries concise.

---

## Current Phase

**Active phase:** Phase 0 — Reconnaissance (in progress; awaits user review at exit gate)

**Completed phases:** Phase 1 (repo scaffold)

**Next concrete task:** User reviews Phase 0 deliverables in `reference/` (especially `phase0_summary.md` and `uranium_custom_features.md`). Several agent-generated claims in those docs need verification — see Open Questions. After review, plan the Phase 1 fork setup + the `.dat` deserialization spike that gates Phase 2.

---

## Key File Notes

- `scripts/extract_rgssad.py` — pure-stdlib RGSSAD v1 extractor. Run it once per Uranium release to unpack `Uranium.rgssad` → `<dir>/_unpacked/`. Algorithm: XOR stream cipher, initial key 0xDEADCAFE, advance `key = key * 7 + 3`. File data uses the global key as starting seed and advances per 4-byte group within the file; the global key is *not* advanced by file data, only by name and size fields.
- `scripts/recon_maps.rb` — Marshal stubs for RMXP classes. Critical: `RPG::Event::Page` (and its `Condition`/`Graphic`) must be **nested** inside `RPG::Event`, not flat. `Color`/`Tone`/`Table` use the user-defined `_dump`/`_load` *class-method* pattern, not `marshal_dump`/`marshal_load` instance methods. Both gotchas were live bugs we hit on first run.
- `scripts/recon_scripts.rb` — section name normalization handles spaces, `*`, leading `_`, divider strings (`=====`); use `vanilla?(name)` rather than direct allowlist lookup. Inflated source is transcoded `Windows-1252 → UTF-8` (with replacement) and written via `File.binwrite` — the prior `File.write(..., encoding: 'utf-8')` raised on 85 of 260 sections leaving 0-byte files. If a future change reintroduces UTF-8-strict writes, ~85 sections will silently fail to dump.
- `reference/scripts_dump/` — verbatim Uranium Ruby source extracted from `Scripts.rxdata`. **Gitignored.** Do not commit. Treat as read-only research material.

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
- **Tandor dex lower bound: ≥194 species.** Derived from `scripts_dump/213_Bambo_Reward.rb:12` SHINYCHARM threshold. Scripts never embed the total — `PBSpecies.maxValue` is computed by the compiler from `PBS/pokemon.txt`. The "~200 species, 18 Uranium-original" claim is currently unsupported; resolve in the `.dat` spike.
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

- **Which `.dat` holds the species table?** Candidates: `attacksRS.dat`, `tmpbs.dat`, possibly inside `dexdata.dat`. Resolve via the Phase 2 deserialization spike. Blocks Phase 2.
- **Exact Tandor regional dex size + fakemon count.** Lower bound from scripts is ≥194; the "~200 species / 18 Uranium-original" claim has no script-level support. Resolve in the spike against `Data/regionals.dat` + the species `.dat`.
- **Locate the Nuclear 1/8-HP-per-turn out-of-battle effect.** Not in `217_Nuclear_Forms_Moves.rb`; likely in a field/step hook or `PokeBattle_Pokemon` patch. Resolve before Phase 6.
- **Confirm no `TPSHADOW=true` rows** in `trainers.txt` (or whichever `.dat` holds trainer data) before stripping the Shadow Pokémon code path entirely. Resolve during the Phase 2 spike.
- **`tmpbs.dat`** — name suggests "temp PBS" intermediate. May be compilation scratch left in build, or may hold real data. Inspect during the Phase 2 spike.
- **Verify pre-seeded `VAR_GYM8_*` / `VAR_TANDOR_CHAMPIONSHIP_*` names** at Phase 4 flag-registry build (proposed in Flag Registry Notes; subject to renaming based on registry policy).
- ~~Re-examine other previously-undumped sections for description accuracy.~~ **Resolved 2026-05-15.** Verified `209_Achievements_System.rb` (STRIP stands; dead URL stub at 209:118 confirms online dep), `216_Custom_Trainers.rb` (description rewritten — was filename-inferred and wrong; decision still ADAPT but real porting work), `231_Beta_Save_Transfer.rb` (STRIP stands; uses hardcoded `$game_switches[113]`, `$game_switches[130]`, `$game_variables[19]` (trainer id), `$game_variables[20]` (savenumber), plus `NEW_VERSION_SWITCH` constant — only relevant if a future Phase 8 tool migrates real Uranium saves).

---

## Last Session Summary

**2026-05-12:** Phase 0 verification pass. Walked the user through the seven Phase-0 deliverables. Then attempted the four quick-win + two medium verification items from Open Questions via three parallel Opus sub-agents. First-round agents reported several files as "0 bytes / empty stubs" — investigation revealed a **dumper encoding bug** in `recon_scripts.rb`: 85 of 260 sections had failed to write because `File.write(out, source, encoding: 'utf-8')` raised on Windows-1252 bytes. Fixed by transcoding `Windows-1252 → UTF-8` and using `File.binwrite`; re-ran the dumper (all 260 sections now valid; 40 genuinely empty). Re-spawned the three Opus agents against the corrected dump. Applied verified updates to `uranium_custom_features.md` (expanded Nuclear-move list to 9 codenames, corrected Multiple Fogs #232→#223, rewrote Tandor Championship entry + downgraded CONVERT→ADAPT, added new sections for Custom Mode and Gym 8 puzzle, updated Summary Decision Matrix), `phase0_summary.md` (Tandor dex statement now lower-bound-only with citation, expanded Shadow note with code-complete-but-inert finding), `uranium_dat_inventory.md` (shadowmoves entry updated). Populated Flag Registry Notes with 4 pre-seed candidates from gym-8 and championship scripts. Pick up at: user re-reviews Phase 0 docs at exit gate, then Phase 1 fork setup + `.dat` deserialization spike. The Bambo SHINYCHARM threshold ≥194 + the missing exact species/fakemon counts are now top of Open Questions.

**2026-05-09:** Did Phase 0 reconnaissance. Wrote `scripts/extract_rgssad.py`, extracted `Uranium.rgssad` to `~/Pokemon_Uranium_132/_unpacked/`, fixed two pre-existing bugs in `recon_maps.rb` (RPG class nesting, `_load` vs `marshal_load`) and one in `recon_scripts.rb` (allowlist normalization). Ran 4/5 recon scripts (skipped `recon_pbs.py` — no PBS source). Spawned a Haiku agent to produce `reference/uranium_essentials_version.md`, `uranium_dat_inventory.md`, `uranium_custom_features.md`, `phase0_summary.md`; rewrote the dat inventory after spotting hallucinations (claimed `pokemon.dat`/`abilities.dat` that don't exist). Updated ROADMAP.md (removed wrong "team open-sourced it" claim, restructured Phase 2 around `.dat` inputs instead of PBS text).
