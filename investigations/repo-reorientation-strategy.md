# Investigation: Reorienting the repo — incremental purge vs. blank canvas

**Status:** **closed** — Q1-Q7 answered 2026-09-08, decisions D1-D7 recorded, execution order in Next steps. Q8 answered and landed 2026-09-08. Sibling `scripts-dir-liveness.md` stays open by decision (D7).
**Started:** 2026-09-08   **Last updated:** 2026-09-08 (decisions walked through with the operator; two of my own conclusions corrected by him — see D1 and D2)
**Question:** Should the repo be cleaned incrementally, or archived wholesale and rebuilt from the live parts — and what must CLAUDE.md say once the project's stated goal is "convert *any* RPG Maker XP Pokémon fan game", not "convert Uranium"?
**Expected artifact:** **decision brief** — the three-option comparison in "The decision" below, plus the open questions that follow from it

**Operator's framing (2026-09-08, in chat), recorded verbatim in substance:**
- The pipeline's purpose is to convert RPG Maker XP based Pokémon fan games into `.gba`.
- **Uranium is the test game, not the product.** The goal is that a *new* game needs only
  minimal changes to convert successfully.
- **Corollary the operator stated as a rule:** *anything that can be done
  deterministically should be built as code.* This is the acceptance test for what
  survives the cleanup.
- The chapter-based flow is the current way of working.
- CLAUDE.md has been renamed `CLAUDE.md.bak` pending a rewrite.

**Parents / siblings.** This doc sits above four existing investigations:
- `investigations/repo-audit-dead-code-stale-docs.md` — **CLOSED.** 48 findings, Q1-Q13
  answered and remediated 2026-09-07. Scoped to documentation and safety; **file count was
  explicitly out of scope**, which is why the operator read the repo afterwards and still
  called it uncleaned.
- `investigations/claude-md-accuracy-and-compliance.md` — **blocked-on-answers** (Q1, Q2,
  Q4, Q5). Section-by-section audit of `CLAUDE.md.bak`.
- `investigations/scripts-dir-liveness.md` — **blocked-on-answers.** 90 files, 3 liveness
  markers.
- `investigations/conversion-agent-package-boundary.md` — **blocked-on-answers.** Live
  spine under a retired regime's name.

**The rewrite of CLAUDE.md subsumes part of the second doc**, and the purge decision
subsumes part of the third. See Q-numbers below for how they fold in.

## Summary

**Four fan-out audits are in. The headline is that neither of the two proposed approaches is
the right one, and the evidence for that is unusually concrete.**

The repo's problem was diagnosed twice before as "dead code and stale docs," remediated in
three passes on 2026-09-07, and the operator still read the result as uncleaned. This
investigation finds he was right, and finds *why*: every prior audit asked **"is this
dead?"** — a question that took 48 findings to answer and still left the repo feeling wrong.
The operator's stated goal implies a different and sharper question, **"is this general, or
is it Uranium?"**, and that question turns out to be decidable from code in a way the first
one never was.

**The generalization audit came back worse than expected.** There is no game seam anywhere:
no `GameProfile`, no `--game`, no `--reference-dir`. The pipeline's only source-path knob is
an env var named after the test game (`RPG2GBA_URANIUM_SRC`, `pipeline.py:91`), `reference/`
is located by a module-level constant with no override (`:186`), and the literal
`"uranium-build"` is hand-copied across 15+ files. Most decisively, **the test game's name is
compiled into the deliverable** — `REMATCH_URANIUM_`, `sBackAnims_Uranium`,
`GUARD_URANIUM_SPECIES_CONSTANTS_H`, `graphics/pokemon/uranium`, `gUraniumMap33` are emitted
C symbols, not paths (12). "Uranium is just the test case" is not currently true of the
output format.

The good news underneath that: **the layer split is already cleaner than the literals
suggest** (15). `rxdata_deserializer`, `map_deserializer`'s core walk, and
`pbs_converter/_binary.py` are Essentials-generic *by construction* — they implement the
shared Pokémon Essentials format, not Uranium's. The game-specificity is bolted on above a
sound substrate, mostly as paths, prefixes, and curated JSON.

**Against the blank canvas, the evidence is specific and it is about names.** Twice now,
measured independently: `scripts/assemble_pathfinder.py` is named for an era retired and
archived in August, and is the assembly step of *every* chapter build — edited mid-CH05 to
fix a live defect (18). `ROM_TEST_DEV.md` reads as a raw untitled transcript and has 33
referrers (33). A restore pass that judges a blank canvas by reading it deletes the build
and orphans a third of the corpus's cross-references. And the live set is not small — CH05
touched **166 distinct files** (19).

**Against incremental purge, the evidence is that it has already been tried and measured.**
The 2026-06-18 pivot consolidated planning to five root docs and said so in writing; eighty
days later there are ten (5). And finding **29** is the clincher: the audit's own
#1-ranked, "destroys working engine features" claim **still sits live at
`BUILD_PLAN.md:314-317`**, three weeks after being corrected in two other files and
explicitly reversed in `MEMORY.md:163` — in a document the same remediation had already
banner-edited, pointing the reader at the very section that refutes it. Hand-enumerated
fixes miss things. That is now measured twice.

**The recommendation is a third option: sort by the goal, not by liveness.** Build the game
seam that doesn't exist, and let *it* do the purging — anything that fits neither "pipeline"
nor "game pack" is dead by construction. This is not extra work bolted onto a cleanup: the
single-resolver refactor it needs (~24 call sites, mirroring the healthy pattern already in
`tests/conftest.py:22`) is the **prerequisite for both other options anyway**, since nothing
can move safely until `reference/` stops being located three different ways. And it can be
made byte-identical in output by defaulting the symbol prefix to `Uranium`, which means it
is gateable against the existing CH05 ROM — a safety property neither other option has.

**On CLAUDE.md specifically: do not rewrite it from scratch.** The section-by-section verdict
is 1 DROP, 6 KEEP-BUT-FIX, 6 KEEP-AS-IS (31). Its behavior contract — §2's boundaries, §9's
gates, §10's ask-policy — exists in binding form nowhere else in the corpus, and a blank-page
rewrite is most likely to lose exactly those. What it needs is the stale *maps* deleted and
one real gap filled: the CLI it describes advertises the retired phase model and omits the
entire live chapter loop (17).

## Findings

1. **The repo is 96% vendored engine by file count.** `git ls-files | sed 's|/.*||' | sort
   | uniq -c`: `engine/` 29,981 · `reference/` 178 · `src/` 166 · `tests/` 159 ·
   `scripts/` 95 · `.claude/` 5 · 10 root `.md` files · config. On disk: `engine/` 581 MB,
   `output/` 6.5 GB, `tests/` 13 MB, `reference/` 8.9 MB, `src/` 6.8 MB, `scripts/`
   1.4 MB. **The "blank canvas" therefore has a permanent 30k-file fixture in the middle of
   it** — `engine/` cannot be archived, because the prior audit's finding 42 established it
   carries 2,647 lines of custom edits across 77 files that are the project's actual output
   surface.

2. **An archive convention already exists, is documented, and has been exercised three
   times.** `reference/archive/` (40 entries) with `reference/archive/README.md` as its
   ledger. The README's operating rule, `reference/archive/README.md:5-10`: docs are "kept
   verbatim for history; their **still-authoritative content was absorbed first** into the
   live docs before archiving… **Do not treat anything here as current.** If it matters,
   it's in a live doc; if it's only here, it's history."

3. **The archive ledger records provenance per document, not just the move.** Three dated
   tables map each archived doc to *what it was* and *where its live content went* — e.g.
   `SLICE1_TODO.md` → `PROJECT_TODO.md` #15-26/#27, a renamed `CH02_TODO.md`, the
   `ROM_TEST_DEV.md` harness section, and `reference/guides/engine_gotchas.md`
   (`reference/archive/README.md:31`). This is the artifact that makes archiving safe, and
   it is hand-written per file. **It is the step that a wholesale move cannot afford**, and
   the step whose absence turns an archive into a deletion.

4. **Archiving without the absorb step has already produced a documented failure in this
   repo.** `map_inspector_spec.md` was archived carrying two false supersession claims —
   that it superseded `compare_collision.py` and `tree_debug.py`, which the live viewer
   still uses (`reference/archive/README.md:53`). The husk kept asserting things about live
   code after being moved.

