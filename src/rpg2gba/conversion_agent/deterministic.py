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

# -- RMXP command codes (reference/guides/rgss_event_commands.md) --------------------
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
EXIT_EVENT_PROCESSING = 115  # RMXP "Exit Event Processing" (rgss_event_commands.md:27)

# Native RMXP commands that carry no game state and produce no Poryscript in a
# dialogue context. Frozen-Opus drops both (FABLES gate G2, 2026-06-12: Map174 ev9
# dropped Wait(106), Map031 ev9 dropped SE(250)+pbCallBub, both dialogue-only). They
# are tolerated ONLY on a page that also has real dialogue — a page whose sole
# content is a stripped SE/Wait is a cosmetic-only event whose Opus output is
# unvalidated (declined near-miss Tier 2), so it falls through to the LLM.
_DIALOGUE_PLUMBING_CODES = frozenset({WAIT, PLAY_SE})

ACTION_BUTTON_TRIGGER = 0  # RMXP page trigger: "talk to" (the NPC case)

# STRIP-classified Script (355/655) calls that carry no game state and produce no
# output (reference/recon/uranium_script_calls.md). Anchored at the start of the call
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
# Uranium's corpus writes this code in BOTH cases — 404 ``\PN`` plus 38 ``\pn``
# (13 maps: Map032/050/052/069/076/121/135/137/143/148/150/155/163) — so the
# match is deliberately case-insensitive; a case-sensitive match let ``\pn``
# fall through untranslated into emitted Poryscript, and pokeemerald's charmap
# then ate the leading ``\p`` as its own paragraph-break control code
# (engine/charmap.txt: ``'\p' = FB``), silently dropping the player-name and
# printing the stray "n" (found live: "n, you're leaving home..." should read
# "Oh, {PLAYER}, you're leaving home..."). The trailing ``\b`` is required
# once the match goes case-insensitive: without it, ``\\PN`` also matches the
# first two letters of e.g. ``\pNext`` (lowercase ``p`` + word-initial ``N``),
# which is not the player-name code at all. Corpus census confirms real
# ``\pn``/``\PN`` occurrences are never immediately followed by a word
# character (always punctuation/space/end-of-string), so ``\b`` costs nothing
# on real data and closes the false-positive window.
_TEXT_SUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\\PN\b", re.IGNORECASE), "{PLAYER}"),
)

# After the prescribed substitutions are removed, dialogue is deterministically
# translatable only if its remaining control codes are the pokeemerald-safe line
# breaks ``\n`` / ``\l`` (which poryscript emits verbatim). Any other backslash
# code is Essentials-specific and needs the agent's judgement to translate —
# ``\sign[..]`` (sign window → MSGBOX_SIGN, not yet prescribed), ``\g[m,f]``
# (gender branch), colour/pause (``\.``) codes — so the event falls through to
# the LLM. Braces are unsafe too (poryscript placeholders), which is why the
# ``\PN``/``\pn`` → ``{PLAYER}`` substitution is applied *after* this scan,
# never before.
#
# ``\p`` (pokeemerald's paragraph-break control code, charmap.txt ``'\p' =
# FB``) is deliberately NOT in the safe set, unlike ``\n``/``\l``. A full
# corpus census of every deserialized map (output/uranium-build/maps/*.json,
# 2026-08-04) found 442 backslash-p occurrences and every single one was the
# player-name code (404 ``\PN`` + 38 ``\pn``) — zero were a genuine standalone
# paragraph break. Since ``_TEXT_SUBS`` already deletes the player-name codes
# from this scan copy before this regex runs, any ``\p`` still present here is
# never the player-name code — the false negative that let ``\pn`` slip past
# this exact guard case-sensitively before. Treating it as unsafe (queue for
# the LLM tail) is strictly correct for the observed corpus; if Uranium is
# ever found to use a genuine ``\p`` paragraph break, add it back as its own
# prescribed substitution rather than reopening this lookahead.
_UNSAFE_TEXT_RE = re.compile(r"\\(?![nl])|[{}]")

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

@dataclass(frozen=True)
class TextTranslation:
    """Translated dialogue for the transpiler spine (slice1 idiom bucket).

    ``text`` is poryscript-safe. ``autoclose`` means the message ended in a
    trailing ``\\wtnp[n]`` and must be emitted as ``msgbox(.., MSGBOX_AUTOCLOSE)``.
    ``sign`` means a leading ``\\sign[..]`` was stripped and the caller wraps the
    msgbox in the gate-validated lock/release-no-faceplayer sign idiom.
    """

    text: str
    autoclose: bool = False
    sign: bool = False


