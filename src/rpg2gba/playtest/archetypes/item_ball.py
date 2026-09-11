"""The `item_ball` archetype beat template.

Page 0 is the grant; page 1 is the "already spent" re-touch, prescribed
`cosmetic` by `chapter_manifest.archetypes` (module docstring:
`ArchetypeMatch.prescribed`) -- the operator decision of 2026-09-01 is that
`cosmetic` means **no beat by default**. `negative_beat=True` promotes it to
a real "re-touch grants nothing a second time" beat.

The self-switch letter that gates the spent page is read from the manifest
row itself (`ManifestRow.condition.self_switch_ch`), not hardcoded to "A" --
`_match_item_ball` requires it to be set on the spent page for that page to be
claimed at all (`chapter_manifest/archetypes.py`). A single-page item ball
(loosened 2026-09-10, `map068/ev018/p0`-shaped: `pbItemBall` with no page-1
remainder at all) has no spent row to read a letter from, so `item_ball_beats`
demands `self_switch_letter=` from the author in that case rather than
defaulting one, and refuses `negative_beat=True` outright since there is no
spent row to assert against.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import assertions
from ..cells import approach_to, event_cell
from ..errors import ScenarioError
from . import find_match, load_chapter_rows

if TYPE_CHECKING:  # runtime import is lazy so this module works without bindings
    from ...chapter_manifest.schema import ManifestRow
    from ..chapter import ChapterBuilder
    from ..emulator import Emulator

logger = logging.getLogger(__name__)

_DIR_TOWARD: dict[tuple[int, int], str] = {
    (1, 0): "RIGHT", (-1, 0): "LEFT", (0, 1): "DOWN", (0, -1): "UP",
}


def _facing_toward(approach: tuple[int, int], target: tuple[int, int]) -> str:
    delta = (target[0] - approach[0], target[1] - approach[1])
    facing = _DIR_TOWARD.get(delta)
    if facing is None:
        raise ValueError(
            f"item_ball_beats: approach {approach} is not orthogonally "
            f"adjacent to target {target} (delta {delta})"
        )
    return facing


def item_ball_beats(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    map_constant: str,
    map_id: int,
    event_id: int,
    item: str,
    beat_prefix: str,
    negative_beat: bool = False,
    self_switch_letter: str | None = None,
    approach_prefer: str | None = None,
    group: str | None = None,
    manifest_rows: "tuple[ManifestRow, ...] | None" = None,
    manifest_dir=None,
) -> None:
    """Register an `item_ball` archetype's grant beat, and its spent-page
    negative beat if `negative_beat=True`.

    `item` (a plain `ITEM_*` constant string) is author-supplied -- the
    manifest's `ArchetypeMatch.params` for `item_ball` is empty
    (`chapter_manifest/archetypes.py`), because which item a `giveitem`
    call grants is not something a `ManifestRow`'s effect tags carry, only
    that one is granted at all. There is nothing to validate this against;
    only the self-switch gating and the approach/facing geometry are
    manifest-derived here.

    `group=` defaults to `beat_prefix` when omitted: an archetype instance's
    beats belong to one route-solver stop, exactly as a hand-authored
    chapter groups them today (`ChapterBuilder.beat`'s `group=` docstring).
    The primary beat is named exactly `beat_prefix` (not `f"{beat_prefix}_grant"`)
    because the chapter manifest dispositions this stop as bare `beat:{beat_prefix}`,
    and `_check_route_approach` looks up a node's beats by that exact name
    (`chapter_manifest/checker.py`, `RouteModel.declared_beat_cell`) -- the
    primary beat *is* the stop the disposition names. The spent-page negative
    beat keeps its descriptive `_spent` suffix; it is a satellite of the stop,
    not the stop's own identity.
    """
    resolved_group = group if group is not None else beat_prefix
    match = find_match(
        chapter_id, map_id, event_id, "item_ball",
        rows=manifest_rows, manifest_dir=manifest_dir,
    )
    grant_row_id = next(rid for rid, role in match.roles.items() if role == "grant")
    spent_row_id = next(
        (rid for rid, role in match.roles.items() if role == "spent"), None)

    # A single-page item ball (chapter_manifest.archetypes._match_item_ball,
    # loosened 2026-09-10 for map068/ev018/p0-shaped instances) has no
    # "spent" role at all -- there is no remainder page to gate a negative
    # beat against. `negative_beat=True` asks for exactly that beat, so it
    # cannot be honoured here; fail loud rather than silently skip it or
    # raise a bare KeyError from the `next()` below.
    if spent_row_id is None:
        if negative_beat:
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: "
                "negative_beat=True requires a 'spent' page, but this "
                "item_ball match has none (a single-page item ball with no "
                "remainder page) -- omit negative_beat= for this event"
            )
        # No page-1 condition exists to read the self-switch letter off of
        # -- that is precisely what makes this a single-page item ball. The
        # letter a page *writes* is not in the manifest at all: `Condition`
        # carries `self_switch_ch`, the letter a page READS to gate itself
        # (`chapter_manifest/schema.py`), and a single-page ball has no such
        # page. So the letter is author-supplied here, and demanded rather
        # than defaulted (CLAUDE.md 4.5): guessing "A" would assert
        # FLAG_MAP..._SSA on a ball that actually writes B, and the beat
        # would then pass or fail for the wrong reason.
        if self_switch_letter is None:
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: this is a "
                "single-page item ball (no spent page), so the self-switch "
                "letter cannot be read from the manifest -- pass "
                "self_switch_letter= explicitly, citing the event's own "
                "code-123 write in output/uranium-build/maps/"
                f"Map{map_id:03d}.json"
            )
        letter = self_switch_letter
        ssa = assertions.flag_ssa(map_id, event_id, letter)
        spent_page_is_empty = False
    else:
        rows = manifest_rows if manifest_rows is not None else load_chapter_rows(
            chapter_id, manifest_dir=manifest_dir)
        row_by_id = {r.row_id: r for r in rows}
        spent_row = row_by_id.get(spent_row_id)
        if spent_row is None or spent_row.condition is None \
                or spent_row.condition.self_switch_ch is None:
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: spent row "
                f"{spent_row_id!r} carries no self_switch_ch -- "
                "chapter_manifest.archetypes._match_item_ball should have "
                "refused to match this event at all if that's true; this is "
                "unreachable unless the manifest and the classifier disagree"
            )
        letter = spent_row.condition.self_switch_ch
        if self_switch_letter is not None and self_switch_letter != letter:
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: stated "
                f"self_switch_letter={self_switch_letter!r} disagrees with the "
                f"spent row's own condition ({letter!r}) -- the manifest is the "
                "source of truth when a spent page exists; drop the argument"
            )
        ssa = assertions.flag_ssa(map_id, event_id, letter)

        # Does the spent page DO anything? Some are a "nothing here" message;
        # others are an empty page whose only job is to make the ball vanish
        # once the self-switch flips. CH05's Escape Rope ball (map036/ev003/p1)
        # is the second kind: no graphic, a single terminator command, and a
        # manifest row that records it exactly -- no effects, no script
        # heads, no other codes, nothing unhandled.
        #
        # It matters because the two shapes have OPPOSITE pass conditions. On
        # an empty page an A press starts no script, and demanding one fails
        # a beat for behaving correctly. Read from the manifest rather than
        # assumed, so a chapter whose spent page does speak still gets the
        # stronger assertion. (Only reachable when a spent row exists at
        # all -- a single-page item ball sets `spent_page_is_empty = False`
        # above and never reaches this branch.)
        spent_page_is_empty = not (
            spent_row.effects or spent_row.script_heads
            or spent_row.other_codes or spent_row.unhandled
        )

    approach = approach_to(map_constant, event_id, prefer=approach_prefer)
    facing = _facing_toward(approach, event_cell(map_constant, event_id))

    @builder.beat(
        beat_prefix,
        f"The item ball at {map_constant} event {event_id} grants "
        f"{item} once (manifest {grant_row_id})",
        map_constant=map_constant, at=approach,
        group=resolved_group, archetype="item_ball", rows=(grant_row_id,),
    )
    def grant_beat(emu: Emulator) -> None:
        if emu.flag(ssa):
            raise ScenarioError(
                f"{beat_prefix} precondition failed: {ssa} already "
                "set before the pickup"
            )
        bag_before = emu.bag_item_quantity(item)
        emu.walk_to(*approach)
        emu.face(facing)
        emu.interact()
        emu.advance_dialog()
        if not emu.flag(ssa):
            shot = emu.screenshot(f"{beat_prefix}_no_ssa")
            raise ScenarioError(
                f"{beat_prefix}: {ssa} not set after the pickup ({shot})"
            )
        bag_after = emu.bag_item_quantity(item)
        if bag_after != bag_before + 1:
            shot = emu.screenshot(f"{beat_prefix}_bag_unchanged")
            raise ScenarioError(
                f"{beat_prefix}: self-switch {ssa} was set but "
                f"{item} did not reach the bag ({bag_before} -> "
                f"{bag_after}, expected +1) ({shot})"
            )

    if negative_beat:
        @builder.beat(
            f"{beat_prefix}_spent",
            f"Re-touching the spent item ball at {map_constant} event "
            f"{event_id} grants nothing (manifest {spent_row_id})",
            map_constant=map_constant, at=approach,
            group=resolved_group, archetype="item_ball", rows=(spent_row_id,),
        )
        def spent_beat(emu: Emulator) -> None:
            if not emu.flag(ssa):
                raise ScenarioError(
                    f"{beat_prefix}_spent precondition failed: {ssa} not "
                    "set -- the grant beat must run first"
                )
            bag_before = emu.bag_item_quantity(item)
            emu.walk_to(*approach)
            emu.face(facing)
            started = emu.interact(require_script=not spent_page_is_empty)
            if spent_page_is_empty and started:
                # The absence IS the assertion here: the ball is gone, so an
                # A press at its tile must hit nothing. A script running means
                # the page was emitted with a body it should not have, or the
                # self-switch never flipped and page 1 answered again.
                shot = emu.screenshot(f"{beat_prefix}_spent_unexpected_script")
                raise ScenarioError(
                    f"{beat_prefix}_spent: {spent_row_id} is an empty page, "
                    f"but interacting started a script ({shot})"
                )
            if started:
                emu.advance_dialog()
            bag_after = emu.bag_item_quantity(item)
            if bag_after != bag_before:
                shot = emu.screenshot(f"{beat_prefix}_spent_regranted")
                raise ScenarioError(
                    f"{beat_prefix}_spent: re-touching the spent ball "
                    f"changed {item} ({bag_before} -> {bag_after}), "
                    f"expected no change ({shot})"
                )

        del spent_beat
