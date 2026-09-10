# CH01 manifest re-derivation and coverage analysis (REDERIVATION_PLAN P8, CH01 half)

**Scope.** This covers CH01 only: run the generator, diff against the P7 freeze
(`reference/frozen/rederivation/CH01.freeze.json`), classify the diff per
`REDERIVATION_PLAN.md` §1, then build a row-by-row coverage candidate list against
CH01's 17 beats. This is analysis, not disposition-authoring — no
`CH01.dispositions.json` was written or should be inferred from this doc.

## Summary

- **Manifest diff: 1 field changed on 1 row, 0 rows added/removed, 0 content-hash
  changes.** Category **1** (derivation is better) — see below. **No category-3
  finding.**
- **Bucket counts** (211 rows total):

| Bucket | Count |
|---|---|
| `gated_post_ch01` | 56 |
| `gated_same_visit` | 40 |
| `covered` | 16 |
| `wants_a_beat` | 31 (25 ordinary + 6 forward-boundary rows, see note) |
| `inert` | 68 |

- Suite: **3195 passed, 17 skipped, 1 failed** (was 3196/17/0 at P7). The one new
  failure is a real finding about the freeze's test design, not a regression in the
  derivation — see §8. `test_frozen_manifest_rows_match_blob`, the test whose own
  docstring calls itself "the test that matters" and claims to "stay meaningful
  after P8 regenerates the working manifest," does in fact still pass.

## 1. Manifest diff vs. the P7 freeze

Ran `.venv/bin/python -m rpg2gba.chapter_manifest generate --chapter CH01`:
`wrote reference/manifests/CH01.manifest.json: 211 rows, 19 undispositionable, 32 need citation`.

Row-id sets are identical (0 added, 0 removed). All 211 rows compared field-by-field
against `manifest_rows` in the freeze (ignoring `terrain`/`reachability_consulted`,
which the freeze predates per the README). Exactly **one** field on **one** row
differs, and it is not a content-hash change:

```
map032/seam/E/map059
    unhandled: 0 -> None
```

**Classification: category 1 (derivation is better), not a regression.** The row is
a `kind="seam"` row (a map-connection edge, not an event page); `_generate_seam_rows`
(`chapter_manifest/generator.py:701-739`) never passes `unhandled=` when building a
`ManifestRow` for a seam, so the field now takes its dataclass default, `None`.
`schema.py`'s own docstring for `ManifestRow.unhandled` (lines ~279-295) says `None`
means "never measured" and must not be read as "measured, zero found" — which is
exactly what the frozen `0` implied for a row that has no event page and thus nothing
`transpile_unhandled.jsonl` could ever join against. The freeze's `0` was the
misleading answer; `None` is the schema-correct one for a seam row. This is not
scored a "regression" because nothing about seam-row semantics changed between the
freeze and now — the freeze was simply frozen holding a value the schema doesn't
actually claim.

No other row of the 211 differs in any field, including `content_hash`. Per the
freeze README's point 2, that agreement only proves the derivation didn't drift,
not that any row's *content* is correct — but it does mean this diff step surfaced
nothing to litigate beyond the one field above.

## 2. Coverage analysis — method and confidence

CH01's 17 beats carry no `rows=` (confirmed, per the freeze README and
`test_no_chapter_before_ch05_claims_manifest_rows_from_a_beat`), so the beat↔row
join here is **entirely reconstructed by hand**, from four kinds of evidence, in
descending order of confidence:

1. **Coordinate/constant match** — a beat's `at=` coordinate or a helper's named
   constant (`LAB_DOOR_MOKI_TOWN`, `CEREMONY_APPROACH`, etc.) traced to the exact
   `warp(...)` target or event tile in the converted `.pory` script
   (`output/uranium-build/scripts/Map0*.pory`), confirmed by reading the actual
   script bodies, not just the manifest's summary fields.
2. **Flag/switch-name match** — a beat's `emu.flag("FLAG_X")` assertion traced to a
   `setflag(FLAG_X)` call inside one specific event page's script.
3. **Self-switch inheritance** — where a page's *own* condition is only `self=A`
   (etc.), I traced which sibling page in the same event actually writes that
   self-switch, and inherited that writer's gate. This mattered for six rows where
   the writer requires a post-CH01 switch or the Rock Smash capability — a page
   that looks "same-visit gated" by its own condition alone is not reachable if the
   only page that ever sets its self-switch is itself unreachable in CH01.
