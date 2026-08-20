# Playtest Authoring — Findings and Open Questions

**Status:** pre-decision working document. Written 2026-08-20, before CH04 (Route 2) scenario work starts.
**Goal being pursued:** be able to say "write the CH04 scenario" and get a beat list that (a) covers every
event in the chapter, (b) knows what the player can and cannot do at that point in the playthrough, and
(c) asserts the real effect of each event rather than a proxy for it.

Sources: git history of `src/rpg2gba/playtest/chapters/{moki,route1,kevlar}.py` and the framework under
`src/rpg2gba/playtest/`; `reference/archive/CH02_TODO.md`, `reference/archive/CH03_TODO.md`;
`reference/chapters/*.md`; `reference/chapters.json`; `chapter_atlas/census.py`.

---

## Part 1 — What actually happened in CH01–CH03

### 1.1 Beat counts

| Chapter | Approved at authoring | Registered at gate pass |
|---|---|---|
| CH01 moki | 18 (B1–B15, N1–N3) | 17 (N1 dropped as a duplicate of B2, `d5b56bc1`) |
| CH02 route1 | 29 incl. 9 deferred/unregistered | 29/29, green first attempt |
| CH03 kevlar | 35 (25 positive + 6 negative + 4 deferred), user-approved 2026-08-12 before build work | 60/60 (`e1c5200f`, stamp ROM `c3e75d4f`) |

CH03 nearly doubled between approval and gate. That growth is the thing to explain: it was not scope
creep, it was omission discovered late.

### 1.2 Failure taxonomy

Seven distinct classes, each with real instances. These are the things a better authoring process has
to prevent.

**A. Coverage omission — events nobody enumerated.**
CH03 gained B26 (the PC, `09ba551f`) and B27–B33 (warp-arrival facing and BGM, `7a2909b0`) after the
approved list. The facing/BGM defect classes had been *reasoned about* in prose and never asserted
against a running ROM. Nothing mechanical existed to say "this map has a PC event and no beat touches
it." `reference/chapters/03-kevlar-town.md` §4 does carry a coverage reconciliation against census
totals — but by hand, in prose, and the doc's own §3 table has already drifted from `kevlar.py`.

**B. Proxy oracle — asserting the wrong thing, in a way that cannot fail.**
The flagship: `e1c5200f`. B5/B7/N1/B14 verified item grants by checking the self-switch the grant script
also sets. The commit's own words: *"the flag is set by the same script whether or not `giveitem` was
ever emitted."* Three dead item grants survived two boot walks behind that. The fix moved the assertion
onto `bag_item_quantity` — B5 exact count, B7 a **delta** (the Mart also stocks Antidotes, so a total
would be ambiguous), B14 all four berries checked separately.

**C. Design misread — compiled output read as evidence about intent.**
Named explicitly in `5422a599`: *"compiled output read as evidence about the design, without checking
the Essentials source or the wiki."* Instances: the Magikarp gift beats B17/N2 were written **backwards**
(`631c3aa7`) against pre-fix output where a staging bug suppressed `givemon`; the real design is a
100-refusal counter. B19–B24 were nearly filed as build defects before being recognized as correct
Strength gating (`5422a599`). RGSS switch polarity was inverted in prose (`2f676ab1`, code-121 uses
`0=ON, 1=OFF`) and mislabeled a live sidequest as dead content.

**D. No capability model.**
Nothing in the repo records what the player holds entering chapter N. `reference/chapters.json` has
`id, act, title, wiki_page, visit, outdoor, maps[], predecessor, tier, status, notes` — no HMs, badges,
items, or flags-true. `flag_registry.py` is a naming registry only. The atlas admits it: §7.3,
*"`gate_in` is null for every chapter."* Every gate decision (Strength, Rock Smash, the bike) was
re-derived by hand-grepping the corpus. Deferrals were right in the end, but each one cost a
mis-diagnosis first.

**E. Harness-shape traps that hid failures.**
- CH03 B13–B18 and B25 **had never actually run** — B11 hung ahead of them and masked seven latent
  geometry bugs at once (`e0d1a4cf`, `db586a92`).
- B8 carried a hardcoded `MAWULI_APPROACH (3,16)` that was never reachable and never noticed, because
  the beat routed through a helper computing its own live position (`5a1b823f`).
- `gObjectEvents` is camera-bound; reading an NPC from across the map raises or lies. **This bit twice** —
  route1 N2 (`a3027496`) and kevlar B17 — before "walk first, then look" was written down anywhere.
- Registration order **is** playthrough order; beat ids are labels. B27–B33 were appended at the end
  instead of beside the beats producing their preconditions, costing a red run (`0f46cb2e`). The
  convention lived only in code until that commit.

**F. Retroactive invalidation — old gates that passed under a bug.**
CH03 #15: everything after a `warp` command was silently dead (RMXP continues past Transfer Player;
pokeemerald halts the script). **CH01 and CH02 both passed §9 with that bug live** — their beats simply
never asserted a post-warp state write. Same shape as CH03 #22: `compute_arrival_facings` had been
skipping `dest_dir==0` since 2026-07-16, undetected through two chapter gates. When a new assertion
class is invented, prior chapters are stale, and nothing currently forces a re-check.

**G. Blind spots the harness cannot express at all.**
No dialogue **text-content** assertion (only "is text drawing"). No party HP/moveset/stats assertion, no
PC-box read. No bag-write seeding primitive. No cursor navigation into mart/box menus (`use_pc` only
exercises the cancel arm). Route planner is 4-neighbour, so sideways-staircase tiles must be stepped by
hand, and elevation is unmodeled — an elevation mismatch presents as an ordinary stuck walk. No
double-battle support. Contact sheets do not automatically capture the frame where a choreography bug
would be visible; the author must remember `mark_frame()`.

**H. Primitives are born chapter-local, so prior chapters can never inherit them.**
This is the mechanism *underneath* finding F, and it was not visible until the harness was inventoried.
Every good assertion helper lives as a private function inside whichever chapter invented it:
`_expected_arrival_facing`, `_assert_player_facing`, and `_assert_near` are all in `kevlar.py`;
`_party_has_magikarp` is in `kevlar.py` while `_player_starter_species` is a near-duplicate in `moki.py`.
`route1.py` has none of the facing helpers — which is exactly why CH01 and CH02 are stale against the
facing class. The assertion class was not merely "invented late"; it was invented *in a place structurally
unreachable by the chapters already written*. A defect-class ledger (Q7b) treats the symptom. The rule that
treats the cause: **an assertion helper that generalizes is promoted into the framework as part of the
inventing chapter's gate**, after which re-verifying prior chapters is mechanical rather than a research
project.

### 1.3 What already works and should not be disturbed

- Approve-the-beat-list-before-build ordering (CH02 onward) — the user's explicit directive, and it is
  the reason CH03's scenario drove the build rather than rubber-stamping it.
- `ChapterBuilder(predecessor=…)` chaining: every chapter replays its ancestors from a new game at gate
  time, so regressions in early chapters surface immediately.
- Blob seeding (`--from-beat`) for iteration; full replay for the gate. Same-build-only by design.
- Flake classification (run, rerun once, classify pass/flake/fail) keeps harness noise out of game bugs.
- Event enumeration is already solid and mechanical: `output/uranium-build/maps/Map###.json` carries
  every event, page, condition, and command; `chapter_atlas/census.py::_census_one_map` already walks it.

### 1.4 The one-line diagnosis

> **Every failure class in this document is the same shape: an omission that no artifact made visible.**
> Events nobody enumerated (A). Assertions that could not fail (B). Beats that never ran (E). Deferrals with
> no owner (§4.4). Assertion classes invented with nothing marking prior chapters stale (F, H). A gate tally
> nothing generates (§5.8).
>
> That is also the **test for every proposed fix**: *does this make an omission visible, or does it rely on
> someone remembering?* The decisions that survived scrutiny in this session all pass it — required
> dispositions, content hashes, generated lag reports, `NOT_RUN` status, unrecognized-head vetoes. The ones
> that had to be corrected all failed it — proxy oracles, hand-maintained ledgers, author-judgment triggers.


Event data is mechanically available; beat lists are hand-written prose. The gap between those two is
where every omission lived. Player capability is not modeled anywhere, so every gate call is re-derived
by grep. And assertion quality is a matter of author discipline with no rule saying what counts as a
valid oracle.

---

## Part 2 — Questions

Each has context, options, and a recommendation where I have one. These are the grill topics.

### Q1. Should the beat list be *generated* from a per-event manifest, or stay hand-authored?

