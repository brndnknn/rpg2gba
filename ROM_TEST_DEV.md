i want to try out using the rom testing to drive development. 
heres what I'm thinking
step 1: agent drafts story plot and area event document using pokemon uranium wiki. plot is broken into chapters: for example the early game in moki town, or the trip through route one. chapters can vary in content. story heavy chapters are like moki town early game with all of its events and a fixed order. exploration chapters are like the trip through route one with a bunch trainers to battle and wild pokemon to catch and not set order. these names are informal and atleast some of the chapters will have elements of both. 
step 2: agent matches up rpg data to plot points. this way it can understand the expected behaviour.
step 3: agent writes a rom play test that goes through the chapter testing that everything works as expected. so for route 1 the rom should test every trainer battle, make sure wild pokemon spawn in the grass, get the old rod from the house, and so on.
Step 4: agent looks at events that need conversion in the chapter and tries to match them up with native pokeemerald code, anything that looks like it needs hand conversion the agent double checks that the porblem can't be broken down into smaller problems that may have pokeemerald analogs or that there isnt a way to bootstrap it. anything that needs hand converting gets surfaced to me. the goal is to minimize custom c code as much as possible. 
step 5: agent runs ROM test until it errors or reaches the end of the chapter its working on. ROM test always starts from a new game to gaurd against regressions. if the same event causes the test to fail more than once the agent should look at pokeemerald wiki to try to sort it out. 

the goal is to automate play testing and eliminate me having to do the boot walk over and over
i want to set up the testing so when it 

---

# Grill session — 2026-07-18 (non-interactive, appended by build agent)

Questions grouped into branches, walking the design tree in dependency order. Where I
have a recommendation it's marked **➤ Recommendation**; where I don't, there's
**Context** to help you decide. Answer in shorthand whenever ("A1: b, A2: a but only
for X"). Repo exploration was delegated to sub-agents (harness internals, recorded
decisions in MEMORY/SLICE1_TODO, transpiler tail workflow, wiki resources); the
load-bearing findings are inlined so you can answer without re-reading code.

## Grounding facts the questions lean on

- **Harness today** (`src/rpg2gba/playtest/`): libmgba-py in-process, ~2,300 fps.
  Primitives: `walk_to` / `face` / `interact` / `advance_dialog` / `save_in_game`,
  all poll-based with frame budgets + failure screenshots. Observables: player pos,
  map location, flags, field-lock. **Missing:** var reads (offset already probed,
  no accessor), any battle interaction, wild-encounter control, text-content
  assertions, multi-scenario chaining, RNG control. One scenario exists
  (`moki-running-shoes`), written as a plain Python function.
- **Embedded-save stamping** exists but only as a *terminal* review artifact
  (scenario → stamp → taildrop). "Boot from blob, then keep scripting on top" is
  mechanically possible but unimplemented.
- **Step 4 already has a workflow**: transpiler queues unhandled commands to
  `transpile_unhandled.jsonl` → queue readthrough doc buckets them
  (native / idiom / hand / defer) → idiom bar = ≥2 occurrences + fork-verified
  native analog → irreducible events become `hand_conversions/*.pory`. Slice 1 has
  **1 live queue entry** left (Map049 species-check, blocked on Phase 7).
- **Wiki**: fandom.com returns HTTP 402 here (research goes through WebSearch
  snippets / mirrors); on the Moki chain alone the wiki had 3 discrepancies vs the
  rxdata. `reference/findings/moki_slice_story_chain_2026-07-16.md` is already a
  chapter-document prototype: 12 beats, each with gate + effect, derived
  rxdata-first with the wiki as cross-check.
- **Standing decisions on record** (2026-07-13/17): fresh-start-always as the
  regression guardrail; `new_game.c` test grant (Badge 3, lv5 Geodude, Rock Smash)
  kept indefinitely; harness is "a regression floor **under** the §9 boot-walk…
  the manual gate stays" (explicit non-goal in the feasibility doc).

