"""Chapter 5 -- Passage Cave (`reference/chapters/05-passage-cave.md`).

Predecessor-chained onto `route2` (CH04): `route2.build()`'s own beats
(Larrie/Timothy/the rockslide/wild grass, ending on `MAP_ROUTE_02`) are
prepended. CH05 covers Passage Cave 1F and 2F, Uranium map ids 36 and 37
(`MAP_PASSAGE_CAVE_1F` / `MAP_PASSAGE_CAVE_2F`), the first two maps to enter
`SLICE_MAP_IDS` after CH04's own map 35.

**This module was authored against an approved route plan, not from a blank
page.** `reference/routes/CH05.route.json` (STOP 3, operator-approved) fixes
the beat-GROUP order and, for the approach-sensitive stops, which SIDE of
the target the solver committed to (`chosen_approach`). Every group below
registers in that order, using the exact resolver call
`reference/routes/CH05.locations.json` records for it -- this file is
transcription of an already-reviewed plan, not fresh derivation.

**Why the four archetype templates
(`playtest.archetypes.{item_ball,trainer,warp,arrival_nudge}`) are NOT
called directly here, even though every beat below matches one of them.**
`chapter_manifest.checker.RULE_ROUTE_APPROACH` looks up a beat by its EXACT
registered NAME (`route_model.PlanRouteModel.declared_beat_cell`, keyed on
`Beat.name`), and the approved plan's `chosen_approach` nodes each cover a
group whose `beats` list is the single bare id from
`CH05.dispositions.json` (`"B2"`, `"B3"`, ... -- see
`routing.locations.chapter_from_locations`, which gives every derived beat
its own singleton group named after itself). None of the four template
functions expose a `group=` parameter, and each always suffixes its beat
names (`f"{beat_prefix}_grant"`, `f"{beat_prefix}_battle"`, ...) -- calling
one verbatim would (a) create a NEW singleton group per suffix, which
`RULE_ROUTE_ORDER` would then report as "registered but not in the planned
order" for every group with more than one row, and (b) leave
`declared_beat_cell("B2")` finding nothing (no beat is ever literally named
`"B2"`), degrading the whole group's approach check to
`RULE_ROUTE_MODEL_UNENFORCED` instead of a real pass. So every group below
is hand-written with an EXACT-match primary beat name (`"B2"`, `"B3"`, ...)
plus an explicit `group=` tying its sibling rows (spent page / re-talk page
/ nudge) into one contiguous stop -- the same assertions the templates would
make (grant/spent bag deltas, trainer identity, nudge displacement), just
without the templates' fixed naming. This is a real, load-bearing gap
between the router's naming assumptions and the templates' naming
convention, worth carrying to `PROJECT_TODO.md`, not something to paper
over in this file.

**Trainers are native, not self-switch-gated.** Per `CH05_TODO.md` step 1,
`TRAINER_MANNY_5` / `TRAINER_KEICHI_248` / `TRAINER_NUNES_128` are staged
into `SLICE_TRAINER_BATTLES` as ordinary `trainerbattle_single` instances --
unlike CH04's Larrie (a phone-rematch idiom needing an RPG-Maker self-switch
flag), their defeat state is the engine's own `TRAINER_FLAGS_START + <id>`
bit, set inside the battle before any script runs, so it can be read the
instant `win_battle` returns (no post-battle-script settle needed, unlike
CH04's Larrie).

**Trigger dispatch is a hedge, not a confirmed fact.** The manifest
describes these three trainers as event-sight (`pbNoticePlayer`), which
CH04's own module docstring found ambiguous for its own roster (some
compiled trigger=2 "Event Touch", but the *engine's* compiled dispatch
mechanism for a solid NPC was unconfirmed at authoring time). `_trigger_trainer`
below reuses CH04's resolution: try a bump first, fall back to `interact()`,
and only fail if neither produces a trainer battle against the RIGHT
trainer id. Untested against a real ROM at authoring time -- flagged, not
guessed away.

**Re-talk beats use the STATIC approach cell, not a measured live position.**
CH04 found that an event-touch trainer's battle walks it toward the player
and the compiled engine keeps the moved position afterward
(`TryOverrideTemplateCoordsForObjectEvent`), so its own re-talk beats read a
measured `local_id`/live position instead of trusting the template cell.
No such measurement exists yet for Manny/Keichi/Nunes (this is the first
build; nothing has boot-walked). Re-talk beats below approach the STATIC
cell -- a real risk that the trainer has moved and the re-talk beat cannot
reach it, deliberately accepted per the task brief's "prefer a weaker but
correct assertion" over inventing an unverified `local_id`. If the boot walk
finds this wrong, the fix is the same `_press_a_live`-style live-position
read CH04 already has, not a new mechanism.

**Re-talk/gift text is asserted non-empty, never against a literal string.**
Unlike CH04 (whose re-talk lines were already public via the manifest and
its own module docstring), this repo's standing rule
(`feedback-avoid-uranium-spoilers`) is that the build agent does not quote
Uranium dialogue in files a human reviews casually. `emu.assert_text_contains`
against a real string would require transcribing one; a non-empty-text check
is the honest, weaker substitute.

**B13/B14 (the sideways staircases) use `raw_cell()`.** `playtest.cells` has
no `stair_approach` resolver -- deliberately, per its own module docstring
and `routing.locations`' -- because a stair's routing point (the E/W
neighbour owning the `stair_diagonal` edge) has no `prefer=`-style side
parameter in the sanctioned vocabulary. The two values below
((10,9) west-of-stair-(11,9), (19,9) west-of-stair-(20,9)) are copied
verbatim from `reference/routes/CH05.locations.json`'s own
`stair_approach(...)` derivation, itself built from
`traversal.graph.build_map_graph`'s real `stair_diagonal` edges -- not
guessed, not hand-measured against a screenshot, just outside the five
resolvers this module is allowed to call directly. Two calls total, both
cited here.

**B6/B7 (TM76, Sableyeite) are not authored at all.** Both are
`blocked:surf`, `assertable=false` in `CH05.dispositions.json` -- the sealed
30-tile room they sit in has no walkable approach under the offline
traversal graph, so there is no negative beat to write (contrast CH04's
Rock Smash rows, which had an open south face). Surf itself is not granted
until Act 5 (map 143); this room is the corpus's longest-standing capability
deferral.

**B1 and B8 are warp round trips, not one-way crossings** (operator
convention, 2026-09-04): a warp is tested by crossing it, crossing back, and
crossing again, ending on the far side. B1 additionally exercises CH04's own
permanently-deferred nudge on the Route 2 side
(`ch04.b8_autorun_deferred`'s row, `map035/ev001/p1`) -- under the boundary
convention an outgoing chapter delivers the player to the edge and the
ARRIVING chapter (this one) asserts the crossing, so B1 claims that row too
even though it is generated from a different chapter's manifest. B8's own
nudge (`map036/ev002/p1`) is claimed by the sibling beat `B8_nudge`
(same `group="B8"`), because a `Beat` can carry only one `archetype=` tag
and B8's own rows are tagged `"warp"`.

**A genuine cross-chapter continuity risk, noted and not resolved here.**
`playtest.runner._check_beat_continuity` compares each beat's declared
`at=` against wherever the PREVIOUS beat (including inherited predecessor
beats) actually left the player, checked strictly, at run time. CH04's own
last own-beat (`B15`, the wild-grass encounter) leaves the player somewhere
in the grass south of the rockslide, not at B1's declared entry
(`event_cell(MAP_PASSAGE_CAVE_1F, 1)`, deep inside the cave) -- the two
cannot literally agree, since B1's own body is what walks the player from
the Route 2 side to the cave mouth and crosses. Whether the runner tolerates
this (or whether CH04 already has the same latent gap for its own first
beat after CH03) is a `playtest.runner`/harness question, out of this file's
scope and not exercised by any of this task's own verification commands
(`routing plan --dry-run`, `chapter_manifest check`, `pytest`, `ruff`) --
flagged for whoever runs Step 7's real ROM build.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...traversal.direction import CARDINALS, Direction
from .. import assertions
from ..battle import in_battle, win_battle
from ..cells import approach_to, arrival_cell, event_cell, raw_cell, warp_cell
from ..chapter import ChapterBuilder
from ..errors import ScenarioError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from ..emulator import Emulator

ch05 = ChapterBuilder("CH05", doc="reference/chapters/05-passage-cave.md",
                        predecessor="CH04")

MAP_1F = "MAP_PASSAGE_CAVE_1F"
MAP_2F = "MAP_PASSAGE_CAVE_2F"
ROUTE_2_CONST = "MAP_ROUTE_02"  # CH04's own map constant; see module docstring's B1

# -- shared helpers, adapted from ch04.py (chapter-local by design, per
# assertions.py's own docstring on what deliberately does not get promoted --
# a wild-encounter-aware absorbing walk is Route/Cave specific tuning, not a
# corpus-wide primitive) --------------------------------------------------

_MAX_ABSORBED_INTERRUPTIONS = 12
_WALK_ABSORBING_FRAME_BUDGET = 6000

# Keyed on `traversal.direction.Direction` members, never a bare (dx, dy)
# tuple literal -- CH05 is the first chapter born under the D1 zero-tolerance
# ban (`tests/test_chapter_coordinate_literals.py`), which flags ANY
# two-int-constant tuple anywhere in the file, including a direction-delta
# dict's keys, not just an `at=`/coordinate constant. `Direction.delta`
# builds its own (dx, dy) internally (`traversal/direction.py`), so matching
# against it here never spells one out.
_DIRECTION_TO_FACING: dict[Direction, str] = {
    Direction.NORTH: "UP", Direction.SOUTH: "DOWN",
    Direction.EAST: "RIGHT", Direction.WEST: "LEFT",
}


def _direction_toward(dx: int, dy: int) -> str:
    direction = next((d for d in CARDINALS if d.delta == (dx, dy)), None)
    if direction is None:
        raise ValueError(f"ch05: ({dx}, {dy}) is not one of the four cardinal deltas")
    return _DIRECTION_TO_FACING[direction]


def _facing_toward(approach: tuple[int, int], target: tuple[int, int]) -> str:
    return _direction_toward(target[0] - approach[0], target[1] - approach[1])


def _walk_absorbing(emu: Emulator, beat: str, tx: int, ty: int, *,
                    absorb_wild: bool, absorb_trainer: bool,
                    max_absorbed: int = _MAX_ABSORBED_INTERRUPTIONS,
                    frame_budget: int = _WALK_ABSORBING_FRAME_BUDGET) -> None:
    """Walk to `(tx, ty)`, absorbing whichever kind(s) of incidental battle
    the caller declares. Byte-adapted from `ch04.py`'s own `_walk_absorbing`
    -- Passage Cave's `Cave` wild table (Tonemy/Barewl/Grozard/Dunsparce,
    densities 15/20) makes an unabsorbing walk between beats just as unsafe
    here as on Route 2."""
    from ..emulator import WalkInterrupted

    for _ in range(max_absorbed):
        try:
            emu.walk_to(tx, ty, frame_budget)
            return
        except WalkInterrupted as exc:
            if exc.battle:
                trainer = emu.is_trainer_battle()
            else:
                assertions.advance_to_battle(emu)
                if not in_battle(emu):
                    continue
                trainer = emu.is_trainer_battle()
            if trainer and not absorb_trainer:
                return
            if not trainer and not absorb_wild:
                return
            emu.resolve_interruption()
    shot = emu.screenshot(f"{beat}_ambush_cap")
    raise ScenarioError(
        f"{beat}: absorbed {max_absorbed} incidental battles walking toward "
        f"{(tx, ty)} without reaching it ({shot})")


def _press_a(emu: Emulator, beat: str, approach: tuple[int, int], facing: str) -> None:
    _walk_absorbing(emu, beat, *approach, absorb_wild=True, absorb_trainer=True)
    emu.face(facing)
    emu.interact()


def _trainer_defeat_flag(trainer_const: str) -> str:
    """The engine's own defeat flag for a native `trainerbattle_single`
    trainer -- see module docstring on why CH05's trainers use this and not
    an RPG-Maker self-switch."""
    return f"TRAINER_FLAGS_START + {trainer_const}"


def _trigger_trainer(emu: Emulator, beat: str, approach: tuple[int, int],
                     facing: str, trainer_const: str) -> None:
    """Byte-adapted from `ch04.py`'s `_trigger_trainer` -- bump first (the
    literal "Event Touch" reading), fall back to `interact()`, and assert
    WHICH trainer fought (never trust "a battle started" alone)."""
    _walk_absorbing(emu, beat, *approach, absorb_wild=True, absorb_trainer=False)
    emu.face(facing)
    assertions.try_step(emu, facing)
    if not emu.field_locked() and not in_battle(emu):
        try:
            emu.interact()
        except ScenarioError:
            pass
    assertions.advance_to_battle(emu)
    if not in_battle(emu):
        shot = emu.screenshot(f"{beat}_no_battle")
        raise ScenarioError(
            f"{beat}: neither a bump nor interact() at {approach} started a "
            f"battle ({shot})")
    if not emu.is_trainer_battle():
        shot = emu.screenshot(f"{beat}_wild_not_trainer")
        raise ScenarioError(
            f"{beat}: a battle started at {approach} but it isn't a trainer "
            f"battle ({shot})")
    expected = emu.resolve_constant(trainer_const)
    actual = emu.opponent_trainer_id()
    if actual != expected:
        shot = emu.screenshot(f"{beat}_wrong_trainer")
        raise ScenarioError(
            f"{beat}: a trainer battle started at {approach}, but against "
            f"trainer id {actual}, not {trainer_const} ({expected}) "
            f"({shot})")


def _battle_beat_body(emu: Emulator, beat: str, approach: tuple[int, int],
                      facing: str, trainer_const: str, defeat_flag: str) -> None:
    if emu.flag(defeat_flag):
        raise ScenarioError(
            f"{beat} precondition failed: {defeat_flag} already set before "
            f"the fight")
    _trigger_trainer(emu, beat, approach, facing, trainer_const)
    party = win_battle(emu)
    if not emu.flag(defeat_flag):
        shot = emu.screenshot(f"{beat}_not_defeated")
        raise ScenarioError(f"{beat}: {defeat_flag} not set after the win ({shot})")
    logger.info("%s: enemy party at battle start: %s", beat,
                [(m.species, m.level) for m in party])


def _retalk_beat_body(emu: Emulator, beat: str, approach: tuple[int, int],
                      facing: str, defeat_flag: str) -> None:
    if not emu.flag(defeat_flag):
        raise ScenarioError(
            f"{beat} precondition failed: {defeat_flag} not set -- the "
            f"battle beat must run first")
    _press_a(emu, beat, approach, facing)
    text = emu.current_field_message_text()
    if not text or not text.strip():
        shot = emu.screenshot(f"{beat}_empty_text")
        raise ScenarioError(
            f"{beat}: re-talk text is empty (see module docstring on why "
            f"this checks non-empty rather than a literal string) ({shot})")
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot(f"{beat}_stuck")
        raise ScenarioError(f"{beat}: re-talk did not close cleanly ({shot})")


def _item_grant_beat_body(emu: Emulator, beat: str, approach: tuple[int, int],
                          facing: str, item: str, ssa: str) -> None:
    if emu.flag(ssa):
        raise ScenarioError(
            f"{beat} precondition failed: {ssa} already set before the pickup")
    bag_before = emu.bag_item_quantity(item)
    _press_a(emu, beat, approach, facing)
    emu.advance_dialog()
    if not emu.flag(ssa):
        shot = emu.screenshot(f"{beat}_no_ssa")
        raise ScenarioError(f"{beat}: {ssa} not set after the pickup ({shot})")
    bag_after = emu.bag_item_quantity(item)
    if bag_after != bag_before + 1:
        shot = emu.screenshot(f"{beat}_bag_unchanged")
        raise ScenarioError(
            f"{beat}: {item} {bag_before}->{bag_after}, expected +1 ({shot})")


def _item_spent_beat_body(emu: Emulator, beat: str, approach: tuple[int, int],
                          facing: str, item: str, ssa: str) -> None:
    if not emu.flag(ssa):
        raise ScenarioError(
            f"{beat} precondition failed: {ssa} not set -- the grant beat "
            f"must run first")
    bag_before = emu.bag_item_quantity(item)
    _press_a(emu, beat, approach, facing)
    emu.advance_dialog()
    bag_after = emu.bag_item_quantity(item)
    if bag_after != bag_before:
        shot = emu.screenshot(f"{beat}_regranted")
        raise ScenarioError(
            f"{beat}: {item} {bag_before}->{bag_after} on a re-touch, "
            f"expected no change ({shot})")


# Direction lookup for a raw (dx, dy) displacement reuses `_direction_toward`
# (defined above) rather than a second literal dict.


# -- B1 -- cave entrance/exit warp round trip (map036/ev001/p0, plus CH04's
# own deferred nudge on map035/ev001/p1; see module docstring) ------------

_B1_ROUTE2_TRIGGER = warp_cell(ROUTE_2_CONST, to=MAP_1F)
_B1_ROUTE2_APPROACH = (_B1_ROUTE2_TRIGGER[0], _B1_ROUTE2_TRIGGER[1] + 1)
_B1_CAVE_TRIGGER = event_cell(MAP_1F, 1)
_B1_CAVE_ARRIVAL = arrival_cell(MAP_1F, from_map=ROUTE_2_CONST)
_B1_ROUTE2_ARRIVAL = arrival_cell(ROUTE_2_CONST, from_map=MAP_1F, event_id=1)


@ch05.beat("B1", "The Route 2 <-> Passage Cave 1F warp pair round-trips: "
                   "cross in, cross back out (exercising CH04's own "
                   "permanently-deferred once-per-visit nudge on the Route "
                   "2 side), then cross in again -- boundary convention: "
                   "CH05 owns this crossing (manifest map036/ev001/p0, "
                   "CH04 map035/ev001/p1)",
            map_constant=MAP_1F, at=_B1_CAVE_TRIGGER, group="B1",
            rows=("map036/ev001/p0",), archetype="warp")
def b1(emu: Emulator) -> None:
    # Forward: Route 2 -> Cave 1F (Map035's own entrance event, CH04-owned;
    # this crossing is exercised here under the boundary convention).
    assertions.cross_threshold(emu, "B1", _B1_ROUTE2_APPROACH, "UP", MAP_1F)
    assertions.assert_near(emu, "B1", _B1_CAVE_ARRIVAL)

    # Return: Cave 1F -> Route 2 (Map036's own exit event, this chapter's
    # manifest row).
    assertions.cross_threshold(emu, "B1", _B1_CAVE_ARRIVAL, "DOWN", ROUTE_2_CONST)
    assertions.assert_near(emu, "B1", _B1_ROUTE2_ARRIVAL)

    # CH04's own deferred nudge (map035/ev001/p1) fires here.
    emu.settle_field()
    if emu.field_locked():
        shot = emu.screenshot("b1_stuck_after_nudge")
        raise ScenarioError(
            f"B1: field still locked after the Route 2 arrival nudge "
            f"settled ({shot})")
    nudged = emu.player_pos()
    if nudged == _B1_ROUTE2_ARRIVAL:
        shot = emu.screenshot("b1_no_nudge")
        raise ScenarioError(
            f"B1: player still at the Route 2 arrival cell "
            f"{_B1_ROUTE2_ARRIVAL} after settling -- expected the nudge "
            f"move route to have displaced them ({shot})")
    dx = abs(nudged[0] - _B1_ROUTE2_ARRIVAL[0])
    dy = abs(nudged[1] - _B1_ROUTE2_ARRIVAL[1])
    if dx + dy != 1:
        shot = emu.screenshot("b1_wrong_nudge_distance")
        raise ScenarioError(
            f"B1: nudged to {nudged}, expected exactly one tile off "
            f"{_B1_ROUTE2_ARRIVAL} (Manhattan distance {dx + dy}) ({shot})")

    # Forward again: confirms the warp still fires after the nudge, ending
    # inside the cave for the rest of the chapter.
    ddx = _B1_ROUTE2_ARRIVAL[0] - nudged[0]
    ddy = _B1_ROUTE2_ARRIVAL[1] - nudged[1]
    step_dir = _direction_toward(ddx, ddy)
    assertions.try_step(emu, step_dir)
    assertions.wait_for_map(emu, "B1", MAP_1F)
    assertions.assert_near(emu, "B1", _B1_CAVE_ARRIVAL)


# -- B2 -- Escape Rope item ball (map036/ev003) ----------------------------

_B2_EVENT = 3
_B2_ITEM = "ITEM_ESCAPE_ROPE"
_B2_APPROACH = approach_to(MAP_1F, _B2_EVENT, prefer="east")
_B2_FACING = _facing_toward(_B2_APPROACH, event_cell(MAP_1F, _B2_EVENT))
_B2_SSA = assertions.flag_ssa(36, _B2_EVENT, "A")


@ch05.beat("B2", "The Escape Rope item ball grants one Escape Rope, once "
                   "(manifest map036/ev003/p0)",
            map_constant=MAP_1F, at=_B2_APPROACH, group="B2",
            rows=("map036/ev003/p0",), archetype="item_ball")
def b2(emu: Emulator) -> None:
    _item_grant_beat_body(emu, "B2", _B2_APPROACH, _B2_FACING, _B2_ITEM, _B2_SSA)


@ch05.beat("B2_spent", "Re-touching the spent Escape Rope ball grants "
                          "nothing a second time (manifest map036/ev003/p1)",
            map_constant=MAP_1F, at=_B2_APPROACH, group="B2",
            rows=("map036/ev003/p1",), archetype="item_ball")
def b2_spent(emu: Emulator) -> None:
    _item_spent_beat_body(emu, "B2_spent", _B2_APPROACH, _B2_FACING, _B2_ITEM, _B2_SSA)


# -- B3 -- Hiker Manny (map036/ev004) --------------------------------------

_B3_EVENT = 4
_B3_TRAINER = "TRAINER_MANNY_5"
_B3_DEFEAT_FLAG = _trainer_defeat_flag(_B3_TRAINER)
_B3_APPROACH = approach_to(MAP_1F, _B3_EVENT, prefer="east")
_B3_FACING = _facing_toward(_B3_APPROACH, event_cell(MAP_1F, _B3_EVENT))


@ch05.beat("B3", "Hiker Manny's trainer battle fires and is won; the "
                   "native defeat flag latches (manifest map036/ev004/p0)",
            map_constant=MAP_1F, at=_B3_APPROACH, group="B3",
            rows=("map036/ev004/p0",), archetype="trainer")
def b3(emu: Emulator) -> None:
    _battle_beat_body(emu, "B3", _B3_APPROACH, _B3_FACING, _B3_TRAINER, _B3_DEFEAT_FLAG)


@ch05.beat("B3_retalk0", "After B3, Manny's defeated re-talk page shows "
                            "(manifest map036/ev004/p1)",
            map_constant=MAP_1F, at=_B3_APPROACH, group="B3",
            rows=("map036/ev004/p1",), archetype="trainer")
def b3_retalk0(emu: Emulator) -> None:
    _retalk_beat_body(emu, "B3_retalk0", _B3_APPROACH, _B3_FACING, _B3_DEFEAT_FLAG)


# -- B5 -- Blackbelt Keichi (map036/ev006) ---------------------------------

_B5_EVENT = 6
_B5_TRAINER = "TRAINER_KEICHI_248"
_B5_DEFEAT_FLAG = _trainer_defeat_flag(_B5_TRAINER)
_B5_APPROACH = approach_to(MAP_1F, _B5_EVENT, prefer="east")
_B5_FACING = _facing_toward(_B5_APPROACH, event_cell(MAP_1F, _B5_EVENT))


@ch05.beat("B5", "Blackbelt Keichi's trainer battle fires and is won; the "
                   "native defeat flag latches (manifest map036/ev006/p0)",
            map_constant=MAP_1F, at=_B5_APPROACH, group="B5",
            rows=("map036/ev006/p0",), archetype="trainer")
def b5(emu: Emulator) -> None:
    _battle_beat_body(emu, "B5", _B5_APPROACH, _B5_FACING, _B5_TRAINER, _B5_DEFEAT_FLAG)


@ch05.beat("B5_retalk0", "After B5, Keichi's defeated re-talk page shows "
                            "(manifest map036/ev006/p1)",
            map_constant=MAP_1F, at=_B5_APPROACH, group="B5",
            rows=("map036/ev006/p1",), archetype="trainer")
def b5_retalk0(emu: Emulator) -> None:
    _retalk_beat_body(emu, "B5_retalk0", _B5_APPROACH, _B5_FACING, _B5_DEFEAT_FLAG)


# -- B4 -- Great Ball item ball (map036/ev005) -----------------------------
# Registered after B5, not before -- registration order is playthrough
# order, and the approved route (reference/routes/CH05.route.json) visits
# Keichi before the Great Ball even though the doc numbers them the other
# way; beat ids are labels, not ordering (ch04.py's own B4/B2/B3 note makes
# the same point).

_B4_EVENT = 5
_B4_ITEM = "ITEM_GREAT_BALL"
_B4_APPROACH = approach_to(MAP_1F, _B4_EVENT, prefer="west")
_B4_FACING = _facing_toward(_B4_APPROACH, event_cell(MAP_1F, _B4_EVENT))
_B4_SSA = assertions.flag_ssa(36, _B4_EVENT, "A")


@ch05.beat("B4", "The Great Ball item ball grants one Great Ball, once "
                   "(manifest map036/ev005/p0)",
            map_constant=MAP_1F, at=_B4_APPROACH, group="B4",
            rows=("map036/ev005/p0",), archetype="item_ball")
def b4(emu: Emulator) -> None:
    _item_grant_beat_body(emu, "B4", _B4_APPROACH, _B4_FACING, _B4_ITEM, _B4_SSA)


@ch05.beat("B4_spent", "Re-touching the spent Great Ball ball grants "
                          "nothing a second time (manifest map036/ev005/p1)",
            map_constant=MAP_1F, at=_B4_APPROACH, group="B4",
            rows=("map036/ev005/p1",), archetype="item_ball")
def b4_spent(emu: Emulator) -> None:
    _item_spent_beat_body(emu, "B4_spent", _B4_APPROACH, _B4_FACING, _B4_ITEM, _B4_SSA)


# -- B8 -- 1F <-> 2F warp round trip (map036/ev002, map037/ev001) ---------
# B8 crosses forward and back; the nudge on arrival back at 1F, and the
# final forward crossing that actually ends the chapter on 2F, are the
# sibling beat B8_nudge (module docstring: a Beat carries one archetype=,
# and B8's own rows are "warp").

_B8_FORWARD_EVENT = 2   # on MAP_1F
_B8_RETURN_EVENT = 1    # on MAP_2F
_B8_FORWARD_TRIGGER = event_cell(MAP_1F, _B8_FORWARD_EVENT)
_B8_FORWARD_APPROACH = (_B8_FORWARD_TRIGGER[0], _B8_FORWARD_TRIGGER[1] + 1)
_B8_FORWARD_ARRIVAL = arrival_cell(MAP_2F, from_map=MAP_1F, event_id=_B8_FORWARD_EVENT)
_B8_RETURN_ARRIVAL = arrival_cell(MAP_1F, from_map=MAP_2F, event_id=_B8_RETURN_EVENT)


@ch05.beat("B8", "The Passage Cave warp pair crosses forward (1F->2F) and "
                   "back (2F->1F) (manifest map036/ev002/p0, "
                   "map037/ev001/p0)",
            map_constant=MAP_1F, at=_B8_FORWARD_APPROACH, group="B8",
            rows=("map036/ev002/p0", "map037/ev001/p0"), archetype="warp")
def b8(emu: Emulator) -> None:
    assertions.cross_threshold(emu, "B8", _B8_FORWARD_APPROACH, "DOWN", MAP_2F)
    assertions.assert_near(emu, "B8", _B8_FORWARD_ARRIVAL)
    assertions.cross_threshold(emu, "B8", _B8_FORWARD_ARRIVAL, "DOWN", MAP_1F)
    assertions.assert_near(emu, "B8", _B8_RETURN_ARRIVAL)


@ch05.beat("B8_nudge", "Arriving back on 1F, the once-per-visit arrival "
                          "nudge autorun fires (manifest map036/ev002/p1); "
                          "stepping back onto the warp tile crosses forward "
                          "again, ending on 2F for the rest of the chapter",
            map_constant=MAP_1F, at=_B8_RETURN_ARRIVAL, group="B8",
            rows=("map036/ev002/p1",), archetype="arrival_nudge")
def b8_nudge(emu: Emulator) -> None:
    assertions.require_map(emu, "B8_nudge", MAP_1F)
    emu.settle_field()
    if emu.field_locked():
        shot = emu.screenshot("b8_nudge_stuck")
        raise ScenarioError(
            f"B8_nudge: field still locked after settling on arrival ({shot})")
    pos = emu.player_pos()
    if pos == _B8_RETURN_ARRIVAL:
        shot = emu.screenshot("b8_nudge_no_nudge")
        raise ScenarioError(
            f"B8_nudge: player still at arrival cell {_B8_RETURN_ARRIVAL} "
            f"after settling -- expected the nudge move route to have "
            f"displaced them ({shot})")
    dx = abs(pos[0] - _B8_RETURN_ARRIVAL[0])
    dy = abs(pos[1] - _B8_RETURN_ARRIVAL[1])
    if dx + dy != 1:
        shot = emu.screenshot("b8_nudge_wrong_distance")
        raise ScenarioError(
            f"B8_nudge: nudged to {pos}, expected exactly one tile off "
            f"{_B8_RETURN_ARRIVAL} (Manhattan distance {dx + dy}) ({shot})")
    ddx = _B8_FORWARD_TRIGGER[0] - pos[0]
    ddy = _B8_FORWARD_TRIGGER[1] - pos[1]
    step_dir = _direction_toward(ddx, ddy)
    assertions.try_step(emu, step_dir)
    assertions.wait_for_map(emu, "B8_nudge", MAP_2F)
    assertions.assert_near(emu, "B8_nudge", _B8_FORWARD_ARRIVAL)


# -- B9 -- Hiker Nunes (map037/ev004) --------------------------------------

_B9_EVENT = 4
_B9_TRAINER = "TRAINER_NUNES_128"
_B9_DEFEAT_FLAG = _trainer_defeat_flag(_B9_TRAINER)
_B9_APPROACH = approach_to(MAP_2F, _B9_EVENT, prefer="west")
_B9_FACING = _facing_toward(_B9_APPROACH, event_cell(MAP_2F, _B9_EVENT))


@ch05.beat("B9", "Hiker Nunes's trainer battle fires and is won; the "
                   "native defeat flag latches (manifest map037/ev004/p0)",
            map_constant=MAP_2F, at=_B9_APPROACH, group="B9",
            rows=("map037/ev004/p0",), archetype="trainer")
def b9(emu: Emulator) -> None:
    _battle_beat_body(emu, "B9", _B9_APPROACH, _B9_FACING, _B9_TRAINER, _B9_DEFEAT_FLAG)


@ch05.beat("B9_retalk0", "After B9, Nunes's defeated re-talk page shows "
                            "(manifest map037/ev004/p1)",
            map_constant=MAP_2F, at=_B9_APPROACH, group="B9",
            rows=("map037/ev004/p1",), archetype="trainer")
def b9_retalk0(emu: Emulator) -> None:
    _retalk_beat_body(emu, "B9_retalk0", _B9_APPROACH, _B9_FACING, _B9_DEFEAT_FLAG)


# -- B14 -- east sideways staircase (map037/terrain/stairs/20,9 + 20,10) ---
# No archetype: a staircase is not one of the four recognized RPG Maker
# archetypes, same as ch04.py's rockslide boulders.

_B14_APPROACH = raw_cell(
    19, 9, why=(
        "cells.py has no stair_approach resolver (only event_cell/"
        "approach_to/warp_cell/arrival_cell/entry_cell exist -- see cells.py "
        "module docstring). Value copied verbatim from "
        "reference/routes/CH05.locations.json's B14 stair_approach "
        "derivation: the west E/W neighbour of stair cell (20,9) that owns "
        "the stair_diagonal edge (routing.locations._stair_approach), "
        "itself built from traversal.graph.build_map_graph's real edges, "
        "not measured or guessed."))


@ch05.beat("B14", "The east sideways staircase is mandatory traversal: an "
                     "E/W press diagonally displaces the player across it "
                     "(manifest map037/terrain/stairs/20,9 and .../20,10)",
            map_constant=MAP_2F, at=_B14_APPROACH, group="B14",
            rows=("map037/terrain/stairs/20,9", "map037/terrain/stairs/20,10"))
def b14(emu: Emulator) -> None:
    _walk_absorbing(emu, "B14", *_B14_APPROACH, absorb_wild=True, absorb_trainer=True)
    emu.face("RIGHT")
    before = emu.player_pos()
    moved = assertions.try_step(emu, "RIGHT")
    if not moved:
        shot = emu.screenshot("b14_not_moving")
        raise ScenarioError(
            f"B14: stepping RIGHT from the west approach {_B14_APPROACH} "
            f"did not move the player across the staircase ({shot})")
    after = emu.player_pos()
    if after[0] <= before[0]:
        shot = emu.screenshot("b14_wrong_direction")
        raise ScenarioError(
            f"B14: staircase crossing did not move the player east "
            f"({before} -> {after}) ({shot})")
    assertions.require_map(emu, "B14", MAP_2F)


# -- B13 -- west sideways staircase (map037/terrain/stairs/11,9 + 11,10) ---

_B13_APPROACH = raw_cell(
    10, 9, why=(
        "cells.py has no stair_approach resolver -- same gap B14 cites "
        "above. Value copied verbatim from CH05.locations.json's B13 "
        "stair_approach derivation: the west E/W neighbour of stair cell "
        "(11,9) that owns the stair_diagonal edge."))


@ch05.beat("B13", "The west sideways staircase is mandatory traversal: an "
                     "E/W press diagonally displaces the player across it "
                     "(manifest map037/terrain/stairs/11,9 and .../11,10)",
            map_constant=MAP_2F, at=_B13_APPROACH, group="B13",
            rows=("map037/terrain/stairs/11,9", "map037/terrain/stairs/11,10"))
def b13(emu: Emulator) -> None:
    _walk_absorbing(emu, "B13", *_B13_APPROACH, absorb_wild=True, absorb_trainer=True)
    emu.face("RIGHT")
    before = emu.player_pos()
    moved = assertions.try_step(emu, "RIGHT")
    if not moved:
        shot = emu.screenshot("b13_not_moving")
        raise ScenarioError(
            f"B13: stepping RIGHT from the west approach {_B13_APPROACH} "
            f"did not move the player across the staircase ({shot})")
    after = emu.player_pos()
    if after[0] <= before[0]:
        shot = emu.screenshot("b13_wrong_direction")
        raise ScenarioError(
            f"B13: staircase crossing did not move the player east "
            f"({before} -> {after}) ({shot})")
    assertions.require_map(emu, "B13", MAP_2F)


# -- B10 -- the Revive NPC (map037/ev005) ----------------------------------
# No archetype: matches no recognized template (dispositions note: "Matches
# no archetype template, so B10_grant is hand-written").

_B10_EVENT = 5
_B10_ITEM = "ITEM_REVIVE"
_B10_APPROACH = approach_to(MAP_2F, _B10_EVENT, prefer="south")
_B10_FACING = _facing_toward(_B10_APPROACH, event_cell(MAP_2F, _B10_EVENT))
_B10_SSA = assertions.flag_ssa(37, _B10_EVENT, "A")


@ch05.beat("B10", "The NPC grants one Revive on talk, once (manifest "
                     "map037/ev005/p0)",
            map_constant=MAP_2F, at=_B10_APPROACH, group="B10",
            rows=("map037/ev005/p0",))
def b10(emu: Emulator) -> None:
    _item_grant_beat_body(emu, "B10", _B10_APPROACH, _B10_FACING, _B10_ITEM, _B10_SSA)


@ch05.beat("B10_retalk", "After B10, the NPC's post-gift re-talk page shows "
                            "(manifest map037/ev005/p1)",
            map_constant=MAP_2F, at=_B10_APPROACH, group="B10",
            rows=("map037/ev005/p1",))
def b10_retalk(emu: Emulator) -> None:
    if not emu.flag(_B10_SSA):
        raise ScenarioError(
            f"B10_retalk precondition failed: {_B10_SSA} not set -- B10 "
            f"must run first")
    _press_a(emu, "B10_retalk", _B10_APPROACH, _B10_FACING)
    text = emu.current_field_message_text()
    if not text or not text.strip():
        shot = emu.screenshot("b10_retalk_empty_text")
        raise ScenarioError(
            f"B10_retalk: re-talk text is empty ({shot})")
    emu.advance_dialog()
    if emu.field_locked():
        shot = emu.screenshot("b10_retalk_stuck")
        raise ScenarioError(f"B10_retalk: re-talk did not close cleanly ({shot})")


# -- B11 -- CH05|CH06 boundary (map037/ev002) ------------------------------

_B11_BOUNDARY = event_cell(MAP_2F, 2)


@ch05.beat("B11", "The player reaches the CH05|CH06 boundary at Map037 "
                     "event 2 (16,5); Map040 is not in SLICE_MAP_IDS, so no "
                     "warp compiles here and the tile is walkable and inert "
                     "-- CH05's contract is to deliver the player to the "
                     "edge, not cross it (boundary convention; manifest "
                     "map037/ev002/p0)",
            map_constant=MAP_2F, at=_B11_BOUNDARY, group="B11",
            rows=("map037/ev002/p0",), archetype="warp")
def b11(emu: Emulator) -> None:
    _walk_absorbing(emu, "B11", *_B11_BOUNDARY, absorb_wild=True, absorb_trainer=True)
    if emu.player_pos() != _B11_BOUNDARY:
        shot = emu.screenshot("b11_wrong_pos")
        raise ScenarioError(
            f"B11: expected to stand at the boundary tile {_B11_BOUNDARY}, "
            f"got {emu.player_pos()} ({shot})")
    assertions.require_map(emu, "B11", MAP_2F)
    if emu.field_locked():
        shot = emu.screenshot("b11_unexpected_lock")
        raise ScenarioError(
            f"B11: field locked after reaching the boundary tile -- Map040 "
            f"is unstaged, so nothing should have fired here ({shot})")


# -- symbol lint surface ------------------------------------------------------
MAP_CONSTANTS: tuple[str, ...] = (ROUTE_2_CONST, MAP_1F, MAP_2F)

FLAG_CONSTANTS: tuple[str, ...] = (_B2_SSA, _B4_SSA, _B10_SSA)

ITEM_CONSTANTS: tuple[str, ...] = (_B2_ITEM, _B4_ITEM, _B10_ITEM)

TRAINER_CONSTANTS: tuple[str, ...] = (_B3_TRAINER, _B5_TRAINER, _B9_TRAINER)

ALL_CONSTANTS: tuple[str, ...] = (
    MAP_CONSTANTS + FLAG_CONSTANTS + ITEM_CONSTANTS + TRAINER_CONSTANTS
)

CHAPTER = ch05.build()
