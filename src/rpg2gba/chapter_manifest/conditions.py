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

**`time_of_day` is the one explicit exception to "a compound boolean never
classifies" (REDERIVATION_PLAN.md §16.3 C2 ruling (e), found by C2b's
triggered-common-event guard on real data).** Common event 51 (parallel,
gated on switch 51 GAME RUNNING) sets switch 105 DAY / 106 NIGHT from
`Time.now.hour<6||Time.now.hour>=20` (and its negation) every 200 frames --
a compound `||`/`&&` join of `Time.now.hour <cmp> N` clauses, and the ONLY
compound shape this table recognizes on purpose. `classify_condition`
special-cases it before the general "no compound classifies" guard.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# --- per-family arm outcome table (REDERIVATION_PLAN.md §16.3 C2, "C2 shape"
# paragraph (a)) --------------------------------------------------------
#
# Every family declares how ITS two arms (then/else of the code-111 whose
# condition text matched it) become live:
#
#   always     -- the enclosing scope's ordinary path: live whenever that
#                 scope is (a won battle, a stored item, the no-capability
#                 arm of a field move).
#   input      -- the player's position, facing, choice or button decides.
#   random     -- an RNG outcome decides (C2 ruling (c): every outcome is
#                 live and checked offline; a ROM walk asserts whichever the
#                 RNG produced is in the valid set).
#   state      -- evaluable from `story_state.state`'s modelled keys. `detail`
#                 names the shape (e.g. "game_variables_cmp"); the concrete
#                 Test(s) are synthesized at extraction time
#                 (`story_state.extract`), not baked into this static table,
#                 because the literal switch/variable id is per-instance.
#   fork       -- an engine transition (C3's territory). `detail` names it,
#                 e.g. "whiteout".
#   harness    -- reachable only in a contrived setup; `detail` names the
#                 missing primitive (e.g. "full_bag"). C2 ruling (b): this is
#                 a REAL branch arm, walked once the harness primitive
#                 exists -- never `unreachable:`.
#   capability -- `detail` names the capability token (e.g. "rock_smash").
#   unmodelled -- `detail` says what state would be needed and is never
#                 empty -- CLAUDE.md §4.5, a silent "we don't know" is not
#                 acceptable, an explicit one is.
#   dead       -- never live: the arm contradicts a `static_predicates`
#                 constant (`reference/strip_list.json`). No family here
#                 declares it; `story_state.extract` assigns it before family
#                 classification. `detail` names the predicate and its value.
OutcomeKind = Literal[
    "always", "input", "random", "state", "fork", "harness", "capability", "unmodelled", "dead",
]


