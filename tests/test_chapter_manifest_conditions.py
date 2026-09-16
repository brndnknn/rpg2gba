"""Tests for the code-111/type-12 condition classifier.

Exemplars below are drawn verbatim from the 2026-09-12 measurement of the 18
staged CH01-CH05 maps under `output/uranium-build/maps/` (see
`conditions.py`'s module docstring), so a passing suite here is evidence the
table actually matches the corpus, not just synthetic strings.
"""
from __future__ import annotations

import pytest

from rpg2gba.chapter_manifest.conditions import FAMILIES, classify_condition


# --- one exemplar per family, all judgment_free=True (vanilla Essentials) --

_VANILLA_EXEMPLARS: list[tuple[str, str]] = [
    ("get_character_on_event", "get_character(0).onEvent?"),
    (
        "pb_trainer_battle",
        'pbTrainerBattle(PBTrainers::BIKER,"Lou",_I("Owww!"),false,0,false,0)',
    ),
    ("pb_trainer_battle", "pbTrainerBattle(PBTrainers::RICHBOY,\"Mawuli\",_I(\"See? We keep losing!\"),false,0)"),
    ("pb_item_ball", "Kernel.pbItemBall(::PBItems::POTION)"),
    ("pb_rock_smash", "Kernel.pbRockSmash"),
    ("pb_rock_smash", "Kernel.pbCoralBreak"),
    ("game_player_axis", "$game_player.x==17"),
    ("game_player_axis", "$game_player.y<=43"),
    ("pb_receive_item", "Kernel.pbReceiveItem(::PBItems::RARECANDY)"),
    ("pb_receive_item", "Kernel.pbReceiveItem(::PBItems::POKeBALL,10)"),
    (
        "pb_phone_battle_count",
        'pbPhoneBattleCount(PBTrainers::YOUNGSTER,"Richey")>=1',
    ),
    ("pokemon_global_attr", "$PokemonGlobal.surfing"),
    ("pokemon_global_attr", "$PokemonGlobal.nuzlocke==true"),
    ("pokemon_global_attr", "!$PokemonGlobal.surfing"),
    ("pb_pick_berry", "pbPickBerry(PBItems::ORANBERRY,2)"),
    ("game_variables_cmp", "$game_variables[1]==0"),
    ("pokemon_bag_query", "$PokemonBag.pbQuantity(PBItems::TURTICKET)>0"),
    ("pokemon_bag_query", "$PokemonBag.pbQuantity(:FERRYPASS)>0"),
    ("pokemon_bag_query", "$PokemonBag.pbStoreItem(::PBItems::OLDROD)"),
    ("pb_has_species", "pbHasSpecies?(::PBSpecies::RAPTORCH)"),
    ("pb_next_mystery_gift_id", "pbNextMysteryGiftID>0"),
    ("pb_pokerus", "Kernel.pbPokerus?"),
    ("pb_wild_battle", "pbWildBattle(PBSpecies::LINKITE,38)"),
    ("trainer_attr", "$Trainer.ablePokemonCount<=1"),
    ("trainer_attr", "$Trainer.gender==0"),
    ("trainer_attr", "$Trainer.gender == 0"),  # whitespace variant, same family
    ("input_trigger", "Input.trigger?(Input::C)"),
    ("distance_checker", "distanceChecker>=2"),
    ("pb_get_pokemon_egg", "pbGetPokemon(1).egg?"),
    (
        "pb_get_pokemon_shadow_rescue",
        "(pbGetPokemon(1).isShadow? rescue false)",
    ),
    ("is_temp_switch_off", 'isTempSwitchOff?("A")'),
    ("pb_day_care_deposited", "Kernel.pbDayCareDeposited==1"),
    ("pb_egg_generated", "Kernel.pbEggGenerated?"),
]

_URANIUM_EXEMPLARS: list[tuple[str, str]] = [
    ("uranium_jv_reward", "jvGiveReward"),
    ("uranium_jv_reward", "jvNextReward"),
    ("uranium_is_custom_game", "isCustomGame?"),
    ("uranium_show_ruleset_settings", "showRulesetSettings(1)"),
    ("uranium_is_rock_smash_softlocked", "isRockSmashSoftlocked?"),
]


@pytest.mark.parametrize("family_name,text", _VANILLA_EXEMPLARS)
def test_vanilla_exemplar_classifies_and_is_judgment_free(family_name: str, text: str) -> None:
    match = classify_condition(text)
    assert match is not None, f"{text!r} did not match any family"
    assert match.name == family_name
    assert match.judgment_free is True


@pytest.mark.parametrize("family_name,text", _URANIUM_EXEMPLARS)
def test_uranium_exemplar_classifies_and_is_not_judgment_free(family_name: str, text: str) -> None:
    match = classify_condition(text)
    assert match is not None, f"{text!r} did not match any family"
    assert match.name == family_name
    assert match.judgment_free is False


def test_all_families_have_unique_names() -> None:
    names = [f.name for f in FAMILIES]
    assert len(names) == len(set(names))


