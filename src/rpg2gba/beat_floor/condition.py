"""Condition-family extractors for the generic beat floor (REDERIVATION_PLAN.md
§16.3 C4, "C4 shape" (a)).

One extractor per `chapter_manifest.conditions.ConditionFamily` (keyed by
`family.name`), not per code-111 type. A code-111 type-12 condition's
extractor contributes to the row ENCLOSING the 111 -- the condition itself
runs there, not in either arm (assertion.py's `ConditionFamilyExtractor`
docstring; `conditions.py`'s own module docstring, REDERIVATION_PLAN.md
§16.3 C4 design).

Most families are pure predicates: they read modelled or unmodelled state
and branch on it, with no side effect of their own (`get_character(N)
.onEvent?`, `$game_player.x==N`, `$PokemonGlobal.surfing`, ...) --
`story_state.extract` already turns the ones over modelled keys into the
row's own reads, so these contribute nothing further here (`_no_assertion`).
A handful of families are the CALL that performs the guarded effect itself
(`Kernel.pbItemBall` grants the item as a side effect of returning `true`;
`pbTrainerBattle` IS the battle) -- those get a real assertion, parsed from
the same condition text `classify_condition` already matched.
"""
from __future__ import annotations

import re

from rpg2gba.beat_floor.assertion import (
    ConditionFamilyExtractor,
    ExtractContext,
    ExtractResult,
    FloorAssertion,
    FloorRefusal,
    make_params,
)
from rpg2gba.chapter_manifest.conditions import classify_condition
from rpg2gba.conversion_agent.transpiler import _RECEIVE_ITEM_RE

CODE_CONDITION = 111


def extract_condition(condition_text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    family = classify_condition(condition_text)
    if family is None:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="unclassified_condition", list_index=list_index,
            code=CODE_CONDITION, detail=f"no family matches: {condition_text[:120]!r}",
        ),)
    extractor = CONDITION_FAMILY_EXTRACTORS.get(family.name)
    if extractor is None:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="no_condition_extractor", list_index=list_index,
            code=CODE_CONDITION, detail=f"family {family.name!r} has no extractor",
        ),)
    return extractor(condition_text, list_index, ctx)


# --- shared builders --------------------------------------------------

def _no_assertion(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    """Pure predicate: reads only, no side effect of its own (a story_state
    guard, modelled or not -- either way nothing for the floor to add)."""
    return (), ()


# --- item / berry grants ------------------------------------------------

_ITEM_BALL_RE = re.compile(
    r"^\s*Kernel\.pbItemBall\(\s*(?:::)?PBItems::(\w+)\s*(?:,\s*(\d+)\s*)?\)\s*$"
)


# Kernel.pbItemBall(ITEM) -- 101__PField_Field.rb:2303-2371 -- the guard call
# IS the grant: returns $PokemonBag.pbStoreItem(...), true on success. The
# item symbol is the condition text's own literal argument.
def _extract_pb_item_ball(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    m = _ITEM_BALL_RE.match(text.strip())
    if not m:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index,
            code=CODE_CONDITION, detail=f"pbItemBall: not a bare literal call: {text[:120]!r}",
        ),)
    symbol, qty = m.group(1), m.group(2)
    return (FloorAssertion(
        row_id=ctx.row_id, kind="item_grant", list_index=list_index, code=CODE_CONDITION,
        params=make_params(item=symbol, quantity=int(qty) if qty else 1), tag="state",
    ),), ()


# Kernel.pbReceiveItem(ITEM[, qty[, name]]) as a code-111 guard -- same call,
# same shape, as script.py's bare-statement idiom; reuses the same regex
# (CLAUDE.md §4.3).
def _extract_pb_receive_item(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    m = _RECEIVE_ITEM_RE.match(text.strip())
    if not m:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index,
            code=CODE_CONDITION, detail=f"pbReceiveItem: not a bare literal call: {text[:120]!r}",
        ),)
    symbol, qty = m.group(1), m.group(2)
    return (FloorAssertion(
        row_id=ctx.row_id, kind="item_grant", list_index=list_index, code=CODE_CONDITION,
        params=make_params(item=symbol, quantity=int(qty) if qty else 1), tag="state",
    ),), ()


_PICK_BERRY_RE = re.compile(
    r"^\s*pbPickBerry\(\s*(?:::)?PBItems::(\w+)\s*(?:,\s*(\d+)\s*)?\)\s*$"
)


# pbPickBerry(ITEM, n=1) -- 109_PField_BerryPlants.rb:616-625 -- harvest
# grant, literal item + optional quantity (default 1, per the Ruby default).
def _extract_pb_pick_berry(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    m = _PICK_BERRY_RE.match(text.strip())
    if not m:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index,
            code=CODE_CONDITION, detail=f"pbPickBerry: not a bare literal call: {text[:120]!r}",
        ),)
    symbol, qty = m.group(1), m.group(2)
    return (FloorAssertion(
        row_id=ctx.row_id, kind="item_grant", list_index=list_index, code=CODE_CONDITION,
        params=make_params(item=symbol, quantity=int(qty) if qty else 1), tag="state",
    ),), ()


# --- battles ---------------------------------------------------------

_TRAINER_BATTLE_RE = re.compile(
    r"pb(?:Double)?TrainerBattle\(\s*(?:::)?PBTrainers::([A-Za-z0-9_]+)\s*,\s*\"([^\"]*)\""
)