5. **The five-doc consolidation of 2026-06-18 did not hold.** The archive README states
   flatly, `reference/archive/README.md:6-7`: "Live planning now lives in just five root
   docs: `README.md`, `ROADMAP.md`, `CLAUDE.md`, `MEMORY.md`, `BUILD_PLAN.md`." Root doc
   creation dates since, from `git log --diff-filter=A`:
   | Doc | Added | Commit |
   |---|---|---|
   | `MEMORY.md`, `ROADMAP.md` | 2026-05-09 | `abe97803` |
   | `BUILD_PLAN.md` | 2026-06-18 | `3118f0f5` (the consolidation itself) |
   | `PROJECT_TODO.md` | 2026-07-13 | `df41aff6` |
   | `ROM_TEST_DEV.md` | 2026-07-21 | `2b045012` |
   | `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` | 2026-08-28 | `6bf21a91` |
   | `CH05_DECISIONS.md` | 2026-09-01 | `43ebfca8` |
   | `POST_CH05_REVIEW.md` | 2026-09-06 | `14b40cdb` |
   Five root docs became ten in eighty days — **one new root document every ~16 days**,
   sustained, through a period that included a formal consolidation and a 48-finding audit.
   Whatever cleanup shape is chosen, this is the rate it decays at unless the *rule* for
   creating a root document changes.

6. **The three sibling investigations are all blocked on the operator, and their pending
   questions are inputs to this decision, not independent of it.** No `**Answer:**` line
   has been filled in since 2026-09-07 (`grep -n '^\*\*Answer:\*\*'` across the three).
   Specifically: `claude-md-accuracy-and-compliance.md` Q1 (hand-maintained directory tree:
   update / delete / generate) and Q4 (§1 leads with the retired LLM regime) are
   **decisions the CLAUDE.md rewrite makes automatically**; its Q5 (scope §5's typing rules
   to `src/` vs. annotate ~675 functions) is not.

7. **The repo runs two organizing models at once, and they live in separate documents that
   barely reference each other.** Counts of `Phase [0-9]` vs. `CH0[0-9]|chapter`:
   | Doc | "Phase N" hits | chapter hits |
   |---|---|---|
   | `ROADMAP.md` | 50 | 1 |
   | `PROJECT_TODO.md` | 6 | 350 |
   | `BUILD_PLAN.md` | 2 | 41 |
   | `CLAUDE.md.bak` | 12 | 8 |
   | `README.md` | 1 | 1 |
   `ROADMAP.md` is almost purely the **phase** model; `PROJECT_TODO.md` and `BUILD_PLAN.md`
   are almost purely the **chapter** model. `CLAUDE.md.bak` is the only file that straddles
   both, which is precisely why it reads as incoherent — it is the seam between two process
   eras. This is the mechanical form of the operator's "our process has changed a few times
   and we haven't purged the old ways."
   *(Related: the sibling doc records a live instance of the damage — `CLAUDE.md.bak` §6
   tells the reader the flag registry is "dormant during the current Phase 2" when Phase 4
   is active per its own designated authority; `investigations/claude-md-accuracy-and-compliance.md`
   finding 8. A stale phase pointer suppressed a whole section's rules.)*

8. **The process layer is Uranium-named too, not just the code.** Five project skills are
   tracked in `.claude/skills/`: `boot-walk-harness`, `debug`, `pbs-convert`,
   `phase-walkthrough`, `pokemon-uranium-wiki`. They split along the same seam as finding 7
   — `pbs-convert` and `phase-walkthrough` are phase-model, `boot-walk-harness` and `debug`
   are chapter-model — and one of them, `pokemon-uranium-wiki`, hardcodes the *test game*
   into the agent's process layer as a validation oracle. All five are currently maintained
   (last touched `3e100ffb` 2026-09-01 and `9bd3621e` 2026-09-07), so this is live
   configuration, not residue. **Generalizing the pipeline means generalizing this
   directory too**, and no prior investigation has looked at it.

9. **The retired phase vocabulary is baked into the CLI, not just the docs.**
   `src/rpg2gba/pipeline.py` registers subcommands named `phase2` (`:152`), `phase3`
   (`:191`), `phase4` (`:294`) and `phase5` (`:438`) alongside semantically-named ones
   (`convert-map` `:351`, `convert-common-events` `:385`, and the `transpile-events` group
   `:76`). `phase4 --run` raises "retired (2026-06-18)" (`:306`) while the rest of `phase4`
   stays live. **This upgrades finding 7 from documentation debt to a migration:** the
   phase model is the public command surface, it is what `README.md:41-44` tells a user to
   type, and renaming it touches code, tests, docs, and every runbook. Any plan that
   promises "purge the old process vocabulary" must price this in or explicitly exclude it.

10. **`README.md` already states the operator's current framing, and its recipe is stale
    anyway — the two rot independently.** `README.md:3-5` says the pipeline "is the
    long-term deliverable. The Uranium ROM is the proof of concept," and `:9` defines the
    chapter model correctly. Then `:11` heads the build recipe "**(pathfinder slice:
    Map049 ↔ Map048 ↔ Map32)**" — pathfinder/slice-1 was retired and archived 2026-08-04
    (`reference/archive/README.md:28`). So the doc closest to the operator's stated goal is
    also carrying a retired vocabulary in its most-executed section. **Framing and
    procedure are separate rot surfaces**; fixing a doc's mission statement does not fix
    its commands, and this is the same finding-34 mechanism the parent audit named.

### The generalization audit (findings 11-16) — H1 confirmed

11. **There is no game seam. Anywhere.** A search for `GameProfile`, `GameConfig`,
    `GameSpec`, a `--game` flag, or a `--reference-dir` override returned zero hits.
    `src/rpg2gba/pipeline.py:186` holds `REFERENCE_DIR = Path("reference")` as a
    module-level constant with no CLI override, and `:91` reads the pipeline's *only*
    source-path knob from an env var literally named after the test game:
    `RPG2GBA_URANIUM_SRC`. Many individual functions do accept `reference_dir: Path`
    (e.g. `species_converter/stage.py:259`, `pbs_converter/pokemon.py:402-404`) — the
    hygiene is right one level down — but `pipeline.py` wires every one of them to the
    single hardcoded constant. **The plumbing for a second game is one file away from
    existing and does not exist.**

12. **The test game's name is compiled into the deliverable.** Not paths — the emitted
    pokeemerald-expansion C symbols:
    `trainer_converter/rematch.py:127` `REMATCH_PREFIX = "REMATCH_URANIUM_"` · `:137`
    `MEMBERS_MACRO = "URANIUM_REMATCH_MEMBERS"` · `trainer_converter/stage.py:250,275`
    `f"Uranium{_pascal_ident(...)}"` · `:194,209` `sAnim_UraniumBackIdle`,
    `sBackAnims_Uranium` · `:150` `ENGINE_GFX_ROOT = Path("graphics/trainers/uranium")` ·
    `species_converter/common.py:176` `graphics/pokemon/uranium` ·
    `species_converter/stage.py:428,434` `GUARD_URANIUM_SPECIES_CONSTANTS_H`,
    `#define URANIUM_SPECIES_LAST` · `pbs_converter/tmpbs.py:70` `f"sUraniumTMPBS_{internal}"`
    · `pbs_converter/abilities.py:167` `GUARD_URANIUM_CONSTANTS_ABILITIES_H` ·
    `tileset_converter/wild_encounters.py:93` `gUraniumMap33`.
    This is the sharpest available refutation of "Uranium is just the test case": **the
    test case is currently a naming convention in the output format.**

13. **The build directory literal `"uranium-build"` is hand-copied across ≥15 files with no
    override**, e.g. `pipeline.py:102,444`, `routing/__main__.py:66`,
    `traversal/triggers.py:147`, `traversal/world.py:58-59`, `playtest/cells.py:87`,
    `playtest/assertions.py:262`, `playtest/text_source.py:95`, `chapter_atlas/__main__.py:22`,
    `text_validator/__init__.py:21`, `text_validator/__main__.py:34`. Same duplication shape
    as the parent audit's findings 9-11 (`_reference_dir()` ×10, output-path resolution ×9)
    — **a third instance of the same defect, which the prior audits catalogued as latent
    and this goal reclassifies as blocking.**

