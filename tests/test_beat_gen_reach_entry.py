"""`beat_gen.reach.chapter_entry_cells` (C6 A5 groundwork): each map's entry
cells derived from the engine spawn over the chapter chain, against the real
build. Pins the measured differences from the hand-kept
`_CHAPTER_MAP_START_CELLS` that make the derivation the better answer."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_gen.reach import chapter_entry_cells
from rpg2gba.chapter_atlas.binding import load_binding
from rpg2gba.routing.__main__ import _build_graphs_and_overlays, _build_world, _LazyOccupancy

BUILD = Path("output/uranium-build")


def _cells(chapter_id: str) -> dict[int, frozenset[tuple[int, int]]]:
    binding = load_binding(Path("reference/chapters.json"))
    chain: list[int] = []
    for cid in ("CH01", "CH02", "CH03", "CH04", "CH05"):
        chain += binding.chapter(cid).maps
        if cid == chapter_id:
            break
    graphs, _ = _build_graphs_and_overlays(chain, BUILD)
    return chapter_entry_cells(frozenset(binding.chapter(chapter_id).maps), frozenset(chain),
                               graphs, _build_world(BUILD), _LazyOccupancy(BUILD))


@pytest.fixture(scope="module")
def ch01() -> dict[int, frozenset[tuple[int, int]]]:
    return _cells("CH01")


def test_the_spawn_is_an_entry(ch01):
    assert (7, 7) in ch01[49]


def test_a_later_chapters_warp_is_not_an_entry(ch01):
    # (8,43) is the return from Route 1 (CH02's map): the table listed it.
    assert ch01[32] == {(17, 11), (24, 42), (28, 31), (43, 31), (56, 42)}


def test_a_seam_enters_on_every_crossing_cell():
    assert _cells("CH04")[35] == {(20, 56), (21, 56), (22, 56), (23, 56), (24, 56), (25, 56)}