# pbTrainerBattle(TRAINERID, "NAME", ...) / pbDoubleTrainerBattle(...) --
# 115_PTrainer_NPCTrainers.rb:358-549 -- the trainer id and display name are
# always the first two positional args and always literal in the corpus;
# later args (party size, canlose, ...) aren't needed for identity.
def _extract_pb_trainer_battle(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    m = _TRAINER_BATTLE_RE.search(text)
    if not m:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index,
            code=CODE_CONDITION,
            detail=f"pbTrainerBattle: no literal trainer id/name: {text[:120]!r}",
        ),)
    trainer_type, name = m.group(1), m.group(2)
    return (FloorAssertion(
        row_id=ctx.row_id, kind="battle", list_index=list_index, code=CODE_CONDITION,
        params=make_params(kind="trainer", trainer_type=trainer_type, name=name),
    ),), ()


_WILD_BATTLE_RE = re.compile(
    r"^\s*pbWildBattle\(\s*(?:::)?PBSpecies::(\w+)\s*,\s*(\d+)\s*\)\s*$"
)


# pbWildBattle(SPECIES, level) -- corpus-wide-only family (0 staged CH01-
# CH05 instances), same forced-battle choreography as pbTrainerBattle per
# conditions.py's own description (shares PokeBattle_Battle's decision
# path). Included for completeness per C4 shape's "cover every family".
def _extract_pb_wild_battle(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    m = _WILD_BATTLE_RE.match(text.strip())
    if not m:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index,
            code=CODE_CONDITION, detail=f"pbWildBattle: not a bare literal call: {text[:120]!r}",
        ),)
    species, level = m.group(1), int(m.group(2))
    return (FloorAssertion(
        row_id=ctx.row_id, kind="battle", list_index=list_index, code=CODE_CONDITION,
        params=make_params(kind="wild", species=species, level=level),
    ),), ()


# --- rock smash --------------------------------------------------------

# Kernel.pbRockSmash / Kernel.pbCoralBreak -- 103__PField_HiddenMoves.rb:
# 385-410 -- the guard call itself performs the smash choreography
# (messages, animation) once the capability/confirm gate passes; no literal
# identity field survives to assert (the broken terrain's erasure, if any,
# is a separate erase/self-switch command elsewhere on the page, covered by
# its own extractor) -- visual per R11's "best kind or visual" allowance.
def _extract_pb_rock_smash(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    return (FloorAssertion(
        row_id=ctx.row_id, kind="visual", list_index=list_index, code=CODE_CONDITION,
        params=make_params(code=CODE_CONDITION, detail="pb_rock_smash"), tag="visual",
    ),), ()


# --- jvGiveReward / jvNextReward ----------------------------------------

# uranium_jv_give_reward (and, before 2026-10-15, jvNextReward too) matches jvGiveReward (213_Bambo_Reward.rb:33-45)
# and jvNextReward/jvNextRewardPhone (pure reads, no side effect).
# Dispatched by which head the condition text names.
#
# A `if jvGiveReward` condition tests jvGiveReward's RETURN VALUE, not which
# rung fires -- a different question from R2's (script.py's bare-call
# extractor). Reading the Ruby again: the return is `item`, which tracks
# whether `Kernel.pbReceiveItem` succeeded, i.e. bag-space success/failure.
# Bag capacity isn't modelled (nothing in `story_state` tracks bag
# occupancy), so this can't resolve either -- but for a genuinely different
# reason than the R2 refusal, hence its own reason code.
def _extract_uranium_jv_reward(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    if "jvGiveReward" in text:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="bag_capacity_unmodelled", list_index=list_index,
            code=CODE_CONDITION,
            detail=(
                "jvGiveReward: condition tests the return value, which is "
                "Kernel.pbReceiveItem's bag-space success/failure -- bag "
                "capacity is not modelled"
            ),
        ),)
    return (), ()


# --- registry ------------------------------------------------------------

CONDITION_FAMILY_EXTRACTORS: dict[str, ConditionFamilyExtractor] = {
    # pure predicates -- staged in CH01-CH05.
    "get_character_on_event": _no_assertion,
    "game_player_axis": _no_assertion,
    "pokemon_global_attr": _no_assertion,
    "pb_phone_battle_count": _no_assertion,
    "game_variables_cmp": _no_assertion,
    "pokemon_bag_query": _no_assertion,
    "uranium_is_rock_smash_softlocked": _no_assertion,
    "pb_has_species": _no_assertion,
    "uranium_is_custom_game": _no_assertion,
    "uranium_show_ruleset_settings": _no_assertion,
    "pb_next_mystery_gift_id": _no_assertion,
    "pb_pokerus": _no_assertion,

    # pure predicates -- corpus-wide-only families, covered per C4 shape's
    # "every other family that's trivially a pure predicate".
    "trainer_attr": _no_assertion,
    "input_trigger": _no_assertion,
    "distance_checker": _no_assertion,
    "pb_get_pokemon_egg": _no_assertion,
    "pb_get_pokemon_shadow_rescue": _no_assertion,
    "is_temp_switch_off": _no_assertion,
    "pb_day_care_deposited": _no_assertion,
    "pb_egg_generated": _no_assertion,
    "time_of_day": _no_assertion,

    # side-effecting.
    "pb_trainer_battle": _extract_pb_trainer_battle,
    "pb_wild_battle": _extract_pb_wild_battle,
    "pb_item_ball": _extract_pb_item_ball,
    "pb_receive_item": _extract_pb_receive_item,
    "pb_rock_smash": _extract_pb_rock_smash,
    "pb_pick_berry": _extract_pb_pick_berry,
    "uranium_jv_next_reward": _no_assertion,
    "uranium_jv_give_reward": _extract_uranium_jv_reward,
}
