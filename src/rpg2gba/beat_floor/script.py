"""Script-call-head extractors for the generic beat floor (REDERIVATION_PLAN.md
§16.3 C4, "C4 shape" (a); whole-statement parsing since C8 stage 5).

One extractor per Ruby call head, not one per command code. A 355/655 block
is parsed whole by `ruby_subset.parse_program` (C8 ruling (d)) -- the same
grammar story_state's interpreter runs -- and each top-level statement is
classified from its AST, never from its leading identifier:

* a call to a registered head (bare, `Kernel.`-qualified, or on a namespace
  such as `$PokemonBag.` / `GTS.`), or a local assignment whose right-hand
  side is one (`result = customTrainerBattle(...)`), dispatches to that
  head's extractor with the call's own source text. Its arguments must be
  pure (see below), or it refuses.
* anything else -- a state or local assignment, `if`/`unless`/`for`/`while`
  -- is **silent** only if it provably has no effect of its own: every call
  inside it is a pure read (`builtins.STATE_READ_CALLS`, attribute reads,
  `VALUE_METHODS`) or a state-writing head, and every assignment target is
  one story_state models. Such a statement's only consequence is state,
  which story_state's interpreter owns for the same row. Otherwise it refuses
  by name: an effect under control flow (`conditional_script_effect`), a
  player input inside an expression (`script_input`), or an unmodelled
  assignment target.

This closes the head-only false negative ruling (d) found: under the old
split-and-read-the-head scheme `x=pbGet(151).index(pbGet(151).max)` read as
a bare `pbGet` getter, and `if`/`elsif`/`end` fragments refused as unknown
heads. A block outside the subset refuses `ruby_parse_error`.

State-writing heads (`pbSetSelfSwitch`, `setTempSwitchOn`, `pbSet`, raw
`$game_switches`/`$game_variables` assignment) return an EMPTY result on
purpose: `story_state.extract` already turns these into the row's
`switch_write`/`var_write`/`self_switch_write` assertions (or refuses the
row itself on a non-constant write), and re-deriving them here would be a
second, divergent source of truth for the same fact (CLAUDE.md §4.3).
"""
from __future__ import annotations

import re
from functools import cache

from rpg2gba.beat_floor.assertion import (
    ExtractContext,
    ExtractResult,
    FloorAssertion,
    FloorRefusal,
    ScriptHeadExtractor,
    make_params,
)
from rpg2gba.beat_floor.reward_ladder import load_profrewards
from rpg2gba.conversion_agent.deterministic import _PBPOKEMART_ITEM_RE, _PBPOKEMART_LIST_RE
from rpg2gba.conversion_agent.transpiler import _ADD_POKEMON_RE, _RECEIVE_ITEM_RE
from rpg2gba.ruby_subset import ast
from rpg2gba.ruby_subset import builtins as bi
from rpg2gba.ruby_subset.evaluate import _is_nuzlocke_party_loop
from rpg2gba.ruby_subset.parser import RubyParseError, parse_program

CODE_SCRIPT = 355


# --- whole-statement parsing (C8 stage 5) ------------------------------------

def _split_statements(text: str) -> list[str]:
    """The source text of each top-level Ruby statement in a joined 355/655
    block, cut at the parser's own statement spans -- so a call whose string
    argument wraps across raw rows stays one statement, and an
    `if ... elsif ... end` is one statement rather than four fragments.
    Raises `RubyParseError` outside the subset."""
    program = parse_program(text)
    return [text[s.span[0]:s.span[1]] for s in program.statements]


def extract_script(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    try:
        program = parse_program(text)
    except RubyParseError as exc:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="ruby_parse_error", list_index=list_index,
            code=CODE_SCRIPT, detail=f"{exc.reason}: {text[:120]!r}",
        ),)
    assertions: list[FloorAssertion] = []
    refusals: list[FloorRefusal] = []
    for stmt in program.statements:
        try:
            a, r = _extract_statement(stmt, text, list_index, ctx)
        except _Refused as refused:
            refusals.append(FloorRefusal(
                row_id=ctx.row_id, reason=refused.reason, list_index=list_index,
                code=CODE_SCRIPT,
                detail=f"{refused.detail}: {_source(text, stmt)[:120]!r}",
            ))
            continue
        assertions.extend(a)
        refusals.extend(r)
    return tuple(assertions), tuple(refusals)


