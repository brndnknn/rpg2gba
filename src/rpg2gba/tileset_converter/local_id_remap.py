"""Staging-time pass: rewrite RMXP event ids into compiled object-event local ids.

The transpiler emits script commands whose first argument targets a map object
(NPC) — e.g. ``applymovement(16, ...)`` — using the RPG Maker XP event id as the
integer literal. That is not what pokeemerald's compiled Poryscript expects: the
runtime "local id" a script command like ``applymovement`` resolves against is
the object event's 1-based position in the map JSON's ``object_events`` array,
which does not generally equal the RMXP event id (maps drop/reorder events during
map-wiring). This module applies the per-map remap table the map-wiring layer
produces (``reference/uranium_id_map.json``'s sibling per-map local-id tables,
one ``Map{id:03d}.json`` per map — see ``load_local_id_table``) to rewrite those
bare integer literals in already-transpiled ``.pory`` text.

This is a *staging* pass, not part of transpilation proper: it runs once, after
the transpiler emits a map's ``.pory`` file, against fresh transpiler output.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Poryscript commands whose first argument is an object local id.
REMAP_COMMANDS: tuple[str, ...] = (
    "applymovement",
    "setobjectxy",
    "addobject",
    "removeobject",
    "turnobject",
)

_COMMAND_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(cmd) for cmd in REMAP_COMMANDS) + r")\s*\(\s*(\d+)\b"
)


def load_local_id_table(path: Path) -> dict[str, int]:
    """Load a per-map RMXP-event-id -> compiled-local-id table.

    Pinned contract with the map-wiring layer: the JSON file is a flat object
    mapping decimal-string RMXP event ids to positive-int local ids, e.g.
    ``{"9": 1, "16": 2}``, one file per map (``Map{id:03d}.json``). Fails loud
    on any deviation from that shape rather than silently coercing or skipping
    bad entries.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a JSON object, got {type(raw).__name__}")

    table: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.isdigit():
            raise ValueError(f"{path}: key {key!r} is not a decimal string")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{path}: value {value!r} for key {key!r} is not a positive int")
        table[key] = value
    return table


@dataclass
class RemapResult:
    """Result of applying a local-id remap to one ``.pory`` file's text."""

    text: str
    #: (line, command, old_id, new_id), in order of appearance.
    replacements: list[tuple[int, str, int, int]]
    #: (line, command, old_id) for object ids absent from the table, left unchanged.
    warnings: list[tuple[int, str, int]]


def _mask_strings_and_comments(text: str) -> str:
    """Blank out string-literal contents and ``#`` comments, same length as `text`.

    Double-quoted string contents (msgbox/format text) and unquoted-``#``
    trailing/full-line comments are replaced with spaces so the command-arg
    scanner can't match integers that merely appear as text inside them.
    Escaped quotes (``\\"``) inside a string are consumed as a pair so they
    don't prematurely end the string. Quote delimiters, newlines, and all
    other syntax are preserved verbatim so offsets/line numbers still line up
    with the original text.
    """
    out: list[str] = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                out.append(" ")
                out.append(" ")
                i += 2
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                i += 1
                continue
            out.append(ch if ch == "\n" else " ")
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "#":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def remap_pory_object_ids(
    pory_text: str, table: dict[str, int], *, source_name: str = "?"
) -> RemapResult:
    """Rewrite bare-integer object-local-id arguments in `pory_text` via `table`.

    Matches ``<command>(<integer>`` for every command in `REMAP_COMMANDS`
    (whitespace around the parenthesis/comma is tolerated, including
    single-arg forms like ``removeobject(16)``). Only bare integer literals
    are touched — identifier first-arguments (``OBJ_EVENT_ID_PLAYER``,
    ``LOCALID_*``, ``VAR_*``) are left alone and never produce a warning.
    Matches inside double-quoted strings or ``#`` comments are ignored (see
    `_mask_strings_and_comments`).

    All replacements are computed as spans against the *original* text in a
    single scan, then spliced in one pass — never as sequential
    search-and-replace. This matters because remap tables can be "shifting"
    (e.g. ``{"4": 2, "9": 4}``): a naive sequential replace could rewrite an
    id a moment after it was produced by an earlier substitution. One
    finditer pass followed by a single splice guarantees each original
    integer is read and rewritten exactly once, independent of table order.

    Ids with no entry in `table` are left unchanged, recorded in
    `RemapResult.warnings`, and logged via `logging.warning` (they can be
    legitimately-absent objects whose scripts are unreachable).

    Caller's responsibility (invariant): this pass must be applied exactly
    once, to fresh transpiler output. Because the table can be shifting,
    applying it a second time to already-remapped text — or to text some ids
    of which are already-compiled local ids — will corrupt ids silently.
    """
    masked = _mask_strings_and_comments(pory_text)

    replacements: list[tuple[int, str, int, int]] = []
    warnings: list[tuple[int, str, int]] = []
    spans: list[tuple[int, int, str]] = []

    for m in _COMMAND_PATTERN.finditer(masked):
        command = m.group(1)
        old_id = int(m.group(2))
        start, end = m.span(2)
        line = pory_text.count("\n", 0, start) + 1

        new_id = table.get(str(old_id))
        if new_id is None:
            warnings.append((line, command, old_id))
            logger.warning(
                "%s:%d: %s references object local id %d absent from remap table",
                source_name,
                line,
                command,
                old_id,
            )
            continue

        spans.append((start, end, str(new_id)))
        replacements.append((line, command, old_id, new_id))

    text = pory_text
    for start, end, new_text in sorted(spans, key=lambda s: s[0], reverse=True):
        text = text[:start] + new_text + text[end:]

    return RemapResult(text=text, replacements=replacements, warnings=warnings)
