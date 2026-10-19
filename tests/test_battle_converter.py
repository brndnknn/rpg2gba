"""battle_converter: move/ability rulings, function-code effects, the TM/HM list."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.battle_converter import catalog, emit
from rpg2gba.battle_converter.catalog import Catalog, GenAbility, GenMove
from rpg2gba.battle_converter.function_codes import AddedEffect, EffectSpec, effect_for
from rpg2gba.text_validator.engine_metrics import load_charmap

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"

STOCK_MOVES_INFO = """\
    [MOVE_BIND] =
    {
        .name = COMPOUND_STRING("Bind"),
        .effect = EFFECT_HIT,
        .battleAnimScript = gBattleAnimMove_Bind,
        .validApprenticeMove = TRUE,
    },
"""

STOCK_TMS_HMS = """\
#if __has_include("constants/rpg2gba_machines.gen.h")
#include "constants/rpg2gba_machines.gen.h"
#else
#define FOREACH_TM(F) \\
    F(FOCUS_PUNCH) \\
    F(DRAGON_CLAW)

#define FOREACH_HM(F) \\
    F(CUT) \\
    F(FLASH)
#endif

#define FOREACH_TMHM(F) \\
    FOREACH_TM(F) \\
    FOREACH_HM(F)
"""


def _move(**kw) -> GenMove:
    base = dict(uranium_id=562, internal="METALWHIP", constant="MOVE_METAL_WHIP",
                name="Metal Whip", description="A sharp steel whip that\nholds and hurts the foe.",
                uranium_description="A whip made of sharp steel.", kind="generate",
                type_="TYPE_STEEL", power=50, accuracy=90, pp=10,
                category="DAMAGE_CATEGORY_PHYSICAL", target="TARGET_SELECTED", priority=0,
                flag_lines=("        .makesContact = TRUE,",),
                spec=effect_for(0x0CF, "METALWHIP"), effect_chance=100, anim="MOVE_BIND")
    base.update(kw)
    return GenMove(**base)


def _catalog(moves=(), aliases=(), abilities=(), tms=(), hms=()) -> Catalog:
    return Catalog(moves=tuple(moves), aliases=tuple(aliases), blocked=(),
                   abilities=tuple(abilities), tms=tuple(tms), hms=tuple(hms))


# --- the gate set -------------------------------------------------------------

def test_generated_constants_cover_generated_aliased_and_every_ability() -> None:
    got = catalog.generated_constants()
    assert {"MOVE_METAL_WHIP", "MOVE_FLAME_IMPACT", "MOVE_SMOKE_SCREEN"} <= got
    assert {"ABILITY_LAZY", "ABILITY_CHERNOBYL", "ABILITY_DEEP_FREEZE"} <= got
    assert not {"MOVE_GAMMA_RAY", "MOVE_THUNDERSTORM", "MOVE_STICKY_TERRAIN"} & got


def test_rulings_reasons_and_blocked_nuclear_moves_are_explicit() -> None:
    rulings = json.loads(catalog.RULINGS_PATH.read_text(encoding="utf-8"))
    for key, r in rulings["moves"].items():
        assert r["kind"] in {"generate", "alias", "blocked"}, key
        if r["kind"] == "blocked":
            assert r["reason"], key
        if r["kind"] == "generate":
            assert r["anim"].startswith("MOVE_"), key
    for key, r in rulings["abilities"].items():
        if r["kind"] == "inert":
            assert r["reason"], key


# --- effects ------------------------------------------------------------------

def test_unknown_function_code_fails_loud() -> None:
    with pytest.raises(ValueError, match="no engine mapping"):
        effect_for(0x999, "MADEUP")


def test_ruling_effect_overrides_code_but_keeps_its_additional_effect() -> None:
    spec = catalog._spec({"effect": "EFFECT_SUPER_EFFECTIVE_ON_ARG",
                          "argument": ".type = TYPE_FAIRY"}, 0x00A, "INFERNALBLADE")
    assert spec.effect == "EFFECT_SUPER_EFFECTIVE_ON_ARG"
    assert spec.argument == ".type = TYPE_FAIRY"
    assert [a.move_effect for a in spec.added] == ["MOVE_EFFECT_BURN"]


def test_custom_code_takes_its_effect_from_the_ruling() -> None:
    spec = catalog._spec({"effect": "EFFECT_RPG2GBA_TRI_TYPE"}, 0x164, "LASERPULSE")
    assert spec.effect == "EFFECT_RPG2GBA_TRI_TYPE" and spec.added == ()


def test_chance_rolled_effect_with_zero_chance_fails_loud() -> None:
    move = _move(spec=EffectSpec("EFFECT_HIT", (AddedEffect("MOVE_EFFECT_BURN", "effect_chance"),)),
                 effect_chance=0)
    with pytest.raises(ValueError, match="never fires"):
        emit.render_move_row(move, load_charmap(ENGINE / "charmap.txt"), frozenset(),
                             STOCK_MOVES_INFO)


def test_golden_move_row() -> None:
    row = emit.render_move_row(_move(), load_charmap(ENGINE / "charmap.txt"), frozenset(),
                               STOCK_MOVES_INFO)
    assert row == """\
    [MOVE_METAL_WHIP] =
    {
        .name = COMPOUND_STRING("Metal Whip"),
        .description = COMPOUND_STRING(
            "A sharp steel whip that\\n"
            "holds and hurts the foe."),
        .effect = EFFECT_HIT,
        .power = 50,
        .type = TYPE_STEEL,
        .accuracy = 90,
        .pp = 10,
        .target = TARGET_SELECTED,
        .priority = 0,
        .category = DAMAGE_CATEGORY_PHYSICAL,
        .makesContact = TRUE,
        .additionalEffects = ADDITIONAL_EFFECTS({
            .moveEffect = MOVE_EFFECT_WRAP,
            .multistring.wrapped = B_MSG_WRAPPED_WRAP,
        }),
        .battleAnimScript = gBattleAnimMove_Bind,
    },"""


# --- text ---------------------------------------------------------------------

def test_long_uranium_description_fails_loud_without_a_ruling() -> None:
    move = _move(description="The user slugs the opponent with a fist made of solid gold. "
                             "Scatters coins which can be picked up after the battle.")
    with pytest.raises(ValueError, match="add a description"):
        emit.move_description_lines(move, load_charmap(ENGINE / "charmap.txt"))


def test_long_ability_description_fails_loud() -> None:
    ability = GenAbility(uranium_id=209, internal="CHERNOBYL", constant="ABILITY_CHERNOBYL",
                         name="Chernobyl", uranium_description="",
                         description="Affects weather and reduces all of the Nuclear type's "
                                     "weaknesses.", kind="inert")
    with pytest.raises(ValueError, match="add a description"):
        emit.ability_description(ability, load_charmap(ENGINE / "charmap.txt"))


# --- constants and machines -----------------------------------------------------

def test_move_constants_start_at_the_custom_slot_and_alias_stock() -> None:
    alias = _move(constant="MOVE_SMOKE_SCREEN", kind="alias", alias_of="MOVE_SMOKESCREEN")
    text = emit.render_move_constants(_catalog(moves=[_move()], aliases=[alias]))
    assert "    MOVE_METAL_WHIP = MOVES_COUNT_GEN9, \\\n    RPG2GBA_MOVES_END," in text
    assert "#define MOVE_SMOKE_SCREEN MOVE_SMOKESCREEN\n" in text
    assert "#define RPG2GBA_HAS_MOVE_METAL_WHIP 1\n" in text
    empty = emit.render_move_constants(_catalog())
    assert "RPG2GBA_MOVES_END = MOVES_COUNT_GEN9," in empty


def test_only_implemented_abilities_get_a_presence_macro() -> None:
    lazy = GenAbility(193, "LAZY", "ABILITY_LAZY", "Lazy", "", "", "implemented")
    leadskin = GenAbility(202, "LEADSKIN", "ABILITY_LEAD_SKIN", "Lead Skin", "", "", "inert")
    text = emit.render_ability_constants(_catalog(abilities=[lazy, leadskin]))
    assert "ABILITY_LAZY = ABILITIES_COUNT_GEN9," in text
    assert "#define RPG2GBA_HAS_ABILITY_LAZY 1" in text
    assert "RPG2GBA_HAS_ABILITY_LEAD_SKIN" not in text


def test_stock_machine_names_the_game_drops_are_aliased_to_their_number() -> None:
    tms, hms = emit.stock_machines(STOCK_TMS_HMS)
    assert (tms, hms) == (["FOCUS_PUNCH", "DRAGON_CLAW"], ["CUT", "FLASH"])
    text = emit.render_machines(
        _catalog(tms=["MOVE_FOCUS_PUNCH", "MOVE_DRAGON_CLAW"], hms=["MOVE_CUT", "MOVE_STRUGGLE"]),
        tms, hms)
    assert "#define ITEM_HM_FLASH ITEM_HM02\n" in text
    assert "ITEM_TM_FOCUS_PUNCH" not in text


def test_stock_machine_name_on_another_number_fails_loud() -> None:
    with pytest.raises(ValueError, match="would duplicate"):
        emit.machine_aliases("TM", ["FOCUS_PUNCH", "DRAGON_CLAW"],
                             ("MOVE_DRAGON_CLAW", "MOVE_FOCUS_PUNCH"))


# --- the real catalog -------------------------------------------------------------

def test_real_catalog(uranium_data: Path, fork_path: Path | None) -> None:
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set")
    cat = catalog.build_catalog(uranium_data.parent, fork_path)
    assert len(cat.moves) == 17 and len(cat.blocked) == 14
    assert [g.alias_of for g in cat.aliases] == ["MOVE_SMOKESCREEN"]
    assert len(cat.abilities) == 19
    # Uranium renamed Pay Day: same internal name, its own move.
    golden = next(g for g in cat.moves if g.internal == "PAYDAY")
    assert golden.constant == "MOVE_GOLDEN_FIST"
    assert len(cat.tms) == 100 and len(cat.hms) == 8
    assert cat.tms[94:96] == ("MOVE_CAUSTIC_BREATH", "MOVE_CORAL_BREAK")
    assert cat.tms[69] == "MOVE_FLASH"
    assert cat.hms[4] == "MOVE_STRUGGLE"   # HM05 duplicates HM01: placeholder ruling


def test_stray_ruling_fails_loud(tmp_path: Path, uranium_data: Path,
                                 fork_path: Path | None) -> None:
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set")
    rulings = json.loads(catalog.RULINGS_PATH.read_text(encoding="utf-8"))
    rulings["moves"]["TACKLE"] = {"kind": "blocked", "reason": "test"}
    path = tmp_path / "rulings.json"
    path.write_text(json.dumps(rulings), encoding="utf-8")
    with pytest.raises(ValueError, match="already has"):
        catalog.build_catalog(uranium_data.parent, fork_path, rulings_path=path)
