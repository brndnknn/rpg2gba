"""`cells.trainer_sight_lanes`: the cells a sight trainer can see a player from."""
import pytest

from rpg2gba.playtest import cells


class _Graph:
    def __init__(self, walls):
        self._walls = walls

    def is_walkable(self, cell):
        return cell not in self._walls and 0 <= cell[0] < 30 and 0 <= cell[1] < 30


def _setup(monkeypatch, objects, walls=frozenset()):
    monkeypatch.setattr(cells, "_graph_for", lambda m, *, resolver: (0, _Graph(walls)))
    monkeypatch.setattr(cells, "_emitted_map_json", lambda m: {"object_events": objects})


def _trainer(**kw):
    base = {"x": 10, "y": 10, "movement_type": "MOVEMENT_TYPE_FACE_DOWN",
            "movement_range_x": 0, "movement_range_y": 0,
            "trainer_type": "TRAINER_TYPE_NORMAL", "trainer_sight_or_berry_tree_id": "3"}
    return {**base, **kw}


def test_a_facing_trainer_sees_only_its_named_directions(monkeypatch):
    _setup(monkeypatch, [_trainer(movement_type="MOVEMENT_TYPE_FACE_DOWN_AND_RIGHT")])
    assert cells.trainer_sight_lanes("M")[1] == frozenset(
        {(10, 11), (10, 12), (10, 13), (11, 10), (12, 10), (13, 10)})


def test_a_ray_stops_at_a_wall(monkeypatch):
    _setup(monkeypatch, [_trainer()], walls={(10, 12)})
    assert cells.trainer_sight_lanes("M")[1] == frozenset({(10, 11)})


def test_a_walking_trainer_sees_from_its_whole_movement_box(monkeypatch):
    _setup(monkeypatch, [_trainer(movement_type="MOVEMENT_TYPE_WALK_UP_AND_DOWN",
                                  movement_range_y=1, trainer_sight_or_berry_tree_id="1")])
    lane = cells.trainer_sight_lanes("M")[1]
    # the box itself, plus one cell every way from each of (10,9) (10,10) (10,11)
    assert {(10, 9), (10, 11), (10, 8), (10, 12), (9, 9), (11, 11)} <= lane
    # the spawn cell counts once the trainer has walked off it; range 1 stops short of (10,13)
    assert (10, 10) in lane and (10, 13) not in lane


def test_non_trainers_have_no_lane_and_local_ids_are_one_based(monkeypatch):
    _setup(monkeypatch, [{"x": 1, "y": 1, "trainer_type": "TRAINER_TYPE_NONE"}, _trainer()])
    lanes = cells.trainer_sight_lanes("M")
    assert list(lanes) == [2]


@pytest.mark.parametrize("movement", ["MOVEMENT_TYPE_LOOK_AROUND", "MOVEMENT_TYPE_FACE_DOWN_UP_AND_LEFT"])
def test_direction_parsing(monkeypatch, movement):
    _setup(monkeypatch, [_trainer(movement_type=movement, trainer_sight_or_berry_tree_id="1")])
    lane = cells.trainer_sight_lanes("M")[1]
    expected = {(10, 11), (10, 9), (9, 10)} | ({(11, 10)} if "LOOK_AROUND" in movement else set())
    assert lane == frozenset(expected)
