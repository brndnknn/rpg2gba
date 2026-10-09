"""Tests for `playtest.cells.stair_approach` (`POST_CH05_REVIEW.md` G4,
`PROJECT_TODO.md` #79 and #90).

**The six values these tests pin are the only independently-verified stair
approaches in the corpus**, and they are the reason the resolver uses the rule
it does:

- CH02's four `STAIR*_APPROACH` constants (`ch02.py:138-141`). Its B2 and B3
  step into each of Route 01's two staircases from both ends and assert the
  diagonal displacement against a booted ROM; the chapter passed its §9 gate,
  so all four are ROM-verified, not authored guesses.
- CH05's two `raw_cell` escapes (`ch05.py:548`, `:586`), which exist *only*
  because this resolver did not. Both passed CH05's §9 gate.

`routing.locations._stair_approach` answers a related but different question
("which cell does the stair edge depart from") by testing `stair_diagonal`
ownership. Measured against these six, that rule reproduces 4 and returns an
**unstandable** cell for the other 2 -- it holds mid-run and breaks at the ends
of a diagonal run, where the flat cell you walk in from owns no edge. Plain
walkability of the named side reproduces all 6. That measurement is what
`test_walkability_rule_beats_edge_ownership_on_every_known_value` records, so
the choice does not have to be re-derived later.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.playtest.cells import stair_approach

BUILD = Path("output/uranium-build")
_CORPUS = pytest.mark.skipif(
    not (BUILD / "maps").is_dir(), reason="decoded corpus absent (output/ is gitignored)"
)

#: (map_constant, uranium_id, stair_event, stair_cell, side, expected, provenance)
KNOWN_GOOD = [
    ("MAP_ROUTE_01", 33, 33, (57, 9), "west", (56, 9), "ch02 STAIR1_WEST_APPROACH"),
    ("MAP_ROUTE_01", 33, 31, (57, 10), "east", (58, 10), "ch02 STAIR1_EAST_APPROACH"),
    ("MAP_ROUTE_01", 33, 69, (52, 41), "west", (51, 41), "ch02 STAIR2_WEST_APPROACH"),
    ("MAP_ROUTE_01", 33, 47, (53, 44), "east", (54, 44), "ch02 STAIR2_EAST_APPROACH"),
    ("MAP_PASSAGE_CAVE_2F", 37, 6, (20, 9), "west", (19, 9), "ch05 B14 raw_cell"),
    ("MAP_PASSAGE_CAVE_2F", 37, 8, (11, 9), "west", (10, 9), "ch05 B13 raw_cell"),
]


@_CORPUS
@pytest.mark.parametrize(
    "map_constant,uid,stair_event,stair,side,expected,provenance",
    KNOWN_GOOD,
    ids=[k[6].replace(" ", "-") for k in KNOWN_GOOD],
)
def test_reproduces_every_rom_verified_approach(
    map_constant: str, uid: int, stair_event: int, stair: tuple[int, int],
    side: str, expected: tuple[int, int], provenance: str,
) -> None:
    assert stair_approach(map_constant, stair_event=stair_event, side=side) == expected, (
        provenance
    )


@_CORPUS
def test_walkability_rule_beats_edge_ownership_on_every_known_value() -> None:
    """Records the measurement the resolver's rule was chosen on.

    If someone later "simplifies" `stair_approach` to reuse
    `_stair_approach`'s `stair_diagonal`-ownership test, this fails and says
    exactly what breaks and why.
    """
    from rpg2gba.routing.locations import _stair_approach

    ownership_ok = 0
    for map_constant, uid, _ev, stair, _side, expected, _prov in KNOWN_GOOD:
        try:
            got = _stair_approach(uid, map_constant, stair[0], stair[1], row_id="probe")
        except ValueError:
            continue
        ownership_ok += got == expected

    walkability_ok = sum(
        stair_approach(mc, stair_event=ev, side=sd) == exp
        for mc, _uid, ev, _st, sd, exp, _p in KNOWN_GOOD
    )
    assert walkability_ok == len(KNOWN_GOOD)
    assert ownership_ok < len(KNOWN_GOOD), (
        "edge-ownership now reproduces every known value too -- if that is a real "
        "improvement to _stair_approach, update this test's premise deliberately "
        "rather than deleting it"
    )


# --- fail-loud behaviour -----------------------------------------------------


@_CORPUS
def test_a_side_that_is_not_walkable_fails_loud_and_names_the_other() -> None:
    """`side` is a claim about which end the beat enters from, so an
    unwalkable one must never silently fall back to the opposite side --
    that is `approach_to`'s `prefer=` contract, applied here."""
    with pytest.raises(ValueError) as exc:
        stair_approach("MAP_ROUTE_01", stair_event=69, side="east")
    message = str(exc.value)
    assert "not walkable" in message
    assert "(51, 41)" in message  # the side that IS available, named


