"""Resolves what dialogue text an event page should display in the ROM,
according to Uranium's own RPG Maker source.

This exists so a playtest beat can assert the ROM's on-screen text against
the SOURCE, not against a string a human retyped by hand, and not against
our own converter's emitted Poryscript. Asserting against emitted
Poryscript would only prove the ROM matches the converter -- the claim this
module backs is that the ROM matches Uranium.

Inputs are the decoded RMXP map data at `build_dir/maps/Map###.json` (one
file per map, produced by the Ruby rxdata deserializer). Dialogue text is
RPG Maker command code 101 ("Show Text", first line) followed by zero or
more code 401 ("Show Text continuation") commands; a consecutive 101/401*
run is one message box. `_extract_message_groups` walks a page's command
list the same way `chapter_manifest.generator._extract_page` does (linear
scan, numeric code dispatch), just collecting text fragments instead of
effect tags -- no second interpretation of the command-list shape.

Normalization reuses, rather than reinvents, two existing pieces of the
pipeline:

* `conversion_agent.deterministic.join_text_lines` / `translate_text_codes`
  -- the transpiler spine's own fragment-joiner and Essentials-control-code
  translator (`\\PN` -> `{PLAYER}`, `\\wt[n]`/`\\.`/`\\|` -> `{PAUSE 0xHH}`,
  `\\c[n]` and the DrawTextEx `<b>`/`<c2=X>`/... tag family dropped, `<br>`
  -> `\\n`, `\\n`/`\\l` passed through verbatim). Reusing these means this
  module's idea of "what a control code means" can never silently diverge
  from what the transpiler already emits into staged `.pory` -- and it
  refuses (raises) on anything neither table recognizes (`\\v[n]`, `\\r`,
  `\\g[..]`, a stray brace), exactly the "fail loud on a code you don't
  understand" the brief calls for.
* the vendored engine's own `engine/charmap.txt` (loaded via
  `text_validator.engine_metrics.load_charmap`, the one parser of that file)
  for character-level normalization -- see `_char_canon_table`'s docstring
  for why this, not a hand-picked substitution table, is the correct answer
  to the U+2019 problem this module exists to fix for real (CLAUDE.md's
  brief; previously dodged by rewriting an assertion in commit `2a4e4b61`
  rather than fixed here).
* `tileset_converter.assembly.apply_dialogue_char_substitutions` -- the same
  open/close typographic-quote toggle and `*`/`[`/`]` substitutions staging's
  `normalize_pory` applies to every `.pory` string literal, called here with
  `quote_escaped=False` (RMXP source text has a bare `"` for a quote, not
  `.pory`'s `\\"`). A consecutive 101/401* run (one message box, per
  `_extract_message_groups` above) becomes exactly one `.pory` string
  literal at every dialogue emission site in `deterministic.py`/
  `transpiler.py` -- so resetting the toggle per message here agrees with
  resetting it per string literal at staging, with one documented exception
  this module cannot reach anyway: `transpiler._emit_value_var_text`'s
  `\\v[N]`-substitution dialogue fans one message box out into several
  sibling literals, but `translate_text_codes` already refuses `\\v[n]`
  before normalization runs (PROJECT_TODO #109).

`playtest.emulator._invert_charmap_english_first` does exactly the
byte-to-char inversion this module also needs, but `playtest.emulator`
hard-imports the `mgba` Python bindings at module scope (an environment
without them installed, e.g. this build agent's, cannot import it at all --
confirmed: `ModuleNotFoundError: No module named 'mgba'`). The ~5-line
inversion is reimplemented locally in `_invert_first_per_byte` instead of
importing a module that would make merely importing this one fail outside
an mGBA-equipped environment; the logic is unchanged from the original and
the docstring says so at the call site.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rpg2gba.conversion_agent.deterministic import (
    SHOW_TEXT,
    SHOW_TEXT_CONT,
    join_text_lines,
    translate_text_codes,
)
from rpg2gba.playtest.charmap import invert_charmap_english_first
from rpg2gba.text_validator.engine_metrics import load_charmap
from rpg2gba.tileset_converter.assembly import apply_dialogue_char_substitutions

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceMessage:
    """One dialogue message box, resolved from Uranium's own source."""

    map_id: int
    event_id: int
    page_idx: int
    index: int  # 0-based index of this message box within the page
    text: str   # normalized, ROM-comparable, line breaks as literal "\n"
    raw: str    # verbatim source text before normalization


# -- decoded map JSON cache (module-level, mirrors playtest.cells' graph
# cache -- keyed only on the inputs `_load_map` is ever given, so a repeated
# resolver call for the same map/build_dir is a pure cache hit rather than
# re-parsing Map###.json from disk again; CLAUDE.md sec 4.2 idempotence). ---
_MAP_CACHE: dict[tuple[str, int], dict[str, Any]] = {}


