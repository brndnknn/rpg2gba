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

from ...beat_floor.assertion import FloorAssertion, make_params
from ...beat_floor.lookup import floor_for_row as _default_floor_for_row
from .. import assertions
from ..cells import arrival_cell, warp_cell
from ..errors import ScenarioError
from . import (
    FloorLookup, declare_assertions, find_match, load_chapter_rows,
    map_uranium_id, walked_arms,
)

if TYPE_CHECKING:  # runtime import is lazy so this module works without bindings
    from ...chapter_manifest.schema import ManifestRow
    from ..chapter import ChapterBuilder
    from ..emulator import Emulator

logger = logging.getLogger(__name__)

# Kinds this template's body actually checks (REDERIVATION_PLAN.md sec 16.3
# C5). `trigger`/`completes` are the row's own bookkeeping; `warp` is the
# arrival-position check `_forward`/`_back` always make; `visual`/`audio`
# assert nothing beyond the page completing (assertion.py's own kind
# docstrings), which `_cross`'s `emu.settle_field()` drive/observe -- so
# declaring them is honest, not aspirational. `text`, `item_grant`,
# `switch_write`, etc. are deliberately absent: nothing in this body reads a
# text box or a state write, so a warp page that also does one of those
# stays honestly uncovered for it.
_EXECUTED_KINDS: frozenset[str] = frozenset({
    "trigger", "completes", "warp", "visual", "audio",
})

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


