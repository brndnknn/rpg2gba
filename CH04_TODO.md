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

- [ ] **Ledge directions are unmapped globally.** `ledge_directions` is empty
      in `reference/terrain_tag_map.json`, so unmapped ledges fall back to
      `MB_NORMAL` in `stairs.py`. Map 35 has **12 ledge cells** that will
      convert to plain floor instead of one-way drops. Converter defect — fix
      the converter, not the output.
- [ ] **Runtime text-content primitive does not exist.** Map 35 events 3 and
      23 are multi-page phone-rematch dialogue, exactly the multi-response case
      Q4 says needs a runtime assertion.
- [ ] **Map 35 was never staged through the transpiler** — `unhandled: null`
      in the readiness tracker; it was not one of the 8 slice-1 maps
      (`04-route-2.md` §6.3).
- [ ] **Engine map directory / porymap constant unassigned** — `Route2` /
      `MAP_ROUTE_2` proposed in `04-route-2.md` §2, not yet bound.

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
