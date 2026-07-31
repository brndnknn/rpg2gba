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
  **Correction (2026-07-24, from the E1 backfill):** that entry is **stale — it is
  already resolved natively.** `checkspecies` (`engine/asm/macros/event.inc:2541`)
  and `DoesPlayerPartyContainSpecies` (`engine/data/specials.inc:603`,
  `engine/src/field_specials.c:4939`) both exist, `SPECIES_RAPTORCH` was staged by
  the 2026-07-21 starter conversion, and `transpiler.py::_emit_has_species_idiom`
  already emits it (shape 6 in `tests/test_transpiler_native.py`). It should be
  bucketed `native`, not `hand`. This is the §4.7 failure mode a third time —
  which is precisely why E1's evidence field now exists.
- **Wiki**: ~~fandom.com returns HTTP 402 here (research goes through WebSearch
  snippets / mirrors)~~ **— CORRECTED 2026-07-30. The wiki IS fully readable.**
  `WebFetch` 402s on every `pokemon-uranium.fandom.com` URL (including `api.php`
  and `?action=raw`) and a bare `curl` gets a Cloudflare 403, but the MediaWiki
  API **with a browser User-Agent** returns 200. Use
  `python scripts/fetch_uranium_wiki.py <Page>`; pages land as raw wikitext in
  `output/uranium-build/wiki/`. This is what made the chapter atlas's
  walkthrough-derived act/chapter structure possible
  (`reference/chapters/00-atlas.md`). On the Moki chain alone the wiki had 3
  discrepancies vs the rxdata, and the corpus-wide pass found 8 more — the
  rxdata-first rule (A1:b) is unchanged and, if anything, better supported. `reference/findings/moki_slice_story_chain_2026-07-16.md` is already a
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

**Agreed**

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

**Agreed**

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

**Agreed**

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

**Agreed**

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

**Agreed**

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

**Answer** I think there's a case for B now. in slice one if you try to skip Theo's house and go straight to the catch tutorial the professor tells you to go get theo. and it's not like you can test that by going to the path where you get denied first. what if some how going and getting stopped is what flips the flag for example. I don't think completely random is the answer.

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

**Agreed**

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

**Agreed**

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

**Answer** I think you're missing somethings. what about the different tables of different encounters; grass, surfing, fishing, night vs day, and any others. I assume that things like the logic that handles encounter rates is baked into the engine and doesn't need to be tested? 

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

**Agreed** I want to avoid manual walking as much as possible. maybe it would be better to do a corpus review of text that may be hard to convert. I've seen some odd things I haven't reported yet. thinks like text wrapped in something that looked kinda like html tags like <br>some text blah,blah</br>. but overall I agree with the order 

**C4. Chapter scenario authoring format?**
- a) **Plain Python functions** (current pattern), one module per chapter, small
  shared helpers as they emerge
- b) A declarative step DSL (data-driven scenarios) interpreted by the harness

➤ **Recommendation: a.** One scenario exists; a DSL now is premature abstraction.
The chapter tests will *discover* the right abstractions (e.g., "beat" helpers) —
extract them after two or three chapters, per A4's same logic.

**Agreed**

**C5. Runner surface?**
- a) Everything through pytest (current `RPG2GBA_PLAYTEST=1` opt-in)
- b) **Standalone CLI for iteration (`python -m rpg2gba.playtest run --chapter
  moki [--from-beat N]`) + a thin pytest wrapper that runs the full chapter suite
  for gate/CI runs**
- c) CLI only

➤ **Recommendation: b.** The dev loop (step 5) wants chapter selection, verbose
progress, and artifact paths printed; pytest wants a binary green/red for "did
anything regress." They're different consumers of the same scenarios.

**Agreed**

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

**Agreed**

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

**Agreed**

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

**Agreed**

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

**Answer** I generally aggree, but a few corrections to what you said. first of all, not sure what you're talking about closed slice one but we're still working through it. and so far the queue loop has worked, but it's needed pushing from me to get the model to realize or admit? that there is pokeemerald analogs for what the event does. we need to really push the model toward attempting to find a behavior match. 

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