# -- Extended text-code table for translate_text_codes (transpiler spine) ----
# Approved 2026-07-05, slice1 idiom review (reference/findings/slice1_queue_readthrough.md
# "Idiom" bucket, item 1 — 26 slice-1 / 627 corpus occurrences). This table is
# strictly additive: it is a *superset* of ``_TEXT_SUBS`` (reusing that tuple
# below so ``\PN`` has exactly one pattern definition), consumed only by
# ``translate_text_codes``. ``_translate_text``/``_TEXT_SUBS`` above are the
# LEGACY path the frozen-Opus classifiers depend on and are never touched.

# \wt[n] -> {PAUSE 0xHH}. Essentials waits n*2 ticks at its 40fps game loop;
# GBA text runs at 60fps, so the same wall-clock pause is n*2 * (60/40) = n*3
# GBA frames. Capped at 0xFE, the largest value that fits the one-byte pause
# operand. First-guess formula — calibrated by eye at the slice boot gate
# (CLAUDE.md §9). Hex format matches vanilla precedent: engine's
# ``{PAUSE 0x0F}`` (engine/data/text/lottery_corner.inc:19).
_WT_RE = re.compile(r"\\wt\[(\d+)\]")


def _wt_pause_repl(m: re.Match[str]) -> str:
    frames = min(0xFE, int(m.group(1)) * 3)
    return f"{{PAUSE 0x{frames:02X}}}"


# \wtnp[n] ("wait, no page" — Essentials' auto-advance-and-close code) is
# handled as its own trailing-only step in translate_text_codes, not through
# this substitution table: it maps to TextTranslation.autoclose, not to
# inline text, and the corpus census says it only ever appears at the very
# end of a message (fail loud, not silently drop, if that ever breaks).
_WTNP_RE = re.compile(r"\\wtnp\[(\d+)\]")

# \c[n] (colour) needs windowskin pixel data pokeemerald doesn't expose the
# same way — approved DROP (strip the token, keep surrounding text).
_COLOR_CODE_RE = re.compile(r"\\c\[[^\]]*\]")

# Essentials' DrawTextEx rich-text tag family (reference/scripts_dump/
# 058_DrawText.rb:385-417): <b>/<i>/<u>/<s> emphasis, <al>/<ar>/<ac> alignment,
# <c=X>/<c2=X>/<c3=B,S> colour runs, <o=X>/<outln>/<outln2> outlines,
# <fn=X>/<fs=X> font/size, <icon=X>, and the void <br>.
#
# Uranium authors used these *inline in ordinary map dialogue* (Map050's
# aptitude test), not just in the Essentials UI screens the tags were meant
# for. pokeemerald's msgbox has no tag interpreter, so anything left here
# renders as its literal characters — the boot-walk defect the text corpus
# scan found live (reference/findings/text_corpus_scan_2026-07-24.md).
#
# All of these are approved DROPs of the same shape as \c[n] above: the GBA
# has no bold/colour-run/arbitrary-font rendering in msgbox text, so the tag
# goes and its wrapped text stays. The one exception is <br>, which is not
# decoration but a line break, and maps to the charmap-legal ``\n``.
# ``<fs=n>``/``</fs>`` were the only two handled before this; the rest of the
# family went through untouched.
_DRAWTEXTEX_BR_RE = re.compile(r"<br>", re.IGNORECASE)
_DRAWTEXTEX_TAG_RE = re.compile(
    r"</?(?:b|i|u|s|al|ar|ac|c|c2|c3|o|outln|outln2|fn|fs|icon)(?:=[^>]*)?>",
    re.IGNORECASE,
)

_TextSub = tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]

_TEXT_CODE_SUBS: tuple[_TextSub, ...] = (
    (_WT_RE, _wt_pause_repl),
    (re.compile(r"\\\."), "{PAUSE 0x0F}"),  # 15 frames — same value vanilla uses around ellipses
    (re.compile(r"\\\|"), "{PAUSE 0x3C}"),  # 1 second at 60fps; \wt's first-guess family
    (_COLOR_CODE_RE, ""),
    (_DRAWTEXTEX_BR_RE, "\\n"),
    (_DRAWTEXTEX_TAG_RE, ""),
    *_TEXT_SUBS,  # \PN -> {PLAYER}, the one pattern shared with the legacy path
)


def _translate_text_code_body(text: str) -> str | None:
    """Two-pass substitution + safety scan over the extended code table.

    Same shape as ``_translate_text``: delete every recognized code from a
    scan copy (never substitute-then-scan, so a substitution's own braces —
    e.g. ``{PAUSE 0x0F}`` — can't trip the guard), then apply the real
    substitution to the text actually returned. Anything left over — an
    unrecognized escape (``\\v[n]``, ``\\r``, ``\\g[..]``) or a stray brace in
    the source — fails the scan and returns ``None``: fail loud, queue for the
    LLM tail rather than silently drop (CLAUDE.md §4.5).
    """
    scan = text
    for pat, _repl in _TEXT_CODE_SUBS:
        scan = pat.sub("", scan)
    if _UNSAFE_TEXT_RE.search(scan):
        return None
    out = text
    for pat, repl in _TEXT_CODE_SUBS:
        out = pat.sub(repl, out)
    return out


