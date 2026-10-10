"""Deterministic event→Poryscript transpiler (BUILD_PLAN §3, grill D5/D7).

The generalization of ``deterministic._dialogue_body`` from "bail on unknown"
to "emit for every command, queue only the uninterpretable". This module is
the conversion *spine*; the whole-event classifiers in ``deterministic.py``
run on top as an idiom-collapse layer (the driver tries them first), and the
LLM tail tool is for queue residue only — never a fallback path from here.

Contract:

* ``transpile_event(map_id, event, ctx)`` returns the event's script blocks
  plus a list of ``unhandled.jsonl``-shaped queue entries. It never returns
  ``None`` and never raises on corpus data — every command either emits
  Poryscript or queues, loudly, in place (an ``# UNHANDLED`` comment marks
  the spot in the emitted script).
* Emitted symbols must resolve against the fork index ∪ registries; the
  driver runs the conversion-time gate (grill D4) over every map's output.
* Flag/var names go through the ``FlagRegistry`` instance in the context —
  never hardcoded, never invented for unnamed ids (unnamed → queue).

Structure notes (verified against real Phase-3 JSON, not RMXP folklore):

* Nesting is carried by each command's ``indent`` field; 411/412 (else/branch
  end), 402/403/404 (choice arms/end) and 413 (repeat above) sit at the SAME
  indent as their opener, with children one deeper.
* A code-209 route is ``[target_id, {"list": [{code, parameters}, ...]}]``
  with a trailing code-0 terminator inside the route list; ``repeat`` /
  ``skippable`` flags ride on the route object.
* Code-123 self-switch: value 0 means ON → ``setflag`` (yes, inverted).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from rpg2gba.conversion_agent.deterministic import (
    RMXP_DIRECTION_TO_DIR_CONST as _RMXP_DIRECTION_TO_DIR_CONST,
)
from rpg2gba.conversion_agent.deterministic import (
    _label_name,
    format_pory_dialogue,
    join_text_lines,
    translate_text_codes,
    warp_lines,
)
from rpg2gba.conversion_agent.flag_registry import (
    TERMINAL_HIDE_FLAG_PLACEHOLDER,
    FlagRegistry,
    resolve_switch_flag,
    resolve_variable_var,
)
from rpg2gba.conversion_agent import ruby_idioms
from rpg2gba.conversion_agent.inline_choice import (
    CANCEL_SENTINEL,
    InlineChoiceError,
    cancel_sentinel_read_problem,
    has_inline_choice,
    parse_inline_choice,
)
from rpg2gba import ingame_trades as _trades
from rpg2gba.pbs_converter._naming import to_constant
from rpg2gba.ruby_subset.builtins import NUM_BADGES, badge_flag
from rpg2gba.pbs_converter.heal_locations import _CALL_RE as _SET_POKEMON_CENTER_RE
from rpg2gba.tileset_converter.npc_gfx import is_door_sheet

logger = logging.getLogger(__name__)

# -- RMXP command codes -------------------------------------------------------

SHOW_TEXT = 101
SHOW_CHOICES = 102
INPUT_NUMBER = 103
CHANGE_TEXT_OPTIONS = 104
WAIT = 106
COMMENT = 108
CONDITIONAL_BRANCH = 111
LOOP = 112
BREAK_LOOP = 113
EXIT_EVENT = 115
ERASE_EVENT = 116
CALL_COMMON_EVENT = 117
LABEL = 118
JUMP_TO_LABEL = 119
CONTROL_SWITCHES = 121
CONTROL_VARIABLES = 122
CONTROL_SELF_SWITCH = 123
TRANSFER_PLAYER = 201
SET_EVENT_LOCATION = 202
CHANGE_MAP_SETTINGS = 204
SHOW_ANIMATION = 207
CHANGE_PLAYER_TRANSPARENCY = 208
SET_MOVE_ROUTE = 209
WAIT_MOVE_COMPLETION = 210
PREPARE_TRANSITION = 221
EXECUTE_TRANSITION = 222
CHANGE_TONE = 223
PLAY_BGM = 241
FADEOUT_BGM = 242
PLAY_ME = 249
PLAY_SE = 250
RECOVER_ALL = 314
SCRIPT = 355
SHOW_TEXT_CONT = 401
CHOICE_WHEN = 402
CHOICE_CANCEL = 403
CHOICES_END = 404
COMMENT_CONT = 408
ELSE_BRANCH = 411
MOVE_COMMAND_ROW = 509  # editor-display duplicate of a 209 route step
SCRIPT_CONT = 655
BRANCH_END = 412
REPEAT_ABOVE = 413

# Codes that carry no game state on the GBA and are dropped without a queue
# entry (dispositions validated in the FABLES G2 gate / command-reference
# ledger). Dropping is visible in the diff vs the source page, not silent-
# wrong: nothing conditions on them. 509 rows are the editor's per-step
# display duplicates of the 209 route object already transpiled — content-
# free by construction.
_STRIP_CODES = frozenset({CHANGE_TEXT_OPTIONS, COMMENT, COMMENT_CONT, MOVE_COMMAND_ROW})

ACTION_BUTTON_TRIGGER = 0

# 355 idioms proven on the slice (grill D8: ≥2 occurrences + native analog).
# Whole-string matches — a longer expression around the call falls to queue.
_SET_TEMP_SWITCH_RE = re.compile(r'^\s*setTempSwitchOn\(\s*"([A-Za-z0-9]+)"\s*\)\s*$')
_SET_SELF_SWITCH_RE = re.compile(
    r'^\s*pbSetSelfSwitch\(\s*(\d+)\s*,\s*"([A-Z])"\s*,\s*(true|false)\s*\)\s*$'
)

# pbPhoneRegisterNPC(...) — Essentials phone-directory registration; the
# system has no slice-relevant analog on the GBA. User-approved strip
# (2026-07-05, slice1 hand-bucket review), Map032 EV9 page 3. Transpiler-local
# addition to the 355 STRIP tier (not routed through deterministic.py's
# _DIALOGUE_STRIP_RE — that module is out of scope for this change). Any
# argument list is fine — the whole call is cosmetic for our purposes. Anchored
# on the literal call-open ``(`` so a longer identifier
# (``pbPhoneRegisterNPCFoo(...)``) does not match — "NPC(" never appears
# inside "NPCFoo(".
_PHONE_REGISTER_NPC_STRIP_RE = re.compile(r"^\s*(?:Kernel\.)?pbPhoneRegisterNPC\(")

# Type-12 (script) condition idioms proven on the slice (grill D8/D10 read-
# through, reference/findings/slice1_queue_readthrough.md) — whole-string matches, same
# discipline as the 355 idioms above: a longer expression around the call
# falls to queue.

# "Player is standing on this event's tile" — fires on reverse-warp arrival
# (door idiom, Map032 EV3/5/6/7/17/23/36/37 page 2). Any other get_character(...)
# form (a different index, a different predicate) still queues.
_DOOR_ONEVENT_RE = re.compile(r"^\s*get_character\(0\)\.onEvent\?\s*$")

# Kernel.pbReceiveItem(::PBItems::SYMBOL[, qty[, _I("Display Name")]]) —
# give-item-with-fanfare call (Map032 EV27/EV9, Map049 EV18, Map068 EV15,
# Map073 EV6). Same family as deterministic.classify_ground_item's pbItemBall
# idiom; qty is optional (bare RARECANDY/LAVACOOKIE vs. POKeBALL,5), and so is
# a trailing ``_I("...")`` display-name argument used only for Essentials'
# own on-screen message (Map068 EV15 cmd 83:
# ``pbReceiveItem(::PBItems::ORANBERRY,5,_I("Oran Berries"))``) — dropped,
# since giveitem's own STD_OBTAIN_ITEM message already names the item
# (engine/asm/macros/event.inc:2118-2126). The ``::`` module-scope prefix is
# corpus-inconsistent (Map073 EV6 cmds 5-7 write bare ``PBItems::X``, cmd 8
# and Map073's second event write ``::PBItems::X``) so it's optional here,
# matching ``_ITEMBALL_RE``'s ``(?:::)?`` in deterministic.py. Whole-string
# match only (mirrors every other 355/111 idiom in this module): a guard
# modifier (``... if pbGetPokemon(1).species == N``, the mega-stone grants),
# a bare ``:SYMBOL`` literal, or a dynamic argument (``pbGet(1)``,
# ``getVariable()``) all still fall through to the queue rather than being
# guessed at.
_RECEIVE_ITEM_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbReceiveItem\(\s*(?:::)?PBItems::(\w+)\s*"
    r"(?:,\s*(\d+)\s*(?:,\s*_I\(\s*\"[^\"]*\"\s*\)\s*)?)?\)\s*$"
)

# The consuming counterpart: `$PokemonBag.pbDeleteItem(PBItems::SYMBOL)`.
# Surfaced 2026-08-19 once the BIKEWHEEL bag-quantity branch started emitting —
# it sits inside that branch's then-arm (Map073 EV001 cmd 9), so it was hidden
# behind the dropped conditional until then. Without it the player is handed the
# Bicycle but keeps the spent wheel as a dead Key Item. Same narrow discipline as
# _RECEIVE_ITEM_RE: a bare complete call with a literal symbol only — a dynamic
# argument or a guard modifier still falls through to the queue.
_DELETE_ITEM_RE = re.compile(
    r"^\s*\$PokemonBag\.pbDeleteItem\(\s*(?::|(?:::)?PBItems::)(\w+)\s*"
    r"(?:,\s*(\d+)\s*)?\)\s*$"
)

# `pbPlayCry(PBSpecies::X)` / `pbPlayCry(:X)` — play the species cry. Fork:
# `playmoncry species, mode` (engine/asm/macros/event.inc:1468) + `waitmoncry`
# (:1723); CRY_MODE_NORMAL = 0 (engine/include/constants/sound.h). Previously
# swallowed by deterministic._DIALOGUE_STRIP_RE (silent drop, no queue row).
_PLAY_CRY_RE = re.compile(
    r"^\s*pbPlayCry\(\s*(?::|(?:::)?PBSpecies::)([A-Za-z0-9_]+)\s*\)\s*$"
)

# `$Trainer.party.length <op> N` as a code-111 script condition. The party
# count is an unsigned count, so only the zero / non-zero tests are mapped.
_PARTY_LENGTH_CMP_RE = re.compile(
    r"^\s*\$Trainer\.party\.length\s*(<=|==|<|>=|>|!=)\s*(\d+)\s*$"
)

# "$game_player.AXIS OP LITERAL" — a one-shot position guard/boundary check
# outside a code-112 wait loop (Map032 EV9 pages 1-3: `x==17` is a map-edge
# sign guard that early-exits before the scene proper; EV9 page 3's
# `y<=43` is a "walk the player into place before continuing" reposition).
# Corpus census 2026-08-02: 24 sites across 8 maps (5 `x==`, 19 `y<=`/`y>=`),
# so this is the same idiom wherever it appears, not an EV9-specific shape.
# Distinct from `_ALIGN_BREAK_RE` above, which is this same comparison
# *inside* a code-112 loop body (a step-until-aligned wait, not a guard) —
# the two never collide because one only fires with an enclosing loop and
# this one only fires without ``node.otherwise`` context restrictions beyond
# the comparison itself. VAR_TEMP_0/VAR_TEMP_1 are the transpiler's own
# generic scratch vars (`_ALIGN_AXIS_VAR`), reused rather than re-minted.
_PLAYER_POSITION_CMP_RE = re.compile(
    r"^\s*\$game_player\.(x|y)\s*(==|<=|>=)\s*(-?\d+)\s*$"
)

# Essentials defensive numeric guard: "variable is not numeric or negative"
# (Map049 EV20 page 1, output/uranium-build/maps/Map049.json — 4 then-nodes, 0
# else-nodes: comment lines explaining the guard, plus a 122 re-set of the
# variable to 0). Statically FALSE on the GBA: game variables are always
# unsigned integers, so ``pbGet(N).is_a?(Numeric)`` is always true (the first
# disjunct, negated, is always false) and ``$game_variables[M] < 0`` is never
# true (the second disjunct is always false) — the whole OR can never be true.
# User-approved strip (2026-07-05, slice1 hand-bucket review): drop the
# then-arm entirely, splice the else-arm's children in place of the branch
# (see _emit_unsatisfiable_numeric_guard). Whole-string match — a different
# combinator (&&), an un-negated is_a?, a different comparison (>), or any
# extra clause all fall through to queue.
_UNSATISFIABLE_NUMERIC_GUARD_RE = re.compile(
    r"^\s*!\s*pbGet\(\s*\d+\s*\)\.is_a\?\(\s*Numeric\s*\)\s*"
    r"(?:\|\|\s*\$game_variables\[\s*\d+\s*\]\s*<\s*0\s*)?$"
)

# Essentials wait-until-aligned break condition inside a code-112 loop (Map032
# EV74/78/80): "loop { if $game_player.AXIS CMP N; break; else move-one-step;
# wait }". Only >= / <= are the proven shape — anything else (>, <, ==, a
# different receiver) stays outside the tier.
_ALIGN_BREAK_RE = re.compile(r"^\s*\$game_player\.(x|y)\s*(>=|<=)\s*(-?\d+)\s*$")
_ALIGN_NEGATED_CMP = {">=": "<", "<=": ">"}
_ALIGN_AXIS_VAR = {"x": "VAR_TEMP_0", "y": "VAR_TEMP_1"}

# Code-207 (Show Animation) emote tier: pokeemerald ships these as movement
# tokens, not a runtime animation call (movement.inc, verified against pristine
# HEAD — see _emit_show_animation). Ids resolved against
# reference/animation_names.json (dumped from Uranium's own Animations.rxdata
# — the source of truth for what a numeric id *is*).
_EMOTE_MOVEMENT_LABELS = {
    17: "Common_Movement_ExclamationMark",  # movement.inc:8 (EM Exclamation)
    19: "Common_Movement_QuestionMark",  # movement.inc:4 (EM Interrogation)
    # 104 "Rustle" — the wild-encounter grass-rustle cue (Map032 EV9's Chyinmunk
    # reveal). No native rustle effect, but "something in the grass" reads the
    # same as "!" over the target's head, the same substitution FRLG's own
    # encounter tutorials use; corpus census 2026-08-02: 1 occurrence.
    104: "Common_Movement_ExclamationMark",
}

# 207 animation ids with a *decided* drop — not a capability gap, an approved
# fidelity call (id 18 "EM scratch", an attack-hit flourish with no overworld
# analog in the fork; the hit itself is conveyed by the freeze-pose movement
# route immediately after it in every corpus occurrence). Distinct from
# _EMOTE_MOVEMENT_LABELS misses, which still queue — this id has been looked
# at and dropped on purpose, so it gets a breadcrumb instead of a queue entry.
_EMOTE_DROP_IDS = frozenset({18})

# -- native bucket idioms (queue-clearing pass, 2026-07-05 slice review) ------
# Whole-shape matches proven against the real slice corpus (Map032/048/049) —
# same discipline as the 355/111 idioms above: a longer/different string or
# route falls through to queue, never guessed.

# Kernel.pbRockSmash — Essentials' RMXP-side rock-smash choreography (break
# animation + erase self + Kernel.pbRockSmashRandomEncounter + self-switch A
# on), replaced wholesale by the fork's own field-move script
# (engine/data/scripts/field_move_scripts.inc:64 EventScript_RockSmash —
# lockall, checkfieldmove FIELD_MOVE_ROCK_SMASH, yes/no prompt,
# dofieldeffect FLDEFF_USE_ROCK_SMASH, removeobject VAR_LAST_TALKED, then
# `special RockSmashWildEncounter`; every path ends in `end`/`releaseall`,
# never returns to the caller). Proven on Map032 EV14/15/33: the conditional
# IS the page's substantive body (nothing precedes/follows it), then-arm 14
# nodes / else-arm 1 node (a nested isRockSmashSoftlocked? check) — both
# dropped without being walked, so nothing inside them can leak a queue
# entry. Corpus grep (Map033/035/066/107/118) shows this condition string
# always pairs with the same Kernel.pbRockSmashRandomEncounter choreography,
# so the match is shape-only, not map/event-scoped — Kernel.pbRockSmash's
# real Ruby-side gate logic is what matters; the RMXP arms are visual
# choreography for the same interaction regardless of map.
_ROCK_SMASH_RE = re.compile(r"^\s*(?:Kernel\.)?pbRockSmash\s*$")

# pbHasSpecies?(::PBSpecies::NAME) — "does the party have this species"
# (Auntie's farewell dialogue, Map049 EV001 page 3 — SLICE1_TODO #2, the last
# live queue entry; STARTER_SPECIES_PLAN.md §W5). Corpus-verified against the
# only 3 occurrences (Map049.json EV001 page 3, RAPTORCH/ELETUX/ORCHYNX): the
# call is always this exact bare shape, never negated (no `!`/`unless`
# wrapper observed anywhere in the corpus) — a negated form is not handled
# here and falls through to the generic script-condition queue like any
# other non-matching type-12 shape.
# pbMoveTutorChoose(PBMoves::NAME) as a code-111 script condition (Map046 EV003
# page 1, Nowtoch City's tutor: eleven near-identical blocks). Essentials opens
# the party screen, the player picks a compatible mon, the move is taught; the
# call is true iff a move was taught. Exactly one move argument -- the optional
# movelist / bymachine arguments are a different shape and fall through to the
# generic script-condition queue.
_MOVE_TUTOR_CHOOSE_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbMoveTutorChoose\(\s*(?:::)?PBMoves::([A-Za-z0-9_]+)\s*\)\s*$"
)

# -- party-pick family (Map046 EV014 NPC trade, EV002 Name Rater) -------------
# Essentials' `pbChoosePokemon(v, n[, proc])` stores the chosen party index in
# RMXP variable v (-1 on cancel) and the mon's name in variable n.
#
# Plain form -> the fork's party-only picker. `special(ChoosePartyMon)` (not
# `chooseboxmon`) is deliberate: the Name Rater's readers are mixed --
# `ScriptGetPartyMonSpecies` indexes `gPlayerParty[gSpecialVar_0x8004]` directly
# (engine/src/field_specials.c:1641) and would read out of bounds on a PC-box
# pick (PC_MON_CHOSEN), while BufferMonNickname / IsMonOTIDNotPlayers /
# MonOTNameNotPlayer / TryPutNameRaterShowOnTheAir / ChangePokemonNickname all
# go through GetSelectedBoxMonFromPcOrParty (engine/src/pokemon.c:7384,
# tv.c:3267-3302, field_specials.c:1677), which is correct for a party index.
# Party-only is also exactly what Essentials' screen offers.
_PICK_PLAIN_RE = re.compile(r"^\s*pbChoosePokemon\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*$")
_PICK_EGG_COND_RE = re.compile(r"^\s*pbGetPokemon\(\s*(\d+)\s*\)\.egg\?\s*$")
_PICK_FOREIGN_COND_RE = re.compile(
    r"^\s*pbGetPokemon\(\s*(\d+)\s*\)\.isForeign\?\(\s*\$Trainer\s*\)\s*$"
)
_PICK_PARTY_ROW_RE = re.compile(r"^\s*pkmn=\$Trainer\.party\[\s*pbGet\(\s*(\d+)\s*\)\s*\]\s*$")
_PICK_SPECIES_ROW_RE = re.compile(r"^\s*species=PBSpecies\.getName\(\s*pkmn\.species\s*\)\s*$")
_PICK_TEXTENTRY_ROW_RE = re.compile(
    r'^\s*pbTextEntry\(\s*_I\(\s*"[^"]*"\s*,\s*species\s*\)\s*,\s*0\s*,\s*'
    r"MAXPOKENAMELENGTH\s*,\s*(\d+)\s*,\s*pkmn\s*\)\s*$"
)
_PICK_RENAME_ROW_RE = re.compile(r"^\s*pkmn\.name=pbGet\(\s*(\d+)\s*\)\s*$")
_PICK_NAME_CHANGED_COND_RE = re.compile(
    r'^\s*\$game_variables\[\s*(\d+)\s*\]\s*==\s*""\s*\|\|\s*'
    r"\$game_variables\[\s*\1\s*\]\s*==\s*pbGet\(\s*(\d+)\s*\)\s*$"
)
# Proc-filtered form (NPC trade): the filter is exactly "not an egg and species
# == X" -- the one shape ingame_trades._CHOOSE_RE also accepts.
_PICK_PROC_RE = re.compile(
    r"^\s*pbChoosePokemon\(\s*(\d+)\s*,\s*(\d+)\s*,\s*proc\s*\{\s*\|(\w+)\|\s*"
    r"!\s*\3\.egg\?\s*(?:and|&&)\s*\3\.species\s*==\s*(?:::)?PBSpecies::(\w+)\s*\}\s*\)\s*$"
)
# RMXP Control Variables comparison op codes (code 111, type 1) that mean
# "a mon was chosen" (var != -1, >= 0, > -1) / "cancelled" (< 0, == -1, <= -1).
_PICK_CHOSEN_CMPS = frozenset({(5, -1), (1, 0), (3, -1)})
_PICK_CANCEL_CMPS = frozenset({(4, 0), (0, -1), (2, -1)})
# Placeholder standing in for a recorded name variable while a text row goes
# through translate_text_codes (which rejects `\v[n]` and any brace).
_STRVAR_PLACEHOLDER = "§STRVAR1§"

# Poryscript has no bare infinite loop (`while (true)` does not parse: the
# condition must be var()/flag()/...; verified against the real compiler
# 2026-10-09). A u16 var is always >= 0, so this is the always-true condition.
_LOOP_ALWAYS_TRUE = "var(VAR_RESULT) >= 0"

_HAS_SPECIES_RE = re.compile(r"^\s*pbHasSpecies\?\(\s*::PBSpecies::([A-Za-z0-9_]+)\s*\)\s*$")

# Character-facing conditional (RMXP condition kind 6: `[6, character_id,
# direction]`), player-only. Real occurrence: Map031 EV049 "NurseTut" page 1,
# commands 5 and 42 (output/uranium-build/maps/Map031.json), both
# `[6, -1, 8]` — "is the player facing up?" gates a re-ask of the same
# question. Character id -1 is always the player in RMXP; any other id is an
# NPC local-id lookup that is deliberately out of scope (no established
# RMXP-local-id -> fork-local-id mapping exists yet) and must keep queueing,
# not be guessed at. RMXP direction constants 2/4/6/8 (down/left/right/up)
# map onto the fork's DIR_SOUTH/DIR_WEST/DIR_EAST/DIR_NORTH through
# `_RMXP_DIRECTION_TO_DIR_CONST` (imported above; owned by deterministic.py);
# any other direction value falls through to the queue.

# $PokemonBag.pbQuantity(PBItems::SYMBOL) <op> 0 — a bag has-item/lacks-item
# guard (Map073 EV1 page 1 cmd 4 `...BIKEWHEEL)>0`; EV3 page 1 cmd 0 and EV6
# page 2 cmd 2, both `...SPRINKLOTAD)==0`, output/uranium-build/maps/
# Map073.json). Only the two comparison shapes actually observed in the
# corpus are handled: `>0` (player HAS at least one) and `==0` (player LACKS
# it entirely) — any other operator or non-zero RHS falls through to the
# generic script-condition queue rather than being guessed at. The item may be
# spelled as a `PBItems::` constant or as a bare Ruby symbol (`:MARIAKEY` —
# Map040 EV017 page 0 cmd 0, the Nowtoch key door); both name the same
# Essentials internal item symbol.
_BAG_QUANTITY_CMP_RE = re.compile(
    r"^\s*\$PokemonBag\.pbQuantity\(\s*(?:(?:::)?PBItems::|:)([A-Za-z0-9_]+)\s*\)"
    r"\s*(>|==)\s*0\s*$"
)

# $PokemonGlobal.nuzlocke==true — Nuzlocke mode is not ported (user-approved
# strip, 2026-08-19), so the guard is statically false: Map068 EV015 page 1
# cmd 16 (output/uranium-build/maps/Map068.json), 2 then-nodes / 0 else-nodes.
_NUZLOCKE_MODE_GUARD_RE = re.compile(r"^\s*\$PokemonGlobal\.nuzlocke\s*==\s*true\s*$")

# pbNextMysteryGiftID>0 — the Mystery Gift subsystem is not ported (user-
# approved strip, 2026-08-19), so the guard is statically false: Map067 EV009
# "Deliveryman" page 2 cmd 0 (output/uranium-build/maps/Map067.json), 4
# then-nodes / 1 else-node.
_MYSTERY_GIFT_ID_GUARD_RE = re.compile(r"^\s*pbNextMysteryGiftID\s*>\s*0\s*$")

# isRockSmashSoftlocked? — Uranium's anti-softlock helper (see
# reference/scripts_dump/221_Extra_Scripts.rb:796-812). Its very first line
# is ``return false if !$PokemonGlobal.nuzlocke || !$PokemonGlobal.randomizer``
# and Nuzlocke mode is already an established, user-approved not-ported strip
# on this port (``_NUZLOCKE_MODE_GUARD_RE`` above — ``$PokemonGlobal.nuzlocke``
# is never set true by any runtime path we ship), so ``!$PokemonGlobal.nuzlocke``
# is always true and the function returns ``false`` before evaluating any of
# its later randomizer/badge/party-composition checks. Statically FALSE on the
# GBA, exactly like the Nuzlocke-mode guard it's gated behind. Real corpus
# occurrences: Map032 (Rock Smash event, all 3 pages of the Rock Smash
# choreography — output/uranium-build/maps/Map032.json lines 22518, 23139,
# 26280), each a bare ``if isRockSmashSoftlocked?`` with a then-arm (softlock
# rescue dialogue/heal) and no else-arm.
_ROCK_SMASH_SOFTLOCKED_GUARD_RE = re.compile(r"^\s*isRockSmashSoftlocked\?\s*$")

# isCustomGame?(any=false) — Uranium's "any custom-mode option enabled" check
# (reference/scripts_dump/220_Custom_Mode.rb:244-262). It ORs together
# $PokemonGlobal.nuzlocke, .nuzlockehealbattle, .nuzlockenomart,
# .nuzlockepoisonfield, .challengemode (+ .nuzlockedupesclause,
# .nuzlockeshinyclause, .randomizer when any=true) — every one of those flags
# belongs to Custom Mode / Nuzlocke, neither of which is ported (Nuzlocke
# already established not-ported above; Custom Mode is the same "not
# portable to GBA" subsystem per REDERIVATION_PLAN.md item 6). No runtime
# path on this port ever sets any of them true, so every disjunct is always
# false and isCustomGame? always returns false. Statically FALSE, same
# collapse as _emit_nuzlocke_mode_strip. Real corpus occurrences: Map050
# EV005/EV027 (output/uranium-build/maps/Map050.json), always the bare
# no-arg call ``isCustomGame?`` (the ``any=false`` default — no corpus call
# ever passes ``true``).
_CUSTOM_GAME_GUARD_RE = re.compile(r"^\s*isCustomGame\?\s*$")

# showRulesetSettings(mode) — opens Uranium's PokemonRulesetScene, the Custom
# Mode options UI (reference/scripts_dump/220_Custom_Mode.rb:776-781). Not
# portable to GBA (no equivalent scene), and — because it's only ever reached
# from behind an isCustomGame? guard that itself statically collapses to
# false (see _CUSTOM_GAME_GUARD_RE above) — already dead code in every corpus
# occurrence. Handled as a bare script-call strip (breadcrumb, no queue) for
# the one occurrence NOT behind such a guard: Map039 EV015 (berry tree),
# output/uranium-build/maps/Map039.json line ~1473, a standalone
# ``showRulesetSettings(1)`` call with no enclosing isCustomGame? check.
_SHOW_RULESET_SETTINGS_STRIP_RE = re.compile(r"^\s*showRulesetSettings\(\s*\d*\s*\)\s*$")

# pbCaveEntrance — Essentials' cave-entry fade/step-in call (Map032 EV23/36/
# 37 page 1; 48 corpus occurrences total, always bare — no argument list ever
# observed, confirmed by corpus grep). Sits between a 223/106 fade-to-black
# and the page's own 201 transfer (which already emits a native
# `warp(...)` + `waitstate` — the GBA warp performs its own map-transition
# fade), so this call is pre-warp RMXP choreography the native warp subsumes.
# Breadcrumb strip, no queue.
_CAVE_ENTRANCE_STRIP_RE = re.compile(r"^\s*(?:Kernel\.)?pbCaveEntrance\s*$")

# Code-204 (Change Map Settings) subtype 1 = fog (command_204 in
# reference/scripts_dump/041_Interpreter.rb:1257 — the params[0]==1 branch
# sets fog_name/hue/opacity/blend_type/zoom/sx/sy). Exact params observed on
# Map032 EV23/36/37 page 1, immediately after the native warp: a dim fog
# overlay for the cave interior. The fork has no fog layer tied to a map
# transition (no fog opcode in asm/macros/event.inc) and this fog belongs to
# the same pre/post-warp RMXP choreography the native warp already subsumes.
# Exact tuple match only — any other subtype/name/value still queues.
_CAVE_FOG_204_PARAMS = (1, "004-Shade02", 0, 60, 0, 250, 0, 0)

# pbTrainerPC — Map048 EV4, bare call (1 corpus occurrence). Fork native:
# EventScript_PC (engine/data/scripts/pc.inc:1) — the generic non-bedroom PC
# every other building's PC metatile resolves to
# (engine/src/field_control_avatar.c:496 `return EventScript_PC;`). Ends the
# script itself (goto-chains through EventScript_PCMainMenu/
# EventScript_AccessPC to a releaseall/end or plain end — verified, never
# returns to the caller), so `goto` is correct here, not `call`.
#
# pbPokeCenterPC — Map068 EV7, same bare-call shape (Kevlar Town Center PC).
# Uranium gives the Center's PC a distinct Essentials method name, but
# pokeemerald has no separate "Center PC" script: vanilla PCs everywhere
# (bedroom, mart, Center) resolve to this same EventScript_PC
# (field_control_avatar.c:496 dispatches on metatile behavior alone, not
# location) — same idiom, same native target. 2026-08-14: this was previously
# a raw UNHANDLED-code-355 queue entry despite CH03_TODO.md's own recon
# already flagging the pbTrainerPC/pbPokeCenterPC pair as a "classifier
# near-miss."
_TRAINER_PC_RE = re.compile(r"^\s*(?:Kernel\.)?(?:pbTrainerPC|pbPokeCenterPC)\s*$")

# pbShowMap — Map048 EV7/8, bare call (18 corpus occurrences, all bare — no
# argument ever observed). Fork native: `special FieldShowRegionMap`
# (engine/data/specials.inc:274 `def_special FieldShowRegionMap,
# waitstate=1` — the vanilla usage at engine/data/event_scripts.s:1250
# EventScript_RegionMap confirms no explicit poryscript-level `waitstate`
# follows the special call: `waitstate=1` makes the ASSEMBLER'S `special`
# macro (engine/asm/macros/event.inc:293-298) auto-emit an implicit
# waitstate; an explicit one here would double up and trip the "implicit
# waitstate followed by waitstate" assembler warning). The page's own
# preceding dialogue ("It's a map of West Tandor.") is left in place — only
# the call itself is replaced, not the whole page.
_SHOW_MAP_RE = re.compile(r"^\s*(?:Kernel\.)?pbShowMap\s*$")

# $PokemonGlobal.runningShoes=true — Map049 EV1, exact literal (the `=false`
# variant seen elsewhere in the corpus, e.g. Map137/188/195, is out of scope
# here — still queues). Native: FLAG_SYS_B_DASH
# (engine/include/constants/flags.h:1463, "RECEIVED Running Shoes") — the
# vanilla b-dash unlock flag.
_RUNNING_SHOES_ON_RE = re.compile(r"^\s*\$PokemonGlobal\.runningShoes\s*=\s*true\s*$")

# Kernel.pbSetPokemonCenter — the white-out respawn anchor
# (reference/scripts_dump/101__PField_Field.rb:1666-1676:
#   def pbSetPokemonCenter(map=$game_map.map_id, x=$game_player.x,
#                           y=$game_player.y, direction=$game_player.direction)
#     ...
#   end
# ). Previously ruled STRIP (still in `deterministic._DIALOGUE_STRIP_RE` until
# this change); the recon ledger corrected that TWICE
# (reference/recon/uranium_script_calls.md:71) — this call is the *only*
# source of a white-out respawn point, and dropping it silently sends every
# white-out to the global spawn (`MetadataHome`) instead of the local Center.
# 64 call sites across 42 maps in the corpus; as of this change exactly one
# (Map068 EV001 page0, the Kevlar Town Center) is staged and resolvable via
# ``rpg2gba.pbs_converter.heal_locations.call_site_heal_locations()`` — every
# other site queues (see ``_emit_script_call``) rather than guessing. Fork
# native: `setrespawn HEAL_LOCATION_*` (engine/asm/macros/event.inc:1456-1459,
# `SetLastHealLocationWarp`). Regex imported from ``heal_locations._CALL_RE``
# rather than duplicated (CLAUDE.md §4.3 single source of truth) — it accepts
# the bare call and the `Kernel.`-prefixed / up-to-4-literal-arg forms; see
# that module for the exact accepted shapes.

# $PokemonGlobal.seenStorageCreator=true — Essentials' "have you met Bill/the
# PC's creator yet" flag; until set, script_menu.c prints the anonymous "SOMEONE'S
# PC" label instead of "LANETTE'S PC" for every PC interaction (see
# engine/src/script_menu.c:751, gated on FLAG_SYS_PC_LANETTE,
# engine/include/constants/flags.h:1438) — the exact mechanic Essentials models.
# Corpus census 2026-08-12 (output/uranium-build/maps/*.json): 3 occurrences,
# all `=true`, no `=false` anywhere — Map031 EV49 page0 (single-row
# "...seenStorageCreator=true"), Map031 EV49 page2 and Map042 EV3 page0 (both
# split across a 355 "...seenStorageCreator=" row and a same-indent 655 "true"
# continuation — RGSS wraps the assignment at the script-editor's line width,
# not a multi-statement blob; see _SEEN_STORAGE_CREATOR_OPEN_RE below for the
# split half). `=false` is not in the corpus, so no clearflag arm exists yet —
# a hypothetical `=false` still falls through to queue rather than guessing.
_SEEN_STORAGE_CREATOR_RE = re.compile(
    r"^\s*\$PokemonGlobal\.seenStorageCreator\s*=\s*true\s*$"
)

# The split-assignment opener half of the idiom above — a bare trailing `=`
# with the value (`true`/`false`) on the next physical 655 row. Handled
# statefully in ``_emit_script_call`` (mirrors the ``_ruby_locals``
# build-across-rows pattern already used for the starter-selector idiom):
# this row emits nothing and remembers it saw the opener; the immediately
# following script-call row (skipping only stripped comment rows, which
# never reach ``_emit_script_call``) completes it. Only ``true`` completes to
# ``setflag``; anything else (including ``false``) queues both rows rather
# than guessing.
_SEEN_STORAGE_CREATOR_OPEN_RE = re.compile(
    r"^\s*\$PokemonGlobal\.seenStorageCreator\s*=\s*$"
)

# $Trainer.pokedex=true — the canonical Pokédex grant, native-analog table
# entry (CLAUDE.md §4.7): FLAG_SYS_POKEDEX_GET is vanilla's own dex-received
# flag (engine/include/constants/flags.h:1351) and SetUnlockedPokedexFlags is
# a real special (engine/data/specials.inc:515) — the same pair vanilla's own
# Birch/Oak-lab script uses. Exact literal only (the corpus has no `=false`
# variant); anything else still queues.
#
# `EnableNationalPokedex` (specials.inc:518) is ours to add on top, and is not
# optional for this corpus: Uranium species are chained past
# NATIONAL_DEX_PECHARUNT and have no regional dex number, but a dex without
# national mode is pinned to DEX_MODE_HOENN (pokedex.c:2031) and
# CreatePokedexList then enumerates only `i < REGIONAL_DEX_COUNT`, mapping
# outward via RegionalToNationalOrder (pokedex.c:2194-2218). Every Uranium
# species would be caught-but-invisible. Setting FLAG_SYS_NATIONAL_DEX alone
# is NOT sufficient — IsNationalPokedexEnabled also requires
# pokedex.nationalMagic == 0xDA and VAR_NATIONAL_DEX == 0x302
# (event_data.c:101), which only the special sets.
_POKEDEX_GRANT_RE = re.compile(r"^\s*\$Trainer\.pokedex\s*=\s*true\s*$")

# $Trainer.pokegear=true — Theo's father hands over the PokéPod (Map172 EV4
# page0; the only corpus occurrence in the built chapters). Native:
# FLAG_SYS_POKENAV_GET (engine/include/constants/flags.h:1371), vanilla's own
# "received the PokéNav" flag, which adds the POKéNAV start-menu entry
# (engine/src/start_menu.c:345). Same mapping as story_state's
# `ruby_subset.builtins.ENGINE_ATTRIBUTES` (C8 ruling (b)), which the floor
# asserts; before this the row queued as UNHANDLED and the flag never set
# (ROM run 47). Exact literal only; `=false` still queues.
_POKEGEAR_ON_RE = re.compile(r"^\s*\$Trainer\.pokegear\s*=\s*true\s*$")

# $Trainer.badges[N]=true — gym badge grant. Fork-native: vanilla's own
# FLAG_BADGE01_GET..FLAG_BADGE08_GET; the index -> flag mapping is
# `ruby_subset.builtins.badge_flag` (one definition, shared with story state
# and the floor). Emitted as fork constants (like FLAG_SYS_*), not
# registry-minted. Only the exact literal `=true` form with an in-range
# literal index resolves; `=false`, a variable index, or N outside 0..7
# fall through to the generic queue (CLAUDE.md §4.5).
_BADGE_TRUE_RE = re.compile(
    r"^\s*\$Trainer\.badges\[\s*(\d+)\s*\]\s*=\s*true\s*$"
)

# Kernel.pbSetHealingSpot(map, x, y) — Uranium's TELEPORT/region-map anchor,
# NOT the white-out respawn (pbs_converter/heal_locations.py docstring). The
# fork's single `lastHealLocation` slot serves both white-out and teleport
# (engine/include/global.h:1106), so a `setrespawn` here would overwrite the
# white-out anchor that `pbSetPokemonCenter` just set. It resolves only when
# the literal (map, x, y) equals a minted heal location's tile; otherwise it
# queues with the precise reason.
_SET_HEALING_SPOT_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbSetHealingSpot\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,"
    r"\s*(-?\d+)\s*\)\s*$"
)

# -- Essentials one-line Ruby guards (`<statement> if $game_variables[V]==K`) ---
# RMXP script rows routinely carry a whole statement plus a trailing modifier-if
# on one line; the starter grant (Map050 EV019 cmds 9-16) is the canonical case.
# Parsed as (statement, optional guard) so each statement idiom below only has
# to match its own bare form.
_RUBY_GUARD_RE = re.compile(
    r"^(?P<stmt>.*?)\s+if\s+\$game_variables\[\s*(?P<var>\d+)\s*\]\s*==\s*(?P<val>-?\d+)\s*$"
)

# pbAddPokemon / pbAddPokemonSilent (PSystem_Utilities.rb:1710,1730). The two
# are NOT the same conversion, and the difference is the whole ceremony:
#
#   pbAddPokemon       -> "{player} obtained {species}!" + \me[PU-PokemonObtained]
#                         + pbNicknameAndStore (nickname prompt, party or PC)
#   pbAddPokemonSilent -> straight into the party/box, no message, no prompt
#
# Emitting a bare `givemon` for the loud form (what we did until 2026-08-01)
# silently dropped a fanfare, a message and a nickname prompt at 26 call sites
# across 11 events. Every piece has a native host and vanilla's own gift flow
# uses exactly them (engine/data/maps/LittlerootTown_ProfessorBirchsLab/
# scripts.inc:333-372 + engine/data/scripts/pc_transfer.inc), so this is a
# native-analog restoration, not an invention (§4.7).
_ADD_POKEMON_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbAddPokemon\(\s*(?:::)?PBSpecies::([A-Za-z0-9_]+)\s*,\s*(\d+)\s*\)\s*$"
)
_ADD_POKEMON_SILENT_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbAddPokemonSilent\(\s*(?:::)?PBSpecies::([A-Za-z0-9_]+)"
    r"\s*,\s*(\d+)\s*\)\s*$"
)

# $game_switches[61] = true — a direct switch write from Ruby rather than a
# code-121 Control Switches command. Same registry path as _emit_control_switches
# (never hardcode a flag name — CLAUDE.md §6).
_SWITCH_ASSIGN_RE = re.compile(
    r"^\s*\$game_switches\[\s*(\d+)\s*\]\s*=\s*(true|false)\s*$"
)

# Uranium's Nuzlocke-mode heal loop (`for i in $Trainer.party / i.nuzlocke_heal /
# end`, Map050 EV019 cmds 219-221). Always immediately followed by a code-314
# Recover All, which already emits special(HealPlayerParty) — the loop exists
# only to bypass Uranium's own Nuzlocke restriction on that command. We have no
# Nuzlocke mode, so the 314 alone is the whole behaviour. Breadcrumb, no queue.
_NUZLOCKE_HEAL_STRIP_RE = re.compile(
    r"^\s*(?:for\s+i\s+in\s+\$Trainer\.party|i\.nuzlocke_heal|end)\s*$"
)

# -- pbStarterSelector scene (Map050 EV005 player pick / EV019 Theo's pick) ----
# Uranium's full-screen starter-reveal presentation. The speech and the reveal
# are recovered natively (showmonpic/hidemonpic — engine/asm/macros/event.inc
# :1002,1010, the same pair FRLG's Oak's Lab uses for its own starter reveal);
# the animated background planes are dropped. Content lives in
# reference/starter_selector_scene.json, never inline here (CLAUDE.md §4.3).
#
# The argument is a Ruby local built over the preceding script rows
# (`x=pbGet(151)` / `x-=2` / `x=2 if x==-1`), so the three shapes below are
# tracked into _ruby_locals and replayed per source-var value at emit time.
# Recognized by `ruby_idioms.match_local_from_var` / `match_local_addsub` /
# `match_local_wrap` (C8 stage 6 — AST shapes, not regexes).

# pbGet(id) / pbSet(id, value) — thin wrappers over $game_variables
# (reference/scripts_dump/170__PSystem_Utilities.rb:2516-2528):
#   def pbGet(id); return 0 if !id || !$game_variables; return $game_variables[id]; end
#   def pbSet(id,value); if id && id>=0; $game_variables[id]=value ...; end
# `pbSet`'s `$game_map.need_refresh = true` side effect (a tile-redraw hint)
# has no GBA equivalent and is a deliberate no-op — nothing to fail loud
# about, so it is simply not emitted.
#
# Only the fully-literal shapes are resolved deterministically here
# (REDERIVATION_PLAN.md item 4, "trivial"): a plain `pbSet(<int>, <int>)`
# statement, and `$game_variables[<int>] = pbGet(<int>)` (pbGet used exactly
# where a plain variable read is expected — copied straight through, no
# arithmetic). Any computed argument (array indexing, `$Trainer.*` reads,
# ternaries, arithmetic — the overwhelming majority of real corpus call
# sites; see the head-match fallbacks below) is deliberately NOT evaluated
# (no Ruby expression evaluator, CLAUDE.md §4.5) and queues instead, with a
# reason naming the specific unsupported shape.
_PBSET_LITERAL_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbSet\(\s*(?P<var>\d+)\s*,\s*(?P<val>-?\d+)\s*\)\s*$"
)
_PBSET_HEAD_RE = re.compile(r"^\s*(?:Kernel\.)?pbSet\(")
_PBGET_ASSIGN_LITERAL_RE = re.compile(
    r"^\s*\$game_variables\[\s*(?P<target>\d+)\s*\]\s*=\s*"
    r"(?:Kernel\.)?pbGet\(\s*(?P<source>\d+)\s*\)\s*$"
)
_PBGET_HEAD_RE = re.compile(r"(?:Kernel\.)?pbGet\(")
_STARTER_SELECTOR_RE = re.compile(
    r"^\s*pbStarterSelector\(\s*([a-z_]\w*)\s*(?:,\s*(true|false)\s*)?\)\s*$"
)
# The player's own pick passes the variable straight through, with no Ruby
# local in between: pbStarterSelector(pbGet(151)).
_STARTER_SELECTOR_PBGET_RE = re.compile(
    r"^\s*pbStarterSelector\(\s*pbGet\(\s*(\d+)\s*\)\s*(?:,\s*(true|false)\s*)?\)\s*$"
)

# -- array-valued game variables (Map050 EV005's aptitude tally) ---------------
# Essentials lets a game variable hold a Ruby Array. Uranium uses it in exactly
# ONE place (corpus census 2026-08-01: 1 array literal, 4 indexed bumps, 1
# argmax — all Map050 EV005), so this is deliberately a narrow idiom rather
# than a general array subsystem; `test_aptitude_tally_is_still_one_of_a_kind`
# pins the count so a second site re-opens the design instead of silently
# reusing it.
#
# The array becomes N scalar scratch vars. VAR_TEMP_* is right: the whole
# lifetime is inside one scene on one map (the buckets are dead the moment the
# argmax lands in the real variable), and the fork zeroes temps on map change.
# VAR_TEMP_0/1 are this transpiler's own scratch (_ALIGN_AXIS_VAR); the
# buckets take 3/4/5, the same three the (now retired) hand conversion used
# and boot-walked. NB the registry's VAR_TEMP_MOVE_CHOICE is NOT VAR_TEMP_2 —
# it is a minted var in the Uranium range (data/scripts/uranium_flags.h), so
# it cannot collide with these.
_ARRAY_BUCKET_VARS = ("VAR_TEMP_3", "VAR_TEMP_4", "VAR_TEMP_5")
# The array literal, the indexed bump, the argmax, the `if x==A / x=B` remap
# chain and the write-back to a real variable are recognized by
# `ruby_idioms.match_array_literal` / `match_array_bump` /
# `match_array_argmax` / `match_remap_arm_open` + `match_local_const_assign`
# + `is_block_end` / `match_var_from_local` (C8 stage 6).

# ``$game_variables[N]=$Trainer.party.length`` (Map068 EV001 page1 cmd14 /
# page2 cmd8, both var 43). Fork-native ``CalculatePlayerPartyCount``
# (engine/data/specials.inc:154, engine/src/pokemon.c:3495) returns the
# player's party count; ``specialvar`` (engine/asm/macros/event.inc:303)
# writes a special's return value into a script variable in one command —
# no scratch var needed. The RMXP var must resolve through the registry
# (CLAUDE.md §6); an unnamed variable returns None so the row keeps queueing
# rather than inventing/reusing a scratch VAR_TEMP_* for a real RMXP var.
_PARTY_LENGTH_ASSIGN_RE = re.compile(
    r"^\s*\$game_variables\[\s*(\d+)\s*\]\s*=\s*\$Trainer\.party\.length\s*$"
)

# -- string-valued Ruby local + indexed text readback (Map032 EV9's starter
# name-back) ---------------------------------------------------------------
# `list=["Orchynx","Raptorch","Eletux"]` binds a plain (non-$game_variables)
# Ruby local to an ordered string literal; `$game_variables[3]=list[x]` then
# indexes it by the SAME local `x` already tracked by
# `ruby_idioms.match_local_from_var`/`match_local_wrap` above (Uranium's
# `x=pbGet(151); x=0 if x==3`) and also materialized into a real var by
# `match_var_from_local`'s plain-local
# arm (`$game_variables[1]=x`, the same `x`). Nothing is emitted for either
# row — like the other Ruby-local trackers, they only feed a later idiom,
# here `\v[3]` in the very next dialogue row's text
# (`_PageEmitter._emit_value_var_text`). Corpus census 2026-08-02: this
# string-array shape is ONE site (`list=[` never appears elsewhere), unlike
# the `x=pbGet(151)` readback itself, which recurs — see the plain-local
# materialize arm's own docstring. Both rows are recognized by
# `ruby_idioms.match_string_list` / `match_var_from_list_index` (C8 stage 6).

# u16 subtract-and-test-sign threshold. NOT 32768: 0x8000 is SPECIAL_VARS_START
# (include/constants/vars.h), and the `compare` macro (asm/macros/event.inc)
# auto-selects compare_var_to_var for a literal in that range — which silently
# compared against VAR_0x8000, the engine's own `switch` scratch. That was the
# 2026-07-21 always-Eletux bug; 32767 has the same semantics
# (A>=B <=> (A-B) <= 0x7FFF) and is outside every reserved range.
_SIGN_TEST_MAX = 32767

# $PokemonGlobal.randomizer — Uranium's randomizer *mode*, a new-game option we
# do not implement. Every code-111 gated on it picks the normal-play arm: the
# RMXP `else` block. Emitting the `then` block instead would hand out random
# species. See _emit_randomizer_branch.
_RANDOMIZER_MODE_RE = re.compile(r"^\s*\$PokemonGlobal\.randomizer\s*$")

# Kernel.pbPokerus? — the Pokerus infection check. Deferred to CH18 (Nuclear
# Plant Epsilon, its home chapter — reference/chapters.json), so no Pokemon in
# our ROM is ever infected and the check is statically false, same collapse
# as _RANDOMIZER_MODE_RE below. See _emit_pokerus_branch. CH03_TODO.md
# decision #4 update (2026-08-14): Map068_EV001_Page1's healing-counter YES
# branch gates on this, and the RMXP else arm (not the then arm) carries the
# scene's actual closing content (the nurse's return-facing movement plus the
# "restored to full health"/"we hope to see you again" messages) — dropping
# the whole conditional, as the generic script-condition path does, silently
# truncated the healing scene (playtest missed it; see ch03.py's B4 note).
_POKERUS_CHECK_RE = re.compile(r"^\s*Kernel\.pbPokerus\?\s*$")

# Essentials inline-choice text escape (SLICE1_TODO #17): a Show Text message
# trailing \ch[var,ifCancel,opt1,opt2,...] (reference/scripts_dump/059_Messages.rb
# :1218-1225, 1360-1362, 1429-1465). Parsing (marker detection, comma-split
# fields, color-code stripping) now lives in `conversion_agent.inline_choice`
# (CLAUDE.md §4.3 -- C8 stage 3 part A); this module keeps only the emit-side
# work (var-name resolution, text translation, dynmultichoice/queue lines).

# ``\v[N]`` game-variable text substitution — normally unrecognized (queues,
# see translate_text_codes). _PageEmitter._emit_value_var_text resolves the
# one shape a tracked list-index readback produces (ruby_idioms.match_var_from_list_index);
# any other \v[N] still falls through and queues.
_VALUE_VAR_RE = re.compile(r"\\v\[(\d+)\]")

# ``\b``/``\B`` — Essentials' message pre-processor expands this to a whole-
# line blue text-colour tag (PScreen_Message.rb-family gsub:
# ``text.gsub!(/\\[Bb]/,"<c2=6546675A>")``), the counterpart to ``\r``'s red
# ``<c2=043C675A>``. It carries no mechanical meaning — purely cosmetic tint.
# Design decision 2026-08-19: drop the code rather than reproduce the colour
# (pokeemerald's message boxes render in a themed palette; an inline mid-
# dialogue colour swap would look out of place for a whole-line tint that
# never varies). Stripped specifically — every OTHER untranslated control
# code must keep queueing (CLAUDE.md §4.5); this is not a general "unknown
# backslash code" strip.
_BLUE_TEXT_CODE_RE = re.compile(r"\\[bB]")

# RMXP's own colour-change code, `\C[n]` (n = a palette slot; `\C[0]` resets).
# Uranium uses it to highlight item/place names mid-sentence, e.g. Map073 EV001
# cmd 18: `bring me a \C[3]Bike wheel\C[0] I can fix an old bicycle`. Same
# disposition and same reasoning as _BLUE_TEXT_CODE_RE above (2026-08-19):
# purely a tint, no mechanical meaning, dropped rather than reproduced. Also
# stripped specifically — `\r`, `\v[n]` and every other code keep queueing.
_COLOUR_TEXT_CODE_RE = re.compile(r"\\C\[\d+\]")

# -- canlose trainer battle idiom (type-12 pbTrainerBattle inside a 111) ------
# reference/guides/canlose_battle_pipeline_plan.md "Gap A — transpiler"; proven
# target shape: hand_conversions/Map050_EV019.pory (Theo's rival battle). A
# code-111 branch whose script condition is a losable ``pbTrainerBattle(...)``
# call converts to ``trainerbattle_earlyrival`` + a ``VAR_RESULT`` win/loss
# branch instead of queuing the whole conditional. Same parsing as
# ``deterministic.classify_trainer_battle`` (lines ~842-874) — reimplemented
# here rather than imported, since ``deterministic.py`` is out of scope for
# this change (private helpers there aren't meant to be shared across
# modules).
_CANLOSE_TRAINER_CLASS_RE = re.compile(r"(?:::)?PBTrainers::(\w+)")
_CANLOSE_DEFEAT_TEXT_RE = re.compile(r'_I\("((?:[^"\\]|\\.)*)"\)')
_CANLOSE_STRIP_I_RE = re.compile(r'_I\("(?:[^"\\]|\\.)*"\)')
_CANLOSE_CALL_ARGS_RE = re.compile(r"pbTrainerBattle\((.*?)\)\s*$", re.DOTALL)
_CANLOSE_NAME_RE = re.compile(r'"([^"]*)"')
# Runtime party selection: ``party_id == pbGet(N) + K`` (Theo: N=151, K=18).
# A literal integer party_id is handled separately; any other expression
# shape falls through to the generic queue rather than being guessed
# (CLAUDE.md §4.5).
_CANLOSE_PBGET_PLUS_RE = re.compile(r"^pbGet\(\s*(\d+)\s*\)\s*\+\s*(\d+)$")

# -- starter-dependent rival battle (CH06 Map040 EV079) -----------------------
# The exact script-row run, in order. Switch -> party mapping is RMXP's own
# (61 -> p=1, 59 -> p=2, 60 -> p=3); any deviation (other ids, extra/missing
# rows, non-literal values) does not collapse and falls to the generic queue.
_STARTER_RIVAL_ROWS: tuple[tuple[str, int, int], ...] = (
    (r"p=1 if $game_switches[61] == true", 61, 1),
    (r"p=2 if $game_switches[59] == true", 59, 2),
    (r"p=3 if $game_switches[60] == true", 60, 3),
)
_STARTER_RIVAL_VAR_ROW = "$game_variables[1]=p"
_STARTER_RIVAL_VAR_ID = 1
_STARTER_RIVAL_CALL_RE = re.compile(
    r'^pbTrainerBattle\(PBTrainers::(\w+),"([^"]+)",'
    r'_I\("((?:[^"\\]|\\.)*)"\),false,pbGet\(1\)\)$'
)

# -- native object-template idioms (item balls, berry trees, pushable boulders) --
# rpg2gba wave 2026-08-08 (boulders added 2026-09-12, REDERIVATION_PLAN.md
# §15.1 item 8): item balls, berry plants, and pushable Strength boulders are
# converted to the fork's NATIVE object-event systems (Common_EventScript_
# FindItem / GetItemBallIdAndAmountFromTemplate — engine/src/item_ball.c —
# BerryTreeScript / MOVEMENT_TYPE_BERRY_TREE_GROWTH — engine/src/berry.c —
# and OBJ_EVENT_GFX_PUSHABLE_BOULDER / TryPushBoulder — engine/src/
# field_player_avatar.c) instead of being lowered command-by-command.
# Detection here is EVENT-level
# (scans every page's raw commands, not the parsed control-flow tree) and
# runs in ``transpile_driver.transpile_map`` BEFORE both the idiom-collapse
# classifiers (``deterministic.classify_ground_item`` already lowers bare
# pbItemBall to giveitem/setflag) and the general per-command transpiler — a
# claimed event contributes NO .pory text and NO queue entry (same
# disposition as the diagonal-stair skip in transpile_driver.py), only a
# ``Map{id:03d}.template_fields.json`` sidecar row a different agent's
# consumer turns into object-template fields.
#
# ``::PBItems::`` and bare ``PBItems::`` both occur in the corpus (see the
# pbPokemonMart classifier's identical tolerance in deterministic.py); the
# optional amount only appears on the item-ball call, never on pbPickBerry's
# quantity argument (that quantity is Uranium's per-pick RNG range, not the
# planted item — the object template doesn't carry it).
_ITEM_BALL_CALL_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbItemBall\(\s*(?:::)?PBItems::(\w+)\s*(?:,\s*(\d+)\s*)?\)\s*$"
)
_BERRY_PLANT_CALL_RE = re.compile(r"^\s*pbBerryPlant\s*$")
_PICK_BERRY_CALL_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbPickBerry\(\s*(?:::)?PBItems::(\w+)\s*,\s*(\d+)\s*\)\s*$"
)
_PICK_BERRY_ANY_RE = re.compile(r"pbPickBerry\b")

# REDERIVATION_PLAN.md §15.1 item 8 (third TF_KIND_* instance, "no engine/
# changes"): a pushable Strength boulder. `pbPushThisBoulder`
# (reference/scripts_dump/101__PField_Field.rb:2850) is a zero-arg predicate —
# `if $PokemonMap.strengthUsed then pbPushThisEvent; return true end` — so
# there is no argument shape to capture, unlike item balls/berries. The five
# corpus rows currently staged (Map019 EV1/2/3, Map031 EV1/37 — confirmed
# against output/uranium-build/transpile_unhandled.jsonl, matching the plan's
# claimed count exactly) are all single-page events named "Boulder" whose
# ENTIRE body is a bare `pbPushThisBoulder` script call (code 355), optionally
# followed by an SE row, then the page terminator — the whole event IS the
# native object placement, same shape as item balls/berry trees.
#
# The push itself is ALREADY NATIVE pokeemerald-expansion, keyed purely on
# object graphics id: `TryPushBoulder` checks
# `gObjectEvents[id].graphicsId == OBJ_EVENT_GFX_PUSHABLE_BOULDER`
# (engine/src/field_player_avatar.c:1044, constant defined at
# engine/include/constants/event_objects.h:113) and drives the push via
# `Task_PushBoulder`/`sPushBoulderFuncs` (:1822-1878). No engine/ change is
# needed to support this idiom — only the pipeline needs to know to place the
# object with that graphics id instead of transpiling a script for it.
#
# Deliberately does NOT match the code-111 `if pbPushThisBoulder ... end`
# conditional-branch shape that also occurs corpus-wide on unstaged maps
# (reference/recon/uranium_real_commands.md:80 counts 84 total instances
# across both shapes) — that shape wraps an arbitrary branch body this
# detector has never inspected, and is out of scope for this work item, which
# only clears the 5 bare-call rows actually queued today. An event using that
# shape falls through to the general transpiler/classifiers and queues, per
# CLAUDE.md §4.5 (fail loud, don't guess).
_PUSH_BOULDER_CALL_RE = re.compile(r"^\s*(?:Kernel\.)?pbPushThisBoulder\s*$")


def _script_condition_text(cmd: dict) -> str | None:
    """The literal Ruby text of a code-111 script-type (params[0]==12)
    condition, or ``None`` if ``cmd`` isn't one."""
    if cmd.get("code") != CONDITIONAL_BRANCH:
        return None
    params = cmd.get("parameters", [])
    if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
        return None
    return params[1]


