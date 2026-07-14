# Phase 7 Integration Plan — Reconciliation Spec (2026-07-14)

Phase 7 (ROADMAP: drop converted artifacts into the fork, resolve build
errors, boot) is where every deferred ID/data debt comes due at once. This
plan enumerates the known debts with their evidence, the reconciliation
strategy, and an order of attack — so the phase starts as execution, not
archaeology. Companion: `reference/guides/nuclear_type_spec.md` (Phase 6 lands
inside/alongside this phase per the slice model).

## The central problem: two ID universes

Phase 2 deliberately emitted **Uranium-native IDs** with reconciliation
deferred (headers say so explicitly):

- `output/uranium-build/include/constants/species.h` — 202 `SPECIES_*` at
  Uranium's 1-based Tandor ids ("overlap vanilla SPECIES_* numbering — V6
  integration must reconcile").
- `.../items.h` (607), `.../moves.h` (637), `.../abilities.h` (210) — same
  pattern.
- `reference/uranium_id_map.json` (the §4.3 SoT) already maps every Uranium
  internal name → expansion constant *name* — the reconciliation is therefore
  about **numeric identity and table merging**, not naming.

**Strategy (per concept): keep-vanilla → fork's existing constant;
Uranium-original → new enum entry appended after the fork's last id.**
Precedent and the verification pattern both exist:
`reference/findings/item_dupe_census_2026-07-04.md` proved all 496
kept-vanilla items resolve in the fork (472 modern + 24 pre-Gen-VI aliases)
and 103 are true originals. Phase 7 task one is running the same census for
species / moves / abilities and regenerating the Phase-2 emitters to target
fork ids (a converter change, not output editing — §4.4/§11).

## Debt ledger (each with evidence + disposition)

### D1 — items.h full replacement zeroes vanilla item behavior (CRITICAL)
`items.py` emits a **full-replacement `src/data/items.h`** with behavior
fields zeroed for ALL 607 items *including kept-vanilla ones* (flagged in
`items.py:284-286` and `item_dupe_census_2026-07-04.md`). Landing it as-is
breaks every vanilla item. Fix in the converter: emit **merge-not-replace** —
Uranium-original items append entries; kept-vanilla items keep the fork's
entries (override only fields Uranium actually changes: price, description
text). Same review applies to `moves_info.h` and the pokemon data tables:
audit each Phase-2 emitter for replace-vs-extend before staging.

### D2 — species graphics/cries/dex data have NO pipeline (gap found by the
scaling audit)
Nothing converts Uranium's battler sprites, icons, footprints, or cries;
Phase-2 species data alone gives invisible/silent mons. New converter needed
(pattern exists: `graphics/sprites.py` handles 2×-scale detection and
majority-vote downscale; battlers are 64×64 targets, ~190 species ≈ 1–1.5 MB
ROM per the audit). Cries: Uranium ships per-species cry audio — GBA cries
are sample-based (one short sample each); a downsample-to-cry converter is
plausible but needs a spike; fallback = closest vanilla cry via a mapping
table (same shape as the audio table). Dex text/pages come from Phase-2 data
already; wire them with the species reconciliation.