def _default_build_dir() -> Path:
    """Same convention `playtest.assertions.expected_arrival_facing` and
    `pipeline.py` use: `$RPG2GBA_OUTPUT` (default `output`) / `uranium-build`.
    Never sets the env var -- only reads it."""
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"


def _load_map(map_id: int, build_dir: Path) -> dict[str, Any]:
    key = (str(build_dir), map_id)
    cached = _MAP_CACHE.get(key)
    if cached is not None:
        return cached
    path = build_dir / "maps" / f"Map{map_id:03d}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"text_source: no converted map for id {map_id} at {path}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    _MAP_CACHE[key] = data
    return data


def _find_event(map_data: dict[str, Any], map_id: int, event_id: int) -> dict[str, Any]:
    for event in map_data.get("events", []) or []:
        if event and event.get("id") == event_id:
            return event
    known = sorted(e["id"] for e in map_data.get("events", []) or [] if e)
    raise ValueError(
        f"text_source: map {map_id} has no event id {event_id} -- known "
        f"event ids on this map are {known}"
    )


def _find_page(
    event: dict[str, Any], map_id: int, event_id: int, page_idx: int
) -> dict[str, Any]:
    pages = event.get("pages") or []
    if not 0 <= page_idx < len(pages):
        raise ValueError(
            f"text_source: map {map_id} event {event_id} has {len(pages)} "
            f"page(s) -- no page index {page_idx}"
        )
    return pages[page_idx]


def _extract_message_groups(commands: list[dict[str, Any]]) -> list[list[str]]:
    """Split a page's command list into consecutive 101/(401)* runs, one
    list of raw text fragments per run. A 101 always opens a new message
    box (even immediately after another message box ends); a 401 is always
    a continuation of whatever message box immediately precedes it, and is
    treated as its own leading fragment (never merged) if none does."""
    groups: list[list[str]] = []
    current: list[str] | None = None
    for cmd in commands:
        code = cmd.get("code")
        if code == SHOW_TEXT:
            if current is not None:
                groups.append(current)
            params = cmd.get("parameters") or []
            current = [str(params[0]) if params else ""]
        elif code == SHOW_TEXT_CONT:
            params = cmd.get("parameters") or []
            frag = str(params[0]) if params else ""
            if current is None:
                current = [frag]
            else:
                current.append(frag)
        else:
            if current is not None:
                groups.append(current)
                current = None
    if current is not None:
        groups.append(current)
    return groups


# -- charmap-based character canonicalization --------------------------------
#
# `engine/charmap.txt` is the vendored engine's one source of truth for
# char<->byte. It reuses the same byte for more than one glyph in places --
# most relevantly here, byte 0xB4 is defined TWICE:
#
#     '’'         = B4      (U+2019, right single quotation mark)
#     '\''        = B4      (U+0027, ASCII apostrophe)
#
# Both compile to the identical glyph on the ROM's font -- there is no visual
# difference. But which Python `str` character a *decode* of that byte
# produces depends on which definition is treated as canonical, and
# `playtest.emulator`'s own live screen-text reader
# (`decode_text_bytes`/`_invert_charmap_english_first`) resolves that
# ambiguity by keeping the FIRST char-per-byte in file order -- which is
# U+2019, since it appears one line above the ASCII entry. That is not this
# module's invention; it is the ROM-reading side of the harness making a
# real, already-shipped decision, and this module has to agree with it or
# `expected_text()` would systematically diverge from a live emulator read
# on every apostrophe in the corpus. Reused, not re-decided, here.
_TOKEN_OR_ESCAPE_RE = re.compile(r"\{[^}]*\}|\\n|\\l")


_CHARMAP_PATH_ENV = "RPG2GBA_POKEEMERALD"
_charmap_cache: dict[str, dict[str, str]] = {}


def _default_engine_dir() -> Path:
    """Same convention as everywhere else in the pipeline: read (never set)
    `RPG2GBA_POKEEMERALD`, which `.env-paths` points at the vendored
    `engine/` (CLAUDE.md sec 3/12)."""
    return Path(os.environ.get(_CHARMAP_PATH_ENV, "engine"))


def _char_canon_table(engine_dir: Path) -> dict[str, str]:
    """char -> the char a ROM text-decode of that char's charmap byte would
    produce (see the module-level comment above `_TOKEN_OR_ESCAPE_RE`)."""
    key = str(engine_dir)
    cached = _charmap_cache.get(key)
    if cached is not None:
        return cached
    charmap_path = engine_dir / "charmap.txt"
    if not charmap_path.exists():
        raise FileNotFoundError(
            f"text_source: no charmap.txt at {charmap_path} -- resolve "
            f"{_CHARMAP_PATH_ENV} via the repo's tracked .env-paths, never "
            "set it inline (CLAUDE.md sec 3)"
        )
    char_to_byte = load_charmap(charmap_path).char_to_byte
    byte_to_char = invert_charmap_english_first(char_to_byte)
    table = {ch: byte_to_char[byte] for ch, byte in char_to_byte.items()}
    _charmap_cache[key] = table
    return table


