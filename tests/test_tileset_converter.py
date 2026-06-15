"""Phase 5 acceptance scaffold — the tests the assignment must make pass.

These are written against the stub APIs in `rpg2gba.tileset_converter` and are
SKIPPED until each section is implemented (the stubs `raise NotImplementedError`).
As you implement a section, delete its `pytest.skip(...)` line and flesh the test
out into a real round-trip / golden / edge-case check (CLAUDE.md §8). They encode
the acceptance checklists from PHASE5_PLAN.md so the target is concrete.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from rpg2gba.tileset_converter import layout as layout_mod
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter.layout import TileGrid
from rpg2gba.tileset_converter.tile_map import (
    METATILE_ID_MASK,
    Metatile,
    TilesetChoice,
    load_tile_map,
    normalize_tile_id,
)

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

def _passages(blocked_ranges: list[tuple[int, int]], n: int = 600) -> list[int]:
    """A passages array (length n) with the given [lo,hi) ranges set blocked (15)."""
    arr = [0] * n
    for lo, hi in blocked_ranges:
        for i in range(lo, hi):
            arr[i] = 15
    return arr


def _write_slice_table(tmp_path: Path) -> tuple[Path, Path]:
    """Self-contained tileset_map.json + passages oracle for the two slice tilesets."""
    table = {
        "tilesets": {
            "19": {"primary": "gTileset_Building", "secondary": "gTileset_BrendansMaysHouse"},
            "22": {"primary": "gTileset_General", "secondary": "gTileset_Petalburg"},
        },
        "buckets": {
            "19": {"passable": 513, "blocked": 622, "void": 1},
            "22": {"passable": 1, "blocked": 468, "void": 468},
        },
        # one explicit override at autotile-2 base 96 (tests normalization + precedence)
        "tiles": {"19": {"96": {"metatile": 50, "collision": 0, "elevation": 3}}, "22": {}},
        "stacks": {},
    }
    oracle = {  # autotile 1 (ids 48..95) blocked; everything else passable
        "19": {"passages": _passages([(48, 96)]), "priorities": _passages([])},
        "22": {"passages": _passages([(48, 96)]), "priorities": _passages([])},
    }
    tpath, opath = tmp_path / "tileset_map.json", tmp_path / "tilesets.json"
    tpath.write_text(json.dumps(table), encoding="utf-8")
    opath.write_text(json.dumps(oracle), encoding="utf-8")
    return tpath, opath


def test_tile_map_loads_and_explicit_precedence(tmp_path: Path) -> None:
    tpath, opath = _write_slice_table(tmp_path)
    tm = load_tile_map(tpath, opath)
    assert tm.tileset_for(19) == TilesetChoice("gTileset_Building", "gTileset_BrendansMaysHouse")
    # explicit entry wins; autotile variant 100 normalizes to base 96
    assert normalize_tile_id(100) == 96
    assert tm.lookup(19, 100) == Metatile(50, 0, 3)
    assert tm.lookup(19, 96) == Metatile(50, 0, 3)
    assert tm.void(22) == Metatile(468, 1, 0)


def test_tile_map_bucket_fallback(tmp_path: Path) -> None:
    tpath, opath = _write_slice_table(tmp_path)
    tm = load_tile_map(tpath, opath)
    # autotile 1 variant (passage 15, no explicit entry) -> blocked bucket
    assert tm.lookup(19, 52) == Metatile(622, 1, 0)
    # passable tiles (passage 0) -> passable bucket
    assert tm.lookup(19, 400) == Metatile(513, 0, 3)
    assert tm.lookup(22, 200) == Metatile(1, 0, 3)
    # blocked autotile in the town -> blocked bucket
    assert tm.lookup(22, 60) == Metatile(468, 1, 0)


def test_tile_map_unmapped_fails_loud(tmp_path: Path) -> None:
    """lookup() on an unmapped tileset raises with the ids; tile_id 0 is rejected."""
    tpath, opath = _write_slice_table(tmp_path)
    tm = load_tile_map(tpath, opath)
    with pytest.raises(KeyError) as exc:
        tm.lookup(99, 384)
    assert "99" in str(exc.value) and "384" in str(exc.value)
    with pytest.raises(ValueError):
        tm.lookup(19, 0)


def test_tile_map_validate_rejects(tmp_path: Path) -> None:
    base = {
        "tilesets": {
            "19": {"primary": "gTileset_Building", "secondary": "gTileset_BrendansMaysHouse"},
        },
        "buckets": {"19": {"passable": 1, "blocked": 2, "void": 3}},
        "tiles": {"19": {}},
    }

    def _load(mutate) -> None:
        d = json.loads(json.dumps(base))
        mutate(d)
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        load_tile_map(p, None)

    with pytest.raises(ValueError):  # metatile beyond the 10-bit field
        _load(lambda d: d["tiles"]["19"].update({"384": {"metatile": 0x400}}))
    with pytest.raises(ValueError):  # bad collision
        _load(lambda d: d["tiles"]["19"].update({"384": {"metatile": 5, "collision": 4}}))
    with pytest.raises(ValueError):  # tiles references an unknown tileset
        _load(lambda d: d["tiles"].update({"77": {}}))
    with pytest.raises(ValueError):  # bucket missing a role
        _load(lambda d: d["buckets"]["19"].pop("void"))
    with pytest.raises(ValueError):  # missing secondary
        _load(lambda d: d["tilesets"]["19"].pop("secondary"))


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


# --- 5.5 move_routes ---------------------------------------------------------

def test_move_route_census_parses() -> None:
    """Census tool reports per-map event count and target-class breakdown (player/self/other)."""
    pytest.skip("Phase 5 §5.5 — not yet implemented")


def test_move_route_player_only_translation() -> None:
    """A player-only 209 route translates to applymovement(OBJ_EVENT_ID_PLAYER, …)
    and compile-gates clean."""
    pytest.skip("Phase 5 §5.5 — not yet implemented")


def test_move_route_timing_conversion() -> None:
    """A wait command of N frames at RMXP 40fps converts to the nearest GBA 60fps delay value."""
    pytest.skip("Phase 5 §5.5 — not yet implemented")


def test_move_route_injection_idempotent() -> None:
    """Re-running the move-route post-pass on already-processed .pory output is idempotent."""
    pytest.skip("Phase 5 §5.5 — not yet implemented")


# --- 5.6 reachability --------------------------------------------------------

def test_reachability_blocked_exit_is_defect() -> None:
    """BFS on a synthetic map where an exit cell is walled off classifies it as a defect."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")


def test_reachability_ledge_one_way() -> None:
    """A ledge edge allows forward traversal (approach→landing) but the reverse
    direction is unreachable."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")


def test_reachability_water_is_hm_gated() -> None:
    """An exit reachable only through water tiles is classified HM-gated, not a defect."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")


def test_reachability_puzzle_gated_routes_to_wiki_review() -> None:
    """An exit passable in optimistic mode but not pessimistic is flagged for
    wiki review, not auto-failed."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")


def test_passages_oracle_diff_reports_disagreements() -> None:
    """Passages oracle diff reports every cell where emitted GBA collision
    disagrees with the RMXP source passages value."""
    pytest.skip("Phase 5 §5.6 — not yet implemented")
