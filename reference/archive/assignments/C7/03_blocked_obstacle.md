# Task 3 — The `blocked_obstacle` Floor Kind (40 points)

## Goal

Add a new assertion kind, `blocked_obstacle`, to the beat floor. A row gets one when its
**own commands** are gated on a field move (Rock Smash, Strength). The assertion means:

> *Without `<capability>`, interacting with this event leaves it in place (no erase, no state
> write), and its tile at `(x, y)` stays impassable.*

This replaces the rowless "you can't smash this rock yet" hand beats (`CH01:N4`, `CH02:N2`,
`CH03:N7`, `CH04:B6`) with a source-derived fact the generator (C6) can emit for every
obstacle in every chapter.

Operator ruling: `REDERIVATION_PLAN.md` "DECIDED 2026-09-18" table, "Field-move obstacles" row.

## Learning objectives

- Extend a closed vocabulary (`Literal` type) and a pipeline that consumes it
- Reuse an existing single source of truth instead of writing a second detector (§4.3)
- Distinguish two facts that look alike in the data: *this event is an obstacle* vs *this
  event is behind an obstacle*

## Orientation — the package in one table

| Module | Role |
|---|---|
| `beat_floor/assertion.py` | the data contract: `AssertionKind`, `FloorAssertion`, `RowFloor`, `OFFLINE_KINDS`, `make_params` |
| `beat_floor/walk.py` | the walker; `floor_for_map` (line ~663) builds every row's `RowFloor` for a map |
| `beat_floor/script.py` / `condition.py` | per-call-head / per-condition-family extractors |
| `beat_floor/terrain.py` | **your precedent**: row-level kinds (`seam_crossing`, `stair_crossing`) with `list_index=-1, code=None` |
| `beat_floor/coverage.py` | `assertion_key`, `covers`, `contradicts`: generic, **needs no changes** |
| `beat_floor/__main__.py` | `report --chapter CHnn` CLI: generic, **needs no changes** |

The core record (from `assertion.py`):

```python
@dataclass(frozen=True)
class FloorAssertion:
    row_id: str
    kind: AssertionKind
    list_index: int      # position in the owning page's raw `list`; -1 for row-level kinds
    code: int | None     # source command code; None for row-level kinds
    params: Params = ()
    tag: AssertionTag = "flow"
    offline: bool = field(init=False)
```

## The single source of truth you must reuse

The manifest generator already decides which rows need a capability.
`src/rpg2gba/chapter_manifest/generator.py`:

```python
_HEAD_REQUIRES: dict[str, str] = {        # line 218
    "pbRockSmash": "rock_smash",
    "pbRockSmashRandomEncounter": "rock_smash",
    "pbPushThisBoulder": "strength",
}

def _extract_page(commands) -> dict[str, Any]:   # line 626
    ...  # returns {"requires": ("rock_smash",), "script_heads": ..., ...}
```

**Call `_extract_page(scope.commands)["requires"]`. Don't write your own head scan.**
`terrain.py` already imports private generator helpers (`_generate_terrain_rows`) for the same
reason: if two detectors exist, they can silently disagree.

### ⚠️ The trap

A manifest row's `requires` field is **not** the same thing. Look at `_generate_page_rows`
(generator.py ~line 1000):

```python
requires = tuple(sorted(set(extracted["requires"]) | set(reach_requires)))
```

`reach_requires` is added for any event that is *reachable only past* an obstacle, such as an
NPC standing behind a rock. Those rows can also end up dispositioned `blocked:rock_smash`, but
they are **not** obstacles, and asserting that the NPC's tile is impassable would be false.
Use only the head-derived half. Q1 asks you to explain this.

## Requirements

### R1 — Register the kind

In `assertion.py`:
- Add `"blocked_obstacle"` to `AssertionKind`, under the row-level section, with a params
  comment: `# params: x, y, capability`.
- **Don't** add it to `OFFLINE_KINDS`. Impassability needs the emulator. Update the
  `OFFLINE_KINDS` docstring, which lists the ROM-only kinds.

### R2 — The extractor: new module `beat_floor/obstacle.py`

```python
"""`blocked_obstacle`: a row whose own commands are gated on a field move
(REDERIVATION_PLAN.md §16.3 C7 residue ruling, 2026-09-18). ..."""

def obstacle_assertions(
    row_id: str, event: dict[str, Any], commands: list[dict[str, Any]],
) -> tuple[tuple[FloorAssertion, ...], tuple[FloorRefusal, ...]]:
    """Zero or one `blocked_obstacle` assertion for one scope.

    - no capability head in `commands`  -> ((), ())
    - exactly one capability            -> one assertion, list_index -1, code None,
                                           params x, y (the event's cell), capability;
                                           tag "position"
    - more than one capability          -> refuse loud (reason
                                           "obstacle_multiple_capabilities")
    """
```