> **DECIDED 2026-08-20 — (a) generated manifest, disposition required.** A build step emits every
> event/page on the chapter's maps; the author must mark each row `beat:Bn` / `deferred:<reason>` /
> `cosmetic` / `unreachable:<reason>`. The checker fails the chapter if any row is undispositioned or
> names a beat that does not exist. Manifest generator + checker get built before CH04 authoring starts.
>
> **AMENDED 2026-08-20 — the manifest is generated from the RMXP side, never the compiled side.**
> Source is `output/uranium-build/maps/Map###.json` (deserialized rxdata). If it were generated from the
> emitted Poryscript, an event the transpiler silently dropped would be absent from both the manifest and
> the ROM — which is precisely the shape of CH03's three dead `giveitem`s (`e1c5200f`). Generating from
> RMXP means a dropped event still produces an undispositioned row and fails the chapter.
>
> **Second, free check enabled by the same artifact:** `output/uranium-build/transpile_unhandled.jsonl`
> already carries `(map_id, event_id, page, line, command_code)` per `QueueEntry` — page granularity, an
> exact join key against manifest rows. Rule: **a page with unhandled queue entries may not be
> dispositioned `cosmetic`.** This catches dead conversions with no beat written at all.


Today a scenario is prose → Python, with a manual census reconciliation. The map JSON already lets us
enumerate every event/page/command on a chapter's maps.

- **(a) Generate a per-event manifest, require an explicit disposition for every row.** A build step
  emits every event on the chapter's maps; the author must mark each `beat:Bn` / `deferred:<reason>` /
  `cosmetic` / `unreachable:<reason>`. A checker fails if any row is undispositioned or points at a
  beat that does not exist. **Recommended** — this is the only option that structurally prevents class A.
- **(b) Keep prose, add a coverage script that reports uncovered events as a warning.** Cheaper, but
  advisory; the CH03 doc already drifted from `kevlar.py` under exactly this regime.
- **(c) Status quo plus a stronger checklist in the chapter-doc template.** Lowest cost, no structural
  guarantee.

### Q2. What granularity does "every event" mean — event, page, or command?

> **DECIDED 2026-08-20 — (a) one row per page.** Schema:
> `(map_id, event_id, event_name, page_idx, condition{sw1,sw2,var,selfsw}, trigger, effects[], disposition)`,
> where `effects[]` is derived tags: `giveitem, givemon, trainerbattle, warp, switch_write, var_write,
> shop, heal, pc, text`. Idiom-collapse was *not* adopted here — if route-scale noise becomes a problem it
> is handled at the assertion level (Q11), not by dropping rows.
>
> **AMENDED 2026-08-20 — three corrections.**
>
> **(i) The generator never filters.** The original prose said "every page whose condition is satisfiable
> in this chapter needs a disposition," which puts a satisfiability judgment inside a script where no
> reviewer sees it — class A omission, relocated. The generator emits **every page of every event on every
> map in the chapter**, unconditionally. `unreachable:<reason>` is an *author* disposition, written by a
> human and visible at review. Operator's rule, verbatim: *"there shouldn't be anything that could possibly
> happen in the map that the chapter is on ... that doesn't get looked at."*
>
> **(ii) The tag vocabulary cannot be derived from RGSS command codes.** Verified against the corpus:
> `giveitem`, `givemon`, `trainerbattle`, `shop`, `heal`, and `pc` **do not exist as numeric codes**. They
> are embedded Ruby inside code-355/655 `Script` commands, or inside a code-111 conditional whose
> `params[0] == 12` (script-typed condition). `census.py` states it outright: *there is not a single
> code-301 (Battle Processing) command in the corpus* — every trainer battle is a type-12 branch wrapping
> `pbTrainerBattle(...)`. So the extractor has two halves:
>   - **numeric dispatch** — 201 warp, 121 switch, 122 var, 123 self-switch, 209/509/210 move route,
>     241/242 BGM, 249 ME, 250 SE, 101/401 text, 102/402/403/404 choices, 111/411/412 branch, 314 recover,
>     125 gold, 117 common event;
>   - **Ruby script-head recognition** — `MECHANIC_BY_HEAD` in `chapter_atlas/census.py`
>     (`pbTrainerBattle`, `pbDoubleTrainerBattle`, `pbWildBattle`, `pbReceiveItem`, `pbItemBall`,
>     `pbPokemonMart`, `pbPokemonBerryMart`, `pbHealAll`, `pbPokeCenterPC`, `pbTrainerPC`, …).
>
> **(iii) Unrecognized input is undispositionable, not untagged.** Script-head recognition is open-ended: a
> novel `pbSomething` absent from `MECHANIC_BY_HEAD` would produce an untagged row that reads as cosmetic
> and gets waved through — the class A hole reopening one level down. Same for command codes:
> `_census_one_map` recognizes only **10 of the 59 codes in use** and has no fallback bucket, so 49 codes
> are invisible to it today. Therefore the manifest carries **every script head verbatim** and an
> **`other_codes[]`** bucket, and **a row containing an unrecognized head or code cannot be dispositioned
> until a human classifies it.** Fail loud (CLAUDE.md §4.5), do not default to cosmetic.
>
> **Tags added beyond the original list:** `move_route`, `bgm`, `se`, `money`, `wild_battle` (distinct from
> `trainerbattle`), `common_event`. Rationale: CH03's own late growth (B27–B33) was warp-arrival **facing**
> and **BGM**. The original vocabulary had no `move_route` and no `bgm`, so it would not have prompted the
> very beats whose omission motivated this document.


Uranium events are multi-page with switch/var/self-switch conditions. Covering "the event" can silently
mean covering only page 0.

- **(a) Per *page*.** Every page whose condition is satisfiable in this chapter needs a disposition. Catches
  the "second page never fires" class. **Recommended.**
- **(b) Per event.** Cheaper, but page-2 content (post-flag dialogue, rematches) hides.
- **(c) Per *effectful command*** (`giveitem`, `givemon`, switch writes, warps, battles) — dialogue-only
  pages auto-dispositioned as cosmetic. Sharpest signal-to-noise; risks auto-dismissing a page whose only
  job is a text change that matters.

### Q3. How should player capability be modeled?

> **OPERATOR DIRECTIVE 2026-08-20 — capability is a timeline *inside* the chapter, not a boundary value.**
> The question as originally written ("at a chapter boundary") is wrong. If CH-N is the chapter that grants
> Strength, then Strength-gated content **on CH-N's own maps is not deferrable** — a beat *after* the
> granting beat must actually exercise it, on that map, in that chapter. Operator, verbatim: *"if in chapter
> 3 we say that that was the chapter where we gained the ability to use strength, I would want a beat after
> that point to go and check and make sure that we can use strength as a part of that chapter since we're
> already on that map."*
>
> Consequences:
> - The capability model must be keyed to a **beat index**, not a chapter id — `Strength granted at B18` —
>   so a checker can ask "does some beat with index > 18 exercise it?"
> - **Deferral becomes a computed status, not an author's note.** A row is legitimately deferrable only if
>   the capability it needs is held at *no* point in this chapter. If the chapter grants it, deferring is a
>   bug the checker must catch.
> - This merges Q8 into Q3: un-deferral triggers at a *beat*, not at a chapter.

Nothing models this today (finding D).

- **(a) Declarative `capabilities` block per chapter in `chapters.json`** — HMs, key items, badges,
  flags-true, party expectations — hand-maintained, machine-readable, and used both to justify deferrals
  and to fail loud if a beat assumes something not yet granted. **Recommended**, with the entry-state
  derived from the predecessor's exit-state so the chain stays consistent.
- **(b) Derive it empirically from the predecessor chapter's green seed blob** — read the actual save
  state at chapter end (bag, flags, party) and treat that as ground truth. More honest, zero
  hand-maintenance drift, but only available *after* the predecessor is green, and opaque to read.
- **(c) Both: (b) generates, (a) is the reviewed/committed artifact, checker diffs them.** More machinery;
  probably the right end state, question is whether it is worth it now.

### Q4. What is the rule for a valid oracle?

> **DECIDED 2026-08-20 — (a) + (b), plus three standing assertions that are never an author judgment call.**
> Assert the observable effect, never the flag the same script also writes; use a before/after **delta** for
> anything countable. On top of that rule, the following are *unconditional* — any manifest row carrying the
> tag requires the assertion, with no "obviously fine" arm:
>
> 1. **`warp` → destination map + coords + arrival facing, every time.** Facing is not optional and not
>    sampled. Cheap to adopt: `kevlar.py::_expected_arrival_facing` already derives the expectation from
>    this build's own `compute_arrival_facings` output rather than a literal, so a converter regression
>    fails the beat instead of silently passing. Promote it to the framework (finding H).
> 2. **`text` → see the split below.** (Originally written as "assert the string on every `text` row";
>    **REVISED 2026-08-20** — applied literally that makes every ambient NPC a beat and is unaffordable at
>    route scale. Map 32 alone carries ~41 `pbCallBub` dialogue rows.)
>
>    **"Did this string convert correctly?" is a STATIC check, not a beat.** Compare the RMXP source string
>    against the string emitted into the `.pory` output, offline, for **every** text row in the corpus. No
>    ROM, no walking, no beat. This covers all 41 map-32 dialogue rows and every corpus equivalent at
>    essentially zero marginal cost, and it is where the operator's "make sure the text is converting
>    correctly" requirement is actually satisfied — as a **converter test**, not a playtest burden.
>
>    **"Which of several possible strings did the player get?" is a RUNTIME assertion**, needed only where
>    text distinguishes branches: multi-page NPCs, choice arms — the "multiple different responses" case.
>    The runtime text primitive (§4.1) is still required, but its scope is exactly that case, not every
>    dialogue row.
> 3. **HM/field-move gating → prove usability, never assume it.** Do not write "deferred, Strength-gated"
>    without establishing the player cannot use Strength at that point in *this* chapter (Q3).