---

## Branch A — The chapter document (steps 1–2): what it is, where truth comes from

**A1. Primary source for the chapter/event document?**
- a) Wiki-first, then match rxdata to it (as drafted in step 1–2)
- b) **rxdata-first, wiki as cross-check** — derive beats/gates/effects from the
  deserialized events, then diff against the wiki walkthrough and record
  discrepancies explicitly
- c) rxdata only, skip the wiki

➤ **Recommendation: b.** That's exactly how the Moki story-chain doc was produced
and it worked: the rxdata is ground truth for what the ROM must *do*; the wiki
caught intent-level things (what the player is supposed to experience) and was
wrong 3 times. Wiki-first inverts the reliability ordering and fights the 402
block. (c) throws away the only independent check on "did we understand the
events correctly."

**A2. Spoiler policy for the chapter document?** (You've asked to avoid Uranium
story spoilers; a plot document is inherently spoilery.)
- a) **Mechanical/spoiler-free** — beats described as gates and effects ("NPC X
  blocks exit until VAR_Y ≥ 1"), same convention as the Moki doc and this repo's
  norm
- b) Full narrative, but agent-facing only (you never read it, only the test
  results)
- c) Full narrative, you read it — you've decided spoilers don't matter for areas
  you have to boot-walk anyway

➤ **Recommendation: a.** It's already the house style, it's sufficient for test
authoring (tests assert flags/vars/positions, not prose), and (b) is fragile —
you *will* end up reading these docs when a test fails.

**A3. Where do chapter documents live?**
- a) **`reference/chapters/` (or keep `reference/findings/`), committed** — they're
  hand-curated review artifacts like the Moki doc
- b) `output/` — regenerated per run, treated as derived
- c) Not written down at all — the chapter "document" is just the docstring of the
  chapter's test scenario

➤ **Recommendation: a.** The doc is where wiki-vs-rxdata discrepancies and
accepted-deviation notes accumulate — that's curation, not generation, so it
belongs in git. (b) would regenerate away your annotations; (c) buries decisions
in code.

**A4. Does the chapter doc carry machine-readable test bindings?**
- a) Prose + explicit gate/effect lines (Moki style); the agent interprets it when
  hand-writing the Python scenario
- b) Structured beat schema (YAML/JSON blocks per beat: expected flag/var writes,
  coords, map ids) that the test harness consumes directly

**Context, no strong recommendation:** (a) is proven and zero new machinery, but
every chapter costs a hand-translation into Python, and doc/test drift is
possible. (b) makes the doc the single source of truth for both reading and
testing, but you'd be designing a beat schema now, before you know what chapter 2+
beats even look like — and exploration chapters (unordered trainer sweeps) fit a
schema much less cleanly than story chains. If in doubt: start (a), extract a
schema only if the third chapter's translation feels mechanical.

---

## Branch B — Chapter boundaries and coverage semantics

**B1. What is a chapter?**
- a) **Chapter ≡ slice** (the existing build/convert unit; Moki = 8 maps). Chapters
  and slices advance together
- b) Chapter = a quest-var span (e.g., one VAR_QUEST_LOG value range), independent
  of slice boundaries
- c) Chapter = wiki walkthrough section

➤ **Recommendation: a, revisit at slice 3.** For the current frontier they
coincide anyway (Moki chapter = slice 1; Route 1 trip = slice 2), the §9 gate is
already per-slice, and a chapter that spans unconverted maps can't run. The real
test of (a) is when a story arc crosses a slice boundary mid-beat — decide then,
not now.

**B2. Coverage model for exploration chapters (unordered content)?**
- a) **One canonical tour** — a fixed order the test always walks (test order ≠
  required game order), touching every trainer/item/encounter zone once
- b) Canonical tour + targeted permutation cases only where the data shows
  order-sensitive gates (e.g., an event that behaves differently if you did X
  first)
