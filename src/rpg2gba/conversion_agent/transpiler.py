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

import logging
import re
from dataclasses import dataclass, field

from rpg2gba.conversion_agent.deterministic import (
    _label_name,
    _translate_text,
    format_pory_string,
)
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, RegistryError
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

    def to_json(self) -> dict:
        return {
            "map_id": self.map_id,
            "event_id": self.event_id,
            "event_name": self.event_name,
            "page": self.page,
            "line": self.line,
            "command_code": self.command_code,
            "description": self.description,
            "reason": self.reason,
        }


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

    # per-event cursor, set by transpile_event
    map_id: int = 0
    event_id: int | None = None
    event_name: str = ""
    page_no: int = 0

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
        )
        self.unhandled.append(entry)
        return f"# UNHANDLED code {code}: {description}"

    # -- registry glue (every name goes through the registry, CLAUDE.md §6) --

    def flag_for_switch(self, switch_id: int) -> str | None:
        """Resolve a Uranium switch id to a FLAG_* name, minting from the
        developer-given label when one exists. ``None`` = unnamed or script
        switch → caller queues."""
        if self.registry.is_script_switch(switch_id):
            return None
        existing = self.registry.get_flag(switch_id)
        if existing is not None:
            return existing
        label = self.registry.label_for_switch(switch_id)
        if not label:
            return None
        try:
            return self.registry.propose_flag(switch_id, to_constant("FLAG", label))
        except RegistryError:
            return None

    def var_for_variable(self, variable_id: int) -> str | None:
        existing = self.registry.get_var(variable_id)
        if existing is not None:
            return existing
        label = self.registry.label_for_var(variable_id)
        if not label:
            return None
        try:
            return self.registry.propose_var(variable_id, to_constant("VAR", label))
        except RegistryError:
            return None

    def self_switch_flag(self, letter: str) -> str:
        assert self.event_id is not None
        return self.registry.mint_self_switch(self.map_id, self.event_id, letter)


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
        elif params[2] == 1:  # another variable
            other = ctx.var_for_variable(params[3])
            if other is None:
                return None
            rhs = f"var({other})"
        else:
            return None
        return f"var({name}) {op} {rhs}"

    if ctype == 2 and len(params) >= 3:  # self-switch [2, "A", 0=ON/1=OFF]
        letter = params[1]
        if not isinstance(letter, str):
            return None
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
    16: "face_down", 17: "face_left", 18: "face_right", 19: "face_up",
    25: "face_player", 26: "face_away_player",
    35: "lock_facing_direction", 36: "unlock_facing_direction",
}

