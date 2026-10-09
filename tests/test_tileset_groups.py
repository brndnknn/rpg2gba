"""Tests for map_set.tileset_groups (shared synthetic tileset per connected component)."""

from __future__ import annotations

import pytest

from rpg2gba.tileset_converter.connections import parse_connections
from rpg2gba.tileset_converter.map_set import (
    remapped_connections,
    synth_tileset_id,
    tileset_groups,
)

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


def test_mixed_real_tilesets_stay_split_as_remapped_connection() -> None:
    got = tileset_groups(ROWS, [31, 35, 40], frozenset(), REAL)
    assert got[31] == got[35] == synth_tileset_id(31)
    assert got[40] == synth_tileset_id(40)
    remapped = remapped_connections(ROWS, [31, 35, 40], frozenset(), REAL)
    assert [(r.map_a, r.map_b) for r in remapped] == [(35, 40)]


def test_same_tileset_connection_is_not_remapped() -> None:
    assert remapped_connections(ROWS, [31, 35], frozenset(), REAL) == []


def test_suppressed_mixed_pair_is_not_remapped() -> None:
    assert remapped_connections(
        ROWS, [31, 35, 40], frozenset({frozenset({35, 40})}), REAL
    ) == []


def test_mixed_transitive_chain_splits_only_at_the_tileset_change() -> None:
    # 5 -(same ts)- 9 -(different ts)- 2 -(same ts as 2)- 7
    rows = parse_connections([
        [5, "N", 0, 9, "S", 0], [9, "E", 0, 2, "W", 0], [2, "N", 0, 7, "S", 0],
    ])
    real = {5: 1, 9: 1, 2: 3, 7: 3}
    got = tileset_groups(rows, [2, 5, 7, 9], frozenset(), real)
    assert got[5] == got[9] == synth_tileset_id(5)
    assert got[2] == got[7] == synth_tileset_id(2)
    assert [(r.map_a, r.map_b) for r in remapped_connections(rows, [2, 5, 7, 9], frozenset(), real)] == [(9, 2)]