- c) Multiple randomized orders per run

➤ **Recommendation: a now, b when the transpiler queue or chapter doc actually
surfaces an order-sensitive gate.** Order sensitivity is visible statically (a
page conditioned on a flag another optional event sets) — enumerate permutations
from the data when they exist rather than paying (c)'s nondeterminism tax on
every run.

**B3. What is the test actually testing — where's the scope line?** "Test every
trainer battle" can mean two very different things:
- a) **Conversion artifacts only**: the battle *launches*, the enemy party matches
  the converted trainer data (species/levels readable from `gEnemyParty`), and
  winning sets the right defeat flag / post-battle effects. Vanilla battle-engine
  correctness (damage math, AI) is upstream's and untested
- b) Full battle playthroughs as an end-to-end smoke test, accepting that most of
  what's exercised is stock engine code

➤ **Recommendation: a.** Everything this pipeline can break lives in the data and
the script wiring — party contents, battle-trigger scripts, defeat flags, reward
handouts. Testing Emerald's battle engine re-tests upstream. Same logic for wild
encounters: assert the converted table + that an encounter *fires*; don't test
catching mechanics.

---

## Branch C — Harness capability gaps (step 3 depends on all of these)

**C1. How do trainer battles resolve deterministically?**
- a) Beef the party (extend the standing `new_game.c` grant, or a test-build
  variant, with a lv100 no-miss sweeper), A-mash through; assert defeat flag after
- b) **Read + assert `gEnemyParty` at battle start, then RAM-write enemy HP to 0
  and let the engine's real battle-end path run**; assert defeat flag / post-battle
  script effects after
- c) Detect battle launch + assert party, then force-exit the battle entirely via
  RAM

➤ **Recommendation: b.** Fully deterministic, fast, and still exercises the
converter-owned surface end-to-end (trigger script → correct party → real
victory path → defeat flag → post-battle script). (a) is an acceptable v1 but
A-mashing is only *mostly* deterministic and hundreds of frames per battle;
(c) skips the battle-end code path, which is exactly where defeat flags get set.
Note (a) also changes the fresh-start state that every regression run shares —
the grant is standing in all builds today.

**C2. Wild encounter coverage?**
- a) Static golden test on the converted encounter tables (no emulator needed) only
- b) One real walk-in-grass encounter per map: walk until an encounter fires
  (bounded budget), assert species ∈ expected table, run away
- c) **Both** — golden test for table contents, one live encounter per grass map
  for wiring

➤ **Recommendation: c.** The golden test catches data bugs cheaply and
exhaustively; the single live encounter catches wiring bugs (grass behavior bytes,
header hookup) the static test can't see. Fleeing needs the same minimal
battle-menu primitive as C1, so it's nearly free once that exists.

**C3. New primitives to build, in priority order.** Proposed order — confirm or
reorder:
1. `var(id)` accessor (offset already probed; ~3 lines; unblocks quest-log
   assertions, which the Moki chain S-checks need *today*)
2. Battle-menu mini-driver: detect in-battle, navigate FIGHT/RUN, plus the C1
   enemy-HP write and `gEnemyParty` reader
3. `walk_to` step-aside-and-retry fallback (the known NPC body-block flake, see C6)
4. Party/inventory readers (assert item handouts like the old rod without opening
   the bag)
5. Text-content reading — **punt indefinitely**; field-lock + state assertions
   cover behavior, and text stays a by-eye §9 item

➤ **Recommendation: as listed.** 1 is trivial and immediately useful; 2 unblocks
both battle questions; 5 is high-effort/low-yield (tile-decoding VRAM text) and
its failure modes (typos, overflow) are what the manual walk already catches.

**C4. Chapter scenario authoring format?**
- a) **Plain Python functions** (current pattern), one module per chapter, small
  shared helpers as they emerge
- b) A declarative step DSL (data-driven scenarios) interpreted by the harness

