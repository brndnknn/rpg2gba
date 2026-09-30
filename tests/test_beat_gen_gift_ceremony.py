"""`beat_gen.gift_ceremony`: a refused conditional gift inside a claimed page
marks its beat's `gift_ceremonies` (ROM run 27)."""
from __future__ import annotations

from rpg2gba.beat_floor.assertion import FloorRefusal, RowFloor
from rpg2gba.beat_gen.gift_ceremony import annotate_gift_ceremonies
from rpg2gba.beat_gen.plan import PlannedBeat, Refusal, make_kwargs

PAGE = "map050/ev019/p0"
ARM = f"{PAGE}/b1"
DETAIL = "effect 'pbAddPokemon' under control flow"


def _beat(template: str = "generic", rows: tuple[str, ...] = (PAGE,)) -> PlannedBeat:
    return PlannedBeat(name="m050e019p0", template=template, group="g", rows=rows,
                       map_id=50, kwargs=make_kwargs())


def _floor(reason: str = "conditional_script_effect", detail: str = DETAIL) -> RowFloor:
    refusals = tuple(FloorRefusal(ARM, reason, 9, 355, f"{detail}: stmt {i}") for i in range(3))
    return RowFloor(row_id=ARM, trigger="action", assertions=frozenset(), refusals=refusals)


def _refusal(reason: str = "conditional_script_effect", detail: str = DETAIL) -> Refusal:
    return Refusal(ARM, "floor", reason, detail)


def test_the_page_beat_gets_one_ceremony_per_list_index():
    (beat,) = annotate_gift_ceremonies((_beat(),), (_refusal(),), {ARM: _floor()})
    assert dict(beat.kwargs)["gift_ceremonies"] == (9,)


def test_other_refusals_and_other_templates_are_left_alone():
    other = _refusal(detail="effect 'pbReceiveItem' under control flow")
    (beat,) = annotate_gift_ceremonies((_beat(),), (other,), {ARM: _floor(detail=other.detail)})
    assert "gift_ceremonies" not in dict(beat.kwargs)
    (beat,) = annotate_gift_ceremonies((_beat(template="warp"),), (_refusal(),), {ARM: _floor()})
    assert "gift_ceremonies" not in dict(beat.kwargs)
    (beat,) = annotate_gift_ceremonies((_beat(rows=("map050/ev005/p0",)),), (_refusal(),),
                                       {ARM: _floor()})
    assert "gift_ceremonies" not in dict(beat.kwargs)
