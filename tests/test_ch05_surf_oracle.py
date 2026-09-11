"""Regression test that reproduces the frozen CH05 `blocked:surf` derivation
recorded in `reference/frozen/ch05_surf_expectations.json`.

slice2's oracle (`test_traversal_frozen_oracle.py`) validated the
*event-obstacle* route: a graph-walkable cell that an event's script head
gates on a capability (rock_smash). CH05 is the corpus's only *terrain-
gated* case -- the inverted route, where the collision graph itself marks
water tiles as blocked and holding Surf flips them passable. This test makes
that half of the model mechanically checkable, the same way the slice-2 test
does for the event-obstacle half.

`ch05_surf_expectations.json` is a FROZEN ORACLE -- see its own `rule`
field. Its `provenance_honesty` block is explicit that this is not a blind
freeze (the derivation engine predates the file) and that the negative arm
is the load-bearing check: a derivation that flipped to marking the whole
map surf-gated would satisfy the positive arm alone. Do not edit the oracle
to make a failing derivation pass; a disagreement here is a finding about
the derivation, not license to adjust the oracle.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.generator import generate_chapter_manifest
from rpg2gba.traversal import (
    build_capability_map,
    build_map_graph,
    derive_blocked_verdict_for_event,
    extract_warp_exits,
)
from rpg2gba.traversal.collision import DEFAULT_MAPS_DIR, DEFAULT_TILESETS_JSON

ORACLE_PATH = Path("reference/frozen/ch05_surf_expectations.json")
CHAPTERS_PATH = Path("reference/chapters.json")
BUILD_DIR = Path("output/uranium-build")

MAP036_ID = 36
MAP037_ID = 37

pytestmark = pytest.mark.skipif(
    not ORACLE_PATH.is_file()
    or not (DEFAULT_MAPS_DIR / "Map035.json").is_file()
    or not (DEFAULT_MAPS_DIR / "Map036.json").is_file()
    or not (DEFAULT_MAPS_DIR / "Map037.json").is_file()
    or not DEFAULT_TILESETS_JSON.is_file(),
    reason="requires the frozen oracle and the decoded corpus under output/uranium-build/",
)


def _load_oracle() -> dict:
    return json.loads(ORACLE_PATH.read_text(encoding="utf-8"))


def _find_set(oracle: dict, map_id: int, arm: str) -> dict:
    for s in oracle["sets"]:
        if s["map_id"] == map_id and s["arm"] == arm:
            return s
    raise KeyError(f"no map_id={map_id!r}/arm={arm!r} set in {ORACLE_PATH}")


@pytest.fixture(scope="module")
def oracle() -> dict:
    return _load_oracle()


@pytest.fixture(scope="module")
def start_cell_36(oracle) -> tuple[int, int]:
    return tuple(oracle["start_cells"]["36"]["cell"])


@pytest.fixture(scope="module")
def start_cell_37(oracle) -> tuple[int, int]:
    return tuple(oracle["start_cells"]["37"]["cell"])


@pytest.fixture(scope="module")
def map036_graph():
    return build_map_graph(MAP036_ID)


@pytest.fixture(scope="module")
def map036_capabilities():
    return build_capability_map(MAP036_ID)


@pytest.fixture(scope="module")
def map037_graph():
    return build_map_graph(MAP037_ID)


@pytest.fixture(scope="module")
def map037_capabilities():
    return build_capability_map(MAP037_ID)


def test_map036_positive_arm_all_derive_blocked_surf(
    oracle, start_cell_36, map036_graph, map036_capabilities,
):
    """The four rows inside the sealed room (TM76 + Sableyeite item balls,
    p0/p1 each) must all derive as gated on surf and nothing else."""
    ch05 = _find_set(oracle, MAP036_ID, "positive")
    rows = ch05["rows"]
    assert len(rows) == ch05["expected_count"] == 4

    for row in rows:
        cell = tuple(row["event_cell"])
        verdict = derive_blocked_verdict_for_event(
            map036_graph, map036_capabilities, start_cell_36, cell, require_clearing=False,
        )
        assert verdict.as_disposition() == "blocked:surf", (
            f"{row['row_id']} at {cell}: expected 'blocked:surf', "
            f"got {verdict.as_disposition()!r}"
        )


def test_map036_negative_arm_all_other_events_stay_clear(
    oracle, start_cell_36, map036_graph, map036_capabilities,
):
    """The load-bearing check (per the oracle's own `provenance_honesty`
    note): every event on map 36 OUTSIDE the sealed room must NOT derive
    surf. This is what catches over-derivation -- a bug that marked the
    whole map surf-gated would pass the positive arm alone.

    "Does not require surf" is asserted as `reachable_now is True OR SURF
    is absent from every minimal set` rather than just checking the
    disposition string, because a cell could in principle be blocked by
    some other capability (or by nothing openable at all, i.e. plain
    geography) without that meaning surf is involved -- the oracle's claim
    is specifically about surf, not about full reachability. Checking the
    disposition string alone (`!= "blocked:surf"`) would also work here
    since none of these six events happen to be gated by anything else, but
    the minimal-sets check is the one that actually encodes what the oracle
    is claiming."""
    ch05 = _find_set(oracle, MAP036_ID, "negative")
    event_cells = ch05["event_cells_expected_clear"]
    assert len(event_cells) == len(ch05["event_ids_expected_clear"]) == 6

    # 11 page rows come from 6 events; per the oracle this is a per-event
    # cell check (page rows share their event's geometry, exactly as the
    # positive arm's p0/p1 pairs do), so 6 event derivations stand in for
    # the 11 rows. The expected_count assertion below still checks the
    # page-row total.
    checked = 0
    for event_id_str, cell in event_cells.items():
        assert int(event_id_str) in ch05["event_ids_expected_clear"]
        cell = tuple(cell)
        verdict = derive_blocked_verdict_for_event(
            map036_graph, map036_capabilities, start_cell_36, cell, require_clearing=False,
        )
        surf_in_any_minimal_set = any(
            "surf" in {c.value for c in minimal_set}
            for minimal_set in verdict.minimal_sets
        )
        assert verdict.reachable_now or not surf_in_any_minimal_set, (
            f"event {event_id_str} at {cell}: expected NOT gated on surf, "
            f"got {verdict.as_disposition()!r}"
        )
        checked += 1

    assert checked == 6
    # 6 events, each an item ball or NPC with exactly one or two page rows,
    # summing to the oracle's declared 11 page-row total.
    assert ch05["expected_count"] == 11


def test_map037_no_row_derives_surf(oracle, start_cell_37, map037_graph, map037_capabilities):
    """Map 37 has no surfable water at all; its only traversal constraint is
    the diagonal staircases, absorbed into terrain rows, not a capability.
    Check every event on the map, not just a sample."""
    ch05 = _find_set(oracle, MAP037_ID, "negative")
    assert ch05["expected_count"] == 0

    map037_json = json.loads((DEFAULT_MAPS_DIR / "Map037.json").read_text(encoding="utf-8"))
    events = map037_json.get("events", [])
    assert events, "map 37 has no events to check -- the negative claim would be vacuous"

    for event in events:
        cell = (event["x"], event["y"])
        verdict = derive_blocked_verdict_for_event(
            map037_graph, map037_capabilities, start_cell_37, cell, require_clearing=False,
        )
        surf_in_any_minimal_set = any(
            "surf" in {c.value for c in minimal_set}
            for minimal_set in verdict.minimal_sets
        )
        assert verdict.reachable_now or not surf_in_any_minimal_set, (
            f"map 37 event {event['id']} at {cell}: expected NOT gated on surf, "
            f"got {verdict.as_disposition()!r}"
        )


def test_ch05_manifest_carries_requires_surf_on_exactly_the_oracle_rows(oracle, tmp_path):
    """End-to-end through the real manifest generator: the four sealed-room
    rows carry `requires == ("surf",)`, no other row on CH05's maps does,
    and every row was generated with `reachability_consulted=True` (both
    CH05 maps have a registered start cell in
    `chapter_manifest/generator.py`'s `_CHAPTER_MAP_START_CELLS`)."""
    positive = _find_set(oracle, MAP036_ID, "positive")
    expected_surf_row_ids = {row["row_id"] for row in positive["rows"]}
    assert len(expected_surf_row_ids) == 4

    rows = generate_chapter_manifest(
        "CH05", build_dir=BUILD_DIR, chapters_path=CHAPTERS_PATH,
    )
    assert rows, "generate_chapter_manifest returned no rows for CH05"

    surf_row_ids = {row.row_id for row in rows if "surf" in row.requires}
    assert surf_row_ids == expected_surf_row_ids

    not_consulted = [row.row_id for row in rows if not row.reachability_consulted]
    assert not_consulted == [], (
        f"expected every CH05 row to have reachability_consulted=True "
        f"(both maps 36 and 37 have registered start cells); "
        f"rows without it: {not_consulted}"
    )


def test_oracle_start_cells_match_extract_warp_exits(oracle):
    """Guards the oracle itself against silent rot if the decoded corpus is
    regenerated differently: map 36's start cell must be the destination of
    the sole warp OUT of map 35, and map 37's must be the destination of the
    sole warp out of map 36 -- exactly as the oracle's own `start_cells`
    `source` fields claim."""
    assert oracle["expected_capability"] == "surf"

    map035_json = json.loads((DEFAULT_MAPS_DIR / "Map035.json").read_text(encoding="utf-8"))
    warps_from_35 = extract_warp_exits(map035_json)
    warps_to_36 = [w for w in warps_from_35 if w.dest_map == MAP036_ID]
    assert len(warps_to_36) == 1, (
        f"expected exactly one warp from map 35 into map 36, found {len(warps_to_36)}"
    )
    warp = warps_to_36[0]
    assert (warp.dest_x, warp.dest_y) == tuple(oracle["start_cells"]["36"]["cell"])

    map036_json = json.loads((DEFAULT_MAPS_DIR / "Map036.json").read_text(encoding="utf-8"))
    warps_from_36 = extract_warp_exits(map036_json)
    warps_to_37 = [w for w in warps_from_36 if w.dest_map == MAP037_ID]
    assert len(warps_to_37) == 1, (
        f"expected exactly one warp from map 36 into map 37, found {len(warps_to_37)}"
    )
    warp = warps_to_37[0]
    assert (warp.dest_x, warp.dest_y) == tuple(oracle["start_cells"]["37"]["cell"])