def _script_call_text(cmd: dict) -> str | None:
    """The literal Ruby text of a code-355/655 script-call row, or ``None``."""
    if cmd.get("code") not in (SCRIPT, SCRIPT_CONT):
        return None
    params = cmd.get("parameters", [])
    if not params or not isinstance(params[0], str):
        return None
    return params[0]


def detect_item_ball(event: dict) -> tuple[str, int] | None:
    """Scan every page's raw commands for a ``pbItemBall(::PBItems::X[, N])``
    script condition (code 111). Returns ``(uranium_item_symbol, amount)``,
    amount defaulting to 1 when the call carries no explicit quantity, or
    ``None`` if the event doesn't contain the call at all."""
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            text = _script_condition_text(cmd)
            if text is None:
                continue
            m = _ITEM_BALL_CALL_RE.match(text)
            if m:
                amount = int(m.group(2)) if m.group(2) else 1
                return m.group(1), amount
    return None


def detect_berry_tree(event: dict) -> tuple[str | None, bool, int | None] | None:
    """Scan every page's raw commands for ``pbBerryPlant`` (code 355) and/or
    ``pbPickBerry(PBItems::X, n)`` (code 111).

    Keys ONLY on these two calls, never on the event's graphic name — a
    corpus census found four events that reuse berry-tree sprites for
    unrelated purposes (a credits trigger, a settings menu, a door sign, a
    puzzle NPC), and Map143's cooldown harvest nodes reuse a berry-adjacent
    graphic too but call ``pbReceiveItem``/``pbSetEventTime``, never these.

    Returns ``None`` when neither call appears (not a berry-plant event at
    all — caller falls through to the classifiers / general transpiler).
    Otherwise returns ``(uranium_berry_symbol_or_None, planted, yield)``:
    ``pbPickBerry`` present -> the pre-grown 2-/3-page kind, ``planted=True``,
    symbol and yield (the call's literal second argument, the tree's fixed
    first-pick count) from the call; ``pbPickBerry`` absent (bare-soil 1-page
    kind) -> ``(None, False, None)``. A ``pbPickBerry`` whose item or count
    is not a literal positive int, or two calls that disagree on the count,
    raises ``ValueError`` (CLAUDE.md §4.5) — no default yield. The 3-page Map117 variant (soil page duplicated
    before and after the tree page) needs no special case: scanning every
    page for both calls finds them regardless of how many soil pages flank
    the tree page.
    """
    has_plant = False
    berry_symbol: str | None = None
    berry_yield: int | None = None
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            script_text = _script_call_text(cmd)
            if script_text is not None and _BERRY_PLANT_CALL_RE.match(script_text):
                has_plant = True
                continue
            cond_text = _script_condition_text(cmd)
            if cond_text is not None:
                m = _PICK_BERRY_CALL_RE.match(cond_text)
                if m:
                    count = int(m.group(2))
                    if count < 1 or (berry_yield is not None and count != berry_yield):
                        raise ValueError(
                            f"transpiler: EV{event.get('id')!r} pbPickBerry yield "
                            f"{count} is not a positive int consistent with "
                            f"{berry_yield!r} on another page — cannot pick the "
                            f"tree's first-pick yield"
                        )
                    berry_symbol = m.group(1)
                    berry_yield = count
                elif _PICK_BERRY_ANY_RE.search(cond_text):
                    raise ValueError(
                        f"transpiler: EV{event.get('id')!r} pbPickBerry call "
                        f"{cond_text!r} has no literal PBItems item / positive-int "
                        f"yield — cannot read the tree's first-pick yield"
                    )
    if not has_plant and berry_symbol is None:
        return None
    return berry_symbol, berry_symbol is not None, berry_yield


def detect_push_boulder(event: dict) -> bool:
    """Scan every page's raw commands for a bare ``pbPushThisBoulder`` script
    call (code 355/655, no arguments — see ``_PUSH_BOULDER_CALL_RE``).

    Unlike ``detect_item_ball``/``detect_berry_tree`` there is no per-event
    payload to extract (the call takes no arguments and the object's graphics
    id — ``OBJ_EVENT_GFX_PUSHABLE_BOULDER`` — is fixed, not per-event data),
    so this returns a plain ``bool`` rather than an ``Optional[tuple]``:
    ``True`` when the idiom is present, ``False`` when it is not at all (the
    caller falls through to the classifiers / general transpiler, which will
    queue any other shape rather than guess)."""
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            text = _script_call_text(cmd)
            if text is not None and _PUSH_BOULDER_CALL_RE.match(text):
                return True
    return False


def _resolve_fork_item(
    ctx: "TranspileContext", uranium_symbol: str, *, map_id: int, event_id: int | None, kind: str
) -> str:
    """Uranium item symbol -> verified fork ``ITEM_*`` constant (CLAUDE.md
    §4.3 single source of truth: ``reference/uranium_id_map.json``'s
    ``items`` table, via ``ctx.item_id_map``; §4.7 forward check: the
    resolved constant must actually exist in the fork's headers, via
    ``ctx.fork_item_constants`` — the id map is known to name ITEM_*_BERRY
    constants (ACAI/HAFLI/GUARA/CUPU/BACU) the fork does not define. Fails
    loud on either miss — never silently drops the event or guesses a
    substitute; a substitution decision is a project-lead call (CLAUDE.md
    §10), not this function's to make."""
    where = f"Map{map_id:03d} EV{event_id!r}"
    const = ctx.item_id_map.get(uranium_symbol)
    if const is None:
        raise ValueError(
            f"transpiler: {where} ({kind}) references Uranium item "
            f"{uranium_symbol!r}, which has no entry in "
            f"reference/uranium_id_map.json's items table — fix the id map, "
            f"don't guess a constant."
        )
    if const not in ctx.fork_item_constants:
        raise ValueError(
            f"transpiler: {where} ({kind}) — Uranium item {uranium_symbol!r} "
            f"maps to {const}, which does not exist in "
            f"engine/include/constants/items.h. A substitution decision is "
            f"required from the project lead before this item/berry can "
            f"convert (CLAUDE.md §10) — this is not a bug to silently work "
            f"around."
        )
    return const


def resolve_native_object_template(map_id: int, event: dict, ctx: "TranspileContext") -> bool:
    """Detect the item-ball / berry-tree / pushable-boulder idioms on
    ``event`` and, on a match, record its ``Map{id:03d}.template_fields.json``
    payload on ``ctx``.

    Returns ``True`` when the event was claimed — the caller (``transpile_
    driver.transpile_map``) must emit NO ``.pory`` text and NO queue entry
    for it, exactly like the diagonal-stair skip; the native object-template
    fields are the whole story for these events. Returns ``False`` when
    none of the three idioms matched, so the caller proceeds to the idiom-collapse
    classifiers / general transpiler as usual.
    """
    event_id = event.get("id")

    item_ball = detect_item_ball(event)
    if item_ball is not None:
        symbol, amount = item_ball
        const = _resolve_fork_item(
            ctx, symbol, map_id=map_id, event_id=event_id, kind="item_ball"
        )
        ctx.record_template_fields(
            map_id, event_id, {"kind": "item_ball", "item": const, "amount": amount},
        )
        return True

    try:
        berry = detect_berry_tree(event)
    except ValueError as exc:
        raise ValueError(f"Map{map_id:03d}: {exc}") from exc
    if berry is not None:
        berry_symbol, planted, berry_yield = berry
        berry_const = (
            _resolve_fork_item(
                ctx, berry_symbol, map_id=map_id, event_id=event_id, kind="berry_tree"
            )
            if berry_symbol is not None
            else None
        )
        ctx.record_template_fields(
            map_id, event_id,
            {"kind": "berry_tree", "berry_item": berry_const, "planted": planted,
             "yield": berry_yield},
        )
        return True

    if detect_push_boulder(event):
        # No fork-item lookup needed (unlike item_ball/berry_tree) — the
        # boulder's only per-event fact is "it exists here"; the object
        # graphics id (OBJ_EVENT_GFX_PUSHABLE_BOULDER) and native push
        # behavior are fixed engine constants, not per-event data. Downstream
        # consumer (metadata_wiring.py's KNOWN_TEMPLATE_KINDS/validation/
        # emission, REDERIVATION_PLAN.md §15.1 item 8) still needs a
        # TF_KIND_PUSHABLE_BOULDER = "pushable_boulder" wiring pass — not
        # present yet as of this change (out of this change's file scope).
        ctx.record_template_fields(map_id, event_id, {"kind": "pushable_boulder"})
        return True

    return False


