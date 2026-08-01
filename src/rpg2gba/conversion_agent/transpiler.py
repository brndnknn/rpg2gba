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
    _label_name,
    format_pory_dialogue,
    translate_text_codes,
)
from rpg2gba.conversion_agent.flag_registry import (
    FlagRegistry,
    resolve_switch_flag,
    resolve_variable_var,
)
from rpg2gba.pbs_converter._naming import to_constant

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

# Kernel.pbReceiveItem(::PBItems::SYMBOL[, qty]) — give-item-with-fanfare branch
# (Map032 EV27/EV9, Map049 EV18). Same family as deterministic.classify_ground_item's
# pbItemBall idiom; qty is optional (bare RARECANDY/LAVACOOKIE vs. POKeBALL,5).
_RECEIVE_ITEM_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbReceiveItem\(\s*::PBItems::(\w+)\s*(?:,\s*(\d+)\s*)?\)\s*$"
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
# HEAD — see _emit_show_animation). Only the two emote ids proven on the slice;
# any other animation_id (e.g. the corpus's 104/18 flourishes) still queues.
_EMOTE_MOVEMENT_LABELS = {
    17: "Common_Movement_ExclamationMark",  # movement.inc:8 (EM Exclamation)
    19: "Common_Movement_QuestionMark",  # movement.inc:4 (EM Interrogation)
}

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
_HAS_SPECIES_RE = re.compile(r"^\s*pbHasSpecies\?\(\s*::PBSpecies::([A-Za-z0-9_]+)\s*\)\s*$")

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
_TRAINER_PC_RE = re.compile(r"^\s*(?:Kernel\.)?pbTrainerPC\s*$")

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
_RUBY_LOCAL_PBGET_RE = re.compile(r"^\s*([a-z_]\w*)\s*=\s*pbGet\(\s*(\d+)\s*\)\s*$")
_RUBY_LOCAL_ADDSUB_RE = re.compile(r"^\s*([a-z_]\w*)\s*(\+|-)=\s*(\d+)\s*$")
_RUBY_LOCAL_WRAP_RE = re.compile(
    r"^\s*([a-z_]\w*)\s*=\s*(-?\d+)\s+if\s+\1\s*==\s*(-?\d+)\s*$"
)
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
_ARRAY_LITERAL_RE = re.compile(
    r"^\s*\$game_variables\[\s*(\d+)\s*\]\s*=\s*\[\s*([\d\s,]*?)\s*\]\s*$"
)
_ARRAY_INDEXED_BUMP_RE = re.compile(
    r"^\s*pbGet\(\s*(\d+)\s*\)\[\s*pbGet\(\s*(\d+)\s*\)\s*\]\s*\+=\s*(\d+)\s*$"
)
_ARRAY_ARGMAX_RE = re.compile(
    r"^\s*([a-z_]\w*)\s*=\s*pbGet\(\s*(\d+)\s*\)\.index\(\s*pbGet\(\s*(\d+)\s*\)\.max\s*\)\s*$"
)
_RUBY_IF_EQ_RE = re.compile(r"^\s*(?:els)?if\s+([a-z_]\w*)\s*==\s*(-?\d+)\s*$")
_RUBY_ASSIGN_CONST_RE = re.compile(r"^\s*([a-z_]\w*)\s*=\s*(-?\d+)\s*$")
_RUBY_END_RE = re.compile(r"^\s*end\s*$")
_VAR_ASSIGN_LOCAL_RE = re.compile(
    r"^\s*\$game_variables\[\s*(\d+)\s*\]\s*=\s*([a-z_]\w*)\s*$"
)

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

