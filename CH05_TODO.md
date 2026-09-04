# CH05 — Passage Cave: live work items

**Status:** in progress. Branch `ch05` cut; steps 0-5 done and verified.
**You are here:** → **STOP 3**. Step 6a has been run: `reference/routes/CH05.locations.json`
holds 12 derived routing points and `reference/routes/CH05.route.json` solves clean
(155 tiles, no `CROSSING`) — the first route plan any chapter has ever carried. Review
it in the map viewer (maps 36/37, Events mode), then approve the order and go to 6b.

**What this document is.** The execution path for CH05. Two other documents already
exist and this one does not repeat them:

| Document | Answers |
|---|---|
| `reference/chapters/05-passage-cave.md` | *What* CH05 contains — beats B1-B11, inventory, risks |
| `CH05_DECISIONS.md` | *Why* it is built this way — the A/B/C/D/E design calls |
| **this file** | *How* to build it, in order, with commands |

It is a **living document.** The "you are here" marker above moves, checkboxes get
ticked, and findings get appended to §Log as we go. It is not a plan written once and
then obeyed — when reality disagrees with it, the document is what changes.

On gate pass it retires to `reference/archive/` and its carryovers migrate to
`PROJECT_TODO.md`, same as `CH02_TODO.md` … `CH04_TODO.md` before it.

---

## How to read the effort annotations

Each step carries a line like:

> **Effort — you:** 10 min, mechanical · **me:** low · **attended:** no

- **you** — your wall-clock time, and whether it is mechanical (run a command, read a
  number) or judgement (you have to decide something).
- **me** — my context/token load, coarse **low / medium / high**. This is a *relative
  ranking, not a measurement.* I have no meter. Treat it as "which steps to be careful
  about," not as a budget in any real unit.
- **attended** — whether we need to be working at the same time. "no" means you can
  run it and hand me the result later, or I can run it while you do something else.

The two budgets are genuinely different and pull in opposite directions: the steps
that cost me most (READ synthesis, FIX) are the ones where handing you more work does
not help, and the steps that cost you most (the boot walk) cost me almost nothing.

---

## Ground rules carried into this chapter

1. **Scope is closed.** CH05 does CH05, plus `PROJECT_TODO.md` #62 and #67. Anything
   else that surfaces gets **filed, not fixed** (§Deferred below lists what is already
   ruled out and why). The guardrail from `BUILD_PLAN.md` §2 is that the *next*
   chapter should need data changes, not code changes — scope creep here is how a
   chapter degrades into a content grind.
2. **No local LLM this chapter** (decided 2026-09-02, reversing the earlier plan). We
   work through it together: you run the mechanical commands, I do synthesis and
   authoring, you make the calls and pull me in when stuck.
3. **Output goes to disk, not into chat.** Noisy commands (`make modern`, `phase5`)
   redirect to a log under `output/` — tell me the path and the exit code, and I read
   the tail or grep it. Short summaries (`chapter_manifest check`, `routing plan
   --dry-run`) are a screen or less; paste those directly.
4. **Five stop points, not ten.** Marked ⏸ below. Steps 1-4 run as one uninterrupted
   mechanical block because there is nothing to decide in them — they either succeed
   or fail loud. Failures interrupt regardless of the marks; how we handle a given
   failure gets decided when it happens, not pre-committed here.
5. **Every command below is copy-pasteable as written.** `$V` is
   `/home/b/repos/rpg2gba/.venv/bin/python`; set it once per shell:
   ```bash
   V=/home/b/repos/rpg2gba/.venv/bin/python
   ```
   Never set or export any `RPG2GBA_*` variable — `.env-paths` is already correct and
   a shell override silently redirects the build at a tree that cannot work
   (`CLAUDE.md` §3).

---

## Step 0 — prerequisites and branch

**Effort — you:** 5 min, mechanical · **me:** low · **attended:** no

Everything here is *in-between work* and belongs on `main` by the standing rule that
branches are for chapters only. The branch gets cut at the **end** of this step.

- [x] **D1-D4 verified as actually built** (2026-09-02). All four shipped; D1/D3 in
      commit `758abc5b`, D2 in `d3cddc5d`, D4 separately. `tests/test_chapter_coordinate_literals.py`
      20 pass, the D2 checker suite 85 pass, and `chapter_manifest check --chapter CH04`
      fires its two documented deferred-beat findings live rather than being dead code.
- [x] **`CH05_DECISIONS.md` D1/D3 sections corrected** (2026-09-02). Both still read
      "Built: … do not exist" long after the code landed; only D2 and D4 ever got a
      reconciling addendum. Fixed, because that doc is the one we consult mid-chapter.
- [x] **`PROJECT_TODO.md` #28 Cave half resolved, #62 part 1 marked done.** See §Deferred.
- [x] **Cut the branch.**
      ```bash
      git switch -c ch05
      ```

**What good looks like:** `git branch --show-current` prints `ch05`, and `git status`
is clean because everything above was already committed to `main`.

---

## Step 1 — SELECT

**Effort — you:** 30-45 min, mechanical · **me:** low · **attended:** no

Not a judgement call. The chapter comes from the atlas chain in order, and CH05's
binding is already written: `reference/chapters.json` gives **maps 36 and 37**, act
A1, predecessor CH04, traversal `35 → 36 ↔ 37 → 40` confirmed by the warp graph.

**Revised 2026-09-04 — this step is four pinned lists, not one.** The doc previously
claimed the "one real action" was `SLICE_MAP_IDS`. That is wrong and it cost a full
debugging loop in step 2: most of the pipeline derives from `SLICE_MAP_IDS`, but
**trainer pics, trainer battles, and species do not.** They are hand-maintained,
append-only tuples, and the transpiler's fork-index gate fails on the *last* of them
you forget, one at a time, with each failure looking unrelated to the previous.

Do all of these before running step 2.

- [x] **Maps.** Add `36, 37` to `SLICE_MAP_IDS` in
      `src/rpg2gba/tileset_converter/map_set.py:34`, following the existing
      per-chapter comment convention above it.
- [x] **Trainer battles.** Append the chapter's trainers to `SLICE_TRAINER_BATTLES`
      (`src/rpg2gba/trainer_converter/common.py:117`) **in map event order**. CH05:
      `TRAINER_MANNY_5` (Map036 EV004), `TRAINER_KEICHI_248` (Map036 EV006),
      `TRAINER_NUNES_128` (Map037 EV004). Order is load-bearing — fork trainer ids are
      assigned by position off `PRISTINE_TRAINER_ANCHOR`, so this list is append-only.
      Never reorder or remove.
- [x] **Trainer pics.** Append a `TrainerPicSpec(<trainertypes.dat id>, "<INTERNAL>")`
      to `SLICE_TRAINER_PICS` (`common.py:69`) for each trainer *class* not already
      staged. CH05 needed only `TrainerPicSpec(16, "BLACKBELT")` for Keichi — Manny and
      Nuñes are HIKER, already staged for CH04's Chuck. Verify the id against
      `output/uranium-build/intermediate/trainer_types.json` **and** confirm a real
      `Graphics/Characters/trainer<NNN>.png` exists before pinning it.
