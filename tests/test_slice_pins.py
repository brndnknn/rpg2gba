"""Tests for `rpg2gba.slice_pins` -- the pinned-list completeness check.

`POST_CH05_REVIEW.md` G1: four lists must move together when a chapter joins
`SLICE_MAP_IDS` and until 2026-09-08 exactly one was guarded. The behaviour
under test is not just "does it notice" but **"does it report everything at
once"** -- the one-at-a-time discovery is what cost CH05 a full loop, so a
check that stops at the first gap would not fix the actual problem.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba import slice_pins
from rpg2gba.slice_pins import PinnedListError, PinReport, TrainerEventRef

BUILD = Path("output/uranium-build")


# --- emitted_trainer_constants -----------------------------------------------


def _pory(tmp_path: Path, map_id: int, body: str) -> Path:
    d = tmp_path / "scripts"
    d.mkdir(exist_ok=True)
    (d / f"Map{map_id:03d}.pory").write_text(body, encoding="utf-8")
    return d


def test_emitted_picks_up_every_trainerbattle_form(tmp_path: Path) -> None:
    scripts = _pory(
        tmp_path,
        19,
        "script A {\n"
        "  trainerbattle_single(TRAINER_LOU_136, T1, T2)\n"
        "  trainerbattle_no_intro(TRAINER_MAWULI_90, T3)\n"
        "  trainerbattle_double(TRAINER_ABE_GAYLE_166, T4, T5, T6)\n"
        "}\n",
    )
    found = slice_pins.emitted_trainer_constants(scripts, [19])
    assert set(found) == {"TRAINER_LOU_136", "TRAINER_MAWULI_90", "TRAINER_ABE_GAYLE_166"}
    assert found["TRAINER_LOU_136"] == [19]


def test_emitted_ignores_a_queued_unhandled_comment(tmp_path: Path) -> None:
    """A trainer whose battle is still in the `# UNHANDLED` queue is not
    emitted, so it must not be treated as a build risk -- this is exactly the
    Map019 biker case that would otherwise be a false positive."""
    scripts = _pory(
        tmp_path,
        19,
        "script A {\n"
        "  # UNHANDLED code 111: conditional on script: "
        'pbTrainerBattle(PBTrainers::BIKER,"Lou",_I("Owww!"),false,0,false,0)\n'
        "}\n",
    )
    assert slice_pins.emitted_trainer_constants(scripts, [19]) == {}


def test_emitted_skips_maps_with_no_pory_on_disk(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    assert slice_pins.emitted_trainer_constants(tmp_path / "scripts", [19, 33]) == {}


def test_emitted_records_every_map_that_emits_a_shared_constant(tmp_path: Path) -> None:
    _pory(tmp_path, 19, "trainerbattle_single(TRAINER_LOU_136, A, B)")
    _pory(tmp_path, 33, "trainerbattle_single(TRAINER_LOU_136, A, B)")
    found = slice_pins.emitted_trainer_constants(tmp_path / "scripts", [19, 33])
    assert found["TRAINER_LOU_136"] == [19, 33]


# --- TrainerEventRef.status --------------------------------------------------


def _ref(**kw) -> TrainerEventRef:
    base = dict(
        map_id=19,
        event_id=4,
        trainer_constant="TRAINER_LOU_136",
        trainer_class_constant="TRAINER_CLASS_BIKER",
        display_name="Lou",
        kind="sight",
        emitted=False,
        pinned=False,
    )
    base.update(kw)
    return TrainerEventRef(**base)


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"emitted": True, "pinned": True}, "ok"),
        ({"emitted": True, "pinned": False}, "MISSING_PIN"),
        ({"emitted": False, "pinned": True}, "pinned-not-emitted"),
        ({"emitted": False, "pinned": False}, "queued-not-pinned"),
        ({"trainer_constant": None}, "unresolved"),
    ],
)
def test_status_covers_every_combination(kwargs: dict, expected: str) -> None:
    assert _ref(**kwargs).status == expected


# --- error classification: the batching that makes this worth having ---------


def test_every_gap_class_is_filed_under_the_list_that_has_to_be_edited() -> None:
    """One staging run's collected errors must fan out into per-list buckets --
    a human fixing this edits four different files, and a flat blob makes them
    work out which line goes where."""
    report = PinReport()
    for msg in (
        "- TRAINER_A_1: TRAINER_CLASS_BIKER (display name 'BIKER') resolves to "
        "TRAINER_CLASS_BIKER, which is not a TRAINER_CLASS_* constant the fork defines "
        "-- verify include/constants/trainers.h, do not invent one",
        "- TRAINER_B_2: TRAINER_CLASS_NINJABOY: no pic mapping -- "
        "_CLASS_PIC_INTERNAL_NAME must be extended before this class can be staged",
        "- TRAINER_C_3: TRAINER_CLASS_SAILOR: no encounter-music mapping -- "
        "_CLASS_ENCOUNTER_MUSIC must be extended",
        "- TRAINER_D_4: TRAINER_CLASS_HIKER: pic internal_name 'HIKER' is not staged "
        "in common.SLICE_TRAINER_PICS -- append TrainerPicSpec(4, 'HIKER') there first",
        "- TRAINER_E_5: species not available (neither in the fork nor in the staged "
        "species overlay): SPECIES_GROZARD, SPECIES_TERLARD",
    ):
        slice_pins._classify_staging_error(msg, report)

    assert len(report.unmapped_classes) == 3  # fork-absent + pic + music
    assert report.missing_pics == ["TrainerPicSpec(4, 'HIKER')"]
    assert report.missing_species == ["SPECIES_GROZARD", "SPECIES_TERLARD"]
    assert report.other == []
    assert not report.ok


def test_an_unrecognised_error_is_reported_not_dropped() -> None:
    """Falling through to `other` matters: silently discarding an error we
    can't categorise would be the §4.5 failure this module exists to prevent."""
    report = PinReport()
    slice_pins._classify_staging_error("- TRAINER_X_9: something entirely new", report)
    assert report.other == ["- TRAINER_X_9: something entirely new"]
    assert not report.ok