**Agreed** I would add that the bar should be much lower, not 40. maybe 2 over the whole corpus not just the slice.

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

**Agreed**

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

**Answer** actually id really like to get this automated. I would be happy not doing a ton of boot walks 

**F2. "Look at the pokeemerald wiki" on repeat failure —**
- a) As drafted: consult the pokeemerald wiki after a second failure
- b) **Fork source first (per §4.7 — the fork on disk is the source of truth;
  grep costs seconds), decomp docs/wiki only as secondary color; Uranium wiki
  only for expected-*behavior* questions, via the 402 workarounds**

➤ **Recommendation: b — this one's essentially mandated.** The most expensive
recorded bug class in this repo came from trusting memory/external sources over
the fork (`healparty` vs `HealPlayerParty`). The wiki step in the draft inverts
§4.7.

**Agreed**

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

**Agreed**

---

## Branch G — Relationship to the §9 manual gate, and the unfinished sentence

**Answer for the Section**

For this branch I think i want to just say I really want this to become a much more hands off project. the idea was always to set it up and let it go, but as the project has gone on it has felt more attention consuming, more down in the weeds. I have tried litterally dozens of ROMs and we haven't even completed the first town. we've got a good start, but there's still some issues. Including several cosmetic issues, things that if you logic out what's happening on screen you should be able to tell something is wrong. I want to use the rest of Moki town as a test on this strategy and the goal is for you to not give me another ROM until everything is finished and I can play the game on the rom and the PC side by side and only notice the cosmetic differences we had to adapt due to the tech of a GBA. 


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


---

# Response to your answers — 2026-07-23 (appended by build agent)

Structure: (0) a correction that has to come first, (1) per-answer feedback where
your answer changes the design, (2) the part of Branch G I'd push back on,
(3) the build order to finish slice 1.

---

## 0. Correction: day/night encounters ARE native. Our converter drops them.

In my C2 recommendation above I implied the fork has no day/night encounter slot.
That was wrong, and it was wrong the same way `healparty` was wrong — asserted from
memory instead of grepped (§4.7, §11). Verified against the vendored engine:

**The engine supports it, off by default, no custom C:**

| Thing | Where |
|---|---|
| `OW_TIME_OF_DAY_ENCOUNTERS` (default `FALSE`) | `engine/include/config/overworld.h:95` |
| `OW_TIME_OF_DAY_DISABLE_FALLBACK`, `OW_TIME_OF_DAY_FALLBACK` (default `TIME_MORNING`) | `overworld.h:96-97` |
| `enum TimeOfDay` = `TIME_MORNING/DAY/EVENING/NIGHT` | `engine/include/constants/rtc.h:98-105` |
| Hour boundaries, selected by `OW_TIMES_OF_DAY` (default `GEN_LATEST`) | `rtc.h:19-95` |
| Consumers | `src/wild_encounter.c`, `src/rtc.c`, `src/pokedex_area_screen.c` |

**The data mechanism** (`engine/tools/wild_encounters/wild_encounters_to_header.py:223-236`):
there is no `time` field in the JSON. You emit a **separate encounter entry per
time bucket** whose `base_label` carries the bucket name as a suffix
(`gWildMons_SomeMap_Night`); the generator strips the suffix, groups entries by the
stripped label, and emits one per-map header indexed by `TimeOfDay`. Empty buckets
fall back to `OW_TIME_OF_DAY_FALLBACK` unless `DISABLE_FALLBACK` is set. At
`OW_TIMES_OF_DAY == GEN_LATEST` the boundaries are morning 6-10, day 10-19,
evening 19-20, night 20-6 (`rtc.h:83-94`).

**What our converter does instead** (`src/rpg2gba/pbs_converter/encounters.py`):

- `:57` — `_LAND_SOURCES = (LAND, CAVE, LAND_DAY, LAND_MORNING, LAND_NIGHT)`;
  `:123` takes the *first present* as `land_mons`.
- `:146-156` — every other land table is shunted into `uranium_extra`, preserved
  but never emitted to the ROM.
- `:16` and `:190` — the docstring/note assert the fork "has no host" for
  Cave-vs-Land and time-of-day tables. **The time-of-day half of that claim is
  false and should be deleted, not softened.**