def translate_text_codes(raw: str) -> TextTranslation | None:
    """Essentials control codes → pokeemerald text, for the transpiler spine.

    Returns ``None`` when the text still contains a code with no approved
    mapping (caller queues the dialogue). Approved mappings: slice1 idiom
    review 2026-07-05 (reference/findings/slice1_queue_readthrough.md):

    1. A leading ``\\sign[..]`` is stripped and ``sign=True`` is set. A
       ``\\sign`` that is not a leading prefix is an unknown shape -> ``None``.
    2. A trailing ``\\wtnp[n]`` (possibly followed only by whitespace) is
       stripped and ``autoclose=True`` is set. A non-trailing (or repeated)
       ``\\wtnp[n]`` -> ``None`` — the corpus census says 100% are trailing;
       fail loud rather than guess if that assumption ever breaks.
    3. ``\\wt[n]`` -> ``{PAUSE 0xHH}``, ``\\.`` -> ``{PAUSE 0x0F}``,
       ``\\|`` -> ``{PAUSE 0x3C}``.
    4. ``\\c[n]`` is dropped; ``<fs=n>``/``</fs>`` tags are dropped (their
       wrapped text is kept).
    5. ``\\PN``/``\\pn`` (case-insensitive) -> ``{PLAYER}``; ``\\n``/``\\l``
       pass through verbatim.
    6. Anything else remaining (``\\v[n]``, ``\\r``, ``\\g[..]``, a stray
       brace, a ``\\p`` that isn't the player-name code, any other
       unrecognized escape) -> ``None``.
    """
    text = raw
    sign = False
    autoclose = False

    if "\\sign[" in text:
        m = _SIGN_PREFIX_RE.match(text)
        if m is None:
            return None  # \sign present but not a leading prefix -- unknown shape
        text = text[m.end() :]
        sign = True

    if "\\wtnp[" in text:
        matches = list(_WTNP_RE.finditer(text))
        if len(matches) != 1 or text[matches[0].end() :].strip():
            return None  # not exactly one trailing \wtnp -- census says 100% are
        text = text[: matches[0].start()]
        autoclose = True

    translated = _translate_text_code_body(text)
    if translated is None:
        return None
    return TextTranslation(text=translated, autoclose=autoclose, sign=sign)


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# -- string + label helpers ---------------------------------------------------


def join_text_lines(parts: list[str]) -> str:
    """Join RGSS 101 (Show Text) + 401 (Show Text continuation) fragments.

    RMXP's message window wraps dialogue at its own (wide) window width, and
    each visual line is stored as a separate string -- the 101 command holds
    the first line, each following 401 holds one more. The naive
    ``"".join(parts)`` this replaced assumed every continuation fragment
    carried its own leading space from the source, i.e. that the author wrote
    ``"Hello,"`` + ``" world!"``. That assumption is false for most of the
    corpus: a census of all 199 converted maps found 3127 total 401
    continuations, of which only 9 begin with a space and 1798 follow a
    fragment that already ends with one. The remaining 1320 are "glue" cases
    where neither side has a space -- the wrap simply landed mid-sentence --
    and blind concatenation welds two words together. A real shipped example
    (Map033 event 34, ``Trainer(4)`` at cell (36,8)) joined ``'...and I want
    to'`` + ``'see how it fares!'`` into ``"...I want tosee how it fares!"``.

    This helper inserts exactly one space at each fragment boundary unless
    doing so would be wrong:

    - Either side of the boundary is empty (nothing to join).
    - The accumulated text already ends in whitespace, or the next fragment
      already begins with whitespace -- the space is already there; adding
      another would double it (1798 + 9 corpus cases).
    - The accumulated text ends with the literal two-character escape
      ``\\n`` (a layout break the RGSS export stores verbatim).
      ``format_pory_dialogue`` flattens those to spaces downstream, so no
      extra space is needed here (90 corpus cases).
    - The accumulated text ends with a word-internal hyphen -- a hyphen
      immediately preceded by an alphanumeric character, e.g. ``'Two
      strong-'`` + ``'looking trainers'`` -> ``"strong-looking trainers"``.
      This is distinct from a hyphen used as punctuation (an em-dash-style
      break, preceded by another dash or by whitespace, as in ``'That noise
      just now --'`` or ``'waiting for a strong opponent -'``), which *does*
      take a space.

    Fragments are accumulated left-to-right and each boundary is decided
    against the running accumulated string (not just the immediately
    preceding fragment), so an empty fragment in the middle of the list
    can't hide a real boundary.
    """
    result = ""
    for nxt in parts:
        if not result or not nxt:
            result += nxt
            continue
        if result[-1].isspace() or nxt[0].isspace():
            result += nxt
            continue
        if result.endswith("\\n"):
            result += nxt
            continue
        if result.endswith("-") and len(result) >= 2 and result[-2].isalnum():
            result += nxt
            continue
        result += " " + nxt
    return result


