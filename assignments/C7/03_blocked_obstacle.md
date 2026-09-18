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

### R5 — Real-data cross-check (script, not a test)

Write `scripts/check_blocked_obstacles.py` (mark it a one-off in its docstring). For each of
CH01–CH05 it should:
1. compute `floor_for_chapter(ch, build_dir=Path("output"))`,
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

Build synthetic maps the way `tests/test_beat_floor_walk.py:22` does. **Add `x`/`y` to the
event dict**, because the existing helper leaves them out. A Rock Smash page looks like this:

```python
ROCK_PAGE = [
    {"code": 111, "indent": 0, "parameters": [12, "Kernel.pbRockSmash"]},
    {"code": 355, "indent": 1, "parameters": ["pbEraseThisEvent"]},
    {"code": 0,   "indent": 1, "parameters": []},
    {"code": 412, "indent": 0, "parameters": []},
    {"code": 0,   "indent": 0, "parameters": []},
]
```

*(Verify this shape against a real rock page in `output/maps/Map032.json` before you trust
it. That verification is part of the assignment.)*

| Test | Asserts |
|---|---|
| `test_rock_smash_page_gets_obstacle` | one `blocked_obstacle`; `list_index == -1`; `code is None`; params `{x, y, capability: "rock_smash"}` |
| `test_strength_boulder_gets_obstacle` | `pbPushThisBoulder` → `capability == "strength"` |
| `test_plain_npc_gets_none` | a text-only page has no `blocked_obstacle` |
| `test_visual_placeholder_kept` | the rock page still carries its `visual` assertion |
| `test_missing_cell_refuses` | event without `x` → refusal `obstacle_missing_cell`, no assertion |
| `test_one_row_per_obstacle_page` | across trunk + arms, exactly one row carries the kind (R4) |
| `test_not_offline` | `"blocked_obstacle" not in OFFLINE_KINDS`, and such a row is not `offline_eligible` |
| `test_covers_roundtrip` | `coverage.covers(a, a)` is true; changing `capability` makes `contradicts` true |

Also run the existing `tests/test_beat_floor_*.py`. They must stay green. If one breaks,
decide whether the old expectation or your change is wrong, and explain which in the commit.

## Questions (commit message)

1. Explain the reach-requires trap in your own words, and name one real row from R5's output
   that would have been mis-tagged if you'd used the manifest's `requires`.
2. R4: where does the capability head live, trunk or arm? How did you guarantee one
   assertion per obstacle?
3. C6 will group these assertions into beats by *(map, capability)*. Why does it still matter
   that each assertion carries its own `row_id`?
