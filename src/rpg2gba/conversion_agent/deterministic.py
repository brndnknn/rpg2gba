"""Deterministic pre-filter for the Phase 4 conversion pipeline.

Fully-mechanical events — whose entire Poryscript is a direct structural read of
the event JSON — are translated here by lookup instead of spawning the LLM
(PHASE4_DETERMINISTIC_PLAN.md). Every classifier is a pure function returning a
Poryscript string on a confident match, or ``None`` to fall through to the LLM
path; **none of them raise** (the dispatcher swallows any unexpected error into a
fall-through). The orchestrator runs the result through the compile-gate and the
self/temp-switch mint before accepting it, so a wrong guess is caught and a
non-match costs nothing.

Why this is safe (plan §1): for these events the LLM adds nothing — the output is
fully determined by the input — so the deterministic path is cheaper, faster, and
more consistent, and the existing compile-gate is the safety net.

Design notes that differ from the plan's first draft, grounded in the real corpus
and the §9-gate-approved Map002 output:

* **The lock/faceplayer/release wrapper tracks the event trigger, not codes
  5/6/7** (which do not exist in RMXP data). Opus wraps every Action-Button NPC
  (trigger 0) in ``lock``/``faceplayer``/``release``; the dialogue-family
  classifiers only claim trigger-0 events and emit that wrapper.
* **Dialogue text is deterministic only for plain text plus codes whose mapping
  ``system.md`` prescribes verbatim.** The player-name placeholder ``\\PN`` →
  ``{PLAYER}`` is such a code (substituted in ``_translate_text``). Every other
  Essentials backslash escape (``\\g[..]`` gender branch, ``\\sign[..]`` sign
  window, colour/pause codes …) needs the agent's *judgement* to translate, so the
  event falls through to the LLM — poryscript passes codes through verbatim and is
  not a safety net here.
* **Script-block labels** are ``Map{map:03d}_{event_name}_Page{n}``. Event names
  that are not valid identifiers (``"Trainer(4)"``) are deterministically
  sanitized; this need not match the LLM because each event is owned by exactly
  one conversion path (the deterministic check runs before the memo/LLM path).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rpg2gba.conversion_agent.flag_registry import self_switch_flag_name
from rpg2gba.pbs_converter._naming import to_constant

# -- RMXP command codes (reference/rgss_event_commands.md) --------------------
SHOW_TEXT = 101
SHOW_TEXT_CONT = 401
CONDITIONAL_BRANCH = 111
ELSE_BRANCH = 411  # RMXP conditional "Else"
BRANCH_END = 412  # RMXP conditional "Branch End"
CALL_COMMON_EVENT = 117
CONTROL_SELF_SWITCH = 123
TRANSFER_PLAYER = 201
SCRIPT = 355
SCRIPT_CONT = 655
COMMENT = 108
COMMENT_CONT = 408
WAIT = 106  # RMXP "Wait N frames" — pure pacing, no GBA equivalent
PLAY_SE = 250  # RMXP "Play SE" — a sound effect; cosmetic plumbing in a dialogue

# Native RMXP commands that carry no game state and produce no Poryscript in a
# dialogue context. Frozen-Opus drops both (FABLES gate G2, 2026-06-12: Map174 ev9
# dropped Wait(106), Map031 ev9 dropped SE(250)+pbCallBub, both dialogue-only). They
# are tolerated ONLY on a page that also has real dialogue — a page whose sole
# content is a stripped SE/Wait is a cosmetic-only event whose Opus output is
# unvalidated (declined near-miss Tier 2), so it falls through to the LLM.
_DIALOGUE_PLUMBING_CODES = frozenset({WAIT, PLAY_SE})

ACTION_BUTTON_TRIGGER = 0  # RMXP page trigger: "talk to" (the NPC case)

# STRIP-classified Script (355/655) calls that carry no game state and produce no
# output (reference/uranium_script_calls.md). Anchored at the start of the call
# string. Extend only with calls verified STRIP in that table.
# The identifier-terminated calls take a trailing ``\b`` so a prefix can't match
# (``pbSEPlay`` must not claim ``pbSEPlayWhatever``); the ``need_refresh =``
# assignment ends in ``=`` (a non-word char, so ``\b`` would never follow) and is
# its own branch without the anchor.
_DIALOGUE_STRIP_RE = re.compile(
    r"^\s*(?:"
    r"(?:"
    r"pbCallBub"
    r"|set_fog2"
    r"|XInput\.vibrate"
    r"|pbSEPlay"
    r"|pbPlayCry"
    r"|\$scene\.spriteset\.addUserSprite"
    r"|(?:Kernel\.)?pbRemoveDependency2"
    r"|(?:Kernel\.)?pbAddDependency2"
    r"|Kernel\.pbSetPokemonCenter"
    r")\b"
    r"|\$game_map\.need_refresh\s*="
    r")"
)

# Prescribed Essentials→poryscript text substitutions. Only codes whose mapping
# ``system.md`` states verbatim go here, so the deterministic output provably
# matches what the frozen agent is told to emit. Currently just the player-name
# placeholder (system.md "Dialogue": ``\PN`` → ``{PLAYER}``). Applied in flush().
_TEXT_SUBS: tuple[tuple[re.Pattern[str], str], ...] = ((re.compile(r"\\PN"), "{PLAYER}"),)

# After the prescribed substitutions are removed, dialogue is deterministically
# translatable only if its remaining control codes are the pokeemerald-safe line
# breaks ``\n`` / ``\l`` / ``\p`` (which poryscript emits verbatim). Any other
# backslash code is Essentials-specific and needs the agent's judgement to
# translate — ``\sign[..]`` (sign window → MSGBOX_SIGN, not yet prescribed),
# ``\g[m,f]`` (gender branch), colour/pause (``\.``) codes — so the event falls
# through to the LLM. Braces are unsafe too (poryscript placeholders), which is why
# the ``\PN`` → ``{PLAYER}`` substitution is applied *after* this scan, never
# before. The lookahead is case-sensitive: ``\p`` (paragraph) is safe.
_UNSAFE_TEXT_RE = re.compile(r"\\(?![nlp])|[{}]")

# Matches a leading \sign[...] control code anchored at the start of dialogue text.
_SIGN_PREFIX_RE = re.compile(r"^\\sign\[[^\]]*\]")


def _translate_text(text: str) -> str | None:
    """Apply the prescribed substitutions, or ``None`` if any unhandled code remains.

    The safety scan runs on a copy with every prescribed code *deleted* (not yet
    substituted) so the braces those substitutions introduce can't trip the
    brace guard; only then is the real substitution applied to the returned text.
    """
    scan = text
    for pat, _repl in _TEXT_SUBS:
        scan = pat.sub("", scan)
    if _UNSAFE_TEXT_RE.search(scan):
        return None
    out = text
    for pat, repl in _TEXT_SUBS:
        out = pat.sub(repl, out)
    return out

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# -- string + label helpers ---------------------------------------------------


def format_pory_string(text: str) -> str:
    """Wrap dialogue in a poryscript double-quoted string, escaping only ``"``.

    Backslashes are intentionally *not* escaped: the text-safety guard
    (``_UNSAFE_TEXT_RE``) rejects any text containing a backslash before it
    reaches here, so none survive — and were the guard ever loosened to admit the
    pokeemerald-safe ``\\n``/``\\l``/``\\p`` breaks, those must pass through, not
    be doubled.
    """
    return '"' + text.replace('"', '\\"') + '"'


def _label_name(name: str) -> str:
    """A poryscript-identifier form of an event name (``"Trainer(4)"`` → ``Trainer_4``)."""
    name = name or ""
    if _IDENT_RE.match(name):
        return name
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = "EV_" + cleaned
    return cleaned


def _page_label(map_id: int, event: dict, page_no: int) -> str:
    return f"Map{int(map_id):03d}_{_label_name(event.get('name', ''))}_Page{page_no}"


def _block(label: str, lines: list[str]) -> str:
    """Render one ``script <label> { ... }`` block with 4-space-indented body."""
    inner = "\n".join(f"    {ln}" for ln in lines)
    return f"script {label} {{\n{inner}\n}}"


def _talk_block(label: str, body: list[str]) -> str:
    """A trigger-0 NPC page: wrap a non-empty body in lock/faceplayer/release.

    An empty page (no statements) is a bare ``end`` block — matches the
    gate-approved output for content-less pages (e.g. Map002 EV011 Page1).
    """
    if not body:
        return _block(label, ["end"])
    return _block(label, ["lock", "faceplayer", *body, "release", "end"])


def _sign_block(label: str, body: list[str]) -> str:
    """A signpost page: lock/release with no faceplayer (validated Opus output)."""
    if not body:
        return _block(label, ["end"])
    return _block(label, ["lock", *body, "release", "end"])


# -- dialogue-family page walker (classifiers 1–3) ----------------------------


def _dialogue_body(
    page: dict,
    *,
    map_id: int,
    event_id: int,
    allow_call: bool = False,
    allow_self_switch: bool = False,
    strip_sign: bool = False,
) -> list[str] | None:
    """Ordered body statements for a dialogue-family page, or ``None`` to bail.

    Walks the page command list in order, collapsing each Show Text run
    (101 + 401 continuations) into one ``msgbox`` and interleaving the optional
    Call Common Event (117) and Control Self Switch (123) statements in source
    position. Returns ``None`` if any command is outside the allowed set, if a
    355/655 Script call is not STRIP-classified, or if any dialogue carries an
    Essentials control code (fall through to the LLM).
    """
    body: list[str] = []
    buf: list[str] = []
    unsafe = False
    # Pre-scan: plumbing codes (Wait/SE) are dropped only when the page actually
    # speaks. A page that would be content-less but for a stripped SE/Wait is the
    # unvalidated cosmetic-only class — bail so it reaches the LLM (see gate G2).
    has_dialogue = any(
        cmd.get("code") == SHOW_TEXT for cmd in page.get("list", [])
    )

    def flush() -> None:
        nonlocal buf, unsafe
        text = "".join(buf).strip()
        buf = []
        if not text:
            return
        if strip_sign:
            text = _SIGN_PREFIX_RE.sub("", text, count=1)
            if '"' in text:
                unsafe = True
                return
        translated = _translate_text(text)
        if translated is None:
            unsafe = True
            return
        body.append(f"msgbox({format_pory_string(translated)})")

    for cmd in page.get("list", []):
        code = cmd.get("code", 0)
        params = cmd.get("parameters", [])
        if code == SHOW_TEXT:
            flush()
            buf = [params[0] if params else ""]
        elif code == SHOW_TEXT_CONT:
            buf.append(params[0] if params else "")
        elif code == 0:
            flush()
        elif code == CALL_COMMON_EVENT and allow_call:
            flush()
            ce_id = params[0] if params else 0
            if not isinstance(ce_id, int) or ce_id <= 0:
                return None
            body.append(f"call CommonEvent_{ce_id:03d}")
        elif code == CONTROL_SELF_SWITCH and allow_self_switch:
            flush()
            if not params or not isinstance(params[0], str):
                return None
            letter = params[0]
            value = params[1] if len(params) > 1 else 0
            name = self_switch_flag_name(map_id, event_id, letter)
            body.append(f"setflag({name})" if value == 0 else f"clearflag({name})")
        elif code in (SCRIPT, SCRIPT_CONT):
            p = params[0] if params else ""
            if isinstance(p, str) and _DIALOGUE_STRIP_RE.match(p):
                continue  # STRIP — no output
            return None
        elif code in _DIALOGUE_PLUMBING_CODES:
            if not has_dialogue:
                return None  # cosmetic-only (no text) — unvalidated, defer to LLM
            continue  # Wait/SE alongside dialogue — drop as plumbing (gate G2)
        else:
            return None

    flush()
    if unsafe:
        return None
    return body


def _all_pages_action_button(event: dict) -> bool:
    pages = event.get("pages", [])
    return bool(pages) and all(pg.get("trigger") == ACTION_BUTTON_TRIGGER for pg in pages)


def _has_sign_prefix(event: dict) -> bool:
    """True if any page's Show-Text (101/401) run text contains a \\sign[ code."""
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code") in (SHOW_TEXT, SHOW_TEXT_CONT):
                params = cmd.get("parameters", [])
                first = params[0] if params else ""
                if isinstance(first, str) and "\\sign[" in first:
                    return True
    return False