# -- queue entries ------------------------------------------------------------


@dataclass
class QueueEntry:
    """One unhandled.jsonl row (same shape the orchestrator wrote)."""

    map_id: int
    event_id: int | None
    event_name: str
    page: int
    line: int
    command_code: int
    description: str
    reason: str = "transpiler-unhandled"
    common_event_id: int | None = None

    def to_json(self) -> dict:
        out = {
            "map_id": self.map_id,
            "event_id": self.event_id,
            "event_name": self.event_name,
            "page": self.page,
            "line": self.line,
            "command_code": self.command_code,
            "description": self.description,
            "reason": self.reason,
        }
        if self.common_event_id is not None:
            out["common_event_id"] = self.common_event_id
            del out["map_id"]
        return out


# -- context ------------------------------------------------------------------


@dataclass
class TranspileContext:
    """Per-run state: the flag registry plus queue collection.

    ``registry`` is live and mutated (self/temp-switch mints, named-switch
    proposals); the driver owns persisting it. ``unhandled`` accumulates
    across events; the driver writes it out.
    """

    registry: FlagRegistry
    unhandled: list[QueueEntry] = field(default_factory=list)

    # Essentials symbol -> ITEM_* constant (deterministic.Context.items shape —
    # populated by whoever builds the context; empty means "not wired up",
    # same disposition as an unresolved symbol: the give-item idiom queues).
    items: dict[str, str] = field(default_factory=dict)

    # Uranium internal species name -> its SPECIES_* constant, straight from
    # reference/uranium_id_map.json's "species" table (CLAUDE.md §4.3 single
    # source of truth — never string-munged from the name). Populated by the
    # driver; empty means the id map isn't wired up (the pbHasSpecies? idiom
    # queues, same disposition as an unresolved item symbol above).
    species: dict[str, str] = field(default_factory=dict)

    # Uranium move internal name (``PBMoves::FEINT`` -> ``FEINT``) -> its
    # MOVE_* constant, from reference/uranium_id_map.json's "moves" table
    # (CLAUDE.md §4.3). Empty means "not wired by the driver": `move_constant`
    # then lazy-loads the repo's id map itself (the driver does not populate
    # this field yet). When ``fork_item_constants`` is non-empty a resolved
    # constant must also exist in the fork (§4.7 forward check).
    moves: dict[str, str] = field(default_factory=dict)

    # SPECIES_* constants that species_converter.stage has actually staged
    # into the fork (species_manifest.json), i.e. that the fork's headers
    # really define. A name resolving in `species` above is NOT sufficient
    # on its own for a `needs_engine` species (see ``needs_engine_species``
    # below) — most of Uranium's ~166 needs_engine species are id-mapped but
    # never staged, and emitting their constant would be an invented symbol
    # the gate correctly rejects. Populated by the driver.
    staged_species: frozenset[str] = field(default_factory=frozenset)

    # SPECIES_* constants for Uranium species that are vanilla reuses (e.g.
    # MAGIKARP) rather than one of the ~166 custom/reworked `needs_engine`
    # species — straight from reference/uranium_id_map.json's full species
    # table MINUS its ``needs_engine.species`` list (CLAUDE.md §4.3 single
    # source of truth). A vanilla species's constant already exists in
    # engine/include/constants/species.h with no staging step, so
    # ``staged_species_constant`` passes it through regardless of
    # ``staged_species``. This is a WHITELIST, not a blacklist: the default
    # (empty, id map not wired) means nothing is presumed vanilla and every
    # species must clear ``staged_species`` instead — the same fail-loud
    # default as before this field existed. Populated by the driver.
    vanilla_species: frozenset[str] = field(default_factory=frozenset)

    # (class_const, name, party_id) -> TRAINER_* constant, straight from
    # deterministic.Context.trainers (intermediate/trainers.json). Populated
    # by the driver; empty means "not wired up" — the canlose trainer-battle
    # idiom queues on a lookup miss, same disposition as an unresolved item
    # symbol above (CLAUDE.md §4.3: one source of truth, reused not re-derived).
    trainers: dict[tuple[str, str, int], str] = field(default_factory=dict)

    # reference/starter_selector_scene.json — the converted content of
    # Uranium's full-screen starter-reveal scene (speech + reveal line per
    # starter, plus Theo's variant). Populated by the driver; empty means the
    # data file isn't wired up and the pbStarterSelector idiom queues.
    starter_scene: dict = field(default_factory=dict)

    # RMXP character sheet name -> OBJ_EVENT_GFX_* constant, from
    # reference/npc_gfx_map.json (tileset_converter.npc_gfx owns that file).
    # Feeds the code-41 live sprite swap; empty means "not wired up" and every
    # change-graphic step queues.
    npc_gfx: dict[str, str] = field(default_factory=dict)

    # RMXP character sheet name -> {(direction, pattern): OBJ_EVENT_GFX_* constant},
    # from the same file's "states" entries (npc_gfx.load_npc_gfx_states). Only
    # sheets that carry more than one selectable visual state appear. A code-41
    # swap naming one of these resolves to the exact state's constant instead of
    # the sheet's; see _emit_route_with_gfx_swaps.
    npc_gfx_states: dict[str, dict[tuple[int, int], str]] = field(default_factory=dict)

    # (map_id, event_id, page_index) -> HEAL_LOCATION_* constant for a resolved
    # `Kernel.pbSetPokemonCenter` call site, straight from
    # rpg2gba.pbs_converter.heal_locations.call_site_heal_locations() (CLAUDE.md
    # §4.3 single source of truth). ``page_index`` here is 0-based — the same
    # basis as ``page_no`` below (set from ``page_idx`` in transpile_event,
    # matching the manifest row_id per #98/7e2e2668), NOT the 1-based script
    # block label numbering. Populated by the driver; a call site missing from
    # this table (unstaged map, unresolved bare call, or a common event — see
    # ``_emit_script_call``) queues instead of inventing a HEAL_LOCATION_*
    # (CLAUDE.md §4.7 forward check).
    heal_locations: dict[tuple[int, int, int], str] = field(default_factory=dict)

    # INGAME_TRADE_* const -> the staged ``ingame_trades.InGameTradeSpec`` for
    # every NPC trade the driver detected (single source of truth for the
    # sIngameTrades row). The pair idiom for ``pbChoosePokemon(.., proc{..})`` +
    # ``pbStartTrade`` asserts the call text agrees with this spec; an event
    # with no entry here queues rather than emitting an unverifiable trade.
    ingame_trades: dict[str, "_trades.InGameTradeSpec"] = field(default_factory=dict)

    # What the current page's closing wrapper releases (``release`` for the
    # lock/faceplayer and lock pages, ``releaseall`` for lockall), set by
    # ``transpile_event`` per page. RMXP's Exit Event Processing (115) leaves
    # the script early, so it must emit this before its ``end`` or the player
    # stays frozen. ``None`` for pages with no lock wrapper and for common
    # events (those ``return``).
    exit_epilogue: str | None = None

    # (uranium_map_id, x, y) -> HEAL_LOCATION_* constant for every minted heal
    # location's tile. Lets `Kernel.pbSetHealingSpot(m,x,y)` resolve ONLY when
    # its literal triple is exactly a minted heal location; empty by default
    # (the driver does not populate it yet), so every call queues loudly.
    healing_spots: dict[tuple[int, int, int], str] = field(default_factory=dict)

    # per-event cursor, set by transpile_event / transpile_common_event
    map_id: int = 0
    event_id: int | None = None
    event_name: str = ""
    event_x: int | None = None
    event_y: int | None = None
    page_no: int = 0
    common_event_id: int | None = None
    # Character-sheet name of the page being transpiled (set by transpile_page);
    # lets a self-targeted move route recognise a door-sheet event (native door
    # animation, see ``_door_self_route``).
    page_graphic: str = ""

    # Per-event traits recorded during transpile (e.g. "smashable_rock" from
    # the rock-smash native idiom below), keyed by (map_id, event_id). The
    # driver reads this to write the Map{id:03d}.traits.json sidecar — a
    # fixed schema shared with a downstream consumer (metadata_wiring.py /
    # stage_slice_scripts.py, owned by a different agent); don't rename.
    traits: dict[tuple[int, int], set[str]] = field(default_factory=dict)

    # Uranium internal item/berry symbol -> ITEM_* constant, from
    # reference/uranium_id_map.json's "items" table (CLAUDE.md §4.3). Used
    # ONLY by resolve_native_object_template (item ball / berry tree) — the
    # generic give-item idiom (pbReceiveItem) resolves through ``items``
    # above instead, a different Phase-2-derived table; the two are kept
    # separate on purpose (see resolve_native_object_template's docstring).
    # Populated by the driver; empty means every item-ball/berry-tree event
    # fails loud on lookup (a wiring bug, not corpus data).
    item_id_map: dict[str, str] = field(default_factory=dict)

    # Fork ITEM_* constants that actually exist (engine/include/constants/
    # items.h, via the fork-capability index — CLAUDE.md §4.7 forward
    # check). Populated by the driver from the same ForkIndex the
    # conversion-time gate already builds; empty means every item-ball/
    # berry-tree resolution fails loud (again, a wiring bug, not corpus
    # data — the driver always has a real index by the time it calls in).
    fork_item_constants: frozenset[str] = field(default_factory=frozenset)

    # Per-event native object-template description, keyed by (map_id,
    # event_id) — the Map{id:03d}.template_fields.json sidecar payload (see
    # resolve_native_object_template). Fixed schema, a contract with a
    # downstream consumer (metadata_wiring.py, owned by a different agent);
    # don't rename or reshape without updating that consumer too.
    template_fields: dict[tuple[int, int], dict] = field(default_factory=dict)

    # Events dropped whole by ``transpile_driver.transpile_map`` before ever
    # reaching a classifier or this transpiler (currently: diagonal-stair
    # "player touch" events superseded by the tileset layer's native
    # MB_SIDEWAYS_STAIRS_* metatile behavior — see
    # ``rpg2gba.tileset_converter.stairs``). These contribute NO .pory block
    # and NO unhandled-queue entry, but CLAUDE.md §4.5 forbids a silent drop,
    # so the driver records one row per skipped event here instead — visible
    # to ``transpile_corpus``'s summary the same way ``traits``/queue entries
    # are visible. Each row: {"map_id", "event_id", "event_name", "reason"}.
    skipped_stair_events: list[dict] = field(default_factory=list)

    def record_trait(self, trait: str) -> None:
        """Record a trait on the event currently being transpiled. No-op in
        a common event (no owning event id to key by — see ``event_id``)."""
        if self.event_id is None:
            return
        self.traits.setdefault((self.map_id, self.event_id), set()).add(trait)

    def record_template_fields(self, map_id: int, event_id: int | None, payload: dict) -> None:
        """Record the native object-template payload for one event, keyed
        explicitly by ``(map_id, event_id)`` rather than the cursor fields
        (``self.map_id``/``self.event_id``) — ``resolve_native_object_
        template`` runs BEFORE ``transpile_event`` sets those, from
        ``transpile_driver.transpile_map``'s per-event loop."""
        if event_id is None:
            return
        self.template_fields[(map_id, event_id)] = payload

    def queue(self, cmd_index: int, code: int, description: str) -> str:
        """Record one unhandled command; return the in-script marker comment."""
        entry = QueueEntry(
            map_id=self.map_id,
            event_id=self.event_id,
            event_name=self.event_name,
            page=self.page_no,
            line=cmd_index,
            command_code=code,
            description=description,
            common_event_id=self.common_event_id,
        )
        self.unhandled.append(entry)
        return f"# UNHANDLED code {code}: {description}"

    # -- registry glue (every name goes through the registry, CLAUDE.md §6) --

    def flag_for_switch(self, switch_id: int) -> str | None:
        """Resolve a Uranium switch id to a FLAG_* name, minting from the
        developer-given label when one exists. ``None`` = unnamed or script
        switch → caller queues."""
        return resolve_switch_flag(self.registry, switch_id)

    def var_for_variable(self, variable_id: int) -> str | None:
        return resolve_variable_var(self.registry, variable_id)

    def self_switch_flag(self, letter: str) -> str:
        assert self.event_id is not None
        return self.registry.mint_self_switch(self.map_id, self.event_id, letter)

    def move_constant(self, internal_name: str) -> str | None:
        """Uranium move internal name -> a MOVE_* constant the fork defines,
        else None (caller queues). See the ``moves`` field."""
        if not self.moves:
            self.moves = _default_move_table()
        const = self.moves.get(internal_name)
        if const is None:
            return None
        if self.fork_item_constants and const not in self.fork_item_constants:
            return None
        return const

    def staged_species_constant(self, internal_name: str) -> str | None:
        """Resolve a Uranium species internal name to its SPECIES_* constant,
        but ONLY if the fork's headers actually define it. ``None`` (caller
        queues) for an id-map miss, or for an id-map hit that is neither
        staged nor a known vanilla reuse — the important case: a species like
        URAYNE resolves fine through the id map but was never staged, so its
        constant doesn't exist in the fork's headers. A species in
        ``vanilla_species`` (e.g. MAGIKARP) is a vanilla reuse — its constant
        already ships in the fork with no staging step, so it passes
        regardless of ``staged_species``."""
        const = self.species.get(internal_name)
        if const is None:
            return None
        if const in self.staged_species or const in self.vanilla_species:
            return const
        return None


def _default_move_table() -> dict[str, str]:
    """The repo's id map "moves" table (used only when the driver has not
    wired `TranspileContext.moves`)."""
    from rpg2gba.pbs_converter._id_map import IdMap

    path = Path(__file__).resolve().parents[3] / "reference" / "uranium_id_map.json"
    return dict(IdMap.load(path).by_category["moves"])


# -- control-flow tree --------------------------------------------------------


@dataclass
class Node:
    cmd: dict
    index: int  # position in the flat page list (queue line references)


@dataclass
class Leaf(Node):
    pass


@dataclass
class TextRun(Node):
    """A Show Text (101) with its 401 continuations merged."""

    text: str = ""


@dataclass
class IfNode(Node):
    then: list[Node] = field(default_factory=list)
    otherwise: list[Node] | None = None


@dataclass
class ChoiceNode(Node):
    # arms: (choice_index | None for cancel, choice_text, children)
    arms: list[tuple[int | None, str, list[Node]]] = field(default_factory=list)


@dataclass
class LoopNode(Node):
    children: list[Node] = field(default_factory=list)


@dataclass
class StarterRivalBattle(Node):
    """Synthetic node: the four-row ``p=N if $game_switches[S] == true`` /
    ``$game_variables[1]=p`` script run plus the ``pbTrainerBattle(...,
    pbGet(1))`` code-111 that follows it (Map040 EV079, rival Theo's CH06
    starter-dependent battle). Built by
    ``Emitter._collapse_starter_rival_battles``; ``cond`` is the original
    ``IfNode`` and ``first_index`` the index of the 355 row."""

    cond: "IfNode | None" = None


@dataclass
class PickTrade(Node):
    """Synthetic node: ``pbChoosePokemon(v, n, proc{not egg and species==X})``
    plus the code-111 "a mon was chosen" test that immediately follows it
    (Map046 EV014). Built by ``_PageEmitter._collapse_pick_groups``; ``cond`` is
    the original ``IfNode`` and ``index`` the 355 row's."""

    cond: "IfNode | None" = None
    chosen_var: int = 0
    requested: str = ""  # Uranium internal species name from the proc


@dataclass
class NameEntry(Node):
    """Synthetic node: the three-row ``pkmn=$Trainer.party[pbGet(v)]`` /
    ``species=PBSpecies.getName(pkmn.species)`` / ``pbTextEntry(..., m, pkmn)``
    nickname-entry statement group (Map046 EV002)."""

    chosen_var: int = 0
    new_name_var: int = 0


@dataclass
class NameApply(Node):
    """Synthetic node: ``pkmn=$Trainer.party[pbGet(v)]`` + ``pkmn.name=pbGet(m)``
    -- applying the entered name to the mon, which the native rename has
    already done."""

    chosen_var: int = 0
    new_name_var: int = 0


def parse_tree(commands: list[dict]) -> list[Node]:
    """Nest a page's flat command list into a control-flow tree.

    Driven by a cursor over the list; each opener consumes to its matching
    closer at the same indent. Blank code-0 rows are structure markers
    (choice-arm/branch terminators), not content — dropped here.
    """
    pos = 0

    def parse_block(indent: int) -> list[Node]:
        nonlocal pos
        nodes: list[Node] = []
        while pos < len(commands):
            cmd = commands[pos]
            code = cmd.get("code", 0)
            cmd_indent = cmd.get("indent", 0)
            if cmd_indent < indent:
                return nodes  # end of this block — closer handled by caller
            if cmd_indent > indent:
                # Shouldn't happen with well-formed data; treat as content of
                # the current block rather than silently skipping.
                nodes.extend(parse_block(cmd_indent))
                continue

            if code in (ELSE_BRANCH, BRANCH_END, CHOICE_WHEN, CHOICE_CANCEL,
                        CHOICES_END, REPEAT_ABOVE):
                return nodes  # a closer/arm at our indent — caller's job

            idx = pos
            if code == SHOW_TEXT:
                params = cmd.get("parameters", [])
                parts = [params[0] if params else ""]
                pos += 1
                while pos < len(commands) and commands[pos].get("code") == SHOW_TEXT_CONT:
                    p = commands[pos].get("parameters", [])
                    parts.append(p[0] if p else "")
                    pos += 1
                nodes.append(TextRun(cmd, idx, text=join_text_lines([str(s) for s in parts])))
            elif code == CONDITIONAL_BRANCH:
                pos += 1
                then = parse_block(indent + 1)
                otherwise: list[Node] | None = None
                if pos < len(commands) and commands[pos].get("code") == ELSE_BRANCH \
                        and commands[pos].get("indent") == indent:
                    pos += 1
                    otherwise = parse_block(indent + 1)
                if pos < len(commands) and commands[pos].get("code") == BRANCH_END \
                        and commands[pos].get("indent") == indent:
                    pos += 1
                nodes.append(IfNode(cmd, idx, then=then, otherwise=otherwise))
            elif code == SHOW_CHOICES:
                pos += 1
                node = ChoiceNode(cmd, idx)
                params = cmd.get("parameters", [])
                choice_texts = params[0] if params else []
                while pos < len(commands):
                    arm = commands[pos]
                    a_code, a_indent = arm.get("code"), arm.get("indent", 0)
                    if a_indent != indent:
                        break
                    if a_code == CHOICE_WHEN:
                        a_params = arm.get("parameters", [])
                        c_idx = a_params[0] if a_params else 0
                        c_text = (
                            a_params[1] if len(a_params) > 1
                            else (choice_texts[c_idx] if c_idx < len(choice_texts) else "")
                        )
                        pos += 1
                        node.arms.append((c_idx, str(c_text), parse_block(indent + 1)))
                    elif a_code == CHOICE_CANCEL:
                        pos += 1
                        node.arms.append((None, "", parse_block(indent + 1)))
                    elif a_code == CHOICES_END:
                        pos += 1
                        break
                    else:
                        break
                nodes.append(node)
            elif code == LOOP:
                pos += 1
                children = parse_block(indent + 1)
                if pos < len(commands) and commands[pos].get("code") == REPEAT_ABOVE \
                        and commands[pos].get("indent") == indent:
                    pos += 1
                nodes.append(LoopNode(cmd, idx, children=children))
            elif code == 0:
                pos += 1  # blank terminator row — structure only
            else:
                pos += 1
                nodes.append(Leaf(cmd, idx))
        return nodes

    return parse_block(0)


def _tree_writes_self_switch(nodes: list[Node]) -> bool:
    """True if any node in ``nodes``, recursively, is a raw code-123 Control
    Self Switch command. Used by ``_emit_facility_trainer_battle_idiom`` to
    tell a repeatable facility win-body (plain dialogue) apart from a
    one-time sight trainer's win-body (dialogue + a self-switch flip so the
    page never re-triggers) — the two idioms share an identical inner
    code-111/pbTrainerBattle shape and only differ here."""
    for n in nodes:
        if n.cmd.get("code") == CONTROL_SELF_SWITCH:
            return True
        if isinstance(n, IfNode):
            if _tree_writes_self_switch(n.then):
                return True
            if n.otherwise and _tree_writes_self_switch(n.otherwise):
                return True
        elif isinstance(n, ChoiceNode):
            for _, _, children in n.arms:
                if _tree_writes_self_switch(children):
                    return True
        elif isinstance(n, LoopNode):
            if _tree_writes_self_switch(n.children):
                return True
    return False


@dataclass
class _RubyLocal:
    """An integer Ruby local tracked across script rows: ``$game_variables
    [source_var]`` plus ``offset``, with an optional ``wrap`` remap applied
    afterwards (``x = to if x == from``)."""

    source_var: int
    offset: int = 0
    wrap: tuple[int, int] | None = None
    # Set when the local is the argmax of an array-valued variable rather than
    # plain arithmetic on a scalar one; `remap` collects the `if x==A / x=B`
    # permutation the original applies to the winning index afterwards.
    argmax_of: int | None = None
    remap: dict[int, int] = field(default_factory=dict)

    def value_for(self, source_value: int) -> int:
        v = source_value + self.offset
        if self.wrap is not None and v == self.wrap[0]:
            return self.wrap[1]
        return v


# -- RMXP labels (118) / jump-to-label (119) ----------------------------------
# RMXP's intra-page goto. The fork has the same primitive (`goto`, a jump
# inside one script context), so the conversion is a basic-block split: the
# labelled region is hoisted into its own `script` block and both the
# fall-through *and* every jump become `goto(<block>)`.
#
# The hoist is only sound when the region TERMINATES — control must never need
# to fall back into whatever structure enclosed the label, because the hoisted
# block has no way to return there. Two shapes qualify (corpus census
# 2026-08-01, 51 labels / 138 jumps over 23 distinct names):
#
#   * the region runs to the end of the page (29 labels) — nothing follows in
#     any enclosing scope either way;
#   * the region ends at a same-indent code-115 Exit Event Processing
#     (2 labels, incl. Map050 EV005's aptitude-test body) — an explicit `end`.
#
# The remaining 20 sit inside a choice/branch arm and fall out on a dedent;
# hoisting those needs a continuation the fork's `goto` can't express, so they
# queue (§4.5). Pages carrying more than one label also queue as a unit: the
# regions nest, and chaining them correctly is a separate unit of work.
_LABEL_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]+")


