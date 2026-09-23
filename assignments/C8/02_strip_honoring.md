# Task 2 — Honouring Stripped Common Events in `beat_floor` (25 points)

## Goal

Make `beat_floor` treat a code-117 call to a **strip-listed** common event as a no-op, the way
`story_state` already does. Today the two packages disagree about what the same command means.

Operator ruling: `REDERIVATION_PLAN.md` §16.3, C8 stage list item **(7)** — "CEs 4/5/6
(GTS/VT/LOBBY) are already in `strip_list.json` … the `$lobbyreset`/`system(...)` refusals exist
only because `story_state`/`beat_floor` inline code 117 without honoring common-event strips, so
the fix is there, not a new strip entry."

`story_state`'s half of that fix landed in C8 stage 4 (commit `bd80c080`). **`beat_floor`'s half
is this task.**

## Learning objectives

- Thread a new optional parameter through a deep call chain without breaking a dozen callers
- Recognise the "default it, don't require it" pattern and when it is safe
- Notice that a *cache* in the chain changes what "optional parameter" means

## The disagreement, concretely

`reference/strip_list.json` lists three whole common events under `common_events`: ids **4, 5,
6** (GTS / VT / LOBBY — Uranium's online features, unportable). A strip-listed common event is
one the ROM will not contain.

- `story_state` inlines 117 **except** for those ids, which it treats as a no-op.
- `beat_floor/walk.py` inlines 117 **unconditionally** — it parses the CE's command tree and
  attributes every assertion inside it back to the caller's `list_index`.

So for the same row, `story_state` says "this call does nothing" and `beat_floor` says "this
call does everything CE 6 does". Downstream, `beat_gen` consumes both.

The visible symptom: CH03 currently carries `unclassified_condition` refusals like

```
map068/ev009/p0: no family matches: '!$lobbyreset'
```

`$lobbyreset` is a global that only exists inside the stripped LOBBY common event. The floor is
refusing to classify a condition that, in the ROM, will never be reached.

## The source of truth you must reuse

| Thing | Where | Signature |
|---|---|---|
| The strip-list loader | `ruby_subset/search.py:161` | `load_stripped_ce_ids(reference_dir: Path) -> frozenset[int]` |
| The cached wrapper | `story_state/scope_search.py:281` | `stripped_ce_ids_for(reference_dir: Path) -> frozenset[int]` |

**Reuse `stripped_ce_ids_for`.** It caches per `reference/` directory, which matters here:
`floor_for_map` runs per map, and re-reading `strip_list.json` once per row would be silly.
Do **not** add a third loader, and do **not** read `strip_list.json` directly.

Note `load_stripped_ce_ids` itself already delegates to
`conversion_agent.orchestrator._load_strip_list` rather than reading the JSON — that is the §4.3
chain you are joining, not starting.

## The defaulting pattern to copy

`story_state/extract.py:732` shows exactly the shape wanted:

```python
def extract_map(
    map_id: int,
    map_data: dict[str, Any],
    *,
    common_events: list[dict[str, Any]],
    switch_labels: dict[int, str],
    stripped_ce_ids: frozenset[int] | None = None,
) -> dict[str, "RowState"]:
```

with, in the body:

```python
sce = stripped_ce_ids if stripped_ce_ids is not None else stripped_ce_ids_for(_default_reference_dir())
```

The point of `None` rather than a bare default is that **a caller who has not been updated still
gets strip-honouring for free**, while a test can pass an explicit set (including an empty one)
to pin behaviour precisely. Copy this exactly.

## The call chain you must thread

Six deep, from CLI to the inlining site. All in `src/rpg2gba/beat_floor/`:

| # | Function | File:line |
|---|---|---|
| 1 | `report` (CLI) | `__main__.py:73` |
| 2 | `floor_for_chapter` | `walk.py:737` |
| 3 | `floor_for_map` | `walk.py:665` |
| 4 | `_build_row_floor` | `walk.py:603` |
| 5 | `_walk_commands` | `walk.py:374` |
| 6 | `_walk_common_event_call` | `walk.py:453` ← **the site** |

### ⚠️ The trap: there is a second entry point, and it is cached

`beat_floor/lookup.py:65` has:

```python
@cache
def floor_for_map_cached(build_dir: str, map_id: int) -> dict[str, RowFloor]:
```

which calls `floor_for_map` directly, bypassing `floor_for_chapter` entirely. It feeds
`floor_for_row`. Two consequences:

1. It needs the same treatment, or half the pipeline keeps the old behaviour.
2. `@cache` keys on the arguments. If you add a `frozenset` parameter to a `@cache`d function,
   think about whether it is hashable (it is), whether it *should* be part of the cache key, and
   what happens to a test that calls it twice with different strip sets. **Q2 asks.**

## Requirements

### R1 — Thread the parameter

Add `stripped_ce_ids: frozenset[int] | None = None` to `floor_for_chapter` and `floor_for_map`
as a keyword-only argument, defaulting via `stripped_ce_ids_for` exactly as `extract_map` does.
Thread it down to `_walk_common_event_call`. Internal helpers (4, 5, 6) take it positionally or
keyword as you prefer, but **not** optionally — an internal function silently defaulting is how
the two halves drifted in the first place.

### R2 — The no-op

In `_walk_common_event_call`, a `ce_id` in the stripped set produces `((), ())` — no assertions,
no refusals — and does **not** recurse. Check this *before* the missing-CE lookup: a stripped CE
may legitimately be absent from `common_events.json`, and you do not want a `missing_common_event`
refusal for something you are deliberately not running.

Order of checks, therefore: malformed → cycle → **stripped** → missing → inline.

Be honest with yourself about *why* that ordering is required, because the corpus does not
prove it: CEs 4, 5 and 6 are all present in `common_events.json` today, with 219 / 204 / 185
commands respectively. So the real corpus only ever exercises "stripped **and** present". The
ordering is a **defensive** requirement — a stripped CE is one the ROM will not contain, and
nothing guarantees a future strip entry stays present in the dump. Your test pins it; the data
does not. Say so in Q1 rather than claiming the corpus forced it.

### R3 — The cached entry point

Give `floor_for_map_cached` / `floor_for_row` the same behaviour. You may decide the cache key
question either way; document it.

The tests call these **by keyword** (`stripped_ce_ids=...`), deliberately, so that they pin the
behaviour without pinning your parameter order or your cache-key decision. Accept a keyword
argument of that name and the rest is yours.

### R4 — Do not touch `story_state`

Its half is done. If you find yourself editing `extract.py`, stop and re-read.

## Measured acceptance

| Measurement | Value |
|---|---|
| Strip-listed common events | ids 4, 5, 6 |
| Code-117 calls to one of them, corpus-wide | **36**, across 11 maps |
| …of those, in **staged** chapters (INTRO, CH01–CH05) | **3** |
| Where those 3 are | `Map068` (CH03): `ev009/p0`, `ev011/p0`, `ev013/p0`, calling CE 4, 5, 6 respectively |

**So the visible effect of this task is small and entirely inside CH03.** That is expected and
is not a reason to widen the change. The other 33 sites are on maps that stage in later
chapters; you are fixing them ahead of time, which is why the test suite pins corpus-wide
behaviour and not just CH03's three.

Expected movement: CH03's `unclassified_condition` count drops (it is 4 today, and at least the
`!$lobbyreset` one is a stripped-CE artefact). **Report the exact before/after in your commit
message.** If a refusal you expected to vanish does not, find out why before "fixing" it — it
may be a genuine refusal that merely mentions `$lobbyreset`.