➤ **Recommendation: a.** One scenario exists; a DSL now is premature abstraction.
The chapter tests will *discover* the right abstractions (e.g., "beat" helpers) —
extract them after two or three chapters, per A4's same logic.

**C5. Runner surface?**
- a) Everything through pytest (current `RPG2GBA_PLAYTEST=1` opt-in)
- b) **Standalone CLI for iteration (`python -m rpg2gba.playtest run --chapter
  moki [--from-beat N]`) + a thin pytest wrapper that runs the full chapter suite
  for gate/CI runs**
- c) CLI only

➤ **Recommendation: b.** The dev loop (step 5) wants chapter selection, verbose
progress, and artifact paths printed; pytest wants a binary green/red for "did
anything regress." They're different consumers of the same scenarios.

**C6. NPC random-walk body-blocking (known open risk, currently just
timeout+screenshot)?**
- a) **Fix in the harness**: step-aside-and-retry inside `walk_to`, treat residual
  stuck-timeouts as real failures
- b) Freeze NPC movement in test builds (a build flag)
- c) Accept flakes; auto-rerun failed chapters once to classify flake vs real

➤ **Recommendation: a, with c's single-rerun as a stopgap until it's built.**
(b) is the dangerous one: NPC movement is converter output you *want* under test
(the RMXP blocked-move semantics bug class came from exactly this code), and a
frozen-NPC ROM isn't the ROM you ship for review.

---

## Branch D — "Always start from a new game" vs chapter seeding (step 5)

**D1. Run topology as chapters accumulate?** At ~2,300 fps this is a non-issue for
Moki, but chapter N's dev loop replaying chapters 1..N-1 on every attempt adds
wall-clock and — worse — makes chapter-N failures ambiguous with upstream noise.
- a) Strict new-game-always for every run, forever (your recorded 2026-07-17
  guardrail, applied literally)
- b) **Two modes: iteration runs may seed chapter N from an embedded-save blob
  produced by a green chapter N-1 run of the *same build*; the gate/regression
  bar stays full-from-new-game** (guardrail unchanged where it matters)
- c) Blob-chaining as the norm; full runs only occasionally

➤ **Recommendation: b.** It keeps the guardrail's actual intent (no regression
ever certified from a stale save) while making the dev loop scale. The stamping
machinery already exists; the missing piece is small — an `Emulator` boot path
that runs a blob-stamped ROM instead of new-game, then keeps scripting. (c)
quietly erodes the guardrail: a blob is a cache, and cache invalidation bugs here
look exactly like "the ROM works."

**D2. If seeding exists (D1: b/c), blob provenance rules?**
- a) **Blobs are derived artifacts: regenerated from a green full run of the
  current build, live in `output/`, never committed, invalidated by any ROM
  rebuild**
- b) Keep a library of committed checkpoint blobs per chapter

➤ **Recommendation: a — and (b) is close to forced-off anyway.** A blob bakes in
flag/var IDs and SaveBlock layout from a specific build; the flag registry can
renumber and the engine structs can move. A committed blob is a stale save with
version-control legitimacy — the exact thing the guardrail exists to prevent.
(The stamper already refuses size-mismatched blobs loudly, which helps, but
"fails loudly on layout change" is weaker than "regenerated every time.")

---

## Branch E — Step 4's relationship to the existing conversion workflow

**E1. Is step 4 a new process, or the existing queue loop scoped per chapter?**
The described flow (match to native → try to decompose → surface irreducibles to
you) is, almost verbatim, the existing discipline: unhandled queue → readthrough
buckets → ≥2-occurrence + fork-verified idiom bar → hand conversion as last
resort (§4.7's both-directions rule).
- a) **Existing loop, chapter-scoped** — the chapter doc contributes ordering and
  behavioral context (what the event is *for*), nothing procedural changes
- b) New chapter-driven process that replaces the queue readthrough

