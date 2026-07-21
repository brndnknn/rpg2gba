# Starter Species Conversion Plan — real Orchynx/Raptorch/Eletux for the S6 quiz

**Date:** 2026-07-18 · **Status:** PLANNED (user-approved scope, implementation not started)
**Replaces:** the Emerald stand-in starters (Treecko/Torchic/Mudkip) decided 2026-07-17
(SLICE1_TODO #17) — that decision was explicitly "until Uranium species land." This lands them.
**Research basis:** 4-agent fan-out 2026-07-18 (converter-state audit, engine add-a-species
surface, Uranium asset inventory, stand-in touchpoint census). Key facts below are verified
against source, not memory.

---

## 0. TL;DR

Convert the six starter-line species — **Orchynx→Metalynx (Lv28), Raptorch→Archilles (Lv29),
Eletux→Electruxo (Lv27)** — into real pokeemerald-expansion species with real battler art,
icons, and cries, staged into the engine build by the assembler as **generated overlays behind
one-time fenced include hooks** (same pattern as `uranium_flags.h` / `layouts.gen.json`).
Then swap the quiz-scene hand files to grant the real species, add `SPECIES_*` gate extras so
scripts referencing them pass the capability gate, teach the transpiler `pbHasSpecies?` →
`checkspecies` (closing SLICE1_TODO #2, the last live queue entry), and convert the real
starter overworld sprites for the Pokédex ceremony. Ends at a §9 boot-walk of S6 with the
real starters.

This is a deliberate slice-scoped **down-payment on Phase-7 debts D1/D2/D3** (see §8): the
staging emitter is append-only from day one (D1's merge-not-replace lesson), the art+cry
converters are the D2 spike, and the gate-extras wiring is D3's mechanism built for a
6-species manifest instead of the full 166.

## 1. Verified ground truth (2026-07-18)

**Species data** (from `dexdata.dat`/`evolutions.dat` via the repo's own parsers):

| Dex# | Species | Types | Abilities (hidden) | Evolution |
|---|---|---|---|---|
| 1 | ORCHYNX | Grass/Steel | Battle Armor (Overgrow) | → METALYNX, EVO_LEVEL 28 |
| 2 | METALYNX | Grass/Steel | Battle Armor (Overgrow) | — (Mega deferred) |
| 3 | RAPTORCH | Fire/Ground | Flame Body (Blaze) | → ARCHILLES, EVO_LEVEL 29 |
| 4 | ARCHILLES | Fire/Ground | Flame Body (Blaze) | — (Mega deferred) |
| 5 | ELETUX | Water/Electric | Static (Torrent) | → ELECTRUXO, EVO_LEVEL 27 |
| 6 | ELECTRUXO | Water/Electric | Static (Torrent) | — (Mega deferred) |

All abilities are vanilla constants that exist in the fork. All three lines are **2-stage**
(the "3-stage starter" assumption was wrong); the finals' Mega forms are battle-only and out
of scope. All six are already in `reference/uranium_id_map.json` (`species` map +
`needs_engine.species`).

**Assets** (`/home/b/repos/uranium-src`):
- Front battlers `Graphics/Battlers/NNN.png` are **horizontal filmstrips** of 64–84 frames,
  80×80 each. Uranium's own starter-select UI uses the **last** frame as the static resting
  pose (`230_StarterSelect.rb:58`) — that's our extraction frame.
- Back battlers `NNNb.png` are single 160×160 images. Shiny variants are **separate PNGs**,
  not palette swaps. Icons `Graphics/Icons/iconNNN.png` are 128×64 = two 64×64 frames.
- 19 of 36 battler files exceed 15 opaque colors (worst 24) → quantization required.
- Cries are `Audio/SE/NNNCry.wav`, PCM16, mixed rates (8000/11025/44100 Hz; 003 is stereo).
- Uranium ships **no footprints for any species** — nothing to convert, ever.
- Traps: `002b.PNG`/`006b.PNG`/`006_1.PNG`/`006b_1.PNG` are uppercase `.PNG`;
  `002s.png` has 77 frames vs `002.png`'s 80 (last frames may not correspond).

**Engine** (`engine/`, pinned 21c24202; in-tree tutorial `docs/tutorials/how_to_new_pokemon.md`):
- Species constants are hand-listed `#define`s; append above `SPECIES_EGG` (currently 1573)
  and bump it — never renumber existing species. `NATIONAL_DEX_*` is a separate enum in
  `include/constants/pokedex.h`.
- **Save-safety landmine:** a species left at `natDexNum = NATIONAL_DEX_NONE` that is ever
  battled causes an **out-of-bounds write** into `dexSeen[]/dexCaught[]`
  (`src/pokedex.c:4513` underflow; no guard on the send-out path). Every new species MUST
  get a real `NATIONAL_DEX_*` + `NATIONAL_DEX_COUNT` bump. `pokedex_orders.h` and Hoenn-dex
  placement are self-sized (`ARRAY_COUNT`) and safe to skip.
- `species_info.h` has a **dedicated custom-species slot** after `[SPECIES_EGG]`
  (lines 177–248, commented template) — no `P_FAMILY_*` wrapping for custom species.
- Graphics need zero Makefile edits: `INCGFX_*` declarations in
  `src/data/graphics/pokemon.h` + PNG/pal files under `graphics/pokemon/<name>/`; this tree's
  compression suffix is **`.4bpp.smol`** (not the tutorial's `.lz`). Minimal front is a
  single-frame `front.png` + `.frontAnimFrames = sAnims_SingleFramePlaceHolder`
  (Pecharunt precedent, `gen_9_families.h:8517`).
- Cries: this tree's build rule takes **`.wav` directly** (`audio_rules.mk:22`,
  wav2agb `-b -c -l 1 --no-pad`) — not the tutorial's `.aif`. New cry = wav file +
  `CRY_*` enum entry (`include/constants/cries.h`) + one row in each of the two ordered
  lists in `sound/cry_tables.inc` + `.incbin` in `sound/direct_sound_data.inc`.
- Icons index against one of **6 shared palettes** (`graphics/pokemon/icon_palettes/pal0–5`),
  chosen via 3-bit `iconPalIndex`.
- Footprint field omitted ⇒ NULL ⇒ blank dex footprint, no crash (`src/pokedex.c:4810` guard).
- TM coupling gotcha: setting `.teachableLearnset` without a matching key in
  `all_learnables.json` breaks the build with a Python `KeyError` — we set **neither** (out
  of scope), which just means no TM/tutor moves, fine at slice levels.

**Pipeline state:**
- `pbs_converter/pokemon.py` already parses everything needed (stats/learnsets/evos/dex text)
  but its Phase-2 output is Uranium-1-based-numbered, full-replacement, and **never staged**
  — the slice ROM runs pure vanilla species data today. We reuse its **parsers**, not its
  emitters.
- The capability gate (`fork_index.py:426`) rejects any `SPECIES_*` not in the pristine
  fork headers; `registry_extra_symbols()` (`fork_index.py:571`) has flag/var and
  map-constant categories only — **no species category exists yet** (D3).
- Stand-in touchpoints: `hand_conversions/Map050_EV005.pory` (announce text, lines ~324–328),
  `Map050_EV019.pory` (givemon ×3 lines 18/22/26, Theo text 52–56), `Map032_EV009.pory`
  (ceremony text — already uses Uranium names, no change), Map049 EV001 Auntie
  `pbHasSpecies?(RAPTORCH)` = the 1 live queue entry (SLICE1_TODO #2). Regression test
  pinning the RAPTORCH rejection: `tests/test_transpiler_native.py:306`.
- Quiz/counter-pick logic in the hand files is already faithful (bucket remap 0→Raptorch,
  1→Orchynx, 2→Eletux; Theo = (player−1) mod 3); **only the species constants and display
  names change.**
- **Environment note / doc drift:** `.env-paths` already points `RPG2GBA_POKEEMERALD` at the
  vendored `engine/` — the D4 cutover appears de-facto done on this machine even though
  CLAUDE.md prose still calls it pending. This plan builds against `engine/`. Confirm at
  implementation start; update CLAUDE.md §3 if confirmed.

## 2. Decisions

**User (2026-07-18):**
1. Scope = **6 species** (full lines). Megas deferred.
2. Cries = **convert the real WAVs** (this is the D2 cry spike); fall back to
   closest-vanilla mapping only if the spike fails.
3. Extras in scope: **Auntie's RAPTORCH branch** (transpiler `pbHasSpecies?` support) and
   **real starter overworld sprites** for the ceremony. TM/teachable wiring **out**.

**Lead (architecture):**
4. **Generated overlays + fenced hooks, not committed generated data.** Species data/art/cry
   artifacts are pipeline output (gitignored, staged by `assemble_pathfinder.py`); the only
   committed engine edits are small `URANIUM PATHFINDER SLICE`-fenced hook points that
   `#include`/`.include` the generated files. Keeps §4.2 idempotence and the "never commit
   generated output under engine/" rule intact.
5. **Static single-frame fronts** (last filmstrip frame, `sAnims_SingleFramePlaceHolder`).
   2-frame idle anims are a possible later polish, not slice work.
6. **Dex: minimal-but-safe with real text.** Real `NATIONAL_DEX_*` constants (mandatory per
   the landmine) + real category/height/weight/description from the already-parsed
   `species_pokedex.json` data (free). Skip dex sort orders + Hoenn dex.
7. New package `src/rpg2gba/species_converter/` owns all of this (staging emitter, battler,
   icon, cry converters). It **imports parsers from `pbs_converter.pokemon`** — no logic
   duplication, and Phase-2 emitters/goldens stay untouched.
8. Numbering = fork-append space (first new id = current `SPECIES_EGG` value, then bump
   EGG/NUM_SPECIES). Uranium-id ↔ fork-id mapping recorded in the staging manifest;
   `reference/uranium_id_map.json` stays internal-name→constant (unchanged schema).

## 3. Architecture: overlays + fenced hooks

Generated (gitignored, under `output/uranium-build/species/`, staged by assembler):

| Artifact | Staged to (engine/) | Consumed via |
|---|---|---|
| `uranium_species.h` (constants + dex enum entries as `#define`s) | `include/constants/` | fenced `#include` in `species.h` above the `SPECIES_EGG` block, with EGG redefined against the last Uranium id; fenced hook in `pokedex.h` for dex ids + COUNT (mechanism note below) |
| `uranium_species_info.h` (6 `[SPECIES_X] = {...}` entries) | `src/data/pokemon/` | fenced `#include` in the custom-species slot of `species_info.h` (~line 177) |
| `uranium_species_graphics.h` (INCGFX declarations) | `src/data/graphics/` | fenced `#include` at end of `graphics/pokemon.h` |
| `uranium_learnsets.h` (6 level-up learnsets) | `src/data/pokemon/` | included from `uranium_species_info.h` |
| `graphics/pokemon/<name>/{front,back}.png`, `{normal,shiny}.pal`, `icon.png` ×6 | `graphics/pokemon/` | INCGFX pattern rules (no Makefile edits) |
| `cries/<name>.wav` ×6 | `sound/direct_sound_samples/cries/` | fenced `.include`/rows: `cries.h` enum (before `CRY_COUNT`), `cry_tables.inc` (both ordered lists), `direct_sound_data.inc` |
| `species_manifest.json` (uranium_id ↔ fork_id ↔ constant ↔ files) | — (stays in output/) | gate extras source + tests |

Hook-mechanism notes: `pokedex.h`'s `NATIONAL_DEX_*` is an enum — the fenced hook is an
`#include` **inside the enum body** before the terminator (preprocessor-legal), with
`NATIONAL_DEX_COUNT` derived so it self-adjusts. If the count is a separate `#define`, the
generated header carries the new count. Exact shape settled at implementation; the invariant
is: **empty generated files ⇒ pristine-equivalent engine** (hooks are no-ops when the
overlay is absent — assembler writes empty stubs on clean checkouts, mirroring
`uranium_includes.inc`).

CLAUDE.md §10 check: these hooks are additive and behavior-neutral for baseline pokeemerald
(guarded by the empty-overlay invariant). The one deliberate behavior change — 6 new species
+ bumped `NUM_SPECIES`/`NATIONAL_DEX_COUNT` — is the point of the task and is user-approved
via this plan.

## 4. Work units

Each unit lands with tests per §4.6 (round-trip + golden + Uranium-quirk edge case).
Suggested delegation tier in brackets; lead owns W1 design, all engine hook edits, and merges.

**W1 — Species staging emitter** (`species_converter/stage.py`) [lead designs, Sonnet builds]
Reuse `pbs_converter.pokemon` parsers; select the 6 species; assign fork-append ids; emit
the five generated headers + manifest. Entries: real stats/types/abilities/EVs/gender/
egg-cycles/growth/egg-groups/catch-rate/exp-yield, real dex text, `.evolutions` links,
`.cryId = CRY_URANIUM_X`, gfx pointers, `.frontAnimFrames = sAnims_SingleFramePlaceHolder`,
`SHADOW`/scale fields from sensible defaults (see W2 yOffset note), **no**
`.teachableLearnset`, no footprint, `.natDexNum` real. Golden test: pinned emitted entry for
ORCHYNX + METALYNX (evolution edge). Edge test: the id-append math (EGG bump) and
empty-manifest ⇒ empty-overlay idempotence.

**W2 — Battler converter** (`species_converter/battlers.py`) [Sonnet; lead eye-gates]
Per species × {normal, shiny}: extract **last** front frame (80×80); back from the 160×160
single image. Fit to 64×64 by opaque-bbox: crop/center if content ≤64px, else integer-aware
downscale (majority-vote per the `graphics/sprites.py` precedent; backs are natively 2×).
**Joint quantization:** one 15-color+transparent palette must cover front+back together
(engine shares `gMonPalette_X` across both). **Shiny is a palette, not an image:** build the
shiny .pal by per-palette-slot color lookup — for each normal-palette index, sample the shiny
PNG's color at the same pixel positions; fail loud if shiny geometry diverges beyond a
threshold (002's 80-vs-77 frame mismatch: sample shiny from its own last frame; verify
correspondence by eye). Compute `frontPicYOffset`/`backPicYOffset` from bbox bottom-alignment
(Uranium's `metrics.dat` is unparsed; bbox-derived offsets + eye-tune beats building that
parser for 6 mons). Handle uppercase `.PNG` names case-insensitively. Output PNGs are
indexed-color against the emitted .pal. Tests: golden PNG/pal hashes for one species;
edge tests for the .PNG-case and shiny-mismatch fail-loud. **Gate: user eyeballs a
contact-sheet render (per the validate-graphics-by-eye rule) before W6.**

**W3 — Icon converter** (`species_converter/icons.py`) [Sonnet; lead eye-gates]
128×64 two-horizontal-frames → 32×64 two-vertical-frames (2× majority-vote downscale +
re-stack). Choose `iconPalIndex` by minimum total remap error across the 6 shared palettes;
remap colors to that palette. Icons are ≤13 colors pre-downscale, so this should survive —
eye-gate the result (worst case: hand-nudge specific pixels is NOT allowed; adjust the
remap metric instead). Tests: frame-restack round-trip + pinned palette choice per starter.

**W4 — Cry converter** (`species_converter/cries.py`) [Sonnet]
Normalize the 6 WAVs: stereo→mono (003), resample to one target rate (pick by inspecting
vanilla cry WAV rates in `sound/direct_sound_samples/cries/` — match the house norm),
PCM16, trim silence. Pure-Python (stdlib `wave` + resample; no ffmpeg system dep). Emit
wav files + the fenced cry-table rows via the staging emitter. Spike check: `make` must
produce a ROM where the cry plays (verified in W6's build + boot-walk). Fallback if wav2agb
output is unusable: `.cryId` → closest-vanilla mapping table (documented in the manifest),
and the cry debt returns to Phase 7. Tests: normalization round-trip (rate/channels/duration
tolerances).

**W5 — Gate extras + transpiler `pbHasSpecies?`** (`fork_index.py`, `transpiler.py`) [lead —
touches gate policy]
Add a species category to the gate extras sourced from **`species_manifest.json`** (only
staged species pass — not all 166 `needs_engine` species; an unstaged species reference must
still fail loud). Wire into `registry_extra_symbols()`/driver extras alongside flags and map
constants. Teach the transpiler the 111-condition `pbHasSpecies?(::PBSpecies::X)` →
`checkspecies`(+`VAR_RESULT` compare, per `asm/macros/event.inc:2541` semantics), resolving X
through the id map and gating through the manifest. Re-transpile Map049; the Auntie branch
leaves the queue. Flip `tests/test_transpiler_native.py:306` from pinned-rejection to
pinned-emission; add a still-rejected test for an unstaged species (e.g. URAYNE).

**W6 — Quiz-scene + ceremony swap, staging, build** [lead]
- `Map050_EV019.pory`: `givemon(SPECIES_ORCHYNX/RAPTORCH/ELETUX, 5)` per the existing
  branch mapping; fix grant/Theo text to Uranium names. `Map050_EV005.pory`: announce text.
  Remove the stand-in debt comments; `Map032_EV009.pory` text already correct.
- Overworld sprites: convert the real `PU-Orchynx/PU-Raptorch/PU-Eletux` sheets through the
  existing OW sprite pass (`sprite_pass.py`; `preview_sprite_conversion.py` already lists
  them) and update the three `npc_gfx_map.json` entries off their Chikorita/Charmander/Shinx
  stand-in shapes.
- `assemble_pathfinder.py`: stage the species overlay artifacts (table in §3) into
  `$RPG2GBA_POKEEMERALD`; add the engine fenced hooks (one-time commit); full
  `make modern`; full pytest.
- Known collateral: **embedded-save review ROMs from before this change are invalidated**
  (`NUM_SPECIES`/`NATIONAL_DEX_COUNT` resize dex flag arrays in the save layout). Fresh
  boot-walk saves only; note it in the taildrop message.

**W7 — §9 gate: S6 boot-walk retest** [user]
Taildrop the ROM with hash. Walk: quiz → announce (right species name) → grant (real
Orchynx/Raptorch/Eletux in party, sprite+icon+cry correct in summary/party) → Theo
counter-pick text → Auntie's RAPTORCH dialogue branch (Map049) → ceremony OW sprites →
(stretch) rare-candy an evolution to Lv27–29 if a debug lever exists. Art verdicts are the
user's (eye-gate), per §9.

## 5. Sequencing

W1 → W2/W3/W4 in parallel (disjoint files) → W5 (needs manifest) → W6 → W7.
W2 is the highest-risk unit (joint quantization + shiny-as-palette); do its ORCHYNX
vertical prototype first and eye-gate a contact sheet before batch-converting the other five.

## 6. Risk ledger

| Risk | Handling |
|---|---|
| Shiny PNG geometry ≠ normal PNG (breaks palette-slot sampling) | fail-loud threshold + eye check; 002's 77/80 frame mismatch is the known suspect |
| Joint front+back 15-color palette too tight (front+back quantized together) | quantizer works on the union; eye-gate; worst case accept slightly flatter backs — backs show rarely |
| Icon shared-palette remap looks wrong | eye-gate; adjust remap metric, never hand-edit output |
| wav2agb cry quality unusable | fallback: closest-vanilla `cryId` mapping, cry debt → Phase 7 |
| `NATIONAL_DEX_COUNT` bump ⇒ save-layout change | accepted; invalidates old review saves — flag in taildrop |
| Fenced hooks drift from pristine-equivalence | empty-overlay invariant + a test that stubs empty overlays and diffs preprocessed headers |
| `engine/` needs first full build (cutover follow-up) | confirm `.env-paths`/build state at W6 start; budget one clean `make modern` |

## 7. Explicitly out of scope (→ Phase-7 ledger)

Mega forms + Mega Stones; egg sprites/hatching art (001egg partial-alpha quirk moot); egg
moves; TM/teachable learnsets (`all_learnables.json` untouched — avoids the KeyError
coupling); footprints (Uranium has none); dex sort orders + regional dex placement;
2-frame front animations; the other 160 `needs_engine` species (this plan's emitter +
manifest + gate mechanism are built to scale to them at Phase 7, which is the D1/D2/D3
payoff); `metrics.dat` parsing (bbox-derived offsets for 6 mons instead).



## W7 boot-walk state (user, ROM `23c53bb3`)

Reported symptoms:
1. Quiz works when yes is chosen to begin the scene —
   however no sprite is shown and the start menu doesn't show a slot for a party.
2. If no is selected when the question about the quiz is asked, the game freezes.

## W7 investigation findings (2026-07-19, 4-agent fan-out + lead verification in engine C)

### Symptom 1 — no sprite / empty party after "yes": grant step never executes (by flow design + two real script defects)

**Species staging is NOT the problem.** Verified healthy end to end: compiled
`scripts.inc` has `givemon SPECIES_ORCHYNX/RAPTORCH/ELETUX, 5`
(`engine/data/maps/MokiTownProfessorLab/scripts.inc:871/880/889`, no stale
TREECKO/etc.); the staged overlays are real data, not stubs
(`uranium_species_constants.h` chained correctly with `SPECIES_EGG`/`NUM_SPECIES`
derived; `uranium_species_info.h` 242 lines of real `gSpeciesInfo` entries;
graphics header present). The Poké Ball machine's OW sprite also converted fine
(`OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE` = 414, wired in the gen headers,
`pics/uranium/pu_pokeballmachine.png` eyeballed OK, `flag: 0` = always spawned).

**Why the party is empty:** the quiz scene (`Map050_EV005_TestBody`) only *sets*
`VAR_POKEMONTEST` (1/2/3) and announces the result — the `givemon` lives in a
**separate object interaction**: EV019, the Poké Ball machine (object local id 3
at (14,5), `Map050_EV019_Dispatch` → Page1 `switch VAR_POKEMONTEST`). The player
must walk to the machine and press A after the quiz; nothing in the quiz flow
grants directly. **"No sprite" at the announcement is per hand-conversion
design** — the original `pbStarterSelector` fullscreen cutscene was deliberately
replaced with a plain announce msgbox, so no battler sprite was ever going to
appear there.

Two real defects found on this path:

- **Defect A — missing `releaseall` in `TestBody`** (`hand_conversions/
  Map050_EV005.pory` ~line 336; compiled `scripts.inc:509-512`). Page1 opens
  with `lockall`; the accept path `goto`s into `TestBody`, which ends on a bare
  `end`, skipping Page1's shared `fadedefaultbgm; releaseall` epilogue (that
  epilogue is only reached on the decline arm). The engine auto-unlocks *player*
  field controls when any script hits `end` (`engine/src/script.c:268`) — which
  is exactly why the user could still open the start menu — but the
  `lockall` object freeze is never undone, so **every NPC in the lab stays
  frozen until map reload**.
- **Defect B — fail-silent switch in EV019 Page1**: the
  `switch VAR_POKEMONTEST { case 1/2/3 }` has **no default arm**. With the var
  at 0 (interacting before/without the quiz, or any future regression that loses
  the var), the interaction silently does nothing — violates the fail-loud rule.
  Note EV019's dispatch is gated only on `VAR_QUEST_LOG` (0 → Page1), not on any
  quiz-completion flag, so the machine is live-but-silent pre-quiz.

**Open question for the user (next boot-walk):** after the quiz, did you walk to
the Poké Ball machine (the blue machine with the red ball top, right side of the
lab at (14,5)) and press A on it? If you did and nothing happened, that's a new
bug to trace (var write/interactability); if not, the grant flow "worked" as
converted and the issue is discoverability/fidelity.

### Symptom 2 — "freeze" on retaking the quiz after declining: ROOT CAUSE FOUND (stale ON_FRAME latch)

**User clarification (2026-07-19): the first NO does not freeze** — the decline
choreography completes fine. The failure is on the **retake**: talk to Bamb'o
again after declining and try to start the quiz — nothing can ever start it
again.

Mechanism (all verified in generated sources):

1. Declining sets `FLAG_MAP050_EVENT005_SSD`; on the next unlocked frame the
   ON_FRAME dispatcher (`Map050_dispatch.pory:83-94`) finds no guard matching
   (SSD blocks the quiz entry) and **latches `setvar(VAR_TEMP_C, 1)`** — the
   map's ON_FRAME table only fires while `VAR_TEMP_C == 0`, so per-frame
   dispatch is off for the rest of the map visit.
2. The retake script `Map050_EV005_Page3` (transpiler output, staged
   `Map050.pory:219-244`) on YES does `setflag(SSB)` + `clearflag(SSD)` and
   ends, expecting the autorun Page1 to re-fire (its SSB shortcut `goto`s
   straight into `TestBody`). **Nothing ever resets `VAR_TEMP_C` to 0**, so the
   re-fire never happens. The quiz is permanently unstartable for that map
   visit (leaving and re-entering the lab would reset the temp var and
   auto-start the test — untested by the user).

This is a **general transpiler-design bug, not a Map050 one-off**: RMXP autorun
pages re-evaluate their trigger conditions continuously; our `VAR_TEMP_C` latch
is an optimization that goes stale whenever any later script writes a symbol
used in an autorun guard.

Killed hypotheses from the earlier (mis-scoped) first-NO investigation, kept
for the record: compiled `.inc` is a bit-exact recompile (not stale); the NO
branch itself is well-formed and releases; Theo is always spawned, and
`applymovement`/`waitmovement` on an unspawned id no-op/return immediately
anyway (`script_movement.c:22-46`); missing-release can't lock input
(auto-unlock at `script.c:268`). Ledger item found en route:
`ScrCmd_applymovement` (`scrcmd.c:1307`) writes `directionOverwrite` through an
unchecked id lookup — unresolved local id = silent OOB write to
`gObjectEvents[16]`.

## W8 — fix plan (IMPLEMENTED + HARNESS-VERIFIED 2026-07-19; ROM `6d6e372a` taildropped, user retest pending)

All five steps below are done. Headless-harness verification on ROM `6d6e372a`
(scenario driver in the session scratchpad): decline → retake → quiz →
announcement → ball-machine grant → Theo counter-pick all complete with control
retained (`VAR_POKEMONTEST`=1..3, `FLAG_RECEIVED_STARTER`=1, party grows by 1);
fresh-boot immediate-accept regression also passes. Remaining: user §9
boot-walk (art/cry verdicts are eye-gates the harness can't give).

1. **DONE — `releaseall` added to `Map050_EV005_TestBody`**
   (`hand_conversions/Map050_EV005.pory`) — closes defect A (frozen lab NPCs).
2. **DONE — default arm added to EV019 Page1's switch**
   (`hand_conversions/Map050_EV019.pory`): neutral machine msgbox + early
   `release`/`end`. Investigation upgraded defect B's severity: without the
   arm, `VAR_POKEMONTEST`=0 **fell through into the whole Theo cutscene**
   (bumping `VAR_QUEST_LOG`, setting `FLAG_RECEIVED_STARTER`, no starter) — a
   sequence break, not just a silent no-op.
3. **Grant flow: keeping the Uranium-faithful two-step** (quiz → walk to the
   Poké Ball machine → A-press runs the grant + Theo counter-pick scene). The
   "no sprite/no party" symptom is consistent with the machine step simply not
   being taken (its sprite + dispatch verified healthy); revisit only if the
   retest shows the machine interaction itself failing.
4. **IN PROGRESS — retake-latch fix (the "freeze")**: staging-time re-arm pass —
   `metadata_wiring.insert_onframe_rearms` inserts `setvar(VAR_TEMP_C, 0)`
   after every write to an ON_FRAME guard-input symbol in a map's page
   scripts, wired into `stage_slice_scripts.py` with a fail-loud verifier.
   Fixes Page3's retake generically (any autorun whose guard inputs change
   mid-visit re-fires, matching RMXP's continuous condition evaluation). The
   transpile driver's reserved-var gate (no `VAR_TEMP_C` writes in
   transpiler/hand output) stays intact — insertion is downstream of it.
   In parallel, a headless-harness runtime trace (libmgba-py, script-PC watch)
   is confirming the mechanism on ROM `23c53bb3` and characterizing whether
   the user's "freeze" is a hard input lock or a soft "quiz unstartable".
5. Re-run the full 4-step chain (`transpile_driver run` → `stage_slice_scripts
   --write` → `assemble_pathfinder.py` → `make modern` — never skip the first
   two after a hand-file edit), full pytest, taildrop new ROM + hash, W7
   boot-walk retest.

## W9 — party-menu-invisible fix (2026-07-20; ROM `e20f2158` taildropped, user retest pending)

**Symptom (user walked W8 ROM `6d6e372a`):** quiz plays through; walk to the
Poké Ball machine, press A → "{PLAYER} received Orchynx!" msgbox fires — but no
battler sprite (by design) AND the START menu shows **no POKÉMON slot / no
party**. So the two-step grant flow now works (they reached the machine, hit a
case-1/2/3 arm — not the default "machine hums" arm), yet the party looked empty.

**Root cause (verified in engine C):** `givemon` → `ScrCmd_createmon`
(`asm/macros/event.inc:1042`) adds the mon to the first empty `gPlayerParty`
slot but **never sets `FLAG_SYS_POKEMON_GET`**. The START-menu POKÉMON action is
gated on that flag (`src/start_menu.c:340,359`); its only setter,
`SetDexPokemonPokenavFlags`, is marked `// unused` (`start_menu.c:283`). So the
starter *is* in the party (party count → 1 — exactly why the W8 harness "party
grows by 1" check passed) but the menu never exposes it. Essentials' party menu
is always available; Emerald gates it on this flag → a **systematic
Essentials→Emerald conversion gap**: the first `pbAddPokemon`/`givemon` in the
game must also set `FLAG_SYS_POKEMON_GET`. "No sprite" at announce stays
by-design (pbStarterSelector → msgbox, W7 finding).

**Fix:** `setflag(FLAG_SYS_POKEMON_GET)` in `hand_conversions/Map050_EV019.pory`,
placed right after the switch closes — reached only on the grant path (the
default arm ends above with `release`/`end`). Idempotent; flag pass-through
already proven (`Map032_EV009.pory:175` uses `FLAG_SYS_POKEDEX_GET`). Full
4-step chain re-run (driver → stage --write → assemble → make modern),
compiled `scripts.inc:785` carries the setflag on the grant path only; pytest
**1320 passed / 15 skipped**. ROM CRC32 `e20f2158`, taildropped as
`uranium-slice-e20f2158-starters-partyflag.gba`. **Transpiler-debt note:**
consider auto-pairing `givemon`/`giveegg` emission with a one-time
`FLAG_SYS_POKEMON_GET` set in the deterministic path so future maps don't
re-hit this — logged as Phase-7 debt, not slice-urgent. W1-W9 committed
`2b045012` 2026-07-21 (party-flag fix user-confirmed working before commit).

## W7 gate — PASSED 2026-07-21, plan CLOSED (ROM `b0b21993`)

After the W9 party-flag fix (confirmed working), the retest surfaced one more
real bug: **the quiz always resolved to Eletux, regardless of answers.**

**Root cause:** the argmax sign-test literal `32768` (0x8000) fell inside the
engine's `SPECIAL_VARS` range (`include/constants/vars.h`:
`SPECIAL_VARS_START 0x8000` .. `SPECIAL_VARS_END 0x8015`). The `compare` asm
macro (`asm/macros/event.inc`) auto-selects `compare_var_to_var` vs
`compare_var_to_value` based on whether its literal operand falls in that
range (or the temp-var range) — so `if (var(VAR_RESULT) < 32768)` silently
compiled to "compare `VAR_RESULT` against the value in `VAR_0x8000`", not the
literal. `VAR_0x8000` is the vanilla engine's own switch-statement scratch
variable (`switch`'s codegen is `copyvar VAR_0x8000, <var>; compare
VAR_0x8000, <case>` per case) — and the quiz's per-question `Tally` call uses
`switch (var(VAR_TEMP_MOVE_CHOICE))`, which left `VAR_0x8000` holding the
**last question's raw 0-2 answer index** after the 4th question. Since a
tally delta (0-4 range) is essentially never `<` a leftover 0-2 value, both
override branches (`T4>=T5` and `T3>=T4 && T3>=T5`) skipped almost every
time, leaving `VAR_POKEMONTEST` stuck at its hardcoded default (`2` =
Eletux) no matter what the player picked.

**Fix:** use `32767` (0x7FFF) instead of `32768` in the three sign-test
comparisons — same subtract-and-test-sign semantics (`A>=B` ⟺ `(A-B) <=
0x7FFF`), but 32767 sits outside both the temp-var (`0x4000`-ish) and
special-var (`0x8000`-`0x8015`) ranges, so the macro correctly emits
`compare_var_to_value`. `hand_conversions/Map050_EV005.pory`, commit
`b3b1b623`. Full chain re-run clean (transpile → stage → assemble → `make
modern`), 1320 passed/15 skipped, ROM `b0b21993` taildropped.

**User boot-walked and confirmed:** the quiz now correctly resolves to
Orchynx/Raptorch/Eletux (and evolutions) matching the player's actual
answers. This closes `STARTER_SPECIES_PLAN.md` end to end (W1-W9) and
`SLICE1_TODO.md` #2 (Auntie's RAPTORCH branch — `checkspecies(SPECIES_
RAPTORCH)` compiles clean now that the species is in the gate extras).
§9 boot-walk checklist S6 → **PASSED**.