class _Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(reason, detail)
        self.reason = reason
        self.detail = detail


def _source(text: str, node: ast.Node) -> str:
    return text[node.span[0]:node.span[1]]


def _call_head(node: ast.Call) -> str | None:
    """The dotted head of a call on no receiver, `Kernel.`, or a namespace
    (`$PokemonBag.pbDeleteItem`, `GTS.open`) -- the key convention
    `SCRIPT_HEAD_EXTRACTORS` and `ruby_subset.builtins` share. `None` for a
    method on a computed value (`pbGet(151).index(...)`)."""
    receiver = node.receiver
    if receiver is None:
        return node.name
    if isinstance(receiver, ast.Const):
        return node.name if receiver.name == "Kernel" else f"{receiver.name}.{node.name}"
    if isinstance(receiver, ast.GlobalVar):
        return f"{receiver.name}.{node.name}"
    return None


def _attribute_key(node: ast.Call) -> tuple[str, str] | None:
    """`($Global, attr)` for a zero-arg attribute on a namespace global."""
    if node.args or not isinstance(node.receiver, ast.GlobalVar):
        return None
    return (node.receiver.name, node.name)


_ATTRIBUTE_TABLES = (
    bi.ENGINE_ATTRIBUTES, bi.STATIC_PREDICATE_ATTRS, bi.NOOP_ATTRS,
    bi.PASSTHROUGH_ENGINE_ATTRS, bi.PARTY_MODEL_ATTRS,
)
# Attribute writes that are silent here: an engine unlock (story_state's
# EngineKey write becomes the row's `engine_flag_write` in walk.py), a redraw
# hint, or a party write story_state refuses party_model for the row itself.
_SILENT_ATTRIBUTE_WRITES = (bi.ENGINE_ATTRIBUTES, bi.NOOP_ATTRS, bi.PARTY_MODEL_ATTRS)
_STATE_GLOBALS = frozenset({"$game_switches", "$game_variables", "$game_self_switches"})


def _is_pure_head(head: str) -> bool:
    """A head that returns a value without an effect the floor could assert:
    the interpreter's pure reads, opaque constructors, and every head this
    module's registry already answers with no assertion (a state writer
    story_state owns, a getter, a no-UI counter)."""
    if head in bi.STATE_READ_CALLS or head in bi.CONSTRUCTOR_CALLS:
        return True
    if head in bi.PARTY_MODEL_CALLS or head == bi.RANDOM_SPECIES_CALL:
        return True  # a read; story_state refuses party_model for the row itself
    if head in (bi.STATIC_FALSE_CALLS | bi.STATIC_ZERO_CALLS) and head not in bi.EFFECT_CALLS:
        return True
    return SCRIPT_HEAD_EXTRACTORS.get(head) is _no_assertion


def _check_pure(node: ast.Node) -> None:
    """Raise `_Refused` unless `node` is an expression with no effect of its
    own -- every value it computes lands only in state or locals."""
    if isinstance(node, ast.Call):
        _check_pure_call(node)
        return
    if isinstance(node, (ast.Assign, ast.OpAssign)):
        _check_target(node.target)
        _check_pure(node.value)
        return
    for child in _children(node):
        _check_pure(child)


def _check_pure_call(node: ast.Call) -> None:
    if node.block is not None:
        raise _Refused("unknown_script_head", f"block argument on {node.name!r}")
    head = _call_head(node)
    if head is None:
        if node.name not in bi.VALUE_METHODS:
            raise _Refused("unknown_script_head", f"method {node.name!r} on a computed value")
        _check_pure(node.receiver)
    else:
        key = _attribute_key(node)
        if key is not None and any(key in table for table in _ATTRIBUTE_TABLES):
            return
        if head in bi.INPUT_CALLS:
            raise _Refused("script_input", f"player/engine input {head!r} inside an expression")
        if not _is_pure_head(head):
            if head in SCRIPT_HEAD_EXTRACTORS or head in bi.EFFECT_CALLS:
                raise _Refused("nested_script_effect", f"effect {head!r} inside an expression")
            raise _Refused("unknown_script_head", f"head {head!r} has no extractor")
    for arg in node.args:
        _check_pure(arg)


