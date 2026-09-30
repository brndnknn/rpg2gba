"""The generic per-row walker (REDERIVATION_PLAN.md §16.3 C4).

`CODE_EXTRACTORS` covers every plain RMXP command code present in
CH01-CH05 (R11's "generic floor": one extractor per command code, expected
values always from the RMXP source, never from converted Poryscript).
`floor_for_map`/`floor_for_chapter` are the entry points: they walk every
row's own scope via `chapter_manifest.generator.iter_page_scopes` (the
single source of row scopes, per its own docstring), dispatch each command
through `CODE_EXTRACTORS` (or one of the three grouped special cases --
Show Text runs, Script runs, and code 117 common-event inlining -- handled
directly in `_walk_scope` before the generic dispatch), and then merge in
the story-state model's own writes/refusals for the same row id
(`rpg2gba.story_state.extract.extract_map`) rather than re-deriving 121/122/
123 here (CLAUDE.md §4.3: one source of truth).

`script.py` (per script-call head), `condition.py` (per 111 type-12
condition family) and `move_route.py` (code 209) are sibling modules in
this package, written independently (REDERIVATION_PLAN.md §16.3 C4 design).
This module calls their three public entry points -- `extract_script`,
`extract_condition`, `extract_move_route` -- by module-global name, so unit
tests can inject fakes by monkeypatching `walk.extract_script` etc. -- see
`tests/test_beat_floor_walk.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from rpg2gba.beat_floor.assertion import (
    ExtractContext,
    ExtractResult,
    FloorAssertion,
    FloorRefusal,
    LeafExtractor,
    RowFloor,
    make_params,
)
from rpg2gba.beat_floor.cond_write import cond_write_inputs
from rpg2gba.beat_floor.condition import extract_condition
from rpg2gba.beat_floor.move_route import extract_move_route
from rpg2gba.beat_floor.obstacle import obstacle_assertions
from rpg2gba.beat_floor.script import extract_script
from rpg2gba.beat_floor.terrain import seam_floors_for_map, stair_floors_for_map
from rpg2gba.beat_floor.var_text import var_text_source
from rpg2gba.chapter_manifest.generator import PageScope, detect_stair_cells, iter_page_scopes
from rpg2gba.chapter_manifest.schema import parse_row_id, row_id_sort_key
from rpg2gba.conversion_agent.deterministic import join_text_lines, translate_text_codes
from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.conversion_agent.inline_choice import (
    InlineChoiceError,
    has_inline_choice,
    parse_inline_choice,
)
from rpg2gba.playtest.text_source import (
    _char_canon_table,
    _default_engine_dir,
    rom_text,
)
from rpg2gba.ruby_subset.builtins import ENGINE_ATTRIBUTES
from rpg2gba.story_state.extract import (
    _default_reference_dir,
    _TRIGGER_NAMES,
    RowState,
    extract_map,
)
from rpg2gba.story_state.scope_search import stripped_ce_ids_for
from rpg2gba.story_state.state import (
    Assign,
    EngineKey,
    SelfSwitch,
    Switch,
    TempSwitch,
    Variable,
)

logger = logging.getLogger(__name__)

# EngineKey name -> native FLAG_SYS_* for the engine-held unlocks (C8 ruling
# (b)); read from the one table, never restated here (§4.3).
_UNLOCK_FLAGS: dict[str, str] = {a.key_name: a.flag for a in ENGINE_ATTRIBUTES.values()}


# --- RMXP command codes used by this module (kept local, matching the
# convention `chapter_manifest.generator`/`story_state.extract` already
# follow -- the corpus has no single canonical command-code module). -------
SHOW_TEXT = 101
SHOW_TEXT_CONT = 401
SHOW_CHOICES = 102
CONDITIONAL_BRANCH = 111
COMMON_EVENT_CALL = 117
EXIT_EVENT_PROCESSING = 115
SCRIPT = 355
SCRIPT_CONT = 655

_CONDITION_TYPE_SCRIPT = 12


# --- text normalization (reuses playtest.text_source, never re-implemented) -

def _normalize_fragments(fragments: list[str]) -> str:
    """Fragments -> ROM-comparable text, via the exact pipeline
    `playtest.text_source.page_messages` uses per message (join, translate
    control codes, then `text_source.rom_text`).
    Raises `ValueError` on anything neither step recognizes -- the caller
    converts that into a `FloorRefusal(reason="text_unnormalizable")`."""
    return _normalize_translated(join_text_lines(fragments), fragments)


def _normalize_translated(joined: str, fragments: list[str]) -> str:
    """The translate + `rom_text` half of `_normalize_fragments`, on already
    joined text (`fragments` only names the source in the error)."""
    translated = translate_text_codes(joined)
    if translated is None:
        raise ValueError(
            f"unrecognized control code in fragments {fragments!r}")
    return rom_text(translated.text, _char_canon_table(_default_engine_dir()))


def _extract_inline_choice(
    fragments: list[str], text_list_index: int, choice_list_index: int,
    index_within_row: int, ctx: ExtractContext,
) -> ExtractResult:
    """A Show Text message carrying Essentials' inline ``\\ch[var,ifCancel,
    opt1,...]`` escape: a `text` assertion for the prompt plus a `choice`
    assertion for the menu, exactly the pair a 101 + 102 would give (so
    `beat_gen`'s per-choice handling reads it unchanged).

    Parsing is `conversion_agent.inline_choice.parse_inline_choice` and the
    prompt is prepared exactly as `transpiler._emit_inline_choice` does (strip
    ``\\b`` and ``\\C[n]``, strip whitespace, translate) so the text is what
    the ROM's `msgbox` shows. The `choice` sits at the LAST fragment's list
    index (where the `\\ch` lives), after the prompt's own, so the step order
    is prompt then menu. Its params add `inline=True`, `var_id` and `if_cancel`:
    the ROM's menu is a `dynmultichoice` (never `yesnobox`, whatever the option
    count) whose pick lands in `VAR_RESULT` and is then copied to the game
    variable `var_id` (or `if_cancel - 1` on B when `if_cancel` != 0)."""
    from rpg2gba.conversion_agent.transpiler import _BLUE_TEXT_CODE_RE, _COLOUR_TEXT_CODE_RE

    def refuse(code_index: int, detail: str) -> ExtractResult:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="text_unnormalizable", list_index=code_index,
            code=SHOW_TEXT, detail=f"code 101 @list[{code_index}]: {detail}",
        ),)

    try:
        choice = parse_inline_choice(join_text_lines(fragments))
    except InlineChoiceError as exc:
        return refuse(text_list_index, exc.message)
    prompt_source = _COLOUR_TEXT_CODE_RE.sub("", _BLUE_TEXT_CODE_RE.sub("", choice.prompt_text)).strip()
    if not prompt_source:
        return refuse(text_list_index, f"inline choice with no prompt text: {fragments!r}")
    try:
        prompt = _normalize_translated(prompt_source, fragments)
        options = tuple(_normalize_fragments([o]) for o in choice.options)
    except ValueError as exc:
        return refuse(text_list_index, str(exc))
    return (
        FloorAssertion(
            row_id=ctx.row_id, kind="text", list_index=text_list_index, code=SHOW_TEXT,
            params=make_params(index=index_within_row, text=prompt), tag="text"),
        FloorAssertion(
            row_id=ctx.row_id, kind="choice", list_index=choice_list_index, code=SHOW_TEXT,
            params=make_params(options=list(options), inline=True, var_id=choice.var_id,
                               if_cancel=choice.if_cancel),
            tag="text"),
    ), ()


def _text_blocks(commands: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Index ranges `[start, end)` of consecutive Show Text (101) + Show
    Text continuation (401) runs, matching
    `playtest.text_source._extract_message_groups`'s own grouping exactly:
    a 101 always opens a new block even immediately after another; a run of
    401s with no preceding 101 in this scope is still its own block."""
    blocks: list[tuple[int, int]] = []
    i = 0
    n = len(commands)
    while i < n:
        code = commands[i].get("code")
        if code in (SHOW_TEXT, SHOW_TEXT_CONT):
            start = i
            j = i + 1
            while j < n and commands[j].get("code") == SHOW_TEXT_CONT:
                j += 1
            blocks.append((start, j))
            i = j
        else:
            i += 1
    return blocks


