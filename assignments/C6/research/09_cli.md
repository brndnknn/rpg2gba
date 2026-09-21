# Research: C6 Task 9 (`__main__.py`, the CLI / CH05 checkpoint) — measured data

**Dated 2026-09-21.** This is measured data, not a solution. It does not implement the
boundary-warp handling or the duplicate-exit fix, and it does not recommend which stage should
own either. Every number below was produced by a throwaway script under `/tmp/c6research/` run
against this build's `output/uranium-build/` and `reference/` data; the scripts are not part of
the repo and are not committed. Repo state at measurement time: Tasks 6 (emit) and 8 (review)
are implemented and their tests are live (`e41f2d1c`, `ead93860`). The other seven test files
are still `pytest.mark.skip`ped, and `build_plan`/`write_outputs` in
`src/rpg2gba/beat_gen/__main__.py` are wired (`db89b62e`) but call select, group, seam, locate,
adapt and generic, which are stubs raising `NotImplementedError`. *(Corrected 2026-09-21 by the
lead: the draft said all nine were skipped.)* So `build_plan("CH05")` cannot be run end-to-end today; item 1
below reproduces the blocker by calling `playtest.cells.warp_cell` directly, in isolation, as
the task brief itself suggests.

---

## 1. The failure itself

Direct call, no pipeline:

```python
from rpg2gba.playtest.cells import warp_cell
warp_cell("MAP_NOWTOCH_CITY", to="MAP_PASSAGE_CAVE_2F")
```

Reproduces exactly the error quoted in `09_cli.md`'s "The blocker you will hit":

```
ValueError: warp_cell: MAP_NOWTOCH_CITY has 2 distinct warp exits to MAP_PASSAGE_CAVE_2F:
cell=(68, 43) event_id=19, cell=(68, 43) event_id=19 -- disambiguate with event_id=
```

This is the **reciprocal** lookup `warp_beat` makes when `crosses_reciprocal` is true
(`round_trip=True` or `start_side="dest"`) — `src/rpg2gba/playtest/archetypes/warp.py:365`,
`return_crossing = warp_cell(dest_map_constant, to=map_constant)`. The **forward** (claimed)
leg's own lookups do **not** fail — measured directly:

| call | result |
|---|---|
| `warp_cell("MAP_PASSAGE_CAVE_2F", to="MAP_NOWTOCH_CITY", event_id=2)` | `(16, 5)` — ok |
| `warp_cell("MAP_PASSAGE_CAVE_2F", to="MAP_NOWTOCH_CITY")` (no `event_id`) | `(16, 5)` — ok |
| `arrival_cell("MAP_NOWTOCH_CITY", from_map="MAP_PASSAGE_CAVE_2F", event_id=2)` | `(68, 43)` — ok |

The forward direction is single-valued because Map037's own event 2 (the claimed row,
`map037/ev002/p0`) has exactly one command-201 page. The ambiguity lives entirely on
**Map040's side**: Map040 event 19 (cell `(68, 43)`) is what the *return* search finds, and it
has two pages carrying the identical warp.

**Map040 event 19's pages** (`output/uranium-build/maps/Map040.json`, mechanically — event
list, no dialogue):

| page | condition block present? | code-201 (warp) params present? |
|---|---|---|
| 0 | yes (switch/variable/self-switch condition fields, all present in the JSON schema whether active or not) | yes — `[0, 37, 16, 6, 2, 1]` (mode=0 literal, dest_map=37, dest_x=16, dest_y=6, facing=2, fade=1) |
| 1 | yes | no (single command, code 0 = end) |
| 2 | yes | **yes — identical `[0, 37, 16, 6, 2, 1]`** |
| 3 | yes | no (a longer command list — codes `111,208,106,208,209,509,210,0,412,355,0` — no code-201 anywhere) |

