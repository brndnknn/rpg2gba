"""`beat_gen.adapt` warp lookup is arm-aware: a key-gated door page's warp
sits on its branch-arm row's floor, not the trunk's (map14006/ev017/p0)."""
import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor, make_params
from rpg2gba.beat_gen.adapt import _warp_kwargs, escort_kwargs, is_boundary_warp
from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch

TRUNK = "map14006/ev017/p0"
ARM0 = "map14006/ev017/p0/b0"
ARM1 = "map14006/ev017/p0/b1"
OTHER_PAGE_ARM = "map14006/ev017/p1/b0"   # a different page: never ours


def _floor(row_id: str, *warp_maps: int) -> RowFloor:
    return RowFloor(row_id=row_id, trigger="player_touch", refusals=(), assertions=frozenset(
        FloorAssertion(row_id=row_id, kind="warp", list_index=i, code=201,
                       params=make_params(map_id=m, x=0, y=0), tag="position")
        for i, m in enumerate(warp_maps)))


def _match() -> ArchetypeMatch:
    return ArchetypeMatch(archetype="warp", map_id=14006, event_id=17, params={},
                          roles={TRUNK: "warp"}, prescribed={TRUNK: "beat"})


def _beat(*rows: str, template: str = "warp") -> PlannedBeat:
    return PlannedBeat(name="b", template=template, map_id=14006, rows=rows, group="g")


def _const(map_id: int) -> str:
    return f"MAP_{map_id}"


def _dest(floors) -> str:
    return _warp_kwargs(_beat(TRUNK), _match(), floors, _const)["dest_map_constant"]


def test_trunk_only_warp_unchanged():
    floors = {TRUNK: _floor(TRUNK, 9)}
    assert _dest(floors) == "MAP_9"
    assert dict(escort_kwargs(_beat(TRUNK, template="escort"), floors, map_constant_fn=_const))[
        "dest_map_constant"] == "MAP_9"
    assert is_boundary_warp(_beat(TRUNK), floors, frozenset({1})) is True


def test_trunk_with_two_warps_still_raises():
    floors = {TRUNK: _floor(TRUNK, 9, 9)}
    with pytest.raises(ValueError, match="2 'warp' assertions"):
        _dest(floors)


def test_warp_on_arm_only_is_found():
    floors = {TRUNK: _floor(TRUNK), ARM0: _floor(ARM0, 9), ARM1: _floor(ARM1),
              OTHER_PAGE_ARM: _floor(OTHER_PAGE_ARM, 77)}
    assert _dest(floors) == "MAP_9"
    assert dict(escort_kwargs(_beat(TRUNK, template="escort"), floors, map_constant_fn=_const))[
        "dest_map_constant"] == "MAP_9"
    assert is_boundary_warp(_beat(TRUNK), floors, frozenset({9})) is False


def test_identical_destination_on_two_arms_counts_once():
    floors = {TRUNK: _floor(TRUNK), ARM0: _floor(ARM0, 9), ARM1: _floor(ARM1, 9)}
    assert _dest(floors) == "MAP_9"


def test_arms_with_different_destinations_raise():
    floors = {TRUNK: _floor(TRUNK), ARM0: _floor(ARM0, 9), ARM1: _floor(ARM1, 10)}
    with pytest.raises(ValueError, match="2 distinct 'warp' destinations"):
        _dest(floors)
    with pytest.raises(ValueError, match="distinct"):
        escort_kwargs(_beat(TRUNK, template="escort"), floors, map_constant_fn=_const)
    with pytest.raises(ValueError, match="2 warp destinations"):
        is_boundary_warp(_beat(TRUNK), floors, frozenset({9}))


def test_no_warp_anywhere_raises():
    floors = {TRUNK: _floor(TRUNK), ARM0: _floor(ARM0), ARM1: _floor(ARM1)}
    with pytest.raises(ValueError, match="0 'warp' assertions"):
        _dest(floors)
    with pytest.raises(ValueError, match="0 warp destinations"):
        is_boundary_warp(_beat(TRUNK), floors, frozenset({9}))