- [x] **Trainer class mapping tables.** A new class also needs two rows in
      `src/rpg2gba/trainer_converter/battles.py`: `_CLASS_PIC_INTERNAL_NAME:66`
      (class → the internal name you pinned above) and `_CLASS_ENCOUNTER_MUSIC:82`
      (class → `TRAINER_ENCOUNTER_MUSIC_*`). **Derive the music from the fork, never
      guess** — the constants' own comments in `engine/include/constants/trainers.h`
      name the classes they serve, and vanilla's own entries in
      `engine/src/data/trainers.h` confirm it. CH05: `TRAINER_CLASS_BLACK_BELT` →
      `TRAINER_ENCOUNTER_MUSIC_INTENSE`, confirmed by both (`trainers.h:562` names Black
      Belts outright; `src/data/trainers.h:1329` uses it).
- [x] **Species.** Append a `SpeciesSpec(<uranium_id>, "<INTERNAL>")` to
      `STARTER_SPECIES` (`src/rpg2gba/species_converter/common.py:64`) for every
      **Uranium-original** species in the chapter's trainer parties. Vanilla species
      (Mankey, Dunsparce) need nothing — the gate unions fork species with staged
      species. **Stage whole evolution families:** `build_staged_species` fails loud on
      a staged species whose evolution target is not itself staged. CH05 needed
      `GROZARD → TERLARD` (Nuñes) and `BAASHAUN → BAASCHAF → BAARIETTE` (Keichi).
      Append-only, same reason as the trainer list.

**Find the party species before you start**, rather than discovering them one failure
at a time:

```bash
$V - <<'EOF'
import json
t = json.load(open("output/uranium-build/intermediate/trainers.json"))["trainers"]
for n in ("TRAINER_MANNY_5", "TRAINER_KEICHI_248", "TRAINER_NUNES_128"):
    print(n, [p["species"] for p in t[n]["party"]])
EOF
```

**Then refresh the two manifests** — the staging chain is *species overlay → trainer
battles → transpiler gate*, each link reading the previous one's manifest:

```bash
$V scripts/stage_species.py
$V scripts/stage_trainers.py
```

