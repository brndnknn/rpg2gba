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
8. Each re-talk page's text is asserted, box by box, against the generic
   beat floor's own `text` assertions (REDERIVATION_PLAN.md §16.3 C5) --
   degrading honestly (loud log, non-empty check only) when the floor has
   none for that row (refused, or `text_unnormalizable`).

**C5 (REDERIVATION_PLAN.md §16.3):** every beat this template registers
passes `assertions=declare_assertions(...)`, so the checker's ⊇-floor rule
can compare what the body actually checks against what the RMXP source
implies. See the block comment above `_NATIVE_TRAINER_FLAG_RE` for the
declared-kinds story per beat.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .. import assertions
from ..battle import in_battle, win_battle
from ..cells import approach_to, event_cell
from ..errors import ScenarioError
from . import FloorLookup, declare_assertions, facing_toward, find_match
from ...beat_floor.assertion import FloorAssertion
from ...beat_floor.lookup import default_build_dir
from ...conversion_agent.flag_registry import self_switch_flag_name
from ...pbs_converter._naming import to_constant
from ...trainer_converter.battles import load_trainers_json

if TYPE_CHECKING:  # runtime import is lazy so this module works without bindings
    from ...chapter_manifest.schema import ManifestRow
    from ..chapter import ChapterBuilder
    from ..emulator import Emulator

logger = logging.getLogger(__name__)


# -- C5: declared assertions (REDERIVATION_PLAN.md §16.3 C5) -----------------
#
# The trainer archetype's floor-vs-declared story, in one place:
#
# 1. `battle` (identity): the floor's `battle` assertion on the battle page
#    row carries the RMXP source's own literal identity -- `trainer_type`
#    (the PBTrainers:: class symbol) and `name` (the display-name string),
#    never a party id (the corpus's `pbTrainerBattle` calls all pass it
#    positionally but the floor extractor -- `beat_floor/condition.py`'s
#    `_extract_pb_trainer_battle` -- does not capture it; see that module).
#    The author's `trainer_const` is therefore validated in the OTHER
#    direction: resolve it forward through `trainers.json` (the same table
#    `conversion_agent.deterministic.load_context` builds `ctx.trainers`
#    from) and check ITS recorded `trainer_class`/`name` agree with what the
#    floor derived from source -- no party id needed, because this doesn't
#    need to reconstruct the trainers.json lookup key, only confirm the
#    author's already-resolved answer against the same table.
# 2. `battle` (defeat write): every CH01-CH05 sight-trainer instance the
#    corpus has (`_TRAINER_BATTLE_RE` shape, RMXP self-switch A ON in the
#    win branch) is ROUTED, at conversion time, through
#    `conversion_agent.deterministic.classify_trainer_battle`'s
#    `trainerbattle_single` (or the phone-rematch idiom's
#    `trainerbattle_rematch`) -- both REQUIRE that exact self-switch shape
#    structurally (`has_self_switch`) but never re-emit it as a checkable
#    flag write: the native pokeemerald trainer-flags bit
#    (`TRAINER_FLAGS_START + <trainer_const>`, `ch04.py`'s own
#    `_trainer_defeat_flag`) takes over instead. There is no `AssertionKind`
#    for "the native trainer-flags bit got set" -- it isn't a
#    `story_state.state.Switch`/`SelfSwitch` write at all -- so a
#    `defeat_flag` matching that native shape declares NOTHING for the win
#    branch; that is the honest answer, not a gap. A `defeat_flag` that is
#    instead a plain `FLAG_MAP<map>_EVENT<event>_SS<letter>` (reconstructed
#    via `flag_registry.self_switch_flag_name`, matched against a REAL
#    `self_switch_write` floor assertion on one of the battle row's branch
#    rows) IS declared, on that branch row.
# 3. `text`: the pre-battle intro box the floor sees (the row's own `text`
#    kind) is declared when every `text` assertion on the battle row sits
#    before its `battle` assertion -- the body reads each intro box off the
#    field message before `advance_to_battle` dismisses it (2026-09-24, C9
#    grading). A row with text after the battle is left undeclared: the body
#    has no post-battle field read to back it. Every CH01-CH05 trainer's
#    battle row has exactly one intro box and nothing after.
# 4. `item_grant`: only declared when `rider=True` and the body's
#    before/after bag-count check is for the SAME item the floor's
#    `item_grant` assertion names (validated via the same internal-name ->
#    `ITEM_*` table `deterministic._load_item_symbols` builds).


_NATIVE_TRAINER_FLAG_RE = re.compile(r"^\s*TRAINER_FLAGS_START\s*\+\s*(\S+)\s*$")