@_CORPUS
def test_a_cell_partway_along_a_diagonal_run_says_so() -> None:
    """(53,43) sits mid-run: its west neighbour is unwalkable. The error has to
    distinguish this from 'you picked the wrong end', because the fix differs."""
    with pytest.raises(ValueError, match="not walkable"):
        stair_approach("MAP_ROUTE_01", stair_event=48, side="west")


@_CORPUS
def test_an_event_that_is_not_a_staircase_is_rejected() -> None:
    """An approach to a non-stair event is a stale beat, not something to round
    off -- and the message lists what the map actually has."""
    with pytest.raises(ValueError) as exc:
        stair_approach("MAP_ROUTE_01", stair_event=999, side="west")
    assert "is not a diagonal-stair event" in str(exc.value)
    assert "33" in str(exc.value)  # the real stair event ids, enumerated


@_CORPUS
@pytest.mark.parametrize("side", ["north", "south", "up", "", "WEST"])
def test_only_east_and_west_are_accepted(side: str) -> None:
    """A sideways staircase is entered by a horizontal press; N/S is a
    category error, not a side that happens to be unwalkable."""
    with pytest.raises(ValueError, match="must be 'east' or 'west'"):
        stair_approach("MAP_ROUTE_01", stair_event=33, side=side)


@_CORPUS
def test_every_detected_stair_cell_resolves_or_fails_loud() -> None:
    """No stair cell in the built corpus may return a cell the player cannot
    stand on. Silent-wrong is the failure mode this whole resolver exists to
    remove, so the invariant is checked over every stair in the slice rather
    than only the six pinned above."""
    from rpg2gba.playtest.cells import _graph_for
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS
    from rpg2gba.tileset_converter.stairs import detect_stair_cells

    checked = 0
    for uid in SLICE_MAP_IDS:
        path = BUILD / "maps" / f"Map{uid:03d}.json"
        if not path.is_file():
            continue
        map_json = json.loads(path.read_text(encoding="utf-8"))
        stairs = detect_stair_cells(map_json)
        if not stairs:
            continue
        map_constant = _MAP_CONSTANTS[uid]
        _uid, graph = _graph_for(map_constant, resolver="test")
        for cell in stairs:
            for side in ("east", "west"):
                try:
                    got = stair_approach(
                        map_constant, stair_event=cell.event_id, side=side)
                except ValueError:
                    continue  # fail-loud is an acceptable answer
                assert graph.is_walkable(got), (
                    f"{map_constant} stair ({cell.x},{cell.y}) {side} -> {got}, "
                    "which is not walkable"
                )
                checked += 1
    assert checked > 0, "no stair cells found in the slice — corpus out of sync?"


_MAP_CONSTANTS = {
    33: "MAP_ROUTE_01",
    31: "MAP_KEVLAR_TOWN",
    37: "MAP_PASSAGE_CAVE_2F",
    14002: "MAP_NOWTOCH_CITY_PARK",  # CH06: 4 diagonal-stair events (map 40's park piece)
}