**Blast radius is tiny — this is a small fix, not a schema overhaul.** Tally over
`output/uranium-build/intermediate/wild_encounters.json`:

- 53 maps have encounter tables at all.
- **Exactly one map** (Uranium map id **22**) carries any `uranium_extra`: one
  `land_morning` (rate 25) and one `land_night`.
- **Zero** `cave`, `headbutt_low`, `headbutt_high`, or `bug_contest` tables exist
  anywhere in the corpus.

So Uranium uses time-of-day encounters on a single map, and the Cave/Headbutt/
BugContest "can't host" caveat is describing a problem the data doesn't have.

**Open decision for you (§10 — content fidelity, I'm not deciding this):**
Essentials gives us Morning / Day / Night; the engine wants four buckets including
**Evening**. Options: (a) fold Evening into Night (closest to Essentials' own
day-length semantics), (b) fold Evening into Day, (c) set `OW_TIMES_OF_DAY` to a
gen with no Evening bucket — `GEN_2` or `GEN_4` (`rtc.h:19-56`) — which is the
cleanest match to Essentials' three-bucket model but changes every other
time-of-day-sensitive system in the engine. My lean is **(c) with `GEN_4`** if
nothing else in the build depends on Evening, else (a).

**Second open decision:** turning `OW_TIME_OF_DAY_ENCOUNTERS` on for one map's
sake means every other map's single table becomes its fallback bucket. That's
correct behavior, but it's a global engine-config change — §10 "ask before
proceeding" territory, so flagging rather than doing.

**Testing implication:** asserting a night table needs RTC control from the
harness (write the RTC / clock state, then walk into grass). That's a real new
primitive, but it's needed for exactly one map on the whole corpus — so it lands
whenever map 22's slice comes up, not now. The static golden test covers the table
contents for all 53 maps today with no emulator at all.

---

## 1. Per-answer feedback

### B2 — permutations: you're right, and your own reasoning contains the fix

The Theo-skip case is real and (a) would have missed it. Adopting **(b) now**.

But note what you actually wrote: *"what if somehow going and getting stopped is
what flips the flag."* That is answerable **statically** from the rxdata — the
redirect event either writes a var or it doesn't. So derive the permutations from
the event data rather than from suspicion, which is the difference between (b) and
(c) in practice.

Concretely, the negative path becomes a **first-class beat in the chapter doc**,
not a random ordering:

> walk to the lab before Theo's house → assert redirect dialogue fires (field-lock
> cycle) → **assert the quest var is unchanged** → then perform the intended order

One extra branch in one scenario, fully deterministic, and it tests the thing
you're actually worried about: a gate that leaks progress. Randomized ordering
would probably never hit it, and when it did you couldn't reproduce it.

**Rule for the chapter doc:** every gate gets both a positive beat (satisfy it,
assert it opens) and, where the data shows a redirect/refusal page, a negative
beat (violate it, assert refusal *and* assert no state advanced).

### C2 — encounter tables: I missed the table taxonomy; the fix isn't symmetric

Splitting three ways rather than one:

1. **Table contents** — golden test over the converted JSON, exhaustive, no
   emulator. Every table type, all 53 maps, effectively free. This is where
   grass/water/rock-smash/fishing-tier coverage lives.
2. **Wiring** — one live encounter per *mechanic present in the slice*, not per
   table. Grass now; fishing when slice 2 hands over the old rod; rock smash
   already has the standing `new_game.c` grant.
3. **Time-of-day** — see §0. Converter bug first, RTC harness primitive much
   later, one map.

And confirming your instinct: **encounter rate logic is stock engine, don't test
it.** Same for step-counting and the repel/ability modifiers.

### C3 — text: your counter-proposal beats my item 5

A static corpus scan over converted text is better than VRAM tile-decoding on
every axis — exhaustive instead of sampled, no emulator, runs in seconds.

One amendment: make it a **converter-side validator that fails loud** (§4.5),
not a playtest. It should scan emitted strings for:

- unconverted Essentials markup — `\c[n]`, `\v[n]`, `\pn`, `\b`, `\r`
- the `<br>…</br>` construct you saw (see below)
- chars-per-line budget overflow against the message-box width
- characters outside the emerald charmap

That catches the whole corpus at conversion time instead of at boot time, which is
strictly earlier and cheaper than either alternative.

**Please dump the odd text you've seen somewhere I can read it.** `<br>...</br>`
is *not* standard Essentials markup — no Essentials text tag uses closing-tag
syntax. That means it's either Uranium-specific (a custom message handler in their
scripts) or it's literal text an author typed. Either way the transpiler is almost
certainly passing it through verbatim into the ROM right now, so it will render as
the literal characters `<br>` in a dialogue box. Worth checking before it shows up
in a boot walk.

### E1 — correction accepted, and the real point is fixable mechanically

Taking the correction: slice 1 is not closed, it has one deferred queue entry,
which is not the same thing.

Your substantive point — *the model needs pushing to admit a pokeemerald analog
exists* — is the important one, and exhortation won't fix it. Neither will another
paragraph in CLAUDE.md; §4.7 already says exactly this and it still happened
(twice: `healparty`, and §0 of this very document).

**Proposed mechanical fix: search evidence becomes a required field.** No queue
entry may be bucketed `hand` until it records:

- the greps actually run against `$RPG2GBA_POKEEMERALD`
- what each returned
- which behavior decomposition was attempted and why it failed

An entry that reaches `hand` with an empty evidence field is a **schema
violation**, not a judgment call — it fails loud like everything else. That turns
"the agent should look harder" into a field that is visibly blank when the agent
didn't. `healparty` and the day/night claim would both have been caught by an
empty box.

### E2 — agreed, and the number is yours

Bar = **2 occurrences corpus-wide**, not 40, not per-slice. The jsonl already spans
the corpus so counting is free.

### F1 — automation is reconcilable, but sequencing matters

Running the suite unattended is fine and cheap — it's headless and fast. The thing
that costs budget is the **fix** loop, and an unattended fix loop is only safe once
a failure is legible without you in the room. That needs F3's flake classification
and G3(a)'s repro bundle to exist first.