**Check the counts, not the exit codes.** `stage_trainers.py` exits 0 while staging
**zero** battles: `stage_slice` drops the whole batch when any single pinned trainer
fails, so one missing species silently un-stages every previously-good chapter too.
A `0 battle(s)` line is a regression, not a pass. CH05's expected numbers are
**32 species** and **20 battles**. (Both scripts write only into `output/`; the full
art pass runs in step 7's assembler. See §Deferred for the all-or-nothing bug.)

Note map **19** is *also* named "Passage Cave" and is **not** ours — it belongs to
CH03, because the warp graph shows it connects only to and from Kevlar (31) and never
reaches Route 02 or Nowtoch. A naive reading of the name mis-assigns it. `chapters.json`
already records this; do not let it surprise you when grepping for the name.

**Why this step is first and separate:** `SLICE_MAP_IDS` is the single source of truth
that *both* the collision emitter and the NPC-passability gate read (`CLAUDE.md` §4.3).
Everything downstream keys off it, so getting it wrong makes steps 2-4 produce
confidently wrong output rather than failing.

---

## Step 2 — EVENTS

**Effort — you:** 5 min to run · **me:** medium (reading the unhandled queue) · **attended:** no

Run the deterministic transpiler over maps 36 and 37. Everything mechanical becomes
Poryscript; anything uninterpretable lands in an explicit unhandled queue.

```bash
$V -m rpg2gba.conversion_agent.transpile_driver run --maps slice > output/ch05-events.log 2>&1
echo "exit=$?"
```

> **Corrected 2026-09-04 — the command here used to be
> `pipeline convert-map --map-id 036/037`, and that is the wrong tool.**
> `convert-map` is the retired Phase-4 orchestrator: its per-event core
> (`orchestrator.py:465-490`) tries the whole-event classifier layer, then a memo,
> then **spawns a live Claude call** (default backend `claude_code`,
> `pipeline.py:302-305`). It has no general transpiler. `transpile_driver` does —
> classifiers first, then `transpiler.transpile_event` for anything unclaimed
> (`transpile_driver.py:1-15`), and no LLM at all. It is also what
> `slice_expansion_runbook.md` step 3 and CH04 both used.
>
> The first CH05 run used the wrong command: 9 of 16 events spawned Claude, **all 9
> came back queued as `agent-flagged unhandled`** — zero net conversions for ~$0.96.
> Six were `Stairs` events on Map037, which `transpile_driver` handles natively (it
> imports `tileset_converter.stairs`).
>
> **Re-run clean 2026-09-04** (after step 1's pinned lists were completed): 18 maps,
> 308 events, no traceback. Both CH05 maps regenerated. Only EV001/EV002 per map are
> queued, both in the corpus-wide `command follows a Transfer Player warp` cluster —
> disposition them at step 5, not here.

**Where the item balls went.** Map036's four item balls (EV003, EV005, EV008, EV009)
appear in **neither** `Map036.pory` nor the unhandled queue, which looks like data loss
and is not. Item balls are object events instantiated from a template, so the
transpiler emits *fields*, not Poryscript — look in
`output/uranium-build/scripts/Map036.template_fields.json`. The LLM run had emitted a
bespoke `lock`/`giveitem`/`setflag`/`release` script plus a minted self-switch flag for
each one: same behavior, four times the surface area, four extra registry flags.

**Good:** exit 0, and the unhandled queue is short and boring. **Bad:** a queue entry
naming a `pbXXX` script call we have never seen, or an unknown command code. That is
the transpiler failing *loud and bounded* by design — it is a work item, not a crash.

Hand me the log path and the exit code; I read the queue, not the whole log.

**Why it sits here:** it needs nothing but the deserialized map JSON, and everything
after it needs its output. It is also the step most likely to surface genuinely new
work, so it runs before you have invested effort in art or wiring.

---

## Step 3 — ART (checkpoint — nothing to run)

**Effort — you:** 0 min · **me:** none · **attended:** no

**This step has no command, and cannot have one.** There is no `art`/`tilesets`/
`quantize` subcommand on `rpg2gba.pipeline`, and no module under `tileset_converter/`
has its own entry point. Do not go looking for one; the number is kept only to stay
aligned with the canonical loop in `BUILD_PLAN.md:86-122`, which every chapter shares.

**Why it exists at all.** The pathfinder slice deferred art, booted, and was
unplayable — a chapter is not done until it is playable *with real art*
(`CLAUDE.md` §9, §11). This checkpoint is the standing refusal to defer it again. It
is a decision already made, not work to perform.

**Where the art actually comes from:**

- **Tilesets — step 4's `pipeline phase5`.** `phase5.convert_all` calls
  `build_slice_tilesets` (`tileset_converter/phase5.py:232`) as its own internal step
  3, *"per-map graphics: synth tilesets + overlay"*. It **produces** the quantized art
  rather than assuming it exists, so it re-runs on every `phase5`.
- **Sprites — step 7's assembler chain.** `phase5` writes only empty-conversion stubs
  (`sprite_emit.write_stub_gen_files`, `phase5.py:350`). Real NPC and player sheet
  conversion is `sprite_pass.run_sprite_pass`, called from
  `scripts/stage_slice_scripts.py:429` and `scripts/assemble_pathfinder.py:214`.

**Its two checks are discharged elsewhere, and are checkboxes there, not here:**

| Check | Discharged at | How you know |
|---|---|---|
| Tileset budget (two hard 1024 caps) | **step 4** | `phase5` exits 0. The guard is `NUM_TILES_TOTAL` / `NUM_METATILES_TOTAL` (`graphics/emit.py:47-48`), raised in `emit_tileset` (`:537-548`) |
| Legibility through Flash darkness | **step 8** | your eyes, on the device |

Pre-checked for CH05: maps 36 and 37 are on neither `WALKER_OVERFLOW_MAP_IDS` nor
`WALKER_EMPTY_MAP_IDS` (`map_set.py:69,77`), so they are expected to fit. That is a
prediction, not the check — the guard at step 4 is the check. If it fires anyway that
is a real finding and it stops the chapter.

**Bad, at either step:** anything that makes you reach for a hand-edit of generated
output — fix the converter instead (`CLAUDE.md` §11).

---

## Step 4 — WIRE

**Effort — you:** 15-30 min, mostly waiting · **me:** low · **attended:** no

Map constants, layouts (collision + warp metatiles), object events, encounters,
connections. This is the heavy mechanical build.

```bash
$V -m rpg2gba.pipeline phase5 --maps slice > output/ch05-phase5.log 2>&1
echo "exit=$?"
```

Then generate the manifest that step 5 reads:

```bash
$V -m rpg2gba.chapter_manifest generate --chapter CH05
```

Two things to expect specifically here:

- **Encounters:** maps 36 and 37 carry only a `Cave` table (Tonemy / Barewl / Grozard /
  Dunsparce, Lv 4-6, densities 15 and 20). It folds into `land_mons`, and that is
  correct, not a compromise — see §Deferred #28. `wild_encounters.py:259-264` logs an
  `uranium_extra` drop at info level for maps that have one; for 36/37 there is
  nothing to drop.
- **Darkness:** `metadata_wiring._dark_map_for` already wires `dark_map` →
  `requires_flash`, and the engine handles the rest natively (`gMapHeader.cave`,
  `FLAG_SYS_USE_FLASH`, `SetDefaultFlashLevel` at `engine/src/overworld.c:1103`, the
  transitions in `engine/src/fldeff_flash.c`). **No new C.** If you find yourself
  writing engine code for cave darkness, stop — something else is wrong.

**Good:** exit 0, manifest written to `reference/manifests/CH05.manifest.json`.

- [x] **Step 3's tileset-budget check, discharged here.** `phase5` exiting 0 *is* the
      check — the 1024 guard raises from inside it. A `ValueError` naming a tileset and
      a count over 1024 stops the chapter; it is not something to work around.

---

## ⏸ STOP 1 — look at the manifest together

**Effort — you:** 15 min, judgement · **me:** medium · **attended:** yes

```bash
$V -m rpg2gba.chapter_manifest review --chapter CH05
```

We look at the generated rows before you spend an hour dispositioning them. What I am
looking for: does the row count and shape match what `05-passage-cave.md` predicts, do
the archetype classifications land where expected, and is anything present that the
spec does not mention. Cheap to catch here, expensive after step 5.

---

## Step 5 — READ

**Effort — you:** 1-2 hours, pure judgement · **me:** medium · **attended:** partly

**This is your step, and it is the highest-yield one in the chapter.** In CH04 the
equivalent read-through caught 4 missed beats and a wrong `cosmetic` rule definition,
and at that point it was still informal with no home in the loop. It has a home now:
`BUILD_PLAN.md:97` step 5, checklist at `reference/guides/read_through_checklist.md`.

**CH05 is the checklist's first real use.** Nothing in the repo shows it has been run
yet — CH04's run predated it. So treat the checklist itself as under test: if it asks
a question that does not fit a row, that is a finding about the checklist.

Work the checklist per row and record a disposition for each:

- Is the verdict answering the right question **for that row's `kind`** (page / seam /
  terrain), not merely mechanically legal?
- **Was any row on the page skipped?** A human's eye slides off a row that was visible
  the whole time. This is the failure the checklist exists for.
- A **verdict-definition** error found here is fixed as a *definition* and re-reviewed
  across every row of that kind — not patched on the one row where you noticed it.

Dispositions go in `reference/manifests/CH05.dispositions.json`. Expected shape from
the spec's B1-B11:

| Beat | What | Template |
|---|---|---|
| B1 | enter cave from Route 2 | `warp` (cave entrance) |
| B2 | Escape Rope pickup | `item_ball` |
| B3 | Manny (HIKER), event-sight | `trainer` |
| B4 | Great Ball pickup | `item_ball` |
| B5 | Keichi (BLACKBELT) | `trainer` |
| B6, B7 | TM76 / Sableyeite | **deferred** — `blocked:surf`, no live beat |
| B8 | warp 1F → 2F | `warp` |
| B9 | Nuñes (HIKER) | `trainer` |
| B10 | NPC gives Revive | **no template** — hand-written |
| B11 | exit to Nowtoch | `warp` (cave exit) |
| — | Map036 EV002 p1 arrival nudge | `arrival_nudge` |

Nine of ten live beats are templated. The templates are *helpers you call*, not a
generator — the rejection of a generator was deliberate
(`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md:309-330`). Beat ordering, B10, and the
provenance prose are hand-written.

**B6/B7 must be authored as deferred beats**, in the `DEFERRED_BEATS` idiom CH02 and
CH04 use — not as live beats. TM76 and Sableyeite sit in a 30-tile room that opens
only into a water pocket disconnected from the walkable region: Map036 has 513 walkable
tiles in 7 connected components, 450 reachable on foot from the entrance, and that room
is not among them. Surf is granted at map 143 (Act 5) — the longest capability deferral
found in the corpus. This is a second, much longer arm on the stranded-revisit backlog
alongside the Rock Smash one.

## ⏸ STOP 2 — after your READ pass

You hand me the dispositions; I check them against the manifest and we reconcile
disagreements. Then:

```bash
$V -m rpg2gba.chapter_manifest check --chapter CH05
```

Expect a `route_model_unenforced` warning at this point — there is no route plan on
disk yet. **Do not read that warning as a pass.** It means the rule could not run.
Step 6 is what silences it.

---

## Step 6 — ROUTE

**Effort — you:** 20 min, judgement · **me:** medium · **attended:** yes

**CH05 is the first chapter in the project to carry a route plan at all.** `PROJECT_TODO.md`
#67: CH01-CH03 cannot be solved (their pre-slice-2 manifests are refused by
`load_manifest`), and CH04 solves but its plan disagrees with its registered order by
18 tiles of pure walk distance — suboptimal, not wrong, and not worth turning a closed
chapter red over. So `RULE_ROUTE_ORDER` has been unenforced for every chapter gated to
date, and slice 3 is validated **forward, from here**.

