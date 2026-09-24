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
from rpg2gba.beat_gen.plan import Blocker, Elsewhere, Refusal, Selection
from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.story_state.model import RowVerdict

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
    owned: list[ManifestRow] = []
    refusals: list[Refusal] = []
    elsewhere: list[Elsewhere] = []

    for row in rows:
        floor = floors.get(row.row_id)
        if floor is None:
            raise ValueError(f"{row.row_id}: no floor (upstream bug)")

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
            # Rule 5: later / unreachable -> elsewhere.
            if verdict.status == "later":
                elsewhere.append(Elsewhere(row.row_id, "later", verdict.owner))
                continue
            if verdict.status == "unreachable":
                elsewhere.append(Elsewhere(row.row_id, "unreachable", None))
                continue

        # Rule 6: requires a capability and isn't the obstacle itself.
        if row.requires and not _is_obstacle_row(floor):
            elsewhere.append(Elsewhere(row.row_id, "blocked", None, row.requires))
            continue

        # Rule 7: floor refused.
        if floor.refusals:
            reason = floor.refusals[0].reason
            refusals.append(Refusal(row.row_id, blocker_for(reason), reason,
                                     floor.refusals[0].detail))
            continue

        # Rule 8: owned.
        owned.append(row)

    return Selection(owned=tuple(owned), refusals=tuple(refusals),
                      elsewhere=tuple(elsewhere))
