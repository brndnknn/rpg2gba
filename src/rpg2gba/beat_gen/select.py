"""Stage 1: which manifest rows does this chapter walk? (C6 Task 1)

Every manifest row lands in exactly one bucket of a `Selection`: owned
(the generator will produce a beat for it), refused (listed with a named
blocker, R7), or elsewhere (the story model puts it in another chapter or
none, R8).

STATUS: stub (`assignments/C6/01_select.md`).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import Blocker, Selection
from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.story_state.model import RowVerdict


def blocker_for(reason: str) -> Blocker:
    """The named upstream blocker for one refusal reason id.

    `reason` is either a floor refusal's `reason` (`FloorRefusal.reason`)
    or the head of a story-state refusal string (`RowVerdict.refusals[i]`
    is `"<head>"` or `"<head>:<detail>"`; pass the head). Raises
    `ValueError` naming the reason if it isn't in the table -- a new reason
    must be classified by a person, not defaulted (§4.5)."""
    raise NotImplementedError


def select_rows(
    rows: Sequence[ManifestRow],
    verdicts: Mapping[str, RowVerdict],
    floors: Mapping[str, RowFloor],
) -> Selection:
    """Sort every manifest row into owned / refused / elsewhere.

    `rows` in manifest order; `verdicts` and `floors` keyed by row id.
    Raises `ValueError` if a row has no floor at all (every manifest row
    has one by construction, C4/C5, so a missing floor is a bug upstream,
    not a refusal). See the task file for the full rule table."""
    raise NotImplementedError