def _resolve_floor_lookup(
    floor_lookup: FloorLookup | None, build_dir: Path | None,
) -> FloorLookup:
    if floor_lookup is not None:
        return floor_lookup
    from ...beat_floor.lookup import floor_for_row

    return lambda row_id: floor_for_row(row_id, build_dir=build_dir)


def _validate_battle_identity(
    battle_row_id: str, trainer_const: str, *,
    floor_lookup: FloorLookup, build_dir: Path | None,
) -> str | None:
    """`None` when `trainer_const` is confirmed, through `trainers.json`,
    to name the same (trainer_class, display name) the floor's `battle`
    assertion derived from the RMXP `pbTrainerBattle` call itself. Otherwise
    a reason `battle` cannot be declared (no floor assertion, no
    `trainers.json` to check against) -- never raised for those, only
    logged; raises `ValueError` for a genuine identity MISMATCH, per this
    package's fail-loud convention (module docstring point 4)."""
    floor = floor_lookup(battle_row_id)
    if floor.refused:
        return f"floor for {battle_row_id} is refused"
    battles = [a for a in floor.assertions if a.kind == "battle"]
    if not battles:
        return f"no 'battle' floor assertion on {battle_row_id}"
    battle = battles[0]
    if battle.param("kind") != "trainer":
        return f"floor battle kind is {battle.param('kind')!r}, not 'trainer'"
    trainer_type = battle.param("trainer_type")
    name = battle.param("name")
    expected_class = to_constant("TRAINER_CLASS", trainer_type)

    resolved_build_dir = build_dir if build_dir is not None else default_build_dir()
    trainers_path = Path(resolved_build_dir) / "intermediate" / "trainers.json"
    if not trainers_path.is_file():
        return f"no trainers.json at {trainers_path} to confirm trainer_const"
    trainers = load_trainers_json(trainers_path.parent)
    entry = trainers.get(trainer_const)
    if entry is None:
        return f"trainer_const {trainer_const!r} not found in trainers.json"
    if entry.get("trainer_class") != expected_class or entry.get("name") != name:
        raise ValueError(
            f"trainer_beats: {battle_row_id}: trainer_const {trainer_const!r} "
            f"resolves in trainers.json to trainer_class="
            f"{entry.get('trainer_class')!r} name={entry.get('name')!r}, but "
            f"the source pbTrainerBattle floor assertion says class "
            f"{expected_class!r} name {name!r} -- fix the call site's "
            "trainer_const"
        )
    return None


def _defeat_write_declaration(
    battle_row_id: str, trainer_const: str, defeat_flag: str, *,
    map_id: int, event_id: int, floor_lookup: FloorLookup,
) -> tuple[str, str] | None:
    """`(row_id, kind)` to declare for the defeat-flag write `defeat_flag`
    names, or `None` when nothing in the floor's vocabulary models it (see
    module docstring point 2). Only `self_switch_write` is recognized today
    -- no CH01-CH05 instance's `defeat_flag` is a plain native `FLAG_*`
    backed by a `switch_write` (every non-native case staged so far is the
    self-switch shape); a future one would need the same treatment added
    here, not silently declared."""
    native = _NATIVE_TRAINER_FLAG_RE.match(defeat_flag)
    if native and native.group(1) == trainer_const:
        return None
    for i in range(8):
        row_id = f"{battle_row_id}/b{i}"
        try:
            floor = floor_lookup(row_id)
        except KeyError:
            break
        if floor.refused:
            continue
        for a in floor.assertions:
            if a.kind != "self_switch_write":
                continue
            if a.param("event_id") != event_id:
                continue
            expected = self_switch_flag_name(map_id, a.param("event_id"), a.param("letter"))
            if expected == defeat_flag:
                return row_id, "self_switch_write"
    return None


def _validate_rider_item_grant(
    battle_row_id: str, rider_item: str, *,
    floor_lookup: FloorLookup, reference_dir: Path | None,
) -> str | None:
    """Mirrors `_validate_battle_identity` for the rider item: `None` when
    `rider_item` is confirmed against the floor's `item_grant` assertion
    (resolved through the same internal-name -> `ITEM_*` table
    `conversion_agent.deterministic._load_item_symbols` builds); otherwise a
    reason it cannot be declared. Raises `ValueError` on a genuine
    mismatch."""
    from ...conversion_agent.deterministic import _load_item_symbols

    floor = floor_lookup(battle_row_id)
    if floor.refused:
        return f"floor for {battle_row_id} is refused"
    grants = [a for a in floor.assertions if a.kind == "item_grant"]
    if not grants:
        return f"no 'item_grant' floor assertion on {battle_row_id}"
    grant = grants[0]
    resolved_reference_dir = reference_dir if reference_dir is not None else Path("reference")
    symbols = _load_item_symbols(resolved_reference_dir)
    expected = symbols.get(grant.param("item"))
    if expected is None:
        return (
            f"item symbol {grant.param('item')!r} not found in "
            f"{resolved_reference_dir}/uranium_data item tables"
        )
    if expected != rider_item:
        raise ValueError(
            f"trainer_beats: {battle_row_id}: rider_item {rider_item!r} "
            f"disagrees with the source item_grant {grant.param('item')!r} "
            f"(resolves to {expected!r}) -- fix the call site's rider_item"
        )
    return None


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