## Hints

- The three CH03 sites are all `list[0]` — the *first* command of their page. That makes them
  easy to eyeball in the JSON: `output/uranium-build/maps/Map068.json`, events 9, 11, 13.
- The three CH03 sites inline **219, 204 and 185 commands** respectively today (CE 4 / 5 / 6).
  That is the size of the over-assertion you are removing: three rows currently carry the floor
  of Uranium's entire online-lobby UI. Eyeball one before and after — it is the clearest way to
  see that the change did what you think.
- A `frozenset()` (empty, not `None`) is the right way for a test to say "strip nothing". Make
  sure your defaulting logic distinguishes it from `None`. This is the single most likely bug in
  this task.

## Tests

`tests/test_beat_floor_strip_honoring.py`: a synthetic stripped 117 emits nothing; a
non-stripped 117 still inlines (the existing behaviour must not regress); an explicit
`frozenset()` disables stripping; a stripped **and missing** CE produces no refusal; the
cached entry point honours it too; and a real-data test pinning CH03's three `Map068` sites.

The existing `tests/test_beat_floor_walk.py` 117-inlining tests (from line ~192) must still
pass unchanged — if you have to edit them, your default is wrong.

## Questions (commit message)

1. Why must the stripped check come *before* the missing-CE check rather than after — given
   that today's corpus never hits the case that ordering protects?
2. What did you do about `floor_for_map_cached`'s `@cache` key, and what breaks under the other
   choice?
3. The real corpus only exercises one of your two new paths (stripped-and-present). Why is the
   other one worth implementing and testing anyway?
4. CH03's `unclassified_condition` before and after. Did every one of them clear? If not, which
   survived and why is that correct?