Notes:
- The cell is `event["x"], event["y"]`. If either is missing, **refuse**
  (`"obstacle_missing_cell"`). Don't default to `(0, 0)`.
- Build params with `make_params(...)` so they're canonical and hashable.
- Look at `terrain.py:175–229` (`stair_floors_for_map`) for the refusal shape.

### R3 — Wire it into `floor_for_map`

In `walk.py`'s scope loop (around line 700), after `_build_row_floor(...)` returns, merge
your assertions and refusals into that row's floor. `RowFloor` is frozen, so use
`dataclasses.replace`:

```python
floor = _build_row_floor(...)
extra, refused = obstacle_assertions(scope.row_id, event, scope.commands)
if extra or refused:
    floor = replace(
        floor,
        assertions=floor.assertions | frozenset(extra),
        refusals=floor.refusals + refused,
    )
result[scope.row_id] = floor
```

**Leave the existing `visual` placeholders alone** (`condition.py` `_extract_pb_rock_smash`,
`script.py` `pbPushThisBoulder`). They describe what happens *with* the capability. Your kind
describes what happens *without* it. Both are true.

### R4 — Branch arms

`iter_page_scopes` yields the page trunk and then each branch arm as its own row. The
`pbRockSmash` condition sits on the trunk. Find out, using real data, whether the head shows
up in the trunk's `scope.commands`, an arm's, or both. Then make sure **exactly one** row per
obstacle page gets the assertion. Record what you found in Q2.

#### Hints for R4

- Before writing any filter, **measure**. For one real rock (`Map033.json` ev29 is the simplest
  one), loop over `iter_page_scopes(33, event, 0, page)` (it lives in
  `chapter_manifest/generator.py`) and print each `scope.row_id` next to
  `_extract_page(scope.commands)["requires"]`. Then do the same for map032 ev14, which has
  nested arms. Write down what you see *before* deciding anything, because Q2 wants the
  observation, not the fix.
- Once you know which scopes report the capability, you have two broad choices: filter in
  `floor_for_map` (only some scopes get the call), or filter inside `obstacle_assertions`
  (it gets called for every scope and declines for some). Which keeps `obstacle_assertions`
  a pure "these commands → this assertion" function? Which one makes the unit tests in the
  "pure function" section keep making sense?
- `chapter_manifest.schema.parse_row_id(row_id).kind` tells you what kind a row is. That's
  sturdier than string-matching on `"/b"`.
- Think about a boulder too: it has a single scope. Does your rule still pick it?

### R5 — Real-data cross-check (script, not a test)

> **Correction, 2026-09-19:** the build directory is `output/uranium-build/`, not `output/`.
> The maps are at `output/uranium-build/maps/MapNNN.json`. This section and the fixture note
> below used to say `output/`.

Write `scripts/check_blocked_obstacles.py` (mark it a one-off in its docstring). For each of
CH01–CH05 it should:
1. compute `floor_for_chapter(ch, build_dir=Path("output/uranium-build"))`,
2. load `reference/manifests/CHnn.dispositions.json`,
3. for every row dispositioned `blocked:<cap>`, report whether its floor has a matching
   `blocked_obstacle` (same capability).

Expected output: every true obstacle matches. Any `blocked:` row **without** one should be a
behind-an-obstacle row (the trap above). List those in your commit message. A spot check to
anchor you: `CH01.dispositions.json` says `map032/ev014/p0` is a rock at **(65, 45)**, so your
floor should say `x=65, y=45, capability="rock_smash"`.

This needs `output/` populated. If it isn't, generate it with the normal pipeline commands
rather than skipping the check.

## Tests — `tests/test_beat_floor_obstacle.py`

**Implemented for you as of 2026-09-19, and skipped.** Delete the `pytestmark` line when you
start. The stub `src/rpg2gba/beat_floor/obstacle.py` is also in place (signature and
docstring, body raises `NotImplementedError`).

> **Correction, 2026-09-19: the fixture this section used to show was wrong.** It had
> `pbEraseThisEvent` alone in the arm. A real rock (`output/uranium-build/maps/Map033.json`
> ev29 p0) has **two** capability calls: the trunk's `111 Kernel.pbRockSmash` condition *and*
> a `355 Kernel.pbRockSmashRandomEncounter` inside the then-arm. That second call is what
> makes R4 a real problem rather than a hypothetical one. The test file's `ROCK_PAGE` is cut
> down from the real page (the move route is dropped). It's still worth opening the real page
> and comparing. Boulders (`Map031.json` ev1) are a single `355 pbPushThisBoulder` on a
> player-touch page.