Finding B. Today nothing forbids a proxy assertion.

- **(a) Hard rule: assert the observable *effect*, never the flag the same script also writes.** Item →
  bag count. Mon → party. Money → money. Warp → map+coords. A flag assertion is valid only when the
  flag *is* the deliverable (a gate the player later feels). **Recommended.**
- **(b) Rule plus mandatory before/after delta** for anything countable, since a total can be satisfied by
  an unrelated source (the B7 Antidote case).
- **(c) Advisory guidance in the authoring doc.**

Sub-question: should the checker be able to *detect* proxy assertions mechanically (e.g. flag-only
assertion on an event whose manifest row contains `giveitem`), or is this review-only?

### Q5. How do we prevent design misreads (finding C)?

> **DECIDED 2026-08-20 — (a) with a mechanical trigger and a checker-enforced field, plus a targeted (c)
> pass on CH04–CH05 run as a measured experiment.**
>
> **Most of Q5's scope is already absorbed by earlier decisions.** Finding C's three instances have three
> different causes, and only one survives:
> - *RGSS switch polarity inverted in prose* (`2f676ab1`, code-121 `0=ON`) is a **decoding** problem, not a
>   citation problem. The manifest renders conditions in human terms ("self-switch A is ON"), never raw
>   values, and the misread becomes impossible rather than discouraged.
> - *B19–B24 nearly filed as build defects* is covered by **Q3**: if the capability model says Strength is
>   not held, gated content behaving as gated is the expected result, not a defect.
> - *The Magikarp gift written backwards* (a 100-refusal counter, authored against pre-fix compiled output)
>   is the **residue**. Neither the manifest nor the capability model catches it, because the manifest
>   carries structure and this is semantics.
>
> **The trigger is mechanical, not a judgment call.** Option (b) — "cite only when the effect is
> non-obvious" — fails by construction: the author who misreads a design is the author who believes it is
> obvious. Instead:
>
> > A beat requires a source citation when its manifest row contains an **unrecognized script head** or a
> > **script-typed conditional** (code-111 with `params[0] == 12`).
>
> These are exactly the rows whose behavior lives in Ruby rather than in structure, and both are already
> computed for Q2(iii). Everything whose effect the manifest fully determines — item grant, warp, switch
> write — owes nothing. The trigger fires on Magikarp; it does not fire on map 32's ~41 plain `pbCallBub`
> dialogue rows, which is what keeps it affordable at route scale.
>
> **Enforcement: a `source:` column on the manifest row, checker-enforced.** It must be non-empty whenever
> the trigger fires. Content is the RMXP path (already in the row) plus the Essentials script or the wiki
> page; the `pokemon-uranium-wiki` skill is the sanctioned wiki source. A docstring convention was rejected
> because it can drift and the manifest cannot.

#### Q5.1 The targeted verification pass, run as a measured experiment

A blanket second-agent pass (option c) is too expensive to adopt blind. It runs **only over rows the
citation trigger flags** — a handful of rows out of 90 on a map-32-sized map — and on **CH04 and CH05 only**,
as an experiment with its result recorded before it is made standing policy.

**Methodological requirement: the verifier works blind.** It must derive the expected effect independently
from the Essentials source and wiki, *without seeing the author's expected effect*, and only then diff.
A verifier shown the author's answer measures agreement, not correctness, and will anchor.

**Benefit is not "disagreements found."** A misread that makes a beat *fail* at gate time costs one debug
cycle. A misread that makes a beat *pass while asserting the wrong thing* is the CH03 dead-grant shape — it
survives boot walks and surfaces chapters later. Only the second class justifies a standing pass, so the
metric must separate them:

> When the pass catches a disagreement, **retain the author's original assertion as a recorded artifact.**
> After the CH04 ROM is built, run that original assertion against it.
> - **Passes** → *silent-pass class*. The gate would never have caught it. This is the money metric.
> - **Fails** → the gate would have caught it anyway. Real but low value: a saved debug cycle, not a
>   prevented defect.

Cost of the measurement is one extra beat execution per catch.

**Ledger (JSONL, accumulating across chapters):** per flagged row — `map_id, event_id, page_idx,
trigger_reason, author_expected, verifier_expected, agreed(bool), adjudication ∈
{author_wrong, verifier_wrong, escalated}, original_assertion, replay_result ∈ {passed, failed, n/a}`.

**Cost metrics:** trigger selectivity (flagged ÷ total rows — if it flags most of a map it is not targeted),
verifier token/wall-clock cost, and count of disagreements requiring operator adjudication.

**Decision rule, fixed in advance** (deliberately, so the threshold is not chosen after seeing the numbers):
run on CH04 **and** CH05 — one single-map chapter is too weak a sample to settle it either way. Keep the pass
if it catches **at least one silent-pass case** across the two. Abandon it if silent-pass count is zero while
false positives are consuming operator time. Re-evaluate cumulatively, not per chapter.


- **(a) Require a source citation per beat** — the RMXP event JSON path plus either the Essentials script
  or the wiki page — recorded in the beat's docstring. Cheap, and makes "I read the compiled output"
  visible at review time. **Recommended.**
- **(b) Require it only for beats whose expected effect is non-obvious** (counters, gated content,
  anything the transpiler flagged unhandled). Less friction, relies on judgment about what is obvious —
  which is exactly what failed for Magikarp.
- **(c) Separate verification pass before approval:** author the list, then a second agent independently
  checks each expected effect against the Essentials source, and disagreements go to you.

### Q6. What form should the approval artifact take?

> **DECIDED 2026-08-20 — (a), split into generated facts + authored decisions, joined by a stable key and
> guarded by a content hash.**
>
> Q1(a) largely pre-decided this: the approved artifact *is* the generated manifest with dispositions, so
> the prose table's drift problem disappears because no second copy exists. The live problem was narrower
> and sharper: **CLAUDE.md §11 forbids editing generated output, so how does the operator change something
> they disagree with?** The answer is that the artifact is two files, not one.
>
> **Generated, never hand-edited** — one row per event page:
> `map_id, event_id, event_name, page_idx, condition, trigger, effects[], script_heads[], requires[],
> other_codes[], content_hash`. Pure derivation from RMXP data (plus `connections.json` seams, §6.2, and
> the `transpile_unhandled.jsonl` join, Q1). Idempotent by construction.
>
> **Authored, committed, hand-edited** — the disposition file, keyed by row id:
> `beat:Bn` / `deferred:<capability>` / `cosmetic` / `unreachable:<reason>`, plus the `source:` field Q5
> requires. The generator joins it at build time and **never writes to it**.
>
> Re-running the generator therefore cannot clobber a decision, and the checker reports drift in both
> directions: a row with no disposition (new content appeared) and a disposition whose row no longer exists
> (stale decision).

#### Q6.1 The content hash is what actually prevents drift

Row appearance and disappearance are the easy cases. The dangerous one is a row that still exists while its
*contents* change underneath a decision already made — the deserializer improves, the converter changes,
Uranium data is re-read. Each row therefore carries a **hash of its page content**; on mismatch the stored
disposition is **invalidated and must be re-affirmed**. Detecting deletion is not enough; this is the
mechanism that makes "machine-checked against the code, no drift possible" true rather than aspirational.

#### Q6.2 "I disagree with what was generated" has exactly two resolutions

The checker identifies which one applies, which is what makes the no-editing rule livable:

1. **The row is right, the disposition is wrong.** The Surf-gated event genuinely exists; it was marked
   `beat:B12` when it should be `deferred:surf`. **Edit the authored file.** Supported, no rule broken.
2. **The row itself is wrong** — it should not exist, or its effects are mis-tagged. That is a **generator
   bug by definition**: fix the generator, add a regression case, never touch the row. (CLAUDE.md §11.)

There is no third case.

#### Q6.3 NEW REQUIREMENT — `requires[]` has two sources, and only one is in scope so far

The operator's worked example: *what if a row is dispositioned as a beat but the player cannot Surf yet?*
Q3's capability model is the mechanism that catches it — a row dispositioned `beat:Bn` whose required
capability is not held at that beat index fails the checker. **But that only works if the row knows what it
requires**, and requirements come from two different places:

- **Script content** — `pbRockSmash`, or `pbPushThisBoulder` gating on `$PokemonMap.strengthUsed`.
  Mechanically derivable from the page. Already in scope.
- **Reachability** — **not in scope, and this is the case the Surf example lands on.** An event across water
  carries nothing in its script saying "needs Surf"; it is unreachable because the player cannot physically
  stand adjacent to it. That is a property of the collision grid, not of the event.

**Reachability analysis therefore becomes a generator input**, and `requires[]` is populated from both
sources. There is precedent that this works: `route1.py`'s deferred list was produced exactly this way — BFS
over the collision grid with chokepoint analysis — and it correctly identified all ten rock-gated beats,
including two nobody would have guessed by reading scripts (a staircase run, and an NPC pacing check whose
object never spawns while behind the gate).

**Known trap to design around:** the route planner is 4-neighbour and does not model sideways stairs.
`route1.py` documents a 13-tile pocket that a naive BFS reports unreachable in *every* rock configuration,
which is wrong — `GetRightSideStairsDirection` maps EAST to SOUTHEAST on `MB_SIDEWAYS_STAIRS_RIGHT_SIDE`
tiles. A reachability pass that ignores staircases will **over-defer**. This lands on Q9's list.

#### Q6.4 The human review view is a rendering, not a second artifact

The operator reads the manifest to feel confident about what a chapter is set up for, likely with an agent
summarizing it. That review view is **generated from the same rows** — grouped by disposition, `cosmetic`
rows collapsed, flagged and `deferred` rows expanded, seams and capability requirements surfaced. What is
read and what is checked share one source, so summarizing is a rendering choice rather than a new document
that can drift.

Corollary, from §5.8: the gate's headline tally should be **emitted by the runner**, not written as prose by
the authoring agent. The "60/60" figure is currently hand-authored and nothing checks it.


You approve the beat list before build work. Today that is a prose table in the chapter doc that then
drifts from the Python.

- **(a) Approve the generated manifest with dispositions** (Q1a) — one artifact, machine-checked against
  the code, no drift possible. **Recommended.**
- **(b) Keep the prose table, generate it from the Python so it cannot drift.**
- **(c) Keep both, add a drift checker.**

### Q7. What happens to prior chapters when a new defect class is discovered (finding F)?

> **DECIDED 2026-08-20 — rule-set versioning, not a hand-maintained ledger.** Option (b) as written assumed
> a ledger of classes with per-chapter "verified / not verified" entries. Two things change that.

#### Q7.1 What triggers registering a class — finding H gives the mechanical trigger

Nothing registers a class today, which is exactly how warp-arrival facing was invented inside `kevlar.py`
while CH01 and CH02 were never marked stale. The trigger falls out of finding H:

> **Promoting an assertion helper into the framework is the birth of a defect class.** The promotion and the
> class registration are the same act — `_assert_player_facing` cannot move out of `kevlar.py` without
> registering its class and marking every prior chapter as lagging it.

#### Q7.2 Most classes need no ledger — and that is the problem, not the relief

A class expressible as a **manifest rule** ("every row tagged `warp` owes a facing assertion"; "every row
tagged `text` owes a content assertion") needs no bookkeeping at all: the checker enforces it and prior
chapters fail immediately. But "fail immediately" means **adding a rule instantly turns CH01–CH03 red and
halts the frontier.** That is the real Q7 question, and it was unanswered.

The ledger therefore only carries classes that are *not* row-expressible — a much smaller set than Q7(b)
assumed.

#### Q7.3 DECIDED — versioned rule sets

Waivers were rejected: they rot, they accumulate owners who have moved on, and a waiver that outlives its
reason is indistinguishable from a bug.

- The rule set is **versioned and monotonic**. Each rule carries `id`, the tag it binds, the assertion it
  requires, the date added, and why.
- **Each chapter records the rule-set version it passed at gate time**, written by the runner as part of the
  gate stamp — never hand-edited. A chapter's version is bumped only by re-running it green under the newer
  rules.
- **New chapters bind to the current version.** Adding a rule bumps the current version; it does not fail
  chapters that passed under an older one.
- **The lag report is generated, not maintained**: "CH01 passed at rules v1; current is v4; CH01 lags
  warp-facing (v2) and text-content (v3)." That generated report *is* Q7's ledger, and it cannot drift
  because nobody writes it.
- **Retiring lag is the §4.5 staleness remedy with bookkeeping attached**: upgrade the beats in place,
  re-run the chapter green, its recorded version advances.

**Critical mechanical detail — replayed ancestors evaluate at their own recorded version.** Predecessor
chaining means CH04's gate replays CH01–CH03. Those replayed beats are evaluated under **the version their
own chapter recorded**, not CH04's. Without this, adding a single rule would break every descendant gate in
the corpus at once — the precise "halts the frontier" failure versioning exists to prevent.


- **(a) Nothing automatic; note it and move on.** Status quo. CH01/CH02 currently carry an unretired
  post-warp re-check.
- **(b) A defect-class ledger: each new class gets an entry, and a chapter is "verified against class X"
  or not.** Re-verification is then a bounded, visible backlog rather than a vague worry. **Recommended.**
- **(c) Full re-audit of prior chapters on every new class.** Correct, expensive, and grows quadratically.

### Q8. How are deferred beats tracked and un-deferred?

> **DECIDED 2026-08-20 — (a), as specified by §4.4 (corpus-wide backlog, capability-keyed, Arm A / Arm B
> triage) and §Q3 (keyed to beat index, not chapter id), plus the two rules below that §4.4 left open.**

#### Q8.1 Source of truth between the disposition file and the `DEFERRED_*` tuples

The same deferral will exist in two places: `route1.py`'s `DEFERRED_ROCK_GATED` (an inert tuple of
undecorated functions, verified in §5.8 to touch nothing) and the disposition file's `deferred:rock_smash`.
Nothing links them today, so they can silently diverge — and CLAUDE.md §4.3 requires one source of truth per
concept.

> **The disposition file is the source of truth. The Python tuple is the ready-made implementation.**
> The checker cross-references both directions: a row dispositioned `deferred` with no corresponding stub,
> or a stub with no corresponding deferred row, fails the chapter.

This matters more than it looks: those stubs are the cheapest asset in the corpus — ready-to-run regression
tests for content years away — and they are currently held together by comments.

#### Q8.2 The `deferred` / `unreachable` boundary needs a rule, not prose

Kevlar's **B26** is blocked on a dev-only flag (`sw130` / `FLAG_FILE_RECOVERY`) that is **never set anywhere
in the corpus**. That is not deferred content; it will never unblock. Today only prose distinguishes the two
dispositions, so the backlog would silently accumulate rows that can never resolve.

> **`deferred:<capability>` requires naming a capability that some chapter actually grants.** If no chapter
> in `chapters.json` grants it, the row is **`unreachable`**, not `deferred`.

Checkable directly against Q3's capability model, and it keeps the backlog to things that will genuinely
come due. B26 is the worked example.


CH02 has 9 deferred to CH06 (Rock Smash), CH03 has 6 to CH25 (Strength) plus 4 unregistered. Today they
are comments and module-level tuples.

- **(a) Structured deferral: each carries the capability that unblocks it and the chapter granting it;
  when that chapter goes green, a checker lists every beat now unblocked.** **Recommended** — pairs
  directly with Q3.
- **(b) Keep as comments, sweep by hand at each capability-granting chapter.**

### Q9. Which harness blind spots (finding G) get closed before CH04?

> **DECIDED 2026-08-20 — (a), and answered empirically.** Q9(a) said "one map-JSON read to know." That read
> was performed (Part 7); the table below is its result, not an estimate.

| Blind spot | Blocks CH04? | Evidence from map 35 |
|---|---|---|
| Runtime text content | **YES** | Events 3 and 23 are multi-page trainers with distinct self-switch A/B rematch dialogue — the multi-response case |
| Ledge directions | **YES — live converter defect** | 12 ledge tiles (tag 1); `ledge_directions` in `reference/terrain_tag_map.json` is empty **globally**, so ledges fall back to `MB_NORMAL` and convert to plain walkable floor |
| Capability model (Q3) | **YES** | Needed to adjudicate §7.2 and any CH06 deferrals |
| Double-battle support | no | 0 `pbDoubleTrainerBattle` |
| Menu / cursor navigation | no | no mart, no heal, no PC on the map |
| Fishing / Surf primitives | no | land encounters only; water tiles passive scenery |
| Staircase-aware reachability | no | `stairs.py::detect_stair_cells` returns **zero** stair cells on map 35 |
| Choice-arm handling | no | 0 code-102 choices |
| PC box reads | no | no PC on the map |

**Scheduling win:** the hardest item from Q6.3 — staircase-aware reachability — **does not block CH04**.
**Scheduling surprise:** two items nobody had listed do: ledge directions, and the text primitive.


