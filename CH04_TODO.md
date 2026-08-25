# CH04 TODO — Route 2 (map 35)

Live work checklist for chapter CH04 (Route 2), the current build frontier.
The chapter's spec, story beats and coverage targets live in
`reference/chapters/04-route-2.md`; the corpus-wide plan is
`reference/chapters/00-atlas.md`. This file tracks only *work items*, not
design. Same conventions as `reference/archive/CH03_TODO.md`: commit updates
as items close; move an item to **Done** with a one-line result rather than
deleting it. Facts here are pointers — the cited code/docs stay authoritative.

Seeded 2026-08-22. CH04 is the **pilot chapter for the generated manifest**
(`PLAYTEST_AUTHORING_IMPROVEMENT.md` §4.3): the first chapter whose approval
object is a joined manifest + disposition file rather than a prose beat table.

## Approved scope

**Not yet approved.** Under the Q6 decision the object the user approves is
the joined manifest + dispositions, before build work — the same
approval-order rule CH02 and CH03 followed, with a different artifact. See
"Open — blocking approval" below.

- Manifest: `reference/manifests/CH04.manifest.json` — 42 rows (40 event
  pages + both overland seams), generated, never hand-edited.
- Dispositions: `reference/manifests/CH04.dispositions.json` — hand-authored,
  one verdict per row.

## Done

- **Manifest generation is a first-class CLI operation** —
  `python -m rpg2gba.chapter_manifest generate --chapter CH04`
  (`src/rpg2gba/chapter_manifest/__main__.py`), idempotent, 3 tests in
  `tests/test_chapter_manifest_cli.py`. Previously a library call with no
  entry point.
- **CH04 is fully dispositionable** — 19 of 42 rows were blocked behind 6
  unrecognized script heads and 10 unruled command codes; now 0. Vocabulary
  extended per the operator's conservative-split decision (2026-08-22):
  new cosmetic-safe tags `bubble_ui` / `animation` / `screen_fx`, new
  state-writing tags `erase_event` / `temp_switch_write` / `control_flow`.
  Codes 106/108/413 ignored; 204/208 → `graphic`; 112/113/115 → `control_flow`
  (115 truncates a page, so such a page can never be called decoration).
- **Head-extraction bug fixed** — `_script_head` was taking the left-hand side
  of a Ruby assignment as the call head, so
  `trainer = createPhoneTrainer(...)` reported head `trainer`. Both of map 35's
  phone-rematch trainers were affected. Fixed in
  `src/rpg2gba/chapter_atlas/census.py`.
- **Rockslide contradiction adjudicated** (closes
  `PLAYTEST_AUTHORING_IMPROVEMENT.md` §7.2). Event 19's clearing page really is
  engine-ungated — no switch, variable or self-switch condition — but the gate
  is **geometric**: BFS over the tileset passage bytes shows event 19's
  trigger-adjacent tiles are unreachable from the south-accessible region while
  the five Rock events are solid. CLAIM A (wiki: rockslide forces the Passage
  Cave detour) and CLAIM B (data: no condition flag) are both true. CH04's gate
  is real, CH07's revisit stands, the Rock Smash deferrals are real.
- **Content hashes unaffected** by the vocabulary work — `content_hash` is
  computed over the raw page dict before tag derivation, so no existing
  affirmation is invalidated.

## Open — blocking approval

- [ ] **Author all 42 dispositions.** Every row needs a verdict
      (`beat:` / `cosmetic` / `deferred:rock_smash` / `unreachable:`) plus an
      `affirmed_hash`. 18 rows trip the citation trigger and additionally need
      a `source:`.
- [ ] **Reconcile `04-route-2.md` §3** — its hand-authored B1–B7 beat table
      predates the manifest and must map onto generated row ids, the way CH03
      reconciled its spec numbering against `kevlar.py`'s canonical numbers.
- [ ] **User approval** of the joined manifest + dispositions.

## Open — blocks the §9 gate, not authoring