### D3 — fork-gate extras: Uranium constants join the capability index
`fork_index` gates against the **pristine** fork, so every emitted Uranium
constant is invisible to it until the generated headers are registered as
gate extras (the mechanism exists: `registry_extra_symbols`). Once species
constants join, `checkspecies`/`DoesPlayerPartyContainSpecies` become
emittable — this unblocks **SLICE1_TODO #2** (Auntie's `pbHasSpecies?
(RAPTORCH)` branch, the last live slice queue entry) and the whole class of
species/item-conditional event logic corpus-wide.

### D4 — engine cutover: point RPG2GBA_POKEEMERALD at `engine/`
Still pointing at the old external clone (CLAUDE.md §3). Cutover = one-time
`make modern` in `engine/` to generate the headers the pipeline reads, then
re-assemble so the custom C compiles, then flip the env var. Do this EARLY in
Phase 7 (or before) — every other item lands C in the vendored tree, and
running the pipeline against a different fork than the one being built is a
standing footgun. Remember the deferred consolidation note: `load_fork_
constants`/`load_multi_constants`/`load_charmap_chars` intentionally read
working-tree (generated) headers — after cutover that's the same tree, which
is the point.

### D5 — encounters wiring
Phase-2 encounter output is keyed by Uranium map id
(`intermediate/wild_encounters.json`) by design ("ties into map IDs from
Phase 5"). Wiring = per-map `wild_encounters.json` entries in the emitted map
dirs, species ids through the D-central remap, encounter-method mapping
(land/water/rock-smash/old-rod… — Essentials encounter types are richer;
unmapped types fail loud, disposition per type). Slice payoff immediately:
Route 01 (slice 2) is the first map with wild grass.

### D6 — trainer battles end-to-end
Phase-2 trainers converted (`intermediate/trainers*.json`); transpiler emits
`trainerbattle` with intro/defeat text. Phase 7 glues: trainer ids through
the remap into `src/data/trainers.h`-family, trainer-class sprites/music
(class → existing fork class where close, else new sprite via D2 pipeline),
and the §4.6 round-trip test. First slice trainer appears on the early
routes — this can land slice-by-slice like everything else.

### D7 — save-block capacity re-check
`RPG2GBA_EXPAND_EVENT_RANGES` capacities were sized by the 2026-07-10 census
(needs: 235 global flags / 119 vars / 1132 self-switches / 345 temp-switches;
capacities 0x180/0x100/0x500/0x180). Re-run the mint census when the frontier
is large (assembler already fails loud on overflow); the nuclearFree
BoxPokemon bit (nuclear spec §5.2) is the only other save-format change on
the books — land both before anyone keeps a long-lived save.

### D8 — ROM budget: vanilla stripping pass
From `corpus_scaling_audit_2026-07-14.md`: full-corpus additions ≈ 8.5–11 MB
vs 7.08 MB current headroom → a stripping pass over vanilla Hoenn
layouts/maps/scripts (mechanism proven by the walker's stock-data stubbing)
is a *planned* Phase-7 item, not an emergency lever. Keep vanilla
battle/species data (kept-vanilla Uranium mons use it). Add the per-build ROM%
line to the assembler log now — it's one number and it trends.

### D9 — audio substitution table
`reference/findings/audio_decision_2026-07-14.md` — the audio_map.json
mechanism should exist before Phase 7 bulk-wires maps (every map.json wants
its BGM row). Corpus completion of the table is Phase-7-adjacent grunt work.

### D10 — Phase-2 deferred exit criteria + release hygiene
- Phase-2 exit #3/#4 (generated C compiles in the fork; test ROM shows the
  species list in the Pokédex) — deliberately deferred to Phase 7; they
  become the acceptance test of the D-central reconciliation + D1 + D2.
- `engine/src/new_game.c` test harness: KEEP through development (user
  decision, SLICE1_TODO #5), strip only for a release ROM — tracked in
  `engine_extension_surface.md` §3.
- CommonEvents queue (88 entries) — triage lands when the first slice calls
  a CE; not strictly Phase 7 but same reconciliation window.

## Order of attack

1. **D4 cutover** (everything else assumes one tree).
2. **Census + remap decision per concept** (species/moves/abilities — the
   item census pattern; produces the numeric id plan and updates
   `uranium_id_map.json` consumers).
3. **D1 emitter rework** (merge-not-replace) + regenerate; **D10 compile
   gate**: generated C builds clean in `engine/`.
4. **D2 species graphics/cries spike → converter**; Pokédex smoke test
   (D10 #4).
5. **D3 gate extras** — then clear SLICE1_TODO #2 and re-transpile.
6. **Phase 6 spec execution** (type chart needs the reconciled move/species
   tables for Nuclear move types and form entries).
7. **D5 encounters + D6 trainers**, slice-by-slice with the frontier.
8. **D7/D8/D9** as standing checks (capacity, ROM%, audio rows) per slice.

Manual gate: ROADMAP §9 #3 (end-of-Phase-7 playthrough) stays; items 3–5
above also individually deserve a boot-walk since each changes what the
player sees (mon sprites, obedience, encounters).

## What can go wrong (verify-first list)

- Expansion species enum interleaves forms/megas — "append after last id"
  must use the fork's actual mechanism for adding species (families/
  `SPECIES_INFO` macros), not raw enum math. Read how the expansion adds a
  new species before writing the emitter (§4.7).
- Item behavior "overrides" for kept-vanilla items: Uranium rebalances some
  vanilla item prices/effects — diff field-by-field in the census, don't
  assume identity.
- Move effects: Uranium-original moves reference Essentials function codes
  (`intermediate/move_function_codes.json`) — map to expansion `EFFECT_*`;
  unmapped codes fail loud into a disposition list (the §2.2 LLM-assist tail
  is available but most are standard).
- Save compatibility promises are void across D7 changes — say so loudly in
  the build log when the BoxPokemon bit lands.
