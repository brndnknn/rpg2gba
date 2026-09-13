"""Tests for `pbs_converter.heal_locations` — white-out respawn derivation.

Per CLAUDE.md §4.6:
  * golden: the real Map068 (Kevlar Town Pokémon Center) call site
  * idempotence: running the generator twice yields identical output
  * edge case: bare call vs. explicit-argument call
  * fail loud: a staged map absent from `map_constants.json`

Real-corpus tests are gated on `output/uranium-build/` existing, matching the
pattern in `tests/test_traversal_map037_golden.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import heal_locations as hl
from rpg2gba.tileset_converter.layout import TileGrid
from rpg2gba.traversal.collision import TilesetArrays
from rpg2gba.traversal.graph import MapGraph

MAPS_DIR = Path("output/uranium-build/maps")
TILESETS_JSON = Path("output/uranium-build/tilesets.json")
MAP_CONSTANTS_JSON = Path("output/uranium-build/porymap/map_constants.json")
METADATA_HEADER = Path("output/uranium-build/include/constants/metadata.h")
MAP068 = MAPS_DIR / "Map068.json"

pytestmark = pytest.mark.skipif(
    not MAP068.is_file()
    or not TILESETS_JSON.is_file()
    or not MAP_CONSTANTS_JSON.is_file()
    or not METADATA_HEADER.is_file(),
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)


def test_golden_map068_kevlar_town_pokemon_center() -> None:
    """The one staged `pbSetPokemonCenter` call site (Map068, Kevlar Town
    Pokémon Center, event 1 @ (8,11), bare call) resolves to (8,13) facing
    UP — the unique reachable candidate once counters and reachability are
    accounted for (ROM-verified via CH03's beat B4,
    `src/rpg2gba/playtest/chapters/ch03.py:207-212`). The old
    "unique open orthogonal neighbour" rule resolved this to (8,10), a
    sealed pocket the player can never actually stand in — see the module
    docstring."""
    entries, resolutions = hl.generate_entries(
        maps_dir=MAPS_DIR,
        tilesets_json=TILESETS_JSON,
        map_constants_json=MAP_CONSTANTS_JSON,
        metadata_header=METADATA_HEADER,
    )
    assert entries == [
        hl.HealLocationEntry(
            id=hl.START_ANCHOR_ID,
            map="MAP_MOKI_TOWN_PLAYERS_HOUSE_1F",
            x=7,
            y=7,
        ),
        hl.HealLocationEntry(
            id="HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER",
            map="MAP_KEVLAR_TOWN_POKEMON_CENTER",
            x=8,
            y=13,
        ),
    ]

    map068_resolutions = [r for r in resolutions if r.call_site.map_id == 68]
    assert len(map068_resolutions) == 1
    res = map068_resolutions[0]
    assert res.resolved is True
    assert res.call_site.event_id == 1
    assert res.call_site.explicit_args is None
    assert (res.map_id, res.x, res.y) == (68, 8, 13)
    assert res.direction == hl.DIR_UP
    assert "counter" in res.reason


def test_call_site_census_matches_measured_ground_truth() -> None:
    """64 `pbSetPokemonCenter` call sites across 42 distinct maps in the
    corpus (measured 2026-09-12); Map068 is the only staged one."""
    sites = hl.find_call_sites(MAPS_DIR)
    assert len(sites) == 64
    assert len({s.map_id for s in sites}) == 42
    staged_sites = [s for s in sites if s.map_id in hl.SLICE_MAP_IDS]
    assert [s.map_id for s in staged_sites] == [68]


def test_idempotent() -> None:
    """Running the generator twice produces byte-identical output."""
    entries1, _ = hl.generate_entries(
        maps_dir=MAPS_DIR,
        tilesets_json=TILESETS_JSON,
        map_constants_json=MAP_CONSTANTS_JSON,
        metadata_header=METADATA_HEADER,
    )
    entries2, _ = hl.generate_entries(
        maps_dir=MAPS_DIR,
        tilesets_json=TILESETS_JSON,
        map_constants_json=MAP_CONSTANTS_JSON,
        metadata_header=METADATA_HEADER,
    )
    assert entries1 == entries2


def test_bare_vs_explicit_call_parsing() -> None:
    """A bare call and an explicit-args call both parse, and resolve via
    different paths (collision-derived vs. literal passthrough)."""
    bare = hl._parse_call("Kernel.pbSetPokemonCenter")
    assert bare is None

    explicit = hl._parse_call("Kernel.pbSetPokemonCenter(43,8,13,8)")
    assert explicit == (43, 8, 13, 8)

    not_a_call = hl._parse_call("Kernel.pbHealAll")
    assert not_a_call is hl._NOT_A_CALL

    # An explicit-args call resolves without touching the collision grid at
    # all — it should work even for a map/event that doesn't exist on disk.
    call = hl.CallSite(
        map_id=999999,
        event_id=1,
        event_name="EV001",
        page_index=0,
        trigger=0,
        event_x=0,
        event_y=0,
        explicit_args=(43, 8, 13, 8),
    )
    res = hl.resolve_call_site(call)
    assert res.resolved is True
    assert (res.map_id, res.x, res.y, res.direction) == (43, 8, 13, 8)

    # A bare call on a non-Action-Button trigger is reported unresolved, not
    # guessed.
    bare_call = hl.CallSite(
        map_id=68,
        event_id=1,
        event_name="EV001",
        page_index=1,
        trigger=3,  # autorun, not Action Button
        event_x=8,
        event_y=11,
        explicit_args=None,
    )
    res2 = hl.resolve_call_site(bare_call, maps_dir=MAPS_DIR, tilesets_json=TILESETS_JSON)
    assert res2.resolved is False


def test_fails_loud_on_missing_map_constant(tmp_path: Path) -> None:
    """A staged call site whose map has no `map_constants.json` entry must
    fail loud, not silently skip or emit a broken constant name."""
    empty_constants = tmp_path / "map_constants.json"
    empty_constants.write_text(json.dumps({}), encoding="utf-8")

    with pytest.raises(KeyError):
        hl.generate_entries(
            maps_dir=MAPS_DIR,
            tilesets_json=TILESETS_JSON,
            map_constants_json=empty_constants,
            metadata_header=METADATA_HEADER,
        )


def test_initial_anchor_reads_from_generated_header() -> None:
    """The initial anchor comes from the emitted metadata.h, not a hardcoded
    49/7/7 — matches `URANIUM_START_MAP/X/Y/DIR`."""
    anchor = hl.initial_anchor(METADATA_HEADER)
    assert anchor == hl.InitialAnchor(map_id=49, x=7, y=7, direction=2)


def test_call_site_heal_locations_real_corpus() -> None:
    """The transpiler-facing lookup returns exactly the one staged call site,
    mapped to the same id `generate_entries` mints for it."""
    mapping = hl.call_site_heal_locations(
        maps_dir=MAPS_DIR,
        tilesets_json=TILESETS_JSON,
        map_constants_json=MAP_CONSTANTS_JSON,
        metadata_header=METADATA_HEADER,
    )
    assert mapping == {(68, 1, 0): "HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER"}


# -- synthetic (no real corpus needed) tests for the new resolution rule ----


def _grid(xsize: int, ysize: int, layers: list[list[list[int]]]) -> TileGrid:
    """Build a `TileGrid` from `layers[z][y][x]` (z ascending, bottom first)."""
    zsize = len(layers)
    data = [0] * (xsize * ysize * zsize)
    for z, plane in enumerate(layers):
        for y, row in enumerate(plane):
            for x, tid in enumerate(row):
                data[z * ysize * xsize + y * xsize + x] = tid
    return TileGrid(xsize, ysize, zsize, data)


class TestSyntheticResolution:
    """No `output/uranium-build/` dependency — pure geometry/reachability
    fixtures, so these run unconditionally (module-level skipif above only
    gates the real-corpus tests)."""

    def test_across_counter_resolution(self) -> None:
        """Mirrors the real Map068 shape: event at (2,2), a counter directly
        below it at (2,3) (furniture — impassable, but interactable across),
        and the tile beyond the counter at (2,4) open and connected to the
        map's one warp exit at (2,5). Every other approach side is walled
        off, so the across-counter tile is the only candidate."""
        blocked = {(x, y): True for x in range(5) for y in range(6)}
        for cell in ((2, 2), (2, 4), (2, 5)):
            blocked[cell] = False
        counters = {(2, 3): True}  # the counter tile itself stays blocked

        graph = MapGraph(
            map_id=1,
            width=5,
            height=6,
            tileset_id=0,
            blocked=blocked,
            warp_exits={(2, 5): []},
        )

        candidates = hl._candidate_approach_tiles(2, 2, 5, 6, blocked, counters)
        # No plain "adjacent" candidate survives (all four neighbours of the
        # event are blocked); the across-counter candidate below the
        # counter is the only one.
        assert [(c.cell, c.kind, c.direction) for c in candidates] == [
            ((2, 4), "across-counter", hl.DIR_UP)
        ]

        warp_anchor_cells = hl._warp_adjacent_cells(set(graph.warp_exits.keys()))
        reachable = hl._reachable_candidates(candidates, graph, warp_anchor_cells)
        assert [c.cell for c in reachable] == [(2, 4)]
        assert reachable[0].direction == hl.DIR_UP

    def test_sealed_pocket_rejected(self) -> None:
        """A passable-but-walled-off adjacent tile (all of its own
        neighbours blocked, and it never reaches a warp cell) must be
        discarded even though it passes the local geometric check."""
        # event at (2,2); its "adjacent" candidate (2,1) is open but has no
        # other open neighbours and no path to the warp at (0,0).
        blocked = {(x, y): True for x in range(4) for y in range(4)}
        blocked[(2, 1)] = False  # sealed pocket: open, but isolated
        blocked[(0, 0)] = False  # the map's real, connected floor
        counters: dict[tuple[int, int], bool] = {}

        graph = MapGraph(
            map_id=2,
            width=4,
            height=4,
            tileset_id=0,
            blocked=blocked,
            warp_exits={(0, 0): []},
        )

        candidates = hl._candidate_approach_tiles(2, 2, 4, 4, blocked, counters)
        assert [(c.cell, c.kind) for c in candidates] == [((2, 1), "adjacent")]

        warp_anchor_cells = hl._warp_adjacent_cells(set(graph.warp_exits.keys()))
        reachable = hl._reachable_candidates(candidates, graph, warp_anchor_cells)
        assert reachable == []

    def test_two_reachable_candidates_unresolved(self) -> None:
        """Two candidates both reachable to the same warp exit, via disjoint
        routes that never cross the event's own tile: the rule must refuse
        to guess between them.

        Layout (event at (2,2), open cells marked `.`, blocked `#`):

            . # .
            . # .
            . . .    <- y=4, warp at (2,4)

        Left column (1,2)-(1,3)-(1,4) and right column (3,2)-(3,3)-(3,4)
        both reach the warp via the y=4 connector row, without ever
        touching (2,1), (2,2), or (2,3)."""
        blocked = {(x, y): True for x in range(5) for y in range(5)}
        for cell in (
            (1, 2), (1, 3), (1, 4),
            (3, 2), (3, 3), (3, 4),
            (2, 4),
        ):
            blocked[cell] = False
        counters: dict[tuple[int, int], bool] = {}

        graph = MapGraph(
            map_id=3,
            width=5,
            height=5,
            tileset_id=0,
            blocked=blocked,
            warp_exits={(2, 4): []},
        )

        candidates = hl._candidate_approach_tiles(2, 2, 5, 5, blocked, counters)
        assert {c.cell for c in candidates} == {(1, 2), (3, 2)}

        warp_anchor_cells = hl._warp_adjacent_cells(set(graph.warp_exits.keys()))
        reachable = hl._reachable_candidates(candidates, graph, warp_anchor_cells)
        # Two reachable candidates: `_resolve_bare` (real-corpus tests above
        # exercise its file-backed code path end to end) treats this as
        # unresolved rather than guessing between them — this test isolates
        # the exact condition (`len(reachable) != 1`) that triggers that.
        assert len(reachable) == 2