4. **Narrative plausibility** — for a handful of rows (noted below) I could not find
   direct script evidence either way and said so rather than asserting a match.

**Where this join is weakest:** (a) `FLAG_GOT_POKEMON` and `VAR_BAMBO_REWARD` are
read in condition checks but their *setters* do not appear anywhere in the
currently-transpiled `.pory` output at all (not even in `CommonEvents.pory`) —
likely because the setting logic lives in a common event RPG Maker Essentials
pattern that hasn't been harvested yet (`#87`, filed as a CH06 prerequisite, out of
this task's scope). I inferred "Got Pokemon" is same-visit reachable (set alongside
the starter grant) from its name and from B8/B9 giving a starter in this same
chapter, but this is a plausibility call, not a script citation. (b)
`map049/ev019/p1`'s `self=A` condition has no confirmed writer anywhere in
`Map049.pory` — `p0` (gated `FINAL EVENT`) has no `self_switch_write` effect either,
so it's unclear what ever sets this self-switch. I bucketed it `gated_same_visit`
per the "self-switch" family default, but flag the join as unconfirmed.

## 3. `gated_post_ch01` (56 rows)

Dominant gates, all definitionally unreachable within CH01 (Moki Town, before any
gym):

- **switch `FINAL EVENT`** (33 base rows, per the scoping facts) plus **6 more**
  found by self-switch inheritance (see §2.3): `map032/ev080/p1`, `map049/ev018/p1`,
  `map050/ev022/p1`, `map172/ev004/p3` inherit `FINAL EVENT` from the sibling page
  that writes the self-switch they read.
- **var `Quest Log >= 5`** — CH01's own story only ever drives this var to 4 (B13).
  Any row conditioned on `>= 5` is post-CH01 regardless of the base fact's grouping
  of "1/2/4/5" together; 1/2/4 are all same-visit (see §4).
- **switch `Gym 1 defeated` / `Gym 2 trainers off`** (5 base + 2 more via
  inheritance: `map032/ev078/p1`, `map050/ev027/p1`).
- **capability `rock_smash`** (6 rows: `map032/ev014/p0`+`p1`, `ev015/p0`+`p1`,
  `ev033/p0`+`p1`) — three Rock-Smash boulders on Map032, each `requires:
  ["rock_smash"]` in the row itself. Moki Town is the starting town; Rock Smash is
  not a capability CH01 can have. This is a capability gate, not a switch/var gate,
  but it has the same practical effect and belongs in this bucket.
- **switch `Starting Over`** (2 rows: `map048/ev013/p0`, `map049/ev022/p0`, both
  `HEAL` autorun pages) — only `clearflag(FLAG_STARTING_OVER)` appears anywhere in
  the converted scripts, never a `setflag`; whatever sets it (a post-game/NG+ reset
  path) is out of CH01's reach either way.
- **var `BAMBO REWARD >= 10`** (`map050/ev005/p7`) — no setter for
  `VAR_BAMBO_REWARD` appears in the converted scripts either (only one read, in
  `CommonEvents.pory:113`); its name implies a repeatable post-game reward tracker,
  not anything CH01's 17-beat single visit touches.
- **seam `map032/seam/E/map059`** — the lone `connections.json` entry for Map032
  goes to Map059, which is **Route 03** (`map_infos.json`), a map nowhere near the
  built CH01–CH04 corpus. Bucketed here as "not reachable in the current corpus,"
  the seam-side equivalent of a post-CH01 gate.

## 4. `gated_same_visit` (40 rows)

- **`var Quest Log >= 1 / 2 / 4`** (25 rows) — CH01's own beats drive this var
  0→1 (B9) →2 (B12) →4 (B13), so every row gated on these thresholds is reachable
  within the same playthrough, just not from the chapter's start.
- **switch `NIGHT? People`** (9 rows, all `Luz` NPC pages on Map032) — a
  time-of-day toggle, not a story flag; matches the bucket's own "time-of-day
  variant" example exactly.