@dataclass(frozen=True)
class ArmOutcome:
    """How one arm (then or else) of a family's code-111 becomes live.

    `detail` is required (non-empty) for every kind except `input`/`random`,
    which name no further token -- the player's own action or the RNG IS the
    detail.
    """

    kind: OutcomeKind
    detail: str = ""


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
    # Required (REDERIVATION_PLAN.md §16.3 C2): how the then-arm and the
    # else-arm of this family's code-111 each become live. See `ArmOutcome`
    # and `OutcomeKind` above for the vocabulary and C2a's citation rule --
    # every non-input/random kind is decided from what the called Ruby
    # ACTUALLY does (grepped in `reference/scripts_dump/`), cited in
    # `description` as a short trailing clause, never guessed.
    then_outcome: ArmOutcome
    else_outcome: ArmOutcome


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
        description=(
            "get_character(N).onEvent? -- self-switch-style event-running "
            "guard; Game_Event#onEvent? (022_Game_Event_v17.rb:117) compares "
            "the character's position to $game_player's -- a player-position "
            "read, both arms player input"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="input"),
        else_outcome=ArmOutcome(kind="input"),
    ),
    ConditionFamily(
        name="pb_trainer_battle",
        # 22 staged instances / 22 distinct texts -- every one differs only
        # in trainer id, name, and loss quote. The transpiler already
        # recognizes this head (census.py); this family just stops the
        # manifest from discarding the same information at the condition
        # layer.
        pattern=_rx(r"pb(?:Double)?TrainerBattle\(.*\)"),
        description=(
            "pbTrainerBattle(...) / pbDoubleTrainerBattle(...) -- trainer "
            "battle trigger; Kernel.pbTrainerBattle "
            "(115_PTrainer_NPCTrainers.rb:358-549) returns (decision==1) -- "
            "then=win, the ordinary path (always); on decision in {2,5} (loss/draw) with canlose=false "
            "(the argument's own default, and the only value seen in the "
            "CH01-CH05 corpus -- 0 canlose=true call sites, grepped) it calls "
            "Kernel.pbStartOver -- else=fork:whiteout. A canlose=true call "
            "site would make else a state-continuation instead; none exists "
            "in the corpus this family covers (R13 scope)"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="always"),
        else_outcome=ArmOutcome(kind="fork", detail="whiteout"),
    ),
    ConditionFamily(
        name="pb_item_ball",
        # 15 staged instances across 10 distinct item literals.
        pattern=_rx(r"Kernel\.pbItemBall\(.*\)"),
        description=(
            "Kernel.pbItemBall(ITEM) -- overworld item-ball grant guard; "
            "Kernel.pbItemBall (101__PField_Field.rb:2303-2371) returns "
            "$PokemonBag.pbStoreItem(...) -- true (then) if the bag has room, "
            "the ordinary path (always); false (else, 'Too bad... The Bag is "
            "full...') only with a full bag, the harness primitive 'full_bag'"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="always"),
        else_outcome=ArmOutcome(kind="harness", detail="full_bag"),
    ),
    ConditionFamily(
        name="pb_rock_smash",
        # 14 staged instances, all bare "Kernel.pbRockSmash". pbCoralBreak is
        # the corpus-wide sibling (36 instances, not in the staged 18 maps)
        # -- same shape, same guard role, folded in here rather than given
        # its own family.
        pattern=_rx(r"Kernel\.(?:pbRockSmash|pbCoralBreak)\??"),
        description=(
            "Kernel.pbRockSmash / Kernel.pbCoralBreak -- breakable-terrain "
            "guard; Kernel.pbRockSmash (103__PField_HiddenMoves.rb:385-410) "
            "returns true only past the badge AND (move OR Boxing Gloves) gate "
            "and a confirm -- then=capability rock_smash; it returns false "
            "without the capability or on a declined confirm, so else is the "
            "ordinary path (always)"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="capability", detail="rock_smash"),
        else_outcome=ArmOutcome(kind="always"),
    ),
    ConditionFamily(
        name="game_player_axis",
        # 12 staged instances, e.g. "$game_player.x==17", "$game_player.y<=43".
        pattern=_rx(r"\$game_player\.[xy]\s*" + _CMP + r"\s*-?\d+"),
        description="$game_player.x|y <cmp> N -- player-position gate, both arms player input",
        judgment_free=True,
        then_outcome=ArmOutcome(kind="input"),
        else_outcome=ArmOutcome(kind="input"),
    ),
    ConditionFamily(
        name="pb_receive_item",
        # 9 staged instances, e.g. "Kernel.pbReceiveItem(::PBItems::REVIVE)",
        # "Kernel.pbReceiveItem(::PBItems::POKeBALL,10)".
        pattern=_rx(r"Kernel\.pbReceiveItem\(.*\)"),
        description=(
            "Kernel.pbReceiveItem(ITEM[, qty[, name]]) -- item grant guard; "
            "Kernel.pbReceiveItem (101__PField_Field.rb:2373-2401+) returns "
            "$PokemonBag.pbStoreItem(...) the same way pbItemBall does -- "
            "then=always, else=harness 'full_bag'"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="always"),
        else_outcome=ArmOutcome(kind="harness", detail="full_bag"),
    ),
    ConditionFamily(
        name="pb_add_pokemon",
        # CH10 Map060 EV007 (3 instances): "Kernel.pbAddPokemon(:MAREEP, 12)".
        pattern=_rx(r"Kernel\.pbAddPokemon\(.*\)"),
        description=(
            "Kernel.pbAddPokemon(SPECIES, level) -- gift-Pokemon guard; "
            "pbAddPokemon (170__PSystem_Utilities.rb) returns false only when "
            "the party AND every box are full (pbBoxesFull?), else stores the "
            "mon and returns true -- then=always; storage-full is not a "
            "modelled state, so else is unmodelled (the transpiler's native "
            "gift flow ends the script there, Common_EventScript_NoMoreRoomForPokemon)"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="always"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="pokemon_storage_full"),
    ),
    ConditionFamily(
        name="trainer_money_literal_cmp",
        # CH10 Map060 EV007 (3 instances): "3800>$Trainer.money" -- the
        # literal-first spelling `trainer_attr` below does not match.
        pattern=_rx(r"-?\d+\s*" + _CMP + r"\s*\$Trainer\.money"),
        description=(
            "literal <cmp> $Trainer.money -- can-afford gate (transpiled to "
            "checkmoney); the player's money is not a modelled Switch/Variable "
            "key -- unmodelled both arms"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="$Trainer.money"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="$Trainer.money"),
    ),
    ConditionFamily(
        name="pb_phone_battle_count",
        # 8 staged instances, e.g. "pbPhoneBattleCount(PBTrainers::YOUNGSTER,\"Richey\")>=1".
        pattern=_rx(r"pbPhoneBattleCount\(.*\)\s*" + _CMP + r"\s*\d+"),
        description=(
            "pbPhoneBattleCount(TRAINER, NAME) <cmp> N -- rematch-count "
            "gate; pbPhoneBattleCount (133_PScreen_Phone.rb:120-126) returns "
            "a per-trainer rematch counter held in $Trainer's phone-trainer "
            "list, not a modelled Switch/Variable -- unmodelled both arms"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="phone_battle_count(trainer)"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="phone_battle_count(trainer)"),
    ),
    ConditionFamily(
        name="pokemon_global_attr",
        # 8 staged instances, e.g. "$PokemonGlobal.surfing",
        # "$PokemonGlobal.randomizer", "$PokemonGlobal.nuzlocke==true". The
        # corpus-wide sibling "!$PokemonGlobal.surfing" (negated, bare) is
        # covered by the optional leading "!".
        pattern=_rx(r"!?\$PokemonGlobal\.\w+(?:\s*" + _CMP + r"\s*(?:true|false|-?\d+))?"),
        description=(
            "$PokemonGlobal.<attr>[ <cmp> literal] -- global play-state flag "
            "read; $PokemonGlobal is a PokemonGlobalMetadata instance, not a "
            "modelled Switch/Variable/SelfSwitch -- unmodelled both arms "
            "(worked example, REDERIVATION_PLAN.md §16.3 C2 design)"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="$PokemonGlobal.<attr>"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="$PokemonGlobal.<attr>"),
    ),
    ConditionFamily(
        name="pb_pick_berry",
        # 5 staged instances, e.g. "pbPickBerry(PBItems::ORANBERRY,2)".
        pattern=_rx(r"pbPickBerry\(.*\)"),
        description=(
            "pbPickBerry(ITEM, n) -- berry-tree harvest guard; pbPickBerry "
            "(109_PField_BerryPlants.rb:616+) asks Kernel.pbConfirmMessage "
            "'Want to pick it?' before its $PokemonBag.pbCanStore? check, so "
            "the player's yes/no reaches both arms -- both arms player input"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="input"),
        else_outcome=ArmOutcome(kind="input"),
    ),
    ConditionFamily(
        name="game_variables_cmp",
        # 4 staged instances, e.g. "$game_variables[1]==0".
        pattern=_rx(r"\$game_variables\[\d+\]\s*" + _CMP + r"\s*-?\d+"),
        description=(
            "$game_variables[N] <cmp> M -- raw variable comparison; parses "
            "directly into a Variable Test (extract.py builds the concrete "
            "Test/negation from the literal id and value at extraction time, "
            "per C2's worked example), both arms modelled state"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="state", detail="game_variables_cmp"),
        else_outcome=ArmOutcome(kind="state", detail="game_variables_cmp"),
    ),
    ConditionFamily(
        name="pokemon_bag_query",
        # 3 staged instances ($PokemonBag.pbQuantity) + 1 (pbStoreItem);
        # corpus-wide also seen with a bare symbol argument
        # ("$PokemonBag.pbQuantity(:FERRYPASS)>0"), which `.*` already covers.
        pattern=_rx(r"\$PokemonBag\.(?:pbQuantity|pbStoreItem)\(.*\)(?:\s*" + _CMP + r"\s*\d+)?"),
        description=(
            "$PokemonBag.pbQuantity|pbStoreItem(ITEM)[ <cmp> N] -- "
            "inventory-quantity gate; current bag contents are not a "
            "modelled key -- unmodelled both arms, harness-adjacent but a "
            "distinct primitive from bag-capacity ('full_bag')"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="bag_contents"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="bag_contents"),
    ),
    ConditionFamily(
        name="pb_has_species",
        # 3 staged instances, e.g. "pbHasSpecies?(::PBSpecies::RAPTORCH)".
        pattern=_rx(r"pbHasSpecies\?\(.*\)"),
        description=(
            "pbHasSpecies?(SPECIES) -- party/box species-ownership guard; "
            "pbHasSpecies? (170__PSystem_Utilities.rb:2091-2099) scans "
            "$Trainer.party -- not a modelled key, unmodelled both arms "
            "(worked example, REDERIVATION_PLAN.md §16.3 C2 design)"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="party_has_species"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="party_has_species"),
    ),
    ConditionFamily(
        name="pb_next_mystery_gift_id",
        # 1 staged instance, "pbNextMysteryGiftID>0".
        pattern=_rx(r"pbNextMysteryGiftID\s*" + _CMP + r"\s*\d+"),
        description=(
            "pbNextMysteryGiftID <cmp> N -- pending mystery-gift guard; "
            "pbNextMysteryGiftID (147__PScreen_MysteryGift.rb:431-435) scans "
            "$Trainer.mysterygift -- not a modelled key, unmodelled both arms"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="mystery_gift_queue"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="mystery_gift_queue"),
    ),
    ConditionFamily(
        name="pb_pokerus",
        # 1 staged instance, "Kernel.pbPokerus?".
        pattern=_rx(r"Kernel\.pbPokerus\?"),
        description=(
            "Kernel.pbPokerus? -- Pokerus-infection guard, an RNG roll "
            "(vanilla Essentials' PokeBattle_Pokemon#pbPokerus is a chance "
            "check, not a modelled key) -- random both arms"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="random"),
        else_outcome=ArmOutcome(kind="random"),
    ),
    # --- corpus-wide-only shapes: zero staged instances today, recognized
    # now so a later chapter's manifest doesn't have to rediscover them. ---
    ConditionFamily(
        name="pb_wild_battle",
        # 4 corpus-wide, e.g. "pbWildBattle(PBSpecies::LINKITE,38)".
        pattern=_rx(r"pbWildBattle\(.*\)"),
        description=(
            "pbWildBattle(SPECIES, level) -- scripted wild encounter trigger; "
            "shares PokeBattle_Battle's decision path with pbTrainerBattle "
            "(a forced encounter with no canlose escape) -- then=win (always), "
            "else=fork:whiteout, same reasoning as pb_trainer_battle"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="always"),
        else_outcome=ArmOutcome(kind="fork", detail="whiteout"),
    ),
    ConditionFamily(
        name="trainer_attr",
        # $Trainer.ablePokemonCount<=1 (13 corpus-wide), $Trainer.gender==0
        # (4, also spaced "$Trainer.gender == 0" -- both occur).
        pattern=_rx(r"\$Trainer\.\w+\s*" + _CMP + r"\s*-?\w+"),
        description=(
            "$Trainer.<attr> <cmp> literal -- player-character state gate; "
            "$Trainer's own attributes (party count, gender, ...) are not "
            "modelled Switch/Variable keys -- unmodelled both arms"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="$Trainer.<attr>"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="$Trainer.<attr>"),
    ),
    ConditionFamily(
        name="input_trigger",
        # 7 corpus-wide, e.g. "Input.trigger?(Input::C)".
        pattern=_rx(r"Input\.trigger\?\(Input::\w+\)"),
        description="Input.trigger?(Input::KEY) -- raw button-press poll, both arms player input",
        judgment_free=True,
        then_outcome=ArmOutcome(kind="input"),
        else_outcome=ArmOutcome(kind="input"),
    ),
    ConditionFamily(
        name="distance_checker",
        # 10 corpus-wide, e.g. "distanceChecker>=2".
        pattern=_rx(r"distanceChecker\s*" + _CMP + r"\s*\d+"),
        description=(
            "distanceChecker <cmp> N -- scripted proximity gate; "
            "distanceChecker (221_Extra_Scripts.rb:414-421) reads two "
            "characters' x/y (get_character) -- position, same category as "
            "game_player_axis/get_character_on_event -- both arms player input"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="input"),
        else_outcome=ArmOutcome(kind="input"),
    ),
    ConditionFamily(
        name="pb_get_pokemon_egg",
        # 8 corpus-wide, e.g. "pbGetPokemon(1).egg?".
        pattern=_rx(r"pbGetPokemon\(\d+\)\.egg\?"),
        description=(
            "pbGetPokemon(N).egg? -- party-slot egg-state guard; a party "
            "slot's egg flag is not a modelled key -- unmodelled both arms"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="party_slot_egg_state"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="party_slot_egg_state"),
    ),
    ConditionFamily(
        name="pb_get_pokemon_shadow_rescue",
        # 6 corpus-wide, e.g. "(pbGetPokemon(1).isShadow? rescue false)".
        pattern=_rx(r"\(pbGetPokemon\(\d+\)\.isShadow\?\s*rescue\s*false\)"),
        description=(
            "(pbGetPokemon(N).isShadow? rescue false) -- shadow-state guard, "
            "nil-safe; a party slot's shadow flag is not a modelled key -- "
            "unmodelled both arms"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="party_slot_shadow_state"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="party_slot_shadow_state"),
    ),
    ConditionFamily(
        name="is_temp_switch_off",
        # 5 corpus-wide, e.g. 'isTempSwitchOff?("A")'.
        pattern=_rx(r'isTempSwitchOff\?\("\w+"\)'),
        description=(
            'isTempSwitchOff?("X") -- ephemeral self-switch-style guard; '
            "isTempSwitchOff?/tsOff? (101__PField_Field.rb:2926-2927, "
            "022_Game_Event_v17.rb:75) resolve to get_character(0) -- THIS "
            "row's own running event -- so the TempSwitch key's (map_id, "
            "event_id) must be filled in from the row being extracted, not "
            "from the condition text; extract.py builds the concrete Test at "
            "extraction time. Both arms modelled state"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="state", detail="is_temp_switch_off"),
        else_outcome=ArmOutcome(kind="state", detail="is_temp_switch_off"),
    ),
    ConditionFamily(
        name="pb_day_care_deposited",
        # 3 corpus-wide, "Kernel.pbDayCareDeposited==1".
        pattern=_rx(r"Kernel\.pbDayCareDeposited\s*" + _CMP + r"\s*\d+"),
        description=(
            "Kernel.pbDayCareDeposited <cmp> N -- Day Care occupancy gate; "
            "pbDayCareDeposited (110_PField_DayCare.rb:6-12) counts "
            "$PokemonGlobal.daycare slots -- not a modelled key, unmodelled "
            "both arms"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="daycare_deposited_count"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="daycare_deposited_count"),
    ),
    ConditionFamily(
        name="pb_egg_generated",
        # 6 corpus-wide, "Kernel.pbEggGenerated?".
        pattern=_rx(r"Kernel\.pbEggGenerated\?"),
        description=(
            "Kernel.pbEggGenerated? -- Day Care egg-ready guard; "
            "pbEggGenerated? (110_PField_DayCare.rb:1-4) reads "
            "$PokemonGlobal.daycareEgg -- not a modelled key, unmodelled "
            "both arms"
        ),
        judgment_free=True,
        then_outcome=ArmOutcome(kind="unmodelled", detail="daycare_egg_ready"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="daycare_egg_ready"),
    ),
)

