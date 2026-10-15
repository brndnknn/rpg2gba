"""CH08 generator fixes (2026-10-15): a smash beat claims its rock's YES arm,
`erase_event` is a declarable generic kind (and a self-erase proves an
arrival page fired), and an arm of a floor-refused page inherits the refusal."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.beat_gen import __main__ as bg
from rpg2gba.beat_gen import group
from rpg2gba.beat_gen.arms import blocked_arms
from rpg2gba.beat_gen.plan import Selection
from rpg2gba.beat_gen.select import select_rows
from rpg2gba.chapter_manifest.schema import BranchRef, ManifestRow
from rpg2gba.playtest.archetypes import generic
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.story_state.model import RowVerdict

PAGE = "map033/ev029/p0"
YES, NO = f"{PAGE}/b0", f"{PAGE}/b1"


def _a(row, kind, idx=-1, **params) -> FloorAssertion:
    return FloorAssertion(row_id=row, kind=kind, list_index=idx,
                          code=None if idx < 0 else 355, params=make_params(**params))


def _floor(row, *assertions, refusals=()) -> RowFloor:
    return RowFloor(row_id=row, trigger="action", assertions=frozenset(assertions),
                    refusals=tuple(refusals))


def _branch(row_id, arm_kind="then", text="Kernel.pbRockSmash", ctype=12) -> ManifestRow:
    ref = BranchRef(arm_index=int(row_id[-1]), arm_kind=arm_kind, opener_code=111,
                    opener_index=0, choice_index=None, choice_text=None,
                    condition_type=ctype, condition_text=text, explicit=True)
    return ManifestRow(row_id=row_id, kind="branch", map_id=33, content_hash="x",
                       event_id=29, page_idx=0, branch=ref)


def _page(row_id=PAGE) -> ManifestRow:
    return ManifestRow(row_id=row_id, kind="page", map_id=33, content_hash="x",
                       event_id=29, page_idx=0)


def _verdict(row_id, blockers=()) -> RowVerdict:
    return RowVerdict(row_id=row_id, status="live", owner="CH08", stage=0, enabled_by=(),
                      killed_by=(), blockers=tuple(blockers), forced=False, refusals=(),
                      detail=None)


# --- fix 1: the smash beat claims the YES arm ---------------------------------

def test_rock_yes_arm_is_the_then_arm_of_the_rock_smash_test():
    assert bg._rock_yes_arm(_branch(YES))
    assert not bg._rock_yes_arm(_branch(NO, arm_kind="else"))
    assert not bg._rock_yes_arm(_branch(YES, text="Kernel.pbSomethingElse"))
    assert not bg._rock_yes_arm(_page())


def test_blocked_arms_leaves_a_held_arm_alone():
    yes, no = _branch(YES), _branch(NO, arm_kind="else")
    sel = Selection(owned=(yes, no), refusals=(), elsewhere=())
    verdicts = {r.row_id: _verdict(r.row_id, ["capability:rock_smash"]) for r in (yes, no)}
    out = blocked_arms(sel, verdicts, {YES})
    assert [r.row_id for r in out.owned] == [YES]
    assert [e.row_id for e in out.elsewhere] == [NO]
    plain = blocked_arms(sel, verdicts, set())
    assert plain.owned == ()


def test_plan_beats_groups_the_yes_arm_into_the_smash_beat():
    rows = [_page(), _branch(YES)]
    floors = {PAGE: _floor(PAGE, _a(PAGE, "blocked_obstacle", x=13, y=21,
                                    capability="rock_smash")),
              YES: _floor(YES, _a(YES, "erase_event", 12, event_id=29))}
    beats = group.plan_beats(rows, [], floors, held_obstacles={(33, 29)})
    assert [(b.template, b.rows) for b in beats] == [("smash", (PAGE, YES))]


def test_smash_beat_declares_the_arm_floor_it_checks():
    page_floor = _floor(PAGE, _a(PAGE, "blocked_obstacle", x=13, y=21, capability="rock_smash"),
                        _a(PAGE, "trigger", trigger="action"), _a(PAGE, "completes"))
    yes_floor = _floor(
        YES, _a(YES, "trigger", trigger="action"), _a(YES, "completes"),
        _a(YES, "erase_event", 12, event_id=29),
        _a(YES, "audio", 1, code=250, name="notverydamage"),
        _a(YES, "visual", 13, code=355, detail="pbRockSmashRandomEncounter"))
    floors = {PAGE: page_floor, YES: yes_floor}
    b = ChapterBuilder("TEST", doc="smash arm")
    generic.smash_beat(b, chapter_id="CH08", beat_name="smash", rows=(PAGE, YES),
                       capability="rock_smash", floor_lookup=lambda r: floors[r])
    (beat,) = b.build().beats
    got = {(a.row_id, a.kind) for a in beat.assertions}
    assert got == {(PAGE, "smashed_obstacle"), (YES, "trigger"), (YES, "completes"),
                   (YES, "erase_event")}
    from rpg2gba.beat_floor.coverage import graded_gaps
    for row_id, floor in floors.items():
        assert not graded_gaps(floor, beat.assertions), row_id


def test_smash_beat_rejects_an_arm_without_its_page():
    yes_floor = _floor(YES, _a(YES, "erase_event", 12, event_id=29))
    page_floor = _floor(PAGE, _a(PAGE, "blocked_obstacle", x=13, y=21, capability="rock_smash"))
    other = "map033/ev036/p0"
    floors = {YES: yes_floor, other: _floor(other, _a(other, "blocked_obstacle", x=1, y=1,
                                                    capability="rock_smash")),
              PAGE: page_floor}
    b = ChapterBuilder("TEST", doc="x")
    with pytest.raises(ValueError, match="no blocked_obstacle page"):
        generic.smash_beat(b, chapter_id="CH08", beat_name="smash", rows=(other, YES),
                           capability="rock_smash", floor_lookup=lambda r: floors[r])


# --- fix 2: erase_event ---------------------------------------------------------

def test_erase_event_is_declarable_and_handled():
    assert "erase_event" in generic.GENERIC_EXECUTED_KINDS
    assert set(generic.STEP_HANDLERS) == generic.GENERIC_EXECUTED_KINDS


class _Emu:
    def __init__(self, present: list[int]) -> None:
        self._present = present

    def object_events(self):
        return [SimpleNamespace(local_id=i) for i in self._present]

    def screenshot(self, name: str) -> str:
        return name


def _erase_step() -> generic.Step:
    return generic.Step("map031/ev049/p2", "erase_event", 3, make_params(event_id=49))


def test_erase_handler_passes_when_the_object_is_gone(monkeypatch):
    monkeypatch.setattr(generic, "local_id", lambda const, ev: 7)
    generic.STEP_HANDLERS["erase_event"](_Emu([1, 2]), "b", _erase_step())


def test_erase_handler_fails_loud_when_the_object_is_still_active(monkeypatch):
    monkeypatch.setattr(generic, "local_id", lambda const, ev: 7)
    with pytest.raises(ScenarioError, match="still an active object"):
        generic.STEP_HANDLERS["erase_event"](_Emu([7]), "b", _erase_step())


ARRIVAL_ROW = "map033/ev004/p0"  # a real parallel page, event 4 (CH02)


def _arrival_floor(*assertions) -> RowFloor:
    return RowFloor(row_id=ARRIVAL_ROW, trigger="parallel", assertions=frozenset(assertions),
                    refusals=())


def _declared_kinds(floor: RowFloor) -> set[str]:
    b = ChapterBuilder("TEST", doc="x")
    generic.generic_beat(b, chapter_id="CH02", beat_name="arr", rows=(ARRIVAL_ROW,),
                         floor_lookup=lambda r: floor, approach_prefer="arrive@(70,11)")
    (beat,) = b.build().beats
    return {a.kind for a in beat.assertions}


def test_self_erase_proves_an_autorun_page_fired():
    floor = _arrival_floor(_a(ARRIVAL_ROW, "trigger", trigger="parallel"),
                           _a(ARRIVAL_ROW, "erase_event", 3, event_id=4),
                           _a(ARRIVAL_ROW, "completes"))
    assert _declared_kinds(floor) == {"trigger", "erase_event", "completes"}


def test_erasing_another_event_does_not_prove_the_page_fired():
    floor = _arrival_floor(_a(ARRIVAL_ROW, "trigger", trigger="parallel"),
                           _a(ARRIVAL_ROW, "erase_event", 3, event_id=99),
                           _a(ARRIVAL_ROW, "completes"))
    assert _declared_kinds(floor) == {"erase_event", "completes"}


# --- fix 3: an arm of a refused page inherits the refusal -------------------------

def test_arm_of_a_floor_refused_page_is_refused_with_the_parents_blocker():
    page, arm = _page("map050/ev027/p0"), _branch("map050/ev027/p0/b0")
    arm = ManifestRow(**{**arm.__dict__, "map_id": 50, "event_id": 27, "row_id": arm.row_id})
    refusal = FloorRefusal(page.row_id, "text_unnormalizable", 0, 101, "dex-count text")
    floors = {page.row_id: _floor(page.row_id, refusals=[refusal]),
              arm.row_id: _floor(arm.row_id, _a(arm.row_id, "completes"))}
    verdicts = {r.row_id: RowVerdict(row_id=r.row_id, status="live", owner="CH08", stage=0,
                                     enabled_by=(), killed_by=(), blockers=(), forced=False,
                                     refusals=(), detail=None) for r in (page, arm)}
    sel = select_rows([page, arm], verdicts, floors)
    assert sel.owned == ()
    by_id = {r.row_id: r for r in sel.refusals}
    assert set(by_id) == {page.row_id, arm.row_id}
    assert by_id[arm.row_id].reason == by_id[page.row_id].reason == "text_unnormalizable"
    assert by_id[arm.row_id].blocker == by_id[page.row_id].blocker
    assert by_id[arm.row_id].detail == "dex-count text"
