"""Known-zero key items (`story_state.bag`, `BagHas`).

The key-item set comes from the real Uranium `items.dat`, so every test skips
when the source tree is not configured (same stance as the other real-data
story_state tests).
"""
from __future__ import annotations

import pytest

from rpg2gba.chapter_manifest.schema import branch_row_id, page_row_id
from rpg2gba.story_state.bag import key_item_symbols, scan_bag_text
from rpg2gba.story_state.extract import extract_map
from rpg2gba.story_state.state import Assign, BagHas, Test
from tests.test_chapter_manifest_generator import _cmd, _page
from tests.test_story_state_extract import _event, _map

try:
    KEYS = key_item_symbols()
except (RuntimeError, FileNotFoundError, OSError) as exc:  # no Uranium tree here
    pytest.skip(f"Uranium items.dat unavailable: {exc}", allow_module_level=True)


def _arms(condition: str) -> tuple:
    page = _page([
        _cmd(111, [12, condition], indent=0),
        _cmd(101, ["then"], indent=1),
        _cmd(411, [], indent=0),
        _cmd(101, ["else"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    page_id = page_row_id(999, 1, 0)
    return rows[branch_row_id(page_id, 0)], rows[branch_row_id(page_id, 1)]


def _page_rows(commands: list[dict]):
    page = _page(commands)
    rows = extract_map(999, _map([_event(1, [page])]), common_events=[], switch_labels={})
    return rows[page_row_id(999, 1, 0)]


# (a) key-item quantity comparisons become BagHas tests ----------------------


@pytest.mark.parametrize("condition,then_value", [
    ("$PokemonBag.pbQuantity(PBItems::BIKEWHEEL)>0", True),
    ("$PokemonBag.pbQuantity(::PBItems::BIKEWHEEL) >= 1", True),
    ("$PokemonBag.pbQuantity(:BIKEWHEEL)==0", False),
    ("$PokemonBag.pbQuantity(PBItems::BIKEWHEEL) < 1", False),
])
def test_key_item_quantity_is_a_baghas_test(condition: str, then_value: bool) -> None:
    then_row, else_row = _arms(condition)
    assert then_row.arm_guard.tests == (Test(BagHas("BIKEWHEEL"), "==", then_value),)
    assert else_row.arm_guard.tests == (Test(BagHas("BIKEWHEEL"), "==", not then_value),)
    assert else_row.arm_guard.negated and not then_row.arm_guard.negated


# (b) anything else keeps the old outcome ------------------------------------


@pytest.mark.parametrize("condition", [
    "$PokemonBag.pbQuantity(PBItems::POTION)>0",           # ordinary item
    "$PokemonBag.pbQuantity(PBItems::BIKEWHEEL)>2",        # other comparison
])
def test_other_bag_conditions_stay_unmodelled(condition: str) -> None:
    then_row, _ = _arms(condition)
    assert then_row.arm_guard is not None
    assert then_row.arm_guard.tests == ()
    assert then_row.arm_guard.outcome.kind == "unmodelled"
    assert then_row.arm_guard.outcome.detail == "bag_contents"


def test_compound_bag_condition_falls_through_unchanged() -> None:
    then_row, _ = _arms("$PokemonBag.pbQuantity(PBItems::BIKEWHEEL)>0 && $game_switches[3]")
    assert then_row.arm_guard is None  # the family table never classified it
    assert then_row.refusals[0].code == "unclassified_condition"


# (c) grants and havocs -------------------------------------------------------


@pytest.mark.parametrize("call", [
    "Kernel.pbReceiveItem(PBItems::BIKEWHEEL)",
    "pbReceiveItem(:BIKEWHEEL)",
    "pbItemBall(::PBItems::BIKEWHEEL)",
    "$PokemonBag.pbStoreItem(PBItems::BIKEWHEEL)",
])
def test_literal_key_item_grant_writes_true(call: str) -> None:
    row = _page_rows([_cmd(355, [call])])
    assert [w for w in row.writes if isinstance(w, Assign) and w.key == BagHas("BIKEWHEEL")] != []
    assert all(w.values == frozenset({True}) for w in row.writes if w.key == BagHas("BIKEWHEEL"))
    assert BagHas("BIKEWHEEL") not in row.havoc_keys


def test_grant_in_a_condition_text_counts() -> None:
    row = _page_rows([_cmd(111, [12, "Kernel.pbReceiveItem(PBItems::BIKEWHEEL)"], indent=0),
                      _cmd(412, [], indent=0)])
    assert any(w.key == BagHas("BIKEWHEEL") for w in row.writes)


def test_unclassifiable_mention_is_havoc_not_a_grant() -> None:
    row = _page_rows([_cmd(355, ["$PokemonBag.pbDeleteItem(PBItems::BIKEWHEEL)"])])
    assert BagHas("BIKEWHEEL") in row.havoc_keys
    assert not any(w.key == BagHas("BIKEWHEEL") for w in row.writes)


def test_mart_list_havocs_its_key_items_only() -> None:
    row = _page_rows([_cmd(355, ["pbPokemonMart([ PBItems::TURTICKET, PBItems::POTION ])"])])
    assert BagHas("TURTICKET") in row.havoc_keys
    assert BagHas("POTION") not in row.havoc_keys


def test_quantity_read_is_neutral() -> None:
    scan = scan_bag_text("$PokemonBag.pbQuantity(PBItems::BIKEWHEEL)>0")
    assert scan.grants == frozenset() and scan.havocs == frozenset()


def test_jvgivereward_havocs_every_ladder_key_item() -> None:
    from rpg2gba.beat_floor.reward_ladder import load_profrewards

    ladder_keys = {i for rung in load_profrewards() for i in rung.items} & KEYS
    assert ladder_keys, "PROFREWARDS lists no key item -- this test no longer proves anything"
    assert scan_bag_text("jvGiveReward").havocs == frozenset(ladder_keys)


# (d) the key-item loader -----------------------------------------------------


def test_key_item_loader() -> None:
    assert "BIKEWHEEL" in KEYS
    assert "POTION" not in KEYS


def test_a_non_literal_grant_havocs_every_key_item():
    # Map052's `Kernel.pbReceiveItem(pbGet(1))` / Map107's `pbItemBall(item)`:
    # the item is chosen at runtime, so any key item could arrive.
    from rpg2gba.story_state.bag import key_item_symbols, scan_bag_text

    for text in ("Kernel.pbReceiveItem(pbGet(1))", "Kernel.pbItemBall(item)"):
        scan = scan_bag_text(text)
        assert scan.grants == frozenset()
        assert scan.havocs == key_item_symbols()


def test_a_literal_non_key_grant_havocs_nothing():
    from rpg2gba.story_state.bag import scan_bag_text

    assert scan_bag_text("Kernel.pbReceiveItem(PBItems::POTION)") == scan_bag_text("")