def _label_block_suffix(name: str) -> str:
    """`Choice Made` -> `ChoiceMade`, for a Poryscript-legal block label."""
    parts = [p for p in _LABEL_SANITIZE_RE.split(str(name)) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Label"


def hoistable_label_region(commands: list[dict]) -> tuple[int, int] | None:
    """The single hoistable label's ``(label_index, region_end_exclusive)``.

    Returns None when the page has no label, more than one, or the one it has
    does not terminate (see the module note above) — every such case leaves
    the 118/119 rows to queue.
    """
    label_positions = [i for i, c in enumerate(commands) if c.get("code") == LABEL]
    if len(label_positions) != 1:
        return None
    i = label_positions[0]
    indent = commands[i].get("indent", 0)
    for j in range(i + 1, len(commands)):
        if commands[j].get("indent", 0) < indent:
            return None  # falls out of the enclosing block — no continuation
        if (commands[j].get("indent", 0) == indent
                and commands[j].get("code") == EXIT_EVENT):
            return i, j + 1  # region owns the `end`
    return i, len(commands)  # runs to the end of the page


def loop_label_region(commands: list[dict]) -> tuple[int, int] | None:
    """The backward-jump loop shape: ``(label_index, region_end_exclusive)``.

    For a page `hoistable_label_region` rejects because the label sits inside
    a choice/branch arm. Qualifies when: the page has exactly one label; it has
    at least one ``119`` jump; every ``119`` names it, comes AFTER it and lies
    inside the label's enclosing block (the label's region = label ..
    first following row of lower indent, or the page end); and every jump is
    the last statement of its own block (next row has lower indent) -- poryscript
    requires ``continue`` to be last in its scope. Map046 EV003 page 1 (the
    tutor's "teach another?" loop) is the corpus case. None otherwise: the
    118/119 rows then queue as before."""
    label_positions = [i for i, c in enumerate(commands) if c.get("code") == LABEL]
    if len(label_positions) != 1:
        return None
    i = label_positions[0]
    indent = commands[i].get("indent", 0)
    name = (commands[i].get("parameters") or [""])[0]
    end = len(commands)
    for j in range(i + 1, len(commands)):
        if commands[j].get("indent", 0) < indent:
            end = j
            break
    jumps = [j for j, c in enumerate(commands) if c.get("code") == JUMP_TO_LABEL]
    if not jumps:
        return None
    for j in jumps:
        if (commands[j].get("parameters") or [None])[0] != name:
            return None
        if not (i < j < end):
            return None
        # RMXP pads each block with code-0 rows at the block's own indent.
        k = j + 1
        while k < len(commands) and commands[k].get("code") == 0:
            k += 1
        nxt = commands[k].get("indent", 0) if k < len(commands) else -1
        if nxt >= commands[j].get("indent", 0):
            return None
    return i, end


def _load_starter_selector_scene(reference_dir: Path) -> dict:
    path = reference_dir / "starter_selector_scene.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_consecutive_routes(nodes: list[Node]) -> list[Node]:
    """Fuse runs of code-209 Set Move Route nodes that target the same actor
    with no intervening Wait For Move Completion.

    RMXP runs such routes as one continuous motion (each 209 replaces the
    actor's route, and the interpreter only yields at the paired 210). The fork
    does not: ``applymovement`` on an object whose movement is still in flight
    is **dropped**, so the second route silently never runs and the actor stops
    short. Map050 EV019 cmds 54 and 56 are the case that surfaced this — Theo's
    two steps to the machine became one, and the resulting stagger was
    misdiagnosed for weeks as a map-geometry problem.

    Merging (rather than inserting a ``waitmovement`` between them) is what
    preserves RMXP's semantics: a wait would insert a beat the author never
    wrote, visibly stuttering every fused route in the corpus.

    Only *adjacent* routes fuse — 509 editor rows are transparent (they are the
    per-step display duplicates of the route they follow), anything else breaks
    the run. The merged node keeps the first route's index and flags so queue
    entries still point at the row a human would look at.
    """
    merged: list[Node] = []
    for node in nodes:
        if type(node) is not Leaf or node.cmd.get("code") != SET_MOVE_ROUTE:
            merged.append(node)
            continue

        params = node.cmd.get("parameters", [])
        if len(params) < 2 or not isinstance(params[1], dict):
            merged.append(node)
            continue

        # Walk back over transparent 509 rows to find the run's predecessor.
        prev_idx = len(merged) - 1
        while (
            prev_idx >= 0
            and type(merged[prev_idx]) is Leaf
            and merged[prev_idx].cmd.get("code") == MOVE_COMMAND_ROW
        ):
            prev_idx -= 1
        if prev_idx < 0:
            merged.append(node)
            continue
        prev = merged[prev_idx]
        prev_params = prev.cmd.get("parameters", [])
        if (
            type(prev) is not Leaf
            or prev.cmd.get("code") != SET_MOVE_ROUTE
            or len(prev_params) < 2
            or not isinstance(prev_params[1], dict)
            or prev_params[0] != params[0]
        ):
            merged.append(node)
            continue

        # Fuse: concatenate step lists, dropping the predecessor's terminating
        # code-0 row so the routes read as one uninterrupted motion.
        prev_steps = [s for s in prev_params[1].get("list", []) if s.get("code") != 0]
        this_steps = list(params[1].get("list", []))
        fused_route = {**prev_params[1], "list": prev_steps + this_steps}
        fused_cmd = {
            **prev.cmd,
            "parameters": [prev_params[0], fused_route, *prev_params[2:]],
        }
        merged[prev_idx] = Leaf(cmd=fused_cmd, index=prev.index)
    return merged


_SCRIPT_ROW_TRAILING_ASSIGN_RE = re.compile(r"(?<![=!<>])=\s*$")


def _script_row_leaves_expression_open(text: str) -> bool:
    """True when ``text`` (a 355/655 row, or the join of a run of them so
    far) ends mid-expression — an unbalanced bracket/paren/brace, or a bare
    trailing ``=`` (the split-assignment opener shape, e.g.
    ``$PokemonGlobal.seenStorageCreator=``). Used by
    ``_merge_script_call_rows`` to tell "RMXP wrapped this one call across
    several editor rows" apart from "the scripter wrote several complete
    statements, one per row" — both shapes reuse the same 355/655 codes, and
    only the former is safe to concatenate with no separator."""
    depth = 0
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
    if depth > 0:
        return True
    return bool(_SCRIPT_ROW_TRAILING_ASSIGN_RE.search(text))


def _merge_script_call_rows(nodes: list[Node]) -> list[Node]:
    """Fuse a run of one code-355 Script leaf plus immediately-following
    code-655 continuation leaves into a single logical node, when the
    accumulated text is still an open expression (see
    ``_script_row_leaves_expression_open``).

    RMXP's script editor wraps a single logical line at the box's character
    width, mid-token — so a call like ``pbPokemonMart([...])`` that overruns
    the box lands as a 355 row followed by several 655 rows that are each an
    exact substring of the original text, split with nothing lost or added.
    Concatenating them edge-to-edge (no separator) reconstructs the original
    source; that's what lets ``_emit_script_call`` match an idiom against the
    joined text instead of failing on each fragment independently (the
    Kevlar Town Poké Mart bug: eight ``PBItems::`` continuation rows, each
    queued on its own instead of the one native mart call they spell out
    together).

    This is deliberately NOT "join every consecutive 355/655 run" — several
    idioms (the pbStarterSelector Ruby-locals build-up, the argmax
    if/elsif/end remap chain) rely on 355/655 rows that are genuinely
    separate complete Ruby statements the scripter wrote one per line, not
    wrap fragments of one call; joining those with no separator would
    concatenate distinct statements into unparseable garbage and silently
    break the row-by-row state machines built for them. The two shapes are
    told apart by whether the text so far is still "open" mid-expression.

    Only adjacent Leaf nodes merge — a comment row or any structural node
    (IfNode/ChoiceNode/LoopNode) between two script-call rows breaks the run
    (see the ``$PokemonGlobal.seenStorageCreator=`` pending-opener machinery
    in ``_emit_script_call``, which still covers exactly that non-adjacent
    case). The merged node keeps the first row's index, so a queue entry for
    an unmatched joined call still points at the row a human would look at.
    """
    merged: list[Node] = []
    for node in nodes:
        if (
            type(node) is Leaf
            and node.cmd.get("code") == SCRIPT_CONT
            and merged
            and type(merged[-1]) is Leaf
            and merged[-1].cmd.get("code") in (SCRIPT, SCRIPT_CONT)
        ):
            prev = merged[-1]
            prev_params = prev.cmd.get("parameters", [])
            prev_text = (
                prev_params[0]
                if prev_params and isinstance(prev_params[0], str) else ""
            )
            if _script_row_leaves_expression_open(prev_text):
                params = node.cmd.get("parameters", [])
                text = params[0] if params and isinstance(params[0], str) else ""
                fused_cmd = {
                    **prev.cmd,
                    "parameters": [prev_text + text, *prev_params[1:]],
                }
                merged[-1] = Leaf(cmd=fused_cmd, index=prev.index)
                continue
        merged.append(node)
    return merged


def _is_real_warp_leaf(node: Node) -> bool:
    """True for a Transfer Player leaf that emit_node actually turns into a
    native ``warp(...)``/``waitstate`` pair (mode-0, literal x/y/map) — the
    variable-target form (mode 1) queues instead and never halts the fork's
    script, so it doesn't trigger post-warp hoist/queue handling."""
    if type(node) is not Leaf or node.cmd.get("code") != TRANSFER_PLAYER:
        return False
    params = node.cmd.get("parameters", [])
    return (
        len(params) >= 4
        and params[0] == 0
        and all(isinstance(v, int) for v in params[1:4])
    )


def _is_state_write_leaf(node: Node) -> bool:
    """True for an unconditional control-switch/variable/self-switch leaf —
    the only commands safe to hoist across a warp (CLAUDE.md §... post-warp
    dead-code rule): no player input is accepted between the write and the
    warp, and the write doesn't depend on anything the warp changes."""
    return type(node) is Leaf and node.cmd.get("code") in (
        CONTROL_SWITCHES, CONTROL_VARIABLES, CONTROL_SELF_SWITCH,
    )


def _first_dialogue_text(nodes: list[Node]) -> str | None:
    """DFS for the first Show-Text run in a branch body's node tree.

    Used by the canlose trainer-battle idiom to lift the trainer's win
    reaction line out of the RMXP lost/else block (CLAUDE.md-instructed
    VictoryText source). Recurses into nested control flow — a leading
    setflag/breadcrumb one level down shouldn't hide dialogue further in —
    and returns ``None`` if no ``TextRun`` exists anywhere in the subtree
    (caller falls back to a generic line)."""
    for n in nodes:
        if isinstance(n, TextRun):
            return n.text
        if isinstance(n, IfNode):
            found = _first_dialogue_text(n.then)
            if found is not None:
                return found
            if n.otherwise:
                found = _first_dialogue_text(n.otherwise)
                if found is not None:
                    return found
        elif isinstance(n, ChoiceNode):
            for _idx, _text, children in n.arms:
                found = _first_dialogue_text(children)
                if found is not None:
                    return found
        elif isinstance(n, LoopNode):
            found = _first_dialogue_text(n.children)
            if found is not None:
                return found
    return None


# -- condition interpreter (111 / grill D-series "the real work") --------------

_VAR_COMPARISONS = {0: "==", 1: ">=", 2: "<=", 3: ">", 4: "<", 5: "!="}


def condition_expr(params: list, ctx: TranspileContext) -> str | None:
    """A poryscript boolean expression for a 111 condition, or None → queue.

    v1 tier: switch (0), variable (1), self-switch (2). Script conditions
    (12) and character-facing (6) etc. are queue-class until the condition
    interpreter grows per-cluster (grill D8: extended on queue evidence).
    """
    if not params:
        return None
    ctype = params[0]

    if ctype == 0 and len(params) >= 3:  # switch [0, id, 0=ON/1=OFF]
        name = ctx.flag_for_switch(params[1])
        if name is None:
            return None
        return f"flag({name})" if params[2] == 0 else f"!flag({name})"

    if ctype == 1 and len(params) >= 5:  # variable [1, id, operand_kind, operand, cmp]
        name = ctx.var_for_variable(params[1])
        if name is None:
            return None
        op = _VAR_COMPARISONS.get(params[4])
        if op is None:
            return None
        if params[2] == 0:  # constant operand
            if not isinstance(params[3], int):
                return None
            rhs = str(params[3])
        else:
            # operand kind 1 (another variable) and others (random/item/actor/…):
            # poryscript's `if` condition grammar takes only a literal RHS —
            # `var(X) OP var(Y)` fails to compile (verified against the real
            # poryscript binary: "expected next token to be '{', got ')'").
            # Queue rather than emit invalid syntax.
            return None
        return f"var({name}) {op} {rhs}"

    if ctype == 2 and len(params) >= 3:  # self-switch [2, "A", 0=ON/1=OFF]
        letter = params[1]
        if not isinstance(letter, str) or ctx.event_id is None:
            return None  # a self-switch has no meaning in a common event
        name = ctx.self_switch_flag(letter)
        return f"flag({name})" if params[2] == 0 else f"!flag({name})"

    return None


_CONDITION_TYPE_NAMES = {
    0: "switch", 1: "variable", 2: "self-switch", 3: "timer", 4: "actor",
    5: "enemy", 6: "character-facing", 7: "gold", 8: "item", 9: "weapon",
    10: "armor", 11: "button-input", 12: "script",
}


def _describe_condition(params: list) -> str:
    ctype = params[0] if params else None
    name = _CONDITION_TYPE_NAMES.get(ctype, f"type {ctype}")
    detail = ""
    if ctype == 12 and len(params) > 1:
        detail = f": {str(params[1])[:120]}"
    elif ctype == 0 and len(params) > 1:
        detail = f" (switch {params[1]})"
    elif ctype == 1 and len(params) > 1:
        detail = f" (variable {params[1]})"
    return f"conditional on {name}{detail}"


# -- move routes (209) — grill D7 deterministic tier ---------------------------

# Bucket A: RMXP move-command code → poryscript movement token, unconditional.
# (Walk codes 1–4 are handled separately — their token depends on the current
# route speed, see _WALK_CODES/_SPEED_PREFIX.)
_MOVE_TOKENS: dict[int, str] = {
    # Diagonals (5–8): vanilla emerald lacks these; the EXPANSION ships them
    # (movement.inc walk_diag_*) — the moveroute census's HARD call predated
    # the fork check (§4.7). RMXP: 5 lower-left, 6 lower-right, 7 upper-left,
    # 8 upper-right.
    5: "walk_diag_southwest", 6: "walk_diag_southeast",
    7: "walk_diag_northwest", 8: "walk_diag_northeast",
    16: "face_down", 17: "face_left", 18: "face_right", 19: "face_up",
    25: "face_player", 26: "face_away_player",
    31: "restore_anim", 32: "disable_anim",
    35: "lock_facing_direction", 36: "unlock_facing_direction",
    39: "set_fixed_priority", 40: "clear_fixed_priority",
}

# SOFT-C drops (moveroute_coverage.py dispositions): timing/physics toggles
# with no per-step GBA analog whose removal doesn't change where anyone ends
# up. 30 frequency · 33/34 "step anime" on/off (RGSS's continuous-idle-
# animation flag — Game_Character#update_move switch, Interpreter.rb —
# no per-step fork toggle: `walk_in_place_*` plays a literal animation loop,
# not a persistent inanimate-while-standing flag; corpus census 2026-08-02,
# 53 routes touch 33/34) · 37/38 through on/off (Essentials door-walk
# plumbing) · 43 blend · 44 SE (audio is a visible drop elsewhere too).
_MOVE_DROP_CODES = frozenset({30, 33, 34, 37, 38, 43, 44})

# Code 41 (Change Graphic) is script-level, not a movement token — handled by
# _PageEmitter._emit_route_with_gfx_swaps, which splits the route around it.
CHANGE_GRAPHIC = 41

# RMXP facing (2 down / 4 left / 6 right / 8 up) -> the fork's facing action.
# Used by the code-41 swap, whose `direction` parameter is how RMXP props
# select a visual state on a single sheet.
_RMXP_DIRECTION_TOKENS = {2: "face_down", 4: "face_left",
                          6: "face_right", 8: "face_up"}

# Bucket B (15 = wait N frames): emit the nearest not-longer delay_* chain.
_DELAY_TOKENS = [(16, "delay_16"), (8, "delay_8"), (4, "delay_4"),
                 (2, "delay_2"), (1, "delay_1")]

# Bucket B (29 = change speed): RMXP speed sets the gait of FOLLOWING steps.
# 4 is normal; map the rest onto the fork's slow/fast/faster walk tokens.
_SPEED_PREFIX = {1: "walk_slow", 2: "walk_slow", 3: "walk_slow",
                 4: "walk", 5: "walk_fast", 6: "walk_faster"}
_WALK_CODES = {1: "down", 2: "left", 3: "right", 4: "up"}


def _delay_tokens(frames: int) -> list[str]:
    out: list[str] = []
    remaining = max(int(frames), 1)
    for size, token in _DELAY_TOKENS:
        while remaining >= size:
            out.append(token)
            remaining -= size
    return out


def _is_forward_backward_gesture(route: dict) -> bool:
    """RMXP move-codes 12 ("1 Step Forward") + 13 ("1 Step Backward"), back to
    back — a facing-relative bob with zero net displacement and unchanged
    facing (``move_backward`` pins ``@direction_fix`` for its own step,
    ``reference/scripts_dump/021_Game_Character_v17.rb:603-622``). Neither
    code has an absolute-direction fork token (all ``walk_*`` actions are
    direction-fixed, not facing-relative), so there is no way to replay the
    *displacement* faithfully — but the source's own visible effect is just a
    gesture, not a walk, and the fork's ``walk_in_place_*`` family gives a
    same-tile gesture too. Matches ONLY a route consisting of exactly these
    two non-terminator steps, in this order, no repeat (corpus census
    2026-08-02: 2 occurrences, both this shape exactly) — anything else
    containing a 12 or 13 still falls through to the per-step loop below
    (queues, since neither code has an entry there either)."""
    if route.get("repeat"):
        return False
    steps = [s.get("code", 0) for s in route.get("list", []) if s.get("code", 0) != 0]
    return steps == [12, 13]


def route_tokens(route: dict) -> list[str] | None:
    """Movement tokens for a route, or None if any step is outside the tier."""
    if route.get("repeat"):
        return None  # ambient looping route — no movement-block equivalent
    if _is_forward_backward_gesture(route):
        # walk_in_place_right, not a facing-aware token: the source route is
        # itself facing-relative and this transpiler doesn't track an event's
        # accumulated facing across a page (§10 fidelity substitution, same
        # disposition the retired Map032_EV009 hand file used for this exact
        # shape).
        return ["walk_in_place_right", "walk_in_place_right"]
    tokens: list[str] = []
    speed_prefix = "walk"
    for step in route.get("list", []):
        code = step.get("code", 0)
        if code == 0:
            break  # terminator
        if code in _MOVE_DROP_CODES:
            continue
        if code in _WALK_CODES:
            tokens.append(f"{speed_prefix}_{_WALK_CODES[code]}")
        elif code in _MOVE_TOKENS:
            tokens.append(_MOVE_TOKENS[code])
        elif code == 15:
            params = step.get("parameters", [])
            frames = params[0] if params and isinstance(params[0], int) else 1
            tokens.extend(_delay_tokens(frames))
        elif code == 29:
            params = step.get("parameters", [])
            speed = params[0] if params and isinstance(params[0], int) else 4
            prefix = _SPEED_PREFIX.get(speed)
            if prefix is None:
                return None
            speed_prefix = prefix
        elif code == 42:
            params = step.get("parameters", [])
            opacity = params[0] if params and isinstance(params[0], int) else None
            if opacity == 0:
                tokens.append("set_invisible")
            elif opacity == 255:
                tokens.append("set_visible")
            else:
                return None  # partial opacity has no binary analog
        else:
            return None
    return tokens


def _is_cave_step_forward_route(route: dict) -> bool:
    """RMXP move-code 12 ("Step Forward", relative to current facing) has no
    fork token — walk_down/up/left/right etc. are all absolute directions
    (verified against pristine HEAD: no relative-to-facing action in
    ``asm/macros/movement.inc``). Matches ONLY a route consisting of exactly
    one non-terminator step, that step code 12, no repeat — the "player
    steps off the door tile after a reverse-warp arrival" idiom (Map032
    EV23/36/37 page 2, part of the door-onEvent idiom's then-arm; corpus-wide
    35 occurrences, all target -1/player, all this exact one-step shape —
    confirmed by corpus scan, never mixed with other steps). A longer route
    that happens to contain a 12 anywhere still falls through to
    ``route_tokens`` (queues), matching the door idiom's existing disposition
    for anything outside this narrow shape."""
    if route.get("repeat"):
        return False
    steps = [s for s in route.get("list", []) if s.get("code", 0) != 0]
    return len(steps) == 1 and steps[0].get("code") == 12


def _describe_route(route: dict, target: object) -> str:
    codes = [s.get("code", 0) for s in route.get("list", []) if s.get("code", 0) != 0]
    rpt = " repeat" if route.get("repeat") else ""
    return (
        f"move route (target {target},{rpt} {len(codes)} steps, codes {codes[:12]}) "
        f"outside the deterministic tier — paired 210 waits are neutralized"
    )


# -- door-sheet self animation ("native opendoor", operator-approved 2026-10-07) --
# An RMXP door-sheet event (``is_door_sheet``) animates itself by turning through
# its four direction rows: the rows are animation frames, not facings. Row down
# is the closed door, row left the fully open one. The fork has no such object;
# the door is a metatile the engine animates natively (``opendoor`` /
# ``closedoor`` / ``setdooropen`` / ``setdoorclosed`` — engine/src/scrcmd.c
# ScrCmd_opendoor et al., all no-ops on a metatile without door behavior or door
# graphics, field_door.c FieldAnimateDoorOpen / FieldSetDoorOpened).
_DOOR_FACE_CODES = {16: "closed", 17: "open", 18: "mid", 19: "mid"}
_DOOR_INERT_CODES = frozenset({15, *_MOVE_DROP_CODES})  # delays + SOFT-C drops


def _door_route_plan(route: dict) -> tuple[str, bool] | str:
    """Classify a door sheet's self-route: ``(final_state, animated)`` where
    final_state is ``"open"``/``"closed"`` and animated means more than one
    face step (intermediate frames). Returns a reason string if the route is
    anything but face-turns + delays (never silently dropped, CLAUDE.md §4.5)."""
    if route.get("repeat"):
        return "repeating route"
    faces: list[str] = []
    for step in route.get("list", []):
        code = step.get("code", 0)
        if code == 0:
            break
        if code in _DOOR_FACE_CODES:
            faces.append(_DOOR_FACE_CODES[code])
        elif code not in _DOOR_INERT_CODES:
            return f"step code {code} is not a face-turn or delay"
    if not faces:
        return "no face-turn step to give a terminal door state"
    if faces[-1] == "mid":
        return "ends facing up/right, which is neither the open nor the closed door row"
    return faces[-1], len(faces) > 1


# -- page emitter --------------------------------------------------------------

_TONE_FADES = {
    (-255, -255, -255): "FADE_TO_BLACK",
    (0, 0, 0): "FADE_FROM_BLACK",
    (255, 255, 255): "FADE_TO_WHITE",
}


class _PageEmitter:
    """Emits body lines for one page's tree; tracks 209/210 pairing state."""

    def __init__(self, ctx: TranspileContext, page_label: str) -> None:
        self.ctx = ctx
        self.page_label = page_label
        self.movements: list[tuple[str, list[str]]] = []  # (label, tokens)
        self.text_blocks: list[tuple[str, str]] = []  # (label, formatted content)
        # Fully-rendered auxiliary blocks (e.g. a `mart { ... }` list) an
        # idiom needs to emit alongside the page's script block. Unlike
        # movements/text_blocks these are pre-rendered strings, appended
        # verbatim by the caller (see _emit_script_call's pbPokemonMart arm).
        self.aux_blocks: list[str] = []
        self._last_route_ok = False  # was the most recent 209 emitted?
        self._choice_count = 0  # running per-page \ch counter (label uniqueness)
        # Ruby locals built across 355/655 rows: name -> (source_var_id, offset,
        # wrap). Only the shapes the starter-selector idiom needs; see
        # ruby_idioms.match_local_from_var and friends.
        self._ruby_locals: dict[str, _RubyLocal] = {}
        # Set to the opener row's cmd index when a
        # "$PokemonGlobal.seenStorageCreator=" row (no value yet) was just
        # seen; consumed by the immediately following script-call row (see
        # _SEEN_STORAGE_CREATOR_OPEN_RE).
        self._pending_storage_creator_open: int | None = None
        # RMXP label name -> hoisted script block label, filled by
        # transpile_page for the one region it could prove terminates.
        # Anything not in here queues, both at the label and at every jump.
        self.label_blocks: dict[str, str] = {}
        # RMXP label names emitted as a Poryscript loop (see
        # `loop_label_region`): the label opens a `while`, each jump is a
        # `continue`. Filled by transpile_page.
        self.loop_labels: set[str] = set()
        # The page's flat command list (set by transpile_page) -- lets an
        # emitter check page-wide facts, e.g. every read of a \ch variable.
        self.page_commands: list[dict] = []
        # Uranium variable id -> the scratch vars standing in for an array
        # value it was assigned (see _emit_array_literal).
        self._array_vars: dict[int, list[str]] = {}
        # Open `if x==A` remap arm: (local name, tested value, assigned value).
        self._pending_remap: tuple[str, int, int | None] | None = None
        # Ruby local name -> the real FLAG_*/VAR_* it was materialized into
        # (see _emit_local_materialize). Lets a later list-index readback
        # sharing the same local find the var it now lives in.
        self._materialized_locals: dict[str, str] = {}
        # Plain Ruby local name -> ordered string literal it was bound to
        # (see ruby_idioms.match_string_list).
        self._string_lists: dict[str, list[str]] = {}
        # Uranium variable id -> (real var it would have held the indexed
        # string, the ordered values) for a \v[N] text substitution
        # (see ruby_idioms.match_var_from_list_index / _emit_value_var_text).
        self._value_text_choices: dict[int, tuple[str, list[str]]] = {}
        # Party-pick family state (see _PICK_PLAIN_RE): RMXP var holding the
        # chosen party index / the mon's name / the nickname just entered.
        self._pick_chosen: int | None = None
        self._pick_name: int | None = None
        self._pick_new_name: int | None = None
        # (spec, chosen var) while the then-arm of a PickTrade is emitting, so
        # the pbStartTrade row inside it resolves; _trade_consumed records that
        # it did.
        self._active_trade: tuple["_trades.InGameTradeSpec", int] | None = None
        self._trade_consumed = False

    def _emit_loop(self, nodes: list[Node], split: int) -> list[str]:
        """``nodes[split]`` is a loop label: what precedes it emits normally,
        everything after it (the rest of the label's enclosing block -- the
        region `loop_label_region` proved) becomes a ``while`` body whose
        every ``119`` is a ``continue`` and which ``break``s at the end.
        Queues (region dropped) if a ``continue`` ended up inside an emitted
        ``switch``: verified against the real compiler, poryscript rejects it
        ("'continue' must be the last statement in block scope")."""
        label_cmd = nodes[split]
        lines = self.emit_nodes(nodes[:split])
        body = self.emit_nodes(nodes[split + 1:])
        stripped = [ln.strip() for ln in body]
        if "continue" in stripped and any(ln.startswith("switch (") for ln in stripped):
            return lines + [self.ctx.queue(
                label_cmd.index, LABEL,
                "RMXP loop label: a jump back sits inside an emitted switch, "
                "where poryscript rejects `continue` — loop not emitted",
            )]
        return [
            *lines,
            f"while ({_LOOP_ALWAYS_TRUE}) {{",
            *[f"    {ln}" for ln in body],
            "    break",
            "}",
        ]

    # -- leaf emitters -------------------------------------------------------

    def emit_nodes(self, nodes: list[Node]) -> list[str]:
        if self.loop_labels:
            split = next((
                k for k, n in enumerate(nodes)
                if type(n) is Leaf and n.cmd.get("code") == LABEL
                and str((n.cmd.get("parameters") or [""])[0]) in self.loop_labels
            ), None)
            if split is not None:
                return self._emit_loop(nodes, split)
        nodes = _merge_consecutive_routes(nodes)
        nodes = _merge_script_call_rows(nodes)
        nodes = self._collapse_starter_rival_battles(nodes)
        nodes = self._collapse_pick_groups(nodes)
        warp_pos = next(
            (i for i, node in enumerate(nodes) if _is_real_warp_leaf(node)), None
        )
        if warp_pos is None:
            lines: list[str] = []
            for node in nodes:
                lines.extend(self.emit_node(node))
            return lines

        # RMXP keeps running an event's command list after a Transfer Player;
        # pokeemerald's `warp` halts the script (ScrCmd_warp returns TRUE,
        # DoWarp tears down the context on map change). Everything the RMXP
        # page put after the transfer is therefore dead code on the fork —
        # except unconditional state writes at this same nesting level,
        # which are unobservable to reorder across the warp (no input is
        # accepted between the two, and the write doesn't depend on
        # anything the warp changes), so those get hoisted above it instead
        # of silently dropped.
        lines = []
        for node in nodes[:warp_pos]:
            lines.extend(self.emit_node(node))

        hoisted: list[str] = []
        tail: list[str] = []
        for node in nodes[warp_pos + 1:]:
            if _is_state_write_leaf(node):
                hoisted.extend(self.emit_node(node))
            else:
                tail.append(self.ctx.queue(
                    node.index, node.cmd.get("code", 0),
                    "command follows a Transfer Player warp: pokeemerald "
                    "halts the script at the warp (ScrCmd_warp/DoWarp), "
                    "unlike RMXP which keeps running the page — unreachable",
                ))

        if hoisted:
            lines.append(
                "# hoisted above the warp: RMXP continues after a transfer, "
                "pokeemerald does not"
            )
            lines.extend(hoisted)
        lines.extend(self.emit_node(nodes[warp_pos]))
        lines.extend(tail)
        return lines

    def emit_node(self, node: Node) -> list[str]:
        ctx = self.ctx
        cmd = node.cmd
        code = cmd.get("code", 0)
        params = cmd.get("parameters", [])

        if isinstance(node, TextRun):
            if has_inline_choice(node.text):
                return self._emit_inline_choice(node)
            named_text = self._emit_pick_name_text(node)
            if named_text is not None:
                return named_text
            value_text = self._emit_value_var_text(node.text)
            if value_text is not None:
                return value_text
            text_source = _COLOUR_TEXT_CODE_RE.sub("", _BLUE_TEXT_CODE_RE.sub("", node.text))
            result = translate_text_codes(text_source.strip())
            if result is None:
                return [ctx.queue(
                    node.index, SHOW_TEXT,
                    f"dialogue with untranslated control code: {node.text[:120]!r}",
                )]
            text = format_pory_dialogue(result.text)
            if result.autoclose:
                # MSGBOX_AUTOCLOSE (engine/asm/macros/event.inc:2094) — a trailing
                # \wtnp[n] closes the box itself; no player input needed.
                return [f"msgbox({text}, MSGBOX_AUTOCLOSE)"]
            if result.sign:
                # Gate-validated sign idiom (deterministic._sign_block /
                # classify_sign_dialogue): lock/msgbox/release, deliberately no
                # faceplayer and NOT MSGBOX_SIGN.
                return ["lock", f"msgbox({text})", "release"]
            return [f"msgbox({text})"]

        if isinstance(node, StarterRivalBattle):
            return self._emit_starter_rival_battle(node)
        if isinstance(node, PickTrade):
            return self._emit_pick_trade(node)
        if isinstance(node, NameEntry):
            return self._emit_name_entry(node)
        if isinstance(node, NameApply):
            return self._emit_name_apply(node)
        if isinstance(node, IfNode):
            return self._emit_if(node)
        if isinstance(node, ChoiceNode):
            return self._emit_choice(node)
        if isinstance(node, LoopNode):
            align = self._align_loop_lines(node)
            if align is not None:
                return align
            return [ctx.queue(
                node.index, LOOP,
                f"RMXP loop with {len(node.children)} children — no v1 mapping "
                f"(poryscript while needs a condition); subtree not emitted",
            )]

        # -- plain leaves ------------------------------------------------
        if code in _STRIP_CODES:
            return []
        if code == WAIT:
            frames = params[0] if params and isinstance(params[0], int) else 1
            return [f"delay({frames})"]
        if code in (LABEL, JUMP_TO_LABEL):
            # Both sides of RMXP's intra-page goto compile to the same `goto`:
            # the label is where fall-through enters the hoisted block, the
            # jump is where a branch enters it.
            name = str(params[0]) if params else ""
            if code == JUMP_TO_LABEL and name in self.loop_labels:
                return ["continue"]
            block = self.label_blocks.get(name)
            if block is None:
                return [ctx.queue(
                    node.index, code,
                    f"RMXP label {name!r} was not hoistable — its region falls "
                    f"back into an enclosing branch/choice arm, or the page has "
                    f"more than one label (see hoistable_label_region)",
                )]
            return [f"goto({block})"]
        if code == EXIT_EVENT:
            # In a called common event, exiting means returning to the caller;
            # `end` there would kill the whole script context.
            if ctx.common_event_id is not None:
                return ["return"]
            # Leave the script early, but release first: the page's closing
            # release/releaseall (added by transpile_event) is skipped by `end`,
            # which froze the player on every early exit (Map046 EV002).
            return [*([ctx.exit_epilogue] if ctx.exit_epilogue else []), "end"]
        if code == ERASE_EVENT:
            if ctx.event_id is None:
                return [ctx.queue(node.index, code, "erase event in a common event")]
            return [f"removeobject({ctx.event_id})"]
        if code == CALL_COMMON_EVENT:
            ce_id = params[0] if params else 0
            if not isinstance(ce_id, int) or ce_id <= 0:
                return [ctx.queue(node.index, code, "call common event with bad id")]
            # `call(Label)`, never bare `call Label` — poryscript has no bare
            # call keyword and would emit two broken lines. See the identical
            # note in deterministic.py's CALL_COMMON_EVENT branch.
            return [f"call(CommonEvent_{ce_id:03d})"]
        if code == CONTROL_SWITCHES:
            return self._emit_control_switches(node)
        if code == CONTROL_VARIABLES:
            return self._emit_control_variables(node)
        if code == CONTROL_SELF_SWITCH:
            if not params or not isinstance(params[0], str):
                return [ctx.queue(node.index, code, "self-switch with bad params")]
            if ctx.event_id is None:
                return [ctx.queue(node.index, code, "self-switch in a common event")]
            name = ctx.self_switch_flag(params[0])
            value = params[1] if len(params) > 1 else 0
            return [f"setflag({name})" if value == 0 else f"clearflag({name})"]
        if code == TRANSFER_PLAYER:
            # [mode, map_id, x, y, direction, fade]; mode 1 = variable target.
            if len(params) < 4 or params[0] != 0 \
                    or not all(isinstance(v, int) for v in params[1:4]):
                return [ctx.queue(node.index, code, "variable-target player transfer")]
            direction = params[4] if len(params) > 4 else None
            lines = warp_lines(params[1], params[2], params[3], direction)
            if lines is None:
                return [ctx.queue(
                    node.index, code, f"player transfer with unknown direction {direction!r}",
                )]
            return lines
        if code == SET_EVENT_LOCATION:
            return self._emit_set_event_location(node)
        if code == CHANGE_MAP_SETTINGS:
            return self._emit_change_map_settings(node)
        if code == SHOW_ANIMATION:
            return self._emit_show_animation(node)
        if code == CHANGE_PLAYER_TRANSPARENCY:
            return self._emit_player_transparency(node)
        if code == SET_MOVE_ROUTE:
            return self._emit_move_route(node)
        if code == WAIT_MOVE_COMPLETION:
            if self._last_route_ok:
                return ["waitmovement(0)"]
            return []  # neutralized — its 209 was queued/stubbed (grill D7)
        if code == CHANGE_TONE:
            return self._emit_tone(node)
        if code == PREPARE_TRANSITION:
            # RMXP freezes the screen for the coming transition; the standard
            # Essentials use is a door/scene fade — map the pair to fadescreen.
            return ["fadescreen(FADE_TO_BLACK)"]
        if code == EXECUTE_TRANSITION:
            return ["fadescreen(FADE_FROM_BLACK)"]
        if code == FADEOUT_BGM:
            return ["fadedefaultbgm"]
        if code == RECOVER_ALL:
            return ["special(HealPlayerParty)"]
        if code in (PLAY_SE, PLAY_ME, PLAY_BGM):
            # No Uranium→MUS_*/SE_* mapping yet; audio is cosmetic — visible
            # drop, not queue spam (validated disposition for dialogue SE).
            name = ""
            if params and isinstance(params[0], dict):
                name = str(params[0].get("name", ""))
            return [f"# audio (code {code}): {name}"] if name else []
        if code in (SCRIPT, SCRIPT_CONT):
            return self._emit_script_call(node)

        return [ctx.queue(
            node.index, code,
            f"command {code} outside the v1 deterministic tier",
        )]

    def _emit_set_event_location(self, node: Node) -> list[str]:
        """RMXP code 202 ("Set Event Location") -> ``setobjectxy``.

        RMXP layout: ``[event_id, designation_type, arg1, arg2, arg3]``.
        ``designation_type`` 0 = direct designation (``arg1=x, arg2=y,
        arg3=direction``); only that shape is handled here. 1 (designate with
        variables) and 2 (exchange with another event) have no established
        indirection story in this transpiler and always queue — corpus census
        2026-09-12 (``output/uranium-build/maps/*.json``) found 195 total
        code-202 occurrences: 161 direct (type 0), 34 variable (type 1), 0
        exchange (type 2) — so type 2 queues on principle, not on an observed
        shape.

        ``event_id`` 0 is RMXP's "this event" convention (verified against
        the corpus: 35 of the 195 occurrences use id 0, always inside a
        non-common event's own page); it resolves to ``ctx.event_id``, the
        transpiler's existing notion of "the event currently being
        transpiled" (same pattern as ``ERASE_EVENT`` above). A literal
        nonzero id is emitted as-is — RMXP event id, not yet a compiled local
        id — and left for ``tileset_converter.local_id_remap`` to rewrite
        post-transpile (``REMAP_COMMANDS`` there already lists
        ``"setobjectxy"`` for exactly this reason; its regex matches
        ``setobjectxy(<int>`` on the first argument, which is exactly the
        form emitted below).

        ``setobjectxy`` (not ``setobjectxyperm``) is the right analog: RMXP's
        "Set Event Location" repositions the event's *live* on-map instance,
        the same thing ``setobjectxy`` does (`engine/asm/macros/event.inc`
        ~702-707); ``setobjectxyperm`` instead rewrites the object's
        off-screen *template* position (~878-885), a different, narrower
        RMXP behavior this command was never observed to need.

        ``setobjectxy`` only moves the object; it does not turn it, so a
        nonzero ``arg3`` (direction) also needs a ``turnobject`` call
        (`engine/asm/macros/event.inc:757`, ``.macro turnobject localId:req,
        direction:req`` — same local-id shape, also in ``REMAP_COMMANDS``).
        Direction 0 means "keep current facing" and emits nothing extra.
        Nonzero values are resolved through ``_RMXP_DIRECTION_TO_DIR_CONST``
        (the same RMXP-2/4/6/8 -> ``DIR_SOUTH``/``DIR_WEST``/``DIR_EAST``/
        ``DIR_NORTH`` table ``_emit_player_facing_idiom`` already uses, reused
        rather than re-minted per CLAUDE.md §4.3); an out-of-range direction
        queues instead of guessing.
        """
        ctx = self.ctx
        params = node.cmd.get("parameters", [])
        if len(params) < 5 or not all(isinstance(v, int) for v in params[:5]):
            return [ctx.queue(node.index, SET_EVENT_LOCATION, "malformed 202 params")]

        event_id, designation_type, arg1, arg2, arg3 = params[:5]

        if designation_type == 1:
            return [ctx.queue(
                node.index, SET_EVENT_LOCATION,
                "variable-target set event location (designation_type 1)",
            )]
        if designation_type == 2:
            return [ctx.queue(
                node.index, SET_EVENT_LOCATION,
                "exchange-with-event set event location (designation_type 2)",
            )]
        if designation_type != 0:
            return [ctx.queue(
                node.index, SET_EVENT_LOCATION,
                f"set event location with unknown designation_type {designation_type}",
            )]

        if event_id == 0:
            if ctx.event_id is None:
                return [ctx.queue(
                    node.index, SET_EVENT_LOCATION,
                    "self-targeted set event location in a common event",
                )]
            target_id = ctx.event_id
        else:
            target_id = event_id

        lines = [f"setobjectxy({target_id}, {arg1}, {arg2})"]

        direction = arg3
        if direction != 0:
            dir_const = _RMXP_DIRECTION_TO_DIR_CONST.get(direction)
            if dir_const is None:
                return [ctx.queue(
                    node.index, SET_EVENT_LOCATION,
                    f"set event location with unhandled direction {direction}",
                )]
            lines.append(f"turnobject({target_id}, {dir_const})")

        return lines

    # -- structured emitters -------------------------------------------------

    def _emit_if(self, node: IfNode) -> list[str]:
        door = self._emit_door_idiom(node)
        if door is not None:
            return door
        position = self._emit_player_position_idiom(node)
        if position is not None:
            return position
        facing = self._emit_player_facing_idiom(node)
        if facing is not None:
            return facing
        give_item = self._emit_give_item_idiom(node)
        if give_item is not None:
            return give_item
        bag_quantity = self._emit_bag_quantity_idiom(node)
        if bag_quantity is not None:
            return bag_quantity
        guard = self._emit_unsatisfiable_numeric_guard(node)
        if guard is not None:
            return guard
        nuzlocke_mode = self._emit_nuzlocke_mode_strip(node)
        if nuzlocke_mode is not None:
            return nuzlocke_mode
        mystery_gift = self._emit_mystery_gift_id_strip(node)
        if mystery_gift is not None:
            return mystery_gift
        rock_smash_softlocked = self._emit_rock_smash_softlocked_strip(node)
        if rock_smash_softlocked is not None:
            return rock_smash_softlocked
        custom_game = self._emit_custom_game_strip(node)
        if custom_game is not None:
            return custom_game
        rock_smash = self._emit_rock_smash_idiom(node)
        if rock_smash is not None:
            return rock_smash
        has_species = self._emit_has_species_idiom(node)
        if has_species is not None:
            return has_species
        move_tutor = self._emit_move_tutor_choose_idiom(node)
        if move_tutor is not None:
            return move_tutor
        for pick_idiom in (
            self._emit_pick_cancel_idiom,
            self._emit_pick_egg_idiom,
            self._emit_pick_foreign_idiom,
            self._emit_pick_name_changed_idiom,
        ):
            pick = pick_idiom(node)
            if pick is not None:
                return pick
        canlose_battle = self._emit_canlose_trainer_battle_idiom(node)
        if canlose_battle is not None:
            return canlose_battle
        facility_battle = self._emit_facility_trainer_battle_idiom(node)
        if facility_battle is not None:
            return facility_battle
        randomizer = self._emit_randomizer_branch(node)
        if randomizer is not None:
            return randomizer
        pokerus = self._emit_pokerus_branch(node)
        if pokerus is not None:
            return pokerus
        party_len = self._emit_party_length_idiom(node)
        if party_len is not None:
            return party_len
        expr = condition_expr(node.cmd.get("parameters", []), self.ctx)
        if expr is None:
            marker = self.ctx.queue(
                node.index, CONDITIONAL_BRANCH,
                _describe_condition(node.cmd.get("parameters", []))
                + f" — branch ({len(node.then)} then / "
                  f"{len(node.otherwise or [])} else nodes) not emitted",
            )
            return [marker]
        lines = [f"if ({expr}) {{"]
        lines += [f"    {ln}" for ln in self.emit_nodes(node.then)]
        if node.otherwise is not None:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(node.otherwise)]
        lines.append("}")
        return lines

    # -- party-pick family: NPC trade + Name Rater ----------------------------

    def _script_rows(self) -> list[tuple[int, str]]:
        """The page's logical script rows -- 355/655 runs fused exactly as
        ``emit_nodes`` fuses them, plus every code-111 script condition --
        as ``(flat index, text)``."""
        leaves: list[Node] = [Leaf(cmd=c, index=i) for i, c in enumerate(self.page_commands)]
        rows: list[tuple[int, str]] = []
        for leaf in _merge_script_call_rows(leaves):
            text = _script_call_text(leaf.cmd) or _script_condition_text(leaf.cmd)
            if text is not None:
                rows.append((leaf.index, text))
        return rows

    def _pick_refs_clean(self, chosen: int, name: int, *, trade: bool) -> bool:
        """True iff every read of the pick's RMXP variables on this page is one
        of the shapes the party-pick idioms translate. Anything else (a stray
        ``pbGet(1)``, ``\\v[1]``, ``var1 > 3``, a Control Variables write) would
        read a variable the native flow never fills, so the whole family
        queues instead (CLAUDE.md §4.5)."""
        rows = self._script_rows()
        known = {chosen, name}
        for _, text in rows:
            entry = _PICK_TEXTENTRY_ROW_RE.match(text)
            if entry:
                known.add(int(entry.group(1)))
        new_vars = known - {chosen, name}
        ref_re = re.compile(
            r"pbGet\(\s*(\d+)\s*\)|\$game_variables\[\s*(\d+)\s*\]|pbGetPokemon\(\s*(\d+)\s*\)"
        )

        def row_allowed(text: str) -> bool:
            for rx in (_PICK_EGG_COND_RE, _PICK_FOREIGN_COND_RE, _PICK_PARTY_ROW_RE):
                m = rx.match(text)
                if m:
                    return int(m.group(1)) == chosen
            m = _PICK_RENAME_ROW_RE.match(text)
            if m:
                return int(m.group(1)) in new_vars
            m = _PICK_NAME_CHANGED_COND_RE.match(text)
            if m:
                return int(m.group(1)) in new_vars and int(m.group(2)) == name
            m = _trades._TRADE_RE.search(text.strip())
            if m:
                return trade and int(m.group(1)) == chosen
            return False

        for _, text in rows:
            refs = {int(g) for m in ref_re.finditer(text) for g in m.groups() if g}
            if refs & known and not row_allowed(text):
                return False
        for cmd in self.page_commands:
            code, params = cmd.get("code"), cmd.get("parameters", [])
            if code == CONDITIONAL_BRANCH and params and params[0] == 1 and len(params) >= 5:
                if params[2] == 1 and params[3] in known:
                    return False
                if params[1] in known and not (
                    params[1] == chosen and params[2] == 0
                    and (params[4], params[3]) in _PICK_CHOSEN_CMPS | _PICK_CANCEL_CMPS
                ):
                    return False
            elif code == CONTROL_VARIABLES and len(params) >= 5:
                if any(params[0] <= x <= params[1] for x in known):
                    return False
                if params[3] == 1 and params[4] in known:
                    return False
            elif code in (SHOW_TEXT, SHOW_TEXT_CONT) and params and isinstance(params[0], str):
                for m in _VALUE_VAR_RE.finditer(params[0]):
                    x = int(m.group(1))
                    if x == chosen or (trade and x in known):
                        return False
        return True

    @staticmethod
    def _pick_cmp(node: Node) -> tuple[int, int, str] | None:
        """``(variable, op, "chosen"|"cancel")`` of a code-111 variable-vs-
        constant test shaped like a pick result (``var != -1`` / ``>= 0`` /
        ``> -1`` = chosen, ``< 0`` / ``== -1`` / ``<= -1`` = cancel), else
        ``None``. Comparing the u16 VAR_* against -1 is never emitted; the
        idioms test PARTY_NOTHING_CHOSEN instead."""
        params = node.cmd.get("parameters", [])
        if node.cmd.get("code") != CONDITIONAL_BRANCH or len(params) < 5 or params[0] != 1:
            return None
        if params[2] != 0 or not all(isinstance(v, int) for v in params[1:5]):
            return None
        key = (params[4], params[3])
        if key in _PICK_CHOSEN_CMPS:
            return params[1], params[4], "chosen"
        if key in _PICK_CANCEL_CMPS:
            return params[1], params[4], "cancel"
        return None

    def _collapse_pick_groups(self, nodes: list[Node]) -> list[Node]:
        """Replace the exact multi-row shapes of the party-pick family with one
        synthetic node each (a node claims its successors): the proc-filtered
        ``pbChoosePokemon`` + its "was chosen" test, the three-row
        nickname-entry group, and the two-row apply-name group. Anything that
        doesn't match exactly is left for the generic path to queue."""

        def leaf_text(i: int, code: int | None = None) -> str | None:
            if i >= len(nodes) or type(nodes[i]) is not Leaf:
                return None
            if code is not None and nodes[i].cmd.get("code") != code:
                return None
            return _script_call_text(nodes[i].cmd)

        out: list[Node] = []
        i = 0
        while i < len(nodes):
            text = leaf_text(i)
            m = _PICK_PROC_RE.match(text) if text is not None else None
            if m and i + 1 < len(nodes) and type(nodes[i + 1]) is IfNode:
                cmp = self._pick_cmp(nodes[i + 1])
                chosen, name = int(m.group(1)), int(m.group(2))
                if (
                    cmp is not None and cmp[0] == chosen and cmp[2] == "chosen"
                    and self._pick_refs_clean(chosen, name, trade=True)
                ):
                    out.append(PickTrade(
                        cmd=nodes[i + 1].cmd, index=nodes[i].index, cond=nodes[i + 1],
                        chosen_var=chosen, requested=m.group(4),
                    ))
                    i += 2
                    continue
            party = _PICK_PARTY_ROW_RE.match(text) if text is not None and \
                leaf_text(i, SCRIPT) is not None else None
            if party:
                chosen = int(party.group(1))
                t2, t3 = leaf_text(i + 1), leaf_text(i + 2)
                entry = _PICK_TEXTENTRY_ROW_RE.match(t3) if t3 is not None else None
                if t2 is not None and _PICK_SPECIES_ROW_RE.match(t2) and entry:
                    out.append(NameEntry(
                        cmd=nodes[i].cmd, index=nodes[i].index,
                        chosen_var=chosen, new_name_var=int(entry.group(1)),
                    ))
                    i += 3
                    continue
                rename = _PICK_RENAME_ROW_RE.match(t2) if t2 is not None else None
                if rename:
                    out.append(NameApply(
                        cmd=nodes[i].cmd, index=nodes[i].index,
                        chosen_var=chosen, new_name_var=int(rename.group(1)),
                    ))
                    i += 2
                    continue
            out.append(nodes[i])
            i += 1
        return out

    def _emit_pick_statement(self, text: str) -> list[str] | None:
        """``pbChoosePokemon(v, n)`` (no proc) and, inside a PickTrade's
        then-arm, ``pbStartTrade(pbGet(v), PBSpecies::Y, "nick", "ot")``."""
        m = _PICK_PLAIN_RE.match(text)
        if m:
            chosen, name = int(m.group(1)), int(m.group(2))
            if self._pick_chosen is not None or not self._pick_refs_clean(
                    chosen, name, trade=False):
                return None
            self._pick_chosen, self._pick_name = chosen, name
            return ["special(ChoosePartyMon)", "waitstate"]
        if self._active_trade is not None:
            m = _trades._TRADE_RE.search(text.strip())
            if m:
                spec, chosen = self._active_trade
                if int(m.group(1)) != chosen:
                    return None
                given = self.ctx.staged_species_constant(m.group(2))
                got = (given, m.group(3), m.group(4), int(m.group(5) or 0))
                want = (spec.species, spec.nickname, spec.ot_name, spec.ot_gender)
                if got != want:
                    raise ValueError(
                        f"in-game trade drift on {spec.const}: pbStartTrade call gives "
                        f"(species, nickname, OT, OT gender)={got} but the staged "
                        f"sIngameTrades row (ingame_trades.py) has {want}"
                    )
                self._trade_consumed = True
                return [
                    "special(CreateInGameTradePokemon)",
                    "special(DoInGameTradeScene)",
                    "waitstate",
                ]
        return None

    def _emit_pick_trade(self, node: PickTrade) -> list[str]:
        """Map046 EV014's NPC trade, natively: the fork's ``ingame_trade`` macro
        (engine/asm/macros/event.inc:2684) minus its own prompts -- the RMXP
        event supplies the dialogue.

        ``chooseboxmon SELECT_PC_MON_TRADE`` (party AND PC, chooseboxmon.c:47)
        only *greys* non-matching mons (non-strict, chooseboxmon.c:44-52), so the
        species is re-checked with ``GetTradeSpecies`` -- which reads the mon via
        the same ``GetSelectedBoxMonFromPcOrParty`` as ``CreateInGameTradePokemon``
        (trade.c:4563/4630) and must not run on PARTY_NOTHING_CHOSEN (it would
        index gPlayerParty[0xFF]). The "mon chosen AND right species" result is
        folded into VAR_RESULT so the RMXP then/else arms are each emitted once.
        The species is compared against the constant the call site names, which
        the sIngameTrades row's ``requestedSpecies`` is asserted equal to."""
        ctx = self.ctx
        cond = node.cond
        assert cond is not None
        if ctx.event_id is None or ctx.common_event_id is not None:
            return [ctx.queue(node.index, SCRIPT,
                              "NPC trade outside a map event: no trade row to bind")]
        const = _trades.trade_const(ctx.map_id, ctx.event_id)
        spec = ctx.ingame_trades.get(const)
        if spec is None or spec.page != ctx.page_no:
            return [ctx.queue(
                node.index, SCRIPT,
                f"NPC trade (pbChoosePokemon proc + pbStartTrade): no staged "
                f"in-game trade row {const} for this page — cannot verify the call "
                f"against sIngameTrades, not emitting",
            )]
        requested = ctx.staged_species_constant(node.requested)
        if requested != spec.requested_species:
            raise ValueError(
                f"in-game trade drift on {const}: the proc filter requests "
                f"{node.requested} -> {requested} but the staged sIngameTrades row "
                f"requests {spec.requested_species}"
            )
        self._active_trade, self._trade_consumed = (spec, node.chosen_var), False
        try:
            then = self.emit_nodes(cond.then)
        finally:
            self._active_trade = None
        if not self._trade_consumed:
            then.append(ctx.queue(
                node.index, SCRIPT,
                f"NPC trade {const}: no pbStartTrade call inside the chosen-mon arm",
            ))
        lines = [
            f"setvar(VAR_0x8005, {const})",
            "specialvar(VAR_0x8009, GetInGameTradeSpeciesInfo)",
            "chooseboxmon(SELECT_PC_MON_TRADE)",
            "waitstate",
            "setvar(VAR_RESULT, FALSE)",
            "if (var(VAR_0x8004) != PARTY_NOTHING_CHOSEN) {",
            "    specialvar(VAR_0x800B, GetTradeSpecies)",
            f"    if (var(VAR_0x800B) == {requested}) {{",
            "        setvar(VAR_RESULT, TRUE)",
            "    }",
            "}",
            "if (var(VAR_RESULT) == TRUE) {",
            *[f"    {ln}" for ln in then],
        ]
        if cond.otherwise:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(cond.otherwise)]
        lines.append("}")
        return lines

    def _emit_name_entry(self, node: NameEntry) -> list[str]:
        """``pbTextEntry`` nickname prompt -> the fork's own rename script
        (event_scripts.s:1334: fadescreen + ``special ChangePokemonNickname``,
        which also stashes the old name in STR_VAR_3 for
        TryPutNameRaterShowOnTheAir)."""
        if self._pick_chosen != node.chosen_var:
            return [self.ctx.queue(
                node.index, SCRIPT,
                "nickname entry on a mon not chosen by a recognised pbChoosePokemon(v, n)",
            )]
        self._pick_new_name = node.new_name_var
        return ["call(Common_EventScript_NameReceivedPartyMon)"]

    def _emit_name_apply(self, node: NameApply) -> list[str]:
        if self._pick_chosen != node.chosen_var or self._pick_new_name != node.new_name_var:
            return [self.ctx.queue(
                node.index, SCRIPT,
                "pkmn.name= apply on a variable that is not the recorded new-name entry",
            )]
        return []  # the native rename already applied the entered name

    def _pick_branch(self, head: list[str], cond: str, node: IfNode,
                     invert: bool = False) -> list[str]:
        then, otherwise = (node.otherwise or [], node.then) if invert else (node.then, node.otherwise)
        lines = [*head, f"if ({cond}) {{"]
        lines += [f"    {ln}" for ln in self.emit_nodes(then)]
        if otherwise:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(otherwise)]
        lines.append("}")
        return lines

    def _emit_pick_cancel_idiom(self, node: IfNode) -> list[str] | None:
        """The pick's result test -> ``VAR_0x8004 == PARTY_NOTHING_CHOSEN``
        (party_menu.c:7929 writes it on cancel)."""
        cmp = self._pick_cmp(node)
        if cmp is None or self._pick_chosen is None or cmp[0] != self._pick_chosen:
            return None
        op = "==" if cmp[2] == "cancel" else "!="
        return self._pick_branch([], f"var(VAR_0x8004) {op} PARTY_NOTHING_CHOSEN", node)

    def _emit_pick_egg_idiom(self, node: IfNode) -> list[str] | None:
        """``pbGetPokemon(v).egg?`` -> ScriptGetPartyMonSpecies == SPECIES_EGG
        (field_specials.c:1641 returns MON_DATA_SPECIES_OR_EGG)."""
        text = _script_condition_text(node.cmd)
        m = _PICK_EGG_COND_RE.match(text) if text is not None else None
        if not m or self._pick_chosen is None or int(m.group(1)) != self._pick_chosen:
            return None
        return self._pick_branch(
            ["specialvar(VAR_RESULT, ScriptGetPartyMonSpecies)"],
            "var(VAR_RESULT) == SPECIES_EGG", node)

    def _emit_pick_foreign_idiom(self, node: IfNode) -> list[str] | None:
        """``pbGetPokemon(v).isForeign?($Trainer)`` -> vanilla's two OT checks:
        OT id differs (IsMonOTIDNotPlayers, tv.c:3295), else OT name/language
        differs (MonOTNameNotPlayer, field_specials.c:1675 -- clobbers
        STR_VAR_1, which the name text re-buffers itself)."""
        text = _script_condition_text(node.cmd)
        m = _PICK_FOREIGN_COND_RE.match(text) if text is not None else None
        if not m or self._pick_chosen is None or int(m.group(1)) != self._pick_chosen:
            return None
        return self._pick_branch(
            [
                "special(IsMonOTIDNotPlayers)",
                "if (var(VAR_RESULT) == FALSE) {",
                "    specialvar(VAR_RESULT, MonOTNameNotPlayer)",
                "}",
            ],
            "var(VAR_RESULT) == TRUE", node)

    def _emit_pick_name_changed_idiom(self, node: IfNode) -> list[str] | None:
        """"entered name empty or unchanged" -> ``TryPutNameRaterShowOnTheAir``
        (tv.c:3265): FALSE iff the nickname equals the one stashed before the
        rename; TRUE also puts the Name Rater show on the air (kept, per the
        operator ruling)."""
        text = _script_condition_text(node.cmd)
        m = _PICK_NAME_CHANGED_COND_RE.match(text) if text is not None else None
        if (
            not m or self._pick_new_name is None or self._pick_name is None
            or int(m.group(1)) != self._pick_new_name or int(m.group(2)) != self._pick_name
        ):
            return None
        return self._pick_branch(
            ["specialvar(VAR_RESULT, TryPutNameRaterShowOnTheAir)"],
            "var(VAR_RESULT) == FALSE", node)

    def _emit_pick_name_text(self, node: TextRun) -> list[str] | None:
        """Dialogue whose ``\\v[n]`` names a recorded pick-name variable ->
        ``{STR_VAR_1}`` filled by ``special(BufferMonNickname)`` immediately
        before the msgbox (tv.c:3288), so it always shows the mon's current
        nickname. Mixed or unrecorded variables fall through to the generic
        path (which queues)."""
        known = {x for x in (self._pick_name, self._pick_new_name) if x is not None}
        if not known or has_inline_choice(node.text):
            return None
        refs = [int(m.group(1)) for m in _VALUE_VAR_RE.finditer(node.text)]
        if not refs or any(r not in known for r in refs):
            return None
        raw = _VALUE_VAR_RE.sub(_STRVAR_PLACEHOLDER, node.text)
        source = _COLOUR_TEXT_CODE_RE.sub("", _BLUE_TEXT_CODE_RE.sub("", raw))
        result = translate_text_codes(source.strip())
        if result is None or result.sign:
            return None
        text = format_pory_dialogue(result.text.replace(_STRVAR_PLACEHOLDER, "{STR_VAR_1}"))
        auto = ", MSGBOX_AUTOCLOSE" if result.autoclose else ""
        return ["special(BufferMonNickname)", f"msgbox({text}{auto})"]

    def _emit_party_length_idiom(self, node: IfNode) -> list[str] | None:
        """``$Trainer.party.length <op> N`` — zero / non-zero party test.

        Fork ``getpartysize`` (engine/asm/macros/event.inc:558) writes
        ``CalculatePlayerPartyCount()`` to VAR_RESULT. The count is unsigned,
        so ``<=0``/``==0``/``<1`` mean "== 0" and ``>0``/``>=1``/``!=0`` mean
        "!= 0"; any other comparison returns ``None`` (queued, not guessed).
        """
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        m = _PARTY_LENGTH_CMP_RE.match(params[1])
        if not m:
            return None
        op, n = m.group(1), int(m.group(2))
        if (op, n) in {("<=", 0), ("==", 0), ("<", 1)}:
            cmp = "=="
        elif (op, n) in {(">", 0), (">=", 1), ("!=", 0)}:
            cmp = "!="
        else:
            return None
        lines = ["getpartysize", f"if (var(VAR_RESULT) {cmp} 0) {{"]
        lines += [f"    {ln}" for ln in self.emit_nodes(node.then)]
        if node.otherwise is not None:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(node.otherwise)]
        lines.append("}")
        return lines

    def _emit_randomizer_branch(self, node: IfNode) -> list[str] | None:
        """``if $PokemonGlobal.randomizer`` — Uranium's randomizer mode.

        A new-game option we do not implement, so the mode is statically false
        and the branch is resolved at conversion time: emit the RMXP ``else``
        block (normal play) and drop the ``then`` block. This is a *static*
        collapse, not a guess — there is no runtime path that turns the mode on
        in our ROM, so keeping the conditional would emit an unreachable arm
        plus a flag that nothing ever sets.

        Critically, the else-block is where the real work lives: on Map050 EV019
        the starter grant itself (``pbAddPokemon`` per VAR_POKEMONTEST) sits in
        the else, so queuing this conditional whole — as the generic
        script-condition path did — silently shipped a scene that hands out no
        starter at all.

        Returns ``None`` for any other script condition.
        """
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        if not _RANDOMIZER_MODE_RE.match(params[1]):
            return None
        lines = ["# randomizer mode not implemented — normal-play arm only"]
        if node.otherwise:
            lines += self.emit_nodes(node.otherwise)
        return lines

    def _emit_pokerus_branch(self, node: IfNode) -> list[str] | None:
        """``if Kernel.pbPokerus?`` — Pokerus is deferred to CH18 (Nuclear
        Plant Epsilon), so no Pokemon in this ROM is ever infected and the
        check is statically false: emit the RMXP ``else`` block (the ordinary
        "not infected" outcome) and drop the ``then`` block (Pokerus-specific
        flavor text). Same static collapse as ``_emit_randomizer_branch``.

        Critically, the else-block carries content that is NOT Pokerus-
        specific — on Map068 EV001 it's the healing counter's return-facing
        movement and closing "thank you"/"restored to full health" messages,
        present in the else arm only. Queuing the whole conditional (the
        generic script-condition path) drops that shared tail along with the
        Pokerus text, silently truncating the scene.

        Returns ``None`` for any other script condition.
        """
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        if not _POKERUS_CHECK_RE.match(params[1]):
            return None
        lines = ["# Pokerus not implemented (deferred to CH18) — "
                  "not-infected arm only"]
        if node.otherwise:
            lines += self.emit_nodes(node.otherwise)
        return lines

    def _emit_door_idiom(self, node: IfNode) -> list[str] | None:
        """``get_character(0).onEvent?`` — "player is standing on this event's
        tile" (fires on reverse-warp arrival, Map032 EV3/5/6/7/17/23/36/37 page
        2). ``VAR_TEMP_0``/``VAR_TEMP_1`` are the fork's generic scratch vars,
        emitted literally like ``VAR_RESULT`` elsewhere — not registry-minted.
        Returns ``None`` (caller falls through to the generic path, which
        queues) for any other ``get_character(...)`` form or a common event
        (no owning event = no static tile to compare against)."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        if not _DOOR_ONEVENT_RE.match(params[1]):
            return None
        ctx = self.ctx
        if (
            ctx.event_id is None
            or not isinstance(ctx.event_x, int)
            or not isinstance(ctx.event_y, int)
        ):
            return None
        lines = [
            "getplayerxy(VAR_TEMP_0, VAR_TEMP_1)",
            f"if (var(VAR_TEMP_0) == {ctx.event_x} && var(VAR_TEMP_1) == {ctx.event_y}) {{",
        ]
        lines += [f"    {ln}" for ln in self.emit_nodes(node.then)]
        if node.otherwise:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(node.otherwise)]
        lines.append("}")
        return lines

    def _emit_player_position_idiom(self, node: IfNode) -> list[str] | None:
        """``$game_player.x==N`` / ``$game_player.y<=N`` / ``$game_player.y>=N``
        — a one-shot position guard or reposition check (see
        ``_PLAYER_POSITION_CMP_RE``). ``getplayerxy`` into the transpiler's own
        scratch vars, then the same comparison over whichever axis. Returns
        ``None`` (falls through to the generic script-condition queue) for any
        other script call or comparison operator."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        m = _PLAYER_POSITION_CMP_RE.match(params[1])
        if not m:
            return None
        axis, op, value = m.group(1), m.group(2), m.group(3)
        var_name = _ALIGN_AXIS_VAR[axis]
        lines = [
            "getplayerxy(VAR_TEMP_0, VAR_TEMP_1)",
            f"if (var({var_name}) {op} {value}) {{",
        ]
        lines += [f"    {ln}" for ln in self.emit_nodes(node.then)]
        if node.otherwise:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(node.otherwise)]
        lines.append("}")
        return lines

    def _emit_player_facing_idiom(self, node: IfNode) -> list[str] | None:
        """RMXP condition kind 6 (character-facing), player-only — see
        ``_RMXP_DIRECTION_TO_DIR_CONST`` for the corpus evidence (Map031
        EV049 "NurseTut" page 1, commands 5/42, both ``[6, -1, 8]``). This is
        a COMMAND-then-branch idiom like ``_emit_has_species_idiom`` above,
        not a pure expression: the fork has no inline "am I facing N" boolean,
        only the special ``GetPlayerFacingDirection``
        (engine/data/specials.inc:309, engine/src/field_player_avatar.c:1524)
        which must be read into a variable first via ``specialvar`` before it
        can be compared. ``VAR_TEMP_0`` is the transpiler's own generic
        scratch var (same one ``_emit_player_position_idiom`` uses for
        ``getplayerxy`` — reused, not re-minted, since its lifetime never
        crosses this one branch).

        Returns ``None`` (falls through to the generic script-condition
        queue) for: any condition kind other than 6, a character id other
        than -1 (the player) — NPC local-id resolution is deliberately out of
        scope, there is no established RMXP-local-id -> fork-local-id mapping
        to guess at — or a direction value that is not one of the four
        cardinal RMXP constants (2/4/6/8)."""
        params = node.cmd.get("parameters", [])
        if len(params) < 3 or params[0] != 6:
            return None
        character_id, direction = params[1], params[2]
        if character_id != -1:
            return None  # NPC local-id mapping is out of scope — keep queueing
        dir_const = _RMXP_DIRECTION_TO_DIR_CONST.get(direction)
        if dir_const is None:
            return None
        lines = [
            "specialvar(VAR_TEMP_0, GetPlayerFacingDirection)",
            f"if (var(VAR_TEMP_0) == {dir_const}) {{",
        ]
        lines += [f"    {ln}" for ln in self.emit_nodes(node.then)]
        if node.otherwise is not None:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(node.otherwise)]
        lines.append("}")
        return lines

    def _give_item_const(self, symbol: str) -> str | None:
        """Uranium ``PBItems`` symbol -> verified fork ``ITEM_*`` constant for
        the pbReceiveItem give-item idiom (both the shape-B bare-statement
        form in ``_emit_ruby_statement`` and the shape-C type-12-condition
        form below). Resolved through ``ctx.items`` — the same Essentials-
        symbol -> ``ITEM_*`` table ``deterministic._load_item_symbols``/
        ``load_context`` builds for the mart/ground-item classifiers (reused
        via the context, not re-derived here, CLAUDE.md §4.3).

        When ``ctx.fork_item_constants`` is wired (non-empty — the driver
        always populates it for a real run from the same ForkIndex the
        conversion-time gate uses, transpile_driver.py:580), the resolved
        constant must also actually exist in the fork's headers (§4.7 forward
        check) or this returns ``None`` just like an unmapped symbol. This
        matters: ``ctx.items`` is known to name ITEM_*_BERRY constants
        (ACAI/BACU/CUPU/GUARA, and ITEM_SPRINKLOTAD) the fork does NOT
        define (confirmed absent from engine/include/constants/items.h,
        2026-08-18) — emitting them would trip the driver's post-transpile
        fork-index gate as a hard crash instead of a queue entry. An empty
        ``fork_item_constants`` means "not wired up" (unit tests that only
        set ``ctx.items``) and skips this second check, same disposition as
        every other "not wired" default on this context."""
        const = self.ctx.items.get(symbol)
        if const is None:
            return None
        if self.ctx.fork_item_constants and const not in self.ctx.fork_item_constants:
            return None
        return const

    def _emit_give_item_idiom(self, node: IfNode) -> list[str] | None:
        """``Kernel.pbReceiveItem(::PBItems::SYMBOL[, qty])`` give-item-with-
        fanfare branch (Map032 EV27/EV9, Map049 EV18, Map068 EV15). Resolved
        via ``_give_item_const`` above. Returns ``None`` (falls through to the
        generic script-condition queue) for any other script call or an
        unresolved/un-forked item symbol."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        m = _RECEIVE_ITEM_RE.match(params[1])
        if not m:
            return None
        symbol, qty = m.group(1), m.group(2)
        const = self._give_item_const(symbol)
        if const is None:
            return None  # unresolved item symbol — fall through to the queue
        give_line = f"giveitem({const}, {qty})" if qty else f"giveitem({const})"
        then_lines = self.emit_nodes(node.then)
        else_lines = self.emit_nodes(node.otherwise) if node.otherwise else []
        if not then_lines and not else_lines:
            # Both arms empty (Map049 EV18, user-approved) — no branch at all.
            return [give_line]
        lines = [give_line, "if (var(VAR_RESULT) != 0) {"]
        lines += [f"    {ln}" for ln in then_lines]
        if else_lines:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in else_lines]
        lines.append("}")
        return lines

    def _emit_bag_quantity_idiom(self, node: IfNode) -> list[str] | None:
        """``$PokemonBag.pbQuantity(PBItems::SYMBOL) <op> 0`` — a bag
        has-item/lacks-item guard (see ``_BAG_QUANTITY_CMP_RE`` for the
        corpus evidence, Map073 EV1/EV3/EV6). Fork-native ``checkitem``
        (engine/asm/macros/event.inc:588, ``SCR_OP_CHECKITEM``) is a COMMAND
        that writes ``VAR_RESULT`` to TRUE if the player has at least
        ``quantity`` (default 1) of the item, FALSE otherwise — so this emits
        a preamble ``checkitem(...)`` call plus an ``if`` over the result,
        same shape as ``_emit_has_species_idiom``'s ``checkspecies`` preamble.

        **Polarity** (get this wrong and a shop hands out free items
        forever): ``>0`` means "player HAS at least one" — the RMXP then-arm
        is the checkitem-TRUE arm. ``==0`` means "player LACKS it entirely" —
        the RMXP then-arm is the checkitem-FALSE arm. Any other operator or
        non-zero RHS is not one of the two shapes actually observed in the
        corpus and is not handled.

        The item symbol is resolved via ``_give_item_const`` (both the
        Essentials-symbol -> ``ITEM_*`` lookup and the fork-header forward
        check, CLAUDE.md §4.7) — an unresolved or un-forked symbol returns
        ``None`` here too, same disposition as ``_emit_give_item_idiom``.

        Returns ``None`` (falls through to the generic script-condition
        queue) for: any other script call/comparison shape, or an
        unresolved/un-forked item symbol."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        m = _BAG_QUANTITY_CMP_RE.match(params[1])
        if not m:
            return None
        symbol, op = m.group(1), m.group(2)
        const = self._give_item_const(symbol)
        if const is None:
            return None  # unresolved/un-forked item symbol — fall through to the queue
        result_literal = "TRUE" if op == ">" else "FALSE"
        lines = [
            f"checkitem({const})",
            f"if (var(VAR_RESULT) == {result_literal}) {{",
        ]
        lines += [f"    {ln}" for ln in self.emit_nodes(node.then)]
        if node.otherwise is not None:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(node.otherwise)]
        lines.append("}")
        return lines

    def _emit_unsatisfiable_numeric_guard(self, node: IfNode) -> list[str] | None:
        """``!pbGet(N).is_a?(Numeric) || $game_variables[M] < 0`` — Essentials'
        defensive "is this numeric and non-negative" guard (Map049 EV20 page
        1, output/uranium-build/maps/Map049.json). Both disjuncts are
        statically false on the GBA — game variables are always unsigned
        integers, so ``pbGet`` always returns a Numeric and a var is never
        negative — meaning the condition itself can never be true. User-
        approved strip (2026-07-05, slice1 hand-bucket review): drop the
        then-arm entirely and splice the else-arm's children in directly (no
        wrapping ``if`` — the branch could never have routed to the then-arm
        in the first place). Returns ``None`` (falls through to the generic
        script-condition queue, which still handles then/else counts in its
        description) for any other combinator/comparison/extra-clause shape."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        if not _UNSATISFIABLE_NUMERIC_GUARD_RE.match(params[1]):
            return None
        breadcrumb = (
            "# numeric guard: unsatisfiable on GBA — then-arm dropped "
            "(slice1, 2026-07-05)"
        )
        else_lines = self.emit_nodes(node.otherwise) if node.otherwise else []
        return [breadcrumb, *else_lines]

    def _emit_nuzlocke_mode_strip(self, node: IfNode) -> list[str] | None:
        """``$PokemonGlobal.nuzlocke==true`` — Nuzlocke mode is not ported
        (user-approved strip, 2026-08-19). Statically false on the GBA (no
        runtime path ever sets it), so exactly like
        ``_emit_unsatisfiable_numeric_guard`` above: drop the then-arm
        entirely and splice the else-arm's children in directly (no wrapping
        ``if`` — the branch could never have routed to the then-arm in the
        first place). Real occurrence: Map068 EV015 page 1 cmd 16
        (output/uranium-build/maps/Map068.json), 2 then-nodes / 0 else-nodes.
        Returns ``None`` (falls through to the generic script-condition
        queue) for any other script condition."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        if not _NUZLOCKE_MODE_GUARD_RE.match(params[1]):
            return None
        breadcrumb = (
            "# nuzlocke mode: not ported, unsatisfiable on GBA — then-arm "
            "dropped (user-approved strip, 2026-08-19)"
        )
        else_lines = self.emit_nodes(node.otherwise) if node.otherwise else []
        return [breadcrumb, *else_lines]

    def _emit_mystery_gift_id_strip(self, node: IfNode) -> list[str] | None:
        """``pbNextMysteryGiftID>0`` — the Mystery Gift subsystem is not
        ported (user-approved strip, 2026-08-19). Statically false on the GBA
        (no runtime path ever sets it), same static collapse as
        ``_emit_nuzlocke_mode_strip``/``_emit_unsatisfiable_numeric_guard``:
        drop the then-arm entirely and splice the else-arm's children in
        directly. Real occurrence: Map067 EV009 "Deliveryman" page 2 cmd 0
        (output/uranium-build/maps/Map067.json), 4 then-nodes / 1 else-node.
        Returns ``None`` (falls through to the generic script-condition
        queue) for any other script condition."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        if not _MYSTERY_GIFT_ID_GUARD_RE.match(params[1]):
            return None
        breadcrumb = (
            "# mystery gift: not ported, unsatisfiable on GBA — then-arm "
            "dropped (user-approved strip, 2026-08-19)"
        )
        else_lines = self.emit_nodes(node.otherwise) if node.otherwise else []
        return [breadcrumb, *else_lines]

    def _emit_rock_smash_softlocked_strip(self, node: IfNode) -> list[str] | None:
        """``isRockSmashSoftlocked?`` — see ``_ROCK_SMASH_SOFTLOCKED_GUARD_RE``
        for the full derivation. Reading
        ``reference/scripts_dump/221_Extra_Scripts.rb:796-812``, the
        function's first statement is
        ``return false if !$PokemonGlobal.nuzlocke || !$PokemonGlobal.randomizer``.
        Nuzlocke mode is already a statically-false, user-approved not-ported
        strip on this port (``_NUZLOCKE_MODE_GUARD_RE`` /
        ``_emit_nuzlocke_mode_strip`` above — no runtime path ever sets
        ``$PokemonGlobal.nuzlocke`` true), so ``!$PokemonGlobal.nuzlocke`` is
        always true, the ``||`` short-circuits, and ``isRockSmashSoftlocked?``
        always returns ``false`` before any of its later randomizer/badge/
        party-composition checks run. Statically FALSE on the GBA — same
        collapse as ``_emit_nuzlocke_mode_strip``/``_emit_mystery_gift_id_strip``:
        drop the then-arm entirely and splice the else-arm's children in
        directly (no wrapping ``if``). Real occurrences: Map032's Rock Smash
        event, all 3 pages (output/uranium-build/maps/Map032.json lines
        22518, 23139, 26280) — each a bare ``if isRockSmashSoftlocked?`` with
        a then-arm (softlock-rescue dialogue/heal) and no else-arm, so the
        splice is an empty list for all three. Returns ``None`` (falls
        through to the generic script-condition queue) for any other script
        condition."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        if not _ROCK_SMASH_SOFTLOCKED_GUARD_RE.match(params[1]):
            return None
        breadcrumb = (
            "# isRockSmashSoftlocked?: unsatisfiable on GBA (gated behind "
            "not-ported Nuzlocke mode) — then-arm dropped"
        )
        else_lines = self.emit_nodes(node.otherwise) if node.otherwise else []
        return [breadcrumb, *else_lines]

    def _emit_custom_game_strip(self, node: IfNode) -> list[str] | None:
        """``isCustomGame?`` — see ``_CUSTOM_GAME_GUARD_RE`` for the full
        derivation. Reading
        ``reference/scripts_dump/220_Custom_Mode.rb:244-262``, the function
        ORs together every Nuzlocke/Custom-Mode flag
        (``.nuzlocke``, ``.nuzlockehealbattle``, ``.nuzlockenomart``,
        ``.nuzlockepoisonfield``, ``.challengemode``, plus
        ``.nuzlockedupesclause``/``.nuzlockeshinyclause``/``.randomizer`` when
        called with ``any=true``) and returns true iff any is set. Custom
        Mode (this whole script, ``220_Custom_Mode.rb``) is not ported —
        same "not portable to GBA" call as Nuzlocke mode — so no runtime path
        on this port ever sets any of these flags true, meaning every
        disjunct is always false and ``isCustomGame?`` always returns false.
        Statically FALSE on the GBA, same static collapse as
        ``_emit_nuzlocke_mode_strip``: drop the then-arm, splice the
        else-arm's children in directly. Real occurrences: Map050 EV005/
        EV027 (output/uranium-build/maps/Map050.json), always the bare
        no-arg form (the ``any=false`` default). Returns ``None`` (falls
        through to the generic script-condition queue) for any other script
        condition."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        if not _CUSTOM_GAME_GUARD_RE.match(params[1]):
            return None
        breadcrumb = (
            "# isCustomGame?: Custom Mode not ported, unsatisfiable on GBA "
            "— then-arm dropped"
        )
        else_lines = self.emit_nodes(node.otherwise) if node.otherwise else []
        return [breadcrumb, *else_lines]

    def _emit_rock_smash_idiom(self, node: IfNode) -> list[str] | None:
        """``Kernel.pbRockSmash`` — see ``_ROCK_SMASH_RE`` for the fork
        evidence (field_move_scripts.inc:64 EventScript_RockSmash). The
        native script replaces the RMXP choreography end to end (break
        animation, encounter roll, self-switch hide) and never returns, so
        BOTH arms are dropped without being walked — neither is emitted, and
        nothing inside them can produce a stray queue entry. The native
        script requires the interacting object to be VAR_LAST_TALKED, which
        is true for our per-page object scripts (the page is only ever
        entered via the object's own action-button/touch trigger). Returns
        ``None`` (falls through to the generic script-condition queue) for
        any other script condition."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        if not _ROCK_SMASH_RE.match(params[1]):
            return None
        breadcrumb = (
            "# rock smash: native EventScript_RockSmash supersedes RMXP "
            "choreography (both arms dropped, slice1 2026-07-05)"
        )
        # Upstream signal for the downstream FLAG_TEMP_* respawn-flag fix
        # (porymap ships "flag": "0" on these objects — a null sentinel that
        # never latches, so the native removeobject respawns the rock on the
        # next step). This is the component that KNOWS the event is a
        # smashable rock; the driver serializes it to the trait sidecar.
        self.ctx.record_trait("smashable_rock")
        return [breadcrumb, "goto(EventScript_RockSmash)"]

    def _emit_move_tutor_choose_idiom(self, node: IfNode) -> list[str] | None:
        """``pbMoveTutorChoose(PBMoves::X)`` as a code-111 script condition --
        true iff the player picked a mon that learned the move.

        Fork analog: the ``move_tutor`` macro (engine/asm/macros/event.inc:2700)
        does ``setvar VAR_0x8005, <move>`` then ``call
        MoveTutor_EventScript_OpenBox`` (engine/data/scripts/move_tutors.inc:169:
        ``chooseboxmon SELECT_PC_MON_MOVE_TUTOR`` + ``waitstate`` + re-``lock``/
        ``faceplayer``) and branches ``goto_if_eq VAR_RESULT, FALSE, declined``
        -- so after OpenBox, VAR_RESULT is TRUE iff the move was taught.
        OpenBox (not OpenPartyMenu, which is just ``special
        ChooseMonForMoveTutor``) is the macro's own choice: it covers party AND
        PC-box mons (chooseboxmon.c:49) and is the contract the macro tests.
        The macro's own YES/NO prompt, "which mon" text and per-move taught
        flag are NOT emitted -- the RMXP event supplies its dialogue, and
        Essentials' tutor has no once-only flag.

        Returns None (generic script-condition queue) for any other shape or
        a move the id map / fork does not resolve."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        m = _MOVE_TUTOR_CHOOSE_RE.match(params[1])
        if not m:
            return None
        const = self.ctx.move_constant(m.group(1))
        if const is None:
            return None
        lines = [
            f"setvar(VAR_0x8005, {const})",
            "call(MoveTutor_EventScript_OpenBox)",
        ]
        then, otherwise = node.then, node.otherwise
        if not then and otherwise:
            cond, then, otherwise = "FALSE", otherwise, None
        else:
            cond = "TRUE"
        lines.append(f"if (var(VAR_RESULT) == {cond}) {{")
        lines += [f"    {ln}" for ln in self.emit_nodes(then)]
        if otherwise:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(otherwise)]
        lines.append("}")
        return lines

    def _emit_has_species_idiom(self, node: IfNode) -> list[str] | None:
        """``pbHasSpecies?(::PBSpecies::NAME)`` — see ``_HAS_SPECIES_RE`` for
        the corpus evidence (Map049 EV001 page 3, Auntie's farewell dialogue).
        Fork-native ``checkspecies`` (engine/asm/macros/event.inc:2541,
        ``Scrcmd_checkspecies`` -> ``CheckPartyHasSpecies``,
        engine/src/scrcmd.c:3139) is a COMMAND that writes ``VAR_RESULT``, not
        an inline boolean — so this emits a preamble ``checkspecies(...)``
        call plus an ``if`` over the result, in the same style as
        ``_emit_door_idiom``'s ``getplayerxy`` preamble (that idiom is the
        precedent for the poryscript call syntax: a fork macro is invoked
        exactly like any other command, ``name(args)``). Returns ``None``
        (falls through to the generic script-condition queue) for: any other
        type-12 script shape, a ``::PBSpecies::`` name the id map doesn't
        know, or — the important safety gate — a species the id map DOES
        know but the staging manifest never staged into the fork (e.g.
        SPECIES_URAYNE: id-mapped, one of the ~166 ``needs_engine`` species,
        but not among the six staged starters). Emitting a constant the
        fork's headers don't actually define would be exactly the class of
        bug the conversion-time gate exists to catch — queuing here is the
        correct failure mode, not a workaround."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        m = _HAS_SPECIES_RE.match(params[1])
        if not m:
            return None
        const = self.ctx.staged_species_constant(m.group(1))
        if const is None:
            return None
        lines = [
            f"checkspecies({const})",
            "if (var(VAR_RESULT) == TRUE) {",
        ]
        lines += [f"    {ln}" for ln in self.emit_nodes(node.then)]
        if node.otherwise:
            lines.append("} else {")
            lines += [f"    {ln}" for ln in self.emit_nodes(node.otherwise)]
        lines.append("}")
        return lines

    def _emit_canlose_trainer_battle_idiom(self, node: IfNode) -> list[str] | None:
        """A losable ``pbTrainerBattle(...)`` embedded as a code-111 script
        condition — see the module-level ``_CANLOSE_*`` comment and
        ``reference/guides/canlose_battle_pipeline_plan.md`` for the mechanism.
        Converts to ``trainerbattle_earlyrival`` (or a ``switch`` over one per
        runtime party-selection value) plus a ``VAR_RESULT`` win/loss branch.
        Returns ``None`` (falls through to the generic script-condition path,
        which queues) for: not a script condition, not a
        ``pbTrainerBattle(``/is a ``pbDoubleTrainerBattle``, a falsy/missing
        ``canlose`` argument, an unparseable call, an unknown trainer class/
        name/party combination in ``ctx.trainers``, or a party-id expression
        that isn't a literal int or the proven ``pbGet(N)+K`` shape.

        **Polarity** (get this wrong and every canlose battle plays the
        opposite aftermath): the engine sets ``VAR_RESULT = TRUE`` when the
        player is defeated in an EARLY_RIVAL battle (battle_setup.c), so
        ``var(VAR_RESULT) == 1`` is the player LOSING — the RMXP ``otherwise``
        (code-411/else) block. The poryscript ``else`` clause is therefore the
        RMXP ``then`` block (the player WON). Confirmed against
        ``hand_conversions/Map050_EV019.pory``, lines ~110-128.
        """
        ctx = self.ctx
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        call = params[1]
        if "pbTrainerBattle(" not in call or "pbDoubleTrainerBattle" in call:
            return None

        m_class = _CANLOSE_TRAINER_CLASS_RE.search(call)
        if not m_class:
            return None
        class_const = to_constant("TRAINER_CLASS", m_class.group(1))

        m_name = _CANLOSE_NAME_RE.search(call)
        if not m_name:
            return None
        name = m_name.group(1)

        m_defeat = _CANLOSE_DEFEAT_TEXT_RE.search(call)
        defeat_raw = m_defeat.group(1) if m_defeat else ""

        # party_id/canlose: strip the _I("...") blob first so its own commas
        # don't confuse the positional split (identical discipline to
        # deterministic.classify_trainer_battle).
        cleaned_call = _CANLOSE_STRIP_I_RE.sub("_I", call)
        m_args = _CANLOSE_CALL_ARGS_RE.search(cleaned_call)
        if not m_args:
            return None
        args = [a.strip() for a in m_args.group(1).split(",")]
        # args: [class_expr, name_str, _I, doublebattle, party_id, canlose, ...]
        if len(args) < 6:
            return None
        if args[5] not in ("true", "1"):
            return None  # not canlose — the plain single-trainer classifier's turf
        party_expr = args[4]

        # -- resolve party selection: literal int, or pbGet(N)+K -----------
        cases: list[tuple[int, str]] | None = None  # None = single-trainer path
        var_name: str | None = None
        trainer_const: str | None = None
        if party_expr.isdigit():
            party_id = int(party_expr)
            trainer_const = ctx.trainers.get((class_const, name, party_id))
            if trainer_const is None:
                return None
        else:
            m_pbget = _CANLOSE_PBGET_PLUS_RE.match(party_expr)
            if not m_pbget:
                return None  # some other expression shape — don't guess
            source_var_id, offset = int(m_pbget.group(1)), int(m_pbget.group(2))
            var_name = ctx.var_for_variable(source_var_id)
            if var_name is None:
                return None
            case_map: dict[int, str] = {}
            for (cc, nm, pid), const in ctx.trainers.items():
                if cc == class_const and nm == name and pid > offset:
                    case_map[pid - offset] = const
            if not case_map:
                return None
            cases = sorted(case_map.items())

        # -- text slots -----------------------------------------------------
        defeat_result = translate_text_codes(defeat_raw)
        if defeat_result is None:
            return None
        victory_raw = _first_dialogue_text(node.otherwise) if node.otherwise else None
        victory_text: str | None = None
        if victory_raw is not None:
            victory_result = translate_text_codes(victory_raw)
            if victory_result is not None:
                victory_text = victory_result.text
        if victory_text is None:
            # RMXP has no explicit "loss reaction" arg (plan §"Text slots"
            # decision (b)) — a generic line when the lost-block's own
            # dialogue can't be lifted cleanly (untranslatable code, or no
            # Show-Text at all in that block).
            victory_text = "Argh! I lost!"

        defeat_label = f"{self.page_label}_CanloseDefeatText"
        victory_label = f"{self.page_label}_CanloseVictoryText"
        self.text_blocks.append((defeat_label, format_pory_dialogue(defeat_result.text)))
        self.text_blocks.append((victory_label, format_pory_dialogue(victory_text)))

        battle_lines: list[str]
        if cases is None:
            battle_lines = [
                f"trainerbattle_earlyrival({trainer_const}, RIVAL_BATTLE_HEAL_AFTER, "
                f"{defeat_label}, {victory_label})"
            ]
        else:
            battle_lines = [f"switch (var({var_name})) {{"]
            for v, const in cases:
                battle_lines.append(f"    case {v}:")
                battle_lines.append(
                    f"        trainerbattle_earlyrival({const}, RIVAL_BATTLE_HEAL_AFTER, "
                    f"{defeat_label}, {victory_label})"
                )
            battle_lines.append("}")

        lost_body = self.emit_nodes(node.otherwise) if node.otherwise else []
        won_body = self.emit_nodes(node.then)
        lines = [*battle_lines, "if (var(VAR_RESULT) == 1) {"]
        lines += [f"    {ln}" for ln in lost_body]
        lines.append("} else {")
        lines += [f"    {ln}" for ln in won_body]
        lines.append("}")
        return lines

    def _collapse_starter_rival_battles(self, nodes: list[Node]) -> list[Node]:
        """Replace each exact ``[355 p=1 if sw61, 655 p=2 if sw59, 655 p=3 if
        sw60, 655 $game_variables[1]=p, IfNode(pbTrainerBattle(...,false,
        pbGet(1)))]`` run with one ``StarterRivalBattle`` node. Strict: every
        row's text and the call shape must match exactly, the class/name must
        resolve to parties 1/2/3 in ``ctx.trainers``, the three switches must
        have registry flags, variable 1 must have a registry VAR_*, and the
        ``otherwise`` must be exactly one Exit Event (the non-canlose loss arm,
        unreachable: a loss blacks out). Anything else is left untouched so the
        generic path queues it loudly."""
        out: list[Node] = []
        i = 0
        n_rows = len(_STARTER_RIVAL_ROWS) + 1
        while i < len(nodes):
            window = nodes[i:i + n_rows + 1]
            if len(window) == n_rows + 1 and self._starter_rival_match(window):
                out.append(StarterRivalBattle(
                    cmd=window[-1].cmd, index=window[0].index, cond=window[-1],
                ))
                i += n_rows + 1
                continue
            out.append(nodes[i])
            i += 1
        return out

    def _starter_rival_resolve(self, node: IfNode) -> tuple[str, str, str] | None:
        """(class_const, name, defeat_raw) when ``node`` is the exact call."""
        call = _script_condition_text(node.cmd)
        if call is None:
            return None
        m = _STARTER_RIVAL_CALL_RE.match(call)
        if not m:
            return None
        return to_constant("TRAINER_CLASS", m.group(1)), m.group(2), m.group(3)

    def _starter_rival_match(self, window: list[Node]) -> bool:
        ctx = self.ctx
        rows, cond = window[:-1], window[-1]
        for leaf, (text, _sw, _party) in zip(rows[:3], _STARTER_RIVAL_ROWS):
            if type(leaf) is not Leaf or leaf.cmd.get("code") not in (SCRIPT, SCRIPT_CONT):
                return False
            if _script_call_text(leaf.cmd) != text:
                return False
        if rows[0].cmd.get("code") != SCRIPT:
            return False
        last = rows[3]
        if type(last) is not Leaf or _script_call_text(last.cmd) != _STARTER_RIVAL_VAR_ROW:
            return False
        if type(cond) is not IfNode:
            return False
        resolved = self._starter_rival_resolve(cond)
        if resolved is None:
            return False
        class_const, name, _defeat = resolved
        if not (
            len(cond.otherwise or []) == 1
            and type(cond.otherwise[0]) is Leaf
            and cond.otherwise[0].cmd.get("code") == EXIT_EVENT
        ):
            return False
        for _text, sw, party in _STARTER_RIVAL_ROWS:
            if ctx.trainers.get((class_const, name, party)) is None:
                return False
            if ctx.flag_for_switch(sw) is None:
                return False
        return ctx.var_for_variable(_STARTER_RIVAL_VAR_ID) is not None

    def _emit_starter_rival_battle(self, node: StarterRivalBattle) -> list[str]:
        """Rival Theo's starter-dependent battle (CH06 Map040 EV079).

        RMXP computes ``p`` from the starter switches, stores it in game
        variable 1, then calls ``pbTrainerBattle(RIVAL,"Theo",...,false,
        pbGet(1))``. Emitted as an ``if / elif`` chain over the registry flags,
        one ``trainerbattle_no_intro`` per party (defeat text is shared); the
        win body is emitted once after the chain. The ``$game_variables[1]=p``
        write is KEPT (as ``setvar`` per arm): Map049 EV20 / Map172 EV1 read
        variable 1's prior value as a persistent dialogue counter, so dropping
        the write would change their behaviour.

        The ``otherwise`` arm (single Exit Event) is dropped: ``canlose`` is
        false, so a loss blacks the player out and control never returns.

        No-starter ``else`` arm: RMXP's ``p`` would be nil, ``pbGet(1)``
        would not select a party and pbTrainerBattle would raise — there is
        no RIVAL "Theo" party 0 to fall back to. Emitted as a comment only;
        nothing is invented."""
        ctx = self.ctx
        cond = node.cond
        assert cond is not None
        class_const, name, defeat_raw = self._starter_rival_resolve(cond)  # type: ignore[misc]
        var_name = ctx.var_for_variable(_STARTER_RIVAL_VAR_ID)
        defeat_result = translate_text_codes(defeat_raw)
        if defeat_result is None:
            return [ctx.queue(
                node.index, SCRIPT,
                f"starter-dependent rival battle: untranslatable defeat text {defeat_raw[:80]!r}",
            )]
        lose_label = f"{self.page_label}_StarterRivalLoseText"
        self.text_blocks.append((lose_label, format_pory_dialogue(defeat_result.text)))

        lines = [
            "# rival battle: party chosen by starter switch "
            "(RMXP p=1/2/3 -> $game_variables[1] -> pbGet(1))"
        ]
        # RMXP runs the `p=` rows in order, so the LAST true row wins: test
        # them in reverse so the if/elif chain has the same precedence.
        for k, (_text, sw, party) in enumerate(reversed(_STARTER_RIVAL_ROWS)):
            flag = ctx.flag_for_switch(sw)
            const = ctx.trainers[(class_const, name, party)]
            head = "if" if k == 0 else "} elif"
            lines += [
                f"{head} (flag({flag})) {{",
                f"    setvar({var_name}, {party})",
                f"    trainerbattle_no_intro({const}, {lose_label})",
            ]
        lines += [
            "} else {",
            "    # no starter switch set: RMXP p=nil (no RIVAL Theo party 0) — "
            "pbTrainerBattle would fail; nothing invented",
            "}",
        ]
        lines += self.emit_nodes(cond.then)
        return lines

    def _emit_facility_trainer_battle_idiom(self, node: IfNode) -> list[str] | None:
        """A repeatable, non-canlose ``pbTrainerBattle(...)`` embedded as a
        code-111 script condition inside a Yes/No offer — CH03's Mawuli
        (``Map068_EV014_Page1``: single always-active page, no self-switch
        gate, ``pbTrainerBattle(PBTrainers::RICHBOY,"Mawuli",_I("..."),
        false,0)``). Distinct from ``_emit_canlose_trainer_battle_idiom``'s
        call shape — that one is a 6+-arg
        ``[class,name,_I,doublebattle,party_id,canlose,...]`` form; this is
        the plain 5-arg ``[class,name,_I,canlose,party_id]`` form
        ``deterministic._parse_trainer_battle_call`` already models for the
        route-trainer classifier. Since ``canlose`` is false here, a loss
        blacks the player out to the last Pokémon Center exactly like
        vanilla ``trainerbattle_single`` — the RMXP ``otherwise`` (code-412)
        branch is therefore unreachable and must be empty; a non-empty one
        means this isn't the facility idiom and we bail to the generic
        queue rather than guess.

        The offer text ("Wanna fight?") and the accept line ("OK, here we
        come!") are ordinary sibling ``Show Text`` nodes emitted by the
        normal node walk before this ``IfNode`` runs — so the battle line
        uses ``trainerbattle_no_intro`` (NULL intro, ``asm/macros/
        event.inc:828``) rather than duplicating a greeting.
        ``cleartrainerflag`` follows the win so the facility stays
        repeatable — nothing here is a native sight trainer, but leaving the
        engine's own "already defeated" bookkeeping stale would be a latent
        trap for any future feature (trainer card, match call) that reads
        it.

        Returns ``None`` (falls through to the generic script-condition
        queue) for: not a script condition, not a
        ``pbTrainerBattle(``/is a ``pbDoubleTrainerBattle``, fewer than 5
        parsed args, a canlose arg that isn't ``false``/``0``, a
        non-digit party id, an unparseable class/name/defeat text, an
        unknown trainer in ``ctx.trainers``, a non-empty ``otherwise``, or a
        win-body that itself writes a self-switch.

        That last guard is load-bearing, not defensive filler: Map019 EV6
        ("Richard") wraps this exact same inner shape — 5-arg call,
        canlose=false, empty ``otherwise`` — inside an outer sw94 pre/post-
        Gym-5 branch, but its win-body sets self-switch A to flip the page to
        a permanently idle one, i.e. a one-time sight trainer, not a
        repeatable facility. Without this check the fork-index gate catches
        the mistake anyway (Richard's trainer ids aren't staged), but it
        would catch it as an unstaged-constant error instead of what it
        actually is: this idiom firing on the wrong shape.
        """
        ctx = self.ctx
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        call = params[1]
        if "pbTrainerBattle(" not in call or "pbDoubleTrainerBattle" in call:
            return None
        if node.otherwise:
            return None

        m_class = _CANLOSE_TRAINER_CLASS_RE.search(call)
        if not m_class:
            return None
        class_const = to_constant("TRAINER_CLASS", m_class.group(1))

        # A Gym Leader badge battle (``LEADER_*`` class — CH06's Maria,
        # Map042 EV003) legitimately writes self-switch A in its win-body: it
        # is a one-time gate, not a sight trainer. The battle line is the same
        # ``trainerbattle_no_intro``; only the repeatable-facility
        # ``cleartrainerflag`` is dropped, because a leader must stay beaten.
        is_leader = m_class.group(1).startswith("LEADER_")
        if not is_leader and _tree_writes_self_switch(node.then):
            return None

        m_name = _CANLOSE_NAME_RE.search(call)
        if not m_name:
            return None
        name = m_name.group(1)

        m_defeat = _CANLOSE_DEFEAT_TEXT_RE.search(call)
        defeat_raw = m_defeat.group(1) if m_defeat else ""

        cleaned_call = _CANLOSE_STRIP_I_RE.sub("_I", call)
        m_args = _CANLOSE_CALL_ARGS_RE.search(cleaned_call)
        if not m_args:
            return None
        args = [a.strip() for a in m_args.group(1).split(",")]
        # args: [class_expr, name_str, _I, canlose, party_id] — the plain
        # 5-arg form; distinct from the canlose idiom's 6+-arg layout above
        # (which also has a "false" token at index 3 -- the doublebattle
        # flag, not canlose -- so an exact-length check is required to avoid
        # misreading that shape as this one; a >= check let a 6-arg canlose
        # call with doublebattle=false alias into this idiom).
        if len(args) != 5:
            return None
        if args[3] not in ("false", "0"):
            return None  # canlose battle — the earlyrival idiom's turf
        if not args[4].isdigit():
            return None
        party_id = int(args[4])

        trainer_const = ctx.trainers.get((class_const, name, party_id))
        if trainer_const is None:
            return None

        defeat_result = translate_text_codes(defeat_raw)
        if defeat_result is None:
            return None

        lose_label = f"{self.page_label}_FacilityLoseText"
        self.text_blocks.append((lose_label, format_pory_dialogue(defeat_result.text)))

        lines = [f"trainerbattle_no_intro({trainer_const}, {lose_label})"]
        if not is_leader:
            lines.append(f"cleartrainerflag({trainer_const})")
        lines += self.emit_nodes(node.then)
        return lines

    def _emit_inline_choice(self, node: TextRun) -> list[str]:
        """Essentials' inline ``\\ch[var,ifCancel,opt1,opt2,...]`` text escape
        (SLICE1_TODO #17) — a Show Text message whose choice menu is embedded
        in the text itself rather than a separate 102 command. Fork-native
        ``dynmultichoice`` (asm/macros/event.inc:1932) + a ``msgbox`` for the
        prompt. Parsing is `conversion_agent.inline_choice.parse_inline_choice`
        (CLAUDE.md §4.3); this method does the emit-side work only: var-name
        resolution, text translation, dynmultichoice/queue lines. Queues
        (whole command, nothing emitted) for every reason
        `parse_inline_choice` can raise, plus an unresolvable var id.
        """
        text = node.text
        try:
            choice = parse_inline_choice(text, allow_cancel_sentinel=True)
        except InlineChoiceError as exc:
            return [self.ctx.queue(node.index, SHOW_TEXT, exc.message)]
        if choice.if_cancel < 0:
            # ifCancel -1: Essentials stores -1 on cancel, unrepresentable in a
            # u16 var. Store CANCEL_SENTINEL instead, but only when every read
            # of the var on this page is an ==/!= against a non-negative
            # option index (see inline_choice.cancel_sentinel_read_problem).
            problem = cancel_sentinel_read_problem(self.page_commands, choice.var_id)
            if problem is not None:
                return [self.ctx.queue(
                    node.index, SHOW_TEXT,
                    f"inline choice: ifCancel {choice.if_cancel} stores a "
                    f"negative value a u16 var cannot hold, and {problem}",
                )]

        prompt_text = choice.prompt_text
        if_cancel = choice.if_cancel
        options = choice.options

        var_name = self.ctx.var_for_variable(choice.var_id)
        if var_name is None:
            return [self.ctx.queue(
                node.index, SHOW_TEXT,
                f"inline choice: variable {choice.var_id} is unnamed — cannot mint a VAR_*",
            )]

        prompt_source = _COLOUR_TEXT_CODE_RE.sub("", _BLUE_TEXT_CODE_RE.sub("", prompt_text))
        result = translate_text_codes(prompt_source.strip())
        if result is None:
            return [self.ctx.queue(
                node.index, SHOW_TEXT,
                f"dialogue with untranslated control code: {prompt_text[:120]!r}",
            )]
        prompt = format_pory_dialogue(result.text)
        if result.autoclose:
            lines = [f"msgbox({prompt}, MSGBOX_AUTOCLOSE)"]
        elif result.sign:
            lines = ["lock", f"msgbox({prompt})", "release"]
        else:
            lines = [f"msgbox({prompt})"]

        self._choice_count += 1
        choice_no = self._choice_count
        opt_labels: list[str] = []
        for m, opt_text in enumerate(options):
            label = f"{self.page_label}_Choice{choice_no}_Opt{m}"
            self.text_blocks.append((label, format_pory_dialogue(opt_text)))
            opt_labels.append(label)

        cancel_value = CANCEL_SENTINEL if if_cancel < 0 else if_cancel - 1
        ignore_b_press = "TRUE" if if_cancel == 0 else "FALSE"
        argv = ", ".join(opt_labels)
        lines.append(
            f"dynmultichoice(0, 0, {ignore_b_press}, 6, 0, "
            f"DYN_MULTICHOICE_CB_NONE, {argv})"
        )
        if if_cancel == 0:
            lines.append(f"copyvar({var_name}, VAR_RESULT)")
        else:
            lines += [
                "if (var(VAR_RESULT) == MULTI_B_PRESSED) {",
                f"    setvar({var_name}, {cancel_value})",
                "} else {",
                f"    copyvar({var_name}, VAR_RESULT)",
                "}",
            ]
        return lines

    def _emit_starter_pick_choice_idiom(self, node: ChoiceNode) -> list[str] | None:
        """The three-option starter-pick menu (Map068 EV003 page 1 cmd 3,
        output/uranium-build/maps/Map068.json — ``['Orchynx', 'Raptorch',
        'Eletux']``, no cancel arm). ``_emit_choice`` below only natively
        handles 2-way choices via ``yesnobox``; a 3+-option menu needs a
        minted ``MULTI_*`` multichoice list, which is a per-menu engine-side
        asset (``engine/include/constants/script_menu.h`` /
        ``engine/src/data/script_menu.h``) — trusting an unminted constant
        would compile-clean-but-wrong (CLAUDE.md §4.1). ``MULTI_URANIUM_STARTER_PICK``
        is that minted list for exactly this menu (option order Orchynx/
        Raptorch/Eletux at indices 0/1/2, per the concurrent engine-side
        change) — deliberately keyed on the exact label tuple, not on "any
        3-option choice," so no other 3+-option menu can silently pick up a
        constant that was never minted for it.

        Returns ``None`` (falls through to ``_emit_choice``'s generic
        2-way/queue handling) for: any label list other than exactly
        ``['Orchynx', 'Raptorch', 'Eletux']``, a cancel arm present (this
        menu has none — a cancel arm would mean a different shape we have not
        verified against the minted list), or arm indices that are not
        exactly ``{0, 1, 2}``."""
        params = node.cmd.get("parameters", [])
        choices = params[0] if params else []
        if list(choices) != ["Orchynx", "Raptorch", "Eletux"]:
            return None
        arm_children: dict[int, list[Node]] = {}
        for choice_idx, _text, children in node.arms:
            if choice_idx is None:
                return None  # cancel arm present — not this menu's verified shape
            arm_children[choice_idx] = children
        if set(arm_children) != {0, 1, 2}:
            return None
        lines = [
            "multichoice(0, 0, MULTI_URANIUM_STARTER_PICK, TRUE)",
            "switch (var(VAR_RESULT)) {",
        ]
        for i in range(3):
            lines.append(f"    case {i}:")
            lines += [f"        {ln}" for ln in self.emit_nodes(arm_children[i])]
        lines.append("}")
        return lines

    def _emit_choice(self, node: ChoiceNode) -> list[str]:
        starter_pick = self._emit_starter_pick_choice_idiom(node)
        if starter_pick is not None:
            return starter_pick
        params = node.cmd.get("parameters", [])
        choices = params[0] if params else []
        # v1 tier: any two-way choice maps to the yesnobox/VAR_RESULT idiom,
        # regardless of the choice labels — the prompt text is the preceding
        # msgbox, and poryscript's msgbox(text, MSGBOX_YESNO) form needs the
        # text inline, so the driver-level idiom (merge with the preceding
        # TextRun) is deferred. Custom choice labels degrade to generic
        # YES/NO (cosmetic, accepted v1 trade-off) — pressing B maps to the
        # second arm, matching RMXP cancel-type 2 (the common case). Choices
        # with 3+ texts still need a minted MULTI_* multichoice and fall
        # through to the unhandled queue below.
        if len(choices) == 2:
            yes_arm = next((a for a in node.arms if a[0] == 0), None)
            no_arm = next((a for a in node.arms if a[0] == 1 or a[0] is None), None)
            lines = ["yesnobox(0, 0)", "if (var(VAR_RESULT) == 1) {"]
            if yes_arm:
                lines += [f"    {ln}" for ln in self.emit_nodes(yes_arm[2])]
            lines.append("} else {")
            if no_arm:
                lines += [f"    {ln}" for ln in self.emit_nodes(no_arm[2])]
            lines.append("}")
            return lines
        return [self.ctx.queue(
            node.index, SHOW_CHOICES,
            f"choice menu {[str(c) for c in choices]} — needs a minted MULTI_* "
            f"multichoice; arms not emitted",
        )]

    def _emit_control_switches(self, node: Node) -> list[str]:
        params = node.cmd.get("parameters", [])
        if len(params) < 3:
            return [self.ctx.queue(node.index, CONTROL_SWITCHES, "bad 121 params")]
        start, end, value = params[0], params[1], params[2]
        lines: list[str] = []
        for switch_id in range(start, end + 1):
            name = self.ctx.flag_for_switch(switch_id)
            if name is None:
                lines.append(self.ctx.queue(
                    node.index, CONTROL_SWITCHES,
                    f"switch {switch_id} is unnamed or a script-switch — "
                    f"cannot mint a FLAG_* deterministically",
                ))
                continue
            lines.append(f"setflag({name})" if value == 0 else f"clearflag({name})")
        return lines

    def _emit_control_variables(self, node: Node) -> list[str]:
        # [start_id, end_id, operation(0 set/1 add/2 sub/...), operand_kind, operand]
        params = node.cmd.get("parameters", [])
        if len(params) < 5:
            return [self.ctx.queue(node.index, CONTROL_VARIABLES, "bad 122 params")]
        start, end, operation, operand_kind = params[0], params[1], params[2], params[3]
        lines: list[str] = []
        for variable_id in range(start, end + 1):
            name = self.ctx.var_for_variable(variable_id)
            if name is None:
                lines.append(self.ctx.queue(
                    node.index, CONTROL_VARIABLES,
                    f"variable {variable_id} is unnamed — cannot mint a VAR_*",
                ))
                continue
            if operand_kind == 0 and isinstance(params[4], int):  # constant
                if operation == 0:
                    lines.append(f"setvar({name}, {params[4]})")
                elif operation == 1:
                    lines.append(f"addvar({name}, {params[4]})")
                elif operation == 2:
                    lines.append(f"subvar({name}, {params[4]})")
                else:
                    lines.append(self.ctx.queue(
                        node.index, CONTROL_VARIABLES,
                        f"variable op {operation} (mul/div/mod) has no script macro",
                    ))
            elif operand_kind == 1:  # another variable
                other = self.ctx.var_for_variable(params[4])
                if other is None or operation != 0:
                    lines.append(self.ctx.queue(
                        node.index, CONTROL_VARIABLES,
                        f"variable-operand op {operation} with unnamed source",
                    ))
                else:
                    lines.append(f"copyvar({name}, {other})")
            elif operand_kind == 2 and operation == 0 and len(params) >= 6:
                # random [lo, hi] → random(count) puts 0..count-1 in
                # VAR_RESULT; shift by lo when nonzero. (Oracle-validated
                # idiom, Map002 EV004/EV007.)
                lo, hi = params[4], params[5]
                if isinstance(lo, int) and isinstance(hi, int) and hi >= lo:
                    lines.append(f"random({hi - lo + 1})")
                    if lo:
                        lines.append(f"addvar(VAR_RESULT, {lo})")
                    lines.append(f"copyvar({name}, VAR_RESULT)")
                else:
                    lines.append(self.ctx.queue(
                        node.index, CONTROL_VARIABLES,
                        f"random operand with non-int bounds {params[4:6]!r}",
                    ))
            else:
                lines.append(self.ctx.queue(
                    node.index, CONTROL_VARIABLES,
                    f"operand kind {operand_kind} (random/item/actor/…) unhandled",
                ))
        return lines

    def _align_loop_lines(self, node: LoopNode) -> list[str] | None:
        """The Essentials wait-until-aligned idiom (Map032 EV74/78/80): a 112
        loop whose body is exactly ``if $game_player.AXIS CMP N; break;`` (no
        else) followed by a one-step player move + wait. Collapses to a
        poryscript ``while`` on the NEGATED break condition. Any other 112
        loop shape returns ``None`` (caller queues, as before)."""
        # 509 rows are the editor's per-step display duplicates of the 209
        # route (stripped everywhere else too) — invisible to the shape match.
        children = [
            c for c in node.children
            if not (isinstance(c, Leaf) and c.cmd.get("code") == MOVE_COMMAND_ROW)
        ]
        if len(children) != 3:
            return None
        if_node, move_leaf, wait_leaf = children

        if not isinstance(if_node, IfNode) or if_node.otherwise:
            return None
        if (
            len(if_node.then) != 1
            or not isinstance(if_node.then[0], Leaf)
            or if_node.then[0].cmd.get("code") != BREAK_LOOP
        ):
            return None
        cond_params = if_node.cmd.get("parameters", [])
        if len(cond_params) < 2 or cond_params[0] != 12 or not isinstance(cond_params[1], str):
            return None
        m = _ALIGN_BREAK_RE.match(cond_params[1])
        if not m:
            return None
        axis, cmp_op, n_str = m.groups()

        if not isinstance(move_leaf, Leaf) or move_leaf.cmd.get("code") != SET_MOVE_ROUTE:
            return None
        move_params = move_leaf.cmd.get("parameters", [])
        if len(move_params) < 2 or move_params[0] != -1 or not isinstance(move_params[1], dict):
            return None  # only a player-target move is the proven shape
        tokens = route_tokens(move_params[1])
        if tokens is None or len(tokens) != 1:
            return None  # anything but a single-step move is outside the tier

        if not isinstance(wait_leaf, Leaf) or wait_leaf.cmd.get("code") != WAIT_MOVE_COMPLETION:
            return None

        var_name = _ALIGN_AXIS_VAR[axis]
        negated = _ALIGN_NEGATED_CMP[cmp_op]
        # Inline `[token]` movement lists are NOT supported by the installed
        # poryscript (passed through verbatim -> asm error); emit a named
        # movement block like _emit_move_route does.
        label = f"{self.page_label}_Move{len(self.movements) + 1}"
        self.movements.append((label, [tokens[0]]))
        return [
            "getplayerxy(VAR_TEMP_0, VAR_TEMP_1)",
            f"while (var({var_name}) {negated} {n_str}) {{",
            f"    applymovement(OBJ_EVENT_ID_PLAYER, {label})",
            "    waitmovement(0)",
            "    getplayerxy(VAR_TEMP_0, VAR_TEMP_1)",
            "}",
        ]

    def _emit_show_animation(self, node: Node) -> list[str]:
        """RMXP 207 (Show Animation): the emote tier only — pokeemerald ships
        exclamation/question emotes as movement tokens
        (``engine/data/scripts/movement.inc``), not a runtime animation call,
        so the mapping is an ``applymovement`` + ``waitmovement`` pair, same
        shape as a 209 move route. An id in ``_EMOTE_DROP_IDS`` is a decided
        drop (breadcrumb, no queue entry); any other unmapped animation id
        still queues."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or not all(isinstance(v, int) for v in params[:2]):
            return [self.ctx.queue(node.index, SHOW_ANIMATION, "bad 207 params")]
        target_id, animation_id = params[0], params[1]
        if animation_id in _EMOTE_DROP_IDS:
            return [f"# show animation id {animation_id} on target {target_id} "
                    f"— no OW analog, dropped (approved, v1)"]
        label = _EMOTE_MOVEMENT_LABELS.get(animation_id)
        if label is None:
            return [self.ctx.queue(
                node.index, SHOW_ANIMATION,
                f"show animation id {animation_id} on target {target_id} — "
                f"no emote mapping in the v1 tier",
            )]
        if target_id == -1:
            who = "OBJ_EVENT_ID_PLAYER"
        elif target_id == 0:
            # RMXP "this event" -> the event's own id, exactly as the 209
            # self-target path does (local_id_remap rewrites it post-transpile).
            if self.ctx.event_id is None:
                return [self.ctx.queue(
                    node.index, SHOW_ANIMATION,
                    "show animation on self (target 0) in a common event",
                )]
            who = str(self.ctx.event_id)
        else:
            # task-4: local id = RMXP event id (same assumption _emit_move_route
            # makes for a 209 target — pokeemerald localids map 1:1 in our
            # porymap export).
            who = str(target_id)
        return [f"applymovement({who}, {label})", "waitmovement(0)"]

    def _emit_player_transparency(self, node: Node) -> list[str]:
        """RMXP 208 (Change Player Transparency) always targets the player
        (Essentials ``$game_player.transparent = (params[0] == 0)``), unlike
        209 which can target self/other events. ``set_invisible``/
        ``set_visible`` are the same token spellings ``route_tokens`` already
        emits for a 209's opacity step (42) — reused literally, not
        reinvented."""
        params = node.cmd.get("parameters", [])
        if not params or params[0] not in (0, 1):
            return [self.ctx.queue(
                node.index, CHANGE_PLAYER_TRANSPARENCY, "bad 208 params",
            )]
        token = "set_invisible" if params[0] == 0 else "set_visible"
        # Named movement block, not an inline `[token]` list — the installed
        # poryscript passes brackets through verbatim (asm error).
        label = f"{self.page_label}_Move{len(self.movements) + 1}"
        self.movements.append((label, [token]))
        return [
            f"applymovement(OBJ_EVENT_ID_PLAYER, {label})",
            "waitmovement(0)",
        ]

    def _emit_door_self_route(self, node: Node, route: dict) -> list[str]:
        """A door-sheet event turning through its own rows -> native door
        animation at the event's tile. Multi-frame: ``opendoor``/``closedoor``
        + ``waitdooranim`` (the paired 210 is neutralized — waitdooranim is the
        wait). Single-facing snap: ``setdooropen``/``setdoorclosed``."""
        self._last_route_ok = False  # the 210 must not become a waitmovement
        ctx = self.ctx
        plan = _door_route_plan(route)
        if isinstance(plan, str):
            return [ctx.queue(
                node.index, SET_MOVE_ROUTE,
                f"door-sheet {ctx.page_graphic!r} self-route: {plan}",
            )]
        if not isinstance(ctx.event_x, int) or not isinstance(ctx.event_y, int):
            return [ctx.queue(
                node.index, SET_MOVE_ROUTE,
                f"door-sheet {ctx.page_graphic!r} self-route without event coordinates",
            )]
        state, animated = plan
        x, y = ctx.event_x, ctx.event_y
        if animated:
            verb = "opendoor" if state == "open" else "closedoor"
            return [f"{verb}({x}, {y})", "waitdooranim"]
        verb = "setdooropen" if state == "open" else "setdoorclosed"
        return [f"{verb}({x}, {y})"]

    def _emit_move_route(self, node: Node) -> list[str]:
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or not isinstance(params[1], dict):
            self._last_route_ok = False
            return [self.ctx.queue(node.index, SET_MOVE_ROUTE, "malformed 209 params")]
        target, route = params[0], params[1]
        if target == -1 and _is_cave_step_forward_route(route):
            # code-12 (Step Forward, relative-to-facing) on the player — see
            # module-level comment on _is_cave_step_forward_route. No token
            # to emit (facing-relative movement has no fork equivalent), and
            # the paired 210 must be neutralized too — same disposition as a
            # queued route (WAIT_MOVE_COMPLETION checks _last_route_ok).
            self._last_route_ok = False
            return [
                "# cave transition: player step-forward route (code 12) "
                "dropped — no facing-relative movement token, subsumed by "
                "native warp fade"
            ]
        # RMXP target: -1 = player, 0 = this event, N = event N.
        # pokeemerald localids: OBJ_EVENT_ID_PLAYER for the player; event ids
        # map 1:1 to localids in our porymap export.
        if target == -1:
            who = "OBJ_EVENT_ID_PLAYER"
        elif target == 0:
            if self.ctx.event_id is None:
                self._last_route_ok = False
                return [self.ctx.queue(
                    node.index, SET_MOVE_ROUTE,
                    "self-target move route in a common event",
                )]
            who = str(self.ctx.event_id)
        else:
            who = str(target)

        if (target == 0 or (target != -1 and target == self.ctx.event_id)) \
                and is_door_sheet(self.ctx.page_graphic):
            return self._emit_door_self_route(node, route)

        # A code-41 Change Graphic step is script-level, not a movement token,
        # so a route carrying one is emitted as alternating applymovement runs
        # and gfx swaps rather than a single movement block.
        if any(step.get("code") == CHANGE_GRAPHIC for step in route.get("list", [])):
            return self._emit_route_with_gfx_swaps(node, route, who)

        tokens = route_tokens(route)
        if tokens is None or not tokens:
            self._last_route_ok = False
            return [self.ctx.queue(
                node.index, SET_MOVE_ROUTE, _describe_route(route, target),
            )]
        label = f"{self.page_label}_Move{len(self.movements) + 1}"
        self.movements.append((label, tokens))
        self._last_route_ok = True
        return [f"applymovement({who}, {label})"]

    def _emit_route_with_gfx_swaps(
        self, node: Node, route: dict, who: str
    ) -> list[str]:
        """A move route containing RMXP code-41 Change Graphic steps.

        Splits the route on its 41s: each run of ordinary steps becomes its own
        ``applymovement`` (followed by a ``waitmovement``, so the swap lands
        after the motion it was authored to follow, not during it), and each 41
        becomes a ``setobjectgfx(localId, gfxId)`` call — the
        ``asm/macros/event.inc`` macro wrapping the ``RPG2GBA_SetObjectEventGfx``
        special (engine/src/event_object_movement.c, sentinel-fenced).

        Sheet name → constant comes from ``reference/npc_gfx_map.json``, the
        same single source of truth the sprite pass uses; an unmapped sheet
        queues rather than inventing a constant (CLAUDE.md §4.3, §4.7).
        """
        lines: list[str] = []
        pending: list[dict] = []
        emitted_movement = False

        def flush() -> bool:
            nonlocal emitted_movement
            if not pending:
                return True
            tokens = route_tokens({**route, "list": [*pending, {"code": 0}]})
            pending.clear()
            if tokens is None or not tokens:
                return False
            label = f"{self.page_label}_Move{len(self.movements) + 1}"
            self.movements.append((label, tokens))
            lines.append(f"applymovement({who}, {label})")
            lines.append("waitmovement(0)")
            emitted_movement = True
            return True

        for step in route.get("list", []):
            if step.get("code", 0) == 0:
                continue  # route terminator — flush() re-adds its own
            if step.get("code") != CHANGE_GRAPHIC:
                pending.append(step)
                continue
            if not flush():
                self._last_route_ok = False
                return [self.ctx.queue(
                    node.index, SET_MOVE_ROUTE,
                    _describe_route(route, who) + " — untranslatable step "
                    "alongside a change-graphic",
                )]
            params = step.get("parameters", [])
            sheet = params[0] if params and isinstance(params[0], str) else ""
            direction = params[2] if len(params) > 2 else None
            pattern = params[3] if len(params) > 3 else None

            # RMXP Change Graphic sets sheet AND (direction, pattern) together,
            # and props use those to select a visual STATE rather than a facing:
            # Map050's pokéball machine swaps to its OWN sheet repeatedly,
            # moving only direction/pattern, so a sheet-only conversion is a
            # visible no-op. Sheets whose art the sprite pass emits state by
            # state (`npc_gfx_states`, currently the 64x64 large props) resolve
            # to the exact state's own OBJ_EVENT_GFX_* — one gfx swap, no
            # facing, nothing dropped.
            states = self.ctx.npc_gfx_states.get(sheet)
            if states:
                entry = states.get((direction, pattern))
                if entry is None:
                    self._last_route_ok = False
                    return [self.ctx.queue(
                        node.index, SET_MOVE_ROUTE,
                        f"change-graphic to sheet {sheet!r} state "
                        f"(direction {direction}, pattern {pattern}), which its "
                        f"art has no cell for — the sheet's emitted states are "
                        f"{sorted(states)}",
                    )]
                lines.append(f"setobjectgfx({who}, {entry})")
                continue

            entry = self.ctx.npc_gfx.get(sheet)
            if not entry:
                self._last_route_ok = False
                return [self.ctx.queue(
                    node.index, SET_MOVE_ROUTE,
                    f"change-graphic to unmapped sheet {sheet!r} — add it to "
                    f"reference/npc_gfx_map.json",
                )]
            lines.append(f"setobjectgfx({who}, {entry})")
            # Sheets converted as ordinary walk cycles have no per-state art:
            # direction still has an exact analog (the object's facing picks the
            # same row of the converted 4-direction sheet), so emit it as its own
            # movement block. `pattern` (the frame within a row) has none — the
            # fork animates frames itself and no movement action selects one — so
            # a pattern-moving swap on such a sheet is a real drop and says so
            # rather than pretending (§4.5).
            face = _RMXP_DIRECTION_TOKENS.get(direction)
            if face is not None:
                label = f"{self.page_label}_Move{len(self.movements) + 1}"
                self.movements.append((label, [face]))
                lines.append(f"applymovement({who}, {label})")
                lines.append("waitmovement(0)")
                emitted_movement = True
            if isinstance(pattern, int) and pattern != 0:
                lines.append(self.ctx.queue(
                    node.index, SET_MOVE_ROUTE,
                    f"change-graphic on sheet {sheet!r} also selects frame "
                    f"{pattern} within the row; the fork drives sprite frames "
                    f"itself and no movement action picks one, so that part of "
                    f"the state change is dropped",
                ))
        if not flush():
            self._last_route_ok = False
            return [self.ctx.queue(
                node.index, SET_MOVE_ROUTE, _describe_route(route, who),
            )]
        # This emitter waits for its own movement; a following 210 would be a
        # second wait on nothing, so it is always neutralized.
        self._last_route_ok = False
        if not emitted_movement and not lines:
            return [self.ctx.queue(
                node.index, SET_MOVE_ROUTE, _describe_route(route, who),
            )]
        return lines

    def _emit_tone(self, node: Node) -> list[str]:
        params = node.cmd.get("parameters", [])
        tone = params[0] if params else None
        if isinstance(tone, dict) and "rgba" in tone:
            rgb = tuple(int(v) for v in tone["rgba"][:3])
            fade = _TONE_FADES.get(rgb)
            if fade is not None:
                return [f"fadescreen({fade})"]
        return [self.ctx.queue(
            node.index, CHANGE_TONE,
            f"screen tone {tone!r} has no fadescreen mapping",
        )]

    def _emit_change_map_settings(self, node: Node) -> list[str]:
        """Code-204 (Change Map Settings) — see ``_CAVE_FOG_204_PARAMS`` for
        the fork/corpus evidence. Only the exact cave-entrance fog tuple
        strips; any other subtype or value queues (unchanged disposition)."""
        params = node.cmd.get("parameters", [])
        if tuple(params) == _CAVE_FOG_204_PARAMS:
            return [
                "# cave transition: fog settings (004-Shade02) dropped — "
                "post-warp cosmetic, no GBA fog layer (code 204)"
            ]
        return [self.ctx.queue(
            node.index, CHANGE_MAP_SETTINGS,
            "command 204 outside the v1 deterministic tier",
        )]

    def _emit_script_call(self, node: Node) -> list[str]:
        # v1: the STRIP set from the validated ledger produces nothing; two
        # slice-proven idioms emit deterministically; everything else queues
        # (the idiom library grows per grill D8 on queue evidence).
        from rpg2gba.conversion_agent.deterministic import (
            _DIALOGUE_STRIP_RE,
            _PBPOKEMART_ITEM_RE,
            _PBPOKEMART_LIST_RE,
        )
        params = node.cmd.get("parameters", [])
        text = params[0] if params and isinstance(params[0], str) else ""

        # Completing a pending "$PokemonGlobal.seenStorageCreator=" opener
        # (see _SEEN_STORAGE_CREATOR_OPEN_RE) — checked first, before any
        # other idiom, since the completing row is a bare "true"/"false" that
        # matches nothing else. Only "true" resolves; anything else queues
        # BOTH the opener and this row rather than guessing at "false".
        if self._pending_storage_creator_open is not None:
            opener_index = self._pending_storage_creator_open
            self._pending_storage_creator_open = None
            if text.strip() == "true":
                return ["setflag(FLAG_SYS_PC_LANETTE)"]
            return [
                self.ctx.queue(
                    opener_index, SCRIPT,
                    "script call: '$PokemonGlobal.seenStorageCreator=' "
                    "(split assignment)",
                ),
                self.ctx.queue(
                    node.index, SCRIPT,
                    f"seenStorageCreator continuation not 'true': {text[:120]!r}",
                ),
            ]

        # Kernel.pbSetPokemonCenter — white-out respawn anchor (see
        # _SET_POKEMON_CENTER_RE above). Checked before _DIALOGUE_STRIP_RE
        # (which no longer lists this head — recon corrected the STRIP ruling
        # twice, reference/recon/uranium_script_calls.md:71). A common event
        # has no single owning map/event to resolve a respawn tile against,
        # so it always queues regardless of the lookup table's contents.
        if _SET_POKEMON_CENTER_RE.match(text):
            if self.ctx.event_id is not None and self.ctx.common_event_id is None:
                key = (self.ctx.map_id, self.ctx.event_id, self.ctx.page_no)
                heal_location = self.ctx.heal_locations.get(key)
                if heal_location is not None:
                    return [f"setrespawn({heal_location})"]
            return [self.ctx.queue(
                node.index, SCRIPT,
                "pbSetPokemonCenter: call site not in the resolved "
                "heal_locations table (unstaged map, unresolved bare call, "
                "or a common event — no single owning map/event to resolve "
                "a respawn tile against)",
            )]

        # Kernel.pbSetHealingSpot(m,x,y) — teleport anchor (see
        # _SET_HEALING_SPOT_RE). Resolves only on an exact minted-tile match.
        m = _SET_HEALING_SPOT_RE.match(text)
        if m:
            triple = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            spot = self.ctx.healing_spots.get(triple)
            if spot is not None:
                return [f"setrespawn({spot})"]
            return [self.ctx.queue(
                node.index, SCRIPT,
                f"script call: {text.strip()!r} — pbSetHealingSpot is the "
                f"teleport anchor; (map, x, y)={triple} matches no minted "
                "HEAL_LOCATION_* tile, and the fork's single lastHealLocation "
                "slot is shared with white-out (setrespawn here would clobber "
                "the pbSetPokemonCenter anchor)",
            )]

        # $Trainer.badges[N]=true — FLAG_BADGE0{N+1}_GET (see _BADGE_TRUE_RE).
        m = _BADGE_TRUE_RE.match(text)
        if m and int(m.group(1)) < NUM_BADGES:
            return [f"setflag({badge_flag(int(m.group(1)))})"]

        if _DIALOGUE_STRIP_RE.match(text):
            return []

        # $PokemonGlobal.seenStorageCreator=true, single-row form (see
        # _SEEN_STORAGE_CREATOR_RE) — Map031 EV49 page0.
        if _SEEN_STORAGE_CREATOR_RE.match(text):
            return ["setflag(FLAG_SYS_PC_LANETTE)"]

        # $PokemonGlobal.seenStorageCreator=, split-row opener (see
        # _SEEN_STORAGE_CREATOR_OPEN_RE) — remember it and emit nothing yet;
        # completed above on the next script-call row.
        if _SEEN_STORAGE_CREATOR_OPEN_RE.match(text):
            self._pending_storage_creator_open = node.index
            return []

        # pbPhoneRegisterNPC(...) — phone-directory registration, cosmetic on
        # the GBA (see _PHONE_REGISTER_NPC_STRIP_RE). Breadcrumb, no queue.
        if _PHONE_REGISTER_NPC_STRIP_RE.match(text):
            return ["# phone: pbPhoneRegisterNPC stripped (slice1)"]

        # pbCaveEntrance — pre-warp fade choreography subsumed by the native
        # warp (see _CAVE_ENTRANCE_STRIP_RE). Breadcrumb, no queue.
        if _CAVE_ENTRANCE_STRIP_RE.match(text):
            return ["# cave transition: pbCaveEntrance subsumed by native warp fade"]

        # showRulesetSettings(mode) — opens the Custom Mode options UI, not
        # portable to GBA (see _SHOW_RULESET_SETTINGS_STRIP_RE). Breadcrumb,
        # no queue. (The other corpus occurrences of this call are already
        # unreachable — nested inside an isCustomGame? then-arm that
        # _emit_custom_game_strip collapses away before this bare-call row
        # is ever walked; this arm only fires for the one standalone
        # occurrence, Map039 EV015.)
        if _SHOW_RULESET_SETTINGS_STRIP_RE.match(text):
            return ["# custom mode: showRulesetSettings stripped (not ported)"]

        # pbTrainerPC — the generic non-bedroom PC (see _TRAINER_PC_RE);
        # EventScript_PC ends the script itself, so `goto` (not `call`).
        if _TRAINER_PC_RE.match(text):
            return ["goto(EventScript_PC)"]

        # pbShowMap — the wall/region-map special (see _SHOW_MAP_RE). Only
        # the call is replaced; any preceding dialogue on the page stays.
        if _SHOW_MAP_RE.match(text):
            return ["special(FieldShowRegionMap)"]

        # $PokemonGlobal.runningShoes=true — b-dash unlock (see
        # _RUNNING_SHOES_ON_RE).
        if _RUNNING_SHOES_ON_RE.match(text):
            return ["setflag(FLAG_SYS_B_DASH)"]

        # $Trainer.pokegear=true — PokéPod/PokéNav unlock (see _POKEGEAR_ON_RE).
        if _POKEGEAR_ON_RE.match(text):
            return ["setflag(FLAG_SYS_POKENAV_GET)"]

        # setTempSwitchOn("A") — set this event's temp switch (344× corpus).
        m = _SET_TEMP_SWITCH_RE.match(text)
        if m and self.ctx.event_id is not None:
            name = self.ctx.registry.mint_temp_switch(
                self.ctx.map_id, self.ctx.event_id, m.group(1)
            )
            return [f"setflag({name})"]

        # pbSetSelfSwitch(18, "A", true) — set ANOTHER event's self-switch on
        # this map (336× corpus). Meaningless without a map (common events).
        m = _SET_SELF_SWITCH_RE.match(text)
        if m and self.ctx.common_event_id is None:
            name = self.ctx.registry.mint_self_switch(
                self.ctx.map_id, int(m.group(1)), m.group(2)
            )
            return [f"setflag({name})" if m.group(3) == "true" else f"clearflag({name})"]

        # Nuzlocke-mode heal loop — subsumed by the paired code-314 Recover All
        # (see _NUZLOCKE_HEAL_STRIP_RE). Breadcrumb, no queue.
        if _NUZLOCKE_HEAL_STRIP_RE.match(text):
            return ["# nuzlocke heal loop stripped — code-314 Recover All covers it"]

        # pbPokemonMart([item, ...]) — the joined multi-row shop call (see
        # _merge_script_call_rows). Mirrors classify_pokemart's native
        # pokemart(<label>)/mart{...} shape, but bare: unlike the classifier
        # (which builds a whole standalone page), this idiom emits into a
        # page the caller's normal trigger handling already wraps in
        # lock/faceplayer/release, so no ceremony here. Every item symbol
        # must resolve through ctx.items or the whole call falls through to
        # the queue — never a partial mart list (CLAUDE.md §4.5).
        m = _PBPOKEMART_LIST_RE.search(text)
        if m:
            consts: list[str] = []
            for sym in _PBPOKEMART_ITEM_RE.findall(m.group(1)):
                const = self.ctx.items.get(sym)
                if const is None:
                    consts = []
                    break
                consts.append(const)
            if consts:
                # A page with several marts (one per branch arm, Map073 EV003)
                # numbers the later ones; the first keeps the bare label.
                n = sum(1 for b in self.aux_blocks
                        if b.startswith(f"mart {self.page_label}_Mart"))
                mart_label = f"{self.page_label}_Mart" + (str(n + 1) if n else "")
                mart_inner = "\n".join(f"    {const}" for const in consts)
                self.aux_blocks.append(f"mart {mart_label} {{\n{mart_inner}\n}}")
                return [f"pokemart({mart_label})"]

        # `<statement> if $game_variables[V]==K` — split the trailing modifier-if
        # off and emit the statement inside a poryscript `if`. A guard whose
        # variable can't be resolved queues the whole row rather than dropping
        # the condition and running the statement unconditionally.
        guard = _RUBY_GUARD_RE.match(text)
        stmt_text = guard.group("stmt") if guard else text
        body = self._emit_ruby_statement(stmt_text, node)
        if body is not None:
            if guard is None:
                return body
            var_name = self.ctx.var_for_variable(int(guard.group("var")))
            if var_name is not None:
                return [
                    f"if (var({var_name}) == {int(guard.group('val'))}) {{",
                    *[f"    {ln}" for ln in body],
                    "}",
                ]

        return [self.ctx.queue(
            node.index, SCRIPT, f"script call: {text[:120]!r}",
        )]

    def _emit_ruby_statement(self, text: str, node: Node) -> list[str] | None:
        """One bare Ruby statement from a 355/655 row, guard already stripped.

        ``None`` = no idiom matched; the caller queues the original row. Every
        arm here resolves its symbols (species, flags) through the same sources
        of truth the rest of the pipeline uses and returns ``None`` on a miss,
        so an unstaged species or unnamed switch queues instead of emitting a
        symbol the fork doesn't define (CLAUDE.md §4.3, §4.5).
        """
        # Kernel.pbReceiveItem(::PBItems::SYMBOL[, qty[, _I("...")]]) as a
        # bare complete statement (see _RECEIVE_ITEM_RE) — the shape-B item
        # grant (Map073 EV6 cmds 5-8: four separate berry grants, each its
        # own complete call; _merge_script_call_rows leaves them unfused
        # since each is a balanced expression, not a mid-expression wrap
        # fragment). Resolved via _give_item_const, the same helper
        # _emit_give_item_idiom uses for the type-12 condition shape —
        # CLAUDE.md §4.3, one source of truth, not re-derived here. An
        # unresolved-or-un-forked symbol returns None so the caller queues
        # the row instead of guessing/inventing a constant (§4.5, §4.7).
        pick = self._emit_pick_statement(text)
        if pick is not None:
            return pick

        m = _RECEIVE_ITEM_RE.match(text)
        if m:
            symbol, qty = m.group(1), m.group(2)
            const = self._give_item_const(symbol)
            if const is None:
                return None  # unresolved item symbol — fall through to the queue
            return [f"giveitem({const}, {qty})" if qty else f"giveitem({const})"]

        # `removeitem itemId:req, quantity=1` (engine/asm/macros/event.inc:572),
        # so a bare one-argument call is the correct emission for the default
        # single-item delete. Same _give_item_const resolution and the same
        # fail-loud disposition as the grant above.
        m = _DELETE_ITEM_RE.match(text)
        if m:
            symbol, qty = m.group(1), m.group(2)
            const = self._give_item_const(symbol)
            if const is None:
                return None  # unresolved item symbol — fall through to the queue
            return [f"removeitem({const}, {qty})" if qty else f"removeitem({const})"]

        m = _PLAY_CRY_RE.match(text)
        if m:
            const = self.ctx.staged_species_constant(m.group(1))
            if const is None:
                return None  # unstaged / unknown species — queue, don't guess
            return [f"playmoncry({const}, CRY_MODE_NORMAL)", "waitmoncry"]

        m = _ADD_POKEMON_SILENT_RE.match(text)
        if m:
            const = self.ctx.staged_species_constant(m.group(1))
            if const is None:
                return None
            return self._emit_give_pokemon(const, int(m.group(2)), silent=True)

        m = _ADD_POKEMON_RE.match(text)
        if m:
            const = self.ctx.staged_species_constant(m.group(1))
            if const is None:
                return None
            return self._emit_give_pokemon(const, int(m.group(2)), silent=False)

        m = _SWITCH_ASSIGN_RE.match(text)
        if m:
            name = self.ctx.flag_for_switch(int(m.group(1)))
            if name is None:
                return None
            return [f"setflag({name})" if m.group(2) == "true" else f"clearflag({name})"]

        if _POKEDEX_GRANT_RE.match(text):
            return [
                "setflag(FLAG_SYS_POKEDEX_GET)",
                "special(SetUnlockedPokedexFlags)",
                "special(EnableNationalPokedex)",
            ]

        # -- Ruby locals / arrays / argmax (C8 stage 6) -----------------------
        # Twelve shapes, all recognized by `ruby_idioms` against a real parse
        # rather than an anchored regex each (CLAUDE.md §4.3). The row is
        # parsed ONCE here and the parse tree handed to each matcher in turn;
        # the order below is the order the regexes used to be tried in, which
        # several of these depend on (`x=0` must not be read as a remap arm
        # body before the array/argmax shapes have had their look). A row
        # that doesn't parse leaves `stmt` None, so every node matcher misses
        # and the row falls through to the queue exactly as before.
        stmt = ruby_idioms.parse_statement(text)

        # These rows emit nothing on their own; they build the argument the
        # pbStarterSelector call below consumes. Tracked, not queued.
        from_var = ruby_idioms.match_local_from_var(stmt) if stmt else None
        if from_var is not None:
            self._ruby_locals[from_var.name] = _RubyLocal(
                source_var=from_var.source_var)
            return []

        addsub = ruby_idioms.match_local_addsub(stmt) if stmt else None
        if addsub is not None and addsub.name in self._ruby_locals:
            local = self._ruby_locals[addsub.name]
            self._ruby_locals[addsub.name] = _RubyLocal(
                local.source_var, local.offset + addsub.delta, local.wrap
            )
            return []

        wrap = ruby_idioms.match_local_wrap(stmt) if stmt else None
        if wrap is not None and wrap.name in self._ruby_locals:
            local = self._ruby_locals[wrap.name]
            self._ruby_locals[wrap.name] = _RubyLocal(
                local.source_var, local.offset,
                (wrap.from_value, wrap.to_value),
            )
            return []

        # -- array-valued game variable (the aptitude tally) ------------------
        array_lit = ruby_idioms.match_array_literal(stmt) if stmt else None
        if array_lit is not None:
            return self._emit_array_literal(array_lit.var_id, array_lit.values)

        bump = ruby_idioms.match_array_bump(stmt) if stmt else None
        if bump is not None:
            return self._emit_array_bump(
                bump.var_id, bump.index_var, bump.delta)

        argmax = ruby_idioms.match_array_argmax(stmt) if stmt else None
        if argmax is not None and argmax.var_id in self._array_vars:
            # Value lands in the local; nothing is emitted until the local is
            # written back to a real variable (match_var_from_local below).
            self._ruby_locals[argmax.name] = _RubyLocal(
                source_var=argmax.var_id, argmax_of=argmax.var_id)
            return []

        const_assign = (
            ruby_idioms.match_local_const_assign(stmt) if stmt else None)
        if const_assign is not None and self._pending_remap is not None:
            # Body of the `if x==A / x=B` remap opened below.
            local = self._ruby_locals.get(const_assign.name)
            if local is not None and local.argmax_of is not None:
                self._pending_remap = (
                    const_assign.name, self._pending_remap[1],
                    const_assign.value,
                )
                local.remap[self._pending_remap[1]] = const_assign.value
                return []

        arm = ruby_idioms.match_remap_arm_open(text)
        if arm is not None:
            local = self._ruby_locals.get(arm.name)
            if local is not None and local.argmax_of is not None:
                # `if x==1 / x=0 / elsif x==0 / x=1 / end` is a value
                # permutation over the argmax result, not control flow — the
                # arms are mutually exclusive tests of the same local.
                self._pending_remap = (arm.name, arm.tested_value, None)
                return []

        if ruby_idioms.is_block_end(text) and self._pending_remap is not None:
            self._pending_remap = None
            return []

        writeback = ruby_idioms.match_var_from_local(stmt) if stmt else None
        if writeback is not None:
            local = self._ruby_locals.get(writeback.name)
            if local is not None and local.argmax_of is not None:
                return self._emit_argmax(writeback.var_id, local)
            if local is not None:
                return self._emit_local_materialize(
                    writeback.var_id, writeback.name, local)

        # -- string-valued Ruby local + indexed text readback ----------------
        # See ruby_idioms.StringList. Both rows are tracked only; nothing is
        # emitted until _emit_value_var_text sees the \v[N].
        string_list = ruby_idioms.match_string_list(stmt) if stmt else None
        if string_list is not None:
            self._string_lists[string_list.name] = list(string_list.values)
            return []

        readback = ruby_idioms.match_var_from_list_index(stmt) if stmt else None
        if readback is not None:
            values = self._string_lists.get(readback.list_name)
            target = self._materialized_locals.get(readback.index_name)
            if values and target is not None:
                self._value_text_choices[readback.var_id] = (target, values)
                return []

        m = _STARTER_SELECTOR_PBGET_RE.match(text)
        if m:
            # No intervening Ruby local: the variable already holds the
            # 0-based starter index the argmax wrote into it.
            var_id = int(m.group(1))
            return self._emit_starter_selector_over(
                var_id, {i: i for i in range(len(
                    (self.ctx.starter_scene.get("starters") or [])))},
                theo=m.group(2) == "true")

        m = _STARTER_SELECTOR_RE.match(text)
        if m:
            return self._emit_starter_selector(m.group(1), m.group(2) == "true")

        # $game_variables[N]=$Trainer.party.length (see _PARTY_LENGTH_ASSIGN_RE).
        m = _PARTY_LENGTH_ASSIGN_RE.match(text)
        if m:
            var_name = self.ctx.var_for_variable(int(m.group(1)))
            if var_name is None:
                return None  # unnamed RMXP variable — fall through to the queue
            return [f"specialvar({var_name}, CalculatePlayerPartyCount)"]

        # pbSet(<int>, <int>) — literal id/value only (see _PBSET_LITERAL_RE
        # and the pbGet/pbSet module note above). Unnamed target variable
        # queues (never mints a scratch VAR_*, CLAUDE.md §6); a computed
        # argument (anything not matching the fully-literal shape) also
        # queues, with a reason naming the unsupported shape rather than
        # falling through to the generic "script call: ..." echo.
        m = _PBSET_LITERAL_RE.match(text)
        if m:
            var_name = self.ctx.var_for_variable(int(m.group("var")))
            if var_name is None:
                return [self.ctx.queue(
                    node.index, SCRIPT,
                    f"pbSet({m.group('var')}, ...): variable "
                    f"{m.group('var')} is unnamed — cannot mint a VAR_*",
                )]
            return [f"setvar({var_name}, {int(m.group('val'))})"]
        if _PBSET_HEAD_RE.match(text):
            return [self.ctx.queue(
                node.index, SCRIPT,
                "pbSet(...) with a computed argument (not a plain int "
                f"literal) — no expression evaluator: {text[:120]!r}",
            )]

        # $game_variables[<int>] = pbGet(<int>) — pbGet used exactly where a
        # plain variable read is expected (see _PBGET_ASSIGN_LITERAL_RE):
        # straight copyvar, no arithmetic. Any other pbGet(...) shape
        # (nested in arithmetic/array-indexing/method args — the corpus
        # norm) queues with a precise reason instead of falling through to
        # the generic echo.
        m = _PBGET_ASSIGN_LITERAL_RE.match(text)
        if m:
            target_name = self.ctx.var_for_variable(int(m.group("target")))
            source_name = self.ctx.var_for_variable(int(m.group("source")))
            if target_name is None or source_name is None:
                return [self.ctx.queue(
                    node.index, SCRIPT,
                    f"$game_variables[{m.group('target')}]=pbGet("
                    f"{m.group('source')}): unnamed variable (target or "
                    "source) — cannot mint a VAR_*",
                )]
            return [f"copyvar({target_name}, {source_name})"]
        if _PBGET_HEAD_RE.search(text):
            return [self.ctx.queue(
                node.index, SCRIPT,
                "pbGet(...) not in a plain-variable-read assignment shape "
                f"— no expression evaluator: {text[:120]!r}",
            )]

        return None

    def _emit_local_materialize(
        self, target_var_id: int, local_name: str, local: _RubyLocal
    ) -> list[str] | None:
        """``$game_variables[N] = x`` where ``x`` is a plain (non-argmax)
        tracked local — ``copyvar`` the source var into the real target, then
        replay ``x``'s offset/wrap at runtime (the same arithmetic
        ``_RubyLocal.value_for`` replays at *emit* time for
        ``pbStarterSelector``'s switch arms, here reproduced as actual
        instructions because the target is a real, reused var rather than a
        one-shot switch scrutinee — Map032 EV9's ``VAR_TEMP_POKEMON_CHOICE``
        is read by five different branches downstream). Registers the target
        under ``local_name`` in ``_materialized_locals`` so a later
        list-index readback (``ruby_idioms.match_var_from_list_index``) sharing the same
        local can find it. Returns ``None`` (queues) if either var is
        unnamed.
        """
        target = self.ctx.var_for_variable(target_var_id)
        source = self.ctx.var_for_variable(local.source_var)
        if target is None or source is None:
            return None
        lines = [f"copyvar({target}, {source})"]
        if local.offset > 0:
            lines.append(f"addvar({target}, {local.offset})")
        elif local.offset < 0:
            lines.append(f"subvar({target}, {-local.offset})")
        if local.wrap is not None:
            test_value, replacement = local.wrap
            lines += [
                f"if (var({target}) == {test_value}) {{",
                f"    setvar({target}, {replacement})",
                "}",
            ]
        self._materialized_locals[local_name] = target
        return lines

    def _emit_value_var_text(self, raw: str) -> list[str] | None:
        """A dialogue row whose ``\\v[N]`` control code names a tracked
        list-index readback (``_value_text_choices``, built by
        ``ruby_idioms.match_var_from_list_index``) — GBA has no runtime string variable to
        substitute at that control code the way RMXP does, so this resolves
        it at conversion time into one ``if``-branch per possible value of
        the real var the index was materialized into (Map032 EV9's "Go!
        \\v[3]!" -> "Go! Orchynx!" / "Go! Raptorch!" / "Go! Eletux!", keyed
        off the same ``VAR_TEMP_POKEMON_CHOICE`` the surrounding branches
        already read). Returns ``None`` (falls through to the generic
        dialogue path) unless the text carries exactly one ``\\v[N]`` and N is
        tracked; any per-branch text that itself fails control-code
        translation aborts the whole substitution rather than emitting a
        partial one.
        """
        matches = list(_VALUE_VAR_RE.finditer(raw))
        if len(matches) != 1:
            return None
        var_id = int(matches[0].group(1))
        choice = self._value_text_choices.get(var_id)
        if choice is None:
            return None
        target_var, values = choice
        match = matches[0]
        lines: list[str] = []
        for index, value in enumerate(values):
            substituted = raw[: match.start()] + value + raw[match.end() :]
            translated = translate_text_codes(substituted.strip())
            if translated is None:
                return None
            body = format_pory_dialogue(translated.text)
            auto = ", MSGBOX_AUTOCLOSE" if translated.autoclose else ""
            lines.append(f"if (var({target_var}) == {index}) {{")
            lines.append(f"    msgbox({body}{auto})")
            lines.append("}")
        return lines

    def _emit_give_pokemon(self, const: str, level: int,
                           silent: bool) -> list[str]:
        """Essentials' `pbAddPokemon` / `pbAddPokemonSilent`, natively.

        The loud form is a whole ceremony in Essentials — the species' sprite
        on screen, an "obtained" line over a fanfare, then the nickname prompt
        and a box transfer if the party is full. Vanilla's own gift flow is the
        same sequence of the same primitives, so this mirrors it:
        `showmonpic`/`hidemonpic`, `playfanfare MUS_OBTAIN_ITEM`,
        `Common_EventScript_GetGiftMonPartySlot` / `NameReceivedPartyMon` /
        `NameReceivedBoxMon` / `TransferredToPC` / `NoMoreRoomForPokemon`.

        `givemon` reports where the mon landed in VAR_RESULT
        (MON_GIVEN_TO_PARTY / MON_GIVEN_TO_PC / MON_CANT_GIVE), and the box
        path needs VAR_TEMP_TRANSFERRED_SPECIES set beforehand — vanilla sets
        it before the `givemon`, so this does too.
        """
        # Essentials' party menu is always available; Emerald gates the
        # START-menu POKEMON option on FLAG_SYS_POKEMON_GET
        # (engine/src/start_menu.c:340,359) and givemon -> ScrCmd_createmon
        # never sets it — its only vanilla setter, SetDexPokemonPokenavFlags,
        # is marked unused. Without this the mon is in gPlayerParty but has no
        # menu to appear in.
        if silent:
            return [f"givemon({const}, {level})", "setflag(FLAG_SYS_POKEMON_GET)"]

        nickname = [
            "msgbox(gText_NicknameThisPokemon, MSGBOX_YESNO)",
            "if (var(VAR_RESULT) == YES) {",
        ]
        return [
            "# pbAddPokemon: Essentials shows the species, plays its obtained "
            "jingle and offers a nickname — vanilla's own gift flow, natively",
            f"bufferspeciesname(STR_VAR_1, {const})",
            f"setvar(VAR_TEMP_TRANSFERRED_SPECIES, {const})",
            f"showmonpic({const}, 10, 3)",
            f"givemon({const}, {level})",
            "if (var(VAR_RESULT) == MON_CANT_GIVE) {",
            "    hidemonpic",
            "    goto(Common_EventScript_NoMoreRoomForPokemon)",
            "}",
            "setflag(FLAG_SYS_POKEMON_GET)",
            "playfanfare(MUS_OBTAIN_ITEM)",
            'message(format("{PLAYER} obtained {STR_VAR_1}!"))',
            "waitmessage",
            "waitfanfare",
            "if (var(VAR_RESULT) == MON_GIVEN_TO_PARTY) {",
            *[f"    {ln}" for ln in nickname],
            "        call(Common_EventScript_GetGiftMonPartySlot)",
            "        call(Common_EventScript_NameReceivedPartyMon)",
            "    }",
            "} else {",
            *[f"    {ln}" for ln in nickname],
            "        call(Common_EventScript_NameReceivedBoxMon)",
            "    }",
            "    call(Common_EventScript_TransferredToPC)",
            "}",
            "hidemonpic",
        ]

    # -- array-valued game variables -----------------------------------------

    def _emit_array_literal(
        self, var_id: int, values: tuple[int, ...]
    ) -> list[str] | None:
        """``$game_variables[N] = [0,0,0]`` — bind N scratch vars, seed them.

        `values` comes parsed from `ruby_idioms.ArrayLiteral`; an element
        that wasn't an integer literal never reaches here (the matcher
        misses, and the row queues).
        """
        if not values or len(values) > len(_ARRAY_BUCKET_VARS):
            return None  # wider than the idiom covers — queue, don't guess
        buckets = list(_ARRAY_BUCKET_VARS[:len(values)])
        self._array_vars[var_id] = buckets
        return [f"# $game_variables[{var_id}] = {list(values)} — array-valued "
                f"variable, one scratch var per element",
                *(f"setvar({b}, {v})" for b, v in zip(buckets, values))]

    def _emit_array_bump(self, var_id: int, index_var: int,
                         delta: int) -> list[str] | None:
        """``pbGet(A)[pbGet(B)] += n`` — bump the bucket B selects."""
        buckets = self._array_vars.get(var_id)
        if buckets is None:
            return None
        index_name = self.ctx.var_for_variable(index_var)
        if index_name is None:
            return None
        lines = [f"switch (var({index_name})) {{"]
        for i, bucket in enumerate(buckets):
            lines.append(f"    case {i}:")
            lines.append(f"        addvar({bucket}, {delta})")
        lines.append("}")
        return lines

    def _emit_argmax(self, target_var: int, local: _RubyLocal) -> list[str] | None:
        """``$game_variables[T] = <argmax local>`` — lowest-index-wins argmax.

        Poryscript cannot compare two variables directly, so each `A >= B` is a
        u16 subtract-and-test-sign through VAR_RESULT (subvar's second operand
        goes through VarGet, so a VAR_* id dereferences; A-B wraps past 0x8000
        iff B > A). Ruby's `index(max)` breaks ties toward the LOWEST index,
        which is why the tests are `>=` and are applied last-to-first.
        """
        buckets = self._array_vars.get(local.argmax_of or -1)
        target = self.ctx.var_for_variable(target_var)
        if buckets is None or target is None:
            return None
        if len(buckets) != 3:
            return None  # the >= chain below is written for exactly 3 buckets
        remap = local.remap

        def out(index: int) -> int:
            return remap.get(index, index)

        return [
            f"# argmax over {buckets} (Ruby index(max): ties -> lowest index)"
            + (f", then the source's {remap} remap" if remap else ""),
            f"setvar({target}, {out(2)})",
            f"copyvar(VAR_RESULT, {buckets[1]})",
            f"subvar(VAR_RESULT, {buckets[2]})",
            f"if (var(VAR_RESULT) <= {_SIGN_TEST_MAX}) {{",
            f"    setvar({target}, {out(1)})",
            "}",
            f"copyvar(VAR_RESULT, {buckets[0]})",
            f"subvar(VAR_RESULT, {buckets[1]})",
            f"if (var(VAR_RESULT) <= {_SIGN_TEST_MAX}) {{",
            f"    copyvar(VAR_RESULT, {buckets[0]})",
            f"    subvar(VAR_RESULT, {buckets[2]})",
            f"    if (var(VAR_RESULT) <= {_SIGN_TEST_MAX}) {{",
            f"        setvar({target}, {out(0)})",
            "    }",
            "}",
        ]

    def _emit_starter_selector(self, local_name: str, theo: bool) -> list[str] | None:
        """``pbStarterSelector(x, theo)`` — Uranium's full-screen starter reveal.

        Emits a ``switch`` over the source variable the argument was built
        from, one arm per possible value: the scripted speech as msgboxes and
        the reveal line. The animated background is dropped (operator fidelity
        decision, see reference/starter_selector_scene.json).

        **No sprite here** (user call, 2026-08-01 boot-walk): the reveal used
        to draw the chosen starter with ``showmonpic``, which meant the mon
        popped up twice in the scene — once here and once in the ``pbAddPokemon``
        gift ceremony a few lines later, which shows the same sprite and is the
        one that also runs the nickname prompt. The ceremony keeps the sprite;
        the reveal is speech.

        The surrounding RMXP code-223 tone commands black the screen out for
        the scene's own viewport; the fork's ``fadescreen`` leaves the screen
        black, so this un-fades on the way in and re-fades on the way out,
        leaving the caller's before/after state exactly as it found it.

        Returns ``None`` (caller queues the row) when the local wasn't tracked,
        the scene data isn't wired up, the source variable is unnamed, or any
        arm's species/text doesn't resolve — never a partial scene.
        """
        local = self._ruby_locals.get(local_name)
        scene = self.ctx.starter_scene
        if local is None or not scene:
            return None
        starters = scene.get("starters") or []
        if not starters:
            return None
        # The source variable is Uranium's 1-based selection index; the tracked
        # arithmetic maps it onto the scene's 0-based starter index.
        return self._emit_starter_selector_over(
            local.source_var,
            {v: local.value_for(v) for v in range(1, len(starters) + 1)},
            theo=theo,
        )

    def _emit_starter_selector_over(
        self, source_var: int, value_map: dict[int, int], theo: bool
    ) -> list[str] | None:
        """The reveal itself: one `switch` arm per possible source value.

        `value_map` is source-variable value -> starter index, which is what
        differs between the two call sites — Theo's pick arrives 1-based
        through Ruby arithmetic, the player's already 0-based from the argmax.
        """
        scene = self.ctx.starter_scene
        if not scene or not value_map:
            return None
        var_name = self.ctx.var_for_variable(source_var)
        if var_name is None:
            return None
        starters = scene.get("starters") or []
        by_index = {s["index"]: s for s in starters}
        if not by_index:
            return None

        lines = [
            "# pbStarterSelector: full-screen reveal — speech only; the sprite "
            "is the gift ceremony's job, animated background dropped",
            "fadescreen(FADE_FROM_BLACK)",
            f"switch (var({var_name})) {{",
        ]
        # Any source value that maps outside the starter list means the tracked
        # arithmetic is wrong, so bail rather than emit a broken arm.
        for source_value, starter_index in sorted(value_map.items()):
            starter = by_index.get(starter_index)
            if starter is None:
                return None
            # The species still has to resolve even though the reveal no longer
            # draws it: an arm naming a starter with no staged constant means
            # the scene data and the conversion disagree, which is a broken arm
            # whatever it shows.
            if self.ctx.staged_species_constant(starter["internal_name"]) is None:
                return None
            speech = scene.get("theo_speech") if theo else starter.get("player_speech")
            body: list[str] = []
            for raw in [*(speech or []), starter["reveal"]]:
                result = translate_text_codes(raw)
                if result is None:
                    return None
                body.append(f"msgbox({format_pory_dialogue(result.text)})")
            lines.append(f"    case {source_value}:")
            lines += [f"        {ln}" for ln in body]
        lines.append("}")
        lines.append("fadescreen(FADE_TO_BLACK)")
        return lines


# -- event-level API -----------------------------------------------------------


@dataclass
class TranspiledEvent:
    """One event's output: script blocks (+ any movement blocks), pre-joined."""

    text: str
    unhandled: list[QueueEntry]