- [ ] **Route 2's two battle trainers are unstaged, and they hard-block the
      transpiler.** `transpile_driver run --maps 35 --dry-run` does not reach
      the unhandled queue at all — the fork-index gate raises first, on two
      undefined constants: `TRAINER_TIMOTHY_247` (Map035:100) and
      `TRAINER_CHUCK_279` (Map035:482), both `trainerbattle_single`.
      `reference/uranium_id_map.json` names both (:1976, :1723); the engine
      defines neither. Not a transpiler bug despite the gate's wording — the
      gate resolves `TRAINER_*` through the staging manifest
      (`output/uranium-build/trainers/trainer_manifest.json`,
      `transpile_driver.py:512`), which is generated from
      `common.SLICE_TRAINER_BATTLES` (`trainer_converter/common.py:109`).
      That tuple is **append-only and order-load-bearing** (fork ids are
      assigned by position off `PRISTINE_TRAINER_ANCHOR`), currently 13
      entries ending in CH03's `TRAINER_MAWULI_90`. CH04's build step must
      append the two Route 2 trainers *in that order* and re-run trainer
      staging. Deliberately NOT done yet: it is build work, and the Q6 rule
      puts approval first. **Consequence: the map-35 unhandled queue cannot
      be read until this is done**, so `unhandled: null` in the readiness
      tracker stays null through approval.

- [x] **Ledge directions are unmapped globally — CONVERTER FIXED, emission
      unverified.** `terrain_tags.column_behavior` now derives the jump
      direction from the RMXP passage byte's low nibble instead of falling
      back to `MB_NORMAL`, closing `PROJECT_TODO.md` §33. Precedence:
      `ledge_directions` override wins; else sole clear bit -> `MB_JUMP_*`
      (0x08 south / 0x01 north / 0x02 east / 0x04 west, the opposite-side
      `10 - d` rule); 0x0F is a plain wall and stays silent; >=2 clear bits
      warns once and falls back. No hand table needed, and
      `reference/terrain_tag_map.json` was left empty by design. Suite 2358
      passed / 19 skipped. **Against real data, map 35's ledges all resolve:
      16 tag-1 cells, tiles 557/565/572 (passage 0x07) -> `MB_JUMP_SOUTH`,
      zero ambiguous** — matching the hand-verified ts22 inventory in
      `reference/archive/CH02_TODO.md`. Two caveats: (a) this item previously
      said **12** ledge cells and the direct count says **16** — the count
      above ignores `effective_tag`'s opaque-cover stop, so neither figure is
      confirmed; settle it when the map actually converts. (b) Nothing has
      been *emitted* yet — map 35 is not in `SLICE_MAP_IDS`, so the ROM-side
      check that these become real one-way drops is build work, post-approval.
      Note `reference/archive/PATHFINDER_FINDINGS.md:106` calls tiles 840-842
      (passage 0x0E) a *south* ledge; that prose is wrong (0x0E -> north) and
      was left unedited as archived history.

## Carried, not blocking

- [ ] **Capability model (Q3) is unbuilt**, so checker rule 7
      (`deferred_no_granting_chapter`) cannot enforce CH04's 5 `rock_smash`
      deferrals — they pass on a `capability_model_unenforced` warning.
      Operator decision 2026-08-22: accept warnings for now. CH06 is the
      grant chapter per `reference/chapters.json`.
- [ ] **Rule-set versioning (Q7) is designed but absent from the code** —
      `checker.py` carries no rule-set version field, so no gate stamp can
      record one and no lag report can be generated.
- [ ] **`isRockSmashSoftlocked` remains unrecognized** on map 32 (CH01's map),
      the last unrecognized head in that fixture. Out of CH04's scope; filed
      so it is not rediscovered.
- [ ] **Q5.1 citation-verification experiment** is scoped to run on CH04 and
      CH05: a blind second-agent pass over citation-triggered rows only, kept
      if it catches at least one silent pass across both chapters.
- [ ] **Poké Radar catch-table entries** (Dunsparce, Tofurang) appear on the
      Route 2 wiki page but are absent from `wild_encounters.json`
      (`04-route-2.md` §5). Data gap, unresolved.
