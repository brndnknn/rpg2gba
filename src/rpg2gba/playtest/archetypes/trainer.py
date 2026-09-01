"""The `trainer` archetype beat template.

**This is the one the design decision singles out**: "a weak archetype
industrializes a weak oracle" -- a shallow assertion set here is shallow in
every trainer battle in the corpus, uniformly, and they all pass anyway.
Every fix below traces to a real, named CH04 failure (see
`playtest.chapters.ch04`'s module docstring and its `_trigger_trainer`/
`_settle_post_battle_script`/`_press_a_live` helpers, which this template
generalizes):

1. Approach is `cells.approach_to()` -- decoded, never a literal.
2. Precondition: the defeat flag must NOT already be set (fails loud if it
   is -- a beat that "passes" against an already-defeated trainer proves
   nothing).
3. Trigger dispatch is parameterized (`event_touch` / `action` /
   `player_touch`), never assumed -- 24% of the corpus is not
   `event_touch` (task brief).
4. Identity: `opponent_trainer_id()` is asserted against the expected
   trainer constant. "A battle started" is never enough -- CH04's B2 fought
   Timothy, not Larrie, and passed under that weaker check.
5. Re-talk beats read the NPC's LIVE position (`emu.object_event(local_id)`)
   when `local_id=` is supplied, not its static template cell -- an
   event-touch trainer's battle walks it toward the player, and
   `TryOverrideTemplateCoordsForObjectEvent` keeps the moved position
   (ch04.py's `_press_a_live`).
6. Post-battle settle is a real script-drain loop
   (`_settle_post_battle_script`), not a bare `field_locked()` check --
   ch03.py's B4 comment: a single guarded check can sample the flag before
   the continue script has run at all.
7. The defeat flag is asserted set after the win.
8. Each re-talk page's text is asserted non-empty AND matched against
   `text_source.expected_text` -- degrading honestly (loud log, no
   swallowed exception) on the documented `{PLAYER}`/control-code caveats.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import assertions
from ..battle import in_battle, win_battle
from ..cells import approach_to, event_cell
from ..errors import ScenarioError
from ..text_source import expected_text
from . import find_match

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
            f"trainer_beats: approach {approach} is not orthogonally "
            f"adjacent to target {target} (delta {delta}) -- "
            "cells.approach_to should never produce this"
        )
    return facing


def _trainer_defeat_flag_settle(
    emu: Emulator, beat: str, defeat_flag: str, budget: int = 1800,
) -> None:
    """Drain a post-battle continue script until `defeat_flag` reads set, or
    the budget is spent. Adapted from ch04.py's `_settle_post_battle_script`
    -- see this module's docstring point 6 for why a bare `field_locked()`
    check after `win_battle` is not enough."""
    spent = 0
    while spent < budget:
        if emu.flag(defeat_flag):
            return
        if in_battle(emu):
            win_battle(emu)
        elif emu.field_locked():
            emu.advance_dialog()
        else:
            emu.run(10)
        spent += 10
    logger.info(
        "%s: post-battle script did not set %s within %d frames",
        beat, defeat_flag, budget,
    )


def _start_trigger(
    emu: Emulator, beat: str, approach: tuple[int, int], facing: str, trigger: str,
) -> None:
    if trigger == "event_touch":
        emu.walk_to(*approach)
        emu.face(facing)
        assertions.try_step(emu, facing)
    elif trigger == "action":
        emu.walk_to(*approach)
        emu.face(facing)
        emu.interact()
    elif trigger == "player_touch":
        emu.walk_to(*approach)
        emu.face(facing)
        assertions.try_step(emu, facing)
    else:
        raise ScenarioError(
            f"{beat}: unrecognized trigger {trigger!r} -- expected "
            "'event_touch', 'action', or 'player_touch'"
        )


def trainer_beats(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    map_constant: str,
    map_id: int,
    event_id: int,
    trainer_const: str,
    defeat_flag: str,
    beat_prefix: str,
    trigger: str,
    phone: bool,
    double: bool,
    retalk_pages: int,
    rider: bool,
    approach_prefer: str | None = None,
    local_id: int | None = None,
    rider_item: str | None = None,
    manifest_rows: "tuple[ManifestRow, ...] | None" = None,
    manifest_dir=None,
) -> None:
    """Register a `trainer` archetype's whole beat set: the battle beat plus
    one re-talk beat per re-talk page the manifest says exists.

    `trigger`/`phone`/`double`/`retalk_pages`/`rider` are the author's
    stated claims about this instance -- checked against
    `chapter_manifest.archetypes.classify_manifest`'s own derivation for
    `(map_id, event_id)` and rejected loud on any disagreement, per this
    package's whole premise: the data drives the test.

    `defeat_flag`/`trainer_const` are NOT manifest-derivable (the manifest
    sees RGSS structure, not which engine mechanism -- native
    `TRAINER_FLAGS_*` bit vs. an RPG-Maker self-switch -- the transpiler
    picked for this instance), so they are plain author-supplied strings,
    exactly like every existing chapter module resolves them
    (`emu.resolve_constant`/`assertions.flag_ssa`).

    `local_id=`, if given, makes re-talk beats read the trainer's LIVE
    position (point 5 above) instead of its static approach cell -- compiled
    local ids cannot be derived from RMXP data (ch04.py's module docstring),
    so this is deliberately an opt-in author-measured parameter, not
    something this template can derive.
    """
    match = find_match(
        chapter_id, map_id, event_id, "trainer",
        rows=manifest_rows, manifest_dir=manifest_dir,
    )
    stated = {
        "trigger": trigger, "phone": phone, "double": double,
        "retalk_pages": retalk_pages, "rider": rider,
    }
    for key, value in stated.items():
        derived = match.params.get(key)
        if derived != value:
            raise ValueError(
                f"trainer_beats: {map_constant} event {event_id}: stated "
                f"{key}={value!r} disagrees with classify_manifest's "
                f"derived {key}={derived!r} -- fix the call site's "
                "parameter, not this check"
            )

    battle_row_id = next(rid for rid, role in match.roles.items() if role == "battle")
    retalk_row_ids = [rid for rid, role in match.roles.items() if role == "retalk"]
    if len(retalk_row_ids) != retalk_pages:
        raise ValueError(
            f"trainer_beats: {map_constant} event {event_id}: match has "
            f"{len(retalk_row_ids)} retalk rows but retalk_pages={retalk_pages} "
            "-- classify_manifest and the stated count disagree (this "
            "should be unreachable given the params check above; if it "
            "fires, the archetype classifier's own invariant broke)"
        )

    approach = approach_to(map_constant, event_id, prefer=approach_prefer)
    facing = _facing_toward(approach, event_cell(map_constant, event_id))

    @builder.beat(
        f"{beat_prefix}_battle",
        f"Trainer battle at {map_constant} event {event_id} fires and is "
        f"won; {defeat_flag} latches the defeated state "
        f"(manifest {battle_row_id})",
        map_constant=map_constant, at=approach,
        archetype="trainer", rows=(battle_row_id,),
    )
    def battle_beat(emu: Emulator) -> None:
        if emu.flag(defeat_flag):
            raise ScenarioError(
                f"{beat_prefix}_battle precondition failed: {defeat_flag} "
                "already set before the fight"
            )
        _start_trigger(emu, f"{beat_prefix}_battle", approach, facing, trigger)
        if not emu.field_locked() and not in_battle(emu):
            # A second nudge for the `action` trainers (61 of the corpus's
            # 299), where stepping adjacent is not itself the trigger. This
            # `interact` is allowed to fail: it is a retry, not the oracle.
            # Swallowing it is bounded rather than silent -- if no battle
            # results, the explicit check immediately below fails loud with
            # a screenshot, so a genuine miss cannot reach a green beat.
            try:
                emu.interact()
            except ScenarioError as exc:
                logger.debug(
                    "%s: follow-up interact() at %s did not take (%s); the "
                    "battle check below decides",
                    f"{beat_prefix}_battle", approach, exc,
                )
        assertions.advance_to_battle(emu)
        if not in_battle(emu):
            shot = emu.screenshot(f"{beat_prefix}_battle_no_battle")
            raise ScenarioError(
                f"{beat_prefix}_battle: trigger {trigger!r} at {approach} "
                f"never started a battle ({shot})"
            )
        if not emu.is_trainer_battle():
            shot = emu.screenshot(f"{beat_prefix}_battle_wild_not_trainer")
            raise ScenarioError(
                f"{beat_prefix}_battle: a battle started at {approach} but "
                f"it isn't a trainer battle ({shot})"
            )
        expected = emu.resolve_constant(trainer_const)
        actual = emu.opponent_trainer_id()
        if actual != expected:
            shot = emu.screenshot(f"{beat_prefix}_battle_wrong_trainer")
            raise ScenarioError(
                f"{beat_prefix}_battle: a trainer battle started at "
                f"{approach}, but against trainer id {actual}, not "
                f"{trainer_const} ({expected}) -- never trust 'a battle "
                f"started' alone ({shot})"
            )
        bag_before = (
            emu.bag_item_quantity(rider_item) if rider and rider_item else None
        )
        party = win_battle(emu)
        logger.info(
            "%s: enemy party at battle start: %s", f"{beat_prefix}_battle",
            [(m.species, m.level) for m in party],
        )
        _trainer_defeat_flag_settle(emu, f"{beat_prefix}_battle", defeat_flag)
        if not emu.flag(defeat_flag):
            shot = emu.screenshot(f"{beat_prefix}_battle_not_defeated")
            raise ScenarioError(
                f"{beat_prefix}_battle: {defeat_flag} not set after the win "
                f"({shot})"
            )
        if bag_before is not None:
            bag_after = emu.bag_item_quantity(rider_item)
            if bag_after != bag_before + 1:
                shot = emu.screenshot(f"{beat_prefix}_battle_rider_missing")
                raise ScenarioError(
                    f"{beat_prefix}_battle: rider item {rider_item} "
                    f"{bag_before}->{bag_after}, expected +1 ({shot})"
                )

    for page_idx, retalk_row_id in enumerate(sorted(retalk_row_ids), start=1):
        _register_retalk_beat(
            builder, beat_prefix=beat_prefix, page_idx=page_idx,
            retalk_row_id=retalk_row_id, map_id=map_id, event_id=event_id,
            map_constant=map_constant, approach=approach, facing=facing,
            defeat_flag=defeat_flag, local_id=local_id,
        )


def _register_retalk_beat(
    builder: ChapterBuilder, *, beat_prefix: str, page_idx: int,
    retalk_row_id: str, map_id: int, event_id: int, map_constant: str,
    approach: tuple[int, int], facing: str, defeat_flag: str,
    local_id: int | None,
) -> None:
    name = f"{beat_prefix}_retalk{page_idx}"

    @builder.beat(
        name,
        f"Re-talk page {page_idx} of {map_constant} event {event_id} after "
        f"defeat (manifest {retalk_row_id})",
        map_constant=map_constant, at=approach,
        archetype="trainer", rows=(retalk_row_id,),
    )
    def retalk_beat(emu: Emulator) -> None:
        if not emu.flag(defeat_flag):
            raise ScenarioError(
                f"{name} precondition failed: {defeat_flag} not set -- "
                "the battle beat must run first"
            )
        if local_id is not None:
            _press_a_live(emu, name, local_id, facing)
        else:
            emu.walk_to(*approach)
            emu.face(facing)
            emu.interact()
        try:
            expected = expected_text(map_id, event_id, page_idx)
        except ValueError:
            logger.warning(
                "%s: text_source.expected_text could not translate this "
                "page's control codes -- degrading to a non-empty check "
                "only (exact-text oracle unavailable for this page)",
                name,
            )
            actual = emu.current_field_message_text()
            if not actual or not actual.strip():
                shot = emu.screenshot(f"{name}_empty_text")
                raise ScenarioError(
                    f"{name}: re-talk text is empty and the exact-text "
                    f"oracle was unavailable for this page ({shot})"
                ) from None
        else:
            if "{PLAYER}" in expected:
                before, _, after = expected.partition("{PLAYER}")
                emu.assert_text_contains(before)
                if after:
                    emu.assert_text_contains(after)
            else:
                emu.assert_text_contains(expected, exact=True)
        emu.advance_dialog()
        if emu.field_locked():
            shot = emu.screenshot(f"{name}_stuck")
            raise ScenarioError(
                f"{name}: re-talk did not close cleanly ({shot})"
            )

    del retalk_beat  # registered via the decorator; nothing else references it


def _press_a_live(
    emu: Emulator, beat: str, local_id: int, facing: str, max_attempts: int = 3,
) -> None:
    """Byte-adapted from ch04.py's `_press_a_live` -- reads the NPC's live
    `gObjectEvents` position rather than trusting its template cell, for a
    trainer that walked toward the player on trigger and kept the moved
    position (point 5 in this module's docstring)."""
    dx, dy = {"DOWN": (0, 1), "UP": (0, -1), "LEFT": (-1, 0), "RIGHT": (1, 0)}[facing]
    for _ in range(max_attempts):
        ev = emu.object_event(local_id)
        emu.walk_to(ev.x - dx, ev.y - dy)
        emu.face(facing)
        try:
            emu.interact()
            return
        except ScenarioError:
            continue
    shot = emu.screenshot(f"{beat}_live_no_interact")
    raise ScenarioError(
        f"{beat}: could not interact with local id {local_id} after "
        f"{max_attempts} attempts reading its live position ({shot})"
    )
