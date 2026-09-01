# CH05 — Decisions Owed Before the Branch Opens

**Written:** 2026-08-31, against `360eaf60` (the build-status audit commit).
**Scope:** everything that must be *decided* before CH05 (Passage Cave, maps 36 + 37) starts.
**Sources:** `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` (Part 2 questions Q0–Q13, Part 5 CH05 dry-run),
`reference/chapters/05-passage-cave.md` §7, `PROJECT_TODO.md` #49/#51/#53/#54/#56/#57/#61/#62/#63/#64/#65/#66/#67.
Every "still absent" claim below was re-verified against the code on 2026-08-31, not read off a status marker.

This document is **options, not a plan**. Nothing here is decided. Where the source documents already
argue for an option, that is marked *(doc leans)* — it is still yours to take or reject.

---

## Build status — audited 2026-09-01

Derived from the code, not from each section's own prose. Recorded here because this repo has
already been burned once by a decision doc whose inline markers said "not yet built" about code
that existed (`360eaf60`). Update this table when an item lands; do not trust the sections below.

| Item | Status | Where |
|---|---|---|
| A1 / C2 — cave darkness → `requires_flash` | **built** 2026-08-31 | `tileset_converter/metadata_wiring.py`; `PROJECT_TODO.md` Done #56 |
| A2 — maps 36/37 names | **built** 2026-08-31 | `reference/map_name_overrides.json`; Done #53 |
| A3 — Sableyeite | answered; no code owed | folds into B2's deferred-beat handling |
| B1 — staircases absorbed into `terrain` rows | **built** 2026-09-01 | `chapter_manifest/{schema,generator}.py`; Done #54 |
| C1 — `unhandled: null` outside the staged set | **built** 2026-09-01 | `chapter_manifest/{schema,generator,checker,render}.py`; Done #54 |
| D1 — coordinate resolvers + literal-ban lint | **built** 2026-09-01 | `playtest/cells.py`, `tests/test_chapter_coordinate_literals.py` |
| D3 — operator read-through as a named gate step | **built** 2026-09-01 | `BUILD_PLAN.md` step 5 READ; `reference/guides/read_through_checklist.md` |
| B2 — `blocked:surf` derived by the route finder | **built** 2026-09-01 | `generator._CHAPTER_MAP_START_CELLS` + `reference/frozen/ch05_surf_expectations.json`; authoring the 4 dispositions belongs to CH05's build |
| D2 — bidirectional `DEFERRED_*` registration rule | **built** 2026-09-01 | `RULE_UNREGISTERED_BEAT` + `BeatModel` in `checker.py`, `chapter_manifest/beat_model.py`, `playtest/chapter.load_chapter_module`; the two directions collapse into one scan — see below |
| D4 — Tier-1 archetype templates | **built** 2026-09-01 | `chapter_manifest/archetypes.py` (classifier) + `playtest/archetypes/` (4 templates) + `RULE_ARCHETYPE_CONFORMANCE`; Tier 1 is **four** members, not six — see below |
| D6 — per-chapter input fingerprint | **not built** | generator hashes pages/connections only |
| E1 — chapter id → playtest module | **built** 2026-09-01 | modules renamed to chapter ids: `chapters/ch0{1,2,3,4}.py`; `PROJECT_TODO.md` Done #66 |
| E2 — CH05 route plan | **not built** | `reference/routes/` does not exist |
| C4 — capability model signature | accepted as-is (option 2) | 28 warnings stand by decision |
| D5, D7 | deferred by decision | — |
| C3 | deferred until after CH05 | — |
| D8 — whole-corpus re-disposition | **deferred** 2026-09-01 (option 3) | stays blocked behind C3; the slip is recorded in D8 below |

**Both questions back to the build agent were answered on 2026-09-01** and are now closed: E1
(modules renamed to chapter ids) and D8 (deferred — the operator was right that the comparison's
whole point was CH01–CH03, which makes the CH04-only option worthless). No open questions remain in
this document.

**One correction to the record:** C4's answer says Old Rod is mis-described as a field move somewhere
in the repo. A search on 2026-09-01 found no such text — `02-route-1.md` and
`PLAYTEST_AUTHORING_IMPROVEMENT.md:892` both describe it as Gym-1-gated, which agrees. Nothing owed.

---

## How to read this

Decisions come in four kinds, and they block differently:

| Kind | Blocks what | Section |
|---|---|---|
| **Content / naming calls** — CLAUDE.md §10, yours alone | The build cannot start | [A](#a--operator-content-and-naming-calls) |
| **Disposition-vocabulary calls** — what verdict CH05's rows get | Manifest authoring | [B](#b--disposition-vocabulary-calls-forced-by-ch05s-data) |
| **Fail-loud repairs** — build now or accept the hole | Trust in the manifest | [C](#c--fail-loud-repairs-and-standing-regressions) |
| **Decided-but-unbuilt** — pay now or eat later | Nothing hard; costs correctness or authoring time | [D](#d--decided-but-unbuilt-build-before-ch05-or-not) |

Plus [E](#e--process-and-scoping) for process items that need a ruling but not code.

A **minimum path** is proposed at the end ([§F](#f--a-proposed-minimum-path)).

---

## A — Operator content and naming calls

These are §10 content-fidelity decisions. No amount of build work resolves them, and CH05 cannot be
authored around them. Both A1 and A2 were deliberately deferred by operator instruction on 2026-08-29
to "the opening of the CH05 branch" — this is that moment.

### A1. Cave darkness, given HM05 is ungrantable — **hard blocker**

**The situation.** Maps 36 and 37 both carry `DarkMap: true` (26 maps corpus-wide do).
`pbs_converter/metadata.py:115` parses it into `dark_map: True`; **nothing in the tree reads it back** —
grep for `dark_map` across `src/rpg2gba/` returns exactly that one write.
`tileset_converter/metadata_wiring.py:602` emits a hardcoded literal `"requires_flash": False` into
every map header. CH05 was tier-promoted in `chapters.json` specifically as the "first candidate for
cave/Flash handling," and as built it converts as a fully lit cave.

**Why the obvious fix isn't one.** HM05 has **no grant site anywhere in the 199-map corpus** (Part 4c),
and Uranium's own handler (`scripts_dump/103__PField_HiddenMoves.rb:1161-1176`) additionally gates
`CanUseMove(:FLASH)` on `BADGEFORFLASH`. Wiring `dark_map → requires_flash` naively produces a cave
the player can never light.

**Options.**

1. **Render darkness and invent a grant.** Place HM05 (or a substitute) somewhere reachable before
   CH05. *Cost:* invents content Uranium does not have; needs a badge-count decision too; ripples into
   every later chapter's capability model.
2. **Render darkness and accept an unlightable cave.** *Cost:* the chapter is dark and stays dark —
   playability call at the §9 gate is yours; CH05's four staircases are the only vertical traversal and
   would be navigated blind.
3. **Strip darkness corpus-wide and record the decision.** All 26 dark maps convert lit. *Cost:* fidelity
   loss, uniform and explicit; *benefit:* one decision closes 26 maps and removes a whole capability
   surface Part 4c flagged as structurally invisible to the manifest.
4. **Strip for now, revisit when a Flash-gated chapter actually needs it.** Same as (3) but recorded as
   a debt rather than a verdict. *Cost:* the debt has no home chapter yet, and §1.3(O)'s stranded-backlog
   problem is already live.

**Retro-application, whichever you pick.** Map 19 (Grott-Hole) is also `DarkMap: true` and already
shipped lit through **CH03's §9 gate**, unremarked. The V2 doc calls this "a live class-P instance in a
gated chapter, found by enumeration, not by walking." Options (2) and (1) reopen CH03; (3) and (4)
ratify what already shipped.

**Coupled but separable.** The hardcoded `False` is a §4.5 silent default regardless of which content
option wins — see [C2](#c2-56--requires_flash-hardcoded-false).

#### Answer 

Your read is off on a couple of points. 

First, in pokemon uranium Flash isn't an HM it is a move some pokemon learn through leveling, and it is also TM70.
Second, in Uranium, like in Pokemon Emerald, a 'dark' cave isn't completely dark, instead there is a circle around the player that is lit up.

so, wire up this and any map that says it's dark as dark, use Emerald's native system to handle it.

### A2. Engine map names for 36 and 37 — **hard blocker, trivial**

**The situation.** `map_infos.json` names both maps "Passage Cave". `reference/map_name_overrides.json`
records both as `"CORRECT — no override"`. `MapConstantRegistry.mint` is strict outside the Map Walker
and raises:

```
map 37 ('Passage Cave') -> MAP_PASSAGE_CAVE collides with already-minted map 36;
add a map_name_overrides.json entry
```

This is CH05's *first* blocker — it fires before any interesting work. (`PROJECT_TODO.md` #53.)

**Options.**

1. **`PassageCave` / `PassageCave2`** → `MAP_PASSAGE_CAVE`, `MAP_PASSAGE_CAVE_2`. *(doc leans —
   `05-passage-cave.md` §2 proposes it.)* *Cost:* the `2` carries no meaning to a player or a reader.
2. **Descriptive split** matching house style — map 19 was already disambiguated to
   `"Passage Cave Grott-Hole"` in CH03's scope pass, so precedent exists for a semantic suffix
   (e.g. entrance level vs. inner level, once you've seen the layouts).
3. **Rename one map entirely** if the wiki or in-game signage gives them distinct names.

**Note:** no `engine/data/maps/` entry exists for either map yet, so nothing downstream is pinned;
this is a free choice now and an expensive one later.

**Deliverable either way:** two `overrides` entries with evidence in `reference/map_name_overrides.json`.



#### Answer

Map 36 is 'Passage Cave 1F' and Map 37 is 'Passage Cave 2F' 

### A3. Sableyeite vs. the atlas's "first Mega Stone" credit

`05-passage-cave.md` §7.3 finds a Mega Stone (Sableyeite) on map 036, while `00-atlas.md` credits
CH40 with the first Mega Stone.

**Options:** (1) confirm CH40's credit is wrong and correct the atlas; (2) confirm both are genuine
Mega Stones and reword the atlas's phrasing; (3) find that Sableyeite is not a Mega Stone in Uranium's
own terms and drop the flag. Needs the atlas maintainer's ruling, not a build agent's.

#### Answer

The Sableyeite is on the other side of some water that will need to be surfed over. since we do not have that ability at this point we can not access the Mega Stone. We can assume for now that CH 40 is the first chapter where there is a Megastone on the map and we can reach it the first time we come to that map. don't check that. the only thing relevant to ch 5 that we need to clear up is that the megastone should come back as defered due to being currently unreachable and blocked by surf.



---

## B — Disposition-vocabulary calls forced by CH05's data

CH05 inverts CH04's disposition distribution. CH04's 42 rows were carried mostly by
`unreachable`-geography (24 rows). CH05's projected 25 rows are **15 `beat:`, 4 `blocked:surf`,
2 `cosmetic`, and 4 with no correct verdict at all** — no geography gate anywhere. The V2 doc's
summary: *"CH05 is the first chapter where the weakest check carries the load."*

### B1. The four staircases — the vocabulary has no correct verdict

**The situation.** Map037 has four "Stairs" events (ev3 (20,10), ev6 (20,9), ev7 (11,10), ev8 (11,9)):
`trigger=1` player-touch, `through=false`, code-111 facing branch, forced diagonal move route. The
manifest generator marks each `may_be_cosmetic=True` (they write no state), `needs_citation=False`,
`is_dispositionable=True` — so **`cosmetic`, one keystroke, disposes of the map's principal traversal
mechanic and `check` exits 0.**

BFS against the repo's own `layout.column_blocked` proves they are load-bearing:

| target | stairs walkable | stairs blocked |
|---|---|---|
| cave exit (16,5) → Nowtoch | reachable, 35 steps | **UNREACHABLE** |
| trainer Nuñes, adj (23,10) | reachable, 23 | reachable, same path |
| gift NPC, adj (9,7) | reachable, 26 | reachable, same path |

The idiom occurs **222 times corpus-wide**. `tileset_converter/stairs.py` already classifies all four
correctly; the beat layer is simply not one of the two layers that knows.

**Options.**

1. **Absorb into a terrain row.** The generator learns the stair fingerprint from `stairs.py` and emits
   `kind="terrain"`, `behaviour=MB_SIDEWAYS_STAIRS_*`, **with no page row**. *(doc leans — "reuse
   `stairs.py`; do not write a second detector.")* *Cost:* Q5's `terrain` row kind is decided but
   unbuilt, and Q5 was framed as *adding* invisible rows; this needs the mirror operation —
   *absorbing* a page row — which **is in no decision yet**. Naive implementation double-counts:
   4 page rows *and* 4 terrain rows for 4 staircases.
2. **Allow `cosmetic` with a counted exemption.** Cheap, honest-ish, and leaves the weakest verdict
   carrying the chapter's traversal.
3. **Mint a new page verdict** (e.g. `traversal:`) for pages whose only realization is a metatile
   behaviour. *Cost:* new vocabulary, and it competes with (1) for the same job.

Whatever wins here also decides whether the staircase is a Q0 Tier-1 *template* or leaves the page
world entirely — see [D4](#d4-q0--archetype-templates-and-two-new-tier-1-members).

#### Answer

Sideways stairs show up again and again, the rout generator should absolutely recognize them and handle them without issue or hand holding. sounds like option 1 would do that, if I'm wrong bring it to my attention, if not do it. 

### B2. TM76 and Sableyeite are Surf-sealed — a second, later revisit debt

**The situation.** Map036 has 513 walkable tiles in 7 components; 450 are reachable on foot from the
entrance (17,39). TM76 (31,15) and Sableyeite (34,12) sit in a **sealed 30-tile room** (bbox x31–36,
y11–16), walled on three sides, opening only into a disconnected water pocket (terrain tag 7,
`isSurfable?`). Surf is granted at Map143, **deep in Act 5** — the longest capability deferral in the
corpus so far.

This is genuinely good news for slice 2: it is a **terrain-derived** `blocked:` case, the exact surface
Part 4c called structurally invisible, so slice 2 gets a real test instead of deferring all validation
to a retroactive CH01–CH04 re-derivation.

**Options.**

1. **`blocked:surf` on all four rows** (map036 ev008 + ev009, both pages each), with B6/B7 authored as
   **deferred beats** in the CH02/CH04 `DEFERRED_BEATS` idiom. *(doc leans.)* *Cost:* CH05 acquires a
   revisit debt owed to an Act-5 chapter that does not exist in `chapters.json` yet — §1.3(O)'s
   stranded-backlog arm gets much longer.
2. **Mint the Act-5 Surf revisit chapter now**, following Q11's CH07A precedent, so the debt has a
   named home the moment it is created.
3. **Strip the two items** as unreachable-in-practice content. *Cost:* fidelity; and the room is
   legitimately reachable later.


#### Answer

We should be landing on option 1 here but we should be diriving that from the route finder not from you asking a question.


---

## C — Fail-loud repairs and standing regressions

§5.12 calls the first two of these "prerequisites, not follow-ups." Code state re-verified 2026-08-31.

### C1. #54 — `unhandled: 0` is indistinguishable from "never staged"

`transpile_unhandled.jsonl` has 332 rows; the 244 map-tagged ones fall on exactly the 16
`SLICE_MAP_IDS` maps. Maps 36/37 have never been staged → every CH05 row gets `unhandled: 0`
(`chapter_manifest/generator.py:460`, `.get(key, 0)`) → `ManifestRow.may_be_cosmetic`'s unhandled-queue
veto (`schema.py:284-291`) **passes vacuously for the entire chapter**. CH04 did not expose this
because map 35 was staged before its manifest was generated.

Note the compounding with [B1](#b1-the-four-staircases--the-vocabulary-has-no-correct-verdict): the
cosmetic verdict is simultaneously mis-derived on the staircases *and* unvetoed chapter-wide.

**Options.**

1. **Build the fix:** record the map ids the queue covers; emit `unhandled: null` outside it;
   `may_be_cosmetic` False until staged and regenerated. *(doc leans — "a prerequisite for trusting any
   pre-build manifest.")* Touches `generator.py` + `schema.py`.
2. **Procedural workaround:** make stage-before-generate an explicit ordering rule in `BUILD_PLAN.md`
   and stage 36/37 first. Free, but relies on remembering — the exact failure shape v1 existed to kill.
3. **Accept for CH05** and note the veto is vacuous.



#### Answer

Build the fix

### C2. #56 — `requires_flash` hardcoded `False`

The mechanical half of [A1](#a1-cave-darkness-given-hm05-is-ungrantable--hard-blocker), separable from
the content call.

**Options.** (1) header reads parsed `dark_map` and **fails loud on a dark map until a decision is
recorded** *(doc leans)*; (2) wire it honestly to whatever A1 decides and skip the fail-loud;
(3) leave the literal and record A1's outcome in prose only. Option (1) is the only one that protects
the other 24 dark maps from repeating map 19's silent pass.

#### Answer

again, we should be using Emeralds handling of how a dark cave is rendered without using flash. 


### C3. #65 — CH01–CH03 manifests no longer load *(regression)*

Verified empirically: `row_from_dict` fails on the first row of all three
(`CH01 map032/ev001/p0`, `CH02 map033/ev002/p0`, `CH03 map019/ev001/p0`) with
`missing ['reachability_consulted']`. Slice 2 added the field (`schema.py:271`) with strict field-set
equality (`schema.py:438-451`) and the three manifests were never regenerated. `_VERDICTS` also dropped
`deferred:`/`unreachable:<reason>` for `blocked:<set>`; only CH04's dispositions were hand-migrated.

**Options.** (1) regenerate all three now — needs per-(chapter,map) verified start cells, and
`_CHAPTER_MAP_START_CELLS` covers CH04 only; diff before commit; (2) build Q5's `PRE_MANIFEST_CHAPTER`
marker and let them be legibly absent; (3) leave broken through CH05 — CH05 does not read them.
Note (3) keeps **#67 item 1 blocked** (CH01–CH03 cannot be route-solved) and keeps the decided
whole-corpus re-disposition ([D8](#d8-whole-corpus-re-disposition-during-ch05s-build)) impossible.

#### Answer

We'll deal with them after ch5

### C4. #64 — `CapabilityModel.grants_capability` is the wrong signature

`checker.py:59`: `def grants_capability(self, name: str) -> str | None` — assumes a capability is a
boolean granted at one place. Uranium grants field moves by disjoint routes
(`rock_smash = numbadges>=1 AND (knows ROCKSMASH OR holds BOXINGGLOVES)`); `old_rod` gates on
`var[103]>=5` with no derivable name. 28 `capability_model_unenforced` warnings stand on CH04.

CH05 makes this concrete: its four `blocked:surf` rows are exactly what the rule would enforce.

**Options.** (1) redesign the Protocol to take predicates over player state, hand-annotating
non-derivable gates — unknown scope, all call sites; (2) accept the warnings through CH05 as already
agreed on 2026-08-22, and revisit when CH06 (the grant chapter) lands; (3) hand-annotate only the
capabilities CH05 needs (`surf`) as a narrow stopgap.

#### Answer

Old rod isn't a field move, it doesn't gate access to any area. it lets you fish, a specific kind of wild encounter and we'll deal with it when we get to the chapter that goes back through route 1. where ever we have written down that old rod is somehow a field move lets correct that. as for the actual question you asked, stikc with option 2

---

## D — Decided-but-unbuilt: build before CH05, or not

All seven verified absent in code on 2026-08-31. The V2 doc names **three** as the ones "CH05 will
actually walk into": D1, D2, D3.

### D1. Q1 — coordinate resolvers and the literal-ban lint

**Decided 2026-08-28:** resolvers only; integer coordinate literals **banned** in `chapters/*.py` and
enforced by lint; escape hatch `raw_cell(x, y, why="...")`, counted per chapter.
**Built:** the prerequisite (slice 1's offline graph) shipped. `approach_to()`, `entry_cell()`,
`warp_cell()`, `raw_cell()` and the lint do not exist. `chapters/route2.py:253`
(`LARRIE_APPROACH = (18, 37)`) is still a bare int-tuple.

**Why it matters now:** CH05 is the **first chapter authored after the ban**. Without the lint, its
chapter file reproduces exactly the pattern the decision outlawed — and three CH04 failures traced to
unverified coordinate literals.

**Options.** (1) build resolvers + lint before authoring; (2) build the resolvers, skip the lint
(author discipline — already failed three times); (3) author CH05 with literals and retrofit, accepting
that CH05 becomes the corpus's next cleanup target.

#### Answer

Option 1

### D2. Q10 — bidirectional `DEFERRED_*` registration rule

**Decided 2026-08-28:** every `beat:Bn` disposition row must name a **registered** beat, and every
`DEFERRED_*` entry's row must be dispositioned as something **other than** `beat:`. (The naive
row-vs-entry rule has an axis error — rows are per-page, entries per-beat; it scored 0/28 on CH04.)
**Built:** `blocked:tooling:` shipped. The rule did not — `RULE_ORPHAN_DISPOSITION`
(`checker.py:35`, fired :345) checks a different mismatch. CH04's own contradiction (route2.py lists
B8/B10 as unregistered while `CH04.dispositions.json` disposes them `beat:B8`/`beat:B10`) is still
undetected today.

**Options.** (1) build before CH05 — CH05 will register deferred rows ([B3](#b3-does-ch05-register-deferred_-rows-at-all)),
so this is its first live test; (2) defer and hand-check CH05's deferred set; (3) take Q10's rejected
option (b) — generate the Python tuples from the disposition file — which was rejected for making the
chapter file partly generated.


#### Answer

Option 1

#### BUILT 2026-09-01 — the two directions are one scan, and CH04's contradiction is real

Shipped as `RULE_UNREGISTERED_BEAT` + `RULE_BEAT_MODEL_UNENFORCED` and the `BeatModel` Protocol in
`checker.py`, the concrete adapter `chapter_manifest/beat_model.py`, and `load_chapter_module` in
`playtest/chapter.py` (the built `Chapter` holds only *registered* beats, so `DEFERRED_BEATS` — by
definition the ones that were not registered — is reachable only through the module object).

**The bidirectionality collapses.** Both halves key on the beat id: a deferred beat is by
construction not registered, so walking the dispositions and asking the model about each `beat:`
argument catches "every `DEFERRED_*` entry's row is dispositioned as something other than `beat:`"
for free. No second scan over the deferred entries exists, and none is needed. A deferred beat whose
row carries no disposition at all is `RULE_UNDISPOSITIONED`'s job, not this rule's.

**Beat ids match as prefix families.** A disposition names `B4`, but D4's templates register
`B4_battle`/`B4_retalk` via `beat_prefix=`. So `B4` is satisfied by a beat named exactly `B4` or by
any `B4_<something>`, matched on the literal `_` separator — without that, every template-authored
chapter (i.e. CH05 onward) would read as entirely unregistered; with a naive `startswith`, `B4`
would be satisfied by `B40_x`. Verified against the real CH04 module: `B4` and `B14` resolve
independently.

**CH04's contradiction was real and is now visible.** The rule fires on exactly two rows —
`map035/ev001/p1` (`beat:B8`) and `map035/ev003/p1` (`beat:B10`) — both disposed `beat:` while
`ch04.py`'s `DEFERRED_BEATS` names them, with the recorded reason quoted in the finding. Zero false
positives on the other 11 `beat:` dispositions. CH04 is `status: "built"`, so these land as
**counted debt** (warning), not a red build, under the same live/gated severity policy as
`RULE_ARCHETYPE_CONFORMANCE`. B8's own deferral reason says "restore once CH05 stages Map036" — so
CH05's build is the moment to resolve it, and that is a content decision for the operator, not
something the rule decides.

### D3. Q9 items 1–3 — the operator read-through as a named gate step

**Decided 2026-08-28:** a named step in `BUILD_PLAN.md`'s per-chapter loop, **before** approve-before-build,
with a checklist framed on *verdict-correctness* ("is each verdict answering the right question for this
row's kind", "was any row on the page skipped") and a decaying blind-spot appendix.
**Built:** item 4 only — the ROUTE step at `BUILD_PLAN.md:97` (position 5 of 9: SELECT, EVENTS, ART,
WIRE, ROUTE, BUILD, BOOT, FIX, RECORD). No read-through step, no checklist, no appendix.

**Why it matters:** in CH04 this read-through caught 4 missed beats and a wrong `cosmetic` rule
definition — the doc calls it "CH04's highest-yield single step," and it still has no home in the loop.
CH05's disposition distribution ([§B](#b--disposition-vocabulary-calls-forced-by-ch05s-data)) leans on
`cosmetic` harder than any chapter so far, which is precisely what the read-through catches.

**Options.** (1) add the step and checklist before CH05; (2) run the read-through informally again and
formalize after; (3) skip it for a 2-map chapter.

#### Answer

Option 1

### D4. Q0 — archetype templates, and two new Tier-1 members

**Decided 2026-08-27/28:** templates as **helpers the author calls per instance**, backed by a coverage
checker; extend by parameter never fork; explicit counted `archetype_exempt(row, why=...)` opt-out;
conformance is an ERROR on the live chapter and a counted debt elsewhere.
**Built:** nothing — no `template`, `archetype`, or `archetype_exempt` symbol exists.

The build-status note reclassifies this as *"an authoring-cost decision to make deliberately, not a
correctness gate for a 2-map chapter."* But CH05's dry-run adds two members to the Tier-1 set:

- **Arrival-nudge autorun (§5.6) — 324 instances across 73 maps.** `map036/ev002/p1` is **byte-identical,
  field for field**, to CH04's `map035/ev001/p1` (already `beat:B8`). Larger than item ball (243),
  staircase (222), cave exit (102) — bigger than everything except door/warp (996), and often the *other
  page* of those same warp events. It was missed because §4b censused by event role, not by page: the
  same event-vs-page axis error Q0 identified for trainer re-talk, biting in the other direction. Two
  instances already trip Q6's promote-on-second-use trigger.
- **The staircase leaves the page world entirely**, if [B1](#b1-the-four-staircases--the-vocabulary-has-no-correct-verdict) option 1 wins.

Also noted: three CH05 item balls use sprite `PU-POKEBALL`, one (Sableyeite) uses `PU-MegaStone` — a
template keyed on the sprite misses it; keyed on `pbItemBall` it does not.

**Options.** (1) build Tier 1 (trainer, item ball, door/warp, cave exit, arrival-nudge) before CH05 —
grill warning: *"a weak archetype industrializes a weak oracle"*; (2) build only the arrival-nudge
template, since it is the largest and CH05 needs it; (3) defer the mechanism, author CH05 bespoke, and
accept a second corpus-wide retrofit later.


#### Answer

Option 1

#### BUILT 2026-09-01 — four templates, not five, and the prescription is a floor

Shipped as `chapter_manifest/archetypes.py` (fingerprint classifier, a pure function of
`ManifestRow`), `playtest/archetypes/` (`trainer`, `item_ball`, `warp`, `arrival_nudge` templates +
`ChapterArchetypeModel`), `RULE_ARCHETYPE_CONFORMANCE` + `ArchetypeModel` in `checker.py`,
`Disposition.archetype_exempt`, and `chapter_manifest/archetype_model.py` wiring the two together in
the CLI. Frozen expectations: `reference/frozen/archetype_expectations.json`.

**Four Tier-1 members, not the six listed above.** The **staircase left the page world entirely**
when [B1](#b1-the-four-staircases--the-vocabulary-has-no-correct-verdict) landed on 2026-09-01 —
Map037's four staircases are `terrain` rows now, so there is nothing for a page template to claim
(independently confirmed: CH05's generated manifest carries 4 terrain rows and no staircase page
rows). And the **cave exit folded into the warp template as a parameter** rather than becoming a
fifth template: `ManifestRow` cannot distinguish a cave exit from a door — the code-201 destination
is not on the row — and the axis that actually varies is which navigation helper applies
(`enter_door` / `cross_threshold` / `cross_arrow_warp`), which is the beat author's parameter, not a
classification. That is Q0 rule 2 ("extend by parameter, never fork") working as intended.

**Two operator calls made at build time.** `archetype_exempt` is a field on the disposition row, not
a call in the chapter module — the exemption is a claim *about a manifest row*, it must work for rows
with no beat and for gated chapters that predate templates, and it keeps `checker.py` from importing
`playtest`. And the item ball's spent page is `cosmetic` by default with a `negative_beat=True`
parameter promoting it to a real "re-touch grants nothing" beat.

**The prescription is a floor on strength, not an equality — and CH04 taught us that.** Run with `!=`,
the rule reported 10 findings against CH04's committed, gate-passed dispositions, and all 10 were the
rule's error:

- 8 rows are genuine trainers and item balls north of Route 2's rockslide gate, correctly
  `blocked:rock_smash` until CH07. An archetype says what *kind* of event a row is; it cannot demand a
  beat for a row no player can walk to. `blocked:` / `unreachable:` supersede the prescription.
- `map035/ev009/p1` is a deliberate negative beat whose note already recorded the definition it was
  reclassified under on 2026-08-25: *"cosmetic means no trigger to press, not merely no state write."*
  That is the `negative_beat` arm, hand-derived a week before templates existed, so `beat` satisfies a
  `cosmetic` prescription.

What remains is the pair worth erroring on: a row with **no disposition at all** (the B14 shape) and a
load-bearing archetype page **waved through as decoration**. CH04 now reports 0 archetype errors;
CH05, generated and undispositioned, reports 19 errors, all "no disposition at all".

**Standing debt, counted not silent:** with the beat-claim half wired, CH04 reports 9 warnings for
rows whose beats exist but predate templates and so carry no `archetype=`. Warnings rather than errors
because CH04 is gated — the decided "ERROR on the live chapter, counted debt elsewhere" behaviour.

**Two corrections to the record this produced.** CH05's maps 36/37 **are** staged — its manifest
generates for real, so C1's `unhandled: null` arm does not apply to it. And **Uranium's source
contains no U+2019 anywhere**: the curly apostrophe commit `2a4e4b61` dodged is manufactured by our own
decoder, because `engine/charmap.txt:91-92` defines byte `B4` twice (`’` then `'`) and the inverter
keeps the first. `playtest/text_source.py` now normalizes source text through that same table, so the
character cannot be dodged; the inversion lives in one place (`playtest/charmap.py`) instead of two.

### D5. Q2 — `oracle=` on beats

**Decided 2026-08-27**, coupled to `at=` enforcement. **Built:** no — `playtest/chapter.py:230`'s
`beat()` signature has no `oracle` parameter. Its stated prerequisite (`at=` enforcement via the route
plan) **is** built, so the gate is open.

Scoped to bespoke beats only; templated beats get their oracle from the Q0 template — so its cost
depends on [D4](#d4-q0--archetype-templates-and-two-new-tier-1-members).

**Options.** (1) build now, while the prerequisite is fresh and CH05's beats are unwritten;
(2) defer until Q0's templates exist, so fewer beats need it typed by hand; (3) drop it and rely on
the read-through ([D3](#d3-q9-items-13--the-operator-read-through-as-a-named-gate-step)).


#### Answer

Option 2

### D6. Q4 — per-chapter input fingerprint (class P staleness)

**Decided 2026-08-28:** each chapter fingerprints **every decoded artifact its beats actually consumed**,
derived from slice 1's graph — `map.bin`/`border.bin` collision (scoped to touched tiles),
`seam_warps.json`, `terrain_tag_map.json`, `tileset_map.gen.json`, encounter tables.
**Built:** no — `generator.py` hashes only `content_hash(page)` (:454) and `content_hash(list(conn))`
(:492, :506).

**Live instance:** map 19 shipped lit through CH03's gate and nothing noticed — the class-P case
[A1](#a1-cave-darkness-given-hm05-is-ungrantable--hard-blocker) reopens.

**Options.** (1) build now, so CH05 is the first chapter fingerprinted correctly from birth;
(2) defer — nothing in CH05 goes stale during CH05; (3) build only the small whole-file hashes
(seam_warps, terrain_tag_map, encounters) and defer the scoped `map.bin` work.

#### Answer

Option 1


### D7. Q6 — forced helper promotion

**Decided 2026-08-28:** (c) any helper used by two chapters must be promoted at the second chapter's
gate + (d) no chapter-local shadowing of a public `assertions.py` name, enforced by (b) an **AST
duplicate/near-duplicate detector comparing bodies, not names**; the only escape hatch is
parameterization (`absorb_trainer=True`), never a rationale comment.
**Built:** no detector exists; `route1.py`'s shadowing helpers are unpromoted.

**Options.** (1) build the detector before CH05 adds a third chapter's worth of helpers; (2) apply
rules (c)/(d) by hand during CH05 authoring; (3) defer entirely — this is code hygiene, not correctness.

#### Answer

Probably will do 2 but defer for now


### D8. Whole-corpus re-disposition during CH05's build

**Decided 2026-08-28** as part of Q3: re-disposition the entire built corpus during CH05's build, with
a freeze → derive → diff → write ordering safeguard (freeze the expected answers *before* deriving, so
the diff is meaningful).

**Blocked by [C3](#c3-65--ch01ch03-manifests-no-longer-load-regression)** — CH01–CH03 manifests do not
load, so there is nothing to re-dispose.

**Options.** (1) unblock C3 and honour the decision during CH05; (2) scope it to CH04 only (the one
chapter that loads); (3) defer the whole re-disposition to a later chapter and record the slip.

#### Answer

I think the whole point was to compare the new derived based authoring vs the hand written version that ch 1 - 3 shipped with. Correct me if i'm wrong here

**Not wrong — and it kills option 2. Deferred (option 3) 2026-09-01.** CH04 was already authored
under the derived flow, so re-disposing CH04 alone compares the new system against itself and proves
nothing; the only chapters that make the comparison mean anything are CH01–CH03, which is exactly the
set C3 broke. So the choice was never three-way. It was: unblock C3 first, or slip.

Slipping, and recording it here rather than quietly dropping it: unblocking C3 means regenerating
three gate-closed chapters' manifests, and doing that inside CH05's build would put a corpus-wide
regeneration on the critical path of a chapter that has its own §9 boot gate to clear. The
comparison does not decay by waiting — CH01–CH03's hand-written dispositions are committed and
frozen, and the derived flow only gets more evidence behind it as CH05 and CH06 use it. **The debt:
C3 must be unblocked before the re-disposition can run at all, and the re-disposition is owed
against CH01–CH03 specifically, not against whatever loads at the time.**

---

## E — Process and scoping

### E1. #66 — mapping an atlas chapter id to its playtest module

`chapters.json` keys by atlas id (`CH04`); playtest modules are named by place (`route2.py`); nothing
records the pairing, so `routing/__main__.py:231` requires a hand-carried `--module`
(verified `required=True`; no `playtest_module` key exists in `chapters.json`).

**Needs your ruling on two things before the obvious fix lands:** what a `playtest_module` field holds
for the ~20 chapters that will never have a module, and whether revisit chapters (CH07A) share the
module of the chapter they revisit.

#### Answer

should they be named by place? why aren't they named by the chapters

**Resolved 2026-09-01 — renamed, field not added.** The question was the better one and it dissolved
the item rather than answering it. There was no reason of substance: CH01–CH03's modules were
written before `chapters.json` and the atlas ids existed, so they took the place names that were the
only identifiers around at the time, and nothing since forced the issue. Both of my sub-questions
(what the field holds for the ~20 module-less chapters; whether CH07A shares CH07's module) only
existed because the field did — with the module *named for* the chapter, a chapter without a module
simply has no file, and a revisit either gets `ch07a.py` or imports CH07's explicitly.

`moki.py`→`ch01.py`, `route1.py`→`ch02.py`, `kevlar.py`→`ch03.py`, `route2.py`→`ch04.py`, and the
`ChapterBuilder` name went with the filename (`"moki"`→`"CH01"`) — renaming only the file would have
left `load_chapter("ch01").name == "moki"`, which is the same mapping problem one layer down. Full
scope and the migrated artifacts are in `PROJECT_TODO.md` Done #66.

`--module` survives on `routing plan` as an *override* defaulting to the chapter id, and every plan
still records `RoutePlan.chapter_module`, because `divergence.load_plan_index_for_module` joins on
the recorded value rather than on the convention. That is deliberate: a convention that holds today
is not a binding the artifact carries, and CH07A is where the two will part company.

### E2. #67 — CH05's route plan

No `reference/routes/` directory exists and no chapter carries a route plan (verified).
`RULE_ROUTE_ORDER` only enforces when the file exists. CH04 *can* be solved but its solver-optimal
order (112 tiles) disagrees with its registered order (130 tiles) — both crossing-free and routable;
the gap is cosmetic walk distance. Slice 4 widens this: `compare_walk` reports `compared: false` for
every chapter.

**Options.** (1) solve and commit CH05's plan as part of its authoring loop, forward-only *(doc leans)*;
(2) also retrofit CH04 to close `compare_walk`; (3) defer route plans another chapter.

#### Answer

option 1

### E3. #51 — the citation-verification second pass

A blind second-agent pass over citation-triggered disposition rows, scoped to CH04 + CH05, kept as
standing practice if it catches ≥1 silent pass across both. CH04's half is done. **This runs during
CH05, not before it** — the decision owed is only whether it still runs, and who does the blind pass.

### E4. Standing guardrail — a green CH05 gate proves less than it looks like

Measured, not estimated (§5.8):

| mechanism | CH05 exposure |
|---|---|
| seam rows / overland connections | 0 |
| `requires[]` populated | 0 of 25 rows |
| `blocked:` derivation | 4 rows, `blocked:surf`, terrain-derived only |
| page conditions on a real global switch/variable | 0 (8 self-switches + 1 runtime predicate) |
| unrecognized script heads | 0 |
| `unhandled` queue join | 0, vacuously |
| mart / PC / Center templates | 0 instances |

Of the two structural holes v1's dry runs found — invisible overland seams and the unrecognized-head
rule — **CH05 exercises neither**. Slice 1, by contrast, is exercised hard.

**The decision:** whether to record this explicitly in `05-passage-cave.md` and the gate record, so a
green CH05 is not later cited as evidence that slice 2, the capability model, or the mart/Center/PC
templates work.

### E5. Non-blocking items that could ride along

- **#61** — B26's re-triage (`deferred` → `unreachable`; flag `sw130`/`FLAG_FILE_RECOVERY` is never set
  anywhere in the corpus) is actionable **now**, independent of CH25.
- **#63** — CH04's two owed negative beats (`map035/ev014/p1`, `map035/ev017/p1`); deferred to CH07A.
- **#57** — 12 unmodelled walked legs, blocked on chapters acquiring manifests (so on [C3](#c3-65--ch01ch03-manifests-no-longer-load-regression)).
- **#49** — checker rule 7 + rule-set versioning; matters most once CH06/CH07 land.
- **§5.9's ordering constraint — satisfied, not owed.** Slice 1 landed before the `_route_waypoints`
  fail-loud (`f780a972`, `364732ac`, `46bd2efe`, then `f705b642`); slice 1 closed `c9f73178`/`31ddb7c5`;
  regression test `tests/test_traversal_map037_golden.py`. **No action.**
- **Code 408** (`Comment (continuation)`) added to `_CODE_IGNORED` — **fixed** `511ef4af`. **No action.**

---

## F — A proposed minimum path

Not a decision — a suggestion for what the smallest defensible set looks like, offered so the "defer
everything" and "build everything" ends of the range are both visible.

**Cannot start without:**
- A1 (darkness) and A2 (names) — the build literally halts on A2's `mint`, and A1 determines what the
  maps look like.

**Should land before authoring, cheaply:**
- C2 (`requires_flash` fail-loud) — falls straight out of A1 and protects 24 other dark maps.
- C1 (`unhandled` null) — otherwise every cosmetic verdict in the chapter is unvetoed, in the one
  chapter where `cosmetic` carries the load.
- B1 (staircase verdict) — decide it before the manifest is generated; regenerating after is a diff you
  will not enjoy reading.

**Highest yield per hour, if you build anything from §D:**
- D3 (read-through step) — cheapest of the three, and CH04's best-performing single step.
- D1 (resolvers + lint) — CH05 is the last moment this is free rather than a retrofit.
- D2 (registration rule) — only if B2/B3 register deferred rows, which they almost certainly will.

**Explicitly reasonable to defer for a 2-map chapter:** D4 (except possibly the arrival-nudge template),
D5, D6, D7, C3/C4, D8. *(E1 was deferrable on cost grounds but got built anyway on 2026-09-01, because
the operator's answer replaced the proposed `playtest_module` schema field with a rename — cheaper than
the thing it was compared against, not more expensive. D8 was deferred as proposed.)*

**Decide deliberately, don't drift into:** D4. It was recommended "before CH05" and quietly reclassified
as authoring cost. That may well be right — but it should be a call, not an omission, since the
arrival-nudge idiom alone is 324 instances waiting.