14. **Two game-mechanic decisions are hardcoded as regexes inside the transpiler**, not as
    data: `conversion_agent/transpiler.py:564` collapses a randomizer-mode check to its
    non-randomizer branch unconditionally, and `:571,574` statically forces a status-check
    false with a comment deferring the feature to a specific named late chapter. Also
    `pbs_converter/pokemon.py:395-396`, where the `_EVONAMES` tuple carries this game's
    *custom* evolution-method field names next to the stock Essentials ones. These are the
    dangerous kind: invisible, correct-for-this-game, and silently wrong for the next one.

15. **The layer split is cleaner than the literals suggest, and that is the good news.**
    Genuinely game-agnostic today: `rxdata_deserializer/deserialize.rb` (dumps whatever
    `.rxdata` it is pointed at), `map_deserializer/driver.py`'s core RMXP walk,
    `pbs_converter/_binary.py` + `_c_emit.py` (these implement the *shared Pokémon
    Essentials* PBS compiler format per `reference/scripts_dump/175__Compiler.rb`, so they
    are Essentials-generic by construction), and `traversal`'s ledge/passability algorithms.
    **The Essentials format is the real substrate**, and the pipeline already parses it
    generically — the game-specificity is bolted on above that layer, mostly as paths,
    prefixes, and curated JSON. Contrast `playtest/chapters/ch01.py`-`ch05.py` (~thousands
    of lines) and `reference/chapters.json` / `manifests/` / `routes/`, which are
    irreducibly per-game content: the code that consumes them is generic, the curation
    effort is not transferable, and no amount of refactoring changes that.