# -- Classifier 1: Pure Dialogue (plan §4) ------------------------------------


def classify_pure_dialogue(map_id: int, event: dict, ctx: "Context | None" = None) -> str | None:
    """A talk NPC whose every page is just dialogue (+ STRIP script calls)."""
    if not _all_pages_action_button(event):
        return None
    blocks: list[str] = []
    for i, page in enumerate(event.get("pages", []), start=1):
        body = _dialogue_body(page, map_id=map_id, event_id=event["id"])
        if body is None:
            return None
        blocks.append(_talk_block(_page_label(map_id, event, i), body))
    return "\n\n".join(blocks)


# -- Classifier 7: Sign Dialogue (plan §12) -----------------------------------


def classify_sign_dialogue(map_id: int, event: dict, ctx: "Context | None" = None) -> str | None:
    """A signpost: action-button dialogue whose text leads with \\sign[..].

    Strips the prefix and emits a plain msgbox in a no-faceplayer lock/release
    block (validated frozen-Opus output, plan §12 — no MSGBOX_SIGN, no faceplayer).
    Claims only events that actually carry a \\sign code; text containing a quote
    falls through to the LLM (Opus's quote-drop rule is unconfirmed)."""
    if not _all_pages_action_button(event):
        return None
    if not _has_sign_prefix(event):
        return None
    blocks: list[str] = []
    for i, page in enumerate(event.get("pages", []), start=1):
        body = _dialogue_body(page, map_id=map_id, event_id=event["id"], strip_sign=True)
        if body is None:
            return None
        blocks.append(_sign_block(_page_label(map_id, event, i), body))
    return "\n\n".join(blocks)


