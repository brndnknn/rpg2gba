"""Stage 1: which manifest rows does this chapter walk? (C6 Task 1)

Every manifest row lands in exactly one bucket of a `Selection`: owned
(the generator will produce a beat for it), refused (listed with a named
blocker, R7), or elsewhere (the story model puts it in another chapter or
none, R8).

STATUS: stub (`assignments/C6/01_select.md`).
"""
from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import Blocker, Elsewhere, Refusal, Selection
from rpg2gba.chapter_manifest.schema import ManifestRow, parse_row_id
from rpg2gba.story_state.model import RowVerdict
from rpg2gba.tileset_converter.metadata_wiring import blank_touch_drop
from rpg2gba.tileset_converter.stairs import stair_event_ids

# reason id -> Blocker. Test-pinned (10 reasons; `01_select.md`/research §1d)
# plus the row-kind-level "no story verdict" reason select.py itself mints.
# Deliberately NOT pre-populated with the other 15 reasons that exist in code
# but have never been seen in CH01-CH05 (research doc §1c/"Decisions left to
# you"): classifying an unseen reason is a call for a person, not a guess, so
# an unknown reason raises instead of silently picking a blocker (§4.5).
_BLOCKER_BY_REASON: dict[str, Blocker] = {
    "text_unnormalizable": "#109",
    "unknown_script_head": "C8",
    "non_literal_args": "C8",
    "unparsed_state_write": "C8",
    "unmodelled_outcome": "story-state",
    "unmodelled_predicate": "story-state",
    "unclassified_condition": "story-state",
    "story_state_refusal": "story-state",
    "stair_no_qualifying_page": "floor",
    "obstacle_missing_cell": "floor",
    # C8 stage 4 put the real interpreter behind story-state extraction, so
    # these replaced the `unparsed_state_write` catch-all above. Every one
    # below was MEASURED across CH01-CH05 on 2026-09-23 -- the file's rule
    # against pre-populating unseen reasons still holds, so the rest of the
    # interpreter's codes (`ruby_unknown_call`, `search_cap`, ...) are
    # deliberately absent and will still raise for a person to classify.
    "ruby_unknown_attribute": "C8",
    "computed_row_self_reference": "C8",
    # Not C8's to fix: the interpreter resolved these rows fine, the STATE
    # MODEL cannot hold the answer. `party_model` is the blocker C8's shape
    # ruling (b) named and deferred to "the first chapter that needs those
    # rows green"; `search_nonscalar_value` is a variable holding a string
    # (a species name), which `state.Assign.values` (bool|int) cannot carry.
    "party_model": "story-state",
    "search_nonscalar_value": "story-state",
    # Pre-existing extraction codes, measured in CH02-CH05 the same day (the
    # CH01-only fixture above never reached them).
    "nonconstant_variable_write": "story-state",
    "unhandled_condition_type": "story-state",
    # C8 stage 7 task 1 (2026-09-24), replacing jvGiveReward's old
    # `non_literal_args`. `one_of_n_grant`: exactly one PROFREWARDS rung pays
    # out, and the floor (a conjunction) has no disjunctive kind to say so --
    # a floor-vocabulary gap. `bag_capacity_unmodelled`: `if jvGiveReward`
    # tests pbReceiveItem's bag-space success, state the model does not hold.
    # Measured: CH01 7 / 4, every other chapter 0.
    "one_of_n_grant": "floor",
    "bag_capacity_unmodelled": "story-state",
    # C8 stage 5 (2026-09-24): whole-statement script parsing. Measured
    # CH01-CH05: `conditional_script_effect` 3 (map050/ev019 b1's postfix
    # pbAddPokemon grants), `unmodelled_attribute_write` 1.
    "conditional_script_effect": "floor",
    "unmodelled_attribute_write": "C8",
}

# Row kinds that stand for themselves rather than an RMXP event page/branch:
# the story model never produces verdicts for these (research §3), so rule 2
# does not apply to them.
_ROW_LEVEL_KINDS = frozenset({"seam", "terrain"})


def blocker_for(reason: str) -> Blocker:
    """The named upstream blocker for one refusal reason id.

    `reason` is either a floor refusal's `reason` (`FloorRefusal.reason`)
    or the head of a story-state refusal string (`RowVerdict.refusals[i]`
    is `"<head>"` or `"<head>:<detail>"`; pass the head). Raises
    `ValueError` naming the reason if it isn't in the table -- a new reason
    must be classified by a person, not defaulted (§4.5)."""
    try:
        return _BLOCKER_BY_REASON[reason]
    except KeyError:
        raise ValueError(f"unclassified refusal reason {reason!r}; add it to "
                          f"_BLOCKER_BY_REASON") from None


