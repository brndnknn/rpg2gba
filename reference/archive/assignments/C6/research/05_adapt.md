# Research: C6 Task 5 (`adapt.py`) — measured data

**Dated 2026-09-21.** This is measured data, not a solution. It does not implement
`archetype_kwargs`/`warp_candidates`/`route_kwargs`, and it does not recommend a design.
Every number below was produced by a throwaway script under `/tmp/c6research/` run against
this build's `output/uranium-build/` and `reference/` data; the scripts are not part of the
repo and are not committed.

---

## 1. Item constants: `ESCAPEROPE` → `ITEM_ESCAPE_ROPE`

**The mint point (CLAUDE.md §4.3):** `src/rpg2gba/pbs_converter/_naming.py:47-52`
(`to_constant(prefix, name)`) is the single normalizer. For items specifically,
`src/rpg2gba/pbs_converter/_resolve.py:103-112` (`ItemResolverMixin.item_constant`) calls
`to_constant("ITEM", display_name_or_internal)` and records the result into the id map via
`self.id_map.add("items", internal, const, ...)`. The persisted result is
`reference/uranium_id_map.json`'s `"items"` table: internal Ruby symbol (e.g. `"ESCAPEROPE"`)
→ `ITEM_*` constant (e.g. `"ITEM_ESCAPE_ROPE"`). Sample entries:
`{"ABSORBBULB": "ITEM_ABSORB_BULB", "ACAIBERRY": "ITEM_ACAI_BERRY", ...}`.

**Already-existing forward check:** `src/rpg2gba/playtest/archetypes/item_ball.py`:
- `_uranium_item_constants()` (lines 81-87) loads and caches `reference/uranium_id_map.json`'s
  `"items"` table.
- `_validate_item_constant()` (lines 90-113) takes the floor's `item_grant` assertion's
  `item` param (the internal symbol) and the author's `item=` kwarg, looks the symbol up in
  the table, and raises `ValueError` on a missing entry or a disagreement. This is the lookup
  the task brief's "look for the forward check" hint points at.

**Measured on CH05** (`floor.assertions` where `kind == "item_grant"`, via
`beat_floor.walk.floor_for_chapter("CH05", ...)`):

| row_id | source `item` symbol | `reference/uranium_id_map.json["items"]` result | qty |
|---|---|---|---|
| `map036/ev003/p0` | `ESCAPEROPE` | `ITEM_ESCAPE_ROPE` | 1 |
| `map036/ev005/p0` | `GREATBALL` | `ITEM_GREAT_BALL` | 1 |
| `map036/ev008/p0` | `TM76` | `ITEM_TM76` | 1 |
| `map036/ev009/p0` | `SABLEYEITE` | `ITEM_SABLENITE` | 1 |
| `map037/ev005/p0` | `REVIVE` | `ITEM_REVIVE` | 1 |

(Only `map036/ev003` and `map036/ev005` are archetype `item_ball` matches with a claimed
beat in `ch05.py`; `ev008`/`ev009` are the sealed B6/B7 room, unauthored; `map037/ev005` is
B10, hand-written, no archetype.)

**Across every `item_grant` floor assertion in CH01–CH05** (all rows, not just archetype
matches):

| chapter | `item_grant` assertions | resolved | failed |
|---|---|---|---|
| CH01 | 7 | 7 | 0 |
| CH02 | 9 | 9 | 0 |
| CH03 | 12 | 12 | 0 |
| CH04 | 3 | 3 | 0 |
| CH05 | 5 | 5 | 0 |
| **total** | **36** | **36** | **0** |

No failures anywhere in the corpus measured.

---

## 2. Trainer constants: `(Manny, HIKER)` → `TRAINER_MANNY_5`

**The forward check that already exists:** `src/rpg2gba/playtest/archetypes/trainer.py`,
`_validate_battle_identity()` (lines 125-166). It reads the battle row's floor `battle`
assertion (`trainer_type`, `name`), derives `expected_class = to_constant("TRAINER_CLASS",
trainer_type)`, loads `output/uranium-build/intermediate/trainers.json` via
`trainer_converter.battles.load_trainers_json` (battles.py:155-157, which reads the
`"trainers"` key), looks up the author's `trainer_const` in that table, and raises
`ValueError` if `entry["trainer_class"]`/`entry["name"]` disagree with the floor. This is the
"forward check" the task hint refers to; there is no reverse `(name, class) → trainer_const`
helper in the codebase today — `_validate_battle_identity` only ever checks a candidate the
author already supplied.

