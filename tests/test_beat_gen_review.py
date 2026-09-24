"""Tests for `rpg2gba.beat_gen.review` (C6 Task 8).

These pin the doc's STRUCTURE and required CONTENT (section order, every
beat/refusal/pick/order-dependent write shown), not its exact bytes -- the
layout inside a section is yours.

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 8.
"""
from __future__ import annotations

import dataclasses

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor, make_params
from rpg2gba.beat_gen import review
from rpg2gba.beat_gen.plan import ChapterPlan, Elsewhere, PlannedBeat, Refusal, make_kwargs
from rpg2gba.story_state.model import OrderDependentKey

SECTIONS = ["## Summary", "## Order", "## Assertions", "## Refusals", "## Elsewhere",
            "## Order-dependent writes"]

LAB = "map049/ev001/p2"
AUNT = "map050/ev001/p1"


def _a(row: str, kind: str, i: int, **params) -> FloorAssertion:
    return FloorAssertion(row_id=row, kind=kind, list_index=i, code=None if i < 0 else 121,
                          params=make_params(**params))


FLOORS = {
    LAB: RowFloor(LAB, "action", frozenset({
        _a(LAB, "trigger", -1, trigger="action"), _a(LAB, "completes", -1),
        _a(LAB, "switch_write", 3, switch_id=104, value=False)}), ()),
    AUNT: RowFloor(AUNT, "action", frozenset({
        _a(AUNT, "trigger", -1, trigger="action"), _a(AUNT, "completes", -1),
        _a(AUNT, "switch_write", 7, switch_id=104, value=True),
        _a(AUNT, "var_write", 8, var_id=7, op="=", value=1)}), ()),
}

BEATS = (
    PlannedBeat(name="m050e001p1", template="generic", map_id=50, rows=(AUNT,),
                group="m050e001p1", kwargs=make_kwargs(approach_prefer="west")),
    PlannedBeat(name="m049e001p2", template="generic", map_id=49, rows=(LAB,),
                group="m049e001p2"),
)
PLAN = ChapterPlan(
    chapter_id="CH01", predecessor=None, beats=BEATS,
    refusals=(Refusal("map032/ev020/p0", "#109", "text_unnormalizable", "saw a straight quote"),
              Refusal("map050/ev019/p0", "C8", "unparsed_state_write", "tally in var 151")),
    elsewhere=(Elsewhere("map032/ev014/p1", "blocked", None, ("rock_smash",)),
               Elsewhere("map048/ev013/p0", "unreachable")),
    order_dependent=(OrderDependentKey(key="switch:104", writers=(LAB, AUNT),
                                       values=(False, True)),),
)


def _doc(plan: ChapterPlan = PLAN) -> str:
    return review.render_review(plan, floor_lookup=FLOORS.__getitem__)


def _section(doc: str, header: str) -> str:
    start = doc.index(header)
    later = [doc.index(h) for h in SECTIONS if h in doc and doc.index(h) > start]
    return doc[start:min(later) if later else len(doc)]


def test_title_and_sections_in_order():
    doc = _doc()
    assert doc.splitlines()[0].startswith("# CH01")
    positions = [doc.index(h) for h in SECTIONS]
    assert positions == sorted(positions)


def test_ends_with_one_newline_and_is_deterministic():
    doc = _doc()
    assert doc.endswith("\n") and not doc.endswith("\n\n")
    assert doc == _doc()


def test_order_lists_every_beat_in_plan_order_with_its_pick():
    order = _section(_doc(), "## Order")
    assert order.index("m050e001p1") < order.index("m049e001p2")
    line = next(ln for ln in order.splitlines() if "m050e001p1" in ln)
    assert "west" in line


def test_assertions_show_kinds_and_rom_vs_offline():
    section = _section(_doc(), "## Assertions")
    assert "switch_write" in section and "var_write" in section
    aunt = section[section.index("m050e001p1"):section.index("m049e001p2")]
    lab = section[section.index("m049e001p2"):]
    assert "ROM" in aunt           # var_write is ROM-only (R11)
    assert "offline" in lab


def test_refusals_grouped_by_blocker_with_reason_and_detail():
    section = _section(_doc(), "## Refusals")
    assert section.index("#109") < section.index("C8")
    for text in ("map032/ev020/p0", "text_unnormalizable", "straight quote",
                 "map050/ev019/p0", "unparsed_state_write"):
        assert text in section


def test_elsewhere_shows_status_and_capability():
    section = _section(_doc(), "## Elsewhere")
    assert "blocked" in section and "rock_smash" in section
    assert "unreachable" in section and "map048/ev013/p0" in section


def test_elsewhere_shows_never_fires_with_detail():
    detail = "no warp lands on this arrival autorun's cell (5,6) on map 68 -- it never fires"
    plan = dataclasses.replace(
        PLAN, elsewhere=PLAN.elsewhere + (Elsewhere("map068/ev012/p1", "never_fires",
                                                     detail=detail),))
    section = _section(_doc(plan), "## Elsewhere")
    assert "never_fires" in section and "map068/ev012/p1" in section and detail in section


def test_order_dependent_write_shows_order_taken_and_end_value():
    # The lab page runs AFTER Auntie in this plan, so its write (False) lands last.
    section = _section(_doc(), "## Order-dependent writes")
    assert "switch:104" in section
    assert section.index(AUNT) < section.index(LAB)
    assert "False" in section.split(LAB, 1)[1]


def test_empty_sections_say_so():
    plan = ChapterPlan(chapter_id="CH05", predecessor="CH04", beats=BEATS[1:])
    doc = _doc(plan)
    for header in ("## Refusals", "## Elsewhere", "## Order-dependent writes"):
        body = _section(doc, header)[len(header):].strip()
        assert body, f"{header} is silently empty"