def _is_obstacle_row(floor: RowFloor) -> bool:
    """Is this row's floor the obstacle itself, rather than merely reachable
    only past one? The only source of truth (C7 Task 3): a `blocked_obstacle`
    assertion on its own floor."""
    return any(a.kind == "blocked_obstacle" for a in floor.assertions)


def _held_obstacle(row: ManifestRow, floor: RowFloor,
                   held_obstacles: Collection[tuple[int, int]]) -> bool:
    """The row is an obstacle (`_is_obstacle_row`) the walk can clear itself:
    its (map, event) is in `held_obstacles` (capability held, and no other
    event clears it -- `beat_gen.__main__._smashable_by_walk`)."""
    return (_is_obstacle_row(floor) and row.event_id is not None
            and (row.map_id, row.event_id) in held_obstacles)


def empty_events(map_id: int, map_json: Mapping) -> set[tuple[int, int]]:
    """The (map, event) pairs on one decoded map whose EVERY page is empty
    (only the terminating code 0). Such an event can show nothing on the
    ROM whatever the story state -- no page it could switch to does
    anything -- so its rows are `empty_page`, not walked (2026-09-29
    operator ruling, ROM run 26: the lab's invisible machine-side cells).
    An empty page that SUPERSEDES a non-empty one is not in here: its beat
    proves the earlier scene doesn't replay (hand CH03's N3)."""
    out: set[tuple[int, int]] = set()
    for event in map_json.get("events") or []:
        if not event:
            continue
        pages = event.get("pages") or []
        if pages and all(all(c.get("code") == 0 for c in p.get("list") or [])
                         for p in pages):
            out.add((map_id, event["id"]))
    return out


def dropped_events(map_id: int, map_json: Mapping) -> dict[tuple[int, int], str]:
    """(map, event) -> detail for every event on one decoded map that the
    converter drops as `blank_trigger1` (`metadata_wiring.blank_touch_drop`,
    the converter's own test). The ROM never carries them, so their rows
    are `converter_dropped`. The detail quotes the boot page's script so
    the review doc says what was dropped: the Surf work re-checks the
    vehicle-cancel ones against the engine's native dismount
    (PROJECT_TODO.md #119, 2026-09-30 operator ruling)."""
    out: dict[tuple[int, int], str] = {}
    # Stair cells drop earlier (`DROP_STAIR`) and are terrain rows, not this.
    stairs = stair_event_ids(dict(map_json))
    for event in map_json.get("events") or []:
        if not event or event["id"] in stairs or not blank_touch_drop(event):
            continue
        scripts = [
            p for page in event.get("pages") or [] for c in page.get("list") or []
            if c.get("code") in (111, 355, 655)
            for p in (c.get("parameters") or [])[-1:] if isinstance(p, str)
        ]
        out[(map_id, event["id"])] = (
            "converter drops it (blank_trigger1: blank graphic, player touch, no "
            "transfer)" + (f"; script: {' / '.join(scripts)}" if scripts else ""))
    return out


