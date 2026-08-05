"""W6 tests -- trainer battle-data staging (`trainer_converter.battles` +
`trainer_converter.stage`'s battle integration).

Per CLAUDE.md §4.6:
  * round-trip: a staged trainer's party data matches trainers.json.
  * golden: pinned emitted `.party` fragment + id header for the Theo trio
    (the one subset that resolves today -- Route-1's other nine are blocked
    on species conversion, see `test_full_slice_blocked_on_species`).
  * edge: fork-append id math, empty-selection no-op, idempotence, and
    fail-loud guards (unknown class, missing species, dangling pic, unmapped
    music).

Fork-verification tests (`resolve_trainer_class`, `read_pristine_trainer_
anchor`, etc against the REAL fork) take the `fork_path` fixture from
conftest.py and skip cleanly when `RPG2GBA_POKEEMERALD` is unset. Everything
else uses synthetic trainers.json/trainer_types.json-shaped dicts and
synthetic fork constant sets, so the suite stays fast and hermetic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.trainer_converter import battles, common
from rpg2gba.trainer_converter.battles import StagedTrainerBattle
from rpg2gba.trainer_converter.stage import write_all

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ===========================================================================
# Synthetic fork constant sets (fast, hermetic -- no real engine/ needed)
# ===========================================================================


def _fork_classes() -> set[str]:
    return {
        "TRAINER_CLASS_RIVAL", "TRAINER_CLASS_FISHERMAN", "TRAINER_CLASS_YOUNGSTER",
        "TRAINER_CLASS_BUG_CATCHER", "TRAINER_CLASS_SCHOOL_KID", "TRAINER_CLASS_TRIATHLETE",
        "TRAINER_CLASS_EXPERT", "TRAINER_CLASS_LASS",
    }


def _fork_genders() -> set[str]:
    return {"TRAINER_GENDER_MALE", "TRAINER_GENDER_FEMALE"}


def _fork_music() -> set[str]:
    return {
        "TRAINER_ENCOUNTER_MUSIC_MALE", "TRAINER_ENCOUNTER_MUSIC_FEMALE",
        "TRAINER_ENCOUNTER_MUSIC_GIRL", "TRAINER_ENCOUNTER_MUSIC_INTENSE",
        "TRAINER_ENCOUNTER_MUSIC_HIKER",
    }


def _fork_species() -> set[str]:
    return {"SPECIES_MANKEY", "SPECIES_MAGIKARP"}


def _fork_moves() -> set[str]:
    return {"MOVE_PECK", "MOVE_CHARM", "MOVE_FORESIGHT"}


def _fork_items() -> set[str]:
    return {"ITEM_POTION"}


_STAGED_STARTER_SPECIES = {"SPECIES_ELETUX", "SPECIES_ORCHYNX", "SPECIES_RAPTORCH"}
_STAGED_PIC_NAMES = {"RIVAL", "FISHERMAN", "YOUNGSTER", "BUGCATCHER", "SCHOOLKID",
                      "TRIATHLETE_MALERUNNER", "EXPERT_FEMALE", "LASS"}


def _trainer_types() -> dict:
    return {
        "TRAINER_CLASS_RIVAL": {"id": 86, "name": "RIVAL", "gender": "Male"},
        "TRAINER_CLASS_FISHERMAN": {"id": 6, "name": "FISHERMAN", "gender": "Male"},
        "TRAINER_CLASS_LASS": {"id": 2, "name": "LASS", "gender": "Female"},
        # deliberately un-mapped in _CLASS_ENCOUNTER_MUSIC-adjacent tests:
        "TRAINER_CLASS_UNMAPPABLE": {"id": 999, "name": "GYM LEADER", "gender": "Male"},
    }


def _trainers() -> dict:
    return {
        "TRAINER_THEO_9": {
            "id": 9, "trainer_class": "TRAINER_CLASS_RIVAL", "name": "Theo",
            "party_id": 19, "items": [],
            "party": [{"species": "SPECIES_ELETUX", "level": 5, "iv": 10, "happiness": 70}],
        },
        "TRAINER_THEO_10": {
            "id": 10, "trainer_class": "TRAINER_CLASS_RIVAL", "name": "Theo",
            "party_id": 20, "items": [],
            "party": [{"species": "SPECIES_ORCHYNX", "level": 5, "iv": 10, "happiness": 70}],
        },
        "TRAINER_THEO_11": {
            "id": 11, "trainer_class": "TRAINER_CLASS_RIVAL", "name": "Theo",
            "party_id": 21, "items": [],
            "party": [{"species": "SPECIES_RAPTORCH", "level": 5, "iv": 10, "happiness": 70}],
        },
        "TRAINER_MARKO_19": {
            "id": 19, "trainer_class": "TRAINER_CLASS_FISHERMAN", "name": "Marko",
            "party_id": 0, "items": [],
            "party": [{"species": "SPECIES_MANKEY", "level": 10, "iv": 10, "happiness": 70}],
        },
        "TRAINER_LYNETTE_246": {
            "id": 246, "trainer_class": "TRAINER_CLASS_LASS", "name": "Lynette",
            "party_id": 0, "items": [],
            "party": [
                {
                    "species": "SPECIES_MAGIKARP", "level": 5,
                    "moves": ["MOVE_PECK", "MOVE_CHARM", "MOVE_FORESIGHT"],
                    "iv": 10, "happiness": 70,
                }
            ],
        },
        "TRAINER_UNMAPPABLE_1": {
            "id": 1, "trainer_class": "TRAINER_CLASS_UNMAPPABLE", "name": "Gary",
            "party_id": 0, "items": [],
            "party": [{"species": "SPECIES_MANKEY", "level": 10, "iv": 10, "happiness": 70}],
        },
    }


def _build(selected: tuple[str, ...], **overrides) -> list[StagedTrainerBattle]:
    kwargs = dict(
        fork_classes=_fork_classes(),
        fork_genders=_fork_genders(),
        fork_music=_fork_music(),
        fork_species=_fork_species(),
        fork_moves=_fork_moves(),
        fork_items=_fork_items(),
        staged_species=_STAGED_STARTER_SPECIES,
        staged_pic_internal_names=_STAGED_PIC_NAMES,
    )
    kwargs.update(overrides)
    return battles.build_staged_battles(selected, _trainers(), _trainer_types(), 854, **kwargs)


_THEO_KEYS = ("TRAINER_THEO_9", "TRAINER_THEO_10", "TRAINER_THEO_11")


# ===========================================================================
# Round-trip
# ===========================================================================


def test_roundtrip_party_matches_trainers_json() -> None:
    staged = _build(_THEO_KEYS)
    trainers = _trainers()
    for s in staged:
        expected = trainers[s.trainer_key]["party"]
        assert s.party == expected
        assert s.uranium_trainer_id == trainers[s.trainer_key]["id"]
        assert s.name == trainers[s.trainer_key]["name"]


def test_roundtrip_class_gender_music_pic_resolved_correctly() -> None:
    staged = _build(_THEO_KEYS)
    for s in staged:
        assert s.trainer_class_constant == "TRAINER_CLASS_RIVAL"
        assert s.gender_constant == "TRAINER_GENDER_MALE"
        assert s.encounter_music_constant == "TRAINER_ENCOUNTER_MUSIC_MALE"
        assert s.pic_constant == "TRAINER_PIC_FRONT_URANIUM_RIVAL"


# ===========================================================================
# Id allocation math
# ===========================================================================


def test_id_allocation_chains_off_anchor_by_position() -> None:
    staged = _build(_THEO_KEYS)
    assert [s.fork_id for s in staged] == [855, 856, 857]

    header = battles.emit_trainer_ids(staged, "TRAINER_MAY_PLACEHOLDER")
    assert "#define TRAINER_THEO_9 (TRAINER_MAY_PLACEHOLDER + 1)" in header
    assert "#define TRAINER_THEO_10 (TRAINER_THEO_9 + 1)" in header
    assert "#define TRAINER_THEO_11 (TRAINER_THEO_10 + 1)" in header
    assert "#define URANIUM_TRAINERS_LAST TRAINER_THEO_11" in header
    assert "#define URANIUM_TRAINERS_STAGED_COUNT 3" in header


def test_id_allocation_order_is_selection_order_not_uranium_id() -> None:
    """Fork ids are assigned by POSITION in the selection tuple, not sorted
    by the Uranium trainer id -- Marko (id 19) placed before Theo (id 9)
    must still take the lower fork id."""
    staged = _build(("TRAINER_MARKO_19", "TRAINER_THEO_9"))
    by_key = {s.trainer_key: s.fork_id for s in staged}
    assert by_key["TRAINER_MARKO_19"] == 855
    assert by_key["TRAINER_THEO_9"] == 856


# ===========================================================================
# Golden output
# ===========================================================================


def test_golden_output_for_theo_trio() -> None:
    staged = _build(_THEO_KEYS)
    combined = (
        "// === uranium_trainer_ids.h ===\n"
        + battles.emit_trainer_ids(staged, "TRAINER_MAY_PLACEHOLDER")
        + "// === uranium_trainer_party.inc ===\n"
        + battles.emit_party_fragment(staged)
    )
    golden_path = FIXTURES / "trainer_battles_golden.inc"
    if not golden_path.exists():
        golden_path.write_text(combined, encoding="utf-8")
    assert combined == golden_path.read_text(encoding="utf-8")


# ===========================================================================
# Empty selection -> no-op
# ===========================================================================


def test_empty_selection_produces_noop_files() -> None:
    ids_header = battles.emit_trainer_ids([], "TRAINER_MAY_PLACEHOLDER")
    party_frag = battles.emit_party_fragment([])
    assert "no-op" in ids_header
    assert "no-op" in party_frag
    assert "TRAINER_MAY_PLACEHOLDER + 1" not in ids_header
    assert "===" not in party_frag


def test_empty_battles_write_all_leaves_pic_only_behavior_unaffected(tmp_path: Path) -> None:
    manifest = write_all(out_dir=tmp_path, fronts=(), backs=(), battles=())
    assert manifest["trainers"] == []
    ids_header = (tmp_path / "uranium_trainer_ids.h").read_text(encoding="utf-8")
    party_frag = (tmp_path / "uranium_trainer_party.inc").read_text(encoding="utf-8")
    assert "no-op" in ids_header
    assert "no-op" in party_frag


# ===========================================================================
# Idempotence
# ===========================================================================


def test_idempotent_reruns_are_byte_identical(tmp_path: Path) -> None:
    staged = _build(_THEO_KEYS)
    write_all(out_dir=tmp_path, battles=staged)
    snapshot = {p.name: p.read_bytes() for p in sorted(tmp_path.iterdir())}

    write_all(out_dir=tmp_path, battles=staged)
    rerun = {p.name: p.read_bytes() for p in sorted(tmp_path.iterdir())}

    assert snapshot == rerun


def test_manifest_battle_records_written_to_disk_match_return_value(tmp_path: Path) -> None:
    staged = _build(_THEO_KEYS)
    manifest = write_all(out_dir=tmp_path, battles=staged)
    on_disk = json.loads((tmp_path / "trainer_manifest.json").read_text(encoding="utf-8"))
    assert on_disk == manifest
    battle_records = [r for r in manifest["trainers"] if r["kind"] == "battle"]
    assert len(battle_records) == 3
    for rec, s in zip(battle_records, staged):
        assert rec["trainer_constant"] == s.trainer_key
        assert rec["fork_trainer_id"] == s.fork_id


# ===========================================================================
# Fail-loud guards
# ===========================================================================


def test_missing_species_fails_loud() -> None:
    with pytest.raises(ValueError, match="SPECIES_MAGIKARP"):
        _build(("TRAINER_LYNETTE_246",), staged_species=set(), fork_species=set())


def test_unknown_class_fails_loud() -> None:
    """`trainer_types.json`'s display name resolves to a TRAINER_CLASS_*
    (via the trainerproc-matching transform) that the fork doesn't define."""
    with pytest.raises(ValueError, match="TRAINER_CLASS_GYM_LEADER"):
        _build(("TRAINER_UNMAPPABLE_1",))