➤ **Recommendation: a.** The queue loop just closed slice 1 to a single deferred
entry — it works. What the chapter doc genuinely adds is *intent*: the queue
shows an event is unhandled, the chapter doc says what the player-visible
behavior must be, which is exactly what's needed to judge "can this decompose
into native pieces." Frame step 4 as "read the chapter's slice of the queue with
the chapter doc open," not as new machinery.

**E2. Idiom-minting bar as scope widens?** Current bar: ≥2 occurrences *on the
slice* + fork-verified native analog.
- a) Keep per-slice/per-chapter counting
- b) **Count occurrences corpus-wide** (the unhandled jsonl already covers the
  corpus) — an idiom appearing once in this chapter but 40× across the game is
  worth minting now
- c) Also lower the bar to 1 occurrence if the native analog is exact

**Context, mild lean b:** corpus-wide counting is nearly free (the jsonl exists)
and front-loads transpiler work that later chapters would force anyway. The
counterargument is slice discipline: building for maps you can't yet boot-test is
speculative. (c) trades review burden for queue shrinkage — that's a taste call
about how much you trust the fork-index gate to catch bad mints.

**E3. Ordering: does the chapter test exist before or after conversion?**
- a) Test-first, strictly: write the chapter test from the doc, watch it fail,
  convert until green
- b) Convert-first, then write the test as verification
- c) **Interleaved per-beat, with late binding: scenario skeleton comes from the
  chapter doc, but flag/var IDs, coords, and species constants are resolved at
  runtime from the build's own artifacts (linker map, generated headers, registry
  state — the existing `offsets.py`/`symbols.py` pattern), never hardcoded**

➤ **Recommendation: c.** Pure test-first stalls on mechanics: the test needs a
booting ROM and registry-minted names to even express its assertions. The
non-negotiable part is late binding — a hardcoded flag number is a regression
bomb every time the registry renumbers, and the harness already solved this
correctly for `FLAG_SYS_B_DASH`.

---

## Branch F — The run loop and the failure protocol (step 5)

**F1. Who/what runs the loop?**
- a) **You invoke it: build agent runs the chapter suite in-session on demand
  (and before handing you any review ROM)**
- b) /loop-style self-pacing automation in a session
- c) Scheduled/cron cloud runs

➤ **Recommendation: a.** The suite runs in seconds-to-minutes headless, so
scheduling buys nothing, and (b)/(c) burn usage budget unattended — which
CLAUDE.md says to always ask about. A natural standing rule instead: **no ROM
gets taildropped for §9 review unless the chapter suite is green on that exact
build.** Revisit (b) only if suite wall-clock ever gets long enough that waiting
on it is the bottleneck.

**F2. "Look at the pokeemerald wiki" on repeat failure —**
- a) As drafted: consult the pokeemerald wiki after a second failure
- b) **Fork source first (per §4.7 — the fork on disk is the source of truth;
  grep costs seconds), decomp docs/wiki only as secondary color; Uranium wiki
  only for expected-*behavior* questions, via the 402 workarounds**

➤ **Recommendation: b — this one's essentially mandated.** The most expensive
recorded bug class in this repo came from trusting memory/external sources over
the fork (`healparty` vs `HealPlayerParty`). The wiki step in the draft inverts
§4.7.

**F3. Failure classification protocol?**
- a) Any failure → immediate agent investigation
- b) **Auto-rerun the failed chapter once; twice-failed = real, investigate
  (existing /debug workflow, fed by the failure artifacts); pass-on-rerun = flake,
  logged as a harness bug (C6), not a game bug**

➤ **Recommendation: b.** The known flake source is harness-side (body-blocking),
so a flake is still a bug — just in a different backlog. One rerun at these
speeds is cheap; investigating phantom failures is not. The "same event fails
across ≥2 *separate* runs" rule from your draft then triggers the deeper
protocol (F2) naturally.

---

