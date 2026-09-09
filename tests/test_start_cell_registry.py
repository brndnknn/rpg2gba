"""`_CHAPTER_MAP_START_CELLS`'s entries must stay sound, not just present.

The registry's own comment block argues that a DERIVED start-cell set is safe
for CH01-CH03 because of two properties that a reader cannot check by eye:

1. **Every registered cell is walkable.** An unwalkable cell floods nothing,
   so registering one produces a confident wrong answer (every event on the
   map reported unreachable) where leaving the map out would have honestly
   reported "unanswerable". Five real door tiles were dropped during the
   2026-09-09 derivation for exactly this reason -- Map031's (23,28),
   (32,28), (35,6), (37,28) and Map033's (39,18), all shop-exit doorways the
   warp lands you on and steps you off.

2. **All of an entry's cells share one connected component** -- with map 73
   as the single, deliberate exception. This is what makes a superset of
   "the first-arrival cell" equivalent to the first-arrival cell itself: if
   every candidate lies in one component, the flood is identical whichever
   is chosen. The property is monotone in capabilities (adding a capability
   only merges components, never splits them), so component-agreement with
   nothing held implies it under every held set.

Both are load-bearing for the manifests the re-derivation freezes, and
neither is enforced anywhere else. A future edit that registers a door tile,
or a second component on a map that had one, would otherwise be silent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.generator import _CHAPTER_MAP_START_CELLS
from rpg2gba.traversal.graph import build_map_graph

REPO_ROOT = Path(__file__).resolve().parents[1]
MAPS_DIR = REPO_ROOT / "output" / "uranium-build" / "maps"
TILESETS_JSON = REPO_ROOT / "output" / "uranium-build" / "tilesets.json"

requires_decoded_output = pytest.mark.skipif(
    not (MAPS_DIR.is_dir() and TILESETS_JSON.is_file()),
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)

# The one entry whose cells deliberately span several components: Kevlar's
# building strip is one map record holding four shops behind four separate
# doors, all four of which CH03 actually enters.
_MULTI_COMPONENT_ENTRY = ("CH03", 73)
_MULTI_COMPONENT_CELLS = 4


def _component_index(components: list[set[tuple[int, int]]], cell: tuple[int, int]) -> int | None:
    return next((i for i, comp in enumerate(components) if cell in comp), None)


@requires_decoded_output
@pytest.mark.parametrize("key", sorted(_CHAPTER_MAP_START_CELLS))
def test_every_registered_start_cell_is_walkable(key):
    chapter_id, map_id = key
    graph = build_map_graph(map_id, maps_dir=MAPS_DIR, tilesets_json=TILESETS_JSON)

    unwalkable = sorted(
        cell for cell in _CHAPTER_MAP_START_CELLS[key] if not graph.is_walkable(cell)
    )

    assert not unwalkable, (
        f"{chapter_id}/map{map_id:03d}: registered start cell(s) {unwalkable} are not "
        "walkable. A start cell that cannot be stood on floods nothing, so every event "
        "on this map would be reported unreachable -- worse than leaving the map "
        "unregistered, which honestly reports 'unanswerable'. If this is a warp "
        "destination, it is most likely a door tile (a blocked metatile the warp lands "
        "you on and steps you off); drop it and register the walkable arrivals."
    )


@requires_decoded_output
@pytest.mark.parametrize("key", sorted(_CHAPTER_MAP_START_CELLS))
def test_start_cells_agree_on_one_component(key):
    """See this module's docstring, property 2."""
    chapter_id, map_id = key
    cells = _CHAPTER_MAP_START_CELLS[key]
    graph = build_map_graph(map_id, maps_dir=MAPS_DIR, tilesets_json=TILESETS_JSON)
    components = graph.connected_components()
    indices = {_component_index(components, cell) for cell in cells}

    if key == _MULTI_COMPONENT_ENTRY:
        assert len(cells) == _MULTI_COMPONENT_CELLS, (
            f"{chapter_id}/map{map_id:03d} is the registry's one deliberate "
            f"multi-component entry and is expected to carry exactly "
            f"{_MULTI_COMPONENT_CELLS} cells (one per shop door), found {len(cells)}."
        )
        assert len(indices) == _MULTI_COMPONENT_CELLS, (
            f"{chapter_id}/map{map_id:03d}: expected each of the four shop doors to "
            f"land in its own component, found {len(indices)} distinct component(s). "
            "If the map's collision changed, re-derive this entry rather than "
            "relaxing the test."
        )
        return

    assert len(indices) == 1, (
        f"{chapter_id}/map{map_id:03d}: registered start cells span {len(indices)} "
        f"connected components ({sorted(cells)}). The registry's soundness argument "
        "for a derived start-cell set depends on component agreement -- with several "
        "components, which cell you start from changes what is reachable, so the set "
        "must be exactly the doors the chapter genuinely enters (as for CH03/map073) "
        "rather than every arrival the corpus offers."
    )
