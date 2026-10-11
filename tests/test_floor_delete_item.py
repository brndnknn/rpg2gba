"""`$PokemonBag.pbDeleteItem(...)` -> `item_remove` floor assertion, and the
generic archetype's after-the-page bag check for it (mirrors item_grant)."""
import pytest

from rpg2gba.beat_floor.assertion import ExtractContext
from rpg2gba.beat_floor.script import extract_script

ROW_ID = "map047/ev013/p0"


def _ctx() -> ExtractContext:
    return ExtractContext(
        map_id=47, event_id=13, page_idx=0, row_id=ROW_ID,
        event={}, map_data={}, common_events_by_id={}, door_cells={},
    )


@pytest.mark.parametrize("text,item", [
    ("$PokemonBag.pbDeleteItem(:MARIAKEY)", "MARIAKEY"),
    ("$PokemonBag.pbDeleteItem(PBItems::BIKEWHEEL)", "BIKEWHEEL"),
])
def test_delete_item_extracts_item_remove(text, item):
    a, r = extract_script(text, 0, _ctx())
    assert r == ()
    assert [x.kind for x in a] == ["item_remove"]
    assert a[0].param("item") == item
    assert a[0].param("quantity") == 1


def test_delete_item_with_quantity():
    a, _ = extract_script("$PokemonBag.pbDeleteItem(:POTION,3)", 0, _ctx())
    assert a[0].param("quantity") == 3


def test_delete_item_non_literal_refuses():
    a, r = extract_script("$PokemonBag.pbDeleteItem(pbGet(1))", 0, _ctx())
    assert a == ()
    assert [x.reason for x in r] == ["non_literal_args"]


class _BagEmu:
    def __init__(self, qty: int) -> None:
        self.qty = qty

    def bag_item_quantity(self, const: str) -> int:
        return self.qty

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def test_item_remove_handler_checks_the_bag_total():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS, Step
    from rpg2gba.playtest.errors import ScenarioError

    handler = STEP_HANDLERS["item_remove"]
    params = (("item", "MARIAKEY"), ("quantity", 1))
    with pytest.raises(ScenarioError, match="after the page completes"):
        handler(_BagEmu(0), "B1", Step(ROW_ID, "item_remove", 3, params))
    checked = Step(ROW_ID, "item_remove", 3,
                   params + (("const", "ITEM_MARIA_KEY"), ("expected_total", 0)))
    handler(_BagEmu(0), "B1", checked)
    with pytest.raises(ScenarioError, match="bag holds 1 ITEM_MARIA_KEY, expected 0"):
        handler(_BagEmu(1), "B1", checked)