def format_pory_string(text: str) -> str:
    """Wrap dialogue in a poryscript double-quoted string, escaping only ``"``.

    Charmap legality (the GBA has no ``"`` glyph) is *not* this function's job —
    the single owner of charmap normalization is
    ``tileset_converter.assembly.normalize_pory`` at staging, which rewrites the
    escaped ``\\"`` to typographic quotes. Emitting the escaped form here keeps
    that one source of truth (CLAUDE.md §4.3).

    Backslashes are intentionally *not* escaped: the text-safety guard
    (``_UNSAFE_TEXT_RE``) rejects any text containing a backslash before it
    reaches here, so none survive — and were the guard ever loosened to admit
    another pokeemerald-safe break (it currently allows ``\\n``/``\\l``
    through), that must pass through, not be doubled.
    """
    return '"' + text.replace('"', '\\"') + '"'


_LAYOUT_BREAK_RE = re.compile(r"(?:\\n)+")


def format_pory_dialogue(text: str) -> str:
    """Dialogue destined for a message box: a poryscript ``format("...")``
    expression that re-wraps the text to the GBA textbox width at compile time.

    Uranium's dialogue is laid out for RMXP's much wider window — single lines
    run to ~90 chars and embedded ``\\n`` breaks land mid-box, so raw pass-through
    overflows the viewport and a third consecutive ``\\n`` line draws OVER line
    two (``\\l`` is the scroll code, which the source never uses). ``format()``
    inserts correct ``\\n``/``\\l`` breaks itself but passes explicit escapes
    through untouched (verified against the pinned binary), so the RMXP layout
    breaks must be flattened to spaces first — they carry no meaning the re-wrap
    doesn't recreate.
    """
    text = _LAYOUT_BREAK_RE.sub(" ", text)
    text = re.sub(r" {2,}", " ", text).strip()
    return f"format({format_pory_string(text)})"


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
        text = join_text_lines(buf).strip()
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
        body.append(f"msgbox({format_pory_dialogue(translated)})")

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
    intro_raw = join_text_lines(intro_parts).strip()

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
    post_raw = join_text_lines(post_parts).strip()

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
        f" {format_pory_dialogue(intro)}, {format_pory_dialogue(defeat)})"
    )
    lines: list[str] = [battle_line]
    if post is not None:
        lines.append(f"msgbox({format_pory_dialogue(post)})")
    lines += ["release", "end"]
    return _block(_page_label(map_id, event, 1), lines)


