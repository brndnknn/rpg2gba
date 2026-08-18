"""Corpus-wide invariant for post-warp facing.

The engine has no way to face the player anywhere but south on arrival
(`GetAdjustedInitialDirection`, engine/src/overworld.c:1060 — every branch
needs a metatile behavior we deliberately don't stamp on arrival tiles, and
the fallback is `DIR_SOUTH`). Facing is therefore entirely the pipeline's
job, via the ON_WARP_INTO_MAP_TABLE script `compute_arrival_facings` feeds.

The unit tests in `test_tileset_converter.py` pin that function's rules on
synthetic fixtures. This file pins the *result* over the real built slice,
as the property that actually matters to a player:

    when you land, you face a tile you can walk onto, and it is not the
    warp you just came out of.

That is "face away from the return warp" stated executably. It fires for
any warp added later, in any chapter, without anyone having to remember
the Kevlar bug (CH03: four arrivals inherited `DIR_SOUTH` because Uranium
authored RMXP direction 0, "retain current facing", which pokeemerald
cannot honor).

Skips when the slice output isn't staged, matching `test_assembly.py`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rpg2gba.tileset_converter import metadata_wiring as mw
from rpg2gba.tileset_converter.layout import TileGrid, column_blocked, column_key
from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

_OUT = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
_MAPS_DIR = _OUT / "maps"
_TILESETS = _OUT / "tilesets.json"

# (dx, dy) the player looks toward, per engine DIR_* constant. y grows south.
_DIR_VECTOR: dict[str, tuple[int, int]] = {
    "DIR_NORTH": (0, -1),
    "DIR_SOUTH": (0, 1),
    "DIR_WEST": (-1, 0),
    "DIR_EAST": (1, 0),
}

_HAVE_OUTPUT = _MAPS_DIR.is_dir() and _TILESETS.is_file() and all(
    (_MAPS_DIR / f"Map{uid:03d}.json").is_file() for uid in SLICE_MAP_IDS
)

pytestmark = pytest.mark.skipif(
    not _HAVE_OUTPUT, reason="staged slice output not present"
)


@pytest.fixture(scope="module")
def slice_data() -> tuple[dict[int, dict], dict[int, list[mw.WarpSpec]], dict]:
    """The real slice maps, their warp specs, and the tileset oracle."""
    slice_set = set(SLICE_MAP_IDS)
    maps = {
        uid: json.loads(
            (_MAPS_DIR / f"Map{uid:03d}.json").read_text(encoding="utf-8")
        )
        for uid in SLICE_MAP_IDS
    }
    warp_lists = {
        uid: [spec for _event, spec in mw.classify_map_events(maps[uid], slice_set)[1]]
        for uid in SLICE_MAP_IDS
    }
    tilesets = json.loads(_TILESETS.read_text(encoding="utf-8"))
    return maps, warp_lists, tilesets


def _blocked(map_json: dict, tilesets: dict, x: int, y: int) -> bool:
    """RMXP multi-layer passability for one cell of a real slice map, through
    the single implementation of the rule (`layout.column_blocked`)."""
    tiles = map_json["tiles"]
    grid = TileGrid(tiles["xsize"], tiles["ysize"], tiles["zsize"], tiles["data"])
    ts = tilesets[str(map_json["tileset_id"])]
    return column_blocked(
        column_key(grid, x, y),
        passages=ts["passages"],
        priorities=ts.get("priorities"),
        terrain_tags=ts.get("terrain_tags"),
    )


def _in_bounds(map_json: dict, x: int, y: int) -> bool:
    return 0 <= x < map_json["width"] and 0 <= y < map_json["height"]


def test_every_in_bounds_arrival_has_an_explicit_facing(slice_data) -> None:
    """No arrival may silently inherit the engine's `DIR_SOUTH` fallback.

    An arrival with no table row is not "defaulted", it is unspecified — the
    exact shape of the CH03 bug, where RMXP direction 0 meant "retain" and
    got skipped.
    """
    maps, warp_lists, tilesets = slice_data
    facings = mw.compute_arrival_facings(warp_lists, maps, tilesets=tilesets)

    covered = {
        (uid, f.x, f.y) for uid, entries in facings.items() for f in entries
    }
    missing = [
        (src_uid, spec.dest_uid, spec.dest_x, spec.dest_y)
        for src_uid, specs in warp_lists.items()
        for spec in specs
        if spec.dest_uid in maps
        and _in_bounds(maps[spec.dest_uid], spec.dest_x, spec.dest_y)
        and (spec.dest_uid, spec.dest_x, spec.dest_y) not in covered
    ]
    assert missing == [], (
        "arrivals with no ON_WARP_INTO_MAP facing row, so the player inherits "
        f"the engine's DIR_SOUTH fallback: {missing}"
    )


def _derived_arrivals(
    warp_lists: dict[int, list[mw.WarpSpec]]
) -> set[tuple[int, int, int]]:
    """Arrivals whose facing the pipeline DERIVED rather than read off the event.

    An arrival is derived exactly when every warp landing on it was authored
    with RMXP direction 0/None ("retain"). If any warp landing there names a
    direction, Uranium spoke and tier 2 used its answer verbatim.
    """
    authored: set[tuple[int, int, int]] = set()
    seen: set[tuple[int, int, int]] = set()
    for specs in warp_lists.values():
        for spec in specs:
            key = (spec.dest_uid, spec.dest_x, spec.dest_y)
            seen.add(key)
            if spec.dest_dir not in (0, None):
                authored.add(key)
    return seen - authored


def _wall_facers(
    facings: dict[int, list[mw.ArrivalFacing]], maps: dict[int, dict], tilesets: dict
) -> dict[tuple[int, int, int], str]:
    """Arrivals whose faced tile is off-map or impassable."""
    bad: dict[tuple[int, int, int], str] = {}
    for uid, entries in facings.items():
        map_json = maps[uid]
        for f in entries:
            dx, dy = _DIR_VECTOR[f.dir_const]
            nx, ny = f.x + dx, f.y + dy
            if not _in_bounds(map_json, nx, ny):
                bad[(uid, f.x, f.y)] = f"{f.dir_const} -> off-map"
            elif _blocked(map_json, tilesets, nx, ny):
                bad[(uid, f.x, f.y)] = f"{f.dir_const} -> blocked ({nx},{ny})"
    return bad


def test_derived_arrival_never_faces_a_wall(slice_data) -> None:
    """A DERIVED facing that points into a wall means the derivation guessed
    wrong — the player was never walking that way.

    Scoped to derived arrivals on purpose. Where Uranium authored a direction
    we reproduce it verbatim, wall or not; that case is pinned separately in
    `test_uranium_authored_wall_facers_are_pinned`.
    """
    maps, warp_lists, tilesets = slice_data
    facings = mw.compute_arrival_facings(warp_lists, maps, tilesets=tilesets)

    derived = _derived_arrivals(warp_lists)
    bad = {k: v for k, v in _wall_facers(facings, maps, tilesets).items() if k in derived}
    assert bad == {}, f"derived facings pointing at something unwalkable: {bad}"


def test_uranium_authored_wall_facers_are_pinned(slice_data) -> None:
    """Uranium sometimes authors a transfer direction that faces a wall.

    Maps 49 and 172 are the stairwell landings in the Moki houses: the player
    comes down from 2F onto (11,3), one tile west of the stairs at (12,3),
    and Uranium's transfer says direction 4 (west) — into the wall at (10,3).
    We reproduce that faithfully rather than "improving" it, because the
    authored direction is ground truth for fidelity (CLAUDE.md §10: content
    fidelity calls are the user's, not ours).

    Pinned as an exact set so a NEW authored wall-facer shows up as a failure
    and gets a deliberate look, instead of hiding in a warning nobody reads.
    """
    maps, warp_lists, tilesets = slice_data
    facings = mw.compute_arrival_facings(warp_lists, maps, tilesets=tilesets)

    derived = _derived_arrivals(warp_lists)
    authored_bad = {
        k: v for k, v in _wall_facers(facings, maps, tilesets).items() if k not in derived
    }
    assert authored_bad == {
        (49, 11, 3): "DIR_WEST -> blocked (10,3)",
        (172, 11, 3): "DIR_WEST -> blocked (10,3)",
    }


def test_arrival_never_faces_the_warp_it_came_out_of(slice_data) -> None:
    """The player must face AWAY from the return warp.

    Facing a warp cell means the first step forward re-triggers it, which is
    the bounce the arrow-warp metatile approach would have caused and the
    reason this is done with a script instead (metadata_wiring, docstring on
    `compute_arrival_facings`).
    """
    maps, warp_lists, tilesets = slice_data
    facings = mw.compute_arrival_facings(warp_lists, maps, tilesets=tilesets)

    for uid, entries in facings.items():
        warp_cells = {(s.src_x, s.src_y) for s in warp_lists[uid]}
        for f in entries:
            dx, dy = _DIR_VECTOR[f.dir_const]
            neighbor = (f.x + dx, f.y + dy)
            assert neighbor not in warp_cells, (
                f"map {uid} arrival ({f.x},{f.y}) faces {f.dir_const} into warp "
                f"cell {neighbor} — stepping forward would warp the player back"
            )


def test_kevlar_chapter_three_arrivals_face_up(slice_data) -> None:
    """Regression pin for the reported CH03 bug: the four destinations that
    landed the player facing down must now face north.

    Route 1 -> Kevlar Town (two-tile-wide edge warp), and the town's Poke
    Mart / Poke Center / flower-shop doors. All four are authored in Uranium
    with RMXP transfer direction 0 ("retain"), so all four are derived rather
    than read off the event.
    """
    maps, warp_lists, tilesets = slice_data
    facings = mw.compute_arrival_facings(warp_lists, maps, tilesets=tilesets)

    expected = {
        (31, 15, 42): "DIR_NORTH",  # Route 1 -> Kevlar Town, west tile
        (31, 16, 42): "DIR_NORTH",  # Route 1 -> Kevlar Town, east tile
        (67, 10, 10): "DIR_NORTH",  # town -> Poke Mart
        (68, 8, 18): "DIR_NORTH",   # town -> Poke Center
        (73, 44, 12): "DIR_NORTH",  # town -> flower shop
    }
    actual = {
        (uid, f.x, f.y): f.dir_const
        for uid, entries in facings.items()
        for f in entries
        if (uid, f.x, f.y) in expected
    }
    assert actual == expected