# SOFT-C drops (moveroute_coverage.py dispositions): timing/physics toggles
# with no per-step GBA analog whose removal doesn't change where anyone ends
# up. 30 frequency · 37/38 through on/off (Essentials door-walk plumbing) ·
# 43 blend · 44 SE (audio is a visible drop elsewhere too).
_MOVE_DROP_CODES = frozenset({30, 37, 38, 43, 44})

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
        self._last_route_ok = False  # was the most recent 209 emitted?

    # -- leaf emitters -------------------------------------------------------

    def emit_nodes(self, nodes: list[Node]) -> list[str]:
        lines: list[str] = []
        for node in nodes:
            lines.extend(self.emit_node(node))
        return lines

    def emit_node(self, node: Node) -> list[str]:
        ctx = self.ctx
        cmd = node.cmd
        code = cmd.get("code", 0)
        params = cmd.get("parameters", [])

        if isinstance(node, TextRun):
            translated = _translate_text(node.text.strip())
            if translated is None:
                return [ctx.queue(
                    node.index, SHOW_TEXT,
                    f"dialogue with untranslated control code: {node.text[:120]!r}",
                )]
            return [f"msgbox({format_pory_string(translated)})"]

        if isinstance(node, IfNode):
            return self._emit_if(node)
        if isinstance(node, ChoiceNode):
            return self._emit_choice(node)
        if isinstance(node, LoopNode):
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
        if code == EXIT_EVENT:
            return ["end"]
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

    def _emit_choice(self, node: ChoiceNode) -> list[str]:
        params = node.cmd.get("parameters", [])
        choices = params[0] if params else []
        # v1 tier: the two-way YES/NO question via MSGBOX_YESNO. The prompt
        # text is the preceding msgbox — poryscript's msgbox(text, MSGBOX_YESNO)
        # form needs the text inline, so the driver-level idiom (merge with the
        # preceding TextRun) is deferred; emitting yesnobox on VAR_RESULT keeps
        # v1 self-contained.
        if [str(c).upper() for c in choices] == ["YES", "NO"]:
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

    def _emit_move_route(self, node: Node) -> list[str]:
        params = node.cmd.get("parameters", [])
        if len(params) < 2 or not isinstance(params[1], dict):
            self._last_route_ok = False
            return [self.ctx.queue(node.index, SET_MOVE_ROUTE, "malformed 209 params")]
        target, route = params[0], params[1]
        tokens = route_tokens(route)
        if tokens is None or not tokens:
            self._last_route_ok = False
            return [self.ctx.queue(
                node.index, SET_MOVE_ROUTE, _describe_route(route, target),
            )]
        label = f"{self.page_label}_Move{len(self.movements) + 1}"
        self.movements.append((label, tokens))
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
        self._last_route_ok = True
        return [f"applymovement({who}, {label})"]

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

    def _emit_script_call(self, node: Node) -> list[str]:
        # v1: the STRIP set from the validated ledger produces nothing; two
        # slice-proven idioms emit deterministically; everything else queues
        # (the idiom library grows per grill D8 on queue evidence).
        from rpg2gba.conversion_agent.deterministic import _DIALOGUE_STRIP_RE
        params = node.cmd.get("parameters", [])
        text = params[0] if params and isinstance(params[0], str) else ""
        if _DIALOGUE_STRIP_RE.match(text):
            return []

        # setTempSwitchOn("A") — set this event's temp switch (344× corpus).
        m = _SET_TEMP_SWITCH_RE.match(text)
        if m and self.ctx.event_id is not None:
            name = self.ctx.registry.mint_temp_switch(
                self.ctx.map_id, self.ctx.event_id, m.group(1)
            )
            return [f"setflag({name})"]

        # pbSetSelfSwitch(18, "A", true) — set ANOTHER event's self-switch on
        # this map (336× corpus).
        m = _SET_SELF_SWITCH_RE.match(text)
        if m:
            name = self.ctx.registry.mint_self_switch(
                self.ctx.map_id, int(m.group(1)), m.group(2)
            )
            return [f"setflag({name})" if m.group(3) == "true" else f"clearflag({name})"]

        return [self.ctx.queue(
            node.index, SCRIPT, f"script call: {text[:120]!r}",
        )]


# -- event-level API -----------------------------------------------------------


@dataclass
class TranspiledEvent:
    """One event's output: script blocks (+ any movement blocks), pre-joined."""

    text: str
    unhandled: list[QueueEntry]


def _render_movement(label: str, tokens: list[str]) -> str:
    inner = "\n".join(f"    {t}" for t in tokens)
    return f"movement {label} {{\n{inner}\n}}"


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
) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Body lines + movement blocks for one page. Queue entries land in ctx."""
    tree = parse_tree(page.get("list", []))
    emitter = _PageEmitter(ctx, page_label)
    body = emitter.emit_nodes(tree)
    return body, emitter.movements


def transpile_event(map_id: int, event: dict, ctx: TranspileContext) -> TranspiledEvent:
    """Transpile every page of one map event into script (+movement) blocks."""
    ctx.map_id = map_id
    ctx.event_id = event.get("id")
    ctx.event_name = event.get("name", "")
    before = len(ctx.unhandled)

    name = _label_name(event.get("name", ""))
    blocks: list[str] = []
    for page_no, page in enumerate(event.get("pages", []), start=1):
        ctx.page_no = page_no
        label = _page_label(map_id, event, page_no)
        body, movements = transpile_page(page, ctx, label)
        trigger = page.get("trigger")
        if body and trigger == ACTION_BUTTON_TRIGGER:
            body = ["lock", "faceplayer", *body, "release"]
        elif body and trigger in (1, 2):
            # player-touch / event-touch cutscene: freeze the player while
            # the script runs (validated Opus output, e.g. Map001 doormats).
            body = ["lock", *body, "release"]
        body = body or []
        body.append("end")
        inner = "\n".join(f"    {ln}" for ln in body)
        header = f"# {name}\n" if name and not name.startswith("EV") else ""
        blocks.append(f"{header}script {label} {{\n{inner}\n}}")
        for m_label, tokens in movements:
            blocks.append(_render_movement(m_label, tokens))

    return TranspiledEvent(
        text="\n\n".join(blocks),
        unhandled=ctx.unhandled[before:],
    )
