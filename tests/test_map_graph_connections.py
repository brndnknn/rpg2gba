"""Tests for map_graph seam-connection geometry (connections.dat support).

Anchor semantics under test mirror Essentials 107__PField_Map.rb
getMapConnections/getMapEdge: (edge, offset) -> anchor point N->(off,0),
S->(off,h), W->(0,off), E->(w,off); the two anchors of an entry coincide in
world space, so other_origin = my_anchor - other_anchor.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_graph  # noqa: E402

# Kevlar-shaped fixture: A (50x50) north edge offset 11 <-> B (40x57) south
# edge offset 0, plus an E/W pair C (72x64) east 26 <-> Dm (79x53) west 0.
DIMS = {1: (50, 50), 2: (40, 57), 3: (72, 64), 4: (79, 53), 5: (10, 10)}
RAW = (
    (1, "N", 11, 2, "S", 0),
    (3, "E", 26, 4, "W", 0),
)


@pytest.fixture()
def patched(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(map_graph, "_load_connections_raw", lambda: RAW)
    monkeypatch.setattr(map_graph, "map_dims", lambda mid: DIMS[mid])
    monkeypatch.setattr(map_graph, "map_display_name", lambda mid: f"Map{mid:03d}")


def test_north_south_pair_forward(patched) -> None:
    (c,) = map_graph.connections_for(1)
    assert c["id"] == 2
    assert c["edge"] == "N"
    # B's origin: my anchor (11,0) minus B's anchor (0,57)
    assert c["origin"] == [11, -57]
    # shared x range on my north edge: B spans x 11..51, clipped to my width 50
    assert c["band"] == [11, 50]


def test_north_south_pair_reverse(patched) -> None:
    (c,) = map_graph.connections_for(2)
    assert c["id"] == 1
    assert c["edge"] == "S"
    assert c["origin"] == [-11, 57]
    # A spans x -11..39 in B's space, clipped to B's width 40
    assert c["band"] == [0, 39]


def test_east_west_pair(patched) -> None:
    (c,) = map_graph.connections_for(3)
    assert c["edge"] == "E"
    assert c["origin"] == [72, 26]
    # y range: other spans y 26..79 in my space, clipped to my height 64
    assert c["band"] == [26, 64]
    (r,) = map_graph.connections_for(4)
    assert r["edge"] == "W"
    assert r["origin"] == [-72, -26]
    assert r["band"] == [0, 38]  # my y 0..38 maps into the other's 26..64


def test_component_layout_normalizes_to_origin(patched) -> None:
    lay = map_graph.component_layout(1)
    by_id = {m["id"]: m for m in lay["members"]}
    assert set(by_id) == {1, 2}
    # B sits above A: after normalization B is at (11-min_x, 0) ... compute:
    # A at (0,0), B at (11,-57); min = (0,-57) -> A (0,57), B (11,0)
    assert (by_id[1]["ox"], by_id[1]["oy"]) == (0, 57)
    assert (by_id[2]["ox"], by_id[2]["oy"]) == (11, 0)
    assert lay["w"] == max(0 + 50, 11 + 40)
    assert lay["h"] == 57 + 50
    assert lay["anchor"] == 1


def test_component_layout_isolated_map(patched) -> None:
    lay = map_graph.component_layout(5)  # has dims, no connections
    assert [m["id"] for m in lay["members"]] == [5]
    assert (lay["w"], lay["h"]) == (10, 10)


def test_degenerate_band_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    # other map so far off the shared edge that no cells overlap -> dropped
    monkeypatch.setattr(map_graph, "_load_connections_raw",
                        lambda: ((1, "N", 100, 2, "S", 0),))
    monkeypatch.setattr(map_graph, "map_dims", lambda mid: DIMS[mid])
    monkeypatch.setattr(map_graph, "map_display_name", lambda mid: f"Map{mid:03d}")
    assert map_graph.connections_for(1) == []


def test_relationships_carry_connections(patched, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(map_graph, "load_map_names", lambda: {1: "A", 2: "B"})
    monkeypatch.setattr(map_graph, "_map_id_universe", lambda: frozenset({1, 2}))
    monkeypatch.setattr(map_graph, "_load_map_infos", lambda: {})
    monkeypatch.setattr(map_graph, "extract_warp_targets", lambda mid: [])
    rel = map_graph.map_relationships(1)
    assert rel["connections"] and rel["connections"][0]["id"] == 2
