"""Script-call-head extractors for the generic beat floor (REDERIVATION_PLAN.md
§16.3 C4, "C4 shape" (a)).

One extractor per Ruby call head found in a code-355/655 block
(`census._script_head`, `Kernel.` already normalized away), not one per
command code -- a single 355/655 block can itself contain several complete
Ruby statements (`_split_statements` below), and every statement's head must
resolve or the row is refused. A head with no extractor -- or a statement
with no recognizable head at all (`census._script_head` returns `None`,
usually a stray fragment of embedded control flow: `if`/`elsif`/`end`, a
loop variable, C8's problem, not C4's) -- refuses the row.

State-writing heads (`pbSetSelfSwitch`, `setTempSwitchOn`, `pbSet`, raw
`$game_switches`/`$game_variables` assignment) return an EMPTY result on
purpose: `story_state.extract` already turns these into the row's
`switch_write`/`var_write`/`self_switch_write` assertions (or refuses the
row itself on a non-constant write), and re-deriving them here would be a
second, divergent source of truth for the same fact (CLAUDE.md §4.3).
"""
from __future__ import annotations

import re

from rpg2gba.beat_floor.assertion import (
    ExtractContext,
    ExtractResult,
    FloorAssertion,
    FloorRefusal,
    ScriptHeadExtractor,
    make_params,
)
from rpg2gba.chapter_atlas.census import _script_head
from rpg2gba.conversion_agent.deterministic import _PBPOKEMART_ITEM_RE, _PBPOKEMART_LIST_RE
from rpg2gba.conversion_agent.transpiler import _ADD_POKEMON_RE, _RECEIVE_ITEM_RE

CODE_SCRIPT = 355


# --- statement splitting --------------------------------------------------

def _split_statements(text: str) -> list[str]:
    """Split a joined 355/655 block into top-level Ruby statements.

    Most blocks are ONE call whose own string argument happens to wrap
    across several raw text rows (`pbPhoneRegisterBattle(_I("...\\n...a
    multi-line loss quote..."))` -- 133_PScreen_Phone.rb:91); splitting on
    every raw newline would shred that single call into several bogus
    "statements" whose heads are mid-sentence words. Others really are
    several complete statements, one per raw row
    (`pbNoticePlayer(event)` / `pbTrainerIntro(:X)` / `setTempSwitchOn("A")`).

    The two are told apart by paren depth alone: a newline only starts a new
    statement once every `(` opened so far in this block has been closed.
    Verified against the CH01-CH05 corpus's two representative shapes
    (`pbPokemonMart([\\nPBItems::X,\\n...])`, whose surrounding `(` stays
    open across every `PBItems::` line despite the inner `[...]`, and the
    phone-quote wrap above) -- both collapse to one statement, as they must.
    An unclosed trailing `(` folds the remainder of the block into one
    statement rather than dropping any of it (fails safe, not silent,
    CLAUDE.md §4.5).
    """
    statements: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch == "\n" and depth <= 0:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        buf.append(ch)
    stmt = "".join(buf).strip()
    if stmt:
        statements.append(stmt)
    return statements


