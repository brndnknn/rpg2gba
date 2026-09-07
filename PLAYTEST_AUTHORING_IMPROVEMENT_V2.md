# Playtest Authoring — Findings and Open Questions, Round 2

**Status:** pre-decision working document. Written 2026-08-27, after CH04 (Route 2) passed its §9 gate
and before CH05 (Passage Cave) scenario work starts.

**Predecessor:** `reference/archive/PLAYTEST_AUTHORING_IMPROVEMENT.md` (2026-08-20), written before CH04. That document
analyzed CH01–CH03, named eight failure classes A–H, and decided a set of fixes. CH04 was the pilot
chapter for those fixes. This document asks the same question one round later: *what did the fixes
actually do, and what is left?*

**Goal being pursued (unchanged):** be able to say "write the CH05 scenario" and get a beat list that
(a) covers every event in the chapter, (b) knows what the player can and cannot do at that point, and
(c) asserts the real effect of each event rather than a proxy for it.

Sources: the full commit history of `src/rpg2gba/playtest/chapters/route2.py` and the 26-commit CH04
range `85fc9417..c8159327`; `reference/archive/CH04_TODO.md`; `reference/chapters/04-route-2.md`;
`reference/manifests/CH04.{manifest,dispositions}.json`; `PROJECT_TODO.md` #43–#52; an audit of
`src/rpg2gba/chapter_manifest/` and `src/rpg2gba/playtest/` against every decision in the v1 document.

---

## Part 1 — What actually happened in CH04

### 1.1 Beat counts — the headline result

| Chapter | Approved at authoring | Registered at gate pass | Growth |
|---|---|---|---|
| CH01 moki | 18 | 17 | −1 |
| CH02 route1 | 29 incl. 9 deferred | 29/29 green first attempt | 0 |
| CH03 kevlar | 35 (user-approved 2026-08-12) | 60/60 (`e1c5200f`) | **+25** |
| **CH04 route2** | **15 (B1–B15), after `0983e163`** | **13 registered + 2 `DEFERRED_BEATS` = 15** (`2a4e4b61`) | **0** |

**CH03's +25 was the problem the v1 document existed to solve, and CH04 did not repeat it.** The beat
*set* never changed size between authoring and gate. This is the single strongest piece of evidence
that the manifest-driven approach works, and it should be stated plainly before anything else in this
document is read as criticism.

Two caveats on that number:

- The approval object was not a beat list. It was **42 manifest rows** (40 event pages + 2 overland
  seams) plus **42 hand-authored dispositions** — 10 `beat:`, 4 `deferred:rock_smash`, 4 `cosmetic`,
  24 `unreachable` — approved 2026-08-25 in `9bdce713`. A manifest row is not a beat 1:1.
- The count was 15 only *after* `0983e163`, a post-approval operator read-through that added four beats
  (B9, B13, B14, and B15) and redefined the `cosmetic` rule. Measured from the machine-generated
  artifact alone, the growth was +4. See §1.3(N).

The suite figure of **74/74 at gate pass** (`2a4e4b61`, ROM `5953e98f`) is the whole replayed
predecessor chain, not CH04: moki 17 + route1 61 + kevlar 60 + route2 13. Note route1 grew 60→61 in
that window — CH04's phone-rematch fix retroactively registered `route1:N5`, a beat written and
withheld since CH02 pending a converter fix that CH04 finally forced.

### 1.2 The v1 taxonomy, one round later

| Class (v1) | Status after CH04 | Evidence |
|---|---|---|
| **A. Coverage omission** | **Closed for event-shaped content; open for everything else** | Manifest enumerates event pages + seams only. B15 (a wild-encounter table) is invisible to it *by construction*; caught by human read-through (`0983e163`). `PROJECT_TODO.md` #43. |
| **B. Proxy oracle** | **RECURRED — twice, inside the pilot chapter** | See §1.2.1. |
| **C. Design misread** | **RECURRED** | B7 asserted a cave-mouth tile was BLOCKED; RMXP's real rule is that a blank-graphic event never blocks the player. Failed on both live ROMs (`ec7401d4`, `b246127d`) for its entire existence before the premise was questioned (`a06a0628`). The codebase had already corrected this *same inverted premise* once, for Route 1's shoreline events (`collect_through_block_cells`). |
| **D. No capability model** | **NOT FIXED — decided, never built** | `chapter_manifest/checker.py:45` `CapabilityModel` is a bare `Protocol`, explicitly "Not implemented here — deliberately." No `capabilities` block in `reference/chapters.json`. CH04's `rock_smash` deferrals passed on a `capability_model_unenforced` **warning**. `PROJECT_TODO.md` #49. |
| **E. Harness-shape traps** | **One closed, three new ones found** | `NOT_RUN` worked exactly as designed (§1.4). New: `interact()`'s stale field-lock sample; the `current_field_message_text` race; `route1:B14`'s RNG-timed flake truncating two full debug runs at beat 25/73. All three fixed in `3315df3a`/`a06a0628`. |
| **F. Retroactive invalidation** | **Rule-versioning shipped and works — but does not cover the live instance** | `playtest/rules.py` (`RULES`, `CURRENT_VERSION`, `lag_report`) + `reference/playtest_rule_versions.json` shipped and are correct. They catch staleness caused by *inventing a new assertion class*. They do **not** catch `PROJECT_TODO.md` #47: `kevlar.py` B25 asserts the Kevlar↔Route 2 seam is blocked, which stopped being true on 2026-08-25 when Route 2 joined the map set. No rule changed; the *world* changed. See §1.3(P). |
| **G. Blind spots** | **2 of 3 targeted spots closed** | Text-content primitive shipped (`emulator.py:1159` `current_field_message_text`, `:1294` `assert_text_contains`). Ledge directions shipped (`4709a7fe`, `terrain_tags.py`). Capability model did not (row D). New blind spots found: no PokeNav driver and no `Emulator.set_flag`, which is why CH04's B10 is deferred. |
| **H. Chapter-local primitives** | **Promoted once, then stopped** | `expected_arrival_facing`/`assert_player_facing` were correctly promoted into `assertions.py` (`a00b9337`) and `kevlar.py:486` now aliases them. But `route1.py` still defines `_cross_threshold`, `_enter_door`, and `_flag_ssa` that **shadow already-promoted public framework functions of the same purpose**, and `_walk_absorbing` + `_trainer_defeat_flag` are independently defined in *both* `route1.py` and `route2.py`. CH04 added four more chapter-local helpers deliberately. See §1.3(Q). |

#### 1.2.1 Class B in detail — the proxy oracle is not dead

Two recurrences, both inside the pilot chapter, both after the rule "assert the observable effect, never
a proxy" was written down:

1. **B2/B4 asserted "a trainer battle started"** — a proxy for "the *intended* trainer's battle
   started." The walk to Larrie crossed Timothy's event-touch tile; the wrong trainer was fought while
   Larrie's end state was asserted. **Both guards passed.** It read as a converter bug for three
   sessions before `_trigger_trainer` gained an explicit `opponent_trainer_id()` identity check.
2. **`field_locked()` as a proxy for "the script finished."** Insufficient, and this was the *second*
   occurrence — `kevlar.py` had already recorded it on 2026-08-14. CH04 hit it again and had to build
   `_settle_post_battle_script`.

The v1 rule was correct and was written down. It did not prevent either instance, because nothing
mechanically checks it. This is the live MEMORY open question ("should the checker mechanically detect
proxy assertions?") and CH04 is now two more data points in favour of yes.

### 1.3 New failure classes CH04 exposed

The v1 taxonomy does not name these. Each has at least one real instance from this chapter.

**I. Inferred world-facts asserted as if decoded.** *Three instances, all in one chapter — the largest
new class.*
- **B1's approach column** was authored at x=29 and justified as "low-risk because B25 confirmed x=28."
  B25 had only ever tested Kevlar's **own** edge, never the blocked side. x=29 mapped to map035 x=18,
  inside a blocked collision run; the crossing never happened (`5153e4ac`, found `b71f4a13`).
- **B3's item-ball approach** applied the NPC heuristic "approach from the side the sprite faces" to an
  item ball, whose graphic direction is **cosmetic**. The target (16,43) was solid terrain; greedy
  pathing then walked through Timothy's touch tile and Larrie's sight cone, absorbing wild battles
  until the retry cap tripped.
- **B6's rock approach** used the same NPC-derived rule and produced a sealed pocket reachable only by
  smashing the rock the beat exists to prove you *cannot* smash.

  All three share one root: **a rule applied outside its domain, and an inference chain presented as
  low-risk, with no artifact distinguishing "this coordinate was decoded from collision data" from
  "this coordinate was reasoned about."** All three were corrected only by a live run, or by hand-decoding
  `metatile_attributes.bin` against `Route02/map.bin` after a build existed.

**J. A harness false signal masking a real defect, causing repeated misdiagnosis.** `interact()`
sampled a stale field-lock, producing false "no script started" verdicts for any script that locks,
runs and releases inside the sampling window. Compounded with a *genuine* engine bug (the re-talk
resume address was `battleScriptRetAddrA`, firing once rather than every re-talk) producing the same
symptom. B11 was written up wrong **three times in one calendar day** — `48164d1d` → `cf7d6739` →
`1ba6e454` → root cause `5c396c74`. Two of the three were confidently stated and flatly wrong
("nothing runs, the object is not rendered"; "it was Richey" when it was Timothy). Every correction was
driven by the operator's own hand-walk, not by any harness or process check. This is not "harness blind
spot" (a *known* capability gap) — it is the harness **actively lying**, with no mechanism that treats
harness output as itself suspect.

**K. A correct empirical measurement disbelieved and shelved.** Larrie's live position (18,39) was
measured correctly, dismissed as a harness decode fault, and confirmed real a day later — a full debug
cycle lost. Distinct from a missing check or a wrong assertion target: the datum was *right and in
hand*. The underlying game fact — NPCs that walk toward the player on an event-touch battle keep the
moved position, so template coordinates are stale for every subsequent interaction — then affected
B10, B11 and B14.

**L. A latent defect visible only through a later chapter's incidentally broader requirement.** The
phone-trainer `Page2` dead-code bug shipped inside **CH02's gated ROM** (Brandon and Richey silent).
Nothing was omitted from CH02's coverage; no rule changed; no chapter went stale in the class-F sense.
It simply took until a chapter whose beat list happened to require re-talking a defeated trainer.
Nothing in the process predicts which future requirement will expose which latent defect, and nothing
estimates how much of that is still out there.

**M. Emitter-level resource constraints discovered at device-render time.** The Kevlar↔Route 2
`connections` seam rendered as garbage on-device: connected maps must share a tileset pair, and the two
maps' union exceeds pokeemerald's 1024-tile cap **by exactly 4 tiles**, with both dedup levers already
exhausted. Remedied by substituting an arrow-warp pair and a new SoT, `reference/seam_warps.json`
(`59a0a4a9`). The aggravating detail: **the very first screenshot of this seam, days earlier, showed
the corruption and was misread as "an unfilled void region."** The tile budget was then measured by
hand through the real `build_slice_tilesets` path because no tool reports it.

**N. The manifest is structurally blind to non-event content classes.** It joins `Map###.json`,
`connections.json` and `transpile_unhandled.jsonl` — so it sees event pages and overland seams and
nothing else. Encounter tables, tileset/metatile behaviour, and map connections-as-content are not
representable. B15 exists only because the operator read the list and noticed. Worse, `PROJECT_TODO.md`
#43 records that the `cosmetic` rule was **silently redefined** mid-stream (from "writes no state" to
"has no observable trigger", `0983e163`) and CH01–CH03 were never re-swept under the new definition.

**O. The deferral backlog is two unreconciled lists.** 23 deferred beats exist: CH02 has 10
(rock-gated, unblocked by CH06), CH03 has 10 (Strength-gated, unblocked by **CH25**), CH04 has 2. The
`DEFERRED_*` Python tuples in the chapter files and the `deferred:` rows in the `.dispositions.json`
files are **never cross-referenced in either direction** by any code. Nothing tracks which are now
unblocked. Re-registration is manual and by memory. v1 §4.4 decided this needed fixing; the mechanism
did not ship.