def _script_blocks(commands: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Index ranges `[start, end)` of consecutive Script (355) + Script
    continuation (655) runs -- same grouping shape as `_text_blocks`, and
    the same one `story_state.extract._extract_scope_writes` groups before
    dispatch (this module's docstring: "355+655* into one block")."""
    blocks: list[tuple[int, int]] = []
    i = 0
    n = len(commands)
    while i < n:
        code = commands[i].get("code")
        if code in (SCRIPT, SCRIPT_CONT):
            start = i
            j = i + 1
            while j < n and commands[j].get("code") == SCRIPT_CONT:
                j += 1
            blocks.append((start, j))
            i = j
        else:
            i += 1
    return blocks


# --- plain-code leaf extractors ---------------------------------------------

def _no_assertion(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
    """Structure/comment/no-op codes: contributes nothing (not even a
    refusal) -- see the module docstring's `_CODE_EFFECT`-adjacent codes
    (108/408, loop/label/jump control flow, and the branch/choice/loop
    structural markers, which never actually reach here since `parse_tree`
    consumes them before `iter_page_scopes` ever sees them -- kept for
    documentation and census completeness, per the C4 brief)."""
    return (), ()


def _visual(code_for_detail: int, detail: str) -> LeafExtractor:
    """A visual-only command: asserts nothing beyond `completes`, tagged
    `"visual"` so it never blocks offline eligibility (`assertion.
    OFFLINE_KINDS`). Mirrors `move_route.py`'s own `visual` shape exactly
    (`params=make_params(code=..., detail=...)`)."""

    def _extractor(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
        assertion = FloorAssertion(
            row_id=ctx.row_id, kind="visual", list_index=list_index,
            code=code_for_detail, params=make_params(code=code_for_detail, detail=detail),
            tag="visual",
        )
        return (assertion,), ()

    return _extractor


def _audio(code_for_detail: int, name_param_index: int) -> LeafExtractor:
    """241/242/249/250: `audio`-tagged, not checked until audio is mapped
    (assertion.py: "not checked until audio is mapped"), so it does not
    block offline eligibility (`audio` is in `OFFLINE_KINDS`)."""

    def _extractor(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
        params = cmd.get("parameters") or []
        name: Any = None
        if len(params) > name_param_index:
            entry = params[name_param_index]
            name = entry.get("name") if isinstance(entry, dict) else entry
        assertion = FloorAssertion(
            row_id=ctx.row_id, kind="audio", list_index=list_index,
            code=code_for_detail, params=make_params(code=code_for_detail, name=name),
            tag="audio",
        )
        return (assertion,), ()

    return _extractor


def _extract_warp(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
    """201 Transfer Player. `parameters`: [designation, map_id, x, y,
    direction, fade_type] (designation 0 = direct constants; 1/2 = variable-
    designated -- refused, R11's proxy-oracle rule can't read a variable's
    runtime value from source alone).

    `arrives_on_door` (C5b) is whether the emitted layout stamps the arrival
    cell as a door tile (`ctx.door_cells`): the engine then walks the player
    one step on in their arrival facing, so a beat's expected final cell is
    the destination plus that step (`playtest.assertions.arrival_landing_
    cell`). Direction 0 ("retain") is left for the consumer to resolve from
    its own approach -- the floor cannot know how the row is crossed."""
    params = cmd.get("parameters") or []
    if not params or params[0] != 0:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="warp_variable_target", list_index=list_index,
            code=201, detail=f"code 201 @list[{list_index}]: designation {(params[0] if params else None)!r} is not direct",
        ),)
    if len(params) < 5:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="malformed_warp", list_index=list_index,
            code=201, detail=f"code 201 @list[{list_index}]: too few params {params!r}",
        ),)
    map_id, x, y, direction = params[1], params[2], params[3], params[4]
    if ctx.door_cells is None:
        raise ValueError(
            f"{ctx.row_id}: code 201 @list[{list_index}] needs the emitted layout's "
            "door cells (ExtractContext.door_cells) to derive arrives_on_door -- "
            "pass door_cells= to floor_for_map")
    arrives_on_door = (x, y) in ctx.door_cells.get(map_id, frozenset())
    assertion = FloorAssertion(
        row_id=ctx.row_id, kind="warp", list_index=list_index, code=201,
        params=make_params(map_id=map_id, x=x, y=y, direction=direction,
                           arrives_on_door=arrives_on_door),
        tag="position",
    )
    return (assertion,), ()


def _extract_event_position(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
    """202 Set Event Location. `parameters`: [event_id, designation, x, y,
    direction] (designation 0 = direct constants; else variable/exchange-
    designated -- refused)."""
    params = cmd.get("parameters") or []
    if len(params) < 2 or params[1] != 0:
        designation = params[1] if len(params) > 1 else None
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="event_position_variable_target", list_index=list_index,
            code=202, detail=f"code 202 @list[{list_index}]: designation {designation!r} is not direct",
        ),)
    if len(params) < 5:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="malformed_event_position", list_index=list_index,
            code=202, detail=f"code 202 @list[{list_index}]: too few params {params!r}",
        ),)
    target, x, y, direction = params[0], params[2], params[3], params[4]
    assertion = FloorAssertion(
        row_id=ctx.row_id, kind="event_position", list_index=list_index, code=202,
        params=make_params(target=target, x=x, y=y, direction=direction), tag="position",
    )
    return (assertion,), ()