def _check_target(target: ast.Node) -> None:
    """Raise `_Refused` unless story_state models this assignment target."""
    if isinstance(target, ast.Local):
        return
    if isinstance(target, ast.Index):
        receiver = target.receiver
        if not (isinstance(receiver, ast.GlobalVar) and receiver.name in _STATE_GLOBALS):
            _check_pure(receiver)  # in-place array mutation, e.g. pbGet(151)[i] += 1
        for arg in target.args:
            _check_pure(arg)
        return
    if isinstance(target, ast.Call):
        key = _attribute_key(target)
        if key is not None and any(key in table for table in _SILENT_ATTRIBUTE_WRITES):
            return
        raise _Refused("unmodelled_attribute_write", f"assignment to {target.name!r}")
    if isinstance(target, ast.GlobalVar):
        raise _Refused("unmodelled_global_write", f"assignment to {target.name}")
    raise _Refused("unknown_script_head", f"assignment target {type(target).__name__}")


def _check_silent_body(body: tuple[ast.Node, ...]) -> None:
    for stmt in body:
        _check_silent(stmt)


def _check_silent(stmt: ast.Node) -> None:
    """Raise `_Refused` unless `stmt` changes nothing but modelled state and
    locals. An asserting head under control flow is `conditional_script_effect`:
    the floor is unconditional, so it cannot claim the effect happens."""
    if isinstance(stmt, (ast.If, ast.Unless)):
        _check_pure(stmt.cond)
        _check_silent_body(stmt.then_body)
        for cond, body in getattr(stmt, "elifs", ()):
            _check_pure(cond)
            _check_silent_body(body)
        if stmt.else_body is not None:
            _check_silent_body(stmt.else_body)
        return
    if isinstance(stmt, ast.For):
        if _is_nuzlocke_party_loop(stmt):
            return  # the evaluator's structural no-op (C8 design (7))
        _check_pure(stmt.iterable)
        _check_silent_body(stmt.body)
        return
    if isinstance(stmt, ast.While):
        _check_pure(stmt.cond)
        _check_silent_body(stmt.body)
        return
    if isinstance(stmt, ast.Call):
        head = _call_head(stmt)
        if head is not None and not _is_pure_head(head) and (
            head in SCRIPT_HEAD_EXTRACTORS or head in bi.EFFECT_CALLS
        ):
            raise _Refused("conditional_script_effect", f"effect {head!r} under control flow")
    _check_pure(stmt)


def _dispatch_call(stmt: ast.Node) -> ast.Call | None:
    """The registered call a top-level statement IS: the statement itself,
    or the right-hand side of a plain local assignment
    (`trainer = createPhoneTrainer(...)`)."""
    node = stmt
    if isinstance(stmt, ast.Assign) and isinstance(stmt.target, ast.Local):
        node = stmt.value
    if isinstance(node, ast.Call):
        head = _call_head(node)
        if head is not None and head in SCRIPT_HEAD_EXTRACTORS:
            return node
    return None


def _extract_statement(
    stmt: ast.Node, text: str, list_index: int, ctx: ExtractContext,
) -> ExtractResult:
    call = _dispatch_call(stmt)
    if call is not None:
        for arg in call.args:
            _check_pure(arg)
        return SCRIPT_HEAD_EXTRACTORS[_call_head(call)](_source(text, call), list_index, ctx)
    if isinstance(stmt, ast.Call):
        head = _call_head(stmt)
        if head is not None and not _is_pure_head(head):
            raise _Refused("unknown_script_head", f"head {head!r} has no extractor")
    _check_silent(stmt)
    return (), ()