16. **The test suite would not survive a second game, and would fail rather than skip.**
    `tests/conftest.py:25-34` skips cleanly when `RPG2GBA_URANIUM_SRC` is unset — but that
    is an absence-of-data skip, not a different-game accommodation. **78 of 141 test files
    reference this game by name**; `tests/fixtures/maps_golden/` ships four real
    game-derived map JSONs asserted byte-for-byte. A genuinely game-agnostic layer does
    exist and is explicitly labelled as such (`tests/test_binary.py:2-3`, "env-independent
    — no Uranium data required") — but it is the minority.

### The live-spine trace (findings 17-21)

17. **The CLI advertises the retired model and hides the live one.** The installed console
    script (`pyproject.toml:25` → `rpg2gba.pipeline:main`) registers only
    `phase2/phase3/phase4/phase5/convert-map/convert-common-events/transpile-events`
    (`src/rpg2gba/pipeline.py:76-85,145-467`). **The entire chapter loop — SELECT, READ,
    ROUTE, BOOT — is not wired into it**, and runs as bare module calls:
    `python -m rpg2gba.chapter_atlas`, `python -m rpg2gba.chapter_manifest`,
    `python -m rpg2gba.routing`, `python -m rpg2gba.playtest`. This is the single best
    explanation of the operator's complaint. **An agent that reads `pipeline.py` to learn
    what this project does sees only the retired phase model** and has to be *told*, out of
    band, that four other entry points exist. Finding 9 said the phase vocabulary is in the
    CLI; this says the chapter vocabulary is *absent* from it. Those are the same defect
    seen from both sides.

18. **The build step every chapter depends on is named for a retired era, and it is the
    riskiest object in the repo.** `scripts/assemble_pathfinder.py` — "pathfinder" was
    slice-1, retired and archived 2026-08-04. It reads as a spent one-off next to the ~6
    other pathfinder-era scripts finding 47 marks spent. It is in fact the assembly stage
    of every chapter build (`README.md:84-96`, `BUILD_PLAN.md:121`), it was **edited
    mid-CH05 to fix a live defect** (commit `08baf280`), and 20+ files reference it
    (`text_validator/`, `fork_index.py`, `flag_registry.py`, `tileset_converter/graphics/*`,
    `species_converter/`, `trainer_converter/`, `playtest/offsets.py`). The sibling doc
    already caught this shape twice (`scripts/calibrate_map002.sh`, `scripts/assembly_smoke.py`
    — `investigations/scripts-dir-liveness.md:57-68,86-103`), but those were landmines to
    disarm. **This one is the build.** Any blank-canvas restore driven by reading names
    rather than tracing imports deletes it.

19. **The live spine is large and recently exercised.** The CH05 development range
    (`git log --name-only c27f9dc5^..af0d8e25`) touched **166 distinct files**. Heaviest
    clusters: `playtest/` (chapter.py ×9, chapters/ch05.py ×9, emulator.py ×8, runner.py ×6,
    archetypes/warp.py ×6) and `chapter_manifest/` (checker.py ×6, generator.py ×5).
    Recently-edited is the strongest liveness evidence available, and it says the chapter
    machinery — not the phase machinery — is where the work happens.

20. **Chapter-flow conventions are enforced forward, not retroactively, and the repo already
    says so.** `reference/routes/` contains route files for CH05 only; CH01-CH04 have none,
    matching `BUILD_PLAN.md:143-144`'s explicit "enforced forward from CH05, not
    retroactively." **This is the precedent that matters for the whole decision:** the
    project's own established answer to "old work doesn't meet the new standard" is *leave
    it and raise the bar going forward*, not *go back and redo it*.

21. **The LLM tail path is live-by-policy but did not fire in CH05.**
    `conversion_agent/backends/{ollama,claude_code,human}.py`, `prompt_builder.py`,
    `prompts/` appear nowhere in the CH05 diff. Per the parent audit's H5 they are reached
    only when the deterministic transpiler queues something uninterpretable. Under the
    operator's stated rule — *anything deterministic should be code* — this is the one
    subsystem whose **purpose is to be shrinking**, and its non-appearance in CH05 is a
    success metric, not evidence of death.

### Layout coupling — what a mass move would actually cost (findings 22-28)

22. **The asymmetry that decides the archive question: the 96% is cheap to move and the
    game data is expensive.** `engine/` (29,981 files) is located via the
    `RPG2GBA_POKEEMERALD` env var at 30+ call sites and `.env-paths` already points it at an
    absolute path — its code-visible location is one of the *least* coupled things in the
    repo. `reference/` has **no env-var seam at all** and is located exclusively by
    hardcoded means. **Moving the 581 MB vendored engine is nearly free; moving the 8.9 MB
    reference directory is the expensive one.**

23. **`reference/` is located by ~24 hardcoded sites across three mechanisms, and the prior
    audit undercounted by roughly half.**
    - *Mechanism A — `Path(__file__).resolve().parents[N]`*: 27 occurrences in 21 files;
      12 are `parents[3] / "reference"` (e.g. `pbs_converter/tm_hm.py:42`,
      `species_converter/stage.py:256`, `chapter_atlas/binding.py:108`,
      `conversion_agent/fork_index.py:43`, `chapter_manifest/generator.py:664`). The audit's
      finding 10 counted 10 `def _reference_dir()`; **two more sites use the pattern inline
      without the helper name**, so a grep for the function name misses them.
    - *Mechanism B — bare cwd-relative `Path("reference")`*: **12 further sites**
      (`pipeline.py:186`, `routing/plan.py:25`, `routing/__main__.py:65,67`,
      `chapter_manifest/dispositions.py:41`, `chapter_manifest/__main__.py:36,38`,
      `tileset_converter/phase5.py:147`, `tileset_converter/metadata_wiring.py:1323`,
      `conversion_agent/orchestrator.py:91`, `conversion_agent/transpile_driver.py:436,517`).
      **This mechanism is new — no prior audit named it.** It depends on the *process's
      working directory*, so it can break with no file move at all, and after a reorg it
      fails silently if the new cwd contains a same-named subdirectory. It is invisible to
      the `grep "parents\["` sweep anyone executing the move would run.
    - *Mechanism C — env-var-with-relative-fallback*: `RPG2GBA_OUTPUT`, `RPG2GBA_POKEEMERALD`.
      The healthy one.

24. **The env-var loader is itself anchored by a depth walk-up.**
    `src/rpg2gba/pipeline.py:24-44` resolves `.env-paths` via `_repo_root()`, which is
    `Path(__file__).resolve().parents[2]` (`:21`). **If `pipeline.py`'s depth from the repo
    root ever changes, env loading breaks silently** — it finds nothing and returns, and
    every env-var seam in finding 22 quietly reverts to its relative fallback. This is the
    single highest-leverage silent failure in a reorganization: it disables the mechanism
    that would otherwise make the reorganization safe.

25. **`.gitignore`'s ~40 exact `engine/<path>` rules fail silently and in the dangerous
    direction.** Read in full: `output/` is ignored wholesale (`:1`), then roughly 40
    explicit rules name exact generated artifacts (`engine/data/scripts/CommonEvents.inc`,
    `engine/include/constants/uranium_*.gen.h`, `engine/graphics/{object_events,pokemon,trainers}/uranium/`,
    `engine/data/maps/*/`, `engine/sound/direct_sound_samples/cries/*.wav`, …). If `engine/`
    moves, **none of these error — they just stop matching**, and newly generated build
    artifacts become accidentally committable. Git gives zero feedback when an ignore rule
    stops matching. (The file's own comments already record a CH05 near-miss of this shape.)

26. **`output/` is 6.5 GB and entirely untracked — the one big-ticket item that is free.**
    `git ls-files output | wc -l` → **0**. Breakdown: `playtest/` 5.1 G, `uranium-build/`
    923 M, `smoke-worktree/` 386 M, `map_viewer/` 8.4 M, `tileset_palette_study/` 4.5 M.
    Fully regenerable, keyed off `RPG2GBA_OUTPUT` with a sane default. *(Caveat carried from
    the report: this is a git/code-coupling judgment only — whether any artifact is
    expensive to regenerate is a workflow question nobody has answered.)*

27. **CI fails loudly; the skill docs fail silently.** `.github/workflows/ci.yml` runs
    `ruff check src tests` / `ruff format --check src tests` / `pytest` — bare top-level
    names, so a move of `src/` or `tests/` errors immediately. `.pre-commit-config.yaml` has
    **zero** path coupling. But `.claude/skills/pbs-convert/SKILL.md` alone contains **35
    hardcoded prose references** to `reference/`, `output/`, and `src/rpg2gba/pbs_converter/`
    paths (`:32,34,44,61-62,76,100-119,177,206-207`). A moved repo produces no error there —
    just an agent following stale directions from a document that still reads as
    authoritative. **Prose path references are the reorganization's blind spot**, and
    findings 8 and 27 together mean `.claude/` needs the same treatment as the code.

28. **`tests/conftest.py` is the template for the fix.** It computes
    `REPO_ROOT = Path(__file__).resolve().parents[1]` once (`:22`) and funnels both the
    `reference_dir()` and `fork_path()` fixtures through it. One indirection point instead of
    ten. The remediation for findings 22-24 is to mirror this in `src/rpg2gba/` — a bounded,
    single-PR refactor of ~24 call sites, **not** an open-ended one. This is the cheap part.

### Doc corpus triage (findings 29-36)

29. **⚠ A live copy of the "destroy the engine" claim survived the 2026-09-07 remediation,
    in `BUILD_PLAN.md`.** Verified first-hand, `BUILD_PLAN.md:314-317`:
    > "**Tracked obligation:** the fork-baseline divergences (`new_game.c` WarpToTruck spawn
    > override + `intro.c` intro-skip, sentinel-fenced, uncommitted) are *test-only* and must
    > be reverted/gated before any real build — a fresh fork clone drops them. See MEMORY →
    > Decisions Made."

    This is the parent audit's **#1-ranked finding**, the only one whose failure mode is
    destroying working engine features. It was corrected in `engine/RPG2GBA_VENDOR.md` and
    explicitly reversed at `MEMORY.md:163` ("**REVERSED 2026-09-07** … now **false and
    dangerous**: the custom engine work is 77 files of load-bearing features, committed, and
    reverting it destroys the build"). **`BUILD_PLAN.md` was missed**, and neither
    `repo-audit-dead-code-stale-docs.md` nor `claude-md-accuracy-and-compliance.md` mentions
    it (grepped for `WarpToTruck` / `BUILD_PLAN.md §8` — zero hits in both). Worse, its
    final sentence sends the reader to `MEMORY → Decisions Made` — **the exact location that
    now refutes it** — so an agent that follows the pointer sees a contradiction and an
    agent that doesn't, acts on the landmine.
    **This is the strongest single argument in this investigation, and it cuts against
    incremental purge specifically:** a 48-finding audit, executed in three passes by an
    agent that had the correct answer written down, still left the highest-consequence claim
    in the repo standing in a document it had already banner-edited. Hand-enumerated fixes
    miss things; that is not a hypothesis here, it is now measured twice (this, and
    `scripts/calibrate_map002.sh` in the sibling doc).

30. **Three independently-stale hand-drawn repository trees, not one.** `CLAUDE.md.bak:72-112`
    (§3) is the known one. `ROADMAP.md:157-192` is a second copy and is **staler** — it shows
    a bare `src/pbs_converter/` with the `rpg2gba/` package level missing entirely, and lists
    a `backends/anthropic_api.py` that matches nothing else in the corpus. The compliance
    audit scoped itself to CLAUDE.md and so never inventoried the duplicates. Same class as
    finding 42's rotted hand-list of engine files: **hand-maintained inventories rot, and
    this repo now has four documented instances.**

31. **`CLAUDE.md` is far less rotten than its renaming implies.** Section-by-section verdict
    across all 13 sections: **1 DROP** (§3's directory tree), **6 KEEP-BUT-FIX** (§1's framing,
    §4.3's stale source-of-truth row, §5's unscoped typing rule, §6's false "current Phase 2",
    §8's nonexistent `ruby test/test_deserializer.rb` at `:325`, §12's env table), and
    **6 KEEP-AS-IS** (§2 boundaries, the memory-system section, §3's vendored-engine subsection,
    §7, §9 gates, §10 ask-policy, §11 pitfalls). **The behavior contract is sound; the maps
    are stale.** A from-scratch rewrite would spend most of its effort re-deriving rules that
    are already correct, and risks dropping §2/§9/§10 — which the triage found exist in binding
    form *nowhere else in the corpus* (`ROADMAP.md:770` calls its own Agent Guidance a
    "conceptual outline" and defers to CLAUDE.md).

32. **The corpus's authority problem is formally solved; its content problem is not.** The
    2026-09-07 remediation put deferral banners on `BUILD_PLAN.md:3-6`, `ROADMAP.md:3-6`, and
    `PROJECT_TODO.md:3-7`, all routing status claims to `MEMORY.md`, and pruned `MEMORY.md` to
    a chronicle pointer. `MEMORY.md:10-16` now says outright it is "the *sole* authority on
    project status." That worked — and finding 29 is the proof that **banners do not
    disinfect the body text underneath them.** `BUILD_PLAN.md` carries a correct banner and a
    dangerous §8 simultaneously.

33. **`ROM_TEST_DEV.md` is a transcript with 33 referrers — the trap for any archive sweep.**
    It has no banner and no status header, opens as a raw operator note (`:1`), and reads
    exactly like something a blank-canvas pass would leave behind. The parent audit's finding
    37 established it is **the highest-traffic doc in the corpus (33 referrers, confirmed)**,
    and it uniquely holds the `new_game.c` debug-harness re-arm technique (`:882-975`) and the
    P2 time-of-day blocking-decision index (`:976-999`). **Same shape as
    `assemble_pathfinder.py` (18): reads retired, is load-bearing.** Two independent
    instances in two different media is a pattern, not a coincidence.

34. **The chapter-document convention is one chapter old and already has an unactioned
    archive decision.** There are no CH01-CH04 equivalents of `CH05_DECISIONS.md` /
    `POST_CH05_REVIEW.md` anywhere — root or archive (grepped `CH0[1-4]_DECISIONS`,
    `POST_CH0[1-4]` across `investigations/` and `reference/`: zero hits). `POST_CH05_REVIEW.md:30`
    says why: "No precedent; CH05 is the first chapter to have one." That same line, D3,
    **already recommends archiving `CH05_DECISIONS.md`** — and it is still at root. So two of
    the ten root docs are a brand-new convention whose own author has already scheduled one of
    them for archival. (The archived `CH02_TODO.md`-`CH05_TODO.md` are a *different* artifact
    type — per-chapter tracking checklists, archived on gate-pass; `reference/README.md:12`.)

35. **`POST_CH05_REVIEW.md` §0's D1-D5 are open and gate CH06.** `MEMORY.md:26` instructs the
    agent to "Read `POST_CH05_REVIEW.md` before starting [CH06]", and its §0 is titled
    "Decisions I need from you" (`:24-32`). No in-file ANSWERED markers; no `MEMORY.md` entry
    referencing them by ID. *(Reported UNVERIFIED by the triage — consistent with CH06 not
    being open, but not positively confirmed.)* **This decision competes for the same
    operator attention as the reorientation decision, and it is the one blocking actual
    chapter work.**

36. **Sizing the game-pack boundary, for option C below.** `src/rpg2gba/playtest/chapters/`
    is **5,858 lines across ch01-ch05** of irreducibly per-game content (`ch02.py` 1762,
    `ch03.py` 1560, `ch04.py` 1160, `ch05.py` 740, `ch01.py` 635). `reference/` tracked-file
    breakdown: `archive/` 60, `uranium_data/` 29, `guides/` 22, `recon/` 12, `findings/` 12,
    `chapters/` 8, `manifests/` 7, `viewer/` 5, `frozen/` 4, `routes/` 2, plus 16 loose JSONs.
    **The game-specific set is roughly: `reference/`'s data JSONs + `uranium_data/` +
    `chapters/` + `manifests/` + `routes/` + `recon/`, plus `playtest/chapters/`, plus the
    Uranium-named halves of `tests/`.** `guides/`, `findings/`, and `viewer/` are pipeline
    knowledge, not game data — the split is not clean along existing directory lines.

### Operator correction — the two-bucket sort was wrong (finding 37)

37. **The map viewer is live, heavily documented, and fits neither bucket — which means
    option C as originally written condemned it.** Raised by the operator 2026-09-08:
    "there's at least one thing I use frequently that it probably would say I should delete,
    and that's the map viewer server. It's critical to troubleshooting but I doubt it would
    survive based on this test." **He is right, and the evidence backs him hard:**
    - `scripts/map_viewer_server.py`, `map_viewer_common.py`, `map_viewer_events.py` plus
      `scripts/map_viewer/{viewer,knobbar,palette}.{js,css,html}` — last touched **2026-09-04**
      (`e081fce8`), with two more CH05-era commits (`3e100ffb` 09-01, `cd13c3e1` 08-30).
    - **20 documents reference it**, including a dedicated `reference/viewer/` subdirectory
      (5 tracked files: `map_viewer.md`, `map_viewer_palette_plan.md`,
      `map_viewer_perf_and_fidelity.md`, `map_walker_plan.md`,
      `viewer_rom_parity_2026-07-12.md`) and a runbook section at `README.md:131-176`.
    - It carries live tracked bugs (`PROJECT_TODO.md` #13/#14).

    **It is not pipeline code** — it emits no ROM output. **It is not game-pack content** —
    it renders whatever the pipeline produced. It is a **third thing: instrumentation.**

    **This is the same failure mode this investigation criticized option B for, committed one
    level up.** B was rejected because its restore step judges files by their *names*, and
    names twice pointed the wrong way on load-bearing infrastructure (18, 33). The original
    two-bucket sort judges files by their *category*, and does the same thing to the tooling
    you actually debug with. A sorting function with too few buckets is a name test wearing a
    better hat.

    **And instrumentation is the highest-value carry to game #2, not residue.** When the
    pipeline is pointed at an unfamiliar game, the tools that show you what it produced are
    exactly what makes the "minimal changes" goal reachable. The map viewer renders whatever
    `output/` holds; it is *already* close to game-agnostic. Under the corrected sort it is
    not something to justify keeping — it is a first-class deliverable.

### The CH01-CH03 backfill (finding 38) — surfaced by the operator, not by any audit

38. **A due, well-documented validation obligation sits between here and CH06, and none of
    the four fan-out audits surfaced it.** Raised by the operator 2026-09-08: "before we do
    ch6 we need to run the new playtest process on ch1-3 as we have noted and deferred a few
    times." The repo's own record is considerably stronger than "deferred":
    - **`MEMORY.md:120` (2026-09-06):** "CH05 is gated, and **a green CH05 gate is
      deliberately weak evidence for everything except CH05.**" CH05 exercises **zero** seam
      rows, **zero** populated `requires[]`, **zero** mart/Center/PC instances, and its only
      `blocked:` rows are terrain-derived. "**Their real validation is the retroactive
      re-derivation of CH01–CH04 (`PROJECT_TODO.md` #65 + #62 parts 3-4), which is now
      due.** Do not read the 93/93 as a verdict on those systems."
    - **`PROJECT_TODO.md` #65:** CH01–CH03 manifests **no longer load** — `reachability_consulted`
      became a required field. **#67:** no chapter carries a route plan and CH01-CH03
      *cannot get one*; their manifests predate slice 2. `:2143` — CH01–CH03 "predate the
      manifest system and have **no** manifests."
    - **`POST_CH05_REVIEW.md:373`:** "Derive the CH01-CH03 start cells (A1). **The bulk of
      the work.**" Coordinate-literal counts to migrate (`:348`): ch01 **13**, ch02 **45**,
      ch03 **42**.
    - **`MEMORY.md:136`:** the whole-corpus re-disposition (D8) is "**owed against CH01–CH03
      specifically**" and blocked behind C3.

    **This reframes finding 20.** `BUILD_PLAN.md:144`'s "enforced forward from CH05 rather
    than retroactively" is a statement about *slice 3's* validation scope, not a general
    project precedent for leaving old work behind — I over-read it. The project's actual
    posture is that the retroactive pass is **owed and now due**, and `PROJECT_TODO.md:883-884`
    says so explicitly: slice 3 is the *one place* that differs from slice 2, "whose
    retroactive [re-derivation]" was expected.

    **Why it matters to this decision, beyond sequencing: the backfill is the best available
    generalization test short of acquiring a second game.** Re-deriving three chapters written
    before the current machinery existed is precisely a dry run of "point this at content it
    was not authored against." Whatever CH04/CH05-shaped assumptions are baked into
    `chapter_manifest/` and `routing/` will surface there — and those are exactly the findings
    that should decide where the pipeline / game-pack seam gets drawn in step 4. **Running
    step 4 before the backfill means drawing the seam from a one-chapter sample.**

## The decision — three options compared

*This is the artifact. Options A and B are the operator's two; C is the one the evidence
produced. Every claim is keyed to a finding number above.*

### Option A — Incremental purge (continue the established practice)

Keep doing what `reference/archive/` already does: retire artifacts in waves, absorb their
live content first, record the move in the ledger.

**For**
- **It is proven here, three times** (2, 3). The ledger convention — per document, *was* →
  *live content now in* — is a genuinely good artifact, better than most repos have.
- **Zero breakage risk.** Nothing moves, so the entire coupling inventory (22-25) never
  fires. No silent failures, no CI break, no re-verification burden.
- **It never blocks chapter work.** Can be interleaved; CH06 starts whenever the operator wants.
- **It matches the project's own precedent for exactly this situation** (20): route files are
  "enforced forward from CH05, not retroactively" (`BUILD_PLAN.md:143-144`). The project has
  already decided, once, that the answer to "old work doesn't meet the new bar" is *raise the
  bar going forward.*

**Against**
- **It has been measured, and it does not hold.** Five root docs → ten in eighty days (5),
  across a period containing a formal consolidation *and* a 48-finding audit.
- **It has been measured to miss the thing that matters.** Finding 29: the highest-consequence
  claim in the repo survived a three-pass remediation run by an agent that had the correct
  answer in front of it, in a file it had already edited.
- **It does nothing for the stated goal.** Findings 11-13 are untouched by any amount of
  tidying. A perfectly clean repo with no game seam is still a one-game repo.
- **It reproduces the complaint that started this.** The prior audits scoped file count out
  on purpose; that is precisely why the operator read the repo afterwards and called it
  uncleaned. Running the same play again ends the same way.

### Option B — Archive everything, blank canvas, restore what's live

**For**
- **It is the only option that makes non-restoration the default.** This is a real and
  serious advantage: the defect every one of the four investigations independently found is
  that *liveness is recorded nowhere a reader can see it* — 3 markers across 90 files, and
  the one real inventory lives in a document nothing points at.
- **By construction it would have caught finding 29 and `calibrate_map002.sh`**, because
  nothing returns unexamined. Neither hand-enumerated audit did.

**Against — and this is where the evidence is heaviest**
- **Names lie, and they lie in the direction that gets you hurt. Measured twice.**
  `assemble_pathfinder.py` (18) reads as a retired-era relic and is the build step of every
  chapter. `ROM_TEST_DEV.md` (33) reads as an untitled transcript and has 33 referrers. A
  restore pass judges a blank canvas *by reading it*. Two independent instances in two
  different media is a pattern.
- **The live set is not small.** 166 distinct files in CH05 alone (19). This is not "bring
  back the dozen things that matter."
- **The step that makes archiving safe here does not scale.** Absorb-first is hand-written per
  document (2-3). Skipping it has already produced a husk that lied about live code (4).
- **The worst silent failure disables the safety net itself.** Finding 24: `.env-paths`
  loading is anchored by `parents[2]` from `pipeline.py`. Move that file's depth and env
  loading fails *silently*, reverting every env-var seam to its relative fallback — the
  mechanism that would otherwise make the reorganization safe. Add mechanism B (23), which is
  invisible to the `grep "parents\["` sweep whoever executes the move will run, and
  `.gitignore` (25), which fails by silently making build artifacts committable.
- **96% of the repo can't participate.** `engine/` is a hand-edited vendored fork with four
  fence vocabularies plus two unfenced edits; reconstructing it from upstream is provably
  lossy. It sits in the middle of the "blank canvas" permanently (1).
- **It blocks CH06 for its duration** and competes with the D1-D5 decisions that actually gate
  the next chapter (35).

### Option C — Sort by the goal, not by liveness *(recommended)*

Build the game seam findings 11-13 say is missing, and use it as the sorting function.
Roughly, in independently-shippable order:

1. **One resolver.** A single `repo_root()` / `reference_dir()` / `game_dir()` module in
   `src/rpg2gba/`, mirroring `tests/conftest.py:22` — the healthiest pattern in the repo
   (28). Replaces ~24 sites across three mechanisms (23). Bounded, one PR, no behavior change.
2. **One game knob.** `RPG2GBA_GAME` / `--game` selecting a game pack;
   `RPG2GBA_URANIUM_SRC` → `RPG2GBA_GAME_SRC`; retire the hand-copied `"uranium-build"`
   literal (13).
3. **Parameterize the emitted symbol prefix, defaulting to `Uranium`** (12). **This is the
   de-risking move:** output stays byte-identical, so the whole refactor is gateable against
   the existing CH05 ROM by hash.
4. **Split the tree by the answer — into three buckets, not two** (37, operator correction
   2026-09-08). **Pipeline** (game-agnostic conversion code) · **Game pack** (per-game data
   and content, 36) · **Instrumentation** (tools that show you what the pipeline did: the map
   viewer and its `reference/viewer/` docs, the oracle/comparison scripts, the playtest
   harness). Only what fits *none* of the three is dead. **The third bucket is not a
   concession — it is the part that makes game #2 tractable**, and it needs its own home and
   its own liveness markers rather than living unmarked in `scripts/`.
5. **Then** an A-style ledgered pass over the 10 root docs and `.claude/`.

**For**
- **The sorting question becomes decidable.** "Is this general or game-specific?" is answerable
  from code with citations (11-16). "Is this dead?" took 48 findings and still didn't convince.
- **The purge falls out of it** rather than being a separate act of judgment against
  misleading names — which is exactly where B fails.
- **It is the only option that advances the stated goal.** A and B both leave the repo
  one-game.
- **You have to do step 1 anyway.** It is the prerequisite for B (nothing moves safely
  without it), it is the fix the prior audit's findings 9-11 already implied, and it is
  required for game #2. Doing it once, deliberately, is strictly cheaper than doing it under
  a mass move.
- **It has a real safety gate** — byte-identical ROM output — that neither A nor B offers.

**Against**
- **It is the largest change**, touching code, tests, CI, docs, and `.claude/` skills (27).
- **It does not clean the doc corpus by itself.** The 10 root docs still need an A-style pass;
  C makes that pass smaller and better-targeted, it does not replace it.
- **It does not make the expensive part cheaper.** The curated per-game JSON — chapters,
  manifests, routes, tileset overrides, and 5,858 lines of playtest chapters (36) — is
  irreducible re-authoring effort for game #2 no matter how well the seam is drawn (15). C
  makes the *location* honest, not the work smaller.
- **Big-bang risk.** Mitigated by the numbered order above: steps 1-3 are behavior-preserving
  and independently shippable, and step 4 is the only one that moves files.

### Recommendation

**C, executed with A's ledger discipline, and explicitly not B.** B's one real advantage —
forcing an explicit decision on every file — is bought at the price of judging 600 files by
their names, and this repo has now produced two measured cases where the name points the wrong
way on load-bearing infrastructure.

**Do this first, today, independent of the choice:** fix `BUILD_PLAN.md:314-317` (29). It is
live, it is the one claim in the repo whose failure mode is destroying the build, and it
currently contradicts `MEMORY.md:163` while citing it.

**And on CLAUDE.md:** edit in place, do not rewrite from a blank page (31). Delete §3's tree
(the third stale copy of which is `ROADMAP.md:157-192` — 30), make the six factual fixes, keep
§2/§9/§10 untouched, and add the one thing genuinely missing: the chapter loop's four entry
points, which the CLI does not expose and no document lists in one place (17).

## Hypotheses / unverified

- ~~**H1**~~ — **CONFIRMED 2026-09-08**, see findings 11-16. Stronger than stated: it is not
  only that liveness audits kept Uranium-specific code, it is that the game's name is in the
  emitted C symbols (12) and the only source knob is named after it (11). *Original text:*
  The generalization goal ("a new game needs minimal changes") is a *harder* filter
  than "is it live", and will condemn code the liveness audits kept. A module can be fully
  live, fully tested, and still be a pile of Uranium constants. Nothing in the four prior
  investigations asked this question — they all asked "is it dead?", never "is it
  general?". Confirmation: the Uranium-specificity audit now running.
- ~~**H2**~~ — **CONFIRMED**, and sharpened by finding 17: liveness is not merely unrecorded,
  the repo's most authoritative machine-readable surface (the CLI) records the *wrong* answer.
  *Original text:* The real defect is not the file count but that **liveness is not recorded
  anywhere a reader can see it** — the `scripts/` doc already found 3 markers across 90
  files, and finding 47's inventory "lives only in [an investigation] document, which
  nothing points at" (`investigations/scripts-dir-liveness.md`, Summary). If true, both
  proposed approaches are treatments for a symptom, and a marker convention is the cure.
  Confirmation: whether the live-spine trace can be reconstructed from the repo alone.

## Decisions

**D7 — The three sibling docs: fold two, keep `scripts-dir-liveness.md` open.** (2026-09-08,
in chat.) `claude-md-accuracy-and-compliance.md` closes into D4, carrying its Q5 forward as
**Q8** below. `conversion-agent-package-boundary.md` closes into step 4's three-bucket split,
which is a better cut than the rename it was considering. `scripts-dir-liveness.md` **stays
open** — no decision here answers its liveness-marker question, and D1's instrumentation
bucket plus finding 18 are fresh evidence for it.

**D6 — `output/` is kept whole for now.** (2026-09-08, in chat.) The operator declined the
drop. **What it changed:** the reasoning is better than the one I offered — the backfill is
about to regenerate playtest artifacts for CH01-CH03, so the existing `output/playtest/`
(5.1 G) is a **before/after comparison baseline for exactly the run we are about to do**, and
`MEMORY.md:120` says that run is the real validation of systems CH05 could not exercise.
Revisit after the backfill, not before. *(Carries one live risk worth watching: several
modules default to paths under `output/uranium-build/` — 13 — so a stale artifact there can
be read silently. If the backfill produces a confusing result, suspect this first.)*

**D5 — CLI: add the chapter entry points, don't rename the phase ones.** (2026-09-08, in
chat.) Register `chapter_atlas`, `chapter_manifest`, `routing`, `playtest` as real
subcommands; leave `phase2-5` working with a "(pipeline stage N)" help string. **What it
changed:** finding 17's damage — an agent reading `pipeline.py` sees only the retired model —
is fixed before the backfill, which is the run where agents most need to find the chapter
tooling. Finding 9's rename cost is not paid. Revisit at step 4.

**D4 — CLAUDE.md is edited in place, before the backfill.** (2026-09-08, in chat.) Restore
from `CLAUDE.md.bak`; DROP §3's tree; apply the six factual fixes; keep §2/§9/§10/§11 as-is;
add the four chapter-loop entry points missing from the CLI surface (17). **What it changed:**
`CLAUDE.md.bak` is no longer a rewrite candidate — it is the working base, and the sibling doc
`claude-md-accuracy-and-compliance.md` Q1 (delete the tree) and Q4 (§1's framing) are answered
by this decision. Its Q5 (scope §5's typing rule vs. annotate ~675 functions) is **not**
answered and still needs a call.

**D3 — Backfill first, then seam steps 1-3, then step 4.** (2026-09-08, in chat.) **What it
changed:** the working order is now (0) fix `BUILD_PLAN.md:314-317`; (1) answer
`POST_CH05_REVIEW.md` §0 D1-D5, which scope the backfill; (2) run the CH01-CH03 re-derivation;
(3) seam steps 1-3, hash-gated; (4) tree split into pipeline/game-pack/instrumentation;
(5) CH06. **Raises the priority of Q3** — the backfill is a large agent-driven run and the
repo currently has no `CLAUDE.md` at all, so the behavior contract needs restoring *before*
step 2, not after.

**D2 — Steps 1-3 before CH06, step 4 after; plus the CH01-CH03 backfill lands before CH06
too.** (2026-09-08, in chat.) The operator accepted the Q2 recommendation and added the
backfill obligation, which no audit had surfaced — see finding 38. **What it changed:** Q2's
answer is no longer a two-way split. The remaining fork is where the backfill sits relative
to the seam plumbing, which is now Q7. It also retires my reading of finding 20: the
"enforced forward, not retroactively" line is scoped to slice 3, not a project-wide
precedent, so that argument is withdrawn from option A's case.

**D1 — Approach C, with a corrected three-bucket sort.** (2026-09-08, in chat.) The operator
chose C and immediately found a hole in it: the map viewer server is critical to
troubleshooting and would not have survived a general-vs-game-specific test. Confirmed —
see finding 37. **What it changed:** option C's step 4 now sorts into *pipeline / game pack /
instrumentation*, and the purge rule tightens from "anything in neither bucket" to "anything
in none of the three." The correction also generalizes: it is the same defect this doc used
to reject option B (judging files by a label instead of by evidence), so **every bucket
assignment in step 4 must be backed by import-trace or git-recency evidence, not by
category intuition** — the standard findings 18 and 33 were established to enforce.

## Open questions

### Q1. Which approach — A (incremental), B (blank canvas), or C (sort by the goal)?
The full comparison is in "The decision" above. The short version: A is proven but measured
not to hold (5) and measured to miss the important thing (29); B's restore step judges 600
files by names that have twice been shown to point the wrong way on load-bearing
infrastructure (18, 33); C uses the generalization goal as the sorting function, gets the
purge as a side effect, and needs a refactor that is a prerequisite for the other two anyway.

**Recommendation:** **C**, with A's ledger discipline for the doc pass, and not B. C is the
only option that advances the stated goal rather than tidying around it, and it is the only
one with a hard safety gate (byte-identical ROM output, step 3).
**Blocked on:** —
**Answer:**

### Q2. Does the seam work happen before CH06, or after it?
C's steps 1-3 are behavior-preserving but they touch ~24 call sites across the packages CH06
will be actively editing. Doing it first means a clean base and no merge pain; doing it after
means CH06 ships sooner and the refactor lands against a repo whose chapter machinery just
moved (19: CH05 touched 166 files, heaviest in `playtest/` and `chapter_manifest/`).
Competing for the same attention: `POST_CH05_REVIEW.md` §0's D1-D5, which are the decisions
that actually gate CH06 (35).

**Recommendation:** **Steps 1-3 before CH06, step 4 after.** Steps 1-3 are pure plumbing with
a hash gate and no file moves — the cheapest they will ever be, and they get cheaper still by
landing before another chapter's worth of new call sites is written. Step 4 moves files, and
moving files while a chapter is in flight is how merge conflicts eat a week. Answer D1-D5
first regardless; they are smaller and they block real work.
**Blocked on:** —
**Answer:**

### Q3. CLAUDE.md — rewrite from scratch, or edit in place?
You renamed it to `.bak`, which signals from-scratch. The section audit says the file is 1
DROP / 6 KEEP-BUT-FIX / 6 KEEP-AS-IS (31), and that §2's boundaries, §9's gates and §10's
ask-policy exist in binding form nowhere else in the corpus — `ROADMAP.md:770` explicitly
calls its own version a "conceptual outline" and defers here.

**Recommendation:** **Edit in place.** Restore `CLAUDE.md`, delete §3's tree, apply the six
fixes, and add the missing chapter-flow entry points (17). A blank page re-derives twelve
sound sections at the cost of the four that took real incidents to learn. If you want the
*feel* of a rewrite, reorder it so the chapter loop leads and the phase model is demoted —
that is a restructure, not a re-derivation.
**Blocked on:** — (but if Q1 = C, sequence this after C's step 1, so §3's replacement text
describes the new resolver rather than the old three mechanisms)
**Answer:**

### Q4. Do the phase-named CLI subcommands get renamed?
`phase2/3/4/5` are the public command surface (9), they are what `README.md:41-44` tells a
user to type, and the live chapter loop is *not* in the CLI at all (17). Renaming touches
code, tests, docs, runbooks and every skill file.

**Recommendation:** **Add, don't rename — for now.** Register the four chapter entry points
(`chapter_atlas`, `chapter_manifest`, `routing`, `playtest`) as real subcommands so the CLI
stops lying by omission, and leave `phase2-5` as working aliases with a one-line "(pipeline
stage N)" help string. That fixes the misleading-surface problem, which is the actual damage,
without paying a rename's migration cost for a cosmetic gain. Revisit once C's step 4 lands.
**Blocked on:** Q1
**Answer:**

### Q5. `output/` is 6.5 GB and entirely untracked — drop it, or keep it?
`git ls-files output` returns zero (26). It is fully regenerable and keyed off `RPG2GBA_OUTPUT`.
`playtest/` alone is 5.1 GB. The audit flagged, correctly, that git evidence cannot tell you
whether any of it is *expensive* to regenerate — that is a workflow question only you can
answer.

**Recommendation:** **Drop everything except `output/uranium-build/` (923 M), and only after
you confirm nothing in `output/playtest/` is a comparison baseline you still want.** It is
the single cheapest large win available and it is independent of Q1 — worth doing under any
option.
**Blocked on:** —
**Answer:**

### Q6. Do the three blocked sibling investigations close into this decision, or stay open?
`claude-md-accuracy-and-compliance.md` (Q1, Q2, Q4, Q5), `scripts-dir-liveness.md`, and
`conversion-agent-package-boundary.md` have all been blocked on you since 2026-09-07 (6).
Q3 above resolves the first doc's Q1 and Q4 by construction. C's step 4 resolves the
package-boundary doc's central question by construction — the package gets split by
general-vs-game-specific, which is a better cut than renaming it. `scripts-dir-liveness.md`
is **not** subsumed: its liveness-marker question survives every option here, and finding 18
is fresh evidence for it.

**Recommendation:** **Fold the first and third into this doc's decision; keep
`scripts-dir-liveness.md` open** and answer its questions separately — it is the one whose
core finding (nothing in the repo records what is live) is the root cause the other three
kept circling.
**Blocked on:** Q1
**Answer:**

### Q8. Scope §5's typing convention to `src/`, or enforce it everywhere? *(carried from `claude-md-accuracy-and-compliance.md` Q5)*
The only question surviving that doc. §5 reads as repo-wide law; measured, the generics ban
holds repo-wide but "type hints on all public functions" holds in `src/` and fails in
`scripts/` (17% missing) and `tests/` (18%). Options: (a) scope the rule to `src/rpg2gba/`;
(b) annotate ~675 functions, most of them one-line test bodies; (c) enforce mechanically with
ruff's `ANN` rules and a per-directory config.

**Recommendation:** (a) now, (c) later if you want it to stay true. A pytest test has no
caller, so `-> None` on it is annotation noise. **Does not block anything** — fold it into
D4's CLAUDE.md edit pass as a one-line scope statement.
**Blocked on:** —
**Answer:**

## Next steps

The execution order set by D1-D7. Steps 0-2 are the CLAUDE.md/safety work; step 3 is the
overdue validation; steps 4-6 are the reorientation proper.

0. **Fix `BUILD_PLAN.md:314-317`** (29). Live "revert the engine C before any real build"
   claim, contradicting `MEMORY.md:163` while citing it. Not a decision — a correction the
   2026-09-07 remediation intended and missed.
1. **Restore and edit `CLAUDE.md`** per D4: DROP §3's tree, six factual fixes, keep
   §2/§9/§10/§11, add Q8's scope line. Also fix `ROADMAP.md:157-192`, the stalest of the
   three hand-drawn trees (30).
2. **Add the four chapter entry points to the CLI** per D5 (17).
3. **Answer `POST_CH05_REVIEW.md` §0 D1-D5** (35) — they scope the backfill — then **run the
   CH01-CH03 re-derivation** (38). This is the project's real validation event, not a chore:
   `MEMORY.md:120` says the CH05 gate is weak evidence for everything CH05 didn't exercise.
   Treat its findings as input to step 5's seam placement.
4. **Seam steps 1-3** (D3): the single path resolver (~24 sites, template at
   `tests/conftest.py:22` — 23, 28), the `--game`/`RPG2GBA_GAME` knob, and the emitted-symbol
   prefix parameterized with default `Uranium`. Gate the whole thing on byte-identical ROM
   output.
5. **Step 4 — the three-bucket split** (D1): pipeline / game pack / instrumentation. Every
   assignment backed by import-trace or git-recency evidence, never by category intuition.
   Anything in none of the three is dead; that is the purge.
6. **Then CH06.**
7. **Housekeeping:** close the two folded sibling docs per D7; run an A-style ledgered pass
   over the 10 root docs and `.claude/`'s 5 skills (27) once the layout is settled; revisit
   `output/` (D6) and the CLI rename (D5) after step 5.

## Ground covered

- `reference/archive/` — read; the existing convention and its ledger. Findings 2-4.
- Root doc creation dates via `git log --diff-filter=A`. Finding 5.
- The three sibling docs' `**Answer:**` lines — all still empty 2026-09-08. Finding 6.
- Phase-vs-chapter vocabulary counts across the five main docs. Finding 7.
- `.claude/` — 5 tracked skills, all currently maintained. Finding 8. **Not examined:** the
  skill *bodies* beyond `pbs-convert`'s path references (27); `.claude/worktrees/`.
- `src/rpg2gba/pipeline.py` subcommand registry. Findings 9, 17.
- Uranium-specificity across all 13 sub-packages + `tests/`. Findings 11-16.
- CH05 development range (`c27f9dc5^..af0d8e25`, 166 files). Findings 19, 21.
- Path-resolution mechanisms across `src/` and `scripts/`; `.gitignore`, `.github/workflows/ci.yml`,
  `.pre-commit-config.yaml`, `pyproject.toml`, `tests/conftest.py`, `.env.example`, `.env-paths`
  (the committed examples only — `.env` deliberately not read). Findings 22-28.
- All 10 root markdown docs, classified. Findings 29-35.
- **Looked for and not found:** any `GameProfile`/`GameConfig`/`--game`/`--reference-dir`
  seam (11); any CH01-CH04 equivalent of `CH05_DECISIONS.md`/`POST_CH05_REVIEW.md`, at root
  or archived (34); any `.gitmodules` or `engine/.git` — `engine/` is a flat vendored copy,
  not a submodule (22); any mention of `WarpToTruck` or `BUILD_PLAN.md §8` in either prior
  investigation (29).
- **Deliberately not done:** any audit of process-rule compliance (§9 gates, §10 ask-policy);
  enumeration of `output/` below top level; whether `POST_CH05_REVIEW.md`'s D1-D5 are answered
  outside the file (35, UNVERIFIED); whether `tileset_converter`'s ~25 map-specific comment
  citations represent over-fitting to one game (15, would require a second game to settle).

---

## Execution log — 2026-09-08, steps 0-2

Branch `repo-audit-remediation`. **Not committed** — awaiting the operator's call on branch
policy (`MEMORY.md:26` says in-between work goes straight to `main`; this branch was already
open from the prior audit).

### Step 0 — `BUILD_PLAN.md` §8 (finding 29). **DONE**
Replaced the "Tracked obligation" paragraph at `:314-317` with a dated correction matching the
wording already used in `engine/RPG2GBA_VENDOR.md:28-38` and `MEMORY.md:163`: the custom engine
work is 77 files / +2647 −343, committed and load-bearing, and `git diff 80cdfce2 HEAD -- engine/`
is the canonical check. **The last live copy of the build-destroying claim is gone.**

### Step 1 — `CLAUDE.md` restored and edited in place (D4). **DONE**
`cp CLAUDE.md.bak CLAUDE.md`, then eight edits:
1. **§1** — second bullet now leads with the deterministic transpiler as the spine and demotes
   the LLM to a hand-invoked tail tool, keeping the role-confusion warning. Adds the line that
   its shrinking is the point. *(Answers `claude-md-accuracy-and-compliance.md` Q4.)*
2. **§3** — the hand-drawn directory tree is **deleted**, replaced by a prose orientation
   explicitly labelled "orientation, not an inventory", pointing at `ls src/rpg2gba/` as the
   authority. Names the five packages worth knowing, and carries forward finding 18's warning
   that `scripts/` filenames do not indicate liveness — `assemble_pathfinder.py` called out by
   name. *(Answers that doc's Q1, recommendation (b).)*
3. **§4.3** — two new source-of-truth rows: `_naming.py` → `to_constant(prefix, name)` as the
   single mint point for constant spelling (verified at `_naming.py:47`), and `_resolve.py`'s
   five resolver mixins for emit-time resolution (verified at `:47,72,94,115,136`). Closes the
   gap the parent audit's own consolidation created.
4. **§5** — scope statement added: binding in `src/rpg2gba/`; in `scripts/`/`tests/` only the
   built-in-generics ban binds. **This lands Q8 as recommended**, so Q8 is now answered.
5. **§6** — "dormant during the current Phase 2" corrected; Phase 4 is active per `MEMORY.md:36`
   ("Active: Phase-4 rework"). The rule-suppressing error is gone.
6. **§8** — the `ruby test/test_deserializer.rb` line removed (file and directory do not exist),
   with a note that there is no standalone Ruby suite and that adding one is a task, not a doc fix.
7. **§12** — env table rebuilt with a "Set in" column: `RPG2GBA_PORYSCRIPT` added (it *is* in
   `.env-paths`), `RPG2GBA_OUTPUT` correctly marked a code default, `OLLAMA_HOST` marked
   `.env.example`-only.
8. **§7** — **new subsection, "The chapter loop's entry points"** (finding 17): the four
   packages with their commands, and an explicit warning that reading `pipeline.py` alone
   misleads.

Also **`ROADMAP.md:157-192`** — the third and stalest hand-drawn tree deleted (finding 30),
replaced by a pointer to `CLAUDE.md` §3 and a note on why hand-maintained inventories rot here.

### Step 2 — chapter entry points in the CLI (D5). **DONE, verified**
`src/rpg2gba/pipeline.py`: generalized `_LazyTranspileEvents` into a reusable `_LazyGroup`
taking a `"module.path:attr"` target, preserving the lazy-import behaviour, then registered
four delegating groups — `chapter-atlas`, `chapter-manifest`, `routing`, `playtest` — against
each package's existing `__main__:cli`. `phase2/3/4/5` kept and their help strings changed to
"(pipeline stage N — …)". `main`'s docstring now names both families.

**Verified by running:** all five delegated groups resolve and list their real subcommands
(`chapter-atlas` → validate/list/census/coverage; `chapter-manifest` → generate/check/review;
`routing` → plan/locations/show; `playtest` → run/walk/seeds/list/rules-lag/conformance;
`transpile-events` → run, i.e. the refactor did not break the existing delegate).

### Verification
- **Tests: 2984 passed, 16 skipped, 2 failed.** Both failures are
  `tests/test_deterministic.py::test_{ground_item,pokemart}_differential_vs_frozen_opus`, and
  both are **pre-existing and already tracked** — `PROJECT_TODO.md` **#86**, "Frozen-Opus
  differential oracle is stale as of Map036 — two permanently red tests". Confirmed
  independently by stashing the `pipeline.py` change and re-running: identical two failures.
- **Ruff on `pipeline.py`: 2 errors before my change, the same 2 after** (E501 at
  `_phase4_backend` and the `ClaudeCodeBackend` return, both untouched pre-existing lines).
  **Zero new lint errors introduced.**
- **Incidental finding, not acted on:** repo-wide `ruff format --check src tests` reports
  **283 files would be reformatted**, and `ruff check src tests` reports errors across many
  untouched files. Cause is a version split — the venv has **ruff 0.15.12**,
  `.pre-commit-config.yaml` pins **v0.4.4**, and `.github/workflows/ci.yml:17` installs
  unpinned `ruff` (i.e. latest). **CI's format job is therefore almost certainly red on any
  branch**, independent of this work. Worth its own small task: pin ruff in all three places.