def _extract_erase_event(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
    assertion = FloorAssertion(
        row_id=ctx.row_id, kind="erase_event", list_index=list_index, code=116,
        params=make_params(event_id=ctx.event_id), tag="flow",
    )
    return (assertion,), ()


def _extract_heal_party(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
    assertion = FloorAssertion(
        row_id=ctx.row_id, kind="heal_party", list_index=list_index, code=314,
        params=(), tag="state",
    )
    return (assertion,), ()


def _extract_choice(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
    """102 Show Choices. `parameters[0]` is the list of choice-label
    strings (`transpiler.parse_tree`'s own reading of the same command).
    Each label goes through the same normalization pipeline as dialogue
    text (R11: "102 -> choice with normalized options"); an unnormalizable
    option refuses the row exactly like unnormalizable body text."""
    params = cmd.get("parameters") or []
    raw_options = params[0] if params and isinstance(params[0], list) else []
    try:
        options = tuple(_normalize_fragments([str(o)]) for o in raw_options)
    except ValueError as exc:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="text_unnormalizable", list_index=list_index,
            code=102, detail=f"code 102 @list[{list_index}]: {exc}",
        ),)
    assertion = FloorAssertion(
        row_id=ctx.row_id, kind="choice", list_index=list_index, code=102,
        params=make_params(options=list(options)), tag="text",
    )
    return (assertion,), ()


def _extract_conditional_branch(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
    """111 Conditional Branch. Its condition text runs in the ENCLOSING
    scope (R11/C4 shape): since `chapter_manifest.generator._flatten_scope`
    only ever puts a branch opener's raw command into the scope that
    contains it (never into either arm's own scope), simply dispatching
    this command wherever it is encountered already contributes it to the
    correct (enclosing) row -- no extra lookup needed. Only condition type
    12 (script-typed) has anything to extract; every other type (switch,
    variable, self-switch, ...) is a story_state guard, contributing
    nothing here (R11 C4 shape)."""
    params = cmd.get("parameters") or []
    condition_type = params[0] if params else None
    if condition_type != _CONDITION_TYPE_SCRIPT:
        return (), ()
    condition_text = params[1] if len(params) > 1 and isinstance(params[1], str) else ""
    return extract_condition(condition_text, list_index, ctx)


CODE_EXTRACTORS: dict[int, LeafExtractor] = {
    102: _extract_choice,
    104: _visual(104, "text_options"),
    106: _visual(106, "wait"),
    108: _no_assertion,
    111: _extract_conditional_branch,
    112: _no_assertion,   # loop opener (transparent; body stays in this scope)
    113: _no_assertion,   # break loop
    116: _extract_erase_event,
    118: _no_assertion,   # label
    119: _no_assertion,   # jump to label
    121: _no_assertion,   # switch write: comes from story_state, not here
    122: _no_assertion,   # var write: comes from story_state, not here
    123: _no_assertion,   # self-switch write: comes from story_state, not here
    201: _extract_warp,
    202: _extract_event_position,
    204: _visual(204, "map_settings"),
    207: _visual(207, "animation"),
    208: _visual(208, "player_transparency"),
    209: extract_move_route,
    210: _visual(210, "wait_for_move"),
    221: _visual(221, "fade_to_black"),
    222: _visual(222, "fade_from_black"),
    223: _visual(223, "screen_tone"),
    241: _audio(241, 0),
    242: _audio(242, 0),
    249: _audio(249, 0),
    250: _audio(250, 0),
    314: _extract_heal_party,
    # Structural markers `parse_tree` consumes before `iter_page_scopes`
    # ever produces a scope -- never actually seen by `_walk_scope`, kept
    # here for census completeness/documentation (R11 C4 shape).
    0: _no_assertion,
    402: _no_assertion,
    403: _no_assertion,
    404: _no_assertion,
    408: _no_assertion,
    411: _no_assertion,
    412: _no_assertion,
    413: _no_assertion,
    509: _no_assertion,
}


# --- scope walking (special-cased text/script grouping + 117 inlining) -----

def _walk_leaf(
    cmd: dict[str, Any], list_index: int, ctx: ExtractContext,
) -> ExtractResult:
    code = cmd.get("code")
    extractor = CODE_EXTRACTORS.get(code)
    if extractor is None:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="no_extractor", list_index=list_index,
            code=code, detail=f"command code {code!r} @list[{list_index}] has no floor extractor",
        ),)
    return extractor(cmd, list_index, ctx)


