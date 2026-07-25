"""The four corpus-scan rules (ROM_TEST_DEV.md C3 / design ref C3).

Each rule is a plain function ``(ExtractedString, ...) -> list[TextIssue]``.
``validate_text`` runs all four over a corpus and returns the combined list —
this is the converter-side, fail-loud gate: no emulator, exhaustive over
every emitted string, runs in seconds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .engine_metrics import (
    MSGBOX_WIDTH_PX,
    Charmap,
    measure_line_width_px,
)
from .extraction import ExtractedString

Severity = str  # "error" | "warning"

RULE_MARKUP = "TEXT_MARKUP"
RULE_HTML_TAG = "TEXT_HTML_TAG"
RULE_LINE_WIDTH = "TEXT_LINE_WIDTH"
RULE_CHARMAP = "TEXT_CHARMAP"


@dataclass(frozen=True)
class TextIssue:
    """One validator finding."""

    severity: Severity
    rule_id: str
    text: str
    location: object  # extraction.SourceLocation; typed loosely to avoid an import cycle
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.rule_id} {self.location}: {self.message}"


# --- Rule 1: unconverted Essentials/RGSS backslash markup -------------------
#
# Same safe/unsafe boundary as the transpiler's own pre-emission guard
# (conversion_agent/deterministic.py, ``_UNSAFE_TEXT_RE``): ``\n``/``\l``/``\p``
# are the only backslash sequences pokeemerald's own charmap defines
# (charmap.txt: ``'\l' = FA``, ``'\p' = FB``, ``'\n' = FE``) and the only ones
# poryscript emits verbatim; everything else backslash-prefixed is an
# Essentials escape (``\c[n]``, ``\v[n]``, ``\wt[n]``, ``\g[m,f]``, ``\sign[...]``,
# a stray ``\PN`` that slipped past translation, ...) that should never reach
# an emitted string — the transpiler's own translate_text_codes either
# converts or queues these (see deterministic.py); if one shows up here, it
# reached the ROM some other way (e.g. a hand-authored msgbox that bypassed
# translation) and that is a real corpus bug.
_UNSAFE_BACKSLASH_RE = re.compile(r"\\(?![nlp])\S*?(?=\\|\s|$)")


def check_markup(s: ExtractedString) -> list[TextIssue]:
    issues: list[TextIssue] = []
    for m in _UNSAFE_BACKSLASH_RE.finditer(s.content):
        snippet = m.group(0)
        issues.append(
            TextIssue(
                severity="error",
                rule_id=RULE_MARKUP,
                text=s.content,
                location=s.location,
                message=(
                    f"unconverted Essentials/RGSS control code {snippet!r} in "
                    f"emitted string {s.content!r}"
                ),
            )
        )
    return issues


# --- Rule 2: the DrawTextEx <br>...</br> tag family --------------------------
#
# Essentials' DrawTextEx rich-text markup (reference/scripts_dump/058_DrawText.rb,
# lines 385-417): <b>/<i>/<u>/<s>/<al>/<ar>/<ac>/<c=X>/<c2=X>/<c3=B,S>/<o=X>/
# <outln>/<outln2>/<fn=X>/<fs=X>/<icon=X>/<br>. This is a DIFFERENT text
# subsystem than the ordinary dialogue window's backslash escapes (rule 1) —
# used by Essentials' own hardcoded UI screens (Hall of Fame, Save screen,
# Phone, battle-scene PP/type readout: reference/scripts_dump/090__PokeBattle_Scene.rb,
# 148_PScreen_HallOfFame.rb, 138__PScreen_Save.rb, 133_PScreen_Phone.rb), not
# by ordinary map-event Show Text dialogue. pokeemerald's msgbox has no
# DrawTextEx-tag interpreter, so any of these reaching an emitted string
# render as their literal characters. The whole family is stripped upstream
# (deterministic.py's ``_DRAWTEXTEX_TAG_RE``, with ``<br>`` mapped to ``\n``);
# if one shows up here, that upstream handling regressed or never covered the
# path this string went through — a hand-authored ``hand_conversions/*.pory``
# bypasses the transpiler's translation entirely, for instance.
_DRAWTEXTEX_TAG_RE = re.compile(
    r"</?(?:b|i|u|s|al|ar|ac|c|c2|c3|o|outln|outln2|fn|fs|icon|br)(?:=[^>]*)?>",
    re.IGNORECASE,
)


def check_html_tag(s: ExtractedString) -> list[TextIssue]:
    issues: list[TextIssue] = []
    for m in _DRAWTEXTEX_TAG_RE.finditer(s.content):
        issues.append(
            TextIssue(
                severity="error",
                rule_id=RULE_HTML_TAG,
                text=s.content,
                location=s.location,
                message=(
                    f"Essentials DrawTextEx markup tag {m.group(0)!r} in emitted "
                    f"string {s.content!r} — pokeemerald's msgbox has no tag "
                    f"interpreter, this will render as literal characters"
                ),
            )
        )
    return issues


# --- Rule 3: chars-per-line budget, measured in pixels -----------------------
#
# See engine_metrics.py for the full grounding (message-box width, font,
# glyph-width table) and exactly what's approximated. Scope note: a string
# wrapped in ``format(...)`` is re-wrapped by poryscript at compile time using
# its own algorithm this module can't see, so whole-segment overflow on a
# format()-wrapped string is *expected*, not a bug — only a single unbreakable
# token (no space to wrap on) that alone exceeds the box width is a real,
# format()-proof overflow. A NOT-format()-wrapped string (a bare
# ``msgbox("...")`` or ``text NAME { "..." }``) renders exactly as written, so
# whole-segment overflow there is checked directly.
_BREAK_RE = re.compile(r"\\[nlp]")


def check_line_width(s: ExtractedString, charmap: Charmap) -> list[TextIssue]:
    issues: list[TextIssue] = []
    segments = _BREAK_RE.split(s.content)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if s.wrapped_in_format:
            for token in seg.split():
                w = measure_line_width_px(token, charmap)
                if w > MSGBOX_WIDTH_PX:
                    issues.append(
                        TextIssue(
                            severity="error",
                            rule_id=RULE_LINE_WIDTH,
                            text=s.content,
                            location=s.location,
                            message=(
                                f"single token {token!r} is {w}px wide, exceeds the "
                                f"{MSGBOX_WIDTH_PX}px message-box width and cannot be "
                                f"fixed by poryscript's format() re-wrap (no space to "
                                f"break on) in string {s.content!r}"
                            ),
                        )
                    )
        else:
            w = measure_line_width_px(seg, charmap)
            if w > MSGBOX_WIDTH_PX:
                issues.append(
                    TextIssue(
                        severity="error",
                        rule_id=RULE_LINE_WIDTH,
                        text=s.content,
                        location=s.location,
                        message=(
                            f"line {seg!r} is {w}px wide, exceeds the "
                            f"{MSGBOX_WIDTH_PX}px message-box width (not wrapped in "
                            f"format(), so it renders exactly as written)"
                        ),
                    )
                )
    return issues


# --- Rule 4: characters outside the emerald charmap --------------------------
#
# Delegates to tileset_converter.assembly.normalize_pory — the repo's single
# owner of charmap normalization/legality (CLAUDE.md §4.3-adjacent: it already
# handles the *->~, [->(, ]->) substitutions and \"->typographic-quote
# toggling before deciding a character is truly unrepresentable) — rather than
# reimplementing that decision here. Runs it on a synthetic one-line
# ``msgbox("<raw literal>")`` so ``ValueError`` (its fail-loud signal) maps
# 1:1 onto the ExtractedString that produced it. This mirrors exactly what
# scripts/assemble_pathfinder.py does at real assemble time (normalize_pory
# call sites there), just earlier — at corpus-scan time instead of at
# make-modern time.
def check_charmap(s: ExtractedString, allowed: set[str]) -> list[TextIssue]:
    from rpg2gba.tileset_converter import assembly as asm

    probe = f'msgbox("{s.raw_literal}")\n'
    try:
        asm.normalize_pory(probe, allowed)
    except ValueError as exc:
        return [
            TextIssue(
                severity="error",
                rule_id=RULE_CHARMAP,
                text=s.content,
                location=s.location,
                message=str(exc),
            )
        ]
    return []


def validate_text(
    strings: list[ExtractedString],
    *,
    charmap: Charmap,
    allowed_chars: set[str],
) -> list[TextIssue]:
    """Run all four rules over every extracted string; return all issues found."""
    issues: list[TextIssue] = []
    for s in strings:
        issues.extend(check_markup(s))
        issues.extend(check_html_tag(s))
        issues.extend(check_line_width(s, charmap))
        issues.extend(check_charmap(s, allowed_chars))
    return issues


def load_allowed_chars(charmap_path: Path) -> set[str]:
    from rpg2gba.tileset_converter import assembly as asm

    return asm.load_charmap_chars(charmap_path)