# -- Classifier 2: Call Common Event (plan §5) --------------------------------


def classify_call_common_event(
    map_id: int, event: dict, ctx: "Context | None" = None
) -> str | None:
    """A talk NPC that delegates to a common event (code 117), with only
    dialogue + STRIP script calls alongside. Claims only events that actually
    contain a call — pure-dialogue events stay with Classifier 1."""
    if not _all_pages_action_button(event):
        return None
    saw_call = False
    blocks: list[str] = []
    for i, page in enumerate(event.get("pages", []), start=1):
        body = _dialogue_body(page, map_id=map_id, event_id=event["id"], allow_call=True)
        if body is None:
            return None
        if any(line.startswith("call CommonEvent_") for line in body):
            saw_call = True
        blocks.append(_talk_block(_page_label(map_id, event, i), body))
    if not saw_call:
        return None
    return "\n\n".join(blocks)


# -- Classifier 3: Self-Switch Dialogue (plan §6) -----------------------------


def classify_self_switch_dialogue(
    map_id: int, event: dict, ctx: "Context | None" = None
) -> str | None:
    """A talk NPC that is pure dialogue plus a self-switch set (code 123), no
    conditional branch. Claims only events that actually set a self-switch —
    pure-dialogue events stay with Classifier 1."""
    if not _all_pages_action_button(event):
        return None
    saw_switch = False
    blocks: list[str] = []
    for i, page in enumerate(event.get("pages", []), start=1):
        body = _dialogue_body(page, map_id=map_id, event_id=event["id"], allow_self_switch=True)
        if body is None:
            return None
        if any(line.startswith(("setflag(", "clearflag(")) for line in body):
            saw_switch = True
        blocks.append(_talk_block(_page_label(map_id, event, i), body))
    if not saw_switch:
        return None
    return "\n\n".join(blocks)