def _walk_commands(
    commands: list[dict[str, Any]],
    ctx: ExtractContext,
    index_of: dict[int, int],
    visited_ce: frozenset[int],
    stripped_ce_ids: frozenset[int],
) -> ExtractResult:
    """Walks one flat scope's commands (a page trunk, a branch arm, or an
    inlined common event's own flattened body), dispatching text/script
    grouping, 117 common-event inlining, and 115 early-exit before falling
    through to `CODE_EXTRACTORS`/`_walk_leaf` for everything else."""
    assertions: list[FloorAssertion] = []
    refusals: list[FloorRefusal] = []

    text_blocks = dict(_text_blocks(commands))
    script_blocks = dict(_script_blocks(commands))
    earlier_scripts: list[str] = []  # this scope's script blocks so far (ruling 18)

    i = 0
    n = len(commands)
    while i < n:
        cmd = commands[i]
        code = cmd.get("code")
        list_index = index_of.get(id(cmd), -1)

        if i in text_blocks:
            end = text_blocks[i]
            fragments = []
            for c in commands[i:end]:
                params = c.get("parameters") or []
                fragments.append(str(params[0]) if params else "")
            index_within_row = sum(1 for a in assertions if a.kind in ("text", "var_text"))
            if has_inline_choice(join_text_lines(fragments)):
                a, r = _extract_inline_choice(
                    fragments, list_index, index_of.get(id(commands[end - 1]), -1),
                    index_within_row, ctx)
                assertions.extend(a)
                refusals.extend(r)
                i = end
                continue
            try:
                text = _normalize_fragments(fragments)
            except ValueError as exc:
                var_text = var_text_source(fragments, earlier_scripts)
                if var_text is None:
                    refusals.append(FloorRefusal(
                        row_id=ctx.row_id, reason="text_unnormalizable", list_index=list_index,
                        code=SHOW_TEXT, detail=f"code 101 @list[{list_index}]: {exc}",
                    ))
                else:
                    var_id, script, input_vars = var_text
                    assertions.append(FloorAssertion(
                        row_id=ctx.row_id, kind="var_text", list_index=list_index,
                        code=SHOW_TEXT, tag="text",
                        params=make_params(index=index_within_row, raw=tuple(fragments),
                                           var_id=var_id, script=script,
                                           input_vars=input_vars),
                    ))
            else:
                assertions.append(FloorAssertion(
                    row_id=ctx.row_id, kind="text", list_index=list_index, code=SHOW_TEXT,
                    params=make_params(index=index_within_row, text=text), tag="text",
                ))
            i = end
            continue

        if i in script_blocks:
            end = script_blocks[i]
            parts = []
            for c in commands[i:end]:
                params = c.get("parameters") or []
                parts.append(str(params[0]) if params else "")
            text = "\n".join(parts)
            earlier_scripts.append(text)
            a, r = extract_script(text, list_index, ctx)
            assertions.extend(a)
            refusals.extend(r)
            i = end
            continue

        if code == EXIT_EVENT_PROCESSING:
            # No assertion of its own; stops walking the REST of this
            # scope (R11 C4 shape).
            i = n
            break

        if code == COMMON_EVENT_CALL:
            a, r = _walk_common_event_call(cmd, list_index, ctx, visited_ce, stripped_ce_ids)
            assertions.extend(a)
            refusals.extend(r)
            i += 1
            continue

        a, r = _walk_leaf(cmd, list_index, ctx)
        assertions.extend(a)
        refusals.extend(r)
        i += 1

    return tuple(assertions), tuple(refusals)


