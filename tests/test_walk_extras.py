"""Walk-ROM extras (reference/walk_qol_plan.md): map scope, species, encoding."""
from __future__ import annotations

import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from rpg2gba.playtest import walk_extras
from rpg2gba.playtest.walk_extras import WalkExtras

OFFSETS = {
    "sizeof_walk": 12, "off_walk_romid": 0, "off_walk_expshare": 4,
    "off_walk_grantcount": 6, "off_walk_grants": 8, "val_walk_grant_max": 2,
}


def beat(name: str, maps: tuple[str, ...] = (), rows: tuple[str, ...] = ()):
    return SimpleNamespace(
        name=name, rows=rows,
        locations=tuple(SimpleNamespace(map_constant=m) for m in maps))


def chapter(*beats):
    names = [b.name for b in beats]
    return SimpleNamespace(beats=tuple(beats), index_of=names.index)


@pytest.fixture
def map_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = {"MAP_A": 31, "MAP_B": 35, "MAP_C": 40}
    monkeypatch.setattr(walk_extras, "map_uranium_id", ids.__getitem__)


def test_maps_entered_stops_before_the_seed_beat_and_reads_row_crossings(map_ids) -> None:
    chap = chapter(
        beat("B1", ("MAP_A",), ("map031/ev001/p0",)),
        beat("B2", ("MAP_A",), ("map031/seam/N/map035",)),
        beat("B3", ("MAP_C",)),
    )

    assert walk_extras.maps_entered(chap, "B3") == [31, 35]
    assert walk_extras.maps_entered(chap, None) == [31, 35, 40]
    assert walk_extras.maps_entered(chap, "B1") == []


def write_build(root: Path, wild: dict, scripts: dict[str, str]) -> Path:
    (root / "intermediate").mkdir(parents=True)
    (root / "intermediate" / "wild_encounters.json").write_text(
        json.dumps({"maps": wild}), encoding="utf-8")
    (root / "scripts").mkdir()
    for name, text in scripts.items():
        (root / "scripts" / name).write_text(text, encoding="utf-8")
    return root


def test_catchable_species_unions_every_method_then_gifts_in_map_order(tmp_path: Path) -> None:
    root = write_build(tmp_path, {
        "31": {
            "land_mons": {"mons": [{"species": "SPECIES_A"}, {"species": "SPECIES_B"}]},
            "fishing_mons": {"super_rod": [{"species": "SPECIES_C"}]},
            "uranium_extra": {"cave": {"mons": [{"species": "SPECIES_D"}]}},
        },
        "35": {"water_mons": {"mons": [{"species": "SPECIES_A"}, {"species": "SPECIES_E"}]}},
    }, {
        "Map031.pory": "givemon(SPECIES_F, 5)\n",
        "Map035.pory": "giveegg(SPECIES_G)\nmsgbox(\"SPECIES_X\")\n",
    })

    assert walk_extras.catchable_species([31, 35], root) == [
        "SPECIES_A", "SPECIES_B", "SPECIES_C", "SPECIES_D", "SPECIES_F",
        "SPECIES_E", "SPECIES_G"]


def test_catchable_species_reads_a_split_piece_through_its_origin(tmp_path: Path) -> None:
    from rpg2gba.map_split.ids import SPLIT_BASE, _MAX_PIECES

    root = write_build(tmp_path, {"40": {"land_mons": {"mons": [{"species": "SPECIES_A"}]}}}, {})
    piece = SPLIT_BASE + 40 * _MAX_PIECES

    assert walk_extras.catchable_species([piece], root) == ["SPECIES_A"]


def test_catchable_species_fails_loud_without_the_encounter_data(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="wild_encounters.json"):
        walk_extras.catchable_species([31], tmp_path)


def test_encode_extras_lays_out_the_engine_struct() -> None:
    extras = WalkExtras(rom_id=0xDEADBEEF, exp_share=True,
                        species=("SPECIES_A", "SPECIES_B"))

    data = walk_extras.encode_extras(extras, OFFSETS, {"SPECIES_A": 1573, "SPECIES_B": 25})

    assert struct.unpack("<IBxHHH", data) == (0xDEADBEEF, 1, 2, 1573, 25)


def test_encode_extras_refuses_more_species_than_the_engine_holds() -> None:
    extras = WalkExtras(rom_id=1, exp_share=False, species=("A", "B", "C"))

    with pytest.raises(ValueError, match="RPG2GBA_WALK_GRANT_MAX"):
        walk_extras.encode_extras(extras, OFFSETS, {"A": 1, "B": 2, "C": 3})


def test_plan_extras_without_grant_still_gets_a_nonzero_rom_id() -> None:
    extras = walk_extras.plan_extras(chapter(), None, grant=False, exp_share=False)

    assert extras.rom_id != 0
    assert extras.species == ()
    assert extras.exp_share is False
