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

**APPROVED 2026-08-25** by the operator. Under the Q6 decision the approved
object is the joined manifest + dispositions, approved before build work —
the same approval-order rule CH02 and CH03 followed, with a different
artifact. `chapters.json` CH04 status advanced `planned` -> `in_progress`;
it advances to `built` at the §9 gate.

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

## Approval — closed

- [x] **Author all 42 dispositions.** Every row needs a verdict
      (`beat:` / `cosmetic` / `deferred:rock_smash` / `unreachable:`) plus an
      `affirmed_hash`. 18 rows trip the citation trigger and additionally need
      a `source:`.
- [x] **Reconcile `04-route-2.md` §3** — B1–B7 bound to generated row ids;
      B8–B15 now stated in the same action/effect form rather than merely
      acknowledged in an explainer table.
- [x] **Re-affirm the operator walk-through of B8–B15** (added 2026-08-25 from
      the operator's read of the beat list). Four gaps, one rule change:
      - B15 wild encounters in the grass corridor — the beat list had no
        encounter check at all. **Structural:** the manifest enumerates event
        pages and seams, so an encounter table can never be a row. Any
        non-event beat class is invisible to the approval object and must be
        added by hand.
      - B9 the real sign @(19,34) (ev002) — was identified as a beat but had
        no player action / expected effect, so it was not walkable. Note id 8
        "Sign" @(19,33) is an empty page and is *not* the sign by the cave.
      - B13 the Barewl @(17,36) beside Larrie, and B14 Timothy's defeated
        re-talk — both were `cosmetic`, both have observable behaviour.
      - **Disposition rule changed:** `cosmetic` now means *no trigger to
        press*, not *writes no state*. The old rule made Larrie's re-talk a
        beat (B11, via `pbPhoneRegisterBattle`) while Timothy's identical
        re-talk was cosmetic. Re-swept all 42 rows; ev009/p1, ev011/p0 and
        ev012/p1 were reclassified to `beat:`, and id 8 is the only reachable
        cosmetic row left on map 35.
      Checker is clean after the change: `0 error(s), 4 warning(s), 42 rows`
      (the 4 are the pre-existing `capability_model_unenforced` warnings on
      the deferred rock rows).
- [x] **User approval** of the joined manifest + dispositions — given
      2026-08-25. Build work is unblocked.

## Open — blocks the §9 gate, not authoring

- [x] **Route 2's two battle trainers are unstaged, and they hard-block the
      transpiler.** DONE 2026-08-25 — and it was four trainers, not two.
      Timothy and Chuck were appended as described below; Larrie (ev003) and
      Brent (ev023) had to be appended too. Those two never tripped the gate
      because the transpiler was *queueing* their battles rather than emitting
      them: their `pbTrainerBattle` sits inside a code-111 conditional on the
      phone-trainer path. Brent brought `TRAINER_CLASS_BIRD_KEEPER`, the
      second new class this chapter (`TRAINER_ENCOUNTER_MUSIC_COOL`, what
      vanilla's own Bird Keepers use); Chuck brought `TRAINER_CLASS_HIKER`.
      17 battles now stage. Larrie's party needed no new species — MANKEY is
      vanilla, BAREWL came with CH02. Original note follows.

- [ ] ~~**Route 2's two battle trainers are unstaged, and they hard-block the
      transpiler.**~~ (superseded, kept for the reasoning) `transpile_driver run --maps 35 --dry-run` does not reach
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
      **(c) CH04 cannot verify them at all** (user, 2026-08-25): all 16 cells
      lie beyond the rockslide, which is impassable until Rock Smash, so the
      chapter emits the derived ledges but no walk can reach one. Do not
      register a beat for them and do not read CH04's gate as proof the
      derivation is right on hardware — that waits on the rockslide-opening
      chapter. Recorded corpus-wide at `PROJECT_TODO.md` §33.
      Note `reference/archive/PATHFINDER_FINDINGS.md:106` calls tiles 840-842
      (passage 0x0E) a *south* ledge; that prose is wrong (0x0E -> north) and
      was left unedited as archived history.

## Open — found during the build

- [x] **CH04 has no entrance until map connections exist.** DONE 2026-08-26 Map 31 has ten
      warp events and not one goes to map 35: the only link is the borderless
      seam `[31,'N',11,35,'S',0]` in `connections.json`. Connections are
      unimplemented — `tileset_converter/connections.py` is still the §5.4
      assignment stub and `porymap/maps/Route02/map.json` emits
      `"connections": null` — so Route 2 is unreachable in the ROM. There is
      no warp to fake it with, unlike the CH02->CH03 boundary, which had real
      transfer events on both sides. 14 seams exist corpus-wide; two involve
      map 35, and the north one (`[35,'N',0,40,'S',15]`, to CH06's Nowtoch)
      must stay omitted under the frontier rule. In progress.

- [x] **The rematch registered-flag block overflowed, as `rematch.py`
      predicted.** Vanilla derives a rematch's registered flag as
      `TRAINER_REGISTERED_FLAGS_START + rematchTableId`; the block ends at
      0x1A9 with only 0x1AA/0x1AB free before `FLAG_DEFEATED_DEOXYS`. CH02's
      two phone trainers took exactly those two, and CH04's Larrie and Brent
      need two more, so `assemble_pathfinder`'s S8b5 pass fails loud rather
      than truncating. Operator's call 2026-08-25: relocate the block to a
      base with >=100 contiguous free flags, so vanilla's own
      `FLAG_REGISTERED_*` defines keep deriving correctly and `battle_setup.c`
      needs no change. `MAX_REMATCH_ENTRIES` is deliberately NOT grown — that
      moves the saveblock and invalidates every save and seed blob. In
      progress.

- [x] **The phone-rematch classifier bails on a one-command difference.**
      `deterministic.classify_phone_rematch_trainer_battle` expects
      `pbPhoneRegisterBattle(...)` split across code 355 + code 655, because
      on map 33 the `_I("...")` literal spans the RGSS command boundary. Map
      35's events 3 and 23 carry the same call as a single code-355 command,
      and the classifier is atomic over all three pages, so one mismatch drops
      the whole event to the queue — 14 of map 35's 20 queued rows. The fix is
      to match on content rather than command-code count. In progress.

- [x] **B11 was going to be dropped by design.** The phone classifier
      deliberately discards RGSS page 2 (the defeated re-talk) on the argument
      that native match-call bookkeeping supersedes the self-switch state
      machine. CH04's approved beat list has that page as B11, so the idle
      line is being re-emitted the way vanilla does it — a post-battle
      `msgbox` branch off `trainerbattle_single`'s continue-script label,
      mirroring `Route102_EventScript_Calvin`.

- [ ] **`kevlar.py` B25 asserts the Kevlar<->Route 2 seam is BLOCKED.** True
      today, false the moment connections land. Flip it when the seam works;
      it is CH03's file, so it is a deliberate cross-chapter edit, not drift.

- [ ] **B10 has no harness path.** `route2.py` registers 13 of 15 beats. B8 is
      unwalkable for the B7 reason above. B10 (Larrie's rematch offer) needs a
      PokeNav/Match-Call driver and a self-switch setter, neither of which the
      emulator harness has. Both are recorded in `DEFERRED_BEATS` rather than
      quietly dropped.

- [ ] **Several `route2.py` coordinates are inferred, not decoded** — the
      Kevlar-side approach column for B1, and B15's two grass cells. Flagged
      in that file's docstring; settle them on the first real suite run.

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

## First real build + suite run — 2026-08-26

The chapter was built and the scenario suite run against a live ROM for the
first time. Pipeline: `transpile_driver run --maps slice` -> `stage_slice_scripts
--write` -> `assemble_pathfinder` -> `make modern` (exit 0). Python suite
**2358 passed, 19 skipped**.

**ROM `ec7401d4`** (first build of this chapter was `dcf6d603`, superseded by
the self-switch fix below). Suite tally: **62/73 run, 61 passed, 1 failed,
0 hung, 11 not run.** Every CH01-CH03 regression beat still passes, so the
connections work did not disturb the earlier chapters.

Settled by the run:

- **B1's approach column is decoded, not inferred.** The authored x=29 was
  wrong: it translates (offset 11) to map035 x=18, inside the blocked
  collision run 14-19 on Route 02's south row 56, so the step north was
  refused and the player never left map031. x=31 -> map035 x=20 is passable on
  both sides and B1 now passes. `route2.py`'s docstring carries the evidence.
  Note this is NOT a converter bug: the connection is correctly wired both
  ways (offset +/-11), correct group, correct overlap.
- **The connection itself is proven live** — the seam crosses in the ROM,
  which is the thing `connections.py` was written for.

Still open after the run:

- [ ] **B2 fails: `FLAG_MAP035_EVENT003_SSA` is not set after Larrie's win.**
      The phone-rematch idiom consumed RMXP's `code 123 ["A",0]` as a
      structural predicate and emitted nothing for it. A `setflag` was added to
      the continue-script block and is **confirmed present** in the staged
      `Map035.pory`, but the freshly built ROM still reports the flag unset —
      so the emission is necessary but not sufficient, and the live cause is
      still open. B2 gates B3/B4/B5/B6/B7/B9/B11/B12/B13/B14/B15, which is why
      11 beats read NOT_RUN.