def _canonicalize_chars(text: str, table: dict[str, str]) -> str:
    """Rewrite every literal glyph in `text` to the character a ROM
    text-decode of the same charmap byte would produce. Control tokens
    (`{PLAYER}` and friends, `\\n`, `\\l`) are passed through unexamined --
    `translate_text_codes` has already consumed every other backslash code,
    and these two are not literal glyphs. Fails loud on a character
    `engine/charmap.txt` has no entry for at all -- unrepresentable on the
    ROM's font, not something to silently drop or guess a substitute for."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        m = _TOKEN_OR_ESCAPE_RE.match(text, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        ch = text[i]
        canon = table.get(ch)
        if canon is None:
            raise ValueError(
                f"text_source: character U+{ord(ch):04X} {ch!r} has no "
                "engine/charmap.txt entry -- unrepresentable on the ROM's "
                "font; fix the source data or extend charmap.txt"
            )
        out.append(canon)
        i += 1
    return "".join(out)


_PAUSE_TOKEN_RE = re.compile(r"\{PAUSE 0x[0-9A-Fa-f]{2}\}")


def _strip_zero_width_tokens(text: str) -> str:
    """Drop the poryscript-source pause tokens `translate_text_codes` emits
    for `\\wt[n]`/`\\.`/`\\|`. They are real tokens in `.pory` source, but the
    control byte they assemble to is zero-width in a screen-scrape decode
    (`playtest.emulator.decode_text_bytes`'s own EXT_CTRL_CODE_BEGIN
    handling skips the opcode and its operand entirely) -- so the literal
    `{PAUSE 0xHH}` text must not survive into ROM-comparable output."""
    return _PAUSE_TOKEN_RE.sub("", text)


def rom_text(translated: str, table: dict[str, str]) -> str:
    """Control-code-translated message text -> what the ROM displays: strip
    zero-width pause tokens, apply staging's character substitutions, then
    canonicalize against the charmap. The one implementation, shared by
    `page_messages` and `beat_floor.walk` so the floor and the playtest can
    never disagree about a character. Raises `ValueError` on a character
    with no charmap entry."""
    text = _strip_zero_width_tokens(translated)
    text = apply_dialogue_char_substitutions(text, quote_escaped=False)
    return _canonicalize_chars(text, table)


def page_messages(
    map_id: int,
    event_id: int,
    page_idx: int,
    *,
    build_dir: Path | None = None,
) -> tuple[SourceMessage, ...]:
    """Every dialogue message box on one event page, in source order.

    Reads decoded RMXP command data (`build_dir/maps/Map###.json`), groups
    consecutive Show Text (101) + continuation (401) commands into message
    boxes, and resolves each to a `SourceMessage` carrying both the verbatim
    source (`raw`) and the text the ROM will actually display (`text`).

    Raises `ValueError` if a message's remaining control codes are not ones
    `translate_text_codes` recognizes, or if a character survives
    normalization with no `engine/charmap.txt` entry at all -- both are
    "refuse loudly" cases per this module's brief, not something to mangle
    silently."""
    resolved_build_dir = build_dir if build_dir is not None else _default_build_dir()
    map_data = _load_map(map_id, resolved_build_dir)
    event = _find_event(map_data, map_id, event_id)
    page = _find_page(event, map_id, event_id, page_idx)
    commands = page.get("list") or []

    table = _char_canon_table(_default_engine_dir())

    messages: list[SourceMessage] = []
    for idx, fragments in enumerate(_extract_message_groups(commands)):
        raw = "\n".join(fragments)
        translated = translate_text_codes(join_text_lines(fragments))
        if translated is None:
            raise ValueError(
                f"text_source: map {map_id} event {event_id} page {page_idx} "
                f"message {idx} contains a control code translate_text_codes "
                f"does not recognize -- raw fragments: {fragments!r}"
            )
        text = rom_text(translated.text, table)
        messages.append(SourceMessage(
            map_id=map_id,
            event_id=event_id,
            page_idx=page_idx,
            index=idx,
            text=text,
            raw=raw,
        ))
    return tuple(messages)


def expected_text(
    map_id: int,
    event_id: int,
    page_idx: int,
    *,
    index: int = 0,
    build_dir: Path | None = None,
) -> str:
    """The ROM-comparable text of message `index` on this page.

    Fails loud if the page has fewer than `index + 1` messages -- the
    caller is asserting about text it believes exists, so silence would be
    the wrong answer."""
    messages = page_messages(map_id, event_id, page_idx, build_dir=build_dir)
    if not 0 <= index < len(messages):
        raise ValueError(
            f"text_source: map {map_id} event {event_id} page {page_idx} "
            f"has {len(messages)} message(s) -- no message at index {index}"
        )
    return messages[index].text