def _render_movement(label: str, tokens: list[str]) -> str:
    inner = "\n".join(f"    {t}" for t in tokens)
    return f"movement {label} {{\n{inner}\n}}"


def _render_text_block(label: str, content: str) -> str:
    return f"text {label} {{\n    {content}\n}}"


def _page_label(map_id: int, event: dict, page_no: int) -> str:
    """The canonical page label (= ``metadata_wiring.page_label``): id-based,
    never name-based. Two same-named events on one map (Map002 has two
    "Receptionist TRADE" receptionists) would collide under a name label —
    the event id is the only safe key. map.json wiring references this exact
    form, so no ``normalize_labels`` rewrite is needed on transpiler output.
    The human-readable name rides along as a comment (see transpile_event)."""
    return f"Map{int(map_id):03d}_EV{int(event.get('id', 0)):03d}_Page{page_no}"


_APPLYMOVEMENT_RE = re.compile(
    r"^(?P<indent>\s*)applymovement\((?P<who>[^,]+), (?P<label>[^)]+)\)\s*$"
)


def _insert_terminal_hide_removeobject(
    body: list[str], movements: list[tuple[str, list[str]]], ctx: TranspileContext
) -> list[str]:
    """Free the collision cell a permanently-hidden NPC leaves behind.

    A 209 move route ending in ``set_invisible`` (RGSS Change Opacity to 0)
    only clears the sprite's render flag — pokeemerald's
    ``GetObjectObjectCollidesWith`` (engine/src/event_object_movement.c)
    never checks ``invisible``, only ``active`` and coordinates, so the
    object stays solid forever (Map050 EV020 "Theo" after the starter
    ceremony: (14,16) permanently blocked). If nothing LATER in this same
    emitted body restores that target's visibility (the transient
    hide/reveal idiom used elsewhere, e.g. Map032/Map049), the hide is
    terminal — emit ``removeobject`` once the movement finishes, matching
    the disposition this transpiler already gives RGSS Erase Event (214).

    ``RemoveObjectEventByLocalIdAndMap`` (engine/src/event_object_movement.c)
    both deactivates the object AND ``FlagSet``s the flag off its TEMPLATE —
    the respawn gate every camera update re-checks
    (``TrySpawnObjectEvents``'s ``!FlagGet(template->flagId)``). Porymap
    ships every template with ``"flag": "0"`` (the null sentinel,
    ``FlagGet`` always FALSE), so without a real persistent flag the very
    next step respawns the NPC visible at its start tile — the script never
    re-runs, only the object comes back (the Map050 boot-walk regression).

    So this pass ALSO emits ``setflag(<PLACEHOLDER>)`` immediately before
    ``removeobject`` and records a ``terminal_hide`` trait on the HIDDEN
    event (keyed by (map_id, the hidden event's RMXP id) — not the scripting
    event, which may differ, e.g. the professor's script hides Theo).

    The placeholder, not a real flag name: which flag ultimately belongs here
    depends on the WHOLE map's rock/hidden-actor visibility-flag pool
    (``metadata_wiring._assign_visibility_flags``), decided downstream during
    staging — an event that already gets a real flag from that pool must
    REUSE it (one flag per template, never two), and only an event that would
    otherwise carry ``"0"`` gets a freshly minted ``FLAG_HIDE_*``. This
    module can't see that decision at transpile time, so it can't name the
    flag — ``metadata_wiring.resolve_terminal_hide_setflags`` (called from
    ``stage_slice_scripts.py`` once ``build_object_events`` has decided every
    template's flag) substitutes the placeholder for the real name
    (CLAUDE.md §4.3: metadata_wiring owns this decision alone).
    """
    tokens_by_label = dict(movements)
    lines = list(body)
    i = 0
    while i < len(lines):
        m = _APPLYMOVEMENT_RE.match(lines[i])
        if m is None:
            i += 1
            continue
        who, label = m.group("who"), m.group("label")
        tokens = tokens_by_label.get(label)
        if who == "OBJ_EVENT_ID_PLAYER" or not tokens or tokens[-1] != "set_invisible":
            i += 1
            continue
        restored = False
        for later in lines[i + 1:]:
            m2 = _APPLYMOVEMENT_RE.match(later)
            if m2 is None or m2.group("who") != who:
                continue
            later_tokens = tokens_by_label.get(m2.group("label"))
            if later_tokens and "set_visible" in later_tokens:
                restored = True
                break
        if restored:
            i += 1
            continue
        # who is always OBJ_EVENT_ID_PLAYER (excluded above) or a bare RMXP
        # event id (_emit_show_animation / _emit_move_route never emit any
        # other form) — the HIDDEN event, which may differ from the
        # scripting ctx.event_id (e.g. the professor's script hides Theo).
        target_event_id = int(who)
        ctx.traits.setdefault((ctx.map_id, target_event_id), set()).add("terminal_hide")
        setflag_line = f"setflag({TERMINAL_HIDE_FLAG_PLACEHOLDER})"
        indent = m.group("indent")
        insert_at = i + 1
        if insert_at < len(lines) and lines[insert_at].strip() == "waitmovement(0)":
            insert_at += 1
            extra = [f"{indent}{setflag_line}", f"{indent}removeobject({who})"]
        else:
            # No paired 210 wait was emitted (its RGSS command was
            # skipped/queued/absent) — synthesize the wait so the hide's
            # movement plays out before the object is torn down, rather than
            # despawning it mid-walk.
            extra = [
                f"{indent}waitmovement(0)",
                f"{indent}{setflag_line}",
                f"{indent}removeobject({who})",
            ]
        lines[insert_at:insert_at] = extra
        i = insert_at + len(extra)
    return lines


