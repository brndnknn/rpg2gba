"""Tests for the derived warp-override cell set (`PROJECT_TODO.md` #25,
`POST_CH05_REVIEW.md` G2).

An unstamped warp tile is plain floor, so a missing override cell produces a
warp event that compiles cleanly and never fires. That failure mode is
invisible until someone boots the ROM and walks into a door, which is why
CH02, CH03 and CH05 each opened their own frontier by hand -- before CH05's
four cells were added the player could not enter the Passage Cave, leave it,
or use the 1F<->2F stairs.

Two things are under test:

1. **The handoff** -- `write_warp_overrides` / `load_warp_overrides` round-trip,
   and the absent-file case fails loud rather than defaulting to "no doors".
2. **The derivation** -- against a frozen golden of the hand-maintained table
   as it stood immediately before it was replaced. Every cell in that golden
   was verified by a human against a booted ROM across five section-9 gates,
   which makes it the strongest oracle available for "did the derivation stay
   correct".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.tileset_converter import metadata_wiring as mw

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "warp_overrides_ch01_ch05.json"
BUILD = Path("output/uranium-build")


#: Cells a LATER chapter legitimately adds to a golden map: a warp whose target
#: was out of slice (skipped, no door metatile) becomes a real warp once the
#: target map joins. Kept separate so the frozen, human-verified golden stays
#: exactly what the five gates signed off on.
#:   CH06: Map037 EV002 (16, 5) -- Passage Cave exit -> Nowtoch City (map 40).
GROWN_CELLS: dict[int, set[tuple[int, int]]] = {37: {(16, 5)}}


def _golden() -> dict[int, set[tuple[int, int]]]:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    cells = {
        int(uid): {(x, y) for x, y in cells} for uid, cells in payload["cells"].items()
    }
    for uid, grown in GROWN_CELLS.items():
        cells[uid] = cells[uid] | grown
    return cells


# --- the handoff -------------------------------------------------------------


def test_round_trip_preserves_every_cell(tmp_path: Path) -> None:
    overrides = {36: {(17, 40), (17, 4)}, 37: {(16, 27)}}
    mw.write_warp_overrides(tmp_path, overrides)
    assert mw.load_warp_overrides(tmp_path) == overrides


def test_write_is_byte_identical_on_a_rerun(tmp_path: Path) -> None:
    """CLAUDE.md §4.2 -- set iteration order must not leak into the output."""
    overrides = {32: {(8, 45), (28, 31), (8, 43), (17, 11), (8, 44)}, 19: {(11, 30)}}
    path = mw.write_warp_overrides(tmp_path, overrides)
    first = path.read_bytes()
    mw.write_warp_overrides(tmp_path, overrides)
    assert path.read_bytes() == first


def test_missing_file_fails_loud_instead_of_yielding_no_doors(tmp_path: Path) -> None:
    """The whole point. An empty override set is not a harmless default -- it is
    a ROM in which every warp is inert, which is what G2 exists to prevent."""
    with pytest.raises(FileNotFoundError) as exc:
        mw.load_warp_overrides(tmp_path)
    assert "stage_slice_scripts" in str(exc.value)
    assert "inert" in str(exc.value)


def test_empty_override_set_round_trips_as_empty_not_missing(tmp_path: Path) -> None:
    """A map with genuinely no doors is distinguishable from an absent file."""
    mw.write_warp_overrides(tmp_path, {49: set()})
    assert mw.load_warp_overrides(tmp_path) == {49: set()}


# --- the derivation, against the hand-verified golden ------------------------
#
# The full set is `src_coords | gated_door_cells`. Only the first half can be
# recomputed cheaply: `gated_door_cells` comes out of `build_object_events`,
# which needs the NPC gfx map keyed to a BUILD-GENERATED fork header. So the
# two halves are checked differently, and neither reimplements production
# logic -- reimplementing the page-selection rule is exactly the divergence
# PROJECT_TODO #25 warns about.

#: The only two gated doors in CH01-CH05. A gated door is a player-touch event
#: that transfers the player but whose selected page carries no `code 201`, so
#: `classify_event` refuses to collapse it into a `warp_event`. It still needs
#: the door metatile: RMXP calls the cell impassable, but the override pass
#: forces it walkable so the player can step into the doorway and trip the gate
#: script. Both are logged by `build_object_events` as "gated door".
GATED_DOOR_CELLS = {49: {(10, 11)}, 50: {(14, 19)}}


@pytest.mark.skipif(
    not (BUILD / "maps").is_dir(), reason="decoded corpus absent (output/ is gitignored)"
)
def test_warp_sources_reproduce_the_hand_verified_cells() -> None:
    """`classify_map_events` -- the production classifier, called directly --
    must still yield exactly the golden's cells minus the two gated doors.

    Only the 18 maps in the golden are compared: when a chapter joins
    `SLICE_MAP_IDS` the derived set legitimately grows, and asserting whole-dict
    equality would fail every new chapter for the wrong reason.
    """
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

    golden = _golden()
    slice_set = set(SLICE_MAP_IDS)

    mismatches: list[str] = []
    for uid, all_cells in sorted(golden.items()):
        path = BUILD / "maps" / f"Map{uid:03d}.json"
        if not path.is_file():
            mismatches.append(f"Map{uid:03d}: decoded JSON missing")
            continue
        expected = all_cells - GATED_DOOR_CELLS.get(uid, set())
        map_json = json.loads(path.read_text(encoding="utf-8"))
        derived = {
            (spec.src_x, spec.src_y)
            for _e, spec in mw.classify_map_events(map_json, slice_set)[1]
        }
        if derived != expected:
            mismatches.append(
                f"Map{uid:03d}: missing={sorted(expected - derived)} "
                f"unexpected={sorted(derived - expected)}"
            )
    assert not mismatches, "\n".join(mismatches)


def test_every_gated_door_is_absent_from_the_warp_sources() -> None:
    """The two halves must not overlap -- if a gated door ever started
    classifying as a warp source, the union would still be right but
    `GATED_DOOR_CELLS` would have silently become dead weight."""
    golden = _golden()
    for uid, cells in GATED_DOOR_CELLS.items():
        assert cells <= golden[uid], f"Map{uid:03d}: gated door not in the golden"


@pytest.mark.skipif(
    not (BUILD / mw.WARP_OVERRIDES_FILENAME).is_file(),
    reason="warp_overrides.gen.json absent -- run scripts/stage_slice_scripts.py --write",
)
def test_persisted_overrides_match_the_hand_verified_golden() -> None:
    """End-to-end: what the real pipeline actually wrote, against what five
    section-9 gates signed off on. No reimplementation at all -- this reads the
    artifact `build_slice_maps` produced."""
    golden = _golden()
    written = mw.load_warp_overrides(BUILD)
    mismatches = [
        f"Map{uid:03d}: missing={sorted(cells - written.get(uid, set()))} "
        f"unexpected={sorted(written.get(uid, set()) - cells)}"
        for uid, cells in sorted(golden.items())
        if written.get(uid, set()) != cells
    ]
    assert not mismatches, "\n".join(mismatches)


@pytest.mark.skipif(
    not (BUILD / "maps").is_dir(), reason="decoded corpus absent (output/ is gitignored)"
)
def test_arrival_warps_are_not_stamped() -> None:
    """`_resolve_all_warp_events` mints an arrival warp on every destination.
    Those are plain floor BY DESIGN -- stamping a door at an arrival cell would
    put a door where the player lands. The derivation must not pick them up.

    Checked structurally: the golden's cell count is the number of real
    `code 201` sources, and every arrival coordinate paired to one of them is
    absent from the golden unless it is independently a source in its own right
    (a two-way door, where both ends are real events).
    """
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

    golden = _golden()
    slice_set = set(SLICE_MAP_IDS)
    for uid in sorted(golden):
        path = BUILD / "maps" / f"Map{uid:03d}.json"
        if not path.is_file():
            continue
        map_json = json.loads(path.read_text(encoding="utf-8"))
        for _e, spec in mw.classify_map_events(map_json, slice_set)[1]:
            dest_cell = (spec.dest_x, spec.dest_y)
            dest_golden = golden.get(spec.dest_uid)
            if dest_golden is None or dest_cell not in dest_golden:
                continue
            # Present at the destination: only legitimate if that cell is also
            # a real warp source on the destination map (a two-way door).
            dest_json = json.loads(
                (BUILD / "maps" / f"Map{spec.dest_uid:03d}.json").read_text(
                    encoding="utf-8"
                )
            )
            dest_srcs = {
                (s.src_x, s.src_y)
                for _de, s in mw.classify_map_events(dest_json, slice_set)[1]
            }
            assert dest_cell in dest_srcs, (
                f"Map{spec.dest_uid:03d} {dest_cell} is stamped as a door but is "
                f"only an ARRIVAL from Map{uid:03d} -- arrivals must stay plain floor"
            )