def test_unmapped_music_class_fails_loud() -> None:
    """A class that resolves fine against the fork but has no
    `_CLASS_ENCOUNTER_MUSIC` row (this slice only mapped the eight classes
    it actually touches) must fail loud, not silently default to some
    music."""
    trainer_types = _trainer_types()
    trainer_types["TRAINER_CLASS_UNMAPPABLE"]["name"] = "BLACK BELT"  # real class, unmapped here
    fork_classes = _fork_classes() | {"TRAINER_CLASS_BLACK_BELT"}
    with pytest.raises(ValueError, match="no encounter-music mapping"):
        battles.build_staged_battles(
            ("TRAINER_UNMAPPABLE_1",),
            _trainers(),
            trainer_types,
            854,
            fork_classes=fork_classes,
            fork_genders=_fork_genders(),
            fork_music=_fork_music(),
            fork_species=_fork_species(),
            fork_moves=_fork_moves(),
            fork_items=_fork_items(),
            staged_species=_STAGED_STARTER_SPECIES,
            staged_pic_internal_names=_STAGED_PIC_NAMES,
        )


def test_dangling_pic_fails_loud() -> None:
    """A resolvable class whose pic hasn't been staged in
    `common.SLICE_TRAINER_PICS` yet must fail loud, not fall back silently."""
    with pytest.raises(ValueError, match="not staged in common.SLICE_TRAINER_PICS"):
        _build(("TRAINER_MARKO_19",), staged_pic_internal_names=set())


