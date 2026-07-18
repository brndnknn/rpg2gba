"""S8 staging pass: auto-bracket flag-hidden cutscene actors with addobject/removeobject.

SLICE1_TODO #16. On GBA, an ``object_events`` entry gated behind a nonzero
``flag`` (a "hidden actor" — see ``metadata_wiring._assign_visibility_flags`` /
``build_object_events``'s ``hidden_actor_ids`` path) is never spawned while its
flag is set. RMXP has no such concept — an event always exists, only its
*opacity* is 0 — so a choreography script's ``applymovement(N, ...)`` against
a flag-hidden actor N silently no-ops on GBA unless something ``addobject``s
it first. The transpiler doesn't know about this GBA-only spawn gate (it only
sees RMXP semantics), so its raw output is wrong for every flag-hidden actor;
``hand_conversions/Map032_EV074.pory`` is a hand-authored fix for exactly one
instance of this class. This module makes that fix deterministic.

Given a map's staged ``.pory`` text and the set of RMXP event ids that are
flag-hidden actors on that map, ``bracket_hidden_actor_scripts`` inserts, for
every ``script { ... }`` block that references such an id N as an
object-command target (``applymovement``/``removeobject``/``addobject``/
``turnobject``/etc. — reused verbatim from ``local_id_remap``'s
``_COMMAND_PATTERN``/``_mask_strings_and_comments``, since ids at this stage
are still raw RMXP ids, pre local-id-remap):

- ``addobject(N)`` immediately before the first line referencing N, unless
  the block already addobjects N itself (hand files like
  ``Map032_EV009.pory`` do their own bracketing).
- ``removeobject(N)`` immediately after the last line referencing N (or after
  a directly-following ``waitmovement(0)``), but ONLY when the last
  ``applymovement(N, LABEL)`` in the block names a ``movement LABEL { ... }``
  block (anywhere in the file) whose last command is ``set_invisible`` — i.e.
  the actor's own choreography fades it out. Otherwise the actor is left
  spawned (``ON_TRANSITION`` re-hides it on the next map entry). Skipped
  outright if the block already has a ``removeobject(N)``.

Only ``script`` blocks are considered; ``movement``/``text``/``mapscripts``
blocks are never rewritten (only read, to resolve a movement label's last
command). String/comment contents are masked before scanning so a reference
to N inside dialogue text can never be mistaken for a command argument.

Idempotent by construction: the existing-addobject/-removeobject checks are
what make a second pass over already-bracketed text a no-op.
"""
from __future__ import annotations

import re

from rpg2gba.tileset_converter.local_id_remap import (
    _COMMAND_PATTERN,
    _mask_strings_and_comments,
)

_BRACKET_COMMENT = "# auto-bracket: flag-hidden actor"

_SCRIPT_HEADER_RE = re.compile(r"^script\s+(\S+)\s*\{")
_MOVEMENT_HEADER_RE = re.compile(r"^movement\s+(\S+)\s*\{")
_CLOSE_BRACE_RE = re.compile(r"^\}\s*$")
_APPLYMOVEMENT_RE = re.compile(
    r"\bapplymovement\s*\(\s*(\d+)\s*,\s*([A-Za-z_]\w*)\s*\)"
)


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _find_top_level_blocks(
    lines: list[str], header_re: re.Pattern[str]
) -> dict[str, tuple[int, int]]:
    """Map ``label -> (header_line_idx, closing_brace_line_idx)`` for every
    top-level ``<keyword> LABEL { ... }`` block matching `header_re`.

    A block closes at the next column-0 ``}`` line — nested ``if (...) {``
    bodies are always indented in this codebase's output (see
    `local_id_remap`/`assembly` docstrings for the same assumption). An
    unterminated block (shouldn't happen in well-formed ``.pory``) is treated
    as extending to end-of-file rather than raising, mirroring
    ``stage_slice_scripts._find_script_block``.
    """
    blocks: dict[str, tuple[int, int]] = {}
    i = 0
    n = len(lines)
    while i < n:
        m = header_re.match(lines[i])
        if not m:
            i += 1
            continue
        label = m.group(1)
        j = i + 1
        while j < n and not _CLOSE_BRACE_RE.match(lines[j]):
            j += 1
        end = j if j < n else n - 1
        blocks[label] = (i, end)
        i = end + 1
    return blocks


def _movement_last_command(lines: list[str], start: int, end: int) -> str | None:
    """The last non-blank, non-comment command line (stripped) inside a
    ``movement LABEL { ... }`` block spanning `lines[start:end+1]`, or None if
    the body is empty."""
    body = [
        stripped
        for ln in lines[start + 1 : end]
        if (stripped := ln.strip()) and not stripped.startswith("#")
    ]
    return body[-1] if body else None