#: Frames to wait for a trainer's intro box: the "!" emote plus a walk across
#: the trainer's whole sight range (16 frames a tile) with room to spare.
_INTRO_FRAME_BUDGET = 600


def _intro_text_assertions(
    battle_row_id: str, floor_lookup: FloorLookup,
) -> tuple[tuple[FloorAssertion, ...], str | None]:
    """The battle row's pre-battle `text` assertions in source order, and
    None -- or `()` and the reason `text` can't be declared (point 3)."""
    try:
        floor = floor_lookup(battle_row_id)
    except KeyError as exc:
        return (), f"no floor for {battle_row_id} ({exc})"
    if floor.refused:
        return (), f"floor for {battle_row_id} is refused"
    battles = [a.list_index for a in floor.assertions if a.kind == "battle"]
    texts = tuple(sorted(
        (a for a in floor.assertions if a.kind == "text"), key=lambda a: a.list_index))
    if not texts:
        return (), f"floor has no 'text' assertions for {battle_row_id}"
    if not battles:
        return (), f"floor has no 'battle' assertion on {battle_row_id} to order text against"
    after = [a for a in texts if a.list_index > min(battles)]
    if after:
        return (), (f"{len(after)} text assertion(s) follow the battle on "
                    f"{battle_row_id}; the body has no post-battle field read")
    return texts, None


def _assert_floor_text(emu: Emulator, expected: str) -> None:
    """Assert the open field message against one floor `text` param. The
    engine expands `{PLAYER}` to the player's name, so a line carrying it is
    checked as the text either side of the placeholder."""
    if "{PLAYER}" in expected:
        before, _, after = expected.partition("{PLAYER}")
        emu.assert_text_contains(before)
        if after:
            emu.assert_text_contains(after)
    else:
        emu.assert_text_contains(expected, exact=True)


def _approach(emu: Emulator, approach: tuple[int, int]) -> bool:
    """Walk to the trainer's approach cell, tolerating the trainer firing on
    the way. Returns whether the approach was interrupted.

    A touch trainer's range can reach the approach cell itself, so the walk
    that gets into position is the same motion that triggers him -- the field
    locks mid-walk and `walk_to` raises `WalkInterrupted`. CH05's B3 (Hiker
    Manny) is the case: "walk_to(19, 29) interrupted by a locked-field scene
    at (19, 29)". Nothing went wrong there; the beat got what it came for one
    step earlier than the template expected.

    Deliberately NOT `resolve_interruptions=True`. That resolves the
    interruption and walks on, which for a trainer beat would fight the battle
    inside the movement helper and leave the assertions below nothing to
    inspect. Here the interruption is caught and handed straight to those
    assertions, which still check a battle is running, that it is a TRAINER
    battle, and that the opponent id is the expected one -- so an ambush by
    the wrong trainer on the way in still fails loud. That guard is CH04 B3's
    legacy and this must not weaken it.
    """
    # Imported here, not at module scope: `WalkInterrupted` lives in
    # `emulator.py`, which hard-imports `mgba`, and this module is deliberately
    # importable without the bindings (see the TYPE_CHECKING guard above). By
    # the time this runs there is a real emulator in hand.
    from ..emulator import WalkInterrupted

    try:
        emu.walk_to(*approach)
    except WalkInterrupted as exc:
        logger.info(
            "approach to %s was interrupted at %s -- the trainer fired during "
            "the walk; the battle assertions decide whether it was the right "
            "one", approach, exc.stopped_at)
        return True
    return False


