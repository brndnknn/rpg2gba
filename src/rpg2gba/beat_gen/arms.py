"""Mutually exclusive branch arms (REDERIVATION_PLAN.md §16.3 ruling 19).

One walk through a page takes one arm of each branch point, so a beat that
claims two exclusive arms declares assertions it can't all execute. This
stage runs between selection and grouping and decides, per arm, whether the
walk takes it, by what selects the arm:

- **blocked arms** (`blocked_arms`): the story model marks the arm
  `harness:` (a setup no walk makes, e.g. a full bag), `fork:` (a loss that
  whites out) or `capability:`. The walk takes its sibling; the arm and
  everything nested in it go to `elsewhere` as `unselected_arm`.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping

from rpg2gba.beat_gen.plan import Elsewhere, Selection
from rpg2gba.story_state.model import RowVerdict

_BLOCKING = ("harness", "fork", "capability")


def blocked_arms(
    selection: Selection, verdicts: Mapping[str, RowVerdict], fork_owned: Collection[str],
) -> Selection:
    """Move every owned branch arm whose story verdict carries a blocking
    `harness:`/`fork:`/`capability:` blocker to `elsewhere`. `fork_owned`
    rows (a white-out fork's landing pages) are left alone: they get their
    own beat (`beat_gen/whiteout.py`)."""
    owned = []
    moved = []
    for row in selection.owned:
        verdict = verdicts.get(row.row_id)
        blockers = [] if verdict is None else [
            b for b in verdict.blockers if b.split(":", 1)[0] in _BLOCKING]
        if row.kind == "branch" and blockers and row.row_id not in fork_owned:
            moved.append(Elsewhere(
                row.row_id, "unselected_arm",
                detail=f"blocked by {blockers[0]}; the walk takes the sibling arm (ruling 19)"))
        else:
            owned.append(row)
    return Selection(owned=tuple(owned), refusals=selection.refusals,
                     elsewhere=selection.elsewhere + tuple(moved))