def extract_script(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    assertions: list[FloorAssertion] = []
    refusals: list[FloorRefusal] = []
    for stmt in _split_statements(text):
        head = _script_head(stmt)
        extractor = SCRIPT_HEAD_EXTRACTORS.get(head) if head is not None else None
        if extractor is None:
            refusals.append(FloorRefusal(
                row_id=ctx.row_id,
                reason="unknown_script_head",
                list_index=list_index,
                code=CODE_SCRIPT,
                detail=(
                    f"no recognized call head: {stmt[:120]!r}" if head is None
                    else f"head {head!r} has no extractor: {stmt[:120]!r}"
                ),
            ))
            continue
        a, r = extractor(stmt, list_index, ctx)
        assertions.extend(a)
        refusals.extend(r)
    return tuple(assertions), tuple(refusals)


# --- shared builders -------------------------------------------------------

def _visual(detail: str) -> ScriptHeadExtractor:
    def _extractor(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
        return (FloorAssertion(
            row_id=ctx.row_id, kind="visual", list_index=list_index, code=CODE_SCRIPT,
            params=make_params(code=CODE_SCRIPT, detail=detail), tag="visual",
        ),), ()
    return _extractor


def _audio(detail: str) -> ScriptHeadExtractor:
    def _extractor(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
        return (FloorAssertion(
            row_id=ctx.row_id, kind="audio", list_index=list_index, code=CODE_SCRIPT,
            params=make_params(code=CODE_SCRIPT, detail=detail), tag="audio",
        ),), ()
    return _extractor


def _no_assertion(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    return (), ()


def _service(name: str, **literal_params: object) -> ScriptHeadExtractor:
    """A ROM-only `service` assertion -- ONLY for calls whose effect is a
    real service/menu/state change (mart, PC, save, online feature, ...),
    never a stand-in for "I don't know what kind this is" (that's `visual`,
    reserved for presentation-only calls per R11's own wording -- lead
    review 2026-09-16: `visual` had been used as a catch-all here, which
    silently weakens the floor for anything with a real gameplay effect)."""
    def _extractor(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
        return (FloorAssertion(
            row_id=ctx.row_id, kind="service", list_index=list_index, code=CODE_SCRIPT,
            params=make_params(name=name, **literal_params), tag="service",
        ),), ()
    return _extractor


def _refuse(reason: str, detail: str) -> ScriptHeadExtractor:
    def _extractor(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason=reason, list_index=list_index, code=CODE_SCRIPT,
            detail=f"{detail}: {text[:120]!r}",
        ),)
    return _extractor


# --- erase / item grant / warp ---------------------------------------------

# pbEraseThisEvent -- 059_Messages.rb:347-354: erases $game_map.events
# [@event_id] -- THIS running event, unconditionally, then marks it erased
# for the map's persistent event-erasure list.
def _extract_erase_this_event(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    return (FloorAssertion(
        row_id=ctx.row_id, kind="erase_event", list_index=list_index, code=CODE_SCRIPT,
        params=make_params(event_id=ctx.event_id), tag="state",
    ),), ()


# Kernel.pbReceiveItem(::PBItems::SYMBOL[, qty[, _I("...")]]) as a bare
# complete statement (101__PField_Field.rb:2373-2401+) -- reuses
# transpiler._RECEIVE_ITEM_RE, the same shape the emitter already resolves
# (CLAUDE.md §4.3, one parser). A guard-modified or otherwise non-literal
# call doesn't match and refuses instead of guessing.
def _extract_receive_item(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    m = _RECEIVE_ITEM_RE.match(text)
    if not m:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index, code=CODE_SCRIPT,
            detail=f"pbReceiveItem: not a bare literal call: {text[:120]!r}",
        ),)
    symbol, qty = m.group(1), m.group(2)
    return (FloorAssertion(
        row_id=ctx.row_id, kind="item_grant", list_index=list_index, code=CODE_SCRIPT,
        params=make_params(item=symbol, quantity=int(qty) if qty else 1), tag="state",
    ),), ()


# Kernel.pbAddPokemon(::PBSpecies::SYMBOL, level) -- 170__PSystem_Utilities.rb:
# 1710-1730 -- reuses transpiler._ADD_POKEMON_RE, the same shape the emitter
# already resolves (CLAUDE.md §4.3). A non-literal species/level (dynamic
# starter picks etc.) refuses instead of guessing.
def _extract_add_pokemon(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    m = _ADD_POKEMON_RE.match(text)
    if not m:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index, code=CODE_SCRIPT,
            detail=f"pbAddPokemon: not a bare literal call: {text[:120]!r}",
        ),)
    species, level = m.group(1), int(m.group(2))
    return (FloorAssertion(
        row_id=ctx.row_id, kind="pokemon_grant", list_index=list_index, code=CODE_SCRIPT,
        params=make_params(species=species, level=level), tag="state",
    ),), ()


# pbPokemonMart([PBItems::X, PBItems::Y, ...]) -- reuses
# deterministic._PBPOKEMART_LIST_RE / _PBPOKEMART_ITEM_RE, the same parse the
# emitter's mart-list idiom already does (CLAUDE.md §4.3). Every item in the
# list must resolve to a literal symbol or the whole call refuses -- never a
# partial mart list (mirrors _emit_script_call's own "all or nothing" rule).
def _extract_pokemon_mart(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    m = _PBPOKEMART_LIST_RE.search(text)
    if not m:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index, code=CODE_SCRIPT,
            detail=f"pbPokemonMart: not a literal item-list call: {text[:120]!r}",
        ),)
    items = tuple(_PBPOKEMART_ITEM_RE.findall(m.group(1)))
    if not items:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index, code=CODE_SCRIPT,
            detail=f"pbPokemonMart: no literal item symbols found: {text[:120]!r}",
        ),)
    return (FloorAssertion(
        row_id=ctx.row_id, kind="service", list_index=list_index, code=CODE_SCRIPT,
        params=make_params(name="mart", items=items), tag="service",
    ),), ()


