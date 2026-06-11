"""Phase 5 acceptance scaffold — the tests the assignment must make pass.

These are written against the stub APIs in `rpg2gba.tileset_converter` and are
SKIPPED until each section is implemented (the stubs `raise NotImplementedError`).
As you implement a section, delete its `pytest.skip(...)` line and flesh the test
out into a real round-trip / golden / edge-case check (CLAUDE.md §8). They encode
the acceptance checklists from PHASE5_PLAN.md so the target is concrete.
"""
from __future__ import annotations

import struct

import pytest

from rpg2gba.tileset_converter import layout as layout_mod
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter.layout import TileGrid
from rpg2gba.tileset_converter.tile_map import METATILE_ID_MASK, Metatile

_TODO = "Phase 5: implement this section, then un-skip and flesh out the test"


# --- helpers that are real already (no skip needed) ---------------------------

def test_metatile_block_packing() -> None:
    """Metatile.to_block packs metatile|collision<<10|elevation<<12 (no skip — pure)."""
    block = Metatile(metatile_id=0x123, collision=2, elevation=3).to_block()
    assert block & METATILE_ID_MASK == 0x123
    assert (block >> 10) & 0x3 == 2
    assert (block >> 12) & 0xF == 3


def test_tilegrid_indexing() -> None:
    """TileGrid.tile_at uses the Phase 3 flat layout index (no skip — pure)."""
    # 2x2x2: layer 0 = [1,2,3,4], layer 1 = [5,6,7,8]
    grid = TileGrid(xsize=2, ysize=2, zsize=2, data=[1, 2, 3, 4, 5, 6, 7, 8])
    assert grid.tile_at(0, 0, 0) == 1
    assert grid.tile_at(1, 1, 0) == 4
    assert grid.tile_at(0, 0, 1) == 5
    assert grid.column(1, 0) == [2, 6]


def test_blockdata_round_trip_reader() -> None:
    """read_blockdata is the inverse of the LE u16 packing (no skip — pure)."""
    blocks = [0x0001, 0x0FFF, 0x3C04]
    raw = struct.pack(f"<{len(blocks)}H", *blocks)
    assert layout_mod.read_blockdata.__doc__  # exists
    # round-trip via a temp file is exercised in test_layout_round_trip below.
    assert list(struct.unpack(f"<{len(raw) // 2}H", raw)) == blocks


# --- 5.1 tile_map ------------------------------------------------------------

def test_tile_map_loads_and_round_trips() -> None:
    pytest.skip(_TODO)


def test_tile_map_unmapped_fails_loud() -> None:
    """lookup() on an unmapped (tileset_id, tile_id) raises with the ids."""
    pytest.skip(_TODO)


# --- 5.2 layout --------------------------------------------------------------

def test_layout_round_trip() -> None:
    """convert_layout on a 2x2 synthetic map -> map.bin of width*height*2 bytes,
    re-readable to the same metatile ids."""
    pytest.skip(_TODO)


def test_layout_idempotent() -> None:
    """Re-running convert_layout + write_blockdata yields byte-identical .bin."""
    pytest.skip(_TODO)


# --- map_constants -----------------------------------------------------------

def test_map_constants_idempotent_mint() -> None:
    """mint(id) returns the same constants across runs (persisted)."""
    pytest.skip(_TODO)


def test_map_constants_resolve_placeholder() -> None:
    """A MAP_URANIUM_<N> for a real map resolves; an unknown N fails loud."""
    pytest.skip(_TODO)


def test_alias_const_format_is_valid_identifier() -> None:
    """The Q2 alias spelling yields a valid C identifier (no skip — pure)."""
    name = mc.ALIAS_CONST_FMT.format(n=42)
    assert name.replace("_", "").isalnum() and name[0].isalpha()
    assert name == "MAP_URANIUM_42"


# --- 5.3 metadata_wiring -----------------------------------------------------

def test_object_events_placed_at_coords() -> None:
    """Each Uranium event -> one object_event at its (x, y) with a resolved label."""
    pytest.skip(_TODO)


def test_page_dispatcher_reflects_conditions() -> None:
    """A 2-page event's dispatcher gotos page 2 under its condition flag, else page 1."""
    pytest.skip(_TODO)


# --- 5.4 connections ---------------------------------------------------------

def test_connections_bidirectional() -> None:
    """A->B up implies B->A down with negated offset."""
    pytest.skip(_TODO)


def test_connections_no_dangling_map() -> None:
    """No emitted connection references a non-existent MAP_*."""
    pytest.skip(_TODO)
