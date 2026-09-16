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

**The oracle is the source, not a literal.** Expected text comes from
`text_source.expected_text`, which reads the decoded RMXP page and applies
the same charmap canonicalization the staging path does. A beat that
hardcoded its dialogue would pass against a converter that dropped the
text entirely and re-added it wrong -- PLAYTEST_AUTHORING_IMPROVEMENT.md's
proxy-oracle complaint, which is exactly what §15.8's #43(b) ruling pushed
these ~100 rows back into the residue to avoid.

This is emphatically not a beat generator (see the package docstring): one
call per NPC, in a chapter file that stays a linear, hand-controlled,
approvable document.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import assertions
from ..cells import approach_to, event_cell
from ..errors import ScenarioError
from ..text_source import page_messages
from . import facing_toward, find_match

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
    the self-switch reveals, and is read only for the `toggling` variant.

    `approach_prefer` is passed through to `cells.approach_to` for the
    handful of NPCs reachable from more than one side; `approach_to` fails
    loud naming every candidate when it is needed and omitted.
    """
    match = find_match(
        chapter_id, map_id, event_id, "flavour_npc",
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

    # Read the source's lines at REGISTRATION time, not inside the beat: a
    # missing page or an empty message list is an authoring error that should
    # surface when the chapter module imports, not 40 minutes into a ROM run.
    messages = page_messages(map_id, event_id, page_idx)
    if not messages:
        raise ValueError(
            f"flavour_npc_beat: {map_constant} event {event_id} page "
            f"{page_idx} (row {row_id}) has no messages in source -- a "
            "flavour NPC with nothing to say is not this archetype; check "
            "the page index"
        )
    expected_lines = tuple(message.text for message in messages)

    @builder.beat(
        beat_name,
        description or (
            f"The {derived} flavour NPC at {map_constant} event {event_id} "
            f"says its line (manifest {row_id})"
        ),
        map_constant=map_constant, at=approach,
        group=resolved_group, archetype="flavour_npc", rows=(row_id,),
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
        else:
            emu.assert_text_contains(expected_lines[0])
        emu.advance_dialog()

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
    toggled_text = toggled[0].text

    @builder.beat(
        f"{beat_name}_again",
        f"Re-talking the toggled flavour NPC at {map_constant} event "
        f"{event_id} says its second line instead (manifest {row_id})",
        map_constant=map_constant, at=approach,
        group=resolved_group, archetype="flavour_npc", rows=(),
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
        emu.assert_text_contains(toggled_text)
        emu.advance_dialog()

    del talk_again


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