def bracket_hidden_actor_scripts(
    pory_text: str, hidden_ids: set[int], *, source_name: str = "?"
) -> str:
    """Insert addobject/removeobject brackets for flag-hidden actor ids.

    `hidden_ids` are RMXP event ids on this map whose emitted object_event
    sits behind a nonzero visibility flag (see
    `stage_slice_scripts.hidden_actor_ids_from_map_json`). Must run on
    already-normalized (label-normalize + prune) but NOT YET local-id-remapped
    text — ids are matched as raw RMXP ids, exactly what `local_id_remap`
    expects to see next.

    Raises `ValueError` if a hidden actor id is referenced inside a script
    block but no insertion point can be determined (should not happen in
    practice — a non-empty match list always yields a first/last line; this
    guards the invariant rather than papering over a future refactor bug).
    """
    if not hidden_ids:
        return pory_text

    ends_with_newline = pory_text.endswith("\n")
    lines = pory_text.split("\n")
    if ends_with_newline:
        lines = lines[:-1]

    masked = _mask_strings_and_comments(pory_text)
    masked_lines = masked.split("\n")
    if ends_with_newline:
        masked_lines = masked_lines[:-1]

    if len(lines) != len(masked_lines):
        raise ValueError(
            f"{source_name}: masked text line count diverged from original "
            f"(internal invariant violation)"
        )

    script_blocks = _find_top_level_blocks(lines, _SCRIPT_HEADER_RE)
    movement_blocks = _find_top_level_blocks(lines, _MOVEMENT_HEADER_RE)
    movement_last_cmd = {
        label: _movement_last_command(lines, s, e)
        for label, (s, e) in movement_blocks.items()
    }

    # (line_idx, "before"/"after", text), collected across every block/id.
    insertions: list[tuple[int, str, str]] = []

    for _label, (s, e) in script_blocks.items():
        for eid in sorted(hidden_ids):
            matches: list[tuple[int, str]] = []
            for i in range(s, e + 1):
                for m in _COMMAND_PATTERN.finditer(masked_lines[i]):
                    if int(m.group(2)) == eid:
                        matches.append((i, m.group(1)))
            if not matches:
                continue

            has_addobject = any(cmd == "addobject" for _, cmd in matches)
            has_removeobject = any(cmd == "removeobject" for _, cmd in matches)

            first_line = matches[0][0]
            last_line = matches[-1][0]
            if not (s <= first_line <= e and s <= last_line <= e):
                raise ValueError(
                    f"{source_name}: hidden actor {eid} referenced but its "
                    f"insertion point falls outside the enclosing script "
                    f"block ({s}..{e})"
                )

            if not has_addobject:
                indent = _leading_ws(lines[first_line])
                insertions.append(
                    (first_line, "before", f"{indent}addobject({eid})  {_BRACKET_COMMENT}")
                )

            if not has_removeobject:
                last_move_label: str | None = None
                for i, cmd in matches:
                    if cmd != "applymovement":
                        continue
                    for am in _APPLYMOVEMENT_RE.finditer(masked_lines[i]):
                        if int(am.group(1)) == eid:
                            last_move_label = am.group(2)
                fades_out = (
                    last_move_label is not None
                    and movement_last_cmd.get(last_move_label) == "set_invisible"
                )
                if fades_out:
                    insert_after = last_line
                    if (
                        last_line + 1 <= e
                        and lines[last_line + 1].strip() == "waitmovement(0)"
                    ):
                        insert_after = last_line + 1
                    indent = _leading_ws(lines[last_line])
                    insertions.append(
                        (
                            insert_after,
                            "after",
                            f"{indent}removeobject({eid})  {_BRACKET_COMMENT}",
                        )
                    )

    if not insertions:
        return pory_text

    by_line: dict[int, list[tuple[str, str]]] = {}
    for line_idx, position, text in insertions:
        by_line.setdefault(line_idx, []).append((position, text))

    new_lines = list(lines)
    for line_idx in sorted(by_line.keys(), reverse=True):
        entries = by_line[line_idx]
        before_texts = [t for pos, t in entries if pos == "before"]
        after_texts = [t for pos, t in entries if pos == "after"]
        for t in reversed(after_texts):
            new_lines.insert(line_idx + 1, t)
        for t in reversed(before_texts):
            new_lines.insert(line_idx, t)

    result = "\n".join(new_lines)
    if ends_with_newline:
        result += "\n"
    return result
