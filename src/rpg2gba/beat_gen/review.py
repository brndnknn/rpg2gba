"""Stage 8: `ChapterPlan` -> `output/beats/CHnn.review.md` (C6 Task 8; R7, C2).

The review doc is part of the §9 per-chapter boot gate (C6 plan C2): the
operator reads and approves it before the generated module replaces a hand
module. It is the ONLY human-visible record of the solver's picks, so it
must show every pick, every refusal and every order-dependent write.

STATUS: stub (`assignments/C6/08_review.md`).
"""
from __future__ import annotations

from collections.abc import Callable

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import ChapterPlan

FloorLookup = Callable[[str], RowFloor]


def render_review(plan: ChapterPlan, *, floor_lookup: FloorLookup) -> str:
    """The review document as markdown, ending in exactly one newline.
    Deterministic: same plan and floors -> same bytes."""
    raise NotImplementedError
