"""Tests for `rpg2gba.beat_gen.seam` (C6 Task 3; A1).

Synthetic `MapGraph`s are built the way `tests/test_traversal_graph.py`
does (the dataclass constructor with a `blocked` grid).

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 3.
"""
from __future__ import annotations

import pytest

from rpg2gba.beat_gen import seam
from rpg2gba.beat_gen.seam import SeamCrossing
from rpg2gba.chapter_manifest.schema import ManifestRow, SeamRef
from rpg2gba.routing.connections import MapConnection
from rpg2gba.traversal.direction import Direction
from rpg2gba.traversal.graph import MapGraph

def _graph(map_id: int, w: int, h: int, walls: set[tuple[int, int]] = frozenset()) -> MapGraph:
    blocked = {(x, y): (x, y) in walls for x in range(w) for y in range(h)}
    return MapGraph(map_id=map_id, width=w, height=h, tileset_id=0, blocked=blocked)


def _row(direction: str, offset: int = 0, other_offset: int = 0, *, a: int = 1,
         b: int = 2) -> ManifestRow:
    opposite = {"N": "S", "S": "N", "E": "W", "W": "E"}[direction]
    return ManifestRow(
        row_id=f"map{a:03d}/seam/{direction}/map{b:03d}", kind="seam", map_id=a,
        content_hash="x",
        seam=SeamRef(map_id=a, direction=direction, offset=offset, other_map_id=b,
                     other_direction=opposite, other_offset=other_offset))


# --- connection_for -----------------------------------------------------------

def test_connection_for_maps_every_field():
    assert seam.connection_for(_row("N", 11, 0, a=31, b=35)) == MapConnection(
        from_map=31, direction=Direction.NORTH, offset=11, to_map=35, to_offset=0)


def test_connection_for_rejects_non_seam_rows():
    page = ManifestRow(row_id="map001/ev001/p0", kind="page", map_id=1, content_hash="x")
    with pytest.raises(ValueError):
        seam.connection_for(page)


# --- seam_crossings -----------------------------------------------------------

def test_open_north_seam_every_column():
    got = seam.seam_crossings(_row("N"), from_graph=_graph(1, 3, 4), to_graph=_graph(2, 3, 4))
    assert got == tuple(SeamCrossing((x, 0), (x, 3), "UP") for x in range(3))


def test_offset_shift_is_applied():
    # from offset 2, to offset 0: this map's column x is the other's x - 2.
    got = seam.seam_crossings(_row("N", 2, 0), from_graph=_graph(1, 5, 4),
                              to_graph=_graph(2, 5, 4))
    assert [(c.exit_cell, c.entry_cell) for c in got] == [((2, 0), (0, 3)),
                                                          ((3, 0), (1, 3)),
                                                          ((4, 0), (2, 3))]


def test_walled_exit_or_entry_is_not_legal():
    got = seam.seam_crossings(_row("N"), from_graph=_graph(1, 3, 4, {(0, 0)}),
                              to_graph=_graph(2, 3, 4, {(2, 3)}))
    assert [c.exit_cell for c in got] == [(1, 0)]


def test_closed_landing_is_not_legal():
    # (1, 3) is open, but the step after it, (1, 2), is a wall: you'd arrive
    # and be stuck against it.
    got = seam.seam_crossings(_row("N"), from_graph=_graph(1, 3, 4),
                              to_graph=_graph(2, 3, 4, {(1, 2)}))
    assert [c.exit_cell for c in got] == [(0, 0), (2, 0)]


@pytest.mark.parametrize("direction, press, exit_cell, entry_cell", [
    ("S", "DOWN", (0, 3), (0, 0)),
    ("E", "RIGHT", (2, 0), (0, 0)),
    ("W", "LEFT", (0, 0), (2, 0)),
])
def test_other_directions(direction, press, exit_cell, entry_cell):
    got = seam.seam_crossings(_row(direction), from_graph=_graph(1, 3, 4),
                              to_graph=_graph(2, 3, 4))
    assert got[0] == SeamCrossing(exit_cell, entry_cell, press)
    assert {c.press for c in got} == {press}