## Branch G — Relationship to the §9 manual gate, and the unfinished sentence

**G1. "Eliminate the boot walk" vs the recorded "manual gate stays" decision —
which is it?**
- a) Automation fully replaces the manual walk (conflicts with the 2026-07-17
  decision and the feasibility doc's explicit non-goal: art legibility, palettes,
  animation jank are by-eye)
- b) **Automation eliminates *repeat* walks: everything previously walked is
  guarded by the chapter suite, so regression re-walks after fixes disappear; the
  *first* walk of new content, and all by-eye categories, stay §9 manual**
- c) Keep both in full (automation adds no relief)

➤ **Recommendation: b — and I'd argue that's what your draft already means.** The
boot-walks you're sick of are the re-walks after each fix round (Moki is on
retest round 3+). A green chapter suite makes each re-walk shrink to "the items
that changed + by-eye sweep," and the stamped review ROM already positions you at
the relevant state.

**G2. Split BOOT_WALK_CHECKLIST into automated vs by-eye?** Of the checklist's
check categories, roughly seven automate cleanly (boot/spawn identity, warp
destinations + post-warp facing, collision, one-time event/flag/var gating, story
chain sequencing, mechanic counts like rock-smash respawns, NPC presence), and
roughly six stay by-eye (art/layout legibility, palettes, animation cadence,
depth ordering, dialogue readability, audio).
- a) **Tag each checklist item `[auto]` / `[eye]`; the manual §9 walk becomes just
  the `[eye]` subset plus anything newly changed**
- b) Keep the checklist unified and untagged; automation coverage tracked
  separately

➤ **Recommendation: a.** It makes G1's bargain concrete and auditable — you can
see exactly what you're no longer re-checking by hand, and a checklist item with
no `[auto]` tag and no `[eye]` justification is a coverage gap staring at you.

**G3. The file's last line cuts off: "i want to set up the testing so when it …"
— complete it.** (Multi-select; these compose.)
- a) **…fails, it produces a self-contained repro bundle**: failure screenshot(s),
  state dump (map/pos/flags/vars), the failing beat name, and a stamped ROM
  positioned just before the failing beat — ready to hand to /debug or taildrop
  for by-eye confirmation
- b) **…passes, it auto-stamps the chapter-complete review ROM** (the thing you
  taildrop for §9) as the suite's green-side artifact
- c) …the ROM is rebuilt, the suite runs automatically (a build hook)

➤ **Recommendation: a + b.** They turn every suite run's *both* outcomes into the
artifact you'd want next, and (a) is the piece the current harness half-has
(screenshots exist; the state dump, beat context, and pre-failure stamp don't).
(c) is fine later but couples build time to suite time; with F1's "green before
taildrop" rule you get the discipline without the coupling.

---

## Cross-cutting notes (not questions, but they'd bite later)

- **The `.sav` gotcha is now a test-infrastructure hazard**: any ROM with a `.sav`
  beside it silently skips the new-game path (BOOT_WALK_CHECKLIST §8). The runner
  should always execute against a scratch copy in a temp dir (the stamper already
  does this) and probably *assert* it booted the path it expected — cheap
  insurance against certifying a "fresh run" that wasn't.
- **Exploration-chapter tours need the chapter doc to enumerate coverage
  targets** (every trainer, every item ball, every grass patch) — that enumeration
  comes from the converted map data, not the wiki, which is another point for A1:b.
- **`libmgba-py` is pinned to a third-party release URL with no checksum** — fine
  for now, but the moment the chapter suite becomes the gate for review ROMs, that
  dependency is load-bearing; worth a checksum in `fetch_libmgba.py` eventually.
- **Var-gated beats can't be asserted until C3 item 1 lands** — the Moki chain's
  own S-checks (VAR_QUEST_LOG 0→1→2→4) are the first thing the suite should
  encode, and they need `var()`. It's the single highest-leverage three-line
  change in this whole plan.