Pages 0 and 2 carry byte-identical code-201 parameters. `extract_warp_exits`
(`src/rpg2gba/traversal/warps.py:39-77`) walks every page of every event with no page-condition
awareness (RPG Maker's own page-priority/condition rules are not consulted at all — see item 2),
so it emits two `WarpExit` records for event 19, cell `(68,43)`, both `dest_map=37,
dest_x=16, dest_y=6, dest_facing=2` — exactly the two "distinct" (in truth identical) exits the
error message lists.

---

## 2. The duplicate-exit bug

**Where `warp_exits` is built:** `src/rpg2gba/traversal/graph.py:355-358`:

```python
warp_list = extract_warp_exits(map_json)
warp_exits: dict[Cell, list[WarpExit]] = {}
for w in warp_list:
    warp_exits.setdefault(w.cell, []).append(w)
```

`extract_warp_exits` (`src/rpg2gba/traversal/warps.py:39-76`) iterates `event.get("pages",
[])` and, for every page carrying a literal (mode==0) code-201 command, appends a `WarpExit` —
one per **page**, not one per **event**, with no page-condition/self-switch filtering and no
dedup. RPG Maker XP evaluates page conditions at runtime and only one page is ever "active" for
a given switch/variable/self-switch state, but nothing in `extract_warp_exits` or
`build_map_graph` reads `page.condition` at all — confirmed by reading the full function body;
`condition` is never referenced in `warps.py`. So two pages with the same warp command but
different (mutually-exclusive-at-runtime) conditions become two list entries under the same
cell.

*(Lead note, 2026-09-21: "doesn't read page conditions" is one way to frame the cause. The
mechanical fact is one exit per page. That leaves two different fixes with different blast
radius. (a) Collapse exact-duplicate `WarpExit`s: the list stops lying about how many distinct
exits exist, and nothing else changes. (b) Model page conditions: which exits exist would then
depend on story state, and that's a much larger change touching all five callers. Map040 ev19's
pages carry the same destination, so (a) alone clears it. Whether any of the 98 duplicate
groups also has same-cell pages with different destinations isn't measured here. If it does,
(a) leaves those as a genuine "many".)*

**Corpus-wide scan** (`extract_warp_exits` over every staged `output/uranium-build/maps/
Map*.json`, grouping by `(cell, event_id)` and counting exact-duplicate `WarpExit` tuples —
same cell, same event_id, same dest_map/dest_x/dest_y/dest_facing):

- **199 staged maps total.**
- **47 maps (23.6%)** carry at least one cell whose `warp_exits` list holds an exact duplicate.
- **98 distinct `(map, cell, event_id)` groups** are affected, with duplicate counts ranging
  from 2 to 6 (e.g. `Map094.json (40,0) event_id 1` count 6, `Map144.json (16,50) event_id 151`
  count 6, `Map213.json (28,20) event_id 3` count 6; most groups are count 2).
- Full per-map list (map, cell, event_id, count) is in the scratch script's output; 47 maps
  affected, 98 groups, reconciling to the corpus-wide total above. **CH05's own maps (36, 37)
  have zero duplicate groups** — the bug only shows up on Map040, which CH05 touches only as a
  warp *destination*, never as one of its own maps.

**Callers of `MapGraph.warp_exits`** (every hit in `src/rpg2gba/`, from a whole-package grep,
not just `playtest/cells.py`):

| caller | file:line | effect of a duplicate |
|---|---|---|
| `cells._matching_warp_exits` (feeds `warp_cell`/`arrival_cell`) | `src/rpg2gba/playtest/cells.py:283-327`, `330-369` | **Broken.** The "zero/one/many" rule (`cells.py`'s own module docstring, lines 293-327/330-369) counts list length, so 2 identical entries reads as "2 distinct exits" and raises, even though they describe the same crossing. |
| `warp._report_reciprocal_manifest_row` (advisory log only) | `src/rpg2gba/playtest/archetypes/warp.py:114-134` | Cosmetic — would log the same reciprocal-row advisory twice; `try/except Exception` around it (`warp.py:107-112`) means it never raises. |
| `chapter._reachable` (existence check only, `bool(...)`) | `src/rpg2gba/playtest/chapter.py:791` | Unaffected — only checks non-emptiness. |
| `heal_locations._warp_adjacent_cells(set(graph.warp_exits.keys()))` | `src/rpg2gba/pbs_converter/heal_locations.py:373` | Unaffected — takes `.keys()` as a `set`, duplicates in the value lists never seen. |
| `traversal.__main__` dump/count command | `src/rpg2gba/traversal/__main__.py:127,139,153` | Cosmetic — the exit-count line (`traversal/__main__.py:139`) would over-count by the duplicate factor; a dump/debug command, not load-bearing. |

**No test pins exact `warp_exits` list contents or length.** Whole-package grep for
`warp_exits[` and `len(...warp_exits` in `tests/`: only two hits, both in
`tests/test_traversal_build.py:46,48`, and both index `[0]` on a list that (for Map037's own
cells, which have no duplicates) already has exactly one entry — a dedup fix would not change
either assertion. No test in `tests/` asserts `len(graph.warp_exits[cell]) == N` for any N. So a
fix confined to `graph.py`'s dict-building loop (or to `extract_warp_exits`) has no currently-
pinned test to break, based on this grep.

---

## 3. How the hand module handles B11

`src/rpg2gba/playtest/chapters/ch05.py:745-775`. B11 is **not** registered through `warp_beat` —
it is a plain `@ch05.beat(...)`-decorated function, `archetype="warp"` tagged but hand-written:

```python
@ch05.beat("B11", "The player reaches the CH05|CH06 boundary at Map037 "
                     "event 2 (16,5); Map040 is not in SLICE_MAP_IDS, so no "
                     "warp compiles here and the tile is walkable and inert "
                     "-- CH05's contract is to deliver the player to the "
                     "edge, not cross it (boundary convention; manifest "
                     "map037/ev002/p0)",
            map_constant=MAP_2F, at=_B11_BOUNDARY, group="B11",
            rows=("map037/ev002/p0",), archetype="warp")
def b11(emu: Emulator) -> None:
    ...walk to the boundary tile, assert exact position, assert MAP_2F (no map
    change), assert field not locked...
```

**No `assertions=` kwarg is passed** — `ChapterBuilder.beat`'s `assertions` parameter defaults
to `None` (`src/rpg2gba/playtest/chapter.py:406`), so `B11`'s `beat.assertions is None`. This
directly matters for C9's test: `test_generated_module_imports_and_claims_every_owned_row`
asserts `all(b.assertions is not None for b in own)` for the **generated** module
(`tests/test_beat_gen_cli.py:100`) — the hand module's own B11 would **fail** that specific
assertion if it were the thing being checked (it isn't; the test only checks the generated
module).

**What the row's floor declares** (`floor_for_row("map037/ev002/p0")`, mechanical — kinds and
params, no dialogue):

```
refused: False
completes {}
trigger  {'trigger': 'player_touch'}
visual   {'code': 223, 'detail': 'screen_tone'}   (x2, two separate visual commands)
visual   {'code': 106, 'detail': 'wait'}
visual   {'code': 355, 'detail': 'pbCaveExit'}
warp     {'arrives_on_door': False, 'direction': 2, 'map_id': 40, 'x': 68, 'y': 43}
```

`warp_beat`'s `_EXECUTED_KINDS = frozenset({"trigger", "completes", "warp", "visual",
"audio"})` (`warp.py:70-72`) covers every kind this row's floor carries. A `warp_beat`/
`declare_assertions(..., template="warp")` call on this row **would** produce a non-`None`,
non-empty declared-assertions set — see item 5 for whether `round_trip` affects that.

**Compared with what `warp_beat` would do:**

- **With `round_trip=True`** (what `route_kwargs("warp", side)` currently always produces,
  per `__main__.py`'s `BOUNDARY WARP` comment, `src/rpg2gba/beat_gen/__main__.py:220-224`): the
  body crosses forward, then calls `_back`, which needs `return_crossing =
  warp_cell(dest_map_constant, to=map_constant)` (`warp.py:365`) — this is exactly the call
  that raises the item-1 error, because it searches *from* Map040's graph.
- **Without `round_trip`** (i.e. `round_trip=False`, `start_side="origin"`, the defaults): see
  item 5 — this specific registration-time exception disappears, but a different, ROM-time
  failure mode remains per `ch05.py`'s own documented reasoning (ROM cannot compile a warp at
  Map040 because it isn't in `SLICE_MAP_IDS`).

---

## 4. Boundary facts: what identifies a warp as leaving the chapter's built ROM

**Candidate signals, and their value for map 40 (the B11 destination):**

| signal | source | value for map 40 |
|---|---|---|
| `reference/chapters.json` map membership | `chapter_atlas.binding.Chapter.maps` (a `tuple[int, ...]`, `src/rpg2gba/chapter_atlas/binding.py:46`) | CH05's `Chapter.maps` is `(36, 37)` — 40 is absent. `ChapterBinding.successor(chapter_id)` (`binding.py:96-…`) finds the chapter whose `predecessor` names this one — the forward-pointer helper R3 cites for the `boundary` disposition mechanism. |
| `tileset_converter.map_set.SLICE_MAP_IDS` | membership set | **`40 not in SLICE_MAP_IDS`** — measured in `05_adapt.md` §5 and unchanged here. This is the actual gate on whether a compiled `warp_event` exists (`metadata_wiring.classify_event`). |
| `MAP_*` constant existence (`routing.locations._map_constant_for`) | `output/uranium-build/porymap/map_constants.json`, inverted (`src/rpg2gba/routing/locations.py:124-153`) | **Succeeds** — `_map_constant_for(40)` returns `MAP_NOWTOCH_CITY`, no exception (directly re-verified this session: `warp_cell("MAP_PASSAGE_CAVE_2F", to="MAP_NOWTOCH_CITY", event_id=2)` resolves cleanly). Its own error message (`locations.py:148-152`) *mentions* `SLICE_MAP_IDS` as a guess ("almost certainly not in SLICE_MAP_IDS") but the function never reads that table — it only checks whether a constant was minted, a different, earlier pipeline stage. |
| staged map JSON existence | `output/uranium-build/maps/Map040.json` | **Exists** — read directly this session (event 19, 4 pages, confirmed above). |
| engine's emitted map data (compiled warp event) | `SLICE_MAP_IDS` gate, per `ch05.py`'s own B11 note | **Absent** — `ch05.py:204-206` states `metadata_wiring.classify_event` skipped map 40 and emitted no `warp_event`, because it isn't in `SLICE_MAP_IDS`. Not independently re-derived this session (would require reading `metadata_wiring.py`/a compiled build); taken as read from the cited hand-module comment and cross-checked against the `SLICE_MAP_IDS` measurement above, which is independently verified. |

**Do the signals ever disagree?** Yes, for map 40 specifically: `chapters.json` membership and
`SLICE_MAP_IDS` both say "not this chapter's / not staged for compilation," while
`_map_constant_for` and staged-JSON-existence both say "resolvable, decoded data exists." This
is `05_adapt.md` §5's finding, re-confirmed here: **map 40 is this corpus's only observed
resolves-but-not-`SLICE_MAP_IDS` warp destination among CH01–CH05's warp rows** — every other
CH01–CH04 warp destination (including ordinary cross-chapter ones, e.g. CH01's Moki Town house
warps into CH08's maps) resolves a `MAP_*` constant *and* is staged/playable. Not re-run this
session; cited from `05_adapt.md` §5, whose own methodology (constant resolution success/
failure per warp row) is independently reproducible from the code read above.

**Which C6 stage currently receives which input**, from each stage's own function signature
(all currently `NotImplementedError` stubs; signatures read directly):

| stage | function | signature's inputs | has `chapters.json`/`successor()`? | has `SLICE_MAP_IDS`? | has `map_constant_fn`? |
|---|---|---|---|---|---|
| select | `select_rows(rows, verdicts, floors)` (`select.py:31`) | manifest rows, story verdicts, floors | no | no | no |
| group | `plan_beats(owned, matches, floors)` (`group.py:33`) | owned rows, archetype matches, floors | no | no | no |
| seam | `seam_crossings(row, *, from_graph, to_graph)` (`seam.py:41`) | one row, two `MapGraph`s | no | no | no |
| locate | `locate_beats(beats, rows_by_id, *, cell_fn, seam_fn, map_constant_fn)` (`locate.py:29`) | beats, rows, and three injected functions | no | no | **yes** (`map_constant_fn`, but see above — success ≠ `SLICE_MAP_IDS` membership) |
| adapt | `archetype_kwargs(beat, match, floors, *, map_constant_fn)` (`adapt.py:34`) | beat, match, floors | no | no | **yes** (same caveat) |
| emit | `emit_module(plan)` (`emit.py:110`) | the finished `ChapterPlan` | no | no | no |
| CLI `build_plan` | `build_plan(chapter_id, *, build_dir)` (`__main__.py:166`) | loads `binding` itself via `load_binding(DEFAULT_CHAPTERS_PATH)` (`__main__.py:169`) | **yes** — `binding.chapter(chapter_id).predecessor`/`.maps` available; `successor()` not currently called anywhere in `__main__.py` (grep of the file: no `.successor(` call) | no (`SLICE_MAP_IDS` is not imported anywhere under `src/rpg2gba/beat_gen/` or `src/rpg2gba/routing/` — only mentioned as a string literal in `locations.py:150`) | yes, via `_map_constant_for` (imported `__main__.py:63`) |

A separate, already-existing module — `src/rpg2gba/chapter_manifest/boundary_model.py`
(`ChapterBoundaryModel`, `build_boundary_model`) — implements chapter-boundary detection for
the **disposition** pipeline (R2/R3's `boundary` verdict), including a `_crossing_row_ids`
helper and `_ensure_successor_loaded` (cited by name in `REDERIVATION_PLAN.md` around its R2/R3
sections). It is not imported by anything under `src/rpg2gba/beat_gen/` today (confirmed by
grep — no `boundary_model` import in `beat_gen/`). Whether it's relevant to C6's own boundary
question is a fact for you to weigh, not established here.

---

## 5. What `warp_beat` can do without a round trip

**`inspect.signature(warp_beat)`** (`playtest/archetypes/warp.py:137-160`, params only):
`builder`, `chapter_id`, `map_constant`, `map_id`, `event_id`, `dest_map_constant`,
`mechanism`, `beat_name` (all required); `description=None`, `direction=None`,
`assert_facing=False`, `assert_bgm=False`, `dest_engine_map_dir=None`, `group=None`,
`round_trip=False`, `return_direction=None`, `start_side="origin"`, `manifest_rows=None`,
`manifest_dir=None`, `manifest_chapter_id=None`, `floor_lookup=None` (all optional, defaults
shown).

**With `round_trip=False` and `start_side="origin"` (the all-defaults case):**
`crosses_reciprocal = round_trip or start_side == "dest"` evaluates `False`
(`warp.py:259`). The body (`warp.py:491-495`) then runs only:

```python
if start_side == "origin":
    _forward(emu, check_arrival_details=True)
    if round_trip:      # False -> skipped
        _back(emu)
        _forward(emu)
```

i.e. exactly one crossing, the claimed forward leg, nothing else. Registration-time, this also
means the reciprocal lookup (`warp.py:365`, `warp_cell(dest_map_constant, to=map_constant)`) is
**never called** — `if crosses_reciprocal:` at `warp.py:361` guards it. **Directly verified
this session:** the item-1 `ValueError` comes exclusively from that guarded reciprocal lookup;
a one-way call would not execute it at all, so registering B11 this way would not raise it.

**What it asserts on the one-way crossing:** `_forward` (`warp.py:424-452`) calls `_cross`
(door/threshold/arrow dispatch → `assertions.cross_threshold`/`enter_door`/
`cross_arrow_warp`, then `emu.settle_field()`), then `assertions.require_map(emu, beat_name,
dest_map_constant)`, then `assertions.assert_position_exact(emu, beat_name, landing)` — i.e. it
asserts the map genuinely changed to `dest_map_constant` and the landing cell is exact. For
B11, `dest_map_constant` would be `MAP_NOWTOCH_CITY`. Per `ch05.py`'s own B11 section
(`ch05.py:204-211`, quoted in item 3), `cross_threshold` ultimately calls
`assertions.wait_for_map(..., dest_map)`, which "polls until the map changes... against a
destination that was never staged, that call cannot succeed; it would hang out to its frame
budget and fail loud on every run" — **this reasoning is not specific to `round_trip=True`**;
it is about whether the *compiled game* actually fires a map-change transfer at all, which per
item 4's `SLICE_MAP_IDS` finding it does not, for either a one-way or round-trip call. So
dropping `round_trip` avoids the item-1 *registration-time* exception but, per the hand
module's own stated reasoning (not independently re-verified in-ROM this session — no ROM runs
were performed), does not avoid a *runtime* hang if the beat's body is actually executed
against the compiled ROM.

**Is one-way use (`round_trip=False`, `start_side="origin"`, the defaults) already exercised by
a hand module?** Yes — `ch05.py`'s own `B8` call (`ch05.py:558-579`) passes neither
`round_trip` nor `start_side`, so both take their defaults: a single forward crossing,
`map036/ev002/p0` → `MAP_PASSAGE_CAVE_2F`, with no reciprocal lookup and no return-direction
requirement. This is a real, already-in-the-corpus precedent for a bare one-way `warp_beat`
call (used there because the stop's earlier beats, `B8_return`/`B8_nudge`, already proved the
reciprocal; B8 itself only needs to prove the forward leg once more).

**Is the "row claimed, floor declared" requirement satisfied by a one-way call?**
`declare_assertions(claimed_rows, executed_kinds=_EXECUTED_KINDS, template="warp", extras=...,
floor_lookup=lookup)` is called at `warp.py:354-357`, **unconditionally** — it does not read
`round_trip`, `start_side`, or `crosses_reciprocal` at all; it only depends on `claimed_rows =
(row_id,) + arm_rows` (computed at `warp.py:352-353`, also unconditional) and the row's floor.
So yes: a one-way `warp_beat(..., round_trip=False)` call on `map037/ev002/p0` would declare
the same non-`None` assertions (`trigger`/`completes`/`warp`/`visual`, per item 3's floor dump)
as a round-tripping call would — the declared-assertions question and the round-trip question
are independent in this code path.

---

## 6. Freeze grading

`reference/frozen/hand_beats_ch01-ch05.json`, `chapters.CH05`: **21 frozen beats total**
(counted directly). The scope `test_frozen_rows_on_ch05_maps_are_claimed` checks —
`own_maps = {36, 37}` (`tests/test_beat_gen_cli.py:116`) — narrows to rows on CH05's *own*
staged maps:

| frozen beat | group | rows | on own maps (36/37)? |
|---|---|---|---|
| `B1` | B1 | `map036/ev001/p0` | yes (36) |
| `B1_nudge` | B1 | `map035/ev001/p1`, `.../b0` | no (35, CH04's map) |
| `B1_in` | B1 | `map035/ev001/p0` | no (35) |
| `B2`/`B2_spent` | B2 | `map036/ev003/*` | yes |
| `B3`/`B3_retalk1` | B3 | `map036/ev004/*` | yes |
| `B5`/`B5_retalk1` | B5 | `map036/ev006/*` | yes |
| `B4`/`B4_spent` | B4 | `map036/ev005/*` | yes |
| `B8_return` | B8 | `map037/ev001/p0` | yes (37) |
| `B8_nudge` | B8 | `map036/ev002/p1`, `.../b0` | yes (36) |
| `B8` | B8 | `map036/ev002/p0` | yes (36) |
| `B9`/`B9_retalk1` | B9 | `map037/ev004/*` | yes |
| `B14` | B14 | `map037/terrain/stairs/20,9`, `.../20,10` | yes |
| `B13` | B13 | `map037/terrain/stairs/11,9`, `.../11,10` | yes |
| `B10`/`B10_retalk` | B10 | `map037/ev005/*` | yes |
| **`B11`** | **B11** | **`map037/ev002/p0`** | **yes (37)** |

**B11's row is in-scope for the freeze test.** `map037/ev002/p0` is on map 37, one of CH05's
own two maps, so `test_frozen_rows_on_ch05_maps_are_claimed` requires the generated suite's
`claimed` set to include it — this is exactly the row the boundary-warp decision has to leave
claimed, confirming the task file's own framing ("Whatever you decide must still leave the row
claimed, with its floor declared").

Only `B1_nudge`/`B1_in` (rows on map 35, CH04's map) fall outside `own_maps`; every other
frozen CH05 row, 19 of 21 beats' worth, is on map 36 or 37 and therefore in-scope.

---

## 7. Q1/Q4 data

### (a) Hand CH05 rows vs. the pinned generated plan's rows

**Pinned generated beat names** (`tests/test_beat_gen_group.py:205-222`, the
`test_real_ch05_plan` fixture — 20 names): `m036e001_warp`, `m036e002_warp`,
`m036e002_arrival_nudge` (+`_arms`), `m036e003_item_ball` (+`_arms`), `m036e004_trainer`
(+`_arms`), `m036e005_item_ball` (+`_arms`), `m036e006_trainer` (+`_arms`), `m037e001_warp`,
`m037e002_warp`, `m037e004_trainer` (+`_arms`), `m037e005p0`, `m037e005p1`, `m037stair11x9`,
`m037stair20x9`.

**Row-by-row mapping to `ch05.py`'s own hand beats** (from `02_group.md` §8, reproduced/
verified against `ch05.py`'s source read this session — no re-run needed, the mapping is a
static row-identity comparison):

| pinned generated beat | hand beat | rows |
|---|---|---|
| `m036e001_warp` | `B1` (only the `map036/ev001/p0`-claiming call of B1's three) | `map036/ev001/p0` |
| `m036e002_warp` | `B8` | `map036/ev002/p0` |
| `m036e002_arrival_nudge`(+arms) | `B8_nudge` | `map036/ev002/p1` |
| `m036e003_item_ball`(+arms) | `B2` | `map036/ev003/*` |
| `m036e004_trainer`(+arms) | `B3` | `map036/ev004/*` |
| `m036e005_item_ball`(+arms) | `B4` | `map036/ev005/*` |
| `m036e006_trainer`(+arms) | `B5` | `map036/ev006/*` |
| `m037e001_warp` | `B8_return` | `map037/ev001/p0` |
| `m037e002_warp` | `B11` (hand-written, not `warp_beat`) | `map037/ev002/p0` |
| `m037e004_trainer`(+arms) | `B9` | `map037/ev004/*` |
| `m037e005p0` | `B10` | `map037/ev005/p0` |
| `m037e005p1` | `B10_retalk` | `map037/ev005/p1` |
| `m037stair11x9` | `B13` | `.../11,9`, `.../11,10` |
| `m037stair20x9` | `B14` | `.../20,9`, `.../20,10` |

**Hand-only, no pinned-generated counterpart:** `B1_nudge`, `B1_in`. Both are registered with
`manifest_chapter_id="CH04"` (`ch05.py:390,406`), claiming rows from **CH04's** manifest
(`map035/ev001/p1`, `map035/ev001/p0`) via R2/R3's cross-chapter-ownership ruling
(`REDERIVATION_PLAN.md:364-407`). `select_rows` for CH05's real-data test only ever sees CH05's
own manifest rows (`select.select_rows(rows, ...)` where `rows = load_chapter_rows("CH05")`,
`__main__.py:171`), so these two rows are structurally outside the pinned 20-beat plan's scope
— not a generator gap, per `02_group.md` §8's own framing, repeated here as it bears directly
on this task's Q1.

**`REDERIVATION_PLAN.md` §10 R2/R3 on the `map035` rows** (`REDERIVATION_PLAN.md:364-407`):
R2 rules `map035/ev001/p0` `boundary`, claimed by CH05's B1 ("the crossing belongs to the
chapter being opened"); R3 rules `map035/ev001/p1` `boundary` too, registered as an
`arrival_nudge_beat` grouped with B1, and states the code-level plumbing this needs
(`find_match` gaining a manifest-chapter override — already present as `manifest_chapter_id=`;
`is_forward_crossing` widening page-level to event-level). Both rulings are already reflected
in `ch05.py`'s current `B1_nudge`/`B1_in` calls.

### (b) Route group order: hand vs. generated

**Hand route** (`reference/routes/CH05.route.json`, `nodes` where `kind == "group"`, in file
order): `B1, B2, B3, B5, B4, B8, B9, B14, B13, B10, B11` — 11 groups, `chosen_approach` is
`None` for every one (no route-solver disambiguation recorded in this file; single-candidate
groups per the task file's own `_picks_with_fallback` logic).

**Pinned generated group order**, inferred from the 20-beat name list's own registration order
(`test_beat_gen_group.py`'s list is itself ordered by "manifest position of first row" per the
task's docstring, `group.py:33-42`'s own contract) mapped one-to-one via the table in (a) above:
`B1(m036e001_warp), B8(m036e002_warp), B8(nudge), B2, B3, B4, B5, B8(m037e001_warp=B8_return),
B11(m037e002_warp), B9, B10, B10(retalk), B13, B14`.

Two differences from the hand order:

1. **B4/B5 swap.** Hand order visits `B3, B5, B4` (Keichi before the Great Ball — `ch05.py`'s
   own comment at lines 471-476 states this is deliberate, route-order not registration-order,
   because "the approved route ... visits Keichi before the Great Ball"). The pinned generated
   list, ordered by manifest position, produces `B3, B4, B5` (event 4, then 5, then 6 —
   ascending event id, the opposite of the hand route's order).
2. **B13/B14 swap.** Hand order visits `B14` before `B13` (east staircase before west). The
   pinned generated list's manifest-position order (event/terrain ordering on map037) is not
   independently re-derived in this session for the exact stair ordering rule, but the group
   names list them `m037stair11x9` before `m037stair20x9` (west, x=11, before east, x=20) —
   the reverse of the hand route.

**Group.py's own docstring note** (from `02_group.md` §8, `group.py:33-42`'s contract as
described there): the pinned plan's own beat order is manifest position, **not** route order —
Task 2's `plan_beats` does not consult the solver at all; `Task 4`/`locate.order_beats` is
what's supposed to reorder groups into route order downstream. So the "difference" measured
here is expected at the `plan_beats` stage and is not by itself evidence about what the
**solved** route (post-Task-4/solver) would produce — that requires running the solver, which
requires Tasks 1–8's stubs to be implemented, not available on this branch. **What R12 says
about order:** `REDERIVATION_PLAN.md` R12 (`REDERIVATION_PLAN.md:1623`, amended 2026-09-17 at
line 1957) is scoped to **coverage of frozen rows with assertions at least as strong**, not to
route-order fidelity: "Generated suites must cover every frozen row with an assertion at least
as strong and reproduce every frozen literal; a mismatch is fixed in the generator or state
model, never excepted" — no clause about matching the hand route's *group visitation order*.
`tests/test_beat_gen_cli.py`'s own order-related tests
(`test_groups_are_contiguous_in_route_order`, `test_every_warp_has_a_press_direction`) check
internal consistency (a beat's group appears contiguously in the *solver's own* route order)
and warp-direction completeness, not agreement with the hand route's particular order.

**Also note:** `02_group.md` §8 separately measured that the pinned generated plan's **group
structure**, not just order, diverges from the hand module's for the B8 stop: `m037e001_warp`,
`m036e002_arrival_nudge`, `m036e002_warp` are three *separate* single-row groups in the
generated plan (each `ArchetypeMatch` gets its own group under Task 2's per-match rule), while
`ch05.py` deliberately shares one `group="B8"` across `B8_return`/`B8_nudge`/`B8` so the solver
keeps them contiguous (`ch05.py:493-517`'s own comment on why). Whether/how that reconciliation
happens (if at all) is not resolved by anything measured in this task's scope.

---

## Decisions left to you

- **Which stage marks a warp as a chapter boundary, if any does.** Item 4 shows no current C6
  stage signature is handed `SLICE_MAP_IDS`, `chapters.json` map membership, or
  `boundary_model`'s existing machinery — every stage that touches warps (`locate`, `adapt`)
  only has `map_constant_fn`, which **succeeds** for map 40 and therefore cannot by itself
  distinguish this row from an ordinary staged cross-chapter warp. Building that signal in
  requires either a new import somewhere in the `beat_gen` pipeline or reusing
  `boundary_model.py` (not currently wired into `beat_gen/` at all), or handling the failure
  reactively (catching `warp_cell`'s `ValueError` and falling back) rather than proactively
  detecting the boundary before attempting the reciprocal lookup.
- **What the boundary beat's body should do.** Item 5 shows a one-way `warp_beat` call (already
  precedented by `ch05.py`'s own `B8`) avoids the *registration-time* exception (no reciprocal
  lookup happens at all) but, per `ch05.py`'s own B11 comment, would still hit a ROM-time
  `wait_for_map` hang if actually run, because `SLICE_MAP_IDS` excludes map 40 regardless of
  `round_trip`. The hand module's current B11 avoids the ROM hang entirely by not crossing at
  all (walk to the tile, assert position/map/no-lock, never call `_cross`) — but that is a
  hand-written function, not a `warp_beat` call, and (per item 3) declares `assertions=None`,
  which the generated-module test (`tests/test_beat_gen_cli.py:100`) requires to be non-`None`.
  Item 5 also shows `declare_assertions` (and therefore a non-`None` assertions set) is reachable
  independent of whether any crossing happens at all, since it depends only on `claimed_rows`
  and the floor — so satisfying "floor declared" does not by itself require choosing any
  particular crossing behavior.
- **Whether to fix the duplicate-exit bug, and where.** Item 2 shows the bug is real,
  corpus-wide (47/199 maps, 98 groups), has no currently-pinned test asserting exact
  `warp_exits` contents, and only one of its five callers (`cells._matching_warp_exits`, and
  therefore `warp_cell`/`arrival_cell`) is actually broken by it — the other four either ignore
  list length or are advisory/cosmetic. Fixing it (in `extract_warp_exits`'s page loop, or in
  `graph.py`'s dict-building loop, or in `cells.py`'s matching logic) would make the item-1
  reciprocal lookup on Map040 resolve to one exit instead of raising — but that exit still
  points at a destination (Map037) whose *own* side of the round trip is fine; fixing the dedup
  does not by itself address whether the *forward* crossing into the unstaged Map040 should be
  attempted, walked, or skipped (that's the boundary-beat question above).
- **How the pinned generated plan's group order/structure (item 7b) should be reconciled with
  the hand route's order and grouping**, if at all. R12 (as quoted) does not require order or
  group-structure fidelity to the hand route — only frozen-row coverage. Whether the B4/B5 and
  B13/B14 order differences, and the B8-stop's 3-groups-vs-1 structural difference, are
  generator gaps, acceptable divergences, or things a later stage (the solver, or `locate`'s
  `order_beats`) is expected to reconcile is not settled by anything measured here.