def _walk_common_event_call(
    cmd: dict[str, Any], list_index: int, ctx: ExtractContext, visited_ce: frozenset[int],
    stripped_ce_ids: frozenset[int],
) -> ExtractResult:
    """117 Call Common Event: inlines the callee's body -- trunk plus every
    branch arm (both sides; the floor asserts what COULD happen, not what
    is certain) -- with every resulting assertion/refusal attributed to
    THIS call's own `list_index` (R11 C4 shape), never a position inside
    the callee's own command list. Guards against a common-event call
    cycle with a `visited_ce` set threaded through the recursion.

    A `ce_id` in `stripped_ce_ids` (`reference/strip_list.json`'s whole
    common events -- ids 4/5/6, GTS/VT/LOBBY) is a no-op: the ROM will not
    contain that common event, so it produces neither assertions nor
    refusals, and its body is never walked. This check runs BEFORE the
    missing-CE lookup below (order: malformed -> cycle -> stripped ->
    missing -> inline) -- a stripped CE may legitimately be absent from
    `common_events.json`, and a `missing_common_event` refusal for
    something deliberately not run would be wrong. Matches
    `story_state.extract.extract_map`'s own treatment of the same command
    (C8 stage 4, commit `bd80c080`; CLAUDE.md §4.3)."""
    params = cmd.get("parameters") or []
    if not params:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="malformed_common_event_call", list_index=list_index,
            code=COMMON_EVENT_CALL, detail=f"code 117 @list[{list_index}]: no params",
        ),)
    ce_id = params[0]
    if ce_id in visited_ce:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="common_event_cycle", list_index=list_index,
            code=COMMON_EVENT_CALL,
            detail=f"code 117 @list[{list_index}] (common event {ce_id}): already inlined on this path",
        ),)
    if ce_id in stripped_ce_ids:
        return (), ()
    ce = ctx.common_events_by_id.get(ce_id)
    if ce is None:
        return (), (FloorRefusal(
            row_id=ctx.row_id, reason="missing_common_event", list_index=list_index,
            code=COMMON_EVENT_CALL, detail=f"code 117 @list[{list_index}]: common event {ce_id} not found",
        ),)

    from rpg2gba.chapter_manifest.generator import _flatten_scope
    from rpg2gba.conversion_agent.transpiler import ChoiceNode, IfNode, LoopNode, parse_tree

    ce_commands = ce.get("list") or []
    tree = parse_tree(ce_commands)
    new_visited = visited_ce | {ce_id}

    assertions: list[FloorAssertion] = []
    refusals: list[FloorRefusal] = []

    def _walk_scope_forced(nodes: list[Any]) -> None:
        flat = _flatten_scope(nodes, ce_commands)
        # Every write/assertion inside an inlined common event is
        # attributed to the calling 117's own `list_index` -- there is no
        # per-command `index_of` inside the callee, so pass an empty one
        # and let `_walk_commands` fall back to `list_index=-1` internally;
        # override every produced record's `list_index` to the call site.
        a, r = _walk_commands(
            flat, ctx, index_of={}, visited_ce=new_visited, stripped_ce_ids=stripped_ce_ids)
        for item in a:
            assertions.append(FloorAssertion(
                row_id=item.row_id, kind=item.kind, list_index=list_index,
                code=item.code, params=item.params, tag=item.tag,
            ))
        for item in r:
            refusals.append(FloorRefusal(
                row_id=item.row_id, reason=item.reason, list_index=list_index,
                code=item.code, detail=item.detail,
            ))

    _walk_scope_forced(tree)

    def _walk_arms(nodes: list[Any]) -> None:
        for node in nodes:
            if isinstance(node, IfNode):
                _walk_scope_forced(node.then)
                _walk_arms(node.then)
                otherwise = node.otherwise if node.otherwise is not None else []
                _walk_scope_forced(otherwise)
                _walk_arms(otherwise)
            elif isinstance(node, ChoiceNode):
                for _, _, children in node.arms:
                    _walk_scope_forced(children)
                    _walk_arms(children)
            elif isinstance(node, LoopNode):
                _walk_arms(node.children)

    _walk_arms(tree)

    return tuple(assertions), tuple(refusals)