**Where `_5` comes from — Q1's answer, precisely.** `src/rpg2gba/pbs_converter/trainers.py`:
- `Trainer` records `index=index` at parse time (`trainers.py:158`, the position in
  Uranium's `trainers.dat` array — "the de-facto Uranium id", per the code comment at
  line 202).
- `_Resolver.trainer_constant()` (lines 200-206): `key = f"{t.name}_{t.index}"`, then
  `const = to_constant("TRAINER", key)`, then `self.id_map.add("trainers", key, const)`.
- The same `t.index` is separately written as the `"id"` field of each entry in
  `output/uranium-build/intermediate/trainers.json`'s `"trainers"` table
  (`trainers.py:290`, `"id": t.index`).

So `_5` is `t.index` — Manny's position in Uranium's `trainers.dat` — recorded **twice**,
independently: as the numeric suffix baked into the minted constant (`reference/
uranium_id_map.json`'s `"trainers"` key, e.g. `"Manny_5": "TRAINER_MANNY_5"`) and as the
`"id"` field of `trainers.json`'s `TRAINER_MANNY_5` entry (`"id": 5`). Measured:

| Uranium name | trainer_type param (floor) | `trainers.json` entry | `uranium_id_map.json["trainers"]` key |
|---|---|---|---|
| Manny | HIKER | `TRAINER_MANNY_5`: `{"id": 5, "trainer_class": "TRAINER_CLASS_HIKER", "name": "Manny", ...}` | `"Manny_5": "TRAINER_MANNY_5"` |
| Keichi | BLACKBELT | `TRAINER_KEICHI_248`: `{"id": 248, "trainer_class": "TRAINER_CLASS_BLACKBELT", "name": "Keichi", ...}` | `"Keichi_248": "TRAINER_KEICHI_248"` |
| Nuñes | HIKER | `TRAINER_NUNES_128`: `{"id": 128, "trainer_class": "TRAINER_CLASS_HIKER", "name": "Nuñes", ...}` | `"Nuñes_128": "TRAINER_NUNES_128"` |

**Ambiguity, measured across the whole sidecar** (`output/uranium-build/intermediate/
trainers.json`, keyed `(name, trainer_class)`):

- 331 total `TRAINER_*` entries, 263 distinct `(name, trainer_class)` keys, **19 keys with
  more than one entry** (i.e. same displayed name + same class, different `id`/instance).
  Examples: `('Angelica', 'TRAINER_CLASS_LADY')` → 2 entries; `('Theo', 'TRAINER_CLASS_RIVAL')`
  → 21 entries (Theo rematches); `('Homer', 'TRAINER_CLASS_SWIMMERMA')` → 4 entries.
- **`('Richard', 'TRAINER_CLASS_BIKER')` → `['TRAINER_RICHARD_137', 'TRAINER_RICHARD_138']`
  is ambiguous, and CH03's `map019/ev006` battle floor is `name='Richard'
  trainer_type='BIKER'`** — i.e. this specific corpus row (not CH05) hits an ambiguous key
  in the sidecar. CH03's `trainer_beats` call would have to disambiguate on something the
  floor doesn't carry (per the task's own note: "nothing in the floor distinguishes two
  trainers with the same name *and* class").
- **None of CH05's three trainers is ambiguous** — `(Manny, HIKER)`, `(Keichi, BLACKBELT)`,
  `(Nuñes, HIKER)` are each a single-entry key. This matches the task file's own claim
  ("checked 2026-09-19: none of CH05's three is ambiguous").

Every trainer `battle` floor assertion's `(name, trainer_type)` in CH01–CH05, for reference:

```
CH01 map050/ev019/p0: name='Theo' trainer_type='RIVAL'
CH02 map033/ev009/p0: name='Marko' trainer_type='FISHERMAN'
CH02 map033/ev010/p0: name='Bob' trainer_type='YOUNGSTER'
CH02 map033/ev030/p0: name='Flood' trainer_type='BUGCATCHER'
CH02 map033/ev034/p0: name='Tath' trainer_type='SCHOOLKID'
CH02 map033/ev035/p0: name='Brandon' trainer_type='TRIATHLETE_MaleRunner'
CH02 map033/ev039/p0: name='Brandon' trainer_type='FISHERMAN'
CH02 map033/ev041/p0: name='Gertha' trainer_type='EXPERT_Female'
CH02 map033/ev053/p0: name='Richey' trainer_type='YOUNGSTER'
CH02 map033/ev103/p0: name='Lynette' trainer_type='LASS'
CH03 map019/ev004/p0: name='Lou' trainer_type='BIKER'
CH03 map019/ev005/p0: name='Joe' trainer_type='BIKER'
CH03 map019/ev006/p0/b0: name='Richard' trainer_type='BIKER'   # ambiguous key, see above
CH03 map019/ev006/p0/b3: name='Richard' trainer_type='BIKER'
CH03 map068/ev014/p0/b0: name='Mawuli' trainer_type='RICHBOY'
CH04 map035/ev003/p0: name='Larrie' trainer_type='HIKER'
CH04 map035/ev012/p0: name='Timothy' trainer_type='YOUNGSTER'
CH04 map035/ev023/p0: name='Brent' trainer_type='BIRDKEEPER'
CH04 map035/ev024/p0: name='Chuck' trainer_type='HIKER'
CH05 map036/ev004/p0: name='Manny' trainer_type='HIKER'
CH05 map036/ev006/p0: name='Keichi' trainer_type='BLACKBELT'
CH05 map037/ev004/p0: name='Nuñes' trainer_type='HIKER'
```

**Files/fields that answer the task's Q1:** `src/rpg2gba/pbs_converter/trainers.py:158`
(`Trainer.index`), `:200-206` (`trainer_constant`, the `f"{t.name}_{t.index}"` key), and
`:290` (`"id": t.index` written into `output/uranium-build/intermediate/trainers.json`).
`reference/uranium_id_map.json`'s `"trainers"` table is the persisted mint record;
`output/uranium-build/intermediate/trainers.json`'s `"id"` field is the same number surfaced
again at battle-conversion time.

---

## 3. `EXPECTED` table: kwarg → source

All ten rows, every kwarg, and where it comes from.

### `warp` (4 rows: `36,1` / `36,2` / `37,1` / `37,2`)

| kwarg | source |
|---|---|
| `map_constant` | `map_constant_fn(match.map_id)` — the test's own `MAP_CONSTANTS` dict standing in for the real resolver |
| `map_id` | `beat.map_id` / `match.map_id` |
| `event_id` | `match.event_id` |
| `dest_map_constant` | the row's floor `warp` assertion's `map_id` param, through `map_constant_fn` (e.g. `map036/ev001/p0`'s floor warp `map_id=35` → `MAP_ROUTE_02`) |
| `mechanism` | **not derivable from any per-row field measured** — the task brief states it as a constant answer ("A2's answer: every warp source cell is door-stamped, so it's a step-on crossing") → always `"threshold"` for this corpus, not read off the floor. `warp.py`'s own module docstring (lines 1-9) confirms `ManifestRow`/the floor carry no field that would let `mechanism` be derived per-instance: "the code-201 destination that would settle it is not on the row". |

### `arrival_nudge` (1 row: `36,2`)

| kwarg | source |
|---|---|
| `map_constant`/`map_id`/`event_id` | same as above, this row's own identity |
| `from_map_constant` | the map that owns the warp row whose floor `warp` assertion lands on **this** nudge event's own cell (see §6) |
| `from_event_id` | that warp row's `event_id` |

### `item_ball` (2 rows: `36,3` / `36,5`)

| kwarg | source |
|---|---|
| `map_constant`/`map_id`/`event_id` | grant row identity |
| `item` | the grant row's floor `item_grant.item` symbol, resolved through `reference/uranium_id_map.json["items"]` (§1) |
| `negative_beat` | `True` exactly when `match.roles` contains a `"spent"` role (task brief, confirmed against `_match_item_ball` in `chapter_manifest/archetypes.py:166-200`, which only assigns a `"spent"` role when a page-1 row exists and passes its own self-switch/cosmetic checks) |

### `trainer` (3 rows: `36,4` / `36,6` / `37,4`, via the `_trainer()` helper)

| kwarg | source |
|---|---|
| `map_constant`/`map_id`/`event_id` | battle row identity |
| `trainer_const` | reverse lookup from the battle floor's `(name, trainer_type)` into the trainers sidecar (§2) — **no existing helper does this reverse lookup**; only the forward check (`_validate_battle_identity`) exists today |
| `defeat_flag` | `f"TRAINER_FLAGS_START + {trainer_const}"` — a **string template over `trainer_const`**, not read from the floor. `ch05.py`'s own `_trainer_defeat_flag` (lines 341-345) is exactly this one-line function; `trainer.py`'s `_NATIVE_TRAINER_FLAG_RE`/`_defeat_write_declaration` (lines 112, 169-199) confirm this shape is the one that declares **nothing** extra from the floor (module docstring point 2: "a `defeat_flag` matching that native shape declares NOTHING for the win branch"). |
| `trigger` | `match.params["trigger"]` |
| `phone` | `match.params["phone"]` |
| `double` | `match.params["double"]` |
| `retalk_pages` | `match.params["retalk_pages"]` |
| `rider` | `match.params["rider"]` |

All five of `trigger`/`phone`/`double`/`retalk_pages`/`rider` are cross-checked by
`trainer_beats` itself at call time against `classify_manifest`'s derivation
(`trainer.py:381-393`) — a caller-stated value that disagrees raises `ValueError`. So they are
directly `match.params` values, not re-derived independently.

**No kwarg in `EXPECTED` lacks an identifiable source.** The one genuinely non-per-row value
is `mechanism` (always `"threshold"` in this corpus, stated as a constant by the task brief,
not read from any field).

---

## 4. Template signatures (`inspect.signature`)

Parameters shown as `name (required/optional[, default])`. Split into: **emitter** (always
one of `builder`/`chapter_id`/the name keyword/`group`, per `emit.py`'s
`_RESERVED_KWARGS = {"chapter_id", "group", "rows"}` + the name keyword, `emit.py:65,72`),
**route** (in `NOT_SOURCE`, `test_beat_gen_adapt.py:56-57`), **archetype_kwargs candidate**
(everything else), or **manifest/floor plumbing** (`manifest_rows`/`manifest_dir`/
`manifest_chapter_id`/`floor_lookup`/`build_dir`/`reference_dir` — test/real-chapter-only
overrides, never touched by `archetype_kwargs`).

### `warp_beat` (`playtest/archetypes/warp.py:137`)

| param | required | emitter/route/candidate/plumbing |
|---|---|---|
| `builder`, `chapter_id`, `beat_name`, `group` | required/required/required/optional | emitter |
| `map_constant`, `map_id`, `event_id`, `dest_map_constant`, `mechanism` | required | candidate |
| `direction`, `return_direction` | optional (None) | route |
| `assert_facing`, `assert_bgm`, `dest_engine_map_dir` | optional | candidate (unused by any CH05 EXPECTED row) |
| `round_trip`, `start_side` | optional | route (`NOT_SOURCE`) |
| `description` | optional (None) | candidate, unused in CH05's EXPECTED |
| `manifest_rows`, `manifest_dir`, `manifest_chapter_id`, `floor_lookup` | optional | plumbing |

### `arrival_nudge_beat` (`arrival_nudge.py:78`)

`builder`/`chapter_id`/`beat_name`/`group` emitter; `map_constant`/`map_id`/`event_id`/
`from_map_constant` required candidate; `from_event_id` optional candidate; `description`
optional candidate (unused); rest plumbing.

### `item_ball_beats` (`item_ball.py:188`)

`builder`/`chapter_id`/`beat_prefix`(name kw)/`group` emitter; `map_constant`/`map_id`/
`event_id`/`item` required candidate; `negative_beat`, `self_switch_letter` optional
candidate; `approach_prefer` optional — **route** per `NOT_SOURCE`; rest plumbing.

### `trainer_beats` (`trainer.py:319`)

`builder`/`chapter_id`/`beat_prefix`(name kw)/`group` emitter; `map_constant`/`map_id`/
`event_id`/`trainer_const`/`defeat_flag`/`trigger`/`phone`/`double`/`retalk_pages`/`rider`
required candidate (9 required non-emitter kwargs — the largest of the five templates);
`approach_prefer` route; `local_id`, `rider_item` optional candidate (both unused in CH05:
no re-talk uses a live position, no trainer carries a rider item); rest plumbing.

### `flavour_npc_beat` (`flavour_npc.py:69`)

`builder`/`chapter_id`/`beat_name`/`group` emitter; `map_constant`/`map_id`/`event_id`
required candidate; `variant`, `page_idx`, `toggled_page_idx`, `self_switch_letter`,
`description` optional candidate; `approach_prefer` route; rest plumbing.

**What `test_only_keywords_the_template_accepts_and_every_required_one` checks**
(`test_beat_gen_adapt.py:88-95`): for the resolved `(module, func, _)` from
`emit.TEMPLATE_CALLS`, `set(got) <= set(params) - NOT_SOURCE` (every kwarg
`archetype_kwargs` returns must be a real, non-route param) and
`required - NOT_SOURCE <= set(got)` (every required, non-route param must be present). It does
**not** check that route-only params (`direction`, `round_trip`, etc.) are absent from
`archetype_kwargs`'s output — only that whatever *is* present is legal.

---

## 5. Warps: every CH05 warp row, plus the boundary/staging question (Q3 data)

| row_id | trigger map/event | dest Uranium map_id | dest `MAP_*` constant resolves? | dest inside CH05's own maps (`chapters.json["maps"]`)? | dest owned by another chapter? |
|---|---|---|---|---|---|
| `map036/ev001/p0` (B1) | 36/1 | 35 | yes, `MAP_ROUTE_02` | no | CH04 |
| `map036/ev002/p0` (B8) | 36/2 | 37 | yes, `MAP_PASSAGE_CAVE_2F` | **yes** | — |
| `map037/ev001/p0` (B8 reciprocal) | 37/1 | 36 | yes, `MAP_PASSAGE_CAVE_1F` | **yes** | — |
| `map037/ev002/p0` (B11) | 37/2 | 40 | **yes, `MAP_NOWTOCH_CITY`** | no | CH06 |

**Easy to conflate with `ch05.py`'s own docstring (not a contradiction; lead retitle, 2026-09-21).** `routing.locations.
_map_constant_for(40)` (`routing/locations.py:124-153`) **succeeds** and returns
`MAP_NOWTOCH_CITY` — it does not raise. `ch05.py`'s B11 section (lines 202-218) says "Map040
(Nowtoch) is not in `SLICE_MAP_IDS`, so `metadata_wiring.classify_event` skipped it and
emitted no `warp_event`" and treats this as the reason `warp_beat` can't be used there. Both
things are true and not actually in tension, but the mechanism is easy to conflate:

- `map_constant_fn`/`_map_constant_for` reads `output/uranium-build/porymap/
  map_constants.json` (via `playtest.chapter._load_map_const_to_uranium_id`) — **a minted
  constant exists for map 40**, and `output/uranium-build/maps/Map040.json` **is staged**
  (decoded map data exists on disk).
- **Measured separately:** `40 in rpg2gba.tileset_converter.map_set.SLICE_MAP_IDS` is
  `False`. `SLICE_MAP_IDS` gates which maps actually get a compiled `warp_event`
  (`metadata_wiring.classify_event`) in the built ROM — a narrower, later-stage set than "has
  a decoded map JSON" or "has a minted `MAP_*` constant".

**This is directly relevant to Q3.** A generator that calls `map_constant_fn(dest_map_id)`
and checks only "did it raise" **cannot** distinguish `map036/ev002` (dest fully staged,
round-trip is safe) from `map037/ev002` (dest has a constant and decoded JSON, but no
compiled warp event exists, so a round-trip would hang at `wait_for_map` and fail loud in the
ROM per `warp.py`'s own `_cross`). `map_constant_fn` succeeding is not proof the destination
is playable; `SLICE_MAP_IDS` membership is the actual gate, and it is a different table than
the one `map_constant_fn` reads.

For comparison, the same measurement across CH01–CH04's warp rows: every warp destination in
CH01–CH04 resolves a `MAP_*` constant successfully (no `ValueError`s), and cross-chapter
destinations are common and ordinary (e.g. CH01's Moki Town has house warps into CH08's
maps that are perfectly staged and playable — being "in another chapter" alone does not mean
unstaged). The CH05→CH06 boundary (`map037/ev002`→map 40) is this corpus's only observed case
of a *resolves-but-not-`SLICE_MAP_IDS`* destination among CH01–CH05's warp rows.

---

## 6. Arrival nudges: event cell vs. matching warp landings

For each `arrival_nudge` match, the event's own `(x, y)` was read from
`output/uranium-build/maps/Map{map_id:03d}.json`'s `events[].{x,y}` (the event list keyed by
`id`), and compared against every warp row's floor `warp` assertion `(x, y)` **across all of
CH01–CH05's warp matches** (not scoped to one chapter) via
`beat_floor.walk.floor_for_chapter`.

CH01–CH05 has 24 `arrival_nudge` matches total. Selected results (full list available on
request; every row was checked):

| row_id | event cell | matching warp landing row(s) |
|---|---|---|
| CH01 `map032/ev003/p1` | (17,11) | `map050/ev001/p1` (same chapter) |
| CH01 `map032/ev023/p1` | (8,44) | **none** |
| CH01 `map032/ev037/p1` | (8,43) | CH02's `map033/ev022/p0`,`ev023/p0`,`ev024/p0` — **cross-chapter, 3-way** |
| CH02 `map033/ev023/p1` | (70,11) | CH01's `map032/ev023/p0`,`ev036/p0`,`ev037/p0` — **cross-chapter, 3-way** |
| CH04 `map035/ev001/p1` (B1_nudge) | (20,33) | **CH05's `map036/ev001/p0`** — cross-chapter |
| CH05 `map036/ev002/p1` (B8_nudge) | (17,4) | CH05's own `map037/ev001/p0` |

**So the search cannot be scoped to "this chapter's own warp rows"** — CH01's
`map032/ev037/p1` and CH02's `map033/ev023/p1` both only match a warp row in the *other*
chapter, and B1_nudge (CH04's own manifest row, claimed by CH05 via
`manifest_chapter_id="CH04"`) matches a warp row that belongs to CH05, not CH04. Several
nudges (e.g. CH01 `map032/ev023/p1`, `map032/ev036/p1`) match **zero** warp landings in the
CH01–CH05 corpus at all — either the source warp is outside this five-chapter sample, or the
nudge fires from something other than a warp this measurement covers.

---

## 7. `item_ball` `spent`/`negative_beat` role, per chapter

| chapter | `item_ball` matches | with a `"spent"` role | without |
|---|---|---|---|
| CH01 | 0 | 0 | 0 |
| CH02 | 7 | 7 | 0 |
| CH03 | 1 | 0 | 1 |
| CH04 | 3 | 3 | 0 |
| CH05 | 4 | 4 | 0 |

CH03's one item ball (`map068/ev018/p0`, cited in `item_ball.py`'s own module docstring as
the motivating single-page instance) has no `"spent"` role — `negative_beat=True` would raise
`ValueError` there (`item_ball.py:262-269`).

---

## 8. Trainer `match.params` keys vs. template keyword names

Every trainer `ArchetypeMatch.params` in CH01–CH05 (21 instances) carries **exactly**
`{"trigger", "phone", "double", "retalk_pages", "rider"}` — the same five names
`trainer_beats` accepts (`trainer.py:329-333`). No instance has an extra key, and none is
missing a key. (`_match_trainer`, `chapter_manifest/archetypes.py:133-163`, always populates
all five.) So this task's own contract — "the five behaviour flags are already in
`match.params`, under the template's own keyword names" — held for every measured instance,
with zero exceptions.

---

## 9. `flavour_npc`: signature + variant distribution

Signature: see §4. The `variant` check (`flavour_npc.py:139-153`) validates a caller-supplied
`variant=` against `match.params["variant"]` (`str(match.params["variant"])`) — one of
`"plain"`/`"toggling"`/`"randomized"` (`_VARIANTS`, line 66) — and raises on disagreement or
an unrecognized value; passing nothing (`variant=None`, the default) skips the check.

CH01–CH05 `flavour_npc` counts and variant distribution:

| chapter | total | plain | randomized | toggling |
|---|---|---|---|---|
| CH01 | 79 | 68 | 3 | 8 |
| CH02 | 3 | 3 | 0 | 0 |
| CH03 | 22 | 18 | 1 | 3 |
| CH04 | 2 | 2 | 0 | 0 |
| CH05 | 0 | 0 | 0 | 0 |

CH05 has zero `flavour_npc` matches, confirming the task brief's "CH05 has no flavour NPC
match" and explaining why no `EXPECTED` row pins its kwargs.

---

## 10. `warp_candidates` data: CH05 warp cells' four neighbours

Each warp row's own event cell (its **trigger** cell, on its own map — not the destination
landing cell) and orthogonal-neighbour walkability, via
`traversal.graph.build_map_graph(map_id).is_walkable`:

| row (event) | cell (x,y) | north | east | south | west |
|---|---|---|---|---|---|
| `map036/ev001` (B1) | (17,40) | walkable | blocked | blocked | blocked |
| `map036/ev002` (B8) | (17,4) | walkable | blocked | walkable | blocked |
| `map037/ev001` (B8 reciprocal) | (16,27) | walkable | blocked | blocked | blocked |
| `map037/ev002` (B11) | (16,5) | blocked | walkable | walkable | walkable |

`map036/ev002`'s two walkable sides (north, south) match the docstring's own account of the
(17,3)/(17,5) one-cell-pocket geometry (`warp.py`'s module docstring / `ch05.py`'s B8
comments, cited in §0's reading).

**`MapGraph.is_walkable` and out-of-bounds** (`traversal/graph.py:157-172`): `is_walkable`
checks `in_bounds` **first** and returns `False` immediately for an out-of-bounds cell — it
never reaches the ledge/stair/collision checks in that case. A cell one step off the map edge
therefore reads as simply "not walkable", indistinguishable in the return value from an
in-bounds wall (both `False`); nothing in `is_walkable`'s contract exposes the distinction.
(This is what `test_warp_candidates_skip_walls_and_edges` exercises with a 3×3 synthetic
graph: the north edge and a west wall both produce the same "absent from the candidate list"
result.)

---

## 11. Q2 data: every kwarg hand-typed in `ch05.py`'s archetype template calls

Restricting to the seven archetype-template calls (`B1`, `B1_nudge`, `B1_in`, `B2`(item),
`B3`(trainer), `B5`(trainer), `B4`(item), `B8_return`, `B8_nudge`, `B8`, `B9`(trainer) — 11
calls total across the 4 templates used), every kwarg typed, and whether it is a value
`EXPECTED`/`archetype_kwargs` would need to reach, is route-derived (excluded from Task 5's
scope), or is neither:

| kwarg (call) | typed value | status |
|---|---|---|
| `mechanism="threshold"` (all warps) | constant | archetype_kwargs candidate — but derived as a corpus-wide constant, not per-row (§3) |
| `direction=`, `return_direction=` (all warps) | e.g. `"DOWN"`/`"UP"` | route-derived (`NOT_SOURCE`) |
| `start_side="dest"` (B1, B8_return) | | **route-derived per `NOT_SOURCE`, but the choice of *which beat* gets `start_side="dest"` vs `"origin"` is a beat-splitting decision `ch05.py`'s module docstring attributes to hand analysis of the CH04→CH05 handoff (`_ROUTE_ENTRY`, `entry_cell`), not to any field on the row or the match.** |
| `round_trip=False` (B1, B8_return) / omitted (B8, B1_in) | | route-derived (`NOT_SOURCE`) |
| `manifest_chapter_id="CH04"` (B1_nudge, B1_in) | | **not covered by `EXPECTED` at all** — `EXPECTED` is built from `classify_manifest(load_chapter_rows("CH05"))` alone, which never sees `map035` rows. `manifest_chapter_id` is how the author tells `find_match` to search CH04's manifest instead of CH05's (`find_match`'s docstring, `warp.py`'s own docstring lines 228-233) — this is cross-chapter row ownership (REDERIVATION_PLAN.md §10 R2/R3), a fact about which chapter's manifest a row lives in, not something derivable from CH05's own `match`/`floors` arguments that Task 5's `archetype_kwargs` receives. |
| `approach_prefer=` (item_ball, trainer calls) | e.g. `"east"` | route-derived (`NOT_SOURCE`) |
| `item=`, `trainer_const=`, `defeat_flag=`, `trigger=`, `phone=`, `double=`, `retalk_pages=`, `rider=`, `negative_beat=`, `from_map_constant=`, `dest_map_constant=` | | all covered by `EXPECTED`/§3 |

**The one hand-typed value structurally outside `EXPECTED`'s reach is
`manifest_chapter_id="CH04"`** on `B1_nudge`/`B1_in` — not because the underlying fact (which
chapter owns `map035/ev001`) is unknowable, but because Task 5's test fixture only exercises
CH05's own manifest rows, and `manifest_chapter_id` decides *which chapter's rows to search in
the first place*, upstream of anything `archetype_kwargs(beat, match, floors, ...)` is handed.

---

## Decisions left to you

- **`mechanism`.** Every measured CH05/CH01–CH05 warp row this task's tests touch uses
  `"threshold"`, and the task brief states this as a corpus-wide fact ("A2's answer"), not
  something read per-row. Whether `archetype_kwargs` should hardcode `"threshold"`, derive it
  from some other signal not measured here, or take it as a caller-supplied constant is open.
- **Reverse trainer lookup.** No existing function does `(name, trainer_type) →
  trainer_const`; only the forward check (`_validate_battle_identity`) exists. §2 gives the
  ambiguity rate (19/263 keys sidecar-wide, 1 hit in CH01–CH05's own battle floors — CH03's
  Richard) for whatever refusal policy you choose.
- **`from_map_constant`/`from_event_id` search scope for `arrival_nudge`.** §6 shows the
  matching warp row is sometimes in the *same* chapter, sometimes in a *different* chapter
  (both directions: a predecessor's row matching a landing in this chapter, and vice versa),
  and sometimes not found in this five-chapter sample at all. Which manifests
  `archetype_kwargs` is allowed to search (just `floors`/`match` as given, or something wider)
  is not fixed by the function signature in the stub.
- **`start_side`/`round_trip`/beat-splitting.** These are `NOT_SOURCE` (route-derived) per the
  test, but §11 shows the actual per-instance choice in `ch05.py` (which beat gets
  `start_side="dest"`, and the three-way B1/B1_nudge/B1_in split) came from hand analysis of
  the chapter handoff, not from any field `archetype_kwargs` receives. Whether that
  reasoning belongs in a later C6 stage, stays hand-authored indefinitely, or needs new data
  plumbed into `adapt.py` is open.
- **`map_constant_fn` success vs. `SLICE_MAP_IDS` membership (Q3).** §5 measured that these
  are two different tables: `map_constant_fn(40)` succeeds (a constant is minted, the map
  JSON is decoded) while `40 not in SLICE_MAP_IDS` (no compiled warp event exists). A
  generator that only checks "did `map_constant_fn` raise" cannot detect the map037/B11 case.
  Which stage should own the `SLICE_MAP_IDS` check — `archetype_kwargs` itself (would need a
  new import/dependency), an upstream stage (`select`/`group`), or the route solver — is not
  decided by anything measured here.
- **Item ball ambiguity/refusal shape.** §1 found zero resolution failures across the whole
  CH01–CH05 corpus, so there's no real-corpus case to calibrate a refusal message against;
  the `ValueError` shapes in `_validate_item_constant`/`item_ball.py:100-105` are the only
  existing precedent.
