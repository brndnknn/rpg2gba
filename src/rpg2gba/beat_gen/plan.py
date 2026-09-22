"""The beat generator's data contract (REDERIVATION_PLAN.md §16.3 C6).

C6 turns a chapter's manifest rows into a GENERATED playtest module. The
pipeline, one module per stage:

    select.py   manifest rows + story verdicts + floors -> Selection
    group.py    Selection + archetype matches           -> PlannedBeats
    seam.py     a seam row + two MapGraphs              -> legal crossings
    locate.py   PlannedBeats -> location records -> solved route -> order
    adapt.py    archetype match + floors + route pick   -> template kwargs
    emit.py     ChapterPlan                             -> Python source
    review.py   ChapterPlan                             -> CHnn.review.md
    __main__.py the `generate` CLI tying it together

This module holds only the records every stage shares, like
`beat_floor/assertion.py` does for the floor. It carries no logic beyond
validation. It is complete; the stage modules are the assignment
(`assignments/C6/`).

Determinism is part of the contract (§4.2, R7 "byte-identical on re-run"):
every tuple here is in a defined order, and `kwargs` is sorted by key, so two
runs over the same inputs build equal plans and emit identical bytes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.routing.plan import RoutePlan
from rpg2gba.story_state.model import OrderDependentKey

TemplateName = Literal[
    # the five archetype templates (`playtest/archetypes/`)
    "warp", "arrival_nudge", "item_ball", "trainer", "flavour_npc",
    # the generic template (Task 6), for every row no archetype claims
    "generic",
    # row-level kinds, each with its own beat shape
    "obstacle",   # blocked_obstacle rows grouped by (map, capability)
    "stair",      # one staircase's terrain rows, crossed both ways (A3)
    "seam",       # one connections.json seam row (A1)
    # travel between beats (C6 part two, `continuity.py`): crosses warps to
    # reach the next beat's map; claims and declares nothing
    "transit",
]

ARCHETYPE_TEMPLATES: frozenset[str] = frozenset(
    {"warp", "arrival_nudge", "item_ball", "trainer", "flavour_npc"})

Blocker = Literal["#109", "C8", "story-state", "floor", "cell"]
"""The named upstream blocker a refusal waits on (C6 plan, B2). `#109` is the
text-normalisation gap; `C8` is the Ruby-subset interpreter; `story-state` is
an outcome-table or modelling gap in `story_state/`; `floor` is any other
floor refusal (stairs, obstacles); `cell` is "no location could be derived"."""

BLOCKERS: frozenset[str] = frozenset({"#109", "C8", "story-state", "floor", "cell"})

Kwargs = tuple[tuple[str, Any], ...]


def make_kwargs(**values: Any) -> Kwargs:
    """Canonical template kwargs: sorted by key, lists turned into tuples.
    Same shape as `beat_floor.assertion.make_params`."""
    return tuple(sorted(
        (k, tuple(v) if isinstance(v, list) else v) for k, v in values.items()))


@dataclass(frozen=True)
class Refusal:
    """A row the generator cannot produce a beat for. The chapter stays red
    until the blocker is fixed upstream (R7)."""

    row_id: str
    blocker: Blocker
    reason: str      # the stable snake_case id from the source of the refusal
    detail: str      # human-readable, cites what was seen

    def __post_init__(self) -> None:
        if self.blocker not in BLOCKERS:
            raise ValueError(f"{self.row_id}: unknown blocker {self.blocker!r}")


@dataclass(frozen=True)
class Elsewhere:
    """A manifest row this chapter does not walk: the story model places it
    in another chapter (`later`) or in none (`unreachable`), or it sits
    behind a field-move obstacle the chapter can't pass (`blocked`: the row
    `requires` a capability and is not itself the obstacle), or it belongs
    to a boundary event the successor opens (`boundary`, §10 R2/R3; added
    in C6 part two, `beat_gen/boundary.py`)."""

    row_id: str
    status: Literal["later", "unreachable", "blocked", "boundary"]
    owner: str | None = None             # the owning chapter for `later`/`boundary`, else None
    requires: tuple[str, ...] = ()       # the capabilities, for `blocked`


@dataclass(frozen=True)
class Selection:
    """Task 1's output. Every manifest row lands in exactly one of the
    three, in manifest order within each."""

    owned: tuple[ManifestRow, ...]
    refusals: tuple[Refusal, ...]
    elsewhere: tuple[Elsewhere, ...]


@dataclass(frozen=True)
class PlannedBeat:
    """One template call in the generated module.

    `name` is derived from the rows, never from an order or a counter, so a
    beat keeps its name when the route changes (Task 2's naming rule).
    `group` is the route-solver stop this beat belongs to; beats sharing a
    group are emitted contiguously. `kwargs` are the template's keyword
    arguments EXCEPT the builder, `chapter_id` and the name keyword, which
    the emitter supplies (`emit.TEMPLATE_CALLS`).
    """

    name: str
    template: TemplateName
    map_id: int
    rows: tuple[str, ...]
    group: str
    kwargs: Kwargs = ()

    def __post_init__(self) -> None:
        if self.template == "transit":
            if self.rows:
                raise ValueError(f"transit beat {self.name!r} must claim no rows")
        elif not self.rows:
            raise ValueError(f"beat {self.name!r} claims no rows")
        keys = [k for k, _ in self.kwargs]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError(
                f"beat {self.name!r}: kwargs must be sorted and unique "
                f"(use make_kwargs), got {keys}")

    def kwarg(self, name: str) -> Any:
        return dict(self.kwargs)[name]


@dataclass(frozen=True)
class ChapterPlan:
    """Everything the emitter and the review doc need, fully decided."""

    chapter_id: str
    predecessor: str | None
    beats: tuple[PlannedBeat, ...]            # solved order (Task 4)
    refusals: tuple[Refusal, ...] = ()
    elsewhere: tuple[Elsewhere, ...] = ()
    order_dependent: tuple[OrderDependentKey, ...] = ()
    route: RoutePlan | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        names = [b.name for b in self.beats]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"{self.chapter_id}: duplicate beat names {dupes}")