> **Revised 2026-09-04 — this step used to be circular, and the circle is now cut.**
> `routing plan` imports the chapter's playtest module and reads every routing
> coordinate out of the beats registered there (`solver.py:84-110` takes
> `beat.locations[0]`; `__main__.py:249-252` does a literal
> `importlib.import_module`). So the old step 6 asked you to approve an order using a
> command that could not run until `ch05.py` — the thing the approved order is
> supposed to shape — already existed. Every chapter to date resolved that by
> authoring first, which is exactly why `routing` was built as a *grader*
> (`513b0f00`, "Both beat orders were right, and nothing had ever compared them")
> rather than a planner.
>
> **Step 6a now derives the coordinates from data that already exists at this point**
> — the manifest, the dispositions, and the decoded map JSON — into a small reviewable
> file. That file materializes into an in-memory `Chapter`, so `solver.py` is
> untouched. Locations are pure lookups; behaviour (assertions, facing, prose) stays
> hand-authored at 6b, so the standing rejection of a beat *generator*
> (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md:309-330`) is not reopened.

### Step 6a — derive the beat locations

```bash
$V -m rpg2gba.routing locations --chapter CH05
```

Writes `reference/routes/CH05.locations.json`: one routing point per `beat:`
disposition, each carrying the **resolver that produced it** and **every candidate row
cell it was chosen from**. Read those two fields — they are the review surface. Rules
the derivation applies, all of which fail loud rather than defaulting:

- **Trigger decides the resolver**, not archetype: `player_touch`/`autorun` → the
  event's own cell (you stand *on* a warp you step onto, and on the tile a nudge fires
  from), `action`/`event_touch` → `approach_to`. This locates B10 and B12, neither of
  which is one of the four recognized archetypes.
- **A beat spanning distinct cells routes on its terminal row.** B8, B13 and B14 each
  claim two rows under the round-trip and staircase idioms; a traversal is represented
  by where it *ends*, because routing cost is about where the next beat departs from.
  Multiple pages of one event collapse before this rule is ever consulted.
- **A stair row resolves to its approach cell, never the stair cell.**
- **Seam rows fail loud** — they carry a direction/offset, not a cell, and nothing
  converts one. CH05 has none; a later chapter will hit this.

Then solve against it:

```bash
$V -m rpg2gba.routing plan --chapter CH05 --locations --dry-run
```

Read the summary. **Any `CROSSING` line is a beat that will fire the wrong event** —
fix it here, not after the walk goes wrong.

### Review it in the map viewer

The route is easier to judge as a picture than as a tile count. With the server
running (`python scripts/map_viewer_server.py --port 8765`):

```
http://localhost:8765/map/36     # Passage Cave 1F
http://localhost:8765/map/37     # Passage Cave 2F
```

Press `e` for Events mode; **Beats / Planned / Walked / Dim** are default-on. You get
the solver's ordered polyline (`drawPlannedRoute`, `viewer.js:423`), and — because a
step-6a chapter has no authored module — **derived** beat markers read straight from
`CH05.locations.json`, drawn hollow with a dashed outline and labelled `#<position>
<beat>` so the visit order is legible on the map. Derived rows sort by solved position
in the Beats panel, never by beat id; ids are labels, not an ordering.

This is a **new** use of the overlay. `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md:1105-1112`
promised and shipped it as an *after-the-fact* diagnostic for planned-vs-observed
divergence; the approval gate it specified is the CLI text summary
(`BUILD_PLAN.md:107-110`, "read the summary"). Reviewing the order visually *before*
authoring is better than what is written down, and the wording change belongs in
`BUILD_PLAN.md` — carried to `PROJECT_TODO.md` at step 10, not edited mid-chapter
(§2 guardrail).

## ⏸ STOP 3 — you approve the ORDER

This is a real gate, not a formality (`BUILD_PLAN.md` §2 step 6). You approve the
**order**, not just the beat set: registration order *is* playthrough order, and the
plan is the thing you are signing off. Solving after the beats are written inverts
that — the solver then just grades an order nobody can change without reopening the
chapter, which is exactly the state CH01-CH04 are in.

Because 6a auto-resolves the multi-cell beats, the approval covers **two** things now:
the order itself, and the three derived choices the log lines flag (B8, B13, B14). The
losing candidates are all in the file; overruling one means editing
`CH05.locations.json` and re-solving, not arguing with the solver.

### Step 6b — write the plan and author the beats

```bash
$V -m rpg2gba.routing plan --chapter CH05 --locations
```

- [ ] Author `src/rpg2gba/playtest/chapters/ch05.py`, beat groups in the approved order.
- [ ] **No bare coordinate literals.** CH05 is the first chapter under the D1 ban and
      the lint is zero-tolerance for CH05+ (the CH01-CH04 debt has a ratchet budget).
      Use the resolvers in `src/rpg2gba/playtest/cells.py` — `event_cell`, `approach_to`,
      `warp_cell`, `arrival_cell`, `entry_cell` — and the `raw_cell(x, y, why="...")`
      escape hatch only with a real reason, counted per chapter. Three CH04 failures
      traced to unverified coordinate literals; that is what the ban is for.
      `CH05.locations.json` records the resolver call for each beat, so this is
      transcription, not rediscovery.
- [ ] **Re-solve against the authored module** and confirm it agrees with 6a's plan:
      ```bash
      $V -m rpg2gba.routing plan --chapter CH05 --dry-run
      ```
      A disagreement means the authored beats drifted from what you approved. There is
      no automated equality check between the two yet — see §Deferred.
- [ ] Re-run `chapter_manifest check --chapter CH05`. `route_model_unenforced` should
      now be gone and `RULE_ROUTE_ORDER` enforcing.

---

## Step 7 — BUILD

**Effort — you:** 10-15 min, mostly waiting · **me:** low · **attended:** no

Reconciled 2026-09-04 against `reference/guides/slice_expansion_runbook.md` steps
3-6 (the authoritative runbook) and CH04's build record
(`reference/archive/CH04_TODO.md:362`). The previous two-command block here was
wrong; see §Log.

```bash
$V scripts/stage_slice_scripts.py --write > output/ch05-stage.log 2>&1
echo "exit=$?"
$V scripts/assemble_pathfinder.py > output/ch05-assemble.log 2>&1
echo "exit=$?"
make -C engine -j$(nproc) modern > output/ch05-make.log 2>&1
echo "exit=$?"
```

1. **`stage_slice_scripts.py --write`** — normalizes labels, regenerates `map.json`
   with real page labels, prunes orphan warp blocks, and **runs the real NPC/player
   sprite pass** (`sprite_pass.run_sprite_pass`, `stage_slice_scripts.py:429`). Map
   ids come from `DEFAULT_SLICE = tuple(SLICE_MAP_IDS)` (`:71`), so step 1's edit is
   picked up automatically — do not pass ids.
2. **`assemble_pathfinder.py`** — full fork assembly: tileset graphics (re-run,
   idempotent), layout `.bin`, species/trainer/encounter/rematch staging, copies
   staged artifacts into the engine, emits `uranium_flags.h`. Also runs the sprite
   pass (`:214`). On success it logs the exact `make` line to run next (`:1300`).
3. **`make -C engine -j$(nproc) modern`** — must exit 0.

Run these **by path, not `-m`** — they live in `scripts/` and are not package modules.

> **Why `phase5` is not in this block.** `phase5` builds a disjoint artifact — a
> warps-only Map Walker corpus with **no** Poryscript, events, or NPCs
> (`phase5.py:8-11`), and only empty-conversion sprite stubs (`:350`). It is a
> *prerequisite*, not a build stage: its step 1 mints
> `output/uranium-build/porymap/map_constants.json` (`phase5.py:189-199`), which
> both `stage_slice_scripts.py:416` and `assemble_pathfinder.py:1262` read and crash
> without. Step 4 already runs it, so it is satisfied by the time you get here.
> `phase5` + `make` **alone** — the old block — produces a ROM with stub sprites and
> no Uranium NPC art. That is the bug this reconciliation fixes.

> **Re-run step 2 first if script content changed since it ran.** Nothing detects
> staleness for you. Step 4 (WIRE) does not touch scripts, so in the normal path this
> is unnecessary.

`make modern` must exit 0. Then the headless suite, which is the cheap filter before
you spend your own time walking:

```bash
$V -m rpg2gba.playtest run --chapter CH05 --engine engine
```

## ⏸ STOP 4 — before the boot walk

We look at the headless results together. Anything red gets fixed before you pick up a
device — the boot walk is the expensive resource in this loop and it should be spent on
things only a human can see.

---

## Step 8 — BOOT (the §9 gate)

**Effort — you:** 45-90 min, judgement, hands-on · **me:** low · **attended:** no

Per your standing rule, the walk starts at **the previous chapter's end** — seed from
CH04's blob rather than replaying from the beginning:

```bash
$V -m rpg2gba.playtest seeds --chapter CH04 --engine engine
$V -m rpg2gba.playtest walk --chapter CH04 --at-end --engine engine
```

Then deliver it to the phone:

```bash
tailscale file cp <the .gba> iphone182:
```

## ⏸ STOP 5 — the gate itself

A chapter is not done until it **boots in mGBA and the section is genuinely playable —
warps fire, NPCs sane, layout legible, art included.** You walk it. Specific things to
look at this chapter, beyond the beat list:

- [ ] **Does the cave read in the dark?** Step 3's legibility check, discharged here
  and nowhere else — art that reads fine at full brightness can be unreadable through
  the Flash overlay, and only your eyes on the device can tell you.
- **The arrival nudge on Map036 EV002.** The `arrival_nudge` template has never run in
  a ROM — CH04's `beat:B8` was authored and deliberately never registered, because its
  sibling warp page was out of slice. This is its **first live exercise**, against the
  corpus's second-largest idiom (324 instances across 73 maps, behind only the
  door/warp event at 996). Of the four templates, this is the one to bet on
  misbehaving. Two failure shapes: a **freeze on arrival** (the move route hangs, field
  never unlocks) or a **warp loop** (the guard flag never sets, the autorun refires
  while you are still on the warp tile). The second is not hypothetical — `WARP_FACING_HANDOFF.md`
  and commit `b7c5b8d7` document a boot-tested case of a down-stairs warp re-firing
  `TryArrowWarp` and bouncing the player back upstairs.

**A green CH05 gate is not evidence** that slice 2, the capability model, or the
mart/Center/PC templates are correct. CH05 exercises zero seam rows, zero populated
`requires[]`, zero mart/Center/PC instances, and its only `blocked:` rows are
terrain-derived Surf rather than switch/variable-derived — the least representative
possible confirmation. Their real validation is the retroactive re-derivation of
CH01-CH04, which is post-CH05 work (§Deferred).

---

## Step 9 — FIX

**Effort — you:** varies · **me:** high · **attended:** yes

Cluster any systematic defect and **fix the converter, then re-run.** Never hand-edit
generated output — it gets regenerated (`CLAUDE.md` §11).

The `/debug` workflow drives this: clarify the symptom → localize the layer → fix →
full verified rebuild with hash evidence → taildrop for retest.

---

## Step 10 — RECORD

**Effort — you:** 5 min · **me:** low · **attended:** no

- [ ] `MEMORY.md` → Current Phase and Decisions Made.
- [ ] `reference/chapters.json` → CH05 `status` to gated, with the gate note (date,
      suite result, ROM hash) in the established format.
- [ ] Retire this file to `reference/archive/`, migrating carryovers to `PROJECT_TODO.md`.
- [ ] Commit as one logical unit; merge `ch05`.

---

## Deferred — filed, not fixed

Recorded so they are not re-litigated mid-chapter.

- **#28 Cave encounters — RESOLVED 2026-09-02, no work owed.** Emerald has no cave
  encounter concept: `struct WildEncounterTypes` has five pools and none is a cave, and
  all 11 `gMapHeader.cave` / `MAP_TYPE_UNDERGROUND` sites are lighting, transitions,
  battle backdrop, DexNav cosmetics, Dusk Ball flavor and the region map — never table
  or rate selection. On the data side, 23 Uranium maps carry a `Cave` slot and **zero**
  of them also carry a populated `Land`-family table, so the fold into `land_mons` is
  lossless corpus-wide. The **time-of-day** half of #28 stays open and is out of CH05's
  scope: `OW_TIME_OF_DAY_ENCOUNTERS` is one flag away, but `_LAND_SOURCES` ranks plain
  `Land` above the time-split tables, so flipping it without auditing that precedence
  changes behavior on unwalked maps.
- **#57 — 12 unmodelled walked legs.** Deferred to **CH07 at the earliest** (operator
  decision, 2026-09-02).
- **#65 — CH01-CH03 manifests no longer load.** Immediately **after** CH05.
- **#62 parts 3-4 — corpus re-disposition.** Folded into #65, so also **after** CH05.
  This is a deliberate deviation: the recorded decision said "during CH05's build," and
  we are moving it out, because corpus-wide re-derivation mid-chapter is precisely the
  scope creep the loop guardrail exists to prevent. **The ordering safeguard moves with
  it and must not be lost:** *freeze the expected answers, derive, diff, then write* —
  never derive-and-write in one pass, or a regression in the derivation logic reads as
  a correct re-disposition.
- **#62 part 1 — DONE**, by D4 on 2026-09-01, two days after the item was filed. The
  `arrival_nudge` template and its classifier both exist. Its untested-in-ROM residue is
  live at step 8, not here.
- **#67 — route plans.** In scope; it *is* step 6.
- **`BUILD_PLAN.md:94`'s ART step has the same defect — fix AFTER CH05.** The
  canonical per-chapter loop (`BUILD_PLAN.md:86-122`) lists ART as a peer of
  SELECT/EVENTS/WIRE but gives it no owning command, exactly like this doc did before
  2026-09-04. CH05 inherited the problem rather than introducing it, so CH06 will
  rediscover it unless the shared doc is corrected. Deliberately **not** fixed
  mid-chapter (operator decision, 2026-09-04): editing the shared planning doc during
  a chapter is the scope creep the `BUILD_PLAN.md` §2 guardrail exists to prevent.
  Carry to `PROJECT_TODO.md` at step 10 with the fix already known — ART is discharged
  by step 4 (`phase5` → `build_slice_tilesets`) and step 7 (assembler →
  `sprite_pass`), and its number is kept only for cross-reference alignment.
- **Trainer battle staging is all-or-nothing — FILE, do not fix here.** Found
  2026-09-04. `trainer_converter.stage.stage_slice` catches `build_staged_battles`'
  `ValueError` and skips battle staging *wholesale* with a logged WARNING, then exits
  0. One unstageable trainer therefore discards every battle in the manifest,
  including chapters that staged fine before: CH05's Keichi took CH04's 17 battles
  down to 0, and the damage surfaced as a *CH01* failure (`TRAINER_THEO_9/10/11`
  undefined on Map050) because the transpiler walks `SLICE_MAP_IDS` in tuple order
  and aborts at the first failing map. A §4.5 violation — a partial failure silently
  discarding good work, while reporting success. The pic half legitimately stands
  alone; the battle half should stage per-trainer or abort. Out of CH05 scope
  (`BUILD_PLAN.md` §2 guardrail), belongs in `PROJECT_TODO.md`.
- **No automated equality check between the locations plan and the authored module.**
  Step 6a's `CH05.locations.json` and the `ch05.py` you author at 6b are two statements
  of the same coordinates, and nothing yet fails if they disagree — 6b's re-solve is a
  manual eyeball. This is the residual cost of splitting the artifact and it is the one
  real objection to the approach; it wants a `routing locations --check` that diffs the
  authored beats against the approved file. Out of CH05 scope (`BUILD_PLAN.md` §2),
  carry to `PROJECT_TODO.md` at step 10.

- **ROUTE (step 6) runs before object events exist, so its crossing check is vacuous —
  reorder the loop AFTER CH05.** Step 4's `phase5` regenerates the engine maps as the
  warps-only Map Walker corpus with no object events (`phase5.py:8-11`); trainer
  objects and their sight cones are only restored at step 7 by `build_object_events`
  and the assembler's copy into `engine/data/maps`. But `build_trigger_overlay` reads
  `engine/data/maps`, so a route solved at step 6 sees **zero** trainers and reports
  zero `CROSSING` lines regardless of the truth. CH05's first solve did exactly that;
  after staging objects, the same 155-tile order was found to enter trainer cones in
  five places. Affects every chapter, not just this one. Fix is a `BUILD_PLAN.md`
  ordering change (ROUTE after object staging); shared-doc surgery, so carry to
  `PROJECT_TODO.md` at step 10 rather than editing mid-chapter (§2 guardrail).
- **`destination_scripts` is never populated, and is global rather than per-destination.**
  `routing/__main__.py:296` calls `solve_route` without it and it defaults to empty
  (`solver.py:229`), so **a trainer's own sight cone is treated as a foreign hazard on
  the very segment whose destination is that trainer** — the solver contorts to avoid
  Manny on its way to Manny. Re-solving CH05 with real cone data went 155 -> 233 tiles
  and produced an incoherent order. It is also forwarded unchanged to every
  `plan_segment` (`solver.py:355`), so it structurally cannot express "crossing X's
  cone is fine when X is the destination." Filed, not fixed.
- **No warp-topology precedence.** `_derive_precedence` (`solver.py:159-209`) builds
  ordering edges only from self-switch reads/writes, so nothing prevents a far-side
  beat being ordered before the warp beat that reaches it — the cone-aware re-solve put
  B9 (on 2F) before B8 (the 1F->2F warp round trip that introduces 2F). Filed.
- **A vacuous trigger overlay should say so.** Zero `CROSSING` lines currently reads
  identically whether the route is clean or the overlay was empty. The project already
  has the right idiom for this — `route_model_unenforced` refuses to look like a pass —
  and the same discipline belongs here: if a chapter's dispositions carry trainer rows
  but the overlay yields no `TRAINER_SIGHT` tiles on those maps, fail loud (§4.5).
  Filed.

- **`ITEM_TM76` needs a sanity check — filed, not blocking.** The transpiler resolved
  B6's TM76 to `ITEM_TM76`, which passes the fork-index gate, but this expansion
  normally names TMs `ITEM_TM_<MOVE>`. `05-passage-cave.md:134` says TM76 is Stealth
  Rock; confirm the constant is actually that move and not a numbering coincidence.
  Cannot bite in CH05 — the item is in the Surf-sealed room — which is exactly why it
  would otherwise be found in Act 5.

---

## Log

Append findings, surprises and decisions here as they happen, newest last.

- **2026-09-02** — Prerequisite pass run before the branch. D1-D4 all confirmed built
  and tested. Found `CH05_DECISIONS.md` D1/D3 sections stale ("Built: … do not exist"
  about shipped code, never reconciled the way D2/D4 were) and corrected them. Found
  `PROJECT_TODO.md` #62 part 1 stale in the same way. #28's Cave half investigated and
  closed. Local-LLM pre-fill dropped from the plan.
- **2026-09-04** — Steps 1 and 2 done: maps 36/37 added to `SLICE_MAP_IDS`, transpiler
  clean on both (8/8 events each, logs `output/ch05-events-036.log` / `-037.log`).
  Step 3 had no command; traced the pipeline and found ART is not a standalone
  invocation — tilesets are produced inside step 4's `phase5`
  (`phase5.py:232` → `build_slice_tilesets`; budget guard `graphics/emit.py:537-548`),
  sprites inside step 7's assembler chain (`sprite_pass.run_sprite_pass`). Step 3
  rewritten to say so explicitly. **Open discrepancy:** step 7's command block is
  `phase5` + `make` only, but CH04 actually built via `transpile_driver` →
  `stage_slice_scripts --write` → `assemble_pathfinder` → `make modern`. **Reconciled
  same day** against `reference/guides/slice_expansion_runbook.md` steps 3-6 (the
  authoritative runbook); step 7 rewritten. `phase5` stays out of the build block —
  it is a prerequisite that mints `porymap/map_constants.json`, already satisfied by
  step 4.
- **2026-09-04** — **Step 2 was running the wrong tool.** `pipeline convert-map` is
  the retired Phase-4 orchestrator and falls through to a live Claude spawn; the
  deterministic transpiler is `conversion_agent.transpile_driver`. The first run
  spawned Claude on 9 of 16 events and **all 9 returned queued as
  `agent-flagged unhandled`** — zero conversions, ~$0.96, six of them `Stairs` events
  the transpiler handles natively. This also silently violated ground rule 2 (that
  rule meant ollama; the default backend routed to Claude). Step 2 corrected to
  `transpile_driver run --maps slice`. **The maps still need re-converting** —
  `output/uranium-build/scripts/Map036.pory` / `Map037.pory` currently hold the LLM
  output. Not re-run yet; awaiting your go-ahead.
- **2026-09-04** — Step 2 cleared, and the real blocker was **step 1, not step 2**.
  Step 1 documented only `SLICE_MAP_IDS`; three more pinned lists (trainer battles,
  trainer pics, species families) plus two class-mapping tables in `battles.py` were
  never mentioned. Each omission failed separately and looked unrelated to the last,
  costing a full loop. Step 1 rewritten to cover all four lists with the ordering
  rules and the manifest-count checks. Decisions made along the way: `SABLEYEITE`
  aliased to the existing vanilla `ITEM_SABLENITE` (operator call — same species, same
  mega evolution, already wired; only the display name differs);
  `TRAINER_CLASS_BLACK_BELT` mapped to `TRAINER_ENCOUNTER_MUSIC_INTENSE` (derived from
  two independent fork sources, not guessed); `GROZARD/TERLARD` and
  `BAASHAUN/BAASCHAF/BAARIETTE` staged as whole families. `tests/test_trainer_battles.py`
  `test_unmapped_music_class_fails_loud` repointed from BLACK BELT (now mapped) to
  HEX MANIAC — still a real fork class with no music row, so the assertion is
  unchanged in strength. Added `scripts/stage_species.py` and
  `scripts/stage_trainers.py`: the fast, `output/`-only half of the assembler's
  species and trainer passes, for iterating on pinned lists without the art passes.
  Final state: 32 species, 20 battles, 18 maps / 308 events, no traceback.
- **2026-09-04** — Command audit of this document, all 21 instructed commands checked
  against source. **One defect:** step 8's `playtest seeds --chapter CH04` was missing
  the required `--engine` flag (`playtest/__main__.py:183-185`) and could not have
  succeeded — ground rule 5 forbids satisfying it via `RPG2GBA_*`. Fixed. Everything
  else — `chapter_manifest generate/review/check`, `routing plan`, `playtest
  run/walk`, `phase5`, `transpile_driver run`, both `scripts/` invocations, `make -C
  engine modern` — verified correct including every flag. **No retired LLM-path
  command survives as a live instruction**; the four remaining mentions of
  `pipeline convert-map` are explanatory prose in callouts and this Log. Step 3
  reframed as an explicit no-command checkpoint keeping its number, with its two
  checks moved to checkboxes at steps 4 and 8 where they are actually discharged.
- **2026-09-04** — **STOP 1 + step 5 (READ) done: 25 rows dispositioned, checker
  0 errors.** Five findings, one operator convention, one cross-chapter repair.
  - **Boundary convention (operator ruling).** *A boundary crossing belongs to the
    chapter being opened, not the one shipping.* An outgoing chapter's contract is
    to deliver the player to the edge; the crossing is asserted by the chapter whose
    maps make it true. Rationale: an edge beat written against an unstaged neighbour
    is a test authored to decay, and it fails in the wrong chapter. **Carry to
    `PROJECT_TODO.md` at step 10** — `BUILD_PLAN.md` should state it, but editing the
    shared loop doc mid-chapter is the §2 scope creep guardrail (same disposition the
    ART defect got).
  - **CH04's B7 was silently invalidated by step 1 and is now repaired.** Adding 36/37
    to `SLICE_MAP_IDS` made `metadata_wiring.classify_event` stop returning
    `("skip", "out-of-slice warp")` for Map035 EV001, so `MAP_ROUTE_02` now emits warps
    at (20,33) — while B7 asserted *"the player steps onto it, no warp fires."* B7 is
    8th of CH04's 13 beats, so crossing there would have teleported the player into the
    cave for B9/B11/B12/B13/B15, all of which declare `map_constant=MAP_ROUTE_02`: one
    stale edge assertion, six broken beats, inside CH05's own predecessor replay.
    B7 now walks to (20,34) and stops. `_PRE_BAN_BUDGET["ch04.py"]` 25 -> 23.
  - **B11 does not convert, by design.** Map040 is not in `SLICE_MAP_IDS`, so the exit
    at Map037 (16,5) emitted no `warp_event` — `PassageCave2F` has exactly two warps,
    (16,27) and (16,26). Under the convention B11 asserts only that the player reaches
    the boundary; CH06 owns the crossing. **Step 7 constraint, and it is not obvious:**
    the beat must use `approach_to(..., prefer="east")` -> **(17,5)**. The default
    approach cell is (16,6) — and `Map040 ev019 (68,43)` warps back to `Map037 (16,6)`
    twice, so staging map 40 mints an arrival warp there. **Both (16,5) and (16,6) go
    live at once**; a BFS avoiding both still reaches (17,5) in 33 steps.
  - **The stairs ARE mandatory traversal — but the obvious experiment says otherwise.**
    Blocking the four stair *cells* changes reachability by exactly zero (282 -> 282)
    because you are never *on* a sideways staircase: an E/W press into one is displaced
    diagonally across it (`traversal/graph.py:221-225`), and the cells have no walkable
    N/S neighbour, so they read as "unreachable" in any cell-blocking BFS. The correct
    experiment removes `stair_diagonal` *edges*: reachability drops **282 -> 233** and
    the exit (16,5) becomes UNREACHABLE, while Nuñes and the Revive NPC keep stair-free
    paths — `05-passage-cave.md` §3 vindicated exactly as written. Anyone re-deriving
    this with `column_blocked` and a cell blocklist will "disprove" a true claim.
  - **CH04's deferred B8 is now unblocked and owed a decision — FILE, do not fix here.**
    Its `DEFERRED_BEATS` reason reads *"restore once CH05 stages Map036"*, which this
    chapter just did: Map035 EV001 compiles again, so the arrival nudge at (20,33) has a
    live subject. `chapter_manifest check --chapter CH04` reports it today as
    `unregistered_beat` (warning, because CH04 is not the live chapter). Open question
    it raises: the nudge is a CH04 *row* but fires on the CH05 crossing — under the new
    convention, whose beat is it? Not answered here.
- **2026-09-04 (later)** — Two more operator rulings, both narrowing the beat set.
  - **CH04's deferred B8 gets B7's treatment: it stays out of CH04, permanently.** Its
    `DEFERRED_BEATS` reason no longer reads "restore once CH05 stages Map036" — the
    autorun fires on the Route 2 side of the crossing and is observable only by coming
    back OUT of the cave, so CH05's entry beat owns it. **Encoding gap, filed not
    fixed:** `build_beat_model` loads a chapter's own module *plus predecessors*, never
    successors, so a CH05 beat cannot satisfy CH04's committed `beat:B8` disposition.
    CH04 therefore keeps reporting `unregistered_beat` as a **warning** (it is not the
    live chapter) — counted debt, already recorded in `MEMORY.md` as such. The real fix
    is letting `BeatModel` see a boundary row claimed by the arriving chapter; that is
    tooling work, so it goes to `PROJECT_TODO.md` at step 10 beside the convention.
  - **Warp round-trip idiom (operator).** *A warp is tested by crossing it, crossing
    back, and crossing again, so the beat ENDS on the far side* — stated for a chapter's
    entry warp and then generalized: "it probably makes sense to test any warp that
    way." Consequence: **one beat per warp PAIR, claiming both manifest rows**, the same
    shape as the staircases. Two ids collapsed — the 1F->2F and 2F->1F rows are now both
    `beat:B8`, and the cave entry/exit pair is both `beat:B1` (the doc's B1 becomes the
    round trip, not the one-way crossing). B11 is the single exception and that is the
    point: with map 40 unstaged there is nothing to come back from, so it cannot use the
    idiom, and CH06 writes the round trip when it stages Nowtoch.
  - **Net beat set: B1-B5, B8-B14, plus `blocked:surf` for B6/B7.** Only THREE ids are
    new beyond `05-passage-cave.md`'s list — B12 (arrival nudge), B13 (west staircase),
    B14 (east staircase) — down from the 13 the first pass minted. Renumbered
    contiguously while nothing is registered; note that B14 briefly meant the 2F->1F
    warp during this session and now means the east staircase.
- **2026-09-04 (later still)** — **Step 6 was circular, and the circle is now cut in
  code.** `routing plan` imports the playtest chapter module (`__main__.py:249-252`) and
  reads every routing coordinate from the beats registered there
  (`solver.py:84-110`, `beat.locations[0]`); the manifest carries no coordinates at all
  (`generator.py:552` computes an event cell and discards it). So the old step 6 could
  not run before `ch05.py` existed, which is why `routing` shipped as a grader
  (`513b0f00`) and why no chapter has ever had a route plan — `reference/routes/` did
  not exist in the tree or in history. Built `src/rpg2gba/routing/locations.py` plus a
  `routing locations` subcommand and a `plan --locations` path: derive one routing
  point per `beat:` disposition from manifest + dispositions + map JSON, materialize
  the file as an in-memory `Chapter`, and hand *that* to `solve_route` — so `solver.py`
  is unchanged. CH05 solves from derived locations: 12 beats, 14 nodes, **155 tiles, no
  `CROSSING` lines**. Findings along the way, all of which would otherwise have surfaced
  during authoring:
  - **B11's cell was wrong in this log and is corrected.** The earlier entry claimed
    `approach_to` defaults to (16,6), that staging map 40 makes "both (16,5) and (16,6)
    go live at once", and that B11 therefore needs `prefer="east"` → (17,5). That
    conflated a warp *destination* with a warp *source*. Map037's only code-201 events
    are EV001 (16,27) and EV002 **(16,5)**; (16,6) carries no warp event, it is merely
    where Map040's return warp deposits the player, and a destination arms nothing.
    When CH06 stages map 40, **(16,5) goes live and (16,6) does not.** B11 is a
    `player_touch` warp, so its cell is the trigger tile (16,5) and no `prefer=` is
    needed. Operator call, 2026-09-04.
  - **A terrain/stairs row can never be a routing point.** Its recorded cell is the
    stair itself, and no edge in the traversal graph ever *targets* a stair cell — an
    E/W press is redirected diagonally across it. BFS from anywhere in Map037's
    walkable region reaches 282 cells and **none of the four stair cells is among
    them**, even though `is_walkable` returns True for each. The first solve dead-ended
    with "no route from group 'B10' to any of ['B13', 'B14']". `_stair_approach` now
    resolves a stair row to the E/W neighbour owning the `stair_diagonal` edge (B13 →
    (10,9), B14 → (19,9)). This is the same trap the earlier stairs entry describes from
    the other direction: a cell-blocking experiment reads stair cells as unreachable,
    and so does the router.
  - **`_validate_row_id` rejected terrain row ids** (`playtest/chapter.py`), so no beat
    could claim the stair rows it exercises — CH05's B13/B14 are the first to need it.
    Fixed by adding the `terrain_row_id` shape; page and seam shapes unchanged. This
    would have blocked step 6b authoring regardless of the routing work.
  - `tests/test_routing_locations.py`, 16 pass. Full suite: 2898 pass, 9 fail, and all
    9 fail identically on the pre-change tree (verified by stash) — pre-existing and
    unrelated.
- **2026-09-04 (viewer)** — The planned-route overlay promised by
  `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md:1105-1112` was built and had simply never had
  data: no chapter has ever committed a `.route.json` (`PROJECT_TODO.md` #67), and
  step 6a had only ever been run with `--dry-run`, which writes nothing. Wrote
  `CH05.route.json` and the overlay lit up first try on the already-running server.
  Two gaps closed while confirming it:
  - **The declared layer was empty pre-authoring**, by construction — it reads
    `beat.locations` via `load_chapter`, and `ch05.py` does not exist. `beat_markers`
    now falls back to `reference/routes/<chapter>.locations.json` for chapters with no
    module, tagged `derived: True`, drawn hollow/dashed and labelled with the solved
    route position. It never applies to a chapter whose module loaded, so a derived
    cell cannot mask an authored one.
  - **Beat markers were labelled `'B' + array_index`** (`viewer.js:577`), which is
    neither the beat id nor the visit order — a beat named B1 sitting first in the
    array rendered as "B0". Now labelled with the beat's own name plus `#position`.
    Observed markers had the same `'N' + i` defect and now use the beat name.
  Note V2 promised the *visualization*, not a visual approval gate: `BUILD_PLAN.md`
  step 6 says "read the summary," a CLI text output. Making STOP 3 visual is a
  genuine improvement on the written loop and is carried to `PROJECT_TODO.md`.
- **2026-09-04 (sight cones)** — Operator asked what happens if a trainer spots the
  player before the walk reaches the cell where the battle was supposed to start. Two
  separate answers, and the first one was a real hole.
  - **Step 6's crossing check was measuring nothing.** See §Deferred: object events do
    not exist at step 6. Ran step 7's first two commands (`stage_slice_scripts --write`,
    `assemble_pathfinder`, both exit 0) to populate them, then re-checked. Real cones:
    Manny (18,29) sight **5** `FACE_RIGHT` (single facing + stationary -> CERTAIN),
    Keichi (6,13) sight 3 `LOOK_AROUND`, Nuñes m37 (24,10) sight 3 `LOOK_AROUND`. The
    approved 155-tile order enters a cone on five legs: B2->B3 at (20,29) CERTAIN,
    B3->B5, B5->B4, B14->B9, B9->exit. **All five are benign** — each is either into
    the cone of the trainer that leg is walking to (B3 *is* Manny, B5 *is* Keichi, B9
    *is* Nuñes) or past a trainer already defeated. No leg walks an *undefeated*
    trainer's cone en route to a non-trainer beat, which is the shape that would
    actually fire the wrong event. The order stands.
  - **Runtime tolerance is already built, and is not a routing concern.** The question
    "does the harness recognise the battle as the beat it was heading to, finish it in
    place, and re-path around the trainer's new position" is answered yes on all three
    counts: `_walk_greedy` polls `_in_battle()` even when the field is unlocked
    (`emulator.py:2422-2437`, from the 2026-08-11 no-lock wild-battle regression) and
    raises `WalkInterrupted`; `_trigger_trainer` asserts the live opponent trainer id,
    not merely that a battle happened; and `_plan_route` blocks every active object
    event's **live** tile via `_occupied_object_tiles` (`emulator.py:1613-1647`) on
    every re-plan, so a trainer standing on the planned path is routed around. The
    static `MapGraph` has no object-event awareness at all — occupancy is layered on at
    plan time, deliberately. `_press_a_live` (`ch04.py:576-616`) exists for the
    aftermath (Larrie's template (18,36) vs measured (18,39) post-battle).
    `divergence.py` records the resulting off-plan tiles as non-blocking contradictions
    and fails only on a genuinely foreign trigger. **Step-6b consequence:** the absorb
    policy is per-walk and not automatic (`resolve_interruptions` defaults False), so
    CH05's trainer beats must use CH04's `_walk_absorbing(absorb_wild=True,
    absorb_trainer=False)` + assert-which-trainer pattern.
  - **Two step-7 blockers found and fixed:** `reference/npc_gfx_map.json` had no entry
    for `HGSS_048` (Keichi) or `PU-MegaStone` (the Sableyeite ball), and
    `build_object_events` fails loud on a missing sheet. Added `HGSS_048` ->
    `OBJ_EVENT_GFX_URANIUM_HGSS_048` / fallback `OBJ_EVENT_GFX_BLACK_BELT`
    (`event_objects.h:70`; the sheet is a white-gi red-headband martial artist, which
    agrees with the `TRAINER_CLASS_BLACK_BELT` mapping pinned in step 1), and
    `PU-MegaStone` -> `OBJ_EVENT_GFX_POKE_BALL` (a sparkle overlay, not a character;
    the item ball converts to the fork's native item ball, the same call `PU-POKEBALL`
    already records).
