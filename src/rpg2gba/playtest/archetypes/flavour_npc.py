"""The `flavour_npc` archetype beat template -- T2, the corpus's largest
*talk* population (REDERIVATION_PLAN.md §13.3: ~915 pages across 112+ maps).

Fingerprint (`chapter_manifest.archetypes._match_flavour_npc`): an
action-triggered page you press A on, which says something and changes
nothing you could observe later. Three variants, and the template asserts
a different thing for each:

- `plain` -- talk once, get the source's text.
- `toggling` -- a self-switch flips, so the SECOND talk is a different
  page. The beat asserts both halves and the flag between them, because a
  toggling NPC that never toggles reads identically to a plain one if you
  only talk once.
- `randomized` -- `random()` picks a line. The set of possible lines is
  known from source; which one shows is not. The beat asserts the shown
  text is *one of* them, never a particular one.

**The oracle is the generic beat floor (REDERIVATION_PLAN.md §16.3 C4/C5),
not a literal.** Expected text comes from the row's `beat_floor` -- the same
source-derived vocabulary every archetype template declares against -- so a
beat that hardcoded its dialogue would pass against a converter that dropped
the text entirely and re-added it wrong. `declare_assertions` (package
`__init__.py`) is what turns "the body checks this" into a declared claim
the checker's ⊇-floor rule can verify, and this module is careful to declare
only what its body actually checks (C5 shape (c), "honest declarations").

**Branch arms are left to C6.** A talk's floor is sometimes only on its
page's TRUNK (plain single-message NPCs, and the two textbook toggling
instances this module's own tests pin: `map031/ev048` and `map073/ev005` in
CH03, whose p0/p1 write their self-switch and speak their line at the page
level, no branch children at all) and sometimes the real text/self-switch
work happens inside `111`-branch arm rows the page's trunk only guards
(`map064/ev001`, `map065/ev001`/`ev002` in CH01: trunk floor is
`trigger`/`completes`/`visual` only, and each variant's two lines live on
`p0/b0`/`p0/b1`). Which arm a given walk hits there depends on runtime
self-switch/story state this template does not trace (C5 shape (f) allows
leaving them for the generic template; §16.3 R11 "don't guess" backs
leaving them alone over a wrong claim). This module never adds an arm row
to `rows=`; it is listed here, once, rather than re-derived per instance.

This is emphatically not a beat generator (see the package docstring): one
call per NPC, in a chapter file that stays a linear, hand-controlled,
approvable document.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...beat_floor.assertion import FloorAssertion, RowFloor
from ...beat_floor.lookup import floor_for_row as _default_floor_for_row
from ...chapter_manifest.schema import page_row_id
from .. import assertions
from ..cells import approach_to, event_cell
from ..errors import ScenarioError
from ..text_source import page_messages
from . import FloorLookup, declare_assertions, facing_toward, find_match, load_chapter_rows

if TYPE_CHECKING:  # runtime import is lazy so this module works without bindings
    from ...chapter_manifest.schema import ManifestRow
    from ..chapter import ChapterBuilder
    from ..emulator import Emulator

logger = logging.getLogger(__name__)

_VARIANTS = ("plain", "toggling", "randomized")


def flavour_npc_beat(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    map_constant: str,
    map_id: int,
    event_id: int,
    beat_name: str,
    variant: str | None = None,
    page_idx: int = 0,
    toggled_page_idx: int = 1,
    self_switch_letter: str = "A",
    description: str | None = None,
    approach_prefer: str | None = None,
    group: str | None = None,
    manifest_rows: "tuple[ManifestRow, ...] | None" = None,
    manifest_dir=None,
    manifest_chapter_id: str | None = None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register one `flavour_npc` instance.

    `variant=`, if given, is checked against the variant the manifest
    independently derives and raises at registration time on disagreement
    -- the package's manifest-driven-validation discipline. Omit it to
    take the manifest's word; pass it when you want the chapter file to
    state the claim out loud, which is worth doing for `toggling`, whose
    second beat only exists because of it.

    `page_idx` is which page of the event carries the dialogue this beat
    asserts (0 for almost every instance). `toggled_page_idx` is the page
    the self-switch reveals, and is read only for the `toggling` variant --
    when that page exists as its own manifest row (`page_row_id`), the
    `_again` beat claims it and declares its floor; when it does not (the
    row the pipeline generated refuses, or the manifest has no such page),
    the `_again` beat claims no row, same as before this refactor.

    `self_switch_letter` is used only to compute the toggled page's flag
    name as a PRECONDITION check on the `_again` beat when the primary
    row's own floor carries no `self_switch_write` assertion to derive the
    letter from (e.g. the write lives on a branch arm this template does
    not claim -- see the module docstring). When the primary row's floor
    does carry a trunk-level `self_switch_write`, its own `letter`/`value`
    params are used instead, and the first beat additionally OBSERVES the
    flag after talking (not just leaving it as the second beat's
    precondition) -- REDERIVATION_PLAN.md §16.3 C5's declared-assertions
    rule again: a beat that never reads the flag it writes cannot honestly
    declare `self_switch_write`.

    `approach_prefer` is passed through to `cells.approach_to` for the
    handful of NPCs reachable from more than one side; `approach_to` fails
    loud naming every candidate when it is needed and omitted.

    `floor_lookup=`, defaulting to `beat_floor.lookup.floor_for_row`, lets
    a caller (chiefly tests) supply an in-memory floor instead of reading
    `output/uranium-build/`; passed straight through to `declare_assertions`.
    """
    # `row_id=` disambiguates events where MORE THAN ONE page independently
    # qualifies as a flavour_npc instance (e.g. a page-condition-gated
    # second page that is its own, unrelated dialogue -- `find_match`'s own
    # docstring: flavour_npc is page-level, same as warp/arrival_nudge,
    # which already need this). Without it, `page_idx` alone can't tell
    # `find_match` which of the several matches this call means.
    match = find_match(
        chapter_id, map_id, event_id, "flavour_npc",
        row_id=page_row_id(map_id, event_id, page_idx),
        rows=manifest_rows, manifest_dir=manifest_dir,
        manifest_chapter_id=manifest_chapter_id,
    )
    row_id = next(iter(match.roles))
    derived = str(match.params["variant"])

    if variant is not None:
        if variant not in _VARIANTS:
            raise ValueError(
                f"flavour_npc_beat: {map_constant} event {event_id}: unknown "
                f"variant {variant!r} -- one of {list(_VARIANTS)}"
            )
        if variant != derived:
            raise ValueError(
                f"flavour_npc_beat: {map_constant} event {event_id}: stated "
                f"variant={variant!r} disagrees with the manifest, which "
                f"derives {derived!r} from row {row_id} -- the manifest is "
                "the source of truth; drop the argument or fix the claim"
            )

    resolved_group = group if group is not None else beat_name
    approach = approach_to(map_constant, event_id, prefer=approach_prefer)
    facing = facing_toward(
        approach, event_cell(map_constant, event_id), caller="flavour_npc_beat")

    resolved_floor_lookup: FloorLookup = (
        floor_lookup if floor_lookup is not None else _default_floor_for_row)
    floor0: RowFloor = resolved_floor_lookup(row_id)

    manifest_chapter = manifest_chapter_id if manifest_chapter_id is not None else chapter_id
    chapter_rows = manifest_rows if manifest_rows is not None else load_chapter_rows(
        manifest_chapter, manifest_dir=manifest_dir)
    arm_row_ids = tuple(sorted(
        r.row_id for r in chapter_rows if r.parent_row_id == row_id))

    # -- text: prefer the row's own trunk floor; it is what the checker's
    # ⊇-floor rule compares against, so basing the runtime check on
    # anything else risks the two silently drifting apart (task item 2).
    floor_text_assertions = () if floor0.refused else tuple(sorted(
        (a for a in floor0.assertions if a.kind == "text"),
        key=lambda a: a.param("index")))
    floor_lines = tuple(a.param("text") for a in floor_text_assertions)

    # Read the source's lines at REGISTRATION time, not inside the beat: a
    # missing page or an empty message list is an authoring error that should
    # surface when the chapter module imports, not 40 minutes into a ROM run.
    #
    # `randomized`'s candidates and the fallback (no trunk-level floor text
    # -- the row is refused, or its text lives on branch arms this template
    # does not claim, see module docstring) both still need a source-derived
    # oracle; `page_messages` is that oracle -- unlike `floor_lines`, it is
    # not declared as a beat assertion, so there is no drift risk to avoid
    # by preferring it over the floor in those two cases.
    source_messages = page_messages(map_id, event_id, page_idx)
    if not source_messages:
        raise ValueError(
            f"flavour_npc_beat: {map_constant} event {event_id} page "
            f"{page_idx} (row {row_id}) has no messages in source -- a "
            "flavour NPC with nothing to say is not this archetype; check "
            "the page index"
        )
    fallback_lines = tuple(message.text for message in source_messages)

    if derived == "randomized":
        # Candidates come from the branch arms' own floors when the row has
        # them (the real shape for every randomized instance found in
        # CH01/CH03: a trunk `var_write` picking an index, then one text arm
        # per candidate) -- same discipline as `floor_lines` above, source
        # of truth is `beat_floor`, not a second interpretation of the
        # page's raw command list. Falls back to `page_messages` only if no
        # arm yields any text (defensive; not hit by the current corpus).
        candidate_texts: list[str] = []
        for arm_id in arm_row_ids:
            try:
                arm_floor = resolved_floor_lookup(arm_id)
            except KeyError:
                continue
            if arm_floor.refused:
                continue
            candidate_texts.extend(
                a.param("text") for a in arm_floor.assertions if a.kind == "text")
        if not candidate_texts:
            candidate_texts = list(fallback_lines)
        expected_lines: tuple[str, ...] = tuple(candidate_texts)
    elif floor_lines:
        expected_lines = floor_lines
    else:
        logger.info(
            "%s: row %s has no trunk-level 'text' floor assertion (refused "
            "or on an unclaimed branch arm) -- falling back to the raw "
            "source's first message box, undeclared", beat_name, row_id)
        expected_lines = (fallback_lines[0],)

    # -- self-switch (toggling only): derive letter/expected-value from the
    # row's own floor when it has a trunk-level self_switch_write (the two
    # textbook CH03 instances), so the write this beat OBSERVES is the same
    # one declared. Falls back to the explicit `self_switch_letter=` (as a
    # precondition only, no post-talk observation) when the floor doesn't
    # carry it -- the arm-nested CH01 instances.
    ssa0: str | None = None
    expected_ssa0_value: bool | None = None
    if derived == "toggling" and floor_text_assertions:  # trunk-level floor present
        ss0 = next(
            (a for a in floor0.assertions if a.kind == "self_switch_write"), None)
        if ss0 is not None:
            ssa0 = assertions.flag_ssa(map_id, event_id, str(ss0.param("letter")))
            expected_ssa0_value = bool(ss0.param("value"))

    executed_kinds = {"trigger", "completes", "visual", "audio"}
    if expected_lines and derived != "randomized" and floor_lines:
        executed_kinds.add("text")
    if ssa0 is not None:
        executed_kinds.add("self_switch_write")

    declared = declare_assertions(
        (row_id,), executed_kinds=frozenset(executed_kinds), template="flavour_npc",
        floor_lookup=resolved_floor_lookup,
    )

    @builder.beat(
        beat_name,
        description or (
            f"The {derived} flavour NPC at {map_constant} event {event_id} "
            f"says its line (manifest {row_id})"
        ),
        map_constant=map_constant, at=approach,
        group=resolved_group, archetype="flavour_npc", rows=(row_id,),
        assertions=declared,
    )
    def talk(emu: Emulator) -> None:
        assertions.require_map(emu, beat_name, map_constant)
        emu.walk_to(*approach)
        emu.face(facing)
        if not emu.interact(require_script=True):
            shot = emu.screenshot(f"{beat_name}_no_script")
            raise ScenarioError(
                f"{beat_name}: pressing A at {approach} facing {facing} "
                f"started no script -- {row_id} is an action-triggered page "
                f"with text, so it must speak ({shot})"
            )
        if derived == "randomized":
            # Which line is genuinely unknown; asserting a particular one
            # would fail one run in N for a correct conversion.
            _assert_one_of(emu, beat_name, expected_lines, row_id)
            emu.advance_dialog()
        else:
            _walk_text_boxes(emu, beat_name, row_id, expected_lines)

        if ssa0 is not None:
            actual = emu.flag(ssa0)
            if actual != expected_ssa0_value:
                shot = emu.screenshot(f"{beat_name}_self_switch")
                raise ScenarioError(
                    f"{beat_name}: after talking, {ssa0} reads {actual!r}, "
                    f"expected {expected_ssa0_value!r} -- {row_id}'s source "
                    "self-switch write did not fire as declared "
                    f"({shot})"
                )

    del talk

    if derived != "toggling":
        return

    # The toggling half. Without it the beat proves only that the NPC has a
    # first thing to say -- the self-switch write, which is the ONLY thing
    # distinguishing this variant, would go entirely unobserved.
    ssa = assertions.flag_ssa(map_id, event_id, self_switch_letter)
    toggled = page_messages(map_id, event_id, toggled_page_idx)
    if not toggled:
        raise ValueError(
            f"flavour_npc_beat: {map_constant} event {event_id} is the "
            f"toggling variant (row {row_id}) but page {toggled_page_idx} "
            "has no messages in source -- pass toggled_page_idx= if the "
            "second page is elsewhere"
        )
    toggled_fallback = tuple(message.text for message in toggled)

    # The toggled page's own row, when the manifest has one (task item 3):
    # claim it and declare its floor the same way the primary row is
    # declared, instead of the old `rows=()`.
    toggled_row_id = page_row_id(map_id, event_id, toggled_page_idx)
    toggled_floor: RowFloor | None
    try:
        toggled_floor = resolved_floor_lookup(toggled_row_id)
    except KeyError:
        toggled_floor = None

    toggled_floor_text = () if toggled_floor is None or toggled_floor.refused else tuple(
        sorted(
            (a for a in toggled_floor.assertions if a.kind == "text"),
            key=lambda a: a.param("index")))
    toggled_expected_lines = (
        tuple(a.param("text") for a in toggled_floor_text)
        if toggled_floor_text else toggled_fallback)

    toggled_ssa: str | None = None
    toggled_expected_value: bool | None = None
    if toggled_floor_text:
        ss1 = next(
            (a for a in toggled_floor.assertions if a.kind == "self_switch_write"),
            None) if toggled_floor is not None else None
        if ss1 is not None:
            toggled_ssa = assertions.flag_ssa(map_id, event_id, str(ss1.param("letter")))
            toggled_expected_value = bool(ss1.param("value"))

    again_rows: tuple[str, ...] = ()
    again_executed_kinds = {"trigger", "completes", "visual", "audio"}
    again_declared: frozenset[FloorAssertion] = frozenset()
    if toggled_floor is not None and not toggled_floor.refused:
        again_rows = (toggled_row_id,)
        if toggled_floor_text:
            again_executed_kinds.add("text")
        if toggled_ssa is not None:
            again_executed_kinds.add("self_switch_write")
        again_declared = declare_assertions(
            again_rows, executed_kinds=frozenset(again_executed_kinds),
            template="flavour_npc", floor_lookup=resolved_floor_lookup,
        )

    @builder.beat(
        f"{beat_name}_again",
        f"Re-talking the toggled flavour NPC at {map_constant} event "
        f"{event_id} says its second line instead (manifest {row_id})",
        map_constant=map_constant, at=approach,
        group=resolved_group, archetype="flavour_npc", rows=again_rows,
        assertions=again_declared,
    )
    def talk_again(emu: Emulator) -> None:
        if not emu.flag(ssa):
            raise ScenarioError(
                f"{beat_name}_again precondition failed: {ssa} is not set "
                f"-- {beat_name} must run first, and its A press is what "
                "flips the self-switch"
            )
        emu.walk_to(*approach)
        emu.face(facing)
        if not emu.interact(require_script=True):
            shot = emu.screenshot(f"{beat_name}_again_no_script")
            raise ScenarioError(
                f"{beat_name}_again: the toggled page started no script "
                f"({shot})"
            )
        _walk_text_boxes(emu, f"{beat_name}_again", toggled_row_id, toggled_expected_lines)

        if toggled_ssa is not None:
            actual = emu.flag(toggled_ssa)
            if actual != toggled_expected_value:
                shot = emu.screenshot(f"{beat_name}_again_self_switch")
                raise ScenarioError(
                    f"{beat_name}_again: after talking, {toggled_ssa} reads "
                    f"{actual!r}, expected {toggled_expected_value!r} -- "
                    f"{toggled_row_id}'s source self-switch write did not "
                    f"fire as declared ({shot})"
                )

    del talk_again