# --- state-write merge (reuses story_state.extract, never re-derived) ------

def _render_write_value(values: frozenset) -> Any:
    if len(values) == 1:
        return next(iter(values))
    return tuple(sorted(values, key=repr))


def _later_arm_writes(row_id: str, row_states: Mapping[str, RowState]) -> dict[Any, int]:
    """Key -> the last page list index any branch arm under `row_id` (a
    descendant row, `row_id/bN...`) writes it at. Arm bodies are separate
    rows, but the ROM check reads a write after the WHOLE page has run."""
    prefix = row_id + "/"
    last: dict[Any, int] = {}
    for rid, state in row_states.items():
        if not rid.startswith(prefix):
            continue
        for write in state.writes:
            if write.list_index > last.get(write.key, -1):
                last[write.key] = write.list_index
    return last


def _state_assertions_for_row(
    row_id: str, row_state: RowState, scripts_by_index: Mapping[int, str],
    later_arm_writes: Mapping[Any, int] | None = None,
) -> tuple[
    tuple[FloorAssertion, ...], tuple[FloorRefusal, ...],
]:
    """Converts one row's `story_state.extract.RowState` writes/refusals
    into floor assertions/refusals (R11 C4 design: "State writes are NOT
    re-derived"). An `EngineKey` write for an engine-held unlock
    (`builtins.ENGINE_ATTRIBUTES`: running shoes, Pokédex, PokéGear, storage
    creator) becomes `engine_flag_write` on its native `FLAG_SYS_*` (C8 ruling
    (b), added 2026-09-24). Every other `EngineKey` (respawn map, surfing,
    run toggle) and `TempSwitch` writes are per-visit/engine-only state with
    no `AssertionKind` -- skipped, not mapped.

    A `conditional` assign (written on only some runs) is never asserted as
    certain: if its source is one of this row's script blocks
    (`scripts_by_index`, keyed by the block's list index) that reads only
    game variables, the assertion carries `script` + `input_vars` and the ROM
    check evaluates it on the ROM's own values (`beat_floor.cond_write`);
    otherwise it refuses as `conditional_state_write`.

    A write that a branch arm under this row writes again later on the page
    (`later_arm_writes`) is not the page's final value, and the ROM check
    reads it after the page completes: it is not asserted here. The arm rows
    assert their own writes. ROM run 46: Auntie's page (map049/ev001/p2)
    turns switch 185 ON, then each starter arm turns it OFF again; the
    trunk asserted ON and the ROM read OFF."""
    assertions: list[FloorAssertion] = []
    refusals: list[FloorRefusal] = []
    later = later_arm_writes or {}

    def cond_params(write: Assign) -> tuple[tuple[str, Any], ...] | None:
        """() for an unconditional write, the condition params for a
        checkable conditional one, None (after refusing) otherwise."""
        if not write.conditional:
            return ()
        script = scripts_by_index.get(write.list_index)
        inputs = cond_write_inputs(script) if script is not None else None
        if script is None or inputs is None:
            refusals.append(FloorRefusal(
                row_id=row_id, reason="conditional_state_write",
                list_index=write.list_index, code=None,
                detail=f"{write.key!r} written on only some runs ({write.source})",
            ))
            return None
        return make_params(script=script, input_vars=inputs)

    for write in row_state.writes:
        key = write.key
        if later.get(key, -1) > write.list_index:
            continue  # an arm writes it again after this; not the final value
        if isinstance(key, Switch):
            if not isinstance(write, Assign):
                continue  # switches have no arithmetic write form
            cond = cond_params(write)
            if cond is None:
                continue
            assertions.append(FloorAssertion(
                row_id=row_id, kind="switch_write", list_index=write.list_index,
                code=121, params=make_params(
                    switch_id=key.id, value=_render_write_value(write.values), **dict(cond)),
                tag="state",
            ))
        elif isinstance(key, SelfSwitch):
            if not isinstance(write, Assign):
                continue
            cond = cond_params(write)
            if cond is None:
                continue
            assertions.append(FloorAssertion(
                row_id=row_id, kind="self_switch_write", list_index=write.list_index,
                code=123, params=make_params(
                    event_id=key.event_id, letter=key.letter,
                    value=_render_write_value(write.values), **dict(cond)),
                tag="state",
            ))
        elif isinstance(key, Variable):
            if isinstance(write, Assign):
                cond = cond_params(write)
                if cond is None:
                    continue
                assertions.append(FloorAssertion(
                    row_id=row_id, kind="var_write", list_index=write.list_index,
                    code=122, params=make_params(
                        var_id=key.id, op="=", value=_render_write_value(write.values), **dict(cond)),
                    tag="state",
                ))
            else:  # Adjust
                assertions.append(FloorAssertion(
                    row_id=row_id, kind="var_write", list_index=write.list_index,
                    code=122, params=make_params(
                        var_id=key.id, op=write.op, value=write.amount),
                    tag="state",
                ))
        elif isinstance(key, EngineKey) and key.name in _UNLOCK_FLAGS:
            if not isinstance(write, Assign):
                continue  # a flag has no arithmetic write form
            if write.conditional:
                # The evaluator's EngineKey writes have no ROM-side check yet.
                refusals.append(FloorRefusal(
                    row_id=row_id, reason="conditional_state_write",
                    list_index=write.list_index, code=None,
                    detail=f"{key!r} written on only some runs ({write.source})",
                ))
                continue
            assertions.append(FloorAssertion(
                row_id=row_id, kind="engine_flag_write", list_index=write.list_index,
                code=355, params=make_params(
                    flag=_UNLOCK_FLAGS[key.name], value=_render_write_value(write.values)),
                tag="state",
            ))
        elif isinstance(key, (TempSwitch, EngineKey)):
            continue
        else:  # pragma: no cover - exhaustive over story_state.state.Key
            continue

    refusals.extend(
        FloorRefusal(
            row_id=row_id, reason="story_state_refusal", list_index=-1, code=None,
            detail=f"{r.code}: {r.detail}",
        )
        for r in row_state.refusals
    )
    return tuple(assertions), tuple(refusals)


