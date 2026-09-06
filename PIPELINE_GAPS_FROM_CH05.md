# Pipeline gaps CH05 worked around by hand

**Written 2026-09-06, after CH05's gate pass and merge (`af0d8e25`).**

**The question:** during CH05 we hand-edited tables, hand-appended pinned lists, and
hand-wrote beats that the pipeline should have produced. Which of those are **gaps to fix
before running anything more**, as opposed to genuine content calls that will always need
a human?

`BUILD_PLAN.md` §2's guardrail is the standard: *the next chapter should need **data**
changes, not **code** changes.* Measured against it, CH05 needed code changes in six
places, and four of them were mechanical work a human did because nothing does it.

> Companion doc: `PRE_REDERIVATION_AUDIT.md` answers a different question — what's
> cheaper to fix before the #65 re-derivation. This one is about hand-work that recurs
> every chapter. **Where they overlap (#83), this document is the stronger reason.**

---

## Why this is urgent rather than tidy: CH06 is an order of magnitude bigger

Counted from the decoded map JSON (`output/uranium-build/maps/Map0NN.json`):

| | CH05 (maps 36, 37) | CH06 (maps 40-47) | ratio |
|---|---|---|---|
| maps | 2 | **8** | 4× |
| events | 16 | **206** | 13× |
| `code 201` (warp) commands | 4 | **41** | 10× |

Every hand-step below scales with one of those rows. The four warp cells someone
hand-derived for CH05 become roughly forty for CH06 — and CH06 is a Gym city with a
Poké Center, a Mart, and the first metro station, i.e. the first chapter to exercise the
mart/Center/PC templates at all.

*(A trainer count is deliberately omitted: a crude scan of the event scripts finds ~6 for
CH06 against CH05's 3, but the heuristic is unreliable and almost certainly undercounts a
Gym. Treat the warp and event columns as the load-bearing numbers.)*

---

## Tier 1 — mechanical work a human did because nothing does it. Fix these.

### G1. The three pinned lists have no completeness check, and omission is silent

**This is the biggest one, and it is not filed anywhere.**

Four lists must move together when a chapter is added. Exactly one of them is guarded:

| List | Location | Validated? |
|---|---|---|
| `SLICE_MAP_IDS` | `tileset_converter/map_set.py:26` | **Yes** — `test_chapter_atlas.py:253` asserts it equals the `built`+`in_progress` set in `chapters.json` |
| `SLICE_TRAINER_BATTLES` | `trainer_converter/common.py:148` | **No** |
| `SLICE_TRAINER_PICS` | `trainer_converter/common.py:89` | **No** |
| `STARTER_SPECIES` | `species_converter/common.py:124` | **No** |

The existing tests (`test_trainer_battles.py`, `test_species_gate.py`) check that entries
which *are* present are valid, and fail loud on bad ones. Nothing checks that the lists
are **complete** for the current `SLICE_MAP_IDS`. An omission is not caught at all — it
surfaces later as a transpile abort.

CH05's own §Log records what that costs:

> "Step 1 documented only `SLICE_MAP_IDS`; three more pinned lists … were never
> mentioned. **Each omission failed separately and looked unrelated to the last, costing
> a full loop.**"

Every entry is derivable: the trainers on a chapter's maps are in the map events, their
pics from `trainertypes.dat`, their species from the parties plus the evolution chains
(`STARTER_SPECIES` stages whole families only because `build_staged_species` fails loud
on a dangling evolution target — which is itself derivable).

**Fix:** derive the expected sets from `SLICE_MAP_IDS` and fail loud listing *everything*
missing at once. The one-at-a-time discovery is the whole cost; the lists themselves are
fine as pinned append-only data.

### G2. `WARP_OVERRIDES` — filed as #25 since 2026-08-04, and CH05 showed the failure mode

Hand-adding four cells to `scripts/assemble_pathfinder.py` was the difference between a
working chapter and a completely inert one. Before it (`08baf280`): the player **could
not enter the Passage Cave, leave it, or use the 1F↔2F stairs.** Every warp event
compiled; none fired, because an unstamped warp tile is plain floor.

The derivation is not unknown — the commit message *states the algorithm* and then
executes it by hand: the maps' own `code 201` events, `trigger=1`, blank graphic,
**excluding** the arrival warps `_resolve_all_warp_events` mints on every destination
(which are plain floor by design and must stay that way).

#25 already says the fix — "derive `WARP_OVERRIDES` from `build_slice_maps`'s computed
set instead of hand-listing it" — and notes the two sources "happen to agree today … but
nothing enforces it." CH05 is the third chapter to open this gate by hand; the commit
says so outright: *"This is the same gate CH02 and CH03 each had to open for their own
frontier."*

**CH06 has 41 `code 201` commands against CH05's 4.** Doing this by hand a fourth time,
at ten times the volume, across a Gym, a Center, a Mart and a metro station, is the single
most likely way CH06 boots inert.

### G3. #83 — trainer staging is all-or-nothing, which is what makes G1 catastrophic

`trainer_converter/stage.py:619-625` catches the failure, logs a WARNING, leaves
`staged_battles` empty, and **exits 0**. One unstageable trainer discards every battle in
the manifest.

This is listed in `PRE_REDERIVATION_AUDIT.md` too, but its real significance is here: it
is the amplifier that turns a G1 omission into a cross-chapter mystery. CH05's Keichi took
**CH04's 17 already-good battles down to 0**, and the damage surfaced as a **CH01**
failure (`TRAINER_THEO_9/10/11` undefined on Map050), because the transpiler walks
`SLICE_MAP_IDS` in tuple order and aborts at the first failing map.

So the observed symptom of "you forgot to pin a CH06 trainer" is "CH01 is broken." Fix G1
and this is rarer; fix G3 and it is legible when it happens. Both are cheap. Do both.

### G4. #79 — no stair resolver, so stairs are hand-typed coordinates

`playtest/cells.py` has resolvers for events, approaches, warps, arrivals and entries —
and nothing for a staircase. CH05's B13 and B14 are the chapter's **only** two `raw_cell`
escape hatches (`chapters/ch05.py:548`, `:586`) purely because of this, in the first
chapter born under the zero-literal ban.

The logic is already written: `routing/locations.py`'s `_stair_approach` resolves a stair
row to the E/W neighbour owning the `stair_diagonal` edge. This is a port from one module
to another, not a discovery.

---

## Tier 2 — judgment stays human; the *loop* around it should improve

These are not gaps in the sense above. A human should keep making the call. What should
change is that the pipeline surfaces the whole list at once instead of one item per
build.

- **`_CLASS_ENCOUNTER_MUSIC` / `_CLASS_PIC_INTERNAL_NAME`** (`trainer_converter/battles.py:75`, `:103`).
  CH05 added one class, and justifying it took two independent fork sources
  (`constants/trainers.h:562`'s own comment naming Black Belts, plus vanilla's own Black
  Belts at `src/data/trainers.h:1329`). That care is correct and should not be automated.
  But CH06 is a **Gym** — gym leader plus gym trainers, several new classes at once.
  `test_multiple_failures_all_reported_not_just_first` already exists for the battle
  builder; the class-mapping gate should behave the same way.
- **`reference/npc_gfx_map.json`.** Choosing which fork sprite resembles a Uranium NPC is
  judgment. It already fails loud on a missing sheet (`build_object_events`), which is the
  right behaviour. No change needed beyond G1-style batching.
- **`reference/warp_facing_overrides.json`.** CH05 hand-added two entries. The file's own
  comment says to use it *only* where tier 3 is genuinely ambiguous. **#107** already
  records a measured second-order reachability check that resolves both CH05 cases
  uniquely and neither map33 case — so part of this is closable, and #107 is where it
  lives.
- **`_CHAPTER_MAP_START_CELLS`** (`generator.py:242`). Three hand entries for CH05. The
  cell must be *verified*, so a human stays in the loop — but see
  `PRE_REDERIVATION_AUDIT.md` A1: the generator currently **warns** rather than failing
  when one is missing, which is the actual defect. Fail loud instead.

---

## Tier 3 — correctly hand-authored; leave alone

- **`SABLEYEITE` → `ITEM_SABLENITE`** (`reference/uranium_id_map.json`). A content-fidelity
  call: same species, same mega evolution, already wired, only the display name differs.
  This is exactly what a hand-maintained id map is *for*.
- **B11 hand-written rather than templated.** `map037/ev002` never compiles to a warp
  (Map040 out of slice), so `warp_beat` would wait forever. Correct as authored; the
  boundary convention (#72) is the general answer.

---

## Two workarounds that quietly became infrastructure

Worth a decision rather than drift:

- **`scripts/stage_species.py` and `scripts/stage_trainers.py`** were written during CH05
  as the fast, `output/`-only half of the assembler's species and trainer passes, "for
  iterating on pinned lists without the art passes." They are now the practical way to
  work G1 — but they are not in `reference/guides/slice_expansion_runbook.md`, so CH06
  starts by not knowing they exist. Either document them in the runbook or fold them in.
- **`_walk_unplanned_for_replay`** (`emulator.py:3035`) is scaffolding that expires when
  CH01-CH04 are re-derived, and it fired **zero** times in CH05's green run. Tracked in
  `PRE_REDERIVATION_AUDIT.md` §5; noted here so it is not mistaken for load-bearing code.

---

## Recommendation

**G1, G2 and G3 before CH06 — not before the re-derivation, before *anything* that
stages maps.** All three are small, all three are mechanical, and all three have already
cost a full debugging loop each at CH05's scale. G2 in particular is the one that decides
whether CH06's first ROM has working doors, and CH06 has ten times the warps.

G4 before whichever comes first of CH06 or re-authoring CH02's beats (Map033 carries
sideways staircases).

Tier 2's batching is worth doing alongside G1, since it is the same "tell me everything
that's missing in one run" change applied to a second table.
