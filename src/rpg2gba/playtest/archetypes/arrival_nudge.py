"""The `arrival_nudge` archetype beat template -- the largest archetype in
the corpus (324 instances across 73 maps, task brief).

Fingerprint (`chapter_manifest.archetypes._match_arrival_nudge`): an
autorun page that branches on `get_character(0)`, moves the player one tile
off the arrival cell via a move route, and sets a temp switch so it never
refires on the same visit. The beat asserts exactly that shape: on arrival
the field locks, the scene drives to completion, and the player ends
displaced exactly one tile from the arrival cell -- both cells derived from
`cells.py` (`arrival_cell` for where the warp lands, the emulator's own
`player_pos()` for the settled position), never a hardcoded delta.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import assertions
from ..cells import arrival_cell
from ..errors import ScenarioError
from . import find_match

if TYPE_CHECKING:  # runtime import is lazy so this module works without bindings
    from ...chapter_manifest.schema import ManifestRow
    from ..chapter import ChapterBuilder
    from ..emulator import Emulator

logger = logging.getLogger(__name__)


def arrival_nudge_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    map_constant: str,
    map_id: int,
    event_id: int,
    from_map_constant: str,
    beat_name: str,
    description: str | None = None,
    from_event_id: int | None = None,
    group: str | None = None,
    manifest_rows: "tuple[ManifestRow, ...] | None" = None,
    manifest_dir=None,
    manifest_chapter_id: str | None = None,
) -> None:
    """Register one `arrival_nudge` archetype instance.

    `group=` defaults to `beat_name` when omitted, matching the convention
    of the other three templates (`ChapterBuilder.beat`'s `group=`
    docstring) -- this template registers only one beat, so the default is
    a no-op in the solver's eyes, but it keeps the convention uniform
    across all four archetypes rather than leaving it an accident of this
    template happening to have no satellites.

    `from_map_constant` is the map the player warps FROM to trigger this
    arrival -- required because `cells.arrival_cell` needs a source map to
    find the warp exit that lands on this event's map (same requirement
    every other warp-arrival consumer in `cells.py` has).

    `from_event_id`, if given, disambiguates which warp event ON
    `from_map_constant` produces this arrival, for `cells.arrival_cell`'s
    own zero/one/many discipline. This is deliberately NOT the same number
    as `event_id` above: `event_id` names the nudge's own event on THIS
    map (destination side), while a disambiguating event id for
    `arrival_cell` names an event on the SOURCE map -- the two live in
    independent per-map id spaces and coincidentally sharing a template's
    event numbering across two different maps would be a bug, not a
    shortcut. Only needed when more than one warp between the two maps
    exists; `arrival_cell` fails loud, naming every candidate, if it's
    needed and omitted.

    `manifest_chapter_id=`, if given, is a predecessor chapter whose
    manifest actually carries this row (`find_match`'s own docstring --
    REDERIVATION_PLAN.md §10 R3): an arrival nudge sitting on a map the
    PREVIOUS chapter owns, claimed by this chapter because only this
    chapter's walk can trigger it. `None` (the default) preserves today's
    behavior of reading `chapter_id`'s own manifest.
    """
    match = find_match(
        chapter_id, map_id, event_id, "arrival_nudge",
        rows=manifest_rows, manifest_dir=manifest_dir,
        manifest_chapter_id=manifest_chapter_id,
    )
    row_id = next(iter(match.roles))
    resolved_group = group if group is not None else beat_name

    arrival = arrival_cell(
        map_constant, from_map=from_map_constant, event_id=from_event_id)

    @builder.beat(
        beat_name,
        description or (
            f"Arrival autorun on {map_constant} event {event_id} nudges the "
            f"player one tile off the arrival cell (manifest {row_id})"
        ),
        map_constant=map_constant, at=arrival,
        group=resolved_group, archetype="arrival_nudge", rows=(row_id,),
    )
    def run(emu: Emulator) -> None:
        assertions.require_map(emu, beat_name, map_constant)
        emu.settle_field()
        if emu.field_locked():
            shot = emu.screenshot(f"{beat_name}_stuck")
            raise ScenarioError(
                f"{beat_name}: field still locked after settling on "
                f"arrival ({shot})"
            )
        pos = emu.player_pos()
        if pos == arrival:
            shot = emu.screenshot(f"{beat_name}_no_nudge")
            raise ScenarioError(
                f"{beat_name}: player still at arrival cell {arrival} "
                "after the autorun settled -- expected the nudge move "
                f"route to have displaced them ({shot})"
            )
        dx = abs(pos[0] - arrival[0])
        dy = abs(pos[1] - arrival[1])
        if dx + dy != 1:
            shot = emu.screenshot(f"{beat_name}_wrong_nudge_distance")
            raise ScenarioError(
                f"{beat_name}: nudged to {pos}, expected exactly one tile "
                f"off arrival cell {arrival} (got Manhattan distance "
                f"{dx + dy}) ({shot})"
            )

    del run