With those, a loop iteration has a bounded job ("suite red on beat 7, bundle
attached, fix it"). Without them, it has an open-ended one, and it will spend the
night flailing at `walk_to` body-block flakes and bill you for it.

**So: yes to automation, but it's step 5 of the build order below, not step 1.**

---

## 2. Branch G — where I'd push back

Your Branch G answer is a blanket "make this hands-off; no more ROMs until it's
finished." Taking that as your call and building toward it. One honest objection
first, because it's structural rather than a preference:

**A green suite cannot tell you it's finished.** The issues you're describing —
cosmetic, *"things that if you logic out what's happening on screen you should be
able to tell something is wrong"* — are precisely the class that flag/var/position
assertions cannot see. If a green suite is the only gate, the loop terminates
satisfied while a sprite is drawn behind a wall and a palette is wrong.

The way out isn't more manual walking. It's **making the by-eye pass cheap instead
of interactive**:

> The harness drives to N waypoints per chapter and dumps PNGs into a contact
> sheet. You review 40 images on your phone in a minute instead of playing for
> thirty. Same coverage of the by-eye categories, none of the boot-walk tedium.

Two properties make this better than either extreme. It scales — adding chapters
adds images, not play sessions. And **I can look at the screenshots too**, which is
the only mechanism in this whole plan that catches "logic out what's on screen."
That's a genuinely different capability from asserting state.

**Proposed reading of Branch G:** automation replaces the *walk*, screenshots
replace the *watching*, and you stay the final yes/no on a contact sheet rather
than a controller. G1 → **(b)**, achieved via a mechanism the original (b) didn't
have. G2 → **(a)**, and the `[eye]` items become the waypoint list. G3 → **a + b**,
unanswered above, recommending both.

**Agreed**

---

## 3. Build order to finish slice 1

> **Progress log** (update this as items land; a future agent picks up from here)
>
> | # | Item | Status |
> |---|---|---|
> | 1 | `var()` accessor | **done** — `Emulator.var()` in `playtest/emulator.py`, `vars_start` probed in `offsets.py`, tests in `tests/test_playtest.py` |
> | 2 | Chapter doc for Moki | **done** — `reference/chapters/01-moki.md` |
> | 3 | Battle mini-driver | **done** — `playtest/battle.py`: `in_battle`, `read_enemy_party`, `zero_enemy_hp`, `win_battle`; new struct offsets in `offsets.py`; `u16`/`write_u16` on `Emulator` |
> | 4 | Chapter scenario | **done** — `playtest/chapters/moki.py`, 18 beats (B1–B15 + N1–N3 interleaved; N2 sits after B10 because it needs the player back outside). All symbols late-bound; map identity via `MAP_GROUP`/`MAP_NUM`. **Two live-run TODOs:** `THEO_LAB_INTERACT = (13, 9)` collision unverified, and the B13/N2 ceremony-tile doc/data discrepancy (doc says (16,43), `Map032.json` says (16,42) — annotated in the chapter doc) |
> | 5 | Failure bundle + green stamp | **done** — `playtest/runner.py` (`run_chapter` → `ChapterRunResult`, verdict `pass`/`flake`/`fail`), `playtest/__main__.py` CLI (`run --chapter … [--from-beat …]`, `list`). Artifacts under `output/playtest/`: `bundles/<chapter>/<ts>/` (failure.json, state_dump.json, pre_beat.gba, screenshots/), `review/<chapter>-complete.gba`, `flake_log.jsonl`, `blobs/` with sha256 ROM-provenance refusal |
> | 6 | Screenshot contact sheet | **done** — `playtest/contact_sheet.py` (`Waypoint`, `build_contact_sheet`, paginated PNG grid, 3 cols @2x, 12/page) + `Emulator.waypoint(beat, name, note, failed)`. The runner captures a waypoint at boot and at every beat boundary (and at the failing beat, captioned red), then renders the sheet on **both** outcomes: green → `output/playtest/review/<chapter>-sheet.png` beside the review ROM, red → inside the repro bundle, ending on the failing frame. Beats can add their own mid-beat waypoints. `ChapterRunResult.contact_sheet` + CLI prints the paths |
> | 7 | `walk_to` step-aside retry | **done** — perpendicular single-step sidestep + re-path, `max_sidesteps=8`, visited-tile preference, post-sidestep `map_location()` guard; three distinct failure messages (step-aside exhausted / sidestep changed map / budget exhausted) |
> | P1 | Text corpus validator (C3) | **done (standalone; not yet wired as a gate)** — `src/rpg2gba/text_validator/`, 4 rules (markup / DrawTextEx angle-bracket tags / pixel line-width vs the real 216px box + `FONT_NORMAL` glyph widths / charmap). CLI: `python -m rpg2gba.text_validator scan`. Findings: `reference/findings/text_corpus_scan_2026-07-24.md`. **Live bug found:** Map050 aptitude-test dialogue carries literal `<b>`/`</b>`/`<c2=…>` into the ROM. **GATE WIRED 2026-07-25** — `TextGate`/`TextGateViolation` (per-script rather than per-corpus, so a slice build isn't failed by the 191 maps it doesn't stage) called from `run_fork_pass` next to the fork-index gate, for every staged map + CommonEvents. Both live defects fixed to land it green: the whole DrawTextEx tag family is now stripped in `deterministic.py` (`_DRAWTEXTEX_TAG_RE`; `<br>`→`\n`) — previously only `<fs=n>` was — the hand-authored `Map050_EV005.pory` had its 8 `<b>` tags removed by hand (it bypasses the transpiler), and the 232px `strip_list.json` network stub was shortened to 179px |
> | P2 | Encounter time-of-day fix (§0) | blocked on user decisions (Evening bucket, global engine config) |
> | P3 | Queue evidence field (E1) | **done** — `conversion_agent/queue_evidence.py`: `GrepRecord`/`SearchEvidence`/`QueueEntry`, `enforce_hand_evidence` on both save and per-line load, `legacy_unaudited` escape hatch that warns instead of raising. Ledger: `queue_evidence.LEDGER_PATH` → `reference/findings/hand_bucket_queue.jsonl`. **GATE WIRED 2026-07-25** — enforced in `hand_overrides.load_hand_overrides`, which is where a hand conversion actually enters the pipeline: writing a file into `hand_conversions/` *is* the act of bucketing an event `hand`, so every override must have a matching evidence-carrying `hand` entry or the load fails loud. Backfilled the two unjustified overrides: **Map050/EV005** (aptitude test) with real evidence — the Lilycove Quiz Lady specials are the only native quiz analog and are single-question/single-answer with their own SaveBlock state, while `multichoice`/`givemon`/`compare` (the primitives it actually uses) are all native, so it is irreducible by *shape* (§4.1 branch-heavy), not by capability; **Map050/EV019** (Theo battle) as `legacy_unaudited` because it is **pending retirement** — the canlose idiom landed in `d3d57af8` and the native `trainerbattle_earlyrival` analog exists, so writing `hand` evidence for it would be false |
>
> **First end-to-end run (2026-07-24, `python -m rpg2gba.playtest run --chapter moki
> --engine engine`):** the whole loop works — B1 failed, the runner reran once, classified
> `fail` (not a flake), and wrote a complete bundle
> (`output/playtest/bundles/moki/20260724T225057071539Z/`: failure.json, state_dump.json,
> pre_beat.gba, screenshot). **The failure is not a game bug:** `engine/src/new_game.c:166`
> still carries the S6b post-quiz repro harness spawn override
> (`MAP_MOKI_TOWN_PROFESSOR_LAB` @ 14,8, active since 2026-07-22) instead of the normal
> `MAP_MOKI_TOWN_PLAYERS_HOUSE_1F` @ 7,7 spawn — the vanilla-spawn call is kept commented
> at line 160. B1 correctly caught it.
>
> **Blocker for the first meaningful suite run:** swap that override back and rebuild
> (`make modern`). The ROM at `engine/pokeemerald.gba` also predates the 2026-07-23/24
> transpiler changes, so a rebuild is needed regardless. Both are user decisions
> (CLAUDE.md §10: engine changes + long-running builds).
>
> **Framework note (lead-authored, item 4/5 contract):** `src/rpg2gba/playtest/chapter.py`
> defines `Beat` / `Chapter` / `ChapterBuilder` / `load_chapter(name)`; one module per
> chapter under `playtest/chapters/`, each exposing a module-level `CHAPTER`. Beat ids
> match the chapter doc's table rows (`B1`…`B15`, `N1`…`N3`) so a failure names a doc row.

1. **`var()` accessor** — ~3 lines in `emulator.py`, offset already probed.
   Unblocks the Moki chain's `VAR_QUEST_LOG` 0→1→2→4 beats, which is most of what
   the chapter asserts.
2. **Chapter doc for the rest of Moki** — promote
   `reference/findings/moki_slice_story_chain_2026-07-16.md` to
   `reference/chapters/01-moki.md`, rxdata-first, wiki as cross-check, with B2's
   negative-path beats added per the rule above.
3. **Battle mini-driver** — moved *ahead* of `walk_to` hardening: the Theo and
   can-lose trainer battles are on slice 1's critical path (recent commits), so
   C1(b) is needed now rather than at slice 2. Needs `gEnemyParty` read + enemy-HP
   write + in-battle detection.
4. **Chapter scenario** — plain Python (C4a), beat-tagged, all symbols late-bound
   (E3c), never a hardcoded flag number.
5. **Failure bundle + green stamp** (G3 a+b) — the prerequisite for any unattended
   loop, per F1 above.
6. **Screenshot contact sheet** (§2) — ~80 lines on top of the existing screenshot
   code.
7. **`walk_to` step-aside retry** (C6a); single auto-rerun as the stopgap until
   then.

**Parallel, independent of all of the above:**

- **Text corpus validator** (C3) — no emulator, no harness dependency.
- **Encounter time-of-day converter fix** (§0) — blocked only on your two
  decisions there (Evening bucket, global engine config).
- **Queue evidence field** (E1) — schema change plus a backfill of the one live
  slice-1 entry.

Items 1 and 2 have no open design questions in them and are the natural start.