# -- Classifier 10: PokePod Phone-Rematch Trainer -----------------------------
#
# Verified against Map033 EV039 (FISHERMAN "Brandon") and EV053 (YOUNGSTER
# "Richey") in output/uranium-build/maps/Map033.json (2026-08-10). A 3-page
# sight trainer offering phone registration on defeat, then a phone rematch:
#
#   Page 0 (default page, no self-switch condition, trigger 2/touch): the
#     first battle. pbTrainerIntro -> pbNoticePlayer -> optional pbCallBub ->
#     intro Show-Text -> a code-111 script conditional on
#     ``pbTrainerBattle(PBTrainers::X,"Name",_I("defeat"),false,0,false,0)``
#     whose then-branch is ``pbPhoneRegisterBattle(...)`` (split 355+655
#     because the ``_I("...")`` literal itself spans the boundary) followed by
#     self-switch A ON; then, after the branch, ``pbTrainerEnd``.
#   Page 1 (self-switch B set): the phone rematch. A code-111 conditional on
#     ``pbPhoneBattleCount(PBTrainers::X,"Name")>=1`` gates pbTrainerIntro,
#     optional pbCallBub, a rematch intro Show-Text, then three separate
#     Ruby statements (``trainer = createPhoneTrainer(...)``,
#     ``result = customTrainerBattle(trainer, "defeat")``,
#     ``pbSet(1, result == BR_WIN ? 0 : 1)`` — each its own full line, coded
#     355 then 655/655, NOT a continued literal), a nested code-111 on
#     ``$game_variables[1]==0`` (win) whose body does pbPhoneIncrement + the
#     self-switch A-on/B-off flip + pbTrainerEnd, and unconditionally (after
#     the nested branch closes) a code-115 Exit Event Processing.
#   Page 2 (self-switch A set, no B): idle post-battle dialogue that re-offers
#     phone registration. NOT converted here — see below.
#
# NOTE on a text/letter mismatch: an earlier description of this idiom given
# to this classifier's author claimed the rematch page's condition was
# "self-switch A set (B not set)". The real corpus data above says otherwise
# — the rematch page (page 1) requires self-switch B, and the idle page
# (page 2) requires self-switch A. This classifier matches the verified real
# JSON, not that description; a page-condition letter that doesn't match is a
# structural deviation and bails per the fail-loud rule below.
#
# WHAT'S EMITTED: three blocks — page 1 (this event's Page1 label) becomes a
# normal pokeemerald sight trainer, ``trainerbattle_single`` using the
# four-argument continue-script form (a ``<Page1 label>_RegisterMatchCall``
# block) instead of a trailing top-level ``register_matchcall``: on a genuine
# first win, control never falls through past ``trainerbattle_single`` (a win
# runs ``EventScript_EndTrainerBattle`` / ``gotobeatenscript``, which does not
# reach the next top-level command), so a trailing ``register_matchcall``
# would be dead code. The continue-script block runs
# ``special(PlayerFaceTrainerAfterBattle)`` + ``waitmovement(0)`` (mirroring
# engine/data/maps/Route102/scripts.inc:20-41) then
# ``register_matchcall`` (asm/macros/event.inc:2150) unconditionally — no
# ``FLAG_HAS_MATCH_CALL`` gate, since this pipeline never grants that flag and
# gating would reintroduce the same dead-code bug. Page 2 (this event's
# Page2 label) becomes an ``IsTrainerReadyForRematch``-gated
# ``trainerbattle_rematch`` (asm/macros/event.inc:823), replacing the
# hand-rolled ``pbPhoneBattleCount``/``createPhoneTrainer``/
# ``customTrainerBattle`` rematch. All symbols and the special
# (``data/specials.inc:538``) were confirmed present in the vendored
# ``engine/`` before use (CLAUDE.md §4.7).
#
# Page 3 (the original event's third RGSS page, self-switch A idle/re-offer)
# is deliberately NOT emitted. This event ends up defining only 2 of its 3
# canonical page labels — exactly the ``collapsed_pages`` shape
# ``transpile_driver._record_collapsed_pages`` already expects (the existing
# 2-page ``classify_trainer_battle`` above does the same thing, folding page 2
# into page 1's block and leaving no page-2 label at all). Native Match Call
# registration and the rematch table (owned by a separate rematch-table-
# generator workstream) supersede this event's self-switch state machine
# entirely, so nothing needs to reach page 3's idle re-offer text.
#
# FAILS LOUD (returns None, no widening) on: not exactly 3 pages; page 0's
# condition checking a self-switch, or its trigger not 2; page 1's condition
# not self-switch B, or page 2's not self-switch A; a double battle
# (``pbDoubleTrainerBattle``); a ``canlose`` argument that isn't
# ``false``/``0`` (that's ``_emit_canlose_trainer_battle_idiom``'s turf, not
# this one's); a trainer class/name/party-id combination this classifier
# can't resolve in ``ctx.trainers``; untranslatable dialogue (an Essentials
# control code with no prescribed mapping); or ANY command, ordering, or
# content mismatch against the exact shape above — including a mismatched
# trainer class/name between the ``pbTrainerIntro``, ``pbTrainerBattle``,
# ``pbPhoneRegisterBattle``, ``pbPhoneBattleCount``, and
# ``createPhoneTrainer`` calls.

_PHONE_TRAINER_INTRO_RE = re.compile(r"^pbTrainerIntro\(:(\w+)\)$")
_PHONE_NOTICE_PLAYER = "Kernel.pbNoticePlayer(get_character(0))"
_PHONE_CALLBUB_RE = re.compile(r"^pbCallBub\(\d+\)$")
_PHONE_TRAINER_END = "pbTrainerEnd"
_PHONE_REGISTER_BATTLE_RE = re.compile(
    r'^pbPhoneRegisterBattle\(_I\("(?:[^"\\]|\\.)*"\),'
    r'get_character\(0\),(?:::)?PBTrainers::(\w+),"([^"]*)",\d+\)$'
)
_PHONE_BATTLE_COUNT_RE = re.compile(
    r'^pbPhoneBattleCount\((?:::)?PBTrainers::(\w+),"([^"]*)"\)>=1$'
)
_PHONE_CREATE_TRAINER_RE = re.compile(
    r'^trainer\s*=\s*createPhoneTrainer\((?:::)?PBTrainers::(\w+),"([^"]*)",\d+\)$'
)
_PHONE_CUSTOM_BATTLE_RE = re.compile(
    r'^result\s*=\s*customTrainerBattle\(trainer,\s*"((?:[^"\\]|\\.)*)"\)$'
)
_PHONE_SET_RESULT = "pbSet(1, result == BR_WIN ? 0 : 1)"
_PHONE_WIN_CHECK = "$game_variables[1]==0"
_PHONE_INCREMENT_RE = re.compile(
    r'^pbPhoneIncrement\((?:::)?PBTrainers::(\w+),"([^"]*)",\d+\)$'
)
_PHONE_TRAINER_BATTLE_CLASS_RE = re.compile(r"(?:::)?PBTrainers::(\w+)")
_PHONE_TRAINER_BATTLE_DEFEAT_RE = re.compile(r'_I\("((?:[^"\\]|\\.)*)"\)')
_PHONE_TRAINER_BATTLE_STRIP_I_RE = re.compile(r'_I\("(?:[^"\\]|\\.)*"\)')
_PHONE_TRAINER_BATTLE_INNER_RE = re.compile(r"pbTrainerBattle\((.*?)\)\s*$", re.DOTALL)
_PHONE_TRAINER_BATTLE_NAME_RE = re.compile(r'"([^"]*)"')