def _report_reciprocal_manifest_row(
    *, beat_name: str, dest_map_constant: str, map_constant: str,
    return_crossing: "tuple[int, int] | None", resolved_rows: "tuple[ManifestRow, ...]",
) -> None:
    """Advisory only (task brief point 4): a `round_trip`/`start_side="dest"`
    leg crosses the RECIPROCAL warp, which this beat does not own. If that
    reciprocal happens to be a real row in the manifest actually searched
    for this call, name it in the log so the author can decide whether it
    needs its own explicit claim -- never added to `rows=` here, because
    `warp_beat`'s own contract (`test_warp_beat_start_side_dest_still_claims_
    the_same_single_row`) is that which side the player starts on must not
    change what a beat claims.
    """
    if return_crossing is None:
        return
    from ...chapter_manifest.archetypes import classify_manifest
    from ...traversal.graph import build_map_graph

    try:
        dest_uid = map_uranium_id(dest_map_constant)
        origin_uid = map_uranium_id(map_constant)
        graph = build_map_graph(dest_uid)
    except Exception:  # advisory path; never blocks registration
        logger.debug("%s: reciprocal-manifest-row check skipped (map lookup failed)", beat_name)
        return
    candidates = [
        exit_ for exit_ in graph.warp_exits.get(return_crossing, ())
        if exit_.dest_map == origin_uid
    ]
    if not candidates:
        return
    matches = classify_manifest(resolved_rows)
    for exit_ in candidates:
        for match in matches:
            if match.map_id != dest_uid or match.event_id != exit_.event_id:
                continue
            if match.archetype != "warp":
                continue
            for row_id in match.roles:
                logger.info(
                    "warp_beat(%s): the reciprocal crossing (%s event %s) is "
                    "manifest row %s -- not auto-claimed (this beat only "
                    "crosses it, it does not own it); give it its own "
                    "warp_beat() call if it needs its own assertions",
                    beat_name, dest_map_constant, exit_.event_id, row_id,
                )


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
    start_side: Literal["origin", "dest"] = "origin",
    boundary: bool = False,
    manifest_rows: "tuple[ManifestRow, ...] | None" = None,
    manifest_dir=None,
    manifest_chapter_id: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one `warp` archetype crossing.

    `floor_lookup=`, if given, replaces `beat_floor.lookup.floor_for_row`
    for both the registration-time arrival check and `declare_assertions`
    below -- real chapters never pass it; tests use it to inject a synthetic
    `RowFloor` (REDERIVATION_PLAN.md sec 16.3 C5, task brief point 8).

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

    `start_side` names which side of the warp the PLAYER IS STANDING ON
    when the beat begins, which is not always the side that owns the
    claimed row. `"origin"` (the default) is the ordinary case: the player
    is on `map_constant`, the map whose event this beat claims. `"dest"`
    means the player begins on `dest_map_constant` -- the far side -- so
    the legs run mirrored: the RECIPROCAL warp is crossed first, to reach
    the map the claimed event lives on, and the claimed event itself is
    crossed second. With `round_trip=True` a third leg follows and the beat
    ends back on the far side it started from; with `round_trip=False` it
    stops after two and ends on `dest_map_constant`, which is where it
    began. Both forms prove the warp fires in BOTH directions -- mirroring
    guarantees the reciprocal leg, so unlike `start_side="origin"` there is
    no one-crossing mode on this side at all. What `round_trip` chooses
    here is only which map the beat hands the player over on.

    CH05's B1 is why it exists. Its row is `map036/ev001/p0`, the CAVE's
    exit warp, so the template's origin is the cave -- but CH04 leaves the
    player on Route 02, and a beat that assumes it starts in the cave walks
    the cave's warp coordinates on Route 02 and asserts an arrival that
    never happens. `start_side="dest"` is the difference between a beat
    that begins where the player is and one that begins where its manifest
    row lives.

    CH05's B8_return is why the two-leg (`round_trip=False`) form exists.
    Its row is `map037/ev001/p0`, 2F's stairs down, but the whole B8 stop
    is approached on 1F -- and `B8_nudge` has to observe the arrival autorun
    that fires when those stairs land you on 1F, so the beat before it must
    END on 1F. Mirrored and two-legged, `B8_return` runs 1F -> 2F -> 1F: it
    starts where the player is, crosses its claimed warp, and stops on the
    floor the nudge needs. `B8` then runs last as a lone forward crossing
    and leaves the stop on 2F. Three crossings, three rows, and the stop
    ends where the chapter continues -- see `chapters/ch05.py`.

    `round_trip=True` (module docstring) crosses forward, asserts arrival,
    crosses back through the DERIVED reciprocal warp, asserts arrival back
    at the origin, then crosses forward once more -- still one beat, one
    row claim (`rows=(row_id,)` below is unaffected by `round_trip`; the
    extra crossings exercise cells this beat's own row already covers, not
    a second row). `return_direction` is required whenever the reciprocal
    is crossed at all -- `round_trip=True` OR `start_side="dest"` -- and
    `mechanism` is `"threshold"` or `"arrow"` (the reciprocal's press
    direction cannot be derived, same reasoning as `direction` above); it
    is rejected when neither mode is on, since it would otherwise silently
    do nothing.

    `manifest_chapter_id=`, if given, is a predecessor chapter whose
    manifest actually carries this row (`find_match`'s own docstring --
    REDERIVATION_PLAN.md §10 R2): a warp page sitting on a map the
    PREVIOUS chapter owns, claimed by this chapter because only this
    chapter's walk can trigger it. `None` (the default) preserves today's
    behavior of reading `chapter_id`'s own manifest.

    `boundary=True` is for a warp that LEAVES the chapter: its destination
    belongs to a later chapter, so this chapter's ROM may or may not have
    staged it (C6 Task 9). The beat walks to the approach cell on the
    `direction` side, asserts it stands there on `map_constant` with the
    field unlocked, and stops -- it never steps onto the warp. That holds
    whether or not the destination is staged, which is the lesson of
    `ch04.py`'s B7 (it stepped on the cave mouth and asserted nothing fired,
    true only until CH05 staged the cave). It still claims the row, but
    declares none of its floor kinds: nothing here executes the page, so
    the crossing stays honestly uncovered, owed to the chapter being opened
    (REDERIVATION_PLAN.md §10 R2). No round trip, no far-side start, no
    arrival facing/BGM: each would need the destination staged.
    """
    resolved_group = group if group is not None else beat_name
    if boundary and (round_trip or start_side != "origin" or return_direction is not None
                     or assert_facing or assert_bgm):
        raise ValueError(
            "warp_beat: boundary=True never crosses the warp, so round_trip=, "
            "start_side='dest', return_direction=, assert_facing= and "
            "assert_bgm= are all meaningless with it"
        )
    if boundary and mechanism == "door":
        raise ValueError(
            "warp_beat: boundary=True with mechanism='door' has no approach "
            "side to stop on -- no boundary door exists in this corpus yet"
        )
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
    if start_side not in ("origin", "dest"):
        raise ValueError(
            f"warp_beat: start_side={start_side!r} is not 'origin' or 'dest'"
        )
    if assert_bgm and dest_engine_map_dir is None:
        raise ValueError(
            "warp_beat: assert_bgm=True requires dest_engine_map_dir= "
            "(the compiled map's directory under engine/data/maps/)"
        )
    # The reciprocal leg is crossed by BOTH extra modes: `round_trip` adds it
    # after the claimed crossing, `start_side="dest"` adds it before. Either
    # one means `return_direction` is load-bearing; neither means it is dead
    # weight and saying it is a mistake worth failing on.
    crosses_reciprocal = round_trip or start_side == "dest"
    if return_direction is not None and not crosses_reciprocal:
        raise ValueError(
            "warp_beat: return_direction= was given without round_trip=True "
            "or start_side='dest' -- it has no effect on a lone forward "
            "crossing"
        )
    if crosses_reciprocal and mechanism in ("threshold", "arrow") and return_direction is None:
        raise ValueError(
            f"warp_beat: mechanism={mechanism!r} with round_trip=True or "
            "start_side='dest' requires return_direction= (the held D-pad "
            "direction of the reciprocal crossing step -- not necessarily "
            "the same as direction=; see warp.py's module docstring)"
        )

    match = find_match(
        chapter_id, map_id, event_id, "warp",
        rows=manifest_rows, manifest_dir=manifest_dir,
        manifest_chapter_id=manifest_chapter_id,
    )
    row_id = next(iter(match.roles))
    lookup = floor_lookup if floor_lookup is not None else _default_floor_for_row

    crossing = warp_cell(map_constant, to=dest_map_constant, event_id=event_id)
    arrival = arrival_cell(dest_map_constant, from_map=map_constant, event_id=event_id)

    # Registration-time cross-check (task brief point 1): the RMXP source
    # floor's own (map_id, x, y) for this row's code-201 must agree with the
    # arrival cell `cells.arrival_cell` derived from the SAME build's decoded
    # warp-exit graph -- both read the identical staged Map###.json, so
    # disagreement here is never "the pipeline drifted a tile", it is a claim
    # bug (wrong event_id, wrong map pairing) and fails loud naming both
    # sides rather than surfacing later as a mystifying runtime landing miss.
    dest_uid = map_uranium_id(dest_map_constant)
    floor = lookup(row_id)
    warp_floor_assertions = [a for a in floor.assertions if a.kind == "warp"]
    if warp_floor_assertions:
        if len(warp_floor_assertions) != 1:
            raise ValueError(
                f"warp_beat({beat_name}): row {row_id} floor carries "
                f"{len(warp_floor_assertions)} 'warp' assertions, expected "
                "exactly one"
            )
        floor_warp = warp_floor_assertions[0]
        floor_params = dict(floor_warp.params)
        if (floor_params["map_id"], floor_params["x"], floor_params["y"]) != (
            dest_uid, arrival[0], arrival[1],
        ):
            raise ValueError(
                f"warp_beat({beat_name}): derived arrival cell {arrival} on "
                f"{dest_map_constant} (Uranium map {dest_uid}) disagrees "
                f"with row {row_id}'s source floor warp target "
                f"(map_id={floor_params['map_id']}, x={floor_params['x']}, "
                f"y={floor_params['y']}) -- cells.arrival_cell and the "
                "generic floor should never diverge on the same build"
            )
    elif assert_facing or assert_bgm:
        raise ValueError(
            f"warp_beat({beat_name}): assert_facing=/assert_bgm= requested "
            f"but row {row_id}'s floor carries no 'warp' assertion to "
            "strengthen (refused or malformed source command)"
        )

    # Arrival facing and landing cell (C5b, WARP_RETAIN_FACING_PROPOSAL.md §0):
    # the claimed warp's own RMXP direction when explicit, else the facing the
    # player crossed with (`door` is always entered holding UP -- see
    # `assertions.enter_door`). When the floor says the arrival cell is a door
    # tile, the engine walks the player one step on in that facing, so the
    # forward leg lands one tile past `arrival`.
    expected_facing: str | None = None
    landing = arrival
    if warp_floor_assertions:
        floor_params = dict(warp_floor_assertions[0].params)
        approach = "UP" if mechanism == "door" else direction
        expected_facing = assertions.facing_for_direction(
            floor_params["direction"], approach)
        landing = assertions.arrival_landing_cell(
            arrival, expected_facing, floor_params["arrives_on_door"])

    extras: list[FloorAssertion] = []
    if warp_floor_assertions and (assert_facing or assert_bgm):
        floor_warp = warp_floor_assertions[0]
        extra_params = dict(floor_warp.params)
        if assert_facing:
            extra_params["arrival_facing"] = expected_facing
        if assert_bgm:
            extra_params["bgm"] = dest_engine_map_dir
        extras.append(FloorAssertion(
            row_id=row_id, kind="warp", list_index=floor_warp.list_index,
            code=floor_warp.code, params=make_params(**extra_params),
            tag=floor_warp.tag,
        ))

    arm_rows = walked_arms(row_id, "warp", floor_lookup=lookup)
    claimed_rows = (row_id,) + arm_rows
    declared = declare_assertions(
        claimed_rows, executed_kinds=frozenset() if boundary else _EXECUTED_KINDS,
        template="warp", extras=extras, floor_lookup=lookup,
    )

    if boundary:
        dx, dy = _APPROACH_DELTA[direction]
        edge = (crossing[0] + dx, crossing[1] + dy)

        @builder.beat(
            beat_name,
            description or (
                f"{map_constant} event {event_id} leaves the chapter for "
                f"{dest_map_constant} (manifest {row_id}); the beat stops on "
                f"the approach cell {edge} and does not cross"
            ),
            map_constant=map_constant, at=edge,
            group=resolved_group, archetype="warp", rows=claimed_rows,
            assertions=declared,
        )
        def run_boundary(emu: Emulator) -> None:
            emu.walk_to(*edge)
            assertions.require_map(emu, beat_name, map_constant)
            assertions.assert_position_exact(emu, beat_name, edge)
            if emu.field_locked():
                shot = emu.screenshot(f"{beat_name}_unexpected_lock")
                raise ScenarioError(
                    f"{beat_name}: field locked on the approach cell {edge} of a "
                    f"chapter-boundary warp -- nothing should fire here ({shot})")

        del run_boundary
        return

    return_crossing: tuple[int, int] | None = None
    return_arrival: tuple[int, int] | None = None
    if crosses_reciprocal:
        # Derived, never a coordinate literal (task brief) -- fails loud,
        # naming the maps involved, via cells.py's own zero/one/many
        # discipline if the reciprocal warp can't be found unambiguously.
        return_crossing = warp_cell(dest_map_constant, to=map_constant)
        return_arrival = arrival_cell(map_constant, from_map=dest_map_constant)
        # Advisory report only (task brief point 4) -- never changes rows=.
        resolved_rows = manifest_rows if manifest_rows is not None else load_chapter_rows(
            manifest_chapter_id if manifest_chapter_id is not None else chapter_id,
            manifest_dir=manifest_dir,
        )
        _report_reciprocal_manifest_row(
            beat_name=beat_name, dest_map_constant=dest_map_constant,
            map_constant=map_constant, return_crossing=return_crossing,
            resolved_rows=resolved_rows,
        )

    def _cross(emu: Emulator, crossing_cell: tuple[int, int],
               crossing_direction: str | None, dest_map: str,
               from_map: str) -> None:
        # Proving a warp fired means proving the player LEFT, not just that
        # they are standing on the destination -- when `from_map` and
        # `dest_map` are the same map, `wait_for_map`/`require_map` both
        # pass without a warp ever firing. That is not hypothetical: B1's
        # mis-sided authoring walked Route 02 the whole beat and both
        # guards waved it through, and only a coordinate assertion caught
        # it. A round trip exists to prove the warp works BOTH ways, so a
        # guard that can pass trivially defeats the point of running it.
        if from_map == dest_map:
            raise ValueError(
                f"warp_beat({beat_name}): a crossing from {from_map} to "
                f"{dest_map} cannot be proven -- origin and destination are "
                "the same map, so no map assertion can tell a fired warp "
                "from a walk that did nothing"
            )
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
        # Arriving is not the same as having arrived. `cross_threshold` and
        # friends end at `wait_for_map`, which proves the map CHANGED and
        # nothing more -- the destination's own arrival scripts may not have
        # run yet. A converted map's OnFrame dispatcher tests its autorun
        # guards in sequence (`Emulator.settle_field`), so the field can be
        # released for a frame and re-locked as the next page arms itself.
        # The next leg's `walk_to` then starts unlocked, watches the field
        # lock underneath it, and raises `WalkInterrupted` -- which is what
        # B1 did the first time the warps actually fired: "walk_to(17, 39)
        # interrupted by a locked-field scene at (17, 39)".
        #
        # Draining here rather than reacting to it removes the race instead
        # of racing better, and it is what `ch03.py`/`ch04.py` already do by
        # hand after their own crossings. A beat that wants to ASSERT an
        # arrival autorun (the `arrival_nudge` archetype) claims that page
        # as its own row and does not go through this template.
        emu.settle_field()

    def _forward(emu: Emulator, *, check_arrival_details: bool = False) -> None:
        """Cross the CLAIMED warp: origin -> dest.

        `assert_facing`/`assert_bgm` describe the landing on
        `dest_map_constant`, so they belong to THIS leg and are asked for
        only on the first forward crossing -- checking them after a
        reciprocal leg would test the arrival on the wrong map, which is
        the mistake `start_side="dest"` exists to stop making.
        """
        _cross(emu, crossing, direction, dest_map_constant, map_constant)
        assertions.require_map(emu, beat_name, dest_map_constant)
        # Exact, not `_assert_near`'s tolerance-1 (task brief point 1):
        # `cells.arrival_cell` and the generic floor's warp target are the
        # SAME RMXP source coordinates (both read straight off this build's
        # decoded Map###.json, verified against each other above at
        # registration time), and `chapter.py`'s own `ChapterBuilder.beat`
        # docstring records that `ON_WARP_INTO_MAP` dispatch compares
        # `getplayerxy` against them with no tolerance either -- a tolerant
        # check here would hide exactly the one-tile miss that dispatch
        # would catch anyway, just later and with a worse error. `landing` is
        # `arrival` itself unless the floor marks it a door tile (C5b).
        assertions.assert_position_exact(emu, beat_name, landing)

        if not check_arrival_details:
            return
        if assert_facing:
            assertions.assert_player_facing(emu, beat_name, expected_facing)
        if assert_bgm:
            assertions.assert_bgm(emu, beat_name, dest_engine_map_dir)

    def _back(emu: Emulator) -> None:
        """Cross the DERIVED reciprocal: dest -> origin."""
        _cross(emu, return_crossing, return_direction, map_constant,
               dest_map_constant)
        assertions.require_map(emu, beat_name, map_constant)
        # Same exactness reasoning as `_forward` above -- `return_arrival` is
        # derived through the identical `cells.arrival_cell` call. Unlike the
        # forward leg there is no floor for the (unclaimed) reciprocal row, so
        # a reciprocal that lands on a door tile is NOT offset by the C5b
        # exit step here; that mismatch fails this check loudly in-ROM (P11).
        assertions.assert_position_exact(emu, beat_name, return_arrival)

    @builder.beat(
        beat_name,
        description or (
            f"{map_constant} event {event_id} warps to {dest_map_constant} "
            f"via {mechanism} (manifest {row_id})"
            + (" (round trip)" if round_trip else "")
            + (" (entered from the far side)" if start_side == "dest" else "")
        ),
        map_constant=map_constant, at=crossing,
        group=resolved_group, archetype="warp", rows=claimed_rows,
        assertions=declared,
    )
    def run(emu: Emulator) -> None:
        # The operator's round-trip rule: start on the map you are standing
        # on, cross to the other one, come back, then cross again so the
        # beat ENDS on the far side. Three crossings is the fewest that
        # proves a warp works in BOTH directions and still leaves the
        # player where the next beat needs them; two would prove both
        # directions but end where it started.
        #
        # `start_side` only chooses which leg is first, because which side
        # the player is on is a fact about the chapter's approach, not
        # about the warp. The claimed event is crossed either way -- first
        # leg when starting on its own map, middle leg when starting on the
        # far side.
        if start_side == "origin":
            _forward(emu, check_arrival_details=True)
            if round_trip:
                _back(emu)
                _forward(emu)
        else:
            _back(emu)
            _forward(emu, check_arrival_details=True)
            if round_trip:
                _back(emu)

    del run