Route 2 is an outdoor route: likely trainers, wild encounters, item balls, ledges, possibly a gate
building. Dialogue-text assertion and menu navigation may not be needed yet; elevation and diagonal
routing might be.

- **(a) Close only what CH04's map data proves it needs** — inspect Route 2's events first, then decide.
  **Recommended**; it is one map-JSON read to know.
- **(b) Close the general-purpose gaps now** (party assertions, bag write seeding, text content) so later
  chapters are unblocked.
- **(c) Close nothing; defer until a beat is actually blocked.** How B11 happened.

### Q10. Beat independence versus fail-fast ordering.

> **DECIDED 2026-08-20 — `NOT_RUN` first, hang budget second, seed-resume optional.**
>
> **The doc originally framed B11 as a fail-fast ordering problem. That misses the actual mechanism.** When
> B11 hung, the seven beats behind it **simply did not appear in the output**. Nothing said they had not
> run. The runner prints per-beat `PASS`/`FAIL` and a verdict line, so a beat that never executed is
> indistinguishable from one that does not exist. Seven latent geometry bugs hid behind that silence, and
> the ordering was never the reason.
>
> 1. **The runner emits `NOT_RUN` as an explicit per-beat status**, and the tally reads `53/60 run` rather
>    than going quiet. No seeding, no reordering, and it composes with §5.8 (the `N/N` figure is currently
>    hand-written prose that nothing generates). **This is the minimum and it would have caught B11.**
> 2. **A per-beat hang budget** (option b), so a hang reports as a status distinct from an assertion
>    failure.
> 3. **Seed-resume after failure** (option a) — the stronger version, adopted only if the seeding cost
>    proves acceptable.
>
> Note this is another instance of §1.4's thesis: the bug was not sequencing, it was an omission the report
> did not surface.


CH03's B11 hang masked seven downstream failures (finding E). Beats are sequential and stateful by
design, so one hang stops everything behind it.

- **(a) Accept it, but on failure automatically continue from the last good seed blob** and report every
  downstream beat's result too, marked "ran from seed after a failure."
- **(b) Keep strict sequential fail-stop, but add a hang budget per beat** so a hang is reported as a
  distinct status from a failed assertion. **Recommended** as the minimum; (a) is the stronger version
  if the seeding cost is acceptable.
- **(c) Status quo.**

### Q11. What is the actual unit of "done" for scenario authoring?

> **DECIDED 2026-08-20 — (a), with `cosmetic` given a mechanical definition so it carries the load option
> (b) was invented to carry.**
>
> **Idiom sampling (b) is rejected on empirical grounds.** CH03's three dead item grants were *identical
> idiom* — the same generated grant shape — and sampling one of them would have missed the other two. The
> exact failure that motivated this document is the failure idiom-sampling permits.
>
> **What makes (a) affordable is not sampling but a defined `cosmetic`.** The disposition was previously
> undefined, which meant it could absorb anything an author wanted it to. Mechanical rule:
>
> > A row may be dispositioned **`cosmetic` only if its entire effect set is non-state-writing** — `text`,
> > `se`, `bgm`, graphic changes, `move_route` that writes no state. A row carrying **any** of `giveitem`,
> > `givemon`, `trainerbattle`, `wild_battle`, `warp`, `switch_write`, `var_write`, `self_switch_write`,
> > `shop`, `heal`, `pc`, `money`, or `common_event` **cannot be cosmetic**. Nor can a row with unhandled
> > queue entries (Q1), nor one with an unrecognized script head (Q2iii — that row cannot be dispositioned
> > at all until classified).
>
> Note `self_switch_write` is deliberately on the forbidden list: a dialogue NPC that sets a self-switch is
> changing its own future behavior, which is state, not decoration.
>
> **Unit of done, stated plainly:** every page of every event on every map in the chapter, plus every
> overland seam touching them (§6.2), carries a disposition. Every non-`cosmetic`, non-`deferred`,
> non-`unreachable` row carries an assertion on its observable effect (Q4). Text *conversion* is verified
> statically across the whole corpus rather than per beat (Q4 revised).


Implied by everything above but worth stating: is the target "every event dispositioned and every
non-deferred one asserted," or something looser like "every event class exercised at least once per
chapter" (one dialogue NPC, one item ball, one trainer, not all nine)?

- **(a) Every satisfiable page dispositioned; every non-deferred one asserted.** Highest fidelity, highest
  cost per chapter. **Recommended for this corpus** — it is a get-it-right-once conversion, and CH03's
  three dead item grants were exactly the kind of thing sampling would have missed.
- **(b) Full disposition, but assertion sampling within an identical-idiom class** (nine copies of the
  same generated sign script → assert one, disposition the rest as `idiom:<classifier>`). Much cheaper at
  route scale, and the transpiler already knows which events are the same idiom.
- **(c) Class coverage only.**

---

## Part 3 — Things I am fairly confident about and would not spend grill time on

- Beat ids stay labels, registration order stays playthrough order (already documented as of `0f46cb2e`).
- Approve-before-build stays.
- Predecessor chaining and full-replay-at-gate stay.
- "Walk first, then look" (camera-bound `gObjectEvents`) belongs in the authoring rules, not as an open
  question.
- No hardcoded coordinate constants that a helper might bypass — B8's dead `MAWULI_APPROACH` should be
  structurally impossible (coordinates come from the map JSON or are computed live).

---

## Part 4 — Verified harness and data inventory (2026-08-20)

Established by direct code read, not recollection. This is what the decisions above are standing on.

### 4.1 What the harness can observe today

| Capability | Status | Where |
|---|---|---|
| Player map / x,y | Exists | `emulator.py:552` `player_pos()`, `:556` `map_location()` |
| Player + NPC facing | Exists | `emulator.py:203` `_decode_facing()`, `:560` `object_event()` |
| Expected arrival facing (derived from build) | Exists, **chapter-local** | `kevlar.py:538` `_expected_arrival_facing()` |
| Flags / vars | Exists | `emulator.py:634` `flag()`, `:639` `var()`, `:659` `set_var()` |
| Money (read + write) | Exists | `emulator.py:685` / `:693` |
| Bag item quantity | Exists | `emulator.py:718` `bag_item_quantity()` |
| Item price (ROM table) | Exists | `emulator.py:751` `item_price()` |
| Party **species** | Exists, **chapter-local + duplicated** | `moki.py:277`, `kevlar.py:1244`, via `battle.py:94` `decrypt_species` |
| Text is *drawing* / page landed | Exists | `emulator.py:860` `text_showing()`, `:878` `text_ready()` |
| **Text content (the actual string)** | **DOES NOT EXIST** | — |
| **Party HP / moves / PP / stats / level** | **DOES NOT EXIST** | acknowledged in `pokecenter.py:26-40` |
| **PC box contents** | **DOES NOT EXIST** | `use_pc` exercises only the cancel arm, `pokecenter.py:61-85` |
| **Field-move usability (Strength/Rock Smash/Cut/Surf)** | **DOES NOT EXIST** | all such beats deferred corpus-wide |
| **Yes/No cursor position** | **DOES NOT EXIST** | `emulator.py:833`; A always commits default YES |
| Menu cursor navigation | Start menu only | `scenarios.py:204` `_select_start_menu_row()`; mart and battle rely on default-cursor-0 |

**Recommended build order.** Text-content read first. The harness already walks the `sFirstTextPrinter`
linked list to implement `text_ready()`; those printer structs carry a pointer to the source string, so
reading that pointer and decoding pokeemerald's character table yields the exact string — deterministic,
cheap, and far better than OCR. It satisfies the "text converts correctly" requirement *and* makes an NPC's
multiple responses distinguishable by content, which is the only way to cover them. One primitive, two
requirements.

**Known live defect parked behind a deferral.** `kevlar.py` records that Kevlar's three boulders
(`Map019_EV00{1,2,3}_Page1`) have **no push movement wired at all** — bare `lock`/`release`, no
`OBJ_EVENT_GFX_PUSHABLE_BOULDER`. That is a converter bug, not merely Strength-gated content, and it is
currently invisible until CH25. Whatever deferral mechanism is chosen must carry known defects riding on
deferred rows, or this resurfaces 22 chapters out as a mystery.

### 4.2 What the data gives the manifest generator

- **Page shape** (`Map###.json`): `condition{switch1_valid, switch1_id, switch2_valid, switch2_id,
  variable_valid, variable_id, variable_value, self_switch_valid, self_switch_ch}`, `trigger`, `graphic`,
  `move_route`, and `list` = `[{code, indent, parameters}, …]` terminated by `code: 0`. Nesting is carried
  by the `indent` integer, not by JSON structure.
- **Command catalog**: `reference/guides/rgss_event_commands.md`, generated by
  `map_deserializer/command_catalog.py`. **59 codes in use, 83,237 instances.** Do not hand-edit.
