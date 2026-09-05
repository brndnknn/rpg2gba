"""The `warp` archetype beat template.

`ManifestRow` cannot distinguish a door from an edge threshold from an
arrow warp (task brief) -- the code-201 destination that would settle it is
not on the row (`chapter_manifest.schema.ManifestRow` carries no code-201
target field) -- so `mechanism` is a required, explicit author parameter,
never inferred. What IS derived: the trigger cell (`cells.warp_cell`), the
arrival cell (`cells.arrival_cell`), and (optionally) the expected arrival
facing/BGM, all from this build's own staged output, never a literal.

`assert_facing=True`/`assert_bgm=True` cover the door+facing+BGM triplet
`ch03.py` repeats three times by hand (task brief) -- optional here because
not every warp instance has a meaningful facing/BGM claim to make (an
interior door where the map header's music never changes, for instance).

`round_trip=True` restores the "cross in, cross back, cross in again"
convention `CH05.dispositions.json` (2026-09-04) recorded for a
hand-written module this template replaced (task brief) -- the operator's
decision is that this idiom belongs in the template itself, not
hand-written back into a chapter, so every future warp beat gets it for
free. The reciprocal (return) leg's cells are DERIVED, same discipline as
the forward leg: `cells.warp_cell(dest_map_constant, to=map_constant)` for
the return trigger, `cells.arrival_cell(map_constant, from_map=
dest_map_constant)` for the return landing -- never a coordinate literal,
and it fails loud (propagating `cells.py`'s own precise zero/one/many
errors) if the reciprocal can't be found. The one thing that is NOT
derivable from the graph is which way the reciprocal is crossed --
`MapGraph.warp_exits` records a destination cell, not a mechanism/press
direction (same gap that makes `mechanism`/`direction` explicit params
above) -- so `return_direction` is a second explicit parameter, required
whenever the reciprocal needs one (`mechanism` in `{"threshold", "arrow"}`).
It is genuinely not always equal to `direction`: CH05's B1 crosses out
DOWN and back UP (an ordinary opposite-facing pair), while its B8 crosses
both directions DOWN (a cave staircase idiom where both floors' transition
tiles are entered by pressing down) -- see `warp.py`'s own test coverage.
`mechanism` itself is assumed shared by both legs (true of every instance
in this corpus so far); a warp whose reciprocal uses a *different*
mechanism has no representation here yet.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from .. import assertions
from ..cells import arrival_cell, warp_cell
from . import find_match, map_uranium_id

if TYPE_CHECKING:  # runtime import is lazy so this module works without bindings
    from ...chapter_manifest.schema import ManifestRow
    from ..chapter import ChapterBuilder
    from ..emulator import Emulator

logger = logging.getLogger(__name__)

Mechanism = Literal["door", "threshold", "arrow"]
_MECHANISMS: frozenset[str] = frozenset({"door", "threshold", "arrow"})

# Same convention `assertions.cross_arrow_warp` uses internally (private
# `_ARROW_APPROACH_DELTA`): the offset from the crossing tile to the tile
# you approach it FROM, i.e. the tile one step opposite the crossing
# direction. Reused here (not imported -- that table is private to
# `assertions.py`) so `mechanism="threshold"` can compute its own approach
# cell the same way `cross_threshold`'s caller in every existing chapter
# module already does by hand.
_APPROACH_DELTA: dict[str, tuple[int, int]] = {
    "UP": (0, 1), "DOWN": (0, -1), "LEFT": (1, 0), "RIGHT": (-1, 0),
}


def warp_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    map_constant: str,
    map_id: int,
    event_id: int,
    dest_map_constant: str,
    mechanism: Mechanism,
    beat_name: str,
    description: str | None = None,
    direction: str | None = None,
    assert_facing: bool = False,
    assert_bgm: bool = False,
    dest_engine_map_dir: str | None = None,
    group: str | None = None,
    round_trip: bool = False,
    return_direction: str | None = None,
    manifest_rows: "tuple[ManifestRow, ...] | None" = None,
    manifest_dir=None,
) -> None:
    """Register one `warp` archetype crossing.

    `direction` is required for `mechanism="threshold"` and
    `mechanism="arrow"` (both are held-D-pad crossings gated on the
    direction the player is stepping, per `assertions.cross_threshold`/
    `cross_arrow_warp`'s own docstrings); `mechanism="door"` ignores it --
    `assertions.enter_door` always approaches from the south and holds UP,
    per pokeemerald's `TryDoorWarp` (`assertions.py`'s own citation).

    `group=` defaults to `beat_name` when omitted, matching the convention
    of the other three templates (`ChapterBuilder.beat`'s `group=`
    docstring) -- this template registers only one beat, so the default is
    a no-op in the solver's eyes (a singleton group named after the beat is
    what an ungrouped beat already gets), but stating it explicitly keeps
    the convention uniform across all four archetypes rather than leaving
    it as an accident of this template happening to have no satellites.

    `round_trip=True` (module docstring) crosses forward, asserts arrival,
    crosses back through the DERIVED reciprocal warp, asserts arrival back
    at the origin, then crosses forward once more -- still one beat, one
    row claim (`rows=(row_id,)` below is unaffected by `round_trip`; the
    extra crossings exercise cells this beat's own row already covers, not
    a second row). `return_direction` is required alongside it whenever
    `mechanism` is `"threshold"` or `"arrow"` (the reciprocal's press
    direction cannot be derived, same reasoning as `direction` above); it
    is rejected if given without `round_trip=True`, since it would
    otherwise silently do nothing.
    """
    resolved_group = group if group is not None else beat_name
    if mechanism not in _MECHANISMS:
        raise ValueError(
            f"warp_beat: mechanism={mechanism!r} is not one of "
            f"{sorted(_MECHANISMS)}"
        )
    if mechanism in ("threshold", "arrow") and direction is None:
        raise ValueError(
            f"warp_beat: mechanism={mechanism!r} requires direction= "
            "(the held D-pad direction of the crossing step)"
        )
    if assert_bgm and dest_engine_map_dir is None:
        raise ValueError(
            "warp_beat: assert_bgm=True requires dest_engine_map_dir= "
            "(the compiled map's directory under engine/data/maps/)"
        )
    if return_direction is not None and not round_trip:
        raise ValueError(
            "warp_beat: return_direction= was given without round_trip=True "
            "-- it has no effect on a one-way crossing"
        )
    if round_trip and mechanism in ("threshold", "arrow") and return_direction is None:
        raise ValueError(
            f"warp_beat: round_trip=True with mechanism={mechanism!r} "
            "requires return_direction= (the held D-pad direction of the "
            "return crossing step -- not necessarily the same as direction=; "
            "see warp.py's module docstring)"
        )

    match = find_match(
        chapter_id, map_id, event_id, "warp",
        rows=manifest_rows, manifest_dir=manifest_dir,
    )
    row_id = next(iter(match.roles))

    crossing = warp_cell(map_constant, to=dest_map_constant, event_id=event_id)
    arrival = arrival_cell(dest_map_constant, from_map=map_constant, event_id=event_id)

    return_crossing: tuple[int, int] | None = None
    return_arrival: tuple[int, int] | None = None
    if round_trip:
        # Derived, never a coordinate literal (task brief) -- fails loud,
        # naming the maps involved, via cells.py's own zero/one/many
        # discipline if the reciprocal warp can't be found unambiguously.
        return_crossing = warp_cell(dest_map_constant, to=map_constant)
        return_arrival = arrival_cell(map_constant, from_map=dest_map_constant)

    def _cross(emu: Emulator, crossing_cell: tuple[int, int],
               crossing_direction: str | None, dest_map: str) -> None:
        if mechanism == "door":
            assertions.enter_door(emu, beat_name, crossing_cell, dest_map)
        elif mechanism == "threshold":
            dx, dy = _APPROACH_DELTA[crossing_direction]
            approach = (crossing_cell[0] + dx, crossing_cell[1] + dy)
            assertions.cross_threshold(
                emu, beat_name, approach, crossing_direction, dest_map)
        else:  # "arrow"
            assertions.cross_arrow_warp(
                emu, beat_name, crossing_cell, crossing_direction, dest_map)

    @builder.beat(
        beat_name,
        description or (
            f"{map_constant} event {event_id} warps to {dest_map_constant} "
            f"via {mechanism} (manifest {row_id})"
            + (" (round trip)" if round_trip else "")
        ),
        map_constant=map_constant, at=crossing,
        group=resolved_group, archetype="warp", rows=(row_id,),
    )
    def run(emu: Emulator) -> None:
        _cross(emu, crossing, direction, dest_map_constant)
        assertions.require_map(emu, beat_name, dest_map_constant)
        assertions.assert_near(emu, beat_name, arrival)

        if assert_facing:
            dest_uid = map_uranium_id(dest_map_constant)
            expected_facing = assertions.expected_arrival_facing(
                dest_uid, *arrival)
            assertions.assert_player_facing(emu, beat_name, expected_facing)

        if assert_bgm:
            assertions.assert_bgm(emu, beat_name, dest_engine_map_dir)

        if round_trip:
            _cross(emu, return_crossing, return_direction, map_constant)
            assertions.require_map(emu, beat_name, map_constant)
            assertions.assert_near(emu, beat_name, return_arrival)

            _cross(emu, crossing, direction, dest_map_constant)
            assertions.require_map(emu, beat_name, dest_map_constant)
            assertions.assert_near(emu, beat_name, arrival)

    del run
