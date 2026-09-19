"""The generic template: the floor for every row no archetype claims
(R11; REDERIVATION_PLAN.md §16.3 C6, C6_GENERATOR_PLAN.md part #4).

Four registration functions, one per `beat_gen.plan.TemplateName` this
module serves:

- `generic_beat`  -- page and branch-arm rows: walk up, interact, then
                     check the row's floor step by step
- `obstacle_beat` -- `blocked_obstacle` rows of one (map, capability)
- `stair_beat`    -- one staircase's terrain rows, crossed and crossed back (A3)
- `seam_beat`     -- one seam row, crossed at the solver's picked cell (A1)

The design splits WHAT to check from HOW to drive the emulator:

- `steps_for(floor)` is pure: the ordered checks a row's floor implies.
  Offline-testable.
- `STEP_HANDLERS[kind]` drives the emulator for one step. Only a ROM walk
  (P11) can exercise it.

Honesty (C5 ruling (c)): a template declares only the kinds its body
executes. Here that is the invariant `set(STEP_HANDLERS) ==
GENERIC_EXECUTED_KINDS`, and a test pins it, so a kind can't be declared
without a handler that checks it.

STATUS: stub (`assignments/C6/07_generic.md`).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rpg2gba.beat_floor.assertion import Params, RowFloor
from rpg2gba.playtest.archetypes import FloorLookup
from rpg2gba.playtest.chapter import ChapterBuilder

if TYPE_CHECKING:  # runtime import is lazy so this module works without mGBA bindings
    from rpg2gba.playtest.emulator import Emulator

# Which floor kinds the generic body checks. Yours to decide (Task 7, R1).
GENERIC_EXECUTED_KINDS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Step:
    """One check the body performs, in execution order."""

    row_id: str
    kind: str
    list_index: int
    params: Params


StepHandler = Callable[["Emulator", str, Step], None]
"""(emu, beat_name, step) -> None; raises ScenarioError on a mismatch."""

STEP_HANDLERS: dict[str, StepHandler] = {}


def steps_for(floor: RowFloor) -> tuple[Step, ...]:
    """The ordered checks for one row: only `GENERIC_EXECUTED_KINDS`;
    `trigger` first, `completes` last, everything else by `list_index`
    (ties broken by kind, then params). Raises `ValueError` if the floor
    is refused."""
    raise NotImplementedError


def generic_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    group: str | None = None,
    approach_prefer: str | None = None,
    skip_claimed: bool = False,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one generic beat claiming `rows` (a page row and/or its
    arms). With `skip_claimed=True`, rows some earlier beat in `builder`
    already claims are dropped first, and if none remain nothing is
    registered. Fails loud (`ValueError`) on a refused floor."""
    raise NotImplementedError


def obstacle_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    capability: str,
    group: str | None = None,
    approach_prefer: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one beat asserting every `blocked_obstacle` in `rows`
    (all on one map, all needing `capability`). Fails loud if a row's floor
    has no `blocked_obstacle`, or one for a different capability."""
    raise NotImplementedError


def stair_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    group: str | None = None,
    approach_prefer: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one round-trip staircase beat for `rows` (terrain rows of
    one staircase). Declares their `stair_crossing` assertions."""
    raise NotImplementedError


def seam_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    beat_name: str,
    rows: Sequence[str],
    group: str | None = None,
    approach_prefer: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one seam-crossing beat for a single seam row. Declares its
    `seam_crossing` assertion."""
    raise NotImplementedError