- **Polarity trap, already known**: code-123 self-switch value `0` means **ON**.
- **Noise**: code-509 rows are the editor's per-step display duplicates of a preceding 209 route;
  stripped without a queue entry.
- **`_census_one_map`** (`chapter_atlas/census.py:230-294`) is a **pure aggregator** — one `MapCensus` of
  scalars per map, no per-page rows, and it **never reads `condition` or `trigger`**. Import its traversal,
  `_script_head`, `_record_script`, and `MECHANIC_BY_HEAD`; do not try to wrap its output.
- **`chapters.json`** enumerates each chapter's maps explicitly (`"maps": [...]`) — no derivation needed.

### 4.3 CH04 as the pilot

`CH04` is **a single map (35)**, so the manifest generator, the checker, and the text primitive can all be
proven on a small surface before route-scale volume is a concern. CH04's own `notes` record that the direct
Route 02 → Nowtoch overland seam is **rockslide-blocked until Rock Smash**, so CH04 will produce
rock-smash-class deferrals joining CH02's nine. The deferral-tracking question (Q7/Q8) is therefore load
bearing in the very next chapter, not hypothetical.

### 4.4 DECIDED 2026-08-20 — the corpus-wide deferral backlog

**Pages do not respect chapter boundaries.** A page whose condition unlocks on a capability granted much
later is on an early chapter's map, is genuinely unreachable during that chapter, and is on no later
chapter's map list. Under a per-chapter manifest keyed to maps it is dispositioned `deferred` once and then
never appears in any manifest again — falling through the exact crack the manifest exists to close.

**Decision: option (1). Deferrals leave the chapter manifest and enter a corpus-wide backlog keyed to the
capability that unblocks them.**

> **CORRECTED 2026-08-20.** An earlier draft of this section claimed this is "the same ledger Q7 wants for
> defect classes; they are one artifact." **That is wrong** — see §4.5 and Q7. The two have different join
> keys: a deferral is *(row x capability)*, resolving at a beat index; a defect class is
> *(chapter x assertion class)*, resolving by re-running a chapter. They are two artifacts with two
> remedies.

#### The sweep

When a chapter grants a capability, the backlog is swept for every row that capability unblocks. Each
unblocked row is then **triaged**, and the triage has exactly two arms:

**Arm A — a natural revisit exists.** The playthrough genuinely routes the player back across that map.
The canonical case: Moki Town's Rock Smash boulders block Route 3. After Nowtoch City the player reaches a
dead end and must walk back to the starter town to take Route 3 onward. That backtrack is not a contrivance
— it *is* the playthrough. The unblocked rows are assigned to the chapter covering that leg and asserted for
real, on the way through.

**Arm B — no natural revisit.** Nothing in the playthrough brings the player back across that map after the
capability arrives. Suspected case: Kevlar Town's Strength boulders, where HM04 lands at CH25 and the route
may never return through Kevlar. **The checker raises these to the operator as an explicit decision** at the
moment the capability is granted. It does not silently leave them deferred, and it does not invent a
detour on its own. Operator, verbatim: *"anything where there is no natural 'we come back through this town'
element so we can test the event then we should raise those as a flag when we gain that ability."*

#### Revisit manifests are deltas, not full manifests

A backtrack leg does **not** re-manifest the whole map. Beats already covered by a prior chapter stay
covered — the predecessor-chaining replay already re-runs them at gate time. A revisit's manifest contains
only:

- previously-deferred rows on the crossed maps that the new capability unblocks, and
- any rows that were genuinely new or undispositioned on those maps.

This bounds the cost of a backtrack to the thing that actually changed, which is what makes Arm A affordable
at all.

#### Deferred rows carry known defects with them

A backlog row is not only "blocked content." It must carry any defect already discovered against it, or the
defect resurfaces many chapters later as a mystery. Live instance: Kevlar's three boulders
(`Map019_EV00{1,2,3}_Page1`) have **no push movement wired at all** — bare `lock`/`release`, no
`OBJ_EVENT_GFX_PUSHABLE_BOULDER`. That is a converter bug parked behind a Strength deferral and currently
invisible until CH25.

---

### 4.5 Two backlogs, two different remedies

These were conflated in an earlier draft. They are not the same problem and only one needs a revisit leg.

**Backlog 1 — staleness.** New assertion classes invented after a chapter passed its gate. **Remedy: upgrade
the beats in place** in `moki.py` / `route1.py` / `kevlar.py`. Predecessor chaining replays every ancestor
from a new game at gate time, so an upgraded ancestor beat re-runs automatically on the next chapter's gate.
Fix once, verified from then on. No revisit chapter involved.

| Class | Stale chapters | Notes |
|---|---|---|
| Warp arrival facing | CH01, CH02 | `route1.py` has none of the facing helpers (finding H); CH03 has them |
| Text content | CH01, CH02, CH03 | Blocked on the primitive not existing at all (§4.1) |

**Backlog 2 — capability.** Content that cannot be asserted from the original chapter at any price, because
it needs the player to be standing there later holding a tool they do not yet have. **Remedy: a revisit leg**
(§4.4 Arm A) or an operator decision (Arm B). This is the only backlog that adds chapters. Sized in §5.6.

---

## Part 5 — Finding I: the chain chapters endpoints, not the walk between them

**RESOLVED 2026-08-20 by direct read of `chapters.json` (59 chapters) and the warp/connection data.**
The original suspicion — "the chapter model has no revisit concept" — is **wrong**, and the correction
matters because it makes the fix much cheaper than feared.

### 5.1 The revisit pattern already exists

**65 map ids already appear in more than one chapter's `maps` list.** The schema supports revisits and the
atlas uses them consistently: a gating town gets a later `(revisit)` chapter carrying the *same* `maps`
list as its first visit. Examples: `CH08 "Moki Town (revisit)"`, `CH07 "Route 2 (revisit)"`,
`CH28 Burole revisit`, `CH37 Bealbeach revisit`, `CH58 "Moki Town (postgame)"`.

So the earlier framing of "(i) new first-class chapters vs (ii) new delta-attachment machinery" is moot —
**neither needs inventing.** The mechanism exists. What is missing is *coverage*: it has been applied to
some legs and not others.

### 5.2 The gap is the intervening walk

Capability grants, confirmed:

| Capability | Chapter | Title |
|---|---|---|
| Rock Smash (HM06) | **CH06** | Nowtoch City (maps 40–47; Gym 1 at map 42) |
| Strength (HM04) | **CH25** | Route 11 (maps 18, 140) |

The Moki/Route 3 line the operator described is chained correctly at its **endpoints**:
`CH07 Route 2 (revisit)` → `CH08 Moki Town (revisit)` → `CH09 Route 3`, and CH09's notes name the seam
(`connections.json` `32 E <-> 59 W`). But to get from Nowtoch to Moki the player must physically walk
**Nowtoch → Route 2 → Kevlar Town (31) → Route 1 (33) → Moki**. Only Route 2 has a revisit chapter.
**Maps 31 and 33 appear in exactly one chapter each — CH03 and CH02 — and never again.** CH07 and CH08 sit
adjacent in the chain with two physically-crossed maps modelled by nothing.

### 5.3 This is Arm A, with no owner — a live instance, not a hypothetical

CH02's nine deferred rock-gated beats (6 boulders + 3 rock-gated item balls: Repel, Super Potion, Rare
Candy) are **on map 33** — the very map the player crosses on the CH07→CH08 walk, **with Rock Smash already
in hand from CH06**. That is §4.4 Arm A exactly: a natural revisit exists, the capability is held, the rows
are unblocked — and there is no chapter to assign them to. Without the fix they stay deferred forever
despite the player walking right past them holding the tool.

### 5.4 Kevlar is Arm B, and confirmed

Maps 31 (Kevlar Town) and 19 (Passage Cave) appear in **no chapter after CH03**, anywhere in all 59
chapters — no revisit, no postgame. Passage Cave connects only to and from Kevlar in both directions. So
when CH25 grants Strength, the Kevlar boulders have **no natural revisit**: §4.4 **Arm B**, raised to the
operator as an explicit decision. This is the first confirmed Arm B case, and it is the one carrying the
known converter defect (boulders with no push movement wired at all).

Note the two arms are distinguished by *capability timing*, not by geography: Kevlar **is** naturally
re-crossed on the CH07→CH08 walk — but that is at Rock Smash time, and its boulders need Strength, which is
18 chapters later. A map can be Arm A for one capability and Arm B for another.

### 5.5 Recommendation

1. **Add the missing revisit chapters for walked legs** — at minimum Route 1 (33) between CH07 and CH08,
   using the existing `(revisit)` pattern with a **delta manifest** (§4.4): only the rows the new capability
   unblocks, not the whole map. CH02's nine rock-gated beats become that chapter's content.