# customTrainerBattle(trainer, endspeech, ...) -- 216_Custom_Trainers.rb:65 --
# a real trainer battle (same BR_WIN/BR_LOSS choreography as pbTrainerBattle,
# per its own body), but `trainer` is always a LOCAL variable built by a
# preceding createPhoneTrainer(...) statement in the same script block --
# never a literal PBTrainers:: id in this statement's own text, and each
# head extractor only sees its own statement (script.py's per-statement
# dispatch), not the sibling assignment. No literal identity survives to
# assert here, so this refuses rather than fabricating one.
def _extract_custom_trainer_battle(
    text: str, list_index: int, ctx: ExtractContext,
) -> ExtractResult:
    return (), (FloorRefusal(
        row_id=ctx.row_id, reason="non_literal_args", list_index=list_index, code=CODE_SCRIPT,
        detail=(
            f"customTrainerBattle: trainer identity is a local variable, "
            f"not literal: {text[:120]!r}"
        ),
    ),)


_TRANSFER_PLAYER_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbTransferPlayer\(\s*"
    r"(?:\$game_map\.map_id|(\d+))\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*"
    r"(?:,\s*(\d+)\s*)?\)\s*$"
)


# Kernel.pbTransferPlayer(map_id, x, y[, direction]) -- 023__Game_Player_v17.rb
# -- an in-place scripted warp (no fade choreography of its own, unlike a
# code-201 map transfer). All four CH01-CH05 instances pass
# `$game_map.map_id` for the map argument, i.e. "this map" at the calling
# row's own map -- resolved to `ctx.map_id` rather than left symbolic. A
# literal map id argument (not staged in the corpus today) is honored too.
def _extract_transfer_player(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    m = _TRANSFER_PLAYER_RE.match(text)
    if not m:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index, code=CODE_SCRIPT,
            detail=f"pbTransferPlayer: not a literal-args call: {text[:120]!r}",
        ),)
    map_id = int(m.group(1)) if m.group(1) is not None else ctx.map_id
    x, y = int(m.group(2)), int(m.group(3))
    direction = int(m.group(4)) if m.group(4) is not None else None
    return (FloorAssertion(
        row_id=ctx.row_id, kind="warp", list_index=list_index, code=CODE_SCRIPT,
        params=make_params(map_id=map_id, x=x, y=y, direction=direction), tag="position",
    ),), ()


# --- registry ----------------------------------------------------------