# Essentials inline-choice text escape (SLICE1_TODO #17): a Show Text message
# trailing \ch[var,ifCancel,opt1,opt2,...] (reference/scripts_dump/059_Messages.rb
# :1218-1225, 1360-1362, 1429-1465). Split on the literal marker, not a single
# regex over the whole payload — option text is free-form (may itself contain
# escapes/brackets from embedded color codes) and the true end of the command
# is "the last ']' in the message" (verified tail-only corpus shape), not the
# first one a naive `\[.*?\]` would stop at.
_CH_MARK = "\\ch["
# Cosmetic color-code carriers inside option labels — stripped, never queued
# for these two shapes specifically (same disposition as _COLOR_CODE_RE in
# deterministic.py, applied here to \ch's own comma-split option text).
_CH_COLOR_TAG_RE = re.compile(r"<c2=[0-9a-fA-F]+>")
_CH_LEGACY_COLOR_RE = re.compile(r"\\c\[\d+\]")
# After stripping the two shapes above, any surviving backslash or angle
# bracket is an unrecognized tag — queue the whole command rather than emit
# mystery text into a menu option.
_CH_RESIDUAL_TAG_RE = re.compile(r"[\\<>]")

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

    # SPECIES_* constants that species_converter.stage has actually staged
    # into the fork (species_manifest.json), i.e. that the fork's headers
    # really define. A name resolving in `species` above is NOT sufficient
    # on its own — most of Uranium's ~166 needs_engine species are id-mapped
    # but never staged, and emitting their constant would be an invented
    # symbol the gate correctly rejects. Populated by the driver.
    staged_species: frozenset[str] = field(default_factory=frozenset)

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

    # per-event cursor, set by transpile_event / transpile_common_event
    map_id: int = 0
    event_id: int | None = None
    event_name: str = ""
    event_x: int | None = None
    event_y: int | None = None
    page_no: int = 0
    common_event_id: int | None = None

    # Per-event traits recorded during transpile (e.g. "smashable_rock" from
    # the rock-smash native idiom below), keyed by (map_id, event_id). The
    # driver reads this to write the Map{id:03d}.traits.json sidecar — a
    # fixed schema shared with a downstream consumer (metadata_wiring.py /
    # stage_slice_scripts.py, owned by a different agent); don't rename.
    traits: dict[tuple[int, int], set[str]] = field(default_factory=dict)

    def record_trait(self, trait: str) -> None:
        """Record a trait on the event currently being transpiled. No-op in
        a common event (no owning event id to key by — see ``event_id``)."""
        if self.event_id is None:
            return
        self.traits.setdefault((self.map_id, self.event_id), set()).add(trait)

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

    def staged_species_constant(self, internal_name: str) -> str | None:
        """Resolve a Uranium species internal name to its SPECIES_* constant,
        but ONLY if that species has actually been staged into the fork.
        ``None`` (caller queues) for an id-map miss OR an id-map hit that
        isn't in ``staged_species`` — the latter is the important case: a
        species like URAYNE resolves fine through the id map but was never
        staged, so its constant doesn't exist in the fork's headers."""
        const = self.species.get(internal_name)
        if const is None or const not in self.staged_species:
            return None
        return const


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
                nodes.append(TextRun(cmd, idx, text="".join(str(s) for s in parts)))
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
    35: "lock_facing_direction", 36: "unlock_facing_direction",
    39: "set_fixed_priority", 40: "clear_fixed_priority",
}

# SOFT-C drops (moveroute_coverage.py dispositions): timing/physics toggles
# with no per-step GBA analog whose removal doesn't change where anyone ends
# up. 30 frequency · 37/38 through on/off (Essentials door-walk plumbing) ·
# 43 blend · 44 SE (audio is a visible drop elsewhere too).
_MOVE_DROP_CODES = frozenset({30, 37, 38, 43, 44})

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