2. **Audit the whole chain mechanically rather than case-by-case.** The check is derivable: for each
   consecutive chapter pair, compute the physical path between them from `connections.json` and the warp
   graph; any map on that path present in **neither** chapter is an unmodelled walked leg. Kevlar and
   Route 1 were found by hand here; a 59-chapter chain should not be audited by hand.
3. Treat "does this chapter's `maps` list cover what the player physically crosses to reach it" as a
   property the atlas asserts, not a thing an author remembers.

**Open for the operator:** whether the walked-leg revisit chapters get their own §9 boot gate (CLAUDE.md
pins chapter ≡ slice ≡ one boot gate ≡ one ROM-test scenario) or ride along on the following chapter's walk.
Lead recommends riding along — the player crosses those maps *inside* the CH08 walk regardless, so a
separate gate would mean walking the same ground twice.

### 5.6 Sizing the revisit legs (measured 2026-08-20)

Counted directly from the chapter modules. **Registered beats: CH01 17, CH02 13, CH03 30** (see §5.8).

#### CH02 Route 1 — `DEFERRED_ROCK_GATED` holds **10** beats, and excludes the boulders

An earlier draft of this document said "9 deferred = 6 boulders + 3 item balls." **That is wrong twice
over.** The tuple holds 10, and none of them are boulders:

| Count | Content | Blocker |
|---|---|---|
| 5 | Trainer battles — Marko, Bob, Brandon (triathlete), Gertha, Brandon (phone + Match Call) | Rock Smash |
| 1 | B3, the second sideways-staircase run walkable both directions | Rock Smash |
| 1 | B14b, Brandon's `WALK_UP_AND_DOWN` pacing (object never spawns behind the pocket) | Rock Smash |
| 3 | Item balls — Repel (EV008), Super Potion (EV037), Rare Candy (EV032) | Rock Smash |

Plus **6 boulders with no positive smash beat written at all** — only the EV036/EV038 chokepoint pair is
covered *negatively* by the registered N2. So Route 1's revisit owes **10 restorable + 6 to author = 16**,
including five trainer battles.

**The Old Rod unblocks at the same time.** It is gated on clearing Gym 1 (`VAR_BATTLE_VAR01 >= 5`), not on a
key item — and Gym 1 is CH06 Nowtoch, the same chapter that grants Rock Smash. The earlier worry that Route 1
might owe *two* revisits is dissolved: rock content and fishing content unblock together. The rod grant plus
the three `fishing_mons` tables have **no beat stubs written**, so that side is bounded below at ~4 and is not
exactly sizeable from code.

**Conclusion: Route 1 gets its own thin `Route 1 (revisit)` chapter at CH06+.** This is not a new pattern —
`CH07 "Route 2 (revisit)"` is already a single-map `tier: thin` chapter created for exactly this reason
(Rock Smash changed reachability on one map). Route 1 is the identical case one map earlier and was simply
missed.

#### CH01 Moki Town — **zero** deferred beats, and that is the finding

`moki.py` has no deferral tuple, no Rock-Smash content, and mentions Route 3, boulders, and HMs **nowhere**.
Its only out-of-scope note is B15's westward walk, which is a build-scope boundary (unset `connections`), not
a capability gate.

The operator recalls Rock-Smash boulders in Moki Town blocking Route 3. If that is right, **CH01 never
enumerated them** — a live class-A omission in the first chapter, and precisely what the manifest generator
exists to catch. **Action: run the manifest over map 32 before sizing CH08.** Until then CH08's ride-along
delta is unknown; the risk is not that CH08 grows too large but that it is empty for the wrong reason.

#### CH03 Kevlar — 10 deferrals across **three** triggers, with no revisit chapter at any of them