- **self-switches (`self=A`/`C`) not tied to a post-CH01 writer** (6 rows) — repeat-
  interact variants of Auntie (`map049/ev001/p1`), the fence-trip Trainer(5)
  (`ev074/p1`), the ceremony NPC "Theo75" (`ev075/p1`), Bambo's aptitude offer
  (`map050/ev005/p1`, self=C), the give-item NPC's repeat line (`ev027/p1`), and the
  post-Bambo-after-gym... (excluded, that one's post-ch01) — all confirmed
  reachable because their writer page is itself ungated or Quest-Log-gated within
  CH01.

## 5. `covered` (16 rows)

| row_id | beat | evidence |
|---|---|---|
| `map049/ev002/p0` | B2 | unconditioned page = the blocked-exit redirect `_assert_house1f_exit_blocked` exercises |
| `map049/ev001/p0` | B3 | `setflag(FLAG_MUM)` (`Map049.pory:25`), matches Auntie's page-0 script |
| `map032/ev074/p0` | B4 | fence-trip cameo, self-switch write B4 asserts |
| `map049/ev002/p1` | B4 (`_leave_house1f`) | `Mum`-gated warp page, the actual house exit |
| `map032/ev003/p0` | B5 | `warp(MAP_URANIUM_50, 14, 18)` traced to `Map032_EV003_Page1` — the lab door |
| `map032/ev003/p1` | B5 | its `tsOff?("A")` fade partner |
| `map050/ev005/p0` | B5/B6/N3/B7 | Bambo's whole intro→quiz branch tree lives in this one page's script (no field-lock release between offer/decline/re-offer/quiz) |
| `map050/ev005/p2` | B7 | self=D re-offer page — `self=D` matches `FLAG_MAP050_EVENT005_SSD`, which N3's own code names as the flag it asserts after declining; B7 walks up and answers Yes, which is this page |
| `map050/ev019/p0` | B8/B9 | `givemon`+`trainerbattle` in one script, matches B8/B9's own citations |
| `map050/ev001/p1` | B10 | `Quest Log >= 1` exit-door page, matches `LAB_EXIT_APPROACH`/`_cross_threshold` |
| `map032/ev009/p1` | N2 | `Quest Log >= 1` page on the ceremony-trigger event, matches N2's precondition and redirect assertion |
| `map032/ev017/p0` | B11 | `warp(MAP_URANIUM_172, 10, 10)` traced to `Map032_EV017_Page1` — Theo's house door |
| `map032/ev017/p1` | B11 | its fade partner |
| `map172/ev004/p0` | B12 | `Quest Log >= 1` autorun, PokePod scene B12 exercises |
| `map032/ev009/p2` | B13 | `Quest Log >= 2` page on the ceremony event, writes to 4 — matches B13 |
| `map172/ev002/p0` | B13 (`_leave_theo_house`) | `warp(MAP_URANIUM_32, 56, 42)` — the reverse of B11's door, exercised when B13 walks the player back out |

## 6. `wants_a_beat` (31 rows) — the list to review

25 ordinary rows plus 6 forward-boundary rows (flagged separately, see note below
the table). All are ungated or same-visit-gated, write state or are a real
mechanical connection, and no existing beat plausibly reaches them.

| row_id | map | event | page | trigger | effects | condition (plain) | what it does |
|---|---|---|---|---|---|---|---|
| `map032/ev005/p0` | Map032 (Moki Town) | EV005 | p0 | player_touch | warp | none | door into Player's House 1F (map49) from town — the reverse of B4's exit; no beat ever re-enters from outside |
| `map032/ev005/p1` | Map032 | EV005 | p1 | autorun | temp_switch_write | `s:tsOff?("A")` runtime | door's arrival-fade partner for the above |
| `map032/ev006/p0` | Map032 | EV006 | p0 | player_touch | warp | none | door into Map064 ("Moki Town House 2"), a flavor house never entered by any beat |
| `map032/ev006/p1` | Map032 | EV006 | p1 | autorun | temp_switch_write | `s:tsOff?("A")` | fade partner for the above |
| `map032/ev007/p0` | Map032 | EV007 | p0 | player_touch | warp | none | door into Map065 ("Moki Town House 1"), same situation as Map064 |
| `map032/ev007/p1` | Map032 | EV007 | p1 | autorun | temp_switch_write | `s:tsOff?("A")` | fade partner |
| `map032/ev027/p0` | Map032 | EV027 | p0 | action | giveitem, self_switch_write | none | an NPC gives an item on first interact; no beat ever talks to this NPC |
| `map048/ev001/p0` | Map048 (Player's House 2F) | EV001 | p0 | autorun | self_switch_write | none | first-entry autorun scene on 2F; no beat ever visits 2F at all |
| `map048/ev002/p0` | Map048 | EV002 | p0 | player_touch | warp | none | stairs down to Map049 (1F) |
| `map048/ev004/p0` | Map048 | EV004 | p0 | action | pc | none | a PC on 2F |
| `map048/ev005/p0` | Map048 | EV005 | p0 | parallel | self_switch_write, switch_write | none | a parallel process that sets two persistent global switches (`FLAG_GAME_RUNNING`, `FLAG_JUKEBOX`) plus its own once-only flag — since no beat visits Map048, these never get set during any CH01 boot-walk today |
| `map049/ev001/p2` | Map049 (Player's House 1F) | Auntie | p2 | action | switch_write | `Quest Log >= 1`, self=A | Auntie's post-starter re-talk line, writes a switch; no beat re-talks to her after B9 |
| `map049/ev001/p3` | Map049 | Auntie | p3 | action | heal, switch_write, var_write | `Quest Log >= 2`, self=A | Auntie's post-Theo-visit re-talk line — heals the party and writes a switch + var; no beat re-talks to her after B12/B13 |
| `map049/ev003/p0` | Map049 | EV003 | p0 | player_touch | warp | none | stairs up to Map048 (2F) — the reverse of `map048/ev002` |
| `map050/ev009/p1` | Map050 (Professor Lab) | EV009 | p1 | action | heal | switch `Got Pokemon` | a heal-desk NPC once you have a Pokémon; no beat visits this NPC after B9 |
| `map050/ev021/p1` | Map050 | EV021 | p1 | action | heal | switch `Got Pokemon` | a second heal-desk NPC, same situation |
| `map050/ev026/p0` | Map050 | EV026 | p0 | action | pc | none | a PC in the lab |
| `map064/ev001/p0` | Map064 (House 2) | EV001 | p0 | action | self_switch_write | none | NPC first-talk once-off flag; house never visited |
| `map064/ev002/p0` | Map064 | EV002 | p0 | action | self_switch_write | none | same |
| `map064/ev003/p0` | Map064 | EV003 | p0 | player_touch | warp | none | exit door back to Map032 |
| `map065/ev001/p0` | Map065 (House 1) | EV001 | p0 | action | self_switch_write | none | NPC first-talk once-off flag; house never visited |
| `map065/ev002/p0` | Map065 | EV002 | p0 | action | self_switch_write | none | same |
| `map065/ev003/p0` | Map065 | EV003 | p0 | player_touch | warp | none | exit door back to Map032 |
| `map089/ev002/p0` | Map089 (Theo's House 2F) | EV002 | p0 | player_touch | warp | none | stairs down to Map172 — the *only* way in or out of 2F; Theo's upstairs room is never visited by any beat |
| `map172/ev003/p0` | Map172 (Theo's House 1F) | EV003 | p0 | player_touch | warp | none | stairs up to Map089 — the reverse of the row above |

**Forward-boundary rows (6, listed but not ordinary gaps):** `map032/ev023/p0`+`p1`,
`ev036/p0`+`p1`, `ev037/p0`+`p1` — all warp to Map033 (Route 01) at (70,11); this is
the exact set `rpg2gba slice-growth` (REDERIVATION_PLAN P2) already found and
attributed to CH01's forward boundary. **Per P3's boundary-ownership rule, a
forward crossing belongs to the chapter being *opened* (CH02), not the one
shipping.** They satisfy `wants_a_beat`'s literal definition (ungated, writes state,
no CH01 beat covers them), which is why they're listed here rather than silently
dropped, but the fix is a `boundary` verdict on CH02's side plus a CH02 beat, **not**
a new CH01 beat. Worth noting separately: CH01's own `b15()` docstring still says
"MokiTown's connections are unset ... no built westward destination to walk to yet"
— that was true when B15 was written and is no longer true now that Map033 is
staged. That's a stale comment in `ch01.py`, not a manifest problem; flagging it
here since P8 is where it surfaces, but not fixing it (out of this task's write
scope).

## 7. What I could not determine

- **`FLAG_GOT_POKEMON` / `VAR_BAMBO_REWARD` setters are invisible to this pass.**
  Neither appears as a `setflag`/`setvar` anywhere in the currently-transpiled
  `.pory` output, including `CommonEvents.pory`. I inferred "Got Pokemon" is
  same-visit reachable from its name and from B8/B9's starter grant, but this is
  plausibility, not citation — flag it before trusting the `wants_a_beat` entries
  that depend on it (`map050/ev009/p1`, `ev021/p1`).
- **`map049/ev019/p1`'s `self=A` condition has no confirmed writer.** Neither `p0`
  (the only other page, gated `FINAL EVENT`) nor anything else in `Map049.pory`
  sets this self-switch as far as I can find. Bucketed `gated_same_visit` by the
  bucket's own self-switch default, but the join is unconfirmed either way.
- **Two "inert-by-heuristic" rows are borderline.** `map032/ev009/p0` (the
  ceremony-trigger event's page before `Quest Log >= 1`) and `map050/ev001/p0`
  (the lab-exit door's page before `Quest Log >= 1`) are both unconditioned
  redirect-shaped pages with `text`/`move_route` effects but no state write — by my
  "no state effect = inert" rule they land in `inert`, but both are structurally
  identical to B2's already-tested "blocked exit before the gating event" shape,
  just for different gates. No beat exercises either. I left them in `inert`
  rather than force them into `wants_a_beat` since they write nothing, but this is
  a judgment call the operator may want to override.
- **The heuristic itself: "state effects" vs. "presentation effects."** I treated
  `text`/`bubble_ui`/`se`/`bgm`/`animation`/`screen_fx`/`choice`/`move_route`/
  `graphic`/`control_flow` as non-state (hence `inert` when that's all a row has)
  and `var_write`/`switch_write`/`self_switch_write`/`temp_switch_write`/
  `giveitem`/`givemon`/`heal`/`warp`/`erase_event`/`pc`/`trainerbattle` as state.
  Two rows (`map032/ev012/p0`, `ev013/p0`, `map048/ev011/p0`) have `var_write` but
  I reclassified them to `inert` after reading their scripts: the var they write
  (`VAR_PEOPLE_TALKING` / `VAR_TEMP_POKEMON_CHOICE`) is a shared RNG scratch
  variable for picking a random flavor line, not part of any tracked progression —
  worth flagging in case the operator disagrees with that call for other chapters'
  rows using the same pattern.

## 8. Test suite finding: `test_script_is_idempotent` is not P8-safe

Regenerating CH01's manifest (as this task instructs) turns
`tests/test_rederivation_freeze.py::test_script_is_idempotent` **red**:

```
AssertionError: CH01: regeneration does not match committed freeze file --
run scripts/freeze_rederivation.py write
...
- eam": null
+ eam": null,
+       "terrain": null,
+       "reachability_consulted": true...
```

**This is a design gap in the test, not a regression to fix by editing the test**
(per this task's own instruction, and per §1's diff: the only real content
difference is the one `unhandled` field already classified category-1). The root
cause: `scripts/freeze_rederivation.py`'s `_manifest_rows_by_id` (`:122-134`) reads
`manifest_rows` by calling `_read_json` on the **live working-tree file**
(`MANIFEST_PATHS[chapter]`), not via `git show <blob_sha>:<path>`. Only the
`blob_sha` recorded in `_header` is pinned to git; the row *content* `build_freeze`
recomputes is whatever is on disk *right now*. `test_script_is_idempotent` (added
alongside the freeze) calls `build_freeze()` fresh and diffs it against the
committed freeze file's bytes — which is exactly the comparison that breaks the
moment P8 does its first, expected, instructed regeneration.

Its sibling, `test_frozen_manifest_rows_match_blob` (`tests/test_rederivation_freeze.py:56`),
was written correctly for this purpose — it reads `blob_rows` via
`git cat-file`/`git show`, bypassing the working tree, and its own docstring says
"stays meaningful after P8 regenerates the working manifest." **It still passes.**
`test_script_is_idempotent`'s docstring ("Regenerating into a tmp dir reproduces
the committed bytes exactly") doesn't match what the test body actually does either
— it never uses its own `tmp_path` fixture, per the comment above it explaining
that redirecting `FREEZE_DIR` was "awkward" so it fell back to calling
`build_freeze()` in-process against the real working tree instead. The test is
verifying "the script's output today equals the script's output when the freeze
was written" rather than "the script is idempotent," and those two things are only
the same thing as long as nobody has run P8 yet.

**Recommendation (not applied — outside this task's write scope):** either make
`test_script_is_idempotent` genuinely idempotent-in-isolation (write into
`tmp_path`, compare the two writes to each other, drop the "matches committed"
assertion since `test_frozen_manifest_rows_match_blob` already owns that check via
the blob), or have `_manifest_rows_by_id` read through `git show HEAD:<path>`
consistently with how `_git_blob_sha` already treats provenance. Left as a P8/P10
follow-up, not fixed here per the task's constraint against editing tests to make
them pass.

## 9. Files touched

- `reference/manifests/CH01.manifest.json` — regenerated via the generator (as
  instructed; not hand-edited).
- `investigations/ch01_coverage.md` — this document.

No dispositions file was written for CH01 or any chapter.