# --- row / map / chapter assembly -------------------------------------------

def _build_row_floor(
    scope: PageScope,
    trigger: str,
    map_id: int,
    event_id: int,
    page_idx: int,
    event: dict[str, Any],
    map_data: dict[str, Any],
    common_events_by_id: dict[int, dict[str, Any]],
    index_of: dict[int, int],
    row_states: dict[str, RowState],
    door_cells: Mapping[int, frozenset[tuple[int, int]]],
    stripped_ce_ids: frozenset[int],
) -> RowFloor:
    ctx = ExtractContext(
        map_id=map_id, event_id=event_id, page_idx=page_idx, row_id=scope.row_id,
        event=event, map_data=map_data, common_events_by_id=common_events_by_id,
        door_cells=door_cells,
    )

    assertions: list[FloorAssertion] = [
        FloorAssertion(
            row_id=scope.row_id, kind="trigger", list_index=-1, code=None,
            params=make_params(trigger=trigger), tag="flow",
        ),
        FloorAssertion(
            row_id=scope.row_id, kind="completes", list_index=-1, code=None,
            params=(), tag="flow",
        ),
    ]
    refusals: list[FloorRefusal] = []

    a, r = _walk_commands(scope.commands, ctx, index_of, frozenset(), stripped_ce_ids)
    assertions.extend(a)
    refusals.extend(r)

    row_state = row_states.get(scope.row_id)
    if row_state is not None:
        scripts_by_index = {
            index_of.get(id(scope.commands[start]), -1): "\n".join(
                str((c.get("parameters") or [""])[0]) for c in scope.commands[start:end])
            for start, end in _script_blocks(scope.commands)
        }
        sa, sr = _state_assertions_for_row(
            scope.row_id, row_state, scripts_by_index,
            _later_arm_writes(scope.row_id, row_states))
        assertions.extend(sa)
        refusals.extend(sr)

    return RowFloor(
        row_id=scope.row_id, trigger=trigger,
        assertions=frozenset(assertions), refusals=tuple(refusals),
    )


def load_door_cells(build_dir: Any) -> dict[int, frozenset[tuple[int, int]]]:
    """The emitted layout's door-tile cells per Uranium map: the build's
    `warp_overrides.gen.json`, which is exactly the set the assembler stamps
    MB_NON_ANIMATED_DOOR on (`metadata_wiring.load_warp_overrides` -- fails
    loud when the file is absent, CLAUDE.md §4.5)."""
    from pathlib import Path

    from rpg2gba.tileset_converter.metadata_wiring import load_warp_overrides

    return {
        uid: frozenset(cells)
        for uid, cells in load_warp_overrides(Path(build_dir)).items()
    }