def _start_trigger(
    emu: Emulator, beat: str, approach: tuple[int, int], facing: str, trigger: str,
) -> None:
    if trigger in ("event_touch", "player_touch"):
        if _approach(emu, approach):
            return  # already triggered; a second nudge would be a second fight
        emu.face(facing)
        assertions.try_step(emu, facing)
    elif trigger == "action":
        if _approach(emu, approach):
            return
        emu.face(facing)
        emu.interact()
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
    group: str | None = None,
    manifest_rows: "tuple[ManifestRow, ...] | None" = None,
    manifest_dir=None,
    build_dir: Path | None = None,
    floor_lookup: FloorLookup | None = None,
    reference_dir: Path | None = None,
) -> None:
    """Register a `trainer` archetype's whole beat set: the battle beat plus
    one re-talk beat per re-talk page the manifest says exists.

    `group=` defaults to `beat_prefix` when omitted, so the battle beat and
    every re-talk beat form one indivisible route-solver stop, matching what
    a hand-authored chapter does today (`ChapterBuilder.beat`'s `group=`
    docstring). The battle beat is named exactly `beat_prefix` (not
    `f"{beat_prefix}_battle"`) because the chapter manifest dispositions this
    stop as bare `beat:{beat_prefix}`, and `_check_route_approach` looks up a
    node's beats by that exact name (`chapter_manifest/checker.py`,
    `RouteModel.declared_beat_cell`) -- the battle beat *is* the stop the
    disposition names. Re-talk beats keep their descriptive `_retalk{n}`
    suffixes; they are satellites of the stop, not the stop's own identity.

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
    facing = facing_toward(
        approach, event_cell(map_constant, event_id), caller="trainer_beats")
    resolved_group = group if group is not None else beat_prefix

    resolved_lookup = _resolve_floor_lookup(floor_lookup, build_dir)

    executed_kinds = {"trigger", "completes"}
    extra_rows: list[str] = []

    battle_reason = _validate_battle_identity(
        battle_row_id, trainer_const, floor_lookup=resolved_lookup, build_dir=build_dir)
    if battle_reason is None:
        executed_kinds.add("battle")
    else:
        logger.info("%s: not declaring 'battle' -- %s", beat_prefix, battle_reason)

    defeat_write = _defeat_write_declaration(
        battle_row_id, trainer_const, defeat_flag, map_id=map_id,
        event_id=event_id, floor_lookup=resolved_lookup)
    if defeat_write is not None:
        write_row_id, write_kind = defeat_write
        extra_rows.append(write_row_id)
        executed_kinds.add(write_kind)
    else:
        logger.info(
            "%s: not declaring a state-write for defeat_flag=%r -- either the "
            "native TRAINER_FLAGS bit (consumed from the source self-switch by "
            "trainerbattle_single/_rematch, no floor kind models it) or no "
            "branch row's write matches it", beat_prefix, defeat_flag)

    intro_texts, intro_reason = _intro_text_assertions(battle_row_id, resolved_lookup)
    if intro_reason is None:
        executed_kinds.add("text")
    else:
        logger.info("%s: not declaring 'text' -- %s", beat_prefix, intro_reason)

    if rider and rider_item:
        item_reason = _validate_rider_item_grant(
            battle_row_id, rider_item, floor_lookup=resolved_lookup,
            reference_dir=reference_dir)
        if item_reason is None:
            executed_kinds.add("item_grant")
        else:
            logger.info("%s: not declaring 'item_grant' -- %s", beat_prefix, item_reason)

    battle_rows = (battle_row_id, *extra_rows)
    declared = declare_assertions(
        battle_rows, executed_kinds=frozenset(executed_kinds),
        template=beat_prefix, floor_lookup=resolved_lookup)
    battle_archetype = {battle_row_id: "trainer"} if extra_rows else "trainer"

    @builder.beat(
        beat_prefix,
        f"Trainer battle at {map_constant} event {event_id} fires and is "
        f"won; {defeat_flag} latches the defeated state "
        f"(manifest {battle_row_id})",
        map_constant=map_constant, at=approach,
        group=resolved_group, archetype=battle_archetype, rows=battle_rows,
        assertions=declared,
    )
    def battle_beat(emu: Emulator) -> None:
        if emu.flag(defeat_flag):
            raise ScenarioError(
                f"{beat_prefix} precondition failed: {defeat_flag} "
                "already set before the fight"
            )
        _start_trigger(emu, beat_prefix, approach, facing, trigger)
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
                    beat_prefix, approach, exc,
                )
        for a in intro_texts:
            # The box comes up only after the "!" and the trainer's walk to
            # the player, which can outlast wait_for_field_message's default.
            if emu.wait_for_field_message(frame_budget=_INTRO_FRAME_BUDGET) is None:
                shot = emu.screenshot(f"{beat_prefix}_no_intro_text")
                raise ScenarioError(
                    f"{beat_prefix}: no intro message box appeared before the "
                    f"battle; expected {a.param('text')!r} ({shot})")
            _assert_floor_text(emu, a.param("text"))
            if a is not intro_texts[-1]:
                emu.clear_field_message()
                emu.tap("A")
        assertions.advance_to_battle(emu)
        if not in_battle(emu):
            shot = emu.screenshot(f"{beat_prefix}_no_battle")
            raise ScenarioError(
                f"{beat_prefix}: trigger {trigger!r} at {approach} "
                f"never started a battle ({shot})"
            )
        if not emu.is_trainer_battle():
            shot = emu.screenshot(f"{beat_prefix}_wild_not_trainer")
            raise ScenarioError(
                f"{beat_prefix}: a battle started at {approach} but "
                f"it isn't a trainer battle ({shot})"
            )
        expected = emu.resolve_constant(trainer_const)
        actual = emu.opponent_trainer_id()
        if actual != expected:
            shot = emu.screenshot(f"{beat_prefix}_wrong_trainer")
            raise ScenarioError(
                f"{beat_prefix}: a trainer battle started at "
                f"{approach}, but against trainer id {actual}, not "
                f"{trainer_const} ({expected}) -- never trust 'a battle "
                f"started' alone ({shot})"
            )
        bag_before = (
            emu.bag_item_quantity(rider_item) if rider and rider_item else None
        )
        party = win_battle(emu)
        logger.info(
            "%s: enemy party at battle start: %s", beat_prefix,
            [(m.species, m.level) for m in party],
        )
        _trainer_defeat_flag_settle(emu, beat_prefix, defeat_flag)
        if not emu.flag(defeat_flag):
            shot = emu.screenshot(f"{beat_prefix}_not_defeated")
            raise ScenarioError(
                f"{beat_prefix}: {defeat_flag} not set after the win "
                f"({shot})"
            )
        if bag_before is not None:
            bag_after = emu.bag_item_quantity(rider_item)
            if bag_after != bag_before + 1:
                shot = emu.screenshot(f"{beat_prefix}_rider_missing")
                raise ScenarioError(
                    f"{beat_prefix}: rider item {rider_item} "
                    f"{bag_before}->{bag_after}, expected +1 ({shot})"
                )

    for page_idx, retalk_row_id in enumerate(sorted(retalk_row_ids), start=1):
        _register_retalk_beat(
            builder, beat_prefix=beat_prefix, page_idx=page_idx,
            retalk_row_id=retalk_row_id,
            map_constant=map_constant, approach=approach, facing=facing,
            defeat_flag=defeat_flag, local_id=local_id, group=resolved_group,
            floor_lookup=resolved_lookup,
        )


def _register_retalk_beat(
    builder: ChapterBuilder, *, beat_prefix: str, page_idx: int,
    retalk_row_id: str, map_constant: str,
    approach: tuple[int, int], facing: str, defeat_flag: str,
    local_id: int | None, group: str, floor_lookup: FloorLookup,
) -> None:
    name = f"{beat_prefix}_retalk{page_idx}"

    executed_kinds = {"trigger", "completes"}
    text_assertions: tuple[FloorAssertion, ...] = ()
    try:
        floor = floor_lookup(retalk_row_id)
    except KeyError as exc:
        logger.info(
            "%s: no floor for %s (%s) -- degrading to a non-empty text check",
            name, retalk_row_id, exc)
        floor = None
    if floor is not None:
        if floor.refused:
            logger.info(
                "%s: floor for %s is refused (%s) -- degrading to a "
                "non-empty text check", name, retalk_row_id,
                [r.reason for r in floor.refusals])
        else:
            text_assertions = tuple(sorted(
                (a for a in floor.assertions if a.kind == "text"),
                key=lambda a: a.list_index))
            if text_assertions:
                executed_kinds.add("text")
            else:
                logger.info(
                    "%s: floor has no 'text' assertions for %s -- "
                    "degrading to a non-empty text check", name, retalk_row_id)

    declared = declare_assertions(
        (retalk_row_id,), executed_kinds=frozenset(executed_kinds),
        template=name, floor_lookup=floor_lookup)

    @builder.beat(
        name,
        f"Re-talk page {page_idx} of {map_constant} after "
        f"defeat (manifest {retalk_row_id})",
        map_constant=map_constant, at=approach,
        group=group, archetype="trainer", rows=(retalk_row_id,),
        assertions=declared,
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
        if text_assertions:
            for a in text_assertions:
                _assert_floor_text(emu, a.param("text"))
                emu.advance_dialog()
        else:
            actual = emu.current_field_message_text()
            if not actual or not actual.strip():
                shot = emu.screenshot(f"{name}_empty_text")
                raise ScenarioError(
                    f"{name}: re-talk text is empty and no floor text "
                    f"oracle was available for this page ({shot})"
                )
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
