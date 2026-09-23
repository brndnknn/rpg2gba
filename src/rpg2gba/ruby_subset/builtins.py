"""Builtin call/attribute tables for the embedded-Ruby subset evaluator
(REDERIVATION_PLAN.md C8 stage 2, "Builtins" -- CLAUDE.md §4.3: one declared
table per concept, not `if name ==` chains scattered through evaluate.py).

Every table here is data, keyed either by a bare call name (`"pbGet"`), a
`(namespace, attribute)` pair for zero-arg attribute reads/writes on a known
global (`("$PokemonGlobal", "runningShoes")`), or a dotted "head" string for
a namespaced call with arguments (`"$PokemonBag.pbDeleteItem"`) -- the same
dotted-head convention `chapter_atlas.census._script_head` and
`beat_floor.script.SCRIPT_HEAD_EXTRACTORS` already use, so a table entry
here reads the same as the corpus measurements that motivated it.

`Kernel.` is normalized away before any lookup here (evaluate.py's job, one
normalization site, mirroring `census._script_head`) -- so `Kernel.pbSetPokemonCenter`
and bare `pbSetPokemonCenter` are the same table entry.

Every table was built by scanning every real 355/655 script block and 111
type-12 condition in CH01-CH05 (`tests/test_ruby_subset_evaluate.py`'s
real-corpus gate) for every head/attribute actually used, then classifying
each against `reference/scripts_dump/*.rb`. Nothing here is invented --
where a head's exact story-state effect wasn't specified by the C8 design
paragraphs, the classifying comment says so and the report to the lead
calls it out as a judgment call.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "EngineAttribute",
    "InputSpec",
    "NAMESPACE_GLOBALS",
    "NAMESPACE_CONSTS",
    "ENGINE_ATTRIBUTES",
    "PARTY_MODEL_ATTRS",
    "PARTY_MODEL_CALLS",
    "STATIC_PREDICATE_ATTRS",
    "NOOP_ATTRS",
    "PASSTHROUGH_ENGINE_ATTRS",
    "CONST_VALUES",
    "NO_PORT_CALLS",
    "CONSTRUCTOR_CALLS",
    "STATIC_FALSE_CALLS",
    "STATIC_ZERO_CALLS",
    "EFFECT_CALLS",
    "INPUT_CALLS",
    "RANDOM_SPECIES_CALL",
]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STRIP_LIST_PATH = _REPO_ROOT / "reference" / "strip_list.json"


@dataclass(frozen=True)
class EngineAttribute:
    """A `$Global.attr` that reads/writes an engine-held unlock flag rather
    than any RMXP switch/variable (REDERIVATION_PLAN.md C8 shape ruling
    (b)). `key_name` is the `state.EngineKey.name`; `flag` is the native
    pokeemerald-expansion `FLAG_SYS_*` it corresponds to (asserted to exist
    by a §4.7 test, not trusted from this table alone)."""

    key_name: str
    flag: str


@dataclass(frozen=True)
class InputSpec:
    """A nondeterministic input call (C8 shape ruling (c)): `kind` labels
    the `InputSource`, `domain` is every value in source/semantic order --
    `domain[0]` is R10's "main path" outcome."""

    kind: str
    domain: tuple


# --- namespaces --------------------------------------------------------
# Receivers that name an engine object, not a value this evaluator can
# compute generically -- Call dispatch routes these through the attribute/
# head tables below instead of evaluating the receiver.

NAMESPACE_GLOBALS: frozenset[str] = frozenset({
    "$PokemonGlobal", "$Trainer", "$PokemonBag", "$game_map", "$game_player",
})

# Constant-named receivers whose methods dispatch like namespaced calls
# (`Foo.bar`). Empty in CH01-CH05 once strip-listed CEs are skipped.
NAMESPACE_CONSTS: frozenset[str] = frozenset()


# --- category 2: engine unlock attributes -------------------------------
# REDERIVATION_PLAN.md C8 shape ruling (b), the four named entries.

ENGINE_ATTRIBUTES: dict[tuple[str, str], EngineAttribute] = {
    ("$PokemonGlobal", "runningShoes"): EngineAttribute("running_shoes", "FLAG_SYS_B_DASH"),
    ("$Trainer", "pokedex"): EngineAttribute("pokedex", "FLAG_SYS_POKEDEX_GET"),
    ("$Trainer", "pokegear"): EngineAttribute("pokegear", "FLAG_SYS_POKENAV_GET"),
    ("$PokemonGlobal", "seenStorageCreator"): EngineAttribute("seen_storage_creator", "FLAG_SYS_PC_LANETTE"),
}