def select_rows(
    rows: Sequence[ManifestRow],
    verdicts: Mapping[str, RowVerdict],
    floors: Mapping[str, RowFloor],
    *,
    stripped: Mapping[tuple[int, int], str | None] | None = None,
    empty: Collection[tuple[int, int]] = frozenset(),
    dropped: Mapping[tuple[int, int], str] | None = None,
    held: Collection[str] = frozenset(),
    held_obstacles: Collection[tuple[int, int]] = frozenset(),
    foreign_cleared: Collection[tuple[int, int]] = frozenset(),
) -> Selection:
    """Sort every manifest row into owned / refused / elsewhere.

    `held` names the field capabilities the walk holds (CH08 §9): a row
    behind an obstacle whose every required capability is held is not
    `blocked` (Rule 6) -- it is walked once its obstacle's smash beat
    clears the way. `held_obstacles` are the (map, event) obstacles the walk
    clears itself; one an earlier chapter owns (as a negative beat) is
    claimed here instead of `later` (Rule 5). `foreign_cleared` obstacles are
    cleared by some other event, so their own rows keep Rule 6 even when the
    capability is held.

    `rows` in manifest order; `verdicts` and `floors` keyed by row id.
    Raises `ValueError` if a row has no floor at all (every manifest row
    has one by construction, C4/C5, so a missing floor is a bug upstream,
    not a refusal). See the task file for the full rule table.

    `stripped` is `strip_list.json`'s `map_events` ((map, event) ->
    expect_name, `orchestrator.load_map_event_strips`): those events never
    reach the ROM, so their rows are `stripped`, ahead of every other rule
    (2026-09-27: CH01 generated a beat for each of Moki Town's eleven
    no-port `Luz` lamps, and the ROM run found nothing to talk to).

    `empty` is `empty_events` over the chapter's maps: those events' rows
    are `empty_page`, right after the strip rule.

    `dropped` is `dropped_events` over the chapter's maps: those events'
    rows are `converter_dropped`, after the empty rule."""
    owned: list[ManifestRow] = []
    refusals: list[Refusal] = []
    elsewhere: list[Elsewhere] = []

    for row in rows:
        floor = floors.get(row.row_id)
        if floor is None:
            raise ValueError(f"{row.row_id}: no floor (upstream bug)")

        # Rule 1: the event is strip-listed.
        if stripped and row.event_id is not None and (row.map_id, row.event_id) in stripped:
            name = stripped[(row.map_id, row.event_id)]
            elsewhere.append(Elsewhere(
                row.row_id, "stripped",
                detail=f"strip_list.json map_events ({name or 'unnamed'})"))
            continue

        # Rule 1b: every page of the event is empty.
        if row.event_id is not None and (row.map_id, row.event_id) in empty:
            elsewhere.append(Elsewhere(
                row.row_id, "empty_page",
                detail="every page of the event is empty; nothing to check on the ROM"))
            continue

        # Rule 1c: the converter drops the event, so the ROM never carries it.
        if dropped and row.event_id is not None and (row.map_id, row.event_id) in dropped:
            elsewhere.append(Elsewhere(
                row.row_id, "converter_dropped",
                detail=dropped[(row.map_id, row.event_id)]))
            continue

        verdict = verdicts.get(row.row_id)

        # Rule 2: page/branch rows need a story verdict; seam/terrain don't.
        if verdict is None and row.kind not in _ROW_LEVEL_KINDS:
            refusals.append(Refusal(row.row_id, "story-state", "no_story_verdict",
                                     "no story-state verdict for this row"))
            continue

        if verdict is not None:
            # Rule 3: story status refused.
            if verdict.status == "refused":
                head, _, _ = verdict.refusals[0].partition(":")
                refusals.append(Refusal(row.row_id, blocker_for(head), head,
                                         verdict.refusals[0]))
                continue
            # Rule 4: story status undetermined.
            if verdict.status == "undetermined":
                refusals.append(Refusal(row.row_id, "story-state", "undetermined",
                                         "story model could not determine this row"))
                continue
            # Rule 5: later / unreachable -> elsewhere. Except (CH08 §9) an
            # obstacle whose capability the walk now holds: an earlier chapter
            # only proved it BLOCKED; clearing it is this chapter's beat.
            if verdict.status == "later" and _held_obstacle(row, floor, held_obstacles):
                pass
            elif verdict.status == "later":
                elsewhere.append(Elsewhere(row.row_id, "later", verdict.owner))
                continue
            if verdict.status == "unreachable":
                elsewhere.append(Elsewhere(row.row_id, "unreachable", None))
                continue

        # Rule 6: requires a capability and isn't the obstacle itself.
        held_here = set(row.requires) <= set(held) and (
            row.event_id is None or (row.map_id, row.event_id) not in foreign_cleared)
        if row.requires and not _is_obstacle_row(floor) and not held_here:
            elsewhere.append(Elsewhere(row.row_id, "blocked", None, row.requires))
            continue

        # Rule 7: floor refused.
        if floor.refusals:
            reason = floor.refusals[0].reason
            refusals.append(Refusal(row.row_id, blocker_for(reason), reason,
                                     floor.refusals[0].detail))
            continue

        # Rule 7b: an arm of a page whose floor is refused inherits the refusal.
        # The arm's floor repeats the page's `trigger`, which no arms-only beat
        # can prove, and the arm runs only inside the page's one firing
        # (2026-10-15, CH08: Map050 EV027 p0's dex-count text, #144).
        if row.kind == "branch":
            owner = parse_row_id(row.row_id).owning_page_row_id
            owner_floor = floors.get(owner) if owner is not None else None
            if owner_floor is not None and owner_floor.refusals:
                reason = owner_floor.refusals[0].reason
                refusals.append(Refusal(row.row_id, blocker_for(reason), reason,
                                         owner_floor.refusals[0].detail))
                continue

        # Rule 8: owned.
        owned.append(row)

    return Selection(owned=tuple(owned), refusals=tuple(refusals),
                      elsewhere=tuple(elsewhere))