# -- Classifier 8: Ground Item / pbItemBall (iterative roadmap Group 1) --------

# The Essentials ground-item idiom: a script-type (param[0] == 12) conditional
# branch testing ``pbItemBall(::PBItems::SYMBOL)``. ``pbItemBall`` gives the item
# (quantity 1), shows its own "found" fanfare message, and returns success; the
# event sets a self-switch so the pickup can't repeat, with an empty else. All 230
# corpus instances share the exact page-1 shape (111 → 123 → 411 empty → 412) with
# no quantity argument; frozen-Opus collapses it to a bare ``giveitem`` (pokeemerald
# handles the bag-full case the conditional guarded). No ``faceplayer`` — it is a
# pickup, not an NPC talk (validated: Map007 EV006/011/012 et al.).
_ITEMBALL_RE = re.compile(r"^\s*(?:Kernel\.)?pbItemBall\(\s*::PBItems::(\w+)\s*\)\s*$")


def classify_ground_item(
    map_id: int, event: dict, ctx: "Context | None" = None
) -> str | None:
    """A ground-item pickup whose page 1 is ``if pbItemBall(::PBItems::X)`` setting
    a self-switch (empty else); any later page is the empty post-pickup gate.

    Emits the canonical pokeemerald ground-item idiom — lock / giveitem(ITEM_X, 1)
    / setflag(<self-switch>) / release / end, plus a bare ``end`` block per gate
    page. Needs ``ctx.items`` to resolve the PBItems symbol to its ``ITEM_*``
    constant; an unknown symbol or any structural deviation falls through to the
    LLM."""
    if ctx is None or not ctx.items:
        return None
    if not _all_pages_action_button(event):
        return None
    pages = event.get("pages", [])
    if not pages:
        return None
    symbol: str | None = None
    letter: str | None = None
    sw_value = 0
    for cmd in pages[0].get("list", []):
        code = cmd.get("code", 0)
        if code == CONDITIONAL_BRANCH:
            if symbol is not None:
                return None  # a second branch — not the bare pickup idiom
            params = cmd.get("parameters", [])
            if len(params) < 2 or params[0] != 12 or not isinstance(params[1], str):
                return None  # not a script-type conditional
            m = _ITEMBALL_RE.match(params[1])
            if m is None:
                return None  # script-type branch, but not pbItemBall
            symbol = m.group(1)
        elif code == CONTROL_SELF_SWITCH:
            if letter is not None:
                return None
            params = cmd.get("parameters", [])
            if not params or not isinstance(params[0], str):
                return None
            letter = params[0]
            sw_value = params[1] if len(params) > 1 else 0
        elif code in (0, ELSE_BRANCH, BRANCH_END, COMMENT, COMMENT_CONT):
            continue  # control-flow scaffolding / blanks — no output
        else:
            return None  # any other command — defer to the LLM
    if symbol is None or letter is None:
        return None
    const = ctx.items.get(symbol)
    if const is None:
        return None  # unknown item symbol — fall through
    for page in pages[1:]:  # gate pages must carry no real commands
        for cmd in page.get("list", []):
            if cmd.get("code", 0) not in (0, COMMENT, COMMENT_CONT):
                return None
    flag = self_switch_flag_name(map_id, event["id"], letter)
    set_line = f"setflag({flag})" if sw_value == 0 else f"clearflag({flag})"
    blocks = [
        _block(
            _page_label(map_id, event, 1),
            ["lock", f"giveitem({const}, 1)", set_line, "release", "end"],
        )
    ]
    for i in range(2, len(pages) + 1):
        blocks.append(_block(_page_label(map_id, event, i), ["end"]))
    return "\n\n".join(blocks)


