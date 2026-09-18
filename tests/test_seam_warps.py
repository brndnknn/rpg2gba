"""Tests for `rpg2gba.tileset_converter.seam_warps` (reference/seam_warps.json,
CLAUDE.md §4.3): the arrow-warp substitution for a map CONNECTION whose two
maps can't share a tileset.

Covers: schema loading/validation, the derived behavior-cells/warp-pairs/
suppressed-pairs shapes, the `metadata_wiring` direct-pair reciprocal warp
resolution (no redundant arrival minted), and `connections.py`'s suppression
of the superseded connection row (including its fail-loud contradiction
check).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter import connections as conn
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter import metadata_wiring as mw
from rpg2gba.tileset_converter import seam_warps as sw

# ---------------------------------------------------------------------------
# load_seam_warps / schema validation
# ---------------------------------------------------------------------------

_ONE_SEAM = {
    "seams": [
        {
            "id": "a_b",
            "map_a": 31,
            "map_b": 35,
            "cells_a": [[31, 0], [32, 0]],
            "cells_b": [[20, 56], [21, 56]],
            "direction_a": "up",
            "direction_b": "down",
        }
    ]
}


def _write(tmp_path: Path, obj: dict) -> Path:
    p = tmp_path / "seam_warps.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_load_seam_warps_parses_one_seam(tmp_path: Path) -> None:
    path = _write(tmp_path, _ONE_SEAM)
    seams = sw.load_seam_warps(path)
    assert len(seams) == 1
    s = seams[0]
    assert s.seam_id == "a_b"
    assert s.map_a == 31 and s.map_b == 35
    assert s.cells_a == ((31, 0), (32, 0))
    assert s.cells_b == ((20, 56), (21, 56))
    assert s.direction_a == "up" and s.direction_b == "down"
    assert s.pair_key == frozenset({31, 35})


def test_load_seam_warps_missing_field_fails_loud(tmp_path: Path) -> None:
    obj = {"seams": [{"id": "a_b", "map_a": 31, "map_b": 35, "cells_a": [[0, 0]]}]}
    path = _write(tmp_path, obj)
    with pytest.raises(ValueError, match="cells_b"):
        sw.load_seam_warps(path)


def test_load_seam_warps_same_map_fails_loud(tmp_path: Path) -> None:
    obj = {
        "seams": [
            {
                "id": "x", "map_a": 31, "map_b": 31,
                "cells_a": [[0, 0]], "cells_b": [[1, 1]],
                "direction_a": "up", "direction_b": "down",
            }
        ]
    }
    path = _write(tmp_path, obj)
    with pytest.raises(ValueError, match="map_a == map_b"):
        sw.load_seam_warps(path)


def test_load_seam_warps_mismatched_cell_counts_fails_loud(tmp_path: Path) -> None:
    obj = {
        "seams": [
            {
                "id": "x", "map_a": 31, "map_b": 35,
                "cells_a": [[0, 0], [1, 0]], "cells_b": [[0, 1]],
                "direction_a": "up", "direction_b": "down",
            }
        ]
    }
    path = _write(tmp_path, obj)
    with pytest.raises(ValueError, match="equal-length"):
        sw.load_seam_warps(path)


def test_load_seam_warps_unknown_direction_fails_loud(tmp_path: Path) -> None:
    obj = {
        "seams": [
            {
                "id": "x", "map_a": 31, "map_b": 35,
                "cells_a": [[0, 0]], "cells_b": [[0, 1]],
                "direction_a": "north", "direction_b": "down",
            }
        ]
    }
    path = _write(tmp_path, obj)
    with pytest.raises(ValueError, match="direction_a"):
        sw.load_seam_warps(path)


def test_load_seam_warps_duplicate_pair_fails_loud(tmp_path: Path) -> None:
    obj = {
        "seams": [
            {
                "id": "a", "map_a": 31, "map_b": 35,
                "cells_a": [[0, 0]], "cells_b": [[0, 1]],
                "direction_a": "up", "direction_b": "down",
            },
            {
                "id": "b", "map_a": 35, "map_b": 31,
                "cells_a": [[0, 2]], "cells_b": [[0, 3]],
                "direction_a": "down", "direction_b": "up",
            },
        ]
    }
    path = _write(tmp_path, obj)
    with pytest.raises(ValueError, match="already declared"):
        sw.load_seam_warps(path)


def test_seams_for_slice_frontier_rule(tmp_path: Path) -> None:
    path = _write(tmp_path, _ONE_SEAM)
    seams = sw.load_seam_warps(path)
    assert sw.seams_for_slice(seams, {31, 35}) == seams
    assert sw.seams_for_slice(seams, {31}) == []  # map 35 unstaged


def test_behavior_cells_for(tmp_path: Path) -> None:
    seams = sw.load_seam_warps(_write(tmp_path, _ONE_SEAM))
    cells = sw.behavior_cells_for(seams)
    assert cells[31] == {(31, 0): "arrow_warp_up", (32, 0): "arrow_warp_up"}
    assert cells[35] == {(20, 56): "arrow_warp_down", (21, 56): "arrow_warp_down"}


def test_warp_pairs_for(tmp_path: Path) -> None:
    seams = sw.load_seam_warps(_write(tmp_path, _ONE_SEAM))
    pairs = sw.warp_pairs_for(seams)
    assert pairs == [(31, 31, 0, 35, 20, 56), (31, 32, 0, 35, 21, 56)]


def test_suppressed_pairs(tmp_path: Path) -> None:
    seams = sw.load_seam_warps(_write(tmp_path, _ONE_SEAM))
    assert sw.suppressed_pairs(seams) == frozenset({frozenset({31, 35})})


# ---------------------------------------------------------------------------
# metadata_wiring: direct_pair reciprocal warp resolution
# ---------------------------------------------------------------------------


def _mint(map_ids: dict[int, str]) -> mc.MapConstantRegistry:
    reg = mc.MapConstantRegistry(Path("x"))
    for uid, name in map_ids.items():
        reg.mint(uid, name)
    return reg


def test_direct_pair_warps_resolve_to_each_others_index_no_arrival() -> None:
    """Two direct_pair WarpSpecs (a seam's reciprocal cells) pair to each
    other's OWN warp_event index — no extra 'arrival' warp_event is minted on
    either map, unlike an ordinary code-201 transfer."""
    reg = _mint({31: "Kevlar Town", 35: "Route 2"})
    warp_lists = {
        31: [mw.WarpSpec(src_x=31, src_y=0, dest_uid=35, dest_x=20, dest_y=56, direct_pair=True)],
        35: [mw.WarpSpec(src_x=20, src_y=56, dest_uid=31, dest_x=31, dest_y=0, direct_pair=True)],
    }
    resolved = mw._resolve_all_warp_events(warp_lists, reg, {31: {}, 35: {}})

    assert len(resolved[31]) == 1  # no arrival minted
    assert len(resolved[35]) == 1
    assert (resolved[31][0].x, resolved[31][0].y) == (31, 0)
    assert (resolved[35][0].x, resolved[35][0].y) == (20, 56)
    assert resolved[31][0].dest_map == "MAP_ROUTE_2"
    assert resolved[35][0].dest_map == "MAP_KEVLAR_TOWN"
    # Each points at the other's own (only) index.
    assert resolved[31][0].dest_warp_id == 0
    assert resolved[35][0].dest_warp_id == 0


def test_direct_pair_multi_cell_seam_pairs_correctly() -> None:
    """Two seam cell-pairs on the same seam ([31,0]<->[20,56] and
    [32,0]<->[21,56]) each pair to their OWN reciprocal, not the other pair's."""
    reg = _mint({31: "Kevlar Town", 35: "Route 2"})
    warp_lists = {
        31: [
            mw.WarpSpec(src_x=31, src_y=0, dest_uid=35, dest_x=20, dest_y=56, direct_pair=True),
            mw.WarpSpec(src_x=32, src_y=0, dest_uid=35, dest_x=21, dest_y=56, direct_pair=True),
        ],
        35: [
            mw.WarpSpec(src_x=20, src_y=56, dest_uid=31, dest_x=31, dest_y=0, direct_pair=True),
            mw.WarpSpec(src_x=21, src_y=56, dest_uid=31, dest_x=32, dest_y=0, direct_pair=True),
        ],
    }
    resolved = mw._resolve_all_warp_events(warp_lists, reg, {31: {}, 35: {}})

    assert len(resolved[31]) == 2 and len(resolved[35]) == 2
    assert resolved[31][0].dest_warp_id == 0  # (31,0) <-> (20,56), index 0 on both
    assert resolved[31][1].dest_warp_id == 1  # (32,0) <-> (21,56), index 1 on both
    assert resolved[35][0].dest_warp_id == 0
    assert resolved[35][1].dest_warp_id == 1


def test_direct_pair_with_no_reciprocal_fails_loud() -> None:
    """A direct_pair spec with no matching reciprocal on the destination map is
    a caller bug — fails loud rather than silently falling back to arrival
    pairing (which would mint a redundant warp_event for an arrow-warp cell)."""
    reg = _mint({31: "Kevlar Town", 35: "Route 2"})
    warp_lists = {
        31: [mw.WarpSpec(src_x=31, src_y=0, dest_uid=35, dest_x=20, dest_y=56, direct_pair=True)],
        35: [],  # no reciprocal
    }
    with pytest.raises(ValueError, match="no reciprocal"):
        mw._resolve_all_warp_events(warp_lists, reg, {31: {}, 35: {}})


def test_build_slice_maps_extra_warps_end_to_end(tmp_path: Path) -> None:
    """`extra_warps` threaded into build_slice_maps produces real warp_events on
    both maps with correct reciprocal dest_warp_id, and the seam cells are
    EXCLUDED from the returned src_coords override set (they go through
    behavior_overrides, not warp_overrides — see build_slice_maps' docstring)."""
    reg = _mint({31: "Kevlar Town", 35: "Route 2"})
    map_31 = {"map_id": 31, "width": 50, "height": 50, "events": []}
    map_35 = {"map_id": 35, "width": 42, "height": 57, "events": []}
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    (maps_dir / "Map031.json").write_text(json.dumps(map_31), encoding="utf-8")
    (maps_dir / "Map035.json").write_text(json.dumps(map_35), encoding="utf-8")
    metadata_path = tmp_path / "map_metadata.json"
    metadata_path.write_text(json.dumps({"maps": {}}), encoding="utf-8")
    out_dir = tmp_path / "out"

    extra_warps = {
        31: [mw.WarpSpec(src_x=31, src_y=0, dest_uid=35, dest_x=20, dest_y=56, direct_pair=True)],
        35: [mw.WarpSpec(src_x=20, src_y=56, dest_uid=31, dest_x=31, dest_y=0, direct_pair=True)],
    }
    overrides = mw.build_slice_maps(
        [31, 35], maps_dir=maps_dir, registry=reg, metadata_path=metadata_path,
        out_dir=out_dir, dispatcher_dir=tmp_path / "disp",
        stripped_event_ids={}, extra_warps=extra_warps,
    )

    # No real code-201 warps on either map: src_coords must be empty.
    assert overrides[31] == set()
    assert overrides[35] == set()

    map31_json = json.loads((out_dir / "KevlarTown" / "map.json").read_text())
    map35_json = json.loads((out_dir / "Route2" / "map.json").read_text())
    assert len(map31_json["warp_events"]) == 1
    assert len(map35_json["warp_events"]) == 1
    w31, w35 = map31_json["warp_events"][0], map35_json["warp_events"][0]
    assert (w31["x"], w31["y"]) == (31, 0)
    assert (w35["x"], w35["y"]) == (20, 56)
    assert w31["dest_map"] == "MAP_ROUTE_2" and w35["dest_map"] == "MAP_KEVLAR_TOWN"
    assert w31["dest_warp_id"] == "0" and w35["dest_warp_id"] == "0"


# ---------------------------------------------------------------------------
# connections.py: seam suppression
# ---------------------------------------------------------------------------


def test_build_slice_connections_suppresses_declared_seam(tmp_path: Path) -> None:
    """A connections.json row whose map pair is in `suppress_pairs` is omitted
    from the result entirely (both directions) — replaced by the arrow warp."""
    rows_json = [[31, "N", 11, 35, "S", 0]]
    cpath = tmp_path / "connections.json"
    cpath.write_text(json.dumps(rows_json), encoding="utf-8")
    resolve = {31: "MAP_KEVLAR_TOWN", 35: "MAP_ROUTE_2"}.get

    result = conn.build_slice_connections(
        cpath, [31, 35], lambda uid: resolve(uid), frozenset({frozenset({31, 35})}),
    )
    assert result == {}


def test_build_slice_connections_keeps_unsuppressed_rows(tmp_path: Path) -> None:
    """A row NOT in suppress_pairs still emits normally."""
    rows_json = [[31, "N", 11, 35, "S", 0]]
    cpath = tmp_path / "connections.json"
    cpath.write_text(json.dumps(rows_json), encoding="utf-8")
    resolve = {31: "MAP_KEVLAR_TOWN", 35: "MAP_ROUTE_2"}.get

    result = conn.build_slice_connections(cpath, [31, 35], lambda uid: resolve(uid))
    assert 31 in result and 35 in result


def test_build_connections_contradictory_suppression_fails_loud(tmp_path: Path) -> None:
    """A suppress_pairs entry naming a map pair with NO connections.json row at
    all is a contradictory declaration between the two source-of-truth files
    — fails loud rather than silently doing nothing."""
    rows = conn.parse_connections([[31, "N", 11, 35, "S", 0]])
    resolve = {31: "MAP_KEVLAR_TOWN", 35: "MAP_ROUTE_2"}.get

    with pytest.raises(ValueError, match="nothing to suppress"):
        conn.build_connections(
            rows, {31, 35}, lambda uid: resolve(uid),
            frozenset({frozenset({31, 99})}),
        )