The tests go through the **real walker** (`walk.floor_for_map` on a one-event synthetic map),
so they only pass once both R2 (the extractor) and R3 (the wiring) are done. The three
"pure function" tests call `obstacle_assertions` directly, so you can get those green first.

| Test | Asserts | Needs |
|---|---|---|
| `test_pure_function_no_capability` | a text page → `((), ())` | R2 |
| `test_multiple_capabilities_refuses` | rock + boulder heads in one scope → one `obstacle_multiple_capabilities` refusal, no assertion | R2 |
| `test_missing_y_alone_refuses` | `x` present, `y` absent → `obstacle_missing_cell` | R2 |
| `test_cell_zero_is_a_real_cell` | `(0, 0)` is a real cell, not "missing" | R2 |
| `test_rock_smash_page_gets_obstacle` | exactly one across the map; `list_index -1`, `code None`, tag `position`, params `{x, y, capability: "rock_smash"}` built with `make_params` | R2+R3+R4 |
| `test_strength_boulder_gets_obstacle` | `pbPushThisBoulder` → `"strength"`, on the trunk row | R2+R3 |
| `test_plain_npc_gets_none` | a text page gets none | R3 |
| `test_visual_placeholder_kept` | `visual` and `blocked_obstacle` both present | R3 |
| `test_missing_cell_refuses` | no `x`/`y` → exactly one `obstacle_missing_cell` refusal on the map, and no assertion | R3+R4 |
| `test_one_row_per_obstacle_page` | trunk + arms carry exactly one between them | **R4** |
| `test_obstacle_row_keeps_existing_assertions` | the merge adds to `trigger`/`completes`, it doesn't replace them | R3 |
| `test_not_offline` | not in `OFFLINE_KINDS`, and the row isn't `offline_eligible` | R1+R3 |
| `test_covers_roundtrip` | `covers(a, a)`; a different `capability` `contradicts` | R2+R3 |

```bash
.venv/bin/pytest tests/test_beat_floor_obstacle.py -q -k "pure or multiple or missing_y or cell_zero"   # R2 alone
.venv/bin/pytest tests/test_beat_floor_obstacle.py -q                                                 # everything
.venv/bin/pytest tests/test_beat_floor_*.py -q                                                        # regression
```

If you wire it up and see `test_one_row_per_obstacle_page` fail with a list of two or three
assertions, **that's R4**, not a test bug. Read the row ids in the failure message; they're
the answer to Q2's first half.

### Hints for R2

- The whole detector is one expression you're told to reuse. Before writing anything, call it
  from a REPL on `ROCK_PAGE`, on the arm's commands alone, and on `BOULDER_PAGE`, and look at
  what comes back (type, order, duplicates?). You'll need `len(...)` on it, so ask whether the
  same capability can appear twice.
- There are three outcomes plus one refusal path. Write them as early returns, in the order
  the docstring lists them. Which check has to come **before** the cell check, so a text
  page with no `x` doesn't refuse?
- "Missing" means the key is absent, not that the value is falsy (`test_cell_zero_is_a_real_cell`).
- `FloorRefusal` is positional-friendly, but use keywords. `terrain.py`'s refusals are the
  house style: a stable `reason` id plus a `detail` that cites what was seen.
- `_extract_page` is private to the generator. Importing it is the deliberate §4.3 choice
  here (see `terrain.py`'s precedent). Add a short comment saying *why*, so the next reader
  doesn't "fix" it by writing a second detector.
- **Import cycles:** `walk.py` imports from `chapter_manifest.generator` at module level
  already, so a module-level import in `obstacle.py` should be fine. If you do hit a cycle,
  the error message names the import chain, so read it before reaching for a local import.

### Hints for R3

- `dataclasses.replace` on a frozen dataclass returns a **new** object. The snippet in R3
  is nearly complete. The piece it leaves to you is R4's filter.
- `refusals` is a tuple, `assertions` is a frozenset. That's why one uses `+` and the other
  uses `|`.

Also run the existing `tests/test_beat_floor_*.py`. They must stay green. If one breaks,
decide whether the old expectation or your change is wrong, and explain which in the commit.

## Questions (commit message)

1. Explain the reach-requires trap in your own words, and name one real row from R5's output
   that would have been mis-tagged if you'd used the manifest's `requires`.
2. R4: where does the capability head live, trunk or arm? How did you guarantee one
   assertion per obstacle?
3. C6 will group these assertions into beats by *(map, capability)*. Why does it still matter
   that each assertion carries its own `row_id`?