# -- Classifier 9: Poké Mart / pbPokemonMart (iterative roadmap Group 1) -------

# Items inside ``pbPokemonMart([...])`` — both ``::PBItems::X`` and ``PBItems::X``
# spellings occur (Map004 EV002 uses the bare ``PBItems::POKeBALL`` form, incl. the
# known ``POKeBALL`` typo). Order is preserved in the emitted mart list.
_PBPOKEMART_ITEM_RE = re.compile(r"(?:::)?PBItems::(\w+)")
_PBPOKEMART_LIST_RE = re.compile(r"pbPokemonMart\(\s*\[(.*)\]", re.DOTALL)


def classify_pokemart(map_id: int, event: dict, ctx: "Context | None" = None) -> str | None:
    """A mart clerk whose page-1 sole content is ``pbPokemonMart([item, …])``.

    Emits the pokeemerald shop idiom — lock / faceplayer / pokemart(<label>) /
    release / end — plus a ``mart <label> { ITEM_* … }`` block listing the items
    in source order (byte-for-byte vs frozen-Opus, Map004 EV002). Needs
    ``ctx.items`` to resolve every symbol; an unresolved item or any non-mart
    command on the page falls through to the LLM."""
    if ctx is None or not ctx.items:
        return None
    if not _all_pages_action_button(event):
        return None
    pages = event.get("pages", [])
    if not pages:
        return None
    parts: list[str] = []
    for cmd in pages[0].get("list", []):
        code = cmd.get("code", 0)
        if code in (SCRIPT, SCRIPT_CONT):
            p = cmd.get("parameters") or [""]
            parts.append(p[0] if p else "")
        elif code in (0, COMMENT, COMMENT_CONT):
            continue
        else:
            return None  # anything but the mart call + plumbing — defer to the LLM
    call = "".join(parts)
    m = _PBPOKEMART_LIST_RE.search(call)
    if m is None:
        return None
    consts: list[str] = []
    for sym in _PBPOKEMART_ITEM_RE.findall(m.group(1)):
        const = ctx.items.get(sym)
        if const is None:
            return None  # unresolved item symbol — fall through
        consts.append(const)
    if not consts:
        return None
    for page in pages[1:]:  # any extra page must carry no real commands
        for cmd in page.get("list", []):
            if cmd.get("code", 0) not in (0, COMMENT, COMMENT_CONT):
                return None
    mart_label = f"Map{int(map_id):03d}_{_label_name(event.get('name', ''))}_Mart"
    script = _block(
        _page_label(map_id, event, 1),
        ["lock", "faceplayer", f"pokemart({mart_label})", "release", "end"],
    )
    mart_inner = "\n".join(f"    {const}" for const in consts)
    blocks = [script, f"mart {mart_label} {{\n{mart_inner}\n}}"]
    for i in range(2, len(pages) + 1):
        blocks.append(_block(_page_label(map_id, event, i), ["end"]))
    return "\n\n".join(blocks)