def test_whitespace_variants_unify() -> None:
    assert classify_condition("$Trainer.gender==0") is not None
    assert classify_condition("$Trainer.gender == 0") is not None
    assert (
        classify_condition("$Trainer.gender==0").name
        == classify_condition("$Trainer.gender == 0").name
    )
    # Interior whitespace runs (tabs, doubled spaces) collapse the same way.
    assert classify_condition("$Trainer.gender  ==\t0") is not None


def test_compound_boolean_outliers_land_in_fallback() -> None:
    # The two genuine outliers (REDERIVATION_PLAN.md §14.6): compound
    # booleans mixing a type guard with a variable comparison. No family
    # should claim these -- they must stay unclassified residue.
    outlier = "!pbGet(1).is_a?(Numeric) || $game_variables[1] < 0"
    assert classify_condition(outlier) is None


def test_novel_condition_does_not_match_any_family() -> None:
    # A condition shape that has never appeared in the corpus must not be
    # accidentally swallowed by an over-broad pattern.
    assert classify_condition("SomeFutureFanGame.pbTotallyNovelCheck(42)") is None
    assert classify_condition("") is None
    assert classify_condition("$game_switches[7]") is None


def test_staged_corpus_measurement_matches_plan() -> None:
    """Regression pin for REDERIVATION_PLAN.md's measured 147/76 figures.

    18 CH01-CH05 map JSONs, every code-111/type-12 condition. 145 of 147
    instances classify; the 2 remaining are the known compound-boolean
    outliers. This is the number the build agent measured and reported
    against the plan's estimate.
    """
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    manifests_dir = repo_root / "reference" / "manifests"
    maps_dir = repo_root / "output" / "uranium-build" / "maps"
    if not maps_dir.exists():
        pytest.skip("output/uranium-build/maps not present in this environment")

    map_ids: set[int] = set()
    for manifest_path in sorted(manifests_dir.glob("CH0*.manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
        for row in rows:
            map_ids.add(row["map_id"])

    texts: list[str] = []
    for map_id in sorted(map_ids):
        map_path = maps_dir / f"Map{map_id:03d}.json"
        if not map_path.exists():
            pytest.skip(f"{map_path} not present in this environment")
        map_data = json.loads(map_path.read_text(encoding="utf-8"))
        for event in map_data.get("events", []):
            for page in event.get("pages", []):
                for cmd in page.get("list") or []:
                    if cmd.get("code") != 111:
                        continue
                    params = cmd.get("parameters") or []
                    if len(params) >= 2 and params[0] == 12 and isinstance(params[1], str):
                        texts.append(params[1])

    assert len(map_ids) == 18
    assert len(texts) == 147
    assert len(set(texts)) == 76

    unclassified = [t for t in texts if classify_condition(t) is None]
    assert len(unclassified) == 2
    assert set(unclassified) == {"!pbGet(1).is_a?(Numeric) || $game_variables[1] < 0"}


def test_compound_boolean_never_classifies_even_when_both_operands_would() -> None:
    """The guard in `classify_condition`, not a property of the patterns.

    Every family's argument list is `.*`, and under `fullmatch` a greedy `.*`
    spans a `)` and an operator quite happily -- so before the explicit
    compound-boolean guard, a condition joining two calls of the SAME family
    matched that family and inherited its "no citation owed". No corpus row
    hits this today (all 7 compound-boolean texts in the 199-map corpus fall
    through on their operands), which is exactly why it needs pinning: the
    failure is silent and the next fan game is where it would land.
    """
    for text in (
        "pbTrainerBattle(PBTrainers::A,'x') || pbTrainerBattle(PBTrainers::B,'y')",
        "Kernel.pbItemBall(::PBItems::POTION) && Kernel.pbItemBall(::PBItems::ETHER)",
        "$game_player.x == 3 || $game_player.y == 4",
    ):
        assert classify_condition(text) is None, text


# --- per-family arm outcome table (REDERIVATION_PLAN.md §16.3 C2, "C2 shape"
# (a)) -----------------------------------------------------------------

_NON_EMPTY_DETAIL_KINDS = frozenset({"harness", "capability", "unmodelled"})


def test_every_family_has_both_outcomes() -> None:
    for family in FAMILIES:
        assert family.then_outcome is not None, family.name
        assert family.else_outcome is not None, family.name


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.name)
def test_harness_capability_unmodelled_outcomes_carry_a_detail(family) -> None:
    for outcome in (family.then_outcome, family.else_outcome):
        if outcome.kind in _NON_EMPTY_DETAIL_KINDS:
            assert outcome.detail, (
                f"{family.name}: {outcome.kind} outcome has an empty detail")


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.name)
def test_fork_outcomes_carry_a_detail(family) -> None:
    for outcome in (family.then_outcome, family.else_outcome):
        if outcome.kind == "fork":
            assert outcome.detail, (
                f"{family.name}: fork outcome has an empty detail")