| Count | Blocker | Unblocks at |
|---|---|---|
| 7 | Strength — B19–B24 (cave door, 3 boulders, Lou/Joe/Richard, exit warp) + B18b (Cry Boy accept branch) | CH25 |
| 1 | Bike Wheel key item (B15b, Bike Wheel → Bicycle) | CH11 Route 4 |
| 1 | Story flag `sw94`, post-Gym-5 (B23b, Richard's harder team) — **doubly blocked**: no `trainerbattle*` exists in the compiled script on either branch, a converter gap on top of the gate | post-Gym-5 |
| 1 | B26 Compensation Man — dev-only `sw130`/`FLAG_FILE_RECOVERY`, **never set anywhere in the corpus** | never |

B26 is not deferred content; it should be dispositioned **`unreachable`**, and it is a clean worked example
of why that disposition needs to exist separately from `deferred`.

Kevlar is the strongest case in the corpus for §4.4 Arm B: it owes content at three distinct points and maps
31/19 appear in **no chapter after CH03** anywhere in all 59.

#### Sizing rule this supports

A walked leg **rides along** when its delta is small and exercises no mechanic the host chapter is not already
exercising (Kevlar-on-the-way-to-Moki, at Rock Smash time: contributes nothing, since its deferrals are keyed
to other capabilities). It gets its **own thin revisit chapter** when it has its own mechanic to prove or the
delta is a play session in its own right (Route 1: 16 beats, five of them trainer battles).

#### Resolved: the 62-vs-60 discrepancy (see §5.8)

### 5.7 Transit beats — who owns the walk across a map with no new content

If Route 2 and Route 1 each get their own revisit chapter, the player still has to physically cross **Kevlar
Town** between them, and Kevlar owes no unblocked rows at Rock Smash time. So which chapter executes that
walk?

**The convention already exists and is unnamed: the entering chapter owns the seam crossing.** `kevlar.py`'s
first beat is B1, *"Crossing Route 1's north seam lands in Kevlar Town"* — CH03's first beat performs the
walk *from* CH02's ending position. This falls out of the harness design: beats are sequential and stateful,
each chapter begins wherever its predecessor left the player, so a crossing must be executed by some beat or
the next chapter's first beat starts stranded.

**Therefore the Kevlar walk belongs to the `Route 1 (revisit)` chapter's entry beat** — enter from Route 2,
cross Kevlar, exit south into Route 1. Identical shape to B1, one map further along.

#### A transit beat is not assertion-free

Naming the category matters because "no new content" reads as "no work," and that reading is how CH01 and
CH02 both passed §9 with the post-warp bug live. A transit beat owes:

1. **Every seam crossed, under the Q4 standing rule** — destination map + coords + arrival facing. The Kevlar
   transit crosses two (Route 2 → Kevlar, Kevlar → Route 1), so it owes two full warp assertions.
2. **The revisit delta on the crossed map** — pages on map 31 whose conditions are **now satisfiable but were
   not during CH03**, i.e. anything gated on a flag set in CH04–CH06. Those were correctly dispositioned
   `unreachable` on the first pass and go live on the second. This is the per-(row, capability) triage of
   §5.4 applied to a map nobody would think has new content, and it is invisible without the manifest.

A transit beat is therefore the cheapest place for an omission to hide: it looks like plumbing, it is
skipped in prose, and it is exactly where a re-crossing silently activates pages nobody re-examined.

---

### 5.8 RESOLVED — the beat-count discrepancy was a grep artifact

An earlier draft flagged that registered counts summed to 62 while CH03's gate reported 60/60.
**60 is correct; 62 was the error.**

Counting `@X.beat(` with grep also matches two *prose comments* that describe the decorator syntax without
applying it — `route1.py:1616` and `kevlar.py:1562`, both inside the deferred-block explanations. Excluding
those two false positives:

| File | Real registered beats |
|---|---|
| `moki.py` | 17 |
| `route1.py` | **13** (not 14) |
| `kevlar.py` | **30** (not 31) |

17 + 13 + 30 = **60**, verified independently by importing `load_chapter` and reading `len(CHAPTER.beats)`:
moki 17, route1 30 (17 inherited + 13 own), kevlar 60 (30 inherited + 30 own).

Confirmed while reconciling, and worth recording because both were open assumptions:

- **`ChapterBuilder.build()` does no filtering, dedup, or dropping.** It prefixes the predecessor's
  recursively-resolved beats as `<owner>:<name>` and concatenates. The chain is preserved 1:1, so an
  ancestor beat upgraded in place *does* re-run on every descendant's gate — which is what §4.5's
  staleness remedy depends on.
- **The `DEFERRED_*` tuples are inert.** They are plain tuples of undecorated functions; no code path
  touches `ChapterBuilder._beats`. They can neither add nor remove anything from a build.
- Git history across the gate window shows no beats added after the stamp, so 60 was correct then and now.

#### Incidental finding: the "N/N" tally is hand-written

`playtest/__main__.py` prints per-beat `PASS`/`FAIL` lines and a `chapter {name}: {VERDICT}` line, but
**never emits an `N/N` tally**. The "60/60" in `MEMORY.md` and the archived CH03 TODO is the authoring
agent's own prose summary of a real run, not a generated artifact. A small instance of exactly the drift
class this document exists to eliminate: the gate's headline number is not machine-produced and nothing
checks it. Cheap fix, and it belongs with the Q6 approval-artifact question.

---

## Part 6 — Manifest dry-run over map 32 (Moki Town), 2026-08-20
The manifest generator does not exist yet, so this was run by hand-script against
`output/uranium-build/maps/Map032.json` as a calibration case: a map with a chapter (CH01) that already
passed its §9 gate, so the diff between "what is on the map" and "what CH01 asserted" is measurable.

**Map 32 carries 52 events / 90 event pages. CH01 registered 17 beats.**

### 6.1 The boulders exist, and CH01 never enumerated them

Confirmed: **events 14, 15, and 33**, all named `Rock`, all with graphic `character_name` =
`fk107-rocksmash`, all with the page-0 chain `pbRockSmash` → `pbRockSmashRandomEncounter` →
`isRockSmashSoftlocked` → `pbEraseThisEvent`, and a page 1 gated on `self_switch=A` (the smashed state).
Positions (65,45), (66,46), (66,44) — the easternmost cluster on a 72-wide map.

`moki.py` mentions rock, smash, or boulder **nowhere**. This is a live class-A omission in the first
chapter of the game, found by the first mechanical enumeration ever run against that map. It is the
strongest single argument in this document for Q1(a).

### 6.2 CRITICAL — overland seams are invisible to an event-only manifest

There is **no code-201 warp from map 32 to map 59 (Route 3)**. The connection is
`[32, "E", 26, 59, "W", 0]` in `output/uranium-build/connections.json` — an **overland seam**, part of the
outdoor connection system, not an event at all.

> **A manifest generated from event JSON alone cannot see overland seams.** Every outdoor route boundary in
> the corpus is invisible to it.

This is not academic. **CH04 is Route 2, and its entire chapter identity is two overland seams**
(`31 N<->S 35` and `35 N<->S 40`, per its own `chapters.json` notes). Running an event-only manifest on CH04
would silently omit both of the chapter's most important transitions.

**Requirement added to Q1/Q2:** the manifest generator joins `connections.json` and emits a row per seam
touching the chapter's maps, dispositioned like any other row. Under the Q4 standing rule each seam row owes
destination map + coords + arrival facing.

### 6.3 The unrecognized-head rule earned its place immediately

Script heads found on map 32, against `census.py`'s `MECHANIC_BY_HEAD`:

| head | count | recognized? |
|---|---|---|
| `pbCallBub` | 41 | **no** |
| `get_character` | 8 | **no** |
| `setTempSwitchOn` | 8 | **no** |
| `pbEraseThisEvent` | 6 | **no** |
| `pbRockSmashRandomEncounter` | 6 | yes |
| `pbReceiveItem` | 3 | yes |
| `pbRockSmash` | 3 | yes |
| `isRockSmashSoftlocked` | 3 | **no** |
| `pbCaveEntrance` | 3 | yes |
| `pbSetSelfSwitch` | 3 | **no** |
| `pbPhoneRegisterNPC` | 1 | yes |

**Six of eleven heads are unrecognized on the very first map tested.** Q2(iii) — a row with an unrecognized
head cannot be dispositioned until a human classifies it — is validated empirically, not just in principle.

### 6.4 Coverage diff against CH01

Only **4 of 52 events** have verifiable correspondence to a registered beat: ev3 (lab door, B5), ev9
(ceremony, B13/B14), ev17 (Theo's house, B11), ev74 (fence trip, B4).

**Stated precisely, because the number is easy to over-read:** this is a textual/coordinate check, and many
of the remaining 48 are plain dialogue NPCs that would legitimately disposition as `cosmetic`. It is **not**
"48 missing beats" — it is **48 undispositioned rows**, among which the three boulders and the Route 3 seam
are real load-bearing omissions. The distinction is exactly why the manifest requires a *disposition* rather
than a *beat* per row.

Also surfaced: events 78–81 gated on `switch1=55` / `switch1=125` (post-gym states) and eleven `Luz` events
gated on `switch1=106` — later-chapter content living on a CH01 map. §4.4's "pages do not respect chapter
boundaries" confirmed in the first chapter of the game.

### 6.5 Consequences

- **CH08 (Moki revisit) is not empty.** Its delta is the three boulders plus the Route 3 seam — real content,
  small enough that the §5.6 ride-along rule still holds.
- **The manifest generator must join three sources**, not one: `Map###.json` (events/pages),
  `connections.json` (overland seams), and `transpile_unhandled.jsonl` (the cosmetic-disposition veto).
- **Map 32 is the regression fixture.** It has a known-good chapter, a known omission, and unrecognized
  heads — build the generator against it and the expected output is already characterized.

---

## Part 7 — Manifest dry-run over map 35 (Route 2), 2026-08-20

Run before CH04 authoring starts, as Q9(a) prescribes. Second calibration case after map 32.

### 7.1 Scale — a good pilot

42x57 tiles, **21 events, 40 event pages** (map 32: 72x64, 52 events, 90 pages). Event ids 4-7 and 10 do not
exist — gaps in RMXP numbering, not omissions.

### 7.2 The rockslide contradiction — unadjudicated, and a live Q5 instance

**Event 19 is labelled `Trainer(4)` but contains no `pbTrainerBattle` call.** It is a cutscene that runs
`for i in 14..18: pbSetSelfSwitch(i, "A", true)` — force-setting the smashed-state self-switch on all five
Rock events (14-18). Those rocks' page 1 (`self_switch=A`) is empty, so the cutscene **bulk-clears the
rockslide**.

This **contradicts CH04's own `chapters.json` notes**, which state — sourced from the wiki — that the route
is *"rockslide-blocked until Rock Smash, so the first pass is forced through Passage Cave."*

Both cannot be true, and the answer decides whether CH04 has **any** Rock Smash deferrals. **Not adopted —
this is one agent's read of a Ruby loop and the trigger conditions need checking.** Flagged for adjudication
before CH04 authoring.

**Note what this demonstrates.** The Q5 citation trigger (unrecognized script head; script-typed conditional)
**fires on this row**, and it fired *before a single beat was authored*, on the first chapter run under the
new process. The failure it guards against — reading compiled output or a wiki summary as evidence about
design — was live and waiting in CH04's own notes.

### 7.3 Mechanic inventory

| Mechanic | Count | Events |
|---|---|---|
| Trainer battles (single) | 4 | 3, 12, 23, 24 |
| Double trainer battles | 0 | — |
| Scripted wild battles | 0 | — |
| Item balls (`pbItemBall`) | 3 | 9, 25, 26 |
| Item grants (`pbReceiveItem`) | 0 | — |
| Rock Smash rocks | 5 | 14-18 (but see §7.2) |
| Boulders / Cut / Surf / Flash | 0 | — |
| Mart / heal / PC | 0 | — |
| Choices (code 102) | 0 | — |
| Scripted warps (code 201) | 1 | ev 1 -> map 36 (17,39), `pbCaveEntrance` |

Events 3 and 23 additionally carry phone/rematch state (`pbPhoneRegisterBattle`, `pbPhoneIncrement`,
`pbPhoneBattleCount`) across self-switch A/B pages — **the multi-response case**, and CH04's reason for
needing the runtime text primitive.

### 7.4 Terrain

Terrain-tag histogram over 1184 cells (tileset 22, `PU Route01-Kevlar`): 959 normal, 54 water, 49 grass,
48 waterfall, 21 rock, **12 ledge**, 1 long grass.

- **Ledges are a live defect.** `reference/terrain_tag_map.json`'s `ledge_directions` is empty **globally** —
  no tileset has directions assigned. Per `stairs.py`, an unmapped ledge falls back to `MB_NORMAL` with a
  runtime warning, so Route 2's 12 ledge cells will convert to plain walkable floor rather than one-way
  drops. This must be fixed before CH04's §9 playability gate.
- **No sideways stairs.** `detect_stair_cells` returns zero on map 35, so the Route 1 diagonal-staircase trap
  does not apply and staircase-aware reachability is not a CH04 blocker.
- **Water and waterfall tiles exist but are passive** — no `pbSurf`/`pbWaterfall` call and no water encounter
  table.
- **Elevation not determined.** The `tiles` grid is 42x57x3, but that is RMXP's render-layer stack, not a
  passability model. Deciding true elevation/passability requires decoding the `passages` bitmask via the
  tileset converter's `layout.py`; not done here.

### 7.5 Two smaller flags

- **Seams carry lateral offsets**: `[31,'N',11,35,'S',0]` and `[35,'N',0,40,'S',15]`. Arrival coordinates are
  therefore not a straight axis mapping — directly relevant to the Q4 warp-facing assertions.
- **Encounter table location**: map 35's own `encounter_list` is empty; the real table (land only, rate 25,
  12 slots, levels 3-5) lives in `output/uranium-build/intermediate/wild_encounters.json`. There is no
  top-level `wild_encounters.json`. Worth confirming which file the emitter consumes.