def transpile_page(
    page: dict, ctx: TranspileContext, page_label: str
) -> tuple[list[str], list[tuple[str, list[str]]], list[tuple[str, str]],
           list[tuple[str, list[str]]], list[str]]:
    """Body lines + movement blocks + text blocks + hoisted label blocks +
    auxiliary blocks for one page. Queue entries land in ctx.

    The fourth element is the RMXP-label basic-block split (see
    `hoistable_label_region`): `(block_label, body_lines)` pairs the caller
    renders as sibling `script` blocks. They are entered by `goto` from this
    page with its script context (and its `lock`) already live, so they take
    the trigger's *epilogue* only — never its `lock` prologue.

    The fifth element is `emitter.aux_blocks` — fully-rendered sibling blocks
    (e.g. a `mart { ... }` list) an idiom needed alongside the page's script
    block; the caller appends them to its output verbatim.
    """
    commands = page.get("list", [])
    ctx.page_graphic = (page.get("graphic") or {}).get("character_name") or ""
    region = hoistable_label_region(commands)
    hoisted: list[tuple[str, list[str]]] = []
    emitter = _PageEmitter(ctx, page_label)
    emitter.page_commands = commands
    if region is None:
        loop = loop_label_region(commands)
        if loop is not None:
            emitter.loop_labels.add(str(commands[loop[0]].get("parameters", [""])[0]))

    if region is not None:
        label_index, region_end = region
        name = commands[label_index].get("parameters", [""])[0]
        block_label = f"{page_label}_{_label_block_suffix(name)}"
        emitter.label_blocks[str(name)] = block_label
        # The region leaves the main page entirely; the label row stays put and
        # emits the `goto` that enters it (so does every 119 jump).
        main = commands[:label_index + 1] + commands[region_end:]
        region_cmds = commands[label_index + 1:region_end]
    else:
        main, region_cmds, block_label = commands, [], ""

    body = emitter.emit_nodes(parse_tree(main))
    body = _insert_terminal_hide_removeobject(body, emitter.movements, ctx)
    if region_cmds:
        # Same emitter: movement/text blocks and the per-page choice counter
        # stay in one namespace, so a hoisted block can't collide with the
        # main body's labels.
        hoisted_body = emitter.emit_nodes(parse_tree(region_cmds))
        hoisted_body = _insert_terminal_hide_removeobject(hoisted_body, emitter.movements, ctx)
        hoisted.append((block_label, hoisted_body))
    return body, emitter.movements, emitter.text_blocks, hoisted, emitter.aux_blocks