def _walk_text_boxes(
    emu: Emulator, beat_name: str, row_id: str, expected_texts: tuple[str, ...],
) -> None:
    """Check EVERY message box in `expected_texts`, in order, then mash
    through to the end of the script.

    A page's dialogue can be more than one `msgbox` in source order (the
    floor's `text` assertions each carry their own `index`) -- ordinary
    pokeemerald text-box advance (A or B, `Emulator.advance_dialog`'s own
    docstring) is what moves from one box to the next, so this drives that
    same primitive one box at a time instead of mashing straight through,
    which would only ever observe the LAST box.
    """
    for i, expected in enumerate(expected_texts):
        if i > 0:
            emu.clear_field_message()
            emu.tap("A")
        text = emu.wait_for_field_message()
        if text is None or expected not in text:
            shot = emu.screenshot(f"{beat_name}_text_box_{i}")
            raise ScenarioError(
                f"{beat_name}: message box {i} of {row_id} expected to "
                f"contain {expected!r}, got {text!r} ({shot})"
            )
    emu.advance_dialog()


def _assert_one_of(
    emu: Emulator, beat: str, candidates: tuple[str, ...], row_id: str,
) -> None:
    """The shown message must be one of `candidates`.

    `assert_text_contains` is per-string, so this drives it manually to
    keep one failure message that lists every line the NPC could have said
    -- a `random()` beat failing with only the last candidate printed is
    the failure-message complaint PLAYTEST_AUTHORING_IMPROVEMENT.md makes,
    reproduced.
    """
    for candidate in candidates:
        try:
            emu.assert_text_contains(candidate)
            return
        except ScenarioError:
            continue
    actual = emu.wait_for_field_message()
    shot = emu.screenshot(f"{beat}_no_candidate")
    raise ScenarioError(
        f"{beat}: {row_id} is the randomized variant; the shown text "
        f"{actual!r} matches none of its {len(candidates)} source lines "
        f"{list(candidates)} ({shot})"
    )