def floor_for_map(
    map_id: int,
    map_data: dict[str, Any],
    *,
    common_events: list[dict[str, Any]],
    switch_labels: dict[int, str],
    door_cells: Mapping[int, frozenset[tuple[int, int]]],
    connections: list[list[Any]] = (),
    stripped_ce_ids: frozenset[int] | None = None,
    resolved_rows: Mapping[str, RowState] | None = None,
) -> dict[str, RowFloor]:
    """Every row's `RowFloor` for one map's events, plus its `seam` and
    `terrain` rows (REDERIVATION_PLAN.md §16.3 C5 -- `beat_floor.terrain`).

    `connections` is `chapter_manifest.generator`'s own `connections.json`
    contents (a list of 6-tuples/lists); defaults to `()`, matching the
    generator's own behaviour when no `connections.json` exists (no seam
    rows) -- a caller with connections data available should pass it through
    rather than accept a silently seam-less floor.

    `door_cells` (required, no default) is the emitted layout's door-tile
    cells per Uranium map -- `load_door_cells(build_dir)` -- which the `warp`
    extractor needs for `arrives_on_door` (C5b). Required so a caller cannot
    silently get a floor where every arrival reads as plain floor.

    `stripped_ce_ids` (keyword-only, default `None`) is the set of
    whole-strip-listed common-event ids (`reference/strip_list.json`) whose
    code-117 calls are a no-op rather than inlined -- same treatment as
    `story_state.extract.extract_map`'s own parameter of the same name
    (C8 stage 4; assignments/C8/02_strip_honoring.md). `None` defaults via
    `stripped_ce_ids_for(_default_reference_dir())` so a caller who has not
    been updated still gets strip-honouring for free; an explicit
    `frozenset()` disables stripping entirely.

    `resolved_rows` replaces extraction-time row states with the story
    model's resolved ones (`lookup.resolved_rows`): a computed row's writes
    depend on state from earlier chapters, which extraction on one map
    cannot see, so without this its placeholder refusal refuses the floor.
    """
    sce = stripped_ce_ids if stripped_ce_ids is not None else stripped_ce_ids_for(
        _default_reference_dir())
    common_events_by_id = {ce["id"]: ce for ce in common_events}
    row_states = extract_map(
        map_id, map_data, common_events=common_events, switch_labels=switch_labels,
        stripped_ce_ids=sce)
    if resolved_rows:
        row_states.update({rid: rs for rid, rs in resolved_rows.items() if rid in row_states})

    # Diagonal-stair events are absorbed into `terrain` manifest rows, never
    # page rows (`chapter_manifest.generator._generate_page_rows`); they get
    # no floor, so the floor's row set matches the manifest's event rows.
    absorbed_event_ids = {cell.event_id for cell in detect_stair_cells(map_data)}

    result: dict[str, RowFloor] = {}
    for event in map_data.get("events", []) or []:
        event_id = event["id"]
        if event_id in absorbed_event_ids:
            continue
        for page_idx, page in enumerate(event.get("pages", []) or []):
            raw_commands = page.get("list") or []
            index_of = {id(cmd): idx for idx, cmd in enumerate(raw_commands)}
            trigger_raw = page.get("trigger")
            trigger = _TRIGGER_NAMES.get(trigger_raw, str(trigger_raw))

            scopes = list(iter_page_scopes(map_id, event, page_idx, page))
            for scope in scopes:
                result[scope.row_id] = _build_row_floor(
                    scope, trigger, map_id, event_id, page_idx, event, map_data,
                    common_events_by_id, index_of, row_states, door_cells, sce,
                )

            # `blocked_obstacle` is per PAGE: the capability head appears on
            # the trunk and in arms, so ask once on the trunk row with every
            # scope's commands unioned (an arm-only head is still caught).
            trunk = next(
                (s for s in scopes if parse_row_id(s.row_id).kind == "page"), None)
            if trunk is not None:
                page_commands = [c for s in scopes for c in s.commands]
                extra, refused = obstacle_assertions(trunk.row_id, event, page_commands)
                if extra or refused:
                    floor = result[trunk.row_id]
                    result[trunk.row_id] = replace(
                        floor,
                        assertions=floor.assertions | frozenset(extra),
                        refusals=floor.refusals + refused,
                    )

    result.update(seam_floors_for_map(map_id, list(connections)))
    result.update(stair_floors_for_map(map_id, map_data))

    return result


def floor_for_chapter(
    chapter_id: str, *, build_dir: Any, stripped_ce_ids: frozenset[int] | None = None,
) -> dict[str, RowFloor]:
    """Every row's `RowFloor` for one chapter's own maps, loaded the same
    way `story_state.model.build_chapter_stories` loads them (R11 C4
    design): `reference/chapters.json` for map membership,
    `build_dir/maps/MapNNN.json` per map, `build_dir/common_events.json`,
    and the tracked switch/variable label sidecars.

    `stripped_ce_ids` is threaded straight through to `floor_for_map`,
    which resolves the `None` default (see its own docstring)."""
    import json
    from pathlib import Path

    from rpg2gba.chapter_atlas.binding import load_binding

    build_dir = Path(build_dir)
    binding = load_binding(path=Path("reference/chapters.json"))
    maps = binding.chapter(chapter_id).maps

    common_events = json.loads((build_dir / "common_events.json").read_text(encoding="utf-8"))
    ref_dir = Path(__file__).resolve().parents[3] / "reference"
    switch_labels, _var_labels = load_label_tables(
        ref_dir / "uranium_switches.json", ref_dir / "uranium_variables.json")

    conn_path = build_dir / "connections.json"
    connections = json.loads(conn_path.read_text(encoding="utf-8")) if conn_path.exists() else []

    door_cells = load_door_cells(build_dir)
    from rpg2gba.beat_floor.lookup import resolved_rows

    resolved = resolved_rows(str(build_dir))

    merged: dict[str, RowFloor] = {}
    for map_id in maps:
        map_path = build_dir / "maps" / f"Map{map_id:03d}.json"
        map_data = json.loads(map_path.read_text(encoding="utf-8"))
        merged.update(floor_for_map(
            map_id, map_data, common_events=common_events, switch_labels=switch_labels,
            door_cells=door_cells, connections=connections, stripped_ce_ids=stripped_ce_ids,
            resolved_rows=resolved))

    return {rid: merged[rid] for rid in sorted(merged, key=row_id_sort_key)}