# -- Classifier 4: Simple Warp (plan §7) --------------------------------------

_WARP_SAFE_CODES = {0, 5, 6, 7, 106, 201, 221, 222, 223, 224, 249, 250}
# 0 term · 5/6/7 lock/face/release (absent in corpus, allowed) · 106 wait ·
# 201 transfer · 221/222 transition · 223 tone-fade · 224 flash · 249/250 ME/SE


def classify_simple_warp(
    map_id: int, event: dict, ctx: "Context | None" = None
) -> "DetResult | None":
    """A single-page doormat warp: code 201 transfer plus only plumbing (fade/wait/SE).

    Emits the canonical pokeemerald scripted-warp idiom (lockall / warp / waitstate /
    releaseall) with a ``MAP_URANIUM_<N>`` placeholder, and queues one unhandled entry
    so Phase 5 resolves the real map constant."""
    pages = event.get("pages", [])
    if len(pages) != 1:
        return None
    warp_cmd = None
    for cmd in pages[0].get("list", []):
        code = cmd.get("code", 0)
        if code == TRANSFER_PLAYER:
            if warp_cmd is not None:
                return None  # 2+ warps → fall through to the LLM
            warp_cmd = cmd
        elif code in _WARP_SAFE_CODES:
            continue
        elif code in (SCRIPT, SCRIPT_CONT):
            params = cmd.get("parameters") or [""]
            first = params[0] if params else ""
            if isinstance(first, str) and _DIALOGUE_STRIP_RE.match(first):
                continue  # stateless STRIP call (audio etc.) — no output
            return None
        else:
            return None
    if warp_cmd is None:
        return None
    params = warp_cmd.get("parameters", [])
    # RMXP 201 params: [mode, map_id, x, y, direction, fade]. mode 0 = literal target;
    # mode 1 = variable-indirection (target is a variable id) → cannot resolve, bail.
    if len(params) < 4 or params[0] != 0:
        return None
    target_map, x, y = params[1], params[2], params[3]
    if not all(isinstance(v, int) for v in (target_map, x, y)):
        return None
    script = _block(
        _page_label(map_id, event, 1),
        [
            "lockall",
            f"warp(MAP_URANIUM_{target_map}, {x}, {y})",
            "waitstate",
            "releaseall",
            "end",
        ],
    )
    entry = {
        "command_code": TRANSFER_PLAYER,
        "page": 1,
        "description": (
            f"Transfer Player to Uranium map {target_map} at ({x}, {y}) — emitted as "
            f"placeholder warp(MAP_URANIUM_{target_map}, {x}, {y}); the real pokeemerald "
            f"MAP_* constant must be resolved in Phase 5."
        ),
    }
    return DetResult(script, [entry])


# -- Classifier 6: Trainer Battle (plan §9) -----------------------------------

# STRIP-classified trainer-scripting calls (in addition to _DIALOGUE_STRIP_RE).
_TRAINER_STRIP_RE = re.compile(
    r"^\s*(?:Kernel\.)?(?:pbTrainerIntro|pbNoticePlayer|pbTrainerEnd)\b"
)

_PAGE1_TRAINER_ALLOWED = {0, 5, 6, 7, 101, 401, 108, 408, 123, 355, 655, 111, 412}
_PAGE2_TRAINER_ALLOWED = {0, 5, 6, 7, 101, 401, 355, 655}


def _is_trainer_strip(p: object) -> bool:
    """True if a Script (355/655) parameter is a STRIP call in the trainer context."""
    return isinstance(p, str) and (
        bool(_DIALOGUE_STRIP_RE.match(p)) or bool(_TRAINER_STRIP_RE.match(p))
    )