def test_report_format_names_all_four_lists_when_all_four_are_short() -> None:
    report = PinReport(
        missing_battles=["TRAINER_LOU_136  (emitted by Map019)"],
        missing_pics=["BIKER"],
        missing_species=["SPECIES_GROZARD"],
        unmapped_classes=["- TRAINER_LOU_136: TRAINER_CLASS_BIKER: no pic mapping"],
    )
    text = report.format()
    for expected in (
        "SLICE_TRAINER_BATTLES",
        "SLICE_TRAINER_PICS",
        "STARTER_SPECIES",
        "_CLASS_ENCOUNTER_MUSIC",
        "TRAINER_LOU_136",
        "SPECIES_GROZARD",
    ):
        assert expected in text, expected
    # The append-only rule is load-bearing: fork trainer ids are positional.
    assert "append, never reorder" in text


def test_empty_report_is_ok_and_formats_to_nothing() -> None:
    report = PinReport()
    assert report.ok
    assert report.format() == ""


# --- preconditions: an absent input must not read as "no gaps" ---------------


def test_missing_maps_dir_raises_rather_than_reporting_clean(tmp_path: Path) -> None:
    with pytest.raises(PinnedListError, match="does not exist"):
        slice_pins.check_pinned_lists(out_dir=tmp_path, engine_dir=tmp_path)


def test_missing_species_manifest_raises_rather_than_flagging_every_species(
    tmp_path: Path,
) -> None:
    """An absent species manifest makes every party species read as unstaged.
    Over-reporting is fail-safe but useless -- the real gaps get buried."""
    (tmp_path / "maps").mkdir()
    with pytest.raises(PinnedListError, match="stage_species"):
        slice_pins.check_pinned_lists(out_dir=tmp_path, engine_dir=tmp_path)


# --- census ------------------------------------------------------------------


class _Ctx:
    def __init__(self, trainers: dict) -> None:
        self.trainers = trainers


def _trainer_event(event_id: int, class_sym: str, name: str) -> dict:
    call = f'pbTrainerBattle(PBTrainers::{class_sym},"{name}",_I("ow"),false,0,false,0)'
    return {
        "id": event_id,
        "pages": [{"list": [{"code": 111, "parameters": [12, call]}]}],
    }


def test_census_reports_a_queued_trainer_without_making_it_an_error(tmp_path: Path) -> None:
    maps = tmp_path / "maps"
    maps.mkdir()
    (maps / "Map019.json").write_text(
        json.dumps({"events": [_trainer_event(4, "BIKER", "Lou")]}), encoding="utf-8"
    )
    ctx = _Ctx({("TRAINER_CLASS_BIKER", "Lou", 0): "TRAINER_LOU_136"})
    refs = slice_pins.census_trainer_events(
        maps, [19], ctx, emitted={}, pinned=frozenset()
    )
    assert len(refs) == 1
    assert refs[0].trainer_constant == "TRAINER_LOU_136"
    assert refs[0].status == "queued-not-pinned"


def test_census_flags_an_emitted_but_unpinned_trainer(tmp_path: Path) -> None:
    maps = tmp_path / "maps"
    maps.mkdir()
    (maps / "Map019.json").write_text(
        json.dumps({"events": [_trainer_event(4, "BIKER", "Lou")]}), encoding="utf-8"
    )
    ctx = _Ctx({("TRAINER_CLASS_BIKER", "Lou", 0): "TRAINER_LOU_136"})
    refs = slice_pins.census_trainer_events(
        maps, [19], ctx, emitted={"TRAINER_LOU_136": [19]}, pinned=frozenset()
    )
    assert refs[0].status == "MISSING_PIN"


def test_census_keeps_an_event_whose_trainer_does_not_resolve(tmp_path: Path) -> None:
    """Map050's Theo event resolves to no single key (which rival battle fires
    depends on the starter). It must still appear, as `unresolved` -- dropping
    it would hide a real event from the census."""
    maps = tmp_path / "maps"
    maps.mkdir()
    (maps / "Map050.json").write_text(
        json.dumps({"events": [_trainer_event(19, "RIVAL", "Theo")]}), encoding="utf-8"
    )
    refs = slice_pins.census_trainer_events(
        maps, [50], _Ctx({}), emitted={}, pinned=frozenset()
    )
    assert len(refs) == 1
    assert refs[0].trainer_constant is None
    assert refs[0].status == "unresolved"


# --- integration against the real corpus (gitignored, so skipped in CI) ------


@pytest.mark.skipif(
    not (BUILD / "maps").is_dir() or not (BUILD / "species" / "species_manifest.json").is_file(),
    reason="on-disk corpus absent (output/ is gitignored)",
)
def test_current_slice_has_no_unpinned_emitted_trainer() -> None:
    """The gate, against the real tree. CH05 is gate-passed, so this is green;
    it turns red the moment a chapter adds a trainer nobody pinned."""
    import os

    from rpg2gba.pipeline import _load_dotenv

    _load_dotenv()
    engine = os.environ.get("RPG2GBA_POKEEMERALD")
    if not engine or not Path(engine).is_dir():
        pytest.skip("engine tree not resolvable")
    report = slice_pins.check_pinned_lists(out_dir=BUILD, engine_dir=Path(engine))
    assert report.missing_battles == [], report.format()
    assert report.ok, report.format()
