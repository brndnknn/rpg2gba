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

**The four archetype templates
(`playtest.archetypes.{item_ball,trainer,warp,arrival_nudge}`) are now used
directly, for seven of the eleven groups below.** They previously could not
be called at all: neither exposed `group=`, and none named its primary beat
the bare id (`"B2"`) a disposition names (see git history at `aa2dcb0f` for
the fix). That gap is closed, so `B2`/`B4` call `item_ball_beats`, `B3`/`B5`/
`B9` call `trainer_beats`, and `B1`/`B8` call `warp_beat` (`B8` also calls
`arrival_nudge_beat`). `B10`/`B13`/`B14` stay hand-written -- no archetype
matches them, same as before. `B11` **also stays hand-written, by deliberate
build-agent deviation from the assigned mapping** -- see its own section
below for why calling `warp_beat` there would be actively wrong, not just
differently-shaped.

**`warp_beat` now has a `round_trip=True` mode** (added after this module's
first conversion pass, per the operator's decision that the idiom belongs
in the template, not hand-written back into a chapter): it crosses the
warp, asserts arrival, crosses back through the DERIVED reciprocal warp,
asserts arrival back at the origin, then crosses forward once more --
`playtest.archetypes.warp`'s own module docstring has the full contract,
including why the return leg's press direction (`return_direction=`) is a
required, explicit parameter alongside `round_trip=True`, not something
derivable from the graph. `B1`/`B8` below now pass `round_trip=True`,
restoring the "cross in, cross back, cross in again" convention the
hand-authored module this one replaces used for both
(`CH05.dispositions.json`, 2026-09-04) -- see each group's own section for
exactly what's covered now versus what the very first conversion pass
dropped.

**Trainers are native, not self-switch-gated.** Per `CH05_TODO.md` step 1,
`TRAINER_MANNY_5` / `TRAINER_KEICHI_248` / `TRAINER_NUNES_128` are staged
into `SLICE_TRAINER_BATTLES` as ordinary `trainerbattle_single` instances --
unlike CH04's Larrie (a phone-rematch idiom needing an RPG-Maker self-switch
flag), their defeat state is the engine's own `TRAINER_FLAGS_START + <id>`
bit, set inside the battle before any script runs, so it can be read the
instant `win_battle` returns (no post-battle-script settle needed, unlike
CH04's Larrie). `trainer_beats` takes this as a plain `defeat_flag=` string,
computed the same way (`_trainer_defeat_flag`) it always was here -- the
manifest cannot derive which mechanism (native flag vs. self-switch) the
transpiler picked for a given instance, so this remains author-supplied.

**Trigger dispatch is a hedge, not a confirmed fact.** The manifest
describes these three trainers as event-sight (`pbNoticePlayer`), which
CH04's own module docstring found ambiguous for its own roster (some
compiled trigger=2 "Event Touch", but the *engine's* compiled dispatch
mechanism for a solid NPC was unconfirmed at authoring time). `trainer_beats`
now owns this resolution (`_start_trigger`, generalized from CH04's own
`_trigger_trainer`): try the stated trigger, retry with `interact()` if
nothing fired, and only fail if neither produces a trainer battle against
the RIGHT trainer id. `trigger="event_touch"` is passed for all three of
this chapter's trainers, cross-checked against `classify_manifest`'s own
derivation for each event at import time -- a mismatch is a loud
`ValueError`, not a silently-accepted claim. Untested against a real ROM at
authoring time -- flagged, not guessed away.

**Re-talk beats use the STATIC approach cell, not a measured live position.**
CH04 found that an event-touch trainer's battle walks it toward the player
and the compiled engine keeps the moved position afterward
(`TryOverrideTemplateCoordsForObjectEvent`), so its own re-talk beats read a
measured `local_id`/live position instead of trusting the template cell.
No such measurement exists yet for Manny/Keichi/Nunes (this is the first
build; nothing has boot-walked). `trainer_beats` is called below with no
`local_id=`, so its re-talk beats fall back to the STATIC approach cell --
the same real risk the hand-written module accepted (the trainer may have
moved and the re-talk beat cannot reach it), deliberately kept per the task
brief's "prefer a weaker but correct assertion" over inventing an unverified
`local_id`. If the boot walk finds this wrong, the fix is passing a measured
`local_id=` to `trainer_beats`, not a new mechanism.