SCRIPT_HEAD_EXTRACTORS: dict[str, ScriptHeadExtractor] = {
    # visual-only: speech bubbles, sight/notice choreography, fades, menus
    # and UI screens with no assertable game-state effect of their own
    # (170__PSystem_Utilities.rb:2506 pbCallBub; :1046 pbNoticePlayer --
    # exclaim + turn + move-toward, direction not literal/predictable).
    "pbCallBub": _visual("pbCallBub"),
    "pbNoticePlayer": _visual("pbNoticePlayer"),
    # 101__PField_Field.rb:2873-2877 -- pbGlobalUnlock + erase_route, no
    # audio of its own (pairs with pbTrainerIntro's ME, but plays none
    # itself).
    "pbTrainerEnd": _visual("pbTrainerEnd"),
    # 101__PField_Field.rb:2042-2050 -- pre/post-warp fade choreography,
    # subsumed by the native warp fade (transpiler._CAVE_ENTRANCE_STRIP_RE);
    # presentation only, no menu, no state.
    "pbCaveEntrance": _visual("pbCaveEntrance"),
    "pbCaveExit": _visual("pbCaveExit"),
    # 101__PField_Field.rb:2850-2856 -- conditional push (gated on
    # $PokemonMap.strengthUsed): moves an EVENT, not a modelled key --
    # collision/position after the push is event-side state the engine
    # itself tracks, not this floor's `displacement`/`event_position` kinds
    # (those are for a code-209 move-route's own predictable net effect).
    # Lead review 2026-09-16: kept visual, noted explicitly rather than
    # silently folded in with the presentation-only heads above.
    "pbPushThisBoulder": _visual("pbPushThisBoulder (moves an event; no predictable dx/dy here)"),
    # 023__Game_Player_v17.rb:513-517 -- resets $PokemonGlobal
    # surfing/diving/bicycle (unmodelled keys), no menu, no screen. Lead
    # review 2026-09-16: kept visual (a pure state reset with nothing to
    # show), noted explicitly rather than silently folded in above.
    "pbCancelVehicles": _visual("pbCancelVehicles (surf/dive/bike state reset, no UI)"),
    # 132__PScreen_RegionMap.rb:491-497 -- fade + a region-map SCREEN the
    # player drives and dismisses -- a real menu, not mere presentation
    # (lead review 2026-09-16: was miscategorized visual).
    "pbShowMap": _service("region_map"),
    # 109_PField_BerryPlants.rb:374+ -- an interactive fertilize/plant/
    # harvest UI the player drives (lead review 2026-09-16: was
    # miscategorized visual).
    "pbBerryPlant": _service("berry_plant"),
    # 133_PScreen_Phone.rb:91-107 -- confirm dialogue THEN writes the phone
    # directory / phone-trainer list (pbPhoneRegister / pbPhoneIncrement) --
    # real phone state, not mere presentation (lead review 2026-09-16).
    "pbPhoneRegisterBattle": _service("phone_register"),
    "pbPhoneRegisterNPC": _service("phone_register"),
    # createPhoneTrainer builds the local contact object
    # pbPhoneRegisterBattle/customTrainerBattle consume -- no screen, no
    # state write, no assertable effect of its own beyond completion.
    "createPhoneTrainer": _no_assertion,
    # 103__PField_HiddenMoves.rb:379-382 -- rand(100)<25 wild encounter; no
    # literal species/level available at this call, so nothing stronger
    # than "the row completes" is assertable (R11's "visual with detail
    # explaining randomness" fallback) -- genuinely presentation-only from
    # this call's own text (the actual battle, if any, is
    # engine/RNG-decided, matching pb_wild_battle's fork treatment
    # elsewhere, not a literal this call can name).
    "pbRockSmashRandomEncounter": _visual("pbRockSmashRandomEncounter (25% random wild battle)"),
    # 138__PScreen_Save.rb:59 -- a real save-game SCREEN with its own
    # confirm/overwrite flow, not mere presentation (lead review 2026-09-16).
    "pbSave": _service("save"),
    "pbPokeCenterPC": _service("pc"),
    "pbTrainerPC": _service("pc"),
    "pbStarterSelector": _service("starter_select"),
    "pbChooseNuclearCurePokemon": _service("nuclear_cure"),
    # 221_Extra_Scripts.rb:774-779 pbDisplayLetter -- draws a static image +
    # text overlay, dismissed like a message box; no menu, no branching
    # input -- presentation, per lead review 2026-09-16's own carve-out.
    "displayNinjaLetter": _visual("displayNinjaLetter"),
    # 147__PScreen_MysteryGift.rb -- subsystem not ported; still a real
    # (would-be) menu/state feature, not presentation -- service so C6
    # surfaces it rather than hiding it as visual (lead review 2026-09-16).
    "pbNextMysteryGiftID": _service("mystery_gift"),
    "pbReceiveMysteryGift": _service("mystery_gift"),
    # Online features with no GBA analog at all -- kept as `service` (not
    # visual) precisely so C6's generator surfaces them as real gaps rather
    # than presentation the port can shrug off (lead review 2026-09-16).
    "GTS.open": _service("online_gts"),
    "WONDERTRADE.open": _service("online_wondertrade"),
    "PVP.open": _service("online_pvp"),
    "OnlineLobby.open": _service("online_lobby"),

    # audio-only.
    # 101__PField_Field.rb:2863-2870 -- Kernel.pbPlayTrainerIntroME(trtype),
    # nothing else assertable.
    "pbTrainerIntro": _audio("pbTrainerIntro"),

    # state writes -- extracted by story_state.extract, not here (see module
    # docstring). Includes pbSet, the bare-call sibling of $game_variables[N]=
    # (story_state._RE_PBSET matches its literal-int form; a non-literal
    # operand, e.g. a ternary, is a real refusal but story_state's own, not
    # this module's).
    "setTempSwitchOn": _no_assertion,
    "pbSetSelfSwitch": _no_assertion,
    "pbSet": _no_assertion,
    # pbGet is a pure getter (no write at all) -- nothing to assert beyond
    # the row's own `completes`.
    "pbGet": _no_assertion,
    # 133_PScreen_Phone.rb pbPhoneIncrement -- increments a per-trainer
    # rematch counter inside $Trainer's own phone-trainer list (the same
    # unmodelled key condition.py's pb_phone_battle_count family already
    # documents); no on-screen effect and no modelled key to assert.
    "pbPhoneIncrement": _no_assertion,
    # Kernel.pbSetPokemonCenter -- the white-out respawn anchor. Verified
    # (lead review 2026-09-16) against story_state/extract.py:476-495:
    # `_extract_script_writes` recognizes this exact head via
    # `heal_locations._parse_call` and writes `state.RESPAWN_MAP`
    # (an `EngineKey`) there -- already covered by the row's story-state
    # writes, same disposition as the other state-writing heads above.
    "pbSetPokemonCenter": _no_assertion,

    "pbEraseThisEvent": _extract_erase_this_event,
    "pbReceiveItem": _extract_receive_item,
    "pbTransferPlayer": _extract_transfer_player,
    "pbAddPokemon": _extract_add_pokemon,
    "pbPokemonMart": _extract_pokemon_mart,
    "customTrainerBattle": _extract_custom_trainer_battle,

    # jvGiveReward (213_Bambo_Reward.rb:33-51) grants an egg or item(s)
    # selected from PROFREWARDS[$game_variables[22]] -- indexed by runtime
    # state, never a literal in the source -- refuses rather than guessing
    # which reward table row fires (CLAUDE.md §4.5).
    "jvGiveReward": _refuse(
        "non_literal_args",
        "jvGiveReward: reward selected by $game_variables[22], not literal",
    ),

    # `system("start http://...")` -- a Ruby Kernel#system shell-out
    # (opens a URL in the OS browser), not presentation of anything
    # in-game -- deliberately NOT registered (lead review 2026-09-16: was
    # miscategorized visual). Falls through to `unknown_script_head`.
}
