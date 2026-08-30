"""Regression test that reproduces the frozen slice-2 `blocked:<capability>`
validation recorded in `reference/frozen/slice2_derivation_diff.md` against
the frozen oracle `reference/frozen/slice2_blocked_expectations.json`.

That validation was originally run from an ad-hoc throwaway script that no
longer exists -- nothing committed re-ran it, so the project's own validation
artifact was unverifiable and would silently rot the first time the
derivation changed. This test is the committed replacement.

`slice2_blocked_expectations.json` is a FROZEN ORACLE, authored before this
derivation code existed. It must never be edited to make this test pass --
see the file's own `rule` field. A disagreement here is a finding about the
derivation, not license to adjust the oracle.

Two sets, per the diff document:

* CH04 (map 35, start (21, 56), the Kevlar seam arrival): 28 manifest rows.
  24 derive `blocked:rock_smash` (their *approach* is gated -- this is the
  reachability half of the two-source disposition structure the diff
  document describes). The other 4 (`map035/ev014/p0`, `ev014/p1`,
  `ev017/p0`, `ev017/p1`) derive as reachable now -- their gate is the
  script head `Kernel.pbRockSmash`, not the approach, so this reachability
  pass correctly does NOT call them blocked.

* CH02 (map 33, start (70, 11), the Moki Town warp arrival): 10 beats, each
  an explicit `map_id`/`cell` pair. The diff document frames this half as a
  beat -> cell containment check (CH02 has no `.dispositions.json` the way
  CH04 does), not a row-level diff. All 10 derive `blocked:rock_smash`.
  Every beat cell is treated as an event site (approached from an adjacent
  tile, never stood on directly) via `derive_blocked_verdict_for_event` --
  this matches how the CH04 event rows are derived, and is required for at
  least one beat (Gertha, B10 at (25, 37)): that cell itself is not walkable
  per the collision graph (an NPC occupies it), so a bare-cell
  `derive_blocked_verdict` against it is a geography dead end regardless of
  capability, not the rock-smash gate the beat is actually recording.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rpg2gba.traversal import build_capability_map, build_map_graph, derive_blocked_verdict_for_event
from rpg2gba.traversal.collision import DEFAULT_MAPS_DIR, DEFAULT_TILESETS_JSON

ORACLE_PATH = Path("reference/frozen/slice2_blocked_expectations.json")

CH04_START = (21, 56)
CH04_MAP_ID = 35
CH02_START = (70, 11)
CH02_MAP_ID = 33

# The 4 rows whose gate is the event's own script head (Kernel.pbRockSmash),
# not the approach -- these derive as reachable, per the diff document.
CH04_APPROACH_REACHABLE_ROW_IDS = frozenset(
    {"map035/ev014/p0", "map035/ev014/p1", "map035/ev017/p0", "map035/ev017/p1"}
)

_ROW_ID_EVENT_RE = re.compile(r"^map035/ev(\d+)/p\d+$")

pytestmark = pytest.mark.skipif(
    not ORACLE_PATH.is_file()
    or not (DEFAULT_MAPS_DIR / "Map033.json").is_file()
    or not (DEFAULT_MAPS_DIR / "Map035.json").is_file()
    or not DEFAULT_TILESETS_JSON.is_file(),
    reason="requires the frozen oracle and the decoded corpus under output/uranium-build/",
)


def _load_oracle() -> dict:
    return json.loads(ORACLE_PATH.read_text(encoding="utf-8"))


def _find_set(oracle: dict, chapter: str) -> dict:
    for s in oracle["sets"]:
        if s["chapter"] == chapter:
            return s
    raise KeyError(f"no {chapter!r} set in {ORACLE_PATH}")


def _event_cell(map_json: dict, event_id: int) -> tuple[int, int]:
    for event in map_json.get("events", []):
        if event["id"] == event_id:
            return (event["x"], event["y"])
    raise KeyError(f"map 35 has no event id {event_id}")


@pytest.fixture(scope="module")
def oracle() -> dict:
    return _load_oracle()


@pytest.fixture(scope="module")
def map035_json() -> dict:
    return json.loads((DEFAULT_MAPS_DIR / "Map035.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def map035_graph():
    return build_map_graph(CH04_MAP_ID)


@pytest.fixture(scope="module")
def map035_capabilities():
    return build_capability_map(CH04_MAP_ID)


@pytest.fixture(scope="module")
def map033_graph():
    return build_map_graph(CH02_MAP_ID)


@pytest.fixture(scope="module")
def map033_capabilities():
    return build_capability_map(CH02_MAP_ID)


def test_ch04_manifest_rows_split_24_blocked_4_reachable(
    oracle, map035_json, map035_graph, map035_capabilities,
):
    ch04 = _find_set(oracle, "CH04")
    rows = ch04["rows"]
    assert len(rows) == ch04["expected_count"] == 28

    blocked_row_ids: list[str] = []
    reachable_row_ids: list[str] = []

    for row in rows:
        row_id = row["row_id"]
        if row_id == "map035/seam/N/map040":
            continue  # handled separately below -- not an event, no per-row cell
        m = _ROW_ID_EVENT_RE.match(row_id)
        assert m is not None, f"unrecognized row_id shape: {row_id!r}"
        event_id = int(m.group(1))
        cell = _event_cell(map035_json, event_id)

        verdict = derive_blocked_verdict_for_event(
            map035_graph, map035_capabilities, CH04_START, cell,
        )

        if row_id in CH04_APPROACH_REACHABLE_ROW_IDS:
            assert verdict.reachable_now is True, (
                f"{row_id} (event {event_id} at {cell}): expected the approach to be "
                f"reachable now (gate is the script head, not geography), got "
                f"{verdict.as_disposition()!r}"
            )
            reachable_row_ids.append(row_id)
        else:
            assert verdict.as_disposition() == "blocked:rock_smash", (
                f"{row_id} (event {event_id} at {cell}): expected 'blocked:rock_smash', "
                f"got {verdict.as_disposition()!r}"
            )
            blocked_row_ids.append(row_id)

    # The seam row: not an event, so there is no single canonical cell. Per
    # the diff document, the north seam "becomes usable in CH07" once the
    # rocks are cleared -- i.e. at least one walkable row-0 cell must be
    # gated on rock_smash (not reachable now, and not a plain geography dead
    # end), and none may be reachable with nothing held.
    seam_row = next(r for r in rows if r["row_id"] == "map035/seam/N/map040")
    assert seam_row["current_disposition"] == "unreachable:rockslide_blocks_north_seam"

    row0_cells = [(x, 0) for x in range(map035_graph.width) if map035_graph.is_walkable((x, 0))]
    assert row0_cells, "map 35 has no walkable cell on row y=0 to test the north seam against"

    seam_dispositions = {
        cell: derive_blocked_verdict_for_event(
            map035_graph, map035_capabilities, CH04_START, cell,
        ).as_disposition()
        for cell in row0_cells
    }
    assert not any(d == "" for d in seam_dispositions.values()), (
        f"row y=0 has a cell reachable with nothing held -- contradicts the oracle's "
        f"'not in the south-reachable set': {seam_dispositions}"
    )
    assert any(d == "blocked:rock_smash" for d in seam_dispositions.values()), (
        f"expected at least one row-0 cell gated on rock_smash (the north seam becomes "
        f"usable once rocks are cleared, per the oracle note); got {seam_dispositions}"
    )
    blocked_row_ids.append(seam_row["row_id"])

    assert len(blocked_row_ids) == 24, blocked_row_ids
    assert len(reachable_row_ids) == 4, reachable_row_ids
    assert set(reachable_row_ids) == CH04_APPROACH_REACHABLE_ROW_IDS


def test_ch02_beats_all_gated_on_rock_smash(oracle, map033_graph, map033_capabilities):
    ch02 = _find_set(oracle, "CH02")
    beats = ch02["beats"]
    assert len(beats) == ch02["expected_count"] == 10

    for beat in beats:
        assert beat["map_id"] == CH02_MAP_ID
        cell = tuple(beat["cell"])
        verdict = derive_blocked_verdict_for_event(
            map033_graph, map033_capabilities, CH02_START, cell,
        )
        assert verdict.as_disposition() == "blocked:rock_smash", (
            f"beat {beat['beat_id']} at {cell}: expected 'blocked:rock_smash', "
            f"got {verdict.as_disposition()!r}"
        )
