# Investigation: Repo audit — dead code, duplicated code, stale docs

**Status:** closed — 48 findings, Q1-Q13 all answered 2026-09-07; the artifact is the remediation plan in Next steps. **Stages A-E EXECUTED 2026-09-07** on branch `repo-audit-remediation`, then a **second pass the same day worked the "Not scheduled" deferrals to zero** (Q3 consolidation, H2, H3, H8, the UNVERIFIED status lines, the dead-code sweep, and follow-up #3). Two execution logs below. **Exactly one item is still open — follow-up #1, the external-clone rename, which needs the operator.**
**Started:** 2026-09-06   **Last updated:** 2026-09-07 (second pass; deferrals closed, follow-ups #3 and #4 closed)
**Question:** What in this repo is dead, duplicated, or out of date — and specifically, which artifacts caused agents to follow retired processes or misread the project's current state?
**Expected artifact:** plan — the prioritized remediation plan in Next steps, keyed to the Q1–Q13 answers

## Summary

**Closed 2026-09-07.** The audit found 48 things; all 13 decisions are made and the
remediation plan is in Next steps, in five independently-shippable stages (engine safety →
remove the harmful → the authority problem → MEMORY.md prune → code). Three answers diverge
from my recommendation and are flagged in Decisions so nobody reverses them by accident.

What the audit found: The
headline: there is almost no classically dead code here — every module in `src/rpg2gba/`
is referenced from somewhere (28), and spent one-offs in `scripts/` are expected by
policy, not a defect (47). The repo's problem is that **its documentation asserts things
about itself that are no longer true**, and it does so in the files agents are told to
trust most.

Ranked by what it would actually cost you:

1. **`engine/RPG2GBA_VENDOR.md` describes the custom C as three test-only files to
   "revert/gate before a real build". The real diff is 77 files, 2647 insertions** —
   including two whole new source files, a movement-type bytecode interpreter, and ~15
   generated-content include-hooks (42). `MEMORY.md:101` repeats the "3 files" claim. This
   is the only finding whose failure mode is *destroying working engine features*. Two
   custom edits are also unfenced and invisible to a sentinel-based revert (40), and the
   fence convention is four vocabularies rather than the one `CLAUDE.md` §5 documents (41).
2. **Two scripts are dead *and harmful*:** `run_slice.py` spends API budget,
   `regen_outputs.py` strips `output/` and flips three tests from skip to fail. The repo
   warns about both — in a runbook footnote and a memory-archive entry. Neither script says
   anything (45).
3. **Six docs claim to be the "what to do next" authority, and the loudest is three
   chapters stale** (1-3): `BUILD_PLAN.md` is headed "**Status:** live ... the project's
   single 'current *how*' doc" and points at CH02 and an archived `CH02_TODO.md`.
4. **Five docs assert a shipped feature is unbuilt** — trainer staging (35), the palette
   viewer (36), can-lose battles (17), the engine cutover (19) — plus two false
   supersession claims about scripts the live stack still imports (21, 46).
5. **`MEMORY.md` is 260 KB in 350 lines.** Protocol-compliant in structure, but line 43 is
   27 KB and the frontier fact sits ~12 KB deep inside line 18 (4-7).

**The mechanism, which matters more than any instance (34):** the 2026-08-05 slice→chapter
rename pass mechanically rewrote stale claims into current vocabulary. `BUILD_PLAN.md` §6's
CH02 pointer was *true when rewritten* — it rotted after — but the rename gave it fresh
vocabulary and a recent commit date, defeating both date-based and terminology-based
staleness detection. Editing is then section-local: two later commits to that file touched
only lines 94-130 and never revisited §6. **A global terminology pass is harmful unless
each rewritten claim is also checked for truth.**

Code duplication yielded no live bug. `move_constant` is hand-copied five times with two
copies missing the `MOVE_NONE` guard (8), but both are latent — `trainers.py` by a hard
code guard, `tm_hm.py` only because index 0 of the real `tm.dat` is null, so it could go
live from a data change alone with no code change (38). The rest is latent: 10 copies of
`_reference_dir()`, 9 of the output-path resolution, three `chapters.json` loaders of which
one validates (9-11).

**Two of my own findings needed correcting mid-audit, both from the same error — inferring
death from silence.** Finding 27 called the bulk-run stack dormant on MEMORY.md date
silence; `backends/` is retained by explicit policy (`BUILD_PLAN.md:26`), though the
operator layer that drives it does appear dormant (39, 44). And I repeated a sub-agent's
"post-pivot commit" claim without checking the date — it was six days pre-pivot (44).
Findings marked CONFIRMED were verified first-hand; the distinction is load-bearing here.

## Findings

1. **`BUILD_PLAN.md` is the single most dangerous doc in the repo: loudest authority
   claim, three chapters stale.** Header `BUILD_PLAN.md:1-5` reads "the active build
   sequence / **Status:** live. This is the project's single 'current *how*' doc."
   But `BUILD_PLAN.md:246` says "active chapter is now CH02" and `:256` says "**Active
   chapter is now CH02** (Route 1, maps 33 and 81) — see `CH02_TODO.md` ... blocked on
   promoting per-map tileset packing into `assemble_pathfinder.py`". Reality per
   `POST_CH05_REVIEW.md:3`: "Written 2026-09-06, after CH05 passed its §9 gate and
   merged to `main` (`af0d8e25`)", and `:12` "§2 is the one that blocks CH06."
   `CH02_TODO.md` exists only at `reference/archive/CH02_TODO.md`.
   *Verified first-hand (read both files).* **Wrong action it causes:** an agent
   resumes CH02 Route 1 work, hunts a root-level `CH02_TODO.md`, and may re-litigate a
   tileset-packing blocker resolved during CH02–CH05.

2. **Six competing self-declared "what to do next" authorities.** Each of these
   positions itself as current-state or how-to authority: `BUILD_PLAN.md:1-5`
   ("Status: live", the single current-*how* doc); `CLAUDE.md:5` (roadmap wins on
   *what*, this file on *how*); `ROADMAP.md` (the *what/why*, per both of the above);
   `PROJECT_TODO.md:4-5` + `:9` (disclaims authority, but names `CH02_TODO.md` "the
   current frontier checklist"); `CH05_DECISIONS.md:17` ("Update this table when an
   item lands; do not trust the sections below"); `POST_CH05_REVIEW.md:3,14,17`
   (structurally the current decision/status doc, dated today). **Nothing in the corpus
   tells an agent which to prefer.** The freshest is `POST_CH05_REVIEW.md`; the one
   with the strongest self-label is the stale `BUILD_PLAN.md`. This is the mechanism of
   the reported confusion.

3. **`PROJECT_TODO.md` header points at an archived checklist.**
   `PROJECT_TODO.md:3-5` sends agents to "`CH02_TODO.md`, the current frontier
   checklist" — retired to `reference/archive/`. The file was committed 2026-09-06,
   the same day CH05 closed, so the stale pointer survived a same-day edit.

4. **`MEMORY.md` is unskimmable by byte layout, though structurally protocol-compliant.**
   260 KB in 350 lines. All 7 sections mandated by `reference/memory-protocol.md:18-47`
   are present, in order. But: `MEMORY.md:43` is **27,431 bytes on one line** (a
   run-on chronicle of the transpiler build, image pipeline, NPC gfx, boot-gate bug #7,
   tileset animation, Map032 fixes); `:18` is **13,039 bytes** and buries the live
   status ("CH05 ... PASSED its §9 boot-walk gate 2026-09-06 ... CH06 (Nowtoch City,
   maps 40-47) is now the frontier") behind ~12 KB of superseded CH02-era detail on the
   same physical line. Next largest: `:36` 5,810 B, `:55` 4,720 B, `:134` 4,182 B,
   `:44` 3,622 B, `:57` 3,364 B, `:139` 3,232 B, `:130` 3,166 B, `:195` 3,142 B.

5. **`MEMORY.md`'s readable headline is stale relative to its own body.** `:12` opens
   "Active: Phase-4 rework — deterministic transpiler + vertical playable **slices**",
   while `:16` corrects it three paragraphs down: "**Work unit = one CHAPTER**
   (reoriented 2026-08-05 from ad-hoc 'slices')". A skimming agent reads the headline
   and stops.

6. **Eviction discipline has slipped: 4 of 8 Open Questions are already resolved in
   their own text.** `MEMORY.md:302` ("DECIDED 2026-08-27"), `:304` (three of four
   sub-items marked DONE), `:306` ("Update 2026-06-18: ... is now the single owner of
   charmap legality"), `:309` ("[SUPERSEDED 2026-06-18 ...]"). Per `CLAUDE.md:65` these
   belong in `reference/memory-archive.md` (which exists, at **334,766 bytes — larger
   than MEMORY.md itself**). Also note a stray bullet at `:315` sitting after a `---`
   separator, outside the section's own archive note at `:311`.

7. **Key File Notes systematically violate the two-sentence rule** (`CLAUDE.md:63`:
   longer than two sentences belongs in `reference/`). Representative: `MEMORY.md:101`
   (engine/ vendoring provenance, ~6 sentences), `:111` (fork struct shapes + 3
   sub-bullets — doc-shaped, not a note), `:130`, `:134`, `:139` (a full
   question/finding/fix investigation writeup as one "note"). Worse, a note near `:151`
   states it "supersedes the 'Map Inspector/Issues/slice-pool' framing in the notes
   above" — and those superseded bullets are still sitting there.

8. **CONFIRMED BUG — `move_constant` copied five times, two copies missing the
   `MOVE_NONE` guard.** `CLAUDE.md:4.3` names `pbs_converter/moves.py` the source of
   truth for `MOVE_*`. Five resolver classes hand-copy `move_constant` instead:
   guarded — `pbs_converter/moves.py:205`, `pokemon.py:452`, `tmpbs.py:53` (whose
   docstring says it "mirrors pokemon.py's move_constant"); **unguarded** —
   `trainers.py:216`, `tm_hm.py:88`. *Verified first-hand by reading all three
   variants.* **Severity: LATENT, not live — see finding 38**, which traces the callers
   and shows a 0 cannot currently reach either unguarded copy. **Failure mode if it
   did:** on `move_id == 0` (an unset move slot) the guarded copies
   return `MOVE_NONE`; `trainers.py`/`tm_hm.py` fall through to
   `self.move_internal.get(0)` → `None` → `raise ValueError("move id 0 absent from
   move_internal_names.json")`. `item_constant`, `species_constant` and
   `ability_constant` share the same copy-paste skeleton and currently still agree —
   one edit from the same fate.

9. **`chapters.json` has three loaders, only one of which validates.**
   `chapter_atlas/binding.py` is the designated validating loader (unique ids, map-id
   existence, visit-numbering, tier/status vocab, all fail-loud) and is used by
   `chapter_atlas/__main__.py:36`. Bypassed by `chapter_manifest/generator.py:644-649`
   (`_load_chapter_maps`, raw `json.loads` + linear scan, no validation) and
   `routing/__main__.py:78-86`, whose own docstring admits it is "mirroring
   `chapter_manifest.generator._load_chapter_maps`'s simple lookup (kept as a separate
   small helper here rather than importing that private function)" — a deliberate copy
   of a copy. A malformed `chapters.json` passes silently through two of three paths.

10. **Latent copy-paste with no shared helper (identical today, breaks on the next
    refactor).** `_reference_dir()` — `Path(__file__).resolve().parents[3] /
    "reference"`, hardcoding directory depth — appears in 10 files:
    `pbs_converter/{tm_hm.py:49, tmpbs.py:40, moves.py:185, pokemon.py:397,
    trainers.py:176, items.py:186, encounters.py:81, abilities.py:77, types_dump.py:32}`,
    `species_converter/stage.py:255`. `_load_id_json()` in 9 of those same files.
    Output-path resolution (`Path(os.environ.get("RPG2GBA_OUTPUT", "output")) /
    "uranium-build"`) in 9 places: `pipeline.py:71`, `pipeline.py:393`,
    `playtest/{cells.py:86, text_source.py:95, assertions.py:262, chapter.py:670,
    emulator.py:539}`, `conversion_agent/{fork_index.py:351, transpile_driver.py:750}`,
    `chapter_atlas/__main__.py:22`. Changing the default requires 9 synchronized edits.

11. **Trainer-pic constants bypass `_naming.to_constant`.**
    `trainer_converter/common.py:39-45` (`TrainerPicSpec._sanitize`) does its own
    regex uppercase+collapse. `pbs_converter/_naming.py:47-56` additionally NFKD-folds
    diacritics and drops periods. Current `SLICE_TRAINER_PICS` entries are plain ASCII
    so no live divergence, but an accented trainer-class name would yield a different
    constant from the two paths. Trainer-pic constants aren't in the §4.3 table, so
    this is a DRY/mechanism violation rather than a strict rule breach.

12. **`FABLE_PLAN.md` is fully spent and should not read as live work.** All steps
    marked "DONE 2026-07-14" (`FABLE_PLAN.md:47,151,165,177`); its only git commit is
    2026-07-14; its premise ("Fable ... may leave the Pro plan soon", `:2`) is a closed
    time-box. Step 1 ("USER: measure how bad the seam problem actually is", `:16`)
    lacks a DONE marker and reads as an open user task, but its deliverable
    (`reference/guides/connections_and_palette_families.md`) shipped.

13. **`PLAYTEST_AUTHORING_IMPROVEMENT.md` (V1) is superseded but `MEMORY.md` still
    calls it authoritative.** V2 claims succession explicitly
    (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md:6`, "**Predecessor:** ... asks the same
    question one round later"). No *root* doc directs an agent to V1's process
    (`CH05_DECISIONS.md:47` cites it only as passive corroboration). But `MEMORY.md:98`
    and `:189-190` call V1 the "authoritative record" and instruct "Read before
    authoring any chapter scenario." That is a live directive at a superseded doc.

14. **`ROADMAP.md` never migrated off "slice" vocabulary.** Grep-confirmed: 9
    occurrences of "slice", **zero** of "chapter", despite `CLAUDE.md:277` recording
    chapters as the unit of work since 2026-08-05. `README.md:9,52,55,103,106,117,119`
    has the same pattern in its build recipe. An agent reading either exclusively never
    learns the current unit of work. (Not a false claim — a vocabulary gap. Note
    `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` uses "slice 1–4" for its own feature-build
    phases, a *different* referent that compounds the ambiguity.)

15. **`ROADMAP.md` Phase 1 still instructs a fresh external clone.** `:258-280` says
    "Fork pokeemerald-expansion" / "Clone from rh-hideout", the pre-vendoring process;
    `CLAUDE.md:120` records the cutover DONE 2026-06-19. Lower risk (framed as phase
    history), and `PROJECT_TODO.md:13-16` already tracks the related open item.

16. **The known-hazard external clone still exists on disk.**
    `/home/b/repos/pokeemerald-expansion` is present. `MEMORY.md:92` calls its
    "continued existence ... an active hazard", noting an agent that points
    `RPG2GBA_POKEEMERALD` at it gets a tree with no `include/config/rpg2gba.h` and
    concludes the fork "lacks the event-range extension" — a fabricated blocker that
    cost a session on 2026-08-17. Tracked at `PROJECT_TODO.md:13-16`, mentioned three
    times in `MEMORY.md` (`:92`, `:101`, `:304`), never actioned. **This is a
    previously-realized instance of exactly the failure the user is reporting.**

17. **CONFIRMED — `reference/guides/canlose_battle_pipeline_plan.md` says "not built"
    about a feature that shipped.** `:6`: "Status: **design only, not built** (user
    chose design-first 2026-07-21)." But the deterministic path exists and is tested:
    `conversion_agent/transpiler.py:2429` defines
    `_emit_canlose_trainer_battle_idiom`, called from the main emit path at `:2003`,
    covered by `tests/test_transpiler_idioms.py:376,407`
    (`test_canlose_literal_party_emits_earlyrival_and_swapped_branches`, passing).
    *Verified first-hand.* **Wrong action:** an agent concludes can-lose battles still
    need hand-conversion (`hand_conversions/Map050_EV019.pory`) and hand-writes what
    the transpiler already emits.

18. **CONFIRMED — `reference/guides/command_pokeemerald_map.md:8-11` asserts the
    conversion-agent prompt is frozen; `CLAUDE.md:239-240` says it is not.** The guide
    says the guidance is "part of the §9-frozen system prompt — do **not** edit
    mid-campaign, invariant 1". CLAUDE.md: "The prompt is **no longer frozen** (the
    bulk run is retired); edit it like any source file." This is the *highest-traffic*
    guide in `reference/` (12 in-repo references) and the very file `CLAUDE.md` §4.7
    designates as the corrected capability ledger — so its preamble's stale regime
    propagates widely. `grep -n "frozen\|invariant"` in the file it points at
    (`reference/recon/uranium_script_calls.md`) returns nothing, confirming the regime
    is gone. **Wrong action:** an agent refuses a legitimate edit to `system.md`.

19. **CONFIRMED — `reference/guides/phase7_integration_plan.md:73-78` (D4) describes
    the engine cutover as still pending, in a doc written a month after it landed.**
    Text: "**D4** — engine cutover ... Still pointing at the old external clone
    (CLAUDE.md §3) ... Do this EARLY in Phase 7 (or before)". Doc dated 2026-07-14;
    cutover DONE 2026-06-19 per `CLAUDE.md:120`. No DONE annotation anywhere in the
    file. Cited as a live debt ledger 3 times (`FABLE_PLAN.md:187`, `MEMORY.md:24`,
    `reference/archive/README.md:36`). **Wrong action:** an agent re-does a completed
    cutover — and, per finding 16, the obvious way to "verify" it is to point
    `RPG2GBA_POKEEMERALD` at the stale clone, which is the exact hazard `CLAUDE.md` §3
    devotes a paragraph to.

20. **CONFIRMED — `reference/guides/conversion_walkthrough.md:1-9` presents the retired
    LLM per-event loop as the current, actively-built Phase 4 process.** It says the
    scope is "Phase 4 — the event → Poryscript conversion **agent**, because that's ...
    the part we're **actively building**", describing "a **per-event loop** that builds
    a prompt, asks an LLM". `CLAUDE.md` §4.1 says the transpiler is the spine and the
    LLM was retired from it 2026-06-18. **This was already caught in-repo two months
    ago and never fixed:** `reference/findings/critique_2026-07-01.md:176` reads
    "`conversion_walkthrough.md` presents the retired Opus loop as *the* Phase 4
    process." Its 2026-08-05 mtime is a directory-wide reorg touch, not a content
    update. *Verified first-hand.*

21. **CONFIRMED — `reference/viewer/map_inspector_spec.md:10` claims to supersede a
    script that live code still imports.** It says the inspector "generalizes both",
    naming `scripts/compare_collision.py`. But `scripts/map_viewer_common.py:53`:
    `from compare_collision import our_blocked, uranium_blocked`. Also already flagged
    at `reference/findings/critique_2026-07-01.md:177-178` and still uncorrected.
    *Verified first-hand.* **Wrong action:** an agent deletes `compare_collision.py` as
    superseded and breaks the viewer.

22. **Pattern worth naming: `reference/findings/critique_2026-07-01.md` already found
    findings 20 and 21 nine weeks ago, and nothing was done.** The repo has a working
    self-audit habit and a broken follow-through habit. Any remediation plan that ends
    at "write down what's stale" will reproduce this outcome.

23. **CONFIRMED — `HumanBackend` is unreachable from the packaged CLI.**
    `pipeline.py:225` has an `if name == "human":` branch in `_phase4_backend`, but all
    three `--backend` options are `click.Choice(["claude_code", "ollama"])`
    (`pipeline.py:250,305,338`), so `"human"` cannot be selected. Its only live caller
    is out-of-package: `scripts/run_human.py:102`,
    `backend = pipeline._phase4_backend("human")` — reaching into a private function.
    *Verified first-hand.* Tests exist (`tests/test_human_backend.py`,
    `test_skip_lane.py`, `test_tutor.py`), so it is test-live, CLI-dead.

24. **`Orchestrator.convert_all` / `phase4 --run` is the retired LLM bulk spine, still
    wired and budget-spending.** Defined `conversion_agent/orchestrator.py:130`;
    referenced only from `pipeline.py:296` and `scripts/run_bulk.py:181`; **no test
    calls it** (tests exercise `convert_map`/`convert_single` instead). `pipeline.py:265`
    carries the comment "spends Pro/API budget". Retirement cited at `CLAUDE.md:20,271-272`.
    The tail-tool path that *is* current (`convert-map`, `CLAUDE.md:387`) is separate
    and remains legitimate.

25. **`transpile_driver` — the current spine — is not reachable from the `rpg2gba`
    console script.** `pyproject.toml:24-25` maps `rpg2gba` to `pipeline:main`, whose
    click group offers `phase2 phase3 phase4 convert-map convert-common-events phase5`.
    `pipeline.py` never imports `transpile_driver` (grep: no hits), which instead has
    its own click group (`transpile_driver.py:592-621`) invoked as
    `python -m rpg2gba.conversion_agent.transpile_driver run --maps ...`
    (`:13-15`). So the retired spine is on the main CLI and the live spine is not —
    a discoverability trap for any agent that explores via `--help`.

26. **`OllamaBackend` is documented as rejected for production yet is one of only two
    CLI-selectable backends.** `conversion_agent/backends/__init__.py:1-9`: "optional
    local fallback; **rejected for production** (silent-wrong risk)". Still offered at
    `pipeline.py:250,305,338` and referenced by `scripts/{run_bulk,run_slice,regen_outputs}.py`.
    `MEMORY.md:229` records the staged Ollama/local-first plan as retired.

27. ~~**The whole bulk-run resilience stack is dormant.**~~ **REVISED 2026-09-06 — this
    finding was wrong as written; the corrected verdict is finding 44.** What I claimed:
    that `scripts/run_bulk.py`, `prep_bulk_run.py`, `run_stats.py`,
    `conversion_agent/run_report.py`, *and*
    `CappingBackend`/`BudgetReached`/`RateLimitError`/`BackendTransportError` were all
    dormant, on the grounds that the only production-adjacent exerciser is
    `tests/test_bulk_run.py` and that MEMORY.md dates all of it to 2026-06-05…06-12 with
    zero mentions after the pivot. **What is actually true (finding 44):** the
    `backends/` classes are **live by explicit policy** — `BUILD_PLAN.md:26` says
    "`orchestrator.py`/`backends/` remain solely the hand-invoked LLM tail tool" — and
    only the *operator script layer* (`run_bulk.py` and its three satellites) is dormant.
    **Why it was wrong:** I inferred death from MEMORY.md date silence. That is not
    evidence of death; MEMORY.md simply stopped narrating this machinery after the pivot.
    Kept rather than deleted because the reasoning error is the reusable lesson.

28. **No whole orphaned module exists in `src/rpg2gba/`.** A grep of every non-dunder
    module basename across `src/`, `tests/`, `scripts/` returned zero zero-reference
    files. The dead code here is *retired call paths inside live files* (24, 23, 27),
    not abandoned modules — which is precisely why it is dangerous: nothing looks
    unused, so an agent can pick up a retired path and it will run.

29. **Two orphaned `reference/guides/` docs (zero referrers repo-wide):**
    `how_to_use_agents.md` (human session-start script; also carries a stale path,
    `src/conversion_agent/prompts/system.md`, missing the `rpg2gba/` package segment,
    and doesn't mention the prompt is unfrozen or the LLM tail-only) and
    `playing_uranium_wine.md` (Wine setup; operationally harmless).

30. **`reference/recon/phase0_summary.md` is pre-pivot and un-flagged.** `:33` "Allocate
    time for edge cases during bulk conversion"; `:59-61` frames Phase 4 as "start
    calibration (Stage A)". It is absent from `reference/archive/README.md`'s
    moved-docs table, so it missed the cleanup and sits in `recon/` without the
    "do not treat as current" banner that `archive/` carries.

31. **`.claude/skills/pbs-convert/SKILL.md:105` cites a nonexistent path** —
    `reference/pokeemerald_struct_shapes.md`; the file is at
    `reference/guides/pokeemerald_struct_shapes.md`. Minor, but it is a broken
    reference inside an agent-consumed skill.

32. **`reference/` handles staleness correctly in exactly one place.**
    `reference/archive/` + `reference/archive/README.md` document what moved and why,
    and the `viewer/` cluster self-annotates supersession properly
    (`map_inspector_spec.md:2-5` names `map_viewer.md` as current). The failures
    cluster in `guides/` and `recon/`, where nothing distinguishes live from historical.
    The `essentials_to_emerald_map.md` / `command_pokeemerald_map.md` naming confusion
    from `CLAUDE.md` §4.7 **is** properly fixed now (both headers self-describe
    accurately and cross-reference the correction) — only its symptom survives, as
    finding 18.

33. **All source-of-truth JSON files in the `CLAUDE.md` §4.3 table exist at their stated
    paths** — `uranium_id_map.json`, `tileset_map.json`, `strip_list.json`,
    `map_name_overrides.json`, `chapters.json`, `seam_warps.json`, all present and
    nonzero. The one similarly-named sibling, `tileset_map.gen.json`, is documented as
    the generated counterpart at `reference/README.md:7`. No integrity problem here.

34. **MECHANISM — the 2026-08-05 slice→chapter rename pass laundered stale text into
    looking current, and section-local editing keeps it that way.** This explains the
    *class*, not just the instances. `git log -L 246,257:BUILD_PLAN.md` shows the stale
    CH02 block was last touched by commit `a33abdf0` ("Chapters are the unit of work
    now; slices survive only in code", 2026-08-05), which rewrote it mechanically:
    `## 6. Slice 1 (pathfinder) — ... active slice is now slice 2` became
    `## 6. CH01 (Moki Town, pathfinder) — ... active chapter is now CH02`, and
    `SLICE2_TODO.md` became `CH02_TODO.md`. **The claim was true when rewritten** — CH01
    passed 2026-08-04, so CH02 genuinely was the frontier on 2026-08-05. It went stale
    afterward as CH02→CH05 completed. Two things then kept it hidden:
    (a) the rename gave the file current *vocabulary* and a recent commit date, so it
    defeats both date-based and terminology-based staleness detection — the text reads
    as maintained;
    (b) `BUILD_PLAN.md` has since been edited twice (`aa08398b` 2026-08-30, `758abc5b`
    2026-09-01) and both touched **only lines 94-130** (`git show ... | grep '^@@'`),
    never revisiting §6 at line 246. Section-local edits to a document that makes a
    whole-file currency claim ("**Status:** live") leave the unedited sections asserting
    that claim on stale content.
    **Consequence for remediation:** a global find-and-replace terminology pass is
    actively harmful unless each rewritten claim is also checked for truth — it converts
    detectable staleness (old vocabulary, old date) into undetectable staleness. Any
    fix here should move per-chapter status OUT of prose sections that get renamed and
    into the one designated frontier authority (Q1).

35. **CONFIRMED — `reference/guides/canlose_trainer_battles.md:89-91` says trainer
    staging is an unwired "pipeline gap"; it shipped.** The doc: converted trainers
    "are **not yet wired into the slice assembly** — the Theo parties were hand-added.
    Staging converted trainers is a pipeline gap (see the pipeline TODO)." But
    `trainer_converter/stage.py:635` defines `stage_battles(...)`, and
    `scripts/assemble_pathfinder.py:544` calls
    `trainer_stage.stage_slice(uranium_src, trainer_dir)` — the exact
    trainers.json→assembly wiring the doc says is missing. Covered by
    `tests/test_trainer_battles.py` (golden test pinning the Theo trio, plus fail-loud
    edge cases). Corroborated by commits `bbc20ee2` (2026-08-02) and `5bd3fab4`
    (2026-08-05, "Route 1's trainers exist now, and they can see you"), both after the
    doc's 2026-07-21 date. *Verified first-hand.* **Wrong action:** an agent hand-adds
    a trainer party to `engine/src/data/trainers.party` instead of running the staging
    pipeline that already emits it. **This one reached into this very investigation:**
    my earlier Ground-covered note called the canlose doc pair a "clean split" on the
    strength of this file — the overlap assessment stands, but I had no basis to treat
    its content as current. Corrected below.

36. **CONFIRMED — `reference/viewer/map_viewer_palette_plan.md:4` says "implementation
    not yet started" about a view that has been in daily use since the day the plan was
    written.** Status line: "Status: approved, implementation not yet started." But
    `scripts/map_viewer_server.py:11` documents the route
    `GET /palettes/<id> -> palette inspector HTML`, `:81` compiles `_RE_PAL_PAGE`, `:202`
    dispatches `_serve_palette_page`, and `:143` links it from the index. Assets exist
    (`scripts/map_viewer/palette.{html,js,css}`) and `reference/viewer/map_viewer.md`
    documents the palette inspector as live. `MEMORY.md:137` says "Built."
    *Verified first-hand.* The feature commit and the plan doc share a date
    (2026-06-22), so the status line was stale within a day and never revisited.
    **Same section-local mechanism as finding 34:** the file *was* edited 2026-08-28 to
    add a "**Superseded paths (2026-08-28)**" note four lines below the status line,
    and the editor did not fix the status line they were looking at.
    **Wrong action:** an agent re-runs the plan's own `/delegate` build instructions to
    rebuild a shipped feature. Aggravating detail: `MEMORY.md:137` cites this doc as the
    "resume checklist" for a feature it simultaneously records as built — only 1
    referrer, but that referrer is the file every session reads first.

37. **NOT A FINDING (sub-agent report corrected) — `ROM_TEST_DEV.md:39` is stale but
    self-corrects in the next sentence.** A sweep flagged `:39` ("**1 live queue entry**
    left (Map049 species-check, blocked on Phase 7)") as a false-status instance in the
    highest-traffic doc in the corpus (33 referrers, confirmed). The underlying fact is
    indeed stale — `transpiler.py:2389` `_emit_has_species_idiom` is called from `:2000`
    and tested at `tests/test_transpiler_native.py:429`. **But `ROM_TEST_DEV.md:40-41`
    immediately reads: "**Correction (2026-07-24, from the E1 backfill):** that entry is
    **stale — it is already resolved natively.** `checkspecies`
    (`engine/asm/macros/event.inc:2541`) ..."** *Verified first-hand.* No agent reading
    the passage in order is misled. Recorded because it is the **counter-example that
    validates the Q4/Q6 recommendation**: an inline dated correction beside the stale
    claim is exactly the pattern that works, and it is the one case in this audit where
    a stale fact was neutralized rather than left to mislead. `reference/findings/
    hand_bucket_queue.jsonl` also flagged it ("ROM_TEST_DEV.md's ... fact is stale and
    should be corrected by whoever next touches that doc") — and unlike the critique-doc
    items in finding 22, this one *was* actioned in place.

38. **H1 RESOLVED — finding 8's missing `MOVE_NONE` guards are LATENT, not live, and the
    two copies rest on guards of very different strength.**
    *`trainers.py` — hard code guard.* The only call site is `:268`
    (`[r.move_constant(mv) for mv in m.moves]`), and zeros are stripped upstream at
    `:128`: `moves = [rec[i] for i in TPMOVES if rec[i]]` with `TPMOVES = (3, 4, 5, 6)`
    (`:47`) — the four fixed move slots. The `if rec[i]` clause unconditionally drops
    falsy slots, and the field is documented as such at `:73`
    (`moves: list[int]  # nonzero custom moves only`). Dataset-independent.
    *`tm_hm.py` — data-dependent only.* Call site `:141`; `parse_tm` iterates
    `enumerate(raw)` so `move_id` **is** the array index, including 0, guarded only by
    `if entry is None: continue` (`:129-130`). No `move_id == 0` check exists. It is safe
    today purely because index 0 of the real `tm.dat` is null — confirmed empirically in
    `output/uranium-build/intermediate/tm_raw.json` (627 entries, index 0 = `None`).
    *Verified first-hand.* Neither path has test coverage for a synthetic 0:
    `tests/test_pbs_trainers.py` and `test_pbs_tm_hm.py` both only round-trip real
    env-gated Uranium data, so a regression in either filter fails silently in CI.
    **Severity call:** not a bug to fix urgently; the guard asymmetry is still worth
    closing (Q3), and `tm_hm.py` is the one that would go live from an input-data change
    alone, with no code change at all.

39. **H5 RESOLVED (then partly corrected by finding 44) — finding 27 was wrong to call
    `backends/` dormant; deleting that package would break the tail-tool workflow. My
    accompanying claim that `scripts/run_bulk.py` is also live did not hold up.** "Bulk run" has **one** meaning
    throughout the repo — `scripts/run_bulk.py` — and what was retired on 2026-06-18 is
    its *mode* (unattended, frozen-prompt, full-corpus sweep), not the script or its
    machinery. Evidence: `backends/__init__.py:63-71`, the `EventDeferred` docstring,
    names it explicitly — an operator punt leaves the event "unconverted and un-memoized
    so the bulk run (`run_bulk.py`) claims it later"; `BUILD_PLAN.md:26` states
    "`orchestrator.py`/`backends/` remain solely the hand-invoked LLM tail tool"; and
    and commit `9ceed1b3` adds `--skip-lane` to `run_bulk.py` to hold
    hand-conversion-lane events for `run_human` (**I described this commit as
    "post-pivot"; it is not — see the correction below**). So the chain
    `human_quickref.md:56` ("type `opus` to punt it to the bulk run") →
    `backends/human.py:119` (`raise EventDeferred`) → `scripts/run_human.py:122-125`
    ("punted to Opus") → `run_bulk.py` mop-up is internally coherent as *code*.
    *Verified first-hand: the docstring and the BUILD_PLAN line. I did NOT verify the
    commit date, and that is where this finding went wrong — see the correction below.*
    **Still live, do not delete:** `CappingBackend`, `BudgetReached`, `RateLimitError`,
    `BackendTransportError`, `ClaudeCodeBackend` — i.e. the `backends/` package.
    **CORRECTION (finding 44):** two claims in this finding do not survive. (i) Commit
    `9ceed1b3` is dated **2026-06-12 — six days BEFORE the 2026-06-18 pivot**, not after,
    so it is not evidence of post-pivot currency. (ii) `scripts/run_bulk.py` should NOT
    have been listed as "still live": nothing in `src/` or `tests/` imports or executes
    it and no current doc mentions it. The `backends/` half of the verdict stands on
    `BUILD_PLAN.md:26`, which is policy and not date-dependent; the script half is
    reversed. `run_report.py`, `run_stats.py`, `prep_bulk_run.py` remain unresolved
    (H7 → Q11).
    **Lesson for this audit:** finding 27 inferred dormancy from MEMORY.md date silence.
    That was the wrong instrument — MEMORY.md's post-pivot entries simply stopped
    narrating this machinery. Date silence in a bloated notes file is not evidence of
    death.

40. **CONFIRMED — two custom engine edits are UNFENCED, invisible to a
    revert-against-upstream check.** `engine/` was vendored by flat `git archive` at
    commit `80cdfce2`, so `git diff 80cdfce2 HEAD -- engine/` is the exact
    custom-vs-pristine diff: **77 files changed, 2647 insertions, 343 deletions**
    (upstream `21c24202` is not a reachable object here — `engine/RPG2GBA_VENDOR.md`
    explains why). Two of those changes carry no sentinel:
    - `engine/include/global.h:28` — `#include "config/uranium_walker.h"` added with
      **zero comment**. Required by every `URANIUM_MAP_WALKER` `#if` site.
    - `engine/include/config/save.h:11` — `FREE_MYSTERY_EVENT_BUFFERS` flipped
      `FALSE`→`TRUE`, with only a trailing inline note. Required to offset the
      SaveBlock1 growth from `RPG2GBA_EXPAND_EVENT_RANGES`.
    *Both verified first-hand via the diffs.* `save.h` is the nastier of the two: a grep
    for `URANIUM`/`RPG2GBA` finds its *comment*, but the semantically important part —
    the changed macro value — sits outside any fence, so a "strip everything between
    sentinels" revert would silently leave it behind and produce a save-layout mismatch.

41. **The fence convention is four vocabularies, not one, so `CLAUDE.md` §5's phrasing
    under-describes it.** Actually in use: `BEGIN/END URANIUM PATHFINDER SLICE`
    (dominant, ~40 sites, sometimes suffixed `(rpg2gba)`), `BEGIN/END URANIUM MAP WALKER`
    (`event_object_movement.c`, `uranium_map_walker.c`, `overworld.c`,
    `field_control_avatar.c`, `new_game.c`, `config/overworld.h`),
    `BEGIN/END URANIUM EMBEDDED SAVE` (`new_game.c`, `uranium_embedded_save.c`), and
    `BEGIN/END RPG2GBA EVENT RANGE EXPANSION` (`include/constants/flags.h:1660`,
    `vars.h:279`, `src/event_data.c`). Plus a no-`BEGIN` variant of the main fence at
    `src/berry.c:1625,1723`, `items.h:12168`, `graphics.h:1908,1992`,
    `item_menu_icons.c:387`. **Consequence:** a grep for the documented string
    `URANIUM PATHFINDER SLICE` misses the walker, embedded-save, and event-range fences
    entirely. Every `BEGIN` checked had a matching `END`.

42. **CONFIRMED — `engine/RPG2GBA_VENDOR.md` describes the custom edits as three
    test-only files; there are 77 changed files of permanent logic.** The doc's "Our
    custom changes" section (`:26`, `:41-47`) says: "**Test-only baseline divergences —
    revert/gate before a real build.** Sentinel-fenced blocks in: `src/new_game.c`,
    `src/intro.c`, `include/new_game.h`". `MEMORY.md:101` repeats this as "3
    sentinel-fenced custom files". Reality (verified: 77 files, 2647 insertions)
    includes whole new source files (`uranium_map_walker.c`, 761 lines;
    `uranium_embedded_save.c`, 66 lines), a movement-type bytecode interpreter
    (`event_object_movement.c:6178-6376`, registered in the movement tables at `:354-356`
    and `:486-488`), rematch/heal-fix logic in `battle_setup.c:235-240,1328-1343`,
    pacing knobs in `palette.c`/`sound.c`, Uranium berries in
    `berry.c`/`item_menu_icons.c`, and ~15 generated-content include-hooks. **This is the
    most consequential doc error found in the audit**: an agent trusting it would
    believe the engine is three reverts away from pristine, and could wipe permanent
    features while "reverting test-only divergences" before a build.

43. **No dead config flags in the engine — all nine are tested.**
    `engine/include/config/rpg2gba.h` defines `RPG2GBA_EXPAND_EVENT_RANGES`
    (tested `flags.h:1662`, `vars.h:281`, `event_data.c`), `RPG2GBA_FAST_TEXT_DEFAULT`
    (`new_game.c:120`), `RPG2GBA_FADE_DELTA_Y` (`palette.c:120,165,480`),
    `RPG2GBA_BGM_TEMPO_SCALE` (`sound.c:571`), `RPG2GBA_TRAINER_REGISTERED_FLAGS_COUNT`
    (`flags.h:1681`) and the four count macros. `RPG2GBA_BGM_TEMPO_SCALE` is inert at its
    current value 256 **by design** — the file's own comment says "at 256 the call site
    compiles away entirely" — a neutral knob, not a leftover. `URANIUM_MAP_WALKER`
    (currently `FALSE`) is tested in 8 places; both branches compile, and the disabled
    branch is a documented dual-mode debug ROM, not dead code. Also confirmed clean: the
    retired `ObjectEventGetNearbyReflectionType` narrow-scan experiment was fully
    reverted — `event_object_movement.c:10182` is pristine, no `#if 0` body, no orphan
    fence.

44. **FINDING 39 PARTIALLY CORRECTED — the two sweeps disagreed on the bulk run, and both
    were half right. Split the verdict by layer.** My finding 39 cited commit `9ceed1b3`
    (`--skip-lane`) as *post-pivot* evidence that `run_bulk.py` is current. **That was
    wrong: `git log -1 9ceed1b3` gives 2026-06-12, six days BEFORE the 2026-06-18
    pivot.** `scripts/run_bulk.py` itself was last touched 2026-06-16 — also pre-pivot.
    *Verified first-hand.* The correct split:
    - **`backends/` + `orchestrator.py` — LIVE, by explicit policy.** `BUILD_PLAN.md:26`:
      "`orchestrator.py`/`backends/` remain solely the hand-invoked LLM tail tool." That
      still holds and is not date-dependent. `CappingBackend`, `ClaudeCodeBackend`,
      `BudgetReached`, `RateLimitError`, `BackendTransportError` stay.
    - **`scripts/run_bulk.py` — DORMANT as an operator entry point.** No `src/` or
      `tests/` file imports or executes the script; every mention is a comment naming its
      CLI flag (`backends/__init__.py:12,70`, `lane.py:4`, `orchestrator.py:103,151,483`).
      `tests/test_bulk_run.py` imports `orchestrator`/`run_report` directly, never the
      script. **No current doc mentions it at all** — grep of `BUILD_PLAN.md`,
      `POST_CH05_REVIEW.md`, `CH05_DECISIONS.md`, `PROJECT_TODO.md` returns nothing.
      *Verified first-hand.*
    - **`reference/guides/human_quickref.md` is itself stale.** Last commit 2026-07-13,
      before the chapter pivot; its "punt it to the bulk run" instruction (`:56`) is the
      only surviving reference to that workflow. So the `EventDeferred` docstring chain I
      cited in 39 is *internally coherent but describes a workflow no current doc uses*.
    **Net:** delete nothing in `backends/`; treat the `run_bulk.py`/`prep_bulk_run.py`/
    `run_stats.py`/`run_report.py` operator layer as dormant pending Q11. **Second
    instance of the finding-39 lesson, this time in my own work:** I accepted a
    sub-agent's "post-pivot commit" framing without checking the date.

45. **H6 RESOLVED — `run_slice.py` and `regen_outputs.py` are dead and the repo already
    says so in prose, twice, with warnings attached.**
    `reference/guides/slice_expansion_runbook.md:68`: "Ignore the stale literals in
    `scripts/run_slice.py:66` (retired LLM path)".
    `reference/memory-archive.md:530`: "**Do NOT reach for `run_slice.py` for this —
    that's the retired LLM driver and it spends budget.**"
    `reference/memory-archive.md:131`: "**`scripts/regen_outputs.py` is the retired LLM
    path, not the way to re-emit** — it deletes `.pory` and checkpoints *before*
    replaying and aborts when a common event needs a real spawn, leaving output/
    stripped; it also *creates* `output/uranium-build/checkpoints/`, which flips 3 corpus
    tests from skip to fail. **The live re-emit is
    `python -m rpg2gba.conversion_agent.transpile_driver run --maps slice`**."
    *Verified first-hand.* **These two scripts are actively harmful, not merely dead** —
    one spends budget, the other strips `output/` and breaks three tests. The warnings
    are buried in a runbook footnote and a memory-archive entry; nothing in the scripts
    themselves says so. This is the strongest deletion candidate in the audit.

46. **CONFIRMED — `scripts/tree_debug.py` is a second instance of finding 21 exactly.**
    `reference/viewer/map_inspector_spec.md:9` says "**Supersedes:** the ad-hoc debug
    scripts `scripts/tree_debug.py` (per-layer render)". But the *current* viewer doc
    documents it as a live, separate tool: `reference/viewer/map_viewer.md:129` ("**Not
    part of this tool:** `tree_debug.py` — a separate script that emits a **PNG**"),
    `:274` (its own section, "separate per-layer collapse debugger") and `:283` a working
    invocation (`python scripts/tree_debug.py --x0 33 --y0 40 ...`). *Verified
    first-hand.* So `map_inspector_spec.md` now has **two** false supersession claims —
    `compare_collision.py` (finding 21) and `tree_debug.py` — both about scripts the
    live stack still uses. That file is the single least trustworthy doc in `reference/`.

47. **`scripts/` inventory: ~20 load-bearing, ~75 spent, 2 uncertain, 6 orphaned caches.**
    `scripts/` has 83 `.py` files (plus shell/ruby and 7 `map_viewer/` assets).
    **Load-bearing** (evidence in each case is an import or a live doc instruction):
    `assemble_pathfinder.py` (called from 5 `src/` modules), `map_graph.py`,
    `map_viewer_common.py`, `map_viewer_server.py`, `map_viewer_events.py`,
    the 7 `map_viewer/` assets, `compare_collision.py`, `stage_slice_scripts.py`,
    `stage_species.py`, `stage_trainers.py`, `extract_rgssad.py` (`README.md:25`),
    `fetch_libmgba.py` (`playtest/__init__.py:5`), `fetch_uranium_wiki.py` (used by the
    `pokemon-uranium-wiki` skill), `oracle_harvest.py` (`tests/test_hand_overrides.py:351`
    pins its API), `run_human.py` + `run_tutor.py` (test-imported helpers), `tree_debug.py`,
    `verify_viewer_rom_match.py`.
    **Spent clusters:** the Phase-0 recon set (`phase0_run_all.sh` + `recon_*.py/rb`,
    `spike_dat_inventory.rb`, `dump_constants.rb`, `dump_messages.rb` — job done
    2026-05-09, output checked into `reference/recon/`); ~17 Phase-4 "Fables" one-offs
    (`assembly_smoke.py`, `compile_pory.py`, `convert_one_event.py`,
    `count_deterministic_*.py`, `dup_label_scan.py`, `pick_*.py`, etc.);
    the closed difficulty-analysis pair (`measure_trivial_tier.py` +
    `near_miss_families.py`, decision "rejected on measurement" per `MEMORY.md:229`);
    ~6 pathfinder S1-era previews; **~28 Phase-5 graphics exploratory scripts** (all
    dated 2026-07-02, results folded into `reference/guides/graphics_conversion_notes.md`)
    — the single largest spent cluster; plus `charmap_lint.py` (superseded by
    `assembly.normalize_pory` per `MEMORY.md:306`) and `convert_uranium_item_icons.py`.
    **Uncertain:** `count_unique_commands.py` (`reference/findings/agent_coverage_diff.md:117`
    still gives a literal "Reproduce" command, and its outputs are checked in, but its
    framing — the agent's frozen system prompt — is a retired regime);
    `pathfinder_collision_preview.py` (SPENT, but `tileset_converter/layout.py:174` and
    `compare_collision.py:7` cite its `cell_blocked` as the implementation they *mirror*
    — provenance, not invocation, so it is load-bearing by algorithm lineage only).
    Per the Decisions entry, spent one-offs in `scripts/` are **expected** and are not a
    defect — this inventory exists so nobody has to re-derive it, not as a deletion list.

48. **Six orphaned `.pyc` caches whose `.py` source no longer exists** —
    `scripts/__pycache__/` holds 18 entries against 83 source files. Orphans:
    `scratch_items_probe`, `_tmp_sonnet_tier` (renamed to `measure_trivial_tier.py`),
    `_tmp_smoke_human`, `_tmp_smoke_tutor`, `build_map_viewer` and `palette_page` (both
    sources deleted in the 2026-08-28 cleanup per `MEMORY.md:151`). Harmless, but they
    are why a filename-based search can surface a module that does not exist — a small
    contributor to the confusion this audit is about. Note `.pyc` presence is *not*
    evidence of liveness (bytecode regenerates on any import, live or dead) and was not
    used as such anywhere above.

## Hypotheses / unverified

- ~~**H1**~~ — RESOLVED, see finding 38 (LATENT both). Original text: `trainers.py`/`tm_hm.py` may never actually receive `move_id == 0`, making
  finding 8 latent rather than live. Confirming: trace whether trainer party move
  slots and TM/HM tables can carry an unset slot through to `move_constant`. The
  divergence is real either way; only the severity is open.
- ~~**H2**~~ — RESOLVED 2026-09-07 and **fixed**. Verdict was PARTIAL-OVERLAP: both
  loaders read the same two sidecars with the same `int(k)` normalization, so they
  could never mint a *different name* for the same id — but `_load_name_table`
  returned `{}` on a missing file where `seed_labels` raises, and both JSONs are
  tracked in git, so the silent path could only ever hide a real breakage. Both now
  call one `flag_registry.load_label_tables`; the generator's sidecar paths are
  anchored to the repo instead of the CWD (the CWD-relative read was what the empty
  table had been masking — `tests/test_chapter_manifest_cli.py` runs in an isolated
  filesystem and went red the moment the loader started failing loud, which is the
  proof the old behaviour was hiding something). Original text: `_load_name_table`
  may duplicate `flag_registry.py`'s switch/variable sidecar loader.
- ~~**H3**~~ — RESOLVED 2026-09-07, **no action taken, deliberately.** The diff was
  done. **No diverged copies exist** — the dangerous case (a fix landing in one copy
  and not the others) is not present. A 2026-08-20 consolidation had already promoted
  the cross-file helpers into `src/rpg2gba/playtest/assertions.py`, and the chapters
  hold thin aliases to it. What remains is ~150 lines across `ch02`/`ch04`/`ch05`
  (`_walk_absorbing`, `_trainer_defeat_flag`), verified behaviourally identical, plus
  per-chapter beat bodies — coordinates, flags, map constants — which are data, not
  duplication, and account for essentially all of the 29 KB–93 KB. Extraction was
  **declined**: it would reopen CH01–CH04, all of which have passed their §9 boot
  gates, for a mechanical ~150-line move with no defect to fix. If it is ever done it
  should ride along with a chapter already being reopened. Original text: the family
  is heavy copy-paste; a full line-level diff was not done.
- **H4. `ROM_TEST_DEV.md` (61 KB) is a raw grill/design transcript, not a current-state
  doc** — so its pervasive "slice" usage is lower-risk. Based on its framing, not on a
  full read.
- ~~**H5**~~ — RESOLVED by findings 39 **and 44** together. Net verdict: the `backends/`
  package is live by policy (so finding 27 was wrong to include it), while the
  `run_bulk.py` operator script layer is dormant (so finding 39 was wrong to defend it).
  Read 44, not 39 alone. Original hypothesis: the dormant bulk-run stack may still be
  load-bearing for the *tail* tool. `reference/guides/human_quickref.md:56` ("type `opus` to punt it to
  the bulk run") suggests "bulk run" now means a bounded run of the hand-invoked tail
  tool over the lane queue, not the retired 199-map sweep — and `run_report.py` /
  `human.py` do still exist. The term is overloaded across two eras. Confirming:
  ask whether the lane-queue punt path is still used before deleting anything in 27.
- ~~**H6**~~ — RESOLVED, see finding 45: both are dead AND actively harmful.
- **H7. The `run_bulk.py` operator layer** — `run_bulk.py`, `prep_bulk_run.py`,
  `run_stats.py`, `run_report.py`. Finding 44 establishes no code or current doc
  references them, but `backends/` (which they drive) is retained by explicit policy.
  Only the operator knows whether a bounded tail run is still part of the workflow.
  Escalated to Q11 rather than left as a hypothesis.
- ~~**H8**~~ — RESOLVED 2026-09-07: **the script is KEPT; only the diff document is
  retired.** The two halves come apart cleanly. `count_unique_commands.py` is a
  zero-LLM walk of the deserialized corpus that depends on nothing about the LLM
  regime, spends nothing, and produces `reference/recon/uranium_real_commands.md` /
  `uranium_excluded_noncommands.md` — the command-vocabulary ledger the *deterministic
  transpiler* is measured against, which is more relevant after the pivot, not less.
  Its header now says so, explicitly warning against retiring it alongside its
  neighbour. `reference/findings/agent_coverage_diff.md` is the regime-bound half —
  it compares that census to the agent's **frozen** prompt — and is bannered
  HISTORICAL, with its "Reproduce" block split into the live census command and the
  retired parity check. Original text: a checked-in findings doc still gives a
  "Reproduce" command for it, but its whole framing is a retired regime.

## Decisions

- **2026-09-06 — engine/ scope.** Q: is the vendored `engine/` tree in audit scope?
  A: only the custom sentinel-fenced edits and rpg2gba-specific headers; pristine
  upstream pokeemerald-expansion is out of scope. *Effect:* no upstream dead-code
  sweep; a fenced-edit inventory is still owed (Next steps #3).
- **2026-09-06 — scripts/ policy.** Q: how to treat `scripts/` (115 files of one-offs)?
  A: in scope as an inventory — separate genuinely spent one-offs from load-bearing
  pipeline steps still invoked by code or docs. *Effect:* Next steps #2.

- **2026-09-07 — Q1–Q13 all answered.** Compact record; full text under Open questions.
  | Q | Answer | What it changed |
  |---|---|---|
  | Q1 | `MEMORY.md` → Current Phase is the **sole** frontier authority | Every other doc gets a "historical / topic reference" header and stops asserting what to do next. Unblocks Q2, Q4. |
  | Q2 | Prune now, enforce later | Hoist live status to a skimmable headline; chronicle out of lines 18/43 into `memory-archive.md`; evict 4 resolved Open Questions. **No CI byte cap.** |
  | Q3 | Guard now, consolidate separately | Two-line fix to `trainers.py:216` / `tm_hm.py:88`; the five-way `*_constant` consolidation becomes its own scoped change. |
  | Q4 | Both, split by doc | Banner `BUILD_PLAN.md`/`ROADMAP.md`/`PROJECT_TODO.md`; archive `FABLE_PLAN.md` and `PLAYTEST_AUTHORING_IMPROVEMENT.md` V1. |
  | Q5 | **Keep, rename to a warning name** (diverges from the recommendation to delete) | External clone survives as `pokeemerald-expansion-PRISTINE-DO-NOT-USE`; upstream stays available for diffing, misuse becomes self-evident at the path level. `MEMORY.md` ×3 + `PROJECT_TODO.md:13-16` updated to the new name and closed. |
  | Q6 | Fix in the same change; banner in place | No CI check, no PROJECT_TODO filing. Finding 37's inline dated correction is the model. |
  | Q7 | Both, in one change | Add `transpile-events` to the `pipeline.py` click group; make `phase4 --run` refuse and name the replacement. |
  | Q8 | **Leave as-is, document it** (diverges from the recommendation to widen `click.Choice`) | `HumanBackend` stays script-only by design; add explanatory comments at `pipeline.py:225` and in `scripts/run_human.py`. No code deleted, no CLI change. |
  | Q9 | All three | Rewrite the vendor doc's custom-changes section, fence `global.h:28` + `save.h:11`, correct `CLAUDE.md` §5's fence vocabulary, fix `MEMORY.md:101`. |
  | Q10 | **Yes, plus a summary** (extends the recommendation) | `git diff 80cdfce2 HEAD -- engine/` is canonical in `CLAUDE.md` §3 and `RPG2GBA_VENDOR.md`, replacing the hand list — but a short feature-area summary stays for orientation, explicitly labelled as orientation, not inventory. |
  | Q11 | No — mark all four spent | `run_bulk.py`, `prep_bulk_run.py`, `run_stats.py`, `run_report.py` marked spent; `human_quickref.md:56`'s punt instruction retired. **`backends/` + `orchestrator.py` stay.** Resolves H7. |
  | Q12 | Delete both | `scripts/run_slice.py` and `scripts/regen_outputs.py` removed outright, not guarded. |
  | Q13 | Archive it | `reference/viewer/map_inspector_spec.md` → `reference/archive/`. |

- **2026-09-07 — three answers diverge from my recommendation; note them so nobody "corrects" them back.**
  Q5 (rename, don't delete), Q8 (document the reach-around rather than widen the CLI), and Q10
  (keep an orientation summary beside the canonical diff command). Each is a deliberate call,
  not an oversight.

## Open questions

**None — all 13 were answered 2026-09-07.** They are kept below with their recommendations and answers intact, because the rationale is what makes the remediation plan legible to a cold reader; the compact version is in Decisions.

### Q1. Which document should become the single "what to do next" authority?
Finding 2 is the root cause of the reported confusion: six docs claim currency and
nothing ranks them. Any fix to the individual stale lines leaves the structural problem
in place. The candidates are `BUILD_PLAN.md` (owns *how*, currently stale),
`MEMORY.md` → Current Phase (already designated by `CLAUDE.md` §7 as holding "the
active phase and next concrete task"), or a new thin `STATUS.md`.

**Recommendation:** Keep `MEMORY.md` → Current Phase as the sole frontier authority,
since `CLAUDE.md` §7 already says so, and demote every other doc to an explicit
"historical / topic reference" header. Cheaper than a new file and removes the
contradiction rather than adding a seventh claimant.
**Blocked on:** —
**Answer:** **MEMORY.md → Current Phase is the sole frontier authority** (2026-09-07). Every other doc gets an explicit "historical / topic reference" header and stops asserting what to do next. No new STATUS.md.
### Q2. Is MEMORY.md worth restructuring now, or only pruning?
It is protocol-compliant in structure but 260 KB with 27 KB single lines (findings 4-7).
Pruning to protocol (evict the 4 resolved Open Questions, move oversized Key File Notes
to `reference/`, break the mega-lines) is maybe a session of careful work. A harder
version — cap the file at some byte budget and enforce it in CI — is more.

**Recommendation:** Prune now, mechanically enforce later. The specific high-value cut
is line 18 and line 43: hoist the live status (CH05 passed / CH06 frontier) into a
short skimmable headline and push the historical chronicle into
`reference/memory-archive.md`, which is already the designated destination.
**Blocked on:** Q1
**Answer:** **Prune now, mechanically enforce later** (2026-09-07). Hoist the live status (CH05 passed / CH06 frontier) into a short skimmable headline, push the historical chronicle out of lines 18 and 43 into `reference/memory-archive.md`, evict the 4 already-resolved Open Questions, move oversized Key File Notes to `reference/`. No CI byte cap in this pass.
### Q3. Fix the `move_constant` divergence by consolidation, or just add the guard?
Finding 8 is a confirmed inconsistency across five copies; finding 38 establishes it is
latent, not a live bug, so this is hygiene rather than a fix under pressure. Adding the
missing guard to two files is a two-line fix; extracting one shared resolver touches five
converters that all have golden tests. Note finding 38's asymmetry: `tm_hm.py` is safe
only because index 0 of the real `tm.dat` is null, so it could go live from an input-data
change with no code change at all.

**Recommendation:** Add the guard now (removes the divergence today), and file the
consolidation separately — the same five-way copy-paste affects `item_constant`,
`species_constant` and `ability_constant`, so it wants its own scoped change with the
golden tests re-run, not a drive-by.
**Blocked on:** —
**Answer:** **Add the guard now; file the consolidation separately** (2026-09-07). Two-line fix to `trainers.py:216` and `tm_hm.py:88` in the remediation pass; the five-way `move_/item_/species_/ability_constant` consolidation becomes its own scoped change with the golden tests re-run.
### Q4. How aggressive should the stale-doc treatment be — annotate or archive?
Findings 1, 3, 12, 13, 14, 15 are all stale text in otherwise-useful documents.
Options: (a) add a dated "SUPERSEDED — see X" banner at the top of each, (b) move spent
docs (`FABLE_PLAN.md`, `PLAYTEST_AUTHORING_IMPROVEMENT.md` V1) into `reference/archive/`
alongside the retired chapter TODOs, (c) both.

**Recommendation:** (c), split by doc: banner the docs that are still consulted
(`BUILD_PLAN.md`, `ROADMAP.md`, `PROJECT_TODO.md`), and physically archive the fully
spent ones (`FABLE_PLAN.md`, V1) so nothing greps them up as current. `reference/archive/`
already exists and is the established convention.
**Blocked on:** Q1
**Answer:** **Both, split by doc** (2026-09-07). Banner the still-consulted docs (`BUILD_PLAN.md`, `ROADMAP.md`, `PROJECT_TODO.md`) with a dated header deferring frontier status to `MEMORY.md` (per Q1); physically archive the fully spent ones (`FABLE_PLAN.md`, `PLAYTEST_AUTHORING_IMPROVEMENT.md` V1) into `reference/archive/`.
### Q5. Delete the external `/home/b/repos/pokeemerald-expansion` clone?
Finding 16: it is outside this repo, it is pristine upstream, it has already burned one
session via a fabricated blocker, and its removal has been an open PROJECT_TODO item
across at least three MEMORY.md mentions.

**Recommendation:** Delete it. It is the one finding in this audit with a proven
past cost and a one-command fix. Out-of-repo deletion is the user's call, hence this
question rather than an action.
**Blocked on:** —
**Answer:** **Keep it, rename it to a warning name** (2026-09-07) — e.g. `pokeemerald-expansion-PRISTINE-DO-NOT-USE`. Upstream stays available for reference/diffing; misuse becomes self-evident at the path level. Update the three `MEMORY.md` mentions and `PROJECT_TODO.md:13-16` to the new name and close the item.
### Q6. Do the "already caught, never fixed" findings need a follow-through mechanism?
Findings 20 and 21 were both documented in `reference/findings/critique_2026-07-01.md`
nine weeks ago and are still live (finding 22). The repo audits itself well and acts on
audits poorly, so this investigation is at risk of the same fate.

**Recommendation:** When remediating, fix the doc text in the same change that records
the finding, rather than filing it — and for anything not fixed immediately, put the
banner on the offending file itself, not in a findings doc nobody re-reads. A findings
doc is not a mechanism.
**Blocked on:** Q4
**Answer:** **Fix in the same change; banner in place** (2026-09-07). No new mechanism. Remediate doc text in the same change that records the finding; for anything not fixed immediately, put a dated banner on the offending file itself, never in a findings doc. Finding 37 (`ROM_TEST_DEV.md`'s inline dated correction) is the in-repo proof this pattern works. No CI staleness check, no PROJECT_TODO filing.
### Q7. Should the retired LLM bulk path be removed from the CLI, or just labelled?
Findings 24-27 plus 25's discoverability trap: `phase4 --run` (retired, budget-spending,
untested) is on the main `rpg2gba` console script, while the live deterministic spine
(`transpile_driver`) is only reachable via `python -m`. An agent exploring `--help`
finds the retired path and not the current one.

**Recommendation:** Do both, in one change: add `transpile-events` to the `pipeline.py`
click group delegating to `transpile_driver.cli`, and make `phase4 --run` refuse with a
message naming the replacement. Removing the code outright is riskier — per finding 44
the `backends/` package is retained by policy, even though the `run_bulk.py` script layer
that drives it looks dormant (Q11).
**Blocked on:** —
**Answer:** **Do both, in one change** (2026-09-07). Add `transpile-events` to `pipeline.py`'s click group delegating to `transpile_driver.cli`, and make `phase4 --run` refuse with a message naming the replacement. Delete no code in `backends/`.
### Q8. Is `HumanBackend` meant to be CLI-reachable?
Finding 23: `pipeline.py:225` handles `"human"` but no `--backend` choice offers it;
only `scripts/run_human.py` reaches it, via the private `_phase4_backend`.

**Recommendation:** Add `"human"` to the three `click.Choice` lists — the branch and
its three test files indicate it is wanted, and the private-function reach-around in
`scripts/run_human.py` is a symptom of the gap, not a design. If instead it is spent,
delete the branch, the backend, and the script together.
**Blocked on:** Q7
**Answer:** **Leave as-is and document it** (2026-09-07). `HumanBackend` stays script-only; add a comment at `pipeline.py:225` and in `scripts/run_human.py` stating that `"human"` is intentionally not a `--backend` choice and is reached deliberately via `_phase4_backend`. Do not widen the `click.Choice` lists, do not delete the backend.
### Q9. Fix `engine/RPG2GBA_VENDOR.md` and fence the two unfenced edits?
Finding 42 is the highest-consequence doc error in the audit: the vendor doc says the
custom C is three test-only files to "revert/gate before a real build", when the real
diff is 77 files including two whole new source files and a movement bytecode
interpreter. Finding 40 adds two unfenced edits (`global.h:28`, `save.h:11`) that a
sentinel-based revert would silently miss. Finding 41: the fence vocabulary is four
strings, not the one `CLAUDE.md` §5 documents.

**Recommendation:** All three, and treat it as the most urgent item in the audit — it is
the only finding whose failure mode is *destroying working engine features*. Concretely:
replace the vendor doc's custom-changes section with a generated summary of
`git diff 80cdfce2 HEAD -- engine/ --stat`, fence the two bare edits, and correct
`CLAUDE.md` §5 to list all four sentinel vocabularies. Also fix `MEMORY.md:101`, which
repeats the "3 sentinel-fenced custom files" claim.
**Blocked on:** —
**Answer:** **All three** (2026-09-07): rewrite `RPG2GBA_VENDOR.md`'s custom-changes section from the real diff, fence `global.h:28` and `save.h:11`, and correct `CLAUDE.md` §5 to list all four sentinel vocabularies. Also fix `MEMORY.md:101`'s "3 sentinel-fenced custom files".
### Q10. Should `git diff 80cdfce2 HEAD -- engine/` become the documented way to see custom edits?
The vendored tree has no upstream history, so that one command is the definitive
custom-vs-pristine answer (finding 40) — and it cannot go stale the way a hand-maintained
file list did.

**Recommendation:** Yes — put it in `CLAUDE.md` §3 and in `RPG2GBA_VENDOR.md` as the
canonical check, replacing the hand-maintained list rather than supplementing it. A
hand-maintained inventory of 77 files will rot again; this is the general fix for the
finding-34 class, applied here.
**Blocked on:** Q9
**Answer:** **Yes, with a summary alongside** (2026-09-07). `git diff 80cdfce2 HEAD -- engine/` becomes the canonical check in `CLAUDE.md` §3 and `RPG2GBA_VENDOR.md`, replacing the hand-maintained file list — but keep a short human-readable summary of the major feature areas (map walker, embedded save, event-range expansion, movement bytecode interpreter, generated-content include-hooks) so an agent gets orientation without running git. The summary is explicitly orientation, not an inventory.
### Q11. Is a bounded LLM tail run still part of the workflow?
Finding 44: `backends/` is retained by explicit policy (`BUILD_PLAN.md:26`), but the
operator layer that drives it (`run_bulk.py`, `prep_bulk_run.py`, `run_stats.py`,
`run_report.py`) has no code referrer, no current-doc mention, and was last touched
pre-pivot. Only you know whether you still punt events to it. CH05 and CH06 appear to
have been built without it.

**Recommendation:** If you have not punted an event since the pivot, mark all four spent
and add a line to `human_quickref.md` saying the punt path is retired — leaving a live
"type `opus` to punt it" instruction (`:56`) pointing at dormant machinery is the same
trap as finding 1. Keep `backends/` either way; `convert-map` still needs it.
**Blocked on:** —
**Answer:** **No — mark all four spent** (2026-09-07). No event has been punted since the pivot. `run_bulk.py`, `prep_bulk_run.py`, `run_stats.py`, `run_report.py` are marked spent, and `reference/guides/human_quickref.md` gets a line retiring the punt path so `:56` stops pointing at dormant machinery. **`backends/` and `orchestrator.py` stay** — `convert-map` needs them.
### Q12. Delete `run_slice.py` and `regen_outputs.py`?
Finding 45: both are retired LLM paths, and both are *harmful* if run — `run_slice.py`
spends API budget, `regen_outputs.py` strips `output/` and flips three tests from skip to
fail. The warnings exist only in a runbook footnote and a memory-archive entry; the
scripts themselves say nothing.

**Recommendation:** Delete both. This is the clearest action in the audit: they cannot be
run correctly, an agent that finds them by filename has no in-file warning, and the
correct replacement is documented
(`transpile_driver run --maps ...` then `stage_slice_scripts.py --write`). If you would
rather keep them for reference, a one-line `raise SystemExit("retired — use ...")` at the
top of each is the cheap alternative.
**Blocked on:** —
**Answer:** **Delete both** (2026-09-07). `scripts/run_slice.py` and `scripts/regen_outputs.py` are removed outright, not guarded.
### Q13. Is `reference/viewer/map_inspector_spec.md` worth keeping at all?
Findings 21 and 46: it carries two false supersession claims (`compare_collision.py`,
`tree_debug.py`), both about scripts the live viewer still uses, and both were flagged in
`critique_2026-07-01.md` nine weeks ago. It is the least trustworthy doc in `reference/`.

**Recommendation:** Archive it. `reference/viewer/map_viewer.md` is the current doc, it
self-annotates correctly, and it already documents both scripts accurately — the spec's
only remaining function is to mislead.
**Blocked on:** Q4
**Answer:** **Archive it** (2026-09-07). Move `reference/viewer/map_inspector_spec.md` to `reference/archive/`; `reference/viewer/map_viewer.md` is the current doc and already documents `compare_collision.py` and `tree_debug.py` accurately.
## Next steps

**The investigation is closed. What follows is the artifact: the remediation plan, ordered by
risk-per-unit-effort.** Each stage is independently shippable. Per Q6, *every* stage fixes the
text in the same change that records the finding — nothing here gets filed for later.

### Stage A — engine safety (Q9, Q10). Do this first; it is the only work whose failure mode is destroying working code.
1. Rewrite `engine/RPG2GBA_VENDOR.md`'s "Our custom changes" section (`:26`, `:41-47`). Delete the
   "three test-only files — revert/gate before a real build" claim outright. Replace with:
   (a) `git diff 80cdfce2 HEAD -- engine/` named as **the** canonical custom-vs-pristine check,
   with a note on why `21c24202` is unreachable; (b) a short orientation summary of the feature
   areas — map walker, embedded save, event-range expansion, movement bytecode interpreter,
   battle_setup rematch/heal, palette/sound pacing knobs, Uranium berries, ~15 generated-content
   include-hooks — explicitly labelled *orientation, not an inventory* (Q10).
2. Fence the two unfenced edits (finding 40): `engine/include/global.h:28` (the bare
   `#include "config/uranium_walker.h"`) and `engine/include/config/save.h:11`
   (`FREE_MYSTERY_EVENT_BUFFERS` `FALSE`→`TRUE`). `save.h` is the important one — the changed macro
   value currently sits outside any fence, so a sentinel-based revert leaves it behind and produces
   a save-layout mismatch.
3. Correct `CLAUDE.md` §5 to list all four sentinel vocabularies (finding 41): `URANIUM PATHFINDER
   SLICE`, `URANIUM MAP WALKER`, `URANIUM EMBEDDED SAVE`, `RPG2GBA EVENT RANGE EXPANSION` — plus the
   no-`BEGIN` variant. Add the canonical diff command to `CLAUDE.md` §3.
4. Fix `MEMORY.md:101`'s "3 sentinel-fenced custom files".
5. **Verify:** `make -j$(nproc) modern` in `engine/` still builds clean after the fencing edits.

### Stage B — remove the harmful (Q12, Q5, Q11).
6. `git rm scripts/run_slice.py scripts/regen_outputs.py` (Q12). Then grep for both basenames and
   fix every referrer — including `reference/guides/slice_expansion_runbook.md:68` and
   `reference/memory-archive.md:131,530`, whose warnings become obsolete.
7. Rename the external clone to `/home/b/repos/pokeemerald-expansion-PRISTINE-DO-NOT-USE` (Q5).
   Update `MEMORY.md:92,101,304` and close `PROJECT_TODO.md:13-16` with the new name.
   *This is an out-of-repo `mv` — confirm before running.*
8. Mark the bulk-run operator layer spent (Q11): `run_bulk.py`, `prep_bulk_run.py`, `run_stats.py`,
   `conversion_agent/run_report.py`. Add a dated header comment to each. Retire the punt path in
   `reference/guides/human_quickref.md:56`. **Touch nothing in `backends/` or `orchestrator.py`.**

### Stage C — the authority problem (Q1, Q4, Q6, Q13). This is the root cause of the reported confusion.
9. Establish `MEMORY.md` → Current Phase as sole frontier authority (Q1). Amend `CLAUDE.md` §7 to
   say so unambiguously and to say the other docs are topic references.
10. Banner the still-consulted docs (Q4): `BUILD_PLAN.md` (and **fix or delete its stale §6 CH02
    block at `:246-256`** — finding 1, the single most misleading passage in the repo),
    `ROADMAP.md`, `PROJECT_TODO.md` (`:3-5` points at an archived `CH02_TODO.md`).
    Banner text defers frontier status to `MEMORY.md` and carries a date.
11. Archive to `reference/archive/`: `FABLE_PLAN.md`, `PLAYTEST_AUTHORING_IMPROVEMENT.md` (V1),
    `reference/viewer/map_inspector_spec.md` (Q13). Update `reference/archive/README.md`'s
    moved-docs table. Fix `MEMORY.md:98,189-190`, which call V1 authoritative (finding 13).
12. Fix the false-status docs in place, each with a dated inline correction (Q6, findings 17, 18,
    19, 20, 21, 35, 36, 46): `canlose_battle_pipeline_plan.md:6`, `command_pokeemerald_map.md:8-11`
    (the frozen-prompt claim — highest-traffic guide in `reference/`),
    `phase7_integration_plan.md:73-78`, `conversion_walkthrough.md:1-9`,
    `canlose_trainer_battles.md:89-91`, `map_viewer_palette_plan.md:4`.
13. Low-priority text fixes: `ROADMAP.md`/`README.md` vocabulary gap (finding 14) — add one
    sentence naming chapters as the unit of work rather than a global find-and-replace, which
    finding 34 shows is actively harmful; `ROADMAP.md:258-280` clone instruction (15);
    `phase0_summary.md` banner (30); `.claude/skills/pbs-convert/SKILL.md:105` broken path (31);
    `reference/guides/how_to_use_agents.md`'s stale `src/conversion_agent/` path (29).

### Stage D — MEMORY.md prune (Q2).
14. Hoist the live status (CH05 passed / CH06 = Nowtoch City, maps 40-47) into a short skimmable
    headline; fix `:12`'s stale "slices" framing (finding 5).
15. Split the mega-lines — `:43` (27 KB), `:18` (13 KB) — pushing the historical chronicle into
    `reference/memory-archive.md`.
16. Evict the 4 already-resolved Open Questions (`:302,304,306,309`) and the stray bullet at `:315`;
    move oversized Key File Notes (`:101,111,130,134,139`) into `reference/` per the two-sentence
    rule. Delete the superseded Map-Inspector bullets that `:151` says it supersedes (finding 7).
    No CI byte cap this pass.

### Stage E — code (Q3, Q7, Q8). Lowest risk; all latent.
17. Add the `MOVE_NONE` guard to `pbs_converter/trainers.py:216` and `tm_hm.py:88` (Q3). Add a
    synthetic-zero unit test for each — finding 38 notes both existing tests only round-trip real
    env-gated Uranium data, so a regression fails silently in CI today.
18. Add `transpile-events` to `pipeline.py`'s click group delegating to `transpile_driver.cli`, and
    make `phase4 --run` refuse with a message naming the replacement (Q7).
19. Comment `pipeline.py:225` and `scripts/run_human.py:102` to record that `"human"` is
    intentionally script-only (Q8).
20. **Separately scoped, not part of this plan:** consolidate the five-way
    `move_/item_/species_/ability_constant` copy-paste, with all golden tests re-run (Q3).
    Also unclaimed: the 10× `_reference_dir()`, 9× output-path resolution, and the two
    non-validating `chapters.json` loaders (findings 9-10) — latent, no decision taken.

### Not scheduled
Deferred by budget, not by decision (was Next steps #3): H2 (`_load_name_table` vs the flag-registry
sidecar loader), H3 (the `ch01.py`–`ch05.py` playtest copy-paste), H8
(`scripts/count_unique_commands.py` — Q11's answer makes retirement likely but it was not asked),
the UNVERIFIED status lines in `slice_expansion_runbook.md:199-204`, intra-file dead code in
`transpiler.py`/`deterministic.py`, and a full line-level read of `git diff 80cdfce2 HEAD -- engine/`
to confirm findings 40-41 caught **every** unfenced edit — that last one is cheap and closes the
only completeness gap in the engine sweep. Worth doing as part of Stage A step 1.

## Ground covered

- **Root markdown corpus (all 12 files, ~840 KB) — swept.** Findings 1-3, 12-15. No
  live claim anywhere in the root docs that the LLM is still the conversion spine;
  `ROADMAP.md:437,451,474-475` narrates that retirement correctly.
- **`MEMORY.md` — swept** for structure, eviction, line bloat, staleness, Key File Note
  length. Structure is compliant; the problem is byte layout and eviction (4-7). Not
  every one of ~50 Key File Notes and 57 Decisions entries was individually checked.
- **Windows-1252 / encoding-fallback duplication — looked, not there.** Exactly one
  implementation: `pbs_converter/_binary.py:130-144` (`DatReader.s()`).
  `tileset_converter/assembly.py:332` and `map_constants.py:457-458` decode UTF-8 for
  `.pory`/JSON — unrelated concept, not a duplicate.
- **Reference-JSON loaders — mostly clean.** `uranium_id_map.json`, `strip_list.json`,
  `tileset_map.json`, `seam_warps.json` each have one loader
  (`pbs_converter/_id_map.py`, `conversion_agent/orchestrator.py`,
  `tileset_converter/tile_map.py`, `tileset_converter/seam_warps.py`).
  `conversion_agent/triage.py:95-107` reads only the CE-id subset for a different
  purpose — narrower, not a duplicate. `chapters.json` is the exception (finding 9).
- **`to_constant` call sites — mostly clean.** `items.py`, `abilities.py`,
  `encounters.py`, `tileset_converter/{map_constants,npc_gfx}.py`,
  `graphics/sprite_emit.py`, `conversion_agent/{transpiler,deterministic,flag_registry}.py`
  all correctly route through `pbs_converter/_naming.to_constant`. Violations are
  finding 11 only.- **`src/rpg2gba/` reachability — swept at module level.** Findings 23-28. Every
  subpackage was checked for external importers and entry-point reachability; no
  orphaned module exists. Deliberate non-findings, to stop future re-searches:
  `rxdata_deserializer/deserialize.rb` has no Python importers *by design* — it is
  shelled out to from `map_deserializer/driver.py:23` and `pbs_converter/_marshal.py:26`.
  `conversion_agent/queue_evidence.py` looks test-only but its `QueueSchemaViolation` is
  imported by `hand_overrides.py:38`, which the live `transpile_driver` uses.
  `pbs_converter/types_dump.py:8-9` self-documents as deliberately outside
  `pipeline.module_order`. `chapter_atlas/`, `species_converter/`, `trainer_converter/`
  are all live via their own CLIs or `scripts/stage_*.py`.
- **`reference/` (444 files / 101 md) — swept** for orphans, overlap, and contradiction.
  Findings 18-21, 29-33. Overlap clusters checked and found *clean*:
  `essentials_to_emerald_map.md` vs `command_pokeemerald_map.md` (properly disambiguated
  now), `canlose_battle_pipeline_plan.md` vs `canlose_trainer_battles.md` (clean split as to
  *scope* — but both carry false "not built" status claims: findings 17 and 35),
  the six-doc `viewer/` cluster (self-annotates supersession), and
  `flag_registry_policy.md` / `read_through_checklist.md` / `event_conversion_model.md`
  (distinct scopes). `reference/archive/` is not a risk — it is the one place staleness
  is handled correctly.
- **Slice-vs-chapter naming in `reference/` — deliberately not treated as staleness.**
  `CLAUDE.md:278` declares `chapter ≡ slice ≡ one §9 boot gate`, so slice-named docs are
  not stale by name alone. Only `ROADMAP.md`/`README.md` (finding 14) matter, because
  they never mention "chapter" at all.
- **Not swept for the finding-17 pattern** ("status: not built" on shipped features)
  across `reference/guides/` — see Next steps #4.
- **False-"not built" sweep of `reference/` — done, with a negative list.** Findings
  17, 19, 35, 36 (plus non-finding 37). Candidate status lines checked and confirmed
  **genuinely still open**, so nobody re-checks them:
  `reference/guides/essentials_to_emerald_map.md:40` (badges, switches 251-263 —
  deferred, no badge rows in the preseed table);
  `reference/viewer/map_viewer.md:183` (multi-floor composite view is Phase B, not
  built — `map_viewer_server.py` has only `/map/<id>` and `/palettes/<id>` routes;
  note the unrelated "Phase B1" label at `map_viewer_server.py:2` refers to the server
  itself — do not conflate).
  Not verified either way (UNVERIFIED, low suspicion):
  `reference/guides/slice_expansion_runbook.md:199-204` (animated-tile secondary
  callback, NPC movement wiring), `map_viewer.md:183`'s sibling overworld-borders
  claim, `reference/chapters/*.md` per-chapter "not yet converted or boot-walked"
  headers (these look like legitimate progress trackers),
  `reference/guides/nuclear_type_spec.md:95`,
  `reference/findings/text_corpus_scan_2026-07-24.md:125`.
- **`scripts/` (115 files) — swept and fully classified.** Findings 45-48. Every
  non-cache script was checked by basename grep across `src/`, `tests/`, `scripts/`, root
  docs, `reference/`, and `.claude/` — the bare-string form, so command-line invocations
  (`python scripts/foo.py`) were caught, not just imports. Cross-script imports checked
  separately. Two items classified SPENT on *provenance-only* references, worth knowing
  before anyone deletes them: `recon_maps.rb`/`recon_scripts.rb` are cited by
  `rxdata_deserializer/deserialize.rb:45,104` and `map_deserializer/validate.py:24-25`
  as where a constant *originated*, and `pathfinder_collision_preview.py`'s `cell_blocked`
  is cited by `tileset_converter/layout.py:174` as the implementation the real converter
  mirrors. Neither is invoked; both are lineage.
- **`engine/` custom edits — swept within the agreed scope** (fenced edits and
  rpg2gba-specific files only; pristine upstream deliberately untouched). Findings 40-43.
  The definitive instrument is `git diff 80cdfce2 HEAD -- engine/` (77 files) — upstream
  `21c24202` is not a reachable object in this repo, so that vendor commit is the
  baseline. Not exhaustive at line level across all 77 files: the two unfenced edits
  found are confirmed, but "only two exist" is UNVERIFIED.
- **Not yet examined:** intra-file dead code inside `transpiler.py` (203 KB) and
  `deterministic.py` (84 KB) — both confirmed on the live path, but not every function
  within was checked; `tileset_converter/` symbol-by-symbol (package liveness confirmed
  via `pipeline.py:392` `phase5`); `metadata_wiring.py` internals (188 KB);
  `conversion_agent/prompts/few_shot/*.md` for individually-unused examples;
  the `species_converter`/`pbs_converter`/`trainer_converter` parse→reconcile→emit
  skeletons in depth; `tests/` (143 files) as a corpus; `.github/` workflows;
  `reference/chapters/*.md` vs `chapters.json` drift.

---

## Remediation execution log — 2026-09-07, branch `repo-audit-remediation`

All five stages of the Next-steps plan were executed in one pass (lead + five
sub-agents, write-partitioned by file). Everything below is what actually landed,
including the three places the repo disagreed with the plan.

### Stage A — engine safety (Q9, Q10) — **DONE, build verified**

- `engine/RPG2GBA_VENDOR.md`'s "Our custom changes" section rewritten. The
  "three test-only files — revert/gate before a real build" claim is **deleted**, with a
  dated `CORRECTED 2026-09-07` note saying what it claimed and why it was dangerous.
  `git diff 80cdfce2 HEAD -- engine/` is named as **the** canonical check, with the
  reason `21c24202` is unusable (flat `git archive` import, no upstream history).
  The feature-area summary is labelled *orientation, not an inventory* and was
  verified against the real diff, not the plan's list — it added **script-callable
  live graphics swap**, **new-game boot redirect**, and **corpus-sized trainer/flag
  capacity increases** to the areas the audit had named. A stale downstream line
  ("only the two committed hook files differ from raw upstream") was fixed too.
- The two unfenced edits are fenced: `engine/include/global.h:28` as
  `URANIUM MAP WALKER`, `engine/include/config/save.h:11` as
  `RPG2GBA EVENT RANGE EXPANSION` (matching the vocabulary already used in
  `flags.h`/`vars.h`/`event_data.c` for that feature). Both fences say what breaks on
  removal — the `save.h` one records that reverting it alone fails the
  `SaveBlock1FreeSpace` static assert.
- `CLAUDE.md` §5 now lists all four sentinel vocabularies, the `BEGIN`/`END` comment
  form and the no-`BEGIN` variant, and states that **a fence is a locator, not a revert
  script**. `CLAUDE.md` §3 carries the canonical diff command.
- `MEMORY.md`'s "3 sentinel-fenced custom files" corrected — **and so was the Decisions
  Made entry that caused it.** `[2026-06-18] "Fork-baseline divergences MUST be
  reverted/gated before any real build"` is now explicitly marked **REVERSED
  2026-09-07**: it was true when the custom C was two test conveniences and is now
  false and destructive. That entry, not the vendor doc, is the origin of this whole
  finding class; leaving it standing would have regrown the error.
- **Build verified green:** `make -j$(nproc) modern` in `engine/` succeeds
  (EWRAM 86.80%, IWRAM 86.99%, ROM 82.12%; only the pre-existing benign RWX-segment
  linker note). Confirms the comment-only fences are inert.

### Stage B — remove the harmful (Q12, Q11) — **DONE**; Q5 **BLOCKED, needs the operator**

- `scripts/run_slice.py` and `scripts/regen_outputs.py` deleted. Both were read first
  and the audit's characterization confirmed: `run_slice.py` really does spend budget
  (`FROZEN_MODEL = "claude-opus-4-8"`, `--limit` caps *LLM* conversions);
  `regen_outputs.py` really does clear checkpoints and `.pory` before replaying.
- Every live referrer fixed (`slice_expansion_runbook.md:68` rewritten into a removal
  notice naming the replacement). Referrers left alone deliberately: dated past-tense
  entries in `reference/archive/`, `reference/findings/critique_2026-07-01.md`, and
  `reference/memory-archive.md` — rewriting those falsifies history rather than
  removing a dangling instruction.
- One referrer the audit had not found: `backends/__init__.py`'s `NullBackend`
  docstring cited `regen_outputs.py` as its only caller. Rewritten to record the
  deletion and why the class is still worth keeping.
- The four bulk-run operator scripts carry dated `SPENT (2026-09-07)` headers; none
  deleted, `backends/` and `orchestrator.py` untouched as decided.
- `human_quickref.md`'s punt instruction was at **line 93, not 56** (content drifted
  since the audit). Annotated in place: `opus` still spawns the tail tool for that one
  event, but nothing sweeps up punted events afterwards — **treat a punt as final,
  not deferred.**

### Stage C — the authority problem (Q1, Q4, Q6, Q13) — **DONE**

- `CLAUDE.md` §7 rewritten: `MEMORY.md` → Current Phase is the **sole** frontier
  authority, with a table assigning each other document what it owns and what it does
  *not* own (`ROADMAP.md`, `BUILD_PLAN.md`, the atlas, `PROJECT_TODO.md`).
- Banners on `BUILD_PLAN.md`, `ROADMAP.md`, `PROJECT_TODO.md`. `BUILD_PLAN.md`'s §6
  CH02 block — the audit's "single most misleading passage" — kept as a **dated
  historical note rather than deleted**, because the surrounding paragraph carried real
  lineage; the "active chapter is now CH02" claim is gone from both the body and the
  heading. `PROJECT_TODO.md`'s dead `CH02_TODO.md` pointer fixed.
- Archived to `reference/archive/`: `FABLE_PLAN.md`,
  `PLAYTEST_AUTHORING_IMPROVEMENT.md` (V1), `reference/viewer/map_inspector_spec.md`,
  with `reference/archive/README.md` updated and every inbound reference across the
  repo repointed. `MEMORY.md` no longer calls V1 authoritative — the note now leads
  with V2 and says explicitly that the "authoritative" claim was the error.
- All six false-status docs corrected in place with dated notes, each **verified against
  the code before writing** — `canlose_battle_pipeline_plan.md` (both gaps built:
  `transpiler.py:2433`, `scripts/stage_trainers.py`), `command_pokeemerald_map.md` (the
  frozen-prompt claim removed), `phase7_integration_plan.md`, `conversion_walkthrough.md`,
  `canlose_trainer_battles.md`, `map_viewer_palette_plan.md`. None were left unverified.
- Low-priority sweep done: chapter vocabulary added to `ROADMAP.md`/`README.md` (one
  sentence each, no blanket rename), the `ROADMAP.md` clone instruction corrected in
  **two** places — the §1.1 body *and* the toolchain table at `:142`, which the plan
  had missed — `.claude/skills/pbs-convert/SKILL.md` path fixed,
  `how_to_use_agents.md` path fixed. `phase0_summary.md` lives at
  `reference/recon/`, not `reference/guides/` as the plan said; bannered there.

### Stage D — MEMORY.md prune (Q2) — **DONE**

- **260 KB → 143 KB.** The Current Phase section is now a headline: a frontier table
  (CH01-CH05 gate dates, CH06 = Nowtoch City maps 40-47 as next, branch policy), a
  pointer to `POST_CH05_REVIEW.md`, and three standing facts. ~100 KB of dated
  chronicle moved verbatim to `reference/memory-archive.md` → "Current Phase chronicle
  (2026-05 → 2026-09-06)". The 27 KB and 13 KB mega-lines are gone from MEMORY.md.
- Open Questions: the CH05 parking banner is generalized to any open chapter (none is
  open); four entries evicted with a breadcrumb line — the `engine/` cutover (done;
  residue is `PROJECT_TODO.md` #1), the Nuclear 1/8-HP effect and GBA charmap handling
  (both duplicates of `PROJECT_TODO.md` #2/#3), and the superseded UNHANDLED
  script-call question. The stray bullet below the section's closing `---` (Maps
  49/172 arrival facing) was a discovery, not a question, and moved to the archive.
- Five oversized Key File Notes replaced by one-line pointers: the bulk-run harness,
  the hand-conversion pass, both Map Inspector notes, and the palette-packing
  investigation. No CI byte cap, as decided.

### Stage E — code (Q3, Q7, Q8) — **DONE, tests green**

- `MOVE_NONE` guard added to `trainers.py:216` and `tm_hm.py:88`, copied verbatim from
  the three copies that already had it (`pokemon.py:452`, `moves.py:205`,
  `tmpbs.py:53`) rather than inventing a convention. Two synthetic-zero unit tests
  added that construct the `_Resolver` directly with no dependency on
  `RPG2GBA_URANIUM_SRC` — and the fail-without-fix behaviour was **actually checked**
  by reverting the guards (both failed with `ValueError: move id 0 absent from
  move_internal_names.json`), not assumed.
- `transpile-events` added to `pipeline.py`'s click group via a lazy `click.Group`
  subclass, so `rpg2gba --help` lists it without paying the transpiler's import chain.
  It delegates to `transpile_driver`'s real command objects, so `--maps`/`--dry-run`
  cannot drift from the driver's own definitions.
- `phase4 --run` now refuses with a `ClickException` (exit 1) naming
  `rpg2gba transpile-events run --maps <spec>`, raised before any orchestrator import
  so it cannot be mistaken for a conversion failure. Non-`--run` `phase4` is unchanged.
- `HumanBackend` documented at both ends as intentionally script-only; no
  `click.Choice` widened, nothing deleted.
- `pytest`: **2984 passed, 16 skipped, 2 failed** — the two failures
  (`test_ground_item_differential_vs_frozen_opus`, `test_pokemart_differential_vs_frozen_opus`
  in `tests/test_deterministic.py`) are **pre-existing**, confirmed identical with the
  branch stashed; they depend on a gitignored on-disk oracle under `output/`.

## Follow-ups opened by the remediation

1. **Q5 is blocked on you: the clone rename needs a user-run `mv`.** Tracked as
   `PROJECT_TODO.md` #1 with the exact command. The agent attempt was
   classifier-blocked — the **second** time that has happened, so this will not
   resolve itself on a future agent pass.
   **And the audit's premise was wrong:** `/home/b/repos/pokeemerald-expansion` is
   *not* pristine. Checked 2026-09-07: upstream `21c24202` with **6 modified tracked
   files and ~125 untracked generated-artifact directories** from a pre-cutover
   pipeline run sitting on top (uranium tilesets, cries, species graphics, map
   layouts). So the decided name `-PRISTINE-DO-NOT-USE` would itself be a false claim
   of the kind this audit exists to remove; the command in `PROJECT_TODO.md` uses
   **`-STALE-DO-NOT-USE`** instead. Say the word if you want the original name anyway.
   `CLAUDE.md` §3's description of that clone was corrected to match.
2. **CLOSED same day — the engine sweep found six more unfenced edits, and all eight are now fenced.**
   Stage A read all 77 files of the diff hunk-by-hunk (closing the completeness gap
   the plan listed under "Not scheduled") and found six bare custom `#include` lines
   beyond the two it was scoped to fix — `overworld.c:2`, `field_control_avatar.c:2`,
   `event_object_movement.c:2`, `palette.c:2`, `sound.c:2`, `new_game.c:2-4` — plus
   two soft cases with an opening comment but no `END` bracket
   (`flags.h`'s `TRAINER_REGISTERED_FLAGS_START`, `opponents.h`'s
   `TRAINERS_COUNT_EMERALD`). These are lower-risk than the two fixed (a missed
   include leaves an unused header, not a behaviour or save-layout change), but all
   eight were fenced in a follow-up pass with the build re-verified green — the memory
   table came back byte-identical (EWRAM 86.80% / IWRAM 86.99% / ROM 82.12%), which is
   the proof the comment-only fences are inert. Sentinel choices worth knowing:
   `palette.c` and `sound.c` pull `config/rpg2gba.h` only for the **pacing knobs**
   (`RPG2GBA_FADE_DELTA_Y`, `RPG2GBA_BGM_TEMPO_SCALE`), not the event-range expansion,
   so they are fenced `URANIUM PATHFINDER SLICE` to match the existing
   `RPG2GBA_FAST_TEXT_DEFAULT` fence in `new_game.c`; `new_game.c`'s three includes got
   three separate fences rather than one block, so a
   `grep "BEGIN URANIUM EMBEDDED SAVE"` sweep still finds every pull of that header.
   **Everything else in the 77-file diff is properly fenced** — the "only two exist"
   UNVERIFIED caveat is resolved, and the answer was "no, ten".
3. **CLOSED 2026-09-07 — both oversized Key File Notes are now one-line pointers.**
   The ownership judgement turned out to be easy: each note already *named* its owner
   doc in its own text. `quantize.py`'s note was near-total duplication of
   `reference/guides/graphics_conversion_notes.md` §10, which covers the two-phase
   packer, the three by-eye bug fixes and the durable lessons in more detail — so the
   note became a pointer and nothing was lost. The map-viewer note was mostly covered
   by `reference/viewer/map_viewer.md`; the three facts that were **not** (the
   2026-07-11 refocus superseding the Map-Inspector framing, the 2026-08-28 deletion
   of the static HTML build and `palette_page.py`, and the `build_map_data` →
   `compare_collision` `terrain`-argument gotcha) were moved into that guide under a
   dated Provenance bullet first. MEMORY.md is 2 lines and ~4.6 KB lighter.
   **Found while doing it:** `graphics_conversion_notes.md` §10 ended with a
   "NEXT (pending user sign-off): wire the GBA 4bpp binary emitter" — a frontier
   claim in a topic reference, and a false one: that emitter is
   `tileset_converter/graphics/emit.py` and has shipped every ROM through CH05. Struck
   through with a dated correction per Q6.
4. **CLOSED 2026-09-07 — Q3's consolidation is done and the "Not scheduled" list is
   fully worked.** See the second execution log below. Nothing from the original plan
   or its deferrals remains open; the only outstanding item in this document is #1,
   which is the operator's.

**Deliberately not done:** stale references to the three archived documents inside
`reference/memory-archive.md` were left pointing at the old paths. It is a historical
record; per Q6's "fix the text where the instruction is live", a dated archive entry
is not a live instruction.

---

## Second remediation pass — 2026-09-07, same branch: the deferrals

The first pass executed Stages A–E and left a "Not scheduled" list plus two of its
own follow-ups. This pass worked that list to zero. Every item is either fixed,
verified-still-true, or explicitly declined with a reason.

### Q3 — the five-way `*_constant` consolidation. **DONE**

The divergence was closed in the first pass by adding the missing zero-guards; the
duplication is closed now. New module `src/rpg2gba/pbs_converter/_resolve.py` holds
five mixins — `Move`, `Species`, `Item`, `Ability`, `Type` — each the single
definition of its resolver method, plus the `TYPE_NAME_OVERRIDES` table that
`pokemon.py` and `moves.py` had been keeping "in sync" by hand (their own comment
said so). The five `_Resolver` dataclasses now inherit what they need and declare
only their fields.

Two design points worth recording, because both are load-bearing:

- **The mixins are plain classes, not dataclasses, and declare no runtime
  annotations.** A dataclass base with annotated fields would inject fields into
  every subclass in base-first order and silently reorder their constructors. The
  fields each mixin reads are declared under `if TYPE_CHECKING:`, which never
  executes, so nothing reaches `__annotations__`. Declaring the actual fields stays
  the subclass's job — that is what keeps each converter's `_build_resolver` honest
  about which reference tables it really loads.
- **`species_constant` deliberately has no zero-guard**, unlike move/item/ability.
  No PBS table uses species 0 as an empty slot, so a 0 there is a data defect and
  must fail loud (§4.5). The asymmetry is now stated in the docstring instead of
  being an accident of which copy you happened to read. Consolidating also settled a
  cosmetic divergence: `pokemon.py` raised `no internal name for species id N` where
  the other two named the sidecar file. The sidecar-naming message won.

`tests/test_pbs_pokemon.py` was reaching `to_constant` through `pokemon`'s module
namespace — an incidental re-export that the import cleanup removed. Fixed to import
from `_naming` directly, which is where it lives.

### H2 — `_load_name_table` vs the flag-registry sidecar loader. **DONE, and it was hiding a bug**

Extracted `load_label_tables` in `flag_registry.py`; both `seed_labels` and
`chapter_manifest/generator.py` call it. The interesting part is what the
deduplication exposed rather than the deduplication itself: `_load_name_table`
returned `{}` for a missing file, and the generator was reading
`Path("reference/uranium_switches.json")` **relative to the CWD**. Both files are
tracked in git, so the only thing that empty table could ever mean was "you are not
in the repo root" — and it would have produced a manifest with every switch and
variable silently unnamed. The moment the shared loader started failing loud,
`test_chapter_manifest_cli.py` went red, because Click's `isolated_filesystem`
changes directory. Fixed properly: the sidecar paths are anchored to the repo via
`__file__`, matching what `pbs_converter` already does. The test passes again for the
right reason. Note the CWD-relative `reference/` convention is repo-wide
(`pipeline.py`, `transpile_driver.py`, `stage_slice_scripts.py`); only the generator
was changed, since only it had a fail-loud reason to.

### H3 — the `ch01.py`–`ch05.py` playtest copy-paste. **VERIFIED, action declined**

No diverged copies. A 2026-08-20 consolidation had already moved the cross-file
helpers into `playtest/assertions.py`; the chapters hold aliases. ~150 lines remain
duplicated across `ch02`/`ch04`/`ch05` and are behaviourally identical. Declined —
extracting them means reopening four chapters that have passed their §9 boot gates
to fix nothing. Full reasoning in the H3 entry above.

### H8 — `scripts/count_unique_commands.py`. **KEPT; its neighbour retired**

Script kept and its header now says why; `reference/findings/agent_coverage_diff.md`
bannered HISTORICAL. Full reasoning in the H8 entry above.

### The UNVERIFIED status lines. **ALL SEVEN CHECKED — five true, two stale**

`slice_expansion_runbook.md`'s "Limits every new map inherits" list was re-verified
against the code and now carries a dated header saying so, so nobody re-checks it
blind. Per-claim:

| Claim | Verdict | Evidence |
|---|---|---|
| Animated tiles must land in PRIMARY; no secondary-callback variant | **still true** | `graphics/emit.py` fails loud when an animated effect does not fit PRIMARY; `build_slice_tilesets.py` gives the callback to PRIMARY only |
| Page dispatch selects the script only; boot-page gfx/visibility/movement static | **still true** | `npc_gfx.select_boot_page` fixes those once at boot; the dispatcher routes only the interaction script |
| Warp cells are all `MB_NON_ANIMATED_DOOR` | **still true** | one door behavior resolved and applied to every warp column; sideways stairs use `stairs.py`, a different idiom |
| **NPC movement wiring is under investigation** | **STALE — built** | `metadata_wiring.py` emits `movement_type`, with custom-route bytecode, a trainer-movement allow-list and berry-tree growth types |
| Viewer has no overworld N/S/E/W borders | **still true** | no `connections.dat` / border rendering anywhere in the viewer sources |
| `nuclear_type_spec.md` — Nuclear type not built | **still true** | no `TYPE_NUCLEAR` in `engine/include/constants/types.h` or `types_info.h`; the whole doc is an unstarted Phase 6 spec |
| **`text_corpus_scan_2026-07-24.md` — DrawTextEx tags not implemented** | **STALE — built** | `deterministic.py` strips the full tag family and maps `<br>`; only `<fs=n>` was handled when the scan was written |

Both stale claims got dated in-place corrections per Q6. One structural note worth
keeping: the runbook cites `SLICE1_TODO` #8/#10/#12, and that tracker now exists only
at `reference/archive/SLICE1_TODO.md` — where #12 is *closed*. A live document citing
item numbers in a retired tracker is the same failure shape as the rest of this audit,
so the runbook now says the citations are provenance, not a backlog.

### Intra-file dead code in `transpiler.py` / `deterministic.py`. **CLEAN — nothing found**

Every module-level function, class, method and command-code constant in both files
traces to a live caller: direct calls, `deterministic.py`'s `_CLASSIFIERS` dispatch
list, `transpiler.py`'s code-keyed `emit_node` chain, the `_emit_if` idiom-probe
chain, or `parse_tree`'s parse-time code checks. Indirect dispatch was checked
explicitly for every classifier and every `_emit_*_idiom` method — that was the
obvious false-positive trap, and nothing fell into it. **Zero confirmed-dead lines.**

The only findings are two inert names in `transpiler.py`: a `logger` that is assigned
and never called, and `INPUT_NUMBER = 103`, defined and never compared against (code
103 falls through to the `# UNHANDLED` queue, which is the correct fail-loud
behaviour). Both left alone: neither is a defect, and the live conversion spine is not
worth touching for a two-line cosmetic edit. Recorded here so the next reader does not
re-derive it.

### Verification

`.venv/bin/python -m pytest -q` → **2 failed, 2984 passed, 16 skipped** — identical to
the baseline recorded in the first pass. The two reds are the pre-existing
`test_ground_item_differential_vs_frozen_opus` /
`test_pokemart_differential_vs_frozen_opus` in `test_deterministic.py`, which depend on
a gitignored frozen-Opus oracle under `output/` that predates Map036. `ruff` clean on
every file touched (one pre-existing E501 in `chapter_manifest/generator.py:124`, in a
comment unrelated to this work, left as found).

No engine C was touched in this pass, so no rebuild was owed.