def _children(node: ast.Node) -> tuple[ast.Node, ...]:
    """Direct sub-expressions of a non-call, non-assignment expression node."""
    if isinstance(node, ast.ArrayLit):
        return node.elements
    if isinstance(node, ast.HashLit):
        return tuple(n for pair in node.pairs for n in pair)
    if isinstance(node, ast.RangeLit):
        return (node.lo, node.hi)
    if isinstance(node, ast.BinOp):
        return (node.left, node.right)
    if isinstance(node, ast.UnaryOp):
        return (node.operand,)
    if isinstance(node, ast.Ternary):
        return (node.cond, node.then, node.else_)
    if isinstance(node, ast.Index):
        return (node.receiver, *node.args)
    if isinstance(node, ast.ScopedConst):
        return (node.scope,)
    if isinstance(node, (ast.Return, ast.Break, ast.Next)):
        return (node.value,) if node.value is not None else ()
    if isinstance(node, (
        ast.Int, ast.Float, ast.Str, ast.Sym, ast.Bool, ast.Nil,
        ast.Local, ast.GlobalVar, ast.Const,
    )):
        return ()
    if isinstance(node, (ast.If, ast.Unless, ast.For, ast.While)):
        raise _Refused("conditional_script_effect", "control flow inside an expression")
    raise _Refused("unknown_script_head", f"unsupported node {type(node).__name__}")


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


_JV_GIVE_REWARD_RE = re.compile(r"^\s*(?:Kernel\.)?jvGiveReward\s*$")


@cache
def _reward_candidates() -> str:
    """Every grant the PROFREWARDS ladder can pay, for the refusal detail.
    Cached: the ladder is read from source once per process, not per site."""
    rungs = load_profrewards()
    items = sorted({item for rung in rungs for item in rung.items})
    eggs = sorted({rung.species for rung in rungs if rung.is_egg and rung.species is not None})
    return ", ".join([
        *(f"item:{item}" for item in items),
        *(f"egg:{species}" for species in eggs),
    ])


# jvGiveReward (213_Bambo_Reward.rb:33-51) grants an egg or item(s) selected
# by `PROFREWARDS[$game_variables[22]]` -- variable 22 is ordinary modelled
# state (C8 stage 7, assignment task 1's whole point: `jvGiveReward` itself
# needs no party/dex model, unlike `jvNextReward`), but the floor is a
# CONJUNCTION of its row's assertions (`coverage.uncovered`) and exactly one
# PROFREWARDS rung pays out per visit -- there is no vocabulary today for "one
# of these N grants holds" at a single `(row_id, kind, list_index, code)` key
# (`coverage.contradicts` would flag the siblings as mutually refuting). R2's
# "refuse, precisely" option: keep refusing, but name the true obstruction
# instead of the old (wrong) "not literal" diagnosis, and list the candidate
# grants read straight from the ladder so the refusal is still informative.
def _extract_jv_give_reward(text: str, list_index: int, ctx: ExtractContext) -> ExtractResult:
    if not _JV_GIVE_REWARD_RE.match(text):
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="non_literal_args", list_index=list_index, code=CODE_SCRIPT,
            detail=f"jvGiveReward: not a bare literal call: {text[:120]!r}",
        ),)
    # Refuse loudly rather than silently falling back to the old blanket
    # refusal if the ladder itself can't be read (CLAUDE.md §4.5) -- let
    # `FileNotFoundError`/`ValueError` propagate.
    candidates = _reward_candidates()
    return (), (FloorRefusal(
        row_id=ctx.row_id, reason="one_of_n_grant", list_index=list_index, code=CODE_SCRIPT,
        detail=(
            "jvGiveReward: the floor is a conjunction -- exactly one PROFREWARDS "
            "rung pays out per visit and the vocabulary cannot express a "
            f"one-of-N grant at one call site; candidates: {candidates}"
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

    # jvGiveReward: see `_extract_jv_give_reward` above (C8 stage 7, task 1).
    "jvGiveReward": _extract_jv_give_reward,

    # `system("start http://...")` -- a Ruby Kernel#system shell-out
    # (opens a URL in the OS browser), not presentation of anything
    # in-game -- deliberately NOT registered (lead review 2026-09-16: was
    # miscategorized visual). Falls through to `unknown_script_head`.
}