def classify_phone_rematch_trainer_battle(
    map_id: int, event: dict, ctx: "Context | None" = None
) -> str | None:
    """The PokePod phone-rematch idiom — see the module-level comment above.

    Returns ``None`` (falls through to the LLM) on any structural deviation
    from the verified Map033 EV039/EV053 shape.
    """
    pages = event.get("pages", [])
    if len(pages) != 3:
        return None
    page0, page1, page2 = pages

    cond0 = page0.get("condition", {})
    if cond0.get("self_switch_valid"):
        return None
    if page0.get("trigger") != 2:
        return None

    cond1 = page1.get("condition", {})
    if not cond1.get("self_switch_valid") or cond1.get("self_switch_ch") != "B":
        return None

    cond2 = page2.get("condition", {})
    if not cond2.get("self_switch_valid") or cond2.get("self_switch_ch") != "A":
        return None

    if ctx is None:
        return None

    # ---- walk page 0: the first battle -----------------------------------
    cmds0 = [c for c in page0.get("list", []) if c.get("code") not in (COMMENT, COMMENT_CONT)]

    def _at(cmds: list[dict], i: int) -> dict | None:
        return cmds[i] if 0 <= i < len(cmds) else None

    idx = 0
    c = _at(cmds0, idx)
    if c is None or c.get("code") != SCRIPT:
        return None
    p = c.get("parameters", [""])
    m_intro = _PHONE_TRAINER_INTRO_RE.match(p[0] if p else "")
    if not m_intro:
        return None
    class_sym = m_intro.group(1)
    idx += 1

    c = _at(cmds0, idx)
    if c is None or c.get("code") != SCRIPT:
        return None
    p = c.get("parameters", [""])
    if (p[0] if p else "") != _PHONE_NOTICE_PLAYER:
        return None
    idx += 1

    c = _at(cmds0, idx)
    if c is not None and c.get("code") == SCRIPT:
        p = c.get("parameters", [""])
        if _PHONE_CALLBUB_RE.match(p[0] if p else ""):
            idx += 1

    c = _at(cmds0, idx)
    if c is None or c.get("code") != SHOW_TEXT:
        return None
    p = c.get("parameters", [""])
    intro_parts = [p[0] if p else ""]
    idx += 1
    while True:
        c = _at(cmds0, idx)
        if c is not None and c.get("code") == SHOW_TEXT_CONT:
            p = c.get("parameters", [""])
            intro_parts.append(p[0] if p else "")
            idx += 1
        else:
            break
    intro_raw = join_text_lines(intro_parts).strip()

    c = _at(cmds0, idx)
    if c is None or c.get("code") != CONDITIONAL_BRANCH:
        return None
    b_params = c.get("parameters", [])
    if len(b_params) < 2 or b_params[0] != 12 or not isinstance(b_params[1], str):
        return None
    call = b_params[1]
    if "pbTrainerBattle(" not in call or "pbDoubleTrainerBattle" in call:
        return None
    idx += 1

    c = _at(cmds0, idx)
    if c is None or c.get("code") != SCRIPT:
        return None
    p = c.get("parameters", [""])
    reg_first = p[0] if p else ""
    idx += 1
    c = _at(cmds0, idx)
    if c is None or c.get("code") != SCRIPT_CONT:
        return None
    p = c.get("parameters", [""])
    reg_second = p[0] if p else ""
    idx += 1
    m_reg = _PHONE_REGISTER_BATTLE_RE.match(reg_first + reg_second)
    if not m_reg:
        return None
    if m_reg.group(1) != class_sym:
        return None

    c = _at(cmds0, idx)
    if c is None or c.get("code") != CONTROL_SELF_SWITCH:
        return None
    p = c.get("parameters", [])
    if not p or p[0] != "A" or (len(p) > 1 and p[1] != 0):
        return None
    idx += 1

    while True:
        c = _at(cmds0, idx)
        if c is not None and c.get("code") == 0:
            idx += 1
        else:
            break

    c = _at(cmds0, idx)
    if c is None or c.get("code") != BRANCH_END:
        return None
    idx += 1

    c = _at(cmds0, idx)
    if c is None or c.get("code") != SCRIPT:
        return None
    p = c.get("parameters", [""])
    if (p[0] if p else "") != _PHONE_TRAINER_END:
        return None
    idx += 1

    while True:
        c = _at(cmds0, idx)
        if c is not None and c.get("code") == 0:
            idx += 1
        else:
            break
    if idx != len(cmds0):
        return None  # trailing junk on page 0 — deviation, fail loud

    # ---- parse the pbTrainerBattle(...) call itself ----------------------
    m_class = _PHONE_TRAINER_BATTLE_CLASS_RE.search(call)
    if not m_class or m_class.group(1) != class_sym:
        return None
    class_const = to_constant("TRAINER_CLASS", class_sym)

    m_defeat = _PHONE_TRAINER_BATTLE_DEFEAT_RE.search(call)
    defeat_raw = m_defeat.group(1) if m_defeat else ""

    cleaned_call = _PHONE_TRAINER_BATTLE_STRIP_I_RE.sub("_I", call)
    m_inner = _PHONE_TRAINER_BATTLE_INNER_RE.search(cleaned_call)
    if not m_inner:
        return None
    args = [a.strip() for a in m_inner.group(1).split(",")]
    if len(args) < 6:
        return None
    if args[5] not in ("false", "0"):
        return None  # canlose battle — _emit_canlose_trainer_battle_idiom's turf
    party_id = 0
    if args[4].isdigit():
        party_id = int(args[4])

    m_name = _PHONE_TRAINER_BATTLE_NAME_RE.search(call)
    if not m_name:
        return None
    name = m_name.group(1)
    if name != m_reg.group(2):
        return None

    trainer_const = ctx.trainers.get((class_const, name, party_id))
    if trainer_const is None:
        return None

    intro = _translate_text(intro_raw)
    if intro is None:
        return None
    defeat = _translate_text(defeat_raw)
    if defeat is None:
        return None

    # ---- walk page 1: the phone rematch ----------------------------------
    cmds1 = [c for c in page1.get("list", []) if c.get("code") not in (COMMENT, COMMENT_CONT)]
    idx = 0

    c = _at(cmds1, idx)
    if c is None or c.get("code") != CONDITIONAL_BRANCH:
        return None
    b_params = c.get("parameters", [])
    if len(b_params) < 2 or b_params[0] != 12 or not isinstance(b_params[1], str):
        return None
    m_count = _PHONE_BATTLE_COUNT_RE.match(b_params[1])
    if not m_count or m_count.group(1) != class_sym or m_count.group(2) != name:
        return None
    idx += 1

    c = _at(cmds1, idx)
    if c is None or c.get("code") != SCRIPT:
        return None
    p = c.get("parameters", [""])
    m_intro2 = _PHONE_TRAINER_INTRO_RE.match(p[0] if p else "")
    if not m_intro2 or m_intro2.group(1) != class_sym:
        return None
    idx += 1

    c = _at(cmds1, idx)
    if c is not None and c.get("code") in (SCRIPT, SCRIPT_CONT):
        p = c.get("parameters", [""])
        if _PHONE_CALLBUB_RE.match(p[0] if p else ""):
            idx += 1

    c = _at(cmds1, idx)
    if c is None or c.get("code") != SHOW_TEXT:
        return None
    p = c.get("parameters", [""])
    re_intro_parts = [p[0] if p else ""]
    idx += 1
    while True:
        c = _at(cmds1, idx)
        if c is not None and c.get("code") == SHOW_TEXT_CONT:
            p = c.get("parameters", [""])
            re_intro_parts.append(p[0] if p else "")
            idx += 1
        else:
            break
    re_intro_raw = join_text_lines(re_intro_parts).strip()

    c = _at(cmds1, idx)
    if c is None or c.get("code") != SCRIPT:
        return None
    p = c.get("parameters", [""])
    m_create = _PHONE_CREATE_TRAINER_RE.match(p[0] if p else "")
    if not m_create or m_create.group(1) != class_sym or m_create.group(2) != name:
        return None
    idx += 1

    c = _at(cmds1, idx)
    if c is None or c.get("code") != SCRIPT_CONT:
        return None
    p = c.get("parameters", [""])
    m_custom = _PHONE_CUSTOM_BATTLE_RE.match(p[0] if p else "")
    if not m_custom:
        return None
    re_defeat_raw = m_custom.group(1)
    idx += 1

    c = _at(cmds1, idx)
    if c is None or c.get("code") != SCRIPT_CONT:
        return None
    p = c.get("parameters", [""])
    if (p[0] if p else "") != _PHONE_SET_RESULT:
        return None
    idx += 1

    c = _at(cmds1, idx)
    if c is None or c.get("code") != CONDITIONAL_BRANCH:
        return None
    b_params = c.get("parameters", [])
    if len(b_params) < 2 or b_params[0] != 12 or b_params[1] != _PHONE_WIN_CHECK:
        return None
    idx += 1

    c = _at(cmds1, idx)
    if c is None or c.get("code") != SCRIPT:
        return None
    p = c.get("parameters", [""])
    m_inc = _PHONE_INCREMENT_RE.match(p[0] if p else "")
    if not m_inc or m_inc.group(1) != class_sym or m_inc.group(2) != name:
        return None
    idx += 1

    c = _at(cmds1, idx)
    if c is None or c.get("code") != CONTROL_SELF_SWITCH:
        return None
    p = c.get("parameters", [])
    if not p or p[0] != "A" or (len(p) > 1 and p[1] != 0):
        return None
    idx += 1

    c = _at(cmds1, idx)
    if c is None or c.get("code") != CONTROL_SELF_SWITCH:
        return None
    p = c.get("parameters", [])
    if not p or p[0] != "B" or len(p) < 2 or p[1] == 0:
        return None
    idx += 1

    c = _at(cmds1, idx)
    if c is None or c.get("code") != SCRIPT:
        return None
    p = c.get("parameters", [""])
    if (p[0] if p else "") != _PHONE_TRAINER_END:
        return None
    idx += 1

    while True:
        c = _at(cmds1, idx)
        if c is not None and c.get("code") == 0:
            idx += 1
        else:
            break

    c = _at(cmds1, idx)
    if c is None or c.get("code") != BRANCH_END:
        return None
    idx += 1  # closes the inner ($game_variables[1]==0) branch

    c = _at(cmds1, idx)
    if c is None or c.get("code") != EXIT_EVENT_PROCESSING:
        return None
    idx += 1

    while True:
        c = _at(cmds1, idx)
        if c is not None and c.get("code") == 0:
            idx += 1
        else:
            break

    c = _at(cmds1, idx)
    if c is None or c.get("code") != BRANCH_END:
        return None
    idx += 1  # closes the outer (pbPhoneBattleCount>=1) branch

    while True:
        c = _at(cmds1, idx)
        if c is not None and c.get("code") == 0:
            idx += 1
        else:
            break
    if idx != len(cmds1):
        return None  # trailing junk on page 1 — deviation, fail loud

    re_intro = _translate_text(re_intro_raw)
    if re_intro is None:
        return None
    re_defeat = _translate_text(re_defeat_raw)
    if re_defeat is None:
        return None

    # ---- emit -------------------------------------------------------------
    # ``register_matchcall`` as a trailing top-level command after
    # ``trainerbattle_single`` is structurally unreachable on a genuine first
    # win: a fresh win runs EventScript_EndTrainerBattle (gotobeatenscript),
    # which never falls through to the command after the trainerbattle_single
    # line. Only the four-argument ``trainerbattle_single`` continue-script
    # form (TRAINER_BATTLE_CONTINUE_SCRIPT) is reachable post-battle — see
    # engine/data/maps/Route102/scripts.inc:20-41 for the vanilla shape this
    # mirrors. Two deliberate deviations from that vanilla shape:
    #   1. No ``goto_if_set FLAG_HAS_MATCH_CALL`` gate — this pipeline has no
    #      equivalent flag grant wired up, so gating would make registration
    #      dead code again (the exact bug this fixes). Register unconditionally.
    #   2. ``special(PlayerFaceTrainerAfterBattle)`` + ``waitmovement(0)`` are
    #      kept (verified present: engine/data/specials.inc:538 and the
    #      ``special``/``waitmovement`` macros in engine/asm/macros/event.inc)
    #      so the post-battle scene still looks right.
    register_label = _page_label(map_id, event, 1) + "_RegisterMatchCall"
    battle_block = _block(
        _page_label(map_id, event, 1),
        [
            f"trainerbattle_single({trainer_const},"
            f" {format_pory_dialogue(intro)}, {format_pory_dialogue(defeat)},"
            f" {register_label})",
            "release",
            "end",
        ],
    )
    register_block = _block(
        register_label,
        [
            "special(PlayerFaceTrainerAfterBattle)",
            "waitmovement(0)",
            f"register_matchcall({trainer_const})",
            "release",
            "end",
        ],
    )
    rematch_block = _block(
        _page_label(map_id, event, 2),
        [
            "specialvar(VAR_RESULT, IsTrainerReadyForRematch)",
            "if (var(VAR_RESULT) == FALSE) {",
            "    release",
            "    end",
            "}",
            f"trainerbattle_rematch({trainer_const},"
            f" {format_pory_dialogue(re_intro)}, {format_pory_dialogue(re_defeat)})",
            "release",
            "end",
        ],
    )
    return "\n\n".join([battle_block, register_block, rematch_block])


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
        data_dir = reference_dir / "uranium_data"
        internal = json.loads(
            (data_dir / "item_internal_names.json").read_text(encoding="utf-8")
        )
        names = json.loads((data_dir / "item_names.json").read_text(encoding="utf-8"))
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
    classify_phone_rematch_trainer_battle,  # Classifier 10
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
