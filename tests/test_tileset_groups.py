"""Tests for map_set.tileset_groups (shared synthetic tileset per connected component)."""

from __future__ import annotations

import pytest

from rpg2gba.tileset_converter.connections import parse_connections
from rpg2gba.tileset_converter.map_set import synth_tileset_id, tileset_groups

ROWS = parse_connections([[31, "N", 11, 35, "S", 0], [35, "N", 0, 40, "S", 0]])
REAL = {31: 22, 35: 22, 40: 23, 99: 5}


def test_connected_pair_shares_min_id() -> None:
    got = tileset_groups(ROWS, [31, 35], frozenset(), REAL)
    assert got == {31: synth_tileset_id(31), 35: synth_tileset_id(31)}


def test_isolated_map_keeps_own_id() -> None:
    got = tileset_groups(ROWS, [31, 35, 99], frozenset(), REAL)
    assert got[99] == synth_tileset_id(99)
    assert got[35] == synth_tileset_id(31)


def test_frontier_rule_out_of_slice_endpoint_does_not_join() -> None:
    # 40 not in the slice: the 35<->40 row is omitted, so no mixed-tileset error.
    got = tileset_groups(ROWS, [35, 31], frozenset(), REAL)
    assert set(got.values()) == {synth_tileset_id(31)}
    assert 40 not in got


def test_suppressed_pair_stays_split_even_with_mixed_tilesets() -> None:
    got = tileset_groups(
        ROWS, [31, 35, 40], frozenset({frozenset({35, 40})}), REAL
    )
    assert got[40] == synth_tileset_id(40)
    assert got[31] == got[35] == synth_tileset_id(31)


def test_transitive_component_uses_min_of_component() -> None:
    rows = parse_connections([[5, "N", 0, 9, "S", 0], [9, "E", 0, 2, "W", 0]])
    real = {2: 1, 5: 1, 9: 1}
    got = tileset_groups(rows, [9, 5, 2], frozenset(), real)
    assert set(got.values()) == {synth_tileset_id(2)}


def test_mixed_real_tilesets_fail_loud() -> None:
    with pytest.raises(ValueError) as exc:
        tileset_groups(ROWS, [31, 35, 40], frozenset(), REAL)
    msg = str(exc.value)
    assert "map 35 (RMXP tileset 22)" in msg
    assert "map 40 (RMXP tileset 23)" in msg
    assert "seam_warps.json" in msg
    assert "#27" in msg
