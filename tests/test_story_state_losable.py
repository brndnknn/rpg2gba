"""Ruling 15's losable-battle check (REDERIVATION_PLAN.md §16.3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.story_state.losable import losable_battle_evidence, losable_battle_sites

OUT_DIR = Path("output/uranium-build")


def _sites(source: str, *, program: bool = False) -> list[str]:
    return losable_battle_sites(source, "here", program=program)


def test_default_canlose_is_losable() -> None:
    assert _sites('pbTrainerBattle(PBTrainers::YOUNGSTER,"Joey",_I("..."))') == [
        "here: pbTrainerBattle"]


def test_canlose_true_at_the_signature_position_is_not_losable() -> None:
    # pbTrainerBattle(id,name,speech,doublebattle,trainerparty,canlose,variable)
    assert _sites('pbTrainerBattle(PBTrainers::RIVAL,"Theo",_I("x"),false,19,true,7)') == []
    # Index 3 is `doublebattle`, not `canlose`: `true` there changes nothing.
    assert _sites('pbTrainerBattle(PBTrainers::RIVAL,"Theo",_I("x"),true,19)') != []


def test_each_helper_reads_its_own_position() -> None:
    assert _sites("pbWildBattle(PBSpecies::X,5,1,true,true)") == []
    assert _sites("pbWildBattle(PBSpecies::X,5,1,true)") != []
    assert _sites("pbDoubleWildBattle(PBSpecies::X,5,PBSpecies::Y,5,1,true,true)") == []
    assert _sites("customTrainerBattle(t,\"bye\",false,true)") == []
    assert _sites(
        'pbDoubleTrainerBattle(PBTrainers::A,"a",0,_I("x"),PBTrainers::B,"b",0,_I("y"),true)'
    ) == []


def test_ruby_truthiness_zero_means_can_lose() -> None:
    # `if canlose` in the body: 0 is truthy in Ruby, nil is not.
    assert _sites("pbWildBattle(PBSpecies::X,5,1,true,0)") == []
    assert _sites("pbWildBattle(PBSpecies::X,5,1,true,nil)") != []


def test_non_literal_canlose_fails_loud() -> None:
    with pytest.raises(ValueError, match="not a literal"):
        _sites("pbWildBattle(PBSpecies::X,5,1,true,flag)")


def test_script_blocks_are_parsed_as_programs() -> None:
    assert _sites("x=1\npbWildBattle(PBSpecies::X,5)", program=True) == ["here: pbWildBattle"]


def test_encounter_table_is_evidence(tmp_path: Path) -> None:
    build = tmp_path / "build"
    (build / "intermediate").mkdir(parents=True)
    (build / "maps").mkdir()
    (build / "intermediate" / "wild_encounters.json").write_text(json.dumps({
        "maps": {"7": {"fishing_mons": {"mons": [{}]}}},
    }), encoding="utf-8")
    for m in (7, 8):
        (build / "maps" / f"Map{m:03d}.json").write_text(json.dumps({"events": []}),
                                                         encoding="utf-8")
    assert losable_battle_evidence({7, 8}, build, set()) == (
        "map007: wild encounters (fishing_mons)",)
    assert losable_battle_evidence({8}, build, set()) == ()


def test_strip_listed_events_are_skipped(tmp_path: Path) -> None:
    build = tmp_path / "build"
    (build / "intermediate").mkdir(parents=True)
    (build / "maps").mkdir()
    (build / "intermediate" / "wild_encounters.json").write_text('{"maps": {}}', encoding="utf-8")
    battle = {"code": 355, "indent": 0, "parameters": ["pbWildBattle(PBSpecies::X,5)"]}
    map_data = {"events": [{"id": 3, "pages": [{"list": [battle]}]}]}
    (build / "maps" / "Map009.json").write_text(json.dumps(map_data), encoding="utf-8")
    assert losable_battle_evidence({9}, build, set()) == ("map009/ev003/p0@0: pbWildBattle",)
    assert losable_battle_evidence({9}, build, {(9, 3)}) == ()


@pytest.mark.skipif(not (OUT_DIR / "maps").is_dir(), reason="no converted corpus on disk")
def test_real_ch01_can_white_out_only_in_moki_town_grass() -> None:
    """Ruling 15 as corrected: CH01's rival passes canlose=true, but Moki
    Town has a land encounter table, so a post-starter white-out is real."""
    from rpg2gba.chapter_atlas.binding import load_binding
    from rpg2gba.conversion_agent.orchestrator import load_map_event_strips

    binding = load_binding(path=Path("reference/chapters.json"))
    stripped = set(load_map_event_strips(Path("reference")))
    evidence = losable_battle_evidence(set(binding.chapter("CH01").maps), OUT_DIR, stripped)
    assert evidence == ("map032: wild encounters (land_mons, fishing_mons)",)
