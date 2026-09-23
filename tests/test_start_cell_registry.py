"""Derived entry cells (`chapter_manifest.generator._start_cells`, A5) must
be walkable.

A5 (C6_GENERATOR_PLAN.md) replaced the hand-kept per-chapter start-cell
table with a derivation from source data
(`beat_gen.reach.chapter_entry_cells`): the engine spawn plus every landing a
reachable warp/seam/connection puts the player on, flooded over a chapter's
own chain. Walkability is still worth checking here even though the
derivation is not hand-typed -- a landing_cell computation that resolves to a
blocked tile is exactly the "confident wrong answer" the old table's own
comment warned about (every event on the map reported unreachable), and nothing
downstream re-checks it.

This module used to also assert that every entry's cells share one connected
component (the soundness argument that let a SUPERSET of "the first-arrival
cell" stand in for the exact first-arrival cell in the old hand-kept table).
That check is dropped here: it was a soundness argument for a hand-picked
superset of possible arrivals, not a property of the underlying geography.
The derived cells ARE the exact set of landings a reachable crossing puts the
player on -- not a guessed superset -- so a multi-component map (several
disconnected walkable areas each entered by its own door, e.g. Kevlar's
four-shop strip) is simply a map with several genuine entries, not a
soundness violation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.chapter_atlas.binding import load_binding
from rpg2gba.chapter_manifest.generator import _start_cells
from rpg2gba.traversal.graph import build_map_graph

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = REPO_ROOT / "output" / "uranium-build"
MAPS_DIR = BUILD_DIR / "maps"
TILESETS_JSON = BUILD_DIR / "tilesets.json"
CHAPTERS_JSON = REPO_ROOT / "reference" / "chapters.json"

requires_decoded_output = pytest.mark.skipif(
    not (MAPS_DIR.is_dir() and TILESETS_JSON.is_file() and CHAPTERS_JSON.is_file()),
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)


def _derived_keys() -> list[tuple[str, int]]:
    """Every (chapter_id, map_id) pair for CH01-CH05's own maps that has a
    derivable entry cell -- built once at collection time so the walkability
    tests below can be parametrized the same way the old table-driven tests
    were."""
    if not (MAPS_DIR.is_dir() and TILESETS_JSON.is_file() and CHAPTERS_JSON.is_file()):
        return []
    binding = load_binding(CHAPTERS_JSON)
    keys: list[tuple[str, int]] = []
    for chapter_id in ("CH01", "CH02", "CH03", "CH04", "CH05"):
        for map_id in binding.chapter(chapter_id).maps:
            if _start_cells(chapter_id, map_id, BUILD_DIR) is not None:
                keys.append((chapter_id, map_id))
    return keys


@requires_decoded_output
@pytest.mark.parametrize("key", _derived_keys())
def test_every_derived_entry_cell_is_walkable(key):
    chapter_id, map_id = key
    graph = build_map_graph(map_id, maps_dir=MAPS_DIR, tilesets_json=TILESETS_JSON)
    cells = _start_cells(chapter_id, map_id, BUILD_DIR)

    unwalkable = sorted(cell for cell in cells if not graph.is_walkable(cell))

    assert not unwalkable, (
        f"{chapter_id}/map{map_id:03d}: derived entry cell(s) {unwalkable} are not "
        "walkable. A start cell that cannot be stood on floods nothing, so every event "
        "on this map would be reported unreachable -- worse than leaving the map "
        "unregistered, which honestly reports 'unanswerable'."
    )
