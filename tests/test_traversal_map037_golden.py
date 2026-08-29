"""Golden regression: Map037 (CH05's cave), tileset 32 — the measured ground
truth from PLAYTEST_AUTHORING_IMPROVEMENT_V2.md §5.9 (~lines 1728-1745).

Methodology (matches the doc's own "Measured" derivation exactly): a plain
4-neighbour BFS over `layout.column_blocked`'s real walkability, with the
four staircase cells ((11,9), (11,10), (20,9), (20,10) —
`stairs.stair_cell_sides(Map037)`) forced walkable in one run and forced
blocked in another. This deliberately does NOT use the graph's diagonal
stair-displacement model (that model is exercised by
`test_traversal_graph.py`'s stair unit tests) — it is the doc's own simpler
validation that the four staircases are Map037's only south-centre/
north-centre link, independent of exactly how a diagonal press behaves.

Map entry point: confirmed (not guessed) from the map corpus itself —
`output/uranium-build/maps/Map036.json` event 2 is a command-201 transfer
into map 37 at (16, 26) (`rpg2gba.traversal.warps.extract_warp_exits` on
Map036 finds it), which is the reverse of Map037's own south warp
(`Map037.json` event 1, (16, 27) -> map 36). (16, 26) is therefore where the
player actually stands after walking in from the south, one tile north of
the warp trigger tile itself.

DISCREPANCY, since RESOLVED in this graph's favour: with this exact
methodology and this exact entry point, the trainer-approach and gift-NPC
distances match the doc's measured numbers exactly (23 and 26 steps,
identically whether the stairs are forced walkable or blocked, as the doc
states), and the stairs-blocked cave exit is UNREACHABLE as the doc says.
The stairs-open cave-exit distance did not: this test measures 35 steps
where the doc stated 34.

Settled by exhaustive search over the map rather than by argument: (16, 26)
is the UNIQUE cell on Map037 from which the trainer sits at 23 steps and the
gift NPC at 26, and no cell anywhere on the map produces the doc's full
34/23/26 triple. The entry point is therefore confirmed correct and the
doc's 34 was off by one. `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` §5.9 has
been corrected to 35; this test asserts the measured value.

The structural conclusion the doc drew from these numbers is untouched, and
it is the part that matters: the four staircases are the only link from
south-centre to north-centre, so the cave exit is unreachable without them.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.layout import TileGrid, column_blocked, column_key
from rpg2gba.tileset_converter.stairs import stair_cell_sides

MAPS_DIR = Path("output/uranium-build/maps")
TILESETS_JSON = Path("output/uranium-build/tilesets.json")
MAP037 = MAPS_DIR / "Map037.json"

pytestmark = pytest.mark.skipif(
    not MAP037.is_file() or not TILESETS_JSON.is_file(),
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)

ENTRY = (16, 26)
CAVE_EXIT = (16, 5)
TRAINER_APPROACH = (23, 10)
GIFT_APPROACH = (9, 7)


def _load() -> tuple[TileGrid, list, list, list, dict]:
    doc = json.loads(MAP037.read_text(encoding="utf-8"))
    t = doc["tiles"]
    grid = TileGrid(t["xsize"], t["ysize"], t["zsize"], t["data"])
    arrays = json.loads(TILESETS_JSON.read_text(encoding="utf-8"))[str(doc["tileset_id"])]
    return grid, arrays["passages"], arrays["priorities"], arrays["terrain_tags"], doc


def _bfs_distances(
    grid: TileGrid, passages, priorities, terrain_tags,
    stair_cells: set[tuple[int, int]], stairs_walkable: bool, start: tuple[int, int],
) -> dict[tuple[int, int], int]:
    """Plain 4-neighbour BFS distance map from `start`, with `stair_cells`
    force-set to `stairs_walkable` (overriding whatever plain collision says).
    """
    blocked: dict[tuple[int, int], bool] = {}
    for y in range(grid.ysize):
        for x in range(grid.xsize):
            if (x, y) in stair_cells:
                blocked[(x, y)] = not stairs_walkable
                continue
            key = column_key(grid, x, y)
            blocked[(x, y)] = column_blocked(
                key, passages=passages, priorities=priorities, terrain_tags=terrain_tags
            )
    assert not blocked[start], f"start {start} unexpectedly blocked"
    dist = {start: 0}
    queue = deque([start])
    while queue:
        cx, cy = queue.popleft()
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if 0 <= nx < grid.xsize and 0 <= ny < grid.ysize and (nx, ny) not in dist:
                if not blocked[(nx, ny)]:
                    dist[(nx, ny)] = dist[(cx, cy)] + 1
                    queue.append((nx, ny))
    return dist


@pytest.fixture(scope="module")
def _map037_data():
    return _load()


@pytest.fixture(scope="module")
def _stair_cells(_map037_data):
    _, _, _, _, doc = _map037_data
    cells = set(stair_cell_sides(doc))
    assert cells == {(11, 9), (11, 10), (20, 9), (20, 10)}
    return cells


def test_entry_point_confirmed_from_map036s_reverse_warp():
    """(16, 26) is not guessed: it's Map036 event 2's command-201 destination
    into map 37, the reverse of Map037's own (16,27)->map36 south warp."""
    from rpg2gba.traversal.warps import extract_warp_exits

    map036 = json.loads((MAPS_DIR / "Map036.json").read_text(encoding="utf-8"))
    exits = extract_warp_exits(map036)
    into_37 = [w for w in exits if w.dest_map == 37]
    assert into_37, "Map036 has no literal warp into map 37"
    assert (into_37[0].dest_x, into_37[0].dest_y) == ENTRY


def test_trainer_approach_reachable_23_steps_regardless_of_stairs(_map037_data, _stair_cells):
    grid, pas, pri, ter, _ = _map037_data
    for stairs_walkable in (True, False):
        dist = _bfs_distances(grid, pas, pri, ter, _stair_cells, stairs_walkable, ENTRY)
        assert dist.get(TRAINER_APPROACH) == 23


def test_gift_npc_approach_reachable_26_steps_regardless_of_stairs(_map037_data, _stair_cells):
    grid, pas, pri, ter, _ = _map037_data
    for stairs_walkable in (True, False):
        dist = _bfs_distances(grid, pas, pri, ter, _stair_cells, stairs_walkable, ENTRY)
        assert dist.get(GIFT_APPROACH) == 26


def test_cave_exit_unreachable_with_stairs_blocked(_map037_data, _stair_cells):
    """The doc's core claim, reproduced exactly: block the four staircases
    and the cave exit becomes provably unreachable — the staircases are not
    cosmetic, they are the only south-centre/north-centre link (§5.9)."""
    grid, pas, pri, ter, _ = _map037_data
    dist = _bfs_distances(grid, pas, pri, ter, _stair_cells, False, ENTRY)
    assert CAVE_EXIT not in dist


def test_cave_exit_reachable_with_stairs_walkable(_map037_data, _stair_cells):
    """Reproduces with the confirmed entry point and the doc's exact
    methodology. 35 steps: the doc originally stated 34 and has been
    corrected — see the module docstring for how that was settled."""
    grid, pas, pri, ter, _ = _map037_data
    dist = _bfs_distances(grid, pas, pri, ter, _stair_cells, True, ENTRY)
    assert dist.get(CAVE_EXIT) == 35
