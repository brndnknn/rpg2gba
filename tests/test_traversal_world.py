"""Unit tests for `rpg2gba.traversal.world` -- the corpus-wide map adjacency
graph (warps + connections + seam warps). A small synthetic fixture (tmp_path)
covers the core logic; one slower test exercises the real decoded corpus for
stable structural facts, skipped cleanly on a clean checkout.

CLAUDE.md §4.6: round-trip/consistency (reciprocal edges from connections and
seam warps), golden-shaped assertions against the real corpus, and explicit
edge-case coverage (one-way warps, unknown-map fail-loud cases).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.traversal.collision import DEFAULT_MAPS_DIR
from rpg2gba.traversal.world import (
    DEFAULT_CONNECTIONS_JSON,
    DEFAULT_MAP_INFOS_JSON,
    build_world_graph,
)

# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------


def _warp_event(event_id: int, x: int, y: int, mode: int, dest_map: int, dest_x: int, dest_y: int) -> dict:
    return {
        "id": event_id,
        "x": x,
        "y": y,
        "pages": [
            {
                "list": [
                    {"code": 201, "parameters": [mode, dest_map, dest_x, dest_y, 2]},
                ]
            }
        ],
    }


def _map_json(map_id: int, events: list[dict]) -> dict:
    return {"map_id": map_id, "events": events}


def _write_corpus(
    tmp_path: Path,
    map_events: dict[int, list[dict]],
    infos: dict[int, str],
    connections: list[list] | None = None,
    seams: list[dict] | None = None,
) -> dict[str, Path]:
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    for map_id, events in map_events.items():
        path = maps_dir / f"Map{map_id:03d}.json"
        path.write_text(json.dumps(_map_json(map_id, events)), encoding="utf-8")

    map_infos_path = tmp_path / "map_infos.json"
    map_infos_path.write_text(
        json.dumps({str(mid): {"name": name} for mid, name in infos.items()}),
        encoding="utf-8",
    )

    connections_path = tmp_path / "connections.json"
    connections_path.write_text(json.dumps(connections or []), encoding="utf-8")

    seam_warps_path = tmp_path / "seam_warps.json"
    seam_warps_path.write_text(json.dumps({"seams": seams or []}), encoding="utf-8")

    return {
        "maps_dir": maps_dir,
        "map_infos": map_infos_path,
        "connections_json": connections_path,
        "seam_warps": seam_warps_path,
    }


def _build_fixture_graph(tmp_path: Path):
    """A 5-map synthetic world:

    - map1 <-> map2: reciprocal warp pair (bidirectional).
    - map2 -> map3: one-way warp (no warp back).
    - map4: one variable-driven (mode!=0) warp event -- blind-spot count only.
    - map1 <-> map4: connections.json row (bidirectional).
    - map3 <-> map4: seam_warps.json seam (bidirectional).
    - map5: map_infos-only, no map file -- orphan, unreachable.
    - map3: has a map file but no map_infos entry.
    """
    paths = _write_corpus(
        tmp_path,
        map_events={
            1: [_warp_event(10, 5, 5, 0, 2, 1, 1)],
            2: [
                _warp_event(20, 1, 1, 0, 1, 5, 5),
                _warp_event(21, 2, 2, 0, 3, 0, 0),
            ],
            3: [],
            4: [_warp_event(40, 3, 3, 1, 99, 0, 0)],  # variable-driven, dest 99 never checked
        },
        infos={1: "Map One", 2: "Map Two", 4: "Map Four", 5: "Ghost Town"},
        connections=[[1, "E", 0, 4, "W", 0]],
        seams=[
            {
                "id": "s1",
                "map_a": 3,
                "map_b": 4,
                "cells_a": [[0, 0]],
                "cells_b": [[0, 0]],
                "direction_a": "up",
                "direction_b": "down",
            }
        ],
    )
    return build_world_graph(**paths)


# ---------------------------------------------------------------------------
# Construction + edge sources
# ---------------------------------------------------------------------------


def test_map_universe_and_orphan_bookkeeping(tmp_path):
    g = _build_fixture_graph(tmp_path)
    assert g.map_ids == frozenset({1, 2, 3, 4, 5})
    assert g.maps_without_info == frozenset({3})
    assert g.infos_without_map == frozenset({5})
    assert g.names[5] == "Ghost Town"
    assert g.names[3] == "Map003"  # no info entry -> fallback name


def test_warp_edges_carry_cells_and_event_id(tmp_path):
    g = _build_fixture_graph(tmp_path)
    warp_1_to_2 = [e for e in g.edges_from(1) if e.kind == "warp"]
    assert len(warp_1_to_2) == 1
    edge = warp_1_to_2[0]
    assert edge.dst_map == 2
    assert edge.src_cell == (5, 5)
    assert edge.dst_cell == (1, 1)
    assert edge.event_id == 10


def test_connection_edges_emitted_both_directions(tmp_path):
    g = _build_fixture_graph(tmp_path)
    assert any(e.kind == "connection" and e.dst_map == 4 for e in g.edges_from(1))
    assert any(e.kind == "connection" and e.dst_map == 1 for e in g.edges_from(4))


def test_seam_warp_edges_emitted_both_directions_with_cells(tmp_path):
    g = _build_fixture_graph(tmp_path)
    fwd = [e for e in g.edges_from(3) if e.kind == "seam_warp"]
    back = [e for e in g.edges_from(4) if e.kind == "seam_warp"]
    assert len(fwd) == 1 and fwd[0].dst_map == 4
    assert fwd[0].src_cell == (0, 0) and fwd[0].dst_cell == (0, 0)
    assert len(back) == 1 and back[0].dst_map == 3


def test_variable_warp_counted_but_not_edged(tmp_path):
    g = _build_fixture_graph(tmp_path)
    assert g.variable_warp_count == 1
    assert g.variable_warp_maps == {4: 1}
    # No edge from map4 to the nonexistent destination 99, or anywhere else
    # via that event.
    assert g.edges_from(4) == [e for e in g.edges_from(4) if e.kind != "warp"]


# ---------------------------------------------------------------------------
# One-way detection / bidirectionality
# ---------------------------------------------------------------------------


def test_reciprocal_warp_pair_is_bidirectional(tmp_path):
    g = _build_fixture_graph(tmp_path)
    assert g.is_bidirectional(1, 2) is True


def test_one_way_warp_is_detected(tmp_path):
    g = _build_fixture_graph(tmp_path)
    assert g.is_bidirectional(2, 3) is False
    assert (2, 3) in g.one_way_pairs()
    assert (3, 2) not in g.one_way_pairs()


def test_connection_and_seam_warp_pairs_are_not_one_way(tmp_path):
    g = _build_fixture_graph(tmp_path)
    one_way = set(g.one_way_pairs())
    assert (1, 4) not in one_way and (4, 1) not in one_way
    assert (3, 4) not in one_way and (4, 3) not in one_way


# ---------------------------------------------------------------------------
# Graph-wide queries
# ---------------------------------------------------------------------------


def test_reachable_from_is_transitive(tmp_path):
    g = _build_fixture_graph(tmp_path)
    # 1 -> 2 (warp), 1 -> 4 (connection), 2 -> 3 (warp), 4 -> 3 (seam_warp).
    assert g.reachable_from(1) == {1, 2, 3, 4}


def test_connected_components_groups_orphan_separately(tmp_path):
    g = _build_fixture_graph(tmp_path)
    components = g.connected_components()
    assert {1, 2, 3, 4} in components
    assert {5} in components
    assert len(components) == 2


def test_orphan_maps_reports_isolated_map(tmp_path):
    g = _build_fixture_graph(tmp_path)
    assert g.orphan_maps() == [5]


def test_shortest_path_annotates_edge_kinds(tmp_path):
    g = _build_fixture_graph(tmp_path)
    # map3's only outgoing edge is the seam warp to map4; map4's only route
    # to map1 is the connection -- this path is the unique shortest route,
    # unlike map2->map4 which has two equal-length routes (BFS tie-breaking
    # would make that assertion implementation-dependent).
    path = g.shortest_path(3, 1)
    assert path is not None
    kinds = [e.kind for e in path]
    assert kinds == ["seam_warp", "connection"]
    assert path[-1].dst_map == 1


def test_shortest_path_none_when_unreachable(tmp_path):
    g = _build_fixture_graph(tmp_path)
    assert g.shortest_path(5, 1) is None


def test_shortest_path_empty_when_same_map(tmp_path):
    g = _build_fixture_graph(tmp_path)
    assert g.shortest_path(1, 1) == []


# ---------------------------------------------------------------------------
# Fail-loud cases
# ---------------------------------------------------------------------------


def test_warp_to_unknown_map_fails_loud(tmp_path):
    paths = _write_corpus(
        tmp_path,
        map_events={1: [_warp_event(1, 0, 0, 0, 999, 0, 0)]},
        infos={1: "Lonely Map"},
    )
    with pytest.raises(ValueError, match="map 1 event 1.*999"):
        build_world_graph(**paths)


def test_connections_row_naming_unknown_map_fails_loud(tmp_path):
    paths = _write_corpus(
        tmp_path,
        map_events={1: []},
        infos={1: "Solo"},
        connections=[[1, "E", 0, 999, "W", 0]],
    )
    with pytest.raises(ValueError, match="999"):
        build_world_graph(**paths)


def test_seam_warp_naming_unknown_map_fails_loud(tmp_path):
    paths = _write_corpus(
        tmp_path,
        map_events={1: []},
        infos={1: "Solo"},
        seams=[
            {
                "id": "bad_seam",
                "map_a": 1,
                "map_b": 999,
                "cells_a": [[0, 0]],
                "cells_b": [[0, 0]],
                "direction_a": "up",
                "direction_b": "down",
            }
        ],
    )
    with pytest.raises(ValueError, match="999"):
        build_world_graph(**paths)


# ---------------------------------------------------------------------------
# Real-corpus integration (stable structural facts only)
# ---------------------------------------------------------------------------

pytestmark_corpus = pytest.mark.skipif(
    not (DEFAULT_MAPS_DIR / "Map019.json").is_file()
    or not DEFAULT_MAP_INFOS_JSON.is_file()
    or not DEFAULT_CONNECTIONS_JSON.is_file(),
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)


@pytestmark_corpus
def test_real_corpus_builds_without_raising():
    build_world_graph()


@pytestmark_corpus
def test_real_corpus_passage_cave_connects_only_to_map_31():
    g = build_world_graph()
    assert g.neighbors(19) == [31]
    assert {e.src_map for e in g.edges_to(19)} == {31}


@pytestmark_corpus
def test_real_corpus_kevlar_route2_is_a_real_connection_both_directions():
    """31<->35 became a real scrolling connection 2026-10-06 (shared tileset;
    the kevlar_town_route_02 arrow-warp seam was retired)."""
    g = build_world_graph()
    fwd = [e for e in g.edges_from(31) if e.kind == "connection" and e.dst_map == 35]
    back = [e for e in g.edges_from(35) if e.kind == "connection" and e.dst_map == 31]
    assert len(fwd) >= 1
    assert len(back) >= 1
    assert not [e for e in g.edges_from(31) if e.kind == "seam_warp"]