# --- category 4: party/dex quantities -> party_model --------------------
# Explicit brief scope: $Trainer.party / pokedexSeen / pokedexOwned.
# `$Trainer.party.length` refuses through `.party` itself (chain
# evaluation order), not a separate table entry.

PARTY_MODEL_ATTRS: frozenset[tuple[str, str]] = frozenset({
    ("$Trainer", "party"),
    ("$Trainer", "pokedexSeen"),
    ("$Trainer", "pokedexOwned"),
})

# Bare calls whose Ruby body (reference/scripts_dump/*.rb) reads $Trainer's
# party/dex/phone-trainer state directly -- pbGetPokemon/pbHasSpecies? are
# the brief's own examples; pbPhoneBattleCount, isRockSmashSoftlocked?, and
# jvNextReward are this evaluator's own extension of the same bucket
# (measured against the real corpus, C8 shape ruling (b): "party_model...
# also absorbs the existing unmodelled party families in conditions.py" --
# chapter_manifest/conditions.py's pb_phone_battle_count family is one of
# those, and isRockSmashSoftlocked?/jvNextReward directly `for pkmn in
# $Trainer.party` / read `$Trainer.pokedexOwned` in their own Ruby bodies,
# same as pbHasSpecies? does). Judgment call -- see report to lead.
PARTY_MODEL_CALLS: frozenset[str] = frozenset({
    "pbGetPokemon",
    "pbHasSpecies?",
    "pbPhoneBattleCount",
    "isRockSmashSoftlocked?",
    "jvNextReward",
})


# --- category 3: static predicates / no-ops -----------------------------


def _load_static_predicates() -> dict[tuple[str, str], bool]:
    """`$PokemonGlobal.randomizer` -> False, sourced from
    `reference/strip_list.json`'s `static_predicates` (CLAUDE.md §4.3 --
    load the value, don't hardcode it). `$PokemonGlobal.nuzlocke` -> False
    is NOT in strip_list.json (no `static_predicates` entry exists for it);
    it's hardcoded here per the brief's own citation
    (`reference/scripts_dump/220_Custom_Mode.rb:212-223`): no Nuzlocke mode
    exists in this port at all, so the flag that would enable it is always
    false, same reasoning as `nuzlocke_heal`'s no-op (below)."""
    predicates: dict[tuple[str, str], bool] = {
        ("$PokemonGlobal", "nuzlocke"): False,
    }
    if _STRIP_LIST_PATH.exists():
        data = json.loads(_STRIP_LIST_PATH.read_text(encoding="utf-8"))
        for entry in data.get("static_predicates", []):
            predicate = entry["predicate"]
            if "." not in predicate:
                continue
            ns, attr = predicate.split(".", 1)
            predicates[(ns, attr)] = bool(entry["value"])
    return predicates


STATIC_PREDICATE_ATTRS: dict[tuple[str, str], bool] = _load_static_predicates()

# `$game_map.need_refresh = ...` -- redraw hint, presentation only.
NOOP_ATTRS: frozenset[tuple[str, str]] = frozenset({
    ("$game_map", "need_refresh"),
})

# `$PokemonGlobal.surfing` -- read directly in the CH01-CH05 corpus
# (a bare 111 type-12 condition), but not one of the four engine-unlock
# attributes the C8 shape/design paragraphs name, and not a static
# predicate either (surf capability is real and toggles in play, unlike
# randomizer/nuzlocke which never exist in this port). Evaluator's own
# extension, explicitly registered (not a silent unknown-attribute
# fallback, CLAUDE.md §4.5): read through a synthetic EngineKey so a
# FixedOracle/enumerator can still drive it, default False. Judgment call
# -- see report to lead; no consumer elsewhere in `src/` yet, same
# footnote strip_list.json already carries for `static_predicates`.
PASSTHROUGH_ENGINE_ATTRS: dict[tuple[str, str], str] = {
    ("$PokemonGlobal", "surfing"): "pokemonglobal_surfing",
}


# --- category 7: pure constants ------------------------------------------
# BR_WIN/BR_LOSS/BR_DRAW are plain (unscoped) Ruby constants
# (reference/scripts_dump/216_Custom_Trainers.rb:6-8), not PBSpecies::-style
# scoped ones -- int-valued so `result == BR_WIN` type-checks the way real
# Ruby does (an int never == a bool, see evaluate.py's `_ruby_eq`), which
# is why the battle-result InputSpecs below use an int domain instead of a
# bare bool one.
CONST_VALUES: dict[str, int] = {
    "BR_WIN": 1,
    "BR_LOSS": 2,
    "BR_DRAW": 5,
}


