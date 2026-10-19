"""Essentials move function codes -> the engine's move effects.

Generic to every Essentials game: a code means the same thing in each
(`086__PokeBattle_MoveEffects.rb`). Only the codes some generated move has
needed are listed; anything else fails loud, and a game's own custom codes are
spelled out per move in its rulings file instead.

Essentials runs an effect in one of two places, and the engine's chance field
follows from which:
  * `pbAdditionalEffect` -- rolls the move's effect chance (an additional
    effect; `chance` is the move's effect_chance, and 0 means it never fires).
  * `pbEffect` -- always happens when the move hits (a primary effect; the
    engine's `chance = 0`).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AddedEffect:
    move_effect: str
    #: "effect_chance" (roll the move's chance) or "always" (primary).
    chance: str = "always"
    self_: bool = False
    extra: tuple[tuple[str, str], ...] = ()   # further fields, e.g. multistring


@dataclass(frozen=True)
class EffectSpec:
    effect: str
    added: tuple[AddedEffect, ...] = ()
    argument: str | None = None
    #: Extra bool/int MoveInfo fields the effect needs, e.g. damagesUnderwater.
    fields: tuple[tuple[str, str], ...] = field(default=())


FUNCTION_CODES: dict[int, EffectSpec] = {
    0x000: EffectSpec("EFFECT_HIT"),
    0x007: EffectSpec("EFFECT_HIT", (AddedEffect("MOVE_EFFECT_PARALYSIS", "effect_chance"),)),
    0x00A: EffectSpec("EFFECT_HIT", (AddedEffect("MOVE_EFFECT_BURN", "effect_chance"),)),
    # Focus Energy on the user, as a damaging move's additional effect.
    0x023: EffectSpec("EFFECT_HIT", (AddedEffect("MOVE_EFFECT_RPG2GBA_FOCUS_ENERGY",
                                                 "effect_chance", self_=True),)),
    0x043: EffectSpec("EFFECT_HIT", (AddedEffect("MOVE_EFFECT_DEF_MINUS_1", "effect_chance"),)),
    0x047: EffectSpec("EFFECT_HIT", (AddedEffect("MOVE_EFFECT_ACC_MINUS_1", "effect_chance"),)),
    # Trapping (Bind's family). The wrap message is Wrap's ("was wrapped by").
    0x0CF: EffectSpec("EFFECT_HIT", (AddedEffect(
        "MOVE_EFFECT_WRAP", extra=(("multistring.wrapped", "B_MSG_WRAPPED_WRAP"),)),)),
    # Whirlpool: trapping, and hits a target that is underwater (Dive).
    0x0D0: EffectSpec("EFFECT_HIT", (AddedEffect(
        "MOVE_EFFECT_WRAP", extra=(("multistring.wrapped", "B_MSG_WRAPPED_WHIRLPOOL"),)),),
        fields=(("damagesUnderwater", "TRUE"),)),
    0x0D6: EffectSpec("EFFECT_ROOST"),
    0x0DD: EffectSpec("EFFECT_ABSORB", argument=".absorbPercentage = 50"),
    0x109: EffectSpec("EFFECT_HIT", (AddedEffect("MOVE_EFFECT_PAYDAY"),)),
    0x122: EffectSpec("EFFECT_PSYSHOCK"),
}


def effect_for(code: int, label: str) -> EffectSpec:
    spec = FUNCTION_CODES.get(code)
    if spec is None:
        raise ValueError(
            f"{label}: Essentials function code {code:#05x} has no engine mapping; add it "
            "to battle_converter/function_codes.py or give the move an effect in its ruling")
    return spec
