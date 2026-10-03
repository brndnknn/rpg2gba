"""Tests for `playtest.cells.grass_cell`, `.cell_for_local_id`, and
`.seam_cells` -- the three resolvers added to cover the 9 coordinate
literals in `ch02.py`/`ch03.py`/`ch04.py` that none of the pre-existing
resolvers (`event_cell`/`approach_to`/`warp_cell`/`arrival_cell`/
`stair_approach`) can express: two tall-grass pairs, three boulders keyed by
compiled local id, and one map-connection seam.

Same skip idiom as `test_cells_stair_approach.py`/`test_start_cell_registry.py`:
these need the decoded corpus under `output/uranium-build/`, which is
gitignored, so the whole module is skipped rather than failing on a machine
that hasn't run the pipeline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.playtest.cells import cell_for_local_id, grass_cell, seam_cells

BUILD = Path("output/uranium-build")
requires_decoded_output = pytest.mark.skipif(
    not (BUILD / "maps").is_dir(), reason="decoded corpus absent (output/ is gitignored)"
)


# --- grass_cell --------------------------------------------------------------

#: (map_constant, x, y), the four grass cells `ch02.py`/`ch04.py` name today.
KNOWN_GRASS = [
    ("MAP_ROUTE_01", 30, 7, "ch02 GRASS_CELL_A"),
    ("MAP_ROUTE_01", 31, 7, "ch02 GRASS_CELL_B"),
    ("MAP_ROUTE_02", 19, 49, "ch04 GRASS_CELL_A"),
    ("MAP_ROUTE_02", 19, 50, "ch04 GRASS_CELL_B"),
]


@requires_decoded_output
@pytest.mark.parametrize(
    "map_constant,x,y,provenance", KNOWN_GRASS,
    ids=[k[3].replace(" ", "-") for k in KNOWN_GRASS],
)
def test_grass_cell_confirms_every_known_grass_cell(
    map_constant: str, x: int, y: int, provenance: str,
) -> None:
    assert grass_cell(map_constant, x, y) == (x, y), provenance


@requires_decoded_output
def test_grass_cell_rejects_a_non_grass_cell_naming_the_real_behavior() -> None:
    with pytest.raises(ValueError) as exc:
        grass_cell("MAP_ROUTE_01", 0, 0)
    message = str(exc.value)
    assert "not tall grass" in message
    assert "MB_NORMAL" in message


@requires_decoded_output
def test_grass_cell_rejects_an_out_of_bounds_cell() -> None:
    with pytest.raises(ValueError, match="out of bounds"):
        grass_cell("MAP_ROUTE_01", 9999, 9999)


# --- cell_for_local_id ---------------------------------------------------

#: (map_constant, local_id, expected cell) -- ch03.py's BOULDERS on map 19.
KNOWN_BOULDERS = [
    ("MAP_PASSAGE_CAVE_GROTT_HOLE", 1, (10, 14)),
    ("MAP_PASSAGE_CAVE_GROTT_HOLE", 2, (8, 15)),
    ("MAP_PASSAGE_CAVE_GROTT_HOLE", 3, (10, 12)),
]


@requires_decoded_output
@pytest.mark.parametrize("map_constant,local_id_value,expected", KNOWN_BOULDERS)
def test_cell_for_local_id_reproduces_every_known_boulder(
    map_constant: str, local_id_value: int, expected: tuple[int, int],
) -> None:
    assert cell_for_local_id(map_constant, local_id_value) == expected


@requires_decoded_output
def test_cell_for_local_id_rejects_an_unknown_id_naming_the_real_ones() -> None:
    with pytest.raises(ValueError) as exc:
        cell_for_local_id("MAP_PASSAGE_CAVE_GROTT_HOLE", 999)
    message = str(exc.value)
    assert "no object event with local id 999" in message
    assert "[1, 2, 3" in message


@requires_decoded_output
def test_cell_for_local_id_fails_loud_on_an_unstaged_map() -> None:
    # MAP_ABYSSAL_VENESI (Uranium map 71) has no staged local-id table --
    # only maps touched by CH01-CH04's own staging runs do.
    with pytest.raises(ValueError, match="has not been staged"):
        cell_for_local_id("MAP_ABYSSAL_VENESI", 1)


# --- seam_cells ------------------------------------------------------------


@requires_decoded_output
def test_seam_cells_reproduces_the_kevlar_route_2_seam() -> None:
    """`ch04.py`'s `KEVLAR_SEAM_ARROW = (32, 0)` is `seam_cells(...)[1]`;
    `[0]` is the seam's other cell, (31, 0), whose Route 2 landing is
    blocked and so is never used by any beat (see `ch04.py`'s module
    docstring), but is still a real, geometry-verified seam cell."""
    assert seam_cells("MAP_KEVLAR_TOWN", to="MAP_ROUTE_02") == ((31, 0), (32, 0))


@requires_decoded_output
def test_seam_cells_fails_loud_when_the_two_maps_share_no_seam() -> None:
    with pytest.raises(ValueError) as exc:
        seam_cells("MAP_KEVLAR_TOWN", to="MAP_ROUTE_01")
    message = str(exc.value)
    assert "no seam_warps.json entry touches" in message
    assert "kevlar_town_route_02" in message


@requires_decoded_output
def test_seam_cells_fails_loud_when_the_near_map_is_not_a_party() -> None:
    """Route 1 shares no seam with anything; Route 2 (`to=`) DOES have a
    seam, but with Kevlar Town, not Route 1 -- a different, more specific
    failure than "no seam at all", and the message must say who Route 2's
    real partner is."""
    with pytest.raises(ValueError) as exc:
        seam_cells("MAP_ROUTE_01", to="MAP_ROUTE_02")
    message = str(exc.value)
    assert "has a seam, but not with" in message
    assert "[31]" in message


@requires_decoded_output
def test_seam_cells_fails_loud_on_a_real_border_connection() -> None:
    """Route 2 <-> Nowtoch City (map 40) is a genuine, un-substituted
    pokeemerald connection in `connections.json` -- not a seam_warps.json
    arrow-warp pair -- so it is a whole-edge crossing this resolver
    structurally cannot reduce to a handful of cells, and must say so
    rather than inventing an answer."""
    with pytest.raises(ValueError) as exc:
        seam_cells("MAP_ROUTE_02", to="MAP_NOWTOCH_CITY")
    message = str(exc.value)
    assert "real connections.json border" in message
    assert "not a seam_warps.json arrow-warp substitution" in message


@requires_decoded_output
def test_seam_cells_fails_loud_when_multiple_seams_match(monkeypatch) -> None:
    """Ambiguity isn't reachable with today's single-seam corpus, so this
    injects a second synthetic seam entry sharing both map ids with the real
    Kevlar<->Route 2 one, to pin the behavior before the table ever grows
    into it for real."""
    import rpg2gba.playtest.cells as cells_mod

    real_seams = cells_mod._seam_warps()
    duplicate = dict(real_seams[0])
    duplicate["id"] = "duplicate_kevlar_route_02"
    monkeypatch.setattr(cells_mod, "_SEAM_WARPS_CACHE", [*real_seams, duplicate])

    with pytest.raises(ValueError) as exc:
        seam_cells("MAP_KEVLAR_TOWN", to="MAP_ROUTE_02")
    message = str(exc.value)
    assert "distinct seam_warps.json entries" in message


# --- arrival_cell ------------------------------------------------------------

@requires_decoded_output
def test_arrival_cell_accepts_several_exits_sharing_one_landing() -> None:
    """Map049 EV002 carries two transfer pages (p1, p3), both landing on Moki
    (28,31); `event_id=` cannot separate pages of one event, and there is
    only one answer, so this resolves rather than failing loud."""
    from rpg2gba.playtest.cells import arrival_cell

    landing = arrival_cell(
        "MAP_MOKI_TOWN", from_map="MAP_MOKI_TOWN_PLAYERS_HOUSE_1F", event_id=2)
    assert landing == (28, 31)


@requires_decoded_output
def test_arrival_cell_still_fails_loud_when_landings_differ() -> None:
    """Kevlar's building strip has four doors into town with four landings."""
    from rpg2gba.playtest.cells import arrival_cell

    with pytest.raises(ValueError, match="disambiguate with event_id="):
        arrival_cell("MAP_KEVLAR_TOWN", from_map="MAP_KEVLAR_TOWN_BUILDINGS")