# --- Uranium-specific shapes -------------------------------------------
#
# Trivial to match, but the meaning is Uranium's own custom Ruby, not vanilla
# Essentials -- a human read Uranium's source once to confirm what each does
# (REDERIVATION_PLAN.md §14.6's "14.1's ten work items" list). Do not expect
# these to appear in the next fan game.
_URANIUM_FAMILIES: tuple[ConditionFamily, ...] = (
    # 2026-10-15 (CH08 §9 ruling: the ladder is converted natively; rung 0 is
    # walked, higher rungs wait on a dex-seeded harness start). Was one
    # `uranium_jv_reward` family, unmodelled both arms.
    ConditionFamily(
        name="uranium_jv_next_reward",
        # 1 staged instance, "jvNextReward".
        pattern=_rx(r"jvNextReward"),
        description=(
            "jvNextReward -- Uranium's dex-reward-ladder guard "
            "(213_Bambo_Reward.rb:16-23): true iff $Trainer.pokedexOwned >= "
            "PROFREWARDS[var22+1][0] (the next tier: 10 owned first). The "
            "natural walk owns far fewer, so else is the ordinary path "
            "(always); then needs a dex-seeded start, the harness primitive "
            "'dex_owned_tier'"
        ),
        judgment_free=False,
        then_outcome=ArmOutcome(kind="harness", detail="dex_owned_tier"),
        else_outcome=ArmOutcome(kind="always"),
    ),
    ConditionFamily(
        name="uranium_jv_give_reward",
        # 4 staged instances, "jvGiveReward".
        pattern=_rx(r"jvGiveReward"),
        description=(
            "jvGiveReward -- pays the current tier (213_Bambo_Reward.rb:33-50): "
            "an Egg on tiers 4/6/8 (false on a full party), else an item via "
            "pbReceiveItem (returns true only if nothing was stored). Reached "
            "only past jvNextReward's then-arm, so both arms are harness "
            "'dex_owned_tier' like that one"
        ),
        judgment_free=False,
        then_outcome=ArmOutcome(kind="harness", detail="dex_owned_tier"),
        else_outcome=ArmOutcome(kind="harness", detail="dex_owned_tier"),
    ),
    ConditionFamily(
        name="uranium_is_custom_game",
        # 3 staged instances, bare "isCustomGame?".
        pattern=_rx(r"isCustomGame\?"),
        description=(
            "isCustomGame? -- Uranium's Nuzlocke/randomizer custom-ruleset "
            "flag; isCustomGame? (220_Custom_Mode.rb:244-256) ORs a handful "
            "of $PokemonGlobal fields (nuzlocke, challengemode, ...) -- none "
            "are modelled keys -- unmodelled both arms"
        ),
        judgment_free=False,
        then_outcome=ArmOutcome(kind="unmodelled", detail="$PokemonGlobal custom-ruleset flags"),
        else_outcome=ArmOutcome(kind="unmodelled", detail="$PokemonGlobal custom-ruleset flags"),
    ),
    ConditionFamily(
        name="uranium_show_ruleset_settings",
        # 2 staged instances, "showRulesetSettings(1)".
        pattern=_rx(r"showRulesetSettings\(.*\)"),
        description=(
            "showRulesetSettings(N) -- Uranium's custom-ruleset menu guard; "
            "showRulesetSettings (220_Custom_Mode.rb:776-782) opens "
            "PokemonRulesetScene and returns pbOptions's exit value -- the "
            "player's own menu selection decides the branch, both arms "
            "player input"
        ),
        judgment_free=False,
        then_outcome=ArmOutcome(kind="input"),
        else_outcome=ArmOutcome(kind="input"),
    ),
    ConditionFamily(
        name="uranium_is_rock_smash_softlocked",
        # 3 staged instances, bare "isRockSmashSoftlocked?".
        pattern=_rx(r"isRockSmashSoftlocked\?"),
        description=(
            "isRockSmashSoftlocked? -- Uranium's Rock Smash softlock-"
            "prevention guard; isRockSmashSoftlocked? "
            "(221_Extra_Scripts.rb:796-806+) combines "
            "$PokemonGlobal.nuzlocke/randomizer, bag HM06 quantity, badge "
            "count, and party/box move knowledge -- none individually "
            "modelled and the combination isn't a single Test -- unmodelled "
            "both arms"
        ),
        judgment_free=False,
        then_outcome=ArmOutcome(
            kind="unmodelled",
            detail="nuzlocke/randomizer + bag HM06 + badge + party/box move-knowledge state",
        ),
        else_outcome=ArmOutcome(
            kind="unmodelled",
            detail="nuzlocke/randomizer + bag HM06 + badge + party/box move-knowledge state",
        ),
    ),
)

