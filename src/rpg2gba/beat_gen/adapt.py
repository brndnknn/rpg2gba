"""Stage 5: template keyword arguments (C6 Task 5).

Two kinds of kwarg, from two sources:

- SOURCE-derived (`archetype_kwargs`): what the RMXP data says, e.g. the
  item a ball grants, the trainer an event battles, where a warp lands. The
  oracle is the hand-written `playtest/chapters/ch05.py`, whose author
  typed these same values by hand: the generator must arrive at the same
  answer without a person.
- ROUTE-derived (`route_kwargs`): what the solver picked, e.g. the side a
  beat approaches from, and for a warp the press direction that follows
  from it (C6 plan A2: "direction and return_direction are the solver's
  cheapest walkable approach side").

`warp_candidates` closes a gap between the two. The solver can only pick a
side from candidates, and `routing.locations.cell_for_row` gives a warp row
none (the player stands ON a warp), so this derives them.

STATUS: stub (`assignments/C6/05_adapt.md`).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import Kwargs, PlannedBeat
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch
from rpg2gba.routing.locations import ApproachCandidate
from rpg2gba.traversal.graph import Cell, MapGraph

MapConstantFn = Callable[[int], str]


def archetype_kwargs(
    beat: PlannedBeat,
    match: ArchetypeMatch,
    floors: Mapping[str, RowFloor],
    *,
    map_constant_fn: MapConstantFn,
) -> Kwargs:
    """The source-derived kwargs for one archetype beat (sorted, via
    `make_kwargs`). Only keywords the template accepts. Raises `ValueError`
    naming the row if a value can't be derived (a floor without the
    expected assertion, an unknown item, an unmintable trainer)."""
    raise NotImplementedError


def warp_candidates(cell: Cell, graph: MapGraph) -> tuple[ApproachCandidate, ...]:
    """Every side a warp cell can be stepped onto from: one candidate per
    walkable orthogonal neighbour, `side` naming where the player stands
    ("north" = the cell above). In N, E, S, W order."""
    raise NotImplementedError


def route_kwargs(template: str, side: str) -> Kwargs:
    """The kwargs a solver pick turns into for `template`. For `warp`: the
    press direction (standing south of the tile, you press UP), a round trip
    and the reverse press. For every other template: `approach_prefer`.
    Raises `ValueError` on an unknown side."""
    raise NotImplementedError