def classify_trainer_battle(
    map_id: int, event: dict, ctx: "Context | None" = None
) -> str | None:
    """A route trainer event: exactly 2 pages, single pbTrainerBattle, emits
    ``trainerbattle_single``.  Returns ``None`` on any mismatch (falls through
    to the LLM).
    """
    pages = event.get("pages", [])
    if len(pages) != 2:
        return None

    # Count code-111 across BOTH pages; exactly one allowed, must be on page 1
    branch_count = 0
    branch_cmd: dict | None = None
    branch_page: int | None = None
    for pg_idx, page in enumerate(pages, start=1):
        for cmd in page.get("list", []):
            if cmd.get("code") == CONDITIONAL_BRANCH:
                branch_count += 1
                branch_page = pg_idx
                branch_cmd = cmd
    if branch_count != 1 or branch_page != 1 or branch_cmd is None:
        return None

    # Branch params: [0]==12 and [1] must contain pbTrainerBattle( (not double)
    b_params = branch_cmd.get("parameters", [])
    if len(b_params) < 2 or b_params[0] != 12:
        return None
    call: object = b_params[1]
    if not isinstance(call, str):
        return None
    if "pbTrainerBattle(" not in call or "pbDoubleTrainerBattle" in call:
        return None

    # Page 1 must have code-123 with params ["A", 0]
    page1 = pages[0]
    has_self_switch = False
    for cmd in page1.get("list", []):
        if cmd.get("code") == CONTROL_SELF_SWITCH:
            p = cmd.get("parameters", [])
            if p and p[0] == "A" and (len(p) < 2 or p[1] == 0):
                has_self_switch = True
    if not has_self_switch:
        return None

    # Validate every page-1 command code
    for cmd in page1.get("list", []):
        code = cmd.get("code", 0)
        if code not in _PAGE1_TRAINER_ALLOWED:
            return None
        if code in (COMMENT, COMMENT_CONT):
            continue
        if code in (SCRIPT, SCRIPT_CONT):
            p = cmd.get("parameters", [""])
            if not _is_trainer_strip(p[0] if p else ""):
                return None

    # Validate every page-2 command code
    page2 = pages[1]
    for cmd in page2.get("list", []):
        code = cmd.get("code", 0)
        if code not in _PAGE2_TRAINER_ALLOWED:
            return None
        if code in (SCRIPT, SCRIPT_CONT):
            p = cmd.get("parameters", [""])
            if not _is_trainer_strip(p[0] if p else ""):
                return None

    # --- Parse the trainer call ------------------------------------------------
    # class symbol
    m_class = re.search(r"(?:::)?PBTrainers::(\w+)", call)
    if not m_class:
        return None
    sym = m_class.group(1)
    class_const = to_constant("TRAINER_CLASS", sym)

    # defeat text (inside _I("..."))
    m_defeat = re.search(r'_I\("((?:[^"\\]|\\.)*)"\)', call)
    defeat_raw = m_defeat.group(1) if m_defeat else ""

    # party_id: strip the _I("...") blob first so its commas don't confuse split
    cleaned_call = re.sub(r'_I\("(?:[^"\\]|\\.)*"\)', "_I", call)
    m_inner = re.search(r"pbTrainerBattle\((.*?)\)\s*$", cleaned_call, re.DOTALL)
    if not m_inner:
        return None
    args = [a.strip() for a in m_inner.group(1).split(",")]
    # args: [class_expr, name_str, _I, canlose, party_id, ...]
    party_id = 0
    if len(args) >= 5 and args[4].isdigit():
        party_id = int(args[4])

    # trainer name (first quoted string in the call)
    m_name = re.search(r'"([^"]*)"', call)
    if not m_name:
        return None
    name = m_name.group(1)

    # --- Lookup in context -----------------------------------------------------
    if ctx is None:
        return None
    trainer_const = ctx.trainers.get((class_const, name, party_id))
    if trainer_const is None:
        return None

    # --- Collect intro text from page-1 Show-Text run -------------------------
    intro_parts: list[str] = []
    in_intro = False
    for cmd in page1.get("list", []):
        code = cmd.get("code", 0)
        params = cmd.get("parameters", [])
        if code == SHOW_TEXT:
            in_intro = True
            intro_parts = [params[0] if params else ""]
        elif code == SHOW_TEXT_CONT and in_intro:
            intro_parts.append(params[0] if params else "")
        elif code != SHOW_TEXT_CONT:
            in_intro = False
    intro_raw = "".join(intro_parts).strip()

    # --- Collect post-battle text from page-2 Show-Text run -------------------
    post_parts: list[str] = []
    in_post = False
    for cmd in page2.get("list", []):
        code = cmd.get("code", 0)
        params = cmd.get("parameters", [])
        if code == SHOW_TEXT:
            in_post = True
            post_parts = [params[0] if params else ""]
        elif code == SHOW_TEXT_CONT and in_post:
            post_parts.append(params[0] if params else "")
        elif code != SHOW_TEXT_CONT:
            in_post = False
    post_raw = "".join(post_parts).strip()

    # --- Translate texts -------------------------------------------------------
    intro = _translate_text(intro_raw)
    if intro is None:
        return None
    defeat = _translate_text(defeat_raw)
    if defeat is None:
        return None
    post: str | None = None
    if post_raw:
        post = _translate_text(post_raw)
        if post is None:
            return None

    # --- Emit ------------------------------------------------------------------
    battle_line = (
        f"trainerbattle_single({trainer_const},"
        f" {format_pory_string(intro)}, {format_pory_string(defeat)})"
    )
    lines: list[str] = [battle_line]
    if post is not None:
        lines.append(f"msgbox({format_pory_string(post)})")
    lines += ["release", "end"]
    return _block(_page_label(map_id, event, 1), lines)


