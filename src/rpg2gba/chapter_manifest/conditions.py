"""Idiom families for code-111/`COND_TYPE_SCRIPT` (type 12) condition text.

**The defect this closes (REDERIVATION_PLAN.md §14.6 / Ruling 2, 2026-09-12):**
`generator.py` used to see a script-typed conditional branch, increment a
counter, and throw `params[1]` away. The manifest then recorded only *that* a
page had a Ruby condition, never *what it said* -- which is why every page
carrying one owed a human a `source:` citation, even when the condition is a
completely ordinary Essentials idiom (`get_character(0).onEvent?`,
`Kernel.pbItemBall(PBItems::POTION)`, ...) that needs no judgment at all to
classify.

**Measured ground state (2026-09-12, all 18 CH01-CH05 maps under
`output/uranium-build/maps/`):** 147 code-111/type-12 instances collapse to 76
distinct texts. Text-level uniqueness is NOT shape-level uniqueness -- 55 of
the 76 texts occur exactly once, but nearly all of those are the same handful
of call shapes (`pbTrainerBattle`, `Kernel.pbItemBall`, `Kernel.pbReceiveItem`,
`$game_player.y`) with different literal arguments. This module tables those
shapes so a family is "one function/attribute name with interchangeable
literal arguments," not a stack of one-off strings.

**Table-driven, not if/elif.** This package moved its archetype dispatch from
if/elif to a registry in commit c91f70d3 for exactly the reason this module
exists for again: an open-ended, growing set of shapes belongs in a table a
later session can extend by appending a row, not by editing branching logic.
See `archetypes.py` for the sibling registry this one is modeled on.

**Cross-game reusability is the point.** ~89% of the staged corpus's
instances are vanilla Essentials shapes (`get_character`, `$game_player`,
`$PokemonGlobal`, `Kernel.pbItemBall`, `pbPhoneBattleCount`, ...), so this
table is expected to transfer unchanged to the next Essentials-based fan
game. `judgment_free=False` families are reserved for shapes that are
Uranium-specific custom methods (`jvGiveReward`, `isCustomGame?`,
`showRulesetSettings`, `isRockSmashSoftlocked?`) -- classifying them still
takes zero regex-matching effort, but confirming what they *mean* required
reading Uranium's own Ruby source, so they do not transfer.

**Two genuine outliers are a fallback, not a pattern.**
`!pbGet(1).is_a?(Numeric) || $game_variables[1] < 0` and its one sibling are
compound booleans mixing a type guard with a variable comparison. No family
matches them on purpose -- `classify_condition` returns `None` and the row
keeps its citation requirement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ConditionFamily:
    """One recognized idiom for a code-111/type-12 condition string.

    `pattern` is matched with `re.fullmatch` against the *whitespace-
    normalized* condition text (`_normalize`), so `$Trainer.gender==0` and
    `$Trainer.gender == 0` -- both occur in the corpus -- match identically.
    `judgment_free` is true for vanilla-Essentials shapes that transfer to
    the next fan game unchanged; false for shapes whose meaning is specific
    to Uranium's own custom Ruby (still a trivial regex match, but a human
    had to read Uranium's source once to know what the call does).
    """

    name: str
    pattern: re.Pattern[str]
    description: str
    judgment_free: bool


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


_CMP = r"(?:==|!=|<=|>=|<|>)"

# --- vanilla Essentials shapes (judgment-free; transfer to the next game) --
#
# Corpus counts are from the 2026-09-12 measurement of the 18 staged CH01-CH05
# maps (147 instances / 76 texts) unless marked "corpus-wide", which is the
# full 199-map count given alongside the staged measurement in
# REDERIVATION_PLAN.md -- those shapes have zero staged instances today but
# are cheap to recognize now rather than rediscovering them chapter by
# chapter as later chapters stage the maps that carry them.
_VANILLA_FAMILIES: tuple[ConditionFamily, ...] = (
    ConditionFamily(
        name="get_character_on_event",
        # 26 staged instances, e.g. "get_character(0).onEvent?" -- the
        # single most common condition shape in the corpus by a wide margin.
        pattern=_rx(r"get_character\(-?\d+\)\.onEvent\?"),
        description="get_character(N).onEvent? -- self-switch-style event-running guard",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_trainer_battle",
        # 22 staged instances / 22 distinct texts -- every one differs only
        # in trainer id, name, and loss quote. The transpiler already
        # recognizes this head (census.py); this family just stops the
        # manifest from discarding the same information at the condition
        # layer.
        pattern=_rx(r"pb(?:Double)?TrainerBattle\(.*\)"),
        description="pbTrainerBattle(...) / pbDoubleTrainerBattle(...) -- trainer battle trigger",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_item_ball",
        # 15 staged instances across 10 distinct item literals.
        pattern=_rx(r"Kernel\.pbItemBall\(.*\)"),
        description="Kernel.pbItemBall(ITEM) -- overworld item-ball grant guard",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_rock_smash",
        # 14 staged instances, all bare "Kernel.pbRockSmash". pbCoralBreak is
        # the corpus-wide sibling (36 instances, not in the staged 18 maps)
        # -- same shape, same guard role, folded in here rather than given
        # its own family.
        pattern=_rx(r"Kernel\.(?:pbRockSmash|pbCoralBreak)\??"),
        description="Kernel.pbRockSmash / Kernel.pbCoralBreak -- breakable-terrain guard",
        judgment_free=True,
    ),
    ConditionFamily(
        name="game_player_axis",
        # 12 staged instances, e.g. "$game_player.x==17", "$game_player.y<=43".
        pattern=_rx(r"\$game_player\.[xy]\s*" + _CMP + r"\s*-?\d+"),
        description="$game_player.x|y <cmp> N -- player-position gate",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_receive_item",
        # 9 staged instances, e.g. "Kernel.pbReceiveItem(::PBItems::REVIVE)",
        # "Kernel.pbReceiveItem(::PBItems::POKeBALL,10)".
        pattern=_rx(r"Kernel\.pbReceiveItem\(.*\)"),
        description="Kernel.pbReceiveItem(ITEM[, qty[, name]]) -- item grant guard",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_phone_battle_count",
        # 8 staged instances, e.g. "pbPhoneBattleCount(PBTrainers::YOUNGSTER,\"Richey\")>=1".
        pattern=_rx(r"pbPhoneBattleCount\(.*\)\s*" + _CMP + r"\s*\d+"),
        description="pbPhoneBattleCount(TRAINER, NAME) <cmp> N -- rematch-count gate",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pokemon_global_attr",
        # 8 staged instances, e.g. "$PokemonGlobal.surfing",
        # "$PokemonGlobal.randomizer", "$PokemonGlobal.nuzlocke==true". The
        # corpus-wide sibling "!$PokemonGlobal.surfing" (negated, bare) is
        # covered by the optional leading "!".
        pattern=_rx(r"!?\$PokemonGlobal\.\w+(?:\s*" + _CMP + r"\s*(?:true|false|-?\d+))?"),
        description="$PokemonGlobal.<attr>[ <cmp> literal] -- global play-state flag read",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_pick_berry",
        # 5 staged instances, e.g. "pbPickBerry(PBItems::ORANBERRY,2)".
        pattern=_rx(r"pbPickBerry\(.*\)"),
        description="pbPickBerry(ITEM, n) -- berry-tree harvest guard",
        judgment_free=True,
    ),
    ConditionFamily(
        name="game_variables_cmp",
        # 4 staged instances, e.g. "$game_variables[1]==0".
        pattern=_rx(r"\$game_variables\[\d+\]\s*" + _CMP + r"\s*-?\d+"),
        description="$game_variables[N] <cmp> M -- raw variable comparison",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pokemon_bag_query",
        # 3 staged instances ($PokemonBag.pbQuantity) + 1 (pbStoreItem);
        # corpus-wide also seen with a bare symbol argument
        # ("$PokemonBag.pbQuantity(:FERRYPASS)>0"), which `.*` already covers.
        pattern=_rx(r"\$PokemonBag\.(?:pbQuantity|pbStoreItem)\(.*\)(?:\s*" + _CMP + r"\s*\d+)?"),
        description="$PokemonBag.pbQuantity|pbStoreItem(ITEM)[ <cmp> N] -- inventory-quantity gate",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_has_species",
        # 3 staged instances, e.g. "pbHasSpecies?(::PBSpecies::RAPTORCH)".
        pattern=_rx(r"pbHasSpecies\?\(.*\)"),
        description="pbHasSpecies?(SPECIES) -- party/box species-ownership guard",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_next_mystery_gift_id",
        # 1 staged instance, "pbNextMysteryGiftID>0".
        pattern=_rx(r"pbNextMysteryGiftID\s*" + _CMP + r"\s*\d+"),
        description="pbNextMysteryGiftID <cmp> N -- pending mystery-gift guard",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_pokerus",
        # 1 staged instance, "Kernel.pbPokerus?".
        pattern=_rx(r"Kernel\.pbPokerus\?"),
        description="Kernel.pbPokerus? -- Pokerus-infection guard",
        judgment_free=True,
    ),
    # --- corpus-wide-only shapes: zero staged instances today, recognized
    # now so a later chapter's manifest doesn't have to rediscover them. ---
    ConditionFamily(
        name="pb_wild_battle",
        # 4 corpus-wide, e.g. "pbWildBattle(PBSpecies::LINKITE,38)".
        pattern=_rx(r"pbWildBattle\(.*\)"),
        description="pbWildBattle(SPECIES, level) -- scripted wild encounter trigger",
        judgment_free=True,
    ),
    ConditionFamily(
        name="trainer_attr",
        # $Trainer.ablePokemonCount<=1 (13 corpus-wide), $Trainer.gender==0
        # (4, also spaced "$Trainer.gender == 0" -- both occur).
        pattern=_rx(r"\$Trainer\.\w+\s*" + _CMP + r"\s*-?\w+"),
        description="$Trainer.<attr> <cmp> literal -- player-character state gate",
        judgment_free=True,
    ),
    ConditionFamily(
        name="input_trigger",
        # 7 corpus-wide, e.g. "Input.trigger?(Input::C)".
        pattern=_rx(r"Input\.trigger\?\(Input::\w+\)"),
        description="Input.trigger?(Input::KEY) -- raw button-press poll",
        judgment_free=True,
    ),
    ConditionFamily(
        name="distance_checker",
        # 10 corpus-wide, e.g. "distanceChecker>=2".
        pattern=_rx(r"distanceChecker\s*" + _CMP + r"\s*\d+"),
        description="distanceChecker <cmp> N -- scripted proximity gate",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_get_pokemon_egg",
        # 8 corpus-wide, e.g. "pbGetPokemon(1).egg?".
        pattern=_rx(r"pbGetPokemon\(\d+\)\.egg\?"),
        description="pbGetPokemon(N).egg? -- party-slot egg-state guard",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_get_pokemon_shadow_rescue",
        # 6 corpus-wide, e.g. "(pbGetPokemon(1).isShadow? rescue false)".
        pattern=_rx(r"\(pbGetPokemon\(\d+\)\.isShadow\?\s*rescue\s*false\)"),
        description="(pbGetPokemon(N).isShadow? rescue false) -- shadow-state guard, nil-safe",
        judgment_free=True,
    ),
    ConditionFamily(
        name="is_temp_switch_off",
        # 5 corpus-wide, e.g. 'isTempSwitchOff?("A")'.
        pattern=_rx(r'isTempSwitchOff\?\("\w+"\)'),
        description='isTempSwitchOff?("X") -- ephemeral self-switch-style guard',
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_day_care_deposited",
        # 3 corpus-wide, "Kernel.pbDayCareDeposited==1".
        pattern=_rx(r"Kernel\.pbDayCareDeposited\s*" + _CMP + r"\s*\d+"),
        description="Kernel.pbDayCareDeposited <cmp> N -- Day Care occupancy gate",
        judgment_free=True,
    ),
    ConditionFamily(
        name="pb_egg_generated",
        # 6 corpus-wide, "Kernel.pbEggGenerated?".
        pattern=_rx(r"Kernel\.pbEggGenerated\?"),
        description="Kernel.pbEggGenerated? -- Day Care egg-ready guard",
        judgment_free=True,
    ),
)

# --- Uranium-specific shapes -------------------------------------------
#
# Trivial to match, but the meaning is Uranium's own custom Ruby, not vanilla
# Essentials -- a human read Uranium's source once to confirm what each does
# (REDERIVATION_PLAN.md §14.6's "14.1's ten work items" list). Do not expect
# these to appear in the next fan game.
_URANIUM_FAMILIES: tuple[ConditionFamily, ...] = (
    ConditionFamily(
        name="uranium_jv_reward",
        # 5 staged instances: "jvGiveReward" (4), "jvNextReward" (1).
        pattern=_rx(r"jv(?:GiveReward|NextReward)"),
        description="jvGiveReward / jvNextReward -- Uranium's quest-reward-ladder guard",
        judgment_free=False,
    ),
    ConditionFamily(
        name="uranium_is_custom_game",
        # 3 staged instances, bare "isCustomGame?".
        pattern=_rx(r"isCustomGame\?"),
        description="isCustomGame? -- Uranium's Nuzlocke/randomizer custom-ruleset flag",
        judgment_free=False,
    ),
    ConditionFamily(
        name="uranium_show_ruleset_settings",
        # 2 staged instances, "showRulesetSettings(1)".
        pattern=_rx(r"showRulesetSettings\(.*\)"),
        description="showRulesetSettings(N) -- Uranium's custom-ruleset menu guard",
        judgment_free=False,
    ),
    ConditionFamily(
        name="uranium_is_rock_smash_softlocked",
        # 3 staged instances, bare "isRockSmashSoftlocked?".
        pattern=_rx(r"isRockSmashSoftlocked\?"),
        description="isRockSmashSoftlocked? -- Uranium's Rock Smash softlock-prevention guard",
        judgment_free=False,
    ),
)

FAMILIES: tuple[ConditionFamily, ...] = _VANILLA_FAMILIES + _URANIUM_FAMILIES

# Duplicate-name guard, same reasoning as the head tables' guard (15.4): a
# second family silently shadowing a first would make `classify_condition`
# depend on table order instead of failing loud.
_seen_names: set[str] = set()
for _family in FAMILIES:
    if _family.name in _seen_names:
        raise ValueError(f"duplicate condition family name {_family.name!r}")
    _seen_names.add(_family.name)
del _seen_names


def _normalize(text: str) -> str:
    """Collapse whitespace runs to single spaces and strip the ends.

    `$Trainer.gender==0` and `$Trainer.gender == 0` both occur in the corpus
    and must classify identically; every family pattern is written expecting
    at most single-space gaps, so this is the only whitespace handling the
    patterns themselves need to do.
    """
    return " ".join(text.split())


def classify_condition(text: str) -> ConditionFamily | None:
    """Match a code-111/type-12 condition string against the family table.

    Returns the first matching family, or `None` if no family recognizes the
    shape -- the caller (`generator.py`) treats `None` as unclassified
    residue that still owes a human a citation. Order among `FAMILIES` does
    not matter for the corpus today (no two families' patterns overlap), but
    `classify_condition` is written to return the first match rather than
    assert exclusivity, so a future ambiguous pair fails soft (first-listed
    wins) rather than raising mid-generation.

    A compound boolean never classifies, whatever its operands look like.
    REDERIVATION_PLAN.md §14 ruling 2 is explicit that the compound outliers
    "need judgment and get a fallback bucket, not a pattern", so this is the
    ruling stated in code rather than left to the patterns to imply. It also
    closes a real hole: every family's argument list is `.*`, and under
    `fullmatch` a greedy `.*` happily spans a `)` and an operator, so
    `pbTrainerBattle(A) || pbTrainerBattle(B)` matched `pb_trainer_battle`
    before this guard -- a two-branch condition silently inheriting a
    single-call family's "no citation owed". Latent, not live: all 7
    compound-boolean texts in the 199-map corpus already fell through to
    `None` on their operands, so the guard changes no current row. It is
    here so that the day one does not, the row owes a citation rather than
    quietly claiming it does not.
    """
    normalized = _normalize(text)
    if "||" in normalized or "&&" in normalized:
        return None
    for family in FAMILIES:
        if family.pattern.fullmatch(normalized):
            return family
    return None
