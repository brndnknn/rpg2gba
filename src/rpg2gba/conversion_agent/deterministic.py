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

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rpg2gba.conversion_agent.flag_registry import self_switch_flag_name

# -- RMXP command codes (reference/rgss_event_commands.md) --------------------
SHOW_TEXT = 101
SHOW_TEXT_CONT = 401
CONDITIONAL_BRANCH = 111
CALL_COMMON_EVENT = 117
CONTROL_SELF_SWITCH = 123
TRANSFER_PLAYER = 201
SCRIPT = 355
SCRIPT_CONT = 655
COMMENT = 108
COMMENT_CONT = 408

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


# -- dialogue-family page walker (classifiers 1–3) ----------------------------


def _dialogue_body(
    page: dict,
    *,
    map_id: int,
    event_id: int,
    allow_call: bool = False,
    allow_self_switch: bool = False,
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

    def flush() -> None:
        nonlocal buf, unsafe
        text = "".join(buf).strip()
        buf = []
        if not text:
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
        else:
            return None

    flush()
    if unsafe:
        return None
    return body


def _all_pages_action_button(event: dict) -> bool:
    pages = event.get("pages", [])
    return bool(pages) and all(pg.get("trigger") == ACTION_BUTTON_TRIGGER for pg in pages)


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


# -- context + dispatcher -----------------------------------------------------


@dataclass(frozen=True)
class Context:
    """Lookup tables the data-driven classifiers (item ball, trainer) need.

    Empty by default so the dialogue/warp classifiers (which need no external
    data) work without it; populated by ``load_context`` for a real run.
    """

    items: dict[str, str] = field(default_factory=dict)  # Essentials symbol -> ITEM_*
    trainers: dict[tuple[str, str, int], str] = field(default_factory=dict)


def load_context(*, reference_dir: Path, intermediate_dir: Path) -> Context:
    """Build the data-driven classifiers' lookup tables from Phase-2 outputs.

    Tolerant by design: a missing/unreadable file yields an empty table, and the
    classifier that needs it then falls through to the LLM rather than failing the
    run. The item-ball and trainer tables are populated when those classifiers are
    implemented; until then this returns an empty context.
    """
    return Context()


# Classifiers are tried in this order; the first non-None wins. Order follows the
# plan (most general dialogue first); detection is strict enough that overlaps do
# not occur, but order still matters for events a looser classifier could claim.
_CLASSIFIERS: list[Callable[[int, dict, "Context | None"], str | None]] = [
    classify_pure_dialogue,
]


def try_deterministic(map_id: int, event: dict, ctx: Context | None = None) -> str | None:
    """Try each classifier in order; return the first match, or None to use the LLM."""
    for classify in _CLASSIFIERS:
        try:
            out = classify(map_id, event, ctx)
        except Exception:  # a classifier must never abort the run — fall through
            out = None
        if out is not None:
            return out
    return None
