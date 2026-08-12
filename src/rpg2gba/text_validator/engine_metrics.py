"""Static text metrics grounded in the vendored pokeemerald-expansion engine.

Two numbers this module exists to get right, both cited against ``engine/``
(pinned per ``engine/RPG2GBA_VENDOR.md``) rather than assumed:

* the field message box's usable draw width in pixels
* each charmap glyph's draw width, for the font field messages actually use

Message-box width
------------------
``sStandardTextBox_WindowTemplates[0]`` (``engine/src/menu.c``) is::

    { .bg = 0, .tilemapLeft = 2, .tilemapTop = 15, .width = 27, .height = 4,
      .paletteNum = 15, .baseBlock = 0x194 }

``AddTextPrinterForMessage`` (``engine/src/menu.c``) prints into this window
(window 0) at ``x = 0`` via ``AddTextPrinterParameterized2`` — the frame/
border tiles are drawn outside the window's own bounds, so no extra margin is
subtracted. Usable width = ``27 tiles * 8 px/tile`` = **216 px** (``MSGBOX_WIDTH_PX``
below).

Font + glyph widths
--------------------
``AddTextPrinterForMessage`` prints with ``FONT_NORMAL``
(``AddTextPrinterParameterized2(0, FONT_NORMAL, gStringVar4, ...)``,
``engine/src/menu.c``). ``FONT_NORMAL``'s width function is
``GetGlyphWidth_Normal`` (``engine/src/text.c``), which returns
``gFontNormalLatinGlyphWidths[glyphId]`` directly — no letter-spacing added,
since ``sFontInfos[FONT_NORMAL].letterSpacing == 0`` (``engine/src/text.c``).

``gFontNormalLatinGlyphWidths`` (``engine/src/fonts.c``) is a 512-entry ``u8``
table. Only the first 256 entries are reachable from ordinary charmap bytes:
``GetStringWidth``'s default case (``engine/src/text.c``) does
``glyphWidth = func(*str, isJapanese)`` for an untagged byte, i.e. the raw
charmap byte value (0x00-0xFF) is the index. The second 256 entries
(indices 0x100-0x1FF) are only reached through the ``CHAR_EXTRA_SYMBOL``
escape (``glyphWidth = func(*++str | 0x100, isJapanese)``, ``engine/src/text.c``)
— an icon/extra-symbol glyph page dialogue text never emits, so this module
only embeds the first 256 entries (``_FONT_NORMAL_WIDTHS_0_255`` below,
transcribed verbatim from ``engine/src/fonts.c``'s ``gFontNormalLatinGlyphWidths``
rows 1-16).

Control-code width handling (also read out of ``GetStringWidth``,
``engine/src/text.c``):

* ``CHAR_NEWLINE`` (charmap ``\\n`` = ``FE``) ends the current line-width
  accumulation — never itself measured.
* Extended control codes (``EXT_CTRL_CODE_BEGIN`` = ``FC``, e.g. ``PAUSE``,
  ``COLOR``, ``PALETTE``...) are explicitly skipped: their opcode and operand
  bytes contribute **zero** width.
* String-var / name placeholders (``PLACEHOLDER_BEGIN`` = ``FD``, e.g.
  ``PLAYER``, ``STR_VAR_1..3``) resolve to the real runtime buffer and *its*
  glyphs are measured — i.e. a real name's width, not zero.

This module reimplements that walk over **source-level** (pre-compile) pory
dialogue text, so it needs its own approximations for what only exists at
runtime. See ``measure_line_width_px`` for exactly what is approximated and
where that can be wrong.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# --- message-box width --------------------------------------------------

MSGBOX_TILE_WIDTH = 27  # sStandardTextBox_WindowTemplates[0].width, engine/src/menu.c
TILE_PX = 8
MSGBOX_WIDTH_PX = MSGBOX_TILE_WIDTH * TILE_PX  # 216

# --- FONT_NORMAL glyph widths, charmap bytes 0x00-0x FF -----------------
# Transcribed verbatim from gFontNormalLatinGlyphWidths (engine/src/fonts.c),
# first 256 of its 512 entries — see module docstring for why only the first
# half applies. Index = charmap byte value (0-255); value = draw width in px.
_FONT_NORMAL_WIDTHS_0_255: tuple[int, ...] = (
    3, 6, 6, 6, 6, 6, 6, 6, 6, 6, 3, 6, 6, 6, 6, 6,
    8, 6, 6, 6, 6, 6, 6, 6, 3, 6, 6, 6, 6, 6, 6, 3,
    6, 6, 6, 6, 6, 8, 6, 6, 6, 6, 6, 6, 9, 7, 6, 3,
    3, 3, 3, 3, 10, 8, 3, 3, 7, 3, 3, 3, 3, 3, 3, 3,
    3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
    6, 6, 4, 8, 8, 8, 7, 8, 8, 4, 6, 6, 4, 4, 3, 3,
    3, 3, 3, 3, 3, 3, 3, 3, 6, 3, 3, 3, 3, 3, 3, 6,
    3, 3, 3, 3, 3, 3, 3, 6, 3, 7, 7, 7, 7, 1, 2, 3,
    4, 5, 6, 7, 6, 6, 6, 3, 3, 3, 3, 3, 3, 3, 3, 3,
    3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
    8, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 4, 6, 3, 6, 3,
    6, 6, 6, 3, 3, 6, 6, 6, 3, 7, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 4, 5, 6,
    4, 6, 6, 6, 6, 6, 5, 6, 6, 6, 6, 6, 6, 6, 6, 8,
    3, 6, 6, 6, 6, 6, 6, 3, 3, 3, 3, 8, 3, 3, 3, 3,
)
assert len(_FONT_NORMAL_WIDTHS_0_255) == 256

# Widest glyph in the printable table (10px, e.g. 'M'/'W'-class capitals /
# full-width punctuation at bytes 0x34/0x35). Used as a conservative
# per-character fallback for characters absent from the parsed charmap (that
# case is already reported by the TEXT_CHARMAP rule; this just keeps the
# line-width estimate from silently under-counting when both rules fire on
# the same string).
_FALLBACK_GLYPH_WIDTH_PX = max(_FONT_NORMAL_WIDTHS_0_255)

# Placeholders whose runtime-substituted content is a name/string of unknown
# static length ({PLAYER}, {STR_VAR_1..3}, {B_PLAYER_NAME}, ...). Width is
# APPROXIMATED (see measure_line_width_px docstring) as this many pixels —
# 7 chars (pokeemerald's PLAYER_NAME_LENGTH, include/constants/global.h)
# at the font's modal glyph width (6px, the most common value in the table
# above) = 42px. Real names vary; this is a documented approximation, not a
# measurement.
_PLAYER_NAME_MAX_CHARS = 7
_MODAL_GLYPH_WIDTH_PX = 6
PLACEHOLDER_WIDTH_PX = _PLAYER_NAME_MAX_CHARS * _MODAL_GLYPH_WIDTH_PX  # 42

# {TOKEN ...} names recognized as "runtime string of unknown length" — get
# PLACEHOLDER_WIDTH_PX. Everything else bracketed ({PAUSE ...}, {COLOR ...},
# {PALETTE ...}, etc.) is treated as a zero-width control code, matching
# GetStringWidth's EXT_CTRL_CODE_BEGIN handling (engine/src/text.c).
_NAME_LIKE_TOKEN_RE = re.compile(
    r"^(PLAYER|STR_VAR_\d+|B_PLAYER_NAME|B_PLAYER_MON\d_NAME|"
    r"B_LINK_PLAYER_NAME|B_LINK_PLAYER_MON\d_NAME|RIVAL|NAME_\w+)\b",
    re.IGNORECASE,
)

_BRACE_TOKEN_RE = re.compile(r"\{([^}]*)\}")


# --- charmap parsing (char -> byte value) --------------------------------

_CHARMAP_GLYPH_LINE_RE = re.compile(r"^'(.+?)'\s*=\s*([0-9A-Fa-f]{2})\s*(?:@.*)?$")


@dataclass(frozen=True)
class Charmap:
    """A parsed ``charmap.txt``: literal-character glyphs, byte-indexed."""

    char_to_byte: dict[str, int]

    def is_representable(self, char: str) -> bool:
        return char in self.char_to_byte

    def glyph_width_px(self, char: str) -> int:
        byte = self.char_to_byte.get(char)
        if byte is None:
            return _FALLBACK_GLYPH_WIDTH_PX
        if byte < len(_FONT_NORMAL_WIDTHS_0_255):
            return _FONT_NORMAL_WIDTHS_0_255[byte]
        return _FALLBACK_GLYPH_WIDTH_PX


def load_charmap(path: Path) -> Charmap:
    """Parse ``engine/charmap.txt`` into single-glyph char -> byte-value pairs.

    Only single-character literal-glyph lines (``'A' = BB``) count; multi-byte
    named control codes (``PAUSE = FC 08``, ``PLAYER = FD 01``) and the
    2-character escape glyphs (``'\\l' = FA``, ``'\\n' = FE``, ``'\\p' = FB``)
    are deliberately excluded — they're handled as line-break/control tokens
    elsewhere, not as measured literal characters. ``'\\'' = ...`` (the escaped
    apostrophe) is special-cased to the literal ``'`` character, mirroring
    ``tileset_converter.assembly.load_charmap_chars``.
    """
    char_to_byte: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _CHARMAP_GLYPH_LINE_RE.match(line.strip())
        if not m:
            continue
        body, hex_byte = m.group(1), m.group(2)
        if body == "\\'":
            char = "'"
        elif len(body) == 1:
            char = body
        else:
            continue  # \n \l \p or anything else multi-char -- not a literal glyph
        char_to_byte[char] = int(hex_byte, 16)
    return Charmap(char_to_byte)


def measure_line_width_px(text: str, charmap: Charmap) -> int:
    """Approximate ``GetStringWidth``'s pixel width for one already-unwrapped
    line of source-level dialogue text (i.e. text with no ``\\n``/``\\l``/``\\p``
    breaks in it — callers split on those first).

    What this measures faithfully, grounded in ``GetStringWidth``
    (``engine/src/text.c``):

    * every literal character present in ``charmap.txt`` — its real
      ``FONT_NORMAL`` glyph width, byte-exact (``Charmap.glyph_width_px``).
    * ``{PAUSE ...}``, ``{COLOR ...}``, ``{PALETTE ...}`` and other non-name
      bracketed control tokens — zero width, matching the engine's
      ``EXT_CTRL_CODE_BEGIN`` skip logic.

    Where this is an APPROXIMATION, not a measurement:

    * ``{PLAYER}`` / ``{STR_VAR_n}`` / other name-like placeholders — the
      engine measures the *real* runtime buffer's glyphs; this function has
      no runtime, so it charges a fixed ``PLACEHOLDER_WIDTH_PX`` (42px,
      documented above) regardless of the actual player name or string-var
      content. A very long nickname or item name could still overflow a line
      this function reports as fitting.
    * a character present in the source text but absent from ``charmap.txt``
      — charged the widest known glyph (10px) as a conservative stand-in.
      This should be rare in practice: the TEXT_CHARMAP rule already flags
      any such character as a hard error independently, so a line carrying
      one gets *both* issues, not a silently wrong width.
    * this function does not reimplement poryscript's own line-wrap
      algorithm (the ``format(...)`` call the transpiler wraps most dialogue
      in re-wraps text at *compile* time using its own logic this module
      never sees). See ``rules.py`` for how the two are scoped differently:
      this measures single explicit-break segments and the longest
      unbreakable (whitespace-free) run, not poryscript's chosen wrap
      points.
    """
    width = 0
    i = 0
    n = len(text)
    while i < n:
        m = _BRACE_TOKEN_RE.match(text, i)
        if m:
            token = m.group(1)
            if _NAME_LIKE_TOKEN_RE.match(token.strip()):
                width += PLACEHOLDER_WIDTH_PX
            # else: zero-width control code (PAUSE, COLOR, PALETTE, ...)
            i = m.end()
            continue
        width += charmap.glyph_width_px(text[i])
        i += 1
    return width


# --- Wrapping data-table text into explicit lines -----------------------------
#
# Nothing in pokeemerald auto-wraps a data-table string. `.description` fields
# render exactly as authored, so the line breaks must be baked in as literal
# `\n` at emit time or the whole entry draws on one line.
#
# For the Pokedex info screen that failure is not a graceful overflow: the
# entry is centred by `GetStringCenterAlignXOffset(FONT_NORMAL, description,
# DISPLAY_WIDTH)` (`src/pokedex.c:4225`), and `GetStringWidth` returns the
# *widest line* -- which for an unbroken string is the entire text. A 160-char
# entry measures ~835px against a 240px screen, so the centring offset goes
# steeply negative and the text starts far off the left edge.
#
# The budgets below are derived from vanilla, not from window geometry: across
# all 1315 `.description` entries in `engine/src/data/pokemon/species_info/`,
# no line exceeds 224px and no entry exceeds 4 lines. Vanilla is correct by
# construction, so matching it is safer than re-deriving the usable window
# width from the tilemap.
DEX_DESCRIPTION_WIDTH_PX = 224
DEX_DESCRIPTION_MAX_LINES = 4


def wrap_to_width(text: str, charmap: Charmap, *, width_px: int,
                  max_lines: int | None = None, label: str = "text") -> list[str]:
    """Greedily wrap `text` into lines no wider than `width_px`, measured in
    real glyph pixels rather than characters (the font is variable-width, so a
    character count is not a width).

    Breaks on existing whitespace only -- it never hyphenates or splits a word.
    Fails loud rather than overflowing (CLAUDE.md §4.5): a single unbreakable
    token wider than `width_px` cannot be wrapped by any algorithm, and text
    that needs more than `max_lines` lines would be silently clipped by the
    engine, so both raise instead of returning something that renders wrong.
    """
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = ""
    for word in words:
        word_px = measure_line_width_px(word, charmap)
        if word_px > width_px:
            raise ValueError(
                f"{label}: the word {word!r} alone measures {word_px}px, wider "
                f"than the {width_px}px line budget -- no wrap point exists"
            )
        candidate = f"{current} {word}" if current else word
        if measure_line_width_px(candidate, charmap) <= width_px:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    if max_lines is not None and len(lines) > max_lines:
        raise ValueError(
            f"{label}: text wraps to {len(lines)} lines at {width_px}px, "
            f"exceeds the {max_lines}-line budget -- the engine would clip it. "
            f"Text: {text!r}"
        )
    return lines