**P. World-change staleness, as distinct from rule-change staleness.** `rules.py` versioning correctly
handles "a new assertion class was invented, so prior chapters are stale." It has no answer for "the
map set changed, so a prior chapter's assertion is now asserting a falsehood." `kevlar.py` B25 is the
live instance (`PROJECT_TODO.md` #47) and it is still on `main`, still asserting a seam is blocked that
has been open since 2026-08-25.

**Q. Promotion is a judgment call, so it stops happening.** v1's finding H was correctly diagnosed and
the specific fix (promote the facing helpers) shipped. But promotion has no trigger. CH04 created
`_walk_absorbing`, `_press_a_live`, `_settle_post_battle_script` and `_trigger_trainer` chapter-local
*on purpose*, with a documented rationale. Meanwhile `route1.py` shadows three functions that were
already promoted, and two helpers are independently duplicated across route1/route2. The rule that
worked once is not self-sustaining.

### 1.4 What worked and must not be disturbed

- **The generated manifest + separate hand-authored disposition file, joined by `row_id` and guarded by
  a content hash.** The generator never writes the disposition file; `RULE_STALE_DISPOSITION` /
  `RULE_UNAFFIRMED_DISPOSITION` invalidate decisions when source data moves. The manifest surfaced a
  `_script_head` misparse affecting both of map 35's phone trainers **before any beat was written**
  (`e78b4543`).
- **`NOT_RUN` status.** Made "11 beats did not run behind the B2 blocker" a legible fact in the report
  instead of beats silently absent — exactly the CH03 defect (`e0d1a4cf`) it was built to close.
- **Rule-set versioning** (`rules.py` + `reference/playtest_rule_versions.json`) and the generated gate
  tally (`runner.py:249` `BeatTally`). No hand-maintained ledgers.
- **`DEFERRED_BEATS` naming the specific missing primitive.** B8 and B10 were written, reviewed, left
  unregistered with the blocker named, and carried into `PROJECT_TODO.md` #48 rather than silently dropped.
- **Mechanical citation triggers** (`schema.py:216` `needs_citation`, `RULE_MISSING_CITATION`) —
  populated in practice in `CH04.dispositions.json`.
- **Predecessor chaining.** It is why CH04's converter fixes immediately surfaced two silent NPCs
  already shipped in CH02.
- **Approve-the-beat-list-before-build ordering**, and the **operator read-through** — see Q9, which
  argues that read-through should be promoted from habit to gate step.

### 1.5 The one-line diagnosis

v1's diagnosis was: *every failure class is an omission that no artifact made visible*, and its test was
*does this make an omission visible, or does it rely on someone remembering?* That diagnosis was right,
the fixes built from it worked, and CH04's flat beat count is the proof.

CH04's remaining failures are a **different shape**, and the v1 test does not catch them. Nothing was
omitted from B1, B3, B6 or B7 — they were enumerated, dispositioned, approved, and *wrong*. So:

> **The beats are now complete. What they assert is not yet grounded.** Every CH04 authoring failure is
> a claim about the world — a coordinate, a passability rule, a trainer's identity, an NPC's live
> position, a tile budget — that was **inferred** rather than **decoded**, with no artifact
> distinguishing the two. The harness itself is part of the world it reports on, and it lied at least
> three times this chapter (J), so its output is not automatically grounding either.
>
> **The v2 test for every proposed fix:** *does this force a world-fact to be decoded from source data,
> or does it let an inference pass as one?* And its corollary: *when the harness and the game disagree,
> what artifact says which one to doubt?*

---

## Part 2 — Questions

Each has context, options, and a recommendation where I have one. These are the grill topics.

#### Build status, audited 2026-08-30

Each decision's own `**Adjudicated…**` line is written when the decision is made and was not being
updated when the thing shipped; six said "not yet built" about code that exists. They have been
corrected, and this index is the summary. **It is derived from the code, not from the markers** —
if the two ever disagree again, re-audit rather than trusting either.

| Q | Built? | Where it stands |
|---|---|---|
| Q0 archetype beat templates | **no** | No `template`/`archetype`/`archetype_exempt` symbol exists. Costs authoring time per chapter, not correctness. |
| Q1 provenance / coordinate-literal ban | **partial** | Slice 1's offline graph (the prerequisite) shipped; the named resolvers and the literal-ban lint did not. `chapters/route2.py:253` still declares bare int-tuples. |
| Q2 `oracle=` on beats | **no** | `chapter.py:230`'s `beat()` has no `oracle` parameter. Its stated prerequisite (`at=` enforcement) is built. |
| Q3 `blocked:` vocabulary | **partial** | Vocabulary + `assertable` shipped with slice 2; `CapabilityModel.grants_capability` is still the rejected signature (`PROJECT_TODO.md` #64). |
| Q4 input fingerprint | **no** | `content_hash` still covers only pages and connections; no seam/terrain/encounter inputs. |
| Q5 retroactive manifests + row kinds | **partial, regressed** | CH01-CH03 manifests exist but no longer load (`PROJECT_TODO.md` #65); no `PRE_MANIFEST_CHAPTER`, no `encounter_table`/`terrain` row kinds. |
| Q6 forced helper promotion | **no** | No duplicate detector; `route1.py`'s shadowing helpers are still unpromoted. |
| Q7 frame rule + conformance | **yes** | Slice 4 — `playtest/frame_rule.py`, `runner._apply_frame_rule`, `playtest conformance`. |
| Q8 contradiction ledger | **yes** | Slice 4 — `playtest/contradictions.py`. |
| Q9 read-through as a gate step | **yes** (2026-09-01) | Items 1-3 built: READ is step 5 of the 10-step loop, ahead of ROUTE (now 6); checklist + decaying appendix at `reference/guides/read_through_checklist.md`. Item 4 (route approval) was already the ROUTE step. |
| Q10 deferral backlog rule | **partial** | `blocked:tooling:` shipped; the bidirectional registration rule did not. |
| Q11 revisit chapters | **yes** | `CH07A` "Route 1 (revisit)" in `reference/chapters.json:130-133`. |
| Q12 citation-verification ledger | **no** | Parked until the CH05 branch (`PROJECT_TODO.md` #51) — do not raise before then. |
| Q13 ordering + the walk between beats | **yes** | All four slices; see the slice table and its status notes. |

**Three of the unbuilt items are the ones CH05 will actually walk into**, in this order: Q1's
literal-coordinate ban (CH05 is the first chapter authored *after* that decision, so without the
lint its chapter file reproduces exactly the pattern the decision bans); Q10's bidirectional
registration rule (CH05 will register `DEFERRED_*` rows, and CH04's own route2.py-vs-dispositions
disagreement is still undetected); and Q9 items 1-3 (CH04's highest-yield single step still has no
home in the per-chapter loop). Q0 was recommended "before CH05" and was not built — that is an
authoring-cost decision to make deliberately, not a correctness gate for a 2-map chapter.

**Status note, 2026-08-29.** Q13 slice 1 is now built and closed — landed in `f780a972`,
`364732ac`, `46bd2efe`, with the `_route_waypoints` fail-loud following it in `f705b642`, and its
exit criterion (the one-shot chapter-chain edit against the full warp graph) closed by `c9f73178`
and `31ddb7c5`.

### Q0. Should recurring event archetypes get data-driven beat templates, instead of a bespoke beat per instance?

**This is the operator's question, raised 2026-08-27, and it reframes Q1, Q2 and Q6.** Stated in his terms:
most of CH04's failures were things we had already dealt with before; a trainer battle is a prototype we
will meet hundreds more times; we should not be rewriting a test for each one, we should pipe the event's
own data into a standard test.

**The data supports it more strongly than the argument did.** Every trainer on map 35 has an identical
page structure, and the manifest already recorded it:

| Event | p0 | p1 | p2 |
|---|---|---|---|
| ev003 (phone) | battle → `beat:B2` | rematch offer → `beat:B10` | re-talk → `beat:B11` |
| ev012 (plain) | battle → `beat:B4` | re-talk → `beat:B14` | — |
| ev023 (phone) | battle | rematch offer | re-talk | 
| ev024 (plain) | battle | re-talk | — |

The `script_heads` sets are an exact recurring fingerprint — plain battle is
`{pbCallBub, pbNoticePlayer, pbTrainerBattle, pbTrainerEnd, pbTrainerIntro}`; phone battle is that set
plus `pbPhoneRegisterBattle`; the rematch offer is
`{createPhoneTrainer, pbCallBub, pbPhoneBattleCount, pbPhoneIncrement, pbTrainerEnd, pbTrainerIntro}`;
the re-talk is `{pbCallBub}` or, for phone trainers,
`{pbCallBub, pbPhoneBattleCount, pbPhoneRegisterBattle}`. Two archetypes, mechanically distinguishable
from generated data. Four bespoke beats were hand-written against them, and three of the four were wrong
in three different ways (B2 wrong opponent identity, B11/B14 wrong live position, B10 undeliverable).

**Correction to §1.2/§1.3(N) as first drafted.** B14 was *not* an instance of the manifest being
structurally blind. `map035/ev012/p1` was a generated row; the generator saw it. What missed it was the
**disposition pass** — a human skipping a row already on the page. That strengthens the archetype case:
a trainer's beats generated *as a set* cannot be picked off one row at a time and partially skipped.

**Scope of the archetype's assertion set.** It must encode CH04's hard-won fixes, not the naive version:
approach along a path derived from decoded collision and object occupancy (Q1); the correct opponent's
`opponent_trainer_id()`, not "a battle started" (Q2); the NPC's **live** position after it walks at the
player on trigger (class K); a post-battle script settle, not bare `field_locked()`; the defeat flag; and
a re-talk that produces non-empty text **matching the string the converter emitted from the RMXP source**.
That last point is the operator's "pipe in the data": expected strings come from the source event, so the
beat asserts *the ROM matches the source* rather than matching a string a human retyped — which also
converts the Unicode-apostrophe workaround (`2a4e4b61`, where the assertion was rewritten to dodge U+2019)
into a real normalization fix, because the character can no longer be dodged.

**Encounter ordering is part of this and is derivable, not guessable.** B2-before-B3 and B3-before-B2
were both bugs in the same missing computation. Entry cell, decoded collision, object facing/sight range
and event-touch tiles are all in hand; which trainers a route crosses and in what order is a graph walk.
It is the *same* BFS that Q1(d) and the unbuilt Q6.3 `requires[]` need — one piece of infrastructure
serving three questions.

**Variants to parameterize, not to fork:** double battles (the operator's call — a parameter, not a
separate beat), phone-rematch vs plain, sight-trigger vs event-touch vs talk.

**The one real counter-argument, and it is about *how*, not *whether*:** a weak archetype industrializes
a weak oracle. Today a bad assertion is one bad beat; with a template it is bad in every trainer battle
in the corpus, uniformly, and they all pass — class B at scale. This raises the stakes on Q2 rather than
arguing for delay.

**The weaker counter-argument — that we have not yet seen gym trainers, double battles, or pre-battle
branching, so the parameter schema may be wrong — is measurable rather than arguable.** A corpus-wide
census of every `pbTrainerBattle` event, grouped by page-structure signature with the structural outliers
enumerated, is running as of 2026-08-27; its result belongs in Part 4. If two templates cover ~95%, the
question is settled by measurement.

**Recommendation: build it, starting with the trainer archetype, before CH05.** I do not have a good
reason to wait.

#### DECIDED 2026-08-27 — archetype templates, delivered as helper + coverage checker

**Adjudicated with the operator. Recorded, not yet built.**

1. **Templates are helpers the author calls, backed by a coverage checker** — not a beat generator, and
   not bare helpers. Authors call a template per instance, so the chapter file stays a linear, readable,
   approvable document and registration order stays hand-controlled (registration order *is* playthrough
   order, and ordering is where CH04 bled). The checker then enforces the *set*: every `beat:` row is
   claimed by a registered beat, and **every row whose fingerprint matches a known archetype must be
   dispositioned as that archetype's beat set.**
   **Rationale — it targets the actual defect.** B14 was not a missing helper call; it was a
   *misclassification* (`0983e163`: "cosmetic was being decided on whether a page writes state"), and
   the misclassification was possible because a per-*page* question was asked about a page whose meaning
   exists only at the *event* level. Archetype-aware disposition asks the question at the right level.
   A plain helper improves each beat but leaves the set incomplete; a generator closes the set but makes
   the beat list an output rather than a document. Generation remains available later if the checker
   turns out to be doing so much work that generating is simpler.
2. **Templates must be extendable by parameter, not by fork.** A new variant means adding a fingerprint
   and a parameter, never a parallel template. Two extension seams are already known and must be
   designed in from the start: the mart's switch-gated stock (§4b.3) and the Pokémon Center's four
   trigger variants.
3. **Build set** (operator constraint: only what we have already seen or are about to see in CH05):
   - **Tier 1 — CH05 needs them:** trainer, item ball, staircase forced-move, door/warp, cave exit.
   - **Tier 2 — already-built chapters, buys retroactive coverage:** PC access, mart, Pokémon Center heal.
   - **Do not build:** sign (not an archetype, §4b.4), gift (30% regular — wait for instances),
     plain dialogue NPC (loose, and covered inside the trainer template where it matters).
4. **The trainer template's assertion set encodes CH04's hard-won fixes**, not the naive version:
   decoded-collision approach path; `opponent_trainer_id()` identity, never "a battle started"; the
   NPC's **live** position after it walks at the player; a post-battle script settle rather than bare
   `field_locked()`; the defeat flag; and a re-talk asserting non-empty text **matching the string the
   converter emitted from the RMXP source**.
5. **Settled 2026-08-28, see below:** how an instance opts out when it is genuinely special
   (Map141/ev25 and Map131/ev3 prove an escape hatch is needed, §4.4); and whether the checker's
   archetype conformance is an error or a warning for chapters already gated.

#### DECIDED 2026-08-28 — item 5 closed: counted exemption, error only on the live chapter

**Adjudicated with the operator. Recorded, not yet built.**

1. **Opt-out is an explicit, counted declaration on the row** — `archetype_exempt(row, why="...")` —
   greppable, never a comment, and tallied per chapter and corpus-wide. §4.4's census puts the baseline
   at **two** genuinely special instances in 199 maps (Map141/ev25, 12 heads on one `player_touch` page;
   Map131/ev3, the `setupWaitingRoom` / `preRoundDialogues` ceremony), so a third is visible growth
   rather than an unnoticed drift toward bypass.
2. **Not inconsistent with Q6's rejection of an escape hatch.** Q6's hatch was for *implementation
   forking*, and parameterization genuinely replaces it (`absorb_trainer=True` makes the fork
   unnecessary). This one is for *classification*: no parameter turns a 12-head gym ceremony into a
   standard trainer battle. The hatch is legitimate; the counting is what keeps it honest.
3. **Archetype conformance is an ERROR for the chapter currently being authored and a counted debt for
   chapters already gated** — the same shape and the same reasoning as Q5a's `PRE_MANIFEST_CHAPTER`: a
   gated chapter passed under a rule that did not exist yet, and a permanently-red check is one people
   learn to scroll past.

**Status: recorded 2026-08-27, build deferred.** Operator has further scope to add before the grill.

### Q1. Should beats carry machine-checkable provenance for the world-facts they depend on?

Class I is the largest new class — three failures in one chapter, each an unverified coordinate. Today a
beat's coordinates are bare integer literals in Python; nothing distinguishes `(31, 18)` decoded from
`map.bin` from `(29, 18)` reasoned about from a neighbouring chapter's beat.

Options: (a) do nothing, rely on author discipline — this is what CH04 did and it failed three times;
(b) a comment convention (`# decoded: metatile_attributes.bin` / `# inferred:`) with a grep-level lint;
(c) a real `Coord` value type carrying a provenance field, with the checker refusing `inferred`
provenance for any beat whose assertion is *about* passability or position; (d) go further — a
build-time resolver that computes approach tiles from decoded collision + object-occupancy data so the
author never types a coordinate at all.

**Recommendation: (d) where it is cheap, (c) as the backstop.** B6's fix already did (d) by hand —
derived the approach from decoded collision and object occupancy instead of the graphic-direction
heuristic. That is the correct shape and it should be a function, not a one-off. Note (d) subsumes the
unbuilt Q6.3 reachability BFS, which is the same code.

#### DECIDED 2026-08-28 — resolver only; coordinate literals banned, not annotated

**Adjudicated with the operator. Recorded, not yet built.**

1. **Option (d) is the whole answer; option (c) is rejected.** Q13's slice 1 already commits to the
   offline graph, which *is* (d). Every coordinate a chapter file uses comes from a named resolver call
   against that graph — `approach_to(map, event)`, `entry_cell(...)`, `warp_cell(...)` — so
   decoded-ness is true **by construction** rather than by declaration.
2. **Integer coordinate literals are banned in `chapters/*.py`**, enforced by lint, not by a value type.
   Rationale: a `Coord(31, 18, provenance="decoded")` is a field the *author types*, which is exactly
   the shape `at=` has today — the Q2 grill finding already named that pattern "decorative metadata"
   that teaches authors declarations are documentation. A provenance field catches an honest author's
   mismatch, not the failure mode that bit CH04 three times. Removing the surface beats annotating it.
3. **The residual tail gets one explicit, greppable escape hatch**: `raw_cell(x, y, why="...")`. The
   checker counts these per chapter and reports the count, so the un-resolved tail stays visible and is
   expected to shrink rather than quietly normalize.

### Q2. Should beats declare their oracle type so the checker can detect proxy assertions?

Class B recurred twice after the rule was written. The manifest makes the *input* side detectable — a
row tagged `giveitem` whose beat asserts only a flag — but beats are arbitrary Python, so the checker
cannot see what a beat asserts unless beats declare it.

Options: (a) leave it as a written rule; (b) a declared `oracle=` argument on `beat(...)` naming the
observable class asserted (`bag_delta`, `party_species`, `position`, `text`, `trainer_identity`, …),
cross-checked against the manifest row's effect tags; (c) static analysis of the beat body for known
assertion calls.

**Recommendation: (b).** It is the only option that closes the loop mechanically, and CH04's two
recurrences both had a manifest row whose tags would have flagged the mismatch. Cost is real authoring
ceremony on every beat — that is the trade to grill.

#### Grill findings 2026-08-27

**The ceremony objection is weaker than drafted: beats already carry declarative metadata.**
`ChapterBuilder.beat()` (`chapter.py:136`) takes `map_constant=`, `at=`, `locations=`. `oracle=` is the
same shape, not a new concept.

**But `at=` is declared and never checked, and the API says so.** From its own docstring: *"`at=` is
descriptive metadata, not a command… one whose declared `at=` disagrees with that inherited position does
not error — it silently starts somewhere else and fails later, often as a misleading pathfinding 'stuck'
error near the target."* That is v1 finding E precisely (CH03's B8 carried a hardcoded
`MAWULI_APPROACH (3,16)` that was never reachable and never noticed). **We already have one declarative
field nobody verifies; adding a second before the first is enforced only accumulates decorative
metadata.**

**Honest limit on what `oracle=` buys.** It catches a *mismatched* declaration — row tagged `giveitem`,
beat declares `oracle="flag"` → error, which would have caught CH03's three dead grants — but it catches
a mismatch, **not a lie**. An author who declares `trainer_identity` and asserts something weaker gets a
green check. Declaration is a claim, not a proof. The gap actually closes at Q0: **for templated beats
the oracle is set by the template, not claimed by the author**, so `oracle=` earns its keep on *bespoke*
beats, a far smaller population than "every beat."

#### DECIDED 2026-08-27 — `oracle=` added, coupled to `at=` enforcement

**Adjudicated with the operator. Recorded, not yet built.**

1. **Add `oracle=` to `beat()`**, scoped to bespoke beats; templated beats get their oracle from the
   template (Q0), which is where the proxy-oracle class actually closes.
2. **Land it with or after the enforcement of `at=`** by Q13's route plan. Two unchecked declarative
   fields are strictly worse than one: they teach authors that declarations are documentation. One
   enforced field teaches the opposite, and the second inherits that expectation.
3. Consequence: **Q2 depends on Q13**, joining Q3's `blocked:` derivation, Q7's oracle, and the `at=`
   check. See Q13's slice plan for how that load is sequenced.

### Q3. Build the capability model now, or defer it a third time?

Decided in v1 Q3, not built. `CapabilityModel` is a `Protocol` with no implementation;
`deferred:<capability>` (Q8.2) and the whole deferral backlog (Q8) are unenforceable as a result; CH04
passed on a warning. CH05 is a dungeon and will add its own gated content; CH06 grants Rock Smash and is
the point where 10 of CH02's deferred beats must come back.

**Recommendation: build it now, minimally.** A `capabilities` block in `reference/chapters.json` keyed
to chapter, listing what the player holds *entering* that chapter, is enough to turn the warning into an
error. The elaborate beat-index-granular version from v1 Q3 is not needed yet. The reason to do it
before CH05 rather than before CH06: CH06 is where being wrong is expensive, and CH05 is the cheap
place to find out the schema is wrong.

#### Grill findings 2026-08-27 — why this was never built, and what the data says

**The seam was never the blocker.** `checker.CapabilityModel` needs exactly one method,
`grants_capability(name) -> chapter_id | None` (`checker.py:45`). A working implementation is an
afternoon. What blocked it twice is that building it forces a commitment to a **capability vocabulary**,
and nobody had made one — the one-method seam was designed as though the hard part were plumbing.

**The vocabulary was doing two jobs and only one was enforced.** CH04's 42 rows: 13 `beat:`,
1 `cosmetic`, 4 `deferred:rock_smash`, 24 `unreachable:` — the last with free-text arguments
(`north_of_rockslide_gate`, `boxed_in_by_outer_rocks`, `rockslide_blocks_north_seam`) describing one
physical barrier that Rock Smash opens at the CH07 revisit. Most of those 24 are not unreachable; they
are blocked, and the CH07 debt they represent is currently uncountable.

**The split tracks the tool's boundary, not author care.** `_HEAD_REQUIRES` derives capability from a
row's *own script heads*. The 4 `deferred:` rows are the rock events themselves (they contain
`pbRockSmash`, so the generator proposed the capability and the author affirmed it). The 24
`unreachable:` rows are *behind* the rockslide, contain no such head, and the generator cannot see their
blocker — `schema.py:190` says so: *"Reachability-derived requirements are a second source and are not
populated yet."* **Where the machine proposed a capability the verdict was right; where a human reasoned
geographically it drifted.**

**`_HEAD_REQUIRES` was two-thirds fictional — FIXED 2026-08-27.** Of its nine heads, only `pbRockSmash`
(6 maps), `pbRockSmashRandomEncounter` (6) and `pbPushThisBoulder` (15) occur in the corpus.
`pbStrength`, `pbCutTree`, `pbSurf`, `pbWaterfall`, `pbDive` and `pbFishing` match **zero** map files —
written from general Pokémon knowledge, never checked. (Caught by the operator noticing that `pbFishing`
→ `old_rod` names a key item, not an HM.) This is the §4.7 "verify against the real source" rule
violated on the *Essentials* side; had the capability model shipped on this table,
`grants_capability("cut")` would have validated `blocked:cut` for a capability this game never spells
that way. The six phantom entries are removed and the table now carries corpus counts and a warning;
CH04's manifest is unaffected (`requires` values are only `()` ×37 and `('rock_smash',)` ×5) and
`content_hash(page)` covers the raw page dict, not derived fields, so no affirmed hash moved.
**Structural note recorded in the code:** Surf/Dive/Waterfall are terrain-tag mechanics, not event
scripts, so a head→capability table can never reach them — terrain-gated capabilities need a second
source. A corpus census of the *real* gating vocabulary (heads, terrain tags, page conditions, item
checks, and story-progression chains such as the Old Rod being gated on the first gym) is commissioned
and lands in Part 4c.

**The apparent multi-blocker case was a missing axis, not a hard blocker call.** All five rock rows carry
`requires: rock_smash`. Two (ev014, ev017) are `deferred:` — the player can stand adjacent and press A,
and be refused (that is B6). Three (ev015, ev016, ev018) are `unreachable:boxed_in_by_outer_rocks` —
they have no adjacent walkable tile because *other rocks* block them, i.e. they are behind rock_smash
**twice**, at two depths. One capability, not two. What actually differed between the two groups was
whether a **negative beat can be written today**, and there was no field for that, so authors encoded it
in the verdict name: `deferred:` drifted to mean "blocked but assertable," `unreachable:` to mean
"blocked and not assertable."

#### DECIDED 2026-08-27 — `blocked:`, split from assertability, with `unreachable` reserved

**Adjudicated with the operator. PARTIALLY BUILT (slice 2, 2026-08-29).** The vocabulary shipped:
`blocked` is a `_VERDICTS` member (`chapter_manifest/schema.py:91`), `blocked:tooling:` is handled
(`schema.py:122`, `checker.py:270`), `assertable: bool | None` exists with validation
(`schema.py:338`), and CH01-CH04 were re-dispositioned. **Not built:** the corrected
`CapabilityModel` predicate signature — `grants_capability` is still the pre-amendment shape the
Part-4c census rejected (`checker.py:59-68`), which is why 28 `capability_model_unenforced`
warnings stand (`PROJECT_TODO.md` #64).

1. **Collapse `deferred:` and `unreachable:`-by-geography into one verdict, `blocked:<capability set>`**,
   answering exactly one question: *what unblocks this row.* Geography stops being a verdict and becomes
   a note.
2. **`unreachable` is retained, narrowed** to content no chapter will ever reach — cut content, dead
   pages. It is no longer a synonym for "blocked and I gave up."
3. **Assertability is a separate field.** Whether a negative beat can be written now (walk up, press A,
   assert the refusal) is an authoring judgment with its own field and an optional beat reference — not
   a second meaning smuggled into the verdict. This lets the checker flag a `blocked:` row that *has* an
   adjacent walkable tile and *no* negative beat: the ev014/ev017 opportunity a future author would
   otherwise miss.
4. **`blocked:` takes a set, and the graph derives it.** Multi-blocker is the natural shape of a
   reachability result — the minimal set of capability-tagged obstacles whose removal opens the path —
   so the author affirms or overrides a derived value rather than inventing one, the same shape as the
   content-hash affirmation that already works.
5. **The vocabulary is closed, and comes from the corpus** (Part 4c census), never from Pokémon priors.
   Capabilities arrive by at least three routes — event heads, terrain tags, and story-progression gates
   (page conditions on named switches) — so the model must accept all three, not just heads.

**RESOLVED 2026-08-27 — sequencing.** The hand-authoring compromise is withdrawn as unnecessary: the
operator intends to build Q13's graph before CH05, so `blocked:` is **derived properly the first time**
and the vocabulary is right rather than provisional. Validation is the retroactive re-derivation of
CH04's 24 geography rows and CH02's 10 rock-gated deferrals (Q13 slice plan), not CH05's gate.

**Open — CH04 re-disposition.** *(Closed 2026-08-28, and widened — see the decision below.)* Whether to re-disposition CH04's 24 geography rows to `blocked:rock_smash`,
which would make the CH07 debt countable, or leave a gated chapter alone. Not yet ruled on.

#### DECIDED 2026-08-28 — re-disposition the whole built corpus during CH05's build

**Adjudicated with the operator. Recorded, not yet built.** Operator's call, and it widens the question:
CH05 is a thin chapter (2 maps, 3 trainers, 4 item balls), so the slack goes into retiring the
disposition debt across **all** built chapters rather than CH04's 24 rows alone. Every map is revisited
at some point, so these files are live artifacts rather than archaeology.

1. **CH01-CH04 are all re-dispositioned during CH05's build**, under the final vocabulary: `blocked:`
   with its capability set, `unreachable` narrowed to never-reachable content, the separate
   assertability field (Q3), and `blocked:tooling:` (Q10).
2. **This supersedes Q5a's lazy-affirmation clause.** Q5a chose generate-now / affirm-later to avoid a
   large pass on already-gated chapters; the operator's decision spends that pass during CH05 instead.
   `PRE_MANIFEST_CHAPTER` survives only as the state CH01-CH03 occupy between manifest generation and
   the CH05 pass, not as a long-lived debt bucket.
3. **Ordering safeguard — derive, compare, then write.** Slice 2's validation is "re-derivation of
   already-gated chapters *where the right answers are known*." If one pass both derives and writes the
   verdicts, the derivation is validated against verdicts it authored and that property is destroyed.
   So: **freeze the expected answers first** — they are known today (CH04's 24 geography rows and CH02's
   10 rock-gated deferrals both -> `blocked:rock_smash`) — then run slice 2's derivation, then diff
   against the frozen set, then commit. The diff is the validation artifact.
4. **Re-affirmation is the normal flow, not an exception.** Q3 decision 4 already makes `blocked:` a
   derived value the author affirms or overrides, so rewriting a gated chapter's verdicts under a
   corrected vocabulary is that mechanism working as designed. It also keeps the repo's only worked
   example from contradicting the narrowed `unreachable` definition.

#### AMENDED 2026-08-27 by the Part 4c census — three schema corrections

1. **`grants_capability(name) -> chapter_id | None` is the wrong signature.** Capabilities are
   **predicates over player state, not booleans**, and Uranium grants every field move by *two disjoint
   routes*: `rock_smash` is `numbadges >= 1 AND (knows ROCKSMASH OR holds BOXINGGLOVES)`, and the same
   move-or-gadget shape holds for strength/`POWERGLOVE`, surf/`SURFBOARD`, dive/`SCUBAGEAR`,
   waterfall/`CLIMBINGPICK` — the five gadgets all granted from one event (Map167/ev28) on a badge-count
   ladder, at a different point in the game than the HMs. A single granting chapter cannot express this.
2. **Some gates are not derivable at all and must be hand-annotated.** `old_rod` is granted at
   Map081/ev1/pg1 behind `var[103] >= 5`, and variable 103 is named **"Battle Var01"** — an anonymous
   scratch variable. The only artifact stating what it means is the dialogue text. A name-keyed
   classifier misses it *confidently*. So the model must accept annotation, and the checker must keep
   `derived` and `annotated` distinguishable so annotated gates stay visible for review. (Contrast
   `rock_smash`: HM06 at Map040/ev20/pg2 behind switch **55 "Gym 1 defeated"** — same kind of gate,
   properly named, fully derivable.)
3. **A capability may have more than one surface.** `strength` appears both as the engine flag
   `$PokemonMap.strengthUsed` (read only by `pbPushThisBoulder`) and as story switch 86 "Has Strength"
   (read by 58 unrelated page conditions). A classifier must union both surfaces or it under-counts.

**Corollary — `blocked:cut` and `blocked:flash` are unverifiable today.** HM01 and HM05 exist as item ids
(`reference/uranium_id_map.json:1034,1038`) and have **no grant site in the 199-map corpus**. This is the
silent-failure mode argued as hypothetical when commissioning the census; it was real.

### Q4. What detects world-change staleness (class P)?

`kevlar.py` B25 is asserting a falsehood on `main` right now. Rule-versioning cannot see it.

Options: (a) fix B25 by hand and move on; (b) content-hash the *map set and connection graph* a chapter
was gated against, and flag every chapter whose inputs moved — the same mechanism as
`RULE_STALE_DISPOSITION`, applied one level up; (c) re-run all prior chapters' manifests at every gate
and diff the generated rows.

**Recommendation: (b).** It reuses a mechanism that already works, and (c) is nearly free once (b)
exists since the generator is deterministic. Doing (a) alone guarantees a third instance.

#### Grill findings 2026-08-28 — the motivating instance was misread, twice

**B25 is not asserting a falsehood.** It probes `NORTH_EDGE_APPROACH = (28, 0)`; the Kevlar<->Route 2
seam's warp cells are `(31,0)` and `(32,0)` (`reference/seam_warps.json`, seam `kevlar_town_route_02`).
The boolean B25 asserts is still true, and the beat was already hand-annotated 2026-08-26 reasoning
through exactly this. What is stale is the beat's *description prose* ("toward unbuilt Route 2"), not
its assertion. Q4's premise as drafted — "asserting a falsehood on `main` right now" — was wrong.

**But the real gap is worse than the one drafted, and option (b) as written would have missed it.**
The seam is an *arrow-warp substitution*, taken because Kevlar + Route 2 need 1028 unique 8x8 tiles
against the GBA's 1024 cap. RMXP's `connections` array for Kevlar is therefore `null`, so
`_generate_seam_rows` emits **no row at all** for that boundary. Content-hashing "the map set and
connection graph" cannot flag a boundary that is not in the connection graph.

**The chapter's real input set is wider than `{pages, connections}`.** `content_hash` covers the decoded
page dict (`generator.py:347`) and the 6-tuple seam (`generator.py:383,396`), stored as `affirmed_hash`
and enforced by `RULE_STALE_DISPOSITION` (`checker.py:105-123`). Uncovered: `map.bin` / `border.bin`
collision, `reference/seam_warps.json`, `reference/terrain_tag_map.json`,
`reference/tileset_map.gen.json`, and the wild encounter tables.

#### DECIDED 2026-08-28 — per-chapter input fingerprint, scoped by actual use

**Adjudicated with the operator. Recorded, not yet built.**

1. **A chapter records a fingerprint of every decoded artifact its beats consumed**, not just maps and
   connections. Slice 1's graph must enumerate those inputs to build itself, so the input list is
   derived rather than hand-maintained — the §1.5 test applied to the fix itself.
2. **Scoped by use, to avoid rubber-stamp churn.** For `map.bin` the fingerprint covers only the tiles
   the chapter's route and beat targets actually touched (slice 1's graph knows them), not the whole
   map. A tile edited elsewhere in a 50x50 map must not invalidate the chapter. Small artifacts
   (`seam_warps.json`, `terrain_tag_map.json`, the map's encounter table) are hashed whole.
   **Rationale:** mass re-affirmation is how affirmation degrades into a rubber stamp, which would rot
   the one mechanism Part 3 lists as proven.
3. Option (c) — regenerate all prior manifests at each gate and diff — remains nearly free once the
   generator is deterministic, but is *not* sufficient on its own: it is blind to anything that is not
   a row, which is precisely the Kevlar seam case.

### Q5. What closes the manifest's structural blindness (class N)?

Encounter tables, tileset/metatile behaviour and connections-as-content cannot be represented as rows.
`PROJECT_TODO.md` #43. Also unresolved: CH01–CH03 were never re-swept after the `cosmetic` rule was
redefined.

Options: (a) accept it, and make the human read-through the formal compensating control (see Q9);
(b) add row *kinds* — `encounter_table`, `terrain`, `connection` — generated from the other artifacts,
so every content class is dispositionable in the same file; (c) a second manifest per non-event class.

**Recommendation: (b).** The disposition vocabulary and content-hash machinery already generalize; the
row kind is a discriminator, not a new system. And the CH01–CH03 `cosmetic` re-sweep should be scheduled
as its own task regardless of which option wins — it is a known-stale approval.

#### Grill findings 2026-08-28 — CH01-CH03 have no manifest at all

**`PROJECT_TODO` #43 understates the gap.** `reference/manifests/` contains **only**
`CH04.manifest.json` and `CH04.dispositions.json`; `git log --diff-filter=A` confirms no other
disposition file was ever added. CH01-CH03 predate the tool (`a00b9337`, "The manifest exists now, and
CH04 cannot be authored around it"). So the `cosmetic` re-sweep is not a re-sweep: three gated chapters,
106 registered beats between them, **zero dispositioned rows**.

**This blocks a decision already made.** Q13's validation section commits slice 2 to "retroactive
re-derivation of already-gated chapters, where the right answers are known — ... CH02's 10 rock-gated
deferrals must come back as `blocked:rock_smash`." That re-derivation needs CH02 rows to attach verdicts
to. CH02 has none, so slice 2's stated validation is currently unbuildable.

(For the record, the current `cosmetic` rule lives at `schema.py:64-88`: a row may be `cosmetic` only if
its effect tags are a subset of `COSMETIC_SAFE_TAGS`; `STATE_WRITING_TAGS` forbids it. Enforced by
`RULE_ILLEGAL_COSMETIC`, `checker.py:126-145`.)

#### DECIDED 2026-08-28 — retroactive manifests with lazy affirmation, plus three new row kinds

**Adjudicated with the operator. PARTIALLY BUILT, and the built half has since regressed.**
Decision 1's retroactive manifests exist (`reference/manifests/CH0{1,2,3}.manifest.json`,
`de9343cb`) but **no longer load** — slice 2 made `reachability_consulted` required and they were
never regenerated (`PROJECT_TODO.md` #65), and none has a dispositions file. **Not built:**
`PRE_MANIFEST_CHAPTER` (no such symbol), and the two new row kinds — `ManifestRow.kind` is still
`Literal["page", "seam"]` (`schema.py:228`), with `seam_warps.json` unread by the generator.

1. **Generate and commit manifests for CH01, CH02 and CH03 now.** Generation is deterministic and cheap;
   the human disposition pass is the expensive half and is *not* required up front.
2. **Un-affirmed rows are a counted debt, not an error.** A distinct checker state
   (`PRE_MANIFEST_CHAPTER`) reports the count rather than failing the gate. **Rationale:** a
   permanently-red check is one people learn to scroll past, and it would protect nothing. The point is
   to make the debt *countable* instead of *absent* — §1.5 applied to this gap.
3. **Affirm on demand.** CH02's rock-gated rows are affirmed as part of slice 2, because its validation
   needs them. The rest is scheduled, not blocking.
   **SUPERSEDED same day** by Q3's "re-disposition the whole built corpus during CH05's build": the full
   pass happens during CH05 rather than being deferred, so `PRE_MANIFEST_CHAPTER` is only the transient
   state CH01-CH03 occupy between generation and that pass.
4. **Three new row kinds** (option (b)), since the disposition vocabulary and content-hash machinery
   already generalize:
   - **seam extended to `seam_warps.json` substitutions** — a boundary whose RMXP `connections` entry is
     `null` because the tilesets could not merge currently generates **no row at all**. This is the
     Kevlar<->Route 2 hole in Q4's findings.
   - **`encounter_table`** — one row per map's wild table.
   - **`terrain`** — one row per **distinct behaviour class present in the map** (ledge, tall grass,
     water, sideways stairs, ice, ...), asking "does any beat exercise this behaviour here?"
     **Explicitly not per tile, and not per region:** hundreds of rows per map is not a disposition
     surface, it is noise, and it would drown the Q9 read-through this same question relies on. The
     by-class form is what would have surfaced the 222 unroutable sideways-staircase instances (§4b.2).

### Q6. What forces helper promotion, given that judgment does not (class Q)?

Options: (a) status quo; (b) a mechanical duplicate-detector in CI over `chapters/*.py` private
functions (name or AST similarity) that fails the gate on a cross-chapter duplicate; (c) a rule that any
helper used by two chapters *must* be promoted as part of the second chapter's gate; (d) additionally,
ban chapter-local functions that shadow a public `assertions.py` name.

**Recommendation: (c) + (d), with (b) as the enforcement.** (d) is trivial and catches `route1.py`'s
three shadowing definitions today. Grill point: CH04's decision to keep `_walk_absorbing` local had a
*stated, reasonable* rationale (rate tuning differs per map) — a blanket rule overrides that, so the
rule needs an explicit escape hatch or it will be resented and worked around.

#### Grill findings 2026-08-28 — the census refutes CH04's stated rationale

**The rationale this question was drafted to protect is false.** CH04 kept `_walk_absorbing` local on the
stated grounds that rate tuning differs per map. `route1.py:376` and `route2.py:470` are **byte-identical**
in control flow, parameters, defaults and the `WalkInterrupted` / `is_trainer_battle` /
`resolve_interruption` logic; both draw `_MAX_ABSORBED_INTERRUPTIONS` and `_WALK_ABSORBING_FRAME_BUDGET`
from module-local constants of the same value and derivation. Only the docstring differs. Nothing was
tuned. `_trainer_defeat_flag` (`route1.py:570`, `route2.py:505`) is likewise byte-identical.
"I have a reason" is therefore not a sufficient escape hatch — it was exercised once, on a reason the
data refutes, and went unchallenged for a whole chapter.

**The real cost is the near-duplicate, not the exact one.** `route1.py:521 _approach_moving_npc` and
`kevlar.py:413 _approach_patrol_npc` are the same algorithm — read the NPC's live `object_event` position,
subtract `_DIR_VECTOR[facing]`, walk, face, `interact()`, retry up to `_MAX_PATROL_APPROACH_ATTEMPTS` —
with **one silent difference**: route1's approach step absorbs incidental battles
(`_walk_absorbing(..., absorb_wild=True, absorb_trainer=True)`), kevlar's calls bare `emu.walk_to` and
does not. Copy-drift producing a latent flake, invisible to any name-based detector.

**Full census.** Shadowing: 3, all in `route1.py` — `_cross_threshold` (:302) and `_enter_door` (:311)
are genuine supersets of the `assertions.py` originals (they swap `emu.walk_to` for `_walk_absorbing`);
`_flag_ssa` (:562) is a one-line delegating wrapper hardcoding `map_num=33`. Cross-chapter exact
duplicates: 2 names, 4 definitions. Near-duplicates by body: 1 pair. Module-level function counts:
moki 21, route1 42, kevlar 43, route2 21. (`kevlar.py:459-464` and `route1.py:319-320` also bind shared
names by plain assignment — visible traces of prior promotions, and why the shadowing count is not
higher.)

#### DECIDED 2026-08-28 — (c) + (d), enforced by (b); the hatch is parameterization

**Adjudicated with the operator. Recorded, not yet built.**

1. **Any helper used by two chapters must be promoted** as part of the second chapter's gate, and
   **chapter-local functions may not shadow a public `assertions.py` name.**
2. **Enforced mechanically by an AST duplicate/near-duplicate detector in CI** that fails the gate.
   It must compare **bodies, not names** — a name-based detector misses the `_approach_*` pair, which is
   the instance that actually cost something.
3. **No rationale-comment escape hatch.** Differing behaviour is expressed as a **parameter on the
   promoted helper** (`absorb_trainer=True`), never as a chapter-local fork. This is Q0's decided rule —
   *extend by parameter, never by fork* — applied one level down, and the `_approach_*` pair is exactly
   what a fork costs.
4. The two `route1.py` supersets are the migration's first cases: they become parameters on the shared
   `cross_threshold` / `enter_door`, not private overrides.

### Q7. When the harness and the game disagree, what says which to doubt (class J)?

The most expensive single arc of CH04. Three wrong diagnoses in one day, all resolved by the operator
hand-walking the ROM.

Options: (a) nothing systematic — accept that live human observation is the tiebreaker; (b) a harness
self-test suite that runs known-good primitives against a known-good ROM state before each debug
session, so a lying primitive is caught before it is trusted; (c) a rule that any primitive implicated
in a diagnosis must be independently corroborated by a second, differently-implemented read before the
diagnosis is written down; (d) require a contact-sheet frame as evidence for any claim of the form "X
did not happen."

**Recommendation: (b) + (d).** (b) would have caught both the `interact()` stale sample and the
`current_field_message_text` race directly. (d) is cheap and specifically targets the two confidently
wrong write-ups, both of which were negative claims ("nothing runs", "the object is not rendered") that a
single frame would have refuted. (c) is the most rigorous and the most expensive; worth grilling.

#### Grill findings 2026-08-27

**Existing harness tests cannot catch this class, structurally.** They test *pure functions against
fakes* — `decode_text_bytes` with a synthetic charmap, `_plan_route` against `_FakeRouteEmu`. Both CH04
lies were **liveness** bugs: `interact()` sampling a stale field-lock, and `current_field_message_text`
gating on "a draw task is running" rather than "the box is on screen." Neither is a logic error; both are
timing against a running ROM. That is how 112 test files and a green suite coexisted with a harness that
lied three times in one day.

**The seed-blob maintenance objection was wrong — withdrawn.** Seeds are ROM-hash keyed
(`available_seeds` returns only non-stale ones), but the runner **writes a fresh blob per beat on every
run** (`runner.py:148` snapshots save blocks; `305`/`322` write blob + meta). Regeneration is a byproduct
of the run, not extra work.

**The real problem is oracle circularity.** A conformance suite needs a statement of what the primitive
*should* have returned. If that expectation comes from the harness, a lying primitive and a lying oracle
agree and the suite goes green — `interact()`'s stale sample would have passed a suite whose
expectations `interact()` recorded. Only two independent oracles exist: **decoded map data** (which is
Q13's offline graph) and **a human reading a frame** (the contact sheet).

**Therefore Q7 and Q13.1 are the same mechanism.** "Does the harness's live read agree with
offline-derived truth?" is simultaneously the conformance check and the plan-divergence check. Building
them separately builds one thing twice.

#### DECIDED 2026-08-27 — enforced frame rule now; conformance suite folded into Q13

**Adjudicated with the operator. BUILT 2026-08-30** (Q13 slice 4, `cd13c3e1`): the frame rule is `playtest/frame_rule.py` + `runner._apply_frame_rule`; the conformance suite is item 2's one-mechanism version — `contradictions.ContradictionLedger.conformance()`, read out by `python -m rpg2gba.playtest conformance`, with no second expectation table.

1. **The frame rule is enforced by the runner, not left as a discipline.** Any beat failure whose claim
   is a negative — "nothing runs", "the object is not rendered", "no script started" — requires a
   captured frame. The runner refuses to record such a failure without a `mark_frame()` in that beat.
   Rationale: §1.5's own test disqualifies fixes that rely on someone remembering, and a written
   discipline is exactly that. Both of CH04's confidently-wrong write-ups were negative claims that one
   frame would have refuted; each was eventually corrected by the operator hand-walking the ROM to
   produce that very frame, days and several commits later.
2. **The conformance suite is built together with Q13's divergence check, using the offline graph as its
   oracle** — one mechanism, not two.
3. **Option (c) — a conformance suite with hand-established expected values — is rejected.** It is
   available sooner but introduces a second hand-maintained source of truth that rots silently, which is
   a fresh instance of the class this document exists to eliminate.

### Q8. What is the rule for handling a measurement that contradicts the model (class K)?

The Larrie position datum was correct, in hand, and thrown away. This is a process/discipline question
more than a tooling one, and I am least confident here.

Options: (a) nothing; (b) a standing rule that a measurement is never overruled by an inference —
if a decoded read disagrees with the model, the model is wrong until a *second measurement* says
otherwise; (c) require contradictions to be logged as findings rather than resolved in-line.

**Recommendation: (b)**, stated in `CLAUDE.md` where it will actually be read, not in a reference doc.
It is the shortest rule that would have prevented a full lost cycle. Grill whether it is too absolute —
harness reads genuinely *were* unreliable (class J), so "measurement beats inference" and "the harness
lies" are in direct tension. That tension is the real question and I do not have a clean answer.

#### Grill findings 2026-08-27 — neither side can be privileged

The draft rule "a measurement is never overruled by an inference" does not survive Q7. In CH04 the
harness genuinely *was* lying, so dismissing Larrie's (18,39) reading was a **defensible** call that
happened to be wrong — and `interact()`'s false "no script started" was *also* a measurement. A rule
privileging measurements would have been right about one and wrong about the other.

**The defect was not picking the wrong side. It was closing a contradiction without resolving it.** The
datum and the model disagreed, someone chose, and the choice was recorded as a conclusion rather than as
an open question. Same shape as §1.5: what went invisible was a *known disagreement*.

Precedent for the right posture already exists in the harness: **flake classification** refuses to let an
ambiguous result be interpreted — run, rerun once, classify pass/flake/fail. It resolves rather than
asking the author to judge.

#### DECIDED 2026-08-27 — contradictions are recorded and carried, not blocking

**Adjudicated with the operator. BUILT 2026-08-30** (Q13 slice 4, `cd13c3e1`): `playtest/contradictions.py`. Append-only, non-blocking, carried into `observed_beats/<chapter>.json` and the map viewer; nothing may branch on its contents.

1. **A measurement/model contradiction is a recorded finding, not a blocking one.** Work continues on a
   **stated assumption**; the contradiction is carried forward in the artifact until explicitly closed.
2. **Not blocking, deliberately.** `route1:B14`'s RNG-timed facing check is indistinguishable from "not
   yet fired" and truncated two full CH04 debug runs; a blocking rule would have halted work on genuine
   noise. The CH04 failure was never that work continued — it was that the disagreement **vanished**,
   with nothing carrying it. A carried contradiction would have resurfaced on the next Larrie beat
   instead of being rediscovered a day later.
3. **Resolution is against an independent oracle** (Q7): the offline graph, or a captured frame — never
   against another inference.

### Q9. Should the operator read-through become a formal gate step?

`0983e163` — a manual read of the generated beat list — added four beats and corrected the `cosmetic`
rule definition. It was the highest-yield single step in the chapter, and it appears nowhere in the
written process (`BUILD_PLAN.md`'s per-chapter loop does not mention it).

**Recommendation: yes, and name what it is for.** Its value is precisely that it catches what the
manifest is structurally blind to (class N) — so it should be a checklist with the known blind spots
enumerated ("is there an encounter table? a terrain behaviour? a connection?"), not an open-ended
"read it over." If Q5(b) lands, this checklist shrinks accordingly.

#### DECIDED 2026-08-28 — formal step, framed on verdict-correctness

**Adjudicated with the operator. Recorded, not yet built.**

**Reframing, because Q5b changes what the checklist is for.** Q5b converts three of the drafted
blind spots into generated rows, so a blind-spot checklist trends toward empty. And the read-through's
actual CH04 yield was not a blind spot: `0983e163` touched only rows that were already on the page. What
it found was that **`cosmetic` was asking the wrong question** — a verdict-*definition* error — and that
a human had skipped a row that was visible (the B14 miss, which §1.2 already reclassifies as a
disposition failure rather than a generator one). Row kinds do not touch either.

1. **The read-through becomes a named step in `BUILD_PLAN.md`'s per-chapter loop**, positioned **before**
   approve-before-build, where it ran in CH04.
2. **Its checklist is framed on verdict-correctness**, not enumeration: *is each verdict answering the
   right question for this row's kind*, and *was any row on the page skipped*.
3. **The blind-spot list is kept as an appendix that decays** — each row kind Q5b lands deletes an item
   from it, so the checklist shrinks as the generator grows rather than accumulating inapplicable
   ritual.
4. Once slice 3 lands, the read-through covers **the route plan as well as the beat set** — consistent
   with Q13's "what the operator approves is the route, not just the beat set."

**Status note, 2026-08-30 — item 4 is half-built, items 1–3 are not.** Slice 3 landed (`513b0f00`), and
with it a **ROUTE step at position 5 of `BUILD_PLAN.md`'s per-chapter loop**: solve, read the summary for
foreign-trigger crossings, operator approves the *order*, write `reference/routes/CHnn.route.json`, then
register the beat groups in that order with `RULE_ROUTE_ORDER` holding the two together. So "the operator
approves the route, not just the beat set" is now a written step rather than an intention. What is still
**not** built is the read-through itself (items 1–3) — §4b.5's step is still unnamed in the loop, and the
verdict-correctness checklist and its decaying blind-spot appendix do not exist. Item 4 says the
read-through *covers* the route plan; today the route plan is approved on its own, ahead of a read-through
that has no written home.

**Built 2026-09-01 — items 1-3 landed.** READ is now a named step at position 5 of the
per-chapter loop, ahead of ROUTE (which moved to 6), so the inversion described above is
closed: the read-through runs before the operator signs off on the route order. The
verdict-correctness checklist and the decaying blind-spot appendix live at
`reference/guides/read_through_checklist.md`. The appendix already carries a worked decay —
diagonal staircases were struck from it the same day, when the generator learned to emit
`terrain` rows (`PROJECT_TODO.md` #54).

### Q10. Deferral backlog: reconcile the two lists, and what about CH25?

Class O. Two lists, never cross-checked, 23 beats. CH03's 10 are blocked until **CH25** — twenty
chapters away.

Options for the reconciliation: (a) checker rule requiring every `deferred:` disposition row to have a
matching `DEFERRED_*` entry and vice versa — mechanical, cheap, closes the class; (b) generate the
Python tuples from the disposition file so there is one source. For CH03's CH25 problem specifically:
(c) accept a 20-chapter hold; (d) revisit whether those beats can be reached earlier.

**Recommendation: (a) now, (b) later if (a) proves noisy; and (c) for CH25 — but only once the Q3
capability model can *prove* the block, so the hold is a fact in a file and not a memory.**

#### Grill findings 2026-08-28 — the drafted rule has an axis error, and one list is lying

**The two lists are not the same kind of thing.** `DEFERRED_*` entries are about **beats**; disposition
rows are about **event pages**. "Every `deferred:` row must have a matching `DEFERRED_*` entry and vice
versa" compares mismatched axes, and on CH04 — the only chapter where a comparison is possible at all —
it scores **0 agreements against 28 rows and 2 entries**. That is a category error, not a backlog result:
the 28 `deferred:`/`unreachable:` rows all sit behind beat **B6**, which *is* registered, so the drafted
rule would flag every one of them as an orphan wrongly.

**A live contradiction on `main`.** `route2.py`'s `DEFERRED_BEATS` lists **B8** ("restore once CH05
stages Map036") and **B10** ("needs a PokeNav-driving primitive ... or an `Emulator.set_flag` primitive
... none exists") as not registered. `CH04.dispositions.json` disposes their rows — `map035/ev001/p1`
and `map035/ev003/p1` — as `beat:B8` and `beat:B10`, i.e. covered by a registered beat. One of the two
artifacts is wrong; `route2.py` was committed twice (08-26, 08-27) after the dispositions were last
touched (08-25).

**A third blocker kind exists and Q3's vocabulary has no slot for it.** B10 is blocked on a **missing
harness primitive** — not a capability, not a chapter. `blocked:<capability set>` answers "what unblocks
this row" with capabilities only, so B10 has nowhere legal to go.

**Corrected inventory: 22 Python deferrals, not 23.** CH02 10 (`DEFERRED_ROCK_GATED`: B3, B5, B6, B9,
B10, B12, B14b, B15b, B15c, B15d — rock_smash, stated as CH06); CH03 10 (`DEFERRED_BEATS`: B15b, B18b,
B26, B23b, B19-B24 — HM04 Strength, stated as CH25); CH04 2. CH02 and CH03 stay unverifiable until
Q5a's retroactive manifests exist.

#### DECIDED 2026-08-28 — registration-based rule, plus `blocked:tooling:`

**Adjudicated with the operator. PARTIALLY BUILT.** `blocked:tooling:<primitive>` shipped with
slice 2 (`chapter_manifest/schema.py:122`, `checker.py:270`). **The bidirectional registration rule
did not** — nothing cross-references `DEFERRED_BEATS`/`DEFERRED_ROCK_GATED` against disposition
rows; `RULE_ORPHAN_DISPOSITION` (`checker.py:345`) checks generated-row-vs-disposition, a different
mismatch. So CH04's own route2.py-vs-dispositions disagreement is still undetected.

1. **The checker rule is registration-based and bidirectional on the correct axis:** every `beat:Bn`
   disposition row must name a **registered** beat, and every `DEFERRED_*` entry must have its row
   dispositioned as something **other than** `beat:`. This fires on CH04's B8/B10 contradiction today.
2. **Q3's `blocked:` vocabulary gains a third kind, `blocked:tooling:<primitive>`**, so a missing harness
   primitive becomes a countable debt against the harness instead of untracked free text — the same
   shape the Part 4c census flagged for `old_rod`, where the only artifact stating the gate was prose.
3. Option (b) — generating the Python tuples from the disposition file — stays available but is not
   taken now: it would make the chapter file partly generated, cutting against Q0's decision that the
   chapter file remains a linear, readable, approvable document.
4. **The CH25 half of this question is settled in Q11**, where the map-coverage audit changes it.

### Q11. v1 §5.5's revisit chapters — decide, or defer a second time?

v1 recommended adding a Route 1 revisit chapter (and a mechanical chain-coverage audit for unmodelled
walked legs). Neither shipped. `reference/chapters.json` still has no chapter covering map 33 or map 31
after CH02/CH03. This blocks the same 10 CH02 beats that Q10 covers.

**Recommendation: run the mechanical audit now** (it is a small script over `chapters.json` +
`connections.json`, and it is the cheap half), **and let its output decide the chapter question**
rather than re-litigating from the same evidence v1 already had.

#### Grill findings 2026-08-28 — the audit ran; the hold is permanent, not 20 chapters

**The mechanical audit v1 asked for has now been run.** `reference/chapters.json` defines 59 chapters
covering 187 distinct map ids (CH01-CH04 built, the rest planned). **Map 33 appears in exactly one
chapter's `maps` array — CH02. Map 31 appears in exactly one — CH03.** Neither is revisited anywhere in
the plan.

**This reframes Q10's CH25 answer.** CH03's 10 deferrals wait on HM04 Strength at CH25, but CH25 does
not cover map 31; CH02's 10 rock-gated deferrals point at CH06/CH07, but CH07 is the Route 2 revisit
(maps 35, 40), not Route 1. **All 20 stranded beats are held permanently, not for 20 chapters.**
"Accept a 20-chapter hold" was never the actual choice on offer.

**The audit's connectivity half is not trustworthy yet.** It reported zero uncovered-but-adjacent maps,
but the only connection graph on disk is `output/uranium-build/connections.json` — **14 entries**,
overland seams only, no doors or caves, and untracked by git (`.gitignore: output/`). That check cannot
see most of the graph, so its clean result is weak evidence.

#### DECIDED 2026-08-28 — deferred once more, but bound to slice 1's exit criteria

**Adjudicated with the operator. BUILT 2026-08-29**: the chain edit landed against slice 1's full warp graph — `reference/chapters.json` gained `CH07A` "Route 1 (revisit)" (`chapters.json:130-133`, atlas §7), restoring CH02's 10 deferred beats.

1. **No chapter-chain edit now.** The chain is fixed **once**, against the full warp/door connectivity
   that Q13 slice 1's offline graph produces, rather than twice against a 14-entry overland graph that
   may be hiding other coverage holes.
2. **This is not an open defer.** The corrected coverage audit — re-run against slice 1's graph, listing
   every map covered by no chapter and every stranded deferral — is an **exit criterion of slice 1**,
   not a follow-up task. v1 deferred this question once already and it went invisible; a defer with no
   trigger is the §1.5 failure applied to our own process.
3. **What the re-run must decide:** whether maps 33 and 31 get dedicated revisit chapters (preserving
   *chapter = one ROM-test scenario*) or are folded into CH07 and CH25 (cheaper, but each gate then
   covers two disjoint routes). Deciding this is part of slice 1's close-out, not a later grill.
4. Until then the 20 stranded beats stay countable via Q10's registration rule and Q3's `blocked:`
   verdicts — the hold is a fact in a file, which was v1's requirement.

### Q12. Q5.1's citation-verification experiment — CH05 is the deciding data point.

`PROJECT_TODO.md` #51: CH04's pass happened informally, but **no ledger artifact was ever produced**, so
the "silent-pass" metric the decision was supposed to rest on does not exist for CH04 either. If CH05
runs the same way, the experiment will have consumed two chapters and produced no decision data.

**Recommendation: build the JSONL ledger before CH05 starts, or formally abandon the experiment.**
Grill which — a half-run experiment is worse than either.

#### Grill findings 2026-08-27 — measured on CH04's real manifest

**The pass is far cheaper than v1 feared.** CH04: **18 of 42 rows citation-triggered (43% selectivity)**,
but only **6 of those are dispositioned as beats** — `ev001/p1` (B8), `ev003/p0` (B2), `ev003/p1` (B10),
`ev003/p2` (B11), `ev009/p0` (B3), `ev012/p0` (B4). v1 worried the trigger might flag most of a map; the
verification pass is six rows for a whole chapter.

**But the trigger cannot see the class it exists for.** Finding C is design misreads, and CH04's one
genuine instance — **B7**, the inverted RMXP passability premise that failed on both live ROMs for its
entire existence — is **not** citation-triggered: `map035/ev001/p0` has no unrecognized heads and zero
script-typed conditions. Nor are B9, B12, B13 or B14. B7's misread was not in the Ruby; it was in RMXP's
*page semantics*, which the trigger's two conditions do not reach.

Note also that the flagged set looks well-targeted partly for a tautological reason: every trainer battle
is 111-wrapped, so trainers auto-flag, and trainers are where CH04's trouble was. The correlation is
weaker evidence than it first appears.

#### DECIDED 2026-08-27 — reconstruct CH04's half, and widen the trigger as a separate question

**Adjudicated with the operator. Recorded, not yet built.**

1. **Reconstruct CH04's verification pass retroactively.** Everything required still exists: the six
   flagged beat rows, the gate ROM (`5953e98f`), and the author's original assertions in `route2.py`'s
   git history. A fresh verifier that has never seen `route2.py` satisfies v1's blind requirement
   genuinely. This restores the two-chapter cumulative sample the decision rule demands, and costs six
   rows. The ledger (JSONL, per v1 Q5.1's schema) is written for CH04 as part of this, then CH05 runs
   into the same ledger.
2. **Widen the citation trigger** so structural-semantics rows like B7 are reachable — currently the
   trigger fires only on unrecognized heads or script-typed conditionals, both Ruby-shaped.
3. **Keep 1 and 2 separate.** The experiment measures whether a blind second read is worth its cost *on
   the rows it sees*; that is a fair question independent of which rows it sees. Conflating them would
   let a widened trigger's results read as a verdict on the pass, or the reverse.

**Unchanged:** v1's decision rule stands — evaluate cumulatively across CH04 + CH05; keep on ≥1
silent-pass; abandon on zero silent-passes with false positives consuming operator time.

---

### Q13. Chapter-arc ordering and the walk between beats

**Raised by the operator 2026-08-27.** Ordering bit CH04 twice: B2 registered before B3, so the walk to
Larrie crossed Timothy's event-touch tile (wrong trainer fought, both guards passed, read as a converter
bug for three sessions); and B14 registered at the end, requiring a walk back to an NPC who had left the
object spawn window and was unreadable.

**What exists today: nothing at chapter scope.** `Emulator._plan_route` (`emulator.py:1598`) is a
*runtime*, per-leg Dijkstra over the live collision snapshot. Its own docstring lists the gaps, and they
are the gaps that bit us:

- It avoids warp tiles and tiles *held* by active object events, but **sight cones are not modelled
  anywhere** — a trainer whose cone reaches several tiles is invisible to it.
- On planning failure it falls back to `_walk_greedy`, which has none of those protections. **That is
  the mechanism of B3.**
- 4-neighbour, so sideways staircases are unroutable and "must be stepped manually by the scenario" —
  against **222 corpus instances** (§4b.2).
- Elevation deliberately unmodelled; a cliff-rim edge is planned through and presents as an ordinary
  stuck walk.
- It plans from live state at runtime, so **there is no artifact to review before the ROM runs.**

Chapter-arc ordering is convention only — "registration order is playthrough order," enforced by nothing
and recorded only in a commit message (`0f46cb2e`).

**The two bugs are different constraints, and one fix does not cover both.** B2/B3 is a *path* problem:
the segment from beat N's end to beat N+1's target crosses a trigger. B14 is an *ordering* problem plus
an object-spawn-window problem. Q0's templates fix B14's shape **only if templates emit a contiguous
beat group** — battle and re-talk adjacent — with ordering operating on groups, not individual beats.
That property is doing the work and must be explicit.

#### DECIDED 2026-08-27 — offline traversable graph, consumed by the runtime, visualized in the viewer

**Adjudicated with the operator. BUILT 2026-08-29/30** across slices 1-4 — see the slice table below and its status notes. `src/rpg2gba/traversal/` (graph, triggers, reachability, world), `src/rpg2gba/routing/` (solver, plan, pathing, connections), `RULE_ROUTE_ORDER` (`chapter_manifest/checker.py:46`), and the viewer's planned/walked overlays.

1. **An offline traversable graph is the single source of truth for walkability**, derived from decoded
   data with no ROM: collision + staircases + **ledge directionality** (one-way — ignoring it plans
   impossible returns) + warps + elevation.
2. **The runtime planner consumes it** rather than re-deriving walkability from the live snapshot.
   Operator's explicit call. This closes the "two implementations of walkable" risk by construction
   rather than by reconciliation — see Q13.1 for what remains.
3. **A trigger overlay** on that graph: per event, the tiles that fire it — event-touch, player-touch,
   and for trainers the **sight cone** (facing + range, occlusion-checked).
4. **A per-chapter route plan artifact**, derived and reviewed before the build: nodes are the entry
   cell, each beat *group*'s interaction cell, and the exit; precedence constraints come from the
   manifest (an event's page 1 can only be beat'd after page 0 fired — the self-switch dependency is in
   the data); minimize backtracking subject to **no path segment crossing a trigger that is not its own
   destination**. What the operator approves is the **route**, not just the beat set.
5. **Checker rules that follow:** registered beat order must match plan order; every trigger crossing is
   either the target or explicitly declared; any beat reading an NPC's live position must have that NPC
   inside the spawn window at that point in the route.
6. **Visualized in the map viewer.** Extend the events page with a planned-route overlay — basic first
   (which tiles the planned route covers), expandable later. This joins the two layers
   `map_viewer_events.py:575 beat_markers()` already serves: `declared` (beat target x/y from
   `beat.locations`) and `observed` (actual `player_pos` per beat enter/exit, with status, from
   `output/playtest/observed_beats/*.json`).
   **Rationale beyond visualization:** planned-vs-observed divergence is the fail-loud signal for
   offline/runtime disagreement. Without it, that disagreement presents as a mystery stuck walk — the
   class-J shape (§1.3) that cost CH04 a full debug cycle.

**This is the fourth consumer of one piece of infrastructure** — Q0's decoded approach paths, Q1(d)'s
provenance, Q6.3's unbuilt `requires[]` reachability, and now routing all need the same graph. That
consolidation is the argument for building it properly rather than patching `_plan_route`.

#### Q13.1 — what happens when the offline graph and the ROM disagree? *(decided 2026-08-28)*

Decision 2 removes the *duplicate-implementation* risk but not the *wrong-model* risk: the offline graph
can be wrong about the real engine. Sight-cone semantics, sideways-staircase collision
(`GetSidewaysStairsCollision`, `GetRightSideStairsDirection`) and the object spawn window all live in
engine C, and **§4.7 requires verifying against the fork rather than from memory** — the ledge-direction
derivation is already flagged as hardware-unverified until CH07.

Options: (a) trust the offline graph, fail loud on any runtime stuck-walk; (b) have the runner record the
walked path and **fail the beat on any divergence from plan**, not just on a stuck walk; (c) treat
divergence as a warning and surface it in the viewer only.
**Recommendation: (b).** A silently-diverging route is how B3 passed its guards. Grill whether
per-tile-exact divergence is too strict — a re-plan around a patrolling NPC is legitimate divergence, so
the rule probably needs to be "diverged onto a trigger tile" rather than "diverged at all."

#### DECIDED 2026-08-28 — trigger divergence fails; all other divergence is a Q8 carried contradiction

**Adjudicated with the operator. BUILT 2026-08-30** (slice 4): `runner.DivergenceError` fails a beat on a divergence onto a trigger tile; every other divergence is recorded in Q8's ledger as `contradictions.KIND_OFF_PLAN` and carried.

**The trigger half was already settled** by slice 4's own text ("fail on divergence **onto a trigger
tile**, not on any divergence"). The open half was the other one, and it is the more important:

1. **Non-trigger divergence is the wrong-model signal.** A path that diverges without touching a trigger
   tile is precisely evidence that the offline graph is wrong about the engine — sideways-stairs
   collision, sight-cone semantics, the object spawn window, the hardware-unverified ledge derivation.
   That class of error will essentially never land on a trigger tile, so a trigger-only rule leaves it
   silent, and it re-presents as a mystery stuck walk: the class-J shape that cost CH04 a debug cycle.
2. **It cannot be a failure either.** A legitimate re-plan around a patrolling NPC diverges every run,
   and `route1:B14` already demonstrated that blocking on ambiguous evidence truncates real work.
3. **Therefore Q13.1 is not a new mechanism — it is Q8's contradiction ledger** with the offline graph
   as the *model* and the walked path as the *measurement*. Recorded and carried until closed against an
   independent oracle; never blocking. Slice 4 builds one thing, not two.
4. **Surfaced in the viewer** alongside `declared` and `observed`, per Q13 decision 6 — planned-vs-observed
   divergence is the fail-loud rendering of the carried contradiction.

#### Q13.2 — does the runner record the walked tile path? *(decided 2026-08-28)*

`beat_markers()`'s `observed` layer currently holds **enter/exit snapshots only** — two points per beat,
not the tile sequence. Rendering observed-vs-planned, and enforcing Q13.1(b), both require the runner to
log the path it actually walked. Cost: a per-step append in `walk_to`, and a larger
`observed_beats/*.json`. **Recommendation: yes, record it** — it is the prerequisite for both, and it is
also the artifact that would have shown B3 walking through Timothy's tile the first time it happened.

#### DECIDED 2026-08-28 — yes, the runner records the walked tile path

**Adjudicated with the operator.** Confirmed as drafted, and it is now load-bearing rather than
optional: slice 4's trigger-divergence check and Q13.1's carried contradiction *both* require the tile
sequence, and neither can exist without it. Cost is a per-step append in `walk_to` and a larger
`observed_beats/*.json`; accepted. It is also the artifact that would have shown B3 walking through
Timothy's tile the first time it happened.

#### DECIDED 2026-08-27 — slice plan, and validation against already-gated chapters

**Adjudicated with the operator. Operator intends to build all of Q0/Q2/Q3/Q7/Q8/Q13 before CH05.**

Four slices, dependency-ordered; each ends at something checkable, so a wrong slice is caught before the
next depends on it.

| Slice | Contents | Ends at |
|---|---|---|
| **1 — graph, and `at=` becomes real** | Offline traversable graph from decoded data: collision, staircases, ledge directionality, warps, elevation. Library + CLI dump. `_plan_route` consumes it instead of the live snapshot. Enforce `at=`: a declared position must be reachable and must match where the previous beat leaves the player. | `at=` stops being decorative — kills v1 finding E (B8's unreachable hardcoded coordinate) and unblocks Q2. |
| **2 — trigger overlay + reachability** | Per-event trigger tiles: event-touch, player-touch, sight cones (facing + range + occlusion). Reachability from entry with capability-tagged obstacles removable. | Three at once: `blocked:<set>` derivation (Q3), the unbuilt `requires[]` reachability half (Q6.3), and "does this path cross a trigger that is not its destination" (the B2/B3 class). |
| **3 — route solver, plan artifact, viewer overlay** | Order beat *groups*; emit `reference/routes/CHnn.route.json`; checker enforces registration order == plan order; viewer renders planned tiles beside `declared` and `observed`. | The route is what gets approved; ordering stops being convention. |
| **4 — divergence enforcement + conformance suite** | Runner logs the walked tile path (Q13.2); compare against plan; fail on divergence **onto a trigger tile**, not on any divergence. Frame-rule enforcement (Q7) lands here. | Q7's conformance check, sharing slice 1's graph as its oracle. |

**Critical path:** slice 1 → slice 2 → {trainer / item-ball / staircase templates, `blocked:` derivation,
slice 3} → slice 4.

**Parallelizable from day one, no graph dependency:** the `blocked:`/`unreachable` vocabulary and
assertability field (schema only); the frame rule; and the **PC, mart and Pokémon Center templates** —
talk-to-a-thing archetypes that barely touch routing. The trainer, item-ball and staircase templates *do*
want slices 1–2, since decoded approach paths are their entire point.

**Status note, 2026-08-30 — all four slices are built.** Slice 4 landed alongside slice 3: the runner
records the walked tile path per beat (`Emulator._record_walk_tile`, appended from `_walk_greedy`'s own
position read); `playtest/divergence.py` compares it against the approved plan; a divergence onto a
trigger tile fails the beat (`runner.DivergenceError`), and every other divergence is recorded in
`playtest/contradictions.py`, Q8's ledger, which also absorbed `_plan_route`'s graph-vs-live-collision
finding — previously a `logger.warning` that reached no artifact. Q7's frame rule is enforced by
`playtest/frame_rule.py` at the point a beat fails, and Q7's conformance number is read out of that same
ledger (`python -m rpg2gba.playtest conformance`) rather than from a second expectation table. The run
artifact `observed_beats/<chapter>.json` is schema **2**.

**What slice 4 is not yet validated by.** Like slice 3, its enforcing half is forward-only: with no
route plan committed for any gated chapter (`PROJECT_TODO.md` #67), `compare_walk` reports
`compared: false` everywhere today and no divergence can fail anything until CH05's plan is approved and
committed. The non-enforcing halves — the walked path, the ledger, the frame rule, the conformance
report — are live from the next run of any chapter.

#### Validation — CH05 is not sufficient evidence

CH05 is a thin surface for this much machinery: 2 maps, 3 trainers, 4 staircases, 4 item balls, no mart,
no Pokémon Center, likely no blocked rows.

- **Slice 1 is validated hard by CH05.** Map 37's four staircases cannot be routed at all by the current
  4-neighbour planner, so a wrong slice 1 fails immediately and visibly.
- **Slice 2 is barely exercised by CH05.** Its real test is **retroactive re-derivation of already-gated
  chapters, where the right answers are known**: CH04's 24 geography rows must come back as
  `blocked:rock_smash`, and CH02's 10 rock-gated deferrals must come back as `blocked:rock_smash` too.
- **The mart / Pokémon Center / PC templates are not exercised by CH05 at all** and must be validated
  against their CH01–CH03 instances (Map067 ev1/ev3, Map073 ev3, Map068 ev1, Map050 ev26, Map068 ev7).

**Standing rule from this: a green CH05 gate is NOT evidence that slice 2, the capability model, or the
mart/Center/PC templates are correct.** The retroactive re-derivation check is part of the build, not a
follow-up — otherwise a wrong slice surfaces at CH06, where §1.3(O)'s stranded Route 1 backlog makes it
expensive.

#### Q13.3 — cheap interim before the graph exists? *(decided 2026-08-28)*

Two changes kill most of the class without the offline graph: add sight cones and event-touch tiles to
the avoid set in **both** `_plan_route` and `_walk_greedy`; and a backtracking lint flagging any beat
whose target sits far back toward the entry from the previous beat's target. Grill whether to take these
now or go straight to the full build — the risk of the interim is that it makes the runtime planner
smarter in a way the offline graph then has to replicate exactly.

---

#### Grill findings 2026-08-28 — the hazard is a silent degrade, not the greedy walker

**`_walk_greedy` is not a fallback; it is the executor for every leg.** The hazard is one level up.
`Emulator._route_waypoints` (`emulator.py:1716`) calls `_plan_route`, and when planning returns `None`
it logs a `warning` and **returns the bare target** — handing the leg to a greedy walk with none of the
planner's avoid-set. Its docstring justifies this: *"an ordinary planner blind spot costs a slower
failure rather than a wrong answer."*

**B3 refutes that rationale directly** — the same shape as Q6, where CH04's stated reason for a local
helper turned out to be false. The greedy walk crossed Timothy's event-touch tile, the wrong trainer was
fought, and both guards passed. It was a wrong answer, not a slow failure. It is also a **silent
fallback**, which CLAUDE.md §4.5 and §11 forbid outright.

**And it survives slice 1.** Slice 1 makes the planner consume the offline graph, but the graph will
still fail to plan sometimes — occlusion, an unmodelled behaviour, a stale grid — and this degrade path
walks unprotected no matter where walkability came from. So fixing it is not interim code.

#### DECIDED 2026-08-28 — no planner-smartening; the silent degrade becomes fail-loud

**Adjudicated with the operator. BUILT 2026-08-29** (`f705b642`): `_route_waypoints` fails loud instead of degrading silently to an unprotected greedy walk on the bare target.

1. **The avoid-set changes are not taken.** Adding sight cones and event-touch tiles to `_plan_route`
   and `_walk_greedy` teaches the runtime planner walkability that slice 1 then deletes — the doc's own
   stated replication risk — and the operator intends slices 1-2 before CH05, so the interim's window is
   days.
2. **`_route_waypoints`' degrade is made fail-loud instead:** a planning failure raises with its own
   diagnosis rather than warning and continuing on the bare target. This is B3's actual mechanism, it is
   a standing §4.5 violation, and it is permanent — slice 1 does not touch this lane.
3. **The backtracking lint is not taken either**; slice 3's route solver subsumes it, and ordering stops
   being convention there rather than here.

---

## Part 3 — Things I would not spend grill time on

- The manifest/disposition two-file split, content hashing, and stale-disposition invalidation. Proven.
- `NOT_RUN`, the generated tally, and the hang budget. Proven.
- `rules.py` version tracking for assertion classes. Proven for what it covers; Q4 covers what it doesn't.
- Predecessor chaining and full-replay-at-gate. It caught two silent CH02 NPCs this round.
- Approve-before-build ordering.
- Seed-resume after failure (v1 Q10's optional stronger form). Correctly left unbuilt; no evidence it is needed.

---

## Part 4 — Corpus trainer-archetype census (2026-08-27)

Run to settle Q0's weaker counter-argument by measurement. Method reused `_script_head` / `RUBY_KEYWORDS`
/ `COND_TYPE_SCRIPT` from `chapter_atlas/census.py` verbatim (including the assignment-LHS fix) and the
355/655 script-block splitting from `chapter_manifest/generator.py::_extract_scripts`, so the numbers
match how the existing pipeline sees these events.

### 4.1 Scale

**299 trainer events** (pages containing `pbTrainerBattle` or `pbDoubleTrainerBattle`) across **68 of 199
maps**, in **67 distinct signatures**, where a signature is the ordered list of (page index, trigger,
sorted script heads). Page counts: 1 page ×6, 2 pages ×216 (72%), 3 pages ×70 (23%), 4 pages ×5, 5 pages ×2.

### 4.2 Regularity — read the axes, not the signature count

Taken literally, only 162/299 (54%) match map 35's PLAIN or PHONE byte-for-byte. **That framing
overstates the irregularity**, because the signature key treats parameterizable axes as distinct shapes:
page-0 trigger (`action` / `player_touch` instead of `event_touch`), an empty p1 instead of a
`pbCallBub` re-talk, and a trailing extra re-talk page. Collapsing those:

| Bucket | Count | Cumulative |
|---|---|---|
| PLAIN (signature rank 1) | 149 | 50% |
| PLAIN + extra re-talk page (rank 2) | 38 | 63% |
| PHONE (rank 3) | 13 | 67% |
| Same shapes, `action`/`player_touch` trigger or empty p1 (ranks 4–10, 16) | ~41 | **~81%** |
| + item-grant / self-switch rider folded into the battle page | 33 (overlapping) | ~90% |

Genuinely bespoke tail: **43 events with unique one-off signatures (14%)**. Conclusion: **one template
with roughly four parameters — trigger, re-talk page count, phone-rematch, item/flag rider — covers about
four-fifths of the corpus.**

### 4.3 The decision at hand is unambiguous

**All 16 trainer events in the CH04/CH05 neighbourhood match PLAIN or PHONE exactly.**

| Map | Chapter | Trainer events | Shapes |
|---|---|---|---|
| 031 Kevlar | CH03 | 0 | — |
| 032 Moki | CH01 | 0 | — |
| 033 Route 1 | CH02 | 9 | 7 PLAIN + 2 PHONE |
| 035 Route 2 | CH04 | 4 | 2 PLAIN + 2 PHONE |
| **036 Passage Cave** | **CH05** | **2** | **both PLAIN** |
| **037 Passage Cave** | **CH05** | **1** | **PLAIN** |

CH05's 3 trainers match the atlas's stated count. The template also covers Route 1's 5 stranded
rock-gated trainer beats when CH06 unblocks them (§1.3(O)), and CH07's Route 2 revisit — Brent (PHONE)
and Chuck (PLAIN), both currently `unreachable:north_of_rockslide_gate`.

### 4.4 Three findings independent of the archetype question

1. **A documented invariant is false corpus-wide.** `census.py` records that every trainer battle is
   wrapped in one code-111 script-typed conditional. It holds on map 35. **11 events reach
   `pbTrainerBattle` through a plain 355 block with no 111 wrapper** (Map040/event20, Map214/event6,
   Map075/event26, …). Any code using that invariant to *find* trainer battles silently misses them —
   a fail-loud (§4.5) violation in existing code. Distribution of type-12 conditionals on the battle
   page: `{0:11, 1:250, 2:19, 3:12, 4:6, 6:1}`; the 38 events with ≥2 carry genuine extra pre-battle
   branching.
2. **Double battles exist and are detectable now: 5 events**, all via a `pbDoubleTrainerBattle` head —
   Map099/event3, event4, event17; Map203/event5, event6. Two also carry `pbSetSelfSwitch`;
   Map203/event5 also carries `pbReceiveItem`. The second opponent id lives in the call arguments, not
   as a separate head. The harness has no double-battle support (v1 blind spot G) — but these are now
   enumerable in advance rather than discovered mid-chapter.
3. **24% of trainer events (72) do not use `event_touch` on page 0** — 61 `action`, 8 `player_touch`,
   3 `autorun` (Map105/event1, Map195/event46, Map216/event13). Approach-and-trigger logic built only
   against the touch pattern is wrong for a quarter of the corpus.

**Genuinely special, hand-write these:** Map141/event25 (12 heads on one `player_touch` page — a gym-7
handler with partner register/deregister and mega selection; the most complex trainer page in the
corpus) and Map131/event3 (a single-page ceremony with `setupWaitingRoom` / `preRoundDialogues` /
`postRoundDialogues` / `upNextDialogue` and no follow-up page). Partner register/deregister battles
(Map187/event42, event59; Map202/event9; Map075/event25) are a small recurring non-generic family.

---

## Part 4b — Non-trainer archetype census (2026-08-27)

Scope: the 18 maps bound to CH01–CH05 in `reference/chapters.json` (32, 48, 49, 50, 64, 65, 89, 172,
33, 81, 31, 67, 68, 73, 19, 35, 36, 37) — 488 event pages in 93 distinct (trigger, heads, effects)
signatures — with corpus-wide counts for generalization. Same reused parsing as §4.

### 4b.1 Archetypes ranked, with build tier

Operator constraint: build only what we have already seen or are about to see in CH05.

| Archetype | In-scope | Corpus | Regularity | Tier |
|---|---|---|---|---|
| Door/warp event | 51 | 996 | 92% / 87% `player_touch` | **1 — CH05 needs it** |
| Item ball (2-page spent pattern) | 15 | 243 | ~99% one shape | **1 — CH05 needs it** |
| **Staircase forced-move** | 13 | **222** | high, one shape | **1 — CH05 needs it** |
| Trainer battle (§4) | 16 | 299 | ~81% with 4 params | **1 — CH05 needs it** |
| Cave entrance/exit | 13 | 102 | high | 1 — CH05 needs it |
| PC access | 2 | 21 | **21/21 identical** | 2 — trivial, closes a gap |
| Mart / shop | 3 | 46 | 95% single-page one-item-list | 2 |
| Pokémon Center heal | 1 | 64 | ~23% dominant shape | 2 — build against the one instance, expect to extend |
| Plain dialogue NPC | 59 | — | loose by nature | 3 |
| Gift / receive item | 15 | 137 | **30%** — a family, not a shape | 3 — defer |
| Sign / signpost | — | — | not mechanically separable | **do not build** |
| Berry plant | 13 | 96 | two-state, item-ball-shaped | 3 |
| Rock Smash obstacle | 14 | 94 | high, 3–4 head core | 3 |

### 4b.2 The staircase forced-move is the significant find

`player_touch`, **no script heads**, effects = `{move_route}` only, gated on a code-111 **direction**
branch (not a switch), no character graphic — a fake staircase that nudges the player one tile
diagonally. **222 corpus-wide**, 13 in scope, **4 of them on CH05's map 37** (events 3, 6, 7, 8, all
identical). Top corpus maps: 22 (×25), 71 and 74 (×16 each). It is templated nowhere and appears in no
prior planning document.

It also connects to a v1 blind spot: finding G recorded that "the route planner is 4-neighbour, so
sideways-staircase tiles must be stepped by hand." That hand-stepping is being done, one beat at a time,
against 222 instances of a single regular shape.

### 4b.3 Findings on the operator's named three

- **PC access — 21/21 identical corpus-wide** (`action`, heads=(`pbPokeCenterPC`,), no effects). A
  one-line template, and it closes a standing gap: `pokecenter.use_pc` currently exercises only the
  cancel arm. `pbTrainerPC` occurs exactly once (Map048/ev4) and is a separate one-off.
- **Mart — 46 corpus-wide, 95% single-page with one item list**, and the item list is literally the
  `pbPokemonMart([...])` call-argument array, so it pipes in directly. One real variant: Map073/ev3 has
  switch-gated stock (a second page stocking a different list after switch 81). **RGSS's native Shop
  Processing command (code 302) is used nowhere in the corpus** — everything routes through
  `pbPokemonMart` / `pbPokemonBerryMart` (the latter only on map 171), so there is one code path.
- **Pokémon Center heal — 64 corpus-wide but only ~23% share a dominant shape.** Trigger varies
  (`action` nurse dialogue / `player_touch` auto-heal / `parallel` / `autorun`); some bundle a trainer
  battle or an item grant. Core is `pbSetPokemonCenter` + `pbCallBub` + a yes/no choice + code-314 heal
  + a counter move-route + an optional PokeRus branch. Build against the single in-scope instance
  (Map068/ev1) and expect extension.

### 4b.4 Two corrections to our assumptions

1. **"Sign" is not a real archetype.** The obvious filter (action trigger, no heads, text only, no
   graphic) matches 107 in-scope pages, but most are **the blank spent second page of an item ball** —
   no graphic and no commands at all. True signs are not mechanically separable from one-off text
   triggers without reading dialogue content. Fold into plain-dialogue-NPC distinguished by
   `char_name == ''`; do not build a separate template. *(Note this is the same confusion `0983e163`
   had to untangle by hand: map 35's event named "Sign" is an empty page, and the actual sign by the
   cave entrance is ev002.)*
2. **The census classified trainers' post-battle re-talk pages as "plain dialogue NPC."** That is the
   B14 misclassification reproduced mechanically: an archetype-blind classifier sees a trainer's page 1
   as a generic talking NPC. Under archetype-aware classification it is not a dialogue NPC at all — it
   is page 1 of a trainer, and is never classified independently. Direct evidence for Q0's
   "ask the question at the event level, not the page level."

### 4b.5 CH05 exhaustive worklist (maps 36, 37)

**Map036** — 8 events / 14 pages: 4 item balls (ev3, ev5, ev8, ev9; each the clean 2-page spent pair,
`PU-POKEBALL` graphic), 2 trainer battles (ev4, ev6; each with a page-1 re-talk), 1 door/warp (ev2),
1 cave exit (ev1), 1 autorun system-plumbing page (ev2/p1, `get_character` + `setTempSwitchOn`).
No signs, gifts, marts, PC, heal, or staircases.

**Map037** — 8 events / 9 pages: **4 staircase forced-moves** (ev3, ev6, ev7, ev8; all identical),
1 door/warp (ev1), 1 cave exit (ev2), 1 trainer battle (ev4, with page-1 re-talk), 1 **bespoke** gift
(ev5 — `pbCallBub` + `pbReceiveItem` writing both a self-switch *and* a global switch, with a page-1
follow-up that also writes state, so it is not a clean gift and not a plain dialogue NPC).

**Net:** four templates — trainer, item ball, staircase, door/warp — plus cave-exit and one hand-written
gift cover every event in CH05.

---

## Part 4c — Real gating-vocabulary census (2026-08-27)

Commissioned after `_HEAD_REQUIRES` was found two-thirds fictional (Q3). Sources: all 199
`Map###.json`; `reference/uranium_switches.json` / `uranium_variables.json`;
`reference/terrain_tag_map.json`; the Uranium script dump under `reference/scripts_dump/`.

### 4c.1 Capabilities arrive by four different surfaces, not one

| Surface | Example | Head-table can see it? |
|---|---|---|
| Event script head | `pbRockSmash`, `pbPushThisBoulder` | yes |
| **Terrain tag** | Surf / Waterfall / Dive | **no — structurally** |
| **Page condition on a switch/var** | switch 86 "Has Strength", switch 55 "Gym 1 defeated" | no |
| **Item-possession check** | `$PokemonBag.pbQuantity(PBItems::BIKEWHEEL) > 0` (45 uses) | no |

Surf/Waterfall/Dive fire from `Events.onAction` reading `pbFacingTerrainTag`
(`reference/scripts_dump/103__PField_HiddenMoves.rb:648-654, 793-802, 940-961`) — **zero** script-head
surface, confirmed not inferred. Relevant terrain tags: 5 DeepWater (dive), 7 Water, 8 Waterfall,
9 WaterfallCrest, 17 StillWater; `isSurfable?` = {5,7,8,9,17}, `isWaterfall?` = {8,9}. Dive additionally
needs the per-map metadata key `MetadataDiveMap` — a map property, not a switch.

### 4c.2 Verified head counts (all 199 maps)

| Head | Occurrences | Maps |
|---|---|---|
| `pbPushThisBoulder` | 84 | 15 |
| `pbRockSmashRandomEncounter` | 68 | 6 |
| `pbRockSmash` | 29 | 4 |
| `pbStrength`, `pbCutTree`, `pbSurf`, `pbWaterfall`, `pbDive`, `pbFishing` | **0** | **0** |

The table conflated *engine hook names* with *map-script call names*. `pbPushThisBoulder`'s only guard is
the derived engine flag `$PokemonMap.strengthUsed`, set by `Kernel.pbStrength` when facing an event named
`"Boulder"` — so its requirement is *transitively* strength, and the map-script surface never names it.

### 4c.3 Grant sites and their gates

| Capability | Grant site | Gate on that page |
|---|---|---|
| `rock_smash` (HM06) | Map040/ev20/p2 | switch **55 "Gym 1 defeated"** + a nested trainer-battle win |
| `strength` (HM04) | Map140/ev16/p1 | var 119 == 6; same event writes switch 86 "Has Strength" |
| `surf` (HM03) | Map143/ev22,24/p2 | self-switch A; same event writes switch 97 "Theo SURF" |
| `fly` (HM02) | Map112/ev23/p1 | var 123 ≥ 9 **and** an inline `$game_player.x == 38` positional check |
| `dive` (HM08) | Map135/ev37/p1 | switch 113 + switch 61 + switch 60 + var 117 ≥ 5 — **four stacked gates** |
| `waterfall` (HM07) | Map172/ev4/p3 | switch 125 "FINAL EVENT" |
| `old_rod` | Map081/ev1/p1 | **`var[103] "Battle Var01" >= 5`** — anonymous scratch variable |
| `bicycle` | Map073/ev1/p1 | `pbQuantity(BIKEWHEEL) > 0`; `BIKEWHEEL` is an unconditioned pickup at Map076/ev84 |
| gadget items | Map167/ev28, pages 1–5 | `numbadges >= BADGEFOR<X> + 1` per page |
| `cut` (HM01), `flash` (HM05) | **none in corpus** | — |

Eight badge writes exist, one per map (`$Trainer.badges[0..7] = true` on maps 42, 66, 102, 148, 69, 147,
141, 175), so badge count is mechanically derivable independent of switch names.

**The dependency structure is a graph, not a chain.** Rock Smash / Strength / Surf are clean
single-prerequisite chains. Dive has four independent predecessors. Fly folds in a raw coordinate check —
a gate *shape* outside the switch/item/terrain vocabulary entirely.

### 4c.4 Page-condition switch census

1,832 switch reads across page conditions, 92 distinct switches. Most frequent: 125 "FINAL EVENT" (180),
139 "KoD - Complete" (153), 79/80 "Gym 4 puzzle" (100/64), **86 "Has Strength" (58)**, 94 "Gym 5 End"
(46), 113 "Gym 7 end" (32), **55 "Gym 1 defeated" (13)**. **Most of the 92 are plot-state flags, not
capabilities** — the vocabulary must not swallow them wholesale, or `blocked:` becomes a synonym for
"gated on any switch."

### 4c.5 Structural finding — stacked gates are not derivable from the row's condition

`_build_condition` (`generator.py:186`) reads only the RGSS page `condition` struct — switch1, switch2,
variable. It never walks nested code-111 branches in the command list. RGSS page conditions hold at most
two switches plus one variable, so **anything beyond that is expressed as nested in-body conditionals and
is invisible to the row's condition field** — Map135/ev37's four stacked gates present to the manifest
as one.

**This is a prompted hole, not a silent one.** The row still records `script_typed_conditions`, and
`needs_citation` fires when that count is `> 0`, so the author is required to cite a source. The
compensating control works as designed; what it cannot do is *derive* the gate. Any automatic `blocked:`
derivation must therefore treat a row with `script_typed_conditions > 0` as under-determined and defer to
annotation rather than emitting a confident single capability.

---

## Part 5 — CH05 dry-run (Passage Cave, maps 36 + 37), 2026-08-28

**Status note, 2026-08-29.** This part is a dated finding — a snapshot of what was true on
2026-08-28 — and several of its specifics are superseded below. Code 408 is fixed: added to
`_CODE_IGNORED` the same day, in `511ef4af` (§5.10, §5.12). §5.9's build-ordering constraint is
satisfied: slice 1 landed first (`f780a972`, `364732ac`, `46bd2efe`), the `_route_waypoints`
fail-loud landed after it (`f705b642`), and Q13 slice 1 as a whole is now complete and closed
(`c9f73178`, `31ddb7c5`, 2026-08-29). CH05's remaining decisions — the cave-darkness/Flash
content-fidelity call and the maps 36/37 naming collision — are deferred by operator instruction
(2026-08-29) until the CH05 branch is cut; their live home is `reference/chapters/05-passage-cave.md`
§7, with a parked worklist section in `PROJECT_TODO.md`. Nothing in Part 5 below should be read as
a live blocker on current work.

Run before any Q13 slice is built, as Part 5 prescribes. Third calibration case after map 32
(v1 §6) and map 35 (v1 §7), and the **first one run against the real generator** rather than a
hand-script: `python -m rpg2gba.chapter_manifest generate --chapter CH05` now works unmodified.
Output was written to a scratchpad path, not to `reference/manifests/` — nothing in this section
is committed state.

> `wrote CH05.manifest.json: 25 rows, 1 undispositionable, 9 need citation`

Sources joined, as v1 §6.5 requires: `maps/Map0{36,37}.json`, `connections.json`,
`transpile_unhandled.jsonl`.

### 5.1 Scale, and a corrected census

| | Map036 | Map037 | CH05 |
|---|---|---|---|
| size / tileset | 42x42 / ts32 "PU Caves" | 34x30 / ts32 | — |
| events | 8 (ids 1-6, 8, 9 — **id 7 does not exist**) | 8 (ids 1-8) | 16 |
| **pages / manifest rows** | **15** | **10** | **25** |
| seam rows | 0 | 0 | **0** |
| triggers | — | — | action 13, player_touch 8, event_touch 3, autorun 1 |

**§4b.5's page counts are both wrong by one** — it says 14 and 9, i.e. 23 pages; the generator
emits 15 and 10, and `chapter_atlas census --chapter CH05` independently reports
`events=16 pages=25`. §4b.5 also attributes Map036's autorun system page to
`ev2/p1`; it is **`ev2/p2`** (1-based) = `map036/ev002/p1` (0-based row id). Its classification
of *which* events are what is otherwise exactly right, verified command-by-command.

Everything else in §4b.5 holds: 4 item balls (Map036 ev3/5/8/9 — Escape Rope, Great Ball, TM76,
Sableyeite), 3 trainers (Map036 ev4 HIKER "Manny", ev6 BLACKBELT "Keichi"; Map037 ev4 HIKER
"Nuñes"), 4 staircases (Map037 ev3/6/7/8), 2 door/warps, 2 cave exits, 1 bespoke gift
(Map037 ev5, Revive).

### 5.2 CRITICAL — the four staircases disposition as `cosmetic`, and every check agrees

This is the CH05 equivalent of v1 §6.2, and it is worse, because nothing fails.

The four Map037 "Stairs" events are the diagonal-staircase idiom already met on Map033
(CH02): `trigger=1` player-touch, `through=false`, a code-111 **character-direction** branch on
the player's facing, and a forced diagonal move route in each arm. Verified from the data:

| event | cell | branch | arms | axis | derived side |
|---|---|---|---|---|---|
| ev3 | (20,10) | `111 [6,-1,6]` — player faces RIGHT | move 6 / move 7 | NW/SE | `RIGHT_SIDE` |
| ev6 | (20,9) | `111 [6,-1,6]` | move 6 / move 7 | NW/SE | `RIGHT_SIDE` |
| ev7 | (11,10) | `111 [6,-1,4]` — player faces LEFT | move 5 / move 8 | NE/SW | `LEFT_SIDE` |
| ev8 | (11,9) | `111 [6,-1,4]` | move 5 / move 8 | NE/SW | `LEFT_SIDE` |

`tileset_converter/stairs.py` already handles all four, both axes, no fail-loud
(`detect_stair_cells` returns the four cells classified LEFT/LEFT/RIGHT/RIGHT). They convert to
native `MB_SIDEWAYS_STAIRS_{LEFT,RIGHT}_SIDE` metatile behaviours. **No object event and no
script reach the ROM.**

Now look at what the manifest says about those same four rows:

```
map037/ev003/p0   heads=[]   effects=[move_route]   stc=0   unhandled=0   other_codes=[]
                  -> needs_citation=False   is_dispositionable=True   may_be_cosmetic=True
```

Identical for ev006, ev007, ev008. So:

- `may_be_cosmetic` is True, because it is computed as "writes no state" and a staircase writes
  no switch, variable, self-switch or item;
- `needs_citation` is False, because `unrecognized_heads` is empty (there are no script heads at
  all) and `script_typed_conditions` is 0 (the branch is character-direction, `params[0]==6`, not
  script-typed `params[0]==12`);
- `is_dispositionable` is True.

**A single author keystroke — `"cosmetic"` — disposes of the map's principal traversal mechanic,
and `check` exits 0.** This is exactly the B14 shape that `0983e163` diagnosed ("cosmetic was
being decided on whether a page writes state"), reproduced mechanically, on the mechanic §4b.2
calls "the significant find" with **222 corpus instances**.

**The vocabulary has no correct verdict for these rows.** They are not `beat:` — there is no
event in the output to interact with, and no state to assert. They are not `blocked:` or
`unreachable`. They are emphatically not `cosmetic`. Q5's decided `terrain` row kind (by
behaviour class) is the right home, but Q5 framed it as *adding* rows the event scan cannot see;
here the requirement is the mirror image: **a page row whose only realization is a metatile
behaviour must be *absorbed* by its terrain row, not double-counted beside it.** That absorption
is not in any decision yet, and if both mechanisms fire naively CH05 gets 4 page rows and 4
terrain rows for 4 staircases.

**Recommendation:** the generator learns the stair fingerprint directly — it is a pure structural
match on `trigger=player_touch` + character-direction branch + diagonal move arms, the same test
`stairs.py:_page_qualifies` already implements — and emits those rows as `kind="terrain"`,
`behaviour=MB_SIDEWAYS_STAIRS_*`, with no page row. Reuse `stairs.py`; do not write a second
detector.

One correction to §4b.2 while we are here: "It is templated nowhere and appears in no prior
planning document" is true of the **playtest/manifest layer only**. The *converter* solved this
mechanic during CH02 (Map033), and `stairs.py` plus the `behavior_overrides` overlay is that
solution. The gap is not that the engine cannot do sideways stairs; it is that two layers of the
pipeline already know about them and the beat layer is not one of them.

### 5.3 CRITICAL — both maps are dark, and nothing in the pipeline can see it

`intermediate/metadata_raw.json` (`MetadataDarkMap` = field 9):

- **map 36: `DarkMap: true`. map 37: `DarkMap: true`.** 26 maps in the corpus carry it.
- `pbs_converter/metadata.py:114` parses it into `dark_map: True` and nothing downstream reads it.
- `tileset_converter/metadata_wiring.py:602` emits **`"requires_flash": False` as a hardcoded
  literal** into every map header.

So CH05 — the chapter `chapters.json` tier-promotes to medium *specifically* for "first candidate
for cave/Flash handling" — will convert as a fully lit cave, and the manifest is structurally
blind to it: `DarkMap` is a **map property**, not an event page, not a connection, not a terrain
tag. It is a fifth capability surface on top of Part 4c's four, and the same argument applies —
the head table cannot see it.

Two things make this sharper than a missing feature:

1. **It already shipped.** Map 19 (Grott-Hole) is `DarkMap: true` and went through **CH03's §9
   boot-walk gate as a lit room**, unremarked. That is a live class-P instance in a gated chapter,
   found by enumeration, not by walking.
2. **Vanilla's Flash path cannot be the answer.** Part 4c established that HM05 has **no grant
   site in the 199-map corpus**, and Uranium's own `CanUseMove(:FLASH)` handler additionally
   requires `BADGEFORFLASH`
   (`reference/scripts_dump/103__PField_HiddenMoves.rb:1161-1176`). A `requires_flash: true`
   header would produce a cave the player can never light. So "wire `dark_map` to
   `requires_flash`" is *not* the fix; this is a content-fidelity decision (CLAUDE.md §10) with
   at least three options — render the darkness and grant Flash from somewhere, render it and
   accept an unlightable cave, or strip darkness corpus-wide and record it — and it is the
   operator's call, not the build agent's.

The hardcoded `False` is a §4.5 silent default regardless of which way that call goes: it should
read the parsed metadata and fail loud on a dark map until a decision is recorded.

### 5.4 The cosmetic veto is vacuous on an unstaged map

`transpile_unhandled.jsonl` has 332 rows; 244 carry a `map_id` and **those 244 fall on exactly 16
map ids, every one of them a `SLICE_MAP_IDS` map** (the other 88 carry no map id at all). Maps 36 and 37 have never been staged, so they contribute zero rows, so
every CH05 row gets `unhandled: 0`, so `may_be_cosmetic`'s unhandled-queue veto passes vacuously
for the entire chapter.

`05-passage-cave.md` §6 already warned that "zero entries means 'never staged', not 'clean'". The
finding here is that **the generator does not encode that distinction and the checker cannot**:
`unhandled == 0` is indistinguishable from `map never transpiled`, and it silently strengthens a
verdict. Straightforward fix, and it is a prerequisite for trusting any pre-build manifest:
record the set of map ids the queue actually covers, and have the generator mark rows for maps
outside it — `unhandled: null` rather than `0`, with `may_be_cosmetic` False until the chapter is
staged and the manifest regenerated. That also makes the generate-before-staging ordering
explicit instead of conventional. (CH04 did not expose this: map 35 was staged before its
manifest was generated, so its 6 queue rows were real.)

### 5.5 CH05 cannot mint: two maps, one name

`map_infos.json` names **both** map 36 and map 37 "Passage Cave", and `map_name_overrides.json`
records both as `"CORRECT — no override"`. `map_constants.MapConstantRegistry.mint` is strict
outside the Map Walker and raises:

> `map 37 ('Passage Cave') -> MAP_PASSAGE_CAVE collides with already-minted map 36; add a
> map_name_overrides.json entry`

This is the fail-loud working exactly as designed, and it is CH05's **first** blocker — it fires
before any of the interesting work. `05-passage-cave.md` §2/§7 proposes `PassageCave` /
`PassageCave2` and flags the names as unconfirmed; the fix is two `overrides` entries with
evidence. Map 19 was already disambiguated to "Passage Cave Grott-Hole" on the same grounds
(CH03 scope pass), so the precedent and the house style both exist.

### 5.6 The archetype build set is missing its largest member

Q0's Tier-1 build set is trainer / item ball / staircase / door-warp / cave exit. Applied to
CH05's 25 rows, that covers 22 (88%). The residual three are Map037 ev5's two bespoke-gift pages
— and **`map036/ev002/p1`**, whose fingerprint is:

```
trigger=autorun  switch1=22 's:tsOff?("A")'  heads=[get_character, setTempSwitchOn]
effects=[graphic, move_route, temp_switch_write]  script_typed_conditions=1
```

That is **byte-identical, field for field, to `map035/ev001/p1`** — a CH04 row, dispositioned
`beat:B8`. Two instances in two consecutive chapters is already Q6's promote-on-second-use
trigger. A corpus census settles the size: the idiom (autorun page, `get_character(0).onEvent?`
branch, `setTempSwitchOn` tail, player nudged one tile off the arrival cell) occurs
**324 times across 73 maps** — larger than the item ball (243), the staircase (222), the cave
entrance/exit (102) and every Tier-2 archetype. Only the door/warp event (996) is bigger, and this
idiom is the *other page* of many of those same events.

**It is the arrival-nudge archetype, and neither §4b.1's ranking nor Q0's build set contains it.**
The likely reason is instructive: §4b's census classified by *event role* (item ball, trainer,
sign), and this idiom is a *page* of an event whose other page is a warp — the same event-level
vs page-level axis error Q0 identified for trainer re-talk pages, biting in the other direction.
It belongs in Tier 1, and CH05 needs it.

### 5.7 CH05 *does* have blocked rows, and they are terrain-derived

`05-passage-cave.md` §7 left open whether TM76 (31,15) and Sableyeite (34,12) on Map036 need Surf
— "path connectivity from the entrance was not traced". Traced now, same method as §5.9:

- Map036 has **513 walkable tiles in 7 connected components**; **450** are reachable on foot from
  the entrance (17,39).
- Escape Rope (10,35) d=11, Manny (18,29) d=15, Keichi (6,13) d=49, Great Ball (22,7) d=65, the
  Map037 warp (17,4) d=63, the Route 2 exit (17,40) d=1 — all reachable.
- **TM76 and Sableyeite are both inside a sealed 30-tile room** (bbox x 31-36, y 11-16). Ordinary
  wall (terrain tag 0) on north, east and west; its only opening is south, into a **water pocket
  (terrain tag 7, in `isSurfable?`)** that is itself disconnected from the walkable region.

So the wiki was right and the two Mega-Stone-tier pickups are **`blocked:surf`** — and Surf is
granted at Map143 (Part 4c), deep in Act 5. This is CH05's first genuine deferral, and it lands
on the longest capability deferral in the corpus so far.

**It also gives slice 2 a real test after all, on the surface Part 4c flagged as structurally
invisible.** `blocked:surf` here is not derivable from a script head (there is none), not from a
page condition (there is none), and not from `_HEAD_REQUIRES`. It is derivable only from
reachability over **terrain tags** — precisely Q3 decision 4's "the graph derives the minimal set
of capability-tagged obstacles". CH05 is thin for slice 2 (§5.8) but it is not empty, and the one
case it does provide is the *hardest* of the four surfaces rather than the easiest.

Corollary for the beat list: `05-passage-cave.md` B6 and B7 cannot be walked in CH05 and must be
authored as deferred beats in the CH02/CH04 `DEFERRED_BEATS` idiom, not as live beats. They come
back on the Surf revisit, not at CH07 with the rock-gated backlog — a **second, later** revisit
debt on a chapter that was expected to generate none.

### 5.7b Projected disposition, and the shape it makes

| verdict | rows | which |
|---|---|---|
| `beat:` | 15 | 2 cave exits, 2 door-warps, 1 arrival-nudge, 2 item-ball p0, 3 trainer p0 + 3 trainer re-talk p1, 2 gift pages |
| `blocked:surf` | 4 | `map036/ev008` and `ev009`, both pages each (§5.7) |
| `cosmetic` | 2 | the two reachable spent item-ball p1 pages |
| **no correct verdict** | **4** | the four staircases (§5.2) |

Compare CH04's committed dispositions: 42 rows = 13 `beat`, 24 `unreachable` (geography),
4 `deferred:rock_smash`, **1 `cosmetic`**. CH05 inverts that distribution: no geography gate
anywhere, so the verdict doing the work is `cosmetic`, which is also the verdict with the weakest
check (`may_be_cosmetic` is a single "writes no state" test). **CH05 is the first chapter where
the weakest check carries the load** — which is why §5.2 matters more here than the raw count of
four rows suggests.

### 5.8 What CH05 does *not* exercise — now measured, not estimated

Q13's "CH05 is not sufficient evidence" clause was written from the map roster, and predicted
"likely no blocked rows". The generated manifest plus the reachability traces put numbers on it —
and correct that one prediction (§5.7):

| mechanism | CH05 exposure |
|---|---|
| seam rows / overland connections | **0** — `connections.json` has no entry touching 36 or 37 |
| `requires[]` populated | **0 of 25 rows** |
| `blocked:` derivation (Q3, slice 2) | **4 rows**, `blocked:surf`, terrain-derived only (§5.7) |
| page conditions on a real global switch or variable | **0** — 8 self-switches and one runtime predicate (`s:tsOff?("A")`), that is all |
| unrecognized script heads (v1 §6.3's rule) | **0** — every head is in `MECHANIC_BY_HEAD` now |
| `unhandled` queue join | **0**, and vacuously so (§5.4) |
| mart / Pokémon Center / PC templates | **0 instances** |

The `blocked:` line is the one place the prediction was too pessimistic, and §5.7 argues it is
worth more than its row count. Everything else holds. So of the two structural holes v1's dry
runs found — invisible overland seams (§6.2) and the
unrecognized-head rule (§6.3) — **CH05 exercises neither.** It is a regression-free surface for
the existing machinery, and that is the risk, not the reassurance: Q13's standing rule ("a green
CH05 gate is NOT evidence that slice 2, the capability model, or the mart/Center/PC templates are
correct") is confirmed with harder numbers than it was written with. The retroactive
re-derivation over CH01-CH04 is the only validation slice 2 gets.

Against that, **slice 1 is exercised hard**, though not in the way Q13 states — see §5.9.

### 5.9 Slice 1's stated CH05 validation is stated wrong (and the real one is sharper)

Q13's slice table says: *"Map 37's four staircases cannot be routed at all by the current
4-neighbour planner, so a wrong slice 1 fails immediately and visibly."* The premise is right
(`_plan_route`'s own docstring, `emulator.py:1632-1639`, says a destination reachable only across
a sideways staircase "is unroutable here"); the conclusion — *fails visibly* — is not.

`_plan_route` returning `None` does not fail. It returns to `_route_waypoints`
(`emulator.py:1716`), which logs a warning and **hands the leg to the greedy walker on the bare
target** — the silent degrade this document's own grill findings identify as B3's mechanism and a
standing §4.5 violation. So today, a stair-crossing leg on Map037 does not fail visibly; it
walks unprotected, and whether it arrives is luck.

Two decided items collide here, and the collision is a **build-ordering constraint that no
decision states**:

- the 2026-08-28 decision makes `_route_waypoints`' degrade **fail loud** ("permanent, not
  interim — slice 1 does not touch this lane"); and
- slice 1's graph is what teaches the planner to cross a staircase.

Land the fail-loud first and **Map037 becomes unwalkable** — every stair-crossing leg raises. So
either slice 1 lands first, or the fail-loud lands with an explicit stair-crossing escape until
it does. Given the CH05 route is the first thing anyone will run after the fail-loud change, this
is worth pinning before the build starts rather than rediscovering at the first red suite.

There is also a modelling correction worth carrying into slice 1: a sideways staircase is not an
impassable tile and not a diagonal *edge*. The cell is passable, the player presses EAST or WEST,
and the **engine** turns that press into a diagonal displacement (`GetSidewaysStairsCollision`,
`GetRightSideStairsDirection`). A graph that models it as an 8-neighbour edge will plan correct
paths and then mispredict the player's position after each step. That mismatch — right path,
wrong resulting cell, no trigger touched — is precisely Q13.1's "non-trigger divergence = the
offline graph is wrong about the engine" class, so **CH05 will produce the first real entries in
Q8's contradiction ledger.** That is the honest statement of what slice 1 gets validated by here,
and it is a better test than "it fails immediately."

**Measured: the staircases are mandatory for finishing the chapter.** A 4-neighbour BFS over
Map037's real walkability — built with the repo's own `layout.column_blocked` against
`tilesets.json["32"]`, run twice with the four stair cells forced walkable and forced blocked —
gives:

| target | stairs walkable | stairs blocked |
|---|---|---|
| cave exit (16,5) -> Nowtoch | reachable, 35 steps | **UNREACHABLE** |
| trainer "Nuñes", adj (23,10) | reachable, 23 steps | reachable, same path |
| gift NPC, adj (9,7) | reachable, 26 steps | reachable, same path |

> **Corrected 2026-08-28 (slice 1).** The cave-exit figure read **34** when this section was
> written; the built graph measures **35**, and the graph is right. Settled by exhaustive search
> rather than argument: **(16,26) is the unique cell on Map037** from which the trainer sits at 23
> steps and the gift NPC at 26, and **no cell anywhere on the map** yields the original 34/23/26
> triple — so the entry point was never in doubt and the exit figure was off by one. The other
> three measurements reproduce exactly. **The structural conclusion is untouched**, and it is the
> load-bearing part: the exit is unreachable without the staircases.
> Regression: `tests/test_traversal_map037_golden.py`.

Walkable/blocked band, x=0..33 (stairs-blocked run; the walkable run differs only at x=11 and
x=20 on rows 9 and 10):

```
y= 8: #######....#........##.....#######
y= 9: #######....#........#......#######
y=10: ######.....#..####..#......#######
y=11: ########...#..#####.#......#######
```

The band is not a full-width wall: a west corridor (x=9-13) and an east zone (x=21-26) both run
past it, which is why the trainer and the gift are collectible without ever touching a staircase.
What the wall at x=11 and x=20 seals is the **centre** strip (x=12-19) — and the exit is at
x=16. The four staircases are the only link from south-centre to north-centre.

So the disposition in §5.2 is not "four cosmetic rows on a nice-to-have": `cosmetic` on those
four rows would wave through **the one mechanic without which CH05 cannot be completed**, and
`check` would exit 0 while doing it. It also means the ordering constraint above is not
hypothetical — with the fail-loud landed and no stair model, the chapter's final leg raises every
run.


### 5.10 Two smaller flags

- **A comment blocks a disposition.** `map037/ev004/p0` (the trainer "Nuñes") is the chapter's
  one `is_dispositionable=False` row, and the sole reason is `other_codes=[408]`. Code 408 is
  *Comment (continuation)*; code 108 (*Comment*) is already in `generator.py:107`'s
  `_CODE_IGNORED` and 408 is not. So a two-line RMXP comment makes an otherwise ordinary trainer
  page require human classification, and — under Q0's coverage checker — splits an archetype
  fingerprint that is otherwise identical to Map036 ev4 and ev6. One-line fix: add 408 to
  `_CODE_IGNORED`. Worth doing before the archetype checker exists, not after.
  **FIXED 2026-08-28 (`511ef4af`).**
- **Fingerprint on the head, not the graphic.** Three of CH05's item balls use
  `character_name = "PU-POKEBALL"`; `map036/ev009` (Sableyeite) uses **`PU-MegaStone`**. Any
  item-ball template keyed on the sprite misses it; keyed on `pbItemBall` it does not.

### 5.11 Corrections owed to committed documents

The dry run contradicts three committed artifacts. All three are cheap to fix and all three are
load-bearing for CH05:

1. **`reference/chapters/05-passage-cave.md` §3 and §7 are wrong about the staircases.** §3 omits
   the four Stairs events on the grounds that "each is a player-touch trigger with only a
   turn-in-place move route ... They gate and observe nothing", and §7 lists them as "inert
   templates ... flag both for an eye-check once art exists". They are not turn-in-place and they
   are not inert: each is a facing-conditional **forced diagonal move**, and they are very
   probably the map's only vertical traversal. This is the approved spec a scenario gets written
   from, so the error would propagate straight into the beat list.
2. **§4b.5's page counts** (14 / 9 → **15 / 10**) and its `ev2/p1` attribution (→ `ev2/p2`).
3. **`05-passage-cave.md` §2** gives Map037 ev1's return warp as `dir=4`; the data is
   `[0, 36, 17, 4, 0, 1]` — direction **0** (retain). Its exit coordinate `(68,43)` is correct
   and should be trusted over any re-read that reports `(43,2)`; the parameter layout is
   `[?, map, x, y, dir, fade]`.

### 5.12 Consequences

- **Two new Tier-1 templates, not one build-set edit:** the arrival-nudge autorun (§5.6, 324
  instances) joins the set; the staircase leaves the *page-row* world entirely and becomes a
  terrain row (§5.2).
- **Three fail-loud repairs are prerequisites, not follow-ups:** the `unhandled: 0`-vs-null
  distinction (§5.4), `requires_flash` reading its parsed metadata (§5.3), and code 408 (§5.10).
  **Status 2026-08-29:** the code 408 repair is done (`511ef4af`); the other two are parked as
  `PROJECT_TODO.md` #54 (`unhandled` null-vs-0) and #56 (`requires_flash`).
- **One operator decision is blocking, and it is a §10 content-fidelity call:** what CH05 does
  about darkness, given HM05 is ungrantable (§5.3). It also retro-applies to map 19 in gated CH03.
  **Status 2026-08-29:** deferred by operator instruction to the opening of the CH05 branch;
  live home is `reference/chapters/05-passage-cave.md` §7.
- **One naming decision is blocking and trivial:** override entries for maps 36 and 37 (§5.5).
  **Status 2026-08-29:** deferred by operator instruction to the opening of the CH05 branch;
  live home is `reference/chapters/05-passage-cave.md` §7.
- **One ordering constraint should be pinned into Q13's slice plan:** slice 1 before the
  `_route_waypoints` fail-loud, or an explicit stair escape between them (§5.9).
  **Status 2026-08-29: satisfied.** Slice 1 landed first (`f780a972`, `364732ac`, `46bd2efe`),
  the fail-loud landed after it (`f705b642`), and Q13 slice 1 is now complete and closed
  (`c9f73178`, `31ddb7c5`).
- **CH05 is confirmed as thin for slice 2 and the capability model** with measured zeros (§5.8) —
  but not empty: the Surf-sealed item room (§5.7) is a terrain-derived `blocked:` case, the
  surface Part 4c called structurally invisible, so slice 2 should be built to satisfy it rather
  than deferring all of its validation to the retroactive CH01-CH04 re-derivation.
- **CH05 acquires a second revisit debt**, on Surf rather than Rock Smash: B6/B7 become deferred
  beats owed to an Act-5 chapter (§5.7). §1.3(O)'s stranded-backlog problem now has a second,
  much longer arm.