# --- category 8: no-port --------------------------------------------------

NO_PORT_CALLS: frozenset[str] = frozenset({"system"})


# --- constructors: opaque values, not effects -----------------------------
# `createPhoneTrainer` builds the local object `customTrainerBattle`/
# `pbPhoneIncrement` consume; `get_character` returns an event/character
# reference passed to visual calls (pbNoticePlayer). Neither has an
# assertable effect of its own (beat_floor/script.py already treats
# createPhoneTrainer as `_no_assertion` for the same reason) -- the
# evaluator returns an opaque marker value threaded through, not recorded
# as an Effect.
CONSTRUCTOR_CALLS: frozenset[str] = frozenset({
    "createPhoneTrainer",
    "get_character",
})


# --- static-false bare/namespaced calls -----------------------------------
# `isCustomGame?` (220_Custom_Mode.rb:244-256) ORs a list of
# $PokemonGlobal.nuzlocke*/challengemode/randomizer fields -- every one of
# them is a Nuzlocke/randomizer-mode flag, and neither game mode exists in
# this port (same reasoning as STATIC_PREDICATE_ATTRS above), so the
# function as a whole is statically False. (The online features' `GTS.open`
# etc. are deliberately absent: they live only in strip-listed CEs 4/5/6,
# which no consumer evaluates, so reaching one is a real gap and refuses.)
STATIC_FALSE_CALLS: frozenset[str] = frozenset({
    "isCustomGame?",
})

# `pbNextMysteryGiftID>0` (real corpus, e.g. map067/ev009/p1) -- the mystery
# gift subsystem isn't ported (beat_floor/script.py already tags
# pbNextMysteryGiftID/pbReceiveMysteryGift `service` for the same reason);
# its ID accessor is compared numerically, so it needs an int, not a bool.
# 0 (no gift pending) is the natural "feature not ported" answer, same
# static-value reasoning as STATIC_FALSE_CALLS above. Judgment call -- see
# report to lead.
STATIC_ZERO_CALLS: frozenset[str] = frozenset({
    "pbNextMysteryGiftID",
})


# --- category 5: effect calls ---------------------------------------------
# Side-effecting heads with no further story-state modelling -- recorded as
# an `Effect(name, evaluated_args, span)` and nothing else. Built from
# `beat_floor/script.py`'s `SCRIPT_HEAD_EXTRACTORS` registry (every head it
# knows is by definition real corpus, per that module's own docstring) plus
# the CH01-CH05 scan for heads it doesn't cover (state-accessor heads like
# pbSet/pbGet/pbSetSelfSwitch are covered by their own dedicated dispatch in
# evaluate.py, not here -- same "don't re-derive a second source of truth"
# discipline beat_floor/script.py documents for itself).
EFFECT_CALLS: frozenset[str] = frozenset({
    "pbCallBub",
    "pbNoticePlayer",
    "pbTrainerEnd",
    "pbCaveEntrance",
    "pbCaveExit",
    "pbPushThisBoulder",
    "pbCancelVehicles",
    "pbShowMap",
    "pbBerryPlant",
    "pbPhoneRegisterBattle",
    "pbPhoneRegisterNPC",
    "pbRockSmashRandomEncounter",
    "pbSave",
    "pbPokeCenterPC",
    "pbTrainerPC",
    "pbStarterSelector",
    "pbChooseNuclearCurePokemon",
    "displayNinjaLetter",
    "pbNextMysteryGiftID",
    "pbReceiveMysteryGift",
    "pbTrainerIntro",
    "pbEraseThisEvent",
    "pbReceiveItem",
    "pbTransferPlayer",
    "pbAddPokemon",
    "pbPokemonMart",
    "jvGiveReward",
    "pbPhoneIncrement",
    "$PokemonBag.pbDeleteItem",
    "$PokemonBag.pbStoreItem",
    "customTrainerBattle",
    "pbTrainerBattle",
    "pbDoubleTrainerBattle",
    "pbWildBattle",
    "pbItemBall",
    "pbPickBerry",
})


