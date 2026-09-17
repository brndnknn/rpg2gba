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

from ...beat_floor.assertion import FloorAssertion
from ...beat_floor.lookup import floor_for_row as _default_floor_for_row
from .. import assertions
from ..cells import arrival_cell
from . import FloorLookup, declare_assertions, find_match, walked_arms

if TYPE_CHECKING:  # runtime import is lazy so this module works without bindings
    from ...chapter_manifest.schema import ManifestRow
    from ..chapter import ChapterBuilder
    from ..emulator import Emulator

logger = logging.getLogger(__name__)

# Kinds this template's body always checks (REDERIVATION_PLAN.md sec 16.3
# C5): the row's own bookkeeping, plus `visual`/`audio` (assert nothing
# beyond completion, which `assert_arrival_settled`'s field-drain already
# observes). `displacement` is declared per-instance via `extras=` below,
# never blanket -- a nudge's move-route script commonly carries MORE than
# one `displacement` assertion on the walked arm (the nudging event's own
# decorative move alongside the player's, `target=0` vs `target=-1` --
# see `_player_displacement`), and blanket-declaring the kind would claim
# the event's own move is checked too, which this body never reads.
_EXECUTED_KINDS: frozenset[str] = frozenset({"trigger", "completes", "visual", "audio"})

#: `target=-1` is `assertion.py`'s own convention for "the player" (0 = this
#: event, N = another event) -- the only target this template's body ever
#: observes (`emu.player_pos()`).
_PLAYER_TARGET = -1


def _player_displacement(
    row_id: str, arm_rows: tuple[str, ...], *, floor_lookup: FloorLookup,
) -> "tuple[str, FloorAssertion] | None":
    """The one `target=-1` (player) `displacement` assertion covering this
    nudge, searched on the page's own trunk floor first and then its walked
    arm(s) -- both are legal homes for it depending on whether the move
    route sits inside the branch or outside it. `None` when neither carries
    one (the refused/unpredictable-route case `_walked_arms` documents).
    Fails loud on more than one candidate: this template checks exactly one
    player position, so two would mean the fingerprint matched something
    this body cannot honestly assert against.
    """
    found: list[tuple[str, FloorAssertion]] = []
    for candidate_row in (row_id, *arm_rows):
        floor = floor_lookup(candidate_row)
        for a in floor.assertions:
            if a.kind == "displacement" and a.param("target") == _PLAYER_TARGET:
                found.append((candidate_row, a))
    if not found:
        return None
    if len(found) > 1:
        listing = [(r, dict(a.params)) for r, a in found]
        raise ValueError(
            f"arrival_nudge_beat: row {row_id} has {len(found)} player "
            f"(target={_PLAYER_TARGET}) displacement assertions across its "
            f"trunk/arms: {listing} -- exactly one is expected"
        )
    return found[0]


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
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one `arrival_nudge` archetype instance.

    `floor_lookup=`, if given, replaces `beat_floor.lookup.floor_for_row`
    for both the registration-time displacement lookup and
    `declare_assertions` below -- real chapters never pass it; tests use it
    to inject a synthetic `RowFloor` (REDERIVATION_PLAN.md sec 16.3 C5,
    task brief point 8).

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
    lookup = floor_lookup if floor_lookup is not None else _default_floor_for_row

    arrival = arrival_cell(
        map_constant, from_map=from_map_constant, event_id=from_event_id)

    arm_rows = walked_arms(row_id, "displacement", floor_lookup=lookup)
    claimed_rows = (row_id,) + arm_rows
    displacement = _player_displacement(row_id, arm_rows, floor_lookup=lookup)

    extras: list[FloorAssertion] = []
    expected_delta: "tuple[int, int, str | None] | None" = None
    if displacement is not None:
        source_row, fa = displacement
        params = dict(fa.params)
        dx, dy, facing = params["dx"], params["dy"], params["facing"]
        expected_delta = (dx, dy, facing)
        # A straight copy of the floor's own assertion (task brief point 5:
        # "check the exact declared (dx, dy)") -- there is nothing to
        # strengthen beyond what the source already states, so the extra
        # exists only to name it PER-ASSERTION (this row_id, this
        # list_index/code), which is what keeps the sibling target=0
        # displacement on the same arm honestly undeclared (see
        # `_EXECUTED_KINDS`'s docstring above).
        extras.append(FloorAssertion(
            row_id=source_row, kind="displacement", list_index=fa.list_index,
            code=fa.code, params=fa.params, tag=fa.tag,
        ))

    declared = declare_assertions(
        claimed_rows, executed_kinds=_EXECUTED_KINDS, template="arrival_nudge",
        extras=extras, floor_lookup=lookup,
    )

    @builder.beat(
        beat_name,
        description or (
            f"Arrival autorun on {map_constant} event {event_id} nudges the "
            f"player one tile off the arrival cell (manifest {row_id})"
        ),
        map_constant=map_constant, at=arrival,
        group=resolved_group, archetype="arrival_nudge", rows=claimed_rows,
        assertions=declared,
    )
    def run(emu: Emulator) -> None:
        assertions.require_map(emu, beat_name, map_constant)
        assertions.assert_arrival_settled(emu, beat_name, arrival, nudged=True)

        if expected_delta is None:
            return
        dx, dy, facing = expected_delta
        # Exact (task brief point 5), not `assert_arrival_settled`'s
        # Manhattan-distance-1 tolerance above -- the move route's `(dx, dy)`
        # is a fully known net displacement (C4's `move_route.py`), so the
        # landing tile is a single point, not a neighbourhood, and a diagonal
        # miss that still happens to be 1 tile away would pass the looser
        # check silently.
        assertions.assert_position_exact(
            emu, beat_name, (arrival[0] + dx, arrival[1] + dy))
        if facing is not None:
            assertions.assert_player_facing(emu, beat_name, facing.upper())

    del run