**Re-talk/gift text: the template checks MORE than the hand-written beats
did, in the common case.** Unlike this module's own `B10_retalk` (still
hand-written, still a bare non-empty check per the standing
`feedback-avoid-uranium-spoilers` rule -- this file never quotes Uranium
dialogue), `trainer_beats`' re-talk beats call
`playtest.text_source.expected_text` and assert the REAL line
(`emu.assert_text_contains`, with `{PLAYER}` split around the control code)
when that lookup succeeds -- no dialogue is embedded in this source file,
only fetched at run time. It degrades to the same non-empty check this
module always used, with a loud warning log, only when
`expected_text` cannot translate that page's control codes. Net effect for
`B3`/`B5`/`B9`'s re-talk beats: coverage went UP, not down.

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

**B1 -- round trip, one row claimed.** The manifest row this chapter owns
for B1 is `map036/ev001/p0`, the CAVE's own exit event (cave -> Route 2);
the entrance crossing (Route 2 -> cave) is `map035/ev001/p0`, owned by
CH04's manifest, not this one. `warp_beat(round_trip=True,
return_direction="UP")` now crosses cave -> Route 2 (claims
`map036/ev001/p0`), crosses back Route 2 -> cave via the DERIVED reciprocal
(`cells.warp_cell(ROUTE_2_CONST, to=MAP_1F)`, CH04's own entrance warp,
exercised but not claimed -- same boundary convention as before: the
arriving chapter tests a crossing the outgoing chapter's manifest can't),
then crosses cave -> Route 2 once more, ending the beat back on
`MAP_ROUTE_02`. **Still short of the pre-conversion hand-written beat in
one respect:** that module's return leg additionally exercised CH04's own
permanently-deferred arrival-nudge autorun on the Route 2 side
(`map035/ev001/p1`) and asserted its specific one-tile displacement before
crossing back in; `round_trip=True` asserts map+position on each leg but has
no nudge-specific step (nudges are `arrival_nudge_beat`'s own archetype, a
different template, and `map035/ev001/p1` is CH04's row, not claimable
here). **B1 ends this beat on `MAP_ROUTE_02`, not inside the cave** -- an
artifact of the manifest's own row orientation (this chapter's claimable
crossing is cave-to-Route-2, so that is `round_trip`'s declared "forward"
and its own destination), unchanged from this template's pre-round-trip
one-way behavior and not newly introduced here; flagged, not resolved, same
as the next paragraph's own continuity note.

**B8 -- one stop, three beats; the forward call now round-trips.** The warp
pair (`map036/ev002/p0` forward, `map037/ev001/p0` return) and the nudge
that fires on the return leg (`map036/ev002/p1`) are three `ArchetypeMatch`
rows on two different maps; `warp_beat`/`find_match` key a claim to one
exact `(map_id, event_id)` pair, so covering both warp rows still takes two
calls -- `find_match` cannot merge a `map036` row and a `map037` row into
one claim, and `round_trip=True` does not change that (task brief's "the
pair collapses back to one call" option: not available without changing
`find_match`'s matching key, which this task does not own).
`warp_beat(beat_name="B8", round_trip=True, return_direction="DOWN")` now
does the FULL forward/back/forward-again cycle on the forward leg alone --
crosses 1F->2F (claims `map036/ev002/p0`), crosses back 2F->1F via the
DERIVED reciprocal (physically the same warp `B8_return` also tests, just
not claimed here), then crosses 1F->2F once more, ending back on 2F.
`warp_beat(beat_name="B8_return", group="B8")` runs next, UNCHANGED
(`round_trip` still `False` there) -- it still exists solely to claim
`map037/ev001/p0` via its own `find_match` call, and it still performs one
real 2F->1F crossing to do so, which leaves the group's own final position
back on 1F. **Why `B8_return` was not also made `round_trip=True`:** its
own declared "forward" is fixed by the manifest to 2F->1F (the row's own
map/event), so round-tripping IT always ends on 1F too (a round trip's net
effect is always two arrivals at the call's own declared destination and
one at the origin) -- no ordering or choice of which single call gets
`round_trip=True` avoids the group ending on 1F once `B8_return` runs last,
since `B8_return` must physically run after `B8` (the only entry to 2F).
This is the SAME map the group already ended on before this change (this
is not a new regression); the possible mismatch against `B9`'s own declared
`MAP_PASSAGE_CAVE_2F` entry is a pre-existing, unresolved question (like
B1's own continuity note above), not exercised by any of this task's
verification commands, flagged for the real ROM boot walk. **Restored
versus the pre-conversion module:** the full three-crossing round trip on
the forward warp (this was entirely absent before this change); the
reciprocal warp is now physically exercised twice (once inside `B8`'s
round trip, once by `B8_return`'s own claim) rather than once.

**B11 -- deliberately NOT converted; still hand-written.** The assigned
mapping for this rewrite calls for `warp_beat` here, but `map037/ev002/p0`
does not compile to a working warp at all: Map040 (Nowtoch) is not in
`SLICE_MAP_IDS`, so `metadata_wiring.classify_event` skipped it and emitted
no `warp_event`
(`CH05.dispositions.json`'s own note on this row). `warp_beat`'s body calls
`assertions.cross_threshold` then `assertions.wait_for_map(..., dest_map)`,
which polls until the map changes -- against a destination that was never
staged, that call cannot succeed; it would hang out to its frame budget and
fail loud on every run, not just report a weaker assertion. The
dispositions file already documents this row as "the one warp row in the
chapter that cannot use the round-trip idiom" for the same reason. This is
a build-agent judgment call made without being asked: B11 keeps its
hand-written body (reach the boundary tile, assert position and an
un-locked field, assert nothing crossed), and the mismatch between the
assigned mapping and what actually compiles here is flagged for the lead
rather than silently worked around.

**A genuine cross-chapter continuity risk, noted and not resolved here.**
`playtest.runner._check_beat_continuity` compares each beat's declared
`at=` against wherever the PREVIOUS beat (including inherited predecessor
beats) actually left the player, checked strictly, at run time. CH04's own
last own-beat (`B15`, the wild-grass encounter) leaves the player somewhere
in the grass south of the rockslide, not at B1's declared entry
(`event_cell(MAP_PASSAGE_CAVE_1F, 1)`, deep inside the cave) -- the two
cannot literally agree, and B1's body (round trip or not) starts from its
own declared `at=`, deep in the cave; it never walks the player across the
CH04-handoff gap itself, round-tripping or no. `round_trip=True` does now
put B1's body back onto `MAP_ROUTE_02` mid-beat (its own "cross back" leg),
but only after starting from inside the cave -- it does not, and cannot,
retroactively bridge the entry mismatch above. Whether the runner tolerates
this (or whether CH04 already has the same latent gap for its own first
beat after CH03) is a `playtest.runner`/harness question, out of this
file's scope and not exercised by any of this task's own verification
commands (`routing plan --dry-run`, `chapter_manifest check`, `pytest`,
`ruff`) -- flagged for whoever runs Step 7's real ROM build.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...traversal.direction import CARDINALS, Direction
from .. import assertions
from ..archetypes.arrival_nudge import arrival_nudge_beat
from ..archetypes.item_ball import item_ball_beats
from ..archetypes.trainer import trainer_beats
from ..archetypes.warp import warp_beat
from ..battle import in_battle
from ..cells import approach_to, entry_cell, event_cell, raw_cell
from ..chapter import BeatLocation, ChapterBuilder
from ..errors import ScenarioError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from ..emulator import Emulator


_CHAPTER_ID = "CH05"

MAP_1F = "MAP_PASSAGE_CAVE_1F"
MAP_2F = "MAP_PASSAGE_CAVE_2F"
ROUTE_2_CONST = "MAP_ROUTE_02"  # CH04's own map constant; see module docstring's B1

# CH05 begins on ROUTE 2, not in the cave. CH04 hands the player over at the
# route's own cave entrance (observed entry (19,49), map 35), and B1's first
# move is a walk across Route 2 to the cave mouth.
#
# This has to be declared rather than inferred, because the solver's fallback
# reads the entry off `own_beats[0].locations[0]` -- the same field it uses as
# that group's INTERACTION cell, the point later segments are costed from.
# B1 acts on, and ends on, the cave's exit warp; it only STARTS on Route 2.
# Overloading the one field to mean both was measured at 141 -> 258 tiles with
# the cave reordered into a backtracking sweep, because every segment after B1
# was then costed from Route 2. See `Chapter.route_entry`.
#
# It is where CH04 HANDS OVER, not where CH05 crosses. Declaring the crossing
# cell instead still left the approach walk outside the plan -- the run starts
# at (19,49) and walks north to the cave mouth, and a plan whose entry is the
# warp tile does not contain that walk. B1 then left the approved route onto
# Map035 EV012's trigger tile (Timothy, event touch) with nothing planning
# around it.
#
# Derived, not a literal (D1): `entry_cell` reads the one verified table of
# (chapter, map) start cells, where CH05/map035 is registered from the
# emulator-observed position the step-7 runs recorded.
_ROUTE_ENTRY = entry_cell(_CHAPTER_ID, ROUTE_2_CONST)

ch05 = ChapterBuilder("CH05", doc="reference/chapters/05-passage-cave.md",
                        predecessor="CH04",
                        route_entry=BeatLocation(
                            ROUTE_2_CONST, *_ROUTE_ENTRY,
                            label="CH05 entry (CH04 hands over on Route 2)"))

# -- shared helpers, adapted from ch04.py (chapter-local by design, per
# assertions.py's own docstring on what deliberately does not get promoted --
# a wild-encounter-aware absorbing walk is Route/Cave specific tuning, not a
# corpus-wide primitive) -- still needed by B10/B11/B13/B14, the four groups
# with no matching archetype template. -------------------------------------

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
    an RPG-Maker self-switch. Fed to `trainer_beats(defeat_flag=...)` below."""
    return f"TRAINER_FLAGS_START + {trainer_const}"


def _item_grant_beat_body(emu: Emulator, beat: str, approach: tuple[int, int],
                          facing: str, item: str, ssa: str) -> None:
    """Still used by B10 -- the Revive NPC matches no archetype template
    (`pbReceiveItem`, not `pbItemBall`), so it stays hand-written."""
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


# -- B1 -- cave entry/exit warp, Cave 1F <-> Route 2 (map036/ev001) --------
# See module docstring: the hand-written round trip this replaces is not
# reproducible through `warp_beat`, which crosses one direction per call.
#
# `start_side="dest"` because the player is NOT in the cave when this beat
# begins. CH05's only claimable row here is `map036/ev001/p0` -- the CAVE's
# exit warp -- so the template's origin is the cave, but CH04 hands the
# player over on Route 02 (observed entry (19,49), map 35). Authored
# origin-first, the beat walked the cave's warp coordinates ON ROUTE 02 for
# all 17 tiles of its path and asserted an arrival that never happened
# (step-7 run 4, 2026-09-06). Mirrored, it runs Route 2 -> cave -> Route 2
# -> cave: it starts where the player is, proves the warp both ways, and
# ends inside the cave where B2 needs them.
warp_beat(
    ch05,
    chapter_id=_CHAPTER_ID,
    map_constant=MAP_1F,
    map_id=36,
    event_id=1,
    dest_map_constant=ROUTE_2_CONST,
    mechanism="threshold",
    direction="DOWN",
    beat_name="B1",
    round_trip=True,
    return_direction="UP",
    start_side="dest",
)


# -- B2 -- Escape Rope item ball (map036/ev003) ----------------------------

_B2_ITEM = "ITEM_ESCAPE_ROPE"

item_ball_beats(
    ch05,
    chapter_id=_CHAPTER_ID,
    map_constant=MAP_1F,
    map_id=36,
    event_id=3,
    item=_B2_ITEM,
    beat_prefix="B2",
    negative_beat=True,
    approach_prefer="east",
)


# -- B3 -- Hiker Manny (map036/ev004) --------------------------------------

_B3_TRAINER = "TRAINER_MANNY_5"

trainer_beats(
    ch05,
    chapter_id=_CHAPTER_ID,
    map_constant=MAP_1F,
    map_id=36,
    event_id=4,
    trainer_const=_B3_TRAINER,
    defeat_flag=_trainer_defeat_flag(_B3_TRAINER),
    beat_prefix="B3",
    trigger="event_touch",
    phone=False,
    double=False,
    retalk_pages=1,
    rider=False,
    approach_prefer="east",
)


# -- B5 -- Blackbelt Keichi (map036/ev006) ---------------------------------

_B5_TRAINER = "TRAINER_KEICHI_248"

trainer_beats(
    ch05,
    chapter_id=_CHAPTER_ID,
    map_constant=MAP_1F,
    map_id=36,
    event_id=6,
    trainer_const=_B5_TRAINER,
    defeat_flag=_trainer_defeat_flag(_B5_TRAINER),
    beat_prefix="B5",
    trigger="event_touch",
    phone=False,
    double=False,
    retalk_pages=1,
    rider=False,
    approach_prefer="east",
)


# -- B4 -- Great Ball item ball (map036/ev005) -----------------------------
# Registered after B5, not before -- registration order is playthrough
# order, and the approved route (reference/routes/CH05.route.json) visits
# Keichi before the Great Ball even though the doc numbers them the other
# way; beat ids are labels, not ordering (ch04.py's own B4/B2/B3 note makes
# the same point).

_B4_ITEM = "ITEM_GREAT_BALL"

item_ball_beats(
    ch05,
    chapter_id=_CHAPTER_ID,
    map_constant=MAP_1F,
    map_id=36,
    event_id=5,
    item=_B4_ITEM,
    beat_prefix="B4",
    negative_beat=True,
    approach_prefer="west",
)


# -- B8 -- 1F <-> 2F warp pair plus the return-side nudge (map036/ev002,
# map037/ev001) -- one stop, three beats; see module docstring for why this
# is short of the old round trip and why it takes three template calls
# instead of the "one warp beat" a single crossing would need. -------------

warp_beat(
    ch05,
    chapter_id=_CHAPTER_ID,
    map_constant=MAP_1F,
    map_id=36,
    event_id=2,
    dest_map_constant=MAP_2F,
    mechanism="threshold",
    direction="DOWN",
    beat_name="B8",
    round_trip=True,
    return_direction="DOWN",
)

warp_beat(
    ch05,
    chapter_id=_CHAPTER_ID,
    map_constant=MAP_2F,
    map_id=37,
    event_id=1,
    dest_map_constant=MAP_1F,
    mechanism="threshold",
    direction="DOWN",
    beat_name="B8_return",
    group="B8",
)

arrival_nudge_beat(
    ch05,
    chapter_id=_CHAPTER_ID,
    map_constant=MAP_1F,
    map_id=36,
    event_id=2,
    from_map_constant=MAP_2F,
    from_event_id=1,
    beat_name="B8_nudge",
    group="B8",
)


# -- B9 -- Hiker Nunes (map037/ev004) --------------------------------------

_B9_TRAINER = "TRAINER_NUNES_128"

trainer_beats(
    ch05,
    chapter_id=_CHAPTER_ID,
    map_constant=MAP_2F,
    map_id=37,
    event_id=4,
    trainer_const=_B9_TRAINER,
    defeat_flag=_trainer_defeat_flag(_B9_TRAINER),
    beat_prefix="B9",
    trigger="event_touch",
    phone=False,
    double=False,
    retalk_pages=1,
    rider=False,
    approach_prefer="west",
)


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
# Deliberately NOT converted to warp_beat -- see module docstring's own B11
# section for why: Map040 is not in SLICE_MAP_IDS, so no warp actually
# compiles here, and warp_beat's body would wait forever for a map change
# that cannot happen.

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

FLAG_CONSTANTS: tuple[str, ...] = (_B10_SSA,)

ITEM_CONSTANTS: tuple[str, ...] = (_B2_ITEM, _B4_ITEM, _B10_ITEM)

TRAINER_CONSTANTS: tuple[str, ...] = (_B3_TRAINER, _B5_TRAINER, _B9_TRAINER)

ALL_CONSTANTS: tuple[str, ...] = (
    MAP_CONSTANTS + FLAG_CONSTANTS + ITEM_CONSTANTS + TRAINER_CONSTANTS
)

CHAPTER = ch05.build()