# --- category 6: input calls -----------------------------------------------
# Nondeterministic-return heads: the value is read via `oracle.choose`, not
# computed. `domain[0]` is always the "main path" per R10. Battle heads are
# ALSO in EFFECT_CALLS (recorded both, per the brief).
INPUT_CALLS: dict[str, InputSpec] = {
    # 115_PTrainer_NPCTrainers.rb:358-549 -- Kernel.pbTrainerBattle returns
    # (decision==1): a plain boolean, win=True first.
    "pbTrainerBattle": InputSpec(kind="battle_result", domain=(True, False)),
    "pbDoubleTrainerBattle": InputSpec(kind="battle_result", domain=(True, False)),
    # 103__PField_HiddenMoves.rb-adjacent: same decision path as
    # pbTrainerBattle (chapter_manifest/conditions.py pb_wild_battle family).
    "pbWildBattle": InputSpec(kind="battle_result", domain=(True, False)),
    # 216_Custom_Trainers.rb:65-... returns BR_WIN/BR_LOSS (int constants,
    # not a bool) -- domain must be the actual int codes so
    # `result == BR_WIN` type-checks per real Ruby int/bool `==` semantics
    # (see CONST_VALUES comment above). Win (BR_WIN=1) first.
    "customTrainerBattle": InputSpec(kind="battle_result", domain=(1, 2)),
    # Kernel.pbConfirmMessage / bare pbConfirmMessage -- yes/no prompt.
    "pbConfirmMessage": InputSpec(kind="confirm", domain=(True, False)),
    "Kernel.pbConfirmMessage": InputSpec(kind="confirm", domain=(True, False)),
    # 220_Custom_Mode.rb:776-782 -- opens a menu screen; the player's own
    # selection decides the branch (chapter_manifest/conditions.py
    # uranium_show_ruleset_settings family: "both arms player input").
    "showRulesetSettings": InputSpec(kind="menu_choice", domain=(True, False)),
    # 101__PField_Field.rb:2303-2371/2373-2401 -- returns
    # $PokemonBag.pbStoreItem's own true/false (room in the bag or not);
    # bag contents aren't modelled (pokemon_bag_query family), so this is
    # genuinely nondeterministic from this evaluator's point of view, same
    # as pbReceiveItem's sibling family (pb_receive_item: "then=always,
    # else=harness full_bag") -- success (True) first, the ordinary path.
    "$PokemonBag.pbStoreItem": InputSpec(kind="bag_store", domain=(True, False)),
    "pbItemBall": InputSpec(kind="bag_store", domain=(True, False)),
    # 103__PField_HiddenMoves.rb:385-410 -- true only past a badge+move
    # capability gate AND a confirm; capability state isn't modelled
    # (pb_rock_smash family: "then=capability rock_smash, else=always") --
    # both arms genuinely reachable and neither is derivable from modelled
    # state, so this is an input rather than a static value. Judgment call:
    # domain order (True=capability present first) follows this table's
    # general "yes/success first" convention, not a documented R10 citation
    # for this specific head -- see report to lead.
    "pbRockSmash": InputSpec(kind="capability", domain=(True, False)),
    "pbCoralBreak": InputSpec(kind="capability", domain=(True, False)),
    # 109_PField_BerryPlants.rb:616+ -- confirms "Want to pick it?" before
    # a bag-capacity check; both arms player input (pb_pick_berry family).
    "pbPickBerry": InputSpec(kind="confirm", domain=(True, False)),
    # Not found as a head in CH01-CH05 but named in
    # chapter_manifest/conditions.py's pb_pokerus family docstring;
    # registered defensively so a corpus refresh that stages it doesn't
    # need a new table entry. RNG-decided, not modelled -- input.
    "pbPokerus?": InputSpec(kind="random_state", domain=(True, False)),
}

# 220_Custom_Mode.rb:361 "Used for starter" -- a random species picker (the
# randomizer-mode starter path). Never actually reachable in this port
# (randomizer is statically False, C8 shape ruling), but its own script
# block is unconditioned text in the corpus (map050/ev019's sibling idiom:
# "pbAddPokemon(pbGetRandomPokemonSpecies,5)"), so the evaluator still needs
# a value for it rather than refusing. Judgment call: a full PBSpecies
# domain would be huge and pointless for genuinely dead content, so this
# gets its own sentinel head handled directly in evaluate.py (its domain is
# a single opaque ConstRef, which this module can't construct without an
# import cycle with evaluate.py) -- see report to lead.
RANDOM_SPECIES_CALL = "pbGetRandomPokemonSpecies"