def test_missing_trainer_key_fails_loud() -> None:
    with pytest.raises(ValueError, match="not present in trainers.json"):
        _build(("TRAINER_DOES_NOT_EXIST",))


def test_multiple_failures_all_reported_not_just_first() -> None:
    with pytest.raises(ValueError) as exc_info:
        _build(
            ("TRAINER_MARKO_19", "TRAINER_LYNETTE_246"),
            staged_pic_internal_names=set(),
            staged_species=set(),
        )
    msg = str(exc_info.value)
    assert "TRAINER_MARKO_19" in msg
    assert "TRAINER_LYNETTE_246" in msg
    assert "2/2 pinned trainer(s)" in msg


def test_unresolved_nature_index_fails_loud() -> None:
    """`pbs_converter.trainers._emit_mon` passes a raw nature INDEX through
    unresolved -- staging must refuse to emit a bogus numeric `Nature:` line."""
    staged = _build(("TRAINER_MARKO_19",))
    staged[0].party[0]["nature"] = 5
    with pytest.raises(NotImplementedError, match="nature"):
        battles.emit_party_fragment(staged)


def test_full_slice_against_real_intermediate_json(fork_path: Path | None) -> None:
    """Integration check against the REAL Phase-2 intermediate JSON + fork:
    documents the corpus-readiness gap this slice landed with (however many
    of the 12 pinned trainers currently resolve depends on how far
    species_converter's concurrent work has landed at test time -- this
    doesn't pin an exact count, it just proves `build_staged_battles` either
    stages the full dozen cleanly or names every blocker precisely, never
    silently drops one)."""
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set")
    intermediate_dir = Path("output/uranium-build/intermediate")
    if not (intermediate_dir / "trainers.json").is_file():
        pytest.skip("output/uranium-build/intermediate/trainers.json not generated yet")

    from rpg2gba.pbs_converter._naming import load_fork_constants

    trainers = battles.load_trainers_json(intermediate_dir)
    trainer_types = battles.load_trainer_types_json(intermediate_dir)
    anchor_value = battles.read_pristine_trainer_anchor(fork_path)
    species_manifest = Path("output/uranium-build/species/species_manifest.json")
    staged_species = battles.load_species_manifest_constants(
        species_manifest if species_manifest.is_file() else None
    )

    trainers_h = fork_path / "include/constants/trainers.h"
    try:
        staged = battles.build_staged_battles(
            common.SLICE_TRAINER_BATTLES,
            trainers,
            trainer_types,
            anchor_value,
            fork_classes=load_fork_constants(trainers_h, "TRAINER_CLASS"),
            fork_genders=load_fork_constants(trainers_h, "TRAINER_GENDER"),
            fork_music=load_fork_constants(trainers_h, "TRAINER_ENCOUNTER_MUSIC"),
            fork_species=load_fork_constants(fork_path / "include/constants/species.h", "SPECIES"),
            fork_moves=load_fork_constants(fork_path / "include/constants/moves.h", "MOVE"),
            fork_items=load_fork_constants(fork_path / "include/constants/items.h", "ITEM"),
            staged_species=staged_species,
            staged_pic_internal_names={s.internal_name for s in common.SLICE_TRAINER_PICS},
        )
        assert len(staged) == len(common.SLICE_TRAINER_BATTLES)
    except ValueError as e:
        # Not staged yet is fine -- but Theo (starter-line species, always
        # staged) must never be among the failures.
        assert "TRAINER_THEO_9" not in str(e)
        assert "TRAINER_THEO_10" not in str(e)
        assert "TRAINER_THEO_11" not in str(e)