def transpile_event(map_id: int, event: dict, ctx: TranspileContext) -> TranspiledEvent:
    """Transpile every page of one map event into script (+movement) blocks."""
    ctx.map_id = map_id
    ctx.event_id = event.get("id")
    ctx.event_name = event.get("name", "")
    ctx.event_x = event.get("x")
    ctx.event_y = event.get("y")
    ctx.common_event_id = None
    before = len(ctx.unhandled)

    name = _label_name(event.get("name", ""))
    blocks: list[str] = []
    # Two different page numberings meet here and must not be conflated
    # (#98). Script block LABELS are 1-based (`..._Page1` is the first
    # page) and are load-bearing symbols -- renumbering them would rename
    # every block in the corpus. The QUEUE's `page` field is 0-based, to
    # match the manifest `row_id`'s `pN` component (`schema.page_row_id`),
    # which is what the disposition pass joins on.
    for page_idx, page in enumerate(event.get("pages", [])):
        page_no = page_idx + 1
        ctx.page_no = page_idx
        label = _page_label(map_id, event, page_no)
        trigger = page.get("trigger")
        epilogue = {ACTION_BUTTON_TRIGGER: "release", 1: "release",
                    2: "release", 3: "releaseall"}.get(trigger)
        ctx.exit_epilogue = epilogue
        try:
            body, movements, text_blocks, hoisted, aux_blocks = transpile_page(page, ctx, label)
        finally:
            ctx.exit_epilogue = None
        # Hoisted label blocks are entered by `goto` with the page's lock
        # already held, so they need the epilogue but not the prologue. Without
        # it a `goto`-ed block would end without ever releasing — the exact
        # freeze the Map050 EV005 hand conversion had to patch by hand.
        if body and trigger == ACTION_BUTTON_TRIGGER:
            body = ["lock", "faceplayer", *body, "release"]
        elif body and trigger in (1, 2):
            # player-touch / event-touch cutscene: freeze the player while
            # the script runs (validated Opus output, e.g. Map001 doormats).
            body = ["lock", *body, "release"]
        elif body and trigger == 3:
            # autorun cutscene: invoked from an ON_FRAME_TABLE map script
            # (metadata_wiring, another agent's emitter); vanilla ON_FRAME
            # cutscenes use lockall/releaseall, not lock/release.
            body = ["lockall", *body, "releaseall"]
        body = body or []
        body.append("end")
        inner = "\n".join(f"    {ln}" for ln in body)
        header = f"# {name}\n" if name and not name.startswith("EV") else ""
        blocks.append(f"{header}script {label} {{\n{inner}\n}}")
        for h_label, h_body in hoisted:
            # A region that ended on RMXP's Exit Event Processing already
            # emitted its own `end`; the epilogue has to go BEFORE it, or the
            # release is dead code after the terminator.
            if h_body and h_body[-1] in ("end", "return"):
                # A trailing 115 already emitted its own release before `end`.
                already = len(h_body) >= 2 and h_body[-2] == epilogue
                h_body = [*h_body[:-1],
                          *([epilogue] if epilogue and not already else []),
                          h_body[-1]]
            else:
                h_body = [*h_body, *([epilogue] if epilogue else []), "end"]
            h_inner = "\n".join(f"    {ln}" for ln in h_body)
            blocks.append(f"script {h_label} {{\n{h_inner}\n}}")
        for m_label, tokens in movements:
            blocks.append(_render_movement(m_label, tokens))
        for t_label, content in text_blocks:
            blocks.append(_render_text_block(t_label, content))
        blocks.extend(aux_blocks)

    return TranspiledEvent(
        text="\n\n".join(blocks),
        unhandled=ctx.unhandled[before:],
    )


