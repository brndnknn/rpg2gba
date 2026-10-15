"""Lane-gated rocks, their precedence edge, teach placement and
`sight_trainers` emission (beat_gen/smash_lanes.py, CH08 Route 1)."""
from __future__ import annotations

from rpg2gba.beat_gen import smash_lanes as sl
from rpg2gba.beat_gen.__main__ import _with_teach
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs

MAP = 33


def _smash(rocks: tuple[int, ...]) -> PlannedBeat:
    rows = tuple(r for e in rocks for r in (f"map033/ev{e:03d}/p0", f"map033/ev{e:03d}/p0/b0"))
    return PlannedBeat(name="m033smash_rock_smash", template="smash", map_id=MAP, rows=rows,
                       group="m033smash_rock_smash", kwargs=make_kwargs(capability="rock_smash"))


def _trainer(event: int, template: str = "trainer", **kw: object) -> PlannedBeat:
    name = f"m033e{event:03d}_{template}"
    return PlannedBeat(name=name, template=template, map_id=MAP,
                       rows=(f"map033/ev{event:03d}/p0",), group=name, kwargs=make_kwargs(**kw))


APPROACH = {(MAP, 42): frozenset({(17, 23), (17, 25), (16, 24)}),
            (MAP, 29): frozenset({(13, 20), (13, 22)})}
LANES = {(MAP, 35): frozenset({(17, 23), (17, 25), (16, 24), (15, 23)}),
         (MAP, 39): frozenset({(13, 37)})}


def _split(beats):
    return sl.split_lane_gated(
        beats, approach_cells=lambda m, e: APPROACH.get((m, e), frozenset()),
        lane_of=lambda m, e: LANES.get((m, e)))


def test_gated_rock_moves_to_second_group():
    split = _split([_smash((29, 42)), _trainer(35), _trainer(39, "generic")])
    names = [b.name for b in split.beats]
    assert names[:2] == ["m033smash_rock_smash", "m033smash2_rock_smash"]
    main, second = split.beats[0], split.beats[1]
    assert second.rows == ("map033/ev042/p0", "map033/ev042/p0/b0")
    assert all("ev042" not in r for r in main.rows)
    assert second.group == "m033smash2_rock_smash" and second.template == "smash"
    assert dict(second.kwargs)["capability"] == "rock_smash"
    assert split.gates == {"m033smash2_rock_smash": (35,)}


def test_lane_free_approach_keeps_rock_in_main_group():
    split = _split([_smash((29,)), _trainer(35)])
    assert [b.name for b in split.beats] == ["m033smash_rock_smash", "m033e035_trainer"]
    assert split.gates == {}


def test_partial_lane_cover_is_not_gated():
    lanes = {(MAP, 35): frozenset({(17, 23), (17, 25)})}
    split = sl.split_lane_gated(
        [_smash((42,)), _trainer(35)], approach_cells=lambda m, e: APPROACH[(m, e)],
        lane_of=lambda m, e: lanes.get((m, e)))
    assert split.gates == {}


def test_union_of_lanes_gates_and_records_each_trainer():
    lanes = {(MAP, 35): frozenset({(17, 23), (17, 25)}), (MAP, 39): frozenset({(16, 24)})}
    split = sl.split_lane_gated(
        [_smash((42,)), _trainer(35), _trainer(39, "generic")],
        approach_cells=lambda m, e: APPROACH[(m, e)], lane_of=lambda m, e: lanes.get((m, e)))
    assert split.gates == {"m033smash_rock_smash": (35, 39)}
    assert [b.name for b in split.beats][0] == "m033smash_rock_smash"  # all gated: no rename


def test_inbound_trainer_does_not_gate():
    split = _split([_smash((42,)), _trainer(35, manifest_chapter_id="CH07")])
    assert split.gates == {}


def test_precedence_edge_follows_gating_trainer_group():
    beats = [_smash((29, 42)), _trainer(35)]
    split = _split(beats)
    edges = sl.wait_edges(split, split.beats)
    assert edges == {"map033/ev042/p0": (("map033/ev035/p0",),)}


def test_teach_stays_on_first_smash_beat_in_solved_order():
    split = _split([_smash((29, 42)), _trainer(35)])
    ordered = (split.beats[0], split.beats[2], split.beats[1])  # main, trainer, gated
    taught = _with_teach(ordered, taught=())
    kinds = {b.name: dict(b.kwargs).get("teach") for b in taught}
    assert kinds["m033smash_rock_smash"] == "teach_rock_smash"
    assert kinds["m033smash2_rock_smash"] is None


def test_sight_trainers_are_those_fought_later():
    split = _split([_smash((29, 42)), _trainer(35), _trainer(39, "generic")])
    main, second, t35, t39 = split.beats[0], split.beats[1], split.beats[2], split.beats[3]
    ordered = (main, t39, t35, second)
    out = sl.sight_trainers_for(ordered, lambda m, e: LANES.get((m, e)))
    assert out == {"m033smash_rock_smash": (35, 39), "m033smash2_rock_smash": ()}