# --- the one compound-boolean exception (REDERIVATION_PLAN.md §16.3 C2
# ruling (e)) -------------------------------------------------------------

_TIME_OF_DAY_CLAUSE = r"Time\.now\.hour\s*" + _CMP + r"\s*\d+"
_TIME_OF_DAY_FAMILY = ConditionFamily(
    name="time_of_day",
    # e.g. "Time.now.hour<6||Time.now.hour>=20" (common event 51's night
    # guard) and its negation (the day guard); one or more
    # `Time.now.hour <cmp> N` clauses joined by `||`/`&&`. Anchored and
    # specific on purpose -- this is the single compound shape this table
    # is allowed to recognize.
    pattern=_rx(_TIME_OF_DAY_CLAUSE + r"(?:\s*(?:\|\||&&)\s*" + _TIME_OF_DAY_CLAUSE + r")*"),
    description=(
        "Time.now.hour <cmp> N[ (|||&&) Time.now.hour <cmp> N ...] -- "
        "real-time clock read; common event 51 (parallel, gated on switch "
        "51 GAME RUNNING, 022_Game_Event_v17.rb-era common-event trigger) "
        "polls Time.now.hour every 200 frames to set switch 105 DAY / 106 "
        "NIGHT (REDERIVATION_PLAN.md §16.3 C2 ruling (e)) -- ruled player "
        "input (the clock), both arms"
    ),
    judgment_free=True,
    then_outcome=ArmOutcome(kind="input", detail="clock"),
    else_outcome=ArmOutcome(kind="input", detail="clock"),
)