def transpile_common_event(ce: dict, ctx: TranspileContext) -> TranspiledEvent:
    """Transpile one common event (flat `list`, no pages, no trigger wrapper).

    Self-switch semantics don't exist here (no owning event) — those commands
    queue. The block label matches the `call CommonEvent_{id:03d}` form the
    map-event emitters produce.
    """
    ce_id = int(ce.get("id", 0))
    ctx.map_id = 0
    ctx.event_id = None
    ctx.event_name = ce.get("name", "")
    ctx.event_x = None
    ctx.event_y = None
    ctx.common_event_id = ce_id
    ctx.page_no = 0  # 0-based, matching the manifest row_id (#98)
    before = len(ctx.unhandled)

    label = f"CommonEvent_{ce_id:03d}"
    body, movements, text_blocks, hoisted, aux_blocks = transpile_page(
        {"list": ce.get("list", [])}, ctx, label)
    body = body or []
    body.append("return")  # called script — return to the caller, never `end`
    inner = "\n".join(f"    {ln}" for ln in body)
    name = _label_name(ce.get("name", ""))
    header = f"# {name}\n" if name else ""
    blocks = [f"{header}script {label} {{\n{inner}\n}}"]
    for h_label, h_body in hoisted:
        # A called script never `end`s — a hoisted region's Exit Event
        # Processing already became `return` (EXIT_EVENT checks
        # ctx.common_event_id), so only a fall-through region needs one added.
        if not h_body or h_body[-1] != "return":
            h_body = [*h_body, "return"]
        h_inner = "\n".join(f"    {ln}" for ln in h_body)
        blocks.append(f"script {h_label} {{\n{h_inner}\n}}")
    for m_label, tokens in movements:
        blocks.append(_render_movement(m_label, tokens))
    for t_label, content in text_blocks:
        blocks.append(_render_text_block(t_label, content))
    blocks.extend(aux_blocks)

    return TranspiledEvent(
        text="\n\n".join(blocks),
        unhandled=ctx.unhandled[before:],
    )