def test_all_walled_is_empty_not_an_error():
    walls = {(x, 0) for x in range(3)}
    assert seam.seam_crossings(_row("N"), from_graph=_graph(1, 3, 4, walls),
                               to_graph=_graph(2, 3, 4)) == ()


def test_no_overlap_fails_loud():
    with pytest.raises(ValueError):
        seam.seam_crossings(_row("N", 10, 0), from_graph=_graph(1, 3, 4),
                            to_graph=_graph(2, 3, 4))


def test_sorted_and_deterministic():
    kwargs = {"from_graph": _graph(1, 4, 4), "to_graph": _graph(2, 4, 4)}
    got = seam.seam_crossings(_row("N"), **kwargs)
    assert list(got) == sorted(got)
    assert got == seam.seam_crossings(_row("N"), **kwargs)


# --- real data: the Kevlar case A1 names ------------------------------------

def test_real_kevlar_seam_x31_closed_x32_open():
    from rpg2gba.playtest.archetypes import load_chapter_rows
    from rpg2gba.traversal.graph import build_map_graph

    (row,) = [r for r in load_chapter_rows("CH03") if r.row_id == "map031/seam/N/map035"]
    got = seam.seam_crossings(row, from_graph=build_map_graph(31), to_graph=build_map_graph(35))
    exits = {c.exit_cell for c in got}
    assert (32, 0) in exits
    assert (31, 0) not in exits      # walkable pair, but the landing is walled
    # Since 2026-10-06 31<->35 is a real whole-edge connection (the arrow-warp
    # seam was retired), so every walkable-pair column crosses, not just (32,0).
    assert len(got) > 1


# --- arrow-warp seams (seam_warps.json substitution) --------------------------

def _inject_arrow_seam(monkeypatch, cells_a, cells_b, *, map_a: int = 1, map_b: int = 2):
    from rpg2gba.playtest import cells as cells_mod

    monkeypatch.setattr(cells_mod, "_SEAM_WARPS_CACHE", [
        {"id": "synthetic", "map_a": map_a, "map_b": map_b,
         "cells_a": [list(c) for c in cells_a], "cells_b": [list(c) for c in cells_b]}])


def test_arrow_seam_drops_exits_outside_the_arrow_list(monkeypatch):
    _inject_arrow_seam(monkeypatch, [(0, 0), (1, 0)], [(0, 3), (1, 3)])
    got = seam.seam_crossings(_row("N"), from_graph=_graph(1, 4, 4), to_graph=_graph(2, 4, 4))
    # (2, 0) and (3, 0) are walkable with open landings but do not warp.
    assert [c.exit_cell for c in got] == [(0, 0), (1, 0)]


def test_arrow_seam_drops_cell_whose_approach_is_blocked(monkeypatch):
    _inject_arrow_seam(monkeypatch, [(0, 0), (1, 0)], [(0, 3), (1, 3)])
    # (0, 1) is the approach cell behind arrow (0, 0) when pressing UP.
    got = seam.seam_crossings(_row("N"), from_graph=_graph(1, 4, 4, {(0, 1)}),
                              to_graph=_graph(2, 4, 4))
    assert [c.exit_cell for c in got] == [(1, 0)]


def test_arrow_seam_applies_in_the_reverse_direction(monkeypatch):
    # Route-2-like side: the arrow list is cells_b, direction S, approach is y - 1.
    _inject_arrow_seam(monkeypatch, [(0, 0), (1, 0)], [(0, 3), (1, 3)])
    got = seam.seam_crossings(_row("S", a=2, b=1), from_graph=_graph(2, 4, 4, {(0, 2)}),
                              to_graph=_graph(1, 4, 4))
    assert [c.exit_cell for c in got] == [(1, 3)]
    assert {c.press for c in got} == {"DOWN"}


def test_pair_without_a_seam_entry_keeps_whole_edge(monkeypatch):
    # A seam entry exists, but for an unrelated pair: this pair is unfiltered.
    _inject_arrow_seam(monkeypatch, [(0, 0)], [(0, 3)], map_a=7, map_b=8)
    got = seam.seam_crossings(_row("N"), from_graph=_graph(1, 3, 4, {(0, 1)}),
                              to_graph=_graph(2, 3, 4))
    assert [c.exit_cell for c in got] == [(0, 0), (1, 0), (2, 0)]
