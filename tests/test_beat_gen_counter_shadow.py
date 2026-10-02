"""`beat_gen.counter_shadow`: an invisible action event on a counter cell with
an object across the counter from every side never fires on the ROM
(pokeemerald reaches across the counter to the object first). Shaped like
Kevlar's Poke Mart, map067: clerk at (1,0), counter at (1,1), player stands
at (1,2) -- the only such cell in the converted corpus (ROM run 66)."""
from __future__ import annotations

from rpg2gba.beat_gen.counter_shadow import counter_shadow_proof
from rpg2gba.traversal.graph import MapGraph

_COUNTER = (1, 1)
_CLERK = (1, 0)


def _graph(blocked: set[tuple[int, int]]) -> MapGraph:
    cells = {(x, y): (x, y) in blocked for x in range(3) for y in range(3)}
    return MapGraph(map_id=67, width=3, height=3, tileset_id=0, blocked=cells,
                    counters=frozenset({_COUNTER}))


# Counter row y=1 is solid; the clerk's row is behind it; the player row is open.
_MART = _graph({(0, 1), (1, 1), (2, 1), (0, 0), (2, 0)})


def test_counter_event_shadowed_by_the_object_behind_never_fires():
    proof = counter_shadow_proof("map067/ev003/p0", _COUNTER, graph=_MART,
                                 object_cells={_CLERK})
    assert proof is not None
    assert "never fires" in proof and "(1, 0)" in proof


def test_no_object_behind_the_counter_fires():
    # Kevlar's Center counter bg event (7,12): no object on any side.
    assert counter_shadow_proof("map068/ev012/p0", _COUNTER, graph=_MART,
                                object_cells=set()) is None


def test_an_event_that_is_itself_an_object_fires():
    assert counter_shadow_proof("map067/ev003/p0", _COUNTER, graph=_MART,
                                object_cells={_CLERK, _COUNTER}) is None


def test_a_cell_that_is_no_counter_is_not_this_rules_business():
    plain = MapGraph(map_id=67, width=3, height=3, tileset_id=0,
                     blocked=_MART.blocked, counters=frozenset())
    assert counter_shadow_proof("map067/ev003/p0", _COUNTER, graph=plain,
                                object_cells={_CLERK}) is None


def test_one_unshadowed_side_is_enough_to_fire():
    # The counter's east end is open floor: pressing A from (2,1) facing west
    # finds no object across at (0,1), so the counter event answers there.
    open_east = _graph({(0, 1), (1, 1), (0, 0), (2, 0)})
    assert counter_shadow_proof("map067/ev003/p0", _COUNTER, graph=open_east,
                                object_cells={_CLERK}) is None


def test_the_clerks_own_floor_is_not_a_side_the_player_presses_from():
    # Behind the counter is walkable floor, but the clerk stands on it.
    behind_open = _graph({(0, 1), (1, 1), (2, 1)})
    assert counter_shadow_proof("map067/ev003/p0", _COUNTER, graph=behind_open,
                                object_cells={_CLERK}) is not None
