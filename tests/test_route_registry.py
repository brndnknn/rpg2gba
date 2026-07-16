"""Tests for the custom-route dedup registry (route_bytecode.RouteRegistry)."""
from __future__ import annotations

import pytest

from rpg2gba.tileset_converter.route_bytecode import (
    MAX_ROUTE_ID,
    RouteRegistry,
)


def test_ids_are_1_based_and_sequential() -> None:
    reg = RouteRegistry()
    assert reg.intern([102, 0x02, 0x03, 0x00]) == 1
    assert reg.intern([102, 0x01, 0x04, 0x00]) == 2


def test_identical_bytecode_dedups_to_same_id() -> None:
    reg = RouteRegistry()
    first = reg.intern([102, 0x02, 0x03, 0x00])
    again = reg.intern([102, 0x02, 0x03, 0x00])
    assert first == again == 1
    assert len(reg) == 1


def test_list_and_tuple_inputs_dedup_together() -> None:
    reg = RouteRegistry()
    a = reg.intern([102, 0x02, 0x00])
    b = reg.intern((102, 0x02, 0x00))
    assert a == b
    assert len(reg) == 1


def test_routes_in_id_order() -> None:
    reg = RouteRegistry()
    reg.intern([1, 2, 0])
    reg.intern([3, 4, 0])
    reg.intern([1, 2, 0])  # dup
    routes = reg.routes()
    assert routes == [(1, 2, 0), (3, 4, 0)]
    # 0-based index i carries route id i+1
    assert reg.intern(routes[0]) == 1
    assert reg.intern(routes[1]) == 2


def test_overflow_past_u8_fails_loud() -> None:
    reg = RouteRegistry()
    for i in range(MAX_ROUTE_ID):
        reg.intern([i % 200, 0x01, 0x00, i])  # distinct byte arrays
    assert len(reg) == MAX_ROUTE_ID
    with pytest.raises(ValueError, match="registry overflow"):
        reg.intern([0x02, 0x02, 0x02, 0xFF, 0xEE])