FAMILIES: tuple[ConditionFamily, ...] = _VANILLA_FAMILIES + _URANIUM_FAMILIES + (_TIME_OF_DAY_FAMILY,)

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

    A compound boolean never classifies, whatever its operands look like --
    with exactly one exception: `time_of_day` (REDERIVATION_PLAN.md §16.3 C2
    ruling (e)), a real-time-clock compound found live on CH01-CH03 real
    data by C2b's triggered-common-event guard. REDERIVATION_PLAN.md §14
    ruling 2 is explicit that the OTHER compound outliers "need judgment and
    get a fallback bucket, not a pattern", so this is the ruling stated in
    code rather than left to the patterns to imply. It also closes a real
    hole: every family's argument list is `.*`, and under `fullmatch` a
    greedy `.*` happily spans a `)` and an operator, so
    `pbTrainerBattle(A) || pbTrainerBattle(B)` matched `pb_trainer_battle`
    before this guard -- a two-branch condition silently inheriting a
    single-call family's "no citation owed". Latent, not live: all 7
    non-clock compound-boolean texts in the 199-map corpus already fell
    through to `None` on their operands, so the guard changes no current row
    besides the clock one. It is here so that the day one does not, the row
    owes a citation rather than quietly claiming it does not.
    """
    normalized = _normalize(text)
    if "||" in normalized or "&&" in normalized:
        if _TIME_OF_DAY_FAMILY.pattern.fullmatch(normalized):
            return _TIME_OF_DAY_FAMILY
        return None
    for family in FAMILIES:
        if family.pattern.fullmatch(normalized):
            return family
    return None