def route_tokens(route: dict) -> list[str] | None:
    """Movement tokens for a route, or None if any step is outside the tier."""
    if route.get("repeat"):
        return None  # ambient looping route — no movement-block equivalent
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
        self._last_route_ok = False  # was the most recent 209 emitted?
        self._choice_count = 0  # running per-page \ch counter (label uniqueness)
        # Ruby locals built across 355/655 rows: name -> (source_var_id, offset,
        # wrap). Only the shapes the starter-selector idiom needs; see
        # _RUBY_LOCAL_PBGET_RE and friends.
        self._ruby_locals: dict[str, _RubyLocal] = {}
        # RMXP label name -> hoisted script block label, filled by
        # transpile_page for the one region it could prove terminates.
        # Anything not in here queues, both at the label and at every jump.
        self.label_blocks: dict[str, str] = {}
        # Uranium variable id -> the scratch vars standing in for an array
        # value it was assigned (see _emit_array_literal).
        self._array_vars: dict[int, list[str]] = {}
        # Open `if x==A` remap arm: (local name, tested value, assigned value).
        self._pending_remap: tuple[str, int, int | None] | None = None

    # -- leaf emitters -------------------------------------------------------

    def emit_nodes(self, nodes: list[Node]) -> list[str]:
        lines: list[str] = []
        for node in _merge_consecutive_routes(nodes):
            lines.extend(self.emit_node(node))
        return lines

    def emit_node(self, node: Node) -> list[str]:
        ctx = self.ctx
        cmd = node.cmd
        code = cmd.get("code", 0)
        params = cmd.get("parameters", [])

        if isinstance(node, TextRun):
            if _CH_MARK in node.text:
                return self._emit_inline_choice(node)
            result = translate_text_codes(node.text.strip())
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
            return ["return" if ctx.common_event_id is not None else "end"]
        if code == ERASE_EVENT:
            if ctx.event_id is None:
                return [ctx.queue(node.index, code, "erase event in a common event")]
            return [f"removeobject({ctx.event_id})"]
        if code == CALL_COMMON_EVENT:
            ce_id = params[0] if params else 0
            if not isinstance(ce_id, int) or ce_id <= 0:
                return [ctx.queue(node.index, code, "call common event with bad id")]
            return [f"call CommonEvent_{ce_id:03d}"]
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
            return [
                f"warp(MAP_URANIUM_{params[1]}, {params[2]}, {params[3]})",
                "waitstate",
            ]
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

    # -- structured emitters -------------------------------------------------

    def _emit_if(self, node: IfNode) -> list[str]:
        door = self._emit_door_idiom(node)
        if door is not None:
            return door
        give_item = self._emit_give_item_idiom(node)
        if give_item is not None:
            return give_item
        guard = self._emit_unsatisfiable_numeric_guard(node)
        if guard is not None:
            return guard
        rock_smash = self._emit_rock_smash_idiom(node)
        if rock_smash is not None:
            return rock_smash
        has_species = self._emit_has_species_idiom(node)
        if has_species is not None:
            return has_species
        canlose_battle = self._emit_canlose_trainer_battle_idiom(node)
        if canlose_battle is not None:
            return canlose_battle
        randomizer = self._emit_randomizer_branch(node)
        if randomizer is not None:
            return randomizer
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

    def _emit_give_item_idiom(self, node: IfNode) -> list[str] | None:
        """``Kernel.pbReceiveItem(::PBItems::SYMBOL[, qty])`` give-item-with-
        fanfare branch (Map032 EV27/EV9, Map049 EV18). Resolved through
        ``ctx.items`` — the same Essentials-symbol -> ``ITEM_*`` table
        ``deterministic._load_item_symbols``/``load_context`` builds for the
        mart/ground-item classifiers (reused via the context, not re-derived
        here). Returns ``None`` (falls through to the generic script-condition
        queue) for any other script call or an unresolved item symbol."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
            return None
        m = _RECEIVE_ITEM_RE.match(params[1])
        if not m:
            return None
        symbol, qty = m.group(1), m.group(2)
        const = self.ctx.items.get(symbol)
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

    def _emit_inline_choice(self, node: TextRun) -> list[str]:
        """Essentials' inline ``\\ch[var,ifCancel,opt1,opt2,...]`` text escape
        (SLICE1_TODO #17) — a Show Text message whose choice menu is embedded
        in the text itself rather than a separate 102 command. Fork-native
        ``dynmultichoice`` (asm/macros/event.inc:1932) + a ``msgbox`` for the
        prompt. See the module-level ``_CH_MARK``/``_CH_*_RE`` comments for
        the parsing rationale. Queues (whole command, nothing emitted) for:
        more than one ``\\ch[`` marker, text after the closing ``]`` (must be
        the tail), too few comma fields, a non-integer var/ifCancel, a
        negative ifCancel (unrepresentable in a GBA u16 var), an unresolvable
        var id, or a residual unknown tag in a label after color-code strip.
        """
        text = node.text
        if text.count(_CH_MARK) != 1:
            return [self.ctx.queue(
                node.index, SHOW_TEXT,
                f"inline choice: expected exactly one \\ch[...] marker, "
                f"found {text.count(_CH_MARK)}: {text[:120]!r}",
            )]
        mark_idx = text.index(_CH_MARK)
        inner_start = mark_idx + len(_CH_MARK)
        close_idx = text.rfind("]")
        if close_idx < inner_start:
            return [self.ctx.queue(
                node.index, SHOW_TEXT,
                f"inline choice: no closing ']' for \\ch[...]: {text[:120]!r}",
            )]
        if text[close_idx + 1 :].strip():
            return [self.ctx.queue(
                node.index, SHOW_TEXT,
                f"inline choice: trailing text after \\ch[...] block: {text[:120]!r}",
            )]
        prompt_text = text[:mark_idx]
        inner = text[inner_start:close_idx]

        fields = [f.strip() for f in inner.split(",")]
        if len(fields) < 3:
            return [self.ctx.queue(
                node.index, SHOW_TEXT,
                f"inline choice: too few \\ch[...] fields ({len(fields)}): {inner!r}",
            )]
        var_str, if_cancel_str, *option_texts = fields
        try:
            var_id = int(var_str)
            if_cancel = int(if_cancel_str)
        except ValueError:
            return [self.ctx.queue(
                node.index, SHOW_TEXT,
                f"inline choice: non-integer var/ifCancel in \\ch[{inner}]",
            )]
        if if_cancel < 0:
            return [self.ctx.queue(
                node.index, SHOW_TEXT,
                f"inline choice: negative ifCancel ({if_cancel}) is "
                f"unrepresentable in a GBA u16 var — \\ch[{inner}]",
            )]

        options: list[str] = []
        for opt in option_texts:
            stripped = _CH_COLOR_TAG_RE.sub("", opt)
            stripped = _CH_LEGACY_COLOR_RE.sub("", stripped)
            stripped = stripped.strip()
            if _CH_RESIDUAL_TAG_RE.search(stripped):
                return [self.ctx.queue(
                    node.index, SHOW_TEXT,
                    f"inline choice: residual unknown tag in option {opt!r} "
                    f"after color-code strip — \\ch[{inner}]",
                )]
            options.append(stripped)

        var_name = self.ctx.var_for_variable(var_id)
        if var_name is None:
            return [self.ctx.queue(
                node.index, SHOW_TEXT,
                f"inline choice: variable {var_id} is unnamed — cannot mint a VAR_*",
            )]

        result = translate_text_codes(prompt_text.strip())
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
                f"    setvar({var_name}, {if_cancel - 1})",
                "} else {",
                f"    copyvar({var_name}, VAR_RESULT)",
                "}",
            ]
        return lines

    def _emit_choice(self, node: ChoiceNode) -> list[str]:
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
        shape as a 209 move route. Any other animation id (the corpus also
        has 104/18 flourishes with no native analog) still queues."""
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or not all(isinstance(v, int) for v in params[:2]):
            return [self.ctx.queue(node.index, SHOW_ANIMATION, "bad 207 params")]
        target_id, animation_id = params[0], params[1]
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
            # Self-target animation — no clean self-reference in v1 (not
            # exercised on the slice); queue rather than guess.
            return [self.ctx.queue(
                node.index, SHOW_ANIMATION,
                "show animation on self (target 0) — no v1 self-reference",
            )]
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
        becomes the ``RPG2GBA_SetObjectEventGfx`` special —
        VAR_0x8004 = local id, VAR_0x8005 = OBJ_EVENT_GFX_*
        (engine/src/event_object_movement.c, sentinel-fenced).

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
            entry = self.ctx.npc_gfx.get(sheet)
            if not entry:
                self._last_route_ok = False
                return [self.ctx.queue(
                    node.index, SET_MOVE_ROUTE,
                    f"change-graphic to unmapped sheet {sheet!r} — add it to "
                    f"reference/npc_gfx_map.json",
                )]
            lines += [
                f"setvar(VAR_0x8004, {who})",
                f"setvar(VAR_0x8005, {entry})",
                "special(RPG2GBA_SetObjectEventGfx)",
            ]
            # RMXP Change Graphic sets sheet AND (direction, pattern) together,
            # and props use those to select a STATE: Map050's pokéball machine
            # swaps to its own sheet twice, changing only direction/pattern, so
            # a sheet-only conversion is a visible no-op. Direction has an exact
            # analog — the object's facing picks the same row of the converted
            # 4-direction sheet — so emit it as its own movement block.
            # `pattern` (the frame within a row) has none: the fork animates
            # frames itself and no movement action selects one. A swap that
            # moves ONLY the pattern is therefore still a silent drop; it gets
            # a queue entry rather than pretending (§4.5).
            direction = params[2] if len(params) > 2 else None
            pattern = params[3] if len(params) > 3 else None
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
        from rpg2gba.conversion_agent.deterministic import _DIALOGUE_STRIP_RE
        params = node.cmd.get("parameters", [])
        text = params[0] if params and isinstance(params[0], str) else ""
        if _DIALOGUE_STRIP_RE.match(text):
            return []

        # pbPhoneRegisterNPC(...) — phone-directory registration, cosmetic on
        # the GBA (see _PHONE_REGISTER_NPC_STRIP_RE). Breadcrumb, no queue.
        if _PHONE_REGISTER_NPC_STRIP_RE.match(text):
            return ["# phone: pbPhoneRegisterNPC stripped (slice1)"]

        # pbCaveEntrance — pre-warp fade choreography subsumed by the native
        # warp (see _CAVE_ENTRANCE_STRIP_RE). Breadcrumb, no queue.
        if _CAVE_ENTRANCE_STRIP_RE.match(text):
            return ["# cave transition: pbCaveEntrance subsumed by native warp fade"]

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

        # -- Ruby locals feeding pbStarterSelector ---------------------------
        # These three rows emit nothing on their own; they build the argument
        # the selector call below consumes. Tracked, not queued.
        m = _RUBY_LOCAL_PBGET_RE.match(text)
        if m:
            self._ruby_locals[m.group(1)] = _RubyLocal(source_var=int(m.group(2)))
            return []

        m = _RUBY_LOCAL_ADDSUB_RE.match(text)
        if m and m.group(1) in self._ruby_locals:
            local = self._ruby_locals[m.group(1)]
            delta = int(m.group(3)) * (1 if m.group(2) == "+" else -1)
            self._ruby_locals[m.group(1)] = _RubyLocal(
                local.source_var, local.offset + delta, local.wrap
            )
            return []

        m = _RUBY_LOCAL_WRAP_RE.match(text)
        if m and m.group(1) in self._ruby_locals:
            local = self._ruby_locals[m.group(1)]
            self._ruby_locals[m.group(1)] = _RubyLocal(
                local.source_var, local.offset, (int(m.group(3)), int(m.group(2)))
            )
            return []

        # -- array-valued game variable (the aptitude tally) ------------------
        m = _ARRAY_LITERAL_RE.match(text)
        if m:
            return self._emit_array_literal(int(m.group(1)), m.group(2))

        m = _ARRAY_INDEXED_BUMP_RE.match(text)
        if m:
            return self._emit_array_bump(
                int(m.group(1)), int(m.group(2)), int(m.group(3)))

        m = _ARRAY_ARGMAX_RE.match(text)
        if m and m.group(2) == m.group(3) and int(m.group(2)) in self._array_vars:
            # Value lands in the local; nothing is emitted until the local is
            # written back to a real variable (_VAR_ASSIGN_LOCAL_RE below).
            self._ruby_locals[m.group(1)] = _RubyLocal(
                source_var=int(m.group(2)), argmax_of=int(m.group(2)))
            return []

        m = _RUBY_ASSIGN_CONST_RE.match(text)
        if m and self._pending_remap is not None:
            # Body of the `if x==A / x=B` remap opened below.
            name, value = m.group(1), int(m.group(2))
            local = self._ruby_locals.get(name)
            if local is not None and local.argmax_of is not None:
                self._pending_remap = (name, self._pending_remap[1], value)
                local.remap[self._pending_remap[1]] = value
                return []

        m = _RUBY_IF_EQ_RE.match(text)
        if m:
            local = self._ruby_locals.get(m.group(1))
            if local is not None and local.argmax_of is not None:
                # `if x==1 / x=0 / elsif x==0 / x=1 / end` is a value
                # permutation over the argmax result, not control flow — the
                # arms are mutually exclusive tests of the same local.
                self._pending_remap = (m.group(1), int(m.group(2)), None)
                return []

        if _RUBY_END_RE.match(text) and self._pending_remap is not None:
            self._pending_remap = None
            return []

        m = _VAR_ASSIGN_LOCAL_RE.match(text)
        if m:
            local = self._ruby_locals.get(m.group(2))
            if local is not None and local.argmax_of is not None:
                return self._emit_argmax(int(m.group(1)), local)

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

        return None

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

    def _emit_array_literal(self, var_id: int, body: str) -> list[str] | None:
        """``$game_variables[N] = [0,0,0]`` — bind N scratch vars, seed them."""
        try:
            values = [int(v) for v in body.split(",") if v.strip() != ""]
        except ValueError:
            return None
        if not values or len(values) > len(_ARRAY_BUCKET_VARS):
            return None  # wider than the idiom covers — queue, don't guess
        buckets = list(_ARRAY_BUCKET_VARS[:len(values)])
        self._array_vars[var_id] = buckets
        return [f"# $game_variables[{var_id}] = {values} — array-valued "
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
        from, one arm per possible value: the scripted speech as msgboxes, the
        chosen starter's front sprite via native ``showmonpic``, and the reveal
        line. The animated background is dropped (operator fidelity decision,
        see reference/starter_selector_scene.json).

        The surrounding RMXP code-223 tone commands black the screen out for
        the scene's own viewport; the fork's ``fadescreen`` leaves the screen
        black, which would hide the sprite box entirely — so this un-fades on
        the way in and re-fades on the way out, leaving the caller's before/
        after state exactly as it found it.

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
            "# pbStarterSelector: full-screen reveal — speech + native "
            "showmonpic; animated background dropped",
            "fadescreen(FADE_FROM_BLACK)",
            f"switch (var({var_name})) {{",
        ]
        # Any source value that maps outside the starter list means the tracked
        # arithmetic is wrong, so bail rather than emit a broken arm.
        for source_value, starter_index in sorted(value_map.items()):
            starter = by_index.get(starter_index)
            if starter is None:
                return None
            const = self.ctx.staged_species_constant(starter["internal_name"])
            if const is None:
                return None
            speech = scene.get("theo_speech") if theo else starter.get("player_speech")
            body = [f"showmonpic({const}, 10, 3)"]
            for raw in [*(speech or []), starter["reveal"]]:
                result = translate_text_codes(raw)
                if result is None:
                    return None
                body.append(f"msgbox({format_pory_dialogue(result.text)})")
            body.append("hidemonpic")
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


def transpile_page(
    page: dict, ctx: TranspileContext, page_label: str
) -> tuple[list[str], list[tuple[str, list[str]]], list[tuple[str, str]],
           list[tuple[str, list[str]]]]:
    """Body lines + movement blocks + text blocks + hoisted label blocks for
    one page. Queue entries land in ctx.

    The fourth element is the RMXP-label basic-block split (see
    `hoistable_label_region`): `(block_label, body_lines)` pairs the caller
    renders as sibling `script` blocks. They are entered by `goto` from this
    page with its script context (and its `lock`) already live, so they take
    the trigger's *epilogue* only — never its `lock` prologue.
    """
    commands = page.get("list", [])
    region = hoistable_label_region(commands)
    hoisted: list[tuple[str, list[str]]] = []
    emitter = _PageEmitter(ctx, page_label)

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
    if region_cmds:
        # Same emitter: movement/text blocks and the per-page choice counter
        # stay in one namespace, so a hoisted block can't collide with the
        # main body's labels.
        hoisted.append((block_label, emitter.emit_nodes(parse_tree(region_cmds))))
    return body, emitter.movements, emitter.text_blocks, hoisted


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
    for page_no, page in enumerate(event.get("pages", []), start=1):
        ctx.page_no = page_no
        label = _page_label(map_id, event, page_no)
        body, movements, text_blocks, hoisted = transpile_page(page, ctx, label)
        trigger = page.get("trigger")
        # Hoisted label blocks are entered by `goto` with the page's lock
        # already held, so they need the epilogue but not the prologue. Without
        # it a `goto`-ed block would end without ever releasing — the exact
        # freeze the Map050 EV005 hand conversion had to patch by hand.
        epilogue = {ACTION_BUTTON_TRIGGER: "release", 1: "release",
                    2: "release", 3: "releaseall"}.get(trigger)
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
                h_body = [*h_body[:-1], *([epilogue] if epilogue else []),
                          h_body[-1]]
            else:
                h_body = [*h_body, *([epilogue] if epilogue else []), "end"]
            h_inner = "\n".join(f"    {ln}" for ln in h_body)
            blocks.append(f"script {h_label} {{\n{h_inner}\n}}")
        for m_label, tokens in movements:
            blocks.append(_render_movement(m_label, tokens))
        for t_label, content in text_blocks:
            blocks.append(_render_text_block(t_label, content))

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
    ctx.page_no = 1
    before = len(ctx.unhandled)

    label = f"CommonEvent_{ce_id:03d}"
    body, movements, text_blocks, hoisted = transpile_page(
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

    return TranspiledEvent(
        text="\n\n".join(blocks),
        unhandled=ctx.unhandled[before:],
    )