# --- seam_warp_cells / is_seam_crossing (injected tables, no build artifacts) --

def _inject_seam_tables(monkeypatch) -> None:
    import rpg2gba.playtest.cells as cells_mod

    monkeypatch.setattr(cells_mod, "_SEAM_WARPS_CACHE", [
        {"id": "synthetic", "map_a": 31, "map_b": 35,
         "cells_a": [[31, 0], [32, 0]], "cells_b": [[20, 56], [21, 56]]}])
    monkeypatch.setattr(cells_mod, "_MAP_CONST_INDEX", {
        "MAP_A": 31, "MAP_B": 35, "MAP_C": 99})


def test_seam_warp_cells_returns_each_sides_cells(monkeypatch) -> None:
    from rpg2gba.playtest.cells import seam_warp_cells

    _inject_seam_tables(monkeypatch)
    assert seam_warp_cells(31, 35) == ((31, 0), (32, 0))
    assert seam_warp_cells(35, 31) == ((20, 56), (21, 56))


def test_seam_warp_cells_is_empty_for_an_unrelated_pair(monkeypatch) -> None:
    from rpg2gba.playtest.cells import seam_warp_cells

    _inject_seam_tables(monkeypatch)
    assert seam_warp_cells(31, 99) == ()
    assert seam_warp_cells(98, 99) == ()


def test_is_seam_crossing_true_false_and_no_raise(monkeypatch) -> None:
    from rpg2gba.playtest.cells import is_seam_crossing

    _inject_seam_tables(monkeypatch)
    assert is_seam_crossing("MAP_A", "MAP_B", (32, 0)) is True
    assert is_seam_crossing("MAP_B", "MAP_A", (20, 56)) is True
    assert is_seam_crossing("MAP_A", "MAP_B", (33, 0)) is False
    assert is_seam_crossing("MAP_A", "MAP_C", (32, 0)) is False
