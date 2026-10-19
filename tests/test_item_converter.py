"""item_converter: catalog rulings, stock-block cloning, description wrapping."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.item_converter import catalog, emit
from rpg2gba.item_converter.catalog import Catalog, GenItem
from rpg2gba.text_validator.engine_metrics import load_charmap, measure_line_width_px

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"

STOCK_ITEMS = """\
    [ITEM_CHERI_BERRY] =
    {
        .name = ITEM_NAME("Cheri Berry"),
        .pluralName = ITEM_PLURAL_NAME("Cheri Berries"),
        .price = (I_BERRY_PRICE >= GEN_8) ? 80 : 20,
        .holdEffect = HOLD_EFFECT_CURE_PAR,
        .description = COMPOUND_STRING(
            "A hold item that\\n"
            "heals paralysis\\n"
            "in battle."),
        .pocket = POCKET_BERRIES,
        .effect = gItemEffect_ParalyzeHeal,
        .iconPic = gItemIcon_CheriBerry,
        .iconPalette = gItemIconPalette_CheriBerry,
    },

    [ITEM_FOSSIL] =
    {
        .name = ITEM_NAME("Fossil"),
    #if I_KEY_FOSSILS >= GEN_4
        .price = 1000,
    #endif
    },
"""


def _item(**kw) -> GenItem:
    base = dict(uranium_id=500, internal="ACAIBERRY", constant="ITEM_ACAI_BERRY",
                name="Acai Berry", description="Cures paralysis.", price=20,
                essentials_pocket=5, kind="berry", analog="ITEM_CHERI_BERRY")
    base.update(kw)
    return GenItem(**base)


def test_clone_replaces_only_named_fields() -> None:
    block = emit.extract_block(STOCK_ITEMS, "ITEM_CHERI_BERRY", "items.h")
    out = block.render("ITEM_ACAI_BERRY", {"name": 'ITEM_NAME("Acai Berry")',
                                           "iconPic": "gItemIcon_GameAcaiBerry"})
    assert out.startswith("    [ITEM_ACAI_BERRY] =\n    {")
    assert '.name = ITEM_NAME("Acai Berry"),' in out
    assert ".holdEffect = HOLD_EFFECT_CURE_PAR," in out      # behaviour carried over
    assert ".effect = gItemEffect_ParalyzeHeal," in out
    assert "gItemIcon_CheriBerry," not in out
    assert '"heals paralysis\\n"' in out                       # untouched multi-line field


def test_clone_refuses_blocks_with_preprocessor_lines() -> None:
    with pytest.raises(ValueError, match="preprocessor"):
        emit.extract_block(STOCK_ITEMS, "ITEM_FOSSIL", "items.h")


def test_missing_stock_block_fails_loud() -> None:
    with pytest.raises(ValueError, match="no stock initializer"):
        emit.extract_block(STOCK_ITEMS, "ITEM_NOPE", "items.h")


def test_row_lookup_is_scoped_to_one_table() -> None:
    text = ("const u8 *const sA[] = {\n    [ITEM_CHERI_BERRY - FIRST_BERRY_INDEX] = sPicA,\n};\n"
            "const u8 *const sB[] = {\n    [ITEM_CHERI_BERRY - FIRST_BERRY_INDEX] = sPicB,\n};\n")
    cat = Catalog(berries=(_item(),), tail=(), blocked=())
    assert "= sPicB," in emit.render_berry_rows(cat, text, "sB", "x.h")
    assert "= sPicA," in emit.render_berry_rows(cat, text, "sA", "x.h")


def test_constants_header_counts_berries_and_lists_members() -> None:
    cat = Catalog(berries=(_item(),),
                  tail=(_item(constant="ITEM_LOOT_SACK", kind="key", analog=None),), blocked=())
    text = emit.render_constants(cat)
    assert "#define RPG2GBA_EXTRA_BERRIES 1" in text
    assert "#define RPG2GBA_BERRY_ITEMS \\\n    ITEM_ACAI_BERRY," in text
    assert "#define RPG2GBA_TAIL_ITEMS \\\n    ITEM_LOOT_SACK," in text


def test_long_name_fails_loud() -> None:
    with pytest.raises(ValueError, match="display_name"):
        emit.item_name(_item(name="Unidentified Fallen Object"), frozenset())


def test_paged_wrap_leaves_the_corner_free() -> None:
    charmap = load_charmap(ENGINE / "charmap.txt")
    text = ("A long description that keeps going well past the three lines the bag "
            "box can hold, so it has to page with the R button mark in the corner.")
    lines = emit.description_lines(_item(description=text), charmap)
    assert len(lines) > emit.DESCRIPTION_PAGE_LINES
    for i, line in enumerate(lines):
        last_of_page = i % emit.DESCRIPTION_PAGE_LINES == emit.DESCRIPTION_PAGE_LINES - 1
        limit = emit.PAGED_DESCRIPTION_WIDTH_PX if last_of_page else emit.DESCRIPTION_WIDTH_PX
        assert measure_line_width_px(line, charmap) <= limit


def test_short_description_stays_one_page() -> None:
    charmap = load_charmap(ENGINE / "charmap.txt")
    assert len(emit.description_lines(_item(description="Cures paralysis."), charmap)) == 1


def _write_refs(tmp: Path, rulings: dict) -> tuple[Path, Path]:
    id_map = tmp / "id_map.json"
    id_map.write_text(json.dumps({
        "items": {"ACAIBERRY": "ITEM_ACAI_BERRY", "ATOMBALL": "ITEM_ATOM_BALL",
                  "POTION": "ITEM_POTION"},
        "needs_engine": {"items": ["ITEM_ACAI_BERRY", "ITEM_ATOM_BALL"]},
    }), encoding="utf-8")
    rul = tmp / "rulings.json"
    rul.write_text(json.dumps({"items": rulings}), encoding="utf-8")
    return id_map, rul


def test_generated_constants_excludes_blocked(tmp_path: Path) -> None:
    id_map, rul = _write_refs(tmp_path, {"ACAIBERRY": {"kind": "berry", "analog": "ITEM_CHERI_BERRY"},
                                         "ATOMBALL": {"kind": "blocked"}})
    assert catalog.generated_constants(id_map_path=id_map, rulings_path=rul) == {"ITEM_ACAI_BERRY"}


def test_real_rulings_cover_every_missing_item() -> None:
    """Against the real reference files: 110 missing, 5 blocked (2026-10-19)."""
    generated = catalog.generated_constants()
    assert len(generated) == 105
    assert "ITEM_HAFLI_BERRY" not in generated
    assert {"ITEM_ACAI_BERRY", "ITEM_MARIAS_KEY", "ITEM_UNIDENTIFIED_FALLEN_OBJECT"} <= generated


def test_real_rulings_name_only_missing_items() -> None:
    id_map = json.loads(catalog.ID_MAP_PATH.read_text(encoding="utf-8"))
    rulings = json.loads(catalog.RULINGS_PATH.read_text(encoding="utf-8"))["items"]
    missing = {id_map["items"][i] for i in rulings}
    assert missing <= set(id_map["needs_engine"]["items"])