# -- context + dispatcher -----------------------------------------------------


@dataclass(frozen=True)
class DetResult:
    """A deterministic match: the Poryscript plus any unhandled queue entries.

    Classifiers may return a bare ``str`` (script only) or a ``DetResult`` when they
    also need to queue an ``unhandled.jsonl`` entry (e.g. a warp placeholder that
    Phase 5 must resolve). ``try_deterministic`` normalizes the bare-``str`` form."""

    script: str
    unhandled: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Context:
    """Lookup tables the data-driven classifiers (item ball, trainer) need.

    Empty by default so the dialogue/warp classifiers (which need no external
    data) work without it; populated by ``load_context`` for a real run.
    """

    items: dict[str, str] = field(default_factory=dict)  # Essentials symbol -> ITEM_*
    trainers: dict[tuple[str, str, int], str] = field(default_factory=dict)


def _load_item_symbols(reference_dir: Path) -> dict[str, str]:
    """Map each Essentials ``PBItems`` symbol → its ``ITEM_*`` constant.

    Uses the same naming rule as ``pbs_converter.items._ItemResolver.constant``
    (display name through ``to_constant``, internal-symbol fallback), so the
    constant the ground-item classifier emits is exactly the one Phase 2 defined.
    Tolerant: a missing/unreadable sidecar yields ``{}``."""
    try:
        internal = json.loads(
            (reference_dir / "item_internal_names.json").read_text(encoding="utf-8")
        )
        names = json.loads((reference_dir / "item_names.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for iid, sym in internal.items():
        out[sym] = to_constant("ITEM", names.get(iid) or sym)
    return out


def load_context(*, reference_dir: Path, intermediate_dir: Path) -> Context:
    """Build the data-driven classifiers' lookup tables from Phase-2 outputs.

    Tolerant by design: a missing/unreadable file yields an empty table, and the
    classifier that needs it then falls through to the LLM rather than failing the
    run.
    """
    trainers: dict[tuple[str, str, int], str] = {}
    try:
        data = json.loads((intermediate_dir / "trainers.json").read_text(encoding="utf-8"))
        for const, v in data["trainers"].items():
            trainers[(v["trainer_class"], v["name"], v["party_id"])] = const
    except Exception:
        pass
    return Context(trainers=trainers, items=_load_item_symbols(reference_dir))


# Classifiers are tried in this order; the first non-None wins. Order follows the
# plan (most general dialogue first); detection is strict enough that overlaps do
# not occur, but order still matters for events a looser classifier could claim.
_CLASSIFIERS: list[
    Callable[[int, dict, "Context | None"], "str | DetResult | None"]
] = [
    classify_pure_dialogue,
    classify_sign_dialogue,  # Classifier 7
    classify_call_common_event,  # Classifier 2
    classify_self_switch_dialogue,  # Classifier 3
    classify_ground_item,  # Classifier 8
    classify_pokemart,  # Classifier 9
    classify_simple_warp,  # Classifier 4
    classify_trainer_battle,  # Classifier 6
]


def try_deterministic(
    map_id: int, event: dict, ctx: "Context | None" = None
) -> "DetResult | None":
    """Try each classifier in order; return the first match (normalized to a
    ``DetResult``), or ``None`` to fall through to the LLM."""
    for classify in _CLASSIFIERS:
        try:
            out = classify(map_id, event, ctx)
        except Exception:  # a classifier must never abort the run — fall through
            out = None
        if out is None:
            continue
        return out if isinstance(out, DetResult) else DetResult(out)
    return None
